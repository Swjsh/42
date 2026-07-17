"""Guard for accounts.json's `display_name` field, added 2026-07-17 (J: "i dont like how
the arms are named currently" -- safe-1/safe-2/safe-3/risky-1/risky-3/bold-2 carries no
meaning on its own AND safe-1/safe-2 sharing ONE broker account (PA3DHPT7KIQE) caused a real
double-count in a report). Arm ids are UNCHANGED and remain the load-bearing key everywhere
(see the file's `_display_name_doc`); this guard only covers the NEW display_name field:

  1. Every ACTIVE arm has a non-empty display_name.
  2. All display_names present are UNIQUE (no two arms read the same on a status line).
  3. safe-1's display_name explicitly flags that it shares CORE-SAFE's account (the exact
     scenario that caused the double-count this field exists to prevent).
  4. Every display_name that names a real broker account embeds that account's last-4
     characters, so two arms sharing an account are visually identical by construction
     (never two different-looking labels hiding the same account).

Runs under pytest OR standalone (mirrors this directory's existing test style, e.g.
test_duplicate_account_guard.py).
"""
from __future__ import annotations

import json
from pathlib import Path

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"


def _load_accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def test_every_active_arm_has_a_display_name() -> None:
    accounts = _load_accounts()
    missing = [a["id"] for a in accounts["arms"]
               if a.get("status") == "active" and not a.get("display_name")]
    assert not missing, f"active arm(s) with no display_name: {missing}"


def test_every_arm_has_a_display_name() -> None:
    """Stronger than the active-only check above -- retired/dormant/pending arms get one
    too (safe-1's RETIRED label and the two futures arms' dormant/pending labels are exactly
    the disambiguating information J asked for), so nothing in the roster is unlabeled."""
    accounts = _load_accounts()
    missing = [a["id"] for a in accounts["arms"] if not a.get("display_name")]
    assert not missing, f"arm(s) with no display_name at all: {missing}"


def test_display_names_are_unique() -> None:
    accounts = _load_accounts()
    names = [a["display_name"] for a in accounts["arms"] if a.get("display_name")]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"display_name collision(s), no longer unambiguous: {dupes}"


def test_safe1_display_name_flags_the_shared_account() -> None:
    """The exact 2026-07-11 repoint scenario (safe-1 retired, shares safe-2's account) must
    be self-evident from safe-1's display_name alone -- this is the concrete fix for the
    double-count J hit."""
    accounts = _load_accounts()
    arm_by_id = {a["id"]: a for a in accounts["arms"]}
    safe1 = arm_by_id.get("safe-1")
    assert safe1 is not None, "safe-1 missing from accounts.json"
    name = safe1.get("display_name", "")
    assert "RETIRED" in name.upper(), f"safe-1 display_name must flag it is retired: {name!r}"
    # must reference the account it shares (CORE-SAFE, or the shared account's last-4)
    safe2 = arm_by_id.get("safe-2", {})
    acct2 = str(safe2.get("account_number", ""))
    last4 = acct2[-4:] if len(acct2) >= 4 else ""
    assert (last4 and last4 in name) or "CORE-SAFE" in name.upper(), (
        f"safe-1 display_name must reference the shared account it points at: {name!r}")


def test_display_names_sharing_an_account_embed_the_same_last4() -> None:
    """Any two arms that share a real account_number must show the SAME last-4 in their
    display_name (or at least one of them must, per the RETIRED-labeling exception above) --
    proves the naming scheme actually prevents the double-count, not just documents it once."""
    accounts = _load_accounts()
    by_account: dict[str, list[dict]] = {}
    for a in accounts["arms"]:
        acct = a.get("account_number")
        if acct:
            by_account.setdefault(acct, []).append(a)
    for acct, arms in by_account.items():
        if len(arms) < 2:
            continue
        last4 = acct[-4:]
        for a in arms:
            name = a.get("display_name", "")
            assert last4 in name or "RETIRED" in name.upper(), (
                f"{a['id']!r} shares account ...{last4} with {[x['id'] for x in arms if x is not a]} "
                f"but its display_name {name!r} doesn't show it")


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
