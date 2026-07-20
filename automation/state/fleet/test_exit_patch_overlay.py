"""Guard for the 2026-07-20 EXIT-PARAMETER A/B overlay (J directive: "every fleet arm takes
the SAME engine signals but with DIFFERENT exit/risk parameters -- one gets stopped out on
the ribbon, one plays the rejection outside the ribbon, one rides it better").

accounts.json's per-arm `params_patch.exit_patch` is a shallow dict merged OVER the
strategies.py REGISTRY's ExitShape.to_dict() (fleet_executor._exit_shape_dict) at every ENTER
call site (_plan_from_strategies' FIX2 path, plan_all's legacy side-block fallback path, and
_probe_plan). This is a VARY-AND-ASSERT guard (C14/L201 discipline: a translated-but-unapplied
knob is this repo's #1 recurring failure class) -- every test here proves the patch actually
REACHES the placed plan through the REAL fleet_executor path against the REAL accounts.json,
not just that _exit_shape_dict parses a patch in isolation. It also proves an unknown exit_patch
key fails LOUD (ValueError), both standalone and through the eager accounts.json-load validator.

Complements test_six_account_exit_shapes.py (the per-arm exit-shape CORRECTNESS contract,
updated same session to be patch-aware).
"""
from __future__ import annotations

import json
from pathlib import Path

import fleet_executor as fx
import strategies as strat_mod

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))


def _arm(arm_id):
    for a in ACCOUNTS["arms"]:
        if a.get("id") == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} not in accounts.json")


# --- fixtures: signals that fire BOTH strategies via the two independent code paths ------
FIX2_SIGNAL = {"spot": 600.0, "strategies": [
    {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
     "triggers": ["level_rejection", "ribbon_flip", "confluence"], "quality": "ELITE",
     "est_premium": 1.20, "spot": 600.0},
    {"name": "vwap_continuation", "side": "C", "setup": "VWAP_CONTINUATION",
     "triggers": ["sequence_reclaim", "VWAP_CONTINUATION_BREAKOUT"], "quality": "ELITE",
     "est_premium": 1.20, "spot": 600.0},
]}

# The LEGACY (pre-FIX2) side-block path: no top-level "strategies" key, so plan_all falls
# back to strategies.fired(side_block) off the setup_name match (plan_all's else-branch,
# the 3rd _exit_shape_dict call site).
LEGACY_VWAP_BEAR_SIGNAL = {
    "spot": 600.0, "production_action": "ENTER_BEAR",
    "bear": {"passed": True, "triggers_fired": ["level_reject", "confluence"],
             "confluence": True, "setup_name": "VWAP_CONTINUATION"},
    "bull": {"passed": False},
}

SAFE_PARAMS = {
    "per_trade_risk_cap_pct": 0.3, "daily_loss_kill_switch_pct": 0.3, "min_contracts": 3,
    "position_sizing_tiers": [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}],
    "recency_min_size_enabled": False,
}


def _enters_by_strategy(arm_id, signal, params=None):
    arm = _arm(arm_id)
    equity = float(arm.get("starting_equity") or 2000.0)
    plans = fx.plan_all(arm, signal, equity, params or SAFE_PARAMS,
                        probe_cfg=ACCOUNTS.get("probe_arm"))
    return {p.strategy: p for p in plans if p.action == "ENTER" and p.strategy}


# --- REACHES THE PLAN (FIX2 path) ---------------------------------------------------------
def test_safe3_exit_patch_reaches_plan_fix2_path():
    """safe-3's exit_patch (stop_mode=structure + trailing) actually lands on the ENTERed
    plan's exit_shape via the FIX2 strategies[] path -- not just parsed, REACHED."""
    patch = _arm("safe-3")["params_patch"]["exit_patch"]
    assert patch, "fixture assumption: safe-3 must carry a non-empty exit_patch"
    enters = _enters_by_strategy("safe-3", FIX2_SIGNAL)
    assert set(enters) == {"ribbon_ride", "vwap_continuation"}
    for name, plan in enters.items():
        for key, val in patch.items():
            assert plan.exit_shape[key] == val, f"safe-3/{name}: {key} not patched"
    # discriminating proof: vwap_continuation's REGISTRY default does NOT already carry
    # these values, so a match here can only come from the patch actually applying.
    vwap_registry = strat_mod.VWAP_CONTINUATION.exit.to_dict()
    assert enters["vwap_continuation"].exit_shape["stop_mode"] != vwap_registry["stop_mode"]
    assert (enters["vwap_continuation"].exit_shape["profit_lock_mode"]
            != vwap_registry["profit_lock_mode"])


