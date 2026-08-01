"""vix_regime_gate_archetype_fate_2026_08_02.py -- measure what FILTER 8 (the VIX-regime
gate) costs, archetype-conditionally, then decide its fate on evidence.

FROZEN PRE-REG: analysis/recommendations/prereg-vix-regime-gate-archetype-2026-08-02.json
(VIX-REGIME-GATE-ARCHETYPE-PARTICIPATION-2026-08-02, frozen 2026-08-01 16:53:48 ET, BEFORE
this file existed). Read that file for the hypothesis, arms, cohorts, gates and ship rule;
this module is the RUNNER, not a second copy of the spec. Structural template:
backtest/tools/filter5_ribbon_fate_2026_07_31.py (same population, same exit walk, same
G1-G5 gate math, same OPRA-measurability honesty layer) -- reused deliberately, not
reinvented, per this repo's own convention.

WHY THIS EXISTS: analysis/deep-research/REGIME-PARTICIPATION-2026-08-02.md found
GATE_BLOCKED[filter_8] is the single largest blocker in EVERY ONE of 8 day-archetypes
without exception (121/389 days, 31.1%, oracle-bound +$26,547) -- the biggest single
"the engine saw it and refused" surface in the whole engine. The ONLY prior research on
this exact gate (8 scripts, 2026-05-19) is DISQUALIFIED: it summed P&L directly off
run_backtest()'s raw trade objects, never re-deriving through the real exit_manager_walk
-- exactly the KNOWN-DIVERGENT simulate_trade_real-shaped path this repo's newer tooling
exists to correct (best-config headline $107,859-$111,254 vs this engine's real validated
18-month total of $4,808.75, a >20x gap). None of those 8 files' numbers are cited here.

WHAT FILTER 8 IS (read from backtest/lib/filters.py this session, verified live via
inspect.signature -- see `vary_and_assert` below, not assumed from memory):
  BULL (filters.py:1190-1195): vix_pass = vix_now < 17.20 OR vix_direction == "falling";
    not vix_pass -> blockers.append(8). NO vix_soft_mode parameter exists on
    evaluate_bullish_setup AT ALL (confirmed via inspect.signature) -- bull-side filter 8
    has NO soft-mode escape valve of any kind, ever. disable_filters=[8] is the only lever.
  BEAR (filters.py:1506-1528): vix_pass = vix_now > 17.30 AND vix_direction == "rising"
    (VIX_HARD_CAP_BEAR=999.0 and VIX_DECLINING_REQUIRED_BEAR=False are both currently OFF
    in production, verified by reading the constants, so those two sub-conditions never
    fire and the live rule reduces to exactly the stated vix_pass expression); when
    vix_soft_mode=True and vix_pass is False, sets vix_soft_demerit=True (-1 score
    modifier) INSTEAD OF blockers.append(8) -- a soft demerit, not a hard veto.

METHOD (two arms, one shared population, real exits -- ARM_C bull-side-soft is explicitly
NOT attempted per the prereg's no-new-knobs discipline; it would require a genuinely new
code path):
  CONTROL      run_backtest(**SAFE_BASE_LIVE) -- live production config, unchanged.
  ARM_A_soft   CONTROL + vix_soft_mode=True. BEAR-SIDE ONLY (bull has no such parameter).
               Zero new code -- vix_soft_mode is ALREADY a first-class run_backtest kwarg,
               already threaded to both the direct scoring call AND the internal
               _ENGINE_SCORE_ASSERT parity-oracle call (orchestrator.py:996/1047) -- so
               unlike filter5's ARM_B (a brand-new kwarg that needed monkeypatch
               injection), this arm needs NO monkeypatching at all; a plain kwarg suffices
               and cannot desync the two internal scoring paths.
  ARM_B_delete CONTROL + disable_filters=[8]. SYMMETRIC across both sides -- filter 8
               removed entirely from both evaluate_bullish_setup and evaluate_bearish_setup,
               no demerit either. Also a first-class native run_backtest kwarg already.

CAPTURE (CONTROL only): every scored bar (either side) whose blockers == [8] EXACTLY is
recorded via a PURE PASS-THROUGH monkeypatch of evaluate_bearish_setup / evaluate_bullish_
setup in BOTH `lib.orchestrator` and `lib.engine.score` (same dual-binding technique
filter5_ribbon_fate_2026_07_31.py uses for its own cohort-A capture, including the
timestamp-keyed dedupe that fixes that script's own shipped 2x bar-count inflation --
Blockers8Capture below is that same fix, applied fresh, not re-discovered the hard way).

EXITS: every entry in every arm is re-walked through the REAL live exit core
(lib/exit_manager_walk.walk_exit_manager driving automation/state/fleet/exit_manager.py's
plan_exit_actions under the RIBBON_RIDE registry exit shape). Each arm's own run_backtest
`dollar_pnl` is DISCARDED -- simulate_trade_real is known-divergent from the live exit
manager. entry+1 convention is enforced by walk_exit_manager itself (first bar STRICTLY
after entry).

P&L: real cached OPRA contracts ONLY. Contracts with no cached CSV are excluded and
COUNTED per arm; nothing is Black-Scholes-synthesized into a total.

G6 (archetype participation, REPORTED NOT GATING): every trade tagged via
lib.regime_slice.load_library against analysis/regime-library/day-archetypes.json (WS6,
spec 1.0.0), aggregated with regime_participation_study.performance_by_archetype (REUSED,
not reimplemented -- that function is already guarded by
backtest/tests/test_regime_participation_study.py, 18 tests).

Run: backtest/.venv/Scripts/python.exe backtest/tools/vix_regime_gate_archetype_fate_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
import random
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- SAFE_BASE_LIVE, ribbon lookup, TIME_STOP_ET
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- entry_date, classify_tier
import strategies as fleet_strategies  # noqa: E402
import lib.orchestrator as orch_mod  # noqa: E402
import lib.engine.score as score_mod  # noqa: E402 -- holds its OWN by-name bindings (score.py:66)
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import CACHE_DIR, load_contract_bars, option_symbol  # noqa: E402
from lib.filters import BarContext, evaluate_bearish_setup, evaluate_bullish_setup  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402
from lib.regime_slice import load_library  # noqa: E402
from regime_participation_study import performance_by_archetype  # noqa: E402 -- G6, reused

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
NEW_VIX = DATA / "vix_5m_2026-05-19_2026-07-31.csv"
OLD_WINDOW_END = dt.date(2026, 7, 22)
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-vix-regime-gate-archetype-2026-08-02.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "vix-regime-gate-archetype-2026-08-02.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "vix-regime-gate-archetype-2026-08-02.md"
ARCHETYPE_LIBRARY = ROOT / "analysis" / "regime-library" / "day-archetypes.json"

RECENT_TRADING_DAYS = 25           # backtest/autoresearch/recency_check.py convention
RUNNER_NO_REGRESSION_FLOOR = 0.95  # G4
FIRE_FLOOR_FULL = 10               # G5
FIRE_FLOOR_RECENT = 2              # G5
N_PERMS = 20_000                   # BH-FDR advisory -- matches trendline_context_conditioning
SEED = 42                          # _2026_08_01.py's own convention (20k perms, Random(42))
Q_STAR = 0.10                      # prereg's stated alpha


def log(msg: str) -> None:
    print(f"[vix8-fate] {msg}", flush=True)


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


# ============================================================== vary-and-assert (requirement 1)

def _probe_bar(open_=540.5, high=541.5, low=539.5, close=540.3, volume=900_000) -> pd.Series:
    return pd.Series({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def _probe_prior_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [{"open": 540.0, "high": 540.4, "low": 539.6, "close": 540.0, "volume": 800_000}
         for _ in range(30)]
    )


def _probe_bear_ctx(vix_now: float, vix_prior: float) -> BarContext:
    """Isolates filter 8 -- every OTHER filter is built to pass cleanly (BEAR-stacked
    ribbon, 50c spread, level active, 10:00 ET, calm volume) so blockers == [8] exactly
    when vix_pass is False. Mirrors backtest/tests/test_engine_score_parity.py's own
    `_bear_ctx` fixture shape (that file's "vix_falling" case uses these exact VIX values)."""
    ts = dt.datetime.fromisoformat("2026-05-20 10:00:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    ribbon = RibbonState(fast=539.0, pivot=540.0, slow=541.0, spread_cents=50.0, stack="BEAR")
    return BarContext(
        bar_idx=4, timestamp_et=ts, bar=_probe_bar(), prior_bars=_probe_prior_bars(),
        ribbon_now=ribbon, ribbon_history=[ribbon], vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=1_000_000.0, range_baseline_20=1.0, levels_active=[540.8],
        multi_day_levels=[], htf_15m_stack="BEAR", level_states={},
    )


def _probe_bull_ctx(vix_now: float, vix_prior: float) -> BarContext:
    """Mirrors test_engine_score_parity.py's `_bull_ctx` -- BULL-stacked ribbon, green bar,
    level active, everything else clean so blockers == [8] exactly when vix_pass is False."""
    ts = dt.datetime.fromisoformat("2026-05-20 10:00:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    ribbon = RibbonState(fast=541.0, pivot=540.0, slow=539.0, spread_cents=50.0, stack="BULL")
    green = _probe_bar(open_=540.0, high=541.5, low=539.8, close=541.2, volume=750_000)
    return BarContext(
        bar_idx=4, timestamp_et=ts, bar=green, prior_bars=_probe_prior_bars(),
        ribbon_now=ribbon, ribbon_history=[ribbon], vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=1_000_000.0, range_baseline_20=1.0, levels_active=[540.5],
        multi_day_levels=[], htf_15m_stack="BULL", level_states={},
    )


def vary_and_assert() -> dict:
    """C14 dead-knob discipline: PROVE vix_soft_mode and disable_filters=[8] each actually
    change evaluate_*'s output before trusting a single dollar of the AB run below. A knob
    that silently does nothing would make this whole study vacuous. Every assertion here is
    checked live, this session, against the real filters.py -- not read from memory or from
    the prereg's own claim. Raises AssertionError (halting main() before any expensive
    backtest runs) if any check fails.
    """
    out: dict = {"_doc": "Live proof each flag changes evaluate_* behaviour, run before the "
                          "AB study below. All checks executed against lib.filters this "
                          "session via inspect.signature + direct evaluate_* calls."}

    # --- signature-level asymmetry proof (structural, no BarContext needed) ---
    bull_params = inspect.signature(evaluate_bullish_setup).parameters
    bear_params = inspect.signature(evaluate_bearish_setup).parameters
    assert "vix_soft_mode" not in bull_params, (
        "evaluate_bullish_setup now HAS a vix_soft_mode parameter -- the prereg's "
        "'bull has no soft-mode escape valve' claim is STALE, ARM_A_soft's bull-side "
        "no-op assumption is wrong, re-read filters.py before running this study")
    assert "vix_soft_mode" in bear_params, (
        "evaluate_bearish_setup LOST its vix_soft_mode parameter -- ARM_A_soft cannot run")
    assert "disable_filters" in bull_params and "disable_filters" in bear_params, (
        "disable_filters is no longer symmetric across both sides -- ARM_B_delete's "
        "'symmetric, both sides' claim is stale")
    out["signature_check"] = {
        "bull_has_vix_soft_mode": False, "bear_has_vix_soft_mode": True,
        "bull_has_disable_filters": True, "bear_has_disable_filters": True,
        "status": "PASS -- matches prereg's asymmetry_disclosed claim exactly",
    }

    # --- bear: vix_now=17.25 (falling from 17.50) -- vix_pass False regardless of soft mode ---
    ctrl = evaluate_bearish_setup(_probe_bear_ctx(17.25, 17.50))
    soft = evaluate_bearish_setup(_probe_bear_ctx(17.25, 17.50), vix_soft_mode=True)
    delf = evaluate_bearish_setup(_probe_bear_ctx(17.25, 17.50), disable_filters=[8])
    assert ctrl.blockers == [8], (
        f"probe scenario no longer isolates filter 8 alone on CONTROL bear -- "
        f"got blockers={ctrl.blockers}, the vary-and-assert fixture itself needs repair "
        f"before it can prove anything about filter 8 specifically")
    assert 8 not in soft.blockers, (
        "vix_soft_mode=True still hard-blocks bear on filter 8 -- the flag is a DEAD KNOB, "
        "ARM_A_soft would be measuring zero behaviour change")
    assert 8 not in delf.blockers, (
        "disable_filters=[8] still blocks bear on filter 8 -- DEAD KNOB, ARM_B_delete "
        "would be measuring zero behaviour change")
    assert soft.bear_score == delf.bear_score - 1, (
        f"vix_soft_mode's -1 score demerit did not fire as documented: soft bear_score="
        f"{soft.bear_score}, disable bear_score={delf.bear_score} (expected soft == "
        f"disable - 1) -- the soft-vs-delete distinction this study measures may not exist")
    out["bear_probe"] = {
        "scenario": "vix_now=17.25 falling from 17.50 (vix_pass False under both rules)",
        "control_blockers": ctrl.blockers, "soft_blockers": soft.blockers,
        "disable_blockers": delf.blockers,
        "control_bear_score": ctrl.bear_score, "soft_bear_score": soft.bear_score,
        "disable_bear_score": delf.bear_score,
        "status": "PASS -- CONTROL hard-blocks (blockers==[8]); vix_soft_mode=True removes "
                  "the block and costs exactly -1 score; disable_filters=[8] removes the "
                  "block with NO score cost. Three distinguishable behaviours confirmed live.",
    }

    # --- bull: vix_now=17.40 rising from 17.10 -- not <17.20, not falling -> vix_pass False ---
    ctrl_b = evaluate_bullish_setup(_probe_bull_ctx(17.40, 17.10))
    delf_b = evaluate_bullish_setup(_probe_bull_ctx(17.40, 17.10), disable_filters=[8])
    assert ctrl_b.blockers == [8], (
        f"probe scenario no longer isolates filter 8 alone on CONTROL bull -- "
        f"got blockers={ctrl_b.blockers}")
    assert 8 not in delf_b.blockers, (
        "disable_filters=[8] still blocks bull on filter 8 -- DEAD KNOB on the bull side, "
        "ARM_B_delete's bull-side effect would be zero")
    out["bull_probe"] = {
        "scenario": "vix_now=17.40 rising from 17.10 (not <17.20, not falling -> vix_pass False)",
        "control_blockers": ctrl_b.blockers, "disable_blockers": delf_b.blockers,
        "status": "PASS -- CONTROL hard-blocks; disable_filters=[8] removes the block. "
                  "No vix_soft_mode variant exists on this side (confirmed above) so only "
                  "disable_filters is exercised here, matching ARM_A_soft's bull-side no-op.",
    }
    out["overall"] = "ALL VARY-AND-ASSERT CHECKS PASSED -- neither flag is a dead knob"
    log("vary-and-assert: " + out["overall"])
    return out


# ============================================================================== data

def load_extended_data():
    """OLD full-history file + the strictly-later tail of the newest file. VIX's
    timestamp_et is deliberately left as a RAW STRING column -- pre-parsing breaks across
    the DST seam and silently changes P&L (root-caused in structure_shift_cascade_ab.py
    lines 286-297). Do not "fix" this."""
    spy_old = pd.read_csv(OLD_SPY)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX)
    vix_new = pd.read_csv(NEW_VIX)
    _vix_new_dates = pd.to_datetime(vix_new["timestamp_et"]).dt.date
    vix_tail = vix_new[_vix_new_dates > OLD_WINDOW_END].reset_index(drop=True)
    vix_df = pd.concat([vix_old, vix_tail], ignore_index=True)
    return spy_df, vix_df


def recent_window_dates(spy_df: pd.DataFrame, n: int = RECENT_TRADING_DAYS) -> set:
    days = sorted({d for d in spy_df["timestamp_et"].dt.date if d <= FULL_END})
    return set(days[-n:])


# ============================================================================== arms

class Blockers8Capture:
    """Records blockers==[8] bars EXACTLY ONCE per (side, timestamp).

    THE DEDUPE IS LOAD-BEARING, NOT COSMETIC. `run_arm` patches BOTH `lib.orchestrator` and
    `lib.engine.score` with the SAME closure (they hold independent by-name bindings), and
    orchestrator.py's per-bar parity cross-check `_ENGINE_SCORE_ASSERT` drives EVERY bar
    through BOTH of them. A plain `list.append` would therefore record every qualifying bar
    TWICE -- exactly the defect filter5_ribbon_fate_2026_07_31.py shipped and then fixed
    (cohort A reported "346 bull / 152 bear" when the true bar counts were half that; DAY
    counts were unaffected, which is why it survived review). This class starts from that
    fix rather than re-discovering it.

    Guard: backtest/tests/test_vix_regime_gate_archetype_fate_2026_08_02.py
    (RED-proofed against a plain-list reimplementation).
    """

    __slots__ = ("_rows", "duplicate_hits")

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, dict]] = {"bear": {}, "bull": {}}
        self.duplicate_hits: int = 0

    def add(self, side: str, row: dict) -> None:
        bucket = self._rows[side]
        key = row["timestamp_et"]
        if key in bucket:
            self.duplicate_hits += 1
            return
        bucket[key] = row

    def rows(self, side: str) -> list[dict]:
        return list(self._rows[side].values())

    def assert_dual_patch_observed(self) -> None:
        """Positive proof the orchestrator/engine.score parity cross-check is still running.
        An assert, not a warning: a silent drop to zero means the capture is blind to one of
        the two scoring paths (C7 -- audit the output, never the exit code)."""
        assert self.duplicate_hits > 0, (
            "capture saw ZERO duplicate (side, timestamp) hits -- the orchestrator/engine.score "
            "parity cross-check that drives every bar through both patched bindings appears to "
            "have stopped running. Cohort A is now measuring only ONE scoring path."
        )


