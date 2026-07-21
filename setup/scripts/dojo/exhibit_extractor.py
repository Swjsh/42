"""dojo/exhibit_extractor.py -- the nightly film-room agenda generator.

WHY THIS EXISTS (markdown/specs/DOJO-EOD-PIPELINE.md, J-directed 2026-07-21: "brainstorm
running the EOD pipeline in line with the dojo now that we have candle replays"). Every close,
the day's misses/blocks/wins are auto-extracted as EXHIBITS (bar timestamps + engine state) and
written as a dojo session manifest, so J + Sonnet can sit down, hit replay, and jump straight to
the 4-6 moments that mattered instead of re-deriving them from a raw decisions ledger. This is a
pure read of automation/state/core-decisions.jsonl (+ journal/trades.csv for J-called fills) --
zero LLM, $0, notify-only. It composes from parts that already exist (TradeAutopsy's
counterfactual replay, core-decisions.jsonl's per-minute verdict/score/trigger/gate log, the
dojo session/whisper/directive machinery) -- see the spec for the "why this composes" argument.

Exhibit classes (deterministic, mirrors the spec's extraction rules exactly):
  1. BLOCKED-TRIGGER  -- verdict SKIP_* while triggers is non-empty (the engine FIRED and a gate
     refused). Ranked #1 -- real-money attributable (OP-33(d) burden-of-proof: quotes the
     forward SPY path so the exhibit states whether the block saved or cost money).
  2. SCORE-HIGH-NO-TRIGGER -- bull_score>=9 or bear_score>=9 with triggers=[] (the engine FELT
     it but has no vocabulary for the pattern -- a capability gap, not a policy gap).
  3. EXTRA-LANE FILL -- every extra_exec entry whose nested exec.status == "PLACED" (win or
     lose, the G4 extra-setup side-channel actually filled).
  4. J-CALLED -- any journal/trades.csv row for the day with j_override == "Y" (the CSV's own
     clean marker for a J-directed trade, no heuristic needed).
Capped at ~6/day, ranked in that class order (matches the spec's own ranking).

NEVER overwrites a hand-authored brief: if automation/state/dojo/session-briefs/{date}.md
already exists and does NOT carry this module's own AUTO_MARKER, main() skips the write and
reports why (a Fable/human-curated brief -- like 2026-07-21's own hand-built exemplar -- must
never be silently clobbered by a later automated re-run for the same date). Re-running for a
date this module itself already wrote is a normal idempotent overwrite (the marker is present).

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/dojo/exhibit_extractor.py [--date YYYY-MM-DD]

Guard: backtest/tests/test_exhibit_extractor.py.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, ported from trade_autopsy.py's 2026-07-14
# popup-storm fix) ================================================================
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting can
# allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout write.
# Redirect stdio to log files BEFORE any other import gets a chance to write. This module is
# launched by the SAME wscript->run_exe_hidden.vbs->backtest-venv-pythonw chain as
# trade_autopsy.py (install-eod-dojo-manifest.ps1 mirrors install-trade-autopsy.ps1 exactly),
# so it inherits the identical exposure -- ported proactively rather than waiting for a live
# repeat of the 2026-07-14 "stop the fkin popus on my screen" incident on a new script.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[3] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "eod-dojo-manifest.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "eod-dojo-manifest.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for _p in (REPO / "setup" / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
TRADES_CSV = REPO / "journal" / "trades.csv"
OUT_DIR = STATE / "dojo" / "session-briefs"

PRIMARY_ACCOUNT = "safe"  # canonical signal source -- safe/bold share the same underlying
                          # engine signal (triggers/scores) far more often than they diverge;
                          # using one account avoids double-counting the same real-world moment
                          # as two exhibits. See module docstring / DOJO-EOD-PIPELINE.md.
MAX_GAP_MINUTES = 15       # a blocked/high-score campaign can skip a tick (score dip) without
                          # being a NEW exhibit; a gap wider than this starts a fresh run.
SCORE_HIGH_THRESHOLD = 9
CAP_EXHIBITS = 6
AUTO_MARKER = "<!-- exhibit_extractor.py:auto-generated -->"


# ---------- pure helpers (unit-tested; no I/O) ----------------------------------------------

def _parse_ts(ts_et: str) -> datetime:
    """core-decisions.jsonl's ts_et is a naive ET ISO string -- parse without tz reasoning."""
    return datetime.fromisoformat(ts_et)


