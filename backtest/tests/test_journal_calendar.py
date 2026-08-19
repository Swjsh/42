"""JOURNAL CALENDAR guard (2026-08-19) -- setup/scripts/journal_calendar.py.

Covers the 4 things the build brief called out as RED-PROOF-worthy: (1) multi-leg exit
reconstruction produces a correct, non-null P&L instead of dropping the trade or treating
it as $0; (2) day aggregation sums correctly across multiple trades/arms; (3) win-rate-by-
day and win-rate-by-trade are computed independently and CAN diverge (a day can be a net
loser even when most of its individual trades won); (4) a date with zero trades is simply
ABSENT from the days dict -- never present with a fabricated $0 entry.

RED-PROOF (this session): reverted enrich_trip's multi-leg branch to fall back to
`t["exit_premium_avg"] = None` (mirroring the old "just drop it" failure mode this brief
warned about) -- test_multi_leg_exit_reconstructs_nonnull_pnl and
test_multi_leg_avg_exit_premium_is_dollar_weighted both FAILED as expected (avg went None /
wrong). Reverting restored 100% pass. Also temporarily made aggregate_view emit a $0.0 entry
for every date in a synthetic 3-day range regardless of trade presence -- test_day_with_
no_trades_is_absent_not_zero FAILED as expected (found a spurious zero-trade day). Reverted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import journal_calendar as jc  # noqa: E402
import fills_fifo  # noqa: E402


# =============================================================================
# 1. Multi-leg exit reconstruction -- the biggest-winner-of-the-day scar
# =============================================================================

def _write_ledger(tmp_path, rows):
    p = tmp_path / "fills-ledger.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _tp1_runner_rows():
    """Real shape from 2026-08-19 risky-1 SPY260819C00770000: buy 5@1.12, TP1 sell 3@1.65
    under order A, runner sell 2@1.82 under order B -- two DIFFERENT order_ids/prices, a
    genuine 2-leg exit. Expected real_pnl = (3*1.65 + 2*1.82 - 5*1.12) * 100 = 299.00."""
    return [
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00770000",
         "side": "buy", "qty": 5.0, "price": 1.12, "ts_et": "2026-08-19T11:50:09.995323",
         "date_et": "2026-08-19"},
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00770000",
         "side": "sell", "qty": 3.0, "price": 1.65, "ts_et": "2026-08-19T12:05:08.233648",
         "date_et": "2026-08-19"},
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00770000",
         "side": "sell", "qty": 2.0, "price": 1.82, "ts_et": "2026-08-19T12:22:07.700496",
         "date_et": "2026-08-19"},
    ]


def test_multi_leg_exit_reconstructs_nonnull_pnl(tmp_path):
    ledger = _write_ledger(tmp_path, _tp1_runner_rows())
    trips = fills_fifo.mine_real_arm_fills("test-arm", ledger_path=ledger)
    assert len(trips) == 1
    trip = trips[0]
    assert trip["exit_premium"] is None, "fills_fifo should flag this as a >1-leg exit"
    assert trip["real_pnl"] == 299.0, "fills_fifo's own FIFO net must already be exact"

    raw_rows = jc.load_raw_ledger_rows(ledger)
    enriched = jc.enrich_trip(trip, "test-arm", raw_rows, setup_idx={})

    assert enriched["multi_leg"] is True
    assert enriched["pnl_gross"] == 299.0, "must NOT be dropped or treated as $0"
    assert enriched["pnl_cross_check_ok"] is True
    assert enriched["exit_premium_avg"] is not None


def test_multi_leg_avg_exit_premium_is_dollar_weighted(tmp_path):
    ledger = _write_ledger(tmp_path, _tp1_runner_rows())
    trips = fills_fifo.mine_real_arm_fills("test-arm", ledger_path=ledger)
    raw_rows = jc.load_raw_ledger_rows(ledger)
    enriched = jc.enrich_trip(trips[0], "test-arm", raw_rows, setup_idx={})

    expected_avg = round((3 * 1.65 + 2 * 1.82) / 5.0, 4)
    assert enriched["exit_premium_avg"] == expected_avg
    assert len(enriched["legs"]) == 2
    assert {leg["qty"] for leg in enriched["legs"]} == {3.0, 2.0}


def test_multi_leg_scratch_is_not_mistaken_for_a_dropped_trade(tmp_path):
    """Real shape from 2026-08-19 bold-2 SPY260819C00771000: ONE order filled in two
    pieces (qty=2 @0.54, qty=3 @0.54) at the SAME price as the entry -- a genuine scratch
    (real_pnl == 0.0), not a data gap. The pipeline must still report it as multi_leg with
    a matched cross-check, not silently omit it or flag it as broken."""
    rows = [
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00771000",
         "side": "buy", "qty": 5.0, "price": 0.54, "ts_et": "2026-08-19T12:36:07.451832",
         "date_et": "2026-08-19"},
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00771000",
         "side": "sell", "qty": 2.0, "price": 0.54, "ts_et": "2026-08-19T12:41:06.226890",
         "date_et": "2026-08-19"},
        {"arm": "test-arm", "attribution": "engine", "symbol": "SPY260819C00771000",
         "side": "sell", "qty": 3.0, "price": 0.54, "ts_et": "2026-08-19T12:41:06.351775",
         "date_et": "2026-08-19"},
    ]
    ledger = _write_ledger(tmp_path, rows)
    trips = fills_fifo.mine_real_arm_fills("test-arm", ledger_path=ledger)
    raw_rows = jc.load_raw_ledger_rows(ledger)
    enriched = jc.enrich_trip(trips[0], "test-arm", raw_rows, setup_idx={})

    assert enriched["multi_leg"] is True
    assert enriched["pnl_gross"] == 0.0
    assert enriched["pnl_cross_check_ok"] is True
    assert enriched["exit_premium_avg"] == 0.54


# =============================================================================
# 2. Day aggregation
# =============================================================================

def _fake_trip(date, arm, real_pnl, symbol="SPY260819C00770000", qty=1, entry_premium=1.0):
    """A minimal already-enriched trip dict, bypassing fee_breakdown/setup lookup so
    aggregation tests are pure and don't depend on cost_model or decisions ledgers."""
    fees = 0.10  # arbitrary fixed per-trade fee for these synthetic cases
    return {
        "date": date, "arm": arm, "symbol": symbol, "side": "C", "strike": 770.0,
        "qty": qty, "entry_premium": entry_premium, "entry_ts_et": f"{date}T10:00:00",
        "exit_premium": entry_premium, "exit_ts_et": f"{date}T10:05:00",
        "real_pnl": real_pnl, "pnl_gross": real_pnl,
        "multi_leg": False, "legs": [], "exit_premium_avg": entry_premium,
        "pnl_cross_check_ok": True, "setup": None, "setup_matched": False,
        "fees_total_ex_cat": fees, "pnl_net_ex_cat": round(real_pnl - fees, 2),
    }


