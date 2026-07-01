"""MONEY-PATH guards for the 2026-07-01 four-fix batch (make tomorrow's order fillable).

Pins, RED-on-regression:

  FIX1 — ENTRY-TIME CEILING: params entry_no_trade_after_et ("15:00") was never forwarded
    to engine_cli (only no_trade_before/no_trade_window), so on 2026-06-30 the engine's only
    10 ENTER verdicts fired 15:51-15:55 ET and Alpaca rejected every order ('expires soon').
    Now: run_account logs SKIP_LATE_ENTRY before the free-model eval; _execute has the same
    check as belt-and-suspenders (covers the extra-setup route); fleet_live._place_live too.

  FIX2 — SIMPLE-FIRST PLACEMENT: Alpaca NEVER accepts bracket/oto for options (42210000);
    the old ladder ate 2 guaranteed 422s (bracket_err + oto_err) before every simple attempt.
    Now: ONE plain marketable-limit POST (no order_class), C2 preserved (only placed when
    CORE_MANAGES_EXITS; exit_manager owns TP/stop).

  FIX3 — GATE_KEYS omission: block_elite_bull_vix_low/high were missing from heartbeat_core
    GATE_KEYS, so gates.py ran defaults [0.0, 999.0) and the elite-bull block applied at ALL
    VIX instead of the ratified band (Safe [0,25)).

  FIX4 — vwap_continuation ARMED on Safe (J trade-to-learn mandate): params.json now carries
    extra_setup_exec_armed.vwap_continuation=true; the routed _execute trades the VALIDATED
    cell (WP-5 ATM strike override, qty=3). gap_and_go NOT armed; Bold NOT armed.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_money_path_2026_07_01.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

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

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
BOLD_PARAMS_PATH = ROOT / "automation" / "state" / "aggressive" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def fl():
    return importlib.import_module("fleet_live")


# =============================================================================
# FIX1 — entry-time ceiling
# =============================================================================
class TestEntryCeiling:
    @pytest.mark.parametrize("hh,mm,expected", [
        (14, 0, False),   # mission guard (a): 14:00 allowed
        (14, 59, False),
        (15, 0, True),    # window is [09:35, 15:00) — 15:00 itself is late
        (15, 30, True),   # mission guard (a): 15:30 suppressed
        (15, 51, True),   # yesterday's actual failure window
    ])
    def test_ceiling_boundaries(self, hc, hh, mm, expected):
        now = dt.datetime(2026, 7, 2, hh, mm)
        assert hc._past_entry_ceiling(SAFE_PARAMS, now) is expected

    @pytest.mark.parametrize("params", [
        {},                                     # key absent -> fail CLOSED to 15:00
        {"entry_no_trade_after_et": None},
        {"entry_no_trade_after_et": "garbage"},
        {"entry_no_trade_after_et": ["15", "00"]},
        "not-a-dict",
    ])
    def test_ceiling_fails_closed_on_missing_or_malformed(self, hc, params):
        assert hc._past_entry_ceiling(params, dt.datetime(2026, 7, 2, 15, 1)) is True
        assert hc._past_entry_ceiling(params, dt.datetime(2026, 7, 2, 14, 59)) is False

    # ---- core path (run_account) ------------------------------------------
    @staticmethod
    def _wire_run_account(hc, monkeypatch, now):
        payload = {"bar_ctx": {
            "bar": {"close": 620.0},
            "ribbon_now": {"stack": "BEARISH", "spread_cents": 45.0},
            "vix_now": 17.2, "vix_prior": 17.3, "htf_15m_stack": "BEARISH"}}
        verdict = {"verdict": "ENTER_BEAR", "side": "P",
                   "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "bear_score": 9, "bull_score": 2,
                   "triggers_fired": ["level_rejection"], "reason": "test"}
        monkeypatch.setattr(hc, "_et_now", lambda: now)
        monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
        monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
        monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
        monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        logged: list = []
        monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
        monkeypatch.setitem(sys.modules, "setup_dispatch",
                            types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
        return logged

    def test_run_account_enter_at_1530_is_skip_late_entry(self, hc, monkeypatch):
        """Mission guard (a): an ENTER verdict at 15:30 ET is a logged SKIP, no model
        call, no _execute, no order attempt."""
        logged = self._wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 2, 15, 30))
        executed = {"n": 0}
        evaled = {"n": 0}
        monkeypatch.setattr(hc, "_execute",
                            lambda *a, **k: executed.__setitem__("n", executed["n"] + 1) or {"status": "X"})
        monkeypatch.setattr(hc, "_free_model_eval",
                            lambda *a, **k: evaled.__setitem__("n", evaled["n"] + 1) or {"veto": False})
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_LATE_ENTRY"
        assert executed["n"] == 0, "no order attempt after the entry ceiling"
        assert evaled["n"] == 0, "free-model eval must not run on a late tick"
        assert logged and logged[-1]["action"] == "SKIP_LATE_ENTRY", "the SKIP must be a LOGGED verdict"

    def test_run_account_enter_at_1400_is_allowed(self, hc, monkeypatch):
        """Mission guard (a): an ENTER verdict at 14:00 ET still routes to _execute."""
        self._wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 2, 14, 0))
        executed = {"n": 0}
        monkeypatch.setattr(hc, "_execute",
                            lambda *a, **k: executed.__setitem__("n", executed["n"] + 1) or {"status": "WOULD_PLACE"})
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        rec = hc.run_account("safe")
        assert executed["n"] == 1, "14:00 ENTER must reach _execute"
        assert rec["action"] == "WOULD_PLACE"

    # ---- belt-and-suspenders inside _execute (covers the extra-setup route) --
    def test_execute_skip_late_entry_touches_no_broker(self, hc, monkeypatch):
        import fleet_broker as fb

        def _boom(*a, **k):
            raise AssertionError("broker must not be touched after the entry ceiling")
        monkeypatch.setattr(fb, "load_creds", _boom)
        monkeypatch.setattr(fb, "_request", _boom)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 2, 15, 30))
        out = hc._execute("safe", {"verdict": "ENTER_BEAR"}, {"bar_ctx": {"bar": {"close": 620.0}}},
                          SAFE_PARAMS, dry=False)
        assert out["status"] == "SKIP_LATE_ENTRY"

    def test_extra_route_late_fire_is_skip_late_entry(self, hc, monkeypatch):
        """An ARMED vwap_continuation fire at 15:30 dies at _execute's ceiling check —
        logged SKIP, no broker touch (the extra-setup route is covered too)."""
        import fleet_broker as fb

        def _boom(*a, **k):
            raise AssertionError("broker must not be touched after the entry ceiling")
        monkeypatch.setattr(fb, "load_creds", _boom)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 2, 15, 30))
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, SAFE_PARAMS)
        assert out[0]["action"] == "SKIP_LATE_ENTRY"

    def test_fleet_place_live_skip_late_entry(self, fl, monkeypatch):
        """fleet executor path (safe-1/risky-3 hit the same 15:52 rejection)."""
        def _boom(*a, **k):
            raise AssertionError("broker must not be touched after the entry ceiling")
        monkeypatch.setattr(fl.fb, "get_option_mid", _boom)
        monkeypatch.setattr(fl.fb, "_request", _boom)
        decision = types.SimpleNamespace(side="P", strike=620, qty=3, setup_name="x")
        res = fl._place_live(_CREDS, {"id": "safe-1"}, decision, {}, {},
                             {"entry_no_trade_after_et": "15:00"},
                             dt.datetime(2026, 7, 2, 15, 52))
        assert res["placed"] is False and res["reason"] == "SKIP_LATE_ENTRY"
        assert fl._past_entry_ceiling({"entry_no_trade_after_et": "15:00"},
                                      dt.datetime(2026, 7, 2, 14, 0)) is False


# =============================================================================
# FIX2 — simple-FIRST options placement (no bracket/oto attempt, ever)
# =============================================================================
def _wire_execute(hc, monkeypatch, tmp_path, *, equity="2000.0", manages_exits=True,
                  now=dt.datetime(2026, 7, 2, 11, 0)):
    """Full _execute harness: fake broker REST, real risk_gate/strike_selection/params."""
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})
        return {"id": "ord-1", "status": "accepted"}

    monkeypatch.setattr(fb, "_request", fake_request)
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
    monkeypatch.setattr(fb, "marketable_limit_price",
                        lambda c, s, side="buy", buffer=0.03: 1.08)
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "STATE", tmp_path)  # no circuit-breaker / kill-switch files
    monkeypatch.setattr(hc, "_quality_lock_check",
                        lambda *a, **k: {"allow": True, "rank": 1, "tier": "BASE", "prior_quality": 0})
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", manages_exits)
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        types.SimpleNamespace(register_entry=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


class TestSimpleFirstPlacement:
    def test_place_simple_entry_is_one_plain_limit_post(self, hc, monkeypatch):
        import fleet_broker as fb
        posts: list = []
        monkeypatch.setattr(fb, "_request",
                            lambda creds, endpoint, method="GET", data=None, timeout=15:
                            posts.append({"endpoint": endpoint, "method": method, "data": data})
                            or {"id": "ord-1", "status": "accepted"})
        res = hc._place_simple_entry(_CREDS, symbol="SPY260702P00620000", qty=3, limit_price=1.08)
        assert len(posts) == 1
        data = posts[0]["data"]
        assert posts[0]["endpoint"] == "orders" and posts[0]["method"] == "POST"
        assert "order_class" not in data and "take_profit" not in data and "stop_loss" not in data
        assert data == {"symbol": "SPY260702P00620000", "qty": "3", "side": "buy",
                        "type": "limit", "limit_price": "1.08", "time_in_force": "day"}
        assert res.get("_simple_first") is True

    @pytest.mark.parametrize("qty,px", [(0, 1.08), (None, 1.08), (3, 0), (3, None)])
    def test_place_simple_entry_refuses_bad_inputs(self, hc, monkeypatch, qty, px):
        import fleet_broker as fb
        monkeypatch.setattr(fb, "_request",
                            lambda *a, **k: pytest.fail("must not POST on bad inputs"))
        res = hc._place_simple_entry(_CREDS, symbol="S", qty=qty, limit_price=px)
        assert "_refused" in res

    def test_execute_first_and_only_order_call_is_simple_marketable(self, hc, monkeypatch, tmp_path):
        """Mission guard (b): mock broker; assert the FIRST (and only) order call is the
        simple marketable limit — NO bracket, NO oto, priced at ask+buffer."""
        posts = _wire_execute(hc, monkeypatch, tmp_path)
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.0}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert len(posts) == 1, f"exactly ONE order POST expected, got {posts}"
        first = posts[0]["data"]
        assert "order_class" not in first, "bracket/oto attempt detected — FIX2 regression"
        assert first["type"] == "limit"
        assert first["limit_price"] == "1.08", "entry must be marketable (ask + entry_cross_buffer)"
        assert plan["entry_px"] == 1.08
        assert plan["broker"].get("_simple_first") is True

    def test_execute_refuses_simple_when_exits_unmanaged(self, hc, monkeypatch, tmp_path):
        """C2: without engine-managed exits a stopless simple entry must NOT be placed."""
        posts = _wire_execute(hc, monkeypatch, tmp_path, manages_exits=False)
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.0}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACE_FAIL"
        assert "_refused" in plan["broker"]
        assert posts == [], "no order POST may happen when exits are unmanaged"

    @pytest.mark.parametrize("path", [
        ROOT / "setup" / "scripts" / "heartbeat_core.py",
        ROOT / "automation" / "state" / "fleet" / "fleet_live.py",
    ])
    def test_no_place_bracket_call_left_in_either_live_path(self, path):
        """AST guard: neither heartbeat_core nor fleet_live may CALL place_bracket (the
        2x-422 bracket->oto ladder) again. Comments/docstrings are ignored."""
        import ast
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name == "place_bracket":
                    offenders.append(node.lineno)
        assert not offenders, (
            f"{path.name} calls place_bracket at lines {offenders} — every options entry "
            "would eat 2 guaranteed 422s (bracket_err + oto_err) again. FIX2 regression."
        )


# =============================================================================
# FIX3 — GATE_KEYS carries the elite-bull VIX band and gates consume it
# =============================================================================
class TestGateKeysVixBand:
    def test_gate_keys_include_both_band_keys(self, hc):
        assert "block_elite_bull_vix_low" in hc.GATE_KEYS
        assert "block_elite_bull_vix_high" in hc.GATE_KEYS

    def test_band_values_reach_gate_params(self, hc):
        """The exact dict heartbeat_core builds for engine_cli must carry the ratified band
        for BOTH accounts (Safe [0,25), Bold [15,18))."""
        safe_gp = {k: SAFE_PARAMS[k] for k in hc.GATE_KEYS if k in SAFE_PARAMS}
        assert safe_gp["block_elite_bull_vix_low"] == 0.0
        assert safe_gp["block_elite_bull_vix_high"] == 25.0
        bold_gp = {k: BOLD_PARAMS[k] for k in hc.GATE_KEYS if k in BOLD_PARAMS}
        assert bold_gp["block_elite_bull_vix_low"] == 15.0
        assert bold_gp["block_elite_bull_vix_high"] == 18.0

    @staticmethod
    def _elite_bull_ctx(vix):
        from lib.engine.gates import GateContext
        return GateContext(
            winning_side="C",
            winning_triggers=["level_reclaim", "confluence"],
            quality_tier="ELITE",
            has_level=True,
            bar=pd.Series({"open": 620.0, "high": 621.0, "low": 619.5,
                           "close": 620.8, "volume": 1_000_000.0}),
            bar_idx=50,
            bar_time=dt.datetime(2026, 7, 2, 10, 30),
            vix_now=vix,
            ribbon_spread_cents=45.0,
            ribbon_stack="BULLISH",
            spy_df=None,
            ribbon_df=None,
        )

    def test_gates_apply_band_inside_and_outside(self, hc):
        from lib.engine.gates import evaluate_gates
        band = {"block_elite_bull": True,
                "block_elite_bull_vix_low": SAFE_PARAMS["block_elite_bull_vix_low"],
                "block_elite_bull_vix_high": SAFE_PARAMS["block_elite_bull_vix_high"]}
        # inside [0, 25): blocked
        blk = evaluate_gates(self._elite_bull_ctx(20.0), band)
        assert blk is not None and blk.gate_id == "block_elite_bull"
        # outside the band (VIX 30 >= 25): NOT blocked by the elite-bull gate
        blk_hi = evaluate_gates(self._elite_bull_ctx(30.0), band)
        assert blk_hi is None or blk_hi.gate_id != "block_elite_bull"
        # THE BUG THIS FIX REMOVES: without the band keys (old GATE_KEYS) the gate
        # defaults to [0.0, 999.0) and blocks at ALL VIX.
        blk_bug = evaluate_gates(self._elite_bull_ctx(30.0), {"block_elite_bull": True})
        assert blk_bug is not None and blk_bug.gate_id == "block_elite_bull"

    def test_band_values_not_changed_by_this_fix(self):
        """FIX3 is code-side only — the 06-30 A/B-proven band values stay untouched."""
        assert SAFE_PARAMS["block_elite_bull_vix_low"] == 0.0
        assert SAFE_PARAMS["block_elite_bull_vix_high"] == 25.0


# =============================================================================
# FIX4 — vwap_continuation armed on Safe; validated cell (ATM strike, qty 3)
# =============================================================================
class TestVwapContinuationArmed:
    def test_safe_params_arm_vwap_continuation_only(self, hc):
        armed = SAFE_PARAMS.get("extra_setup_exec_armed")
        assert isinstance(armed, dict) and armed.get("vwap_continuation") is True, \
            "Safe params must arm vwap_continuation (J trade-to-learn mandate 2026-07-01)"
        assert armed.get("gap_and_go") is not True, \
            "gap_and_go must NOT be armed (0 robust cells on 06-28 re-validation + broken feed)"
        assert hc._extra_exec_armed(SAFE_PARAMS, "vwap_continuation") is True
        assert hc._extra_exec_armed(SAFE_PARAMS, "gap_and_go") is False

    def test_bold_params_not_armed(self, hc):
        assert hc._extra_exec_armed(BOLD_PARAMS, "vwap_continuation") is False, \
            "Bold must stay unarmed: min_contracts=5 conflicts with the validated qty-3 cell"

    def test_wp5_strike_override_enabled_on_safe(self):
        assert SAFE_PARAMS["j_vwap_cont_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_vwap_cont_strike_offset_safe"] == 0  # ATM

    def test_fired_armed_vwap_routes_to_execute(self, hc, monkeypatch):
        """Mission guard (d): fired + REAL-params-armed vwap_continuation reaches _execute."""
        captured: dict = {}

        def fake_execute(account, verdict, payload, params, *, dry):
            captured.update(account=account, verdict=verdict, dry=dry)
            return {"status": "WOULD_PLACE"}

        monkeypatch.setattr(hc, "_execute", fake_execute)
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 2, 11, 0))
        extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, SAFE_PARAMS)
        assert captured["verdict"]["verdict"] == "ENTER_BEAR"
        assert captured["verdict"]["setup_name"] == "vwap_continuation"
        assert out[0]["action"] == "WOULD_PLACE"

    def test_missing_key_stays_watch_not_armed(self, hc, monkeypatch):
        """Mission guard (d): without the armed key the same fire is WATCH-only."""
        monkeypatch.setattr(hc, "_execute",
                            lambda *a, **k: pytest.fail("must not execute when not armed"))
        extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}},
                                     {"j_vwap_cont_enabled": True})
        assert out == [{"setup": "vwap_continuation", "action": "WATCH_NOT_ARMED"}]

    def test_execute_vwap_uses_validated_atm_strike_and_qty3(self, hc, monkeypatch, tmp_path):
        """The routed order trades the VALIDATED cell: ATM strike (WP-5 override) + qty 3.
        Vary-and-assert (C14): at $25K equity the generic Safe tier is ITM-2 (+2), so the
        override MUST move the strike to ATM; with the flag off it must NOT."""
        posts = _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "vwap_continuation",
                   "triggers_fired": ["vwap_continuation"]}
        payload = {"bar_ctx": {"bar": {"close": 620.4}}}
        plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert plan["strike"] == 620, "vwap_continuation must trade ATM (WP-5 validated cell)"
        assert plan["qty"] == 3, "validated cell is qty 3 (min_contracts)"
        assert plan["symbol"].startswith("SPY") and "P00620000" in plan["symbol"]
        assert len(posts) == 1 and "order_class" not in posts[0]["data"]

        # flag OFF -> generic tier (ITM-2 at $25K => 622 for a put): proves the knob is LIVE
        off = dict(SAFE_PARAMS)
        off["j_vwap_cont_strike_override_enabled"] = False
        plan_off = hc._execute("safe", verdict, payload, off, dry=True)
        assert plan_off["strike"] == 622, "override flag must be load-bearing (C14 vary-and-assert)"

    def test_generic_ribbon_setup_unaffected_by_override(self, hc, monkeypatch, tmp_path):
        """C29: the per-setup override must NOT leak to other setups."""
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.4}}},
                           SAFE_PARAMS, dry=True)
        assert plan["strike"] == 622  # generic Safe ITM-2 tier at $25K, unchanged
