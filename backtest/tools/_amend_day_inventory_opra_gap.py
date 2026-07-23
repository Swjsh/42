"""Honest, clearly-marked amendment to day-inventory-2026-07-23.json.

Does NOT re-derive day_type/gap_pct/vix_band/range_ratio for the 5 newly-filled
days (that requires the full inventory-builder's ATR20/VIX pipeline, which
this script does not reproduce) and does NOT touch heldout_days (frozen
last-25% boundary — recomputing it post-hoc after adding newer dates would
shift the OOS cutoff, a validation-integrity risk). It only flips has_opra /
n_opra_files for the 5 days this session actually fetched, appends them to
opra_days, updates counts.opra_days, and records a manual_amendments log
entry so the change is traceable and distinguishable from the original build.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "options"
INV_PATH = Path(__file__).resolve().parents[2] / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"

NEW_OPRA_DAYS = ["2026-07-15", "2026-07-16", "2026-07-20", "2026-07-21", "2026-07-22"]


def main() -> int:
    d = json.loads(INV_PATH.read_text(encoding="utf-8"))

    changed = []
    by_date = {row["date"]: row for row in d["days"]}
    for date in NEW_OPRA_DAYS:
        row = by_date.get(date)
        if row is None:
            print(f"WARN: {date} not in days[] — skipping")
            continue
        ymd = date[2:4] + date[5:7] + date[8:10]
        n_files = len(list(DATA.glob(f"SPY{ymd}*.csv")))
        before = (row.get("has_opra"), row.get("n_opra_files"))
        row["has_opra"] = True
        row["n_opra_files"] = n_files
        changed.append({"date": date, "before": {"has_opra": before[0], "n_opra_files": before[1]},
                         "after": {"has_opra": True, "n_opra_files": n_files}})

    opra_set = set(d["opra_days"])
    added_to_opra_days = [x["date"] for x in changed if x["date"] not in opra_set]
    d["opra_days"] = sorted(opra_set | {x["date"] for x in changed})

    d["counts"]["opra_days"] = len(d["opra_days"])

    d.setdefault("manual_amendments", []).append({
        "amended_by": "backtest/tools/_amend_day_inventory_opra_gap.py",
        "amended_for": "OPRA backfill mission 2026-07-22 (see analysis/edge-matrix/OPRA-BACKFILL-REPORT.md)",
        "what": "Flipped has_opra=true + n_opra_files for the 5 trading days that were missing "
                "real OPRA fills (2026-07-15, 07-16, 07-20, 07-21, 07-22) after fetching them via "
                "backtest/tools/_backfill_opra_recent_gap.py. Did NOT recompute day_type/gap_pct/"
                "vix_band/range_ratio for these rows (needs the original inventory-builder's "
                "ATR20+VIX pipeline, not reproduced here) and did NOT touch heldout_days (frozen "
                "last-25%-by-date boundary; recomputing it now would shift the OOS cutoff).",
        "days_changed": changed,
        "opra_days_added": added_to_opra_days,
        "opra_days_count_before": 381,
        "opra_days_count_after": len(d["opra_days"]),
    })

    INV_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print(f"Amended {INV_PATH}")
    print(f"opra_days: 381 -> {len(d['opra_days'])}")
    for c in changed:
        print(" ", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
