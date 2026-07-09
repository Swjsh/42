"""STRUCTURE-STOP (v15.3 chart-stop-primary, 2026-07-09) -- cross-module wiring guards.

test_exit_manager.py covers the pure core (exit_manager.py) in isolation. THIS file proves
the plumbing that carries a trigger_level from the entry signal all the way to a live
ExitState, and back down from a closed-5m-SPY-close feed into a firing structure exit, for
BOTH consumption lanes named in the wiring map (fleet_rest via fleet_executor/fleet_live/
exit_actuator; core via heartbeat_core). Static (grep-based) wiring guards mirror the
existing precedent in backtest/tests/test_g14_fleet_ribbon_exit.py -- they RED if a future
edit silently drops a kwarg the way the 2026-07-01 ribbon-flip wiring gap did.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # automation/state/fleet/<this file> -> repo root
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import exit_actuator as ea  # noqa: E402
import exit_manager as em  # noqa: E402
import fleet_executor as fx  # noqa: E402
import build_shared_signal as bss  # noqa: E402

SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}]
# Mirrors test_fix1_selection.py's PARAMS -- the minimal set risk_gate.check_order requires
# to ALLOW (per_trade_risk_cap_pct / daily_loss_kill_switch_pct / min_contracts) so
# finalize()'s ENTER path is actually exercised, not silently denied.
PARAMS = {"position_sizing_tiers": SIZING, "per_trade_risk_cap_pct": 0.5,
          "daily_loss_kill_switch_pct": 0.5, "min_contracts": 3,
          "v15_max_premium_pct_of_account": [{"equity_min": 0, "equity_max": 1e9, "max_pct": 0.9}]}
ARM = {"id": "risky-loose", "gate_override": {}}
STRUCTURE_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
                   "profit_lock_mode": "fixed", "stop_mode": "structure"}


# === static wiring guards (grep-based, precedent: test_g14_fleet_ribbon_exit.py) ===========
def test_fleet_live_passes_closed_5m_close_to_manage_tick():
    src = (FLEET / "fleet_live.py").read_text(encoding="utf-8")
    assert "last_closed_5m_close=" in src, \
        "fleet_live must forward a closed-5m SPY close into manage_tick"
    assert '.get("spot")' in src, \
        "fleet_live's closed-5m close must derive from shared-signal's spot field"


def test_fleet_live_passes_trigger_level_to_register_entry():
    src = (FLEET / "fleet_live.py").read_text(encoding="utf-8")
    assert "trigger_level=getattr(decision, \"trigger_level\", None)" in src.replace("'", '"'), \
        "fleet_live._place_live must thread decision.trigger_level into register_entry"
    assert "structure_stop_enabled=bool(params.get(\"structure_stop_enabled\"" in src.replace("'", '"'), \
        "fleet_live._place_live must read params.structure_stop_enabled"


def test_heartbeat_core_passes_closed_5m_close_both_call_sites():
    src = (Path(__file__).resolve().parents[3] / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert src.count("last_closed_5m_close") >= 3, \
        "heartbeat_core must thread last_closed_5m_close through run_account -> _manage_exits -> manage_tick"


def test_heartbeat_core_passes_trigger_level_to_register_entry():
    src = (Path(__file__).resolve().parents[3] / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert "trigger_level=_trigger_level" in src
    assert "structure_stop_enabled=_structure_enabled" in src
    assert "nearest_active_level" in src, "heartbeat_core must derive trigger_level via exit_manager.nearest_active_level"


# === EntryPlan / ArmDecision threading (fleet_executor.py) =================================
def test_entry_plan_carries_trigger_level_fix2_path():
    sig = {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["t1", "t2"], "quality": "BASE", "est_premium": None, "spot": 600.0,
         "trigger_level": 601.4},
    ]}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level == 601.4


def test_entry_plan_trigger_level_defaults_none_when_absent():
    """A strategies[] entry with NO trigger_level key -> EntryPlan.trigger_level is None
    (never guessed), so from_entry falls back to premium mode for this position."""
    sig = {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["t1", "t2"], "quality": "BASE", "est_premium": None, "spot": 600.0},
    ]}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level is None


def test_entry_plan_carries_trigger_level_side_block_fallback_path():
    """The non-FIX2 fallback (no strategies[] key) also threads trigger_level when the
    side-block itself carries it."""
    sig = {"spot": 600.0,
           "bear": {"passed": True, "triggers_fired": ["t1"],
                    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON", "trigger_level": 601.4},
           "bull": {"passed": False}}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level == 601.4


def test_arm_decision_carries_trigger_level_on_allow():
    plan = fx.EntryPlan("risky-loose", "ENTER", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON",
                        601, 5, "BASE", "clean entry", strategy="ribbon_ride",
                        exit_shape=STRUCTURE_SHAPE, trigger_level=601.4)
    decision = fx.finalize(plan, equity=2000.0, start_of_day_equity=2000.0, premium=1.00,
                           current_position_status=None, day_trades_used_5d=0,
                           kill_switch_tripped=False, prior_stops_today=[], params=PARAMS,
                           account_label="test-arm")
    assert decision.action == "ENTER_BEAR" and decision.trigger_level == 601.4


def test_arm_decision_trigger_level_none_on_hold():
    """A HOLD ArmDecision (positional-8-arg construction, pre-existing call sites) still
    default-constructs with trigger_level=None -- never breaks the older constructors."""
    d = fx.ArmDecision("safe-1", "HOLD", None, None, None, None, None, None, None, "no setup")
    assert d.trigger_level is None


# === LEVEL PROVENANCE (G12, 2026-07-09 night): trigger_level_exact preferred over the
# nearest_active_level heuristic, in BOTH fleet_executor lanes (FIX2 strategies[] path +
# the side-block fallback path) ============================================================
def test_entry_plan_prefers_trigger_level_exact_fix2_path():
    """Non-vacuous (guard ii): trigger_level (heuristic, 601.4) and trigger_level_exact
    (ground truth, 602.75) are DELIBERATELY different -- a regression back to heuristic-
    only REDs here."""
    sig = {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["t1", "t2"], "quality": "BASE", "est_premium": None, "spot": 600.0,
         "trigger_level": 601.4, "trigger_level_exact": 602.75},
    ]}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level == 602.75


def test_entry_plan_prefers_trigger_level_exact_side_block_fallback_path():
    """Same preference on the non-FIX2 fallback path (side-block carries both fields)."""
    sig = {"spot": 600.0,
           "bear": {"passed": True, "triggers_fired": ["t1"],
                    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                    "trigger_level": 601.4, "trigger_level_exact": 602.75},
           "bull": {"passed": False}}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level == 602.75


def test_entry_plan_trigger_level_exact_falls_back_to_heuristic_when_absent():
    """guard iii: trigger_level_exact ABSENT (older shared-signal.json / a TRENDLINE-tier
    entry with no level-tied trigger) -> falls back to trigger_level (heuristic), never
    None just because the exact key is missing while the heuristic value IS present."""
    sig = {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["t1", "t2"], "quality": "BASE", "est_premium": None, "spot": 600.0,
         "trigger_level": 601.4},   # trigger_level_exact absent
    ]}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].trigger_level == 601.4


def test_entry_plan_trigger_level_exact_is_emission_only():
    """guard iv, vary-and-assert: EVERY other EntryPlan field (action/side/setup_name/
    strike/qty/quality/reason/strategy/exit_shape) is byte-identical whether or not
    trigger_level_exact is present on the strategies[] entry -- only .trigger_level itself
    (an emission-only field the gate/sizing logic never reads) differs. Proves this is a
    pure data addition, not a gating/sizing change."""
    base_entry = {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                  "triggers": ["t1", "t2"], "quality": "BASE", "est_premium": None, "spot": 600.0,
                  "trigger_level": 601.4}
    sig_without = {"spot": 600.0, "strategies": [dict(base_entry)]}
    sig_with = {"spot": 600.0, "strategies": [{**base_entry, "trigger_level_exact": 602.75}]}
    p_without = [p for p in fx.plan_all(ARM, sig_without, 2000.0, PARAMS) if p.action == "ENTER"][0]
    p_with = [p for p in fx.plan_all(ARM, sig_with, 2000.0, PARAMS) if p.action == "ENTER"][0]
    for field in ("arm_id", "action", "side", "setup_name", "strike", "qty", "quality",
                  "reason", "strategy", "exit_shape"):
        assert getattr(p_without, field) == getattr(p_with, field), (
            f"{field} must be byte-identical: {getattr(p_without, field)!r} vs "
            f"{getattr(p_with, field)!r}")
    assert p_without.trigger_level == 601.4
    assert p_with.trigger_level == 602.75


# === end-to-end: entry plan -> exit state -> structure exit fires on a fixture =============
def test_register_entry_then_manage_tick_structure_fires_end_to_end(tmp_path, monkeypatch):
    """The FULL threading chain through the ACTUATOR layer (not just the pure core):
    register_entry(trigger_level=..., structure_stop_enabled=True) persists a structure-mode
    ExitState -> a later manage_tick call fed a closed-5m SPY close beyond the level fires
    the structure exit and prunes the position, via a FakeBroker (no network)."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    arm = "test-structure-arm"
    sym = "SPY260709P00745000"
    ea.register_entry(arm, symbol=sym, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, strategy="ribbon_ride",
                      trigger_level=745.0, structure_stop_enabled=True)
    st = ea.load_states(arm)[sym]
    assert st.stop_mode == "structure" and st.trigger_level == 745.0
    assert st.premium_stop_pct == -0.50  # demoted to the catastrophe cap

    class FakeBroker:
        def get_position_qty(self, creds, symbol):
            return 5
        def get_option_quote_hilo(self, creds, symbol):
            return (1.05, 1.00)  # no premium-stop / TP1 reason to exit on price alone

    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    res = ea.manage_tick(arm, {}, live=False, broker=FakeBroker(), now_et=now,
                         last_closed_5m_close=745.6)  # PUT: close > 745.0 -> structure exit
    actions = [a for r in res for a in r.get("actions", [])]
    assert any(a["kind"] == "SELL_ALL" and a["stage"] == "structure_stop" for a in actions)
    assert sym not in ea.load_states(arm)  # fully closed this tick -> pruned


