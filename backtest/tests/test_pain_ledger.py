"""Guard suite for setup/scripts/pain_ledger.py -- the MAE/MFE pain ledger (WS9, prereg
analysis/pain-ledger/PREREG-2026-08-01.md).

PURE layer only (no network, no ledger). The rails these guards protect, in priority order
-- each one's failure would be SILENT and would poison every future stop study that cites
this ledger as its evidence base:

  1. ENTRY+1 WINDOW. If the entry bar's own low leaks into the window, every trade "takes
     heat" it could never have been managed through, and MAE inflates book-wide. Same for
     bars after the final exit: heat we never held through is not pain.
  2. FLOORS + SIGNS. mae_pct <= 0 <= mfe_pct always; a never-adverse trade is 0.0 with
     time_to None -- never a positive "adverse" excursion, never a fabricated timestamp.
  3. FIRST-TOUCH TIMING. time-to-extreme is time to the FIRST bar printing it; ties must
     not drift to the last touch (that silently lengthens every time_to).
  4. STOP SEMANTICS. `stop_inside_mae` counts a TOUCH; the as-configured stop resolves
     placement > arm_patch > default, and structure-mode stops are labelled as the
     catastrophe cap they are -- never passed off as the operative stop.
  5. EXCLUDE-AND-COUNT (C7/L241). No-bars / no-window / bad-entry positions must be
     counted, never zero-filled and never silently dropped: n_positions must equal
     n_scored + all exclusion counters.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pain_ledger as pl  # noqa: E402


def _bar(t: str, o=1.0, h=1.0, low=1.0, c=1.0) -> dict:
    return {"t": t, "o": o, "h": h, "l": low, "c": c}


ENTRY_TS = "2026-07-31T16:19:02.259Z"          # fill inside the 16:19 bar


# ---------------------------------------------------------------------------------
# 1. THE WINDOW (entry+1 in, final-exit-bar out)
# ---------------------------------------------------------------------------------

def test_holding_window_excludes_entry_bar_low():
    """A catastrophic low ON the entry bar must never count as MAE: the live exit pass
    cannot act inside the entry bar's own minute (ENTRY-BAR-CONVENTION-RULING-2026-07-25)."""
    bars = [_bar("2026-07-31T16:19:00Z", low=0.01),          # entry bar spike-down
            _bar("2026-07-31T16:20:00Z", low=0.90),
            _bar("2026-07-31T16:21:00Z", low=0.95)]
    w = pl.holding_window(bars, ENTRY_TS, "2026-07-31T16:21:30Z")
    assert [b["t"] for b in w] == ["2026-07-31T16:20:00Z", "2026-07-31T16:21:00Z"]
    m = pl.excursion_metrics(1.0, 1.0, ENTRY_TS, w, "2026-07-31T16:21:30Z")
    assert m["min_low"] == 0.90                              # 0.01 must be unreachable
    assert m["mae_pct"] == pytest.approx(-0.10)


def test_holding_window_stops_at_final_exit_bar():
    """A crash AFTER we were flat is not pain we held through."""
    bars = [_bar("2026-07-31T16:20:00Z", low=0.95, h=1.2),
            _bar("2026-07-31T16:25:00Z", low=0.90, h=1.1),   # final exit bar
            _bar("2026-07-31T16:40:00Z", low=0.05, h=9.0)]   # post-flat crash+spike
    w = pl.holding_window(bars, ENTRY_TS, "2026-07-31T16:25:11Z")
    assert [b["t"] for b in w] == ["2026-07-31T16:20:00Z", "2026-07-31T16:25:00Z"]
    m = pl.excursion_metrics(1.0, 1.0, ENTRY_TS, w, "2026-07-31T16:25:11Z")
    assert m["min_low"] == 0.90 and m["max_high"] == 1.2     # neither 0.05 nor 9.0 leak in


# ---------------------------------------------------------------------------------
# 2. FLOORS + SIGNS
# ---------------------------------------------------------------------------------

