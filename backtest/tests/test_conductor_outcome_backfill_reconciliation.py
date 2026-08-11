"""Guard for the 2026-08-11 backfill-lag reconciliation fix.

WHAT THIS GUARDS: conductor_outcome rows are point-in-time snapshots of
journal/trades.csv taken when record() fired. fleet_journal_bridge.py
backfills trades.csv from broker-truth (pnl-statement.json) on its OWN
schedule, well after a trading day ends -- so a conductor fire that fires
BEFORE that backfill catches up correctly snapshots `fills: 0` for a day that
actually traded fine. Live-verified 2026-08-11: 3 consecutive fires all
recorded `fills: 0` for 2026-08-10 while `fill_funnel.py --date 2026-08-10`
(broker-truth) showed GREEN with real fills, and re-running
trading_function_snapshot() live afterward returned a real nonzero count.

Without reconciliation this pollutes BOTH `function_latest` (a downstream
consumer reads a stale "0 fills today" and could wrongly treat the trading
function as broken -- the exact VERIFY-2026-08-10-ZERO-FILLS-DESPITE-ACCEPTED-
ORDERS false alarm that forced this investigation) and `trend` (several
same-night zero-fill snapshots for one real trading day can flip "regressing"
purely from timing, not from anything actually wrong).

compute_metric() now reconciles function fields per trading_day to the
MAX seen across the full outcome history before computing function_latest/
trend/function_score_avg -- safe because fills/orders/enters are monotonically
non-decreasing as a completed day's ledgers get backfilled. The rows on disk
are never rewritten (append-only ledger intact); this is a read-layer fix only.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_conductor_outcome_backfill_reconciliation.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "conductor_outcome.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("conductor_outcome_bfr", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def co(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUTCOMES_FILE", tmp_path / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "METRIC_FILE", tmp_path / "autonomy-metric.json")
    monkeypatch.setattr(mod, "DECISIONS_FILE", tmp_path / "core-decisions.jsonl")
    monkeypatch.setattr(mod, "FLEET_DIR", tmp_path / "fleet")
    monkeypatch.setattr(mod, "TRADES_CSV", tmp_path / "trades.csv")
    return mod


def _snap(enters=0, accepted=0, fills=0, setups=0, extra=0, day="2026-08-10"):
    return {
        "trading_day": day,
        "enters_last_trading_day": enters,
        "orders_accepted": accepted,
        "fills": fills,
        "distinct_setups_traded": setups,
        "extra_exec_orders_accepted": extra,
    }


def test_stale_zero_fill_snapshot_reconciled_to_later_known_max(co):
    # Fire 1 (early evening): fires BEFORE fleet_journal_bridge.py backfills
    # trades.csv -- genuinely, honestly snapshots 0 fills.
    co.record(task_id="early", function_snapshot=_snap(enters=55, accepted=9, fills=0))
    # Fire 2 (later that same night, same trading_day): backfill has landed,
    # a fresh snapshot correctly shows real fills.
    co.record(task_id="later", function_snapshot=_snap(enters=55, accepted=9, fills=11))
    # Fire 3 (still later, no new record() call in between -- mirrors a fire
    # whose OWN task didn't touch the ledgers, e.g. an infra-only fix, so it
    # still gets whatever record() computed live at ITS OWN fire time -- here
    # simulated as another honest 0 to prove the reconciliation is NOT "last
    # row wins" but "max seen for this trading_day wins").
    co.record(task_id="third", function_snapshot=_snap(enters=55, accepted=9, fills=0))

    metric = co.compute_metric(window=20)
    # The metric must report the TRUE known state for 2026-08-10 (11 fills),
    # not the last-recorded row's stale 0 -- this is the exact false-alarm
    # class that cost a conductor fire investigating a non-existent break.
    assert metric["function_latest"]["fills"] == 11
    assert metric["function_latest"]["trading_day"] == "2026-08-10"


def test_reconciliation_does_not_manufacture_a_fake_regression(co):
    # A genuinely quiet OLDER day (real 0s, never backfilled higher).
    co.record(task_id="o1", function_snapshot=_snap(day="2026-08-08", enters=0, accepted=0, fills=0))
    co.record(task_id="o2", function_snapshot=_snap(day="2026-08-08", enters=0, accepted=0, fills=0))
    # A trading day that backfills LATE within the recent half -- must not
    # read as "regressing" just because the first of the two recent rows
    # snapshotted before the backfill landed.
    co.record(task_id="r1", function_snapshot=_snap(day="2026-08-10", enters=55, accepted=9, fills=0))
    co.record(task_id="r2", function_snapshot=_snap(day="2026-08-10", enters=55, accepted=9, fills=11))
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "improving"


def test_reconciliation_never_lowers_a_value_below_stored(co):
    # A day whose snapshots are already monotonically increasing (the normal,
    # non-lagging case) must be completely unaffected by reconciliation.
    co.record(task_id="a", function_snapshot=_snap(day="2026-08-05", enters=10, accepted=2, fills=1))
    co.record(task_id="b", function_snapshot=_snap(day="2026-08-05", enters=10, accepted=2, fills=2))
    metric = co.compute_metric(window=20)
    assert metric["function_latest"]["fills"] == 2


def test_reconciliation_leaves_rows_without_trading_day_untouched(co):
    # A pre-2026-07-01 style row (or any row with no trading_day) must not
    # crash the reconciliation or get contaminated by unrelated days.
    row = co.record(task_id="legacy", function_snapshot={})
    assert row is not None
    metric = co.compute_metric(window=20)
    assert metric["function_latest"]["trading_day"] == ""
    assert metric["function_latest"]["fills"] == 0


def test_on_disk_rows_are_never_mutated_by_reconciliation(co):
    # The append-only ledger on disk must stay exactly as each fire recorded
    # it -- reconciliation is a read-layer correction only, never a rewrite.
    co.record(task_id="early", function_snapshot=_snap(fills=0))
    co.record(task_id="later", function_snapshot=_snap(fills=11))
    co.compute_metric(window=20)  # trigger reconciliation
    rows = co.OUTCOMES_FILE.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    import json
    first = json.loads(rows[0])
    assert first["fills"] == 0, "on-disk row must stay the honest point-in-time snapshot"
