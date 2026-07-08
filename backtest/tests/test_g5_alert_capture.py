"""Guard: G5 alert/capture flywheel (2026-07-08 Fable gap-audit).

Three legs: (1) the discord bridge delivers BOTH outbox schemas (content + message) so
self_check/spend_summary alerts stop dropping; (2) level_memory pings J on a high-memory-level
rejection; (3) j_call_capture appends validated J-call anchors. All notify/log-only, no
trading path.

Run: cd backtest && python -m pytest tests/test_g5_alert_capture.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
WATCHERS = REPO / "backtest" / "lib" / "watchers"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# --- 1. bridge accepts both content + message schemas (static pin of the 1-line fix) ---
def test_bridge_accepts_message_schema():
    src = (SCRIPTS / "discord-bridge.py").read_text(encoding="utf-8")
    assert 'row.get("content") or row.get("message")' in src, (
        "drain_outbox must fall back to `message` else self_check/spend_summary alerts drop")


# --- 2. level_memory reject alert ---
def _lm():
    return _load("level_memory", WATCHERS / "level_memory.py")


def _snap(lm, kind: str, memory: float):
    import pandas as pd
    lvl = lm.Level(price=750.90, role="resistance", memory_score=memory, touches=9, wicks=4,
                   bars_consolidated=20, role_flips=2, first_seen_idx=0, last_touch_idx=5)
    it = lm.Interaction(kind=kind, level=lvl, distance=-0.3, detail="wick rejection")
    return lm.Snapshot(idx=10, timestamp_et=pd.Timestamp("2026-07-07 09:45"), close=750.6,
                       levels=(lvl,), nearest=lvl, interaction=it)


def test_reject_alert_fires_on_high_memory():
    lm = _lm()
    msg = lm.format_reject_alert(_snap(lm, "reject", 5.0))
    assert msg and "REJECT" in msg and "750.90" in msg


def test_no_alert_on_touch_or_low_memory():
    lm = _lm()
    assert lm.format_reject_alert(_snap(lm, "touch", 5.0)) is None            # not a reject
    assert lm.format_reject_alert(_snap(lm, "reject", 1.0)) is None           # below ALERT_MIN_MEMORY


def test_emit_writes_delivered_outbox_row(tmp_path):
    lm = _lm()
    ob = tmp_path / "outbox.jsonl"
    assert lm.emit_reject_alert(_snap(lm, "reject", 5.0), ob) is True
    row = json.loads(ob.read_text(encoding="utf-8").strip())
    assert "content" in row and "REJECT" in row["content"]                    # the delivered schema


# --- 3. j_call_capture ---
def _jc():
    return _load("j_call_capture", SCRIPTS / "j_call_capture.py")


def test_capture_writes_valid_anchor(tmp_path):
    jc = _jc()
    p = tmp_path / "anchors.jsonl"
    row = jc.capture({"ts_et": "2026-07-07T09:45", "source": "chat", "symbol": "spy",
                      "side": "put", "level": 750.9, "thesis": "reject the 750 shelf"}, path=p)
    assert row["symbol"] == "SPY" and row["side"] == "put" and row["call_id"].startswith("jc_")
    assert json.loads(p.read_text(encoding="utf-8").strip())["level"] == 750.9


def test_capture_rejects_malformed():
    jc = _jc()
    with pytest.raises(ValueError):
        jc.validate({"source": "chat", "symbol": "SPY", "side": "put"})       # missing ts_et + thesis
    with pytest.raises(ValueError):
        jc.validate({"ts_et": "x", "source": "chat", "symbol": "SPY",
                     "side": "sideways", "thesis": "t"})                       # bad side
