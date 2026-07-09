"""Drift guard for the ENGINE-CONTRACT card (T1, HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX).

The card `automation/state/engine-contract.md` is auto-derived from the live sources
(accounts.json / strategies.py / params.json / aggressive params / cap_admission tables).
This guard RE-DERIVES it and asserts the committed file matches — so any source edit that
is NOT followed by a regeneration (or any hand-edit of the card) turns this RED. That is
the T1 acceptance: "guard test asserts regeneration is clean vs committed code (drift = RED)."

Pure — no network, no backtest. engine_contract.render_contract() reads local files only.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "engine_contract", REPO / "setup" / "scripts" / "engine_contract.py")
ec = importlib.util.module_from_spec(_SPEC)
sys.modules["engine_contract"] = ec
_SPEC.loader.exec_module(ec)

CARD = REPO / "automation" / "state" / "engine-contract.md"


def test_card_exists():
    assert CARD.exists(), (
        "engine-contract.md is missing — run `python setup/scripts/engine_contract.py`.")


def test_no_drift_vs_committed():
    """The committed card must equal a fresh render. A mismatch means a source (arms /
    strategies / params / cap tables) changed without regenerating the card, OR someone
    hand-edited it. Fix: `python setup/scripts/engine_contract.py`, then commit."""
    committed = CARD.read_text(encoding="utf-8")
    fresh = ec.render_contract()
    assert committed == fresh, (
        "ENGINE-CONTRACT DRIFT: committed engine-contract.md differs from a fresh render. "
        "A source changed without regeneration. Run: python setup/scripts/engine_contract.py")


def test_drift_detection_actually_discriminates():
    """Red-proof of the MECHANISM (not the live file): a mutated card must NOT compare equal
    to a fresh render, so the guard can never silently pass on real drift."""
    fresh = ec.render_contract()
    mutated = fresh.replace("stop -20%", "stop -99%", 1)
    assert mutated != fresh, "render produced no '-20%' to mutate — update this red-proof anchor"
    assert mutated != ec.render_contract()


def test_render_is_deterministic():
    """No timestamps / now() in the card, else the drift guard would false-RED every run."""
    assert ec.render_contract() == ec.render_contract()


def test_card_surfaces_both_exec_paths():
    """The card's whole point (OP-33e): show that control arms and fleet_rest arms trade
    DIFFERENT shapes. Assert both the params.json control shape and a strategies.py shape appear."""
    card = ec.render_contract()
    assert "ribbon_ride" in card and "vwap_continuation" in card       # strategies.py shapes
    assert "params.json" in card and "CONTROL" in card                  # control-arm path
    assert "Kill switch" in card and "Min contracts" in card            # hard floors + sizing
