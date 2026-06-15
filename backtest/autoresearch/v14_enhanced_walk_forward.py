"""Walk-forward validation for the v14_enhanced front-runner combo.

This script (T44c per overnight queue) runs the OP 20 walk-forward OOS gate
on the top combo from `v14_enhanced_real_fills.py` (T44b PASS).

Splits the historical window into:
  TRAIN: 2025-01-01 to 2025-12-31 (12 months — optimizer saw this)
  TEST:  2026-01-01 to 2026-05-12 (~4.4 months — TRULY out of sample
         for the wide-window optimizer, though J-anchors in this window
         (4/29..5/12) were used for floor protection)

Per CLAUDE.md OP 20 walk-forward gate, the combo is "Monday ready" only if:
  - TEST P&L > 0 (positive OOS dollars)
  - test_pnl_per_month >= 0.5 * train_pnl_per_month (no major regime decay)

Real-fills mode (use_real_fills=True) mirrors T44b's environment:
  - profit_lock_threshold_pct=0.05 / profit_lock_stop_offset_pct=0.10
    (NO-OP in real-fills — see caveat #1 in T44b)
  - tp1_premium_pct / runner_target_premium_pct / tp1_qty_fraction patched
    into simulator_real's module-level constants (same pattern T44b uses)

Outputs:
  analysis/recommendations/v14_enhanced-walkforward.json
  docs/V14_ENHANCED-WALK-FORWARD-2026-05-13.md

CLI:
  python backtest/autoresearch/v14_enhanced_walk_forward.py
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from lib import simulator_real as _sim_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

TRAIN_START = dt.date(2025, 1, 1)
TRAIN_END = dt.date(2025, 12, 31)
TEST_START = dt.date(2026, 1, 1)
TEST_END = dt.date(2026, 5, 12)

OUT_JSON = ROOT / "analysis" / "recommendations" / "v14_enhanced-walkforward.json"
OUT_MD = ROOT / "docs" / "V14_ENHANCED-WALK-FORWARD-2026-05-13.md"
T44B_DOC = ROOT / "docs" / "V14_ENHANCED-REAL-FILLS-2026-05-13.md"

# TOP COMBO #1 from T44b (this evening 17:49 ET) — passed all 4 gates with
# real wide_pnl $36,450 / 4/29 +$869 / 5/12 +$464 / 6/6 quarters / DD $2,857
WINNER_COMBO: dict[str, Any] = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
    "no_trade_before": "09:35",
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
    "tp1_premium_pct": 0.30,
    "runner_target_premium_pct": 2.5,
}


# ── Helpers ──────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _patched_sim_real_constants(
    tp1_premium_pct: float,
    runner_target_premium_pct: float,
    tp1_qty_fraction: float,
) -> Iterator[None]:
    """Temporarily swap simulator_real's module-level exit constants.

    Mirrors T44b's `v14_enhanced_real_fills._patched_sim_real_constants`.
    simulator_real imports TP1_PREMIUM_PCT / RUNNER_MAX_PREMIUM_PCT /
    TP1_QTY_FRACTION from simulator at import time, so they live in
    simulator_real's namespace. Patch + restore.
    """
    saved = {
        "TP1_PREMIUM_PCT": _sim_real.TP1_PREMIUM_PCT,
        "RUNNER_MAX_PREMIUM_PCT": _sim_real.RUNNER_MAX_PREMIUM_PCT,
        "TP1_QTY_FRACTION": _sim_real.TP1_QTY_FRACTION,
    }
    _sim_real.TP1_PREMIUM_PCT = tp1_premium_pct
    _sim_real.RUNNER_MAX_PREMIUM_PCT = runner_target_premium_pct
    _sim_real.TP1_QTY_FRACTION = tp1_qty_fraction
    try:
        yield
    finally:
        _sim_real.TP1_PREMIUM_PCT = saved["TP1_PREMIUM_PCT"]
        _sim_real.RUNNER_MAX_PREMIUM_PCT = saved["RUNNER_MAX_PREMIUM_PCT"]
        _sim_real.TP1_QTY_FRACTION = saved["TP1_QTY_FRACTION"]


def _evaluate_window(
    combo: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    label: str,
) -> dict[str, Any]:
    """Run the combo through real-fills over [start, end] + aggregate metrics.

    Mirrors T44b's `_run_candidate_real_fills` but parameterised by window so
    we can call it twice (TRAIN, TEST). Calls lib.orchestrator.run_backtest
    directly with use_real_fills=True.
    """
    from lib.orchestrator import run_backtest
    from autoresearch import config

    kwargs: dict[str, Any] = {
        "spy_df": spy_df,
        "vix_df": vix_df,
        "start_date": start,
        "end_date": end,
        "use_real_fills": True,
    }
    direct_passthrough = (
        "min_triggers_bear",
        "min_triggers_bull",
        "premium_stop_pct_bear",
        "premium_stop_pct_bull",
        "strike_offset_bear",
        "strike_offset_bull",
        "tp1_premium_pct",
        "tp1_qty_fraction",
        "runner_target_premium_pct",
        "profit_lock_threshold_pct",
        "profit_lock_stop_offset_pct",
        "f9_vol_mult",
    )
    for k in direct_passthrough:
        if k in combo:
            kwargs[k] = combo[k]

    if "no_trade_before" in combo:
        kwargs["no_trade_before"] = config.parse_time(combo["no_trade_before"])

    tp1_pct = combo.get("tp1_premium_pct", 0.30)
    runner_pct = combo.get("runner_target_premium_pct", 3.0)
    tp1_frac = combo.get("tp1_qty_fraction", 2.0 / 3.0)

    log.info(
        "%s: running real-fills %s..%s with combo", label, start, end,
    )
    with _patched_sim_real_constants(tp1_pct, runner_pct, tp1_frac):
        result = run_backtest(**kwargs)

    # Aggregate per-day, per-month, per-quarter
    per_day: dict[str, float] = defaultdict(float)
    per_month: dict[str, float] = defaultdict(float)
    per_quarter: dict[str, float] = defaultdict(float)
    bs_fallback_count = 0
    real_fills_count = 0
    for t in result.trades:
        d = t.entry_time_et.date()
        per_day[d.isoformat()] += t.dollar_pnl
        m = f"{d.year}-{d.month:02d}"
        per_month[m] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        per_quarter[q] += t.dollar_pnl
        if "BS_FALLBACK" in (t.setup or ""):
            bs_fallback_count += 1
        else:
            real_fills_count += 1

    total_pnl = sum(per_day.values())
    n_trades = len(result.trades)
    n_winners = sum(1 for t in result.trades if t.dollar_pnl > 0)
    wr = (n_winners / n_trades) if n_trades else 0.0
    positive_quarters = sum(1 for v in per_quarter.values() if v > 0)
    sorted_day_pnls = sorted(per_day.values(), reverse=True)
    top5_pct = (
        round(sum(sorted_day_pnls[:5]) / total_pnl, 3)
        if total_pnl > 0 else 999.0
    )

    # Sequential drawdown
    sorted_trades = sorted(result.trades, key=lambda t: t.entry_time_et)
    cum = peak = max_dd = 0.0
    for t in sorted_trades:
        cum += t.dollar_pnl
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_pnl": round(total_pnl, 2),
        "n_trades": n_trades,
        "n_winners": n_winners,
        "wr": round(wr, 3),
        "trading_days": len(per_day),
        "monthly_pnl": {k: round(v, 2) for k, v in sorted(per_month.items())},
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(per_quarter.items())},
        "positive_quarters": positive_quarters,
        "quarter_count": len(per_quarter),
        "max_dd": round(max_dd, 2),
        "top5_pct": top5_pct,
        "real_fills_count": real_fills_count,
        "bs_fallback_count": bs_fallback_count,
        "bs_fallback_pct": (
            round(bs_fallback_count / n_trades * 100, 1) if n_trades else 0.0
        ),
    }


def _months_in_window(start: dt.date, end: dt.date) -> float:
    """Approximate months between two dates (fractional)."""
    days = (end - start).days + 1
    return days / 30.4375  # average month length


def _verdict(
    train: dict[str, Any], test: dict[str, Any], ratio: float,
) -> tuple[str, str, list[str]]:
    """Compute walk-forward verdict per OP 20.

    PASS gates (all required):
      - TEST P&L > 0
      - per_month_ratio >= 0.5

    CAVEAT downgrades — note but do not fail:
      - TEST window overlaps J anchors (selection bias call-out)
      - High BS fallback fraction (>20%) in either window
    """
    test_positive = test["total_pnl"] > 0
    ratio_ok = ratio >= 0.5

    caveats: list[str] = []
    # OP 20 disclosure 2: J anchors 4/29..5/12 sit inside the TEST window
    # AND were used for floor protection in the optimizer that produced this
    # combo. Selection bias.
    caveats.append(
        "TEST window overlaps J anchors (4/29..5/12). These days were used "
        "for floor protection in the v14_enhanced grinder, so they are NOT "
        "fully out-of-sample. Per OP 20 disclosure 2 (sample bias)."
    )
    if train.get("bs_fallback_pct", 0) > 20:
        caveats.append(
            f"TRAIN BS-fallback {train['bs_fallback_pct']:.1f}% > 20% — less "
            f"than a true real-fills test for TRAIN."
        )
    if test.get("bs_fallback_pct", 0) > 20:
        caveats.append(
            f"TEST BS-fallback {test['bs_fallback_pct']:.1f}% > 20% — less "
            f"than a true real-fills test for TEST."
        )

    if not test_positive:
        return (
            "FAIL",
            f"TEST P&L ${test['total_pnl']:.0f} <= 0 — strategy fails OOS.",
            caveats,
        )
    if not ratio_ok:
        return (
            "FAIL",
            f"per_month_ratio {ratio:.2f}x < 0.5x floor — serious regime "
            f"decay between TRAIN and TEST.",
            caveats,
        )
    return (
        "PASS",
        f"TEST positive (${test['total_pnl']:.0f}) AND per_month_ratio "
        f"{ratio:.2f}x >= 0.5x floor.",
        caveats,
    )


def _build_markdown_report(payload: dict[str, Any]) -> str:
    """Render the JSON payload as a Markdown document."""
    train = payload["train"]
    test = payload["test"]
    verdict = payload["verdict"]
    verdict_reason = payload["verdict_reason"]
    ratio = payload["per_month_ratio"]
    train_per_mo = payload["train_per_month"]
    test_per_mo = payload["test_per_month"]
    caveats: list[str] = payload.get("caveats", [])

    md: list[str] = []
    md.append("# v14_enhanced Walk-Forward Validation — 2026-05-13")
    md.append("")
    md.append(f"_Generated: {payload['generated_at']}_")
    md.append("")
    md.append(f"**Verdict: {verdict}**")
    md.append("")
    md.append(f"_{verdict_reason}_")
    md.append("")
    md.append("## Context (T44c — the OOS gate)")
    md.append("")
    md.append(
        "T44b real-fills test (this evening 17:49 ET) PASSED all 3/3 "
        "candidates over the wide window. Top combo (this script's WINNER): "
        "`stop=-0.20, PL=0.05/0.10, no_trade=09:35, tp1=0.30, runner=2.5, "
        "tp1_qty_fraction=0.5, strike_offset_bear=0` → real wide_pnl "
        "$36,450 / 4/29 +$869 / 5/12 +$464 / 6/6 quarters / DD $2,857."
    )
    md.append("")
    md.append(
        "T44c (this script) is the OOS gate per CLAUDE.md OP 20 disclosure 3: "
        "split data into TRAIN (2025-01-01 → 2025-12-31, 12 months — "
        "optimizer saw this) and TEST (2026-01-01 → 2026-05-12, ~4.4 months "
        "— held out from wide-window optimizer; J-anchors used only for "
        "floor protection). Run BOTH on the same combo and compare per-month "
        "normalized P&L."
    )
    md.append("")
    md.append("## Windows")
    md.append("")
    md.append(
        f"- **TRAIN:** {TRAIN_START} to {TRAIN_END}  "
        f"({_months_in_window(TRAIN_START, TRAIN_END):.1f} months — "
        f"optimizer saw this)"
    )
    md.append(
        f"- **TEST:**  {TEST_START} to {TEST_END}  "
        f"({_months_in_window(TEST_START, TEST_END):.1f} months — "
        f"held out from wide-window optimizer; J-anchors used only for "
        f"floor protection)"
    )
    md.append("")
    md.append("## Headline numbers")
    md.append("")
    md.append("| Metric | TRAIN | TEST |")
    md.append("|---|---|---|")
    md.append(
        f"| Total P&L | ${train['total_pnl']:,.0f} | "
        f"${test['total_pnl']:,.0f} |"
    )
    md.append(f"| Trades | {train['n_trades']} | {test['n_trades']} |")
    md.append(
        f"| Win rate | {train['wr'] * 100:.1f}% | "
        f"{test['wr'] * 100:.1f}% |"
    )
    md.append(
        f"| Per-month P&L | ${train_per_mo:,.0f} | ${test_per_mo:,.0f} |"
    )
    md.append(
        f"| Max drawdown | ${train['max_dd']:,.0f} | "
        f"${test['max_dd']:,.0f} |"
    )
    md.append(
        f"| Top-5 day concentration | "
        f"{train['top5_pct'] * 100:.1f}% | "
        f"{test['top5_pct'] * 100:.1f}% |"
    )
    md.append(
        f"| Positive quarters | {train['positive_quarters']}/"
        f"{train['quarter_count']} | {test['positive_quarters']}/"
        f"{test['quarter_count']} |"
    )
    md.append(
        f"| BS-fallback % | {train['bs_fallback_pct']:.1f}% | "
        f"{test['bs_fallback_pct']:.1f}% |"
    )
    md.append("")
    md.append(f"**Per-month ratio (test / train): {ratio:.2f}x**")
    md.append("")
    md.append("## Monthly breakdown (per-month P&L)")
    md.append("")
    md.append("| Month | P&L |")
    md.append("|---|---|")
    all_months = sorted(
        set(train["monthly_pnl"].keys()) | set(test["monthly_pnl"].keys())
    )
    for m in all_months:
        train_m = train["monthly_pnl"].get(m, 0.0)
        test_m = test["monthly_pnl"].get(m, 0.0)
        total_m = train_m + test_m
        md.append(f"| {m} | ${total_m:+,.0f} |")
    md.append("")
    md.append("## Quarter breakdown")
    md.append("")
    md.append("| Quarter | P&L |")
    md.append("|---|---|")
    all_q = sorted(
        set(train["quarter_pnl"].keys()) | set(test["quarter_pnl"].keys())
    )
    for q in all_q:
        train_q = train["quarter_pnl"].get(q, 0.0)
        test_q = test["quarter_pnl"].get(q, 0.0)
        total_q = train_q + test_q
        md.append(f"| {q} | ${total_q:+,.0f} |")
    md.append("")
    md.append("## Interpretation (per CLAUDE.md OP 20 walk-forward gate)")
    md.append("")
    md.append("- **Per-month ratio > 0.7x** = strategy generalizes well to OOS")
    md.append("- **Per-month ratio 0.5–0.7x** = mild overfit, still trade-worthy")
    md.append("- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)")
    md.append("- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)")
    md.append("")
    md.append("## Winner combo (the params tested)")
    md.append("")
    md.append("```json")
    md.append(json.dumps(payload["winner_combo"], indent=2))
    md.append("```")
    md.append("")
    md.append("## Caveats (OP 20 disclosures)")
    md.append("")
    for cav in caveats:
        md.append(f"- {cav}")
    md.append(
        "- Profit-lock NO-OP in real-fills (simulator_real does not implement "
        "it). T44b documented this; same caveat applies here."
    )
    md.append(
        "- Per-quality exit-knob matrix NO-OP in real-fills (uniform exits "
        "across qualities). T44b documented this; same caveat applies here."
    )
    md.append(
        "- Per-month normalized is the honest metric because TRAIN is 12 "
        "months and TEST is ~4.4 months — naive dollar ratios mislead."
    )
    md.append("")
    md.append("## Provenance")
    md.append("")
    md.append("- Script: `backtest/autoresearch/v14_enhanced_walk_forward.py`")
    md.append(
        "- Real-fills runner: `lib.orchestrator.run_backtest(use_real_fills=True)`"
    )
    md.append(
        "- Module-level exit-knob patch: "
        "`_patched_sim_real_constants` (mirrors T44b)"
    )
    md.append("- T44b reference: `docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md`")
    md.append("")
    return "\n".join(md)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    log.info("=" * 70)
    log.info("v14_enhanced WALK-FORWARD validation (T44c — OOS gate)")
    log.info("=" * 70)
    log.info("WINNER_COMBO: %s", WINNER_COMBO)
    log.info("TRAIN window: %s .. %s", TRAIN_START, TRAIN_END)
    log.info("TEST  window: %s .. %s", TEST_START, TEST_END)

    log.info("Loading data %s .. %s", TRAIN_START, TEST_END)
    spy_full, vix_full = _runner.load_data(TRAIN_START, TEST_END)
    # Normalize timestamps to tz-naive ET — same fix T44b uses
    spy_full["timestamp_et"] = (
        pd.to_datetime(spy_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    vix_full["timestamp_et"] = (
        pd.to_datetime(vix_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    log.info(
        "Loaded: SPY %d bars, VIX %d bars (tz-normalized to ET)",
        len(spy_full), len(vix_full),
    )

    try:
        log.info("─" * 60)
        log.info("Evaluating TRAIN window...")
        train = _evaluate_window(
            WINNER_COMBO, spy_full, vix_full, TRAIN_START, TRAIN_END, "TRAIN",
        )
        log.info(
            "TRAIN: pnl=$%.0f / trades=%d / wr=%.1f%% / +q=%d/%d / dd=$%.0f / "
            "fallback=%.1f%%",
            train["total_pnl"], train["n_trades"], train["wr"] * 100,
            train["positive_quarters"], train["quarter_count"],
            train["max_dd"], train["bs_fallback_pct"],
        )
    except Exception as exc:
        log.exception("TRAIN evaluation failed")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({
            "rule_id": "v14_enhanced",
            "generated_at": dt.datetime.now().isoformat(),
            "winner_combo": WINNER_COMBO,
            "verdict": "ERROR",
            "verdict_reason": f"TRAIN failed: {exc!r}",
            "trace": traceback.format_exc(),
        }, indent=2, default=str), encoding="utf-8")
        return 1

    try:
        log.info("─" * 60)
        log.info("Evaluating TEST window...")
        test = _evaluate_window(
            WINNER_COMBO, spy_full, vix_full, TEST_START, TEST_END, "TEST",
        )
        log.info(
            "TEST:  pnl=$%.0f / trades=%d / wr=%.1f%% / +q=%d/%d / dd=$%.0f / "
            "fallback=%.1f%%",
            test["total_pnl"], test["n_trades"], test["wr"] * 100,
            test["positive_quarters"], test["quarter_count"],
            test["max_dd"], test["bs_fallback_pct"],
        )
    except Exception as exc:
        log.exception("TEST evaluation failed")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({
            "rule_id": "v14_enhanced",
            "generated_at": dt.datetime.now().isoformat(),
            "winner_combo": WINNER_COMBO,
            "train": train,
            "verdict": "ERROR",
            "verdict_reason": f"TEST failed: {exc!r}",
            "trace": traceback.format_exc(),
        }, indent=2, default=str), encoding="utf-8")
        return 1

    train_months = _months_in_window(TRAIN_START, TRAIN_END)
    test_months = _months_in_window(TEST_START, TEST_END)
    train_per_mo = train["total_pnl"] / train_months if train_months else 0.0
    test_per_mo = test["total_pnl"] / test_months if test_months else 0.0
    ratio = (test_per_mo / train_per_mo) if train_per_mo > 0 else 0.0

    verdict, verdict_reason, caveats = _verdict(train, test, ratio)

    payload: dict[str, Any] = {
        "rule_id": "v14_enhanced",
        "generated_at": dt.datetime.now().isoformat(),
        "winner_combo": WINNER_COMBO,
        "train_window": f"{TRAIN_START} to {TRAIN_END}",
        "train_months": round(train_months, 2),
        "test_window": f"{TEST_START} to {TEST_END}",
        "test_months": round(test_months, 2),
        "train_per_month": round(train_per_mo, 2),
        "test_per_month": round(test_per_mo, 2),
        "per_month_ratio": round(ratio, 3),
        "train": train,
        "test": test,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "monday_ready": verdict == "PASS",
        "caveats": caveats,
        "thresholds": {
            "test_positive_required": True,
            "test_per_month_min_ratio": 0.5,
            "policy_reference": "CLAUDE.md OP 20 walk-forward gate",
        },
        "provenance": {
            "t44b_doc": "docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md",
            "real_fills": True,
            "profit_lock_in_real_fills": False,
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8",
    )
    log.info("Wrote JSON: %s", OUT_JSON)

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(_build_markdown_report(payload), encoding="utf-8")
    log.info("Wrote MD:   %s", OUT_MD)

    # If PASS, append a one-liner to T44b doc
    if verdict == "PASS" and T44B_DOC.exists():
        try:
            existing = T44B_DOC.read_text(encoding="utf-8")
            stamp = (
                f"\n\n---\n\n**Walk-forward verdict: PASS** "
                f"(T44c, {dt.datetime.now().isoformat()}) — "
                f"TRAIN ${train['total_pnl']:,.0f} ({train['n_trades']} trades, "
                f"{train_per_mo:,.0f}/mo) vs TEST ${test['total_pnl']:,.0f} "
                f"({test['n_trades']} trades, {test_per_mo:,.0f}/mo). "
                f"Per-month ratio: {ratio:.2f}x (>= 0.5x floor). "
                f"See `docs/V14_ENHANCED-WALK-FORWARD-2026-05-13.md`.\n"
            )
            if "Walk-forward verdict:" not in existing:
                T44B_DOC.write_text(existing + stamp, encoding="utf-8")
                log.info("Appended walk-forward verdict to T44b doc.")
            else:
                log.info("T44b doc already has walk-forward verdict; skipping.")
        except Exception as exc:
            log.warning("Could not append to T44b doc: %r", exc)

    log.info("=" * 70)
    log.info(
        "VERDICT: %s — %s", verdict, verdict_reason,
    )
    log.info(
        "TRAIN: $%.0f / %.0f per month | TEST: $%.0f / %.0f per month | "
        "ratio: %.2fx",
        train["total_pnl"], train_per_mo,
        test["total_pnl"], test_per_mo, ratio,
    )
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
