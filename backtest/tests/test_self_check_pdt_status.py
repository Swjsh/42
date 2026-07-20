"""Guard for self_check.check_pdt_status -- the PDT (Rule 7) VISIBILITY instrument
(2026-07-14; extended 2026-07-15).

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

2026-07-15 EXTENSION -- a second, distinct scar: automation/state/discord-outbox.jsonl
fired "SELF-CHECK DEGRADED: PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd)..." at
15:09 ET even though BOTH core accounts are CASH accounts pinned to
params.pdt_gate_mode="cash_settlement" (commit fd09a78, 2026-07-14) -- the margin-PDT
day-trade counter above is NOT the live gate for them (risk_gate.check_order never reads
day_trades_used_5d in that mode) and nothing was actually blocked (both of that day's
trades filled AFTER the alert). check_pdt_status now reads each account's OWN
params.json#pdt_gate_mode (injectable via `account_params`) and, for cash_settlement
accounts, reports settlement-ledger truth via check_cash_settlement_status (injectable
via `settlement_status`) instead of the margin counter. This adds:

  5. A cash_settlement account with a high margin-style day_trades_used_5d count (>3)
     NEVER produces a PDT-BLOCKED alert -- the exact 7/3 scenario from the scar,
     reproduced and RED-proofed.
  6. The settlement gate DOES alert (SETTLEMENT-BLOCKED, DEGRADED not BROKEN) when it
     would actually refuse -- roundtrip cap reached, or settled cash exhausted.
  7. An account still pinned to pdt_gate_mode="margin_pdt" (the fleet-arm default) is
     UNCHANGED -- same day_trades_used_5d/equity path as before this fix.

Existing tests 1-4 above are pinned to the margin_pdt branch explicitly via
`account_params=_margin_params` so they stay deterministic regardless of what
automation/state/params.json#pdt_gate_mode is set to in the live repo (which is
cash_settlement today, and is exactly the condition tests 5-7 exercise instead).

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


def _margin_params(label: str) -> dict:
    """Pin BOTH accounts to the legacy margin_pdt mode -- used by tests 1-4 (below) that
    guard the ORIGINAL day_trades_used_5d/equity branch, so they stay deterministic no
    matter what automation/state/params.json#pdt_gate_mode is set to live."""
    return {"pdt_gate_mode": "margin_pdt"}


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
                                             fetch_equity=fake_equity, account_params=_margin_params)
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
                                             fetch_equity=fake_equity, account_params=_margin_params)
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
                                             fetch_equity=fake_equity, account_params=_margin_params)
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
                                             fetch_equity=fake_equity, account_params=_margin_params)
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
                                             fetch_equity=fake_equity, account_params=_margin_params)
    assert problems == [], "a fetch failure is not itself flagged as a PDT block"
    assert summary["safe"]["status"] == "UNKNOWN"
    assert "day_trades_used_5d" not in summary["safe"], "must never carry a fabricated count"
    assert summary["bold"]["status"] == "UNKNOWN"


