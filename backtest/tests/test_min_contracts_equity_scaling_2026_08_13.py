"""Guard: the recency clamp's floor is an EQUITY FRACTION, not a $2K-era constant.

WHAT THIS FIXES (J directive 2026-08-13, "fix all issues like account sizing being wrong"):

    `min_contracts = 3` was authored when an account held ~$2,000. It is the ONLY sizing knob in
    params.json that is an absolute COUNT -- per_trade_risk_cap_pct and daily_loss_kill_switch_pct
    are PERCENTAGES and rescale themselves. Equity is now $5,501 and the count never moved.

    That matters because fleet_executor._apply_recency_min_sizing uses the FLOOR as a CEILING
    (`clamped = min(qty, min_contracts)`), so a risk gate that correctly computed 8 contracts was
    overridden back to the $2K-era 3. Measured live on 2026-08-13:
        safe-3 : qty clamped 8 -> 3   (equity 4470)
        risky-1: qty clamped 12 -> 5  (equity 4979)

THIS IS A RESTORATION, NOT AN UPSIZE. At $2,000 equity, 3 contracts at ~$1.03 was 15.4% of
equity. At $5,501 the same 3 contracts is 5.6% -- the clamp became 2.75x tighter than the policy
that was A/B validated (recency-sizing-ab.json, policy_dominates=true, -$1,274 improvement).
Scaling the floor by equity/baseline makes the policy mean today what it meant when it was
measured. It restores 3 -> 8 (the risk gate's own answer), NOT 3 -> 16 (the full risk cap).

WHY NOT the 5.6x number from the review: equity-proportional sizing on every trade would have
made +$9,734 instead of +$1,748 today -- but today's zero drawdown was ORDERING LUCK (the 09:51
winners landed before every loser). Reversed, bold-2 ends at -39.8% of equity. And C31 stands:
J's 667 real trades are +$4,576 at 1-2 lots and -$17,461 at 3+. Sizing up is the documented
historical killer, so the change is deliberately bounded to restoring the validated intent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FE_PATH = REPO / "automation" / "state" / "fleet" / "fleet_executor.py"


@pytest.fixture(scope="module")
def fe():
    sys.path.insert(0, str(FE_PATH.parent))
    spec = importlib.util.spec_from_file_location("_fe_minqty_probe", FE_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_fe_minqty_probe"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _pin_recency_red(fe, monkeypatch):
    """LIVE-STATE DEPENDENCY REMOVED (2026-09-03 03:50 ET). Every assertion below is scoped to
    'recency is RED' (the clamp's only active branch), but the module read the LIVE
    automation/state/recency-confirmation.json through fe._recency_verdict. It passed for
    weeks only because recency happened to be RED; at 2026-09-03 00:42 ET a real OosCheck run
    flipped headline.any_red -> False / edges_confirmed_on_recent -> True (bull side now the
    winner), the clamp correctly released, and 12 of these tests went RED in the full suite
    with floors of 8/12/99 -- a test measuring the market, not the code (C7 / L298 class).
    Pin the verdict the docstrings already assume."""
    monkeypatch.setattr(fe, "_recency_verdict", lambda *a, **k: "RED")


BASE = {"recency_min_size_enabled": True, "min_contracts": 3,
        "min_contracts_equity_scaled": True, "min_contracts_baseline_equity": 2000.0}


def _call(fe, qty, params, equity, strat=None):
    return fe._apply_recency_min_sizing(qty, strat or fe.RECENCY_MIN_SIZE_STRATEGY, params, equity)


# --------------------------------------------------------------- the restoration


def test_the_live_2026_08_13_clamp_is_restored(fe):
    """THE INCIDENT. safe-3's risk gate said 8 at equity 4470 and the clamp cut it to 3.
    Scaled: 3 * 4470/2000 = 6.7 -> 7, so min(8, 7) = 7 -- the gate's answer is no longer
    overridden by a $2K constant."""
    qty, note = _call(fe, 8, BASE, 4470.48)
    assert qty == 7, f"expected the floor to scale to 7 at equity 4470, got {qty}"
    qty2, _ = _call(fe, 8, BASE, 5501.0)
    assert qty2 == 8, f"at equity 5501 the floor scales to 8 and must not clamp an 8, got {qty2}"


def test_it_never_raises_qty_above_what_the_risk_gate_computed(fe):
    """SAFETY INVARIANT. This is a CEILING (min()), never a floor-raise. If the gate says 4, the
    result is 4 even though the scaled floor is 8 -- the clamp can only ever reduce."""
    qty, _ = _call(fe, 4, BASE, 5501.0)
    assert qty == 4, f"clamp raised qty from 4 to {qty} -- it must never increase size"


def test_flag_off_is_byte_identical_to_the_pre_fix_behaviour(fe):
    """The whole change must be inert until deliberately enabled."""
    off = dict(BASE, min_contracts_equity_scaled=False)
    qty, note = _call(fe, 8, off, 5501.0)
    assert qty == 3, f"with the flag off the clamp must still cut to 3, got {qty}"
    assert note and "8->3" in note


def test_at_the_baseline_equity_it_reproduces_the_original_floor(fe):
    """VARY-AND-ASSERT identity point (C14): at exactly $2,000 the scaled floor IS 3, so the
    validated policy is reproduced rather than replaced."""
    qty, _ = _call(fe, 12, BASE, 2000.0)
    assert qty == 3, f"at baseline equity the floor must remain 3, got {qty}"


def test_it_never_scales_the_floor_DOWN(fe):
    """A drawdown below baseline must not tighten the clamp below min_contracts -- Rule 6's
    'min 3 contracts (2 TP + 1 runner)' is a hard floor, not a target."""
    for eq in (500.0, 1000.0, 1999.0):
        qty, _ = _call(fe, 12, BASE, eq)
        assert qty == 3, f"equity {eq} scaled the floor below min_contracts (got {qty})"


@pytest.mark.parametrize("eq,expected", [(2000.0, 3), (3000.0, 5), (4470.48, 7), (5501.0, 8), (10000.0, 15)])
def test_scaling_is_monotone_in_equity(fe, eq, expected):
    """If the floor does not move with equity, the fix did not bind (C14)."""
    qty, _ = _call(fe, 99, BASE, eq)
    assert qty == expected, f"equity {eq}: expected floor {expected}, got {qty}"


# --------------------------------------------------------------- fail-safe direction


@pytest.mark.parametrize("bad", [None, 0, "", "abc", -100.0])
def test_unreadable_equity_falls_back_to_the_SMALLER_unscaled_floor(fe, bad):
    """FAIL-SAFE DIRECTION. A bad equity read must degrade toward LESS size, never more --
    the opposite would size up on missing data, which is the worst possible failure mode."""
    qty, _ = _call(fe, 12, BASE, bad)
    assert qty == 3, f"equity={bad!r} produced floor {qty}; must fall back to the unscaled 3"


def test_missing_baseline_key_falls_back_to_unscaled(fe):
    p = dict(BASE); p.pop("min_contracts_baseline_equity")
    qty, _ = _call(fe, 12, p, 5501.0)
    assert qty == 3


def test_wrong_strategy_and_flag_off_still_pass_through_untouched(fe):
    """Scope: this only ever touches ribbon_ride while recency is RED."""
    qty, note = _call(fe, 12, BASE, 5501.0, strat="some_other_strategy")
    assert qty == 12 and note is None
    p = dict(BASE, recency_min_size_enabled=False)
    qty2, note2 = _call(fe, 12, p, 5501.0)
    assert qty2 == 12 and note2 is None


# --------------------------------------------------------------- all call sites patched


def test_every_call_site_passes_equity(fe):
    """THE HALF-LANDED-FIX GUARD. There are THREE call sites (plan_entry, _plan_from_strategies,
    plan_all). Patching one and missing two is exactly the vwap-kill defect found earlier on
    2026-08-13, which landed on 2 of 5 arms and cost -$1,046. Every call site must pass equity or
    that site silently keeps the $2K constant."""
    import re
    src = FE_PATH.read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    calls = re.findall(r"_apply_recency_min_sizing\(([^)]*)\)", code)
    invocations = [c for c in calls if "qty" in c]
    assert len(invocations) >= 3, f"expected >=3 invocations, found {len(invocations)}"
    for c in invocations:
        assert "equity" in c, (
            f"a call site does NOT pass equity: _apply_recency_min_sizing({c.strip()}) -- that "
            "site still clamps to the un-scaled $2K-era floor while the others do not")


def test_the_full_send_clamp_scales_TOO_or_the_fix_is_a_no_op(fe):
    """THE HALF-LANDED FIX, CAUGHT PRE-SHIP.

    There are TWO clamps against min_contracts: _apply_recency_min_sizing and
    _apply_full_send_min_sizing. They run BACK TO BACK (fleet_executor ~750/751 and ~949/950).
    risky-1 is `full_send: true` AND `live: true` in accounts.json -- so scaling only the recency
    floor is silently re-clamped to the $2K-era constant one line later, and the fix does nothing
    on the one live arm it was aimed at.

    This is the same class as the vwap kill that landed on 2 of 5 arms (-$1,046) earlier the same
    day. Pinning both clamps together is what stops it recurring.
    """
    arm = {"gate_override": {"full_send": True}}
    params = {"min_contracts": 5, "min_contracts_equity_scaled": True,
              "min_contracts_baseline_equity": 1648.0}
    qty, note = fe._apply_full_send_min_sizing(20, arm, params, 5384.17)
    assert qty == 16, (
        f"full_send clamped to {qty}; expected 16 (5 * 5384/1648 = 16.3). If this is 5, the "
        "recency scaling is being undone one line later and the fix is a no-op on risky-1.")
    # flag off -> byte-identical to the pre-fix behaviour
    off = dict(params, min_contracts_equity_scaled=False)
    qty2, _ = fe._apply_full_send_min_sizing(20, arm, off, 5384.17)
    assert qty2 == 5
    # still a ceiling, never a floor-raise
    qty3, _ = fe._apply_full_send_min_sizing(3, arm, params, 5384.17)
    assert qty3 == 3, "full_send raised qty from 3 -- min() must only ever reduce"
    # non-full-send arms untouched
    qty4, note4 = fe._apply_full_send_min_sizing(20, {"gate_override": {}}, params, 5384.17)
    assert qty4 == 20 and note4 is None


def test_every_full_send_call_site_passes_equity(fe):
    """Same half-landed guard as the recency one, for the second clamp."""
    import re
    code = "\n".join(l for l in FE_PATH.read_text(encoding="utf-8").splitlines()
                     if not l.strip().startswith("#"))
    calls = [c for c in re.findall(r"_apply_full_send_min_sizing\(([^)]*)\)", code) if "qty" in c]
    assert len(calls) >= 2, f"expected >=2 full_send invocations, found {len(calls)}"
    for c in calls:
        assert "equity" in c, f"full_send call site does not pass equity: ({c.strip()})"


def test_both_params_files_carry_the_baseline(fe):
    """Each account file must declare its OWN baseline -- safe was validated at $2,000 and bold
    at $1,648 (recency-confirmation.json config.equity). A shared constant would mis-scale one."""
    for f, expect in (("automation/state/params.json", 2000.0),
                      ("automation/state/aggressive/params.json", 1648.0)):
        d = json.loads((REPO / f).read_text(encoding="utf-8"))
        assert d.get("min_contracts_baseline_equity") == expect, (
            f"{f}: baseline is {d.get('min_contracts_baseline_equity')}, expected {expect} -- "
            "the equity each arm's clamp was actually validated at")
        assert "min_contracts_equity_scaled" in d, f"{f} missing the arming flag"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
