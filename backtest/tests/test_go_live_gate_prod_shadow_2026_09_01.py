"""Guard: go_live_gate.py criterion 5 (PROD-SHADOW) is WIRED (TASK W5, 2026-09-01) --
previously this always returned status=NOT_WIRED regardless of any data. Also guards the
BEHAVIOURAL criterion's honesty fix: a stale rule-breaks.jsonl (zero writes for longer than
the trailing window) must report PASS_UNVERIFIED, not a bare PASS, when 0 breaks are found
in-window.

Covers exactly the 4 areas named in the task brief:
  1. config present/missing        -> NOT_WIRED when automation/state/prod-shadow-
                                       designation.json is absent or unreadable.
  2. insufficient days              -> INSUFFICIENT_DAYS when the designated window hasn't
                                       scored min_days yet.
  3. window restriction             -> rows outside [window_start, window_end] or for a
                                       different arm never count toward days_scored or the
                                       bootstrap.
  4. PASS_UNVERIFIED path           -> behavioural_criterion's rule-breaks sub-check.

RED-proof evidence (quoted in the session report, not re-executed here): prod_shadow_
criterion() was temporarily forced to always return status="NOT_WIRED" (short-circuiting
_load_prod_shadow_designation's result) -- test_designation_present_but_insufficient_days,
test_window_restriction_excludes_out_of_window_rows, and
test_designation_pass_when_history_is_clean_and_positive all failed with the expected
AssertionError (status was "NOT_WIRED", not "INSUFFICIENT_DAYS"/"PASS"), then passed again
after the revert.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import go_live_gate as glg  # noqa: E402


def _row(arm, date, pnl, qty=3.0, exit_px=1.0, attribution="engine"):
    return {
        "arm": arm, "date": date, "pnl_dollars": pnl, "attribution": attribution,
        "qty": qty, "exit_px_avg": exit_px, "symbol": "SPY000000C00000000",
    }


def _write_designation(tmp_path, **overrides):
    cfg = {
        "arm": "safe-3",
        "profile_summary": "test fixture",
        "window_start": "2026-09-01",
        "window_end": "2026-09-29",
        "min_days": 20,
        "designated_at": "2026-09-01T00:00:00-04:00",
        "rationale": "test fixture",
        "revoke": "delete this file",
    }
    cfg.update(overrides)
    p = tmp_path / "prod-shadow-designation.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


# --------------------------------------------------------------------------------------- #
# 1. config present / missing
# --------------------------------------------------------------------------------------- #
def test_missing_config_reports_not_wired(tmp_path, monkeypatch):
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", tmp_path / "does-not-exist.json")
    result = glg.prod_shadow_criterion([])
    assert result["status"] == "NOT_WIRED"
    assert result["pass"] is False
    assert "recommendation" in result


def test_unreadable_config_reports_not_wired(tmp_path, monkeypatch):
    bad = tmp_path / "prod-shadow-designation.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", bad)
    result = glg.prod_shadow_criterion([])
    assert result["status"] == "NOT_WIRED"


def test_config_missing_required_field_reports_not_wired(tmp_path, monkeypatch):
    p = tmp_path / "prod-shadow-designation.json"
    p.write_text(json.dumps({"arm": "safe-3", "window_start": "2026-09-01"}), encoding="utf-8")
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    result = glg.prod_shadow_criterion([])
    assert result["status"] == "NOT_WIRED"


# --------------------------------------------------------------------------------------- #
# 2. insufficient days
# --------------------------------------------------------------------------------------- #
def test_designation_present_but_insufficient_days(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, min_days=20)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    rows = [_row("safe-3", f"2026-09-{d:02d}", 50.0) for d in range(1, 6)]  # 5 days only
    result = glg.prod_shadow_criterion(rows)
    assert result["status"] == "INSUFFICIENT_DAYS"
    assert result["pass"] is False
    assert result["days_scored"] == 5
    assert result["days_needed"] == 20


def test_zero_days_in_window_is_insufficient_not_a_crash(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, min_days=20)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    result = glg.prod_shadow_criterion([])
    assert result["status"] == "INSUFFICIENT_DAYS"
    assert result["days_scored"] == 0
    assert result["current_ci_lower_2.5"] is None


# --------------------------------------------------------------------------------------- #
# 3. window restriction
# --------------------------------------------------------------------------------------- #
def test_window_restriction_excludes_out_of_window_rows(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, window_start="2026-09-01", window_end="2026-09-05", min_days=2)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    rows = [
        _row("safe-3", "2026-08-15", 9999.0),   # before window -- must be excluded
        _row("safe-3", "2026-09-01", 100.0),    # in window (win)
        _row("safe-3", "2026-09-02", -20.0),    # in window (loss, keeps PF finite)
        _row("safe-3", "2026-09-10", -9999.0),  # after window -- must be excluded
        _row("risky-1", "2026-09-01", 5000.0),  # right arm-window, wrong ARM -- must be excluded
    ]
    result = glg.prod_shadow_criterion(rows)
    assert result["days_scored"] == 2, "only the 2 in-window safe-3 days should count"
    # if the out-of-window rows leaked in, the PF would be wildly different (9999 gain or
    # -9999 loss dominates); as-traded total must equal exactly the 2 in-window days' sum.
    assert result["detail"]["as_traded"]["total_pnl"] == 80.0


def test_window_restriction_min_days_uses_only_in_window_count(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, window_start="2026-09-01", window_end="2026-09-03", min_days=5)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    # 10 days of history exist for the arm, but only 3 fall inside the tiny window above.
    rows = [_row("safe-3", f"2026-08-{20+d:02d}", 10.0) for d in range(10)]
    rows += [_row("safe-3", f"2026-09-0{d}", 10.0) for d in range(1, 4)]
    result = glg.prod_shadow_criterion(rows)
    assert result["status"] == "INSUFFICIENT_DAYS"
    assert result["days_scored"] == 3


# --------------------------------------------------------------------------------------- #
# PASS / FAIL scoring once min_days is met (reuses statistical_criterion -- sanity, not a
# re-test of that function's own math, which is covered by its existing suite).
# --------------------------------------------------------------------------------------- #
def test_designation_pass_when_history_is_clean_and_positive(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, window_start="2026-09-01", window_end="2026-09-30", min_days=20)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    rows = [_row("safe-3", f"2026-09-{d:02d}", 100.0) for d in range(1, 24)]  # 23 all-winner days
    rows.append(_row("safe-3", "2026-09-24", -5.0))
    result = glg.prod_shadow_criterion(rows)
    assert result["days_scored"] == 24
    assert result["status"] == "PASS"
    assert result["pass"] is True
    assert result["current_ci_lower_2.5"] is not None


def test_designation_fail_when_history_is_breakeven(tmp_path, monkeypatch):
    p = _write_designation(tmp_path, window_start="2026-09-01", window_end="2026-09-30", min_days=20)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    rows = []
    for d in range(1, 26):
        pnl = 55.0 if d % 2 == 0 else -60.0
        rows.append(_row("safe-3", f"2026-09-{d:02d}", pnl))
    result = glg.prod_shadow_criterion(rows)
    assert result["days_scored"] == 25
    assert result["status"] == "FAIL"
    assert result["pass"] is False


def test_extended_clock_disclosure_never_overrides_the_pass_bar(tmp_path, monkeypatch):
    """A window that PASSES on the short (09-29) horizon must not be swapped out for the
    extended (10-30) horizon's own number anywhere in the top-level pass/status fields --
    the extended clock is disclosure only."""
    p = _write_designation(tmp_path, window_start="2026-09-01", window_end="2026-09-30",
                            min_days=20, extended_clock_end="2026-10-30", extended_clock_min_days=40)
    monkeypatch.setattr(glg, "PROD_SHADOW_DESIGNATION_PATH", p)
    rows = [_row("safe-3", f"2026-09-{d:02d}", 100.0) for d in range(1, 24)]  # 23 winners
    rows.append(_row("safe-3", "2026-09-24", -5.0))  # 1 loser, keeps PF finite
    result = glg.prod_shadow_criterion(rows)
    assert result["status"] == "PASS"
    ext = result["extended_clock_disclosure"]
    assert ext["days_scored"] == 24  # same rows, extended window just hasn't hit its OWN 40-day bar
    assert ext["min_days"] == 40
    # the extended block carries its own detail but never writes into result["status"]/"pass"
    assert result["status"] == "PASS"


# --------------------------------------------------------------------------------------- #
# 4. PASS_UNVERIFIED path (behavioural_criterion, rule-breaks staleness)
# --------------------------------------------------------------------------------------- #
def _engine_rows_for_window(n_days=20, start_day=1):
    return [_row("safe-3", f"2026-08-{start_day + i:02d}", 10.0) for i in range(n_days)]


def test_behavioural_rule_breaks_pass_unverified_when_ledger_stale(tmp_path, monkeypatch):
    rb_path = tmp_path / "rule-breaks.jsonl"
    rb_path.write_text(
        '{"date":"2026-05-18","rule_id":"X","severity":"low"}\n', encoding="utf-8"
    )
    # mtime far BEFORE the engine rows' trailing window (2026-08-01..08-20)
    old_ts = 1747526400  # 2025-05-18 UTC-ish; well before any window used below
    os.utime(rb_path, (old_ts, old_ts))
    monkeypatch.setattr(glg, "RULE_BREAKS_PATH", rb_path)

    rows = _engine_rows_for_window(n_days=20, start_day=1)
    result = glg.behavioural_criterion(rows, recon={"per_arm": {}})
    rb = result["rule_breaks_in_window"]
    assert rb["count"] == 0
    assert rb["status"] == "PASS_UNVERIFIED"
    assert rb["status_note"] is not None
    # overall behavioural verdict logic is UNCHANGED by the staleness disclosure
    assert result["pass"] is True


def test_behavioural_rule_breaks_pass_when_ledger_fresh(tmp_path, monkeypatch):
    rb_path = tmp_path / "rule-breaks.jsonl"
    rb_path.write_text("", encoding="utf-8")  # no rows, but freshly written
    import time
    now_ts = time.time()
    os.utime(rb_path, (now_ts, now_ts))
    monkeypatch.setattr(glg, "RULE_BREAKS_PATH", rb_path)

    rows = _engine_rows_for_window(n_days=20, start_day=1)
    result = glg.behavioural_criterion(rows, recon={"per_arm": {}})
    rb = result["rule_breaks_in_window"]
    assert rb["count"] == 0
    assert rb["status"] == "PASS"
    assert rb["status_note"] is None
    assert result["pass"] is True


def test_behavioural_rule_breaks_fail_status_when_breaks_present(tmp_path, monkeypatch):
    rb_path = tmp_path / "rule-breaks.jsonl"
    # a real break dated inside the engine rows' trailing window (2026-08-01..08-20)
    rb_path.write_text(
        '{"date":"2026-08-10","rule_id":"RULE_5_KILL_SWITCH","severity":"high"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(glg, "RULE_BREAKS_PATH", rb_path)

    rows = _engine_rows_for_window(n_days=20, start_day=1)
    result = glg.behavioural_criterion(rows, recon={"per_arm": {}})
    rb = result["rule_breaks_in_window"]
    assert rb["count"] == 1
    assert rb["status"] == "FAIL"
    assert result["pass"] is False
