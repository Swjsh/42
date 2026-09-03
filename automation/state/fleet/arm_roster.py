"""arm_roster -- ONE definition of "which arms are live", read from accounts.json.

09-29 SAFETY BUNDLE component (work-order §3: "safe-2 retirement mechanics (ACCOUNTS from
accounts.json, not hardcoded)"). New leaf module; adopting callers land with the bundle.

WHY THIS EXISTS, measured rather than assumed. 66 modules read `accounts.json` independently,
and at least twelve carry a HARDCODED arm tuple instead. Those tuples disagree with each other
and with reality: `risky-3` was retired 2026-08-28 and is still named in eight of them;
`safe-1` is still named in three; `journal_calendar` lists only the fleet arms and omits the
core pair entirely. So "which arms are live" currently has a dozen answers.

That is the exact failure the work order recorded as a THIRD SIGHTING: risky-3's retirement
silently invalidated a prereg (`ladder-x-premium`), the cheap-contract boost lane, and its own
exit A/B leg, because "a retired arm's dependents are not swept". safe-2's retirement is the
next one scheduled, and it is a CORE arm -- a wider blast radius than risky-3's.

THE SEMANTICS ARE LIFTED, NOT INVENTED. `active_arms()` is the proven definition already in
`eod_flatten._active_arms`, which has run on the live flatten path for weeks:
  * `account_number` must start with "PA" -- skips futures/sim arms, which are not SPY options;
  * `status` must be exactly "active" -- skips retired and pending_build;
  * an unreadable registry falls back to the two core arms, because flattening SOMETHING beats
    flattening nothing.
Reproducing it here (rather than importing eod_flatten, which would drag the broker path into
every reader) is deliberate; `test_arm_roster_matches_eod_flatten_semantics` pins the two
against each other so they cannot drift.

HARDCODED ROSTERS ARE NOT ALL WRONG. A module that backfills HISTORY legitimately needs retired
arms -- their fills really happened. So the companion guard does not ban hardcoded tuples; it
requires each one to be DECLARED with a reason, and fails on any new or undeclared one. The
goal is that an arm retirement can never again be silent, not that every list becomes dynamic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"

# Same fallback as eod_flatten._active_arms: the two core arms. Never an empty list -- a reader
# that gets [] would silently do nothing, which is the failure mode this module exists to end.
CORE_FALLBACK = ("safe-2", "bold-2")

SPY_ACCOUNT_PREFIX = "PA"


def _load(path: Optional[Path] = None) -> Optional[dict]:
    try:
        return json.loads((path or ACCOUNTS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _arms(reg: dict) -> list:
    arms = reg.get("arms", reg)
    if isinstance(arms, dict):
        return list(arms.values())
    return list(arms) if isinstance(arms, list) else []


def _is_spy_options_arm(arm: dict) -> bool:
    acct = arm.get("account_number")
    return isinstance(acct, str) and acct.startswith(SPY_ACCOUNT_PREFIX)


def _arm_id(arm: dict) -> Optional[str]:
    aid = arm.get("id") or arm.get("arm_id")
    return str(aid) if aid else None


def active_arms(path: Optional[Path] = None) -> list[str]:
    """SPY-options arms with status == 'active'. Never empty."""
    reg = _load(path)
    if reg is None:
        return list(CORE_FALLBACK)
    out = []
    for arm in _arms(reg):
        if not isinstance(arm, dict) or not _is_spy_options_arm(arm):
            continue
        if str(arm.get("status") or "").lower() != "active":
            continue
        aid = _arm_id(arm)
        if aid:
            out.append(aid)
    return out or list(CORE_FALLBACK)


def retired_arms(path: Optional[Path] = None) -> list[str]:
    """SPY-options arms explicitly marked retired. The set a sweep must check dependents against.

    Empty on an unreadable registry -- unlike active_arms, there is no safe fallback to invent
    here, and claiming an arm is retired when we cannot read the file would be worse than
    saying nothing.
    """
    reg = _load(path)
    if reg is None:
        return []
    out = []
    for arm in _arms(reg):
        if not isinstance(arm, dict) or not _is_spy_options_arm(arm):
            continue
        if str(arm.get("status") or "").lower() == "retired":
            aid = _arm_id(arm)
            if aid:
                out.append(aid)
    return out


def all_spy_arms(path: Optional[Path] = None) -> list[str]:
    """Every SPY-options arm regardless of status -- the correct roster for HISTORICAL work,
    where a retired arm's past fills are real data and excluding them would restate history."""
    reg = _load(path)
    if reg is None:
        return list(CORE_FALLBACK)
    out = [aid for arm in _arms(reg)
           if isinstance(arm, dict) and _is_spy_options_arm(arm)
           for aid in (_arm_id(arm),) if aid]
    return out or list(CORE_FALLBACK)


def is_active(arm_id: str, path: Optional[Path] = None) -> bool:
    return arm_id in active_arms(path)
