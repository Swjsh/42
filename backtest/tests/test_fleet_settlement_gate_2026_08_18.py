"""Guard for the fleet settlement gate (2026-08-18 fix,
analysis/deep-research/RULE-ENGINE-ALIGNMENT-2026-08-18.md).

THE AUDIT'S FINDING: fleet_executor.py deliberately pins pdt_gate_mode="margin_pdt"
for all 3 fleet arms (safe-3, risky-1, risky-3) because it never computed a
settled-cash number -- so no fleet order was EVER checked against a settled-cash
pool, and nothing capped fleet's same-day entry COUNT (core caps at 5/day via
max_same_day_roundtrips; fleet was uncapped -- real consequence, measured: risky-1
took SIXTEEN entries on 2026-08-12 while core was capped at 5; the book lost $890
across 38 trades that day).

THIS SUITE PROVES, WITHOUT changing fleet's pdt_gate_mode (still margin_pdt --
see test_finalize_pins_pdt_gate_mode_to_margin_pdt_regardless_of_params in
automation/state/fleet/test_fleet_executor.py, unmodified by this fix, still green):

  1. risk_gate.check_settlement (extracted from check_order's own inline
     cash_settlement branch, byte-identical -- test_risk_gate.py's existing
     cash_settlement suite is unmodified and still green) enforces cash + cap.
  2. settlement_ledger.ledger_path's new fleet-arm branch isolates each fleet
     arm's ledger from core's safe/bold files AND from every OTHER fleet arm.
  3. fleet_executor.finalize()'s new settlement gate:
       - is a byte-identical no-op for every caller that doesn't wire the two
         new kwargs (run_dry, every pre-existing test) OR that has the config
         flag off -- DOUBLE-gated, either alone is enough to keep it inert.
       - refuses (HOLD) with risk_code FLEET_SETTLEMENT_CASH when notional >
         settled cash remaining.
       - refuses with FLEET_SETTLEMENT_CAP when same_day_entries_used >= the
         CONFIGURED cap (params.max_same_day_roundtrips -- proven to read from
         config, not a hardcoded number, by varying the param and watching the
         trip point move).
       - refuses with FLEET_SETTLEMENT_UNREADABLE (fail-closed) when the
         settlement data is present but malformed.
       - the refusal's reason string names the real numbers -- never a bare
         "no signal"/HOLD (the silent-failure class C7 warns about).
       - the cap is evaluated per the CALLER-SUPPLIED same_day_entries_used --
         two different values (standing in for two different arms' own
         ledgers) produce independent verdicts under the identical cap.
       - defers to KILL_SWITCH (not a settlement code) when kill_switch_tripped
         is already True, matching check_order's own rule PRIORITY.
       - a clean order still ALLOWs exactly as before when cash/cap are fine.
  4. fleet_live._place_live actually WRITES the ledger entry on a real placed
     order (sod= kwarg wiring), and stays byte-identical (no write at all) when
     sod is not supplied -- every pre-existing _place_live test call site.

Run: cd backtest && python -m pytest tests/test_fleet_settlement_gate_2026_08_18.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from lib.risk_gate import (  # noqa: E402
    CODE_SETTLEMENT,
    CODE_UNREADABLE_INPUT,
    check_settlement,
)
import fleet_executor as fx  # noqa: E402
import settlement_ledger as sl  # noqa: E402


# --- fixtures (self-contained; mirrors test_fleet_executor.py's _final() shape) -----
SAFE_PARAMS = {
    "per_trade_risk_cap_pct": 0.3,
    "daily_loss_kill_switch_pct": 0.3,
    "min_contracts": 3,
    "max_same_day_roundtrips": 5,  # matches automation/state/params.json's live value
}


def _plan(qty=3, side="P", action="ENTER"):
    return fx.EntryPlan("test-arm", action, side, "BEARISH_REJECTION_RIDE_THE_RIBBON",
                        745, qty, "BASE", "test plan", strategy="ribbon_ride",
                        exit_shape={"premium_stop_pct": -0.5, "tp1_premium_pct": 1.0})


def _final(plan, premium, params, **overrides):
    kwargs = dict(
        equity=2000.0, start_of_day_equity=2000.0, premium=premium,
        current_position_status=None, day_trades_used_5d=0,
        kill_switch_tripped=False, prior_stops_today=[], params=params,
        account_label="TEST-ARM",
    )
    kwargs.update(overrides)
    return fx.finalize(plan, **kwargs)


# =====================================================================================
# 1. risk_gate.check_settlement -- the extracted pure function (self-contained)
# =====================================================================================

def test_check_settlement_allows_within_pool():
    d = check_settlement("acct", premium=1.00, proposed_qty=3,
                         settled_cash_available=2000.0, same_day_entries_used=0,
                         params=SAFE_PARAMS)
    assert d is None


def test_check_settlement_denies_notional_exceeding_pool():
    d = check_settlement("acct", premium=1.00, proposed_qty=3,
                         settled_cash_available=250.0, same_day_entries_used=0,
                         params=SAFE_PARAMS)
    assert d is not None and d.code == CODE_SETTLEMENT
    assert "exceeds settled cash remaining" in d.reason


def test_check_settlement_denies_at_configured_cap():
    d = check_settlement("acct", premium=1.00, proposed_qty=3,
                         settled_cash_available=100_000.0, same_day_entries_used=5,
                         params=SAFE_PARAMS)
    assert d is not None and d.code == CODE_SETTLEMENT
    assert "sanity cap" in d.reason


def test_check_settlement_fails_closed_on_missing_inputs():
    d1 = check_settlement("acct", premium=1.00, proposed_qty=3,
                          settled_cash_available=None, same_day_entries_used=0,
                          params=SAFE_PARAMS)
    d2 = check_settlement("acct", premium=1.00, proposed_qty=3,
                          settled_cash_available=2000.0, same_day_entries_used=None,
                          params=SAFE_PARAMS)
    assert d1.code == CODE_UNREADABLE_INPUT
    assert d2.code == CODE_UNREADABLE_INPUT


def test_check_settlement_fails_closed_on_bad_premium_or_qty():
    """check_settlement self-validates premium/proposed_qty -- safe to call standalone
    without check_order's own rule-0 pre-validation (fleet_executor calls it directly,
    independent of check_order's mode dispatch)."""
    d1 = check_settlement("acct", premium=None, proposed_qty=3,
                          settled_cash_available=2000.0, same_day_entries_used=0,
                          params=SAFE_PARAMS)
    d2 = check_settlement("acct", premium=1.00, proposed_qty=None,
                          settled_cash_available=2000.0, same_day_entries_used=0,
                          params=SAFE_PARAMS)
    assert d1.code == CODE_UNREADABLE_INPUT
    assert d2.code == CODE_UNREADABLE_INPUT


