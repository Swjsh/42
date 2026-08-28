"""Guard tests for trades_enriched.py's EXIT-QUOTE JOIN (Task B1, 2026-08-28) --
load_quote_tape / _nearest_before_after / join_exit_quote. Pure logic, all fixtures
synthetic (never reads the real analysis/quote-tape/ directory), so these never depend on
whether the live quote_recorder.py daemon has actually run yet.
"""
import datetime as dt
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name):
    path = os.path.join(ROOT, "setup", "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


te = _load("trades_enriched")


def _write_tape(tmp_path, date, rows):
    p = tmp_path / f"{date}.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


# --------------------------------------------------------------------------------------- #
# load_quote_tape
# --------------------------------------------------------------------------------------- #

def test_load_quote_tape_indexes_by_date_arm_symbol_sorted(tmp_path):
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": "2026-08-28T11:09:20", "arm": "safe-3", "symbol": "SYM", "bid": 3.8, "ask": 3.85},
        {"ts_et": "2026-08-28T11:08:50", "arm": "safe-3", "symbol": "SYM", "bid": 3.68, "ask": 3.72},
    ])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    key = ("2026-08-28", "safe-3", "SYM")
    assert key in idx
    ts_list = [ts.isoformat() for ts, _ in idx[key]]
    assert ts_list == sorted(ts_list)  # sorted ascending regardless of file order


def test_load_quote_tape_only_reads_requested_dates(tmp_path):
    _write_tape(tmp_path, "2026-08-27", [{"ts_et": "2026-08-27T10:00:00", "arm": "a", "symbol": "S"}])
    _write_tape(tmp_path, "2026-08-28", [{"ts_et": "2026-08-28T10:00:00", "arm": "a", "symbol": "S"}])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    assert ("2026-08-27", "a", "S") not in idx
    assert ("2026-08-28", "a", "S") in idx


def test_load_quote_tape_missing_file_is_silent(tmp_path):
    assert te.load_quote_tape(tmp_path, {"2026-08-28"}) == {}


def test_load_quote_tape_skips_corrupt_lines_and_rows_missing_required_fields(tmp_path):
    p = tmp_path / "2026-08-28.jsonl"
    p.write_text(
        "{not json\n"
        + json.dumps({"ts_et": "2026-08-28T10:00:00", "arm": "a"}) + "\n"  # no symbol
        + json.dumps({"ts_et": "2026-08-28T10:00:01", "arm": "a", "symbol": "S"}) + "\n",
        encoding="utf-8",
    )
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    assert list(idx.keys()) == [("2026-08-28", "a", "S")]
    assert len(idx[("2026-08-28", "a", "S")]) == 1


# --------------------------------------------------------------------------------------- #
# _nearest_before_after
# --------------------------------------------------------------------------------------- #

def test_nearest_before_after_picks_closest_on_each_side():
    snaps = [
        (dt.datetime(2026, 8, 28, 11, 8, 30), {"tag": "t1"}),
        (dt.datetime(2026, 8, 28, 11, 8, 50), {"tag": "t2"}),
        (dt.datetime(2026, 8, 28, 11, 9, 20), {"tag": "t3"}),
    ]
    before, after = te._nearest_before_after(snaps, dt.datetime(2026, 8, 28, 11, 9, 6, 737449))
    assert before[1]["tag"] == "t2"
    assert after[1]["tag"] == "t3"


def test_nearest_before_after_exact_match_counts_as_before():
    snaps = [(dt.datetime(2026, 8, 28, 11, 9, 0), {"tag": "exact"})]
    at = dt.datetime(2026, 8, 28, 11, 9, 0)
    before, after = te._nearest_before_after(snaps, at)
    assert before[1]["tag"] == "exact"
    assert after is None


def test_nearest_before_after_all_snapshots_after_at():
    snaps = [(dt.datetime(2026, 8, 28, 11, 10, 0), {"tag": "later"})]
    before, after = te._nearest_before_after(snaps, dt.datetime(2026, 8, 28, 11, 9, 0))
    assert before is None
    assert after[1]["tag"] == "later"


def test_nearest_before_after_empty_snapshots():
    before, after = te._nearest_before_after([], dt.datetime(2026, 8, 28, 11, 9, 0))
    assert before is None and after is None


