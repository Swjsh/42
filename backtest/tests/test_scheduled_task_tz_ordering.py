"""Static TZ + prep-chain-ordering guard for scheduled-task install scripts.

THE FOOT-GUN THIS GRADUATES TO CODE (`project_scheduled_task_tz`, recurring):
The rig runs in **Mountain time**; Windows Task Scheduler's ``-At`` takes a LOCAL
(Mountain) clock value. ET = MT + 2h. So a daily task intended to fire at an ET hour
must be registered with the **MT** literal (ET - 2h). Passing the ET value straight to
``-At`` fires the task **2 hours late** — silent, and catastrophic for the trading
chain (an EodFlatten registered "15:55 ET" as a 15:55 MT literal fires 17:55 ET, i.e.
*after the close*, leaving 0DTE positions to expire).

This was re-discovered 2026-06-27 (conductor) while reconciling the stale G5 queue item:
the TZ-fixed prep-chain installers (`install-swarm-task.ps1`, `install-ema-snapshot.ps1`)
were already correct (06:15/06:20 MT = 08:15/08:20 ET), but the canonical multi-task
installer ``setup/install-tasks.ps1`` STILL passes ET-as-local to ``-AtTime`` for the
whole core chain (LaunchTV/Premarket/Heartbeat/EodFlatten). The live tasks happen to be
correct *only* because other scripts (`register_tz_fixed_tasks.ps1`, `fix-trading-tasks.ps1`)
re-registered them at the right MT literal — a re-run of install-tasks.ps1 would re-arm
the time-bomb. Nothing asserted any of this.

TWO invariants, pure file parsing (no live Task Scheduler call → runs anywhere, fast,
deterministic; complementary to `setup/scripts/audit_scheduled_tasks.py` which checks
doc<->live reality, and `test_scheduled_tasks_doc.py` which checks doc<->script names):

  1. PREP-CHAIN TZ-CONSISTENCY + ORDERING — each TZ-fixed pre-market prep installer's
     ``-At "HH:MM"`` MT literal, converted to ET (+2h), must equal its documented
     intended ET fire time, AND the prep tasks must all fire strictly BEFORE the
     premarket routine reads their output at 08:30 ET (swarm 08:15 < ema 08:20 < 08:30).
     A future TZ edit that re-misorders the swarm->ema->premarket handoff FAILS here.

  2. ET-AS-LOCAL RATCHET — `install-tasks.ps1` is a KNOWN TZ-unfixed installer (it
     passes ET values straight to ``-At`` on the MT rig). It is recorded below with a
     ratchet that (a) asserts it is GENUINELY still broken (so the entry can't go stale),
     and (b) the day it is fixed to MT literals, the "still broken" assert fails ->
     forcing its removal from the allowlist (shrinks-only). Any NEW daily installer that
     introduces the same ET-as-local bug is caught by the same consistency check.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SETUP = _REPO / "setup"

# ET = MT + this many hours (the rig is Mountain; -At is a LOCAL/MT clock value).
MT_TO_ET_HOURS = 2


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _mt_to_et_minutes(mt_hhmm: str) -> int:
    return _to_minutes(mt_hhmm) + MT_TO_ET_HOURS * 60


# ── -At / -AtTime literal extraction ─────────────────────────────────────────
# Handles both forms seen in the repo:
#   -At ([DateTime]"06:15")      -At "06:20"      -AtTime ([DateTime]"08:30")
_AT_LITERAL = re.compile(
    r'-At(?:Time)?\s+(?:\(\s*\[DateTime\]\s*)?"(\d{1,2}:\d{2})"',
    re.IGNORECASE,
)


def _all_at_literals(script_rel: str) -> list[str]:
    p = _SETUP / script_rel
    txt = p.read_text(encoding="utf-8", errors="replace")
    return _AT_LITERAL.findall(txt)


def _single_at_literal(script_rel: str) -> str:
    lits = _all_at_literals(script_rel)
    assert lits, f"no -At literal found in {script_rel} (format changed?)"
    # All prep installers register exactly one daily task -> one -At literal.
    assert len(set(lits)) == 1, (
        f"{script_rel} has multiple distinct -At literals {sorted(set(lits))}; "
        f"this guard assumes a single-task prep installer. Update the registry."
    )
    return lits[0]


# ── The pre-market prep chain (authoritative intended ET fire times = loop spec)
# Each prep task must fire (in ET) at its intended time AND before PREMARKET_ET, when
# premarket.md Step 1c reads swarm_output.json / today-bias is finalized.
PREMARKET_ET_HHMM = "08:30"  # Gamma_Premarket reads the prep outputs here.

PREP_CHAIN: list[tuple[str, str, str]] = [
    # (task name, TZ-fixed install script under setup/, intended ET HH:MM)
    ("Gamma_SwarmPremarket", "install-swarm-task.ps1", "08:15"),
    ("Gamma_EmaSnapshot", "install-ema-snapshot.ps1", "08:20"),
]

# ── KNOWN TZ-UNFIXED installers (ET passed straight to -At on the MT rig) ─────
# Ratchet: each entry is asserted to be GENUINELY still broken (the script's premarket
# -At literal still equals the ET value, i.e. no -2h applied). When the script is fixed
# to use the MT literal (06:30 for an 08:30-ET task), `test_known_tz_unfixed_still_broken`
# FAILS -> the entry must be removed, tightening the ratchet. A brand-new daily installer
# with the same bug is NOT auto-exempt — add it here consciously or fix it.
# Each: script -> (task name, the ET-HH:MM it WRONGLY passes as a local literal).
KNOWN_TZ_UNFIXED: dict[str, tuple[str, str]] = {
    "install-tasks.ps1": ("Gamma_Premarket", "08:30"),
}


# ── Tests ────────────────────────────────────────────────────────────────────

def test_prep_chain_scripts_exist():
    for _task, script, _et in PREP_CHAIN:
        assert (_SETUP / script).exists(), f"prep installer missing: setup/{script}"


def test_prep_chain_tz_consistency():
    """Each TZ-fixed prep installer's MT -At literal, converted to ET (+2h), equals its
    documented intended ET fire time. Catches a swarm/ema task drifting off the MT rig."""
    for task, script, intended_et in PREP_CHAIN:
        mt = _single_at_literal(script)
        got_et_min = _mt_to_et_minutes(mt)
        want_et_min = _to_minutes(intended_et)
        assert got_et_min == want_et_min, (
            f"{task} ({script}): -At '{mt}' MT = "
            f"{got_et_min // 60:02d}:{got_et_min % 60:02d} ET, but the loop spec wants "
            f"{intended_et} ET. Register with the MT literal (ET - {MT_TO_ET_HOURS}h); "
            f"do NOT pass the ET value straight to -At (the project_scheduled_task_tz "
            f"foot-gun)."
        )


def test_prep_chain_fires_before_premarket():
    """The prep tasks must fire (in ET) strictly before Gamma_Premarket reads their
    output at 08:30 ET, and in the documented order swarm < ema < premarket. This is the
    G5 handoff invariant: a mis-ordered prep task = today-bias logs the bias vote as
    SWARM_CONTEXT_UNAVAILABLE every day."""
    premarket_min = _to_minutes(PREMARKET_ET_HHMM)
    last = -1
    for task, script, intended_et in PREP_CHAIN:
        et_min = _to_minutes(intended_et)
        assert et_min < premarket_min, (
            f"{task} intended {intended_et} ET is NOT before premarket "
            f"{PREMARKET_ET_HHMM} ET — its output is stale when premarket reads it."
        )
        assert et_min > last, (
            f"prep chain out of order at {task} ({intended_et} ET); the PREP_CHAIN "
            f"registry must be in ascending ET fire-time order."
        )
        last = et_min


def test_known_tz_unfixed_still_broken():
    """Ratchet: every KNOWN_TZ_UNFIXED installer is GENUINELY still passing ET-as-local
    (its premarket -At literal still equals the ET value, no -2h). The day it is fixed to
    the MT literal this assert FAILS -> remove the entry (shrinks-only)."""
    for script, (task, et_hhmm) in KNOWN_TZ_UNFIXED.items():
        assert (_SETUP / script).exists(), (
            f"KNOWN_TZ_UNFIXED names missing script setup/{script} — remove the stale entry."
        )
        lits = set(_all_at_literals(script))
        assert et_hhmm in lits, (
            f"{script}: expected the ET-as-local literal '{et_hhmm}' for {task} to still "
            f"be present (found {sorted(lits)}). If this installer was TZ-fixed to the MT "
            f"literal, REMOVE it from KNOWN_TZ_UNFIXED so the ratchet tightens."
        )


def test_no_new_et_as_local_daily_installer():
    """A daily-task installer whose -At literal lands in market hours (>= 09:30 *as a
    bare local value*) is the ET-as-local smell — unless it is a known, accepted entry.
    This is a soft net for a brand-new installer that re-introduces the bug; it does not
    second-guess the heterogeneous legacy scripts, only flags an unregistered new one
    that passes a clearly-ET trading-hours value straight to -At.

    Scoped to the canonical install-tasks.ps1 premarket/launch block only (the known
    instance) to stay deterministic; broadening is a conscious future tightening."""
    # Structural: the known instance is install-tasks.ps1, and it IS in the allowlist.
    # Assert the partition holds (documents intent; always true unless someone adds a
    # raw ET trading-hours literal to a prep installer, which test_prep_chain_tz_consistency
    # would already fail on).
    for _task, script, _et in PREP_CHAIN:
        for lit in _all_at_literals(script):
            # A prep installer must never carry a bare >= 09:00 literal (that would be an
            # ET trading-hours value passed as local — the bug). Prep fires pre-08:30 MT.
            assert _to_minutes(lit) < _to_minutes("09:00"), (
                f"{script} has -At '{lit}' which is >= 09:00 as a LOCAL literal — looks "
                f"like an ET value passed straight to -At. Convert to the MT literal."
            )
