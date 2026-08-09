"""audit_scheduled_tasks — verify registered tasks vs SCHEDULED-TASKS.md registry.

Runs daily via Gamma_CryptoDaily. Flags:
  - ORPHAN_TASK            : registered but not in registry
  - STALE_REGISTRY_ENTRY   : in registry but not registered
  - BARE_CMD_POWERSHELL    : HARD FAIL -- bare cmd.exe/powershell.exe/.bat action (always
                             flashes OpenConsole on Win11; convert to
                             wscript->run_exe_hidden.vbs chain)
  - VISIBLE_WINDOW         : action not on the wscript->pythonw hidden chain (subtler patterns,
                             including the retired wscript->run_hidden.vbs ShellExecute path)
  - SILENT_TASK            : active task hasn't fired in (cadence x 3) window
  - PYTHON_NOT_PYTHONW     : long-running python.exe launch (should use pythonw.exe)
  - CANDIDATE_FOR_REMOVAL  : registry-disabled AND last ran > 30 days ago
  - DISABLED_BUT_DOCUMENTED_ACTIVE : registry says Active, Task Scheduler says Disabled,
                             and the row carries no intentional-disable annotation
  - NON_REPEATING_TRIGGER  : registry documents an "every N min/h" cadence but no enabled
                             trigger repeats (one-shot trigger -> fires once, dark forever)
  - REPETITION_INTERVAL_MISMATCH : live repetition >2x slower than the documented cadence

BLIND SPOT CLOSED (2026-07-30, the LEVELS-BLINDNESS incident): the engine ran 772 ticks
with ZERO key levels because `Gamma_LevelRefresh` was Disabled -- as were 48 other tasks
this registry documents as Active, including `Gamma_PremarketReadiness`, the gate built
to catch precisely that. This audit reported nothing, because every per-task check sat
below a `if state == "Disabled": continue` in `audit()`: disabling a task did not make it
FAIL a check, it removed the task from checking altogether. Silence read as health.
`evaluate_trigger_health()` now runs BEFORE that skip and is a pure function, so
`backtest/tests/test_scheduled_task_triggers_live.py` can RED-proof it against fixtures.
  - CLAUDE_NATIVE_TASK_UNGOVERNED : a Claude-native scheduled task (~/.claude/scheduled-tasks/)
                             exists that isn't in KNOWN_CLAUDE_NATIVE_TASKS below (see
                             AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS, queue.md 2026-07-25)

GOVERNANCE BLIND SPOT CLOSED (2026-07-25, self-audit gap -> queue item -> this fix): this
script only ever knew about `Gamma_*` WINDOWS tasks. A SEPARATE scheduling mechanism --
Claude-native scheduled skills living at `~/.claude/scheduled-tasks/<name>/SKILL.md` -- was
invisible to every governance surface here and in SCHEDULED-TASKS.md. That is how a daily
**opus** fire (`gamma-sniper-shadow-eod`, ~$100/mo) survived 2 months processing data frozen
since 2026-05-22 while the registry believed it had been "retired 2026-06-18": nothing ever
looked at that directory. Both offenders were moved to
`~/.claude/scheduled-tasks-retired-2026-07-25/` by hand on 2026-07-25; this audit now makes
sure a THIRD one can't grow there unnoticed.

Enumeration: `setup/scripts/_list-gamma-tasks-json.ps1` returns every `Gamma_*` task PLUS
a small explicit `$ExtraTaskNames` allowlist of other repo-managed automation registered
under a different name (e.g. SwjshAK-BrainSync). Those extra tasks are exempt from
ORPHAN_TASK/STALE_REGISTRY_ENTRY (SCHEDULED-TASKS.md is Gamma's own registry, not theirs)
but ARE fully subject to every window-leak safety check below -- see KNOWN_EXTERNAL_TASKS.

Writes:
  automation/state/scheduled-tasks-audit.json
  Console summary suitable for the daily digest.

Exit code 0 if no flags, 1 if any. Daily routine reads the JSON and surfaces RED to STATUS.md.

STRUCTURAL GUARD (2026-07-14, J: "stop the fkin popups on my screen"): a 0-task scan
(PowerShell helper failure, task-scheduler service down, etc.) must NEVER read as a clean
GREEN -- see the `total_registered == 0` hard-fail in `audit()`. A previous sibling
auditor (audit_window_leak_compliance.py) silently reported near-zero violations for
weeks not because there were none, but because it never looked at the live task registry
at all -- only at source-file text patterns. Silent-pass-on-empty-scan is the same failure
mode one layer up; guarded here explicitly so it can't recur.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
# TZ-SYSTEMIC FIX (2026-06-26): machine is Mountain time; datetime.now().weekday() returns
# Mountain weekday, which can be Saturday (5) when ET is still Friday.  Weekend-suppression
# logic that depends on the local weekday must use ET weekday.
from et_clock import et_weekday as _et_weekday  # DST-aware ET weekday

REGISTRY_PATH = Path("automation/state/SCHEDULED-TASKS.md")
AUDIT_OUT = Path("automation/state/scheduled-tasks-audit.json")

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost allocation when spawning console
# binaries (powershell.exe, tasklist.exe, git.exe). See CLAUDE.md OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Repo-managed automation registered under a non-Gamma_ name (see the matching
# $ExtraTaskNames array in _list-gamma-tasks-json.ps1, which is what actually pulls
# these into `tasks` below). SCHEDULED-TASKS.md is Gamma's OWN registry -- these
# will never appear in it, so they're exempt from ORPHAN_TASK/STALE_REGISTRY_ENTRY,
# but every window-leak safety check still runs against them normally.
KNOWN_EXTERNAL_TASKS = {"SwjshAK-BrainSync"}

# Claude-native scheduled skills (~/.claude/scheduled-tasks/<name>/SKILL.md) -- a completely
# DIFFERENT scheduling mechanism from Windows Task Scheduler, invisible to `_registered_tasks()`
# above. Empty by design as of 2026-07-25: the only 2 that ever existed
# (`gamma-sniper-shadow-eod`, `autoresearch-fleet`) were both retired to
# `~/.claude/scheduled-tasks-retired-2026-07-25/` for being ungoverned cost sinks (one was a
# daily **opus** fire, ~$100/mo, dead for 2 months and nobody noticed). Any name found under
# the LIVE directory that isn't in this set gets flagged CLAUDE_NATIVE_TASK_UNGOVERNED --
# review its SKILL.md (model tier, cadence, cost) before adding it here, and give it a real
# row in SCHEDULED-TASKS.md the same way any Gamma_* task gets one.
KNOWN_CLAUDE_NATIVE_TASKS: set[str] = set()

# Resolve the actual Windows user profile dir even when this runs under a service account or
# a shell with HOME unset -- Path.home() is the correct cross-platform fallback (C9: anchor to
# a reliable base, never assume an env var is set).
CLAUDE_NATIVE_TASKS_DIR = Path.home() / ".claude" / "scheduled-tasks"


def _powershell_file(path: Path) -> str:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        capture_output=True, text=True, check=False,
        creationflags=_CREATE_NO_WINDOW,
    ).stdout


def _parse_registry(text: str) -> tuple[set[str], set[str]]:
    """Return (active_names, disabled_names) parsed from the registry's markdown tables."""
    active: set[str] = set()
    disabled: set[str] = set()
    section = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## Active"):
            section = "active"
            continue
        if s.startswith("## Disabled"):
            section = "disabled"
            continue
        if s.startswith("## "):
            section = None
            continue
        if section in ("active", "disabled") and s.startswith("| `Gamma_"):
            m = re.match(r"^\|\s*`(Gamma_[^`]+)`", s)
            if m:
                (active if section == "active" else disabled).add(m.group(1))
    return active, disabled


