"""
INDEPENDENT VERIFICATION of fleet-gates-ledger-binding-check.md / .json.
Written fresh (not copy-pasted from the original fleetgates_ledger-binding-check.py) to
re-derive the same join from raw ledgers and flag any material disagreement.

READ-ONLY: automation/state/**, journal/**. No broker/network calls. <5s runtime.
"""
import json
from collections import Counter, defaultdict

REPO = "C:/Users/jackw/Desktop/42"
FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
ENTER_VERDICTS = ("ENTER_BULL", "ENTER_BEAR")
ENTER_ACTIONS = ("ENTER_BULL", "ENTER_BEAR", "PLACED")
NAMED_WINNING_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARN: bad json line {i} in {path}: {e}")
    return rows


def build_core_index(min_date=None, max_date=None):
    """core_tick_id -> {"safe": row, "bold": row}. Independent re-derivation."""
    rows = load_jsonl(f"{REPO}/automation/state/core-decisions.jsonl")
    idx = defaultdict(dict)
    n_seen = 0
    n_unarmed = 0
    n_no_tick_id = 0
    for r in rows:
        ts = r.get("ts_et", "")
        if min_date and ts < min_date:
            continue
        if max_date and ts >= max_date:
            continue
        acct = r.get("account")
        if acct not in ("safe", "bold"):
            continue
        n_seen += 1
        if r.get("armed") is False:
            n_unarmed += 1
        ct = r.get("core_tick_id")
        if ct is None:
            n_no_tick_id += 1
            continue
        idx[ct][acct] = r
    return idx, {"n_rows_seen": n_seen, "n_unarmed": n_unarmed, "n_no_tick_id": n_no_tick_id}


def build_fleet_index(arm):
    rows = load_jsonl(f"{REPO}/automation/state/fleet/{arm}/decisions.jsonl")
    idx = defaultdict(list)
    for r in rows:
        ct = r.get("core_tick_id")
        if ct is None:
            continue
        idx[ct].append(r)
    return idx


def gated_ticks(core_idx, gated_side, other_side):
    """List of (core_tick_id, gate_label, date) where gated_side's action is SKIP_*
    and other_side's verdict is ENTER_BULL/ENTER_BEAR."""
    out = []
    for ct, accts in core_idx.items():
        g = accts.get(gated_side)
        o = accts.get(other_side)
        if g is None or o is None:
            continue
        act = g.get("action")
        if not (isinstance(act, str) and act.startswith("SKIP_")):
            continue
        if o.get("verdict") not in ENTER_VERDICTS:
            continue
        out.append((ct, act, ct[:10]))
    return out


def fleet_entered(fleet_idx, ct):
    rows = fleet_idx.get(ct)
    if not rows:
        return None  # absent
    return any(r.get("action") in ENTER_ACTIONS for r in rows)


def gate_table(tick_list, fleet_idx_by_arm):
    by_gate = defaultdict(list)
    for ct, gate, date in tick_list:
        by_gate[gate].append((ct, date))
    table = {}
    for gate, ticks in by_gate.items():
        n = len(ticks)
        arm_stats = {}
        for arm in FLEET_ARMS:
            fidx = fleet_idx_by_arm[arm]
            n_logged = 0
            n_entries = 0
            for ct, _ in ticks:
                e = fleet_entered(fidx, ct)
                if e is None:
                    continue
                n_logged += 1
                if e:
                    n_entries += 1
            arm_stats[arm] = {
                "n_ticks": n, "n_logged": n_logged, "n_entries": n_entries,
                "share_of_all": round(n_entries / n, 4) if n else None,
                "share_of_logged": round(n_entries / n_logged, 4) if n_logged else None,
            }
        table[gate] = {"n_ticks": n, "arms": arm_stats}
    return table


