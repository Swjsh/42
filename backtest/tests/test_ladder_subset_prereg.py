"""Guard for backtest/tools/ladder_subset_prereg.py (LADDER-SUBSET-PREREG executor,
analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.{json,md}).

Pins the pure logic that decides which trades count as the frozen subset:

  1. subset_match is EXACTLY the frozen hypothesis (score>=9 AND confluence AND HTF BEAR) --
     any drift (e.g. >=8, trendline accepted, MIXED accepted) REDs here.
  2. check_alignment raises on a frame whose bar_idx does not land on the recorded timestamp
     (silent misalignment would attach the wrong bar's HTF stack to every trade).
  3. slice_trades filters by the derived stack and annotates htf_15m without mutating input.
  4. held_out_cutoff_from_parent hard-fails if the parent JSON's frozen split moved.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ladder_subset_prereg.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ladder_subset_prereg as lsp  # noqa: E402


# ------------------------------------------------------------------ 1. subset_match truth table

@pytest.mark.parametrize(
    "score,triggers,htf,expected",
    [
        (9, ["level_rejection", "confluence"], "BEAR", True),
        (10, ["confluence"], "BEAR", True),
        (8, ["confluence"], "BEAR", False),           # floor is 9, not 8
        (9, ["level_rejection"], "BEAR", False),      # confluence REQUIRED
        (9, ["trendline_rejection"], "BEAR", False),  # trendline is not confluence
        (9, ["confluence"], "BULL", False),
        (9, ["confluence"], "MIXED", False),          # MIXED is not BEAR
        (9, ["confluence"], None, False),             # insufficient warmup is not BEAR
        (9, [], "BEAR", False),
        (9, None, "BEAR", False),                     # defensive: None trigger list
    ],
)
def test_subset_match_is_the_frozen_hypothesis(score, triggers, htf, expected):
    assert lsp.subset_match(score, triggers, htf) is expected


# ------------------------------------------------------------------ 2. alignment hard-assert

def _frame(times: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"timestamp_et": pd.to_datetime(times), "close": [1.0] * len(times)})


def test_check_alignment_passes_on_exact_match():
    spy = _frame(["2026-07-27 09:40:00", "2026-07-27 09:45:00"])
    rows = [{"trigger_bar_idx": 1, "trigger_time_et": "2026-07-27T09:45:00"}]
    lsp.check_alignment(spy, rows)  # must not raise


def test_check_alignment_raises_on_mismatch():
    spy = _frame(["2026-07-27 09:40:00", "2026-07-27 09:45:00"])
    rows = [{"trigger_bar_idx": 0, "trigger_time_et": "2026-07-27T09:45:00"}]
    with pytest.raises(AssertionError, match="alignment broken"):
        lsp.check_alignment(spy, rows)


# ------------------------------------------------------------------ 3. slice_trades

def test_slice_trades_filters_and_annotates_without_mutation():
    trades = [
        {"trigger_bar_idx": 0, "bear_score": 9, "triggers_raw": ["confluence"], "dollar_pnl": 10.0},
        {"trigger_bar_idx": 1, "bear_score": 9, "triggers_raw": ["confluence"], "dollar_pnl": -5.0},
        {"trigger_bar_idx": 2, "bear_score": 9, "triggers_raw": ["level_rejection"], "dollar_pnl": 7.0},
    ]
    stacks = ["BEAR", "BULL", "BEAR"]
    out = lsp.slice_trades(trades, stacks)
    assert [t["trigger_bar_idx"] for t in out] == [0]      # BULL and non-confluence dropped
    assert out[0]["htf_15m"] == "BEAR"
    assert "htf_15m" not in trades[0]                       # input not mutated


# ------------------------------------------------------------------ 4. frozen held-out split

def test_held_out_cutoff_accepts_the_frozen_parent_split():
    parent = {"held_out_split": {"cutoff_date": "2026-03-06"}}
    assert lsp.held_out_cutoff_from_parent(parent) == dt.date(2026, 3, 6)


def test_held_out_cutoff_rejects_a_moved_split():
    parent = {"held_out_split": {"cutoff_date": "2026-04-01"}}
    with pytest.raises(AssertionError, match="not the population"):
        lsp.held_out_cutoff_from_parent(parent)
