"""Guards for backtest/tools/repeatability_decompose_2026_08_04.py (LENS 4, 2026-08-04).

Three of these pin defects that were REAL in this file during the build, not hypotheticals:

  1. limit_anchor cross-contract leak -- the SHIP-A-reverted lane anchored a $0.42 OTM-2
     option's exit state to the ATM contract's $1.41 marketable limit. The runner stop then
     resolved ABOVE the entry and the walk booked PROFIT on a stop-out; the YESTERDAY lane
     printed +$630 with six positive "premium_stop" exits before it was caught.
  2. tick_is_admissible treating placement reason "not_enter" as a refusal -- that stub is
     written on EVERY non-ENTER tick, including the flatness-blocked HOLD rows the whole
     counterfactual depends on, and silently deleted every counterfactual admission.
  3. claim_blocks missing entirely -- without the 180s per-symbol entry claim the flat-state
     machine re-enters on every freed tick and manufactures round trips production would have
     refused (+$942 of pure artifact on the parity lane).

The rest pin the arithmetic the artifact's headline numbers rest on.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import repeatability_decompose_2026_08_04 as rd  # noqa: E402


# --- strike + symbol math --------------------------------------------------
def test_otm2_call_is_two_strikes_ABOVE_atm():
    """pick_strike: BULL calls take strike = round(spot) - offset, offset=-2 -> atm + 2.
    Getting this backwards would price the counterfactual as ITM-2 and invert every delta."""
    assert rd.otm2_strike(763, "C") == 765


def test_otm2_put_is_two_strikes_BELOW_atm():
    assert rd.otm2_strike(763, "P") == 761


def test_otm2_rejects_an_unknown_side():
    with pytest.raises(ValueError):
        rd.otm2_strike(763, "X")


def test_occ_symbol_matches_the_real_2026_08_04_contract():
    assert rd.occ_symbol("2026-08-04", 763, "C") == "SPY260804C00763000"
    assert rd.occ_symbol("2026-08-04", 745, "P") == "SPY260804P00745000"


# --- admissibility ---------------------------------------------------------
def test_a_flatness_blocked_hold_row_IS_admissible():
    """The counterfactual's whole engine: risky-1/risky-3 were OFFERED the 09:58 ELITE ribbon
    and refused it only because a vwap position was open."""
    assert rd.tick_is_admissible(
        "HOLD", "risk_gate denied: PA3S9N1IV0A4: position already open (status='open')",
        "not_enter", False) is True


def test_not_enter_placement_stub_is_not_treated_as_a_refusal():
    """DEFECT #2. 'not_enter' is written on every non-ENTER tick; treating it as a structural
    refusal deleted every counterfactual admission in the file."""
    assert "not_enter" in rd.NON_REFUSAL_PLACEMENT_REASONS
    assert rd.tick_is_admissible("HOLD", "position already open", "not_enter", False) is True


def test_a_structural_placement_refusal_is_inadmissible_in_every_lane():
    """SKIP_LATE_ENTRY is a config-INDEPENDENT time ceiling the live tape already proved."""
    assert rd.tick_is_admissible("ENTER_BULL", "ribbon_ride C (ELITE)",
                                 "SKIP_LATE_ENTRY", False) is False


def test_duplicate_claim_refusal_is_left_to_the_modelled_claim_ttl():
    assert rd.tick_is_admissible("ENTER_BULL", "ribbon_ride C",
                                 "SKIP_DUPLICATE_CLAIM", False) is True


def test_a_gate_refusal_stays_refused():
    assert rd.tick_is_admissible("HOLD", "gate: requires confluence/sequence",
                                 "not_enter", False) is False


def test_no_signal_tick_is_not_admissible():
    assert rd.tick_is_admissible("HOLD", "no qualifying setup (no strategy fired)",
                                 "not_enter", False) is False


# --- the 180s entry claim (DEFECT #3) --------------------------------------
def _t(h, m):
    return dt.datetime(2026, 8, 4, h, m)


def test_claim_blocks_the_same_symbol_inside_180s():
    claims = {"_symbol": "SPY260804C00762000", "_at": _t(9, 46)}
    assert rd.claim_blocks(claims, "SPY260804C00762000", _t(9, 48)) is True


def test_claim_expires_after_180s():
    claims = {"_symbol": "SPY260804C00763000", "_at": _t(9, 50)}
    assert rd.claim_blocks(claims, "SPY260804C00763000", _t(9, 53)) is False
    assert rd.claim_blocks(claims, "SPY260804C00763000", _t(9, 52)) is True


def test_claim_is_keyed_on_symbol_so_a_new_strike_places_immediately():
    """The mechanism that turned risky-3's seven 09:46-09:57 ENTER ticks into four fills:
    09:50 was a NEW symbol (763C vs 762C) so it placed inside 762C's live claim window."""
    claims = {"_symbol": "SPY260804C00762000", "_at": _t(9, 46)}
    assert rd.claim_blocks(claims, "SPY260804C00763000", _t(9, 47)) is False


def test_claim_ttl_matches_production():
    assert rd.ENTRY_CLAIM_TTL_SEC == 180


