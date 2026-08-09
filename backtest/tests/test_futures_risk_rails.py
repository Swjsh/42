"""Guards for futures_risk_rails + futures_session.

Every test here pins a rail that, if it silently inverted or drifted, would let the
futures arm take a trade it must not take. They are written to FAIL if the rail stops
doing its job -- not merely to exercise the code path.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.instruments import MES, MNQ  # noqa: E402
from futures import futures_session as fs  # noqa: E402
from futures.futures_risk_rails import (  # noqa: E402
    FuturesRiskRails, MINUTES_BEFORE_MAINTENANCE_BLOCK, ROLLOVER_BLOCK_DAYS,
    days_to_expiry, front_month_expiry, third_friday,
)

# A Wednesday inside RTH, comfortably clear of any rollover window.
RTH_WED = dt.datetime(2026, 8, 12, 11, 0)


@pytest.fixture()
def rails():
    return FuturesRiskRails()


# ── session model ─────────────────────────────────────────────────────────────

class TestSessionModel:
    def test_saturday_is_closed(self):
        assert not fs.is_session_open(dt.datetime(2026, 8, 8, 12, 0))

    def test_sunday_before_1800_closed_after_open(self):
        assert not fs.is_session_open(dt.datetime(2026, 8, 9, 17, 59))
        assert fs.is_session_open(dt.datetime(2026, 8, 9, 18, 0))

    def test_friday_closes_at_1700(self):
        assert fs.is_session_open(dt.datetime(2026, 8, 7, 16, 59))
        assert not fs.is_session_open(dt.datetime(2026, 8, 7, 17, 0))

    def test_maintenance_break_is_closed_mon_thu(self):
        # Wednesday 17:30 ET -- inside the daily settlement break.
        assert not fs.is_session_open(dt.datetime(2026, 8, 12, 17, 30))
        assert fs.is_session_open(dt.datetime(2026, 8, 12, 18, 30))

    def test_rth_window_excludes_globex(self):
        assert fs.is_rth(RTH_WED)
        assert not fs.is_rth(dt.datetime(2026, 8, 12, 3, 0))
        assert fs.session_phase(dt.datetime(2026, 8, 12, 3, 0)) == "GLOBEX"

    def test_phases_are_distinct(self):
        assert fs.session_phase(RTH_WED) == "RTH"
        assert fs.session_phase(dt.datetime(2026, 8, 8, 12, 0)) == "WEEKEND"
        assert fs.session_phase(dt.datetime(2026, 8, 12, 17, 30)) == "MAINTENANCE"

    def test_next_open_crosses_the_weekend(self):
        # Saturday -> the Sunday 18:00 reopen.
        nxt = fs.next_open(dt.datetime(2026, 8, 8, 12, 0))
        assert nxt == dt.datetime(2026, 8, 9, 18, 0)

    def test_seconds_since_open_is_none_when_closed(self):
        assert fs.seconds_since_open(dt.datetime(2026, 8, 8, 12, 0)) is None


# ── rollover calendar ─────────────────────────────────────────────────────────

class TestRollover:
    def test_third_friday_is_correct(self):
        assert third_friday(2026, 9) == dt.date(2026, 9, 18)
        assert third_friday(2026, 12) == dt.date(2026, 12, 18)

    def test_front_month_rolls_to_next_quarter_after_expiry(self):
        assert front_month_expiry(dt.date(2026, 8, 9)) == dt.date(2026, 9, 18)
        assert front_month_expiry(dt.date(2026, 9, 19)) == dt.date(2026, 12, 18)

    def test_december_rolls_into_next_year(self):
        assert front_month_expiry(dt.date(2026, 12, 19)) == dt.date(2027, 3, 19)

    def test_entry_blocked_inside_rollover_window(self, rails):
        near = dt.datetime(2026, 9, 15, 11, 0)   # 3 days to the Sep expiry
        assert days_to_expiry(near.date()) <= ROLLOVER_BLOCK_DAYS
        assert not rails.check_rollover(near).allow

    def test_entry_allowed_outside_rollover_window(self, rails):
        assert rails.check_rollover(RTH_WED).allow


# ── individual rails ──────────────────────────────────────────────────────────

class TestContractCap:
    def test_default_cap_is_one_contract(self, rails):
        assert rails.check_contract_cap(1).allow
        assert not rails.check_contract_cap(2).allow

    def test_zero_or_negative_qty_refused(self, rails):
        assert not rails.check_contract_cap(0).allow
        assert not rails.check_contract_cap(-1).allow


class TestPerTradeRisk:
    def test_stop_within_cap_allowed(self, rails):
        # 10 MES points x $5 = $50 <= $100 cap
        assert rails.check_per_trade_risk(10, 1, MES).allow

    def test_stop_beyond_cap_blocked(self, rails):
        # 30 MES points x $5 = $150 > $100 cap
        v = rails.check_per_trade_risk(30, 1, MES)
        assert not v.allow and v.rail == "per_trade_risk"

    def test_entry_without_a_stop_is_refused(self, rails):
        """Rule 3 analogue: no defined stop, no trade."""
        assert not rails.check_per_trade_risk(0, 1, MES).allow
        assert not rails.check_per_trade_risk(-5, 1, MES).allow

    def test_point_value_is_respected_across_instruments(self, rails):
        # 30 points: MES = $150 (blocked), MNQ = $60 (allowed) at the same cap.
        assert not rails.check_per_trade_risk(30, 1, MES).allow
        assert rails.check_per_trade_risk(30, 1, MNQ).allow


class TestSessionLossCap:
    def test_cap_blocks_when_worst_case_reaches_it(self, rails):
        # -$150 realized + a $50 worst case == the $200 cap.
        assert not rails.check_session_loss(-150.0, 50.0).allow

    def test_room_left_allows(self, rails):
        assert rails.check_session_loss(-50.0, 50.0).allow

    def test_profitable_session_is_never_blocked_by_the_loss_cap(self, rails):
        assert rails.check_session_loss(400.0, 50.0).allow


class TestAccountFloor:
    def test_floor_breach_blocked(self, rails):
        assert not rails.check_account_floor(1_620.0, 50.0).allow

    def test_above_floor_allowed(self, rails):
        assert rails.check_account_floor(2_000.0, 50.0).allow


class TestLiquidationDistance:
    """The rail that keeps OUR stop inside the BROKER's margin call."""

    def test_stop_inside_the_cushion_is_allowed(self, rails):
        # equity 2000 - 500 margin = 1500 cushion; stop costs 10 x $5 = $50.
        assert rails.check_liquidation_distance(2_000.0, 10, 1, MES).allow

    def test_stop_beyond_the_cushion_is_blocked(self, rails):
        # equity 600 - 500 margin = 100 cushion; stop costs 40 x $5 = $200 > cushion.
        v = rails.check_liquidation_distance(600.0, 40, 1, MES)
        assert not v.allow and v.rail == "liquidation_distance"

    def test_equity_below_day_margin_is_blocked(self, rails):
        assert not rails.check_liquidation_distance(400.0, 5, 1, MES).allow

    def test_margin_call_never_fires_before_our_stop(self, rails):
        """Property: any qty/stop the rails ACCEPT must leave the stop cheaper than
        the cushion. This is the invariant the whole file exists to protect.

        Two rail sets are swept deliberately. Under the DEFAULT rails this property
        holds vacuously -- `account_floor` ($1,600) and `per_trade_risk` ($100) are
        strictly tighter than the liquidation cushion at every reachable size, so
        they reject the dangerous combinations before this rail is ever consulted
        (C15: gates interact multiplicatively -- a rail can be correct and still be
        shadowed). `binding` is sized so the liquidation rail is the ONLY thing
        standing between the engine and a margin call, which is what makes this test
        able to fail when that rail is removed.
        """
        binding = FuturesRiskRails(
            account_floor=0.0,            # floor cannot shadow the cushion
            per_trade_risk_cap=10_000.0,  # per-trade cap cannot shadow it either
            max_contracts=5,
            day_margin_per_contract=500.0,
        )
        for r in (rails, binding):
            for equity in (600.0, 1_200.0, 1_700.0, 2_000.0, 5_000.0):
                for stop_pts in (2, 5, 10, 20, 40, 80):
                    qty = r.max_qty_for(equity=equity, stop_points=stop_pts, instrument=MES)
                    if qty == 0:
                        continue
                    cushion = equity - r.day_margin_per_contract * qty
                    assert stop_pts * MES.point_value * qty < cushion, (
                        f"accepted qty={qty} stop={stop_pts} at equity={equity} but the "
                        f"stop costs more than the ${cushion} cushion")

    def test_liquidation_rail_is_the_binding_constraint_somewhere(self):
        """Guard the guard: prove a configuration exists where removing the
        liquidation rail would actually change the accepted size. Without this, the
        property test above could pass on a build where the rail does nothing."""
        binding = FuturesRiskRails(account_floor=0.0, per_trade_risk_cap=10_000.0,
                                   max_contracts=5, day_margin_per_contract=500.0)
        # equity 1,200, 40-pt stop: 1 contract posts $500 margin (cushion $700) and
        # risks $200 -- safe. 2 contracts post $1,000 (cushion $200) and risk $400 --
        # the margin call would land first, so only the liquidation rail can reject it.
        assert binding.check_liquidation_distance(1_200.0, 40, 2, MES).allow is False
        assert binding.check_per_trade_risk(40, 2, MES).allow is True
        assert binding.check_account_floor(1_200.0, 40 * MES.point_value * 2).allow is True
        assert binding.max_qty_for(equity=1_200.0, stop_points=40, instrument=MES) == 1


