"""Guard: FIVE-ET-FALLBACKS-STILL-HARDCODE-MINUS-4 (filed 2026-09-02, fixed 2026-09-03).

Five modules named in the queue item computed ET, in the `except:` branch of their own
`try: from et_clock import et_now / except:` fallback, as the fixed-offset anti-pattern
`datetime.utcnow() - timedelta(hours=4)` -- exactly what et_clock.py's own docstring exists
to replace ("Any code using naive datetime.now() or timezone(timedelta(hours=-4))..."). That
offset is EDT-only: during EST (roughly Nov-Mar) it is wrong by an hour, and for the two
callers that derive a DATE from it (conductor_budget._et_today, entry_location_shadow's
_et_date) the wrong hour can name the wrong DAY between 00:00-01:00 ET in winter.

A repo-wide grep for the same shape (`utcnow() [+-] timedelta(hours=[-]4)`) found TEN more
files with the byte-identical fallback beyond the five named in the queue item -- fixed here
too per the work order's "fix ... any that are clearly the same fallback shape" instruction.

FIX: every fallback now derives ET via stdlib `zoneinfo` (`ZoneInfo("America/New_York")`),
which is DST-aware and cannot itself fail the way the et_clock import it guards might.
Naive-datetime callers get `.replace(tzinfo=None)` so the fallback's return type still
matches et_clock.et_now()'s own (naive) contract -- no aware/naive comparison crashes
downstream. entry_location_shadow.py's `_et_date` is a different shape (it converts an
existing UTC timestamp to an ET date, not `now()`) -- fixed with `.astimezone(ZoneInfo(...))`
instead of `.now(ZoneInfo(...))`.

Two protection layers:

1. test_no_fixed_offset_fallback_remains -- STATIC: scans every file in ALL_FILES for the
   `utcnow() [+-] timedelta(hours=[-]4)` pattern. A regression that re-introduces it FAILS.

2. test_*_fallback_matches_zoneinfo (parametrized + two special cases) -- BEHAVIORAL: for
   each file, blocks `et_clock` (via `sys.modules["et_clock"] = None`, which forces the
   module's own `try: from et_clock import ...` to raise ImportError -- the REAL fallback
   branch runs, not a hand-copied restatement of it) and asserts the fallback's result
   matches a fresh `datetime.now(ZoneInfo("America/New_York"))` call. entry_location_shadow.py
   and live_watch.py don't expose a standalone `et_now`-shaped callable (the former is a
   closure nested inside `round_trips()`, the latter is inline in `run_once()`), so those two
   extract the exact AST node from source and `exec` it directly -- still testing the real
   fallback code, not a copy.

RED-PROOF (run manually, not encoded as a test): reintroducing the old fixed-offset line in
one of these files makes test 1 fail with that file's path in the assertion message. See the
session report for the quoted RED output.

Run:
    cd backtest && .venv/Scripts/python.exe -m pytest tests/test_et_fallbacks_no_fixed_offset_2026_09_03.py -v
"""
from __future__ import annotations

import ast
import re
import sys
import textwrap
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")

# The five files named verbatim in the queue item (FIVE-ET-FALLBACKS-STILL-HARDCODE-MINUS-4).
NAMED_FIVE = [
    REPO / "setup/scripts/conductor_budget.py",
    REPO / "setup/scripts/conductor_wake_watch.py",
    REPO / "setup/scripts/entry_block_watch.py",
    REPO / "setup/scripts/entry_location_shadow.py",
    REPO / "setup/scripts/fill_funnel.py",
]

# Found by repo-wide grep for the identical fallback shape; fixed alongside the named five
# per the work order's "fix ... any that are clearly the same fallback shape" instruction.
SAME_SHAPE_EXTRA = [
    REPO / "automation/state/weekly/participation_cascade.py",
    REPO / "backtest/tools/participation_cascade.py",
    REPO / "setup/scripts/gamma_glance.py",
    REPO / "setup/scripts/gamma_status.py",
    REPO / "setup/scripts/loop_state_refresh.py",
    REPO / "setup/scripts/quote_recorder.py",
    REPO / "setup/scripts/self_check.py",
    REPO / "setup/scripts/task_state_guard.py",
    REPO / "setup/scripts/trendline_draw_state.py",
    REPO / "setup/scripts/live_watch.py",
]

