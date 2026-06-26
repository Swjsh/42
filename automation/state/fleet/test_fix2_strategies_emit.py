"""FIX2 tests — the producer emits signal['strategies'] (every registered strategy
evaluated independently per tick) and plan_all CONSUMES that set.

Two layers:
  A. plan_all consumes a strategies[] signal -> one plan per (strategy entry), each with
     its own exit shape; VWAP and ribbon BOTH fire as independent plans (the bug fix:
     before, the producer carried only the single ribbon verdict so VWAP could never fire).
  B. build_shared_signal.build(run_vwap=False) emits a strategies[] list with the ribbon_ride
     entry re-keyed from the core verdict row (offline — no network VWAP pass).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import build_shared_signal as bss
import fleet_executor as fx

ET = timezone(timedelta(hours=-4))
SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}]
PARAMS = {"position_sizing_tiers": SIZING}
ARM = {"id": "risky-loose", "gate_override": {}}


def _entry(name, side, setup, triggers=("t1", "t2"), quality="BASE", spot=600.0):
    return {"name": name, "side": side, "setup": setup, "triggers": list(triggers),
            "quality": quality, "est_premium": None, "spot": spot}


# === A. plan_all consumes strategies[] =======================================
def test_plan_all_consumes_strategies_set_both_fire():
    """A strategies[] signal with ribbon AND vwap -> BOTH produce an independent ENTER plan."""
    sig = {"spot": 600.0, "strategies": [
        _entry("ribbon_ride", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON"),
        _entry("vwap_continuation", "C", "VWAP_CONTINUATION",
               triggers=["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_BREAKOUT"]),
    ]}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enters = {(p.strategy, p.side) for p in plans if p.action == "ENTER"}
    assert ("ribbon_ride", "P") in enters
    assert ("vwap_continuation", "C") in enters


def test_strategies_path_attaches_correct_exit_shapes():
    """Each consumed strategy carries ITS OWN exit shape from the REGISTRY (not the other's)."""
    sig = {"spot": 600.0, "strategies": [
        _entry("ribbon_ride", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON"),
        _entry("vwap_continuation", "C", "VWAP_CONTINUATION", triggers=["VWAP_TREND_ESTABLISHED"]),
    ]}
    plans = {p.strategy: p for p in fx.plan_all(ARM, sig, 2000.0, PARAMS) if p.action == "ENTER"}
    assert plans["ribbon_ride"].exit_shape["premium_stop_pct"] == -0.20
    assert plans["ribbon_ride"].exit_shape["tp1_premium_pct"] == 1.5
    assert plans["vwap_continuation"].exit_shape["premium_stop_pct"] == -0.08
    assert plans["vwap_continuation"].exit_shape["tp1_premium_pct"] == 0.3


def test_strategies_path_applies_arm_gate():
    """The arm's selectivity gate still applies on the strategies[] path (tight -> HOLD)."""
    sig = {"spot": 600.0, "strategies": [
        _entry("ribbon_ride", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON", triggers=["t1"])]}
    tight = {"id": "tight", "gate_override": {"min_triggers": 2}}
    plans = fx.plan_all(tight, sig, 2000.0, PARAMS)
    assert plans and all(p.action == "HOLD" for p in plans)
    assert any("triggers <" in p.reason for p in plans)


def test_strategies_path_no_direction_lock():
    """A CALL strategy is never dropped for a direction-lock reason on the FIX2 path."""
    sig = {"spot": 600.0, "strategies": [
        _entry("ribbon_ride", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON")]}
    plans = fx.plan_all({"id": "risky-loose", "gate_override": {}}, sig, 2000.0, PARAMS)
    assert any(p.action == "ENTER" and p.side == "C" for p in plans)


def test_empty_strategies_list_yields_no_plans():
    """strategies=[] (present but empty) -> no plans (the FIX2 path is taken, not the fallback)."""
    sig = {"spot": 600.0, "strategies": []}
    assert fx.plan_all(ARM, sig, 2000.0, PARAMS) == []


def test_absent_strategies_falls_back_to_side_blocks():
    """No strategies key -> the v1 side-block path still works (backward-compat)."""
    sig = {"spot": 600.0,
           "bear": {"passed": True, "triggers_fired": ["t1"], "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
           "bull": {"passed": False}}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    assert any(p.action == "ENTER" and p.strategy == "ribbon_ride" and p.side == "P" for p in plans)


def test_unknown_strategy_name_skipped():
    sig = {"spot": 600.0, "strategies": [_entry("not_a_real_strategy", "P", "X")]}
    assert fx.plan_all(ARM, sig, 2000.0, PARAMS) == []


# === B. build_shared_signal emits strategies[] (offline, run_vwap=False) ======
def _seed_core(tmp_path, monkeypatch, *, account, verdict, setup, side, triggers, today):
    """Write a one-row core-decisions.jsonl and point the producer at it + a tmp OUT."""
    core = tmp_path / "core-decisions.jsonl"
    row = {"ts_et": f"{today}T11:00:00-04:00", "account": account, "spy": 600.0,
           "ribbon": "BEAR_STACK", "spread_cents": 12, "vix": 15.0, "htf_15m": "BEAR",
           "verdict": verdict, "side": side, "setup": setup,
           "bear_score": 9, "bull_score": 2, "triggers": triggers, "action": verdict}
    core.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")  # force ledger path


def test_build_emits_ribbon_strategy_entry(tmp_path, monkeypatch):
    """build(run_vwap=False) on an ENTER_BEAR core row emits a strategies[] with the
    ribbon_ride entry re-keyed from the verdict (offline; no network VWAP pass)."""
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="safe", verdict="ENTER_BEAR",
               setup="BEARISH_REJECTION_RIDE_THE_RIBBON", side="P",
               triggers=["level_rejection", "sequence_rejection"], today=today)
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False)
    strats = sig.get("strategies")
    assert isinstance(strats, list)
    ribbon = [s for s in strats if s["name"] == "ribbon_ride"]
    assert len(ribbon) == 1
    r = ribbon[0]
    assert r["side"] == "P"
    assert r["setup"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"
    assert "sequence_rejection" in r["triggers"]
    assert r["quality"] == "ELITE"  # sequence_* trigger -> ELITE


def test_build_strategies_feed_plan_all_end_to_end(tmp_path, monkeypatch):
    """The producer's strategies[] is directly consumable by plan_all -> an ENTER plan
    with the ribbon exit shape (the FIX2 producer<->consumer contract end to end)."""
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="safe", verdict="ENTER_BULL",
               setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
               triggers=["level_reclaim"], today=today)
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False)
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS)
    enter = [p for p in plans if p.action == "ENTER" and p.strategy == "ribbon_ride"]
    assert len(enter) == 1 and enter[0].side == "C"
    assert enter[0].exit_shape["premium_stop_pct"] == -0.20


def test_build_no_strategies_when_disabled(tmp_path, monkeypatch):
    """emit_strategies=False -> no strategies key (byte-identical-to-pre-FIX2 revert)."""
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="safe", verdict="ENTER_BEAR",
               setup="BEARISH_REJECTION_RIDE_THE_RIBBON", side="P",
               triggers=["level_rejection"], today=today)
    sig = bss.build(now=now, emit_strategies=False, run_vwap=False)
    assert "strategies" not in sig


def test_build_hold_row_emits_empty_strategies(tmp_path, monkeypatch):
    """A HOLD core row (no side passed) -> strategies[] present but empty (no ribbon entry)."""
    now = datetime(2026, 6, 26, 11, 5, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="safe", verdict="HOLD",
               setup=None, side=None, triggers=[], today=today)
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False)
    assert sig.get("strategies") == []


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

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