# ---------------------------------------------------------------------------
# TRIGGER / DISABLED-DRIFT CHECKS  (added 2026-07-30 after the LEVELS-BLINDNESS
# incident -- see the three flag docstrings below and the module header.)
#
# THE INCIDENT: on 2026-07-30 the engine ran 772 ticks with ZERO key levels.
# `Gamma_LevelRefresh` (the 5-min intraday level refresher) and
# `Gamma_PremarketReadiness` (the gate BUILT to catch exactly that) were both
# State=Disabled -- along with 47 other tasks this registry documents as Active.
# NOTHING flagged it. The reason is one line in `audit()`'s task loop:
#
#     if state == "Disabled":
#         continue
#
# Every per-task check lived BELOW that `continue`, so flipping a documented-Active
# task to Disabled did not make it fail a check -- it removed it from checking
# entirely. Silence read as health: the audit that night emitted 2 unrelated
# SILENT_TASK flags and nothing else. That is the C7 failure mode (silent success
# is failure) applied to the monitor itself.
#
# The module docstring also advertised a `CANDIDATE_FOR_REMOVAL: disabled > 30 days`
# flag that was never implemented -- an L249-class stub (a docstring citing a
# never-built check, unchallenged across many fires). It is implemented below.
# ---------------------------------------------------------------------------