def aggregate(tick_list, fleet_idx_by_arm, drop_date=None):
    ticks = [(ct, d) for ct, g, d in tick_list if d != drop_date] if drop_date else \
        [(ct, d) for ct, g, d in tick_list]
    n = len(ticks)
    by_date = Counter(d for _, d in ticks)
    result = {"n_ticks": n, "n_dates": len(by_date), "top_dates": by_date.most_common(5), "arms": {}}
    for arm in FLEET_ARMS:
        fidx = fleet_idx_by_arm[arm]
        n_logged = 0
        n_entries = 0
        for ct, _ in ticks:
            e = fleet_entered(fidx, ct)
            if e is None:
                continue
            n_logged += 1
            if e:
                n_entries += 1
        result["arms"][arm] = {
            "n_entries": n_entries, "n_logged": n_logged,
            "share_of_all_ticks": round(n_entries / n, 4) if n else None,
            "share_of_logged": round(n_entries / n_logged, 4) if n_logged else None,
        }
    return result


def symmetric_check(core_idx, gate_name):
    both = 0
    either = 0
    for ct, accts in core_idx.items():
        s = accts.get("safe")
        b = accts.get("bold")
        if s is None or b is None:
            continue
        sg = s.get("action") == gate_name
        bg = b.get("action") == gate_name
        if sg or bg:
            either += 1
        if sg and bg:
            both += 1
    return both, either


def check_specific_tick(core_idx, fleet_idx_by_arm, ct, expect_gate=None, expect_side=None):
    accts = core_idx.get(ct, {})
    s = accts.get("safe")
    b = accts.get("bold")
    out = {"core_tick_id": ct, "safe_action": s.get("action") if s else None,
           "safe_verdict": s.get("verdict") if s else None,
           "bold_action": b.get("action") if b else None,
           "bold_verdict": b.get("verdict") if b else None}
    for arm in FLEET_ARMS:
        rows = fleet_idx_by_arm[arm].get(ct)
        out[f"{arm}_action"] = rows[0].get("action") if rows else "ABSENT"
    return out


