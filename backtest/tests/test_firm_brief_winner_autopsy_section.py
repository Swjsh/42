"""Guard for firm_brief.render_winner_autopsy_lines -- the WINNER-side brief section.

J 2026-07-31: "We need to analyze these winners just as much as the losers." The loss
autopsy has had a standing brief line since 2026-07-08; the winner side had none, so J had
to ask for this analysis by hand. These tests pin the three properties that make the new
line trustworthy rather than merely present:

  1. It ALWAYS carries its n, and flags the sample as an ANECDOTE below the aggregate floor.
  2. It ALWAYS carries the winners-only conditioning warning -- a reader who sees only the
     brief must not walk away believing this is a policy comparison.
  3. It fails OPEN on every malformed/absent input, exactly like the loss-side section.

Mirrors test_firm_brief_autopsy_pnl_status.py's import convention and fail-open contract."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "firm_brief", REPO / "setup" / "scripts" / "firm_brief.py")
fb = importlib.util.module_from_spec(_SPEC)
sys.modules["firm_brief"] = fb
_SPEC.loader.exec_module(fb)

_OK = {
    "n_winners_found": 21, "n_winners_scored": 21, "n_no_bars": 0,
    "sufficient_n": True, "capture_vs_best_policy": 1.0189,
    "best_policy": "all_out_at_tp1_100", "realized_total": 3479.0,
    "runner_cohort": {"n_scaled_out_winners": 11, "n_runner_below_tp1": 7,
                      "n_runner_material_giveback": 7,
                      "median_runner_giveback_pct": 0.324},
    "md": "analysis/winner-autopsies/all.md",
}


def test_never_ran_renders_placeholder_not_a_number():
    lines = fb.render_winner_autopsy_lines({})
    assert len(lines) == 1 and "no winner autopsy yet" in lines[0]
    assert "%" not in lines[0]


def test_error_renders_loudly():
    lines = fb.render_winner_autopsy_lines({"error": "ZeroDivisionError: boom"})
    assert "FAILED" in lines[0] and "fix me" in lines[0]


def test_no_replayable_winners_does_not_fabricate_capture():
    lines = fb.render_winner_autopsy_lines(
        {"n_winners_found": 2, "n_winners_scored": 0, "n_no_bars": 2})
    assert "no replayable winners" in lines[0]
    assert "2 found" in lines[0] and "2 without bars" in lines[0]


def test_happy_path_carries_capture_n_and_policy():
    lines = fb.render_winner_autopsy_lines(_OK)
    body = " ".join(lines)
    assert "102%" in body                       # capture, rounded
    assert "n=21" in body                       # ALWAYS with its n
    assert "all_out_at_tp1_100" in body         # which policy is the denominator
    assert "ANECDOTE" not in body               # n above the floor


def test_low_n_is_labelled_an_anecdote():
    data = dict(_OK, n_winners_scored=3, sufficient_n=False)
    body = " ".join(fb.render_winner_autopsy_lines(data))
    assert "ANECDOTE" in body and "n=3" in body


def test_winners_only_caveat_is_always_present():
    """THE rail. Without this line the brief reads as a policy recommendation."""
    for data in (_OK, dict(_OK, sufficient_n=False, n_winners_scored=2),
                 dict(_OK, capture_vs_best_policy=0.5)):
        body = " ".join(fb.render_winner_autopsy_lines(data))
        assert "winners-only" in body
        assert "NOT a policy comparison" in body
        assert "pre-registered A/B" in body


def test_runner_cohort_summary_is_surfaced():
    body = " ".join(fb.render_winner_autopsy_lines(_OK))
    assert "7/11" in body and "BELOW their own TP1" in body
    assert "32%" in body


def test_missing_runner_cohort_degrades_without_crashing():
    body = " ".join(fb.render_winner_autopsy_lines(dict(_OK, runner_cohort={})))
    assert "102%" in body and "BELOW their own TP1" not in body


def test_capture_none_renders_na_not_zero():
    """A non-positive denominator yields None upstream; it must never print as 0%."""
    body = " ".join(fb.render_winner_autopsy_lines(dict(_OK, capture_vs_best_policy=None)))
    assert "n/a" in body and "0%" not in body


def test_capture_above_one_is_reported_plainly():
    """Our shipped exits beating every fixed policy is a REAL outcome, not an error to
    massage away."""
    body = " ".join(fb.render_winner_autopsy_lines(dict(_OK, capture_vs_best_policy=1.35)))
    assert "135%" in body
