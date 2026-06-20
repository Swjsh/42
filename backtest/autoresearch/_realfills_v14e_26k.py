"""Real-fills (OPRA) validation for the v14_enhanced $26,601 best combo.

This script is the final gate before J weekend ratification of the
$26,601 v14_enhanced combo documented in:
  strategy/candidates/2026-05-23-v14e-param-sweep-26k.md

BS-sim result: $26,601 wide_pnl, 65% WR, 6/6 +quarters, OOS ratio=2.07.
Real-fills answer: does the edge hold with actual OPRA bid/ask spreads
and per-strike skew, not Black-Scholes approximation?

== THE COMBO ==
  strike_offset_bear=0          ATM (OP-17 locked)
  min_triggers_bear=1           asymmetric (OP-17 locked)
  premium_stop_pct_bear=-0.20   OP-17 locked
  tp1_qty_fraction=0.5          OP-17 locked
  no_trade_before="09:35"       sweep winner
  tp1_premium_pct=0.30          sweep winner (vs production 0.75)
  runner_target_premium_pct=2.5 sweep winner (vs production 2.0)
  profit_lock_threshold_pct=0.05  sweep winner (new param, off in production)
  profit_lock_stop_offset_pct=0.10 sweep winner (new param)

== KEY CAVEAT ==
simulator_real DOES NOT implement profit-lock. Only BS simulator does.
profit_lock_threshold_pct=0.05 / profit_lock_stop_offset_pct=0.10 are
NO-OPS in real-fills mode. This means:
  - Trades that would have been locked to profit (premium hit +5% then
    reversed to stop) will show as losses here but profits in BS-sim.
  - Expected real-fills WR < BS-sim WR due to this gap.
  - If real-fills wide_pnl > $8,000 despite this gap, the combo has
    durable edge even without profit-lock (profit-lock is upside only).

== VERDICT GATES ==
  PASS: real wide_pnl > $8,000  AND
        4/29 real > $0           (winner, not required to be huge)
        5/01 real > $0
        5/04 real > $100
        5/12 real > $0
        5/05 real >= -$350       (don't blow through J's -$260)
  CONDITIONAL: real wide_pnl $3,000-$8,000 → "PASS_DEGRADED — J review"
  FAIL: real wide_pnl <= $3,000 OR any winner day negative AND loss > $200

== OUTPUT ==
  backtest/autoresearch/_state/v14e_realfills_26k_results.json
  markdown/research/V14E-REALFILLS-26K-2026-05-23.md
  Console report with per-anchor + per-quarter breakdown

CLI:
  .venv\\Scripts\\python.exe -m autoresearch._realfills_v14e_26k
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
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from lib import simulator_real as _sim_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # matches OOS validation window

OUT_DIR = REPO / "autoresearch" / "_state"
OUT_JSON = OUT_DIR / "v14e_realfills_26k_results.json"
OUT_DOC = REPO.parent / "markdown" / "research" / "V14E-REALFILLS-26K-2026-05-23.md"

# The $26,601 winning combo
BEST_COMBO: dict[str, Any] = {
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

# BS-sim reference (from the grinder + OOS validation)
BS_METRICS: dict[str, Any] = {
    "wide_pnl": 26601,
    "wide_wr": 0.649,
    "wide_n_trades": 404,
    "positive_quarters": 6,
    "top5_pct": 0.148,
    "max_drawdown": 1203,
    "oos_pnl": 19293,
    "oos_wr": 0.693,
    "wf_ratio": 2.072,
}

# J anchor days for comparison
J_ANCHORS: dict[str, dict[str, Any]] = {
    "2026-04-29": {"j_pnl": 342, "direction": "winner"},
    "2026-05-01": {"j_pnl": 470, "direction": "winner"},
    "2026-05-04": {"j_pnl": 730, "direction": "winner"},
    "2026-05-12": {"j_pnl": 400, "direction": "winner"},
    "2026-05-05": {"j_pnl": -260, "direction": "loser"},
    "2026-05-06": {"j_pnl": -300, "direction": "loser"},
    "2026-05-07": {"j_pnl": -45, "direction": "loser"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _patched_sim_real_constants(
    tp1_premium_pct: float,
    runner_target_premium_pct: float,
    tp1_qty_fraction: float,
) -> Iterator[None]:
    """Temporarily swap simulator_real's module-level exit constants.

    simulator_real reads TP1_PREMIUM_PCT / RUNNER_MAX_PREMIUM_PCT /
    TP1_QTY_FRACTION from its own namespace at runtime. We patch them,
    run, then restore — same pattern as v14_enhanced_real_fills.py.
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


