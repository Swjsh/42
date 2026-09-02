"""No non-repeating task may have its ONLY trigger inside the quiet-mode blackout.

WHY THIS IS A TEST AND NOT A ONE-OFF SWEEP. On 2026-08-26 a sweep re-timed five tasks out of
the blackout -- GateRecency, OosCheck, LicenseMonitor, KalshiAuto, McpDailyAudit -- each
registry row saying "the 16:00-08:00 blackout meant it fired never". `Gamma_Conductor` was
missed by that sweep and stayed stranded for a week, its first daily fire at 20:30 ET inside
an 18:00-23:00 ET blackout. The STATUS archive shows the cost: 3 conductor entries at hour
T20 against 5 at T01 and 7 at T05, i.e. the autonomous improvement loop ran at roughly
two-thirds cadence and nothing said so.

A sweep that fixes a class should be checked against the whole class. A sweep cannot do
that; a test can, on every run.

THE FAILURE MODE THIS CATCHES: a task registered inside the blackout is DISABLED at its own
trigger time, and Windows' StartWhenAvailable cannot recover a fire missed while the task
was Disabled -- so the run is simply lost, every night, silently. Repeaters are exempt
because they self-heal on their next tick; ESSENTIAL tasks are exempt because quiet mode
never disables them.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


qm = _load("quiet_mode_g", SCRIPTS / "quiet_mode.py")
sts = _load("scheduled_task_staleness_g", SCRIPTS / "scheduled_task_staleness.py")

# This box runs Mountain time; Task Scheduler StartBoundary is local. ET = local + 2.
MT_TO_ET_HOURS = 2


def _et_probe(hh: int, mm: int) -> dt.datetime:
    return dt.datetime(2026, 9, 2, (hh + MT_TO_ET_HOURS) % 24, mm, tzinfo=qm.ET)


# ---------------------------------------------------------------------------------------
# The predicate must be able to FIRE. A sweep that finds nothing and a sweep that cannot
# find anything look identical from the outside (C14).
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("mt,expect_flagged", [
    ("18:30", True),    # Gamma_Conductor's OLD time -- the case that motivated this
    ("16:05", True),    # 18:05 ET, just inside the window's start
    ("20:59", True),    # 22:59 ET, just inside its end
    ("22:10", False),   # the conductor's NEW time, 00:10 ET
    ("21:05", False),   # 23:05 ET, just after the window closes
    ("06:00", False),   # 08:00 ET, the LOUD band's end
])
def test_predicate_discriminates_the_window(mt, expect_flagged):
    hh, mm = (int(x) for x in mt.split(":"))
    assert qm.in_quiet_window(_et_probe(hh, mm)) is expect_flagged


# ---------------------------------------------------------------------------------------
# The live sweep.
# ---------------------------------------------------------------------------------------

def _stranded() -> list[tuple[str, str]]:
    rows = sts.query_tasks()
    if not rows:
        pytest.skip("scheduler query returned nothing (not this test's failure)")
    out = []
    for r in rows:
        if str(r.get("state", "")).lower() in ("disabled", "1"):
            continue                        # deliberately off; quiet mode is not why
        name = str(r.get("name") or "")
        if name in qm.ESSENTIAL:
            continue                        # never disabled by the blackout
        if sts.parse_iso_duration_minutes(r.get("repeat")):
            continue                        # repeaters self-heal on the next tick
        sb = r.get("startBound")
        if not isinstance(sb, str) or "T" not in sb:
            continue
        hh, mm = (int(x) for x in sb.split("T")[1][:5].split(":"))
        if qm.in_quiet_window(_et_probe(hh, mm)):
            out.append((name, f"{hh:02d}:{mm:02d} MT = {(hh + 2) % 24:02d}:{mm:02d} ET"))
    return sorted(out)


def test_no_task_is_stranded_inside_the_blackout():
    stranded = _stranded()
    assert not stranded, (
        "these non-repeating, non-ESSENTIAL tasks have their ONLY trigger inside quiet "
        "mode's blackout, so they are Disabled at their own trigger time and the fire is "
        "lost -- StartWhenAvailable cannot recover a run missed while Disabled:\n  "
        + "\n  ".join(f"{n}  ({when})" for n, when in stranded)
        + "\nEither re-time into the LOUD maintenance band (the 2026-08-26 precedent) or, "
          "if it is genuinely trading-critical, add it to quiet_mode.ESSENTIAL."
    )


def test_the_conductor_specifically_is_out_of_the_window():
    """Regression anchor for the 2026-09-02 fix. Named because it was missed once already."""
    rows = sts.query_tasks()
    if not rows:
        pytest.skip("scheduler query returned nothing")
    row = next((r for r in rows if r.get("name") == "Gamma_Conductor"), None)
    if row is None:
        pytest.skip("Gamma_Conductor not registered on this box")
    sb = row.get("startBound")
    if not isinstance(sb, str) or "T" not in sb:
        pytest.skip("no parseable StartBoundary")
    hh, mm = (int(x) for x in sb.split("T")[1][:5].split(":"))
    assert not qm.in_quiet_window(_et_probe(hh, mm)), (
        f"Gamma_Conductor's first trigger is back inside the blackout ({hh:02d}:{mm:02d} MT). "
        "It spawns Sonnet sessions with ship authority at ~$1/fire, so the fix is to re-time "
        "it, NOT to add it to ESSENTIAL."
    )