def test_mae_floor_zero_when_never_adverse():
    """A trade that never traded below entry has MAE 0.0 and NO time-to-MAE -- a positive
    'adverse excursion' or an invented timestamp would both be lies."""
    w = [_bar("2026-07-31T16:20:00Z", low=1.05, h=1.10),
         _bar("2026-07-31T16:21:00Z", low=1.02, h=1.30)]
    m = pl.excursion_metrics(1.0, 2.0, ENTRY_TS, w, "2026-07-31T16:21:30Z")
    assert m["mae_pct"] == 0.0
    assert m["mae_dollars_entry_qty"] == 0.0
    assert m["time_to_mae_min"] is None
    assert m["mae_before_first_exit"] is None
    assert m["mfe_pct"] == pytest.approx(0.30)


def test_mfe_floor_zero_when_never_favorable():
    w = [_bar("2026-07-31T16:20:00Z", low=0.80, h=0.95),
         _bar("2026-07-31T16:21:00Z", low=0.70, h=0.90)]
    m = pl.excursion_metrics(1.0, 2.0, ENTRY_TS, w, "2026-07-31T16:21:30Z")
    assert m["mfe_pct"] == 0.0
    assert m["mfe_dollars_entry_qty"] == 0.0
    assert m["time_to_mfe_min"] is None
    assert m["mfe_before_first_exit"] is None
    assert m["mae_pct"] == pytest.approx(-0.30)


def test_known_excursions_exact_pcts_dollars_and_times():
    """End-to-end arithmetic pin: entry 1.00 x 3 lots; low 0.70 two bars in, high 1.50 five
    bars in -> MAE -30% / -$90, MFE +50% / +$150, t->MAE 2m, t->MFE 5m."""
    w = [_bar("2026-07-31T16:20:00Z", low=0.90, h=1.10),
         _bar("2026-07-31T16:21:00Z", low=0.70, h=1.20),
         _bar("2026-07-31T16:24:00Z", low=0.80, h=1.50)]
    m = pl.excursion_metrics(1.0, 3.0, ENTRY_TS, w, "2026-07-31T16:24:30Z")
    assert m["mae_pct"] == pytest.approx(-0.30)
    assert m["mae_dollars_entry_qty"] == pytest.approx(-90.0)
    assert m["time_to_mae_min"] == 2
    assert m["mfe_pct"] == pytest.approx(0.50)
    assert m["mfe_dollars_entry_qty"] == pytest.approx(150.0)
    assert m["time_to_mfe_min"] == 5
    assert m["n_bars_walked"] == 3


def test_excursion_metrics_refuses_empty_window_and_bad_entry():
    """None on empty window / non-positive entry -- the caller COUNTS these; a fabricated
    zero-row here would be indistinguishable from a real one (C7)."""
    assert pl.excursion_metrics(1.0, 1.0, ENTRY_TS, [], "2026-07-31T16:21:00Z") is None
    w = [_bar("2026-07-31T16:20:00Z")]
    assert pl.excursion_metrics(0.0, 1.0, ENTRY_TS, w, "2026-07-31T16:21:00Z") is None


# ---------------------------------------------------------------------------------
# 3. FIRST-TOUCH TIMING
# ---------------------------------------------------------------------------------

def test_time_to_extreme_is_first_touch_on_ties():
    """Two bars print the identical min low -> time-to-MAE is the FIRST touch. Drifting to
    the last touch silently lengthens every time_to in the ledger."""
    w = [_bar("2026-07-31T16:20:00Z", low=0.70, h=1.10),
         _bar("2026-07-31T16:35:00Z", low=0.70, h=1.10),     # same low, 15 min later
         _bar("2026-07-31T16:36:00Z", low=0.90, h=1.50),
         _bar("2026-07-31T16:40:00Z", low=0.95, h=1.50)]     # same high, later
    m = pl.excursion_metrics(1.0, 1.0, ENTRY_TS, w, "2026-07-31T16:41:00Z")
    assert m["time_to_mae_min"] == 1      # 16:19 -> 16:20, not 16:35
    assert m["time_to_mfe_min"] == 17     # 16:19 -> 16:36, not 16:40


