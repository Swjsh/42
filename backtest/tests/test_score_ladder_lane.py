"""Guards for the SCORE LADDER lane (2026-07-27) -- the probe's sibling for scoring-failed ticks.

THE INCIDENT THIS ENCODES: 2026-07-27 09:40-09:50, bear_score 9/10 with raw detections
level_rejection+confluence @744.9, refused by one structural blocker (filter 5, ribbon).
Zero arms traded; the engine later chased the bottom for -$571.64. J's standing design:
the arms are a risk ladder -- "the riskiest arm can hop in at a seven out of ten."

The lane is deliberately fail-closed at every layer: no raw fields (all rows before
2026-07-28), no level, no floor config, gate-skip verdicts, ENTER ticks -- each alone must
produce NO ladder entry.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fx  # noqa: E402

# The real 2026-07-27 09:49 tick, as the ledger will carry it from 2026-07-28 on.
BLOCKED_ROW = {
    "verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)",
    "bear_score": 9, "bull_score": 6, "bear_blockers": [5],
    "bear_triggers_raw": ["level_rejection", "confluence"],
    "bear_rejection_level_raw": 744.9, "spy": 743.45,
}

ARM_LADDER = {"id": "risky-3", "gate_override": {"min_triggers": 1, "score_ladder_floor": 7}}
ARM_PLAIN = {"id": "risky-1", "gate_override": {"min_triggers": 2}}
PARAMS = {"min_contracts": 5}


def _signal(row=BLOCKED_ROW, spot=743.45):
    return {"spot": spot, "bear": {"passed": False}, "bull": {"passed": False},
            "ladder": bss._ladder_block_from_row(row)}


# ------------------------------------------------------------ producer (build_shared_signal)
def test_producer_emits_available_block_on_the_incident_row():
    blk = bss._ladder_block_from_row(BLOCKED_ROW)["bear"]
    assert blk["available"] is True
    assert blk["score"] == 9 and blk["level"] == 744.9
    assert "level_rejection" in blk["triggers_raw"]


def test_producer_fail_closed_on_pre_upgrade_rows():
    """Every row before 2026-07-28 lacks the raw fields -- must produce NO block."""
    old = {k: v for k, v in BLOCKED_ROW.items()
           if k not in ("bear_triggers_raw", "bear_rejection_level_raw", "bear_blockers")}
    assert bss._ladder_block_from_row(old)["bear"]["available"] is False


def test_producer_ignores_gate_skips_and_enters():
    for verdict in ("SKIP_STRUCTURE_VETO", "ENTER_BEAR", "SKIP_BULL_1100_1200"):
        row = dict(BLOCKED_ROW, verdict=verdict, reason="whatever")
        assert bss._ladder_block_from_row(row)["bear"]["available"] is False, verdict


def test_producer_requires_level_tied_trigger_and_level():
    no_trig = dict(BLOCKED_ROW, bear_triggers_raw=["ribbon_flip"])
    assert bss._ladder_block_from_row(no_trig)["bear"]["available"] is False
    no_level = dict(BLOCKED_ROW, bear_rejection_level_raw=None)
    assert bss._ladder_block_from_row(no_level)["bear"]["available"] is False


def test_producer_none_row_is_empty():
    assert bss._ladder_block_from_row(None)["bear"]["available"] is False


# ------------------------------------------------------------ consumer (fleet_executor)
def test_armed_arm_enters_on_the_incident_tick():
    """THE trade of 2026-07-27: risky-3 at floor 7 must plan a min-size bear entry."""
    plans = fx.plan_all(ARM_LADDER, _signal(), 1852.21, PARAMS)
    enters = [p for p in plans if p.action == "ENTER"]
    assert len(enters) == 1
    p = enters[0]
    assert p.side == "P" and p.qty == 5
    assert p.trigger_level == 744.9, "the raw rejection level must ride as the stop anchor"
    assert "SCORE_LADDER" in p.reason and "score=9" in p.reason


def test_unarmed_arm_never_enters_via_ladder():
    plans = fx.plan_all(ARM_PLAIN, _signal(), 1424.63, PARAMS)
    assert not any(p.action == "ENTER" for p in plans), (
        "an arm without score_ladder_floor must be byte-identical to pre-ladder behavior")


def test_floor_is_respected():
    low = dict(BLOCKED_ROW, bear_score=6)
    plans = fx.plan_all(ARM_LADDER, _signal(row=low), 1852.21, PARAMS)
    assert not any(p.action == "ENTER" for p in plans), "score 6 < floor 7 must not enter"


def test_ladder_never_doubles_a_normal_enter():
    """When the normal path already ENTERs, the ladder must stay silent."""
    sig = _signal()
    sig["bear"] = {"passed": True, "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"], "trigger_level_exact": 744.9,
                   "score": 10}
    params = dict(PARAMS, position_sizing_tiers=[
        {"equity_min": 0.0, "equity_max": 999_999.0, "base_qty": 3, "elite_qty": 3}])
    plans = fx.plan_all(ARM_LADDER, sig, 1852.21, params)
    enters = [p for p in plans if p.action == "ENTER"]
    assert len(enters) == 1, f"expected exactly one ENTER, got {len(enters)}"
    assert "SCORE_LADDER" not in enters[0].reason


def test_passed_but_sizing_blocked_is_NOT_rescued_by_ladder():
    """FOUND BY THIS FILE'S FIRST RED RUN: with no sizing tier, the normal path HOLDs
    ('no sizing tier covers equity') and the ladder was firing as an accidental min-size
    fallback. The lane's scope is SCORING-FAILED ticks only -- a passed-but-unsized tick is
    a config problem to surface, not a trade to rescue."""
    sig = _signal()
    sig["bear"] = {"passed": True, "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"], "trigger_level_exact": 744.9,
                   "score": 10}
    plans = fx.plan_all(ARM_LADDER, sig, 1852.21, PARAMS)  # PARAMS has no sizing tiers
    assert not any(p.action == "ENTER" for p in plans), (
        "ladder must not paper over a sizing/config hole at min-size")


def test_bull_side_has_no_ladder():
    """BEAR ONLY at ship -- a bull mirror must not exist until its own pre-reg passes."""
    blk = bss._ladder_block_from_row(BLOCKED_ROW)
    assert "bull" not in blk or not (blk.get("bull") or {}).get("available")


def test_ladder_entry_reuses_probe_strike_tiers():
    plans = fx.plan_all(ARM_LADDER, _signal(), 1852.21, PARAMS)
    p = [x for x in plans if x.action == "ENTER"][0]
    expect = fx.strike_selection.pick_strike(743.45, 1852.21, "P", fx.PROBE_STRIKE_TIERS)
    assert p.strike == expect
