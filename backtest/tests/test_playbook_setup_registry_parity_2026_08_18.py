"""Guard: markdown/0dte/playbook.md <-> code setup-name registry parity.

Closes RULE-ENGINE-ALIGNMENT-2026-08-18.md finding #2 (Rule 1, "No setup, no trade. Every
trade matches a named pattern in markdown/0dte/playbook.md", was only PARTIALLY enforced —
the code enforces "must match code's own named-setup registry", real and effective, but
nothing cross-validates that registry against playbook.md, so the two silently diverge).

VERIFIED DRIFT AT BUILD TIME (2026-08-18 re-verification — corrects the audit doc's own
GAP_AND_GO claim, see the fix's session report): the code's real, single-source-of-truth
setup registries are strategies.REGISTRY (automation/state/fleet/strategies.py, the 2 core
ribbon setups + the fleet strategy set) and setup_dispatch.KNOWN_SETUP_NAMES
(setup/scripts/setup_dispatch.py, the "extra setup" G4 dispatch roster — that module's OWN
declared "single source of truth for which extra setups exist"). Before this fix, 5 of the
7 KNOWN_SETUP_NAMES entries had ZERO playbook.md mention despite being real, wired,
dispatched-every-tick detectors: vwap_reclaim_failed_break (armed on core safe-2, real OPRA
fills), bollinger_squeeze (armed, real OPRA fills through 2026-08-11), vix_regime_dayside
(real fills 2026-07-20/21, since disarmed), double_bottom_base_quiet (armed, no confirmed
fill yet), level_break_first_strike (deliberately SHADOW-LOGGED, never armed). Separately,
GAP_AND_GO already had a playbook.md entry claiming "Status: LIVE" that was FALSE — the
detector is real and wired (contra the audit doc's "wired nowhere in code" claim, which this
fix's session independently falsified by reading setup_dispatch.py/heartbeat_core.py
directly) but 'gap_and_go' has NEVER appeared in extra_setup_exec_armed, so it has never
placed a real order; the corrected entry says so.

TWO DIRECTIONS, asymmetric on purpose:
  1. Every CODE-tradeable setup name must be named SOMEWHERE in playbook.md (a "###
     Setup name:" header). This is the durable, forward-looking half — RED the day a new
     detector is wired into either registry without a matching playbook.md entry.
  2. Every "### Setup name:" header in playbook.md (the doc's OWN convention for "this is a
     real pattern", distinct from the "### CANDIDATE --"/"### RETIRED --" headers used by
     the not-yet-tradable/retired sections) must either resolve to a code name, OR carry an
     explicit non-live marker in its own Status line (WATCH-ONLY / NOT IMPLEMENTED / etc.) —
     so a playbook entry can never silently claim LIVE for a setup with zero code backing
     the way the old GAP_AND_GO entry did.

Reproduce a violation locally: edit setup_dispatch.py's DISPATCH_ROSTER (add a row) or
strategies.py's REGISTRY without touching playbook.md, then re-run this file — it goes RED
immediately, naming exactly which setup is missing (this is the "found by hand a month
later" gap the audit asked to be closed).

Run:  cd backtest && .venv/Scripts/python.exe -m pytest tests/test_playbook_setup_registry_parity_2026_08_18.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAYBOOK = ROOT / "markdown" / "0dte" / "playbook.md"

_SETUP_SCRIPTS = str(ROOT / "setup" / "scripts")
_FLEET_STATE = str(ROOT / "automation" / "state" / "fleet")
for _p in (_SETUP_SCRIPTS, _FLEET_STATE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import setup_dispatch  # noqa: E402
import strategies as fleet_strategies  # noqa: E402

_HEADER_RE = re.compile(r"^### Setup name:\s*`?([A-Za-z0-9_]+)`?", re.MULTILINE)
_STATUS_RE = re.compile(r"\*\*Status:\*\*\s*(.+)")

# Vocabulary this doc already uses elsewhere (candidates section, STAIRSTEP_CONTINUATION's
# retirement) for "not currently a live, code-backed trade" — recognized here rather than
# forcing every non-live entry into one single literal string.
_NON_LIVE_MARKERS = (
    "NOT YET TRADABLE", "NOT IMPLEMENTED", "WATCH-ONLY", "WATCH ONLY", "RETIRED",
    "CANDIDATE", "OBSERVATION", "OBSERVED", "PAPER-ELIGIBLE", "DRAFT", "SHADOW-LOGGED",
)


def _code_setup_names() -> set[str]:
    """Every setup_name the live/paper path can actually dispatch, canonicalized upper.
    Union of setup_dispatch.KNOWN_SETUP_NAMES (the G4 extra-setup roster) and
    strategies.REGISTRY's entry_setups (covers the 2 core ribbon setups, which never go
    through setup_dispatch at all)."""
    names = {n.upper() for n in setup_dispatch.KNOWN_SETUP_NAMES}
    for strat in fleet_strategies.REGISTRY:
        for setup in strat.entry_setups:
            names.add(setup.upper())
    return names


def _playbook_text() -> str:
    assert PLAYBOOK.exists(), f"missing playbook: {PLAYBOOK}"
    return PLAYBOOK.read_text(encoding="utf-8")


def _playbook_named_setups() -> set[str]:
    return {m.group(1).upper() for m in _HEADER_RE.finditer(_playbook_text())}


def _playbook_sections() -> list[tuple[str, str]]:
    """[(NAME_UPPER, section_text)] for every '### Setup name:' header, section_text
    spanning from that header to the next header (or EOF) so each entry's OWN Status line
    is read, never a neighbor's."""
    text = _playbook_text()
    matches = list(_HEADER_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1).upper(), text[start:end]))
    return out


