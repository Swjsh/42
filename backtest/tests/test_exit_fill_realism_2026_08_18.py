"""Guards for the exit-fill realism proxy.

WHY IT EXISTS: the 2026-08-18 cost audit resolved ENTRY fill realism with high confidence but
left EXITS unverified -- market orders carry no submitted limit to diff against. That gap was
worth 2.3x on the book (-$2,201 vs -$5,069 scenarios) while the arms sit only 0.6-5.1pp under
their own breakeven win rates, so it decided whether the strategy is marginally-under or
hopelessly-under.

METHOD: Alpaca's historical options QUOTES endpoint 404s on this key, but options BARS are
free. So we ask the answerable question -- where in the minute's traded range did the fill
land? -- and use BUY fills as the built-in control. Measured over real engine fills:

    BUY  median position 0.667  (high in range = paying the ask -> realistic)
    SELL median position 0.462  (mid, NOT the ~0.333 a genuine bid-hit implies)

The asymmetry is the finding: entries are charged realistically, exits are credited about
0.129 of the traded range better than a real market sell would get.

These tests pin the PURE math only. They never hit the network.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("efr", REPO / "setup" / "scripts" / "exit_fill_realism.py")
efr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(efr)  # type: ignore[union-attr]


def test_position_at_low_is_zero_and_at_high_is_one() -> None:
    assert efr.position_in_range(0.50, 0.50, 0.60) == 0.0
    assert efr.position_in_range(0.60, 0.50, 0.60) == 1.0


def test_position_at_midpoint_is_half() -> None:
    # pytest.approx, not ==: (0.55-0.50)/(0.60-0.50) is 0.5000000000000006 in binary float.
    assert efr.position_in_range(0.55, 0.50, 0.60) == pytest.approx(0.5)


def test_thin_range_returns_None_not_a_default() -> None:
    """THE IMPORTANT ONE. A one-trade minute (high == low) is NOT evidence of a midpoint
    fill. Defaulting it to 0.5 would manufacture the exact conclusion this instrument
    exists to test -- a silent-zero-class error with the sign flipped."""
    assert efr.position_in_range(0.50, 0.50, 0.50) is None
    assert efr.position_in_range(0.50, 0.495, 0.505) is None, "sub-threshold range must not score"


def test_fill_outside_the_bar_is_clamped_not_extrapolated() -> None:
    assert efr.position_in_range(0.40, 0.50, 0.60) == 0.0
    assert efr.position_in_range(0.90, 0.50, 0.60) == 1.0


def test_malformed_inputs_return_None() -> None:
    for args in ((None, 0.5, 0.6), ("x", 0.5, 0.6), (0.55, None, 0.6), (0.55, 0.5, "y")):
        assert efr.position_in_range(*args) is None


def test_loader_takes_only_engine_attributed_option_sells(tmp_path: Path) -> None:
    """Never J's manual fills, never equities, never buys."""
    import json
    led = tmp_path / "fills.jsonl"
    rows = [
        {"is_option": True, "attribution": "engine", "side": "sell", "ts_utc": "2026-08-01T14:00:00Z", "date_et": "2026-08-01"},
        {"is_option": True, "attribution": "manual", "side": "sell", "ts_utc": "2026-08-01T14:01:00Z", "date_et": "2026-08-01"},
        {"is_option": True, "attribution": "engine", "side": "buy",  "ts_utc": "2026-08-01T14:02:00Z", "date_et": "2026-08-01"},
        {"is_option": False, "attribution": "engine", "side": "sell", "ts_utc": "2026-08-01T14:03:00Z", "date_et": "2026-08-01"},
    ]
    led.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    orig = efr.FILLS_LEDGER
    try:
        efr.FILLS_LEDGER = led
        got = efr.load_option_sell_fills()
        assert len(got) == 1, f"filter admitted the wrong rows: {got}"
        assert got[0]["attribution"] == "engine"
    finally:
        efr.FILLS_LEDGER = orig


def test_loader_respects_max_date_cutoff(tmp_path: Path) -> None:
    """Same-day option bars 403; the cutoff must actually exclude them."""
    import json
    led = tmp_path / "fills.jsonl"
    rows = [
        {"is_option": True, "attribution": "engine", "side": "sell", "ts_utc": "2026-08-01T14:00:00Z", "date_et": "2026-08-01"},
        {"is_option": True, "attribution": "engine", "side": "sell", "ts_utc": "2026-08-18T14:00:00Z", "date_et": "2026-08-18"},
    ]
    led.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    orig = efr.FILLS_LEDGER
    try:
        efr.FILLS_LEDGER = led
        assert len(efr.load_option_sell_fills(max_date="2026-08-17")) == 1
    finally:
        efr.FILLS_LEDGER = orig


def test_bid_side_and_midpoint_verdicts_are_distinguishable() -> None:
    """The thresholds must actually separate the two hypotheses this instrument tests."""
    assert efr.position_in_range(0.502, 0.50, 0.60) < 0.35, "a bid-side fill must read bid-side"
    assert efr.position_in_range(0.55, 0.50, 0.60) >= 0.45, "a mid fill must read as mid"
