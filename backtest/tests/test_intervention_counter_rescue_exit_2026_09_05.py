"""Guard: intervention_counter.py's `rescue_exit` category (2026-09-05).

WHY THIS EXISTS: on 2026-09-04 the box lost power 09:51-10:46 ET while safe-2 (3x
SPY260904P00772000) held an open position the engine itself had placed (09:46:05 ET).
J closed it from the Alpaca web dashboard at 10:46:06 ET -- one minute after the engine
resumed ticking (10:46:15). Before this fix, intervention_counter.py's classifier saw
only "engine entry attribution, non-engine exit attribution" and filed this as
`engine_entered_manual_exit` -- the SAME bucket as J second-guessing a live, healthy
engine (the exact "cuts winners early" risk pattern the counter exists to police).
That is wrong: the engine was blind and unmanaged for the entire hold; J's action was a
rescue, not an intervention against the Sept ZERO target.

RED-PROOF (quote both runs in the report): this test module fails against the
pre-2026-09-05 intervention_counter.py (no `rescue_exit` category, no `ARM_TO_ACCOUNT`,
no `engine_gaps` import) and passes after.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import intervention_counter as ic  # noqa: E402


def _fill(activity_id, arm, symbol, side, qty, price, date_et, ts_et, attribution,
          is_crypto=False, is_option=True):
    return {
        "activity_id": activity_id, "arm": arm, "order_id": f"ord-{activity_id}",
        "symbol": symbol, "side": side, "qty": qty, "price": price, "multiplier": 100,
        "is_crypto": is_crypto, "is_option": is_option, "ts_utc": f"{date_et}T14:00:00Z",
        "ts_et": ts_et, "date_et": date_et, "attribution": attribution,
    }


# --------------------------------------------------------------------------- #
# THE 2026-09-04 CASE -- real timestamps/qty/price, verbatim from fills-ledger.jsonl.
# The gap-detector side (engine_gaps) reads core-decisions.jsonl for the 'safe' account
# on 2026-09-04; that ledger genuinely has the 09:51:03 -> 10:46:15 hole (verified live
# this session), so this test exercises the REAL production gap, not a monkeypatched one
# -- it is the same fixture as test_engine_health_rth_tick_gaps_2026_09_05.py's pure
# detector test, applied end-to-end through intervention_counter's classifier.
# --------------------------------------------------------------------------- #

def test_2026_09_04_safe2_exit_is_reclassified_as_rescue_not_intervention():
    fills = [
        _fill("20260904094605044::163d6051-00a9-4db7-8c84-2f3278f8f476", "safe-2",
              "SPY260904P00772000", "buy", 3.0, 1.29,
              "2026-09-04", "2026-09-04T09:46:05.044241", "engine"),
        _fill("20260904104606110::03052a27-f805-4fbe-9766-96f05bfb8208", "safe-2",
              "SPY260904P00772000", "sell", 3.0, 2.0,
              "2026-09-04", "2026-09-04T10:46:06.110286", "manual"),
    ]
    out = ic.classify_round_trips(fills)
    assert len(out) == 1
    rt = out[0]
    assert rt["category"] == "rescue_exit", (
        f"expected rescue_exit (blackout rescue), got {rt['category']!r} -- the "
        "2026-09-04 core-decisions.jsonl gap (09:51:03->10:46:15) was not detected"
    )
    assert rt["is_rescue"] is True
    assert rt["is_intervention"] is False, (
        "a rescue must NOT count against the Sept ZERO-intervention target"
    )

    summary = ic.summarize(out)
    assert summary["all_time"]["n_round_trips"] == 0, (
        "rescue must not appear in the intervention headline count"
    )
    assert summary["rescues"]["n_round_trips"] == 1
    assert summary["rescues"]["by_arm"] == {"safe-2": 1}


def test_a_manual_exit_outside_the_rescue_window_stays_a_real_intervention():
    """Same shape (engine entry, manual exit) but on an ordinary day with no gap --
    must NOT be swept into rescue_exit. Uses a date/time far from any known gap."""
    fills = [
        _fill("g1", "safe-2", "SPY260828C00771000", "buy", 3, 1.2,
              "2026-08-28", "2026-08-28T09:36:00", "engine"),
        _fill("g2", "safe-2", "SPY260828C00771000", "sell", 3, 1.3,
              "2026-08-28", "2026-08-28T09:40:00", "manual"),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "engine_entered_manual_exit"
    assert out[0]["is_rescue"] is False
    assert out[0]["is_intervention"] is True


def test_manual_both_is_never_reclassified_as_rescue():
    """rescue_exit only applies to the engine-entered/manual-exit shape -- a fully
    manual round trip must stay manual_both even if its exit happens to fall inside a
    gap window (no engine leg to rescue in the first place)."""
    fills = [
        _fill("m1", "bold-2", "SPY260828P00760000", "buy", 5, 1.0,
              "2026-08-28", "2026-08-28T09:45:00", "manual"),
        _fill("m2", "bold-2", "SPY260828P00760000", "sell", 5, 0.8,
              "2026-08-28", "2026-08-28T09:51:00", "manual"),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "manual_both"
    assert out[0]["is_rescue"] is False


def test_summarize_never_counts_rescues_since_target_start():
    """The Sept-forward target counter must read the same zero it would if the rescue
    round trip did not exist at all."""
    fills = [
        _fill("r1", "safe-2", "SPY260904P00772000", "buy", 3.0, 1.29,
              "2026-09-04", "2026-09-04T09:46:05", "engine"),
        _fill("r2", "safe-2", "SPY260904P00772000", "sell", 3.0, 2.0,
              "2026-09-04", "2026-09-04T10:46:06", "manual"),
    ]
    import datetime as dt
    summary = ic.summarize(ic.classify_round_trips(fills),
                            now_et=dt.datetime(2026, 9, 4, 16, 0, 0))
    assert summary["since_target_start"]["n_round_trips"] == 0
    assert summary["today"]["n_round_trips"] == 0
    assert summary["rescues_today"]["n_round_trips"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
