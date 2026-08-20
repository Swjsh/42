"""Guard: the Bold ATM strike tier stays reverted, and both sites move together.

HISTORY
  2026-07-18 (commit 718e0809) repointed Bold's $0-2K strike tier from OTM-3
  (`V15_BOLD_TIERS`) to ATM (`V15_BOLD_CORE_TIERS`). It FAILED its own
  auto-ratify gate at ship time and was allowed to run only under a standing
  falsification rail (`setup/scripts/bold_tier_rail.py`, escalation n=20).

  2026-08-20 THE RAIL FIRED. At n=25 post-ship fills: -$808, WR 24%, mean
  -$32/fill, against the pre-ship OTM-3 tier's +$406 on 4 at WR 50%
  (`automation/state/bold-tier-rail.json`, rail_status TRIGGERED_NEGATIVE).
  J: "so #2 is asking if I want to retire a strat that is losing? i guess so
  yeah". Reverted.

WHY A GUARD AND NOT JUST A COMMIT
  A pre-registered rail is only worth anything if triggering it actually changes
  behaviour. This test is the thing that makes the revert stick, and it pins the
  two-site invariant: `heartbeat_core.py` (engine path) and `j_intent_executor.py`
  (J-called path) must resolve the SAME bold tier. A split re-creates the exact
  engine/J divergence the 2026-07-18 wire was written to close.

TO RE-SHIP ATM LATER: run the auto-ratify gate FIRST, then flip both sites and
update this test in the same commit — deliberately, not by drift.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HEARTBEAT = REPO / "setup" / "scripts" / "heartbeat_core.py"
J_INTENT = REPO / "setup" / "scripts" / "j_intent_executor.py"
RAIL_JSON = REPO / "automation" / "state" / "bold-tier-rail.json"

# The bold-branch tier selection on each path.
_PICK = re.compile(r"ss\.(V15_BOLD_\w+)\s+if\s+(?:account|intent\[.account.\])\s*==\s*.bold.")


def _bold_tier_in(path: Path) -> str:
    src = path.read_text(encoding="utf-8", errors="replace")
    # Ignore comment lines: the revert rationale legitimately NAMES the old symbol.
    live = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    m = _PICK.search(live)
    assert m, "no bold tier selection found in %s" % path.name
    return m.group(1)


def test_heartbeat_bold_tier_is_reverted_to_otm():
    assert _bold_tier_in(HEARTBEAT) == "V15_BOLD_TIERS", (
        "heartbeat_core.py is back on the ATM tier that its own falsification rail "
        "killed at n=25 / -$808. Re-run the auto-ratify gate before re-shipping."
    )


def test_j_called_path_bold_tier_is_reverted_to_otm():
    assert _bold_tier_in(J_INTENT) == "V15_BOLD_TIERS", (
        "j_intent_executor.py is back on the ATM tier the rail killed."
    )


def test_both_paths_resolve_the_same_bold_tier():
    """The invariant that outlives this particular revert."""
    hb, ji = _bold_tier_in(HEARTBEAT), _bold_tier_in(J_INTENT)
    assert hb == ji, (
        "engine path uses %s but the J-called path uses %s — a split strike tier is "
        "the exact divergence the 2026-07-18 wire existed to close." % (hb, ji)
    )


def test_rail_verdict_still_says_the_atm_tier_lost():
    """If someone re-ships ATM, it must be because the EVIDENCE changed."""
    if not RAIL_JSON.exists():
        pytest.skip("bold-tier-rail.json not generated yet; run bold_tier_rail.py")
    d = json.loads(RAIL_JSON.read_text(encoding="utf-8"))
    post, pre = d.get("post_ship", {}), d.get("pre_ship", {})
    assert post.get("n", 0) >= d.get("escalation_n", 20), (
        "rail has not reached its escalation n yet: %r" % post
    )
    assert post.get("net_usd", 0) < 0, (
        "post-ship ATM P&L is no longer negative (%r) — the revert may be re-litigable, "
        "but do it through the auto-ratify gate, not by editing this test." % post
    )
    assert post["net_usd"] < pre.get("net_usd", 0), (
        "ATM tier no longer underperforms the OTM-3 tier it replaced: %r vs %r"
        % (post, pre)
    )
