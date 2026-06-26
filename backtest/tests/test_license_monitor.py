"""Unit tests for the LICENSE-MONITOR deploy-timing transition logic.

Pure-function tests (no heavy imports, no IO, no Discord). Verifies the RED->green
transition detection that licenses the dormant WP-8 doubler flip.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backtest/

from autoresearch.license_monitor import classify, transition, diff_tiers  # noqa: E402


def test_classify_maps_verdicts_to_deploy_status():
    assert classify("CONFIRM") == "LICENSED"
    assert classify("YELLOW") == "ELIGIBLE"
    assert classify("RED") == "BLOCKED"
    assert classify("NO_FILLS") == "BLOCKED"
    assert classify(None) == "BLOCKED"        # unknown -> cautious default
    assert classify("garbage") == "BLOCKED"


def test_transition_none_when_unchanged_or_no_prior():
    assert transition(None, "BLOCKED") is None
    assert transition("ELIGIBLE", "ELIGIBLE") is None


def test_transition_unblocked_is_the_one_we_wait_for():
    # RED -> YELLOW and RED -> CONFIRM both unblock the flip.
    assert transition("BLOCKED", "ELIGIBLE") == "UNBLOCKED"
    assert transition("BLOCKED", "LICENSED") == "UNBLOCKED"


def test_transition_upgrade_and_reblock_and_downgrade():
    assert transition("ELIGIBLE", "LICENSED") == "UPGRADED"
    assert transition("ELIGIBLE", "BLOCKED") == "RE-BLOCKED"
    assert transition("LICENSED", "BLOCKED") == "RE-BLOCKED"
    assert transition("LICENSED", "ELIGIBLE") == "DOWNGRADED"


def test_diff_tiers_flags_only_changed_tiers():
    prev = {"#1 ATM (Safe-2)": "RED", "#1 ITM-2 (Bold)": "RED", "#2 ATM": "YELLOW"}
    cur = {"#1 ATM (Safe-2)": "YELLOW", "#1 ITM-2 (Bold)": "RED", "#2 ATM": "CONFIRM"}
    events = diff_tiers(prev, cur)
    kinds = {e["tier"]: e["kind"] for e in events}
    assert kinds == {"#1 ATM (Safe-2)": "UNBLOCKED", "#2 ATM": "UPGRADED"}
    # the still-RED Bold tier produced no event
    assert "#1 ITM-2 (Bold)" not in kinds


def test_diff_tiers_first_run_no_prior_is_silent():
    cur = {"#1 ATM (Safe-2)": "RED", "#2 ATM": "YELLOW"}
    assert diff_tiers(None, cur) == []          # baseline run emits nothing
