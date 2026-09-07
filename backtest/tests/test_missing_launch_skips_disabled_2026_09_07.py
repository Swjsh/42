"""Graduated guard (2026-09-07): check_missing_launches must not flag a Disabled task.
Silent-Rig disabled 9 keepalives on 2026-09-05; the 05:45 ET TASK-OUTPUT-FRESHNESS line then
listed 3 of them as missing_launch -- a Disabled task cannot launch, so that is noise on the
Known-broken surface (OP-33 visibility)."""
import datetime as dt, importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sts", ROOT / "setup/scripts/scheduled_task_staleness.py")
sts = importlib.util.module_from_spec(spec); sys.modules["sts"] = sts; spec.loader.exec_module(sts)
ARGS = '//nologo "C:/x/run_exe_hidden.vbs" "C:/x/run_cmd_hidden.py" -- "C:/x/setup/scripts/foo_keepalive.py"'

def _row(name, state):
    return {"name": name, "state": state, "argsRaw": ARGS, "lastRun": "2026-09-06T15:00:00-04:00"}

def test_disabled_task_is_not_a_missing_launch():
    now = dt.datetime(2026, 9, 7, 5, 45, tzinfo=sts.ET); start = now - dt.timedelta(days=2)
    rows = [_row("Gamma_Foo", "Disabled"), _row("Gamma_Bar", "Ready")]
    out = sts.check_missing_launches(rows, launched=set(), window_start=start, now=now)
    names = {o["task"] for o in out}
    assert "Gamma_Foo" not in names, "Disabled task was flagged as missing_launch"
    assert "Gamma_Bar" in names, "Ready task with no relay line must still be flagged"
