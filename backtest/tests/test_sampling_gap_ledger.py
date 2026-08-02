"""Guard suite for setup/scripts/sampling_gap_ledger.py -- the runner-leg sampling-gap
quantification (overnight 2026-08-02 runner-leg investigation, sub-problem A).

Rails these guards protect, in priority order -- each one's failure would silently distort
the one number the investigation exists to produce (aggregate dollars lost to SAMPLING,
not to the mechanical trail band the exit shape is designed to have):

  1. SCOPE. Only the worst_premium<=runner_stop family (premium_stop / profit_lock_floor /
     trail / be_stop) is ever scored. structure_stop's `runner_stop` field is the STANDING
     catastrophe cap, not the level that actually fired -- scoring it would silently measure
     the wrong mechanism. tp1/runner_target are upside crossings with a different-signed cost
     model. All five must be counted, never scored, never silently dropped.
  2. NEVER-NEGATIVE SAMPLING GAP. A threshold not yet breached at observation (observed >
     threshold, e.g. a precise same-tick stop) must contribute exactly 0, never a negative
     'gain' that could net against and hide a real gap elsewhere in an aggregate sum.
  3. SLIPPAGE STAYS SIGNED, LOSS IS SEPARATELY CLAMPED. A favorable fill (better than the
     observed quote) must not be clamped away in the signed total, but must also not net
     against and hide unfavorable slippage in the loss-only figure.
  4. EXCLUDE-AND-COUNT (C7/L241 pattern, mirrored from test_pain_ledger.py). Every event
     considered must land in exactly one bucket: scored, not-stop-type, not-placed/WATCH, or
     no-matching-fill. The buckets must sum to the total considered -- never a silent drop.
  5. CADENCE IS MEASURED, NOT ASSUMED. The empirical median-tick-gap helper must correctly
     recover a known synthetic cadence and must not let a single cross-session/overnight gap
     (already-open-to-next-day) distort the median.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import sampling_gap_ledger as sgl  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. SCOPE -- stage family filter
# ---------------------------------------------------------------------------------

def _row(symbol="SPY000000C00000000", stage="premium_stop", kind="SELL_ALL",
         qty=5, runner_stop=0.50, worst=0.45, best=0.55, placed=True, order_id="oid-1",
         ts="2026-07-31T12:43:02-04:00"):
    return {
        "ts_et": ts,
        "exit_pass": [{
            "symbol": symbol,
            "runner_stop": runner_stop,
            "worst_premium": worst,
            "best_premium": best,
            "actions": [{
                "kind": kind, "stage": stage, "qty": qty, "placed": placed,
                "broker": ({"id": order_id} if order_id else {}),
            }],
        }],
    }


def test_stop_type_family_is_scored_structure_and_targets_are_not():
    rows = [
        _row(stage="premium_stop"), _row(stage="profit_lock_floor"),
        _row(stage="trail"), _row(stage="be_stop"),
        _row(stage="structure_stop"), _row(stage="tp1"),
        _row(stage="runner_target"), _row(stage="time_stop"),
        _row(stage="ribbon_flip"),
    ]
    events = sgl._collect_exit_events(rows, "fleet", "arm", "risky-3")
    in_scope = {e["stage"] for e in events if e["in_scope"]}
    out_of_scope = {e["stage"] for e in events if not e["in_scope"]}
    assert in_scope == {"premium_stop", "profit_lock_floor", "trail", "be_stop"}
    assert out_of_scope == {"structure_stop", "tp1", "runner_target", "time_stop", "ribbon_flip"}
    assert len(events) == 9, "every action must be counted exactly once, none silently dropped"


def test_hold_actions_never_enter_the_event_stream():
    """A HOLD tick's exit_pass row carries no `actions` list at all in production data;
    a row with actions=[] must simply contribute zero events, never crash."""
    rows = [{"ts_et": "2026-07-31T12:00:00-04:00",
             "exit_pass": [{"symbol": "SPY", "runner_stop": 0.5, "worst_premium": 0.6,
                            "best_premium": 0.6, "actions": []}]}]
    events = sgl._collect_exit_events(rows, "fleet", "arm", "risky-3")
    assert events == []


# ---------------------------------------------------------------------------------
# 2 + 3. score_event -- the pure dollar core
# ---------------------------------------------------------------------------------

def test_sampling_gap_matches_the_hand_verified_autopsy_trade():
    """risky-3 SPY260731C00746000 runner leg, 2026-07-31 12:43:02 ET: floor 0.552, engine's
    next look saw a bid of 0.50, filled 0.48. The winner-autopsy hand-computed this to the
    cent (WINNER-AUTOPSY-2026-07-31-SYNTHESIS.md section 3): sampling gap 0.052/ct, fill
    slippage 0.020/ct. This is the ground-truth anchor for the whole ledger's methodology."""
    r = sgl.score_event(threshold=0.552, observed=0.50, fill_price=0.48, qty=2)
    assert r["sampling_gap_per_ct"] == 0.052
    assert r["sampling_gap_dollars"] == 10.40           # 0.052 * 2 * 100
    assert r["slippage_loss_dollars"] == 4.00            # 0.02 * 2 * 100
    assert r["slippage_signed_dollars"] == -4.00


