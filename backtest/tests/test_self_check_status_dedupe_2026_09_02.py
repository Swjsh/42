"""self_check must not re-append an UNCHANGED problem set to STATUS.md every 30 minutes.

THE BUG (queue.md STATUS-BROKEN-BLOCKS-DRAIN, root-caused 2026-09-02). The STATUS.md append
in `_alert` was unconditional, and the Discord dedupe next to it keyed on
`" | ".join(result["problems"])` -- the FULL problem text. Half of self_check's messages
embed a running count:

    RUN-CMD-HIDDEN MASKED EXIT: run-*.ps1 shows 15 real non-zero exit(s) ...

so the key changed on nearly every fire. Both consumers failed together: STATUS.md grew a new
`### BROKEN: self-check` block every cadence tick (four blocks inside 23 minutes on
2026-09-02, differing ONLY in 13 -> 15 -> 17), and the 6-hour Discord suppression window
never matched, so an unresolved problem re-pinged all day. Nobody reads a surface that
repeats itself, which is how CHART-DRAWING STALE sat unowned since 2026-06-29.

WHAT MUST NOT REGRESS IN THE OTHER DIRECTION. A dedupe that swallows a REAL change is worse
than the noise it replaces: a newly-RED task, a new failing arm, or a new .ps1 must still
append and still ping. Half these tests exist to prove the suppression is narrow.
"""

from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"


@pytest.fixture(scope="module")
def sc():
    spec = importlib.util.spec_from_file_location("self_check_g", SCRIPTS / "self_check.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["self_check_g"] = m
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------------------
# The signature function itself -- the whole fix lives here.
# ---------------------------------------------------------------------------------------

def test_a_running_counter_does_not_change_the_signature(sc):
    """The exact three STATUS.md blocks from 2026-09-02, verbatim shape."""
    a = ["RUN-CMD-HIDDEN MASKED EXIT: run-*.ps1 shows 13 real non-zero exit(s) in 24h"]
    b = ["RUN-CMD-HIDDEN MASKED EXIT: run-*.ps1 shows 15 real non-zero exit(s) in 24h"]
    c = ["RUN-CMD-HIDDEN MASKED EXIT: run-*.ps1 shows 17 real non-zero exit(s) in 24h"]
    assert (sc._problem_set_signature(a) == sc._problem_set_signature(b)
            == sc._problem_set_signature(c))


def test_a_decimal_age_does_not_change_the_signature(sc):
    assert (sc._problem_set_signature(["QUOTE-RECORDER DEGRADED: stale for 3.2h"])
            == sc._problem_set_signature(["QUOTE-RECORDER DEGRADED: stale for 11.9h"]))


def test_ordering_does_not_change_the_signature(sc):
    """Checks run in dict order; a reshuffle is not a new problem."""
    assert (sc._problem_set_signature(["A RED: x", "B RED: y"])
            == sc._problem_set_signature(["B RED: y", "A RED: x"]))


# --- the narrowness half: these MUST still read as changed ------------------------------

def test_a_different_arm_is_a_different_problem(sc):
    """safe-2 vs safe-3 differ only in a digit. Collapsing them would hide a whole arm
    going down behind another arm's identical message -- the regression this guards."""
    assert (sc._problem_set_signature(["FLEET RED: safe-2 has no fills"])
            != sc._problem_set_signature(["FLEET RED: safe-3 has no fills"]))


def test_a_new_problem_joining_the_set_changes_the_signature(sc):
    one = ["RUN-CMD-HIDDEN MASKED EXIT: 15 exits"]
    two = ["RUN-CMD-HIDDEN MASKED EXIT: 17 exits", "FUTURES-HEALTH RED: broker unreachable"]
    assert sc._problem_set_signature(one) != sc._problem_set_signature(two)


def test_a_problem_clearing_changes_the_signature(sc):
    assert (sc._problem_set_signature(["A RED: x", "B RED: y"])
            != sc._problem_set_signature(["A RED: x"]))


def test_different_named_tasks_change_the_signature(sc):
    """TASK-STALENESS names the offending tasks; a different task is a different problem."""
    assert (sc._problem_set_signature(["TASK-STALENESS RED: Gamma_GuardsFull"])
            != sc._problem_set_signature(["TASK-STALENESS RED: Gamma_GuardsNightly"]))


# ---------------------------------------------------------------------------------------
# End-to-end through _alert, against a real temp STATUS.md.
# ---------------------------------------------------------------------------------------

def _run_alert(sc, monkeypatch, tmp_path, problems, ts, prev_alert):
    status = tmp_path / "STATUS.md"
    if not status.exists():
        status.write_text("# STATUS\n", encoding="utf-8")
    monkeypatch.setattr(sc, "STATUS_MD", status)
    monkeypatch.setattr(sc, "LAST", tmp_path / "last.json")
    monkeypatch.setattr(sc, "DISCORD_OUTBOX", tmp_path / "outbox.jsonl")
    result = {"ts_et": ts, "verdict": "BROKEN", "problems": problems}
    sc._alert(result, prev_alert)
    return status.read_text(encoding="utf-8"), result


def _carry(res):
    return {"_status_sig": res["_status_sig"], "_status_at": res["_status_at"]}


def test_identical_set_thirty_minutes_later_does_not_re_append(sc, monkeypatch, tmp_path):
    """The literal reported bug: the 30-minute cadence tick."""
    txt, res = _run_alert(sc, monkeypatch, tmp_path,
                          ["RUN-CMD-HIDDEN MASKED EXIT: shows 13 real non-zero exit(s)"],
                          "2026-09-02T06:28:00", {})
    assert txt.count("### BROKEN: self-check") == 1

    txt, _ = _run_alert(sc, monkeypatch, tmp_path,
                        ["RUN-CMD-HIDDEN MASKED EXIT: shows 15 real non-zero exit(s)"],
                        "2026-09-02T06:58:00", _carry(res))
    assert txt.count("### BROKEN: self-check") == 1, (
        "the counter bumped 13 -> 15 and STATUS.md grew a second identical block -- this is "
        "exactly the reported defect"
    )


def test_a_changed_set_still_appends(sc, monkeypatch, tmp_path):
    """The inverse regression. A dedupe that hides a NEW problem is worse than the noise."""
    txt, res = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], "2026-09-02T06:28:00", {})
    assert txt.count("### BROKEN: self-check") == 1

    txt, _ = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x", "FUTURES-HEALTH RED: down"],
                        "2026-09-02T06:58:00", _carry(res))
    assert txt.count("### BROKEN: self-check") == 2, (
        "a genuinely new problem was SWALLOWED by the dedupe -- worse than the bug it fixed"
    )
    assert "FUTURES-HEALTH RED" in txt


