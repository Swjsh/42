"""NEW-HUNT: Connors RSI(2) intraday mean-reversion on SPY 5m -> 0DTE single-leg directional.

Engine does NOT have this. We have RSI DIVERGENCE but not RSI(2) THRESHOLD mean-reversion.

────────────────────────────────────────────────────────────────────────────────
STEP 1 — SOURCED RULES (Larry Connors' 2-period RSI, "Short Term Trading Strategies
That Work"). Numbers are taken VERBATIM from reputable sources — NOT invented:

  Trend filter:  200-period MA. Long ONLY when price > 200MA; short ONLY when < 200MA.
                 (StockCharts ChartSchool; OptionsTradingIQ)
  Long  entry :  RSI(2) < 10 (primary) — "returns were higher buying on a dip below 5"
                 (more oversold = higher subsequent return). We sweep BOTH 5 and 10.
  Short entry :  RSI(2) > 90 (primary) — "returns were higher selling short above 95".
                 We sweep BOTH 95 and 90.
  Exit (orig) :  close back above the 5-period SMA (long) / below 5-SMA (short). This is
                 a 1-3 DAY SWING exit and CANNOT apply to a 0DTE single-day option, so we
                 substitute the v15 production intraday exit stack (TP1 +30% / chart-level,
                 BE-runner, 15:50 hard time stop) per the task spec.
  Stops       :  Connors does NOT advocate fixed stops ("stops hurt performance ... they
                 frequently exited before the bounce"). The TRUEST-to-source cell is
                 therefore premium_stop_pct=-0.99 (chart-stop only). We still sweep the
                 prescribed stop grid so the disclosure is honest.
  Edge stat   :  Published equity edge ~ "win rate exceeding 75%, 1-3 day holds" (per the
                 WebSearch summary of QuantifiedStrategies/Connors). NOTE (C3/L58): that is
                 an EQUITY-SWING, end-of-day-close edge — NOT a 0DTE option edge, and not on
                 5-min bars. We are stress-testing whether ANY of it survives the translation
                 to SPY 5m intraday -> real OPRA 0DTE fills. Expectation should be LOW.

  Sources (cited in the JSON + returned schema):
    - https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
    - https://www.quantifiedstrategies.com/rsi-2-strategy/
    - https://optionstradingiq.com/2-period-rsi-strategy/

ADAPTATION TO SPY 5m INTRADAY 0DTE (single-leg directional):
  - RSI(2) computed on the CONTINUOUS RTH 5-min close series (Wilder smoothing), causally
    (value at bar i uses closes <= bar i; entry fills on the NEXT bar via simulator_real —
    no look-ahead, C6).
  - 200MA = 200-bar SMA on the same continuous 5-min close series (~2.5 RTH days of lookback).
  - long  signal (oversold + uptrend)  -> BUY CALL ('C')
    short signal (overbought + downtrend) -> BUY PUT  ('P')
  - rejection_level (the strategy's INVALIDATION, so the chart-stop is meaningful):
      CALL -> recent SWING LOW below entry  (support that must hold)
      PUT  -> recent SWING HIGH above entry (resistance that must hold)
    computed over a trailing window of prior bars (no current-bar low/high look-ahead beyond
    the closed trigger bar).
  - Cooldown 45 min between signals (anti-pattern 2.7 — no back-to-back same-setup churn).

STEP 3 — REAL-FILLS (C1 authority): simulator_real.simulate_trade_real, v15 default exits,
qty=3. Grid: strike_offset {-2,-1,0,1,2} x premium_stop_pct {-0.08,-0.20,-0.50,-0.99}.

STEP 4 — SELF-VERIFY (deterministic, in-script — NO agents): for the best cell, compute
drop-top-5-days per-trade, IS(2025)/OOS(2026), positive_quarters/6, top5-day concentration.
REAL CANDIDATE iff: OOS per-trade>0 AND positive_quarters>=4/6 AND top5<200% AND n>=20 AND
drop-top-5 per-trade still >0. OP-20: report per-trade EXPECTANCY not WR; no cherry-picking.

Output: analysis/recommendations/newhunt-rsi2-mean-reversion.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-rsi2-mean-reversion.json"

# ── Strategy parameters ──────────────────────────────────────────────────────
RSI_PERIOD = 2
SMA_TREND_PERIOD = 200          # Connors 200MA trend filter (on 5m closes)
SWING_LOOKBACK = 12             # bars for invalidation swing low/high (~60 min)
QTY = 3
COOLDOWN_MIN = 45
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
ENTRY_GATE_START = dt.time(9, 35)   # match prod 09:35 entry gate (no first-bar)
ENTRY_GATE_END = dt.time(15, 45)    # leave room before 15:50 time stop
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# Grid (task spec)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

# Threshold variants (Connors' two published levels for each side)
# (long_thr, short_thr) — long fires RSI<long_thr; short fires RSI>short_thr
THRESHOLD_VARIANTS = [
    ("5_95", 5.0, 95.0),    # aggressive (more oversold/overbought — Connors: higher returns)
    ("10_90", 10.0, 90.0),  # primary published levels
]

# Self-verify gate
GATE = {"oos_per_trade": 0.0, "positive_quarters_min": 4, "top5_max_pct": 200.0,
        "n_min": 20, "drop_top5_per_trade_min": 0.0}


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI (standard RSI as used by Connors / StockCharts). Causal — value at i
    uses closes through i only. RMA = exponential with alpha=1/period (Wilder smoothing)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # If avg_loss==0 -> RSI=100; if avg_gain==0 -> RSI=0 (handle div-by-zero cleanly)
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return rsi


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _drop_top5_per_trade(rows: list[dict]) -> tuple[float, int, float]:
    """Per-trade expectancy after removing the 5 best P&L days. Returns
    (per_trade_ex_top5, n_ex_top5, dropped_pnl)."""
    by_day: dict[str, float] = defaultdict(float)
    by_day_n: dict[str, int] = defaultdict(int)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
        by_day_n[r["date"]] += 1
    top5_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    kept = [r for r in rows if r["date"] not in top5_days]
    dropped_pnl = sum(by_day[d] for d in top5_days)
    if not kept:
        return 0.0, 0, dropped_pnl
    return sum(r["pnl"] for r in kept) / len(kept), len(kept), dropped_pnl


def build_signals(rth: pd.DataFrame, vix_arr: list[float], long_thr: float, short_thr: float) -> list[dict]:
    """Causal RSI(2) mean-reversion signals on the continuous 5m close series.

    rth must be the full RTH-only frame (continuous across days, reset_index). RSI(2) and
    SMA200 are computed on the continuous close series; signals only emitted inside the
    09:35-15:45 entry gate with a 45-min cooldown.
    """
    close = rth["close"].astype(float)
    rsi = wilder_rsi(close, RSI_PERIOD)
    sma = close.rolling(SMA_TREND_PERIOD, min_periods=SMA_TREND_PERIOD).mean()

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None

    for idx in range(len(rth)):
        r = rsi.iloc[idx]
        s = sma.iloc[idx]
        if pd.isna(r) or pd.isna(s):
            continue
        bar = rth.iloc[idx]
        ts = pd.Timestamp(bar["timestamp_et"])
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        bar_dt = ts.to_pydatetime()
        t = bar_dt.time()
        if t < ENTRY_GATE_START or t > ENTRY_GATE_END:
            continue
        bd = bar_dt.date()
        if bd < START or bd > END:
            continue

        c = float(bar["close"])
        # Connors trend filter + RSI threshold
        long_sig = (r < long_thr) and (c > s)     # oversold in uptrend -> CALL
        short_sig = (r > short_thr) and (c < s)   # overbought in downtrend -> PUT
        if not (long_sig or short_sig):
            continue

        if last_sig_time is not None and (bar_dt - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue

        side = "C" if long_sig else "P"

        # Invalidation level (so the chart-stop is meaningful):
        #   CALL -> swing LOW (support) over the trailing window, strictly below entry
        #   PUT  -> swing HIGH (resistance) over the trailing window, strictly above entry
        lo_start = max(0, idx - SWING_LOOKBACK + 1)
        win = rth.iloc[lo_start: idx + 1]
        if side == "C":
            swing = float(win["low"].min())
            rej = swing if swing < c else round(c - 1.0, 2)  # fallback $1 below if degenerate
        else:
            swing = float(win["high"].max())
            rej = swing if swing > c else round(c + 1.0, 2)

        last_sig_time = bar_dt
        signals.append({
            "idx": idx, "date": bd, "time": bar_dt.strftime("%H:%M"), "side": side,
            "rsi2": round(float(r), 2), "sma200": round(float(s), 2),
            "entry_spot": round(c, 2), "rejection_level": round(float(rej), 2),
            "vix": round(vix_arr[idx], 1),
        })
    return signals


def simulate_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                  premium_stop_pct: float) -> tuple[_Acc, list[dict], int]:
    """Run real-fills for one (strike_offset, premium_stop) cell. Returns
    (overall accumulator, per-trade rows, n_no_opra_data)."""
    overall = _Acc()
    rows: list[dict] = []
    no_data = 0
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["rsi2_mean_reversion", "trend_filter_sma200",
                            "oversold" if s["side"] == "C" else "overbought"],
            side=s["side"], qty=QTY, setup="RSI2_MEAN_REVERSION",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "rsi2": s["rsi2"],
            "vix": s["vix"], "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2), "year": s["date"].year, "quarter": _quarter(s["date"]),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })
    return overall, rows, no_data


def verify_cell(rows: list[dict]) -> dict:
    """Deterministic self-verification for a single cell's per-trade rows."""
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    overall = _Acc()
    for r in rows:
        overall.add(r["pnl"], r["date"])
        by_sample["IS_2025" if r["year"] == 2025 else "OOS_2026"].add(r["pnl"], r["date"])
        by_q[r["quarter"]].add(r["pnl"], r["date"])

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for v in q_reports.values() if v.get("total_pnl", 0) and v["total_pnl"] > 0)
    is_r, oos_r = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    drop_pt, n_ex, dropped = _drop_top5_per_trade(rows)
    ov = overall.report()

    oos_pt = oos_r.get("per_trade") if oos_r.get("n") else None
    clears = bool(
        (oos_pt is not None and oos_pt > GATE["oos_per_trade"]) and
        (pos_q >= GATE["positive_quarters_min"]) and
        (ov.get("top5_day_pct") is not None and ov["top5_day_pct"] < GATE["top5_max_pct"]) and
        (ov["n"] >= GATE["n_min"]) and
        (drop_pt > GATE["drop_top5_per_trade_min"])
    )
    return {
        "overall": ov,
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "positive_quarters_n": pos_q,
        "n_quarters": len(q_reports),
        "oos_per_trade": oos_pt,
        "drop_top5_per_trade": round(drop_pt, 2),
        "drop_top5_n": n_ex,
        "dropped_top5_pnl": round(dropped, 0),
        "top5_day_pct": ov.get("top5_day_pct"),
        "clears_bar": clears,
    }