def test_register_entry_then_manage_tick_structure_holds_when_thesis_intact(tmp_path, monkeypatch):
    """Same setup, but the closed bar stays on the thesis side -> position stays open."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    arm = "test-structure-arm-2"
    sym = "SPY260709P00745000"
    ea.register_entry(arm, symbol=sym, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, strategy="ribbon_ride",
                      trigger_level=745.0, structure_stop_enabled=True)

    class FakeBroker:
        def get_position_qty(self, creds, symbol):
            return 5
        def get_option_quote_hilo(self, creds, symbol):
            return (1.05, 1.00)

    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    res = ea.manage_tick(arm, {}, live=False, broker=FakeBroker(), now_et=now,
                         last_closed_5m_close=744.2)  # PUT: still below the level
    actions = [a for r in res for a in r.get("actions", [])]
    assert not actions
    assert sym in ea.load_states(arm)  # still open


def test_register_entry_flag_off_ignores_trigger_level_end_to_end(tmp_path, monkeypatch):
    """structure_stop_enabled=False at registration -> the persisted state is 'premium' mode
    even though a trigger_level + a structure-declaring shape were both supplied; a later
    manage_tick with a closed-5m-close 'beyond the level' does NOT force an exit."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    arm = "test-structure-arm-3"
    sym = "SPY260709P00745000"
    ea.register_entry(arm, symbol=sym, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, strategy="ribbon_ride",
                      trigger_level=745.0, structure_stop_enabled=False)
    st = ea.load_states(arm)[sym]
    assert st.stop_mode == "premium"

    class FakeBroker:
        def get_position_qty(self, creds, symbol):
            return 5
        def get_option_quote_hilo(self, creds, symbol):
            return (1.05, 1.00)

    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    res = ea.manage_tick(arm, {}, live=False, broker=FakeBroker(), now_et=now,
                         last_closed_5m_close=745.6)  # would have fired IF structure mode
    actions = [a for r in res for a in r.get("actions", [])]
    assert not actions
    assert sym in ea.load_states(arm)


