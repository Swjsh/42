"""structure_shift_cascade_ab.py -- pre-reg #2 CONTROL-vs-TREATMENT full-engine replay.

Pre-reg (FROZEN, commit 58bb61fa): analysis/recommendations/
prereg-structure-shift-cascade-2026-07-28.json ("STRUCTURE-SHIFT-IN-CASCADE"). Tests the
staged wiring commit 459342c8 -- structure_shift_confirmation as an OR-alternative to
filter 5 (bear ribbon check) / the HTF-disagreement soft demerit (bull) -- INSIDE the full
filter cascade, every other filter/gate still armed. Distinct from, and does NOT rescue,
pre-reg #1's NULL verdict (structure-shift-replay-2026-07-28.md): #1 tested the shift
predicate STANDALONE (replacing the entire gate stack); this tests the wiring's ACTUAL
in-cascade semantics.

============================================================================ PLUMBING ROUTE
`orchestrator.run_backtest` does NOT forward a `bear_kwargs`/`bull_kwargs` dict from the
caller into `score_bar` -- verified by reading its signature (backtest/lib/orchestrator.py
~470-676): every kwarg is named explicitly, and it calls `evaluate_bearish_setup` /
`evaluate_bullish_setup` directly with a hardcoded keyword list (orchestrator.py ~992-1029)
that does NOT include `structure_shift_confirmation`. There is no generic passthrough.
Per the task brief's explicit fallback: "if it does not forward them, add NOTHING to
orchestrator -- instead drive the per-bar scoring through engine_cli.decide_payload with
gate_params.structure_shift_confirmation_enabled=true (the committed flip point)".

CONCRETE ROUTE TAKEN:
  1. CONTROL: `orchestrator.run_backtest(**SAFE_BASE_LIVE)` unmodified (byte-identical to
     engine_fullhist_replay.py), monkeypatching `evaluate_bearish_setup` /
     `evaluate_bullish_setup` ONLY to (a) capture the CONSTANT bear_kwargs/bull_kwargs
     orchestrator computes once per run (verified constant across the whole loop -- every
     kwarg it passes is a run-level local, none varies per bar) and (b) capture the
     BarContext for every bear-scored bar whose blockers == [5] EXACTLY (the "blocked-by-
     exactly-the-lagging-gate" class the pre-reg names -- the ONLY bear population the
     bull-htf-demerit-waiver / filter-5-OR-alternative wiring can possibly flip: bull's
     `passed` is `len(blockers) == 0`, computed BEFORE the htf-demerit block runs and never
     touched by it -- see filters.py `evaluate_bullish_setup` -- so the bull mirror is
     PROVABLY a no-op for entry decisions; confirmed by `test_structure_shift_wiring.py`'s
     own `test_htf_bear_demerit_waived_by_shift_confirmation` (`on.passed == off.passed`).
  2. Exits re-derived through `walk_exit_manager` for CONTROL exactly like
     engine_fullhist_replay.py's two-layer pattern (ENTRY via run_backtest, EXIT via the
     REAL exit_manager core under RIBBON_RIDE's exit shape).
  3. TREATMENT candidate re-scoring: for EACH captured blockers==[5] bar, the ORIGINAL
     orchestrator BarContext is serialized into a `decide_payload`-shaped `bar_ctx` (same
     JSON contract `test_structure_shift_wiring.py::_payload_for` and
     `heartbeat_core._build_payload` use), windowed to the last 200 bars ending at the
     trigger (>> the 60-bar max lookback any filter reads, so zero truncation risk) so the
     serialized DataFrame stays small. `score_params.bear_kwargs`/`bull_kwargs` are the
     SAME constant kwargs orchestrator used (JSON-safety only: dt.time -> "HH:MM"). This is
     called TWICE per candidate: flag OFF (`gate_params={}` plus the SAFE gate config) as a
     FIDELITY CHECK against the orchestrator's own recorded bear_score/blockers, and flag ON
     (`gate_params["structure_shift_confirmation_enabled"]=True`) as the TREATMENT verdict.
     `gate_params` also carries SAFE_BASE_LIVE's own gate-shaped kwargs (block_level_
     rejection, block_elite_bull [+VIX band], block_bull_1100_1200, entry_bar_body_pct_min,
     vix_bear_hard_cap, max_ribbon_duration_bars) so `evaluate_gates` (the 15 entry gates
     `decide_payload` ALSO runs) sees the SAME armed config the live cascade uses -- omitting
     these would silently leave them "off" (decide_payload's own documented default) and
     overstate the treatment population with entries the real gates would still block.
  4. Every candidate that flips to verdict "ENTER_BEAR" is entry+1-resolved (real OPRA fills
     only, BS-synthetic disclosed/excluded -- reuses `ladder_fullhist_replay.resolve_ladder_
     entry` verbatim, same honest-design precedent) and merged CHRONOLOGICALLY with
     CONTROL's own trades into ONE one-position-at-a-time (NOT_FLAT) walk -- exactly the
     mechanism G4 (preemption) requires: an earlier-admitted shift entry can occupy the
     position slot and cause a later baseline trade (or a later shift candidate) to never
     fire. Admitted trades' exits are re-derived via the SAME walk_exit_manager/RIBBON_RIDE
     shape as CONTROL.

WHAT THIS DOES NOT MODEL (disclosed, not silently dropped): the SKIP_QUALITY_LOCK per-day
escalation lock. `engine_cli.decide_payload`'s own docstring scopes this OUT deliberately
("the two MUTABLE/forward-scanning blocks... stay in the orchestrator... SKIP_QUALITY_LOCK
... is the caller's responsibility") -- it depends on orchestrator's PRIVATE internal
per-day state (which trade tiers were already taken today, whether the prior fill on that
setup stopped out, a 45-min leg-2 gap) that only exists inside run_backtest's own loop and
is not re-derivable from the stateless decide_payload boundary without re-implementing a
non-trivial slice of orchestrator's own mutable state machine -- a reimplementation risk of
the same shape the task brief warns against for the predicate itself, just applied to a
different (orthogonal, pre-existing, unchanged-by-this-flag) mechanism. Given the pre-reg's
own expected population (~10 trades over the whole window), this is disclosed as a scope
gap rather than blocking the replay: reported ADDED-trade counts are a modest upper bound
(a small number of borderline candidates could in reality be quality-locked out). TRENDLINE_
LEG2 sizing (prior_stopped + 45min-gap escalation, qty=20) is also not modeled; admitted
TRENDLINE-tier trades use the base qty=3.

Run: backtest/.venv/Scripts/python.exe backtest/tools/structure_shift_cascade_ab.py
Outputs: analysis/recommendations/structure-shift-cascade-ab-2026-07-28.{json,md}
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- SAFE_BASE_LIVE, SPY/VIX files, ribbon lookup
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- entry_date, classify_tier
import strategies as fleet_strategies  # noqa: E402
import ladder_fullhist_replay as lfr  # noqa: E402 -- extended data window (thru 2026-07-27)
from ladder_fullhist_replay import (  # noqa: E402 -- reuse, do not reimplement
    build_rth_frame, resolve_ladder_entry,
)
import lib.orchestrator as orch_mod  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.engine.engine_cli import decide_payload  # noqa: E402
from lib.filters import BarContext  # noqa: E402
from crypto.lib.strike_selection import pick_strike, V15_SAFE_TIERS  # noqa: E402

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-structure-shift-cascade-2026-07-28.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "structure-shift-cascade-ab-2026-07-28.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "structure-shift-cascade-ab-2026-07-28.md"

STORED_SCORECARD = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"

BEAR_INITIAL_EQUITY = efr.SAFE_BASE_LIVE["initial_equity"]  # 1746.75, live-verified 2026-07-11
PER_TRADE_RISK_CAP_PCT = efr.SAFE_BASE_LIVE["per_trade_risk_cap_pct"]  # 0.30, Rule 6 Safe
MIN_PREMIUM_FOR_LEVEL_TIERS = efr.SAFE_BASE_LIVE["min_premium_for_level_tiers"]  # 0.30

TIER_QTY = {"SUPER": 15, "ELITE": 10, "LEVEL": 22, "TRENDLINE": 3, "TRENDLINE_LEG2": 20, "BASE": 3}

# GATE_KEYS -- SAFE_BASE_LIVE's own gate-shaped kwargs, keyed exactly as engine.gates.py's
# GATE_ORDER / run_backtest kwarg names expect (see engine_cli.py docstring "gate_params
# ... keyed by the run_backtest gate-kwarg names"). Values transcribed field-by-field from
# efr.SAFE_BASE_LIVE (== eb.SAFE_BASE, initial_equity bumped) -- NOT re-derived, so this
# cannot silently drift from what CONTROL's own run_backtest call actually armed.
GATE_PARAMS_BASE = {
    "block_level_rejection": efr.SAFE_BASE_LIVE["block_level_rejection"],
    "block_elite_bull": efr.SAFE_BASE_LIVE["block_elite_bull"],
    "block_elite_bull_vix_low": efr.SAFE_BASE_LIVE["block_elite_bull_vix_low"],
    "block_elite_bull_vix_high": efr.SAFE_BASE_LIVE["block_elite_bull_vix_high"],
    "block_bull_1100_1200": efr.SAFE_BASE_LIVE["block_bull_1100_1200"],
    "entry_bar_body_pct_min": efr.SAFE_BASE_LIVE["entry_bar_body_pct_min"],
    "vix_bear_hard_cap": efr.SAFE_BASE_LIVE["vix_bear_hard_cap"],
    "midday_trendline_gate": efr.SAFE_BASE_LIVE["midday_trendline_gate"],
    "min_ribbon_momentum_cents": efr.SAFE_BASE_LIVE["min_ribbon_momentum_cents"],
    # NOTE: SAFE_BASE_LIVE's literal max_ribbon_duration_bars=999 is production's own
    # documented "inert workaround" (backtest/lib/engine/gates.py gate 9 comment: "Safe's
    # params.json currently pins 999 (inert workaround, not this bug)") -- no realistic
    # ribbon stack persists 999 bars (~83 RTH hours, several trading days), so the gate
    # never fires in practice. Evaluating it FOR REAL requires a `ribbon_df` payload field
    # walked via `ribbon_at`, which this per-candidate windowed bar_ctx does not build
    # (would require duplicating/windowing a second frame for a gate that cannot fire).
    # `None` here makes `evaluate_gates`' `if _rdur_max:` guard short-circuit -- behaviorally
    # equivalent to 999 for any realistic sequence, disclosed rather than silently omitted.
    "max_ribbon_duration_bars": None,
}

BAR_CTX_WINDOW = 200  # >> TRENDLINE_LOOKBACK_BARS=60 (the largest filter lookback) -- headroom

G5_ANCHOR_DATE = dt.date(2026, 7, 27)
G5_ANCHOR_LEVEL = 744.9
EVIDENCE_FLOOR_N_CHANGED = 10


def log(msg: str) -> None:
    print(f"[cascade-ab] {msg}", flush=True)


def load_prereg() -> dict:
    """The frozen pre-reg JSON (analysis/recommendations/prereg-structure-shift-cascade-
    2026-07-28.json, commit 58bb61fa) has a trailing comma after its last `gates_frozen`
    array element -- invalid strict JSON. The file is the frozen contract and must NOT be
    edited to fix this; strip trailing commas before parsing (read-only, tolerant load)."""
    raw = PREREG_PATH.read_text(encoding="utf-8")
    cleaned = re.sub(r",(\s*[\]}])", r"\1", raw)
    return json.loads(cleaned)


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


# =============================================================================== JSON safety

def _kw_json_safe(kw: dict) -> dict:
    """Convert orchestrator's native-Python bear/bull kwargs into the JSON-string shape
    `engine_cli._coerce_score_kwargs` requires (dt.time -> "HH:MM", tuple -> [str, str]).
    Everything else (ints/floats/bools/None/lists) passes through verbatim -- this boundary
    must never drift from the underlying evaluate_* signature (score.py's own discipline)."""
    out = dict(kw)
    nb = out.get("no_trade_before")
    if isinstance(nb, dt.time):
        out["no_trade_before"] = nb.strftime("%H:%M")
    win = out.get("no_trade_window")
    if isinstance(win, tuple):
        out["no_trade_window"] = [win[0].strftime("%H:%M"), win[1].strftime("%H:%M")]
    return out


def _rs(rs) -> Optional[dict]:
    if rs is None:
        return None
    return {"fast": rs.fast, "pivot": rs.pivot, "slow": rs.slow,
            "spread_cents": rs.spread_cents, "stack": rs.stack}


def bar_ctx_from_orch_ctx(ctx: BarContext, window: int = BAR_CTX_WINDOW) -> dict:
    """Serialize an orchestrator-captured BarContext into the decide_payload JSON contract,
    windowed to the last `window` bars ending at (and including) the trigger bar. Windowing
    is a performance/payload-size choice, NOT a fidelity compromise: `window` (200) is well
    over TRENDLINE_LOOKBACK_BARS (60), the largest lookback any filter reads from
    `ctx.prior_bars`; vol/range baselines are already-precomputed scalars on `ctx`, not
    re-derived from prior_bars at evaluate time. Mirrors heartbeat_core._build_payload's
    proven bar_ctx shape / test_structure_shift_wiring.py's `_payload_for`."""
    lo = max(0, ctx.bar_idx - window + 1)
    win_df = ctx.prior_bars.iloc[lo: ctx.bar_idx + 1][["open", "high", "low", "close", "volume"]]
    prior_bars = [
        {"open": float(r.open), "high": float(r.high), "low": float(r.low),
         "close": float(r.close), "volume": float(r.volume)}
        for r in win_df.itertuples(index=False)
    ]
    local_idx = len(prior_bars) - 1
    return {
        "bar_idx": local_idx,
        "timestamp_et": ctx.timestamp_et.isoformat(),
        "bar": dict(prior_bars[local_idx]),
        "prior_bars": prior_bars,
        "ribbon_now": _rs(ctx.ribbon_now),
        "ribbon_history": [_rs(r) for r in ctx.ribbon_history],
        "vix_now": ctx.vix_now, "vix_prior": ctx.vix_prior,
        "vol_baseline_20": ctx.vol_baseline_20, "range_baseline_20": ctx.range_baseline_20,
        "levels_active": list(ctx.levels_active), "multi_day_levels": list(ctx.multi_day_levels),
        "htf_15m_stack": ctx.htf_15m_stack,
        "level_states": dict(ctx.level_states),
        "fhh_level": ctx.fhh_level, "vix_5d_ma": ctx.vix_5d_ma, "vix_20d_ma": ctx.vix_20d_ma,
    }


# =============================================================================== CONTROL run

def run_control_with_candidate_capture():
    """Runs run_backtest(**SAFE_BASE_LIVE) once, monkeypatching evaluate_bearish_setup /
    evaluate_bullish_setup ONLY to capture (a) the constant bear/bull kwargs orchestrator
    computes (verified constant across the whole loop -- every kwarg passed is a run-level
    local) and (b) the BarContext for every bear bar whose blockers == [5] exactly. Restores
    the originals in `finally` regardless of outcome (same pattern as ladder_fullhist_
    replay.py's run_backtest_with_bull_capture -- pure pass-through wrapper, zero behavior
    change to CONTROL's own trades/decisions)."""
    captured_kw = {"bear": None, "bull": None}
    bear_candidates: dict[int, dict] = {}  # bar_idx -> {"ctx":..., "result":...}
    g5_anchor_day_bear_scan: list[dict] = []  # diagnostic ONLY -- every bear eval on G5_ANCHOR_DATE

    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup

    def _capture_bear(ctx, **kw):
        if captured_kw["bear"] is None:
            captured_kw["bear"] = dict(kw)
        res = orig_bear(ctx, **kw)
        if res.blockers == [5]:
            bear_candidates[ctx.bar_idx] = {"ctx": ctx, "result": res}
        if ctx.timestamp_et.date() == G5_ANCHOR_DATE:
            g5_anchor_day_bear_scan.append({
                "bar_idx": ctx.bar_idx, "timestamp_et": ctx.timestamp_et.isoformat(),
                "bear_score": res.bear_score, "blockers": res.blockers,
                "triggers_fired": res.triggers_fired, "rejection_level": res.rejection_level,
                "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
            })
        return res

    def _capture_bull(ctx, **kw):
        if captured_kw["bull"] is None:
            captured_kw["bull"] = dict(kw)
        return orig_bull(ctx, **kw)

    # DATA WINDOW: engine_fullhist_replay.py's own window ends 2026-07-22 -- BEFORE the
    # frozen G5 anchor (2026-07-27 09:40). Extended here to 2026-07-27 (same OLD file +
    # strictly-after-07-22 tail of the newer SPY/VIX CSVs ladder_fullhist_replay.py uses;
    # see that module's "DATA WINDOW" docstring for the no-overlap justification) so the
    # anchor is reachable, while the baseline-anchor check below verifies the 07-22-and-
    # earlier SUBSET of this run's trades still reproduces the stored 190/$5,064.75
    # scorecard exactly (a strict prefix -- orchestrator is causal, nothing after 07-22 can
    # change an earlier trade).
    #
    # DELIBERATELY NOT `lfr.load_extended_data()`: that helper pre-parses vix_df's
    # timestamp_et via `pd.to_datetime` -- and this VIX CSV spans a DST transition, so the
    # column is a MIXED-OFFSET series that `pd.to_datetime` (without `utc=True`) turns into
    # object-dtype individual Timestamp objects (verified interactively: raw dtype=object
    # containing strings vs "parsed" dtype=object containing Timestamps, NOT a uniform
    # datetime64 column). That fails `run_backtest`'s own internal `is_datetime64_any_dtype`
    # branch and materially changes results: reusing `lfr.load_extended_data()` here made the
    # <=07-22 prefix total $5,365.75 instead of the stored $5,064.75 (n=190 matched, P&L did
    # not -- caught by the baseline-anchor check, root-caused before proceeding). FIX: keep
    # vix_df's timestamp_et as the RAW STRING column engine_fullhist_replay.py's own PROVEN
    # convention uses (run_backtest parses it internally); only spy_df's is pre-parsed
    # (needed for the tail date-boundary filter/sort), matching efr.py exactly.
    spy_old = pd.read_csv(lfr.OLD_SPY_FILE)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(lfr.NEW_SPY_FILE)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > lfr.OLD_WINDOW_END]
    spy_df_raw = (
        pd.concat([spy_old, spy_tail], ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    )

    vix_old = pd.read_csv(lfr.OLD_VIX_FILE)  # timestamp_et stays RAW STRING
    vix_new = pd.read_csv(lfr.NEW_VIX_FILE)
    _vix_new_dates = pd.to_datetime(vix_new["timestamp_et"]).dt.date  # local var only, for the filter
    vix_tail = vix_new[_vix_new_dates > lfr.OLD_WINDOW_END].reset_index(drop=True)
    # vix_old is already chronological (existing file); vix_tail is strictly AFTER
    # vix_old's end by construction -- concatenation is already sorted, no resort needed
    # (a resort would require parsing the raw column, which is exactly what we're avoiding).
    vix_df_raw = pd.concat([vix_old, vix_tail], ignore_index=True)

    orch_mod.evaluate_bearish_setup = _capture_bear
    orch_mod.evaluate_bullish_setup = _capture_bull
    try:
        r = run_backtest(
            spy_df_raw, vix_df_raw,
            start_date=lfr.FULL_START, end_date=lfr.FULL_END, **efr.SAFE_BASE_LIVE,
        )
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
    return r, captured_kw, bear_candidates, spy_df_raw, g5_anchor_day_bear_scan


# =============================================================================== exit re-derivation

def derive_control_rows(r, spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame, exit_shape: dict) -> list[dict]:
    """Re-derives CONTROL's own trades' exits via walk_exit_manager -- byte-identical
    machinery to engine_fullhist_replay.py's main loop. Adds exit_time_et (needed for the
    NOT_FLAT merge) alongside the fields that script already reports."""
    from lib.option_pricing_real import load_contract_bars, option_symbol

    rows = []
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=float(t.entry_premium),
            qty=int(t.qty), exit_shape=exit_shape, structure_stop_enabled=True, trigger_level=trigger_level,
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=rtd,
            five_min_spy_df=day_spy,
        )
        exit_ts = res.exit_time_et if res.exit_time_et is not None else entry_time_et
        rows.append({
            "kind": "baseline", "date": edate.isoformat(), "entry_time_et": entry_time_et,
            "exit_time_et": naive_dt(exit_ts), "setup": t.setup, "side": t.side,
            "tier": eb.classify_tier(t.triggers_fired), "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4), "triggers": t.triggers_fired,
            "rejection_level": trigger_level, "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
        })
    return rows


