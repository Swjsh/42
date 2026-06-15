"""Real-fills + walk-forward validation for failed_breakdown_wick conf=MID | MORNING.

16-month combo search found this as best FBW combo:
  detector:   failed_breakdown_wick
  conf_band:  MID (confidence in [0.65, 0.80))
  time_band:  MORNING (09:30-11:30 ET)
  vix_band:   ANY
  N=52, WR=59.62%, 14 months active, max_month_share=13.5%
  score=0.93 (#8 in 16-month leaderboard)

OP-20 mandatory gates before watcher authoring:
  1. Account assumption (qty=3, ~$300 exposure at ATM)
  2. Sample bias disclosure (16-month in-sample)
  3. Walk-forward OOS result
  4. Real-fills (OPRA) vs SPY-price proxy
  5. Failure mode enumeration
  6. Concentration disclosure

Per L55: FBW is a bounce-entry (bar wicks below support + closes above). These entries
have violent initial bounces that push ATM call premiums DOWN by >10% in bar 1 before
the directional move develops. premium_stop_pct=-0.99 (disabled) + chart stop.

Output: analysis/recommendations/fbw-morning-mid-real-fills.json
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
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "fbw-morning-mid-real-fills.json"

# ── Watcher parameters ────────────────────────────────────────────────────────
QTY = 3
PREMIUM_STOP_PCT = -0.99          # chart-stop only per L55 (bounce entry, premium stops fail)
STRIKE_OFFSET = 0                 # ATM calls
ENTRY_TIME_START = dt.time(9, 30)
ENTRY_TIME_END   = dt.time(11, 30)  # MORNING band
COOLDOWN_MINUTES = 45

CONF_MID_LOW  = 0.65              # inclusive
CONF_MID_HIGH = 0.80              # exclusive

# Chart stop: SPY must stay above support - $0.50. If it closes below that, pattern failed.
# In simulate_trade_real(side="C"): stop fires when spy_close < rejection_level - LEVEL_STOP_BUFFER(0.50)
# Effective stop = support - 0.50 - 0.50 = support - $1.00
CHART_STOP_BELOW_SUPPORT = 0.50

START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)
WALK_FORWARD_SPLIT = dt.date(2025, 9, 30)  # train: Jan-Sep 2025 | test: Oct 2025-May 2026

SCAN_PROXY_WR = 0.5962  # 16-month combo search, N=52

try:
    from crypto.lib.chart_patterns import Bar, failed_breakdown_wick as _detect_fbw
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available")
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

    # VIX alignment
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

    log.info("Scanning for FBW conf=MID | MORNING signals (%s-%s ET, conf=[%.2f,%.2f))...",
             ENTRY_TIME_START, ENTRY_TIME_END, CONF_MID_LOW, CONF_MID_HIGH)
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 12:  # need lookback_for_support=10 + 2
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

        # Time gate: MORNING
        bar_time_only = bar_time_naive.time()
        if bar_time_only < ENTRY_TIME_START or bar_time_only >= ENTRY_TIME_END:
            continue

        # Cooldown
        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        # FBW detector
        bars = _make_bars(rth, idx, window=12)
        if len(bars) < 12:
            continue

        hit = _detect_fbw(bars, lookback_for_support=10)
        if hit is None:
            continue

        # Confidence gate: MID band [0.65, 0.80)
        if hit.confidence < CONF_MID_LOW or hit.confidence >= CONF_MID_HIGH:
            continue

        last_signal_time = bar_time_naive
        bar_close = float(bar["close"])
        support = float(hit.notes.get("support_price", bar_close))
        vix_now = float(vix_arr.iloc[idx])
        is_train = bar_date <= WALK_FORWARD_SPLIT

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "bar": bar,
            "direction": "long",
            "side": "C",  # call, bullish
            "entry_spot": bar_close,
            "support": round(support, 2),
            "rejection_level": round(support - CHART_STOP_BELOW_SUPPORT, 2),
            "vix": round(vix_now, 1),
            "vix_bucket": "<17" if vix_now < 17 else ("17-20" if vix_now < 20 else ("20-25" if vix_now < 25 else ">=25")),
            "conf_score": round(hit.confidence, 3),
            "sweep_depth": round(float(hit.notes.get("sweep_depth_dollars", 0)), 2),
            "close_back": round(float(hit.notes.get("close_back_margin_dollars", 0)), 2),
            "wick_ratio": float(hit.notes.get("wick_to_body_ratio") or 0),
            "vol_mult": round(float(hit.notes.get("volume_mult", 1.0)), 2),
            "is_train": is_train,
        })

    log.info("Found %d signals (%d train / %d test). Running real-fills simulation...",
             len(signals),
             sum(1 for s in signals if s["is_train"]),
             sum(1 for s in signals if not s["is_train"]))

    results: list[dict] = []
    wins = losses = no_data = 0
    total_pnl = 0.0
    train_wins = train_losses = train_pnl = 0.0
    test_wins = test_losses = test_pnl = 0.0
    vix_bucket_w: Counter = Counter()
    vix_bucket_n: Counter = Counter()

    for sig in signals:
        entry_bar = rth.iloc[sig["bar_idx"]]
        fill = simulate_trade_real(
            entry_bar_idx=sig["bar_idx"],
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=sig["rejection_level"],
            triggers_fired=["fbw_detector", "morning_window", "conf_mid_band"],
            side=sig["side"],
            qty=QTY,
            setup="FAILED_BREAKDOWN_WICK_MORNING_MID",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        base_rec = {k: v for k, v in sig.items() if k != "bar"}

        if fill is None:
            no_data += 1
            results.append({**base_rec, "outcome": "NO_OPRA_DATA", "pnl": 0.0})
            continue

        pnl = float(fill.dollar_pnl)
        exit_reason = fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason)
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")

        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

        total_pnl += pnl
        bucket = sig["vix_bucket"]
        vix_bucket_n[bucket] += 1
        if pnl > 0:
            vix_bucket_w[bucket] += 1

        if sig["is_train"]:
            if pnl > 0:
                train_wins += 1
            elif pnl < 0:
                train_losses += 1
            train_pnl += pnl
        else:
            if pnl > 0:
                test_wins += 1
            elif pnl < 0:
                test_losses += 1
            test_pnl += pnl

        results.append({**base_rec,
                        "outcome": outcome,
                        "pnl": round(pnl, 2),
                        "exit_reason": exit_reason,
                        "strike": fill.strike,
                        "entry_premium": round(float(fill.entry_premium), 3),
                        })

    n_completed = wins + losses
    full_wr = wins / n_completed if n_completed else 0.0
    train_n = train_wins + train_losses
    test_n  = test_wins + test_losses
    train_wr = train_wins / train_n if train_n else 0.0
    test_wr  = test_wins  / test_n  if test_n  else 0.0

    # VIX stratification
    vix_split = {}
    for bucket in sorted(set(vix_bucket_n.keys())):
        n = vix_bucket_n[bucket]
        w = vix_bucket_w[bucket]
        vix_split[bucket] = {"n": n, "wins": w, "wr": round(w/n, 3) if n else 0.0}

    # ── Gate check (OP-21) ────────────────────────────────────────────────────
    gate_a = test_wr >= 0.50        # WF OOS WR >= 50%
    gate_b = full_wr >= 0.50        # real-fills WR >= 50%
    gate_c = test_n >= 15           # N_test >= 15
    gate_d = test_pnl > 0           # OOS P&L positive
    all_gates = gate_a and gate_b and gate_c and gate_d

    verdict = "PASS" if all_gates else "FAIL"

    summary = {
        "scan_proxy_wr": SCAN_PROXY_WR,
        "total_signals": len(signals),
        "n_completed": n_completed,
        "n_no_data": no_data,
        "full_wr": round(full_wr, 3),
        "full_pnl": round(total_pnl, 2),
        "avg_pnl_per_trade": round(total_pnl / n_completed, 2) if n_completed else 0.0,
        "walk_forward": {
            "split": WALK_FORWARD_SPLIT.isoformat(),
            "train_n": train_n, "train_wr": round(train_wr, 3), "train_pnl": round(train_pnl, 2),
            "test_n": test_n,  "test_wr": round(test_wr, 3),  "test_pnl": round(test_pnl, 2),
            "verdict": "STABLE" if (gate_a and gate_c and gate_d) else "DEGRADED",
        },
        "vix_stratification": vix_split,
        "op21_gates": {
            "(a) WF OOS WR >= 50%": gate_a,
            "(b) real-fills WR >= 50%": gate_b,
            "(c) N_test >= 15": gate_c,
            "(d) OOS P&L > 0": gate_d,
            "ALL_PASS": all_gates,
        },
        "verdict": verdict,
        "params": {
            "side": "C", "qty": QTY, "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_below_support": CHART_STOP_BELOW_SUPPORT,
            "tp1_premium_pct": 0.30, "runner_target": 1.5,
            "entry_time": f"{ENTRY_TIME_START}-{ENTRY_TIME_END}",
            "conf_band": f"[{CONF_MID_LOW},{CONF_MID_HIGH})",
            "cooldown_minutes": COOLDOWN_MINUTES,
        },
        "op20_disclosures": {
            "1_account_assumption": f"qty={QTY} contracts at ATM. $1K account: ~30% equity/trade. Scale qty per tier.",
            "2_sample_bias": f"N={len(signals)} signals from 16-month in-sample window. Overfit possible.",
            "3_oos_result": f"WF test (Oct 2025-May 2026): WR={test_wr:.1%}, N={test_n}, P&L=${test_pnl:.2f}",
            "4_real_fills": "OPRA-based option premiums, not SPY-price proxy",
            "5_failure_modes": "FBW fails when support level is noise (no named level), when SPY continues through support after initial wick. Chart stop absorbs false-break failures.",
            "6_concentration": f"max_month_share=13.5% (combo search 16mo). VIX split: {json.dumps(vix_split)}",
        },
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Done. Verdict: %s", verdict)
    log.info("  Full WR: %.1f%% (N=%d, P&L=$%.2f)", full_wr * 100, n_completed, total_pnl)
    log.info("  WF TRAIN: WR=%.1f%% N=%d P&L=$%.2f", train_wr * 100, train_n, train_pnl)
    log.info("  WF TEST:  WR=%.1f%% N=%d P&L=$%.2f", test_wr * 100, test_n, test_pnl)
    log.info("  Gates: %s", summary["op21_gates"])
    log.info("Output: %s", OUT_JSON)
    return summary


if __name__ == "__main__":
    scan_and_validate()
