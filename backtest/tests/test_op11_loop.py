"""OP-11 (Karpathy shadow loop) end-to-end validation.

Proves the self-improvement loop CLOSES and is safe:
  stage candidate -> per-bar dual evaluation (prod vs shadow) -> metric diff ->
  auto-ratify gate -> scorecard verdict -> (staged bump w/ REVOKE) -> rollback.

These tests guard two bugs fixed 2026-06-14:
  1. shadow.run_shadow_backtest ran production with params_overrides=None, so the
     A/B compared engine-defaults vs defaults+delta (silent no-op).
  2. orchestrator.run_backtest translated the v15.3 ribbon gates via
     _params_to_kwargs but never assigned them, so params_overrides could not
     enable them — backtests silently ran WITHOUT the v15.3 gates.

Run:  cd backtest && python -m pytest tests/test_op11_loop.py -v
Fast tests use Black-Scholes (use_real_fills=False); they validate LOOP LOGIC,
not fill accuracy. Data-dependent tests skip if the master CSV is absent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for p in (str(BACKTEST), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib import shadow  # noqa: E402
from lib.shadow import (  # noqa: E402
    ShadowMetrics,
    ShadowResult,
    apply_overrides,
    run_shadow_backtest,
    write_shadow_scorecard,
)
from lib.orchestrator import run_backtest  # noqa: E402

DATA = BACKTEST / "data"
MASTER_SPY = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
MASTER_VIX = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
PARAMS = REPO / "automation" / "state" / "params.json"
_HAS_DATA = MASTER_SPY.exists() and MASTER_VIX.exists()
_needs_data = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")


@pytest.fixture(autouse=True)
def _isolate_scorecards(tmp_path, monkeypatch):
    """Never write scorecards into the real analysis/recommendations dir."""
    monkeypatch.setattr(shadow, "RECOMMENDATIONS_DIR", tmp_path / "recs")


def _load_window(start: str, end: str):
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    return spy, vix


def _n(spy, vix, start: str, end: str, **kw) -> int:
    r = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(start),
        end_date=dt.date.fromisoformat(end),
        use_real_fills=False,
        **kw,
    )
    return len(r.trades)


def _mk_metrics(n: int, thresholds_passed: int) -> ShadowMetrics:
    return ShadowMetrics(
        n_trades=n, hit_rate=0.6, expectancy=50.0, total_pnl=5000.0,
        wl_ratio=2.0, max_drawdown=-100.0, worst_trade=-50.0,
        thresholds_passed=thresholds_passed, thresholds_total=4,
    )


def _mk_result(*, dominates: bool, n: int, thresholds: int, hash_match: bool, stable: bool) -> ShadowResult:
    sm = _mk_metrics(n, thresholds)
    eligible = dominates and hash_match and thresholds == 4 and n >= 20 and stable
    return ShadowResult(
        rule_id="R", title="t", window_start="a", window_end="b",
        data_hash="dh", data_hash_match=hash_match,
        prod_run_id="p1", prod_label="prod", prod_metrics=_mk_metrics(20, 4), prod_params_hash="ph",
        shadow_run_id="s1", shadow_label="shadow", shadow_metrics=sm, shadow_params_hash="sh",
        overrides={}, metric_deltas={}, dominates=dominates, regressed_metrics=[],
        auto_ratify_eligible=eligible,
    )


# ---------- pure logic ----------

def test_apply_overrides_deep_merge_and_purity() -> None:
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    out = apply_overrides(base, {"b": {"c": 9}, "e": 5})
    assert out == {"a": 1, "b": {"c": 9, "d": 3}, "e": 5}
    assert base == {"a": 1, "b": {"c": 2, "d": 3}}  # base not mutated


def test_apply_overrides_none_deletes() -> None:
    assert apply_overrides({"a": 1, "b": 2}, {"b": None}) == {"a": 1}


@pytest.mark.parametrize(
    "dominates,n,thresholds,hash_match,stable,want",
    [
        (True, 25, 4, True, True, "auto_ratify"),
        (True, 15, 4, True, True, "needs_review"),   # n < 20
        (True, 25, 4, True, False, "needs_review"),  # sub-window unstable (anti-overfit)
        (True, 25, 3, True, True, "needs_review"),   # not 4/4 thresholds
        (True, 25, 4, False, True, "reject"),        # data_hash mismatch
        (False, 25, 4, True, True, "needs_review"),  # regressed -> not dominate
    ],
)
def test_auto_ratify_verdict_gate(dominates, n, thresholds, hash_match, stable, want) -> None:
    res = _mk_result(dominates=dominates, n=n, thresholds=thresholds, hash_match=hash_match, stable=stable)
    path = write_shadow_scorecard(res)
    assert json.loads(path.read_text())["verdict"] == want


# ---------- engine binding (the two fixed bugs) ----------

@_needs_data
def test_override_binds_ribbon_gate() -> None:
    """params_overrides must actually change engine behavior (anti dead-knob)."""
    spy, vix = _load_window("2026-03-01", "2026-05-07")
    baseline = _n(spy, vix, "2026-03-01", "2026-05-07")
    gated = _n(spy, vix, "2026-03-01", "2026-05-07",
               params_overrides={"min_ribbon_momentum_cents": 50.0})
    assert gated < baseline, f"override did not bind: {gated} !< {baseline}"


@_needs_data
def test_full_params_applies_v153_gates() -> None:
    """The full params.json (v15.3 gates on) must fire fewer trades than the
    bare engine-default (no-gate) baseline — proves prod backtests now reflect
    live config."""
    spy, vix = _load_window("2026-03-01", "2026-05-07")
    base = json.loads(PARAMS.read_text())
    baseline = _n(spy, vix, "2026-03-01", "2026-05-07")
    gated = _n(spy, vix, "2026-03-01", "2026-05-07", params_overrides=base)
    assert gated < baseline


# ---------- full loop + read-only invariant ----------

@_needs_data
def test_shadow_loop_closes_and_is_read_only() -> None:
    spy, vix = _load_window("2026-02-01", "2026-05-07")
    before = hashlib.sha256(PARAMS.read_bytes()).hexdigest()
    # The shadow override must ACTUALLY diverge the shadow arm from the prod arm
    # on THIS window, or the read-only invariant below is tested vacuously (a
    # no-op A/B trivially leaves params.json unchanged). The prod arm runs the
    # full live params.json, where ``min_ribbon_momentum_cents`` is 0 (gate OFF)
    # -> 7 trades fire on 2026-02-01..05-07. The old override value (3.0) was a
    # NO-OP: all 7 of those prod trades already clear a 3c ribbon-momentum bar,
    # so prod==shadow and the divergence assert silently held with zero delta.
    # 10.0c is the empirical divergence cliff (filters 3 of the 7 -> 4 trades);
    # 15.0c sits on the stable 4-trade plateau (10/12/15 all -> 4) for margin.
    res = run_shadow_backtest(
        spy, vix,
        start_date=dt.date(2026, 2, 1), end_date=dt.date(2026, 5, 7),
        shadow_overrides={"min_ribbon_momentum_cents": 15.0},
        rule_id="TEST_RMOM", title="tighten rmom",
        spy_path=MASTER_SPY, vix_path=MASTER_VIX,
        use_real_fills=False, check_sub_window=True,
    )
    # prod (gate OFF) and shadow (15c conviction gate) MUST differ -> the A/B is
    # real, so the byte-identical-params assertion below genuinely proves shadow
    # mode is read-only (it ran a DIFFERENT engine config and still touched
    # nothing), not merely that an identical run changed nothing.
    assert (res.prod_metrics.n_trades, res.prod_metrics.total_pnl) != (
        res.shadow_metrics.n_trades, res.shadow_metrics.total_pnl
    )
    path = write_shadow_scorecard(res)
    assert json.loads(path.read_text())["verdict"] in {"auto_ratify", "needs_review", "reject"}
    # production params.json must be byte-identical after a shadow run
    assert hashlib.sha256(PARAMS.read_bytes()).hexdigest() == before