def run_arm(label: str, spy_df, vix_df, *, vix_soft_mode: bool = False,
            disable_filters: Optional[list[int]] = None, capture_blockers8: bool = False):
    """One arm. `vix_soft_mode` / `disable_filters` are passed as NATIVE run_backtest kwargs
    (both are first-class parameters on run_backtest itself, already threaded to both the
    direct evaluate_* call AND the internal _ENGINE_SCORE_ASSERT parity-oracle call --
    verified by reading orchestrator.py lines ~992-1060 this session) -- unlike filter5's
    ARM_B, NO kwarg-injection monkeypatch is needed for arm behaviour.

    The monkeypatch here exists ONLY for the optional blockers==[8] CAPTURE, and is a PURE
    PASS-THROUGH in every arm (it never alters `result`) -- so it cannot desync the
    orchestrator/engine.score parity assert regardless of which arm is running. Both module
    bindings are patched for the same reason filter5's script patches both: `lib.orchestrator`
    and `lib.engine.score` each hold an INDEPENDENT `from .filters import evaluate_*` binding,
    and the per-bar parity assert drives every bar through both, so a capture patching only
    one side would silently miss whichever path the assert is exercising via the other.
    """
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup
    assert score_mod.evaluate_bearish_setup is orig_bear, (
        "lib.engine.score no longer shares filters.evaluate_bearish_setup with lib.orchestrator "
        "-- the dual patch below would be scoring two different functions"
    )
    assert score_mod.evaluate_bullish_setup is orig_bull, (
        "lib.engine.score no longer shares filters.evaluate_bullish_setup with lib.orchestrator"
    )
    cand = Blockers8Capture()

    def _bear(ctx, **kw):
        res = orig_bear(ctx, **kw)
        if capture_blockers8 and res.blockers == [8]:
            cand.add("bear", {
                "date": ctx.timestamp_et.date().isoformat(),
                "timestamp_et": ctx.timestamp_et.isoformat(),
                "score": res.bear_score,
                "triggers": list(res.triggers_fired),
                "level": res.rejection_level,
                "vix_now": ctx.vix_now, "vix_prior": ctx.vix_prior,
                "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
            })
        return res

    def _bull(ctx, **kw):
        res = orig_bull(ctx, **kw)
        if capture_blockers8 and res.blockers == [8]:
            cand.add("bull", {
                "date": ctx.timestamp_et.date().isoformat(),
                "timestamp_et": ctx.timestamp_et.isoformat(),
                "score": res.bull_score,
                "triggers": list(res.triggers_fired),
                "level": res.reclaim_level,
                "vix_now": ctx.vix_now, "vix_prior": ctx.vix_prior,
                "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
            })
        return res

    kwargs = dict(efr.SAFE_BASE_LIVE)
    if vix_soft_mode:
        kwargs["vix_soft_mode"] = True
    if disable_filters is not None:
        kwargs["disable_filters"] = disable_filters

    orch_mod.evaluate_bearish_setup = _bear
    orch_mod.evaluate_bullish_setup = _bull
    score_mod.evaluate_bearish_setup = _bear
    score_mod.evaluate_bullish_setup = _bull
    t0 = time.time()
    try:
        r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
        score_mod.evaluate_bearish_setup = orig_bear
        score_mod.evaluate_bullish_setup = orig_bull
    log(f"  {label}: {len(r.trades)} raw entries in {time.time() - t0:.1f}s")
    return r, cand


