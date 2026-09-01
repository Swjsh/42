"""Guard: every futures order price must sit on the contract's tick.

SCAR (2026-08-31). The TastytradeBroker lane placed NOTHING for 10 sessions. Every
attempt died as `invalid_price_increment: Price must be in increments of $0.25`
(broker-transport.jsonl 09:45:07 and 15:00:12 on 2026-08-31) because the signal
generator emitted raw dollar offsets -- stops at 7704.05, 7694.30, 7826.10 -- and
nothing snapped them to `Instrument.tick_size`. A rejected stop leg aborts the whole
bracket, so every entry became ENTER_REFUSED (17 rows across 4/5 recent sessions)
while the tick-agnostic fill simulator traded on and reported a normal day. The real
account sat at exactly its $2,000.00 starting net_liq and no alert fired.

Two properties are load-bearing and both are tested here:
  1. ALIGNMENT  -- no price leaves the core off-tick.
  2. NEVER-WIDER -- the stop is snapped toward entry, because
     futures_trader_core sizes from |entry - stop| BEFORE placing; a stop widened
     after sizing would exceed the risk the rails approved.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.futures_trader_core import _snap_signal_to_tick  # noqa: E402
from futures.instruments import MES, MNQ, is_aligned, snap, snap_protective  # noqa: E402


# The exact prices the broker rejected on 2026-08-31.
REJECTED_STOPS = [7704.05, 7694.30, 7826.10]


@pytest.mark.parametrize("bad", REJECTED_STOPS)
def test_the_actually_rejected_prices_were_off_tick(bad):
    """Pin the diagnosis itself: these are off-tick, which is why they were refused."""
    assert not is_aligned(bad, MES.tick_size)


@pytest.mark.parametrize("bad", REJECTED_STOPS)
def test_snapping_makes_rejected_prices_placeable(bad):
    assert is_aligned(snap(bad, MES.tick_size), MES.tick_size)


def test_short_stop_snaps_down_toward_entry_never_wider():
    """SHORT: stop sits ABOVE entry, so a valid snap must not move it further up."""
    entry, raw = 7682.00, 7694.30
    got = snap_protective(raw, MES.tick_size, entry=entry)
    assert is_aligned(got, MES.tick_size)
    assert got <= raw, "stop was widened -- realised risk would exceed sized risk"
    assert got == pytest.approx(7694.25)


def test_long_stop_snaps_up_toward_entry_never_wider():
    """LONG: stop sits BELOW entry, so a valid snap must not move it further down."""
    entry, raw = 7700.00, 7688.30
    got = snap_protective(raw, MES.tick_size, entry=entry)
    assert is_aligned(got, MES.tick_size)
    assert got >= raw, "stop was widened -- realised risk would exceed sized risk"
    assert got == pytest.approx(7688.50)


def test_already_aligned_prices_are_untouched():
    for px in (7685.50, 7678.00, 7700.25, 7700.75):
        assert snap(px, MES.tick_size) == pytest.approx(px)
        assert snap_protective(px, MES.tick_size, entry=7690.0) == pytest.approx(px)


@pytest.mark.parametrize("inst", [MES, MNQ], ids=lambda i: i.symbol)
def test_full_signal_is_aligned_end_to_end(inst):
    """The real entry path: nothing off-tick may survive _snap_signal_to_tick."""
    sig = {"entry": 7682.07, "stop": 7694.33, "tp1": 7678.11, "runner": 7670.02,
           "direction": "short", "setup": "x", "watcher": "w", "confidence": 0.9}
    out = _snap_signal_to_tick(sig, inst)
    for key in ("entry", "stop", "tp1", "runner"):
        assert is_aligned(out[key], inst.tick_size), f"{key}={out[key]} is off-tick"


def test_snap_does_not_mutate_the_incoming_signal():
    sig = {"entry": 7682.07, "stop": 7694.33, "tp1": 7678.11, "runner": None,
           "direction": "short"}
    before = dict(sig)
    _snap_signal_to_tick(sig, MES)
    assert sig == before, "incoming signal was mutated (immutability rule)"


def test_sizing_distance_never_grows_after_snapping():
    """The property that protects the risk rails, stated directly."""
    sig = {"entry": 7682.07, "stop": 7694.33, "tp1": 7678.11, "runner": None,
           "direction": "short"}
    raw_pts = abs(sig["entry"] - sig["stop"])
    out = _snap_signal_to_tick(sig, MES)
    assert abs(out["entry"] - out["stop"]) <= raw_pts + 1e-9


def test_stop_never_collapses_onto_entry():
    """A zero-distance stop is not a stop -- it must be pushed one tick clear."""
    sig = {"entry": 7682.02, "stop": 7682.13, "tp1": 7680.0, "runner": None,
           "direction": "short"}
    out = _snap_signal_to_tick(sig, MES)
    assert out["stop"] != out["entry"]
    assert abs(out["stop"] - out["entry"]) == pytest.approx(MES.tick_size)
    assert is_aligned(out["stop"], MES.tick_size)


def test_none_runner_stays_none():
    sig = {"entry": 7682.07, "stop": 7694.33, "tp1": 7678.11, "runner": None,
           "direction": "short"}
    assert _snap_signal_to_tick(sig, MES)["runner"] is None