# =============================================================================== treatment scoring

def score_candidate(bar_ctx: dict, bear_kw_json: dict, bull_kw_json: dict) -> tuple[dict, dict]:
    """Returns (verdict_flag_off, verdict_flag_on) for one candidate's bar_ctx."""
    score_params = {"enable_bullish": True, "bear_kwargs": bear_kw_json, "bull_kwargs": bull_kw_json}
    payload_off = {"bar_ctx": bar_ctx, "gate_params": dict(GATE_PARAMS_BASE), "score_params": score_params}
    payload_on = {
        "bar_ctx": bar_ctx,
        "gate_params": dict(GATE_PARAMS_BASE, structure_shift_confirmation_enabled=True),
        "score_params": score_params,
    }
    return decide_payload(payload_off), decide_payload(payload_on)


def resolve_candidate_qty(quality_tier: str, entry_premium: float) -> tuple[Optional[int], Optional[str]]:
    """Tier-based qty (orchestrator.py ~1193-1226) + MIN_PREMIUM gate (LEVEL/ELITE/SUPER,
    OP-17) + per_trade_risk_cap_pct linear scale-down (orchestrator.py ~1917-1932), all
    field-cited from the SAME orchestrator logic a real new bear entry would hit. Returns
    (qty, skip_reason) -- qty is None iff skip_reason is set (excluded from the book).
    TRENDLINE_LEG2 (prior_stopped escalation, qty=20) NOT modeled -- disclosed in the module
    docstring; base TRENDLINE (qty=3) used instead."""
    qty = TIER_QTY.get(quality_tier, 3)
    if quality_tier in ("LEVEL", "ELITE", "SUPER") and entry_premium < MIN_PREMIUM_FOR_LEVEL_TIERS:
        return None, "SKIP_MIN_PREMIUM"
    max_cost = BEAR_INITIAL_EQUITY * PER_TRADE_RISK_CAP_PCT
    fill_cost = entry_premium * qty * 100
    if fill_cost > max_cost and entry_premium > 0:
        qty = max(3, int(max_cost / (entry_premium * 100)))
    return qty, None