def test_before_first_exit_is_strictly_before():
    """An extreme printing in the SAME minute as the first exit fill is NOT 'before' it --
    the $-at-entry-qty figure cannot claim full size was still on."""
    w = [_bar("2026-07-31T16:20:00Z", low=0.70, h=1.0),
         _bar("2026-07-31T16:25:00Z", low=0.80, h=1.50)]
    same_minute = pl.excursion_metrics(1.0, 1.0, ENTRY_TS, w, "2026-07-31T16:20:30Z")
    assert same_minute["mae_before_first_exit"] is False     # low @16:20, first exit @16:20
    later_exit = pl.excursion_metrics(1.0, 1.0, ENTRY_TS, w, "2026-07-31T16:25:01Z")
    assert later_exit["mae_before_first_exit"] is True       # low @16:20, first exit @16:25
    assert later_exit["mfe_before_first_exit"] is False      # high @16:25 == exit minute


# ---------------------------------------------------------------------------------
# 4. STOP SEMANTICS
# ---------------------------------------------------------------------------------

def test_stop_inside_mae_touch_counts():
    assert pl.stop_inside_mae(0.49, 0.50) is True    # traded through
    assert pl.stop_inside_mae(0.50, 0.50) is True    # exact touch COUNTS (frozen)
    assert pl.stop_inside_mae(0.51, 0.50) is False   # never reached
    assert pl.stop_inside_mae(None, 0.50) is None    # honest absence, never a guessed False
    assert pl.stop_inside_mae(0.49, None) is None


def test_stop_fields_precedence_placement_over_patch_over_default():
    """The as-configured-at-the-time stop: as-placed placement block is most authoritative,
    then the arm's exit_patch, then the engine default -50% catastrophe cap."""
    s = pl.stop_fields(2.0, {"premium_stop_pct": -0.20, "stop_mode": "premium"},
                       {"exit_patch": "ignored-shape-keys-live-at-top-level",
                        "premium_stop_pct": -0.35})
    assert s["premium_stop_pct"] == -0.20 and s["source"] == "placement"
    assert s["stop_premium"] == pytest.approx(1.60)
    assert s["stop_basis"] == "premium"

    s = pl.stop_fields(2.0, None, {"premium_stop_pct": -0.35})
    assert s["premium_stop_pct"] == -0.35 and s["source"] == "arm_patch"

    s = pl.stop_fields(2.0, None, None)
    assert s["premium_stop_pct"] == -0.50 and s["source"] == "default"
    assert s["stop_premium"] == pytest.approx(1.00)


def test_stop_basis_labels_structure_mode_as_catastrophe_cap():
    """A structure-mode stop's premium number is the -50% cap, NOT the operative chart stop
    -- mislabelling it would let a reader 'validate' a stop that never existed."""
    s = pl.stop_fields(1.0, {"stop_mode": "structure"}, None)
    assert s["stop_basis"] == "structure_catastrophe_cap"
    s = pl.stop_fields(1.0, {"stop_mode": "premium"}, None)
    assert s["stop_basis"] == "premium"
    s = pl.stop_fields(1.0, None, None)                      # stop_mode unrecoverable
    assert s["stop_basis"] == "premium_unverified"


# ---------------------------------------------------------------------------------
# 5. EXCLUDE-AND-COUNT + classification + splits + distribution honesty
# ---------------------------------------------------------------------------------

def _pos(symbol="SPY260731C00746000", arm="safe-2", entry_price=1.0, qty=3.0,
         pnl=100.0, entry_ts=ENTRY_TS, exits=None) -> dict:
    return {"date_et": "2026-07-31", "arm": arm, "symbol": symbol,
            "entry_price": entry_price, "entry_qty": qty, "entry_ts_utc": entry_ts,
            "actual_exit_pnl": pnl,
            "exit_fills": exits or [{"ts_utc": "2026-07-31T16:25:00Z", "price": 1.3, "qty": qty}]}


