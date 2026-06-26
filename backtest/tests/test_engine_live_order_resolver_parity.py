"""A5 / WP-8 parity net — the live-order RESOLVER contract.

The safety net for the A5 deterministic callable
(`live_order_resolver.live_order_params`) — the keystone the heartbeat invokes to resolve
vwap_continuation's order params (strike / expiry / stop / qty). It is the union of the
WP-5 strike dispatch, the WP-0 %-stop dispatch, and the WP-8 1DTE + dollar-stop
overrides, behind their respective DORMANT flags.

THE LOAD-BEARING PROPERTY (the KILL criterion): with ALL the vwap_continuation override
flags OFF (the on-disk production default), `live_order_params(...)` returns TODAY'S EXACT
config — BYTE-IDENTICAL to what the order path computes today:

    strike_offset = the generic v15-tier offset passed in (current_strike_offset),
    expiry_dte    = 0 (0DTE),
    stop_pct      = the percent stop passed in (current_stop_pct), stop_dollars = None,
    qty           = the WP-3 cap-respecting base passed in (current_qty).

Any drift with every flag off is a KILL → revert that flag.

Single source of truth: NO strike/stop/threshold literal is duplicated here — the
flag-ON expectations are read through the SAME `filters.py` accessors the resolver uses,
so this test moves in lockstep with the params keys
(`automation/state/params.json` / `aggressive/params.json`).
"""

from __future__ import annotations

import copy

import pytest

from lib import live_order_resolver as lor
from lib import filters as _filters


VWAP_CONT = "VWAP_CONTINUATION"

# Representative "today" inputs the order path would have computed. The magnitudes are
# irrelevant to the parity property — what matters is the resolver returns them UNCHANGED
# when every flag is off. OTM-2 = sim +2 is the CURRENT LIVE Safe-2 tier (the leak source).
GENERIC_OTM2_SIM = 2     # the live Safe-2 $2K generic tier (sim convention)
GLOBAL_STOP_PCT = -0.08  # the current -8% percent stop
BASE_QTY = lor.WP3_BASE_QTY  # 3


def _safe_params_all_flags_off() -> dict:
    """Safe-2 snapshot with EVERY vwap_continuation override flag explicitly OFF.

    Mirrors the on-disk production Safe params — the state in which the resolved order MUST
    equal today's behavior.
    """
    return {
        "j_vwap_cont_strike_override_enabled": False,
        "j_vwap_cont_strike_offset_safe": 0,        # ATM (live-params convention)
        "j_vwap_cont_1dte_enabled": False,
        "j_vwap_cont_dollar_stop_enabled": False,
        "j_vwap_cont_dollar_stop_safe": 35.88,
    }


def _bold_params_all_flags_off() -> dict:
    """Bold/aggressive snapshot with EVERY vwap_continuation override flag explicitly OFF."""
    return {
        "j_vwap_cont_strike_override_enabled": False,
        "j_vwap_cont_strike_offset_bold": 2,        # ITM-2 (live-params convention)
        "j_vwap_cont_1dte_enabled": False,
        "j_vwap_cont_dollar_stop_enabled": False,
        "j_vwap_cont_dollar_stop_bold": 67.68,
    }


# ─────────────────────────────────────────────────────────────────────────────
# (a) ALL flags OFF -> the resolved order is BYTE-IDENTICAL to today, for the
#     vwap_continuation setup AND every other setup. This is the KILL property.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "setup_name",
    [
        VWAP_CONT,                              # the A5/WP-8 target setup itself
        "BEARISH_REJECTION_RIDE_THE_RIBBON",   # the orchestrator's live gate-cascade setup
        "VWAP_RECLAIM_FAILED_BREAK",
        "VIX_REGIME_DAYSIDE",
        "SOME_UNKNOWN_SETUP",
        "",                                    # blank
    ],
)
@pytest.mark.parametrize("side", ["P", "C"])
@pytest.mark.parametrize("params_fn", [_safe_params_all_flags_off, _bold_params_all_flags_off])
def test_all_flags_off_is_byte_identical_to_today(setup_name, side, params_fn) -> None:
    params = params_fn()
    out = lor.live_order_params(
        setup_name,
        "Gamma-Safe-2",
        params,
        current_strike_offset=GENERIC_OTM2_SIM,
        current_stop_pct=GLOBAL_STOP_PCT,
        current_qty=BASE_QTY,
        side=side,
    )
    assert out.strike_offset == GENERIC_OTM2_SIM, f"strike drift on {setup_name!r}/{side}"
    assert out.expiry_dte == 0, f"expiry drift on {setup_name!r}/{side}"
    assert out.stop_pct == GLOBAL_STOP_PCT, f"stop_pct drift on {setup_name!r}/{side}"
    assert out.stop_dollars is None, f"stop should be %-anchored on {setup_name!r}/{side}"
    assert out.qty == BASE_QTY, f"qty drift on {setup_name!r}/{side}"


