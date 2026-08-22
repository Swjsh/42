"""Guard: CLAUDE.md's account identifiers must match live wiring.

SCAR (2026-08-18): CLAUDE.md's Account-context table carried FOUR stale
identifiers simultaneously -- Safe-2 as PA3DHPT7KIQE and Risky-2 as
PA33W2KUAT40 (neither appears anywhere in the fleet registry), plus MCP key
prefixes PKZFN5G3/PKQMQD2N (neither appears in .mcp.json). Live truth,
broker-verified the same day: safe-2 = PA3POKNV46VG, bold-2 = PA3WEBXJU67N.
The fleet registry and both MCP servers agreed with each other the whole time
-- only the soul file, which EVERY session reads first, was wrong.

Why that is dangerous rather than cosmetic: a session running an OP-33
"broker-verified" check against PA3DHPT7KIQE is verifying an account that does
not exist, and would either error out or -- worse -- silently reason about the
wrong book. CLAUDE.md also mislabeled the aggressive MCP server as pointing at
"Risky-2" when it actually points at bold-2.

This guard is offline and pure: it reads the two tracked files and asserts
CLAUDE.md never names an account number the fleet registry does not know.
It deliberately does NOT call the broker (no network in tests) and does NOT
require .mcp.json (gitignored secret store) -- the key-prefix half is skipped
when that file is absent, so the guard runs green in a fresh clone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO / "CLAUDE.md"
ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"
MCP_JSON = REPO / ".mcp.json"

ACCT_RE = re.compile(r"PA[A-Z0-9]{10}")
KEY_RE = re.compile(r"PK[A-Z0-9]{6}")


# The FLEET registry is not the only account registry. The multi-symbol lane
# (2026-08-19) is a deliberate FORK of the SPY engine that never imports it, and it
# carries its own config under automation/state/multi/ -- including its account. Reading
# only fleet/accounts.json therefore reported the multi lane's REAL, configured account
# (PA38EG1JTFBT) as "absent from the registry", which is the opposite of true.
#
# Corrected 2026-08-21: consult every account registry the repo actually has. The guard's
# purpose is "CLAUDE.md must not name an account nothing is wired to" -- so the question
# is whether ANY live config knows the number, not whether one specific file does.
LANE_REGISTRIES = (
    REPO / "automation" / "state" / "multi" / "params.json",
)


def _registry_accounts() -> set[str]:
    data = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    found: set[str] = set()
    for arm in data.get("arms", []):
        acct = arm.get("account_number")
        if isinstance(arm, dict) and isinstance(acct, str) and ACCT_RE.fullmatch(acct):
            found.add(acct)
    # repoint/retirement notes carry historical numbers; accept those too so a
    # deliberate history reference in CLAUDE.md does not fail the guard.
    for blob in (json.dumps(data),):
        found.update(ACCT_RE.findall(blob))
    # ...plus every non-fleet lane that owns its own account config.
    for lane in LANE_REGISTRIES:
        if lane.is_file():
            found.update(ACCT_RE.findall(lane.read_text(encoding="utf-8", errors="replace")))
    return found


def test_registry_is_readable_and_nonempty() -> None:
    accts = _registry_accounts()
    assert accts, "fleet accounts.json yielded no PA account numbers -- guard cannot run"


def test_claude_md_names_only_known_accounts() -> None:
    """Every PA-account CLAUDE.md names must exist in the fleet registry."""
    doc = CLAUDE_MD.read_text(encoding="utf-8")
    named = set(ACCT_RE.findall(doc))
    assert named, "CLAUDE.md names no account numbers at all -- table likely gutted"
    unknown = sorted(named - _registry_accounts())
    assert not unknown, (
        f"CLAUDE.md names account(s) absent from accounts.json: {unknown}. "
        "Either the soul file is stale (fix CLAUDE.md against the registry) or "
        "the registry lost an arm (fix the registry). Do NOT delete this guard."
    )


def test_claude_md_carries_the_two_active_core_accounts() -> None:
    """The two accounts the core path actually trades must be documented."""
    doc = CLAUDE_MD.read_text(encoding="utf-8")
    data = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    wanted = {}
    for arm in data.get("arms", []):
        if arm.get("id") in ("safe-2", "bold-2") or arm.get("arm_id") in ("safe-2", "bold-2"):
            key = arm.get("id") or arm.get("arm_id")
            acct = arm.get("account_number")
            if isinstance(acct, str):
                wanted[key] = acct
    assert wanted, "neither safe-2 nor bold-2 found in registry -- schema changed?"
    missing = {arm: acct for arm, acct in wanted.items() if acct not in doc}
    assert not missing, (
        f"CLAUDE.md does not name the live account(s) for {sorted(missing)}: {missing}. "
        "The soul file must carry the account numbers the core path actually trades."
    )


@pytest.mark.skipif(not MCP_JSON.exists(), reason=".mcp.json is gitignored; absent in fresh clones")
def test_claude_md_key_prefixes_match_mcp_json() -> None:
    """Documented MCP key prefixes must exist in the real credential store."""
    doc_prefixes = {p for p in KEY_RE.findall(CLAUDE_MD.read_text(encoding="utf-8"))}
    if not doc_prefixes:
        pytest.skip("CLAUDE.md documents no PK key prefixes")
    raw = MCP_JSON.read_text(encoding="utf-8")
    real_prefixes = set(KEY_RE.findall(raw))
    stale = sorted(doc_prefixes - real_prefixes)
    assert not stale, (
        f"CLAUDE.md documents MCP key prefix(es) absent from .mcp.json: {stale}. "
        "A rotated key was not reflected in the soul file."
    )
