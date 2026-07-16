"""Guard: J_VWAP_RECLAIM_FB (edge #2) on Bold is NOT live-armable by its enable flag alone.

CONTEXT (2026-07-16 validity check, markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-
2026-07-16.md ship-list item #3): the redesign report's ship action for this item was "flip
`aggressive/params.json#j_vwap_reclaim_fb_enabled` false->true" as a claimed single-key,
ship-ready flip. Investigation found that claim is INCOMPLETE:

  1. `j_vwap_reclaim_fb_enabled` only gates DETECTOR EVALUATION (perception/WATCH) inside
     `setup_dispatch.dispatch_extra_setups`. A fired signal is routed to a LIVE order only
     when `heartbeat_core._extra_exec_armed(params, setup_name)` reads
     `params["extra_setup_exec_armed"][setup_name] is True` from THAT SAME ACCOUNT's params
     file (see test_g4_extra_setup_routing.py for the generic contract).
  2. `automation/state/aggressive/params.json` (Bold) has NEVER had an `extra_setup_exec_armed`
     key — confirmed via `git log -S extra_setup_exec_armed -- automation/state/aggressive/
     params.json` (zero hits) and `setup_dispatch.py`'s own header doc: "(Bold/aggressive
     params arm NONE of these — Safe-only per the 2026-07-01 mandate.)"
  3. Therefore flipping ONLY `j_vwap_reclaim_fb_enabled` on Bold would make the detector
     evaluate + log every tick, but every fired signal would route to `WATCH_NOT_ARMED`
     forever — ZERO live orders, a no-op for actual trading. This is the C14 dead-knob
     failure mode one level up: not an unread key, but a claimed "ship" that can never reach
     `_execute` because a REQUIRED second key (the exec-arm map entry) does not exist.
  4. Independently, `automation/overnight/queue.md`'s DIRECTION-BLOCK-BATCH-RECONCILE item
     (status: awaiting-j-ratification) explicitly holds this exact flag dormant: "HOLD #2/#4
     -- j_vwap_reclaim_fb_enabled + j_vix_dayside_enabled must stay dormant ... Bold ATM book
     RED (n=10, -$60.12/tr); the recency-confirmation gate ... forbids a live flip into RED
     ... This is the CORRECT held state -- do NOT auto-flip." That hold has not been closed.
  5. The isolated EXIT-CELL keys (j_vwap_reclaim_fb_premium_stop_pct/_tp1_pct/_stop_buffer)
     ARE genuinely read (backtest/lib/filters.py, heartbeat_core.py strike/exit override
     maps) -- that part of the redesign report's claim is accurate and NOT what this guard
     is about. This guard is specifically about the missing ENTRY exec-arm wiring.

DISPOSITION: DO NOT ARM tonight. See automation/overnight/STATUS.md 2026-07-16 entry for the
full validity-check writeup. This test pins the current (correct) dormant state and the exact
mechanism so a future session cannot silently repeat the "flip the enable flag = ship it"
mistake for Bold's extra-setup family. Revert/graduate: once (a) a J-ratified exec-arm note
analogous to Safe's `_j_vwap_reclaim_fb_armed_*` doc lands, (b) `extra_setup_exec_armed` is
added to aggressive/params.json with `vwap_reclaim_failed_break: true`, and (c) the queue HOLD
is closed with a fresh non-RED recency read for Bold's actual ITM-2/$1648/qty5 cell -- update
this test to assert the ARMED state instead.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_AGG_PARAMS_PATH = _REPO / "automation" / "state" / "aggressive" / "params.json"


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def agg_params() -> dict:
    return json.loads(_AGG_PARAMS_PATH.read_text(encoding="utf-8"))


def test_bold_j_vwap_reclaim_fb_still_dormant_tonight(agg_params: dict) -> None:
    """Pins the current, correct DO-NOT-ARM disposition (2026-07-16 validity check)."""
    assert agg_params.get("j_vwap_reclaim_fb_enabled") is False, (
        "j_vwap_reclaim_fb_enabled flipped to true without closing the queue HOLD "
        "(DIRECTION-BLOCK-BATCH-RECONCILE) and without extra_setup_exec_armed wiring -- "
        "see STATUS.md 2026-07-16 entry before re-flipping."
    )


def test_bold_aggressive_params_has_no_exec_arm_map(agg_params: dict) -> None:
    """Vary-and-assert: aggressive/params.json has no extra_setup_exec_armed key at all.

    If this ever starts failing because the key now exists, that is EXPECTED once Bold's
    extra-setup exec-arming is deliberately wired (see module docstring) -- update this test
    at that point, don't just delete it.
    """
    assert "extra_setup_exec_armed" not in agg_params


def test_bold_exec_arm_check_is_false_on_real_live_params(hc, agg_params: dict) -> None:
    """The load-bearing check: even with the real aggressive/params.json (Bold's live file)
    fed straight into the actual routing gate, vwap_reclaim_failed_break reads as NOT armed.

    This proves the "single-key flip" ship action would be a no-op for live trading: the
    detector could evaluate to fired=True every tick and _route_extra_setups would still
    log WATCH_NOT_ARMED, never reaching _execute, for as long as this test passes.
    """
    assert hc._extra_exec_armed(agg_params, "vwap_reclaim_failed_break") is False


def test_bold_exec_arm_would_flip_true_once_wired(hc, agg_params: dict) -> None:
    """Demonstrates the FIX is a second, separate key -- documents the real ship action for
    whoever closes this out later, once J-ratified and the queue HOLD is lifted."""
    patched = dict(agg_params)
    patched["extra_setup_exec_armed"] = {"vwap_reclaim_failed_break": True}
    assert hc._extra_exec_armed(patched, "vwap_reclaim_failed_break") is True
