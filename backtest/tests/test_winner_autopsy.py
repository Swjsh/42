"""Guard suite for setup/scripts/winner_autopsy.py -- the winner-side autopsy organ.

Covers the PURE layer only (no network, no ledger): the conventions and the arithmetic that
the capture-rate headline rests on. The rails these guards exist to protect, in priority
order, are the ones whose failure would be SILENT and would mislead J:

  1. ENTRY+1. If the entry bar leaks back into the exit-eligible window, every variant gets
     to sell into the signal bar's own spike and the whole grid inflates.
  2. THE HEADLINE DENOMINATOR. `capture_vs_best_policy` must be a SINGLE fixed policy's
     total, never the sum of per-trade winners -- conflating them silently converts an
     honest number into a hindsight one.
  3. NEVER ZERO-FILL. Unreplayable variants must exclude a row from the aggregate, not
     count as $0 (C7/L241: a silent zero is indistinguishable from a real one).
  4. NON-POSITIVE DENOMINATORS. A ratio against a <=0 total is meaningless and must be
     None, never a number.
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

import winner_autopsy as wa  # noqa: E402


def _bar(t: str, o=1.0, h=1.0, low=1.0, c=1.0) -> dict:
    return {"t": t, "o": o, "h": h, "l": low, "c": c}


# ---------------------------------------------------------------------------------
# 1. ENTRY+1 CONVENTION
# ---------------------------------------------------------------------------------

def test_entry_bar_minute_floors_fill_timestamp_to_its_bar():
    """A fill at 16:19:02.259Z belongs to the 16:19 bar."""
    assert wa.entry_bar_minute("2026-07-31T16:19:02.259487Z") == "2026-07-31T16:19"
    assert wa.entry_bar_minute("2026-07-31T16:19:00Z") == "2026-07-31T16:19"
    assert wa.entry_bar_minute("2026-07-31T16:19:00+00:00") == "2026-07-31T16:19"


def test_exit_eligible_bars_excludes_the_entry_bar_itself():
    """THE convention guard (ENTRY-BAR-CONVENTION-RULING-2026-07-25): a position placed on
    tick N is not exit-checked until N+1, so the entry bar's own high must be unreachable."""
    bars = [_bar("2026-07-31T16:18:00Z"), _bar("2026-07-31T16:19:00Z", h=9.99),
            _bar("2026-07-31T16:20:00Z"), _bar("2026-07-31T16:21:00Z")]
    elig = wa.exit_eligible_bars(bars, "2026-07-31T16:19:02.259Z")
    ts = [b["t"] for b in elig]
    assert ts == ["2026-07-31T16:20:00Z", "2026-07-31T16:21:00Z"]
    # the 9.99 spike on the entry bar must not be sellable
    assert wa.high_water(elig)[0] == 1.0


def test_exit_eligible_bars_excludes_pre_entry_bars():
    bars = [_bar("2026-07-31T16:00:00Z", h=5.0), _bar("2026-07-31T16:20:00Z")]
    assert wa.exit_eligible_bars(bars, "2026-07-31T16:19:02Z") == [bars[1]]


def test_bars_between_stops_at_the_final_exit_bar():
    """In-trade high must not include premium that printed after we were flat -- the
    2026-07-31 case (position flat 12:43 ET, contract's day high at 15:54 ET)."""
    bars = [_bar("2026-07-31T16:19:00Z"), _bar("2026-07-31T16:20:00Z", h=2.0),
            _bar("2026-07-31T16:43:00Z", h=3.0), _bar("2026-07-31T19:54:00Z", h=99.0)]
    in_trade = wa.bars_between(bars, "2026-07-31T16:19:02Z", "2026-07-31T16:43:03Z")
    assert [b["t"] for b in in_trade] == ["2026-07-31T16:20:00Z", "2026-07-31T16:43:00Z"]
    assert wa.high_water(in_trade)[0] == 3.0        # in-trade high
    assert wa.high_water(wa.exit_eligible_bars(bars, "2026-07-31T16:19:02Z"))[0] == 99.0  # day


# ---------------------------------------------------------------------------------
# 2. THE HEADLINE DENOMINATOR
# ---------------------------------------------------------------------------------

def _row(realized, variants, oracle=None, complete=True):
    return {"realized_pnl": realized, "variants": variants, "_complete": complete,
            "oracle_pnl": oracle, "capture": wa.per_trade_capture(realized, variants)}


