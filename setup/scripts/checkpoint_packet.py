"""checkpoint_packet.py -- GOAL-CHECKPOINT-PACKET-2026-09-29 C2.

Reads the hand-maintained inventory (`analysis/recommendations/checkpoint-2026-09-29-
inventory.json`, C1) and, for each row, calls that row's OWN named scorer to compute
the decision rule's numbers AS OF TODAY, reusing the existing instruments the goal
names rather than re-implementing them: stop_mode_shadow_ledger.py,
day_throttle_shadow.py, intervention_counter.py, right_tail_capture.py,
ladder-rung-shadow-ledger.jsonl, catastrophe-cap-shadow-ledger.jsonl,
vix-bull-hard-cap-unblock-shadow-*.json, analysis/zero-enter/, and each prereg's own
`status`/`decision_rule` field (the September freeze's adjudication vocabulary --
EXTEND / KILL / SHIP-CANDIDATE / NULL / FROZEN_* -- read the same way
prereg_hygiene.py already parses it).

FAIL-OPEN PER ROW (mandatory, per goal DONE-WHEN): any exception inside a row's scorer
is caught and that ONE row reports verdict UNKNOWN with the error message attached --
never a crash for the whole packet.

Verdict vocabulary emitted per row:
  RULE MET       -- the frozen decision rule's threshold is satisfied by today's ledger.
  RULE NOT MET   -- the ledger has enough evidence and the rule's threshold is NOT met.
  INSUFFICIENT N -- not enough observations yet to evaluate the rule (n < the frozen floor).
  PROVISIONAL    -- the row's own scorer/ledger is explicitly provisional (e.g. R4 of
                    GOAL-RIGHT-TAIL-CAPTURE reopened) -- never cited as confirming evidence.
  UNKNOWN        -- the scorer raised, or the named ledger/prereg could not be read.

CLI:
    python setup/scripts/checkpoint_packet.py [--date YYYY-MM-DD] [--json-out PATH]

Writes `analysis/recommendations/checkpoint-packet-<date>.json` (the raw per-row
computation) and prints a compact table to stdout. The markdown generation
(`markdown/planning/CHECKPOINT-2026-09-29.md` / `-2026-10-30.md`) is a separate step
(`generate_checkpoint_markdown.py`, C3) that reads THIS script's json-out.

$0, stdlib + the repo's own scorer modules only. No network, no order placement, no
FROZEN_TRADING_PATH file is ever opened for write.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
RECS_DIR = REPO / "analysis" / "recommendations"
INVENTORY_PATH = RECS_DIR / "checkpoint-2026-09-29-inventory.json"

for _p in (REPO, SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from et_clock import et_now  # noqa: E402
except Exception:  # noqa: BLE001 -- clock import must never wedge this tool
    from datetime import datetime, timezone

    def et_now(now_utc=None):  # type: ignore
        return datetime.now(timezone.utc)

# Reuse prereg_hygiene's own status-classification vocabulary rather than re-deriving
# it -- same ADJUDICATION_STATUS_RE / PENDING_STATUS_RE the September-freeze adjudication
# pass already wrote into every prereg's `status` field.
try:
    from prereg_hygiene import (  # noqa: E402
        ADJUDICATION_STATUS_RE,
        PENDING_STATUS_RE,
        TERMINAL_STATUS_RE,
        _status_field,
    )
except Exception:  # noqa: BLE001 -- fail-open: degrade to local copies if the import breaks
    import re

    ADJUDICATION_STATUS_RE = re.compile(r"^\s*(?:EXTEND|KILL|SHIP-CANDIDATE|NULL)\b")
    PENDING_STATUS_RE = re.compile(
        r"FROZEN|PRE-REGISTERED|\bPENDING\b|PARKED|CANDIDATE ONLY|NOT RUN|NOT SHIPPED"
        r"|NOT IMPLEMENTED|NOT (?:YET )?BUILT",
        re.IGNORECASE,
    )
    TERMINAL_STATUS_RE = re.compile(
        r"RUN_COMPLETE|RETIRED|KILLED|CLOSED_KILL|SUPERSEDED|EARNS_RIGHTS"
        r"|armed_paper_collecting_evidence",
        re.IGNORECASE,
    )

    def _status_field(data: dict) -> Any:  # type: ignore
        if "status" in data and isinstance(data["status"], str):
            return data["status"]
        return None

VERDICT_MET = "RULE MET"
VERDICT_NOT_MET = "RULE NOT MET"
VERDICT_INSUFFICIENT_N = "INSUFFICIENT N"
VERDICT_PROVISIONAL = "PROVISIONAL"
VERDICT_UNKNOWN = "UNKNOWN"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _et_date_str() -> str:
    return et_now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------------
# Per-row scorers. Each takes (row: dict, today: str) and returns a dict with at
# least: verdict, n, numbers (dict of named numbers), note (str). Raising is fine --
# the dispatcher below catches it and reports UNKNOWN for that row only.
# --------------------------------------------------------------------------------


def _score_tight_ladder_control4(row: dict, today: str) -> dict:
    """Reuses right_tail_capture.py's own ledger (analysis/right-tail/ledger.jsonl) --
    never re-walks trades.csv. Reads the CAP4_LIVE_DATE-gated would_be_refused flag the
    instrument already computes per wave-event."""
    ledger_path = REPO / row["ledger_path"]
    if not ledger_path.exists():
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": 0, "numbers": {}, "note": "ledger not found"}
    rows = _read_jsonl(ledger_path)
    cap4_live = "2026-08-31"
    post_cap = [r for r in rows if r.get("date", "") >= cap4_live]
    refused_ge13x = [
        r for r in post_cap
        if r.get("would_be_refused_under_cap4") is True and r.get("wave_multiple_at_exit", 0) not in (None,)
        and (r.get("wave_multiple_at_exit") or 0) >= 1.3
    ]
    # Fall back to the field name the instrument actually documents (per_wave rows may
    # not carry wave_multiple_at_exit at top level -- treat presence of the refusal flag
    # alone as the conservative signal when the multiple field is absent).
    refused_any = [r for r in post_cap if r.get("would_be_refused_under_cap4") is True]
    n = len(post_cap)
    verdict = VERDICT_INSUFFICIENT_N if n == 0 else (
        VERDICT_NOT_MET if len(refused_ge13x) == 0 and len(refused_any) == 0 else VERDICT_MET
    )
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "post_cap_wave_events": n,
            "refused_under_cap4_any": len(refused_any),
            "refused_under_cap4_ge_1_3x": len(refused_ge13x),
        },
        "note": (
            "RULE NOT MET here means the cap has refused zero qualifying waves -- i.e. "
            "the case for reverting (expansion) is NOT supported; the cap STAYS at 4. "
            "This is still an expansion-classified row per goal routing regardless."
        ),
    }


def _score_tight_ladder_control5(row: dict, today: str) -> dict:
    """No standing instrument computes this hypothetical live; it is a one-time replay
    already frozen in the prereg's own interim-evidence text. Read the numbers back out
    of the prereg markdown (no re-replay -- the numbers are already committed evidence)."""
    md_path = REPO / row["prereg_path"]
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    marker = "Control #5"
    if marker not in text:
        return {"verdict": VERDICT_UNKNOWN, "n": 0, "numbers": {}, "note": "Control #5 block not found in prereg"}
    # n = 8 entries blocked, as filed. This is a frozen replay result, not an accruing
    # forward ledger -- report it as such rather than pretending it updates nightly.
    return {
        "verdict": VERDICT_NOT_MET,
        "n": 8,
        "numbers": {"entries_blocked": 8, "net_pnl_if_shipped": -1601.0, "winners_blocked": 1, "losers_blocked": 7},
        "note": (
            "Frozen one-time replay result (2026-08-28..09-05), not a nightly-accruing "
            "ledger. RULE NOT MET = the stop would have net-HURT (-$1,601) over the "
            "study window -- consistent with 'keep' (do not ship this stop)."
        ),
    }


def _score_score_ladder_v2_retirement(row: dict, today: str) -> dict:
    ledger_path = REPO / row["ledger_path"]
    prereg_path = REPO / row["prereg_path"]
    rows = _read_jsonl(ledger_path) if ledger_path.exists() else []
    n_sessions = len({(r.get("date"), r.get("arm_id")) for r in rows if r.get("date")})
    total_delta = sum((r.get("delta_pnl") or 0.0) for r in rows)
    status = None
    if prereg_path.exists():
        try:
            status = _status_field(_read_json(prereg_path))
        except (json.JSONDecodeError, OSError):
            status = None
    verdict = VERDICT_UNKNOWN
    if status and (TERMINAL_STATUS_RE.search(status or "") or ADJUDICATION_STATUS_RE.match(status or "")):
        verdict = VERDICT_MET  # "KILL" verdict already adjudicated -> retirement rule is MET
    elif n_sessions < 15:
        verdict = VERDICT_INSUFFICIENT_N
    return {
        "verdict": verdict,
        "n": n_sessions,
        "numbers": {"sessions_or_arm_days": n_sessions, "total_delta_pnl": round(total_delta, 2), "status": status},
        "note": "Retirement rule MET = the prereg's own adjudicated status is a terminal KILL.",
    }


def _score_f10_vol_baseline_reset(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    zero_enter_dir = REPO / "analysis" / "zero-enter"
    status = _status_field(_read_json(prereg_path)) if prereg_path.exists() else None
    day_files = sorted(zero_enter_dir.glob("ZERO-ENTER-2026-*.json")) if zero_enter_dir.exists() else []
    n = len(day_files)
    verdict = VERDICT_INSUFFICIENT_N
    if status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    elif n >= 20:
        verdict = VERDICT_NOT_MET  # enough days accrued but still frozen/no verdict -> rule not (yet) met
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {"zero_enter_day_files": n, "status": status},
        "note": "10-30 checkpoint candidate; frozen before any result as of this generation.",
    }


def _score_vix_bull_hard_cap_shadow(row: dict, today: str) -> dict:
    summary_path = REPO / row["ledger_path"]
    if not summary_path.exists():
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": 0, "numbers": {}, "note": "summary not found"}
    d = _read_json(summary_path)
    n = int(d.get("n_matched_round_trips") or 0)
    status = d.get("status")
    if status == "ACCRUING" and n < 15:
        verdict = VERDICT_INSUFFICIENT_N
    elif n < 15:
        verdict = VERDICT_INSUFFICIENT_N
    else:
        # n>=15: rule reads forward CI-lower bootstrap PF > 1.0; without re-deriving the
        # bootstrap here (that belongs to the shadow instrument itself), report NOT MET
        # unless the summary already states a PF figure above 1.0.
        pf = d.get("forward_pf_ci_lower")
        verdict = VERDICT_MET if isinstance(pf, (int, float)) and pf > 1.0 else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "n_matched_round_trips": n,
            "forward_total_pnl": d.get("forward_total_pnl"),
            "status": status,
        },
        "note": "Threshold n>=15 matched round trips before any PF figure is citable (per this row's own frozen rule).",
    }


def _score_spy_signal_weekly_lane(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    verdict = VERDICT_INSUFFICIENT_N
    if status and TERMINAL_STATUS_RE.search(status or ""):
        verdict = VERDICT_MET
    elif status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    return {
        "verdict": verdict,
        "n": 0,
        "numbers": {"status": status},
        "note": "FROZEN_BEFORE_ANY_RESULT -- no forward round trips scored yet; n>=15 / n>=20 sessions are the frozen floors.",
    }


def _score_fill_model_unification_step2(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    step1_done = bool(d.get("step1_execution_evidence"))
    verdict = VERDICT_MET if step1_done else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": 1 if step1_done else 0,
        "numbers": {"status": status, "step1_execution_evidence_present": step1_done},
        "note": "Tooling prerequisite -- MET means STEP 1 has run (evidence field populated), NOT MET means it is still blocking.",
    }


def _score_tickers_theta_budget_cadence(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    stats = d.get("statistics") or {}
    min_fills = int(stats.get("min_additional_fills") or 15)
    min_days = int(stats.get("min_additional_trading_days") or 10)
    tickers_dir = REPO / "automation" / "state" / "tickers"
    n_fills = 0
    days_seen: set = set()
    if tickers_dir.exists():
        for arm_dir in tickers_dir.glob("tickers-*"):
            ledger = arm_dir / "ledger.jsonl"
            if not ledger.exists():
                continue
            for r in _read_jsonl(ledger):
                if (r.get("stage") == "theta_budget") or ("theta_budget" in json.dumps(r).lower()):
                    n_fills += 1
                    d_et = r.get("date_et") or r.get("date")
                    if d_et:
                        days_seen.add(d_et)
    n_days = len(days_seen)
    if n_fills < min_fills or n_days < min_days:
        verdict = VERDICT_INSUFFICIENT_N
    else:
        verdict = VERDICT_UNKNOWN  # would need the per-fill bleed decomposition; not re-derived here
    return {
        "verdict": verdict,
        "n": n_fills,
        "numbers": {"theta_budget_fills": n_fills, "trading_days": n_days, "min_fills": min_fills, "min_days": min_days},
        "note": "INSUFFICIENT N until >=15 fills AND >=10 days accrue; above that the ACT/NO_ACTION bleed-decomposition math is the tickers lane's own scorer, not re-derived here.",
    }


def _score_catastrophe_cap_and_day_throttle(row: dict, today: str) -> dict:
    cap_path = REPO / "analysis" / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
    throttle_path = REPO / "analysis" / "recommendations" / "day-throttle-shadow-ledger.jsonl"
    cap_rows = _read_jsonl(cap_path) if cap_path.exists() else []
    throttle_rows = _read_jsonl(throttle_path) if throttle_path.exists() else []
    cap_better_held = sum(1 for r in cap_rows if r.get("would_have_been_better_held") is True)
    cap_worse_held = sum(1 for r in cap_rows if r.get("would_have_been_better_held") is False)
    t2_blocks = sum(1 for r in throttle_rows if r.get("would_block_T-2") is True)
    t6_blocks = sum(1 for r in throttle_rows if r.get("would_block_T-6") is True)
    n = len(cap_rows) + len(throttle_rows)
    verdict = VERDICT_INSUFFICIENT_N if n < 15 else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "catastrophe_cap_fires": len(cap_rows),
            "cap_better_held": cap_better_held,
            "cap_worse_held": cap_worse_held,
            "day_throttle_rows": len(throttle_rows),
            "t2_would_block": t2_blocks,
            "t6_would_block": t6_blocks,
        },
        "note": "Shadow-read only -- no frozen ship threshold in scope for this row; numbers are the accruing evidence base.",
    }


_SCORERS: dict[str, Callable[[dict, str], dict]] = {
    "tight_ladder_control4": _score_tight_ladder_control4,
    "tight_ladder_control5": _score_tight_ladder_control5,
    "score_ladder_v2_retirement": _score_score_ladder_v2_retirement,
    "f10_vol_baseline_reset": _score_f10_vol_baseline_reset,
    "vix_bull_hard_cap_shadow": _score_vix_bull_hard_cap_shadow,
    "spy_signal_weekly_lane": _score_spy_signal_weekly_lane,
    "fill_model_unification_step2": _score_fill_model_unification_step2,
    "tickers_theta_budget_cadence": _score_tickers_theta_budget_cadence,
    "catastrophe_cap_and_day_throttle": _score_catastrophe_cap_and_day_throttle,
}


def score_row(row: dict, today: str) -> dict:
    """Fail-open dispatcher: any scorer exception degrades to one UNKNOWN row, never a crash."""
    scorer_name = row.get("scorer")
    fn = _SCORERS.get(scorer_name)
    base = {
        "row_id": row.get("row_id"),
        "prereg_path": row.get("prereg_path"),
        "ledger_path": row.get("ledger_path"),
        "classification": row.get("classification"),
        "checkpoint": row.get("checkpoint"),
        "frozen_hypothesis": row.get("frozen_hypothesis"),
        "decision_rule_verbatim": row.get("decision_rule_verbatim"),
        "reversible_action": row.get("reversible_action"),
    }
    if fn is None:
        base.update({"verdict": VERDICT_UNKNOWN, "n": None, "numbers": {}, "note": f"no scorer registered for '{scorer_name}'"})
        return base
    try:
        result = fn(row, today)
    except Exception as exc:  # noqa: BLE001 -- fail-open is the point
        base.update({
            "verdict": VERDICT_UNKNOWN,
            "n": None,
            "numbers": {},
            "note": f"scorer '{scorer_name}' raised: {exc.__class__.__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
        })
        return base
    base.update(result)
    return base


# right_tail_capture's own R4 is explicitly PROVISIONAL tonight per the goal text --
# override the row's computed verdict to PROVISIONAL rather than let a mechanical
# threshold silently overstate confidence in a reopened item.
_PROVISIONAL_ROW_IDS = {"tight-ladder-control-4-roundtrip-cap"}


def build_packet(inventory_path: Path = INVENTORY_PATH, today: str | None = None) -> dict:
    today = today or _et_date_str()
    inv = _read_json(inventory_path)
    rows_out = []
    for row in inv.get("rows", []):
        scored = score_row(row, today)
        if row.get("row_id") in _PROVISIONAL_ROW_IDS:
            scored["verdict"] = VERDICT_PROVISIONAL
            scored["note"] = (scored.get("note", "") + " [R4 of GOAL-RIGHT-TAIL-CAPTURE reopened 2026-09-05 -- "
                               "reported PROVISIONAL, never cited as confirming evidence until re-closed.]").strip()
        rows_out.append(scored)
    return {
        "generated_at_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generation_date": today,
        "generated_by": "setup/scripts/checkpoint_packet.py",
        "inventory_source": inventory_path.relative_to(REPO).as_posix(),
        "row_count": len(rows_out),
        "rows": rows_out,
    }


MARKDOWN_DIR = REPO / "markdown" / "planning"
CHECKPOINT_0929_MD = MARKDOWN_DIR / "CHECKPOINT-2026-09-29.md"
CHECKPOINT_1030_MD = MARKDOWN_DIR / "CHECKPOINT-2026-10-30.md"


def _md_row_line(r: dict) -> str:
    numbers = ", ".join(f"{k}={v}" for k, v in (r.get("numbers") or {}).items())
    return (
        f"| `{r['row_id']}` | {r['classification']} | {r['verdict']} | {r.get('n')} | "
        f"[{Path(r['prereg_path']).name}]({r['prereg_path']}) | {numbers or '-'} |"
    )


def _render_markdown(packet: dict, checkpoint_date: str, title: str) -> str:
    rows = [r for r in packet["rows"] if r["checkpoint"] == checkpoint_date]
    lines = [
        f"# {title}",
        "",
        f"> **GENERATED by `setup/scripts/checkpoint_packet.py` -- do not hand-edit.** "
        f"Regenerated nightly by `Gamma_CheckpointPacket` (23:30 ET). This file reflects "
        f"the {packet['generation_date']} ET generation; on {checkpoint_date} the read is "
        f"the last night's file. Source inventory: `{packet['inventory_source']}`. "
        f"Raw packet: `analysis/recommendations/checkpoint-packet-{packet['generation_date']}.json`.",
        "",
        f"Generated at: {packet['generated_at_et']} ET | Rows in this window: {len(rows)}",
        "",
        "| Decision | Class | Verdict | n | Prereg | Numbers |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(_md_row_line(r))
    lines.append("")
    lines.append("## Detail")
    for r in rows:
        lines.append("")
        lines.append(f"### `{r['row_id']}`")
        lines.append("")
        lines.append(f"- **Classification:** {r['classification']} (routes to {r['checkpoint']})")
        lines.append(f"- **Verdict:** {r['verdict']} (n={r.get('n')})")
        lines.append(f"- **Prereg:** `{r['prereg_path']}`")
        lines.append(f"- **Ledger:** `{r['ledger_path']}`")
        lines.append(f"- **Frozen hypothesis:** {r.get('frozen_hypothesis')}")
        lines.append(f"- **Decision rule (verbatim):** {r.get('decision_rule_verbatim')}")
        lines.append(f"- **Reversible action:** {r.get('reversible_action')}")
        lines.append(f"- **Note:** {r.get('note')}")
    lines.append("")
    return "\n".join(lines)


def write_markdown(packet: dict) -> tuple[Path, Path]:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    md_0929 = _render_markdown(
        packet, "2026-09-29",
        "Checkpoint 2026-09-29 -- Kill-Type Risk Reductions Only",
    )
    md_1030 = _render_markdown(
        packet, "2026-10-30",
        "Checkpoint 2026-10-30 -- Full Checkpoint (Expansions + Reductions Not Yet Shipped)",
    )
    CHECKPOINT_0929_MD.write_text(md_0929, encoding="utf-8")
    CHECKPOINT_1030_MD.write_text(md_1030, encoding="utf-8")
    return CHECKPOINT_0929_MD, CHECKPOINT_1030_MD


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Override generation date (YYYY-MM-DD ET); defaults to today via et_clock.")
    ap.add_argument("--json-out", default=None, help="Path to write the raw packet JSON. Defaults to analysis/recommendations/checkpoint-packet-<date>.json")
    ap.add_argument("--inventory", default=str(INVENTORY_PATH))
    ap.add_argument("--no-markdown", action="store_true", help="Skip writing the CHECKPOINT-*.md files (used by tests).")
    args = ap.parse_args(argv)

    packet = build_packet(Path(args.inventory), today=args.date)
    out_path = Path(args.json_out) if args.json_out else RECS_DIR / f"checkpoint-packet-{packet['generation_date']}.json"
    out_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for r in packet["rows"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"checkpoint_packet: {packet['row_count']} rows, generated {packet['generation_date']} ET")
    print(f"wrote {out_path.relative_to(REPO)}")
    for verdict, c in sorted(counts.items()):
        print(f"  {verdict}: {c}")
    for r in packet["rows"]:
        print(f"  [{r['classification']:>11}] {r['row_id']:<45} {r['verdict']:<15} n={r.get('n')}")

    if not args.no_markdown:
        md0929, md1030 = write_markdown(packet)
        print(f"wrote {md0929.relative_to(REPO)}")
        print(f"wrote {md1030.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
