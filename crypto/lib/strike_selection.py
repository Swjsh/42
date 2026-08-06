"""strike_selection — per-tier OTM/ITM strike math (v15 doctrine).

Live source-of-truth (THIS file, `V15_SAFE_TIERS` / `V15_BOLD_TIERS` below):
  `setup/scripts/heartbeat_core.py` (the live core-Safe/Bold engine) calls
  `pick_strike()` against these hardcoded tables directly — it does NOT read
  `automation/state/params.json` for strike tiers. This has been true since
  2026-06-18 (commit 5da0da2), when the old account-specific `params_safe.json`
  / `params_bold.json` ladder files were retired in favor of these constants.

  V15_BOLD_TIERS (mirrors params.json#v15_strike_offset_per_tier, Bold/base):
    $0-$2K   : strike_offset = -3   (OTM-3)
    $2K-$10K : strike_offset = -2   (OTM-2)
    $10K-$25K: strike_offset = -1   (OTM-1)
    $25K+    : strike_offset = +2   (ITM-2)

  V15_SAFE_TIERS: ATM (0) under $10K, then slight ITM, then ITM-2 at $25K+.

Sim-lane source-of-truth (`automation/state/params.json#v15_strike_offset_per_tier`):
  `backtest/lib/orchestrator.py`'s `_apply_param_overrides` genuinely reads this
  key (T-09 per-tier equity-based strike selection) when a backtest supplies
  `account_equity` — it is a REAL, live consumer on the sim/backtest lane, not
  a dead knob, even though the live core path above no longer reads it. The two
  tables can drift; reconcile per Operating Principle 4 if they do. See
  analysis/deep-research/2026-07-11-strike-tier-reconciliation.md for the full
  three-way doc-drift writeup this docstring was corrected from.

Canonical formula (per `automation/prompts/heartbeat.md` line 254):
  BEAR puts:  strike = round(spot) + strike_offset   (positive = ITM, negative = OTM)
  BULL calls: strike = round(spot) - strike_offset   (mirror)

Sanity invariants any strike-selection must hold:
  For calls: ITM iff strike < spot; OTM iff strike > spot.
  For puts:  ITM iff strike > spot; OTM iff strike < spot.

Validator confirms both the tier lookup AND the sign convention via these
invariants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class StrikeTier:
    equity_min: float
    equity_max: float
    strike_offset: int
    label: str


# v15 Bold/base tier table — mirror of params.json#v15_strike_offset_per_tier
V15_BOLD_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     -3, "OTM-3"),
    StrikeTier(2_000.0,    10_000.0,    -2, "OTM-2"),
    StrikeTier(10_000.0,   25_000.0,    -1, "OTM-1"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)

# v15 Safe tier table — mirror of params_safe.json#v15_strike_offset_per_tier
V15_SAFE_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     0, "ATM"),
    StrikeTier(2_000.0,    10_000.0,    0, "ATM"),
    StrikeTier(10_000.0,   25_000.0,    1, "Slight ITM"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)

# --- V15_BOLD_CORE_TIERS -----------------------------------------------------------
# Core-Bold-ONLY candidate tier table. Identical to V15_BOLD_TIERS except the $0-$10K
# band is ATM (strike_offset=0) instead of OTM-3/OTM-2.
#   - $0-$2K ATM: original 2026-07-15 candidate, wired 2026-07-17/18 (see below).
#   - $2K-$10K ATM: ATM-TIER-EXTENSION-2K-10K, shipped 2026-08-04 after the $5,000
#     account rebuild (2026-08-02/03) silently moved EVERY bold_core consumer into the
#     then-OTM-2 $2K-$10K bracket, resurrecting the $0.30 min_entry_premium floor
#     collision this table exists to kill (EOD-2026-08-03-FULL-REVIEW.md section 4
#     structural wall #1: six elite clusters 11:51-14:00 priced $0.06-$0.18 OTM-2, ALL
#     floor-blocked, 33/35/35 SKIP_MIN_PREMIUM_FLOOR rows per fleet arm; safe-2 on
#     V15_SAFE_TIERS' ATM-through-$10K was the only account able to trade the afternoon).
#     Pre-registered BEFORE the code change (git-provable ordering):
#     analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json --
#     kill criterion n>=10 fills/arm or 10 sessions, net<0 -> one-line revert of the
#     $2K-$10K row back to StrikeTier(2_000.0, 10_000.0, -2, "OTM-2").
# Original $0-$2K source: the frozen strike-axis A/B,
# analysis/recommendations/bold-strike-axis-2026-07-15.json -- OTM-3 at this tier shows
# a structural floor-collision (afternoon premium-floor clearance 0.3376, i.e. ~66% of
# afternoon signals never clear min_entry_premium and are silently skipped) and
# -$14.37/tr OOS; ATM clears floor at 0.9688 afternoon / 0.9795 overall and is
# +$28.77/tr OOS, beats control, BH-FDR survivor, sub_window_stable, anchor
# no-regression (4 of 5 gates). See that file's near_miss_diagnostic for the full
# writeup, INCLUDING why it is NOT auto-shipped (next paragraph).
#
# WHY A NEW TABLE INSTEAD OF EDITING V15_BOLD_TIERS IN PLACE:
# V15_BOLD_TIERS is a SHARED surface with consumers beyond core Bold's heartbeat path.
# A direct edit to its $0-2K tier would silently change:
#   1. automation/state/fleet/fleet_executor.py:158 (_tiers_for_arm) -- any fleet arm
#      whose strike_tier_table resolves to "bold" reads V15_BOLD_TIERS directly. Per
#      automation/state/fleet/accounts.json (grid.sizing_profiles.safe / arm safe-3's
#      params_patch.strike_tier_table="bold"), safe-3 DELIBERATELY routes through this
#      table to get cheap OTM pricing at $2K equity ("OTM strikes... ATM doesn't place
#      this small"). risky-1 and risky-3 also resolve here via the id-prefix default
#      (_tiers_for_arm's fallback: "bold" for any non-"safe"-prefixed arm id).
#   2. setup/scripts/j_intent_executor.py:307 (resolve_symbol) -- the deterministic
#      executor for J-called conditional trades on the bold account ALSO reads
#      V15_BOLD_TIERS directly for account=="bold". This is a SECOND consumer not
#      identified by the original naive-fix investigation that led to this table's
#      creation; found independently via a full-repo grep before this table was added.
#      Flagged here so any future wiring decision considers it explicitly instead of
#      leaving J's manual conditional-trade path silently diverged from the heartbeat
#      path's strike tier.
# This table lets core Bold's heartbeat_core.py call site repoint to the new ATM
# behavior WITHOUT touching either consumer above. V15_BOLD_TIERS itself is
# byte-identical / untouched by this table's existence.
#
# STATUS UPDATE 2026-07-18: WIRED. Both live call sites (heartbeat_core.py's bold
# branch, j_intent_executor.py's bold branch) now read V15_BOLD_CORE_TIERS for
# account=="bold" / intent["account"]=="bold". Authorized by J's explicit in-chat
# "Yes -- wire Bold to ATM" (2026-07-17 night), which supersedes the WF-gate-pending
# hold below -- this was a PARTICIPATION fix (OTM-3 = 34% afternoon floor-clearance vs
# ATM's 97%), not a claim that the P&L evidence cleared all 5 auto-ratify gates; that
# regime-parked evidence is unchanged and still honestly disclosed as such. Revert =
# repoint both call sites back to V15_BOLD_TIERS (one line each). Falsification rail:
# first n>=20 live Bold fills under this tier get an expectancy check
# (automation/overnight/queue.md).
#
# STATUS AS OF 2026-07-15 evening (historical, pre-wiring): NOT WIRED into
# heartbeat_core.py, deliberately. This table exists and is guard-tested
# (backtest/tests/test_bold_core_strike_tier_2026_07_15.py) but the live call site
# (setup/scripts/heartbeat_core.py, the
# `ss.V15_BOLD_TIERS if account == "bold" else ss.V15_SAFE_TIERS` line) still points at
# V15_BOLD_TIERS. Two primary-source documents explicitly say this candidate is NOT
# yet ready to auto-ship:
#   - bold-strike-axis-2026-07-15.json's own near_miss_diagnostic.watch_tier_candidate
#     verdict_label: "WATCH -- NOT ship-ready (fails the pre-registered 5-gate bar,
#     specifically wf_ge_070)... near-miss worth a human/Fable look, not a same-night
#     or same-morning auto-ship." Its conditional_one_line_diff_if_a_future_decision_
#     waives_or_redefines_the_wf_gate section explicitly logs this exact diff as
#     "not_applied" / "NOT edited in this session."
#   - automation/overnight/queue.md's "WF-GATE-STRUCTURALLY-NULL" entry, filed the SAME
#     evening (2026-07-15), independently says: "until then every battery/scorecard
#     must disclose WF-null and rest on the remaining gates. Do NOT silently drop the
#     gate." and lists this exact candidate ("ATM cell for BOLD") as "re-adjudicate
#     once the WF redesign lands" -- i.e. a deliberate future decision, not a same-
#     session wire-up.
# Per this project's own OP-16 ("J is NOT a ratification gate... Auto-ratify requires
# OOS_positive AND WF >= 0.70 AND sub_window_stable AND anchor_no_regression") and
# OP-32 (gate-provenance / gate-redefinition questions route to P2/Opus judgment, not
# mechanical Sonnet execution), wiring this table into the live path requires that
# separate WF-gate re-adjudication to land first, not a same-evening flip on the
# strength of the near-miss argument alone. Revert-to-live-wire is a one-line change
# once that lands: point heartbeat_core.py's bold branch at V15_BOLD_CORE_TIERS instead
# of V15_BOLD_TIERS (and, per the second consumer above, decide then whether
# j_intent_executor.py's bold branch should move too).
V15_BOLD_CORE_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     0, "ATM"),
    StrikeTier(2_000.0,    10_000.0,    0, "ATM"),  # ATM-TIER-EXTENSION-2K-10K 2026-08-04 (was -2 OTM-2; revert = restore that one value)
    StrikeTier(10_000.0,   25_000.0,    -1, "OTM-1"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)

# --- V15_BOLD_CORE_PRE_EXT_TIERS ---------------------------------------------------
# ATM-TIER-EXTENSION-2K-10K PER-ARM KILL EXECUTION (2026-08-06 evening). The extension
# prereg (analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json)
# froze its kill criterion as "n>=10 fills/arm ... net<0 -> revert". risky-3 MET it
# (n=14 fills under the extension, net -$653) while risky-1 did NOT (n=11, +$903) and
# core bold-2 / safe-3 keep the extension. Because V15_BOLD_CORE_TIERS is a SHARED
# surface (core bold-2 heartbeat branch + j_intent_executor bold branch + every fleet
# arm whose strike_tier_table resolves 'bold_core'), the prereg's own one-line revert
# (edit row 2 in place) would have executed the kill on EVERY consumer -- the same
# shared-surface trap this file's own V15_BOLD_CORE_TIERS comment documents. So the
# per-arm kill gets its own table: byte-identical to V15_BOLD_CORE_TIERS as it stood
# 2026-07-18..2026-08-04 (pre-extension), reachable ONLY via
# fleet_executor._tiers_for_arm's 'bold_core_pre_ext' branch, selected ONLY by
# risky-3's accounts.json params_patch.strike_tier_table.
# Guard (vary-and-assert): backtest/tests/test_atm_tier_extension_risky3_kill_2026_08_06.py.
# Un-kill (one line): risky-3 params_patch.strike_tier_table back to "bold_core".
V15_BOLD_CORE_PRE_EXT_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     0, "ATM"),
    StrikeTier(2_000.0,    10_000.0,    -2, "OTM-2"),  # the killed extension row, pre-08-04 value
    StrikeTier(10_000.0,   25_000.0,    -1, "OTM-1"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)


def atm_strike(spot: float) -> int:
    """ATM strike = round(spot) to nearest dollar (matches simulator)."""
    return int(round(spot))


def pick_tier(equity: float, tiers: Sequence[StrikeTier] = V15_BOLD_TIERS) -> StrikeTier:
    """Find the tier where equity is in [equity_min, equity_max).

    Last tier acts as equity_min..infinity (inclusive both ends).
    Raises ValueError if equity is negative or no tier matches.
    """
    if equity < 0:
        raise ValueError(f"equity must be >= 0, got {equity}")
    for i, t in enumerate(tiers):
        is_last = i == len(tiers) - 1
        if t.equity_min <= equity < t.equity_max or (is_last and equity >= t.equity_min):
            return t
    raise ValueError(f"no tier matched equity={equity} (table covers $0-${tiers[-1].equity_max})")


def pick_strike(
    spot: float,
    equity: float,
    side: str,
    tiers: Sequence[StrikeTier] = V15_BOLD_TIERS,
) -> int:
    """Return the (integer) strike per the v15 tier-based formula.

    Args:
      spot: current SPY spot price
      equity: current account equity
      side: "C" for bullish calls, "P" for bearish puts
      tiers: tier table (V15_BOLD_TIERS or V15_SAFE_TIERS)

    Formula (per heartbeat.md line 254):
      BEAR puts:  strike = round(spot) + strike_offset
      BULL calls: strike = round(spot) - strike_offset
    """
    if side not in ("C", "P"):
        raise ValueError(f"side must be 'C' or 'P', got {side!r}")
    if spot <= 0:
        raise ValueError(f"spot must be positive, got {spot}")
    tier = pick_tier(equity, tiers)
    atm = atm_strike(spot)
    if side == "P":
        return atm + tier.strike_offset
    return atm - tier.strike_offset


def moneyness(strike: int, spot: float, side: str) -> str:
    """Classify strike as 'ITM' | 'ATM' | 'OTM' relative to spot, given side.

    ATM iff strike == round(spot).
    """
    atm = atm_strike(spot)
    if strike == atm:
        return "ATM"
    if side == "C":
        return "ITM" if strike < atm else "OTM"
    return "ITM" if strike > atm else "OTM"
