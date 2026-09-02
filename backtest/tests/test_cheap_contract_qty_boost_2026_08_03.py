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
import re
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


# --- reading the boost through the tight-ladder ceiling ----------------------------
#
# WHY EVERY ASSERTION BELOW READS `reason` AND NOT JUST `qty` (repaired 2026-09-02,
# queue.md TIGHT-LADDER-LEFT-THREE-STALE-QTY-FIXTURES).
#
# These fixtures were written 2026-08-03, before `max_contracts_per_entry: 5` shipped on
# 2026-08-29 (PREREG-TIGHT-LADDER-2026-08-28 S2, a ratified risk control inside the config
# freeze). The ceiling now clamps the boost's 10 down to 5 BEFORE the decision is returned,
# so `assert d.qty == 10` fails -- correctly. The ceiling is right; the fixtures were stale.
#
# The trap in the obvious repair: post-clamp qty is **5 in every single case** -- boosted or
# not, threshold or not. Rewriting these as `assert d.qty == 5` would make them pass while
# testing NOTHING (they could no longer distinguish a working boost from a deleted one --
# C14, a knob that cannot be observed is a knob that quietly dies).
#
# The clamp records what it clamped FROM: "qty capped 10->5: tight-ladder
# max_contracts_per_entry" (fleet_executor.py:1345). That pre-clamp number is the only
# surviving evidence the boost ran, so it is what these tests assert -- which pins both
# mechanisms AND their ORDER (boost first, ceiling second), strictly more than the original
# assertion did.
_CAP_RE = re.compile(r"qty capped (\d+)->(\d+): tight-ladder max_contracts_per_entry")


def _preclamp_qty(d):
    """The qty the sizing chain produced BEFORE the tight-ladder ceiling, or None if the
    ceiling never bound (in which case d.qty IS the pre-clamp qty)."""
    m = _CAP_RE.search(d.reason or "")
    return int(m.group(1)) if m else None


def _effective_qty(d):
    """What the boost computed, whether or not the ceiling then clamped it."""
    pre = _preclamp_qty(d)
    return d.qty if pre is None else pre


# --- 1. the vary-and-assert -------------------------------------------------------
def test_boost_fires_below_threshold():
    """The boost raises 5 -> 10, and the tight-ladder ceiling then binds at 5.

    Both halves are asserted: the ceiling is the operative cap (qty), and the boost really
    ran (pre-clamp 10). Dropping either half loses a mechanism.
    """
    d = _finalize(_plan(qty=5), _boost_params(), premium=0.38)
    assert d.action == "ENTER_BULL", d
    assert _effective_qty(d) == 10, f"boost did not raise 5->10: {d.reason!r}"
    assert d.qty == 5, (
        f"tight-ladder max_contracts_per_entry must bind at 5, got {d.qty} -- the ratified "
        f"risk control is not clamping: {d.reason!r}"
    )


def test_no_boost_without_key():
    """Absent key = OFF, byte-identical.

    This test was PASSING while the other three failed, and it was still broken -- just
    silently. It asserted `d.qty == 5`, and since 2026-08-29 the tight-ladder ceiling makes
    returned qty 5 whether the boost runs or not, so it passed identically with the key
    present. A green vacuous test is more dangerous than a red stale one: nothing flags it.
    Assert the pre-clamp qty and the absence of a cap note, which do differ.
    """
    d = _finalize(_plan(qty=5), _plain_params(), premium=0.38)
    assert d.action == "ENTER_BULL", d
    assert _effective_qty(d) == 5, f"key absent must be byte-identical: {d.reason!r}"
    assert _preclamp_qty(d) is None, (
        f"no boost means nothing to clamp, so no cap note should appear: {d.reason!r}"
    )


def test_the_fixtures_can_still_tell_boost_on_from_boost_off():
    """Non-vacuity, pinned. The tight-ladder ceiling flattens every returned qty in this
    file to 5, so a future 'simplification' back to `assert d.qty == N` would leave a suite
    that passes with the boost deleted. This asserts the two configurations are actually
    distinguishable by what the tests read."""
    on = _finalize(_plan(qty=5), _boost_params(), premium=0.38)
    off = _finalize(_plan(qty=5), _plain_params(), premium=0.38)
    assert on.qty == off.qty == 5, "premise: the ceiling flattens both to 5"
    assert _effective_qty(on) != _effective_qty(off), (
        "boost-on and boost-off are indistinguishable to these assertions -- the suite can "
        "no longer detect a dead boost"
    )


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
@pytest.mark.parametrize("premium,expected_effective_qty,expect_boost", [
    (0.49, 10, True),    # below -> boost
    (0.50, 5, False),    # exactly at threshold -> strictly-below, no boost
    (0.55, 5, False),    # above -> no boost
])
def test_threshold_is_strictly_below(premium, expected_effective_qty, expect_boost):
    """The strictly-below edge, read through the ceiling.

    NOTE the parameters are EFFECTIVE (pre-clamp) qty, not returned qty: the ceiling makes
    returned qty 5 on all three rows, so a `d.qty ==` assertion here would pass for every
    premium and prove nothing about the threshold.
    """
    d = _finalize(_plan(qty=5), _boost_params(), premium=premium)
    assert _effective_qty(d) == expected_effective_qty, (premium, d.reason)
    assert (_preclamp_qty(d) is not None) is expect_boost, (
        f"premium {premium}: expected boost={expect_boost}; reason={d.reason!r}"
    )
    assert d.qty == 5, f"the ceiling must bind at 5 regardless: {d.reason!r}"


def test_boost_never_shrinks_a_larger_plan():
    """A plan already above the boost's qty must not be pulled DOWN to it.

    Read pre-clamp, because the ceiling flattens every outcome to 5: the property is that
    the pre-clamp qty is 12 (untouched), never 10 (the boost overwriting a larger plan).
    """
    d = _finalize(_plan(qty=12), _boost_params(), premium=0.38)
    assert _effective_qty(d) == 12, (
        f"boost reduced a larger plan to its own qty: {d.reason!r}"
    )
    assert d.qty == 5, f"the ceiling must still bind at 5: {d.reason!r}"


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