# --- direction 1: code -> playbook (the durable forward-looking half) --------------------
def test_every_code_tradeable_setup_is_named_in_playbook():
    code_names = _code_setup_names()
    playbook_names = _playbook_named_setups()
    missing = sorted(code_names - playbook_names)
    assert not missing, (
        "RULE 1 DRIFT: these code-dispatchable setup names have NO '### Setup name:' entry "
        f"in {PLAYBOOK}: {missing}. Add an entry (see the VWAP_RECLAIM_FAILED_BREAK / "
        "GAP_AND_GO entries for the expected shape: hypothesis, trigger, exit, detector "
        "path, TRUE current arm/evidence state) — or, if the setup is being retired from "
        "code, remove it from strategies.REGISTRY / setup_dispatch.DISPATCH_ROSTER in the "
        "SAME change.")


# --- direction 2: playbook -> code (every named live-section entry is accounted for) -----
def test_every_named_playbook_setup_is_wired_or_explicitly_marked():
    code_names = _code_setup_names()
    problems = []
    for name, section in _playbook_sections():
        status_match = _STATUS_RE.search(section)
        status = status_match.group(1) if status_match else ""
        wired = name in code_names
        marked = any(marker in status.upper() for marker in _NON_LIVE_MARKERS)
        if not wired and not marked:
            problems.append(name)
    assert not problems, (
        f"RULE 1 DRIFT: these playbook.md '### Setup name:' entries are not in the code "
        f"registry and carry no recognized non-live marker in their Status line: {problems}. "
        "Either wire the detector, or add an explicit WATCH-ONLY/NOT IMPLEMENTED marker + a "
        "dated explanation to the Status line.")


# --- sanity: the registry helpers themselves aren't silently empty (a passing-by-vacuity
#     guard is worse than no guard — this pins the premise the two tests above depend on) --
def test_registries_are_non_empty_sanity():
    assert len(_code_setup_names()) >= 8, (
        "code setup registry looks too small — did an import silently fail? Expect >= 8: "
        "2 core ribbon setups + setup_dispatch's 7-entry DISPATCH_ROSTER (union, some names "
        "overlap between the two sources).")
    assert len(_playbook_named_setups()) >= 8, (
        "playbook.md's '### Setup name:' header count looks too small post-fix — expected "
        "the original 4 (BEARISH_REJECTION/BULLISH_RECLAIM/VWAP_CONTINUATION/GAP_AND_GO) "
        "plus the 5 newly-documented setups (VWAP_RECLAIM_FAILED_BREAK, VIX_REGIME_DAYSIDE, "
        "DOUBLE_BOTTOM_BASE_QUIET, BOLLINGER_SQUEEZE, LEVEL_BREAK_FIRST_STRIKE).")


def test_known_setup_names_include_the_two_audit_findings():
    """Pins the two setups this fix's task explicitly named, so a future refactor of
    DISPATCH_ROSTER/REGISTRY can't silently drop the exact cases this guard was built for."""
    names = _code_setup_names()
    assert "VWAP_RECLAIM_FAILED_BREAK" in names
    assert "GAP_AND_GO" in names
