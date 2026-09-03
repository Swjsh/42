"""
SCRATCH / read-only analysis tool. G3 bypass-cohort-pnl.
Joins fleet arm entry decisions -> core-decisions.jsonl (safe+bold perception at the
entry's core_tick_id) -> fills-ledger-derived per-position P&L (analysis/pain-ledger/mae-mfe.json,
itself built from fills-ledger.jsonl attribution==engine).

NEVER writes into automation/state/**, journal/**, analysis/quote-tape/**. Read-only on the
whole repo except its own output file (passed as sys.argv[1]).
"""
import json
import sys
import random
import statistics
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET_ARMS = ["safe-3", "risky-1", "risky-3", "safe-1"]

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
    """core_tick_id -> {'safe': row, 'bold': row}. Only rows carrying a non-null
    core_tick_id are indexed (field introduced 2026-08-03 09:30 ET per this-session grep;
    rows before that date carry no core_tick_id key at all)."""
    idx = {}
    path = ROOT / "automation/state/core-decisions.jsonl"
    n_total = 0
    n_indexed = 0
    with open(path, encoding="utf-8") as f:
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
            if not ctid or acct not in ("safe", "bold"):
                continue
            n_indexed += 1
            idx.setdefault(ctid, {})[acct] = r
    return idx, n_total, n_indexed


def load_mae_mfe():
    d = json.load(open(ROOT / "analysis/pain-ledger/mae-mfe.json", encoding="utf-8"))
    trades = d["trades"]
    lut = defaultdict(list)
    for t in trades:
        lut[(t["arm"], t["date"], t["symbol"])].append(t)
    return d, lut


def _parse_iso(ts):
    # "2026-09-03T11:07:15.548666" or with -04:00 offset -- strip offset, treat naive ET.
    ts = ts.replace("Z", "")
    if "+" in ts[10:]:
        ts = ts[: 10 + ts[10:].index("+")]
    if ts.count("-") > 2:  # offset like -04:00 after the date's two dashes
        head = ts[:10]
        rest = ts[10:]
        if "-" in rest:
            rest = rest[: rest.index("-")]
        ts = head + rest
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in ts else "%Y-%m-%dT%H:%M:%S"
    return datetime.strptime(ts, fmt)


def build_fill_cycles_from_ledger():
    """Reconstruct flat-to-flat round-trip positions per (arm, symbol, date) directly from
    fills-ledger.jsonl (attribution==engine only, per pain-ledger's own provenance rule).
    Used ONLY as a fallback for entries the pre-built pain-ledger (analysis/pain-ledger/
    mae-mfe.json, generated 2026-09-02T16:26:57 ET -- BEFORE today 2026-09-03) doesn't cover.
    0DTE rule: every position is flat by EOD, so a qty-return-to-zero boundary is a real
    trade boundary, not an artifact."""
    fills = load_jsonl(ROOT / "automation/state/fills-ledger.jsonl")
    groups = defaultdict(list)
    for r in fills:
        if r.get("attribution") != "engine":
            continue
        if not r.get("is_option"):
            continue
        key = (r.get("arm"), r.get("symbol"), r.get("date_et"))
        groups[key].append(r)
    cycles = []  # each: dict(arm,symbol,date,entry_ts_et,realized_pnl,qty,exit_legs)
    for (arm, symbol, date), rows in groups.items():
        rows = sorted(rows, key=lambda r: r["ts_utc"])
        open_qty = 0.0
        buy_cost = 0.0
        sell_proceeds = 0.0
        entry_ts_et = None
        entry_qty = 0.0
        n_exit_legs = 0
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
                    n_exit_legs = 0
                open_qty += qty
                entry_qty += qty
                buy_cost += qty * price * mult
            elif r.get("side") == "sell":
                open_qty -= qty
                sell_proceeds += qty * price * mult
                n_exit_legs += 1
                if abs(open_qty) < 1e-6:
                    cycles.append({
                        "arm": arm, "symbol": symbol, "date": date,
                        "entry_ts_et": entry_ts_et, "entry_qty": entry_qty,
                        "realized_pnl": round(sell_proceeds - buy_cost, 4),
                        "n_exit_legs": n_exit_legs,
                        "outcome": ("winner" if (sell_proceeds - buy_cost) > 0.005 else
                                    ("loser" if (sell_proceeds - buy_cost) < -0.005 else "scratch")),
                        "source": "fills_ledger_reconstruction",
                    })
                    open_qty = 0.0
        if abs(open_qty) > 1e-6:
            # still open (unflattened as of ledger snapshot time) -- report as unrealized,
            # not silently dropped.
            cycles.append({
                "arm": arm, "symbol": symbol, "date": date,
                "entry_ts_et": entry_ts_et, "entry_qty": entry_qty,
                "realized_pnl": None, "n_exit_legs": n_exit_legs,
                "outcome": "OPEN_UNFLATTENED_AS_OF_LEDGER_SNAPSHOT",
                "open_qty_remaining": round(open_qty, 4),
                "source": "fills_ledger_reconstruction",
            })
    return cycles




