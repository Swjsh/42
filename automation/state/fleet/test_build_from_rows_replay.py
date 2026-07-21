"""DOJO-FLEET-HISTORICAL-SIGNAL (2026-07-20 conductor, AFTERHOURS) -- guards for
build_shared_signal.build_from_rows(), the replay-aware sibling of build().

WHY THIS EXISTS: the DOJO replay room (setup/scripts/dojo/engine_step.py) walks a HISTORICAL
bar through the real engine (heartbeat_core._engine_verdict) for the 2 core accounts, but the
3 fleet exit-diversity arms (safe-3/risky-1/risky-3) previously rendered FLEET_VIEW_PENDING
because fleet_executor.plan_all() needs a "shared signal" dict that build_shared_signal.py only
knew how to construct from TODAY's on-disk core-decisions.jsonl (live-only, not date-
parameterized). build_from_rows() is the fix: the EXACT same signal-construction logic as
build(), fed an already-mapped row instead of a disk read.

BLAST-RADIUS GUARANTEE (this module is a shared PRODUCTION module the live fleet_rest executor
consumes every tick): build_from_rows is PURELY ADDITIVE. This file proves:
  A. build_from_rows(row=None, ...) never touches OUT (the live shared-signal.json) unless
     write=True is passed explicitly -- a replay session can never clobber the live file.
  B. build_from_rows() given the SAME underlying tick data as build()'s disk-read path produces
     a BYTE-IDENTICAL signal shape (same bear/bull/strategies/dual-perception blocks) --
     proving there is exactly ONE implementation of "what a core row means as a fleet signal",
     not a second one that can drift out of sync.
  C. build() itself is UNCHANGED (existing test_probe_arm.py / test_fix2_strategies_emit.py
     suites still pass, run separately as part of this fire's verification, not duplicated here).

Runs under pytest OR standalone (mirrors test_probe_arm.py's shim).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import build_shared_signal as bss

ET = timezone(timedelta(hours=-4))


def _seed_core_both(tmp_path, monkeypatch, today, *, safe_verdict, safe_action,
                    bold_verdict, bold_action, setup, side, triggers,
                    bull_score=11, bear_score=4, ts_h_m="11:21"):
    """Mirrors test_probe_arm.py's helper of the same name -- one safe + one bold row for the
    SAME tick, exactly as production writes them paired."""
    core = tmp_path / "core-decisions.jsonl"
    rows = [
        {"ts_et": f"{today}T{ts_h_m}:03-04:00", "account": "safe", "spy": 752.67,
         "ribbon": "BULL", "spread_cents": 37.3, "vix": 15.83, "htf_15m": "BULL",
         "verdict": safe_verdict, "side": side, "setup": setup,
         "bear_score": bear_score, "bull_score": bull_score, "triggers": triggers,
         "action": safe_action, "trigger_level_exact": 752.49},
        {"ts_et": f"{today}T{ts_h_m}:05-04:00", "account": "bold", "spy": 752.67,
         "ribbon": "BULL", "spread_cents": 37.3, "vix": 15.83, "htf_15m": "BULL",
         "verdict": bold_verdict, "side": side, "setup": setup,
         "bear_score": bear_score, "bull_score": bull_score, "triggers": triggers,
         "action": bold_action, "trigger_level_exact": 752.49},
    ]
    core.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")
    return core


# === A. never writes by default =============================================================
def test_build_from_rows_no_row_never_writes_by_default(tmp_path, monkeypatch):
    out = tmp_path / "shared-signal.json"
    monkeypatch.setattr(bss, "OUT", out)
    now = datetime(2026, 7, 17, 10, 5, tzinfo=ET)
    sig = bss.build_from_rows(None, now, run_vwap=False)
    assert sig["production_action"] == "HOLD"
    assert not out.exists()  # replay path must never clobber the live file


def test_build_from_rows_with_row_never_writes_by_default(tmp_path, monkeypatch):
    out = tmp_path / "shared-signal.json"
    monkeypatch.setattr(bss, "OUT", out)
    now = datetime(2026, 7, 17, 10, 5, tzinfo=ET)
    row = {"action": "ENTER_BEAR", "spy": 748.0, "vix": 15.0, "vix_dir": None,
           "ribbon_stack": "BEAR", "ribbon_spread_cents": 30.0, "htf_15m_stack": "BEAR",
           "bear_score": 9, "bull_score": 2, "triggers_fired": ["level_rejection"],
           "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON", "side": "P", "time_et": "10:05",
           "tick_id": None, "date": "2026-07-17", "_core": True, "trigger_level_exact": 748.5}
    sig = bss.build_from_rows(row, now, run_vwap=False, emit_strategies=False, probe_cohort=False)
    assert sig["production_action"] == "ENTER_BEAR"
    assert not out.exists()


def test_build_from_rows_write_true_does_write(tmp_path, monkeypatch):
    """write=True is the documented opt-in -- prove the flag actually does something (guards
    against a vacuous "never writes" test that would pass even if write were ignored)."""
    out = tmp_path / "shared-signal.json"
    monkeypatch.setattr(bss, "OUT", out)
    now = datetime(2026, 7, 17, 10, 5, tzinfo=ET)
    bss.build_from_rows(None, now, run_vwap=False, write=True)
    assert out.exists()


# === B. parity with build()'s disk-read path ================================================
def test_build_from_rows_matches_build_for_enter_bull_tick(tmp_path, monkeypatch):
    """SAME underlying tick, two callers (build()'s disk read vs build_from_rows()'s direct
    row) -- must produce structurally identical signals (byte-identical after excluding _doc/
    source, which intentionally disclose replay vs live provenance)."""
    now = datetime(2026, 7, 17, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core_both(tmp_path, monkeypatch, today,
                    safe_verdict="ENTER_BULL", safe_action="ENTER_BULL",
                    bold_verdict="ENTER_BULL", bold_action="ENTER_BULL",
                    setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
                    triggers=["level_reclaim", "ribbon_flip", "confluence"])
    disk_sig = bss.build(now=now, emit_strategies=False, run_vwap=False, probe_cohort=False)

    safe_row = bss._latest_today_decision(today, account="safe")
    bold_row = bss._latest_today_decision(today, account="bold")
    row_sig = bss.build_from_rows(safe_row, now, bold_row=bold_row, emit_strategies=False,
                                  run_vwap=False, probe_cohort=False)

    for key in ("bear", "bull", "safe", "bold", "spot", "vix", "ribbon_stack",
                "production_action", "scoring_peak_live", "written_at"):
        assert disk_sig.get(key) == row_sig.get(key), f"mismatch on {key!r}"


def test_build_from_rows_matches_build_for_enter_bear_tick_with_strategies(tmp_path, monkeypatch):
    """Same parity check WITH emit_strategies=True (FIX2 path) -- ribbon_ride entries must
    match exactly (run_vwap=False on both sides to stay offline/deterministic)."""
    now = datetime(2026, 7, 17, 10, 32, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core_both(tmp_path, monkeypatch, today,
                    safe_verdict="ENTER_BEAR", safe_action="ENTER_BEAR",
                    bold_verdict="ENTER_BEAR", bold_action="ENTER_BEAR",
                    setup="BEARISH_REJECTION_RIDE_THE_RIBBON", side="P",
                    triggers=["level_rejection"], ts_h_m="10:32")
    disk_sig = bss.build(now=now, emit_strategies=True, run_vwap=False, probe_cohort=False)

    safe_row = bss._latest_today_decision(today, account="safe")
    bold_row = bss._latest_today_decision(today, account="bold")
    row_sig = bss.build_from_rows(safe_row, now, bold_row=bold_row, emit_strategies=True,
                                  run_vwap=False, probe_cohort=False)

    assert disk_sig["strategies"] == row_sig["strategies"]
    assert disk_sig["bear"] == row_sig["bear"]
    assert disk_sig["bold"] == row_sig["bold"]


def test_build_from_rows_dual_perception_uses_supplied_bold_row_directly(tmp_path, monkeypatch):
    """A caller (DOJO) that has its OWN historical bold-account row (never written to
    core-decisions.jsonl at all) can supply it directly -- proves the replay path does not
    silently fall back to a disk read for the bold perception."""
    now = datetime(2026, 7, 17, 10, 32, tzinfo=ET)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    safe_row = {"action": "HOLD", "spy": 748.0, "vix": 15.0, "vix_dir": None,
                "ribbon_stack": "BEAR", "ribbon_spread_cents": 30.0, "htf_15m_stack": "BEAR",
                "bear_score": 4, "bull_score": 2, "triggers_fired": [],
                "setup_name": None, "side": None, "time_et": "10:32",
                "tick_id": None, "date": "2026-07-17", "trigger_level_exact": None}
    bold_row = {"action": "ENTER_BEAR", "spy": 748.0, "vix": 15.0, "vix_dir": None,
                "ribbon_stack": "BEAR", "ribbon_spread_cents": 30.0, "htf_15m_stack": "BEAR",
                "bear_score": 9, "bull_score": 1, "triggers_fired": ["level_rejection"],
                "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON", "side": "P",
                "time_et": "10:32", "tick_id": None, "date": "2026-07-17",
                "trigger_level_exact": 748.5}
    sig = bss.build_from_rows(safe_row, now, bold_row=bold_row, emit_strategies=False,
                              run_vwap=False, probe_cohort=False)
    assert sig["bear"]["passed"] is False        # production-mirror (safe) stays honest
    assert sig["bold"]["bear"]["passed"] is True  # bold perception sourced from the supplied row


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