# === build_shared_signal.py: nearest-level derivation + full build() emission ================
def _write_levels(tmp_path, levels):
    import json
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": levels}), encoding="utf-8")
    return p


def test_bss_nearest_level_directional_bear(tmp_path, monkeypatch):
    monkeypatch.setattr(bss, "KEY_LEVELS", _write_levels(tmp_path, [
        {"price": 598.0}, {"price": 601.4}, {"price": 605.0},
    ]))
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    prices = bss._active_level_prices(now)
    assert bss._nearest_level(prices, 600.0, "P") == 601.4
    assert bss._nearest_level(prices, 600.0, "C") == 598.0


def test_bss_active_level_prices_drops_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(bss, "KEY_LEVELS", _write_levels(tmp_path, [
        {"price": 601.4, "expires_at": "2020-01-01T16:00:00-04:00"},  # long expired
        {"price": 602.0, "expires_at": "2099-01-01T16:00:00-04:00"},  # far future
        {"price": 603.0},  # no expiry -> kept
    ]))
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    prices = bss._active_level_prices(now)
    assert 601.4 not in prices
    assert 602.0 in prices and 603.0 in prices


def test_bss_active_level_prices_fails_open_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bss, "KEY_LEVELS", tmp_path / "does-not-exist.json")
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert bss._active_level_prices(now) == []