class TestSessionWindow:
    def test_closed_session_blocks_entry(self, rails):
        assert not rails.check_session_window(dt.datetime(2026, 8, 8, 12, 0)).allow

    def test_rth_entry_allowed(self, rails):
        assert rails.check_session_window(RTH_WED).allow

    def test_globex_blocked_while_rth_only(self, rails):
        assert not rails.check_session_window(dt.datetime(2026, 8, 12, 3, 0)).allow

    def test_globex_allowed_once_rth_only_is_lifted(self):
        r = FuturesRiskRails(rth_only=False)
        assert r.check_session_window(dt.datetime(2026, 8, 12, 3, 0)).allow

    def test_no_new_entry_near_the_settlement_stop(self):
        r = FuturesRiskRails(rth_only=False)
        near = dt.datetime(2026, 8, 12, 17, 0) - dt.timedelta(
            minutes=MINUTES_BEFORE_MAINTENANCE_BLOCK - 5)
        assert not r.check_session_window(near).allow


class TestDataFreshness:
    @pytest.mark.parametrize("verdict", ["RED", "YELLOW", "BLIND", "CLOSED", "WARMUP"])
    def test_only_green_authorizes_an_entry(self, rails, verdict):
        assert not rails.check_data_freshness(verdict).allow

    def test_green_allows(self, rails):
        assert rails.check_data_freshness("GREEN").allow


