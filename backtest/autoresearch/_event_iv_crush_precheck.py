"""EVENT-IV-CRUSH mechanism pre-check (STRATEGY-DIRECTION-BACKLOG #6).

QUESTION (decisive, cheap, existing data):
  On the EXISTING 0DTE OPRA cache (backtest/data/options/, 2025-01-02..2026-06-18),
  does a DEFINED-RISK narrow short-premium structure (iron fly / narrow iron condor)
  sold at a fixed intraday time and held to the 0DTE close systematically:
    (a) out-earn the SAME structure on NON-event days (the IV-crush selection delta),
    (b) BEAT the random-DAY-selection null (L172: sample equal-n random NON-event days
        many times -> distribution of exp/tr; the event days must sit in the right tail),
    (c) keep the defined-risk worst-day INSIDE the kill-switch,
    (d) have adequate n + posQ?

WHY THIS IS A NEW TEST (vs WP-PS1 / PIVOT-PREMIUM-SELLING-SCORECARD.md):
  WP-PS1 randomized the STRIKE and found the ambient every-day IC is generic theta that
  a random-STRIKE null reproduces -> no SELECTION alpha. This pre-check supplies the
  MISSING non-random selection rule: trade ONLY on scheduled-EVENT days (FOMC/CPI/NFP),
  and the null randomizes the DAY (equal-n random non-event days), per the spec.

REUSE (byte-for-byte): lib.simulator_credit + lib.multileg_structures (17/17 tests),
  lib.cap_admission (defined-risk notional must fit Safe $600/qty3 and Bold $824/qty5),
  and the spot/entry/eligibility conventions from autoresearch/_pivot_premium_selling.py.
  simulator_real.py UNTOUCHED. Pure offline, $0.

NO live edit. Research-only. DEFINED-RISK ONLY (every short leg paired with a long wing).
"""

from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib import simulator_credit as sc                         # noqa: E402
from lib.multileg_structures import build_legs, legs_in_band   # noqa: E402
from lib import cap_admission as ca                            # noqa: E402

# Reuse the EXACT spot/entry/eligibility plumbing from the pivot harness so the
# event/non-event sims are byte-identical to the validated WP-PS1 path.
from autoresearch._pivot_premium_selling import (              # noqa: E402
    _load_spy_master,
    _spot_and_decision,
    _build_variant_legs,
    eligible,
    _option_cache_dates,
    BAND_HALF_WIDTH,
)

WINDOW_START = dt.date(2025, 1, 2)
WINDOW_END = dt.date(2026, 6, 18)

# ── DETERMINISTIC EVENT-DAY LIST (public scheduled dates) ───────────────────
# Sources (public calendars):
#  FOMC decision days  -> federalreserve.gov FOMC calendar (2025 + 2026).
#  CPI release days    -> bls.gov CPI release schedule (monthly, 08:30 ET).
#  NFP (Employment Sit.)-> bls.gov Employment Situation schedule (monthly, 08:30 ET;
#                          historically the first Friday, with documented exceptions).
# These are SCHEDULED public dates known in advance — no look-ahead.

# FOMC RATE-DECISION days (second day of each 2-day meeting).
FOMC_2025 = [
    dt.date(2025, 1, 29), dt.date(2025, 3, 19), dt.date(2025, 5, 7),
    dt.date(2025, 6, 18), dt.date(2025, 7, 30), dt.date(2025, 9, 17),
    dt.date(2025, 10, 29), dt.date(2025, 12, 10),
]
FOMC_2026 = [
    dt.date(2026, 1, 28), dt.date(2026, 3, 18), dt.date(2026, 4, 29),
    dt.date(2026, 6, 17),
]

# CPI release days (08:30 ET). BLS CPI schedule.
CPI_2025 = [
    dt.date(2025, 1, 15), dt.date(2025, 2, 12), dt.date(2025, 3, 12),
    dt.date(2025, 4, 10), dt.date(2025, 5, 13), dt.date(2025, 6, 11),
    dt.date(2025, 7, 15), dt.date(2025, 8, 12), dt.date(2025, 9, 11),
    dt.date(2025, 10, 15), dt.date(2025, 11, 13), dt.date(2025, 12, 10),
]
CPI_2026 = [
    dt.date(2026, 1, 14), dt.date(2026, 2, 11), dt.date(2026, 3, 11),
    dt.date(2026, 4, 10), dt.date(2026, 5, 12), dt.date(2026, 6, 10),
]