def run() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_START)
                   & (spy_full["timestamp_et"].dt.time < RTH_END)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) — same pattern as confluence_real_fills_validate.py
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr: list[float] = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)

    all_variant_summaries: dict = {}
    global_best = None  # (per_trade, variant_tag, so, ps, overall, rows, verify)

    for tag, long_thr, short_thr in THRESHOLD_VARIANTS:
        signals = build_signals(rth, vix_arr, long_thr, short_thr)
        n_long = sum(1 for s in signals if s["side"] == "C")
        n_short = sum(1 for s in signals if s["side"] == "P")
        log.info("[%s] signals=%d (long/CALL=%d short/PUT=%d)", tag, len(signals), n_long, n_short)

        cells = []
        for so in STRIKE_OFFSETS:
            for ps in PREMIUM_STOPS:
                overall, rows, no_data = simulate_cell(rth, signals, so, ps)
                rep = overall.report()
                cells.append({
                    "strike_offset": so, "premium_stop_pct": ps,
                    "report": rep, "n_no_opra_data": no_data, "_rows": rows,
                })
                pt = rep.get("per_trade")
                log.info("  [%s] so=%+d ps=%.2f -> n=%s per_trade=%s total=%s top5%%=%s",
                         tag, so, ps, rep.get("n"), pt, rep.get("total_pnl"), rep.get("top5_day_pct"))
                if pt is not None and rep.get("n", 0) >= GATE["n_min"]:
                    if global_best is None or pt > global_best[0]:
                        global_best = (pt, tag, so, ps, overall, rows, None)

        # rank cells by per-trade (only those with n>=n_min eligible to "win")
        ranked = sorted(
            [c for c in cells if c["report"].get("per_trade") is not None],
            key=lambda c: c["report"]["per_trade"], reverse=True)
        all_variant_summaries[tag] = {
            "long_threshold": long_thr, "short_threshold": short_thr,
            "n_signals": len(signals), "n_long_call": n_long, "n_short_put": n_short,
            "cells": [{k: v for k, v in c.items() if k != "_rows"} for c in ranked],
        }
        # stash rows for the best cell of this variant for potential best-overall verify
        for c in cells:
            c["report"].pop("_rows", None)

    # ── Self-verify the GLOBAL best cell (by per-trade, n>=20) ──
    best_block = None
    if global_best is not None:
        pt, tag, so, ps, overall, rows, _ = global_best
        verify = verify_cell(rows)
        n_call_best = sum(1 for r in rows if r["side"] == "C")
        n_put_best = sum(1 for r in rows if r["side"] == "P")
        # Coin-flip null: how much of pt is RSI(2) signal vs the asymmetric exit structure?
        log.info("Running random-entry NULL for best cell (C3/L58 structure-vs-signal probe)...")
        null = random_entry_null(rth, n_signals=len(rows), n_call=n_call_best,
                                 n_put=n_put_best, strike_offset=so, premium_stop_pct=ps,
                                 entry_gate=(ENTRY_GATE_START, ENTRY_GATE_END),
                                 swing_lookback=SWING_LOOKBACK, qty=QTY)
        # Standard null candidate-gate (C3/L58, null_baseline.null_gate): the headline
        # per-trade must clear the null MAX (a lucky coin-flip), not just be positive, AND
        # the concentration-robust drop-top5 per-trade must beat the null MEAN.
        gate = null_gate(pt, verify["drop_top5_per_trade"], null)
        edge_over_null = gate["edge_over_null_per_trade"]
        beats_null_max = gate["beats_null_max"]
        drop_beats_null_mean = gate["drop_top5_beats_null_mean"]
        null["edge_over_null_per_trade"] = edge_over_null
        null["beats_null_mean"] = gate["beats_null_mean"]
        null["beats_null_max"] = gate["beats_null_max"]
        null["best_beats_null_max"] = gate["beats_null_max"]   # legacy schema key (downstream + JSON)
        null["drop_top5_beats_null_mean"] = gate["drop_top5_beats_null_mean"]
        null["null_pass"] = gate["null_pass"]
        best_block = {
            "variant": tag, "strike_offset": so, "premium_stop_pct": ps,
            "per_trade": pt, "verify": verify, "random_entry_null": null,
            "sample_rows": rows[:25],
        }
        log.info("=== GLOBAL BEST: %s so=%+d ps=%.2f per_trade=%.2f ===", tag, so, ps, pt)
        log.info("    verify: %s", {k: verify[k] for k in
                 ("overall", "by_sample", "positive_quarters", "oos_per_trade",
                  "drop_top5_per_trade", "top5_day_pct", "clears_bar")})
        log.info("    NULL: %s  edge_over_null=%.2f  beats_null_max=%s  drop_top5_beats_null_mean=%s",
                 null, edge_over_null, beats_null_max, drop_beats_null_mean)

    # Honest gate: the coded structural gate AND the signal must beat a coin-flip null.
    # A 0DTE 'edge' that random entries reproduce is exit-structure + day-concentration,
    # not RSI(2) alpha (C3/L58, anti-pattern 2.10).
    coded_pass = bool(best_block and best_block["verify"]["clears_bar"])
    null_pass = bool(best_block and best_block["random_entry_null"]["best_beats_null_max"]
                     and best_block["random_entry_null"]["drop_top5_beats_null_mean"])
    clears_bar = bool(coded_pass and null_pass)

    if not best_block:
        verdict = "NO_CANDIDATE: no cell reached n>=20 signals — strategy too sparse on SPY 5m 0DTE"
    elif clears_bar:
        verdict = ("REAL CANDIDATE: best cell clears all structural gates AND beats the random-entry "
                   "null (signal adds edge beyond the asymmetric exit structure)")
    else:
        v = best_block["verify"]
        nl = best_block["random_entry_null"]
        fails = []
        if not (v["oos_per_trade"] is not None and v["oos_per_trade"] > 0):
            fails.append(f"OOS per-trade={v['oos_per_trade']} (need >0)")
        if v["positive_quarters_n"] < GATE["positive_quarters_min"]:
            fails.append(f"positive_quarters={v['positive_quarters']} (need >=4/6)")
        if not (v["top5_day_pct"] is not None and v["top5_day_pct"] < GATE["top5_max_pct"]):
            fails.append(f"top5_day_pct={v['top5_day_pct']} (need <200)")
        if v["overall"]["n"] < GATE["n_min"]:
            fails.append(f"n={v['overall']['n']} (need >=20)")
        if not (v["drop_top5_per_trade"] > 0):
            fails.append(f"drop_top5_per_trade={v['drop_top5_per_trade']} (need >0)")
        if not nl["best_beats_null_max"]:
            fails.append(f"per_trade={best_block['per_trade']} does NOT beat random-null MAX "
                         f"{nl['per_trade_max']} (edge_over_null_mean={nl['edge_over_null_per_trade']}) "
                         f"=> 'edge' is the asymmetric exit STRUCTURE, not RSI(2) (C3/L58)")
        if not nl["drop_top5_beats_null_mean"]:
            fails.append(f"drop-top5 per-trade={v['drop_top5_per_trade']} <= random-null mean "
                         f"{nl['per_trade_mean']} => surviving edge is day-concentration, not signal")
        verdict = ("NOT A CANDIDATE (no cherry-pick): even the per-trade-best cell fails — " +
                   "; ".join(fails))

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "rsi2_mean_reversion",
        "hypothesis": ("Connors RSI(2) intraday mean-reversion: RSI(2)<thr in uptrend -> CALL; "
                       "RSI(2)>thr in downtrend -> PUT. Engine has RSI DIVERGENCE, not RSI(2) "
                       "threshold mean-reversion."),
        "window": f"{START}..{END}",
        "sourced_rules": {
            "trend_filter": "200-period MA; long only price>200MA, short only price<200MA (Connors)",
            "long_entry": "RSI(2) < 10 primary; <5 'higher returns' (more oversold). Both swept.",
            "short_entry": "RSI(2) > 90 primary; >95 'higher returns' (more overbought). Both swept.",
            "original_exit": "close back above/below 5-period SMA (1-3 day swing) — N/A for 0DTE; "
                             "substituted v15 intraday exits (TP1 +30%/chart-level, BE runner, 15:50 stop)",
            "stops": "Connors does NOT advocate fixed stops -> truest cell premium_stop=-0.99 (chart-only)",
            "published_edge": "equity-swing ~WR>75%, 1-3 day holds — NOT a 0DTE option edge (C3/L58); "
                              "this run tests whether ANY survives the 5m-intraday->0DTE translation",
        },
        "sources": [
            "https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2",
            "https://www.quantifiedstrategies.com/rsi-2-strategy/",
            "https://optionstradingiq.com/2-period-rsi-strategy/",
        ],
        "adaptation": {
            "instrument": "SPY 0DTE single-leg directional (long->CALL, short->PUT)",
            "rsi_period": RSI_PERIOD, "smoothing": "Wilder (RMA)", "timeframe": "5min RTH continuous",
            "sma_trend_period": SMA_TREND_PERIOD, "swing_lookback_bars": SWING_LOOKBACK,
            "rejection_level": "CALL->trailing swing LOW (support); PUT->trailing swing HIGH (resistance)",
            "cooldown_min": COOLDOWN_MIN, "entry_gate": f"{ENTRY_GATE_START}-{ENTRY_GATE_END}",
            "qty": QTY, "exits": "v15 defaults (causal, no look-ahead C6)",
        },
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS,
                 "threshold_variants": [{"tag": t, "long": l, "short": s} for t, l, s in THRESHOLD_VARIANTS]},
        "self_verify_gate": GATE,
        "variants": all_variant_summaries,
        "best_cell": best_block,
        "clears_bar": clears_bar,
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14)",
            "is_oos": "IS=2025, OOS=2026 split shown for the best cell",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5; anti-pattern 2.10)",
            "no_cherry_pick": "verdict uses the per-trade-BEST cell; if it is thin-N/high-concentration/"
                              "OOS-negative we say so and clears_bar=false",
            "spy_vs_option": "C3/L58 — a SPY-price/equity edge is NOT an option edge; theta+delta+stop-misfire "
                             "routinely erase a directional-underlying edge in 0DTE",
            "random_entry_null": "best cell compared to a coin-flip null (random RTH entries, same count/"
                                 "side-mix/stop/strike). If random entries reproduce the per-trade, the "
                                 "'edge' is the asymmetric exit STRUCTURE (tight stop + +30% TP1 + runner), "
                                 "not the RSI(2) signal — this is the decisive C3/L58 test.",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== RSI(2) MEAN-REVERSION NEW-HUNT VERDICT ===")
    for tag, vs in all_variant_summaries.items():
        top = vs["cells"][0] if vs["cells"] else None
        print(f"[{tag}] n_signals={vs['n_signals']} (CALL={vs['n_long_call']} PUT={vs['n_short_put']})"
              f"  best_cell={top['report'] if top else None} "
              f"(so={top['strike_offset'] if top else '-'} ps={top['premium_stop_pct'] if top else '-'})")
    if best_block:
        v = best_block["verify"]
        print(f"\nGLOBAL BEST: {best_block['variant']} so={best_block['strike_offset']:+d} "
              f"ps={best_block['premium_stop_pct']}")
        print(f"  overall={v['overall']}")
        print(f"  IS={v['by_sample']['IS_2025']}  OOS={v['by_sample']['OOS_2026']}")
        print(f"  positive_quarters={v['positive_quarters']}  oos_per_trade={v['oos_per_trade']}")
        print(f"  drop_top5_per_trade={v['drop_top5_per_trade']} (n={v['drop_top5_n']})  "
              f"top5_day_pct={v['top5_day_pct']}")
        nl = best_block["random_entry_null"]
        print(f"  RANDOM-NULL per_trade: mean={nl['per_trade_mean']} "
              f"[{nl['per_trade_min']}..{nl['per_trade_max']}]  edge_over_null={nl['edge_over_null_per_trade']}")
        print(f"  beats_null_max={nl['best_beats_null_max']}  "
              f"drop_top5_beats_null_mean={nl['drop_top5_beats_null_mean']}")
    print(f"\nCLEARS BAR: {clears_bar}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    run()