def test_day_aggregation_sums_multiple_trades_same_day():
    trips = [
        _fake_trip("2026-08-19", "safe-2", 100.0),
        _fake_trip("2026-08-19", "safe-2", -40.0),
        _fake_trip("2026-08-19", "safe-2", 25.0),
    ]
    days = jc.aggregate_view(trips)
    assert set(days.keys()) == {"2026-08-19"}
    d = days["2026-08-19"]
    assert d["trade_count"] == 3
    assert d["pnl_gross"] == 85.0  # 100 - 40 + 25
    assert d["wins_gross"] == 2 and d["losses_gross"] == 1
    # 1 arm traded that day -> exactly one $0.01 CAT fee folded into fees_total
    assert d["fees_cat"] == 0.01
    assert d["fees_total"] == round(0.10 * 3 + 0.01, 2)
    assert d["pnl_net"] == round(85.0 - d["fees_total"], 2)


def test_day_aggregation_book_view_cat_fee_once_per_arm_per_day():
    """BOOK view: 2 different arms trading the same day = 2 separate CAT fees (one per
    arm-day), not one flat $0.01 for the whole book-day."""
    trips = [
        _fake_trip("2026-08-19", "safe-2", 10.0),
        _fake_trip("2026-08-19", "bold-2", 20.0),
    ]
    days = jc.aggregate_view(trips)
    d = days["2026-08-19"]
    assert d["fees_cat"] == 0.02
    assert d["pnl_gross"] == 30.0