def test_all_flags_off_none_or_empty_params_is_byte_identical() -> None:
    """No params (older snapshot) / empty dict -> still byte-identical to today."""
    for params in (None, {}):
        out = lor.live_order_params(
            VWAP_CONT, "Gamma-Safe-2", params,
            current_strike_offset=GENERIC_OTM2_SIM,
            current_stop_pct=GLOBAL_STOP_PCT,
        )
        assert out.strike_offset == GENERIC_OTM2_SIM
        assert out.expiry_dte == 0
        assert out.stop_pct == GLOBAL_STOP_PCT
        assert out.stop_dollars is None
        assert out.qty == BASE_QTY


# ─────────────────────────────────────────────────────────────────────────────
# (b) Flag-ON resolves to the VALIDATED config, sourced from the filters accessors.
# ─────────────────────────────────────────────────────────────────────────────
def test_strike_flag_on_safe_resolves_to_atm() -> None:
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    # accessor returns live-params 0 (ATM); resolver negates to sim 0.
    expected_sim = -_filters.vwap_cont_strike_offset(params)
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Safe-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.strike_offset == expected_sim == 0


def test_strike_flag_on_bold_resolves_to_itm2() -> None:
    params = _bold_params_all_flags_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    expected_sim = -_filters.vwap_cont_strike_offset(params)  # -(+2) = -2 (ITM-2)
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Risky-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.strike_offset == expected_sim == -2


def test_1dte_flag_on_sets_expiry_1() -> None:
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_1dte_enabled"] = True
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Safe-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.expiry_dte == 1
    # expiry flag alone does NOT touch the stop — still %-anchored.
    assert out.stop_pct == GLOBAL_STOP_PCT
    assert out.stop_dollars is None


def test_dollar_stop_flag_on_safe_uses_dollar_magnitude() -> None:
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_dollar_stop_enabled"] = True
    expected = _filters.vwap_cont_dollar_stop(params)  # 35.88
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Safe-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.stop_dollars == expected == 35.88
    assert out.stop_pct is None  # exactly one stop form


def test_dollar_stop_flag_on_bold_uses_dollar_magnitude() -> None:
    params = _bold_params_all_flags_off()
    params["j_vwap_cont_dollar_stop_enabled"] = True
    expected = _filters.vwap_cont_dollar_stop(params)  # 67.68
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Risky-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.stop_dollars == expected == 67.68
    assert out.stop_pct is None


def test_all_flags_on_safe_full_validated_config() -> None:
    """The full WP-5 + WP-8 deployment for Safe-2: ATM / 1DTE / $35.88 / qty 3."""
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    params["j_vwap_cont_1dte_enabled"] = True
    params["j_vwap_cont_dollar_stop_enabled"] = True
    out = lor.live_order_params(
        VWAP_CONT, "Gamma-Safe-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert out.strike_offset == 0          # ATM (sim)
    assert out.expiry_dte == 1             # 1DTE
    assert out.stop_dollars == 35.88
    assert out.stop_pct is None
    assert out.qty == 3                    # WP-3 cap-respecting base


def test_overrides_never_apply_to_other_setups_even_when_flags_on() -> None:
    """An UNRELATED setup never picks up vwap_continuation's overrides (C29), even when
    every flag is ON."""
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    params["j_vwap_cont_1dte_enabled"] = True
    params["j_vwap_cont_dollar_stop_enabled"] = True
    for setup in (
        "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "VWAP_RECLAIM_FAILED_BREAK",
        "SOME_UNKNOWN_SETUP",
    ):
        out = lor.live_order_params(
            setup, "Gamma-Safe-2", params,
            current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
        )
        assert out.strike_offset == GENERIC_OTM2_SIM, setup
        assert out.expiry_dte == 0, setup
        assert out.stop_pct == GLOBAL_STOP_PCT, setup
        assert out.stop_dollars is None, setup


def test_stop_stated_exactly_one_way_invariant() -> None:
    """LiveOrderParams enforces the exactly-one-stop invariant (both/neither -> error)."""
    with pytest.raises(ValueError):
        lor.LiveOrderParams(strike_offset=0, expiry_dte=0, stop_pct=-0.08, stop_dollars=35.0, qty=3)
    with pytest.raises(ValueError):
        lor.LiveOrderParams(strike_offset=0, expiry_dte=0, stop_pct=None, stop_dollars=None, qty=3)


def test_resolver_is_pure_no_mutation() -> None:
    params = _safe_params_all_flags_off()
    params["j_vwap_cont_strike_override_enabled"] = True
    params["j_vwap_cont_dollar_stop_enabled"] = True
    before = copy.deepcopy(params)
    lor.live_order_params(
        VWAP_CONT, "Gamma-Safe-2", params,
        current_strike_offset=GENERIC_OTM2_SIM, current_stop_pct=GLOBAL_STOP_PCT,
    )
    assert params == before
