"""Guard: no test file may importlib.reload() the shared setup_dispatch module.

Scar (2026-08-22, full-suite RED across at least 3 conductor fires on 2026-08-21
23:15/23:34/23:59 ET, always the identical 5 tests): test_gap_prior_close.py did
`import setup_dispatch as sd; importlib.reload(sd)`. reload() re-executes the
module's class statements IN PLACE, rebinding setup_dispatch.SetupDispatcher /
DispatchResult to brand-new class objects on the shared sys.modules["setup_dispatch"]
entry.

test_setup_dispatch.py does `from setup_dispatch import SetupDispatcher` at
collection time (before any test runs), capturing the ORIGINAL class object. Once
test_gap_prior_close.py's test executed (alphabetically before test_setup_dispatch.py,
"g" < "s") and reloaded the module, `patch("setup_dispatch.SetupDispatcher.<method>", ...)`
(a string lookup that resolves the CURRENT, POST-RELOAD class) patched a class that
test_setup_dispatch.py never actually instantiates -- so the mock never intercepted the
call, and `mock_method.assert_called_once()` failed 5 times downstream, every single
full-suite run, while every individual file passed standalone (the exact "polluted only
in-suite" shape that made this hard to triage -- see STATUS.md 2026-08-21 "TEST POLLUTION
(5+2)" entry).

Fix: test_gap_prior_close.py no longer reloads the module at all -- monkeypatch.setattr
on `_REPO` already isolates the one thing that test needs, without touching the shared
class objects every other test file's collection-time imports depend on.

This guard makes the fixed class of bug unrepresentable: no test file may
`importlib.reload()` a name bound to the `setup_dispatch` module. (Scoped to this one
module -- the specific module that broke -- rather than a blanket reload ban, since a
handful of OTHER tests legitimately reload narrower, single-file-owned modules like a
lone watcher submodule for "simulate a fresh scheduler process" semantics.)
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# Matches: importlib.reload(sd) / importlib.reload(setup_dispatch) / reload(sd) etc,
# where the reloaded name was bound via `import setup_dispatch [as sd]`.
_RELOAD_CALL_RE = re.compile(r"(?:importlib\.)?reload\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_IMPORT_SETUP_DISPATCH_RE = re.compile(
    r"^\s*import\s+setup_dispatch(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*$",
    re.MULTILINE,
)


def _strip_full_line_comments(src: str) -> str:
    """Drop lines that are pure `#` comments so prose ABOUT this pattern (e.g. this
    guard's own docstring/comments, or a fixed file's explanatory note) never trips
    the detector -- same false-positive class as the PS1-BARE-PYTHON-COMMENT-SKIP
    queue item (a doc comment mentioning the banned call site got flagged as a live
    call site). Only inspects real code lines."""
    kept = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _reload_targets_setup_dispatch(src: str) -> bool:
    """True if `src` reloads a name that was bound to the setup_dispatch module.

    Only inspects code lines (docstrings/comments describing this pattern are exempt --
    checked by scanning line-by-line and skipping full `#`-comment lines; the risk of a
    docstring containing a live-looking call is accepted since production test files
    don't write executable-looking prose inside triple-quoted strings without a comment
    marker in this codebase's style)."""
    code = _strip_full_line_comments(src)
    bound_names = {"setup_dispatch"}
    for m in _IMPORT_SETUP_DISPATCH_RE.finditer(code):
        alias = m.group(1)
        bound_names.add(alias if alias else "setup_dispatch")

    for m in _RELOAD_CALL_RE.finditer(code):
        if m.group(1) in bound_names:
            return True
    return False


def test_no_test_file_reloads_setup_dispatch() -> None:
    offenders = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        if path.name == Path(__file__).name:
            continue  # this guard file itself references the pattern in prose/regex form
        src = path.read_text(encoding="utf-8", errors="ignore")
        if "reload" not in src or "setup_dispatch" not in src:
            continue  # cheap prefilter before the regex pass
        if _reload_targets_setup_dispatch(src):
            offenders.append(path.name)

    assert offenders == [], (
        "The following test file(s) importlib.reload() the shared setup_dispatch "
        f"module, which corrupts SetupDispatcher/DispatchResult for every other test "
        f"file that captured the class via `from setup_dispatch import ...` at "
        f"collection time: {offenders}. Use monkeypatch.setattr on the specific "
        "module-level name you need to isolate instead (see test_gap_prior_close.py's "
        "2026-08-22 fix for the pattern)."
    )


def test_gap_prior_close_no_longer_reloads() -> None:
    """Direct regression pin on the actual scarred file, in addition to the sweep above.

    Uses the same comment-aware detector as the sweep (not a raw substring check) --
    this file's own fix comment intentionally NAMES the banned call in prose to explain
    why it was removed, which a naive substring check would itself misflag (the exact
    PS1-BARE-PYTHON-COMMENT-SKIP false-positive class this guard's docstring warns about).
    """
    src = (TESTS_DIR / "test_gap_prior_close.py").read_text(encoding="utf-8")
    assert _reload_targets_setup_dispatch(src) is False
