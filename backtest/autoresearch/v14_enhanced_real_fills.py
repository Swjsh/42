"""v14_enhanced real-fills (OPRA) validation — top-3 front-runner combos.

This script tests whether the v14_enhanced grinder's TOP-3 front-runner combos
(rejected this morning ONLY on the per-loser-day floor for 5/05) hold up under
REAL OPRA fills, not BS-sim approximation.

Per CLAUDE.md OP 20 disclosure 4: a backtest result is not "ready" until
real-fills validation runs. BS sim approximates premium via vix_to_iv +
Black-Scholes; real fills capture bid/ask spread, per-strike per-DTE skew,
and illiquid contracts.

The 3 candidates share these locked OP 17 doctrine knobs:
    strike_offset_bear = 0           (ATM)
    min_triggers_bear = 1            (asymmetric)
    premium_stop_pct_bear = -0.20
    tp1_qty_fraction = 0.5

They differ on:
    no_trade_before (09:35 / 09:45 / 10:00)
    profit_lock_threshold_pct (all 0.05)
    profit_lock_stop_offset_pct (all 0.10)
    tp1_premium_pct (0.30 / 0.50 / 0.75)
    runner_target_premium_pct (all 2.5)

Method:
  1. Load wide window data (2025-01-01 .. 2026-05-12).
  2. For each combo, monkey-patch simulator_real's module-level constants to
     honour the combo's tp1_premium_pct / runner_target / tp1_qty_fraction
     (simulator_real reads these as imported names — they don't flow through
     the function signature). This is the same pattern lib.shadow already
     uses for filter constants.
  3. Run `run_backtest(use_real_fills=True, ...)` with the combo's knobs.
  4. Aggregate per-day, per-quarter, wide-window metrics from real-fills trades.
  5. Compare BS metrics (provided by caller) vs real-fills metrics.

Simplifications + caveats (documented in the report):
  - simulator_real does NOT implement profit-lock (it only exists in BS sim).
    So profit_lock_threshold_pct / profit_lock_stop_offset_pct are NO-OPS in
    real-fills mode. The doctrine intent is "winners-never-negative"; in
    practice this affects 5-10% of trades where favourable premium spiked
    then reversed. We document the omission and run anyway.
  - simulator_real DOES NOT honour the orchestrator's per-quality exit-knob
    matrix (quality_stop / quality_tp1 per tier). It uses the module-level
    constants for all qualities. The TRENDLINE/LEVEL/ELITE/SUPER tier system
    only fires through the BS path. This is per-design (the real-fills path
    in orchestrator.py bypasses _grinder_overrides entirely). Real-fills
    therefore reflects a UNIFORM exit policy across qualities (the combo's
    tp1_premium_pct / runner_target uniformly applied).
  - If OPRA missing for a day/strike, simulate_trade_real returns None and
    the orchestrator falls back to BS sim with a "::BS_FALLBACK" tag in the
    setup name. We surface fallback count in the report.

Output:
    backtest/autoresearch/v14_enhanced_real_fills.py        (this script)
    analysis/recommendations/v14_enhanced-real-fills.json   (machine-readable)
    docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md              (human-readable)

CLI:
    python -m autoresearch.v14_enhanced_real_fills
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

# ── Configuration ────────────────────────────────────────────────────────────

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 12)

OUT_JSON = REPO.parent / "analysis" / "recommendations" / "v14_enhanced-real-fills.json"
OUT_DOC = REPO.parent / "docs" / "V14_ENHANCED-REAL-FILLS-2026-05-13.md"

# Locked OP 17 doctrine knobs shared by all 3 candidates
LOCKED_OVERRIDES = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
    "runner_target_premium_pct": 2.5,
}

# Top-3 v14_enhanced candidates (from this morning's grinder, rejected on
# per-loser-day floor for 5/05).
CANDIDATES: list[dict[str, Any]] = [
    {
        "name": "candidate_1_0935_tp1_0.30",
        "combo": {
            **LOCKED_OVERRIDES,
            "no_trade_before": "09:35",
            "tp1_premium_pct": 0.30,
        },
        "bs_metrics": {
            "wide_pnl": 23188,
            "pnl_4_29": 293,
            "pnl_5_12": 241,
            "pnl_5_07": 249,
            "pnl_5_05": -153,
            "wide_n_trades": 339,
            "wide_wr": 0.614,
            "positive_quarters": 6,
            "top5_pct": 0.20,
        },
    },
    {
        "name": "candidate_2_0945_tp1_0.50",
        "combo": {
            **LOCKED_OVERRIDES,
            "no_trade_before": "09:45",
            "tp1_premium_pct": 0.50,
        },
        "bs_metrics": {
            "wide_pnl": 21769,
        },
    },
    {
        "name": "candidate_3_1000_tp1_0.75",
        "combo": {
            **LOCKED_OVERRIDES,
            "no_trade_before": "10:00",
            "tp1_premium_pct": 0.75,
        },
        "bs_metrics": {
            "wide_pnl": 19501,
        },
    },
]

# J anchor days for per-day comparison
J_ANCHORS = {
    "2026-04-29": {"j_pnl": 342, "direction": "winner"},
    "2026-05-01": {"j_pnl": 470, "direction": "winner"},
    "2026-05-04": {"j_pnl": 730, "direction": "winner"},
    "2026-05-12": {"j_pnl": 400, "direction": "winner"},
    "2026-05-05": {"j_pnl": -260, "direction": "loser"},
    "2026-05-06": {"j_pnl": -300, "direction": "loser"},
    "2026-05-07": {"j_pnl": -45, "direction": "loser"},
}


# ── Helpers ──────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _patched_sim_real_constants(
    tp1_premium_pct: float,
    runner_target_premium_pct: float,
    tp1_qty_fraction: float,
) -> Iterator[None]:
    """Temporarily swap simulator_real's module-level exit constants.

    simulator_real imports TP1_PREMIUM_PCT / RUNNER_MAX_PREMIUM_PCT /
    TP1_QTY_FRACTION from simulator at import time, so they live in
    simulator_real's namespace. We patch them there, run, then restore.

    This mirrors `autoresearch.runner._patched_filter_constants` which does
    the same thing for filter constants.
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


