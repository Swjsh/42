"""Graduated guard — LEVEL_BREAK_FIRST_STRIKE (LBFS) shadow dispatch wiring (2026-07-15).

Mirrors test_g_db_base_quiet_wiring.py's safety-contract shape for the LBFS detector.
Pins the safety contract so a future edit that accidentally defaults the exec-arm ON,
or wires the detector to the wrong enable flag, REDs here immediately.

CONTEXT: markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md section 4 named
LBFS "absent from the live dispatch list" -- this session closed that gap, SHADOW-LOGGED
ONLY, per the 2026-07-15 revalidation (analysis/recommendations/
lbfs-shadow-wiring-revalidation-2026-07-15.json) which FAILED the walk-forward ratification
bar (wf_ratio=-0.44 < 0.70) despite a positive aggregate (WR=58.8%, +$762.60). The watcher's
own docstring precondition ("3 live J observations confirmed") is separately VERIFIED
UNMET (0/3).

SAFETY CONTRACT (all must hold):
  1. DEFAULT-OFF:  'j_lbfs_enabled' flag absent or False -> NOT dispatched (no row at all
                   in SetupDispatcher.run() results).
  2. ENABLE != ARM: flag True (WATCH mode) -> dispatches signal, but heartbeat_core routes
                   to WATCH_NOT_ARMED when extra_setup_exec_armed key is absent/False.
  3. EXEC-ARM:     extra_setup_exec_armed["level_break_first_strike"]=True is the ONLY key
                   that gates live order placement -- not the detector enable flag. This
                   key is deliberately ABSENT from the shipped params.json (see
                   test_lbfs_not_exec_armed_in_live_params below).
  4. CORRECT MAPPING: direction="short" (LBFS is bearish breakdown-continuation) -> maps
                   to ENTER_BEAR via _synthetic_verdict_from_extra().
  5. SETUP NAME:   must be "level_break_first_strike" (exact string), not any alias.
  6. FLAG NAME:    enable flag must be "j_lbfs_enabled" (not lbfs_enabled, j_level_break_*).
  7. FILTERS GAMMA-SYNC: backtest/lib/filters.py#detect_lbfs / lbfs_enabled exist, delegate
                   to the SAME watcher detector (single source of truth), and lbfs_enabled
                   defaults to False on missing/empty params.

Run:
  cd C:\\Users\\jackw\\Desktop\\42
  backtest\\.venv\\Scripts\\python.exe -m pytest backtest/tests/test_lbfs_shadow_wiring_2026_07_15.py -v
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "setup" / "scripts"
_BACKTEST_LIB = _ROOT / "backtest" / "lib"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_BACKTEST_LIB) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_LIB))

PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"


@pytest.fixture()
def sd_mod():
    """Import setup_dispatch (module-cache reused across tests -- SetupDispatcher carries
    no dangerous module-level mutable state, only per-instance self._params/self._payload/
    self._ctx_cache, so a fresh reimport is not needed for isolation).

    DELIBERATELY does NOT del sys.modules["setup_dispatch"] before reimporting. That
    del-then-reimport pattern (used by test_g_db_base_quiet_wiring.py's identically-named
    fixture) creates a NEW module object each time it runs; any OTHER test file that already
    did `from setup_dispatch import X` at collection time keeps holding the OLD module's
    objects, while a later `unittest.mock.patch("setup_dispatch.Y", ...)` resolves
    sys.modules["setup_dispatch"] fresh and patches the NEW object -- the patch silently
    never takes effect on the code path the other file's tests actually exercise. Confirmed
    by a controlled A/B this session: test_g_db_base_quiet_wiring.py ALONE (pre-existing,
    unrelated to LBFS) already breaks 5 of test_setup_dispatch.py's mock-based tests when run
    in the same pytest session, byte-identical with or without this file present. That is a
    pre-existing cross-file test-isolation bug, not something to compound here.
    """
    return importlib.import_module("setup_dispatch")


@pytest.fixture()
def hc_mod():
    """Import heartbeat_core (module-cache reused -- see sd_mod's docstring for why a
    del-then-reimport is deliberately avoided here)."""
    return importlib.import_module("heartbeat_core")


# ---------------------------------------------------------------------------
# 1. DEFAULT-OFF: flag absent -> setup NOT dispatched (no row in results)
# ---------------------------------------------------------------------------

def test_lbfs_not_dispatched_when_flag_absent(sd_mod):
    """When j_lbfs_enabled is absent from params, the detector produces NO row."""
    params = {}   # flag absent entirely
    payload = {}  # empty payload -- _build_ctx returns None -> SKIP path never reached
    disp = sd_mod.SetupDispatcher(params, payload)
    results = disp.run()
    setup_names = [r.setup_name for r in results]
    assert "level_break_first_strike" not in setup_names, (
        "level_break_first_strike must NOT appear in results when flag is absent"
    )


def test_lbfs_not_dispatched_when_flag_false(sd_mod):
    """When j_lbfs_enabled=False, the detector produces NO row."""
    params = {"j_lbfs_enabled": False}
    disp = sd_mod.SetupDispatcher(params, {})
    results = disp.run()
    assert all(r.setup_name != "level_break_first_strike" for r in results)


# ---------------------------------------------------------------------------
# 2. ENABLE != ARM -- enabled (WATCH) but no exec-arm key -> WATCH_NOT_ARMED
# ---------------------------------------------------------------------------

def test_lbfs_enabled_but_not_exec_armed_is_watch_only(hc_mod, monkeypatch):
    """With only j_lbfs_enabled=True (no exec-arm key), _execute is never called."""
    called = {"n": 0}
    monkeypatch.setattr(hc_mod, "_execute",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    params = {"j_lbfs_enabled": True}   # enabled (WATCH) but NOT exec-armed
    extra = [{
        "setup_name": "level_break_first_strike",
        "fired": True,
        "direction": "short",
        "triggers": ["MIXED_RIBBON_LEVEL_BREAK", "VOL_1.5X"],
    }]
    out = hc_mod._route_extra_setups("safe", extra, {"bar_ctx": {}}, params)
    assert called["n"] == 0, "_execute must NOT be called when only enabled, not exec-armed"
    assert out == [{"setup": "level_break_first_strike", "action": "WATCH_NOT_ARMED"}]


# ---------------------------------------------------------------------------
# 3. EXEC-ARM KEY -- exact spelling and exact True value required
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {},                                                                # key absent
    {"extra_setup_exec_armed": {}},                                    # empty dict
    {"extra_setup_exec_armed": {"level_break_first_strike": False}},   # explicit False
    {"extra_setup_exec_armed": {"level_break_first_strike": 1}},       # truthy-not-True
    {"extra_setup_exec_armed": {"level_break_first_strike": "true"}},  # string, not bool
    {"extra_setup_exec_armed": {"lbfs": True}},                        # wrong key name
])
def test_exec_arm_defaults_off(hc_mod, params):
    """All non-True and alias keys must return False from _extra_exec_armed."""
    assert hc_mod._extra_exec_armed(params, "level_break_first_strike") is False


def test_exec_arm_requires_exact_true(hc_mod):
    """Only exact bool True arms the setup; a different setup stays off."""
    armed_params = {"extra_setup_exec_armed": {"level_break_first_strike": True}}
    assert hc_mod._extra_exec_armed(armed_params, "level_break_first_strike") is True
    # arming LBFS must not arm any other extra setup
    assert hc_mod._extra_exec_armed(armed_params, "double_bottom_base_quiet") is False
    assert hc_mod._extra_exec_armed(armed_params, "vwap_continuation") is False


def test_lbfs_not_exec_armed_in_live_params(hc_mod):
    """The SHIPPED params.json must NOT exec-arm LBFS -- this is the load-bearing safety
    fact of the whole 2026-07-15 shadow-only ship. If this ever flips True without a
    documented follow-up ratification, this guard REDs immediately."""
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    assert hc_mod._extra_exec_armed(params, "level_break_first_strike") is False, (
        "level_break_first_strike must stay un-armed in the shipped params.json -- "
        "the 2026-07-15 revalidation FAILED the walk-forward ratification bar "
        "(wf_ratio=-0.44 < 0.70; analysis/recommendations/"
        "lbfs-shadow-wiring-revalidation-2026-07-15.json). Live arming needs its own "
        "follow-up study, not a silent flag flip."
    )
    # j_lbfs_enabled itself SHOULD be True (that's the shadow-logging point) -- detection
    # runs+logs; only the exec-arm is withheld. Document rather than assume.
    assert params.get("j_lbfs_enabled") is True, (
        "j_lbfs_enabled should be True for the shadow-logging telemetry to accumulate; "
        "if this is False, LBFS produces zero visibility (back to the pre-2026-07-15 gap)."
    )


# ---------------------------------------------------------------------------
# 4. CORRECT MAPPING: direction="short" -> ENTER_BEAR
# ---------------------------------------------------------------------------

def test_lbfs_short_maps_to_enter_bear(hc_mod):
    """LBFS is a bearish breakdown-continuation setup -- direction='short' must map to
    ENTER_BEAR."""
    row = {
        "setup_name": "level_break_first_strike",
        "fired": True,
        "direction": "short",
        "triggers": ["MIXED_RIBBON_LEVEL_BREAK", "VOL_1.5X"],
    }
    sv = hc_mod._synthetic_verdict_from_extra(row)
    assert sv is not None, "_synthetic_verdict_from_extra must not return None for fired=short"
    assert sv["verdict"] == "ENTER_BEAR"
    assert sv["side"] == "P"
    assert sv["setup_name"] == "level_break_first_strike"


# ---------------------------------------------------------------------------
# 5. FLAG NAME guard -- the enable flag must be "j_lbfs_enabled"
# ---------------------------------------------------------------------------

def test_enable_flag_name_is_j_lbfs_enabled(sd_mod):
    """The enable flag literal 'j_lbfs_enabled' triggers dispatch when True.

    Patches _build_ctx to return None (so the detector call itself is skipped) and
    verifies that setting j_lbfs_enabled=True causes a row to appear in results (with
    SKIP_NO_FEED), while plausible aliases do NOT.
    """
    with patch.object(sd_mod.SetupDispatcher, "_build_ctx", return_value=None):
        disp_on = sd_mod.SetupDispatcher({"j_lbfs_enabled": True}, {})
        results_on = disp_on.run()
        assert any(r.setup_name == "level_break_first_strike" for r in results_on), (
            "j_lbfs_enabled=True must trigger dispatch (even if SKIP_NO_FEED)"
        )

        for bad_flag in ("lbfs_enabled", "j_level_break_first_strike_enabled", "lbfs_shadow_enabled"):
            disp_bad = sd_mod.SetupDispatcher({bad_flag: True}, {})
            results_bad = disp_bad.run()
            assert all(r.setup_name != "level_break_first_strike" for r in results_bad), (
                f"Alias '{bad_flag}' must NOT trigger dispatch -- only 'j_lbfs_enabled' is valid"
            )


# ---------------------------------------------------------------------------
# 6. SETUP NAME integrity -- exact string "level_break_first_strike"
# ---------------------------------------------------------------------------

def test_setup_name_exact_string(sd_mod):
    """When the flag is on and ctx is missing, the DispatchResult carries the exact
    setup name."""
    with patch.object(sd_mod.SetupDispatcher, "_build_ctx", return_value=None):
        disp = sd_mod.SetupDispatcher({"j_lbfs_enabled": True}, {})
        results = disp.run()
        lbfs_results = [r for r in results if r.setup_name == "level_break_first_strike"]
        assert len(lbfs_results) == 1
        assert lbfs_results[0].fired is False
        assert lbfs_results[0].skip_reason == "SKIP_NO_FEED:sameday_5m_bars_missing"


# ---------------------------------------------------------------------------
# 7. filters.py GAMMA-SYNC delegator pair
# ---------------------------------------------------------------------------

def test_filters_lbfs_delegators_exist_and_delegate():
    """detect_lbfs/lbfs_enabled exist in filters.py and delegate to the SAME watcher
    detector as setup_dispatch.py (single source of truth, no drift)."""
    import datetime as dt
    import pandas as pd
    from lib import filters as filters_mod
    from lib.watchers.level_break_first_strike_watcher import detect_lbfs_setup
    from lib.ribbon import RibbonState

    assert hasattr(filters_mod, "detect_lbfs")
    assert hasattr(filters_mod, "lbfs_enabled")
    # default-off
    assert filters_mod.lbfs_enabled(None) is False
    assert filters_mod.lbfs_enabled({}) is False
    assert filters_mod.lbfs_enabled({"j_lbfs_enabled": True}) is True
    assert filters_mod.lbfs_enabled({"j_lbfs_enabled": False}) is False

    # Delegation identity: detect_lbfs(ctx) must produce the IDENTICAL result to calling
    # detect_lbfs_setup(ctx) directly, for both a firing ctx and a non-firing ctx --
    # proves filters.detect_lbfs is a pure pass-through, not a second drifted copy.
    bar = pd.Series({"open": 601.2, "high": 601.3, "low": 600.4, "close": 600.50, "volume": 9000.0})
    ctx = filters_mod.BarContext(
        bar_idx=3, timestamp_et=dt.datetime(2026, 1, 7, 9, 45), bar=bar,
        prior_bars=pd.DataFrame([bar.to_dict()]),
        ribbon_now=RibbonState(fast=601.0, pivot=601.1, slow=601.15, spread_cents=15.0, stack="MIXED"),
        ribbon_history=[], vix_now=22.0, vix_prior=22.05, vol_baseline_20=3000.0,
        range_baseline_20=0.5, levels_active=[601.00], multi_day_levels=[], htf_15m_stack="MIXED",
    )
    direct = detect_lbfs_setup(ctx)
    via_filters = filters_mod.detect_lbfs(ctx)
    assert direct is not None, "sanity: this ctx should fire LBFS"
    assert via_filters is not None
    assert via_filters.direction == direct.direction == "short"
    assert via_filters.entry_price == direct.entry_price
    assert via_filters.watcher_name == direct.watcher_name == "level_break_first_strike_watcher"

    # Non-firing ctx (ribbon BEAR, not MIXED) -> both return None identically.
    ctx_no_fire = filters_mod.BarContext(
        bar_idx=3, timestamp_et=dt.datetime(2026, 1, 7, 9, 45), bar=bar,
        prior_bars=pd.DataFrame([bar.to_dict()]),
        ribbon_now=RibbonState(fast=601.0, pivot=601.1, slow=601.15, spread_cents=15.0, stack="BEAR"),
        ribbon_history=[], vix_now=22.0, vix_prior=22.05, vol_baseline_20=3000.0,
        range_baseline_20=0.5, levels_active=[601.00], multi_day_levels=[], htf_15m_stack="MIXED",
    )
    assert detect_lbfs_setup(ctx_no_fire) is None
    assert filters_mod.detect_lbfs(ctx_no_fire) is None


# ---------------------------------------------------------------------------
# 8. Fired signal end-to-end -> logged (visible), never executed (regression proof
#    that a REAL qualifying bar produces a row but zero order placement)
# ---------------------------------------------------------------------------

def _mixed_ribbon_level_break_payload() -> dict:
    """A synthetic bar that satisfies EVERY LBFS gate: MIXED ribbon, spread in [12,30)c,
    VIX>=20 and not hard-falling, volume>=1.5x baseline, close >=20c below an active
    level, time >= 09:45 ET."""
    def bar_row(h, m, o, hi, lo, c, v):
        return {"timestamp_iso": f"2026-01-07T{h:02d}:{m:02d}:00-04:00",
                "open": o, "high": hi, "low": lo, "close": c, "volume": v}

    sameday = [
        bar_row(9, 30, 602.0, 602.2, 601.8, 602.0, 3000),
        bar_row(9, 35, 602.0, 602.1, 601.5, 601.6, 3000),
        bar_row(9, 40, 601.6, 601.7, 601.0, 601.2, 3000),
        bar_row(9, 45, 601.2, 601.3, 600.4, 600.50, 9000),  # trigger: 50c below level, 3x vol
    ]
    bar_ctx = {
        "bar_idx": 3, "timestamp_et": sameday[-1]["timestamp_iso"],
        "bar": {"open": 601.2, "high": 601.3, "low": 600.4, "close": 600.50, "volume": 9000},
        "prior_bars": [{k: r[k] for k in ("open", "high", "low", "close", "volume")} for r in sameday],
        "ribbon_now": {"fast": 601.0, "pivot": 601.1, "slow": 601.15, "spread_cents": 15.0, "stack": "MIXED"},
        "ribbon_history": [], "vix_now": 22.0, "vix_prior": 22.05,
        "vol_baseline_20": 3000.0, "range_baseline_20": 0.5,
        "levels_active": [601.00], "multi_day_levels": [], "htf_15m_stack": "MIXED",
        "level_states": {}, "fhh_level": None, "vix_5d_ma": 0.0, "vix_20d_ma": 0.0,
    }
    return {"bar_ctx": bar_ctx, "sameday_5m_bars": sameday, "spy_df": []}


def test_lbfs_real_qualifying_bar_fires_and_logs_but_never_executes(sd_mod, hc_mod, monkeypatch):
    """End-to-end: a bar that genuinely satisfies every LBFS detection gate produces a
    fired=True DispatchResult (visible in extra_signals), but routing it through the
    REAL _route_extra_setups (not a mock) proves _execute is never called."""
    called = {"n": 0}
    monkeypatch.setattr(hc_mod, "_execute",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    payload = _mixed_ribbon_level_break_payload()
    params = {"j_lbfs_enabled": True}  # shadow-shipped shape: enabled, NOT exec-armed

    disp = sd_mod.SetupDispatcher(params, payload)
    results = disp.run()
    lbfs = [r for r in results if r.setup_name == "level_break_first_strike"]
    assert len(lbfs) == 1
    assert lbfs[0].fired is True, "LBFS must fire on a bar that satisfies every documented gate"
    assert lbfs[0].signal.direction == "short"

    extra = sd_mod.dispatch_extra_setups("safe", params, payload, {}, armed=False)
    assert any(r["setup_name"] == "level_break_first_strike" and r["fired"] for r in extra), (
        "the fired LBFS row must be visible in dispatch_extra_setups' output "
        "(-> rec['extra_signals'] -> core-decisions.jsonl)"
    )

    routed = hc_mod._route_extra_setups("safe", extra, payload, params)
    assert called["n"] == 0, "REGRESSION: _execute was called for a shadow-only LBFS signal"
    assert {"setup": "level_break_first_strike", "action": "WATCH_NOT_ARMED"} in routed
