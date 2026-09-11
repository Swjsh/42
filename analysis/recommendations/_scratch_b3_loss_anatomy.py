"""B3 — THE $3,000 LOSS: concrete risk at each account size. READ-ONLY analysis.

Writes ONLY to analysis/recommendations/B3-loss-anatomy-2026-08-28.json.
Touches nothing the live engine reads.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "analysis" / "trades-enriched.jsonl"
OUT = ROOT / "analysis" / "recommendations" / "B3-loss-anatomy-2026-08-28.json"

ACTIVE = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
START_EQ = 5000.0
AUG_START, AUG_END = "2026-08-03", "2026-08-27"

rows = []
for line in LEDGER.open(encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if r.get("_meta"):
        continue
    rows.append(r)

act = [r for r in rows if r["arm"] in ACTIVE]
aug = [r for r in act if AUG_START <= r["date"] <= AUG_END]
full = act  # full available history for the 5 active arms

out: dict = {
    "_doc": "B3 loss anatomy — worst-case + probabilistic $3K exposure at each equity size. READ-ONLY.",
    "generated_at_utc": "2026-08-28",
    "source_ledger": "analysis/trades-enriched.jsonl",
    "n_rows_all_arms": len(rows),
    "n_rows_active_arms": len(act),
    "n_rows_august": len(aug),
    "window_august": [AUG_START, AUG_END],
}


def daily_by_arm(rs):
    d = defaultdict(lambda: defaultdict(float))
    for r in rs:
        d[r["arm"]][r["date"]] += float(r["pnl_dollars"])
    return d


def book_daily(rs):
    d = defaultdict(float)
    for r in rs:
        d[r["date"]] += float(r["pnl_dollars"])
    return d


def series(rs):
    """Return (dates, per-arm pct series aligned on the union of trading dates, book pct)."""
    dba = daily_by_arm(rs)
    dates = sorted({r["date"] for r in rs})
    per_arm = {a: [dba[a].get(d, 0.0) for d in dates] for a in ACTIVE}
    bk = book_daily(rs)
    book = [bk.get(d, 0.0) for d in dates]
    return dates, per_arm, book


# ---------------------------------------------------------------- part A: observed
def describe(vals, base):
    pct = [v / base for v in vals]
    s = sorted(vals)
    return {
        "n_days": len(vals),
        "sum_dollars": round(sum(vals), 2),
        "worst_day_dollars": round(s[0], 2),
        "worst_day_pct_of_base": round(100 * s[0] / base, 3),
        "best_day_dollars": round(s[-1], 2),
        "mean_pct": round(100 * st.mean(pct), 4),
        "sd_pct": round(100 * st.pstdev(pct), 4),
        "median_pct": round(100 * st.median(pct), 4),
    }


def worst_window(vals, w):
    if len(vals) < w:
        return None
    best = min(sum(vals[i : i + w]) for i in range(len(vals) - w + 1))
    idx = min(range(len(vals) - w + 1), key=lambda i: sum(vals[i : i + w]))
    return best, idx


def max_dd(vals):
    eq, peak, mdd = 0.0, 0.0, 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return mdd


for label, rs in (("august_19d", aug), ("full_history", full)):
    dates, per_arm, book = series(rs)
    blk = {"dates": [dates[0], dates[-1]], "n_trading_days": len(dates), "arms": {}}
    for a in ACTIVE:
        v = per_arm[a]
        e = describe(v, START_EQ)
        for w in (5, 10, 21):
            ww = worst_window(v, w)
            if ww:
                e[f"worst_{w}d_dollars"] = round(ww[0], 2)
                e[f"worst_{w}d_window"] = [dates[ww[1]], dates[ww[1] + w - 1]]
        e["max_drawdown_dollars"] = round(max_dd(v), 2)
        blk["arms"][a] = e
    e = describe(book, START_EQ * len(ACTIVE))
    for w in (5, 10, 21):
        ww = worst_window(book, w)
        if ww:
            e[f"worst_{w}d_dollars"] = round(ww[0], 2)
            e[f"worst_{w}d_window"] = [dates[ww[1]], dates[ww[1] + w - 1]]
    e["max_drawdown_dollars"] = round(max_dd(book), 2)
    blk["book"] = e
    out[f"observed_{label}"] = blk

# ---------------------------------------------------- part B: how big are actual bets?
notional = defaultdict(list)
for r in act:
    c = float(r.get("cost_dollars") or 0.0)
    if c > 0:
        notional[r["arm"]].append(c)
allc = [c for v in notional.values() for c in v]
out["actual_deployed_premium_per_trade"] = {
    "n_trades": len(allc),
    "mean_dollars": round(st.mean(allc), 2),
    "median_dollars": round(st.median(allc), 2),
    "p90_dollars": round(sorted(allc)[int(0.90 * len(allc))], 2),
    "max_dollars": round(max(allc), 2),
    "mean_pct_of_5k": round(100 * st.mean(allc) / START_EQ, 2),
    "max_pct_of_5k": round(100 * max(allc) / START_EQ, 2),
    "per_arm_max_dollars": {a: round(max(v), 2) for a, v in notional.items()},
}

# worst single trade + worst realized per-trade loss
losses = sorted(((float(r["pnl_dollars"]), i, r) for i, r in enumerate(act)), key=lambda t: t[0])
out["worst_single_trades"] = [
    {
        "date": r["date"],
        "arm": r["arm"],
        "symbol": r["symbol"],
        "qty": r["qty"],
        "cost_dollars": r.get("cost_dollars"),
        "pnl_dollars": p,
        "ret_pct_of_premium": r.get("ret_pct_of_premium"),
        "exit_reason": r.get("exit_reason"),
    }
    for p, _i, r in losses[:8]
]

# same-day concurrency: how many arms traded same date+direction
byday = defaultdict(list)
for r in act:
    byday[r["date"]].append(r)
conc = []
for d, rs_ in byday.items():
    arms_ = {x["arm"] for x in rs_}
    cost = sum(float(x.get("cost_dollars") or 0) for x in rs_)
    pnl = sum(float(x["pnl_dollars"]) for x in rs_)
    conc.append({"date": d, "n_arms": len(arms_), "total_premium_deployed": round(cost, 2), "pnl": round(pnl, 2)})
conc.sort(key=lambda x: -x["total_premium_deployed"])
out["highest_book_premium_days"] = conc[:6]

# --------------------------------------------- part C: mechanical worst case under rules
def _cap_frac(eq, risk_cap, tier_table):
    c = risk_cap
    if tier_table:
        for row in tier_table:
            if row["equity_min"] <= eq < row["equity_max"]:
                c = min(c, row["max_pct"])
                break
    return c


def mech(sod, risk_cap, kill_pct, tier_table, max_trips, label, loss_frac=1.0):
    """WORST realized session under the CURRENT rules.

    The kill switch is a PRE-ENTRY gate (risk_gate.check_order rule 1): it denies a
    NEW order once equity <= sod*(1-kill_pct). It cannot stop a position already open,
    and the per-trade cap is a % of CURRENT equity. So the worst session is:
      lose small trades until equity sits just ABOVE the kill floor, then take one
      more max-size entry and lose `loss_frac` of it.
    Floor equity = sod*(1-kill_pct) + eps; last entry = cap_frac * floor.
    """
    floor = sod * (1.0 - kill_pct)
    c = _cap_frac(floor, risk_cap, tier_table)
    final = floor - floor * c * loss_frac
    loss = sod - final
    return {
        "label": label,
        "sod_equity": sod,
        "loss_frac_per_trade_assumed": loss_frac,
        "nominal_kill_switch_dollars": round(sod * kill_pct, 2),
        "kill_floor_equity": round(floor, 2),
        "last_allowed_entry_dollars": round(floor * c, 2),
        "worst_realized_day_loss_dollars": round(loss, 2),
        "worst_realized_day_loss_pct_of_sod": round(100 * loss / sod, 2),
        "overshoot_vs_kill_switch_dollars": round(loss - sod * kill_pct, 2),
        "max_entries_per_day_param": max_trips,
    }


SAFE_TIERS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))[
    "v15_max_premium_pct_of_account"
]
out["_safe_tier_table_verbatim"] = SAFE_TIERS

mech_rows = []
for eqv in (5000, 10000, 25000, 50000):
    for lf, tag in ((0.50, "cap holds (-50% catastrophe cap)"), (1.00, "cap FAILS (gap/orphan/expiry -> -100%)")):
        mech_rows.append(mech(eqv, 0.30, 0.30, SAFE_TIERS, 5, f"SAFE arm @ ${eqv:,} | {tag}", lf))
        mech_rows.append(mech(eqv, 0.50, 0.50, None, 5, f"BOLD arm @ ${eqv:,} | {tag} | NO v15 tier table in aggressive/params.json", lf))
out["mechanical_worst_case_single_session"] = mech_rows

# what the WHOLE 5-arm book can lose in ONE session under current rules
book_rows = []
for per_arm_eq in (5000, 10000, 25000, 50000):
    for lf in (0.50, 1.00):
        # 2 SAFE-configured arms (safe-2, safe-3) + 3 BOLD-configured (bold-2, risky-1, risky-3)
        s = mech(per_arm_eq, 0.30, 0.30, SAFE_TIERS, 5, "", lf)["worst_realized_day_loss_dollars"]
        b = mech(per_arm_eq, 0.50, 0.50, None, 5, "", lf)["worst_realized_day_loss_dollars"]
        book_rows.append({
            "per_arm_equity": per_arm_eq,
            "book_equity": per_arm_eq * 5,
            "loss_frac_assumed": lf,
            "book_worst_session_dollars": round(2 * s + 3 * b, 2),
            "book_worst_session_pct": round(100 * (2 * s + 3 * b) / (per_arm_eq * 5), 2),
            "composition": "2 arms on Safe params (30/30) + 3 arms on Bold params (50/50)",
        })
out["book_mechanical_worst_case_single_session"] = book_rows

# book-level: book_exposure_cap_pct 0.25 of aggregate equity, all concurrent -> 0
out["book_exposure_cap_worst_case"] = {
    "book_exposure_cap_pct": 0.25,
    "note": "Cap on AGGREGATE open premium across active SPY arms at one instant (params.json). "
            "A single simultaneous 100%-loss of a fully-capped book is this dollar figure.",
    "by_book_equity": {
        f"${e:,}": round(e * 0.25, 2) for e in (25000, 50000, 100000, 125000, 250000)
    },
}

# ------------------------------------------------- part D: probability of a $3K loss
def boot_month(daily_pct, base, n_days=21, trials=20000, seed=42):
    """Resample observed daily %-returns into synthetic 21-trading-day months."""
    rnd = random.Random(seed)
    hits_sum, hits_dd, sums, dds = 0, 0, [], []
    for _ in range(trials):
        eq, peak, mdd, tot = base, base, 0.0, 0.0
        for _ in range(n_days):
            r = rnd.choice(daily_pct)
            pnl = eq * r
            eq += pnl
            tot += pnl
            peak = max(peak, eq)
            mdd = max(mdd, peak - eq)
        sums.append(tot)
        dds.append(mdd)
        if tot <= -3000:
            hits_sum += 1
        if mdd >= 3000:
            hits_dd += 1
    sums.sort()
    dds.sort()
    return {
        "p_month_total_loss_ge_3000": round(hits_sum / trials, 4),
        "p_month_drawdown_ge_3000": round(hits_dd / trials, 4),
        "month_total_p05": round(sums[int(0.05 * trials)], 2),
        "month_total_p50": round(sums[int(0.50 * trials)], 2),
        "month_total_p95": round(sums[int(0.95 * trials)], 2),
        "month_maxdd_p50": round(dds[int(0.50 * trials)], 2),
        "month_maxdd_p90": round(dds[int(0.90 * trials)], 2),
    }


# tier haircut: engine size is capped as a % of equity, and the SAFE tier % SHRINKS with
# equity. Observed returns were generated in the 30% band ($2K-$10K). Scaling to a higher
# equity band multiplies returns by (band_pct / 0.30).
def band_pct(eq):
    for row in SAFE_TIERS:
        if row["equity_min"] <= eq < row["equity_max"]:
            return row["max_pct"]
    return None


prob = {}
for label, rs in (("august_19d", aug), ("full_history", full)):
    dates, per_arm, book = series(rs)
    blk = {}
    for name, vals, base0 in (
        ("safe-2", per_arm["safe-2"], START_EQ),
        ("bold-2", per_arm["bold-2"], START_EQ),
        ("risky-1", per_arm["risky-1"], START_EQ),
        ("BOOK_5arms", book, START_EQ * 5),
    ):
        pct = [v / base0 for v in vals]
        sub = {}
        for eqv in (5000, 10000, 25000, 50000):
            hair = (band_pct(eqv) or 0.30) / 0.30 if name != "BOOK_5arms" else 1.0
            scaled = [p * hair for p in pct]
            r = boot_month(scaled, eqv)
            r["tier_haircut_applied"] = round(hair, 4)
            sub[f"${eqv:,}"] = r
        blk[name] = sub
    prob[label] = blk
out["prob_3k_loss_per_month"] = prob
out["_prob_method"] = (
    "20,000 bootstrap resamples of the arm's OWN observed daily %-of-equity returns into "
    "synthetic 21-trading-day months. Two separate questions reported: "
    "(a) p_month_total_loss_ge_3000 = the month CLOSES >= $3,000 down; "
    "(b) p_month_drawdown_ge_3000 = at some point inside the month the account is >= $3,000 "
    "below its running peak (this is what an operator SEES and panics at). "
    "iid-day assumption; n=19 (august) / n=41 (full) source days -- small, disclosed per C4. "
    "tier_haircut scales returns by the SAFE v15 max-premium band at that equity "
    "(30% under $10K, 25% $10-25K, 20% $25K+), since bet size is a %-of-equity cap."
)

# ------------------------------------------------- part E: the SAFE configuration
def bounded(eq, per_trade_pct, daily_stop_pct, max_conc, max_trips):
    """Hard arithmetic bound on the worst possible session."""
    # adversarial: repeatedly lose 100% of max size until the daily stop denies
    e = eq
    n = 0
    while n < max_trips and e > eq * (1 - daily_stop_pct):
        e -= min(e * per_trade_pct, eq * per_trade_pct)
        n += 1
    single_day = eq - e
    # concurrent variant: max_conc positions open at once, all go to zero
    conc_loss = min(max_conc * eq * per_trade_pct, eq)
    return {
        "equity": eq,
        "per_trade_risk_pct": per_trade_pct,
        "daily_stop_pct": daily_stop_pct,
        "max_concurrent": max_conc,
        "max_entries_per_day": max_trips,
        "worst_sequential_day_dollars": round(single_day, 2),
        "worst_concurrent_instant_dollars": round(conc_loss, 2),
        "worst_session_dollars": round(max(single_day, conc_loss), 2),
    }


safe_cfg = []
for eqv in (5000, 10000, 25000, 50000):
    for ptp, dsp, mc, mt in ((0.02, 0.04, 2, 3), (0.03, 0.06, 2, 3), (0.04, 0.08, 2, 3)):
        safe_cfg.append(bounded(eqv, ptp, dsp, mc, mt))
out["bounded_configurations"] = safe_cfg

OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"WROTE {OUT}")
print(json.dumps({k: v for k, v in out.items() if k.startswith("observed")}, indent=1)[:4000])
