"""SHIP C guards -- risky-3 cheap-contract qty boost (2026-08-03).

J verbatim: "if it's under point five o for a contract, let's buy ten of them...
let's just do that for risky three."

Pins, RED-on-regression:
  1. VARY-AND-ASSERT (C14): the params key actually changes finalize()'s sized qty --
     a $0.38 plan on an arm carrying the patch resolves qty 10; without the key it
     resolves the plan's own qty. A silently-unrouted key is the dead-knob class that
     has bitten this repo three times.
  2. SCOPE: only risky-3's params_patch carries the key (single-arm A/B by design).
  3. THRESHOLD EDGES: $0.50 exactly does NOT boost (strictly-below), $0.55 does not;
     the boost never SHRINKS a larger plan.
  4. RULE 6 AUTHORITY: shrink-not-deny + risk_gate run AFTER the boost -- a boosted
     qty that busts the cap gets shrunk/refused exactly as any other size would.
  5. Absent/malformed config = byte-identical no-op (fail-open).

Run: backtest/.venv python -m pytest -q backtest/tests/test_cheap_contract_qty_boost_2026_08_03.py
Revert of SHIP C: delete the two keys from risky-3's params_patch -> tests 1/2 flip
to the no-boost expectations (test_no_boost_without_key stays green and pins that).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(FLEET), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_executor as fx  # noqa: E402

SAFE_BASE = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))


def _plan(arm="risky-3", qty=5):
    return fx.EntryPlan(arm_id=arm, action="ENTER_BULL", side="C",
                        setup_name="ribbon_ride", strike=754, qty=qty,
                        quality="ELITE", reason="test")


def _finalize(plan, params, premium):
    return fx.finalize(plan, equity=5000.0, start_of_day_equity=5000.0,
                       premium=premium, current_position_status="flat",
                       day_trades_used_5d=0, kill_switch_tripped=False,
                       prior_stops_today=[], params=params, account_label="risky-3")


def _boost_params(**over):
    p = dict(SAFE_BASE)
    p["min_entry_premium"] = 0.3
    p["cheap_contract_qty_boost"] = {"premium_below": 0.5, "qty": 10}
    p.update(over)
    return p


def _plain_params(**over):
    p = dict(SAFE_BASE)
    p["min_entry_premium"] = 0.3
    p.pop("cheap_contract_qty_boost", None)
    p.update(over)
    return p


# --- 1. the vary-and-assert -------------------------------------------------------
def test_boost_fires_below_threshold():
    d = _finalize(_plan(qty=5), _boost_params(), premium=0.38)
    assert d.action == "ENTER_BULL", d
    assert d.qty == 10, f"expected boosted qty 10, got {d.qty}"


def test_no_boost_without_key():
    d = _finalize(_plan(qty=5), _plain_params(), premium=0.38)
    assert d.action == "ENTER_BULL", d
    assert d.qty == 5, f"key absent must be byte-identical: got {d.qty}"


# --- 2. scope: the LIVE registry patches exactly one arm --------------------------
def test_only_risky3_carries_the_key_live():
    reg = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
    arms = reg["arms"] if "arms" in reg else reg
    arms = list(arms.values()) if isinstance(arms, dict) else arms
    carriers = [a["id"] for a in arms
                if isinstance(a.get("params_patch"), dict)
                and "cheap_contract_qty_boost" in a["params_patch"]]
    assert carriers == ["risky-3"], carriers
    cfg = next(a for a in arms if a["id"] == "risky-3")["params_patch"]["cheap_contract_qty_boost"]
    assert cfg == {"premium_below": 0.5, "qty": 10}, cfg


# --- 3. threshold edges -----------------------------------------------------------
@pytest.mark.parametrize("premium,expected_qty", [
    (0.49, 10),   # below -> boost
    (0.50, 5),    # exactly at threshold -> strictly-below, no boost
    (0.55, 5),    # above -> no boost
])
def test_threshold_is_strictly_below(premium, expected_qty):
    d = _finalize(_plan(qty=5), _boost_params(), premium=premium)
    assert d.qty == expected_qty, (premium, d.qty)


def test_boost_never_shrinks_a_larger_plan():
    d = _finalize(_plan(qty=12), _boost_params(), premium=0.38)
    assert d.qty >= 12, f"boost must never reduce qty: got {d.qty}"


# --- 4. Rule 6 stays authoritative over the boosted size --------------------------
def test_risk_cap_still_binds_boosted_qty():
    # equity $500: 50%/30% cap makes 10 x 0.49 x 100 = $490 unaffordable at the safe
    # 30% cap ($150) -> shrink/refuse must engage; the boost cannot bypass the gate.
    d = fx.finalize(_plan(qty=5), equity=500.0, start_of_day_equity=500.0,
                    premium=0.49, current_position_status="flat",
                    day_trades_used_5d=0, kill_switch_tripped=False,
                    prior_stops_today=[], params=_boost_params(), account_label="risky-3")
    assert (d.action == "HOLD") or (d.qty < 10), d


# --- 5. malformed config fails open ------------------------------------------------
@pytest.mark.parametrize("bad", [
    {"premium_below": "x", "qty": 10},
    {"premium_below": 0.5},
    {"qty": 10},
    "not-a-mapping",
    None,
])
def test_malformed_config_is_a_noop(bad):
    d = _finalize(_plan(qty=5), _boost_params(cheap_contract_qty_boost=bad), premium=0.38)
    assert d.qty == 5, (bad, d.qty)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
