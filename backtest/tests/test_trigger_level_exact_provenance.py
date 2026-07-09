"""Guard: LEVEL PROVENANCE (G12, 2026-07-09 night) -- trigger_level_exact ground truth.

THE GAP THIS CLOSES: SS-B structure stops (commit 933bd65) derive each position's
trigger_level via exit_manager.nearest_active_level() -- a PROXIMITY GUESS (nearest
same-side key-level within $2 of spot). But the entry SIGNAL already knows its level:
filters.detect_level_rejection / detect_level_reclaim (backtest/lib/filters.py) pick the
EXACT level a level_rejection/level_reclaim/sequence_* trigger fired against, and that
value already flows verbatim through score_bar -> engine_cli._derive_routing ->
decide_payload's "rejection_level" (pre-existing field, UNCHANGED by this build). This
file proves TWO things:

  1. SOURCE OF TRUTH (guard i): decide_payload's "rejection_level" equals the actual level
     filters.py matched on a fixture with a DISTRACTOR level present -- non-vacuous, a wrong
     side/level/None would fail the assertion.
  2. CORE-LANE WIRING (guards i/ii/iii/iv): heartbeat_core.py stamps that value into (a) the
     core-decisions.jsonl row as "trigger_level_exact" and (d) prefers it over the
     exit_manager.nearest_active_level heuristic when registering the position's exit state
     -- falling back to the heuristic only when the exact value is absent, never guessing
     when both are absent, and never changing the actual order-placement outcome (vary-and-
     assert: symbol/side/strike/qty/premium/tp/stop/status are byte-identical regardless of
     whether rejection_level is present -- this is an EMISSION-ONLY addition).

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_trigger_level_exact_provenance.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.engine_cli import decide_payload  # noqa: E402

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


# =============================================================================
# PART 1 -- SOURCE OF TRUTH: decide_payload's "rejection_level" == the level the
# trigger actually fired against (backtest/lib/filters.py, UNTOUCHED by this build).
# =============================================================================
def _bar_ctx_json(*, side: str, levels_active: list, time_str: str = "10:00") -> dict:
    """Minimal valid bar_ctx JSON that clears all 10/11 filters for one clean side (mirrors
    test_engine_cli_parity.py's _bear_ctx/_bull_ctx "clean_no_gates" fixtures)."""
    if side == "P":
        ribbon = {"fast": 539.0, "pivot": 540.0, "slow": 541.0, "spread_cents": 50.0, "stack": "BEAR"}
        bar = {"open": 540.5, "high": 541.5, "low": 539.5, "close": 540.3, "volume": 900_000.0}
        vix_now, vix_prior, htf = 17.5, 17.3, "BEAR"
    else:
        ribbon = {"fast": 541.0, "pivot": 540.0, "slow": 539.0, "spread_cents": 50.0, "stack": "BULL"}
        bar = {"open": 540.0, "high": 541.5, "low": 539.8, "close": 541.2, "volume": 750_000.0}
        vix_now, vix_prior, htf = 17.1, 17.3, "BULL"
    prior_bars = [{"open": 540.0, "high": 540.4, "low": 539.6, "close": 540.0, "volume": 800_000.0}
                  for _ in range(30)]
    return {
        "bar_idx": 4, "timestamp_et": f"2026-05-20T{time_str}:00-04:00",
        "bar": bar, "prior_bars": prior_bars,
        "ribbon_now": ribbon, "ribbon_history": [ribbon],
        "vix_now": vix_now, "vix_prior": vix_prior,
        "vol_baseline_20": 1_000_000.0, "range_baseline_20": 1.0,
        "levels_active": levels_active, "multi_day_levels": [],
        "htf_15m_stack": htf, "level_states": {},
    }


def test_decide_payload_rejection_level_matches_fired_level_bear():
    """Non-vacuous (guard i): 545.0 is a DISTRACTOR the bar never touches (high=541.5 never
    reaches it); only 540.8 is actually rejected. A wrong/None level here would RED."""
    verdict = decide_payload({"bar_ctx": _bar_ctx_json(side="P", levels_active=[545.0, 540.8])})
    assert verdict["verdict"] == "ENTER_BEAR", verdict
    assert "level_rejection" in verdict["triggers_fired"]
    assert verdict["rejection_level"] == 540.8, (
        f"expected the ACTUAL rejected level 540.8, got {verdict['rejection_level']!r} "
        "-- 545.0 is a distractor the bar never reached")


def test_decide_payload_rejection_level_matches_fired_level_bull():
    """Bull mirror: 535.0 is a distractor (bar.low=539.8 never dips to it); only 540.5 is
    actually reclaimed."""
    verdict = decide_payload({"bar_ctx": _bar_ctx_json(side="C", levels_active=[535.0, 540.5])})
    assert verdict["verdict"] == "ENTER_BULL", verdict
    assert "level_reclaim" in verdict["triggers_fired"]
    assert verdict["rejection_level"] == 540.5, (
        f"expected the ACTUAL reclaimed level 540.5, got {verdict['rejection_level']!r} "
        "-- 535.0 is a distractor the bar never reached")


def test_decide_payload_rejection_level_none_when_no_level_tied_trigger_fires():
    """No level anywhere near the bar -> no level-tied trigger -> HOLD, rejection_level None.
    Establishes the None contract every downstream consumer (heartbeat_core, build_shared_
    signal, fleet_executor) must fall back on."""
    verdict = decide_payload({"bar_ctx": _bar_ctx_json(side="P", levels_active=[200.0])})
    assert verdict["verdict"] == "HOLD", verdict
    assert verdict["rejection_level"] is None


# =============================================================================
# PART 2 -- CORE LANE: setup/scripts/heartbeat_core.py
# =============================================================================
# (a) run_account's core-decisions.jsonl row stamps trigger_level_exact from the verdict.
def _wire_run_account(hc, monkeypatch, now, verdict, *, levels_active=None):
    payload = {"bar_ctx": {
        "timestamp_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "bar": {"close": 620.0},
        "ribbon_now": {"stack": "BEAR_STACK", "spread_cents": 45.0},
        "vix_now": 17.2, "vix_prior": 17.3, "htf_15m_stack": "BEAR",
        "levels_active": levels_active or [],
    }}
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
    monkeypatch.setitem(sys.modules, "setup_dispatch",
                        types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
    return logged


def test_run_account_stamps_trigger_level_exact_from_verdict(hc, monkeypatch):
    verdict = {"verdict": "ENTER_BEAR", "side": "P", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
              "bear_score": 9, "bull_score": 2, "triggers_fired": ["level_rejection"],
              "reason": "test", "rejection_level": 622.5}
    logged = _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 9, 11, 0), verdict)
    rec = hc.run_account("safe")
    assert rec["trigger_level_exact"] == 622.5
    assert logged and logged[-1]["trigger_level_exact"] == 622.5, "the LOGGED row must carry it too"


