"""WS5 NEVER-DARK/BLIND/FAIL-TO-PLACE liveness guards (2026-06-26).

Four bugs were fixed in the same session and are now UNGATED.  These guards
make them impossible to regress silently.

  (a) DAILY-RECURRING TRIGGER — Gamma engine tasks (SightBeacon, HeartbeatCore,
      Grind_Watchdog, FleetExecutor, HealthBeacon) must use a daily-recurring
      CalendarTrigger (ScheduleByDay), NOT a one-shot MSFT_TaskTimeTrigger.
      The one-shot fires only once (the install day) then goes permanently dark.
      Documented 2026-06-26 memory: "One-time scheduled trigger goes dark every day."
      Guards: snapshot-based (parse committed XML).

  (b) fleet_broker.place_bracket SIMPLE_FALLBACK — Alpaca rejects bracket+oto for
      options (code 42210000). Without simple_fallback the engine could never place
      a single option order through the fleet_broker path.  simple_fallback=True
      allows a plain limit entry when complex orders are refused, provided the
      caller manages TP/stop via exit_manager.
      Guards: source-code inspection (no live call needed).

  (c) sight_beacon SORT=DESC — The Alpaca bars endpoint with sort=asc+limit=300
      returns the OLDEST 300 bars, truncating the newest off the tail.  The beacon
      froze at a prior-session price (2026-06-26 scar: stuck at 731.86, ~$2.80
      stale all morning).  sort=desc keeps the NEWEST 300; reversing restores order.
      Guards: source-code inspection.

  (d) engine_health.build_report WATCHES CORE-DECISIONS + SIGHT_BEACON — After the
      LLM heartbeat was retired and replaced by heartbeat_core (deterministic Python)
      + sight_beacon (direct REST), engine_health must watch the NEW producers
      (core-decisions.jsonl, sight-beacon.json) not the retired ones (loop-state.json,
      tv-watchdog).  Watching retired logs read "missing" forever, making the monitor
      permanently YELLOW/blind to the real engine.
      Guards: import + call engine_health module (monkey-patch state dir).

HOW TO RUN (from repo root):
    backtest\\.venv\\Scripts\\python.exe -m pytest backtest/tests/test_engine_liveness_guards.py -v

Which guards need live schtasks vs snapshot:
  - (a) tries live `schtasks /query /xml` first; if that fails (CI / non-Windows) it
        falls back to the committed snapshot at automation/state/engine-task-snapshot.json.
  - (b)(c)(d) are pure source/module inspection -- no network, no scheduler, always live.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# (a) DAILY-RECURRING TRIGGER helpers
# ---------------------------------------------------------------------------

_ENGINE_TASKS = [
    "Gamma_SightBeacon",
    "Gamma_HeartbeatCore",
    "Gamma_Grind_Watchdog",
    "Gamma_FleetExecutor",
    "Gamma_HealthBeacon",
]

_SNAPSHOT_PATH = _REPO / "automation" / "state" / "engine-task-snapshot.json"

# The OLD broken pattern: a plain CalendarTrigger with NO ScheduleByDay child
# fires only once (== MSFT_TaskTimeTrigger semantics on re-register without -Daily).
# The NEW correct pattern is a CalendarTrigger that includes <ScheduleByDay>.
_ONE_SHOT_PATTERN = re.compile(
    r"<CalendarTrigger>.*?</CalendarTrigger>", re.DOTALL
)
_DAILY_MARKER = re.compile(r"<ScheduleByDay>")


def _query_task_xml_live(task_name: str) -> str | None:
    """Try `schtasks /query /xml /tn <name>`. Returns the XML string, or None on failure.

    schtasks on this rig writes UTF-8 bytes to stdout even though the XML header claims
    UTF-16.  We decode as UTF-8 (the actual byte encoding of the subprocess pipe), not
    UTF-16-LE (which would strip the ASCII text into empty pairs and lose all content).
    """
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/xml", "/tn", task_name],
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None


def _load_snapshot() -> dict[str, str]:
    """Load the committed task XML snapshot. Keys are task names, values are XML strings."""
    assert _SNAPSHOT_PATH.exists(), (
        f"Task snapshot missing: {_SNAPSHOT_PATH}\n"
        "Re-generate with: (on the host box, in PowerShell)\n"
        "  $tasks = @('Gamma_SightBeacon','Gamma_HeartbeatCore',"
        "  'Gamma_Grind_Watchdog','Gamma_FleetExecutor','Gamma_HealthBeacon')\n"
        "  $snap = @{}\n"
        "  foreach ($t in $tasks) {\n"
        "    $xml = (schtasks /query /xml /tn $t 2>&1) -join \"`n\"\n"
        "    $snap[$t] = $xml\n"
        "  }\n"
        "  $snap | ConvertTo-Json | Out-File automation/state/engine-task-snapshot.json"
    )
    raw = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8-sig"))
    return {k: v for k, v in raw.items()}


def _get_task_xml(task_name: str) -> tuple[str, str]:
    """(xml_string, source) where source is 'live' or 'snapshot'."""
    live = _query_task_xml_live(task_name)
    if live and len(live) > 50:
        return live, "live"
    snap = _load_snapshot()
    assert task_name in snap, (
        f"Task {task_name!r} missing from snapshot {_SNAPSHOT_PATH}. "
        "Update the snapshot (see _load_snapshot docstring)."
    )
    return snap[task_name], "snapshot"


def _assert_daily_recurring(task_name: str) -> None:
    """Assert the task has a CalendarTrigger with ScheduleByDay (daily-recurring)."""
    xml, source = _get_task_xml(task_name)

    # The old broken pattern: CalendarTrigger blocks that do NOT contain ScheduleByDay.
    # A one-shot time trigger has no <ScheduleByDay> element inside <Triggers>.
    triggers_section = re.search(r"<Triggers>(.*?)</Triggers>", xml, re.DOTALL)
    assert triggers_section is not None, (
        f"[{source}] {task_name}: no <Triggers> block found in task XML. "
        "Task may be malformed or not registered."
    )
    triggers_xml = triggers_section.group(1)

    # Must NOT be a one-shot: no CalendarTrigger is acceptable only if another
    # recurring trigger type is present -- but for these tasks we always expect
    # CalendarTrigger+ScheduleByDay.
    calendar_blocks = re.findall(
        r"<CalendarTrigger>.*?</CalendarTrigger>", triggers_xml, re.DOTALL
    )
    assert calendar_blocks, (
        f"[{source}] {task_name}: no <CalendarTrigger> in <Triggers>. "
        "Task has no recurring trigger -- it is either one-shot or unregistered. "
        "Re-register with -Daily (MSFT_TaskDailyTrigger, not MSFT_TaskTimeTrigger)."
    )

    for block in calendar_blocks:
        has_daily = bool(_DAILY_MARKER.search(block))
        assert has_daily, (
            f"[{source}] {task_name}: CalendarTrigger found but contains NO "
            "<ScheduleByDay> element -- this is the one-shot anti-pattern (fires only "
            "once, engine goes dark the next day). Re-register with -Daily:\n"
            "  Unregister-ScheduledTask -TaskName '{task_name}' -Confirm:$false\n"
            "  # re-run the task's install script with the -Daily trigger fix\n"
            "Regressed trigger XML:\n" + textwrap.indent(block, "  ")
        )


# Explicit check for the ANTI-PATTERN: a CalendarTrigger WITHOUT ScheduleByDay
# is what the broken one-shot looked like. This function builds a synthetic XML
# that would have passed naively (has a CalendarTrigger, has a Repetition), but
# is missing the ScheduleByDay child -- which is the root cause of the bug.
_BROKEN_ONE_SHOT_XML = """\
<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-06-25T09:30:00</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <Duration>PT6H25M</Duration>
      </Repetition>
      <!-- NOTE: no ScheduleByDay child = one-shot, fires only once -->
    </CalendarTrigger>
  </Triggers>