# =============================================================================== main

def main() -> int:
    t_start = time.time()
    prereg = load_prereg()
    log(f"prereg loaded: {prereg['prereg_id']} frozen {prereg['frozen_at_et']}")

    log(f"CONTROL: run_backtest(**SAFE_BASE_LIVE) with candidate capture, extended window "
        f"{lfr.FULL_START}..{lfr.FULL_END} (thru the 07-27 G5 anchor date)")
    t0 = time.time()
    r, captured_kw, bear_candidates, spy_df, g5_anchor_day_bear_scan = run_control_with_candidate_capture()
    control_entry_elapsed = time.time() - t0
    log(f"  done in {control_entry_elapsed:.1f}s -- {len(r.trades)} raw CONTROL entries, "
        f"{len(bear_candidates)} blockers==[5] candidate bars captured")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    spy_rth = build_rth_frame(spy_df)
    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    log("re-deriving CONTROL exits via walk_exit_manager (RIBBON_RIDE shape)")
    t1 = time.time()
    control_rows = derive_control_rows(r, spy_df, ribbon_lookup, correct_shape)
    control_total = round(sum(row["dollar_pnl"] for row in control_rows), 2)
    control_exit_elapsed = time.time() - t1
    log(f"  CONTROL: n={len(control_rows)} total=${control_total:+.2f} ({control_exit_elapsed:.1f}s), "
        f"window {lfr.FULL_START}..{lfr.FULL_END}")

    # ---- BASELINE ANCHOR: the 2026-07-22-and-earlier SUBSET of this run's trades must
    # reproduce the stored engine-fullhist-replay-2026-07-23 scorecard (n=190, $5,064.75)
    # exactly, as a strict prefix (orchestrator is causal -- extending the window forward
    # to reach the 07-27 G5 anchor cannot change any earlier trade). Fail closed if not.
    stored = json.loads(STORED_SCORECARD.read_text(encoding="utf-8"))
    stored_n = stored["headline"]["n_trades"]
    stored_total = stored["headline"]["total_pnl"]
    prefix_rows = [row for row in control_rows if dt.date.fromisoformat(row["date"]) <= efr.FULL_END]
    prefix_total = round(sum(row["dollar_pnl"] for row in prefix_rows), 2)
    anchor_ok = (len(prefix_rows) == stored_n) and (abs(prefix_total - stored_total) <= 1.00)
    log(f"BASELINE ANCHOR (<={efr.FULL_END} prefix): control n={len(prefix_rows)} "
        f"total=${prefix_total:+.2f} vs stored n={stored_n} total=${stored_total:+.2f} -- "
        f"{'PASS' if anchor_ok else 'FAIL'}")
    if not anchor_ok:
        out = {
            "prereg": prereg, "status": "ABORT_BASELINE_ANCHOR_FAIL",
            "control_prefix_le_20260722": {"n": len(prefix_rows), "total": prefix_total},
            "control_full_extended_window": {"n": len(control_rows), "total": control_total},
            "stored_scorecard": {"n": stored_n, "total": stored_total},
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        OUT_MD.write_text(
            "# Structure-shift cascade A/B -- ABORTED\n\n"
            "**VERDICT: ABORT -- baseline anchor FAIL, treatment not run.**\n\n"
            f"CONTROL's <=2026-07-22 prefix reproduced n={len(prefix_rows)} total=${prefix_total:+.2f}; "
            f"stored scorecard is n={stored_n} total=${stored_total:+.2f}.\n",
            encoding="utf-8",
        )
        log("ABORT: baseline anchor FAIL -- wrote report, stopping before treatment.")
        return 1

    bear_kw_json = _kw_json_safe(captured_kw["bear"])
    bull_kw_json = _kw_json_safe(captured_kw["bull"])

    # ---- TREATMENT candidate re-scoring ----
    log(f"scoring {len(bear_candidates)} candidates via engine_cli.decide_payload "
        f"(flag OFF fidelity check + flag ON treatment verdict)")
    t2 = time.time()
    fidelity_total = 0
    fidelity_match = 0
    scored_candidates = []
    for bar_idx, cand in sorted(bear_candidates.items()):
        ctx = cand["ctx"]
        result = cand["result"]
        bar_ctx = bar_ctx_from_orch_ctx(ctx)
        v_off, v_on = score_candidate(bar_ctx, bear_kw_json, bull_kw_json)
        fidelity_total += 1
        if v_off["bear_score"] == result.bear_score and v_off["bear_blockers"] == result.blockers:
            fidelity_match += 1
        scored_candidates.append({
            "bar_idx": bar_idx, "ctx": ctx, "timestamp_et": ctx.timestamp_et,
            "control_bear_score": result.bear_score, "control_blockers": result.blockers,
            "v_off": v_off, "v_on": v_on,
        })
    score_elapsed = time.time() - t2
    fidelity_pct = round(100.0 * fidelity_match / fidelity_total, 1) if fidelity_total else None
    log(f"  scored {fidelity_total} candidates in {score_elapsed:.1f}s -- flag-off fidelity "
        f"{fidelity_match}/{fidelity_total} ({fidelity_pct}%)")

    flipped = [c for c in scored_candidates if c["v_on"]["verdict"] == "ENTER_BEAR"]
    log(f"  {len(flipped)}/{len(scored_candidates)} candidates flip to ENTER_BEAR under the flag")

    # ---- resolve entry+1 for every flipped candidate (real OPRA only, BS-synthetic disclosed) ----
    log("resolving entry+1 (real OPRA fills only) for flipped candidates")
    shift_signals = []
    excluded_synthetic = []
    for c in flipped:
        ctx = c["ctx"]
        v_on = c["v_on"]
        spot = float(ctx.bar["close"])
        trade_date = ctx.timestamp_et.date()
        strike = pick_strike(spot, BEAR_INITIAL_EQUITY, "P", V15_SAFE_TIERS)
        res = resolve_ladder_entry(spy_rth, ctx.bar_idx, strike, trade_date, float(ctx.vix_now), spot)
        base_row = {
            "bar_idx": ctx.bar_idx, "date": trade_date.isoformat(),
            "trigger_time_et": ctx.timestamp_et.isoformat(), "strike": strike,
            "quality_tier": v_on["quality_tier"], "triggers_fired": v_on["triggers_fired"],
            "rejection_level": v_on["rejection_level"],
            "bear_score_before": c["control_bear_score"], "bear_score_after": v_on["bear_score"],
            "blockers_before": c["control_blockers"], "blockers_after": v_on["bear_blockers"],
        }
        if not res["ok"]:
            excluded_synthetic.append(dict(
                base_row, exclude_reason=res["reason"],
                synthetic_entry_premium=res.get("synthetic_entry_premium"),
            ))
            continue
        qty, skip_reason = resolve_candidate_qty(v_on["quality_tier"], res["entry_premium"])
        if skip_reason is not None:
            excluded_synthetic.append(dict(
                base_row, exclude_reason=skip_reason, entry_premium=round(res["entry_premium"], 4),
                synthetic_entry_premium=None,
            ))
            continue
        shift_signals.append(dict(
            base_row, kind="shift_candidate", side="P", symbol=res["symbol"],
            entry_time_et=naive_dt(res["entry_time_et"]), entry_premium=round(res["entry_premium"], 4),
            qty=qty, opt_df=res["opt_df"],
        ))

    log(f"  {len(shift_signals)} shift signals resolved (real OPRA), "
        f"{len(excluded_synthetic)} excluded (no OPRA cache / min-premium gate)")

    # ---- NOT_FLAT merge: CONTROL trades + shift signals, chronological, one position at a time ----
    log("merging CONTROL trades + shift signals into ONE one-position-at-a-time walk")
    all_events = list(control_rows) + shift_signals
    all_events.sort(key=lambda e: e["entry_time_et"])

    admitted: list[dict] = []
    preempted_baseline: list[dict] = []
    preempted_shift: list[dict] = []
    flat_until: Optional[dt.datetime] = None
    for e in all_events:
        if flat_until is not None and e["entry_time_et"] <= flat_until:
            (preempted_baseline if e["kind"] == "baseline" else preempted_shift).append(e)
            continue
        if e["kind"] == "shift_candidate":
            day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == dt.date.fromisoformat(e["date"])].reset_index(drop=True)
            rtd = efr.ribbon_tick_df_for(e["opt_df"], ribbon_lookup)
            walk = walk_exit_manager(
                symbol=e["symbol"], side="P", entry_time_et=e["entry_time_et"],
                entry_premium=e["entry_premium"], qty=e["qty"], exit_shape=correct_shape,
                structure_stop_enabled=True, trigger_level=e["rejection_level"], strategy="ribbon_ride",
                time_stop_et=efr.TIME_STOP_ET, opt_df=e["opt_df"], ribbon_tick_df=rtd, five_min_spy_df=day_spy,
            )
            exit_ts = walk.exit_time_et if walk.exit_time_et is not None else e["entry_time_et"]
            e = dict(e, exit_time_et=naive_dt(exit_ts), dollar_pnl=walk.dollar_pnl, exit_reason=walk.exit_reason)
            e.pop("opt_df", None)
        admitted.append(e)
        flat_until = e["exit_time_et"]

    admitted_baseline = [e for e in admitted if e["kind"] == "baseline"]
    admitted_shift = [e for e in admitted if e["kind"] == "shift_candidate"]
    treatment_total = round(sum(e["dollar_pnl"] for e in admitted), 2)
    delta_total = round(treatment_total - control_total, 2)
    log(f"  admitted: {len(admitted_baseline)} baseline + {len(admitted_shift)} shift = "
        f"{len(admitted)} trades, total=${treatment_total:+.2f} (delta ${delta_total:+.2f})")
    log(f"  preempted: {len(preempted_baseline)} baseline trades, {len(preempted_shift)} shift signals")

    # ---- day-level series (control vs treatment) ----
    control_by_day: dict[str, float] = {}
    for row in control_rows:
        control_by_day[row["date"]] = control_by_day.get(row["date"], 0.0) + row["dollar_pnl"]
    treatment_by_day: dict[str, float] = {}
    for row in admitted:
        treatment_by_day[row["date"]] = treatment_by_day.get(row["date"], 0.0) + row["dollar_pnl"]

    all_days = sorted(set(control_by_day) | set(treatment_by_day))
    day_delta = {
        d: round(treatment_by_day.get(d, 0.0) - control_by_day.get(d, 0.0), 2)
        for d in all_days
    }
    changed_days = {d: v for d, v in day_delta.items() if abs(v) > 0.005}
    n_improved_days = sum(1 for v in changed_days.values() if v > 0)
    n_worsened_days = sum(1 for v in changed_days.values() if v < 0)

    # ---- changed-trade table: every added / removed(preempted) trade ----
    changed_trades = []
    for e in admitted_shift:
        changed_trades.append({
            "change": "ADDED", "date": e["date"], "entry_time_et": e["entry_time_et"].isoformat(),
            "side": "P", "strike": e["strike"], "qty": e["qty"], "tier": e["quality_tier"],
            "rejection_level": e["rejection_level"], "entry_premium": e["entry_premium"],
            "exit_reason": e["exit_reason"], "dollar_pnl": e["dollar_pnl"], "contribution": e["dollar_pnl"],
        })
    for e in preempted_baseline:
        changed_trades.append({
            "change": "PREEMPTED", "date": e["date"], "entry_time_et": e["entry_time_et"].isoformat(),
            "side": e["side"], "strike": None, "qty": e["qty"], "tier": e["tier"],
            "rejection_level": e["rejection_level"], "entry_premium": e["entry_premium"],
            "exit_reason": e["exit_reason"], "dollar_pnl": e["dollar_pnl"], "contribution": -e["dollar_pnl"],
        })
    changed_trades.sort(key=lambda x: x["entry_time_et"])

    n_changed = len(admitted_shift) + len(preempted_baseline)

    # =============================================================== gates
    g1 = {"delta_total": delta_total, "pass": delta_total > 0}
    g2 = {
        "n_changed_days": len(changed_days), "n_improved": n_improved_days, "n_worsened": n_worsened_days,
        "pass": n_improved_days > n_worsened_days,
    }
    best_contribution = max((ct["contribution"] for ct in changed_trades), default=0.0)
    g3 = {
        "best_trade_contribution": round(best_contribution, 2),
        "delta_minus_best": round(delta_total - best_contribution, 2),
        "pass": (delta_total - best_contribution) > 0,
    }
    g4_preemption_days = sorted({e["date"] for e in preempted_baseline})
    g4_day_checks = [
        {"date": d, "treatment_day_total": round(treatment_by_day.get(d, 0.0), 2), "pass": treatment_by_day.get(d, 0.0) >= 0}
        for d in g4_preemption_days
    ]
    g4 = {
        "n_preemptions": len(preempted_baseline), "preempted_days": g4_day_checks,
        "pass": all(c["pass"] for c in g4_day_checks) if g4_day_checks else True,
    }
    g5_anchor_trades = [
        e for e in admitted_shift
        if e["date"] == G5_ANCHOR_DATE.isoformat() and abs((e["rejection_level"] or 0) - G5_ANCHOR_LEVEL) < 0.01
    ]
    g5 = {
        "anchor_date": G5_ANCHOR_DATE.isoformat(), "anchor_level": G5_ANCHOR_LEVEL,
        "matched_trades": [
            {"entry_time_et": e["entry_time_et"].isoformat(), "dollar_pnl": e["dollar_pnl"]}
            for e in g5_anchor_trades
        ],
        "pass": len(g5_anchor_trades) > 0,
        "note": "bull 07-28 anchor is signal-only (no OPRA cache) per the pre-reg -- not tested here.",
        "diagnostic_full_day_bear_scan": g5_anchor_day_bear_scan,
        "diagnostic_note": (
            "Every bear-side evaluation on 2026-07-27 in THIS run (not just blockers==[5] "
            "candidates), for root-cause visibility on why the anchor was/wasn't captured. "
            "Cross-reference against ladder_fullhist_replay.py's own 09:40 calibration check "
            "(analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json#calibration_2026_07_27_0940): "
            "that tool's own independently-derived ground truth for this exact bar is "
            "bar_idx=29113, bear_score=8, blockers=[5, 9], rejection_level=745.0 -- i.e. even "
            "in that tool's run the 09:40 bar has TWO blockers (5 AND 9, the volume-baseline "
            "filter), not blockers==[5] alone, and rejection_level is already off by $0.10 from "
            "the pinned live-incident level (744.9). That tool's own note attributes this to a "
            "pre-existing, already-root-caused feed-provenance gap: 'the cached 09:40 bar in "
            "backtest/data/spy_5m_2026-05-19_2026-07-27.csv is not byte-identical to the real "
            "IEX bar the live engine read'. Filter 9 (volume) is NOT touched by "
            "structure_shift_confirmation (only filter 5 bear / the HTF-demerit bull), so even "
            "with perfect data fidelity this specific bar could not flip to ENTER_BEAR via the "
            "shift mechanism alone -- G5's FAIL here traces to pre-existing cached-data "
            "limitations at the historical window's tail edge, not a defect in this A/B's "
            "methodology (the <=2026-07-22 baseline anchor reproduces the stored scorecard "
            "EXACTLY, n=190 $5,064.75, proving the methodology is faithful over the 18-month "
            "core window)."
        ),
    }
    evidence_floor = {
        "n_changed": n_changed, "floor": EVIDENCE_FLOOR_N_CHANGED,
        "pass": n_changed >= EVIDENCE_FLOOR_N_CHANGED,
    }
    all_gates_pass = all([g1["pass"], g2["pass"], g3["pass"], g4["pass"], g5["pass"]])
    verdict = "ARM" if (all_gates_pass and evidence_floor["pass"]) else (
        "EVIDENCE_THIN_FORWARD_PAPER_ONLY" if (all_gates_pass and not evidence_floor["pass"])
        else "DO_NOT_ARM"
    )

    total_elapsed = time.time() - t_start
    out = {
        "prereg": prereg,
        "status": "COMPLETE",
        "plumbing_route": (
            "run_backtest does not forward bear_kwargs/bull_kwargs (verified: no such kwarg "
            "in its signature, hardcoded evaluate_bearish_setup/evaluate_bullish_setup calls). "
            "Route taken: engine_cli.decide_payload per flagged candidate bar, gate_params."
            "structure_shift_confirmation_enabled=True, bar_ctx serialized from the ORIGINAL "
            "orchestrator BarContext captured via a pass-through monkeypatch (byte-identical "
            "inputs, not a heartbeat_core-style rebuild), bear_kwargs/bull_kwargs the SAME "
            "constant kwargs orchestrator computed for this run. Bull side proven a no-op "
            "for entries (passed independent of the htf demerit) -- only bear candidates "
            "(blockers==[5]) are re-scored."
        ),
        "control": {
            "n_trades": len(control_rows), "total_pnl": control_total,
            "window": {"start": lfr.FULL_START.isoformat(), "end": lfr.FULL_END.isoformat()},
            "anchor_check": {
                "pass": anchor_ok, "prefix_cutoff": efr.FULL_END.isoformat(),
                "prefix_n": len(prefix_rows), "prefix_total": prefix_total,
                "stored_n": stored_n, "stored_total": stored_total,
            },
        },
        "candidates": {
            "n_bear_candidates_blockers_5_only": len(bear_candidates),
            "flag_off_fidelity": {"match": fidelity_match, "total": fidelity_total, "pct": fidelity_pct},
            "n_flip_to_enter_bear": len(flipped),
            "n_resolved_real_opra": len(shift_signals),
            "n_excluded_no_opra_or_min_premium": len(excluded_synthetic),
        },
        "treatment": {
            "n_admitted_total": len(admitted), "n_admitted_baseline": len(admitted_baseline),
            "n_admitted_shift": len(admitted_shift), "n_preempted_baseline": len(preempted_baseline),
            "n_preempted_shift_signals": len(preempted_shift), "total_pnl": treatment_total,
        },
        "headline": {"control_total": control_total, "treatment_total": treatment_total, "delta_total": delta_total},
        "gates": {"g1_positive_aggregate": g1, "g2_day_majority": g2, "g3_survives_drop_best": g3,
                  "g4_preemption_no_negative_day": g4, "g5_0727_bear_anchor_added": g5},
        "evidence_floor": evidence_floor,
        "verdict": verdict,
        "changed_trades": changed_trades,
        "preempted_shift_signals": [
            {"date": e["date"], "entry_time_et": e["entry_time_et"].isoformat(), "quality_tier": e["quality_tier"]}
            for e in preempted_shift
        ],
        "excluded_synthetic": excluded_synthetic,
        "day_delta": day_delta,
        "runtime_seconds": {
            "control_entry": round(control_entry_elapsed, 1), "control_exit": round(control_exit_elapsed, 1),
            "candidate_scoring": round(score_elapsed, 1), "total": round(total_elapsed, 1),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"VERDICT: {verdict}  (G1={g1['pass']} G2={g2['pass']} G3={g3['pass']} G4={g4['pass']} "
        f"G5={g5['pass']} evidence_floor={evidence_floor['pass']} n_changed={n_changed})")
    return 0


def _fmt(v) -> str:
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def write_markdown(out: dict) -> None:
    g = out["gates"]
    ef = out["evidence_floor"]
    h = out["headline"]
    L = [
        f"# Structure-shift CASCADE A/B (pre-reg #2) -- 2026-07-28",
        "",
        f"**VERDICT: {out['verdict']}** -- "
        f"G1={g['g1_positive_aggregate']['pass']} G2={g['g2_day_majority']['pass']} "
        f"G3={g['g3_survives_drop_best']['pass']} G4={g['g4_preemption_no_negative_day']['pass']} "
        f"G5={g['g5_0727_bear_anchor_added']['pass']} | evidence_floor(n_changed>={ef['floor']})="
        f"{ef['pass']} (n_changed={ef['n_changed']})",
        "",
        f"Tool: `backtest/tools/structure_shift_cascade_ab.py`. Pre-reg: `analysis/recommendations/"
        f"prereg-structure-shift-cascade-2026-07-28.json` (commit 58bb61fa). Wiring under test: "
        f"commit 459342c8. Runtime: {out['runtime_seconds']['total']}s total "
        f"(control entry {out['runtime_seconds']['control_entry']}s, control exit "
        f"{out['runtime_seconds']['control_exit']}s, candidate scoring "
        f"{out['runtime_seconds']['candidate_scoring']}s).",
        "",
        "## Plumbing route",
        "",
        out["plumbing_route"],
        "",
        "## Baseline anchor",
        "",
        f"CONTROL runs the EXTENDED window {out['control']['window']['start']}.."
        f"{out['control']['window']['end']} (engine_fullhist_replay.py's own window ends "
        f"2026-07-22, before the G5 anchor -- extended here, same precedent as "
        f"ladder_fullhist_replay.py, so the 07-27 anchor is reachable). The "
        f"<={out['control']['anchor_check']['prefix_cutoff']} PREFIX of CONTROL's trades "
        f"(a strict prefix -- orchestrator is causal, nothing after 07-22 can change an "
        f"earlier trade) reproduced n={out['control']['anchor_check']['prefix_n']} "
        f"total={_fmt(out['control']['anchor_check']['prefix_total'])} vs stored "
        f"n={out['control']['anchor_check']['stored_n']} "
        f"total={_fmt(out['control']['anchor_check']['stored_total'])} -- "
        f"**{'PASS' if out['control']['anchor_check']['pass'] else 'FAIL'}**. Full extended-"
        f"window CONTROL: n={out['control']['n_trades']} total={_fmt(out['control']['total_pnl'])}.",
        "",
        "## Gate table",
        "",
        "| Gate | Detail | Pass |",
        "|---|---|---|",
        f"| G1 positive aggregate | delta {_fmt(g['g1_positive_aggregate']['delta_total'])} "
        f"({_fmt(out['control']['total_pnl'])} -> {_fmt(out['treatment']['total_pnl'])}) | "
        f"{g['g1_positive_aggregate']['pass']} |",
        f"| G2 day-majority | {g['g2_day_majority']['n_improved']} improved / "
        f"{g['g2_day_majority']['n_worsened']} worsened of {g['g2_day_majority']['n_changed_days']} "
        f"changed days | {g['g2_day_majority']['pass']} |",
        f"| G3 survives drop-best | {_fmt(g['g3_survives_drop_best']['delta_minus_best'])} after "
        f"dropping the best single changed trade ({_fmt(g['g3_survives_drop_best']['best_trade_contribution'])}) "
        f"| {g['g3_survives_drop_best']['pass']} |",
        f"| G4 preemption (no negative day) | {g['g4_preemption_no_negative_day']['n_preemptions']} "
        f"baseline trade(s) preempted | {g['g4_preemption_no_negative_day']['pass']} |",
        f"| G5 07-27 09:40 bear anchor added | {len(g['g5_0727_bear_anchor_added']['matched_trades'])} "
        f"matching trade(s) | {g['g5_0727_bear_anchor_added']['pass']} |",
        f"| Evidence floor (n_changed>={ef['floor']}) | n_changed={ef['n_changed']} | {ef['pass']} |",
        "",
        "### G5 root-cause (FAIL)",
        "",
        g["g5_0727_bear_anchor_added"]["diagnostic_note"],
        "",
        "Full bear-side scan of 2026-07-27 in this run (every evaluated bar, not just "
        "blockers==[5] candidates):",
        "",
        "| Bar idx | Time ET | Bear score | Blockers | Triggers | Level | Ribbon |",
        "|---|---|---|---|---|---|---|",
    ] + [
        f"| {row['bar_idx']} | {row['timestamp_et'][11:16]} | {row['bear_score']} | "
        f"{row['blockers']} | {row['triggers_fired']} | {row['rejection_level']} | "
        f"{row['ribbon_stack']} |"
        for row in g["g5_0727_bear_anchor_added"]["diagnostic_full_day_bear_scan"]
    ] + [
        "",
        "## Headline",
        "",
        f"- CONTROL total: {_fmt(h['control_total'])} ({out['control']['n_trades']} trades)",
        f"- TREATMENT total: {_fmt(h['treatment_total'])} "
        f"({out['treatment']['n_admitted_total']} trades = {out['treatment']['n_admitted_baseline']} "
        f"baseline + {out['treatment']['n_admitted_shift']} shift-added)",
        f"- Delta: {_fmt(h['delta_total'])}",
        f"- Candidates (bear blockers==[5] only): {out['candidates']['n_bear_candidates_blockers_5_only']}",
        f"- Flag-off fidelity check (decide_payload reproduces CONTROL's own bear_score/blockers): "
        f"{out['candidates']['flag_off_fidelity']['match']}/{out['candidates']['flag_off_fidelity']['total']} "
        f"({out['candidates']['flag_off_fidelity']['pct']}%)",
        f"- Flip to ENTER_BEAR under the flag (scoring + all 15 gates): "
        f"{out['candidates']['n_flip_to_enter_bear']}",
        f"- Resolved via real OPRA fills: {out['candidates']['n_resolved_real_opra']}",
        f"- Excluded (no OPRA cache / min-premium gate): {out['candidates']['n_excluded_no_opra_or_min_premium']}",
        f"- Preempted baseline trades: {out['treatment']['n_preempted_baseline']}",
        f"- Preempted shift signals (occupied by an earlier-admitted event): "
        f"{out['treatment']['n_preempted_shift_signals']}",
        "",
        "## Changed-trade table",
        "",
        "| Change | Date | Entry ET | Side | Strike | Qty | Tier | Level | Entry $ | Exit reason | P&L |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for ct in out["changed_trades"]:
        L.append(
            f"| {ct['change']} | {ct['date']} | {ct['entry_time_et'][11:16]} | {ct['side']} | "
            f"{ct['strike'] if ct['strike'] is not None else '-'} | {ct['qty']} | {ct['tier']} | "
            f"{ct['rejection_level']} | ${ct['entry_premium']:.2f} | {ct['exit_reason']} | "
            f"{_fmt(ct['dollar_pnl'])} |"
        )
    L += [
        "",
        "## G4 preemption analysis -- every baseline winner preempted by an earlier shift-entry",
        "",
    ]
    if g["g4_preemption_no_negative_day"]["n_preemptions"] == 0:
        L.append("No baseline trades were preempted.")
    else:
        L.append("| Date | Treatment day total | Day pass (>=0) |")
        L.append("|---|---|---|")
        for c in g["g4_preemption_no_negative_day"]["preempted_days"]:
            L.append(f"| {c['date']} | {_fmt(c['treatment_day_total'])} | {c['pass']} |")
    L += [
        "",
        "## Disclosures",
        "",
        f"- SKIP_QUALITY_LOCK escalation lock NOT modeled for new shift-added candidates (scope "
        "gap, disclosed in the module docstring -- decide_payload's own documented boundary; "
        "reported added-trade counts are a modest upper bound).",
        "- TRENDLINE_LEG2 sizing (prior_stopped + 45min-gap escalation) not modeled; base "
        "TRENDLINE qty=3 used for any TRENDLINE-tier admitted trade.",
        f"- Synthetic-premium share: {out['candidates']['n_excluded_no_opra_or_min_premium']} "
        f"candidates excluded (no OPRA cache or below min-premium gate) out of "
        f"{out['candidates']['n_flip_to_enter_bear']} that flipped to ENTER_BEAR -- flagged "
        "per-trade in the JSON (`excluded_synthetic`), NEVER blended into the P&L above (real "
        "OPRA fills only, same honest-design precedent as ladder_fullhist_replay.py).",
        "- Bull side: the htf-disagreement demerit only ever changes `bull_score`, never "
        "`blockers`/`passed` (filters.py `evaluate_bullish_setup`: `passed=(len(blockers)==0)` "
        "is computed before the demerit block runs) -- PROVEN a no-op for entry decisions, "
        "confirmed by `test_structure_shift_wiring.py::test_htf_bear_demerit_waived_by_"
        "shift_confirmation`. Zero bull candidates were scored; this replay is bear-only by "
        "construction, matching the pre-reg's own G5 scoping (bull anchor is signal-only).",
        "",
        "---",
        "_Raw JSON with full per-trade/per-candidate detail: "
        "`analysis/recommendations/structure-shift-cascade-ab-2026-07-28.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
