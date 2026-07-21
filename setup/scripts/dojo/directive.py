"""dojo/directive.py -- DojoDirective: parse, validate, and ledger-serialize J's spoken
per-arm trade directives captured during a DOJO replay session.

Run by the SESSION AGENT (Sonnet + J), never a broker -- see DOJO-ARCHITECTURE-DECISION.md's
directive.py contract. `session.py`'s `cmd_directive` calls `parse_and_validate(raw)` on a
json.loads()-ed dict, then `to_ledger_row(d)` to append it to the session ledger, and reads
`d.id` / `d.arms` off the result. This module extends the EXISTING j-intent schema
(setup/scripts/j_intent_logic.py) rather than forking a parallel one: side/trigger/exits
validation reuse those real primitives (see `_shape_check_via_j_intent`), and `exits` uses
the SAME exit_patch vocabulary the live fleet already validates against
(automation/state/fleet/fleet_executor.EXIT_PATCH_ALLOWED_KEYS, derived from
strategies.ExitShape's dataclass fields -- never hand-duplicated here).

FAIL LOUD: every violation raises `ValueError` with a specific, actionable message. A
directive J spoke that the schema literally cannot express is exactly a LANE-A harvest item
(DOJO-REPLAY-TRAINING-SPEC.md's two-lane split) -- the caller is expected to catch the
ValueError and log it as a capability gap, not paper over it here.

HARD FENCE: this module imports NO alpaca/broker module and performs no git operations
(guard-tested in backtest/tests/test_dojo_fence.py alongside the rest of the dojo package).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# --- path setup (mirror futures_edge3_sim.py / dojo/session.py's own bootstrap): make
# sibling engine modules importable. Duplicated here (not imported from session.py, which is
# frozen/owned by another builder) because each dojo module bootstraps independently --
# this file must work when imported standalone (e.g. from the test suite) too. ---
_ROOT = Path(__file__).resolve().parents[3]  # .../42
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import arm_display  # noqa: E402 -- setup/scripts/arm_display.py: CORE_LABEL_TO_ARM ("safe"/"bold")
import fleet_executor  # noqa: E402 -- automation/state/fleet/fleet_executor.py: EXIT_PATCH_ALLOWED_KEYS
import j_intent_logic  # noqa: E402 -- setup/scripts/j_intent_logic.py: reused validation primitives

ET = ZoneInfo("America/New_York")
ACCOUNTS_PATH = _ROOT / "automation" / "state" / "fleet" / "accounts.json"

VALID_SIDES = ("C", "P")
REQUIRED_RAW_FIELDS = ("issued_et", "cursor_et", "arms", "side", "trigger", "exits", "sizing")


# =============================================================================== the dataclass
@dataclass(frozen=True)
class DojoDirective:
    """J's structured per-arm trade directive, captured mid-replay-session. Field set + types
    match DOJO-ARCHITECTURE-DECISION.md's frozen directive.py contract exactly:
    id, issued_et, cursor_et, arms(list[str]), side, trigger, invalidation, exits, sizing,
    note, dojo(bool=True). `issued_et`/`cursor_et` are tz-aware ET datetimes (package-wide
    convention set by clock.py); `to_ledger_row` is what turns them back into JSON-safe
    strings for the ledger -- this dataclass itself is the in-memory, richer representation.

    `arms` is typed `list[str]` per the frozen contract (not `tuple`) even though this
    dataclass is `frozen=True` -- `frozen` blocks attribute *reassignment* (`d.arms = [...]`
    raises), not in-place list mutation; callers should treat the returned list as read-only
    by convention, matching the contract's literal type rather than silently upgrading it to
    a tuple and risking a shape mismatch with session.py's `d.arms` read."""

    id: str
    issued_et: datetime
    cursor_et: datetime
    arms: list
    side: str
    trigger: dict
    invalidation: dict
    exits: dict
    sizing: dict
    note: str = ""
    dojo: bool = True