# =============================================================================
# 3. Win-rate-by-day vs win-rate-by-trade -- must diverge when the shapes differ
# =============================================================================

def test_win_rate_by_day_and_by_trade_are_computed_independently_and_can_diverge():
    """Day 1: three small winning trades (+10 each) and one large losing trade (-100) ->
    the DAY is a net LOSER (-70) even though 3 of 4 individual TRADES won. Day 2: a single
    losing trade. by-day win rate must come out LOWER than by-trade win rate here --
    proving the two are genuinely separate computations, not one metric relabeled."""
    trips = [
        _fake_trip("2026-08-19", "safe-2", 10.0),
        _fake_trip("2026-08-19", "safe-2", 10.0),
        _fake_trip("2026-08-19", "safe-2", 10.0),
        _fake_trip("2026-08-19", "safe-2", -100.0),
        _fake_trip("2026-08-20", "safe-2", -5.0),
    ]
    days = jc.aggregate_view(trips)
    summary = jc.compute_summary(days)

    assert days["2026-08-19"]["pnl_gross"] == -70.0  # day is a net loser
    assert days["2026-08-20"]["pnl_gross"] == -5.0

    # by-day: 0 winning days out of 2 trading days
    assert summary["win_rate_by_day_gross"] == 0.0
    # by-trade: 3 winning trades out of 5 total trades
    assert summary["win_rate_by_trade_gross"] == round(3 / 5, 4)
    assert summary["win_rate_by_day_gross"] != summary["win_rate_by_trade_gross"], (
        "by-day and by-trade win rate must be independently computed and able to diverge"
    )


# =============================================================================
# 4. A day with no trades is ABSENT, never a fabricated $0 entry
# =============================================================================

def test_day_with_no_trades_is_absent_not_zero():
    trips = [
        _fake_trip("2026-08-17", "safe-2", 50.0),
        _fake_trip("2026-08-19", "safe-2", -20.0),
        # 2026-08-18 (a real calendar date in between) has NO trades at all.
    ]
    days = jc.aggregate_view(trips)
    assert "2026-08-18" not in days, "a no-trade date must never appear as a $0 entry"
    assert set(days.keys()) == {"2026-08-17", "2026-08-19"}
    assert all(d["trade_count"] >= 1 for d in days.values())


def test_summary_empty_view_reports_none_not_zero_rates():
    """No trades at all in a view -> rates/best/worst must be None (unknown), never a
    misleading 0%/0.0 that reads as 'traded and lost every time'."""
    summary = jc.compute_summary({})
    assert summary["trading_days"] == 0
    assert summary["win_rate_by_day_gross"] is None
    assert summary["win_rate_by_trade_gross"] is None
    assert summary["best_day_gross"] is None
    assert summary["worst_day_gross"] is None


# =============================================================================
# Roster derivation -- must match accounts.json's real active/PA roster, never hardcoded
# =============================================================================

def test_load_roster_matches_current_accounts_json_active_pa_arms():
    roster = jc.load_roster()
    assert roster == ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"], (
        "if this fails, accounts.json's active/PA roster changed -- update the arms, "
        "don't hardcode around this guard"
    )


def test_load_roster_excludes_retired_and_non_pa_arms(tmp_path):
    fake_accounts = tmp_path / "accounts.json"
    fake_accounts.write_text(json.dumps({"arms": [
        {"id": "safe-2", "status": "active", "account_number": "PA111"},
        {"id": "safe-1", "status": "retired", "account_number": "PA111"},
        {"id": "mes-linear-sim", "status": "pending_build", "account_number": "5WW73759"},
    ]}), encoding="utf-8")
    roster = jc.load_roster(fake_accounts)
    assert roster == ["safe-2"]
