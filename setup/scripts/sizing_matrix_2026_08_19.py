#!/usr/bin/env python
"""sizing_matrix_2026_08_19.py -- POSITION-SIZING COUNTERFACTUAL MATRIX over every closed
round trip Project Gamma has ever taken (303 rows, 5 arms, 2026-06-26..2026-08-19).

THE QUESTION (J, BIGGER-WINNERS lane): would ANY other sizing rule -- flat, equity-scaled,
volatility-scaled, conviction-scaled -- have made more money on the SAME trades? Sizing cannot
change which trades happened or whether each one won; it only changes the DOLLAR WEIGHT on
each. So this is purely a question about whether information available AT ENTRY correlates
with per-contract P&L.

PREMISE CORRECTION (measured here, 2026-08-19): the lane brief said "every arm uses a flat
min_contracts". That is true only for the two CORE arms (safe-2, bold-2 -> heartbeat_core,
flat min_contracts 3 and 5). The three FLEET arms (safe-3, risky-1, risky-3) already run an
EQUITY-TIERED + CONVICTION ladder -- params.json#position_sizing_tiers (safe: base 5 / elite 8
in the $2K-$10K tier; risky: base 8 / elite 12) -- with min_contracts applied as a CEILING
only when fleet_executor._apply_recency_min_sizing sees a RED recency verdict. Equity-scaled
and conviction-scaled sizing are therefore NOT hypothetical here: they are ARMED, and this
matrix is scoring an existing system, not proposing a new one.

WHAT IS AND IS NOT ASSUMED
  * Resizing assumes fills at the SAME prices (linear fill). Defensible at 1-12 contracts on
    SPY 0DTE; every cell reports max single-trade contracts so an implausible cell is visible.
  * Exit staging is preserved: each original exit leg's share of qty is re-allocated to the new
    qty by LARGEST REMAINDER. Legs that round to 0 are dropped (unavoidable at qty 1-2); the
    affected-row count is reported per cell. Measured artifact size: multi-leg gross/contract
    moves only $37.21-$38.66 across flat sizes 1..20, and single-leg gross/contract is exactly
    invariant, so the rounding is worth <=$1.5/contract at the extremes and ~$0 from qty 3 up.
  * Fees are RECOMPUTED at the new size from cost_model.py's empirical rates (OCC/ORF/TAF/SEC).
    The SAME formula prices the production cell, so the comparison is apples-to-apples.
  * Exit slippage is RECOMPUTED at the new size: 0.129 x (exit-minute traded range) x contracts
    x 100 -- the measured one-sided exit optimism (exit_fill_realism.py).
  * Rule 6 is enforced in EVERY cell: premium x qty x 100 <= cap x equity (30% safe-2/safe-3,
    50% bold-2/risky-1/risky-3). Clamps are counted per cell.
  * Equity is PATH-SIMULATED per arm: equity_cf = equity_actual + (cum_cf_net - cum_prod_net)
    since the last capital injection. The 2026-08-03/04 re-funding of all 5 arms to $5,000 is
    EXOGENOUS and resets that delta to zero.
  * NO LOOK-AHEAD (C6): every sizing input (equity, VIX, score, tier, premium, clock, prior
    realized P&L) is known at the entry timestamp. Nothing reads the outcome.

$0, stdlib + the trade matrix. Deterministic apart from seeded resampling.
Run: backtest/.venv/Scripts/python.exe setup/scripts/sizing_matrix_2026_08_19.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "sizing-matrix-2026-08-19.json"

# --- cost constants, verbatim from setup/scripts/cost_model.py ----------------
OCC = 0.025
ORF = 0.015
TAF = 0.00329
SEC_RATE = 20.60 / 1_000_000.0
EXIT_SLIP_RANGE_FRAC = 0.129     # measured; exit_fill_realism.py

RULE6_CAP = {"safe-2": 0.30, "safe-3": 0.30, "bold-2": 0.50, "risky-1": 0.50, "risky-3": 0.50}
# min_contracts per arm (params.json / aggressive params.json). Flat reference point.
MINCON = {"safe-2": 3, "safe-3": 3, "bold-2": 5, "risky-1": 5, "risky-3": 5}
MAX_QTY_HARD = 60
REFUND_DATE = "2026-08-03"
BOOT_TRIALS = 2000
PERM_TRIALS = 1000


def ceil_cent(x: float) -> float:
    return math.ceil(round(x, 10) * 100 - 1e-9) / 100.0


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts)


# ============================================================================
# ROW PREP
# ============================================================================

def prep(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        base = parse(r["path_first_bar_et"]) if r.get("path_first_bar_et") else None
        bars = {int(b[0]): b for b in (r.get("path") or [])}
        legs = []
        for leg in r["exit_legs"]:
            rng = None
            if base is not None:
                off = int((parse(leg["ts_et"]) - base).total_seconds() // 60)
                b = bars.get(off)
                if b is not None:
                    rng = float(b[2]) - float(b[3])
            legs.append({"qty": int(leg["qty"]), "price": float(leg["price"]), "range": rng})
        side = r["side"]
        out.append({
            "arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "side": side,
            "entry_ts": parse(r["entry_ts_et"]), "exit_ts": parse(r["exit_ts_et"]),
            "premium": float(r["entry_premium"]), "qty": int(r["qty"]),
            "equity_actual": float(r["equity_at_entry"]),
            "vix": float(r["vix"]),
            "score": float(r["bull_score"]) if side == "C" else float(r["bear_score"]),
            "tier": r.get("quality_tier"), "setup": r["setup"],
            "mso": float(r["minutes_since_open"]),
            "n_entry_legs": int(r["n_entry_legs"]),
            "legs": legs,
            "gross_ledger": float(r["real_pnl_gross"]),
            "_cache": {},
        })
    out.sort(key=lambda x: (x["entry_ts"], x["arm"]))
    return out


def allocate(total: int, legs: list[dict], orig_qty: int) -> list[int]:
    if len(legs) == 1:
        return [total]
    raw = [total * l["qty"] / orig_qty for l in legs]
    floors = [int(math.floor(x)) for x in raw]
    rem = total - sum(floors)
    order = sorted(range(len(legs)), key=lambda i: (-(raw[i] - floors[i]), -legs[i]["qty"]))
    for i in range(rem):
        floors[order[i % len(order)]] += 1
    return floors


def economics(row: dict, qty: int) -> dict:
    hit = row["_cache"].get(qty)
    if hit is not None:
        return hit
    alloc = allocate(qty, row["legs"], row["qty"])
    gross = proceeds = 0.0
    occ_x = orf_x = taf = slip = 0.0
    dropped = slip_missing = 0
    for l, q in zip(row["legs"], alloc):
        if q <= 0:
            dropped += 1
            continue
        gross += (l["price"] - row["premium"]) * q * 100.0
        proceeds += l["price"] * q * 100.0
        occ_x += ceil_cent(OCC * q)
        orf_x += ceil_cent(ORF * q)
        taf += ceil_cent(TAF * q)
        if l["range"] is None:
            slip_missing += 1
        else:
            slip += EXIT_SLIP_RANGE_FRAC * l["range"] * q * 100.0
    fees = (ceil_cent(OCC * qty) + ceil_cent(ORF * qty) + occ_x + orf_x + taf
            + ceil_cent(SEC_RATE * proceeds))
    res = {"gross": gross, "fees": fees, "slip": slip,
           "net": gross - fees, "net_slip": gross - fees - slip,
           "dropped_legs": dropped, "slip_missing_legs": slip_missing,
           "notional": row["premium"] * qty * 100.0}
    row["_cache"][qty] = res
    return res


# ============================================================================
# SIZING SCHEMES -- every input is known at the entry timestamp
# ============================================================================

def _clip(x, lo, hi):
    return max(lo, min(hi, x))


class State:
    def __init__(self) -> None:
        self.vix_hist: list[float] = []
        self.arm_day_net: dict[tuple, float] = defaultdict(float)
        self.arm_days: dict[str, list[str]] = defaultdict(list)

    def vix_ref(self) -> float:
        return statistics.median(self.vix_hist) if len(self.vix_hist) >= 10 else 18.0

    def prior_day_net(self, arm: str, date: str) -> float | None:
        days = [d for d in self.arm_days[arm] if d < date]
        return self.arm_day_net[(arm, days[-1])] if days else None


def scheme_production(row, st):
    return row["qty"]


def scheme_mincon(row, st):
    return MINCON[row["arm"]]


def mk_mincon_mult(m):
    return lambda row, st: max(1, int(round(MINCON[row["arm"]] * m)))


def mk_flat(n):
    return lambda row, st: n


def mk_equity(frac):
    def f(row, st):
        return max(1, int(math.floor(frac * row["_equity_cf"] / (row["premium"] * 100.0))))
    return f


def scheme_vol_inv(row, st):
    return max(1, int(round(MINCON[row["arm"]] * _clip(st.vix_ref() / row["vix"], 0.5, 2.0))))


def scheme_vol_dir(row, st):
    return max(1, int(round(MINCON[row["arm"]] * _clip(row["vix"] / st.vix_ref(), 0.5, 2.0))))


def _conv_mult(score):
    return 2.0 if score >= 10.0 else (1.0 if score >= 8.0 else 0.5)


def scheme_conv(row, st):
    return max(1, int(round(MINCON[row["arm"]] * _conv_mult(row["score"]))))


def scheme_conv_inv(row, st):
    return max(1, int(round(MINCON[row["arm"]] / _conv_mult(row["score"]))))


_TIER_M = {"SUPER": 2.0, "ELITE": 1.5, "TRENDLINE": 1.0, "LEVEL": 1.0, "BASE": 0.5, None: 1.0}


def scheme_tier(row, st):
    return max(1, int(round(MINCON[row["arm"]] * _TIER_M.get(row["tier"], 1.0))))


def scheme_tier_inv(row, st):
    return max(1, int(round(MINCON[row["arm"]] / _TIER_M.get(row["tier"], 1.0))))


def scheme_cheap(row, st):
    return MINCON[row["arm"]] * (2 if row["premium"] < 0.50 else 1)


def scheme_rich(row, st):
    b = MINCON[row["arm"]]
    return b * 2 if row["premium"] >= 0.50 else max(1, b // 2)


def scheme_early(row, st):
    return MINCON[row["arm"]] * (2 if row["mso"] <= 60 else 1)


def scheme_late(row, st):
    return MINCON[row["arm"]] * (2 if row["mso"] > 60 else 1)


def scheme_recency_down(row, st):
    p = st.prior_day_net(row["arm"], row["date"])
    b = MINCON[row["arm"]]
    return b if p is None else (max(1, b // 2) if p < 0 else b)


def scheme_recency_up(row, st):
    p = st.prior_day_net(row["arm"], row["date"])
    b = MINCON[row["arm"]]
    return b if p is None else (b * 2 if p < 0 else b)


SCHEMES: list[tuple[str, str, str, Callable]] = [
    # name, family, description, fn
    ("PRODUCTION", "reference", "as traded: core flat min_contracts + fleet equity/elite ladder + risky-3 cheap boost", scheme_production),
    ("MINCON-FLAT", "reference", "every arm flat at its own min_contracts (3/3/5/5/5) -- the clamp-always baseline", scheme_mincon),
    ("MINCON-FLAT-2X", "reference", "min_contracts x2 -- pure-leverage control for every x2 tilt below", mk_mincon_mult(2.0)),
    ("FLAT-1", "leverage", "1 contract, every trade, every arm", mk_flat(1)),
    ("FLAT-2", "leverage", "2 contracts", mk_flat(2)),
    ("FLAT-3", "leverage", "3 contracts", mk_flat(3)),
    ("FLAT-5", "leverage", "5 contracts", mk_flat(5)),
    ("FLAT-8", "leverage", "8 contracts", mk_flat(8)),
    ("FLAT-10", "leverage", "10 contracts", mk_flat(10)),
    ("EQUITY-2%", "equity", "qty = 2% of live equity / notional (constant-dollar risk)", mk_equity(0.02)),
    ("EQUITY-5%", "equity", "qty = 5% of live equity / notional", mk_equity(0.05)),
    ("EQUITY-10%", "equity", "qty = 10% of live equity / notional", mk_equity(0.10)),
    ("EQUITY-20%", "equity", "qty = 20% of live equity / notional", mk_equity(0.20)),
    ("EQUITY-30%", "equity", "qty = 30% of live equity / notional", mk_equity(0.30)),
    ("EQUITY-50%", "equity", "qty = 50% of live equity / notional (Rule 6 ceiling, bold/risky)", mk_equity(0.50)),
    ("VOL-INV-VIX", "volatility", "min_contracts x clip(median-VIX-so-far / VIX, 0.5, 2)", scheme_vol_inv),
    ("VOL-DIR-VIX", "volatility", "min_contracts x clip(VIX / median-VIX-so-far, 0.5, 2)", scheme_vol_dir),
    ("CONV-SCORE", "conviction", "x2 if score>=10, x1 if 8-9, x0.5 if <8", scheme_conv),
    ("CONV-SCORE-INV", "conviction", "inverse of CONV-SCORE (bigger on WEAK signals)", scheme_conv_inv),
    ("CONV-TIER", "conviction", "x tier multiplier (SUPER 2, ELITE 1.5, BASE 0.5)", scheme_tier),
    ("CONV-TIER-INV", "conviction", "inverse of CONV-TIER", scheme_tier_inv),
    ("CHEAP-BOOST", "premium", "x2 when entry premium < $0.50 (risky-3's live boost, book-wide)", scheme_cheap),
    ("RICH-BOOST", "premium", "x2 when premium >= $0.50, half when cheap", scheme_rich),
    ("EARLY-BOOST", "clock", "x2 in the first 60 min after the open", scheme_early),
    ("LATE-BOOST", "clock", "x2 after the first 60 min", scheme_late),
    ("RECENCY-DOWN", "recency", "half size after the arm's prior trading day was red", scheme_recency_down),
    ("RECENCY-UP", "recency", "double size after a red day (C31 anti-pattern, priced for completeness)", scheme_recency_up),
]
SCHEME_FN = {n: f for n, _, _, f in SCHEMES}
SCHEME_FAM = {n: fam for n, fam, _, _ in SCHEMES}


# ============================================================================
# RUNNER
# ============================================================================

def run_scheme(rows: list[dict], fn: Callable) -> dict:
    st = State()
    delta = defaultdict(float)
    last_eq: dict[str, float] = {}
    injections: list[dict] = []
    per_trade: list[dict] = []
    clamps = clamp_to_zero = dropped_leg_rows = slip_missing = hard_hits = 0
    for row in rows:
        arm = row["arm"]
        prev = last_eq.get(arm)
        if prev is not None and row["equity_actual"] - prev > 1000.0:
            delta[arm] = 0.0
            injections.append({"arm": arm, "date": row["date"],
                               "equity_before": round(prev, 2),
                               "equity_after": round(row["equity_actual"], 2)})
        last_eq[arm] = row["equity_actual"]
        eq_cf = max(0.0, row["equity_actual"] + delta[arm])
        row["_equity_cf"] = eq_cf

        want = max(0, int(fn(row, st)))
        if want > MAX_QTY_HARD:
            want = MAX_QTY_HARD
            hard_hits += 1
        max_q = int(math.floor((RULE6_CAP[arm] * eq_cf) / (row["premium"] * 100.0) + 1e-9))
        qty = min(want, max_q)
        if qty < want:
            clamps += 1
        st.vix_hist.append(row["vix"])
        d = row["date"]
        if d not in st.arm_days[arm]:
            st.arm_days[arm].append(d)
        if qty <= 0:
            clamp_to_zero += 1
            per_trade.append({"row": row, "qty": 0, "econ": None, "equity_cf": eq_cf})
            continue
        e = economics(row, qty)
        if e["dropped_legs"]:
            dropped_leg_rows += 1
        slip_missing += e["slip_missing_legs"]
        delta[arm] += e["net_slip"] - economics(row, row["qty"])["net_slip"]
        st.arm_day_net[(arm, d)] += e["net_slip"]
        per_trade.append({"row": row, "qty": qty, "econ": e, "equity_cf": eq_cf})
    return {"per_trade": per_trade, "clamps": clamps, "clamp_to_zero": clamp_to_zero,
            "dropped_leg_rows": dropped_leg_rows, "slip_missing_legs": slip_missing,
            "injections": injections, "hard_ceiling_hits": hard_hits}


def _key(p) -> tuple:
    return (p["row"]["arm"], p["row"]["symbol"], p["row"]["entry_ts"].isoformat())


def summarise(res: dict, baselines: dict[str, dict]) -> dict:
    pts = res["per_trade"]
    taken = [p for p in pts if p["qty"] > 0]
    gross = sum(p["econ"]["gross"] for p in taken)
    fees = sum(p["econ"]["fees"] for p in taken)
    slip = sum(p["econ"]["slip"] for p in taken)
    net_slip = gross - fees - slip
    contracts = sum(p["qty"] for p in taken)
    wins = [p for p in taken if p["econ"]["net_slip"] > 0]
    losses = [p for p in taken if p["econ"]["net_slip"] <= 0]

    seq = sorted(taken, key=lambda p: p["row"]["exit_ts"])
    cum = peak = mdd = 0.0
    for p in seq:
        cum += p["econ"]["net_slip"]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    by_day = defaultdict(float)
    for p in taken:
        by_day[p["row"]["date"]] += p["econ"]["net_slip"]

    out = {
        "n_taken": len(taken), "n_skipped_rule6": res["clamp_to_zero"], "contracts": contracts,
        "gross": round(gross, 2), "fees": round(fees, 2), "exit_slippage": round(slip, 2),
        "net_of_fees": round(gross - fees, 2), "net_after_costs": round(net_slip, 2),
        "gross_per_contract": round(gross / contracts, 4) if contracts else None,
        "net_after_costs_per_contract": round(net_slip / contracts, 4) if contracts else None,
        "win_rate_net": round(100.0 * len(wins) / len(taken), 2) if taken else None,
        "win_rate_gross": round(100.0 * len([p for p in taken if p["econ"]["gross"] > 0]) / len(taken), 2) if taken else None,
        "avg_win": round(statistics.fmean([p["econ"]["net_slip"] for p in wins]), 2) if wins else None,
        "avg_loss": round(statistics.fmean([p["econ"]["net_slip"] for p in losses]), 2) if losses else None,
        "max_drawdown": round(mdd, 2),
        "worst_day": round(min(by_day.values()), 2) if by_day else 0.0,
        "best_day": round(max(by_day.values()), 2) if by_day else 0.0,
        "max_contracts_single_trade": max((p["qty"] for p in taken), default=0),
        "max_notional_pct_equity": round(max(
            (p["econ"]["notional"] / p["equity_cf"] for p in taken if p["equity_cf"] > 0), default=0.0), 4),
        "rule6_clamps": res["clamps"],
        "rows_with_dropped_exit_leg": res["dropped_leg_rows"],
        "hard_ceiling_hits": res["hard_ceiling_hits"],
        "exit_legs_without_bar": res["slip_missing_legs"],
    }
    for label, base in baselines.items():
        deltas = {}
        idx = {_key(p): p for p in pts}
        for p in pts:
            mine = p["econ"]["net_slip"] if p["qty"] > 0 else 0.0
            deltas[_key(p)] = mine - base.get(_key(p), 0.0)
        tot = sum(deltas.values())
        blk = {"delta_net_after_costs": round(tot, 2)}
        by_day_d = defaultdict(float)
        for k, v in deltas.items():
            by_day_d[idx[k]["row"]["date"]] += v
        if abs(tot) > 1e-9:
            top_day = max(by_day_d.items(), key=lambda kv: abs(kv[1]))
            top_tr = max(deltas.items(), key=lambda kv: abs(kv[1]))
            r = idx[top_tr[0]]["row"]
            blk.update({
                "top_day": top_day[0], "top_day_value": round(top_day[1], 2),
                "top_day_share": round(top_day[1] / tot, 4),
                "top_trade": f"{r['arm']} {r['date']} {r['symbol']}",
                "top_trade_value": round(top_tr[1], 2),
                "top_trade_share": round(top_tr[1] / tot, 4),
                "days_positive": sum(1 for v in by_day_d.values() if v > 0),
                "days_negative": sum(1 for v in by_day_d.values() if v < 0),
            })
        else:
            blk.update({"top_day_share": None, "top_trade_share": None})
        blk["day_deltas"] = {k: round(v, 2) for k, v in sorted(by_day_d.items())}
        out[f"vs_{label}"] = blk
    return out


def day_bootstrap(day_deltas: dict[str, float], trials: int = BOOT_TRIALS, seed: int = 7) -> dict:
    """Resample TRADING DAYS with replacement -- the honest block, because all 5 arms trade one
    shared signal so a day, not a trade, is the independent unit."""
    days = sorted(day_deltas)
    vals = [day_deltas[d] for d in days]
    if not vals:
        return {"n_days": 0}
    rnd = random.Random(seed)
    n = len(vals)
    tot = []
    for _ in range(trials):
        tot.append(sum(vals[rnd.randrange(n)] for _ in range(n)))
    tot.sort()
    return {
        "n_days": n,
        "observed_delta": round(sum(vals), 2),
        "boot_p05": round(tot[int(0.05 * trials)], 2),
        "boot_p50": round(tot[int(0.50 * trials)], 2),
        "boot_p95": round(tot[int(0.95 * trials)], 2),
        "pct_resamples_positive": round(100.0 * sum(1 for x in tot if x > 0) / trials, 2),
    }


def permutation_null(rows, fn, base_by_key, trials=PERM_TRIALS, seed=42) -> dict:
    """Shuffle the rule's own multiplier vector WITHIN each arm and re-price. If the true delta
    sits inside the shuffled distribution, the 'edge' is reweighting noise, not information."""
    res = run_scheme(rows, fn)
    true_delta = 0.0
    mult_by_arm = defaultdict(list)
    order = []
    for p in res["per_trade"]:
        k = _key(p)
        mine = p["econ"]["net_slip"] if p["qty"] > 0 else 0.0
        true_delta += mine - base_by_key.get(k, 0.0)
        mult_by_arm[p["row"]["arm"]].append(p["qty"] / p["row"]["qty"] if p["row"]["qty"] else 1.0)
        order.append(p["row"])
    rnd = random.Random(seed)
    deltas = []
    for _ in range(trials):
        pool = {a: rnd.sample(v, len(v)) for a, v in mult_by_arm.items()}
        idx = defaultdict(int)
        tot = 0.0
        for row in order:
            a = row["arm"]
            m = pool[a][idx[a]]
            idx[a] += 1
            q = max(0, int(round(row["qty"] * m)))
            q = min(q, int(math.floor((RULE6_CAP[a] * row["equity_actual"]) / (row["premium"] * 100.0) + 1e-9)))
            k = (a, row["symbol"], row["entry_ts"].isoformat())
            tot += (economics(row, q)["net_slip"] if q > 0 else 0.0) - base_by_key.get(k, 0.0)
        deltas.append(tot)
    deltas.sort()
    return {
        "true_delta": round(true_delta, 2), "trials": trials,
        "null_p05": round(deltas[int(0.05 * trials)], 2),
        "null_p50": round(deltas[int(0.50 * trials)], 2),
        "null_p95": round(deltas[int(0.95 * trials)], 2),
        "pct_of_random_reweightings_at_least_as_good": round(
            100.0 * sum(1 for x in deltas if x >= true_delta) / trials, 2),
    }


# ============================================================================
# LIVE-KNOB AUDITS
# ============================================================================

def audit_live_knobs(rows: list[dict]) -> dict:
    out = {}

    # (1) risky-3 cheap_contract_qty_boost -- LIVE (accounts.json, shipped 966c48f1 2026-08-03)
    pop = [r for r in rows if r["arm"] == "risky-3" and r["premium"] < 0.50 and r["qty"] > 5]
    as_traded = sum(economics(r, r["qty"])["net_slip"] for r in pop)
    at_five = sum(economics(r, 5)["net_slip"] for r in pop)
    byday = defaultdict(float)
    for r in pop:
        byday[r["date"]] += economics(r, r["qty"])["net_slip"] - economics(r, 5)["net_slip"]
    tot = sum(byday.values())
    sd = sorted(byday.items(), key=lambda kv: kv[1])
    out["risky3_cheap_contract_qty_boost"] = {
        "status": "LIVE in automation/state/fleet/accounts.json (params_patch.cheap_contract_qty_boost)",
        "preregistered_kill": "n>=10 boosted fills or 10 sessions, net<0 -> delete the two keys",
        "n_boosted_fills": len(pop),
        "n_sessions": len(byday),
        "net_after_costs_as_traded": round(as_traded, 2),
        "net_after_costs_at_qty5": round(at_five, 2),
        "boost_delta_net_after_costs": round(tot, 2),
        "worst_session": (sd[0][0], round(sd[0][1], 2)) if sd else None,
        "best_session": (sd[-1][0], round(sd[-1][1], 2)) if sd else None,
        "top_session_share_of_delta": round(sd[0][1] / tot, 4) if sd and abs(tot) > 1e-9 else None,
        "sessions_positive": sum(1 for v in byday.values() if v > 0),
        "sessions_negative": sum(1 for v in byday.values() if v < 0),
        "kill_bar_met": len(pop) >= 10 or len(byday) >= 10,
        "kill_bar_verdict": "TRIGGERED" if (len(pop) >= 10 or len(byday) >= 10) and tot < 0 else "NOT TRIGGERED",
        "day_deltas": {k: round(v, 2) for k, v in sorted(byday.items())},
    }

    # (2) the fleet equity/elite ladder: rows where the ladder passed vs was clamped
    tier_base = {"safe-3": 5, "risky-1": 8, "risky-3": 8}
    lad = {}
    for arm, tb in tier_base.items():
        rs = [r for r in rows if r["arm"] == arm and 2000 <= r["equity_actual"] < 10000]
        passed = [r for r in rs if r["qty"] >= tb]
        clamped = [r for r in rs if r["qty"] < tb]

        def pc(v):
            c = sum(x["qty"] for x in v)
            return round(sum(economics(x, x["qty"])["net_slip"] for x in v) / c, 2) if c else None
        lad[arm] = {"tier_base_qty": tb, "n_ladder_passed": len(passed), "n_clamped": len(clamped),
                    "net_after_costs_per_contract_ladder_passed": pc(passed),
                    "net_after_costs_per_contract_clamped": pc(clamped),
                    "clamped_days": sorted({r["date"] for r in clamped}),
                    "passed_days": sorted({r["date"] for r in passed})}
    out["fleet_equity_elite_ladder"] = {
        "mechanism": ("params.json#position_sizing_tiers -> fleet_executor._qty_for; min_contracts "
                      "is applied as a CEILING only on a RED recency verdict "
                      "(_apply_recency_min_sizing, ribbon_ride scope)"),
        "confound_warning": ("ladder-passed vs clamped is NOT a clean size A/B -- the clamp fires on "
                             "RED recency days and the passed population skews to expensive "
                             "VWAP_CONTINUATION entries, so day-regime, setup and premium are all "
                             "confounded with size. Direction only."),
        "per_arm": lad,
    }

    # (3) min_contracts_equity_scaled -- shipped 2026-08-13 (7f354c19), REVERTED 2026-08-14 (636c5ba4)
    dead = [r for r in rows if r["date"] in ("2026-08-13", "2026-08-14")
            and r["qty"] > MINCON[r["arm"]] and not (r["arm"] == "risky-3" and r["premium"] < 0.50)]
    dtot = sum(economics(r, r["qty"])["net_slip"] - economics(r, MINCON[r["arm"]])["net_slip"] for r in dead)
    out["min_contracts_equity_scaled_DEAD"] = {
        "status": "REVERTED 2026-08-14 (commit 636c5ba4); both params files read false today",
        "live_window": "2026-08-13 .. 2026-08-14",
        "n_rows_it_upsized": len(dead),
        "cost_net_after_costs": round(dtot, 2),
        "rows": [{"arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "qty": r["qty"],
                  "mincon": MINCON[r["arm"]], "premium": r["premium"],
                  "net_after_costs": round(economics(r, r["qty"])["net_slip"], 2)} for r in dead],
        "reading": ("this money is already banked as a lesson -- it is NOT an available forward "
                    "improvement, and any counterfactual that 'gains' it is double-counting a "
                    "closed loop"),
    }
    return out


def per_contract_by_bucket(rows: list[dict]) -> dict:
    def bucketise(name, keyfn):
        b = defaultdict(list)
        for r in rows:
            b[keyfn(r)].append(economics(r, r["qty"])["net_slip"] / r["qty"])
        return {name: {str(k): {"n": len(v),
                                "mean_net_per_contract": round(statistics.fmean(v), 2),
                                "median_net_per_contract": round(statistics.median(v), 2)}
                       for k, v in sorted(b.items(), key=lambda kv: str(kv[0]))}}
    out = {}
    out.update(bucketise("by_score", lambda r: "<8" if r["score"] < 8 else ("8-9" if r["score"] < 10 else ">=10")))
    out.update(bucketise("by_quality_tier", lambda r: r["tier"]))
    out.update(bucketise("by_vix", lambda r: "<16" if r["vix"] < 16 else ("16-20" if r["vix"] < 20 else ">=20")))
    out.update(bucketise("by_entry_premium", lambda r: "<0.50" if r["premium"] < 0.50 else ("0.50-0.99" if r["premium"] < 1.0 else ">=1.00")))
    out.update(bucketise("by_clock", lambda r: "first_60m" if r["mso"] <= 60 else "after_60m"))
    out.update(bucketise("by_capital_regime", lambda r: "pre_refund" if r["date"] < REFUND_DATE else "post_refund"))
    out.update(bucketise("by_arm", lambda r: r["arm"]))
    return out


def main() -> int:
    d = json.loads(MATRIX.read_text())
    rows = prep(d["rows"])

    prod_res = run_scheme(rows, scheme_production)
    prod_by_key = {_key(p): (p["econ"]["net_slip"] if p["qty"] > 0 else 0.0) for p in prod_res["per_trade"]}
    minc_res = run_scheme(rows, scheme_mincon)
    minc_by_key = {_key(p): (p["econ"]["net_slip"] if p["qty"] > 0 else 0.0) for p in minc_res["per_trade"]}
    baselines = {"PRODUCTION": prod_by_key, "MINCON_FLAT": minc_by_key}

    cells = {}
    for name, fam, desc, fn in SCHEMES:
        s = summarise(run_scheme(rows, fn), baselines)
        s["family"] = fam
        s["description"] = desc
        s["is_production"] = (name == "PRODUCTION")
        s["bootstrap_vs_PRODUCTION"] = day_bootstrap(s["vs_PRODUCTION"]["day_deltas"])
        s["bootstrap_vs_MINCON_FLAT"] = day_bootstrap(s["vs_MINCON_FLAT"]["day_deltas"], seed=11)
        cells[name] = s

    # permutation null on the three best SHAPE cells (ranked leverage-neutrally)
    shape_rank = sorted((n for n in cells if n not in ("PRODUCTION",)),
                        key=lambda n: -cells[n]["net_after_costs_per_contract"])
    perms = {}
    for n in shape_rank[:3]:
        perms[n] = permutation_null(rows, SCHEME_FN[n], minc_by_key)

    recon = {
        "ledger_gross": d["totals"]["gross"], "model_gross": cells["PRODUCTION"]["gross"],
        "gross_diff": round(cells["PRODUCTION"]["gross"] - d["totals"]["gross"], 2),
        "ledger_fees_ex_cat": d["totals"]["fees_ex_cat"], "model_fees": cells["PRODUCTION"]["fees"],
        "fees_diff": round(cells["PRODUCTION"]["fees"] - d["totals"]["fees_ex_cat"], 2),
        "note": ("gross differs by $1.34 (one ledger row rounds -36.99 to -37.00); fees differ by "
                 "$0.49 because the model charges OCC/ORF once per SIDE and the ledger charges per "
                 "EXECUTION. The same formula prices every cell, so both cancel out of every delta."),
    }

    sig = set()
    for r in rows:
        b = r["entry_ts"].replace(second=0, microsecond=0)
        b -= dt.timedelta(minutes=b.minute % 5)
        sig.add((r["date"], r["side"], r["setup"], b))

    out = {
        "_doc": ("Position-sizing counterfactual matrix over all 303 closed round trips. Sizing "
                 "cannot change which trades happened or their sign -- only the dollar weight on "
                 "each. Built by setup/scripts/sizing_matrix_2026_08_19.py."),
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "analysis/recommendations/trade-matrix.json",
        "n_rows": len(rows),
        "n_trading_days": len({r["date"] for r in rows}),
        "n_effective_signal_decisions": len(sig),
        "n_effective_note": ("distinct (date, side, setup, 5-min entry bucket) groups across all 5 "
                             "arms. The arms trade ONE shared signal at r=0.846 / 95.7% sign "
                             "agreement, so this -- not 303 -- bounds the independent evidence, and "
                             "for a DAY-level effect the binding number is 35 trading days."),
        "cost_model": {"occ_per_contract": OCC, "orf_per_contract": ORF,
                       "taf_per_contract_sells": TAF, "sec_rate_per_dollar": SEC_RATE,
                       "exit_slippage_range_fraction": EXIT_SLIP_RANGE_FRAC},
        "rule6_caps": RULE6_CAP, "min_contracts": MINCON,
        "capital_injections_detected": prod_res["injections"],
        "production_reconciliation": recon,
        "cells": cells,
        "shape_rank_by_net_after_costs_per_contract": shape_rank,
        "permutation_nulls_vs_MINCON_FLAT": perms,
        "live_knob_audits": audit_live_knobs(rows),
        "per_contract_edge_by_at_entry_bucket": per_contract_by_bucket(rows),
    }
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote {OUT_JSON}")

    hdr = (f"{'cell':16s}{'ctrs':>6s}{'gross':>8s}{'netAC':>8s}{'$/ctr':>8s}{'WR%':>6s}"
           f"{'avgW':>7s}{'avgL':>7s}{'maxDD':>8s}{'worstD':>8s}{'dvsPROD':>9s}{'dvsMINC':>9s}"
           f"{'topDay':>8s}{'boot+%':>8s}{'maxQ':>5s}{'clmp':>5s}")
    print(hdr)
    print("-" * len(hdr))
    for name, _, _, _ in SCHEMES:
        c = cells[name]
        tds = c["vs_MINCON_FLAT"].get("top_day_share")
        print(f"{name:16s}{c['contracts']:6d}{c['gross']:8.0f}{c['net_after_costs']:8.0f}"
              f"{c['net_after_costs_per_contract']:8.2f}{(c['win_rate_net'] or 0):6.1f}"
              f"{(c['avg_win'] or 0):7.0f}{(c['avg_loss'] or 0):7.0f}{c['max_drawdown']:8.0f}"
              f"{c['worst_day']:8.0f}{c['vs_PRODUCTION']['delta_net_after_costs']:9.0f}"
              f"{c['vs_MINCON_FLAT']['delta_net_after_costs']:9.0f}"
              f"{(tds if tds is not None else float('nan')):8.2f}"
              f"{c['bootstrap_vs_MINCON_FLAT'].get('pct_resamples_positive', float('nan')):8.1f}"
              f"{c['max_contracts_single_trade']:5d}{c['rule6_clamps']:5d}")
    print()
    print("reconciliation:", json.dumps(recon))
    print("n_effective signal decisions:", len(sig), "| trading days:", out["n_trading_days"])
    print("\nshape rank (net-after-costs per contract):", shape_rank[:6])
    print("\npermutation nulls vs MINCON-FLAT:", json.dumps(perms, indent=1))
    print("\nLIVE KNOB AUDITS:", json.dumps(out["live_knob_audits"]["risky3_cheap_contract_qty_boost"], indent=1))
    print("\nDEAD KNOB:", json.dumps({k: v for k, v in out["live_knob_audits"]["min_contracts_equity_scaled_DEAD"].items() if k != "rows"}, indent=1))
    print("\nper-contract edge by at-entry bucket:")
    print(json.dumps(out["per_contract_edge_by_at_entry_bucket"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
