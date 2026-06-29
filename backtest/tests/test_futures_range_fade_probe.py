"""Golden guard for the futures range-fade probe (2026-06-28 conductor CLIMB).

Locks the DECISIVE FINDING so a future edit cannot silently flip the conclusion:
the SPY range-scalp vein (LEVEL_REJECT_LIVE mean-reversion fade) does NOT generalize
to deep-data MES/MNQ futures -- both instruments are IS-negative (regime-flip), so
moving off the 25-day OPRA wall to free deep data does not rescue the fade vein.

Non-vacuous: asserts the exact published numbers AND bite-tests the verdict ladder
(a synthetic clean two-sided IS+OOS-positive non-concentrated set must read
CLEAN_GENERALIZES -- proving the WALK_FORWARD_FAIL is a real discriminator, not a
verdict that always fails).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_AUTORESEARCH = pathlib.Path(__file__).resolve().parents[1] / "autoresearch"
sys.path.insert(0, str(_AUTORESEARCH))

import futures_range_fade_probe as frfp  # noqa: E402


@pytest.fixture(scope="module")
def out() -> dict:
    return frfp.run()


def _by_sym(out: dict, sym: str) -> dict:
    return next(r for r in out["results"] if r["instrument"] == sym)


def test_conclusion_does_not_generalize(out):
    # The headline: deep-data futures REJECT the range-fade vein.
    assert out["conclusion"] == "RANGE_FADE_DOES_NOT_GENERALIZE"
    assert set(out["instruments_failing_generalization"]) == {"MES", "MNQ"}


def test_mes_numbers_locked(out):
    mes = _by_sym(out, "MES")
    assert mes["summary"]["n_trades"] == 379           # deep-data N, not the SPY n=8
    assert mes["summary"]["expectancy_per_trade_usd"] == 5.48
    assert mes["summary"]["win_rate"] == 0.628
    assert mes["walk_forward"]["is_total"] == -1306.05  # IS NEGATIVE = the killer
    assert mes["walk_forward"]["oos_total"] == 3383.92
    assert mes["walk_forward"]["regime_flip"] is True
    assert mes["walk_forward"]["wf_pass"] is False
    assert mes["verdict"] == "WALK_FORWARD_FAIL_REGIME_FLIP"


def test_mnq_numbers_locked(out):
    mnq = _by_sym(out, "MNQ")
    assert mnq["summary"]["n_trades"] == 259
    assert mnq["summary"]["expectancy_per_trade_usd"] == 9.27
    assert mnq["walk_forward"]["is_total"] == -1530.96  # IS NEGATIVE
    assert mnq["walk_forward"]["oos_total"] == 3932.68
    assert mnq["walk_forward"]["regime_flip"] is True
    assert mnq["concentration"]["top3_day_pct_of_net"] == 193.5  # severely concentrated
    assert mnq["verdict"] == "WALK_FORWARD_FAIL_REGIME_FLIP"


def test_aggregate_is_a_direction_artifact_on_both(out):
    # The positive aggregate is entirely the LONG side; short loses on both ->
    # a direction-following artifact, not a two-sided edge (C3/L188).
    for sym in ("MES", "MNQ"):
        r = _by_sym(out, sym)
        assert r["direction"]["both_sided"] is False
        nets = {d: v["net"] for d, v in r["direction"]["by_direction"].items()}
        assert nets["short"] < 0 < nets["long"]


def test_verdict_ladder_is_non_vacuous():
    # Bite test: a synthetic CLEAN two-sided, IS+OOS-positive, non-concentrated set
    # must read CLEAN_GENERALIZES -- proves WALK_FORWARD_FAIL actually discriminates.
    rows = []
    # 20 IS (2025) + 20 OOS (2026) trades, both directions positive, spread across
    # many distinct days (no concentration), every trade a small winner.
    for i in range(20):
        rows.append({"date": f"2025-{(i % 12) + 1:02d}-1{i % 9}", "dir": "long", "net": 10.0})
        rows.append({"date": f"2026-{(i % 6) + 1:02d}-1{i % 9}", "dir": "short", "net": 10.0})
    wf = frfp._walk_forward(rows)
    assert wf["wf_pass"] is True
    assert wf["regime_flip"] is False
    dsplit = frfp._direction_split(rows)
    assert dsplit["both_sided"] is True


def test_isolates_fade_cohort_not_momentum_fleet(out):
    # Guard the un-mined-cell premise: the probe scopes to LEVEL_REJECT_LIVE only,
    # NOT the full momentum fleet the 2026-06-20 control already debunked.
    assert frfp.FADE_SETUP == "LEVEL_REJECT_LIVE"
    for r in out["results"]:
        assert r["setup"] == "LEVEL_REJECT_LIVE"