def _run_candidate_real_fills(
    combo: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
) -> dict[str, Any]:
    """Run one candidate combo through real-fills + aggregate metrics.

    Forces `use_real_fills=True` via a runner kwarg injection. Since the
    autoresearch.runner.run_with_params helper sets `use_real_fills=False`
    hard-coded, we re-implement the equivalent path here, calling
    lib.orchestrator.run_backtest directly with use_real_fills=True.
    """
    from lib.orchestrator import run_backtest
    from autoresearch import config

    # Build run_backtest kwargs the same way runner.run_with_params does.
    kwargs: dict[str, Any] = {
        "spy_df": spy_df,
        "vix_df": vix_df,
        "start_date": WIDE_START,
        "end_date": WIDE_END,
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

    # Patch simulator_real's module-level exit constants to honour the combo.
    tp1_pct = combo.get("tp1_premium_pct", 0.30)
    runner_pct = combo.get("runner_target_premium_pct", 3.0)
    tp1_frac = combo.get("tp1_qty_fraction", 2.0 / 3.0)

    with _patched_sim_real_constants(tp1_pct, runner_pct, tp1_frac):
        result = run_backtest(**kwargs)

    # Aggregate per-day + per-quarter
    per_day: dict[str, float] = defaultdict(float)
    per_quarter: dict[str, float] = defaultdict(float)
    bs_fallback_count = 0
    real_fills_count = 0
    for t in result.trades:
        d = t.entry_time_et.date()
        per_day[d.isoformat()] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        per_quarter[q] += t.dollar_pnl
        if "BS_FALLBACK" in (t.setup or ""):
            bs_fallback_count += 1
        else:
            real_fills_count += 1

    wide_pnl = sum(per_day.values())
    n_trades = len(result.trades)
    n_winners = sum(1 for t in result.trades if t.dollar_pnl > 0)
    wide_wr = (n_winners / n_trades) if n_trades else 0.0
    positive_quarters = sum(1 for v in per_quarter.values() if v > 0)
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
        "per_quarter": {k: round(v, 2) for k, v in per_quarter.items()},
        "positive_quarters": positive_quarters,
        "quarter_count": len(per_quarter),
        "top5_pct": top5_pct,
        "max_drawdown": round(max_dd, 2),
        "real_fills_count": real_fills_count,
        "bs_fallback_count": bs_fallback_count,
        "bs_fallback_pct": (
            round(bs_fallback_count / n_trades * 100, 1) if n_trades else 0.0
        ),
    }