def test_run_account_trigger_level_exact_none_when_verdict_lacks_it(hc, monkeypatch):
    """None-safe legacy compatibility (guard iii): a verdict shaped like a HOLD/older
    engine_cli output (no "rejection_level" key at all) -> trigger_level_exact is None,
    never a crash, never a guessed value."""
    verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
              "bear_score": 3, "bull_score": 1, "triggers_fired": [], "reason": "no setup"}
    _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 9, 11, 0), verdict)
    rec = hc.run_account("safe")
    assert rec["trigger_level_exact"] is None


# (d) _execute prefers the exact level over the nearest_active_level heuristic.
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


def _wire_execute(hc, monkeypatch, tmp_path, register_entry_fn, *, mid=1.00,
                  equity="2000.0", now=dt.datetime(2026, 7, 9, 11, 0)):
    """Mirrors test_min_entry_premium_floor.py's harness: fake broker REST + urllib account
    fetch, real risk_gate/strike_selection/params. register_entry_fn is injected so the test
    can capture what trigger_level actually got threaded through."""
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})
        return {"id": "ord-1", "status": "accepted"}

    monkeypatch.setattr(fb, "_request", fake_request)
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: mid)
    monkeypatch.setattr(fb, "marketable_limit_price",
                        lambda c, s, side="buy", buffer=0.03: round(mid + buffer, 2))
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        types.SimpleNamespace(register_entry=register_entry_fn))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


