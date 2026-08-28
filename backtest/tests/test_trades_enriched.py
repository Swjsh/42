"""Guard tests for trades_enriched.py (built 2026-08-27).

Pins the join mechanics (order_id join beats the (date,arm,symbol) fallback), the
2026-08-27 / August-2026 known-good engine totals against the REAL repo ledgers, and
that unmatched rows are LISTED in _meta.unmatched, never silently dropped (C7).
"""
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name):
    path = os.path.join(ROOT, "setup", "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


te = _load("trades_enriched")


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# Synthetic-fixture tests: pin the join mechanics in isolation.
# --------------------------------------------------------------------------- #

def _mk_repo(tmp_path):
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True)
    fleet = state / "fleet"
    fleet.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    return tmp_path, state, fleet


def test_order_id_join_beats_symbol_fallback(tmp_path):
    """Two ENTER rows share the same (date, arm, symbol) key (a same-day re-entry on the
    same strike) but carry DIFFERENT setups. The round trip's buy order_id matches the
    SECOND row's broker id -- the join must pick that row's context, not the first one
    the (date,arm,symbol) fallback would find."""
    repo, state, fleet = _mk_repo(tmp_path)

    fills = [
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "buy", "qty": 3,
         "price": 0.50, "multiplier": 100, "order_id": "ORDER-B", "is_option": True,
         "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "sell", "qty": 3,
         "price": 0.70, "multiplier": 100, "order_id": "ORDER-S", "is_option": True,
         "ts_utc": "2026-08-27T14:10:00Z", "ts_et": "2026-08-27T10:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)

    core_rows = [
        {"ts_et": "2026-08-27T09:00:00", "account": "safe", "verdict": "ENTER_BULL",
         "setup": "WRONG_EARLIER_ROW", "reason": "tier ELITE",
         "exec": {"symbol": "SPY260827C00768000", "broker": {"id": "ORDER-A"}}},
        {"ts_et": "2026-08-27T09:59:00", "account": "safe", "verdict": "ENTER_BULL",
         "setup": "CORRECT_ROW", "reason": "tier SUPER",
         "exec": {"symbol": "SPY260827C00768000", "broker": {"id": "ORDER-B"}}},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    row = rows[0]
    assert row["ctx_matched"] is True
    assert row["setup"] == "CORRECT_ROW", (
        "order_id join must win over the (date,arm,symbol) fallback -- "
        f"got {row['setup']!r}"
    )
    assert row["tier"] == "SUPER"


def test_symbol_fallback_used_when_no_order_id_match(tmp_path):
    repo, state, fleet = _mk_repo(tmp_path)
    fills = [
        {"arm": "bold-2", "symbol": "SPY260827P00765000", "side": "buy", "qty": 2,
         "price": 0.40, "multiplier": 100, "order_id": "ORDER-UNMATCHED", "is_option": True,
         "ts_utc": "2026-08-27T15:00:00Z", "ts_et": "2026-08-27T11:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "bold-2", "symbol": "SPY260827P00765000", "side": "sell", "qty": 2,
         "price": 0.20, "multiplier": 100, "order_id": "ORDER-S2", "is_option": True,
         "ts_utc": "2026-08-27T15:05:00Z", "ts_et": "2026-08-27T11:05:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-08-27T10:55:00", "account": "bold", "verdict": "ENTER_BEAR",
         "setup": "FALLBACK_MATCHED", "reason": "tier TRENDLINE",
         "exec": {"symbol": "SPY260827P00765000", "broker": {"id": "ORDER-DIFFERENT"}}},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    assert rows[0]["ctx_matched"] is True
    assert rows[0]["setup"] == "FALLBACK_MATCHED"


def test_unmatched_rows_are_listed_not_dropped(tmp_path):
    repo, state, fleet = _mk_repo(tmp_path)
    fills = [
        {"arm": "risky-1", "symbol": "SPY260827C00770000", "side": "buy", "qty": 4,
         "price": 0.30, "multiplier": 100, "order_id": "NOMATCH-B", "is_option": True,
         "ts_utc": "2026-08-27T16:00:00Z", "ts_et": "2026-08-27T12:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "risky-1", "symbol": "SPY260827C00770000", "side": "sell", "qty": 4,
         "price": 0.10, "multiplier": 100, "order_id": "NOMATCH-S", "is_option": True,
         "ts_utc": "2026-08-27T16:05:00Z", "ts_et": "2026-08-27T12:05:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    _write_jsonl(state / "core-decisions.jsonl", [])  # no decision rows at all

    result = te.rebuild(repo)
    meta = json.loads((repo / "analysis" / "trades-enriched.jsonl").read_text().splitlines()[0])
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    assert rows[0]["ctx_matched"] is False
    assert meta["unmatched"] == [["2026-08-27", "risky-1", "SPY260827C00770000"]]


def test_same_symbol_reentry_same_day_splits_into_separate_trips(tmp_path):
    """AUDIT FIX (2026-08-27, A3): a symbol re-entered same day (buy->flat->buy->flat) must
    become TWO separate rows, each with its OWN hold_min/entry_px/ctx -- not one merged row
    whose hold_min spans the gap between the two unrelated trips. Real-tape case that caught
    this: 2026-06-30 safe-1 SPY260630C00750000 reported hold_min=170 pre-fix (merged); the
    two real legs individually held 6.0 and ~31 min."""
    repo, state, fleet = _mk_repo(tmp_path)

    fills = [
        # trip 1: buy -> sell, flat.
        {"arm": "safe-1", "symbol": "SPY260630C00750000", "side": "buy", "qty": 3,
         "price": 0.12, "multiplier": 100, "order_id": "OID-A1", "is_option": True,
         "ts_utc": "2026-06-30T16:55:05Z", "ts_et": "2026-06-30T12:55:05",
         "date_et": "2026-06-30", "attribution": "engine"},
        {"arm": "safe-1", "symbol": "SPY260630C00750000", "side": "sell", "qty": 3,
         "price": 0.09, "multiplier": 100, "order_id": "OID-A2", "is_option": True,
         "ts_utc": "2026-06-30T17:01:04Z", "ts_et": "2026-06-30T13:01:04",
         "date_et": "2026-06-30", "attribution": "engine"},
        # trip 2: a FRESH buy after trip 1 is flat -- must NOT merge with trip 1.
        {"arm": "safe-1", "symbol": "SPY260630C00750000", "side": "buy", "qty": 3,
         "price": 0.08, "multiplier": 100, "order_id": "OID-B1", "is_option": True,
         "ts_utc": "2026-06-30T17:14:02Z", "ts_et": "2026-06-30T13:14:02",
         "date_et": "2026-06-30", "attribution": "engine"},
        {"arm": "safe-1", "symbol": "SPY260630C00750000", "side": "sell", "qty": 3,
         "price": 0.02, "multiplier": 100, "order_id": "OID-B2", "is_option": True,
         "ts_utc": "2026-06-30T17:45:05Z", "ts_et": "2026-06-30T13:45:05",
         "date_et": "2026-06-30", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-06-30T12:54:10", "account": "safe", "verdict": "ENTER_BULL",
         "setup": "TRIP_1_SETUP", "reason": "tier ELITE",
         "exec": {"symbol": "SPY260630C00750000", "stop": 0.10, "broker": {"id": "OID-A1"}}},
        {"ts_et": "2026-06-30T13:13:20", "account": "safe", "verdict": "ENTER_BULL",
         "setup": "TRIP_2_SETUP", "reason": "tier BASE",
         "exec": {"symbol": "SPY260630C00750000", "stop": 0.06, "broker": {"id": "OID-B1"}}},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = sorted((r for r in result["rows"] if not r.get("_meta")),
                  key=lambda r: r["entry_ts_et"])
    assert len(rows) == 2, f"same-day re-entry must yield 2 rows, got {len(rows)}"

    t1, t2 = rows
    assert t1["setup"] == "TRIP_1_SETUP" and t1["planned_stop"] == 0.10
    assert t1["hold_min"] == 6.0, f"trip 1 hold_min must be its OWN ~6min, got {t1['hold_min']}"
    assert t1["entry_px"] == 0.12
    assert t1["pnl_dollars"] == -9.0

    assert t2["setup"] == "TRIP_2_SETUP" and t2["planned_stop"] == 0.06
    assert t2["hold_min"] == 31.1, f"trip 2 hold_min must be its OWN ~31min, got {t2['hold_min']}"
    assert t2["entry_px"] == 0.08
    assert t2["pnl_dollars"] == -18.0

    # aggregate pnl must still be exactly the sum (additive correctness preserved)
    assert round(t1["pnl_dollars"] + t2["pnl_dollars"], 2) == -27.0


def test_unbalanced_round_trip_emitted_not_dropped(tmp_path):
    repo, state, fleet = _mk_repo(tmp_path)
    fills = [
        # buy qty 5, sell qty 3 -- never flattened -- must still appear, flagged.
        {"arm": "safe-3", "symbol": "SPY260827C00772000", "side": "buy", "qty": 5,
         "price": 0.25, "multiplier": 100, "order_id": "OID-1", "is_option": True,
         "ts_utc": "2026-08-27T17:00:00Z", "ts_et": "2026-08-27T13:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-3", "symbol": "SPY260827C00772000", "side": "sell", "qty": 3,
         "price": 0.35, "multiplier": 100, "order_id": "OID-2", "is_option": True,
         "ts_utc": "2026-08-27T17:05:00Z", "ts_et": "2026-08-27T13:05:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    _write_jsonl(state / "core-decisions.jsonl", [])

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1, "an unbalanced round trip must still be emitted, never dropped"
    assert rows[0]["unbalanced"] is True
    assert rows[0]["pnl_dollars"] is None, "never fabricate a pnl for an unbalanced trip"


# --------------------------------------------------------------------------- #
# Real-tape known-good checks (pins the exact numbers CLAUDE.md's build task named).
# --------------------------------------------------------------------------- #

REAL_REPO_ROOT = ROOT
_real_fills = os.path.join(REAL_REPO_ROOT, "automation", "state", "fills-ledger.jsonl")


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_2026_08_27_and_august_totals():
    from pathlib import Path
    result = te.rebuild(Path(REAL_REPO_ROOT))
    rows = result["rows"]

    day_rows = te._engine_rows_for(rows, date="2026-08-27")
    assert len(day_rows) == 12, f"expected 12 engine round trips on 2026-08-27, got {len(day_rows)}"
    day_pnl = sum(r["pnl_dollars"] for r in day_rows)
    assert abs(day_pnl - 1897.0) <= 5, f"2026-08-27 engine pnl {day_pnl} not within $5 of +$1897"

    mon_rows = te._engine_rows_for(rows, lo="2026-08-01", hi="2026-08-31")
    mon_pnl = sum(r["pnl_dollars"] for r in mon_rows)
    assert abs(mon_pnl - 1744.0) <= 10, f"August 2026 engine pnl {mon_pnl} not within $10 of +$1744"


def test_premium_stop_suspect_flags_impossible_positive_pnl(tmp_path):
    """AUDIT DISCLOSURE (2026-08-27, A3): exit_manager.py's stage="premium_stop" label is
    known to be reused for ratcheted ladder/trail floor exits that are NOT catastrophe-cap
    hits (see module docstring). A raw premium/catastrophe stop can never close at a
    profit, so a "premium_stop"-tagged row with positive pnl_dollars must be flagged
    exit_reason_premium_stop_suspect=True (proof, not fabrication) -- and a row whose exit
    price closed ABOVE the raw stop level set at entry (planned_stop) must be flagged too,
    even when still a net loss. A row with no premium_stop tag must be flagged None (n/a)."""
    repo, state, fleet = _mk_repo(tmp_path)

    fills = [
        # SUSPECT #1: tagged premium_stop but closed at a PROFIT -- impossible for a raw stop.
        {"arm": "bold-2", "symbol": "SPY260827C00770000", "side": "buy", "qty": 3,
         "price": 0.50, "multiplier": 100, "order_id": "OID-P1", "is_option": True,
         "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "bold-2", "symbol": "SPY260827C00770000", "side": "sell", "qty": 3,
         "price": 0.65, "multiplier": 100, "order_id": "OID-P2", "is_option": True,
         "ts_utc": "2026-08-27T14:10:00Z", "ts_et": "2026-08-27T10:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        # CLEAN: tagged premium_stop, closed at a genuine deep loss consistent with the raw
        # planned_stop (0.40) -- nothing in this row's own data disproves the tag.
        {"arm": "bold-2", "symbol": "SPY260827P00765000", "side": "buy", "qty": 3,
         "price": 0.50, "multiplier": 100, "order_id": "OID-Q1", "is_option": True,
         "ts_utc": "2026-08-27T15:00:00Z", "ts_et": "2026-08-27T11:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "bold-2", "symbol": "SPY260827P00765000", "side": "sell", "qty": 3,
         "price": 0.40, "multiplier": 100, "order_id": "OID-Q2", "is_option": True,
         "ts_utc": "2026-08-27T15:05:00Z", "ts_et": "2026-08-27T11:05:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-08-27T09:59:00", "account": "bold", "verdict": "ENTER_BULL",
         "setup": "PROFIT_ROW", "reason": "tier ELITE",
         "exec": {"symbol": "SPY260827C00770000", "stop": 0.40, "broker": {"id": "OID-P1"}},
         "exit_pass": [{"symbol": "SPY260827C00770000", "actions": [
             {"kind": "SELL_ALL", "placed": True, "stage": "premium_stop",
              "reason": "premium_stop @ 0.65"}]}]},
        {"ts_et": "2026-08-27T10:59:00", "account": "bold", "verdict": "ENTER_BEAR",
         "setup": "CLEAN_STOP_ROW", "reason": "tier ELITE",
         "exec": {"symbol": "SPY260827P00765000", "stop": 0.40, "broker": {"id": "OID-Q1"}},
         "exit_pass": [{"symbol": "SPY260827P00765000", "actions": [
             {"kind": "SELL_ALL", "placed": True, "stage": "premium_stop",
              "reason": "premium_stop @ 0.40"}]}]},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = {r["symbol"]: r for r in result["rows"] if not r.get("_meta")}

    profit_row = rows["SPY260827C00770000"]
    assert profit_row["exit_reason"] == "premium_stop"
    assert profit_row["pnl_dollars"] == 45.0
    assert profit_row["exit_reason_premium_stop_suspect"] is True

    clean_row = rows["SPY260827P00765000"]
    assert clean_row["exit_reason"] == "premium_stop"
    assert clean_row["pnl_dollars"] == -30.0
    assert clean_row["exit_reason_premium_stop_suspect"] is False

    meta = json.loads((repo / "analysis" / "trades-enriched.jsonl").read_text().splitlines()[0])
    assert meta["exit_reason_premium_stop_tagged"] == 2
    assert meta["exit_reason_premium_stop_suspect"] == 1


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_verification_passes():
    from pathlib import Path
    result = te.rebuild(Path(REAL_REPO_ROOT))
    assert te.run_verification(result["rows"], quiet=True) is True
