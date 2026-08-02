"""NBBO CAPTURE guard (2026-07-20, queue: PROFIT-P4-NBBO-CAPTURE).

Problem: the friction stream had NO option bid/ask history anywhere -- the ledger's
spread_cents field is the SPY EMA-ribbon spread (NOT an option quote), and
bid_ask_spread_max_cents was a confirmed dead knob with zero consumers. _execute now
reconstructs bid/ask/mid/spread from the SAME mid + entry_px it already priced the entry
off of (get_option_mid + marketable_limit_price) and threads it onto plan["nbbo"] --
purely additive telemetry, NO new network call on the entry-critical path.

Run: backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_nbbo_capture_2026_07_20.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


def _verdict():
    return {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "triggers_fired": ["level_rejection"]}


def _payload():
    return {"bar_ctx": {"timestamp_et": "2026-07-20 10:55:00", "bar": {"close": 620.0}}}


def _wire_common_broker(hc, monkeypatch, *, mid: float, entry_px: float):
    """Mirrors test_audit_fix_heartbeat.py's TestFillReconciliation wiring exactly --
    mocks ONLY get_option_mid + marketable_limit_price (never get_option_quote_hilo),
    proving the NBBO capture makes ZERO extra network calls on this path."""
    import fleet_broker as fb
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "open_spy_option_positions", lambda c: [])
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: mid)
    monkeypatch.setattr(fb, "marketable_limit_price",
                        lambda c, s, side="buy", buffer=0.03: entry_px)
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    # ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02): this file is about NBBO capture, not the
    # guard -- stub its two broker primitives to "confirmed clear" (see
    # test_core_entry_idempotency_guard_2026_08_02.py for the guard's own dedicated
    # coverage). hc.STATE is already sandboxed to tmp_path below, which is where the guard's
    # claim file lives too -- no extra wiring needed.
    monkeypatch.setattr(fb, "open_buy_orders_checked", lambda c, s: ([], True))
    monkeypatch.setattr(fb, "symbol_position_qty_checked", lambda c, s: (0, True))
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 20, 10, 55))

    class _Resp:
        def read(self):
            return json.dumps({"equity": "2000.0"}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())


def test_dry_plan_carries_reconstructed_nbbo(hc, monkeypatch):
    """dry=True (WOULD_PLACE) path: mid=1.00, entry_px=1.08, buffer=0.03 (explicit local pin,
    independent of whatever automation/state/params.json's live entry_cross_buffer default
    is today -- 2026-08-02 ship changed the live default to 0.015; this test's whole point is
    the bit-exact NBBO INVERSION arithmetic, not the live buffer value, so it pins its own
    buffer rather than silently drifting whenever that default is retuned, mirroring
    test_nbbo_respects_custom_entry_cross_buffer's own explicit-override pattern below) ->
    ask=entry_px-buffer=1.05, bid=2*mid-ask=0.95, spread=0.10. Bit-exact reconstruction."""
    _wire_common_broker(hc, monkeypatch, mid=1.00, entry_px=1.08)
    params = dict(SAFE_PARAMS, entry_cross_buffer=0.03)
    plan = hc._execute("safe", _verdict(), _payload(), params, dry=True)
    assert plan["status"] == "WOULD_PLACE"
    assert plan["nbbo"] == {"bid": 0.95, "ask": 1.05, "mid": 1.00, "spread": 0.10}


def test_nbbo_respects_custom_entry_cross_buffer(hc, monkeypatch):
    """A non-default entry_cross_buffer must still invert correctly (not hardcode 0.03)."""
    _wire_common_broker(hc, monkeypatch, mid=2.00, entry_px=2.20)
    params = dict(SAFE_PARAMS, entry_cross_buffer=0.10)
    plan = hc._execute("safe", _verdict(), _payload(), params, dry=True)
    assert plan["nbbo"]["ask"] == pytest.approx(2.10)   # entry_px(2.20) - buffer(0.10)
    assert plan["nbbo"]["bid"] == pytest.approx(1.90)   # 2*mid(2.00) - ask(2.10)
    assert plan["nbbo"]["mid"] == 2.00
    assert plan["nbbo"]["spread"] == pytest.approx(0.20)


def test_nbbo_reconstruction_uses_zero_new_network_calls(hc, monkeypatch):
    """get_option_quote_hilo (the 3rd/independent quote endpoint) must NEVER be called by
    _execute -- if a future edit adds a real 3rd fetch for NBBO, this goes RED immediately."""
    import fleet_broker as fb
    _wire_common_broker(hc, monkeypatch, mid=1.00, entry_px=1.08)

    def _boom(*a, **k):
        pytest.fail("_execute must not call get_option_quote_hilo -- NBBO is reconstructed "
                    "from mid/entry_px, not a fresh fetch")
    monkeypatch.setattr(fb, "get_option_quote_hilo", _boom)
    plan = hc._execute("safe", _verdict(), _payload(), SAFE_PARAMS, dry=True)
    assert plan["status"] == "WOULD_PLACE"
    assert plan["nbbo"]["mid"] == 1.00


def test_placed_entry_carries_nbbo_into_the_persisted_broker_row(hc, monkeypatch, tmp_path):
    """End-to-end (dry=False, PLACED): plan['nbbo'] survives into the row that would be
    logged to core-decisions.jsonl -- the exact surface run_account persists via rec['exec'].
    Pins an explicit local entry_cross_buffer=0.03 (see test_dry_plan_carries_reconstructed_
    nbbo's docstring above -- decoupled from the live params.json default, which the
    2026-08-02 ship changed to 0.015) so this test keeps proving the persistence path, not
    re-deriving the live buffer value."""
    import fleet_broker as fb
    seq = {"n": 0}

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        if method == "POST":
            return {"id": "ord-nbbo-1", "status": "pending_new", "filled_qty": "0"}
        seq["n"] += 1
        if seq["n"] == 1:
            return {"id": "ord-nbbo-1", "status": "pending_new", "filled_qty": "0"}
        return {"id": "ord-nbbo-1", "status": "filled", "filled_qty": "3",
                "filled_avg_price": "1.09"}

    monkeypatch.setattr(fb, "_request", fake_request)
    _wire_common_broker(hc, monkeypatch, mid=1.00, entry_px=1.08)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    _real_reconcile = hc._reconcile_fill
    monkeypatch.setattr(hc, "_reconcile_fill",
                        lambda creds, order, **k: _real_reconcile(creds, order, sleep_s=0.0))
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        types.SimpleNamespace(register_entry=lambda *a, **k: None,
                                              load_states=lambda arm: {}))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    params = dict(SAFE_PARAMS, entry_cross_buffer=0.03)
    plan = hc._reconcile_exec(hc._execute("safe", _verdict(), _payload(), params, dry=False))
    assert plan["status"] == "PLACED"
    assert plan["nbbo"] == {"bid": 0.95, "ask": 1.05, "mid": 1.00, "spread": 0.10}
    # JSON-native (the persisted-row constraint _reconcile_exec's own docstring calls out).
    json.dumps(plan["nbbo"])


def test_no_premium_short_circuit_never_computes_nbbo(hc, monkeypatch):
    """No two-sided quote -> NO_PREMIUM, same as before this change; nbbo key absent
    (never a None-valued key masquerading as real telemetry)."""
    _wire_common_broker(hc, monkeypatch, mid=0.0, entry_px=0.0)
    plan = hc._execute("safe", _verdict(), _payload(), SAFE_PARAMS, dry=True)
    assert plan["status"] == "NO_PREMIUM"
    assert "nbbo" not in plan
