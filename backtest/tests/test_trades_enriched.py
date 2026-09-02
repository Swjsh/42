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

# AUGUST 2026 ENGINE TOTAL -- one named constant, not a number repeated at N call sites.
# WHY IT MOVED (2026-09-02): the pin was $1,744, set on 2026-08-27 while August was STILL
# ACCRUING DAYS -- so it was guaranteed to rot, and it did. The 2026-09-01 journal/trades.csv
# writer repair (wave 2, task B8: 25 rows repaired) plus the remaining August sessions bring
# the true total to $3,048.00. Verified as a REPAIR, not a regression, by the strongest check
# available: two INDEPENDENT groupings of the same fills agree to the cent --
# flat_to_flat n=221 = $3,048.00 and broker_fills FIFO n=309 = $3,048.00, cross-basis delta
# $0.00 -- and the untouched 2026-08-27 day anchor still reads n=12 / $1,897.
# STABLE NOW in a way the old pin never was: August is CLOSED, so day-accrual can no longer
# move this. Only a further ledger repair can -- and if one does, re-verify cross-basis
# agreement FIRST (that is what proves a change is a repair rather than a regression), then
# update this one constant.
AUG_2026_ENGINE_TOTAL = 3048.0

_real_fills = os.path.join(REAL_REPO_ROOT, "automation", "state", "fills-ledger.jsonl")


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_2026_08_27_and_august_totals():
    from pathlib import Path
    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    rows = result["rows"]

    day_rows = te._engine_rows_for(rows, date="2026-08-27")
    assert len(day_rows) == 12, f"expected 12 engine round trips on 2026-08-27, got {len(day_rows)}"
    day_pnl = sum(r["pnl_dollars"] for r in day_rows)
    assert abs(day_pnl - 1897.0) <= 5, f"2026-08-27 engine pnl {day_pnl} not within $5 of +$1897"

    mon_rows = te._engine_rows_for(rows, lo="2026-08-01", hi="2026-08-31")
    mon_pnl = sum(r["pnl_dollars"] for r in mon_rows)
    assert abs(mon_pnl - AUG_2026_ENGINE_TOTAL) <= 10, (
        f"August 2026 engine pnl {mon_pnl} not within $10 of +${AUG_2026_ENGINE_TOTAL:.0f}")


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
    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    assert te.run_verification(result["rows"], quiet=True) is True


# --------------------------------------------------------------------------- #
# AUDIT-CORRECTIONS-2026-08-27: basis reconciliation between flat_to_flat
# (this module's own round-trip unit) and FIFO (broker_fills.fifo_round_trips,
# the basis behind pnl-statement.json and every journal EOD block). The
# adversarial audit that day found phantom merged-bucket positions (a THIRD,
# already-refuted basis) leaking into A/B scorecards -- these tests pin that
# the two LEGITIMATE bases always reconcile so a future regression can't
# silently reintroduce basis confusion.
# --------------------------------------------------------------------------- #