# Explicit "this task is off ON PURPOSE" markers used in the Active table's Why column.
# A row carrying one of these is an ACKNOWLEDGED pause (J's call, or a documented
# retirement) and must NOT be flagged -- otherwise the new flag fires 8 permanent
# false positives and gets ignored, which is how monitors die.
_INTENTIONAL_DISABLE_RE = re.compile(
    r"(⚠\s*DISABLED"                 # "⚠ DISABLED as of 2026-07-08 (T10 drift-fix ...)"
    r"|\*\*DISABLED\*\*"                  # "**DISABLED** -- shares Max plan rate-limit pool ..."
    r"|RETIRED[^|]{0,60}?DISABLED"        # "RETIRED 2026-06-25 -> DISABLED."
    r")",
    re.I,
)

# "every 5 min" / "every 2h" / "relaunch-check every 30 min" -> a REPEATING cadence.
# Deliberately does NOT match discrete multi-fire cadences like
# "08:35/09:30/12:00/15:50 ET weekdays" (4 separate one-shot triggers, correctly
# shaped) or "daily 21:30 ET" -- those must never be told they need a repetition.
_CADENCE_EVERY_RE = re.compile(r"every\s+(\d+)\s*(min|minute|minutes|h|hr|hour|hours)\b", re.I)

_ISO_DUR_RE = re.compile(
    r"^P(?:(?P<d>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<h>\d+(?:\.\d+)?)H)?(?:(?P<m>\d+(?:\.\d+)?)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$",
    re.I,
)


def _iso_duration_minutes(value: str | None) -> float | None:
    """ISO-8601 duration ('PT5M', 'PT6H25M', 'P3650D') -> minutes. None if unparseable.

    Task Scheduler emits repetition Interval/Duration in this form. An EMPTY duration
    is legal and means "repeat indefinitely" -- callers must distinguish that (None)
    from "no repetition at all".
    """
    if not value or not isinstance(value, str):
        return None
    m = _ISO_DUR_RE.match(value.strip())
    if not m:
        return None
    d = float(m.group("d") or 0)
    h = float(m.group("h") or 0)
    mi = float(m.group("m") or 0)
    s = float(m.group("s") or 0)
    total = d * 1440 + h * 60 + mi + s / 60
    return total or None


def _parse_active_rows(text: str) -> dict[str, dict]:
    """Return {task: {'cadence':..., 'why':..., 'row':...}} for '## Active' table rows.

    Mirrors `_parse_registry`'s section walk so the two never disagree about which
    rows are 'Active'.
    """
    rows: dict[str, dict] = {}
    section = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## Active"):
            section = "active"
            continue
        if s.startswith("## "):
            section = None
            continue
        if section != "active" or not s.startswith("| `Gamma_"):
            continue
        m = re.match(r"^\|\s*`(Gamma_[^`]+)`\s*\|([^|]*)\|([^|]*)\|(.*)$", s)
        if m:
            rows[m.group(1)] = {
                "cadence": m.group(2).strip(),
                "cost": m.group(3).strip(),
                "why": m.group(4),
                "row": s,
            }
    return rows


def _intentionally_disabled(text: str) -> set[str]:
    """Task names whose Active-table row EXPLICITLY documents an intentional disable."""
    return {
        name for name, row in _parse_active_rows(text).items()
        if _INTENTIONAL_DISABLE_RE.search(row["row"])
    }


