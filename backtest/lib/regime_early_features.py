"""regime_early_features.py -- EARLY (pre-cutoff) session features, the feasibility-gate
instrument for REGIME-EARLY-CLASSIFIER-2026-08-02.

WHY THIS EXISTS: analysis/regime-library/day-archetypes.json (WS6, build_day_archetypes.py)
tags every day with a mechanical archetype computed from the FULL session's OHLC -- its own
README says this out loud: "POST-HOC (uses the whole session)... may slice studies and stamp
YESTERDAY, never feed a live entry decision for the SAME day." To gate live participation on
"today looks like a reliably-losing archetype" you must know the archetype EARLY, from data
available by decision time. This module computes the early-window analogue of
build_day_archetypes.day_features() -- same shape-feature vocabulary, computed over only the
bars that exist by a wall-clock cutoff.

NO-LOOKAHEAD GUARANTEE BY CONSTRUCTION, not a runtime check: early_features() takes a bars
frame AS GIVEN and reduces over every row in it -- it has NO cutoff parameter and no notion of
"the rest of the day." It is structurally incapable of reading a bar it was never handed. The
caller supplies an already-truncated frame via bars_through_cutoff(); if a caller accidentally
passed the full day instead, this function has no way to detect that (mirrors
build_day_archetypes.day_features()'s own "compute over whatever you're given" contract
exactly, for the same reason: keeping the reduction pure and the safety property at the call
site, where it is provable). The RED-proof lives in
backtest/tests/test_regime_early_classifier_guards.py: bars strictly after the cutoff are
corrupted/reversed/NaN'd and the features computed on the (still correctly re-sliced) prefix
are proven byte-identical to the uncorrupted version.

BAR LABELING (et-v2, confirmed against backtest/data/spy_5m_2025-01-01_2026-07-22.csv): a bar
labeled "09:40" spans [09:40, 09:45) and is CLOSED, hence real and usable, once wall-clock
reaches 09:45. bars_through_cutoff(cutoff=09:45) therefore correctly includes the 09:30/09:35/
09:40 bars (3 bars) and excludes the 09:45 bar itself (label >= cutoff -> not yet closed).

CUTOFFS -- task brief's own stated window ("~09:45-10:00 ET"):
    09:45 ET -> first 3 bars (09:30,09:35,09:40)   PRIMARY (earliest actionable point)
    10:00 ET -> first 6 bars (09:30..09:55)         SECONDARY robustness check
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

CUTOFFS: dict[str, dt.time] = {
    "09:45": dt.time(9, 45),
    "10:00": dt.time(10, 0),
    # EXPLORATORY ONLY (added post-hoc, 2026-08-02, after 09:45/10:00 were the pre-registered
    # arms in prereg-regime-standdown-2026-08-02.json): cheap sweep to characterize the
    # accuracy/lateness tradeoff for the write-up's "what would it take" section. NOT part of
    # the frozen prereg, NOT fed into regime_standdown_study.py's arms -- descriptive only,
    # never gates anything (same discipline as G6 in the sibling VIX-gate prereg).
    "10:15": dt.time(10, 15),
    "10:30": dt.time(10, 30),
    "11:00": dt.time(11, 0),
}

# Bars required for a cutoff to be meaningful at all (a session with fewer RTH bars than this
# by the cutoff has nothing to classify from -- e.g. a feed gap). Purely a sanity floor, not a
# tuned threshold.
MIN_EARLY_BARS = 2


def bars_through_cutoff(day_bars: pd.DataFrame, cutoff: dt.time, ts_col: str = "ts") -> pd.DataFrame:
    """Bars whose START label is strictly before `cutoff` (see module docstring for why this
    is the correct closed-bar boundary). `day_bars` must already be RTH-only, ts-sorted --
    the exact contract build_day_archetypes.load_sessions()'s per-day frames satisfy."""
    t = day_bars[ts_col].dt.time
    return day_bars[t < cutoff].reset_index(drop=True)


def early_features(bars: pd.DataFrame, prior_close: float | None) -> dict:
    """Shape features over WHATEVER bars are given -- mirrors
    build_day_archetypes.day_features()'s reduction contract exactly (same underlying
    quantities, early_ prefixed where the semantics necessarily differ from a full-day
    reduction), on purpose: a classifier trained on this vocabulary is reasoned about the
    same way build_day_archetypes.classify()'s cascade already is. Zero knowledge of "cutoff"
    or "the rest of the day" -- see module docstring."""
    n = len(bars)
    if n < MIN_EARLY_BARS:
        return {"n_bars": n, "insufficient": True}
    o = float(bars.iloc[0]["open"])
    h = float(bars["high"].max())
    l = float(bars["low"].min())
    c = float(bars.iloc[-1]["close"])
    rng = h - l
    gap_pct = (100.0 * (o - prior_close) / prior_close) if prior_close else None

    gap_filled = False
    if prior_close is not None and gap_pct is not None:
        if gap_pct > 0:
            gap_filled = bool(l <= prior_close)
        elif gap_pct < 0:
            gap_filled = bool(h >= prior_close)
        else:
            gap_filled = True

    return {
        "n_bars": n,
        "insufficient": False,
        "open": o, "high": h, "low": l, "close": c,
        "gap_pct": gap_pct,
        "gap_dir": (0 if gap_pct is None else (1 if gap_pct > 0 else (-1 if gap_pct < 0 else 0))),
        "gap_filled_by_cutoff": gap_filled,
        "early_range_pct": 100.0 * rng / o if o else 0.0,
        "early_body_pct": 100.0 * (c - o) / o if o else 0.0,
        "early_close_loc": (c - l) / rng if rng > 0 else 0.5,
        "early_open_loc": (o - l) / rng if rng > 0 else 0.5,
    }


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)
