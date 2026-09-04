"""Guards for multi/execute.py -- the TICKERS LANE's ARMED paper executor.

NO NETWORK ANYWHERE IN THIS FILE. Every test monkeypatches `execute.mc.resolve` /
`execute.mc.verify_account` (creds) and `execute.core.tick` plus the relevant
`execute.mb.*` broker functions (place_bracket / market_sell / poll_fill /
equity_option_positions) with local stand-ins; `execute.TICKERS_STATE_DIR` /
`execute.JOURNAL_DIR` / `execute.STATUS_PATH` are redirected to a pytest tmp_path so nothing
here ever touches real repo state. Most tests call `execute.run_arm(...)` directly (the
per-arm entry point) rather than `run_once`/`main`, since run_arm needs no shared bar fetch.

Prereg this build answers to: analysis/recommendations/prereg-tickers-lane-production-scorer-
2026-09-04.json. Invariants brief: this lane's day-one clamps are qty EXACTLY 3
(min_contracts==max_contracts==3), 1 concurrent position, 1% daily kill (blocks entries only),
09:35-14:30 ET entry window, SPY forbidden in every universe and on every acted-on contract.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from multi import execute  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import exits as mex  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402

# A Friday within the 09:30-15:00 ET static-invariant window, matching the prereg's own date.
FIXED_NOW = dt.datetime(2026, 9, 4, 10, 0, 0)
assert FIXED_NOW.weekday() == 4, "sanity: 2026-09-04 must be a weekday for these fixtures"

BASE_LANE_PARAMS = {
    "arm": "tickers",
    "shadow_only": False,
    "scorer": "production",
    "risk": {
        "max_contracts": 3, "min_contracts": 3, "max_concurrent_positions": 1,
        "daily_loss_kill_switch_pct": 0.01,
    },
    "exits": {"tp1_premium_pct": 45.0, "catastrophe_stop_pct": -50.0},
    "tick_cadence": {"minutes": 2, "first_tick_et": "09:35", "last_entry_et": "14:30"},
    "arms": {
        "tickers-1": {"key_source": "tickers-1", "account_number": "", "universe": ["NVDA", "AAPL", "AMZN"]},
        "tickers-2": {"key_source": "tickers-2", "account_number": "", "universe": ["TSLA", "META", "AVGO"]},
        "tickers-3": {"key_source": "tickers-3", "account_number": "", "universe": ["QQQ", "IWM", "GLD"]},
    },
}


def _lane_params(**overrides) -> dict:
    p = copy.deepcopy(BASE_LANE_PARAMS)
    p.update(overrides)
    return p


def _entry_row(contract: str, *, symbol="NVDA", side="C", qty=3, ask=1.50, mid=1.45,
               spot=500.0, expiry="2026-09-04", spread_pct=2.0) -> dict:
    return {"decision": "WOULD_PLACE", "contract": contract, "symbol": symbol, "side": side,
            "qty": qty, "ask": ask, "mid": mid, "spot": spot, "expiry": expiry,
            "spread_pct": spread_pct}


def _exit_row(contract: str, symbol: str, decision: str, *, qty_to_close=None,
              bid=1.0, ask=1.05, stage="theta_budget") -> dict:
    row = {"kind": "exit_eval", "contract": contract, "symbol": symbol, "decision": decision,
           "stage": stage, "bid": bid, "ask": ask}
    if qty_to_close is not None:
        row["qty_to_close"] = qty_to_close
    return row


def _seed_position(arm: str, contract: str, **kw) -> mps.PositionRecord:
    defaults = dict(symbol="NVDA", contract=contract, side="C", entry_premium=1.0,
                    entry_underlying_price=500.0, qty=3, entry_session_date="2026-09-04",
                    expiry="2026-09-04", hwm_premium=1.0, strategy="production_ribbon_ride")
    defaults.update(kw)
    rec = mps.PositionRecord(**defaults)
    state_path = execute.arm_state_path(arm)
    mps.ensure_initialized(path=state_path)
    mps.save_state({contract: rec}, path=state_path)
    return rec


def _write_secrets(state_dir: Path, arms=("tickers-1", "tickers-2", "tickers-3"), *, placeholder=False) -> None:
    accounts = {}
    for i, a in enumerate(arms, start=1):
        if placeholder:
            accounts[a] = {"key": "<PASTE Tickers KEY>", "secret": "<PASTE SECRET>",
                           "base_url": "https://paper-api.alpaca.markets"}
        else:
            accounts[a] = {"key": f"PKTEST{i}KEY", "secret": f"TESTSECRET{i}",
                           "base_url": "https://paper-api.alpaca.markets"}
    (state_dir / "secrets.json").write_text(json.dumps({"accounts": accounts}), encoding="utf-8")


def _read_ledger(arm: str) -> list[dict]:
    p = execute.arm_ledger_path(arm)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decisions(arm: str, decision: str) -> list[dict]:
    return [r for r in _read_ledger(arm) if r.get("decision") == decision]


def _stub_resolve(params: dict) -> mc.MultiCreds:
    """Mirrors the REAL creds.resolve()'s contract (echoes account.account_number back onto
    the returned creds) without any file/network I/O."""
    acct = params.get("account") or {}
    return mc.MultiCreds(key="FAKEKEY", secret="FAKESECRET",
                         base_url="https://paper-api.alpaca.markets",
                         account_number=str(acct.get("account_number") or ""),
                         source=f"test:{acct.get('key_source')}")


def _stub_verify_account(resolved_number="PA_RESOLVED", equity=100000.0):
    def _fn(creds: mc.MultiCreds) -> dict:
        if creds.account_number and creds.account_number != resolved_number:
            raise mc.CredError(
                f"ACCOUNT MISMATCH: params.json says {creds.account_number} but the resolved "
                f"key authenticates as {resolved_number}. Refusing to proceed.")
        return {"account_number": resolved_number, "equity": equity, "buying_power": equity,
                "options_approved_level": 3, "status": "ACTIVE"}
    return _fn


def _recording_broker(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patches execute.mb.place_bracket / market_sell / poll_fill / equity_option_positions
    with recording stand-ins that reuse the REAL _gate_submission shadow/armed interlock (so
    the shadow-preview shape and the ShadowModeError interlock behave exactly as broker.py's
    real functions do), never reaching execute.mb._request."""
    calls = {"place_bracket": [], "market_sell": []}

    def fake_place_bracket(creds, *, symbol, qty, limit_price, take_profit_price, stop_price,
                           armed=False, simple_fallback=False, params=None):
        calls["place_bracket"].append({"symbol": symbol, "qty": qty, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"symbol": symbol, "qty": qty}, params=params)
        if preview is not None:
            return preview
        return {"id": "order-entry-1", "status": "accepted"}

    def fake_market_sell(creds, *, symbol, qty, armed=False, params=None):
        calls["market_sell"].append({"symbol": symbol, "qty": qty, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"symbol": symbol, "qty": qty}, params=params)
        if preview is not None:
            return preview
        return {"id": "order-exit-1", "status": "accepted"}

    def fake_poll_fill(creds, order_id, *, attempts=3, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": 3, "filled_avg_price": 1.60, "order": {}}

    def fake_equity_option_positions(creds, *, allowed_roots=None):
        return []

    monkeypatch.setattr(execute.mb, "place_bracket", fake_place_bracket)
    monkeypatch.setattr(execute.mb, "market_sell", fake_market_sell)
    monkeypatch.setattr(execute.mb, "poll_fill", fake_poll_fill)
    monkeypatch.setattr(execute.mb, "equity_option_positions", fake_equity_option_positions)
    return calls


@pytest.fixture
def state_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "tickers"
    d.mkdir()
    monkeypatch.setattr(execute, "TICKERS_STATE_DIR", d)
    monkeypatch.setattr(execute, "JOURNAL_DIR", tmp_path / "journal")
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n", encoding="utf-8")
    monkeypatch.setattr(execute, "STATUS_PATH", status_path)
    monkeypatch.setattr(execute, "now_et", lambda: FIXED_NOW)
    monkeypatch.setattr(execute.mc, "resolve", _stub_resolve)
    monkeypatch.setattr(execute.mc, "verify_account", _stub_verify_account())
    return d


def _deadline() -> float:
    return time.monotonic() + 60.0


# =============================================================================================
# 1. --shadow: armed=False only, no _request POST ever happens
# =============================================================================================
def test_shadow_flag_constructs_and_logs_but_never_sends(state_dir, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("execute.mb._request was called during --shadow -- a real POST was attempted")
    monkeypatch.setattr(execute.mb, "_request", _boom)
    monkeypatch.setattr(execute.mb, "poll_fill",
                        lambda *a, **kw: pytest.fail("poll_fill must never run in shadow mode"))
    monkeypatch.setattr(execute.mb, "equity_option_positions", lambda creds, allowed_roots=None: [])

    exit_contract = "NVDA260904C00490000"
    _seed_position("tickers-1", exit_contract, entry_premium=1.0, hwm_premium=1.0)
    rows = [
        _entry_row("NVDA260904C00510000", qty=3),
        _exit_row(exit_contract, "NVDA", mex.ACTION_SELL_ALL, qty_to_close=3, bid=2.0, ask=2.05, stage="tp1"),
    ]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=True, deadline=_deadline())

    assert summary["creds"] == "ok"
    entry_previews = _decisions("tickers-1", "SHADOW_ENTRY_PREVIEW")
    exit_previews = _decisions("tickers-1", "SHADOW_EXIT_PREVIEW")
    assert len(entry_previews) == 1, _read_ledger("tickers-1")
    assert len(exit_previews) == 1, _read_ledger("tickers-1")
    for row in entry_previews + exit_previews:
        assert row["armed"] is False
        assert row["shadow"] is True


# =============================================================================================
# 2. shadow_only:true + armed=True -> ShadowModeError caught per row, logged, execution continues
# =============================================================================================
def test_shadow_only_interlock_is_caught_and_logged(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    contract = "AAPL260904C00220000"
    rows = [_entry_row(contract, symbol="AAPL", qty=3)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    lp = _lane_params(shadow_only=True)  # armed=True (shadow=False) but lane says shadow_only
    summary = execute.run_arm("tickers-1", lp, {}, {}, shadow=False, deadline=_deadline())

    assert summary["creds"] == "ok"
    interlocked = _decisions("tickers-1", "SHADOW_ONLY_INTERLOCK")
    assert len(interlocked) == 1, _read_ledger("tickers-1")
    # the call WAS attempted with armed=True (that's what tripped the interlock) but nothing filled
    assert calls["place_bracket"][0]["armed"] is True
    assert summary["placed"] == 0


# =============================================================================================
# 3. qty clamp
# =============================================================================================
def test_qty_47_clamps_to_max_contracts_3(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    contract = "AMZN260904C00190000"
    rows = [_entry_row(contract, symbol="AMZN", qty=47)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(calls["place_bracket"]) == 1
    assert calls["place_bracket"][0]["qty"] == 3
    assert summary["placed"] == 1


def test_qty_2_is_below_min_and_never_placed(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    contract = "AMZN260904C00195000"
    rows = [_entry_row(contract, symbol="AMZN", qty=2)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert calls["place_bracket"] == []
    assert len(_decisions("tickers-1", "SIZE_BELOW_MIN")) == 1
    assert summary["placed"] == 0


# =============================================================================================
# 4. SPY refusal -- universe config AND foreign-contract exit safety net
# =============================================================================================
def test_universe_containing_spy_aborts_the_arm(state_dir, monkeypatch):
    _write_secrets(state_dir, arms=["tickers-1"])
    lp = _lane_params()
    lp["arms"]["tickers-1"]["universe"] = ["SPY", "NVDA"]

    summary = execute.run_arm("tickers-1", lp, {}, {}, shadow=False, deadline=_deadline())

    fails = _decisions("tickers-1", "INVARIANT_FAIL")
    assert len(fails) == 1
    assert fails[0]["code"] == "universe_contains_spy"
    assert summary["creds"] == "NO_CREDS"  # aborted before creds were ever touched


def test_foreign_spy_contract_in_exit_row_is_never_sold(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    spy_contract = "SPY260904C00773000"
    # tickers-1's OWN universe (NVDA/AAPL/AMZN) never contains SPY; this exit row simulates a
    # corrupted/foreign state entry naming a SPY contract regardless.
    rows = [_exit_row(spy_contract, "SPY", mex.ACTION_SELL_ALL, qty_to_close=3, bid=5.0, ask=5.05)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert calls["market_sell"] == []
    ignored = _decisions("tickers-1", "FOREIGN_CONTRACT_IGNORED")
    assert len(ignored) == 1
    assert ignored[0]["contract"] == spy_contract


# =============================================================================================
# 5. NO_CREDS self-heal
# =============================================================================================
def test_missing_secrets_file_logs_no_creds_and_exits_0_other_arms_still_run(state_dir, monkeypatch):
    # NOTE: no _write_secrets() call -- secrets.json does not exist at all.
    params_path = state_dir.parent / "params.json"
    params_path.write_text(json.dumps(_lane_params()), encoding="utf-8")

    rc = execute.run_once(list(execute.ARM_NAMES), params_path, shadow=False)

    assert rc == 0
    for arm in execute.ARM_NAMES:
        rows = _decisions(arm, "NO_CREDS")
        assert len(rows) == 1, f"{arm}: expected exactly one NO_CREDS row, got {_read_ledger(arm)}"


# =============================================================================================
# 6. account pin mismatch
# =============================================================================================
def test_account_pin_mismatch_blocks_all_orders(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    # Pin says PA_OLD; the (stubbed) broker resolves PA_NEW -- must refuse, never trade.
    (state_dir / "tickers-1").mkdir(parents=True, exist_ok=True)
    (state_dir / "tickers-1" / "account.json").write_text(
        json.dumps({"account_number": "PA_OLD", "equity_at_pin": 100000.0,
                    "pinned_at_et": FIXED_NOW.isoformat()}), encoding="utf-8")
    monkeypatch.setattr(execute.mc, "verify_account", _stub_verify_account(resolved_number="PA_NEW"))

    rows = [_entry_row("NVDA260904C00500000", qty=3)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-1", "ACCOUNT_PIN_MISMATCH")) == 1
    assert calls["place_bracket"] == [] and calls["market_sell"] == []
    assert summary["placed"] == 0


# =============================================================================================
# 7. kill switch -- blocks entries, exits still act
# =============================================================================================
def test_kill_switch_blocks_entries_but_exits_still_act(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    exit_contract = "TSLA260904C00250000"
    _seed_position("tickers-2", exit_contract, symbol="TSLA", entry_premium=2.0, hwm_premium=2.0)

    # day file: realized -1.1% of a $100k start-of-day equity; kill pct is 1% -> tripped
    day_path = execute.arm_day_path("tickers-2", FIXED_NOW.date().isoformat())
    execute.save_day_file(day_path, {
        "date": FIXED_NOW.date().isoformat(), "arm": "tickers-2",
        "start_of_day_equity": 100000.0, "realized_pnl_today": -1100.0,
        "kill_tripped": False, "fills": [],
    })

    rows = [
        _entry_row("TSLA260904C00260000", symbol="TSLA", qty=3),
        _exit_row(exit_contract, "TSLA", mex.ACTION_SELL_ALL, qty_to_close=3, bid=3.0, ask=3.05, stage="tp1"),
    ]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-2"])

    summary = execute.run_arm("tickers-2", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert summary["kill"] is True
    assert len(_decisions("tickers-2", "KILL_BLOCKED")) == 1
    assert calls["place_bracket"] == []
    assert len(calls["market_sell"]) == 1  # exits still act despite the kill switch
    assert summary["exits"] == 1


# =============================================================================================
# 8. entry window
# =============================================================================================
@pytest.mark.parametrize("hhmm,blocked", [("14:31", True), ("14:29", False)])
def test_entry_window(state_dir, monkeypatch, hhmm, blocked):
    hh, mm = (int(x) for x in hhmm.split(":"))
    monkeypatch.setattr(execute, "now_et", lambda: FIXED_NOW.replace(hour=hh, minute=mm))
    calls = _recording_broker(monkeypatch)
    contract = "QQQ260904C00600000"
    rows = [_entry_row(contract, symbol="QQQ", qty=3)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-3"])

    summary = execute.run_arm("tickers-3", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    if blocked:
        assert calls["place_bracket"] == []
        assert len(_decisions("tickers-3", "ENTRY_WINDOW_CLOSED")) == 1
        assert summary["placed"] == 0
    else:
        assert len(calls["place_bracket"]) == 1
        assert summary["placed"] == 1


# =============================================================================================
# 9. first-fill STATUS.md line, written once
# =============================================================================================
def test_first_fill_status_line_written_once(state_dir, monkeypatch):
    _recording_broker(monkeypatch)
    contract1 = "NVDA260904C00500000"
    contract2 = "AAPL260904C00220000"
    rows1 = [_entry_row(contract1, symbol="NVDA", qty=3)]
    rows2 = [_entry_row(contract2, symbol="AAPL", qty=3)]
    _write_secrets(state_dir, arms=["tickers-1"])

    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows1, Counter()))
    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())
    status_text_1 = execute.STATUS_PATH.read_text(encoding="utf-8")
    assert status_text_1.count("TICKERS-LANE FIRST FILL") == 1
    assert execute.first_fill_marker_path().exists()

    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows2, Counter()))
    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())
    status_text_2 = execute.STATUS_PATH.read_text(encoding="utf-8")
    assert status_text_2.count("TICKERS-LANE FIRST FILL") == 1, "a second fill must not add a second line"


# =============================================================================================
# 10. paper-only invariant
# =============================================================================================
def test_non_paper_base_url_aborts_as_invariant_fail(state_dir, monkeypatch):
    def _raise_non_paper(params):
        raise mc.CredError(
            "multi lane resolved a NON-PAPER base_url (https://api.alpaca.markets). This lane "
            "is shadow/paper only; arming live money is a J decision and is not reachable here.")
    monkeypatch.setattr(execute.mc, "resolve", _raise_non_paper)
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    fails = _decisions("tickers-1", "INVARIANT_FAIL")
    assert len(fails) == 1
    assert fails[0]["code"] == "paper_only"
    assert summary["creds"] == "NO_CREDS"


# --- E2E SHADOW PROBE flag (added 2026-09-04 01:5x ET) -------------------------------------
def test_e2e_probe_root_refused_without_shadow(capsys):
    """The probe borrows a real paper key and ignores the session window -- it must be
    structurally impossible to run it armed."""
    import multi.execute as ex
    with pytest.raises(SystemExit) as ei:
        ex.main(["--once", "--e2e-probe-root", "C:/nope"])
    assert ei.value.code == 2
    assert "requires --shadow" in capsys.readouterr().err


def test_e2e_probe_root_redirects_every_per_arm_path(tmp_path, monkeypatch):
    """Under the probe no path may point at the REAL automation/state/tickers or journal/."""
    import multi.execute as ex
    monkeypatch.setattr(ex, "run_once", lambda arms, p, shadow=False: 0)
    ex.main(["--once", "--shadow", "--e2e-probe-root", str(tmp_path)])
    for fn in (ex.arm_dir, ex.arm_state_path, ex.arm_ledger_path, ex.arm_account_pin_path, ex.arm_journal_path):
        assert str(fn("tickers-1")).startswith(str(tmp_path.resolve())), fn.__name__
    assert str(ex.first_fill_marker_path()).startswith(str(tmp_path.resolve()))
    assert ex.effective_key_source({"key_source": "tickers-1"}) == "crypto-twin"
    # restore module globals so later tests see the real paths
    monkeypatch.setattr(ex, "E2E_PROBE_ROOT", None)
