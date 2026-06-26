"""WP-5 parity net — the order-builder per-setup STRIKE RESOLVER contract.

This is the safety net for the WP-5 dispatch (`risk_gate.select_strike_offset`), the
exact mirror of the WP-0 `select_exit_params` net (`test_engine_order_bracket_parity.py`)
and the C29 / C14 graduation: "per-setup knobs do not transfer; vary-and-assert".

THE LEAK (analysis/recommendations/WP5-STRIKE-AB-SCORECARD.md): the ONE live edge —
`vwap_continuation` (`j_vwap_cont_enabled=true`, Safe-2) — fires the GENERIC v15 OTM-2
tier, the WEAKEST of four cells, but is VALIDATED at ATM (Safe) / ITM-2 (Bold). WP-5
wires a pure dispatch so a matched + ENABLED setup re-strikes to its validated cell;
otherwise the resolved strike is BYTE-IDENTICAL to today's generic v15-tier behavior.

The load-bearing property under test (the KILL criterion in the WP-5 plan):

    With the per-setup strike-override flag OFF, `select_strike_offset(...)` returns the
    SAME `current_strike_offset` for EVERY setup it is asked about. Any drift = revert.

CONVENTION (load-bearing — sim-accuracy gate, OP-16): TWO INVERSE conventions exist.
  * simulator_real / `current_strike_offset` (the value passed to simulate_trade_real):
        NEGATIVE=ITM (ATM=0, ITM-2=-2, OTM-2=+2).
  * filters.py / live params accessor: NEGATIVE=OTM (ATM=0, ITM-2=+2, OTM-2=-2) — INVERSE.
The validated live-params offsets (`j_vwap_cont_strike_offset_safe=0`,
`j_vwap_cont_strike_offset_bold=2`) are NEGATED by the resolver to the simulator
convention, so the flag-ON result is Safe → 0 (ATM) and Bold → -2 (ITM-2), matching the
validated A/B cells in `_wp5_strike_ab.py`.

Single source of truth: the offset literals are NOT duplicated here — they are read
through the same `filters.py` accessors the resolver uses, so this test moves in lockstep
with the params keys (`automation/state/params.json` / `aggressive/params.json`).
"""

from __future__ import annotations

import copy

import pytest

from lib import risk_gate
from lib import filters as _filters


# ── Setup name exactly as the watcher emits it (single source of truth:
#    vwap_continuation_watcher.py setup_name= field) ──────────────────────────────
VWAP_CONT = "VWAP_CONTINUATION"

# Representative generic v15-tier offsets the order path would have computed today
# (`side_strike_off` in orchestrator.py, in the SIMULATOR convention). The exact
# magnitudes are irrelevant to the parity property — what matters is that the resolver
# returns them UNCHANGED whenever the strike-override flag is OFF. OTM-2 = sim +2 is the
# CURRENT LIVE Safe-2 tier (the leak source); a few extra distinct values guard against a
# silent fall-through to the accessor (which would change the result).
GENERIC_OTM2_SIM = 2     # OTM-2 = sim +2 (the LIVE Safe-2 $2K generic tier, the leak)
GENERIC_OTM1_SIM = 1     # OTM-1 = sim +1
GENERIC_ATM_SIM = 0      # ATM   = sim  0
GENERIC_ITM2_SIM = -2    # ITM-2 = sim -2

# Validated flag-ON results (simulator convention, after the resolver's negation):
#   Safe live-params offset 0  (ATM)   -> sim  0
#   Bold live-params offset +2 (ITM-2) -> sim -2
EXPECTED_SAFE_ON_SIM = 0
EXPECTED_BOLD_ON_SIM = -2


def _safe_params_flag_off() -> dict:
    """Safe-2 params snapshot with the strike-override flag explicitly OFF.

    Mirrors the on-disk production Safe params (j_vwap_cont_strike_override_enabled=false,
    j_vwap_cont_strike_offset_safe=0) — the state in which the resolved strike MUST equal
    today's generic v15-tier behavior for every setup.
    """
    return {
        "j_vwap_cont_strike_override_enabled": False,
        "j_vwap_cont_strike_offset_safe": 0,   # ATM (live-params convention)
        # generic ladder that should be IGNORED by the resolver (the resolver only sees
        # the offset the orchestrator already resolved, passed in as current_strike_offset)
        "v15_strike_offset_per_tier": [{"equity_min": 2000, "equity_max": 10000, "strike_offset": -2}],
    }


def _bold_params_flag_off() -> dict:
    """Bold/aggressive params snapshot with the strike-override flag explicitly OFF."""
    return {
        "j_vwap_cont_strike_override_enabled": False,
        "j_vwap_cont_strike_offset_bold": 2,   # ITM-2 (live-params convention)
    }


