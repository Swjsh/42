"""Read-only independent reproduction of fleet-gates-designation-accuracy.md sec 4c
(day-level leak-dependency check) plus the CONSEQUENCE-lens stress test: remove the
top-3 leak-heaviest dates and recompute whether the "0 of 12 sole-source" claim survives.

No writes. <5s runtime. Verification script for a skeptic review, not a trading-path file.
"""
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation/state/core-decisions.jsonl"
SAFE3_DECISIONS = REPO / "automation/state/fleet/safe-3/decisions.jsonl"

SINCE = "2026-08-06"

def load_jsonl(p):
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out

def main():
    core = load_jsonl(CORE_DECISIONS)
    # index by core_tick_id -> {account: row}
    by_tick = defaultdict(dict)
    for r in core:
        ctid = r.get("core_tick_id")
        acct = r.get("account")
        if ctid is None or acct not in ("safe", "bold"):
            continue
        ts = r.get("ts_et", "")
        if ts < SINCE:
            continue
        by_tick[ctid][acct] = r

    # leak ticks: safe action starts with SKIP_, bold verdict ENTER_BULL or ENTER_BEAR
    leak_ticks = {}
    for ctid, accts in by_tick.items():
        s = accts.get("safe")
        b = accts.get("bold")
        if not s or not b:
            continue
        s_action = str(s.get("action") or "")
        b_verdict = str(b.get("verdict") or "")
        if s_action.startswith("SKIP_") and b_verdict in ("ENTER_BULL", "ENTER_BEAR"):
            leak_ticks[ctid] = {"date": ctid[:10], "safe_action": s_action, "bold_verdict": b_verdict}

    distinct_leak_dates = sorted({v["date"] for v in leak_ticks.values()})
    print(f"total_leak_ticks={len(leak_ticks)} distinct_leak_dates={len(distinct_leak_dates)}")
    print("dates:", distinct_leak_dates)

    # safe-3 own decisions: ENTER-type actions
    s3 = load_jsonl(SAFE3_DECISIONS)
    ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}
    per_date = defaultdict(lambda: {"total": 0, "via_leak": 0, "non_leak": 0, "leak_tick_ids": [], "non_leak_tick_ids": []})
    for r in s3:
        action = str(r.get("action") or "")
        if action not in ENTER_ACTIONS:
            continue
        ctid = r.get("core_tick_id")
        date = (ctid or r.get("ts_et", ""))[:10]
        d = per_date[date]
        d["total"] += 1
        if ctid in leak_ticks:
            d["via_leak"] += 1
            d["leak_tick_ids"].append(ctid)
        else:
            d["non_leak"] += 1
            d["non_leak_tick_ids"].append(ctid)

    # restrict to dates that are in distinct_leak_dates (leak-eligible dates) union dates w/ entries
    print("\n--- per-date breakdown (all dates with safe-3 ENTER-type decisions, since", SINCE, ") ---")
    all_relevant_dates = sorted(set(per_date.keys()) | set(distinct_leak_dates))
    sole_source_dates = []
    for date in all_relevant_dates:
        d = per_date.get(date, {"total": 0, "via_leak": 0, "non_leak": 0})
        is_leak_date = date in distinct_leak_dates
        sole = is_leak_date and d["total"] > 0 and d["via_leak"] == d["total"]
        if sole:
            sole_source_dates.append(date)
        flag = " <== SOLE-SOURCE-VIA-LEAK" if sole else ""
        print(f"{date}: total={d['total']} via_leak={d['via_leak']} non_leak={d['non_leak']} leak_eligible={is_leak_date}{flag}")

    print(f"\ndates_where_leak_was_sole_source: {sole_source_dates} (count={len(sole_source_dates)} of {len(distinct_leak_dates)} leak-eligible dates)")

    # CONSEQUENCE LENS: remove top-3 leak-heaviest dates (by via_leak count) and recompute
    leak_date_rows = [(date, per_date.get(date, {"via_leak": 0})["via_leak"]) for date in distinct_leak_dates]
    leak_date_rows.sort(key=lambda x: -x[1])
    top3 = [d for d, _ in leak_date_rows[:3]]
    print(f"\n--- CONSEQUENCE LENS: top-3 leak-heaviest dates by via_leak count = {leak_date_rows[:3]} ---")
    remaining_dates = [d for d in distinct_leak_dates if d not in top3]
    remaining_sole_source = []
    for date in remaining_dates:
        d = per_date.get(date, {"total": 0, "via_leak": 0})
        if d["total"] > 0 and d["via_leak"] == d["total"]:
            remaining_sole_source.append(date)
    print(f"after removing top-3 dates ({top3}): {len(remaining_dates)} leak-eligible dates remain, sole-source count = {len(remaining_sole_source)}")
    print(f"conclusion (0-of-N sole-source) survives without top-3: {len(remaining_sole_source) == 0}")

if __name__ == "__main__":
    main()