# ============================================================================== exits

def derive_rows(label: str, r, spy_df: pd.DataFrame, ribbon_lookup, exit_shape: dict):
    """Re-walk every entry through the REAL exit manager. Byte-identical machinery to
    engine_fullhist_replay.py's / filter5_ribbon_fate_2026_07_31.py's own loop.

    Returns (walked_rows, skipped_counts, excluded_rows). `excluded_rows` carries the SAME
    identity tuple as a walked row so an excluded entry can be diffed against another arm's
    book exactly like a walked one -- an entry an arm ADDED but which no OPRA contract could
    price is NOT the same fact as an entry a GATE refused (C7)."""
    rows, skipped, excluded = [], {"no_opra": 0, "no_spy_day": 0}, []

    def _excluded(edate, symbol, t, reason):
        return {"arm": label, "date": edate.isoformat(),
                "entry_time_et": naive_dt(t.entry_time_et).isoformat(),
                "side": t.side, "symbol": symbol, "reason": reason,
                "setup": t.setup, "triggers": list(t.triggers_fired),
                "level": float(t.rejection_level) if t.rejection_level else None}

    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            skipped["no_opra"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_opra"))
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            skipped["no_spy_day"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_spy_day"))
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        rows.append({
            "arm": label, "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "side": t.side, "setup": t.setup, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": list(t.triggers_fired), "level": trigger_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
        })
    log(f"  {label}: {len(rows)} real-OPRA walks "
        f"(excluded: no_opra={skipped['no_opra']} no_spy_day={skipped['no_spy_day']})")
    return rows, skipped, excluded


# ============================================================================== stats

def _key(row) -> tuple:
    """Trade identity for the control/arm diff: same day, same entry instant, same contract."""
    return (row["date"], row["entry_time_et"], row["symbol"], row["side"])


def cohort_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "total": 0.0, "wr": None, "per_trade": None,
                "total_ex_best": None, "n_days": 0}
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(rows),
        "total": total,
        "wr": round(wins / len(rows), 4),
        "per_trade": round(total / len(rows), 2),
        "total_ex_best": round(total - max(pnls), 2),
        "n_days": len({r["date"] for r in rows}),
    }


