"""Guard: extra-setup free-model veto payload carries a REAL side (2026-07-09 fix).

BUG (GATE-PROVENANCE-CENSUS-2026-07-09.md #2, BUG-CONFIRMED): `_synthetic_verdict_from_extra`
built extra-setup (vwap_continuation / vwap_reclaim_failed_break / vix_regime_dayside /
double_bottom_base_quiet / bollinger_squeeze) veto payloads with ONLY verdict/setup_name/
triggers_fired -- no side, no bear_score/bull_score. `_free_model_eval`'s snapshot builder
then rendered "side=None bear=None/10 bull=None/11" on EVERY extra-setup veto call, and the
2 free models -- reasonably, given what they were shown -- vetoed validated setups by CITING
that malformed prompt as their reason. At least 7 of 14 extra-setup veto events on 2026-07-09
name this exact artifact, including the 10:31:03 vwap_reclaim_failed_break veto the census
called out by name: "Conflicting setup parameters: rules_engine_says=ENTER_BULL but
side=None." Net effect: 5 already-validated setups suppressed for a non-reason.

FIX, two parts:
  1. `_synthetic_verdict_from_extra` (heartbeat_core.py) now populates `side` using the
     IDENTICAL derivation _execute uses for the core-ribbon path (side = "P" if verdict ==
     ENTER_BEAR else "C") -- side is REAL data (direction long/short is always known for a
     fired row), so it is fixed AT THE SOURCE.
  2. `_veto_snapshot` (extracted from `_free_model_eval`) OMITS the bear=.../10 and
     bull=.../11 segments when the verdict doesn't carry them, instead of fabricating
     "None/10" -- extra setups are watcher-pattern detectors, not scored on the core
     engine's 0-10/0-11 scale, so there is no real score to report. This is the "omit
     rather than fabricate" half of the fix; there is no source-side value to populate.

Core-ribbon verdicts (engine_cli output) already carry side/bear_score/bull_score for
every ENTER_BEAR/ENTER_BULL verdict (the only verdicts _free_model_eval is ever called
with on that path) -- this file pins that path stays BYTE-IDENTICAL to the pre-fix format.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_extra_setup_veto_payload.py -q
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def hc():
    """Import heartbeat_core fresh (it lives in setup/scripts)."""
    return importlib.import_module("heartbeat_core")


def _bar_ctx():
    return {
        "bar": {"close": 751.42},
        "ribbon_now": {"stack": "BULL", "spread_cents": 118},
        "vix_now": 16.07,
        "vix_prior": 16.21,
        "htf_15m_stack": "BULL",
        "levels_active": ["750.00", "752.50"],
    }


# =============================================================================
# 1. _synthetic_verdict_from_extra: long -> side C / short -> side P
# =============================================================================
@pytest.mark.parametrize("direction,expected_verdict,expected_side", [
    ("long", "ENTER_BULL", "C"),
    ("short", "ENTER_BEAR", "P"),
    ("LONG", "ENTER_BULL", "C"),   # case-insensitive, mirrors test_g4's mapping guard
    ("Short", "ENTER_BEAR", "P"),
])
def test_direction_maps_to_correct_side(hc, direction, expected_verdict, expected_side):
    row = {"setup_name": "vwap_continuation", "fired": True, "direction": direction,
           "triggers": ["t1"]}
    sv = hc._synthetic_verdict_from_extra(row)
    assert sv is not None
    assert sv["verdict"] == expected_verdict
    assert sv["side"] == expected_side


def test_side_matches_core_execute_convention(hc):
    """`side` must be derived the SAME way _execute derives it for the core-ribbon path
    (side = "P" if verdict == ENTER_BEAR else "C", _execute ~L1091) -- not re-invented."""
    long_sv = hc._synthetic_verdict_from_extra(
        {"setup_name": "x", "fired": True, "direction": "long", "triggers": []})
    short_sv = hc._synthetic_verdict_from_extra(
        {"setup_name": "x", "fired": True, "direction": "short", "triggers": []})
    assert long_sv["side"] == ("P" if long_sv["verdict"] == "ENTER_BEAR" else "C")
    assert short_sv["side"] == ("P" if short_sv["verdict"] == "ENTER_BEAR" else "C")


def test_synthetic_verdict_never_fabricates_scores(hc):
    """The fix populates REAL data (side) but must NOT fabricate bear_score/bull_score --
    extra setups genuinely have no value on that 0-10/0-11 scale. Exact-keys pin: a future
    edit that starts inventing a score here should RED this test, not silently ship."""
    sv = hc._synthetic_verdict_from_extra(
        {"setup_name": "vwap_continuation", "fired": True, "direction": "long", "triggers": []})
    assert set(sv.keys()) == {"verdict", "side", "setup_name", "triggers_fired"}


def test_fail_closed_rows_still_return_none(hc):
    """Regression guard: the side fix must not loosen the existing fail-closed contract."""
    for row in (
        {"setup_name": "x", "fired": False, "direction": "long"},
        {"setup_name": "x", "fired": True, "direction": "neutral"},
        {"setup_name": "x", "fired": True},
        "not-a-dict",
    ):
        assert hc._synthetic_verdict_from_extra(row) is None


# =============================================================================
# 2. _veto_snapshot: rendered prompt contains no "side=None" for extra setups,
#    and never fabricates a score line
# =============================================================================
def test_extra_setup_prompt_has_no_side_none(hc):
    bc = _bar_ctx()
    row = {"setup_name": "vwap_reclaim_failed_break", "fired": True, "direction": "long",
           "triggers": ["vwap_reclaim"]}
    sv = hc._synthetic_verdict_from_extra(row)
    snap = hc._veto_snapshot(bc, sv)
    assert "side=None" not in snap
    assert "side=C" in snap


def test_extra_setup_prompt_short_side_p(hc):
    bc = _bar_ctx()
    row = {"setup_name": "vix_regime_dayside", "fired": True, "direction": "short",
           "triggers": ["vix_spike"]}
    sv = hc._synthetic_verdict_from_extra(row)
    snap = hc._veto_snapshot(bc, sv)
    assert "side=None" not in snap
    assert "side=P" in snap


def test_extra_setup_prompt_omits_score_lines_rather_than_fabricate(hc):
    """The core bug pattern, spelled out: no 'None/10' or 'None/11' anywhere, and no
    'bear='/'bull=' fragment at all -- omitted, not fabricated with a placeholder."""
    bc = _bar_ctx()
    row = {"setup_name": "bollinger_squeeze", "fired": True, "direction": "long",
           "triggers": ["squeeze_break"]}
    sv = hc._synthetic_verdict_from_extra(row)
    snap = hc._veto_snapshot(bc, sv)
    assert "None/10" not in snap
    assert "None/11" not in snap
    assert "bear=" not in snap
    assert "bull=" not in snap
    # setup= must still be present and immediately followed by triggers= (no dangling
    # double space where the omitted score segment used to sit)
    assert "  " not in snap, f"double space -- omission left a formatting artifact: {snap!r}"


# =============================================================================
# 3. Regression sentinel: prove the bug pattern this fix addresses was REAL, so the
#    guards in section 2 (which exercise current code and go RED on a revert) are
#    trusted to be testing something that actually happened, not a strawman.
# =============================================================================
def test_old_code_shape_would_have_produced_the_bug():
    """NOT exercising current code -- _veto_snapshot's omit-logic is unconditional (that
    IS the fix), so feeding it an old-shaped dict no longer reproduces the bug, which is
    correct/more-robust behavior, not something to assert against. Instead this
    reconstructs the pre-2026-07-09 _free_model_eval inline f-string VERBATIM (the code
    that existed before the _veto_snapshot extraction) fed the pre-fix
    _synthetic_verdict_from_extra return shape (verdict/setup_name/triggers_fired only).
    Confirms "side=None bear=None/10 bull=None/11" was the real, reproducible output of
    the old code -- i.e. the actual regression guards above (test_extra_setup_prompt_
    has_no_side_none, test_extra_setup_prompt_omits_score_lines_rather_than_fabricate),
    which DO call hc._synthetic_verdict_from_extra / hc._veto_snapshot and would go RED
    on a revert of the fix in heartbeat_core.py, are guarding against a real defect."""
    bc = _bar_ctx()
    old_shaped_verdict = {  # the pre-2026-07-09 _synthetic_verdict_from_extra return shape
        "verdict": "ENTER_BULL",
        "setup_name": "vwap_reclaim_failed_break",
        "triggers_fired": ["vwap_reclaim"],
    }
    # Verbatim pre-fix inline expression from _free_model_eval, before the _veto_snapshot
    # extraction -- deliberately NOT calling hc._veto_snapshot (that's the fixed function).
    old_snap = (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
                f"spread={bc['ribbon_now']['spread_cents']}c VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
                f"HTF15m={bc['htf_15m_stack']} levels_near={bc['levels_active']} "
                f"rules_engine_says={old_shaped_verdict.get('verdict')} side={old_shaped_verdict.get('side')} "
                f"setup={old_shaped_verdict.get('setup_name')} bear={old_shaped_verdict.get('bear_score')}/10 "
                f"bull={old_shaped_verdict.get('bull_score')}/11 triggers={old_shaped_verdict.get('triggers_fired')}")
    assert "side=None" in old_snap
    assert "bear=None/10" in old_snap
    assert "bull=None/11" in old_snap


# =============================================================================
# 4. Core-ribbon path: byte-identical to the pre-refactor inline f-string
# =============================================================================
_CORE_VERDICT = {
    "verdict": "ENTER_BULL", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "bear_score": 2, "bull_score": 11, "triggers_fired": ["level_reclaim", "confluence"],
}


def test_core_path_prompt_byte_identical_to_pre_fix_format(hc):
    """vary-and-assert (C14): a fully-populated core-ribbon verdict (side + both scores
    real, as engine_cli always produces for ENTER_BEAR/ENTER_BULL -- the only verdicts
    _free_model_eval is ever called with on this path) must render EXACTLY what the
    original pre-refactor inline f-string produced -- this fix must not perturb the
    already-correct core path."""
    bc = _bar_ctx()
    verdict = _CORE_VERDICT
    # The ORIGINAL (pre-2026-07-09) inline expression from _free_model_eval, reconstructed
    # verbatim as the pinned expectation -- NOT calling any production code.
    expected = (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
                f"spread={bc['ribbon_now']['spread_cents']}c VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
                f"HTF15m={bc['htf_15m_stack']} levels_near={bc['levels_active']} "
                f"rules_engine_says={verdict.get('verdict')} side={verdict.get('side')} "
                f"setup={verdict.get('setup_name')} bear={verdict.get('bear_score')}/10 "
                f"bull={verdict.get('bull_score')}/11 triggers={verdict.get('triggers_fired')}")
    actual = hc._veto_snapshot(bc, verdict)
    assert actual == expected


def test_core_path_bear_only_enable_bullish_false_omits_bull(hc):
    """Edge case the old code got wrong too (bull_score genuinely null when
    enable_bullish=False, per engine_cli's own docstring) -- omit, don't fabricate,
    even on the core path. heartbeat_core hardcodes enable_bullish=True today so this
    never fires in production, but the render logic must still be correct if it ever did."""
    bc = _bar_ctx()
    verdict = {**_CORE_VERDICT, "bull_score": None}
    snap = hc._veto_snapshot(bc, verdict)
    assert "bull=" not in snap
    assert "bear=2/10" in snap


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
