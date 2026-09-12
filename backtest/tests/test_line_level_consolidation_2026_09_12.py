"""LINE & LEVEL CONSOLIDATION guards (J directive 2026-09-12: "make sure engine only trades what it
should be looking at line and level wise").

Pins three things:
  C1  the TRENDLINE ANCHOR SWITCH -- with trendline_anchor_enabled=False a trendline-only bear
      bar has no trigger and is not tradable; level-anchored bars are untouched; the switch flows
      from gate_params through engine_cli into filters (the live path); both live params files
      carry it False and no extra setup is exec-armed.
  C2  CAP AUTHORITY -- when key-levels.json carries the producer's ``level_cap`` block, both the
      core reader (heartbeat_core._read_level_records) and the fleet reader
      (build_shared_signal._active_level_prices) return ONLY levels the cap stamped with
      ``touch_rank``; a legacy file (no level_cap) is read unchanged.
RED-proofed 2026-09-12: every test here failed before the consolidation edits landed.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import filters as filters_mod  # noqa: E402
from lib.filters import BarContext, evaluate_bearish_setup  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402
from lib.engine.engine_cli import decide_payload  # noqa: E402

hc = importlib.import_module("heartbeat_core")
bss = importlib.import_module("build_shared_signal")

PARAMS = ROOT / "automation" / "state" / "params.json"
PARAMS_AGG = ROOT / "automation" / "state" / "aggressive" / "params.json"


# ── fixtures (same shape as test_g2_trendline_bypass_scope.py) ─────────────────────────────

def _mixed_ribbon_ctx(when: dt.datetime = dt.datetime(2026, 9, 14, 11, 0)) -> BarContext:
    hist = [{"open": 700.0, "high": 700.3, "low": 699.7, "close": 700.0, "volume": 900_000}] * 30
    df = pd.DataFrame(hist)
    idx = len(df) - 1
    rs = RibbonState(fast=700.05, pivot=700.10, slow=700.00, stack="MIXED", spread_cents=50.0)
    return BarContext(
        bar_idx=idx, timestamp_et=when,
        bar=df.iloc[idx], prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6,
        vix_now=14.0, vix_prior=14.5,
        vol_baseline_20=900_000, range_baseline_20=0.6,
        levels_active=[705.0], multi_day_levels=[705.0], htf_15m_stack="BEAR",
    )


@pytest.fixture(autouse=True)
def _force_other_detectors(monkeypatch):
    monkeypatch.setattr(filters_mod, "volume_divergence_failed", lambda *a, **k: False)
    monkeypatch.setattr(filters_mod, "breakdown_bar_bearish", lambda *a, **k: True)
    monkeypatch.setattr(filters_mod, "detect_confluence", lambda *a, **k: None)
    monkeypatch.setattr(filters_mod, "detect_sequence_rejection", lambda *a, **k: False)
    monkeypatch.setattr(filters_mod, "detect_wick_rejection_bearish", lambda *a, **k: None)
    monkeypatch.setattr(filters_mod, "detect_candlestick_pattern_bearish", lambda *a, **k: None)
    yield


def _force(monkeypatch, *, level: bool, trendline: bool):
    monkeypatch.setattr(filters_mod, "detect_level_rejection",
                        (lambda bar, levels: 705.0) if level else (lambda bar, levels: None))
    monkeypatch.setattr(filters_mod, "detect_trendline_rejection_bearish",
                        (lambda *a, **k: 699.5) if trendline else (lambda *a, **k: None))


def _payload_for(ctx: BarContext, gate_params: Optional[dict] = None) -> dict:
    def _bars(df: pd.DataFrame) -> list:
        return [{"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
                 "close": float(r["close"]), "volume": float(r["volume"])} for _, r in df.iterrows()]

    def _rs(rs: Optional[RibbonState]) -> Optional[dict]:
        return None if rs is None else {"fast": rs.fast, "pivot": rs.pivot, "slow": rs.slow,
                                        "spread_cents": rs.spread_cents, "stack": rs.stack}

    bar_ctx = {
        "bar_idx": ctx.bar_idx, "timestamp_et": ctx.timestamp_et.isoformat(),
        "bar": {"open": float(ctx.bar["open"]), "high": float(ctx.bar["high"]),
                "low": float(ctx.bar["low"]), "close": float(ctx.bar["close"]),
                "volume": float(ctx.bar["volume"])},
        "prior_bars": _bars(ctx.prior_bars), "ribbon_now": _rs(ctx.ribbon_now),
        "ribbon_history": [_rs(rs) for rs in ctx.ribbon_history],
        "vix_now": ctx.vix_now, "vix_prior": ctx.vix_prior,
        "vol_baseline_20": ctx.vol_baseline_20, "range_baseline_20": ctx.range_baseline_20,
        "levels_active": list(ctx.levels_active), "multi_day_levels": list(ctx.multi_day_levels),
        "htf_15m_stack": ctx.htf_15m_stack,
        "fhh_level": ctx.fhh_level, "vix_5d_ma": ctx.vix_5d_ma, "vix_20d_ma": ctx.vix_20d_ma,
    }
    return {"bar_ctx": bar_ctx, "gate_params": gate_params or {}, "score_params": {}}


# ── C1: trendline anchor switch ──────────────────────────────────────────────────────────────

def test_trendline_only_bar_has_no_trigger_and_is_not_tradable_when_switch_off(monkeypatch):
    _force(monkeypatch, level=False, trendline=True)
    ctx = _mixed_ribbon_ctx()
    on = evaluate_bearish_setup(ctx, min_triggers=1)                                  # legacy default
    off = evaluate_bearish_setup(ctx, min_triggers=1, trendline_anchor_enabled=False)
    assert "trendline_rejection" in on.triggers_fired
    assert "trendline_rejection" not in off.triggers_fired
    assert off.triggers_fired == [] and off.passed is False


def test_level_anchored_bar_is_untouched_by_the_switch(monkeypatch):
    _force(monkeypatch, level=True, trendline=False)
    ctx = _mixed_ribbon_ctx()
    on = evaluate_bearish_setup(ctx, min_triggers=1)
    off = evaluate_bearish_setup(ctx, min_triggers=1, trendline_anchor_enabled=False)
    assert "level_rejection" in off.triggers_fired
    assert on.triggers_fired == off.triggers_fired and on.passed == off.passed


def test_switch_flows_from_gate_params_through_engine_cli(monkeypatch):
    """The LIVE path: params.json -> GATE_KEYS -> gate_params -> engine_cli flip point ->
    filters. Absent key = legacy (trendline trigger seen); exactly False = never seen."""
    _force(monkeypatch, level=False, trendline=True)
    ctx = _mixed_ribbon_ctx()
    legacy = decide_payload(_payload_for(ctx, gate_params={}))
    off = decide_payload(_payload_for(ctx, gate_params={"trendline_anchor_enabled": False}))
    assert "trendline_rejection" in (legacy.get("bear_triggers_raw") or [])
    assert "trendline_rejection" not in (off.get("bear_triggers_raw") or [])
    assert "trendline_anchor_enabled" in hc.GATE_KEYS


def test_live_params_switch_is_off_and_no_extra_setup_is_exec_armed():
    p = json.loads(PARAMS.read_text(encoding="utf-8"))
    a = json.loads(PARAMS_AGG.read_text(encoding="utf-8"))
    assert p.get("trendline_anchor_enabled") is False
    assert a.get("trendline_anchor_enabled") is False
    armed = p.get("extra_setup_exec_armed") or {}
    assert armed and all(v is False for v in armed.values()), armed


def test_switch_is_date_gated_so_history_replays_as_traded(monkeypatch):
    """The switch took effect live on 2026-09-14. A bar BEFORE that date keeps the anchor ON even
    with the live params flag False, so replay / parity instruments fed today's params reproduce
    what the engine actually did (2026-09-12 00:36 ET, flag applied retroactively: the dojo
    reproduced NONE of 11 real 07-17 ENTER_BEAR bars and the fleet replay missed 6 of 16 risky-3
    entries -- exactly the trendline-only share). On/after the date the flag rules."""
    _force(monkeypatch, level=False, trendline=True)
    off = {"trendline_anchor_enabled": False}
    before = decide_payload(_payload_for(_mixed_ribbon_ctx(dt.datetime(2026, 9, 11, 11, 0)), gate_params=off))
    after = decide_payload(_payload_for(_mixed_ribbon_ctx(dt.datetime(2026, 9, 14, 9, 35)), gate_params=off))
    assert "trendline_rejection" in (before.get("bear_triggers_raw") or [])
    assert "trendline_rejection" not in (after.get("bear_triggers_raw") or [])
    assert filters_mod.TRENDLINE_ANCHOR_OFF_FROM == dt.date(2026, 9, 14)


# ── C2: cap authority on the read side ──────────────────────────────────────────────────────

def _write_levels(path: Path, *, capped: bool, expires_day: str) -> None:
    doc = {"schema_version": 1, "levels": [
        {"price": 750.0, "role": "support", "label": "STAMPED", "tier": "Active",
         "expires_at": f"{expires_day}T16:00:00-04:00", "touches_uniform": 4, "touch_rank": 1},
        {"price": 751.0, "role": "resistance", "label": "UNSTAMPED_INJECTED", "tier": "Active",
         "expires_at": f"{expires_day}T16:00:00-04:00"},
    ]}
    if capped:
        doc["level_cap"] = {"per_side": 3, "kept": 1, "pruned": 0}
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_core_reader_returns_only_cap_stamped_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "STATE", tmp_path)
    today = hc._et_now().strftime("%Y-%m-%d")
    _write_levels(tmp_path / "key-levels.json", capped=True, expires_day=today)
    assert [lv["price"] for lv in hc._read_level_records(750.5)] == [750.0]
    assert hc._read_levels(750.5)[0] == [750.0]
    _write_levels(tmp_path / "key-levels.json", capped=False, expires_day=today)   # legacy file
    assert sorted(lv["price"] for lv in hc._read_level_records(750.5)) == [750.0, 751.0]


def test_fleet_reader_returns_only_cap_stamped_levels(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    monkeypatch.setattr(bss, "KEY_LEVELS", kl)
    now = dt.datetime.now()
    _write_levels(kl, capped=True, expires_day=now.strftime("%Y-%m-%d"))
    assert bss._active_level_prices(now) == [750.0]
    _write_levels(kl, capped=False, expires_day=now.strftime("%Y-%m-%d"))
    assert sorted(bss._active_level_prices(now)) == [750.0, 751.0]


# ── C1b: the orchestrator path (replays, e2e, parity, graduated guards) ────────────────────────

def test_orchestrator_only_passes_kwargs_each_evaluator_accepts():
    """REGRESSION PIN (2026-09-12 00:36 ET): the consolidation apply added the anchor switch to
    the orchestrator's shared kwarg block, which fed BOTH evaluators -- evaluate_bullish_setup has
    no such parameter, so every orchestrator-path replay raised TypeError while the live path
    (engine_cli builds bear_kwargs separately) stayed green. Walks orchestrator.py's AST: each
    direct `evaluate_*_setup(...)` call and each `bear_kwargs=dict(...)` / `bull_kwargs=dict(...)`
    block may only name keywords the target evaluator's signature declares."""
    import ast
    import inspect
    from lib import orchestrator as orch
    from lib.filters import evaluate_bullish_setup as bull_fn
    sig = {"bear": set(inspect.signature(evaluate_bearish_setup).parameters),
           "bull": set(inspect.signature(bull_fn).parameters)}
    tree = ast.parse(Path(orch.__file__).read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        targets = []
        if fname in ("evaluate_bearish_setup", "evaluate_bullish_setup"):
            targets.append(("bear" if "bearish" in fname else "bull", node))
        for kw in node.keywords:
            if kw.arg in ("bear_kwargs", "bull_kwargs") and isinstance(kw.value, ast.Call)                     and getattr(kw.value.func, "id", None) == "dict":
                targets.append((kw.arg[:4], kw.value))
        for side, call in targets:
            names = {kw.arg for kw in call.keywords if kw.arg is not None}
            unknown = names - sig[side]
            assert not unknown, f"orchestrator.py:{call.lineno} passes {sorted(unknown)} to the {side} evaluator"
            checked += 1
    assert checked >= 4, checked

