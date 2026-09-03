"""Independent read-only reproduction of fleet-gates-designation-accuracy.md's Sec4c
day-level leak-dependency check. New file per task constraints (scratch tool). No writes
to any tracked state, no network. Verifies:
  - the 133-tick / 12-date leak-eligible-tick count since 2026-08-06
  - per-date safe-3 ENTER-type decision counts split leak vs non-leak
  - whether any date's safe-3 entries were leak-only
"""
import json
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
SAFE3_DECISIONS = REPO / "automation" / "state" / "fleet" / "safe-3" / "decisions.jsonl"

SINCE_DATE = "2026-08-06"


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def main():
    core_rows = load_jsonl(CORE_DECISIONS)
    # group core rows by core_tick_id (only rows that carry the field)
    by_tick = defaultdict(dict)  # tick_id -> {account: verdict}
    tick_date = {}
    for r in core_rows:
        ct = r.get("core_tick_id")
        if not ct:
            continue
        date = ct[:10]
        if date < SINCE_DATE:
            continue
        acct = r.get("account")
        if acct not in ("safe", "bold"):
            continue
        # CORRECTED per sibling ledger-binding-check.md's documented method: "gated" =
        # that account's ACTION field starts with SKIP_ (execution-time outcome);
        # "read ENTER" = the OTHER account's VERDICT field (score-time read, what
        # _bold_passed_blocks_from_row keys off). action and verdict diverge on 943/16030
        # rows since 2026-08-06 (verified) -- using verdict for both sides (first pass of
        # this script) undercounts to 116 ticks/11 dates instead of the correct 133/12.
        by_tick[ct][acct] = {"action": r.get("action"), "verdict": r.get("verdict")}
        tick_date[ct] = date

    leak_ticks = set()
    for ct, accts in by_tick.items():
        safe_row = accts.get("safe") or {}
        bold_row = accts.get("bold") or {}
        safe_action = str(safe_row.get("action") or "")
        bold_verdict = str(bold_row.get("verdict") or "")
        if safe_action.startswith("SKIP") and bold_verdict.startswith("ENTER"):
            leak_ticks.add(ct)

    leak_dates = sorted({tick_date[ct] for ct in leak_ticks})
    print(f"leak-eligible ticks: {len(leak_ticks)}")
    print(f"distinct leak dates: {len(leak_dates)}")
    print("dates:", leak_dates)

    # safe-3 decisions: ENTER-type actions
    safe3_rows = load_jsonl(SAFE3_DECISIONS)
    ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}

    per_date = defaultdict(lambda: {"total": 0, "leak": 0, "nonleak": 0})
    for r in safe3_rows:
        action = r.get("action")
        if action not in ENTER_ACTIONS:
            continue
        ct = r.get("core_tick_id")
        ts = r.get("ts_et", "")
        date = (ct[:10] if ct else ts[:10])
        if date < SINCE_DATE:
            continue
        per_date[date]["total"] += 1
        if ct in leak_ticks:
            per_date[date]["leak"] += 1
        else:
            per_date[date]["nonleak"] += 1

    print()
    print("Per-date safe-3 ENTER-type decisions (dates with leak ticks only, per report scope):")
    leak_only_dates = []
    for d in leak_dates:
        stats = per_date.get(d, {"total": 0, "leak": 0, "nonleak": 0})
        print(f"{d}: {stats['total']} entries total | {stats['leak']} via leak | {stats['nonleak']} non-leak")
        if stats["total"] > 0 and stats["nonleak"] == 0:
            leak_only_dates.append(d)

    print()
    print(f"Dates where safe-3's ONLY entry that day came via a leak tick: {len(leak_only_dates)} of {len(leak_dates)}")
    print("leak-only dates:", leak_only_dates)

    # also show full per-date table (any date, not just leak dates) for sanity on total ENTER count
    print()
    print(f"Total distinct dates with ANY safe-3 ENTER-type decision since {SINCE_DATE}: {len([d for d in per_date if per_date[d]['total']>0])}")


if __name__ == "__main__":
    main()
