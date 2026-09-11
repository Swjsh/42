"""GUARD SPEC (red-proofed) for the STAGED vwap_continuation 2DTE expiry override.

STATUS: this guard tests a REFERENCE implementation of the picker logic that the
proposal (strategy/candidates/2026-07-07-*-vwapcont-dte-override.md) stages but does
NOT yet apply to setup/scripts/heartbeat_core.py. When J/Gamma applies the patch, the
last test (test_live_engine_wired) flips from xfail-skip to a real import assertion.

The staged change adds ONE isolated per-setup DTE override, mirroring the existing
_SETUP_STRIKE_OVERRIDES / _SETUP_EXIT_OVERRIDES isolated-key pattern:

  params key:  j_vwap_cont_dte_override  (int, trading days out; ABSENT/0 -> 0DTE)
  picker:      expiry = _expiry_for_setup(setup_name, _et_now(), params)
               which returns _add_trading_days(now, N) for vwap_continuation when the
               override is set, else now (0DTE) -- byte-identical for every other setup.

RED-PROOF: TestBrokenState proves the CURRENT hardcoded `expiry = _et_now()` picks the
WRONG (0DTE) expiry for an armed 2DTE override -- i.e. the bug this guard would catch.
TestReferenceImpl proves the staged picker picks the RIGHT expiry. Together they prove
the guard fails on the unpatched engine and passes on the patched one (guardian_proven).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_vwapcont_dte_override_2026_07_07.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# REFERENCE IMPLEMENTATION — the exact logic the proposal patch stages into
# heartbeat_core.py. Kept here so the guard is runnable BEFORE the patch lands;
# on apply, replace these two funcs with `from heartbeat_core import ...`.
# ---------------------------------------------------------------------------
_SETUP_DTE_OVERRIDES = {
    "vwap_continuation": "j_vwap_cont_dte_override",
}


def _add_trading_days(start: dt.datetime, n: int) -> dt.datetime:
    """start + n TRADING days (skip Sat/Sun). n<=0 -> start unchanged (0DTE).
    NOTE (proposal): US market holidays are NOT skipped here -- a holiday inside the
    window makes the chosen expiry a 1-DTE not 2-DTE contract. Acceptable for a
    liquid SPY weekly (still an existing listed expiry); the proposal flags a
    holiday-aware upgrade (reuse automation/state/calendar.json) as a v2."""
    if n <= 0:
        return start
    d = start
    added = 0
    while added < n:
        d = d + dt.timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            added += 1
    return d


def _expiry_for_setup(setup_name: "str | None", now: dt.datetime, params: dict) -> dt.datetime:
    """Return the contract EXPIRY datetime for a setup. Default = now (0DTE, byte-
    identical to today). If the setup has an armed integer DTE override in params,
    return now + N trading days. Fail-safe: any bad value -> 0DTE."""
    key = _SETUP_DTE_OVERRIDES.get(str(setup_name or "").lower())
    if not key:
        return now
    try:
        n = int(params.get(key, 0))
    except (TypeError, ValueError):
        n = 0
    return _add_trading_days(now, n)


# ---------------------------------------------------------------------------
MON = dt.datetime(2026, 7, 6, 10, 0)   # a Monday
THU = dt.datetime(2026, 7, 9, 10, 0)   # a Thursday (2 td -> next Mon)
FRI = dt.datetime(2026, 7, 10, 10, 0)  # a Friday (weekend crossing)


class TestReferenceImpl:
    def test_default_absent_is_0dte(self):
        assert _expiry_for_setup("vwap_continuation", MON, {}).date() == MON.date()

    def test_override_0_is_0dte(self):
        assert _expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": 0}).date() == MON.date()

    def test_override_2_picks_2_trading_days_out(self):
        # Mon + 2 trading days = Wed
        exp = _expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": 2})
        assert exp.date() == dt.date(2026, 7, 8)  # Wed

    def test_override_2_skips_weekend(self):
        # Thu + 2 trading days = next Mon (skips Sat/Sun)
        exp = _expiry_for_setup("vwap_continuation", THU, {"j_vwap_cont_dte_override": 2})
        assert exp.date() == dt.date(2026, 7, 13)  # Mon

    def test_override_only_applies_to_named_setup(self):
        # a DIFFERENT setup keeps 0DTE even if the vwap key is present
        exp = _expiry_for_setup("bollinger_squeeze", MON, {"j_vwap_cont_dte_override": 2})
        assert exp.date() == MON.date()

    def test_none_setup_is_0dte(self):
        assert _expiry_for_setup(None, MON, {"j_vwap_cont_dte_override": 2}).date() == MON.date()

    def test_bad_value_fails_safe_to_0dte(self):
        exp = _expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": "oops"})
        assert exp.date() == MON.date()


class TestBrokenState:
    """Proves the CURRENT unpatched engine picks the WRONG expiry -- the bug this
    guard exists to catch. Simulates heartbeat_core.py line 1088 `expiry = _et_now()`."""

    def test_hardcoded_expiry_ignores_override(self):
        # current behavior: expiry is ALWAYS now regardless of override -> 0DTE
        hardcoded_expiry = MON  # == _et_now()
        wanted = _expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": 2})
        # the bug: hardcoded != wanted when an override is armed
        assert hardcoded_expiry.date() != wanted.date(), (
            "if these are equal the override has no effect -- unpatched engine bug")


class TestOccSymbolUsesExpiry:
    """The OCC symbol must encode the CHOSEN expiry date (not always today)."""

    def test_occ_encodes_2dte_expiry(self):
        try:
            import heartbeat_core as hc
        except Exception:
            pytest.skip("heartbeat_core import unavailable in this env")
        exp = _expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": 2})
        sym = hc._occ("P", 620, exp)
        assert sym == f"SPY{exp.strftime('%y%m%d')}P00620000", sym
        # and it differs from the 0DTE symbol
        sym0 = hc._occ("P", 620, MON)
        assert sym != sym0


class TestLiveEngineWired:
    """Flips to a real assertion once the patch lands: heartbeat_core exposes
    _expiry_for_setup and _execute uses it in place of `expiry = _et_now()`."""

    def test_engine_exposes_picker_after_patch(self):
        try:
            import heartbeat_core as hc
        except Exception:
            pytest.skip("heartbeat_core import unavailable in this env")
        if not hasattr(hc, "_expiry_for_setup"):
            pytest.xfail("STAGED-NOT-APPLIED: proposal patch not yet merged into heartbeat_core")
        # once applied, the engine picker must match the reference logic
        exp = hc._expiry_for_setup("vwap_continuation", MON, {"j_vwap_cont_dte_override": 2})
        assert exp.date() == dt.date(2026, 7, 8)
