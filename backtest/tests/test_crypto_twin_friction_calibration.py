"""Tests for setup/scripts/crypto_twin_friction_calibration.py (TWIN-B6).

Pure-function tests against synthetic entry-quality/journal fixtures -- no real state file
I/O except through the module's own read helpers (fail-open on missing files), and no
mutation of the real automation/state/crypto-twin/ ledger.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO))

import crypto_twin_friction_calibration as cal  # noqa: E402


def test_backtest_assumptions_import_resolves_real_values():
    """The whole point of this calibration is to diff empirical friction against the LIVE
    backtest constants -- if the import silently fails, every comparison is a lie (None vs
    a number always looks "different"). Guards against the backtest/lib relative-import
    footgun this script's own module docstring documents."""
    a = cal.backtest_assumptions()
    assert a["DEFAULT_ENTRY_SLIPPAGE"] == 0.02
    assert a["DEFAULT_EXIT_SLIPPAGE"] == 0.02


def test_entry_friction_sign_convention_matches_backtest_slippage():
    """entry-quality.json's improvement_bps is POSITIVE when the fill beat baseline_ask.
    slippage_bps must be the mirror sign (positive = cost), matching simulator_real.py's
    entry_slippage (added as a COST to the entry fill)."""
    entry_quality = {"cohorts": {"marketable": {"fills": 10, "fill_rate": 1.0,
                                                "avg_improvement_bps": 2.5,
                                                "avg_time_to_fill_sec": 0.3},
                                 "passive": {}}}
    out = cal.entry_friction(entry_quality)
    assert out["marketable_market_order"]["avg_slippage_bps"] == -2.5
    assert out["passive_resting_limit_no_spy_analog"] is None


def test_entry_friction_handles_empty_cohorts():
    assert cal.entry_friction({}) == {"marketable_market_order": None,
                                      "passive_resting_limit_no_spy_analog": None}


def test_exit_friction_groups_by_stage_and_flips_sign():
    journal_rows = [
        {"event": "EXIT_FILLED", "reason": "structure_stop @ 100.0", "slippage_bps": -5.0,
         "time_to_fill_sec": 0.3},
        {"event": "EXIT_FILLED", "reason": "structure_stop @ 200.0", "slippage_bps": -3.0,
         "time_to_fill_sec": 0.4},
        {"event": "EXIT_FILLED", "reason": "runner_stop @ 150.0 (runner)", "slippage_bps": 2.0,
         "time_to_fill_sec": 0.2},
        # no embedded price -> expected_price None -> slippage_bps None -> excluded
        {"event": "EXIT_FILLED", "reason": "max_hold_flatten", "slippage_bps": None,
         "time_to_fill_sec": 0.25},
        {"event": "PLACED"},  # non-EXIT_FILLED row, ignored
    ]
    out = cal.exit_friction(journal_rows)
    assert out["n_exit_fills_captured"] == 3
    assert out["all_market_orders"] is True
    assert set(out["by_stage_slippage_bps"].keys()) == {"structure_stop", "runner_stop"}
    # sign-flipped: -(-5.0)=5.0, -(-3.0)=3.0 -> avg 4.0
    assert out["by_stage_slippage_bps"]["structure_stop"]["avg"] == 4.0
    assert out["by_stage_slippage_bps"]["structure_stop"]["n"] == 2
    assert out["by_stage_slippage_bps"]["runner_stop"]["avg"] == -2.0
    assert out["latency_sec"]["n"] == 3


def test_exit_friction_counts_capture_errors_separately():
    journal_rows = [{"event": "EXIT_FILLED_CAPTURE_ERROR"}, {"event": "EXIT_FILLED_CAPTURE_ERROR"}]
    out = cal.exit_friction(journal_rows)
    assert out["n_exit_fills_captured"] == 0
    assert out["n_capture_errors"] == 2


def test_build_report_accruing_verdict_when_zero_exit_fills(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "ENTRY_QUALITY_PATH", tmp_path / "entry-quality.json")
    monkeypatch.setattr(cal, "JOURNAL_PATH", tmp_path / "journal.jsonl")  # missing -> []
    report = cal.build_report()
    assert report["exit_friction"]["n_exit_fills_captured"] == 0
    assert "ACCRUING" in report["verdict"]
    assert report["doctrine"].startswith("TWIN-B6")


def test_build_report_reports_count_once_exit_fills_accrue(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "ENTRY_QUALITY_PATH", tmp_path / "entry-quality.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text(
        '{"event": "EXIT_FILLED", "reason": "structure_stop @ 100.0", "slippage_bps": -5.0, '
        '"time_to_fill_sec": 0.3}\n', encoding="utf-8")
    monkeypatch.setattr(cal, "JOURNAL_PATH", journal_path)
    report = cal.build_report()
    assert report["exit_friction"]["n_exit_fills_captured"] == 1
    assert "1 exit fills captured" in report["verdict"]
