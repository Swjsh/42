"""Guard: an install-*.ps1 script's trigger time must match the registry's documented ET time.

THE REGRESSION THIS PINS (2026-09-03, commit dceb125e, the evening self-heal sweep).
On 2026-08-26, three LIVE scheduled tasks (Gamma_OosCheck, Gamma_GateRecency,
Gamma_FreeModelAudit) were re-timed directly against Task Scheduler (Set-ScheduledTaskTrigger
or the UI) out of quiet_mode.py's 16:00-23:00 ET blackout and into the 23:00-08:00 ET LOUD
maintenance band -- but their DECLARATIVE install-*.ps1 sources (setup/install-oos-check.ps1,
setup/scripts/install-gate-recency.ps1, setup/scripts/install-free-model-audit.ps1) kept the
OLD hardcoded -At time. Nothing failed loudly: the scripts ran fine, registered a task, and
printed "OK". Then the 2026-09-03 evening self-heal sweep re-ran those exact three installers
(to add a PT15M/PT30M repetition window) and they silently dragged the live trigger back into
the blackout -- caught only by tests/test_quiet_mode_starvation.py, a BEHAVIOURAL guard that
enumerates live Task Scheduler state, not a STATIC one that reads the declarative source.

THE GAP: nothing checked the install script's own hardcoded time against what
automation/state/SCHEDULED-TASKS.md documents as the live truth. An installer can drift from
the registry indefinitely and nobody notices until it is next re-run. This test closes that
gap the same way tests/test_install_script_relay_wiring_drift.py closes the analogous
relay-wiring gap: pure static text parsing of the install-*.ps1 source, no live Task Scheduler
query, so it runs anywhere, fast, deterministically.

METHOD: for every setup/install-*.ps1 and setup/scripts/install-*.ps1 file, best-effort parse
    1. the Gamma_* task name it registers ($taskName / $TaskName / $newTask literal assignment),
    2. the LOCAL (Mountain) time its primary -Daily/-Weekly trigger fires at (a literal
       -At "HH:MM", or -- for the handful of scripts that compute it dynamically from a
       hardcoded ET base via [DateTime]::Today.AddHours(H).AddMinutes(M) then convert with
       TimeZoneInfo -- the same ET target, resolved without the conversion step since it's
       already expressed in ET),
and compare the resulting ET time (local + 2h, mirroring the CLAUDE.md Ohio->Colorado rule:
this box runs Mountain, ET = local + 2h) against the FIRST unambiguous "HH:MM ET" (or
"HH:MM local") token in that task's SCHEDULED-TASKS.md row's schedule column.

A script/row pair is SKIPPED (never asserted on) rather than guessed at when:
  - no task-name literal is found (batch/shared installers, e.g. install-tasks.ps1,
    install-daily-brief.ps1 which registers two tasks from one shared function),
  - no single -Daily/-Weekly -At literal is found (interval-only, logon/boot/event triggers,
    or a script with no scheduled-task registration at all, e.g. install-git-hooks.ps1),
  - the -At value is a variable this parser cannot resolve to a fixed clock time (most of
    these compute the time from et_clock.py or a CLI arg at install time, not a hardcoded
    constant -- correct by construction, nothing to compare against a fixed registry value),
  - the task has no row in SCHEDULED-TASKS.md, or its row's schedule column has no single
    unambiguous "HH:MM ET"/"HH:MM local" token (an interval-repeating task like "every 10 min,
    09:00-16:00 ET", or a multi-fire-per-day task like "08:35/09:30/12:00/15:50 ET" -- neither
    is comparable to a single -At value).
Coverage as of this guard's authoring: 46 of 130 install scripts parsed to a comparable
(task, script-ET, registry-ET) triple; 84 skipped for one of the reasons above (a live count
is asserted below as a floor, not a ceiling -- new install scripts only grow the parseable set
over time, they never shrink it without a corresponding remove-a-task action).

KNOWN PRE-EXISTING MISMATCHES (found as a byproduct of writing this guard, 2026-09-03,
OUT OF SCOPE for the dceb125e regression fix this guard was built for -- filed as a follow-up
task rather than fixed inline, per this session's scope boundary of touching only
Gamma_OosCheck / Gamma_GateRecency / Gamma_FreeModelAudit): nine install scripts whose
hardcoded -At literal, converted local-to-ET, does NOT match their task's SCHEDULED-TASKS.md
row -- verified via Export-ScheduledTask that in every one of the nine, the LIVE task is
currently registered at the value the REGISTRY documents (i.e. these are not live-starved
today), so the drift is dormant: it only bites the next time someone re-runs that specific
installer, exactly the mechanism that caused the dceb125e regression. Two of the nine
(Gamma_DressRehearsal, Gamma_FuturesBrokerProbe) are additional instances of the SAME
2026-08-26 quiet-mode re-time class the dceb125e fix addressed; the other seven
(Gamma_AnalystEodReview, Gamma_ArchiveKeyLevels, Gamma_CryptoDaily, Gamma_ManagerDailyVerify,
Gamma_GymSession, Gamma_ScoutPremarket, Gamma_TreasurerWeekly) look like an older, unrelated
"ET value used as the -At local argument without the +2h/-2h conversion" bug. This allowlist
exists so the guard can still catch any NEW drift among the other 37 currently-consistent
pairs without blocking on debt this fix was not scoped to touch. Removing an entry here
requires the corresponding installer to actually be fixed and re-verified -- the guard below
re-asserts that every allowlisted pair is STILL mismatched, so a silent fix that forgets to
prune the allowlist is itself caught.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "setup"
REGISTRY = ROOT / "automation" / "state" / "SCHEDULED-TASKS.md"

_TASKNAME_RE = re.compile(r'\$(?:taskName|TaskName|newTask)\s*=\s*"(Gamma_[A-Za-z0-9_]+)"')
_AT_DAILY_RE = re.compile(r'-Daily\s+-At\s+"(\d{1,2}:\d{2})"')
_AT_WEEKLY_RE = re.compile(r'-Weekly[^\n]*-At\s+"(\d{1,2}:\d{2})"')
_AT_VAR_RE = re.compile(r'-Daily\s+-At\s+\$(\w+)')
_DYNAMIC_ET_BASE_RE = re.compile(r'AddHours\((\d+)\)\.AddMinutes\((\d+)\)')

_ROW_RE = re.compile(r"^\|\s*`(Gamma_[A-Za-z0-9_]+)`\s*\|(.*)$", re.MULTILINE)
_ET_RE = re.compile(r"(?<![-–\d:])(\d{1,2}):(\d{2})\s*ET")
_LOCAL_RE = re.compile(r"(?<![-–\d:])(\d{1,2}):(\d{2})\s*local")

# See "KNOWN PRE-EXISTING MISMATCHES" in the module docstring. (task_name, script_relpath).
# All 9 entries cleared 2026-09-03 (queue.md INSTALL-SCRIPT-TIME-DRIFT-DORMANT-9): each
# installer's -At literal re-timed to match its SCHEDULED-TASKS.md registry ET value
# (verified via Export-ScheduledTask that the live trigger already equalled the registry
# in all 9 cases -- the drift was installer-only and dormant). Allowlist intentionally
# left empty rather than deleted so the next drift has a documented place to land.
KNOWN_PREEXISTING_MISMATCHES: dict[str, str] = {}


def _registry_rows() -> dict[str, str]:
    text = REGISTRY.read_text(encoding="utf-8", errors="replace")
    rows: dict[str, str] = {}
    for m in _ROW_RE.finditer(text):
        name, rest = m.group(1), m.group(2)
        if name not in rows:  # first table row wins (Active table precedes any appendix)
            rows[name] = rest
    return rows


def _registry_et(row: str) -> tuple[int, int] | None:
    schedule = row.split("|")[0] if "|" in row else row
    if re.search(r"\bevery\b", schedule, re.IGNORECASE):
        return None  # interval-repeating, not a single fire time
    if re.search(r"\d{1,2}:\d{2}\s*/\s*\d{1,2}:\d{2}", schedule):
        return None  # multiple fires/day, not comparable to a single -At
    m = _ET_RE.search(schedule)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _LOCAL_RE.search(schedule)
    if m:
        return (int(m.group(1)) + 2) % 24, int(m.group(2))
    return None


def _script_et(text: str) -> tuple[int, int] | None:
    """The script's primary trigger time, expressed as an ET (hour, minute) pair."""
    m = _AT_DAILY_RE.search(text) or _AT_WEEKLY_RE.search(text)
    if m:
        h, mm = map(int, m.group(1).split(":"))
        return (h + 2) % 24, mm  # local (Mountain) -> ET
    if _AT_VAR_RE.search(text):
        dh = _DYNAMIC_ET_BASE_RE.search(text)
        if dh:
            return int(dh.group(1)), int(dh.group(2))  # already an ET base, no conversion
    return None


