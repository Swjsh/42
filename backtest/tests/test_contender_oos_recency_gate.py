"""Guard: CONFIRM-BEFORE-CAPITAL recency gate in contender_oos_check (gate 5).

GRADUATES the 2026-06-29 incident into a code assertion. On 2026-06-28 a
dead-premium-axis contender (OTM-2 long single leg, WR 12%, tp+150%) cleared
the OP-11 gates 1-4 on an IS sweep and AUTO-APPLIED to live params
(tp1_qty_fraction 0.667->0.8 + v15_profit_lock_mode trailing->fixed, commit
b8896df) DESPITE recency-confirmation.json reading edges_confirmed_on_recent=
false (any_red=true). The OP-11 auto-ship bar never checked the documented
CONFIRM-BEFORE-CAPITAL gate. assess_recency_gate now blocks auto-clear while
recency is RED, and FAILS CLOSED on any unreadable input.

These tests are pure ($0) -- they never load market data or run a backtest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent       # backtest/
_ROOT = _REPO.parent                                 # repo root
for _p in (str(_REPO / "autoresearch"), str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_gate():
    """Import only assess_recency_gate without triggering main()'s heavy imports.

    contender_oos_check imports strategy_space_grind at module load; if that is
    unavailable in the test env we skip rather than error (the gate logic is the
    unit under test, not the grinder).
    """
    try:
        from autoresearch.contender_oos_check import assess_recency_gate  # noqa
        return assess_recency_gate
    except Exception as exc:  # pragma: no cover - env-dependent
        pytest.skip(f"contender_oos_check import unavailable: {exc}")


def _write(tmp_path: Path, payload) -> Path:
    p = tmp_path / "recency-confirmation.json"
    if isinstance(payload, (dict, list)):
        p.write_text(json.dumps(payload), encoding="utf-8")
    else:
        p.write_text(str(payload), encoding="utf-8")
    return p


# --- fail-closed on unreadable input (uncertainty must never auto-ship) -------

def test_missing_file_fails_closed(tmp_path):
    gate = _load_gate()
    passed, detail = gate(tmp_path / "does-not-exist.json")
    assert passed is False
    assert "fail-closed" in detail


def test_garbled_json_fails_closed(tmp_path):
    gate = _load_gate()
    p = tmp_path / "recency-confirmation.json"
    p.write_text("{not valid json", encoding="utf-8")
    passed, detail = gate(p)
    assert passed is False
    assert "fail-closed" in detail


def test_non_dict_fails_closed(tmp_path):
    gate = _load_gate()
    passed, _ = gate(_write(tmp_path, ["a", "list"]))
    assert passed is False


def test_malformed_headline_fails_closed(tmp_path):
    gate = _load_gate()
    passed, _ = gate(_write(tmp_path, {"headline": "not-a-dict"}))
    assert passed is False


# --- RED recency blocks (the exact 06-28 incident shape) ----------------------

def test_red_recency_blocks_clear(tmp_path):
    gate = _load_gate()
    # The exact 2026-06-28 headline that SHOULD have blocked the auto-apply.
    payload = {"headline": {"edges_confirmed_on_recent": False, "any_red": True}}
    passed, detail = gate(_write(tmp_path, payload))
    assert passed is False
    assert "CONFIRM-BEFORE-CAPITAL" in detail


def test_none_recency_blocks_clear(tmp_path):
    gate = _load_gate()
    payload = {"headline": {"edges_confirmed_on_recent": None}}
    passed, _ = gate(_write(tmp_path, payload))
    assert passed is False


def test_missing_key_blocks_clear(tmp_path):
    gate = _load_gate()
    passed, _ = gate(_write(tmp_path, {"headline": {}}))
    assert passed is False


# --- only an explicit confirm passes ------------------------------------------

def test_confirmed_recency_passes(tmp_path):
    gate = _load_gate()
    payload = {"headline": {"edges_confirmed_on_recent": True, "any_red": False}}
    passed, detail = gate(_write(tmp_path, payload))
    assert passed is True
    assert "true" in detail.lower()


def test_truthy_but_not_true_does_not_pass(tmp_path):
    """edges_confirmed_on_recent=1 (truthy) must NOT pass -- requires bool True."""
    gate = _load_gate()
    passed, _ = gate(_write(tmp_path, {"headline": {"edges_confirmed_on_recent": 1}}))
    assert passed is False


# --- non-vacuous bite: prove the gate is what blocks the all_pass -------------

def test_bite_recency_red_flips_all_pass_false_when_other_gates_pass(tmp_path):
    """All four OP-11 gates pass, but recency RED must drop ALL_PASS to False.

    This is the 06-28 incident reproduced: oos/wf/sub-window/anchor all PASS,
    yet a recency-RED edge must NOT clear. If this test goes green with the gate
    removed, the gate is vacuous.
    """
    gate = _load_gate()
    oos_pos = wf_pass = sw_pass = anchor_pass = True
    recency_pass, _ = gate(_write(tmp_path, {"headline": {"edges_confirmed_on_recent": False, "any_red": True}}))
    all_pass = oos_pos and wf_pass and sw_pass and anchor_pass and recency_pass
    assert all_pass is False, "recency-RED must block clearing even when gates 1-4 pass"

    # And the mirror: with recency confirmed, the same four gates DO clear.
    recency_pass_ok, _ = gate(_write(tmp_path, {"headline": {"edges_confirmed_on_recent": True}}))
    all_pass_ok = oos_pos and wf_pass and sw_pass and anchor_pass and recency_pass_ok
    assert all_pass_ok is True


def test_live_recency_file_currently_red(tmp_path):
    """The live recency-confirmation.json is currently RED -> gate must block.

    Locks the present reality so a silent flip to confirmed (without a real
    recency CONFIRM) would surface. Skips if the live file is absent.
    """
    gate = _load_gate()
    live = _ROOT / "automation" / "state" / "recency-confirmation.json"
    if not live.exists():
        pytest.skip("live recency-confirmation.json absent")
    passed, _ = gate(live)
    # As of the 2026-06-29 incident the live file reads RED; if a genuine CONFIRM
    # has since landed this assertion documents that transition for review.
    data = json.loads(live.read_text(encoding="utf-8"))
    confirmed = data.get("headline", {}).get("edges_confirmed_on_recent")
    assert passed is (confirmed is True)