# =====================================================================================
# 2. settlement_ledger.ledger_path -- fleet-arm branch isolation
# =====================================================================================

def test_ledger_path_fleet_arm_isolated_from_core_and_siblings(tmp_path):
    safe_path = sl.ledger_path(tmp_path, "safe")
    bold_path = sl.ledger_path(tmp_path, "bold")
    safe3_path = sl.ledger_path(tmp_path, "safe-3")
    risky1_path = sl.ledger_path(tmp_path, "risky-1")
    risky3_path = sl.ledger_path(tmp_path, "risky-3")
    paths = [safe_path, bold_path, safe3_path, risky1_path, risky3_path]
    assert len(set(paths)) == 5, f"a fleet arm's ledger collided with another path: {paths}"
    # "safe"/"bold" byte-identical to before (also pinned in test_settlement_ledger.py's
    # own test_ledger_path_safe_vs_bold -- repeated here so this file is self-contained).
    assert safe_path == tmp_path / "settlement-ledger.json"
    assert bold_path == tmp_path / "aggressive" / "settlement-ledger.json"
    # fleet arms live under their OWN namespaced subtree, mirroring fleet_live.py's
    # established per-arm state convention (FLEET_DIR/<arm_id>/circuit-breaker.json).
    assert safe3_path == tmp_path / "fleet" / "safe-3" / "settlement-ledger.json"
    assert risky1_path == tmp_path / "fleet" / "risky-1" / "settlement-ledger.json"
    assert risky3_path == tmp_path / "fleet" / "risky-3" / "settlement-ledger.json"


