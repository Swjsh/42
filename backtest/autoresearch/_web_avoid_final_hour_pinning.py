"""WEB-LEARN: avoid_final_hour_pinning_compression_long.

HYPOTHESIS (web-sourced): On non-expiration-Friday SPY 0DTE, the 15:00-16:00 ET window
shows dealer-hedging-driven realized-move COMPRESSION / pinning toward heavy strikes that
suppresses the sustained directional follow-through a long-premium buyer needs. So any
vwap_continuation entry surviving into / initiated in the final hour underperforms --
reinforcing an earlier entry cutoff + the existing 15:50 flatten.

WHAT IS TESTABLE on OUR data (the binding constraint):
  PART A -- REALIZED COMPRESSION (fully testable, full SPY window 2025-01..2026-06-18):
    Measure SPY 5m realized range per session window:
      OPEN   09:30-10:30   (the live vwap_continuation entry window)
      MIDDAY 11:00-14:00
      FINAL  15:00-16:00   (the pinning-suspect window)
    Normalize each window's summed |bar move| / range by ATR so cross-day comparable.
    Split by day-type: non-OPEX-Friday vs OPEX-Friday vs non-Friday. The claim predicts
    FINAL << OPEN realized move, MORE so on non-OPEX-Fri.

  PART B -- LATE-ENTRY OPTION P&L (testable, real OPRA fills, HARD-WINDOW <=2026-05-29):
    The LIVE vwap_continuation detector has ENTRY_CUTOFF=10:30, so by construction it NEVER
    enters in the final hour -- the "entry initiated in the final hour" clause is already
    answered (it cannot happen live). To still TEST the claim we RELAX the cutoff to 16:00
    and split the resulting entries into MORNING (<=10:30, the live pop) vs AFTERNOON
    (>13:00) vs FINAL-HOUR (>=15:00), comparing per-trade expectancy on REAL fills. If the
    claim holds, FINAL-HOUR entries underperform MORNING.

  WHAT WE CANNOT DO (flag honestly): attribute any compression to dealer gamma / pinning /
    heavy-strike positioning -- we have NO real-time GEX / dealer-positioning feed (only a
    1-day archive). PART A measures the realized-compression EFFECT; the gamma ATTRIBUTION
    is UNVERIFIABLE on our data.

BAR: this is NOT a new entry signal (the live edge is morning-only already). It is an
EXIT/MANAGEMENT / entry-cutoff confirmation. Apply the management bar: an earlier cutoff /
final-hour avoidance only "wins" if it does NOT cost the live edge expectancy AND the
final-hour pop is demonstrably worse (expectancy + risk-adjusted, L175).

Pure Python, $0. No live orders. Writes
analysis/recommendations/_web_avoid_final_hour_pinning.json + console scorecard.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_web_avoid_final_hour_pinning.py
"""
from __future__ import annotations

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

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    session_vwap_asof,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "_web_avoid_final_hour_pinning.json"

# Detector params (IDENTICAL to live vwap_continuation, except the cutoff we RELAX for PART B)
TREND_BARS = 3
SHALLOW_DIP_TOL = 0.0010
LIVE_CUTOFF = dt.time(10, 30)        # the LIVE entry cutoff
RELAXED_CUTOFF = dt.time(16, 0)      # PART B: relax to test late entries
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = 2026
OPRA_HARD_WINDOW = dt.date(2026, 5, 29)  # cache blind spot -- assert + drop after

# Window definitions for PART A (realized compression)
WIN_OPEN = (dt.time(9, 30), dt.time(10, 30))
WIN_MID = (dt.time(11, 0), dt.time(14, 0))
WIN_FINAL = (dt.time(15, 0), dt.time(16, 0))

# Entry-time buckets for PART B
def _entry_bucket(t: dt.time) -> str:
    if t <= dt.time(10, 30):
        return "MORNING_<=1030"
    if t < dt.time(13, 0):
        return "MIDDAY_1030-1300"
    if t < dt.time(15, 0):
        return "AFTERNOON_1300-1500"
    return "FINAL_HOUR_>=1500"


