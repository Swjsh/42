"""Guard tests for setup/scripts/dojo/whisper.py (DOJO Phase 1 build, DOJO-ARCHITECTURE-
DECISION.md's whisper.py contract).

Proves: render() on a hand-built decision list produces the lines the contract specifies
(header = bar time + SPY + ribbon; one line per arm = verdict, bear/bull score, side, setup,
trigger_level, nearest key levels), AND never raises -- not on a decision missing every
optional field, not on an empty decisions list, not on a decision whose attribute access
itself raises, and not on plain-dict decisions (whisper.py must tolerate both access styles
since engine_step.py -- the real DojoDecision producer -- had not been built yet when this
module was written).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_whisper.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import whisper  # noqa: E402

ET = ZoneInfo("America/New_York")
BAR_ET = datetime(2026, 7, 17, 9, 40, tzinfo=ET)


def _full_decision(arm, *, side="C", verdict="ENTER", bear=12, bull=68, setup="RIBBON_RIDE",
                    trig=601.10, spy=601.23, ribbon="BULL_ALIGNED",
                    above=(601.50, 0.27, "R2"), below=(600.80, 0.43, "S1")):
    """A fully-populated DojoDecision-shaped SimpleNamespace -- every field the frozen
    contract lists, so the "full decision" tests exercise every render() branch."""
    levels_context = {
        "nearest_level_above": (
            {"price": above[0], "distance": above[1], "source": above[2]} if above else None
        ),
        "nearest_level_below": (
            {"price": below[0], "distance": below[1], "source": below[2]} if below else None
        ),
        "n_levels_within_1pct": 1,
        "reason": None,
    }
    return SimpleNamespace(
        arm=arm, side=side, verdict=verdict, bear_score=bear, bull_score=bull,
        ribbon=ribbon, htf_15m="uptrend", vix=14.2, triggers=["RIBBON_RIDE"],
        setup=setup, trigger_level=trig, would_place=(verdict == "ENTER"),
        spy=spy, cursor_et=BAR_ET,
        context_bundle={"levels_context": levels_context},
    )


# ==================================================================== 1. expected-lines shape
def test_header_shows_bar_time_spy_and_ribbon():
    decisions = [_full_decision("safe")]
    out = whisper.render(decisions, BAR_ET)
    lines = out.splitlines()
    assert lines[0] == "[09:40 ET] SPY 601.23 | ribbon: BULL_ALIGNED"


def test_arm_line_has_verdict_scores_side_setup_trigger_and_levels():
    decisions = [_full_decision("safe", verdict="enter", bear=12, bull=68, side="C",
                                 setup="RIBBON_RIDE", trig=601.10)]
    out = whisper.render(decisions, BAR_ET)
    arm_line = out.splitlines()[1]
    assert "safe" in arm_line
    assert "ENTER" in arm_line  # verdict is upper-cased
    assert "bear=12.00" in arm_line
    assert "bull=68.00" in arm_line
    assert "side=C" in arm_line
    assert "setup=RIBBON_RIDE" in arm_line
    assert "trig=601.10" in arm_line
    assert "above 601.50(+0.27)" in arm_line
    assert "below 600.80(-0.43)" in arm_line


def test_one_line_per_arm_in_order():
    decisions = [_full_decision("safe", verdict="HOLD"), _full_decision("bold", verdict="ENTER"),
                 _full_decision("safe-3", verdict="HOLD")]
    out = whisper.render(decisions, BAR_ET)
    lines = out.splitlines()
    assert len(lines) == 1 + 3  # header + one per arm
    assert "safe" in lines[1] and "bold" in lines[2] and "safe-3" in lines[3]


def test_only_one_side_of_levels_present():
    decisions = [_full_decision("safe", above=None, below=(600.80, 0.43, "S1"))]
    out = whisper.render(decisions, BAR_ET)
    arm_line = out.splitlines()[1]
    assert "above" not in arm_line.split("levels:")[1]
    assert "below 600.80(-0.43)" in arm_line


# =============================================================== 2. never raises on missing fields
def test_never_raises_on_decision_missing_every_optional_field():
    bare = SimpleNamespace(arm="safe-3")  # everything else absent
    out = whisper.render([bare], BAR_ET)  # must not raise
    arm_line = out.splitlines()[1]
    assert "safe-3" in arm_line
    assert "bear=-" in arm_line
    assert "bull=-" in arm_line
    assert "side=-" in arm_line
    assert "setup=-" in arm_line
    assert "trig=-" in arm_line
    assert "levels: -" in arm_line


def test_never_raises_on_completely_empty_object():
    out = whisper.render([SimpleNamespace()], BAR_ET)  # not even 'arm' set
    assert "?" in out.splitlines()[1] or "-" in out.splitlines()[1]


def test_never_raises_on_empty_decisions_list():
    out = whisper.render([], BAR_ET)
    assert "[09:40 ET] SPY - | ribbon: -" == out.splitlines()[0]
    assert "no arm decisions" in out


def test_never_raises_on_decision_with_none_context_bundle():
    d = _full_decision("safe")
    d.context_bundle = None
    out = whisper.render([d], BAR_ET)
    assert "levels: -" in out.splitlines()[1]


def test_never_raises_on_pathological_getattr():
    """An object whose attribute access itself raises (not just 'missing') must still be
    rendered as a safe fallback line -- proves _render_arm_line's own try/except, not just
    _get's getattr-default, is what makes this safe."""

    class Explodes:
        def __getattr__(self, name):
            raise RuntimeError(f"boom on {name}")

    out = whisper.render([Explodes()], BAR_ET)  # must not raise
    assert "render error" in out.splitlines()[1] or "-" in out.splitlines()[1]


def test_never_raises_on_malformed_levels_context():
    d = _full_decision("safe")
    d.context_bundle = {"levels_context": "not-a-dict"}
    out = whisper.render([d], BAR_ET)
    assert "levels: -" in out.splitlines()[1]


def test_never_raises_on_non_datetime_cursor():
    out = whisper.render([_full_decision("safe")], "not-a-datetime")  # must not raise
    assert "not-a-datetime" in out.splitlines()[0]


# ========================================================================= 3. dict decisions
def test_render_supports_plain_dict_decisions():
    """engine_step.py may not exist yet at whisper-authoring time -- a hand-built dict is a
    valid stand-in per the contract's defensive-getattr requirement."""
    d = {
        "arm": "bold", "side": "P", "verdict": "hold", "bear_score": 55, "bull_score": 20,
        "ribbon": "BEAR_ALIGNED", "setup": "VWAP_CONTINUATION", "trigger_level": 598.4,
        "spy": 599.1,
        "context_bundle": {"levels_context": {
            "nearest_level_above": {"price": 600.0, "distance": 0.9, "source": "R1"},
            "nearest_level_below": None, "n_levels_within_1pct": 0, "reason": None,
        }},
    }
    out = whisper.render([d], BAR_ET)
    arm_line = out.splitlines()[1]
    assert "bold" in arm_line
    assert "HOLD" in arm_line
    assert "bear=55.00" in arm_line
    assert "side=P" in arm_line
    assert "setup=VWAP_CONTINUATION" in arm_line
    assert "trig=598.40" in arm_line
    assert "above 600.00(+0.90)" in arm_line


def test_header_reads_dict_first_decision():
    d = {"arm": "safe", "spy": 602.5, "ribbon": "NEUTRAL"}
    out = whisper.render([d], BAR_ET)
    assert out.splitlines()[0] == "[09:40 ET] SPY 602.50 | ribbon: NEUTRAL"
