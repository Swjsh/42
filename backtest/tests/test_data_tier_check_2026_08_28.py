"""Guard: data_tier_check.py (TASK B2 instrument 3/3).

Pins:
  1. check_account's tier derivation (sip/iex, opra/indicative, the
     no-feed-param live-path inference-by-elimination) against synthetic
     _get() results covering paid, free, and broken-baseline scenarios.
  2. _most_recent_option_symbol picks the latest is_option fill across ALL
     arms (tier is account/key-level, not symbol-dependent).
  3. summarize()'s counts and baseline_broken detection.
  4. STATUS.md escalation fires ONLY on a genuine baseline break (a
     confirmed free-tier 403 must NEVER escalate -- it is expected,
     informational, not a break) and follows the create-if-missing pattern.
  5. This script NEVER calls any order-placement / account-mutation
     function -- static-checked against fleet_broker's write surface.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import data_tier_check as dtc  # noqa: E402

MARKER = "## Known broken"
NO_SECTION = "## [2026-08-20 10:00 ET] a dated entry and nothing else\nfiller\n"


def _fill(activity_id, arm, symbol, ts_utc, is_option=True):
    return {"activity_id": activity_id, "arm": arm, "symbol": symbol, "side": "sell",
            "qty": 1, "price": 1.0, "is_option": is_option, "is_crypto": False,
            "ts_utc": ts_utc, "ts_et": ts_utc, "date_et": ts_utc[:10]}


# --------------------------------------------------------------------------- #
# _most_recent_option_symbol
# --------------------------------------------------------------------------- #

def test_most_recent_option_symbol_across_all_arms(tmp_path):
    p = tmp_path / "fills-ledger.jsonl"
    rows = [
        _fill("a", "safe-2", "SPY260826C00760000", "2026-08-26T14:00:00Z"),
        _fill("b", "risky-3", "SPY260828P00770000", "2026-08-28T14:00:00Z"),  # latest
        _fill("c", "safe-3", "ETH/USD", "2026-08-27T14:00:00Z", is_option=False),
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert dtc._most_recent_option_symbol(p) == "SPY260828P00770000"


def test_most_recent_option_symbol_missing_file_returns_none(tmp_path):
    assert dtc._most_recent_option_symbol(tmp_path / "nope.jsonl") is None


# --------------------------------------------------------------------------- #
# check_account -- tier derivation via a mocked _get
# --------------------------------------------------------------------------- #

def _mock_get_factory(responses: dict):
    """responses: {substring-of-path: result_dict}. First matching substring wins."""
    def _mock_get(creds, path, timeout=12.0):
        for needle, result in responses.items():
            if needle in path:
                return result
        raise AssertionError(f"unmocked path: {path}")
    return _mock_get


def test_check_account_free_tier_everything():
    responses = {
        "feed=sip": {"ok": False, "status": 403, "error": "subscription does not permit"},
        "feed=iex": {"ok": True, "status": 200, "body": {}},
        "feed=opra": {"ok": False, "status": 403, "error": "OPRA agreement is not signed"},
        "feed=indicative": {"ok": True, "status": 200, "body": {}},
        "options/quotes/latest?symbols=SPY260828C00770000": {"ok": True, "status": 200, "body": {}},
        "options/bars": {"ok": True, "status": 200, "body": {}},
    }
    with mock.patch.object(dtc, "_get", side_effect=_mock_get_factory(responses)):
        row = dtc.check_account({"key": "k", "secret": "s"}, "SPY260828C00770000")
    assert row["stock_tier"] == "IEX (free tier)"
    assert row["option_realtime_tier"].startswith("INDICATIVE")
    assert row["live_path_feed_inferred"].startswith("INDICATIVE")
    assert row["baseline_broken"] is False


def test_check_account_paid_tier_everything():
    ok = {"ok": True, "status": 200, "body": {}}
    with mock.patch.object(dtc, "_get", return_value=ok):
        row = dtc.check_account({"key": "k", "secret": "s"}, "SPY260828C00770000")
    assert row["stock_tier"].startswith("SIP")
    assert row["option_realtime_tier"].startswith("OPRA")
    assert row["live_path_feed_inferred"] == "OPRA"
    assert row["baseline_broken"] is False


def test_check_account_baseline_broken_when_iex_itself_fails():
    fail = {"ok": False, "status": 401, "error": "unauthorized"}
    with mock.patch.object(dtc, "_get", return_value=fail):
        row = dtc.check_account({"key": "k", "secret": "s"}, "SPY260828C00770000")
    assert row["stock_tier"].startswith("ERROR")
    assert row["baseline_broken"] is True


def test_check_account_no_symbol_skips_option_checks_never_guesses():
    responses = {"feed=sip": {"ok": False, "status": 403, "error": "x"},
                 "feed=iex": {"ok": True, "status": 200, "body": {}}}
    with mock.patch.object(dtc, "_get", side_effect=_mock_get_factory(responses)):
        row = dtc.check_account({"key": "k", "secret": "s"}, None)
    assert row["option_opra_ok"] is None
    assert row["option_realtime_tier"] == "UNPROBED (no symbol available)"
    assert row["live_path_feed_inferred"] == "UNPROBED"


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #

def test_summarize_counts_and_baseline_broken():
    accounts = {
        "safe-2": {"stock_tier": "IEX (free tier)",
                   "option_realtime_tier": "INDICATIVE (free tier -- x)", "baseline_broken": False},
        "bold-2": {"stock_tier": "SIP (paid, all US exchanges)",
                   "option_realtime_tier": "OPRA (paid, real-time NBBO)", "baseline_broken": False},
        "safe-3": {"stock_tier": "ERROR (neither sip nor iex succeeded -- see errors)",
                   "option_realtime_tier": "ERROR (neither opra nor indicative succeeded)",
                   "baseline_broken": True},
    }
    summary = dtc.summarize(accounts)
    assert summary["n_free_tier_stock_feed"] == 1
    assert summary["n_paid_tier_stock_feed"] == 1
    assert summary["n_free_tier_option_feed"] == 1
    assert summary["n_paid_tier_option_feed"] == 1
    assert summary["n_baseline_broken"] == 1
    assert summary["baseline_broken_arms"] == ["safe-3"]


# --------------------------------------------------------------------------- #
# STATUS.md escalation -- only on a genuine break, never on a confirmed free tier
# --------------------------------------------------------------------------- #

def test_status_never_fires_on_confirmed_free_tier(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    summary = {"generated_at_et": "2026-08-28T16:20:00", "n_baseline_broken": 0,
               "baseline_broken_arms": []}
    fired = dtc._flag_status_md(summary, status_md=p)
    assert fired is False
    assert p.read_text(encoding="utf-8") == NO_SECTION


def test_status_fires_on_genuine_baseline_break_create_if_missing(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    summary = {"generated_at_et": "2026-08-28T16:20:00", "n_baseline_broken": 1,
               "baseline_broken_arms": ["safe-3"]}
    fired = dtc._flag_status_md(summary, status_md=p)
    assert fired is True
    after = p.read_text(encoding="utf-8")
    assert MARKER in after
    assert "DATA-TIER-CHECK" in after


def test_status_does_not_duplicate_marker_when_present(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n- older\n\n" + NO_SECTION, encoding="utf-8")
    summary = {"generated_at_et": "2026-08-28T16:20:00", "n_baseline_broken": 1,
               "baseline_broken_arms": ["safe-3"]}
    dtc._flag_status_md(summary, status_md=p)
    after = p.read_text(encoding="utf-8")
    assert after.count(MARKER) == 1
    assert "- older" in after


# --------------------------------------------------------------------------- #
# Never touches the order-placement surface
# --------------------------------------------------------------------------- #

def test_module_never_calls_order_placement_functions():
    import inspect
    src = inspect.getsource(dtc)
    for forbidden in ("place_bracket", "place_option_order", "close_all_spy_options",
                       "close_position", "cancel_order"):
        assert forbidden not in src, (
            f"data_tier_check.py references '{forbidden}' -- this script must stay strictly "
            "read-only market-data GETs, per TASK B2 scope.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