# =================================================================================== roster
def _load_valid_arms() -> frozenset:
    """Known arm ids: the two core account aliases (arm_display.CORE_LABEL_TO_ARM's keys --
    'safe'/'bold', the SAME short labels core-decisions.jsonl already uses) union every
    ACTIVE arm id in accounts.json (today: safe-3, safe-2, risky-1, bold-2, risky-3 -- safe-1
    is retired, the two futures arms are pending_build/dormant, so none of those three are
    valid dojo targets). Loaded fresh on every call (no module-level cache): a dojo session
    is a long-running interactive process and a roster change (an arm retired/activated mid-
    day) must be picked up without a restart -- do not cache this."""
    try:
        data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot load arm roster from {ACCOUNTS_PATH}: {e}") from e
    active = {
        a["id"]
        for a in data.get("arms", [])
        if isinstance(a, dict) and a.get("status") == "active" and a.get("id")
    }
    return frozenset(active | set(arm_display.CORE_LABEL_TO_ARM.keys()))


def _validate_arms(raw_arms: Any) -> list:
    if not isinstance(raw_arms, list) or not raw_arms:
        raise ValueError(f"arms must be a non-empty list of arm ids, got {raw_arms!r}")
    valid = _load_valid_arms()
    out = []
    for a in raw_arms:
        if not isinstance(a, str):
            raise ValueError(f"each arm id must be a string, got {a!r}")
        if a not in valid:
            raise ValueError(
                f"unknown arm id {a!r} -- valid arms are {sorted(valid)} "
                "(the two core account aliases from arm_display.CORE_LABEL_TO_ARM, union "
                "every status=='active' arm id in accounts.json)"
            )
        out.append(a)
    return out


# ============================================================================= exit_patch
def _validate_exit_patch(raw_exits: Any) -> dict:
    """`exits` must be a dict whose keys are all in fleet_executor.EXIT_PATCH_ALLOWED_KEYS --
    the SAME frozenset (derived from strategies.ExitShape's dataclass fields) the live fleet
    validates accounts.json's params_patch.exit_patch against. Never hand-duplicated: an
    ExitShape field addition automatically becomes a valid dojo exit key with no second edit
    here, exactly mirroring fleet_executor._validate_exit_patch's own reasoning."""
    if not isinstance(raw_exits, dict):
        raise ValueError(f"exits must be a dict, got {type(raw_exits).__name__}")
    allowed = fleet_executor.EXIT_PATCH_ALLOWED_KEYS
    unknown = set(raw_exits) - allowed
    if unknown:
        raise ValueError(
            f"exits has unknown exit_patch key(s) {sorted(unknown)} -- valid keys are "
            f"{sorted(allowed)} (strategies.ExitShape schema, via "
            "fleet_executor.EXIT_PATCH_ALLOWED_KEYS -- do not invent keys the exit manager "
            "can't read)"
        )
    return dict(raw_exits)


# ============================================================================ j-intent reuse
def _shape_check_via_j_intent(raw: dict, directive_id: str, issued_et: datetime) -> None:
    """Reuse j_intent_logic.validate_intent's structural checks for the fields DojoDirective
    shares with the j-intent schema (side in {C,P}; trigger is a dict with a 'type' in the
    known vocabulary; exits/sizing are dicts) instead of re-deriving them a second time --
    "extend, do not fork" per DOJO-ARCHITECTURE-DECISION.md. `account`/`status` are dojo-
    irrelevant fields on that schema, so a known-valid dummy stands in for them; any error
    naming one of those two dummies would be a bug in this shim, not a real validation
    failure of J's directive, so it is excluded from what gets raised to the caller."""
    synthetic = {
        "id": directive_id,
        "created_et": issued_et.isoformat(),
        "account": "safe",  # dummy -- always valid; not a dojo-relevant field
        "side": raw.get("side"),
        "trigger": raw.get("trigger"),
        "sizing": raw.get("sizing"),
        "exits": raw.get("exits"),
        "status": "armed",  # dummy -- a freshly-captured dojo directive is always "armed"
    }
    err = j_intent_logic.validate_intent(synthetic)
    if err and not err.startswith("account must be"):
        raise ValueError(f"directive fails j-intent shape check: {err}")