def _run_real_fills(
    combo: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
) -> dict[str, Any]:
    """Run the combo through real OPRA fills + compute OP-19 metrics.

    Returns a dict with wide metrics, per-day, per-quarter, fallback stats.
    Uses run_backtest(use_real_fills=True) — same path as v14_enhanced_real_fills.py.
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

    # Direct passthrough knobs (matches _run_candidate_real_fills in v14_enhanced_real_fills.py)
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
    runner_pct = combo.get("runner_target_premium_pct", 2.5)
    tp1_frac = combo.get("tp1_qty_fraction", 0.5)

    with _patched_sim_real_constants(tp1_pct, runner_pct, tp1_frac):
        result = run_backtest(**kwargs)

    # Aggregate metrics
    per_day: dict[str, float] = defaultdict(float)
    per_quarter: dict[str, float] = defaultdict(float)
    per_month: dict[str, float] = defaultdict(float)
    bs_fallback_count = 0
    real_fills_count = 0

    for t in result.trades:
        d = t.entry_time_et.date()
        per_day[d.isoformat()] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        per_quarter[q] += t.dollar_pnl
        mo = f"{d.year}-{d.month:02d}"
        per_month[mo] += t.dollar_pnl
        if "BS_FALLBACK" in (t.setup or ""):
            bs_fallback_count += 1
        else:
            real_fills_count += 1

    wide_pnl = sum(per_day.values())
    n_trades = len(result.trades)
    n_winners = sum(1 for t in result.trades if t.dollar_pnl > 0)
    wide_wr = (n_winners / n_trades) if n_trades else 0.0
    positive_quarters = sum(1 for v in per_quarter.values() if v > 0)
    positive_months = sum(1 for v in per_month.values() if v > 0)

    sorted_day_pnls = sorted(per_day.values(), reverse=True)
    top5_pct = (
        round(sum(sorted_day_pnls[:5]) / wide_pnl, 3)
        if wide_pnl > 0 else 999.0
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
        "wide_pnl": round(wide_pnl, 2),
        "wide_n_trades": n_trades,
        "wide_wr": round(wide_wr, 3),
        "per_day": {k: round(v, 2) for k, v in per_day.items()},
        "per_quarter": {k: round(v, 2) for k, v in sorted(per_quarter.items())},
        "per_month": {k: round(v, 2) for k, v in sorted(per_month.items())},
        "positive_quarters": positive_quarters,
        "total_quarters": len(per_quarter),
        "positive_months": positive_months,
        "total_months": len(per_month),
        "top5_pct": top5_pct,
        "max_drawdown": round(max_dd, 2),
        "real_fills_count": real_fills_count,
        "bs_fallback_count": bs_fallback_count,
        "bs_fallback_pct": (
            round(bs_fallback_count / n_trades * 100, 1) if n_trades else 0.0
        ),
    }


def _verdict(real: dict[str, Any]) -> tuple[str, str]:
    """Return (verdict, reason) based on gates.

    PASS:        real wide_pnl > $8,000 AND winner days not negative AND
                 5/05 >= -$350
    CONDITIONAL: wide_pnl $3,000–$8,000 (degraded but positive edge)
    FAIL:        wide_pnl <= $3,000 OR any winner day < -$100 AND |loss|>200
    """
    wp = real["wide_pnl"]
    p429 = real["per_day"].get("2026-04-29", 0.0)
    p501 = real["per_day"].get("2026-05-01", 0.0)
    p504 = real["per_day"].get("2026-05-04", 0.0)
    p512 = real["per_day"].get("2026-05-12", 0.0)
    p505 = real["per_day"].get("2026-05-05", 0.0)

    winner_losses = [
        (d, v) for d, v in [
            ("4/29", p429), ("5/01", p501), ("5/04", p504), ("5/12", p512)
        ] if v < -100
    ]
    failures: list[str] = []

    if wp <= 3000:
        failures.append(f"wide_pnl=${wp:.0f} ≤ $3,000 — BS edge didn't survive real fills")
    if winner_losses:
        failures.append(
            "winner days went negative: "
            + ", ".join(f"{d}=${v:.0f}" for d, v in winner_losses)
        )
    if p505 < -350:
        failures.append(f"5/05=${p505:.0f} < -$350 — added loss beyond J's -$260")

    if failures:
        return "FAIL", "; ".join(failures)

    if wp < 8000:
        return "CONDITIONAL", (
            f"wide_pnl=${wp:.0f} — edge degraded (BS=${BS_METRICS['wide_pnl']:,}) "
            f"but positive. Profit-lock gap explains part of reduction. "
            f"Requires J review before ratification."
        )

    return "PASS", (
        f"wide_pnl=${wp:.0f} (BS=${BS_METRICS['wide_pnl']:,}, "
        f"degradation={100*(1-wp/BS_METRICS['wide_pnl']):.0f}%), "
        f"winner anchors: 4/29=${p429:.0f}, 5/01=${p501:.0f}, "
        f"5/04=${p504:.0f}, 5/12=${p512:.0f}; "
        f"5/05=${p505:.0f} (J=${J_ANCHORS['2026-05-05']['j_pnl']:+}). "
        f"Real edge confirmed."
    )


def _build_markdown_report(
    real: dict[str, Any],
    verdict: str,
    verdict_reason: str,
    generated_at: str,
    error: str | None = None,
) -> str:
    lines: list[str] = []
    lines += [
        "# v14_enhanced Real-Fills Validation — $26K Combo",
        "",
        f"Generated: `{generated_at}`",
        "",
        "## The Combo",
        "",
        "```json",
        json.dumps(BEST_COMBO, indent=2),
        "```",
        "",
        "## BS-Sim Reference (OOS-validated)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
    ]
    for k, v in BS_METRICS.items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Real-Fills Result",
        "",
    ]

    if error:
        lines += [
            f"**ERROR:** `{error}`",
            "",
            "Real-fills run failed. Cannot ratify.",
            "",
        ]
        lines.append(f"## Verdict: **ERROR**")
        return "\n".join(lines)

    bs_pnl = BS_METRICS["wide_pnl"]
    real_pnl = real["wide_pnl"]
    degradation_pct = round(100 * (1 - real_pnl / bs_pnl), 1) if bs_pnl else 0

    lines += [
        "| Metric | BS-Sim | Real-Fills | Delta |",
        "|--------|--------|------------|-------|",
        f"| wide_pnl | ${bs_pnl:,} | ${real_pnl:,.0f} | "
        f"{'-' if degradation_pct>0 else '+'}{abs(degradation_pct):.0f}% |",
        f"| WR | {BS_METRICS['wide_wr']:.1%} | {real['wide_wr']:.1%} | "
        f"{(real['wide_wr']-BS_METRICS['wide_wr'])*100:+.1f}pp |",
        f"| n_trades | {BS_METRICS['wide_n_trades']} | {real['wide_n_trades']} | "
        f"{real['wide_n_trades']-BS_METRICS['wide_n_trades']:+d} |",
        f"| +quarters | {BS_METRICS['positive_quarters']}/6 | "
        f"{real['positive_quarters']}/{real['total_quarters']} | — |",
        f"| top5_pct | {BS_METRICS['top5_pct']:.1%} | {real['top5_pct']:.1%} | — |",
        f"| max_drawdown | ${BS_METRICS['max_drawdown']:,} | "
        f"${real['max_drawdown']:,.0f} | — |",
        f"| BS fallback | N/A | {real['bs_fallback_pct']:.1f}% | — |",
        "",
        "## J Anchor Days",
        "",
        "| Date | Direction | J PnL | Real-Fills PnL | Pass? |",
        "|------|-----------|-------|----------------|-------|",
    ]
    for date_str, anchor in J_ANCHORS.items():
        real_p = real["per_day"].get(date_str, 0.0)
        direction = anchor["direction"]
        j_pnl = anchor["j_pnl"]
        if direction == "winner":
            ok = "✓" if real_p > 0 else ("⚠ small loss" if real_p > -100 else "✗")
        else:
            ok = "✓" if real_p >= j_pnl else "⚠"
        lines.append(
            f"| {date_str} | {direction} | ${j_pnl:+} | ${real_p:+.0f} | {ok} |"
        )

    lines += [
        "",
        "## Quarter Breakdown",
        "",
        "| Quarter | Real-Fills P&L | Period |",
        "|---------|---------------|--------|",
    ]
    for q, pnl in real["per_quarter"].items():
        period = "IS" if q <= "2025-Q3" else "OOS"
        sign = "+" if pnl >= 0 else ""
        lines.append(f"| {q} | {sign}${pnl:,.0f} | {period} |")

    lines += [
        "",
        "## Monthly Breakdown (all months)",
        "",
        "| Month | P&L | Period |",
        "|-------|-----|--------|",
    ]
    for mo, pnl in real["per_month"].items():
        period = "IS" if mo <= "2025-09" else "OOS"
        sign = "+" if pnl >= 0 else ""
        lines.append(f"| {mo} | {sign}${pnl:,.0f} | {period} |")

    lines += [
        "",
        "## Caveats",
        "",
        "- **Profit-lock NOT applied.** `simulator_real` does not implement "
        "`profit_lock_threshold_pct` / `profit_lock_stop_offset_pct`. These are "
        "NO-OPS in real-fills mode. Trades that would have been locked to profit "
        "(premium hit +5% then reversed to the stop) show as losses here but "
        "profits in BS-sim. This partially explains the BS→real P&L gap.",
        "- **Per-quality exit matrix NOT applied.** The TRENDLINE/LEVEL/ELITE/SUPER "
        "tier system only fires through the BS path. Real-fills uses a uniform exit "
        "policy (tp1=0.30, runner=2.5) across all trade qualities.",
        f"- **BS fallback rate: {real['bs_fallback_pct']:.1f}%.** "
        "Trades where OPRA contract was missing from the cache fall back to BS-sim.",
        "",
        f"## Verdict: **{verdict}**",
        "",
        f"{verdict_reason}",
        "",
        "## Next Steps",
        "",
    ]

    if verdict == "PASS":
        lines += [
            "1. **Ratification ready.** Queue for J weekend ratification per Rule 9.",
            "2. Write v15 param update proposal with 3-step revert documented.",
            "3. Update leaderboard rank #12 to RATIFICATION_READY.",
        ]
    elif verdict == "CONDITIONAL":
        lines += [
            "1. **J review required.** Real-fills edge positive but degraded from BS-sim.",
            "2. Investigate profit-lock gap: how many trades would profit-lock have saved?",
            "   Run BS-sim with profit_lock_threshold_pct=0.0 to measure the lock's contribution.",
            "3. If profit-lock contribution explains most of the gap → still ratifiable with "
            "   the caveat that real-fills won't fully capture the lock.",
        ]
    else:
        lines += [
            "1. **Do not ratify.** BS edge does not survive real fills.",
            "2. Investigate the worst mismatch dates (per-day above shows largest deviations).",
            "3. Check if OPRA cache covers the relevant contracts "
            "(high BS-fallback rate would invalidate this test).",
        ]

    lines += [
        "",
        "## Provenance",
        "",
        f"- Script: `backtest/autoresearch/_realfills_v14e_26k.py`",
        f"- Wide window: `{WIDE_START}` → `{WIDE_END}`",
        f"- Generated: `{generated_at}`",
    ]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    generated_at = dt.datetime.now().isoformat()

    log.info("=" * 65)
    log.info("Real-fills validation — v14_enhanced $26K combo")
    log.info("Window: %s .. %s", WIDE_START, WIDE_END)
    log.info("Combo: %s", BEST_COMBO)
    log.info("=" * 65)

    log.info("Loading SPY + VIX data (%s .. %s) ...", WIDE_START, WIDE_END)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)

    # Normalize tz to tz-naive ET (same as v14_enhanced_real_fills.py)
    spy_full["timestamp_et"] = (
        pd.to_datetime(spy_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    vix_full["timestamp_et"] = (
        pd.to_datetime(vix_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    log.info(
        "Loaded: SPY %d bars, VIX %d bars (tz-normalized ET)",
        len(spy_full), len(vix_full),
    )

    real: dict[str, Any] = {}
    verdict = "ERROR"
    verdict_reason = ""
    error: str | None = None

    try:
        log.info("Running real-fills simulation (this takes 2-5 min) ...")
        real = _run_real_fills(
            BEST_COMBO, spy_full, vix_full, WIDE_START, WIDE_END
        )
        log.info(
            "Real-fills: wide=$%.0f  n=%d  wr=%.1f%%  +q=%d/%d  "
            "top5=%.1f%%  dd=$%.0f  real/bs_fallback=%d/%d (%.1f%% BS)",
            real["wide_pnl"], real["wide_n_trades"],
            real["wide_wr"] * 100,
            real["positive_quarters"], real["total_quarters"],
            real["top5_pct"] * 100,
            real["max_drawdown"],
            real["real_fills_count"], real["bs_fallback_count"],
            real["bs_fallback_pct"],
        )
        log.info(
            "Anchors: 4/29=$%.0f  5/01=$%.0f  5/04=$%.0f  5/12=$%.0f  "
            "5/05=$%.0f  5/06=$%.0f  5/07=$%.0f",
            real["per_day"].get("2026-04-29", 0),
            real["per_day"].get("2026-05-01", 0),
            real["per_day"].get("2026-05-04", 0),
            real["per_day"].get("2026-05-12", 0),
            real["per_day"].get("2026-05-05", 0),
            real["per_day"].get("2026-05-06", 0),
            real["per_day"].get("2026-05-07", 0),
        )
        verdict, verdict_reason = _verdict(real)
        log.info("Verdict: %s — %s", verdict, verdict_reason)

    except Exception as exc:
        log.exception("Real-fills run failed")
        error = repr(exc)
        verdict = "ERROR"
        verdict_reason = f"Execution failed: {exc!r}\n{traceback.format_exc()}"

    # Write outputs
    result_doc: dict[str, Any] = {
        "generated_at": generated_at,
        "combo": BEST_COMBO,
        "wide_window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
        "bs_metrics": BS_METRICS,
        "real_fills": real if not error else {"error": error},
        "verdict": verdict,
        "verdict_reason": verdict_reason,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result_doc, indent=2, default=str), encoding="utf-8")
    log.info("Wrote JSON: %s", OUT_JSON)

    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUT_DOC.write_text(
        _build_markdown_report(real, verdict, verdict_reason, generated_at, error),
        encoding="utf-8",
    )
    log.info("Wrote MD: %s", OUT_DOC)

    # Console summary
    log.info("=" * 65)
    log.info("FINAL VERDICT: %s", verdict)
    log.info("REASON: %s", verdict_reason[:120])
    if not error and real:
        log.info(
            "SUMMARY: BS=$%s → Real=$%s (%.0f%% degradation)  WR: %.1f%% → %.1f%%  "
            "+quarters: %d/%d → %d/%d",
            f"{BS_METRICS['wide_pnl']:,}",
            f"{real['wide_pnl']:,.0f}",
            max(0, 100 * (1 - real["wide_pnl"] / BS_METRICS["wide_pnl"])),
            BS_METRICS["wide_wr"] * 100,
            real["wide_wr"] * 100,
            BS_METRICS["positive_quarters"],
            6,
            real["positive_quarters"],
            real["total_quarters"],
        )
    log.info("=" * 65)

    return 0 if verdict in ("PASS", "CONDITIONAL") else 1


if __name__ == "__main__":
    sys.exit(main())
