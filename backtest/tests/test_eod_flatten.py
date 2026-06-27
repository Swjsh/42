"""test_eod_flatten.py -- graduated guards for eod_flatten.py (G7, 2026-06-27).

CONTRACTS PINNED:
  1. FLAT_NOOP      -- if both accounts are flat -> no orders placed, returns NOOP.
  2. CLOSE_ON_OPEN  -- if accounts have open SPY option positions -> close_all_spy_options called.
  3. FAIL_OPEN      -- one account raising an exception does NOT prevent the other from closing.
  4. ET_CLOCK       -- timestamps come from et_clock, NOT naive datetime.now().
  5. DRY_RUN        -- GAMMA_EOD_DRY=1 reports would_close without placing.
  6. NO_CREDS       -- a missing arm is SKIP_NO_CREDS, other arm still flattened.
  7. EXPIRY_AGNOSTIC -- any SPY option is closed (0DTE and 1DTE alike).

These guards ensure the "fragile LLM substrate replaced by pure Python" class of bugs
(L47/C11) cannot silently return: any future edit that (a) skips an account when the
other errors, (b) places orders when already flat, or (c) uses naive local time for
timestamps will RED here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---- path plumbing -----------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in [str(_SCRIPTS), str(_FLEET)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import eod_flatten as ef  # noqa: E402


# ---- helpers -----------------------------------------------------------------

def _make_position(symbol: str, qty: int = 5) -> dict:
    return {"symbol": symbol, "qty": str(qty), "asset_class": "us_option"}


def _flat_creds():
    return {
        "safe-2": {"key": "SK1", "secret": "SS1", "base_url": "https://paper-api.alpaca.markets"},
        "bold-2": {"key": "BK1", "secret": "BS1", "base_url": "https://paper-api.alpaca.markets"},
    }


def _read_jsonl(tmp_path: Path) -> list[dict]:
    """Read all eod-flatten-*.jsonl rows from tmp_path."""
    rows = []
    for f in tmp_path.glob("eod-flatten-*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ===========================================================================
# 1. FLAT_NOOP -- already flat, nothing placed
# ===========================================================================

def test_flat_noop_both_accounts(tmp_path):
    """Both accounts flat -> no orders, both NOOP."""
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=[]),
        patch.object(ef.fleet_broker, "close_all_spy_options") as mock_close,
    ):
        rc = ef.main()

    assert rc == 0
    mock_close.assert_not_called()


def test_flat_noop_result_logged(tmp_path):
    """NOOP result is written to the .jsonl output."""
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=[]),
        patch.object(ef.fleet_broker, "close_all_spy_options"),
    ):
        ef.main()

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "NOOP"
    assert outcomes.get("bold-2") == "NOOP"


# ===========================================================================
# 2. CLOSE_ON_OPEN -- open positions -> close_all_spy_options called
# ===========================================================================

def test_close_when_positions_open(tmp_path):
    """Open SPY option positions -> close_all_spy_options called live=True for each account."""
    pos = [_make_position("SPY260627P00735000", qty=5)]
    close_result = {"closed": ["SPY260627P00735000"], "errors": [], "remaining": 0}

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=pos),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result) as mock_close,
    ):
        rc = ef.main()

    assert rc == 0
    # Both accounts should have triggered a close
    assert mock_close.call_count == 2
    # Both calls must pass live=True
    for c in mock_close.call_args_list:
        assert c.kwargs.get("live") is True


def test_close_success_logged(tmp_path):
    """A successful close -> outcome=SUCCESS in jsonl."""
    pos = [_make_position("SPY260627C00740000", qty=3)]
    close_result = {"closed": ["SPY260627C00740000"], "errors": [], "remaining": 0}

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=pos),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result),
    ):
        ef.main()

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "SUCCESS"
    assert outcomes.get("bold-2") == "SUCCESS"


# ===========================================================================
# 3. FAIL_OPEN -- one account error does NOT block the other
# ===========================================================================

def test_fail_open_safe_errors_bold_still_closes(tmp_path):
    """safe-2 raises a network error; bold-2 MUST still be flattened."""
    pos = [_make_position("SPY260627P00735000", qty=2)]
    close_result = {"closed": ["SPY260627P00735000"], "errors": [], "remaining": 0}

    call_count = {"n": 0}

    def side_effect_positions(creds):
        call_count["n"] += 1
        if creds.get("key") == "SK1":
            raise ConnectionError("simulated safe-2 broker failure")
        return pos

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", side_effect=side_effect_positions),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result),
    ):
        rc = ef.main()

    # Exit 0 even when one account errors
    assert rc == 0

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    # safe-2 errored
    assert outcomes.get("safe-2") == "ERROR"
    # bold-2 succeeded
    assert outcomes.get("bold-2") == "SUCCESS"


def test_fail_open_bold_errors_safe_still_closes(tmp_path):
    """bold-2 raises; safe-2 must still succeed."""
    pos = [_make_position("SPY260627P00735000", qty=2)]
    close_result = {"closed": ["SPY260627P00735000"], "errors": [], "remaining": 0}

    def side_effect_positions(creds):
        if creds.get("key") == "BK1":
            raise ConnectionError("simulated bold-2 failure")
        return pos

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", side_effect=side_effect_positions),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result),
    ):
        rc = ef.main()

    assert rc == 0
    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "SUCCESS"
    assert outcomes.get("bold-2") == "ERROR"


# ===========================================================================
# 4. ET_CLOCK -- timestamps use et_clock, not naive datetime.now()
# ===========================================================================

def test_et_clock_not_naive_local_time():
    """_et_ts() must derive from et_clock.et_now(), NOT bare datetime.now() local.

    On this Mountain Time rig, naive datetime.now() is 2h behind ET.
    We verify the eod_flatten module's time source is et_clock.
    """
    source = Path(ef.__file__).read_text(encoding="utf-8")

    # Must import et_now from et_clock
    assert "from et_clock import et_now" in source, (
        "eod_flatten must import et_now from et_clock "
        "(NEVER use naive datetime.now() as ET on this Mountain-time rig)"
    )

    # Must not use bare datetime.now() without a timezone argument
    import re
    # Allow datetime.now(timezone.utc) but not datetime.now() or datetime.now() with only parens
    bare_now_calls = re.findall(r"datetime\.now\(\s*\)", source)
    assert not bare_now_calls, (
        f"eod_flatten has bare datetime.now() calls (not ET-safe): {bare_now_calls}\n"
        "Use et_now() from et_clock instead."
    )


def test_et_ts_returns_string_with_et_suffix():
    """_et_ts() returns a string containing 'ET' (confirms ET provenance)."""
    ts = ef._et_ts()
    assert isinstance(ts, str)
    assert len(ts) > 10
    assert "ET" in ts


# ===========================================================================
# 5. DRY_RUN -- GAMMA_EOD_DRY=1 reports would_close, no orders
# ===========================================================================

def test_dry_run_no_orders_placed(tmp_path, monkeypatch):
    """With DRY=True, positions are read but NO sell orders are placed."""
    monkeypatch.setattr(ef, "DRY", True)
    pos = [_make_position("SPY260627P00735000", qty=4)]

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=pos),
        patch.object(ef.fleet_broker, "close_all_spy_options") as mock_close,
    ):
        rc = ef.main()

    monkeypatch.setattr(ef, "DRY", False)

    assert rc == 0
    mock_close.assert_not_called()

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "DRY_RUN"
    assert outcomes.get("bold-2") == "DRY_RUN"


def test_dry_run_noop_when_flat(tmp_path, monkeypatch):
    """With DRY=True and flat -> NOOP (flat check runs before dry check)."""
    monkeypatch.setattr(ef, "DRY", True)

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=[]),
        patch.object(ef.fleet_broker, "close_all_spy_options") as mock_close,
    ):
        rc = ef.main()

    monkeypatch.setattr(ef, "DRY", False)

    assert rc == 0
    mock_close.assert_not_called()

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "NOOP"
    assert outcomes.get("bold-2") == "NOOP"


# ===========================================================================
# 6. NO_CREDS -- missing arm -> SKIP_NO_CREDS, other arm still flattened
# ===========================================================================

def test_skip_no_creds_missing_safe(tmp_path):
    """safe-2 missing from secrets.json -> SKIP_NO_CREDS; bold-2 still attempted."""
    creds_missing_safe = {
        "bold-2": {"key": "BK1", "secret": "BS1", "base_url": "https://paper-api.alpaca.markets"},
    }
    pos = [_make_position("SPY260627P00735000", qty=2)]
    close_result = {"closed": ["SPY260627P00735000"], "errors": [], "remaining": 0}

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=creds_missing_safe),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=pos),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result),
    ):
        rc = ef.main()

    assert rc == 0
    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "SKIP_NO_CREDS"
    assert outcomes.get("bold-2") == "SUCCESS"


# ===========================================================================
# 7. EXPIRY_AGNOSTIC -- any SPY option closed (0DTE and 1DTE alike)
# ===========================================================================

def test_expiry_agnostic_closes_all_spy_options(tmp_path):
    """fleet_broker.open_spy_option_positions is trusted as-is -- no expiry filter."""
    # Mix a 0DTE and a 1DTE position
    pos = [
        _make_position("SPY260627P00735000", qty=3),   # today = 0DTE
        _make_position("SPY260628C00740000", qty=2),   # tomorrow = 1DTE
    ]
    close_result = {
        "closed": ["SPY260627P00735000", "SPY260628C00740000"],
        "errors": [],
        "remaining": 0,
    }

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(ef.fleet_broker, "open_spy_option_positions", return_value=pos),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result) as mock_close,
    ):
        rc = ef.main()

    assert rc == 0
    # close_all_spy_options was called for both accounts
    assert mock_close.call_count == 2

    rows = _read_jsonl(tmp_path)
    outcomes = {r["arm"]: r["outcome"] for r in rows if "arm" in r}
    assert outcomes.get("safe-2") == "SUCCESS"
    assert outcomes.get("bold-2") == "SUCCESS"
