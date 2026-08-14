"""PROFIT-P2-ARMED guard (2026-07-11): core Safe ribbon_ride strike OTM-2 -> ATM.

Evidence: analysis/recommendations/ribbon-ride-strike-exit-ab.json, axis1_strike ATM cell
(n=244/250 identical signals, real OPRA replayed through the LIVE exit_manager decision
core): delta_expectancy +$47.96/tr, delta_oos_total +$8,573.6, WF 4.25, both halves
positive, beats its random-entry null, BH-FDR survivor, stable on the fill-bar sensitivity
toggle. clears_auto_ratify_bar=true, anchor_no_regression_op16=true,
unstable_on_open_audit=false. Full provenance: params.json#_j_ribbon_ride_strike_override_doc.

Mechanism: adds ribbon_ride's two entry_setups (BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON, lowercased) to setup/scripts/heartbeat_core.py's
_SETUP_STRIKE_OVERRIDES dispatch table — the SAME table + SAME 3-key params shape the
5 WP-5/trade-to-learn extra-setup overrides already use (test_money_path_2026_07_01.py,
test_trade_to_learn_2026_07_01.py). ribbon_ride is a CORE setup (always evaluated via the
primary ENTER_BEAR/ENTER_BULL verdict path in _execute, never gated by
extra_setup_exec_armed) — this ticket only adds its strike dispatch entry, nothing about
its arming/routing changes.

SCOPE: Safe-side ribbon_ride STRIKE only.
  - OTM-1 and ITM-2 do NOT clear OP-11 auto-ratify on this cohort (OTM-1 fails its own
    random-entry null; ITM-2 fails WF/sub_window_stable, C22 regime-concentration) — NOT
    armed, this file does not touch them.
  - Bold/aggressive is untouched: no j_ribbon_ride_strike_offset_bold key exists anywhere,
    and Bold reads a WHOLLY SEPARATE params file (automation/state/aggressive/params.json)
    this ticket never edits — the enable flag itself is absent there, so the override
    short-circuits False for account="bold" regardless of any offset key value.
  - Exit shape (SS-B, structure-stop) is untouched — _SETUP_EXIT_OVERRIDES was not edited.

DORMANCY: the core Safe account (safe-2, PA3S2PYAS2WQ) is DELETED pending J's
replacement — this override is INERT on the core/heartbeat_core.py lane until re-wired.
The safe-* FLEET arms (safe-1/safe-3) do NOT consume this key at all: fleet_executor.py's
strike selection is a wholly separate mechanism (_tiers_for_arm -> crypto/lib/
strike_selection.py#V15_SAFE_TIERS, keyed only by the arm's strike_tier_table, zero
per-setup dispatch) — they are structurally unchanged by this file's change either way.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_ribbon_ride_strike_override_2026_07_11.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from _broker_request_stub import broker_list_stub, order_posts  # shared L294 contract

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

BEAR_SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"
BULL_SETUP = "BULLISH_RECLAIM_RIDE_THE_RIBBON"


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


def _wire_execute(hc, monkeypatch, tmp_path, *, equity="25000.0",
                  now=dt.datetime(2026, 7, 11, 11, 0)):
    """Full _execute harness (mirrors test_trade_to_learn_2026_07_01._wire_execute): fake
    broker REST, real risk_gate/strike_selection/params."""
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
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
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
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


_PAYLOAD_25K = {"bar_ctx": {"timestamp_et": "2026-07-11 10:55:00", "bar": {"close": 620.4}}}


# =============================================================================
# ARM0 — params.json pins (the arming state itself)
# =============================================================================
class TestParamsArming:
    def test_safe_flags_on_disk(self):
        assert SAFE_PARAMS["j_ribbon_ride_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_ribbon_ride_strike_offset_safe"] == 0  # ATM

    def test_bold_params_file_lacks_the_flag_entirely(self):
        """Structural (not just behavioral) proof Bold cannot leak: the enable key is
        ABSENT from aggressive/params.json, not merely False — this file was never
        touched by the ship. Bold's ITM-2-by-design strike selection is untouched."""
        assert "j_ribbon_ride_strike_override_enabled" not in BOLD_PARAMS
        assert "j_ribbon_ride_strike_offset_safe" not in BOLD_PARAMS
        assert "j_ribbon_ride_strike_offset_bold" not in BOLD_PARAMS

    def test_only_atm_armed_not_otm1_or_itm2(self):
        """Scope pin: the offset is 0 (ATM) — OTM-1 (fails its own random-entry null) and
        ITM-2 (fails WF/sub_window_stable, C22 regime-concentration) are NOT armed."""
        assert SAFE_PARAMS["j_ribbon_ride_strike_offset_safe"] == 0
        assert SAFE_PARAMS["j_ribbon_ride_strike_offset_safe"] != -1  # not OTM-1
        assert SAFE_PARAMS["j_ribbon_ride_strike_offset_safe"] != 2   # not ITM-2

    def test_dispatch_table_carries_both_ribbon_directions(self, hc):
        sov = hc._SETUP_STRIKE_OVERRIDES
        assert sov["bearish_rejection_ride_the_ribbon"] == (
            "j_ribbon_ride_strike_override_enabled",
            "j_ribbon_ride_strike_offset_safe",
            "j_ribbon_ride_strike_offset_bold",
        )
        assert sov["bullish_reclaim_ride_the_ribbon"] == sov["bearish_rejection_ride_the_ribbon"]


