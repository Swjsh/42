"""test_quote_recorder_underlying_2026_09_03.py -- guard for the RTH-SPY-PER-MINUTE-TAPE
queue item: quote_recorder.py now appends ONE "kind":"underlying" SPY row per cycle inside
literal RTH (09:30-16:00 ET), positions open or not, alongside the pre-existing per-(arm,
symbol) option NBBO rows. Motivation quoted from the task briefing: core-decisions.jsonl's
`spy` field is a 5-min-bar-close series, so a 2026-09-03 post-mortem misread a 1-minute 30%
option gap at 10:00->10:01 ET (ISM Services release) as "flat SPY, pure decay" -- this closes
that blind spot with a real per-cycle underlying tape.

Zero network, zero broker imports -- every HTTP call is exercised through a monkeypatched
`quote_recorder._get_json` stand-in, exactly like setup/scripts/test_quote_recorder.py does
for the existing option-side functions. Never runs quote_recorder.py itself.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_quote_recorder_underlying_2026_09_03.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import quote_recorder as qr  # noqa: E402
import trades_enriched as te  # noqa: E402 -- a REAL existing quote-tape reader, for the
                               # "existing reader still parses the file" regression check.


RTH_NOW = dt.datetime(2026, 9, 3, 10, 30, 0)        # inside 09:30-16:00 ET, a Thursday
PRE_OPEN_NOW = dt.datetime(2026, 9, 3, 9, 0, 0)      # inside is_rth_window's 08:55 pad, before 09:30
POST_CLOSE_NOW = dt.datetime(2026, 9, 3, 16, 3, 0)   # inside is_rth_window's 16:05 pad, after 16:00

FAKE_CREDS = {"safe-2": {"key": "k-safe2", "secret": "s-safe2", "base_url": "https://paper-api.alpaca.markets"},
              "bold-2": {"key": "k-bold2", "secret": "s-bold2", "base_url": "https://paper-api.alpaca.markets"}}


def _fake_snapshot_payload(bid=670.10, ask=670.14, last=670.12, last_ts="2026-09-03T14:30:00.5Z"):
    return {
        "symbol": "SPY",
        "latestQuote": {"bp": bid, "ap": ask, "bs": 4, "as": 6, "t": "2026-09-03T14:30:00.4Z"},
        "latestTrade": {"p": last, "t": last_ts, "s": 100},
    }


# --------------------------------------------------------------------------------------- #
# get_stock_snapshot -- pure parsing via monkeypatched _get_json (no network)
# --------------------------------------------------------------------------------------- #

def test_get_stock_snapshot_parses_bid_ask_mid_last_in_one_call(monkeypatch):
    calls = []

    def fake_get_json(url, headers, timeout=10.0):
        calls.append(url)
        assert "/v2/stocks/SPY/snapshot" in url
        return _fake_snapshot_payload(), None

    monkeypatch.setattr(qr, "_get_json", fake_get_json)
    snap, err = qr.get_stock_snapshot({"key": "k", "secret": "s"}, "SPY")
    assert err is None
    assert snap["bid"] == 670.10 and snap["ask"] == 670.14
    assert snap["mid"] == 670.12
    assert snap["last"] == 670.12
    assert snap["last_ts"] == "2026-09-03T14:30:00.5Z"
    assert len(calls) == 1  # confirms it is ONE HTTP call, not two (quote + trade combined)


def test_get_stock_snapshot_propagates_fetch_error(monkeypatch):
    monkeypatch.setattr(qr, "_get_json",
                         lambda url, headers, timeout=10.0: (None, "HTTP 500: boom"))
    snap, err = qr.get_stock_snapshot({"key": "k", "secret": "s"}, "SPY")
    assert snap is None and err == "HTTP 500: boom"


def test_get_stock_snapshot_no_quote_or_trade_is_not_an_error(monkeypatch):
    monkeypatch.setattr(qr, "_get_json", lambda url, headers, timeout=10.0: ({"symbol": "SPY"}, None))
    snap, err = qr.get_stock_snapshot({"key": "k", "secret": "s"}, "SPY")
    assert snap is None and err is None


def test_get_stock_snapshot_uses_the_given_creds_headers(monkeypatch):
    seen_headers = {}

    def fake_get_json(url, headers, timeout=10.0):
        seen_headers.update(headers)
        return _fake_snapshot_payload(), None

    monkeypatch.setattr(qr, "_get_json", fake_get_json)
    qr.get_stock_snapshot({"key": "the-key", "secret": "the-secret"}, "SPY")
    assert seen_headers["APCA-API-KEY-ID"] == "the-key"
    assert seen_headers["APCA-API-SECRET-KEY"] == "the-secret"


# --------------------------------------------------------------------------------------- #
# is_underlying_rth_window -- 09:30-16:00 ET, narrower than is_rth_window's 08:55-16:05 pad
# --------------------------------------------------------------------------------------- #

def test_is_underlying_rth_window_true_mid_session():
    assert qr.is_underlying_rth_window(RTH_NOW)


def test_is_underlying_rth_window_false_before_open_even_inside_is_rth_window_pad():
    assert qr.is_rth_window(PRE_OPEN_NOW)              # broad option-side gate: True
    assert not qr.is_underlying_rth_window(PRE_OPEN_NOW)  # narrow underlying gate: False


def test_is_underlying_rth_window_false_after_close_even_inside_is_rth_window_pad():
    assert qr.is_rth_window(POST_CLOSE_NOW)
    assert not qr.is_underlying_rth_window(POST_CLOSE_NOW)


def test_is_underlying_rth_window_boundaries_inclusive():
    assert qr.is_underlying_rth_window(dt.datetime(2026, 9, 3, 9, 30, 0))
    assert qr.is_underlying_rth_window(dt.datetime(2026, 9, 3, 16, 0, 0))
    assert not qr.is_underlying_rth_window(dt.datetime(2026, 9, 3, 9, 29, 0))
    assert not qr.is_underlying_rth_window(dt.datetime(2026, 9, 3, 16, 1, 0))


def test_is_underlying_rth_window_false_on_weekend():
    assert not qr.is_underlying_rth_window(dt.datetime(2026, 9, 5, 10, 30, 0))  # Saturday


# --------------------------------------------------------------------------------------- #
# build_underlying_row -- never fabricate a row
# --------------------------------------------------------------------------------------- #

def test_build_underlying_row_shape():
    snap = {"bid": 670.10, "ask": 670.14, "mid": 670.12, "last": 670.12, "last_ts": "t1"}
    row = qr.build_underlying_row(RTH_NOW, 7, snap)
    assert row["schema"] == qr.SCHEMA
    assert row["kind"] == "underlying"
    assert row["symbol"] == "SPY"
    assert row["cycle_id"] == 7
    assert row["bid"] == 670.10 and row["ask"] == 670.14 and row["mid"] == 670.12
    assert row["last"] == 670.12 and row["last_ts"] == "t1"
    assert row["source"] == "alpaca_stock_quotes_latest"
    assert row["ts_et"] == RTH_NOW.isoformat()
    assert row["date_et"] == "2026-09-03"
    json.dumps(row, default=str)  # must be JSON-serializable as-is


def test_build_underlying_row_returns_none_for_falsy_snapshot():
    assert qr.build_underlying_row(RTH_NOW, 1, None) is None
    assert qr.build_underlying_row(RTH_NOW, 1, {}) is None


# --------------------------------------------------------------------------------------- #
# run_cycle integration -- RTH writes exactly one SPY row; idle writes none; a fetch
# exception never touches the option rows; both land in the same dated file.
# --------------------------------------------------------------------------------------- #

def _patch_options_side(monkeypatch, positions_by_arm, quote_by_symbol):
    """Stub the option-side broker calls so run_cycle's option path is deterministic and
    hits no network, independent of whatever the underlying-side fake does this test."""
    def fake_positions(creds):
        arm = next(a for a, c in FAKE_CREDS.items() if c is creds)
        return positions_by_arm.get(arm, []), None

    def fake_nbbo(creds, symbol):
        return quote_by_symbol.get(symbol), None

    monkeypatch.setattr(qr, "get_open_spy_option_positions", fake_positions)
    monkeypatch.setattr(qr, "get_option_nbbo", fake_nbbo)


def test_run_cycle_rth_writes_exactly_one_spy_underlying_row(monkeypatch, tmp_path):
    monkeypatch.setattr(qr, "et_now", lambda: RTH_NOW)
    _patch_options_side(monkeypatch, {}, {})  # book-wide flat -- no option rows this cycle
    monkeypatch.setattr(qr, "get_stock_snapshot", lambda creds, symbol="SPY": (_snap(), None))

    summary = qr.run_cycle(FAKE_CREDS, {}, cycle_id=3, out_dir=tmp_path)
    assert summary["underlying_rows_written"] == 1
    assert summary["rows_written"] == 1  # zero option rows + one underlying row
    assert "underlying" not in summary["errors"]

    out_path = tmp_path / "2026-09-03.jsonl"
    lines = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines()]
    underlying_rows = [r for r in lines if r.get("kind") == "underlying"]
    assert len(underlying_rows) == 1
    r = underlying_rows[0]
    assert r["symbol"] == "SPY" and r["schema"] == qr.SCHEMA and r["cycle_id"] == 3
    for field in ("ts_et", "ts_utc", "date_et", "bid", "ask", "mid", "last", "last_ts", "source"):
        assert field in r


def _snap():
    return {"bid": 670.10, "ask": 670.14, "mid": 670.12, "last": 670.12, "last_ts": "t1"}


def test_run_cycle_outside_rth_writes_zero_underlying_rows(monkeypatch, tmp_path):
    """PRE_OPEN_NOW is inside is_rth_window's own 08:55 pad (so run_cycle still executes and
    would poll options normally), but strictly before the 09:30 underlying-only gate."""
    monkeypatch.setattr(qr, "et_now", lambda: PRE_OPEN_NOW)
    _patch_options_side(monkeypatch, {}, {})
    calls = []
    monkeypatch.setattr(qr, "get_stock_snapshot",
                         lambda creds, symbol="SPY": (calls.append(1) or _snap(), None))

    summary = qr.run_cycle(FAKE_CREDS, {}, cycle_id=1, out_dir=tmp_path)
    assert summary["underlying_rows_written"] == 0
    assert summary["rows_written"] == 0
    assert calls == []  # get_stock_snapshot must not even be called outside the window
    assert not (tmp_path / "2026-09-03.jsonl").exists()


def test_run_cycle_underlying_fetch_error_leaves_option_rows_intact(monkeypatch, tmp_path):
    positions = {"safe-2": [{"symbol": "SPY260903C00770000", "qty": "3", "side": "long",
                              "avg_entry_price": "1.80"}]}
    quotes = {"SPY260903C00770000": {"bid": 1.70, "ask": 1.75, "bid_size": 5, "ask_size": 5,
                                      "quote_ts": "t2"}}
    monkeypatch.setattr(qr, "et_now", lambda: RTH_NOW)
    _patch_options_side(monkeypatch, positions, quotes)
    monkeypatch.setattr(qr, "get_stock_snapshot",
                         lambda creds, symbol="SPY": (_ for _ in ()).throw(ConnectionError("no route")))

    summary = qr.run_cycle(FAKE_CREDS, {}, cycle_id=5, out_dir=tmp_path)
    assert summary["underlying_rows_written"] == 0
    assert "underlying" in summary["errors"]
    assert "no route" in summary["errors"]["underlying"] or "ConnectionError" in summary["errors"]["underlying"]
    # the option row must still have been written despite the underlying blow-up
    assert summary["rows_written"] == 1
    lines = [json.loads(l) for l in (tmp_path / "2026-09-03.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["kind"] == "option"
    assert lines[0]["symbol"] == "SPY260903C00770000"


def test_run_cycle_underlying_and_option_rows_share_the_same_dated_file(monkeypatch, tmp_path):
    positions = {"bold-2": [{"symbol": "SPY260903P00765000", "qty": "2", "side": "long"}]}
    quotes = {"SPY260903P00765000": {"bid": 0.50, "ask": 0.55, "bid_size": 1, "ask_size": 1,
                                      "quote_ts": "t3"}}
    monkeypatch.setattr(qr, "et_now", lambda: RTH_NOW)
    _patch_options_side(monkeypatch, positions, quotes)
    monkeypatch.setattr(qr, "get_stock_snapshot", lambda creds, symbol="SPY": (_snap(), None))

    summary = qr.run_cycle(FAKE_CREDS, {}, cycle_id=9, out_dir=tmp_path)
    assert summary["rows_written"] == 2  # 1 option + 1 underlying
    assert summary["underlying_rows_written"] == 1

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]
    kinds = sorted(r["kind"] for r in lines)
    assert kinds == ["option", "underlying"]


def test_run_cycle_uses_one_arm_own_creds_for_the_underlying_call(monkeypatch, tmp_path):
    """The underlying fetch must go through the SAME per-arm credentials the option
    snapshots use -- not a hardcoded/new credential path."""
    seen = {}

    def fake_snapshot(creds, symbol="SPY"):
        seen["creds"] = creds
        return _snap(), None

    monkeypatch.setattr(qr, "et_now", lambda: RTH_NOW)
    _patch_options_side(monkeypatch, {}, {})
    monkeypatch.setattr(qr, "get_stock_snapshot", fake_snapshot)

    qr.run_cycle(FAKE_CREDS, {}, cycle_id=2, out_dir=tmp_path)
    # deterministic pick: sorted(FAKE_CREDS) == ["bold-2", "safe-2"] -> "bold-2" first
    assert seen["creds"] == FAKE_CREDS["bold-2"]


def test_run_cycle_no_creds_configured_is_ok_not_an_underlying_error(monkeypatch, tmp_path):
    """Empty creds_by_arm mirrors the pre-existing option-side contract (test_quote_recorder.
    py::test_run_cycle_dry_run_no_creds_is_ok_and_writes_nothing): nothing configured to check
    is NOT an error, on either side -- the underlying fetch must simply be skipped, never
    recorded under arm_errors["underlying"]."""
    monkeypatch.setattr(qr, "et_now", lambda: RTH_NOW)
    summary = qr.run_cycle({}, {}, cycle_id=1, out_dir=tmp_path)
    assert summary["underlying_rows_written"] == 0
    assert "underlying" not in summary["errors"]
    assert summary["ok"] is True


# --------------------------------------------------------------------------------------- #
# An existing reader of the (unchanged) option-row schema must still parse the file
# unaffected by the new "kind" key and the new underlying rows mixed into the same file.
# --------------------------------------------------------------------------------------- #

def test_existing_trades_enriched_reader_still_parses_mixed_file(tmp_path):
    option_row = {
        "schema": qr.SCHEMA, "kind": "option", "ts_et": "2026-09-03T10:30:00", "ts_utc": "x",
        "date_et": "2026-09-03", "cycle_id": 3, "arm": "safe-2", "account_number": "PAxxx",
        "symbol": "SPY260903C00770000", "qty_open": "3", "side": "long",
        "avg_entry_price": "1.80", "bid": 1.70, "ask": 1.75, "mid": 1.725,
        "bid_size": 5, "ask_size": 5, "quote_ts": "t2", "source": "alpaca_options_quotes_latest",
    }
    underlying_row = qr.build_underlying_row(dt.datetime(2026, 9, 3, 10, 30, 0), 3, _snap())

    p = tmp_path / "2026-09-03.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(option_row) + "\n")
        fh.write(json.dumps(underlying_row) + "\n")

    idx = te.load_quote_tape(tmp_path, {"2026-09-03"})
    # the option row is indexed exactly as before (arm, symbol both present)
    assert ("2026-09-03", "safe-2", "SPY260903C00770000") in idx
    assert len(idx[("2026-09-03", "safe-2", "SPY260903C00770000")]) == 1
    # the underlying row has no "arm" -- load_quote_tape's own contract silently skips it
    # (never a KeyError/crash), so it contributes no new index key
    assert all(key[1] == "safe-2" for key in idx)  # only the option row's key exists


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