def _documented_repeat_minutes(cadence: str) -> int | None:
    """'every 5 min, 09:30-16:00 ET wd' -> 5.  Non-repeating cadence -> None."""
    m = _CADENCE_EVERY_RE.search(cadence or "")
    if not m:
        return None
    n = int(m.group(1))
    return n * 60 if m.group(2).lower().startswith(("h", "hr", "hour")) else n


def _trigger_repeat_minutes(triggers: list[dict] | None) -> float | None:
    """Smallest repetition interval across a task's triggers, in minutes.

    None means NO trigger on this task repeats -- the one-shot-goes-dark shape.
    """
    best: float | None = None
    for tr in triggers or []:
        if not tr.get("enabled", True):
            continue
        mins = _iso_duration_minutes(tr.get("repetition_interval"))
        if mins is not None and (best is None or mins < best):
            best = mins
    return best


def evaluate_trigger_health(registry_text: str, tasks: list[dict]) -> list[dict]:
    """Pure evaluator for the three drift classes the 2026-07-30 blindness exposed.

    Kept PURE (registry text + task dicts in, flags out -- no PowerShell, no clock)
    so `backtest/tests/test_scheduled_task_triggers_live.py` can RED-proof it against
    fixtures rather than by breaking the live box.

    Flags:
      DISABLED_BUT_DOCUMENTED_ACTIVE -- registry says Active, live says Disabled, and
        the row carries NO explicit intentional-disable annotation. THE 2026-07-30 flag.
      NON_REPEATING_TRIGGER -- registry documents an 'every N min/h' cadence but no
        enabled trigger carries a repetition interval. This is the historical
        one-shot-trigger-goes-dark failure mode (project_scheduled_task_onetime_
        trigger_dark): fires once, then never again, while every other field still
        looks healthy.
      REPETITION_INTERVAL_MISMATCH -- the live repetition interval is >2x the
        documented cadence (e.g. doc says every 5 min, task actually repeats hourly).
    """
    active_rows = _parse_active_rows(registry_text)
    exempt = _intentionally_disabled(registry_text)
    by_name = {t["name"]: t for t in tasks}
    flags: list[dict] = []

    for name in sorted(active_rows):
        task = by_name.get(name)
        if task is None:
            continue  # STALE_REGISTRY_ENTRY already covers this
        if name in exempt:
            continue

        if task.get("state") == "Disabled":
            flags.append({
                "flag": "DISABLED_BUT_DOCUMENTED_ACTIVE", "task": name,
                "note": (f"registry documents this task as ACTIVE (cadence: "
                         f"{active_rows[name]['cadence']!r}) but Task Scheduler state is "
                         f"Disabled, and its row carries no intentional-disable annotation. "
                         f"It fires NEVER. Re-enable with `Enable-ScheduledTask -TaskName "
                         f"{name}`, or annotate the row if the pause is deliberate."),
            })
            continue

        want = _documented_repeat_minutes(active_rows[name]["cadence"])
        if want is None:
            continue
        have = _trigger_repeat_minutes(task.get("triggers"))
        if have is None:
            flags.append({
                "flag": "NON_REPEATING_TRIGGER", "task": name,
                "note": (f"registry documents a repeating cadence "
                         f"({active_rows[name]['cadence']!r} = every {want} min) but no enabled "
                         f"trigger carries a repetition interval -- a one-shot trigger fires "
                         f"once and then goes dark forever. Re-register with "
                         f"-RepetitionInterval."),
            })
        elif have > want * 2:
            flags.append({
                "flag": "REPETITION_INTERVAL_MISMATCH", "task": name,
                "note": (f"registry documents every {want} min but the live trigger repeats "
                         f"every {have:g} min (>2x slower)."),
            })

    return flags