RIBBON_SETUPS = {"BULLISH_RECLAIM_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON"}
# The safe/bold perception-swap mechanism this whole analysis measures (build_shared_signal.py
# section 1c/1d of veto-scope-safe-3.md) re-keys ONLY the ribbon_ride strategy's bear/bull
# blocks from the core-decisions safe/bold rows. VWAP_CONTINUATION and
# VWAP_RECLAIM_FAILED_BREAK are separately-sourced strategies (fleet_market.vwap_strategy_block
# / a dedicated setup) with NO safe/bold role split -- comparing their entry tick's core-row
# verdict to the entry's side would compare two unrelated signals. Those setups are excluded
# from A/B/C classification and reported separately as NOT_APPLICABLE_NON_RIBBON_STRATEGY.


def classify_entry(entry_row, core_idx):
    """Returns dict: cohort ('A_BYPASS'|'B_BOTH_PASSED'|'C_OTHER'|'UNCLASSIFIED_NO_CORE_TICK'|
    'NOT_APPLICABLE_NON_RIBBON_STRATEGY'), safe_verdict, safe_action, bold_verdict,
    want_verdict, core_tick_id."""
    ctid = entry_row.get("core_tick_id")
    side = entry_row.get("side")  # "C" or "P"
    setup = entry_row.get("setup_name")
    want = "ENTER_BULL" if side == "C" else ("ENTER_BEAR" if side == "P" else None)
    out = {
        "core_tick_id": ctid, "side": side, "want_verdict": want,
        "safe_verdict": None, "safe_action": None, "safe_reason": None,
        "bold_verdict": None, "bold_action": None,
        "safe_vix": None, "bold_vix": None,
    }
    if setup not in RIBBON_SETUPS:
        out["cohort"] = "NOT_APPLICABLE_NON_RIBBON_STRATEGY"
        return out
    if not ctid or ctid not in core_idx or want is None:
        out["cohort"] = "UNCLASSIFIED_NO_CORE_TICK"
        return out
    pair = core_idx[ctid]
    safe_row = pair.get("safe")
    bold_row = pair.get("bold")
    if safe_row is None or bold_row is None:
        out["cohort"] = "UNCLASSIFIED_MISSING_PAIR_ROW"
        if safe_row:
            out["safe_verdict"] = safe_row.get("verdict")
            out["safe_action"] = safe_row.get("action")
        if bold_row:
            out["bold_verdict"] = bold_row.get("verdict")
        return out
    out["safe_verdict"] = safe_row.get("verdict")
    out["safe_action"] = safe_row.get("action")
    out["safe_reason"] = safe_row.get("reason")
    out["bold_verdict"] = bold_row.get("verdict")
    out["bold_action"] = bold_row.get("action")
    out["safe_vix"] = safe_row.get("vix")
    out["bold_vix"] = bold_row.get("vix")
    safe_passed = out["safe_verdict"] == want
    bold_passed = out["bold_verdict"] == want
    if (not safe_passed) and bold_passed:
        out["cohort"] = "A_BYPASS"
    elif safe_passed and bold_passed:
        out["cohort"] = "B_BOTH_PASSED"
    else:
        out["cohort"] = "C_OTHER"  # safe passed alone, or neither passed (yet arm entered
        # anyway e.g. via VWAP strategies / non-ribbon path, or a hard-skip rescue)
    return out