def _install_scripts() -> list[Path]:
    return sorted(SETUP.glob("install-*.ps1")) + sorted((SETUP / "scripts").glob("install-*.ps1"))


def _collect() -> tuple[list[tuple[str, Path, tuple[int, int], tuple[int, int]]], int]:
    """Returns (comparable triples for MATCHING pairs is not filtered here -- caller does
    that), skipped_count)."""
    rows = _registry_rows()
    comparable: list[tuple[str, Path, tuple[int, int], tuple[int, int]]] = []
    skipped = 0
    for script in _install_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        tm = _TASKNAME_RE.search(text)
        if not tm:
            skipped += 1
            continue
        task = tm.group(1)
        script_et = _script_et(text)
        if script_et is None:
            skipped += 1
            continue
        row = rows.get(task)
        if row is None:
            skipped += 1
            continue
        reg_et = _registry_et(row)
        if reg_et is None:
            skipped += 1
            continue
        comparable.append((task, script, script_et, reg_et))
    return comparable, skipped


def test_install_script_times_match_registry_outside_known_debt():
    comparable, skipped = _collect()

    # Coverage floor -- protects against a silent regex/glob break collapsing this guard to
    # a vacuous pass (the "notests reports success" anti-pattern this repo explicitly guards
    # against elsewhere, e.g. Gamma_GuardsFull's own row).
    assert len(comparable) >= 30, (
        f"only {len(comparable)} install-script/registry pairs were parseable -- expected "
        f">=30 (was 46 when this guard was authored). Either install scripts were deleted/"
        f"renamed in bulk, or a parsing regex broke silently."
    )

    new_mismatches = []
    still_allowlisted = set()
    for task, script, script_et, reg_et in comparable:
        if script_et == reg_et:
            continue
        rel = script.relative_to(SETUP).as_posix()
        if KNOWN_PREEXISTING_MISMATCHES.get(task) == rel:
            still_allowlisted.add(task)
            continue
        new_mismatches.append(
            f"  {task:30s} {rel:45s} script says ET {script_et[0]:02d}:{script_et[1]:02d}, "
            f"registry says ET {reg_et[0]:02d}:{reg_et[1]:02d}"
        )

    assert not new_mismatches, (
        "These install scripts' hardcoded trigger time disagrees with "
        "SCHEDULED-TASKS.md's documented ET time -- re-running the installer would silently "
        "drag the live task back to the wrong time (the exact dceb125e regression class):\n"
        + "\n".join(new_mismatches)
        + "\n\nFix by re-timing the installer's -At value to match the registry's documented "
          "ET time (local = ET - 2h on this Mountain-time box), or update "
          "SCHEDULED-TASKS.md if the registry row is what's actually stale."
    )

    # Allowlist-rot check: an entry that stops reproducing means someone fixed the installer
    # (or renamed/deleted it) without pruning KNOWN_PREEXISTING_MISMATCHES -- surface that so
    # the allowlist never silently outlives the bug it documents.
    stale_allowlist_entries = sorted(set(KNOWN_PREEXISTING_MISMATCHES) - still_allowlisted)
    assert not stale_allowlist_entries, (
        "These KNOWN_PREEXISTING_MISMATCHES entries no longer reproduce a mismatch (the "
        "installer was fixed, or the task/script pair changed) -- remove them from the "
        "allowlist in this test file:\n  " + "\n  ".join(stale_allowlist_entries)
    )