def _registered_tasks() -> list[dict]:
    """Return list of {name, state, execute, arguments, last_run, last_result, next_run, triggers}."""
    # C9 -- anchor to __file__, never CWD. This was a repo-relative path until 2026-08-09:
    # any caller whose CWD wasn't the repo root got `powershell -File <missing>`, which
    # drops PowerShell into banner mode and returns "Windows PowerShell\nCopyright ..." on
    # stdout. That is 78 non-empty chars, so the `not raw.strip()` guard below waved it
    # through and json.loads died with a bare JSONDecodeError -- the scan reporting
    # "broken" instead of the real "you called me from the wrong directory".
    helper = SCRIPTS_DIR / "_list-gamma-tasks-json.ps1"
    raw = _powershell_file(helper)
    if not raw.strip():
        return []
    # Non-JSON stdout means the helper never ran (banner mode, execution-policy refusal,
    # a stray Write-Host). Say so, rather than surfacing a positional JSON parse error.
    if raw.lstrip()[:1] not in ("[", "{"):
        raise RuntimeError(
            f"task-enumeration helper returned non-JSON stdout "
            f"(first 80 chars: {raw.strip()[:80]!r}) -- helper={helper}"
        )
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _is_hidden(execute: str, arguments: str) -> bool:
    """Approved hidden-window patterns per OP-27.

    2026-07-14 CORRECTION (J: "stop the fkin popups on my screen" -- root cause was
    this exact function silently approving a proven-leaky pattern): `run_hidden.vbs`
    was DEMOTED from approved to NOT-hidden. It was carried as "older pattern, still
    approved" ever since the 2026-05-17 escalation, but `run_ps1_hidden.py`'s own
    docstring (written that SAME evening) documents the actual finding: `run_hidden.vbs`
    uses `WScript.Shell.Run` (ShellExecute), which "still leaks WindowsTerminal
    -Embedding windows on Windows 11 default-terminal configs" -- the fix that evening
    was to STOP using it, not to keep approving it. Whoever wrote this function's
    docstring transcribed the old pattern as still-good instead of retired. Live proof
    2026-07-14: Gamma_DiscordBridge fires every 5 min via this exact chain, 24/7 --
    the highest-frequency violator on the box, invisible to this audit until now
    because this function said it was fine.

    Canonical patterns, current:

    1. `wscript.exe //nologo run_exe_hidden.vbs <pythonw> <run_ps1_hidden.py> <ps1>`
       -- canonical L42 zero-leak pattern for PowerShell-wrapped tasks. Uses Python
       `subprocess.Popen(..., creationflags=CREATE_NO_WINDOW)` -- CreateProcess
       directly, which Windows is REQUIRED to honor.

    2. `wscript.exe //nologo run_exe_hidden.vbs <pythonw> <run_cmd_hidden.py> [args]`
       -- canonical WS6 zero-leak pattern for cmd-style grind tasks (2026-06-26).
       run_cmd_hidden.py accepts --env KEY=VAL + -- <python-exe> -m <module>.

    3. `wscript.exe //nologo run_hidden_exec.vbs <ps1> [args]` -- WshShell.Exec
       (CreateProcess) instead of Shell.Run (ShellExecute); also bypasses the WT
       DefaultTerminal handler. Approved alternative when no Python hop is wanted.

    4. A direct GUI-subsystem `pythonw.exe` action -- no console ever allocated,
       regardless of launcher (Task Scheduler included).

    NOT hidden: `wscript.exe //nologo run_hidden.vbs <ps1>` -- Shell.Run/ShellExecute,
    routes through the Win11 DefaultTerminal handler, leaks a `WindowsTerminal
    -Embedding` window on EVERY fire. Retired 2026-07-14; any task still on this
    pattern must be converted to #1 above.

    NOT hidden: a DIRECT `powershell.exe -WindowStyle Hidden` action. Task Scheduler
    allocates the console (OpenConsole.exe -Embedding on Win11) and SHOWS it before
    PowerShell applies -WindowStyle Hidden ~200ms later -> a visible black flash on EVERY
    fire (root-caused 2026-06-20 via Gamma_CryptoGrinderKeepalive, every 5 min = ~288
    flashes/day).

    NOT hidden: a DIRECT `cmd.exe /c ...` action, or a bare `.bat` action (Task
    Scheduler spawns cmd.exe to interpret it). Same allocation problem.
    """
    e = (execute or "").lower()
    a = (arguments or "").lower()
    if "wscript" in e and ("run_exe_hidden.vbs" in a or "run_hidden_exec.vbs" in a):
        return True
    if e.endswith("pythonw.exe"):
        return True
    return False


