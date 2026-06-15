"""Real-fills validation for MOMENTUM_ACCELERATION_HIGHVOL watcher — VIX_FLOOR=25 variant.

Chef inbox item: 2026-05-20-momentum-accel-vix-floor-investigation.md
Variant A: raise VIX_HIGH_VOL_FLOOR from 20.0 → 25.0 to cut the VIX[20-25) drag band.

Also includes inline walk-forward split at 2025-09-30 (train) / 2026-01-01 (test)
to check OOS stability — satisfies the WF requirement without needing the stage-grinder
walk_forward_validate.py framework (which works on combo params, not watcher variants).

Output: analysis/recommendations/momentum-accel-vix25-validate.json
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
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "momentum-accel-vix25-validate.json"

# ── Variant parameters ─────────────────────────────────────────────────────────
VIX_HIGH_VOL_FLOOR = 25.0        # KEY CHANGE: was 20.0
QTY = 3
PREMIUM_STOP_PCT = -0.99          # chart-stop only per L51 analog
STRIKE_OFFSET = 0                 # ATM
ALIGNED_STACKS_BULL = ("BULL",)
ALIGNED_STACKS_BEAR = ("BEAR",)
COOLDOWN_MINUTES = 45
_CHART_STOP_OFFSET = 0.40
_LEVEL_STOP_BUFFER = 0.50
START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

# Walk-forward split
TRAIN_END   = dt.date(2025, 9, 30)   # train: Jan-Sep 2025
TEST_START  = dt.date(2026, 1, 1)    # test:  Jan-May 2026 (3+ month gap avoids look-ahead)

try:
    from crypto.lib.chart_patterns import Bar, momentum_acceleration as _detect_accel
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 20) -> list[Bar]:
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

    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index
    )
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_times_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]

    vix_vals: list[float] = []
    for ts in rth_times_naive:
        try:
            idx_vix = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_vals.append(float(vix_ser.iloc[idx_vix]) if idx_vix >= 0 else 17.0)
        except Exception:
            vix_vals.append(17.0)
    vix_arr = pd.Series(vix_vals, index=rth.index)

    log.info("Scanning with VIX_FLOOR=%.1f...", VIX_HIGH_VOL_FLOOR)
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 62:
            continue

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

        bias = hit.bias
        if bias == "bullish" and stack not in ALIGNED_STACKS_BULL:
            continue
        if bias == "bearish" and stack not in ALIGNED_STACKS_BEAR:
            continue

        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        last_signal_time = bar_time_naive
        direction = "long" if bias == "bullish" else "short"
        side = "C" if direction == "long" else "P"
        entry_spot = float(bar["close"])

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

    log.info("Found %d signals (VIX_FLOOR=%.1f). Running real-fills simulation...",
             len(signals), VIX_HIGH_VOL_FLOOR)

    results: list[dict] = []
    wins = losses = no_data = 0
    total_pnl = 0.0
    direction_counter: Counter = Counter()

    # Walk-forward accumulators
    wf_train_wins = wf_train_losses = 0
    wf_test_wins = wf_test_losses = 0
    wf_train_pnl = wf_test_pnl = 0.0

    for sig in signals:
        direction_counter[sig["direction"]] += 1
        bar_idx = sig["bar_idx"]
        entry_bar = sig["bar"]
        sig_date = dt.date.fromisoformat(sig["date"])

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=ribbon_df,
            rejection_level=sig["rejection_level"],
            triggers_fired=["MOMENTUM_ACCELERATION", "ALIGNED_REGIME", "HIGH_VOL_VIX_25"],
            side=sig["side"],
            qty=QTY,
            setup="MOMENTUM_ACCELERATION_HIGHVOL_V25",
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

        # Walk-forward bucketing
        in_train = sig_date >= START and sig_date <= TRAIN_END
        in_test  = sig_date >= TEST_START and sig_date <= END

        if in_train:
            if pnl > 0:
                wf_train_wins += 1
            else:
                wf_train_losses += 1
            wf_train_pnl += pnl
        elif in_test:
            if pnl > 0:
                wf_test_wins += 1
            else:
                wf_test_losses += 1
            wf_test_pnl += pnl

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
            "window": "train" if in_train else ("test" if in_test else "gap"),
        })

    completed = wins + losses
    wr_real = round(wins / completed, 3) if completed > 0 else 0.0
    scan_proxy_wr_v20 = 0.596  # original VIX>=20 scan proxy
    delta_pp = round((wr_real - scan_proxy_wr_v20) * 100, 1)

    wf_train_completed = wf_train_wins + wf_train_losses
    wf_test_completed  = wf_test_wins + wf_test_losses
    wf_train_wr = round(wf_train_wins / wf_train_completed, 3) if wf_train_completed > 0 else 0.0
    wf_test_wr  = round(wf_test_wins  / wf_test_completed,  3) if wf_test_completed  > 0 else 0.0

    # Walk-forward verdict
    if wf_test_completed < 5:
        wf_verdict = "INSUFFICIENT — N_test too thin for OOS verdict"
    elif wf_test_wr >= 0.55 and wf_test_pnl > 0:
        wf_verdict = "STABLE — OOS WR >= 55% and positive P&L"
    elif wf_test_wr >= 0.50 and wf_test_pnl > 0:
        wf_verdict = "MARGINAL — OOS WR >= 50% but low margin"
    elif wf_test_wr >= 0.50 and wf_test_pnl <= 0:
        wf_verdict = "FRAGILE — OOS WR >= 50% but negative P&L"
    else:
        wf_verdict = "DEGRADED — OOS WR < 50%"

    overall_verdict = (
        "POSITIVE_EXPECTANCY"
        if wr_real >= 0.50 and total_pnl > 0 and completed >= 10
        else (
            "MARGINAL" if wr_real >= 0.50 and completed >= 5
            else "INSUFFICIENT_N" if completed < 10
            else "NEGATIVE_EXPECTANCY"
        )
    )

    log.info("=== VIX=25 VARIANT SUMMARY ===")
    log.info("Signals: %d  Completed: %d  No-data: %d", len(signals), completed, no_data)
    log.info("WR: %.1f%%  (vs VIX>=20 scan proxy: %.1f%%  delta: %.1fpp)",
             wr_real * 100, scan_proxy_wr_v20 * 100, delta_pp)
    log.info("Total P&L: $%.0f  Per-trade avg: $%.0f",
             total_pnl, total_pnl / completed if completed else 0)
    log.info("Walk-forward TRAIN (Jan-Sep 2025): N=%d  WR=%.1f%%  P&L=$%.0f",
             wf_train_completed, wf_train_wr * 100, wf_train_pnl)
    log.info("Walk-forward TEST  (Jan-May 2026): N=%d  WR=%.1f%%  P&L=$%.0f",
             wf_test_completed, wf_test_wr * 100, wf_test_pnl)
    log.info("Walk-forward verdict: %s", wf_verdict)
    log.info("Overall verdict: %s", overall_verdict)

    summary = {
        "run_date": dt.date.today().isoformat(),
        "variant": "VIX_FLOOR_25",
        "vix_floor": VIX_HIGH_VOL_FLOOR,
        "window": f"{START} to {END}",
        "n_signals_found": len(signals),
        "n_completed": completed,
        "n_no_opra_data": no_data,
        "wins": wins,
        "losses": losses,
        "wr_real": wr_real,
        "scan_proxy_wr_v20": scan_proxy_wr_v20,
        "delta_pp_vs_v20_proxy": delta_pp,
        "total_dollar_pnl": round(total_pnl, 2),
        "avg_dollar_pnl_per_trade": round(total_pnl / completed, 2) if completed else 0,
        "by_direction": dict(direction_counter),
        "walk_forward": {
            "train_window": f"{START} to {TRAIN_END}",
            "test_window": f"{TEST_START} to {END}",
            "train_n": wf_train_completed,
            "train_wr": wf_train_wr,
            "train_pnl": round(wf_train_pnl, 2),
            "test_n": wf_test_completed,
            "test_wr": wf_test_wr,
            "test_pnl": round(wf_test_pnl, 2),
            "verdict": wf_verdict,
        },
        "overall_verdict": overall_verdict,
        "simulation_params": {
            "qty": QTY,
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_offset": _CHART_STOP_OFFSET,
            "vix_floor": VIX_HIGH_VOL_FLOOR,
        },
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote: %s", OUT_JSON)
    return summary


if __name__ == "__main__":
    result = scan_and_validate()
    print("\n=== VIX=25 VARIANT RESULT ===")
    print(f"Signals: {result['n_signals_found']}  Completed: {result['n_completed']}")
    print(f"WR: {result['wr_real']*100:.1f}%  Total P&L: ${result['total_dollar_pnl']:.0f}")
    wf = result["walk_forward"]
    print(f"WF TRAIN: N={wf['train_n']} WR={wf['train_wr']*100:.1f}% P&L=${wf['train_pnl']:.0f}")
    print(f"WF TEST:  N={wf['test_n']} WR={wf['test_wr']*100:.1f}% P&L=${wf['test_pnl']:.0f}")
    print(f"WF Verdict: {wf['verdict']}")
    print(f"Overall: {result['overall_verdict']}")