def window_slice(rows: list[dict], dates: Optional[set]) -> list[dict]:
    if dates is None:
        return rows
    return [r for r in rows if dt.date.fromisoformat(r["date"]) in dates]


def runner_cohort(rows: list[dict]) -> dict:
    sel = [r for r in rows
           if "runner" in (r["exit_reason"] or "").lower() or "trail" in (r["exit_reason"] or "").lower()]
    return {"n": len(sel), "total": round(sum(r["dollar_pnl"] for r in sel), 2)}


def added_dropped(control_rows: list[dict], arm_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    ctrl_by_key = {_key(r): r for r in control_rows}
    arm_by_key = {_key(r): r for r in arm_rows}
    added = [arm_by_key[k] for k in arm_by_key if k not in ctrl_by_key]
    dropped = [ctrl_by_key[k] for k in ctrl_by_key if k not in arm_by_key]
    return added, dropped


def score_arm(label: str, control_rows: list[dict], arm_rows: list[dict],
              recent_dates: set) -> dict:
    added, dropped = added_dropped(control_rows, arm_rows)

    out = {"arm": label}
    for wname, wdates in (("full", None), ("recent25", recent_dates)):
        c = window_slice(control_rows, wdates)
        a = window_slice(arm_rows, wdates)
        c_total = round(sum(r["dollar_pnl"] for r in c), 2)
        a_total = round(sum(r["dollar_pnl"] for r in a), 2)
        w_added = window_slice(added, wdates)
        w_dropped = window_slice(dropped, wdates)
        changed_days = sorted({r["date"] for r in w_added} | {r["date"] for r in w_dropped})
        day_deltas = {}
        for d in changed_days:
            cd = sum(r["dollar_pnl"] for r in c if r["date"] == d)
            ad = sum(r["dollar_pnl"] for r in a if r["date"] == d)
            day_deltas[d] = round(ad - cd, 2)
        n_up = sum(1 for v in day_deltas.values() if v > 0)
        n_dn = sum(1 for v in day_deltas.values() if v < 0)
        delta = round(a_total - c_total, 2)
        best_added = max((r["dollar_pnl"] for r in w_added), default=0.0)
        out[wname] = {
            "control": {"n": len(c), "total": c_total},
            "arm": {"n": len(a), "total": a_total},
            "delta_total": delta,
            "n_added": len(w_added), "n_dropped": len(w_dropped),
            "added_stats": cohort_stats(w_added),
            "dropped_stats": cohort_stats(w_dropped),
            "n_changed_days": len(changed_days), "n_days_improved": n_up, "n_days_worsened": n_dn,
            "day_deltas": day_deltas,
            "best_added_trade": round(best_added, 2),
            "delta_minus_best_added": round(delta - best_added, 2),
            # concentration check (requirement 5) -- top single-day $ share of this window's
            # delta, so a positive delta driven by one outlier day cannot pass silently.
            "top_day_delta": (max(day_deltas.values()) if day_deltas else 0.0),
            "top_day_share_of_delta": (
                round(max(day_deltas.values()) / delta, 4)
                if day_deltas and delta not in (0, 0.0) else None),
        }
    out["runner_cohort"] = {
        "control": runner_cohort(control_rows),
        "arm": runner_cohort(arm_rows),
    }
    rc, ra = out["runner_cohort"]["control"], out["runner_cohort"]["arm"]
    out["gates"] = {
        "G1_recent_window_positive": {
            "delta_total_recent": out["recent25"]["delta_total"],
            "pass": out["recent25"]["delta_total"] > 0},
        "G2_day_majority_recent": {
            "improved": out["recent25"]["n_days_improved"],
            "worsened": out["recent25"]["n_days_worsened"],
            "pass": out["recent25"]["n_days_improved"] > out["recent25"]["n_days_worsened"]},
        "G3_survives_drop_best_recent": {
            "delta_minus_best": out["recent25"]["delta_minus_best_added"],
            "pass": out["recent25"]["delta_minus_best_added"] > 0},
        "G4_runner_anchor_no_regression": {
            "control_n": rc["n"], "arm_n": ra["n"],
            "control_total": rc["total"], "arm_total": ra["total"],
            "pass": (ra["n"] >= rc["n"] * RUNNER_NO_REGRESSION_FLOOR
                     and ra["total"] >= rc["total"] * RUNNER_NO_REGRESSION_FLOOR)},
        "G5_fire_count": {
            "n_added_full": out["full"]["n_added"], "n_added_recent": out["recent25"]["n_added"],
            "floor_full": FIRE_FLOOR_FULL, "floor_recent": FIRE_FLOOR_RECENT,
            "pass": (out["full"]["n_added"] >= FIRE_FLOOR_FULL
                     and out["recent25"]["n_added"] >= FIRE_FLOOR_RECENT)},
    }
    for g in out["gates"].values():
        g["status"] = "PASS" if g["pass"] else "FAIL"
    out["all_gates_pass"] = all(g["pass"] for g in out["gates"].values())
    out["verdict"] = "SHIP_CANDIDATE" if out["all_gates_pass"] else "NULL"
    out["evidence_floor_n_changed_ge_10_full"] = out["full"]["n_added"] + out["full"]["n_dropped"] >= 10
    return out


def attribution_block(control_rows: list[dict], arm_rows: list[dict]) -> dict:
    """WHERE the headline delta actually comes from -- artifact hunt, run before reporting.
    Decomposes the full-window delta into (i) trades filter 8 was actually blocking (added)
    and (ii) control trades that merely vanish because an unlocked earlier entry consumed the
    one-position-at-a-time slot (dropped / pre-emption), plus the exit-reason mix of each."""
    from collections import Counter

    added, dropped = added_dropped(control_rows, arm_rows)
    added_days = {r["date"] for r in added}
    dropped_days = {r["date"] for r in dropped}

    def mix(rows):
        c = Counter((r["exit_reason"] or "").split(" @")[0] for r in rows)
        n = max(1, len(rows))
        return {k: {"n": v, "pct": round(100.0 * v / n, 1)} for k, v in c.most_common()}

    add_total = round(sum(r["dollar_pnl"] for r in added), 2)
    drop_total = round(sum(r["dollar_pnl"] for r in dropped), 2)
    return {
        "_doc": "Decomposition of the full-window delta. delta_total == added_total - dropped_total.",
        "added_total_the_gate_was_blocking_this": add_total,
        "dropped_total_preempted_not_blocked": drop_total,
        "delta_from_preemption": round(-drop_total, 2),
        "pct_of_delta_from_preemption": (
            round(100.0 * (-drop_total) / (add_total - drop_total), 1)
            if (add_total - drop_total) else None),
        "dropped_days_that_also_gained_a_trade": {
            "n": len(dropped_days & added_days), "of": len(dropped_days),
            "days": sorted(dropped_days & added_days)},
        "added_exit_reason_mix": mix(added),
        "control_exit_reason_mix": mix(control_rows),
    }


# ====================================================== OPRA measurability (window-stratified)

def cached_contracts_per_day(dates) -> dict:
    """Cached OPRA contract count per trading day, read from the contract cache itself --
    the DENOMINATOR behind every exclusion in this study."""
    counts = {d: 0 for d in dates}
    for p in CACHE_DIR.glob("SPY*.csv"):
        stem = p.stem
        if len(stem) < 9 or not stem[3:9].isdigit():
            continue
        try:
            d = dt.date(2000 + int(stem[3:5]), int(stem[5:7]), int(stem[7:9]))
        except ValueError:
            continue
        if d in counts:
            counts[d] += 1
    return counts


def opra_measurability(control_rows, control_excl, arm_rows, arm_excl, recent_dates,
                        arm_label: str) -> dict:
    """Window-stratified OPRA exclusions + whether G1's recent-window verdict is MEASURABLE.
    G1 is a strict SIGN test on a sum over a handful of trades; if some of the arm's ADDED
    entries in that window could not be priced, the sign is UNDEFINED on the evidence, not
    merely uncertain -- a gap, not a refutation (filter5_ribbon_fate_2026_07_31.py precedent:
    this exact population's newest week has single-digit OPRA coverage)."""
    def keyset(rows):
        return {_key(r) for r in rows}

    def in_window(rows):
        return [r for r in rows if dt.date.fromisoformat(r["date"]) in recent_dates]

    ctrl_raw = keyset(control_rows) | keyset(control_excl)
    out = {"_doc": "OPRA exclusions stratified by window. Never BS-synthesized.", "windows": {}}
    for wname, rows_c, excl_c, rows_a, excl_a in (
        ("full", control_rows, control_excl, arm_rows, arm_excl),
        ("recent25", in_window(control_rows), in_window(control_excl),
         in_window(arm_rows), in_window(arm_excl)),
    ):
        added_walked = [r for r in rows_a if _key(r) not in ctrl_raw]
        added_excluded = [r for r in excl_a if _key(r) not in ctrl_raw]
        n_unmeas = len(added_excluded)
        n_raw = len(added_walked) + n_unmeas
        out["windows"][wname] = {
            "CONTROL": {"walked": len(rows_c),
                        "excluded_no_opra": sum(1 for r in excl_c if r["reason"] == "no_opra"),
                        "excluded_no_spy_day": sum(1 for r in excl_c if r["reason"] == "no_spy_day")},
            arm_label: {"walked": len(rows_a),
                        "excluded_no_opra": sum(1 for r in excl_a if r["reason"] == "no_opra"),
                        "excluded_no_spy_day": sum(1 for r in excl_a if r["reason"] == "no_spy_day")},
            "added_by_arm": {
                "raw_entries": n_raw, "measurable": len(added_walked),
                "unmeasurable_no_opra": n_unmeas,
                "measurable_pct": round(100.0 * len(added_walked) / n_raw, 1) if n_raw else None,
                "unmeasurable_detail": sorted(
                    ({"date": r["date"], "entry_time_et": r["entry_time_et"],
                      "symbol": r["symbol"], "side": r["side"], "reason": r["reason"]}
                     for r in added_excluded),
                    key=lambda r: (r["date"], r["entry_time_et"])),
            },
        }
    out["cached_contracts_per_day_recent25"] = {
        d.isoformat(): n for d, n in sorted(cached_contracts_per_day(recent_dates).items())}
    zero_days = [d for d, n in out["cached_contracts_per_day_recent25"].items() if n == 0]
    out["recent25_days_with_zero_opra_coverage"] = {"n": len(zero_days), "days": zero_days}
    return out


def relabel_g1_measurability(scored: dict, meas: dict) -> dict:
    """FAIL -> UNDETERMINED on G1 when any ADDED recent-window entry could not be priced.
    The pass/fail BOOLEAN is untouched (ship rule needs `all(gates pass)`, UNDETERMINED is
    not a pass) -- only the LABEL + explanation change."""
    g1 = scored["gates"]["G1_recent_window_positive"]
    add = meas["windows"]["recent25"]["added_by_arm"]
    n_missing = add["unmeasurable_no_opra"]
    delta = g1["delta_total_recent"]
    if n_missing <= 0:
        g1["status"] = "PASS" if g1["pass"] else "FAIL"
        return scored
    g1["status"] = "UNDETERMINED"
    g1["undetermined_because"] = (
        f"{n_missing} of {add['raw_entries']} raw entries this arm ADDS in the recent window "
        f"could not be priced (no cached OPRA contract), so only {add['measurable']} are in "
        f"the measured delta of ${delta:+,.2f}. G1 is a strict SIGN test on that sum: the "
        f"missing entries would only need to average "
        f"${(-delta) / n_missing:+,.2f} each to flip it. The sign is UNDETERMINED on the "
        f"evidence, not measured-negative."
    )
    g1["verdict_unchanged"] = (
        "UNCHANGED EITHER WAY. UNDETERMINED is not a PASS, the ship rule requires all five "
        "gates to pass, and this is a gap in the evidence, not a refutation."
    )
    return scored


# ============================================================================== G6 archetype

def archetype_perf(rows: list[dict], archetype_lookup: dict[str, str]) -> dict:
    trades = [{"date": r["date"], "dollar_pnl": r["dollar_pnl"]} for r in rows]
    return performance_by_archetype(trades, archetype_lookup)


def g6_delta(control_perf: dict, arm_perf: dict) -> dict:
    """Per-archetype delta (arm minus control) in n_days_entered and total $ -- exactly what
    the prereg's G6 asks for, reported not gating. Reuses performance_by_archetype's own
    per-archetype dict; no raw-trade re-aggregation here. UNTAGGED carries a different shape
    (n_trades/dates only) and is reported separately, not force-merged."""
    out = {}
    keys = sorted(k for k in (set(control_perf) | set(arm_perf)) if k != "UNTAGGED")
    for arch in keys:
        c = control_perf.get(arch, {"n_days": 0, "total_pnl": 0.0, "n_trades": 0})
        a = arm_perf.get(arch, {"n_days": 0, "total_pnl": 0.0, "n_trades": 0})
        out[arch] = {
            "control_n_days_entered": c.get("n_days", 0), "arm_n_days_entered": a.get("n_days", 0),
            "delta_n_days_entered": a.get("n_days", 0) - c.get("n_days", 0),
            "control_n_trades": c.get("n_trades", 0), "arm_n_trades": a.get("n_trades", 0),
            "control_total": c.get("total_pnl", 0.0), "arm_total": a.get("total_pnl", 0.0),
            "delta_total": round(a.get("total_pnl", 0.0) - c.get("total_pnl", 0.0), 2),
        }
    if "UNTAGGED" in control_perf or "UNTAGGED" in arm_perf:
        out["UNTAGGED"] = {
            "control_n_trades": control_perf.get("UNTAGGED", {}).get("n_trades", 0),
            "arm_n_trades": arm_perf.get("UNTAGGED", {}).get("n_trades", 0),
        }
    return out


# ============================================================================== BH-FDR advisory

def perm_test_mean_gt_zero(pnls: list[float], rng: random.Random, n_perms: int = N_PERMS) -> dict:
    """One-sided sign-flip permutation test: H0 mean==0 (symmetric around 0), H1 mean>0.
    Standard exchangeability-under-H0 construction; matches this repo's own permutation-test
    convention (trendline_context_conditioning_2026_08_01.py's perm_test), one-sided instead
    of two-sided per the prereg's explicit 'one-sided on per-changed-trade mean > 0'."""
    n = len(pnls)
    if n == 0:
        return {"n": 0, "obs_mean": None, "p": None}
    obs_mean = sum(pnls) / n
    hits = 0
    for _ in range(n_perms):
        s = sum(p if rng.random() < 0.5 else -p for p in pnls)
        if (s / n) >= obs_mean - 1e-12:
            hits += 1
    return {"n": n, "obs_mean": round(obs_mean, 4), "p": (1 + hits) / (1 + n_perms)}


def bh_fdr(tests: list[dict], q: float = Q_STAR) -> None:
    """Benjamini-Hochberg across all non-None p-values; annotates in place. Same algorithm as
    trendline_context_conditioning_2026_08_01.py's bh_fdr (this repo's own established
    per-script convention -- no shared stats module exists, each study owns its copy)."""
    scored = [t for t in tests if t.get("p") is not None]
    m = len(scored)
    for t in tests:
        t["bh_survives"] = False
    if not m:
        return
    scored.sort(key=lambda t: t["p"])
    cutoff_rank = 0
    for i, t in enumerate(scored, start=1):
        if t["p"] <= q * i / m:
            cutoff_rank = i
    for i, t in enumerate(scored, start=1):
        t["bh_rank"] = i
        t["bh_threshold"] = round(q * i / m, 5)
        t["bh_survives"] = i <= cutoff_rank


def bh_fdr_advisory(control_rows, a_rows, b_rows) -> dict:
    """Advisory only (reported_not_gating.bh_fdr) -- per-changed-trade mean>0, one-sided,
    across the 2 live arms' FULL-population ADDED cohort (the realized version of 'setups
    filter 8 alone was blocking' -- the population the H1 hypothesis is actually about)."""
    rng = random.Random(SEED)
    added_a, _ = added_dropped(control_rows, a_rows)
    added_b, _ = added_dropped(control_rows, b_rows)
    tests = [
        {"arm": "ARM_A_soft", **perm_test_mean_gt_zero(
            [r["dollar_pnl"] for r in added_a], rng)},
        {"arm": "ARM_B_delete", **perm_test_mean_gt_zero(
            [r["dollar_pnl"] for r in added_b], rng)},
    ]
    bh_fdr(tests)
    return {
        "_doc": "Advisory only (reported_not_gating.bh_fdr) -- one-sided sign-flip permutation "
                "test, H1: mean(dollar_pnl) of the arm's full-population ADDED cohort > 0. "
                f"N_PERMS={N_PERMS}, seed={SEED}, q*={Q_STAR}. Does NOT gate the ship decision.",
        "tests": tests,
    }


# ============================================================================== main

def main() -> int:
    t_start = time.time()
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"pre-reg {prereg['prereg_id']} frozen {prereg['frozen_at_et']}")

    log("STEP 0: vary-and-assert (C14 dead-knob discipline) -- must pass before any run")
    vary = vary_and_assert()

    spy_df, vix_df = load_extended_data()
    log(f"data: spy rows={len(spy_df)} "
        f"{spy_df['timestamp_et'].min()} .. {spy_df['timestamp_et'].max()}")
    recent_dates = recent_window_dates(spy_df)
    log(f"recent window = {len(recent_dates)} trading days "
        f"{min(recent_dates)} .. {max(recent_dates)}")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"exit shape (strategies.py#RIBBON_RIDE): {exit_shape}")

    lib = load_library(ARCHETYPE_LIBRARY)
    archetype_lookup = {d: rec["archetype"] for d, rec in lib["days"].items()}
    log(f"archetype library: {len(archetype_lookup)} tagged days "
        f"({lib.get('spec_version')})")

    log("CONTROL: run_backtest(**SAFE_BASE_LIVE) + blockers==[8] capture")
    r_ctrl, cand = run_arm("CONTROL", spy_df, vix_df, capture_blockers8=True)
    log("ARM_A_soft: vix_soft_mode=True (bear-only, native kwarg, no monkeypatch needed)")
    r_a, _ = run_arm("ARM_A_soft", spy_df, vix_df, vix_soft_mode=True)
    log("ARM_B_delete: disable_filters=[8] (both sides, native kwarg, no monkeypatch needed)")
    r_b, _ = run_arm("ARM_B_delete", spy_df, vix_df, disable_filters=[8])

    cand.assert_dual_patch_observed()
    log(f"capture dedupe: {cand.duplicate_hits} duplicate (side, timestamp) hits suppressed "
        f"-- the orchestrator/engine.score dual patch is live and each bar is recorded ONCE")

    log("walking exits through the REAL exit_manager")
    ctrl_rows, ctrl_skip, ctrl_excl = derive_rows("CONTROL", r_ctrl, spy_df, ribbon_lookup, exit_shape)
    a_rows, a_skip, a_excl = derive_rows("ARM_A_soft", r_a, spy_df, ribbon_lookup, exit_shape)
    b_rows, b_skip, b_excl = derive_rows("ARM_B_delete", r_b, spy_df, ribbon_lookup, exit_shape)

    def cand_stats(side: str) -> dict:
        rows = cand.rows(side)
        recent = [c for c in rows if dt.date.fromisoformat(c["date"]) in recent_dates]
        return {
            "n_bars_full": len(rows), "n_days_full": len({c['date'] for c in rows}),
            "n_bars_recent25": len(recent), "n_days_recent25": len({c['date'] for c in recent}),
            "sample_recent": recent[-8:],
        }

    meas_a = opra_measurability(ctrl_rows, ctrl_excl, a_rows, a_excl, recent_dates, "ARM_A_soft")
    meas_b = opra_measurability(ctrl_rows, ctrl_excl, b_rows, b_excl, recent_dates, "ARM_B_delete")
    scored_a = relabel_g1_measurability(
        score_arm("ARM_A_soft", ctrl_rows, a_rows, recent_dates), meas_a)
    scored_b = relabel_g1_measurability(
        score_arm("ARM_B_delete", ctrl_rows, b_rows, recent_dates), meas_b)

    n_excluded_no_opra = {
        "CONTROL": ctrl_skip["no_opra"], "ARM_A_soft": a_skip["no_opra"],
        "ARM_B_delete": b_skip["no_opra"],
    }
    log(f"n_excluded_no_opra: {n_excluded_no_opra}")

    # G6 -- reported, not gating
    perf_ctrl_full = archetype_perf(ctrl_rows, archetype_lookup)
    perf_a_full = archetype_perf(a_rows, archetype_lookup)
    perf_b_full = archetype_perf(b_rows, archetype_lookup)
    perf_ctrl_recent = archetype_perf(window_slice(ctrl_rows, recent_dates), archetype_lookup)
    perf_a_recent = archetype_perf(window_slice(a_rows, recent_dates), archetype_lookup)
    perf_b_recent = archetype_perf(window_slice(b_rows, recent_dates), archetype_lookup)

    g6 = {
        "_doc": prereg["reported_not_gating"]["G6_archetype_participation_delta"],
        "full_population": {
            "CONTROL": perf_ctrl_full, "ARM_A_soft": perf_a_full, "ARM_B_delete": perf_b_full,
            "delta_ARM_A_soft_vs_CONTROL": g6_delta(perf_ctrl_full, perf_a_full),
            "delta_ARM_B_delete_vs_CONTROL": g6_delta(perf_ctrl_full, perf_b_full),
        },
        "recent_window": {
            "CONTROL": perf_ctrl_recent, "ARM_A_soft": perf_a_recent, "ARM_B_delete": perf_b_recent,
            "delta_ARM_A_soft_vs_CONTROL": g6_delta(perf_ctrl_recent, perf_a_recent),
            "delta_ARM_B_delete_vs_CONTROL": g6_delta(perf_ctrl_recent, perf_b_recent),
        },
    }

    bh = bh_fdr_advisory(ctrl_rows, a_rows, b_rows)

    out = {
        "_doc": __doc__,
        "generated_at_et": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prereg_path": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "prereg_id": prereg["prereg_id"],
        "prereg_frozen_at_et": prereg["frozen_at_et"],
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                   "recent_n_days": len(recent_dates),
                   "recent_start": min(recent_dates).isoformat(),
                   "recent_end": max(recent_dates).isoformat()},
        "filter_8_definition": prereg["filter_8_definition_as_read"],
        "provenance_finding": prereg["provenance_finding_stated_before_measurement"],
        "vary_and_assert": vary,
        "cohort_A_blocked_by_filter8_alone": {
            "_doc": "Bars where filter 8 was the ONLY blocker -- captured during the CONTROL "
                    "run by a pure pass-through monkeypatch. Raw SIGNAL bars, not trades: the "
                    "engine's escalation lock / one-position-at-a-time rules mean only some "
                    "become entries. The REALIZED version is each arm's `added_stats` below.",
            "bear": cand_stats("bear"), "bull": cand_stats("bull"),
        },
        "cohort_B_allowed_by_filter8": {
            "_doc": "CONTROL's own entered book -- every trade taken WITH filter 8 satisfied.",
            "full": cohort_stats(ctrl_rows),
            "recent25": cohort_stats(window_slice(ctrl_rows, recent_dates)),
            "runner_cohort": runner_cohort(ctrl_rows),
        },
        "opra_exclusions": {"CONTROL": ctrl_skip, "ARM_A_soft": a_skip, "ARM_B_delete": b_skip,
                            "n_excluded_no_opra": n_excluded_no_opra,
                            "note": "excluded from every total, never BS-synthesized"},
        "opra_measurability": {"ARM_A_soft": meas_a, "ARM_B_delete": meas_b},
        "arms": {"ARM_A_soft": scored_a, "ARM_B_delete": scored_b},
        "attribution": {
            "ARM_A_soft": attribution_block(ctrl_rows, a_rows),
            "ARM_B_delete": attribution_block(ctrl_rows, b_rows),
        },
        "archetype_participation_G6": g6,
        "bh_fdr_advisory": bh,
        "gates_frozen": prereg["gates_frozen"],
        "reported_not_gating": prereg["reported_not_gating"],
        "ship_rule": prereg["ship_rule"],
        "trades": {"CONTROL": ctrl_rows, "ARM_A_soft": a_rows, "ARM_B_delete": b_rows},
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"done in {time.time() - t_start:.1f}s")

    for name, s in out["arms"].items():
        log(f"{name}: full delta ${s['full']['delta_total']:+,.2f} | "
            f"recent25 delta ${s['recent25']['delta_total']:+,.2f} | "
            f"added {s['full']['n_added']} | verdict {s['verdict']}")
    return 0