def _is_bare_console_launcher(execute: str) -> bool:
    """Return True if the task action is a bare console-subsystem launcher.

    Bare cmd.exe, powershell.exe, or a direct .bat/.cmd action (Task Scheduler
    spawns cmd.exe to interpret those) ALWAYS flash a console window on
    Windows 11 (OpenConsole -Embedding) before any -WindowStyle Hidden takes
    effect.  These MUST be converted to the wscript -> run_exe_hidden.vbs ->
    pythonw -> run_cmd_hidden.py / run_ps1_hidden.py chain.

    This check is a HARD FAIL in the audit (exit 1) -- not a warn -- because
    a regressed task will flash on every fire (up to 288 times/day for 5-min
    cadence tasks).  There is no acceptable reason to have a bare cmd.exe,
    bare powershell.exe, or bare .bat/.cmd Gamma task action.
    """
    e = (execute or "").strip().lower()
    # Match basename only so full paths like C:\Windows\System32\cmd.exe also match
    basename = e.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if basename in ("cmd.exe", "powershell.exe", "pwsh.exe"):
        return True
    return basename.endswith(".bat") or basename.endswith(".cmd")


def _is_long_running_python_with_console(execute: str, arguments: str) -> bool:
    e = (execute or "").lower()
    if e.endswith("python.exe"):
        return True
    if "python.exe" in (arguments or "").lower() and "live_grinder" in (arguments or "").lower():
        return True
    return False


HOOKS_SETTINGS_PATH = Path(".claude/settings.local.json")


def _is_bare_hook_command(command: str) -> bool:
    """Return True if a Claude Code hook `command` string is a bare console launcher.

    Root-caused 2026-07-03 (J: "cmd popups every few minutes"): PreToolUse/PostToolUse
    hooks fire on EVERY tool call across every session (interactive AND every scheduled
    `claude --print` task) -- a far higher-frequency flash source than any Task Scheduler
    action, and a surface this audit never covered before since hooks aren't Task
    Scheduler entries. Same Win11 OpenConsole-before-WindowStyle-Hidden mechanism as
    BARE_CMD_POWERSHELL applies here too. Fix: route through
    setup/scripts/run_hook_hidden.py (pythonw.exe + CREATE_NO_WINDOW), the same pattern
    _is_hidden() already approves for scheduled tasks.
    """
    first_tok = (command or "").strip().split(" ", 1)[0].strip('"')
    basename = first_tok.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].lower()
    return basename in ("cmd.exe", "cmd", "powershell.exe", "powershell", "pwsh.exe", "pwsh")


