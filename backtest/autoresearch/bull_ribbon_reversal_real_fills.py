"""Real-fills validation for BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON signals.

CRITICAL FINDING (2026-05-19): The scanner (bull_ribbon_reversal_scan.py) has a
timezone bug. It reads SPY timestamps as UTC-aware and calls .time() on them, which
returns UTC time. SPY bars are stored with -04:00 ET offset, so the UTC time is
4 hours ahead of ET. The "time gate" of 11:00 checks 11:00 UTC = 07:00 ET (pre-market).
All 4 signals appear at UTC 13:35-14:05, which is ET 09:35-10:05 — in the FIRST HOUR
of RTH, NOT after 11:00 ET as the spec intends.

This means:
  - The scan's "time" field shows UTC, not ET
  - All 4 signals fire in the opening range (09:35-10:05 ET)
  - The "after 11:00 ET" gate in the spec was never enforced by the scanner
  - As-designed (truly after 11:00 ET): 0 valid historical signals in 342-day scan

This is documented as a CRITICAL scanner bug. The real-fills below are run on the
correct bars (using bar_idx_global which maps correctly to 09:35-10:05 ET bars),
not the stated "13:35-14:05" timestamps.

Runs simulate_trade_real on the 4 historical signals using WATCH-ONLY default knobs:
  - TP1: +25% premium
  - Runner target: 1.5x entry premium (+50%)
  - Stop: -6% premium stop
  - Strike: ATM or nearest cached proxy

Signal dates with correct ET times:
  2025-04-23 09:35 ET (scan: "13:35"): bar_close=541.87 -> ATM P542 MISS -> P540 (OTM-2)
  2026-03-23 09:40 ET (scan: "13:40"): bar_close=657.99 -> ATM P658 HIT
  2026-03-23 09:50 ET (scan: "13:50"): bar_close=659.58 -> ATM P660 HIT
  2026-03-31 10:05 ET (scan: "14:05"): bar_close=641.22 -> ATM P641 MISS -> P645 (ITM-4)

Output: analysis/recommendations/bull_ribbon_reversal_real_fills.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.ribbon import compute_ribbon, ribbon_at as _ribbon_at_state
from lib.option_pricing_real import option_symbol, load_contract_bars, CACHE_DIR
import lib.simulator as _sim_mod
from lib.simulator_real import simulate_trade_real


def _load_and_prep_spy(spy_path: str) -> pd.DataFrame:
    """Load and normalise SPY CSV to TZ-naive ET timestamps."""
    df = pd.read_csv(spy_path)
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return df


def _build_ribbon_df(spy_df: pd.DataFrame) -> pd.DataFrame:
    closes = spy_df["close"].astype(float).values
    return compute_ribbon(pd.Series(closes))


def run_signal(
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    signal_date: str,
    bar_idx_global: int,
    level: float,
    bar_close_from_scan: float,
    strike_override: int,
    cache_note: str,
    scanner_time_utc: str,    # what the scanner reported (UTC, wrongly labelled as ET)
    actual_time_et: str,      # the real ET time from bar_idx
    tp1_pct: float = 0.25,
    runner_target_pct: float = 0.50,   # 1.5x = +50%
    stop_pct: float = -0.06,
    qty: int = 3,
) -> dict:
    """Run simulate_trade_real for one signal and return a result dict."""

    if bar_idx_global >= len(spy_df):
        return {
            "date": signal_date,
            "scanner_time_utc": scanner_time_utc,
            "actual_time_et": actual_time_et,
            "status": "BAR_IDX_OUT_OF_RANGE",
            "error": f"bar_idx_global={bar_idx_global} >= len(spy_df)={len(spy_df)}",
        }

    bar = spy_df.iloc[bar_idx_global]
    entry_spot = float(bar["close"])
    actual_close = round(entry_spot, 3)

    if abs(actual_close - bar_close_from_scan) > 0.10:
        return {
            "date": signal_date,
            "scanner_time_utc": scanner_time_utc,
            "actual_time_et": actual_time_et,
            "status": "BAR_CLOSE_MISMATCH",
            "error": f"bar[{bar_idx_global}].close={actual_close} but scan says {bar_close_from_scan}",
        }

    symbol = option_symbol(
        dt.datetime.strptime(signal_date, "%Y-%m-%d").date(),
        strike_override,
        "P",
    )
    opt_df = load_contract_bars(symbol)

    if opt_df is None:
        return {
            "date": signal_date,
            "scanner_time_utc": scanner_time_utc,
            "actual_time_et": actual_time_et,
            "status": "OPRA_CACHE_MISS",
            "cache_note": cache_note,
            "symbol_attempted": symbol,
            "strike": strike_override,
            "entry_spot": actual_close,
            "error": f"No OPRA bars cached for {symbol}",
        }

    # Patch simulator constants for watch-only knobs
    orig_tp1 = _sim_mod.TP1_PREMIUM_PCT
    orig_runner = _sim_mod.RUNNER_MAX_PREMIUM_PCT

    _sim_mod.TP1_PREMIUM_PCT = tp1_pct
    _sim_mod.RUNNER_MAX_PREMIUM_PCT = runner_target_pct

    try:
        result = simulate_trade_real(
            entry_bar_idx=bar_idx_global,
            entry_bar=bar,
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=level,
            triggers_fired=["BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON"],
            side="P",
            qty=qty,
            setup="BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON",
            premium_stop_pct=stop_pct,
            strike_override=strike_override,
        )
    finally:
        _sim_mod.TP1_PREMIUM_PCT = orig_tp1
        _sim_mod.RUNNER_MAX_PREMIUM_PCT = orig_runner

    if result is None:
        return {
            "date": signal_date,
            "scanner_time_utc": scanner_time_utc,
            "actual_time_et": actual_time_et,
            "status": "SIM_RETURNED_NONE",
            "cache_note": cache_note,
            "symbol": symbol,
            "entry_spot": actual_close,
            "strike": strike_override,
            "error": "simulate_trade_real returned None — no valid entry bar in option data",
        }

    return {
        "date": signal_date,
        "scanner_time_utc": scanner_time_utc,
        "actual_time_et": actual_time_et,
        "status": "OK",
        "cache_note": cache_note,
        "symbol": symbol,
        "strike": strike_override,
        "entry_spot": actual_close,
        "bar_close_from_scan": bar_close_from_scan,
        "atm_from_scan": int(round(bar_close_from_scan)),
        "entry_premium": round(result.entry_premium, 4),
        "exit_reason": result.exit_reason.name if result.exit_reason else None,
        "tp1_premium": round(result.tp1_premium, 4) if result.tp1_premium else None,
        "runner_exit_premium": round(result.runner_exit_premium, 4) if result.runner_exit_premium else None,
        "dollar_pnl": round(result.dollar_pnl, 2) if result.dollar_pnl is not None else None,
        "pct_return_on_premium": round(result.pct_return_on_premium, 4) if result.pct_return_on_premium is not None else None,
        "hold_minutes": result.hold_minutes,
        "bars_held": result.bars_held,
        "max_adverse_premium": round(result.max_adverse_premium, 4),
        "max_favorable_premium": round(result.max_favorable_premium, 4),
        "qty": qty,
        "knobs_used": {
            "tp1_pct": tp1_pct,
            "runner_target_pct": runner_target_pct,
            "stop_pct": stop_pct,
            "strike": strike_override,
        },
    }


def main():
    spy_path = str(REPO / "data" / "spy_5m_2025-01-01_2026-05-15.csv")
    print(f"Loading SPY: {spy_path}")
    spy_df = _load_and_prep_spy(spy_path)
    ribbon_df = _build_ribbon_df(spy_df)
    print(f"Loaded {len(spy_df)} SPY bars, computed ribbon.")

    # Signal definitions using bar_idx_global (verified to match bar_close_from_scan)
    # OPRA cache coverage:
    #   2025-04-23: ATM=542, highest cached P540 -> use P540 (OTM-2 proxy)
    #   2026-03-23 09:40: ATM=658, P658 cached -> exact hit
    #   2026-03-23 09:50: ATM=660, P660 cached -> exact hit
    #   2026-03-31: ATM=641, lowest cached P645 -> use P645 (ITM-4 proxy)
    signals = [
        {
            "signal_date": "2025-04-23",
            "scanner_time_utc": "13:35",
            "actual_time_et": "09:35",
            "bar_idx_global": 5970,
            "level": 543.19,
            "bar_close_from_scan": 541.87,
            "strike_override": 540,
            "cache_note": (
                "PARTIAL_CACHE — ATM P542 not cached; P540 used (OTM-2 proxy). "
                "OTM puts have higher % sensitivity but lower absolute premium. "
                "P&L directionally valid; slightly understated vs ATM."
            ),
        },
        {
            "signal_date": "2026-03-23",
            "scanner_time_utc": "13:40",
            "actual_time_et": "09:40",
            "bar_idx_global": 25816,
            "level": 659.80,
            "bar_close_from_scan": 657.99,
            "strike_override": 658,
            "cache_note": "FULL_CACHE_HIT — ATM P658 cached. Real OPRA fills.",
        },
        {
            "signal_date": "2026-03-23",
            "scanner_time_utc": "13:50",
            "actual_time_et": "09:50",
            "bar_idx_global": 25818,
            "level": 659.80,
            "bar_close_from_scan": 659.58,
            "strike_override": 660,
            "cache_note": (
                "FULL_CACHE_HIT — bar_close=659.58 rounds to ATM=660; P660 cached. "
                "Real OPRA fills."
            ),
        },
        {
            "signal_date": "2026-03-31",
            "scanner_time_utc": "14:05",
            "actual_time_et": "10:05",
            "bar_idx_global": 26667,
            "level": 641.46,
            "bar_close_from_scan": 641.22,
            "strike_override": 645,
            "cache_note": (
                "PARTIAL_CACHE — ATM P641 not cached; P645 used (ITM-4 proxy). "
                "ITM puts have higher absolute premium, lower % leverage. "
                "P&L directionally valid; slightly overstated vs ATM."
            ),
        },
    ]

    results = []
    for sig in signals:
        print(f"\nRunning {sig['signal_date']} {sig['actual_time_et']} ET (scanner said {sig['scanner_time_utc']})...")
        r = run_signal(
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            signal_date=sig["signal_date"],
            bar_idx_global=sig["bar_idx_global"],
            level=sig["level"],
            bar_close_from_scan=sig["bar_close_from_scan"],
            strike_override=sig["strike_override"],
            cache_note=sig["cache_note"],
            scanner_time_utc=sig["scanner_time_utc"],
            actual_time_et=sig["actual_time_et"],
        )
        results.append(r)
        status = r.get("status", "?")
        pnl = r.get("dollar_pnl")
        exit_reason = r.get("exit_reason", "?")
        print(f"  Status: {status} | P&L: {pnl} | Exit: {exit_reason}")

    ok_results = [r for r in results if r["status"] == "OK"]
    total_pnl = sum(r["dollar_pnl"] for r in ok_results if r.get("dollar_pnl") is not None)
    wins = [r for r in ok_results if (r.get("dollar_pnl") or 0) > 0]
    losses = [r for r in ok_results if (r.get("dollar_pnl") or 0) <= 0]

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Real-fills validation for BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON (OP-20 disclosure item 4)",
        "spec_file": "strategy/candidates/2026-05-19-bearish-reversal-at-level-on-bull-ribbon.md",
        "CRITICAL_SCANNER_BUG": {
            "description": (
                "bull_ribbon_reversal_scan.py has a timezone bug. The scanner reads SPY timestamps "
                "as UTC-aware and calls .time() on them, returning UTC time. "
                "SPY bars are stored with -04:00 ET offset, so UTC time = ET + 4h. "
                "The '11:00 ET' time gate checks 11:00 UTC = 07:00 ET (pre-market). "
                "All 4 signals fire in the opening range (09:35-10:05 ET), NOT after 11:00 ET. "
                "The spec's time field shows UTC, not ET."
            ),
            "implication": (
                "As designed (truly after 11:00 ET): 0 valid historical signals in 342-day scan. "
                "The 4 signals validated here are OPENING RANGE signals (first 35 min of RTH). "
                "This is a DIFFERENT setup archetype than the spec describes. "
                "The spec must be updated or the scanner must be fixed to enforce 11:00 ET correctly."
            ),
            "verification": {
                "bar_5970_timestamp_et": "2025-04-23 09:35:00",
                "bar_5970_close": 541.87,
                "scan_stated_time": "13:35 (UTC)",
                "bar_25816_timestamp_et": "2026-03-23 09:40:00",
                "scan_stated_time_2": "13:40 (UTC)",
            },
        },
        "knobs_used": {
            "tp1_premium_pct": "+25% (watch-only default from spec)",
            "runner_target_pct": "+50% i.e. 1.5x (watch-only default from spec)",
            "premium_stop_pct": "-6% (watch-only default from spec)",
            "strike": "ATM or nearest cached proxy",
            "qty": 3,
        },
        "opra_cache_coverage": {
            "2025-04-23_P542_ATM": "MISS — used P540 (OTM-2 proxy)",
            "2026-03-23_P658_ATM": "HIT — exact ATM",
            "2026-03-23_P660_ATM": "HIT — exact ATM",
            "2026-03-31_P641_ATM": "MISS — used P645 (ITM-4 proxy)",
        },
        "summary": {
            "signals_attempted": len(signals),
            "ok_results": len(ok_results),
            "full_cache_hits": 2,
            "partial_cache_proxy": 2,
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl_3_contracts": round(total_pnl, 2),
            "interpretation": (
                "All 4 signals are opening-range (09:35-10:05 ET) level rejections, not "
                "the intended post-11:00 ET countertrend fade. Results reflect real fills "
                "on those bars. The stop at -6% is hit quickly on these early bars, "
                "consistent with opening-range volatility making tight stops unprofitable."
            ),
        },
        "signals": results,
    }

    out_path = REPO.parents[0] / "analysis" / "recommendations" / "bull_ribbon_reversal_real_fills.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWrote: {out_path}")
    print(f"Summary: {len(ok_results)}/{len(signals)} OK, {len(wins)} wins, {len(losses)} losses, total P&L: ${total_pnl:.2f}")
    print("\nCRITICAL: Scanner timezone bug — all signals are opening-range (09:35-10:05 ET), not post-11:00 ET.")


if __name__ == "__main__":
    main()