# ── helpers reused from edgehunt ──────────────────────────────────────────────
def _normalize_spy(spy_raw: pd.DataFrame) -> pd.DataFrame:
    df = spy_raw.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["minute"] = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


def _align_vix(spy_df: pd.DataFrame, vix_raw: pd.DataFrame) -> pd.Series:
    spy_ts = pd.to_datetime(spy_df["timestamp_et"]).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    vix_ts = pd.to_datetime(vix_raw["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_raw["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned.fillna(0.0)


def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


# ── OPEX-Friday detection: 3rd Friday of the month is monthly OPEX ────────────
def _is_friday(d: dt.date) -> bool:
    return d.weekday() == 4


def _is_opex_friday(d: dt.date) -> bool:
    """Monthly OPEX = 3rd Friday. (Weekly Fri also expire 0DTE SPY, but monthly is the
    heavy-OI / gamma-pin day the literature points at.)"""
    if d.weekday() != 4:
        return False
    return 15 <= d.day <= 21  # 3rd Friday always falls in [15,21]


def _daytype(d: dt.date) -> str:
    if not _is_friday(d):
        return "non_friday"
    return "opex_friday" if _is_opex_friday(d) else "non_opex_friday"


# ─────────────────────────────────────────────────────────────────────────────
# PART A -- REALIZED COMPRESSION (full SPY window, no options needed)
# ─────────────────────────────────────────────────────────────────────────────
def _window_realized(rth: pd.DataFrame, lo: dt.time, hi: dt.time) -> Optional[dict]:
    w = rth[(rth["t"] >= lo) & (rth["t"] < hi)]
    if len(w) < 3:
        return None
    rng = float(w["high"].max() - w["low"].min())            # window high-low range
    sum_abs = float(np.abs(w["close"].diff().dropna()).sum())  # path realized move
    return {"range": rng, "sum_abs": sum_abs, "n_bars": len(w)}


def part_a_realized_compression(days: list[DayCtx]) -> dict:
    """Per-day window realized range/path, ATR-normalized, split by day-type."""
    # full-session ATR proxy per day = mean 5m true-range over RTH (for normalization)
    per_day = []
    for dc in days:
        rth = dc.rth
        d = dc.date
        # ATR proxy: mean of (high-low) over RTH bars
        atr = float((rth["high"] - rth["low"]).mean())
        if atr <= 0:
            continue
        o = _window_realized(rth, *WIN_OPEN)
        m = _window_realized(rth, *WIN_MID)
        f = _window_realized(rth, *WIN_FINAL)
        if not (o and f):
            continue
        per_day.append({
            "date": str(d),
            "daytype": _daytype(d),
            "atr": atr,
            "open_range_atr": o["range"] / atr,
            "mid_range_atr": (m["range"] / atr) if m else None,
            "final_range_atr": f["range"] / atr,
            "open_path_atr": o["sum_abs"] / atr,
            "final_path_atr": f["sum_abs"] / atr,
            "final_over_open_range": f["range"] / o["range"] if o["range"] > 0 else None,
            "final_over_open_path": f["sum_abs"] / o["sum_abs"] if o["sum_abs"] > 0 else None,
        })

    def _agg(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        def med(key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return round(float(np.median(vals)), 4) if vals else None
        def mean(key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return round(float(np.mean(vals)), 4) if vals else None
        return {
            "n": len(rows),
            "open_range_atr_med": med("open_range_atr"),
            "final_range_atr_med": med("final_range_atr"),
            "open_path_atr_med": med("open_path_atr"),
            "final_path_atr_med": med("final_path_atr"),
            "final_over_open_range_med": med("final_over_open_range"),
            "final_over_open_range_mean": mean("final_over_open_range"),
            "final_over_open_path_med": med("final_over_open_path"),
            "pct_days_final_lt_open_range": round(
                100 * np.mean([1.0 if (r["final_range_atr"] < r["open_range_atr"]) else 0.0
                               for r in rows]), 1),
        }

    by_type = {dt_: _agg([r for r in per_day if r["daytype"] == dt_])
               for dt_ in ("non_friday", "non_opex_friday", "opex_friday")}
    overall = _agg(per_day)
    return {"overall": overall, "by_daytype": by_type, "n_days": len(per_day)}


# ─────────────────────────────────────────────────────────────────────────────
# PART B -- LATE-ENTRY OPTION P&L (relaxed-cutoff detector + real fills)
# ─────────────────────────────────────────────────────────────────────────────
def detect_signals_relaxed(days: list[DayCtx], cutoff: dt.time) -> list[Signal]:
    """vwap_continuation detector, cutoff relaxed. One entry/day, causal."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > cutoff:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if trig is None:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jvwap_{trig}", ))
            break
    return out


@dataclass
class TradeRow:
    date: str
    side: str
    entry_time: str
    bucket: str
    pnl: float
    pct: float
    exit_reason: str


def simulate(signals, spy, ribbon, vix, *, strike_offset=-2, premium_stop_pct=-0.08):
    """Live config: ITM-2 (-2 offset), -8% stop (the LIVE vwap_continuation params)."""
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = n_post_window = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        if d > OPRA_HARD_WINDOW:            # HARD-WINDOW assert: no fills cached after
            n_post_window += 1
            continue
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="JVWAP_LATEHOUR", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        et = bar["timestamp_et"].time()
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, entry_time=et.strftime("%H:%M"),
            bucket=_entry_bucket(et),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none, "post_hard_window_dropped": n_post_window,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def _bucket_metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    wins = int((pnl > 0).sum())
    daily = defaultdict(float)
    for r in rows:
        daily[r.date] += r.pnl
    return {
        "n": len(rows),
        "wr_pct": round(100 * wins / len(rows), 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "median_pnl": round(float(np.median(pnl)), 2),
        "exit_hist": dict(sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())),
    }


def main() -> int:
    print("[final-hour] loading SPY+VIX ...", flush=True)
    # Full window for PART A; load_data goes to the cache edge for PART B.
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 16))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    print(f"[final-hour] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # ── PART A ────────────────────────────────────────────────────────────────
    print("[final-hour] PART A: realized compression by window x daytype ...", flush=True)
    part_a = part_a_realized_compression(days)
    ov = part_a["overall"]
    print(f"  OVERALL n={ov['n']}: open_range_atr_med={ov['open_range_atr_med']} "
          f"final_range_atr_med={ov['final_range_atr_med']} "
          f"final/open_range_med={ov['final_over_open_range_med']} "
          f"%days final<open={ov['pct_days_final_lt_open_range']}", flush=True)
    for k, a in part_a["by_daytype"].items():
        if a.get("n"):
            print(f"  {k:>16}: n={a['n']} open={a['open_range_atr_med']} "
                  f"final={a['final_range_atr_med']} ratio={a['final_over_open_range_med']} "
                  f"%final<open={a['pct_days_final_lt_open_range']}", flush=True)

    # ── PART B ────────────────────────────────────────────────────────────────
    print("[final-hour] PART B: late-entry option P&L (real fills, hard-window) ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    sig_live = detect_signals_relaxed(days, LIVE_CUTOFF)
    sig_relaxed = detect_signals_relaxed(days, RELAXED_CUTOFF)
    print(f"  signals: live_cutoff(<=10:30)={len(sig_live)}  relaxed_cutoff(<=16:00)={len(sig_relaxed)}",
          flush=True)

    rows, cov = simulate(sig_relaxed, spy, ribbon, vix)
    print(f"  coverage: {cov}", flush=True)

    by_bucket = {}
    for b in ("MORNING_<=1030", "MIDDAY_1030-1300", "AFTERNOON_1300-1500", "FINAL_HOUR_>=1500"):
        br = [r for r in rows if r.bucket == b]
        by_bucket[b] = _bucket_metrics(br)
        m = by_bucket[b]
        if m["n"]:
            print(f"  {b:>20}: n={m['n']} exp=${m['exp_dollar']} wr={m['wr_pct']}% "
                  f"total=${m['total_dollar']} med=${m['median_pnl']}", flush=True)
        else:
            print(f"  {b:>20}: n=0 (no entries in this bucket)", flush=True)

    overall_b = _bucket_metrics(rows)

    # ── VERDICT ───────────────────────────────────────────────────────────────
    morning = by_bucket.get("MORNING_<=1030", {})
    finalh = by_bucket.get("FINAL_HOUR_>=1500", {})
    a_overall = part_a["overall"]
    compression_confirmed = (a_overall.get("final_over_open_range_med") is not None
                             and a_overall["final_over_open_range_med"] < 1.0
                             and a_overall["pct_days_final_lt_open_range"] > 55)
    # final-hour-underperf only judgeable if we have entries there
    if finalh.get("n", 0) >= 5 and morning.get("n", 0) >= 5:
        late_underperf = finalh["exp_dollar"] < morning["exp_dollar"]
        late_judgeable = True
    else:
        late_underperf = None
        late_judgeable = False

    summary = {
        "slug": "avoid_final_hour_pinning_compression_long",
        "run_date": dt.date.today().isoformat(),
        "kind": "exit_management / entry_cutoff_confirmation (NOT a new entry signal)",
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "hard_window_opra": str(OPRA_HARD_WINDOW),
        "claim": ("Final hour (15:00-16:00) realized-move compression / pinning suppresses "
                  "directional follow-through -> long-premium late entries underperform; "
                  "reinforce earlier cutoff + 15:50 flatten."),
        "testability": {
            "part_a_realized_compression": "TESTABLE on full SPY 5m window",
            "part_b_late_entry_pnl": "TESTABLE on real OPRA fills <= 2026-05-29 (hard-window)",
            "gamma_pinning_attribution": ("UNVERIFIABLE -- no real-time GEX / dealer feed "
                                          "(only 1-day archive). PART A measures the realized "
                                          "EFFECT, not its cause."),
        },
        "part_a_realized_compression": part_a,
        "part_b_late_entry_pnl": {
            "config": "LIVE vwap_continuation params: ITM-2 (offset -2), -8% premium stop, qty 3",
            "live_cutoff_signals": len(sig_live),
            "relaxed_cutoff_signals": len(sig_relaxed),
            "coverage": cov,
            "by_entry_bucket": by_bucket,
            "overall": overall_b,
        },
        "verdict": {
            "realized_compression_confirmed": bool(compression_confirmed),
            "late_entry_underperforms_judgeable": late_judgeable,
            "late_entry_underperforms": late_underperf,
            "live_edge_is_morning_only": ("vwap_continuation ENTRY_CUTOFF=10:30 -> the live edge "
                                          "NEVER enters in the final hour; the 'entry initiated "
                                          "in final hour' clause cannot occur live."),
        },
        "DISCLOSURE": {
            "no_new_signal": "live edge is morning-only by construction; this is a cutoff confirm",
            "fills_authority": "real OPRA via simulator_real (C1); causal next-bar entry",
            "gamma_caveat": "pinning cause unverifiable on our data (no GEX feed)",
            "opex_definition": "monthly OPEX = 3rd Friday (day in [15,21]); weekly Fri also 0DTE",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[final-hour] wrote {OUT}", flush=True)

    print("\n=== FINAL-HOUR PINNING/COMPRESSION VERDICT ===")
    print(f"PART A realized compression confirmed: {compression_confirmed} "
          f"(final/open range med={a_overall.get('final_over_open_range_med')}, "
          f"%days final<open={a_overall.get('pct_days_final_lt_open_range')})")
    if late_judgeable:
        print(f"PART B late-entry underperforms morning: {late_underperf} "
              f"(morning exp=${morning['exp_dollar']} n={morning['n']} vs "
              f"final-hour exp=${finalh['exp_dollar']} n={finalh['n']})")
    else:
        print(f"PART B late-entry: NOT JUDGEABLE -- too few final-hour entries "
              f"(final_hour n={finalh.get('n',0)}, morning n={morning.get('n',0)}). "
              f"The detector + 10:30 cutoff already produce ~no final-hour entries.")
    print("Gamma/pinning attribution: UNVERIFIABLE (no GEX feed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
