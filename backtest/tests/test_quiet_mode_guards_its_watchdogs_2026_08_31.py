"""Guard: if a task is ESSENTIAL, its watchdog must be ESSENTIAL too.

SCAR (2026-08-31). `Gamma_MarketKeepAwake` was already in quiet_mode's ESSENTIAL set, so
the blackout correctly left the keepawake daemon running. But when its watchdog
(`Gamma_MarketKeepAwakeKeepalive`) was registered that evening, quiet mode immediately
disabled it -- leaving the guarded daemon alive and the ONLY thing that would notice it die
switched off. Dying silently mid-session is exactly this daemon's failure mode (09:23 ET
that day, 99 ticks in, empty stderr, nothing restarted it).

Clock bands do not close the hole on their own: the presence gate can hold quiet active
past the 23:00 ET maintenance boundary, and the daemon's watchdog first fires at 07:47 ET
-- before the 08:00 ET point where a presence hold is forbidden from reaching.

The rule this pins is general, not a one-off allowlist entry: a watchdog is exactly as
essential as the thing it watches, or the blackout silently reintroduces the failure the
watchdog exists to catch.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

qm = importlib.import_module("quiet_mode")

# Watchdog task -> the task it guards. Extend this when a new watchdog is registered.
WATCHDOG_OF = {
    "Gamma_MarketKeepAwakeKeepalive": "Gamma_MarketKeepAwake",
    "Gamma_WindowLeakDetectorKeepalive": None,   # guards a daemon, not a scheduled task
}


@pytest.mark.parametrize("watchdog,guarded", sorted(WATCHDOG_OF.items()))
def test_watchdog_is_essential_whenever_its_target_is(watchdog, guarded):
    if guarded is not None and guarded not in qm.ESSENTIAL:
        pytest.skip(f"{guarded} is not ESSENTIAL; its watchdog need not be either")
    assert watchdog in qm.ESSENTIAL, (
        f"{watchdog} guards {guarded or 'a live daemon'} but quiet mode would DISABLE it. "
        "A watchdog held down while its target keeps running is a watchdog with a hole -- "
        "the blackout silently reintroduces the exact failure the watchdog exists to catch."
    )


def test_keepawake_pair_are_both_essential():
    """The specific 2026-08-31 scar, pinned by name."""
    assert "Gamma_MarketKeepAwake" in qm.ESSENTIAL
    assert "Gamma_MarketKeepAwakeKeepalive" in qm.ESSENTIAL


def test_quiet_mode_itself_stays_essential():
    """Without this, quiet mode could disable itself and never restore anything."""
    assert "Gamma_QuietMode" in qm.ESSENTIAL


def test_full_trading_chain_survives_the_blackout():
    """A market day must never be lost to quiet mode."""
    for name in ("Gamma_HeartbeatCore", "Gamma_SightBeacon", "Gamma_Premarket",
                 "Gamma_LaunchTV", "Gamma_TvWatchdog", "Gamma_EodFlatten",
                 "Gamma_EodFlattenCore", "Gamma_EodFlatten_Aggressive"):
        assert name in qm.ESSENTIAL, f"{name} would be disabled during a blackout"