def _good_bars() -> list[dict]:
    return [_bar("2026-07-31T16:20:00Z", low=0.9, h=1.2),
            _bar("2026-07-31T16:25:00Z", low=0.95, h=1.4)]


def test_build_rows_excludes_and_counts_never_zero_fills():
    """THE C7 guard: no-bars, no-window and bad-entry positions are each COUNTED in their
    own bucket, appear in no row, and the accounting invariant holds exactly."""
    p_ok = _pos()
    p_nobars = _pos(symbol="SPY260731C00747000")
    p_nowin = _pos(symbol="SPY260731C00748000",
                   exits=[{"ts_utc": ENTRY_TS, "price": 1.0, "qty": 3.0}])   # exit same bar
    p_bad = _pos(symbol="SPY260731C00749000", entry_price=0.0)

    def bars_for(pos):
        if pos["symbol"] == p_nobars["symbol"]:
            return []
        if pos["symbol"] == p_nowin["symbol"]:
            return [_bar("2026-07-31T16:19:00Z")]            # entry bar only -> empty window
        return _good_bars()

    built = pl.build_rows([p_ok, p_nobars, p_nowin, p_bad], bars_for,
                          placement_for=lambda pos: None, patches={},
                          setup_for=lambda pos, placement: None)
    assert built["n_positions"] == 4
    assert built["n_scored"] == 1
    assert [r["symbol"] for r in built["rows"]] == [p_ok["symbol"]]
    assert built["no_bars"] == [f"2026-07-31 safe-2 {p_nobars['symbol']}"]
    assert built["no_window"] == [f"2026-07-31 safe-2 {p_nowin['symbol']}"]
    assert built["bad_entry"] == [f"2026-07-31 safe-2 {p_bad['symbol']}"]
    # the scored row is real, not zero-filled, and unattributed setups are labelled
    row = built["rows"][0]
    assert row["setup"] == "(unattributed)"
    assert row["outcome"] == "winner"
    assert row["mae_pct"] == pytest.approx(-0.10)
    assert row["stop"]["stop_inside_mae"] is False           # min_low 0.9 > stop 0.5


def test_classify_outcome_three_way():
    assert pl.classify_outcome(0.01) == "winner"
    assert pl.classify_outcome(-0.01) == "loser"
    assert pl.classify_outcome(0.0) == "scratch"             # neither side absorbs scratches


def test_recent_older_split_boundary_exact():
    dates = [f"2026-06-{d:02d}" for d in range(1, 31)]       # 30 distinct dates
    recent, older = pl.recent_older_split(dates, n_recent=25)
    assert len(recent) == 25 and len(older) == 5
    assert "2026-06-06" in recent and "2026-06-05" in older  # boundary lands exactly
    # duplicates must not inflate the recent window
    recent2, older2 = pl.recent_older_split(dates + dates, n_recent=25)
    assert recent2 == recent and older2 == older


def test_dist_empty_is_none_never_zero_filled():
    d = pl.dist([])
    assert d == {"n": 0, "mean": None, "p25": None, "p50": None, "p75": None, "p90": None}


def test_percentile_linear_interpolation_known_values():
    vals = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert pl.percentile(vals, 50) == 20.0
    assert pl.percentile(vals, 25) == 10.0
    assert pl.percentile(vals, 90) == pytest.approx(36.0)    # 0.9*(5-1)=3.6 -> 30+0.6*10
    assert pl.percentile([], 50) is None
    assert pl.percentile([7.0], 90) == 7.0


def test_minutes_between_parses_and_fails_honestly():
    assert pl.minutes_between("2026-07-31T16:19", "2026-07-31T16:43") == 24
    assert pl.minutes_between("garbage", "2026-07-31T16:43") is None
