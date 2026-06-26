"""PIVOT / SPREAD-IFY: vwap_continuation (the LIVE edge IN THE DRAWDOWN).

THESIS (diagnosed): the recent ~25-trade-day RED bleed on the LIVE vwap_continuation
edge is the -8% premium stop whipsawing a LONG single-leg call/put in the chop regime
(9/10 ATM + 11/11 ITM-2 recent losers exited EXIT_ALL_PREMIUM_STOP). A DEBIT VERTICAL
(BUY near + SELL further-OTM, same side) caps premium-at-risk, cuts theta+vega, and
reduces whipsaw WITHOUT changing the entry signal. The short leg CAPS upside, so per-
trade EV may fall; the WIN is RISK-ADJUSTED (lower variance / maxDD) + reduced recency
bleed while staying positive.

WHAT THIS DOES (A/B, real OPRA fills = WR authority C1):
  * Detect vwap_continuation signals ONCE -- detector BYTE-FOR-BYTE the validated
    _edgehunt_vwap_continuation.detect_signals (which is j_daily_pattern_ratify /
    the live vwap_continuation_watcher).
  * LONG-SINGLE-LEG BASELINE: simulate_trade_real at the two live tiers --
    ATM (Safe-2) and ITM-2 (Bold) -- with the LIVE v15 exits AND a matched simple
    premium-stop/TP form so the spread comparison isolates STRUCTURE not exit-engine.
  * DEBIT SPREAD: simulate_debit_trade (validated 15/15) -- long {ATM,ITM-1,ITM-2} x
    short-leg width {+2,+3,+4 OTM} (all inside the +/-$5 cache band) x the edge's
    stop/TP applied to the SPREAD NET DEBIT.
  * For the BEST spread cell + the full grid, report BOTH full-OOS-2026 AND the recent
    ~25-trading-day window: expectancy/tr, n, WR, book maxDD, per-trade Sharpe,
    Sortino, and DELTAS vs the long-single-leg baseline.

PURE PYTHON, $0. SERIAL (one process). No live orders. Markets closed.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_spreadify_vwap_continuation.py
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

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals, _normalize_spy, _align_vix, MAX_STRIKE_STEPS, QTY,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.simulator_debit import simulate_debit_trade  # noqa: E402
from lib.multileg_structures import Leg, band_strikes  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "spreadify-vwap_continuation.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "PIVOT-SPREADIFY-SCORECARD.md"

OOS_YEAR = 2026
RECENT_DAYS = 25            # the "chop / RED regime" recency window (trading days)

# Live tiers (the two production strike configs for this edge).
LONG_TIERS = {"ATM": 0, "ITM-2": -2}   # offset: 0 = ATM (Safe-2), -2 = ITM-2 (Bold)

# Debit-spread geometry sweep (the whole point):
#   long near-leg offset (near_offset in build_debit_vertical; 0=ATM, 1=ITM-1, 2=ITM-2)
#   x short-leg width $ further OTM. All fit the +/-$5 cache band.
SPREAD_LONG_NEAR = {"ATM": 0, "ITM-1": 1, "ITM-2": 2}   # near_offset (toward ITM)
SPREAD_WIDTHS = [2, 3, 4]

# Exit rules applied to the SPREAD NET DEBIT (the edge's existing -8% stop analogue + a
# small sweep). pt_frac = +X% of debit; stop_frac = lose X% of debit. None = EOD-only.
# -8% of a long single-leg premium maps onto the spread as a small fraction of the
# (much smaller) net debit; we sweep a tight set + a chart-stop-only (EOD-only) form.
SPREAD_PT = [0.50, 1.0]                # close at +50% / +100% of debit
SPREAD_STOP = [0.50, 0.99, None]       # lose 50% / ~100% of debit / EOD-only (no stop)


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (real-fills, OP-20 disclosure + L175 risk-adjusted bar)
# ─────────────────────────────────────────────────────────────────────────────
def _book_maxdd(pnls_in_date_order: list[float]) -> float:
    """Max peak-to-trough drawdown ($) of the cumulative equity curve (1 lot/trade)."""
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for p in pnls_in_date_order:
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return round(mdd, 2)


def _sharpe(pnls: list[float]) -> Optional[float]:
    """Per-trade Sharpe = mean/std of per-trade P&L (not annualized; comparison only)."""
    if len(pnls) < 2:
        return None
    a = np.array(pnls, float)
    sd = a.std(ddof=1)
    return round(float(a.mean() / sd), 4) if sd > 0 else None


def _sortino(pnls: list[float]) -> Optional[float]:
    """Per-trade Sortino = mean / downside-deviation (only negative trades)."""
    if len(pnls) < 2:
        return None
    a = np.array(pnls, float)
    downside = a[a < 0]
    if len(downside) == 0:
        return None  # no losers -> undefined / infinite
    dd = math.sqrt(float((downside ** 2).mean()))
    return round(float(a.mean() / dd), 4) if dd > 0 else None


@dataclass
class Trade:
    date: str
    side: str
    pnl: float
    exit_reason: str


def metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0}
    trades = sorted(trades, key=lambda t: t.date)
    pnls = [t.pnl for t in trades]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    oos = [t for t in trades if int(t.date[:4]) == OOS_YEAR]
    exits = defaultdict(int)
    for t in trades:
        exits[t.exit_reason] += 1
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(np.mean(pnls)), 2),
        "total_dollar": round(float(np.sum(pnls)), 2),
        "book_maxdd": _book_maxdd(pnls),
        "sharpe": _sharpe(pnls),
        "sortino": _sortino(pnls),
        "oos_n": len(oos),
        "oos_exp": round(float(np.mean([t.pnl for t in oos])), 2) if oos else 0.0,
        "oos_total": round(float(np.sum([t.pnl for t in oos])), 2) if oos else 0.0,
        "oos_maxdd": _book_maxdd([t.pnl for t in oos]) if oos else 0.0,
        "oos_sharpe": _sharpe([t.pnl for t in oos]),
        "oos_sortino": _sortino([t.pnl for t in oos]),
        "exit_hist": dict(sorted(exits.items())),
    }


def recent_window(trades: list[Trade], n_days: int) -> list[Trade]:
    """The last n_days TRADING DAYS that have >=1 trade (the chop/RED regime)."""
    days = sorted({t.date for t in trades})
    recent = set(days[-n_days:])
    return [t for t in trades if t.date in recent]


def _delta(spread: dict, base: dict, key: str) -> Optional[float]:
    a, b = spread.get(key), base.get(key)
    if a is None or b is None:
        return None
    return round(a - b, 4)


# ─────────────────────────────────────────────────────────────────────────────
# LONG SINGLE-LEG BASELINE  (simulate_trade_real, the validated long path)
# ─────────────────────────────────────────────────────────────────────────────
def run_long_baseline(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct,
                      simple=False) -> list[Trade]:
    """One long single-leg trade/signal on real OPRA fills.

    simple=False -> the LIVE v15 layered exits (TP1/runner/ribbon/chart-stop) = the
        production baseline.
    simple=True  -> a matched simple-stop form (disable the layered TP/ribbon by pushing
        them out of reach) so the spread's net-debit stop/TP can be compared structure-
        to-structure. We DO keep premium_stop_pct (the -8% whipsaw under test).
    """
    out: list[Trade] = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        kw = dict(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="JVWAP_SPREADIFY_BASE", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct,
        )
        if simple:
            # Push layered exits out of reach: pure premium-stop + EOD/time only.
            kw.update(tp1_premium_pct=9.9, runner_target_premium_pct=99.0,
                      ribbon_flip_back_min_spread_cents=9999.0,
                      ribbon_flip_price_confirm=True)
        fill = simulate_trade_real(**kw)
        if fill is None or fill.dollar_pnl is None:
            continue
        out.append(Trade(date=str(d), side=sg.side, pnl=round(float(fill.dollar_pnl), 2),
                         exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DEBIT SPREAD  (simulate_debit_trade, the validated debit-vertical sim)
# ─────────────────────────────────────────────────────────────────────────────
def run_spread(signals, spy, *, near_offset, width, pt_frac, stop_frac) -> tuple[list[Trade], dict]:
    """One debit vertical / signal on real OPRA fills.

    near_offset: 0=ATM long leg, 1=ITM-1, 2=ITM-2 (toward the money; build_debit_vertical
        treats near_offset as $ toward OTM for the LONG leg, so a positive value here is
        passed as a NEGATIVE near_offset = ITM long leg -- the directional/rich leg).
    width: short leg $ further OTM. Net = long_ask - short_bid = a DEBIT.
    Stop/TP are fractions of the net DEBIT (the cost basis / max loss).
    """
    out: list[Trade] = []
    n_total = len(signals)
    n_filled = n_skip = n_band = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        entry_ts = bar["timestamp_et"]
        # ITM long leg = negative near_offset in build_debit_vertical's OTM-sense.
        if sg.side == "C":
            long_k = int(round(spot)) - near_offset      # ITM call below spot
            short_k = long_k + width
        else:
            long_k = int(round(spot)) + near_offset      # ITM put above spot
            short_k = long_k - width
        legs = [Leg(long_k, sg.side, +1), Leg(short_k, sg.side, -1)]
        # cache band pre-filter (+/-$5)
        band = band_strikes(spot, 5)
        if long_k not in band or short_k not in band:
            n_band += 1
            continue
        fill = simulate_debit_trade(
            date=d, legs=legs, entry_time_et=entry_ts, spot=spot, width=width,
            structure_name="JVWAP_DEBIT", contracts=QTY,
            pt_frac=pt_frac, stop_frac=stop_frac,
            settle_mode="eod_close_mark",
        )
        if fill.skipped or fill.realized_pnl is None:
            n_skip += 1
            continue
        n_filled += 1
        out.append(Trade(date=str(d), side=sg.side,
                         pnl=round(float(fill.realized_pnl), 2),
                         exit_reason=fill.exit_reason))
    cov = {"signals": n_total, "filled": n_filled, "skipped": n_skip,
           "band_miss": n_band,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return out, cov


# ─────────────────────────────────────────────────────────────────────────────
def _ab_block(label, base_full, base_recent, spr_full, spr_recent) -> dict:
    """Build a full + recency A/B block with deltas (spread - long_baseline)."""
    def block(b, s):
        keys = ["n", "wr_pct", "exp_dollar", "total_dollar", "book_maxdd",
                "sharpe", "sortino"]
        return {
            "long_baseline": {k: b.get(k) for k in keys},
            "debit_spread": {k: s.get(k) for k in keys},
            "delta": {k: _delta(s, b, k) for k in keys},
        }
    return {
        "tier": label,
        "full_oos_2026": block(base_full.get("_oos", base_full), spr_full.get("_oos", spr_full)),
        "full_window": block(base_full, spr_full),
        "recent_window": block(base_recent, spr_recent),
    }


def main() -> int:
    print("[spreadify] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = sorted({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[spreadify] SPY days={n_days} signals={len(signals)} on {len(sig_days)} days "
          f"window={sig_days[0]}..{sig_days[-1]}", flush=True)

    # ── LONG SINGLE-LEG BASELINES (live -8% stop, both tiers, live v15 exits) ──
    print("[spreadify] long single-leg baselines ...", flush=True)
    long_full: dict[str, dict] = {}
    long_recent: dict[str, dict] = {}
    long_trades_store: dict[str, list[Trade]] = {}
    for tier, off in LONG_TIERS.items():
        tr = run_long_baseline(signals, spy, ribbon, vix,
                               strike_offset=off, premium_stop_pct=-0.08, simple=False)
        long_trades_store[tier] = tr
        long_full[tier] = metrics(tr)
        long_recent[tier] = metrics(recent_window(tr, RECENT_DAYS))
        m = long_full[tier]
        print(f"  LONG {tier:>5} -8%: n={m['n']} exp=${m['exp_dollar']} "
              f"oos_exp=${m['oos_exp']} maxDD=${m['book_maxdd']} sharpe={m['sharpe']} "
              f"sortino={m['sortino']}", flush=True)
        rm = long_recent[tier]
        print(f"           recent({RECENT_DAYS}d): n={rm['n']} exp=${rm['exp_dollar']} "
              f"total=${rm['total_dollar']} maxDD=${rm['book_maxdd']} sharpe={rm['sharpe']}",
              flush=True)

    # ── DEBIT SPREAD GRID: long-near {ATM,ITM-1,ITM-2} x width {2,3,4} x exits ──
    print(f"\n[spreadify] debit-spread grid "
          f"({len(SPREAD_LONG_NEAR)}x{len(SPREAD_WIDTHS)}x{len(SPREAD_PT)}x{len(SPREAD_STOP)}) ...",
          flush=True)
    grid = []
    for near_name, near_off in SPREAD_LONG_NEAR.items():
        for width in SPREAD_WIDTHS:
            for pt in SPREAD_PT:
                for stop in SPREAD_STOP:
                    trades, cov = run_spread(signals, spy, near_offset=near_off,
                                             width=width, pt_frac=pt, stop_frac=stop)
                    mf = metrics(trades)
                    mr = metrics(recent_window(trades, RECENT_DAYS))
                    cell = {
                        "long_near": near_name, "near_offset": near_off,
                        "width": width, "pt_frac": pt, "stop_frac": stop,
                        "coverage": cov,
                        "full": mf, "recent": mr,
                        "_trades": trades,   # stripped before JSON
                    }
                    grid.append(cell)
                    if mf.get("n"):
                        print(f"  L={near_name:>5} w=${width} pt={pt} stop={stop} | "
                              f"n={mf['n']} exp=${mf['exp_dollar']} oos_exp=${mf['oos_exp']} "
                              f"maxDD=${mf['book_maxdd']} shrp={mf['sharpe']} "
                              f"| recent n={mr['n']} exp=${mr['exp_dollar']} "
                              f"tot=${mr['total_dollar']} maxDD=${mr['book_maxdd']}",
                              flush=True)

    # ── Pick BEST spread cell. Primary objective = the L175 risk-adjusted bar:
    #    recency total > the matching long baseline AND maxDD materially better AND
    #    full-OOS expectancy still positive. Rank by: recency_total_improvement first,
    #    then full sharpe, requiring oos_exp>0 + enough N. Compare each spread tier vs
    #    the SAME-tier long baseline (ITM-2 spread vs ITM-2 long; ATM spread vs ATM long).
    def base_for(near_name: str) -> str:
        return "ITM-2" if near_name == "ITM-2" else "ATM"

    def score(cell) -> tuple:
        mf, mr = cell["full"], cell["recent"]
        if mf.get("n", 0) < 20:
            return (-9e9,)
        b = base_for(cell["long_near"])
        base_rec_total = long_recent[b].get("total_dollar", 0.0) or 0.0
        rec_total = mr.get("total_dollar", -9e9) or -9e9
        base_dd = long_full[b].get("book_maxdd", 0.0) or 0.0
        dd = mf.get("book_maxdd", -9e9) or -9e9
        oos_exp = mf.get("oos_exp", -9e9) or -9e9
        # gate: positive full-OOS expectancy
        if oos_exp <= 0:
            return (-8e9, oos_exp)
        recency_improve = rec_total - base_rec_total
        dd_improve = dd - base_dd  # less-negative is better -> larger = better
        return (recency_improve, dd_improve, mf.get("sharpe") or -9e9)

    filled = [c for c in grid if c["full"].get("n", 0) >= 20]
    best = max(filled, key=score) if filled else None

    # ── Build A/B blocks for the best cell vs its same-tier long baseline ──
    ab_blocks = []
    if best:
        b = base_for(best["long_near"])
        spr_full = best["full"]
        spr_recent = best["recent"]
        base_full = long_full[b]
        base_recent = long_recent[b]
        # OOS sub-block for full_oos_2026
        def oos_view(m):
            return {"n": m.get("oos_n"), "wr_pct": None,
                    "exp_dollar": m.get("oos_exp"), "total_dollar": m.get("oos_total"),
                    "book_maxdd": m.get("oos_maxdd"), "sharpe": m.get("oos_sharpe"),
                    "sortino": m.get("oos_sortino")}
        ab_blocks.append({
            "best_spread_cell": {k: best[k] for k in
                                 ("long_near", "near_offset", "width", "pt_frac", "stop_frac")},
            "vs_long_baseline_tier": b,
            "full_oos_2026": {
                "long_baseline": oos_view(base_full),
                "debit_spread": oos_view(spr_full),
                "delta": {k: _delta(oos_view(spr_full), oos_view(base_full), k)
                          for k in ("n", "exp_dollar", "total_dollar", "book_maxdd",
                                    "sharpe", "sortino")},
            },
            "full_window": _ab_block(b, base_full, base_recent, spr_full, spr_recent)["full_window"],
            "recent_window": _ab_block(b, base_full, base_recent, spr_full, spr_recent)["recent_window"],
        })

    # ── Strip non-serializable, write JSON ──
    for c in grid:
        c.pop("_trades", None)

    def m_pub(m):  # drop nothing; metrics already JSON-safe
        return m

    summary = {
        "family": "vwap_continuation_SPREADIFY",
        "run_date": dt.date.today().isoformat(),
        "window": f"{sig_days[0]}..{sig_days[-1]}",
        "trading_days": n_days,
        "thesis": ("recency RED = -8% premium stop whipsawing LONG single-leg in chop; "
                   "debit vertical caps risk + cuts theta/vega/whipsaw; short leg caps "
                   "upside -> lower EV but better risk-adjusted + less recency bleed"),
        "detector": "BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals (live port: vwap_continuation_watcher.py)",
        "fills_authority": ("real OPRA bars: long via lib.simulator_real.simulate_trade_real; "
                            "spread via lib.simulator_debit.simulate_debit_trade (validated 15/15); "
                            "SAME option_pricing_real OPRA loader -> byte-consistent fills (C1)"),
        "recent_window_days": RECENT_DAYS,
        "oos_split": f"OOS={OOS_YEAR} (calendar-year)",
        "n_signals": len(signals),
        "long_baselines": {t: {"full": long_full[t], "recent": long_recent[t]}
                           for t in LONG_TIERS},
        "spread_grid": grid,
        "best_spread_cell": best and {k: best[k] for k in
                                      ("long_near", "near_offset", "width", "pt_frac",
                                       "stop_frac", "coverage", "full", "recent")},
        "AB": ab_blocks,
        "DISCLOSURE": {
            "structure_isolation": ("long baseline runs LIVE v15 layered exits = the true "
                                    "production comparator; spread runs net-debit pt/stop. "
                                    "Exit engines differ by necessity (a vertical has no "
                                    "ribbon-flip TP); deltas reflect STRUCTURE+exit jointly."),
            "short_leg_caps_upside": "expected lower per-trade EV; the bar is risk-adjusted (L175)",
            "band": "all spread legs forced inside +/-$5 OPRA cache band; band_miss disclosed",
            "fills": "real OPRA, causal next-bar-open entry, no look-ahead",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[spreadify] wrote {OUT_JSON}", flush=True)
    _write_md(summary, long_full, long_recent, best)
    print(f"[spreadify] wrote {OUT_MD}", flush=True)

    # ── Console verdict ──
    print("\n=== SPREAD-IFY vwap_continuation VERDICT ===")
    for t in LONG_TIERS:
        m, r = long_full[t], long_recent[t]
        print(f"LONG {t}: full n={m['n']} exp=${m['exp_dollar']} maxDD=${m['book_maxdd']} "
              f"| recent({RECENT_DAYS}d) total=${r['total_dollar']} maxDD=${r['book_maxdd']}")
    if best:
        bf, br = best["full"], best["recent"]
        b = base_for(best["long_near"])
        print(f"BEST SPREAD: long={best['long_near']} w=${best['width']} pt={best['pt_frac']} "
              f"stop={best['stop_frac']} (vs LONG {b})")
        print(f"  full: n={bf['n']} exp=${bf['exp_dollar']} oos_exp=${bf['oos_exp']} "
              f"maxDD=${bf['book_maxdd']} sharpe={bf['sharpe']} sortino={bf['sortino']}")
        print(f"  recent({RECENT_DAYS}d): n={br['n']} exp=${br['exp_dollar']} "
              f"total=${br['total_dollar']} maxDD=${br['book_maxdd']} sharpe={br['sharpe']}")
        print(f"  vs LONG {b} recent total=${long_recent[b]['total_dollar']} "
              f"maxDD=${long_recent[b]['book_maxdd']}")
    return 0


def _fmt(v):
    return "n/a" if v is None else (f"{v}")


def _write_md(summary, long_full, long_recent, best):
    L = []
    L.append("# PIVOT / SPREAD-IFY Scorecard\n")
    L.append("> Real OPRA fills (C1). Long single-leg (simulator_real, live v15 exits) "
             "vs DEBIT VERTICAL (simulator_debit, validated 15/15). $0, markets closed.\n")
    L.append(f"\n## #1 vwap_continuation  (the LIVE edge IN THE DRAWDOWN)\n")
    L.append(f"- Run: {summary['run_date']}  window {summary['window']}  "
             f"signals={summary['n_signals']}  recent window = last "
             f"{summary['recent_window_days']} trading days\n")
    L.append(f"- Thesis: {summary['thesis']}\n")

    L.append("\n### Long single-leg baselines (the things being rescued)\n")
    L.append("| Tier | scope | n | exp/tr | total | maxDD | Sharpe | Sortino | WR% |\n")
    L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|\n")
    for t in long_full:
        for scope, m in (("full", long_full[t]), (f"recent{summary['recent_window_days']}", long_recent[t])):
            L.append(f"| LONG {t} | {scope} | {m.get('n')} | ${m.get('exp_dollar')} | "
                     f"${m.get('total_dollar')} | ${m.get('book_maxdd')} | "
                     f"{_fmt(m.get('sharpe'))} | {_fmt(m.get('sortino'))} | {m.get('wr_pct')} |\n")
        mo = long_full[t]
        L.append(f"| LONG {t} | OOS2026 | {mo.get('oos_n')} | ${mo.get('oos_exp')} | "
                 f"${mo.get('oos_total')} | ${mo.get('oos_maxdd')} | "
                 f"{_fmt(mo.get('oos_sharpe'))} | {_fmt(mo.get('oos_sortino'))} | - |\n")

    if best:
        bf, br = best["full"], best["recent"]
        bbase = "ITM-2" if best["long_near"] == "ITM-2" else "ATM"
        L.append(f"\n### BEST debit-spread cell  "
                 f"(long {best['long_near']} / short ${best['width']} OTM / "
                 f"pt={best['pt_frac']} stop={best['stop_frac']})  vs LONG {bbase}\n")
        L.append("| scope | struct | n | exp/tr | total | maxDD | Sharpe | Sortino | WR% |\n")
        L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|\n")
        lf, lr = long_full[bbase], long_recent[bbase]
        rows = [
            ("full", "LONG", lf), ("full", "SPREAD", bf),
            ("OOS2026", "LONG", {"n": lf.get("oos_n"), "exp_dollar": lf.get("oos_exp"),
                                 "total_dollar": lf.get("oos_total"), "book_maxdd": lf.get("oos_maxdd"),
                                 "sharpe": lf.get("oos_sharpe"), "sortino": lf.get("oos_sortino"),
                                 "wr_pct": None}),
            ("OOS2026", "SPREAD", {"n": bf.get("oos_n"), "exp_dollar": bf.get("oos_exp"),
                                   "total_dollar": bf.get("oos_total"), "book_maxdd": bf.get("oos_maxdd"),
                                   "sharpe": bf.get("oos_sharpe"), "sortino": bf.get("oos_sortino"),
                                   "wr_pct": None}),
            (f"recent{summary['recent_window_days']}", "LONG", lr),
            (f"recent{summary['recent_window_days']}", "SPREAD", br),
        ]
        for scope, st, m in rows:
            L.append(f"| {scope} | {st} | {m.get('n')} | ${m.get('exp_dollar')} | "
                     f"${m.get('total_dollar')} | ${m.get('book_maxdd')} | "
                     f"{_fmt(m.get('sharpe'))} | {_fmt(m.get('sortino'))} | "
                     f"{_fmt(m.get('wr_pct'))} |\n")
        # deltas
        L.append(f"\n**Deltas (SPREAD - LONG {bbase}):**\n")
        for scope, lm, sm in (("full", lf, bf),
                              (f"recent{summary['recent_window_days']}", lr, br)):
            de = round((sm.get("exp_dollar") or 0) - (lm.get("exp_dollar") or 0), 2)
            dt_ = round((sm.get("total_dollar") or 0) - (lm.get("total_dollar") or 0), 2)
            dd = round((sm.get("book_maxdd") or 0) - (lm.get("book_maxdd") or 0), 2)
            ds = None
            if sm.get("sharpe") is not None and lm.get("sharpe") is not None:
                ds = round(sm["sharpe"] - lm["sharpe"], 4)
            L.append(f"- {scope}: exp/tr {de:+.2f}, total {dt_:+.2f}, "
                     f"maxDD {dd:+.2f} (positive=less drawdown), Sharpe {_fmt(ds)}\n")
    else:
        L.append("\n### No debit-spread cell reached n>=20 with positive full-OOS expectancy.\n")
    L.append("\n---\n*Generated by `backtest/autoresearch/_spreadify_vwap_continuation.py`.*\n")
    # Append to the scorecard file (per task: "Write a section").
    existing = OUT_MD.read_text(encoding="utf-8") if OUT_MD.exists() else ""
    OUT_MD.write_text(existing + ("\n\n" if existing else "") + "".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
