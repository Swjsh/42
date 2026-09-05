"""Guard for the tickers-lane kill-switch REPORTING bug found in the 2026-09-04 day-one
theta-budget-overshoot audit (all 3 arms' first fills exited via theta_budget 38-71% past the
configured 30% bleed cap -- see analysis/recommendations/prereg-tickers-theta-budget-cadence-
2026-09-05.json for that finding, which is cadence/execution-mechanical and NOT fixed here per
OP-16 (n=3 too thin to act on a param change)).

This file guards a SEPARATE, confirmed-mechanical bug surfaced by the same audit: on the tick
whose OWN exit fill is what pushes realized_pnl_today past the daily kill threshold,
multi/execute.py::run_arm persisted day["kill_tripped"] using the value computed BEFORE that
exit's P&L was folded in (step 5, before the exits loop), then saved the day file with that
stale False. The in-memory recompute after the exits loop (originally a comment-only "re-read
the kill state" step) was correct and DID block later entries that tick and every tick after
(proven live 2026-09-04 by 25 "daily kill switch already tripped" BLOCKED rows across the 3
arms) -- but that corrected boolean was never written back into `day` before persisting, and no
LATER tick that day had a fill of its own to trigger another save. Result: automation/state/
tickers/tickers-N/day-2026-09-04.json and downstream day-check-eod.json / STATUS consumers
report kill_tripped:false forever, contradicting the broker-truth trading behavior.

Trading path is NOT touched -- KILL_BLOCKED gating already read the freshly recomputed
in-memory `kill_tripped` correctly. This guard is reporting-only.

NO NETWORK: same fixture pattern as test_tickers_execute_2026_09_04.py (state_dir/monkeypatch
fixtures copied here rather than imported, so this file stands alone and stays RED-proofable
via a plain `git stash`/`git stash pop` of multi/execute.py without touching the sibling file).
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

from multi import execute  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import exits as mex  # noqa: E402
from multi.lib import journal as mj  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402

FIXED_NOW = dt.datetime(2026, 9, 4, 10, 0, 0)
assert FIXED_NOW.weekday() == 4

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


def _exit_row(contract: str, symbol: str, decision: str, *, qty_to_close=None,
              bid=1.0, ask=1.05, stage="theta_budget") -> dict:
    row = {"kind": "exit_eval", "contract": contract, "symbol": symbol, "decision": decision,
           "stage": stage, "bid": bid, "ask": ask}
    if qty_to_close is not None:
        row["qty_to_close"] = qty_to_close
    return row


def _seed_position(arm: str, contract: str, **kw) -> mps.PositionRecord:
    defaults = dict(symbol="AMZN", contract=contract, side="C", entry_premium=0.79,
                    entry_underlying_price=259.97, qty=3, entry_session_date="2026-09-04",
                    expiry="2026-09-04", hwm_premium=0.79, strategy="production_ribbon_ride")
    defaults.update(kw)
    rec = mps.PositionRecord(**defaults)
    state_path = execute.arm_state_path(arm)
    mps.ensure_initialized(path=state_path)
    mps.save_state({contract: rec}, path=state_path)
    return rec


def _write_secrets(state_dir: Path, arms=("tickers-1",)) -> None:
    accounts = {}
    for i, a in enumerate(arms, start=1):
        accounts[a] = {"key": f"PKTEST{i}KEY", "secret": f"TESTSECRET{i}",
                       "base_url": "https://paper-api.alpaca.markets"}
    (state_dir / "secrets.json").write_text(json.dumps({"accounts": accounts}), encoding="utf-8")


def _stub_resolve(params: dict) -> mc.MultiCreds:
    acct = params.get("account") or {}
    return mc.MultiCreds(key="FAKEKEY", secret="FAKESECRET",
                         base_url="https://paper-api.alpaca.markets",
                         account_number=str(acct.get("account_number") or ""),
                         source=f"test:{acct.get('key_source')}")


def _stub_verify_account(resolved_number="PA39FKBSPLPR", equity=4843.85):
    def _verify(creds: mc.MultiCreds) -> dict:
        return {"account_number": resolved_number, "equity": equity, "buying_power": equity,
                "options_approved_level": 3, "status": "ACTIVE"}
    return _verify


def _recording_broker(monkeypatch):
    calls = {"market_sell": []}

    def fake_market_sell(creds, *, symbol, qty, armed=False, params=None):
        calls["market_sell"].append({"symbol": symbol, "qty": qty, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"symbol": symbol, "qty": qty}, params=params)
        if preview is not None:
            return preview
        return {"id": "order-exit-1", "status": "accepted"}

    def fake_poll_fill(creds, order_id, *, attempts=3, sleep_sec=1.5):
        # AMZN 3 @ 0.27 -- the real 2026-09-04 tickers-1 fill (entry 0.79, -65.8% bleed).
        return {"filled": True, "status": "filled", "filled_qty": 3, "filled_avg_price": 0.27, "order": {}}

    monkeypatch.setattr(execute.mb, "market_sell", fake_market_sell)
    monkeypatch.setattr(execute.mb, "poll_fill", fake_poll_fill)
    monkeypatch.setattr(execute.mb, "place_bracket",
                        lambda *a, **kw: pytest.fail("no entry should be attempted in this test"))
    monkeypatch.setattr(execute.mb, "equity_option_positions", lambda *a, **kw: [])
    monkeypatch.setattr(execute.mb, "get_orders", lambda *a, **kw: [])
    monkeypatch.setattr(execute.mb, "get_position_qty", lambda *a, **kw: 3)
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


def test_kill_tripped_persisted_to_day_file_on_the_tripping_exit_tick(state_dir, monkeypatch):
    """Reproduces 2026-09-04 tickers-1 exactly: start-of-day equity $5000 (1% kill = -$50),
    day file starts realized_pnl_today=0.0 / kill_tripped=False (pre-trip snapshot, matching
    what step 5 would have loaded before any fill this tick). ONE tick evaluates a theta_budget
    SELL_ALL for the only open position and fills it at 0.27 (entry 0.79, qty 3): realized
    P&L = (0.27 - 0.79) * 3 * 100 = -$156.00, which is -3.12% of the $5000 start-of-day equity
    -- past the 1% kill threshold for the FIRST time on this exact tick.

    Pre-fix: day["kill_tripped"] is only ever set at step 5 (before this tick's own exit ran)
    and only re-persisted via a save_day_file call that never re-touches the field, so the
    on-disk day file keeps kill_tripped=False even though summary["kill"] (in-memory, used for
    KILL_BLOCKED gating) is correctly True. Post-fix: the on-disk file matches broker truth
    the instant the switch trips, with no dependency on a later tick having its own fill.
    """
    _recording_broker(monkeypatch)
    contract = "AMZN260904C00260000"
    _seed_position("tickers-1", contract, entry_premium=0.79, hwm_premium=0.79)
    # append_exit() looks up its ENTRY row by trade_id/contract to compute pnl_dollars -- without
    # this the exit falls through to EXIT_JOURNAL_LOOKUP_FAILED, pnl stays None, realized_pnl_today
    # never moves, and the kill switch (correctly) never trips -- which would make this test
    # pass for the WRONG reason. Seed the real journal entry the live 09:43:17 fill wrote.
    mj.append_entry(trade_id="tickers-1-AMZN260904C00260000-094317", symbol="AMZN", contract=contract,
                    side="C", entry_date=FIXED_NOW.date(), entry_time_et="09:43:17",
                    entry_premium=0.79, qty=3, arm="tickers-1", path=execute.arm_journal_path("tickers-1"))

    day_path = execute.arm_day_path("tickers-1", FIXED_NOW.date().isoformat())
    execute.save_day_file(day_path, {
        "date": FIXED_NOW.date().isoformat(), "arm": "tickers-1",
        "start_of_day_equity": 5000.0, "realized_pnl_today": 0.0,
        "kill_tripped": False, "fills": [],
    })

    rows = [_exit_row(contract, "AMZN", mex.ACTION_SELL_ALL, qty_to_close=3, bid=0.30, ask=0.32,
                       stage="theta_budget")]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    # In-memory summary was already correct pre-fix -- not the bug. Kept as a sanity check.
    assert summary["kill"] is True, "sanity: this tick's own exit must push realized P&L past -1%"

    persisted = json.loads(day_path.read_text(encoding="utf-8"))
    assert persisted["realized_pnl_today"] == pytest.approx(-156.0, abs=0.01)
    assert persisted["kill_tripped"] is True, (
        "REGRESSION: day file still reports kill_tripped=False after the exact tick whose own "
        "exit tripped it -- this is the 2026-09-04 tickers-1/2/3 reporting bug: "
        "tickers_day_check.py / day-check-eod.json / STATUS all read this stale field, "
        "contradicting the KILL_BLOCKED rows proving the trading path enforced it correctly."
    )
