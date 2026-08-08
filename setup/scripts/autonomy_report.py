"""autonomy_report.py -- honest "did Gamma drive today/this week" scorecard (LANE C, 2026-08-08).

WHY THIS EXISTS (tonight's audit, verified with live evidence):
Gamma_Conductor is the ONLY scheduled loop that can change the rig unattended. Its STAGE-0
budget gate (conductor_budget.py, $30/day cap w/ a 2.16x self-report correction -- re-measured
2026-08-08 from 2.2x, see conductor_budget.py's own SELF_REPORT_CORRECTION constant and
analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md) got exhausted
inside the first ~2h of the ET day on 2026-08-08 (raw $16.05 x2.2 = $35.31 by ~02:07 ET -- the
2.2x constant that was LIVE at the moment of this actual incident, kept here as an accurate
historical quote; the constant has since been corrected, see above), and
every conductor-family fire since has been a pure no-op -- 6+ consecutive QUIET/EXHAUSTED rows
in automation/state/conductor-outcomes.jsonl with items_drained=0 through 20:00 UTC. Nothing
today surfaced that plainly. This script is the instrument: it reads the SAME outcomes ledger
conductor_budget.py already writes and turns it into an honest verdict -- never flattering,
never vague, never silent when the day was fully starved (that silence is itself the failure
mode this closes, per OP-25(c) "silent failure is the only true failure").

DEFINITIONS (explicit, per the build spec -- these are the ONLY definitions this script uses):
  - SHIP event: a conductor-family fire row with items_drained > 0 OR lessons_shipped > 0.
  - No-op fire: everything else, classified by WHY from the row's task_id/note text:
      budget_exhausted -> "budget" appears anywhere in task_id/note (covers every QUIET-*/
                           BUDGET-GATE-*/rail0-budget-exhausted-* row seen in the real ledger)
      error             -> "traceback"/"exception"/"error"/"crash" (checked AFTER budget, so
                           an exhausted-budget row is never double-counted as an error even if
                           its note happens to also say "error code")
      nothing_ready     -> "nothing ready"/"no items"/"no work"/"queue empty"/"idle"
      other             -> doesn't match any of the above (fail-open bucket, never invented)

OUTPUT: automation/state/autonomy-report.json (atomic tmp+replace, same pattern as
gamma_standup.write_latest). Fields: computed_at, today{date,total_fires,ship_fires,
noop_fires,noop_reasons,ship_task_ids,verdict}, week{start_date,end_date,...same shape...,
verdict}, budget_shape{spend_by_hour_et,daily_cap_usd,max_fires_per_day_cap,slots_used_today,
slots_available_today}, autonomy_metric (passthrough of autonomy-metric.json, or None),
verdict (== today's verdict -- the single line gamma_standup.py's AUTONOMY line sources from).

Zero cost, deterministic, pure Python -- no LLM, no broker, no network. Every reader is
FAIL-OPEN: a missing/garbled source file degrades that one section to empty/None, never a
crash (C7) -- but the day's own verdict line ALWAYS renders something honest, even "0 of 0
fires recorded" -- never blank (that was itself a named requirement).

CLI:
  python setup/scripts/autonomy_report.py            # compute + write + print
  python setup/scripts/autonomy_report.py --dry-run  # compute + print only, no disk write
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"

OUTCOMES_PATH = STATE / "conductor-outcomes.jsonl"
METRIC_PATH = STATE / "autonomy-metric.json"
BUDGET_CONFIG_PATH = STATE / "conductor-budget.json"
OUTPUT_PATH = STATE / "autonomy-report.json"

WEEK_DAYS = 7

# Mirrors conductor_budget.py's DEFAULTS -- used only when conductor-budget.json is
# missing/garbled, so the budget_shape section still renders something honest rather
# than a crash or a silently-wrong 0.
_BUDGET_DEFAULTS = {"daily_cap_usd": 30.0, "max_fires": 4, "enabled": True}


# --------------------------------------------------------------------------- #
# Fail-open readers -- never raise, degrade to empty/None (C7).
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def load_outcomes(path: Path = OUTCOMES_PATH) -> list[dict]:
    """Reads conductor-outcomes.jsonl. Skips any malformed line individually rather
    than failing the whole read -- one corrupted row must never blind the report to
    every other row. Missing file -> []."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_budget_config(path: Path = BUDGET_CONFIG_PATH) -> dict:
    cfg = dict(_BUDGET_DEFAULTS)
    doc = _read_json(path)
    if doc:
        for k in _BUDGET_DEFAULTS:
            if k in doc:
                cfg[k] = doc[k]
    return cfg


# --------------------------------------------------------------------------- #
# Time seam -- the ONE place "now" is read, so tests monkeypatch this instead
# of touching the real clock (same discipline as gamma_standup's git-log seam).
# --------------------------------------------------------------------------- #

