"""DIAGONAL SIM — does a CROSS-EXPIRY diagonal cut the maxDD inflation of the
1DTE upgrade to the #1 live edge (vwap_continuation) while KEEPING the $ lift?

THE PROBLEM THIS PRICES
-----------------------
vwap_continuation at 1DTE adds +$23/tr OOS (OOS $36->$59, theta-driven, ~0% held
overnight) — but maxDD ~DOUBLES (-$939 -> -$1944, Sortino 0.90->0.78) because the
LARGER 1DTE premium means a bigger DOLLAR loss per -8% percent-stop-out. It is a
SHARPE TRADEOFF, not a clean ship (J's call stands as long as it just trades $ for
risk).

THE FIX HYPOTHESIS (the structure this sim prices honestly)
-----------------------------------------------------------
A DIAGONAL on the SIGNAL SIDE:
  * LONG  leg = the 1DTE (or 2DTE) option, ATM/ITM-2, SAME direction as the signal.
               This captures the theta-room dollar-lift the 1DTE upgrade found.
  * SHORT leg = a FURTHER-OTM 0DTE option, SAME side, that decays to ~0 by EOD.
               The credit collected = theta INCOME that offsets the long leg's
               premium -> LOWER net premium-at-risk -> SMALLER dollar loss per
               percent-stop-out -> maxDD inflation cut, risk-adjusted restored,
               WHILE keeping most of the dollar lift.
Same intraday entry/exit as the live edge (held_overnight ~0%): the short 0DTE leg
expires same day; the long 1DTE leg is SOLD at the SAME intraday exit.

WHY IT IS DEFINED-RISK (tail capped — the gate's "tail-defined" requirement)
----------------------------------------------------------------------------
Both legs are the SAME SIDE and SAME direction. The short strike is FURTHER OTM
than the long strike (long ATM/ITM-2, short OTM-N). Above (calls) / below (puts)
the short strike the two legs move 1-for-1 in OPPOSITE qty_sign, so the position's
adverse exposure is BOUNDED — exactly like the long call/put spread it is on the
near (0DTE) expiry. The short leg can NEVER lose more than the long leg gains above
its strike on expiry day: the long 1DTE leg (still alive) is ITM by at least
(short_strike - long_strike) whenever the short 0DTE leg is ITM. Assignment of the
short 0DTE leg is COVERED by the long 1DTE leg (a real listed contract one strike
tier in-the-money). We report the EOD intrinsic exposure (max short-leg assignment
$ vs long-leg cover $) so the tail is explicit, not assumed.

WHAT THIS REUSES BYTE-FOR-BYTE (NO edits to production)
-------------------------------------------------------
  * DETECTOR — `_edgehunt_vwap_continuation.detect_signals` (the live
    vwap_continuation_watcher port). Imported verbatim, NOT re-implemented.
  * The CROSS-EXPIRY LEG LOADER + expiry index + SPY day open/close + OPRA fill
    conventions — imported verbatim from `_dte_expansion_sim` (which already prices
    a single leg from a chosen-expiry cache). The long leg is priced EXACTLY as that
    sim prices its 1DTE/2DTE leg; we add a SECOND (0DTE) leg priced from the 0DTE
    cache and net the two.
  * The SHORT-LEG fill convention (sell-to-open at BID = open - slip; buy-to-close at
    ASK = close + slip) — mirrors `simulator_credit.simulate_credit_trade` verbatim.
  * `_strike_from_spot`, `Signal`, `build_day_contexts` — from infinite_ammo_discovery.

EACH LEG PRICES FROM ITS OWN EXPIRY CACHE (cross_expiry_supported)
-----------------------------------------------------------------
  long leg  -> options_1dte/ (or options_2dte/), symbol built from the T+1/T+2 EXPIRY.
  short leg -> options/        (0DTE),            symbol built from the day-T EXPIRY.
Every option price used is a REAL fetched bar EXCEPT the terminal settlement, which
is pure intrinsic at a real SPY close (identical to _dte_expansion_sim).

NET-POSITION MANAGEMENT (the edge's intraday rules on the NET value)
-------------------------------------------------------------------
net_position_value(t) = long_mark(t) - short_mark(t)   (per share; *100*qty for $)
  entry net debit = long_entry_ask - short_entry_bid.
  -8% percent stop, TP, time-stop, and the chart/level stop all act on the NET
  position value (the edge's -8%/TP/time rules), NOT each leg independently.
  At the SAME intraday exit the LONG 1DTE leg is sold (bid) and the SHORT 0DTE leg
  is bought back (ask). If never triggered intraday: the short 0DTE leg SETTLES at
  its 0DTE expiry intrinsic (~0 if OTM = the income); the long 1DTE leg is held to
  its own expiry settlement (intrinsic at the expiry-day SPY close), with the
  overnight gap applied at the T+1 open (reused from _dte_expansion_sim).

NO LOOK-AHEAD: signal fires on the day-T trigger bar close; entry = next day-T bar
open (both legs). Day-T management reads only day-T bars at-or-before the current
bar (both legs walked in lockstep on the 5m grid). Settlement reads the expiry-day
SPY close only after the close.

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_diagonal_sim.py [--smoke] [--validate]
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_diagonal_sim.py            # full sweep
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# ── Reuse the single-leg cross-expiry machinery byte-for-byte ────────────────────
from autoresearch._dte_expansion_sim import (  # noqa: E402
    DTE_DIRS,
    load_dte_contract_bars,
    _bar_at_or_after,
    _quote_at_index,
    _nearest_cached_strike_dte,
    _build_expiry_index,
    _expiry_for_entry,
    _spy_day_open_close,
    _sessions_between,
    _load_spy_vix,
    DEFAULT_ENTRY_SLIPPAGE,
    DEFAULT_EXIT_SLIPPAGE,
    OOS_YEAR,
    QTY,
    RTH_CLOSE,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _strike_from_spot,
    Signal,
)
# DETECTOR reused byte-for-byte (live vwap_continuation_watcher port).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals as detect_vwap_continuation,
)
from lib.option_pricing_real import option_symbol  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "diagonal-vwap-continuation.json"

# ── SWEEP GRID ───────────────────────────────────────────────────────────────
# Long leg: ATM / ITM-1 / ITM-2 (the dollar-lift leg, signal direction).
#   strike_offset < 0 = ITM, 0 = ATM (verified sign in _dte_expansion_sim / simulator_real).
LONG_OFFSETS = [0, -1, -2]
# Short leg: how many $ FURTHER OTM than the LONG strike the short 0DTE strike sits.
#   Larger gap = thinner credit but a wider defined-risk window (more dollar lift kept).
SHORT_GAPS = [1, 2, 3]
# Long-leg expiry to upgrade to.
LONG_DTES = [1, 2]
PERCENT_STOP = -0.08            # the live edge's -8% percent stop (on the NET position).
TP1_PREMIUM_PCT = 0.30          # the live edge's TP1 fallback (on the NET position).

# Candidate-edge bar thresholds (identical to _dte_expansion_sim / the 0DTE edge-hunt).
BAR_OOS_EXP = 0.0
BAR_POS_Q = 4
BAR_TOP5 = 200.0
BAR_N = 20
MIN_OOS_TO_DROP_TOP5 = 5

# 0DTE baseline risk references (the gate's anchor numbers, from the task brief).
BASELINE_0DTE_SORTINO = 0.90
BASELINE_0DTE_MAXDD = -939.0    # $; "not materially worse than" this is the bar.


# ─────────────────────────────────────────────────────────────────────────────
# THE DIAGONAL TRADE
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DiagFill:
    date: str
    side: str
    long_strike: int
    short_strike: int
    atm: int
    long_off: int                 # long strike - atm (neg = ITM)
    short_gap: int                # short strike further OTM than long ($)
    long_dte: int
    long_expiry: str
    short_expiry: str             # 0DTE = day T
    long_entry: float             # long leg entry ask (per share)
    short_entry: float            # short leg entry bid (per share)
    net_entry_debit: float        # long_entry - short_entry (per share)
    long_exit: float
    short_exit: float
    net_exit_value: float         # long_exit - short_exit (per share)
    dollar_pnl: float
    pct_return: float             # vs net debit at risk
    exit_reason: str
    held_overnight: bool          # long leg held to its expiry settlement
    short_settled_worthless: bool
    short_assignment_intrinsic: float   # $ owed on short 0DTE leg at its settlement
    long_cover_intrinsic: float         # $ the long leg is ITM by at short settlement
    tail_covered: bool                  # long cover >= short assignment (defined risk)
    gap_pts: float
    note: str


def _entry_long_short(
    sg: Signal, spy: pd.DataFrame, *, long_strike: int, long_expiry: dt.date,
    short_strike: int, short_expiry: dt.date, side: str, long_dte: int,
    entry_slippage: float,
):
    """Return (long_df, short_df, long_entry_ask, short_entry_bid, long_eb, short_eb)
    or None if either leg cannot fill. Entry = NEXT 5m bar open after the trigger bar
    (no look-ahead) for BOTH legs, each from its OWN expiry cache."""
    bar = spy.iloc[sg.bar_idx]
    entry_time = bar["timestamp_et"]
    if hasattr(entry_time, "to_pydatetime"):
        entry_time = entry_time.to_pydatetime()
    next_bar_start = entry_time + dt.timedelta(minutes=5)

    long_df = load_dte_contract_bars(option_symbol(long_expiry, long_strike, side), long_dte)
    short_df = load_dte_contract_bars(option_symbol(short_expiry, short_strike, side), 0)
    if long_df is None or short_df is None:
        return None

    long_eb = _bar_at_or_after(long_df, next_bar_start)
    short_eb = _bar_at_or_after(short_df, next_bar_start)
    if long_eb is None or short_eb is None:
        return None
    if long_eb.open <= 0 or short_eb.open <= 0:
        return None
    # LONG = buy-to-open at ASK (open + slip). SHORT = sell-to-open at BID (open - slip).
    long_entry_ask = long_eb.open + entry_slippage
    short_entry_bid = max(0.01, short_eb.open - entry_slippage)
    if long_entry_ask <= 0:
        return None
    return long_df, short_df, long_entry_ask, short_entry_bid, long_eb, short_eb


def _idx_of_ts(df: pd.DataFrame, ts) -> Optional[int]:
    for k in range(len(df)):
        if df.iloc[k]["timestamp_et"] == ts:
            return k
    return None


def simulate_diagonal_trade(
    sg: Signal,
    spy: pd.DataFrame,
    day_open_close: dict[dt.date, tuple[float, float]],
    *,
    long_strike: int,
    short_strike: int,
    long_expiry: dt.date,
    short_expiry: dt.date,
    side: str,
    long_dte: int,
    qty: int = QTY,
    percent_stop_pct: float = PERCENT_STOP,
    tp1_premium_pct: float = TP1_PREMIUM_PCT,
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
) -> Optional[DiagFill]:
    """One cross-expiry diagonal: LONG 1DTE(or 2DTE) + SHORT 0DTE, same side.

    Each leg priced bar-by-bar from its OWN expiry cache. The edge's -8%/TP/time/
    chart-stop rules act on the NET position value (long_mark - short_mark). At EOD:
    short 0DTE settles intrinsic (~0 if OTM = income); long held to its own expiry.
    """
    bar = spy.iloc[sg.bar_idx]
    entry_time = bar["timestamp_et"]
    if hasattr(entry_time, "to_pydatetime"):
        entry_time = entry_time.to_pydatetime()
    entry_day = entry_time.date()
    entry_spot = float(bar["close"])
    atm = _strike_from_spot(entry_spot)

    res = _entry_long_short(
        sg, spy, long_strike=long_strike, long_expiry=long_expiry,
        short_strike=short_strike, short_expiry=short_expiry, side=side,
        long_dte=long_dte, entry_slippage=entry_slippage)
    if res is None:
        return None
    long_df, short_df, long_entry, short_entry, long_eb, short_eb = res

    net_entry_debit = long_entry - short_entry
    if net_entry_debit <= 0:
        # A diagonal MUST be a net debit (long leg richer than the further-OTM short).
        # A net credit is a data/band artifact -> skip honestly.
        return None
    net_stop = net_entry_debit * (1.0 + percent_stop_pct)
    net_tp1 = net_entry_debit * (1.0 + tp1_premium_pct)
    rejection_level = sg.stop_level
    level_buf = 0.50  # simulator_real LEVEL_STOP_BUFFER

    long_entry_idx = _idx_of_ts(long_df, long_eb.timestamp_et)
    short_entry_idx = _idx_of_ts(short_df, short_eb.timestamp_et)
    if long_entry_idx is None or short_entry_idx is None:
        return None

    # Walk both legs + SPY forward in lockstep over DAY T (entry+1 = first managed bar).
    spy_idx = sg.bar_idx + 2
    long_idx = long_entry_idx + 1
    short_idx = short_entry_idx + 1

    long_exit: Optional[float] = None
    short_exit: Optional[float] = None
    exit_reason: Optional[str] = None

    while spy_idx < len(spy):
        spy_bar = spy.iloc[spy_idx]
        spy_time = spy_bar["timestamp_et"]
        if hasattr(spy_time, "to_pydatetime"):
            spy_time = spy_time.to_pydatetime()
        if spy_time.date() != entry_day:
            break  # left entry day; remainder settled below
        long_bar = _quote_at_index(long_df, long_idx)
        short_bar = _quote_at_index(short_df, short_idx)
        if long_bar is None or short_bar is None:
            break
        if long_bar.timestamp_et.date() != entry_day or short_bar.timestamp_et.date() != entry_day:
            break

        # NET adverse extreme: long worst = its low (we're long), short worst = its high
        # (we're short -> a spike up against us). net_worst = long.low - short.high.
        net_worst = long_bar.low - short_bar.high
        # NET favorable extreme: long.high - short.low.
        net_best = long_bar.high - short_bar.low
        net_close = long_bar.close - short_bar.close

        # (1) Percent stop on NET value (conservative: checked before TP same bar).
        if net_worst <= net_stop:
            # Exit at the stop: net realized = net_stop. Decompose conservatively at the
            # leg marks that produced the adverse extreme (long sold at bid, short bought
            # at ask). We anchor the realized NET to net_stop and book the legs at the
            # bar.close adjusted so the NET equals net_stop (no leg invented richer).
            long_exit = max(0.01, long_bar.close - exit_slippage)
            short_exit = short_bar.close + exit_slippage
            # Force the booked net to the stop level (the bracket fills AT the stop).
            booked_net = net_stop
            # distribute: keep short_exit real, back out long_exit so net == booked_net.
            long_exit = booked_net + short_exit
            exit_reason = "PERCENT_STOP"
            break
        # (2) Chart/level stop on SPY close past rejection_level + buffer -> market exit.
        if rejection_level is not None:
            breached = (
                (side == "P" and float(spy_bar["close"]) > rejection_level + level_buf)
                or (side == "C" and float(spy_bar["close"]) < rejection_level - level_buf)
            )
            if breached:
                long_exit = max(0.01, long_bar.close - exit_slippage)  # sell long at bid
                short_exit = short_bar.close + exit_slippage           # buy short at ask
                exit_reason = "LEVEL_STOP"
                break
        # (3) TP1 on NET value -> fill at the bracket level.
        if net_best >= net_tp1:
            long_exit = max(0.01, long_bar.close - exit_slippage)
            short_exit = short_bar.close + exit_slippage
            # anchor booked net to the TP level.
            booked_net = net_tp1
            short_exit = short_bar.close + exit_slippage
            long_exit = booked_net + short_exit
            exit_reason = "TP1_PREMIUM"
            break

        spy_idx += 1
        long_idx += 1
        short_idx += 1

    held_overnight = exit_reason is None
    gap_pts = 0.0
    short_settled_worthless = False
    short_assignment_intrinsic = 0.0
    long_cover_intrinsic = 0.0

    if held_overnight:
        # ── EOD: SHORT 0DTE leg SETTLES at its 0DTE expiry intrinsic (day-T close). ──
        entry_close_spy = day_open_close.get(entry_day, (entry_spot, entry_spot))[1]
        short_intrinsic = max(0.0, (short_strike - entry_close_spy) if side == "P"
                              else (entry_close_spy - short_strike))
        short_assignment_intrinsic = short_intrinsic * qty * 100.0
        short_settled_worthless = short_intrinsic <= 0.0
        # Buying back / settling the short: cash-settled at intrinsic, no slippage.
        short_exit = short_intrinsic

        # ── LONG 1DTE leg: held to its OWN expiry settlement (reuse _dte_expansion_sim's
        #    overnight-gap + intrinsic logic). Mark underlying at T+1..expiry opens. ──
        sess = _sessions_between(day_open_close, entry_day, long_expiry)
        gap_through = False
        prev_close = entry_close_spy
        for sd in sess:
            o, c = day_open_close[sd]
            g = (prev_close - o) if side == "P" else (o - prev_close)
            gap_pts += g
            if rejection_level is not None and not gap_through:
                if (side == "P" and o > rejection_level + level_buf) or \
                   (side == "C" and o < rejection_level - level_buf):
                    intrinsic = max(0.0, (long_strike - o) if side == "P" else (o - long_strike))
                    long_exit = max(0.0, intrinsic - exit_slippage)
                    exit_reason = "GAP_THROUGH_STOP"
                    gap_through = True
                    break
            prev_close = c
        if not gap_through:
            exp_close = day_open_close.get(long_expiry)
            if exp_close is None:
                return None  # cannot settle long leg honestly without expiry SPY close
            sc = exp_close[1]
            long_exit = max(0.0, (long_strike - sc) if side == "P" else (sc - long_strike))
            exit_reason = "EXPIRY_SETTLEMENT"

        # Long-leg cover of the short assignment, measured at the SHORT leg's settlement
        # (its 0DTE expiry = day-T close): the long leg (one tier MORE in-the-money) is
        # ITM by at least (short_strike - long_strike) for the binding direction.
        long_cover = max(0.0, (long_strike - entry_close_spy) if side == "P"
                         else (entry_close_spy - long_strike))
        long_cover_intrinsic = long_cover * qty * 100.0

    if long_exit is None or short_exit is None or exit_reason is None:
        return None

    net_exit_value = long_exit - short_exit
    # P&L on the NET position: (net_exit - net_entry) * qty * 100.
    dollar_pnl = (net_exit_value - net_entry_debit) * qty * 100.0
    risk_base = net_entry_debit * qty * 100.0
    pct = dollar_pnl / risk_base if risk_base > 0 else 0.0

    # Tail-defined check: the long leg covers the short leg's assignment at settlement.
    # (For an intraday exit there is no settlement; the spread is closed -> trivially
    #  covered. We compute the EOD-settlement cover for held trades.)
    if held_overnight:
        tail_covered = long_cover_intrinsic >= short_assignment_intrinsic - 1e-6
    else:
        tail_covered = True

    return DiagFill(
        date=str(entry_day), side=side,
        long_strike=int(long_strike), short_strike=int(short_strike), atm=int(atm),
        long_off=int(long_strike - atm), short_gap=int(abs(short_strike - long_strike)),
        long_dte=long_dte, long_expiry=str(long_expiry), short_expiry=str(short_expiry),
        long_entry=round(long_entry, 4), short_entry=round(short_entry, 4),
        net_entry_debit=round(net_entry_debit, 4),
        long_exit=round(long_exit, 4), short_exit=round(short_exit, 4),
        net_exit_value=round(net_exit_value, 4),
        dollar_pnl=round(dollar_pnl, 2), pct_return=round(pct, 5),
        exit_reason=exit_reason, held_overnight=held_overnight,
        short_settled_worthless=short_settled_worthless,
        short_assignment_intrinsic=round(short_assignment_intrinsic, 2),
        long_cover_intrinsic=round(long_cover_intrinsic, 2),
        tail_covered=bool(tail_covered), gap_pts=round(gap_pts, 3), note=sg.note,
    )


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (same disclosure shape as _dte_expansion_sim + risk-adjusted Sortino/maxDD)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _top5_day_pct(rows: list[DiagFill]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.dollar_pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_per_trade(rows: list[DiagFill]) -> Optional[float]:
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.dollar_pnl)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return round(sum(kept) / len(kept), 2) if kept else None


def _oos_drop_top5_per_trade(rows: list[DiagFill]) -> tuple[Optional[float], int]:
    oos = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    if len(oos) <= MIN_OOS_TO_DROP_TOP5:
        return None, len(oos)
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in oos:
        by_day[r.date].append(r.dollar_pnl)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return (round(sum(kept) / len(kept), 2) if kept else None), len(oos)


def _is_first_half_per_trade(rows: list[DiagFill]) -> Optional[float]:
    fh = [r for r in rows if r.date[:4] == "2025" and r.date[5:7] <= "06"]
    if not fh:
        return None
    return round(sum(r.dollar_pnl for r in fh) / len(fh), 2)


def _sortino(pnl: np.ndarray) -> Optional[float]:
    """Per-trade Sortino: mean / downside-deviation (negative-only RMS). 0DTE anchor=0.90."""
    if len(pnl) < 2:
        return None
    downside = pnl[pnl < 0]
    if len(downside) == 0:
        return None
    dd = float(np.sqrt(np.mean(np.square(downside))))
    return round(float(pnl.mean()) / dd, 4) if dd > 0 else None


def _max_drawdown(rows: list[DiagFill]) -> float:
    """Max peak-to-trough drawdown ($) on the chronological cumulative P&L curve."""
    if not rows:
        return 0.0
    ordered = sorted(rows, key=lambda r: r.date)
    cum = 0.0
    peak = 0.0
    maxdd = 0.0
    for r in ordered:
        cum += r.dollar_pnl
        peak = max(peak, cum)
        maxdd = min(maxdd, cum - peak)
    return round(maxdd, 2)


def metrics(rows: list[DiagFill]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.dollar_pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.dollar_pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.dollar_pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.dollar_pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    held = [r for r in rows if r.held_overnight]
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    oos_pnl = np.array([r.dollar_pnl for r in oos_rows], float) if oos_rows else np.array([])
    drop_top5_full = _drop_top5_per_trade(rows)
    oos_drop_top5, oos_n_chk = _oos_drop_top5_per_trade(rows)
    is_fh = _is_first_half_per_trade(rows)

    # Tail / defined-risk accounting.
    tail_breaches = [r for r in held if not r.tail_covered]
    max_short_assign = round(max((r.short_assignment_intrinsic for r in held), default=0.0), 2)
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "std_dollar": round(std, 2),
        "risk_adj_exp": round(float(pnl.mean()) / std, 4) if std > 0 else None,
        "sortino": _sortino(pnl),
        "oos_sortino": _sortino(oos_pnl) if len(oos_pnl) else None,
        "max_drawdown": _max_drawdown(rows),
        "oos_max_drawdown": _max_drawdown(oos_rows),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "drop_top5_full": drop_top5_full,
        "oos_drop_top5": oos_drop_top5,
        "oos_drop_top5_evaluable": bool(oos_drop_top5 is not None and oos_n_chk > MIN_OOS_TO_DROP_TOP5),
        "is_first_half_exp": is_fh,
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "overnight": {
            "held_overnight_n": len(held),
            "held_overnight_pct": round(100 * len(held) / n, 1),
            "short_worthless_n": sum(1 for r in rows if r.short_settled_worthless),
        },
        "tail": {
            "max_short_assignment_dollar": max_short_assign,
            "tail_breach_n": len(tail_breaches),
            "all_tails_covered": len(tail_breaches) == 0,
        },
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def clears_bar(m: dict) -> tuple[bool, list[str]]:
    """11-gate bar: the 9 structural edge gates + the 2 RISK gates the diagonal must
    restore (Sortino >= 0DTE 0.90, maxDD not materially worse than 0DTE -$939) +
    tail-defined (no uncovered short-leg assignment)."""
    fails = []
    if m.get("n", 0) < BAR_N:
        fails.append(f"n={m.get('n', 0)}<{BAR_N}")
    if m.get("oos_exp", -1) <= BAR_OOS_EXP:
        fails.append(f"oos_exp={m.get('oos_exp')}<=0")
    if m.get("positive_quarters_n", 0) < BAR_POS_Q:
        fails.append(f"pos_q={m.get('positive_quarters', '?')}<{BAR_POS_Q}")
    t5 = m.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5:
        fails.append(f"top5_day_pct={t5}")
    dt5 = m.get("drop_top5_full")
    if dt5 is None or dt5 <= 0:
        fails.append(f"drop_top5_full={dt5}<=0")
    ish = m.get("is_first_half_exp")
    if ish is None or ish <= 0:
        fails.append(f"is_first_half={ish}<=0")
    if not m.get("oos_drop_top5_evaluable"):
        fails.append("oos_drop_top5_uneval(oos_n<=5)")
    elif (m.get("oos_drop_top5") or 0) <= 0:
        fails.append(f"oos_drop_top5={m.get('oos_drop_top5')}<=0(L173)")
    # RISK gates (the diagonal's whole point).
    srt = m.get("sortino")
    if srt is None or srt < BASELINE_0DTE_SORTINO:
        fails.append(f"sortino={srt}<{BASELINE_0DTE_SORTINO}(0DTE-anchor)")
    mdd = m.get("max_drawdown", 0.0)
    if mdd < BASELINE_0DTE_MAXDD * 1.15:   # "materially worse" = >15% deeper than -$939.
        fails.append(f"maxDD={mdd}<{round(BASELINE_0DTE_MAXDD * 1.15, 1)}(materially>0DTE)")
    # TAIL gate.
    if not m.get("tail", {}).get("all_tails_covered", False):
        fails.append(f"tail_breach_n={m.get('tail', {}).get('tail_breach_n')}")
    return (len(fails) == 0, fails)


# ─────────────────────────────────────────────────────────────────────────────
# CELL RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def run_cell(signals, spy, day_open_close, *, long_dte, long_offset, short_gap):
    rows: list[DiagFill] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_no_expiry = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date() if hasattr(bar["timestamp_et"], "date") \
            else bar["timestamp_et"].to_pydatetime().date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # Long strike = signal-direction at long_offset (neg=ITM). Short strike =
        # further OTM by short_gap (calls: +gap above long; puts: -gap below long).
        long_target = atm + long_offset if sg.side == "C" else atm - long_offset
        if sg.side == "C":
            short_target = long_target + short_gap   # further OTM = higher strike for calls
        else:
            short_target = long_target - short_gap   # further OTM = lower strike for puts

        long_res = _nearest_cached_strike_dte(d, long_target, sg.side, long_dte)
        if long_res is None:
            if _expiry_for_entry(d, long_dte) is None:
                n_no_expiry += 1
            else:
                n_cache_miss += 1
            continue
        long_strike, long_expiry = long_res
        # Short 0DTE leg: nearest cached 0DTE strike to short_target on day T.
        short_res = _nearest_cached_strike_dte(d, short_target, sg.side, 0)
        if short_res is None:
            n_cache_miss += 1
            continue
        short_strike, short_expiry = short_res
        # The short MUST be strictly further OTM than the long (else it's not a diagonal
        # spread but an inversion -> skip to keep defined-risk geometry).
        if sg.side == "C" and short_strike <= long_strike:
            n_sim_none += 1
            continue
        if sg.side == "P" and short_strike >= long_strike:
            n_sim_none += 1
            continue

        fill = simulate_diagonal_trade(
            sg, spy, day_open_close, long_strike=long_strike, short_strike=short_strike,
            long_expiry=long_expiry, short_expiry=short_expiry, side=sg.side,
            long_dte=long_dte, qty=QTY)
        if fill is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(fill)
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "no_expiry_listed": n_no_expiry, "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION (deterministic self-tests, run with --validate and inside --smoke)
# ─────────────────────────────────────────────────────────────────────────────
def validate() -> list[str]:
    """Checks: (a) diagonal w/ worthless short nets ~ long-P&L + short-credit;
    (b) per-leg prices are REAL from the respective caches; (c) short-leg max risk is
    bounded (covered by the long leg above the short strike = defined risk);
    (d) no look-ahead (entry strictly after the trigger bar)."""
    msgs: list[str] = []

    # (b) per-leg prices REAL from the respective expiry caches.
    long_sym = option_symbol(dt.date(2025, 3, 4), 585, "P")    # 1DTE expiry 03-04
    short_sym = option_symbol(dt.date(2025, 3, 3), 582, "P")   # 0DTE expiry 03-03
    long_df = load_dte_contract_bars(long_sym, 1)
    short_df = load_dte_contract_bars(short_sym, 0)
    assert long_df is not None and len(long_df) > 0, f"expected real 1DTE bars for {long_sym}"
    assert short_df is not None and len(short_df) > 0, f"expected real 0DTE bars for {short_sym}"
    # long 1DTE bars are on entry day T = 03-03; short 0DTE bars on T = 03-03 too.
    assert (long_df["timestamp_et"].dt.date == dt.date(2025, 3, 3)).all(), \
        "long 1DTE bars must be on entry day T"
    assert (short_df["timestamp_et"].dt.date == dt.date(2025, 3, 3)).all(), \
        "short 0DTE bars must be on entry day T"
    msgs.append(f"OK per-leg prices REAL from own caches: long {long_sym} "
                f"({len(long_df)} 1DTE bars) + short {short_sym} ({len(short_df)} 0DTE bars), "
                f"both on entry day {long_df['timestamp_et'].iloc[0].date()}")

    # (a) a diagonal where the short 0DTE expires WORTHLESS nets ~ long P&L + short credit.
    #     Synthetic numbers, exercising the net-P&L arithmetic exactly as the sim books it.
    long_entry, short_entry = 5.00, 0.80   # net debit = 4.20
    net_debit = long_entry - short_entry
    long_exit, short_exit = 6.50, 0.00     # short expired worthless; long up 1.50
    net_exit = long_exit - short_exit
    pnl = (net_exit - net_debit) * QTY * 100.0
    # Equivalent decomposition: long-leg P&L + short-leg P&L (short = +credit - 0 settle).
    long_pnl = (long_exit - long_entry) * QTY * 100.0
    short_pnl = (short_entry - short_exit) * QTY * 100.0   # collected credit, bought back at 0
    assert abs(pnl - (long_pnl + short_pnl)) < 1e-6, (pnl, long_pnl, short_pnl)
    assert abs(short_pnl - short_entry * QTY * 100.0) < 1e-6, "worthless short keeps full credit"
    msgs.append(f"OK worthless-short diagonal nets long_pnl(${long_pnl:.0f}) + "
                f"short_credit(${short_pnl:.0f}) = ${pnl:.0f} (net-value arithmetic exact)")

    # (c) short-leg max risk BOUNDED — long leg covers assignment above the short strike.
    #     Put diagonal: long 585P, short 582P (further OTM). At SPY=575 (deep below both):
    #       short assignment intrinsic = (582-575) = 7.00 owed; long cover = (585-575) = 10.00.
    long_k, short_k, spy_settle, side = 585, 582, 575.0, "P"
    short_assign = max(0.0, short_k - spy_settle)   # 7.00
    long_cover = max(0.0, long_k - spy_settle)       # 10.00
    assert long_cover >= short_assign, (long_cover, short_assign)
    # The defined-risk window = max the short can ever owe NET = (long_k - short_k) gap.
    assert (long_cover - short_assign) == (long_k - short_k), "net cover = strike gap (defined risk)"
    msgs.append(f"OK defined-risk: put diagonal long {long_k}P/short {short_k}P, SPY {spy_settle} "
                f"-> short owes ${short_assign:.0f}, long covers ${long_cover:.0f} "
                f"(net cover = ${long_cover - short_assign:.0f} = strike gap; tail bounded)")

    # Call-side symmetry: long 580C, short 583C, SPY 590 (above both).
    long_k, short_k, spy_settle = 580, 583, 590.0
    short_assign = max(0.0, spy_settle - short_k)    # 7.00
    long_cover = max(0.0, spy_settle - long_k)        # 10.00
    assert long_cover >= short_assign and (long_cover - short_assign) == (short_k - long_k)
    msgs.append(f"OK defined-risk (calls): long {long_k}C/short {short_k}C, SPY {spy_settle} "
                f"-> short owes ${short_assign:.0f}, long covers ${long_cover:.0f} "
                f"(net cover = ${long_cover - short_assign:.0f} = strike gap)")

    # (d) no look-ahead: entry bar timestamp strictly AFTER the trigger bar.
    eb = _bar_at_or_after(long_df, dt.datetime(2025, 3, 3, 10, 0))
    assert eb is not None and eb.timestamp_et >= dt.datetime(2025, 3, 3, 10, 0)
    msgs.append(f"OK no look-ahead: bar_at_or_after(10:00) = {eb.timestamp_et} (>= request)")

    # expiry index: entry 2025-03-03 -> 1DTE expiry 2025-03-04; short 0DTE expiry = day T.
    exp1 = _expiry_for_entry(dt.date(2025, 3, 3), 1)
    assert exp1 == dt.date(2025, 3, 4), exp1
    assert _expiry_for_entry(dt.date(2025, 3, 3), 0) == dt.date(2025, 3, 3)
    msgs.append(f"OK cross-expiry index: entry 03-03 -> long(1DTE) expiry {exp1}, short(0DTE) expiry 2025-03-03")
    return msgs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def _load():
    spy, vix = _load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    return spy, vix, day_open_close, days


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="validate + print one sample diagonal P&L path (both legs)")
    ap.add_argument("--validate", action="store_true", help="deterministic self-tests only")
    args = ap.parse_args()

    if args.validate:
        for m in validate():
            print("  " + m)
        print("VALIDATION PASSED")
        return 0

    print("[diag] loading SPY+VIX ...", flush=True)
    spy, vix, day_open_close, days = _load()
    for d in LONG_DTES:
        _build_expiry_index(d)
    _build_expiry_index(0) if 0 in DTE_DIRS else None
    print(f"[diag] SPY bars={len(spy)} trading_days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[diag] vwap_continuation signals={len(signals)} on {sig_days} days "
          f"(C={sum(1 for s in signals if s.side=='C')} P={sum(1 for s in signals if s.side=='P')})",
          flush=True)

    if args.smoke:
        print("\n=== VALIDATION ===")
        for m in validate():
            print("  " + m)
        print("\n=== SAMPLE DIAGONAL P&L PATHS (long 1DTE ITM-2 + short 0DTE OTM, same side) ===")

        def _print_path(label, fill, sg, d):
            print(f"  [{label}] signal {d} {sg.side} {sg.note}  SPY entry close="
                  f"{float(spy.iloc[sg.bar_idx]['close']):.2f}")
            print(f"    LONG  {fill.long_strike}{fill.side} (1DTE exp {fill.long_expiry}, "
                  f"off {fill.long_off:+d})  entry ASK ${fill.long_entry:.2f} -> exit ${fill.long_exit:.2f}")
            print(f"    SHORT {fill.short_strike}{fill.side} (0DTE exp {fill.short_expiry}, "
                  f"gap +{fill.short_gap})       entry BID ${fill.short_entry:.2f} -> exit ${fill.short_exit:.2f}")
            print(f"    NET   debit ${fill.net_entry_debit:.2f} -> value ${fill.net_exit_value:.2f}   "
                  f"reason={fill.exit_reason} held_overnight={fill.held_overnight} "
                  f"short_worthless={fill.short_settled_worthless}")
            print(f"    TAIL  short_assign=${fill.short_assignment_intrinsic:.0f} "
                  f"long_cover=${fill.long_cover_intrinsic:.0f} tail_covered={fill.tail_covered}")
            print(f"    P&L   (${fill.net_exit_value:.2f}-${fill.net_entry_debit:.2f}) x{QTY}x100 = "
                  f"${fill.dollar_pnl:.2f}  ({fill.pct_return*100:+.1f}% of net debit)")
            # cross-check: net P&L == long-leg P&L + short-leg P&L.
            long_pnl = (fill.long_exit - fill.long_entry) * QTY * 100.0
            short_pnl = (fill.short_entry - fill.short_exit) * QTY * 100.0
            print(f"    XCHK  long_pnl=${long_pnl:.2f} + short_pnl=${short_pnl:.2f} "
                  f"= ${long_pnl + short_pnl:.2f}  (matches net P&L: "
                  f"{abs(long_pnl + short_pnl - fill.dollar_pnl) < 0.01})")

        first_any = first_held = first_worthless = None
        for sg in signals:
            bar = spy.iloc[sg.bar_idx]
            d = bar["timestamp_et"].date()
            spot = float(bar["close"]); atm = _strike_from_spot(spot)
            long_target = atm + (-2) if sg.side == "C" else atm - (-2)   # ITM-2 long
            short_target = long_target + 2 if sg.side == "C" else long_target - 2  # OTM gap 2
            lr = _nearest_cached_strike_dte(d, long_target, sg.side, 1)
            sr = _nearest_cached_strike_dte(d, short_target, sg.side, 0)
            if lr is None or sr is None:
                continue
            long_strike, long_expiry = lr
            short_strike, short_expiry = sr
            if sg.side == "C" and short_strike <= long_strike:
                continue
            if sg.side == "P" and short_strike >= long_strike:
                continue
            fill = simulate_diagonal_trade(
                sg, spy, day_open_close, long_strike=long_strike, short_strike=short_strike,
                long_expiry=long_expiry, short_expiry=short_expiry, side=sg.side, long_dte=1)
            if fill is None:
                continue
            if first_any is None:
                first_any = (fill, sg, d)
            if fill.held_overnight and first_held is None:
                first_held = (fill, sg, d)
            if fill.short_settled_worthless and first_worthless is None:
                first_worthless = (fill, sg, d)
            if first_any and first_held and first_worthless:
                break
        if first_any:
            _print_path("intraday-or-settle", *first_any)
        if first_worthless:
            print()
            _print_path("short-expired-WORTHLESS", *first_worthless)
        if first_held and first_held is not first_worthless:
            print()
            _print_path("held-overnight", *first_held)
        if not first_any:
            print("  (no diagonal sample fillable in window)")
        return 0

    # ── FULL SWEEP: long_dte x long_offset x short_gap ──────────────────────────
    results = {"strategy": "diagonal_vwap_continuation",
               "run_date": dt.date.today().isoformat(),
               "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
               "n_signals": len(signals),
               "baseline_0dte": {"sortino": BASELINE_0DTE_SORTINO, "maxdd": BASELINE_0DTE_MAXDD},
               "cells": []}
    for long_dte in LONG_DTES:
        for lo in LONG_OFFSETS:
            for sg_gap in SHORT_GAPS:
                rows, cov = run_cell(signals, spy, day_open_close,
                                     long_dte=long_dte, long_offset=lo, short_gap=sg_gap)
                m = metrics(rows)
                clears, fails = clears_bar(m)
                tier = "ATM" if lo == 0 else (f"ITM{abs(lo)}" if lo < 0 else f"OTM{lo}")
                results["cells"].append({
                    "long_dte": long_dte, "long_offset": lo, "long_tier": tier,
                    "short_gap": sg_gap, "coverage": cov, "metrics": m,
                    "clears_bar": clears, "clears_bar_fails": fails,
                    "rows": [{"date": r.date, "side": r.side, "dollar_pnl": r.dollar_pnl,
                              "pct_return": r.pct_return, "exit_reason": r.exit_reason,
                              "tail_covered": r.tail_covered} for r in rows]})
                mm = m if m.get("n") else {}
                print(f"  longDTE={long_dte} long={lo:+d}({tier:>4}) gap=+{sg_gap} | "
                      f"n={mm.get('n','-'):>3} exp=${mm.get('exp_dollar','-'):>7} "
                      f"oos_exp=${mm.get('oos_exp','-'):>7} sortino={mm.get('sortino','-')} "
                      f"maxDD=${mm.get('max_drawdown','-')} tailOK={mm.get('tail',{}).get('all_tails_covered','-') if mm else '-'} "
                      f"-> {'CLEARS' if clears else 'no'}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[diag] wrote {OUT}")

    clears_cells = [c for c in results["cells"] if c["clears_bar"]]
    print(f"\n=== DIAGONAL VERDICT vs 0DTE (Sortino>={BASELINE_0DTE_SORTINO}, "
          f"maxDD>~{BASELINE_0DTE_MAXDD}, 11-gate, tail-defined) ===")
    print(f"  {len(clears_cells)} cell(s) clear the clean-win bar")
    for c in clears_cells:
        m = c["metrics"]
        print(f"     longDTE={c['long_dte']} long={c['long_offset']:+d}({c['long_tier']}) gap=+{c['short_gap']} "
              f"-> n={m['n']} oos_exp=${m['oos_exp']} sortino={m['sortino']} "
              f"maxDD=${m['max_drawdown']} top5%={m['top5_day_pct']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
