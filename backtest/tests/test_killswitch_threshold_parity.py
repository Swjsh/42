"""Drift-ratchet: kill-switch threshold parity across params, breaker, and Rule 5.

WHY THIS EXISTS (graduated foot-gun, STAGE 4.5 learn-loop):
The Gamma-Bold daily-loss kill switch silently drifted to -60% in
``automation/state/aggressive/circuit-breaker.json`` while CLAUDE.md Rule 5 and
``aggressive/params.json#daily_loss_kill_switch_pct`` said -50%. Nothing
asserted the three sources had to agree, so the conflict sat as a HIGH
"awaiting-J-ratification" queue flag for days instead of failing loud at build
time. Reconciled 2026-06-21 (-60% -> -50%, the more-protective Rule-5 value).

This is the C9 (dual-account symmetry) + C14 (sync tracker to params) lesson
graduated from prose to a code assertion: the canonical Rule-5 thresholds are
hard-pinned here, and the live params + breaker files must match them. Any
future drift in ANY of the three sources now fails this test instead of
becoming a phantom backlog item.

Policy (mirrors test_state_contracts.py):
  * file ABSENT  -> skip with a note (fresh clone / single-account dev box).
  * file PRESENT but threshold mismatched -> FAIL (real drift -> report it).

Fail-open w.r.t. J: this is a dev/CI assertion only. It can never block, lock,
or kill J's interactive session, the heartbeat, or any order path -- it merely
surfaces drift loudly to a human.

Run:
    backtest/.venv/Scripts/python.exe -m pytest \
        backtest/tests/test_killswitch_threshold_parity.py -q
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

# Repo root = .../42  (this file is at 42/backtest/tests/)
REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# CANONICAL Rule-5 thresholds (CLAUDE.md "The 10 rules", Rule 5).             #
# These are the source of truth the live state files must match. Changing a   #
# trading threshold means editing Rule 5 *and* this constant in the same      #
# deliberate, J-ratified change -- which is exactly the friction we want.     #
# --------------------------------------------------------------------------- #
RULE5_SAFE_KILL_PCT = 0.30  # Gamma-Safe: -30% of start-of-day equity
RULE5_BOLD_KILL_PCT = 0.50  # Gamma-Bold: -50% of start-of-day equity

# Float comparison tolerance (these are exact decimals in JSON, but guard
# against 0.30000000004-style representation noise).
_TOL = 1e-9

# Relative paths + the key each file uses for the daily-loss threshold.
# NOTE the divergent breaker vocabulary (C9 symmetry trap): the SAFE breaker
# stores the limit under ``daily_loss_limit_pct`` while the BOLD breaker uses
# ``daily_loss_kill_switch_pct``. Both params files use the latter.
SAFE_PARAMS = ("automation/state/params.json", "daily_loss_kill_switch_pct")
BOLD_PARAMS = ("automation/state/aggressive/params.json", "daily_loss_kill_switch_pct")
SAFE_BREAKER = ("automation/state/circuit-breaker.json", "daily_loss_limit_pct")
BOLD_BREAKER = ("automation/state/aggressive/circuit-breaker.json", "daily_loss_kill_switch_pct")


def _load_threshold(rel_path: str, key: str) -> Optional[float]:
    """Return the float threshold at ``key`` in ``rel_path``, or None if the
    file is absent (skip signal). Raises if present-but-key-missing (that is a
    real contract break, not a skip)."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    assert key in data, (
        f"{rel_path} is present but is missing the kill-switch key '{key}'. "
        f"A producer dropped a consumed threshold field -- this is a contract "
        f"break, not a benign skip."
    )
    val = data[key]
    assert isinstance(val, (int, float)) and not isinstance(val, bool), (
        f"{rel_path}['{key}'] = {val!r} is not a number."
    )
    return float(val)


# --------------------------------------------------------------------------- #
# Each live source must equal its canonical Rule-5 threshold.                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "rel_path,key,expected",
    [
        (*SAFE_PARAMS, RULE5_SAFE_KILL_PCT),
        (*BOLD_PARAMS, RULE5_BOLD_KILL_PCT),
        (*SAFE_BREAKER, RULE5_SAFE_KILL_PCT),
        (*BOLD_BREAKER, RULE5_BOLD_KILL_PCT),
    ],
    ids=[
        "safe_params==rule5_safe(-30%)",
        "bold_params==rule5_bold(-50%)",
        "safe_breaker==rule5_safe(-30%)",
        "bold_breaker==rule5_bold(-50%)",
    ],
)
def test_threshold_matches_rule5(rel_path: str, key: str, expected: float) -> None:
    actual = _load_threshold(rel_path, key)
    if actual is None:
        pytest.skip(f"{rel_path} absent in this working copy")
    assert abs(actual - expected) < _TOL, (
        f"KILL-SWITCH DRIFT: {rel_path}['{key}'] = {actual} but CLAUDE.md "
        f"Rule 5 canonical is {expected}. Either the threshold drifted (fix the "
        f"file back to {expected}) or Rule 5 changed (update RULE5_*_KILL_PCT in "
        f"this test in the same J-ratified change). This is the -60%/-50% Bold "
        f"drift class -- do NOT just edit the constant to silence it."
    )


# --------------------------------------------------------------------------- #
# Cross-file parity: breaker must equal its own account's params (the literal  #
# producer/consumer pair the live gate reads).                                 #
# --------------------------------------------------------------------------- #
def test_safe_breaker_equals_safe_params() -> None:
    params = _load_threshold(*SAFE_PARAMS)
    breaker = _load_threshold(*SAFE_BREAKER)
    if params is None or breaker is None:
        pytest.skip("SAFE params or breaker absent in this working copy")
    assert abs(params - breaker) < _TOL, (
        f"SAFE kill-switch mismatch: params={params} vs breaker={breaker}. "
        f"The risk gate and the breaker file disagree on when to halt."
    )


def test_bold_breaker_equals_bold_params() -> None:
    params = _load_threshold(*BOLD_PARAMS)
    breaker = _load_threshold(*BOLD_BREAKER)
    if params is None or breaker is None:
        pytest.skip("BOLD params or breaker absent in this working copy")
    assert abs(params - breaker) < _TOL, (
        f"BOLD kill-switch mismatch: params={params} vs breaker={breaker}. "
        f"This is the exact -60%/-50% drift reconciled 2026-06-21 -- it must "
        f"never recur silently."
    )


# --------------------------------------------------------------------------- #
# C9 anti-symmetry: the two accounts have DIFFERENT risk profiles by design.   #
# A copy-paste that made Bold == Safe (or inverted them) is a foot-gun even if #
# each file is internally consistent.                                          #
# --------------------------------------------------------------------------- #
def test_bold_threshold_strictly_looser_than_safe() -> None:
    safe = _load_threshold(*SAFE_PARAMS)
    bold = _load_threshold(*BOLD_PARAMS)
    if safe is None or bold is None:
        pytest.skip("SAFE or BOLD params absent in this working copy")
    assert bold > safe + _TOL, (
        f"Account-symmetry trap (C9): Bold kill-switch ({bold}) must be a "
        f"LOOSER (larger) loss tolerance than Safe ({safe}) per Rule 5 "
        f"(Safe -30% / Bold -50%). They are equal or inverted -- check for a "
        f"copy-paste between the two account params files."
    )
