"""Guards for multi/tickers_day_check.py -- the T6 instrument (2026-09-04).

Pins: DARK arm is RED; NO_CREDS-only is AMBER; scoring rows are GREEN; eod NOT_FLAT at the broker
is RED regardless of state; state-outlives-broker is AMBER; the goal log line lands above the
HONEST STATE anchor; a RED writes the STATUS marker line and a later GREEN clears it; dry-run
writes nothing; phase auto splits at noon ET.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import execute as mx  # noqa: E402
from multi import tickers_day_check as dc  # noqa: E402

NOW_OPEN = dt.datetime(2026, 9, 4, 9, 40)
NOW_EOD = dt.datetime(2026, 9, 4, 15, 5)
PARAMS = {"arms": {"tickers-1": {"key_source": "tickers-1", "universe": ["NVDA", "AAPL", "AMZN"]},
                   "tickers-2": {"key_source": "tickers-2", "universe": ["TSLA", "META", "AVGO"]}}}


@pytest.fixture
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(mx, "TICKERS_STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mx, "JOURNAL_DIR", tmp_path / "journal")
    goal = tmp_path / "GOAL.md"
    goal.write_text("# GOAL\n\n## PROGRESS LOG\n- 2026-09-04 01:05 ET -- opened\n## HONEST STATE\nfine\n", encoding="utf-8")
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## Known broken\n\n- [2026-09-03 10:00 ET] OTHER :: something else\n\n## Next\n", encoding="utf-8")
    return {"root": tmp_path, "goal": goal, "status": status}


def _ledger(arm: str, rows: list, date="2026-09-04"):
    p = mx.arm_ledger_path(arm)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps({"ts_et": f"{date}T09:{35 + i:02d}:00", "arm": arm, **r}) + "\n")


def _no_broker(lane_params, arm, cfg):
    return {"ok": False, "reason": "NO_CREDS: stub"}


def _flat_broker(lane_params, arm, cfg):
    return {"ok": True, "account_number": "PA_TEST", "equity": "100000", "options_approved_level": 3,
            "open_option_positions": []}


def test_dark_arm_is_red_and_no_creds_only_is_amber(lane):
    _ledger("tickers-2", [{"decision": "NO_CREDS", "reason": "secrets.json missing"}] * 3)
    rep = dc.run_check(PARAMS, "open", NOW_OPEN, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_no_broker)
    assert rep["arms"]["tickers-1"]["verdict"] == "RED"
    assert rep["arms"]["tickers-1"]["reasons"][0].startswith("DARK")
    assert rep["arms"]["tickers-2"]["verdict"] == "AMBER"
    assert rep["verdict"] == "RED"
    # RED -> STATUS marker line written, goal line above the anchor, JSON on disk
    status = lane["status"].read_text(encoding="utf-8")
    assert "TICKERS-DAY-CHECK RED" in status and "OTHER :: something else" in status
    goal = lane["goal"].read_text(encoding="utf-8")
    assert goal.index("[day-check/open] RED") < goal.index("## HONEST STATE")
    assert (lane["root"] / "out" / "day-check-2026-09-04-open.json").exists()


def test_scoring_rows_are_green_and_clear_a_prior_red(lane):
    for arm in ("tickers-1", "tickers-2"):
        _ledger(arm, [{"decision": "HOLD", "scorer": "production"}, {"decision": "BLOCKED", "gate": "liquidity"}])
    # seed a prior RED line and prove GREEN removes it
    dc._load_status_writer().upsert(dc.STATUS_MARKER, "- [x] TICKERS-DAY-CHECK RED :: stale", status_path=lane["status"])
    rep = dc.run_check(PARAMS, "open", NOW_OPEN, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_no_broker)
    assert rep["verdict"] == "GREEN"
    assert "TICKERS-DAY-CHECK" not in lane["status"].read_text(encoding="utf-8")


def test_eod_not_flat_at_broker_is_red_even_with_empty_state(lane):
    _ledger("tickers-1", [{"decision": "ENTRY_FILLED", "qty": 3}])
    _ledger("tickers-2", [{"decision": "HOLD"}])

    def broker(lane_params, arm, cfg):
        if arm == "tickers-1":
            return {"ok": True, "account_number": "PA1", "equity": "99000", "options_approved_level": 3,
                    "open_option_positions": [{"symbol": "NVDA260904P00227500", "qty": "2"}]}
        return _flat_broker(lane_params, arm, cfg)

    rep = dc.run_check(PARAMS, "eod", NOW_EOD, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=broker)
    assert rep["arms"]["tickers-1"]["verdict"] == "RED"
    assert any("NOT_FLAT" in r for r in rep["arms"]["tickers-1"]["reasons"])
    assert rep["arms"]["tickers-2"]["verdict"] == "GREEN"
    assert "NOT_FLAT" in lane["status"].read_text(encoding="utf-8")


def test_eod_state_outliving_broker_is_amber(lane, monkeypatch):
    _ledger("tickers-1", [{"decision": "EXIT_FILLED"}])
    _ledger("tickers-2", [{"decision": "HOLD"}])
    monkeypatch.setattr(dc, "read_state", lambda arm: {"exists": True, "records": 1, "contracts": ["NVDA260904P00227500"]}
                        if arm == "tickers-1" else {"exists": False, "records": 0, "contracts": []})
    rep = dc.run_check(PARAMS, "eod", NOW_EOD, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_flat_broker)
    assert rep["arms"]["tickers-1"]["verdict"] == "AMBER"
    assert rep["verdict"] == "AMBER"
    assert "TICKERS-DAY-CHECK" not in lane["status"].read_text(encoding="utf-8")  # AMBER is not RED


def test_dry_run_writes_nothing(lane):
    before_goal = lane["goal"].read_text(encoding="utf-8")
    before_status = lane["status"].read_text(encoding="utf-8")
    rep = dc.run_check(PARAMS, "open", NOW_OPEN, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", dry_run=True, broker_fn=_no_broker)
    assert rep["verdict"] == "RED" and "out_path" not in rep
    assert lane["goal"].read_text(encoding="utf-8") == before_goal
    assert lane["status"].read_text(encoding="utf-8") == before_status
    assert not (lane["root"] / "out").exists()


def test_auto_phase_splits_at_noon_et():
    assert dc.resolve_phase("auto", NOW_OPEN) == "open"
    assert dc.resolve_phase("auto", NOW_EOD) == "eod"
    assert dc.resolve_phase("eod", NOW_OPEN) == "eod"


def test_ledger_reader_ignores_other_days_and_bad_lines(lane):
    _ledger("tickers-1", [{"decision": "HOLD"}], date="2026-09-03")
    _ledger("tickers-1", [{"decision": "HOLD"}, {"decision": "WOULD_PLACE"}])
    with mx.arm_ledger_path("tickers-1").open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    led = dc.read_ledger_today("tickers-1", "2026-09-04")
    assert led["rows_today"] == 2 and led["bad_lines"] == 1
    assert led["decisions"] == {"HOLD": 1, "WOULD_PLACE": 1}


def test_doc_key_in_arms_is_ignored(lane):
    params = {"arms": {"_doc": "per-arm overrides", **PARAMS["arms"]}}
    _ledger("tickers-1", [{"decision": "HOLD"}]); _ledger("tickers-2", [{"decision": "HOLD"}])
    rep = dc.run_check(params, "open", NOW_OPEN, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_no_broker)
    assert set(rep["arms"]) == {"tickers-1", "tickers-2"} and rep["verdict"] == "GREEN"


def test_weekend_and_market_closed_skip_and_write_nothing(lane):
    sat = dt.datetime(2026, 9, 5, 9, 40)
    rep = dc.run_check(PARAMS, "open", sat, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_no_broker)
    assert rep["verdict"] == "SKIP" and "out_path" not in rep
    for arm in ("tickers-1", "tickers-2"):
        _ledger(arm, [{"decision": "MARKET_CLOSED"}] * 2)
    rep = dc.run_check(PARAMS, "open", NOW_OPEN, goal_path=lane["goal"], status_path=lane["status"],
                       out_dir=lane["root"] / "out", broker_fn=_no_broker)
    assert rep["verdict"] == "SKIP" and "out_path" not in rep
    assert "[day-check" not in lane["goal"].read_text(encoding="utf-8")
    assert not (lane["root"] / "out").exists()
