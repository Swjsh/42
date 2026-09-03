"""Guard tests for trades_enriched.py (built 2026-08-27).

Pins the join mechanics (order_id join beats the (date,arm,symbol) fallback), the
2026-08-27 / August-2026 known-good engine totals against the REAL repo ledgers, and
that unmatched rows are LISTED in _meta.unmatched, never silently dropped (C7).
"""
import importlib.util
import json
import os
from pathlib import Path

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
# TRADES-ENRICHED-HAS-NO-SCHEDULED-PRODUCER guard (filed 2026-09-01, fixed 2026-09-02):
# this module's real-tape tests deliberately read the production ledger via
# te.rebuild(Path(REAL_REPO_ROOT), write=False). OBSERVED THIS SESSION (before write=False
# existed): a bare te.rebuild(REAL_REPO_ROOT) -- write defaulting True -- silently reverted
# a just-fixed production artifact as a side effect of merely running this suite, caught
# only by re-checking the invariant afterwards. This autouse fixture makes that class of
# regression fail LOUD and IMMEDIATELY instead of relying on a human noticing later: it
# snapshots the real artifact's mtime+size before this module's tests run and asserts both
# are unchanged after, so any test that regresses to a write=True call against the real
# repo root trips this on the very next run.
# --------------------------------------------------------------------------- #

_REAL_ARTIFACT_PATH = Path(ROOT) / "analysis" / "trades-enriched.jsonl"


@pytest.fixture(scope="module", autouse=True)
def _real_trades_enriched_artifact_untouched():
    mtime_before = _REAL_ARTIFACT_PATH.stat().st_mtime if _REAL_ARTIFACT_PATH.exists() else None
    size_before = _REAL_ARTIFACT_PATH.stat().st_size if _REAL_ARTIFACT_PATH.exists() else None
    yield
    mtime_after = _REAL_ARTIFACT_PATH.stat().st_mtime if _REAL_ARTIFACT_PATH.exists() else None
    size_after = _REAL_ARTIFACT_PATH.stat().st_size if _REAL_ARTIFACT_PATH.exists() else None
    assert mtime_after == mtime_before, (
        f"analysis/trades-enriched.jsonl mtime changed while this test module ran "
        f"({mtime_before} -> {mtime_after}) -- some test wrote to the REAL production "
        f"artifact as a side effect instead of using write=False / a tmp_path repo."
    )
    assert size_after == size_before, (
        f"analysis/trades-enriched.jsonl size changed while this test module ran "
        f"({size_before} -> {size_after}) -- same class of regression as the mtime check."
    )


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

# AUGUST 2026 ENGINE TOTAL, THROUGH 2026-08-27 -- mirrors setup/scripts/trades_enriched.py's
# own AUG_THROUGH_2026_08_27_ENGINE_TOTAL (kept as a separate literal here deliberately, same
# as before -- this test module pins the number independently rather than importing the
# module's constant, so a source-side typo can't silently launder itself into the guard).
#
# TRADES-ENRICHED-AUGUST-ANCHOR-IS-STALE-BY-CONSTRUCTION (queue.md, filed 2026-08-29, fixed
# 2026-09-03): this was a WHOLE-CALENDAR-MONTH assertion (lo=08-01, hi=08-31, pinned at
# $3,048) -- itself a prior hand-bump away from the original $1,744 pin, which is the exact
# anti-pattern the queue item forbids ("do NOT simply bump the number"). Replaced with a
# DATE-ANCHORED PREFIX assertion through 2026-08-27 (a closed window: no ordinary trading day
# can ever add a fill dated <= 08-27), matching the already-passing per-day anchor's style.
# Verified live 2026-09-03: cumulative 2026-08-01..2026-08-27 = n=210, pnl=+$1,744.00 exactly.
AUG_THROUGH_2026_08_27_ENGINE_TOTAL = 1744.0
AUG_PREFIX_HI = "2026-08-27"

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

    prefix_rows = te._engine_rows_for(rows, lo="2026-08-01", hi=AUG_PREFIX_HI)
    prefix_pnl = sum(r["pnl_dollars"] for r in prefix_rows)
    assert abs(prefix_pnl - AUG_THROUGH_2026_08_27_ENGINE_TOTAL) <= 10, (
        f"August 2026 engine pnl through {AUG_PREFIX_HI} {prefix_pnl} not within $10 of "
        f"+${AUG_THROUGH_2026_08_27_ENGINE_TOTAL:.0f}")


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
    """Both LEGITIMATE bases -- this module's flat_to_flat and broker_fills.fifo_round_trips
    -- must reproduce the SAME August-2026-THROUGH-08-27 engine total (+$1,744), because P&L
    is fill-additive regardless of how fills are grouped into trips. Bounded to the same
    closed prefix window as the primary anchor above (see AUG_THROUGH_2026_08_27_ENGINE_TOTAL's
    docstring) rather than the whole calendar month, so this stays a real reconciliation check
    forever instead of rotting as soon as a new August fill (backfill/repair) lands. WR/payoff
    differ by basis -- P&L does not."""
    import sys
    from pathlib import Path
    sys.path.insert(0, os.path.join(ROOT, "setup", "scripts"))
    import broker_fills as bf  # noqa: E402

    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    flat_rows = te._engine_rows_for(result["rows"], lo="2026-08-01", hi=AUG_PREFIX_HI)
    flat_pnl = sum(r["pnl_dollars"] for r in flat_rows)
    assert abs(flat_pnl - AUG_THROUGH_2026_08_27_ENGINE_TOTAL) <= 10, (
        f"flat_to_flat August-through-{AUG_PREFIX_HI} pnl {flat_pnl} not within $10 of "
        f"${AUG_THROUGH_2026_08_27_ENGINE_TOTAL:.0f}")

    fills = bf.load_existing_ledger(Path(_real_fills))[0]
    opt_fills = [f for f in fills if f.get("is_option")]
    round_trips, _ = bf.fifo_round_trips(opt_fills)
    fifo_aug = [r for r in round_trips
                if r["attribution"] == "engine" and "2026-08-01" <= r["date_et"] <= AUG_PREFIX_HI]
    fifo_pnl = sum(r["pnl"] for r in fifo_aug)
    assert abs(fifo_pnl - AUG_THROUGH_2026_08_27_ENGINE_TOTAL) <= 10, (
        f"FIFO August-through-{AUG_PREFIX_HI} pnl {fifo_pnl} not within $10 of "
        f"${AUG_THROUGH_2026_08_27_ENGINE_TOTAL:.0f}")

    assert abs(flat_pnl - fifo_pnl) <= 0.5, (
        f"the two bases must reconcile to the same August-through-{AUG_PREFIX_HI} total: "
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
