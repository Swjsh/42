"""BLINDNESS BLOCK guard (2026-07-30) — an engine with no key levels must not trade.

THE INCIDENT (2026-07-30, safe+bold, 772 ticks / 386 per account):
  Gamma_LevelRefresh last fired 2026-07-29 20:43 ET (its NextRunTime was 16:38 ET, AFTER the
  close), so automation/state/key-levels.json sat untouched for ~19.8h and every level in it
  carried expires_at 2026-07-29. heartbeat_core._read_levels dropped them all CORRECTLY via
  _level_expired -> levels_active == [] on 386 of 386 safe rows (2026-07-29: 0 of 375).

  With no levels, detect_level_rejection cannot fire, so scoring fell through to the one bear
  trigger that survives blindness -- trendline_rejection -- and the engine SILENTLY switched
  to its statistically worst entry mode. Attribution (analysis/deep-research/
  PNL-ATTRIBUTION-2026-07-28): trendline-only = -$1,830 / WR .19 over 124 trades and 89% of
  every bear ENTER verdict ever; every dollar the engine has made is level-tied
  (+$6,895 / 66 trades).

  At 11:31-11:46 ET it produced 11 ENTER_BEAR verdicts at SPY 734.885 -- the LOW OF THE DAY.
  SPY rallied to 741.6 into the close (~-6.7 SPY points wrong). They were stopped only by
  RISK_DENY_RISK_CAP / RISK_DENY_PDT: luck, not design. The engine had NO CONCEPT OF BEING
  BLIND -- it did not halt, warn, or degrade.

BYTE-QUOTED FIXTURE (automation/state/core-decisions.jsonl, the real 11:31:03 bold row):
  {"ts_et":"2026-07-30T11:31:03","account":"bold","spy":734.885,"ribbon":"BEAR",
   "htf_15m":"BEAR","verdict":"ENTER_BEAR","side":"P",
   "setup":"BEARISH_REJECTION_RIDE_THE_RIBBON","bear_score":8,"bull_score":5,
   "triggers":["ribbon_flip","trendline_rejection"],"levels_active":[],
   "trigger_level_exact":null,"action":"RISK_DENY_PDT","vix":19.05,
   "reason":"BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates
             (tier TRENDLINE)"}

THE RULE: blind => HOLD. An ENTER with NO level anchor, taken while levels_active is empty,
becomes SKIP_NO_LEVELS. Level-ANCHORED entries are untouched (fhh_level_rejection is computed
from today's own bars in _build_payload and still fires with an empty key-level file -- it is
a real anchor from the PROFITABLE cohort, so blocking it would be an edge change, not a
safety fix).

SCOPE FENCE, pinned by TestScopeFenceLevelsPresent: when levels exist, EVERY logged field is
byte-identical with the rail ON vs OFF.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q \
        backtest/tests/test_blind_no_levels_2026_07_30.py
"""
from __future__ import annotations

import datetime as dt
import importlib
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

hc = importlib.import_module("heartbeat_core")
bss = importlib.import_module("build_shared_signal")


# =============================================================================
# harness — mirrors test_gate_provenance_ordering_2026_07_10.py::_wire, extended so
# levels_active and the account params can be varied independently (that pair is the
# entire subject of this guard).
# =============================================================================
_NOW = dt.datetime(2026, 7, 30, 11, 31, 3)          # the real wall clock of the incident row
_BAR_ET = "2026-07-30T11:25:00-04:00"                # the real trigger_bar_et of that row


def _wire(monkeypatch, *, verdict: dict, levels_active: list | None,
          params: dict | None = None, extra: list | None = None,
          now: dt.datetime = _NOW, bar_ts: str = _BAR_ET):
    bar_ctx = {
        "timestamp_et": bar_ts,
        "bar": {"close": 734.885},                   # the real incident spot: the day's LOW
        "ribbon_now": {"stack": "BEAR", "spread_cents": 33.31337013472648},
        "vix_now": 19.05, "vix_prior": 19.0, "htf_15m_stack": "BEAR",
    }
    if levels_active is not None:
        bar_ctx["levels_active"] = list(levels_active)
    payload = {"bar_ctx": bar_ctx}
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    # zero divergence -> the sight-freshness guard never trips and never hits the network
    monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: bar_ctx["bar"]["close"])
    executed: list = []
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: (executed.append(a), {"status": "WOULD_PLACE"})[1])
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
    monkeypatch.setitem(sys.modules, "setup_dispatch", types.SimpleNamespace(
        dispatch_extra_setups=lambda *a, **k: list(extra or [])))
    routed: list = []
    monkeypatch.setattr(hc, "_route_extra_setups",
                        lambda *a, **k: (routed.append(a), [{"setup": "x", "action": "PLACED"}])[1])
    # params are read off disk per tick by run_account; pin them so the test never depends on
    # whatever automation/state/params.json currently holds.
    monkeypatch.setattr(hc.json, "loads", lambda *a, **k: dict(params if params is not None else {}))
    return logged, executed, routed