def _audit_hooks() -> list[dict]:
    """Flag any .claude/settings.local.json hook `command` that isn't hidden-window-safe."""
    flags: list[dict] = []
    if not HOOKS_SETTINGS_PATH.exists():
        return flags
    try:
        data = json.loads(HOOKS_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        flags.append({"flag": "HOOKS_UNPARSEABLE", "task": str(HOOKS_SETTINGS_PATH),
                      "note": f"{type(e).__name__}: {e}"})
        return flags
    for phase, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if h.get("type") != "command" or not cmd:
                    continue
                if _is_bare_hook_command(cmd):
                    flags.append({"flag": "BARE_HOOK_POWERSHELL", "task": f"hook:{phase}",
                                  "note": f"HARD FAIL -- bare console launcher in hook command: "
                                          f"{cmd[:100]!r}. Route through setup/scripts/run_hook_hidden.py."})
    return flags


def _claude_native_tasks(base: Path | None = None) -> list[dict]:
    """Enumerate Claude-native scheduled skills under `~/.claude/scheduled-tasks/`.

    Each task is a subdirectory containing a `SKILL.md` whose YAML frontmatter has a
    `name:` field (see any `.claude/skills/*/SKILL.md` for the same convention this repo
    already uses). Returns `[{"name": ..., "dir": ...}, ...]`, using the directory's own
    name as a fallback if `SKILL.md` is missing or unparseable.

    Fail-open by construction: a missing directory or an unreadable file yields fewer
    entries, never an exception -- this is a VISIBILITY check (mirrors `_registered_tasks`'
    own "0 tasks could mean a scan failure" caution), not a gate that can block anything.
    Only scans the LIVE directory -- `scheduled-tasks-retired-*` dirs are deliberately
    excluded (they hold tasks already reviewed and pulled out of governance on purpose).
    """
    root = base if base is not None else CLAUDE_NATIVE_TASKS_DIR
    out: list[dict] = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        skill = child / "SKILL.md"
        if skill.exists():
            try:
                text = skill.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^name:\s*(.+?)\s*$", text, re.MULTILINE)
                if m:
                    name = m.group(1).strip()
            except OSError:
                pass
        out.append({"name": name, "dir": str(child)})
    return out


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _last_run_age_hours(last_run: str | None) -> float | None:
    if not last_run:
        return None
    dt = _parse_iso(last_run)
    if dt is None:
        return None
    # 1999 sentinel means never run
    if dt.year < 2020:
        return None
    return (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600


def audit() -> dict:
    if not REGISTRY_PATH.exists():
        return {"error": f"registry missing: {REGISTRY_PATH}", "health": "RED"}
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    active_registry, disabled_registry = _parse_registry(registry_text)
    tasks = _registered_tasks()

    # STRUCTURAL GUARD (2026-07-14): a scan that returns zero tasks (PowerShell helper
    # crashed, Task Scheduler service unreachable, malformed JSON silently swallowed)
    # must never be indistinguishable from "all clear". `_registered_tasks()` already
    # returns [] on that failure mode -- treat it as a hard error, not a clean report.
    if not tasks:
        return {"error": "0 tasks returned by _registered_tasks() -- PowerShell helper "
                          "failure or empty Task Scheduler query; NOT a clean scan",
                "health": "RED"}

    by_name = {t["name"]: t for t in tasks}

    flags: list[dict] = []

    # Claude Code hook commands (.claude/settings.local.json) -- separate surface from
    # Task Scheduler actions, same hidden-window requirement. See _audit_hooks docstring.
    flags.extend(_audit_hooks())

    # Claude-native scheduled skills (~/.claude/scheduled-tasks/) -- the governance blind
    # spot that let gamma-sniper-shadow-eod run ungoverned for 2 months. See module
    # docstring + AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS.
    for ct in _claude_native_tasks():
        if ct["name"] not in KNOWN_CLAUDE_NATIVE_TASKS:
            flags.append({
                "flag": "CLAUDE_NATIVE_TASK_UNGOVERNED", "task": ct["name"],
                "note": (f"Claude-native scheduled task at {ct['dir']} is not in "
                         f"KNOWN_CLAUDE_NATIVE_TASKS (audit_scheduled_tasks.py) -- review "
                         f"its SKILL.md (model tier/cadence/cost), then either allowlist it "
                         f"there + give it a real SCHEDULED-TASKS.md row, or retire it "
                         f"(move to ~/.claude/scheduled-tasks-retired-<date>/)."),
            })

    # Registered but not in registry (external repo-managed tasks are known-external
    # by design -- see KNOWN_EXTERNAL_TASKS -- not an accidental orphan).
    for name in sorted(by_name):
        if name in KNOWN_EXTERNAL_TASKS:
            continue
        if name not in active_registry and name not in disabled_registry:
            flags.append({"flag": "ORPHAN_TASK", "task": name,
                          "note": f"task registered but not in {REGISTRY_PATH}"})

    # In registry but not registered
    for name in sorted(active_registry):
        if name not in by_name:
            flags.append({"flag": "STALE_REGISTRY_ENTRY", "task": name,
                          "note": "registry says active but task not registered"})

    # Trigger shape + disabled-drift (2026-07-30 LEVELS-BLINDNESS incident).
    # MUST run BEFORE the loop below, which deliberately skips disabled tasks for the
    # window/console/silence checks -- that skip is what made a documented-Active task
    # going Disabled completely invisible. See evaluate_trigger_health's docstring.
    flags.extend(evaluate_trigger_health(registry_text, tasks))

    # CANDIDATE_FOR_REMOVAL -- advertised in this module's docstring since it was
    # written, never actually implemented until 2026-07-30 (L249 class: a docstring
    # citing a check nobody built). Only fires for tasks the registry ALREADY agrees
    # are disabled, so it is a de-sprawl nudge, never noise about a live pause.
    for name in sorted(disabled_registry):
        t = by_name.get(name)
        if t is None or t.get("state") != "Disabled":
            continue
        age_h = _last_run_age_hours(t.get("last_run"))
        if age_h is not None and age_h > 30 * 24:
            flags.append({"flag": "CANDIDATE_FOR_REMOVAL", "task": name,
                          "note": f"disabled and last ran {age_h / 24:.0f} days ago -- "
                                  f"consider Unregister-ScheduledTask + move to Reference."})

    # Window visibility + python console + silent task
    for t in tasks:
        name = t["name"]
        state = t["state"]
        if state == "Disabled":
            # Intentional: the checks below are about how a RUNNING task behaves.
            # Disabled-state drift is caught by evaluate_trigger_health() above --
            # do NOT let this `continue` be the only thing a disabled task meets.
            continue
        if _is_bare_console_launcher(t["execute"]):
            # HARD FAIL: bare cmd.exe / powershell.exe flashes a window on EVERY fire.
            # This is distinct from VISIBLE_WINDOW (which catches subtler patterns) and
            # is always a bug -- there is no approved use of a bare console launcher.
            flags.append({"flag": "BARE_CMD_POWERSHELL", "task": name,
                          "note": f"HARD FAIL -- bare console launcher: execute={t['execute']!r}. "
                                  f"Convert to wscript->run_exe_hidden.vbs->pythonw->run_cmd_hidden.py chain."})
        elif not _is_hidden(t["execute"], t["arguments"]):
            flags.append({"flag": "VISIBLE_WINDOW", "task": name,
                          "note": f"execute={t['execute']!r} args={t['arguments'][:80]!r}"})
        if _is_long_running_python_with_console(t["execute"], t["arguments"]):
            flags.append({"flag": "PYTHON_NOT_PYTHONW", "task": name,
                          "note": "long-running python.exe should use pythonw.exe"})

        # Silent-task check using simple rules:
        # If a task hasn't fired in 24 hours, flag it (unless its cadence is weekly)
        age_h = _last_run_age_hours(t.get("last_run"))
        if age_h is None:
            # never ran or unparseable — flag only if was supposed to run
            continue
        # Weekend false-positive suppression: weekday-only tasks are expected silent on
        # Sat/Sun. Max legitimate gap = ~62h (Thu EOD -> Mon premarket); allow 70h.
        _today_dow = _et_weekday()  # 5=Sat, 6=Sun — ET (not local Mountain) — TZ-SYSTEMIC fix
        if _today_dow >= 5 and age_h <= 70:
            continue
        # Heuristic: anything > 26h old without successful run = SILENT
        if age_h > 26 and "Weekly" not in name and "Monday" not in name:
            flags.append({"flag": "SILENT_TASK", "task": name,
                          "note": f"last ran {age_h:.1f}h ago — expected within 26h"})

    health = "RED" if flags else "GREEN"
    summary = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_registered": len(tasks),
        "active_registered": sum(1 for t in tasks if t["state"] != "Disabled"),
        "disabled_registered": sum(1 for t in tasks if t["state"] == "Disabled"),
        "registry_active": len(active_registry),
        "registry_disabled": len(disabled_registry),
        "claude_native_registered": len(_claude_native_tasks()),
        "flags_count": len(flags),
        "flags": flags,
        "health": health,
    }
    return summary


def main():
    out = audit()
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("=" * 70)
    print("SCHEDULED-TASKS AUDIT")
    print("=" * 70)
    if "error" in out:
        print(f"  ERROR: {out['error']}")
        sys.exit(1)
    print(f"  audited_at:           {out['audited_at']}")
    print(f"  registered active:    {out['active_registered']}  (registry says: {out['registry_active']})")
    print(f"  registered disabled:  {out['disabled_registered']}  (registry says: {out['registry_disabled']})")
    print(f"  HEALTH:               {out['health']}")
    if out["flags"]:
        print(f"  FLAGS ({len(out['flags'])}):")
        for f in out["flags"]:
            print(f"    [{f['flag']:<22s}] {f['task']:<35s} {f['note']}")
    else:
        print(f"  FLAGS:                none -- registry & reality in sync, all windows hidden")
    print()
    print(f"  scorecard: {AUDIT_OUT}")
    sys.exit(0 if not out["flags"] else 1)


if __name__ == "__main__":
    main()
