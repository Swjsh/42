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


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_verification_passes():
    from pathlib import Path
    result = te.rebuild(Path(REAL_REPO_ROOT))
    assert te.run_verification(result["rows"], quiet=True) is True
