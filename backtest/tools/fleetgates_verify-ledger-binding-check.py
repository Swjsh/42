"""Independent re-derivation for verify pass on fleet-gates-ledger-binding-check.md.
READ-ONLY. No trading-path files edited/imported for mutation, only json ledgers read.
"""
import json
from collections import Counter, defaultdict

REPO = "C:/Users/jackw/Desktop/42"
FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
ENTER_VERDICTS = {"ENTER_BULL", "ENTER_BEAR"}
ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_core_by_tick(min_date):
    by_tick = {}
    for rec in load_jsonl(f"{REPO}/automation/state/core-decisions.jsonl"):
        ts = rec.get("ts_et", "")
        if ts < min_date:
            continue
        ct = rec.get("core_tick_id")
        if ct is None:
            continue
        acct = rec.get("account")
        if acct not in ("safe", "bold"):
            continue
        by_tick.setdefault(ct, {})[acct] = rec
    return by_tick


def load_fleet_by_tick(arm):
    by_tick = defaultdict(list)
    for rec in load_jsonl(f"{REPO}/automation/state/fleet/{arm}/decisions.jsonl"):
        ct = rec.get("core_tick_id")
        if ct is None:
            continue
        by_tick[ct].append(rec)
    return by_tick


def fleet_row_is_entry(row):
    return row.get("action") in ENTER_ACTIONS


def build_agg(core_by_tick, fleet_by_tick_all, direction):
    ticks = []
    gate_counter = Counter()
    for ct, accts in core_by_tick.items():
        s = accts.get("safe")
        b = accts.get("bold")
        if s is None or b is None:
            continue
        if direction == "A":
            gated, other = s, b
        else:
            gated, other = b, s
        ga = gated.get("action")
        if not (isinstance(ga, str) and ga.startswith("SKIP_")):
            continue
        if other.get("verdict") not in ENTER_VERDICTS:
            continue
        ticks.append(ct)
        gate_counter[ga] += 1
    n = len(ticks)
    result = {"n_ticks": n, "gate_breakdown": dict(gate_counter), "arms": {}}
    for arm in FLEET_ARMS:
        fbt = fleet_by_tick_all[arm]
        n_logged = 0
        n_entries = 0
        for ct in ticks:
            rows = fbt.get(ct)
            if not rows:
                continue
            n_logged += 1
            if any(fleet_row_is_entry(r) for r in rows):
                n_entries += 1
        result["arms"][arm] = {
            "n_entries": n_entries, "n_logged": n_logged,
            "share_of_all": (n_entries / n) if n else None,
        }
    return result, ticks


def main():
    core_by_tick = load_core_by_tick("2026-08-06")
    fleet_by_tick_all = {a: load_fleet_by_tick(a) for a in FLEET_ARMS}

    agg_a, ticks_a = build_agg(core_by_tick, fleet_by_tick_all, "A")
    agg_b, ticks_b = build_agg(core_by_tick, fleet_by_tick_all, "B")

    print("=== TABLE A (safe gated, bold entered) since 2026-08-06 ===")
    print(json.dumps(agg_a, indent=2))
    print("\n=== TABLE B (bold gated, safe entered) since 2026-08-06 ===")
    print(json.dumps(agg_b, indent=2))

    # spot-check specific quoted core_tick_ids
    checks = [
        ("2026-08-07T12:36:02.451616", "A", "SKIP_STRUCTURE_VETO"),
        ("2026-08-21T13:34:02.490082", "A", "SKIP_STRUCTURE_VETO"),
        ("2026-09-03T11:21:02.576928", "A", "SKIP_STRUCTURE_VETO"),
        ("2026-08-13T11:41:02.990155", "A", "SKIP_BULL_1100_1200"),
        ("2026-08-12T14:16:02.973209", "B", "SKIP_CONF_LVL_REC_AFTERNOON"),
        ("2026-08-13T15:11:02.929340", "B", "SKIP_CONF_LVL_REC_AFTERNOON"),
        ("2026-08-06T10:31:02.400016", "B", "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"),
    ]
    print("\n=== SPOT CHECKS ===")
    for ct, direction, expected_gate in checks:
        accts = core_by_tick.get(ct)
        if not accts:
            print(ct, "NOT FOUND in core_by_tick")
            continue
        s = accts.get("safe")
        b = accts.get("bold")
        print(f"--- {ct} (expect dir={direction} gate={expected_gate}) ---")
        print("  safe:", {k: s.get(k) for k in ("account","verdict","action","setup","reason")} if s else None)
        print("  bold:", {k: b.get(k) for k in ("account","verdict","action","setup","reason")} if b else None)
        for arm in FLEET_ARMS:
            rows = fleet_by_tick_all[arm].get(ct)
            if rows:
                print(f"  {arm}:", [{k: r.get(k) for k in ("action","side","setup_name","reason")} for r in rows])
            else:
                print(f"  {arm}: <no row>")

    # symmetric gate check redo
    print("\n=== SYMMETRIC GATE RE-CHECK ===")
    for gate in ("SKIP_LATE_ENTRY", "SKIP_STALE_TRIGGER", "SKIP_MIN_PREMIUM_FLOOR"):
        both = 0
        either = 0
        for ct, accts in core_by_tick.items():
            s = accts.get("safe")
            b = accts.get("bold")
            if s is None or b is None:
                continue
            sg = s.get("action") == gate
            bg = b.get("action") == gate
            if sg or bg:
                either += 1
            if sg and bg:
                both += 1
        print(gate, "both=", both, "either=", either)

if __name__ == "__main__":
    main()