def test_risky3_exit_patch_reaches_plan_fix2_path():
    """risky-3's exit_patch (structure + trailing + wider 0.20 trail) reaches BOTH strategies'
    placed plans, and trail_pct differs from EACH strategy's own registry default (ribbon_ride
    defaults trail_pct=0.15, vwap_continuation defaults trail_pct=0.125 -- neither coincides
    with 0.20, so this is a real, unambiguous proof of reach)."""
    patch = _arm("risky-3")["params_patch"]["exit_patch"]
    assert patch.get("trail_pct") == 0.20
    enters = _enters_by_strategy("risky-3", FIX2_SIGNAL)
    assert set(enters) == {"ribbon_ride", "vwap_continuation"}
    for name, plan in enters.items():
        registry = strat_mod.by_name(name).exit.to_dict()
        assert plan.exit_shape["trail_pct"] == 0.20
        assert plan.exit_shape["trail_pct"] != registry["trail_pct"], (
            f"risky-3/{name}: trail_pct matched registry by coincidence, not a real proof of reach"
        )
        assert plan.exit_shape["stop_mode"] == "structure"
        assert plan.exit_shape["profit_lock_mode"] == "trailing"


# --- REACHES THE PLAN (legacy side-block fallback path) -----------------------------------
def test_safe3_exit_patch_reaches_plan_legacy_fallback_path():
    """The pre-FIX2 fallback branch (plan_all's else-clause, no top-level strategies[] key)
    ALSO threads the arm through to _exit_shape_dict -- proves the 3rd call site, not just
    the FIX2 one."""
    enters = _enters_by_strategy("safe-3", LEGACY_VWAP_BEAR_SIGNAL)
    assert "vwap_continuation" in enters
    plan = enters["vwap_continuation"]
    assert plan.exit_shape["stop_mode"] == "structure"
    assert plan.exit_shape["profit_lock_mode"] == "trailing"
    registry = strat_mod.VWAP_CONTINUATION.exit.to_dict()
    assert plan.exit_shape["stop_mode"] != registry["stop_mode"]


# --- REACHES THE PLAN (probe path) ---------------------------------------------------------
def test_risky3_exit_patch_reaches_probe_plan():
    """risky-3 is accounts.json's designated probe_arm (probe_arm.arm_id). A probe-shaped
    signal (normal pass produces nothing; signal['probe'] carries a bypassed cohort) also
    threads the arm's exit_patch into _probe_plan's exit_shape -- the 3rd of 3
    _exit_shape_dict call sites in fleet_executor.py."""
    probe_cfg = ACCOUNTS["probe_arm"]
    assert probe_cfg.get("enabled") and probe_cfg.get("arm_id") == "risky-3", (
        "fixture assumption: risky-3 must be the active probe arm"
    )
    signal = {
        "spot": 600.0,
        "bear": {"passed": False}, "bull": {"passed": False},
        "probe": {"bear": {
            "passed": True, "triggers_fired": ["level_rejection"],
            "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "blocked_verdict": "SKIP_BULL_1100_1200",
        }},
    }
    arm = _arm("risky-3")
    equity = float(arm.get("starting_equity") or 2000.0)
    plans = fx.plan_all(arm, signal, equity, SAFE_PARAMS, probe_cfg=probe_cfg,
                        probe_entries_today=0)
    probe_enters = [p for p in plans if p.action == "ENTER" and "PROBE_ARM" in p.reason]
    assert len(probe_enters) == 1, f"expected exactly 1 probe ENTER, got {plans}"
    plan = probe_enters[0]
    assert plan.exit_shape["stop_mode"] == "structure"
    assert plan.exit_shape["profit_lock_mode"] == "trailing"
    assert plan.exit_shape["trail_pct"] == 0.20
    registry = strat_mod.RIBBON_RIDE.exit.to_dict()
    assert plan.exit_shape["trail_pct"] != registry["trail_pct"]


