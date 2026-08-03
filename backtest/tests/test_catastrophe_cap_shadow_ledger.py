"""Guard suite for setup/scripts/catastrophe_cap_shadow_ledger.py -- the ACCRUAL mechanism for
CATASTROPHE-CAP-WIDEN-WATCH (queue.md, filed 2026-07-23 EOD): "shadow-log every future
catastrophe-cap fire + its held-to-EOD counterfactual until n>=10, then a pre-registered
decision. Do NOT widen on n=4."

PURE layer only (no network, no ledger I/O). The rails these guards protect -- each one's
failure would silently corrupt the eventual n>=10 decision:

  1. FIRE DEFINITION. Only a stop_basis=='structure_catastrophe_cap' position whose closing
     fill staged 'premium_stop' counts. A plain premium-mode stop (stop_basis=='premium') must
     NEVER be counted even if it also staged 'premium_stop' -- the label is legitimately shared
     (EXITMGR-STAGE-LABEL-CONFLATION); only condition (1) makes it unambiguous.
  2. DEDUP KEY. One row per real fire, ever -- date+arm+symbol, so a re-run can never double-
     count a fire already in the ledger (the accrual would silently inflate n toward the
     decision bar).
  3. EOD BAR. The 16:00 ET (20:00 UTC) cutoff is EXCLUSIVE on the UTC side and picks the LATEST
     qualifying bar -- never a bar at/after the close, never an arbitrary bar.
  4. COUNTERFACTUAL MATH + READINESS. held-to-EOD pnl at full entry qty; the summary's
     ready_for_decision flag flips at exactly DECISION_N, never before, and NEVER reads as a
     ship/hold verdict by itself (descriptive_only stays True unconditionally).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import catastrophe_cap_shadow_ledger as ccs  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. FIRE DEFINITION
# ---------------------------------------------------------------------------------

def test_structure_catastrophe_cap_plus_premium_stop_stage_is_a_fire():
    assert ccs.is_catastrophe_cap_fire("structure_catastrophe_cap", "premium_stop") is True


def test_plain_premium_mode_stop_never_counts_even_with_same_stage_label():
    """The EXITMGR-STAGE-LABEL-CONFLATION case: 'premium_stop' is shared with plain
    premium-mode stops -- those must be excluded, never mistaken for a catastrophe-cap fire."""
    assert ccs.is_catastrophe_cap_fire("premium", "premium_stop") is False


def test_structure_mode_closed_by_a_different_stage_is_not_a_fire():
    """A structure-mode position that TP1'd, ribbon-flipped, or chart-stopped never tripped
    its catastrophe floor -- correctly excluded."""
    for other_stage in ("structure_stop", "ribbon_flip", "tp1", "time_stop", None):
        assert ccs.is_catastrophe_cap_fire("structure_catastrophe_cap", other_stage) is False


def test_premium_unverified_basis_never_counts():
    assert ccs.is_catastrophe_cap_fire("premium_unverified", "premium_stop") is False


# ---------------------------------------------------------------------------------
# 2. DEDUP KEY
# ---------------------------------------------------------------------------------

def test_ledger_key_is_stable_and_distinguishing():
    k1 = ccs.ledger_key("2026-07-25", "bold-2", "SPY260725P00735000")
    k2 = ccs.ledger_key("2026-07-25", "bold-2", "SPY260725P00735000")
    k3 = ccs.ledger_key("2026-07-25", "safe-2", "SPY260725P00735000")
    assert k1 == k2
    assert k1 != k3


# ---------------------------------------------------------------------------------
# 3. LAST EXIT FILL + EOD BAR
# ---------------------------------------------------------------------------------

def test_last_exit_fill_picks_max_ts():
    fills = [{"ts_utc": "2026-07-25T15:56:00Z", "price": 0.90, "qty": 2},
             {"ts_utc": "2026-07-25T15:58:00Z", "price": 0.67, "qty": 3}]
    assert ccs.last_exit_fill(fills)["price"] == 0.67


def test_last_exit_fill_none_on_empty():
    assert ccs.last_exit_fill([]) is None


def _bar(t: str, c: float) -> dict:
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": 1}


def test_eod_bar_excludes_20_00_utc_and_later():
    bars = [_bar("2026-07-25T19:58:00Z", 0.50),
            _bar("2026-07-25T19:59:00Z", 0.55),
            _bar("2026-07-25T20:00:00Z", 999.0),   # AT the cutoff -- must be excluded
            _bar("2026-07-25T20:03:00Z", 999.0)]   # after RTH close entirely
    b = ccs.eod_bar(bars)
    assert b["t"] == "2026-07-25T19:59:00Z"
    assert b["c"] == 0.55


def test_eod_bar_none_on_no_qualifying_bar():
    bars = [_bar("2026-07-25T20:01:00Z", 0.5)]
    assert ccs.eod_bar(bars) is None


def test_eod_bar_none_on_empty():
    assert ccs.eod_bar([]) is None


# ---------------------------------------------------------------------------------
# 4. COUNTERFACTUAL MATH + BUILD ROW + SUMMARY
# ---------------------------------------------------------------------------------

def test_held_to_eod_counterfactual_pnl_math():
    # entry 1.28, held to eod close 0.95, qty 5 -> (0.95-1.28)*5*100
    assert ccs.held_to_eod_counterfactual_pnl(1.28, 5, 0.95) == -165.0


def test_held_to_eod_counterfactual_pnl_none_when_no_eod_bar():
    assert ccs.held_to_eod_counterfactual_pnl(1.28, 5, None) is None


def _pos(entry_price=1.28, qty=5.0, actual_pnl=-305.0) -> dict:
    return {"date_et": "2026-07-25", "arm": "bold-2", "symbol": "SPY260725P00735000",
            "entry_ts_utc": "2026-07-25T15:29:25Z", "entry_price": entry_price, "entry_qty": qty,
            "actual_exit_pnl": actual_pnl}


def test_build_fire_row_flags_better_held_when_counterfactual_beats_actual():
    pos = _pos()
    stop = {"stop_premium": 0.64, "premium_stop_pct": -0.5}
    fill = {"ts_utc": "2026-07-25T15:56:05Z", "price": 0.67, "qty": 5.0}
    eod = _bar("2026-07-25T19:59:00Z", 0.95)   # recovered well past the stop
    row = ccs.build_fire_row(pos, stop, fill, eod)
    assert row["actual_realized_pnl"] == -305.0
    assert row["held_to_eod_counterfactual_pnl"] == -165.0
    assert row["would_have_been_better_held"] is True
    assert row["delta_vs_actual"] == 140.0


def test_build_fire_row_no_eod_bar_leaves_counterfactual_none_not_zero():
    pos = _pos()
    stop = {"stop_premium": 0.64, "premium_stop_pct": -0.5}
    fill = {"ts_utc": "2026-07-25T15:56:05Z", "price": 0.67, "qty": 5.0}
    row = ccs.build_fire_row(pos, stop, fill, None)
    assert row["held_to_eod_counterfactual_pnl"] is None
    assert row["would_have_been_better_held"] is False   # None-safe, never a guessed True


def test_summarize_ready_flag_exactly_at_decision_n():
    rows_9 = [ccs.build_fire_row(_pos(), {"stop_premium": 0.64, "premium_stop_pct": -0.5},
                                 {"ts_utc": "2026-07-25T15:56:05Z", "price": 0.67, "qty": 5.0},
                                 _bar("2026-07-25T19:59:00Z", 0.95)) for _ in range(9)]
    s9 = ccs.summarize(rows_9)
    assert s9["n_fires"] == 9
    assert s9["ready_for_decision"] is False

    rows_10 = rows_9 + [rows_9[0]]
    s10 = ccs.summarize(rows_10)
    assert s10["n_fires"] == 10
    assert s10["ready_for_decision"] is True
    assert s10["descriptive_only"] is True   # never flips even once ready


def test_summarize_aggregate_math_and_rate():
    rows = [ccs.build_fire_row(_pos(actual_pnl=-100.0), {}, {"ts_utc": "t", "price": 0, "qty": 5.0},
                               _bar("t", 1.5)),    # cf pnl = (1.5-1.28)*5*100 = 110 -- better held
            ccs.build_fire_row(_pos(actual_pnl=-100.0), {}, {"ts_utc": "t", "price": 0, "qty": 5.0},
                               _bar("t", 0.5))]     # cf pnl = (0.5-1.28)*5*100 = -390 -- worse held
    s = ccs.summarize(rows)
    assert s["n_fires"] == 2
    assert s["n_counterfactual_scored"] == 2
    assert s["aggregate_actual_pnl"] == -200.0
    assert s["aggregate_held_to_eod_counterfactual_pnl"] == -280.0
    assert s["n_would_have_been_better_held"] == 1
    assert s["rate_would_have_been_better_held"] == 0.5


def test_summarize_excludes_none_counterfactuals_from_aggregate_not_zero_fills():
    rows = [ccs.build_fire_row(_pos(actual_pnl=-50.0), {}, {"ts_utc": "t", "price": 0, "qty": 5.0},
                               None)]   # no EOD bar available
    s = ccs.summarize(rows)
    assert s["n_fires"] == 1
    assert s["n_counterfactual_scored"] == 0
    assert s["aggregate_held_to_eod_counterfactual_pnl"] is None   # not 0.0
