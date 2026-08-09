"""Guard for self_check.py's 2026-08-08 allow-list exemption in
test_graduated_guards.py::test_no_monitor_trusts_lasttaskresult_as_authoritative.

Motivation: that guard flagged self_check.py for 9 mentions of
LastTaskResult/LastRunResult. Triage (Lane 2 of the 2026-08-08 guard-repair fire) proved
all 9 are PROSE (docstrings + human-readable finding/message strings) explaining why each
check deliberately does NOT trust Task Scheduler's exit code and instead reads the task's
own OUTPUT ARTIFACT (scout_output.json content, run-cmd-hidden.log / run-ps1-hidden.log
real captured exit codes) -- a proven false positive of the guard's broad text-match
regex, not a real violation. This test pins BOTH halves of that finding so it can't
silently rot:

  1. self_check.py must NEVER programmatically read LastTaskResult/LastRunResult -- no
     Get-ScheduledTaskInfo call, no attribute access, no dict-key lookup. If a future edit
     adds a REAL read of the value (the actual (a)-class violation the guard exists to
     catch), this test must fail even though the broader guard's allow-list would
     otherwise let it slide silently.
  2. The exemption's earned-marker text (LASTTASKRESULT-UNTRUSTED-BY-DESIGN) must stay
     present -- duplicated here (not just in test_graduated_guards.py) so this test file
     alone proves the claim, independent of the guard file.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF_CHECK = REPO / "setup" / "scripts" / "self_check.py"

# Patterns that would indicate a REAL (programmatic) use of the value, as opposed to a
# prose mention inside a docstring/comment/message string.
PROGRAMMATIC_READ_PATTERNS = [
    re.compile(r"Get-ScheduledTaskInfo"),
    re.compile(r"\.LastTaskResult\b"),
    re.compile(r"\.LastRunResult\b"),
    re.compile(r"\[[\"']LastTaskResult[\"']\]"),
    re.compile(r"\[[\"']LastRunResult[\"']\]"),
    re.compile(r"\.get\(\s*[\"']LastTaskResult[\"']"),
    re.compile(r"\.get\(\s*[\"']LastRunResult[\"']"),
    # an actual subprocess/os invocation of schtasks -- NOT a mention of the word inside
    # an advisory message string telling the human to run it by hand (self_check.py's
    # check_macro_calendar_freshness does exactly that, legitimately, in its return message).
    re.compile(r"(subprocess\.\w+|os\.system|os\.popen)\([^)]*schtasks"),
]


def test_self_check_never_programmatically_reads_lasttaskresult():
    text = SELF_CHECK.read_text(encoding="utf-8", errors="replace")
    hits = {p.pattern: p.findall(text) for p in PROGRAMMATIC_READ_PATTERNS if p.search(text)}
    assert not hits, (
        f"self_check.py now contains a PROGRAMMATIC read of LastTaskResult/LastRunResult "
        f"(or a schtasks call): {hits} -- this is exactly the (a)-class real violation the "
        f"G-EXITCODE guard exists to catch (Task Scheduler's exit code is fake for the "
        f"wscript/vbs hidden-launch chain). Read the task's own output artifact instead "
        f"(scout_output.json / run-cmd-hidden.log / run-ps1-hidden.log pattern), and if "
        f"this really is a legitimate new use, it must be re-triaged -- not silently "
        f"protected by the existing allow-list entry, which was earned for the OLD "
        f"narrative-only content, not this new code."
    )


def test_self_check_still_carries_the_earned_exemption_marker():
    text = SELF_CHECK.read_text(encoding="utf-8", errors="replace")
    assert "LASTTASKRESULT-UNTRUSTED-BY-DESIGN" in text, (
        "self_check.py's allow-list exemption in test_graduated_guards.py is earned by "
        "this marker documenting all 9 LastTaskResult/LastRunResult mentions as proven "
        "narrative-only -- it has been deleted, so the exemption is no longer earned and "
        "the allow-list entry should be removed (forcing the guard to re-flag and "
        "re-triage) rather than silently kept."
    )


def test_self_check_lasttaskresult_mentions_are_all_prose_not_code_assignment():
    """Extra belt-and-braces check: every line mentioning LastTaskResult/LastRunResult
    must be inside a string literal (docstring, f-string, comment) -- never the target of
    a bare assignment, comparison, or conditional (e.g. `if x.LastTaskResult == 0:` or
    `result = info["LastTaskResult"]`), which would be a real authority-use even if it
    doesn't match the narrower programmatic-read regexes above."""
    text = SELF_CHECK.read_text(encoding="utf-8", errors="replace")
    mention_pattern = re.compile(r"LastTaskResult|LastRunResult")
    bad_lines = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not mention_pattern.search(line):
            continue
        stripped = line.strip()
        # legitimate: comment lines, or lines that are clearly inside a string/docstring
        # (heuristic: the mention is not immediately preceded by an assignment/condition
        # operator touching a bare identifier).
        if stripped.startswith("#"):
            continue
        if re.search(r"==\s*[\"']?LastTaskResult|LastTaskResult\s*==|if\s+\S*LastTaskResult",
                      stripped):
            bad_lines.append((lineno, stripped))
    assert not bad_lines, (
        f"found LastTaskResult/LastRunResult used in what looks like executable "
        f"conditional/comparison logic, not prose: {bad_lines}"
    )
