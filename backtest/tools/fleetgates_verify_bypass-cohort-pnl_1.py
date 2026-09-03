"""
SCRATCH / read-only VERIFICATION tool. LEDGER lens on G3 (fleet-gates-bypass-cohort-pnl).
Independently rebuilds the core_tick_id -> fleet decisions -> P&L join WITHOUT importing
fleetgates_bypass-cohort-pnl.py, to check whether that script's headline dollar figures survive
a from-scratch re-derivation.

Key difference from the original script's join_arm(): when an (arm, date, symbol) key has
MORE THAN ONE mae-mfe.json trade candidate (same-day re-entry into the same strike -- 33 such
keys exist for the 4 fleet arms on/after 2026-08-03), this script pairs decision rows to trade
candidates POSITIONALLY IN CHRONOLOGICAL ORDER (both lists sorted by timestamp, zipped 1:1)
instead of the original's "first same-qty candidate" rule, which -- because same-day re-entries
of the same strike almost always share the same qty -- resolves to candidates[0] for EVERY
decision row hitting that key, assigning the SAME single trade's P&L to every one of them.

NEVER writes into automation/state/**, journal/**, analysis/quote-tape/**. Read-only on the
whole repo except its own output file (argv[1]).
"""
import json
import random
import statistics
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET_ARMS = ["safe-3", "risky-1", "risky-3", "safe-1"]
RIBBON_SETUPS = {"BULLISH_RECLAIM_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON"}
NAMED_WINNING_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
SEPT_START = "2026-09-01"

