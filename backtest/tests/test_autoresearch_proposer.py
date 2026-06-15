"""Tests for autoresearch.proposer — round-robin local search."""

from __future__ import annotations

import datetime as dt

import pytest

from autoresearch import config
from autoresearch.proposer import propose, _candidate_steps
from autoresearch.state import State, fresh_state


def test_candidate_steps_returns_adjacent_values():
    space = config.SEARCH_SPACE["f9_vol_mult"]
    # 0.7 is somewhere in the middle (e.g. [0.4, 0.5, 0.6, 0.7, 0.8, ...])
    out = _candidate_steps("f9_vol_mult", 0.7)
    assert 0.6 in out
    assert 0.8 in out
    assert 0.7 not in out


def test_candidate_steps_at_boundary_returns_one_neighbour():
    space = config.SEARCH_SPACE["min_triggers_bear"]
    first = space[0]
    last = space[-1]
    assert _candidate_steps("min_triggers_bear", first) == [space[1]]
    assert _candidate_steps("min_triggers_bear", last) == [space[-2]]


def test_propose_skips_recently_modified_params():
    s = fresh_state(dt.date(2025, 1, 1), dt.date(2026, 2, 13), dt.date(2026, 2, 14), dt.date(2026, 5, 7))
    s.recently_modified = ["f9_vol_mult"]
    p = propose(s)
    assert p is not None
    assert p.param != "f9_vol_mult", "proposer must respect cooldown"


def test_propose_relaxes_cooldown_when_exhausted():
    s = fresh_state(dt.date(2025, 1, 1), dt.date(2026, 2, 13), dt.date(2026, 2, 14), dt.date(2026, 5, 7))
    # Mark every param as recently modified — cooldown will exhaust the option list,
    # but the relaxation branch should still return something.
    s.recently_modified = list(config.SEARCH_SPACE.keys())[: config.PARAM_COOLDOWN_ITERATIONS]
    p = propose(s)
    assert p is not None


def test_propose_advances_with_iteration_counter():
    s = fresh_state(dt.date(2025, 1, 1), dt.date(2026, 2, 13), dt.date(2026, 2, 14), dt.date(2026, 5, 7))
    s.iteration = 0
    p1 = propose(s)
    s.iteration = 1
    p2 = propose(s)
    s.iteration = 2
    p3 = propose(s)
    # Different iterations should yield different proposals (at least one differs).
    proposals = [(p1.param, p1.new_value), (p2.param, p2.new_value), (p3.param, p3.new_value)]
    assert len(set(proposals)) > 1, "proposer should not return identical proposals across iterations"


def test_propose_never_returns_no_op():
    s = fresh_state(dt.date(2025, 1, 1), dt.date(2026, 2, 13), dt.date(2026, 2, 14), dt.date(2026, 5, 7))
    for i in range(20):
        s.iteration = i
        p = propose(s)
        assert p is not None
        assert p.new_value != p.old_value, f"iter {i}: proposer returned a no-op"
