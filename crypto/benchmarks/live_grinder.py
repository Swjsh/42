"""live_grinder — run the validator suite repeatedly to collect distribution statistics.

Fires runner.py every `--interval` seconds for `--duration` seconds. Each run's
scorecard is appended to crypto/data/scorecards/grinder.jsonl with a timestamp.

After accumulating data, run analyze_grinder.py to summarize:
  - how often each validator passes
  - what verdicts dominate
  - which knob-affected behaviors are stable vs flaky
  - foot-gun catch rate (v01 with naive_last_bar_in_progress=True)
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
# When launched via pythonw.exe (no console), Windows 11's default-terminal can allocate a
# visible WindowsTerminal -Embedding tab on first stdout/stderr write. Redirect to log files
# BEFORE any module-level write. 2026-05-17 evening foot-gun fix.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "live-grinder.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "live-grinder.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.validators import (
    v01_closed_bar, v02_source_parity, v03_indicators, v04_candlesticks,
    v05_levels, v06_trendlines, v07_volume, v08_ribbon,
    v09_regime, v10_divergence, v11_breakout, v12_multi_timeframe,
    v14_sweep, v15_three_source_parity, v16_session_levels_spy,
    v17_entry_gate_timing, v18_vix_filter, v19_profit_lock,
    v20_strike_selection, v21_kill_switch, v22_chart_patterns,
    v23_orb_warmup, v24_runner_invariants, v25_filter_gates,
    v26_ghost_entry_detection, v27_stale_cache_detection, v28_nlwb_bounce_gate,
)

# v13 skipped: requires a live TV MCP snapshot file — interactive-session only.
# v15 (three_source_parity) and v02 are KNOWN_FLAKY live-source parity checks.

_ROOT = Path(__file__).resolve().parents[2]

# SPY CSV for v16_session_levels_spy — find the most recent file in backtest/data/.
def _spy_csv_path() -> Path:
    candidates = sorted((_ROOT / "backtest" / "data").glob("spy_5m_*.csv"), reverse=True)
    return candidates[0] if candidates else _ROOT / "backtest" / "data" / "spy_5m.csv"


def _run_iteration(symbol: str, granularity: int, count: int) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    rec = {"started_at": started, "symbol": symbol, "granularity": granularity, "results": {}}

    # ── v01: closed-bar filter (offline + live) ──────────────────────────────
    try:
        rec["results"]["v01_offline"] = v01_closed_bar.run_offline()
    except Exception as e:
        rec["results"]["v01_offline"] = {"error": str(e)}

    try:
        rec["results"]["v01_live"] = v01_closed_bar.run_live("coinbase", symbol, granularity, 20)
    except Exception as e:
        rec["results"]["v01_live"] = {"error": str(e)}

    # ── v02: source parity (KNOWN_FLAKY — timing jitter) ─────────────────────
    try:
        rec["results"]["v02_parity"] = v02_source_parity.compare(symbol, granularity, 20)
    except Exception as e:
        rec["results"]["v02_parity"] = {"error": str(e)}

    # ── v03: indicators ───────────────────────────────────────────────────────
    try:
        rec["results"]["v03_offline"] = v03_indicators.run_offline()
    except Exception as e:
        rec["results"]["v03_offline"] = {"error": str(e)}

    try:
        rec["results"]["v03_indicators_live"] = v03_indicators.run_live(symbol, granularity, count)
    except Exception as e:
        rec["results"]["v03_indicators_live"] = {"error": str(e)}

    # ── v04: candlesticks ─────────────────────────────────────────────────────
    try:
        rec["results"]["v04_offline"] = v04_candlesticks.run_offline()
    except Exception as e:
        rec["results"]["v04_offline"] = {"error": str(e)}

    try:
        rec["results"]["v04_candlesticks_live"] = v04_candlesticks.run_live(symbol, granularity, count)
    except Exception as e:
        rec["results"]["v04_candlesticks_live"] = {"error": str(e)}

    # ── v05–v11, v14: standard args (symbol, granularity, count) ─────────────
    _standard = [
        ("v05", v05_levels),
        ("v06", v06_trendlines),
        ("v07", v07_volume),
        ("v08", v08_ribbon),
        ("v09", v09_regime),
        ("v10", v10_divergence),
        ("v11", v11_breakout),
        ("v14", v14_sweep),
    ]
    for tag, mod in _standard:
        try:
            rec["results"][f"{tag}_offline"] = mod.run_offline()
        except Exception as e:
            rec["results"][f"{tag}_offline"] = {"error": str(e)}
        try:
            rec["results"][f"{tag}_live"] = mod.run_live(symbol, granularity, count)
        except Exception as e:
            rec["results"][f"{tag}_live"] = {"error": str(e)}

    # ── v12: multi-timeframe (symbol only, no granularity/count) ─────────────
    try:
        rec["results"]["v12_offline"] = v12_multi_timeframe.run_offline()
    except Exception as e:
        rec["results"]["v12_offline"] = {"error": str(e)}

    try:
        rec["results"]["v12_live"] = v12_multi_timeframe.run_live(symbol)
    except Exception as e:
        rec["results"]["v12_live"] = {"error": str(e)}

    # ── v15: three-source parity (KNOWN_FLAKY — timing jitter) ───────────────
    try:
        rec["results"]["v15_parity"] = v15_three_source_parity.compare3(symbol, granularity, count)
    except Exception as e:
        rec["results"]["v15_parity"] = {"error": str(e)}

    # ── v16: SPY session levels (requires SPY CSV path) ───────────────────────
    try:
        rec["results"]["v16_offline"] = v16_session_levels_spy.run_offline()
    except Exception as e:
        rec["results"]["v16_offline"] = {"error": str(e)}

    try:
        rec["results"]["v16_live"] = v16_session_levels_spy.run_live(_spy_csv_path())
    except Exception as e:
        rec["results"]["v16_live"] = {"error": str(e)}

    # ── v17–v25: no-arg validators ────────────────────────────────────────────
    _noarg = [
        ("v17", v17_entry_gate_timing),
        ("v18", v18_vix_filter),
        ("v19", v19_profit_lock),
        ("v20", v20_strike_selection),
        ("v21", v21_kill_switch),
        ("v22", v22_chart_patterns),
        ("v23", v23_orb_warmup),
        ("v24", v24_runner_invariants),
        ("v25", v25_filter_gates),
        ("v26", v26_ghost_entry_detection),
        ("v27", v27_stale_cache_detection),
        ("v28", v28_nlwb_bounce_gate),
    ]
    for tag, mod in _noarg:
        try:
            rec["results"][f"{tag}_offline"] = mod.run_offline()
        except Exception as e:
            rec["results"][f"{tag}_offline"] = {"error": str(e)}
        try:
            rec["results"][f"{tag}_live"] = mod.run_live()
        except Exception as e:
            rec["results"][f"{tag}_live"] = {"error": str(e)}

    # Capture raw bars (last 5 of each source) so ab_test_knob can replay knob values offline.
    # This is the OP-11 OUTER loop enabling autoresearch on historical data.
    try:
        cb = fetch_bars("coinbase", symbol, granularity, 5)
        rec["raw_bars_coinbase"] = [
            {"open_time": b.open_time.isoformat(), "open": b.open, "high": b.high,
             "low": b.low, "close": b.close, "volume": b.volume}
            for b in cb.bars
        ]
    except Exception as e:
        rec["raw_bars_coinbase_error"] = str(e)
    try:
        yf = fetch_bars("yfinance", symbol, granularity, 5)
        rec["raw_bars_yfinance"] = [
            {"open_time": b.open_time.isoformat(), "open": b.open, "high": b.high,
             "low": b.low, "close": b.close, "volume": b.volume}
            for b in yf.bars
        ]
    except Exception as e:
        rec["raw_bars_yfinance_error"] = str(e)
    rec["captured_now_utc"] = now_utc().isoformat()

    rec["finished_at"] = datetime.now(timezone.utc).isoformat()
    return rec


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--interval", type=int, default=300, help="seconds between iterations")
    p.add_argument("--duration", type=int, default=10800, help="total seconds to run (default 3h)")
    p.add_argument("--out", type=Path, default=Path("crypto/data/scorecards/grinder.jsonl"))
    p.add_argument("--max-iterations", type=int, default=0, help="0 = unlimited (duration-bounded)")
    args = p.parse_args(argv)

    started_at_unix = time.time()
    deadline = started_at_unix + args.duration
    args.out.parent.mkdir(parents=True, exist_ok=True)

    iteration = 0
    while time.time() < deadline:
        if args.max_iterations and iteration >= args.max_iterations:
            break
        iteration += 1
        try:
            rec = _run_iteration(args.symbol, args.granularity, args.count)
            rec["iteration"] = iteration
        except Exception:
            rec = {"iteration": iteration, "fatal": traceback.format_exc()}
        with args.out.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(f"[grinder] iter={iteration:03d} t+{int(time.time()-started_at_unix):05d}s ok")
        # Sleep until next interval, unless deadline is closer
        sleep_for = max(0, min(args.interval, deadline - time.time()))
        if sleep_for > 0:
            time.sleep(sleep_for)

    print(f"[grinder] complete. iterations={iteration} duration={int(time.time()-started_at_unix)}s out={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
