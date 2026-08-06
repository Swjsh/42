"""ATM-TIER-EXTENSION-2K-10K per-arm KILL guard (2026-08-06 evening).

The extension's own frozen prereg (analysis/recommendations/
atm-tier-extension-2k10k-prereg-2026-08-03.json) set the kill criterion
"n>=10 fills/arm ... net<0 -> revert". risky-3 MET it: n=14 fills under the
extension, net -$653. risky-1 did NOT (n=11, +$903). Executing the kill for
risky-3 ONLY required a new mechanism because the prereg's one-line revert
(edit V15_BOLD_CORE_TIERS row 2 in place) hits EVERY consumer of the shared
table (core bold-2, j_intent bold, risky-1, safe-3):

  * crypto/lib/strike_selection.py gains V15_BOLD_CORE_PRE_EXT_TIERS
    (bold_core exactly as it stood 2026-07-18..2026-08-04: $0-2K ATM,
    $2K-10K OTM-2, $10-25K OTM-1, $25K+ ITM-2)
  * fleet_executor._tiers_for_arm gains the 'bold_core_pre_ext' branch
  * accounts.json risky-3 params_patch.strike_tier_table = 'bold_core_pre_ext'

Vary-and-assert (C14 -- the knob must be provably live, not dead):
  * risky-3 (live accounts.json) resolves OTM-2 in the $2K-10K band
  * risky-1 (live accounts.json) still resolves ATM there
  * flipping the SAME arm dict's patch value back to 'bold_core' flips the
    resolution back -- proving the config key, not an accident, drives it

RED-proof target: revert accounts.json risky-3 strike_tier_table to
'bold_core' -> test_risky3_resolves_otm2_at_5k fails.

Un-kill (one line): accounts.json risky-3 params_patch.strike_tier_table
back to 'bold_core'.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("automation/state/fleet", "crypto/lib", "backtest/lib", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import fleet_executor as fx  # noqa: E402

ss = fx.strike_selection  # the SAME module object _tiers_for_arm resolves against

ACCOUNTS = json.loads(
    (REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
ARMS_BY_ID = {a["id"]: a for a in ACCOUNTS["arms"]}


def test_risky3_resolves_otm2_at_5k():
    """THE KILL: risky-3 at $5K equity (the live 2K-10K band) prices OTM-2, not ATM."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID["risky-3"])
    assert tiers is ss.V15_BOLD_CORE_PRE_EXT_TIERS
    tier = ss.pick_tier(5_000.0, tiers)
    assert tier.strike_offset == -2 and tier.label == "OTM-2", (
        f"risky-3 $5K band must be OTM-2 after the pre-registered kill, got {tier}"
    )
    # C 748 spot -> 2 strikes OTM = 750
    assert ss.pick_strike(748.0, 5_000.0, "C", tiers) == 750


def test_risky1_keeps_atm_at_5k():
    """THE CONTROL: risky-1 (kill criterion NOT met, n=11 +$903) keeps the extension."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID["risky-1"])
    assert tiers is ss.V15_BOLD_CORE_TIERS
    tier = ss.pick_tier(5_000.0, tiers)
    assert tier.strike_offset == 0 and tier.label == "ATM"
    assert ss.pick_strike(748.0, 5_000.0, "C", tiers) == 748


def test_risky3_zero_to_2k_band_unchanged():
    """The 2026-08-01 extension ($0-2K ATM) is NOT part of this kill -- only 2K-10K."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID["risky-3"])
    tier = ss.pick_tier(1_750.0, tiers)
    assert tier.strike_offset == 0 and tier.label == "ATM"


def test_vary_and_assert_knob_is_live():
    """C14: the SAME arm dict with patch flipped back to 'bold_core' resolves ATM again --
    the accounts.json key, not anything else, carries the kill."""
    arm = copy.deepcopy(ARMS_BY_ID["risky-3"])
    arm["params_patch"]["strike_tier_table"] = "bold_core"
    tiers = fx._tiers_for_arm(arm)
    assert tiers is ss.V15_BOLD_CORE_TIERS
    assert ss.pick_tier(5_000.0, tiers).strike_offset == 0


def test_shared_table_untouched():
    """The kill must NOT have executed via the shared-table one-line revert: core bold-2 /
    j_intent / risky-1 / safe-3 still read $2K-10K = ATM off V15_BOLD_CORE_TIERS."""
    row = ss.pick_tier(5_000.0, ss.V15_BOLD_CORE_TIERS)
    assert row.strike_offset == 0 and row.label == "ATM", (
        "V15_BOLD_CORE_TIERS row 2 was edited in place -- that reverts EVERY consumer, "
        "not just risky-3; the per-arm kill must ride the bold_core_pre_ext branch instead"
    )


def test_pre_ext_table_matches_pre_08_04_shape():
    """V15_BOLD_CORE_PRE_EXT_TIERS is byte-equivalent to bold_core as of 2026-07-18..08-04."""
    expect = [(0.0, 2_000.0, 0, "ATM"), (2_000.0, 10_000.0, -2, "OTM-2"),
              (10_000.0, 25_000.0, -1, "OTM-1"), (25_000.0, 999_999_999.0, 2, "ITM-2")]
    got = [(t.equity_min, t.equity_max, t.strike_offset, t.label)
           for t in ss.V15_BOLD_CORE_PRE_EXT_TIERS]
    assert got == expect
