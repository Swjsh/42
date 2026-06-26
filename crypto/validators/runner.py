"""runner — execute all validators, aggregate into one scorecard.

Includes the 13 validator suites + the 5/14 replay benchmark + the TV MCP fixture parity.
Exit code 0 if all PASS, 1 otherwise.

Writes:
  crypto/data/scorecards/latest.json
  crypto/data/scorecards/history.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from crypto.benchmarks import replay_5_14
from crypto.validators import (
    v01_closed_bar, v02_source_parity, v03_indicators, v04_candlesticks,
    v05_levels, v06_trendlines, v07_volume, v08_ribbon, v09_regime,
    v10_divergence, v11_breakout, v12_multi_timeframe, v13_tv_mcp_parity,
    v14_sweep, v15_three_source_parity, v16_session_levels_spy,
    v17_entry_gate_timing, v18_vix_filter, v19_profit_lock,
    v20_strike_selection, v21_kill_switch, v22_chart_patterns,
    v23_orb_warmup,
    v24_runner_invariants,
    v25_filter_gates,
    v26_ghost_entry_detection,
    v27_stale_cache_detection,
    v28_nlwb_bounce_gate,
    v29_db_base_quiet_gate,
    v30_db_morning_low_vol_gate,
    v31_momentum_accel_highvol_gate,
    v32_db_base_quiet_gate,
    v33_close_ceiling_detection,
    v34_ceiling_floor_watcher_gate,
    v35_v14e_bear_only_gate,
    v36_orb_narrow_or_gate,
    v37_tbr_high_vol_gate,
    v38_v14e_chop_zone_gate,
    v39_orb_signal_reader,
    v40_bearish_rejection_morning_gate,
    v41_midday_trendline_gate,
    v42_sizing_risk_cap_guard,
    v43_ghost_entry_dual_account,
    v44_named_level_second_test_gate,
    v45_stairstep_continuation_gate,
    v46_market_structure,
    v47_chart_read,
    v48_double_top_gate,
    v49_market_structure_watcher_gate,
    v50_confluence,
)


def _run(name: str, fn, *args, **kwargs) -> dict:
    try:
        return {"name": name, "ok": True, "result": fn(*args, **kwargs)}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e), "traceback": traceback.format_exc()}


def _verdict(rec: dict) -> bool:
    if not rec["ok"]:
        return False
    res = rec.get("result", {})
    if "all_pass" in res:
        return bool(res["all_pass"])
    if "pass" in res:
        return bool(res["pass"])
    return True


# Live-source parity validators that are known to produce intermittent failures
# due to bar-boundary timing jitter between independent data sources.  BTC can
# move $40-$80 in the milliseconds between Coinbase, yfinance, and Alpaca API
# calls — causing the max-min spread to tick fractionally above the 5bp
# threshold on any given run.  These failures do NOT indicate an engine bug.
# They are excluded from overall_pass so a routine timing jitter event does not
# halt nightly CI or STATUS.md gate checks.
KNOWN_FLAKY_LIVE_SOURCE: frozenset[str] = frozenset({
    "v02_source_parity",            # coinbase ↔ yfinance 2-source — pre-existing
    "v15_three_source_parity.live", # coinbase ↔ yfinance ↔ alpaca 3-source — same class
})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--out-dir", type=Path, default=Path("crypto/data/scorecards"))
    p.add_argument("--skip-replay", action="store_true", help="Skip the 5/14 SPY replay benchmark")
    args = p.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()
    print("=" * 70)
    print(f"GAMMA CRYPTO VALIDATION + BENCHMARK  @  {started}")
    print(f"  symbol={args.symbol}  granularity={args.granularity}s  count={args.count}")
    print("=" * 70)

    runs = []
    stages = [
        ("v01_closed_bar.offline", v01_closed_bar.run_offline, [], {}),
        ("v01_closed_bar.live", v01_closed_bar.run_live, ["coinbase", args.symbol, args.granularity, 20], {}),
        ("v02_source_parity", v02_source_parity.compare, [args.symbol, args.granularity, 20], {}),
        ("v03_indicators.offline", v03_indicators.run_offline, [], {}),
        ("v03_indicators.live", v03_indicators.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v04_candlesticks.offline", v04_candlesticks.run_offline, [], {}),
        ("v04_candlesticks.live", v04_candlesticks.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v05_levels.offline", v05_levels.run_offline, [], {}),
        ("v05_levels.live", v05_levels.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v06_trendlines.offline", v06_trendlines.run_offline, [], {}),
        ("v06_trendlines.live", v06_trendlines.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v07_volume.offline", v07_volume.run_offline, [], {}),
        ("v07_volume.live", v07_volume.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v08_ribbon.offline", v08_ribbon.run_offline, [], {}),
        ("v08_ribbon.live", v08_ribbon.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v09_regime.offline", v09_regime.run_offline, [], {}),
        ("v09_regime.live", v09_regime.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v10_divergence.offline", v10_divergence.run_offline, [], {}),
        ("v10_divergence.live", v10_divergence.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v11_breakout.offline", v11_breakout.run_offline, [], {}),
        ("v11_breakout.live", v11_breakout.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v12_multi_timeframe.offline", v12_multi_timeframe.run_offline, [], {}),
        ("v12_multi_timeframe.live", v12_multi_timeframe.run_live, [args.symbol], {}),
        ("v13_tv_mcp_parity.fixture", v13_tv_mcp_parity.run_fixture, [_REPO_ROOT / "crypto/data/fixtures/tv_mcp_snapshot_2026-05-16T14-24Z.json", 0.05], {}),
        ("v14_sweep.offline", v14_sweep.run_offline, [], {}),
        ("v14_sweep.live", v14_sweep.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v15_three_source_parity.live", v15_three_source_parity.compare3, [args.symbol, args.granularity, 30], {"skip_most_recent": 2}),
        ("v16_session_levels_spy.offline", v16_session_levels_spy.run_offline, [], {}),
        ("v16_session_levels_spy.live", v16_session_levels_spy.run_live, [_REPO_ROOT / "backtest/data/spy_5m_2025-01-01_2026-05-15.csv", None], {}),
        ("v17_entry_gate_timing.offline", v17_entry_gate_timing.run_offline, [], {}),
        ("v17_entry_gate_timing.live", v17_entry_gate_timing.run_live, [], {}),
        ("v18_vix_filter.offline", v18_vix_filter.run_offline, [], {}),
        ("v18_vix_filter.live", v18_vix_filter.run_live, [], {}),
        ("v19_profit_lock.offline", v19_profit_lock.run_offline, [], {}),
        ("v19_profit_lock.live", v19_profit_lock.run_live, [], {}),
        ("v20_strike_selection.offline", v20_strike_selection.run_offline, [], {}),
        ("v20_strike_selection.live", v20_strike_selection.run_live, [], {}),
        ("v21_kill_switch.offline", v21_kill_switch.run_offline, [], {}),
        ("v21_kill_switch.live", v21_kill_switch.run_live, [], {}),
        ("v22_chart_patterns.offline", v22_chart_patterns.run_offline, [], {}),
        ("v22_chart_patterns.live", v22_chart_patterns.run_live, [], {}),
        ("v23_orb_warmup.offline", v23_orb_warmup.run_offline, [], {}),
        ("v23_orb_warmup.live", v23_orb_warmup.run_live, [], {}),
        ("v24_runner_invariants.offline", v24_runner_invariants.run_offline, [], {}),
        ("v24_runner_invariants.live", v24_runner_invariants.run_live, [], {}),
        ("v25_filter_gates.offline", v25_filter_gates.run_offline, [], {}),
        ("v25_filter_gates.live", v25_filter_gates.run_live, [], {}),
        ("v26_ghost_entry_detection.offline", v26_ghost_entry_detection.run_offline, [], {}),
        ("v26_ghost_entry_detection.live", v26_ghost_entry_detection.run_live, [], {}),
        ("v27_stale_cache_detection.offline", v27_stale_cache_detection.run_offline, [], {}),
        ("v27_stale_cache_detection.live", v27_stale_cache_detection.run_live, [], {}),
        ("v28_nlwb_bounce_gate.offline", v28_nlwb_bounce_gate.run_offline, [], {}),
        ("v28_nlwb_bounce_gate.live", v28_nlwb_bounce_gate.run_live, [], {}),
        ("v29_db_base_quiet_gate.offline", v29_db_base_quiet_gate.run_offline, [], {}),
        ("v29_db_base_quiet_gate.live", v29_db_base_quiet_gate.run_live, [], {}),
        ("v30_db_morning_low_vol_gate.offline", v30_db_morning_low_vol_gate.run_offline, [], {}),
        ("v30_db_morning_low_vol_gate.live", v30_db_morning_low_vol_gate.run_live, [], {}),
        ("v31_momentum_accel_highvol_gate.offline", v31_momentum_accel_highvol_gate.run_offline, [], {}),
        ("v31_momentum_accel_highvol_gate.live", v31_momentum_accel_highvol_gate.run_live, [], {}),
        ("v32_db_base_quiet_gate.offline", v32_db_base_quiet_gate.run_offline, [], {}),
        ("v32_db_base_quiet_gate.live", v32_db_base_quiet_gate.run_live, [], {}),
        ("v33_close_ceiling_detection.offline", v33_close_ceiling_detection.run_offline, [], {}),
        ("v33_close_ceiling_detection.live", v33_close_ceiling_detection.run_live, [], {}),
        ("v34_ceiling_floor_watcher_gate.offline", v34_ceiling_floor_watcher_gate.run_offline, [], {}),
        ("v34_ceiling_floor_watcher_gate.live", v34_ceiling_floor_watcher_gate.run_live, [], {}),
        ("v35_v14e_bear_only_gate.offline", v35_v14e_bear_only_gate.run_offline, [], {}),
        ("v35_v14e_bear_only_gate.live", v35_v14e_bear_only_gate.run_live, [], {}),
        ("v36_orb_narrow_or_gate.offline", v36_orb_narrow_or_gate.run_offline, [], {}),
        ("v36_orb_narrow_or_gate.live", v36_orb_narrow_or_gate.run_live, [], {}),
        ("v37_tbr_high_vol_gate.offline", v37_tbr_high_vol_gate.run_offline, [], {}),
        ("v37_tbr_high_vol_gate.live", v37_tbr_high_vol_gate.run_live, [], {}),
        ("v38_v14e_chop_zone_gate.offline", v38_v14e_chop_zone_gate.run_offline, [], {}),
        ("v38_v14e_chop_zone_gate.live", v38_v14e_chop_zone_gate.run_live, [], {}),
        ("v39_orb_signal_reader.offline", v39_orb_signal_reader.run_offline, [], {}),
        ("v39_orb_signal_reader.live", v39_orb_signal_reader.run_live, [], {}),
        ("v40_bearish_rejection_morning_gate.offline", v40_bearish_rejection_morning_gate.run_offline, [], {}),
        ("v40_bearish_rejection_morning_gate.live", v40_bearish_rejection_morning_gate.run_live, [], {}),
        ("v41_midday_trendline_gate.offline", v41_midday_trendline_gate.run_offline, [], {}),
        ("v41_midday_trendline_gate.live", v41_midday_trendline_gate.run_live, [], {}),
        ("v42_sizing_risk_cap_guard.offline", v42_sizing_risk_cap_guard.run_offline, [], {}),
        ("v42_sizing_risk_cap_guard.live", v42_sizing_risk_cap_guard.run_live, [], {}),
        ("v43_ghost_entry_dual_account.offline", v43_ghost_entry_dual_account.run_offline, [], {}),
        ("v43_ghost_entry_dual_account.live", v43_ghost_entry_dual_account.run_live, [], {}),
        ("v44_named_level_second_test_gate.offline", v44_named_level_second_test_gate.run_offline, [], {}),
        ("v44_named_level_second_test_gate.live", v44_named_level_second_test_gate.run_live, [], {}),
        ("v45_stairstep_continuation_gate.offline", v45_stairstep_continuation_gate.run_offline, [], {}),
        ("v45_stairstep_continuation_gate.live", v45_stairstep_continuation_gate.run_live, [], {}),
        ("v46_market_structure.offline", v46_market_structure.run_offline, [], {}),
        ("v46_market_structure.live", v46_market_structure.run_live, [args.symbol, args.granularity, args.count], {}),
        ("v47_chart_read.offline", v47_chart_read.run_offline, [], {}),
        ("v47_chart_read.live", v47_chart_read.run_live, [], {}),
        ("v48_double_top_gate.offline", v48_double_top_gate.run_offline, [], {}),
        ("v48_double_top_gate.live", v48_double_top_gate.run_live, [], {}),
        ("v49_market_structure_watcher_gate.offline", v49_market_structure_watcher_gate.run_offline, [], {}),
        ("v49_market_structure_watcher_gate.live", v49_market_structure_watcher_gate.run_live, [], {}),
        ("v50_confluence.offline", v50_confluence.run_offline, [], {}),
        ("v50_confluence.live", v50_confluence.run_live, [], {}),
    ]
    if not args.skip_replay:
        stages.append((
            "benchmark.replay_5_14", replay_5_14.replay,
            [Path("backtest/data/spy_5m_2026-05-08_2026-05-14.csv"),
             Path("automation/state/r4-tick-divergence-2026-05-14.csv")],
            {},
        ))

    for name, fn, ag, kw in stages:
        r = _run(name, fn, *ag, **kw)
        runs.append(r)
        ok = _verdict(r)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}")
        if not r["ok"]:
            print(f"         error: {r.get('error','?')}")

    finished = datetime.now(timezone.utc).isoformat()
    # overall_pass excludes known-flaky live-source parity validators (timing jitter).
    non_flaky_runs = [r for r in runs if r["name"] not in KNOWN_FLAKY_LIVE_SOURCE]
    overall_ok = all(_verdict(r) for r in non_flaky_runs)
    flaky_failed = [r["name"] for r in runs
                    if r["name"] in KNOWN_FLAKY_LIVE_SOURCE and not _verdict(r)]

    summary = {
        "started_at": started,
        "finished_at": finished,
        "symbol": args.symbol,
        "granularity_seconds": args.granularity,
        "stages": len(runs),
        "passed": sum(1 for r in runs if _verdict(r)),
        "failed": sum(1 for r in non_flaky_runs if not _verdict(r)),
        "flaky_failed": flaky_failed,
        "overall_pass": overall_ok,
        "per_stage": {r["name"]: _verdict(r) for r in runs},
    }
    if not args.skip_replay:
        replay_run = next((r for r in runs if r["name"] == "benchmark.replay_5_14"), None)
        if replay_run and replay_run["ok"]:
            res = replay_run["result"]
            summary["benchmark_5_14"] = {
                "live_trading_ticks": res["total_live_trading_ticks"],
                "OLD_error_rate_pct": res["OLD_logic"]["error_rate_pct"],
                "NEW_error_rate_pct": res["NEW_logic_crypto_bar_reader"]["error_rate_pct"],
                "critical_misread_OLD": res["critical_decisions_misread_by_old"],
                "critical_misread_NEW": res["critical_decisions_misread_by_new"],
                "improvement": res["improvement_multiplier"],
            }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "latest.json").write_text(json.dumps({"summary": summary, "runs": runs}, indent=2, default=str))
    with (args.out_dir / "history.jsonl").open("a") as f:
        f.write(json.dumps(summary, default=str) + "\n")

    print()
    print("=" * 70)
    flaky_note = f"  ({len(flaky_failed)} known-flaky excluded)" if flaky_failed else ""
    print(f"SUMMARY: passed={summary['passed']}/{summary['stages']}  overall_pass={overall_ok}{flaky_note}")
    if "benchmark_5_14" in summary:
        b = summary["benchmark_5_14"]
        print(f"5/14 REPLAY: OLD err {b['OLD_error_rate_pct']}%  -->  NEW err {b['NEW_error_rate_pct']}%")
        print(f"             critical misread OLD={b['critical_misread_OLD']}  NEW={b['critical_misread_NEW']}")
    print(f"  scorecard: {args.out_dir / 'latest.json'}")
    print(f"  history:   {args.out_dir / 'history.jsonl'}")
    print("=" * 70)

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