def test_sampling_gap_floors_at_zero_never_negative():
    """observed ABOVE threshold (the stop fired precisely, no drift-through) must score a
    sampling gap of exactly 0 -- never a negative number that could hide a real gap
    elsewhere when summed into an aggregate."""
    r = sgl.score_event(threshold=0.50, observed=0.55, fill_price=0.55, qty=3)
    assert r["sampling_gap_per_ct"] == 0.0
    assert r["sampling_gap_dollars"] == 0.0


def test_favorable_slippage_is_signed_not_clamped_but_loss_side_is():
    """A fill BETTER than the observed quote (market moved back up before the sell landed)
    must show as negative in the signed total (so it can offset unfavorable slippage
    elsewhere in an honest aggregate) but must contribute exactly 0 to the loss-only figure
    (never a negative 'loss')."""
    r = sgl.score_event(threshold=0.12, observed=0.08, fill_price=0.10, qty=12)
    assert r["slippage_signed_per_ct"] == 0.02          # fill (0.10) - observed (0.08)
    assert r["slippage_signed_dollars"] == 24.0
    assert r["slippage_loss_dollars"] == 0.0             # favorable -> zero loss, never negative


def test_score_event_handles_zero_qty_without_crashing():
    r = sgl.score_event(threshold=0.5, observed=0.4, fill_price=0.4, qty=0)
    assert r["sampling_gap_dollars"] == 0.0


# ---------------------------------------------------------------------------------
# 4. EXCLUDE-AND-COUNT
# ---------------------------------------------------------------------------------

def test_unplaced_watch_mode_actions_are_excluded_and_counted_not_scored():
    rows = [_row(placed=False, order_id=None)]
    events = sgl._collect_exit_events(rows, "fleet", "arm", "safe-3")
    assert len(events) == 1
    assert events[0]["placed"] is False
    # main()'s join loop would bucket this into n_not_placed, never attempt a fill lookup.


# ---------------------------------------------------------------------------------
# 5. CADENCE IS MEASURED
# ---------------------------------------------------------------------------------

def test_empirical_cadence_recovers_known_synthetic_interval():
    ts = [f"2026-07-31T12:{m:02d}:00-04:00" for m in range(0, 21, 3)]  # exactly 3-min apart
    out = sgl._empirical_cadence_seconds(ts)
    assert out["median_s"] == 180.0
    assert out["n"] == 6


def test_empirical_cadence_recovers_one_minute_interval():
    ts = [f"2026-07-31T12:{m:02d}:00-04:00" for m in range(0, 10)]     # 1-min apart
    out = sgl._empirical_cadence_seconds(ts)
    assert out["median_s"] == 60.0


def test_empirical_cadence_drops_overnight_gap_not_averages_it_in():
    """A session boundary (last tick 15:55 one day, first tick 09:31 the next) is an
    ~17.5-hour gap -- it must be EXCLUDED from the cadence estimate, not blended in and
    dragging the 'median' toward something meaningless."""
    same_day = [f"2026-07-31T12:{m:02d}:00-04:00" for m in range(0, 6)]   # 5 x 1-min gaps
    overnight_next_open = "2026-08-01T09:31:00-04:00"
    out = sgl._empirical_cadence_seconds(same_day + [overnight_next_open])
    assert out["median_s"] == 60.0
    assert out["n"] == 5, "the 1 overnight gap must be dropped, leaving exactly the 5 intraday gaps"