# ============================================================================== markdown

def _measurability_md(out: dict, arm_key: str) -> list[str]:
    m = out["opra_measurability"].get(arm_key)
    if not m:
        return []
    L = [f"### OPRA coverage -- {arm_key} (window-stratified exclusions)", ""]
    L.append("| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |")
    L.append("|---|---|--:|--:|--:|")
    for w, wd in m["windows"].items():
        for arm in ("CONTROL", arm_key):
            a = wd[arm]
            L.append(f"| {w} | {arm} | {a['walked']} | {a['excluded_no_opra']} | "
                     f"{a['excluded_no_spy_day']} |")
    L.append("")
    L.append("**Entries this arm ADDS -- how many are even measurable:**")
    L.append("")
    L.append("| window | raw added | measurable | unmeasurable (no OPRA) | measurable % |")
    L.append("|---|--:|--:|--:|--:|")
    for w, wd in m["windows"].items():
        a = wd["added_by_arm"]
        L.append(f"| {w} | {a['raw_entries']} | {a['measurable']} | "
                 f"{a['unmeasurable_no_opra']} | {a['measurable_pct']}% |")
    L.append("")
    z = m["recent25_days_with_zero_opra_coverage"]
    L.append(f"Recent-window trading days with ZERO cached OPRA coverage: **{z['n']}** "
             f"({', '.join(z['days']) if z['days'] else 'none'}).")
    L.append("")
    return L


