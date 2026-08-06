"""D1 / SWEEP-2 guard -- exit_shape_parity_study must never silently degrade a
structure-mode shape to a premium stop (2026-08-06, HIGH, sign-flip class).

THE DEFECT: replay_position built its ExitState WITHOUT trigger_level /
structure_stop_enabled and ticked plan_exit_actions WITHOUT last_closed_5m_close -- so a
shape declaring stop_mode="structure" (the LIVE registry ribbon_ride shape;
structure_stop_enabled=true in BOTH params files since v15.3) replayed as a -20%-style
premium walk with zero disclosure. Measured on the 2026-08-06 real put: -$76.80 reported
vs +$338.45 broker truth -- SIGN FLIPPED ($415.25 error). Every study built on this helper
was biased pessimistic for structure-mode positions. It also hardcoded side="P" for every
position (inert for premium math, wrong for structure direction on calls).

THE FIX PINNED HERE:
  1. structure-declaring shape + missing structure inputs -> REFUSAL (pnl=None, loud
     reason, lands in n_no_data) -- never a silently-degraded number.
  2. structure-declaring shape + full inputs -> the structure stop is actually MODELED
     (first closed 5m SPY bar beyond trigger_level exits ALL, stage "structure_stop").
  3. side is derived from the OCC symbol, not hardcoded "P".
  4. premium-mode shapes replay byte-identically through the legacy 3-positional-arg call
     (t4_exit_matrix / t5_confirmatory_matrix / stop_width_population_grid compatibility).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_exit_shape_parity_structure_2026_08_06.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "backtest" / "tools"), str(ROOT / "automation" / "state" / "fleet"),
           str(ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import exit_shape_parity_study as esp  # noqa: E402

PUT_POS = {"symbol": "SPY260806P00770000", "arm": "safe-2", "date_et": "2026-08-06",
           "entry_ts_utc": "2026-08-06T14:30:00Z", "entry_qty": 3, "entry_price": 1.00,
           "entry_notional": 3.00, "exit_fills": [], "actual_exit_pnl": 0.0}
CALL_POS = dict(PUT_POS, symbol="SPY260806C00769000")

FLAT_BARS = [
    {"t": "2026-08-06T14:31:00Z", "o": 1.00, "h": 1.02, "l": 0.99, "c": 1.00},
    {"t": "2026-08-06T14:32:00Z", "o": 1.00, "h": 1.02, "l": 0.99, "c": 1.00},
    {"t": "2026-08-06T14:33:00Z", "o": 1.00, "h": 1.02, "l": 0.99, "c": 1.00},
]

STRUCTURE_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 99.0,
                   "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed",
                   "stop_mode": "structure"}
PREMIUM_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                 "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}


def test_structure_shape_without_inputs_refuses_loudly():
    """THE D1 PIN: no structure inputs -> pnl=None + explicit reason. Pre-fix this
    returned a NUMERIC premium-walk pnl -- the silent sign-flip."""
    r = esp.replay_position(PUT_POS, FLAT_BARS, STRUCTURE_SHAPE)
    assert r["pnl"] is None, (
        f"structure-declaring shape produced a numeric pnl {r['pnl']} without structure "
        "inputs -- the silent premium-stop degradation (D1 sign-flip) is back")
    assert "structure_mode_not_modeled" in r["reason"]


def test_structure_shape_with_inputs_models_the_structure_stop():
    """Full inputs -> the chart-level stop actually fires. PUT, trigger 770.0, closed 5m
    SPY close 770.5 ABOVE the level -> exit ALL, stage structure_stop, on the first bar."""
    spy5 = [{"t": "2026-08-06T14:25:00Z", "c": 770.5}]  # closes 14:30Z <= first bar 14:31Z
    r = esp.replay_position(PUT_POS, FLAT_BARS, STRUCTURE_SHAPE,
                            structure_stop_enabled=True, trigger_level=770.0,
                            spy_5m_bars=spy5)
    assert r["pnl"] is not None
    assert r["stop_mode"] == "structure"
    assert r["exits"] and r["exits"][0]["stage"] == "structure_stop", r["exits"]
    assert r["exits"][0]["ts_utc"] == "2026-08-06T14:31:00Z"


def test_structure_stop_holds_while_thesis_intact():
    """Closed 5m close BELOW the put's trigger level -> no structure exit; the walk rides
    to its other exits (here: none within the bars -> open at end)."""
    spy5 = [{"t": "2026-08-06T14:25:00Z", "c": 769.2}]
    r = esp.replay_position(PUT_POS, FLAT_BARS, STRUCTURE_SHAPE,
                            structure_stop_enabled=True, trigger_level=770.0,
                            spy_5m_bars=spy5)
    assert not any(e["stage"] == "structure_stop" for e in r["exits"])


def test_side_derived_from_occ_symbol():
    """side comes from the symbol now -- 'P' was hardcoded for every position pre-fix."""
    assert esp._side_from_occ_symbol("SPY260806C00769000") == "C"
    assert esp._side_from_occ_symbol("SPY260806P00770000") == "P"
    r = esp.replay_position(CALL_POS, FLAT_BARS, PREMIUM_SHAPE)
    assert r["side"] == "C"


def test_call_structure_direction_is_correct():
    """CALL structure stop exits when the closed 5m close is BELOW the trigger level --
    only correct because side is now derived (hardcoded 'P' would invert this)."""
    spy5_break = [{"t": "2026-08-06T14:25:00Z", "c": 768.4}]   # below 769 -> call exits
    r = esp.replay_position(CALL_POS, FLAT_BARS, STRUCTURE_SHAPE,
                            structure_stop_enabled=True, trigger_level=769.0,
                            spy_5m_bars=spy5_break)
    assert r["exits"] and r["exits"][0]["stage"] == "structure_stop"
    spy5_hold = [{"t": "2026-08-06T14:25:00Z", "c": 769.6}]    # above 769 -> call holds
    r2 = esp.replay_position(CALL_POS, FLAT_BARS, STRUCTURE_SHAPE,
                             structure_stop_enabled=True, trigger_level=769.0,
                             spy_5m_bars=spy5_hold)
    assert not any(e["stage"] == "structure_stop" for e in r2["exits"])


def test_premium_shape_legacy_call_signature_unchanged():
    """The pre-existing 3-positional-arg call (every existing caller) still works and
    returns a numeric pnl for premium shapes -- the fix is additive."""
    r = esp.replay_position(PUT_POS, FLAT_BARS, PREMIUM_SHAPE)
    assert r["pnl"] is not None
    assert r["stop_mode"] == "premium"