# --- limit_anchor (DEFECT #1) ----------------------------------------------
def test_limit_anchor_uses_the_live_limit_on_the_unchanged_contract():
    assert rd.limit_anchor(1.38, 1.41, 1.38, same_contract=True) == 1.41


def test_limit_anchor_transfers_the_cross_buffer_ADDITIVELY_to_a_new_strike():
    """A ratio transfer would scale a 3-cent buffer by the strike's price ratio."""
    assert rd.limit_anchor(0.42, 1.41, 1.38, same_contract=False) == pytest.approx(0.45)


def test_limit_anchor_RAISES_on_a_cross_contract_leak():
    """THE regression this file exists to prevent: anchoring a $0.42 option to the ATM
    contract's $1.41 limit made runner_stop resolve above entry and booked fake profit."""
    with pytest.raises(ValueError, match="outside"):
        rd.limit_anchor(0.42, 1.41, None, same_contract=True)


def test_limit_anchor_falls_back_to_the_entry_premium_when_no_live_pair_exists():
    assert rd.limit_anchor(0.55, None, None, same_contract=False) == 0.55


# --- config axes -----------------------------------------------------------
def test_vwap_setups_are_dropped_only_when_the_fix_is_reverted():
    assert rd.setup_allowed("VWAP_CONTINUATION", vwap_emission=True) is True
    assert rd.setup_allowed("VWAP_CONTINUATION", vwap_emission=False) is False
    assert rd.setup_allowed("BULLISH_RECLAIM_RIDE_THE_RIBBON", vwap_emission=False) is True


def test_elite_bull_gate_matches_gates_py_conditions():
    """gates.py #3: tier == ELITE AND 'level_reclaim' in triggers."""
    assert rd.core_elite_bull_blocked("ELITE", ["level_reclaim", "confluence"],
                                      block_elite_bull=True) is True
    assert rd.core_elite_bull_blocked("ELITE", ["confluence"], block_elite_bull=True) is False
    assert rd.core_elite_bull_blocked("BASE", ["level_reclaim"], block_elite_bull=True) is False
    assert rd.core_elite_bull_blocked("ELITE", ["level_reclaim"], block_elite_bull=False) is False


def test_safe_2_is_NOT_on_the_bold_core_tier_table():
    """safe-2 rides V15_SAFE_TIERS (ATM through $10K) and is untouched by
    ATM-TIER-EXTENSION-2K-10K; attributing its P&L to that ship would be a real error."""
    assert "safe-2" not in rd.BOLD_CORE_TIER_ARMS
    assert {"bold-2", "safe-3", "risky-1", "risky-3"} == set(rd.BOLD_CORE_TIER_ARMS)


def test_min_entry_premium_matches_live_params():
    import json
    p = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    assert rd.MIN_ENTRY_PREMIUM == p["min_entry_premium"]


# --- live round-trip matching ----------------------------------------------
def test_match_live_roundtrip_requires_the_same_symbol():
    rts = [{"symbol": "SPY260804C00763000", "entry_ts_et": "2026-08-04T09:58:00-04:00"}]
    assert rd.match_live_roundtrip(rts, "SPY260804C00765000", _t(9, 58)) is None
    assert rd.match_live_roundtrip(rts, "SPY260804C00763000", _t(9, 58)) is not None


def test_match_live_roundtrip_window_is_bounded():
    rts = [{"symbol": "SPY260804C00763000", "entry_ts_et": "2026-08-04T09:58:00-04:00"}]
    assert rd.match_live_roundtrip(rts, "SPY260804C00763000", _t(10, 30)) is None


# --- end-to-end: the parity gate the artifact's headline rests on ----------
def test_hybrid_lane_reproduces_the_broker_day_exactly():
    """OP-16 sim-accuracy gate. If TODAY does not equal the broker to the cent, the admission
    machine is wrong and no counterfactual lane in the artifact is quotable."""
    try:
        res = rd.run("2026-08-04")
    except (FileNotFoundError, OSError) as exc:
        pytest.skip(f"market data not present in this tree: {exc}")
    assert res["parity"]["gate"] == "PASS"
    assert res["parity"]["hybrid_abs_err"] == pytest.approx(0.0, abs=0.01)
    assert res["lanes"]["TODAY"]["total"] == pytest.approx(res["real_broker"]["TOTAL"], abs=0.01)


def test_elite_gate_revert_zeroes_both_cores_and_leaves_fleet_untouched():
    """Every core ENTER_BULL on 2026-08-04 was ELITE + level_reclaim, and fleet_rest arms
    never enforced GATE_ORDER -- so the revert is exactly (safe-2 + bold-2) -> 0."""
    try:
        res = rd.run("2026-08-04")
    except (FileNotFoundError, OSError) as exc:
        pytest.skip(f"market data not present in this tree: {exc}")
    lane = res["lanes"]["REV_ELITE_GATE"]["per_arm"]
    today = res["lanes"]["TODAY"]["per_arm"]
    assert lane["safe-2"]["net"] == 0 and lane["bold-2"]["net"] == 0
    for arm in rd.FLEET_ARMS:
        assert lane[arm]["net"] == today[arm]["net"]