# ---- the real 2026-07-30 11:31:03 bold row, field-for-field (see module docstring) ----
_REAL_BLIND_VERDICT = {
    "verdict": "ENTER_BEAR", "side": "P",
    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    "bear_score": 8, "bull_score": 5,
    "triggers_fired": ["ribbon_flip", "trendline_rejection"],
    "bear_triggers_raw": ["ribbon_flip", "trendline_rejection"],
    "bull_triggers_raw": [],
    "rejection_level": None,                      # trigger_level_exact was null on the row
    "quality_tier": "TRENDLINE",
    "reason": ("BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates "
               "(tier TRENDLINE)"),
}


# =============================================================================
# (a) THE RED-PROOFED GUARD — today's actual row must become SKIP_NO_LEVELS
# =============================================================================
class TestBlindTrendlineOnlyEntryIsRefused:

    def test_real_2026_07_30_1131_row_is_skipped_not_entered(self, monkeypatch):
        """Byte-accurate replay of the 11:31:03 bold row that wanted to short the day's low.
        PRE-FIX this reaches _execute as ENTER_BEAR; POST-FIX it must log SKIP_NO_LEVELS
        and never touch the execution path."""
        logged, executed, _ = _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT),
                                    levels_active=[], params={})
        rec = hc.run_account("bold")
        assert rec["action"] == "SKIP_NO_LEVELS", (
            f"blind trendline-only ENTER_BEAR logged {rec['action']!r} -- the engine took "
            "its worst-performing entry mode while it could not see (2026-07-30 incident)"
        )
        assert executed == [], "a blind entry must never reach _execute"
        assert rec["blind"] is True
        # provenance: the original engine verdict stays visible (OP-33 ledger honesty)
        assert rec["blind_blocked_verdict"] == "ENTER_BEAR"
        assert "BLIND" in rec["reason"] and "no level anchor" in rec["reason"]
        assert logged and logged[-1]["action"] == "SKIP_NO_LEVELS"

    def test_verdict_field_itself_is_rewritten_so_the_fleet_cannot_enter(self, monkeypatch):
        """LOAD-BEARING, not cosmetic. build_shared_signal._map_core_row takes the fleet's
        ENTRY DECISION from this row's `verdict`, NOT its `action` -- if verdict stayed
        ENTER_BEAR, safe-2/bold-2 would be blocked here while the other fleet arms entered
        the identical blind trade off the identical ledger row."""
        _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT), levels_active=[], params={})
        rec = hc.run_account("bold")
        assert rec["verdict"] == "SKIP_NO_LEVELS"
        assert rec["side"] is None
        mapped = bss._map_core_row(rec)
        assert mapped["action"] == "SKIP_NO_LEVELS"
        assert not str(mapped["action"]).startswith("ENTER_")

    def test_blind_row_cannot_pass_any_fleet_arm_including_the_loose_tier(self):
        """The fleet's loose lane closes too. Today's row scores bear_score 8 == the
        BEAR_PEAK_THRESHOLD with trig0 'ribbon_flip' IN ENTRY_TRIGGERS, so the score-peak
        check would otherwise rate a refused blind tick as 'passed on quality alone' --
        and risky-3 ships gate_params.hard_skip_verdicts=[] (inherits no global hard skip),
        so routing this through _HARD_SKIP_VERDICTS would NOT have stopped it."""
        assert bss._score_peak_check("bear", "SKIP_NO_LEVELS", 8, "ribbon_flip", True) is False
        assert bss.passed_scoring_peak("bear", "SKIP_NO_LEVELS", 8, "ribbon_flip", True) is False
        assert bss.passed_probe_cohort("SKIP_NO_LEVELS", "ribbon_flip", True) is False
        # sanity: the same score/trigger WOULD have passed under any non-sight verdict --
        # proves the guard clause is what changed the answer (C14 vary-and-assert)
        assert bss._score_peak_check("bear", "HOLD", 8, "ribbon_flip", True) is True

    def test_blind_also_blocks_the_extra_setup_side_channel(self, monkeypatch):
        """The G4 extra-setup route is the only other order-placing path in heartbeat_core,
        and 6 of its detectors are flag-ON in params.json today. setup_dispatch builds their
        BarContext from the SAME empty levels_active, so they are blind in the literal sense
        too. Mirrors the structure_veto carve-out."""
        hold = {"verdict": "HOLD", "side": None, "setup_name": None, "bear_score": 5,
                "bull_score": 5, "triggers_fired": [],
                "reason": "no setup passed scoring (neither bear nor bull)"}
        fired = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        _, _, routed = _wire(monkeypatch, verdict=hold, levels_active=[], params={}, extra=fired)
        rec = hc.run_account("safe")
        assert rec.get("extra_exec_blocked_by") == "no_levels"
        assert routed == [], "a blind tick must not route an extra-setup entry either"

    def test_score_ladder_rescue_cannot_bypass_the_block(self, monkeypatch):
        """_apply_score_ladder runs ABOVE this branch and can rewrite HOLD -> ENTER_BEAR.
        A ladder rescue that somehow produced no anchor must still be refused when blind
        (pins that the block sits AFTER the ladder, not before it)."""
        hold = {"verdict": "HOLD", "side": None, "setup_name": None, "bear_score": 9,
                "bull_score": 2, "triggers_fired": [],
                "bear_triggers_raw": ["ribbon_flip", "trendline_rejection"],
                "bear_rejection_level_raw": None,
                "reason": "no setup passed scoring (neither bear nor bull)"}
        _, executed, _ = _wire(monkeypatch, verdict=hold, levels_active=[],
                               params={"score_ladder_floor": 7})
        rec = hc.run_account("bold")
        assert rec["action"] in ("SKIP_NO_LEVELS", "HOLD")
        assert executed == []


