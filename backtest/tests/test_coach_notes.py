"""Guard: setup/scripts/coach_notes.py -- Coach's dollar-ranked coaching notes
(CREW-RIG R2, GOAL-GAMMA-STATION-2026-09-13, 2026-09-14 build). J's verdict that
started this build: "why would Coach be WAITING? There should be a plethora of things
for Coach to coach the crypto on, or paper trading."

Locks in: the bounded tail-read of journal.jsonl (never a whole-file read -- the real
file is 24.5MB+ and growing; automation/state/crypto-twin/decisions.jsonl, 146MB, is
never opened at all by this module), realized-P&L aggregation (wins/losses/net/avg/
worst) on synthetic EXIT_FILLED rows, the last-5-session paper-arm counterfactual
grouping from analysis/autopsies/*.jsonl-shaped rows, sectors RED extraction, the
dollar-impact note ranking + 6-note cap, and that run_once() emits a crew-event ONLY
when the top note's line actually changed. Every path is passed explicitly per-test via
tmp_path -- no test here ever reads or writes real repo state (crypto-twin ledgers,
autopsies, or sectors.json).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import coach_notes as cn  # noqa: E402
import crew_events as ce  # noqa: E402


def _exit_row(ts_utc: str, realized_usd: float, *, reason: str = "structure_stop @ 100.0",
              scenario=None) -> dict:
    return {"ts_utc": ts_utc, "event": "EXIT_FILLED", "symbol": "BTC/USD",
            "realized_usd": realized_usd, "realized_pct": realized_usd / 100.0,
            "reason": reason, "scenario": scenario}


def _autopsy_row(arm: str, actual_pnl: float, best_cf=None, stop_cost=None) -> dict:
    row = {"arm": arm, "actual_pnl": actual_pnl}
    if best_cf is not None:
        row["best_counterfactual"] = best_cf
        row["stop_cost_vs_best"] = stop_cost
    return row


# ============================================================================
# _trip_usd -- prefers wired realized_usd, falls back to price*qty, else None
# ============================================================================

def test_trip_usd_prefers_wired_realized_usd():
    assert cn._trip_usd({"realized_usd": -3.5, "entry_price": 1, "fill_price": 999, "btc_qty": 1}) == -3.5


def test_trip_usd_falls_back_to_price_times_qty_when_realized_usd_missing():
    row = {"entry_price": 100.0, "fill_price": 105.0, "btc_qty": 0.01}
    assert cn._trip_usd(row) == pytest.approx(0.05)


def test_trip_usd_returns_none_when_nothing_usable():
    assert cn._trip_usd({}) is None


# ============================================================================
# _window_stats -- wins/losses/net/avg/worst over a time window
# ============================================================================

def test_window_stats_computes_wr_net_avg_and_worst():
    now = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    exits = [
        _exit_row("2026-09-14T19:00:00+00:00", 5.0),
        _exit_row("2026-09-14T18:00:00+00:00", -3.0),
        _exit_row("2026-09-14T17:00:00+00:00", -9.0, scenario="ENTRY_CAT_CAP"),
        _exit_row("2026-09-13T10:00:00+00:00", 2.0),  # outside a 24h window from `now`
    ]
    stats = cn._window_stats(exits, now, timedelta(hours=24))
    assert stats["n"] == 3
    assert stats["wins"] == 1
    assert stats["losses"] == 2
    assert stats["net"] == pytest.approx(-7.0)
    assert stats["avg_win"] == pytest.approx(5.0)
    assert stats["avg_loss"] == pytest.approx(-6.0)
    assert stats["worst"]["usd"] == pytest.approx(-9.0)
    assert stats["worst"]["scenario"] == "ENTRY_CAT_CAP"
    assert stats["worst"]["reason"] == "structure_stop"


def test_window_stats_empty_window_reports_none_not_zero():
    stats = cn._window_stats([], datetime.now(timezone.utc), timedelta(hours=24))
    assert stats["n"] == 0
    assert stats["net"] is None
    assert stats["avg_win"] is None
    assert stats["worst"] is None


# ============================================================================
# _tail_jsonl_rows -- bounded read, never touches the whole file
# ============================================================================

def test_tail_jsonl_rows_missing_file_is_empty(tmp_path):
    rows, earliest = cn._tail_jsonl_rows(tmp_path / "nope.jsonl", 1000)
    assert rows == []
    assert earliest is None


def test_tail_jsonl_rows_bounded_read_never_returns_a_corrupted_row(tmp_path):
    path = tmp_path / "journal.jsonl"
    lines = [json.dumps({"ts_utc": f"2026-09-{(i % 9) + 1:02d}T00:00:00+00:00", "n": i}) for i in range(200)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    full_size = path.stat().st_size
    assert full_size > 2000, "test fixture must be big enough that a 500-byte cap is a real mid-file seek"

    rows, earliest = cn._tail_jsonl_rows(path, max_bytes=500)
    assert 0 < len(rows) < 200, "a bounded read must return fewer rows than the full file"
    for r in rows:
        assert "n" in r and isinstance(r["n"], int), "every returned row must be well-formed JSON, never a fragment"
    assert earliest is not None


def test_tail_jsonl_rows_full_read_when_max_bytes_exceeds_file_size(tmp_path):
    path = tmp_path / "journal.jsonl"
    rows_in = [{"ts_utc": "2026-09-14T00:00:00+00:00", "n": i} for i in range(5)]
    path.write_text("\n".join(json.dumps(r) for r in rows_in) + "\n", encoding="utf-8")
    rows, _ = cn._tail_jsonl_rows(path, max_bytes=1_000_000)
    assert len(rows) == 5


# ============================================================================
# gather_twin_stats -- end to end over tmp-path crypto-twin state
# ============================================================================

def test_gather_twin_stats_full(tmp_path):
    journal = tmp_path / "journal.jsonl"
    now = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    rows = [_exit_row("2026-09-14T19:00:00+00:00", 5.0), _exit_row("2026-09-14T18:00:00+00:00", -3.0)]
    journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    exit_state = tmp_path / "exit-state.json"
    entered = (now - timedelta(minutes=45)).isoformat()
    exit_state.write_text(json.dumps({"BTC/USD": {"side": "bull", "entered_at_utc": entered,
                                                   "exit_state": {"entry_premium": 100.0}}}), encoding="utf-8")

    breaker = tmp_path / "breaker.json"
    breaker.write_text(json.dumps({"current_equity": 990.0, "start_of_day_equity": 1000.0}), encoding="utf-8")

    stats = cn.gather_twin_stats(now, journal_path=journal, exit_state_path=exit_state, breaker_path=breaker)
    assert stats["available"] is True
    assert stats["stats_24h"]["n"] == 2
    assert stats["open_position"]["symbol"] == "BTC/USD"
    assert stats["open_position"]["age_minutes"] == pytest.approx(45.0, abs=0.1)
    assert stats["day_pnl"] == pytest.approx(-10.0)
    assert stats["mae_mfe"] is None
    assert stats["mae_mfe_note"], "the absence of MAE/MFE must be documented, not just silently null"


def test_gather_twin_stats_missing_journal_is_unavailable(tmp_path):
    stats = cn.gather_twin_stats(datetime.now(timezone.utc), journal_path=tmp_path / "nope.jsonl")
    assert stats["available"] is False


def test_gather_twin_stats_no_open_position_when_exit_state_is_empty(tmp_path):
    journal = tmp_path / "journal.jsonl"
    now = datetime.now(timezone.utc)
    journal.write_text(json.dumps(_exit_row(now.isoformat(), 1.0)) + "\n", encoding="utf-8")
    exit_state = tmp_path / "exit-state.json"
    exit_state.write_text("{}", encoding="utf-8")
    stats = cn.gather_twin_stats(now, journal_path=journal, exit_state_path=exit_state)
    assert stats["open_position"] is None


# ============================================================================
# gather_arm_session_stats -- last-N-session grouping + counterfactual mining
# ============================================================================

def test_gather_arm_session_stats_excludes_sessions_beyond_the_last_n(tmp_path):
    d = tmp_path / "autopsies"
    d.mkdir()
    dates = ["2026-09-14", "2026-09-11", "2026-09-10", "2026-09-08", "2026-09-07", "2026-09-04"]
    for date in dates:
        pnl = -99999.0 if date == "2026-09-04" else -10.0  # sentinel on the file that must be excluded
        (d / f"{date}.jsonl").write_text(json.dumps(_autopsy_row("safe-2", pnl)) + "\n", encoding="utf-8")

    result = cn.gather_arm_session_stats(autopsy_dir=d, n_sessions=5)
    assert sorted(result["sessions_covered"]) == sorted(dates[:5])
    assert "2026-09-04" not in result["sessions_covered"]
    assert result["arms"]["safe-2"]["net"] == pytest.approx(-50.0), (
        "the 6th (oldest) session's sentinel pnl must never be counted")


def test_gather_arm_session_stats_best_counterfactual_is_most_common_among_losers(tmp_path):
    d = tmp_path / "autopsies"
    d.mkdir()
    (d / "2026-09-14.jsonl").write_text("\n".join(json.dumps(r) for r in [
        _autopsy_row("risky-1", -10.0, "wide_stop_-50", -12.0),
        _autopsy_row("risky-1", -8.0, "wide_stop_-50", -6.0),
        _autopsy_row("risky-1", -4.0, "no_stop_ride", -1.0),
        _autopsy_row("risky-1", 5.0),
    ]) + "\n", encoding="utf-8")

    result = cn.gather_arm_session_stats(autopsy_dir=d, n_sessions=5)
    arm = result["arms"]["risky-1"]
    assert arm["n"] == 4
    assert arm["losers"] == 3
    assert arm["net"] == pytest.approx(-17.0)
    assert arm["best_counterfactual"] == "wide_stop_-50"
    assert arm["best_counterfactual_loser_count"] == 2
    assert arm["best_counterfactual_delta_usd"] == pytest.approx(18.0), (
        "stop_cost_vs_best is (actual - best); the reported delta is the $ IMPROVEMENT "
        "that counterfactual would have delivered, i.e. -(-12 + -6) = +18")


def test_gather_arm_session_stats_no_losers_means_no_counterfactual(tmp_path):
    d = tmp_path / "autopsies"
    d.mkdir()
    (d / "2026-09-14.jsonl").write_text(json.dumps(_autopsy_row("risky-3", 5.0)) + "\n", encoding="utf-8")

    result = cn.gather_arm_session_stats(autopsy_dir=d, n_sessions=5)
    arm = result["arms"]["risky-3"]
    assert arm["losers"] == 0
    assert arm["best_counterfactual"] is None
    assert arm["best_counterfactual_delta_usd"] is None


def test_gather_arm_session_stats_missing_dir_is_unavailable(tmp_path):
    result = cn.gather_arm_session_stats(autopsy_dir=tmp_path / "nope")
    assert result["available"] is False
    assert result["arms"] == {}


# ============================================================================
# gather_sectors_red
# ============================================================================

def test_gather_sectors_red_filters_to_red_health_only(tmp_path):
    p = tmp_path / "sectors.json"
    p.write_text(json.dumps({"rows": [
        {"lane": "A", "health": "green", "evidence": "e1", "window_pnl": 10},
        {"lane": "B", "health": "red", "evidence": "e2", "window_pnl": -20},
    ]}), encoding="utf-8")
    red = cn.gather_sectors_red(sectors_path=p)
    assert len(red) == 1
    assert red[0]["lane"] == "B"


def test_gather_sectors_red_missing_file_is_empty_list(tmp_path):
    assert cn.gather_sectors_red(sectors_path=tmp_path / "nope.json") == []


# ============================================================================
# build_notes -- dollar-impact ranking + 6-note cap
# ============================================================================

def test_build_notes_ranks_by_absolute_dollar_impact_and_caps_at_six():
    twin_stats = {"available": False}
    arm_stats = {"available": True, "sessions_covered": ["d1"], "arms": {
        f"arm{i}": {"n": 1, "net": float(i * 10), "losers": 0, "best_counterfactual": None,
                    "best_counterfactual_loser_count": 0, "best_counterfactual_delta_usd": None}
        for i in range(1, 8)  # 7 candidates -> only the top 6 by |net| survive
    }}
    notes = cn.build_notes(twin_stats, arm_stats, [])
    assert len(notes) == 6
    deltas = [n["delta"] for n in notes]
    assert deltas == sorted(deltas, key=lambda d: -abs(d)), "must rank by descending absolute dollar impact"
    assert 10.0 not in deltas, "the smallest-impact 7th candidate must be dropped by the cap"


def test_build_notes_non_dollar_notes_rank_after_dollar_notes():
    empty_window = {"n": 0, "wins": 0, "losses": 0, "net": None, "avg_win": None, "avg_loss": None, "worst": None}
    twin_stats = {"available": True, "stats_24h": empty_window, "stats_window": empty_window,
                  "window_7d_days_actual": 0.0,
                  "open_position": {"symbol": "BTC/USD", "side": "bull", "age_minutes": 30.0, "entry_premium": 100.0}}
    arm_stats = {"available": True, "sessions_covered": ["d1"], "arms": {
        "safe-2": {"n": 3, "net": -50.0, "losers": 1, "best_counterfactual": None,
                  "best_counterfactual_loser_count": 0, "best_counterfactual_delta_usd": None}}}
    notes = cn.build_notes(twin_stats, arm_stats, [])
    assert notes[0]["lane"] == "safe-2", "the dollar-bearing note must rank before the open-position note (delta=None)"
    assert notes[1]["stat"] == "open_position"


def test_build_notes_empty_inputs_produce_no_notes():
    assert cn.build_notes({"available": False}, {"available": False, "arms": {}}, []) == []


# ============================================================================
# run_once -- end to end: writes coach-notes.json, crew-event only on change,
# never raises even when every source is missing.
# ============================================================================

def _run_once_paths(tmp_path):
    d = tmp_path / "autopsies"
    d.mkdir()
    sectors_path = tmp_path / "sectors.json"
    sectors_path.write_text(json.dumps({"rows": []}), encoding="utf-8")
    return {
        "journal_path": tmp_path / "journal.jsonl", "exit_state_path": tmp_path / "exit-state.json",
        "breaker_path": tmp_path / "breaker.json", "autopsy_dir": d, "sectors_path": sectors_path,
        "notes_path": tmp_path / "coach-notes.json", "crew_events_path": tmp_path / "crew.jsonl",
    }


def test_run_once_writes_notes_and_emits_crew_event_only_when_top_note_changes(tmp_path):
    paths = _run_once_paths(tmp_path)
    paths["exit_state_path"].write_text("{}", encoding="utf-8")
    paths["breaker_path"].write_text("{}", encoding="utf-8")
    paths["journal_path"].write_text(json.dumps(_exit_row("2026-09-14T19:00:00+00:00", -50.0)) + "\n",
                                     encoding="utf-8")
    now = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)

    doc1 = cn.run_once("t1", now, **paths)
    assert paths["notes_path"].exists()
    assert len(doc1["notes"]) == 1
    events1 = ce.read_rows(paths["crew_events_path"])
    assert len(events1) == 1
    assert events1[0]["who"] == "Coach"
    assert events1[0]["kind"] == "coaching"
    assert events1[0]["to"] == "Gamma"

    # Same data, second fire -> top note line UNCHANGED -> no second crew-event.
    cn.run_once("t2", now, **paths)
    events2 = ce.read_rows(paths["crew_events_path"])
    assert len(events2) == 1, "an unchanged top note must not re-emit a crew-event"

    # New data (an additional, larger-impact trade) changes the top note -> a 2nd event.
    with paths["journal_path"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(_exit_row("2026-09-14T20:00:00+00:00", -800.0)) + "\n")
    cn.run_once("t3", now, **paths)
    events3 = ce.read_rows(paths["crew_events_path"])
    assert len(events3) == 2, "a changed top note must emit a new crew-event"


def test_run_once_never_raises_when_everything_is_missing(tmp_path):
    now = datetime.now(timezone.utc)
    doc = cn.run_once(
        "t", now,
        journal_path=tmp_path / "nope1.jsonl", exit_state_path=tmp_path / "nope2.json",
        breaker_path=tmp_path / "nope3.json", autopsy_dir=tmp_path / "nope4",
        sectors_path=tmp_path / "nope5.json", notes_path=tmp_path / "notes.json",
        crew_events_path=tmp_path / "crew.jsonl",
    )
    assert doc["notes"] == []
    assert (tmp_path / "notes.json").exists()
