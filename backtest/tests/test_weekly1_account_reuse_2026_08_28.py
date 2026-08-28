"""Guard: the weekly-1 / risky-3 shared-account invariant (2026-08-28).

WHY THIS FILE EXISTS
--------------------
J retired the risky-3 SPY cell and re-tasked its Alpaca paper account
(PA3V7JT25H6Z) to the weekly-1 non-SPY options lane.

That reuse is only safe because the SPY lane stopped scanning the account.
`fleet_broker.is_flat_spy_options` / `close_all_spy_options` (and four duplicate
sites) filter `symbol.startswith("SPY")`. A GLD or QQQ position sitting in an
account the SPY fleet still scanned would be **invisible** to both the flat-check
and EOD-flatten -- the engine would happily open a SPY position "into a flat
account" that is not flat, and the EOD flattener would leave the non-SPY leg
open over the weekend. That is an automated, permanent C11 violation.

So the invariant is: **at most one active lane may own a given account_number.**
The specific instance that matters today is risky-3 vs weekly-1. Re-activating
risky-3 without first un-wiring weekly-1 turns this file RED before it can reach
a trading session.

This suite reads ONLY `accounts.json` -- no credentials, no network.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"

SHARED_ACCOUNT = "PA3V7JT25H6Z"


def _arms() -> list[dict]:
    return json.loads(ACCOUNTS.read_text(encoding="utf-8"))["arms"]


def _by_id(arm_id: str) -> dict:
    for a in _arms():
        if a.get("id") == arm_id:
            return a
    pytest.fail(f"arm {arm_id!r} is missing from accounts.json")


# ---------------------------------------------------------------------------
# THE INVARIANT
# ---------------------------------------------------------------------------
def test_no_account_number_is_owned_by_two_active_arms():
    """The general form. Two ACTIVE arms on one account means two lanes place
    orders into the same book and each sees the other's positions as its own."""
    owners: dict[str, list[str]] = defaultdict(list)
    for a in _arms():
        acct = a.get("account_number")
        if acct and a.get("status") == "active":
            owners[acct].append(a.get("id"))
    clashes = {acct: ids for acct, ids in owners.items() if len(ids) > 1}
    assert not clashes, (
        f"account(s) claimed by more than one ACTIVE arm: {clashes}. "
        "Two lanes trading one account cannot both flat-check correctly."
    )


def test_risky3_is_retired_while_weekly1_holds_its_account():
    """The specific instance. risky-3 may not come back while weekly-1 owns
    PA3V7JT25H6Z -- the SPY flat-check is symbol-scoped to SPY and would be
    blind to weekly-1's GLD/QQQ/NVDA positions."""
    risky3, weekly1 = _by_id("risky-3"), _by_id("weekly-1")
    if weekly1.get("account_number") != SHARED_ACCOUNT:
        pytest.skip("weekly-1 no longer holds the shared account; invariant moot")
    assert risky3.get("account_number") == SHARED_ACCOUNT
    assert risky3.get("status") != "active", (
        "risky-3 has been re-activated while weekly-1 still owns "
        f"{SHARED_ACCOUNT}. Un-wire weekly-1 FIRST. The SPY flat-check filters "
        "symbol.startswith('SPY'), so weekly-1's non-SPY positions are invisible "
        "to it -- the SPY engine would trade into an account it wrongly believes "
        "is flat, and EOD-flatten would not close the non-SPY leg."
    )
    assert risky3.get("live") is False


def test_weekly1_is_not_armed_without_a_signal():
    """The weekly v1 signal is REFUTED -- all four expiry arms lose and every one
    FAILS the random-entry null (WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md). Wiring
    an account is not an edge. Arming this lane needs a signal that clears its
    own null first, and flipping status to 'active' is what would arm it."""
    weekly1 = _by_id("weekly-1")
    assert weekly1.get("status") != "active", (
        "weekly-1 has been set active. The weekly v1 signal fails its random-entry "
        "null; there is nothing validated for this lane to trade. If a NEW signal "
        "has cleared, update why_status_is_pending_build with the evidence and "
        "then change this test deliberately."
    )
    assert weekly1.get("live") is False


def test_weekly1_is_not_a_spy_arm():
    """It must never inherit SPY instrument handling -- that is the whole point
    of giving it its own account."""
    weekly1 = _by_id("weekly-1")
    assert weekly1.get("instrument") == "WEEKLY_OPTION_MULTI"
    assert "SPY" not in (weekly1.get("underlyings") or []), (
        "weekly-1 must not trade SPY -- SPY belongs to the core/fleet lane, and "
        "overlapping them on one account reintroduces the flat-check blindness."
    )


def test_retirement_and_reuse_are_documented_not_silent():
    """A future session must be able to reconstruct WHY this account moved lanes
    without archaeology. These fields are the trail."""
    risky3, weekly1 = _by_id("risky-3"), _by_id("weekly-1")
    assert risky3.get("retired_at"), "risky-3 retirement is undated"
    assert "premium" in (risky3.get("retired_reason") or "").lower(), (
        "risky-3's retirement reason should name the premium-stop question it "
        "was closed over"
    )
    assert weekly1.get("account_provenance"), "weekly-1 does not record where its account came from"
    assert weekly1.get("hard_prerequisite_met"), (
        "weekly-1 does not record the risky-3-must-be-retired prerequisite"
    )


def test_starting_equity_was_not_reset_to_a_placeholder():
    """The account carries the retired cell's realised P&L. Resetting it to a
    round 5000.0 would fabricate an evidence trail (the 2026-07-11 repoint scar)."""
    weekly1 = _by_id("weekly-1")
    eq = weekly1.get("starting_equity")
    assert eq is not None
    assert eq != 5000.0, (
        "starting_equity looks like the doc template's placeholder rather than the "
        "broker-verified balance the account actually carried over."
    )
    assert weekly1.get("starting_equity_note"), "the non-placeholder equity is unexplained"