# =============================================================================
# (c) FAIL-CLOSED DEFAULT — the flag absent must still block
# =============================================================================
class TestFailClosedDefault:

    @pytest.mark.parametrize("params,label", [
        ({}, "key absent entirely"),
        ({"block_entries_when_blind": True}, "explicit true"),
        ({"block_entries_when_blind": None}, "null (garbage) still blocks"),
        ({"block_entries_when_blind": "false"}, "the STRING 'false' is not false"),
    ])
    def test_absent_or_non_false_flag_still_blocks(self, monkeypatch, params, label):
        _, executed, _ = _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT),
                               levels_active=[], params=params)
        rec = hc.run_account("bold")
        assert rec["action"] == "SKIP_NO_LEVELS", f"fail-closed broken for: {label}"
        assert executed == []

    def test_missing_levels_active_key_counts_as_blind(self, monkeypatch):
        """A payload that cannot even state what the engine can see must not authorize an
        entry. (Production always writes the key -- _build_payload does it unconditionally
        -- so this only ever fires on a synthetic/partial payload.)"""
        _, executed, _ = _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT),
                               levels_active=None, params={})
        rec = hc.run_account("bold")
        assert rec["action"] == "SKIP_NO_LEVELS"
        assert executed == []

    def test_explicit_false_revokes_the_rail(self, monkeypatch):
        """The documented REVOKE path: `"block_entries_when_blind": false` in params.json
        restores the exact pre-2026-07-30 behavior on the next tick (C14 vary-and-assert --
        proves the flag is load-bearing, not decorative)."""
        _, executed, _ = _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT),
                               levels_active=[], params={"block_entries_when_blind": False})
        rec = hc.run_account("bold")
        assert rec["action"] == "WOULD_PLACE"
        assert rec["verdict"] == "ENTER_BEAR"
        assert len(executed) == 1


# =============================================================================
# (b) SCOPE FENCE — levels present => byte-identical, rail ON vs OFF
# =============================================================================
_ANCHORED = {
    "level_rejection bear": dict(_REAL_BLIND_VERDICT, triggers_fired=["level_rejection", "ribbon_flip"],
                                 rejection_level=736.5),
    "confluence bear": dict(_REAL_BLIND_VERDICT, triggers_fired=["level_rejection", "confluence"],
                            rejection_level=737.0, quality_tier="ELITE"),
    "sequence bear": dict(_REAL_BLIND_VERDICT, triggers_fired=["sequence_rejection"],
                          rejection_level=735.1, quality_tier="ELITE"),
    "trendline-only bear": dict(_REAL_BLIND_VERDICT),
    "bull level_reclaim": {"verdict": "ENTER_BULL", "side": "C",
                           "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                           "bear_score": 3, "bull_score": 10,
                           "triggers_fired": ["level_reclaim", "ribbon_flip"],
                           "rejection_level": 736.2, "quality_tier": "LEVEL",
                           "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed"},
    "hold": {"verdict": "HOLD", "side": None, "setup_name": None, "bear_score": 5,
             "bull_score": 5, "triggers_fired": [],
             "reason": "no setup passed scoring (neither bear nor bull)"},
    "gate skip": dict(_REAL_BLIND_VERDICT, verdict="SKIP_VIX_BEAR_HIGH",
                      reason="blocked by entry gate vix_bear_hard_cap"),
}


