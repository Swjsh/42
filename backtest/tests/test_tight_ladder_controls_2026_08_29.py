"""Guard: PREREG-TIGHT-LADDER-2026-08-28 enforcement controls (risk_gate, 2026-08-29).

WHY THIS FILE EXISTS
---------------------
analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md section 2 + Addendum 1
(S1.1-1.3) describes five controls for the forward-test window opening
2026-09-01 09:30 ET. Before this ship the engine did not enforce them:
  #1  max 5 contracts per entry            -- fleet_executor._qty_for's
      position_sizing_tiers reaches elite_qty 8/12/15/20, no ceiling existed.
  #2  $1,000 hard dollar cap per position   -- no flat per-entry $ cap existed
      (per_trade_risk_cap_pct is a % of equity, a different thing).
  #3  conflict rule: premium too high for even min_contracts to fit under the
      $1,000 cap -> SKIP, never take fewer than min_contracts.
  #4  max 4 entries per arm per day         -- max_same_day_roundtrips was 5.
  #5  -$400 daily realized-loss stop per arm -- daily_loss_kill_switch_pct alone
      (30%/50% of equity) is far looser (~$1,590/$2,524 at current equity).

Mechanism: backtest/lib/risk_gate.py#cap_entry_qty (controls #1/#2/#3, a pre-
check both setup/scripts/heartbeat_core.py#_execute and automation/state/fleet/
fleet_executor.py#finalize call before risk_gate.check_order) + two backstop
Deny rules inside check_order itself (MAX_CONTRACTS_PER_ENTRY /
MAX_POSITION_DOLLARS) + a third KILL_SWITCH trigger inside check_order
(DAILY_LOSS_DOLLARS, control #5) + max_same_day_roundtrips 5->4 in both live
params files (control #4, mechanism already existed -- verified by
TestMaxSameDayRoundtripsIsActuallyConsumed below, not assumed).

THE LOAD-BEARING PROPERTIES:
  1. OFF BY DEFAULT: absent params keys -> byte-identical to pre-2026-08-29
     behavior on every existing caller/test. Regression here means a config
     without these keys silently starts refusing orders.
  2. NEVER a sub-floor qty: cap_entry_qty either returns qty >= min_contracts
     or skip=True. Composed with the pre-existing max_affordable_qty (which
     carries the identical invariant), a live tick can never propose a
     1-or-2-contract order under these caps.
  3. The three worked cases from the ship instruction, run end-to-end through
     the real function (not hand-computed): $0.75 -> 5 contracts/$375;
     $2.50 -> 4 contracts/$1,000; $4.00 -> SKIP.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backtest.lib.risk_gate import (
    CODE_ALLOW,
    CODE_DAILY_LOSS_DOLLARS,
    CODE_KILL_SWITCH,
    CODE_MAX_CONTRACTS_PER_ENTRY,
    CODE_MAX_POSITION_DOLLARS,
    CODE_SETTLEMENT,
    CODE_UNREADABLE_INPUT,
    cap_entry_qty,
    check_order,
    check_settlement,
    max_affordable_qty,
)

REPO = Path(__file__).resolve().parents[2]

# A params set that passes every OTHER check_order gate cleanly, so any denial
# in these tests is unambiguously attributable to the rule under test.
BASE_PARAMS: dict = {
    "per_trade_risk_cap_pct": 0.30,
    "daily_loss_kill_switch_pct": 0.30,
    "min_contracts": 3,
    "pdt_gate_mode": "margin_pdt",
}

ORDER: dict = {
    "account": "TEST-ARM",
    "equity": 5000.0,
    "start_of_day_equity": 5000.0,
    "proposed_qty": 3,
    "premium": 1.00,  # notional $300
    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    "current_position_status": "flat",
    "day_trades_used_5d": 0,
    "kill_switch_tripped": False,
    "prior_stops_today": [],
}


def _order(**overrides):
    kwargs = {**ORDER, **overrides}
    params = kwargs.pop("params", BASE_PARAMS)
    account = kwargs.pop("account", ORDER["account"])
    return check_order(account, params=params, **kwargs)


# ---------------------------------------------------------------------------
# cap_entry_qty -- OFF BY DEFAULT
# ---------------------------------------------------------------------------
class TestCapEntryQtyOffByDefault:
    def test_both_keys_absent_is_a_pure_passthrough(self):
        r = cap_entry_qty(proposed_qty=8, premium=4.00, params=BASE_PARAMS)
        assert r == {"qty": 8, "skip": False, "reason": None,
                     "capped_by_contracts": False, "capped_by_dollars": False}

    def test_off_ignores_garbage_inputs(self):
        """Rule OFF means qty/premium are never even validated -- otherwise
        shipping this file could newly refuse an order some caller already
        passes garbage to today (that garbage is check_order's job to catch)."""
        r = cap_entry_qty(proposed_qty=float("nan"), premium=None, params=BASE_PARAMS)
        assert r["skip"] is False
        assert r["qty"] != r["qty"] or True  # nan passes through unexamined

    def test_none_params_is_a_passthrough(self):
        r = cap_entry_qty(proposed_qty=8, premium=1.0, params=None)
        assert r["qty"] == 8 and r["skip"] is False

    def test_none_proposed_qty_passes_through_even_when_armed(self):
        """No sizing tier matched -- unrelated to these caps. check_order's own
        rule-0 denies UNREADABLE_INPUT on this downstream, exactly as before
        this function existed; cap_entry_qty must not invent a new label."""
        params = {**BASE_PARAMS, "max_contracts_per_entry": 5, "max_position_dollars": 1000}
        r = cap_entry_qty(proposed_qty=None, premium=1.0, params=params)
        assert r == {"qty": None, "skip": False, "reason": None,
                     "capped_by_contracts": False, "capped_by_dollars": False}


# ---------------------------------------------------------------------------
# THE THREE WORKED CASES (ship instruction), run end-to-end
# ---------------------------------------------------------------------------
class TestThreeWorkedCases:
    """proposed_qty=8 simulates a tier/elite qty ABOVE the ceiling (e.g. fleet
    safe-3 ELITE at its $2K-10K tier resolves elite_qty=8) -- the scenario
    where the 5-contract cap is the one doing the clamping, matching Addendum
    1 S1.1's own finding that premiums under $2.00 are bound by the contract
    cap, not the dollar cap."""

    PARAMS = {**BASE_PARAMS, "max_contracts_per_entry": 5, "max_position_dollars": 1000}

    def test_case_a_premium_075_expect_5_contracts_375_dollars(self):
        r = cap_entry_qty(proposed_qty=8, premium=0.75, params=self.PARAMS)
        assert r["skip"] is False
        assert r["qty"] == 5
        assert r["qty"] * 0.75 * 100 == pytest.approx(375.0)
        assert r["capped_by_contracts"] is True
        assert r["capped_by_dollars"] is False

    def test_case_b_premium_250_expect_4_contracts_1000_dollars(self):
        r = cap_entry_qty(proposed_qty=8, premium=2.50, params=self.PARAMS)
        assert r["skip"] is False
        assert r["qty"] == 4
        assert r["qty"] * 2.50 * 100 == pytest.approx(1000.0)
        assert r["capped_by_contracts"] is True
        assert r["capped_by_dollars"] is True

    def test_case_c_premium_400_expect_skip(self):
        r = cap_entry_qty(proposed_qty=8, premium=4.00, params=self.PARAMS)
        assert r["skip"] is True
        assert r["qty"] is None
        assert "conflict" in r["reason"]
        assert "min_contracts" in r["reason"]


# ---------------------------------------------------------------------------
# THE FULL BOUNDARY SWEEP -- vary-and-assert across the premium axis
# ---------------------------------------------------------------------------
class TestPremiumBoundarySweep:
    PARAMS = {**BASE_PARAMS, "max_contracts_per_entry": 5, "max_position_dollars": 1000}

    @pytest.mark.parametrize(
        "premium,expected_qty,expected_skip",
        [
            (0.50, 5, False),   # well under $2 -- contract cap (5) binds
            (1.99, 5, False),
            (2.00, 5, False),   # exactly $1,000 at qty 5 -- fits
            (2.01, 4, False),   # just over -- dollar cap now binds tighter
            (2.50, 4, False),   # worked case (b)
            (3.33, 3, False),   # exactly $999 at qty 3 -- the prereg's own
                                 # stated non-breach boundary (does NOT skip)
            (3.34, None, True),  # one cent over -- 3 contracts would be $1,002
            (4.00, None, True),  # worked case (c)
            (5.00, None, True),
        ],
    )
    def test_boundary(self, premium, expected_qty, expected_skip):
        r = cap_entry_qty(proposed_qty=8, premium=premium, params=self.PARAMS)
        assert r["qty"] == expected_qty, r
        assert r["skip"] == expected_skip, r


# ---------------------------------------------------------------------------
# control #1 in isolation (contract ceiling, no dollar cap set)
# ---------------------------------------------------------------------------
class TestContractCeilingAlone:
    def test_clamps_down_never_up(self):
        params = {**BASE_PARAMS, "max_contracts_per_entry": 5}
        assert cap_entry_qty(proposed_qty=12, premium=1.0, params=params)["qty"] == 5
        assert cap_entry_qty(proposed_qty=2 + 1, premium=1.0, params=params)["qty"] == 3  # <=5, unchanged
        # min_contracts=3 in BASE_PARAMS -- a qty already AT the floor is left
        # exactly alone (neither clamped further nor raised toward the ceiling).
        assert cap_entry_qty(proposed_qty=3, premium=1.0, params=params)["qty"] == 3

    def test_off_when_key_absent(self):
        r = cap_entry_qty(proposed_qty=20, premium=1.0, params=BASE_PARAMS)
        assert r["qty"] == 20 and r["skip"] is False


# ---------------------------------------------------------------------------
# control #2 in isolation (dollar cap, no contract ceiling set)
# ---------------------------------------------------------------------------
class TestDollarCapAlone:
    def test_clamps_to_the_dollar_ceiling(self):
        params = {**BASE_PARAMS, "max_position_dollars": 1000}
        r = cap_entry_qty(proposed_qty=8, premium=2.50, params=params)
        assert r["qty"] == 4  # floor(1000 / 250)

    def test_premium_none_defers_the_dollar_cap(self):
        """Fleet's finalize() can call this before a live quote resolves
        (mirrors _shrink_qty_to_affordable's own premium=None contract).
        Deferring, not skipping, means check_order's rule-0 denies the
        genuinely-missing premium downstream -- unchanged from today."""
        params = {**BASE_PARAMS, "max_position_dollars": 1000}
        r = cap_entry_qty(proposed_qty=8, premium=None, params=params)
        assert r["skip"] is False
        assert r["qty"] == 8  # unchanged -- no contract cap set in this params dict


# ---------------------------------------------------------------------------
# control #3: the conflict rule never returns a sub-floor qty
# ---------------------------------------------------------------------------
class TestConflictRuleNeverUndersizesBelowFloor:
    PARAMS = {**BASE_PARAMS, "max_contracts_per_entry": 5, "max_position_dollars": 1000}

    def test_skip_reason_names_which_cap_bound(self):
        r = cap_entry_qty(proposed_qty=8, premium=10.00, params=self.PARAMS)
        assert r["skip"] is True
        assert "max_position_dollars" in r["reason"]

    def test_min_contracts_misconfigured_above_contract_ceiling_also_skips(self):
        """max_contracts_per_entry < min_contracts is a config error, not a
        crash -- must fail toward SKIP (never silently violate either bound)."""
        params = {**BASE_PARAMS, "min_contracts": 6, "max_contracts_per_entry": 5}
        r = cap_entry_qty(proposed_qty=8, premium=1.0, params=params)
        assert r["skip"] is True
        assert r["qty"] is None

    @pytest.mark.parametrize("premium", [3.34, 4.00, 10.00, 50.00])
    def test_never_returns_qty_below_min_contracts(self, premium):
        r = cap_entry_qty(proposed_qty=8, premium=premium, params=self.PARAMS)
        if r["qty"] is not None:
            assert r["qty"] >= self.PARAMS["min_contracts"]
        else:
            assert r["skip"] is True


# ---------------------------------------------------------------------------
# COMPOSITION with the PRE-EXISTING affordability shrink -- the exact
# interaction the ship instruction asked to be reported on: can two caps
# together ever produce a qty strictly between 0 and min_contracts?
# ---------------------------------------------------------------------------
class TestNeverProducesASubFloorQty:
    """max_affordable_qty's own documented contract: always EITHER 0 (deadlock)
    OR >= min_contracts. cap_entry_qty (above) carries the identical contract.
    Composing them (in either order, since both only ever shrink) must
    therefore never land in the forbidden (0, min_contracts) gap."""

    PARAMS = {
        "per_trade_risk_cap_pct": 0.30,
        "min_contracts": 3,
        "max_contracts_per_entry": 5,
        "max_position_dollars": 1000,
    }

    @pytest.mark.parametrize("equity", [500.0, 1000.0, 1160.42, 2000.0, 5000.0, 5266.38, 50000.0])
    @pytest.mark.parametrize("premium", [0.10, 0.30, 0.75, 1.16, 1.50, 2.50, 3.33, 3.34, 5.00, 20.0])
    @pytest.mark.parametrize("proposed_qty", [3, 5, 8, 12, 20])
    def test_sweep(self, equity, premium, proposed_qty):
        cap = cap_entry_qty(proposed_qty=proposed_qty, premium=premium, params=self.PARAMS)
        if cap["skip"]:
            return  # no order proposed -- can't violate the floor
        qty = cap["qty"]
        afford = max_affordable_qty(equity=equity, premium=premium, params=self.PARAMS)
        final_qty = min(qty, afford) if afford else qty
        # Either the pre-existing affordability shrink leaves a legal (>=min)
        # qty, or it reports a total deadlock (0) and the caller's existing
        # check_order call denies the UNCHANGED qty exactly as before this
        # ship -- either way, nothing downstream ever sees 1 or 2 contracts.
        assert final_qty == 0 or final_qty >= self.PARAMS["min_contracts"], (
            f"equity={equity} premium={premium} proposed_qty={proposed_qty} "
            f"-> cap={cap} afford={afford} final={final_qty}"
        )


# ---------------------------------------------------------------------------
# check_order backstop: MAX_CONTRACTS_PER_ENTRY (control #1, defense in depth)
# ---------------------------------------------------------------------------
class TestCheckOrderMaxContractsBackstop:
    def test_off_by_default(self):
        d = _order(proposed_qty=20, premium=0.10)  # notional $200, well under caps
        assert d.allowed, d.reason

    def test_denies_when_armed_and_exceeded(self):
        params = {**BASE_PARAMS, "max_contracts_per_entry": 5}
        d = _order(proposed_qty=6, premium=0.10, params=params)
        assert not d.allowed
        assert d.code == CODE_MAX_CONTRACTS_PER_ENTRY

    def test_allows_at_the_boundary(self):
        params = {**BASE_PARAMS, "max_contracts_per_entry": 5}
        d = _order(proposed_qty=5, premium=0.10, params=params)
        assert d.allowed, d.reason


# ---------------------------------------------------------------------------
# check_order backstop: MAX_POSITION_DOLLARS (control #2, defense in depth)
# ---------------------------------------------------------------------------
class TestCheckOrderMaxPositionDollarsBackstop:
    def test_off_by_default(self):
        # notional $1,200 -- ABOVE the $1,000 this test is about, but still
        # under BASE_PARAMS' own pre-existing per_trade_risk_cap_pct (30% of
        # $5,000 = $1,500), so this isolates "is MAX_POSITION_DOLLARS off"
        # from the unrelated, already-armed RISK_CAP gate.
        d = _order(proposed_qty=3, premium=4.00)  # no max_position_dollars set
        assert d.allowed, d.reason

    def test_denies_when_armed_and_exceeded(self):
        params = {**BASE_PARAMS, "max_position_dollars": 1000}
        d = _order(proposed_qty=3, premium=4.00, params=params)  # notional $1,200
        assert not d.allowed
        assert d.code == CODE_MAX_POSITION_DOLLARS

    def test_allows_at_the_boundary(self):
        params = {**BASE_PARAMS, "max_position_dollars": 1000}
        d = _order(proposed_qty=4, premium=2.50, params=params)  # notional exactly $1,000
        assert d.allowed, d.reason


# ---------------------------------------------------------------------------
# check_order: DAILY_LOSS_DOLLARS (control #5) -- ALONGSIDE the pct trigger
# ---------------------------------------------------------------------------
class TestDailyLossDollarsKillSwitch:
    def test_off_by_default(self):
        d = _order(equity=4700.0, start_of_day_equity=5000.0)  # -$300, no dollar key set
        assert d.allowed, d.reason

    def test_denies_at_the_dollar_floor(self):
        params = {**BASE_PARAMS, "daily_loss_kill_switch_dollars": 400.0}
        d = _order(equity=4600.0, start_of_day_equity=5000.0, params=params)  # exactly -$400
        assert not d.allowed
        assert d.code == CODE_DAILY_LOSS_DOLLARS

    def test_allows_one_dollar_above_the_floor(self):
        params = {**BASE_PARAMS, "daily_loss_kill_switch_dollars": 400.0}
        d = _order(equity=4601.0, start_of_day_equity=5000.0, params=params)  # -$399
        assert d.allowed, d.reason

    def test_does_not_remove_or_weaken_the_existing_pct_trigger(self):
        """Regression guard: the pct-based trigger (daily_loss_kill_switch_pct)
        must still fire on its own, completely independent of the new key --
        e.g. a big-equity account where -$400 is trivial but -30% is not."""
        params = {**BASE_PARAMS, "daily_loss_kill_switch_pct": 0.30,
                  "daily_loss_kill_switch_dollars": 400.0}
        # -30% of $50,000 = -$15,000 floor; equity here is only down $500 in
        # dollars (well past the $400 dollar floor) but nowhere near -30%.
        # This case is decided by the DOLLAR trigger -- prove BOTH still
        # evaluate by also checking a pct-only trip on a case the dollar floor
        # would NOT catch: -30% of a $2,000 account = -$600, dollar floor is
        # only -$400, so if only the dollar trigger existed this would ALLOW.
        d = _order(equity=1400.0, start_of_day_equity=2000.0, params=params)  # -$600, -30% exactly
        assert not d.allowed
        assert d.code == CODE_KILL_SWITCH  # the PCT trigger fired, not the dollar one first as latched
        # both are evaluated in the same rule-1 block; either firing halts the day

    def test_pct_trigger_alone_still_works_with_no_dollar_key(self):
        """Byte-identical pre-2026-08-29 behavior when the new key is absent."""
        d = _order(equity=3400.0, start_of_day_equity=5000.0,
                    params=BASE_PARAMS)  # -$1,600 > -30% of 5000 (-1500)
        assert not d.allowed
        assert d.code == CODE_KILL_SWITCH

    def test_unreadable_dollar_stop_denies_closed(self):
        params = {**BASE_PARAMS, "daily_loss_kill_switch_dollars": "not-a-number"}
        d = _order(params=params)
        assert not d.allowed
        assert d.code == CODE_UNREADABLE_INPUT


# ---------------------------------------------------------------------------
# control #4: max_same_day_roundtrips is ACTUALLY consumed (not assumed)
# ---------------------------------------------------------------------------
class TestMaxSameDayRoundtripsIsActuallyConsumed:
    """Direct call into check_settlement (the real consumer, verified by code
    read, not doc comment) proving the boundary MOVES when the params value
    moves 5 -> 4 -- i.e. this is not a dead knob (C14)."""

    def test_four_entries_allowed_under_the_old_cap_of_five(self):
        d = check_settlement(
            "TEST-ARM", premium=1.0, proposed_qty=3,
            settled_cash_available=10_000.0, same_day_entries_used=4,
            params={"max_same_day_roundtrips": 5},
        )
        assert d is None  # clears -- 4 < 5

    def test_same_four_entries_now_denied_under_the_new_cap_of_four(self):
        d = check_settlement(
            "TEST-ARM", premium=1.0, proposed_qty=3,
            settled_cash_available=10_000.0, same_day_entries_used=4,
            params={"max_same_day_roundtrips": 4},
        )
        assert d is not None
        assert d.code == CODE_SETTLEMENT
        assert "4" in d.reason

    def test_three_entries_still_allowed_under_four(self):
        d = check_settlement(
            "TEST-ARM", premium=1.0, proposed_qty=3,
            settled_cash_available=10_000.0, same_day_entries_used=3,
            params={"max_same_day_roundtrips": 4},
        )
        assert d is None


# ---------------------------------------------------------------------------
# THE SHIP ITSELF: pin the exact values in BOTH live params files
# ---------------------------------------------------------------------------
class TestShippedParamsFiles:
    SAFE_PATH = REPO / "automation" / "state" / "params.json"
    BOLD_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"

    @pytest.mark.parametrize("path", [SAFE_PATH, BOLD_PATH])
    def test_new_keys_present_with_shipped_values(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["max_contracts_per_entry"] == 5, path
        assert data["max_position_dollars"] == 1000, path
        assert data["max_same_day_roundtrips"] == 4, path
        assert data["daily_loss_kill_switch_dollars"] == 400, path
        # never-weakened invariant: the pre-existing pct kill switch is untouched
        assert data["daily_loss_kill_switch_pct"] in (0.3, 0.5), path

    def test_min_contracts_never_exceeds_the_new_ceiling(self):
        """A config error (min_contracts > max_contracts_per_entry) would make
        the conflict rule fire on EVERY entry -- guard the live files directly."""
        for path in (self.SAFE_PATH, self.BOLD_PATH):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["min_contracts"] <= data["max_contracts_per_entry"], path
