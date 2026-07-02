"""ENTRY-FLOOR guards — the 2026-07-02 09:30:03 open-tick entry discrepancy.

INCIDENT: 2026-07-02 the core engine fired ENTER_BEAR at 09:30:03 (safe) and 09:30:38
(bold) — both PLACED — despite doctrine's [09:35, 15:00) entry window and
entry_no_trade_before_et="09:35" in BOTH params files. Fleet safe-1 entered 09:31:01
off the same fanned-out verdict.

ROOT CAUSE (one sentence, C14-variant "enforced-against-the-wrong-clock"):
    entry_no_trade_before_et IS forwarded (heartbeat_core.py:444) and parsed
    (engine_cli.py:331-332), but filter-1 enforces it against the TRIGGER BAR's own
    timestamp (filters.py:1073-1077 bear / 848-852 bull) — and at the market-open ticks
    the trigger bar (2nd-to-last fetched 5m bar) is still the PRIOR DAY's 15:50/15:55
    bar, so the 09:35 floor structurally cannot fire, and yesterday's after-ceiling
    ENTER_BEAR signal (ceiling-blocked 15:53-15:55 on 07-01) executed at today's open.

EVIDENCE (verified 2026-07-02 ~11:20 ET):
  * core-decisions.jsonl 09:30:03/09:30:38 rows: spy=746.26 = the 2026-07-01 15:50 ET
    bar close (Alpaca IEX, verified); 09:31-09:35 ticks show spy=745.665 = 07-01 15:55
    close; the 09:36 tick shows spy=748.56 = 07-02 09:30 close. The `spy` field is the
    trigger-bar close -> the 09:30 ENTER was scored ENTIRELY on yesterday's bars.
  * Same setup/score as yesterday's 15:53-15:55 ceiling-blocked verdicts
    (ENTER_BEAR / trendline_rejection / bear_score 9): the open tick is the one moment
    a stale after-hours signal escapes BOTH time gates — bar-time 15:50 passes the
    floor, wall-clock 09:30 passes the ceiling (FIX1 checks wall-clock, floor doesn't).
  * fleet_live.py has a wall-clock CEILING mirror (line ~215) but NO floor mirror, and
    build_shared_signal._map_core_row derives `passed` from the VERDICT (not action),
    so a core-side skip alone cannot stop the fleet.

STAGED FIX (apply after close — see markdown/audits/ENTRY-FLOOR-FIX-PLAN-2026-07-02.md):
  1. heartbeat_core._before_entry_floor(params, now_et)  — wall-clock floor mirror of
     _past_entry_ceiling; fail-closed default 09:35.
  2. heartbeat_core._stale_trigger_bar(payload, now_et)  — ENTER only actionable when
     the trigger bar is from TODAY's session; fail-closed (malformed ts = stale).
  3. Both wired in run_account (before free-model eval) + _execute (belt-and-suspenders,
     covers the extra-setup G4 route) — exactly the FIX1 ceiling pattern.
  4. fleet_live._before_entry_floor mirror wired in _place_live.
  5. build_shared_signal._map_core_row: rows whose action is a brain-level time-gate
     skip (SKIP_EARLY_ENTRY / SKIP_STALE_TRIGGER / SKIP_LATE_ENTRY) map to HOLD so the
     fleet never sees passed=true on a time-gated verdict.

Part A (evidence pins) pass TODAY and keep passing. Part B (fix guards) skip until the
patch lands, then arm automatically (hasattr detection). The strict-xfail sentinel
FORCES the apply commit to delete its marker — a fix that lands without arming these
guards turns the suite RED (no silent-skip-forever, C7).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_floor_2026_07_02.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import json
import sys
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

from lib.filters import (  # noqa: E402
    BarContext,
    RibbonState,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
BOLD_PARAMS_PATH = ROOT / "automation" / "state" / "aggressive" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
CORE_LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"

hc = importlib.import_module("heartbeat_core")
fl = importlib.import_module("fleet_live")
bss = importlib.import_module("build_shared_signal")

FLOOR_APPLIED = hasattr(hc, "_before_entry_floor")
STALE_APPLIED = hasattr(hc, "_stale_trigger_bar")
FLEET_FLOOR_APPLIED = hasattr(fl, "_before_entry_floor")
BSS_APPLIED = hasattr(bss, "_TIME_GATE_SKIPS")
_NOT_APPLIED = "entry-floor patch not applied yet (staged: markdown/audits/ENTRY-FLOOR-FIX-PLAN-2026-07-02.md)"

ET = dt.timezone(dt.timedelta(hours=-4))  # July = EDT; test data only, never wall-clock


# --------------------------------------------------------------------------- #
# ctx builders (parity-test pattern, test_engine_cli_parity.py:78-94)
# --------------------------------------------------------------------------- #
def _bear_ribbon() -> RibbonState:
    return RibbonState(fast=745.0, pivot=746.0, slow=747.0, spread_cents=50.0, stack="BEAR")


def _prior_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [{"open": 746.0, "high": 746.4, "low": 745.6, "close": 746.0, "volume": 800_000}
         for _ in range(30)]
    )


def _bear_ctx(ts: dt.datetime) -> BarContext:
    """Minimal bear BarContext at an arbitrary trigger-bar timestamp."""
    bar = pd.Series({"open": 746.5, "high": 747.0, "low": 745.9, "close": 746.26,
                     "volume": 900_000})
    return BarContext(
        bar_idx=4, timestamp_et=ts, bar=bar, prior_bars=_prior_bars(),
        ribbon_now=_bear_ribbon(), ribbon_history=[_bear_ribbon()],
        vix_now=17.5, vix_prior=17.3,
        vol_baseline_20=1_000_000.0, range_baseline_20=1.0,
        levels_active=[746.8], multi_day_levels=[], htf_15m_stack="BEAR",
        level_states={},
    )


# =============================================================================
# Part A — EVIDENCE PINS (pass today; pin the diagnosed mechanism)
# =============================================================================
class TestEvidenceKnobExists:
    """The knob is NOT dead-at-source: present in both params files, parsed by engine_cli."""

    @pytest.mark.parametrize("params,name", [(SAFE_PARAMS, "safe"), (BOLD_PARAMS, "bold")])
    def test_params_floor_is_0935_both_accounts(self, params, name):
        raw = params.get("entry_no_trade_before_et")
        assert raw == "09:35", f"{name} entry_no_trade_before_et is {raw!r}, doctrine says 09:35"

    def test_engine_cli_parses_floor_string(self):
        from lib.engine.engine_cli import _coerce_score_kwargs
        out = _coerce_score_kwargs({"no_trade_before": "09:35"}, "test")
        assert out["no_trade_before"] == dt.time(9, 35)

    def test_heartbeat_forwards_floor_to_both_sides(self):
        """heartbeat_core._build_payload forwards entry_no_trade_before_et into the
        bear_kwargs AND bull_kwargs the engine scores with (the C14 half that is OK)."""
        src = inspect.getsource(hc._build_payload)
        assert "entry_no_trade_before_et" in src
        assert "bear_kwargs" in src and "bull_kwargs" in src


class TestEvidenceFloorReadsBarTimeNotWallClock:
    """THE mechanism: filter-1 compares the floor to the TRIGGER BAR timestamp.
    A prior-day 15:50 trigger bar sails through the 09:35 floor; a same-day 09:31
    trigger bar is blocked. Neither call knows (or checks) the wall clock."""

    def test_prior_day_1550_trigger_passes_floor_bear(self):
        ts = dt.datetime(2026, 7, 1, 15, 50, tzinfo=ET)  # yesterday's bar
        r = evaluate_bearish_setup(_bear_ctx(ts), no_trade_before=dt.time(9, 35))
        assert 1 not in r.blockers, (
            "filter-1 blocked a 15:50 bar?! (floor semantics changed — update this pin)"
        )

    def test_same_day_0931_trigger_is_blocked_bear(self):
        ts = dt.datetime(2026, 7, 2, 9, 31, tzinfo=ET)
        r = evaluate_bearish_setup(_bear_ctx(ts), no_trade_before=dt.time(9, 35))
        assert 1 in r.blockers, "filter-1 must block a same-day 09:31 trigger bar"

    def test_prior_day_1550_trigger_passes_floor_bull(self):
        ts = dt.datetime(2026, 7, 1, 15, 50, tzinfo=ET)
        r = evaluate_bullish_setup(_bear_ctx(ts), no_trade_before=dt.time(9, 35))
        assert 1 not in r.blockers

    def test_filter1_source_uses_ctx_timestamp(self):
        """Pin the exact comparison: bar_time = ctx.timestamp_et.time() (filters.py:1073).
        If this ever changes to a wall-clock read, the backtest breaks — the LIVE fix
        belongs in heartbeat_core/fleet_live, never here."""
        src = inspect.getsource(evaluate_bearish_setup)
        assert "bar_time = ctx.timestamp_et.time()" in src


class TestEvidenceIncidentLedger:
    """Executable record of the incident rows (soft pin — skips if ledger pruned)."""

    def test_0930_enters_recorded_2026_07_02(self):
        if not CORE_LEDGER.exists():
            pytest.skip("core-decisions.jsonl absent (retention prune)")
        rows = []
        for line in CORE_LEDGER.read_text(encoding="utf-8").splitlines():
            if '"2026-07-02T09:3' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("ts_et", "")).startswith("2026-07-02T09:3"):
                rows.append(r)
        if not rows:
            pytest.skip("2026-07-02 09:3x rows pruned from ledger")
        enters = [r for r in rows if r.get("verdict") == "ENTER_BEAR"
                  and r.get("ts_et", "") < "2026-07-02T09:35:00"]
        assert len(enters) == 2, "incident record: exactly safe@09:30:03 + bold@09:30:38"
        assert all(r.get("action") == "PLACED" for r in enters)
        # spy=746.26 == the 2026-07-01 15:50 ET bar close -> trigger bar was yesterday's
        assert all(abs(float(r.get("spy", 0)) - 746.26) < 1e-6 for r in enters)


# =============================================================================
# Part B — FIX GUARDS (skip until applied; arm automatically; RED on regression)
# =============================================================================
class TestFixAppliedSentinel:
    """strict xfail: XFAIL (green) while the patch is staged; XPASS (RED) the moment
    the fix lands — forcing the apply commit to delete this marker, which proves the
    hasattr-gated guards below actually armed. Apply-plan step 6 removes the marker."""

    def test_fix_is_applied(self):
        assert FLOOR_APPLIED and STALE_APPLIED and FLEET_FLOOR_APPLIED and BSS_APPLIED


@pytest.mark.skipif(not FLOOR_APPLIED, reason=_NOT_APPLIED)
class TestCoreWallClockFloor:
    @pytest.mark.parametrize("hh,mm,expected", [
        (9, 30, True),    # today's incident minute
        (9, 34, True),
        (9, 35, False),   # window is [09:35, 15:00) — 09:35 itself trades
        (12, 0, False),
    ])
    def test_floor_boundaries(self, hh, mm, expected):
        now = dt.datetime(2026, 7, 2, hh, mm)
        assert hc._before_entry_floor(SAFE_PARAMS, now) is expected

    def test_floor_fail_closed_defaults(self):
        early = dt.datetime(2026, 7, 2, 9, 34)
        assert hc._before_entry_floor({}, early) is True                        # missing key
        assert hc._before_entry_floor({"entry_no_trade_before_et": "xx"}, early) is True
        assert hc._before_entry_floor(None, early) is True                      # not a dict

    def test_run_account_wires_floor(self):
        assert "_before_entry_floor" in inspect.getsource(hc.run_account)

    def test_execute_wires_floor(self):
        assert "_before_entry_floor" in inspect.getsource(hc._execute)


@pytest.mark.skipif(not STALE_APPLIED, reason=_NOT_APPLIED)
class TestCoreStaleTriggerBar:
    def _payload(self, ts_iso: str) -> dict:
        return {"bar_ctx": {"timestamp_et": ts_iso}}

    def test_prior_day_trigger_is_stale(self):
        now = dt.datetime(2026, 7, 2, 9, 30, 3)
        assert hc._stale_trigger_bar(self._payload("2026-07-01T15:50:00-04:00"), now) is True

    def test_same_day_trigger_is_fresh(self):
        now = dt.datetime(2026, 7, 2, 10, 15)
        assert hc._stale_trigger_bar(self._payload("2026-07-02T10:05:00-04:00"), now) is False

    def test_malformed_fails_closed(self):
        now = dt.datetime(2026, 7, 2, 10, 15)
        assert hc._stale_trigger_bar({}, now) is True
        assert hc._stale_trigger_bar({"bar_ctx": {}}, now) is True
        assert hc._stale_trigger_bar(None, now) is True

    def test_run_account_wires_staleness(self):
        assert "_stale_trigger_bar" in inspect.getsource(hc.run_account)

    def test_execute_wires_staleness(self):
        assert "_stale_trigger_bar" in inspect.getsource(hc._execute)


@pytest.mark.skipif(not FLEET_FLOOR_APPLIED, reason=_NOT_APPLIED)
class TestFleetFloorMirror:
    @pytest.mark.parametrize("hh,mm,expected", [
        (9, 31, True),    # fleet's actual entry minute today
        (9, 35, False),
        (10, 0, False),
    ])
    def test_fleet_floor_boundaries(self, hh, mm, expected):
        now = dt.datetime(2026, 7, 2, hh, mm)
        assert fl._before_entry_floor(SAFE_PARAMS, now) is expected

    def test_place_live_wires_floor(self):
        assert "_before_entry_floor" in inspect.getsource(fl._place_live)


@pytest.mark.skipif(not BSS_APPLIED, reason=_NOT_APPLIED)
class TestSharedSignalTimeGateSkips:
    """A brain-level time-gate skip must never fan out to the fleet as passed=true."""

    _ROW = {"verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "bear_score": 9, "bull_score": 8, "triggers": ["trendline_rejection"],
            "ts_et": "2026-07-02T09:30:03", "spy": 746.26, "vix": 16.22,
            "ribbon": "BEAR", "spread_cents": 38.3, "htf_15m": "MIXED"}

    @pytest.mark.parametrize("skip", ["SKIP_EARLY_ENTRY", "SKIP_STALE_TRIGGER", "SKIP_LATE_ENTRY"])
    def test_time_gate_skip_maps_to_hold(self, skip):
        mapped = bss._map_core_row(dict(self._ROW, action=skip))
        assert not str(mapped["action"]).startswith("ENTER"), (
            f"a {skip} row fanned out to the fleet as {mapped['action']}"
        )

    def test_placed_row_still_maps_to_enter(self):
        mapped = bss._map_core_row(dict(self._ROW, action="PLACED"))
        assert mapped["action"] == "ENTER_BEAR"

    def test_place_fail_still_maps_to_enter(self):
        """PLACE_FAIL is execution noise, not a brain decision — the 2026-06-25
        verdict-not-action redirect must survive this patch (fleet arms may legitimately
        succeed where the core's broker call failed)."""
        mapped = bss._map_core_row(dict(self._ROW, action="PLACE_FAIL"))
        assert mapped["action"] == "ENTER_BEAR"
