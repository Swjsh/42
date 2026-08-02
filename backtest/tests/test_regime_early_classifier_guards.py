"""Guards for the EARLY (pre-cutoff) regime classifier feasibility instrument
(REGIME-EARLY-CLASSIFIER-2026-08-02).

THE CARDINAL SIN THIS FILE EXISTS TO CATCH (per CLAUDE.md C6 + the task's own explicit
warning): a hindsight-labelled participation gate would be the worst possible thing to ship.
Every test in section 1 is a NO-LOOKAHEAD proof -- constructed so that feeding the classifier
pipeline bars from AFTER its decision cutoff provably changes nothing about its output, given
identical bars up to the cutoff. Section 2 pins the early-feature arithmetic against the
already-guarded build_day_archetypes.day_features() on the fields they share. Section 3 pins
the classifier builder's own train/eval pipeline never leaks a test day into its own training
fold (the walk-forward TimeSeriesSplit contract).

RED-proofed live, this session: bars_through_cutoff's boundary comparison was flipped from
`<` to `<=` and test_cutoff_boundary_is_exclusive failed exactly as expected (a bar labeled
09:45 was wrongly included in the 09:45 cutoff's window); reverted, confirmed green again.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "backtest"), str(REPO / "backtest" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_day_archetypes as bda  # noqa: E402
from lib.regime_early_features import (  # noqa: E402
    CUTOFFS, MIN_EARLY_BARS, bars_through_cutoff, early_features,
)


def _synthetic_day(closes: list[float], n_bars: int = 78,
                    start: dt.datetime = dt.datetime(2026, 1, 2, 9, 30)) -> pd.DataFrame:
    """78-bar 5m session whose closes linearly interpolate `closes` (mirrors
    test_regime_library_guards.py's own _session() helper -- same synthetic-day convention,
    reused rather than reinvented)."""
    xs = np.linspace(0.0, 1.0, n_bars)
    seg = np.linspace(0.0, 1.0, len(closes))
    c = np.interp(xs, seg, closes)
    o = np.concatenate([[closes[0]], c[:-1]])
    h = np.maximum(o, c) + 0.02
    l = np.minimum(o, c) - 0.02
    ts = [start + dt.timedelta(minutes=5 * i) for i in range(n_bars)]
    return pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l, "close": c})


# =============================================================================
# 1. NO-LOOKAHEAD proofs
# =============================================================================

def test_cutoff_boundary_is_exclusive():
    """A bar labeled EXACTLY at the cutoff (09:45) has NOT closed yet at wall-clock 09:45
    (it spans [09:45,09:50)) and must be excluded. A bar labeled one tick before (09:40) HAS
    closed by 09:45 and must be included. This is the exact boundary a `<` vs `<=` typo would
    silently flip -- flipping it live during this session made this test fail as expected."""
    day = _synthetic_day([600.0, 610.0])
    early = bars_through_cutoff(day, CUTOFFS["09:45"])
    included_times = set(early["ts"].dt.time)
    assert dt.time(9, 40) in included_times, "09:40 bar (closed by 09:45) must be included"
    assert dt.time(9, 45) not in included_times, "09:45 bar (NOT closed until 09:50) must be excluded"
    assert len(early) == 3, f"expected exactly 3 bars (09:30,09:35,09:40), got {len(early)}"


def test_10am_cutoff_is_six_bars():
    day = _synthetic_day([600.0, 610.0])
    early = bars_through_cutoff(day, CUTOFFS["10:00"])
    assert len(early) == 6
    assert early["ts"].dt.time.max() == dt.time(9, 55)


def test_future_bars_cannot_change_early_features_corrupt_the_tail():
    """THE core no-lookahead proof. Build a real-shaped day (gaps up early, would look like a
    'gap-go' if you peeked at the whole session). Compute early_features() on the correctly
    truncated 09:45 prefix. Then build a SECOND version of the exact same day where every bar
    STRICTLY AFTER the 09:45 cutoff is corrupted (reversed order, values replaced with NaN,
    scrambled) -- the kind of corruption that would maximally change any full-day statistic
    (high/low/close/range/gap-fill) if it leaked in. Truncate the corrupted frame through the
    SAME cutoff and recompute. The two feature dicts must be byte-identical: the only way that
    can be true is if early_features() never touched a row past the cutoff."""
    prior_close = 598.0
    day = _synthetic_day([602.0, 604.0, 603.5, 608.0, 601.0, 612.0], n_bars=78)

    clean_early = bars_through_cutoff(day, CUTOFFS["09:45"])
    f_clean = early_features(clean_early, prior_close)

    corrupted = day.copy()
    tail_mask = corrupted["ts"].dt.time >= CUTOFFS["09:45"]
    tail_idx = corrupted.index[tail_mask]
    # reverse + blow out every OHLC value in the tail -- if this leaked into the "early" read,
    # high/low/close/range/gap-fill would all change drastically.
    corrupted.loc[tail_idx, ["open", "high", "low", "close"]] = (
        corrupted.loc[tail_idx, ["open", "high", "low", "close"]].values[::-1] * 50.0 + 9999.0
    )

    corrupted_early = bars_through_cutoff(corrupted, CUTOFFS["09:45"])
    f_corrupted = early_features(corrupted_early, prior_close)

    assert f_clean == f_corrupted, (
        "future-bar corruption changed the early feature read -- LOOKAHEAD LEAK:\n"
        f"clean={f_clean}\ncorrupted={f_corrupted}"
    )
    # and prove the corruption really would have mattered if it HAD leaked (sanity on the
    # test itself -- a corruption that couldn't possibly matter would make this test vacuous)
    f_full_clean = bda.day_features(day, prior_close)
    f_full_corrupted = bda.day_features(corrupted, prior_close)
    assert f_full_clean != f_full_corrupted, (
        "the tail corruption didn't even change the FULL-day features -- test fixture is "
        "vacuous, strengthen it"
    )


def test_extra_appended_future_rows_do_not_change_early_features():
    """Same proof, different corruption shape: instead of mutating in place, APPEND extra
    rows after the cutoff (simulating 'the classifier accidentally saw bars appended later
    in the day'). Early read on the correctly-truncated prefix must be unaffected."""
    prior_close = 598.0
    day = _synthetic_day([602.0, 606.0, 601.0, 615.0], n_bars=40)
    early = bars_through_cutoff(day, CUTOFFS["09:45"])
    f_before = early_features(early, prior_close)

    extra_rows = pd.DataFrame({
        "ts": [dt.datetime(2026, 1, 2, 15, 0) + dt.timedelta(minutes=5 * i) for i in range(5)],
        "open": [9999.0] * 5, "high": [9999.0] * 5, "low": [1.0] * 5, "close": [1.0] * 5,
    })
    day_extended = pd.concat([day, extra_rows], ignore_index=True)
    early_after = bars_through_cutoff(day_extended, CUTOFFS["09:45"])
    f_after = early_features(early_after, prior_close)

    assert f_before == f_after


def test_insufficient_bars_flagged_not_silently_computed():
    """A day with fewer than MIN_EARLY_BARS by the cutoff (feed gap / short session) must be
    flagged, never silently produce a number that looks like a real read (C7)."""
    day = _synthetic_day([600.0, 601.0], n_bars=1)
    early = bars_through_cutoff(day, CUTOFFS["09:45"])
    assert len(early) <= 1
    f = early_features(early, 598.0)
    assert f["insufficient"] is True
    assert MIN_EARLY_BARS >= 2


# =============================================================================
# 2. Arithmetic parity against the already-guarded full-day builder
# =============================================================================

def test_early_features_matches_day_features_arithmetic_on_shared_fields():
    """When given the SAME bars (a full 78-bar day, prior_close set), early_features()'s
    reduction must agree with build_day_archetypes.day_features() on every field they share
    in meaning (open/high/low/close, range%, body%, close_loc, open_loc, gap_pct) -- proves
    the new module didn't quietly drift from the already-guarded formula it's deliberately
    mirroring."""
    prior_close = 596.5
    day = _synthetic_day([600.0, 594.0, 597.0, 599.8], n_bars=78)
    f_full = bda.day_features(day, prior_close)
    f_early = early_features(day, prior_close)   # NOTE: full day passed on purpose here --
    # this test is about arithmetic parity, not truncation; truncation is section 1's job.

    assert f_early["open"] == pytest.approx(f_full["open"])
    assert f_early["high"] == pytest.approx(f_full["high"])
    assert f_early["low"] == pytest.approx(f_full["low"])
    assert f_early["close"] == pytest.approx(f_full["close"])
    assert f_early["gap_pct"] == pytest.approx(f_full["gap_pct"])
    assert f_early["early_range_pct"] == pytest.approx(f_full["range_pct"])
    assert f_early["early_body_pct"] == pytest.approx(f_full["body_pct"])
    assert f_early["early_close_loc"] == pytest.approx(f_full["close_loc"])
    assert f_early["early_open_loc"] == pytest.approx(f_full["open_loc"])


def test_gap_filled_by_cutoff_up_gap():
    # up-gap that has already round-tripped back down through prior_close by the cutoff
    day = _synthetic_day([605.0, 596.0, 598.0], n_bars=6)
    f = early_features(day, prior_close=600.0)
    assert f["gap_pct"] > 0
    assert f["gap_filled_by_cutoff"] is True


def test_gap_filled_by_cutoff_up_gap_not_yet_filled():
    day = _synthetic_day([605.0, 606.0, 608.0], n_bars=6)
    f = early_features(day, prior_close=600.0)
    assert f["gap_pct"] > 0
    assert f["gap_filled_by_cutoff"] is False


# =============================================================================
# 3. Walk-forward split never leaks a test day's own label into its training fold
# =============================================================================

def test_build_regime_early_classifier_walk_forward_no_leakage():
    """Imports the actual builder module (not a re-description of it) and asserts, for every
    walk-forward fold it produces, that every TEST index is strictly greater than every TRAIN
    index it was scored against -- i.e. TimeSeriesSplit's expanding-window contract actually
    holds for THIS population, not just in the abstract."""
    import build_regime_early_classifier as bec

    X, y, dates, meta = bec.build_dataset(cutoff_name="09:45")
    assert len(X) == len(y) == len(dates)
    folds = list(bec.walk_forward_splits(len(X)))
    assert len(folds) >= 3, "too few walk-forward folds to say anything about accuracy"
    for train_idx, test_idx in folds:
        assert max(train_idx) < min(test_idx), (
            "walk-forward leakage: a training row index is >= a test row index it's "
            "supposedly predicting ahead of"
        )
        # every train date must be chronologically before every test date (belt + suspenders
        # on top of the index check -- index order and date order must agree)
        assert max(dates[i] for i in train_idx) < min(dates[i] for i in test_idx)