def is_blocked_trigger(row: dict) -> bool:
    """The engine fired a trigger AND a gate refused the entry."""
    verdict = row.get("verdict") or ""
    return verdict.startswith("SKIP_") and bool(row.get("triggers"))


def is_score_high_no_trigger(row: dict) -> bool:
    """The engine felt a strong directional score but produced no named trigger at all."""
    if row.get("triggers"):
        return False
    bull = row.get("bull_score") or 0
    bear = row.get("bear_score") or 0
    return bull >= SCORE_HIGH_THRESHOLD or bear >= SCORE_HIGH_THRESHOLD


def score_high_side(row: dict) -> str:
    """'bull' or 'bear' -- whichever score cleared the threshold (bull wins a tie)."""
    bull = row.get("bull_score") or 0
    bear = row.get("bear_score") or 0
    return "bull" if bull >= bear else "bear"


def group_runs(rows: list[dict], key_fn, max_gap_minutes: int = MAX_GAP_MINUTES) -> list[list[dict]]:
    """Group a time-sorted, already-filtered row list into contiguous "campaign" runs: adjacent
    rows sharing the same key_fn(row) AND within max_gap_minutes of each other. Pure, no I/O.
    A key change OR a large time gap starts a new run. Rows must already be sorted by ts_et."""
    runs: list[list[dict]] = []
    for row in rows:
        if runs:
            last_run = runs[-1]
            last_row = last_run[-1]
            same_key = key_fn(last_row) == key_fn(row)
            gap = (_parse_ts(row["ts_et"]) - _parse_ts(last_row["ts_et"])).total_seconds() / 60.0
            if same_key and gap <= max_gap_minutes:
                last_run.append(row)
                continue
        runs.append([row])
    return runs


def _run_span(run: list[dict]) -> tuple[str, str]:
    return run[0]["ts_et"], run[-1]["ts_et"]


def blocked_trigger_exhibit(run: list[dict]) -> dict:
    start, end = _run_span(run)
    first, last = run[0], run[-1]
    spy_path = [r.get("spy") for r in run if r.get("spy") is not None]
    return {
        "class": "blocked_trigger",
        "rank_tier": 1,
        "start_et": start,
        "end_et": end,
        "n_ticks": len(run),
        "verdict": first.get("verdict"),
        "side": first.get("side"),
        "setup": first.get("setup"),
        "triggers": first.get("triggers"),
        "bull_score": first.get("bull_score"),
        "bear_score": first.get("bear_score"),
        "trigger_level_exact": first.get("trigger_level_exact"),
        "spy_start": spy_path[0] if spy_path else None,
        "spy_end": spy_path[-1] if spy_path else None,
        "spy_peak": max(spy_path) if spy_path else None,
        "spy_trough": min(spy_path) if spy_path else None,
        "reason": first.get("reason"),
    }


def score_high_exhibit(run: list[dict]) -> dict:
    start, end = _run_span(run)
    first = run[0]
    side = score_high_side(first)
    scores = [r.get(f"{side}_score") or 0 for r in run]
    spy_path = [r.get("spy") for r in run if r.get("spy") is not None]
    return {
        "class": "score_high_no_trigger",
        "rank_tier": 2,
        "start_et": start,
        "end_et": end,
        "n_ticks": len(run),
        "side": side,
        "score_peak": max(scores) if scores else None,
        "spy_start": spy_path[0] if spy_path else None,
        "spy_end": spy_path[-1] if spy_path else None,
    }


def extra_lane_fill_exhibits(rows: list[dict]) -> list[dict]:
    """One exhibit per PLACED extra-lane fill (the G4 extra-setup side-channel)."""
    out = []
    for row in rows:
        for e in row.get("extra_exec") or []:
            ex = e.get("exec") or {}
            if ex.get("status") != "PLACED":
                continue
            out.append({
                "class": "extra_lane_fill",
                "rank_tier": 3,
                "start_et": row["ts_et"],
                "end_et": row["ts_et"],
                "n_ticks": 1,
                "setup": e.get("setup"),
                "symbol": ex.get("symbol"),
                "qty": ex.get("qty"),
                "premium": ex.get("premium"),
                "spy_start": row.get("spy"),
                "spy_end": row.get("spy"),
            })
    return out