def test_build_emits_trigger_level_for_ribbon_entry(tmp_path, monkeypatch):
    """End-to-end: build() with a controlled key-levels.json + a real core-decisions row
    emits a strategies[] ribbon_ride entry carrying the directionally-correct trigger_level."""
    import json
    from datetime import datetime, timedelta, timezone
    ET = timezone(timedelta(hours=-4))
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    core = tmp_path / "core-decisions.jsonl"
    row = {"ts_et": f"{today}T11:00:00-04:00", "account": "safe", "spy": 600.0,
           "ribbon": "BEAR_STACK", "spread_cents": 12, "vix": 15.0, "htf_15m": "BEAR",
           "verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "bear_score": 9, "bull_score": 2, "triggers": ["level_rejection"], "action": "ENTER_BEAR"}
    core.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")
    monkeypatch.setattr(bss, "KEY_LEVELS", _write_levels(tmp_path, [
        {"price": 600.9},   # nearest above spot=600.0 -> the bear's trigger_level
        {"price": 590.0},   # wrong side, must be ignored for a PUT
    ]))
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False)
    ribbon = [s for s in sig["strategies"] if s["name"] == "ribbon_ride"]
    assert len(ribbon) == 1
    assert ribbon[0]["trigger_level"] == 600.9


# === LEVEL PROVENANCE (G12, 2026-07-09 night): trigger_level_exact passthrough,
# core-decisions.jsonl -> _map_core_row -> build()'s side blocks + strategies[] entries ====
def test_map_core_row_passes_through_trigger_level_exact():
    row = {"ts_et": "2026-07-09T11:00:00-04:00", "account": "safe", "spy": 600.0,
           "ribbon": "BEAR_STACK", "spread_cents": 12, "vix": 15.0, "htf_15m": "BEAR",
           "verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "bear_score": 9, "bull_score": 2, "triggers": ["level_rejection"],
           "action": "ENTER_BEAR", "trigger_level_exact": 622.5}
    mapped = bss._map_core_row(row)
    assert mapped["trigger_level_exact"] == 622.5


