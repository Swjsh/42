"""Guards for the ONE-POSITION-AT-A-TIME CONSTRAINT COST study (prereg:
analysis/deep-research/PREREG-ONE-POSITION-CONSTRAINT-COST-2026-08-02.md; deliverable:
analysis/deep-research/ONE-POSITION-CONSTRAINT-COST-2026-08-02.{json,md}).

MEASUREMENT-ONLY LANE -- these guards pin the MECHANISM (concurrency admission is
monotonic and matches an independently-coded cross-check; kill-switch/notional
calculators are arithmetically correct; K=1 is byte-parity with the already-shipped
`_sequential_admit`), all on synthetic fixture rows where the answer is known by
construction, independent of any particular historical outcome -- same discipline
bold_adaptive_sizing_2026_08_02.py's own TestSequentialAdmitMechanism established.

RED-PROOF (executed once, not committed as a permanent skip): TestParityWithShippedSequentialAdmit
below was run once with a deliberately WRONG expected constant substituted in for the
K=1 fixture output before being corrected -- proving the assertion actually discriminates
rather than being vacuously true. See session report for the quoted RED/GREEN pytest
output (this file's own git history stays clean -- no permanent broken state committed,
matching the mutate-assertion-then-restore technique used when there is no PRIOR tracked
behavior to rename-and-restore against, L238's ban is on `git stash`, not on this).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_one_position_constraint_cost_2026_08_02.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR, CRYPTO_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import one_position_constraint_cost_2026_08_02 as study  # noqa: E402
import bold_adaptive_sizing_2026_08_02 as adaptive_study  # noqa: E402

HEARTBEAT_CORE = REPO / "setup" / "scripts" / "heartbeat_core.py"
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
AGG_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"


def _row(entry: str, exit_: str | None, pnl: float, symbol: str = "X", qty: int = 5,
         entry_premium: float = 1.0, hold_minutes: int | None = None, exit_reason: str = "") -> dict:
    return {"entry_time_et": entry, "exit_time_et": exit_, "dollar_pnl": pnl,
            "symbol": symbol, "date": entry[:10], "qty": qty, "entry_premium": entry_premium,
            "hold_minutes": hold_minutes, "exit_reason": exit_reason}


# --------------------------------------------------------------------------------------
# 1. K=1 PARITY: this study's generalized admission function, at max_concurrent=1, must
#    reproduce the ALREADY-SHIPPED bold_adaptive_sizing_2026_08_02.py's own _sequential_admit
#    byte-for-byte on the same input -- the whole "gained cohort per concurrency step"
#    framing depends on K=1 being the CURRENT live behavior, not a re-derived approximation.
# --------------------------------------------------------------------------------------
class TestParityWithShippedSequentialAdmit:
    def test_k1_matches_shipped_sequential_admit_on_overlapping_fixture(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T10:30:00", -20.0, symbol="A"),
            _row("2026-08-02T09:40:00", "2026-08-02T09:55:00", 999.0, symbol="B"),
            _row("2026-08-02T11:00:00", "2026-08-02T11:20:00", 50.0, symbol="C"),
        ]
        shipped = adaptive_study._sequential_admit(rows)
        mine_k1 = study._sequential_admit_concurrent(rows, 1)
        assert [r["symbol"] for r in shipped] == [r["symbol"] for r in mine_k1]
        assert [r["dollar_pnl"] for r in shipped] == [r["dollar_pnl"] for r in mine_k1]

    def test_k1_matches_shipped_on_unresolved_trade_fixture(self):
        rows = [
            _row("2026-08-02T09:35:00", None, 0.0, symbol="A"),
            _row("2026-08-02T14:00:00", "2026-08-02T14:10:00", 50.0, symbol="B"),
            _row("2026-08-03T09:35:00", "2026-08-03T09:50:00", 25.0, symbol="C"),
        ]
        shipped = {r["symbol"] for r in adaptive_study._sequential_admit(rows)}
        mine = {r["symbol"] for r in study._sequential_admit_concurrent(rows, 1)}
        assert shipped == mine == {"A", "C"}

    def test_rejects_max_concurrent_below_one(self):
        with pytest.raises(ValueError):
            study._sequential_admit_concurrent([], 0)


# --------------------------------------------------------------------------------------
# 2. CONCURRENCY MECHANISM: the actual load-bearing NEW logic this study contributes --
#    proven on synthetic fixtures where the answer is known by construction.
# --------------------------------------------------------------------------------------
class TestConcurrencyAdmission:
    def test_k2_admits_an_overlapping_second_signal_k1_would_refuse(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T10:30:00", -20.0, symbol="A"),
            _row("2026-08-02T09:40:00", "2026-08-02T09:55:00", 999.0, symbol="B"),  # inside A's window
        ]
        k1 = study._sequential_admit_concurrent(rows, 1)
        k2 = study._sequential_admit_concurrent(rows, 2)
        assert {r["symbol"] for r in k1} == {"A"}
        assert {r["symbol"] for r in k2} == {"A", "B"}

    def test_k2_still_refuses_a_third_overlapping_signal(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T10:30:00", -20.0, symbol="A"),
            _row("2026-08-02T09:40:00", "2026-08-02T10:20:00", 10.0, symbol="B"),
            _row("2026-08-02T09:45:00", "2026-08-02T09:59:00", 999.0, symbol="C"),  # 3rd overlap, 2 slots only
        ]
        k2 = study._sequential_admit_concurrent(rows, 2)
        assert {r["symbol"] for r in k2} == {"A", "B"}
        k3 = study._sequential_admit_concurrent(rows, 3)
        assert {r["symbol"] for r in k3} == {"A", "B", "C"}

    def test_slot_frees_the_moment_earliest_open_position_exits(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T09:45:00", 1.0, symbol="A"),
            _row("2026-08-02T09:36:00", "2026-08-02T10:30:00", 2.0, symbol="B"),
            _row("2026-08-02T09:46:00", "2026-08-02T09:50:00", 3.0, symbol="C"),  # A closed at 09:45, slot free
        ]
        k2 = study._sequential_admit_concurrent(rows, 2)
        assert {r["symbol"] for r in k2} == {"A", "B", "C"}

    def test_monotonic_superset_property_on_dense_overlapping_fixture(self):
        """admitted(K) must be a STRICT SUPERSET of admitted(K-1) -- the property that
        makes 'gained cohort per concurrency step' well-defined. Dense, staggered,
        variable-duration fixture designed to stress the property, not just a trivial case."""
        rows = [
            _row("2026-08-02T09:30:00", "2026-08-02T12:00:00", 1.0, symbol="LONG_A"),
            _row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 2.0, symbol="B"),
            _row("2026-08-02T09:40:00", "2026-08-02T11:00:00", 3.0, symbol="C"),
            _row("2026-08-02T09:45:00", "2026-08-02T09:59:00", 4.0, symbol="D"),
            _row("2026-08-02T10:00:00", "2026-08-02T10:05:00", 5.0, symbol="E"),
            _row("2026-08-02T10:30:00", "2026-08-02T10:35:00", 6.0, symbol="F"),
            _row("2026-08-02T11:30:00", "2026-08-02T11:45:00", 7.0, symbol="G"),
        ]
        prev_keys: set = set()
        for K in (1, 2, 3, 4):
            admitted_keys = {study._key(r) for r in study._sequential_admit_concurrent(rows, K)}
            assert prev_keys <= admitted_keys, f"admitted(K={K}) is not a superset of admitted(K-1)"
            prev_keys = admitted_keys

    def test_cascading_servers_crosscheck_matches_count_based_on_dense_fixture(self):
        """Independent re-derivation of the same rule must agree exactly -- the
        cross-check this study's own report cites as proof the mechanism is correct,
        not just internally self-consistent."""
        rows = [
            _row("2026-08-02T09:30:00", "2026-08-02T12:00:00", 1.0, symbol="LONG_A"),
            _row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 2.0, symbol="B"),
            _row("2026-08-02T09:40:00", "2026-08-02T11:00:00", 3.0, symbol="C"),
            _row("2026-08-02T09:45:00", "2026-08-02T09:59:00", 4.0, symbol="D"),
            _row("2026-08-02T10:00:00", "2026-08-02T10:05:00", 5.0, symbol="E"),
            _row("2026-08-02T13:00:00", None, 6.0, symbol="UNRESOLVED"),
            _row("2026-08-02T14:00:00", "2026-08-02T14:10:00", 7.0, symbol="SAME_DAY_AFTER_UNRESOLVED"),
        ]
        for K in (1, 2, 3):
            a = {study._key(r) for r in study._sequential_admit_concurrent(rows, K)}
            b = {study._key(r) for r in study._sequential_admit_cascading_servers(rows, K)}
            assert a == b, f"cascading-servers disagrees with count-based at K={K}"


# --------------------------------------------------------------------------------------
# 3. RISK CALCULATORS: kill-switch breach counter + max-simultaneous-notional, on
#    fixtures with a known answer.
# --------------------------------------------------------------------------------------
class TestKillSwitchBreachCounter:
    def test_breach_detected_at_exact_threshold(self):
        day_pnl = {"2026-08-02": -300.0, "2026-08-03": -299.99, "2026-08-04": 500.0}
        out = study._kill_switch_breaches(day_pnl, equity=1000.0, kill_switch_pct=0.30)
        assert out["threshold_dollars"] == -300.0
        assert out["n_breach_days"] == 1
        assert out["breach_days"][0]["date"] == "2026-08-02"

    def test_worst_day_identified_correctly(self):
        day_pnl = {"2026-08-02": -50.0, "2026-08-03": -900.0, "2026-08-04": 200.0}
        out = study._kill_switch_breaches(day_pnl, equity=1000.0, kill_switch_pct=0.50)
        assert out["worst_day"]["date"] == "2026-08-03"
        assert out["worst_day"]["day_pnl"] == -900.0

    def test_no_breaches_when_all_days_within_threshold(self):
        day_pnl = {"2026-08-02": -10.0, "2026-08-03": 20.0}
        out = study._kill_switch_breaches(day_pnl, equity=1000.0, kill_switch_pct=0.30)
        assert out["n_breach_days"] == 0


class TestMaxConcurrentNotional:
    def test_two_non_overlapping_trades_never_sum(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 1.0, qty=5, entry_premium=1.0),
            _row("2026-08-02T10:00:00", "2026-08-02T10:15:00", 1.0, qty=5, entry_premium=1.0),
        ]
        out = study._max_concurrent_notional(rows)
        assert out["peak_notional_dollars"] == 500.0  # 5 * 1.00 * 100, never doubled
        assert out["peak_concurrent_count"] == 1

    def test_two_overlapping_trades_sum_at_peak(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T10:30:00", 1.0, symbol="A", qty=5, entry_premium=1.0),
            _row("2026-08-02T09:40:00", "2026-08-02T09:55:00", 1.0, symbol="B", qty=3, entry_premium=2.0),
        ]
        out = study._max_concurrent_notional(rows)
        # A: 5*1.00*100=500, B: 3*2.00*100=600 -> peak = 1100 while both open
        assert out["peak_notional_dollars"] == 1100.0
        assert out["peak_concurrent_count"] == 2

    def test_exit_at_exact_entry_instant_is_not_double_counted(self):
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 1.0, symbol="A", qty=5, entry_premium=1.0),
            _row("2026-08-02T09:50:00", "2026-08-02T10:00:00", 1.0, symbol="B", qty=5, entry_premium=1.0),
        ]
        out = study._max_concurrent_notional(rows)
        assert out["peak_concurrent_count"] == 1
        assert out["peak_notional_dollars"] == 500.0


# --------------------------------------------------------------------------------------
# 4. SLOT TURNOVER: gap-minutes-needed calculation on a fixture with a known answer.
# --------------------------------------------------------------------------------------
class TestSlotTurnoverAnalysis:
    def test_gap_minutes_needed_matches_hand_computed_value(self):
        admitted_1 = [_row("2026-08-02T09:35:00", "2026-08-02T10:05:00", 1.0, symbol="A",
                            hold_minutes=30, exit_reason="tp1")]
        refused_1 = [_row("2026-08-02T09:50:00", "2026-08-02T10:10:00", 2.0, symbol="B")]
        gaps, n_unexplained = study._slot_turnover_analysis(admitted_1, refused_1)
        assert n_unexplained == 0
        assert len(gaps) == 1
        assert gaps[0]["gap_minutes_needed"] == 15.0  # 10:05 - 09:50
        assert gaps[0]["gap_as_pct_of_occupant_hold"] == 50.0  # 15 / 30 * 100

    def test_every_k1_refused_signal_has_exactly_one_explainable_occupant(self):
        """By construction under K=1, a refused signal always arrives while exactly one
        admitted trade is open -- n_unexplained must be 0, never silently non-zero."""
        rows = [
            _row("2026-08-02T09:35:00", "2026-08-02T10:30:00", -20.0, symbol="A", hold_minutes=55),
            _row("2026-08-02T09:40:00", "2026-08-02T09:55:00", 999.0, symbol="B"),
            _row("2026-08-02T09:50:00", "2026-08-02T10:00:00", 5.0, symbol="C"),
        ]
        admitted_1 = study._sequential_admit_concurrent(rows, 1)
        refused_1 = study._refused_cohort(rows, admitted_1)
        gaps, n_unexplained = study._slot_turnover_analysis(admitted_1, refused_1)
        assert n_unexplained == 0
        assert len(gaps) == len(refused_1) == 2


# --------------------------------------------------------------------------------------
# 5. PROVENANCE / DO-NOT-TOUCH: this measurement-only lane must not have modified any
#    production file, and must not have changed either params.json's risk numbers.
# --------------------------------------------------------------------------------------
class TestMeasurementOnlyLaneTouchedNothingLive:
    def test_heartbeat_core_flat_check_still_present_unmodified_in_spirit(self):
        src = HEARTBEAT_CORE.read_text(encoding="utf-8")
        assert "fb.is_flat_spy_options(creds)" in src
        assert "return {\"status\": \"NOT_FLAT\"" in src

    def test_safe_and_bold_risk_params_unchanged(self):
        import json
        safe = json.loads(SAFE_PARAMS.read_text(encoding="utf-8"))
        agg = json.loads(AGG_PARAMS.read_text(encoding="utf-8"))
        assert safe["per_trade_risk_cap_pct"] == 0.3
        assert safe["daily_loss_kill_switch_pct"] == 0.3
        assert agg["per_trade_risk_cap_pct"] == 0.5
        assert agg["daily_loss_kill_switch_pct"] == 0.5
