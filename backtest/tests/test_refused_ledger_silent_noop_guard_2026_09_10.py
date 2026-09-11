"""Guard: refused_setup_ledger must FAIL LOUD, never exit 0, when it writes nothing.

SCAR (W10, GOAL-WHY-THIS-WEEK-2026-09-10). `Gamma_RefusedSetupLedger`'s 14:20 ET fire on
2026-09-10 exited 0 in 8 seconds having written NOTHING to `analysis/refusals/` -- the
directory did not even exist. The exact internal mechanism was never pinned this session
(the launcher discards this task's stdout/stderr since its action omits `--log`, so no
traceback or clue survived anywhere), but the SHAPE of the bug was clear on inspection:
`main()` trusted `build()`'s in-memory return dict as proof of success and printed a
summary from it, without ever checking that the file `build()` claims to have written
actually landed on disk. Any future code path that returns a normal-looking `doc` without
completing the disk write -- a permissions blip, a redirected cwd, an early return, a
half-finished refactor -- reproduces the identical symptom: exit 0, nothing written,
nothing to explain it. This is C7 ("silent success is failure") textbook.

The fix adds `_build_and_verify()`: call `build()`, then check the output file actually
exists and is non-empty, and raise RuntimeError (never return 0) if it does not. This test
pins that behaviour by monkeypatching `build` itself to reproduce exactly the failure shape
(a normal-looking return with no disk write) and asserting `main()` refuses to report
success.

RED-PROOF (quoted in the W10 deliverable, not re-derived here): run this file's
`test_main_raises_when_build_writes_nothing_to_disk` against the pre-fix snapshot of
refused_setup_ledger.py (git commit cb6d19a3, the version with no `_build_and_verify` and
no verification step) -- it FAILS, because that `main()` returns 0 unconditionally once
`build()` returns. Run it against the current file -- it PASSES.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

rsl = importlib.import_module("refused_setup_ledger")


def _patch_out_dir(monkeypatch, tmp_path: Path) -> None:
    """Point the module's output paths at tmp_path. `RUN_LOG` only exists on the fixed
    module -- guarded with hasattr so this same test file runs unmodified against the
    pre-fix snapshot too (that absence is itself part of the RED proof: the old module
    had no independent evidence channel at all)."""
    monkeypatch.setattr(rsl, "OUT_DIR", tmp_path)
    if hasattr(rsl, "RUN_LOG"):
        monkeypatch.setattr(rsl, "RUN_LOG", tmp_path / "_run-log.jsonl")


def _fake_doc(date: str) -> dict:
    """A `build()` return value that looks entirely normal -- the exact shape the real
    function produces -- so any check keyed off the dict's *content* would pass. Only a
    check against the FILESYSTEM can catch this bug, which is the point."""
    return {
        "_meta": {
            "date": date, "generated_at_et": "2026-09-10T14:20:09",
            "builder": "setup/scripts/refused_setup_ledger.py",
            "shadow_only": "MEASUREMENT ONLY -- never places, arms, or edits a gate.",
            "min_score": 6, "min_triggers": 1, "ticks_read": 760,
            "unscored_note": "honest null, not a zero",
        },
        "n_episodes": 37, "n_scored": 0,
        "by_binding_blocker": {},
        "episodes": [],
    }


def test_build_and_verify_raises_when_output_missing(tmp_path, monkeypatch):
    """Unit-level: `_build_and_verify` must not trust a doc it cannot find on disk."""
    _patch_out_dir(monkeypatch, tmp_path)

    def fake_build(date, do_score, do_fetch):
        return _fake_doc(date)  # note: never writes tmp_path / f"{date}.json"

    monkeypatch.setattr(rsl, "build", fake_build)

    with pytest.raises(RuntimeError, match="does not exist / is empty"):
        rsl._build_and_verify("2026-09-10", False, False)


def test_build_and_verify_passes_when_output_present(tmp_path, monkeypatch):
    """Sanity counterpart: a build that DOES write must not be flagged."""
    _patch_out_dir(monkeypatch, tmp_path)

    def fake_build(date, do_score, do_fetch):
        doc = _fake_doc(date)
        (tmp_path / f"{date}.json").write_text("{}", encoding="utf-8")
        return doc

    monkeypatch.setattr(rsl, "build", fake_build)

    doc = rsl._build_and_verify("2026-09-10", False, False)
    assert doc["n_episodes"] == 37


def test_main_raises_when_build_writes_nothing_to_disk(tmp_path, monkeypatch):
    """End-to-end (the actual scar): `main()` must not silently exit 0 in this shape.

    This is the RED/GREEN-proofed test. Against the pre-fix snapshot (no
    `_build_and_verify`, no disk-verification step) this reproduces the live incident
    exactly: `main()` returns 0, `tmp_path` stays empty. Against the current file it
    raises, because `_build_and_verify` refuses to report success for a doc it cannot
    find on disk.
    """
    _patch_out_dir(monkeypatch, tmp_path)

    def fake_build(date, do_score, do_fetch):
        return _fake_doc(date)  # never writes -- the exact 2026-09-10 14:20 shape

    monkeypatch.setattr(rsl, "build", fake_build)
    monkeypatch.setattr(sys, "argv", ["refused_setup_ledger.py", "--date", "2026-09-10"])

    with pytest.raises(BaseException):
        rsl.main()

    # Whatever raised, the directory must still be empty -- confirming this is genuinely
    # the "wrote nothing" shape and not some unrelated failure.
    assert list(tmp_path.glob("*.json")) == []


def test_main_does_not_raise_on_a_real_write(tmp_path, monkeypatch):
    """Counter-proof: a normal, successful build must return 0 exactly as before --
    the new verification must not turn healthy runs into false alarms."""
    _patch_out_dir(monkeypatch, tmp_path)

    def fake_build(date, do_score, do_fetch):
        doc = _fake_doc(date)
        (tmp_path / f"{date}.json").write_text("{}", encoding="utf-8")
        return doc

    monkeypatch.setattr(rsl, "build", fake_build)
    monkeypatch.setattr(sys, "argv", ["refused_setup_ledger.py", "--date", "2026-09-10"])

    assert rsl.main() == 0