def test_aggregate_uses_a_single_fixed_policy_not_the_per_trade_best():
    """THE anti-hindsight guard. Policy A wins trade 1, policy B wins trade 2. The honest
    denominator is the better SINGLE column (100), never the per-trade max sum (140)."""
    rows = [_row(50.0, {"A": 100.0, "B": 20.0}), _row(50.0, {"A": 0.0, "B": 40.0})]
    agg = wa.aggregate_capture(rows, ("A", "B"))
    assert agg["policy_totals"] == {"A": 100.0, "B": 60.0}
    assert agg["best_policy"] == "A"
    assert agg["best_policy_total"] == 100.0
    assert agg["capture_vs_best_policy"] == 1.0          # 100 realized / 100 best column
    # the hindsight number is DIFFERENT and strictly lower -- proving they are not conflated
    assert agg["per_trade_best_total"] == 140.0
    assert agg["capture_vs_per_trade_best"] == pytest.approx(100.0 / 140.0, abs=1e-4)
    assert agg["capture_vs_best_policy"] > agg["capture_vs_per_trade_best"]


def test_capture_can_exceed_one_when_shipped_beats_every_policy():
    """Honesty in the other direction: the module must be able to report that our own exits
    won. A harness that can only ever find fault is not measuring."""
    rows = [_row(120.0, {"A": 100.0, "B": 60.0})]
    agg = wa.aggregate_capture(rows, ("A", "B"))
    assert agg["capture_vs_best_policy"] == 1.2


# ---------------------------------------------------------------------------------
# 3. NEVER ZERO-FILL / NEVER SILENTLY DROP
# ---------------------------------------------------------------------------------

def test_incomplete_rows_are_excluded_and_counted_never_zero_filled():
    rows = [_row(50.0, {"A": 100.0, "B": 20.0}),
            _row(999.0, {"A": None, "B": 20.0}, complete=False)]
    agg = wa.aggregate_capture(rows, ("A", "B"))
    assert agg["n_winners_scored"] == 1
    assert agg["n_excluded_incomplete"] == 1
    assert agg["realized_total"] == 50.0        # the 999 must NOT leak into the total
    assert agg["policy_totals"]["A"] == 100.0   # and must NOT be zero-filled into a column


def test_per_trade_capture_ignores_unreplayable_variants():
    cap = wa.per_trade_capture(50.0, {"A": None, "B": 100.0})
    assert cap["best_variant"] == "B"
    assert cap["capture_vs_best_variant"] == 0.5


def test_per_trade_capture_all_none_is_honest_none():
    cap = wa.per_trade_capture(50.0, {"A": None, "B": None})
    assert cap["best_variant"] is None
    assert cap["capture_vs_best_variant"] is None


def test_empty_population_does_not_fabricate_a_capture_rate():
    agg = wa.aggregate_capture([], ("A",))
    assert agg["n_winners_scored"] == 0
    assert agg["capture_vs_best_policy"] is None
    assert agg["realized_total"] is None


# ---------------------------------------------------------------------------------
# 4. NON-POSITIVE DENOMINATORS
# ---------------------------------------------------------------------------------

def test_non_positive_best_policy_total_yields_none_not_a_number():
    """Every menu policy loses money on this population -- a ratio against <=0 is
    meaningless and must not be rendered as a percentage."""
    rows = [_row(50.0, {"A": -10.0, "B": -20.0})]
    agg = wa.aggregate_capture(rows, ("A", "B"))
    assert agg["best_policy_total"] == -10.0
    assert agg["capture_vs_best_policy"] is None


def test_sufficient_n_flag_gates_the_headline():
    small = wa.aggregate_capture([_row(1.0, {"A": 1.0})], ("A",))
    assert small["sufficient_n"] is False
    big = wa.aggregate_capture([_row(1.0, {"A": 1.0})] * wa.MIN_N_FOR_AGGREGATE, ("A",))
    assert big["sufficient_n"] is True


# ---------------------------------------------------------------------------------
# 5. GIVEBACK + CLASSIFICATION
# ---------------------------------------------------------------------------------

def test_leg_giveback_math():
    gb = wa.leg_giveback(leg_price=0.48, peak_before_leg=0.71, qty=2)
    assert gb["giveback_per_contract"] == pytest.approx(0.23)
    assert gb["giveback_dollars"] == pytest.approx(46.0)
    assert gb["giveback_pct_of_peak"] == pytest.approx(0.3239, abs=1e-4)


def test_leg_giveback_without_bar_coverage_is_none_not_zero():
    gb = wa.leg_giveback(0.48, None, 2)
    assert gb["giveback_dollars"] is None and gb["giveback_pct_of_peak"] is None