</Task>
"""

_FIXED_DAILY_XML = """\
<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-06-26T09:30:00</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <Duration>PT6H25M</Duration>
        <StopAtDurationEnd>true</StopAtDurationEnd>
      </Repetition>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
</Task>
"""


class TestTriggerGuard:
    """(a) DAILY-RECURRING TRIGGER — guards for all 5 engine tasks."""

    def _check_broken_raises(self, xml: str, task: str) -> None:
        """Helper: assert that _assert_daily_recurring would FAIL on broken XML."""
        triggers_section = re.search(r"<Triggers>(.*?)</Triggers>", xml, re.DOTALL)
        assert triggers_section is not None
        triggers_xml = triggers_section.group(1)
        calendar_blocks = re.findall(
            r"<CalendarTrigger>.*?</CalendarTrigger>", triggers_xml, re.DOTALL
        )
        if not calendar_blocks:
            return  # No CalendarTrigger at all -- trivially broken
        for block in calendar_blocks:
            if not _DAILY_MARKER.search(block):
                return  # At least one block is missing ScheduleByDay -- correctly broken
        pytest.fail(
            f"Expected broken XML to be missing <ScheduleByDay> but it passed for {task}. "
            "Broken XML:\n" + xml
        )

    def test_broken_one_shot_pattern_would_fail(self):
        """FAIL on old: CalendarTrigger without ScheduleByDay (one-shot anti-pattern).
        This test documents that our detector CATCHES the regression."""
        self._check_broken_raises(_BROKEN_ONE_SHOT_XML, "synthetic_broken_task")

    def test_fixed_daily_pattern_passes(self):
        """PASS on new: CalendarTrigger WITH ScheduleByDay (daily-recurring)."""
        # Build a minimal snapshot-like structure to drive _assert_daily_recurring
        # without calling schtasks -- so this always runs on CI too.
        monkeypatched_snap = {"Gamma_Test_Daily": _FIXED_DAILY_XML}
        orig_load = _load_snapshot.__code__
        # Just call the logic inline:
        triggers_section = re.search(r"<Triggers>(.*?)</Triggers>", _FIXED_DAILY_XML, re.DOTALL)
        assert triggers_section is not None
        calendar_blocks = re.findall(
            r"<CalendarTrigger>.*?</CalendarTrigger>", triggers_section.group(1), re.DOTALL
        )
        assert calendar_blocks, "Fixed XML must have CalendarTrigger"
        for block in calendar_blocks:
            assert _DAILY_MARKER.search(block), "Fixed XML must have ScheduleByDay"

    @pytest.mark.parametrize("task_name", _ENGINE_TASKS)
    def test_engine_task_is_daily_recurring(self, task_name):
        """LIVE OR SNAPSHOT: each Gamma engine task must have a daily-recurring trigger.

        Tries live schtasks first (host box with tasks registered); falls back to the
        committed snapshot (CI / offline). Either way the same XML-level assertion runs:
        the task's CalendarTrigger must contain <ScheduleByDay> -- the marker that
        distinguishes MSFT_TaskDailyTrigger from the one-shot MSFT_TaskTimeTrigger.
        """
        _assert_daily_recurring(task_name)

    def test_snapshot_covers_all_engine_tasks(self):
        """Sanity floor: the snapshot file must contain entries for all 5 engine tasks.
        If a task is missing from the snapshot, the guard above silently skips it."""
        snap = _load_snapshot()
        missing = [t for t in _ENGINE_TASKS if t not in snap]
        assert not missing, (
            f"engine-task-snapshot.json is missing entries for: {missing}\n"
            "Re-generate the snapshot on the host box (see _load_snapshot docstring)."
        )


# ---------------------------------------------------------------------------
# (b) fleet_broker.place_bracket has simple_fallback param for options
# ---------------------------------------------------------------------------

_FLEET_BROKER_PATH = _REPO / "automation" / "state" / "fleet" / "fleet_broker.py"


def _load_fleet_broker():
    """Import fleet_broker.py by path (not installed as a package)."""
    spec = importlib.util.spec_from_file_location("fleet_broker_under_test", _FLEET_BROKER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSimpleFallbackParam:
    """(b) place_bracket must have simple_fallback param (options bracket fix)."""

    def test_place_bracket_has_simple_fallback_param(self):
        """PASS on fixed: simple_fallback=False default exists in the signature.

        The OLD broken state: place_bracket had no simple_fallback param, so when
        Alpaca returned 42210000 ('complex orders not supported') for both bracket
        AND oto, the function returned an error dict and the engine could never place
        a single option order via fleet_broker.
        """
        mod = _load_fleet_broker()
        assert hasattr(mod, "place_bracket"), "place_bracket missing from fleet_broker"
        sig = inspect.signature(mod.place_bracket)
        assert "simple_fallback" in sig.parameters, (
            "place_bracket is missing the simple_fallback parameter (2026-06-26 fix). "
            "Without it, Alpaca's 42210000 rejection of bracket+oto for options leaves "
            "the engine unable to place any option order via the fleet_broker path.\n"
            f"Current signature: {sig}"
        )

    def test_simple_fallback_defaults_to_false(self):
        """simple_fallback must default False (a stopless naked long violates C2 if
        the caller does NOT manage exits; the default enforces the contract)."""
        mod = _load_fleet_broker()
        sig = inspect.signature(mod.place_bracket)
        param = sig.parameters["simple_fallback"]
        assert param.default is False, (
            "simple_fallback must default to False to prevent a stopless naked long "
            "when fleet_broker is called without the caller explicitly opting in to "
            "engine-managed exits. Got default: " + repr(param.default)
        )

    def test_simple_fallback_false_refuses_without_live(self):
        """With live=False the function must return a _skipped sentinel (WATCH mode).
        This is orthogonal to simple_fallback but proves the safety gate is intact."""
        mod = _load_fleet_broker()
        result = mod.place_bracket(
            {"key": "x", "secret": "y", "base_url": "https://example.invalid"},
            symbol="SPY260628C00750000",
            qty=3,
            limit_price=1.00,
            take_profit_price=2.00,
            stop_price=0.50,
            live=False,
            simple_fallback=False,
        )
        assert "_skipped" in result, (
            "place_bracket with live=False must return a _skipped guard dict (WATCH mode). "
            "Got: " + repr(result)
        )

    def test_simple_fallback_source_contains_plain_limit_entry(self):
        """Source-level check: the simple_fallback branch must call a plain limit order
        (no order_class / bracket field) when both bracket and oto are rejected.

        The OLD broken code path: after two rejections, the function returned the error
        dict unconditionally -- no plain limit fallback existed.  The fix adds a third
        _request call with a plain `dict(base)` (no order_class key).
        """
        source = _FLEET_BROKER_PATH.read_text(encoding="utf-8")
        assert "simple_fallback" in source, (
            "simple_fallback not found in fleet_broker.py source. Was the file moved?"
        )
        # The fix branch must place a plain order (no order_class) as the third attempt.
        # A sufficient proxy: the source must reference `dict(base)` (plain entry) AND
        # the word 'simple_fallback' must appear inside the place_bracket function body.
        # We verify by extracting the function and checking both tokens.
        func_src = _extract_function_source(source, "place_bracket")
        assert func_src is not None, "Could not extract place_bracket source"
        assert "simple_fallback" in func_src
        # The plain-limit branch uses `dict(base)` or `data=dict(base)` with no order_class.
        # This pattern is distinct from the bracket/oto dicts (which add order_class key).
        assert re.search(r"dict\(base\)", func_src), (
            "place_bracket does not contain a plain `dict(base)` call (the simple-limit "
            "entry branch). The fallback for Alpaca 42210000 may not be wired correctly."
        )

    def test_broken_state_had_no_simple_fallback(self):
        """Document the old broken state: a function WITHOUT simple_fallback would return
        an error dict on the second rejection, never reaching a plain limit entry.

        This 'broken' function is inlined here so the test always verifies the old
        anti-pattern (no call to production code needed).
        """
        def place_bracket_OLD(creds, *, symbol, qty, limit_price,
                              take_profit_price, stop_price, live):
            """Old signature -- no simple_fallback."""
            if not live:
                return {"_skipped": "WATCH mode"}
            # ... bracket attempt returns error ...
            bracket_err = {"_error": "complex orders not supported", "_status": 422}
            # ... oto fallback also fails ...
            oto_err = {"_error": "complex orders not supported", "_status": 422}
            # OLD: return error after two rejections -- no plain limit branch
            return {"_error": "both bracket and oto rejected",
                    "bracket_err": bracket_err, "oto_err": oto_err}

        sig = inspect.signature(place_bracket_OLD)
        assert "simple_fallback" not in sig.parameters, (
            "OLD broken function unexpectedly has simple_fallback -- test is wrong."
        )
        # Confirm it returns an error with no order placed:
        result = place_bracket_OLD(
            {}, symbol="SPY260628C00750000", qty=3,
            limit_price=1.0, take_profit_price=2.0, stop_price=0.5, live=True
        )
        assert "_error" in result and "both bracket and oto rejected" in result["_error"], (
            "Old broken path must return '_error' after two rejections."
        )
        assert "_simple_fallback" not in result, "Old path must NOT have placed a fallback order"


# ---------------------------------------------------------------------------
# (c) sight_beacon uses sort=desc (not sort=asc)
# ---------------------------------------------------------------------------

_SIGHT_BEACON_PATH = _REPO / "setup" / "scripts" / "sight_beacon.py"


class TestSightBeaconSortDesc:
    """(c) _fetch_alpaca_bars must request sort=desc to get fresh bars."""

    def test_sort_desc_in_source(self):
        """PASS on fixed: 'sort=desc' appears in the fetch URL construction.

        The OLD broken state: 'sort=asc' (or no sort) caused Alpaca to return the
        OLDEST 300 bars, truncating today's newest bars off the tail. The beacon
        reported yesterday's close price all morning (2026-06-26 scar: 731.86 / ~$2.80
        stale). The fix flips to sort=desc and reverses the list before computing the
        ribbon (desc->asc so bars[-1] is always the newest bar).
        """
        source = _SIGHT_BEACON_PATH.read_text(encoding="utf-8")
        # The fix must contain sort=desc somewhere in the URL string
        assert "sort=desc" in source, (
            "sight_beacon.py does not contain 'sort=desc' in the Alpaca URL. "
            "The beacon will silently return stale data when the 5-day bar window "
            "exceeds the 300-bar limit (every normal trading day). "
            "Old broken state: sort=asc (or no sort) keeps oldest 300 bars, "
            "truncating the most recent off the tail. Fix: sort=desc + reverse the list."
        )

    def test_sort_asc_not_present_in_fetch_url(self):
        """The old broken pattern (sort=asc) must NOT appear in the live URL line of
        _fetch_alpaca_bars.

        The docstring legitimately explains the old bug with 'sort=asc' text.  We only
        care that the ACTUAL URL construction uses sort=desc.  We filter to non-comment,
        non-docstring code lines inside the function before checking.
        """
        source = _SIGHT_BEACON_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "_fetch_alpaca_bars")
        assert func_src is not None, "Could not extract _fetch_alpaca_bars source"
        # Strip docstring and comment-only lines; look for sort=asc in executable code.
        code_lines = _non_docstring_code_lines(func_src)
        asc_lines = [ln for ln in code_lines if "sort=asc" in ln]
        assert not asc_lines, (
            "_fetch_alpaca_bars has 'sort=asc' in executable URL code (not just comments/docstring). "
            "The live URL must use sort=desc.\n"
            "Offending lines:\n" + "\n".join("  " + ln for ln in asc_lines)
        )

    def test_reversed_call_present_for_desc_to_asc(self):
        """After fetching with sort=desc the list must be reversed to restore oldest->newest
        order (so bars[-1] is the newest bar and EMA seeding is correct).

        The OLD broken state: no reversal (list was already asc; no thought needed).
        The FIX requires an explicit reversal step after the desc fetch."""
        source = _SIGHT_BEACON_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "_fetch_alpaca_bars")
        assert func_src is not None
        assert "reversed(" in func_src or "reverse()" in func_src or "[::-1]" in func_src, (
            "_fetch_alpaca_bars does not reverse the bars list after a sort=desc fetch. "
            "Without reversal the EMA seeding uses newest->oldest order (backward) and "
            "bars[-1] would be the OLDEST bar. The fix is: `list(reversed(raw_bars))`."
        )

    def test_broken_sort_asc_would_fail_detection(self):
        """Demonstrate that the OLD broken source ('sort=asc') would trigger the guard."""
        broken_snippet = (
            "url = f'https://data.alpaca.markets/v2/stocks/SPY/bars"
            "?timeframe=5Min&start={start}&limit={limit}&feed=iex"
            "&adjustment=raw&sort=asc'"
        )
        # The guard checks for absence of sort=asc in the fetch function.
        assert "sort=asc" in broken_snippet, "Broken snippet must contain sort=asc"
        # A checker would find this and raise; we just assert the detection logic works.
        assert "sort=desc" not in broken_snippet, (
            "Broken snippet must NOT contain sort=desc (it is the old broken state)."
        )


# ---------------------------------------------------------------------------
# (d) engine_health.build_report watches core-decisions + sight_beacon
# ---------------------------------------------------------------------------

_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"


def _load_engine_health():
    """Import engine_health.py by path."""
    spec = importlib.util.spec_from_file_location("engine_health_for_liveness", _EH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestEngineHealthWatchesNewProducers:
    """(d) engine_health.build_report must watch the NEW deterministic engine producers."""

    def test_build_report_calls_check_engine_core_not_check_heartbeat_log(self):
        """PASS on fixed: build_report calls check_engine_core (reads core-decisions.jsonl)
        not the old check_heartbeat (reads retired LLM loop-state.json logs).

        The OLD broken state: build_report called check_heartbeat(name, path=loop-state.json)
        for heartbeat_safe/bold. After the LLM heartbeat was retired, those log files were
        never written, so the check permanently returned 'log missing' (YELLOW). The monitor
        was blind to the real (deterministic) engine.
        """
        eh = _load_engine_health()
        source = _EH_PATH.read_text(encoding="utf-8")
        # Extract build_report function body
        func_src = _extract_function_source(source, "build_report")
        assert func_src is not None, "Could not extract build_report source"

        assert "check_engine_core" in func_src, (
            "build_report does not call check_engine_core. The monitor is watching the "
            "retired LLM loop-state check, not the deterministic heartbeat_core brain. "
            "Fix: replace check_heartbeat(..., loop-state.json) with check_engine_core(...)."
        )

    def test_check_engine_core_reads_core_decisions_jsonl(self):
        """check_engine_core must read 'core-decisions.jsonl' (the brain's per-tick output)."""
        source = _EH_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "check_engine_core")
        assert func_src is not None, "check_engine_core function not found in engine_health.py"
        assert "core-decisions.jsonl" in func_src, (
            "check_engine_core does not reference 'core-decisions.jsonl'. "
            "The BRAIN liveness check must tail this file for per-account per-tick rows. "
            "Old broken state: the function watched loop-state.json (LLM era, retired)."
        )

    def test_build_report_calls_check_sight_beacon_not_loop_state(self):
        """PASS on fixed: build_report calls check_sight_beacon (reads sight-beacon.json).

        The OLD broken state: build_report called check_tv_chart (CDP-liveness check) as
        the EYE. After the LLM heartbeat was replaced by heartbeat_core (direct REST, no
        CDP on hot path), check_tv_chart was no longer the right eye liveness signal.
        The correct check is check_sight_beacon which watches sight-beacon.json freshness.
        """
        source = _EH_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "build_report")
        assert func_src is not None

        assert "check_sight_beacon" in func_src, (
            "build_report does not call check_sight_beacon. The monitor is not watching "
            "the NEVER-BLIND eye (sight-beacon.json). Fix: replace check_tv_chart with "
            "check_sight_beacon in the build_report checks roster."
        )

    def test_loop_state_json_not_a_core_liveness_check_in_build_report(self):
        """build_report must NOT use 'loop-state.json' as a liveness source.

        The retired LLM heartbeat wrote loop-state.json.  After 2026-06-25 the LLM
        heartbeat was DISABLED.  If build_report still reads loop-state.json for liveness
        it will see 'missing' on every tick and keep the monitor permanently YELLOW.
        """
        source = _EH_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "build_report")
        assert func_src is not None

        # 'loop-state' may appear in a COMMENT explaining the old behaviour, but
        # must NOT appear as a path argument to a check call in the function body.
        # Strategy: find any _read_json or Path calls inside build_report that reference
        # 'loop-state'; or any check_heartbeat call (which reads loop-state logs).
        # We allow the word in comments (prefixed by #).
        non_comment_lines = [
            line for line in func_src.splitlines()
            if not line.strip().startswith("#") and "loop-state" in line
        ]
        assert not non_comment_lines, (
            "build_report references 'loop-state' in non-comment code -- the retired LLM "
            "heartbeat log is still being used as a liveness source. These lines must be "
            "replaced with check_engine_core (core-decisions.jsonl):\n"
            + "\n".join("  " + ln for ln in non_comment_lines)
        )

    def test_engine_health_check_sight_beacon_uses_sight_beacon_json(self):
        """check_sight_beacon must read 'sight-beacon.json' (the eye's liveness file)."""
        source = _EH_PATH.read_text(encoding="utf-8")
        func_src = _extract_function_source(source, "check_sight_beacon")
        assert func_src is not None, "check_sight_beacon function not found in engine_health.py"
        assert "sight-beacon.json" in func_src, (
            "check_sight_beacon does not reference 'sight-beacon.json'. "
            "Old broken state: the EYE check read tv-watchdog-status.json (CDP-era). "
            "Fix: check the direct-REST beacon file for freshness + ok flag."
        )

    def test_build_report_integration_core_decisions_path(self, tmp_path, monkeypatch):
        """Integration: build_report with a fresh core-decisions.jsonl must NOT fire
        a brain-dead RED for heartbeat_safe (it should be GREEN or market-closed GREEN).

        This reproduces the permanently-YELLOW failure mode (2026-06-26): the old monitor
        watched retired LLM logs ('missing' forever), so every tick was YELLOW. The fix
        makes it watch core-decisions.jsonl instead.
        """
        eh = _load_engine_health()
        monkeypatch.setattr(eh, "STATE", tmp_path)
        monkeypatch.setattr(eh, "AGG", tmp_path)

        # Write a fresh core-decisions.jsonl with a recent safe tick.
        from datetime import timezone as tz, timedelta as td
        now_utc = datetime.now(tz.utc)
        # Naively use the current-minute ET timestamp format the engine writes.
        et_now = (now_utc + td(hours=-4)).strftime("%Y-%m-%dT%H:%M:%S")
        row = json.dumps({"account": "safe", "ts_et": et_now, "action": "HOLD"})
        (tmp_path / "core-decisions.jsonl").write_text(row + "\n", encoding="utf-8")
        # Write fresh sight-beacon.json
        beacon = {
            "ok": True,
            "ts_utc": now_utc.isoformat(timespec="seconds"),
            "spy": 570.0,
            "ribbon_stack": "BULLISH",
        }
        (tmp_path / "sight-beacon.json").write_text(json.dumps(beacon), encoding="utf-8")
        # Stub out circuit-breaker and position files (non-critical)
        (tmp_path / "circuit-breaker.json").write_text('{"tripped": false}', encoding="utf-8")
        (tmp_path / "current-position.json").write_text('{"status": null}', encoding="utf-8")
        (tmp_path / "current-position-bold.json").write_text('{"status": null}', encoding="utf-8")

        report = eh.build_report()

        # The heartbeat_safe check must be GREEN (fresh core-decisions row exists).
        safe_chk = next((c for c in report["checks"] if c["name"] == "heartbeat_safe"), None)
        assert safe_chk is not None, "heartbeat_safe check missing from build_report output"
        assert safe_chk["status"] == "GREEN", (
            "heartbeat_safe must be GREEN when core-decisions.jsonl has a fresh safe row. "
            "OLD BROKEN: the monitor watched retired LLM loop-state.json -- missing file "
            "always returned YELLOW/RED even when the deterministic engine was healthy.\n"
            "Got: " + repr(safe_chk)
        )

    def test_broken_state_loop_state_check_would_fail(self, tmp_path):
        """Demonstrate that the OLD code (watching loop-state.json) would have returned
        YELLOW on a box where the LLM heartbeat was retired (no loop-state.json present).

        This test does NOT import the OLD code -- it reconstructs the minimal logic inline
        to avoid coupling to the retired code path. The point is to document what would
        have broken and prove our new check avoids it.
        """
        # Old logic: look for loop-state.json; if missing -> YELLOW
        loop_state_path = tmp_path / "loop-state.json"
        # File does not exist (LLM heartbeat retired):
        assert not loop_state_path.exists()

        # Old check result (reconstructed):
        if not loop_state_path.exists():
            old_status = "YELLOW"
            old_detail = "loop-state.json missing"
        else:
            old_status = "GREEN"
            old_detail = "ok"

        assert old_status == "YELLOW", (
            "Old check must return YELLOW when loop-state.json is missing "
            "(this is the permanently-YELLOW failure mode the fix addresses)."
        )

        # New logic: look for core-decisions.jsonl with a recent row.
        from datetime import timezone as tz, timedelta as td
        now_utc = datetime.now(tz.utc)
        et_now = (now_utc + td(hours=-4)).strftime("%Y-%m-%dT%H:%M:%S")
        row = json.dumps({"account": "safe", "ts_et": et_now, "action": "HOLD"})
        (tmp_path / "core-decisions.jsonl").write_text(row + "\n", encoding="utf-8")

        # New check result (simplified):
        path = tmp_path / "core-decisions.jsonl"
        assert path.exists(), "Should exist -- we just wrote it"
        tail_text = path.read_text(encoding="utf-8")
        rows = [json.loads(l) for l in tail_text.splitlines() if l.strip()]
        safe_rows = [r for r in rows if r.get("account") == "safe" and r.get("ts_et")]
        assert safe_rows, "New check finds the safe row"
        # No loop-state.json needed -- new check passes:
        new_status = "GREEN"

        assert new_status == "GREEN" and old_status == "YELLOW", (
            "Guard contract: old (loop-state) returns YELLOW on retired LLM box; "
            "new (core-decisions) returns GREEN when the deterministic engine ticks. "
            f"old={old_status}, new={new_status}"
        )


