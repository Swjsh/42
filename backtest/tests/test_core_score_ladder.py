"""Guards for the CORE-ARM SCORE LADDER hook (2026-07-27) -- heartbeat_core.py's
counterpart to the fleet's build_shared_signal._ladder_block + fleet_executor._ladder_plan
(commits deb781ea/d6fc72a6).

WHY A SEPARATE HOOK: safe-2/bold-2 execute via heartbeat_core.run_account directly
(mcp/REST), never through fleet_executor, so J's graduated-arm design ("I specifically
said I wanted seven out of ten and eight out of tens being traded") needed its own
fail-closed rescue on the CORE verdict. THE INCIDENT this encodes: 2026-07-27 09:40-09:50,
bear_score 9/10 with raw detections level_rejection+confluence @744.9, refused by one
structural blocker (filter 5, ribbon), zero arms traded, engine later chased the bottom for
-$571.64.

The hook (setup/scripts/heartbeat_core.py#_apply_score_ladder) is deliberately fail-closed
at every layer: no floor configured, wrong verdict shape, score under floor, no raw
level-tied trigger, no raw level, gate-skip verdicts, ENTER ticks, bull side -- each alone
must leave the verdict byte-identical (returns the SAME object, `is`-comparable).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_BACKTEST = REPO / "backtest"
_SCRIPTS = REPO / "setup" / "scripts"
_FLEET = REPO / "automation" / "state" / "fleet"
for _p in (str(_BACKTEST), str(REPO), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts above
    handle its internal deps -- same pattern as test_money_path_2026_07_01.py::hc)."""
    return importlib.import_module("heartbeat_core")


# The real 2026-07-27 09:49 tick, as engine_cli's verdict dict carries it (WHY-NOT
# PROVENANCE fields, see test_why_not_provenance.py for the same fixture's origin).
INCIDENT_VERDICT = {
    "verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)",
    "bear_score": 9, "bull_score": 6, "bear_blockers": [5],
    "bull_blockers": None,
    "bear_triggers_raw": ["level_rejection", "confluence"],
    "bull_triggers_raw": [],
    "bear_rejection_level_raw": 744.9, "bull_reclaim_level_raw": None,
    "setup_name": None, "side": None, "triggers_fired": [],
    "rejection_level": None,
}

FLOOR_9 = {"score_ladder_floor": 9}
FLOOR_8 = {"score_ladder_floor": 8}