def _parse_et_timestamp(value: Any, field_name: str) -> datetime:
    """issued_et/cursor_et must be a full ISO8601 ET timestamp string -- reuses
    j_intent_logic.parse_et's own parser (the same primitive the live j-intent schema uses
    for its 'created_et'/'expiry_et' fields) rather than re-deriving a parser, then localizes
    the naive-ET result to tz-aware ET per this package's convention (clock.py: "All
    datetimes tz-aware ET"). Rejects parse_et's bare-'HH:MM' sentinel-year (1900) escape
    hatch -- a dojo directive always needs a real calendar date, never a time-of-day alone."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be an ISO8601 ET timestamp string, got {value!r}"
        )
    try:
        dt = j_intent_logic.parse_et(value)
    except (ValueError, IndexError) as e:
        raise ValueError(f"{field_name} is not a parseable timestamp: {value!r} ({e})") from e
    if dt.year == 1900:
        raise ValueError(
            f"{field_name} must be a full timestamp, not a bare time-of-day: {value!r}"
        )
    return dt.replace(tzinfo=ET)


# =================================================================================== public
def parse_and_validate(raw: dict) -> DojoDirective:
    """Parse + validate a J-directed dojo trade directive from a raw dict (already
    `json.loads()`-ed by `session.cmd_directive`). Fails LOUD: raises `ValueError` with a
    specific, actionable message on the FIRST violation found; never returns a partially-
    valid directive."""
    if not isinstance(raw, dict):
        raise ValueError(f"directive must be a JSON object, got {type(raw).__name__}")

    for name in REQUIRED_RAW_FIELDS:
        if name not in raw:
            raise ValueError(f"directive missing required field {name!r}")

    issued_et = _parse_et_timestamp(raw["issued_et"], "issued_et")
    cursor_et = _parse_et_timestamp(raw["cursor_et"], "cursor_et")

    directive_id = raw.get("id") or (
        f"dojo-{issued_et:%Y%m%d-%H%M%S}-{str(raw.get('side', 'x')).lower()}"
    )
    if not isinstance(directive_id, str) or not directive_id.strip():
        raise ValueError(f"directive id must be a non-empty string, got {directive_id!r}")

    arms = _validate_arms(raw["arms"])

    # reuse: side in {C,P}; trigger is a dict with a known trigger.type; exits/sizing are dicts
    _shape_check_via_j_intent(raw, directive_id, issued_et)

    side = raw["side"]
    if side not in VALID_SIDES:  # belt-and-suspenders: the shim above already caught this
        raise ValueError(f"side must be one of {VALID_SIDES}, got {side!r}")

    trigger = raw["trigger"]

    invalidation = raw.get("invalidation") or {}
    if not isinstance(invalidation, dict):
        raise ValueError(f"invalidation must be a dict, got {type(invalidation).__name__}")

    exits = _validate_exit_patch(raw["exits"])

    sizing = raw["sizing"]
    if not isinstance(sizing, dict):
        raise ValueError(f"sizing must be a dict, got {type(sizing).__name__}")

    note = raw.get("note") or ""
    if not isinstance(note, str):
        raise ValueError(f"note must be a string, got {type(note).__name__}")

    dojo_flag = raw.get("dojo", True)
    if dojo_flag is not True:
        raise ValueError(
            "dojo directives must carry dojo=True (or omit the field) -- this schema is "
            "never used to author a live j-intent"
        )

    return DojoDirective(
        id=directive_id,
        issued_et=issued_et,
        cursor_et=cursor_et,
        arms=arms,
        side=side,
        trigger=dict(trigger),
        invalidation=dict(invalidation),
        exits=exits,
        sizing=dict(sizing),
        note=note,
        dojo=True,
    )


def to_ledger_row(d: DojoDirective) -> dict:
    """JSON-serializable dict for the session ledger (`session._append_ledger`'s row shape --
    plain dicts + primitives only, no datetime objects). Round-trips through `json.dumps`."""
    return {
        "id": d.id,
        "issued_et": d.issued_et.isoformat(),
        "cursor_et": d.cursor_et.isoformat(),
        "arms": list(d.arms),
        "side": d.side,
        "trigger": dict(d.trigger),
        "invalidation": dict(d.invalidation),
        "exits": dict(d.exits),
        "sizing": dict(d.sizing),
        "note": d.note,
        "dojo": d.dojo,
    }