class TestScopeFenceLevelsPresent:

    @pytest.mark.parametrize("name", sorted(_ANCHORED))
    def test_levels_present_is_byte_identical_rail_on_vs_off(self, monkeypatch, name):
        """THE FENCE: with levels present, the rail changes NOTHING. Every logged field is
        compared -- not just `action` -- across a spread of verdict shapes (bear level /
        confluence / sequence / TRENDLINE-only / bull reclaim / HOLD / gate-skip). The
        trendline-only case is included deliberately: with levels present it must STILL
        enter, proving the rail keys off blindness and not off the trendline tier."""
        verdict = _ANCHORED[name]
        levels = [733.0, 736.5, 741.2]

        _wire(monkeypatch, verdict=dict(verdict), levels_active=levels,
              params={"block_entries_when_blind": True})
        on = hc.run_account("bold")

        _wire(monkeypatch, verdict=dict(verdict), levels_active=levels,
              params={"block_entries_when_blind": False})
        off = hc.run_account("bold")

        assert on == off, f"rail changed a SIGHTED tick ({name}): {on} != {off}"
        assert on["blind"] is False

    def test_fhh_anchored_entry_survives_an_empty_key_level_file(self, monkeypatch):
        """SCOPE, precisely: fhh_level_rejection is computed from TODAY'S OWN BARS
        (_build_payload's first-hour-high supplement), not from key-levels.json, so it still
        fires when levels_active is empty -- and it is a genuine level-tied trigger from the
        PROFITABLE cohort. Blocking it would suppress a sighted entry and make this an edge
        change instead of a safety fix."""
        verdict = dict(_REAL_BLIND_VERDICT,
                       triggers_fired=["fhh_level_rejection", "ribbon_flip"],
                       rejection_level=738.44)
        _, executed, _ = _wire(monkeypatch, verdict=verdict, levels_active=[], params={})
        rec = hc.run_account("bold")
        assert rec["action"] == "WOULD_PLACE", (
            "an fhh-anchored entry has a real price anchor and must NOT be treated as blind"
        )
        assert rec["verdict"] == "ENTER_BEAR"
        assert rec["blind"] is True, "still flag the condition; just don't block this entry"
        assert len(executed) == 1

    def test_extra_setup_route_untouched_when_levels_present(self, monkeypatch):
        hold = {"verdict": "HOLD", "side": None, "setup_name": None, "bear_score": 5,
                "bull_score": 5, "triggers_fired": [],
                "reason": "no setup passed scoring (neither bear nor bull)"}
        fired = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        _, _, routed = _wire(monkeypatch, verdict=hold, levels_active=[736.5],
                             params={}, extra=fired)
        rec = hc.run_account("safe")
        assert "extra_exec_blocked_by" not in rec
        assert len(routed) == 1

    def test_structure_veto_attribution_is_preserved(self, monkeypatch):
        """Regression on the shared elif: a structure-veto tick with levels present must
        still be attributed to structure_veto, not to the new no_levels branch."""
        veto = dict(_REAL_BLIND_VERDICT, verdict="SKIP_STRUCTURE_VETO",
                    reason="structure-veto: P entry blocked")
        fired = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
                  "triggers": ["vwap_continuation"]}]
        _wire(monkeypatch, verdict=veto, levels_active=[736.5], params={}, extra=fired)
        rec = hc.run_account("safe")
        assert rec.get("extra_exec_blocked_by") == "structure_veto"


# =============================================================================
# telemetry — `blind` must be on EVERY row, block or no block
# =============================================================================
class TestBlindFieldAlwaysLogged:

    @pytest.mark.parametrize("levels,expected", [([], True), ([736.5], False)])
    def test_blind_boolean_present_on_every_row(self, monkeypatch, levels, expected):
        hold = {"verdict": "HOLD", "side": None, "setup_name": None, "bear_score": 5,
                "bull_score": 5, "triggers_fired": [],
                "reason": "no setup passed scoring (neither bear nor bull)"}
        logged, _, _ = _wire(monkeypatch, verdict=hold, levels_active=levels, params={})
        hc.run_account("safe")
        assert logged[-1]["blind"] is expected

    def test_blind_is_logged_even_when_the_rail_is_revoked(self, monkeypatch):
        """Evidence survives revocation: flipping the flag off must not also blind the
        ledger to the condition."""
        logged, _, _ = _wire(monkeypatch, verdict=dict(_REAL_BLIND_VERDICT), levels_active=[],
                             params={"block_entries_when_blind": False})
        hc.run_account("bold")
        assert logged[-1]["blind"] is True
        assert logged[-1]["verdict"] == "ENTER_BEAR"
