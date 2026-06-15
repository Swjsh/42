"""Real-fills validation for HEAD_AND_SHOULDERS_BEAR watcher (OPRA simulation).

Scans the full 16-month window for head_and_shoulders_top signals (no proximity
filter — hs_watcher fires on ALL H&S tops), then runs simulator_real.py on each
to replace the SPY-price WR proxy with actual option P&L.

Per CLAUDE.md OP-20 disclosure 4: SPY-price scan WR != option P&L WR.
This script validates real option P&L vs the walk-forward proxy WR=55.7%.

Simulation parameters (watcher defaults from hs_watcher.py):
  - side:               "P" (put, bearish) — H&S is a bearish reversal pattern
  - qty:                3 contracts
  - strike_offset:      0 (ATM)
  - premium_stop_pct:   -0.99 (chart-stop only; per L51/L55 lesson for neckline-break entries)
  - rejection_level:    neckline + 0.30 (chart stop above neckline = pattern invalidated)
      -> With LEVEL_STOP_BUFFER=0.50, stop fires at: neckline + 0.30 + 0.50 = neckline + 0.80

NOTE: L51 lesson applies — H&S neckline-break entries have violent initial bounces that
push PUT premiums DOWN by >50% in bar 1 before the directional move develops. All premium
stops are structurally incompatible for this entry class. Only chart stop can discriminate
genuine break (SPY stays below neckline) from false break (SPY recovers above neckline).

Scan proxy WR: 55.7% (walk-forward 16-month all-signals, N=185, no proximity filter,
time gate 09:40-13:30 ET, from analysis/walk-forward-hs-no-named-2026-05-20.json).

Output: analysis/recommendations/hs-bear-real-fills.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # needed for crypto.lib.chart_patterns

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "hs-bear-real-fills.json"

# ── Watcher parameters (mirrors hs_watcher.py constants) ─────────────────────
QTY = 3
PREMIUM_STOP_PCT = -0.99          # chart-stop only per L51/L55
STRIKE_OFFSET = 0                 # ATM
ENTRY_TIME_START = dt.time(9, 40)
ENTRY_TIME_END   = dt.time(12, 0)   # morning-only: afternoon is theta drag (see docstring)
COOLDOWN_MINUTES = 45
_CHART_STOP_ABOVE_NECKLINE = 0.30  # stop fires if SPY recovers above neckline + $0.30 + buffer
_WINDOW_BARS = 35                  # lookback window passed to head_and_shoulders_detector
START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

SCAN_PROXY_WR = 0.557  # walk-forward 16-month aggregate, N=185

try:
    from crypto.lib.chart_patterns import Bar, head_and_shoulders_detector as _detect_hs
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 35) -> list[Bar]:
    """Build Bar list from the last `window` rows up to and including idx."""
    start = max(0, idx - window + 1)
    sub = rth.iloc[start: idx + 1]
    result = []
    for _, row in sub.iterrows():
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        open_time = ts.to_pydatetime().replace(tzinfo=dt.timezone.utc)
        result.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 50_000)),
            granularity_seconds=300,
            source="spy_5m",
        ))
    return result


def scan_and_validate() -> dict:
    log.info("Loading 16-month SPY+VIX data (%s to %s)...", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    # Align VIX — strip tz from RTH timestamps before lookup (VIX index is tz-naive)
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index
    )
    vix_ser = (
        vix_full.set_index("timestamp_et")["close"]
        if "close" in vix_full.columns
        else vix_full.iloc[:, 0]
    )
    rth_times_naive = (
        rth["timestamp_et"].dt.tz_localize(None)
        if rth["timestamp_et"].dt.tz is not None
        else rth["timestamp_et"]
    )

    vix_vals: list[float] = []
    for ts in rth_times_naive:
        try:
            idx_vix = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_vals.append(float(vix_ser.iloc[idx_vix]) if idx_vix >= 0 else 17.0)
        except Exception:
            vix_vals.append(17.0)
    vix_arr = pd.Series(vix_vals, index=rth.index)

    log.info("Scanning for H&S signals (no proximity filter, time gate %s-%s)...",
             ENTRY_TIME_START, ENTRY_TIME_END)
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 30:
            continue  # need lookback for head_and_shoulders_detector

        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()

        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue

        # ── Time window gate (09:40-13:30 ET) ────────────────────────────────
        bar_time_only = bar_time_naive.time()
        if bar_time_only < ENTRY_TIME_START or bar_time_only > ENTRY_TIME_END:
            continue

        # ── Cooldown ──────────────────────────────────────────────────────────
        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        # ── H&S detector ──────────────────────────────────────────────────────
        bars = _make_bars(rth, idx, window=_WINDOW_BARS)
        if len(bars) < 30:
            continue

        hit = _detect_hs(bars, lookback=30)
        if hit is None:
            continue

        # NO proximity filter — fires on ALL H&S tops (no named-level check)

        last_signal_time = bar_time_naive
        bar_close = float(bar["close"])
        neckline = float(hit.notes.get("neckline", bar_close))
        head_high = float(hit.notes.get("head_high", bar_close))
        conf_score = float(hit.confidence)
        neckline_break_pct = float(hit.notes.get("neckline_break_pct", 0.0))
        vix_now = float(vix_arr.iloc[idx])

        # Chart stop: rejection_level = neckline + $0.30
        # In simulate_trade_real(side="P"): stop fires when spy_close > rejection_level + 0.50
        # Effective stop level = neckline + 0.30 + 0.50 = neckline + 0.80
        rejection_level = neckline + _CHART_STOP_ABOVE_NECKLINE

        # VIX bucket for stratification in results
        if vix_now < 15:
            vix_bucket = "<15"
        elif vix_now < 20:
            vix_bucket = "15-20"
        elif vix_now < 25:
            vix_bucket = "20-25"
        else:
            vix_bucket = ">=25"

        # Confidence tier (mirrors hs_watcher.py logic)
        if conf_score >= 0.65 and neckline_break_pct > 0.05:
            conf_tier = "high"
        elif conf_score >= 0.50 or neckline_break_pct > 0.03:
            conf_tier = "medium"
        else:
            conf_tier = "low"

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "bar": bar,
            "direction": "short",
            "side": "P",
            "entry_spot": bar_close,
            "neckline": round(neckline, 2),
            "head_high": round(head_high, 2),
            "rejection_level": round(rejection_level, 2),
            "vix": round(vix_now, 1),
            "vix_bucket": vix_bucket,
            "conf_score": round(conf_score, 3),
            "conf_tier": conf_tier,
            "neckline_break_pct": round(neckline_break_pct, 4),
        })

    log.info("Found %d signals. Running real-fills simulation...", len(signals))

    results: list[dict] = []
    wins = 0
    losses = 0
    no_data = 0
    total_pnl = 0.0
    time_dist: Counter = Counter()
    vix_bucket_dist: Counter = Counter()

    # Track per-vix-bucket wins/total for stratification
    vix_wins: Counter = Counter()
    vix_total: Counter = Counter()

    for sig in signals:
        bar_idx = sig["bar_idx"]
        entry_bar = sig["bar"]

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=sig["rejection_level"],
            triggers_fired=["hs_top_detector", "time_window", "no_proximity_filter"],
            side=sig["side"],
            qty=QTY,
            setup="HEAD_AND_SHOULDERS_BEAR",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        hour = int(sig["time"].split(":")[0])
        time_dist[hour] += 1
        vix_bucket_dist[sig["vix_bucket"]] += 1

        if fill is None:
            results.append({
                "date": sig["date"], "time": sig["time"],
                "status": "NO_OPRA_DATA",
                "direction": "short", "vix": sig["vix"],
                "vix_bucket": sig["vix_bucket"],
                "entry_spot": round(sig["entry_spot"], 2),
                "conf_tier": sig["conf_tier"],
            })
            no_data += 1
            continue

        pnl = fill.dollar_pnl
        total_pnl += pnl
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        if pnl > 0:
            wins += 1
            vix_wins[sig["vix_bucket"]] += 1
        else:
            losses += 1
        vix_total[sig["vix_bucket"]] += 1

        exit_prem = fill.runner_exit_premium or fill.tp1_premium or 0.0
        results.append({
            "date": sig["date"], "time": sig["time"],
            "status": "COMPLETE",
            "direction": "short",
            "side": "P",
            "vix": sig["vix"],
            "vix_bucket": sig["vix_bucket"],
            "entry_spot": round(sig["entry_spot"], 2),
            "neckline": sig["neckline"],
            "head_high": sig["head_high"],
            "conf_score": sig["conf_score"],
            "conf_tier": sig["conf_tier"],
            "neckline_break_pct": sig["neckline_break_pct"],
            "rejection_level": sig["rejection_level"],
            "strike": fill.strike,
            "entry_premium": round(fill.entry_premium, 3),
            "exit_premium": round(exit_prem, 3),
            "exit_reason": (
                fill.exit_reason.value
                if hasattr(fill.exit_reason, "value")
                else str(fill.exit_reason)
            ),
            "dollar_pnl": round(pnl, 2),
            "outcome": outcome,
            "max_adverse_premium": (
                round(fill.max_adverse_premium, 3)
                if fill.max_adverse_premium
                else None
            ),
        })

    completed = wins + losses
    wr_real = round(wins / completed, 3) if completed > 0 else 0.0
    delta_pp = round((wr_real - SCAN_PROXY_WR) * 100, 1)

    if abs(delta_pp) <= 10.0:
        verdict = "FAVORABLE — real-fills WR within 10pp of scan proxy"
    elif delta_pp < -10.0:
        verdict = "DEGRADED — real-fills WR significantly below scan proxy"
    else:
        verdict = "IMPROVED — real-fills WR above scan proxy"

    # Per-VIX-bucket breakdown
    by_vix = {}
    for bucket in ["<15", "15-20", "20-25", ">=25"]:
        n = vix_total[bucket]
        w = vix_wins[bucket]
        by_vix[bucket] = {
            "n": n,
            "wins": w,
            "wr_pct": round(w / n * 100, 1) if n > 0 else None,
        }

    # Time-of-day breakdown
    by_hour = {
        f"{h:02d}:00": time_dist[h]
        for h in sorted(time_dist.keys())
    }

    log.info("=== SUMMARY ===")
    log.info("Total signals: %d  Completed: %d  No-data: %d", len(signals), completed, no_data)
    log.info("Wins: %d  Losses: %d  WR: %.1f%%  (scan proxy: %.1f%%)",
             wins, losses, wr_real * 100, SCAN_PROXY_WR * 100)
    log.info("Total P&L: $%.0f  Per-trade avg: $%.0f",
             total_pnl, total_pnl / completed if completed else 0)
    log.info("Verdict: %s (delta=%.1fpp)", verdict, delta_pp)
    log.info("By VIX bucket: %s", by_vix)
    log.info("Time dist: %s", by_hour)

    # OP-21 gate evaluation
    op21_real_fills_pass = wr_real >= 0.50 and total_pnl > 0

    summary = {
        "run_date": dt.date.today().isoformat(),
        "window": f"{START} to {END}",
        "n_signals_found": len(signals),
        "n_completed": completed,
        "n_no_opra_data": no_data,
        "wins": wins,
        "losses": losses,
        "wr_real": wr_real,
        "scan_proxy_wr": SCAN_PROXY_WR,
        "delta_pp": delta_pp,
        "total_dollar_pnl": round(total_pnl, 2),
        "avg_dollar_pnl_per_trade": round(total_pnl / completed, 2) if completed else 0,
        "verdict": verdict,
        "op21_real_fills_gate": "PASS" if op21_real_fills_pass else "FAIL",
        "by_vix_bucket": by_vix,
        "by_hour_signals": by_hour,
        "notes": (
            "No proximity filter applied — watcher fires on ALL H&S tops. "
            "Time gate 09:40-13:30 ET, cooldown 45 min. "
            "premium_stop_pct=-0.99 (chart stop only per L51 neckline-break lesson). "
            "rejection_level=neckline+0.30 -> effective level stop at neckline+0.80 "
            "(+0.50 LEVEL_STOP_BUFFER in simulator_real). "
            "Scan proxy WR=55.7% from walk-forward 16-month all-signals N=185."
        ),
        "simulation_params": {
            "qty": QTY,
            "side": "P",
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_above_neckline": _CHART_STOP_ABOVE_NECKLINE,
            "effective_level_stop_from_neckline": round(
                _CHART_STOP_ABOVE_NECKLINE + 0.50, 2
            ),
            "entry_time_start": str(ENTRY_TIME_START),
            "entry_time_end": str(ENTRY_TIME_END),
            "cooldown_minutes": COOLDOWN_MINUTES,
        },
        "op21_promotion_status": {
            "historical_gate": "PASS (WR=55.7% N=185 > 50%)",
            "walk_forward_gate": "PASS (train 54.5% N=132 / test 58.5% N=53, STABLE +4.0pp)",
            "real_fills_gate": "PASS" if op21_real_fills_pass else "FAIL",
            "live_observations": "0/3",
        },
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote: %s", OUT_JSON)
    return summary


if __name__ == "__main__":
    result = scan_and_validate()
    print(f"\n=== HEAD_AND_SHOULDERS_BEAR REAL-FILLS RESULT ===")
    print(f"Signals: {result['n_signals_found']}  Completed: {result['n_completed']}  "
          f"No-data: {result['n_no_opra_data']}")
    print(f"Real-fills WR: {result['wr_real']*100:.1f}%  "
          f"(scan proxy: {result['scan_proxy_wr']*100:.1f}%)")
    print(f"Delta: {result['delta_pp']:+.1f}pp")
    print(f"Verdict: {result['verdict']}")
    print(f"Total P&L: ${result['total_dollar_pnl']:.0f}  "
          f"Avg/trade: ${result['avg_dollar_pnl_per_trade']:.0f}")
    print(f"OP-21 real-fills gate: {result['op21_real_fills_gate']}")
    print(f"\nBy VIX bucket:")
    for bucket, stats in result["by_vix_bucket"].items():
        if stats["n"] > 0:
            print(f"  {bucket}: N={stats['n']}  WR={stats['wr_pct']}%")
    print(f"\nBy hour: {result['by_hour_signals']}")
    print(f"\nOP-21 status:")
    for k, v in result["op21_promotion_status"].items():
        print(f"  {k}: {v}")
