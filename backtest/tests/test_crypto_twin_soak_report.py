"""Tests for setup/scripts/crypto_twin_soak_report.py -- the T4 (Sunday) soak-summary
reader. Pure-function tests against summarize()/format_report() (no real files needed
for the core logic) plus a read-only integration check against the module's own
_read_jsonl fail-open behavior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import crypto_twin_soak_report as csr  # noqa: E402


# ============================================================================
# summarize() -- pure
# ============================================================================
def test_summarize_empty_inputs_never_crashes():
    summary = csr.summarize([], [])
    assert summary["n_ticks_total"] == 0
    assert summary["n_errors_total"] == 0
    assert summary["first_tick_et"] is None
    assert summary["last_tick_et"] is None
    assert summary["uptime_pct_estimate"] is None
    assert summary["action_distribution"] == {}
    assert summary["recent_errors"] == []


def test_summarize_counts_actions_and_errors():
    rows = [
        {"ts_et": "2026-07-10T20:00:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:05:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:10:00", "action": "MANAGED"},
        {"ts_et": "2026-07-10T20:15:00", "action": "TICK_ERROR", "reason": "network blip"},
    ]
    summary = csr.summarize([], rows)
    assert summary["n_ticks_total"] == 4
    assert summary["n_errors_total"] == 1
    assert summary["action_distribution"] == {"HOLD": 2, "MANAGED": 1, "TICK_ERROR": 1}
    assert summary["first_tick_et"] == "2026-07-10T20:00:00"
    assert summary["last_tick_et"] == "2026-07-10T20:15:00"
    assert summary["recent_errors"] == [{"ts_et": "2026-07-10T20:15:00", "reason": "network blip"}]


def test_summarize_uptime_estimate_full_coverage():
    """12 ticks over exactly 55 minutes at 5-min cadence (ticks at :00,:05,...,:55)
    -- 12 observed vs 11 expected (55/5) intervals -> capped at 100%."""
    rows = [{"ts_et": f"2026-07-10T20:{m:02d}:00", "action": "HOLD"} for m in range(0, 60, 5)]
    summary = csr.summarize([], rows)
    assert summary["uptime_pct_estimate"] == 100.0


def test_summarize_uptime_estimate_detects_gaps():
    """Only 2 ticks spanning 60 minutes at a 5-min cadence -- expected ~12 ticks,
    observed 2 -> a low uptime estimate, not silently 100%."""
    rows = [
        {"ts_et": "2026-07-10T20:00:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T21:00:00", "action": "HOLD"},
    ]
    summary = csr.summarize([], rows)
    assert summary["uptime_pct_estimate"] is not None
    assert summary["uptime_pct_estimate"] < 50.0


def test_summarize_single_tick_uptime_is_none():
    rows = [{"ts_et": "2026-07-10T20:00:00", "action": "HOLD"}]
    summary = csr.summarize([], rows)
    assert summary["uptime_pct_estimate"] is None


def test_summarize_recent_errors_capped_at_five():
    rows = [{"ts_et": f"2026-07-10T20:{i:02d}:00", "action": "TICK_ERROR", "reason": f"err{i}"}
           for i in range(8)]
    summary = csr.summarize([], rows)
    assert len(summary["recent_errors"]) == 5
    assert summary["recent_errors"][-1]["reason"] == "err7"  # most recent 5, in order


def test_summarize_reports_soak_row_count_separately():
    soak_rows = [{"period_start_et": "a"}, {"period_start_et": "b"}]
    summary = csr.summarize(soak_rows, [])
    assert summary["n_soak_rows"] == 2


# ============================================================================
# format_report() -- pure string rendering, never raises on edge inputs
# ============================================================================
def test_format_report_handles_empty_summary():
    summary = csr.summarize([], [])
    text = csr.format_report(summary)
    assert "Crypto Twin Soak Report" in text
    assert "Ticks logged:        0" in text
    assert "n/a" in text  # first/last tick + uptime all n/a


def test_format_report_includes_action_distribution_sorted_desc():
    rows = [
        {"ts_et": "2026-07-10T20:00:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:05:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:10:00", "action": "MANAGED"},
    ]
    text = csr.format_report(csr.summarize([], rows))
    hold_idx = text.index("HOLD")
    managed_idx = text.index("MANAGED")
    assert hold_idx < managed_idx  # HOLD (count=2) listed before MANAGED (count=1)


def test_format_report_includes_recent_errors_section_only_when_present():
    clean_text = csr.format_report(csr.summarize([], [{"ts_et": "t", "action": "HOLD"}]))
    assert "Recent errors" not in clean_text

    error_rows = [{"ts_et": "2026-07-10T20:00:00", "action": "TICK_ERROR", "reason": "boom"}]
    error_text = csr.format_report(csr.summarize([], error_rows))
    assert "Recent errors" in error_text
    assert "boom" in error_text


# ============================================================================
# _read_jsonl -- fail-open reader
# ============================================================================
def test_read_jsonl_missing_file_returns_empty(tmp_path):
    assert csr._read_jsonl(tmp_path / "nope.jsonl") == []


def test_read_jsonl_skips_malformed_lines(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"a": 2}\n', encoding="utf-8")
    rows = csr._read_jsonl(p)
    assert rows == [{"a": 1}, {"a": 2}]


# ============================================================================
# Integration: main() runs clean against a real (empty) state dir -- never crashes
# ============================================================================
def test_main_runs_clean_when_state_files_absent(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(csr, "SOAK_LOG_PATH", tmp_path / "soak-log.jsonl")
    monkeypatch.setattr(csr, "DECISIONS_PATH", tmp_path / "decisions.jsonl")
    rc = csr.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Crypto Twin Soak Report" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
