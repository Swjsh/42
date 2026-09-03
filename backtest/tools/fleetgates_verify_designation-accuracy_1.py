"""
Independent re-verification script for finding G4-DESIGNATION-ACCURACY.
Read-only. Rebuilds core_tick_id -> safe-3 decisions join from scratch,
independent of backtest/tools/fleetgates_ledger-binding-check.py.

No writes to any file. < 5s runtime.
"""
import json
import collections
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
SAFE3_DECISIONS = REPO / "automation" / "state" / "fleet" / "safe-3" / "decisions.jsonl"

WINDOW_START = "2026-08-06"  # matches sibling report's stated join start


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main():
    core_rows = load_jsonl(CORE_DECISIONS)
    # Split by account, keep only rows with a non-null core_tick_id and date >= WINDOW_START
    safe_rows = {}
    bold_rows = {}
    for r in core_rows:
        ctid = r.get("core_tick_id")
        if not ctid:
            continue
        if ctid[:10] < WINDOW_START:
            continue
        acct = r.get("account")
        if acct == "safe":
            safe_rows[ctid] = r
        elif acct == "bold":
            bold_rows[ctid] = r

    print(f"safe rows w/ core_tick_id >= {WINDOW_START}: {len(safe_rows)}")
    print(f"bold rows w/ core_tick_id >= {WINDOW_START}: {len(bold_rows)}")

    paired = set(safe_rows) & set(bold_rows)
    print(f"paired ticks (both safe+bold present): {len(paired)}")

    # "Gated" = safe's action starts with SKIP_. "Bold read ENTER" = bold's verdict startswith ENTER_
    leak_eligible_ticks = {}  # core_tick_id -> (safe_action, date)
    gate_counter = collections.Counter()
    for ctid in paired:
        srow = safe_rows[ctid]
        brow = bold_rows[ctid]
        s_action = srow.get("action") or ""
        b_verdict = brow.get("verdict") or ""
        if s_action.startswith("SKIP_") and b_verdict.startswith("ENTER_"):
            leak_eligible_ticks[ctid] = (s_action, ctid[:10])
            gate_counter[s_action] += 1

    n_ticks = len(leak_eligible_ticks)
    dates_with_leak = sorted({d for (_, d) in leak_eligible_ticks.values()})
    print(f"\nleak-eligible ticks (safe SKIP_*, bold ENTER_* same tick): {n_ticks}")
    print(f"distinct dates carrying >=1 leak-eligible tick: {len(dates_with_leak)}")
    print("gate breakdown (safe action):")
    for k, v in gate_counter.most_common():
        print(f"  {k}: {v}")
    print("dates:", dates_with_leak)

    # Now join safe-3's own decisions.jsonl on core_tick_id.
    safe3_rows = load_jsonl(SAFE3_DECISIONS)
    safe3_by_tick = collections.defaultdict(list)
    for r in safe3_rows:
        ctid = r.get("core_tick_id")
        if not ctid:
            continue
        safe3_by_tick[ctid].append(r)

    ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}

    # Per-date breakdown of safe-3 ENTER-type decisions: via-leak-tick vs non-leak
    per_date = collections.defaultdict(lambda: {"total": 0, "via_leak": 0, "non_leak": 0, "tick_ids": []})

    # For each safe-3 decision row that is an ENTER-type, is its core_tick_id a leak-eligible tick?
    all_safe3_enter_dates_in_window = set()
    for r in safe3_rows:
        ctid = r.get("core_tick_id")
        if not ctid:
            continue
        date = ctid[:10]
        if date < WINDOW_START:
            continue
        action = r.get("action") or ""
        if action not in ENTER_ACTIONS:
            continue
        all_safe3_enter_dates_in_window.add(date)
        per_date[date]["total"] += 1
        if ctid in leak_eligible_ticks:
            per_date[date]["via_leak"] += 1
        else:
            per_date[date]["non_leak"] += 1

    print("\n--- per-date safe-3 ENTER-type decisions, since", WINDOW_START, "---")
    only_leak_dates = []
    for date in sorted(dates_with_leak):
        d = per_date.get(date, {"total": 0, "via_leak": 0, "non_leak": 0})
        print(f"{date}: total={d['total']} via_leak={d['via_leak']} non_leak={d['non_leak']}")
        if d["total"] > 0 and d["non_leak"] == 0:
            only_leak_dates.append(date)

    print(f"\nDates (of the {len(dates_with_leak)} leak-eligible dates) where safe-3's "
          f"ONLY entry that day came via a leak tick: {len(only_leak_dates)} -> {only_leak_dates}")

    # Aggregate leak rate for safe-3 (Table A equivalent: safe gated, bold entered)
    entered_on_leak_tick = 0
    for ctid in leak_eligible_ticks:
        rows = safe3_by_tick.get(ctid, [])
        if any((rr.get("action") in ENTER_ACTIONS) for rr in rows):
            entered_on_leak_tick += 1
    print(f"\nTable-A style aggregate: safe-3 entered on {entered_on_leak_tick}/{n_ticks} "
          f"leak-eligible ticks ({entered_on_leak_tick/n_ticks*100:.1f}%)" if n_ticks else "n=0")

    # Sanity: also check September-only sub-window
    sept_dates = [d for d in dates_with_leak if d >= "2026-09-01"]
    print(f"\nSeptember-only (>=2026-09-01) leak-eligible dates: {sept_dates}")

    # Named winning days check
    named_days = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
    overlap = named_days & set(dates_with_leak)
    print(f"Named winning days overlapping leak-eligible dates: {sorted(overlap)}")

    out = {
        "window_start": WINDOW_START,
        "paired_ticks": len(paired),
        "leak_eligible_ticks": n_ticks,
        "leak_eligible_dates": dates_with_leak,
        "gate_breakdown": dict(gate_counter),
        "per_date": {k: v for k, v in per_date.items() if k in dates_with_leak},
        "only_leak_dates": only_leak_dates,
        "safe3_entered_on_leak_tick": entered_on_leak_tick,
        "named_winning_days_overlap": sorted(overlap),
    }
    out_path = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "verify-fleet-gates-designation-accuracy-1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
