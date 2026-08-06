"""Wiring guards: the binding-constraint telemetry must REACH the decision rows.

risk_gate.explain_block being correct is worthless if nothing calls it (C7: silent
success is failure — the 2026-07-30 incident was itself a case of a correct component
whose output nobody consumed). These guards pin the two live call sites:

  * automation/state/fleet/fleet_executor.finalize  -> ArmDecision.binding
    (rides into automation/state/fleet/<arm>/decisions.jsonl via fleet_live's
     `row.update(**asdict(decision))`)
  * setup/scripts/heartbeat_core._execute           -> exec["binding"]
    (rides into automation/state/core-decisions.jsonl)

RED-proof targets: delete either `binding=` wiring, or make the telemetry non-additive
(populate it on ALLOW rows too), and the matching test fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest/lib", "automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import fleet_executor as fx  # noqa: E402

SAFE_PARAMS = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
EQ_SAFE_2 = 1160.42


def _plan(qty: int = 3) -> fx.EntryPlan:
    return fx.EntryPlan("safe-2", "ENTER", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON",
                        735, qty, "BASE", "test plan")


def _finalize(premium: float, qty: int = 3) -> fx.ArmDecision:
    return fx.finalize(
        _plan(qty), equity=EQ_SAFE_2, start_of_day_equity=EQ_SAFE_2, premium=premium,
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=SAFE_PARAMS, account_label="safe-2")


def test_fleet_deny_row_carries_the_deadlock_verdict():
    """A cap-refused fleet order must say WHY, machine-readably."""
    d = _finalize(1.42)  # the 2026-07-30 incident premium
    assert d.action == "HOLD"
    assert d.risk_code == "RISK_CAP"
    assert isinstance(d.binding, dict), "deny row lost its binding telemetry"
    assert d.binding["available"] is True
    assert d.binding["deadlock"] is True
    assert d.binding["max_affordable_qty"] == 0
    assert d.binding["premium_ceiling_cents"] == 1.16


def test_fleet_allow_row_is_unchanged():
    """ADDITIVE ONLY: an allowed order carries binding=None, exactly as before."""
    d = _finalize(1.00)
    assert d.action == "ENTER_BEAR"
    assert d.risk_code == "ALLOW"
    assert d.binding is None, "ALLOW rows must stay byte-identical (binding=None)"


def test_fleet_hold_row_is_unchanged():
    hold = fx.EntryPlan("safe-2", "HOLD", None, None, None, None, None, "no setup")
    d = fx.finalize(hold, equity=EQ_SAFE_2, start_of_day_equity=EQ_SAFE_2, premium=None,
                    current_position_status=None, day_trades_used_5d=0,
                    kill_switch_tripped=False, prior_stops_today=[], params=SAFE_PARAMS,
                    account_label="safe-2")
    assert d.action == "HOLD" and d.binding is None


def test_fleet_deny_row_serialises_into_the_ledger_shape():
    """fleet_live writes `row.update(**asdict(decision))` — the whole thing must be JSON."""
    from dataclasses import asdict

    row = {"arm": "safe-2"}
    row.update(**asdict(_finalize(1.42)))
    blob = json.dumps(row)
    assert json.loads(blob)["binding"]["deadlock"] is True


def test_fleet_sizing_miss_is_distinguishable_from_deadlock():
    """The whole point: a sizing miss and a structural deadlock must read differently.

    CONTRACT UPDATE (2026-08-06, test was stale): c2cb9f72 shipped SHRINK-NOT-DENY
    (2026-08-03) — a sizing miss at an affordable premium is no longer DENIED with
    RISK_CAP; it is shrunk to risk_gate.max_affordable_qty and ALLOWED, with the
    shrink stamped into `reason`. The distinguishability this guard exists for is
    PRESERVED with a new shape:
      * sizing miss  -> ALLOW at the shrunk qty + "shrink-not-deny" note in reason
      * deadlock     -> RISK_CAP deny + binding.deadlock=True (unchanged)
    RED-proofs: disable _shrink_qty_to_affordable (return original qty) -> miss arm
    goes RISK_CAP; strip the shrink note -> the reason assert fails.
    """
    # qty far above the affordable max at a premium the arm CAN otherwise trade.
    miss = _finalize(1.00, qty=30)
    assert miss.action == "ENTER_BEAR"
    assert miss.risk_code == "ALLOW"
    assert miss.qty is not None and 3 <= miss.qty < 30, \
        "shrunk qty must land in [min_contracts, original_qty)"
    assert "shrink-not-deny" in miss.reason, "sizing miss must be legible in the reason"
    assert miss.binding is None, "ALLOW rows keep binding=None (additive-only invariant)"

    lock = _finalize(1.42)
    assert lock.risk_code == "RISK_CAP"
    assert lock.binding["deadlock"] is True


def test_heartbeat_core_execute_wires_binding_on_risk_deny():
    """heartbeat_core._execute must attach `binding` to its RISK_DENY_* row.

    Source-level guard rather than a live _execute call: _execute is a broker-touching
    function (flat-verify, quote fetch, order POST) and this repo's rule is that a test
    never reaches the broker. The wiring is what can regress; the arithmetic it wires is
    already pinned by test_sizing_deadlock_diag.py.
    """
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    deny_idx = src.index('"status": f"RISK_DENY_{')
    window = src[deny_idx:deny_idx + 1600]
    assert '_row["binding"] = rg.explain_block(' in window, \
        "heartbeat_core RISK_DENY row no longer attaches binding telemetry"
    assert "except Exception" in window, \
        "binding telemetry must be wrapped fail-open — it must never break the entry path"


def test_heartbeat_core_binding_is_deny_only():
    """It must NOT be attached to the placement/ALLOW path (additive-only invariant)."""
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert src.count('_row["binding"] = rg.explain_block(') == 1, \
        "binding telemetry should be wired at exactly one (deny) site"
