"""Duplicate-account guard (2026-07-14, ultracode-review Job 3a).

The safe-1/safe-2 repoint (2026-07-11, see accounts.json's safe-1._retired_doc /
safe-2._repoint_2026_07_11) left TWO fleet arms pointed at the SAME broker account
(PA3DHPT7KIQE) by design -- safe-2 is the live production arm, safe-1 is retired
and must never place orders again. fleet_live._arm_is_processable /
fleet_executor.run_dry both gate order dispatch on status=='active', so the retired
arm is currently safe -- but nothing has ever asserted that mechanically. If safe-1
(or any future retired/dormant arm) is ever flipped back to 'active' while it still
shares an account with another active arm, that is a live double-fill /
misattribution risk with zero warning.

TWO checks, no live network calls (per JOB 3a instructions -- live REST verification
was run ONCE, 2026-07-14, and its results pinned to
automation/state/fleet/live-verified-account-numbers-2026-07-14.json; re-run the
same probe and refresh that fixture whenever a credential rotates or an account is
repointed):

  1. FIXTURE STILL AGREES WITH THE LIVE SOURCE FILES: every arm present in the
     pinned fixture must still resolve (live_account_number) to the SAME
     account_number accounts.json currently declares for it. A mismatch means
     accounts.json changed since the fixture was recorded and the guard is stale --
     RED on purpose, forcing a live re-verification instead of trusting drifted data.
  2. NO TWO ENABLED (status=='active') ARMS SHARE AN ACCOUNT NUMBER, checked against
     accounts.json's CURRENT contents directly (not the fixture) -- this is the
     actual safety property, and it must hold structurally regardless of whether the
     fixture is fresh.

Runs under pytest OR standalone (mirrors this directory's existing test style).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
SECRETS_PATH = FLEET_DIR / "secrets.json"
LIVE_VERIFIED_PATH = FLEET_DIR / "live-verified-account-numbers-2026-07-14.json"


def _load_accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def _load_secrets() -> dict:
    data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return data.get("accounts", data)


def _load_live_verified() -> dict:
    return json.loads(LIVE_VERIFIED_PATH.read_text(encoding="utf-8"))


def _arms_by_id(accounts: dict) -> dict:
    return {a["id"]: a for a in accounts["arms"]}


def test_every_active_arm_has_a_secrets_entry() -> None:
    """Every arm accounts.json marks 'active' must have live-loadable credentials --
    an active arm with no key/secret pair is a silent no-op dispatch, not a safety
    issue this guard covers directly, but a precondition for check 2 meaning anything
    (an active arm accounts.json can't authenticate for is not verifiably distinct
    from any other account)."""
    accounts = _load_accounts()
    secrets = _load_secrets()
    active_ids = [a["id"] for a in accounts["arms"] if a.get("status") == "active"]
    missing = [aid for aid in active_ids if aid not in secrets]
    assert not missing, f"active arm(s) with no secrets.json credentials: {missing}"


def test_fixture_still_agrees_with_accounts_json() -> None:
    """The pinned live-verification snapshot must still match accounts.json's
    CURRENT declared account_number for every arm it covers. If this REDs,
    accounts.json changed since 2026-07-14 (credential rotation, new repoint, etc.)
    and the fixture is stale -- re-run the live GET /v2/account probe (see this
    file's module docstring / fleet_broker.load_creds) and refresh
    live-verified-account-numbers-2026-07-14.json (or a dated successor) before
    trusting this guard again."""
    accounts = _load_accounts()
    arm_by_id = _arms_by_id(accounts)
    fixture = _load_live_verified()

    drifted = []
    for arm_id, rec in fixture["arms"].items():
        current = arm_by_id.get(arm_id)
        if current is None:
            drifted.append(f"{arm_id}: no longer present in accounts.json")
            continue
        current_account = current.get("account_number")
        if current_account != rec["live_account_number"]:
            drifted.append(
                f"{arm_id}: fixture pinned live_account_number={rec['live_account_number']!r} "
                f"but accounts.json now declares {current_account!r}"
            )
    assert not drifted, (
        "fixture drifted from accounts.json -- re-verify live and refresh the "
        "fixture:\n  " + "\n  ".join(drifted)
    )


def test_no_two_active_arms_share_an_account_number() -> None:
    """THE actual safety property: within accounts.json's CURRENT contents, no two
    arms with status=='active' may declare the same account_number. Retired/dormant/
    pending_build arms sharing an account with an active arm (the safe-1/safe-2
    shape) is fine and expected -- only two SIMULTANEOUSLY-active arms on one
    account is the double-fill/misattribution risk."""
    accounts = _load_accounts()
    active_arms = [a for a in accounts["arms"] if a.get("status") == "active"]

    by_account: dict[str, list[str]] = defaultdict(list)
    for a in active_arms:
        acct = a.get("account_number")
        assert acct, f"active arm {a['id']!r} has no account_number set"
        by_account[acct].append(a["id"])

    dupes = {acct: ids for acct, ids in by_account.items() if len(ids) > 1}
    assert not dupes, (
        f"two or more ACTIVE fleet arms resolve to the same broker account_number "
        f"-- double-fill/misattribution risk: {dupes}"
    )


def test_retired_safe1_shares_safe2s_account_and_must_stay_retired() -> None:
    """Named regression pin for the exact 2026-07-11 repoint scenario (not just the
    general property above): safe-1 and safe-2 share PA3DHPT7KIQE by design, and
    that is ONLY safe because safe-1 is 'retired'. If a future session flips safe-1
    back to 'active' without also moving it (or safe-2) to a distinct account, this
    test REDs immediately -- it does not wait for the general duplicate check to
    catch it as one dupe among many."""
    accounts = _load_accounts()
    arm_by_id = _arms_by_id(accounts)
    safe1 = arm_by_id.get("safe-1")
    safe2 = arm_by_id.get("safe-2")
    assert safe1 is not None and safe2 is not None, "safe-1/safe-2 arms missing from accounts.json"

    if safe1.get("account_number") == safe2.get("account_number"):
        assert safe1.get("status") != "active", (
            "safe-1 shares safe-2's account_number AND is status=='active' -- this "
            "is the exact double-fill risk the 2026-07-11 repoint's retirement of "
            "safe-1 exists to prevent. Do not re-enable safe-1 without first moving "
            "it (or safe-2) to a distinct broker account."
        )


def test_known_shared_account_annotation_matches_reality() -> None:
    """The fixture's own 'known_shared_account_by_design' block must still describe
    a TRUE, currently-safe exception (not a stale note masking a live problem)."""
    accounts = _load_accounts()
    arm_by_id = _arms_by_id(accounts)
    fixture = _load_live_verified()
    known = fixture.get("known_shared_account_by_design")
    if not known:
        return
    acct = known["account_number"]
    ids = known["arms"]
    declared = {arm_by_id[i]["account_number"] for i in ids if i in arm_by_id}
    assert declared == {acct}, (
        f"known_shared_account_by_design claims arms {ids} share {acct!r}, but "
        f"accounts.json now declares {declared} for them -- update or remove the annotation"
    )
    active_among_them = [i for i in ids if arm_by_id.get(i, {}).get("status") == "active"]
    assert len(active_among_them) <= 1, (
        f"more than one arm in the documented shared-account exception is now "
        f"'active': {active_among_them} -- the annotation assumed only one could be"
    )


if __name__ == "__main__":
    import sys

    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
