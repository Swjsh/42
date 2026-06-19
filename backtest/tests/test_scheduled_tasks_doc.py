"""Static consistency test for the scheduled-task registry doc (Phase 0b — 2026-06-18).

THE BUG THIS GUARDS — registry doc drift. ``automation/state/SCHEDULED-TASKS.md`` is
the single source of truth for ``Gamma_*`` scheduled tasks, but it is hand-maintained
and has *self-reported* drift before (its own header: "Registry had drifted to claim
35 active vs 15 real"). Two failure modes this catches WITHOUT touching live Task
Scheduler (so it runs anywhere, fast, deterministic):

  1. UNDOCUMENTED TASK — an install script (``setup/**/*.ps1`` calling
     ``Register-ScheduledTask``) registers a ``Gamma_*`` task that appears NOWHERE in
     the doc (not Active, Reference, Proposed, or Disabled). That task can be installed
     on the box yet be invisible to the registry → the orphan class. → FAIL.

  2. STATED-COUNT DRIFT — the ``## Active`` section header states a registered count
     ("NN registered: ...") that disagrees with the number of task ROWS in the Active
     table. The count is the human-readable summary everyone trusts; if it lies, the
     audit narrative is wrong. → FAIL.

TOLERANCE (by design, per the audit's own governance model):
  * A task DOCUMENTED in the registry (anywhere) but with NO install script is allowed
    — it may be created manually (e.g. the Gamma_Futures* tasks are registered by hand;
    the doc says so). Reported as an informational warning, never a failure.
  * Install scripts for deliberately-removed / never-activated tasks (session-guard,
    sweep, chart-vision, etc.) are fine AS LONG AS the task name appears somewhere in
    the doc (the Reference / removed sections count as "documented"). Only a name that
    appears in NO section is a real drift.
  * One-shot / legacy registration scripts that aren't part of the task registry live
    on an explicit allowlist below.

Pure file parsing. Does NOT call ``Get-ScheduledTask`` — this is a doc↔script static
check, complementary to ``setup/scripts/audit_scheduled_tasks.py`` (which checks
doc↔live-reality and runs daily on the box).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]          # repo root
_REGISTRY = _REPO / "automation" / "state" / "SCHEDULED-TASKS.md"
_SETUP = _REPO / "setup"


# ── Allowlist: install scripts NOT part of the production task registry ───────
#
# A ``Gamma_*`` name registered by a script that is intentionally outside the
# SCHEDULED-TASKS.md governance (one-shot setup helpers, legacy session scripts).
# Each entry: task name -> reason. These are exempt from the "must be documented"
# rule. Keep this list SHORT and justified — the whole point is that new real tasks
# are NOT silently exempt.
ALLOWLIST_UNDOCUMENTED: dict[str, str] = {
    # setup-all.ps1 is the one-shot "run every action-item from the 2026-06-14
    # deep-review" bootstrap, not a production task installer; the freshness
    # watchdog it wires is a legacy helper that predates the current registry and
    # is not part of the 'Active' governance set.
    "Gamma_FreshnessWatchdog": "registered by one-shot setup-all.ps1 bootstrap, not a registry task",
}

# KNOWN DRIFT — REAL findings this test surfaced on 2026-06-18 (Phase 0b). Each was a
# live-capable install script (its run-*.ps1 exists) for a task documented NOWHERE in
# SCHEDULED-TASKS.md. Recorded here so: (a) the suite stayed green for unrelated work,
# (b) the drift was a durable visible record at the point of detection, and (c) the
# ratchet still FAILS for any NEW undocumented task. Resolution is out of this test's
# scope (it owns test files only; the registry doc is read-only here) — fixing the doc
# deletes the entry (the test's `fixed_drift` assertion enforces that removal).
#
# RESOLVED: Gamma_SpendSummary was added to SCHEDULED-TASKS.md "## Active" (it is
# registered + live — no audit flag). Gamma_LevelAlertDaemon was instead RETIRED
# 2026-06-19: the live audit flagged it STALE_REGISTRY_ENTRY (doc said Active but it was
# never registered), it never ran (no logs/output), had no consumer of its live-alerts
# output, and its pwsh-based installer was broken on a PS-5.1 box. It is now documented
# in the Reference "removed" section and its install/runner were archived to
# setup/scripts/_archive/ (still under setup/, so the registration scan still sees the
# name → it MUST, and does, stay documented). With both names documented, this dict is
# empty and the ratchet is back to full tightness — a brand-new undocumented Gamma_*
# task FAILS test_every_installed_task_is_documented.
KNOWN_DRIFT_UNDOCUMENTED: dict[str, str] = {}


# ── Registry parsing (mirrors audit_scheduled_tasks.py for the Active set) ────

def _registry_text() -> str:
    return _REGISTRY.read_text(encoding="utf-8")


def _parse_section_tasks(text: str) -> dict[str, set[str]]:
    """Map each ``## `` section heading -> set of ``Gamma_*`` task names in its table
    rows. A task is attributed to a section when it appears as the first backtick-quoted
    cell of a table row (``| `Gamma_X` | ...``) under that heading."""
    sections: dict[str, set[str]] = {}
    current = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            current = s[3:].strip()
            sections.setdefault(current, set())
            continue
        if current is not None:
            m = re.match(r"^\|\s*`(Gamma_[A-Za-z0-9_]+)`", s)
            if m:
                sections[current].add(m.group(1))
    return sections


def _all_documented_names(text: str) -> set[str]:
    """Every ``Gamma_*`` token anywhere in the doc — Active rows, Reference bullets,
    Proposed rows, prose mentions. This is the permissive "is it documented AT ALL"
    set used for the undocumented-task check (a task named in the removed/Reference
    section IS documented — it is a deliberate, recorded decision)."""
    return set(re.findall(r"Gamma_[A-Za-z0-9_]+", text))


def _active_table_names(text: str) -> set[str]:
    return _parse_section_tasks(text).get("Active tasks (current production)", set())


def _stated_active_count(text: str) -> int | None:
    """The ``NN registered:`` integer in the Active section's summary line.

    e.g. "35 registered: 8 trading + 1 health-beacon + ...". Returns None if absent.
    """
    in_active = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_active = s.startswith("## Active")
            continue
        if in_active:
            m = re.match(r"^(\d+)\s+registered\b", s)
            if m:
                return int(m.group(1))
    return None


# ── Install-script parsing ───────────────────────────────────────────────────

def _registration_scripts() -> list[Path]:
    """Every ``.ps1`` under setup/ that calls ``Register-ScheduledTask`` — the full
    registration surface (``setup/install-*.ps1`` plus ``setup/scripts/register-*.ps1``
    and friends). Scanning by behavior (does it register?) is more robust than by
    filename glob."""
    out: list[Path] = []
    for p in _SETUP.rglob("*.ps1"):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Register-ScheduledTask" in txt:
            out.append(p)
    return sorted(out)


def _gamma_names_in_script(text: str) -> set[str]:
    """Every literal ``Gamma_*`` task name a script registers.

    Single-task installers bind ``$taskName = "Gamma_X"``; multi-task installers
    (install-tasks.ps1, install-kitchen.ps1) pass ``-Name "Gamma_X"`` per call. Both
    surface as a double- or single-quoted ``Gamma_*`` string literal, so we collect all
    such literals in any script that registers tasks. (Over-collecting a name that also
    appears in a comment is harmless — the doc check only cares that registered names
    are documented; an extra documented name is fine.)

    GLOB GUARD: a ``Gamma_*`` token immediately followed by ``*`` (e.g.
    ``Get-ScheduledTask -TaskName 'Gamma_Kitchen*'`` in a verify-hint line) is a
    wildcard fragment, NOT a real task name — excluded so it is not mistaken for an
    undocumented task.
    """
    names: set[str] = set()
    for m in re.finditer(r'(Gamma_[A-Za-z0-9_]+)', text):
        rest = text[m.end():]
        if rest[:1] == "*":
            continue  # glob fragment like 'Gamma_Kitchen*'
        names.add(m.group(1))
    return names


def _registered_name_to_scripts() -> dict[str, set[str]]:
    """task name -> set of script paths (relative) that register it."""
    mapping: dict[str, set[str]] = {}
    for p in _registration_scripts():
        txt = p.read_text(encoding="utf-8", errors="replace")
        for name in _gamma_names_in_script(txt):
            mapping.setdefault(name, set()).add(str(p.relative_to(_REPO)))
    return mapping


# ── Tests ────────────────────────────────────────────────────────────────────

def test_registry_doc_exists():
    assert _REGISTRY.exists(), f"registry doc missing: {_REGISTRY}"


def test_every_installed_task_is_documented():
    """No UNDOCUMENTED TASK: every Gamma_* a setup script registers appears somewhere
    in SCHEDULED-TASKS.md (Active / Reference / Proposed / Disabled), or is allowlisted."""
    text = _registry_text()
    documented = _all_documented_names(text)
    registered = _registered_name_to_scripts()
    allow = set(ALLOWLIST_UNDOCUMENTED)
    known_drift = set(KNOWN_DRIFT_UNDOCUMENTED)

    # Guard against stale exemptions (a name exempted but no longer registered, OR
    # a known-drift item that has since been documented — which means it is fixed and
    # must be removed from KNOWN_DRIFT so the ratchet tightens again).
    stale_allow = allow - set(registered)
    assert not stale_allow, (
        f"ALLOWLIST_UNDOCUMENTED names task(s) no longer registered by any script: "
        f"{sorted(stale_allow)} — remove them from the allowlist."
    )
    stale_drift = known_drift - set(registered)
    assert not stale_drift, (
        f"KNOWN_DRIFT_UNDOCUMENTED names task(s) no longer registered: {sorted(stale_drift)}"
    )
    fixed_drift = known_drift & documented
    assert not fixed_drift, (
        f"KNOWN_DRIFT_UNDOCUMENTED task(s) are now documented in {_REGISTRY.name}: "
        f"{sorted(fixed_drift)} — drift is FIXED, remove them from KNOWN_DRIFT_UNDOCUMENTED "
        f"so the test re-tightens."
    )

    # Surface the accepted known-drift for visibility (non-fatal).
    accepted = sorted(known_drift - documented)
    if accepted:
        print("KNOWN DOC DRIFT (accepted, pre-existing): " + ", ".join(accepted))

    undocumented = {
        name: sorted(scripts)
        for name, scripts in registered.items()
        if name not in documented and name not in allow and name not in known_drift
    }
    assert not undocumented, (
        "install script(s) register Gamma_* task(s) NOT documented anywhere in "
        f"{_REGISTRY.name}:\n"
        + "\n".join(f"  {n}  (registered by {', '.join(s)})" for n, s in sorted(undocumented.items()))
        + "\nAdd each to the registry (Active/Reference/Proposed) or, if it is a "
          "non-registry one-shot, to ALLOWLIST_UNDOCUMENTED with a reason."
    )


def test_active_stated_count_matches_table():
    """No STATED-COUNT DRIFT: the Active section's 'NN registered:' summary equals the
    number of task rows in the Active table."""
    text = _registry_text()
    stated = _stated_active_count(text)
    actual = len(_active_table_names(text))
    assert stated is not None, (
        "could not find an 'NN registered:' summary line in the ## Active section — "
        "the doc format changed; update this test or restore the count line."
    )
    assert stated == actual, (
        f"Active task count drift: header says '{stated} registered' but the Active "
        f"table has {actual} Gamma_* rows. Reconcile the summary line with the table "
        f"(this is exactly the '35 active vs 15 real' self-reported drift class)."
    )


def test_documented_active_tasks_without_install_script_are_only_warned(capsys):
    """TOLERANCE: an Active task with NO install script is allowed (may be created
    manually — e.g. Gamma_Futures*). We never FAIL here; we surface them as an
    informational warning so the gap is visible without blocking CI."""
    text = _registry_text()
    active = _active_table_names(text)
    registered = set(_registered_name_to_scripts())
    manual_only = sorted(active - registered)

    # Informational only — printed for visibility, asserted non-fatally.
    if manual_only:
        print(
            "INFO: Active tasks with no setup/ install script (manual registration "
            "assumed): " + ", ".join(manual_only)
        )
    # The invariant we DO enforce: the warned set is exactly "documented-but-no-script",
    # never "script-but-not-documented" (that is the failing test above). This assertion
    # is structural and always true — it documents intent and guards the partition.
    assert manual_only == sorted(active - registered)


def test_parsing_sanity_floor():
    """Floors so a broken regex can't silently pass everything: the Active table and the
    registration-script scan must both find a non-trivial number of tasks."""
    text = _registry_text()
    assert len(_active_table_names(text)) >= 20, "Active table parse looks empty/broken"
    assert len(_registered_name_to_scripts()) >= 15, "install-script scan looks empty/broken"
