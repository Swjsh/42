"""WP-0 parity net — the order-bracket stop RESOLVER contract.

This is the safety net for the WP-0 dispatch (`risk_gate.select_exit_params`) and
the L174 / C14 graduation: "dead/translated-but-unapplied knobs — vary-and-assert".
The two isolated per-setup stop accessors in `filters.py`
(`vwap_reclaim_failed_break_premium_stop_pct`, `vix_dayside_premium_stop_pct`) were
validated (both = -0.08) but NOTHING read them at order-build time — the order path
applied the GLOBAL stop to every entry. WP-0 wires a pure dispatch so a matched +
ENABLED setup overrides the stop; otherwise the resolved stop is BYTE-IDENTICAL to
today's global behavior.

The load-bearing property under test (the KILL criterion in the WP-0 plan):

    With EVERY per-setup flag OFF, `select_exit_params(...)` returns the SAME
    `global_stop` for EVERY setup it is asked about. Any drift = revert.

Single source of truth: the -0.08 literals are NOT duplicated here — they are read
through the same `filters.py` accessors asserted in
`test_vwap_reclaim_failed_break_watcher.py` (L244/L255/L260) and
`test_vix_regime_dayside_watcher.py` (L281/L284), so this test moves in lockstep
with those.
"""

from __future__ import annotations

import pytest

from lib import risk_gate
from lib import filters as _filters


# ── Setup names exactly as the watchers emit them (single source of truth:
#    *_watcher.py setup_name= fields) ───────────────────────────────────────────
RECLAIM_FB = "VWAP_RECLAIM_FAILED_BREAK"
VIX_DAYSIDE = "VIX_REGIME_DAYSIDE"

# A representative global stop value the order path would have computed today
# (side_premium_stop in orchestrator.py). The exact magnitude is irrelevant to the
# parity property — what matters is that the resolver returns IT UNCHANGED whenever
# no matching setup flag is ON. Use a value distinct from -0.08 so a silent
# fall-through to the isolated accessor would be CAUGHT (it would change the result).
GLOBAL_STOP_SAFE = -0.08   # Safe-2 v15 default
GLOBAL_STOP_BOLD = -0.07   # Bold global — DIFFERS from the isolated -0.08, so a
                           # wrongly-applied override on the Bold path is detectable.


def _params_flags_off() -> dict:
    """A params snapshot with EVERY per-setup stop flag explicitly OFF.

    Mirrors the on-disk production params (j_*_enabled=false) — the state in which
    the resolved bracket MUST equal today's behavior for every setup.
    """
    return {
        "j_vwap_reclaim_fb_enabled": False,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "j_vix_dayside_enabled": False,
        "j_vix_dayside_premium_stop_pct": -0.08,
        # global knobs that should be IGNORED by the resolver when flags are off
        "premium_stop_pct": -0.50,
    }


# ─────────────────────────────────────────────────────────────────────────────
# (a) ALL per-setup flags OFF -> resolver returns the GLOBAL stop for EVERY setup.
#     This is the byte-identity / KILL property.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "setup_name",
    [
        RECLAIM_FB,
        VIX_DAYSIDE,
        "BEARISH_REJECTION_RIDE_THE_RIBBON",  # the production live setup
        "VWAP_CONTINUATION",
        "SOME_UNKNOWN_SETUP",
        "",                                    # blank
    ],
)
@pytest.mark.parametrize("side", ["P", "C"])
def test_flags_off_resolves_to_global_for_every_setup(setup_name: str, side: str) -> None:
    params = _params_flags_off()
    # Safe global
    assert (
        risk_gate.select_exit_params(setup_name, side, params, GLOBAL_STOP_SAFE)
        == GLOBAL_STOP_SAFE
    ), f"flags-off drift on {setup_name!r}/{side} (Safe global)"
    # Bold global (the -0.07 case that would expose a wrong override)
    assert (
        risk_gate.select_exit_params(setup_name, side, params, GLOBAL_STOP_BOLD)
        == GLOBAL_STOP_BOLD
    ), f"flags-off drift on {setup_name!r}/{side} (Bold global)"


def test_flags_off_none_params_is_global() -> None:
    """No params at all (older snapshot) -> still byte-identical to global."""
    assert (
        risk_gate.select_exit_params(RECLAIM_FB, "P", None, GLOBAL_STOP_BOLD)
        == GLOBAL_STOP_BOLD
    )
    assert (
        risk_gate.select_exit_params(VIX_DAYSIDE, "P", {}, GLOBAL_STOP_SAFE)
        == GLOBAL_STOP_SAFE
    )


# ─────────────────────────────────────────────────────────────────────────────
# (b) Matching setup with its flag ON -> the isolated filters.py accessor value.
#     The -0.08 comes from the SAME accessor the watcher tests assert (no literal
#     duplication here).
# ─────────────────────────────────────────────────────────────────────────────
def test_reclaim_fb_flag_on_uses_isolated_accessor() -> None:
    params = _params_flags_off()
    params["j_vwap_reclaim_fb_enabled"] = True
    expected = _filters.vwap_reclaim_failed_break_premium_stop_pct(params)
    assert expected == -0.08  # mirrors test_vwap_reclaim_failed_break_watcher.py L244
    # Even with a deliberately-WRONG global, the override wins when the flag is on.
    assert (
        risk_gate.select_exit_params(RECLAIM_FB, "P", params, GLOBAL_STOP_BOLD)
        == expected
    )


def test_vix_dayside_flag_on_uses_isolated_accessor() -> None:
    params = _params_flags_off()
    params["j_vix_dayside_enabled"] = True
    expected = _filters.vix_dayside_premium_stop_pct(params)
    assert expected == -0.08  # mirrors test_vix_regime_dayside_watcher.py L281
    assert (
        risk_gate.select_exit_params(VIX_DAYSIDE, "C", params, GLOBAL_STOP_BOLD)
        == expected
    )


def test_unknown_setup_with_flags_on_still_global() -> None:
    """An UNRELATED setup never picks up another setup's isolated stop, even when
    every per-setup flag happens to be ON."""
    params = _params_flags_off()
    params["j_vwap_reclaim_fb_enabled"] = True
    params["j_vix_dayside_enabled"] = True
    assert (
        risk_gate.select_exit_params("BEARISH_REJECTION_RIDE_THE_RIBBON", "P", params, GLOBAL_STOP_SAFE)
        == GLOBAL_STOP_SAFE
    )


def test_matched_setup_but_its_own_flag_off_is_global() -> None:
    """The setup matches by name, but ITS flag is off -> global (the other setup's
    flag being on must not leak)."""
    params = _params_flags_off()
    params["j_vix_dayside_enabled"] = True   # only the OTHER setup is enabled
    assert (
        risk_gate.select_exit_params(RECLAIM_FB, "P", params, GLOBAL_STOP_BOLD)
        == GLOBAL_STOP_BOLD
    )


def test_resolver_is_pure_no_mutation() -> None:
    """Resolver must not mutate params (immutability / no side effects)."""
    params = _params_flags_off()
    params["j_vwap_reclaim_fb_enabled"] = True
    import copy
    before = copy.deepcopy(params)
    risk_gate.select_exit_params(RECLAIM_FB, "P", params, GLOBAL_STOP_SAFE)
    assert params == before