def _arm_md(name: str, s: dict) -> list[str]:
    L = [f"## {name} -- **{s['verdict']}**", ""]
    L.append("| window | control | arm | delta | added | dropped | days +/- | top-day share of delta |")
    L.append("|---|--:|--:|--:|--:|--:|:--|--:|")
    for w in ("full", "recent25"):
        x = s[w]
        share = f"{x['top_day_share_of_delta']*100:.1f}%" if x['top_day_share_of_delta'] is not None else "n/a"
        L.append(f"| {w} | ${x['control']['total']:,.2f} (n={x['control']['n']}) | "
                 f"${x['arm']['total']:,.2f} (n={x['arm']['n']}) | "
                 f"**${x['delta_total']:+,.2f}** | {x['n_added']} | {x['n_dropped']} | "
                 f"{x['n_days_improved']}/{x['n_days_worsened']} | {share} |")
    L.append("")
    add = s["full"]["added_stats"]
    L.append(f"Added-trade cohort (full window, real exits): n={add['n']} "
             f"total=${add['total']:,.2f} WR={add['wr']} per-trade=${add['per_trade'] or 0:,.2f} "
             f"ex-best=${add['total_ex_best'] or 0:,.2f}")
    L.append("")
    L.append("| gate | result | status |")
    L.append("|---|---|:--:|")
    _hide = {"pass", "status", "undetermined_because", "verdict_unchanged"}
    for gid, g in s["gates"].items():
        detail = ", ".join(f"{k}={v}" for k, v in g.items() if k not in _hide)
        L.append(f"| {gid} | {detail} | {g.get('status', 'PASS' if g['pass'] else 'FAIL')} |")
    g1 = s["gates"].get("G1_recent_window_positive", {})
    if g1.get("status") == "UNDETERMINED":
        L.append("")
        L.append(f"> **G1 is UNDETERMINED, not FAIL.** {g1['undetermined_because']}")
        L.append(">")
        L.append(f"> **{g1['verdict_unchanged']}**")
    L.append("")
    return L


