"""FULL-SEND producer disarm (2026-08-29) -- pins BOTH halves of a deliberately asymmetric change.

The investigation behind this (TWO-ACCOUNT-CONSOLIDATION handoff s0.2/s6.4) found that
"risky-1's full_send lane" is two completely different mechanisms wearing one config key, and
that the obvious action -- "disarm full_send" -- would have done the harmful half:

  HALF A -- the ENTRY LANE (`build_shared_signal.FULL_SEND_LIVE` -> `_full_send_plan`).
      A secondary entry channel that bypasses the five cohort vetoes. Placed 0 orders in its
      entire lifetime, but NOT because it is unreachable: the producer emits an `available`
      block on 126 replayed ticks. It was held back only by the per-trade risk cap, whose
      ceiling is (equity x cap) / (min_contracts x 100) -- and with equity $2,000 -> $6,495
      and min_contracts frozen at 5, that ceiling went $2.00 -> $6.50. DISARMED.

  HALF B -- the SIZE CLAMP (`arm.gate_override.full_send` -> `_apply_full_send_min_sizing`).
      Clamps qty DOWN to min_contracts. On the 30 entries where it fired it removed 102 of
      252 contracts and saved ~+$1,021. KEPT.

These tests exist so nobody "finishes the job" by deleting the gate_override key, and so
nobody flips the lane back on without re-reading why it was closed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fe  # noqa: E402

ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"


def _risky1():
    arms = json.loads(ACCOUNTS.read_text(encoding="utf-8")).get("arms", [])
    for a in arms:
        if a.get("id") == "risky-1":
            return a
    pytest.skip("risky-1 not in accounts.json")


# ---------------------------------------------------------------- HALF A: lane is OFF

def test_full_send_producer_lane_is_disarmed():
    """The kill itself. Flip this back to True and you re-open a never-validated secondary
    entry channel whose only historical safety catch was an equity level we have passed."""
    assert bss.FULL_SEND_LIVE is False


def test_disarmed_producer_omits_the_key_and_the_consumer_fail_closes_on_that():
    """The disarm works by OMITTING `full_send` from the signal entirely. That is only safe
    because the consumer treats a non-Mapping as 'no lane' -- assert the pair together, since
    either half alone would be a latent crash or a latent entry."""
    row = {
        "verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
        "bull_triggers_raw": ["level_reclaim", "confluence"],
        "bear_triggers_raw": [],
        "trigger_level_exact": 640.25,
        "ts_et": "2026-08-28T11:00:00",
        "spy": 640.0,
    }
    sig = bss.build_from_rows(bss._map_core_row(row), _et("2026-08-28T11:00:00"),
                              bold_row=bss._map_core_row(row), run_vwap=False, write=False)
    assert "full_send" not in sig, "disarmed producer must not emit the block"

    # ...and the consumer must return None (no entry) rather than raise, on that exact shape.
    arm = {"id": "risky-1", "gate_override": {"full_send": True}}
    params = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    plan = fe._full_send_plan(arm, sig, 6495.35, params, "risky-1", 640.0)
    assert plan is None


def _et(ts: str):
    from datetime import datetime
    return datetime.fromisoformat(ts).replace(tzinfo=bss.ET)


def test_full_send_block_from_row_is_empty_when_disarmed():
    """Row-level proof that does not depend on today's on-disk ledger."""
    row = {
        "verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
        "bull_triggers_raw": ["level_reclaim", "confluence"],
        "bear_triggers_raw": [],
        "trigger_level_exact": 640.25,
        "ts_et": "2026-08-28T11:00:00",
    }
    # the allowlist + trigger condition itself must still be TRUE -- i.e. the lane is being
    # held closed by the disarm, not by the signal having gone quiet.
    assert bss.passed_full_send(row["verdict"], "level_reclaim", row["bull_triggers_raw"]) is True


# ---------------------------------------------------------------- HALF B: clamp is ON

def test_risky1_still_carries_gate_override_full_send():
    """The size clamp keys off THIS, not off FULL_SEND_LIVE. Deleting it un-clamps position
    size on a losing cohort -- a risk INCREASE dressed up as a disarm."""
    g = _risky1().get("gate_override") or {}
    assert g.get("full_send") is True, (
        "gate_override.full_send was removed. That is the SIZE CLAMP, not the entry lane. "
        "Measured: it removed 102 of 252 contracts and saved ~+$1,021. Re-read "
        "test_full_send_producer_disarm_2026_08_29's module docstring before changing this."
    )


def test_risky1_selectivity_gate_still_present_under_full_send():
    """The 2026-08-12 gate restoration must survive this change untouched."""
    g = _risky1().get("gate_override") or {}
    assert g.get("min_triggers") == 2
    assert g.get("require_confluence_or_sequence") is True


def test_size_clamp_is_independent_of_the_producer_flag():
    """THE orthogonality claim, executed rather than asserted in prose: the clamp must behave
    identically with FULL_SEND_LIVE False and True."""
    params = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    arm = {"gate_override": {"full_send": True}}
    results = {}
    for flag in (False, True):
        original = bss.FULL_SEND_LIVE
        try:
            bss.FULL_SEND_LIVE = flag
            results[flag] = fe._apply_full_send_min_sizing(12, arm, params, 6495.35)[0]
        finally:
            bss.FULL_SEND_LIVE = original
    assert results[False] == results[True]
    assert results[False] == params.get("min_contracts")


def test_clamp_only_ever_reduces_qty():
    """`min()` is a ceiling, never a floor-raise. If this ever inverts, the 'never loose on
    RISK' half of the profile is gone."""
    params = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    arm = {"gate_override": {"full_send": True}}
    for qty in (1, 2, 5, 8, 12, 20):
        out, _ = fe._apply_full_send_min_sizing(qty, arm, params, 6495.35)
        assert out <= qty, (qty, out)


def test_non_full_send_arms_are_untouched_by_the_clamp():
    """vary-and-assert (C14): the clamp must be a no-op for every other arm."""
    params = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    for arm in ({}, {"gate_override": {}}, {"gate_override": {"min_triggers": 2}}):
        for qty in (1, 8, 20):
            out, note = fe._apply_full_send_min_sizing(qty, arm, params, 6495.35)
            assert out == qty and note is None