def test_every_row_carries_basis_flat_to_flat(tmp_path):
    repo, state, fleet = _mk_repo(tmp_path)
    fills = [
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "buy", "qty": 3,
         "price": 0.50, "multiplier": 100, "order_id": "OID-1", "activity_id": "ACT-1",
         "is_option": True, "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "sell", "qty": 3,
         "price": 0.70, "multiplier": 100, "order_id": "OID-2", "activity_id": "ACT-2",
         "is_option": True, "ts_utc": "2026-08-27T14:10:00Z", "ts_et": "2026-08-27T10:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    _write_jsonl(state / "core-decisions.jsonl", [])

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    assert rows[0]["basis"] == "flat_to_flat"
    assert result["meta"]["basis"] == "flat_to_flat"


def test_fifo_split_partial_exit_reconciles_to_flat_to_flat_pnl(tmp_path):
    """A single flat_to_flat trip (TP1 partial + runner exit -- one buy, TWO sell fills)
    must decompose into 2 FIFO legs whose pnl SUMS to this row's own pnl_dollars exactly.
    This is the mechanism proof for the basis-reconciliation claim: flat_to_flat is the
    coarser behavioral unit, FIFO is the finer P&L-accounting unit, and they must always
    foot to the same total for the same fills (fill-additive)."""
    repo, state, fleet = _mk_repo(tmp_path)
    fills = [
        {"arm": "bold-2", "symbol": "SPY260827C00770000", "side": "buy", "qty": 10,
         "price": 0.40, "multiplier": 100, "order_id": "OID-B", "activity_id": "ACT-B",
         "is_option": True, "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        # TP1 partial: sell 6 of 10 at a profit
        {"arm": "bold-2", "symbol": "SPY260827C00770000", "side": "sell", "qty": 6,
         "price": 0.80, "multiplier": 100, "order_id": "OID-S1", "activity_id": "ACT-S1",
         "is_option": True, "ts_utc": "2026-08-27T14:20:00Z", "ts_et": "2026-08-27T10:20:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        # runner: sell remaining 4 later at a smaller gain
        {"arm": "bold-2", "symbol": "SPY260827C00770000", "side": "sell", "qty": 4,
         "price": 0.50, "multiplier": 100, "order_id": "OID-S2", "activity_id": "ACT-S2",
         "is_option": True, "ts_utc": "2026-08-27T15:30:00Z", "ts_et": "2026-08-27T11:30:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    _write_jsonl(state / "core-decisions.jsonl", [])

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1, "TP1-partial + runner is ONE flat_to_flat position, not two"
    row = rows[0]

    assert row["fifo_trip_count"] == 2, "FIFO must split the partial exit into 2 legs"
    assert len(row["fifo_trip_ids"]) == 2
    # leg 1: 6 @ (0.80-0.40)*100 = 240.0 ; leg 2: 4 @ (0.50-0.40)*100 = 40.0
    assert row["fifo_trip_pnl_sum"] == 280.0
    assert row["pnl_dollars"] == 280.0
    assert row["fifo_trip_pnl_sum"] == row["pnl_dollars"], (
        "flat_to_flat pnl and the sum of its own FIFO legs must reconcile exactly"
    )


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_both_bases_reproduce_the_august_total():
    """Both LEGITIMATE bases -- this module's flat_to_flat (n=210 engine option trips) and
    broker_fills.fifo_round_trips (n=293 engine option trips) -- must reproduce the SAME
    August 2026 engine total (+$3,048), because P&L is fill-additive regardless of how fills
    are grouped into trips. WR/payoff differ by basis (34.8% flat_to_flat vs 44.0% FIFO,
    payoff ~2.04x vs ~1.38x, verified 2026-08-27) -- P&L does not."""
    import sys
    from pathlib import Path
    sys.path.insert(0, os.path.join(ROOT, "setup", "scripts"))
    import broker_fills as bf  # noqa: E402

    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    flat_rows = te._engine_rows_for(result["rows"], lo="2026-08-01", hi="2026-08-31")
    flat_pnl = sum(r["pnl_dollars"] for r in flat_rows)
    assert abs(flat_pnl - AUG_2026_ENGINE_TOTAL) <= 10, (
        f"flat_to_flat August pnl {flat_pnl} not within $10 of ${AUG_2026_ENGINE_TOTAL:.0f}")

    fills = bf.load_existing_ledger(Path(_real_fills))[0]
    opt_fills = [f for f in fills if f.get("is_option")]
    round_trips, _ = bf.fifo_round_trips(opt_fills)
    fifo_aug = [r for r in round_trips
                if r["attribution"] == "engine" and r["date_et"].startswith("2026-08")]
    fifo_pnl = sum(r["pnl"] for r in fifo_aug)
    assert abs(fifo_pnl - AUG_2026_ENGINE_TOTAL) <= 10, (
        f"FIFO August pnl {fifo_pnl} not within $10 of ${AUG_2026_ENGINE_TOTAL:.0f}")

    assert abs(flat_pnl - fifo_pnl) <= 0.5, (
        f"the two bases must reconcile to the same August total: "
        f"flat_to_flat={flat_pnl} vs FIFO={fifo_pnl}"
    )


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_journal_08_12_47_trips_reproduce_under_fifo():
    """journal/2026-08-12.md's EOD block reports 47 trips for that day -- broker_fills.py's
    FIFO method is the canonical one already feeding pnl-statement.json and every journal EOD
    block, so it must reproduce that count exactly on the real ledger (any attribution --
    the journal's day total is not engine-only)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, os.path.join(ROOT, "setup", "scripts"))
    import broker_fills as bf  # noqa: E402

    fills = bf.load_existing_ledger(Path(_real_fills))[0]
    opt_fills = [f for f in fills if f.get("is_option")]
    round_trips, _ = bf.fifo_round_trips(opt_fills)
    day_trips = [r for r in round_trips if r["date_et"] == "2026-08-12"]
    assert len(day_trips) == 47, (
        f"expected 47 FIFO round trips on 2026-08-12 (journal EOD block), got {len(day_trips)}"
    )