# --- PARITY: absent/empty exit_patch is a byte-identical no-op ----------------------------
def test_absent_exit_patch_is_byte_identical_noop():
    for strat in (strat_mod.RIBBON_RIDE, strat_mod.VWAP_CONTINUATION):
        assert fx._exit_shape_dict(strat) == strat.exit.to_dict()
        assert fx._exit_shape_dict(strat, {"id": "no-patch-arm"}) == strat.exit.to_dict()
        assert fx._exit_shape_dict(strat, {"id": "empty-patch", "params_patch": {}}) == strat.exit.to_dict()
        assert (fx._exit_shape_dict(strat, {"id": "empty-exit-patch",
                                            "params_patch": {"exit_patch": {}}})
               == strat.exit.to_dict())


def test_risky1_control_arm_has_no_exit_patch():
    """risky-1 (FLEET-TIGHT-R) is the designated untouched control lane -- accounts.json must
    NOT carry an exit_patch for it (2026-07-20 build)."""
    assert not (_arm("risky-1").get("params_patch") or {}).get("exit_patch")


# --- FAIL LOUD on an unknown exit_patch key -------------------------------------------------
def test_unknown_exit_patch_key_raises_on_validate():
    try:
        fx._validate_exit_patch("bad-arm", {"stop_mode": "structure", "bogus_key": 1})
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "bogus_key" in str(e)


def test_unknown_exit_patch_key_raises_via_exit_patch_for_arm():
    bad_arm = {"id": "bad-arm", "params_patch": {"exit_patch": {"not_a_real_key": True}}}
    try:
        fx._exit_patch_for_arm(bad_arm)
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "not_a_real_key" in str(e)


def test_unknown_exit_patch_key_raises_during_merge():
    """The raise fires from the REAL merge call site (_exit_shape_dict), not just the
    standalone validator -- proves the guard is actually wired into the path a live ENTER
    would take."""
    bad_arm = {"id": "bad-arm", "params_patch": {"exit_patch": {"typo_stop_mode": "structure"}}}
    try:
        fx._exit_shape_dict(strat_mod.RIBBON_RIDE, bad_arm)
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "typo_stop_mode" in str(e)


def test_non_dict_exit_patch_raises():
    bad_arm = {"id": "bad-arm", "params_patch": {"exit_patch": ["stop_mode", "structure"]}}
    try:
        fx._exit_patch_for_arm(bad_arm)
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "must be a dict" in str(e)


def test_validate_accounts_exit_patches_raises_at_load():
    """The eager, config-load-time validator (wired into run_dry()/main()) catches a bad
    exit_patch even for an arm whose strategies never fire on a given tick."""
    hostile_accounts = {"arms": [
        {"id": "ok-arm", "status": "active",
         "params_patch": {"exit_patch": {"stop_mode": "structure"}}},
        {"id": "bad-arm", "status": "active",
         "params_patch": {"exit_patch": {"nonsense": 1}}},
    ]}
    try:
        fx.validate_accounts_exit_patches(hostile_accounts)
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "nonsense" in str(e)


def test_run_dry_validates_eagerly_before_any_tick():
    """run_dry() calls validate_accounts_exit_patches BEFORE evaluating any arm -- a bad
    exit_patch on ANY arm raises immediately, even if the signal would never have produced
    an ENTER for that arm this tick (the failure mode a per-merge-only check would miss)."""
    hostile_accounts = {"arms": [
        {"id": "quiet-arm", "status": "active", "starting_equity": 2000.0,
         "params_patch": {"exit_patch": {"bad_key_never_reached": 1}}},
    ]}
    no_setup_signal = {"spot": 600.0, "bear": {"passed": False}, "bull": {"passed": False}}
    try:
        fx.run_dry(no_setup_signal, hostile_accounts)
        raise AssertionError("expected ValueError, none raised")
    except ValueError as e:
        assert "bad_key_never_reached" in str(e)


# --- schema completeness: EXIT_PATCH_ALLOWED_KEYS matches the real ExitShape fields --------
def test_exit_patch_allowed_keys_matches_exitshape_dataclass_fields():
    """The allowlist is DERIVED from strategies.ExitShape, not hand-copied -- this guard
    proves that derivation actually happened (a hand-copied list could silently drift)."""
    assert fx.EXIT_PATCH_ALLOWED_KEYS == frozenset(strat_mod.ExitShape.__dataclass_fields__.keys())
    # every key currently used in accounts.json's exit_patches must be in the allowlist
    for arm_id in ("safe-3", "risky-3"):
        patch = _arm(arm_id)["params_patch"]["exit_patch"]
        assert set(patch) <= fx.EXIT_PATCH_ALLOWED_KEYS, f"{arm_id} exit_patch uses an invented key"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
