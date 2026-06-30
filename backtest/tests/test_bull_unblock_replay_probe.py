"""Guard for BULL-UNBLOCK-REPLAY-PROBE (the #1 project thread re-audit).

Pins (a) the pure verdict ladder of `classify_verdict` so the decision logic can't
silently regress, and (b) the committed real-fills finding's published numbers, so a
future engine change that silently flips "block correctly removes losers" into
"unblock adds edge" (or vice-versa) re-REDs the build loudly (C7 / C14).
"""
import json
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))

from autoresearch.bull_unblock_replay_probe import classify_verdict  # noqa: E402

RESULT = os.path.join(REPO, "analysis", "recommendations",
                      "bull-unblock-elite-replay-2026-06-30.json")


# ---- verdict ladder ---------------------------------------------------------

def test_no_trades_is_inert():
    assert classify_verdict(False, False, False, False) == \
        "NO_DELTA_BLOCK_INERT_ON_FRESH_WINDOW"


def test_net_negative_cohort_keeps_block():
    # the actual finding: a net-negative added cohort means the block is correct.
    assert classify_verdict(True, False, False, False) == \
        "BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP"
    # even a net-negative cohort that somehow "survives" is still KEEP
    assert classify_verdict(True, False, True, True) == \
        "BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP"


def test_propose_requires_all_three():
    assert classify_verdict(True, True, True, True) == "UNBLOCK_ADDS_EDGE_PROPOSE"
    # missing ANY of net-positive / survives / sufficient -> not a propose
    assert classify_verdict(True, True, True, False) == \
        "UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE"
    assert classify_verdict(True, True, False, True) == \
        "UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE"


def test_bite_propose_logic_actually_gates():
    """Non-vacuous: a positive+surviving+sufficient cohort is the ONLY propose path.
    Flip any single precondition and it must stop proposing."""
    base = ("propose", True, True, True, True)
    assert classify_verdict(*base[1:]) == "UNBLOCK_ADDS_EDGE_PROPOSE"
    for i in range(1, 5):
        args = list(base[1:])
        args[i - 1] = False
        assert classify_verdict(*args) != "UNBLOCK_ADDS_EDGE_PROPOSE", \
            f"flipping precondition {i} should have stopped the propose"


# ---- golden finding (real-fills, committed) ---------------------------------

@pytest.mark.skipif(not os.path.exists(RESULT), reason="probe result not yet committed")
def test_committed_finding_keeps_the_block():
    r = json.load(open(RESULT))
    assert r["real_fills"] is True
    assert r["verdict"] == "BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP"
    cohort = r["added_bull_cohort"]
    # the added cohort is net-negative on the fresh window -> the block is correct.
    assert cohort["net_pnl"] < 0, "finding flipped: added cohort no longer net-negative"
    assert cohort["n"] == 7
    # anchors are all PUT/BEAR -> no bull-unblock can ever regress one.
    assert cohort["anchor_no_regression"] is True