def j_called_exhibits(date_et: str, trades_csv: Path = TRADES_CSV) -> list[dict]:
    """One exhibit per journal/trades.csv row for the day with j_override == 'Y' -- the CSV's
    own clean marker for a J-directed trade. [] if the file is missing (never raises)."""
    if not trades_csv.exists():
        return []
    out = []
    with trades_csv.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("date") != date_et or row.get("j_override") != "Y":
                continue
            out.append({
                "class": "j_called",
                "rank_tier": 4,
                "start_et": f"{date_et}T{row.get('time_entry', '')}",
                "end_et": f"{date_et}T{row.get('time_exit', '')}",
                "n_ticks": 1,
                "setup": row.get("setup"),
                "contract": row.get("contract"),
                "dollar_pnl": row.get("dollar_pnl"),
                "notes_short": row.get("notes_short"),
            })
    return out


def rank_and_cap(exhibits: list[dict], cap: int = CAP_EXHIBITS) -> list[dict]:
    """Stable-sort by (rank_tier, start_et) -- blocked-triggers first, then score-high, then
    extra-lane fills, then J-called -- and cap at `cap` total (the spec's "~6 exhibits/day")."""
    ordered = sorted(exhibits, key=lambda e: (e["rank_tier"], e["start_et"]))
    return ordered[:cap]


# ---------- I/O layer ------------------------------------------------------------------------