# ─────────────────────────────────────────────────────────────────────────────
# (a) Strike-override flag OFF -> resolver returns the GENERIC tier for EVERY setup.
#     This is the byte-identity / KILL property.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "setup_name",
    [
        VWAP_CONT,                              # the WP-5 target setup itself
        "BEARISH_REJECTION_RIDE_THE_RIBBON",   # the orchestrator's live gate-cascade setup
        "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "VWAP_RECLAIM_FAILED_BREAK",           # a WP-0 (different-dispatch) setup
        "VIX_REGIME_DAYSIDE",
        "SOME_UNKNOWN_SETUP",
        "",                                    # blank
    ],
)
@pytest.mark.parametrize("side", ["P", "C"])
@pytest.mark.parametrize(
    "current_offset",
    [GENERIC_OTM2_SIM, GENERIC_OTM1_SIM, GENERIC_ATM_SIM, GENERIC_ITM2_SIM],
)
def test_flag_off_resolves_to_generic_for_every_setup(setup_name, side, current_offset) -> None:
    # Safe params, flag off
    assert (
        risk_gate.select_strike_offset(setup_name, side, _safe_params_flag_off(), current_offset)
        == current_offset
    ), f"flag-off drift on {setup_name!r}/{side}/off={current_offset} (Safe params)"
    # Bold params, flag off
    assert (
        risk_gate.select_strike_offset(setup_name, side, _bold_params_flag_off(), current_offset)
        == current_offset
    ), f"flag-off drift on {setup_name!r}/{side}/off={current_offset} (Bold params)"


def test_flag_off_none_or_empty_params_is_generic() -> None:
    """No params at all (older snapshot) / empty dict -> still byte-identical to generic."""
    assert (
        risk_gate.select_strike_offset(VWAP_CONT, "C", None, GENERIC_OTM2_SIM)
        == GENERIC_OTM2_SIM
    )
    assert (
        risk_gate.select_strike_offset(VWAP_CONT, "P", {}, GENERIC_OTM2_SIM)
        == GENERIC_OTM2_SIM
    )


# ─────────────────────────────────────────────────────────────────────────────
# (b) vwap_continuation with the flag ON -> the VALIDATED per-account cell, sourced
#     from the filters.py accessor (the offset comes from the SAME accessor; the
#     literal is not duplicated here) and NEGATED to the simulator convention.
# ─────────────────────────────────────────────────────────────────────────────
def test_vwap_cont_flag_on_safe_resolves_to_atm() -> None:
    params = _safe_params_flag_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    # The accessor returns the live-params offset (0 = ATM); the resolver negates.
    assert _filters.vwap_cont_strike_offset(params) == 0   # live-params ATM
    expected = -_filters.vwap_cont_strike_offset(params)    # sim convention
    assert expected == EXPECTED_SAFE_ON_SIM
    # Even with a deliberately-WRONG generic offset (the live OTM-2 leak), the override
    # wins when the flag is on, and re-strikes to ATM (sim 0).
    for side in ("P", "C"):
        assert (
            risk_gate.select_strike_offset(VWAP_CONT, side, params, GENERIC_OTM2_SIM)
            == EXPECTED_SAFE_ON_SIM
        ), f"Safe flag-ON should re-strike to ATM (sim 0), side={side}"


def test_vwap_cont_flag_on_bold_resolves_to_itm2() -> None:
    params = _bold_params_flag_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    # The accessor returns the live-params offset (+2 = ITM-2); the resolver negates.
    assert _filters.vwap_cont_strike_offset(params) == 2    # live-params ITM-2
    expected = -_filters.vwap_cont_strike_offset(params)    # sim convention
    assert expected == EXPECTED_BOLD_ON_SIM
    for side in ("P", "C"):
        assert (
            risk_gate.select_strike_offset(VWAP_CONT, side, params, GENERIC_OTM2_SIM)
            == EXPECTED_BOLD_ON_SIM
        ), f"Bold flag-ON should re-strike to ITM-2 (sim -2), side={side}"


def test_unknown_setup_with_flag_on_still_generic() -> None:
    """An UNRELATED setup never picks up vwap_continuation's strike override, even when
    the strike-override flag happens to be ON."""
    params = _safe_params_flag_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    for setup in (
        "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "VWAP_RECLAIM_FAILED_BREAK",
        "SOME_UNKNOWN_SETUP",
    ):
        assert (
            risk_gate.select_strike_offset(setup, "P", params, GENERIC_OTM2_SIM)
            == GENERIC_OTM2_SIM
        ), f"{setup!r} must keep the generic tier even with the flag on"


def test_non_str_setup_is_generic() -> None:
    """A non-str setup_name (defensive) -> generic offset unchanged."""
    params = _safe_params_flag_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    assert risk_gate.select_strike_offset(None, "P", params, GENERIC_ITM2_SIM) == GENERIC_ITM2_SIM
    assert risk_gate.select_strike_offset(123, "C", params, GENERIC_ITM2_SIM) == GENERIC_ITM2_SIM


def test_resolver_is_pure_no_mutation() -> None:
    """Resolver must not mutate params (immutability / no side effects)."""
    params = _safe_params_flag_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    before = copy.deepcopy(params)
    risk_gate.select_strike_offset(VWAP_CONT, "P", params, GENERIC_OTM2_SIM)
    assert params == before
