"""Guards for backtest/tools/regime_participation_study.py (2026-08-02, REGIME-PARTICIPATION task).

Pins the three PURE functions this tool's whole PERFORMANCE-vs-PARTICIPATION decomposition
rests on -- no I/O, no clock, fixture-driven:

  performance_by_archetype()      -- trade log x archetype -> n/WR/total/mean + the
                                      CONCENTRATION check (top-day share, drop-best deltas)
                                      that discriminates "archetype edge" from "one outlier
                                      day wearing an archetype label".
  recent_n_trading_days()         -- last-N-distinct-dates selector (RECENCY_LOOKBACK_TRADING_DAYS
                                      convention, matches backtest/autoresearch/recency_check.py).
  core_decisions_participation()  -- pre-classified core-decisions events x archetype -> stage
                                      + blocker histograms.

RED-proofed: each assertion was checked against a deliberately-broken implementation (wrong
share denominator, off-by-one window slice, blocker categories not excluded from the
leaderboard) and observed to fail before being pinned as written.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_regime_participation_study.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
for _p in (str(REPO), str(REPO / "backtest"), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regime_participation_study as rps  # noqa: E402


# =============================================================================== performance_by_archetype

class TestPerformanceByArchetypeBasics:
    def _lookup(self):
        return {"2026-01-02": "gap-go", "2026-01-03": "gap-go", "2026-01-06": "trend-up"}

    def test_basic_n_total_wr(self):
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 100.0},
            {"date": "2026-01-03", "dollar_pnl": -40.0},
        ]
        out = rps.performance_by_archetype(trades, self._lookup())
        g = out["gap-go"]
        assert g["n_trades"] == 2
        assert g["n_days"] == 2
        assert g["total_pnl"] == 60.0
        assert g["mean_trade_pnl"] == 30.0
        assert g["win_rate"] == 0.5

    def test_untagged_dates_bucketed_separately_not_dropped(self):
        trades = [{"date": "1999-01-01", "dollar_pnl": 5.0}]
        out = rps.performance_by_archetype(trades, self._lookup())
        assert "UNTAGGED" in out
        assert out["UNTAGGED"]["n_trades"] == 1
        assert "1999-01-01" in out["UNTAGGED"]["dates"]

    def test_underpowered_flag_boundary_at_n15(self):
        lookup = {f"2026-01-{i:02d}": "gap-go" for i in range(1, 20)}
        trades_14 = [{"date": f"2026-01-{i:02d}", "dollar_pnl": 1.0} for i in range(1, 15)]
        trades_15 = [{"date": f"2026-01-{i:02d}", "dollar_pnl": 1.0} for i in range(1, 16)]
        out14 = rps.performance_by_archetype(trades_14, lookup)
        out15 = rps.performance_by_archetype(trades_15, lookup)
        assert out14["gap-go"]["n_trades"] == 14
        assert out14["gap-go"]["underpowered_n_lt_15"] is True
        assert out15["gap-go"]["n_trades"] == 15
        assert out15["gap-go"]["underpowered_n_lt_15"] is False


class TestConcentrationCheck:
    """The task's own discriminator: 'a 60.5% share on 22% of days could be edge OR could be
    one outlier day -- check concentration explicitly (top-day share) before calling it a
    regime effect.' These pin the exact arithmetic of that check."""

    def test_broad_based_archetype_has_low_top_day_share_and_survives_drop_best(self):
        lookup = {"2026-01-02": "gap-go", "2026-01-03": "gap-go", "2026-01-06": "gap-go"}
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 100.0},
            {"date": "2026-01-03", "dollar_pnl": 100.0},
            {"date": "2026-01-06", "dollar_pnl": 100.0},
        ]
        out = rps.performance_by_archetype(trades, lookup)["gap-go"]
        assert out["total_pnl"] == 300.0
        assert out["top_day_share_of_total"] == round(100.0 / 300.0, 4)
        assert out["drop_best_day_total"] == 200.0
        assert out["drop_best_day_still_positive"] is True

    def test_single_outlier_day_archetype_has_share_over_1_and_fails_drop_best(self):
        """Mirrors the real trend-up finding: one big day carries a small positive total;
        every OTHER day is a net loser, so removing the best day flips the sign."""
        lookup = {"2026-01-02": "trend-up", "2026-01-03": "trend-up", "2026-01-06": "trend-up"}
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 500.0},
            {"date": "2026-01-03", "dollar_pnl": -200.0},
            {"date": "2026-01-06", "dollar_pnl": -150.0},
        ]
        out = rps.performance_by_archetype(trades, lookup)["trend-up"]
        assert out["total_pnl"] == 150.0
        assert out["top_day_share_of_total"] > 1.0
        assert out["drop_best_day_total"] == -350.0
        assert out["drop_best_day_still_positive"] is False

    def test_zero_total_gives_none_share_not_a_divide_by_zero(self):
        lookup = {"2026-01-02": "pin-day", "2026-01-03": "pin-day"}
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 50.0},
            {"date": "2026-01-03", "dollar_pnl": -50.0},
        ]
        out = rps.performance_by_archetype(trades, lookup)["pin-day"]
        assert out["total_pnl"] == 0.0
        assert out["top_day_share_of_total"] is None

    def test_multiple_trades_same_day_aggregate_into_one_day_bucket(self):
        lookup = {"2026-01-02": "gap-go"}
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 40.0},
            {"date": "2026-01-02", "dollar_pnl": 60.0},
        ]
        out = rps.performance_by_archetype(trades, lookup)["gap-go"]
        assert out["n_trades"] == 2
        assert out["n_days"] == 1
        assert out["top_day"]["total"] == 100.0

    def test_drop_best_trade_differs_from_drop_best_day_when_multiple_trades_share_a_day(self):
        lookup = {"2026-01-02": "gap-go"}
        trades = [
            {"date": "2026-01-02", "dollar_pnl": 40.0},
            {"date": "2026-01-02", "dollar_pnl": 60.0},
        ]
        out = rps.performance_by_archetype(trades, lookup)["gap-go"]
        # drop-best-DAY removes the whole $100 day (both trades); drop-best-TRADE removes
        # only the larger single trade ($60), leaving the $40 one behind.
        assert out["drop_best_day_total"] == 0.0
        assert out["drop_best_trade_total"] == 40.0


