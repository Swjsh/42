"""Guard: setup/scripts/hypothesis_scorer.py -- the deterministic verdict engine that closes
the Station idea loop (GOAL-GAMMA-STATION-2026-09-13 item (12)).

Locks in: size_cap's linear-fill arithmetic + qty/arm confound detection; the pre/post-
registration split by a card's own ts_et (strictly before = in-sample, strictly after =
post-registration); the min_n gate that keeps a verdict at "pending" until post-registration
n is large enough; exit_shape's unknown-shape -> spec_error path; metric_correlation's sign +
permutation-p verdict; time_stop_minutes' honest "not yet expressible" spec_error;
rescore_board's board-mutation contract (status only flips on a terminal verdict, a missing
test_spec increments a fire counter and eventually spec_errors, a card with NO testing status
is never touched); and load_autopsy_rows' fail-open malformed-line handling.

No test here touches the real repo's analysis/autopsies/, ideas-board.json, or
hypotheses-settled.json -- every path is passed explicitly (autopsy_dir/board_path/
verdicts_path/settled_path), matching the pattern hypothesis_scorer.py's own functions use
throughout (defaults are module-level constants, but every function accepts an override)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import hypothesis_scorer as hs  # noqa: E402
import station_board as sb  # noqa: E402


def _row(**kw) -> dict:
    base = {"date": "2026-09-05", "arm": "safe-2", "strategy": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "qty": 5, "actual_pnl": -100.0, "entry_spike_pct": 0.1,
            "counterfactuals": {"wide_stop_-50": -60.0, "no_stop_ride": -150.0, "hold_to_time": 40.0}}
    base.update(kw)
    return base


def _card(**kw) -> dict:
    base = {"id": "c1", "ts_et": "2026-09-01 12:00:00 ET", "status": "testing", "title": "T"}
    base.update(kw)
    return base


_NOW = datetime(2026, 9, 10)


# ============================================================================
# _row_et_datetime / pre-post split
# ============================================================================

def test_row_et_datetime_prefers_entry_ts_utc_over_date():
    # 2026-09-01 00:30 UTC -> EDT (-4h) -> 2026-08-31 20:30 ET, NOT the 'date' field's day.
    r = _row(entry_ts_utc="2026-09-01T00:30:00Z", date="2026-09-01")
    dt = hs._row_et_datetime(r)
    assert dt == datetime(2026, 8, 31, 20, 30)


def test_row_et_datetime_falls_back_to_date_at_midnight():
    r = {"date": "2026-09-05"}
    assert hs._row_et_datetime(r) == datetime(2026, 9, 5, 0, 0)


def test_row_et_datetime_none_when_neither_field_usable():
    assert hs._row_et_datetime({}) is None
    assert hs._row_et_datetime({"date": "not-a-date"}) is None


def test_parse_card_cutoff_et_handles_trailing_et_suffix():
    assert hs._parse_card_cutoff_et("2026-09-13 14:51:00 ET") == datetime(2026, 9, 13, 14, 51, 0)


def test_parse_card_cutoff_et_none_on_bad_format():
    assert hs._parse_card_cutoff_et("garbage") is None
    assert hs._parse_card_cutoff_et("") is None


def test_split_pre_post_is_strict_both_sides():
    cutoff = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        {"date": "2026-08-31"},                        # pre
        {"date": "2026-09-01"},                        # midnight == before noon cutoff -> pre
        {"entry_ts_utc": "2026-09-01T16:00:00Z"},       # 12:00 ET exactly == cutoff -> excluded
        {"date": "2026-09-02"},                         # post
        {},                                              # unresolvable -> excluded from both
    ]
    pre, post = hs._split_pre_post(rows, cutoff)
    assert len(pre) == 2
    assert len(post) == 1


# ============================================================================
# size_cap
# ============================================================================

def test_size_cap_arithmetic_is_linear_fill():
    rows = [_row(qty=5, actual_pnl=-100.0, entry_ts_utc="2026-09-05T14:00:00Z")]
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    # cf = -100 * min(5,3)/5 = -60; delta = -60 - (-100) = +40
    assert result["effect_post"] == pytest.approx(40.0)
    assert result["verdict"] == "supported"


def test_size_cap_no_effect_when_qty_already_at_or_below_cap():
    rows = [_row(qty=3, actual_pnl=-50.0, entry_ts_utc="2026-09-05T14:00:00Z")]
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    assert result["effect_post"] == pytest.approx(0.0)
    assert result["verdict"] == "refuted"   # zero improvement does not confirm the hypothesis


def test_size_cap_splits_pre_and_post_by_card_ts_et():
    card = _card(ts_et="2026-09-01 12:00:00 ET", test_spec={"type": "size_cap", "params": {"cap": 3}})
    rows = (
        [_row(qty=5, actual_pnl=-100.0, date="2026-08-20")] * 2   # in-sample (pre)
        + [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 4  # post-registration
    )
    result = hs.score_card(card, rows, now_et=_NOW, min_n=3)
    assert result["n_pre"] == 2
    assert result["n_post"] == 4
    assert result["effect_pre"] == pytest.approx(80.0)
    assert result["effect_post"] == pytest.approx(160.0)


def test_size_cap_min_n_gate_keeps_verdict_pending():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    rows = [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 2   # only 2 post rows
    result = hs.score_card(card, rows, now_et=_NOW, min_n=10)
    assert result["verdict"] == "pending"
    assert result["n_post"] == 2
    # both windows still reported honestly, never hidden behind the pending status
    assert result["effect_post"] is not None


def test_size_cap_flags_qty_arm_confound():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    rows = [
        _row(qty=5, arm="bold-2", actual_pnl=-100.0, date="2026-09-05"),
        _row(qty=5, arm="safe-3", actual_pnl=-100.0, date="2026-09-05"),
        _row(qty=1, arm="safe-2", actual_pnl=50.0, date="2026-09-05"),
    ]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    assert any("CONFOUND" in a for a in result["assumptions"])


def test_size_cap_no_confound_when_arms_overlap_both_sides_of_cap():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    rows = [
        _row(qty=5, arm="safe-2", actual_pnl=-100.0, date="2026-09-05"),
        _row(qty=1, arm="safe-2", actual_pnl=50.0, date="2026-09-05"),
    ]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    assert not any("CONFOUND" in a for a in result["assumptions"])


def test_size_cap_bad_cap_is_spec_error():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": -1}})
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"
    card2 = _card(test_spec={"type": "size_cap", "params": {}})
    assert hs.score_card(card2, [_row()], now_et=_NOW)["verdict"] == "spec_error"


def test_size_cap_respects_strategy_and_arm_filters():
    card = _card(test_spec={"type": "size_cap",
                            "params": {"cap": 3, "strategy": "BEARISH", "arm": "bold-2"}})
    rows = [
        _row(qty=5, actual_pnl=-100.0, strategy="BULLISH_RECLAIM_RIDE_THE_RIBBON", arm="bold-2", date="2026-09-05"),
        _row(qty=5, actual_pnl=-999.0, strategy="BEARISH_REJECTION_RIDE_THE_RIBBON", arm="safe-2", date="2026-09-05"),
        _row(qty=5, actual_pnl=-40.0, strategy="BEARISH_REJECTION_RIDE_THE_RIBBON", arm="bold-2", date="2026-09-05"),
    ]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    # only the 3rd row matches BOTH filters: cf = -40*3/5=-24, delta=+16
    assert result["n_post"] == 1
    assert result["effect_post"] == pytest.approx(16.0)


# ============================================================================
# exit_shape
# ============================================================================

def test_exit_shape_reads_existing_counterfactual_column():
    card = _card(test_spec={"type": "exit_shape", "params": {"shape": "wide_stop_-50"}})
    rows = [_row(actual_pnl=-100.0, counterfactuals={"wide_stop_-50": -60.0}, date="2026-09-05")]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    assert result["effect_post"] == pytest.approx(40.0)
    assert result["verdict"] == "supported"


def test_exit_shape_unknown_shape_is_spec_error_and_lists_known_shapes():
    card = _card(test_spec={"type": "exit_shape", "params": {"shape": "not_a_real_shape"}})
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"
    assert "wide_stop_-50" in result["detail"]


def test_exit_shape_flags_diagnostic_only_shape():
    card = _card(test_spec={"type": "exit_shape", "params": {"shape": "hold_to_time"}})
    rows = [_row(actual_pnl=-100.0, counterfactuals={"hold_to_time": 40.0}, date="2026-09-05")]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=1)
    assert any("ORACLE" in a or "diagnostic" in a for a in result["assumptions"])


# ============================================================================
# metric_correlation
# ============================================================================

def test_metric_correlation_perfect_positive_signal():
    card = _card(test_spec={"type": "metric_correlation",
                            "params": {"x": "entry_spike_pct", "y": "actual_pnl"}})
    # Perfectly linear negative relationship: higher spike -> worse pnl.
    rows = [_row(entry_spike_pct=x, actual_pnl=-x * 1000.0, date="2026-09-05")
           for x in (0.01, 0.05, 0.10, 0.15, 0.20, 0.25)]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=5)
    assert result["effect_post"] == pytest.approx(-1.0, abs=1e-6)
    assert result["p_value"] is not None and result["p_value"] < 0.10
    assert result["verdict"] == "supported"


def test_metric_correlation_no_relationship_is_refuted_with_enough_n():
    card = _card(test_spec={"type": "metric_correlation",
                            "params": {"x": "entry_spike_pct", "y": "actual_pnl"}})
    # Alternating sign, no real relationship -- should not clear the significance bar.
    vals = [(0.05, 10.0), (0.05, -10.0), (0.10, 10.0), (0.10, -10.0),
           (0.15, 10.0), (0.15, -10.0), (0.20, 10.0), (0.20, -10.0)]
    rows = [_row(entry_spike_pct=x, actual_pnl=y, date="2026-09-05") for x, y in vals]
    result = hs.score_card(card, rows, now_et=_NOW, min_n=5)
    assert result["verdict"] in ("refuted", "pending")  # never a false "supported"


def test_metric_correlation_too_few_rows_is_spec_error():
    card = _card(test_spec={"type": "metric_correlation", "params": {"x": "entry_spike_pct"}})
    rows = [_row(entry_spike_pct=0.1, actual_pnl=-10.0)]
    result = hs.score_card(card, rows, now_et=_NOW)
    assert result["verdict"] == "spec_error"


def test_metric_correlation_bad_method_is_spec_error():
    card = _card(test_spec={"type": "metric_correlation",
                            "params": {"x": "entry_spike_pct", "method": "not_a_method"}})
    rows = [_row(entry_spike_pct=x, actual_pnl=-x) for x in (0.1, 0.2, 0.3, 0.4)]
    assert hs.score_card(card, rows, now_et=_NOW)["verdict"] == "spec_error"


def test_metric_correlation_missing_x_field_is_spec_error():
    card = _card(test_spec={"type": "metric_correlation", "params": {}})
    result = hs.score_card(card, [_row()] * 5, now_et=_NOW)
    assert result["verdict"] == "spec_error"


# ============================================================================
# time_stop_minutes -- always spec_error today (day 2 work, documented)
# ============================================================================

def test_time_stop_minutes_is_always_spec_error_today():
    card = _card(test_spec={"type": "time_stop_minutes", "params": {"minutes": 5}})
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"
    assert "day 2" in result["detail"]


# ============================================================================
# score_card -- generic contract (never raises, spec validation, unknown card ts_et)
# ============================================================================

def test_score_card_no_test_spec_is_spec_error():
    card = _card()  # no test_spec key at all
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"


def test_score_card_null_test_spec_is_spec_error():
    card = _card(test_spec=None)
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"


def test_score_card_unparseable_ts_et_is_spec_error():
    card = _card(ts_et="not-a-timestamp", test_spec={"type": "size_cap", "params": {"cap": 3}})
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"


def test_score_card_never_raises_on_a_handler_exception(monkeypatch):
    monkeypatch.setitem(hs._SPEC_HANDLERS, "size_cap", lambda *a, **kw: 1 / 0)
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    result = hs.score_card(card, [_row()], now_et=_NOW)
    assert result["verdict"] == "spec_error"
    assert "ZeroDivisionError" in result["detail"]


def test_score_card_always_stamps_scored_at_et():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    result = hs.score_card(card, [_row(date="2026-09-05")], now_et=_NOW, min_n=1)
    assert result["scored_at_et"] == "2026-09-10 00:00:00 ET"


# ============================================================================
# load_autopsy_rows -- fail-open, malformed-line handling
# ============================================================================

def test_load_autopsy_rows_skips_malformed_lines(tmp_path):
    (tmp_path / "2026-09-05.jsonl").write_text(
        json.dumps(_row()) + "\nnot json at all\n" + json.dumps(_row(actual_pnl=1.0)) + "\n",
        encoding="utf-8")
    rows = hs.load_autopsy_rows(tmp_path)
    assert len(rows) == 2


def test_load_autopsy_rows_missing_dir_returns_empty(tmp_path):
    assert hs.load_autopsy_rows(tmp_path / "does-not-exist") == []


def test_load_autopsy_rows_never_descends_into_twin_subdir(tmp_path):
    (tmp_path / "2026-09-05.jsonl").write_text(json.dumps(_row()), encoding="utf-8")
    twin_dir = tmp_path / "twin"
    twin_dir.mkdir()
    (twin_dir / "2026-09-05.jsonl").write_text(json.dumps({"event": "CLOSED"}), encoding="utf-8")
    rows = hs.load_autopsy_rows(tmp_path)
    assert len(rows) == 1   # the twin row must never leak into the SPY glob


# ============================================================================
# rescore_board -- the orchestrator
# ============================================================================

def _write_board(path: Path, cards: list) -> None:
    path.write_text(json.dumps(cards), encoding="utf-8")


def test_rescore_board_is_a_cheap_noop_with_no_testing_cards(tmp_path):
    board_path = tmp_path / "board.json"
    _write_board(board_path, [{"id": "c1", "status": "proposed", "title": "x"}])
    verdicts_path = tmp_path / "v.jsonl"

    summary = hs.rescore_board(board_path=board_path, autopsy_dir=tmp_path / "autopsies",
                               verdicts_path=verdicts_path, settled_path=tmp_path / "s.json")

    assert summary["testing_cards"] == 0
    assert not verdicts_path.exists()


def test_rescore_board_missing_spec_increments_counter_then_spec_errors(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    _write_board(board_path, [_card(status="testing")])  # no test_spec

    for _ in range(2):
        summary = hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                                   verdicts_path=tmp_path / "v.jsonl", settled_path=tmp_path / "s.json",
                                   now_et=_NOW)
        assert summary["pending_missing_spec"] == 1
        board = json.loads(board_path.read_text(encoding="utf-8"))
        assert "spec_error" not in board[0]
        assert board[0]["status"] == "testing"

    # third fire without a spec crosses MAX_FIRES_WITHOUT_SPEC (3)
    hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                     verdicts_path=tmp_path / "v.jsonl", settled_path=tmp_path / "s.json", now_et=_NOW)
    board = json.loads(board_path.read_text(encoding="utf-8"))
    assert "spec_error" in board[0]
    assert board[0]["status"] == "testing"   # spec_error never itself flips status


def test_rescore_board_flips_status_and_writes_ledger_row(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    verdicts_path = tmp_path / "v.jsonl"
    _write_board(board_path, [_card(test_spec={"type": "size_cap", "params": {"cap": 3}})])
    rows = [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 5
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    summary = hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                               verdicts_path=verdicts_path, settled_path=tmp_path / "s.json",
                               min_n=3, now_et=_NOW)

    assert summary["supported"] == 1
    board = json.loads(board_path.read_text(encoding="utf-8"))
    assert board[0]["status"] == "supported"
    assert board[0]["verdict_n_post"] == 5
    ledger = [json.loads(l) for l in verdicts_path.read_text(encoding="utf-8").strip().splitlines()]
    assert len(ledger) == 1
    assert ledger[0]["card_id"] == "c1"
    assert ledger[0]["result"]["verdict"] == "supported"


def test_rescore_board_settles_mechanism_ref_on_terminal_verdict(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    settled_path = tmp_path / "settled.json"
    _write_board(board_path, [_card(test_spec={"type": "size_cap", "params": {"cap": 3}},
                                    mechanism_ref="paying_the_signal_spike")])
    rows = [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 3
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                     verdicts_path=tmp_path / "v.jsonl", settled_path=settled_path,
                     min_n=3, now_et=_NOW)

    doc = json.loads(settled_path.read_text(encoding="utf-8"))
    assert doc["settled"][0]["mechanism"] == "paying_the_signal_spike"
    assert doc["settled"][0]["verdict"] == "STATION_SUPPORTED"
    assert doc["settled"][0]["source"] == "station"


def test_rescore_board_does_not_settle_mechanism_on_pending_verdict(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    settled_path = tmp_path / "settled.json"
    _write_board(board_path, [_card(test_spec={"type": "size_cap", "params": {"cap": 3}},
                                    mechanism_ref="paying_the_signal_spike")])
    rows = [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 1   # below min_n
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                     verdicts_path=tmp_path / "v.jsonl", settled_path=settled_path,
                     min_n=10, now_et=_NOW)

    assert not settled_path.exists()


def test_rescore_board_dry_run_never_writes_anything(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    verdicts_path = tmp_path / "v.jsonl"
    original = [_card(test_spec={"type": "size_cap", "params": {"cap": 3}})]
    _write_board(board_path, original)
    rows = [_row(qty=5, actual_pnl=-100.0, date="2026-09-05")] * 5
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    summary = hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                               verdicts_path=verdicts_path, settled_path=tmp_path / "s.json",
                               min_n=3, now_et=_NOW, dry_run=True)

    assert summary["supported"] == 1
    assert summary["dry_run"] is True
    assert json.loads(board_path.read_text(encoding="utf-8")) == original, "dry_run must never write the board"
    assert not verdicts_path.exists()


def test_rescore_board_ignores_non_testing_cards(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    cards = [_card(id="a", status="proposed"), _card(id="b", status="killed"),
            _card(id="c", status="testing", test_spec={"type": "size_cap", "params": {"cap": 3}})]
    _write_board(board_path, cards)
    (autopsy_dir / "all.jsonl").write_text(
        "\n".join(json.dumps(_row(qty=5, actual_pnl=-100.0, date="2026-09-05")) for _ in range(3)),
        encoding="utf-8")

    summary = hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                               verdicts_path=tmp_path / "v.jsonl", settled_path=tmp_path / "s.json",
                               min_n=3, now_et=_NOW)

    assert summary["testing_cards"] == 1
    board = json.loads(board_path.read_text(encoding="utf-8"))
    assert board[0]["status"] == "proposed" and "verdict" not in board[0]
    assert board[1]["status"] == "killed" and "verdict" not in board[1]


def test_rescore_board_bh_corrects_multiple_correlation_cards(tmp_path):
    board_path = tmp_path / "board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()
    spec = {"type": "metric_correlation", "params": {"x": "entry_spike_pct", "y": "actual_pnl"}}
    _write_board(board_path, [_card(id="a", test_spec=spec), _card(id="b", test_spec=spec)])
    rows = [_row(entry_spike_pct=x, actual_pnl=-x * 1000.0, date="2026-09-05")
           for x in (0.01, 0.05, 0.10, 0.15, 0.20, 0.25)]
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    hs.rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                     verdicts_path=tmp_path / "v.jsonl", settled_path=tmp_path / "s.json",
                     min_n=5, now_et=_NOW)

    board = json.loads(board_path.read_text(encoding="utf-8"))
    assert "verdict_bh_q" in board[0]
    assert "verdict_bh_q" in board[1]


# ============================================================================
# graveyard exclusion (station_board.graveyard_titles + station_facts wiring)
# ============================================================================

def test_graveyard_titles_only_terminal_statuses():
    board = [
        {"title": "A", "status": "proposed"},
        {"title": "B", "status": "testing"},
        {"title": "C", "status": "killed"},
        {"title": "D", "status": "refuted"},
        {"title": "E", "status": "supported"},
    ]
    assert sb.graveyard_titles(board) == ["C", "D", "E"]


def test_graveyard_titles_empty_board():
    assert sb.graveyard_titles([]) == []
