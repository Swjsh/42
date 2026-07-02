"""TRADE-TO-LEARN guards for the 2026-07-01 batch-2 arming (J ratified: validated setups
arm on PAPER even while recency is not CONFIRMed; strict gates apply to live money only).

Pins, RED-on-regression — three setups armed on SAFE ONLY, each at its VALIDATED cell
(C29: cells don't transfer across strike tiers):

  ARM1 — vwap_reclaim_failed_break: the ATM RESCUE cell (RECLAIM-RESCUE-SCORECARD.md
    rank 1, 8/8 gates, OOS +$32.33/tr n=76): strike ATM (offset 0), isolated stop -0.08,
    tp1 0.30, buffer 0.25, qty 3. side='both' (validated cell pools both sides; the live
    dispatch routes both — 'put' was a dead knob on this path, C14).

  ARM2 — vix_regime_dayside: the ATM ROBUST cell (vix_regime_dayside.json, 8/8 gates,
    OOS +$79.49/tr n=21): strike ATM, isolated stop -0.08 (LOAD-BEARING per its G8 gate),
    tp1 0.30, low_margin 0.25 / not_rising, qty 3. Enabling the flag also arms the G6
    vix_intraday producer (test_g6_vix_intraday_feed.py owns that contract; feed verified
    live 2026-07-01: 156 RTH 5m closes = the 78-bar median warmup + today).

  ARM3 — double_bottom_base_quiet: the flag db_base_quiet_enabled was ABSENT from
    params.json, so the dispatcher entry never even evaluated (the dead-end this batch
    closes). Armed at the best clearing cell of edgehunt-double_bottom_base_quiet.json
    (strike+0_stop-0.99: N=122, WR 63.9%, OOS +$26.3/tr): strike ATM, isolated stop -0.99
    (chart/TP/time-stop cell), tp1 0.30, runner 2.0, qty 3.

  Cross-cutting: per-setup strike overrides (_SETUP_STRIKE_OVERRIDES) and ISOLATED exit
  shapes (_SETUP_EXIT_OVERRIDES) are load-bearing (C14 vary-and-assert both ways);
  vwap_continuation keeps its FIX4 behavior byte-identical (global exit knobs); Bold is
  NOT armed; gap_and_go stays NOT armed (0 robust cells on the 06-28 re-validation).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_trade_to_learn_2026_07_01.py
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

THE_THREE = ("vwap_reclaim_failed_break", "vix_regime_dayside", "double_bottom_base_quiet")


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


class _RegRecorder:
    """Captures exit_actuator.register_entry kwargs (the exit shape the manager will run)."""

    def __init__(self):
        self.calls: list = []

    def register_entry(self, *a, **k):
        self.calls.append(k)
        return None


def _wire_execute(hc, monkeypatch, tmp_path, *, equity="25000.0", manages_exits=True,
                  now=dt.datetime(2026, 7, 2, 11, 0), reg: "_RegRecorder | None" = None):
    """Full _execute harness (mirrors test_money_path_2026_07_01._wire_execute): fake
    broker REST, real risk_gate/strike_selection/params, optional register_entry capture."""
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
                        reg if reg is not None
                        else types.SimpleNamespace(register_entry=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


# =============================================================================
# ARM0 — params.json pins (the arming state itself)
# =============================================================================
class TestParamsArming:
    def test_safe_arms_all_three_plus_vwap_cont(self, hc):
        armed = SAFE_PARAMS.get("extra_setup_exec_armed")
        assert isinstance(armed, dict)
        for s in THE_THREE + ("vwap_continuation",):
            assert armed.get(s) is True, f"Safe must arm {s} (trade-to-learn 2026-07-01)"
            assert hc._extra_exec_armed(SAFE_PARAMS, s) is True
        assert armed.get("gap_and_go") is not True, \
            "gap_and_go must NOT be armed (0 robust cells on 06-28 re-validation)"

    def test_enable_flags_on_disk(self):
        assert SAFE_PARAMS["j_vwap_reclaim_fb_enabled"] is True
        assert SAFE_PARAMS["j_vix_dayside_enabled"] is True
        assert SAFE_PARAMS["db_base_quiet_enabled"] is True, \
            "the ABSENT-flag dead-end (detector never evaluated) must stay closed"

    @pytest.mark.parametrize("setup", THE_THREE)
    def test_bold_not_armed(self, hc, setup):
        assert hc._extra_exec_armed(BOLD_PARAMS, setup) is False, \
            f"Bold/aggressive must NOT arm {setup} (Safe-only mandate)"

    def test_validated_cells_on_disk(self):
        # ARM1 — reclaim_fb ATM rescue cell (tp1=0.30 / buf=0.25 / stop=-0.08 / ATM)
        assert SAFE_PARAMS["j_vwap_reclaim_fb_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_vwap_reclaim_fb_strike_offset_safe"] == 0
        assert SAFE_PARAMS["j_vwap_reclaim_fb_premium_stop_pct"] == -0.08
        assert SAFE_PARAMS["j_vwap_reclaim_fb_tp1_pct"] == 0.30
        assert SAFE_PARAMS["j_vwap_reclaim_fb_stop_buffer"] == 0.25  # THE rescue knob
        assert SAFE_PARAMS["j_vwap_reclaim_fb_side"] == "both"
        # ARM2 — vix_dayside ATM robust cell
        assert SAFE_PARAMS["j_vix_dayside_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_vix_dayside_strike_offset_safe"] == 0
        assert SAFE_PARAMS["j_vix_dayside_premium_stop_pct"] == -0.08
        assert SAFE_PARAMS["j_vix_dayside_tp1_pct"] == 0.30
        assert SAFE_PARAMS["j_vix_dayside_low_margin"] == 0.25
        assert SAFE_PARAMS["j_vix_dayside_slope_rule"] == "not_rising"
        # ARM3 — db_base_quiet best clearing cell (strike+0_stop-0.99, tp1 0.3, runner 2.0)
        assert SAFE_PARAMS["j_db_base_quiet_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_db_base_quiet_strike_offset_safe"] == 0
        assert SAFE_PARAMS["j_db_base_quiet_premium_stop_pct"] == -0.99
        assert SAFE_PARAMS["j_db_base_quiet_tp1_pct"] == 0.30
        assert SAFE_PARAMS["j_db_base_quiet_runner_target_pct"] == 2.0


# =============================================================================
# Routing — fired + REAL-disk-armed rows reach _execute; unarmed stays WATCH
# =============================================================================
ROUTES = [
    ("vwap_reclaim_failed_break", "short", "ENTER_BEAR"),
    ("vwap_reclaim_failed_break", "long", "ENTER_BULL"),
    ("vix_regime_dayside", "long", "ENTER_BULL"),
    ("vix_regime_dayside", "short", "ENTER_BEAR"),
    ("double_bottom_base_quiet", "long", "ENTER_BULL"),  # calls-only bullish family
]


class TestRouting:
    @pytest.mark.parametrize("setup,direction,expected_verdict", ROUTES)
    def test_fired_armed_setup_routes_to_execute(self, hc, monkeypatch, setup, direction,
                                                 expected_verdict):
        captured: dict = {}

        def fake_execute(account, verdict, payload, params, *, dry):
            captured.update(account=account, verdict=verdict, dry=dry)
            return {"status": "WOULD_PLACE"}

        monkeypatch.setattr(hc, "_execute", fake_execute)
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 2, 11, 0))
        extra = [{"setup_name": setup, "fired": True, "direction": direction,
                  "triggers": [setup]}]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, SAFE_PARAMS)
        assert captured["verdict"]["verdict"] == expected_verdict
        assert captured["verdict"]["setup_name"] == setup
        assert out[0]["action"] == "WOULD_PLACE"

    def test_one_entry_per_tick_second_fire_is_skipped(self, hc, monkeypatch):
        """With 4 setups armed, two same-tick fires must NOT both place (flat-verify reads
        positions, not working orders — 3P+3C could fill simultaneously). First placement
        wins; the second logs SKIP_TICK_ENTRY_TAKEN and touches neither models nor broker."""
        executed: list = []

        def fake_execute(account, verdict, payload, params, *, dry):
            executed.append(verdict["setup_name"])
            return {"status": "WOULD_PLACE"}

        evals = {"n": 0}
        monkeypatch.setattr(hc, "_execute", fake_execute)
        monkeypatch.setattr(hc, "_free_model_eval",
                            lambda *a, **k: evals.__setitem__("n", evals["n"] + 1) or {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        extra = [
            {"setup_name": "vwap_reclaim_failed_break", "fired": True, "direction": "short",
             "triggers": ["vwap_reclaim_failed_break"]},
            {"setup_name": "double_bottom_base_quiet", "fired": True, "direction": "long",
             "triggers": ["double_bottom_base_quiet"]},
        ]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, SAFE_PARAMS)
        assert executed == ["vwap_reclaim_failed_break"], "only the FIRST fire may place"
        assert evals["n"] == 1, "the skipped row must not spend a model eval"
        assert out[0]["action"] == "WOULD_PLACE"
        assert out[1] == {"setup": "double_bottom_base_quiet", "action": "SKIP_TICK_ENTRY_TAKEN"}

    def test_non_placing_first_fire_does_not_block_second(self, hc, monkeypatch):
        """A first fire that DIDN'T take the entry (e.g. NOT_FLAT/risk-deny) must not
        suppress a second, independent fire on the same tick."""
        statuses = iter([{"status": "NOT_FLAT"}, {"status": "WOULD_PLACE"}])
        executed: list = []

        def fake_execute(account, verdict, payload, params, *, dry):
            executed.append(verdict["setup_name"])
            return next(statuses)

        monkeypatch.setattr(hc, "_execute", fake_execute)
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        extra = [
            {"setup_name": "vwap_reclaim_failed_break", "fired": True, "direction": "short",
             "triggers": ["x"]},
            {"setup_name": "vix_regime_dayside", "fired": True, "direction": "short",
             "triggers": ["y"]},
        ]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, SAFE_PARAMS)
        assert executed == ["vwap_reclaim_failed_break", "vix_regime_dayside"]
        assert [r["action"] for r in out] == ["NOT_FLAT", "WOULD_PLACE"]

    @pytest.mark.parametrize("setup", THE_THREE)
    def test_missing_armed_key_stays_watch_not_armed(self, hc, monkeypatch, setup):
        monkeypatch.setattr(hc, "_execute",
                            lambda *a, **k: pytest.fail("must not execute when not armed"))
        extra = [{"setup_name": setup, "fired": True, "direction": "long",
                  "triggers": [setup]}]
        out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, {})
        assert out == [{"setup": setup, "action": "WATCH_NOT_ARMED"}]


# =============================================================================
# Strike override — validated ATM cell, vary-and-assert (C14) per setup.
# At $25K equity the generic Safe tier is ITM-2 (+2): put -> 622 / call -> 618 for a
# 620.4 spot, so the override MUST move the strike to ATM 620; flag off MUST NOT.
# =============================================================================
STRIKES = [
    # (setup, verdict, generic_strike_at_25k)  — spot 620.4, ATM = 620
    ("vwap_reclaim_failed_break", "ENTER_BEAR", 622),   # put: ITM-2 above spot
    ("vwap_reclaim_failed_break", "ENTER_BULL", 618),   # call: ITM-2 below spot
    ("vix_regime_dayside", "ENTER_BULL", 618),
    ("vix_regime_dayside", "ENTER_BEAR", 622),
    ("double_bottom_base_quiet", "ENTER_BULL", 618),
]


class TestStrikeOverride:
    @pytest.mark.parametrize("setup,verdict_name,generic_strike", STRIKES)
    def test_execute_trades_atm_and_flag_off_reverts(self, hc, monkeypatch, tmp_path,
                                                     setup, verdict_name, generic_strike):
        posts = _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": verdict_name, "setup_name": setup, "triggers_fired": [setup]}
        payload = {"bar_ctx": {"bar": {"close": 620.4}}}
        plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert plan["strike"] == 620, f"{setup} must trade ATM (its validated cell)"
        assert plan["qty"] == 3, "validated cell is qty 3 (min_contracts)"
        assert len(posts) == 1 and "order_class" not in posts[0]["data"]
        # flag OFF -> generic tier (proves the knob is LIVE, C14 vary-and-assert)
        off = dict(SAFE_PARAMS)
        off[f"{_flag_prefix(setup)}_strike_override_enabled"] = False
        plan_off = hc._execute("safe", verdict, payload, off, dry=True)
        assert plan_off["strike"] == generic_strike, \
            "override flag must be load-bearing (C14 vary-and-assert)"

    def test_generic_ribbon_setup_unaffected(self, hc, monkeypatch, tmp_path):
        """C29: no per-setup override leaks to the core ribbon setups."""
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.4}}},
                           SAFE_PARAMS, dry=True)
        assert plan["strike"] == 622  # generic Safe ITM-2 tier at $25K, unchanged


def _flag_prefix(setup: str) -> str:
    return {"vwap_reclaim_failed_break": "j_vwap_reclaim_fb",
            "vix_regime_dayside": "j_vix_dayside",
            "double_bottom_base_quiet": "j_db_base_quiet"}[setup]


# =============================================================================
# Isolated exit shape — the exit_manager runs the VALIDATED stop/TP1, never the
# global -50% cap (C14/L149; the -8% stop is LOAD-BEARING for vix_dayside per G8).
# =============================================================================
SHAPES = [
    # (setup, verdict, stop_pct, tp1_pct, runner_or_None)
    ("vwap_reclaim_failed_break", "ENTER_BEAR", -0.08, 0.30, None),
    ("vix_regime_dayside", "ENTER_BULL", -0.08, 0.30, None),
    ("double_bottom_base_quiet", "ENTER_BULL", -0.99, 0.30, 2.0),
]


class TestIsolatedExitShape:
    @pytest.mark.parametrize("setup,verdict_name,stop_pct,tp1_pct,runner", SHAPES)
    def test_registered_shape_is_the_validated_cell(self, hc, monkeypatch, tmp_path,
                                                    setup, verdict_name, stop_pct, tp1_pct,
                                                    runner):
        reg = _RegRecorder()
        _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
        verdict = {"verdict": verdict_name, "setup_name": setup, "triggers_fired": [setup]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.4}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        # plan-level tp/stop reflect the isolated knobs (mid mocked at 1.00)
        assert plan["stop"] == round(1.00 * (1 + stop_pct), 2)
        assert plan["tp"] == round(1.00 * (1 + tp1_pct), 2)
        # the exit_manager shape frozen at entry IS the validated cell
        assert len(reg.calls) == 1
        shape = reg.calls[0]["exit_shape"]
        assert shape["premium_stop_pct"] == stop_pct
        assert shape["tp1_premium_pct"] == tp1_pct
        if runner is not None:
            assert shape["runner_target_pct"] == runner

    def test_vwap_continuation_keeps_fix4_global_shape(self, hc, monkeypatch, tmp_path):
        """vwap_continuation (armed earlier tonight) must stay BYTE-IDENTICAL: global
        -50% catastrophe stop + global tp1 — NOT any isolated override."""
        reg = _RegRecorder()
        _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "vwap_continuation",
                   "triggers_fired": ["vwap_continuation"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.4}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert plan["stop"] == 0.50  # mid 1.00 * (1 - 0.50) — the global catastrophe cap
        shape = reg.calls[0]["exit_shape"]
        assert shape["premium_stop_pct"] == -0.50
        assert shape["tp1_premium_pct"] == float(SAFE_PARAMS["tp1_premium_pct"])

    def test_ribbon_setup_shape_unchanged(self, hc, monkeypatch, tmp_path):
        reg = _RegRecorder()
        _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"bar": {"close": 620.4}}},
                           SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert reg.calls[0]["exit_shape"]["premium_stop_pct"] == -0.50


# =============================================================================
# Dispatch inclusion — the DISK flags actually evaluate every armed detector
# (the db_base_quiet ABSENT-flag dead-end can never silently return).
# =============================================================================
def _ts(h, m, date="2026-01-07"):
    return f"{date}T{h:02d}:{m:02d}:00-04:00"


def _minimal_dispatch_payload():
    bars = [
        {"timestamp_iso": _ts(9, 30), "open": 600.0, "high": 600.6, "low": 599.9, "close": 599.5, "volume": 5000},
        {"timestamp_iso": _ts(9, 35), "open": 599.5, "high": 599.6, "low": 598.8, "close": 598.9, "volume": 5000},
        {"timestamp_iso": _ts(9, 40), "open": 598.9, "high": 599.0, "low": 598.2, "close": 598.3, "volume": 5000},
    ]
    bar_ctx = {
        "bar_idx": len(bars) - 1,
        "timestamp_et": bars[-1]["timestamp_iso"],
        "bar": {"open": 598.9, "high": 599.0, "low": 598.2, "close": 598.3, "volume": 5000},
        "ribbon_now": {"fast": 598.0, "pivot": 598.5, "slow": 599.0, "spread_cents": 200.0, "stack": "BEAR"},
        "ribbon_history": [], "vix_now": 17.0, "vix_prior": 17.5,
        "vol_baseline_20": 5000.0, "range_baseline_20": 0.5,
        "levels_active": [], "multi_day_levels": [], "htf_15m_stack": "BEAR",
    }
    return {"bar_ctx": bar_ctx, "sameday_5m_bars": bars,
            "spy_df": [{k: b[k] for k in ("open", "high", "low", "close", "volume")} for b in bars],
            "ribbon_df": [], "gate_params": {}, "score_params": {}}


def test_disk_params_dispatch_evaluates_all_armed_detectors():
    from setup_dispatch import SetupDispatcher
    results = SetupDispatcher(SAFE_PARAMS, _minimal_dispatch_payload()).run()
    names = {r.setup_name for r in results}
    for s in THE_THREE + ("vwap_continuation", "gap_and_go"):
        assert s in names, f"{s} enabled on disk but produced no dispatch row (dead-end)"
    for r in results:
        assert not str(r.skip_reason or "").startswith("SKIP_DETECTOR_ERROR"), \
            f"{r.setup_name} crashed at dispatch: {r.skip_reason}"


def test_disk_params_feed_vix_intraday_into_payload(hc, monkeypatch):
    """The DISK flag (j_vix_dayside_enabled=true) must actually pull the intraday VIX
    feed into bar_ctx — the producer half armed by this batch (consumer contract owned
    by test_g6_vix_intraday_feed.py). Fetch mocked; the REAL feed was verified live
    2026-07-01 (156 RTH 5m closes = 78-bar median warmup + today)."""
    calls = []

    def fake_fetch(cap_ts_et=None):
        calls.append(cap_ts_et)
        return [16.0, 16.1, 16.2]

    monkeypatch.setattr(hc, "_fetch_vix_intraday", fake_fetch)
    rows = []
    price, prev = 600.0, 599.94
    for d in range(4):
        day = pd.Timestamp(f"2026-06-0{d + 1} 00:00", tz="America/New_York")
        t = day + pd.Timedelta(hours=9, minutes=30)
        end = day + pd.Timedelta(hours=16)
        while t < end:
            price = round(price + 0.06, 2)
            rows.append({"timestamp": t, "open": prev, "high": max(prev, price) + 0.05,
                         "low": min(prev, price) - 0.05, "close": price, "volume": 1_000_000})
            prev = price
            t = t + pd.Timedelta(minutes=5)
    payload = hc._build_payload(pd.DataFrame(rows), SAFE_PARAMS, vix=(18.0, 17.9),
                                levels=([], []), vix_ma=(17.0, 16.5))
    assert payload is not None
    assert payload["bar_ctx"]["vix_intraday"] == [16.0, 16.1, 16.2]
    assert len(calls) == 1 and calls[0] is not None, "fetch must run once, causally capped"
