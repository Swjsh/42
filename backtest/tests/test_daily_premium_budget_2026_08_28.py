"""Guard: per-arm DAILY PREMIUM BUDGET gate (risk_gate, 2026-08-28).

WHY THIS FILE EXISTS
--------------------
Over 42 days of real fills the book deployed $141,641 of premium to net +$1,317,
and 48% of all entries were placed while that arm was ALREADY RED on the day.
`check_daily_premium_budget` caps per-session deployment. Scorecard:
analysis/recommendations/daily-premium-budget.json

THE LOAD-BEARING PROPERTY is the FIRST test class: with
`daily_premium_budget_dollars` absent from params, `check_order` must be
byte-identical to its pre-2026-08-28 behavior. The rule ships OFF; flipping it
on is a params.json edit, which is a weekend/after-hours action under Rule 9.
If someone later makes the gate fire by default, `test_rule_is_off_by_default`
goes RED before it reaches a live account.

Second property: LOSS-ARMED. The default shape only binds once the arm is
already red on the session. A flat cap regressed the 5 best realised days by
-32.3% (it trims size on exactly the trend days the right-tail edge lives on);
the loss-armed shape regressed them -5.3% and passed anchor-no-regression.
`test_green_session_is_never_constrained` pins that -- it is the whole reason
this variant was chosen over the obvious flat cap.
"""

from __future__ import annotations

import math

import pytest

from backtest.lib.risk_gate import (
    CODE_ALLOW,
    CODE_DAILY_PREMIUM_BUDGET,
    CODE_UNREADABLE_INPUT,
    check_daily_premium_budget,
    check_order,
)

# A params set that passes every OTHER gate, so any denial in these tests is
# unambiguously attributable to the budget rule.
BASE_PARAMS: dict = {
    "per_trade_risk_cap_pct": 0.30,
    "daily_loss_kill_switch_pct": 0.30,
    "min_contracts": 3,
    "pdt_gate_mode": "margin_pdt",
}

ORDER: dict = {
    "equity": 5000.0,
    "start_of_day_equity": 5000.0,
    "proposed_qty": 3,
    "premium": 1.50,  # notional $450
    "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "current_position_status": "flat",
    "day_trades_used_5d": 0,
    "kill_switch_tripped": False,
    "prior_stops_today": [],
}


def _order(**overrides):
    kwargs = {**ORDER, **overrides}
    params = kwargs.pop("params", BASE_PARAMS)
    return check_order("TEST-ARM", params=params, **kwargs)


# ---------------------------------------------------------------------------
# 1. OFF BY DEFAULT -- the property that keeps this safe to merge mid-session
# ---------------------------------------------------------------------------
class TestRuleIsOffByDefault:
    def test_rule_is_off_by_default(self):
        """No budget param -> the gate is a no-op, whatever else is passed."""
        assert (
            check_daily_premium_budget(
                "TEST-ARM",
                premium=1.50,
                proposed_qty=3,
                premium_spent_today=999_999.0,
                realized_pnl_today=-999_999.0,
                params=BASE_PARAMS,
            )
            is None
        )

    def test_check_order_unchanged_when_param_absent(self):
        """check_order must ALLOW without the new kwargs -- every pre-2026-08-28
        caller passes neither, and none of them may start failing."""
        decision = _order()
        assert decision.allowed
        assert decision.code == CODE_ALLOW

    def test_absent_param_ignores_unreadable_new_inputs(self):
        """Rule OFF means the new inputs are not required, so garbage in them
        must NOT deny -- otherwise merging this file breaks live callers."""
        decision = _order(premium_spent_today=float("nan"), realized_pnl_today=None)
        assert decision.allowed, decision.reason


# ---------------------------------------------------------------------------
# 2. LOSS-ARMED (the default, and the reason this variant was chosen)
# ---------------------------------------------------------------------------
class TestLossArmed:
    PARAMS = {**BASE_PARAMS, "daily_premium_budget_dollars": 700.0}

    def test_green_session_is_never_constrained(self):
        """A winning session is untouched even far past the budget.

        This is the anchor-no-regression property: the flat cap regressed the
        5 best realised days -32.3%, the loss-armed shape -5.3%.
        """
        decision = _order(
            params=self.PARAMS,
            premium_spent_today=5_000.0,  # way past the $700 budget
            realized_pnl_today=+250.0,  # ...but the arm is GREEN today
        )
        assert decision.allowed, decision.reason

    def test_flat_session_is_not_constrained(self):
        """Exactly break-even is not red. Boundary: >= 0 does not arm."""
        decision = _order(
            params=self.PARAMS, premium_spent_today=5_000.0, realized_pnl_today=0.0
        )
        assert decision.allowed, decision.reason

    def test_red_session_blocked_past_budget(self):
        decision = _order(
            params=self.PARAMS,
            premium_spent_today=500.0,  # + $450 notional = $950 > $700
            realized_pnl_today=-120.0,
        )
        assert not decision.allowed
        assert decision.code == CODE_DAILY_PREMIUM_BUDGET
        assert "already deployed today" in decision.reason

    def test_red_session_allowed_within_budget(self):
        decision = _order(
            params=self.PARAMS,
            premium_spent_today=200.0,  # + $450 = $650 <= $700
            realized_pnl_today=-120.0,
        )
        assert decision.allowed, decision.reason

    def test_budget_boundary_is_inclusive(self):
        """spent + notional == budget is allowed; one cent more is not."""
        allowed = _order(
            params=self.PARAMS, premium_spent_today=250.0, realized_pnl_today=-1.0
        )
        assert allowed.allowed, allowed.reason
        denied = _order(
            params=self.PARAMS, premium_spent_today=250.01, realized_pnl_today=-1.0
        )
        assert not denied.allowed
        assert denied.code == CODE_DAILY_PREMIUM_BUDGET


