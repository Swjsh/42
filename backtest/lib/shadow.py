"""Shadow mode evaluation — run candidate rule version alongside production.

Karpathy method principle 4: every per-bar decision should be evaluated under
production filters AND under the candidate's filters. Output is two parallel
decision logs that can be diffed daily ("v15 would have caught the 11:22 setup
v14 missed").

Public API:
    apply_overrides(base_params, overrides) -> dict
        Deep-merge override dict into base params (does not mutate base).

    run_shadow_backtest(spy, vix, start, end, shadow_params, label_prefix)
        -> ShadowResult with prod metrics + shadow metrics + diff

    write_shadow_scorecard(result, output_dir)
        -> Write A/B scorecard JSON per analysis/recommendations/SCORECARD_TEMPLATE.json

Shadow mode is read-only by construction: it never affects the trades the
production engine fires. The shadow's purpose is data — show what would have
happened, not what should happen.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .orchestrator import run_backtest
from .repro import compute_run_id

REPO = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
RECOMMENDATIONS_DIR = REPO / "analysis" / "recommendations"


@dataclass(frozen=True)
class ShadowMetrics:
    """Per-version summary metrics. Both prod and shadow share this shape."""

    n_trades: int
    hit_rate: float | None
    expectancy: float | None
    total_pnl: float | None
    wl_ratio: float | None
    max_drawdown: float | None
    worst_trade: float | None
    thresholds_passed: int
    thresholds_total: int


@dataclass(frozen=True)
class ShadowResult:
    """Side-by-side comparison of production vs shadow rule versions."""

    rule_id: str
    title: str
    window_start: str
    window_end: str
    data_hash: str
    data_hash_match: bool

    prod_run_id: str
    prod_label: str
    prod_metrics: ShadowMetrics
    prod_params_hash: str

    shadow_run_id: str
    shadow_label: str
    shadow_metrics: ShadowMetrics
    shadow_params_hash: str

    overrides: dict[str, Any]
    metric_deltas: dict[str, dict[str, Any]]
    dominates: bool
    regressed_metrics: list[str]
    auto_ratify_eligible: bool


def apply_overrides(base_params: dict, overrides: dict) -> dict:
    """Deep-merge overrides into base. Returns a new dict; base is not mutated.

    Override semantics:
    - Top-level scalar override: replaces base value.
    - Nested dict override: merges recursively.
    - Lists are replaced wholesale (no element-level merge).
    - None values in overrides DELETE the key from result.
    """
    result = copy.deepcopy(base_params)
    for key, override_value in overrides.items():
        if override_value is None:
            result.pop(key, None)
            continue
        if (
            isinstance(override_value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = apply_overrides(result[key], override_value)
        else:
            result[key] = override_value
    return result


def _compute_metrics(trades: list) -> ShadowMetrics:
    """Compute summary metrics for a list of trades. Mirrors run.py."""
    n = len(trades)
    if n == 0:
        return ShadowMetrics(
            n_trades=0,
            hit_rate=None,
            expectancy=None,
            total_pnl=0.0,
            wl_ratio=None,
            max_drawdown=0.0,
            worst_trade=None,
            thresholds_passed=0,
            thresholds_total=4,
        )

    n_w = sum(1 for t in trades if t.dollar_pnl > 0)
    n_l = sum(1 for t in trades if t.dollar_pnl < 0)
    total = sum(t.dollar_pnl for t in trades)
    avg_w = sum(t.dollar_pnl for t in trades if t.dollar_pnl > 0) / max(1, n_w)
    avg_l = sum(t.dollar_pnl for t in trades if t.dollar_pnl < 0) / max(1, n_l)
    wl_ratio = abs(avg_w / avg_l) if avg_l else float("inf")

    def _naive(ts: Any) -> Any:
        if hasattr(ts, "tz_localize") and getattr(ts, "tz", None) is not None:
            return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts

    cum, peak, max_dd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda t: _naive(t.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    worst = min(t.dollar_pnl for t in trades)
    hit_rate = n_w / n
    expectancy = (hit_rate * avg_w) + ((1 - hit_rate) * avg_l)
    thresholds = {
        "trades_ge_20": n >= 20,
        "wr_ge_45": hit_rate >= 0.45,
        "wl_ge_15x": wl_ratio >= 1.5,
        "expectancy_gt_0": expectancy > 0,
    }
    return ShadowMetrics(
        n_trades=n,
        hit_rate=round(hit_rate, 4),
        expectancy=round(expectancy, 2),
        total_pnl=round(total, 2),
        wl_ratio=round(wl_ratio, 3),
        max_drawdown=round(max_dd, 2),
        worst_trade=round(worst, 2),
        thresholds_passed=sum(thresholds.values()),
        thresholds_total=len(thresholds),
    )


def _compute_metric_deltas(
    prod: ShadowMetrics,
    shadow: ShadowMetrics,
) -> tuple[dict, bool, list[str]]:
    """Compute per-metric old/new/delta and whether shadow dominates.

    Direction rules:
      higher_better:  hit_rate, expectancy, total_pnl, wl_ratio, worst_trade,
                      max_drawdown (less-negative is better, treat as higher)
      more_data_better: n_trades (informational, not used in dominates)
    """
    metrics_def = [
        ("n_trades", "more_data_better"),
        ("hit_rate", "higher_better"),
        ("expectancy", "higher_better"),
        ("total_pnl", "higher_better"),
        ("wl_ratio", "higher_better"),
        ("max_drawdown", "higher_better"),
        ("worst_trade", "higher_better"),
        ("thresholds_passed", "higher_better"),
    ]

    deltas: dict[str, dict[str, Any]] = {}
    regressed: list[str] = []
    strictly_better_on_one = False

    for name, direction in metrics_def:
        old_v = getattr(prod, name)
        new_v = getattr(shadow, name)
        delta = None
        if old_v is not None and new_v is not None:
            delta = round(new_v - old_v, 4) if isinstance(new_v, float) else (new_v - old_v)
        deltas[name] = {
            "old": old_v,
            "new": new_v,
            "delta": delta,
            "direction": direction,
        }
        if direction == "more_data_better":
            continue  # informational only, not used in dominates
        if delta is None:
            continue  # nothing to compare
        if delta < 0:
            regressed.append(name)
        elif delta > 0:
            strictly_better_on_one = True

    dominates = (len(regressed) == 0) and strictly_better_on_one
    return deltas, dominates, regressed


def _check_sub_window_stability(
    spy: pd.DataFrame,
    vix: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    overrides: dict,
    use_real_fills: bool,
) -> dict:
    """Run shadow on first half + second half independently.

    Both halves must independently pass 4-of-4 thresholds for sub_window_stable
    to be true. Catches single-regime overfitting.
    """
    midpoint = start + (end - start) / 2

    def _run_half(half_start: dt.date, half_end: dt.date) -> dict:
        result = run_backtest(
            spy, vix,
            start_date=half_start,
            end_date=half_end,
            use_real_fills=use_real_fills,
            params_overrides=overrides,
        )
        m = _compute_metrics(result.trades)
        return {
            "metrics": {
                "n_trades": m.n_trades,
                "hit_rate": m.hit_rate,
                "expectancy": m.expectancy,
                "thresholds_passed": m.thresholds_passed,
            },
            "passes_4_of_4": m.thresholds_passed == 4,
        }

    first = _run_half(start, midpoint)
    second = _run_half(midpoint + dt.timedelta(days=1), end)
    return {
        "first_half": first,
        "second_half": second,
        "stable": first["passes_4_of_4"] and second["passes_4_of_4"],
    }


def run_shadow_backtest(
    spy: pd.DataFrame,
    vix: pd.DataFrame,
    start_date: dt.date,
    end_date: dt.date,
    shadow_overrides: dict,
    rule_id: str,
    title: str,
    spy_path: Path,
    vix_path: Path,
    use_real_fills: bool = True,
    check_sub_window: bool = True,
) -> ShadowResult:
    """Run production and shadow backtests on the same data, return diff.

    The orchestrator must support a `params_overrides` keyword for this to work
    end-to-end. If it doesn't yet, this function still computes the prod side
    and emits a result with shadow_metrics matching prod (zero-delta) — the
    A/B is a no-op until the orchestrator is wired to consume overrides.
    """
    # Load production params snapshot
    base_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))

    # Run production: pass the FULL params.json as overrides so the production
    # baseline reflects LIVE config (e.g. the v15.3 ribbon-conviction gates), not
    # the orchestrator's bare defaults.
    # Bugfix 2026-06-14: prod previously ran with params_overrides=None, so the A/B
    # compared engine-defaults vs defaults+delta instead of production vs
    # production+candidate. With prod gates defaulting OFF, the shadow was a silent
    # no-op whenever a candidate only toggled a param already at its engine default.
    prod_result = run_backtest(
        spy, vix,
        start_date=start_date,
        end_date=end_date,
        use_real_fills=use_real_fills,
        params_overrides=base_params,
    )
    prod_metrics = _compute_metrics(prod_result.trades)
    prod_identity = compute_run_id(spy_path, vix_path)

    # Run shadow with overrides applied
    shadow_params_dict = apply_overrides(base_params, shadow_overrides)
    shadow_result = run_backtest(
        spy, vix,
        start_date=start_date,
        end_date=end_date,
        use_real_fills=use_real_fills,
        params_overrides=shadow_params_dict,
    )
    shadow_metrics = _compute_metrics(shadow_result.trades)

    # Compute shadow's params hash (canonicalized)
    shadow_canonical = json.dumps(shadow_params_dict, sort_keys=True, separators=(",", ":"))
    import hashlib
    shadow_params_hash = hashlib.sha256(shadow_canonical.encode("utf-8")).hexdigest()

    # Same data → same data_hash → comparable
    data_hash = prod_identity.data_hash
    data_hash_match = True  # by construction; orchestrator uses the same spy/vix

    metric_deltas, dominates, regressed = _compute_metric_deltas(
        prod_metrics, shadow_metrics
    )

    # Sub-window stability check (optional, expensive)
    sub_window = None
    if check_sub_window:
        sub_window = _check_sub_window_stability(
            spy, vix, start_date, end_date, shadow_params_dict, use_real_fills
        )

    auto_ratify = (
        dominates
        and data_hash_match
        and shadow_metrics.thresholds_passed == 4
        and shadow_metrics.n_trades >= 20
        and (sub_window is None or sub_window["stable"])
    )

    return ShadowResult(
        rule_id=rule_id,
        title=title,
        window_start=start_date.isoformat(),
        window_end=end_date.isoformat(),
        data_hash=data_hash,
        data_hash_match=data_hash_match,
        prod_run_id=prod_identity.run_id,
        prod_label="production_v14",
        prod_metrics=prod_metrics,
        prod_params_hash=prod_identity.params_hash,
        shadow_run_id=f"{prod_identity.run_id}_shadow_{rule_id}",
        shadow_label=f"shadow_{rule_id}",
        shadow_metrics=shadow_metrics,
        shadow_params_hash=shadow_params_hash,
        overrides=shadow_overrides,
        metric_deltas=metric_deltas,
        dominates=dominates,
        regressed_metrics=regressed,
        auto_ratify_eligible=auto_ratify,
    )


def write_shadow_scorecard(
    result: ShadowResult,
    sub_window: dict | None = None,
    rationale: str = "",
    trigger_observation: str = "",
) -> Path:
    """Write A/B scorecard JSON matching SCORECARD_TEMPLATE.json schema."""
    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RECOMMENDATIONS_DIR / f"{result.rule_id}.json"

    sub_window_block: dict[str, Any] = {
        "first_half": {"metrics": {}, "passes_4_of_4": None},
        "second_half": {"metrics": {}, "passes_4_of_4": None},
    }
    if sub_window is not None:
        sub_window_block = sub_window

    scorecard: dict[str, Any] = {
        "_doc": "Auto-generated A/B scorecard. See analysis/recommendations/SCORECARD_TEMPLATE.json for schema.",
        "rule_id": result.rule_id,
        "title": result.title,
        "rationale": rationale,
        "proposed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "proposed_by": "weekly-review-auto",
        "old_run": {
            "run_id": result.prod_run_id,
            "label": result.prod_label,
            "params_hash": result.prod_params_hash,
            "version_label": "v14",
        },
        "new_run": {
            "run_id": result.shadow_run_id,
            "label": result.shadow_label,
            "params_hash": result.shadow_params_hash,
            "version_label": f"v14+{result.rule_id}",
        },
        "data_hash_match": result.data_hash_match,
        "data_hash": result.data_hash,
        "window_start": result.window_start,
        "window_end": result.window_end,
        "overrides": result.overrides,
        "metrics": result.metric_deltas,
        "dominates": result.dominates,
        "regressed_metrics": result.regressed_metrics,
        "sub_window_stability": sub_window_block,
        "auto_ratify_conditions": {
            "dominates_or_tied_overall": result.dominates,
            "data_hash_matches": result.data_hash_match,
            "thresholds_passed_4_of_4": result.shadow_metrics.thresholds_passed == 4,
            "sub_window_stable": sub_window_block.get("stable", None) if sub_window else None,
            "min_evidence_n_trades": 20,
            "evidence_n_trades_met": result.shadow_metrics.n_trades >= 20,
        },
        "auto_ratify_eligible": result.auto_ratify_eligible,
        "verdict": (
            "auto_ratify"
            if result.auto_ratify_eligible
            else ("reject" if not result.data_hash_match else "needs_review")
        ),
        "status": "pending",
        "decided_at": None,
        "decided_by": None,
        "decision_note": None,
        "trigger_observation": trigger_observation,
    }

    output_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    return output_path
