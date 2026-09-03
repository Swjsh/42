"""Guard tests for xsp_spread_recorder.py (work order §2b, 2026-09-03) -- pure logic +
mocked HTTP only, zero real network, zero broker/trading-path imports.

Scope: ATM strike resolution on each side (SPY from equity spot, XSP from put-call
parity on its own chain with a labelled fallback), the row-building contract (a
missing leg is recorded MISSING, never fabricated), and --summarize's matched-time
math on a fixture tape. Network functions (get_spy_spot / get_option_nbbo_batch) are
exercised only via monkeypatched urlopen stand-ins -- never a real HTTP call.

Run: backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_xsp_spread_recorder_2026_09_03.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import xsp_spread_recorder as xr  # noqa: E402


# --------------------------------------------------------------------------------------- #
# build_occ_symbol
# --------------------------------------------------------------------------------------- #

def test_build_occ_symbol_spy_and_xsp_unpadded_root():
    d = dt.date(2026, 9, 3)
    assert xr.build_occ_symbol("SPY", d, "C", 765) == "SPY260903C00765000"
    assert xr.build_occ_symbol("XSP", d, "P", 765) == "XSP260903P00765000"


def test_build_occ_symbol_rejects_bad_side():
    with pytest.raises(AssertionError):
        xr.build_occ_symbol("SPY", dt.date(2026, 9, 3), "X", 765)


def test_build_occ_symbol_strike_padding_and_rounding():
    # non-integer strike rounds to nearest dollar before padding
    sym = xr.build_occ_symbol("XSP", dt.date(2026, 9, 3), "C", 765.6)
    assert sym == "XSP260903C00766000"


# --------------------------------------------------------------------------------------- #
# round_to_atm_strike
# --------------------------------------------------------------------------------------- #

def test_round_to_atm_strike_nearest_dollar():
    assert xr.round_to_atm_strike(765.2) == 765
    assert xr.round_to_atm_strike(765.5) == 766
    assert xr.round_to_atm_strike(764.49) == 764


# --------------------------------------------------------------------------------------- #
# estimate_xsp_spot_via_parity -- ATM resolution for the side with no direct feed
# --------------------------------------------------------------------------------------- #

def test_parity_two_strikes_average():
    # strike 765: call mid 2.195, put mid 1.10 -> spot_est = 765 + 1.095 = 766.095
    # strike 766: call mid 1.50, put mid 1.80 -> spot_est = 766 - 0.30 = 765.70
    strike_quotes = {
        765: {"call": {"bid": 2.17, "ask": 2.22}, "put": {"bid": 1.05, "ask": 1.15}},
        766: {"call": {"bid": 1.45, "ask": 1.55}, "put": {"bid": 1.75, "ask": 1.85}},
    }
    spot, method, detail = xr.estimate_xsp_spot_via_parity(strike_quotes)
    assert method == "put_call_parity_2strike"
    assert spot == pytest.approx((766.095 + 765.70) / 2, abs=0.01)
    assert set(detail["per_strike"].keys()) == {765, 766}


def test_parity_one_strike_only_when_other_incomplete():
    strike_quotes = {
        765: {"call": {"bid": 2.17, "ask": 2.22}, "put": {"bid": 1.05, "ask": 1.15}},
        766: {"call": None, "put": {"bid": 1.75, "ask": 1.85}},  # call missing
    }
    spot, method, detail = xr.estimate_xsp_spot_via_parity(strike_quotes)
    assert method == "put_call_parity_1strike"
    assert spot == pytest.approx(766.095, abs=0.01)


def test_parity_fails_closed_when_no_strike_resolves():
    strike_quotes = {
        765: {"call": None, "put": {"bid": 1.05, "ask": 1.15}},
        766: {"call": {"bid": 1.45, "ask": 1.55}, "put": None},
    }
    spot, method, detail = xr.estimate_xsp_spot_via_parity(strike_quotes)
    assert spot is None
    assert method == "parity_failed"
    assert detail == {}


def test_parity_never_fabricates_on_partial_bid_ask():
    # a leg with a bid but no ask must not silently use bid-only as mid
    strike_quotes = {
        765: {"call": {"bid": 2.17, "ask": None}, "put": {"bid": 1.05, "ask": 1.15}},
    }
    spot, method, _ = xr.estimate_xsp_spot_via_parity(strike_quotes)
    assert spot is None
    assert method == "parity_failed"


# --------------------------------------------------------------------------------------- #
# leg_metrics -- per-leg spread/depth/rt_cost math, MISSING never fabricated
# --------------------------------------------------------------------------------------- #

def test_leg_metrics_ok_leg_math():
    m = xr.leg_metrics({"bid": 0.98, "ask": 1.03, "bid_size": 345, "ask_size": 59}, qty=3)
    assert m["status"] == "OK"
    assert m["spread_abs"] == pytest.approx(0.05, abs=1e-9)
    assert m["mid"] == pytest.approx(1.005, abs=1e-9)
    assert m["spread_pct_of_mid"] == pytest.approx(0.05 / 1.005, abs=1e-6)
    assert m["rt_cost_3lot"] == pytest.approx(0.05 * 3 * 100, abs=1e-9)
    assert m["bid_size"] == 345 and m["ask_size"] == 59


def test_leg_metrics_missing_quote_never_fabricates():
    m = xr.leg_metrics(None)
    assert m["status"] == "MISSING"
    assert all(m[k] is None for k in
               ("bid", "ask", "mid", "spread_abs", "spread_pct_of_mid", "rt_cost_3lot"))


def test_leg_metrics_one_sided_quote_is_missing():
    m = xr.leg_metrics({"bid": 0.98, "ask": None, "bid_size": 1, "ask_size": None})
    assert m["status"] == "MISSING"
    assert m["spread_abs"] is None


# --------------------------------------------------------------------------------------- #
# build_sample_row -- row schema + MISSING_<leg> status, never fabricates
# --------------------------------------------------------------------------------------- #

def test_build_sample_row_all_legs_ok():
    now = dt.datetime(2026, 9, 3, 10, 30, 0)
    symbols = {
        "spy_call": "SPY260903C00765000", "spy_put": "SPY260903P00765000",
        "xsp_call": "XSP260903C00765000", "xsp_put": "XSP260903P00765000",
    }
    quotes = {
        "SPY260903C00765000": {"bid": 0.98, "ask": 1.03, "bid_size": 345, "ask_size": 59},
        "SPY260903P00765000": {"bid": 0.90, "ask": 0.95, "bid_size": 200, "ask_size": 100},
        "XSP260903C00765000": {"bid": 2.17, "ask": 2.22, "bid_size": 10, "ask_size": 10},
        "XSP260903P00765000": {"bid": 1.05, "ask": 1.15, "bid_size": 5, "ask_size": 5},
    }
    row = xr.build_sample_row(now, 1, spy_spot=765.46, xsp_spot_est=766.1,
                               xsp_spot_method="put_call_parity_2strike",
                               spy_strike=765, xsp_strike=765,
                               symbols=symbols, quotes=quotes)
    assert row["status"] == "OK"
    assert row["schema"] == xr.SCHEMA
    assert set(row["legs"].keys()) == set(xr.LEG_ORDER)
    for leg in xr.LEG_ORDER:
        assert row["legs"][leg]["status"] == "OK"
    json.dumps(row, default=str)  # must be JSON-serializable as-is


def test_build_sample_row_missing_leg_is_labelled_never_fabricated():
    now = dt.datetime(2026, 9, 3, 10, 30, 0)
    symbols = {
        "spy_call": "SPY260903C00765000", "spy_put": "SPY260903P00765000",
        "xsp_call": "XSP260903C00765000", "xsp_put": "XSP260903P00765000",
    }
    quotes = {
        "SPY260903C00765000": {"bid": 0.98, "ask": 1.03, "bid_size": 345, "ask_size": 59},
        "SPY260903P00765000": {"bid": 0.90, "ask": 0.95, "bid_size": 200, "ask_size": 100},
        "XSP260903C00765000": {"bid": 2.17, "ask": 2.22, "bid_size": 10, "ask_size": 10},
        # xsp_put has no quote this cycle
    }
    row = xr.build_sample_row(now, 1, spy_spot=765.46, xsp_spot_est=766.1,
                               xsp_spot_method="put_call_parity_1strike",
                               spy_strike=765, xsp_strike=765,
                               symbols=symbols, quotes=quotes)
    assert row["status"] == "MISSING_XSP_PUT"
    assert row["legs"]["xsp_put"]["status"] == "MISSING"
    assert row["legs"]["xsp_put"]["bid"] is None


def test_build_sample_row_no_symbols_all_missing():
    now = dt.datetime(2026, 9, 3, 10, 30, 0)
    row = xr.build_sample_row(now, 1, spy_spot=None, xsp_spot_est=None,
                               xsp_spot_method="no_spy_spot", spy_strike=None,
                               xsp_strike=None,
                               symbols={leg: None for leg in xr.LEG_ORDER}, quotes={})
    assert row["status"] == "MISSING_SPY_CALL,MISSING_SPY_PUT,MISSING_XSP_CALL,MISSING_XSP_PUT"
    assert row["spy_spot"] is None


# --------------------------------------------------------------------------------------- #
# summarize_rows -- matched-time comparison math on a fixture tape
# --------------------------------------------------------------------------------------- #

def _fixture_row(spy_spread, xsp_spread, xsp_depth, all_ok=True):
    def ok_leg(spread, size):
        bid = 1.00
        ask = round(bid + spread, 4)
        return {"status": "OK", "bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 4),
                "bid_size": size, "ask_size": size,
                "spread_abs": round(spread, 4), "spread_pct_of_mid": round(spread / ((bid + ask) / 2), 6),
                "rt_cost_3lot": round(spread * 3 * 100, 2), "symbol": "X"}
    missing_leg = {"status": "MISSING", "bid": None, "ask": None, "mid": None,
                    "bid_size": None, "ask_size": None, "spread_abs": None,
                    "spread_pct_of_mid": None, "rt_cost_3lot": None, "symbol": "X"}
    legs = {
        "spy_call": ok_leg(spy_spread, 100),
        "spy_put": ok_leg(spy_spread, 90),
        "xsp_call": ok_leg(xsp_spread, xsp_depth) if all_ok else missing_leg,
        "xsp_put": ok_leg(xsp_spread, xsp_depth),
    }
    return {"legs": legs, "status": "OK" if all_ok else "MISSING_XSP_CALL"}


def test_summarize_rows_medians_and_depth_pct():
    rows = [
        _fixture_row(0.05, 0.05, 10),
        _fixture_row(0.05, 0.05, 10),
        _fixture_row(0.03, 0.10, 2),   # thin XSP depth sample
    ]
    stats = xr.summarize_rows(rows)
    assert stats["n_rows"] == 3
    assert stats["spy"]["median_spread_abs"] == pytest.approx(0.05, abs=1e-6)
    assert stats["xsp"]["n_leg_samples"] == 6  # 2 legs (call+put) x 3 rows, all OK = 6
    # depth<3 on row 3's two xsp legs (depth=2) out of 6 total xsp legs
    assert stats["xsp_pct_depth_below_3lot"] == pytest.approx(2 / 6 * 100, abs=0.1)


def test_summarize_rows_empty_tape_never_crashes():
    stats = xr.summarize_rows([])
    assert stats["n_rows"] == 0
    assert stats["spy"]["median_spread_abs"] is None
    assert stats["xsp_pct_depth_below_3lot"] is None


def test_summarize_rows_missing_legs_tracked_not_fabricated():
    rows = [_fixture_row(0.05, 0.05, 10, all_ok=False)]
    stats = xr.summarize_rows(rows)
    assert stats["n_missing_by_leg"]["xsp_call"] == 1
    assert stats["n_rows_all_legs_ok"] == 0


# --------------------------------------------------------------------------------------- #
# is_rth_window / prune_old_files -- same doctrine as quote_recorder.py
# --------------------------------------------------------------------------------------- #

def test_is_rth_window_weekday_boundaries():
    assert xr.is_rth_window(dt.datetime(2026, 9, 3, 9, 35))    # Thursday, start
    assert xr.is_rth_window(dt.datetime(2026, 9, 3, 15, 55))   # end
    assert not xr.is_rth_window(dt.datetime(2026, 9, 3, 9, 34))
    assert not xr.is_rth_window(dt.datetime(2026, 9, 3, 15, 56))
    assert not xr.is_rth_window(dt.datetime(2026, 9, 5, 10, 0))  # Saturday


def test_prune_old_files_deletes_only_before_cutoff(tmp_path):
    (tmp_path / "xsp-spread-tape-2026-01-01.jsonl").write_text("{}\n")
    (tmp_path / "xsp-spread-tape-2026-09-01.jsonl").write_text("{}\n")
    (tmp_path / "not-a-date-file.jsonl").write_text("{}\n")
    deleted = xr.prune_old_files(tmp_path, dt.date(2026, 6, 1))
    assert deleted == ["xsp-spread-tape-2026-01-01.jsonl"]
    assert (tmp_path / "xsp-spread-tape-2026-09-01.jsonl").exists()
    assert (tmp_path / "not-a-date-file.jsonl").exists()


# --------------------------------------------------------------------------------------- #
# Network functions -- mocked HTTP only, never a real call
# --------------------------------------------------------------------------------------- #

class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_get_spy_spot_parses_mid(monkeypatch):
    body = json.dumps({"quote": {"bp": 765.45, "ap": 765.48}}).encode()
    monkeypatch.setattr(xr.urllib.request, "urlopen", lambda req, timeout=10.0: _FakeResp(body))
    mid, err = xr.get_spy_spot({"key": "k", "secret": "s"})
    assert err is None
    assert mid == pytest.approx(765.465, abs=1e-9)


def test_get_spy_spot_no_quote_is_none_not_error(monkeypatch):
    body = json.dumps({"quote": {}}).encode()
    monkeypatch.setattr(xr.urllib.request, "urlopen", lambda req, timeout=10.0: _FakeResp(body))
    mid, err = xr.get_spy_spot({"key": "k", "secret": "s"})
    assert mid is None and err is None


def test_get_option_nbbo_batch_parses_multiple_symbols(monkeypatch):
    body = json.dumps({"quotes": {
        "SPY260903C00765000": {"bp": 0.98, "ap": 1.03, "bs": 345, "as": 59},
        "XSP260903C00765000": {"bp": 2.17, "ap": 2.22, "bs": 10, "as": 10},
    }}).encode()
    monkeypatch.setattr(xr.urllib.request, "urlopen", lambda req, timeout=10.0: _FakeResp(body))
    quotes, err = xr.get_option_nbbo_batch(
        {"key": "k", "secret": "s"}, ["SPY260903C00765000", "XSP260903C00765000"])
    assert err is None
    assert quotes["SPY260903C00765000"]["bid"] == 0.98
    assert quotes["XSP260903C00765000"]["ask_size"] == 10


def test_get_option_nbbo_batch_empty_symbols_short_circuits():
    quotes, err = xr.get_option_nbbo_batch({"key": "k", "secret": "s"}, [])
    assert quotes == {} and err is None


# --------------------------------------------------------------------------------------- #
# run_cycle -- end-to-end with mocked network, fail-open contract
# --------------------------------------------------------------------------------------- #

def test_run_cycle_no_creds_never_raises_writes_missing_row(tmp_path, monkeypatch):
    monkeypatch.setattr(xr, "et_now", lambda: dt.datetime(2026, 9, 3, 10, 0, 0))
    summary = xr.run_cycle(None, 1, dry_run=True, out_dir=tmp_path)
    assert summary["ok"] is False
    assert "_creds" in summary["errors"]
    assert summary["row_status"] is not None and summary["row_status"] != "OK"


def test_run_cycle_full_success_writes_ok_row(tmp_path, monkeypatch):
    monkeypatch.setattr(xr, "et_now", lambda: dt.datetime(2026, 9, 3, 10, 0, 0))

    def fake_spy_spot(creds):
        return 765.46, None

    def fake_batch(creds, symbols):
        # side char sits right before the 8-digit strike field, e.g. ...C00765000
        out = {}
        for sym in symbols:
            side = sym[-9]
            if sym.startswith("SPY"):
                out[sym] = ({"bid": 0.98, "ask": 1.03, "bid_size": 345, "ask_size": 59} if side == "C"
                             else {"bid": 0.90, "ask": 0.95, "bid_size": 200, "ask_size": 100})
            else:  # XSP
                out[sym] = ({"bid": 2.17, "ask": 2.22, "bid_size": 10, "ask_size": 10} if side == "C"
                             else {"bid": 1.05, "ask": 1.15, "bid_size": 5, "ask_size": 5})
        return out, None

    monkeypatch.setattr(xr, "get_spy_spot", fake_spy_spot)
    monkeypatch.setattr(xr, "get_option_nbbo_batch", fake_batch)

    creds = {"key": "k", "secret": "s"}
    summary = xr.run_cycle(creds, 1, dry_run=False, out_dir=tmp_path)
    assert summary["ok"] is True
    assert summary["rows_written"] == 1
    out_file = tmp_path / "xsp-spread-tape-2026-09-03.jsonl"
    assert out_file.exists()
    row = json.loads(out_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["status"] == "OK"
    assert row["spy_strike"] == 765
    assert row["xsp_spot_method"].startswith("put_call_parity")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