def main():
    print("=" * 90)
    print("INDEPENDENT VERIFICATION -- fleet-gates-ledger-binding-check.md")
    print("=" * 90)

    core_idx, stats = build_core_index(min_date="2026-08-06")
    print(f"\ncore-decisions.jsonl rows since 2026-08-06 (safe/bold only): {stats}")
    n_ticks_both = sum(1 for v in core_idx.values() if "safe" in v and "bold" in v)
    print(f"distinct core_tick_id with BOTH safe+bold rows present: {n_ticks_both}")
    print(f"report claims: 7,998 distinct ticks since 2026-08-06 (100% pairing)")
    print(f"NOTE: my file read happens ~2h after the report's script ran (12:26 -> now) so "
          f"MORE rows may have accumulated live -- expect n_ticks_both >= 7998, not equal.")

    fleet_idx_by_arm = {arm: build_fleet_index(arm) for arm in FLEET_ARMS}
    for arm in FLEET_ARMS:
        print(f"{arm} decisions.jsonl: {sum(len(v) for v in fleet_idx_by_arm[arm].values())} rows, "
              f"{len(fleet_idx_by_arm[arm])} distinct core_tick_ids")

    # ---- Table A: safe gated, bold entered ----
    table_a_ticks = gated_ticks(core_idx, "safe", "bold")
    print(f"\n--- TABLE A (safe gated, bold ENTER) since 2026-08-06: n={len(table_a_ticks)} ---")
    print("report claims: n=133 ticks, 12 distinct dates")
    ta = gate_table(table_a_ticks, fleet_idx_by_arm)
    for gate, d in sorted(ta.items(), key=lambda kv: -kv[1]["n_ticks"]):
        print(f"  {gate:45s} n={d['n_ticks']:4d}  " +
              "  ".join(f"{arm}={d['arms'][arm]['n_entries']}/{d['arms'][arm]['share_of_all']}"
                         for arm in FLEET_ARMS))

    agg_a = aggregate(table_a_ticks, fleet_idx_by_arm)
    print(f"\n  AGGREGATE Table A: n={agg_a['n_ticks']} dates={agg_a['n_dates']} top_dates={agg_a['top_dates']}")
    for arm in FLEET_ARMS:
        print(f"    {arm}: {agg_a['arms'][arm]}")
    print("  report claims aggregate: n=133 dates=12, safe-3 11(8.3%) risky-1 15(11.3%) risky-3 8(6.0%/8.7%logged)")

    best_date_a = agg_a["top_dates"][0][0] if agg_a["top_dates"] else None
    agg_a_drop = aggregate(table_a_ticks, fleet_idx_by_arm, drop_date=best_date_a)
    print(f"\n  DROP-BEST-DAY ({best_date_a}) Table A: n={agg_a_drop['n_ticks']}")
    for arm in FLEET_ARMS:
        print(f"    {arm}: {agg_a_drop['arms'][arm]}")
    print("  report claims drop-best-day(2026-09-03): n=103, safe-3 8.7% risky-1 12.6% risky-3 7.8%")

    # named winning days concentration for Table A
    n_on_named = sum(1 for _, _, d in table_a_ticks if d in NAMED_WINNING_DAYS)
    print(f"\n  Table A ticks on named winning days (08-06/08-13/08-27/08-28): {n_on_named} of "
          f"{len(table_a_ticks)} = {round(100*n_on_named/len(table_a_ticks),1) if table_a_ticks else None}%")
    print("  report claims: 14 of 133 = 10.5%")

    # ---- Table B: bold gated, safe entered (mirror) ----
    table_b_ticks = gated_ticks(core_idx, "bold", "safe")
    print(f"\n--- TABLE B (bold gated, safe ENTER) since 2026-08-06: n={len(table_b_ticks)} ---")
    print("report claims: n=187 ticks, 17 distinct dates")
    tb = gate_table(table_b_ticks, fleet_idx_by_arm)
    for gate, d in sorted(tb.items(), key=lambda kv: -kv[1]["n_ticks"]):
        print(f"  {gate:45s} n={d['n_ticks']:4d}  " +
              "  ".join(f"{arm}={d['arms'][arm]['n_entries']}/{d['arms'][arm]['share_of_all']}"
                         for arm in FLEET_ARMS))

    agg_b = aggregate(table_b_ticks, fleet_idx_by_arm)
    print(f"\n  AGGREGATE Table B: n={agg_b['n_ticks']} dates={agg_b['n_dates']} top_dates={agg_b['top_dates']}")
    for arm in FLEET_ARMS:
        print(f"    {arm}: {agg_b['arms'][arm]}")
    print("  report claims aggregate: n=187 dates=17, safe-3 15(8.0%) risky-1 41(21.9%) risky-3 28(15.0%/18.7%logged)")

    best_date_b = agg_b["top_dates"][0][0] if agg_b["top_dates"] else None
    agg_b_drop = aggregate(table_b_ticks, fleet_idx_by_arm, drop_date=best_date_b)
    print(f"\n  DROP-BEST-DAY ({best_date_b}) Table B: n={agg_b_drop['n_ticks']}")
    for arm in FLEET_ARMS:
        print(f"    {arm}: {agg_b_drop['arms'][arm]}")
    print("  report claims drop-best-day(2026-08-20): n=155, safe-3 9.7% risky-1 26.5% risky-3 16.8%")

    # ---- Sept-only sub-window ----
    core_idx_sept, stats_sept = build_core_index(min_date="2026-09-01")
    fleet_idx_by_arm_sept = fleet_idx_by_arm  # same arm ledgers, just filter ticks by date
    table_a_sept = [t for t in gated_ticks(core_idx_sept, "safe", "bold")]
    table_b_sept = [t for t in gated_ticks(core_idx_sept, "bold", "safe")]
    print(f"\n--- SEPT-ONLY (2026-09-01..today) Table A: n={len(table_a_sept)} ---")
    ta_sept = gate_table(table_a_sept, fleet_idx_by_arm_sept)
    for gate, d in sorted(ta_sept.items(), key=lambda kv: -kv[1]["n_ticks"]):
        print(f"  {gate:45s} n={d['n_ticks']:4d}  " +
              "  ".join(f"{arm}={d['arms'][arm]['n_entries']}/{d['arms'][arm]['share_of_all']}"
                         for arm in FLEET_ARMS))
    print("  report claims: SKIP_BULL_1100_1200 n=20 safe-3/risky-1 15.0%; SKIP_STRUCTURE_VETO n=20 safe-3/risky-1 5.0%")

    print(f"\n--- SEPT-ONLY (2026-09-01..today) Table B: n={len(table_b_sept)} ---")
    tb_sept = gate_table(table_b_sept, fleet_idx_by_arm_sept)
    for gate, d in sorted(tb_sept.items(), key=lambda kv: -kv[1]["n_ticks"]):
        print(f"  {gate:45s} n={d['n_ticks']:4d}  " +
              "  ".join(f"{arm}={d['arms'][arm]['n_entries']}/{d['arms'][arm]['share_of_all']}"
                         for arm in FLEET_ARMS))
    print("  report claims: no Table B gate reaches n>=10 in Sept")

    # ---- Symmetric gate checks ----
    print("\n--- SYMMETRIC GATE CHECKS (whole window since 2026-08-06) ---")
    for gate in ("SKIP_LATE_ENTRY", "SKIP_STALE_TRIGGER", "SKIP_MIN_PREMIUM_FLOOR"):
        both, either = symmetric_check(core_idx, gate)
        print(f"  {gate}: both={both} either={either} symmetric={both==either and either>0}")
    print("  report claims: SKIP_LATE_ENTRY 16/52 both; SKIP_STALE_TRIGGER 120/120 both; "
          "SKIP_MIN_PREMIUM_FLOOR 0/50 both")

    # ---- Spot-check quoted core_tick_ids ----
    print("\n--- SPOT-CHECK QUOTED core_tick_ids ---")
    quoted = [
        ("2026-08-07T12:36:02.451616", "Table A SKIP_STRUCTURE_VETO, claims safe-3+risky-1 entered"),
        ("2026-08-21T13:34:02.490082", "Table A SKIP_STRUCTURE_VETO, claims safe-3+risky-1 entered"),
        ("2026-09-03T11:21:02.576928", "Table A SKIP_STRUCTURE_VETO, claims safe-3+risky-1 entered (veto-scope tick)"),
        ("2026-08-13T11:41:02.990155", "Table A SKIP_BULL_1100_1200, claims safe-3+risky-1 entered"),
        ("2026-08-19T11:49:02.561586", "Table A SKIP_BULL_1100_1200, claims safe-3+risky-1 entered"),
        ("2026-08-21T11:06:02.592949", "Table A SKIP_BULL_1100_1200, claims safe-3+risky-1 entered"),
        ("2026-08-21T11:36:02.613080", "Table A SKIP_BULL_1100_1200, claims safe-3+risky-1 entered"),
        ("2026-08-12T14:16:02.973209", "Table B SKIP_CONF_LVL_REC_AFTERNOON, claims safe-3+risky-1 entered"),
        ("2026-08-13T15:11:02.929340", "Table B SKIP_CONF_LVL_REC_AFTERNOON, claims risky-1 entered"),
        ("2026-08-26T14:56:02.621899", "Table B SKIP_CONF_LVL_REC_AFTERNOON, claims safe-3+risky-3 entered"),
        ("2026-08-26T15:51:02.640393", "Table B SKIP_CONF_LVL_REC_AFTERNOON, claims safe-3 entered"),
        ("2026-08-06T10:31:02.400016", "Table B SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY, claims risky-1+risky-3 entered"),
        ("2026-08-11T11:51:02.965227", "Table B SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY, claims risky-1 entered"),
        ("2026-08-12T11:26:03.024016", "Table B SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY, claims risky-1+risky-3 entered"),
    ]
    for ct, note in quoted:
        r = check_specific_tick(core_idx, fleet_idx_by_arm, ct)
        print(f"  {ct}  [{note}]")
        print(f"    safe: action={r['safe_action']} verdict={r['safe_verdict']} | "
              f"bold: action={r['bold_action']} verdict={r['bold_verdict']}")
        print(f"    safe-3={r['safe-3_action']}  risky-1={r['risky-1_action']}  risky-3={r['risky-3_action']}")

    print("\nDONE")


if __name__ == "__main__":
    main()