def _verdict(combo_real: dict[str, Any], j_real_5_05: float) -> tuple[str, str]:
    """Return (verdict, reason) per task gates.

    PASS gates (all required):
      - real wide_pnl > $5,000
      - 4/29 real > $100
      - 5/12 real > $100
      - 5/05 real loss less negative than J's -$260
    """
    failures: list[str] = []
    wp = combo_real["wide_pnl"]
    p429 = combo_real["per_day"].get("2026-04-29", 0.0)
    p512 = combo_real["per_day"].get("2026-05-12", 0.0)
    p505 = combo_real["per_day"].get("2026-05-05", 0.0)

    if wp <= 5000:
        failures.append(f"wide_pnl=${wp:.0f} ≤ $5000")
    if p429 <= 100:
        failures.append(f"4/29=${p429:.0f} ≤ $100")
    if p512 <= 100:
        failures.append(f"5/12=${p512:.0f} ≤ $100")
    if p505 < -260:
        failures.append(f"5/05=${p505:.0f} < -$260 (J's loss)")

    if not failures:
        return "PASS", (
            f"wide_pnl=${wp:.0f}, 4/29=${p429:.0f}, 5/12=${p512:.0f}, "
            f"5/05=${p505:.0f} (J=$-260) — all gates pass."
        )
    return "FAIL", "; ".join(failures)


