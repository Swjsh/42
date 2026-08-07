"""Guards for SCORE-LADDER-V2 admission semantics (prereg c2ec28f3, frozen 2026-08-07).

Pins the frozen demotable/non-demotable partition + double-demerit arithmetic to the
prereg's own worked examples -- including J's pinned 10:15 tick. RED-proof: flipping any
frozen set/constant in score_ladder_replay_2026_08_07.py fails at least one test here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "backtest" / "tools"
for p in (str(ROOT), str(ROOT / "backtest"), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from score_ladder_replay_2026_08_07 import side_admission  # noqa: E402


def test_j_pinned_1015_tick_bull_sole_f10():
    """2026-08-07 10:15: bull_score 10/11, sole blocker f10, level_reclaim+confluence,
    level 770.46 -> adjusted 9 -> IN at rung 7 and 8 (J's worked example, verbatim)."""
    a = side_admission("C", 10, [10], ["level_reclaim", "confluence"], 770.46, 15.04)
    assert a is not None
    assert a["adjusted"] == 9
    assert a["adjusted"] >= 7 and a["adjusted"] >= 8


def test_bull_sole_f11_never_admits():
    """f11 (trigger count / level-tied requirement) is NON-DEMOTABLE on every rung --
    the bare-confirmation -$103/entry cohort must never enter."""
    assert side_admission("C", 10, [11], ["ribbon_flip"], 770.0, 15.0) is None


def test_bull_two_demotable_rung7_only():
    """blockers {7,10}: reported 9, adjusted 7 -> IN at rung 7, OUT at rung 8."""
    a = side_admission("C", 9, [7, 10], ["level_reclaim", "confluence"], 770.0, 15.0)
    assert a is not None and a["adjusted"] == 7


def test_bull_vix_hard_cap_f9_never_admits():
    assert side_admission("C", 10, [9], ["level_reclaim", "confluence"], 770.0, 23.5) is None


def test_bull_spread_f6_never_admits():
    assert side_admission("C", 10, [6], ["level_reclaim", "confluence"], 770.0, 15.0) is None


def test_bear_sole_ribbon_f5():
    """The 2026-07-27 09:40 incident shape: bear 9/10, sole blocker f5 -> adjusted 8 ->
    IN at rung 7/8, OUT at rung 9 (bear rung 9 = binary)."""
    a = side_admission("P", 9, [5], ["level_rejection", "confluence"], 744.9, 19.67)
    assert a is not None and a["adjusted"] == 8


def test_bear_two_demotable_out_at_7():
    """bear {5,9}: reported 8, adjusted 6 -> OUT at rung 7 (bear rung 7 admits exactly one
    demotable blocker under double-demerit)."""
    a = side_admission("P", 8, [5, 9], ["level_rejection"], 744.0, 19.0)
    assert a is not None and a["adjusted"] == 6 and a["adjusted"] < 7


def test_bear_f8_hard_cap_component():
    """bear f8 demotes at vix<=23 but is ABSOLUTE above the 23.0 hard cap."""
    assert side_admission("P", 9, [8], ["level_rejection"], 744.0, 24.1) is None
    a = side_admission("P", 9, [8], ["level_rejection"], 744.0, 19.0)
    assert a is not None and a["adjusted"] == 8


def test_no_level_never_admits():
    assert side_admission("P", 9, [5], ["level_rejection"], None, 19.0) is None


def test_binary_pass_not_a_ladder_extra():
    assert side_admission("C", 11, [], ["level_reclaim", "confluence"], 770.0, 15.0) is None


def test_window_f1_never_admits():
    assert side_admission("C", 10, [1], ["level_reclaim", "confluence"], 770.0, 15.0) is None
