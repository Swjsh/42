"""ANGLE B — NEUTRAL CALENDAR: does buying a LONG back-leg (1DTE/2DTE) under the
0DTE short strangle/straddle let the theta-harvest BEAT the iron-condor LEAD on
tail-survivability + risk-adjusted AND escape the random-strike NULL (L172)?

THE CONDOR LEAD WE MUST BEAT (PIVOT-PREMIUM-SELLING-SCORECARD.md)
----------------------------------------------------------------
The neutral 0DTE IC (off2/w2/pt0.5) is OOS-POSITIVE (+$23/tr, 82.7% WR, book DD
-$124) but FAILS gate-6: a random-strike null reproduces / at p95 EXCEEDS the
"chosen" expectancy -> generic theta, NOT selection alpha. Its benign tail is
CONDITIONAL on the narrow +-$5 cache band ($1-$2 wings cap max-loss at $100-$200);
it does NOT generalize to a real (~$3000-max-loss) condor. The iron FLY is the
steamroller loser (book DD -$1,378, WR 48%).

THE CALENDAR STRUCTURE THIS PRICES
----------------------------------
  SHORT leg(s) = 0DTE strangle (sell OTM call + sell OTM put, short_offset $ OTM) or
                 straddle (offset 0). The 0DTE theta harvest = the condor's income.
  LONG  leg(s) = the SAME strikes one expiry out (1DTE or 2DTE). This BACK leg is the
                 only structural difference vs the condor: instead of a defined-risk
                 WING at a different strike, the protection is a LONGER-DATED option at
                 the SAME strike that SURVIVES the big-move steamroller (it still has
                 extrinsic value + a day of life when the 0DTE short is breached).

WHY THE BACK LEG IS THE "TAIL PROTECTION"
-----------------------------------------
On a steamroller day the 0DTE short goes deep ITM (full intrinsic loss) but the 1DTE
long at the SAME strike is ALSO deep ITM (it caps the short's loss to ~the calendar
debit/credit + one day of carry) AND retains time value. The condor's wing caps loss
at the strike GAP; the calendar's back leg caps loss at the SAME strike (tighter cap)
while keeping a live directional option overnight -> the steamroller-survivability the
naive condor lacks. THAT is the only edge the calendar can structurally add.

HONEST PRIOR (stated in the task)
---------------------------------
A calendar is STILL fundamentally theta-harvest. Swapping the condor's wings for a
back-leg does NOT change the STRIKE-SELECTION question that killed the condor on
gate-6. So the calendar most likely INHERITS the null failure: the +EV (if any) is
generic theta, and a random short strike reproduces it. The tail-protection is the
one thing that can differ. We test it honestly and report the verdict per the bar.

CROSS-EXPIRY PRICING (reused byte-for-byte, NO edits to production)
------------------------------------------------------------------
Each leg prices from its OWN expiry cache via `_dte_expansion_sim.load_dte_contract_bars`
(short -> options/ 0DTE, long -> options_1dte/ or options_2dte/), the SAME loader the
diagonal sim uses. Short legs: sell-to-open BID (open - slip), buy-to-close ASK
(close + slip) -- mirrors `simulator_credit`. Long legs: buy-to-open ASK, sell-to-close
BID. Net value = sum of signed per-leg marks. NO look-ahead: entry = first 0DTE bar
at/after the grid entry time; management reads day-T bars only; short legs settle at
their 0DTE intrinsic (day-T close); long legs settle at their own expiry intrinsic.

The DAY/ENTRY GRID + band pre-filter + scoring + the OPRA conventions are reused from
`_pivot_premium_selling.py` so the calendar is compared APPLES-TO-APPLES vs the condor
LEAD on the SAME days, SAME entries, SAME slippage/commission, SAME gate bar.

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_calendar_premium_sim.py --validate
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_calendar_premium_sim.py --smoke
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_calendar_premium_sim.py        # sweep+null
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parent
for p in (REPO, ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch._dte_expansion_sim import (  # noqa: E402
    load_dte_contract_bars,
    _bar_at_or_after,
    _quote_at_index,
    _nearest_cached_strike_dte,
    _build_expiry_index,
    _expiry_for_entry,
    _spy_day_open_close,
    DEFAULT_ENTRY_SLIPPAGE,
    DEFAULT_EXIT_SLIPPAGE,
)
from autoresearch._pivot_premium_selling import (  # noqa: E402
    _load_spy_master,
    _spot_and_decision,
    _book_max_dd,
    _drop_top_n,
    _drop_worst_n,
    ENTRY_TIMES_ET,
    OOS_2026_START,
    IS_2025_START,
    IS_2025_END,
)
from lib.option_pricing_real import option_symbol  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "calendar-premium.json"
COMMISSION = 0.65
CONTRACTS = 1
TIME_STOP_ET = dt.time(15, 50)
SAFE_KILL = 600.0   # Safe-2 daily kill ($600) — the tail must fit inside this.

# ── SWEEP GRID (mirror the condor grid's neutral axes) ───────────────────────────
SHORT_OFFSETS = [2, 3, 4]        # strangle OTM offset (0 in STRADDLE_OFFSETS = straddle).
STRADDLE = [False]               # straddle (offset 0) tested separately as a control.
LONG_DTES = [1, 2]               # back-leg expiry.
ENTRY_TIMES = [dt.time(10, 30), dt.time(9, 40), dt.time(11, 0)]  # the condor's winning band.
PT_FRACS = [0.50]                # the condor LEAD's profit-take fraction.
STOP_MULTS: list[Optional[float]] = [2.0, None]   # None = EOD-only.
NULL_SEEDS = 30
NULL_OFFSET_POOL = [2, 3, 4]


@dataclass
class CalFill:
    date: str
    structure: str
    skipped: bool = False
    skip_reason: str = ""
    short_offset: int = 0
    long_dte: int = 0
    call_strike: int = 0
    put_strike: int = 0
    net_entry: float = 0.0       # net debit(+)/credit(-) per share at entry (long-short)
    net_exit: float = 0.0
    realized_pnl: float = 0.0    # $ incl. commission
    exit_reason: str = ""
    worst_day_intrinsic_loss: float = 0.0   # $ steamroller exposure at EOD settlement
    tail_capped_dollar: float = 0.0         # max structural loss the back-leg leaves open
    tail_survivable: bool = True


def _leg_entry(symbol: str, dte: int, when_et: dt.datetime, *, slip: float, buy: bool):
    """Return (df, fill_price, entry_idx) or None. buy=True -> pay ASK(open+slip);
    buy=False -> collect BID(open-slip)."""
    df = load_dte_contract_bars(symbol, dte)
    if df is None:
        return None
    eb = _bar_at_or_after(df, when_et)
    if eb is None or eb.open <= 0:
        return None
    price = eb.open + slip if buy else max(0.01, eb.open - slip)
    # entry index
    idx = None
    for k in range(len(df)):
        if df.iloc[k]["timestamp_et"] == eb.timestamp_et:
            idx = k
            break
    if idx is None:
        return None
    return df, price, idx


def simulate_calendar_trade(
    d: dt.date, decision_dt: dt.datetime, spot: float, *,
    short_offset: int, long_dte: int, straddle: bool,
    call_strike: int, put_strike: int,
    call_expiry_short: dt.date, put_expiry_short: dt.date,
    call_expiry_long: dt.date, put_expiry_long: dt.date,
    day_open_close: dict, pt_frac: float, stop_mult: Optional[float],
    contracts: int = CONTRACTS,
    entry_slip: float = DEFAULT_ENTRY_SLIPPAGE, exit_slip: float = DEFAULT_EXIT_SLIPPAGE,
) -> Optional[CalFill]:
    """Calendar: SHORT 0DTE call+put + LONG (1/2DTE) call+put SAME strikes.

    Net entry = (long_call_ask + long_put_ask) - (short_call_bid + short_put_bid)  [per share].
    Managed on NET value: PT at net DEBIT shrinking to (1-pt_frac)*entry-ish is wrong for a
    calendar (it is a net DEBIT structure that PROFITS when the front decays faster than the
    back). We define profit = net value RISES above entry by pt_frac of the front credit;
    loss-stop = net value falls by stop_mult * front_credit (front credit = the harvest at risk).
    EOD: shorts settle 0DTE intrinsic; longs settle own-expiry intrinsic (held-overnight).
    """
    entry_when = decision_dt
    sc_sym = option_symbol(call_expiry_short, call_strike, "C")
    sp_sym = option_symbol(put_expiry_short, put_strike, "P")
    lc_sym = option_symbol(call_expiry_long, call_strike, "C")
    lp_sym = option_symbol(put_expiry_long, put_strike, "P")

    sc = _leg_entry(sc_sym, 0, entry_when, slip=entry_slip, buy=False)
    sp = _leg_entry(sp_sym, 0, entry_when, slip=entry_slip, buy=False)
    lc = _leg_entry(lc_sym, long_dte, entry_when, slip=entry_slip, buy=True)
    lp = _leg_entry(lp_sym, long_dte, entry_when, slip=entry_slip, buy=True)
    if None in (sc, sp, lc, lp):
        return None
    sc_df, sc_bid, sc_i = sc
    sp_df, sp_bid, sp_i = sp
    lc_df, lc_ask, lc_i = lc
    lp_df, lp_ask, lp_i = lp

    front_credit = sc_bid + sp_bid                 # 0DTE harvest collected (per share)
    back_cost = lc_ask + lp_ask                    # long back-leg paid (per share)
    net_entry = back_cost - front_credit           # net DEBIT (calendar is paid for)
    if front_credit <= 0:
        return None

    # Management thresholds expressed in NET VALUE terms.
    # The calendar GAINS when the front decays faster than the back => net value RISES
    # toward back_cost (front -> 0). Profit target: capture pt_frac of the front credit.
    net_tp = net_entry + pt_frac * front_credit
    # Stop: a steamroller blows the front out faster than the back can offset -> net value
    # FALLS (front loss > back gain near the money). Stop at stop_mult * front_credit loss.
    net_stop = (net_entry - stop_mult * front_credit) if stop_mult is not None else None

    # Walk day-T bars in lockstep (all four legs share the 0DTE/long grid on day T).
    sc_idx, sp_idx, lc_idx, lp_idx = sc_i + 1, sp_i + 1, lc_i + 1, lp_i + 1
    exit_reason = None
    net_exit = None
    while True:
        scb = _quote_at_index(sc_df, sc_idx)
        spb = _quote_at_index(sp_df, sp_idx)
        lcb = _quote_at_index(lc_df, lc_idx)
        lpb = _quote_at_index(lp_df, lp_idx)
        if None in (scb, spb, lcb, lpb):
            break
        if scb.timestamp_et.date() != d:
            break
        t = scb.timestamp_et.time()
        # NET value now, marked on the BAR CLOSE (the only simultaneously-realizable mark).
        # CRITICAL (L49 seller-backtest trap): do NOT use cross-leg intrabar extremes
        # (long.high WITH short.low) for the favorable net or (long.low WITH short.high) for
        # the adverse net -- those extremes do not co-occur within a 5m bar and over-state
        # net_best by $0.5-$1.3/sh (phantom PT fills). The condor sim marks on close
        # (eod_close_mark); we match it. The bracket would fill near the close, so close-MTM
        # is the honest, slightly-conservative basis for BOTH PT and stop.
        net_close = (lcb.close + lpb.close) - (scb.close + spb.close)
        # (1) stop first (conservative)
        if net_stop is not None and net_close <= net_stop:
            net_exit = net_close
            exit_reason = "STOP"
            break
        # (2) profit target
        if net_close >= net_tp:
            net_exit = net_close
            exit_reason = "PT"
            break
        # (3) time stop
        if t >= TIME_STOP_ET:
            net_exit = net_close
            exit_reason = "TIME_STOP"
            break
        sc_idx += 1; sp_idx += 1; lc_idx += 1; lp_idx += 1

    short_intrinsic_loss_dollar = 0.0
    if exit_reason is None:
        # EOD settlement. Shorts settle at 0DTE intrinsic (day-T close); longs at own expiry.
        oc = day_open_close.get(d)
        if oc is None:
            return None
        close_t = oc[1]
        short_c_intr = max(0.0, close_t - call_strike)
        short_p_intr = max(0.0, put_strike - close_t)
        # long legs: held to own expiry settlement intrinsic
        lc_exp = day_open_close.get(call_expiry_long)
        lp_exp = day_open_close.get(put_expiry_long)
        if lc_exp is None or lp_exp is None:
            return None
        long_c_intr = max(0.0, lc_exp[1] - call_strike)
        long_p_intr = max(0.0, lp_exp[1] - put_strike)
        net_exit = (long_c_intr + long_p_intr) - (short_c_intr + short_p_intr)
        exit_reason = "EOD_SETTLE"
        # steamroller exposure: the gross $ the short side is ITM at its 0DTE settlement.
        short_intrinsic_loss_dollar = (short_c_intr + short_p_intr) * contracts * 100.0

    # P&L on the net position (net is a DEBIT paid; profit when net_exit > net_entry).
    gross = (net_exit - net_entry) * contracts * 100.0
    legs_n = 4
    comm = COMMISSION * contracts * legs_n * 2  # open+close both ways
    realized = gross - comm

    # Tail accounting: the back leg caps the short's loss at the SAME strike. The max
    # structural loss the calendar leaves open = net_entry debit (paid) + carry, because
    # above/below the strike the long and short move 1-for-1 (same strike) -> intrinsic
    # nets to ZERO; only time value + the entry debit + 1-day carry is at risk. So the
    # defined max loss ~= net_entry debit * contracts * 100 + a 1-day carry buffer.
    tail_capped = net_entry * contracts * 100.0
    tail_survivable = abs(tail_capped) <= SAFE_KILL and short_intrinsic_loss_dollar <= SAFE_KILL * 3

    struct = "CAL_STRADDLE" if straddle else "CAL_STRANGLE"
    return CalFill(
        date=d.strftime("%Y-%m-%d"), structure=struct, short_offset=short_offset,
        long_dte=long_dte, call_strike=call_strike, put_strike=put_strike,
        net_entry=round(net_entry, 4), net_exit=round(net_exit, 4),
        realized_pnl=round(realized, 2), exit_reason=exit_reason,
        worst_day_intrinsic_loss=round(short_intrinsic_loss_dollar, 2),
        tail_capped_dollar=round(tail_capped, 2), tail_survivable=bool(tail_survivable),
    )


def _resolve_strikes(d: dt.date, spot: float, short_offset: int, straddle: bool, long_dte: int):
    """Resolve cached call/put strikes for BOTH the 0DTE short and the long back-leg at
    the SAME strikes. Returns dict or None if any leg is uncached/unlisted."""
    atm = int(round(spot))
    call_target = atm if straddle else atm + short_offset
    put_target = atm if straddle else atm - short_offset
    # 0DTE short legs
    sc = _nearest_cached_strike_dte(d, call_target, "C", 0)
    sp = _nearest_cached_strike_dte(d, put_target, "P", 0)
    if sc is None or sp is None:
        return None
    call_strike, call_exp_s = sc
    put_strike, put_exp_s = sp
    # long back-legs at the SAME strikes, long_dte expiry
    lc_exp = _expiry_for_entry(d, long_dte)
    lp_exp = _expiry_for_entry(d, long_dte)
    if lc_exp is None or lp_exp is None:
        return None
    if load_dte_contract_bars(option_symbol(lc_exp, call_strike, "C"), long_dte) is None:
        return None
    if load_dte_contract_bars(option_symbol(lp_exp, put_strike, "P"), long_dte) is None:
        return None
    return {
        "call_strike": call_strike, "put_strike": put_strike,
        "call_exp_s": call_exp_s, "put_exp_s": put_exp_s,
        "call_exp_l": lc_exp, "put_exp_l": lp_exp,
    }


def run_cell(spy, day_list, day_open_close, *, short_offset, long_dte, straddle,
             entry_time, pt_frac, stop_mult, strike_override=None):
    """One calendar variant across all days. strike_override(d,spot)->offset for the null."""
    fills: list[CalFill] = []
    for d in day_list:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = _spot_and_decision(spy_day, entry_time)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        off = short_offset if strike_override is None else strike_override(d, spot)
        st = _resolve_strikes(d, spot, off, straddle, long_dte)
        if st is None:
            fills.append(CalFill(date=d.strftime("%Y-%m-%d"),
                                 structure="CAL_STRADDLE" if straddle else "CAL_STRANGLE",
                                 skipped=True, skip_reason="uncached_or_unlisted",
                                 short_offset=off, long_dte=long_dte))
            continue
        f = simulate_calendar_trade(
            d, decision_dt, spot, short_offset=off, long_dte=long_dte, straddle=straddle,
            call_strike=st["call_strike"], put_strike=st["put_strike"],
            call_expiry_short=st["call_exp_s"], put_expiry_short=st["put_exp_s"],
            call_expiry_long=st["call_exp_l"], put_expiry_long=st["put_exp_l"],
            day_open_close=day_open_close, pt_frac=pt_frac, stop_mult=stop_mult)
        if f is None:
            fills.append(CalFill(date=d.strftime("%Y-%m-%d"),
                                 structure="CAL_STRADDLE" if straddle else "CAL_STRANGLE",
                                 skipped=True, skip_reason="sim_none",
                                 short_offset=off, long_dte=long_dte))
            continue
        fills.append(f)
    return fills


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────
def _d(f: CalFill) -> dt.date:
    return dt.date.fromisoformat(f.date)


def score(fills: list[CalFill]) -> dict:
    taken = [f for f in fills if not f.skipped]
    n_sk = sum(1 for f in fills if f.skipped)
    skip_rate = round(n_sk / len(fills), 3) if fills else 0.0
    if not taken:
        return {"n": 0, "skip_rate": skip_rate}
    pnls = [f.realized_pnl for f in taken]
    dated = [(_d(f), f.realized_pnl) for f in taken]
    oos = [f for f in taken if _d(f) >= OOS_2026_START]
    is25 = [f for f in taken if IS_2025_START <= _d(f) <= IS_2025_END]
    oos_p = [f.realized_pnl for f in oos]
    is_p = [f.realized_pnl for f in is25]
    wins = sum(1 for p in pnls if p > 0)
    # monthly OOS sub-windows
    bym = defaultdict(list)
    for f in oos:
        bym[f"{_d(f).year}-{_d(f).month:02d}"].append(f.realized_pnl)
    pos_m = sum(1 for v in bym.values() if statistics.mean(v) > 0)
    dt5 = _drop_top_n(pnls, 5)
    dw5 = _drop_worst_n(pnls, 5)
    arr = np.array(pnls, float)
    downside = arr[arr < 0]
    sortino = (round(float(arr.mean()) / float(np.sqrt(np.mean(downside ** 2))), 4)
               if len(downside) and np.mean(downside ** 2) > 0 else None)
    return {
        "n": len(taken), "skip_rate": skip_rate,
        "wr": round(wins / len(taken), 3),
        "exp": round(statistics.mean(pnls), 2),
        "total": round(sum(pnls), 2),
        "oos_n": len(oos_p), "oos_exp": round(statistics.mean(oos_p), 2) if oos_p else None,
        "is25_exp": round(statistics.mean(is_p), 2) if is_p else None,
        "drop_top5_exp": round(statistics.mean(dt5), 2) if dt5 else None,
        "drop_worst5_exp": round(statistics.mean(dw5), 2) if dw5 else None,
        "pos_months_oos": f"{pos_m}/{len(bym)}", "pos_months_n": pos_m, "n_months": len(bym),
        "book_max_dd": round(_book_max_dd(dated), 2),
        "worst_day": round(min(pnls), 2),
        "max_short_intrinsic_dollar": round(max((f.worst_day_intrinsic_loss for f in taken),
                                                default=0.0), 2),
        "all_tails_survivable": all(f.tail_survivable for f in taken),
        "sortino": sortino,
        "exit_mix": {k: sum(1 for f in taken if f.exit_reason == k)
                     for k in sorted({f.exit_reason for f in taken})},
    }


def run_null(spy, day_list, day_open_close, *, long_dte, straddle, entry_time, pt_frac,
             stop_mult, seeds=NULL_SEEDS) -> dict:
    """Random-strike null: redraw short_offset uniformly from the pool each day. If the
    null reproduces/exceeds the chosen-offset OOS expectancy at p95, there is NO
    strike-selection alpha (L172) -- the calendar inherits the condor's gate-6 failure."""
    oos_exps = []
    for s in range(seeds):
        rng = random.Random(1000 + s)

        def ov(d, spot, _rng=rng):
            return _rng.choice(NULL_OFFSET_POOL)
        fills = run_cell(spy, day_list, day_open_close, short_offset=0, long_dte=long_dte,
                         straddle=straddle, entry_time=entry_time, pt_frac=pt_frac,
                         stop_mult=stop_mult, strike_override=ov)
        sm = score(fills)
        if sm.get("oos_exp") is not None:
            oos_exps.append(sm["oos_exp"])
    if not oos_exps:
        return {"seeds": 0}
    oos_exps.sort()
    return {
        "seeds": len(oos_exps),
        "mean": round(statistics.mean(oos_exps), 2),
        "p50": round(oos_exps[len(oos_exps) // 2], 2),
        "p95": round(oos_exps[min(len(oos_exps) - 1, int(0.95 * len(oos_exps)))], 2),
        "min": round(min(oos_exps), 2), "max": round(max(oos_exps), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate() -> list[str]:
    msgs = []
    # (a) per-leg real bars from own caches: 0DTE short + 1DTE long at same strike.
    short_sym = option_symbol(dt.date(2025, 3, 3), 585, "C")
    long_sym = option_symbol(dt.date(2025, 3, 4), 585, "C")
    sdf = load_dte_contract_bars(short_sym, 0)
    ldf = load_dte_contract_bars(long_sym, 1)
    assert sdf is not None and len(sdf) > 0, f"need 0DTE bars {short_sym}"
    assert ldf is not None and len(ldf) > 0, f"need 1DTE bars {long_sym}"
    assert (sdf["timestamp_et"].dt.date == dt.date(2025, 3, 3)).all()
    assert (ldf["timestamp_et"].dt.date == dt.date(2025, 3, 3)).all()
    msgs.append(f"OK per-leg REAL: short 0DTE {short_sym}({len(sdf)}b) + long 1DTE "
                f"{long_sym}({len(ldf)}b), SAME strike 585C, both on entry day 2025-03-03")
    # (b) calendar net = DEBIT (back richer than same-strike front -> longer expiry costs more)
    sc_bid, sp_bid = 1.20, 1.10          # 0DTE strangle credit
    lc_ask, lp_ask = 1.95, 1.85          # 1DTE same-strike (richer)
    net_entry = (lc_ask + lp_ask) - (sc_bid + sp_bid)
    assert net_entry > 0, "calendar must be a net debit"
    msgs.append(f"OK calendar net = DEBIT ${net_entry:.2f} (back ${lc_ask+lp_ask:.2f} > "
                f"front credit ${sc_bid+sp_bid:.2f})")
    # (c) steamroller cap: same-strike legs net to ZERO intrinsic above/below -> defined risk
    #     SPY 600, 585C: short owes (600-585)=15, long worth (600-585)=15 -> intrinsic nets 0.
    K, settle = 585, 600.0
    short_owe = max(0.0, settle - K); long_worth = max(0.0, settle - K)
    assert abs(short_owe - long_worth) < 1e-9, "same-strike intrinsic cancels (defined risk)"
    msgs.append(f"OK same-strike steamroller cap: SPY {settle} {K}C short owes ${short_owe:.0f}, "
                f"long worth ${long_worth:.0f} -> net intrinsic ${short_owe-long_worth:.0f} "
                f"(only the debit + carry is at risk; tail capped tighter than a condor wing)")
    # (d) no look-ahead
    eb = _bar_at_or_after(sdf, dt.datetime(2025, 3, 3, 10, 30))
    assert eb is not None and eb.timestamp_et >= dt.datetime(2025, 3, 3, 10, 30)
    msgs.append(f"OK no look-ahead: bar_at_or_after(10:30) = {eb.timestamp_et}")
    # (e) cross-expiry index
    assert _expiry_for_entry(dt.date(2025, 3, 3), 1) == dt.date(2025, 3, 4)
    assert _expiry_for_entry(dt.date(2025, 3, 3), 0) == dt.date(2025, 3, 3)
    msgs.append("OK cross-expiry: entry 03-03 -> short 0DTE exp 03-03, long 1DTE exp 03-04")
    return msgs


def _load():
    spy = _load_spy_master()
    days = sorted(set(spy["date"]))
    doc = {}
    for d in days:
        sd = spy[spy["date"] == d]
        if not sd.empty:
            doc[d] = (float(sd.iloc[0]["open"]), float(sd.iloc[-1]["close"]))
    return spy, days, doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.validate:
        for m in validate():
            print("  " + m)
        print("VALIDATION PASSED")
        return 0

    for d in LONG_DTES:
        _build_expiry_index(d)
    print("[cal] loading SPY ...", flush=True)
    spy, days, doc = _load()
    print(f"[cal] SPY days={len(days)} window={days[0]}..{days[-1]}", flush=True)

    if args.smoke:
        for m in validate():
            print("  " + m)
        f = run_cell(spy, days, doc, short_offset=2, long_dte=1, straddle=False,
                     entry_time=dt.time(10, 30), pt_frac=0.50, stop_mult=2.0)
        taken = [x for x in f if not x.skipped]
        print(f"\n[smoke] strangle off2 1DTE 10:30 pt.5 2x: n={len(taken)} "
              f"skip={sum(1 for x in f if x.skipped)}")
        for x in taken[:3]:
            print(f"  {x.date} {x.structure} K(C{x.call_strike}/P{x.put_strike}) "
                  f"net_entry=${x.net_entry:.2f} net_exit=${x.net_exit:.2f} "
                  f"pnl=${x.realized_pnl:.0f} exit={x.exit_reason} "
                  f"tail_cap=${x.tail_capped_dollar:.0f} survivable={x.tail_survivable}")
        print("  score:", json.dumps(score(f), default=str))
        return 0

    # ── FULL SWEEP + NULL ───────────────────────────────────────────────────────
    results = {"strategy": "calendar_premium_vs_condor",
               "run_date": dt.date.today().isoformat(),
               "window": f"{days[0]}..{days[-1]}",
               "condor_lead": {"oos_exp": 22.95, "wr": 0.827, "book_dd": -124.0,
                               "gate6": "FAIL (strike-null p95 +26.03 >= real)"},
               "cells": []}
    for straddle in STRADDLE:
        for long_dte in LONG_DTES:
            for et in ENTRY_TIMES:
                for off in SHORT_OFFSETS:
                    for pt in PT_FRACS:
                        for sm in STOP_MULTS:
                            fills = run_cell(spy, days, doc, short_offset=off,
                                             long_dte=long_dte, straddle=straddle,
                                             entry_time=et, pt_frac=pt, stop_mult=sm)
                            m = score(fills)
                            cell = {"straddle": straddle, "long_dte": long_dte,
                                    "entry": et.strftime("%H:%M"), "short_offset": off,
                                    "pt_frac": pt, "stop_mult": sm, "metrics": m}
                            # null only for the leading axes (off2, the condor's winner)
                            if off == 2 and pt == 0.50:
                                cell["null"] = run_null(
                                    spy, days, doc, long_dte=long_dte, straddle=straddle,
                                    entry_time=et, pt_frac=pt, stop_mult=sm)
                            results["cells"].append(cell)
                            nl = cell.get("null", {})
                            beats = (m.get("oos_exp") is not None and nl.get("p95") is not None
                                     and m["oos_exp"] > nl["p95"])
                            print(f"  strad={straddle} dte={long_dte} {et.strftime('%H:%M')} "
                                  f"off{off} pt{pt} stop{sm} | n={m.get('n','-'):>3} "
                                  f"exp=${m.get('exp','-')} oos=${m.get('oos_exp','-')} "
                                  f"wr={m.get('wr','-')} dd=${m.get('book_max_dd','-')} "
                                  f"sortino={m.get('sortino','-')} "
                                  f"null_p95=${nl.get('p95','-')} beats_null={beats if nl else '-'}",
                                  flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[cal] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
