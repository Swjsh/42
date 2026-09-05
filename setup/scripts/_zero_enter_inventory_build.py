"""One-off builder for analysis/zero-enter/ZERO-ENTER-INVENTORY-2026-09-03.json (Z1).

Read-only. Reuses conductor_outcome._grade_zero_enter_day (AUTONOMY-METRIC-
ZERO-ENTERS-08-31) -- does not reimplement grading. Cross-checks each
candidate day against journal/calendar-data.json (fleet fill-day record) and
core-decisions.jsonl's own per-day tick count (a day with >0 RTH ticks in the
core ledger is a real trading day even if calendar-data.json -- which is
generated from FLEET-ARM fills, not core-account ticks, and was last
regenerated 2026-09-03 -- has no fill row for it).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import conductor_outcome as co  # noqa: E402

WINDOW_START = "2026-08-31"
OUT = REPO / "analysis" / "zero-enter" / "ZERO-ENTER-INVENTORY-2026-09-03.json"


def main() -> int:
    rows = list(co._iter_jsonl_reversed(co.DECISIONS_FILE))
    all_days = sorted({str(r.get("date", "") or "") for r in rows if r.get("date")})
    window_days = [d for d in all_days if d >= WINDOW_START]

    cal = {}
    cal_path = REPO / "analysis" / "journal" / "calendar-data.json"
    try:
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        cal = {}
    fleet_fill_days = set()
    try:
        fleet_fill_days = set(cal.get("views", {}).get("BOOK", {}).get("days", {}).keys())
    except AttributeError:
        pass
    cal_generated = cal.get("generated_et", "") if isinstance(cal, dict) else ""

    entries = []
    for d in window_days:
        n_ticks = sum(1 for r in rows if str(r.get("date", "")) == d)
        grade = co._grade_zero_enter_day(d)
        grade_str = grade["grade"] if grade else None
        included = grade_str in ("SAT_OUT_GATED", "regressing")
        entries.append({
            "trading_day": d,
            "core_rth_ticks": n_ticks,
            "grade": grade_str,
            "high_score_ticks": (grade or {}).get("high_score_ticks"),
            "reason": (grade or {}).get("reason"),
            "included_in_zero_enter_scope": included,
            "cross_check": {
                "in_fleet_calendar_fill_days": d in fleet_fill_days,
                "calendar_generated_et": cal_generated,
                "trading_day_confirmed_by": (
                    "fleet calendar fill-day record" if d in fleet_fill_days
                    else f"core-decisions.jsonl has {n_ticks} RTH ticks for this date "
                         f"(calendar-data.json last generated {cal_generated}, may predate "
                         f"this day's fleet-fill regeneration)"
                ),
            },
        })

    inventory = {
        "_doc": "Z1 -- inventory of every frozen-window (2026-08-31 onward) trading day "
                "graded SAT_OUT_GATED or regressing by conductor_outcome._grade_zero_enter_day "
                "(reused unmodified, not reimplemented). QUIET/None-graded days are listed for "
                "visibility but excluded from zero-enter scope per the goal's own definition.",
        "window_start": WINDOW_START,
        "generated_by": "setup/scripts/_zero_enter_inventory_build.py",
        "score_threshold": co.ZERO_ENTER_SCORE_THRESHOLD,
        "min_rth_ticks": co.ZERO_ENTER_MIN_RTH_TICKS,
        "days": entries,
        "in_scope_days": [e["trading_day"] for e in entries if e["included_in_zero_enter_scope"]],
        "in_scope_count": sum(1 for e in entries if e["included_in_zero_enter_scope"]),
        "known_case_2026_09_02_present": any(
            e["trading_day"] == "2026-09-02" and e["included_in_zero_enter_scope"]
            for e in entries
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"wrote {OUT} -- {inventory['in_scope_count']} in-scope days: {inventory['in_scope_days']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
