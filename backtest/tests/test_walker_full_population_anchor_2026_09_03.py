"""GUARD for WALKER-REANCHOR-FULL-ENGINE-POPULATION (2026-09-03) --
`backtest/tools/walker_full_population_anchor.py`.

Plumbing-only, per this queue item's own scope: population filter, arm-inclusion rule
(`_ArmAccountMap` extension), and reporting-table shape. NO OPRA network access, NO real
1-min bar fetch, NO real ledger read for the harness-walking path -- fixtures + monkeypatch
only, matching the sibling guard `test_exit_slippage_ablation_plumbing_2026_09_03.py`'s own
pure/synthetic convention.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet",
          "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pytest  # noqa: E402

import pdt_blocked_counterfactual as pbc  # noqa: E402
import walker_full_population_anchor as wfpa  # noqa: E402
import whole_engine_null as wen  # noqa: E402

FIXTURE_ROWS = [
    # in-scope: engine-attributed, arm in POPULATION_ARMS, date in window, complete fields
    {"date": "2026-07-08", "arm": "safe-2", "symbol": "SPY260708C00500000",
     "attribution": "engine", "pnl_dollars": 10.0, "entry_px": 1.0, "qty": 1},
    {"date": "2026-08-01", "arm": "bold-2", "symbol": "SPY260801P00500000",
     "attribution": "engine", "pnl_dollars": -5.0, "entry_px": 1.0, "qty": 1},
    {"date": "2026-08-15", "arm": "safe-3", "symbol": "SPY260815C00500000",
     "attribution": "engine", "pnl_dollars": 20.0, "entry_px": 1.0, "qty": 1},
    {"date": "2026-08-20", "arm": "risky-1", "symbol": "SPY260820P00500000",
     "attribution": "engine", "pnl_dollars": -1.0, "entry_px": 1.0, "qty": 1},
    # excluded: not engine-attributed
    {"date": "2026-07-10", "arm": "safe-2", "symbol": "SPY260710C00500000",
     "attribution": "manual", "pnl_dollars": 5.0, "entry_px": 1.0, "qty": 1},
    # excluded: arm not in scope (risky-3 not gate-scored)
    {"date": "2026-07-10", "arm": "risky-3", "symbol": "SPY260710P00500000",
     "attribution": "engine", "pnl_dollars": 5.0, "entry_px": 1.0, "qty": 1},
    # excluded: outside window (before 2026-07-08)
    {"date": "2026-06-26", "arm": "safe-2", "symbol": "SPY260626C00500000",
     "attribution": "engine", "pnl_dollars": 5.0, "entry_px": 1.0, "qty": 1},
    # excluded: missing qty
    {"date": "2026-07-15", "arm": "safe-2", "symbol": "SPY260715C00500000",
     "attribution": "engine", "pnl_dollars": 5.0, "entry_px": 1.0, "qty": 0},
    # excluded: missing entry_px
    {"date": "2026-07-16", "arm": "bold-2", "symbol": "SPY260716C00500000",
     "attribution": "engine", "pnl_dollars": 5.0, "entry_px": None, "qty": 1},
    # excluded: missing pnl_dollars
    {"date": "2026-07-17", "arm": "risky-1", "symbol": "SPY260717C00500000",
     "attribution": "engine", "pnl_dollars": None, "entry_px": 1.0, "qty": 1},
    # _meta row -- must be skipped like every other loader in this repo skips it
    {"_meta": True, "note": "summary row"},
]


@pytest.fixture()
def fixture_ledger(tmp_path, monkeypatch):
    path = tmp_path / "trades-enriched.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for row in FIXTURE_ROWS:
            fh.write(json.dumps(row) + "\n")
    monkeypatch.setattr(wfpa, "TRADES_ENRICHED", path)
    return path


# --------------------------------------------------------------------------- population filter
def test_load_population_rows_applies_attribution_arm_window_completeness(fixture_ledger):
    rows = wfpa.load_population_rows(wfpa.POPULATION_ARMS, wfpa.WINDOW_START, "2026-09-02")
    symbols = {r["symbol"] for r in rows}
    assert symbols == {"SPY260708C00500000", "SPY260801P00500000", "SPY260815C00500000",
                       "SPY260820P00500000"}, (
        "must keep only engine-attributed, in-scope-arm, in-window, complete rows")


def test_load_population_rows_skips_meta_row(fixture_ledger):
    rows = wfpa.load_population_rows(wfpa.POPULATION_ARMS, wfpa.WINDOW_START, "2026-09-02")
    assert all("_meta" not in r for r in rows)


def test_load_population_rows_excludes_out_of_scope_arm(fixture_ledger):
    rows = wfpa.load_population_rows(wfpa.POPULATION_ARMS, wfpa.WINDOW_START, "2026-09-02")
    assert all(r["arm"] != "risky-3" for r in rows), (
        "risky-3 is not in go_live_gate's ACTIVE_ARMS scope -- must never be pulled in")


def test_load_population_rows_respects_explicit_window(fixture_ledger):
    """PDT-43 subset reuse: same loader, tighter window+arms -- must scope correctly."""
    rows = wfpa.load_population_rows(("safe-2", "bold-2"), "2026-07-08", "2026-08-07")
    assert {r["arm"] for r in rows} <= {"safe-2", "bold-2"}
    assert all("2026-07-08" <= r["date"] <= "2026-08-07" for r in rows)


def test_population_arms_matches_go_live_gate_active_scope():
    """POPULATION_ARMS is imported from whole_engine_null.ACTIVE_ARMS, not retyped -- this
    guards against the two ever silently drifting apart."""
    assert wfpa.POPULATION_ARMS == wen.ACTIVE_ARMS
    assert set(wfpa.POPULATION_ARMS) == {"safe-2", "bold-2", "safe-3", "risky-1"}


def test_latest_session_date(fixture_ledger):
    assert wfpa.latest_session_date() == "2026-08-20"


def test_contracts_for_dedupes_symbol_date_pairs():
    rows = [
        {"symbol": "A", "date": "2026-07-08"}, {"symbol": "A", "date": "2026-07-08"},
        {"symbol": "B", "date": "2026-07-09"},
    ]
    assert wfpa.contracts_for(rows) == [("A", "2026-07-08"), ("B", "2026-07-09")]


# ----------------------------------------------------------------------- arm-inclusion mapping
def test_arm_account_map_preserves_original_core_arms():
    """safe-2/bold-2 must resolve to the EXACT SAME values the original ARM2ACCOUNT dict
    already returned -- no behavior change for the rows the PDT anchor already covered."""
    patched = wfpa._ArmAccountMap(pbc.ARM2ACCOUNT)
    assert patched.get("safe-2") == pbc.ARM2ACCOUNT.get("safe-2") == "safe"
    assert patched.get("bold-2") == pbc.ARM2ACCOUNT.get("bold-2") == "bold"


def test_arm_account_map_extends_fleet_arms_via_core_account_for_arm():
    """safe-3/risky-1 are NOT in the original ARM2ACCOUNT dict (a .get() miss there returns
    None, which would leave ribbon_tick_df structurally None) -- the extension must fall back
    to whole_engine_null._core_account_for_arm instead of silently returning None."""
    patched = wfpa._ArmAccountMap(pbc.ARM2ACCOUNT)
    assert "safe-3" not in pbc.ARM2ACCOUNT and "risky-1" not in pbc.ARM2ACCOUNT
    assert patched.get("safe-3") == wen._core_account_for_arm("safe-3") == "safe"
    assert patched.get("risky-1") == wen._core_account_for_arm("risky-1") == "safe"


def test_run_via_harness_validation_restores_monkeypatches_on_success(monkeypatch):
    orig_loader, orig_map = pbc.load_anchor_sample, pbc.ARM2ACCOUNT
    monkeypatch.setattr(pbc, "harness_validation",
                        lambda **kw: {"rows": [], "n": 0, "skipped_no_bars": 0})
    wfpa.run_via_harness_validation([{"symbol": "X"}], None)
    assert pbc.load_anchor_sample is orig_loader
    assert pbc.ARM2ACCOUNT is orig_map


def test_run_via_harness_validation_restores_monkeypatches_on_exception(monkeypatch):
    orig_loader, orig_map = pbc.load_anchor_sample, pbc.ARM2ACCOUNT

    def _boom(**kw):
        raise RuntimeError("simulated failure mid-walk")

    monkeypatch.setattr(pbc, "harness_validation", _boom)
    with pytest.raises(RuntimeError):
        wfpa.run_via_harness_validation([{"symbol": "X"}], None)
    assert pbc.load_anchor_sample is orig_loader, "must restore even when harness_validation raises"
    assert pbc.ARM2ACCOUNT is orig_map


def test_run_via_harness_validation_injects_rows_into_load_anchor_sample(monkeypatch):
    captured = {}

    def _fake_harness_validation(**kw):
        captured["rows_seen"] = pbc.load_anchor_sample()
        return {"rows": [], "n": 0, "skipped_no_bars": 0}

    monkeypatch.setattr(pbc, "harness_validation", _fake_harness_validation)
    sentinel = [{"symbol": "SENTINEL"}]
    wfpa.run_via_harness_validation(sentinel, None)
    assert captured["rows_seen"] == sentinel


# ------------------------------------------------------------------------------- table shape
def test_sign_agreement_pure():
    assert wfpa._sign_agreement([(10.0, 5.0), (-3.0, -1.0)]) == 1.0
    assert wfpa._sign_agreement([(10.0, -5.0)]) == 0.0
    assert wfpa._sign_agreement([]) is None


def _synthetic_hv_rows():
    return [
        {"arm": "safe-2", "actual": 10.0, "replay": 9.0, "recorded_stage": "premium_stop"},
        {"arm": "safe-2", "actual": -5.0, "replay": -4.0, "recorded_stage": "structure_stop"},
        {"arm": "bold-2", "actual": 20.0, "replay": 40.0, "recorded_stage": "premium_stop"},
        {"arm": "bold-2", "actual": -8.0, "replay": -1.0, "recorded_stage": "tp1+trail"},
    ]


def test_bucket_stats_shape():
    stats = wfpa._bucket_stats(_synthetic_hv_rows())
    assert set(stats) == {"n", "sign_agreement", "aggregate_ratio",
                          "median_abs_error_dollars", "verdict"}
    assert stats["n"] == 4
    assert stats["verdict"] == "INSUFFICIENT"  # n=4 < MAGNITUDE_FIDELITY_MIN_N=20


def test_bucket_stats_empty_is_insufficient():
    stats = wfpa._bucket_stats([])
    assert stats["n"] == 0
    assert stats["verdict"] == "INSUFFICIENT"


def test_per_arm_table_shape_and_grouping():
    table = wfpa.per_arm_table(_synthetic_hv_rows())
    assert set(table) == {"safe-2", "bold-2"}
    assert table["safe-2"]["n"] == 2
    assert table["bold-2"]["n"] == 2
    for stats in table.values():
        assert set(stats) == {"n", "sign_agreement", "aggregate_ratio",
                              "median_abs_error_dollars", "verdict"}


def test_per_stage_table_folds_rare_buckets():
    rows = _synthetic_hv_rows() + [
        {"arm": "safe-2", "actual": 1.0, "replay": 1.0, "recorded_stage": "ribbon_flip"},
    ]
    table = wfpa.per_stage_table(rows)
    # premium_stop has n=2 (>=3? no -- 2 < 3, so it folds into other_rare too); structure_stop
    # n=1, tp1+trail n=1, ribbon_flip n=1 -- ALL buckets here are <3, so everything folds into
    # one other_rare bucket covering every row.
    assert sum(s["n"] for s in table.values()) == len(rows)
    assert any(k.startswith("other_rare(") for k in table)


def test_per_stage_table_keeps_buckets_with_n_ge_3():
    rows = [
        {"arm": "safe-2", "actual": 10.0, "replay": 9.0, "recorded_stage": "premium_stop"},
        {"arm": "safe-2", "actual": 10.0, "replay": 9.0, "recorded_stage": "premium_stop"},
        {"arm": "safe-2", "actual": 10.0, "replay": 9.0, "recorded_stage": "premium_stop"},
        {"arm": "safe-2", "actual": 1.0, "replay": 1.0, "recorded_stage": "ribbon_flip"},
    ]
    table = wfpa.per_stage_table(rows)
    assert "premium_stop" in table and table["premium_stop"]["n"] == 3
    assert any(k.startswith("other_rare(") for k in table)


def test_skipped_summary_shape_and_counts():
    hv = {"rows": [{"date": "2026-07-08", "arm": "safe-2", "symbol": "A"}],
         "skipped_no_bars": 2}
    input_rows = [
        {"date": "2026-07-08", "arm": "safe-2", "symbol": "A"},
        {"date": "2026-07-08", "arm": "safe-2", "symbol": "B"},
    ]
    out = wfpa.skipped_summary(hv, input_rows)
    assert out["n_input_rows"] == 2
    assert out["n_priced_rows"] == 1
    assert out["n_unpriced_total"] == 1
    assert out["unpriced_rows_sample"] == [{"date": "2026-07-08", "arm": "safe-2", "symbol": "B"}]


def test_v9_continuity_line_handles_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(wfpa, "REPO", tmp_path)
    out = wfpa.v9_continuity_line()
    assert out["available"] is False
