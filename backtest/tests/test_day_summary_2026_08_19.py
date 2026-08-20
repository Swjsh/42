"""Guards for setup/scripts/day_summary.py -- the counting tool that cannot lie.

WHY THESE EXIST: on 2026-08-19 the day's trade count was reported as 12 twice. The truth is
14. The miscount came from reading a DERIVED file instead of the broker, and from the two
classic counting errors this module now pins:

  * counting EXIT LEGS as separate trades (a TP1 + runner exit is ONE round trip), and
  * missing a same-symbol RE-ENTRY (flat, then bought the same 0DTE contract again -- that
    IS a second round trip).

GOLDEN CASE: the 30 real option fills the broker reported for 2026-08-19 across all 5 arms
are embedded verbatim below. They must reconstruct to exactly 14 round trips and +$266.00
gross. If either number moves, the counting rule has drifted and this test goes RED.

The rest of the tests pin the properties that make the verdict trustworthy: reconciliation
must FAIL LOUDLY on a broker/ledger divergence, a missing broker read must degrade to
UNVERIFIED (never to a silently-preferred ledger number), fees must never default to zero,
and the ET day window must be DST-aware.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import day_summary as ds  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def fill(arm, symbol, side, qty, price, hhmmss, date="2026-08-19", aid=None,
         attribution="engine"):
    return {
        "activity_id": aid or f"{arm}-{symbol}-{side}-{hhmmss}-{qty}",
        "arm": arm, "symbol": symbol, "side": side, "qty": float(qty),
        "price": float(price), "ts_et": f"{date}T{hhmmss}", "date_et": date,
        "is_crypto": "/" in symbol, "is_option": ds._is_option(symbol),
        "attribution": attribution, "order_id": None,
    }


C770 = "SPY260819C00770000"
C771 = "SPY260819C00771000"
C772 = "SPY260819C00772000"
C773 = "SPY260819C00773000"
P770 = "SPY260819P00770000"

# The broker's own FILL activities for ET day 2026-08-19, all 5 active arms, verbatim from
# /v2/account/activities/FILL (read 2026-08-19 23:4x ET). 30 option executions.
GOLDEN_2026_08_19 = [
    fill("safe-2", C771, "buy", 3, 1.15, "10:41:05"),
    fill("safe-2", C771, "sell", 3, 0.92, "10:51:04"),
    fill("safe-2", C771, "buy", 3, 0.55, "12:36:05"),
    fill("safe-2", C771, "sell", 3, 0.54, "12:41:04"),
    fill("safe-2", P770, "buy", 3, 0.97, "12:56:04"),
    fill("safe-2", P770, "sell", 3, 0.83, "13:01:04"),

    fill("bold-2", C771, "buy", 5, 1.12, "10:41:07"),
    fill("bold-2", C771, "sell", 5, 0.91, "10:51:05"),
    fill("bold-2", C770, "buy", 5, 1.38, "11:49:05"),
    fill("bold-2", C770, "sell", 5, 1.77, "12:23:05"),
    fill("bold-2", C771, "buy", 5, 0.54, "12:36:07"),
    fill("bold-2", C771, "sell", 2, 0.54, "12:41:06.226890"),
    fill("bold-2", C771, "sell", 3, 0.54, "12:41:06.351775"),

    fill("safe-3", C771, "buy", 3, 1.05, "10:42:09"),
    fill("safe-3", C771, "sell", 3, 0.97, "10:52:06"),
    fill("safe-3", C770, "buy", 3, 1.14, "11:50:07"),
    fill("safe-3", C770, "sell", 3, 1.83, "12:22:06"),
    fill("safe-3", C771, "buy", 3, 0.54, "12:37:05"),
    fill("safe-3", C771, "sell", 3, 0.55, "12:42:06"),

    fill("risky-1", C771, "buy", 5, 1.06, "10:42:10"),
    fill("risky-1", C771, "sell", 5, 0.97, "10:52:07"),
    fill("risky-1", C770, "buy", 5, 1.12, "11:50:09"),
    fill("risky-1", C770, "sell", 3, 1.65, "12:05:08"),
    fill("risky-1", C770, "sell", 2, 1.82, "12:22:07"),
    fill("risky-1", C771, "buy", 5, 0.55, "12:37:07"),
    fill("risky-1", C771, "sell", 5, 0.55, "12:42:07"),

    fill("risky-3", C773, "buy", 10, 0.33, "10:43:08"),
    fill("risky-3", C773, "sell", 10, 0.27, "10:49:07"),
    fill("risky-3", C772, "buy", 10, 0.30, "11:51:08"),
    fill("risky-3", C772, "sell", 10, 0.21, "11:55:12"),
]


# ---------------------------------------------------------------------------
# THE GOLDEN CASE -- the number that was misreported twice
# ---------------------------------------------------------------------------

def test_golden_2026_08_19_is_fourteen_round_trips_and_266_gross():
    rts, leftover = ds.round_trips(GOLDEN_2026_08_19)
    assert len(GOLDEN_2026_08_19) == 30, "fixture drifted: 30 option executions expected"
    assert len(rts) == 14, (
        f"2026-08-19 must be 14 round trips, got {len(rts)}. The reported-wrong answer was "
        f"12 (source never established -- a stale derived file, not a counting rule this "
        f"module implements). The counting rules that DO produce wrong answers here are "
        f"pinned in test_the_rejected_counting_rules_give_the_wrong_answers.")
    assert round(sum(r["gross_pnl"] for r in rts), 2) == 266.00
    assert leftover == [], f"no unclosed lots expected on 08-19, got {leftover}"


def test_the_rejected_counting_rules_give_the_wrong_answers():
    """RED-proof for the golden test: enumerate the definitions this module deliberately
    does NOT use and show each lands somewhere other than 14. Without this, a passing
    golden test proves only that the number is stable, not that the rule is the right one."""
    G = GOLDEN_2026_08_19
    per_chunk = 0  # one "trade" per FIFO-matched chunk -> splits multi-leg exits
    open_lots: dict = {}
    for f in sorted(G, key=lambda r: r["ts_et"]):
        key = (f["arm"], f["symbol"])
        q = f["qty"]
        lots = open_lots.setdefault(key, [])
        if lots and lots[0][0] != f["side"]:
            while q > 1e-9 and lots:
                take = min(lots[0][1], q)
                per_chunk += 1
                q -= take
                lots[0] = (lots[0][0], lots[0][1] - take)
                if lots[0][1] <= 1e-9:
                    lots.pop(0)
        if q > 1e-9:
            lots.append((f["side"], q))

    assert per_chunk == 16, "chunk-level FIFO splits the 2 multi-leg exits -> 16, not 14"
    assert len({(f["arm"], f["symbol"]) for f in G}) == 10, \
        "one-trip-per-(arm,symbol) blends the same-day re-entries -> 10, not 14"
    assert len(G) == 30, "counting raw executions -> 30, not 14"
    rts, _ = ds.round_trips(G)
    assert len(rts) == 14, "only the open->flat cycle rule gives 14"


def test_golden_2026_08_19_per_arm_breakdown():
    rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    by_arm = {}
    for r in rts:
        n, g = by_arm.get(r["arm"], (0, 0.0))
        by_arm[r["arm"]] = (n + 1, round(g + r["gross_pnl"], 2))
    assert by_arm == {
        "safe-2": (3, -114.00), "bold-2": (3, 90.00), "safe-3": (3, 186.00),
        "risky-1": (3, 254.00), "risky-3": (2, -150.00),
    }


def test_golden_2026_08_19_has_exactly_two_multi_leg_exits():
    """risky-1 C770 (TP1 3 @1.65 + runner 2 @1.82) and bold-2 C771 (2+3 @0.54). Each is ONE
    round trip. Counting their legs separately is exactly how 14 becomes 16."""
    rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    multi = [r for r in rts if r["n_exit_legs"] > 1]
    assert len(multi) == 2
    assert {r["arm"] for r in multi} == {"risky-1", "bold-2"}


# ---------------------------------------------------------------------------
# the counting rule, property by property
# ---------------------------------------------------------------------------

def test_multi_leg_exit_is_one_round_trip_with_weighted_exit_premium():
    fills = [
        fill("risky-1", C770, "buy", 5, 1.12, "11:50:09"),
        fill("risky-1", C770, "sell", 3, 1.65, "12:05:08"),
        fill("risky-1", C770, "sell", 2, 1.82, "12:22:07"),
    ]
    rts, leftover = ds.round_trips(fills)
    assert len(rts) == 1 and leftover == []
    rt = rts[0]
    assert rt["n_exit_legs"] == 2 and rt["n_entry_legs"] == 1
    assert rt["exit_premium_avg"] == pytest.approx((3 * 1.65 + 2 * 1.82) / 5, abs=1e-6)
    assert rt["gross_pnl"] == pytest.approx(299.00, abs=0.005)
    assert rt["exit_ts_et"].endswith("12:22:07"), "exit ts = the LAST leg"


def test_same_symbol_reentry_after_flat_is_a_second_round_trip():
    """0DTE OCC symbols are date-scoped but NOT trip-scoped. Blending a re-entry into the
    first trip is the other way 14 becomes 12."""
    fills = [
        fill("safe-2", C771, "buy", 3, 1.15, "10:41:05"),
        fill("safe-2", C771, "sell", 3, 0.92, "10:51:04"),
        fill("safe-2", C771, "buy", 3, 0.55, "12:36:05"),
        fill("safe-2", C771, "sell", 3, 0.54, "12:41:04"),
    ]
    rts, _ = ds.round_trips(fills)
    assert len(rts) == 2
    assert [r["entry_premium_avg"] for r in rts] == [1.15, 0.55]
    assert [r["gross_pnl"] for r in rts] == [-69.00, -3.00]


def test_scale_in_is_one_round_trip_with_weighted_entry():
    fills = [
        fill("bold-2", C770, "buy", 2, 1.00, "10:00:00"),
        fill("bold-2", C770, "buy", 3, 1.50, "10:05:00"),
        fill("bold-2", C770, "sell", 5, 1.40, "10:30:00"),
    ]
    rts, _ = ds.round_trips(fills)
    assert len(rts) == 1
    assert rts[0]["n_entry_legs"] == 2 and rts[0]["qty"] == 5
    assert rts[0]["entry_premium_avg"] == pytest.approx(1.30, abs=1e-6)
    assert rts[0]["gross_pnl"] == pytest.approx(50.00, abs=0.005)


def test_still_open_position_is_not_a_round_trip_and_is_surfaced():
    fills = [
        fill("safe-3", C770, "buy", 3, 1.10, "10:00:00"),
        fill("safe-3", C770, "sell", 1, 1.30, "10:30:00"),
    ]
    rts, leftover = ds.round_trips(fills)
    assert rts == []
    assert len(leftover) == 1 and leftover[0]["_anomaly"] == "still open at end of window"
    assert leftover[0]["open_qty"] == pytest.approx(2.0)


def test_crypto_is_excluded_from_option_round_trips_but_reported():
    fills = GOLDEN_2026_08_19 + [
        fill("safe-2", "BTC/USD", "buy", 0.000140949, 69553.4, "20:45:03"),
        fill("safe-2", "BTC/USD", "sell", 0.000140596, 69544.71, "20:45:04"),
    ]
    rts, _ = ds.round_trips(fills)
    assert len(rts) == 14, "crypto must not inflate the SPY round-trip count"
    cry = ds.crypto_activity(fills)
    assert cry["n_fills"] == 2, "the exclusion must be VISIBLE, not silent"
    assert cry["n_round_trips"] == 1, "fee-in-kind dust must not hide a closed crypto pair"
    assert cry["notional_pnl"] < 0


def test_sell_with_no_open_lot_is_flagged_not_swallowed():
    fills = [fill("safe-2", C771, "sell", 3, 0.92, "10:51:04")]
    rts, leftover = ds.round_trips(fills)
    assert rts == []
    assert len(leftover) == 1 and leftover[0]["_anomaly"] == "sell with no open lot"


# ---------------------------------------------------------------------------
# reconciliation must FAIL LOUDLY
# ---------------------------------------------------------------------------

def test_reconcile_clean_when_views_agree():
    rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    rec = ds.reconcile(GOLDEN_2026_08_19, GOLDEN_2026_08_19, rts, rts)
    assert rec["problems"] == []
    assert rec["broker_n_round_trips"] == rec["ledger_n_round_trips"] == 14


def test_reconcile_flags_a_fill_the_ledger_never_ingested():
    """THE 2026-08-19 FAILURE MODE: the derived file lags the broker. It must be loud."""
    ledger = GOLDEN_2026_08_19[:-2]  # ledger missed risky-3's last round trip
    b_rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    l_rts, _ = ds.round_trips(ledger)
    rec = ds.reconcile(GOLDEN_2026_08_19, ledger, b_rts, l_rts)
    assert rec["problems"], "a missing ledger fill MUST produce a problem"
    assert any("MISSING from the ledger" in p for p in rec["problems"])
    assert len(rec["only_broker"]) == 2


def test_reconcile_flags_a_pnl_divergence_even_when_counts_match():
    tampered = [dict(f) for f in GOLDEN_2026_08_19]
    tampered[1] = {**tampered[1], "price": 9.99}  # same ids, different money
    b_rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    l_rts, _ = ds.round_trips(tampered)
    rec = ds.reconcile(GOLDEN_2026_08_19, tampered, b_rts, l_rts)
    assert rec["broker_n_round_trips"] == rec["ledger_n_round_trips"] == 14
    assert any("gross P&L differs" in p for p in rec["problems"])


def test_exit_codes_are_distinct_and_nonzero_for_every_failure():
    assert ds.EXIT_OK == 0
    assert ds.EXIT_UNRECONCILED != 0
    assert ds.EXIT_BROKER_UNREACHABLE != 0
    assert len({ds.EXIT_OK, ds.EXIT_USAGE, ds.EXIT_UNRECONCILED,
                ds.EXIT_BROKER_UNREACHABLE}) == 4


def test_back_dated_run_does_not_present_live_equity_as_historical():
    """/v2/account and /v2/positions have no as-of form. Printing today's equity beside an
    old day's trades is the same class of quiet mislabelling that produced the bad count."""
    rep = ds.build("2026-08-18", use_broker=False)
    assert rep["is_today_et"] is False
    assert "open_positions_live" in rep and "open_positions" not in rep
    for arm_stats in rep["per_arm"].values():
        assert "equity_live" in arm_stats and "equity" not in arm_stats
    rendered = ds.render(rep)
    assert "BACK-DATED" in rendered
    assert "live-now broker read, not an as-of-date value" in rendered


