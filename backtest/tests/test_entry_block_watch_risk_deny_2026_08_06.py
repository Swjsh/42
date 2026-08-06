"""D8 guard -- entry_block_watch must see risk-gate denials (2026-08-06).

THE BLINDNESS: _qualifies() treated `verdict == ENTER_*` as "the engine took it" and
returned False -- but a RISK_DENY_* action means NO order ever reached the broker. The
watcher was structurally blind to the exact class of event it exists to alarm on.
Real cost: 2026-08-04, 21 consecutive RISK_DENY_PDT rows on bold (verdict=ENTER_BULL,
bull_score 11/11 tier ELITE, triggers level_reclaim+confluence -- passing every OTHER
check in _qualifies) produced zero alerts; J learned from the EOD review, hours later.

Fixture rows below are byte-shaped on the real 2026-08-04T12:26:55 ledger row.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_block_watch_risk_deny_2026_08_06.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ROOT / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def ebw():
    return importlib.import_module("entry_block_watch")


def _real_0804_shape(**overrides) -> dict:
    """The real 2026-08-04T12:26:55 bold row, trimmed to the fields _qualifies reads."""
    row = {
        "ts_et": "2026-08-04T12:26:55", "account": "bold",
        "verdict": "ENTER_BULL", "action": "RISK_DENY_PDT",
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "bull_score": 11, "bull_triggers_raw": ["level_reclaim", "confluence"],
        "bear_score": 4, "bear_triggers_raw": [],
        "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
        "exec": {"status": "RISK_DENY_PDT", "symbol": "SPY260804C00769000",
                 "qty": 5, "premium": 1.27,
                 "reason": "bold: 3 day-trades in 5d at equity $5,478 < $25,000 -- PDT "
                           "rule blocks a 4th day-trade"},
        "spy": 768.7, "levels_active": [768.5, 770.0],
    }
    row.update(overrides)
    return row


def test_risk_denied_enter_bull_qualifies(ebw):
    """THE D8 PIN: the exact 08-04 row shape must qualify as a missed bull setup."""
    assert ebw._qualifies(_real_0804_shape(), "bull") is True, (
        "a RISK_DENY_PDT row with an 11/11 ELITE bull setup does not qualify -- "
        "entry_block_watch is blind to risk-gate denials again (D8)")


def test_risk_denied_via_exec_status_only_qualifies(ebw):
    """Second surface: exec.status carries the denial even if top-level action is absent."""
    row = _real_0804_shape(action=None)
    assert ebw._qualifies(row, "bull") is True


def test_genuinely_taken_enter_does_not_qualify(ebw):
    """Other direction (non-vacuous): an ENTER_BULL whose order was actually PLACED must
    still NOT qualify -- the fix narrows ONLY the risk-denied case."""
    row = _real_0804_shape(action="PLACED")
    row["exec"] = {"status": "PLACED", "symbol": "SPY260804C00769000"}
    assert ebw._qualifies(row, "bull") is False


def test_low_score_risk_deny_still_filtered(ebw):
    """The quality bar is untouched: a risk-denied row below threshold stays out."""
    row = _real_0804_shape(bull_score=5)
    assert ebw._qualifies(row, "bull") is False


def test_non_level_tied_risk_deny_still_filtered(ebw):
    row = _real_0804_shape(bull_triggers_raw=["ribbon_flip"])
    assert ebw._qualifies(row, "bull") is False


def test_blocker_phrase_names_the_risk_gate(ebw):
    """The alert text must say the risk gate refused -- never the false 'other side won'
    story the old fallthrough produced for a blocker-less ENTER row."""
    phrase = ebw._blocker_phrase(_real_0804_shape(), "bull")
    assert "Risk gate refused" in phrase and "RISK_DENY_PDT" in phrase
    assert "won the tick" not in phrase


def test_bear_side_symmetric(ebw):
    """The fix is side-symmetric: a risk-denied ENTER_BEAR qualifies on the bear side."""
    row = _real_0804_shape(verdict="ENTER_BEAR", action="RISK_DENY_PDT",
                            bear_score=9, bear_triggers_raw=["level_rejection"])
    assert ebw._qualifies(row, "bear") is True
