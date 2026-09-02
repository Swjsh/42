"""The two nightly runners must PARTITION the suite -- no test covered by neither.

THE SCAR (2026-09-02). Three runners existed and each was individually correct:

  * run_safety_gate.py     -- 6 curated fast suites, every commit. By design, not a net.
  * guard_runner_full.py   -- `tests/ -m "not slow"`, nightly. The whole suite MINUS slow.
  * guard_runner_slow.py   -- `-m slow`, nightly, over an ENUMERATED LIST OF TWO FILES.

The gap is in the last one. `guard_runner_full` deselects every slow test; `guard_runner_slow`
picked up only the slow tests that lived in two named files. So marking a test `@pytest.mark.slow`
anywhere else placed it outside EVERY automated fire, by default, silently.

Measured that day: 46 slow tests, 36 covered by the two names, **10 covered by nothing**, spread
across 10 separate files. One of the ten -- `test_structure_shift_cascade_ab.py`'s anchor
reproduction -- had already drifted from 190 to 189 trades, deterministically, and no fire on
this box would ever have reported it. It was found only because a human ran the full suite by
hand with no `-m` filter.

This is the same C7 silent-success class named in `guard_runner_full.py`'s own docstring (the
2026-08-20 ATM-tier revert leaving three pins RED for a day), one level further out: that scar
was "a FILE nothing runs", this one is "a MARKER nothing runs".

WHAT THIS FILE PINS -- the PROPERTY, not the wording. The two nightly runners must between
them collect every test in the suite. Enumerating filenames is what rotted, so an
enumerated-list fix would rot the same way; the invariant is the partition itself.

DELIBERATELY NOT ASSERTED: which marker each runner uses, or that there are exactly two
runners. A future split into three is fine as long as the union still covers everything.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SLOW_RUNNER = REPO / "setup" / "guard_runner_slow.py"
FULL_RUNNER = REPO / "setup" / "guard_runner_full.py"


def _pytest_argv(source_path: Path) -> list[str]:
    """Every string literal in the list passed to a subprocess.run(...) call that invokes
    pytest, read from the AST.

    AST, NOT a substring search -- `test_string_search_cannot_answer_code_questions`
    (2026-09-02, same session): three guards written that night failed or nearly passed
    wrongly because prose in a docstring answered a question about code. This file's whole
    subject is a runner whose argv is buried under ~20 lines of explanatory comment, so a
    text scan here would be reading the comment, not the command.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    # Every list/tuple literal, wherever it sits. The two runners differ in shape --
    # guard_runner_slow.py passes the list INLINE to subprocess.run, guard_runner_full.py
    # assigns it to `cmd` first -- so scanning only Call arguments finds one and misses the
    # other. The argv is identified by its CONTENT ("pytest" and "-m" both present), which
    # is a property of the command either way.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        items = [e.value for e in node.elts if isinstance(e, ast.Constant)
                 and isinstance(e.value, str)]
        if "pytest" in items and "-m" in items:
            return items
    raise AssertionError(f"no pytest invocation found in {source_path.name}")


@pytest.fixture(scope="module")
def slow_argv() -> list[str]:
    if not SLOW_RUNNER.exists():
        pytest.skip("guard_runner_slow.py absent")
    return _pytest_argv(SLOW_RUNNER)


@pytest.fixture(scope="module")
def full_argv() -> list[str]:
    if not FULL_RUNNER.exists():
        pytest.skip("guard_runner_full.py absent")
    return _pytest_argv(FULL_RUNNER)


def _targets(argv: list[str]) -> list[str]:
    """Positional path targets -- argv entries that look like a test path, not a flag or a
    flag's value."""
    out, skip_next = [], False
    for i, a in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if a in ("-m", "-p", "-k", "--timeout"):
            skip_next = True
            continue
        if a.startswith("-") or a in ("python", "pytest"):
            continue
        out.append(a)
    return out


# ---------------------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------------------