_VERDICT = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "triggers_fired": ["level_rejection"]}


def _payload(levels_active):
    return {"bar_ctx": {"timestamp_et": "2026-07-09 10:55:00", "bar": {"close": 620.0},
                        "levels_active": levels_active}}


def test_execute_prefers_trigger_level_exact_over_heuristic(hc, monkeypatch, tmp_path):
    """Non-vacuous (guard ii, core lane): levels_active=[621.0] makes the heuristic pick
    621.0 (nearest P-side level >= spot=620.0); the exact value 622.5 is DELIBERATELY
    different, so a regression back to heuristic-only REDs here."""
    captured = {}
    _wire_execute(hc, monkeypatch, tmp_path, lambda *a, **kw: captured.update(kw), mid=1.00)
    verdict = {**_VERDICT, "rejection_level": 622.5}
    plan = hc._execute("safe", verdict, _payload([621.0]), SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert captured.get("trigger_level") == 622.5, (
        f"expected the EXACT rejection_level 622.5, got {captured.get('trigger_level')} "
        "(the nearest_active_level heuristic would have picked 621.0)")


def test_execute_falls_back_to_heuristic_when_exact_absent(hc, monkeypatch, tmp_path):
    """guard iii: a verdict with no "rejection_level" key (legacy shape / extra-setup
    synthetic verdict) falls back to the SAME heuristic as before this build."""
    captured = {}
    _wire_execute(hc, monkeypatch, tmp_path, lambda *a, **kw: captured.update(kw), mid=1.00)
    plan = hc._execute("safe", dict(_VERDICT), _payload([621.0]), SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert captured.get("trigger_level") == 621.0


def test_execute_trigger_level_none_when_both_sources_absent(hc, monkeypatch, tmp_path):
    """guard iii: no exact value AND no levels_active -> None, never guessed."""
    captured = {}
    _wire_execute(hc, monkeypatch, tmp_path, lambda *a, **kw: captured.update(kw), mid=1.00)
    plan = hc._execute("safe", dict(_VERDICT), _payload([]), SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert captured.get("trigger_level") is None


def test_execute_trigger_level_exact_is_emission_only(hc, monkeypatch, tmp_path):
    """guard iv, vary-and-assert: the ACTUAL order placement (status/symbol/side/strike/
    qty/premium/tp/stop) is byte-identical whether or not the verdict carries
    rejection_level -- only the register_entry trigger_level kwarg differs. Proves this is
    a pure data-emission addition with zero effect on gate/scoring/sizing/placement."""
    captured_without: dict = {}
    _wire_execute(hc, monkeypatch, tmp_path, lambda *a, **kw: captured_without.update(kw), mid=1.00)
    plan_without = hc._execute("safe", dict(_VERDICT), _payload([621.0]), SAFE_PARAMS, dry=False)

    captured_with: dict = {}
    _wire_execute(hc, monkeypatch, tmp_path, lambda *a, **kw: captured_with.update(kw), mid=1.00)
    verdict_with = {**_VERDICT, "rejection_level": 622.5}
    plan_with = hc._execute("safe", verdict_with, _payload([621.0]), SAFE_PARAMS, dry=False)

    for key in ("status", "symbol", "side", "strike", "qty", "premium", "tp", "stop", "equity", "setup"):
        assert plan_without[key] == plan_with[key], (
            f"{key} must be byte-identical: {plan_without[key]!r} vs {plan_with[key]!r}")
    assert captured_without.get("trigger_level") == 621.0   # heuristic (no exact)
    assert captured_with.get("trigger_level") == 622.5      # exact preferred


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
