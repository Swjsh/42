"""crypto_twin_challenger.py -- H1-crypto: a LEDGER OVERLAY challenger for the crypto twin.

GOAL-EARN-YOUR-KEEP item 7c (2026-09-13). No second Alpaca account exists for the crypto
twin, and a denylist challenger differs from the control ONLY by REFUSING some entries --
so its P&L is the control's own real fills minus the refused entries, EXACT BY
CONSTRUCTION. This module never places an order, never mutates twin state, never imports
a broker -- READ-ONLY, mirrors crypto_twin_pnl.py's own standing discipline.

H1 HYPOTHESIS (pre-registered 2026-09-13, markdown/planning/TWIN-PROGRAM.md's "the twin
becomes the 24/7 proving ground" section, §Challenger ladder): refuse organic entries whose
anchor class is SWING_PIVOT. In-sample (215 organic trips, 2026-08-11..09-09, one up-trend
regime): SWING_PIVOT n=71-78 depending on classifier, WR 8.5%, the worst class -- same shape
as the SPY audit's INTRADAY_SWING_ finding. KILL when forward refused n >= H1_KILL_N and
refused net >= 0 (the denylist would have cost nothing). SHIP-CANDIDATE when forward refused
n >= H1_SHIP_N, refused net < 0, and still < 0 after dropping the single worst refused trade
(not one lucky loss carrying the whole result). Otherwise RUNNING.

ANCHOR CLASS TAXONOMY -- {SWING_PIVOT, ROUND_NUMBER, SESSION_H_L, PRIOR_UTC_DAY_H_L_C,
INTRADAY_H_L_FORMING, NO_LEVEL_TRIGGER}, read from crypto_twin_levels.py's REAL Level
labels (quoted verbatim, not paraphrased):
  - "Prior-UTC-day H" / "Prior-UTC-day L" / "Prior-UTC-day C"        -> PRIOR_UTC_DAY_H_L_C
  - "Intraday H (forming)" / "Intraday L (forming)"                 -> INTRADAY_H_L_FORMING
  - "{Asia|Europe|Us} session H" / "... session L"                  -> SESSION_H_L
  - "Round {price:.0f}" (crypto/lib/levels.py round_number_levels)  -> ROUND_NUMBER
  - "Swing H" / "Swing L" (crypto/lib/trendlines.find_swing_points) -> SWING_PIVOT
  - no matching level, or no trigger_level_exact at all             -> NO_LEVEL_TRIGGER

CLASSIFICATION RULE (2026-09-13, coordinator directive -- "derive the class from the field
the SIGNAL CODE itself uses to pick the anchor, not a string heuristic"): crypto_twin_
signal.py's evaluate() selects the anchor via `lvl = tl.nearest_directional_level(levels.
all_levels, spot, side=...)`, and on EVERY path that returns an ENTER_BULL/ENTER_BEAR
verdict it sets BOTH `trigger_level_exact=lvl.price` (crypto_twin_core.py's _decision_row
folds this onto decisions.jsonl verbatim) AND appends `levels_active` (every level.
all_levels entry that tick, each carrying its OWN structured `label`/`kind`/`strength` --
the STARVATION-FIX 2026-08-01 field). `classify_anchor_class()` below PRICE-MATCHES
trigger_level_exact against levels_active to recover the winning Level's `label` --
NEVER a regex over `triggers` or `reason` strings. Per evaluate()'s own two ENTER return
paths, `lvl is not None` is REQUIRED to reach either one, so trigger_level_exact is
STRUCTURALLY non-null for every genuine organic ENTER row -- NO_LEVEL_TRIGGER should be
exactly 0 on real data unless levels_active is itself missing (rows that predate the
2026-08-01 field, or a bad-bars/legacy row that should never have classified as ENTER
in the first place).

CLASSIFIER DISAGREEMENT, reconciled (2026-09-13): two read-only agents classified the SAME
215 organic trips differently, both via string heuristics. Agent A (parsed the `triggers`
list's `level_<reaction>_<label>` entry): SWING_PIVOT 71, ROUND_NUMBER 64, NO_LEVEL_TRIGGER
35, SESSION_H_L 28, PRIOR_UTC_DAY_H_L_C 15, INTRADAY_H_L_FORMING 2. Agent B (regex "of (.+?)
@" over the `reason` sentence): SWING 78, ROUND 84, SESSION 30, PRIOR_UTC 21, INTRADAY 2,
NO_LEVEL 0. Per the STRUCTURAL argument above, Agent A's NO_LEVEL_TRIGGER=35 cannot be 35
genuine no-level entries (trigger_level_exact is always set for an ENTER) -- it is a parse
gap in that regex (an old `triggers` element shape, or a reaction value string its pattern
didn't anticipate), not real signal. Agent B's reason-regex counts are structurally closer
to this module's own price-matched result (both ultimately read the same `lvl.label` the
signal code picked), but this module's `--table` CLI (see main()) is the number quoted in
this session's build report as the actual one of record, per the coordinator's directive --
exact per-class agreement with Agent B is NOT asserted, only that NO_LEVEL_TRIGGER == 0.

PAIRING -- reuses crypto_twin_pnl.py's OWN entry/exit pairing and P&L math verbatim
(imported, never re-implemented): `reconstruct_trips()` walks journal.jsonl's
(ENTRY_QUALITY, EXIT_FILLED) event pairs chronologically (valid only because the twin
holds at most one position at a time -- pnl.py's own documented invariant) and `_mk_trip()`
computes each trip's usd/pct. This module additionally joins each ORGANIC trip's `entry_ts`
back to (a) the nearest decisions.jsonl ENTERED row (for `triggers`/`levels_active`/
`trigger_level_exact` -- classify_anchor_class's input, absent from journal.jsonl) and (b)
the nearest journal.jsonl PLACED row (for `notional_usd`/`sizing_mode`, Part 7b's fields) --
both by timestamp proximity within pnl.py's own `_MATCH_WINDOW_SEC` (120s), the exact
tolerance `_evidence_for` already uses for the identical class of join. This is orchestration
around pnl.py's real functions (`_rows`, `_mk_trip`, `_epoch`, `FORCE_MARKER`), not a
reimplementation of the pairing/P&L math itself.

PERFORMANCE (measured 2026-09-13, real files: decisions.jsonl 135MB/56.5K lines, journal.
jsonl 24MB/47.5K lines): a FULL join (`pnl.reconstruct_trips()` + a fresh decisions.jsonl
scan) costs ~2.6s -- NOT safe to run unconditionally on every periodic hook fire (this
module is invoked every 15 ticks from the live loop, ~every 15 minutes at 1 tick/min). Every
`update_ledger()` call therefore starts with a CHEAP pre-check: journal.jsonl's byte SIZE
(a single os.stat(), microseconds) against the size recorded at the last run. journal.jsonl
grows ONLY on an entry/exit/management EVENT (PLACED/FILLED/EXIT_FILLED/CLOSED/MANAGED/...),
never on a plain HOLD tick (unlike decisions.jsonl, which grows every tick) -- so an
unchanged size PROVES no new trip could have closed since the last run, and the expensive
join is skipped entirely (the common case, organic entries/exits are infrequent). The
expensive path runs ONLY on the (rare) periodic fire where something genuinely happened.
This is a deliberate, honest trade-off -- NOT a claim that every call is <=1s, only that the
overwhelming majority are (a stat() call), with the genuinely new-data case taking longer.

FAIL-OPEN: `update_ledger()` never raises -- any exception is caught and returned as
{"error": "..."}, matching every other twin module's contract (a bug here must never break
the live tick or the HOME build).

KILL/SHIP thresholds (`H1_KILL_N`, `H1_SHIP_N`) and the refuse class (`H1_REFUSE_CLASS`) are
module constants, not magic numbers scattered through the summary builder -- change them
here, in one place, with a REVERT note.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts",):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

import crypto_twin_pnl as pnl  # noqa: E402 -- the real pairing/classification this module reuses

TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
LEDGER_PATH = TWIN_DIR / "challenger-h1.jsonl"
SUMMARY_PATH = TWIN_DIR / "challenger-h1-summary.json"
WATERMARK_PATH = TWIN_DIR / "challenger-watermark.json"
PREREG_LADDER_DOC = REPO / "markdown" / "planning" / "TWIN-PROGRAM.md"

# --- H1 hypothesis, pre-registered (markdown/planning/TWIN-PROGRAM.md, 2026-09-13) -------
H1_REFUSE_CLASS = "SWING_PIVOT"
H1_KILL_N = 6
H1_SHIP_N = 20
# Stamped at this module's own commit (GOAL-EARN-YOUR-KEEP item 7c) -- an entry at/after
# this instant is FORWARD evidence; anything before is IN-SAMPLE (the 215-trip discovery
# set the hypothesis came from, cannot ratify it). REVERT: n/a -- this is a fixed
# provenance stamp, never meant to change after the fact.
H1_FORWARD_START_UTC = "2026-09-13T16:25:00+00:00"

ANCHOR_CLASSES = ("SWING_PIVOT", "ROUND_NUMBER", "SESSION_H_L", "PRIOR_UTC_DAY_H_L_C",
                  "INTRADAY_H_L_FORMING", "NO_LEVEL_TRIGGER")

_CURRENT_GATE = "H1"  # the ladder row presently holding the challenger -- see TWIN-PROGRAM.md


# --- anchor classification (see module docstring's CLASSIFICATION RULE) ------------------
def classify_anchor_class(decision_row: Optional[dict]) -> str:
    """The anchor class for one ENTERED decisions.jsonl row -- price-matches
    `trigger_level_exact` against `levels_active` to recover the winning Level's `label`
    (see module docstring). `decision_row=None` (no matching decision row found within the
    join window) classifies NO_LEVEL_TRIGGER, same as a genuinely absent trigger."""
    if not decision_row:
        return "NO_LEVEL_TRIGGER"
    trigger_price = decision_row.get("trigger_level_exact")
    levels_active = decision_row.get("levels_active") or []
    if trigger_price is None or not levels_active:
        return "NO_LEVEL_TRIGGER"
    try:
        trigger_price = float(trigger_price)
    except (TypeError, ValueError):
        return "NO_LEVEL_TRIGGER"
    label = None
    for lv in levels_active:
        if not isinstance(lv, dict):
            continue
        try:
            if abs(float(lv.get("price")) - trigger_price) < 1e-6:
                label = lv.get("label") or ""
                break
        except (TypeError, ValueError):
            continue
    if not label:
        return "NO_LEVEL_TRIGGER"
    if label.startswith("Prior-UTC-day"):
        return "PRIOR_UTC_DAY_H_L_C"
    if label.startswith("Intraday"):
        return "INTRADAY_H_L_FORMING"
    if label.startswith("Swing"):
        return "SWING_PIVOT"
    if label.startswith("Round "):
        return "ROUND_NUMBER"
    if "session" in label.lower():
        return "SESSION_H_L"
    return "NO_LEVEL_TRIGGER"


# --- watermark (cheap pre-check, see module docstring's PERFORMANCE note) ----------------
def _load_watermark() -> dict:
    if not WATERMARK_PATH.exists():
        return {}
    try:
        return json.loads(WATERMARK_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_watermark(wm: dict) -> None:
    try:
        WATERMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
        WATERMARK_PATH.write_text(json.dumps(wm, indent=2), encoding="utf-8")
    except OSError:
        pass  # the watermark is a performance optimization, not correctness-load-bearing


def _journal_size(journal_path: Path) -> Optional[int]:
    try:
        return os.stat(journal_path).st_size
    except OSError:
        return None


# --- ledger ------------------------------------------------------------------------------
def _already_processed_entry_ts(ledger_path: Path) -> set:
    if not ledger_path.exists():
        return set()
    out = set()
    try:
        with open(ledger_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(r, dict) and r.get("ts_utc"):
                    out.add(r["ts_utc"])
    except OSError:
        return set()
    return out


def _nearest_row(target_epoch: Optional[float], rows_with_epoch: list) -> Optional[dict]:
    """rows_with_epoch: [(epoch_or_None, row), ...]. Nearest row within pnl.py's own
    _MATCH_WINDOW_SEC, mirroring _evidence_for's exact tolerance for the same class of
    timestamp join."""
    if target_epoch is None:
        return None
    best_row, best_dist = None, None
    for e, row in rows_with_epoch:
        if e is None:
            continue
        d = abs(e - target_epoch)
        if d <= pnl._MATCH_WINDOW_SEC and (best_dist is None or d < best_dist):
            best_row, best_dist = row, d
    return best_row


def build_new_rows(*, journal_path: Path = None, decisions_path: Path = None,
                   ledger_path: Path = LEDGER_PATH) -> list:
    """The FULL join (expensive path, see module docstring's PERFORMANCE note): every
    ORGANIC trip from pnl.reconstruct_trips() not already in `ledger_path`, joined to its
    decisions.jsonl ENTERED row (anchor_class) and journal.jsonl PLACED row (notional_usd/
    sizing_mode). Pure function of the files on disk -- no I/O to `ledger_path` beyond the
    read of what's already there; callers persist the result."""
    journal_path = journal_path or pnl.JOURNAL
    decisions_path = decisions_path or pnl.DECISIONS

    trips = pnl.reconstruct_trips(journal_path, decisions_path)
    already = _already_processed_entry_ts(ledger_path)

    decisions_rows = pnl._rows(decisions_path)
    entered_with_epoch = [(pnl._epoch(r.get("ts_utc")), r)
                          for r in decisions_rows if r.get("action") == "ENTERED"]

    journal_rows = pnl._rows(journal_path)
    placed_with_epoch = [(pnl._epoch(r.get("ts_utc")), r)
                         for r in journal_rows if r.get("event") == "PLACED"]

    forward_start_epoch = pnl._epoch(H1_FORWARD_START_UTC)

    new_rows = []
    for t in trips:
        if t["bucket"] != "ORGANIC":
            continue
        entry_ts = t["entry_ts"]
        if not entry_ts or entry_ts in already:
            continue
        entry_epoch = pnl._epoch(entry_ts)
        decision_row = _nearest_row(entry_epoch, entered_with_epoch)
        anchor_class = classify_anchor_class(decision_row)
        placed_row = _nearest_row(entry_epoch, placed_with_epoch)
        notional_usd = placed_row.get("notional_usd") if placed_row else None
        sizing_mode = placed_row.get("sizing_mode") if placed_row else None
        forward = bool(entry_epoch is not None and forward_start_epoch is not None
                      and entry_epoch >= forward_start_epoch)
        new_rows.append({
            "ts_utc": entry_ts,
            "anchor_class": anchor_class,
            "refused": anchor_class == H1_REFUSE_CLASS,
            "control_pnl_usd": t["usd"],
            "notional_usd": notional_usd,
            "sizing_mode": sizing_mode,
            "forward": forward,
        })
    return new_rows


def _append_ledger(rows: list, ledger_path: Path = LEDGER_PATH) -> None:
    if not rows:
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _read_ledger(ledger_path: Path = LEDGER_PATH) -> list:
    if not ledger_path.exists():
        return []
    out = []
    try:
        with open(ledger_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return []
    return out


# --- summary (windows + kill/ship verdict) ------------------------------------------------
def _window_stats(rows: list, *, since_epoch: Optional[float] = None,
                  until_epoch: Optional[float] = None) -> dict:
    def _in_window(r):
        e = pnl._epoch(r.get("ts_utc"))
        if e is None:
            return False
        if since_epoch is not None and e < since_epoch:
            return False
        if until_epoch is not None and e > until_epoch:
            return False
        return True

    windowed = [r for r in rows if _in_window(r)]
    control_n = len(windowed)
    control_net = sum((r.get("control_pnl_usd") or 0.0) for r in windowed)
    refused = [r for r in windowed if r.get("refused")]
    refused_n = len(refused)
    refused_net = sum((r.get("control_pnl_usd") or 0.0) for r in refused)
    challenger_net = control_net - refused_net
    return {"control_n": control_n, "control_net_usd": round(control_net, 6),
           "refused_n": refused_n, "refused_net_usd": round(refused_net, 6),
           "challenger_net_usd": round(challenger_net, 6)}


def _forward_rows(rows: list) -> list:
    return [r for r in rows if r.get("forward")]


def _kill_ship_status(forward_rows: list) -> dict:
    """Pre-registered rule (module docstring, markdown/planning/TWIN-PROGRAM.md):
    KILL when forward refused n >= H1_KILL_N and refused net >= 0.
    SHIP-CANDIDATE when forward refused n >= H1_SHIP_N, refused net < 0, and still < 0
    after dropping the single worst (most negative) refused trade.
    Otherwise RUNNING, reporting progress toward both thresholds."""
    refused = [r for r in forward_rows if r.get("refused")]
    n = len(refused)
    net = sum((r.get("control_pnl_usd") or 0.0) for r in refused)
    f1_sign_holds = net < 0

    if n >= H1_KILL_N and net >= 0:
        return {"status": "KILL", "n": n, "net_usd": round(net, 6), "f1_sign_holds": f1_sign_holds}

    if n >= H1_SHIP_N and net < 0:
        worst = min(refused, key=lambda r: (r.get("control_pnl_usd") or 0.0))
        net_ex_worst = net - (worst.get("control_pnl_usd") or 0.0)
        if net_ex_worst < 0:
            return {"status": "SHIP-CANDIDATE", "n": n, "net_usd": round(net, 6),
                    "net_ex_worst_usd": round(net_ex_worst, 6), "f1_sign_holds": f1_sign_holds}

    return {"status": "RUNNING", "n": n, "net_usd": round(net, 6),
           "kill_progress": f"{n}/{H1_KILL_N}", "ship_progress": f"{n}/{H1_SHIP_N}",
           "f1_sign_holds": f1_sign_holds}


def _next_ladder_row(doc_path: Path = PREREG_LADDER_DOC, current: str = _CURRENT_GATE) -> Optional[str]:
    """The ladder row AFTER `current` in markdown/planning/TWIN-PROGRAM.md's real §Challenger
    ladder table -- read fresh every call, never hardcoded (2026-09-13 coordinator directive:
    "read the next row from that doc's table, don't hardcode"). None if the doc is unreadable
    or `current` is the last row."""
    try:
        text = doc_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    import re
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if re.match(r"^H\d+$", cells[0]):
            rows.append((cells[0], cells[1]))
    for i, (gate_id, gate_desc) in enumerate(rows):
        if gate_id == current and i + 1 < len(rows):
            next_id, next_desc = rows[i + 1]
            return f"{next_id}: {next_desc}"
    return None


def tomorrow_change_line(kill_ship: dict) -> str:
    status = kill_ship["status"]
    if status == "RUNNING":
        return f"none (H1-crypto clock running: {kill_ship['n']}/{H1_KILL_N} refused)"
    if status == "KILL":
        next_row = _next_ladder_row()
        if next_row:
            return f"KILL: H1 refuted (n={kill_ship['n']} refused net {kill_ship['net_usd']:+.2f} >= 0) -- next: {next_row}"
        return (f"KILL: H1 refuted (n={kill_ship['n']} refused net {kill_ship['net_usd']:+.2f} "
               f">= 0) -- n/a: could not read next ladder row from {PREREG_LADDER_DOC.name}")
    if status == "SHIP-CANDIDATE":
        return (f"SHIP-CANDIDATE: file prereg (n={kill_ship['n']} refused net "
               f"{kill_ship['net_usd']:+.2f}, ex-worst {kill_ship['net_ex_worst_usd']:+.2f}, "
               f"both < 0)")
    return "none (unknown status)"  # defensive, unreachable given _kill_ship_status's 3 branches


def build_summary(rows: Optional[list] = None, *, now_utc: Optional[datetime] = None) -> dict:
    rows = _read_ledger() if rows is None else rows
    now_utc = now_utc or datetime.now(timezone.utc)
    now_epoch = now_utc.timestamp()
    forward_start_epoch = pnl._epoch(H1_FORWARD_START_UTC)

    forward_rows = _forward_rows(rows)
    historical_rows = [r for r in rows if not r.get("forward")]

    windows = {
        "last_4h": _window_stats(rows, since_epoch=now_epoch - 4 * 3600),
        "last_24h": _window_stats(rows, since_epoch=now_epoch - 24 * 3600),
        "forward_since_start": _window_stats(forward_rows),
        "historical_in_sample": _window_stats(historical_rows),
    }
    kill_ship = _kill_ship_status(forward_rows)
    summary = {
        "generated_at_utc": now_utc.isoformat(),
        "h1_refuse_class": H1_REFUSE_CLASS,
        "h1_forward_start_utc": H1_FORWARD_START_UTC,
        "kill_n": H1_KILL_N, "ship_n": H1_SHIP_N,
        "windows": windows,
        "kill_ship_status": kill_ship,
        "f1_sign": "refused net < 0 (holds)" if kill_ship.get("f1_sign_holds") else "refused net >= 0 (does not hold)",
        "tomorrow_change": tomorrow_change_line(kill_ship),
        "n_ledger_rows": len(rows),
    }
    return summary


def _write_summary(now_utc: Optional[datetime] = None) -> dict:
    summary = build_summary(now_utc=now_utc)
    try:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except OSError:
        pass
    return summary


# --- the public entry point (called from crypto_twin_health.py + obsidian_vault_sync.py) --
def update_ledger(now_utc: Optional[datetime] = None) -> dict:
    """Fail-open, never raises. Cheap pre-check (see module docstring's PERFORMANCE note):
    skips the expensive join entirely when journal.jsonl hasn't grown since the last call.
    Always (re)writes challenger-h1-summary.json off whatever is on disk, even on a skip --
    the summary's rolling windows (last_4h/last_24h) need a fresh `generated_at_utc` every
    call regardless of whether new rows landed."""
    try:
        now_utc = now_utc or datetime.now(timezone.utc)
        wm = _load_watermark()
        jsize = _journal_size(pnl.JOURNAL)
        if jsize is not None and wm.get("journal_size") == jsize:
            summary = _write_summary(now_utc)
            return {"skipped": "no new journal activity since last run", "summary": summary}

        new_rows = build_new_rows()
        _append_ledger(new_rows)
        _save_watermark({"journal_size": jsize, "last_run_utc": now_utc.isoformat()})
        summary = _write_summary(now_utc)
        return {"new_rows": len(new_rows), "summary": summary}
    except Exception as e:  # noqa: BLE001 -- fail-open contract, see module docstring
        return {"error": f"{type(e).__name__}: {e}"}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true", help="run update_ledger() once and print the result")
    ap.add_argument("--table", action="store_true",
                    help="print the real anchor-class table over the current ledger (or, if "
                         "empty, run a fresh join first)")
    args = ap.parse_args(argv)
    if args.update or not args.table:
        print(json.dumps(update_ledger(), indent=2, default=str))
        return 0
    rows = _read_ledger()
    if not rows:
        rows = build_new_rows()
    counts = {c: 0 for c in ANCHOR_CLASSES}
    for r in rows:
        counts[r.get("anchor_class", "NO_LEVEL_TRIGGER")] = counts.get(r.get("anchor_class"), 0) + 1
    print(json.dumps({"n_organic_trips": len(rows), "by_anchor_class": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
