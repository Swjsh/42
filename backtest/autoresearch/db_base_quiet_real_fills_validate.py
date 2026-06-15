"""Real-fills validation for DOUBLE_BOTTOM_BASE_QUIET watcher (OPRA simulation).

Scans the full 16-month window for double_bottom+conf<0.60+VIX<20 signals (no MORNING
filter — watcher fires all RTH hours), then runs simulator_real.py on each to replace
the SPY-price WR proxy with actual option P&L.

Per CLAUDE.md OP-20 disclosure 4: SPY-price scan WR != option P&L WR.
This script validates real option P&L vs the combo_search WR=59.5% proxy.

Simulation parameters (watcher defaults from double_bottom_base_quiet_watcher.py):
  - side:               "C" (call, bullish) — double bottom is bullish only
  - qty:                3 contracts
  - strike_offset:      0 (ATM)
  - premium_stop_pct:   -0.99 (chart-stop only; L55 analog)
  - rejection_level:    neckline - 0.30 (chart stop below neckline invalidation)
      -> With LEVEL_STOP_BUFFER=0.50, stop fires at: neckline - 0.30 - 0.50 = neckline - 0.80

NOTE: this script SKIPS the NOT_NEAR_NAMED proximity filter (requires full BarContext +
level detection pipeline; the Rank #3 combo uses this filter, but this simplified scan
gives a lower-bound WR estimate). The proximity filter would improve WR if included.

Scan proxy WR: 59.5% (16-month combo: double_bottom|NOT_NEAR_NAMED|conf=LOW|vix=LOW_VOL,
N=168, 2025-01-01 to 2026-05-15). This scan (without NOT_NEAR_NAMED, full RTH hours)
may produce more signals.

Output: analysis/recommendations/db-base-quiet-real-fills.json
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

OUT_JSON = ROOT / "analysis" / "recommendations" / "db-base-quiet-real-fills.json"

# ── Watcher parameters ────────────────────────────────────────────────────────
VIX_LOW_VOL_CEILING = 20.0
CONFIDENCE_LOW_CEILING = 0.60     # conf < 0.60 is the BASE_QUIET gate
QTY = 3
PREMIUM_STOP_PCT = -0.99          # chart-stop only per L55 analog
STRIKE_OFFSET = 0                 # ATM
RTH_START = dt.time(9, 35)
RTH_END   = dt.time(15, 55)       # full RTH (no morning restriction)
COOLDOWN_MINUTES = 30
_CHART_STOP_BELOW_NECKLINE = 0.30  # chart stop = neckline - $0.30
_LEVEL_STOP_BUFFER = 0.50          # from simulator_real.py — constant
START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

try:
    from crypto.lib.chart_patterns import Bar, double_bottom_detector as _detect_db
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 30) -> list[Bar]:
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
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
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

    log.info("Scanning for signals...")
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 30:
            continue  # need lookback for double_bottom_detector

        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()

        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue

        # ── RTH window gate (09:35-15:55, full day — no morning restriction) ──
        bar_time_only = bar_time_naive.time()
        if bar_time_only < RTH_START or bar_time_only > RTH_END:
            continue

        # ── VIX LOW_VOL gate (< 20) ──────────────────────────────────────────
        vix_now = float(vix_arr.iloc[idx])
        if vix_now >= VIX_LOW_VOL_CEILING:
            continue

        # ── Cooldown ──────────────────────────────────────────────────────────
        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        # ── Double bottom detector ────────────────────────────────────────────
        bars = _make_bars(rth, idx)
        if len(bars) < 10:
            continue

        hit = _detect_db(bars)
        if hit is None:
            continue

        # ── Confidence ceiling: conf=LOW only (< 0.60) ───────────────────────
        if hit.confidence >= CONFIDENCE_LOW_CEILING:
            continue

        last_signal_time = bar_time_naive
        entry_spot = float(bar["close"])
        neckline = hit.notes.get("neckline", entry_spot)

        # rejection_level set so chart stop fires at neckline - $0.80
        # (stop = neckline - $0.30 - LEVEL_STOP_BUFFER $0.50)
        rejection_level = float(neckline) - _CHART_STOP_BELOW_NECKLINE

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "bar": bar,
            "direction": "long",
            "side": "C",
            "entry_spot": entry_spot,
            "neckline": round(float(neckline), 2),
            "rejection_level": round(rejection_level, 2),
            "vix": round(vix_now, 1),
            "hit_confidence": round(hit.confidence, 3),
            "v2_factors": hit.notes.get("v2_factors_active", []),
        })

    log.info("Found %d signals. Running real-fills simulation...", len(signals))

    results: list[dict] = []
    wins = 0
    losses = 0
    no_data = 0
    total_pnl = 0.0
    time_dist: Counter = Counter()  # count by hour

    for sig in signals:
        bar_idx = sig["bar_idx"]
        entry_bar = sig["bar"]

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=sig["rejection_level"],
            triggers_fired=["double_bottom_detector", "rth_window", "low_vol_vix", "conf_low_gate"],
            side=sig["side"],
            qty=QTY,
            setup="DOUBLE_BOTTOM_BASE_QUIET",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        # Track time-of-day distribution
        hour = int(sig["time"].split(":")[0])
        time_dist[hour] += 1

        if fill is None:
            results.append({
                "date": sig["date"], "time": sig["time"],
                "status": "NO_OPRA_DATA",
                "direction": "long", "vix": sig["vix"],
                "entry_spot": sig["entry_spot"],
                "hit_confidence": sig["hit_confidence"],
            })
            no_data += 1
            continue

        pnl = fill.dollar_pnl
        total_pnl += pnl
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        if pnl > 0:
            wins += 1
        else:
            losses += 1

        exit_prem = fill.runner_exit_premium or fill.tp1_premium or 0.0
        results.append({
            "date": sig["date"], "time": sig["time"],
            "status": "COMPLETE",
            "direction": "long",
            "side": "C",
            "vix": sig["vix"],
            "entry_spot": round(sig["entry_spot"], 2),
            "neckline": sig["neckline"],
            "hit_confidence": sig["hit_confidence"],
            "v2_factors": sig["v2_factors"],
            "rejection_level": sig["rejection_level"],
            "strike": fill.strike,
            "entry_premium": round(fill.entry_premium, 3),
            "exit_premium": round(exit_prem, 3),
            "exit_reason": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
            "dollar_pnl": round(pnl, 2),
            "outcome": outcome,
            "max_adverse_premium": round(fill.max_adverse_premium, 3) if fill.max_adverse_premium else None,
        })

    completed = wins + losses
    wr_real = round(wins / completed, 3) if completed > 0 else 0.0
    scan_proxy_wr = 0.595  # 16-month combo WR (includes NOT_NEAR_NAMED + conf=LOW)

    delta_pp = round((wr_real - scan_proxy_wr) * 100, 1)
    verdict = (
        "FAVORABLE — real-fills WR within 10pp of scan proxy"
        if abs(delta_pp) <= 10.0
        else (
            "DEGRADED — real-fills WR significantly below scan proxy"
            if delta_pp < -10.0
            else "IMPROVED — real-fills WR above scan proxy"
        )
    )

    # Time-of-day breakdown
    by_hour = {
        f"{h:02d}:00": time_dist[h]
        for h in sorted(time_dist.keys())
    }

    log.info("=== SUMMARY ===")
    log.info("Total signals: %d  Completed: %d  No-data: %d", len(signals), completed, no_data)
    log.info("Wins: %d  Losses: %d  WR: %.1f%%  (scan proxy: %.1f%%)",
             wins, losses, wr_real * 100, scan_proxy_wr * 100)
    log.info("Total P&L: $%.0f  Per-trade avg: $%.0f", total_pnl, total_pnl / completed if completed else 0)
    log.info("Verdict: %s (delta=%.1fpp)", verdict, delta_pp)
    log.info("Time dist: %s", by_hour)

    summary = {
        "run_date": dt.date.today().isoformat(),
        "window": f"{START} to {END}",
        "n_signals_found": len(signals),
        "n_completed": completed,
        "n_no_opra_data": no_data,
        "wins": wins,
        "losses": losses,
        "wr_real": wr_real,
        "scan_proxy_wr": scan_proxy_wr,
        "delta_pp": delta_pp,
        "total_dollar_pnl": round(total_pnl, 2),
        "avg_dollar_pnl_per_trade": round(total_pnl / completed, 2) if completed else 0,
        "verdict": verdict,
        "by_hour_signals": by_hour,
        "notes": (
            "Simplified scan — NOT_NEAR_NAMED filter omitted (requires full BarContext). "
            "Confidence ceiling <0.60 applied (core BASE_QUIET discriminator). "
            "No morning window restriction — full RTH 09:35-15:55 ET. "
            "Scan proxy WR=59.5% includes both NOT_NEAR_NAMED and conf=LOW filters."
        ),
        "simulation_params": {
            "qty": QTY,
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_below_neckline": _CHART_STOP_BELOW_NECKLINE,
            "effective_chart_stop_from_neckline": round(_CHART_STOP_BELOW_NECKLINE + _LEVEL_STOP_BUFFER, 2),
            "confidence_ceiling": CONFIDENCE_LOW_CEILING,
            "vix_ceiling": VIX_LOW_VOL_CEILING,
        },
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote: %s", OUT_JSON)
    return summary


if __name__ == "__main__":
    result = scan_and_validate()
    print(f"\n=== RESULT ===")
    print(f"Signals: {result['n_signals_found']}  Completed: {result['n_completed']}")
    print(f"Real-fills WR: {result['wr_real']*100:.1f}%  (scan proxy: {result['scan_proxy_wr']*100:.1f}%)")
    print(f"Verdict: {result['verdict']}")
    print(f"Total P&L: ${result['total_dollar_pnl']:.0f}")
    print(f"By hour: {result['by_hour_signals']}")
