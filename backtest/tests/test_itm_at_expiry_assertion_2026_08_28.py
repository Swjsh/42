"""Guard: itm_at_expiry_assertion.py (TASK B2 instrument 2/3).

Pins:
  1. OCC symbol parsing (root/expiry/right/strike).
  2. net_positions_by_expiry's FIFO-free net-qty aggregation (buy - sell).
  3. is_judgable's C6 no-look-ahead gate (never judge a still-open position
     before its own expiry's 16:00 ET close has actually happened).
  4. settlement_close: reads the real cache-file shape, and returns None
     (a COVERAGE GAP, never a silent OTM guess) when the file is missing.
  5. is_itm for calls and puts.
  6. assert_all's end-to-end classification: violation / held-OTM / coverage
     gap / closed-flat (never judged) / still-open-not-yet-judgable.
  7. STATUS.md escalation follows the create-if-missing pattern (2026-08-20
     outage fix), fires ONLY on an actual violation.
  8. A live-data smoke check against the real fills-ledger.jsonl + real
     spy_sip_cache (skipped if either is absent) -- pins TODAY'S backfilled
     answer so a future run that silently regresses this to non-zero is
     caught immediately, not discovered by accident.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import itm_at_expiry_assertion as itm  # noqa: E402

MARKER = "## Known broken"
NO_SECTION = "## [2026-08-20 10:00 ET] a dated entry and nothing else\nfiller\n"


def _fill(activity_id, arm, symbol, side, qty, date_et, ts_et, is_option=True):
    return {
        "activity_id": activity_id, "arm": arm, "order_id": f"ord-{activity_id}",
        "symbol": symbol, "side": side, "qty": qty, "price": 1.0, "multiplier": 100,
        "is_crypto": False, "is_option": is_option, "ts_utc": f"{date_et}T14:00:00Z",
        "ts_et": ts_et, "date_et": date_et,
    }


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #

def test_parse_occ_symbol():
    p = itm.parse_occ_symbol("SPY260828C00769000")
    assert p == {"root": "SPY", "expiry_date": "2026-08-28", "right": "C", "strike": 769.0}


def test_parse_occ_symbol_put_and_fractional_strike():
    p = itm.parse_occ_symbol("SPY260701P00742500")
    assert p["right"] == "P"
    assert p["strike"] == 742.5


def test_parse_occ_symbol_rejects_garbage():
    assert itm.parse_occ_symbol("ETH/USD") is None
    assert itm.parse_occ_symbol("") is None
    assert itm.parse_occ_symbol(None) is None


def test_net_positions_nets_buy_minus_sell():
    fills = [
        _fill("f1", "safe-2", "SPY260828C00770000", "buy", 5, "2026-08-28", "2026-08-28T09:35:00"),
        _fill("f2", "safe-2", "SPY260828C00770000", "sell", 2, "2026-08-28", "2026-08-28T10:00:00"),
    ]
    g = itm.net_positions_by_expiry(fills)
    key = ("safe-2", "SPY260828C00770000")
    assert g[key]["net_qty"] == pytest.approx(3.0)
    assert g[key]["expiry_date"] == "2026-08-28"
    assert g[key]["right"] == "C"
    assert g[key]["strike"] == 770.0


def test_net_positions_skips_non_option_and_unparseable():
    fills = [
        _fill("c1", "safe-3", "ETH/USD", "buy", 1, "2026-06-30", "2026-06-30T21:16:30",
              is_option=False),
    ]
    assert itm.net_positions_by_expiry(fills) == {}


def test_is_judgable_before_and_after_close():
    now_before_close = dt.datetime(2026, 8, 28, 15, 59, 0)
    now_after_close = dt.datetime(2026, 8, 28, 16, 0, 0)
    assert itm.is_judgable("2026-08-28", now_before_close) is False
    assert itm.is_judgable("2026-08-28", now_after_close) is True


def test_is_judgable_past_date_always_true_future_date_always_false():
    now = dt.datetime(2026, 8, 28, 20, 0, 0)
    assert itm.is_judgable("2026-08-27", now) is True
    assert itm.is_judgable("2026-08-31", now) is False


def test_settlement_close_reads_last_bar_at_or_before_1600(tmp_path):
    cache = {"bars": [
        {"t": "2026-08-28T15:58:00", "c": 769.10},
        {"t": "2026-08-28T15:59:00", "c": 769.20},
        {"t": "2026-08-28T16:00:00", "c": 769.30},
        {"t": "2026-08-28T16:14:00", "c": 999.99},  # after-hours -- must NOT be picked
    ]}
    (tmp_path / "spy_1m_2026-08-28.json").write_text(json.dumps(cache), encoding="utf-8")
    close = itm.settlement_close("2026-08-28", cache_dir=tmp_path)
    assert close == 769.30


def test_settlement_close_missing_file_is_none_never_a_guess(tmp_path):
    assert itm.settlement_close("2026-08-28", cache_dir=tmp_path) is None


def test_is_itm_call_and_put():
    assert itm.is_itm("C", 770.0, 771.0) is True
    assert itm.is_itm("C", 770.0, 769.0) is False
    assert itm.is_itm("P", 770.0, 769.0) is True
    assert itm.is_itm("P", 770.0, 771.0) is False


# --------------------------------------------------------------------------- #
# assert_all end-to-end
# --------------------------------------------------------------------------- #

def test_assert_all_flags_a_real_itm_violation(tmp_path):
    (tmp_path / "spy_1m_2026-08-28.json").write_text(
        json.dumps({"bars": [{"t": "2026-08-28T16:00:00", "c": 771.0}]}), encoding="utf-8")
    fills = [
        _fill("v1", "safe-2", "SPY260828C00770000", "buy", 3, "2026-08-28", "2026-08-28T15:50:00"),
    ]
    now_et = dt.datetime(2026, 8, 28, 16, 20, 0)
    summary = itm.assert_all(fills, now_et=now_et, cache_dir=tmp_path)
    assert summary["has_ever_happened"] is True
    assert summary["n_violations"] == 1
    v = summary["violations"][0]
    assert v["arm"] == "safe-2" and v["net_qty"] == 3.0
    assert v["notional_usd"] == pytest.approx(3 * 100 * 771.0)
    assert v["itm_by_usd"] == pytest.approx(1.0)


def test_assert_all_otm_held_is_not_a_violation(tmp_path):
    (tmp_path / "spy_1m_2026-08-28.json").write_text(
        json.dumps({"bars": [{"t": "2026-08-28T16:00:00", "c": 765.0}]}), encoding="utf-8")
    fills = [
        _fill("o1", "safe-2", "SPY260828C00770000", "buy", 3, "2026-08-28", "2026-08-28T15:50:00"),
    ]
    now_et = dt.datetime(2026, 8, 28, 16, 20, 0)
    summary = itm.assert_all(fills, now_et=now_et, cache_dir=tmp_path)
    assert summary["n_violations"] == 0
    assert summary["has_ever_happened"] is False
    assert summary["held_to_close_otm_count"] == 1


def test_assert_all_missing_cache_is_a_coverage_gap_not_a_pass(tmp_path):
    fills = [
        _fill("g1", "safe-2", "SPY260828C00770000", "buy", 3, "2026-08-28", "2026-08-28T15:50:00"),
    ]
    now_et = dt.datetime(2026, 8, 28, 16, 20, 0)
    summary = itm.assert_all(fills, now_et=now_et, cache_dir=tmp_path)  # empty tmp_path, no cache
    assert summary["n_violations"] == 0
    assert summary["n_coverage_gaps"] == 1
    assert summary["coverage_gaps"][0]["settlement_close"] is None


def test_assert_all_closed_flat_is_never_judged(tmp_path):
    fills = [
        _fill("f1", "safe-2", "SPY260828C00770000", "buy", 3, "2026-08-28", "2026-08-28T09:35:00"),
        _fill("f2", "safe-2", "SPY260828C00770000", "sell", 3, "2026-08-28", "2026-08-28T10:00:00"),
    ]
    now_et = dt.datetime(2026, 8, 28, 16, 20, 0)
    summary = itm.assert_all(fills, now_et=now_et, cache_dir=tmp_path)
    assert summary["n_judged"] == 0
    assert summary["n_violations"] == 0


def test_assert_all_same_day_before_close_is_not_yet_judgable(tmp_path):
    fills = [
        _fill("p1", "safe-2", "SPY260828C00770000", "buy", 3, "2026-08-28", "2026-08-28T15:50:00"),
    ]
    now_et = dt.datetime(2026, 8, 28, 14, 0, 0)  # mid-session, before the 15:55 flatten window
    summary = itm.assert_all(fills, now_et=now_et, cache_dir=tmp_path)
    assert summary["n_judged"] == 0
    assert len(summary["still_open_not_yet_judgable"]) == 1
    assert summary["n_violations"] == 0


# --------------------------------------------------------------------------- #
# STATUS.md escalation
# --------------------------------------------------------------------------- #

def _violation_summary():
    return {
        "generated_at_et": "2026-08-28T16:20:00", "n_violations": 1,
        "violations": [{"arm": "safe-2", "symbol": "SPY260828C00770000", "net_qty": 3.0,
                         "itm_by_usd": 1.0, "notional_usd": 231300.0}],
    }


def test_status_report_lands_even_with_no_section(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    fired = itm._flag_status_md(_violation_summary(), status_md=p)
    assert fired is True
    after = p.read_text(encoding="utf-8")
    assert MARKER in after, (
        "did not create '## Known broken' when it was missing -- the exact 2026-08-20 outage "
        "class. Recreate the section instead of returning early.")
    assert "ITM-AT-EXPIRY VIOLATION" in after


def test_status_report_lands_when_section_exists_and_does_not_duplicate(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n- an older escalation\n\n" + NO_SECTION, encoding="utf-8")
    itm._flag_status_md(_violation_summary(), status_md=p)
    after = p.read_text(encoding="utf-8")
    assert after.count(MARKER) == 1
    assert "- an older escalation" in after


def test_status_never_fires_when_clean(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    clean = {"generated_at_et": "2026-08-28T16:20:00", "n_violations": 0, "violations": []}
    fired = itm._flag_status_md(clean, status_md=p)
    assert fired is False
    assert p.read_text(encoding="utf-8") == NO_SECTION


# --------------------------------------------------------------------------- #
# Live-data smoke check -- pins TODAY'S backfilled answer so a future silent
# regression is caught, not discovered by accident. Skips if the real data
# isn't present (e.g. a slim CI checkout without backtest/data/).
# --------------------------------------------------------------------------- #

def test_live_backfill_has_zero_violations_to_date():
    if not itm.FILLS_PATH.exists() or not itm.BAR_CACHE_DIR.exists():
        pytest.skip("real fills-ledger.jsonl or spy_sip_cache not present in this checkout")
    fills = itm.load_fills()
    if not fills:
        pytest.skip("fills-ledger.jsonl is empty")
    summary = itm.assert_all(fills)
    assert summary["n_violations"] == 0, (
        f"REAL ITM-at-expiry violation(s) found: {summary['violations']} -- "
        "this is a genuine physical-assignment-risk finding, not a test bug. "
        "Investigate before touching this guard.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