def _g6_md(out: dict) -> list[str]:
    g6 = out["archetype_participation_G6"]
    L = ["## G6 -- archetype participation delta (REPORTED, NOT GATING)", ""]
    L.append(g6["_doc"])
    L.append("")
    for scope_name, scope_key in (("Full population", "full_population"), ("Recent 25-day window", "recent_window")):
        L.append(f"### {scope_name}")
        L.append("")
        for arm_name in ("ARM_A_soft", "ARM_B_delete"):
            delta = g6[scope_key][f"delta_{arm_name}_vs_CONTROL"]
            L.append(f"**{arm_name}:**")
            L.append("")
            L.append("| archetype | control n_days | arm n_days | delta n_days | control $ | arm $ | delta $ |")
            L.append("|---|--:|--:|--:|--:|--:|--:|")
            for arch, d in delta.items():
                if arch == "UNTAGGED":
                    continue
                L.append(f"| {arch} | {d['control_n_days_entered']} | {d['arm_n_days_entered']} | "
                         f"{d['delta_n_days_entered']:+d} | ${d['control_total']:,.2f} | "
                         f"${d['arm_total']:,.2f} | **${d['delta_total']:+,.2f}** |")
            L.append("")
    return L


def _bh_fdr_md(out: dict) -> list[str]:
    bh = out["bh_fdr_advisory"]
    L = ["## BH-FDR advisory (reported_not_gating, alpha=0.10)", ""]
    L.append(bh["_doc"])
    L.append("")
    L.append("| arm | n changed trades | obs mean $/trade | p (one-sided) | BH survives q*=0.10 |")
    L.append("|---|--:|--:|--:|:--:|")
    for t in bh["tests"]:
        L.append(f"| {t['arm']} | {t['n']} | ${t['obs_mean']:,.2f} | {t['p']:.4f} | "
                 f"{'YES' if t['bh_survives'] else 'no'} |")
    L.append("")
    return L