def join_arm(arm, core_idx, mae_lut, cycles_by_key):
    path = ROOT / f"automation/state/fleet/{arm}/decisions.jsonl"
    rows = load_jsonl(path)
    out = []
    n_entry = 0
    n_joined = 0
    n_joined_fallback = 0
    n_reentry_logs_skipped = 0
    for r in rows:
        if r.get("action") not in ("ENTER_BULL", "ENTER_BEAR"):
            continue
        placement = r.get("placement") or {}
        if not placement.get("placed"):
            # Engine re-logs the strategic verdict (action=ENTER_BULL/BEAR) every tick a
            # position stays open under that same setup, even when NO new order is placed
            # (placement.placed=False, symbol often null) -- confirmed by inspection
            # (risky-1/decisions.jsonl 2026-06-21..24 rows). Counting these as trades would
            # massively over-count entries against fills-ledger. Only real placements count.
            n_reentry_logs_skipped += 1
            continue
        n_entry += 1
        ts_et = r.get("ts_et", "")
        date = ts_et[:10]
        placement = r.get("placement") or {}
        symbol = placement.get("symbol")
        setup = r.get("setup_name")
        cls = classify_entry(r, core_idx)
        key = (arm, date, symbol)
        candidates = mae_lut.get(key, [])
        matched = None
        fallback = False
        if len(candidates) == 1:
            matched = candidates[0]
        elif len(candidates) > 1:
            # disambiguate by qty match first, else first
            qty = r.get("qty")
            same_qty = [c for c in candidates if c.get("qty") == qty]
            matched = same_qty[0] if same_qty else candidates[0]
        if matched is None:
            # fallback: reconstruct from fills-ledger.jsonl directly (covers today
            # 2026-09-03, which postdates the pain-ledger snapshot generated 2026-09-02
            # 16:26 ET, and any other gap).
            cyc_candidates = cycles_by_key.get(key, [])
            if cyc_candidates:
                try:
                    dec_dt = _parse_iso(ts_et)
                except Exception:
                    dec_dt = None
                best = None
                best_delta = None
                for c in cyc_candidates:
                    if not c.get("entry_ts_et"):
                        continue
                    try:
                        c_dt = _parse_iso(c["entry_ts_et"])
                    except Exception:
                        continue
                    if dec_dt is None:
                        delta = 0
                    else:
                        delta = (c_dt - dec_dt).total_seconds()
                    if delta < -30:  # cycle entry can't be meaningfully before the decision
                        continue
                    ad = abs(delta)
                    if best_delta is None or ad < best_delta:
                        best_delta = ad
                        best = c
                if best is not None:
                    matched = best
                    fallback = True
        rec = {
            "arm": arm, "date": date, "symbol": symbol, "setup_name": setup,
            "core_tick_id": cls["core_tick_id"], "cohort": cls["cohort"],
            "want_verdict": cls["want_verdict"],
            "safe_verdict": cls["safe_verdict"], "safe_action": cls["safe_action"],
            "safe_reason": cls["safe_reason"],
            "bold_verdict": cls["bold_verdict"], "bold_action": cls["bold_action"],
            "vix": cls["safe_vix"] if cls["safe_vix"] is not None else cls["bold_vix"],
            "decision_qty": r.get("qty"), "decision_strike": r.get("strike"),
            "decision_ts_et": ts_et,
        }
        if matched is not None and not fallback:
            n_joined += 1
            rec.update({
                "matched": True, "match_source": "pain_ledger_mae_mfe",
                "realized_pnl": matched.get("realized_pnl"),
                "outcome": matched.get("outcome"),
                "entry_price": matched.get("entry_price"),
                "qty": matched.get("qty"),
                "hold_minutes": matched.get("hold_minutes"),
                "recency": matched.get("recency"),
                "entry_ts_utc": matched.get("entry_ts_utc"),
            })
        elif matched is not None and fallback:
            n_joined += 1
            n_joined_fallback += 1
            rec.update({
                "matched": True, "match_source": "fills_ledger_reconstruction",
                "realized_pnl": matched.get("realized_pnl"),
                "outcome": matched.get("outcome"),
                "entry_price": None,
                "qty": matched.get("entry_qty"),
                "hold_minutes": None,
                "recency": "live_today" if date == "2026-09-03" else "reconstructed",
                "entry_ts_utc": None,
                "entry_ts_et": matched.get("entry_ts_et"),
                "open_qty_remaining": matched.get("open_qty_remaining"),
            })
        else:
            rec.update({"matched": False, "match_source": None, "realized_pnl": None,
                        "outcome": None})
        out.append(rec)
    return out, n_entry, n_joined, n_joined_fallback, n_reentry_logs_skipped


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
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = int((1 - alpha / 2) * n_boot) - 1
    lo_idx = max(0, min(lo_idx, n_boot - 1))
    hi_idx = max(0, min(hi_idx, n_boot - 1))
    point = sum(values) / n
    return point, means[lo_idx], means[hi_idx]