def test_map_core_row_trigger_level_exact_none_when_absent():
    """guard iii: an OLDER core-decisions.jsonl row (written before this build, no
    trigger_level_exact key at all) maps to None, never a crash, never a guess."""
    row = {"ts_et": "2026-07-09T11:00:00-04:00", "account": "safe", "spy": 600.0,
           "ribbon": "BEAR_STACK", "spread_cents": 12, "vix": 15.0, "htf_15m": "BEAR",
           "verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "bear_score": 9, "bull_score": 2, "triggers": ["level_rejection"], "action": "ENTER_BEAR"}
    mapped = bss._map_core_row(row)
    assert mapped["trigger_level_exact"] is None


def _core_row(tmp_path, *, trigger_level_exact=None, today="2026-06-26"):
    import json
    core = tmp_path / "core-decisions.jsonl"
    row = {"ts_et": f"{today}T11:00:00-04:00", "account": "safe", "spy": 600.0,
           "ribbon": "BEAR_STACK", "spread_cents": 12, "vix": 15.0, "htf_15m": "BEAR",
           "verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "bear_score": 9, "bull_score": 2, "triggers": ["level_rejection"], "action": "ENTER_BEAR"}
    if trigger_level_exact is not None:
        row["trigger_level_exact"] = trigger_level_exact
    core.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return core


def test_build_emits_trigger_level_exact_on_side_block_and_strategies_entry(tmp_path, monkeypatch):
    """End-to-end: build()'s WINNING side (bear, since verdict=ENTER_BEAR) carries
    trigger_level_exact on BOTH the top-level bear block and the strategies[] ribbon_ride
    entry; the LOSING side (bull) stays None (mirrors triggers_fired/setup_name's existing
    win-gated convention)."""
    from datetime import datetime, timedelta, timezone
    ET = timezone(timedelta(hours=-4))
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    monkeypatch.setattr(bss, "CORE_DECISIONS", _core_row(tmp_path, trigger_level_exact=622.5))
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")
    monkeypatch.setattr(bss, "KEY_LEVELS", _write_levels(tmp_path, [{"price": 600.9}]))
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False)
    assert sig["bear"]["trigger_level_exact"] == 622.5
    assert sig["bull"]["trigger_level_exact"] is None
    ribbon = [s for s in sig["strategies"] if s["name"] == "ribbon_ride"]
    assert len(ribbon) == 1
    assert ribbon[0]["trigger_level_exact"] == 622.5
    assert ribbon[0]["trigger_level"] == 600.9, "the heuristic field stays UNCHANGED alongside it"


def test_build_trigger_level_exact_is_emission_only(tmp_path, monkeypatch):
    """guard iv, vary-and-assert: production_action + bear/bull passed/score/triggers_fired/
    setup_name/confluence are byte-identical whether or not the core row carries
    trigger_level_exact -- only the new field differs."""
    from datetime import datetime, timedelta, timezone
    ET = timezone(timedelta(hours=-4))
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")
    monkeypatch.setattr(bss, "KEY_LEVELS", _write_levels(tmp_path, [{"price": 600.9}]))

    monkeypatch.setattr(bss, "CORE_DECISIONS", _core_row(tmp_path, trigger_level_exact=None))
    sig_without = bss.build(now=now, emit_strategies=True, run_vwap=False)

    monkeypatch.setattr(bss, "CORE_DECISIONS", _core_row(tmp_path, trigger_level_exact=622.5))
    sig_with = bss.build(now=now, emit_strategies=True, run_vwap=False)

    assert sig_without["production_action"] == sig_with["production_action"]
    for side in ("bear", "bull"):
        for key in ("passed", "score", "triggers_fired", "setup_name", "confluence"):
            assert sig_without[side][key] == sig_with[side][key], (
                f"{side}.{key} must be byte-identical")
    assert sig_without["bear"]["trigger_level_exact"] is None
    assert sig_with["bear"]["trigger_level_exact"] == 622.5


if __name__ == "__main__":
    import tempfile

    class _MP:
        def __init__(self):
            self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        mp = _MP()
        argn = t.__code__.co_varnames[: t.__code__.co_argcount]
        try:
            with tempfile.TemporaryDirectory() as td:
                kw = {}
                if "tmp_path" in argn:
                    kw["tmp_path"] = Path(td)
                if "monkeypatch" in argn:
                    kw["monkeypatch"] = mp
                t(**kw)
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
