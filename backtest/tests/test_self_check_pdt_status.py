"""Guard for self_check.check_pdt_status -- the PDT (Rule 7) VISIBILITY instrument
(2026-07-14).

Motivation: analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2 -- core Safe reached
risk_gate.check_order with a VALID, gate-passing signal and was denied by the PDT
check (9/3 day-trades used, inherited from the account's prior life as fleet arm
safe-1 after the repoint, commit 61cfca0). Rule 7 fired CORRECTLY; the miss was
that NOTHING surfaced the block until a manual review found it. This pins:

  1. A currently-BLOCKED account produces a problem string that (a) exists and
     (b) does NOT match _problem_is_broken -- i.e. it renders DEGRADED/YELLOW,
     never BROKEN/RED (Rule 7 doing its job is not itself a fault).
  2. A non-blocked account produces NO problem (stays GREEN as far as this
     check goes) but the summary is still populated (firm_brief needs it every
     cycle, not only when something's wrong).
  3. A fetch failure or missing key renders an honest UNKNOWN -- never a
     fabricated 0 that could hide a real block.
  4. Missing secrets file fails open to ([], {}) -- never raises.

Mirrors test_self_check_tradeability.py's import convention (spec_from_file_location,
so this survives running as a lone file without setup/scripts pre-imported)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

NOW = dt.datetime(2026, 7, 14, 11, 0, 0)


def _write_secrets(tmp_path, accounts: dict) -> Path:
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": accounts}), encoding="utf-8")
    return p


def _acct(key="k", secret="s", base="https://paper-api.alpaca.markets") -> dict:
    return {"api_key": key, "secret_key": secret, "base_url": base}


# ---- the exact 2026-07-13 scar, reproduced ----

def test_blocked_account_flags_degraded_not_broken(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        if creds["key"] == "k":
            return {"ok": True, "count": 9, "dates": ["2026-07-08"],
                    "rolloff_date": "2026-07-15", "as_of_et": "x"}
        return {"ok": True, "count": 0, "dates": [], "rolloff_date": None, "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return 1746.63

    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, fetch_detail=fake_detail,
                                             fetch_equity=fake_equity)
    assert len(problems) == 1
    assert "PDT-BLOCKED[safe]" in problems[0]
    assert "9/3" in problems[0]
    assert "2026-07-15" in problems[0]
    assert not sc._problem_is_broken(problems[0]), \
        "a correctly-firing PDT block must be DEGRADED/YELLOW, never BROKEN/RED"
    assert summary["safe"]["status"] == "BLOCKED"
    assert summary["safe"]["remaining"] == 0
    assert summary["bold"]["status"] == "OK"


def test_not_blocked_account_produces_no_problem_but_full_summary(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        return {"ok": True, "count": 1, "dates": ["2026-07-13"],
                "rolloff_date": "2026-07-20", "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return 1963.04

    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, fetch_detail=fake_detail,
                                             fetch_equity=fake_equity)
    assert problems == [], "not blocked -> stays GREEN as far as this check goes"
    assert summary["safe"]["status"] == "OK"
    assert summary["safe"]["day_trades_used_5d"] == 1
    assert summary["safe"]["remaining"] == 2
    assert summary["safe"]["rolloff_date"] == "2026-07-20"
    assert summary["bold"]["status"] == "OK"


def test_equity_at_or_above_25k_marks_not_applicable_even_if_at_limit(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        return {"ok": True, "count": 9, "dates": ["2026-07-08"],
                "rolloff_date": "2026-07-15", "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return 30000.0

    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, fetch_detail=fake_detail,
                                             fetch_equity=fake_equity)
    assert problems == [], "PDT does not apply above the $25K threshold, regardless of count"
    assert summary["safe"]["status"] == "NOT_APPLICABLE"


def test_unreadable_equity_is_conservative_not_silently_clear(tmp_path):
    """If we can't read equity, ASSUME PDT applies (never silently assume an account
    cleared the $25K threshold just because the equity read failed)."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        return {"ok": True, "count": 5, "dates": ["2026-07-08"],
                "rolloff_date": "2026-07-15", "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return None

    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, fetch_detail=fake_detail,
                                             fetch_equity=fake_equity)
    assert len(problems) == 2, "both accounts blocked (count=5 >= limit=3) under conservative assumption"
    assert summary["safe"]["status"] == "BLOCKED"
    assert summary["safe"]["equity"] is None


# ---- honest UNKNOWN, never a fabricated 0 ----

def test_fetch_failure_renders_unknown_not_a_fake_zero(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        return {"ok": False, "error": "OSError: Connection refused"}

    def fake_equity(base, key, sec):
        return 1746.63

    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, fetch_detail=fake_detail,
                                             fetch_equity=fake_equity)
    assert problems == [], "a fetch failure is not itself flagged as a PDT block"
    assert summary["safe"]["status"] == "UNKNOWN"
    assert "day_trades_used_5d" not in summary["safe"], "must never carry a fabricated count"
    assert summary["bold"]["status"] == "UNKNOWN"


def test_missing_key_renders_unknown(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": {}, "bold-2": {}})
    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec)
    assert problems == []
    assert summary["safe"]["status"] == "UNKNOWN"
    assert summary["bold"]["status"] == "UNKNOWN"


def test_missing_secrets_file_fails_open(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    problems, summary = sc.check_pdt_status(NOW, secrets_path=missing)
    assert problems == []
    assert summary == {}


# ---- wiring: run() must persist the pdt summary + extend problems ----

def test_pdt_constants_are_the_real_risk_gate_values():
    limit, threshold = sc._pdt_constants()
    assert limit == 3
    assert threshold == 25_000.0


def test_run_source_wires_check_pdt_status_and_persists_summary():
    """Source-level wiring guard (mirrors test_pdt_tracker_2026_07_06.py's
    test_heartbeat_core_execute_calls_pdt_tracker pattern) -- deliberately does
    NOT invoke run() itself, which does live network I/O (broker pings) and
    real state-file writes (loop_state_refresh, STATUS.md, self-check-last.json)
    not appropriate to exercise from a unit test, especially not one that might
    run during live market hours."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_pdt_status(now)" in src, "run() must call the PDT visibility check"
    assert '"pdt": pdt_summary' in src, "the pdt summary must be persisted onto the result dict"
    assert "problems.extend(pdt_problems)" in src, "a PDT block must feed into the overall verdict"