# =============================================================================
# Strike override — vary-and-assert (C14 / OP-16 sim-accuracy scar): proves the LIVE
# _execute path actually CONSUMES the configured value, both directions, both ways.
# At $25K equity the generic Safe tier is ITM-2 (+2): put -> 622 / call -> 618 for a
# 620.4 spot; the override must move BOTH to ATM 620, and flag-off must revert BOTH.
# =============================================================================
class TestStrikeOverride:
    def test_bear_trades_atm_and_flag_off_reverts(self, hc, monkeypatch, tmp_path):
        posts = _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": BEAR_SETUP,
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("safe", verdict, _PAYLOAD_25K, SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert plan["strike"] == 620, "ribbon_ride BEAR must trade ATM (validated cell)"
        assert len(order_posts(posts)) == 1 and "order_class" not in order_posts(posts)[0]["data"]

        off = dict(SAFE_PARAMS)
        off["j_ribbon_ride_strike_override_enabled"] = False
        plan_off = hc._execute("safe", verdict, _PAYLOAD_25K, off, dry=True)
        assert plan_off["strike"] == 622, \
            "flag off must revert to the generic Safe ITM-2 tier (C14 vary-and-assert)"

    def test_bull_trades_atm_and_flag_off_reverts(self, hc, monkeypatch, tmp_path):
        posts = _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BULL", "setup_name": BULL_SETUP,
                   "triggers_fired": ["level_reclaim"]}
        plan = hc._execute("safe", verdict, _PAYLOAD_25K, SAFE_PARAMS, dry=False)
        assert plan["status"] == "PLACED", plan
        assert plan["strike"] == 620, "ribbon_ride BULL must trade ATM (validated cell)"
        assert len(order_posts(posts)) == 1 and "order_class" not in order_posts(posts)[0]["data"]

        off = dict(SAFE_PARAMS)
        off["j_ribbon_ride_strike_override_enabled"] = False
        plan_off = hc._execute("safe", verdict, _PAYLOAD_25K, off, dry=True)
        assert plan_off["strike"] == 618, \
            "flag off must revert to the generic Safe ITM-2 tier (C14 vary-and-assert)"

    def test_setup_name_fallback_when_verdict_omits_it(self, hc, monkeypatch, tmp_path):
        """_execute derives setup_name from side when the verdict dict omits it
        (production default path) — confirm the override still dispatches correctly
        via that fallback, not only when setup_name is explicit."""
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR"}  # no setup_name key at all
        plan = hc._execute("safe", verdict, _PAYLOAD_25K, SAFE_PARAMS, dry=True)
        assert plan["strike"] == 620

    def test_offset_nonzero_would_move_strike_away_from_atm(self, hc, monkeypatch, tmp_path):
        """Sanity check on the override MATH itself (not just the flag gate): a
        hypothetical non-ATM offset actually moves the strike, proving this isn't a
        coincidental always-620 code path."""
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        hypothetical = dict(SAFE_PARAMS)
        hypothetical["j_ribbon_ride_strike_offset_safe"] = 2  # ITM-2, same as generic here
        verdict = {"verdict": "ENTER_BEAR", "setup_name": BEAR_SETUP}
        plan = hc._execute("safe", verdict, _PAYLOAD_25K, hypothetical, dry=True)
        assert plan["strike"] == 622  # ATM(620) + 2, proves the offset value is READ verbatim


# =============================================================================
# Bold safety — behavioral proof (not just the structural params-file check above):
# calling _execute("bold", ...) with a ribbon verdict and BOLD_PARAMS never overrides.
# =============================================================================
class TestBoldUnaffected:
    def test_bold_ribbon_bear_uses_generic_bold_tier(self, hc, monkeypatch, tmp_path):
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": BEAR_SETUP,
                   "triggers_fired": ["level_rejection"]}
        plan = hc._execute("bold", verdict, _PAYLOAD_25K, BOLD_PARAMS, dry=True)
        assert plan["strike"] == 622, \
            "Bold must stay on its generic ITM-2-by-design tier, unaffected by this ship"

    def test_bold_ribbon_bull_uses_generic_bold_tier(self, hc, monkeypatch, tmp_path):
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BULL", "setup_name": BULL_SETUP,
                   "triggers_fired": ["level_reclaim"]}
        plan = hc._execute("bold", verdict, _PAYLOAD_25K, BOLD_PARAMS, dry=True)
        assert plan["strike"] == 618, \
            "Bold must stay on its generic ITM-2-by-design tier, unaffected by this ship"


# =============================================================================
# Cross-setup non-leak — adding ribbon's 2 dict entries must not disturb the 5
# pre-existing extra-setup overrides (dict lookup is exact-key, but prove it live).
# =============================================================================
class TestOtherSetupsStillUnaffected:
    def test_vwap_continuation_still_trades_its_own_validated_cell(self, hc, monkeypatch,
                                                                    tmp_path):
        _wire_execute(hc, monkeypatch, tmp_path, equity="25000.0")
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "vwap_continuation",
                   "triggers_fired": ["vwap_continuation"]}
        plan = hc._execute("safe", verdict, _PAYLOAD_25K, SAFE_PARAMS, dry=True)
        assert plan["strike"] == 620  # vwap_continuation's own WP-5 ATM cell, unchanged