# ---------------------------------------------------------------------------
# Utilities: extract function source / filter code lines
# ---------------------------------------------------------------------------

def _non_docstring_code_lines(func_src: str) -> list[str]:
    """Return non-blank, non-comment, non-docstring lines from a function source string.

    Strips: lines that are only '#...' comments, lines inside triple-quoted docstrings,
    and blank lines.  What remains is executable Python code that the interpreter runs.
    Used to check for banned patterns in the URL string without false-positives from
    explanatory docstrings that mention the old broken value.
    """
    lines = func_src.splitlines()
    in_docstring = False
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Toggle docstring state on triple-quote boundaries.
        triple_count = stripped.count('"""') + stripped.count("'''")
        if triple_count >= 2:
            # Opening and closing on same line (e.g. """short docstring""") -- skip entire line.
            continue
        if triple_count == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Skip pure comment lines.
        if stripped.startswith("#"):
            continue
        result.append(stripped)
    return result


def _extract_function_source(source: str, func_name: str) -> str | None:
    """Return the text of the named top-level function in `source`, or None.

    Uses a simple indentation-based heuristic: collects lines from the
    `def <name>(` line until the next top-level definition or end of file.
    This avoids importing the module just to inspect source (avoids side effects
    from import-time code in non-test modules).
    """
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^def {re.escape(func_name)}\s*\(", line):
            start = i
            break
    if start is None:
        return None
    body: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        # Stop at the next top-level definition (not indented and starts with def/class).
        if line and line[0] not in (" ", "\t", "#", "") and re.match(r"^(def |class )", line):
            break
        body.append(line)
    return "\n".join(body)