# ---------------------------------------------------------------------------
# 3. FLAT shape (loss_armed=False) -- kept available, not the default
# ---------------------------------------------------------------------------
class TestFlatShape:
    PARAMS = {
        **BASE_PARAMS,
        "daily_premium_budget_dollars": 700.0,
        "daily_premium_budget_loss_armed": False,
    }

    def test_green_session_is_constrained_when_flat(self):
        """The flat shape binds regardless of P&L -- the behavioural difference
        from the default that the anchor gate punished."""
        decision = _order(
            params=self.PARAMS, premium_spent_today=500.0, realized_pnl_today=+250.0
        )
        assert not decision.allowed
        assert decision.code == CODE_DAILY_PREMIUM_BUDGET
        assert "flat budget" in decision.reason

    def test_flat_shape_needs_no_realized_pnl(self):
        """realized_pnl_today is only required when loss-armed."""
        decision = _order(
            params=self.PARAMS, premium_spent_today=100.0, realized_pnl_today=None
        )
        assert decision.allowed, decision.reason


# ---------------------------------------------------------------------------
# 4. FAIL CLOSED once the rule is on
# ---------------------------------------------------------------------------
class TestFailsClosedWhenOn:
    PARAMS = {**BASE_PARAMS, "daily_premium_budget_dollars": 700.0}

    @pytest.mark.parametrize("bad", [None, float("nan"), "lots", float("inf")])
    def test_unreadable_spent_denies(self, bad):
        decision = _order(
            params=self.PARAMS, premium_spent_today=bad, realized_pnl_today=-50.0
        )
        assert not decision.allowed
        assert decision.code == CODE_UNREADABLE_INPUT
        assert "premium_spent_today" in decision.reason

    @pytest.mark.parametrize("bad", [None, float("nan"), "down a bit"])
    def test_unreadable_realized_pnl_denies_when_loss_armed(self, bad):
        decision = _order(
            params=self.PARAMS, premium_spent_today=100.0, realized_pnl_today=bad
        )
        assert not decision.allowed
        assert decision.code == CODE_UNREADABLE_INPUT
        assert "realized_pnl_today" in decision.reason

    def test_negative_spent_denies(self):
        decision = _order(
            params=self.PARAMS, premium_spent_today=-1.0, realized_pnl_today=-50.0
        )
        assert not decision.allowed
        assert decision.code == CODE_UNREADABLE_INPUT

    @pytest.mark.parametrize("bad", [0.0, -100.0, float("nan"), "seven hundred"])
    def test_unreadable_or_nonpositive_budget_denies(self, bad):
        decision = _order(
            params={**BASE_PARAMS, "daily_premium_budget_dollars": bad},
            premium_spent_today=0.0,
            realized_pnl_today=-50.0,
        )
        assert not decision.allowed
        assert decision.code == CODE_UNREADABLE_INPUT

    def test_non_bool_loss_armed_denies(self):
        decision = _order(
            params={**self.PARAMS, "daily_premium_budget_loss_armed": "yes"},
            premium_spent_today=0.0,
            realized_pnl_today=-50.0,
        )
        assert not decision.allowed
        assert decision.code == CODE_UNREADABLE_INPUT
        assert "loss_armed" in decision.reason


# ---------------------------------------------------------------------------
# 5. The gate is reusable standalone (fleet arms do not route through
#    check_order's mode dispatch -- L184 "one implementation").
# ---------------------------------------------------------------------------
def test_callable_standalone_for_fleet():
    denial = check_daily_premium_budget(
        "fleet-risky-3",
        premium=0.90,
        proposed_qty=5,  # $450
        premium_spent_today=400.0,
        realized_pnl_today=-190.0,
        params={"daily_premium_budget_dollars": 700.0},
    )
    assert denial is not None
    assert denial.code == CODE_DAILY_PREMIUM_BUDGET
    assert not denial.allowed


def test_todays_risky_3_sequence_is_what_the_rule_stops():
    """2026-08-28 risky-3, from the broker tape: 5 entries, 0 winners, -$410.

    Entry 1 ($395) is untouched -- nothing had gone wrong yet. Every later
    entry is placed into a session that is already red, and the budget stops
    the sequence once cumulative deployment would pass $700.
    """
    params = {"daily_premium_budget_dollars": 700.0}
    # (cost, realized-so-far) as they actually occurred, in order.
    sequence = [
        (395.0, 0.0),  # 10:22:11 -- first entry, session flat
        (340.0, -75.0),  # 10:25:10 -- already red
        (330.0, -190.0),  # 11:02:09
        (450.0, -240.0),  # 13:02:08
        (440.0, -360.0),  # 13:27:09
    ]
    spent = 0.0
    taken = []
    for cost, realized in sequence:
        denial = check_daily_premium_budget(
            "risky-3",
            premium=cost / 500.0,  # 5 contracts
            proposed_qty=5,
            premium_spent_today=spent,
            realized_pnl_today=realized,
            params=params,
        )
        if denial is None:
            spent += cost
            taken.append(cost)

    # Only the opening entry survives: $395 + the next $340 would be $735 > $700,
    # so the cap binds from the second attempt onward. risky-3's actual day was
    # -$410 across all five; under this rule it is the first entry's -$75 alone.
    assert taken == [395.0], taken
    assert spent == 395.0
    assert not math.isclose(spent, sum(c for c, _ in sequence))
