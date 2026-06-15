"""Backtest orchestrator entry point.

Usage:
    python run.py --start 2026-03-15 --end 2026-05-07
    python run.py --start 2026-03-15 --end 2026-05-07 --disable-filters 8 9   (historical-regime mode)
    python run.py --start 2026-03-15 --end 2026-05-07 --label production_rules

Output: analysis/backtests/{label}/
    trades.csv      — trades.csv-compatible per-trade rows
    decisions.csv   — per-bar filter scores
    summary.md      — hit rate, expectancy, drawdown, by_iv_regime, by_tod_bucket
    metadata.json   — run config + run timestamp
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from lib.orchestrator import run_backtest
from lib.repro import compute_run_id, write_registry_entry


REPO = Path(__file__).resolve().parent
ANALYSIS_DIR = REPO.parent / "analysis" / "backtests"
DATA_DIR = REPO / "data"


# ---------- helpers for output formatting ----------

def _tod_bucket(t: dt.time) -> str:
    if t < dt.time(10, 15):
        return "OPEN_DRIVE"
    if t < dt.time(11, 30):
        return "MORNING"
    if t < dt.time(14, 0):
        return "MIDDAY"
    if t < dt.time(15, 15):
        return "AFTERNOON"
    return "POWER_HOUR"


def _iv_regime(vix: float) -> str:
    if vix < 15:
        return "LOW"
    if vix <= 22:
        return "MID"
    return "HIGH"


def _trade_to_csv_row(t) -> dict:
    return {
        "date": t.entry_time_et.date().isoformat(),
        "time_entry": t.entry_time_et.strftime("%H:%M:%S"),
        "time_exit": t.runner_exit_time_et.strftime("%H:%M:%S") if t.runner_exit_time_et else "",
        "setup": t.setup,
        "contract": f"SPY {t.entry_time_et.date().isoformat()} {t.strike}{'C' if 'BULLISH' in t.setup else 'P'}",
        "dte": 0,
        "strike": t.strike,
        "c_or_p": "C" if "BULLISH" in t.setup else "P",
        "qty": t.qty,
        "entry_px": round(t.entry_premium, 2),
        "exit_px": round(t.runner_exit_premium, 2) if t.runner_exit_premium else "",
        "tp1_px": round(t.tp1_premium, 2) if t.tp1_premium else "",
        "premium_paid": round(t.entry_premium * t.qty * 100, 2),
        "dollar_pnl": round(t.dollar_pnl, 2),
        "pct_return_on_premium": round(t.pct_return_on_premium, 4),
        "exit_reason": t.exit_reason.value if t.exit_reason else "",
        "rejection_level": round(t.rejection_level, 2) if t.rejection_level is not None else "",
        "triggers_fired": "|".join(t.triggers_fired),
        "delta_at_entry": round(t.entry_delta, 4),
        "iv_at_entry": round(t.entry_iv, 4),
        "iv_regime": _iv_regime(t.entry_vix),
        "vix_at_entry": round(t.entry_vix, 2),
        "tod_bucket": _tod_bucket(t.entry_time_et.time()),
        "hold_minutes": t.hold_minutes,
        "bars_held": t.bars_held,
        "max_adverse_premium": round(t.max_adverse_premium, 2),
        "max_favorable_premium": round(t.max_favorable_premium, 2),
    }


def _decision_to_csv_row(d) -> dict:
    return {
        "timestamp_et": pd.Timestamp(d["timestamp_et"]).isoformat(),
        "spy_close": d["spy_close"],
        "vix": d["vix"],
        "ribbon_stack": d["ribbon_stack"],
        "ribbon_spread_cents": d["ribbon_spread_cents"],
        "htf_15m_stack": d["htf_15m_stack"],
        "bear_score": d["bear_score"],
        "blockers": "|".join(map(str, d["blockers"])),
        "triggers_fired": "|".join(d["triggers_fired"]),
        "rejection_level": d["rejection_level"] or "",
        "passed": d["passed"],
    }


def _compute_summary(trades: list, decisions: list, args) -> str:
    n_trades = len(trades)
    if n_trades == 0:
        return _summary_no_trades(decisions, args)

    n_winners = sum(1 for t in trades if t.dollar_pnl > 0)
    n_losers = sum(1 for t in trades if t.dollar_pnl < 0)
    n_flat = n_trades - n_winners - n_losers
    hit_rate = n_winners / n_trades if n_trades else 0
    total_pnl = sum(t.dollar_pnl for t in trades)
    avg_pnl = total_pnl / n_trades
    avg_winner = sum(t.dollar_pnl for t in trades if t.dollar_pnl > 0) / max(1, n_winners)
    avg_loser = sum(t.dollar_pnl for t in trades if t.dollar_pnl < 0) / max(1, n_losers)
    avg_return_pct = sum(t.pct_return_on_premium for t in trades) / n_trades
    avg_hold_min = sum(t.hold_minutes for t in trades) / n_trades

    # Drawdown — peak-to-trough on equity curve. Normalize entry_time to TZ-naive
    # for sorting (real-fills sim returns naive, BS sim returns TZ-aware Timestamps).
    def _naive(ts):
        if hasattr(ts, "tz_localize") and ts.tz is not None:
            return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts
    cum = 0
    peak = 0
    max_dd = 0
    for t in sorted(trades, key=lambda t: _naive(t.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    # Distributions
    by_iv = Counter()
    by_tod = Counter()
    by_exit = Counter()
    for t in trades:
        by_iv[_iv_regime(t.entry_vix)] += 1
        by_tod[_tod_bucket(t.entry_time_et.time())] += 1
        by_exit[t.exit_reason.value if t.exit_reason else "NONE"] += 1

    # Random baseline (rough): random tick to +/-30% premium swing within 30 min
    n_bars = len(decisions)
    n_decision_bars = sum(1 for d in decisions if d["bear_score"] >= 7)

    lines = []
    lines.append(f"# Backtest Summary — {args.label}\n")
    lines.append(f"**Window:** {args.start} to {args.end}")
    lines.append(f"**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON")
    lines.append(f"**Filters disabled:** {args.disable_filters or 'none (full production rules)'}")
    lines.append(f"**Run at:** {dt.datetime.now().isoformat(timespec='seconds')}\n")

    lines.append("## Top-line numbers\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    n_days = len(set(pd.Timestamp(d["timestamp_et"]).date() for d in decisions))
    lines.append(f"| Trading days in window | {n_days} |")
    lines.append(f"| Bars evaluated | {n_bars:,} |")
    lines.append(f"| High-score bars (≥7/10) | {n_decision_bars} |")
    lines.append(f"| **Trades fired** | **{n_trades}** |")
    lines.append(f"| Winners | {n_winners} ({hit_rate*100:.0f}%) |")
    lines.append(f"| Losers | {n_losers} |")
    lines.append(f"| Total P&L (3 contracts each) | **${total_pnl:.0f}** |")
    lines.append(f"| Avg P&L / trade | ${avg_pnl:.0f} |")
    lines.append(f"| Avg winner | ${avg_winner:.0f} |")
    lines.append(f"| Avg loser | ${avg_loser:.0f} |")
    lines.append(f"| Avg return on premium | {avg_return_pct*100:.1f}% |")
    lines.append(f"| Avg hold | {avg_hold_min:.0f} min |")
    lines.append(f"| Max drawdown (sequential) | ${max_dd:.0f} |")
    lines.append(f"| Win/loss ratio | {abs(avg_winner/avg_loser):.2f}x |" if avg_loser else "| Win/loss ratio | n/a (no losers) |")

    expectancy = (hit_rate * avg_winner) + ((1 - hit_rate) * avg_loser)
    lines.append(f"| Expectancy per trade | ${expectancy:.0f} |\n")

    lines.append("## By IV regime\n")
    lines.append(f"| Regime | Trades |")
    lines.append(f"|---|---|")
    for r in ["LOW", "MID", "HIGH"]:
        lines.append(f"| {r} | {by_iv.get(r, 0)} |")
    lines.append("")

    lines.append("## By time-of-day bucket\n")
    lines.append(f"| Bucket | Trades |")
    lines.append(f"|---|---|")
    for r in ["OPEN_DRIVE", "MORNING", "MIDDAY", "AFTERNOON", "POWER_HOUR"]:
        lines.append(f"| {r} | {by_tod.get(r, 0)} |")
    lines.append("")

    lines.append("## By exit reason\n")
    lines.append(f"| Reason | Count |")
    lines.append(f"|---|---|")
    for k, v in sorted(by_exit.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Live deployment threshold check
    lines.append("## Live deployment threshold check\n")
    lines.append(f"| Threshold | Required | Actual | Status |")
    lines.append(f"|---|---|---|---|")
    lines.append(f"| Logged trades | ≥ 20 | {n_trades} | {'PASS' if n_trades >= 20 else 'FAIL'} |")
    lines.append(f"| Win rate | ≥ 45% | {hit_rate*100:.0f}% | {'PASS' if hit_rate >= 0.45 else 'FAIL'} |")
    avg_w_l_ratio = abs(avg_winner / avg_loser) if avg_loser else float('inf')
    lines.append(f"| Avg W/L ratio | ≥ 1.5x | {avg_w_l_ratio:.2f}x | {'PASS' if avg_w_l_ratio >= 1.5 else 'FAIL'} |")
    lines.append(f"| Expectancy / trade | > 0 | ${expectancy:.0f} | {'PASS' if expectancy > 0 else 'FAIL'} |")
    lines.append("")

    # Caveats — be honest about model limitations
    lines.append("## Caveats\n")
    if getattr(args, "real_fills", False):
        lines.append("- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.")
    else:
        lines.append("- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.")
    lines.append("- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.")
    lines.append("- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.")
    lines.append("- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.")
    lines.append("- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.")
    return "\n".join(lines)


def _summary_no_trades(decisions: list, args) -> str:
    n_bars = len(decisions)
    high_score = [d for d in decisions if d["bear_score"] >= 7]
    score_8_plus = [d for d in decisions if d["bear_score"] >= 8]
    score_9_plus = [d for d in decisions if d["bear_score"] >= 9]

    blocker_counter = Counter()
    for d in high_score:
        for b in d["blockers"]:
            blocker_counter[b] += 1

    lines = []
    lines.append(f"# Backtest Summary — {args.label}\n")
    lines.append(f"**Window:** {args.start} to {args.end}")
    lines.append(f"**Filters disabled:** {args.disable_filters or 'none (full production rules)'}")
    lines.append(f"**Run at:** {dt.datetime.now().isoformat(timespec='seconds')}\n")

    lines.append("## ZERO trades fired\n")
    lines.append(f"The engine evaluated **{n_bars:,} bars** over the window and didn't find a single setup that passed all filters.\n")
    lines.append("This is a critical finding. Either:\n")
    lines.append("1. The current rules are calibrated to a regime that didn't appear in this window, or")
    lines.append("2. The rules are too strict and would never fire in any realistic market, or")
    lines.append("3. The setup type (BEARISH_REJECTION) requires conditions that didn't align over 53 trading days.\n")

    lines.append("## High-score bars (>= 7/10)\n")
    lines.append(f"- **Total:** {len(high_score)}")
    lines.append(f"- **Score 8+:** {len(score_8_plus)}")
    lines.append(f"- **Score 9+:** {len(score_9_plus)}\n")

    lines.append("## Top blocking filters on near-misses (score >= 7/10)\n")
    lines.append(f"| Filter # | Times blocked |")
    lines.append(f"|---|---|")
    for f, count in sorted(blocker_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| {f} | {count} |")
    lines.append("")
    lines.append("Filter reference (per heartbeat.md):")
    lines.append("- 1: time ≥ 09:35 ET")
    lines.append("- 5: ribbon BEAR-stacked")
    lines.append("- 6: ribbon spread ≥ 30¢")
    lines.append("- 7: NOT volume_divergence_failed")
    lines.append("- 8: VIX > 17.30 AND rising  ← added 2026-05-05")
    lines.append("- 9: breakdown_bar_bearish (close < Fast EMA, body in lower 40%, vol 1.3x)")
    lines.append("- 10: HTF aligned + ≥2 of 3 triggers (level_reject / ribbon_flip / confluence)\n")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    ap.add_argument("--label", default=None, help="Output folder label (default: derived from dates)")
    ap.add_argument("--disable-filters", type=int, nargs="*", default=[],
                    help="Filter IDs to disable (e.g., 8 9 for historical regime)")
    ap.add_argument("--real-fills", action="store_true",
                    help="Use real OPRA option bars from data/options/ instead of Black-Scholes")
    args = ap.parse_args()

    if args.label is None:
        suffix = "_no_filter_" + "_".join(map(str, sorted(args.disable_filters))) if args.disable_filters else ""
        args.label = f"{args.start}_{args.end}{suffix}"

    # Locate the smallest CSV that fully covers [start, end]. Fall back to the
    # master 2025-01-01..2026-05-07 file if no exact match exists. Mirrors
    # autoresearch.runner.load_data so any window can be backtested without
    # pre-fetching a per-window CSV.
    candidates = [
        (args.start, args.end),
        ("2025-01-01", "2026-05-07"),
    ]
    spy_path = vix_path = None
    for cs, ce in candidates:
        sp = DATA_DIR / f"spy_5m_{cs}_{ce}.csv"
        vp = DATA_DIR / f"vix_5m_{cs}_{ce}.csv"
        if sp.exists() and vp.exists():
            spy_path, vix_path = sp, vp
            break
    if spy_path is None:
        print(f"ERROR: no SPY/VIX csv covers {args.start}..{args.end} in {DATA_DIR}")
        print(f"       run: python tools/fetch_data.py --start {args.start} --end {args.end}")
        return 1

    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    # Filter to requested window if we fell back to a wider master file.
    spy = spy[(spy["timestamp_et"] >= args.start) & (spy["timestamp_et"] < f"{args.end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= args.start) & (vix["timestamp_et"] < f"{args.end}T23:59:59")].reset_index(drop=True)

    print(f"Running backtest: {args.start} to {args.end}")
    print(f"  SPY bars: {len(spy):,}  VIX bars: {len(vix):,}")
    print(f"  Disabled filters: {args.disable_filters or 'none'}")

    result = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(args.start),
        end_date=dt.date.fromisoformat(args.end),
        disable_filters=args.disable_filters or None,
        use_real_fills=args.real_fills,
    )

    print(f"\nResult: {result.metadata['trades_fired']} trades fired, "
          f"{result.metadata['bars_evaluated']:,} bars evaluated")

    out_dir = ANALYSIS_DIR / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write trades.csv
    trades_csv = out_dir / "trades.csv"
    if result.trades:
        df = pd.DataFrame([_trade_to_csv_row(t) for t in result.trades])
        df.to_csv(trades_csv, index=False)
        print(f"  trades.csv:  {trades_csv} ({len(df)} rows)")
    else:
        # Empty file for downstream consistency
        trades_csv.write_text("date,time_entry,time_exit,setup,contract,strike,qty,entry_px,exit_px,dollar_pnl,exit_reason\n")
        print(f"  trades.csv:  empty (no trades)")

    # Write decisions.csv
    decisions_csv = out_dir / "decisions.csv"
    if result.decisions:
        df = pd.DataFrame([_decision_to_csv_row(d) for d in result.decisions])
        df.to_csv(decisions_csv, index=False)
        print(f"  decisions.csv: {decisions_csv} ({len(df)} rows)")

    # Write summary.md
    summary = _compute_summary(result.trades, result.decisions, args)
    summary_md = out_dir / "summary.md"
    summary_md.write_text(summary, encoding="utf-8")
    print(f"  summary.md:  {summary_md}")

    # --- Karpathy-method reproducibility layer ---
    # Content-address the run by hashing inputs (data + code + params).
    # Record everything in metadata.json + the rolling REGISTRY.jsonl index.
    identity = compute_run_id(spy_path, vix_path)

    # Compute key summary metrics for registry indexing (avoids re-parsing summary.md)
    summary_metrics: dict = {
        "trades_fired": len(result.trades),
        "bars_evaluated": len(result.decisions),
    }
    if result.trades:
        n = len(result.trades)
        n_w = sum(1 for t in result.trades if t.dollar_pnl > 0)
        n_l = sum(1 for t in result.trades if t.dollar_pnl < 0)
        total = sum(t.dollar_pnl for t in result.trades)
        avg_w = sum(t.dollar_pnl for t in result.trades if t.dollar_pnl > 0) / max(1, n_w)
        avg_l = sum(t.dollar_pnl for t in result.trades if t.dollar_pnl < 0) / max(1, n_l)
        wl_ratio = abs(avg_w / avg_l) if avg_l else float("inf")
        # Sequential drawdown
        cum, peak, max_dd = 0.0, 0.0, 0.0
        def _naive(ts):
            if hasattr(ts, "tz_localize") and getattr(ts, "tz", None) is not None:
                return ts.tz_localize(None)
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                return ts.replace(tzinfo=None)
            return ts
        for t in sorted(result.trades, key=lambda t: _naive(t.entry_time_et)):
            cum += t.dollar_pnl
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)
        hit_rate = n_w / n
        expectancy = (hit_rate * avg_w) + ((1 - hit_rate) * avg_l)
        thresholds = {
            "trades_ge_20": n >= 20,
            "wr_ge_45": hit_rate >= 0.45,
            "wl_ge_15x": wl_ratio >= 1.5,
            "expectancy_gt_0": expectancy > 0,
        }
        summary_metrics.update({
            "hit_rate": round(hit_rate, 4),
            "total_pnl": round(total, 2),
            "expectancy": round(expectancy, 2),
            "max_drawdown": round(max_dd, 2),
            "wl_ratio": round(wl_ratio, 3),
            "thresholds_passed": sum(thresholds.values()),
            "thresholds_total": len(thresholds),
            "thresholds_breakdown": thresholds,
        })

    # Read params snapshot to embed (so a later read of metadata.json shows
    # exactly which values this run used, even if params.json mutates later)
    params_snapshot: dict = {}
    try:
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params_snapshot = json.loads(params_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        params_snapshot = {"_load_error": str(e)}

    metadata = {
        "label": args.label,
        "start": args.start,
        "end": args.end,
        "disable_filters": args.disable_filters,
        "result_metadata": result.metadata,
        "run_at": dt.datetime.now().isoformat(),
        # Karpathy reproducibility layer
        "run_id": identity.run_id,
        "data_hash": identity.data_hash,
        "code_hash": identity.code_hash,
        "code_source": identity.code_source,
        "params_hash": identity.params_hash,
        "spy_bytes": identity.spy_bytes,
        "vix_bytes": identity.vix_bytes,
        "params_snapshot": params_snapshot,
        "summary_metrics": summary_metrics,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Append to the durable registry (append-only ledger of all backtest runs)
    write_registry_entry(identity, args.label, summary_metrics)

    print(f"\nDone. See {out_dir}/summary.md")
    print(f"  run_id: {identity.run_id}")
    print(f"  registered in analysis/backtests/REGISTRY.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
