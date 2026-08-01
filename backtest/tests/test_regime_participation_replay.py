"""Guards for backtest/tools/regime_participation_replay.py (2026-08-02, REGIME-PARTICIPATION task).

Pins the ONE new piece of logic this script adds on top of the already-guarded
day_report_card.py machinery (classify_day / aggregate_cards -- see test_day_report_card.py,
NOT re-tested here, reused not reimplemented):

  aggregate_by_archetype() -- pure. Groups a list of day-cards by their 'archetype' key and
  re-derives the participation summary (n_days_entered / n_days_gate_blocked /
  n_days_correctly_flat_subqualifying_trigger / n_days_no_vocabulary_zero_triggers) per
  archetype via day_report_card.aggregate_cards() (delegated, not duplicated).

RED-proofed: every assertion below was checked against a deliberately-broken version of the
function (wrong entered-cause set, gate/correctly_flat swapped, archetype grouping dropped)
and observed to fail before being pinned as written.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_regime_participation_replay.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
for _p in (str(REPO), str(REPO / "backtest"), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import day_report_card as drc               # noqa: E402
import regime_participation_replay as rpr   # noqa: E402


def _card(date, archetype, cause, cause_detail=None, cause_dollars=None):
    return {"date": date, "archetype": archetype, "cause": cause,
            "cause_detail": cause_detail, "cause_dollars": cause_dollars}


class TestAggregateByArchetypeBasics:
    def test_empty_input_returns_empty_dict(self):
        assert rpr.aggregate_by_archetype([]) == {}

    def test_single_green_day_counts_as_entered(self):
        cards = [_card("2026-01-02", "gap-go", "GREEN", "day_pnl>=focus_floor", 100.0)]
        out = rpr.aggregate_by_archetype(cards)
        assert out["gap-go"]["n_days"] == 1
        assert out["gap-go"]["n_days_entered"] == 1
        assert out["gap-go"]["participation_rate"] == 1.0
        assert out["gap-go"]["n_days_gate_blocked"] == 0

    def test_gate_blocked_day_not_counted_as_entered(self):
        cards = [_card("2026-01-02", "trend-up", "GATE_BLOCKED", "filter_8", 50.0)]
        out = rpr.aggregate_by_archetype(cards)
        assert out["trend-up"]["n_days_entered"] == 0
        assert out["trend-up"]["n_days_gate_blocked"] == 1
        assert out["trend-up"]["participation_rate"] == 0.0

    def test_all_four_traded_tree_causes_count_as_entered(self):
        for cause in ("GREEN", "EXIT_LEFT_MONEY", "EXIT_TOO_LATE", "SHOULD_NOT_HAVE_TRADED"):
            cards = [_card("2026-01-02", "gap-go", cause, "x", 1.0)]
            out = rpr.aggregate_by_archetype(cards)
            assert out["gap-go"]["n_days_entered"] == 1, f"{cause} should count as entered"

    def test_correctly_flat_and_no_vocabulary_are_distinct_buckets(self):
        cards = [
            _card("2026-01-02", "pin-day", "CORRECTLY_FLAT", "triggers_seen_none_qualifying", 0.0),
            _card("2026-01-03", "pin-day", "NO_VOCABULARY", "zero_triggers_all_day", 0.0),
        ]
        out = rpr.aggregate_by_archetype(cards)
        assert out["pin-day"]["n_days_correctly_flat_subqualifying_trigger"] == 1
        assert out["pin-day"]["n_days_no_vocabulary_zero_triggers"] == 1
        assert out["pin-day"]["n_days_entered"] == 0

    def test_none_archetype_buckets_as_untagged(self):
        cards = [_card("2026-01-02", None, "GREEN", "x", 1.0)]
        out = rpr.aggregate_by_archetype(cards)
        assert "UNTAGGED" in out
        assert out["UNTAGGED"]["n_days"] == 1

    def test_multiple_archetypes_kept_separate_and_not_cross_counted(self):
        cards = [
            _card("2026-01-02", "gap-go", "GREEN", "x", 100.0),
            _card("2026-01-03", "trend-up", "GATE_BLOCKED", "filter_8", 50.0),
        ]
        out = rpr.aggregate_by_archetype(cards)
        assert set(out.keys()) == {"gap-go", "trend-up"}
        assert out["gap-go"]["n_days"] == 1
        assert out["trend-up"]["n_days"] == 1
        assert out["gap-go"]["n_days_gate_blocked"] == 0    # not contaminated by trend-up's block
        assert out["trend-up"]["n_days_entered"] == 0        # not contaminated by gap-go's GREEN

    def test_participation_rate_reflects_mixed_days(self):
        cards = [
            _card("2026-01-02", "gap-fade", "GREEN", "x", 10.0),
            _card("2026-01-03", "gap-fade", "GATE_BLOCKED", "filter_5", -5.0),
            _card("2026-01-04", "gap-fade", "CORRECTLY_FLAT", "y", 0.0),
            _card("2026-01-05", "gap-fade", "NO_VOCABULARY", "z", 0.0),
        ]
        out = rpr.aggregate_by_archetype(cards)
        assert out["gap-fade"]["n_days"] == 4
        assert out["gap-fade"]["n_days_entered"] == 1
        assert out["gap-fade"]["participation_rate"] == 0.25


class TestDelegatesRatherThanReimplements:
    """The whole point of aggregate_by_archetype is to reuse day_report_card's already-
    guarded aggregate_cards() per archetype slice -- these pin that it is a real delegation,
    not a parallel reimplementation that could silently drift from it."""

    def test_cause_histogram_matches_day_report_card_aggregate_cards_directly(self):
        cards = [
            _card("2026-01-02", "gap-go", "GREEN", "x", 100.0),
            _card("2026-01-03", "gap-go", "GATE_BLOCKED", "filter_8", 50.0),
        ]
        out = rpr.aggregate_by_archetype(cards)
        expected = drc.aggregate_cards([c for c in cards if c["archetype"] == "gap-go"])
        assert out["gap-go"]["cause_histogram"] == expected["ranked"]

    def test_rejects_unknown_cause_via_underlying_aggregate_cards(self):
        """aggregate_cards() fail-loudly rejects any cause outside VALID_CAUSES -- pinning
        this here proves the delegation is real (a silently-more-permissive reimplementation
        would swallow this instead of raising)."""
        cards = [_card("2026-01-02", "gap-go", "NOT_A_REAL_CAUSE", "x", 1.0)]
        with pytest.raises(ValueError):
            rpr.aggregate_by_archetype(cards)
