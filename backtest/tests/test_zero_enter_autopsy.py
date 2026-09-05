"""Guard: setup/scripts/zero_enter_autopsy.py must reproduce the hand-validated
Z2 fixture (analysis/zero-enter/ZERO-ENTER-2026-09-02.json) exactly on its
per-bar table and its two cross-validated day-summary numbers (dominant
blocker id + fire count), for GOAL-ZERO-ENTER-DAYS-2026-09-03 Z3.

The fixture was itself hand-validated against the already-published
SIP-VOLMULT-2026-09-02.md research (57/77 bars blocked by f10, both numbers
matched exactly -- see that file's day_summary.validation_against_SIP_VOLMULT_
2026_09_02 block). This test pins the SCRIPT to the FIXTURE so a future edit
to the blocker-detection / dedup logic that silently changes the count is
caught immediately, without re-deriving SIP-VOLMULT's numbers each time.

RED-PROOF (quoted in the goal's report): `git stash` the script and re-run --
this test must fail with an ImportError/AssertionError, not silently pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

FIXTURE = REPO / "analysis" / "zero-enter" / "ZERO-ENTER-2026-09-02.json"


@pytest.fixture(scope="module")
def fixture_data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def autopsy_result():
    from zero_enter_autopsy import run_autopsy
    return run_autopsy("2026-09-02", account="safe")


def test_fixture_exists(fixture_data):
    assert fixture_data["bars"], "Z2 fixture must have per-bar rows"


def test_n_bars_matches_fixture(fixture_data, autopsy_result):
    assert len(autopsy_result["bars"]) == len(fixture_data["bars"]) == 77


def test_per_bar_dominant_blocker_and_would_have_entered_match_fixture(
    fixture_data, autopsy_result
):
    fixture_by_ts = {b["ts_et"]: b for b in fixture_data["bars"]}
    result_by_ts = {b["ts_et"]: b for b in autopsy_result["bars"]}
    assert set(fixture_by_ts) == set(result_by_ts)
    mismatches = []
    for ts, fb in fixture_by_ts.items():
        rb = result_by_ts[ts]
        if fb["dominant_blocker"] != rb["dominant_blocker"] or (
            fb["would_have_entered"] != rb["would_have_entered"]
        ):
            mismatches.append((ts, fb, rb))
    assert not mismatches, f"{len(mismatches)} bar(s) diverged from the Z2 fixture: {mismatches[:3]}"


def test_dominant_blocker_day_matches_sip_volmult_ground_truth(autopsy_result):
    # SIP-VOLMULT-2026-09-02.md / .json's own core_decisions_unique_bar_check:
    # blocker 10 fires on 57 of 77 unique bars -- the published, cross-checked
    # ground truth this whole instrument must reproduce mechanically.
    ds = autopsy_result["day_summary"]
    assert ds["dominant_blocker_day"] == 10
    assert ds["blocker_fire_count"] == 57


def test_grade_matches_conductor_outcome(autopsy_result):
    ds = autopsy_result["day_summary"]
    assert ds["grade"] == "regressing"


def test_thesis_direction_is_dominant_ribbon(autopsy_result):
    assert autopsy_result["day_summary"]["thesis_direction"] == "BULL"


def test_payoff_degrades_gracefully_when_no_entry_bar(monkeypatch):
    """Fail-open contract: a day with no would-have-entered bar must return a
    labeled null, never crash or fabricate a number."""
    from zero_enter_autopsy import _price_thesis_payoff
    result = _price_thesis_payoff("2026-09-02", "bull", None, None)
    assert result["computed"] is False
    assert result["payoff_usd"] is None
    assert "reason" in result and result["reason"]


def test_payoff_degrades_gracefully_on_missing_option_cache():
    """A date/strike with no OPRA cache must degrade, not crash."""
    from zero_enter_autopsy import _price_thesis_payoff
    result = _price_thesis_payoff("2019-01-02", "bull", "2019-01-02T11:00:00", 100.0)
    assert result["computed"] is False
    assert result["payoff_usd"] is None


def test_never_touches_frozen_trading_path_files():
    """Static guard: the script's source must not open any FROZEN_TRADING_PATH
    file for writing (read-only autopsy per the goal's OPERATING RULES)."""
    src = (REPO / "setup" / "scripts" / "zero_enter_autopsy.py").read_text(encoding="utf-8")
    frozen_markers = (
        "params.json\", \"w", "params.json', 'w",
        "filters.py\", \"w", "heartbeat_core.py\", \"w",
    )
    for m in frozen_markers:
        assert m not in src, f"zero_enter_autopsy.py must never write {m}"
