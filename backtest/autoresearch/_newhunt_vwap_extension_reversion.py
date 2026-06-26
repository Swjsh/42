"""NEW-STRATEGY HUNT — vwap_extension_reversion (mean-reversion to session VWAP).

The engine has VWAP continuation/rejection but NOT a VWAP standard-deviation-BAND
EXTENSION FADE. This hunts that strategy on SPY 5m / 0DTE single-leg directional, with
the C1 real-fills authority (lib.simulator_real), per OP-11/OP-16/OP-20 disclosure.

────────────────────────────────────────────────────────────────────────────────
STRATEGY RULES (sourced — NOT invented; see analysis/recommendations JSON `sources`)
────────────────────────────────────────────────────────────────────────────────
Mean-reversion to the session VWAP after over-extension, the canonical VWAP-band fade:

  ENTRY  : price extends >= ENTRY_SD session-VWAP standard deviations from VWAP.
             close >= VWAP + ENTRY_SD*sigma  -> over-extended UP   -> SHORT -> buy PUT
             close <= VWAP - ENTRY_SD*sigma  -> over-extended DOWN -> LONG  -> buy CALL
           Default ENTRY_SD = 2.0  (the "2 SD band" every source converges on).
  CONFIRM: momentum-exhaustion via RSI(14):
             PUT  requires RSI >= RSI_HI  (overbought; default 70, Wilder canonical;
                   sources cite 75 for the high-prob variant — knob RSI_HI)
             CALL requires RSI <= RSI_LO  (oversold;   default 30; source variant 25)
  FRESH  : only fire on the bar that FIRST crosses the band (prior bar inside it) — a
           trend that rides the band does not re-fire every bar (anti-pattern 2.7 +
           the sources' "reversion fails badly on trend days" caveat).
  TARGET : revert to VWAP (handled by the engine's TP1: chart-level/premium fallback +
           v15 exits). VWAP is the mean the sources target.
  STOP   : the published invalidation is VWAP +/- 3 SD ("beyond 3 SD the gravitational
           pull weakens" — Tradewink/ChartSchool). We pass this as `rejection_level` so
           the engine chart-stop is meaningful and structural:
             CALL (faded a drop): invalidation = VWAP - STOP_SD*sigma  (support BELOW)
             PUT  (faded a pop):  invalidation = VWAP + STOP_SD*sigma  (resistance ABOVE)
  COOLDOWN: 35 min between signals.

Published edge (context only — SPY-direction proxy, NOT our option edge; C3/L58):
  2 SD band bounce ~61-64% WR @ 1.4-1.8:1 RR (SPY 180-session + QuantConnect 2022 NASDAQ
  100-stock backtests); 3 SD ~71%. We REPLACE this proxy with real 0DTE option P&L below.

────────────────────────────────────────────────────────────────────────────────
METHOD — copies db_base_quiet / confluence real-fills structure (load, OOS split,
by-quarter, top5). Sweeps strike_offset {-2,-1,0,1,2} x premium_stop_pct
{-0.08,-0.20,-0.50,-0.99}, v15 default exits. Self-verifies the best cell:
drop-top-5-days per-trade, IS(2025)/OOS(2026), positive_quarters/6, top5 concentration.

CANDIDATE BAR (all must hold): OOS per-trade>0 AND positive_quarters>=4/6 AND
top5<200% AND n>=20 AND drop-top-5 per-trade still >0. Else clears_bar=false (2.10:
no cherry-picking a thin/concentrated/OOS-negative cell).

Pure Python, $0 in the sim loop. Interpreter: backtest/.venv/Scripts/python.exe
Output: analysis/recommendations/newhunt-vwap-extension-reversion.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-vwap-extension-reversion.json"

# ── Strategy params (sourced) ───────────────────────────────────────────────────
ENTRY_SD = 2.0          # 2-SD band fade — the value every source converges on
STOP_SD = 3.0           # published invalidation: 3-SD band
RSI_LEN = 14
RSI_HI = 70.0           # PUT confirm (overbought); source high-prob variant = 75
RSI_LO = 30.0           # CALL confirm (oversold);  source high-prob variant = 25
COOLDOWN_MIN = 35
WARMUP_BARS = 6         # bars into the session before VWAP sigma is meaningful
QTY = 3
RTH_START = dt.time(9, 30)
RTH_END = dt.time(15, 55)
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── Sweep grid (small, per the hunt spec) ──────────────────────────────────────
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

SOURCES = [
    "https://www.tradewink.com/learn/mean-reversion-strategy",
    "https://chartswatcher.com/pages/blog/a-practical-guide-to-vwap-strategy-trading",
    "https://crosstrade.io/learn/trading-strategies/vwap-reversion",
    "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/volume-weighted-average-price-vwap",
    "https://www.quantifiedstrategies.com/vwap-trading-strategy/",
]


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _rsi_wilder(close: np.ndarray, length: int = 14) -> np.ndarray:
    """Wilder RSI computed causally (value at i uses closes through i). Standard
    Wilder smoothing (RMA). Returns NaN until `length` deltas are available."""
    n = len(close)
    rsi = np.full(n, np.nan)
    if n < length + 1:
        return rsi
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = gain[:length].mean()
    avg_loss = loss[:length].mean()
    def _val(ag, al):
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)
    rsi[length] = _val(avg_gain, avg_loss)
    for i in range(length + 1, n):
        avg_gain = (avg_gain * (length - 1) + gain[i - 1]) / length
        avg_loss = (avg_loss * (length - 1) + loss[i - 1]) / length
        rsi[i] = _val(avg_gain, avg_loss)
    return rsi


def _session_vwap_bands(day_df: pd.DataFrame, entry_sd: float):
    """Per-session cumulative VWAP + volume-weighted std-dev band sigma.

    Causal by construction: every value at row k is computed ONLY from rows 0..k of
    the same session (cumulative). The signal logic then evaluates the band on the
    just-closed bar and the simulator enters on the NEXT bar (no look-ahead).

    sigma_k = sqrt( cum(vol*tp^2)/cum(vol) - vwap_k^2 )  — the volume-weighted std of
    typical price about VWAP, the standard VWAP-band construction.
    """
    tp = (day_df["high"].to_numpy() + day_df["low"].to_numpy() + day_df["close"].to_numpy()) / 3.0
    vol = day_df["volume"].to_numpy().astype(float)
    vol = np.where(vol <= 0, 1.0, vol)  # guard zero-volume bars
    cum_v = np.cumsum(vol)
    cum_pv = np.cumsum(vol * tp)
    cum_pv2 = np.cumsum(vol * tp * tp)
    vwap = cum_pv / cum_v
    var = cum_pv2 / cum_v - vwap * vwap
    var = np.where(var < 0, 0.0, var)   # numerical guard
    sigma = np.sqrt(var)
    return vwap, sigma


def scan_signals(rth: pd.DataFrame, vix_arr: list[float]) -> list[dict]:
    """Scan all sessions for fresh 2-SD VWAP-band extension fades with RSI confirm."""
    rth = rth.copy()
    rth["date"] = rth["timestamp_et"].dt.date
    # global RSI computed per session (reset each day so warmup is intraday)
    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None

    for d, day_df in rth.groupby("date", sort=True):
        day_df = day_df.sort_values("timestamp_et")
        idxs = day_df.index.to_numpy()
        if len(day_df) < WARMUP_BARS + RSI_LEN + 1:
            continue
        vwap, sigma = _session_vwap_bands(day_df, ENTRY_SD)
        rsi = _rsi_wilder(day_df["close"].to_numpy(), RSI_LEN)
        closes = day_df["close"].to_numpy()

        # Track whether the PRIOR bar was already outside the band (so we only fire on
        # the FRESH crossing — a trend riding the band does not re-fire every bar).
        prev_above = False
        prev_below = False
        for k in range(len(day_df)):
            global_idx = int(idxs[k])
            ts = day_df["timestamp_et"].iloc[k]
            ts_naive = ts.tz_localize(None).to_pydatetime() if ts.tz is not None else ts.to_pydatetime()
            t = ts_naive.time()

            if k < WARMUP_BARS or sigma[k] <= 0 or np.isnan(rsi[k]):
                continue
            if t < RTH_START or t > RTH_END:
                continue

            upper = vwap[k] + ENTRY_SD * sigma[k]
            lower = vwap[k] - ENTRY_SD * sigma[k]
            upper3 = vwap[k] + STOP_SD * sigma[k]
            lower3 = vwap[k] - STOP_SD * sigma[k]
            c = closes[k]

            is_above = c >= upper
            is_below = c <= lower
            fresh_above = is_above and not prev_above
            fresh_below = is_below and not prev_below
            prev_above, prev_below = is_above, is_below

            side = None
            rejection_level = None
            if fresh_above and rsi[k] >= RSI_HI:
                # over-extended UP -> fade short -> PUT; invalidation = resistance above (3 SD)
                side = "P"
                rejection_level = float(upper3)
            elif fresh_below and rsi[k] <= RSI_LO:
                # over-extended DOWN -> fade long -> CALL; invalidation = support below (3 SD)
                side = "C"
                rejection_level = float(lower3)
            if side is None:
                continue

            # Skip exhaustion already past the 3-SD stop band (no room before invalidation).
            if side == "P" and c >= upper3:
                continue
            if side == "C" and c <= lower3:
                continue

            if last_sig_time is not None and (ts_naive - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
                continue
            last_sig_time = ts_naive

            signals.append({
                "global_idx": global_idx,
                "date": d,
                "time": ts_naive.strftime("%H:%M"),
                "side": side,
                "direction": "short_fade" if side == "P" else "long_fade",
                "close": float(c),
                "vwap": round(float(vwap[k]), 2),
                "sigma": round(float(sigma[k]), 3),
                "dist_sd": round(float((c - vwap[k]) / sigma[k]), 2),
                "rsi": round(float(rsi[k]), 1),
                "rejection_level": round(rejection_level, 2),
                "vix": round(float(vix_arr[global_idx]), 1),
            })
    return signals


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
            "avg_pnl": round(self.pnl / self.n, 1),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def simulate_cell(signals: list[dict], rth: pd.DataFrame, strike_offset: int,
                  premium_stop_pct: float) -> dict:
    """Run real-fills for one (strike_offset, premium_stop_pct) cell. Returns the
    per-trade rows + accumulators needed for verification."""
    rows: list[dict] = []
    no_data = 0
    for s in signals:
        gi = s["global_idx"]
        fill = simulate_trade_real(
            entry_bar_idx=gi,
            entry_bar=rth.iloc[gi],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["vwap_band_2sd_extension", "rsi_exhaustion",
                            s["direction"]],
            side=s["side"],
            qty=QTY,
            setup="VWAP_EXTENSION_REVERSION",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None:
            no_data += 1
            continue
        rows.append({
            "date": s["date"].isoformat(),
            "time": s["time"],
            "side": s["side"],
            "direction": s["direction"],
            "dist_sd": s["dist_sd"],
            "rsi": s["rsi"],
            "vix": s["vix"],
            "rejection_level": s["rejection_level"],
            "strike": fill.strike,
            "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(fill.dollar_pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
            "year": s["date"].year,
            "quarter": _quarter(s["date"]),
        })
    return {"rows": rows, "no_data": no_data}


def verify_cell(rows: list[dict]) -> dict:
    """Deterministic self-verification on one cell (no agents)."""
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    for r in rows:
        overall.add(r["pnl"], r["date"])
        by_sample["IS_2025" if r["year"] == 2025 else "OOS_2026"].add(r["pnl"], r["date"])
        by_q[r["quarter"]].add(r["pnl"], r["date"])

    n = overall.n
    avg = overall.pnl / n if n else 0.0

    # drop-top-5-DAYS per-trade: remove the 5 best P&L days, recompute per-trade
    by_day_pnl: dict[str, float] = defaultdict(float)
    by_day_n: dict[str, int] = defaultdict(int)
    for r in rows:
        by_day_pnl[r["date"]] += r["pnl"]
        by_day_n[r["date"]] += 1
    top5_days = set(sorted(by_day_pnl, key=lambda d: by_day_pnl[d], reverse=True)[:5])
    rem_pnl = sum(p for d, p in by_day_pnl.items() if d not in top5_days)
    rem_n = sum(c for d, c in by_day_n.items() if d not in top5_days)
    drop_top5_per_trade = round(rem_pnl / rem_n, 2) if rem_n > 0 else None

    # top5-DAY concentration as % of total P&L
    days_sorted = sorted(by_day_pnl.values(), reverse=True)
    top5_sum = sum(days_sorted[:5])
    top5_day_pct = round(100 * top5_sum / overall.pnl, 1) if overall.pnl > 0 else None

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    n_q = len(q_reports)

    oos = by_sample["OOS_2026"].report()
    is_r = by_sample["IS_2025"].report()
    oos_pt = oos.get("avg_pnl") if oos.get("n") else None

    return {
        "n": n,
        "overall_per_trade": round(avg, 2),
        "overall_total_pnl": round(overall.pnl, 0),
        "wr": round(100 * overall.wins / n, 1) if n else 0.0,
        "drop_top5_per_trade": drop_top5_per_trade,
        "top5_day_pct": top5_day_pct,
        "IS_2025": is_r,
        "OOS_2026": oos,
        "oos_per_trade": oos_pt,
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{n_q}",
        "_pos_q_int": pos_q,
        "_n_q_int": n_q,
    }


def clears_bar(v: dict) -> bool:
    """CANDIDATE bar: OOS per-trade>0 AND positive_quarters>=4/6 AND top5<200% AND
    n>=20 AND drop-top-5 per-trade still >0."""
    if v["n"] < 20:
        return False
    if v["oos_per_trade"] is None or v["oos_per_trade"] <= 0:
        return False
    if v["_pos_q_int"] < 4:
        return False
    if v["top5_day_pct"] is None or v["top5_day_pct"] >= 200.0:
        return False
    if v["drop_top5_per_trade"] is None or v["drop_top5_per_trade"] <= 0:
        return False
    return True


def main() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    t = spy_full["timestamp_et"].dt.time
    rth = spy_full[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    # VIX aligned by ffill (same approach as the reference validators)
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

    log.info("Scanning for fresh 2-SD VWAP-band extension fades (RSI %.0f/%.0f)...", RSI_HI, RSI_LO)
    signals = scan_signals(rth, vix_arr)
    n_long = sum(1 for s in signals if s["side"] == "C")
    n_short = sum(1 for s in signals if s["side"] == "P")
    log.info("Signals: %d  (CALL/long-fade=%d, PUT/short-fade=%d)", len(signals), n_long, n_short)

    if not signals:
        summary = {
            "run_date": dt.date.today().isoformat(),
            "strategy": "vwap_extension_reversion",
            "window": f"{START}..{END}",
            "n_signals": 0,
            "verdict": "NO SIGNALS — band/RSI confirm too strict on this data; strategy did not trigger.",
            "clears_bar": False,
            "sources": SOURCES,
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary

    # ── Sweep the grid ──────────────────────────────────────────────────────────
    cells = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            sim = simulate_cell(signals, rth, so, ps)
            v = verify_cell(sim["rows"]) if sim["rows"] else {"n": 0}
            cell = {
                "strike_offset": so,
                "premium_stop_pct": ps,
                "n": v.get("n", 0),
                "no_opra_data": sim["no_data"],
                "verify": v,
                "clears_bar": clears_bar(v) if v.get("n", 0) >= 20 else False,
                "_rows": sim["rows"],
            }
            cells.append(cell)
            log.info("cell so=%+d ps=%.2f  n=%d  per_trade=%s  OOS_pt=%s  pos_q=%s  top5=%s%%  dropTop5=%s",
                     so, ps, v.get("n", 0),
                     v.get("overall_per_trade"), v.get("oos_per_trade"),
                     v.get("positive_quarters"), v.get("top5_day_pct"),
                     v.get("drop_top5_per_trade"))

    # ── Pick the best cell ───────────────────────────────────────────────────────
    # Prefer cells that CLEAR the bar; rank by OOS per-trade then overall per-trade.
    # If none clear, still surface the best overall per-trade cell for honest disclosure.
    clearing = [c for c in cells if c["clears_bar"]]
    pool = clearing if clearing else [c for c in cells if c["n"] >= 20] or cells
    def _key(c):
        v = c["verify"]
        oos = v.get("oos_per_trade") or -1e9
        ov = v.get("overall_per_trade") or -1e9
        return (oos, ov)
    best = max(pool, key=_key)
    bv = best["verify"]

    any_clears = bool(clearing)
    verdict = (
        f"CANDIDATE — best cell (so={best['strike_offset']:+d}, ps={best['premium_stop_pct']}) "
        f"clears the bar: OOS/trade=${bv.get('oos_per_trade')}, pos_q={bv.get('positive_quarters')}, "
        f"top5={bv.get('top5_day_pct')}%, drop-top5/trade=${bv.get('drop_top5_per_trade')}, n={bv.get('n')}."
        if any_clears else
        "NO CANDIDATE — no cell clears the full bar (OOS/trade>0 AND pos_q>=4/6 AND top5<200% "
        "AND n>=20 AND drop-top5/trade>0). The VWAP-band extension fade does not show a robust "
        "real-fills 0DTE option edge on 2025-01..2026-05. Best cell shown for disclosure only "
        "(anti-pattern 2.10 — not cherry-picked as a survivor)."
    )

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "vwap_extension_reversion",
        "hypothesis": ("Mean-reversion to session VWAP after over-extension: fade back toward "
                       "VWAP when price >= 2 VWAP-std-dev bands away (above-band->PUT, "
                       "below-band->CALL), RSI(14) exhaustion confirm, invalidation at 3-SD band."),
        "sourced_rules": {
            "entry": "close >= VWAP + 2*sigma -> PUT (short fade); close <= VWAP - 2*sigma -> CALL (long fade). 2-SD band is the source-converged threshold.",
            "confirm": f"RSI(14) >= {RSI_HI} for PUT / <= {RSI_LO} for CALL (Wilder; source high-prob variant 75/25).",
            "fresh": "only the bar that FIRST crosses the band fires (no re-fire while a trend rides the band).",
            "target": "revert to VWAP (engine TP1: chart-level/premium fallback + v15 exits).",
            "stop": "published invalidation = VWAP +/- 3*sigma, passed as rejection_level (CALL: support below; PUT: resistance above).",
            "cooldown_min": COOLDOWN_MIN,
            "entry_sd": ENTRY_SD, "stop_sd": STOP_SD, "rsi_len": RSI_LEN,
        },
        "published_edge_context": ("2-SD band bounce ~61-64% WR @ 1.4-1.8:1 RR (SPY 180-session + "
                                   "QuantConnect 2022 100-NASDAQ-stock backtests); 3-SD ~71%. "
                                   "SPY-DIRECTION proxy only — NOT our 0DTE option edge (C3/L58); "
                                   "replaced below with real OPRA fills (C1)."),
        "sources": SOURCES,
        "window": f"{START}..{END}",
        "n_signals": len(signals),
        "n_long_call": n_long,
        "n_short_put": n_short,
        "qty": QTY,
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS,
                 "exits": "v15 defaults"},
        "best_config": {
            "strike_offset": best["strike_offset"],
            "premium_stop_pct": best["premium_stop_pct"],
        },
        "best_cell_verify": {k: v for k, v in bv.items() if not k.startswith("_")},
        "all_cells": [
            {"strike_offset": c["strike_offset"], "premium_stop_pct": c["premium_stop_pct"],
             "n": c["n"], "no_opra_data": c["no_opra_data"],
             "overall_per_trade": c["verify"].get("overall_per_trade"),
             "oos_per_trade": c["verify"].get("oos_per_trade"),
             "positive_quarters": c["verify"].get("positive_quarters"),
             "top5_day_pct": c["verify"].get("top5_day_pct"),
             "drop_top5_per_trade": c["verify"].get("drop_top5_per_trade"),
             "wr": c["verify"].get("wr"),
             "clears_bar": c["clears_bar"]}
            for c in cells
        ],
        "clears_bar": any_clears,
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — supersedes any SPY-direction proxy",
            "per_trade": "expectancy (avg_pnl) reported per OP-14, NOT WR standalone",
            "is_oos": "IS=2025, OOS=2026-01..05-15",
            "concentration": "top5_day_pct + drop-top-5-days per-trade reported per OP-20 #5",
            "anti_cherry_pick": ("per anti-pattern 2.10, the bar requires OOS>0 + pos_q>=4/6 + "
                                 "top5<200% + n>=20 + drop-top5>0 simultaneously; a single thin/"
                                 "concentrated/OOS-negative positive cell does NOT clear it."),
            "spy_vs_option": "the published WR is a SPY-direction proxy; this run is the option-edge test (C3/L58).",
        },
        "best_cell_trades": best["_rows"],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== VWAP EXTENSION REVERSION — REAL-FILLS HUNT ===")
    print(f"signals={len(signals)}  (CALL={n_long}, PUT={n_short})")
    print(f"best cell: so={best['strike_offset']:+d} ps={best['premium_stop_pct']}  "
          f"n={bv.get('n')}  per_trade=${bv.get('overall_per_trade')}  OOS/trade=${bv.get('oos_per_trade')}")
    print(f"pos_q={bv.get('positive_quarters')}  top5={bv.get('top5_day_pct')}%  "
          f"drop-top5/trade=${bv.get('drop_top5_per_trade')}")
    print(f"CLEARS BAR: {any_clears}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    main()
