"""v14_enhanced FIXED vs TRAILING vs STEPPED profit-lock variant retest — T44d.

Hypothesis (per CLAUDE.md operating principles 11 + 17 + 20):
v14_enhanced was ratified tonight (2026-05-13) with FIXED profit-lock
(threshold 5%, offset 10%). The 5/13 738C variant test (4,410 combos)
revealed that FIXED PL caps ride-the-ribbon winners at ~+10%/contract:
the actual J trade was +$2,932 but the same combo with PL armed would
have been +$304.

We test 6 PL variants on the SAME locked v14_enhanced top combo over the
SAME wide window (2025-01-01 → 2026-05-12) using REAL OPRA fills:

    A   FIXED         threshold 0.05 / offset 0.10  (current ratified)
    B1  TRAILING-20%  threshold 0.05 / offset 0.10 / trail 0.20
    B2  TRAILING-30%  threshold 0.05 / offset 0.10 / trail 0.30
    B3  TRAILING-40%  threshold 0.05 / offset 0.10 / trail 0.40
    B4  TRAILING-50%  threshold 0.05 / offset 0.10 / trail 0.50
    C   STEPPED       threshold 0.05 / offset 0.10 / rungs in module

Method:
  1. Load wide window data (2025-01-01 .. 2026-05-12).
  2. For each variant, monkey-patch `lib.orchestrator.simulate_trade_real`
     with a closure that delegates to `simulate_trade_real_trailing`
     passing variant-specific `profit_lock_mode` + `trail_pct`.
  3. Variant A (FIXED) does NOT monkey-patch (uses production
     simulator_real.simulate_trade_real directly — proves the wrapper
     produces identical numbers when mode='fixed').
  4. For each variant we monkey-patch `simulator_real`'s module-level
     exit constants (TP1_PREMIUM_PCT, RUNNER_MAX_PREMIUM_PCT,
     TP1_QTY_FRACTION) — same trick `v14_enhanced_real_fills.py` uses.
  5. Aggregate per-day, per-quarter, J-anchor, max-DD, top5, positive
     quarters. Compare to ratified Variant A baseline.

Outputs:
    backtest/autoresearch/v14_enhanced_pl_variants.py        (this script)
    analysis/recommendations/v14_enhanced-pl-variants.json   (machine-readable)
    docs/V14_ENHANCED-PL-VARIANTS-2026-05-13.md              (human-readable)

Per CLAUDE.md operating principle 20, this is the *eval* layer of an
eval-first ratification: NO production heartbeat.md / params.json
changes are made here. If TRAILING beats FIXED, the morning brief
flags the variant; J ratifies in the morning.

CLI:
    python -m autoresearch.v14_enhanced_pl_variants
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import sys
import traceback
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from lib import orchestrator as _orch  # noqa: E402
from lib import simulator_real as _sim_real  # noqa: E402
from lib.simulator_real import simulate_trade_real as _sim_real_fn  # noqa: E402
from lib.simulator_real_trailing import simulate_trade_real_trailing  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 12)

OUT_JSON = REPO.parent / "analysis" / "recommendations" / "v14_enhanced-pl-variants.json"
OUT_DOC = REPO.parent / "docs" / "V14_ENHANCED-PL-VARIANTS-2026-05-13.md"

# Locked v14_enhanced TOP combo (from analysis/recommendations/v14_enhanced-walkforward.json)
LOCKED_COMBO: dict[str, Any] = {
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

# Ratified baseline metrics (from v14_enhanced-real-fills.json candidate_1)
BASELINE_METRICS: dict[str, Any] = {
    "wide_pnl": 36449.97,
    "wide_n_trades": 317,
    "wide_wr": 0.568,
    "max_drawdown": 2857.10,
    "top5_pct": 0.371,
    "positive_quarters": 6,
}

# 6 variants to test (in order shown in report)
VARIANTS: list[dict[str, Any]] = [
    {"label": "A_fixed_baseline",        "mode": "fixed",    "trail_pct": None},
    {"label": "B1_trailing_20pct",       "mode": "trailing", "trail_pct": 0.20},
    {"label": "B2_trailing_30pct",       "mode": "trailing", "trail_pct": 0.30},
    {"label": "B3_trailing_40pct",       "mode": "trailing", "trail_pct": 0.40},
    {"label": "B4_trailing_50pct",       "mode": "trailing", "trail_pct": 0.50},
    {"label": "C_stepped",               "mode": "stepped",  "trail_pct": None},
]

# J anchor days for per-day comparison
J_ANCHORS = {
    "2026-04-29": {"j_pnl": 342, "direction": "winner"},
    "2026-05-01": {"j_pnl": 470, "direction": "winner"},
    "2026-05-04": {"j_pnl": 730, "direction": "winner"},
    "2026-05-07": {"j_pnl": 616, "direction": "winner"},
    "2026-05-12": {"j_pnl": 464, "direction": "winner"},
    "2026-05-05": {"j_pnl": -260, "direction": "loser"},
    "2026-05-06": {"j_pnl": -300, "direction": "loser"},
}

# ── Helpers ──────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _patched_sim_real_constants(
    tp1_premium_pct: float,
    runner_target_premium_pct: float,
    tp1_qty_fraction: float,
) -> Iterator[None]:
    """Mirror of v14_enhanced_real_fills._patched_sim_real_constants."""
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


@contextlib.contextmanager
def _patched_orch_simulator(
    mode: str,
    trail_pct: float,
) -> Iterator[None]:
    """Monkey-patch orchestrator's bound simulate_trade_real with a closure
    that calls simulate_trade_real_trailing in the chosen mode.

    We bind to lib.orchestrator (the place where the orchestrator looked up
    the symbol at import time), because Python resolves the imported name
    against the orchestrator module's namespace, not simulator_real's.
    """
    saved = _orch.simulate_trade_real

    def _wrapped(*args: Any, **kwargs: Any):
        return simulate_trade_real_trailing(
            *args,
            **kwargs,
            profit_lock_mode=mode,
            trail_pct=trail_pct,
        )

    _orch.simulate_trade_real = _wrapped
    try:
        yield
    finally:
        _orch.simulate_trade_real = saved


def _run_variant(
    variant: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
) -> dict[str, Any]:
    """Run one PL variant through real-fills + aggregate metrics."""
    from lib.orchestrator import run_backtest
    from autoresearch import config

    combo = LOCKED_COMBO
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

    tp1_pct = combo.get("tp1_premium_pct", 0.30)
    runner_pct = combo.get("runner_target_premium_pct", 3.0)
    tp1_frac = combo.get("tp1_qty_fraction", 2.0 / 3.0)

    mode = variant["mode"]
    trail_pct = variant["trail_pct"] if variant["trail_pct"] is not None else 0.30

    # Variant A (FIXED) just uses the unmodified simulator_real path.
    # Variants B1..B4 (TRAILING) and C (STEPPED) monkey-patch.
    with _patched_sim_real_constants(tp1_pct, runner_pct, tp1_frac):
        if mode == "fixed":
            result = run_backtest(**kwargs)
        else:
            with _patched_orch_simulator(mode, trail_pct):
                result = run_backtest(**kwargs)

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


def _verdict(variant_metrics: dict[str, Any]) -> tuple[str, str]:
    """Verdict gates (relative to baseline FIXED variant):
      PASS gates (all required):
        - wide_pnl >= baseline (no aggregate regression)
        - 5/05 still rescued (loss less negative than J's -$260)
        - 4/29 still profitable (>$100)
        - max_drawdown not significantly worse (<= baseline + $1000)
    """
    failures: list[str] = []
    wp = variant_metrics["wide_pnl"]
    p429 = variant_metrics["per_day"].get("2026-04-29", 0.0)
    p505 = variant_metrics["per_day"].get("2026-05-05", 0.0)
    p512 = variant_metrics["per_day"].get("2026-05-12", 0.0)
    dd = variant_metrics["max_drawdown"]

    if wp < BASELINE_METRICS["wide_pnl"]:
        failures.append(f"wide_pnl=${wp:.0f} < baseline=${BASELINE_METRICS['wide_pnl']:.0f}")
    if p429 < 100:
        failures.append(f"4/29=${p429:.0f} < $100")
    if p512 < 100:
        failures.append(f"5/12=${p512:.0f} < $100")
    if p505 < -260:
        failures.append(f"5/05=${p505:.0f} < J's -$260")
    if dd > BASELINE_METRICS["max_drawdown"] + 1000:
        failures.append(f"max_dd=${dd:.0f} > baseline+1000=${BASELINE_METRICS['max_drawdown']+1000:.0f}")

    if not failures:
        return "PASS", (
            f"wide_pnl=${wp:.0f}, 4/29=${p429:.0f}, 5/12=${p512:.0f}, "
            f"5/05=${p505:.0f}, max_dd=${dd:.0f}"
        )
    return "FAIL", "; ".join(failures)


def _build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# v14_enhanced Profit-Lock Variants — 2026-05-13 (T44d)")
    lines.append("")
    lines.append(f"Generated: `{report['generated_at']}`")
    lines.append("")
    lines.append("## Hypothesis")
    lines.append("")
    lines.append(
        "v14_enhanced was ratified tonight with FIXED profit-lock "
        "(threshold 5%, offset 10%). The 5/13 738C variant test (4,410 "
        "combos) showed FIXED PL caps ride-the-ribbon winners — the actual "
        "J trade was +$2,932 but the same combo with PL armed would have "
        "been +$304. TRAILING (chandelier-style) and STEPPED PL hypothesised "
        "to preserve chop-day rescue WITHOUT capping big-day upside."
    )
    lines.append("")
    lines.append("## Variants tested")
    lines.append("")
    lines.append("| Label | Mode | Threshold | Offset | Trail % |")
    lines.append("|-------|------|-----------|--------|---------|")
    for v in VARIANTS:
        trail = f"{v['trail_pct']:.0%}" if v["trail_pct"] is not None else "—"
        lines.append(
            f"| {v['label']} | {v['mode']} | "
            f"{LOCKED_COMBO['profit_lock_threshold_pct']:.0%} | "
            f"{LOCKED_COMBO['profit_lock_stop_offset_pct']:.0%} | {trail} |"
        )
    lines.append("")

    lines.append("## Locked combo (v14_enhanced winner from walk-forward)")
    lines.append("")
    lines.append("```python")
    lines.append(json.dumps(LOCKED_COMBO, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("## Per-variant verdict summary")
    lines.append("")
    lines.append(
        "| Variant | wide_pnl | n | WR | max_dd | top5 | +Q | "
        "4/29 | 5/01 | 5/04 | 5/07 | 5/12 | 5/05 | 5/06 | Verdict |"
    )
    lines.append(
        "|---------|---------:|---:|----:|-------:|-----:|---:|"
        "------:|------:|------:|------:|------:|------:|------:|---------|"
    )
    for v in report["variants"]:
        m = v.get("metrics", {})
        if "error" in v:
            lines.append(f"| {v['label']} | ERROR | | | | | | | | | | | | | **ERROR** |")
            continue
        per_day = m.get("per_day", {})
        lines.append(
            f"| {v['label']} "
            f"| ${m.get('wide_pnl', 0):,.0f} "
            f"| {m.get('wide_n_trades', 0)} "
            f"| {m.get('wide_wr', 0):.1%} "
            f"| ${m.get('max_drawdown', 0):,.0f} "
            f"| {m.get('top5_pct', 0):.1%} "
            f"| {m.get('positive_quarters', 0)} "
            f"| ${per_day.get('2026-04-29', 0):.0f} "
            f"| ${per_day.get('2026-05-01', 0):.0f} "
            f"| ${per_day.get('2026-05-04', 0):.0f} "
            f"| ${per_day.get('2026-05-07', 0):.0f} "
            f"| ${per_day.get('2026-05-12', 0):.0f} "
            f"| ${per_day.get('2026-05-05', 0):.0f} "
            f"| ${per_day.get('2026-05-06', 0):.0f} "
            f"| **{v.get('verdict', 'ERROR')}** |"
        )
    lines.append("")

    lines.append("## Verdict gates")
    lines.append("")
    lines.append("- `wide_pnl ≥ baseline` (FIXED: $36,449.97)")
    lines.append("- `4/29 ≥ $100`")
    lines.append("- `5/12 ≥ $100`")
    lines.append("- `5/05 ≥ -$260` (J's loss)")
    lines.append("- `max_dd ≤ baseline + $1,000` ($3,857.10)")
    lines.append("")

    # Per-variant deep dive
    for v in report["variants"]:
        lines.append(f"## {v['label']}")
        lines.append("")
        if "error" in v:
            lines.append(f"**ERROR:** `{v['error']}`")
            lines.append("")
            lines.append("```")
            lines.append(v.get("trace", ""))
            lines.append("```")
            continue
        m = v.get("metrics", {})
        lines.append(f"- mode: `{v['mode']}`")
        lines.append(f"- trail_pct: `{v['trail_pct']}`")
        lines.append(f"- wide_pnl: **${m.get('wide_pnl', 0):,.2f}** vs baseline ${BASELINE_METRICS['wide_pnl']:,.2f} (Δ ${m.get('wide_pnl', 0) - BASELINE_METRICS['wide_pnl']:+,.2f})")
        lines.append(f"- n_trades: {m.get('wide_n_trades', 0)} vs baseline {BASELINE_METRICS['wide_n_trades']}")
        lines.append(f"- wr: {m.get('wide_wr', 0):.1%} vs baseline {BASELINE_METRICS['wide_wr']:.1%}")
        lines.append(f"- max_drawdown: ${m.get('max_drawdown', 0):,.2f} vs baseline ${BASELINE_METRICS['max_drawdown']:,.2f}")
        lines.append(f"- top5_pct: {m.get('top5_pct', 0):.1%}")
        lines.append(f"- positive_quarters: {m.get('positive_quarters', 0)}/{m.get('quarter_count', 0)}")
        lines.append(f"- real_fills/bs_fallback: {m.get('real_fills_count', 0)}/{m.get('bs_fallback_count', 0)}")
        lines.append("")
        lines.append("**Per-J-anchor:**")
        lines.append("")
        lines.append("| Date | J PnL | Variant PnL | vs Baseline |")
        lines.append("|------|------:|------------:|------------:|")
        per_day = m.get("per_day", {})
        baseline_var = next(
            (x for x in report["variants"] if x["label"] == "A_fixed_baseline"),
            None,
        )
        baseline_per_day = (
            baseline_var.get("metrics", {}).get("per_day", {})
            if baseline_var else {}
        )
        for d, anchor in J_ANCHORS.items():
            this = per_day.get(d, 0.0)
            base = baseline_per_day.get(d, 0.0)
            delta = this - base
            lines.append(
                f"| {d} ({anchor['direction']}) "
                f"| ${anchor['j_pnl']} "
                f"| ${this:.0f} "
                f"| {delta:+.0f} |"
            )
        lines.append("")
        lines.append("**Per-quarter:**")
        per_q = m.get("per_quarter", {})
        for q in sorted(per_q.keys()):
            lines.append(f"- {q}: ${per_q[q]:,.2f}")
        lines.append("")
        lines.append(f"**Verdict:** {v.get('verdict', 'ERROR')}")
        lines.append(f"**Reason:** {v.get('verdict_reason', '')}")
        lines.append("")

    lines.append("## Best variant")
    lines.append("")
    pass_variants = [v for v in report["variants"] if v.get("verdict") == "PASS"]
    if pass_variants:
        best = max(pass_variants, key=lambda v: v.get("metrics", {}).get("wide_pnl", 0))
        lines.append(
            f"**{best['label']}** with wide_pnl "
            f"${best.get('metrics', {}).get('wide_pnl', 0):,.0f} "
            f"vs baseline FIXED ${BASELINE_METRICS['wide_pnl']:,.0f} "
            f"(Δ ${best.get('metrics', {}).get('wide_pnl', 0) - BASELINE_METRICS['wide_pnl']:+,.0f})."
        )
        lines.append("")
        if best["label"] == "A_fixed_baseline":
            lines.append(
                "Baseline FIXED is still the winner. No variant beats the "
                "ratified setting. **No morning ratification change needed.**"
            )
        else:
            lines.append(
                f"**Recommended morning brief headline:** v14_enhanced should "
                f"be ratified with **{best['mode'].upper()} PL** "
                f"(trail_pct={best['trail_pct']}) — NOT fixed PL=5%/10%."
            )
            lines.append("")
            lines.append("**Required follow-up before live deploy:**")
            lines.append("- Walk-forward validate the new PL on the train/test split")
            lines.append("- Update `analysis/recommendations/v14_enhanced-real-fills.json`")
            lines.append("- Update Monday-Ready Checklist with the new PL setting")
            lines.append("- J explicit ratification before any heartbeat.md / params.json change")
    else:
        lines.append(
            "**Zero variants passed all gates.** Baseline FIXED stays as the "
            "ratified setting until further research."
        )
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- **Per-quality exit-knob matrix NOT applied.** Same caveat as "
        "v14_enhanced-real-fills.json — orchestrator's TRENDLINE/LEVEL/"
        "ELITE/SUPER per-quality `_grinder_overrides` only fires through "
        "the BS path."
    )
    lines.append(
        "- **BS-sim fallback on OPRA cache miss.** Each variant reports its "
        "fallback %; if >20% the result is less than a true real-fills test."
    )
    lines.append(
        "- **TRAILING is asymmetric.** When a winner runs, trailing extends "
        "the floor; when a chop-day reverses just past arm threshold, "
        "trailing locks +5% (initial arm offset). FIXED locks +10% on the "
        "same chop-day. So small chop-day P&L might be slightly LOWER with "
        "trailing — that's the expected trade-off, not a bug."
    )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Script: `backtest/autoresearch/v14_enhanced_pl_variants.py`")
    lines.append(f"- Wrapper: `backtest/lib/simulator_real_trailing.py`")
    lines.append(f"- Wide window: `{WIDE_START}` → `{WIDE_END}`")
    lines.append(f"- OPRA cache: `backtest/data/options/` ({report.get('opra_cache_size', '?')} contracts)")
    lines.append(f"- Master SPY/VIX: `data/spy_5m_2025-01-01_2026-05-12.csv`")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    log.info("Loading wide window data %s .. %s", WIDE_START, WIDE_END)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
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

    opra_dir = REPO / "data" / "options"
    opra_count = len(list(opra_dir.glob("*.csv"))) if opra_dir.exists() else 0

    report = {
        "generated_at": dt.datetime.now().isoformat(),
        "rule_id": "v14_enhanced_pl_variants",
        "wide_window": {
            "start": WIDE_START.isoformat(),
            "end": WIDE_END.isoformat(),
        },
        "opra_cache_size": opra_count,
        "locked_combo": LOCKED_COMBO,
        "baseline_metrics": BASELINE_METRICS,
        "variants": [],
    }

    for i, v in enumerate(VARIANTS, 1):
        log.info("─" * 60)
        log.info(
            "Running variant %d/%d: %s (mode=%s, trail_pct=%s)",
            i, len(VARIANTS), v["label"], v["mode"], v["trail_pct"],
        )
        try:
            metrics = _run_variant(v, spy_full, vix_full)
            log.info(
                "Result: wide=$%.0f, n=%d, wr=%.1f%%, dd=$%.0f, top5=%.1f%%, +Q=%d/%d",
                metrics["wide_pnl"], metrics["wide_n_trades"],
                metrics["wide_wr"] * 100,
                metrics["max_drawdown"], metrics["top5_pct"] * 100,
                metrics["positive_quarters"], metrics["quarter_count"],
            )
            log.info(
                "Anchors: 4/29=$%.0f, 5/01=$%.0f, 5/04=$%.0f, 5/07=$%.0f, "
                "5/12=$%.0f, 5/05=$%.0f, 5/06=$%.0f",
                metrics["per_day"].get("2026-04-29", 0),
                metrics["per_day"].get("2026-05-01", 0),
                metrics["per_day"].get("2026-05-04", 0),
                metrics["per_day"].get("2026-05-07", 0),
                metrics["per_day"].get("2026-05-12", 0),
                metrics["per_day"].get("2026-05-05", 0),
                metrics["per_day"].get("2026-05-06", 0),
            )
            verdict, verdict_reason = _verdict(metrics)
            log.info("Verdict: %s — %s", verdict, verdict_reason)
            report["variants"].append({
                "label": v["label"],
                "mode": v["mode"],
                "trail_pct": v["trail_pct"],
                "metrics": metrics,
                "verdict": verdict,
                "verdict_reason": verdict_reason,
            })
        except Exception as exc:
            log.exception("Variant %s failed", v["label"])
            report["variants"].append({
                "label": v["label"],
                "mode": v["mode"],
                "trail_pct": v["trail_pct"],
                "error": repr(exc),
                "trace": traceback.format_exc(),
                "verdict": "ERROR",
                "verdict_reason": f"Execution failed: {exc!r}",
            })

    pass_count = sum(1 for v in report["variants"] if v.get("verdict") == "PASS")
    fail_count = sum(1 for v in report["variants"] if v.get("verdict") == "FAIL")
    err_count = sum(1 for v in report["variants"] if v.get("verdict") == "ERROR")

    pass_variants = [v for v in report["variants"] if v.get("verdict") == "PASS"]
    if pass_variants:
        best = max(pass_variants, key=lambda v: v.get("metrics", {}).get("wide_pnl", 0))
        report["best_variant"] = best["label"]
        report["best_wide_pnl"] = best.get("metrics", {}).get("wide_pnl", 0)
    else:
        report["best_variant"] = None
        report["best_wide_pnl"] = None

    report["summary"] = {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": err_count,
        "overall_verdict": (
            "TRAILING_OR_STEPPED_BEATS_FIXED"
            if pass_variants
               and pass_variants[0]["label"] != "A_fixed_baseline"
               and report["best_variant"] != "A_fixed_baseline"
            else "FIXED_REMAINS_OPTIMAL"
            if pass_variants and report["best_variant"] == "A_fixed_baseline"
            else "ALL_FAIL_OR_ERROR"
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("Wrote JSON: %s", OUT_JSON)

    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUT_DOC.write_text(_build_markdown_report(report), encoding="utf-8")
    log.info("Wrote MD:   %s", OUT_DOC)

    log.info("=" * 60)
    log.info(
        "OVERALL: %d PASS / %d FAIL / %d ERROR — verdict: %s — best: %s",
        pass_count, fail_count, err_count,
        report["summary"]["overall_verdict"],
        report["best_variant"] or "n/a",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