def test_ledger_path_fleet_arms_end_to_end_independent_ledgers(tmp_path):
    """Two fleet arms recording entries on the SAME trading day never see each other's
    count or debit each other's settled-cash pool -- the concrete 'cap is per-arm not
    shared' proof at the ledger-file level (paired with the finalize()-level proof below,
    which shows the SAME independence at the gate-decision level)."""
    p3 = sl.ledger_path(tmp_path, "safe-3")
    p1 = sl.ledger_path(tmp_path, "risky-1")
    today = "2026-08-18"
    for _ in range(4):
        sl.record_entry(p3, today, 2000.0, 300.0, f"{today}T10:00:00")
    status3 = sl.get_settlement_status(p3, today, 2000.0)
    status1 = sl.get_settlement_status(p1, today, 2000.0)
    assert status3["entries_used_today"] == 4
    assert status1["entries_used_today"] == 0, (
        "risky-1's ledger must be untouched by safe-3's 4 entries"
    )


# =====================================================================================
# 3. fleet_executor.finalize() -- the wired gate
# =====================================================================================

def test_finalize_gate_is_noop_when_flag_absent_even_with_data_supplied():
    """Config flag OFF (absent -- every live params.json snapshot before this fix, and
    every params dict a caller might build without knowing about this key) must be a
    byte-identical no-op EVEN IF a caller supplies real ledger numbers -- config wins."""
    plan = _plan(qty=3)
    d = _final(plan, 1.00, SAFE_PARAMS,  # no fleet_settlement_gate_enabled key
              settled_cash_available=1.0, same_day_entries_used=99)  # would deny if live
    assert d.risk_code == "ALLOW", (
        f"REGRESSION: settlement gate fired without params.fleet_settlement_gate_enabled "
        f"(risk_code={d.risk_code!r} reason={d.reason!r})"
    )


def test_finalize_gate_is_noop_when_data_not_supplied_even_with_flag_on():
    """Flag ON but the caller doesn't pass settled_cash_available/same_day_entries_used
    (both default None) -- byte-identical no-op. This is EXACTLY fleet_executor.run_dry()'s
    shape (the CLI/backtest-console path never threads a live ledger) once the live config
    files carry the flag, and EXACTLY every pre-existing test call site's shape too."""
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params)  # no settled_cash_available/same_day_entries_used
    assert d.risk_code == "ALLOW"


def test_finalize_refuses_on_insufficient_settled_cash():
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params, settled_cash_available=100.0, same_day_entries_used=0)
    assert d.action == "HOLD"
    assert d.risk_code == "FLEET_SETTLEMENT_CASH", (
        f"expected a distinct settlement-cash refusal, got risk_code={d.risk_code!r}"
    )
    assert "settled cash" in d.reason.lower()
    assert d.reason != "no qualifying setup (no strategy fired)", (
        "a settlement refusal must never look like a plain no-signal HOLD"
    )


def test_finalize_refuses_at_the_configured_daily_cap():
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params, settled_cash_available=100_000.0,
              same_day_entries_used=5)  # SAFE_PARAMS max_same_day_roundtrips == 5
    assert d.action == "HOLD"
    assert d.risk_code == "FLEET_SETTLEMENT_CAP"
    assert "sanity cap" in d.reason