ALL_FILES = NAMED_FIVE + SAME_SHAPE_EXTRA

# Matches datetime.utcnow() +/- timedelta(hours=4) OR timedelta(hours=-4), the two
# equivalent spellings observed in this repo, with or without a dt./_dt. module prefix.
FIXED_OFFSET_RE = re.compile(
    r"utcnow\(\)\s*[+-]\s*(?:\w+\.)?timedelta\(\s*hours\s*=\s*-?4\s*\)"
)

# Files exposing a standalone, no-arg, module-level fallback callable that returns "now" (or
# a "today" date string) once et_clock is blocked. Maps path -> (attr name, "datetime"|"date_str").
STANDALONE_CALLABLES = {
    REPO / "setup/scripts/conductor_budget.py": ("_et_today", "date_str"),
    REPO / "setup/scripts/conductor_wake_watch.py": ("_et_now", "datetime"),
    REPO / "setup/scripts/entry_block_watch.py": ("_et_now", "datetime"),
    REPO / "setup/scripts/fill_funnel.py": ("et_now", "datetime"),
    REPO / "automation/state/weekly/participation_cascade.py": ("et_now", "datetime"),
    REPO / "backtest/tools/participation_cascade.py": ("et_now", "datetime"),
    REPO / "setup/scripts/gamma_glance.py": ("et_now", "datetime"),
    REPO / "setup/scripts/gamma_status.py": ("et_now", "datetime"),
    REPO / "setup/scripts/loop_state_refresh.py": ("et_now", "datetime"),
    REPO / "setup/scripts/quote_recorder.py": ("et_now", "datetime"),
    REPO / "setup/scripts/self_check.py": ("et_now", "datetime"),
    REPO / "setup/scripts/task_state_guard.py": ("et_now", "datetime"),
    REPO / "setup/scripts/trendline_draw_state.py": ("et_now", "datetime"),
}

assert set(STANDALONE_CALLABLES) == set(ALL_FILES) - {
    REPO / "setup/scripts/entry_location_shadow.py",
    REPO / "setup/scripts/live_watch.py",
}, "STANDALONE_CALLABLES must cover every file except the two AST-extraction special cases"


# ---------------------------------------------------------------------------
# 1. Static source scan
# ---------------------------------------------------------------------------

def test_no_fixed_offset_fallback_remains():
    offenders = []
    for f in ALL_FILES:
        src = f.read_text(encoding="utf-8")
        if FIXED_OFFSET_RE.search(src):
            offenders.append(str(f.relative_to(REPO)))
    assert not offenders, (
        f"fixed -4h ET fallback (the anti-pattern et_clock.py's docstring bans) still "
        f"present in: {offenders}"
    )


# ---------------------------------------------------------------------------
# 2. Behavioral: the real fallback branch, executed with et_clock blocked
# ---------------------------------------------------------------------------

_counter = 0