random.seed(42)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_core_index():
    idx = {}
    n_total = 0
    n_indexed = 0
    first_ctid_ts = None
    with open(ROOT / "automation/state/core-decisions.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ctid = r.get("core_tick_id")
            acct = r.get("account")
            if ctid and first_ctid_ts is None:
                first_ctid_ts = r.get("ts_et")
            if not ctid or acct not in ("safe", "bold"):
                continue
            n_indexed += 1
            idx.setdefault(ctid, {})[acct] = r
    return idx, n_total, n_indexed, first_ctid_ts


def load_mae_mfe():
    d = json.load(open(ROOT / "analysis/pain-ledger/mae-mfe.json", encoding="utf-8"))
    trades = d["trades"]
    lut = defaultdict(list)
    for t in trades:
        lut[(t["arm"], t["date"], t["symbol"])].append(t)
    for k in lut:
        lut[k].sort(key=lambda t: t.get("entry_ts_utc") or "")
    return d, lut


def build_fill_cycles():
    """Same flat-to-flat reconstruction rule as the original tool (0DTE: qty-return-to-zero
    is a real trade boundary), re-derived independently from fills-ledger.jsonl."""
    fills = load_jsonl(ROOT / "automation/state/fills-ledger.jsonl")
    groups = defaultdict(list)
    for r in fills:
        if r.get("attribution") != "engine":
            continue
        if not r.get("is_option"):
            continue
        groups[(r.get("arm"), r.get("symbol"), r.get("date_et"))].append(r)
    cycles = []
    for (arm, symbol, date), rows in groups.items():
        rows = sorted(rows, key=lambda r: r["ts_utc"])
        open_qty = 0.0
        buy_cost = 0.0
        sell_proceeds = 0.0
        entry_ts_et = None
        entry_qty = 0.0
        for r in rows:
            qty = r.get("qty", 0.0)
            price = r.get("price", 0.0)
            mult = r.get("multiplier", 100)
            if r.get("side") == "buy":
                if open_qty == 0:
                    entry_ts_et = r["ts_et"]
                    entry_qty = 0.0
                    buy_cost = 0.0
                    sell_proceeds = 0.0
                open_qty += qty
                entry_qty += qty
                buy_cost += qty * price * mult
            elif r.get("side") == "sell":
                open_qty -= qty
                sell_proceeds += qty * price * mult
                if abs(open_qty) < 1e-6:
                    cycles.append({
                        "arm": arm, "symbol": symbol, "date": date,
                        "entry_ts_et": entry_ts_et, "entry_qty": entry_qty,
                        "realized_pnl": round(sell_proceeds - buy_cost, 4),
                        "source": "fills_ledger_reconstruction",
                    })
                    open_qty = 0.0
        if abs(open_qty) > 1e-6:
            cycles.append({
                "arm": arm, "symbol": symbol, "date": date,
                "entry_ts_et": entry_ts_et, "entry_qty": entry_qty,
                "realized_pnl": None, "outcome": "OPEN_UNFLATTENED",
                "source": "fills_ledger_reconstruction",
            })
    return cycles


def classify_entry(entry_row, core_idx):
    ctid = entry_row.get("core_tick_id")
    side = entry_row.get("side")
    setup = entry_row.get("setup_name")
    want = "ENTER_BULL" if side == "C" else ("ENTER_BEAR" if side == "P" else None)
    out = {"core_tick_id": ctid, "want_verdict": want,
           "safe_verdict": None, "bold_verdict": None, "safe_reason": None}
    if setup not in RIBBON_SETUPS:
        out["cohort"] = "NOT_APPLICABLE_NON_RIBBON"
        return out
    if not ctid or ctid not in core_idx or want is None:
        out["cohort"] = "UNCLASSIFIED_NO_CORE_TICK"
        return out
    pair = core_idx[ctid]
    safe_row, bold_row = pair.get("safe"), pair.get("bold")
    if safe_row is None or bold_row is None:
        out["cohort"] = "UNCLASSIFIED_MISSING_PAIR_ROW"
        return out
    out["safe_verdict"] = safe_row.get("verdict")
    out["bold_verdict"] = bold_row.get("verdict")
    out["safe_reason"] = safe_row.get("reason")
    safe_passed = out["safe_verdict"] == want
    bold_passed = out["bold_verdict"] == want
    if (not safe_passed) and bold_passed:
        out["cohort"] = "A_BYPASS"
    elif safe_passed and bold_passed:
        out["cohort"] = "B_BOTH_PASSED"
    else:
        out["cohort"] = "C_OTHER"
    return out


def _parse_iso(ts):
    ts = ts.replace("Z", "")
    if "+" in ts[10:]:
        ts = ts[: 10 + ts[10:].index("+")]
    if ts.count("-") > 2:
        head = ts[:10]
        rest = ts[10:]
        if "-" in rest:
            rest = rest[: rest.index("-")]
        ts = head + rest
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in ts else "%Y-%m-%dT%H:%M:%S"
    return datetime.strptime(ts, fmt)


def join_arm_corrected(arm, core_idx, mae_lut, cycles_by_key):
    """CORRECTED join: decision rows and mae/fallback candidates sharing an (arm,date,symbol)
    key are paired POSITIONALLY IN TIME ORDER (1st decision <-> 1st trade chronologically,
    2nd <-> 2nd, ...), not by qty-match-then-always-take-index-0 as the original does."""
    path = ROOT / f"automation/state/fleet/{arm}/decisions.jsonl"
    rows = load_jsonl(path)
    decisions = []
    n_skip_relog = 0
    for r in rows:
        if r.get("action") not in ("ENTER_BULL", "ENTER_BEAR"):
            continue
        placement = r.get("placement") or {}
        if not placement.get("placed"):
            n_skip_relog += 1
            continue
        ts_et = r.get("ts_et", "")
        date = ts_et[:10]
        symbol = placement.get("symbol")
        cls = classify_entry(r, core_idx)
        decisions.append({
            "arm": arm, "date": date, "symbol": symbol,
            "setup_name": r.get("setup_name"), "decision_ts_et": ts_et,
            "decision_qty": r.get("qty"),
            **cls,
        })

    # group decisions by key, preserving arrival order, then sort each group by ts_et
    dec_by_key = defaultdict(list)
    for d in decisions:
        dec_by_key[(d["arm"], d["date"], d["symbol"])].append(d)
    for k in dec_by_key:
        dec_by_key[k].sort(key=lambda d: d["decision_ts_et"])

    out = []
    n_joined = 0
    n_joined_fallback = 0
    for key, dec_group in dec_by_key.items():
        mae_candidates = list(mae_lut.get(key, []))
        # positional pairing: 1st decision <-> 1st mae candidate, etc.
        for i, d in enumerate(dec_group):
            rec = dict(d)
            if i < len(mae_candidates):
                m = mae_candidates[i]
                rec.update({"matched": True, "match_source": "pain_ledger_mae_mfe_positional",
                            "realized_pnl": m.get("realized_pnl"), "outcome": m.get("outcome")})
                n_joined += 1
            else:
                # fall through to fills-ledger reconstruction fallback, also positional
                cyc_candidates = sorted(
                    [c for c in cycles_by_key.get(key, []) if c.get("entry_ts_et")],
                    key=lambda c: c["entry_ts_et"])
                fb_idx = i - len(mae_candidates)
                if fb_idx < len(cyc_candidates):
                    c = cyc_candidates[fb_idx]
                    rec.update({"matched": True,
                                "match_source": "fills_ledger_reconstruction_positional",
                                "realized_pnl": c.get("realized_pnl"), "outcome": c.get("outcome")})
                    n_joined += 1
                    n_joined_fallback += 1
                else:
                    rec.update({"matched": False, "match_source": None, "realized_pnl": None,
                                "outcome": None})
            out.append(rec)
    return out, len(decisions), n_joined, n_joined_fallback, n_skip_relog


def bootstrap_ci_mean(values, n_boot=5000, alpha=0.05):
    if not values:
        return None, None, None
    n = len(values)
    if n == 1:
        return values[0], values[0], values[0]
    means = []
    for _ in range(n_boot):
        sample = [values[random.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = max(0, min(int((alpha / 2) * n_boot), n_boot - 1))
    hi_idx = max(0, min(int((1 - alpha / 2) * n_boot) - 1, n_boot - 1))
    point = sum(values) / n
    return point, means[lo_idx], means[hi_idx]


def cohort_stats(trades):
    matched = [t for t in trades if t.get("matched") and t.get("realized_pnl") is not None]
    n = len(matched)
    pnls = [t["realized_pnl"] for t in matched]
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    wr = (len(wins) / (len(wins) + len(losses))) if (len(wins) + len(losses)) > 0 else None
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (
        float("inf") if wins and not losses else None)
    point, lo, hi = bootstrap_ci_mean(pnls) if pnls else (None, None, None)
    by_day = defaultdict(list)
    for t in matched:
        by_day[t["date"]].append(t["realized_pnl"])
    day_totals = {d: sum(v) for d, v in by_day.items()}
    best_day = max(day_totals, key=lambda d: day_totals[d]) if day_totals else None
    drop_best = (round(total - day_totals[best_day], 2), n - len(by_day[best_day])) if best_day else (None, None)
    return {
        "n": n, "n_unmatched": len(trades) - n,
        "total_pnl": round(total, 2),
        "wr": round(wr, 4) if wr is not None else None,
        "n_win": len(wins), "n_loss": len(losses),
        "pf": (round(pf, 3) if isinstance(pf, float) and pf != float("inf") else
               ("inf" if pf == float("inf") else None)),
        "mean_pnl": round(point, 2) if point is not None else None,
        "mean_pnl_ci95_lo": round(lo, 2) if lo is not None else None,
        "mean_pnl_ci95_hi": round(hi, 2) if hi is not None else None,
        "best_day": best_day, "best_day_pnl": round(day_totals[best_day], 2) if best_day else None,
        "drop_best_day_total_pnl": drop_best[0], "drop_best_day_n": drop_best[1],
    }


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "analysis/deep-research/2026-09-03-money/fleetgates-verify-bypass-cohort-pnl-1.json")

    core_idx, n_core_total, n_core_indexed, first_ctid_ts = build_core_index()
    mae_meta, mae_lut = load_mae_mfe()
    cycles = build_fill_cycles()
    cycles_by_key = defaultdict(list)
    for c in cycles:
        cycles_by_key[(c["arm"], c["date"], c["symbol"])].append(c)

    # sanity: count duplicate mae_lut keys among fleet arms on/after 2026-08-03
    dup_keys = {k: len(v) for k, v in mae_lut.items()
                if len(v) > 1 and k[0] in FLEET_ARMS and k[1] >= "2026-08-03"}

    report = {
        "generated_by": "fleetgates_verify_bypass-cohort-pnl_1.py",
        "core_tick_id_first_seen_et": first_ctid_ts,
        "core_decisions_total_rows": n_core_total,
        "core_decisions_rows_with_core_tick_id": n_core_indexed,
        "dup_mae_lut_keys_fleet_arms_post_2026_08_03": {
            "n_keys": len(dup_keys), "keys": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in dup_keys.items()},
        },
        "per_arm": {},
        "join_stats": {},
    }

    all_joined = {}
    for arm in FLEET_ARMS:
        rows, n_entry, n_joined, n_fb, n_skip = join_arm_corrected(arm, core_idx, mae_lut, cycles_by_key)
        all_joined[arm] = rows
        report["join_stats"][arm] = {
            "n_entry_decisions_placed": n_entry, "n_joined": n_joined,
            "n_joined_via_fallback": n_fb, "n_relog_skipped": n_skip,
        }
        cohort_a = [r for r in rows if r["cohort"] == "A_BYPASS"]
        cohort_b = [r for r in rows if r["cohort"] == "B_BOTH_PASSED"]
        cohort_c = [r for r in rows if r["cohort"] == "C_OTHER"]
        report["per_arm"][arm] = {
            "n_total_placed_entries": len(rows),
            "cohort_A_bypass": cohort_stats(cohort_a),
            "cohort_B_both_passed": cohort_stats(cohort_b),
            "cohort_C_other": cohort_stats(cohort_c),
            "named_winning_days": {
                d: {"A": cohort_stats([t for t in cohort_a if t["date"] == d]),
                    "B": cohort_stats([t for t in cohort_b if t["date"] == d])}
                for d in NAMED_WINNING_DAYS
            },
            "september": {
                "A": cohort_stats([t for t in cohort_a if t["date"] >= SEPT_START]),
                "B": cohort_stats([t for t in cohort_b if t["date"] >= SEPT_START]),
            },
        }

    overall_a, overall_b = [], []
    for arm in FLEET_ARMS:
        overall_a += [r for r in all_joined[arm] if r["cohort"] == "A_BYPASS"]
        overall_b += [r for r in all_joined[arm] if r["cohort"] == "B_BOTH_PASSED"]
    report["population_overall"] = {
        "cohort_A_bypass_all_arms": cohort_stats(overall_a),
        "cohort_B_both_passed_all_arms": cohort_stats(overall_b),
    }
    safe3_a = [r for r in all_joined["safe-3"] if r["cohort"] == "A_BYPASS"]
    safe3_b = [r for r in all_joined["safe-3"] if r["cohort"] == "B_BOTH_PASSED"]
    report["safe3_only"] = {
        "cohort_A_bypass": cohort_stats(safe3_a),
        "cohort_B_both_passed": cohort_stats(safe3_b),
        "cohort_A_september": cohort_stats([t for t in safe3_a if t["date"] >= SEPT_START]),
    }

    # Detail dump: full per-trade record for safe-3 cohort A (to hand-check against the report's
    # 13-trade table) and the specific bug-example key.
    report["safe3_cohort_A_full_dump"] = [
        {"date": t["date"], "symbol": t["symbol"], "decision_ts_et": t["decision_ts_et"],
         "realized_pnl": t.get("realized_pnl"), "safe_verdict": t.get("safe_verdict"),
         "match_source": t.get("match_source")}
        for t in sorted(safe3_a, key=lambda t: t["decision_ts_et"])
    ]
    bug_example_key = ("risky-1", "2026-08-12", "SPY260812P00773000")
    report["bug_example_risky1_20260812_773P"] = [
        {"decision_ts_et": t["decision_ts_et"], "setup_name": t["setup_name"],
         "cohort": t["cohort"], "realized_pnl": t.get("realized_pnl")}
        for t in all_joined["risky-1"]
        if (t["arm"], t["date"], t["symbol"]) == bug_example_key
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"WROTE {out_path}")
    print("dup_mae_lut_keys:", report["dup_mae_lut_keys_fleet_arms_post_2026_08_03"]["n_keys"])
    print("join_stats:", json.dumps(report["join_stats"], indent=2))
    print("population_overall:", json.dumps(report["population_overall"], indent=2))
    print("safe3_only:", json.dumps(report["safe3_only"], indent=2))
    print("bug_example:", json.dumps(report["bug_example_risky1_20260812_773P"], indent=2))


if __name__ == "__main__":
    main()