def vix_band(v):
    if v is None:
        return "unknown"
    if v < 15:
        return "<15"
    if v < 18:
        return "15-18"
    if v < 22:
        return "18-22"
    if v < 26:
        return "22-26"
    return ">=26"


def cohort_stats(trades):
    """trades: list of joined+matched records (realized_pnl not None)."""
    matched = [t for t in trades if t.get("matched") and t.get("realized_pnl") is not None]
    n = len(matched)
    pnls = [t["realized_pnl"] for t in matched]
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    scratches = [p for p in pnls if p == 0]
    wr = (len(wins) / (len(wins) + len(losses))) if (len(wins) + len(losses)) > 0 else None
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (
        float("inf") if wins and not losses else None)
    point, lo, hi = bootstrap_ci_mean(pnls) if pnls else (None, None, None)
    top3 = sorted(wins, reverse=True)[:3]
    top3_gross_win_concentration = (sum(top3) / sum(wins)) if wins else None
    # drop-best-day
    by_day = defaultdict(list)
    for t in matched:
        by_day[t["date"]].append(t["realized_pnl"])
    day_totals = {d: sum(v) for d, v in by_day.items()}
    if day_totals:
        best_day = max(day_totals, key=lambda d: day_totals[d])
        drop_best_total = total - day_totals[best_day]
        drop_best_n = n - len(by_day[best_day])
    else:
        best_day, drop_best_total, drop_best_n = None, None, None
    return {
        "n": n,
        "n_unmatched": len(trades) - n,
        "total_pnl": round(total, 2),
        "wr": round(wr, 4) if wr is not None else None,
        "n_win": len(wins), "n_loss": len(losses), "n_scratch": len(scratches),
        "pf": (round(pf, 3) if isinstance(pf, float) and pf != float("inf") else
               ("inf" if pf == float("inf") else None)),
        "mean_pnl": round(point, 2) if point is not None else None,
        "mean_pnl_ci95_lo": round(lo, 2) if lo is not None else None,
        "mean_pnl_ci95_hi": round(hi, 2) if hi is not None else None,
        "top3_gross_win_concentration": (round(top3_gross_win_concentration, 3)
                                          if top3_gross_win_concentration is not None else None),
        "top3_win_dollars": round(sum(top3), 2) if top3 else 0.0,
        "best_day": best_day,
        "best_day_pnl": round(day_totals[best_day], 2) if best_day else None,
        "drop_best_day_total_pnl": round(drop_best_total, 2) if drop_best_total is not None else None,
        "drop_best_day_n": drop_best_n,
        "n_days": len(day_totals),
    }


