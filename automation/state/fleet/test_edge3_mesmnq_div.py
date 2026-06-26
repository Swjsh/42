"""Tests for EDGE #3 (MES->MNQ divergence) frozen-config arm.

Covers the contract that matters for a DORMANT-flip-ready edge:
  1. The frozen config reproduces the VALIDATED OOS expectancy (sign + magnitude),
     i.e. the frozen knobs still map to the gate-clearing cell (+$71.46/tr).
  2. The edge is DORMANT (enabled=False) — the registered default never auto-trades.
  3. The live-tick adapter HONORS the isolated per-edge persistence knob (the edge-#2
     scar): a config with the wrong persistence does NOT reproduce the validated cell,
     proving the knob is actually read & applied (not a dead knob).
  4. When dormant, signal_for_tick forces HOLD even on a real signal (no order path).

Pure Python, $0, no live orders. Run:
    backtest/.venv/Scripts/python.exe -m pytest automation/state/fleet/test_edge3_mesmnq_div.py -v
"""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

import edge3_mesmnq_div as e3


@pytest.fixture(scope="module")
def repro() -> dict:
    return e3.reproduce_validated_expectancy()


def test_frozen_config_is_the_validated_cell() -> None:
    cfg = e3.FROZEN_CONFIG
    assert cfg.leader == "MES" and cfg.laggard == "MNQ"
    assert cfg.threshold == 0.0015
    assert cfg.min_persistence_bars == 2
    assert cfg.qty_micros == 1
    assert cfg.exit_mode == "atr_trail"
    assert cfg.validated_oos_per_trade == pytest.approx(71.46)


def test_reproduces_validated_oos_expectancy_sign(repro: dict) -> None:
    # THE required test: the validated expectancy SIGN is positive (the gate-1 result).
    assert repro["oos_per_trade"] is not None
    assert repro["oos_per_trade"] > 0, "OOS per-trade must be positive (validated +$71.46)"


def test_reproduces_validated_magnitude(repro: dict) -> None:
    # Exact reproduction of the gate-clearing best_cell (n, expectancy, concentration).
    assert repro["n_all"] == 118
    assert repro["oos_per_trade"] == pytest.approx(71.46, abs=0.5)
    assert repro["drop_top5_per_trade"] == pytest.approx(3.65, abs=0.5)
    assert repro["drop_top5_per_trade"] > 0  # gate-5, the blocker the rescue cleared


def test_edge_is_dormant_by_default() -> None:
    # Registered DORMANT — flipping this on is a human action, never a code default.
    assert e3.FROZEN_CONFIG.enabled is False


def test_persistence_knob_is_actually_applied() -> None:
    # edge-#2 scar guard: prove the isolated min_persistence_bars knob is READ & applied.
    # n1 (no concentration fix) must yield a DIFFERENT (larger) trade set than n2; if the
    # knob were dead, n1 and n2 would produce identical results.
    res_n2 = e3.reproduce_validated_expectancy(e3.FROZEN_CONFIG)
    res_n1 = e3.reproduce_validated_expectancy(replace(e3.FROZEN_CONFIG, min_persistence_bars=1))
    assert res_n1["n_all"] != res_n2["n_all"], "persistence knob has no effect -> dead knob"
    assert res_n1["n_all"] > res_n2["n_all"], "n1 should keep >= the n2 subset"


def test_signal_for_tick_holds_when_dormant() -> None:
    # Even on a session that DOES produce a validated signal, a dormant config returns HOLD
    # (no order path). Find a real signal day from the reproduction, then assert HOLD.
    mes = e3.b4.load_futures("MES")
    mnq = e3.b4.load_futures("MNQ")
    common = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common)].reset_index(drop=True)
    lag_atr = e3.b4.atr_series(mnq["high"], mnq["low"], mnq["close"], e3.b4.ATR_LEN)
    sm = e3.b4._per_session_state(mes)
    sn = e3.b4._per_session_state(mnq)
    enriched = e3.b5.enrich_signals(mes, mnq, sm, sn, "MNQ", 0.0015, lag_atr)
    kept = e3.b5.fix_min_persistence(enriched, 2)
    assert kept, "expected at least one validated signal day in the dataset"
    signal_day = kept[0].date

    dec = e3.signal_for_tick(mes, mnq, as_of_date=signal_day)
    assert dec.enabled is False
    assert dec.action == "HOLD"
    assert dec.side in ("long", "short")  # signal WAS detected, just not acted on
    assert "DORMANT" in dec.reason


def test_signal_for_tick_enters_when_enabled() -> None:
    # Sanity: flipping enabled=True on a signal day yields an ENTER decision honoring the
    # persistence knob. (No order placed — this is a pure decision object.)
    mes = e3.b4.load_futures("MES")
    mnq = e3.b4.load_futures("MNQ")
    common = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common)].reset_index(drop=True)
    lag_atr = e3.b4.atr_series(mnq["high"], mnq["low"], mnq["close"], e3.b4.ATR_LEN)
    sm = e3.b4._per_session_state(mes)
    sn = e3.b4._per_session_state(mnq)
    enriched = e3.b5.enrich_signals(mes, mnq, sm, sn, "MNQ", 0.0015, lag_atr)
    kept = e3.b5.fix_min_persistence(enriched, 2)
    signal_day = kept[0].date

    enabled_cfg = replace(e3.FROZEN_CONFIG, enabled=True)
    dec = e3.signal_for_tick(mes, mnq, as_of_date=signal_day, cfg=enabled_cfg)
    assert dec.enabled is True
    assert dec.action in ("ENTER_LONG", "ENTER_SHORT")
    assert dec.persistence is not None and dec.persistence >= 2
    assert dec.entry_idx is not None and dec.chart_stop is not None


def test_signal_for_tick_holds_on_no_signal_day() -> None:
    # A day with no aligned bars / no qualifying divergence returns HOLD, not a crash.
    mes = e3.b4.load_futures("MES")
    mnq = e3.b4.load_futures("MNQ")
    dec = e3.signal_for_tick(mes, mnq, as_of_date=dt.date(1990, 1, 1))
    assert dec.action == "HOLD"
