"""Guards for backtest/autoresearch/core_strategy_recency.py -- WS11 CORE-STRATEGY
RECENCY WIRING (2026-08-01). The revalidation clock for the CORE RIDE_THE_RIBBON
strategy itself, per J's 2026-07-31 recency rule.

Pin, in order:
  1. leg-grouping: tp1 + runner legs of ONE entry count as ONE trade (n = entries,
     never legs -- the n-inflation trap);
  2. cohort hygiene: non-family setups, fleet-vs-core lane split, unattributed
     accounts, side/setup mismatches all excluded AND counted;
  3. the frozen verdict rules incl. boundaries (n==floor, exp==0);
  4. the NEVER-BLEND rail: a huge replay supplement can never lift an UNDERPOWERED
     broker cell over the floor;
  5. registry integration: both core_strategy rows exist in gate-registry.json with
     the full column set, and gate_expiry_check.check_gate ROUTES category
     "core_strategy" to this module (RED-proof: without the routing branch the checker
     would mine core-decisions verdicts that don't exist for a non-gate row);
  6. verdict-vocabulary mapping onto the checker surface (UNDERPOWERED -> YELLOW,
     NO_FILLS -> INSUFFICIENT_DATA, RED -> RED so the newly-RED STATUS flag fires).

No real market data, no network, no heavy replay -- evaluate() is always monkeypatched
where integration is under test.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from autoresearch import core_strategy_recency as csr
from autoresearch import gate_expiry_check as gec

W_START = dt.date(2026, 6, 26)
W_END = dt.date(2026, 7, 31)
FLEET_IDS = {"safe-1", "safe-3", "risky-1", "risky-3"}


def _row(date="2026-07-31", time_entry="12:19:03", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
         contract="SPY 2026-07-31 746C", c_or_p="C", pnl="96", account="safe"):
    return {"date": date, "time_entry": time_entry, "setup": setup, "contract": contract,
            "c_or_p": c_or_p, "dollar_pnl": pnl, "account_id": account}


# ─────────────────────────────────────────────────────────────────────────────
# 1. leg grouping
# ─────────────────────────────────────────────────────────────────────────────

def test_group_fills_folds_legs_of_one_entry_into_one_trade():
    """The 2026-07-31 12:19 746C shape: tp1 leg +$96 and runner leg +$30 share
    (account, date, time_entry, contract) -> ONE +$126 trade, n=1."""
    rows = [_row(pnl="96"), _row(pnl="30")]
    events, _ = csr.group_fills(rows, W_START, W_END, FLEET_IDS)
    assert len(events) == 1
    assert events[0]["pnl"] == pytest.approx(126.0)
    assert events[0]["n_legs"] == 2


def test_group_fills_keeps_distinct_entries_separate():
    rows = [_row(time_entry="12:19:03"), _row(time_entry="13:25:05")]
    events, _ = csr.group_fills(rows, W_START, W_END, FLEET_IDS)
    assert len(events) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. cohort hygiene
# ─────────────────────────────────────────────────────────────────────────────

def test_group_fills_excludes_and_counts_non_family():
    rows = [_row(setup="bollinger_squeeze")]
    events, excl = csr.group_fills(rows, W_START, W_END, FLEET_IDS)
    assert events == []
    assert excl["non_family"] == 1


def test_group_fills_splits_core_vs_fleet_lane():
    rows = [_row(account="safe"), _row(account="risky-3", time_entry="09:31:00")]
    events, _ = csr.group_fills(rows, W_START, W_END, FLEET_IDS)
    lanes = {e["account"]: e["lane"] for e in events}
    assert lanes == {"safe": "core", "risky-3": "fleet"}


def test_group_fills_fleet_lane_matches_pattern_beyond_roster():
    """L234: a NEW arm (not yet in the passed roster set) must still land in the fleet
    lane via the shape pattern, never silently in unattributed."""
    rows = [_row(account="risky-9")]
    events, excl = csr.group_fills(rows, W_START, W_END, fleet_ids=set())
    assert len(events) == 1 and events[0]["lane"] == "fleet"
    assert excl["unattributed_account"] == 0


def test_group_fills_counts_unattributed_and_mismatch_and_bad_pnl():
    rows = [
        _row(account=""),                                            # blank account
        _row(c_or_p="P"),                                            # P on a BULLISH row
        _row(pnl="not-a-number", time_entry="10:00:00"),             # junk pnl
        _row(date="junk"),                                           # junk date
        _row(date="2026-05-01"),                                     # outside window
    ]
    events, excl = csr.group_fills(rows, W_START, W_END, FLEET_IDS)
    assert events == []
    assert excl["unattributed_account"] == 1
    assert excl["side_setup_mismatch"] == 1
    assert excl["bad_pnl"] == 1
    assert excl["bad_date"] == 1
    assert excl["outside_window"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. frozen verdict rules
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell,expected", [
    ({"n": 0}, "NO_FILLS"),
    ({"n": 3, "exp_per_trade": 50.0}, "UNDERPOWERED"),
    ({"n": 9, "exp_per_trade": -50.0}, "UNDERPOWERED"),      # floor-1 boundary
    ({"n": 10, "exp_per_trade": 5.0}, "GREEN"),              # n==floor counts
    ({"n": 10, "exp_per_trade": 0.0}, "RED"),                # exact zero is NOT green
    ({"n": 15, "exp_per_trade": -40.6}, "RED"),
])
def test_direction_verdict_matrix(cell, expected):
    verdict, _ = csr.direction_verdict(cell, floor=10)
    assert verdict == expected


def test_direction_verdict_underpowered_reason_names_the_floor():
    _, reason = csr.direction_verdict({"n": 2, "exp_per_trade": -147.5}, floor=10)
    assert "n=2" in reason and "floor 10" in reason


# ─────────────────────────────────────────────────────────────────────────────
# 4. NEVER-BLEND rail
# ─────────────────────────────────────────────────────────────────────────────

def test_replay_supplement_never_lifts_n_over_the_floor(monkeypatch):
    """A 50-trade replay supplement must NOT turn a 2-fill broker cell into a verdict.
    This is the WS11 honesty rail ('never blended silently') as an executable check:
    the verdict is computed from the broker cell alone."""
    fake_block = {
        "verdicts": {
            "bull": {"verdict": "UNDERPOWERED", "n": 2, "exp_per_trade": -147.5,
                     "reason": "n=2 < floor 10 on real fills (negative $-147.5/tr) "
                               "-- no verdict manufactured; see replay supplement; "
                               "replay supplement (Safe shape, engine-sim, DISCLOSED "
                               "not blended): n=50 exp=$12.0/tr recent",
                     "headline": "bull UNDERPOWERED n=2"},
            "bear": {"verdict": "RED", "n": 15, "exp_per_trade": -40.6,
                     "reason": "x", "headline": "bear RED n=15"},
        },
        "window": {"start": "2026-06-26", "end": "2026-07-31", "n_trading_days": 25},
        "strata": {"broker_core": {"bull": {"n": 2}, "bear": {"n": 15}},
                   "replay_supplement_safe_shape": {
                       "recent": {"bull": {"n": 50, "exp_per_trade": 12.0},
                                  "bear": {"n": 40, "exp_per_trade": -5.0}}}},
    }
    monkeypatch.setattr(csr, "evaluate", lambda **kw: fake_block)
    out = csr.evaluate_for_registry({"id": "core_strategy_bull"})
    # UNDERPOWERED on the checker surface is YELLOW -- never GREEN via the supplement's n
    assert out["verdict"] == "YELLOW"
    assert out["core_strategy_verdict"] == "UNDERPOWERED"
    assert out["broker_core"]["n"] == 2               # broker n is what's reported
    assert out["replay_supplement"]["n"] == 50        # supplement quoted alongside


def test_direction_verdict_has_no_supplement_parameter():
    """Static rail: direction_verdict's signature takes ONLY (cell, floor) -- there is no
    code path by which replay rows can enter the verdict."""
    import inspect
    params = list(inspect.signature(csr.direction_verdict).parameters)
    assert params == ["cell", "floor"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. registry rows + checker routing (RED until the integration edits land)
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_has_both_core_strategy_rows_with_full_columns():
    registry = gec.load_registry()
    rows = {g["id"]: g for g in registry["gates"] if g.get("category") == "core_strategy"}
    assert set(rows) == {"core_strategy_bear", "core_strategy_bull"}, (
        "gate-registry.json must carry exactly the two core_strategy rows")
    # single source for the column contract: the sibling guard file's REQUIRED_GATE_KEYS
    # (loaded by path -- bare cross-test imports break under pytest package-mode collection)
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "_gec_guards", Path(__file__).resolve().parent / "test_gate_expiry_check.py")
    _gec_guards = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_gec_guards)
    REQUIRED_GATE_KEYS = _gec_guards.REQUIRED_GATE_KEYS
    for gid, row in rows.items():
        missing = REQUIRED_GATE_KEYS - set(row.keys())
        assert not missing, f"{gid} missing columns: {missing}"
        assert row["revalidation_interval_days"] == 14, (
            "core strategy carries the tightened 14-day clock (recency is first-class)")


def test_check_gate_routes_core_strategy_category_to_this_module(monkeypatch):
    """The load-bearing integration: category='core_strategy' must reach
    csr.evaluate_for_registry and must NEVER fall through to evaluate_gate_pnl (which
    mines core-decisions.jsonl for SKIP verdicts that do not exist for a strategy row)."""
    sentinel = {"verdict": "GREEN", "reason": "sentinel-from-csr"}
    called = {"csr": 0, "miner": 0}

    def _fake_registry_eval(gate, floor=10, **kw):
        called["csr"] += 1
        return dict(sentinel)

    def _miner_must_not_run(*a, **kw):
        called["miner"] += 1
        raise AssertionError("evaluate_gate_pnl must not run for core_strategy rows")

    monkeypatch.setattr(csr, "evaluate_for_registry", _fake_registry_eval)
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _miner_must_not_run)

    gate = {"id": "core_strategy_bear", "category": "core_strategy",
            "skip_action": "n/a", "accounts_armed": {"safe": True, "bold": True},
            "last_revalidated": "2026-08-01", "revalidation_interval_days": 14}
    today = dt.date(2026, 8, 1)
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)
    assert called["csr"] == 1 and called["miner"] == 0
    assert result["pnl_check"]["reason"] == "sentinel-from-csr"
    assert result["overall"] == "GREEN"


def test_check_gate_core_strategy_red_flows_to_overall_red(monkeypatch):
    """RED-proof end-to-end: a RED core-strategy verdict must surface as overall=RED so
    the newly-RED STATUS.md flag path fires exactly like any other gate."""
    monkeypatch.setattr(csr, "evaluate_for_registry",
                        lambda gate, floor=10, **kw: {"verdict": "RED",
                                                      "reason": "core bear losing (fake)"})
    gate = {"id": "core_strategy_bear", "category": "core_strategy",
            "skip_action": "n/a", "accounts_armed": {"safe": True, "bold": True},
            "last_revalidated": "2026-08-01", "revalidation_interval_days": 14}
    today = dt.date(2026, 8, 1)
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)
    assert result["overall"] == "RED"


def test_check_gate_core_strategy_fail_open_on_eval_exception(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("simulated frame-load failure")
    monkeypatch.setattr(csr, "evaluate_for_registry", _boom)
    gate = {"id": "core_strategy_bull", "category": "core_strategy",
            "skip_action": "n/a", "accounts_armed": {"safe": True, "bold": True},
            "last_revalidated": "2026-08-01", "revalidation_interval_days": 14}
    today = dt.date(2026, 8, 1)
    result = gec.check_gate(gate, None, None, None, today, today, 10, today)  # must not raise
    assert result["overall"] == "ERROR"
    assert "simulated frame-load failure" in result["pnl_check"]["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. checker-vocabulary mapping
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("core_verdict,checker_verdict", [
    ("GREEN", "GREEN"), ("RED", "RED"),
    ("UNDERPOWERED", "YELLOW"), ("NO_FILLS", "INSUFFICIENT_DATA"),
])
def test_verdict_vocabulary_mapping(monkeypatch, core_verdict, checker_verdict):
    fake_block = {
        "verdicts": {"bear": {"verdict": core_verdict, "n": 0, "exp_per_trade": None,
                              "reason": "r", "headline": f"bear {core_verdict} n=0"}},
        "window": {}, "strata": {"broker_core": {"bear": {"n": 0}},
                                 "replay_supplement_safe_shape": None},
    }
    monkeypatch.setattr(csr, "evaluate", lambda **kw: fake_block)
    out = csr.evaluate_for_registry({"id": "core_strategy_bear"})
    assert out["verdict"] == checker_verdict


def test_unknown_registry_id_is_not_measured():
    out = csr.evaluate_for_registry({"id": "core_strategy_sideways"})
    assert out["verdict"] == "NOT_MEASURED"


def test_report_only_static_guard():
    """This module must never place orders or write params (report-only by design)."""
    src = (csr.REPO / "autoresearch" / "core_strategy_recency.py").read_text(encoding="utf-8")
    for token in ("place_option_order", "place_stock_order", "params.json\", \"w"):
        assert token not in src
