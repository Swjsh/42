"""Reconciliation test for the watcher fleet registry (Phase 0b/3 — 2026-06-18).

THE BUG THIS GUARDS: before the registry, ``runner.run_all_watchers`` wired each
watcher by hand in a long try/except chain. Nothing ASSERTED the full set was
loaded, so a watcher could be:
  * defined-but-unwired (an ORPHAN — the file exists, the engine never runs it;
    this is the "engine couldn't see 26 of 28 watchers" class of bug), or
  * registered-but-dead (a registry entry pointing at a detector that no longer
    exists).

The fix is a single source of truth: ``runner.WATCHERS``. This test enforces the
invariant

    set(detector files) == set(registered watchers)  ∪  EXCLUDED_FILES

so CI fails the moment someone adds a ``*_watcher.py`` without registering it, or
registers something that isn't on disk. Intentional exclusions (retired wrappers,
detector-only modules) live in an explicit, documented allowlist below.

It also asserts ``run_all_watchers`` actually ITERATES the registry (a registry
nobody loops over would pass the set check but still be dead), and that the
derived ``WATCHER_COUNT`` matches.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]          # .../backtest
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO.parent))                # repo root (crypto.* etc.)

from lib.watchers import runner as _runner
from lib.watchers.runner import WATCHERS, WATCHER_COUNT, run_all_watchers, _WatcherDeps
from lib.filters import BarContext

_WATCHERS_DIR = _REPO / "lib" / "watchers"


# ── Intentional exclusions (documented allowlist) ────────────────────────────
#
# A ``*_watcher.py`` file present on disk but DELIBERATELY not in the registry.
# Every entry needs a one-line reason. Empty today: SNIPER (sniper_watcher.py)
# and PIN-FADE (pinfade_watcher.py) were DELETED on 2026-06-18 rather than
# excluded, so there is no orphan file to allowlist. STAIRSTEP stays REGISTERED
# (its detector returns None by design — a registered-but-quiet watcher is fine;
# the registry handles a None-returning detector cleanly), so it is NOT excluded.
EXCLUDED_FILES: dict[str, str] = {
    # "example_watcher.py": "reason it is intentionally unregistered",
}


def _detector_files() -> set[str]:
    """Every ``*_watcher.py`` filename in lib/watchers (the fleet on disk)."""
    return {p.name for p in _WATCHERS_DIR.glob("*_watcher.py")}


def _registered_files() -> set[str]:
    """The filename each registry spec resolves to.

    A spec's ``attr`` is the detector's name in the runner module namespace; the
    function's ``__module__`` tells us which watcher file defines it. This is the
    same name the runner resolves at call time, so it reconciles what is REGISTERED
    against what is on DISK without trusting a parallel hand-kept list.
    """
    files: set[str] = set()
    for spec in WATCHERS:
        fn = getattr(_runner, spec.attr, None)
        assert fn is not None, (
            f"registry spec {spec.name!r} references runner global {spec.attr!r} "
            f"which does not exist — registered-but-dead entry"
        )
        mod = sys.modules.get(fn.__module__)
        mod_path = Path(getattr(mod, "__file__", "")) if mod else None
        assert mod_path is not None, f"cannot resolve module file for {spec.attr!r}"
        files.add(mod_path.name)
    return files


# ── The core reconciliation ──────────────────────────────────────────────────

def test_every_detector_file_is_registered():
    """No ORPHANS: every *_watcher.py on disk is wired into WATCHERS (minus allowlist)."""
    on_disk = _detector_files()
    registered = _registered_files()
    excluded = set(EXCLUDED_FILES)

    # Allowlist must reference real files (no stale exclusions).
    stale = excluded - on_disk
    assert not stale, f"EXCLUDED_FILES names files that don't exist: {sorted(stale)}"

    orphans = on_disk - registered - excluded
    assert not orphans, (
        f"ORPHAN watcher file(s) present but NOT in runner.WATCHERS: {sorted(orphans)}. "
        f"Register them in runner.WATCHERS, or add to EXCLUDED_FILES with a reason."
    )


def test_no_registry_entry_without_a_file():
    """No GHOSTS: every registered watcher resolves to a real *_watcher.py on disk."""
    on_disk = _detector_files()
    registered = _registered_files()
    ghosts = registered - on_disk
    assert not ghosts, (
        f"registry references file(s) that are not *_watcher.py on disk: {sorted(ghosts)}"
    )


def test_registry_is_exact_partition_of_disk():
    """The strong form: disk == registered ∪ excluded, with no overlap."""
    on_disk = _detector_files()
    registered = _registered_files()
    excluded = set(EXCLUDED_FILES)

    assert registered.isdisjoint(excluded), (
        f"file(s) both registered AND excluded: {sorted(registered & excluded)}"
    )
    assert on_disk == (registered | excluded), (
        f"fleet mismatch.\n  on_disk    = {sorted(on_disk)}\n"
        f"  registered = {sorted(registered)}\n  excluded   = {sorted(excluded)}"
    )


def test_deleted_watchers_are_gone():
    """SNIPER + PIN-FADE were deleted (not just unregistered) on 2026-06-18."""
    on_disk = _detector_files()
    assert "sniper_watcher.py" not in on_disk, "sniper_watcher.py should be deleted"
    assert "pinfade_watcher.py" not in on_disk, "pinfade_watcher.py should be deleted"
    # And nothing should still import them.
    assert "lib.watchers.sniper_watcher" not in sys.modules
    assert "lib.watchers.pinfade_watcher" not in sys.modules


# ── Registry hygiene ─────────────────────────────────────────────────────────

def test_registry_names_unique():
    names = [s.name for s in WATCHERS]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate watcher names in registry: {sorted(dupes)}"


def test_registry_attrs_unique():
    attrs = [s.attr for s in WATCHERS]
    dupes = {a for a in attrs if attrs.count(a) > 1}
    assert not dupes, f"duplicate detector attrs in registry: {sorted(dupes)}"


def test_watcher_count_derived_from_registry():
    assert WATCHER_COUNT == len(WATCHERS)
    # Sanity floor: deleting SNIPER + PIN-FADE left a substantial fleet.
    assert WATCHER_COUNT >= 20, f"fleet unexpectedly small: {WATCHER_COUNT}"


# ── run_all_watchers actually ITERATES the registry ──────────────────────────

def _minimal_ctx(bar: pd.Series) -> BarContext:
    prior = pd.DataFrame([
        {"timestamp_et": pd.Timestamp("2026-05-20 09:30"), "open": 539.0, "high": 539.5, "low": 538.5, "close": 539.1, "volume": 300_000},
        {"timestamp_et": pd.Timestamp("2026-05-20 09:35"), "open": 539.1, "high": 540.5, "low": 539.0, "close": 540.0, "volume": 300_000},
        {"timestamp_et": pd.Timestamp("2026-05-20 09:40"), "open": 540.0, "high": 540.6, "low": 539.8, "close": 540.3, "volume": 300_000},
    ])
    return BarContext(
        bar_idx=2,
        timestamp_et=bar["timestamp_et"].to_pydatetime(),
        bar=bar,
        prior_bars=prior,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=17.5,
        vix_prior=17.4,
        vol_baseline_20=300_000.0,
        range_baseline_20=1.0,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


def test_run_all_watchers_invokes_every_registry_spec(monkeypatch):
    """Patch EVERY spec's invoke with a tracer; confirm the loop calls each once.

    This is the proof the registry is LIVE — a registry that nobody iterates would
    still pass the set checks above. We replace ``runner.WATCHERS`` with tracer
    specs so the test does not depend on any real detector firing.
    """
    from lib.watchers.runner import WatcherSpec

    called: list[str] = []

    def _make_tracer(name: str):
        def _invoke(_deps, _name=name):
            called.append(_name)
            return None
        return _invoke

    tracer_specs = [WatcherSpec(name=s.name, attr=s.attr, invoke=_make_tracer(s.name)) for s in WATCHERS]
    monkeypatch.setattr(_runner, "WATCHERS", tracer_specs)
    # Reset per-day dedup so the call is clean.
    monkeypatch.setattr(_runner, "_dedup_state", {})
    monkeypatch.setattr(_runner, "_dedup_date", None)

    bar = pd.Series({
        "timestamp_et": pd.Timestamp("2026-05-20 10:00"),
        "open": 540.0, "high": 540.5, "low": 539.5, "close": 540.1, "volume": 300_000,
    })
    day_bars = pd.DataFrame([bar])
    ctx = _minimal_ctx(bar)

    out = run_all_watchers(
        bar, day_bars, 0, vol_baseline_20=300_000.0, ctx=ctx, vix_now=17.5,
        multi_day_rth=None, ribbon_state_dict=None,
    )

    assert isinstance(out, list)
    assert called == [s.name for s in WATCHERS], (
        "run_all_watchers did not invoke each registry spec exactly once in order"
    )


def test_one_broken_watcher_does_not_kill_the_loop(monkeypatch, capsys):
    """The T63 silent-failure guard survives the registry refactor: a raising
    invoke is logged to stderr and the remaining specs still run."""
    from lib.watchers.runner import WatcherSpec

    survived: list[str] = []

    def _ok(name: str):
        def _invoke(_deps, _name=name):
            survived.append(_name)
            return None
        return _invoke

    def _boom(_deps):
        raise ValueError("SYNTHETIC_REGISTRY_EXCEPTION")

    specs = [
        WatcherSpec("alpha_watcher", "detect_orb_break", _ok("alpha_watcher")),
        WatcherSpec("boom_watcher", "detect_v14_enhanced_setup", _boom),
        WatcherSpec("omega_watcher", "detect_bullish_setup", _ok("omega_watcher")),
    ]
    monkeypatch.setattr(_runner, "WATCHERS", specs)
    monkeypatch.setattr(_runner, "_dedup_state", {})
    monkeypatch.setattr(_runner, "_dedup_date", None)

    bar = pd.Series({
        "timestamp_et": pd.Timestamp("2026-05-20 10:05"),
        "open": 540.0, "high": 540.5, "low": 539.5, "close": 540.1, "volume": 300_000,
    })
    ctx = _minimal_ctx(bar)
    run_all_watchers(bar, pd.DataFrame([bar]), 0, 300_000.0, ctx, 17.5,
                     multi_day_rth=None, ribbon_state_dict=None)

    assert survived == ["alpha_watcher", "omega_watcher"], "loop did not continue past the raising spec"
    err = capsys.readouterr().err
    assert "SYNTHETIC_REGISTRY_EXCEPTION" in err and "boom_watcher" in err


# ── Cross-check: the runner source loops over WATCHERS (cheap structural guard) ─

def test_runner_source_iterates_WATCHERS():
    src = (_WATCHERS_DIR / "runner.py").read_text(encoding="utf-8")
    assert re.search(r"for\s+\w+\s+in\s+WATCHERS\b", src), (
        "runner.py no longer contains a `for ... in WATCHERS` loop — the registry "
        "may have been bypassed by a hand-wired chain again"
    )