def _current_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_fired_at_et(ts) -> Optional[datetime]:
    """fired_at (UTC ISO string) -> naive ET datetime, or None on ANY parse failure
    (missing key, non-string, malformed ISO). Fail-open -- a row with a garbled
    timestamp is simply excluded from date-bucketed sections, never crashes."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return et_now(dt.astimezone(timezone.utc))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Ship-event / no-op classification -- the two load-bearing definitions.
# --------------------------------------------------------------------------- #

def is_ship_event(row: dict) -> bool:
    """A conductor-family fire that actually moved something: items_drained>0
    OR lessons_shipped>0. Anything else (including a fire that merely spent
    money without draining/shipping) is a no-op, however busy its note reads."""
    for key in ("items_drained", "lessons_shipped"):
        val = row.get(key)
        try:
            if val is not None and float(val) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


_ERROR_MARKERS = ("traceback", "exception", "error", "crash")
_NOTHING_READY_MARKERS = ("nothing ready", "no items", "no work", "queue empty", "idle")


def classify_noop_reason(row: dict) -> str:
    """WHY a no-op fire did nothing, from its task_id + note text. Checked in a
    fixed priority order (budget first) so a budget-exhausted row whose note
    happens to also mention "error code 3" is still correctly bucketed as
    budget, not error -- budget IS the reason, the exit code is a side detail."""
    text = " ".join(str(row.get(k, "")) for k in ("task_id", "note")).lower()
    if "budget" in text:
        return "budget_exhausted"
    if any(m in text for m in _ERROR_MARKERS):
        return "error"
    if any(m in text for m in _NOTHING_READY_MARKERS):
        return "nothing_ready"
    return "other"


NOOP_REASON_KEYS = ("budget_exhausted", "nothing_ready", "error", "other")


# --------------------------------------------------------------------------- #
# Date bucketing -- ET calendar date per row, day/week row selection.
# --------------------------------------------------------------------------- #

def _row_et_date(row: dict) -> Optional[str]:
    et_dt = _parse_fired_at_et(row.get("fired_at"))
    return et_dt.strftime("%Y-%m-%d") if et_dt else None


def rows_on_date(rows: list[dict], day: str) -> list[dict]:
    return [r for r in rows if _row_et_date(r) == day]


def rows_in_week(rows: list[dict], end_day: str, n_days: int = WEEK_DAYS) -> list[dict]:
    """Trailing n_days ET calendar days, INCLUSIVE of end_day (e.g. n_days=7,
    end_day=Fri -> Sat..Fri)."""
    end = date.fromisoformat(end_day)
    start = end - timedelta(days=n_days - 1)
    out = []
    for r in rows:
        d = _row_et_date(r)
        if d is None:
            continue
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if start <= dd <= end:
            out.append(r)
    return out


# --------------------------------------------------------------------------- #
# Summary + verdict -- shared by both the "today" and "week" sections.
# --------------------------------------------------------------------------- #

def build_verdict(summary: dict, scope_label: str) -> str:
    total = summary["total_fires"]
    ship = summary["ship_fires"]
    starved = summary["noop_reasons"]["budget_exhausted"]
    if total == 0:
        return f"No conductor fires recorded {scope_label} -- nothing to report."
    slot = "slot" if total == 1 else "slots"
    verdict = f"Drove {ship} of {total} fire {slot} {scope_label}"
    if starved > 0:
        verdict += f"; {starved} were budget-starved"
    return verdict + "."


def summarize_rows(rows: list[dict]) -> dict:
    ship_rows = [r for r in rows if is_ship_event(r)]
    noop_rows = [r for r in rows if not is_ship_event(r)]
    reasons = Counter(classify_noop_reason(r) for r in noop_rows)
    return {
        "total_fires": len(rows),
        "ship_fires": len(ship_rows),
        "noop_fires": len(noop_rows),
        "noop_reasons": {k: reasons.get(k, 0) for k in NOOP_REASON_KEYS},
        "ship_task_ids": [r.get("task_id") for r in ship_rows if r.get("task_id")],
    }


# --------------------------------------------------------------------------- #
# Budget utilization shape -- spend by ET hour-of-day + slots used/available.
# --------------------------------------------------------------------------- #

def spend_by_hour_et(rows: list[dict]) -> dict:
    """{'HH': total_cost_usd} for every ET hour that had at least one fire, sorted
    by hour. Non-numeric/missing cost_usd contributes 0 rather than dropping the
    row from the hour bucket (a fire still happened at that hour)."""
    totals: dict = {}
    for r in rows:
        et_dt = _parse_fired_at_et(r.get("fired_at"))
        if et_dt is None:
            continue
        hh = f"{et_dt.hour:02d}"
        try:
            cost = float(r.get("cost_usd") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        totals[hh] = totals.get(hh, 0.0) + cost
    return {hh: round(v, 2) for hh, v in sorted(totals.items())}


def build_budget_shape(rows_today: list[dict], budget_cfg: dict, total_fires_today: int) -> dict:
    """slots_used_today / slots_available_today report budget-SLOT consumption -- i.e. they must
    match conductor_budget.py's own accounting, which counts EVERY conductor-family fire (shipped
    or not) against max_fires (see conductor_budget.check(): `s["fires"] >= cfg["max_fires"]`).

    CORRECTED 2026-08-08 (audit finding, confirmed): this previously took `ship_fires_today` (a
    ship COUNT) under a field literally named for slot consumption, and echoed `max_fires`
    verbatim as "available" regardless of how many fires had actually landed. Live evidence on
    the fixture that motivated this fix: 2026-08-08 had 11 total conductor-family fires against
    max_fires=4 (2.75x over) but only 3 ship events -- the old code reported
    {"slots_used_today": 3, "slots_available_today": 4}, i.e. "1 of 4 slots still open," when the
    day was in fact fully exhausted nearly 3x over. A reader trusting the field NAME (not its
    mislabeled content) would draw the opposite conclusion from reality. Fixed by keying off
    total_fires_today (every fire counts against the cap, ship or no-op) and by actually
    subtracting from max_fires instead of echoing it -- clamped at 0 (a day can go arbitrarily
    over cap, but "slots available" cannot go negative)."""
    max_fires = budget_cfg.get("max_fires")
    slots_available = None
    if isinstance(max_fires, (int, float)):
        slots_available = max(int(max_fires) - int(total_fires_today), 0)
    return {
        "spend_by_hour_et": spend_by_hour_et(rows_today),
        "daily_cap_usd": budget_cfg.get("daily_cap_usd"),
        "max_fires_per_day_cap": max_fires,
        "slots_used_today": total_fires_today,
        "slots_available_today": slots_available,
    }


# --------------------------------------------------------------------------- #
# Full report assembly.
# --------------------------------------------------------------------------- #

def compute_report(rows: list[dict], metric_doc: Optional[dict], budget_cfg: dict, as_of_day: str) -> dict:
    today_rows = rows_on_date(rows, as_of_day)
    week_rows = rows_in_week(rows, as_of_day)
    week_start = (date.fromisoformat(as_of_day) - timedelta(days=WEEK_DAYS - 1)).isoformat()

    today_summary = summarize_rows(today_rows)
    today_summary["date"] = as_of_day
    today_summary["verdict"] = build_verdict(today_summary, "today")

    week_summary = summarize_rows(week_rows)
    week_summary["start_date"] = week_start
    week_summary["end_date"] = as_of_day
    week_summary["verdict"] = build_verdict(week_summary, "this week")

    return {
        "computed_at": _current_utc().isoformat(timespec="seconds"),
        "today": today_summary,
        "week": week_summary,
        "budget_shape": build_budget_shape(today_rows, budget_cfg, today_summary["total_fires"]),
        "autonomy_metric": metric_doc,
        "verdict": today_summary["verdict"],
    }


def write_report(payload: dict, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Honest today/this-week autonomy scorecard.")
    ap.add_argument("--dry-run", action="store_true", help="compute + print only, no disk write")
    args = ap.parse_args(argv)

    as_of_day = et_now(_current_utc()).strftime("%Y-%m-%d")
    rows = load_outcomes(OUTCOMES_PATH)
    metric_doc = _read_json(METRIC_PATH)
    budget_cfg = load_budget_config(BUDGET_CONFIG_PATH)

    report = compute_report(rows, metric_doc, budget_cfg, as_of_day)

    print(f"[autonomy_report] {as_of_day}")
    print(report["verdict"])
    print(f"  today:  {report['today']['ship_fires']}/{report['today']['total_fires']} ship, "
          f"noop_reasons={report['today']['noop_reasons']}")
    print(f"  week:   {report['week']['ship_fires']}/{report['week']['total_fires']} ship "
          f"({report['week']['start_date']}..{report['week']['end_date']})")
    print(f"  {report['week']['verdict']}")
    if metric_doc is None:
        print("  autonomy-metric.json: MISSING -- section omitted (fail-open)")
    else:
        print(f"  standing trend: {metric_doc.get('trend')} "
              f"(net_improvement={metric_doc.get('net_improvement')}, "
              f"total_cost_usd={metric_doc.get('total_cost_usd')})")

    if args.dry_run:
        print("\n[autonomy_report] --dry-run: NOT written to disk")
        return 0

    try:
        write_report(report, OUTPUT_PATH)
    except OSError as exc:
        print(f"[autonomy_report] WRITE FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"\n[autonomy_report] wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
