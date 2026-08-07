"""Guards for the SCORE-LADDER-RUNG mechanism (prereg
analysis/recommendations/prereg-score-ladder-rung-2026-08-07.md, commit a780122e).

TWO FAMILIES:

1. HARNESS PARTITION GUARDS (enforcing from day one -- they pin the FROZEN prereg partition
   inside backtest/tools/ladder_rung_replay_2026_08_07.py, the replay that produced the ship
   evidence). A drift in the partition silently changes the evidence -- these RED on any such
   drift.

2. PRODUCTION LANE GUARDS (the dormant-patch contract). The patch
   (analysis/arm-ladder/score-ladder-rung-2026-08-07.patch, inlined in
   CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md) adds `fleet_executor._ladder_rung_plan`
   behind the per-arm `gate_override.score_ladder_rung` key and a bull side + vix on
   `build_shared_signal._ladder_block_from_row`. The ADMIT tests are the RED-proof: they
   FAIL against HEAD (the lane does not exist yet) and go GREEN when the patch is applied.
   They carry `xfail(strict=False)` so the suite stays green until the ship decision;
   the RED run was captured with --runxfail and quoted in
   analysis/deep-research/SCORE-LADDER-BUILD-2026-08-07.md. REMOVE the xfail markers in the
   same commit that applies the patch (they then become enforcing).
   VETO tests skip when the lane is absent (they would pass vacuously on HEAD) and enforce
   the non-demotable partition once it exists.

C14 (vary-and-assert): test_rung_absent_key_is_inert runs on HEAD *and* post-patch --
default ABSENT key must stay byte-identical binary behavior forever.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(BACKTEST), str(BACKTEST / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ladder_rung_replay_2026_08_07 as harness  # noqa: E402
import fleet_executor as fx  # noqa: E402
import build_shared_signal as bss  # noqa: E402

RUNG_LANE_EXISTS = hasattr(fx, "_ladder_rung_plan")


# ===================================================================== 1. harness partition

def test_partition_bull_frozen():
    assert harness.DEMOTABLE_BULL == {5, 7, 8, 10}
    # sole-blocker score-10 bull ticks (today's 80x f10 / 10x f7 cohort) are admitted at 7 and 8
    for blocker in (5, 7, 8, 10):
        assert harness.rung_admits("C", 10, [blocker], ["level_reclaim", "confluence"],
                                   773.11, 14.94, 7)
        assert harness.rung_admits("C", 10, [blocker], ["level_reclaim", "confluence"],
                                   773.11, 14.94, 8)


def test_partition_bull_non_demotable_veto():
    # window(1) / spread(6) / VIX-hard(9) / trigger-count-level-tied(11) / sweep(12): absolute
    for blocker in (1, 6, 9, 11, 12):
        assert not harness.rung_admits("C", 10, [blocker], ["level_reclaim", "confluence"],
                                       773.11, 14.94, 7), f"bull blocker {blocker} must veto"


def test_partition_bear_hard_vix_decomposition():
    trig = ["level_rejection", "confluence"]
    # F8 with vix <= 23.0 = soft (demotable); vix > 23.0 = the embedded hard cap (veto)
    assert harness.rung_admits("P", 9, [8], trig, 744.9, 20.0, 7)
    assert not harness.rung_admits("P", 9, [8], trig, 744.9, 23.5, 7)
    # bear non-demotable: 1, 6, 10 (trigger-count/level-tied analog), 11 (sweep)
    for blocker in (1, 6, 10, 11):
        assert not harness.rung_admits("P", 9, [blocker], trig, 744.9, 20.0, 7)
    # bear demotable: 5 (ribbon), 7 (vol divergence), 9 (seller pressure)
    for blocker in (5, 7, 9):
        assert harness.rung_admits("P", 9, [blocker], trig, 744.9, 20.0, 7)


def test_level_tied_and_level_are_absolute_on_every_rung():
    # bare-confirmation (no level-tied trigger): the measured -$103/entry 0%-WR cohort
    assert not harness.rung_admits("C", 11, [], ["ribbon_flip"], 773.0, 15.0, 7)
    # no numeric raw level -> no chart-stop anchor -> no trade
    assert not harness.rung_admits("C", 11, [], ["level_reclaim"], None, 15.0, 7)
    # score below rung
    assert not harness.rung_admits("C", 6, [5], ["level_reclaim"], 773.0, 15.0, 7)


# ===================================================================== 2. production lane

def _mk_arm(rung=None):
    g = {}
    if rung is not None:
        g["score_ladder_rung"] = rung
    return {"id": "risky-3", "gate_override": g}


def _mk_signal(side_key="bull", score=10, blockers=(10,), level=773.11, vix=14.94,
               triggers=("level_reclaim", "confluence")):
    blk = {"available": True, "score": score, "blockers": list(blockers),
           "level": level, "vix": vix, "triggers_raw": list(triggers),
           "reason": f"score {score} blocked (blockers {list(blockers)})"}
    other = "bear" if side_key == "bull" else "bull"
    return {
        "bear": {"passed": False}, "bull": {"passed": False},
        "spot": 773.0,
        "ladder": {side_key: blk, other: {"available": False}},
    }


_PARAMS = {"min_contracts": 5, "per_trade_risk_cap_pct": 0.5}


@pytest.mark.xfail(condition=not RUNG_LANE_EXISTS, strict=False,
                   reason="RED-proof: dormant patch (score-ladder-rung-2026-08-07.patch) "
                          "not applied yet -- prereg a780122e. Remove marker when it lands.")
def test_rung_lane_admits_bull_f10_sole_blocker():
    """THE ship shape: today's 10:14 tick class -- bull_score 10/11, sole blocker filter 10,
    level_reclaim+confluence live. rung 7 (risky-3) must produce an ENTER plan."""
    fn = getattr(fx, "_ladder_rung_plan")
    plan = fn(_mk_arm(rung=7), _mk_signal(), 5000.0, _PARAMS, "risky-3", 773.0)
    assert plan is not None and plan.action == "ENTER" and plan.side == "C"
    assert plan.trigger_level == pytest.approx(773.11)
    assert "SCORE_LADDER_RUNG" in str(plan.reason)


@pytest.mark.xfail(condition=not RUNG_LANE_EXISTS, strict=False,
                   reason="RED-proof: dormant patch not applied yet (see above).")
def test_producer_emits_bull_block_with_vix():
    row = {"verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)",
           "bull_score": 10, "bull_blockers": [10],
           "bull_triggers_raw": ["level_reclaim", "confluence"],
           "bull_reclaim_level_raw": 773.11, "vix": 14.94,
           "bear_score": 4, "bear_blockers": [5, 7, 8, 9, 10],
           "bear_triggers_raw": [], "bear_rejection_level_raw": None}
    out = bss._ladder_block_from_row(row)
    assert out.get("bull", {}).get("available") is True
    assert out["bull"]["score"] == 10 and out["bull"]["blockers"] == [10]
    assert out["bull"]["vix"] == pytest.approx(14.94)


@pytest.mark.skipif(not RUNG_LANE_EXISTS,
                    reason="veto tests would pass vacuously before the lane exists")
def test_rung_lane_vetoes_non_demotable_bull():
    fn = getattr(fx, "_ladder_rung_plan")
    for blocker in (1, 6, 9, 11, 12):
        plan = fn(_mk_arm(rung=7), _mk_signal(blockers=(blocker,)), 5000.0, _PARAMS,
                  "risky-3", 773.0)
        assert plan is None or plan.action != "ENTER", f"bull blocker {blocker} must veto"


@pytest.mark.skipif(not RUNG_LANE_EXISTS,
                    reason="veto tests would pass vacuously before the lane exists")
def test_rung_lane_is_bull_only():
    """TWO STRIKES on the bear side: the raw-floor lane measured -$16,642/725tr (killed
    2026-07-27) AND the rung-semantics bear lane re-measured -$16,631/843tr rung-7,
    -$11,758/466tr rung-8 on the same 390-day population (LADDER-RUNG-2026-08-07-population
    .json) with held-out ALSO negative. The production rung lane therefore admits the BULL
    block ONLY -- a fully-demotable bear block must never produce an ENTER, on any rung,
    at any vix. (Mirror-image of the v1 bear-only floor lane, with the evidence inverted.)"""
    fn = getattr(fx, "_ladder_rung_plan")
    sig_soft = _mk_signal(side_key="bear", score=9, blockers=(8,), level=744.9, vix=20.0,
                          triggers=("level_rejection", "confluence"))
    plan = fn(_mk_arm(rung=7), sig_soft, 5000.0, _PARAMS, "risky-3", 744.9)
    assert plan is None or plan.action != "ENTER", "bear must never enter via the rung lane"


@pytest.mark.skipif(not RUNG_LANE_EXISTS,
                    reason="rung-threshold test needs the lane")
def test_rung_lane_respects_rung_threshold():
    fn = getattr(fx, "_ladder_rung_plan")
    sig = _mk_signal(score=7, blockers=(5, 7, 8, 10))  # 4 demotable blockers -> score 7
    assert fn(_mk_arm(rung=7), sig, 5000.0, _PARAMS, "risky-3", 773.0) is not None
    assert fn(_mk_arm(rung=8), sig, 5000.0, _PARAMS, "risky-1", 773.0) is None


def test_rung_absent_key_is_inert():
    """C14 vary-and-assert: an arm WITHOUT score_ladder_rung never gets a rung entry --
    byte-identical binary behavior. Must hold on HEAD (trivially) and after the patch."""
    if RUNG_LANE_EXISTS:
        fn = getattr(fx, "_ladder_rung_plan")
        assert fn(_mk_arm(rung=None), _mk_signal(), 5000.0, _PARAMS, "risky-3", 773.0) is None
    else:
        # HEAD: the lane does not exist at all -- absence of the mechanism IS inertness;
        # this branch documents the pre-patch state rather than vacuously passing silently.
        assert not RUNG_LANE_EXISTS


def test_live_accounts_carry_no_rung_key_yet():
    """The ship decision (tonight, after 16:00 ET) is the ONLY thing that sets the key.
    While this test exists in its current form, accounts.json must NOT carry
    score_ladder_rung -- flip/extend this test in the SAME commit that arms the arms."""
    import json
    acc = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))
    text = json.dumps(acc)
    assert "score_ladder_rung" not in text, (
        "score_ladder_rung found in accounts.json -- if this is the intentional arming, "
        "update this guard in the same commit (it exists to catch accidental arming)")