def load_core_decisions(date_et: str, account: str = PRIMARY_ACCOUNT,
                        path: Path = CORE_DECISIONS) -> list[dict]:
    """Rows for one ET date + one account, time-sorted. [] on a missing file (never raises)."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("account") != account:
            continue
        if not str(r.get("ts_et", "")).startswith(date_et):
            continue
        out.append(r)
    out.sort(key=lambda r: r["ts_et"])
    return out


def build_exhibits(date_et: str, rows: list[dict]) -> list[dict]:
    """Pure orchestration over one day's already-loaded core-decisions rows + a trades.csv
    read for the J-called class. Returns the ranked, capped exhibit list.

    `trades_csv=TRADES_CSV` is forwarded EXPLICITLY (not left to j_called_exhibits' own
    default parameter) -- Python binds a default argument once at def time, so a test's
    `monkeypatch.setattr(ee, "TRADES_CSV", ...)` would silently keep hitting the ORIGINAL
    module-load-time path if this call relied on the callee's own default instead of
    re-reading the current module global at call time (the exact footgun trade_autopsy.py's
    write_twin_hypotheses docstring already documents -- same fix, same reason)."""
    blocked_runs = group_runs([r for r in rows if is_blocked_trigger(r)],
                              key_fn=lambda r: (r.get("verdict"), r.get("side")))
    score_runs = group_runs([r for r in rows if is_score_high_no_trigger(r)],
                            key_fn=score_high_side)
    exhibits = (
        [blocked_trigger_exhibit(run) for run in blocked_runs]
        + [score_high_exhibit(run) for run in score_runs]
        + extra_lane_fill_exhibits(rows)
        + j_called_exhibits(date_et, trades_csv=TRADES_CSV)
    )
    return rank_and_cap(exhibits)


def render_exhibit_section(idx: int, ex: dict) -> str:
    start = ex["start_et"].split("T")[-1][:8] if "T" in ex["start_et"] else ex["start_et"]
    end = ex["end_et"].split("T")[-1][:8] if "T" in ex["end_et"] else ex["end_et"]
    lines = [f"## EXHIBIT {idx} — {ex['class']} ({start} → {end}, {ex['n_ticks']} tick(s))", ""]
    if ex["class"] == "blocked_trigger":
        lines.append(f"- **Engine at the time:** verdict `{ex['verdict']}`, side `{ex['side']}`, "
                     f"setup `{ex['setup']}`, triggers {ex['triggers']}, "
                     f"bull={ex['bull_score']} bear={ex['bear_score']}"
                     + (f", level {ex['trigger_level_exact']}" if ex.get("trigger_level_exact") else ""))
        lines.append(f"- **Blocked by:** {ex.get('reason') or '—'}")
        lines.append(f"- **Forward SPY path:** {ex['spy_start']} → {ex['spy_end']} "
                     f"(peak {ex['spy_peak']}, trough {ex['spy_trough']}) "
                     f"-- OP-33(d): did this block save or cost money?")
        lines.append("- **Question for J:** should this have traded? which arms? what stop?")
    elif ex["class"] == "score_high_no_trigger":
        lines.append(f"- **Engine at the time:** {ex['side']} score peaked at {ex['score_peak']}, "
                     f"`triggers=[]` the entire run (a vocabulary gap, not a gate refusal).")
        lines.append(f"- **Forward SPY path:** {ex['spy_start']} → {ex['spy_end']}")
        lines.append("- **Question for J:** what candle-level trigger definition would have "
                     "captured this run? Lane A (capability) unless J names a new gate policy.")
    elif ex["class"] == "extra_lane_fill":
        lines.append(f"- **Extra-lane fill:** setup `{ex['setup']}`, symbol `{ex['symbol']}`, "
                     f"qty {ex['qty']} @ {ex['premium']}, SPY {ex['spy_start']}.")
        lines.append("- **Question for J:** walk the fill + exit on replay -- confirm the exit "
                     "shape matched the intended stop.")
    elif ex["class"] == "j_called":
        lines.append(f"- **J-called trade:** setup `{ex['setup']}`, contract `{ex['contract']}`, "
                     f"P&L ${ex['dollar_pnl']}.")
        if ex.get("notes_short"):
            lines.append(f"- **Notes:** {ex['notes_short']}")
        lines.append("- **Question for J:** capture the read that triggered this call as a "
                     "directive (Lane B candidate if it generalizes).")
    lines.append("")
    return "\n".join(lines)


def render_manifest_md(date_et: str, exhibits: list[dict]) -> str:
    L = [
        f"# DOJO FILM-ROOM BRIEF — {date_et} (auto-generated by exhibit_extractor.py)",
        "",
        AUTO_MARKER,
        "",
        "> SESSION AGENT: read markdown/specs/DOJO-SESSION-RUNBOOK.md FIRST for the mechanics "
        "(TV replay MCP tools + `python -m dojo.session` CLI from setup/scripts/). This brief "
        "is today's AGENDA -- walk these exhibits in order, whisper the engine's read at each, "
        "capture J's spoken calls as directives.",
        "",
        "## Setup (before J sits down)",
        f"1. TV: `replay_start` date={date_et} on SPY 5-min (Saty ribbon visible).",
        f"2. CLI: `python -m dojo.session start --replay-day {date_et}` (run from setup/scripts/).",
        "3. Per exhibit: `replay_step`/scroll to the bar, `replay_status` -> cursor epoch, "
        "`python -m dojo.session step --session <id> --cursor <epoch>`, read the whisper to J.",
        "",
    ]
    if not exhibits:
        L.append("_No exhibits extracted for this day (no blocked triggers, no high-score "
                 "silent runs, no extra-lane fills, no J-called trades). A quiet/clean day -- "
                 "nothing to walk._")
        return "\n".join(L) + "\n"
    for i, ex in enumerate(exhibits, start=1):
        L.append(render_exhibit_section(i, ex))
    L.append("## Close-out (session agent MUST do)")
    L.append("- `python -m dojo.session close --session <id>` -> harvest doc.")
    L.append("- Route every capture: LANE A (vocabulary/capability) vs LANE B (policy -- needs "
             "pre-reg + J's ruling). File Lane-B items into automation/overnight/queue.md.")
    L.append("- Nothing ships mid-session. After 16:00, shippable items go through their gates.")
    L.append("")
    L.append(f"_Generated by exhibit_extractor.py (Gamma_EodDojoManifest, after TradeAutopsy "
             f"16:15 ET). {len(exhibits)} exhibit(s), capped at {CAP_EXHIBITS}._")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="ET date to extract (default: today ET)")
    args = ap.parse_args()
    date_et = args.date or et_now().date().isoformat()

    try:
        # path=CORE_DECISIONS forwarded explicitly for the same def-time-binding reason as
        # build_exhibits' trades_csv=TRADES_CSV forward above -- lets a test monkeypatch the
        # module global and have it actually take effect on this call.
        rows = load_core_decisions(date_et, path=CORE_DECISIONS)
        exhibits = build_exhibits(date_et, rows)
        md = render_manifest_md(date_et, exhibits)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"{date_et}.md"
        if out_path.exists() and AUTO_MARKER not in out_path.read_text(encoding="utf-8"):
            print(f"[exhibit_extractor] SKIP -- {out_path} already exists and is NOT "
                 f"auto-generated (hand-authored brief); refusing to overwrite.", file=sys.stderr)
            return 0
        out_path.write_text(md, encoding="utf-8")
        print(f"[exhibit_extractor] {date_et}: {len(rows)} decision rows, "
             f"{len(exhibits)} exhibit(s) -> {out_path.name}")
        return 0
    except Exception as e:  # noqa: BLE001 -- notify-only: never propagate a failure
        print(f"[exhibit_extractor] ERROR (fail-open): {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
