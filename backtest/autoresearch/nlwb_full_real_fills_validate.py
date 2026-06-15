"""Full 16-month real-fills validation for NAMED_LEVEL_WICK_BOUNCE (NLWB) watcher.

Replaces the curated 5-case nlwb_real_fills_validate.py with a full batch scan
analogous to hs_bear_real_fills_validate.py.  Per OP-20 disclosure 4 and L50:
SPY-price proxy WR != option P&L. This script validates real OPRA option P&L
against the scan proxy WR.

Walk-forward evidence (from nlwb_walk_forward.json, PDL relaxed variant):
    Train: Jan-Sep 2025  N=70,  WR=75.7%
    Test:  Oct 2025-May 2026  N=87,  WR=67.8%
    Delta: -7.9pp (test vs train, STABLE per OP-21 < 10pp threshold)

Production watcher gate: ribbon MIXED or BULL only.
    Ribbon-favorable subset (all PDL, ribbon=MIXED/BULL):
        Train: N=19, WR=73.7%
        Test:  N=21, WR=61.9%
        16-month combined: N≈40, WR≈67.5%  <- SCAN_PROXY_WR for this validation

Level proxy: PDL (prior RTH day low) — production watcher uses named levels from
key-levels.json, but PDL is the historical best proxy available for 16-month scan.

Simulation parameters (watcher defaults from named_level_wick_bounce_watcher.py):
  - side:               "C" (call, bullish) — bounce off support
  - qty:                3 contracts
  - strike_offset:      0 (ATM)
  - premium_stop_pct:   -0.99 (chart-stop only; per L55 — brief post-bounce dip
                         fires -10% stop before SPY resumes upward)
  - rejection_level:    pdl - 0.30 (chart stop 30c below the PDL bounce level)
      -> With LEVEL_STOP_BUFFER=0.50, stop fires at: pdl - 0.30 - 0.50 = pdl - 0.80
      -> Interpretation: SPY falls 80c below prior day low = false bounce

Output: analysis/recommendations/nlwb_full_real_fills.json
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
from autoresearch.named_level_bounce_scan import (  # noqa: E402
    _compute_prior_day_lows,
    _vol_baseline,
    _session_low_before_bar,
    ENTRY_TIME_START,
    ENTRY_TIME_END,
)
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "nlwb_full_real_fills.json"

# ── Scan parameters (PDL relaxed — max N for real-fills sample) ───────────────
START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

MIN_WICK_BELOW_CENTS = 8.0   # production watcher default
MIN_VOL_MULT = 1.0           # relaxed for max sample (production = 1.2x)
RIBBON_GATE_STACKS = ("MIXED", "BULL")  # production watcher gate

# ── Exit knobs (mirrors named_level_wick_bounce_watcher.py) ──────────────────
QTY = 3
PREMIUM_STOP_PCT = -0.99     # chart-stop only per L55 (initial bounce dip)
STRIKE_OFFSET = 0            # ATM call
_CHART_STOP_BELOW_LEVEL = 0.30  # rejection_level = pdl - 0.30

# ── Scan proxy WR (ribbon-favorable subset, PDL relaxed 16-month) ────────────
SCAN_PROXY_WR = 0.675  # 67.5% combined ribbon-favorable (train 73.7%, test 61.9%)
SCAN_PROXY_WR_ALL = 0.713  # 71.3% all PDL signals (all ribbons, N=157)


def scan_and_validate() -> dict:
    log.info("Loading 16-month SPY+VIX data (%s to %s)...", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    # Add time column for _compute_prior_day_lows / _session_low_before_bar helpers
    rth["time"] = rth["timestamp_et"].dt.time
    log.info("RTH bars: %d", len(rth))

    # VIX alignment — tz-naive index
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

    # Compute PDL map and ribbon
    log.info("Computing PDL map and ribbon...")
    pdl_map = _compute_prior_day_lows(rth)
    log.info("PDL map: %d trading days", len(pdl_map))

    ribbon_df = compute_ribbon(rth["close"])

    log.info(
        "Scanning for NLWB signals (PDL, wick>=%dc, ribbon=MIXED/BULL, vol>=%.1fx, "
        "time=%s-%s)...",
        int(MIN_WICK_BELOW_CENTS), MIN_VOL_MULT, ENTRY_TIME_START, ENTRY_TIME_END,
    )

    signals: list[dict] = []
    bear_ribbon_skipped = 0

    for idx in range(25, len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()

        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue

        # Time window gate
        bar_time_only = bar_time_naive.time()
        if bar_time_only < ENTRY_TIME_START or bar_time_only > ENTRY_TIME_END:
            continue

        # PDL available?
        pdl = pdl_map.get(bar_date)
        if pdl is None:
            continue

        bar_low   = float(bar["low"])
        bar_close = float(bar["close"])
        bar_vol   = float(bar.get("volume", 0))

        # Gate 1: wick below PDL by >= MIN_WICK_BELOW_CENTS
        wick_cents = round((pdl - bar_low) * 100.0, 2)
        if wick_cents < MIN_WICK_BELOW_CENTS:
            continue

        # Gate 2: close ABOVE PDL (bounce confirmed)
        if bar_close <= pdl:
            continue

        # Gate 3: volume >= MIN_VOL_MULT × 20-bar baseline
        vol_base = _vol_baseline(rth, idx, lookback=20)
        if vol_base <= 0 or (bar_vol / vol_base) < MIN_VOL_MULT:
            continue

        # Gate 4: ribbon MIXED or BULL (production watcher gate)
        rib = ribbon_at(ribbon_df, idx)
        if rib is None:
            continue
        ribbon_stack = rib.stack
        if ribbon_stack not in RIBBON_GATE_STACKS:
            bear_ribbon_skipped += 1
            continue

        # VIX for stratification
        vix_now = float(vix_arr.iloc[idx])
        if vix_now < 15:
            vix_bucket = "<15"
        elif vix_now < 17:
            vix_bucket = "15-17"
        elif vix_now < 20:
            vix_bucket = "17-20"
        elif vix_now < 25:
            vix_bucket = "20-25"
        else:
            vix_bucket = ">=25"

        # Session low context
        session_low = _session_low_before_bar(rth, idx, bar_date)
        near_session_low = bar_low <= session_low + 0.10

        # Rejection level for chart stop (false bounce = falls below PDL)
        rejection_level = round(pdl - _CHART_STOP_BELOW_LEVEL, 4)

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "bar": bar,
            "direction": "long",
            "side": "C",
            "entry_spot": float(bar_close),
            "pdl": round(pdl, 2),
            "wick_cents": round(wick_cents, 1),
            "rejection_level": round(rejection_level, 4),
            "ribbon_stack": ribbon_stack,
            "ribbon_spread_cents": round(rib.spread_cents, 1),
            "vix": round(vix_now, 1),
            "vix_bucket": vix_bucket,
            "near_session_low": near_session_low,
            "vol_ratio": round(bar_vol / vol_base, 2) if vol_base > 0 else None,
        })

    log.info(
        "Signals found: %d  (BEAR-ribbon skipped: %d)",
        len(signals), bear_ribbon_skipped,
    )
    log.info("Running real-fills simulation (side=C, ATM, premium_stop=-0.99)...")

    results: list[dict] = []
    wins = 0
    losses = 0
    no_data = 0
    total_pnl = 0.0
    vix_wins: Counter = Counter()
    vix_total: Counter = Counter()
    ribbon_wins: Counter = Counter()
    ribbon_total: Counter = Counter()
    hour_dist: Counter = Counter()

    for sig in signals:
        bar_idx = sig["bar_idx"]
        entry_bar = sig["bar"]

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=sig["rejection_level"],
            triggers_fired=["WICK_BELOW_PDL", "BOUNCE_CLOSE_ABOVE", "RIBBON_MIXED_OR_BULL"],
            side="C",
            qty=QTY,
            setup="NAMED_LEVEL_WICK_BOUNCE",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        hour = int(sig["time"].split(":")[0])
        hour_dist[hour] += 1
        vix_bucket_key = sig["vix_bucket"]
        ribbon_key = sig["ribbon_stack"]

        if fill is None:
            results.append({
                "date": sig["date"], "time": sig["time"],
                "status": "NO_OPRA_DATA",
                "direction": "long", "vix": sig["vix"],
                "vix_bucket": vix_bucket_key,
                "entry_spot": round(sig["entry_spot"], 2),
                "pdl": sig["pdl"],
                "ribbon_stack": sig["ribbon_stack"],
            })
            no_data += 1
            continue

        pnl = fill.dollar_pnl
        total_pnl += pnl
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        if pnl > 0:
            wins += 1
            vix_wins[vix_bucket_key] += 1
            ribbon_wins[ribbon_key] += 1
        else:
            losses += 1
        vix_total[vix_bucket_key] += 1
        ribbon_total[ribbon_key] += 1

        exit_prem = fill.runner_exit_premium or fill.tp1_premium or 0.0
        results.append({
            "date": sig["date"], "time": sig["time"],
            "status": "COMPLETE",
            "direction": "long",
            "side": "C",
            "vix": sig["vix"],
            "vix_bucket": vix_bucket_key,
            "entry_spot": round(sig["entry_spot"], 2),
            "pdl": sig["pdl"],
            "wick_cents": sig["wick_cents"],
            "ribbon_stack": sig["ribbon_stack"],
            "near_session_low": sig["near_session_low"],
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
                round(fill.max_adverse_premium, 3) if fill.max_adverse_premium else None
            ),
        })

    completed = wins + losses
    wr_real = round(wins / completed, 3) if completed > 0 else 0.0
    delta_vs_ribbon_favorable_pp = round((wr_real - SCAN_PROXY_WR) * 100, 1)
    delta_vs_all_signals_pp = round((wr_real - SCAN_PROXY_WR_ALL) * 100, 1)

    if abs(delta_vs_ribbon_favorable_pp) <= 10.0:
        verdict = "FAVORABLE — real-fills WR within 10pp of scan proxy (ribbon-favorable subset)"
    elif delta_vs_ribbon_favorable_pp < -10.0:
        verdict = "DEGRADED — real-fills WR >10pp below ribbon-favorable scan proxy"
    else:
        verdict = "IMPROVED — real-fills WR exceeds ribbon-favorable scan proxy"

    # VIX breakdown
    by_vix: dict = {}
    for bucket in ["<15", "15-17", "17-20", "20-25", ">=25"]:
        n = vix_total[bucket]
        w = vix_wins[bucket]
        by_vix[bucket] = {"n": n, "wins": w, "wr_pct": round(w / n * 100, 1) if n > 0 else None}

    # Ribbon breakdown
    by_ribbon: dict = {}
    for stack in ["MIXED", "BULL"]:
        n = ribbon_total[stack]
        w = ribbon_wins[stack]
        by_ribbon[stack] = {"n": n, "wins": w, "wr_pct": round(w / n * 100, 1) if n > 0 else None}

    # Hour breakdown
    by_hour = {f"{h:02d}:00": hour_dist[h] for h in sorted(hour_dist.keys())}

    op21_pass = wr_real >= 0.50 and total_pnl > 0

    log.info("=== SUMMARY ===")
    log.info("Total signals: %d  Completed: %d  No-data: %d", len(signals), completed, no_data)
    log.info(
        "Wins: %d  Losses: %d  WR: %.1f%%  "
        "(ribbon-fav proxy: %.1f%%, all-signals proxy: %.1f%%)",
        wins, losses, wr_real * 100, SCAN_PROXY_WR * 100, SCAN_PROXY_WR_ALL * 100,
    )
    log.info("Total P&L: $%.0f  Per-trade avg: $%.0f",
             total_pnl, total_pnl / completed if completed else 0)
    log.info("Verdict: %s (delta vs ribbon-fav=%.1fpp)", verdict, delta_vs_ribbon_favorable_pp)
    log.info("By VIX: %s", by_vix)
    log.info("By ribbon: %s", by_ribbon)

    summary = {
        "run_date": dt.date.today().isoformat(),
        "window": f"{START} to {END}",
        "scan_variant": "PDL relaxed (wick>=8c, vol>=1.0x, ribbon=MIXED/BULL)",
        "n_signals_found": len(signals),
        "n_bear_ribbon_skipped": bear_ribbon_skipped,
        "n_completed": completed,
        "n_no_opra_data": no_data,
        "wins": wins,
        "losses": losses,
        "wr_real": wr_real,
        "scan_proxy_wr_ribbon_favorable": SCAN_PROXY_WR,
        "scan_proxy_wr_all_signals": SCAN_PROXY_WR_ALL,
        "delta_vs_ribbon_fav_pp": delta_vs_ribbon_favorable_pp,
        "delta_vs_all_signals_pp": delta_vs_all_signals_pp,
        "total_dollar_pnl": round(total_pnl, 2),
        "avg_dollar_pnl_per_trade": round(total_pnl / completed, 2) if completed else 0,
        "verdict": verdict,
        "op21_real_fills_gate": "PASS" if op21_pass else "FAIL",
        "by_vix_bucket": by_vix,
        "by_ribbon_stack": by_ribbon,
        "by_hour_signals": by_hour,
        "notes": (
            "PDL (prior RTH day low) used as level proxy — production watcher uses named levels "
            "from key-levels.json, PDL is the best available historical proxy. "
            "Ribbon gate: MIXED or BULL only (BEAR ribbon skipped — production watcher gate). "
            "premium_stop_pct=-0.99 (chart-stop only per L55: initial bounce dip fires -10% "
            "stop before SPY resumes upward). "
            "rejection_level=pdl-0.30 -> effective level stop at pdl-0.80 "
            "(+0.50 LEVEL_STOP_BUFFER in simulator_real for side=C). "
            "Scan proxy WR=67.5% from walk-forward ribbon-favorable subset (train 73.7% N=19, "
            "test 61.9% N=21). All-signals proxy WR=71.3% (PDL relaxed N=157)."
        ),
        "simulation_params": {
            "qty": QTY,
            "side": "C",
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_below_level": _CHART_STOP_BELOW_LEVEL,
            "effective_level_stop_from_pdl": round(_CHART_STOP_BELOW_LEVEL + 0.50, 2),
            "entry_time_start": str(ENTRY_TIME_START),
            "entry_time_end": str(ENTRY_TIME_END),
            "min_wick_below_cents": MIN_WICK_BELOW_CENTS,
            "min_vol_mult": MIN_VOL_MULT,
            "ribbon_gate": list(RIBBON_GATE_STACKS),
        },
        "walk_forward_reference": {
            "pdl_relaxed_train_wr": 0.757,
            "pdl_relaxed_train_n": 70,
            "pdl_relaxed_test_wr": 0.678,
            "pdl_relaxed_test_n": 87,
            "pdl_relaxed_delta_pp": -7.9,
            "pdl_relaxed_verdict": "STABLE",
            "ribbon_fav_train_wr": 0.737,
            "ribbon_fav_train_n": 19,
            "ribbon_fav_test_wr": 0.619,
            "ribbon_fav_test_n": 21,
        },
        "op21_promotion_status": {
            "historical_gate": "PASS (WR=71.3% N=157 PDL all-signals > 50%)",
            "walk_forward_gate": "PASS (PDL relaxed: train 75.7% N=70 / test 67.8% N=87, STABLE -7.9pp)",
            "real_fills_gate": "PASS" if op21_pass else "FAIL",
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
    print(f"\n=== NAMED_LEVEL_WICK_BOUNCE FULL REAL-FILLS RESULT ===")
    print(f"Signals: {result['n_signals_found']}  Completed: {result['n_completed']}  "
          f"No-data: {result['n_no_opra_data']}")
    print(f"Real-fills WR: {result['wr_real']*100:.1f}%  "
          f"(ribbon-fav proxy: {result['scan_proxy_wr_ribbon_favorable']*100:.1f}%, "
          f"all-signals proxy: {result['scan_proxy_wr_all_signals']*100:.1f}%)")
    print(f"Delta vs ribbon-fav proxy: {result['delta_vs_ribbon_fav_pp']:+.1f}pp")
    print(f"Verdict: {result['verdict']}")
    print(f"Total P&L: ${result['total_dollar_pnl']:.0f}  "
          f"Avg/trade: ${result['avg_dollar_pnl_per_trade']:.0f}")
    print(f"OP-21 real-fills gate: {result['op21_real_fills_gate']}")
    print(f"\nBy VIX bucket:")
    for bucket, stats in result["by_vix_bucket"].items():
        if stats["n"] > 0:
            print(f"  {bucket}: N={stats['n']}  WR={stats['wr_pct']}%")
    print(f"\nBy ribbon stack:")
    for stack, stats in result["by_ribbon_stack"].items():
        if stats["n"] > 0:
            print(f"  {stack}: N={stats['n']}  WR={stats['wr_pct']}%")
    print(f"\nOP-21 status:")
    for k, v in result["op21_promotion_status"].items():
        print(f"  {k}: {v}")
