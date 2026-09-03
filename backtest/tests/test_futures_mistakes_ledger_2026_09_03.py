"""Guard for FUTURES-MISTAKES-LEDGER-IS-DEAD-CODE (queue.md, MED, C14 dead-knob class).

ROOT CAUSE: `futures_journal.record_mistake()` (backtest/futures/futures_journal.py:178)
was fully implemented -- header, "what/cost/fix" block, fail-open try/except, the whole
shape -- and had ZERO call sites anywhere in the repo (`grep -rn record_mistake
--include=*.py .` returned only the definition itself). `futures_eod.py::rule_audit()`
independently re-detects every rule break from the ledger, post-hoc, and then just...
returned the list. Nothing persisted it. The futures analogue of Rule 8's mistakes
ledger (`journal/mistakes.md` on the SPY side) was documented, implemented, and never
invoked -- `journal/futures/mistakes.md` did not exist on disk.

FIX: `futures_eod.build()` now calls the new `persist_mistakes(date, breaks)` right
after `rule_audit()`, which groups breaks by rule and calls `fj.record_mistake()` once
per NEW (date, rule, lane) key -- idempotent across re-runs via an inline dedupe marker
this module writes into its own bullet text and later scans for. Fail-open throughout:
a ledger write can never break the EOD build.

This guard proves: one break -> exactly one row; a re-run of the same break -> zero new
rows; no breaks -> no write at all; a write error is swallowed, never raised; and the
`record_mistake()` call site actually exists in futures_eod.py's AST (not just grep-able
text -- a commented-out or docstring-only mention would fool grep but not ast.walk).
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EOD_MODULE = REPO / "backtest" / "futures" / "futures_eod.py"
JOURNAL_MODULE = REPO / "backtest" / "futures" / "futures_journal.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture()
def eod_mod(tmp_path, monkeypatch):
    """A freshly-loaded futures_eod module with its journal redirected to tmp_path,
    same isolation pattern as futures_drills.py uses for real drills -- a test run must
    never touch the real journal/futures/mistakes.md."""
    fj = _load("futures_journal_fmg", JOURNAL_MODULE)
    monkeypatch.setattr(fj, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(fj, "MISTAKES_MD", tmp_path / "mistakes.md")
    m = _load("futures_eod_fmg", EOD_MODULE)
    monkeypatch.setattr(m, "fj", fj)
    return m


def _one_break(rule="contract_cap", detail="qty 5 > cap 3"):
    return [{"ts": "2026-09-03T10:00:00", "rule": rule, "detail": detail}]


# ── behavior ─────────────────────────────────────────────────────────────────────

def test_detected_break_lands_exactly_one_row(eod_mod):
    written = eod_mod.persist_mistakes("2026-09-03", _one_break())
    assert written == 1
    text = eod_mod.fj.MISTAKES_MD.read_text(encoding="utf-8")
    assert text.count("## ") == 1
    assert "contract_cap" in text
    assert "2026-09-03" in text


def test_rerun_of_same_break_adds_no_rows(eod_mod):
    breaks = _one_break()
    first = eod_mod.persist_mistakes("2026-09-03", breaks)
    second = eod_mod.persist_mistakes("2026-09-03", breaks)
    assert first == 1
    assert second == 0
    text = eod_mod.fj.MISTAKES_MD.read_text(encoding="utf-8")
    assert text.count("## ") == 1, "re-run duplicated a row instead of deduping"


def test_multiple_breaks_same_rule_collapse_to_one_row(eod_mod):
    breaks = [
        {"ts": "2026-09-03T10:00:00", "rule": "contract_cap", "detail": "qty 5 > cap 3"},
        {"ts": "2026-09-03T10:05:00", "rule": "contract_cap", "detail": "qty 6 > cap 3"},
    ]
    written = eod_mod.persist_mistakes("2026-09-03", breaks)
    assert written == 1
    text = eod_mod.fj.MISTAKES_MD.read_text(encoding="utf-8")
    assert text.count("## ") == 1


def test_different_rule_same_day_is_a_second_row(eod_mod):
    eod_mod.persist_mistakes("2026-09-03", _one_break(rule="contract_cap"))
    eod_mod.persist_mistakes("2026-09-03", _one_break(rule="defined_stop"))
    text = eod_mod.fj.MISTAKES_MD.read_text(encoding="utf-8")
    assert text.count("## ") == 2


def test_different_date_same_rule_is_a_second_row(eod_mod):
    eod_mod.persist_mistakes("2026-09-03", _one_break())
    eod_mod.persist_mistakes("2026-09-04", _one_break())
    text = eod_mod.fj.MISTAKES_MD.read_text(encoding="utf-8")
    assert text.count("## ") == 2


def test_no_breaks_writes_nothing(eod_mod):
    written = eod_mod.persist_mistakes("2026-09-03", [])
    assert written == 0
    assert not eod_mod.fj.MISTAKES_MD.exists()


def test_write_error_does_not_raise(eod_mod, monkeypatch):
    def _boom(**kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(eod_mod.fj, "record_mistake", _boom)
    # Must not raise -- a ledger write error can never break the EOD path.
    written = eod_mod.persist_mistakes("2026-09-03", _one_break())
    assert written == 0


def test_persist_mistakes_is_wired_into_build(eod_mod, monkeypatch):
    """build() must actually call persist_mistakes -- not just have the function exist
    unused, which is precisely the dead-code pattern this guard exists to prevent."""
    calls = []
    monkeypatch.setattr(
        eod_mod, "persist_mistakes",
        lambda date, breaks, lane=eod_mod.MISTAKES_LANE: calls.append((date, breaks)) or 0,
    )
    monkeypatch.setattr(eod_mod, "_read_ledger", lambda date: [])
    eod_mod.build("2026-09-03")
    assert calls, "build() no longer calls persist_mistakes()"


# ── static: the call site actually exists (AST, not grep) ──────────────────────────

def test_record_mistake_call_site_exists_in_ast():
    tree = ast.parse(EOD_MODULE.read_text(encoding="utf-8"), filename=str(EOD_MODULE))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "record_mistake":
                found = True
                break
    assert found, (
        "futures_eod.py no longer calls record_mistake() anywhere -- "
        "FUTURES-MISTAKES-LEDGER-IS-DEAD-CODE would be dead code again"
    )


def test_build_calls_persist_mistakes_in_ast():
    """Belt-and-suspenders on the wiring itself: build()'s own body must contain a call
    to persist_mistakes, not just define it alongside an unrelated build()."""
    tree = ast.parse(EOD_MODULE.read_text(encoding="utf-8"), filename=str(EOD_MODULE))
    build_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "build"
    )
    calls_in_build = [
        n.func.id for n in ast.walk(build_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "persist_mistakes" in calls_in_build


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