def test_finalize_cap_reads_from_params_not_hardcoded():
    """The trip point MUST move when params.max_same_day_roundtrips changes -- proves the
    cap value is read from config (the SAME key core's own cap reads), not a second
    hardcoded fleet-side constant."""
    tight = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True, max_same_day_roundtrips=2)
    plan = _plan(qty=3)
    allowed = _final(plan, 1.00, tight, settled_cash_available=100_000.0,
                     same_day_entries_used=1)
    denied = _final(plan, 1.00, tight, settled_cash_available=100_000.0,
                    same_day_entries_used=2)
    assert allowed.risk_code == "ALLOW"
    assert denied.risk_code == "FLEET_SETTLEMENT_CAP"


def test_finalize_cap_is_per_call_not_shared_across_arms():
    """Two different same_day_entries_used values (standing in for two different fleet
    arms' own independent ledgers -- see the ledger_path isolation tests above) under the
    IDENTICAL configured cap produce INDEPENDENT verdicts -- the cap never aggregates or
    shares state across whichever arm's numbers are passed in."""
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    arm_a = _final(plan, 1.00, params, settled_cash_available=100_000.0,
                   same_day_entries_used=5)   # e.g. "safe-3" already at its own cap
    arm_b = _final(plan, 1.00, params, settled_cash_available=100_000.0,
                   same_day_entries_used=0)   # e.g. "risky-1" fresh for the day
    assert arm_a.risk_code == "FLEET_SETTLEMENT_CAP"
    assert arm_b.risk_code == "ALLOW", "one arm's exhausted cap must never leak into another's"


def test_finalize_fails_closed_on_malformed_settlement_data():
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params, settled_cash_available="not-a-number",
              same_day_entries_used=0)
    assert d.action == "HOLD"
    assert d.risk_code == "FLEET_SETTLEMENT_UNREADABLE"


def test_finalize_kill_switch_takes_priority_over_settlement():
    """Mirrors check_order's own rule PRIORITY (Rule 5 kill-switch before Rule 7
    settlement): when the kill switch is already tripped, the settlement gate must NOT be
    the reported reason -- the more severe/meaningful KILL_SWITCH verdict (from the
    unchanged check_order call immediately below the gate) must surface instead."""
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params, settled_cash_available=1.0, same_day_entries_used=99,
              kill_switch_tripped=True)
    assert d.risk_code == "KILL_SWITCH", (
        f"expected KILL_SWITCH to take priority over the settlement gate, got "
        f"risk_code={d.risk_code!r}"
    )


def test_finalize_allows_clean_order_with_gate_enabled():
    """The gate being ON must not break the ordinary ALLOW path when cash/cap are both
    fine -- proves this is a REFUSAL-only gate, never a second source of denial noise on
    healthy orders."""
    params = dict(SAFE_PARAMS, fleet_settlement_gate_enabled=True)
    plan = _plan(qty=3)
    d = _final(plan, 1.00, params, settled_cash_available=2000.0, same_day_entries_used=0)
    assert d.action == "ENTER_BEAR" and d.risk_code == "ALLOW"


# =====================================================================================
# 4. fleet_live._place_live -- the ledger WRITE (sod= kwarg wiring)
# =====================================================================================

def _stub_broker_for_place_live(monkeypatch, fl, tmp_path, *, mid=1.00, entry_px=1.03):
    monkeypatch.setattr(fl.fb, "get_option_mid", lambda creds, symbol: mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price",
                        lambda creds, symbol, side="buy", buffer=0.03: entry_px)
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", lambda creds, symbol: ([], True))
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", lambda creds, symbol: (0, True))
    monkeypatch.setattr(fl.fb, "_request",
                        lambda creds, endpoint, method="GET", data=None, timeout=15:
                        {"id": "fake-order", "status": "accepted"})
    # Mirrors test_money_path_simple_fallback.py's pattern: bypass exit-state
    # registration entirely (returns None -> _exit_state stays None -> the fill-poll/
    # reanchor block never runs -- this suite is about the SETTLEMENT ledger write, not
    # exit-state registration, and FLEET_SAME_BAR_COOLDOWN defaults False so the cooldown
    # path never touches ea.FLEET_DIR either).
    monkeypatch.setattr(fl.ea, "register_entry", lambda arm_id, **kw: None)
    _fleet_dir = tmp_path / "fleet"
    _fleet_dir.mkdir(parents=True, exist_ok=True)  # _claim_path's mkdir(exist_ok=True) has
    # no parents=True, so the parent must already exist (matches production: FLEET_DIR
    # itself always exists as a real repo directory).
    monkeypatch.setattr(fl, "FLEET_DIR", _fleet_dir)


