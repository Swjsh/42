"""Guards for the multi-lane watchlist funnel (multi/lib/watchlist.py).

The funnel's job is to turn ~72 names into <=5 worth scoring, and it has TWO opposite failure
modes, both of which this shop has paid for:

  * too loose -> attention spread across everything, correlated positions ("shotgun not sniper")
  * too tight -> nothing ever passes (L199: "6 arms, 700 signals, 0 trades")

So the load-bearing property is: **the funnel must ALWAYS yield a non-empty watchlist when the
universe is non-empty**, because it narrows by RANKING, never by thresholding. A threshold cut
can match nothing on a quiet day; a ranked cut cannot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi.lib import watchlist as w  # noqa: E402

UNIVERSE = [f"SYM{i:02d}" for i in range(72)]


def test_funnel_narrows_72_to_at_most_5():
    cands, counts = w.build_watchlist(UNIVERSE)
    assert counts["universe"] == 72
    assert counts["liquidity"] <= w.KEEP_AFTER_LIQUIDITY
    assert counts["attention"] <= w.KEEP_AFTER_ATTENTION
    assert counts["setup"] <= w.KEEP_AFTER_SETUP
    assert len(cands) <= 5


def test_funnel_is_never_empty_on_a_quiet_day():
    """THE anti-L199 guard. No liquidity data, no attention data, no setups -- a totally quiet
    day -- must still produce something to look at, because every stage RANKS rather than
    thresholds. An empty watchlist here would mean the lane can go blind and never notice."""
    cands, counts = w.build_watchlist(UNIVERSE, liquidity=None, attention=None, setups=None)
    assert len(cands) > 0, (
        "the funnel produced an EMPTY watchlist from a 72-name universe on a quiet day -- "
        "that is the L199 zero-participation failure, and it means a threshold crept in "
        "where a ranked cut belongs"
    )
    assert counts["setup"] == w.KEEP_AFTER_SETUP


def test_relative_volume_dominates_attention_ranking():
    """A high-RVOL name must outrank a big-% mover, because RVOL is the only field comparable
    across a $18 stock and a $700 ETF."""
    att = {
        "SYM00": {"rel_volume": 9.8, "pct_change": 2.0, "scanner_hits": 4},   # MRNA-shaped
        "SYM01": {"rel_volume": 1.1, "pct_change": 25.0, "scanner_hits": 1},  # big % move, normal volume
    }
    cands, _ = w.build_watchlist(["SYM00", "SYM01"], attention=att)
    order = [c.symbol for c in cands]
    assert order[0] == "SYM00", f"expected the 9.8x-RVOL name first, got {order}"


def test_illiquid_names_are_dropped_but_unmeasured_names_are_kept():
    """tradeable=False is a measured fail and drops. NO measurement is not evidence of
    illiquidity and must not silently shrink the universe."""
    liq = {
        "SYM00": {"tradeable": False, "spread_pct": 60.0},
        "SYM01": {"tradeable": True, "spread_pct": 2.0},
        # SYM02 deliberately unmeasured
    }
    cands, counts = w.build_watchlist(["SYM00", "SYM01", "SYM02"], liquidity=liq)
    syms = {c.symbol for c in cands}
    assert "SYM00" not in syms, "a measured-illiquid name survived stage 1"
    assert "SYM01" in syms and "SYM02" in syms, "an UNMEASURED name was wrongly dropped"


def test_tighter_spread_ranks_ahead():
    liq = {"SYM00": {"tradeable": True, "spread_pct": 9.0},
           "SYM01": {"tradeable": True, "spread_pct": 1.2}}
    out = w.stage1_liquidity([w.Candidate("SYM00", spread_pct=9.0, tradeable=True),
                              w.Candidate("SYM01", spread_pct=1.2, tradeable=True)])
    assert [c.symbol for c in out][0] == "SYM01"


def test_setup_score_orders_the_final_cut():
    setups = {f"SYM{i:02d}": {"score": i, "side": "C"} for i in range(10)}
    cands, _ = w.build_watchlist([f"SYM{i:02d}" for i in range(10)], setups=setups)
    scores = [c.setup_score for c in cands]
    assert scores == sorted(scores, reverse=True), f"final cut not ordered by score: {scores}"
    assert scores[0] == 9


def test_empty_universe_fails_loud():
    with pytest.raises(w.WatchlistError, match="empty universe"):
        w.build_watchlist([])


def test_stage_counts_are_the_cascade():
    """stage_counts must let a reader answer 'where did the funnel die' in one look."""
    _, counts = w.build_watchlist(UNIVERSE)
    assert set(counts) == {"universe", "liquidity", "attention", "setup"}
    assert counts["universe"] >= counts["liquidity"] >= counts["attention"] >= counts["setup"]


def test_one_absurd_rvol_print_cannot_dominate_the_ranking():
    """A single 500x print (bad data, or a 1-lot contract) must not crowd out everything --
    the rel-volume term is capped for exactly this reason."""
    att = {"SYM00": {"rel_volume": 500.0, "pct_change": 0.1, "scanner_hits": 0},
           "SYM01": {"rel_volume": 15.0, "pct_change": 20.0, "scanner_hits": 4}}
    a0 = w.attention_score(w.Candidate("SYM00", rel_volume=500.0, pct_change=0.1))
    a1 = w.attention_score(w.Candidate("SYM01", rel_volume=15.0, pct_change=20.0,
                                       scanner_hits=4))
    assert a0 < a1 + 10, f"a 500x outlier dominated: {a0} vs {a1}"
    _ = att
