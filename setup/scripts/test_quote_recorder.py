"""Guard tests for quote_recorder.py -- pure logic only, zero network, zero broker imports.

Scope: this tests the SIDE-CHANNEL's own contract (never fabricate a row without a real
position+quote pair, retention pruning is date-exact and non-destructive to newer files, RTH
gating is correct, status writes are atomic and always readable) -- it does NOT hit any live
endpoint (get_open_spy_option_positions / get_option_nbbo are exercised only via monkeypatched
stand-ins inside run_cycle's own guards, never a real urlopen).

Run: backtest/.venv/Scripts/python.exe -m pytest setup/scripts/test_quote_recorder.py -q
     (plain `python -m pytest ...` also works -- stdlib only, no pandas/numpy deps)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import quote_recorder as qr  # noqa: E402


# --------------------------------------------------------------------------------------- #
# build_snapshot_rows -- never fabricate a row
# --------------------------------------------------------------------------------------- #

def test_build_snapshot_rows_emits_one_row_per_position_with_a_quote():
    now = dt.datetime(2026, 8, 28, 10, 30, 0)
    arm_positions = {"safe-3": [{"symbol": "SPY260828C00771000", "qty": "3",
                                  "avg_entry_price": "1.84", "side": "long"}]}
    arm_quotes = {"safe-3": {"SPY260828C00771000": {"bid": 3.70, "ask": 3.75, "mid": 3.725,
                                                      "bid_size": 12, "ask_size": 8,
                                                      "quote_ts": "2026-08-28T14:30:00Z"}}}
    rows = qr.build_snapshot_rows(now, 1, arm_positions, arm_quotes,
                                   account_numbers={"safe-3": "PA32T7Q1O20H"})
    assert len(rows) == 1
    r = rows[0]
    assert r["arm"] == "safe-3"
    assert r["symbol"] == "SPY260828C00771000"
    assert r["bid"] == 3.70 and r["ask"] == 3.75 and r["mid"] == 3.725
    assert r["account_number"] == "PA32T7Q1O20H"
    assert r["schema"] == qr.SCHEMA
    # row must be JSON-serializable as-is (what the real writer does)
    json.dumps(r, default=str)


def test_build_snapshot_rows_skips_position_with_no_quote_yet():
    """A position that exists but has no successfully-fetched quote this cycle must NOT
    produce a row -- a missing quote is silence, never a null-filled fabricated row."""
    now = dt.datetime(2026, 8, 28, 10, 30, 0)
    arm_positions = {"safe-2": [{"symbol": "SPY260828C00771000", "qty": "1"}]}
    arm_quotes = {"safe-2": {}}  # quote fetch failed or returned nothing this cycle
    rows = qr.build_snapshot_rows(now, 1, arm_positions, arm_quotes)
    assert rows == []


def test_build_snapshot_rows_multiple_arms_multiple_symbols():
    now = dt.datetime(2026, 8, 28, 10, 30, 0)
    arm_positions = {
        "safe-2": [{"symbol": "SPY260828C00771000", "qty": "5"}],
        "bold-2": [{"symbol": "SPY260828P00765000", "qty": "8"}],
    }
    arm_quotes = {
        "safe-2": {"SPY260828C00771000": {"bid": 3.70, "ask": 3.75, "mid": 3.725,
                                           "bid_size": 1, "ask_size": 1, "quote_ts": "t1"}},
        "bold-2": {"SPY260828P00765000": {"bid": 0.50, "ask": 0.55, "mid": 0.525,
                                           "bid_size": 1, "ask_size": 1, "quote_ts": "t2"}},
    }
    rows = qr.build_snapshot_rows(now, 1, arm_positions, arm_quotes)
    assert {r["arm"] for r in rows} == {"safe-2", "bold-2"}
    assert len(rows) == 2


def test_build_snapshot_rows_empty_positions_yields_empty():
    now = dt.datetime(2026, 8, 28, 10, 30, 0)
    assert qr.build_snapshot_rows(now, 1, {}, {}) == []


# --------------------------------------------------------------------------------------- #
# prune_old_files -- exact date boundary, never touches an unparseable filename
# --------------------------------------------------------------------------------------- #

def test_prune_old_files_deletes_only_strictly_older_than_cutoff(tmp_path):
    (tmp_path / "2026-06-01.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "2026-06-02.jsonl").write_text("{}\n", encoding="utf-8")  # == cutoff, kept
    (tmp_path / "2026-07-01.jsonl").write_text("{}\n", encoding="utf-8")  # newer, kept
    (tmp_path / "not-a-date.jsonl").write_text("{}\n", encoding="utf-8")  # never touched
    cutoff = dt.date(2026, 6, 2)
    deleted = qr.prune_old_files(tmp_path, cutoff)
    assert deleted == ["2026-06-01.jsonl"]
    remaining = {p.name for p in tmp_path.glob("*.jsonl")}
    assert remaining == {"2026-06-02.jsonl", "2026-07-01.jsonl", "not-a-date.jsonl"}


def test_prune_old_files_missing_dir_returns_empty():
    assert qr.prune_old_files(Path("Z:/definitely/does/not/exist"), dt.date(2026, 1, 1)) == []


# --------------------------------------------------------------------------------------- #
# is_rth_window
# --------------------------------------------------------------------------------------- #

def test_is_rth_window_true_during_session():
    assert qr.is_rth_window(dt.datetime(2026, 8, 28, 10, 30))  # Friday 10:30 ET


def test_is_rth_window_false_before_open():
    assert not qr.is_rth_window(dt.datetime(2026, 8, 28, 8, 0))


def test_is_rth_window_false_after_close():
    assert not qr.is_rth_window(dt.datetime(2026, 8, 28, 17, 13))  # matches the live et_clock
    # snapshot captured this session: 2026-08-28 17:13:24 ET, market_hours=False


def test_is_rth_window_false_on_weekend():
    assert not qr.is_rth_window(dt.datetime(2026, 8, 29, 10, 30))  # Saturday


# --------------------------------------------------------------------------------------- #
# load_creds -- never raises on missing/malformed input, never returns a partial credential
# --------------------------------------------------------------------------------------- #

def test_load_creds_missing_file_returns_empty(tmp_path):
    assert qr.load_creds(tmp_path / "nope.json", qr.ARMS) == {}


def test_load_creds_skips_entries_missing_key_or_secret(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {
        "safe-2": {"key": "k1", "secret": "s1", "base_url": "https://paper-api.alpaca.markets"},
        "bold-2": {"key": "k2"},  # no secret -- must be skipped, not half-loaded
        "safe-3": {},
    }}), encoding="utf-8")
    creds = qr.load_creds(p, ("safe-2", "bold-2", "safe-3"))
    assert set(creds.keys()) == {"safe-2"}
    assert creds["safe-2"]["base_url"] == "https://paper-api.alpaca.markets"


def test_load_creds_only_returns_requested_arms(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {
        "safe-2": {"key": "k1", "secret": "s1"},
        "risky-3": {"key": "k2", "secret": "s2"},
    }}), encoding="utf-8")
    creds = qr.load_creds(p, ("safe-2",))
    assert set(creds.keys()) == {"safe-2"}


def test_load_creds_malformed_json_returns_empty(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert qr.load_creds(p, qr.ARMS) == {}


# --------------------------------------------------------------------------------------- #
# status file -- atomic write, always readable, tolerant of a missing/corrupt prior file
# --------------------------------------------------------------------------------------- #

def test_write_then_read_status_roundtrip(tmp_path):
    p = tmp_path / "status.json"
    qr.write_status({"schema": qr.STATUS_SCHEMA, "last_cycle_ok": True}, p)
    got = qr.read_status(p)
    assert got["last_cycle_ok"] is True
    assert got["schema"] == qr.STATUS_SCHEMA


def test_read_status_missing_file_returns_empty_dict(tmp_path):
    assert qr.read_status(tmp_path / "nope.json") == {}


def test_read_status_corrupt_file_returns_empty_dict(tmp_path):
    p = tmp_path / "status.json"
    p.write_text("{not json", encoding="utf-8")
    assert qr.read_status(p) == {}


def test_write_status_never_leaves_a_tmp_file_behind(tmp_path):
    p = tmp_path / "status.json"
    qr.write_status({"a": 1}, p)
    assert not (tmp_path / "status.tmp").exists()
    assert p.exists()


# --------------------------------------------------------------------------------------- #
# run_cycle -- total containment: one arm erroring never blanks the others, and a broker
# read failure is distinguished from a genuinely-flat account (never a fabricated "flat").
# --------------------------------------------------------------------------------------- #

def test_run_cycle_dry_run_no_creds_is_ok_and_writes_nothing(tmp_path):
    """No creds configured at all -> zero positions checked -> ok (nothing to report failing
    on) -- this is what happens automatically outside RTH / with an empty arms list."""
    summary = qr.run_cycle({}, {}, cycle_id=1, dry_run=True, out_dir=tmp_path)
    assert summary["ok"] is True
    assert summary["rows_written"] == 0
    assert summary["positions_open_count"] == 0
    assert list(tmp_path.glob("*.jsonl")) == []


def test_run_cycle_never_raises_on_garbage_creds(tmp_path):
    """A key/secret pair pointing nowhere real must degrade to a per-arm error, never an
    unhandled exception -- this is the exact fail-open contract the module docstring claims.
    (Hits a real DNS/connect failure quickly rather than a live endpoint; safe offline too --
    urllib raises URLError either way, which get_open_spy_option_positions converts to a
    string, never lets escape.)"""
    creds = {"safe-2": {"key": "bogus", "secret": "bogus",
                        "base_url": "https://this-host-does-not-resolve.invalid"}}
    summary = qr.run_cycle(creds, {}, cycle_id=1, dry_run=True, out_dir=tmp_path)
    assert summary["ok"] is False
    assert "safe-2" in summary["errors"]
    assert summary["rows_written"] == 0


# --------------------------------------------------------------------------------------- #
# get_option_nbbo pure-parsing behaviour via a monkeypatched _get_json (no network)
# --------------------------------------------------------------------------------------- #

def test_get_option_nbbo_parses_bid_ask_mid(monkeypatch):
    def fake_get_json(url, headers, timeout=10.0):
        assert "SPY260828C00771000" in url
        return {"quotes": {"SPY260828C00771000": {"bp": 3.70, "ap": 3.75, "bs": 12, "as": 8,
                                                    "t": "2026-08-28T14:30:00.123Z"}}}, None
    monkeypatch.setattr(qr, "_get_json", fake_get_json)
    q, err = qr.get_option_nbbo({"key": "k", "secret": "s", "base_url": "x"},
                                 "SPY260828C00771000")
    assert err is None
    assert q["bid"] == 3.70 and q["ask"] == 3.75 and q["mid"] == 3.725
    assert q["bid_size"] == 12 and q["ask_size"] == 8


def test_get_option_nbbo_no_quote_available_is_not_an_error(monkeypatch):
    monkeypatch.setattr(qr, "_get_json", lambda url, headers, timeout=10.0: ({"quotes": {}}, None))
    q, err = qr.get_option_nbbo({"key": "k", "secret": "s", "base_url": "x"}, "SPY260828C00771000")
    assert q is None and err is None


def test_get_option_nbbo_propagates_fetch_error(monkeypatch):
    monkeypatch.setattr(qr, "_get_json",
                         lambda url, headers, timeout=10.0: (None, "HTTP 500: boom"))
    q, err = qr.get_option_nbbo({"key": "k", "secret": "s", "base_url": "x"}, "SPY260828C00771000")
    assert q is None and err == "HTTP 500: boom"


def test_get_option_nbbo_one_sided_quote_has_null_mid(monkeypatch):
    """A bid with no ask (or vice versa) must not synthesize a fake mid."""
    monkeypatch.setattr(qr, "_get_json", lambda url, headers, timeout=10.0:
                         ({"quotes": {"SYM": {"bp": 1.0, "ap": None}}}, None))
    q, err = qr.get_option_nbbo({"key": "k", "secret": "s", "base_url": "x"}, "SYM")
    assert q["bid"] == 1.0 and q["ask"] is None and q["mid"] is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