def write_markdown(out: dict) -> None:
    L = []
    L.append("# FILTER 8 (VIX regime gate) -- archetype-conditional cost measurement + fate decision (2026-08-02)")
    L.append("")
    L.append(f"Pre-reg `{out['prereg_path']}` frozen **{out['prereg_frozen_at_et']}**, before any "
             f"run. Runner: `backtest/tools/vix_regime_gate_archetype_fate_2026_08_02.py`.")
    L.append("")
    L.append("## Vary-and-assert (C14 dead-knob discipline)")
    v = out["vary_and_assert"]
    L.append("")
    L.append(f"- Signature check: {v['signature_check']['status']}")
    L.append(f"- Bear probe (vix_now=17.25 falling from 17.50): {v['bear_probe']['status']}")
    L.append(f"  - CONTROL blockers={v['bear_probe']['control_blockers']}, score={v['bear_probe']['control_bear_score']}")
    L.append(f"  - vix_soft_mode=True blockers={v['bear_probe']['soft_blockers']}, score={v['bear_probe']['soft_bear_score']}")
    L.append(f"  - disable_filters=[8] blockers={v['bear_probe']['disable_blockers']}, score={v['bear_probe']['disable_bear_score']}")
    L.append(f"- Bull probe (vix_now=17.40 rising from 17.10): {v['bull_probe']['status']}")
    L.append(f"  - CONTROL blockers={v['bull_probe']['control_blockers']}")
    L.append(f"  - disable_filters=[8] blockers={v['bull_probe']['disable_blockers']}")
    L.append(f"- **{v['overall']}**")
    L.append("")
    L.append("## What filter 8 is")
    fd = out["filter_8_definition"]
    L.append(f"- **BULL** (`filters.py:{fd['bull_path_line']}`): `{fd['bull_rule']}`")
    L.append(f"- **BEAR** (`filters.py:{fd['bear_path_line']}`): `{fd['bear_rule']}`")
    L.append(f"- Asymmetry: {fd['asymmetry_disclosed']}")
    L.append("")
    L.append("## Provenance")
    pf = out["provenance_finding"]
    L.append(f"**{pf['claim']}**")
    for e in pf["evidence_checked"]:
        L.append(f"- {e}")
    L.append(f"\n{pf['consequence']}")
    L.append("")
    L.append("## Cohort A -- setups filter 8 blocked ALONE (blockers == [8])")
    ca = out["cohort_A_blocked_by_filter8_alone"]
    L.append("")
    L.append("| side | bars (full) | days (full) | bars (recent 25d) | days (recent) |")
    L.append("|---|--:|--:|--:|--:|")
    for side in ("bull", "bear"):
        s = ca[side]
        L.append(f"| {side} | {s['n_bars_full']} | {s['n_days_full']} | "
                 f"{s['n_bars_recent25']} | {s['n_days_recent25']} |")
    L.append("")
    L.append("## Cohort B -- the book filter 8 ALLOWED (CONTROL)")
    cb = out["cohort_B_allowed_by_filter8"]
    L.append("")
    L.append("| window | n | total | WR | per-trade | total ex-best |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for w in ("full", "recent25"):
        s = cb[w]
        L.append(f"| {w} | {s['n']} | ${s['total']:,.2f} | {s['wr']} | "
                 f"${s['per_trade'] or 0:,.2f} | ${s['total_ex_best'] or 0:,.2f} |")
    L.append("")
    L.append(f"n_excluded_no_opra: {out['opra_exclusions']['n_excluded_no_opra']}")
    L.append("")
    for name, s in out["arms"].items():
        L.extend(_arm_md(name, s))
        L.extend(_measurability_md(out, name))
        at = out["attribution"][name]
        L.append(f"### {name} -- attribution (artifact hunt)")
        L.append("")
        L.append(f"- Trades filter 8 was ACTUALLY blocking (added cohort): "
                 f"**${at['added_total_the_gate_was_blocking_this']:,.2f}**")
        L.append(f"- Control trades that merely VANISH (pre-emption): "
                 f"${at['dropped_total_preempted_not_blocked']:,.2f} -> "
                 f"**${at['delta_from_preemption']:+,.2f}** "
                 f"({at['pct_of_delta_from_preemption']}% of the delta)")
        L.append("")
    L.extend(_g6_md(out))
    L.extend(_bh_fdr_md(out))
    L.append("## Ship rule")
    L.append("")
    L.append(out["ship_rule"])
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
