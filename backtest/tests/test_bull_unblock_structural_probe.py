"""Guard for BULL-UNBLOCK-STRUCTURAL-PROBE (SLICE 2 of the #1 project thread).

Pins the committed golden finding: on the fresh OPRA window, relaxing the
structural bull lever `filter_10_min_triggers_bull` 2 -> 1 does NOT produce a
PROPOSABLE bull edge — the added cohort is net-positive gross but statistically
insufficient (n<10), day-concentrated, and fragile to realistic slippage.

If a future engine change silently flips this to a clean proposable edge, this
guard re-REDs the build so the finding gets re-audited (C7/C14) rather than a
stale "no bull edge" conclusion masking a real one.
"""
import json
import os

import pytest

from autoresearch.bull_unblock_replay_probe import classify_verdict

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESULT = os.path.join(REPO, "analysis", "recommendations",
                      "bull-unblock-structural-2026-06-30.json")

# The propose verdict — the ONE outcome that would mean "unblock adds edge, tell J".
PROPOSE = "UNBLOCK_ADDS_EDGE_PROPOSE"


@pytest.fixture(scope="module")
def result():
    with open(RESULT) as f:
        return json.load(f)


def test_result_file_exists_and_is_structural_probe(result):
    assert result["probe"] == "bull_unblock_structural_probe"
    assert result["lever"].startswith("filter_10_min_triggers_bull")
    # block_elite_bull held at production so this isolates the structural lever only.
    assert result["block_elite_bull"].startswith("True")
    assert result["base"]["min_triggers_bull"] == 2
    assert result["unblock"]["min_triggers_bull"] == 1


def test_structural_lever_is_not_proposable(result):
    """The golden finding: the structural unblock did NOT clear the propose bar."""
    assert result["verdict"] != PROPOSE
    assert result["verdict"] == "UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE"


def test_added_cohort_is_thin_and_fragile(result):
    """WHY it's not proposable: insufficient n AND slippage-fragile (not the sign)."""
    cohort = result["added_bull_cohort"]
    # net-positive GROSS (so the block is not "removes losers" like the elite lever)...
    assert cohort["net_pnl"] > 0
    # ...but insufficient sample AND fails realistic slippage -> not deployable.
    assert cohort["significance"]["sufficient"] is False
    assert cohort["slippage"]["verdict"] != "SURVIVES_REALISTIC"
    # anchors are all bearish -> a bull unblock can never regress one.
    assert cohort["anchor_no_regression"] is True


def test_verdict_ladder_matches_committed_cohort(result):
    """Recompute the verdict from the committed cohort numbers — no drift between
    the stored verdict and the pure ladder that produced it (C14 parity)."""
    cohort = result["added_bull_cohort"]
    has_trades = cohort["n"] > 0
    net_positive = cohort["net_pnl"] > 0
    survives = cohort["slippage"].get("verdict") == "SURVIVES_REALISTIC"
    sufficient = bool(cohort["significance"]["sufficient"])
    assert classify_verdict(has_trades, net_positive, survives, sufficient) == result["verdict"]


def test_bite_would_propose_if_edge_were_clean(result):
    """Non-vacuous: prove the reason it's NOT proposed is the fragility/thinness —
    if the SAME net-positive cohort were sufficient AND slippage-robust, the ladder
    WOULD say PROPOSE. So the guard isn't a hollow hardcoded reject."""
    cohort = result["added_bull_cohort"]
    net_positive = cohort["net_pnl"] > 0
    assert net_positive  # committed cohort really is gross-positive
    # flip ONLY the two fragility preconditions -> the ladder flips to PROPOSE.
    assert classify_verdict(True, net_positive, True, True) == PROPOSE
    # and with the REAL (fragile) preconditions it does NOT propose.
    assert classify_verdict(True, net_positive, False, False) != PROPOSE