# ------------------------------------------------------------------ (a) the rescue itself
def test_a_incident_tick_at_its_own_floor_is_rewritten_to_enter_bear(hc):
    """THE trade of 2026-07-27: score 9 / blockers [5] / raw level_rejection+confluence
    @744.9, at floor=9 (safe's own configured floor) -> rewritten to ENTER_BEAR with the
    raw level riding as rejection_level, tagged entry_lane."""
    out = hc._apply_score_ladder(dict(INCIDENT_VERDICT), FLOOR_9)
    assert out["verdict"] == "ENTER_BEAR"
    assert out["side"] == "P"
    assert out["setup_name"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"
    assert out["rejection_level"] == 744.9
    assert out["quality_tier"] == "LADDER"
    assert out["entry_lane"] == "score_ladder"
    assert "SCORE_LADDER floor=9 score=9" in out["reason"]
    assert "blockers=[5]" in out["reason"]
    assert "no setup passed scoring" in out["reason"], "original reason must survive, prepended"


# ------------------------------------------------------------------ (b) REVOKE path
def test_b_floor_absent_is_byte_identical_revoke_path(hc):
    """No score_ladder_floor key (or params not a dict with the key) -> the SAME verdict
    object comes back unchanged -- this IS the REVOKE mechanism (delete the key)."""
    v = dict(INCIDENT_VERDICT)
    out = hc._apply_score_ladder(v, {})
    assert out is v, "REVOKE path must return the identical object, not just an equal copy"
    assert "entry_lane" not in out


def test_b_floor_none_and_malformed_also_revoke(hc):
    v = dict(INCIDENT_VERDICT)
    assert hc._apply_score_ladder(v, {"score_ladder_floor": None}) is v
    assert hc._apply_score_ladder(v, {"score_ladder_floor": "not-a-number"}) is v


# ------------------------------------------------------------------ (c) score below floor
def test_c_score_below_floor_is_untouched(hc):
    v = dict(INCIDENT_VERDICT, bear_score=8)
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v
    assert out["verdict"] == "HOLD"


def test_c_score_missing_or_non_numeric_is_untouched(hc):
    for bad in (None, "9", [9]):
        v = dict(INCIDENT_VERDICT, bear_score=bad)
        out = hc._apply_score_ladder(v, FLOOR_9)
        assert out is v, f"bear_score={bad!r} must not admit"


# ------------------------------------------------------------------ (d) no raw level-tied trigger
def test_d_no_level_tied_raw_trigger_is_untouched(hc):
    v = dict(INCIDENT_VERDICT, bear_triggers_raw=["ribbon_flip"])
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


def test_d_empty_raw_triggers_is_untouched(hc):
    v = dict(INCIDENT_VERDICT, bear_triggers_raw=[])
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


# ------------------------------------------------------------------ (e) no raw level
def test_e_missing_raw_level_is_untouched(hc):
    v = dict(INCIDENT_VERDICT, bear_rejection_level_raw=None)
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


def test_e_non_numeric_raw_level_is_untouched(hc):
    v = dict(INCIDENT_VERDICT, bear_rejection_level_raw="744.9")
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


# ------------------------------------------------------------------ (f) gate-skip / ENTER verdicts untouched
@pytest.mark.parametrize("verdict_name", [
    "SKIP_STRUCTURE_VETO", "SKIP_EARLY_ENTRY", "SKIP_LATE_ENTRY", "SKIP_STALE_TRIGGER",
    "SKIP_BAD_INPUT", "ENTER_BEAR", "ENTER_BULL",
])
def test_f_non_plain_hold_verdicts_are_untouched(hc, verdict_name):
    v = dict(INCIDENT_VERDICT, verdict=verdict_name, reason="whatever")
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v, f"{verdict_name} must never be rescued -- only a plain scoring HOLD is"


def test_f_hold_with_different_reason_text_is_untouched(hc):
    """A HOLD for some OTHER reason (not the scoring-failed class) must not be rescued."""
    v = dict(INCIDENT_VERDICT, verdict="HOLD", reason="no live data this tick")
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


def test_f_verdict_shape_check_is_independently_load_bearing(hc):
    """Isolates the `verdict == "HOLD"` condition from the reason-text condition: a
    non-HOLD verdict carrying (adversarially/hypothetically) the exact scoring-failed
    reason text must still be refused -- the verdict-shape gate is its own guard, not
    redundant with the reason-text gate."""
    v = dict(INCIDENT_VERDICT, verdict="ENTER_BULL",
            reason="no setup passed scoring (neither bear nor bull)")
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v


# ------------------------------------------------------------------ (g) bull side never rewritten
def test_g_bull_side_never_rewritten_even_when_bull_would_qualify(hc):
    """A tick where BULL looks ladder-eligible (high bull_score, a bull-side raw trigger)
    but bear does not qualify must stay untouched -- there is no bull mirror at all."""
    v = dict(INCIDENT_VERDICT, bear_score=3, bull_score=9,
            bull_triggers_raw=["level_reclaim"], bull_reclaim_level_raw=744.9)
    out = hc._apply_score_ladder(v, FLOOR_9)
    assert out is v
    assert out["verdict"] == "HOLD"


def test_g_function_never_sets_side_c(hc):
    """Structural pin: _apply_score_ladder's only rewrite path sets side='P'. There is no
    code path in this function that can ever produce side='C' (CALL)."""
    import inspect
    src = inspect.getsource(hc._apply_score_ladder)
    assert '"C"' not in src and "'C'" not in src, "no CALL-side literal may appear -- BEAR ONLY"


# ------------------------------------------------------------------ per-account floor sanity
def test_safe_and_bold_floors_match_j_spec(hc):
    """J's 7/8/8/9/9 ladder: safe (Gamma-Safe-2, this file's most conservative core arm)
    floor=9, bold (Gamma-Bold-2) floor=8 -- pins the shipped params.json values so a
    future edit can't silently drift from the ratified spec."""
    import json
    safe = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    bold = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    assert safe.get("score_ladder_floor") == 9
    assert bold.get("score_ladder_floor") == 8


# ------------------------------------------------------------------ run_account wiring smoke test
def test_run_account_hook_is_wired_after_extra_dispatch_before_v(hc):
    """Structural pin on run_account's source: _apply_score_ladder must be called, and
    the call must appear AFTER dispatch_extra_setups and BEFORE the `v = verdict.get(
    "verdict"` line that claims the execution branch -- the exact placement J specified.
    A source-order check (not a full integration test) because run_account requires a
    live broker/TV/network stack to execute end-to-end."""
    import inspect
    src = inspect.getsource(hc.run_account)
    i_dispatch = src.index("dispatch_extra_setups(")
    i_hook = src.index("_apply_score_ladder(")
    i_v = src.index('v = verdict.get("verdict"')
    assert i_dispatch < i_hook < i_v, (
        "hook must sit strictly between the extra-setup dispatch and the `v =` line "
        "that claims the execution branch"
    )


def test_run_account_tags_entry_lane_only_when_ladder_fires(hc):
    """Structural pin: rec['entry_lane'] assignment must be conditioned on the hook
    actually firing (the `is not` identity check), never unconditional."""
    import inspect
    src = inspect.getsource(hc.run_account)
    assert 'rec["entry_lane"] = "score_ladder"' in src
    assert "verdict is not _pre_ladder_verdict" in src