def test_slow_runner_targets_the_whole_suite_not_named_files(slow_argv):
    """THE regression. If this list ever names individual files again, every slow test
    outside those files is covered by nothing -- which is exactly the state this test was
    written to end."""
    targets = _targets(slow_argv)
    assert targets, f"slow runner has no path target at all: {slow_argv}"
    named_files = [t for t in targets if t.endswith(".py")]
    assert not named_files, (
        f"guard_runner_slow.py is back to an ENUMERATED FILE LIST: {named_files}. Every "
        f"@pytest.mark.slow test outside those files is then run by NO automated fire -- "
        f"guard_runner_full.py deselects them all with -m 'not slow'. That gap hid a "
        f"deterministic anchor failure (190 -> 189 trades) for at least 10 days. Target "
        f"'tests/' so the set is self-maintaining."
    )
    assert any(t.rstrip("/\\").endswith("tests") for t in targets), (
        f"slow runner no longer targets the tests/ directory: {targets}"
    )


def test_the_two_runners_partition_the_suite(slow_argv, full_argv):
    """Union coverage: one runner takes `slow`, the other takes `not slow`, and BOTH run
    over the whole tests/ tree. Neither half alone is a net; only the pair is."""
    def marker(argv: list[str]) -> str:
        # The LAST -m, not the first: both runners spell the command
        # `python -m pytest ... -m <marker>`, so the first -m's value is "pytest" itself.
        idx = max(i for i, a in enumerate(argv) if a == "-m")
        return argv[idx + 1]

    slow_m, full_m = marker(slow_argv), marker(full_argv)
    assert {slow_m.strip(), full_m.strip()} == {"slow", "not slow"}, (
        f"the two runners no longer split on slow/not-slow ({slow_m!r} / {full_m!r}) -- "
        f"whatever the new scheme is, some marker combination is now uncovered"
    )
    for name, argv in (("slow", slow_argv), ("full", full_argv)):
        assert any(t.rstrip("/\\").endswith("tests") for t in _targets(argv)), (
            f"the {name} runner does not run over the whole tests/ tree, so the union of "
            f"the two no longer covers the suite: {_targets(argv)}"
        )


def test_every_slow_test_in_the_repo_is_reachable_by_the_slow_runner(slow_argv):
    """Cross-check against the real filesystem rather than the argv alone: collect the files
    that actually contain a slow marker and confirm the runner's target subsumes them.

    Guards the direction the argv test cannot see -- a runner that targets `tests/foo/`
    would pass the no-named-files check while still missing most of the suite.
    """
    tests_dir = REPO / "backtest" / "tests"
    slow_files = sorted(
        p.relative_to(REPO / "backtest").as_posix()
        for p in tests_dir.rglob("test_*.py")
        if "pytest.mark.slow" in p.read_text(encoding="utf-8", errors="replace")
    )
    if not slow_files:
        pytest.skip("no slow-marked tests in the tree")
    targets = [t.rstrip("/\\").replace("\\", "/") for t in _targets(slow_argv)]
    uncovered = [f for f in slow_files
                 if not any(f == t or f.startswith(t + "/") or t == "tests" for t in targets)]
    assert not uncovered, (
        f"{len(uncovered)} file(s) containing @pytest.mark.slow are outside the slow "
        f"runner's target {targets}: {uncovered[:6]}"
    )


def test_slow_runner_timeout_has_headroom_for_the_whole_suite(slow_argv):
    """Widening the target without widening the timeout would trade a silent gap for a
    nightly timeout -- a different silent failure. The measured full slow run on 2026-09-02
    was 1156s (19m16s) for all 46 tests; the timeout must clear that with real margin."""
    src = SLOW_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    timeout = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "TIMEOUT_S"
                and isinstance(node.value, ast.Constant)):
            timeout = node.value.value
    assert isinstance(timeout, (int, float)), "TIMEOUT_S not found as a literal assignment"
    assert timeout >= 1800, (
        f"TIMEOUT_S={timeout}s is under the headroom the whole slow suite needs (measured "
        f"1156s on 2026-09-02, and it grows as slow tests are added). A timeout kills the "
        f"run WITHOUT writing a verdict, which is the silent failure this runner exists to "
        f"prevent."
    )