def _load_with_et_clock_blocked(path: Path):
    """Import `path` as a fresh module with et_clock forced unimportable.

    sys.modules["et_clock"] = None is CPython's documented way to make
    `import et_clock` (and `from et_clock import ...`) raise ImportError even though
    the real et_clock.py is perfectly importable -- so each module's own
    `try: from et_clock import et_now / except:` genuinely takes its except branch,
    rather than us hand-simulating what that branch does.
    """
    global _counter
    _counter += 1
    modname = f"_et_fallback_probe_{path.stem}_{_counter}"
    with patch.dict(sys.modules, {"et_clock": None}):
        spec = importlib.util.spec_from_file_location(modname, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(modname, None)
    return mod


@pytest.mark.parametrize(
    "path", sorted(STANDALONE_CALLABLES, key=lambda p: str(p)), ids=lambda p: p.name
)
def test_standalone_fallback_matches_zoneinfo(path: Path):
    attr, kind = STANDALONE_CALLABLES[path]
    mod = _load_with_et_clock_blocked(path)
    fn = getattr(mod, attr)

    if kind == "date_str":
        expected = datetime.now(ET).date().isoformat()
        result = fn()
        assert result == expected, (
            f"{path.name}: fallback {attr}() returned {result!r}, expected {expected!r} "
            f"(zoneinfo-derived ET date)"
        )
        return

    before = datetime.now(ET).replace(tzinfo=None)
    result = fn()
    after = datetime.now(ET).replace(tzinfo=None)
    assert isinstance(result, datetime), f"{path.name}: fallback {attr}() did not return a datetime"
    assert result.tzinfo is None, (
        f"{path.name}: fallback {attr}() returned a tz-AWARE datetime -- breaks parity with "
        f"et_clock.et_now()'s naive contract"
    )
    assert before - timedelta(seconds=2) <= result <= after + timedelta(seconds=2), (
        f"{path.name}: fallback {attr}() returned {result}, expected within a couple seconds "
        f"of the zoneinfo-derived ET now() bracket [{before}, {after}]"
    )


# ---------------------------------------------------------------------------
# 2b. Special cases: fallback logic not exposed as a standalone module-level callable
# ---------------------------------------------------------------------------

def test_entry_location_shadow_et_date_fallback_matches_zoneinfo():
    """entry_location_shadow.py's `_et_date` is a closure nested inside `round_trips()` --
    not reachable via getattr on the module. Extract its real AST source and exec it
    directly so the test exercises the actual fixed code, not a restatement of it.

    Uses a UTC instant that crosses the ET date boundary in WINTER (EST, UTC-5):
    2026-01-15T04:30:00Z is 2026-01-14 23:30 ET. The old fixed -4h offset would have
    computed 2026-01-15 00:30 ET -- the wrong DAY -- which is exactly the L-class bug this
    item flags for date-deriving callers.
    """
    path = REPO / "setup/scripts/entry_location_shadow.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_et_date"
    )
    segment = ast.get_source_segment(src, node)
    assert segment, "could not extract _et_date source segment"
    # ast.get_source_segment preserves each line's ORIGINAL absolute indentation except
    # the first line (which starts exactly at the node, losing its own leading spaces) --
    # pad the first line back to the node's real column before dedenting uniformly, or a
    # multi-line segment can dedent into a mismatched-indentation SyntaxError.
    segment = textwrap.dedent(" " * node.col_offset + segment)

    namespace: dict = {}
    exec(compile(segment, str(path), "exec"), namespace)  # noqa: S102
    _et_date = namespace["_et_date"]

    result = _et_date("2026-01-15T04:30:00Z")
    assert result == "2026-01-14", (
        f"_et_date('2026-01-15T04:30:00Z') returned {result!r}, expected '2026-01-14' "
        f"(winter ET date, UTC-5) -- a fixed -4h offset would wrongly return '2026-01-15'"
    )


def test_live_watch_run_once_et_fallback_matches_zoneinfo():
    """live_watch.py computes its ET fallback inline inside `run_once()`, not as a
    standalone function. Extract the exact `try/except` AST node and exec it with
    et_clock blocked -- same "test the real source" discipline as the other cases.
    """
    path = REPO / "setup/scripts/live_watch.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    run_once = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "run_once"
    )
    try_node = next(
        n for n in ast.iter_child_nodes(run_once) if isinstance(n, ast.Try)
    )
    segment = ast.get_source_segment(src, try_node)
    assert segment, "could not extract run_once's et_now try/except source segment"
    segment = textwrap.dedent(" " * try_node.col_offset + segment)

    import datetime as dt  # local alias matching the module's own import style

    namespace = {"dt": dt, "ZoneInfo": ZoneInfo}
    before = datetime.now(ET).replace(tzinfo=None)
    with patch.dict(sys.modules, {"et_clock": None}):
        exec(compile(segment, str(path), "exec"), namespace)  # noqa: S102
    after = datetime.now(ET).replace(tzinfo=None)

    now_et = namespace.get("now_et")
    assert isinstance(now_et, datetime), "run_once fallback did not assign a datetime to now_et"
    assert now_et.tzinfo is None, "run_once fallback returned a tz-AWARE datetime"
    assert before - timedelta(seconds=2) <= now_et <= after + timedelta(seconds=2), (
        f"run_once fallback now_et={now_et}, expected within the zoneinfo bracket "
        f"[{before}, {after}]"
    )
