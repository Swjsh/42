"""arm_display.py -- single source of truth for turning a fleet arm id (or a read-surface
label built from one, e.g. "fleet:safe-3" / "core:safe") into J's human display_name.

WHY (2026-07-17, J: "i dont like how the arms are named currently"): the safe-1/safe-2/
safe-3/risky-1/risky-3/bold-2 scheme is confusing on its own merits (numbers carry no
meaning, "risky" vs "bold" is inconsistent) AND is actively dangerous -- safe-1 (retired)
and safe-2 point at the SAME broker account (PA3DHPT7KIQE, the 2026-07-11 repoint; see
accounts.json's safe-1._retired_doc / safe-2._repoint_2026_07_11), which caused a real
double-count in a report before this fix.

Arm ids stay EXACTLY as they are everywhere -- they are load-bearing keys across 80+
consumers (executor dispatch, decision ledgers, state-file directory names, secrets.json,
guard tests; see the accounts.json `_display_name_doc` field for the blast-radius note).
This module ONLY resolves a display label for READ surfaces (pings, briefs, reports). It is
NEVER used for keying, dispatch, or ledger writes -- callers that need the real id keep using
it directly; only what gets PRINTED changes.

Display names + the account last-4 live in accounts.json's per-arm "display_name" field.
This module is a thin, fail-open reader plus a couple of label-mapping helpers for the two
non-arms-array label shapes ("core:safe"/"core:bold" and the crypto twin) that existing read
surfaces already use.

Guard: backtest/tests/test_arm_display.py.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ACCOUNTS_PATH = REPO / "automation" / "state" / "fleet" / "accounts.json"

# core-decisions.jsonl's "account" field ("safe"/"bold") -> the arm id that owns it.
# Mirrors trade_today_watcher._CORE_ACCOUNT_FOR_ARM and participation_cascade.CORE_ARM_LABEL
# (NOT a new ownership mapping -- just the reverse lookup needed to resolve a display name
# for the same two short labels those modules already emit/consume).
CORE_LABEL_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}

CRYPTO_TWIN_DISPLAY = "CRYPTO-TWIN"

_ARMS_CACHE: "dict | None" = None


def _load_arms() -> dict:
    """id -> full arm dict from accounts.json. Fail-open -> {} on any read/parse error (a
    label lookup must never crash a read surface)."""
    try:
        data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {a["id"]: a for a in data.get("arms", []) if isinstance(a, dict) and a.get("id")}


def _arms(refresh: bool = False) -> dict:
    global _ARMS_CACHE
    if _ARMS_CACHE is None or refresh:
        _ARMS_CACHE = _load_arms()
    return _ARMS_CACHE


def display_name_for_arm_id(arm_id: str) -> str:
    """arm id ('safe-2', 'safe-3', ...) -> its accounts.json display_name, or the raw id
    unchanged if the arm is missing / has no display_name yet (fail-open)."""
    arm = _arms().get(arm_id)
    if not arm:
        return arm_id
    return arm.get("display_name") or arm_id


def display_name_for_label(label: str) -> str:
    """Resolve ANY label shape an existing read surface uses:
      'safe' / 'bold'              -> core-decisions.jsonl account field (heartbeat_core)
      'core:safe' / 'core:bold'    -> fill_funnel.py's funnel account keys
      'fleet:<arm-id>'             -> fill_funnel.py's funnel account keys
      '<arm-id>' directly          -> accounts.json arm id (pnl-statement per_day keys)
      'crypto-twin' / 'twin'       -> the crypto twin (not an accounts.json arm)
    Anything unrecognized passes through unchanged (fail-open -- never raises, never
    hides a label a caller doesn't yet know how to prettify)."""
    if not isinstance(label, str) or not label:
        return label
    if label in ("crypto-twin", "twin", "crypto_twin"):
        return CRYPTO_TWIN_DISPLAY
    if label.startswith("core:"):
        short = label.split(":", 1)[1]
        return display_name_for_arm_id(CORE_LABEL_TO_ARM.get(short, short))
    if label.startswith("fleet:"):
        return display_name_for_arm_id(label.split(":", 1)[1])
    if label in CORE_LABEL_TO_ARM:
        return display_name_for_arm_id(CORE_LABEL_TO_ARM[label])
    return display_name_for_arm_id(label)


if __name__ == "__main__":
    # Read-only self-check: print every arm's id -> display_name (no secrets touched).
    for arm_id, arm in sorted(_arms().items()):
        print(f"{arm_id:24} {arm.get('display_name', '(none)')}")
