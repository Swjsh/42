"""Reconciliation test for the crypto-gym validator registry (Phase 0b — 2026-06-18).

THE BUG THIS GUARDS — the gym's "orphaned validator" class. New validators arrive
by convention (``validator-author`` writes ``crypto/validators/v{NN}_{slug}.py`` and
is *supposed* to register it in ``crypto/validators/runner.py``'s ``stages`` list). If
the registration step is skipped, the file exists on disk, passes its own offline
tests, and is NEVER RUN by the gym — silent dead coverage. The mirror failure is a
``stages`` entry (or import) pointing at a module that no longer exists.

This test makes both structurally detectable. The invariant:

    set(v*.py files on disk)  ==  set(modules wired into runner.stages)  ∪  EXCLUDED

It reconciles three layers against each other for every ``vNN`` module:
  1. file on disk            (``crypto/validators/v*.py``)
  2. imported in runner.py    (``from crypto.validators import ... vNN_*``)
  3. referenced in a stage    (``stages = [("vNN_*.offline", vNN_*.run_offline, ...)]``)

FAIL if a v*.py exists but no stage references it (the ORPHAN — authored-but-
unregistered), or a stage/import references a module with no file (the GHOST).
Intentional non-stage helpers live in an explicit, documented allowlist.

Pure static analysis — parses runner.py source + globs the directory. No gym run,
no network, runs in milliseconds. Belongs in pytest AND is import-safe for the gym.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]          # repo root
sys.path.insert(0, str(_REPO))

_VALIDATORS_DIR = _REPO / "crypto" / "validators"
_RUNNER_PATH = _VALIDATORS_DIR / "runner.py"


# ── Intentional exclusions (documented allowlist) ────────────────────────────
#
# A ``vNN_*.py`` file present on disk but DELIBERATELY not wired as a runner stage.
# Every entry needs a one-line reason. Empty today: every v01-v45 validator is a
# real gym stage. If a future validator is a shared helper / library module that
# legitimately should not run as its own stage, add it here with justification.
EXCLUDED_MODULES: dict[str, str] = {
    # "v99_shared_helpers": "library module imported by other validators, not a stage",
}


def _validator_module_files() -> set[str]:
    """Every ``vNN_*.py`` module name (stem) in crypto/validators (the fleet on disk).

    Restricted to the ``v\\d\\d_`` naming contract so ``runner.py``, ``__init__.py``,
    and any non-validator helper are not mistaken for validators.
    """
    out: set[str] = set()
    for p in _VALIDATORS_DIR.glob("v*.py"):
        if re.match(r"^v\d{2}_", p.name):
            out.add(p.stem)
    return out


def _runner_source() -> str:
    return _RUNNER_PATH.read_text(encoding="utf-8")


def _imported_modules(src: str) -> set[str]:
    """Module names pulled in by the ``from crypto.validators import ( ... )`` block.

    We scan the whole source for ``vNN_word`` import tokens — robust to the import
    being split across lines (it is, in runner.py).
    """
    # Capture the import block to avoid counting stage references as "imports".
    m = re.search(
        r"from\s+crypto\.validators\s+import\s*\((?P<body>.*?)\)",
        src,
        re.DOTALL,
    )
    body = m.group("body") if m else ""
    return set(re.findall(r"\bv\d{2}_\w+", body))


def _stages_block(src: str) -> str:
    """Isolate the ``stages = [ ... ]`` list body so we only count stage callables,
    not import tokens or comments elsewhere in the file. Brace-matched from
    ``stages = [`` to its closing ``]``."""
    start = re.search(r"\bstages\s*=\s*\[", src)
    if not start:
        return ""
    i = start.end() - 1  # at the opening '['
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    return src[i:]


def _stage_referenced_modules(src: str) -> set[str]:
    """Modules invoked inside the ``stages = [ ... ]`` list.

    Each stage entry is ``("vNN_name.mode", vNN_name.<entrypoint>, [...], {...})`` —
    the module appears as the attribute OWNER of the stage callable. The entrypoint is
    usually ``run_offline`` / ``run_live`` but some validators expose a differently-named
    entry (v02 → ``compare``, v15 → ``compare3``). We therefore capture ``vNN_name``
    wherever it owns ANY attribute access inside the stages block, so a module counts as
    "registered" only when it is actually wired as a stage (not merely imported). The
    stages block is isolated first so import tokens elsewhere are not miscounted.
    """
    block = _stages_block(src)
    return set(re.findall(r"\b(v\d{2}_\w+?)\.\w+", block))


# ── The core reconciliation ──────────────────────────────────────────────────

def test_every_validator_file_is_registered_as_a_stage():
    """No ORPHANS: every vNN_*.py on disk is invoked as a runner stage (minus allowlist)."""
    on_disk = _validator_module_files()
    src = _runner_source()
    staged = _stage_referenced_modules(src)
    excluded = set(EXCLUDED_MODULES)

    # Allowlist must reference real files (no stale exclusions).
    stale = excluded - on_disk
    assert not stale, f"EXCLUDED_MODULES names modules with no file: {sorted(stale)}"

    orphans = on_disk - staged - excluded
    assert not orphans, (
        f"ORPHAN validator(s) on disk but NOT invoked as a runner.stages stage: "
        f"{sorted(orphans)}. Register each in crypto/validators/runner.py (import + a "
        f"stages entry calling its run_offline/run_live), or add to EXCLUDED_MODULES "
        f"with a reason."
    )


def test_every_validator_file_is_imported():
    """Every staged/on-disk validator is also IMPORTED in runner.py.

    A stage cannot reference a module the file never imports — this catches the case
    where someone adds a stages line but forgets the import (NameError at gym run).
    """
    on_disk = _validator_module_files()
    imported = _imported_modules(_runner_source())
    excluded = set(EXCLUDED_MODULES)

    missing_import = on_disk - imported - excluded
    assert not missing_import, (
        f"validator file(s) present on disk but NOT imported in runner.py: "
        f"{sorted(missing_import)}. Add to the `from crypto.validators import (...)` block."
    )


def test_no_stage_without_a_file():
    """No GHOSTS: every staged module resolves to a real vNN_*.py on disk."""
    on_disk = _validator_module_files()
    staged = _stage_referenced_modules(_runner_source())
    ghosts = staged - on_disk
    assert not ghosts, (
        f"runner.stages references module(s) with no vNN_*.py file on disk: "
        f"{sorted(ghosts)} — a deleted/renamed validator still wired into the gym."
    )


def test_no_import_without_a_file():
    """No GHOST IMPORTS: every imported vNN_* module resolves to a real file."""
    on_disk = _validator_module_files()
    imported = _imported_modules(_runner_source())
    ghosts = imported - on_disk
    assert not ghosts, (
        f"runner.py imports vNN_* module(s) with no file on disk: {sorted(ghosts)}"
    )


def test_registry_is_exact_partition_of_disk():
    """The strong form: disk == staged ∪ excluded, with no overlap."""
    on_disk = _validator_module_files()
    staged = _stage_referenced_modules(_runner_source())
    excluded = set(EXCLUDED_MODULES)

    assert staged.isdisjoint(excluded), (
        f"module(s) both staged AND excluded: {sorted(staged & excluded)}"
    )
    assert on_disk == (staged | excluded), (
        f"validator fleet mismatch.\n  on_disk  = {sorted(on_disk)}\n"
        f"  staged   = {sorted(staged)}\n  excluded = {sorted(excluded)}"
    )


# ── Registry hygiene ─────────────────────────────────────────────────────────

def test_no_duplicate_validator_numbers():
    """Two files sharing the same vNN prefix (e.g. v29 + v32 both claiming a slot)
    is a renumbering smell. The number must uniquely identify a validator on disk.

    NOTE: this is advisory-strict — if a deliberate duplicate-number ever ships it
    can be allowlisted, but today every number should be unique.
    """
    nums: dict[str, list[str]] = {}
    for stem in _validator_module_files():
        m = re.match(r"^(v\d{2})_", stem)
        if m:
            nums.setdefault(m.group(1), []).append(stem)
    dupes = {n: sorted(v) for n, v in nums.items() if len(v) > 1}
    assert not dupes, f"duplicate validator number(s) on disk: {dupes}"


def test_runner_has_a_stages_list():
    """Cheap structural guard: runner.py still builds a `stages = [` list the loop
    iterates — if a refactor renamed it, the regexes above would silently match
    nothing and every test would vacuously pass."""
    src = _runner_source()
    assert re.search(r"\bstages\s*=\s*\[", src), (
        "runner.py no longer defines a `stages = [...]` list — the registry shape "
        "changed and this reconciliation test needs updating."
    )


def test_fleet_sanity_floor():
    """A floor so the parsing can't silently degrade to zero matches and pass."""
    on_disk = _validator_module_files()
    staged = _stage_referenced_modules(_runner_source())
    assert len(on_disk) >= 40, f"validator fleet unexpectedly small: {len(on_disk)}"
    assert len(staged) >= 40, f"staged validator set unexpectedly small: {len(staged)}"
