"""PIVOT / SPREAD-IFY — debit-spread refinement of edge #4 vix_regime_dayside (ATM Safe-2).

THESIS (J, 2026-06-21, SUNDAY markets CLOSED, $0 offline real-fills):
The recency drawdown's loss MECHANISM = the -8% premium stop whipsawing LONG single-leg
options in the chop regime. A DEBIT SPREAD (BUY near-strike + SELL a further-OTM strike,
SAME direction) caps premium-at-risk (lower cost), cuts theta + vega, reduces whipsaw
WITHOUT changing the entry signal. Tradeoff: the short leg CAPS upside -> per-trade EV may
fall; the WIN is RISK-ADJUSTED (lower variance / maxDD) + reduced recency bleed while
staying positive.

DETECTOR REUSE (byte-for-byte, C1 real-fills WR authority):
  _b5_vix_regime_dayside.detect_opt_signals + favorable_regime + causal_vix_median +
  vix_slope + _swing_stop + _strike_from_spot. NO edits to watchers/params/risk_gate/
  orchestrator/heartbeat. The entry signal is IDENTICAL to the live edge.

LONG SINGLE-LEG BASELINE (the thing we A/B against):
  _b5_vix_regime_dayside.simulate_opt at the ATM Safe-2 tier (strike_offset=0), the edge's
  existing rules (lib.simulator_real, premium_stop=-0.08, swing chart-stop, v15 tiered exits,
  15:50 time stop). This is the live ATM Safe-2 structure for #4.

DEBIT SPREAD (the refinement, real OPRA fills):
  BUY long strike {ATM, ITM-1, ITM-2} + SELL a strike {$2,$3,$4 further OTM} same side.
  CALL (bullish day-side): long@K_long, short@K_long+width (higher = further OTM).
  PUT (bearish day-side):  long@K_long, short@K_long-width (lower  = further OTM).
  Both legs inside the +/-$5 OPRA cache band (near-ATM narrow spreads FIT).
  Net debit PAID at entry; max gain = (width - debit), max loss = debit.
  The edge's stop/TP/time rules applied to the SPREAD NET value:
    - premium stop  : net spread mark <= entry_debit * (1 + PREMIUM_STOP)   [-8%]
    - TP1 (+30%)    : partial close tp1_qty_fraction at net mark >= debit*(1+TP1_PCT)
    - runner target : net mark >= debit*(1+RUNNER_PCT)
    - time stop     : 15:50 ET hard, mark to net close.
  Same conservative same-bar conflict (STOP before TP), next-bar-open fill, $0.02/leg
  slippage each side, $0 commission (Alpaca paper; commission=0.65 disclosed separately).

REPORTING (BEST cell + full grid), for BOTH:
  full-OOS-2026 AND the recent ~25-trading-day window (the chop/RED regime):
    expectancy/tr, n, WR, book maxDD, per-trade Sharpe, Sortino + DELTAS (long_baseline vs
    debit_spread). GATE per the L175 risk-adjusted bar.

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_spreadify_vix_regime.py
Writes analysis/recommendations/_pivot_spreadify_vix_regime.json (machine) and a section to
analysis/recommendations/PIVOT-SPREADIFY-SCORECARD.md (human).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts, _strike_from_spot, _nearest_cached_strike,
)
from autoresearch import _b5_vix_regime_dayside as b5  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after, quote_at_index,
)
from lib.simulator import TIME_STOP_ET  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "_pivot_spreadify_vix_regime.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "PIVOT-SPREADIFY-SCORECARD.md"

# ── Data window: load to 2026-06-16 master pair so the recent chop/RED regime is covered ─
DATA_START = dt.date(2025, 1, 1)
DATA_END = dt.date(2026, 6, 16)
OOS_YEAR = b5.OOS_YEAR  # 2026
RECENT_TRADING_DAYS = 25

# ── The edge's existing exit rules (the LIVE #4 ATM Safe-2 / v15 knobs) ──────────────
PREMIUM_STOP = b5.PREMIUM_STOP          # -0.08
TP1_PCT = 0.30                          # v15 tp1_premium_pct
RUNNER_PCT = 2.5                        # v15 runner_target_premium_pct
TP1_QTY_FRACTION = 0.50                 # v15
QTY = b5.QTY                            # 3
MAX_STRIKE_STEPS = b5.MAX_STRIKE_STEPS  # 4
BAND_HALF = 5                           # +/-$5 OPRA cache band

ENTRY_SLIP = 0.02
EXIT_SLIP = 0.02
COMMISSION_PER_CONTRACT = 0.65  # disclosed; headline uses $0 (Alpaca paper)

# Debit-spread geometry sweep
LONG_TIERS = {"ATM": 0, "ITM1": -1, "ITM2": -2}   # strike_offset of LONG leg (signed like the edge)
SHORT_WIDTHS = [2, 3, 4]                            # $ further OTM for the SHORT leg

# Use ONE fixed favorable VIX regime cell for the A/B (the edge's distilled default):
#   slope_rule = "not_rising", low_margin = 0.0 (LOW = at/below trailing median, declining).
# This is the canonical #4 cell; the spread refinement is geometry, not a regime re-sweep.
SLOPE_RULE = "not_rising"
LOW_MARGIN = 0.0


# ═════════════════════════════════════════════════════════════════════════════════
# Risk-adjusted metric helpers (per-trade Sharpe/Sortino on $ P&L; book maxDD on equity)
# ═════════════════════════════════════════════════════════════════════════════════
def per_trade_sharpe(pnls: np.ndarray) -> Optional[float]:
    if len(pnls) < 2:
        return None
    sd = float(np.std(pnls, ddof=1))
    if sd == 0:
        return None
    return round(float(np.mean(pnls)) / sd, 3)


def per_trade_sortino(pnls: np.ndarray) -> Optional[float]:
    if len(pnls) < 2:
        return None
    downside = pnls[pnls < 0]
    if len(downside) == 0:
        return None  # no losers -> undefined (report as None, not inf)
    dd = float(np.sqrt(np.mean(downside ** 2)))
    if dd == 0:
        return None
    return round(float(np.mean(pnls)) / dd, 3)


def book_max_dd(pnls_chrono: np.ndarray) -> float:
    """Worst peak-to-trough on the cumulative $ equity curve (trades in chrono order)."""
    if len(pnls_chrono) == 0:
        return 0.0
    eq = np.cumsum(pnls_chrono)
    peak = np.maximum.accumulate(eq)
    return round(float((eq - peak).min()), 2)


@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    exit_reason: str


def _chrono(rows: list[TradeRow]) -> list[TradeRow]:
    return sorted(rows, key=lambda r: r.date)


def window_metrics(rows: list[TradeRow], label: str) -> dict:
    if not rows:
        return {"label": label, "n": 0}
    rows = _chrono(rows)
    pnl = np.array([r.pnl for r in rows], float)
    wins = int((pnl > 0).sum())
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r.date] += r.pnl
    return {
        "label": label,
        "n": len(rows),
        "wr_pct": round(100.0 * wins / len(rows), 1),
        "exp_per_trade": round(float(pnl.mean()), 2),
        "total": round(float(pnl.sum()), 2),
        "book_max_dd": book_max_dd(pnl),
        "sharpe_per_trade": per_trade_sharpe(pnl),
        "sortino_per_trade": per_trade_sortino(pnl),
        "n_days": len(bd),
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


# ═════════════════════════════════════════════════════════════════════════════════
# LONG SINGLE-LEG BASELINE — reuse b5.simulate_opt (lib.simulator_real, the live edge)
# ═════════════════════════════════════════════════════════════════════════════════
def long_baseline_rows(sigs, spy, ribbon, vix_g, *, strike_offset: int) -> tuple[list[TradeRow], dict]:
    opt_rows, cov = b5.simulate_opt(sigs, spy, ribbon, vix_g,
                                    strike_offset=strike_offset,
                                    premium_stop_pct=PREMIUM_STOP)
    rows = [TradeRow(date=r.date, side=r.side, pnl=r.pnl, exit_reason=r.exit_reason)
            for r in opt_rows]
    return rows, cov


# ═════════════════════════════════════════════════════════════════════════════════
# DEBIT-SPREAD SIMULATOR (real OPRA fills) — reuse the OPRA loader, price the net spread,
# apply the edge's premium-pct stop/TP/time rules to the SPREAD NET value.
# ═════════════════════════════════════════════════════════════════════════════════
@dataclass
class SpreadFill:
    date: str
    side: str
    long_strike: int
    short_strike: int
    width: int
    net_debit: float        # $ per 1-lot paid at entry (positive)
    realized_pnl: float     # $ net of slippage (+commission knob), all contracts
    exit_reason: str
    skipped: bool = False
    skip_reason: str = ""


def _load_leg(date: dt.date, strike: int, side: str) -> Optional[pd.DataFrame]:
    sym = option_symbol(date, strike, side)
    df = load_contract_bars(sym)
    if df is None or df.empty:
        return None
    df = df.copy()
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    return df


def simulate_debit_spread(date: dt.date, entry_dt: dt.datetime, side: str,
                          long_strike: int, short_strike: int, *,
                          contracts: int = QTY,
                          commission_per_contract: float = 0.0) -> SpreadFill:
    """BUY long_strike + SELL short_strike (same side, short is further OTM).

    Net debit PAID = long_ask - short_bid (>0). open_pnl(t) = (net_mark(t) - net_debit)*100.
      net_mark = long_mark - short_mark  (the spread's current value).
    Apply the edge's rules on the spread NET value vs the entry debit:
      premium stop : open_pnl <= net_debit*PREMIUM_STOP*100   (debit*(1+stop) value floor)
      TP1          : partial tp1_qty_fraction at open_pnl >= net_debit*TP1_PCT*100
      runner       : remaining at open_pnl >= net_debit*RUNNER_PCT*100
      time stop    : 15:50 ET hard, mark net close.
    Conservative same-bar: STOP before TP. Next-bar-open fill. NO look-ahead.
    """
    width = abs(short_strike - long_strike)
    f = SpreadFill(date=str(date), side=side, long_strike=long_strike,
                   short_strike=short_strike, width=width, net_debit=0.0,
                   realized_pnl=0.0, exit_reason="EOD")

    ldf = _load_leg(date, long_strike, side)
    sdf = _load_leg(date, short_strike, side)
    if ldf is None:
        f.skipped = True; f.skip_reason = f"missing_long:{side}{long_strike}"; return f
    if sdf is None:
        f.skipped = True; f.skip_reason = f"missing_short:{side}{short_strike}"; return f

    next_bar = entry_dt + dt.timedelta(minutes=5)
    leb = bar_at_or_after(ldf, next_bar)
    seb = bar_at_or_after(sdf, next_bar)
    if leb is None or seb is None or leb.open <= 0 or seb.open <= 0:
        f.skipped = True; f.skip_reason = "no_entry_bar"; return f

    # Entry fills: long pays ASK (open+slip); short receives BID (open-slip).
    long_entry = leb.open + ENTRY_SLIP
    short_entry = max(0.01, seb.open - ENTRY_SLIP)
    net_debit = long_entry - short_entry
    if net_debit <= 0:
        # A debit spread MUST cost a positive debit; <=0 = data/band artifact -> SKIP.
        f.skipped = True; f.skip_reason = f"non_debit:{net_debit:.2f}"; return f
    f.net_debit = round(net_debit, 4)

    # Align both legs to the entry bar index.
    def _idx_of(df, ts):
        m = df.index[df["timestamp_et"] == ts]
        return int(m[0]) if len(m) else None
    # bar_at_or_after returns possibly different ts per leg; use the LATER one for causality.
    entry_ts = max(leb.timestamp_et, seb.timestamp_et)
    lb = bar_at_or_after(ldf, entry_ts)
    sb = bar_at_or_after(sdf, entry_ts)
    li = _idx_of(ldf, lb.timestamp_et) if lb else None
    si = _idx_of(sdf, sb.timestamp_et) if sb else None
    if li is None or si is None:
        f.skipped = True; f.skip_reason = "entry_idx_align_fail"; return f

    stop_value = net_debit * (1.0 + PREMIUM_STOP)      # net value floor
    tp1_value = net_debit * (1.0 + TP1_PCT)
    runner_value = net_debit * (1.0 + RUNNER_PCT)

    tp1_filled = False
    tp1_exit_value = None
    final_value = None
    reason = "EOD"
    offset = 1
    while True:
        lk = li + offset
        sk = si + offset
        if lk >= len(ldf) or sk >= len(sdf):
            break
        lbar = quote_at_index(ldf, lk)
        sbar = quote_at_index(sdf, sk)
        if lbar is None or sbar is None:
            break
        bar_ts = max(lbar.timestamp_et, sbar.timestamp_et)
        bar_time = bar_ts.time()

        # net spread mark at close: long_close - short_close.
        net_close = lbar.close - sbar.close
        # adverse intrabar: long low - short high (worst spread value) for stop realism.
        net_worst = lbar.low - sbar.high
        time_stop_now = bar_time >= TIME_STOP_ET

        # --- STOP (conservative, before TP). Use bar.close basis (matches simulator_credit). ---
        if net_close <= stop_value:
            reason = "STOP"; final_value = net_close; break
        # TP1 partial
        if (not tp1_filled) and net_close >= tp1_value:
            tp1_filled = True
            tp1_exit_value = net_close
            # remaining runner continues
        # runner target -> close remaining
        if tp1_filled and net_close >= runner_value:
            reason = "TP1_RUNNER_TARGET"; final_value = net_close; break
        if time_stop_now:
            reason = "TP1_THEN_TIME" if tp1_filled else "EOD_TIME"
            final_value = net_close; break
        offset += 1

    if final_value is None:
        # ran out of bars -> mark to each leg's final close.
        l_last = quote_at_index(ldf, len(ldf) - 1)
        s_last = quote_at_index(sdf, len(sdf) - 1)
        final_value = (l_last.close if l_last else 0.0) - (s_last.close if s_last else 0.0)
        reason = "TP1_THEN_EOD" if tp1_filled else "EOD"

    # Exit fills: closing the spread = SELL long (hit BID, -slip) + BUY short (pay ASK, +slip).
    # net exit value realized = (long_close - slip) - (short_close + slip) = net_value - 2*slip.
    def _net_exit_realized(net_value: float) -> float:
        return net_value - 2.0 * EXIT_SLIP

    if tp1_filled and reason.startswith("TP1") and tp1_exit_value is not None and reason != "TP1_RUNNER_TARGET":
        # TP1 leg closed at tp1_exit_value; runner closed at final_value.
        tp1_qty = int(round(contracts * TP1_QTY_FRACTION))
        run_qty = contracts - tp1_qty
        pnl_tp1 = (_net_exit_realized(tp1_exit_value) - net_debit) * 100.0 * tp1_qty
        pnl_run = (_net_exit_realized(final_value) - net_debit) * 100.0 * run_qty
        realized = pnl_tp1 + pnl_run
    elif reason == "TP1_RUNNER_TARGET" and tp1_exit_value is not None:
        tp1_qty = int(round(contracts * TP1_QTY_FRACTION))
        run_qty = contracts - tp1_qty
        pnl_tp1 = (_net_exit_realized(tp1_exit_value) - net_debit) * 100.0 * tp1_qty
        pnl_run = (_net_exit_realized(final_value) - net_debit) * 100.0 * run_qty
        realized = pnl_tp1 + pnl_run
    else:
        realized = (_net_exit_realized(final_value) - net_debit) * 100.0 * contracts

    # commission: 2 legs * 2 sides * contracts
    commission = commission_per_contract * 2 * 2 * contracts
    f.realized_pnl = round(realized - commission, 2)
    f.exit_reason = reason
    return f


def debit_spread_rows(sigs, spy, *, long_offset: int, width: int) -> tuple[list[TradeRow], dict]:
    """For each signal, pick the LONG strike (nearest cached at offset) + the SHORT strike
    (width $ further OTM, nearest cached), price the spread, apply the rules."""
    rows: list[TradeRow] = []
    n_total = len(sigs); n_filled = n_miss = n_skip = 0
    for s in sigs:
        bar = spy.iloc[s.gidx]
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # LONG strike at offset (same convention as edge: P -> atm-off, C -> atm+off).
        long_target = atm - long_offset if s.side == "P" else atm + long_offset
        long_strike = _nearest_cached_strike(s.date, long_target, s.side, MAX_STRIKE_STEPS)
        if long_strike is None:
            n_miss += 1; continue
        # SHORT strike further OTM by `width`: C -> higher, P -> lower.
        short_target = long_strike - width if s.side == "P" else long_strike + width
        short_strike = _nearest_cached_strike(s.date, short_target, s.side, MAX_STRIKE_STEPS)
        if short_strike is None or short_strike == long_strike:
            n_miss += 1; continue
        # Band check: both legs within +/-$5 of ATM.
        if abs(long_strike - atm) > BAND_HALF or abs(short_strike - atm) > BAND_HALF:
            n_miss += 1; continue
        entry_dt = pd.Timestamp(bar["timestamp_et"]).to_pydatetime()
        fill = simulate_debit_spread(s.date, entry_dt, s.side, int(long_strike),
                                     int(short_strike), contracts=QTY,
                                     commission_per_contract=0.0)
        if fill.skipped:
            n_skip += 1; continue
        n_filled += 1
        rows.append(TradeRow(date=fill.date, side=fill.side, pnl=fill.realized_pnl,
                             exit_reason=fill.exit_reason))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "skipped": n_skip,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ═════════════════════════════════════════════════════════════════════════════════
# Windowing: full-OOS-2026 + recent ~25 trading days
# ═════════════════════════════════════════════════════════════════════════════════
def split_windows(all_dates_sorted: list[str]) -> tuple[set, set]:
    """OOS-2026 = all 2026 trade dates; recent = last RECENT_TRADING_DAYS trade dates."""
    oos = {d for d in all_dates_sorted if int(d[:4]) == OOS_YEAR}
    recent = set(all_dates_sorted[-RECENT_TRADING_DAYS:]) if all_dates_sorted else set()
    return oos, recent


def filt(rows: list[TradeRow], dates: set) -> list[TradeRow]:
    return [r for r in rows if r.date in dates]


def deltas(base: dict, spread: dict) -> dict:
    def d(k):
        b = base.get(k); s = spread.get(k)
        if b is None or s is None:
            return None
        return round(s - b, 3)
    return {
        "exp_per_trade": d("exp_per_trade"),
        "wr_pct": d("wr_pct"),
        "book_max_dd": d("book_max_dd"),     # +ve = LESS deep (better, since DD is negative)
        "sharpe_per_trade": d("sharpe_per_trade"),
        "sortino_per_trade": d("sortino_per_trade"),
        "total": d("total"),
        "n": (spread.get("n", 0) - base.get("n", 0)),
    }


# ═════════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[spreadify] loading SPY+VIX {DATA_START}..{DATA_END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(DATA_START, DATA_END)
    spy = b5._normalize_spy(spy_raw)
    vix_g = b5._align_vix(spy, vix_raw)
    vix_med_g = b5.causal_vix_median(vix_g, b5.VIX_MEDIAN_BARS)
    vix_slp_g = b5.vix_slope(vix_g, b5.VIX_SLOPE_BARS)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[spreadify] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # Detect signals ONCE with the canonical #4 regime cell (byte-for-byte b5 detector).
    sigs = b5.detect_opt_signals(days, spy, vix_g, vix_med_g, vix_slp_g, LOW_MARGIN, SLOPE_RULE)
    sig_dates = sorted({str(s.date) for s in sigs})
    print(f"[spreadify] signals={len(sigs)} (slope={SLOPE_RULE} low_margin={LOW_MARGIN}) "
          f"dates {sig_dates[0] if sig_dates else '-'}..{sig_dates[-1] if sig_dates else '-'}",
          flush=True)

    # Determine windows from the union of all dates that ANY structure trades on.
    # Use signal dates that actually FILL (long ATM baseline) for window definition stability.
    base_rows_full, base_cov = long_baseline_rows(sigs, spy, ribbon, vix_g, strike_offset=0)
    all_dates = sorted({r.date for r in base_rows_full})
    oos_dates, recent_dates = split_windows(all_dates)
    recent_sorted = sorted(recent_dates)
    print(f"[spreadify] long-baseline ATM fills={len(base_rows_full)} cov={base_cov}", flush=True)
    print(f"[spreadify] OOS-2026 dates={len([d for d in all_dates if int(d[:4])==OOS_YEAR])} "
          f"recent~{RECENT_TRADING_DAYS}d window={recent_sorted[0] if recent_sorted else '-'}.."
          f"{recent_sorted[-1] if recent_sorted else '-'}", flush=True)

    # ── LONG SINGLE-LEG BASELINE (ATM Safe-2 = the live #4 structure) ──────────────
    baseline = {
        "structure": "long_single_leg_ATM_safe2",
        "strike_offset": 0,
        "coverage": base_cov,
        "full_oos": window_metrics(filt(base_rows_full, oos_dates), "full_oos_2026"),
        "recent": window_metrics(filt(base_rows_full, recent_dates), f"recent_{RECENT_TRADING_DAYS}d"),
        "all_n": len(base_rows_full),
    }
    print(f"[spreadify] BASELINE full_oos: {baseline['full_oos']}", flush=True)
    print(f"[spreadify] BASELINE recent : {baseline['recent']}", flush=True)

    # ── DEBIT-SPREAD GRID ──────────────────────────────────────────────────────────
    grid = []
    for long_name, long_off in LONG_TIERS.items():
        for width in SHORT_WIDTHS:
            rows, cov = debit_spread_rows(sigs, spy, long_offset=long_off, width=width)
            cell = {
                "cell": f"long_{long_name}_short_{width}wOTM",
                "long_tier": long_name, "long_offset": long_off, "short_width": width,
                "coverage": cov,
                "full_oos": window_metrics(filt(rows, oos_dates), "full_oos_2026"),
                "recent": window_metrics(filt(rows, recent_dates), f"recent_{RECENT_TRADING_DAYS}d"),
                "all_n": len(rows),
            }
            cell["delta_full_oos"] = deltas(baseline["full_oos"], cell["full_oos"])
            cell["delta_recent"] = deltas(baseline["recent"], cell["recent"])
            grid.append(cell)
            fo = cell["full_oos"]; rc = cell["recent"]
            print(f"[spreadify] {cell['cell']:24s} fill={cov['fill_rate']} "
                  f"OOS n={fo.get('n')} exp=${fo.get('exp_per_trade')} dd=${fo.get('book_max_dd')} "
                  f"shp={fo.get('sharpe_per_trade')} | REC n={rc.get('n')} exp=${rc.get('exp_per_trade')} "
                  f"dd=${rc.get('book_max_dd')} shp={rc.get('sharpe_per_trade')}", flush=True)

    # ── PICK BEST CELL ───────────────────────────────────────────────────────────
    # Selection per the L175 risk-adjusted bar + the KEY recency question:
    #   require OOS exp/tr > 0 AND OOS n>=10 (evidence), then rank by a composite that
    #   rewards (a) recency-bleed reduction (recent maxDD improvement vs baseline) and
    #   (b) per-trade Sharpe improvement, with EV-positivity as a hard gate.
    def cell_score(c):
        fo = c["full_oos"]; rc = c["recent"]; dfo = c["delta_full_oos"]; drc = c["delta_recent"]
        if fo.get("n", 0) < 10 or fo.get("exp_per_trade", -1) is None:
            return -1e9
        if fo.get("exp_per_trade", -1) <= 0:
            return -1e9  # hard gate: capped but POSITIVE
        # recency maxDD improvement (delta book_max_dd > 0 means shallower = better)
        rec_dd_impr = (drc.get("book_max_dd") or 0.0)
        oos_dd_impr = (dfo.get("book_max_dd") or 0.0)
        sharpe_impr = (dfo.get("sharpe_per_trade") or 0.0)
        rec_exp = rc.get("exp_per_trade") or 0.0
        # composite: prioritize recency DD rescue + OOS DD + sharpe, with EV kept positive.
        return rec_dd_impr * 1.0 + oos_dd_impr * 0.5 + sharpe_impr * 50.0 + rec_exp * 2.0

    scored = sorted(grid, key=cell_score, reverse=True)
    best = scored[0] if scored else None
    best_score = cell_score(best) if best else -1e9

    # ── VERDICT (per the gate) ─────────────────────────────────────────────────────
    def verdict_for(c) -> tuple[str, dict]:
        if c is None or cell_score(c) <= -1e9:
            return "NO_IMPROVEMENT", {}
        fo = c["full_oos"]; rc = c["recent"]; dfo = c["delta_full_oos"]; drc = c["delta_recent"]
        base_rc = baseline["recent"]; base_fo = baseline["full_oos"]
        oos_pos = (fo.get("exp_per_trade") or -1) > 0
        # recency bleed reduced/flipped: recent total less negative or positive vs baseline,
        # OR recent maxDD materially shallower.
        rec_total_impr = (rc.get("total") or 0) - (base_rc.get("total") or 0)
        rec_dd_impr = (drc.get("book_max_dd") or 0.0)
        recency_better = (rec_total_impr > 0) or (rec_dd_impr > 0)
        # risk-adjusted: per-trade Sharpe holds/improves AND maxDD materially better (OOS).
        sharpe_hold = (dfo.get("sharpe_per_trade") or -999) >= -0.05
        maxdd_better = (dfo.get("book_max_dd") or 0.0) > 0  # shallower OOS DD
        ev_cut_materially = (dfo.get("exp_per_trade") or 0.0) < -5.0  # >$5/tr EV drop
        detail = {
            "oos_exp_positive": oos_pos,
            "recency_better": recency_better,
            "recency_total_improvement": round(rec_total_impr, 2),
            "recency_maxdd_improvement": round(rec_dd_impr, 2),
            "oos_maxdd_improvement": round(dfo.get("book_max_dd") or 0.0, 2),
            "oos_sharpe_delta": dfo.get("sharpe_per_trade"),
            "oos_exp_delta": dfo.get("exp_per_trade"),
            "ev_cut_materially": ev_cut_materially,
        }
        if not oos_pos:
            return "DEAD", detail
        if recency_better and (maxdd_better or sharpe_hold) and not ev_cut_materially:
            return "RESCUE_IMPROVEMENT", detail
        if maxdd_better and ev_cut_materially:
            return "RISK_REDUCED_LOWER_EV", detail
        if recency_better and maxdd_better and ev_cut_materially:
            return "RISK_REDUCED_LOWER_EV", detail
        return "NO_IMPROVEMENT", detail

    verdict, vdetail = verdict_for(best)

    summary = {
        "kind": "pivot_spreadify",
        "edge": "#4 vix_regime_dayside (ATM Safe-2)",
        "thesis": ("debit spread (BUY near + SELL far-OTM same side) caps premium-at-risk, "
                   "cuts theta/vega, reduces -8% premium-stop whipsaw in chop; A/B vs the "
                   "long single-leg ATM Safe-2 baseline on real OPRA fills"),
        "run_date": dt.date.today().isoformat(),
        "data_window": f"{DATA_START}..{DATA_END}",
        "markets": "CLOSED (Sunday) — offline real-fills, $0, no live orders",
        "regime_cell": {"slope_rule": SLOPE_RULE, "low_margin": LOW_MARGIN,
                        "note": "canonical #4 favorable regime; spread refinement is geometry only"},
        "exit_rules_applied_to_spread_net": {
            "premium_stop_pct": PREMIUM_STOP, "tp1_pct": TP1_PCT, "tp1_qty_fraction": TP1_QTY_FRACTION,
            "runner_pct": RUNNER_PCT, "time_stop_et": str(TIME_STOP_ET),
            "slippage_per_leg": ENTRY_SLIP, "commission_headline": 0.0,
            "commission_disclosed": COMMISSION_PER_CONTRACT,
        },
        "n_signals": len(sigs),
        "recent_window_dates": recent_sorted,
        "long_baseline": baseline,
        "debit_spread_grid": grid,
        "best_cell": best,
        "best_cell_name": best["cell"] if best else None,
        "verdict": verdict,
        "verdict_detail": vdetail,
        "DISCLOSURE": {
            "detector_reuse": "_b5_vix_regime_dayside.detect_opt_signals byte-for-byte; no watcher/param/risk_gate/orchestrator/heartbeat edits",
            "real_fills": "lib.option_pricing_real OPRA loader; baseline via lib.simulator_real (live edge); spread priced leg-by-leg",
            "band": "both legs within +/-$5 OPRA cache band (near-ATM narrow spreads fit)",
            "per_trade": "per-trade expectancy + Sharpe/Sortino, not WR alone (C4/L175)",
            "no_lookahead": "next-bar-open fill; exit decisions on bars <= current walk bar (C6)",
            "recent_window": f"last {RECENT_TRADING_DAYS} trade dates of the signal stream (the chop/RED regime)",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[spreadify] wrote {OUT_JSON}", flush=True)

    write_scorecard(summary)
    print(f"[spreadify] wrote section to {OUT_MD}", flush=True)

    print("\n=== SPREADIFY #4 vix_regime_dayside ATM Safe-2 VERDICT ===")
    print(f"BEST cell: {summary['best_cell_name']}")
    if best:
        print(f"  OOS:    {best['full_oos']}")
        print(f"  RECENT: {best['recent']}")
        print(f"  d_OOS:  {best['delta_full_oos']}")
        print(f"  d_REC:  {best['delta_recent']}")
    print(f"VERDICT: {verdict}")
    print(f"detail: {vdetail}")
    return 0


def _fmt(v):
    return "-" if v is None else v


def write_scorecard(s: dict) -> None:
    b = s["long_baseline"]; best = s["best_cell"]
    lines = []
    lines.append("# PIVOT — SPREAD-IFY SCORECARD\n")
    lines.append("> Debit-spread refinement of the LIVE edges. A/B vs each edge's long "
                 "single-leg baseline on real OPRA fills. Markets CLOSED, $0 offline, no live "
                 "orders. Detector reused byte-for-byte; geometry-only refinement.\n")
    lines.append(f"\n## #4 vix_regime_dayside — ATM Safe-2  ({s['run_date']})\n")
    lines.append(f"- **Data window:** {s['data_window']} | signals={s['n_signals']} | "
                 f"regime: slope={s['regime_cell']['slope_rule']} low_margin={s['regime_cell']['low_margin']}\n")
    lines.append(f"- **Exit rules on spread NET value:** premium_stop={s['exit_rules_applied_to_spread_net']['premium_stop_pct']}, "
                 f"TP1=+{int(s['exit_rules_applied_to_spread_net']['tp1_pct']*100)}% (qty {s['exit_rules_applied_to_spread_net']['tp1_qty_fraction']}), "
                 f"runner=+{int(s['exit_rules_applied_to_spread_net']['runner_pct']*100)}%, time_stop={s['exit_rules_applied_to_spread_net']['time_stop_et']}\n")
    lines.append(f"- **Recent ~{RECENT_TRADING_DAYS}d window:** "
                 f"{s['recent_window_dates'][0] if s['recent_window_dates'] else '-'}.."
                 f"{s['recent_window_dates'][-1] if s['recent_window_dates'] else '-'}\n")

    def row(name, m):
        return (f"| {name} | {_fmt(m.get('n'))} | {_fmt(m.get('wr_pct'))} | "
                f"${_fmt(m.get('exp_per_trade'))} | ${_fmt(m.get('total'))} | "
                f"${_fmt(m.get('book_max_dd'))} | {_fmt(m.get('sharpe_per_trade'))} | "
                f"{_fmt(m.get('sortino_per_trade'))} |")

    lines.append("\n### Long single-leg BASELINE (ATM Safe-2 = the live #4 structure)\n")
    lines.append("| window | n | WR% | exp/tr | total | maxDD | Sharpe/tr | Sortino/tr |")
    lines.append("|---|---|---|---|---|---|---|---|")
    lines.append(row("full-OOS-2026", b["full_oos"]))
    lines.append(row(f"recent-{RECENT_TRADING_DAYS}d", b["recent"]))

    if best:
        lines.append(f"\n### BEST debit-spread cell: **{best['cell']}** "
                     f"(long {best['long_tier']} / short ${best['short_width']} OTM)\n")
        lines.append("| window | n | WR% | exp/tr | total | maxDD | Sharpe/tr | Sortino/tr |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(row("full-OOS-2026", best["full_oos"]))
        lines.append(row(f"recent-{RECENT_TRADING_DAYS}d", best["recent"]))

        def drow(name, d):
            return (f"| {name} | {_fmt(d.get('n'))} | {_fmt(d.get('wr_pct'))} | "
                    f"{_fmt(d.get('exp_per_trade'))} | {_fmt(d.get('total'))} | "
                    f"{_fmt(d.get('book_max_dd'))} | {_fmt(d.get('sharpe_per_trade'))} | "
                    f"{_fmt(d.get('sortino_per_trade'))} |")
        lines.append("\n### DELTA (debit_spread − long_baseline; +maxDD = shallower/better)\n")
        lines.append("| window | dn | dWR% | dexp/tr | dtotal | dmaxDD | dSharpe/tr | dSortino/tr |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(drow("full-OOS-2026", best["delta_full_oos"]))
        lines.append(drow(f"recent-{RECENT_TRADING_DAYS}d", best["delta_recent"]))

    lines.append("\n### Full geometry grid (full-OOS-2026 / recent)\n")
    lines.append("| cell | fill | OOS n | OOS exp/tr | OOS maxDD | OOS Shp | REC n | REC exp/tr | REC maxDD | REC Shp |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in s["debit_spread_grid"]:
        fo = c["full_oos"]; rc = c["recent"]
        lines.append(f"| {c['cell']} | {c['coverage']['fill_rate']} | {_fmt(fo.get('n'))} | "
                     f"${_fmt(fo.get('exp_per_trade'))} | ${_fmt(fo.get('book_max_dd'))} | "
                     f"{_fmt(fo.get('sharpe_per_trade'))} | {_fmt(rc.get('n'))} | "
                     f"${_fmt(rc.get('exp_per_trade'))} | ${_fmt(rc.get('book_max_dd'))} | "
                     f"{_fmt(rc.get('sharpe_per_trade'))} |")

    lines.append(f"\n### VERDICT: **{s['verdict']}**\n")
    vd = s["verdict_detail"]
    if vd:
        lines.append(f"- OOS exp positive: {vd.get('oos_exp_positive')} | "
                     f"recency better: {vd.get('recency_better')} "
                     f"(total Δ ${vd.get('recency_total_improvement')}, maxDD Δ ${vd.get('recency_maxdd_improvement')})\n")
        lines.append(f"- OOS maxDD improvement: ${vd.get('oos_maxdd_improvement')} | "
                     f"OOS Sharpe Δ {vd.get('oos_sharpe_delta')} | OOS exp Δ ${vd.get('oos_exp_delta')} | "
                     f"EV cut materially: {vd.get('ev_cut_materially')}\n")
    lines.append("\n---\n")

    header = ""
    if OUT_MD.exists():
        existing = OUT_MD.read_text(encoding="utf-8")
        # Replace an existing #4 section if present, else append.
        marker = "## #4 vix_regime_dayside — ATM Safe-2"
        if marker in existing:
            pre = existing.split(marker)[0].rstrip()
            # keep everything before the first #4 section; drop the old #4 block to end-of-section
            body = "\n".join(lines[2:])  # skip title + intro (already in pre)
            OUT_MD.write_text(pre + "\n\n" + body + "\n", encoding="utf-8")
            return
        OUT_MD.write_text(existing.rstrip() + "\n\n" + "\n".join(lines[2:]) + "\n", encoding="utf-8")
        return
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