def test_place_live_records_settlement_entry_when_sod_supplied_and_flag_on(monkeypatch, tmp_path):
    """End-to-end proof that _place_live's new sod= kwarg actually reaches
    settlement_ledger.record_entry on a real PLACED order -- not just that finalize()
    denies/allows correctly upstream of it."""
    import fleet_live as fl
    from types import SimpleNamespace
    import datetime as _dt

    _stub_broker_for_place_live(monkeypatch, fl, tmp_path)
    decision = SimpleNamespace(side="P", strike=745, qty=3,
                               setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON")
    arm = {"id": "safe-3-test"}
    now = _dt.datetime(2026, 8, 18, 11, 0)
    params = {"fleet_settlement_gate_enabled": True}

    res = fl._place_live({}, arm, decision, {}, {}, params, now, sod=2000.0)
    assert res["placed"] is True

    ledger_file = tmp_path / "fleet" / "safe-3-test" / "settlement-ledger.json"
    assert ledger_file.exists(), "settlement ledger was never written on a real placement"
    ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["notional"] == pytest.approx(res["entry_px"] * 3 * 100.0)


def test_place_live_does_not_record_when_sod_not_supplied(monkeypatch, tmp_path):
    """Every pre-existing _place_live call site (all positional args, no sod=) must stay
    byte-identical: no ledger file written at all when sod is omitted, regardless of the
    flag -- this is the exact shape of every test in test_entry_idempotency_guard.py,
    test_fix1_selection.py, test_fleet_same_bar_cooldown.py, test_place_live_stop_display.py,
    test_money_path_simple_fallback.py (all confirmed still green by this fix's test run)."""
    import fleet_live as fl
    from types import SimpleNamespace
    import datetime as _dt

    _stub_broker_for_place_live(monkeypatch, fl, tmp_path)
    decision = SimpleNamespace(side="P", strike=745, qty=3,
                               setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON")
    arm = {"id": "safe-3-test2"}
    now = _dt.datetime(2026, 8, 18, 11, 0)
    params = {"fleet_settlement_gate_enabled": True}

    res = fl._place_live({}, arm, decision, {}, {}, params, now)  # no sod kwarg
    assert res["placed"] is True
    ledger_file = tmp_path / "fleet" / "safe-3-test2" / "settlement-ledger.json"
    assert not ledger_file.exists(), "ledger must not be written when sod is not supplied"


def test_place_live_does_not_record_when_flag_off(monkeypatch, tmp_path):
    """sod IS supplied but the config flag is off -- still no write. Both gates
    independently required, matching the READ side's double-gate contract in run()."""
    import fleet_live as fl
    from types import SimpleNamespace
    import datetime as _dt

    _stub_broker_for_place_live(monkeypatch, fl, tmp_path)
    decision = SimpleNamespace(side="P", strike=745, qty=3,
                               setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON")
    arm = {"id": "safe-3-test3"}
    now = _dt.datetime(2026, 8, 18, 11, 0)
    params = {}  # fleet_settlement_gate_enabled absent

    res = fl._place_live({}, arm, decision, {}, {}, params, now, sod=2000.0)
    assert res["placed"] is True
    ledger_file = tmp_path / "fleet" / "safe-3-test3" / "settlement-ledger.json"
    assert not ledger_file.exists(), "ledger must not be written when the config flag is off"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            import inspect
            if "tmp_path" in inspect.signature(t).parameters or \
               "monkeypatch" in inspect.signature(t).parameters:
                print(f"SKIP  {t.__name__} (needs pytest fixtures -- run under pytest)")
                continue
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
