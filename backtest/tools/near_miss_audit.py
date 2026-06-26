"""Audit near-miss ticks in decisions.jsonl to identify primary filter blockers.

A near-miss tick = bear_score>=8 OR bull_score>=9 AND action in {HOLD, HOLD_DEV}
This tells us which filters are costing the most potential entries.

SECURITY: Read-only on all production state files. No writes to decisions.jsonl.
Writes analysis to analysis/recommendations/near-miss-audit.json only.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path(__file__).resolve().parents[1]
REPO_ROOT = REPO.parent
DECISIONS = REPO_ROOT / "automation" / "state" / "decisions.jsonl"
# Also check aggressive account
DECISIONS_AGG = REPO_ROOT / "automation" / "state" / "aggressive" / "decisions.jsonl"
OUT = REPO_ROOT / "analysis" / "recommendations"
OUT.mkdir(parents=True, exist_ok=True)

NEAR_MISS_BEAR = 8
NEAR_MISS_BULL = 9
HOLD_ACTIONS = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}


def load_decisions(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    rows.append(parsed)
            except json.JSONDecodeError:
                pass
    return rows


def extract_blocked_filters(row: dict) -> list[int]:
    """Extract which filters blocked entry from filter_state or reason field."""
    blocked = []

    # Primary: filter_state field
    fs = row.get("filter_state", {})
    side = row.get("side", "")
    if not side:
        if _score(row, "bear_score") >= NEAR_MISS_BEAR:
            side = "bear"
        elif _score(row, "bull_score") >= NEAR_MISS_BULL:
            side = "bull"

    if fs:
        key = f"{side}_blocked"
        if key in fs:
            blocked = fs[key]
        elif "blocked" in fs:
            blocked = fs["blocked"]

    # Fallback: parse reason field for filter numbers
    if not blocked:
        reason = row.get("reason", "")
        # Look for patterns like "filter_6", "f6", "filter6" in reason text
        nums = re.findall(r'filter[_\s]?(\d+)', reason, re.I)
        blocked = [int(n) for n in nums]

    return blocked


def _score(row: dict, key: str) -> int:
    v = row.get(key, 0)
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def is_near_miss(row: dict) -> bool:
    action = row.get("action", row.get("decision", ""))
    if action not in HOLD_ACTIONS:
        return False
    bear = _score(row, "bear_score")
    bull = _score(row, "bull_score")
    return bear >= NEAR_MISS_BEAR or bull >= NEAR_MISS_BULL


def analyse(rows: list[dict], label: str) -> dict:
    near_misses = [r for r in rows if is_near_miss(r)]
    total = len(near_misses)
    if total == 0:
        return {"label": label, "total_near_misses": 0}

    bear_nm = [r for r in near_misses if _score(r, "bear_score") >= NEAR_MISS_BEAR]
    bull_nm = [r for r in near_misses if _score(r, "bull_score") >= NEAR_MISS_BULL]

    # Tally primary blockers
    filter_counts: Counter = Counter()
    no_filter_state = 0
    for r in near_misses:
        blocked = extract_blocked_filters(r)
        if blocked:
            # Primary blocker = first in list (or most-common if unordered)
            for f in blocked:
                filter_counts[f] += 1
        else:
            no_filter_state += 1

    primary_by_freq = filter_counts.most_common(10)

    # Date distribution
    dates = Counter(str(r.get("date", ""))[:10] for r in near_misses)

    # Bear vs bull breakdown by filter
    side_by_filter: dict[int, dict] = defaultdict(lambda: {"bear": 0, "bull": 0})
    for r in near_misses:
        blocked = extract_blocked_filters(r)
        s = "bear" if _score(r, "bear_score") >= NEAR_MISS_BEAR else "bull"
        for f in blocked:
            side_by_filter[f][s] += 1

    return {
        "label": label,
        "total_near_misses": total,
        "bear_near_misses": len(bear_nm),
        "bull_near_misses": len(bull_nm),
        "no_filter_state_rows": no_filter_state,
        "filter_block_counts": dict(primary_by_freq),
        "filter_side_breakdown": {str(k): v for k, v in side_by_filter.items()},
        "pct_by_filter": {
            str(f): round(100 * c / total, 1)
            for f, c in primary_by_freq
        },
        "unique_dates": len(dates),
        "date_distribution": dict(sorted(dates.items())),
    }


def main():
    rows_safe = load_decisions(DECISIONS)
    rows_agg = load_decisions(DECISIONS_AGG)

    print(f"Safe decisions: {len(rows_safe)} rows")
    print(f"Agg decisions: {len(rows_agg)} rows")

    result = {
        "safe": analyse(rows_safe, "safe"),
        "aggressive": analyse(rows_agg, "aggressive"),
    }

    out = OUT / "near-miss-audit.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote: {out}")

    for label, r in result.items():
        nm = r.get("total_near_misses", 0)
        if nm == 0:
            print(f"\n[{label}] No near-misses found")
            continue
        print(f"\n[{label}] {nm} near-misses ({r.get('unique_dates',0)} dates)")
        print(f"  Bear: {r.get('bear_near_misses',0)}  Bull: {r.get('bull_near_misses',0)}")
        print(f"  No filter_state: {r.get('no_filter_state_rows',0)}")
        print("  Filter block %:")
        for f_str, pct in r.get("pct_by_filter", {}).items():
            side_info = r.get("filter_side_breakdown", {}).get(f_str, {})
            bear_c = side_info.get("bear", 0)
            bull_c = side_info.get("bull", 0)
            print(f"    filter_{f_str}: {pct}%  (bear={bear_c}, bull={bull_c})")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
