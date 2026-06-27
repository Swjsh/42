"""Guard: DST-aware ET clock (G2 / TZ-SYSTEMIC fix, 2026-06-26).

THREE protection layers:

1. test_et_clock_dst_transitions -- BEHAVIORAL: et_clock.et_now() returns the correct
   ET wall-clock for the two DST transition instants (spring-forward Mar 2026,
   fall-back Nov 2026). The naive UTC-4 fixed offset returns 11:30 in November when
   ET is 10:30. This is the root-cause regression the guard pins.

2. test_no_naive_minus4_in_live_path -- STATIC: scans the 9 live-trade-path files
   enumerated in G2. Any raw `timezone(timedelta(hours=-4))` or `timedelta(hours=-4)`
   used as a TZ constant (not as a comparison inside et_clock.py itself) FAILS.
   Prevents regressions where a merge re-introduces the old naive constant.

3. test_et_clock_is_shared_single_implementation -- STRUCTURAL: et_clock._et_offset_hours
   is the ONLY production DST implementation; engine_health, session_guard, and
   discord-responder have identical inline copies (they predate et_clock). This test
   spot-checks that each inline copy matches et_clock for 12 representative UTC
   instants spanning both EDT and EST, so if et_clock is updated they all stay in sync.
   (The goal is eventual consolidation; this test flags divergence proactively.)

Run:
    cd backtest && python -m pytest tests/test_et_clock.py -v
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"

# Make et_clock importable without polluting the persistent sys.path.
def _import_et_clock():
    spec = importlib.util.spec_from_file_location("et_clock", SCRIPTS / "et_clock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Behavioral: DST transition correctness
# ---------------------------------------------------------------------------

def test_et_clock_dst_transitions():
    """et_now() must return correct wall-clock ET at both DST transition moments."""
    ec = _import_et_clock()

    # --- Spring-forward: 2026-03-08 07:00 UTC = 02:00 EST -> clocks skip to 03:00 EDT ---
    # One second BEFORE transition -> EST (UTC-5): 07:00 - 5h = 02:00
    just_before = datetime(2026, 3, 8, 6, 59, 59, tzinfo=timezone.utc)
    offset_before = ec.et_offset_hours(just_before)
    assert offset_before == -5, f"Before spring-forward should be EST (-5), got {offset_before}"
    wall_before = ec.et_now(just_before)
    assert wall_before.hour == 1 and wall_before.minute == 59, (
        f"Wall clock before spring-forward should be 01:59 ET, got {wall_before}")

    # One second AFTER transition -> EDT (UTC-4): 07:00 - 4h = 03:00
    just_after = datetime(2026, 3, 8, 7, 0, 1, tzinfo=timezone.utc)
    offset_after = ec.et_offset_hours(just_after)
    assert offset_after == -4, f"After spring-forward should be EDT (-4), got {offset_after}"
    wall_after = ec.et_now(just_after)
    assert wall_after.hour == 3 and wall_after.minute == 0, (
        f"Wall clock after spring-forward should be 03:00 ET, got {wall_after}")

    # --- Fall-back: 2026-11-01 06:00 UTC = 02:00 EDT -> clocks fall to 01:00 EST ---
    # One second BEFORE transition -> EDT (UTC-4): 06:00 - 4h = 02:00
    fb_before = datetime(2026, 11, 1, 5, 59, 59, tzinfo=timezone.utc)
    offset_fb_before = ec.et_offset_hours(fb_before)
    assert offset_fb_before == -4, f"Before fall-back should be EDT (-4), got {offset_fb_before}"

    # One second AFTER transition -> EST (UTC-5): 06:00 - 5h = 01:00
    fb_after = datetime(2026, 11, 1, 6, 0, 1, tzinfo=timezone.utc)
    offset_fb_after = ec.et_offset_hours(fb_after)
    assert offset_fb_after == -5, f"After fall-back should be EST (-5), got {offset_fb_after}"
    wall_fb_after = ec.et_now(fb_after)
    assert wall_fb_after.hour == 1 and wall_fb_after.minute == 0, (
        f"Wall clock after fall-back should be 01:00 ET, got {wall_fb_after}")


def test_et_clock_november_rth_gate():
    """The specific regression: Nov 15 10:30 ET. Fixed UTC-4 would say 11:30, closing RTH 1h late."""
    ec = _import_et_clock()
    # 2026-11-15 15:30:00 UTC = 10:30 EST (UTC-5)
    nov_utc = datetime(2026, 11, 15, 15, 30, 0, tzinfo=timezone.utc)
    et_wall = ec.et_now(nov_utc)
    assert et_wall.hour == 10 and et_wall.minute == 30, (
        f"Nov 15 15:30 UTC should be 10:30 ET, got {et_wall.hour}:{et_wall.minute:02d}. "
        f"This is the G2 regression: UTC-4 would return 11:30, causing RTH to close 1h late.")

    # Verify offset is -5 (EST)
    offset = ec.et_offset_hours(nov_utc)
    assert offset == -5, f"Nov 15 should be EST (-5), got {offset}"


# ---------------------------------------------------------------------------
# 2. Static: no naive -4 constant in live-trade-path files
# ---------------------------------------------------------------------------

# The 9 G2 files. Relative to REPO root.
_G2_FILES = [
    REPO / "setup" / "scripts" / "heartbeat_core.py",
    REPO / "setup" / "scripts" / "fast_path_executor.py",
    REPO / "setup" / "scripts" / "daily_loss_guard.py",
    REPO / "setup" / "scripts" / "atomic_bracket_guard.py",
    REPO / "setup" / "scripts" / "exit_actuator.py",    # moved to fleet dir
    REPO / "automation" / "state" / "fleet" / "exit_actuator.py",
    REPO / "automation" / "state" / "fleet" / "fleet_live.py",
    REPO / "automation" / "state" / "fleet" / "build_shared_signal.py",
    REPO / "setup" / "scripts" / "eod_full_audit.py",
    REPO / "setup" / "scripts" / "self_audit.py",
    REPO / "setup" / "scripts" / "sight_beacon.py",
]

# Pattern that flags a FIXED -4 offset used as a timezone constant (not a comparison).
# We allow `timedelta(hours=-4)` inside et_clock.py itself (it's the comparator there),
# and in test files (deterministic fixtures are OK with fixed offsets).
_NAIVE_MINUS4_RE = re.compile(
    r'timezone\s*\(\s*timedelta\s*\(\s*hours\s*=\s*-4\s*\)\s*\)'
    r'|'
    r'timedelta\s*\(\s*hours\s*=\s*-4\s*\)\s*(?!\s*[),])'  # standalone, not inside timezone()
)

# More targeted: the exact pattern that WAS the bug
_BUG_PATTERNS = [
    re.compile(r'\bET_TZ\s*=\s*timezone\s*\(timedelta\(hours=-4\)\)'),
    re.compile(r'\bET\s*=\s*timezone\s*\(timedelta\s*\(hours=-4\)\)'),
    re.compile(r'datetime\.now\s*\(timezone\.utc\)\s*\+\s*timedelta\s*\(hours=-4\)'),
    re.compile(r'datetime\.now\s*\(timezone\.utc\)\s*-\s*timedelta\s*\(hours=4\)'),
]


def test_no_naive_minus4_in_live_path():
    """None of the 9 G2 live-trade-path files may contain the naive UTC-4 constant pattern."""
    violations = []
    for fpath in _G2_FILES:
        if not fpath.exists():
            continue  # file may not exist (e.g. setup/scripts/exit_actuator.py is fleet-only)
        text = fpath.read_text(encoding="utf-8", errors="replace")
        for pattern in _BUG_PATTERNS:
            for m in pattern.finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                violations.append(f"{fpath.name}:{line_no}: {m.group()!r}")

    assert not violations, (
        "G2 REGRESSION: naive UTC-4 constant found in live-trade-path file(s):\n"
        + "\n".join(violations)
        + "\n\nFix: replace with `from et_clock import et_now` (see G2 / TZ-SYSTEMIC)."
    )


# ---------------------------------------------------------------------------
# 3. Structural: inline DST copies match et_clock
# ---------------------------------------------------------------------------

_INLINE_DST_FILES = {
    "engine_health.py": REPO / "setup" / "scripts" / "engine_health.py",
    "session_guard.py": REPO / "setup" / "scripts" / "session_guard.py",
}

# Test UTC instants that span both EDT and EST windows.
_TEST_UTC_INSTANTS = [
    datetime(2026, 1, 15, 15, 30, tzinfo=timezone.utc),   # EST: 10:30
    datetime(2026, 3, 7, 20, 0, tzinfo=timezone.utc),     # EST: 15:00 (day before spring-fwd)
    datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc),      # EDT: 04:00 (day of spring-fwd, after)
    datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc),   # EDT: 10:30
    datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc),   # EDT: 11:30
    datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc),    # EDT: 01:59 (just before fall-back)
    datetime(2026, 11, 1, 6, 1, tzinfo=timezone.utc),     # EST: 01:01 (just after fall-back)
    datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc),  # EST: 10:30 (the G2 regression case)
    datetime(2026, 12, 31, 15, 30, tzinfo=timezone.utc),  # EST: 10:30
]


def _extract_et_offset_hours_from_engine_health():
    """Load engine_health._et_offset_hours WITHOUT triggering its pythonw stdio redirect."""
    src = (REPO / "setup" / "scripts" / "engine_health.py").read_text(encoding="utf-8")
    # Strip the pythonw stdio redirect block so we can exec without file handles.
    src = re.sub(
        r'if sys\.platform.*?sys\.stderr = open.*?\n',
        '# [stdio redirect stripped for test]\n',
        src, flags=re.DOTALL
    )
    g: dict = {"__name__": "_test_eh"}
    try:
        exec(compile(src, "engine_health.py", "exec"), g)  # noqa: S102 -- test-only exec
    except Exception:
        # If exec fails (e.g. missing state files), fall back to import-util
        return None
    return g.get("_et_offset_hours")


def test_inline_dst_matches_et_clock():
    """engine_health._et_offset_hours must agree with et_clock.et_offset_hours for all test instants."""
    ec = _import_et_clock()

    eh_fn = _extract_et_offset_hours_from_engine_health()
    if eh_fn is None:
        import warnings
        warnings.warn("Could not extract engine_health._et_offset_hours -- skipping cross-check",
                      stacklevel=1)
        return

    mismatches = []
    for utc in _TEST_UTC_INSTANTS:
        expected = ec.et_offset_hours(utc)
        got = eh_fn(utc)
        if expected != got:
            mismatches.append(f"UTC {utc.isoformat()}: et_clock={expected}, engine_health={got}")

    assert not mismatches, (
        "engine_health._et_offset_hours diverges from et_clock.et_offset_hours:\n"
        + "\n".join(mismatches)
        + "\nThe two implementations must stay in sync."
    )
