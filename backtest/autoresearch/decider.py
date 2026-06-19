"""Keep-or-revert decision after running a candidate modification.

Mirrors Karpathy's `if val_loss < baseline: git commit else: git revert`.
For trading, we add hard gates (KEEP_THRESHOLDS) so a modification that
improves Sharpe but breaks a deployment threshold is still rejected.

Train/validate split (added 2026-05-08):
    `decide_with_validation` runs the keep/revert check on TRAIN metrics
    (must improve sharpe + pass thresholds) AND additionally rejects if the
    candidate's VALIDATE sharpe regresses by more than MAX_VALIDATION_REGRESSION
    vs the baseline's VALIDATE sharpe. This is standard ML hygiene:
    overfitting to the training window gets caught by the held-out set.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from . import config
from .metrics import TradeMetrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    """Outcome of comparing candidate metrics vs baseline."""

    keep: bool
    reason: str
    delta_sharpe: float
    delta_pnl: float
    delta_winrate: float
    threshold_failures: list[str]

    def to_dict(self) -> dict:
        return {
            "keep": self.keep,
            "reason": self.reason,
            "delta_sharpe": round(self.delta_sharpe, 4),
            "delta_pnl": round(self.delta_pnl, 2),
            "delta_winrate": round(self.delta_winrate, 4),
            "threshold_failures": self.threshold_failures,
        }


def _check_thresholds(m: TradeMetrics, baseline: dict[str, Any]) -> list[str]:
    """Return list of hard-gate failures. Empty list = all green."""
    t = config.KEEP_THRESHOLDS
    fails: list[str] = []
    if m.n_trades < t.min_trades:
        fails.append(f"n_trades<{t.min_trades} (got {m.n_trades})")
    if m.win_rate < t.min_win_rate:
        fails.append(f"win_rate<{t.min_win_rate:.0%} (got {m.win_rate:.0%})")
    if math.isfinite(m.wl_ratio) and m.wl_ratio < t.min_wl_ratio:
        fails.append(f"wl_ratio<{t.min_wl_ratio} (got {m.wl_ratio:.2f})")
    if m.expectancy < t.min_expectancy:
        fails.append(f"expectancy<={t.min_expectancy} (got {m.expectancy:.2f})")
    # Drawdown-regression check needs a baseline.
    base_dd = baseline.get("max_drawdown")
    if base_dd is not None and base_dd < 0:
        # Both baseline and candidate are negative; allow new DD to be at most
        # max_drawdown_regression times worse (more negative).
        limit = base_dd * t.max_drawdown_regression
        if m.max_drawdown < limit:
            fails.append(
                f"max_dd regression: baseline={base_dd:.0f} candidate={m.max_drawdown:.0f} "
                f"(limit={limit:.0f})"
            )
    return fails


def decide(candidate: TradeMetrics, baseline: dict[str, Any] | None) -> Decision:
    """Compare candidate run against the current baseline (train-only, legacy)."""
    base_sharpe = float(baseline.get("sharpe_daily", 0.0)) if baseline else 0.0
    base_pnl = float(baseline.get("total_pnl", 0.0)) if baseline else 0.0
    base_wr = float(baseline.get("win_rate", 0.0)) if baseline else 0.0
    delta_sharpe = candidate.sharpe_daily - base_sharpe
    delta_pnl = candidate.total_pnl - base_pnl
    delta_winrate = candidate.win_rate - base_wr

    fails = _check_thresholds(candidate, baseline or {})

    if fails:
        return Decision(
            keep=False,
            reason=f"hard gate failure: {fails[0]}",
            delta_sharpe=delta_sharpe,
            delta_pnl=delta_pnl,
            delta_winrate=delta_winrate,
            threshold_failures=fails,
        )

    if delta_sharpe > 0:
        return Decision(
            keep=True,
            reason=f"sharpe improved by {delta_sharpe:+.3f}",
            delta_sharpe=delta_sharpe,
            delta_pnl=delta_pnl,
            delta_winrate=delta_winrate,
            threshold_failures=[],
        )

    return Decision(
        keep=False,
        reason=f"sharpe did not improve ({delta_sharpe:+.3f})",
        delta_sharpe=delta_sharpe,
        delta_pnl=delta_pnl,
        delta_winrate=delta_winrate,
        threshold_failures=[],
    )


def decide_with_validation(
    train_candidate: TradeMetrics,
    train_baseline: dict[str, Any] | None,
    validate_candidate: TradeMetrics,
    validate_baseline: dict[str, Any] | None,
    objective: str = config.DEFAULT_OBJECTIVE,
) -> Decision:
    """Train/validate split keep/revert.

    Default behaviour (objective="train_sharpe"):
        KEEP iff train hard gates pass AND train sharpe improves AND validate
        sharpe doesn't regress by >MAX_VALIDATION_REGRESSION.

    Validate-side objectives (objective in {"validate_sharpe", "validate_pnl",
    "validate_expectancy"}):
        KEEP iff train hard gates pass AND the chosen VALIDATE metric improves.
        Train hard gates still apply (we won't keep an overfit garbage run that
        coincidentally has good validate numbers), but the train sharpe
        improvement check is replaced by the validate-side improvement check.

    The validate hard gates are NOT enforced — the validate window is
    typically small (~60 days) and trade counts are too noisy.
    """
    if objective not in config.OBJECTIVES:
        raise ValueError(
            f"unknown objective '{objective}'; choices: {config.OBJECTIVES}"
        )

    # Train hard gates always apply. We bypass decide()'s sharpe-improved check
    # so we can substitute a validate-side check below when requested.
    train_fails = _check_thresholds(train_candidate, train_baseline or {})
    train_base_sharpe = float((train_baseline or {}).get("sharpe_daily", 0.0))
    train_base_pnl = float((train_baseline or {}).get("total_pnl", 0.0))
    train_base_wr = float((train_baseline or {}).get("win_rate", 0.0))
    train_delta_sharpe = train_candidate.sharpe_daily - train_base_sharpe
    train_delta_pnl = train_candidate.total_pnl - train_base_pnl
    train_delta_wr = train_candidate.win_rate - train_base_wr

    if train_fails:
        return Decision(
            keep=False,
            reason=f"hard gate failure: {train_fails[0]}",
            delta_sharpe=train_delta_sharpe,
            delta_pnl=train_delta_pnl,
            delta_winrate=train_delta_wr,
            threshold_failures=train_fails,
        )

    # Compute the improvement check based on the chosen objective.
    if objective == "train_sharpe":
        if train_delta_sharpe <= 0:
            return Decision(
                keep=False,
                reason=f"train sharpe did not improve ({train_delta_sharpe:+.3f})",
                delta_sharpe=train_delta_sharpe,
                delta_pnl=train_delta_pnl,
                delta_winrate=train_delta_wr,
                threshold_failures=[],
            )
    else:
        # validate_sharpe / validate_pnl / validate_expectancy
        vb = validate_baseline or {}
        if objective == "validate_sharpe":
            base = float(vb.get("sharpe_daily", 0.0))
            cand = validate_candidate.sharpe_daily
            label = "validate sharpe"
        elif objective == "validate_pnl":
            base = float(vb.get("total_pnl", 0.0))
            cand = validate_candidate.total_pnl
            label = "validate pnl"
        else:  # validate_expectancy
            base = float(vb.get("expectancy", 0.0))
            cand = validate_candidate.expectancy
            label = "validate expectancy"
        if cand <= base:
            return Decision(
                keep=False,
                reason=f"{label} did not improve ({cand:+.3f} vs baseline {base:+.3f})",
                delta_sharpe=train_delta_sharpe,
                delta_pnl=train_delta_pnl,
                delta_winrate=train_delta_wr,
                threshold_failures=[],
            )

    # Train improved (or the validate objective improved). Now apply the
    # validate-sharpe regression guard for ALL objectives — even when
    # optimizing on validate, we still don't want validate sharpe to crater.
    base_val_sharpe = (
        float(validate_baseline.get("sharpe_daily", 0.0)) if validate_baseline else 0.0
    )
    val_sharpe = validate_candidate.sharpe_daily
    delta_val_sharpe = val_sharpe - base_val_sharpe

    # Compute the maximum allowed regression. If baseline validate sharpe is
    # positive, allow at most 20% drop. If baseline is <= 0, only allow improvement.
    if base_val_sharpe > 0:
        floor = base_val_sharpe * (1 - config.MAX_VALIDATION_REGRESSION)
        if val_sharpe < floor:
            return Decision(
                keep=False,
                reason=(
                    f"validate sharpe regressed too far: {val_sharpe:.3f} < "
                    f"floor {floor:.3f} (baseline {base_val_sharpe:.3f})"
                ),
                delta_sharpe=train_delta_sharpe,
                delta_pnl=train_delta_pnl,
                delta_winrate=train_delta_wr,
                threshold_failures=[
                    f"validate_sharpe_regression: {val_sharpe:.3f} vs floor {floor:.3f}"
                ],
            )
    else:
        # Baseline validate sharpe is non-positive; require candidate to not
        # be MORE negative.
        if val_sharpe < base_val_sharpe:
            return Decision(
                keep=False,
                reason=(
                    f"validate sharpe degraded: {val_sharpe:.3f} < "
                    f"baseline {base_val_sharpe:.3f}"
                ),
                delta_sharpe=train_delta_sharpe,
                delta_pnl=train_delta_pnl,
                delta_winrate=train_delta_wr,
                threshold_failures=[
                    f"validate_sharpe_regression: {val_sharpe:.3f} vs {base_val_sharpe:.3f}"
                ],
            )

    return Decision(
        keep=True,
        reason=(
            f"train sharpe {train_delta_sharpe:+.3f}, "
            f"validate sharpe delta {delta_val_sharpe:+.3f}"
        ),
        delta_sharpe=train_delta_sharpe,
        delta_pnl=train_delta_pnl,
        delta_winrate=train_delta_wr,
        threshold_failures=[],
    )
