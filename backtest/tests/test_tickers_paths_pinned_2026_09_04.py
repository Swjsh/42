"""FIX 5 (LOW, 2026-09-04 adversarial review) -- pin explicit `path=` on every mps./mj. call
in the tickers-lane executor scripts.

RATIONALE: `multi/lib/position_state.py`'s `save_state`/`load_state`/`ensure_initialized` and
`multi/lib/journal.py`'s `append_entry`/`append_exit`/`all_rows`/`open_trades`/`closed_trades`
all default their `path` parameter to the MULTI-1 arm's own files
(`automation/state/multi/exit-state.json`, `journal/trades-multi.csv`). One omitted `path=`
kwarg anywhere in `multi/execute.py` or `multi/tickers_flatten.py` would silently read or
write multi-1's state/journal instead of the tickers arm's own -- cross-contaminating two
unrelated lanes. This is an AST check, not a runtime test: it parses the two scripts' source
and asserts every qualifying call site pins `path=` explicitly, so a future edit that drops
the kwarg fails CI immediately with the offending line number rather than silently corrupting
a different lane's books the next time it runs.

The set of "qualifying" mps./mj. functions is DERIVED from the real modules via
`inspect.signature` (never hardcoded) so this check tracks position_state.py/journal.py
automatically if a function is renamed or a new path-accepting helper is added -- and
`test_path_accepting_function_registry_is_nonempty` guards against the derivation itself
silently going toothless.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi.lib import journal as mj  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402

_MODULES = {"mps": mps, "mj": mj}

CHECKED_FILES = (
    REPO / "multi" / "execute.py",
    REPO / "multi" / "tickers_flatten.py",
)


def _functions_accepting_path(module) -> set:
    """Every top-level function on `module` whose signature has a `path` parameter."""
    out = set()
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name)
        if not inspect.isfunction(obj):
            continue
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            continue
        if "path" in sig.parameters:
            out.add(name)
    return out


_PATH_FUNCS = {alias: _functions_accepting_path(mod) for alias, mod in _MODULES.items()}


def _find_missing_path_kwarg(file_path: Path) -> list:
    """[(lineno, 'mps.save_state'), ...] for every call in `file_path` to a known
    path-accepting mps./mj. function that does not pass `path=` explicitly by keyword.
    (Every qualifying function declares `path` keyword-only or defaults it, so a caller can
    never satisfy the requirement positionally in valid Python -- checking `node.keywords`
    alone is complete, not merely convenient.)"""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        alias = func.value.id
        if alias not in _PATH_FUNCS:
            continue
        fn_name = func.attr
        if fn_name not in _PATH_FUNCS[alias]:
            continue
        has_path_kw = any(kw.arg == "path" for kw in node.keywords)
        if not has_path_kw:
            violations.append((node.lineno, f"{alias}.{fn_name}"))
    return violations


def test_path_accepting_function_registry_is_nonempty():
    """Guards the AST check itself: if position_state.py/journal.py's function names ever
    change such that this registry comes back empty, the check below would pass trivially
    without having verified anything."""
    assert _PATH_FUNCS["mps"] >= {"save_state", "load_state", "ensure_initialized"}
    assert _PATH_FUNCS["mj"] >= {"append_entry", "append_exit", "open_trades"}


@pytest.mark.parametrize("file_path", CHECKED_FILES, ids=lambda p: p.name)
def test_every_mps_mj_call_pins_path_explicitly(file_path):
    assert file_path.exists(), f"expected to find {file_path}"
    violations = _find_missing_path_kwarg(file_path)
    assert violations == [], (
        f"{file_path.name}: the following mps./mj. calls omit an explicit path= kwarg -- "
        f"their defaults point at multi-1's own files, so an omission here would cross-"
        f"contaminate a different lane's state/journal: {violations}"
    )