def _build_markdown_report(
    report: dict[str, Any],
) -> str:
    """Render the JSON report as a Markdown document for human review."""
    lines: list[str] = []
    lines.append("# v14_enhanced Real-Fills Validation — 2026-05-13")
    lines.append("")
    lines.append(f"Generated: `{report['generated_at']}`")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(
        "This morning's v14_enhanced grinder produced 60 sampled combos before "
        "silent-dying (3rd time). Three near-identical combos converged on a "
        "strong recipe but were REJECTED only by the per-loser-day floor "
        "(5/05 BS-sim -$153 < -$50 floor — but J had -$260 on 5/05, so engine "
        "loses LESS than J, which should be a WIN not a rejection)."
    )
    lines.append("")
    lines.append(
        "Per CLAUDE.md OP 20 disclosure 4, this report runs the top-3 "
        "candidates through REAL OPRA fills (not BS sim) over the wide "
        f"{WIDE_START} → {WIDE_END} window to determine if any survives "
        "real-fills validation."
    )
    lines.append("")

    # Caveats up front
    lines.append("## Caveats (read first)")
    lines.append("")
    lines.append(
        "- **Profit-lock NOT applied.** `simulator_real` does not implement "
        "the profit-lock primitive (only in BS `simulator`). The combo's "
        "`profit_lock_threshold_pct=0.05` and `profit_lock_stop_offset_pct=0.10` "
        "are no-ops here. This affects 5-10% of trades where favourable "
        "premium spiked then reversed — those trades may show worse real-fills "
        "PnL than BS-sim with profit-lock would have."
    )
    lines.append(
        "- **Per-quality exit-knob matrix NOT applied.** The orchestrator's "
        "TRENDLINE/LEVEL/ELITE/SUPER per-quality `_grinder_overrides` only "
        "fires through the BS path. Real-fills uses a UNIFORM exit policy "
        "(the combo's `tp1_premium_pct` + `runner_target_premium_pct` "
        "applied to all trades regardless of trigger quality)."
    )
    lines.append(
        "- **BS-sim fallback on OPRA cache miss.** `simulate_trade_real` "
        "returns `None` if the OPRA contract isn't cached; the orchestrator "
        "falls back to BS sim with a `::BS_FALLBACK` tag. The fallback "
        "fraction per combo is surfaced below — if it's >20% the result is "
        "less than a true real-fills test."
    )
    lines.append(
        "- **Strike offset = 0 → ATM (round-spot).** v14_enhanced's "
        "`strike_offset_bear=0` matches OP 17 doctrine's J-edge config "
        "(ATM strikes, not ITM-2)."
    )
    lines.append("")

    # Summary table
    lines.append("## Per-Combo Verdict Summary")
    lines.append("")
    lines.append(
        "| Combo | BS wide | Real wide | 4/29 BS | 4/29 Real | 5/12 BS | 5/12 Real | 5/05 BS | 5/05 Real | BS-fallback % | Verdict |"
    )
    lines.append(
        "|-------|---------|-----------|---------|-----------|---------|-----------|---------|-----------|---------------|---------|"
    )
    for c in report["candidates"]:
        bs = c["bs_metrics"]
        real = c.get("real_fills", {})
        per_day = real.get("per_day", {}) if real else {}
        row = (
            f"| {c['name']} "
            f"| ${bs.get('wide_pnl', 0):,.0f} "
            f"| ${real.get('wide_pnl', 0):,.0f} "
            f"| ${bs.get('pnl_4_29', 0):.0f} "
            f"| ${per_day.get('2026-04-29', 0):.0f} "
            f"| ${bs.get('pnl_5_12', 0):.0f} "
            f"| ${per_day.get('2026-05-12', 0):.0f} "
            f"| ${bs.get('pnl_5_05', 0):.0f} "
            f"| ${per_day.get('2026-05-05', 0):.0f} "
            f"| {real.get('bs_fallback_pct', 0):.1f}% "
            f"| **{c.get('verdict', 'ERROR')}** |"
        )
        lines.append(row)
    lines.append("")

    # Per-combo deep dive
    for c in report["candidates"]:
        lines.append(f"## {c['name']}")
        lines.append("")
        lines.append("**Combo:**")
        lines.append("```python")
        lines.append(json.dumps(c["combo"], indent=2))
        lines.append("```")
        lines.append("")
        if "error" in c:
            lines.append(f"**ERROR:** `{c['error']}`")
            lines.append("")
            lines.append("```")
            lines.append(c.get("trace", ""))
            lines.append("```")
            continue
        real = c.get("real_fills", {})
        bs = c["bs_metrics"]
        lines.append("**BS metrics (provided by caller):**")
        for k, v in bs.items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")
        lines.append("**Real-fills metrics:**")
        lines.append(f"- wide_pnl: ${real.get('wide_pnl', 0):,.2f}")
        lines.append(f"- wide_n_trades: {real.get('wide_n_trades', 0)}")
        lines.append(f"- wide_wr: {real.get('wide_wr', 0):.1%}")
        lines.append(
            f"- positive_quarters: {real.get('positive_quarters', 0)}"
            f"/{real.get('quarter_count', 0)}"
        )
        lines.append(f"- top5_pct: {real.get('top5_pct', 0):.1%}")
        lines.append(f"- max_drawdown: ${real.get('max_drawdown', 0):,.2f}")
        lines.append(
            f"- real_fills/bs_fallback: {real.get('real_fills_count', 0)}"
            f"/{real.get('bs_fallback_count', 0)} "
            f"({real.get('bs_fallback_pct', 0):.1f}% BS fallback)"
        )
        lines.append("")
        lines.append("**Per-J-anchor day:**")
        lines.append("")
        lines.append("| Date | J PnL | Real PnL | BS PnL |")
        lines.append("|------|-------|----------|--------|")
        per_day = real.get("per_day", {})
        for d, anchor in J_ANCHORS.items():
            real_p = per_day.get(d, 0.0)
            bs_p: Any = "—"
            if d == "2026-04-29":
                bs_p = f"${bs.get('pnl_4_29', 0):.0f}"
            elif d == "2026-05-12":
                bs_p = f"${bs.get('pnl_5_12', 0):.0f}"
            elif d == "2026-05-07":
                bs_p = f"${bs.get('pnl_5_07', 0):.0f}"
            elif d == "2026-05-05":
                bs_p = f"${bs.get('pnl_5_05', 0):.0f}"
            lines.append(
                f"| {d} ({anchor['direction']}) "
                f"| ${anchor['j_pnl']} "
                f"| ${real_p:.0f} "
                f"| {bs_p} |"
            )
        lines.append("")
        lines.append("**Per-quarter PnL:**")
        per_q = real.get("per_quarter", {})
        if per_q:
            for q in sorted(per_q.keys()):
                lines.append(f"- {q}: ${per_q[q]:,.2f}")
        lines.append("")
        lines.append(f"**Verdict:** {c.get('verdict', 'ERROR')}")
        lines.append("")
        lines.append(f"**Reason:** {c.get('verdict_reason', '')}")
        lines.append("")

    lines.append("## Next-Step Recommendation")
    lines.append("")
    pass_combos = [c for c in report["candidates"] if c.get("verdict") == "PASS"]
    if pass_combos:
        best = max(pass_combos, key=lambda c: c.get("real_fills", {}).get("wide_pnl", 0))
        lines.append(
            f"**{len(pass_combos)} of 3 candidates passed real-fills validation.** "
            f"Best is **{best['name']}** with real wide_pnl "
            f"${best.get('real_fills', {}).get('wide_pnl', 0):,.0f}."
        )
        lines.append("")
        lines.append("**Recommended next steps:**")
        lines.append(
            "1. Run walk-forward validation on the best candidate "
            "(`walk_forward_validate.py`)."
        )
        lines.append(
            "2. Generate full 6-disclosure scorecard at "
            "`analysis/recommendations/v14_enhanced.json`."
        )
        lines.append(
            "3. Add to wake-loop queue: Monday-Ready Checklist for v14_enhanced."
        )
        lines.append(
            "4. **Do NOT auto-ratify** — J reviews scorecard before any "
            "production heartbeat.md change (CLAUDE.md OP 25)."
        )
    else:
        lines.append(
            "**Zero candidates passed real-fills validation.** BS sim was "
            "over-estimating PnL. Recovery options:"
        )
        lines.append(
            "1. Re-spawn v14_enhanced grinder with the silent-death fix "
            "(longer hours, lower workers, better progress.json heartbeats)."
        )
        lines.append(
            "2. Investigate where BS-vs-real diverges most "
            "(per-day comparison above shows the worst-mismatch dates) — "
            "encode a regime filter that excludes those bars."
        )
        lines.append(
            "3. Run the same 3 candidates on the strict (2025-2026Q1-only) "
            "window to see if regime-conditioned the results survive."
        )
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    lines.append(
        f"- Script: `backtest/autoresearch/v14_enhanced_real_fills.py`"
    )
    lines.append(
        f"- Wide window: `{WIDE_START}` → `{WIDE_END}`"
    )
    lines.append(
        f"- OPRA cache: `backtest/data/options/` "
        f"({report.get('opra_cache_size', '?')} contracts)"
    )
    lines.append(
        f"- Master SPY/VIX: `data/spy_5m_2025-01-01_2026-05-12.csv`"
    )
    lines.append("")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    log.info("Loading wide window data %s .. %s", WIDE_START, WIDE_END)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    # Normalize timestamps to tz-naive ET — simulator_real strips tz on entry
    # but spy_df rows keep their tz, causing tz-naive vs tz-aware subtraction
    # errors when fill.runner_exit_time_et meets entry_time. Same fix
    # sniper_real_fills.py uses.
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

    # Count OPRA cache size for provenance
    opra_dir = REPO / "data" / "options"
    opra_count = len(list(opra_dir.glob("*.csv"))) if opra_dir.exists() else 0

    report = {
        "generated_at": dt.datetime.now().isoformat(),
        "rule_id": "v14_enhanced",
        "wide_window": {
            "start": WIDE_START.isoformat(),
            "end": WIDE_END.isoformat(),
        },
        "opra_cache_size": opra_count,
        "candidates": [],
    }

    for i, c in enumerate(CANDIDATES, 1):
        log.info("─" * 60)
        log.info(
            "Running candidate %d/%d: %s",
            i, len(CANDIDATES), c["name"],
        )
        log.info("Combo: %s", c["combo"])
        try:
            real = _run_candidate_real_fills(c["combo"], spy_full, vix_full)
            log.info(
                "Real-fills: wide=$%.0f, n=%d, wr=%.1f%%, +q=%d/%d, "
                "top5=%.1f%%, dd=$%.0f, real/bs_fallback=%d/%d",
                real["wide_pnl"], real["wide_n_trades"],
                real["wide_wr"] * 100,
                real["positive_quarters"], real["quarter_count"],
                real["top5_pct"] * 100,
                real["max_drawdown"],
                real["real_fills_count"], real["bs_fallback_count"],
            )
            log.info(
                "Anchors: 4/29=$%.0f, 5/01=$%.0f, 5/04=$%.0f, 5/12=$%.0f, "
                "5/05=$%.0f, 5/06=$%.0f, 5/07=$%.0f",
                real["per_day"].get("2026-04-29", 0),
                real["per_day"].get("2026-05-01", 0),
                real["per_day"].get("2026-05-04", 0),
                real["per_day"].get("2026-05-12", 0),
                real["per_day"].get("2026-05-05", 0),
                real["per_day"].get("2026-05-06", 0),
                real["per_day"].get("2026-05-07", 0),
            )
            verdict, verdict_reason = _verdict(
                real, real["per_day"].get("2026-05-05", 0.0),
            )
            log.info("Verdict: %s — %s", verdict, verdict_reason)
            report["candidates"].append({
                "name": c["name"],
                "combo": c["combo"],
                "bs_metrics": c["bs_metrics"],
                "real_fills": real,
                "verdict": verdict,
                "verdict_reason": verdict_reason,
            })
        except Exception as exc:
            log.exception("Candidate %s failed", c["name"])
            report["candidates"].append({
                "name": c["name"],
                "combo": c["combo"],
                "bs_metrics": c["bs_metrics"],
                "error": repr(exc),
                "trace": traceback.format_exc(),
                "verdict": "ERROR",
                "verdict_reason": f"Execution failed: {exc!r}",
            })

    # Overall pipeline verdict
    pass_count = sum(1 for c in report["candidates"] if c.get("verdict") == "PASS")
    fail_count = sum(1 for c in report["candidates"] if c.get("verdict") == "FAIL")
    err_count = sum(1 for c in report["candidates"] if c.get("verdict") == "ERROR")
    report["summary"] = {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": err_count,
        "overall_verdict": (
            "READY_FOR_WALK_FORWARD" if pass_count >= 1
            else "BLOCKED" if err_count >= len(CANDIDATES)
            else "ALL_FAIL"
        ),
    }

    # Write outputs
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("Wrote JSON: %s", OUT_JSON)

    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUT_DOC.write_text(_build_markdown_report(report), encoding="utf-8")
    log.info("Wrote MD:   %s", OUT_DOC)

    # Console summary
    log.info("=" * 60)
    log.info("OVERALL: %d PASS / %d FAIL / %d ERROR — verdict: %s",
             pass_count, fail_count, err_count,
             report["summary"]["overall_verdict"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