def gate_breakdown(trades, verdict_field="safe_verdict"):
    c = Counter()
    dollars = defaultdict(float)
    for t in trades:
        if not t.get("matched") or t.get("realized_pnl") is None:
            continue
        gate = t.get(verdict_field) or "UNKNOWN"
        c[gate] += 1
        dollars[gate] += t["realized_pnl"]
    return {g: {"n": n, "pnl": round(dollars[g], 2)} for g, n in c.most_common()}


def filter_trades(trades, pred):
    return [t for t in trades if pred(t)]


def main():
    out_json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "analysis/deep-research/2026-09-03-money/verify-fleet-gates-bypass-cohort-pnl-0-RERUN.json")

    core_idx, n_core_total, n_core_indexed = build_core_index()
    mae_meta, mae_lut = load_mae_mfe()
    cycles = build_fill_cycles_from_ledger()
    cycles_by_key = defaultdict(list)
    for c in cycles:
        cycles_by_key[(c["arm"], c["date"], c["symbol"])].append(c)

    all_joined = {}
    join_stats = {}
    for arm in FLEET_ARMS:
        rows, n_entry, n_joined, n_joined_fallback, n_skip = join_arm(
            arm, core_idx, mae_lut, cycles_by_key)
        all_joined[arm] = rows
        join_stats[arm] = {"n_entry_decisions": n_entry, "n_joined_to_pain_ledger": n_joined,
                            "n_joined_via_fills_ledger_fallback": n_joined_fallback,
                            "n_reentry_logs_skipped_placed_false": n_skip}

    report = {
        "generated_at_et": "2026-09-03T13:30",
        "core_decisions_total_rows": n_core_total,
        "core_decisions_rows_with_core_tick_id": n_core_indexed,
        "core_tick_id_first_seen_et": "2026-08-03T09:30:04",
        "join_stats": join_stats,
        "per_arm": {},
    }

    for arm in FLEET_ARMS:
        trades = all_joined[arm]
        cohort_a = filter_trades(trades, lambda t: t["cohort"] == "A_BYPASS")
        cohort_b = filter_trades(trades, lambda t: t["cohort"] == "B_BOTH_PASSED")
        cohort_c = filter_trades(trades, lambda t: t["cohort"] == "C_OTHER")
        cohort_unclass = filter_trades(trades, lambda t: t["cohort"].startswith("UNCLASSIFIED"))
        cohort_nonribbon = filter_trades(
            trades, lambda t: t["cohort"] == "NOT_APPLICABLE_NON_RIBBON_STRATEGY")

        arm_report = {
            "n_entry_decisions_total": len(trades),
            "cohort_A_bypass": cohort_stats(cohort_a),
            "cohort_A_bypass_gate_breakdown_safe_verdict": gate_breakdown(cohort_a, "safe_verdict"),
            "cohort_B_both_passed": cohort_stats(cohort_b),
            "cohort_C_other": cohort_stats(cohort_c),
            "cohort_C_other_examples": [
                {"date": t["date"], "symbol": t["symbol"], "setup": t["setup_name"],
                 "safe_verdict": t["safe_verdict"], "bold_verdict": t["bold_verdict"],
                 "pnl": t.get("realized_pnl")} for t in cohort_c[:8]
            ],
            "unclassified_no_core_tick": {
                "n": len(cohort_unclass),
                "total_pnl_if_matched": round(sum(
                    t["realized_pnl"] for t in cohort_unclass
                    if t.get("matched") and t.get("realized_pnl") is not None), 2),
                "date_range": sorted(set(t["date"] for t in cohort_unclass))[:3] + (
                    ["..."] if len(set(t["date"] for t in cohort_unclass)) > 6 else []
                ) + sorted(set(t["date"] for t in cohort_unclass))[-3:],
            },
            "non_ribbon_strategy_not_applicable": {
                "n": len(cohort_nonribbon),
                "setups": sorted(set(t["setup_name"] for t in cohort_nonribbon)),
                "total_pnl_if_matched": round(sum(
                    t["realized_pnl"] for t in cohort_nonribbon
                    if t.get("matched") and t.get("realized_pnl") is not None), 2),
                "note": "VWAP_CONTINUATION / VWAP_RECLAIM_FAILED_BREAK entries -- no safe/bold "
                        "role split exists for these setups in build_shared_signal.py; excluded "
                        "from cohort A/B/C, reported here only so no trade is silently dropped.",
            },
        }

        # VIX bands (cohort A vs B)
        vix_bands = {}
        for label, coh in (("A_bypass", cohort_a), ("B_both_passed", cohort_b)):
            band_groups = defaultdict(list)
            for t in coh:
                if t.get("matched") and t.get("realized_pnl") is not None:
                    band_groups[vix_band(t.get("vix"))].append(t)
            vix_bands[label] = {b: cohort_stats(v) for b, v in band_groups.items()}
        arm_report["vix_bands"] = vix_bands

        # Named winning days
        named_days = {}
        for label, coh in (("A_bypass", cohort_a), ("B_both_passed", cohort_b)):
            per_day = {}
            for d in NAMED_WINNING_DAYS:
                day_trades = [t for t in coh if t["date"] == d]
                per_day[d] = cohort_stats(day_trades)
            named_days[label] = per_day
        arm_report["named_winning_days"] = named_days

        # September window (2026-09-01..today)
        sept = {}
        for label, coh in (("A_bypass", cohort_a), ("B_both_passed", cohort_b), ("C_other", cohort_c)):
            sept_trades = [t for t in coh if t["date"] >= SEPT_START]
            sept[label] = cohort_stats(sept_trades)
            sept[label]["trade_list"] = [
                {"date": t["date"], "symbol": t["symbol"], "pnl": t.get("realized_pnl"),
                 "safe_verdict": t["safe_verdict"], "bold_verdict": t["bold_verdict"],
                 "safe_reason": t.get("safe_reason")}
                for t in sept_trades
            ]
        arm_report["september_window"] = sept

        report["per_arm"][arm] = arm_report

    # ---- Candidate costing ----
    # (a) KILL-TYPE: safe-role arms (safe-3, safe-1) drop cohort A entries only.
    safe_role_arms = ["safe-3", "safe-1"]
    risky_role_arms = ["risky-1", "risky-3"]

    def candidate_a_cost():
        removed_trades = []
        for arm in safe_role_arms:
            removed_trades += filter_trades(all_joined[arm], lambda t: t["cohort"] == "A_BYPASS")
        stats = cohort_stats(removed_trades)
        winners_removed = [t for t in removed_trades if t.get("matched") and (t.get("realized_pnl") or 0) > 0]
        losers_removed = [t for t in removed_trades if t.get("matched") and (t.get("realized_pnl") or 0) < 0]
        named_day_effect = {}
        for d in NAMED_WINNING_DAYS:
            dt = [t for t in removed_trades if t["date"] == d]
            named_day_effect[d] = cohort_stats(dt)
        today_effect = [t for t in removed_trades if t["date"] == "2026-09-03"]
        sept_effect = cohort_stats([t for t in removed_trades if t["date"] >= SEPT_START])
        return {
            "scope": safe_role_arms,
            "description": "Remove cohort-A (safe-gated, bold-passed) entries from safe-3 and "
                            "safe-1 only -- a KILL-TYPE reduction, can only remove trades.",
            "removed_trades_stats": stats,
            "winners_removed_n": len(winners_removed), "winners_removed_dollars": round(
                sum(t["realized_pnl"] for t in winners_removed), 2),
            "losers_removed_n": len(losers_removed), "losers_removed_dollars": round(
                sum(t["realized_pnl"] for t in losers_removed), 2),
            "named_winning_days_effect": named_day_effect,
            "today_2026_09_03_effect": [
                {"symbol": t["symbol"], "pnl": t.get("realized_pnl"), "matched": t.get("matched"),
                 "safe_verdict": t["safe_verdict"], "safe_reason": t.get("safe_reason")}
                for t in today_effect
            ],
            "september_window_effect": sept_effect,
        }

    def candidate_b_cost():
        # safe-role arms: same removal as (a).
        # risky-role arms: "own role's gates" = bold's perception only -> remove entries
        # where bold did NOT pass (mirror-direction bypass: bold-gated, safe-passed, i.e.
        # cohort C_OTHER rows where safe passed and bold did not -- see per-arm breakdown).
        removed_safe_role = []
        for arm in safe_role_arms:
            removed_safe_role += filter_trades(all_joined[arm], lambda t: t["cohort"] == "A_BYPASS")

        def bold_gated_safe_passed(t):
            return (t["cohort"] == "C_OTHER" and t.get("safe_verdict") == t.get("want_verdict")
                    and t.get("bold_verdict") != t.get("want_verdict"))

        removed_risky_role = []
        for arm in risky_role_arms:
            removed_risky_role += filter_trades(all_joined[arm], bold_gated_safe_passed)

        all_removed = removed_safe_role + removed_risky_role
        stats_all = cohort_stats(all_removed)
        stats_safe_role = cohort_stats(removed_safe_role)
        stats_risky_role = cohort_stats(removed_risky_role)
        named_day_effect = {}
        for d in NAMED_WINNING_DAYS:
            dt = [t for t in all_removed if t["date"] == d]
            named_day_effect[d] = cohort_stats(dt)
        today_effect = [t for t in all_removed if t["date"] == "2026-09-03"]
        sept_effect = cohort_stats([t for t in all_removed if t["date"] >= SEPT_START])
        return {
            "scope": FLEET_ARMS,
            "description": "Every fleet arm's entries reclassified against ONLY its own "
                            "sizing-role's core account (safe-3/safe-1 -> account=safe only; "
                            "risky-1/risky-3 -> account=bold only). Removes safe-role cohort-A "
                            "(same as candidate a) PLUS risky-role entries where bold's own "
                            "perception did not pass but safe's did (the mirror-direction case).",
            "removed_all_stats": stats_all,
            "removed_safe_role_stats": stats_safe_role,
            "removed_risky_role_stats": stats_risky_role,
            "removed_risky_role_gate_breakdown_bold_verdict": gate_breakdown(
                removed_risky_role, "bold_verdict"),
            "named_winning_days_effect": named_day_effect,
            "today_2026_09_03_effect": [
                {"arm": t["arm"], "symbol": t["symbol"], "pnl": t.get("realized_pnl"),
                 "matched": t.get("matched"), "safe_verdict": t["safe_verdict"],
                 "bold_verdict": t["bold_verdict"]}
                for t in today_effect
            ],
            "september_window_effect": sept_effect,
        }

    report["candidate_a_safe_role_only"] = candidate_a_cost()
    report["candidate_b_all_arms_own_role"] = candidate_b_cost()

    # Overall population-level verdict inputs
    overall_a = []
    overall_b = []
    for arm in FLEET_ARMS:
        overall_a += filter_trades(all_joined[arm], lambda t: t["cohort"] == "A_BYPASS")
        overall_b += filter_trades(all_joined[arm], lambda t: t["cohort"] == "B_BOTH_PASSED")
    report["population_overall"] = {
        "cohort_A_bypass_all_arms": cohort_stats(overall_a),
        "cohort_B_both_passed_all_arms": cohort_stats(overall_b),
    }
    safe3_a = filter_trades(all_joined["safe-3"], lambda t: t["cohort"] == "A_BYPASS")
    safe3_b = filter_trades(all_joined["safe-3"], lambda t: t["cohort"] == "B_BOTH_PASSED")
    report["safe3_only"] = {
        "cohort_A_bypass": cohort_stats(safe3_a),
        "cohort_B_both_passed": cohort_stats(safe3_b),
        "cohort_A_september": cohort_stats([t for t in safe3_a if t["date"] >= SEPT_START]),
    }

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"WROTE {out_json_path}")
    print(json.dumps(report["join_stats"], indent=2))
    print("population_overall:", json.dumps(report["population_overall"], indent=2))
    print("safe3_only:", json.dumps(report["safe3_only"], indent=2))


if __name__ == "__main__":
    main()