# ── composite gate + forced flatten ───────────────────────────────────────────

class TestCompositeEntryGate:
    def _ok(self, **over):
        base = dict(now_et=RTH_WED, equity=2_000.0, session_realized_pnl=0.0,
                    stop_points=10, qty=1, instrument=MES, freshness_verdict="GREEN")
        base.update(over)
        return base

    def test_clean_setup_passes_every_rail(self, rails):
        assert rails.check_entry(**self._ok()).allow

    def test_stale_feed_blocks_an_otherwise_perfect_setup(self, rails):
        v = rails.check_entry(**self._ok(freshness_verdict="RED"))
        assert not v.allow and v.rail == "data_freshness"

    def test_session_loss_cap_blocks_an_otherwise_perfect_setup(self, rails):
        v = rails.check_entry(**self._ok(session_realized_pnl=-180.0))
        assert not v.allow and v.rail == "session_loss_cap"

    def test_oversize_blocks(self, rails):
        v = rails.check_entry(**self._ok(qty=3))
        assert not v.allow and v.rail == "contract_cap"

    def test_weekend_blocks_first_with_the_session_reason(self, rails):
        v = rails.check_entry(**self._ok(now_et=dt.datetime(2026, 8, 8, 12, 0)))
        assert not v.allow and v.rail == "session_window"


class TestForcedFlatten:
    def test_flatten_demanded_near_the_settlement_stop(self):
        r = FuturesRiskRails(rth_only=False)
        assert r.must_flatten(dt.datetime(2026, 8, 12, 16, 55)).allow

    def test_flatten_demanded_after_rth_when_rth_only(self, rails):
        assert rails.must_flatten(dt.datetime(2026, 8, 12, 16, 30)).allow

    def test_no_flatten_mid_rth(self, rails):
        assert not rails.must_flatten(RTH_WED).allow


class TestMaxQtyFor:
    def test_returns_zero_when_nothing_is_safe(self, rails):
        # Equity barely above day margin, wide stop -> no size clears the rails.
        assert rails.max_qty_for(equity=520.0, stop_points=50, instrument=MES) == 0

    def test_never_exceeds_the_contract_cap(self, rails):
        assert rails.max_qty_for(equity=100_000.0, stop_points=1,
                                 instrument=MES) <= rails.max_contracts
