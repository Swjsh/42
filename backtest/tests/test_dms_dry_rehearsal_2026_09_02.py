"""Guards for the dead-man's switch's rehearsal path and its out-of-hours evidence.

WHY THIS EXISTS. Gamma_DeadMansSwitch was registered 2026-09-01 and its first PRODUCTION
fire is 2026-09-02 09:32 ET. Trying to pre-flight it the morning of found two things:

  1. `if not is_rth(et): return 0` returned SILENTLY -- no log, no snapshot. A gated no-op
     was byte-identical to "the task never fired" and to "it crashed before writing
     anything". Three states, one empty result (C7).
  2. Consequently the switch's real path could not be exercised even once outside market
     hours, so its FIRST EVER execution would have been in production, on a live position.
     A safety instrument nobody can rehearse is a safety instrument nobody has tested.

The fix lets DMS_DRY=1 force the full path at any hour. That is only safe because of ONE
invariant, and the first test here is that invariant: the sole mutating call in the file is
`close_all_spy_options(..., live=(not DRY))`, so a dry run cannot place an order at any
hour. If a future edit adds a second broker-mutating call, or hardcodes live=True, the
bypass stops being safe and that test must fail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DMS = REPO / "setup" / "scripts" / "dead_mans_switch.py"


@pytest.fixture(scope="module")
def src() -> str:
    return DMS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------
# THE invariant that makes the out-of-hours bypass safe.
# ---------------------------------------------------------------------------------------

def test_only_one_mutating_broker_call_exists(src: str):
    """The bypass is safe because there is exactly one order path to reason about."""
    # Count CALL SITES via the AST. A substring search cannot: the module docstring names
    # the primitive in prose ("FLATTEN via fleet_broker.close_all_spy_options (the same
    # primitive ...)") and my first cut of this test failed on that false positive. Three
    # guards this session were bitten the same way -- see
    # automation/overnight/_lesson-inbox/2026-09-02-string-search-cannot-answer-code-questions.md
    # Do NOT "simplify" this back to a regex.
    import ast

    tree = ast.parse(src)
    calls = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "close_all_spy_options"]
    assert len(calls) == 1, (
        f"{len(calls)} calls to close_all_spy_options (lines {calls}) -- the dry-run bypass "
        "was justified on there being exactly one order path; re-verify every call before "
        "keeping it"
    )

    # And that the ONE call really is gated on DRY, positionally.
    live_kw_ok = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "close_all_spy_options"
        and any(kw.arg == "live" and isinstance(kw.value, ast.UnaryOp)
                and isinstance(kw.value.op, ast.Not) for kw in n.keywords)
        for n in ast.walk(tree))
    assert live_kw_ok, "the order call no longer passes live=(not DRY) as a keyword"


def test_the_order_path_is_gated_on_dry(src: str):
    """live=(not DRY) is what makes DMS_DRY=1 incapable of placing an order."""
    assert "live=(not DRY)" in src, (
        "the flatten call no longer derives `live` from DRY -- a dry run could now place a "
        "real order, and the out-of-hours bypass must be removed until it does again"
    )
    assert "live=True" not in src, "a hardcoded live=True defeats the dry-run contract"


def test_dry_is_read_from_the_environment_not_a_literal(src: str):
    assert 'DRY = os.environ.get("DMS_DRY", "0") == "1"' in src


# ---------------------------------------------------------------------------------------
# Out-of-hours must leave evidence, and DRY must get past the gate.
# ---------------------------------------------------------------------------------------

def test_out_of_hours_is_not_a_silent_return(src: str):
    """The original `if not is_rth(et): return 0` wrote nothing at all."""
    assert 'if not is_rth(et) and not DRY:' in src, (
        "the out-of-hours branch no longer excludes DRY -- the switch cannot be rehearsed"
    )
    gated = src.split("if not is_rth(et) and not DRY:", 1)[1].split("return 0", 1)[0]
    assert "_write_state_snapshot" in gated, (
        "the gated branch returns without writing a snapshot -- a gated fire is once again "
        "indistinguishable from a dead task"
    )
    assert '"gated": "outside_rth"' in gated


def test_dry_out_of_hours_logs_that_it_forced_the_gate(src: str):
    """A forced run must announce itself, or a reader of the log cannot tell a rehearsal
    from a real RTH fire."""
    assert "DMS_DRY_OUT_OF_HOURS" in src


def test_snapshot_is_overwritten_not_appended(src: str):
    """The gated branch writes on every out-of-hours fire. That is only acceptable because
    the snapshot is a single overwritten file, not an append-only ledger."""
    assert "_write_state_snapshot" in src
    body = src.split("def _write_state_snapshot", 1)[1][:800]
    assert '"a"' not in body and "append" not in body.lower(), (
        "the snapshot writer looks like it appends -- an every-fire write would then grow "
        "without bound"
    )


# ---------------------------------------------------------------------------------------
# The rehearsal actually reached the broker. Anchors the 2026-09-02 pre-flight result.
# ---------------------------------------------------------------------------------------

def test_recorded_rehearsal_checked_every_active_arm():
    """The pre-flight on 2026-09-02 06:10 ET reached the broker for all four active arms and
    returned STALE_BUT_FLAT on each -- engine stale overnight, zero open positions, nothing
    to flatten. If a later change breaks credential loading or the roster read, this file
    still exists but per_arm empties out, and that is the regression to catch."""
    import json
    snap = REPO / "automation" / "state" / "dead-mans-switch.json"
    if not snap.exists():
        pytest.skip("no snapshot on disk yet")
    data = json.loads(snap.read_text(encoding="utf-8"))
    if data.get("gated") == "outside_rth":
        pytest.skip("latest snapshot is a gated no-op, not a checked run")
    per_arm = data.get("per_arm") or {}
    assert per_arm, "a non-gated run checked zero arms -- roster or creds read is broken"
    for arm, row in per_arm.items():
        assert row.get("action"), f"{arm} recorded no action"
        assert row.get("action") != "READ_FAILED", (
            f"{arm}: broker read failed -- the switch cannot verify position state, and by "
            "its own contract it will refuse to flatten. That is fail-closed and correct, "
            "but it means the arm is UNPROTECTED and must be investigated."
        )
