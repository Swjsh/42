"""Guard: spend_summary.py's recalibrated threshold + transition-only alerting.

THE BUG (SPEND-SUMMARY-CHRONIC-RED-ALERT-FATIGUE, queue.md, filed 2026-08-19,
fixed 2026-09-03): the nightly Discord "SPEND WARN" ping fired every single day
for at least 20 real-session days (2026-08-10..2026-09-02, spot-checked in
automation/state/spend-daily.jsonl -- low $43.15, high $2,697.10) against a
hardcoded --warn-threshold 30 that was never revisited after the Max plan moved
from $100/mo flat to $200/mo 20x (2026-06-24). An alert that has never once gone
green carries zero discriminating signal (same "alarm that cannot clear" class
as the 2026-08-17 check_llm_auth_outage fix).

THE FIX has two independent parts, both pinned here:
  1. _derive_warn_threshold: the WARN threshold is now the 75th percentile of
     the trailing WARN_WINDOW_DAYS days' totals STRICTLY BEFORE today (today
     can never raise its own bar), floored at WARN_FLOOR, falling back to the
     floor outright when fewer than WARN_MIN_HISTORY_DAYS prior days exist.
  2. _run_daily_alert: alerts (Discord ping + STATUS.md marker) fire only on a
     genuine breach-state TRANSITION since the last real run (not-breached ->
     breached = one WARN; breached -> not-breached = one CLEAR; unchanged =
     SILENT), tracked via automation/state/spend-summary-alert-state.json.

Tests operate exclusively on tmp paths (monkeypatched module globals) -- never
the live automation/state/ files.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "spend_summary.py"

_spec = importlib.util.spec_from_file_location("spend_summary_alerting", MOD_PATH)
ss = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ss
_spec.loader.exec_module(ss)


def _make_report(total_claude: float, date_et: str = "2026-09-03") -> "ss.DayReport":
    report = ss.DayReport(date_et=date_et)
    report.claude_sessions = 1
    agg = ss.TokenAgg()
    agg.input_tokens = int(total_claude / 3.0 * 1_000_000) if total_claude else 0
    report.claude_by_tier["sonnet"] = agg
    return report


def _row(date_et: str, total: float) -> dict:
    return {"date_et": date_et, "total_cost_usd": total}


# ---------------------------------------------------------------------------
# _derive_warn_threshold -- threshold derivation from a fixture series
# ---------------------------------------------------------------------------

def test_derive_threshold_falls_back_to_floor_with_thin_history():
    """Fewer than WARN_MIN_HISTORY_DAYS prior rows -> can't derive a percentile
    reliably, so the floor wins outright."""
    rows = [_row("2026-09-01", 900.0), _row("2026-09-02", 950.0)]
    th = ss._derive_warn_threshold(rows, "2026-09-03", floor=50.0, min_days=5)
    assert th == 50.0


def test_derive_threshold_p75_from_fixture_series():
    """A known 8-point series (p75 via linear interpolation, numpy-default method)
    must reproduce the textbook value exactly."""
    dates = [f"2026-08-{d:02d}" for d in range(10, 18)]  # 8 prior days
    totals = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]
    rows = [_row(d, t) for d, t in zip(dates, totals)]
    # n=8, p75 index = 0.75*(8-1) = 5.25 -> interpolate between totals[5]=600 and totals[6]=700
    expected = 600.0 + 0.25 * (700.0 - 600.0)
    th = ss._derive_warn_threshold(rows, "2026-08-18", floor=50.0, min_days=5, window_days=30)
    assert th == round(expected, 2)


def test_derive_threshold_floor_wins_when_percentile_is_low():
    """A genuinely quiet history (all near-zero days) must not collapse the
    threshold near zero -- the floor is a hard lower bound."""
    dates = [f"2026-08-{d:02d}" for d in range(10, 20)]
    rows = [_row(d, 1.0) for d in dates]
    th = ss._derive_warn_threshold(rows, "2026-08-20", floor=50.0, min_days=5)
    assert th == 50.0


def test_derive_threshold_excludes_target_date_itself():
    """A huge value ON the target date must never raise its own bar -- only
    STRICTLY PRIOR days count. Proven by exact equality on a SMALL window (n=3,
    min_days=3) where a spliced-in target-date outlier would materially move
    a 75th-percentile computed over only 4 points if it were wrongly included
    (a `<=` off-by-one that includes target_date would move th_with far above
    th_without; this fixture is deliberately small so that shift can't hide in
    percentile-interpolation noise the way it would with a large/diluted window)."""
    dates = ["2026-08-17", "2026-08-18", "2026-08-19"]
    rows_without_today = [_row(d, 100.0) for d in dates]
    th_without = ss._derive_warn_threshold(rows_without_today, "2026-08-20", floor=50.0, min_days=3)
    assert th_without == 100.0

    rows_with_today = rows_without_today + [_row("2026-08-20", 999_999.0)]
    th_with = ss._derive_warn_threshold(rows_with_today, "2026-08-20", floor=50.0, min_days=3)

    assert th_with == th_without, "today's own row must not affect its own threshold at all"


def test_derive_threshold_respects_window_days():
    """Only the trailing `window_days` prior rows count -- older history outside
    the window must not pull the percentile down (or up)."""
    # 40 days of $10 far in the past, then 10 recent days of $1000 -- with a
    # window of 10, only the recent high days should be visible.
    old_dates = [f"2026-06-{d:02d}" for d in range(1, 31)]
    recent_dates = [f"2026-08-{d:02d}" for d in range(1, 11)]
    rows = [_row(d, 10.0) for d in old_dates] + [_row(d, 1000.0) for d in recent_dates]
    th = ss._derive_warn_threshold(rows, "2026-08-11", floor=50.0, min_days=5, window_days=10)
    assert th == 1000.0, "window_days=10 must see only the 10 recent $1000 rows"


# ---------------------------------------------------------------------------
# _run_daily_alert -- transition-only alerting (up / steady / down)
# ---------------------------------------------------------------------------

def _patch_paths(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n", encoding="utf-8")
    outbox = state_dir / "discord-outbox.jsonl"
    alert_state = state_dir / "spend-summary-alert-state.json"
    monkeypatch.setattr(ss, "STATE_DIR", state_dir)
    monkeypatch.setattr(ss, "STATUS_FILE", status)
    monkeypatch.setattr(ss, "DISCORD_OUTBOX", outbox)
    monkeypatch.setattr(ss, "ALERT_STATE_FILE", alert_state)
    return status, outbox, alert_state


def _read_outbox(outbox: Path) -> list:
    if not outbox.exists():
        return []
    return [json.loads(l) for l in outbox.read_text(encoding="utf-8").strip().splitlines() if l.strip()]


def test_transition_up_sends_one_warn(tmp_path, monkeypatch):
    """not-breached -> breached: exactly one WARN Discord ping + STATUS.md marker."""
    status, outbox, _ = _patch_paths(tmp_path, monkeypatch)
    report = _make_report(500.0)
    result = ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert result["action"] == "warn"
    rows = _read_outbox(outbox)
    assert len(rows) == 1
    assert "SPEND WARN" in rows[0]["message"]
    body = status.read_text(encoding="utf-8")
    assert "SPEND_WARN" in body


def test_transition_steady_breached_stays_silent(tmp_path, monkeypatch):
    """breached -> still breached (no state change): SILENT, no repeat ping."""
    status, outbox, alert_state = _patch_paths(tmp_path, monkeypatch)
    alert_state.write_text(json.dumps({"date_et": "2026-09-02", "breached": True,
                                        "threshold_usd": 100.0, "total_usd": 400.0}),
                            encoding="utf-8")
    # Seed STATUS.md as if yesterday's WARN already landed.
    report_yday = _make_report(400.0, date_et="2026-09-02")
    ss._append_status_warn(report_yday, 100.0)

    report = _make_report(500.0)
    result = ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert result["action"] == "silent"
    assert _read_outbox(outbox) == [], "no ping when breach state is unchanged"
    # STATUS.md marker still present (untouched, not re-written or duplicated).
    body = status.read_text(encoding="utf-8")
    assert body.count("SPEND_WARN") == 1


def test_transition_down_sends_one_clear(tmp_path, monkeypatch):
    """breached -> not-breached: exactly one CLEAR Discord ping + STATUS.md marker cleared."""
    status, outbox, alert_state = _patch_paths(tmp_path, monkeypatch)
    alert_state.write_text(json.dumps({"date_et": "2026-09-02", "breached": True,
                                        "threshold_usd": 100.0, "total_usd": 400.0}),
                            encoding="utf-8")
    report_yday = _make_report(400.0, date_et="2026-09-02")
    ss._append_status_warn(report_yday, 100.0)
    assert "SPEND_WARN" in status.read_text(encoding="utf-8")

    report = _make_report(10.0)  # today is back under threshold
    result = ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert result["action"] == "clear"
    rows = _read_outbox(outbox)
    assert len(rows) == 1
    assert "SPEND CLEAR" in rows[0]["message"]
    body = status.read_text(encoding="utf-8")
    assert "SPEND_WARN" not in body, "marker must be cleared, not left stale"


def test_transition_steady_not_breached_stays_silent(tmp_path, monkeypatch):
    """not-breached -> still not-breached: SILENT (the common/normal-day case)."""
    _, outbox, alert_state = _patch_paths(tmp_path, monkeypatch)
    alert_state.write_text(json.dumps({"date_et": "2026-09-02", "breached": False,
                                        "threshold_usd": 100.0, "total_usd": 10.0}),
                            encoding="utf-8")
    report = _make_report(20.0)
    result = ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert result["action"] == "silent"
    assert _read_outbox(outbox) == []


def test_first_ever_run_breached_sends_warn_not_treated_as_steady(tmp_path, monkeypatch):
    """No prior alert-state file at all (first run ever): missing state reads as
    'not previously breached', so a breach on day 1 still sends exactly one WARN
    -- it must not be silently swallowed as if it were a repeat."""
    _, outbox, alert_state = _patch_paths(tmp_path, monkeypatch)
    assert not alert_state.exists()
    report = _make_report(500.0)
    result = ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert result["action"] == "warn"
    assert len(_read_outbox(outbox)) == 1


def test_alert_state_persisted_every_real_run(tmp_path, monkeypatch):
    """Even a SILENT run must persist today's breach state, or the next run has
    nothing correct to compare against."""
    _, _, alert_state = _patch_paths(tmp_path, monkeypatch)
    report = _make_report(500.0)
    ss._run_daily_alert(report, "2026-09-03", forced_threshold=100.0)
    assert alert_state.exists()
    saved = json.loads(alert_state.read_text(encoding="utf-8"))
    assert saved["date_et"] == "2026-09-03"
    assert saved["breached"] is True
    assert saved["threshold_usd"] == 100.0


# ---------------------------------------------------------------------------
# Dry-run (--check-only) never writes the outbox or alert-state
# ---------------------------------------------------------------------------

def test_check_only_never_touches_outbox_or_alert_state(tmp_path, monkeypatch):
    """main()'s --check-only path must never call _run_daily_alert at all --
    verified here by confirming the persistence files that ONLY _run_daily_alert
    (or its callees) can create stay absent after a full check-only main() run
    against an isolated, empty Claude-session directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n", encoding="utf-8")
    empty_cc_dir = tmp_path / "cc-sessions"
    empty_cc_dir.mkdir()
    minimax = state_dir / "minimax-calls.jsonl"
    swarm = state_dir / "swarm-calls.jsonl"
    history = state_dir / "spend-daily.jsonl"
    outbox = state_dir / "discord-outbox.jsonl"
    alert_state = state_dir / "spend-summary-alert-state.json"

    monkeypatch.setattr(ss, "STATE_DIR", state_dir)
    monkeypatch.setattr(ss, "STATUS_FILE", status)
    monkeypatch.setattr(ss, "CC_PROJECT_DIR", empty_cc_dir)
    monkeypatch.setattr(ss, "MINIMAX_TELEMETRY", minimax)
    monkeypatch.setattr(ss, "SWARM_CALLS_TELEMETRY", swarm)
    monkeypatch.setattr(ss, "SPEND_DAILY_HISTORY", history)
    monkeypatch.setattr(ss, "DISCORD_OUTBOX", outbox)
    monkeypatch.setattr(ss, "ALERT_STATE_FILE", alert_state)
    monkeypatch.setattr(sys, "argv", ["spend_summary.py", "--check-only", "--date", "2026-09-03"])

    rc = ss.main()
    assert rc == 0
    assert not outbox.exists()
    assert not alert_state.exists()
    assert not history.exists()
    assert not (state_dir / "spend-2026-09-03.json").exists()