# --------------------------------------------------------------------------------------- #
# join_exit_quote -- the full pipeline, using the REAL 2026-08-28 safe-3 trade shape
# (SPY260828C00771000, exit_px_avg=3.7167, qty=3, exit_ts_et=...11:09:06.737449) from
# analysis/trades-enriched.jsonl as the fixture, with SYNTHETIC bracketing quotes.
# --------------------------------------------------------------------------------------- #

def _real_trade_row():
    return {
        "date": "2026-08-28", "arm": "safe-3", "symbol": "SPY260828C00771000",
        "exit_ts_et": "2026-08-28T11:09:06.737449", "qty": 3, "exit_px_avg": 3.7167,
    }


def test_join_exit_quote_computes_slippage_vs_nearest_before(tmp_path):
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": "2026-08-28T11:08:50", "arm": "safe-3", "symbol": "SPY260828C00771000",
         "bid": 3.68, "ask": 3.72, "mid": 3.70},
        {"ts_et": "2026-08-28T11:09:20", "arm": "safe-3", "symbol": "SPY260828C00771000",
         "bid": 3.80, "ask": 3.85, "mid": 3.825},
    ])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    out = te.join_exit_quote(_real_trade_row(), idx)
    assert out["exit_quote_bid_before"] == 3.68
    assert abs(out["exit_quote_lag_before_s"] - 16.7) < 0.1
    assert out["exit_quote_bid_after"] == 3.80
    # (3.7167 - 3.68) * 3 * 100 = 11.01
    assert abs(out["exit_slippage_vs_bid_before_dollars"] - 11.01) < 0.01
    assert out["exit_slippage_source"] == "quote_recorder"


def test_join_exit_quote_no_coverage_is_all_none(tmp_path):
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})  # empty -- no file written
    out = te.join_exit_quote(_real_trade_row(), idx)
    assert out["exit_quote_bid_before"] is None
    assert out["exit_slippage_vs_bid_before_dollars"] is None
    assert out["exit_slippage_source"] is None


def test_join_exit_quote_missing_exit_ts_is_all_none(tmp_path):
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": "2026-08-28T11:08:50", "arm": "safe-3", "symbol": "SPY260828C00771000", "bid": 3.68}])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    row = dict(_real_trade_row())
    row["exit_ts_et"] = None
    out = te.join_exit_quote(row, idx)
    assert all(v is None for v in out.values())


def test_join_exit_quote_low_confidence_beyond_max_lag(tmp_path):
    """A match that exists but sits far from the fill (beyond MAX_QUOTE_MATCH_LAG_S) is
    still RECORDED (never dropped, C7) but tagged low-confidence, never presented as a
    clean quote_recorder match."""
    far_ts = "2026-08-28T11:00:00"  # ~9 minutes before the 11:09:06 exit
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": far_ts, "arm": "safe-3", "symbol": "SPY260828C00771000", "bid": 3.0, "ask": 3.1, "mid": 3.05}])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    out = te.join_exit_quote(_real_trade_row(), idx)
    assert out["exit_quote_bid_before"] == 3.0
    assert out["exit_slippage_source"].startswith("quote_recorder_low_confidence_lag_")


def test_join_exit_quote_wrong_symbol_no_match(tmp_path):
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": "2026-08-28T11:08:50", "arm": "safe-3", "symbol": "SPY260828C00772000",
         "bid": 1.0, "ask": 1.1}])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    out = te.join_exit_quote(_real_trade_row(), idx)
    assert out["exit_quote_bid_before"] is None


def test_join_exit_quote_never_mutates_input_row(tmp_path):
    _write_tape(tmp_path, "2026-08-28", [
        {"ts_et": "2026-08-28T11:08:50", "arm": "safe-3", "symbol": "SPY260828C00771000", "bid": 3.68}])
    idx = te.load_quote_tape(tmp_path, {"2026-08-28"})
    row = _real_trade_row()
    before = dict(row)
    te.join_exit_quote(row, idx)
    assert row == before


# --------------------------------------------------------------------------------------- #
# Additive-only guarantee: enrich()/rebuild() output is unaffected when no quote-tape
# index is supplied (default behaviour, matches every row before the recorder existed).
# --------------------------------------------------------------------------------------- #

def test_enrich_defaults_to_empty_quote_tape_index_when_omitted():
    """enrich() must not require the new 5th argument -- every pre-existing call site
    (and the module's own history of calling it with 4 args) keeps working."""
    rows, matched, unmatched = te.enrich([], {}, {}, {})
    assert rows == [] and matched == 0 and unmatched == []
