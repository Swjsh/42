"""Guards for entry_block_watch.py -- the ESCALATION CORD (WS4, 2026-07-27 night build).

Locks: the tripwire condition (score + level-tied raw trigger + non-ENTER verdict),
the 2-consecutive-tick debounce -> exactly ONE alert per episode, the 3-alerts/day cap
with a logged SUPPRESSED line on the 4th episode, malformed-row tolerance, the
byte-offset tail (incl. a mid-write partial-line holdback + file-rotation reset), and
the COMPATIBILITY TEST this module ships with: rows in the shape core-decisions.jsonl
actually has TODAY (2026-07-27, before commit 3ced7457's new fields land on 2026-07-28)
must produce zero alerts and zero crashes, not an error.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "entry_block_watch.py"
_spec = importlib.util.spec_from_file_location("entry_block_watch", _SCRIPT)
ebw = importlib.util.module_from_spec(_spec)
sys.modules["entry_block_watch"] = ebw
_spec.loader.exec_module(ebw)  # type: ignore


def _row(**kw) -> dict:
    base = {
        "ts_et": "2026-07-28T09:40:00", "account": "safe", "verdict": "HOLD",
        "spy": 744.90, "bear_score": 5, "bull_score": 5,
        "bear_triggers_raw": [], "bull_triggers_raw": [],
        "bear_blockers": [], "bull_blockers": [], "levels_active": [],
    }
    base.update(kw)
    return base


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# _qualifies -- the tripwire condition, incl. the compatibility test
# --------------------------------------------------------------------------- #
def test_qualifies_bear_true_when_score_trigger_and_not_entered():
    row = _row(bear_score=9, bear_triggers_raw=["level_rejection", "confluence"], verdict="HOLD")
    assert ebw._qualifies(row, "bear") is True


def test_qualifies_false_when_engine_actually_entered():
    row = _row(bear_score=9, bear_triggers_raw=["level_rejection"], verdict="ENTER_BEAR")
    assert ebw._qualifies(row, "bear") is False


def test_qualifies_false_below_threshold():
    row = _row(bear_score=7, bear_triggers_raw=["level_rejection"], verdict="HOLD")
    assert ebw._qualifies(row, "bear") is False


def test_qualifies_false_score_high_no_raw_trigger_is_silence():
    """score 9 with NO raw trigger -> silence (RED-proof required by the build spec)."""
    row = _row(bear_score=9, bear_triggers_raw=[], verdict="HOLD")
    assert ebw._qualifies(row, "bear") is False


def test_qualifies_false_trigger_present_but_not_level_tied():
    """A non-level-tied trigger (e.g. pure ribbon_flip) must NOT qualify -- only the
    named level-tied triggers count."""
    row = _row(bear_score=9, bear_triggers_raw=["ribbon_flip"], verdict="HOLD")
    assert ebw._qualifies(row, "bear") is False


def test_qualifies_compatibility_old_shape_row_never_qualifies():
    """THE COMPATIBILITY TEST: a row shaped exactly like TODAY's real ledger (no
    bear_triggers_raw/bull_triggers_raw/bear_blockers/bull_blockers keys at all --
    pre-2026-07-28 shape) must not crash and must never qualify, on either side."""
    old_shape_row = {
        "ts_et": "2026-07-27T09:40:03", "account": "bold", "armed": True,
        "spy": 744.90, "ribbon": "BULL", "spread_cents": 40.0, "vix": 16.8,
        "htf_15m": "MIXED", "verdict": "HOLD", "side": None, "setup": None,
        "bear_score": 9, "bull_score": 9, "triggers": [],
        "reason": "no setup passed scoring (neither bear nor bull)",
        "trigger_level_exact": None, "shadow_triggers_fired": [],
    }
    assert ebw._qualifies(old_shape_row, "bear") is False
    assert ebw._qualifies(old_shape_row, "bull") is False


def test_qualifies_bull_uses_higher_threshold_and_its_own_trigger_set():
    assert ebw._qualifies(_row(bull_score=8, bull_triggers_raw=["level_reclaim"]), "bull") is False
    assert ebw._qualifies(_row(bull_score=9, bull_triggers_raw=["level_reclaim"]), "bull") is True
    assert ebw._qualifies(_row(bull_score=9, bull_triggers_raw=["ribbon_flip"]), "bull") is False


# --------------------------------------------------------------------------- #
# _read_new_rows -- byte-offset tail
# --------------------------------------------------------------------------- #
def test_read_new_rows_basic_tail(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [_row(ts_et="t1"), _row(ts_et="t2"), _row(ts_et="t3")])
    rows, offset, malformed = ebw._read_new_rows(p, 0)
    assert len(rows) == 3
    assert malformed == 0
    assert offset == p.stat().st_size
    # second read from the returned offset -> nothing new
    rows2, offset2, _ = ebw._read_new_rows(p, offset)
    assert rows2 == []
    assert offset2 == offset


def test_read_new_rows_holds_back_partial_trailing_line(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [_row(ts_et="t1")])
    complete_size = p.stat().st_size
    with p.open("a", encoding="utf-8") as f:
        f.write('{"ts_et": "t2", "account": "saf')  # mid-write, no trailing newline
    rows, offset, malformed = ebw._read_new_rows(p, 0)
    assert len(rows) == 1  # only t1 -- the partial line is held back
    assert malformed == 0
    assert offset == complete_size
    # finish the write -> next tick now sees it
    with p.open("a", encoding="utf-8") as f:
        f.write('e", "verdict": "HOLD"}\n')
    rows2, offset2, malformed2 = ebw._read_new_rows(p, offset)
    assert len(rows2) == 1
    assert rows2[0]["ts_et"] == "t2"
    assert malformed2 == 0


def test_read_new_rows_skips_malformed_and_advances_past_it(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    with p.open("w", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write(json.dumps(_row(ts_et="t2")) + "\n")
    rows, offset, malformed = ebw._read_new_rows(p, 0)
    assert len(rows) == 1
    assert rows[0]["ts_et"] == "t2"
    assert malformed == 1
    assert offset == p.stat().st_size
    # re-read from the new offset never re-surfaces the malformed line
    rows2, _, malformed2 = ebw._read_new_rows(p, offset)
    assert rows2 == []
    assert malformed2 == 0


def test_read_new_rows_missing_file_is_clean_noop(tmp_path):
    rows, offset, malformed = ebw._read_new_rows(tmp_path / "nope.jsonl", 5)
    assert (rows, offset, malformed) == ([], 5, 0)


def test_read_new_rows_rotation_resets_to_top(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [_row(ts_et="t1"), _row(ts_et="t2")])
    big_offset = p.stat().st_size + 500  # watermark points past a since-rotated/shrunk file
    _write_jsonl(p, [_row(ts_et="new1")])  # file "rotated" -- now much shorter
    rows, offset, _ = ebw._read_new_rows(p, big_offset)
    assert len(rows) == 1
    assert rows[0]["ts_et"] == "new1"


# --------------------------------------------------------------------------- #
# run_once -- debounce, exactly-one-alert, suppression, restart-safety
# --------------------------------------------------------------------------- #
@pytest.fixture()
def mock_delivery(monkeypatch):
    calls = {"speak": [], "deliver": [], "dashboard": []}
    monkeypatch.setattr(ebw, "_default_speak",
                         lambda text, out: (calls["speak"].append(text), (True, "ok"))[1])
    monkeypatch.setattr(ebw, "_default_deliver",
                         lambda content, wav, **kw: (calls["deliver"].append(content), {"queued": True})[1])
    monkeypatch.setattr(ebw, "_default_dashboard_update",
                         lambda text, side, account: calls["dashboard"].append((text, side, account)))
    return calls


def test_run_once_exactly_one_alert_after_debounce(tmp_path, mock_delivery, capsys):
    """RED-proof: score 9 + raw trigger + HOLD for 3 consecutive ticks -> exactly ONE alert."""
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    rows = [
        _row(ts_et=f"2026-07-28T09:4{i}:00", bear_score=9,
             bear_triggers_raw=["level_rejection", "confluence"], bear_blockers=[5], verdict="HOLD")
        for i in range(3)
    ]
    _write_jsonl(core, rows)
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert len(summary["alerts_fired"]) == 1
    assert len(mock_delivery["speak"]) == 1
    assert len(mock_delivery["deliver"]) == 1
    assert "ALERT" in capsys.readouterr().out


def test_run_once_single_tick_never_fires(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    _write_jsonl(core, [_row(bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD")])
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert summary["alerts_fired"] == []


def test_run_once_no_trigger_is_silence(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    rows = [_row(ts_et=f"t{i}", bear_score=9, bear_triggers_raw=[], verdict="HOLD") for i in range(6)]
    _write_jsonl(core, rows)
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert summary["alerts_fired"] == []
    assert mock_delivery["speak"] == []


def test_run_once_a_single_clear_tick_resets_predebounce_count(tmp_path, mock_delivery):
    """qualify, clear, qualify, qualify -- must NOT fire on the 3rd row (that's only
    the 2nd CONSECUTIVE qualifying tick after the reset, i.e. still needs one more)."""
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    q = dict(bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD")
    clear = dict(bear_score=9, bear_triggers_raw=[], verdict="HOLD")
    rows = [_row(ts_et="t0", **q), _row(ts_et="t1", **clear), _row(ts_et="t2", **q)]
    _write_jsonl(core, rows)
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert summary["alerts_fired"] == []  # only 1 consecutive qualifying tick since the reset


def test_run_once_malformed_rows_skipped_no_crash(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    with core.open("w", encoding="utf-8") as f:
        f.write("garbage not json\n")
        f.write(json.dumps(_row(bear_score=9, bear_triggers_raw=["level_rejection"])) + "\n")
        f.write("[]\n")  # valid JSON, not a dict -- also malformed for our purposes
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert summary["malformed_skipped"] == 2
    assert summary["rows_scanned"] == 1
    assert summary["alerts_fired"] == []  # only 1 qualifying tick, no crash either


def test_run_once_suppresses_4th_episode_with_logged_line(tmp_path, mock_delivery, capsys):
    """4 independent episodes in one day (safe:bear, safe:bull, bold:bear, bold:bull) --
    the 4th must be SUPPRESSED, not fired, with a logged SUPPRESSED line."""
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    qual = dict(bear_score=9, bear_triggers_raw=["level_rejection"],
                bull_score=10, bull_triggers_raw=["level_reclaim"], verdict="HOLD")
    rows = [
        _row(ts_et="t0", account="safe", **qual),
        _row(ts_et="t1", account="safe", **qual),   # safe:bear + safe:bull both fire here (alerts 1,2)
        _row(ts_et="t2", account="bold", **qual),
        _row(ts_et="t3", account="bold", **qual),   # bold:bear fires (alert 3), bold:bull SUPPRESSED
    ]
    _write_jsonl(core, rows)
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert len(summary["alerts_fired"]) == 3
    assert len(summary["suppressed"]) == 1
    assert "SUPPRESSED" in capsys.readouterr().out
    wm_data = json.loads(wm.read_text(encoding="utf-8"))
    assert wm_data["alerts_today"] == 3


def test_run_once_watermark_prevents_realert_on_restart(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    rows = [
        _row(ts_et="t0", bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD"),
        _row(ts_et="t1", bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD"),
    ]
    _write_jsonl(core, rows)
    first = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert len(first["alerts_fired"]) == 1

    # Simulate a process restart: fresh module state, same on-disk watermark + ledger,
    # no new rows appended. Must NOT re-alert.
    second = ebw.run_once(core_decisions_path=core, watermark_path=wm)
    assert second["alerts_fired"] == []
    assert second["rows_scanned"] == 0  # byte offset already past both rows


def test_run_once_dry_run_never_persists_or_delivers(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm = tmp_path / "wm.json"
    rows = [
        _row(ts_et="t0", bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD"),
        _row(ts_et="t1", bear_score=9, bear_triggers_raw=["level_rejection"], verdict="HOLD"),
    ]
    _write_jsonl(core, rows)
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm, dry_run=True)
    assert len(summary["alerts_fired"]) == 1  # still detected/reported
    assert mock_delivery["speak"] == []       # but never actually spoken
    assert not wm.exists()                    # and never persisted


def test_run_once_date_rollover_resets_daily_budget_not_byte_offset(tmp_path, mock_delivery):
    core = tmp_path / "core-decisions.jsonl"
    wm_path = tmp_path / "wm.json"
    _write_jsonl(core, [_row(ts_et="t0")])
    stale = {"schema": "entry-block-watch-v1", "byte_offset": core.stat().st_size,
              "date_et": "2026-07-01", "alerts_today": 3, "episodes": {"safe:bear": {
                  "consecutive_qualify": 1, "consecutive_clear": 0, "resolved": False}}}
    wm_path.write_text(json.dumps(stale), encoding="utf-8")
    summary = ebw.run_once(core_decisions_path=core, watermark_path=wm_path,
                            now_et=__import__("datetime").datetime(2026, 7, 28, 9, 40))
    assert summary["rows_scanned"] == 0  # byte_offset carried forward, not reset to 0
    reloaded = json.loads(wm_path.read_text(encoding="utf-8"))
    assert reloaded["date_et"] == "2026-07-28"
    assert reloaded["alerts_today"] == 0
    assert reloaded["episodes"] == {}


# --------------------------------------------------------------------------- #
# compose_alert_text -- readable, never crashes on sparse rows
# --------------------------------------------------------------------------- #
def test_compose_alert_text_includes_score_triggers_and_blocker():
    row = _row(bear_score=9, bear_triggers_raw=["level_rejection", "confluence"],
                bear_blockers=[5], verdict="HOLD", account="safe", spy=744.90, levels_active=[])
    text = ebw.compose_alert_text(row, "bear")
    assert "9 out of 10 bear" in text
    assert "level rejection plus confluence" in text
    assert "ribbon" in text
    assert "Safe" in text
    # COPY DRIFT FIXED 2026-09-02. This line used to assert "say the word to arm it".
    # That phrasing was REMOVED from the composer on 2026-08-31 after J heard it read
    # back -- "why am i being asked to arm anything??" -- because a paper gate refusing a
    # setup is not one of OP-0's four J-routed things, and OP-11 names soliciting
    # permission to ship a cleared edge as the banned anti-pattern. A dedicated guard,
    # test_no_permission_framing_in_alerts_2026_08_31.py, now asserts that phrase is
    # ABSENT -- so this assertion was directly CONTRADICTING that guard and demanding the
    # exact anti-pattern J rejected. Assert the alert's real job instead: REPORT the
    # refusal, never shop for an override.
    assert "Logged for gate review" in text
    assert "no action needed from you" in text
    assert "arm it" not in text, "the alert must never ask J to arm paper work"


def test_compose_alert_text_handles_missing_level_and_blockers_gracefully():
    row = {"account": "bold", "bear_score": 8, "bear_triggers_raw": ["confluence"], "verdict": "HOLD"}
    text = ebw.compose_alert_text(row, "bear")
    assert "8 out of 10 bear" in text
    assert "Bold" in text
    assert "lost routing" in text  # no blockers key at all -> graceful fallback phrase