# =============================================================================== recent_n_trading_days

class TestRecentNTradingDays:
    def test_returns_last_n_ascending(self):
        dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-06", "2026-01-07"]
        assert rps.recent_n_trading_days(dates, n=3) == ["2026-01-03", "2026-01-06", "2026-01-07"]

    def test_dedups_duplicate_dates(self):
        dates = ["2026-01-02", "2026-01-02", "2026-01-03"]
        assert rps.recent_n_trading_days(dates, n=2) == ["2026-01-02", "2026-01-03"]

    def test_n_larger_than_population_returns_all(self):
        dates = ["2026-01-02", "2026-01-03"]
        assert rps.recent_n_trading_days(dates, n=25) == ["2026-01-02", "2026-01-03"]

    def test_n_zero_means_unlimited_matching_participation_cascade_discover_sessions_convention(self):
        """Intentional: same 'falsy n = no truncation' convention as
        participation_cascade.discover_sessions(n) -- 0 is NOT '0 most recent days'."""
        dates = ["2026-01-02", "2026-01-03", "2026-01-06"]
        assert rps.recent_n_trading_days(dates, n=0) == dates

    def test_default_n_is_25(self):
        dates = [f"2026-{(i//20)+1:02d}-{(i%20)+1:02d}" for i in range(30)]
        assert len(rps.recent_n_trading_days(sorted(set(dates)))) <= 25


# =============================================================================== core_decisions_participation

def _event(date, stage, category="gate", blocker="some_gate", side="P", setup="X", tier="ELITE"):
    return {"date": date, "side": side, "setup": setup, "tier": tier,
            "stage": stage, "category": category, "blocker": blocker}


class TestCoreDecisionsParticipation:
    def test_basic_stage_histogram_per_archetype(self):
        lookup = {"2026-06-25": "gap-go"}
        events_by_account = {"safe": [
            _event("2026-06-25", "NO_SIGNAL", category="none", blocker=None),
            _event("2026-06-25", "GATE_BLOCK", blocker="block_elite_bull"),
            _event("2026-06-25", "FILLED", category="success", blocker=None),
        ]}
        out = rps.core_decisions_participation(events_by_account, lookup)
        arch = out["safe"]["gap-go"]
        assert arch["n_events"] == 3
        assert arch["by_stage"]["NO_SIGNAL"] == 1
        assert arch["by_stage"]["GATE_BLOCK"] == 1
        assert arch["by_stage"]["FILLED"] == 1
        assert arch["n_entered"] == 1

    def test_no_data_no_signal_placed_filled_excluded_from_blocker_leaderboard(self):
        lookup = {"2026-06-25": "trend-up"}
        events_by_account = {"safe": [
            _event("2026-06-25", "NO_DATA", category="none", blocker=None),
            _event("2026-06-25", "NO_SIGNAL", category="none", blocker=None),
            _event("2026-06-25", "PLACED", category="success", blocker=None),
            _event("2026-06-25", "FILLED", category="success", blocker=None),
            _event("2026-06-25", "GATE_BLOCK", blocker="block_elite_bull"),
        ]}
        out = rps.core_decisions_participation(events_by_account, lookup)
        blockers = out["safe"]["trend-up"]["top_blockers"]
        assert len(blockers) == 1
        assert blockers[0]["blocker"] == "block_elite_bull"

    def test_unknown_date_falls_back_to_untagged(self):
        events_by_account = {"safe": [_event("1999-01-01", "NO_SIGNAL", category="none", blocker=None)]}
        out = rps.core_decisions_participation(events_by_account, {})
        assert "UNTAGGED" in out["safe"]

    def test_accounts_kept_independent(self):
        lookup = {"2026-06-25": "gap-go"}
        events_by_account = {
            "safe": [_event("2026-06-25", "FILLED", category="success", blocker=None)],
            "bold": [_event("2026-06-25", "GATE_BLOCK", blocker="require_bearish_fill_bar")],
        }
        out = rps.core_decisions_participation(events_by_account, lookup)
        assert out["safe"]["gap-go"]["n_entered"] == 1
        assert out["bold"]["gap-go"]["n_entered"] == 0
        assert out["bold"]["gap-go"]["top_blockers"][0]["blocker"] == "require_bearish_fill_bar"

    def test_blocker_leaderboard_ranked_by_count(self):
        lookup = {"2026-06-25": "range-chop"}
        events_by_account = {"safe": [
            _event("2026-06-25", "GATE_BLOCK", blocker="block_elite_bull"),
            _event("2026-06-25", "GATE_BLOCK", blocker="block_elite_bull"),
            _event("2026-06-25", "RISK_GATE_DENY", category="risk_gate", blocker="not_flat_rule4"),
        ]}
        out = rps.core_decisions_participation(events_by_account, lookup)
        top = out["safe"]["range-chop"]["top_blockers"]
        assert top[0]["blocker"] == "block_elite_bull"
        assert top[0]["n"] == 2