def test_the_same_set_still_re_appends_after_the_suppress_window(sc, monkeypatch, tmp_path):
    """Never total silence: an unresolved problem resurfaces every 6h (OP-25 fail-loud)."""
    txt, res = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], "2026-09-02T00:00:00", {})
    later = (dt.datetime.fromisoformat("2026-09-02T00:00:00")
             + dt.timedelta(minutes=sc.SELF_CHECK_REPEAT_SUPPRESS_MIN + 1)).isoformat()
    txt, _ = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], later, _carry(res))
    assert txt.count("### BROKEN: self-check") == 2


def test_an_unparseable_stamp_never_silently_suppresses(sc, monkeypatch, tmp_path):
    """Fail LOUD, not quiet: a corrupt state file must not mute the surface."""
    txt, _ = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], "2026-09-02T06:28:00",
                        {"_status_sig": sc._problem_set_signature(["A RED: x"]),
                         "_status_at": "not-a-timestamp"})
    assert txt.count("### BROKEN: self-check") == 1


def test_status_state_is_carried_forward_when_suppressed(sc, monkeypatch, tmp_path):
    """If the suppressed branch dropped _status_at, the NEXT run would see no stamp, treat
    it as stale, and append -- the bug would return with one extra step."""
    _, res = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], "2026-09-02T06:28:00", {})
    _, res2 = _run_alert(sc, monkeypatch, tmp_path, ["A RED: x"], "2026-09-02T06:58:00",
                         _carry(res))
    assert res2["_status_at"] == res["_status_at"] == "2026-09-02T06:28:00"
    assert res2["_status_sig"] == res["_status_sig"]


def test_run_snapshots_the_status_keys_before_clobbering_last(sc):
    """run() writes LAST before calling _alert. If the snapshot does not carry the _status_*
    keys forward, prev_alert reads back empty every time and the dedupe can never match --
    the identical mechanism that broke the Discord dedupe on 2026-08-17."""
    src = (SCRIPTS / "self_check.py").read_text(encoding="utf-8")
    snap = src.split("prev_alert: dict = {}", 1)[1].split("LAST.write_text", 1)[0]
    assert '"_status_sig"' in snap and '"_status_at"' in snap


def test_discord_dedupe_uses_the_same_identity(sc):
    """The ping path and the STATUS path must not drift apart -- one bug, one key.

    AST, not a substring: this asks WHAT `sig` is assigned, and the docstrings in this file
    and in self_check itself both quote the old expression in prose. See
    automation/overnight/_lesson-inbox/2026-09-02-string-search-cannot-answer-code-questions.md
    """
    src = (SCRIPTS / "self_check.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_alert")
    sig_assign = next(n for n in ast.walk(fn)
                      if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "sig" for t in n.targets))
    assert (isinstance(sig_assign.value, ast.Call)
            and getattr(sig_assign.value.func, "id", "") == "_problem_set_signature"), (
        "the Discord dedupe key is no longer the shared identity function; it used to be "
        "a full-text join, and that is what defeated the 6h suppression window"
    )
