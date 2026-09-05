"""Guard: roster_liveness.flag_known_broken must not silently ignore a monkeypatched
(or otherwise reassigned) module-level STATUS_MD.

ROOT CAUSE (GOAL-RIG-SIGNAL-HYGIENE-2026-09-05 H4): STATUS.md's Known-broken section
carried `ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m` -- but "p::m"
is not, and has never been, a real provider/model pair in automation/state/model-
roster.json (grepped: absent). A same-day live probe (roster_liveness.py, run
2026-09-05) found ZERO dead_id lanes: 4/5 live, the one DOWN lane (ollama::qwen3:14b) is
class="error" (APITimeoutError, a local Ollama timeout), not "dead_id". So the line was
never a real finding.

The actual source: backtest/tests/test_roster_liveness_alerting_2026_08_29.py's
test_main_returns_nonzero_only_when_a_lane_is_dead does
`monkeypatch.setattr(rl, "STATUS_MD", tmp_path / "STATUS.md")` then calls `rl.main()`.
main() calls `flag_known_broken(dead)` with NO status_md kwarg -- same as production.
Pre-fix, flag_known_broken's signature was
`def flag_known_broken(dead, status_md: Path = STATUS_MD) -> bool`, and Python binds a
default argument value ONCE, at function-definition time (module import) -- so that
default was always the ORIGINAL real automation/overnight/STATUS.md path, never the
monkeypatched one, no matter what `rl.STATUS_MD` was reassigned to afterward. Running
that test's dead_id case for real therefore wrote a synthetic "p::m" ROSTER-LIVENESS
line straight into the real STATUS.md -- test pollution masquerading as a live finding.

FIX: status_md now defaults to None and is resolved against the CURRENT module-level
STATUS_MD inside the function body, so a bare call always sees whatever STATUS_MD is at
call time (patched or not).

test_flag_known_broken_default_is_not_a_frozen_path is the RED proof: it inspects the
live function signature directly (no file writes, so it is safe to run against either
the broken or fixed code) and fails on the pre-fix code, where the default was the bound
Path object rather than None.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))
import roster_liveness as rl  # noqa: E402


def test_flag_known_broken_default_is_not_a_frozen_path() -> None:
    """RED-PROOF: pre-fix this default was `rl.STATUS_MD` (a Path object) bound at
    import time -- the exact late-binding-default-argument defect that let
    test_main_returns_nonzero_only_when_a_lane_is_dead's monkeypatch.setattr(rl,
    "STATUS_MD", ...) get silently ignored by main()'s bare flag_known_broken(dead) call,
    and that wrote a synthetic "p::m" line into the real STATUS.md. Post-fix the default
    is None (resolved lazily inside the function against the current module attribute).
    """
    default = inspect.signature(rl.flag_known_broken).parameters["status_md"].default
    assert default is None, (
        f"status_md defaults to {default!r} -- a value frozen at import time. A bare "
        "flag_known_broken(dead) call (as main() makes) will use THIS frozen value even "
        "after monkeypatch.setattr(rl, 'STATUS_MD', ...) reassigns the module attribute, "
        "silently writing to the wrong file (this is how the real STATUS.md got a "
        "synthetic 'p::m' ROSTER-LIVENESS line from a test run)."
    )


def test_bare_call_honors_reassigned_module_status_md(tmp_path, monkeypatch) -> None:
    """Behavioral proof the fix works: reassigning rl.STATUS_MD and then calling
    flag_known_broken with NO status_md kwarg (exactly how main() calls it) must write
    to the reassigned path, never to whatever STATUS_MD was at import time.
    """
    patched = tmp_path / "STATUS.md"
    patched.write_text("## Known broken\n\n", encoding="utf-8")
    monkeypatch.setattr(rl, "STATUS_MD", patched)

    dead = [{"lane": "openrouter::fake/dead-model:free"}]
    assert rl.flag_known_broken(dead) is True  # bare call, no status_md kwarg
    out = patched.read_text(encoding="utf-8")
    assert "fake/dead-model" in out, "write did not land at the reassigned STATUS_MD path"


def test_explicit_status_md_kwarg_still_wins_over_module_default(tmp_path) -> None:
    """Explicit status_md= (production's real call sites, and other tests) must still
    take priority over the module-level STATUS_MD -- the fix only changes what happens
    when the caller omits the kwarg.
    """
    explicit = tmp_path / "explicit.md"
    explicit.write_text("## Known broken\n\n", encoding="utf-8")
    dead = [{"lane": "openrouter::fake/dead-model:free"}]
    assert rl.flag_known_broken(dead, status_md=explicit) is True
    assert "fake/dead-model" in explicit.read_text(encoding="utf-8")


def test_no_pa3_style_dead_lane_in_current_roster_probe() -> None:
    """Sanity-anchor for H4's finding: 'p::m' is not, and never has been, a real
    provider/model pair anywhere in model-roster.json's lane definitions.
    """
    roster = rl.sc.load_roster()
    lanes = rl.unique_lanes(roster)
    keys = {rl.sc._lane_key(ln) for ln in lanes}
    assert "p::m" not in keys, (
        "a lane literally keyed 'p::m' exists in model-roster.json -- if so, H4's "
        "conclusion (synthetic test data, not a real dead lane) needs re-checking"
    )
