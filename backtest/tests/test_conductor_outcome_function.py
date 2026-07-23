"""Guards for the 2026-07-01 conductor_outcome re-aim (pipeline-audit fix #5).

WHAT THIS GUARDS: the autonomy metric used to measure ARTIFACTS only
(drained/lessons/tests) — "a fire adding 41 tests scores like one making an
order fill" (markdown/audits/PIPELINE-AUDIT-2026-07-01.md). Now every recorded
fire snapshots the TRADING FUNCTION funnel from the ledgers and the trend
weights function over artifact count. These tests RED if:

  1. record() stops writing the function fields
     (enters_last_trading_day / orders_accepted / fills / distinct_setups_traded).
  2. trading_function_snapshot() misreads the ledgers (core ENTER verdicts,
     PLACED execs, fleet placed=True, trades.csv fills, distinct setups).
  3. the trend goes back to artifact-only (a fills-up half must beat an
     artifact-heavy half).

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_conductor_outcome_function.py -q
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "conductor_outcome.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("conductor_outcome_fn", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def co(tmp_path, monkeypatch):
    """Module with ALL path constants (state + ledgers) redirected to tmp_path."""
    mod = _load_module()
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUTCOMES_FILE", tmp_path / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "METRIC_FILE", tmp_path / "autonomy-metric.json")
    monkeypatch.setattr(mod, "DECISIONS_FILE", tmp_path / "core-decisions.jsonl")
    monkeypatch.setattr(mod, "FLEET_DIR", tmp_path / "fleet")
    monkeypatch.setattr(mod, "TRADES_CSV", tmp_path / "trades.csv")
    return mod


def _write_core_ledger(co):
    rows = [
        # older day — must be ignored by the last-trading-day snapshot
        {"ts_et": "2026-06-30T10:00:00", "verdict": "ENTER_BEAR",
         "exec": {"status": "PLACED", "setup": "OLD_SETUP"}},
        # last trading day
        {"ts_et": "2026-07-01T10:00:00", "verdict": "HOLD"},
        {"ts_et": "2026-07-01T11:00:00", "verdict": "ENTER_BULL",
         "exec": {"status": "PLACE_FAIL", "setup": "BULLISH_RECLAIM"}},
        {"ts_et": "2026-07-01T12:00:00", "verdict": "ENTER_BEAR",
         "exec": {"status": "PLACED", "setup": "BEARISH_REJECTION"}},
    ]
    co.DECISIONS_FILE.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def _write_fleet_ledger(co):
    arm = co.FLEET_DIR / "risky-1"
    arm.mkdir(parents=True, exist_ok=True)
    rows = [
        {"ts_et": "2026-07-01T11:22:01-04:00", "action": "ENTER_BULL",
         "setup_name": "BULLISH_RECLAIM",
         "placement": {"mode": "LIVE", "placed": True}},
        {"ts_et": "2026-07-01T11:25:01-04:00", "action": "HOLD",
         "placement": {"mode": "LIVE", "placed": False, "reason": "not_enter"}},
    ]
    (arm / "decisions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def _write_trades_csv(co):
    co.TRADES_CSV.write_text(
        "date,time_entry,time_exit,setup,contract\n"
        "2026-06-26,14:54,15:45,BEARISH_REJECTION,SPYx\n"
        "2026-07-01,11:22,11:34,VWAP_CONTINUATION,SPYy\n"
        "2026-07-01,13:00,13:30,BEARISH_REJECTION,SPYz\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 1+2. Snapshot reads the ledgers correctly.
# ---------------------------------------------------------------------------
def test_snapshot_counts_last_trading_day_funnel(co):
    _write_core_ledger(co)
    _write_fleet_ledger(co)
    _write_trades_csv(co)
    snap = co.trading_function_snapshot()
    assert snap["trading_day"] == "2026-07-01"
    # core: 2 ENTER verdicts on 07-01 + fleet: 1 ENTER action = 3
    assert snap["enters_last_trading_day"] == 3
    # core: 1 exec PLACED + fleet: 1 placement.placed=True = 2
    assert snap["orders_accepted"] == 2
    # trades.csv: 2 rows dated 07-01 (the 06-26 row must be excluded)
    assert snap["fills"] == 2
    # setups: BEARISH_REJECTION (core PLACED + csv), BULLISH_RECLAIM (fleet),
    # VWAP_CONTINUATION (csv) — OLD_SETUP from 06-30 excluded.
    assert snap["distinct_setups_traded"] == 3


def test_snapshot_missing_ledgers_yields_zeros_never_raises(co):
    snap = co.trading_function_snapshot()  # nothing written at all
    assert snap["trading_day"] == ""
    assert snap["enters_last_trading_day"] == 0
    assert snap["orders_accepted"] == 0
    assert snap["fills"] == 0
    assert snap["distinct_setups_traded"] == 0
    assert snap["extra_exec_orders_accepted"] == 0


# ---------------------------------------------------------------------------
# EXTRA-EXEC VISIBILITY (2026-07-23): a core row can carry an `extra_exec`
# list — secondary setups (vwap_continuation, bollinger_squeeze...) routed +
# placed OUTSIDE the primary verdict/exec pipeline (_route_extra_setups in
# heartbeat_core.py). Before this fix a day with 0 primary ENTERs but real
# extra_exec PLACED fills silently read "0 orders_accepted" here — the exact
# live mismatch on 2026-07-22 (0 primary orders_accepted, 2 real extra_exec
# fills) that 3 straight conductor fires flagged as "worth a dedicated look."
# fill_funnel.py already fixed this same blind spot on 2026-07-22 for its own
# report; this guard pins the matching fix in conductor_outcome.py.
# ---------------------------------------------------------------------------
def _write_core_ledger_with_extra_exec(co):
    rows = [
        {"ts_et": "2026-07-05T09:51:00", "verdict": "HOLD",
         "extra_exec": [
             {"setup": "vwap_continuation", "action": "PLACED"},
             {"setup": "vwap_continuation", "action": "WATCH_NOT_ARMED"},
         ]},
        {"ts_et": "2026-07-05T13:31:00", "verdict": "HOLD",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED"}]},
        {"ts_et": "2026-07-05T13:32:00", "verdict": "HOLD",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "SKIP_COOLDOWN_SAME_BAR"}]},
    ]
    co.DECISIONS_FILE.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def test_snapshot_counts_extra_exec_placed_separately_from_primary(co):
    _write_core_ledger_with_extra_exec(co)
    snap = co.trading_function_snapshot()
    assert snap["trading_day"] == "2026-07-05"
    # zero PRIMARY ENTERs/orders_accepted -- extra_exec must not contaminate
    # the primary-pipeline signal (matches fill_funnel.py's scoping choice).
    assert snap["enters_last_trading_day"] == 0
    assert snap["orders_accepted"] == 0
    # 2 PLACED extra_exec rows (vwap_continuation + bollinger_squeeze); the
    # WATCH_NOT_ARMED / SKIP_COOLDOWN_SAME_BAR rows must not count.
    assert snap["extra_exec_orders_accepted"] == 2
    # both extra_exec setups counted toward distinct_setups_traded too
    assert snap["distinct_setups_traded"] == 2


def test_record_and_metric_carry_extra_exec_field(co):
    _write_core_ledger_with_extra_exec(co)
    row = co.record(task_id="T-extra")
    assert row is not None
    assert row["extra_exec_orders_accepted"] == 2
    metric = co.compute_metric(window=20)
    assert metric["function_latest"]["extra_exec_orders_accepted"] == 2
    # score now counts extra_exec PLACED at the same weight as orders_accepted (x2)
    assert metric["function_score_avg"] == 4.0


def test_record_writes_function_fields(co):
    _write_core_ledger(co)
    row = co.record(task_id="T1", items_drained=1)
    assert row is not None
    for key in (
        "trading_day",
        "enters_last_trading_day",
        "orders_accepted",
        "fills",
        "distinct_setups_traded",
    ):
        assert key in row, f"function field {key} missing from outcome row"
    assert row["enters_last_trading_day"] == 2
    assert row["orders_accepted"] == 1
    # persisted, not just returned
    on_disk = json.loads(co.OUTCOMES_FILE.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk["orders_accepted"] == 1


# ---------------------------------------------------------------------------
# 3. Trend weights FUNCTION over artifact count.
# ---------------------------------------------------------------------------
def _snap(enters=0, accepted=0, fills=0, setups=0, day="2026-07-01"):
    return {
        "trading_day": day,
        "enters_last_trading_day": enters,
        "orders_accepted": accepted,
        "fills": fills,
        "distinct_setups_traded": setups,
    }


def test_trend_function_beats_artifacts(co):
    # Older half: artifact-heavy (tons drained), zero trading function.
    co.record(task_id="o1", items_drained=10, tests_delta=41, function_snapshot=_snap())
    co.record(task_id="o2", items_drained=10, tests_delta=41, function_snapshot=_snap())
    # Recent half: barely any artifacts, but the rig actually traded.
    co.record(task_id="r1", items_drained=0, function_snapshot=_snap(enters=2, accepted=1, fills=1))
    co.record(task_id="r2", items_drained=0, function_snapshot=_snap(enters=2, accepted=1, fills=1))
    metric = co.compute_metric(window=20)
    # Artifact-only trend would say "regressing" (20 drained -> 0). Function wins.
    assert metric["trend"] == "improving"


def test_trend_function_loss_is_regressing_despite_artifacts(co):
    # BITE (inverse): trading stopped, artifacts exploded -> regressing.
    co.record(task_id="o1", items_drained=0, function_snapshot=_snap(enters=2, accepted=1, fills=1))
    co.record(task_id="o2", items_drained=0, function_snapshot=_snap(enters=2, accepted=1, fills=1))
    co.record(task_id="r1", items_drained=10, tests_delta=41, function_snapshot=_snap())
    co.record(task_id="r2", items_drained=10, tests_delta=41, function_snapshot=_snap())
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "regressing"


def test_trend_falls_back_to_artifacts_on_function_tie(co):
    # Equal function halves (all zero) -> legacy artifact comparison decides.
    co.record(task_id="o1", items_drained=0, function_snapshot=_snap())
    co.record(task_id="o2", items_drained=0, function_snapshot=_snap())
    co.record(task_id="r1", items_drained=3, function_snapshot=_snap())
    co.record(task_id="r2", items_drained=3, function_snapshot=_snap())
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "improving"


def test_metric_carries_function_fields(co):
    co.record(task_id="a", function_snapshot=_snap(enters=5, accepted=2, fills=1, setups=2))
    metric = co.compute_metric(window=20)
    assert metric["function_latest"]["enters_last_trading_day"] == 5
    assert metric["function_latest"]["orders_accepted"] == 2
    assert metric["function_latest"]["fills"] == 1
    assert metric["function_latest"]["distinct_setups_traded"] == 2
    assert metric["function_latest"]["trading_day"] == "2026-07-01"
    # fills x3 + accepted x2 + enters x1 = 3 + 4 + 5 = 12
    assert metric["function_score_avg"] == 12.0
