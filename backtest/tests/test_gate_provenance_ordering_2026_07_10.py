"""GATE-PROVENANCE ORDERING guard (2026-07-10) — staleness must be resolved BEFORE any
verdict/gate name can claim a tick's logged action.

INCIDENT (markdown/audits/GATE-PROVENANCE-SWEEP-2026-07-10.md): evaluate_gates() (the 15
GATE_ORDER gates, run inside _engine_verdict's engine_cli subprocess call) scores + gates
the payload's trigger bar regardless of whether that bar is from TODAY's session. At the
open, a carried-over prior-session bar can satisfy a GATE_ORDER time-window gate's own
predicate (block_conf_lvl_rec_afternoon's `bt.time() >= 14:00` reads TRUE for a bar
legitimately timestamped 15:55 ET *yesterday*) and return a named SKIP_* verdict that reads
as a live block. heartbeat_core.py's OWN _stale_trigger_bar guard only ever re-checked
staleness when the raw engine_cli verdict was ALREADY ENTER_BEAR/ENTER_BULL — a
gate-produced SKIP_* (or a HOLD) fell straight through to the `else: rec["action"] = v`
branch and was logged under the gate's own name instead.

PROOF (real 2026-07-10 rows, automation/state/core-decisions.jsonl:7947/7954 — byte-quoted):
  09:31:03 safe verdict=ENTER_BULL             action=SKIP_STALE_TRIGGER  trigger_bar_et=2026-07-09T15:55:00-04:00
  09:34:04 bold verdict=SKIP_CONF_LVL_REC_AFTERNOON  action=SKIP_CONF_LVL_REC_AFTERNOON  (no trigger_bar_et key at all)
  Both rows: spy=751.55, vix~15.7, triggers=[level_reclaim,ribbon_flip,confluence] — the
  SAME underlying stale bar, two different (and for bold, WRONG) attributions.

FIX: run_account's post-verdict ladder (heartbeat_core.py) now checks _stale_trigger_bar
FIRST, unconditional on the raw verdict `v` — search "GATE-PROVENANCE-SWEEP" in
heartbeat_core.py. gates.py / engine_cli.py are untouched (see that comment for why: they
are the shared, pure, backtest-reused decision core — "staleness vs wall-clock" has no
backtest equivalent, so threading it in there would risk backtest determinism for no
benefit; heartbeat_core.py's live-only post-verdict ladder is the correct and only seam).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_gate_provenance_ordering_2026_07_10.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
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


# =============================================================================
# harness — mirrors test_money_path_2026_07_01.py::TestEntryCeiling._wire_run_account,
# extended so the trigger bar's OWN timestamp (bar_ts) can be varied independently of the
# wall clock (now) — the money-path harness always keeps them matched (fresh); this one
# needs to deliberately mismatch them to reproduce the incident.
# =============================================================================
def _wire(monkeypatch, *, now: dt.datetime, bar_ts: str, verdict: dict):
    payload = {"bar_ctx": {
        "timestamp_et": bar_ts,
        "bar": {"close": 751.55},
        "ribbon_now": {"stack": "BULL", "spread_cents": 47.77194042433166},
        "vix_now": 15.73, "vix_prior": 15.74, "htf_15m_stack": "BULL",
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


# the exact 2026-07-10 09:34:04 bold row, verified against
# automation/state/core-decisions.jsonl:7954 (see module docstring PROOF section).
_REAL_STALE_BAR_ET = "2026-07-09T15:55:00-04:00"
_REAL_NOW_ET = dt.datetime(2026, 7, 10, 9, 34, 4)
_REAL_GATE_VERDICT = {
    "verdict": "SKIP_CONF_LVL_REC_AFTERNOON", "side": "C",
    "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "bear_score": 4, "bull_score": 11,
    "triggers_fired": ["level_reclaim", "ribbon_flip", "confluence"],
    "reason": "blocked by entry gate block_conf_lvl_rec_afternoon",
    "rejection_level": 751.19,
}


# =============================================================================
# THE red-proofed regression guard: RED pre-fix (gate name wins), GREEN post-fix
# (staleness wins, whatever the raw verdict/gate name says).
# =============================================================================
class TestGateNameNeverClaimsAStaleTick:

    def test_real_2026_07_10_bold_row_reproduced_then_fixed(self, monkeypatch):
        """Byte-accurate replay of the real contaminated row. Pre-fix this logs
        SKIP_CONF_LVL_REC_AFTERNOON (the bug); post-fix it must log SKIP_STALE_TRIGGER."""
        logged = _wire(monkeypatch, now=_REAL_NOW_ET, bar_ts=_REAL_STALE_BAR_ET,
                       verdict=dict(_REAL_GATE_VERDICT))
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER", (
            f"gate name {rec['action']!r} claimed a prior-session bar instead of "
            "SKIP_STALE_TRIGGER -- GATE-PROVENANCE-SWEEP-2026-07-10 regression"
        )
        assert rec["trigger_bar_et"] == _REAL_STALE_BAR_ET
        # verdict passthrough is UNCHANGED -- provenance (what the gate WOULD have said)
        # stays visible in the verdict field, exactly like the real SAFE row's ENTER_BULL
        # stays visible in `verdict` even though its `action` is SKIP_STALE_TRIGGER.
        assert rec["verdict"] == "SKIP_CONF_LVL_REC_AFTERNOON"
        assert logged and logged[-1]["action"] == "SKIP_STALE_TRIGGER"

    @pytest.mark.parametrize("gate_name,reason", [
        ("SKIP_CONF_LVL_REC_AFTERNOON", "blocked by entry gate block_conf_lvl_rec_afternoon"),
        ("SKIP_BULL_1100_1200", "blocked by entry gate block_bull_1100_1200"),
        ("SKIP_ELITE_BULL_LEVEL_RECLAIM", "blocked by entry gate block_elite_bull"),
        ("SKIP_MIDDAY_TRENDLINE_GATE", "blocked by entry gate midday_trendline_gate"),
        ("SKIP_VIX_BEAR_HIGH", "blocked by entry gate vix_bear_hard_cap"),
    ])
    def test_every_gate_order_name_yields_to_staleness(self, monkeypatch, gate_name, reason):
        """Sweep a representative sample spanning GATE_ORDER (not just the one gate that
        fired live 07-10) -- ALL must yield to SKIP_STALE_TRIGGER on a stale bar. Guards
        against a fix that special-cases only the one gate seen in the wild."""
        verdict = dict(_REAL_GATE_VERDICT, verdict=gate_name, reason=reason)
        _wire(monkeypatch, now=_REAL_NOW_ET, bar_ts=_REAL_STALE_BAR_ET, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER"

    def test_hold_on_a_stale_bar_also_yields_to_staleness(self, monkeypatch):
        """A stale-bar HOLD is exactly as untrustworthy as a stale-bar gate-skip -- scoring
        ran on yesterday's bar either way, and decide_payload returns HOLD BEFORE
        evaluate_gates even runs (no side won). Pins the broader (and correct) reading of
        'no gate can claim the tick': staleness precedes EVERY ladder branch, not only the
        15 named gates."""
        verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
                   "bear_score": 5, "bull_score": 5, "triggers_fired": [],
                   "reason": "no setup passed scoring (neither bear nor bull)"}
        _wire(monkeypatch, now=_REAL_NOW_ET, bar_ts=_REAL_STALE_BAR_ET, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER"

    def test_g4_extra_setup_dispatch_survives_staleness_relabel(self, monkeypatch):
        """CAUGHT DURING THIS FIX'S OWN VERIFICATION (real regression, not hypothetical):
        the first version of the reorder made the new staleness `if` a hard short-circuit
        ahead of the WHOLE ladder, which accidentally ALSO skipped the G4 extra-setup
        dispatch block (it used to live inside the ladder's `else:` clause). G4 detectors
        read their own same-day-bars slice, independent of the CORE ribbon path's trigger
        bar -- their routing must be unaffected by _stale_trigger_bar. Pins: a stale-bar
        HOLD/gate-skip still routes a fired+armed extra setup exactly as it did pre-fix
        (see test_g4_extra_setup_routing.py for the sibling non-stale coverage)."""
        verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
                   "bear_score": 5, "bull_score": 5, "triggers_fired": [],
                   "reason": "no setup passed scoring (neither bear nor bull)"}
        logged = _wire(monkeypatch, now=_REAL_NOW_ET, bar_ts=_REAL_STALE_BAR_ET, verdict=verdict)
        monkeypatch.setitem(sys.modules, "setup_dispatch", types.SimpleNamespace(
            dispatch_extra_setups=lambda *a, **k: [{"setup_name": "bollinger_squeeze", "fired": True,
                                                     "direction": "long", "triggers": ["squeeze_break"]}]))
        routed = {"n": 0}
        monkeypatch.setattr(
            hc, "_route_extra_setups",
            lambda *a, **k: (routed.__setitem__("n", routed["n"] + 1),
                              [{"setup": "bollinger_squeeze", "action": "PLACED"}])[1],
        )
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER", "the fix under test must still relabel the action"
        assert routed["n"] == 1, "G4 extra-setup dispatch must NOT be suppressed by the staleness relabel"
        assert rec.get("extra_exec") == [{"setup": "bollinger_squeeze", "action": "PLACED"}]

    def test_enter_on_a_stale_bar_still_yields_to_staleness(self, monkeypatch):
        """The ALREADY-correct case (this is the real SAFE row's shape) must keep working
        post-fix: an ENTER_* verdict on a stale bar was already caught pre-fix -- byte-
        identical row shape (action + trigger_bar_et; verdict left as the raw ENTER_*)."""
        verdict = {"verdict": "ENTER_BULL", "side": "C",
                   "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                   "bear_score": 4, "bull_score": 11,
                   "triggers_fired": ["level_reclaim", "ribbon_flip", "confluence"],
                   "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
                   "rejection_level": 751.19}
        _wire(monkeypatch, now=_REAL_NOW_ET, bar_ts=_REAL_STALE_BAR_ET, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER"
        assert rec["verdict"] == "ENTER_BULL"
        assert rec["trigger_bar_et"] == _REAL_STALE_BAR_ET


# =============================================================================
# fresh-bar vary-and-assert tape — the OTHER half of the fix's constraint: a bar that
# genuinely IS today's must be a complete no-op for this reorder.
# =============================================================================
class TestFreshBarByteIdenticalTape:

    _FRESH_NOW = dt.datetime(2026, 7, 10, 11, 0, 0)
    # heartbeat_core always feeds bar_ctx timestamps in "%Y-%m-%d %H:%M:%S" live (see
    # _build_payload) -- match that format here rather than the ISO variant
    # TestCoreStaleTriggerBar's unit tests already cover, so this tape mirrors production.
    _FRESH_BAR_TS = "2026-07-10 11:00:00"

    @pytest.mark.parametrize("verdict_name,reason", [
        ("HOLD", "no setup passed scoring (neither bear nor bull)"),
        ("SKIP_CONF_LVL_REC_AFTERNOON", "blocked by entry gate block_conf_lvl_rec_afternoon"),
        ("SKIP_BULL_1100_1200", "blocked by entry gate block_bull_1100_1200"),
        ("SKIP_STRUCTURE_VETO", "structure-veto: C entry blocked -- price structure is 'downtrend'"),
    ])
    def test_fresh_non_enter_verdict_passes_through_unchanged(self, monkeypatch, verdict_name, reason):
        verdict = {"verdict": verdict_name, "side": None, "setup_name": None,
                   "bear_score": 5, "bull_score": 5, "triggers_fired": [], "reason": reason}
        _wire(monkeypatch, now=self._FRESH_NOW, bar_ts=self._FRESH_BAR_TS, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == verdict_name, "a FRESH bar must never be relabeled SKIP_STALE_TRIGGER"
        assert "trigger_bar_et" not in rec

    def test_fresh_enter_still_executes(self, monkeypatch):
        verdict = {"verdict": "ENTER_BULL", "side": "C",
                   "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                   "bear_score": 4, "bull_score": 11,
                   "triggers_fired": ["level_reclaim", "ribbon_flip", "confluence"],
                   "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)"}
        _wire(monkeypatch, now=self._FRESH_NOW, bar_ts=self._FRESH_BAR_TS, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == "WOULD_PLACE"
        assert "trigger_bar_et" not in rec

    @pytest.mark.parametrize("hh,mm,expected_action", [
        (15, 30, "SKIP_LATE_ENTRY"),   # past ceiling
        (9, 30, "SKIP_EARLY_ENTRY"),   # before floor
    ])
    def test_fresh_enter_ceiling_and_floor_unaffected_by_reorder(self, monkeypatch, hh, mm, expected_action):
        """The reorder inserts staleness ABOVE ceiling/floor in the ladder -- confirm a
        FRESH bar's ceiling/floor verdicts are byte-identical after the reorder (they were
        never gated on staleness to begin with; this re-confirms nothing else shifted)."""
        now = dt.datetime(2026, 7, 10, hh, mm)
        bar_ts = now.strftime("%Y-%m-%d %H:%M:%S")
        verdict = {"verdict": "ENTER_BEAR", "side": "P",
                   "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "bear_score": 9, "bull_score": 2,
                   "triggers_fired": ["level_rejection"], "reason": "test"}
        _wire(monkeypatch, now=now, bar_ts=bar_ts, verdict=verdict)
        rec = hc.run_account("safe")
        assert rec["action"] == expected_action


class TestSourceOrdering:
    """Structural pin: the staleness check must textually precede the ENTER-ceiling check
    inside run_account's source, so a future edit can't silently re-sink it below a gate
    branch again without this test catching the reorder."""

    def test_stale_check_precedes_ceiling_check_in_source(self):
        src = inspect.getsource(hc.run_account)
        # Scope to the POST-VERDICT LADDER only (from `v = verdict.get("verdict"` onward) --
        # _stale_trigger_bar's FIRST appearance in the whole function is the unrelated
        # CORE_MANAGES_EXITS structure-stop call (an earlier, independent use of the same
        # helper), which would make this pin trivially true for the wrong reason if not
        # scoped. Confirmed empirically pre-fix: the naive whole-function search finds that
        # earlier call and reports "already ordered" even on the unfixed ladder.
        ladder_start = src.index('v = verdict.get("verdict"')
        ladder = src[ladder_start:]
        i_stale = ladder.index("_stale_trigger_bar(payload, et)")
        i_ceiling = ladder.index("_past_entry_ceiling(params, et)")
        assert i_stale < i_ceiling, (
            "_stale_trigger_bar must be checked BEFORE _past_entry_ceiling in run_account's "
            "post-verdict ladder -- GATE-PROVENANCE-SWEEP-2026-07-10 requires staleness to "
            "win first"
        )