def test_missing_key_renders_unknown(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": {}, "bold-2": {}})
    problems, summary = sc.check_pdt_status(NOW, secrets_path=sec, account_params=_margin_params)
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


# ---- 2026-07-15 fix: cash_settlement mode reads settlement-ledger truth, never the
#      margin day-trade counter (see module docstring items 5-7) -----------------------

def _cash_params(max_rt=5):
    def _fn(label):
        return {"pdt_gate_mode": "cash_settlement", "max_same_day_roundtrips": max_rt}
    return _fn


def test_cash_settlement_account_ignores_margin_pdt_day_trade_count(tmp_path):
    """RED-PROOF: the exact 2026-07-15 scar reproduced. discord-outbox.jsonl fired
    "SELF-CHECK DEGRADED: PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity
    $1,569.32..." at 15:09 ET even though safe-2 is pinned pdt_gate_mode="cash_settlement"
    (params.json, commit fd09a78) -- risk_gate.check_order never reads day_trades_used_5d
    in that mode, so nothing was actually blocked (both of that day's trades filled AFTER
    the alert). A cash_settlement account with day_trades_used_5d=7 (>3, the margin limit)
    must NEVER produce a PDT-BLOCKED alert."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        # the margin-style count that WOULD have tripped the old (buggy) alert
        return {"ok": True, "count": 7, "dates": [], "rolloff_date": "2026-07-16", "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return 1569.32

    def fake_settlement_status(label, now, params):
        return {"entries_used_today": 1, "settled_cash_remaining": 1200.0,
                "sod_settled_cash": 1569.32}

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, fetch_detail=fake_detail, fetch_equity=fake_equity,
        account_params=_cash_params(), settlement_status=fake_settlement_status)

    assert not any("PDT-BLOCKED" in p for p in problems), \
        "cash_settlement accounts must never alert off the margin day-trade counter"
    assert problems == [], "plenty of settled cash + under the roundtrip cap -> no block at all"
    assert summary["safe"]["gate_mode"] == "cash_settlement"
    assert summary["safe"]["status"] == "OK"
    assert "day_trades_used_5d" not in summary["safe"], \
        "cash_settlement summary must never carry the irrelevant margin day-trade count"
    assert summary["bold"]["gate_mode"] == "cash_settlement"


def test_cash_settlement_blocked_when_roundtrip_cap_reached(tmp_path):
    """The settlement gate DOES alert when it would ACTUALLY refuse -- entries_used_today
    >= max_same_day_roundtrips (the sanity cap risk_gate.check_order enforces)."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_settlement_status(label, now, params):
        if label == "safe":
            return {"entries_used_today": 5, "settled_cash_remaining": 800.0,
                    "sod_settled_cash": 1746.56}
        return {"entries_used_today": 0, "settled_cash_remaining": 1963.04,
                "sod_settled_cash": 1963.04}

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, account_params=_cash_params(max_rt=5),
        settlement_status=fake_settlement_status)

    assert len(problems) == 1
    assert "SETTLEMENT-BLOCKED[safe]" in problems[0]
    assert "5/5" in problems[0]
    assert not sc._problem_is_broken(problems[0]), \
        "a correctly-firing settlement block must be DEGRADED/YELLOW, never BROKEN/RED"
    assert summary["safe"]["status"] == "BLOCKED"
    assert summary["bold"]["status"] == "OK"


def test_cash_settlement_blocked_when_settled_cash_exhausted(tmp_path):
    """The other real-refusal condition: settled_cash_remaining <= 0 -- ANY positive-
    notional order would exceed it, regardless of size, even under the roundtrip cap."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_settlement_status(label, now, params):
        return {"entries_used_today": 2, "settled_cash_remaining": 0.0,
                "sod_settled_cash": 1746.56}

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, account_params=_cash_params(),
        settlement_status=fake_settlement_status)

    assert len(problems) == 2, "both accounts share the same fake settlement fn here"
    assert "SETTLEMENT-BLOCKED[safe]" in problems[0]
    assert "fully committed" in problems[0]
    assert summary["safe"]["settled_cash_remaining"] == 0.0


def test_cash_settlement_not_blocked_stays_green_with_full_summary(tmp_path):
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_settlement_status(label, now, params):
        return {"entries_used_today": 1, "settled_cash_remaining": 1500.0,
                "sod_settled_cash": 1746.56}

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, account_params=_cash_params(),
        settlement_status=fake_settlement_status)

    assert problems == []
    assert summary["safe"]["status"] == "OK"
    assert summary["safe"]["entries_used_today"] == 1
    assert summary["safe"]["max_same_day_roundtrips"] == 5
    assert summary["safe"]["settled_cash_remaining"] == 1500.0
    assert summary["safe"]["sod_settled_cash"] == 1746.56


def test_cash_settlement_unknown_when_sod_equity_unreadable(tmp_path):
    """Fail-open per module docstring: an unreadable start-of-day settled cash (e.g. a
    missing/corrupt circuit-breaker.json) renders an honest UNKNOWN, never a fabricated
    OK or a false BLOCKED."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_settlement_status(label, now, params):
        return None

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, account_params=_cash_params(),
        settlement_status=fake_settlement_status)

    assert problems == []
    assert summary["safe"]["status"] == "UNKNOWN"
    assert summary["safe"]["gate_mode"] == "cash_settlement"


