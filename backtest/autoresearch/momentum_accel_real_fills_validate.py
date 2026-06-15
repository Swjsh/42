"""Real-fills validation for MOMENTUM_ACCELERATION_HIGHVOL watcher (OPRA simulation).

Scans the full 16-month window for momentum_accel+ALIGNED+HIGH_VOL signals, then
runs simulator_real.py on each to replace the SPY-price WR proxy with actual option P&L.

Per CLAUDE.md OP-20 disclosure 4: SPY-price scan WR != option P&L WR.
The momentum_accel watcher's WATCH_STABLE +6.6pp walk-forward result was computed on
SPY-price direction proxy. This script validates real option P&L.

Simulation parameters (watcher defaults from momentum_acceleration_highvol_watcher.py):
  - side:               "P" (put, bearish) or "C" (call, bullish) — per signal direction
  - qty:                3 contracts
  - strike_offset:      0 (ATM — watcher hasn't ratified a strike tier)
  - premium_stop_pct:   -0.99 (chart-stop only; L51 analog — initial accel bar can wick before the move)
  - rejection_level:    entry_spot + 0.10 (BULL) or entry_spot - 0.10 (BEAR)
      -> With LEVEL_STOP_BUFFER=0.50, this makes the chart stop fire at:
         BULL: spy_close < (entry_spot + 0.10) - 0.50 = entry_spot - 0.40
         BEAR: spy_close > (entry_spot - 0.10) + 0.50 = entry_spot + 0.40
         Matches _CHART_STOP_OFFSET = 0.40 in the watcher.

NOTE: this script skips NOT_NEAR_NAMED level filtering (Rank #1 combo doesn't require it).
The simplified scan: VIX >= 20 + ribbon ALIGNED + momentum_acceleration fires.

Output: analysis/recommendations/momentum-accel-highvol-real-fills.json
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
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "momentum-accel-highvol-real-fills.json"

# ── Watcher parameters ────────────────────────────────────────────────────────
VIX_HIGH_VOL_FLOOR = 20.0
QTY = 3
PREMIUM_STOP_PCT = -0.99      # chart-stop only per L51 analog
STRIKE_OFFSET = 0             # ATM
ALIGNED_STACKS_BULL = ("BULL",)
ALIGNED_STACKS_BEAR = ("BEAR",)
COOLDOWN_MINUTES = 45
_CHART_STOP_OFFSET = 0.40
_LEVEL_STOP_BUFFER = 0.50     # from simulator_real.py — constant
START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

try:
    from crypto.lib.chart_patterns import Bar, momentum_acceleration as _detect_accel
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 20) -> list[Bar]:
    """Build Bar list from the last `window` rows up to and including idx."""
    start = max(0, idx - window + 1)
    sub = rth.iloc[start: idx + 1]
    result = []
    for i, (_, row) in enumerate(sub.iterrows()):
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


def _ribbon_state(ribbon_df: pd.DataFrame, idx: int) -> RibbonState | None:
    if idx < 0 or idx >= len(ribbon_df):
        return None
    row = ribbon_df.iloc[idx]
    if str(row.get("stack", "WARMUP")) == "WARMUP" or pd.isna(row.get("fast", float("nan"))):
        return None
    return RibbonState(
        fast=float(row["fast"]),
        pivot=float(row["pivot"]),
        slow=float(row["slow"]),
        stack=str(row["stack"]),
        spread_cents=float(row["spread_cents"]),
    )


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

    ribbon_df = compute_ribbon(rth["close"])
    log.info("Ribbon computed. Aligning VIX...")

    # Align VIX — ffill on tz-naive timestamps (VIX index is tz-naive; RTH may be tz-aware)
    vix_full["timestamp_et"] = pd.to_datetime(vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]

    # Strip tz from RTH timestamps before lookup so both sides are tz-naive
    rth_times_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]

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
        if idx < 62:
            continue  # ribbon warmup

        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()

        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue

        vix_now = float(vix_arr.iloc[idx])
        if vix_now < VIX_HIGH_VOL_FLOOR:
            continue

        ribbon = _ribbon_state(ribbon_df, idx)
        if ribbon is None:
            continue
        stack = ribbon.stack

        bars = _make_bars(rth, idx)
        if len(bars) < 12:
            continue

        hit = _detect_accel(bars)
        if hit is None:
            continue

        bias = hit.bias  # "bullish" | "bearish"
        if bias == "bullish" and stack not in ALIGNED_STACKS_BULL:
            continue
        if bias == "bearish" and stack not in ALIGNED_STACKS_BEAR:
            continue

        # Cooldown
        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        last_signal_time = bar_time_naive
        direction = "long" if bias == "bullish" else "short"
        side = "C" if direction == "long" else "P"
        entry_spot = float(bar["close"])

        # rejection_level engineered so chart stop fires at exactly ±$0.40
        if direction == "long":
            rejection_level = entry_spot + _LEVEL_STOP_BUFFER - _CHART_STOP_OFFSET
        else:
            rejection_level = entry_spot - _LEVEL_STOP_BUFFER + _CHART_STOP_OFFSET

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "bar": bar,
            "direction": direction,
            "side": side,
            "entry_spot": entry_spot,
            "rejection_level": round(rejection_level, 2),
            "vix": round(vix_now, 1),
            "ribbon_stack": stack,
            "hit_confidence": round(hit.confidence, 3),
        })

    log.info("Found %d signals. Running real-fills simulation...", len(signals))

    results: list[dict] = []
    wins = 0
    losses = 0
    no_data = 0
    total_pnl = 0.0
    direction_counter: Counter = Counter()

    for sig in signals:
        direction_counter[sig["direction"]] += 1
        bar_idx = sig["bar_idx"]
        entry_bar = sig["bar"]

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=ribbon_df,
            rejection_level=sig["rejection_level"],
            triggers_fired=["MOMENTUM_ACCELERATION", "ALIGNED_REGIME", "HIGH_VOL_VIX"],
            side=sig["side"],
            qty=QTY,
            setup="MOMENTUM_ACCELERATION_HIGHVOL",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        if fill is None:
            results.append({
                "date": sig["date"], "time": sig["time"],
                "status": "NO_OPRA_DATA",
                "direction": sig["direction"], "vix": sig["vix"],
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
            "direction": sig["direction"],
            "side": sig["side"],
            "vix": sig["vix"],
            "ribbon_stack": sig["ribbon_stack"],
            "entry_spot": round(sig["entry_spot"], 2),
            "hit_confidence": sig["hit_confidence"],
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
    scan_proxy_wr = 0.596  # 16-month combo_search SPY-price WR

    delta_pp = round((wr_real - scan_proxy_wr) * 100, 1)
    verdict = (
        "FAVORABLE — real-fills WR within 10pp of scan proxy"
        if abs(delta_pp) <= 10.0
        else (
            "DEGRADED — real-fills WR significantly below scan proxy"
            if delta_pp < -10.0
            else "IMPROVED — real-fills WR above scan proxy (premium expands with momentum)"
        )
    )

    log.info("=== SUMMARY ===")
    log.info("Total signals: %d  Completed: %d  No-data: %d", len(signals), completed, no_data)
    log.info("Wins: %d  Losses: %d  WR: %.1f%%  (scan proxy: %.1f%%)",
             wins, losses, wr_real * 100, scan_proxy_wr * 100)
    log.info("Total P&L: $%.0f  Per-trade avg: $%.0f", total_pnl, total_pnl / completed if completed else 0)
    log.info("Verdict: %s (delta=%.1fpp)", verdict, delta_pp)

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
        "by_direction": dict(direction_counter),
        "verdict": verdict,
        "simulation_params": {
            "qty": QTY,
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_offset": _CHART_STOP_OFFSET,
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