def test_no_broker_read_is_UNVERIFIED_never_a_silent_ledger_answer():
    """A broker that cannot be read must NOT degrade to 'use the derived file and call it
    truth' -- that is precisely the bug this module was built to kill."""
    rep = ds.build("2026-08-19", use_broker=False)
    assert rep["verdict"] == "UNVERIFIED"
    assert rep["exit_code"] == ds.EXIT_BROKER_UNREACHABLE != 0
    assert "UNVERIFIED" in rep["authority"]


# ---------------------------------------------------------------------------
# costs must never default to zero
# ---------------------------------------------------------------------------

def test_unposted_fees_report_NOT_POSTED_and_never_zero():
    rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    by_arm = {}
    for r in rts:
        by_arm.setdefault(r["arm"], []).append(r)
    fees = ds.fee_summary({a: [] for a in by_arm}, by_arm)
    assert fees["status"] == "NOT_POSTED"
    assert fees["actual_total"] is None, "a missing fee must be None, never 0.0"
    assert fees["modelled_available"] and fees["modelled_total"] > 0


def test_posted_fees_are_summed_from_the_broker_rows():
    rts, _ = ds.round_trips(GOLDEN_2026_08_19)
    by_arm = {}
    for r in rts:
        by_arm.setdefault(r["arm"], []).append(r)
    rows = {"safe-2": [{"activity_sub_type": "OCC", "net_amount": "-0.08"},
                       {"activity_sub_type": "ORF", "net_amount": "-0.09"}]}
    rows.update({a: [] for a in by_arm if a != "safe-2"})
    fees = ds.fee_summary(rows, by_arm)
    assert fees["status"] == "POSTED"
    assert fees["actual_total"] == pytest.approx(-0.17, abs=1e-6)
    assert fees["by_arm"]["safe-2"]["by_sub_type"] == {"OCC": -0.08, "ORF": -0.09}


# ---------------------------------------------------------------------------
# time discipline
# ---------------------------------------------------------------------------

def test_et_day_window_is_dst_aware_not_a_hardcoded_offset():
    edt_start, edt_end = ds.et_day_utc_window("2026-08-19")      # EDT, UTC-4
    est_start, est_end = ds.et_day_utc_window("2026-01-15")      # EST, UTC-5
    assert edt_start == "2026-08-19T04:00:00Z" and edt_end == "2026-08-20T04:00:00Z"
    assert est_start == "2026-01-15T05:00:00Z" and est_end == "2026-01-16T05:00:00Z"


def test_active_arms_are_derived_from_accounts_json_not_hardcoded():
    arms = ds.active_arms()
    assert set(arms) == {"safe-2", "bold-2", "safe-3", "risky-1", "risky-3"}
    assert "safe-1" not in arms, "retired arm must not be counted"


def test_option_vs_crypto_classification():
    assert ds._is_option(C771) and not ds._is_crypto(C771)
    assert ds._is_crypto("BTC/USD") and not ds._is_option("BTC/USD")
    assert not ds._is_option("SPY")