# NFP / Employment Situation release days (08:30 ET). BLS Employment Situation schedule
# (first Friday of the month, with the standard documented shifts).
NFP_2025 = [
    dt.date(2025, 1, 10), dt.date(2025, 2, 7), dt.date(2025, 3, 7),
    dt.date(2025, 4, 4), dt.date(2025, 5, 2), dt.date(2025, 6, 6),
    dt.date(2025, 7, 3), dt.date(2025, 8, 1), dt.date(2025, 9, 5),
    dt.date(2025, 10, 3), dt.date(2025, 11, 7), dt.date(2025, 12, 5),
]
NFP_2026 = [
    dt.date(2026, 1, 9), dt.date(2026, 2, 6), dt.date(2026, 3, 6),
    dt.date(2026, 4, 3), dt.date(2026, 5, 8), dt.date(2026, 6, 5),
]


def build_event_days() -> dict:
    """Return {set of event dates in-window} + provenance counts."""
    fomc = [d for d in FOMC_2025 + FOMC_2026 if WINDOW_START <= d <= WINDOW_END]
    cpi = [d for d in CPI_2025 + CPI_2026 if WINDOW_START <= d <= WINDOW_END]
    nfp = [d for d in NFP_2025 + NFP_2026 if WINDOW_START <= d <= WINDOW_END]
    all_ev = set(fomc) | set(cpi) | set(nfp)
    return {
        "fomc": sorted(fomc), "cpi": sorted(cpi), "nfp": sorted(nfp),
        "all": sorted(all_ev),
        "n_fomc": len(fomc), "n_cpi": len(cpi), "n_nfp": len(nfp),
        "n_union": len(all_ev),
        "overlap": len(fomc) + len(cpi) + len(nfp) - len(all_ev),
    }


# ── STRUCTURE: narrow defined-risk iron fly (IB) — highest credit, the natural
#    "sell the elevated event IV, ride the crush" structure. Also report a narrow IC.
#    The +/-$5 OPRA cache forces narrow $1-$2 wings (a MECHANISM pre-check only; the
#    proper 16-delta/20-wide condor needs the wide-band fetch = the NEXT step IF clear).
ENTRY_TIME = dt.time(10, 0)     # 10:00 ET: after the 08:30 CPI/NFP print + cash open settle
WING_WIDTH = 2                  # narrowest cap-fitting wing the band reliably prices
SHORT_OFFSET_IC = 2            # IC short strikes ATM+/-2 ; IB shorts at ATM
PT_FRAC = 0.50
STOP_MULT = None               # EOD-only: hold the defined-risk structure to the 0DTE close
COMMISSION = 0.65


def run_on_days(structure: str, spy, day_list, *, short_offset: int, wing_width: int):
    """Sim the structure across day_list. Returns list[CreditFill] (taken only)."""
    fills = []
    for d in day_list:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = _spot_and_decision(spy_day, ENTRY_TIME)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs = _build_variant_legs(structure, spot, short_offset, wing_width)
        if not eligible(legs, spot):
            continue
        binding_wing = wing_width
        f = sc.simulate_credit_trade(
            d, legs, decision_dt, spot, wing_width=binding_wing,
            structure_name=structure, contracts=1, pt_frac=PT_FRAC,
            stop_mult=STOP_MULT, commission_per_contract=COMMISSION)
        if not f.skipped:
            fills.append(f)
    return fills


def summarize(fills, label: str) -> dict:
    pnls = [f.realized_pnl for f in fills]
    if not pnls:
        return {"label": label, "n": 0}
    dated = sorted(((f.date, f.realized_pnl) for f in fills), key=lambda x: x[0])
    # book max drawdown
    eq = peak = mdd = 0.0
    for _, p in dated:
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    wins = [p for p in pnls if p > 0]
    # worst defined-risk single trade (== worst day, 1 trade/day)
    worst = min(pnls)
    # posQ over calendar months present
    by_month: dict[str, list[float]] = {}
    for f in fills:
        mk = f.date[:7]
        by_month.setdefault(mk, []).append(f.realized_pnl)
    pos_months = sum(1 for v in by_month.values() if statistics.mean(v) > 0)
    return {
        "label": label,
        "n": len(pnls),
        "exp_per_trade": round(statistics.mean(pnls), 2),
        "total_pnl": round(sum(pnls), 2),
        "wr": round(len(wins) / len(pnls), 3),
        "worst_trade": round(worst, 2),
        "book_max_dd": round(mdd, 2),
        "avg_credit": round(statistics.mean([f.net_credit for f in fills]), 2),
        "avg_max_loss_defined": round(statistics.mean([f.max_loss_defined for f in fills]), 2),
        "n_months": len(by_month),
        "pos_months": pos_months,
        "intrabar_stop_would_hit": sum(1 for f in fills if f.intrabar_stop_would_hit),
    }


