"""Market-clock gate on the tickers executor pass (2026-09-04).

The static invariants check weekday() only; Monday 2026-09-07 is Labor Day. The pass must ask
the BROKER's clock: closed -> one MARKET_CLOSED row per arm and no arm runs; open -> arms run;
unreadable -> arms still run (bounded by the weekday/window invariants) and the ledger says so.
The shadow E2E probe bypasses the gate because it runs off-hours by design.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import execute as mx  # noqa: E402
from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402

ARMS = ["tickers-1", "tickers-2", "tickers-3"]


class _Creds:
    key = "k"
    secret = "s"
    base_url = "https://paper-api.alpaca.markets"
    account_number = ""


@pytest.fixture
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(mx, "TICKERS_STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mx, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(mx, "E2E_PROBE_ROOT", None)
    params = json.loads((REPO / "automation" / "state" / "tickers" / "params.json").read_text(encoding="utf-8"))
    p = tmp_path / "params.json"
    p.write_text(json.dumps(params), encoding="utf-8")
    monkeypatch.setattr(mx, "precheck_creds", lambda key_source, arm: None)
    monkeypatch.setattr(mx, "load_pinned_account", lambda arm: "")
    monkeypatch.setattr(mc, "resolve", lambda params: _Creds())
    calls = {"run_arm": 0, "bars": 0}

    def _run_arm(arm, lane_params, bars, attention, *, shadow, deadline):
        calls["run_arm"] += 1
        return {"arm": arm, "acct": "PA", "equity": 1.0, "open": 0, "would_place": 0,
                "placed": 0, "exits": 0, "kill": False, "creds": "ok"}

    def _bars(*a, **k):
        calls["bars"] += 1
        return {}

    monkeypatch.setattr(mx, "run_arm", _run_arm)
    monkeypatch.setattr(mx.core, "fetch_bars_batch", _bars)
    monkeypatch.setattr(mx.core, "merge_scanner_attention", lambda base, params, creds: dict(base or {}))
    monkeypatch.setattr(mx.core, "attention_from_bars", lambda bars: {})
    return {"params": p, "calls": calls, "root": tmp_path}


def _rows(arm: str) -> list:
    p = mx.arm_ledger_path(arm)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_closed_market_writes_one_row_per_arm_and_runs_nothing(lane, monkeypatch):
    monkeypatch.setattr(mb, "get_clock", lambda creds: {"is_open": False, "next_open": "2026-09-08T13:30:00Z",
                                                        "next_close": "2026-09-08T20:00:00Z"})
    rc = mx.run_once(ARMS, lane["params"], shadow=True)
    assert rc == 0
    assert lane["calls"]["run_arm"] == 0 and lane["calls"]["bars"] == 0
    for arm in ARMS:
        rows = _rows(arm)
        assert [r["decision"] for r in rows] == ["MARKET_CLOSED"]
        assert "is_open=False" in rows[0]["reason"] and rows[0]["scorer"] == "production"


def test_open_market_runs_every_arm(lane, monkeypatch):
    monkeypatch.setattr(mb, "get_clock", lambda creds: {"is_open": True, "next_open": "x", "next_close": "y"})
    assert mx.run_once(ARMS, lane["params"], shadow=True) == 0
    assert lane["calls"]["run_arm"] == 3
    assert all(not _rows(a) for a in ARMS)  # the stubbed run_arm writes nothing; no gate rows


def test_unreadable_clock_proceeds_and_discloses(lane, monkeypatch):
    def _boom(creds):
        raise mb.BrokerAPIError("GET /v2/clock: 503")
    monkeypatch.setattr(mb, "get_clock", _boom)
    assert mx.run_once(ARMS, lane["params"], shadow=True) == 0
    assert lane["calls"]["run_arm"] == 3
    for arm in ARMS:
        assert [r["decision"] for r in _rows(arm)] == ["CLOCK_READ_ERROR"]


def test_probe_bypasses_the_gate(lane, monkeypatch, capsys):
    monkeypatch.setattr(mx, "E2E_PROBE_ROOT", lane["root"])
    monkeypatch.setattr(mb, "get_clock", lambda creds: (_ for _ in ()).throw(AssertionError("clock must not be read in probe mode")))
    assert mx.run_once(ARMS, lane["params"], shadow=True) == 0
    assert lane["calls"]["run_arm"] == 3
    assert "market-clock gate BYPASSED" in capsys.readouterr().err


def test_market_is_open_classifies():
    class _C:  # noqa: D401 -- stub creds
        pass
    import multi.execute as m
    m_get = mb.get_clock
    try:
        mb.get_clock = lambda creds: {"is_open": True, "next_open": "a", "next_close": "b"}
        assert m.market_is_open(_C())[0] is True
        mb.get_clock = lambda creds: {"is_open": False}
        assert m.market_is_open(_C())[0] is False
        def _err(creds):
            raise mb.BrokerAPIError("down")
        mb.get_clock = _err
        is_open, why = m.market_is_open(_C())
        assert is_open is None and "BrokerAPIError" in why
    finally:
        mb.get_clock = m_get