def test_runner_underperformed_tp1_tag_fires_on_the_2026_07_31_shape():
    """The anchor case: TP1 filled 0.65, runner trailed out at 0.48."""
    legs = [{"stage": "tp1", "price": 0.65, "giveback": {"giveback_pct_of_peak": 0.03}},
            {"stage": "trail", "price": 0.48, "giveback": {"giveback_pct_of_peak": 0.324}}]
    tags = wa.classify_winner(126.0, legs, {"A": 1000.0})
    assert "runner_underperformed_tp1" in tags
    assert "runner_material_giveback" in tags
    assert "captured_under_half" in tags


def test_no_runner_underperform_tag_when_runner_beat_tp1():
    legs = [{"stage": "tp1", "price": 0.65, "giveback": {"giveback_pct_of_peak": 0.0}},
            {"stage": "trail", "price": 0.90, "giveback": {"giveback_pct_of_peak": 0.0}}]
    assert "runner_underperformed_tp1" not in wa.classify_winner(300.0, legs, {"A": 100.0})


def test_shipped_exit_beat_menu_tag_is_reachable():
    """C13: a tier nobody can reach is a dead tier. The honesty tag must actually fire."""
    legs = [{"stage": "tp1", "price": 1.0, "giveback": {"giveback_pct_of_peak": 0.0}}]
    assert "shipped_exit_beat_menu" in wa.classify_winner(500.0, legs, {"A": 100.0})


def test_runner_cohort_only_counts_scaled_out_winners():
    """A one-leg winner has no runner and must not dilute the cohort denominator."""
    scaled = {"legs": [{"stage": "tp1", "price": 0.65,
                        "giveback": {"giveback_pct_of_peak": 0.03}},
                       {"stage": "trail", "price": 0.48,
                        "giveback": {"giveback_pct_of_peak": 0.324}}],
              "tags": ["runner_underperformed_tp1", "runner_material_giveback"]}
    one_leg = {"legs": [{"stage": "tp1", "price": 0.65,
                         "giveback": {"giveback_pct_of_peak": 0.0}}], "tags": []}
    rc = wa.runner_cohort_stats([scaled, one_leg])
    assert rc["n_scaled_out_winners"] == 1
    assert rc["n_runner_below_tp1"] == 1
    assert rc["median_runner_giveback_pct"] == pytest.approx(0.324)


def test_attribution_coverage_counts_unattributed_legs():
    rows = [{"legs": [{"stage": "tp1"}, {"stage": None}]}]
    ac = wa.attribution_coverage(rows)
    assert ac["legs_total"] == 2 and ac["legs_unattributed"] == 1
    assert ac["attribution_pct"] == 0.5


# ---------------------------------------------------------------------------------
# 6. ENTRY FILL QUALITY + SHIPPED SHAPE
# ---------------------------------------------------------------------------------

def test_entry_fill_quality_flags_a_fill_at_the_bar_high():
    """The 2026-07-31 746C entry filled at 0.33 on a 0.29-0.33 bar."""
    q = wa.entry_fill_quality(0.33, _bar("t", h=0.33, low=0.29))
    assert q["filled_at_bar_high"] is True
    assert q["paid_above_low_pct"] == pytest.approx(0.1379, abs=1e-4)


def test_entry_fill_quality_without_a_bar_is_honest_none():
    q = wa.entry_fill_quality(0.33, None)
    assert q["paid_above_low_pct"] is None and q["filled_at_bar_high"] is None


def test_resolve_shipped_shape_layers_placement_over_patch_over_defaults():
    shape = wa.resolve_shipped_shape(
        placement={"tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667},
        arm_patch={"trail_pct": 0.2, "profit_lock_mode": "trailing", "tp1_premium_pct": 0.3})
    assert shape["tp1_premium_pct"] == 1.0      # placement wins over patch
    assert shape["trail_pct"] == 0.2            # patch wins over default
    assert shape["profit_lock_mode"] == "trailing"
    assert shape["profit_lock_arm_scope"] == "post_tp1"   # L248: never left implicit


def test_exit_menu_pins_arm_scope_on_every_shape():
    """L234/L248: a knob that is unconditional in prod but optional in the study is how a
    harness silently diverges from live. Every declared shape must pin it."""
    for name, shape in wa.EXIT_MENU.items():
        assert shape.get("profit_lock_arm_scope") == "post_tp1", name


def test_oracle_is_day_scoped_and_never_the_headline_denominator():
    bars = [_bar("t1", h=2.0), _bar("t2", h=5.0)]
    assert wa.oracle_pnl(bars, entry_price=1.0, qty=2) == pytest.approx(800.0)
    agg = wa.aggregate_capture([_row(50.0, {"A": 100.0}, oracle=800.0)], ("A",))
    assert agg["best_policy_total"] == 100.0     # headline uses the POLICY, not the oracle
    assert agg["capture_vs_oracle"] == pytest.approx(0.0625)
