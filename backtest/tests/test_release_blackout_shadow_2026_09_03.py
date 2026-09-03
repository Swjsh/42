"""Guard suite for setup/scripts/release_blackout_shadow.py -- the forward shadow that
accrues evidence for `prereg-scheduled-release-blackout-2026-09-03.md` (task B2, stamp
2026-09-03T12:40 ET).

This instrument's ONLY job is to honestly log, per ISM release day, what R1/R2/R3 would have
done to that day's REAL fills -- without ever letting the rule's own trade-removal decision
see the release's realized size. The guards below pin the mechanics that would matter if
broken:

  1. NO LOOK-AHEAD (the one that matters most). `_apply_rules_for_date` must be structurally
     incapable of reading a move/gap value -- its signature carries no such parameter, and its
     result must be byte-identical whether or not `_load_moves_for_date` was ever called.
  2. WINDOW BOUNDARIES. R1=[09:45,10:05), R2=[09:35,10:05) -- half-open, exact edges tested.
  3. R3's ENTRY-TIME GATE. A position entered AT/AFTER 09:58 did not exist yet at T-2 and must
     never be treated as "open at 09:58" (this exact bug was caught and fixed during this
     module's own build -- regression-guarded here).
  4. THE QUOTE-TAPE ADJACENT-TICK METRIC. A strict minute-bucket comparison silently missed
     the real, documented 0.735->0.495 gap on 2026-09-03's own tape (caught during this
     module's own build); the adjacent-tick-drop metric must recover it.
  5. FORWARD-ONLY, ISM-ONLY, COMPLETION-GATED candidate-date selection, and IDEMPOTENT ledger
     writes on a second fire (same contract as `tp1_r50_forward_shadow`'s own suite).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import release_blackout_shadow as rbs  # noqa: E402
import release_gap_study as rgs        # noqa: E402


# ---------------------------------------------------------------------------------
# fixtures -- a synthetic scored position (same shape score_position() returns)
# ---------------------------------------------------------------------------------
def _position(entry_ts_et="2026-09-03T09:41:04.000000", exit_ts_et="2026-09-03T10:03:03.000000",
              symbol="SPY260903C00770000", arm="safe-2", entry_price=0.98, qty=3.0,
              exit_price=0.50, fully_closed=True, remaining=0.0, activity_id="a1",
              date_et="2026-09-03"):
    legs = [{"price": exit_price, "qty": qty, "ts_utc": "2026-09-03T14:03:03Z", "ts_et": exit_ts_et}] \
        if fully_closed else []
    realized_pnl = round((exit_price - entry_price) * qty * 100, 2) if fully_closed else 0.0
    entry_hhmmss = entry_ts_et[11:19]
    return {
        "activity_id": activity_id, "arm": arm, "symbol": symbol, "date_et": date_et,
        "entry_ts_et": entry_ts_et, "entry_ts_utc": entry_ts_et.replace("T", "T")[:19] + "Z",
        "entry_price": entry_price, "qty": qty, "multiplier": 100.0,
        "fully_closed": fully_closed, "remaining": remaining, "exit_ts_et": exit_ts_et,
        "hold_minutes": 5.0, "realized_pnl": realized_pnl, "pnl_pct_of_premium": None,
        "cap_hit_proxy": False,
        "open_across_1000": True,
        "entry_in_0945_1005": "09:45:00" <= entry_hhmmss < "10:05:00",
        "entry_in_0935_1005": "09:35:00" <= entry_hhmmss < "10:05:00",
        "legs": legs,
    }


# ===================================================================================
# 1. NO LOOK-AHEAD
# ===================================================================================
def test_apply_rules_signature_carries_no_move_parameter():
    import inspect
    params = set(inspect.signature(rbs._apply_rules_for_date).parameters)
    assert not any("move" in p.lower() or "gap" in p.lower() or "adverse" in p.lower() for p in params)
    assert params == {"date_str", "day_positions"}


def test_apply_rules_result_identical_whether_or_not_moves_were_ever_computed(monkeypatch):
    """Poison _load_moves_for_date so calling it would raise -- confirm _apply_rules_for_date
    never touches it and produces the same result regardless."""
    day_positions = [_position(entry_ts_et="2026-09-03T09:41:04.000000")]

    def _poison(date_str):
        raise AssertionError("_apply_rules_for_date must never trigger a move computation")

    monkeypatch.setattr(rbs, "_load_moves_for_date", _poison)
    result = rbs._apply_rules_for_date("2026-09-03", day_positions)
    assert result["r1"]["n_removed"] == 0        # 09:41 is before R1's window -- correct either way
    assert result["r2"]["n_removed"] == 1        # 09:41 IS inside R2's window
    # calling it again (moves still poisoned) must give byte-identical output
    result2 = rbs._apply_rules_for_date("2026-09-03", day_positions)
    assert result == result2


# ===================================================================================
# 2. R1 / R2 window boundaries -- half-open [start, end)
# ===================================================================================
@pytest.mark.parametrize("ts,in_r1,in_r2", [
    ("2026-09-03T09:34:59.000000", False, False),   # before R2 window entirely
    ("2026-09-03T09:35:00.000000", False, True),     # R2 opens exactly here
    ("2026-09-03T09:44:59.000000", False, True),     # inside R2, still before R1
    ("2026-09-03T09:45:00.000000", True, True),      # R1 opens exactly here
    ("2026-09-03T10:04:59.999999", True, True),      # last instant inside both windows
    ("2026-09-03T10:05:00.000000", False, False),    # both windows close exactly here
])
def test_r1_r2_window_boundaries(ts, in_r1, in_r2):
    p = _position(entry_ts_et=ts)
    result = rbs._apply_rules_for_date("2026-09-03", [p])
    assert (result["r1"]["n_removed"] == 1) == in_r1
    assert (result["r2"]["n_removed"] == 1) == in_r2


def test_r1_r2_only_count_fully_closed_positions():
    p = _position(entry_ts_et="2026-09-03T09:50:00.000000", fully_closed=False, remaining=2.0)
    result = rbs._apply_rules_for_date("2026-09-03", [p])
    assert result["r1"]["n_removed"] == 0
    assert result["r2"]["n_removed"] == 0


def test_r1_net_saved_sign_is_savings_not_pnl():
    """A LOSING trade removed by the rule should show as a POSITIVE net_saved (a loss
    avoided); a WINNING trade removed should show as NEGATIVE (a winner forgone)."""
    loser = _position(entry_ts_et="2026-09-03T09:50:00.000000", entry_price=1.00, exit_price=0.50, qty=1.0)
    winner = _position(entry_ts_et="2026-09-03T09:52:00.000000", entry_price=1.00, exit_price=2.00,
                       qty=1.0, activity_id="a2")
    result = rbs._apply_rules_for_date("2026-09-03", [loser, winner])
    assert result["r1"]["n_removed"] == 2
    assert result["r1"]["net_saved"] == pytest.approx(50.0 - 100.0)   # +50 avoided, -100 forgone


# ===================================================================================
# 3. R3's entry-time gate (the regression this module's own build caught and fixed)
# ===================================================================================
def test_r3_position_entered_after_0958_is_excluded_not_flattened():
    """A position entered AT/AFTER 09:58 did not exist yet at T-2 -- R3 must never treat it
    as 'open at 09:58' (the exact bug this module's build caught in release_gap_study.py)."""
    p = _position(entry_ts_et="2026-09-03T11:06:05.000000")   # e.g. today's real Wave 3 entry time
    res = rgs.r3_delta_for_position(p, {})
    assert res["included"] is False
    assert res["exclude_reason"] == rgs.R3_EXCLUDE_NOT_YET_ENTERED


def test_r3_position_entered_before_0958_and_still_open_then_is_included():
    p = _position(entry_ts_et="2026-09-03T09:41:04.000000",
                  exit_ts_et="2026-09-03T10:03:03.000000")   # still open at 09:58, closes after
    # supply a bar_cache pre-seeded for this (symbol,date) key so no real file I/O happens
    key = (p["symbol"], p["date_et"])
    res = rgs.r3_delta_for_position(p, {key: {"09:58": {"c": 0.70}}})
    assert res["included"] is True
    assert res["remaining_at_0958"] == pytest.approx(3.0)
    assert res["flatten_price"] == 0.70


def test_r3_flatten_math_matches_hand_computation():
    """entry 0.98 x3, flatten mark 0.70 at 09:58, actual exit legs all AFTER 09:58 at 0.50.
    actual_remaining_pnl = (0.50-0.98)*3*100 = -144.00
    cf_remaining_pnl      = (0.70-0.98)*3*100 = -84.00
    delta = cf - actual = -84.00 - (-144.00) = +60.00 (flattening early would have SAVED $60)."""
    p = _position(entry_ts_et="2026-09-03T09:41:04.000000", entry_price=0.98,
                  exit_ts_et="2026-09-03T10:03:03.000000", exit_price=0.50, qty=3.0)
    key = (p["symbol"], p["date_et"])
    res = rgs.r3_delta_for_position(p, {key: {"09:58": {"c": 0.70}}})
    assert res["included"] is True
    assert res["actual_remaining_pnl"] == pytest.approx(-144.00)
    assert res["cf_remaining_pnl"] == pytest.approx(-84.00)
    assert res["delta"] == pytest.approx(60.00)


def test_r3_falls_back_to_nearest_earlier_minute_when_0958_missing():
    p = _position(entry_ts_et="2026-09-03T09:41:04.000000")
    key = (p["symbol"], p["date_et"])
    res = rgs.r3_delta_for_position(p, {key: {"09:56": {"c": 0.80}}})   # no 09:58/09:57 bar
    assert res["included"] is True
    assert res["flatten_price"] == 0.80


def test_r3_excluded_when_no_bar_data_at_all():
    p = _position(entry_ts_et="2026-09-03T09:41:04.000000")
    key = (p["symbol"], p["date_et"])
    res = rgs.r3_delta_for_position(p, {key: {}})
    assert res["included"] is False
    assert res["exclude_reason"] == rgs.R3_EXCLUDE_NO_BAR


def test_r3_already_closed_before_0958_has_no_effect():
    p = _position(entry_ts_et="2026-09-03T09:41:04.000000", exit_ts_et="2026-09-03T09:50:00.000000")
    res = rgs.r3_delta_for_position(p, {})
    assert res["included"] is False
    assert res["exclude_reason"] == rgs.R3_EXCLUDE_NO_EFFECT


# ===================================================================================
# 4. Quote-tape adjacent-tick metric (the metric-precision bug this module's build caught)
# ===================================================================================
def test_quote_tape_adjacent_tick_recovers_a_gap_that_straddles_a_minute_boundary(tmp_path, monkeypatch):
    """Reproduces the exact shape of 2026-09-03's own tape: a poll at 10:00:48 (mid 0.735)
    followed by a poll at 10:01:10 (mid 0.495) -- both inside the same nominal 'minute pair'
    from a bucket standpoint is ambiguous, but the drop is real and must be found."""
    qtdir = tmp_path / "quote-tape"
    qtdir.mkdir()
    rows = [
        {"ts_et": "2026-09-03T09:59:45.113710", "symbol": "SPY260903C00770000", "mid": 0.785},
        {"ts_et": "2026-09-03T10:00:48.767813", "symbol": "SPY260903C00770000", "mid": 0.735},
        {"ts_et": "2026-09-03T10:01:10.013080", "symbol": "SPY260903C00770000", "mid": 0.495},
        {"ts_et": "2026-09-03T10:01:31.014840", "symbol": "SPY260903C00770000", "mid": 0.525},
    ]
    (qtdir / "2026-09-03.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(rbs, "QUOTE_TAPE_DIR", qtdir)

    moves = rbs._quote_tape_option_moves("2026-09-03")
    assert len(moves) == 1
    assert moves[0]["symbol"] == "SPY260903C00770000"
    # (0.495-0.735)/0.735*100 = -32.653...
    assert moves[0]["move_1000_1001_pct"] == pytest.approx(-32.653, abs=0.01)
    assert moves[0]["source"] == "quote_tape_adjacent_tick"


def test_quote_tape_moves_ignore_ticks_outside_the_padded_window(tmp_path, monkeypatch):
    qtdir = tmp_path / "quote-tape"
    qtdir.mkdir()
    rows = [
        {"ts_et": "2026-09-03T09:30:00.000000", "symbol": "SPY260903C00770000", "mid": 1.00},
        {"ts_et": "2026-09-03T09:31:00.000000", "symbol": "SPY260903C00770000", "mid": 0.10},  # huge drop, but way outside window
        {"ts_et": "2026-09-03T10:00:00.000000", "symbol": "SPY260903C00770000", "mid": 0.80},
        {"ts_et": "2026-09-03T10:00:30.000000", "symbol": "SPY260903C00770000", "mid": 0.78},
    ]
    (qtdir / "2026-09-03.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(rbs, "QUOTE_TAPE_DIR", qtdir)

    moves = rbs._quote_tape_option_moves("2026-09-03")
    assert len(moves) == 1
    # only the in-window pair (0.80->0.78) should be seen, NOT the -90% pair at 09:30-09:31
    assert moves[0]["move_1000_1001_pct"] == pytest.approx((0.78 - 0.80) / 0.80 * 100, abs=0.01)


def test_load_moves_for_date_reports_no_data_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(rbs, "QUOTE_TAPE_DIR", tmp_path / "empty-quote-tape")
    monkeypatch.setattr(rgs, "OPT_CACHE_DIR", tmp_path / "empty-highres")
    monkeypatch.setattr(rgs, "SPY_CACHE_DIR", tmp_path / "empty-spy-cache")
    result = rbs._load_moves_for_date("2099-01-01")
    assert result["move_source"] == "no_data"
    assert result["worst_adverse_1000_1001_pct"] is None


# ===================================================================================
# 5. candidate_dates -- forward-only, ISM-only, completion-gated
# ===================================================================================
def test_candidate_dates_no_backfill_before_accrual_start():
    out = rbs.candidate_dates(today=dt.date(2026, 8, 1), now_time=dt.time(20, 0))
    assert out == []


def test_candidate_dates_excludes_incomplete_today():
    out = rbs.candidate_dates(today=dt.date(2026, 9, 3), now_time=dt.time(12, 0))
    assert "2026-09-03" not in out


def test_candidate_dates_includes_today_once_complete():
    out = rbs.candidate_dates(today=dt.date(2026, 9, 3), now_time=dt.time(16, 0))
    assert "2026-09-03" in out


def test_is_ism_date_excludes_secondary_only_day():
    """2026-08-28 carries only a secondary (umich_sentiment_final) release -- never ISM.
    (Tested against `_is_ism_date` directly, not `candidate_dates`, because 2026-08-28 predates
    ACCRUAL_START_DATE and `candidate_dates`'s no-backfill floor would make the date
    unreachable regardless -- that floor is guarded separately, above.)"""
    assert rbs._is_ism_date("2026-08-28") is False


def test_is_ism_date_true_on_a_known_historical_ism_day():
    assert rbs._is_ism_date("2026-08-05") is True


def test_candidate_dates_respects_the_calendar_filter_within_its_own_reachable_range(monkeypatch):
    """With ACCRUAL_START_DATE moved earlier (for this test only) so the range is actually
    reachable, confirm candidate_dates includes the ISM day and excludes the secondary-only
    day inside that same window."""
    monkeypatch.setattr(rbs, "ACCRUAL_START_DATE", "2026-08-01")
    out = rbs.candidate_dates(today=dt.date(2026, 8, 28), now_time=dt.time(20, 0))
    assert "2026-08-05" in out          # ISM -- included
    assert "2026-08-03" in out          # ISM -- included
    assert "2026-08-28" not in out      # secondary-only (UMich) -- excluded


# ===================================================================================
# 6. run() -- idempotent, own ledger/summary, fail-open
# ===================================================================================
@pytest.fixture
def _wired(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    monkeypatch.setattr(rbs, "OUT_DIR", out_dir)
    monkeypatch.setattr(rbs, "LEDGER", out_dir / "ledger.jsonl")
    monkeypatch.setattr(rbs, "SUMMARY", out_dir / "summary.json")
    monkeypatch.setattr(rbs, "candidate_dates", lambda: ["2026-09-03"])
    monkeypatch.setattr(rgs, "build_scored_positions",
                         lambda: [_position(entry_ts_et="2026-09-03T09:50:00.000000")])
    monkeypatch.setattr(rbs, "_load_moves_for_date",
                         lambda d: {"move_source": "no_data", "spy_move_1000_1001_dollars": None,
                                    "option_moves": [], "worst_adverse_1000_1001_pct": None})
    return out_dir


def test_run_writes_one_row_then_is_idempotent(_wired):
    out1 = rbs.run()
    assert out1["new_this_run"] == 1
    assert rbs.LEDGER.exists()
    lines1 = rbs.LEDGER.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines1) == 1

    out2 = rbs.run()
    assert out2["new_this_run"] == 0
    lines2 = rbs.LEDGER.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 1          # no duplicate row on a second fire


def test_run_never_raises_on_a_broken_input(monkeypatch, tmp_path):
    out_dir = tmp_path / "out2"
    monkeypatch.setattr(rbs, "OUT_DIR", out_dir)
    monkeypatch.setattr(rbs, "LEDGER", out_dir / "ledger.jsonl")
    monkeypatch.setattr(rbs, "SUMMARY", out_dir / "summary.json")

    def _boom():
        raise RuntimeError("simulated upstream failure")

    monkeypatch.setattr(rgs, "build_scored_positions", _boom)
    out = rbs.run()          # must not raise -- fail-open by contract
    assert "error" in out


def test_summary_ship_verdict_bar_not_met_when_thin(_wired):
    out = rbs.run()
    assert out["bar_met"] is False
    assert out["R1"]["ship_verdict"] == "BAR_NOT_MET"
    assert out["R3"]["ship_verdict"] == "BAR_NOT_MET"
    assert out["R2"]["ship_verdict"] == "NEVER_SHIP_ELIGIBLE"
