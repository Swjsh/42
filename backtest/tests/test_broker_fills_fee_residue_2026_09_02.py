"""Guard: crypto fee-in-kind residue must not be reported as an open position.

THE BUG (queue.md CANARY-OUT-OF-SAFE-2, root-caused 2026-09-02). pnl-statement.json carried
16 open lots while a live /v2/positions read returned ZERO positions on every one of the five
live arms. The queue item called it "float dust vs the 1e-9 threshold". It is not dust:

    safe-1/UNI   bought 103.36473641  sold 103.10632456  residue 0.25841185  = 0.2500%
    bold-2/UNI   bought 280.57525989  sold 279.87382174  residue 0.70143815  = 0.2500%
    safe-2/BTC   bought   0.00969716  sold   0.00967288  residue 0.00002428  = 0.2504%

ALL SIXTEEN were 0.2500% of quantity bought, across 6 arms and 6 symbols, with residues
spanning 4.2e-06 BTC to 0.70 UNI. That is Alpaca's crypto taker fee, charged IN THE BASE
ASSET: buy 100 UNI, pay 0.25 UNI in fees, and only 99.75 UNI is ever sellable. 0.70 UNI is
~$2 -- raising an absolute epsilon until it swallowed that would also swallow real positions.

WHY THE FIX IS A CLASSIFIER, NOT A MATCHER CHANGE. The first attempt popped fee-sized lots
inside the FIFO loop and silently destroyed 90 of 790 round-trip rows, because a popped lot
is no longer available for a later fill to match against. The round trips and their P&L were
never wrong -- only the leftover REPORT was. Verified on the real ledger: round trips
790 -> 790, realized P&L $1,283.45 -> $1,283.45 unchanged to the cent, open lots 16 -> 0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "setup" / "scripts" / "broker_fills.py"

FEE = 0.0025  # Alpaca crypto taker fee, measured from the live ledger (see docstring)


@pytest.fixture(scope="module")
def bf():
    spec = importlib.util.spec_from_file_location("broker_fills_g", MOD)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["broker_fills_g"] = m
    spec.loader.exec_module(m)
    return m


_N = 0


def _fill(arm, symbol, side, qty, price, multiplier=1.0):
    global _N
    _N += 1
    return {"arm": arm, "symbol": symbol, "side": side, "qty": float(qty),
            "price": float(price), "multiplier": multiplier, "activity_id": f"a{_N}",
            "ts_utc": f"2026-08-31T00:00:{_N:02d}Z", "ts_et": f"2026-08-30T20:00:{_N:02d}",
            "date_et": "2026-08-30", "attribution": "manual"}


# ---------------------------------------------------------------------------------------
# The fee residue clears
# ---------------------------------------------------------------------------------------

def test_a_fee_closed_crypto_position_reports_no_open_lot(bf):
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "sell", 100.0 * (1 - FEE), 2.85)]
    rts, lots = bf.fifo_round_trips(fills)
    assert lots == [], f"fee residue reported as an open position: {lots}"
    assert len(rts) == 1, "the round trip itself must survive the classification"


def test_the_round_trip_pnl_is_untouched_by_the_classifier(bf):
    """The classifier must never change a number. It only decides what to REPORT as open."""
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "sell", 100.0 * (1 - FEE), 2.85)]
    rts, _ = bf.fifo_round_trips(fills)
    assert rts[0]["qty"] == pytest.approx(99.75)
    assert rts[0]["pnl"] == pytest.approx(round((2.85 - 2.80) * 99.75, 2))


def test_multi_lot_scale_in_then_full_exit_clears(bf):
    """The live failures were multi-fill symbols (UNI had 10-12 fills per arm). Residue from
    an EARLY lot must clear even though it is stranded on a LATER lot."""
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "buy", 50.0, 2.82),
             _fill("safe-2", "UNI/USD", "sell", 150.0 * (1 - FEE), 2.90)]
    _, lots = bf.fifo_round_trips(fills)
    assert lots == [], f"stranded multi-lot fee residue: {lots}"


# ---------------------------------------------------------------------------------------
# A REAL position must still be reported. This is the half that matters.
# ---------------------------------------------------------------------------------------

def test_a_genuinely_open_crypto_position_is_still_reported(bf):
    fills = [_fill("safe-2", "BTC/USD", "buy", 1.0, 60000.0),
             _fill("safe-2", "BTC/USD", "sell", 0.5, 61000.0)]
    _, lots = bf.fifo_round_trips(fills)
    assert len(lots) == 1 and lots[0]["qty"] == pytest.approx(0.5), (
        "half a Bitcoin was classified as fee residue -- the tolerance is not bounded"
    )


def test_a_position_just_over_tolerance_is_reported(bf):
    """Boundary. 1% unmatched is 4x the fee and must never be absorbed."""
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "sell", 99.0, 2.85)]
    _, lots = bf.fifo_round_trips(fills)
    assert len(lots) == 1 and lots[0]["qty"] == pytest.approx(1.0)


def test_an_unmatched_SELL_residue_is_never_dropped(bf):
    """A fee deduction can only ever leave you holding LESS than you bought. An unmatched
    SELL means something else is wrong (a missing buy, a truncated feed) and must stay
    loudly visible."""
    fills = [_fill("safe-2", "UNI/USD", "sell", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "buy", 100.0 * (1 - FEE), 2.75)]
    _, lots = bf.fifo_round_trips(fills)
    assert len(lots) == 1 and lots[0]["side"] == "sell", (
        "an unmatched short residue was silently dropped as if it were a buy-side fee"
    )


def test_options_are_never_touched(bf):
    """Integer quantities, no fee-in-kind. A relative tolerance here would only add a way to
    be wrong -- so OCC symbols keep the exact epsilon.

    THE QUANTITIES ARE CHOSEN TO REACH THE CRYPTO CHECK. An obvious fixture (buy 3, sell 2)
    leaves 33% unmatched, which the GROUP-completeness test rejects first -- so the crypto
    restriction is never consulted and a mutation removing it passes. Found in RED-proof.
    300/299 leaves 0.33% unmatched, inside the 0.5% tolerance, so only `_is_crypto_symbol`
    stands between this open contract and being silently dropped.
    """
    fills = [_fill("safe-2", "SPY260902C00650000", "buy", 300.0, 1.20, multiplier=100.0),
             _fill("safe-2", "SPY260902C00650000", "sell", 299.0, 1.50, multiplier=100.0)]
    _, lots = bf.fifo_round_trips(fills)
    assert len(lots) == 1 and lots[0]["qty"] == pytest.approx(1.0), (
        "an open option CONTRACT was classified as crypto fee residue -- options have no "
        "fee-in-kind and must never be absorbed"
    )


def test_one_arms_residue_does_not_clear_another_arms_position(bf):
    """Classification is per (arm, symbol) group, like the matching itself. Arms are
    separate accounts with isolated risk (Rule 5) and must never be pooled."""
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "sell", 100.0 * (1 - FEE), 2.85),
             _fill("bold-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("bold-2", "UNI/USD", "sell", 40.0, 2.85)]
    _, lots = bf.fifo_round_trips(fills)
    assert len(lots) == 1 and lots[0]["arm"] == "bold-2"
    assert lots[0]["qty"] == pytest.approx(60.0)


def test_the_tolerance_is_bounded_and_documented(bf):
    """A tolerance nobody can see is a tolerance that grows. Pin the constant."""
    assert bf.CRYPTO_FEE_CLOSEOUT_TOLERANCE == 0.005
    assert bf.CRYPTO_FEE_CLOSEOUT_TOLERANCE >= 2 * FEE, "no headroom above the observed fee"
    assert bf.CRYPTO_FEE_CLOSEOUT_TOLERANCE <= 0.01, (
        "tolerance above 1% starts absorbing positions worth reporting"
    )


def test_the_known_limitation_is_real_and_pinned(bf):
    """HONEST DISCLOSURE, asserted so it cannot be forgotten.

    A genuine position SMALLER than the fee residue is indistinguishable from the fee by
    quantity alone, and this classifier drops it. Below: 100 UNI round-tripped (0.25 UNI of
    fee) plus a real 0.2 UNI holding -- total unmatched 0.45 against a 0.501 tolerance, so
    the real 0.2 UNI (~$0.56) is absorbed.

    This is accepted, not overlooked: the ONLY authority on whether an account is flat is the
    broker's /v2/positions (C11 -- broker is source of truth), which is what confirmed the 16
    phantom lots in the first place. The statement is an accounting view, not a flat-check.
    If that ever changes, this test is where the assumption is written down.
    """
    fills = [_fill("safe-2", "UNI/USD", "buy", 100.0, 2.80),
             _fill("safe-2", "UNI/USD", "sell", 100.0 * (1 - FEE), 2.85),
             _fill("safe-2", "UNI/USD", "buy", 0.2, 2.90)]
    _, lots = bf.fifo_round_trips(fills)
    assert lots == [], (
        "behaviour changed -- a sub-fee-size real position is now retained. That is an "
        "IMPROVEMENT, but the docstring above and the CANARY-OUT-OF-SAFE-2 queue note both "
        "describe the old behaviour and must be updated together with this test."
    )


# ---------------------------------------------------------------------------------------
# The live ledger: the numbers quoted in the commit message
# ---------------------------------------------------------------------------------------

def _live_fills():
    import json
    led = REPO / "automation" / "state" / "fills-ledger.jsonl"
    if not led.exists():
        pytest.skip("fills ledger absent")
    return [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_the_classifier_changes_no_number_on_the_live_ledger(bf, monkeypatch):
    """THE INVARIANT: classification may change what is REPORTED AS OPEN and nothing else.

    Asserted by running the real ledger BOTH ways -- with the classifier and with it stubbed
    to a no-op -- and comparing. Not against frozen absolutes: the first cut of this test
    pinned 790 round trips and $1,283.45, and went red within the hour when the nightly
    canary added 4 fills. A guard that ordinary operation turns RED is a guard nobody reads
    (2026-08-20); the counts were never the point, the equality is.
    """
    rows = _live_fills()
    with_classifier, _ = bf.fifo_round_trips(rows)
    monkeypatch.setattr(bf, "drop_fee_residue_lots", lambda lots, fills: lots)
    without, _ = bf.fifo_round_trips(rows)

    assert len(with_classifier) == len(without), (
        f"the classifier changed the round-trip count ({len(without)} -> "
        f"{len(with_classifier)}) -- it must never affect MATCHING. An earlier cut of this "
        "fix popped fee-sized lots inside the FIFO loop and destroyed 90 of 790 rows, "
        "because a popped lot is no longer available for a later fill to match against."
    )
    assert (round(sum(r["pnl"] for r in with_classifier), 2)
            == round(sum(r["pnl"] for r in without), 2)), "realized P&L moved"


def test_the_live_ledger_reports_flat(bf):
    """Broker read 2026-09-02 returned 0 positions on all five live arms; the statement must
    agree. safe-1 is excluded from that claim -- its key 401s and the arm is dormant."""
    rts, lots = bf.fifo_round_trips(_live_fills())
    assert rts, "no round trips parsed at all -- the ledger or matcher is broken"
    assert lots == [], (
        f"phantom open lots are back: {[(l['arm'], l['symbol'], l['qty']) for l in lots]}. "
        "If any of these is a REAL position the broker also reports, this test is right and "
        "the position is the finding."
    )


# ---------------------------------------------------------------------------------------
# The crypto bucket: `manual` must mean a hand-placed OPTION trade
# ---------------------------------------------------------------------------------------

def test_crypto_round_trips_do_not_count_as_manual_trades(bf):
    """The nightly $10 BTC canary made safe-2 report n_manual=164 -- 157 of them canary --
    which reads as J hand-trading 164 times. The money was never the issue (-$1.08 across
    the whole book); the count on a human-read surface was."""
    rts = [
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "BTC/USD",
         "attribution": "manual", "pnl": -0.01},
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "SPY260901C00650000",
         "attribution": "manual", "pnl": -50.0},
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "SPY260901C00650000",
         "attribution": "engine", "pnl": 120.0},
    ]
    st = bf.build_statement(rts, [])
    a = st["per_account"]["safe-2"]
    assert a["n_manual"] == 1, "a crypto round trip is still being counted as a manual trade"
    assert a["n_crypto"] == 1
    assert a["n_engine"] == 1
    assert a["manual_pnl"] == pytest.approx(-50.0)
    assert a["crypto_pnl"] == pytest.approx(-0.01)


def test_the_buckets_still_sum_to_realized(bf):
    """Adding a bucket must not lose or double-count a cent."""
    rts = [
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "BTC/USD",
         "attribution": "manual", "pnl": -0.01},
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "SPY260901C00650000",
         "attribution": "manual", "pnl": -50.0},
        {"arm": "safe-2", "date_et": "2026-09-01", "symbol": "SPY260901C00650000",
         "attribution": "engine", "pnl": 120.0},
    ]
    st = bf.build_statement(rts, [])
    a = st["per_account"]["safe-2"]
    assert a["realized_pnl"] == pytest.approx(
        a["engine_pnl"] + a["manual_pnl"] + a["crypto_pnl"])
    assert a["n_round_trips"] == a["n_engine"] + a["n_manual"] + a["n_crypto"]
    d = st["per_day"]["2026-09-01"]["safe-2"]
    assert d["realized_pnl"] == pytest.approx(
        d["engine_pnl"] + d["manual_pnl"] + d["crypto_pnl"])


def test_an_engine_crypto_fill_stays_engine(bf):
    """Bucketing must not demote a genuine engine trade just because it is crypto. Engine
    attribution, once earned, is never taken away (promote_ledger_attribution's rule)."""
    st = bf.build_statement([{"arm": "safe-2", "date_et": "2026-09-01", "symbol": "BTC/USD",
                              "attribution": "engine", "pnl": 5.0}], [])
    a = st["per_account"]["safe-2"]
    assert a["n_engine"] == 1 and a["n_crypto"] == 0


def test_the_live_statement_reclassifies_the_canary(bf):
    """End-to-end on the real ledger: safe-2's manual count must drop to the handful of
    genuine hand-placed OPTION trades, with the ~157 canary round trips in their own bucket."""
    rts, lots = bf.fifo_round_trips(_live_fills())
    st = bf.build_statement(rts, lots)
    a = st["per_account"].get("safe-2")
    if not a:
        pytest.skip("safe-2 absent from the ledger")
    assert a["n_crypto"] > 100, (
        f"expected the nightly canary's round trips in the crypto bucket, got "
        f"n_crypto={a['n_crypto']}"
    )
    assert a["n_manual"] < 20, (
        f"safe-2 still reports n_manual={a['n_manual']} -- crypto is leaking into the "
        "hand-placed-trade count"
    )
    assert a["realized_pnl"] == pytest.approx(
        a["engine_pnl"] + a["manual_pnl"] + a["crypto_pnl"], abs=0.02)