def random_day_null(structure, spy, nonevent_days, n_sample, *, short_offset, wing_width,
                    reps=500, seed=12345):
    """L172 random-DAY-selection null: draw n_sample random NON-event days `reps` times,
    sim the SAME structure, return the distribution of exp/tr. The event-day exp must sit
    in the RIGHT tail of this distribution to claim a selection edge."""
    rng = random.Random(seed)
    # pre-sim every non-event day ONCE (cache), then resample indices for speed + parity.
    all_fills = run_on_days(structure, spy, nonevent_days,
                            short_offset=short_offset, wing_width=wing_width)
    by_date = {f.date: f for f in all_fills}
    tradeable_dates = list(by_date.keys())
    if len(tradeable_dates) < n_sample or n_sample == 0:
        return None
    exps = []
    for _ in range(reps):
        pick = rng.sample(tradeable_dates, n_sample)
        exps.append(statistics.mean([by_date[dd].realized_pnl for dd in pick]))
    exps.sort()
    return {
        "reps": reps,
        "n_sample": n_sample,
        "nonevent_tradeable_pool": len(tradeable_dates),
        "null_mean": round(statistics.mean(exps), 2),
        "null_p50": round(exps[len(exps) // 2], 2),
        "null_p95": round(exps[int(0.95 * len(exps))], 2),
        "null_p05": round(exps[int(0.05 * len(exps))], 2),
    }


def percentile_of(value, spy, structure, nonevent_days, n_sample, *, short_offset,
                  wing_width, reps=500, seed=12345):
    rng = random.Random(seed)
    all_fills = run_on_days(structure, spy, nonevent_days,
                            short_offset=short_offset, wing_width=wing_width)
    by_date = {f.date: f for f in all_fills}
    tradeable_dates = list(by_date.keys())
    if len(tradeable_dates) < n_sample or n_sample == 0:
        return None
    exps = []
    for _ in range(reps):
        pick = rng.sample(tradeable_dates, n_sample)
        exps.append(statistics.mean([by_date[dd].realized_pnl for dd in pick]))
    below = sum(1 for e in exps if e < value)
    return round(100.0 * below / len(exps), 1)


def cap_check(fills, account="safe", equity=2000.0):
    """Worst single defined-risk trade vs kill-switch + cap-admission of the qty."""
    qty = ca.SAFE_MIN_CONTRACTS if account == "safe" else ca.BOLD_MIN_CONTRACTS
    if not fills:
        return {}
    worst_per_lot = min(f.realized_pnl for f in fills)
    worst_scaled = worst_per_lot * qty
    max_loss_lot = max(f.max_loss_defined for f in fills)
    # admit the median order at the cap
    res = ca.admit_book(
        fills, account, equity, qty,
        premium_getter=lambda f: f.net_credit / 100.0,  # credit received as the "premium" proxy
    )
    kill = 600.0 if account == "safe" else 824.0
    return {
        "account": account, "qty": qty, "equity": equity,
        "worst_trade_per_lot": round(worst_per_lot, 2),
        "worst_trade_scaled_qty": round(worst_scaled, 2),
        "max_defined_loss_per_lot": round(max_loss_lot, 2),
        "max_defined_loss_scaled": round(max_loss_lot * qty, 2),
        "kill_switch_dollars": kill,
        "worst_scaled_inside_kill": bool(abs(worst_scaled) <= kill),
        "max_defined_scaled_inside_kill": bool(max_loss_lot * qty <= kill),
        "admitted": len(res.admitted), "blocked": len(res.blocked),
        "block_rate": res.block_rate,
    }


def main():
    ev = build_event_days()
    cache_dates = _option_cache_dates()
    spy = _load_spy_master()
    all_dates = sorted(set(spy["date"].unique()) & cache_dates)
    all_dates = [d for d in all_dates if WINDOW_START <= d <= WINDOW_END]
    event_set = set(ev["all"])
    event_days = [d for d in all_dates if d in event_set]
    nonevent_days = [d for d in all_dates if d not in event_set]

    print("=" * 70)
    print("EVENT-DAY LIST (deterministic, public schedules)")
    print("=" * 70)
    print(f"  FOMC: {ev['n_fomc']}  CPI: {ev['n_cpi']}  NFP: {ev['n_nfp']}  "
          f"UNION: {ev['n_union']}  (overlap dropped: {ev['overlap']})")
    print(f"  in-window range: {WINDOW_START} .. {WINDOW_END}")
    print(f"  spot-check FOMC: {ev['fomc'][:4]} ...")
    print(f"  spot-check CPI : {ev['cpi'][:4]} ...")
    print(f"  spot-check NFP : {ev['nfp'][:4]} ...")
    print(f"  trading days w/ both SPY+OPRA cache: {len(all_dates)}")
    print(f"  event days (cache-present): {len(event_days)}  "
          f"non-event: {len(nonevent_days)}")

    out = {"event_days_meta": {k: v for k, v in ev.items()
                               if k in ("n_fomc", "n_cpi", "n_nfp", "n_union", "overlap")},
           "event_days_iso": [d.isoformat() for d in event_days],
           "n_all_cache_days": len(all_dates)}

    for structure, soff in (("IB", 0), ("IC", SHORT_OFFSET_IC)):
        print("\n" + "=" * 70)
        print(f"STRUCTURE: {structure}  (entry {ENTRY_TIME} ET, wing ${WING_WIDTH}, "
              f"short_offset={soff}, pt={PT_FRAC}, stop={STOP_MULT}, hold-to-0DTE-close)")
        print("=" * 70)
        ev_fills = run_on_days(structure, spy, event_days,
                               short_offset=soff, wing_width=WING_WIDTH)
        ne_fills = run_on_days(structure, spy, nonevent_days,
                               short_offset=soff, wing_width=WING_WIDTH)
        ev_sum = summarize(ev_fills, "EVENT")
        ne_sum = summarize(ne_fills, "NON-EVENT")
        print("  EVENT    :", json.dumps(ev_sum))
        print("  NON-EVENT:", json.dumps(ne_sum))

        if ev_sum["n"] == 0:
            print("  >> no event fills; skip null.")
            continue

        delta = round(ev_sum["exp_per_trade"] - ne_sum["exp_per_trade"], 2)
        print(f"  IV-CRUSH SELECTION DELTA (event - nonevent exp/tr): ${delta}")

        nul = random_day_null(structure, spy, nonevent_days, ev_sum["n"],
                              short_offset=soff, wing_width=WING_WIDTH, reps=500)
        pct = percentile_of(ev_sum["exp_per_trade"], spy, structure, nonevent_days,
                            ev_sum["n"], short_offset=soff, wing_width=WING_WIDTH, reps=500)
        print("  RANDOM-DAY NULL:", json.dumps(nul))
        beats_null = bool(nul and pct is not None and ev_sum["exp_per_trade"] > nul["null_p95"])
        print(f"  event-day exp percentile within null: {pct}th  "
              f"(beats p95 = {beats_null})")

        cap = cap_check(ev_fills, "safe", 2000.0)
        cap_b = cap_check(ev_fills, "bold", 1649.0)
        print("  CAP/KILL (Safe):", json.dumps(cap))
        print("  CAP/KILL (Bold):", json.dumps(cap_b))

        mechanism = bool(
            delta > 0
            and beats_null
            and cap.get("max_defined_scaled_inside_kill", False)
        )
        print(f"  >> MECHANISM_PRESENT[{structure}] = {mechanism}  "
              f"(delta>0={delta>0}, beats_null={beats_null}, "
              f"tail_inside_kill={cap.get('max_defined_scaled_inside_kill')})")

        out[structure] = {
            "event": ev_sum, "nonevent": ne_sum, "selection_delta": delta,
            "null": nul, "event_percentile_in_null": pct, "beats_null_p95": beats_null,
            "cap_safe": cap, "cap_bold": cap_b, "mechanism_present": mechanism,
        }

    OUT = _BT / "autoresearch" / "_state" / "event_iv_crush_precheck.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