def test_pdt_gate_mode_defaults_to_margin_pdt_when_key_absent():
    """risk_gate.check_order's own default when pdt_gate_mode is absent from params is
    "margin_pdt" -- self_check must resolve the SAME default (single source of truth)."""
    assert sc._pdt_gate_mode({}) == "margin_pdt"
    assert sc._pdt_gate_mode({"per_trade_risk_cap_pct": 0.3}) == "margin_pdt"
    assert sc._pdt_gate_mode({"pdt_gate_mode": "cash_settlement"}) == "cash_settlement"
    assert sc._pdt_gate_mode({"pdt_gate_mode": "MARGIN_PDT"}) == "margin_pdt", \
        "case-insensitive, matches risk_gate.check_order's .strip().lower()"


def test_margin_pdt_account_unaffected_by_the_2026_07_15_fix(tmp_path):
    """An account still pinned to pdt_gate_mode="margin_pdt" (the fleet-arm default,
    fleet_executor.py#finalize) must take EXACTLY the pre-2026-07-15 path -- this fix is
    additive for cash_settlement accounts, not a behavior change for margin ones."""
    sec = _write_secrets(tmp_path, {"safe-2": _acct("k"), "bold-2": _acct("k2")})

    def fake_detail(creds):
        if creds["key"] == "k":
            return {"ok": True, "count": 4, "dates": ["2026-07-10"],
                    "rolloff_date": "2026-07-17", "as_of_et": "x"}
        return {"ok": True, "count": 0, "dates": [], "rolloff_date": None, "as_of_et": "x"}

    def fake_equity(base, key, sec):
        return 1746.63

    problems, summary = sc.check_pdt_status(
        NOW, secrets_path=sec, fetch_detail=fake_detail, fetch_equity=fake_equity,
        account_params=_margin_params)

    assert len(problems) == 1
    assert "PDT-BLOCKED[safe]" in problems[0]
    assert "gate_mode" not in summary["safe"], "margin_pdt summary shape is unchanged"


def test_real_repo_params_resolve_cash_settlement_for_both_core_accounts():
    """Integration sanity check against the LIVE params.json files (not injected) --
    confirms _default_account_params + _pdt_gate_mode actually resolve to
    "cash_settlement" for both core accounts today (2026-07-15), which is the exact
    condition under which the old code produced the fictional PDT-BLOCKED alert. If this
    ever fails because pdt_gate_mode was reverted to "margin_pdt" (a documented, valid
    revert path -- see params.json#_pdt_gate_mode_doc), that's fine: it means the
    margin-PDT branch is live again and test_blocked_account_flags_degraded_not_broken
    (unpinned from this file's real state) is the one guarding live behavior -- update
    or remove this test at that point rather than treating a fail here as a regression."""
    safe_params = sc._default_account_params("safe")
    bold_params = sc._default_account_params("bold")
    assert sc._pdt_gate_mode(safe_params) == "cash_settlement"
    # UPDATED 2026-07-20 per this test's own docstring instruction: Bold's broker account
    # became a 4x MARGIN account over the 07-18/19 weekend (multiplier=4, live-verified),
    # so bold flipped to margin_pdt that morning -- the margin-PDT branch is live again
    # for bold and this pin now tracks that reality. See aggressive/params.json#_pdt_gate_mode_doc.
    assert sc._pdt_gate_mode(bold_params) == "margin_pdt"
