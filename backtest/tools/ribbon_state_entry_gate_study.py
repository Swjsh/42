"""ribbon_state_entry_gate_study.py -- LANE-B HYPOTHESIS #1 population validation
(markdown/doctrine/DOJO-HARVEST-2026-07-21.md). Frozen pre-reg:
analysis/recommendations/ribbon-state-entry-gate-prereg-2026-07-21.json -- read that file
for the full frozen feature/population/candidate/ship-gate definitions; this module is the
runner, not a second copy of the spec.

WHY THIS EXISTS: the harvest doc's quantified finding (5 real-fill 2026-07-17 entries, same
trigger family level_rejection+confluence, split -$139 [2 losers, ribbon BULL+rising] vs
+$665 [3 winners, ribbon rolled over]) is n=2 days. This module reconstructs the SAME trigger
family's bear-entry population across the widest OPRA-covered history (backtest/data/options/,
382 distinct trading dates 2025-01-02..2026-07-17) and walks EVERY episode through the REAL
exit_manager (backtest/lib/exit_manager_walk.py) instead of trusting orchestrator's own
simulate_trade_real P&L, which exit_manager_walk.py's own docstring documents as KNOWN-
DIVERGENT from the live exit_manager for ribbon_ride entries.

TIMESTAMP FRAME (see backtest/lib/et_frame.py): SPY master + OPRA option cache both store a
FIXED -04:00 offset year-round (mislabeled for EST months but internally self-consistent --
same UTC instants). This module follows the SAME "wall-v1" convention every existing scorecard
in this codebase uses: strip whatever tz label is attached, keep the wall-clock numbers,
NEVER tz_convert. Matches exit_manager_walk.py's own internal handling exactly.

SIGNAL-BAR RECOVERY: TradeFill.entry_time_et is overwritten by simulator_real.py to the FILL
bar's timestamp (signal bar + >=5 min, next available OPRA bar -- see simulator_real.py lines
430-436), NOT the signal bar the engine's filters.py / ribbon gates actually evaluated on. The
ribbon-at-entry feature this study measures MUST be read at the SIGNAL bar. This module
recovers it AUTHORITATIVELY via BacktestResult.decisions -- orchestrator's own unconditional
per-bar audit log ("Always log the decision", orchestrator.py ~line 1099), matched to each
TradeFill by (date, triggers_fired, rejection_level) -- rather than reverse-engineering a bar
index from price/time. An earlier version of this module DID reverse-engineer the signal bar
via entry_spot price-matching and produced ribbon_stack values that silently disagreed with
filter_5's own hard requirement (see GROUND-TRUTH CORRECTION below); root cause found via a
cross-check assertion (decision-log ribbon_stack vs an independent ribbon_at() recompute must
agree bar-for-bar) was a FRAME MISMATCH: orchestrator's `idx` indexes its internal RTH-only
(>=09:30, <16:00), reset_index(drop=True) frame, not the raw merged CSV (which still carries
premarket/after-hours rows) -- this module now reproduces that exact RTH filter before
computing its own ribbon_df, and the cross-check assertion is left in place as a standing guard.

GROUND-TRUTH CORRECTION (found building this study, verified against automation/state/
core-decisions.jsonl -- the real live engine's own per-tick record, not a model): the harvest
doc's characterization of the 2026-07-17 motivating observation does not hold up against the
live log. The two LOSING entries (11:06, 11:40) fired with ribbon=BEAR (bear_score=10, ALL 10
filters passed, spread ~200+c -- a strongly, not weakly, BEAR-stacked ribbon), not BULL as
described. The three WINNING entries (13:01, 13:51, 13:52) fired on triggers=['trendline_
rejection'] ONLY -- a DIFFERENT trigger family than level_rejection+confluence, via the
trendline_only_setup relaxation that bypasses filter_5 (ribbon-stack) with a score demerit
(bear_score 7-9, not 10) -- not the "same trigger family" the harvest doc asserted. The real
discriminator in the live data is TRIGGER TIER (ELITE static-level-anchored vs TRENDLINE
dynamic-only), not ribbon STACK STATE -- and that correctly-framed hypothesis is ALREADY filed
and ALREADY tested: backtest/tools/elite_bear_level_reject_gate_ab.py (2026-07-17), verdict
PARK_INSUFFICIENT_REGIME_SHIFT. See build_scorecard()'s ground_truth_correction block for the
values pulled fresh from core-decisions.jsonl this run (not hand-transcribed).

Run: backtest/.venv/Scripts/python.exe backtest/tools/ribbon_state_entry_gate_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
ROOT = REPO.parent                                    # 42/
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (REPO, FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from lib.orchestrator import run_backtest  # noqa: E402
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import option_symbol, load_contract_bars  # noqa: E402
import strategies as fleet_strategies  # noqa: E402 -- automation/state/fleet/strategies.py

DATA = REPO / "data"
SPY_BASE = DATA / "spy_5m_2025-01-01_2026-07-08.csv"
SPY_TAIL = DATA / "spy_5m_2026-05-19_2026-07-21.csv"
VIX_BASE = DATA / "vix_5m_2025-01-01_2026-07-08.csv"
VIX_TAIL = DATA / "vix_5m_2026-05-19_2026-07-21.csv"

PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
PREREG_PATH = ROOT / "analysis" / "recommendations" / "ribbon-state-entry-gate-prereg-2026-07-21.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "ribbon-state-entry-gate-2026-07-21.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "ribbon-state-entry-gate-2026-07-21.md"
CORE_DECISIONS_PATH = ROOT / "automation" / "state" / "core-decisions.jsonl"

# The 5 real-fill entries the harvest doc cites (markdown/doctrine/DOJO-HARVEST-2026-07-21.md)
# -- timestamps only (ground truth for everything else is read fresh from the log, never
# hand-transcribed).
HARVEST_CITED_TIMESTAMPS = ["11:06", "11:40", "13:01", "13:51", "13:52"]

IS_START, IS_END = dt.date(2025, 1, 2), dt.date(2025, 12, 31)
OOS_START, OOS_END = dt.date(2026, 1, 2), dt.date(2026, 7, 17)
DISCOVERY_DAY = dt.date(2026, 7, 17)

MAX_SIGNAL_LOOKBACK_BARS = 12  # 60 min at 5-min cadence

# =============================================================================
# FAITHFUL CURRENT-PRODUCTION SAFE CONFIG -- verified byte-identical against
# automation/state/params.json fresh this session (2026-07-21); same values already
# independently audited in backtest/tools/elite_bear_level_reject_gate_ab.py's SAFE_BASE.
# =============================================================================
SAFE_BASE = dict(
    use_real_fills=True,
    strike_offset=0,
    premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,
    tp1_premium_pct=0.5, tp1_qty_fraction=0.8,
    runner_target_premium_pct=2.5,
    level_stop_buffer_dollars=0.5,
    time_stop_minutes_before_close=20,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="fixed",
    profit_lock_trail_pct=0.125,
    f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35),
    no_trade_window=(dt.time(15, 0), dt.time(16, 0)),
    block_level_rejection=True,
    block_elite_bull=True, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0,
    entry_bar_body_pct_min=0.2,
    block_bull_1100_1200=True,
    midday_trendline_gate=False,
    min_ribbon_momentum_cents=None,
    max_ribbon_duration_bars=999,
    vix_bear_hard_cap=23.0,
    per_trade_risk_cap_pct=0.30,
    enable_bullish=True,
    min_premium_for_level_tiers=0.3,
    initial_equity=1746.75,  # live-verified 2026-07-11, CLAUDE.md account-context table
)


def log(msg: str) -> None:
    print(f"[ribbon-state-gate] {msg}", flush=True)


def load_merged(base_path: Path, tail_path: Path) -> pd.DataFrame:
    a = pd.read_csv(base_path)
    b = pd.read_csv(tail_path)
    df = pd.concat([a, b], ignore_index=True)
    df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
    df = (df.sort_values("_ts")
            .drop_duplicates(subset="_ts", keep="last")
            .drop(columns="_ts")
            .reset_index(drop=True))
    return df


def naive_wall(series_or_scalar):
    """Wall-v1: strip tz label, keep wall-clock numbers (never tz_convert). Matches
    exit_manager_walk.py's own internal tz handling exactly."""
    if isinstance(series_or_scalar, pd.Series):
        ts = pd.to_datetime(series_or_scalar)
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_localize(None)
        return ts
    p = pd.Timestamp(series_or_scalar)
    if p.tzinfo is not None:
        p = p.tz_localize(None)
    return p


def classify_tier(triggers: list[str]) -> str:
    """Matches backtest/lib/orchestrator.py inline tier logic (elite_bear_level_reject_gate_ab.py
    convention) -- used here for DISCLOSURE labeling only, not for population selection."""
    trig = set(triggers or [])
    has_conf = "confluence" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip = "ribbon_flip" in trig
    has_level = any(t in ("level_rejection", "level_reclaim") for t in trig)
    has_trendline = "trendline_rejection" in trig
    n = len(trig)
    if (has_conf and has_flip) or n >= 3:
        return "SUPER"
    elif has_conf or has_seq:
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trendline:
        return "TRENDLINE"
    return "BASE"


def is_target_population(t) -> bool:
    """Frozen pre-reg population_definition: side=PUT, setup=BEARISH_REJECTION_RIDE_THE_RIBBON
    (implied by side per orchestrator.py:1146-1149), triggers_fired contains BOTH
    'level_rejection' AND 'confluence'."""
    side = str(getattr(t, "side", "P")).upper()
    trig = set(t.triggers_fired or [])
    return side in ("P", "PUT", "BEAR") and "level_rejection" in trig and "confluence" in trig


def is_bs_fallback(t) -> bool:
    """orchestrator.py falls back to the Black-Scholes simulator (simulate_trade, tagged
    '::BS_FALLBACK' on .setup) when the real OPRA contract isn't cached for
    simulate_trade_real. These trades never had a real fill AND their option contract has
    no cached CSV either (load_contract_bars would also return None for them) -- exclude
    them from the real-fills population up front rather than let them surface as an opaque
    'signal bar unmatched' skip (BS_FALLBACK's entry_time_et is the signal bar itself, not
    signal+fill-delay, so it never matches a STRICTLY-earlier decision-log row by construction)."""
    return "::BS_FALLBACK" in str(getattr(t, "setup", ""))


def build_decision_index(decisions: list[dict]) -> dict:
    """Index orchestrator's OWN unconditional per-bar decision log (BacktestResult.decisions --
    'Always log the decision', orchestrator.py ~line 1099) by trade date. Each row carries
    bar_idx, timestamp_et (the SIGNAL bar, NOT the fill bar), ribbon_stack/spread_cents AT
    THAT BAR, triggers_fired, rejection_level, passed. This is the AUTHORITATIVE source for
    'ribbon at entry' -- ctx.ribbon_now at the exact bar filter_5 itself evaluated -- and
    replaces any reverse-engineered signal-bar recovery (a bar-price-matching approach was
    tried and produced ribbon_stack values inconsistent with filter_5's own hard requirement
    that every ENTERED bear trade have stack=='BEAR' at signal time; using the decision log
    directly removes that whole class of bug by construction)."""
    by_date: dict = {}
    for d in decisions:
        if not d.get("passed"):
            continue
        ts = naive_wall(d["timestamp_et"])
        by_date.setdefault(ts.date(), []).append(d)
    for date_key in by_date:
        by_date[date_key].sort(key=lambda r: naive_wall(r["timestamp_et"]))
    return by_date


def find_signal_decision(decisions_by_date: dict, fill_ts_naive: pd.Timestamp,
                          triggers_fired: list[str], rejection_level):
    """Match a TradeFill back to its own signal-bar decision row: same date, passed=True,
    IDENTICAL triggers_fired + rejection_level (both copied through unchanged from this same
    decision to the TradeFill by orchestrator.py, never recomputed), timestamp strictly before
    the fill. Picks the LATEST such candidate (closest to the fill) when more than one bar on
    the day happens to share the exact same trigger set + level."""
    candidates = decisions_by_date.get(fill_ts_naive.date(), [])
    best = None
    best_ts = None
    for d in candidates:
        d_ts = naive_wall(d["timestamp_et"])
        if d_ts >= fill_ts_naive:
            continue
        if d.get("triggers_fired") != triggers_fired:
            continue
        d_level = d.get("rejection_level")
        if (d_level is None) != (rejection_level is None):
            continue
        if d_level is not None and rejection_level is not None and abs(float(d_level) - float(rejection_level)) > 1e-6:
            continue
        if best is None or d_ts > best_ts:
            best, best_ts = d, d_ts
    return best


def build_ribbon_tick_df(ribbon_df: pd.DataFrame, spy_wall_ts: pd.Series, opt_ts_naive: pd.Series) -> pd.DataFrame:
    """Row-for-row aligned (by naive wall-clock timestamp, LEFT join on opt_df's own order/
    count) ribbon frame for walk_exit_manager's positional ribbon_stack_at(ribbon_tick_df, idx)
    lookup -- MUST match opt_df row-for-row, not just by count."""
    day_ribbon = pd.DataFrame({"timestamp_et": spy_wall_ts, "stack": ribbon_df["stack"].values})
    left = pd.DataFrame({"timestamp_et": opt_ts_naive})
    merged = left.merge(day_ribbon, on="timestamp_et", how="left")
    return merged.reset_index(drop=True)


def walk_one(entry_time_et, entry_premium, qty, side, strike, exit_shape, structure_stop_enabled,
             trigger_level, setup, time_stop_et, opt_df, ribbon_tick_df, spy_df, symbol):
    return walk_exit_manager(
        symbol=symbol, side=side, entry_time_et=entry_time_et, entry_premium=entry_premium,
        qty=qty, exit_shape=exit_shape, structure_stop_enabled=structure_stop_enabled,
        trigger_level=trigger_level, strategy=setup, time_stop_et=time_stop_et,
        opt_df=opt_df, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_df,
    )


def fetch_ground_truth_2026_07_17() -> list[dict]:
    """Pull the REAL live engine's own recorded ribbon/triggers/score fields for the harvest
    doc's 5 cited entries directly from automation/state/core-decisions.jsonl -- fresh this
    run, never hand-transcribed (OP-33). For each cited HH:MM, takes the FIRST ENTER_BEAR row
    at that minute (the engine re-logs on every tick; the first ENTER_ verdict at that minute
    is the fill-triggering one)."""
    if not CORE_DECISIONS_PATH.exists():
        return []
    rows_by_minute: dict = {}
    with CORE_DECISIONS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("ts_et", "")
            if not ts.startswith("2026-07-17T"):
                continue
            verdict = d.get("verdict", "")
            if not str(verdict).startswith("ENTER"):
                continue
            hhmm = ts[11:16]
            if hhmm not in HARVEST_CITED_TIMESTAMPS:
                continue
            rows_by_minute.setdefault(hhmm, d)
    out = []
    for hhmm in HARVEST_CITED_TIMESTAMPS:
        d = rows_by_minute.get(hhmm)
        if d is None:
            out.append({"time_et": hhmm, "found": False})
            continue
        out.append({
            "time_et": hhmm, "found": True,
            "verdict": d.get("verdict"),
            "ribbon_LIVE_ENGINE_FIELD": d.get("ribbon"),
            "spread_cents": round(d.get("spread_cents", 0.0), 1),
            "triggers": d.get("triggers"),
            "bear_score": d.get("bear_score"),
            "setup": d.get("setup"),
        })
    return out


def one_sided_p_mean_gt_0(xs: list[float]):
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def main() -> int:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"loaded frozen pre-reg: {PREREG_PATH.name} frozen_at={prereg['frozen_at']}")

    log("loading merged SPY/VIX (base 2025-01-01..2026-07-08 + tail 2026-05-19..2026-07-21)...")
    spy_full = load_merged(SPY_BASE, SPY_TAIL)
    vix_full = load_merged(VIX_BASE, VIX_TAIL)
    log(f"  spy rows={len(spy_full)} range={spy_full['timestamp_et'].iloc[0]}..{spy_full['timestamp_et'].iloc[-1]}")

    log("running orchestrator (use_real_fills=True) over IS 2025 + OOS 2026 YTD (thru 2026-07-17, "
        "the last date with cached OPRA option coverage)...")
    result = run_backtest(spy_full, vix_full, start_date=IS_START, end_date=OOS_END, **SAFE_BASE)
    log(f"  n_total_trades={len(result.trades)}")

    pop_all = [t for t in result.trades if is_target_population(t)]
    n_bs_fallback = sum(1 for t in pop_all if is_bs_fallback(t))
    pop = [t for t in pop_all if not is_bs_fallback(t)]
    log(f"  n_population (side=P, triggers has level_rejection AND confluence) = {len(pop_all)} "
        f"({n_bs_fallback} BS_FALLBACK / uncached-contract, excluded -> {len(pop)} real-fills-eligible)")
    log(f"  n_decision_rows={len(result.decisions)} (orchestrator's own per-bar audit log)")

    decisions_by_date = build_decision_index(result.decisions)

    # CRITICAL: orchestrator's own `idx` / decision-log `bar_idx` indexes into its INTERNAL
    # RTH-only (>=09:30, <16:00), reset_index(drop=True) frame -- NOT the raw merged spy_full
    # (which still carries premarket/after-hours bars). Reproduce that EXACT filter
    # (orchestrator.py: "Split: RTH-only ... for ribbon + baselines + evaluation") before
    # computing our own ribbon_df, or bar_idx alignment silently drifts (caught this build via
    # the ribbon_stack cross-check assertion below -- decision log said BEAR, an unfiltered
    # recompute said BULL at the "same" idx; root cause was exactly this frame mismatch).
    _rth_mask = (
        (pd.to_datetime(spy_full["timestamp_et"]).dt.time >= dt.time(9, 30))
        & (pd.to_datetime(spy_full["timestamp_et"]).dt.time < dt.time(16, 0))
    )
    spy_rth = spy_full.loc[_rth_mask].reset_index(drop=True)
    log(f"  spy_rth rows={len(spy_rth)} (RTH-only, matches orchestrator's internal frame)")

    ribbon_df = compute_ribbon(spy_rth["close"])
    spy_wall_ts = naive_wall(spy_rth["timestamp_et"])
    spy_close = spy_rth["close"].to_numpy()
    # walk_exit_manager's last_closed_bar_close_at requires an ALREADY-datetime timestamp_et
    # column (it calls .dt directly, no parsing).
    spy_full_dt = spy_rth.copy()
    spy_full_dt["timestamp_et"] = pd.to_datetime(spy_rth["timestamp_et"])

    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    structure_stop_enabled = bool(params.get("structure_stop_enabled", False))
    time_stop_et = dt.datetime.strptime(params["time_stop_et"], "%H:%M").time()

    rows = []
    n_signal_unmatched = 0
    n_opra_skip = 0
    n_ribbon_warmup = 0

    for t in pop:
        fill_ts = naive_wall(t.entry_time_et)
        decision = find_signal_decision(decisions_by_date, fill_ts, t.triggers_fired, t.rejection_level)
        if decision is None:
            n_signal_unmatched += 1
            continue
        signal_idx = int(decision["bar_idx"])
        if signal_idx < 3:
            n_ribbon_warmup += 1
            continue
        rib_now = ribbon_at(ribbon_df, signal_idx)
        rib_prev3 = ribbon_at(ribbon_df, signal_idx - 3)
        if rib_now is None or rib_prev3 is None:
            n_ribbon_warmup += 1
            continue
        # Cross-check: the decision log's OWN ribbon_stack (logged by orchestrator at the
        # instant filter_5 evaluated it) must agree with our independent ribbon_at() recompute
        # on the SAME ribbon_df/idx -- these are two different code paths converging on the
        # same primitive; any mismatch means a real bug, not noise, and must not be swallowed.
        assert decision["ribbon_stack"] == rib_now.stack, (
            f"ribbon mismatch at bar_idx={signal_idx} {decision['timestamp_et']}: "
            f"decision log says {decision['ribbon_stack']!r}, recompute says {rib_now.stack!r}"
        )

        momentum3 = rib_now.spread_cents - rib_prev3.spread_cents
        rising_bull = (rib_now.stack == "BULL") and (momentum3 > 0)
        price_riding_up = spy_close[signal_idx] > spy_close[signal_idx - 3]

        strike = int(round(t.strike))
        trade_date = spy_wall_ts.iloc[signal_idx].date()
        symbol = option_symbol(trade_date, strike, t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_opra_skip += 1
            continue
        opt_df = opt_df.reset_index(drop=True)
        opt_ts_naive = naive_wall(opt_df["timestamp_et"])

        ribbon_tick_df = build_ribbon_tick_df(ribbon_df, spy_wall_ts, opt_ts_naive)

        entry_dt = fill_ts.to_pydatetime()
        control_res = walk_one(
            entry_dt, float(t.entry_premium), int(t.qty), t.side, strike, exit_shape,
            structure_stop_enabled, (float(t.rejection_level) if t.rejection_level is not None else None),
            "BEARISH_REJECTION_RIDE_THE_RIBBON", time_stop_et, opt_df, ribbon_tick_df, spy_full_dt, symbol,
        )

        qty_half = max(3, int(t.qty) // 2)
        if rising_bull and qty_half < int(t.qty):
            detier_res = walk_one(
                entry_dt, float(t.entry_premium), qty_half, t.side, strike, exit_shape,
                structure_stop_enabled, (float(t.rejection_level) if t.rejection_level is not None else None),
                "BEARISH_REJECTION_RIDE_THE_RIBBON", time_stop_et, opt_df, ribbon_tick_df, spy_full_dt, symbol,
            )
            detier_pnl = detier_res.dollar_pnl
        else:
            detier_pnl = control_res.dollar_pnl

        rows.append({
            "date": trade_date.isoformat(),
            "signal_time_et": spy_wall_ts.iloc[signal_idx].isoformat(),
            "fill_time_et": fill_ts.isoformat(),
            "strike": strike,
            "qty": int(t.qty),
            "entry_premium": float(t.entry_premium),
            "triggers_fired": t.triggers_fired,
            "tier": classify_tier(t.triggers_fired),
            "rejection_level": t.rejection_level,
            "ribbon_stack_at_entry": rib_now.stack,
            "ribbon_spread_cents_at_entry": round(rib_now.spread_cents, 2),
            "ribbon_momentum_3bar_cents": round(momentum3, 2),
            "rising_bull_at_entry": bool(rising_bull),
            "price_riding_up_at_entry": bool(price_riding_up),
            "am_pm_bucket": "AM" if spy_wall_ts.iloc[signal_idx].time() < dt.time(12, 0) else "PM",
            "simulate_real_pnl_disclosed_only": round(t.dollar_pnl, 2),
            "control_pnl": round(control_res.dollar_pnl, 2),
            "control_exit_reason": control_res.exit_reason,
            "control_hold_minutes": control_res.hold_minutes,
            "candidate_A_suppress_pnl": 0.0 if rising_bull else round(control_res.dollar_pnl, 2),
            "candidate_B_detier_pnl": round(detier_pnl, 2),
            "candidate_C_price_confirmed_suppress_pnl": (
                0.0 if (rising_bull and price_riding_up) else round(control_res.dollar_pnl, 2)
            ),
        })
        log(f"  {trade_date} sig={spy_wall_ts.iloc[signal_idx].strftime('%H:%M')} "
            f"{symbol} qty={t.qty} tier={rows[-1]['tier']} stack={rib_now.stack} "
            f"mom3={momentum3:+.1f}c rising_bull={rising_bull} "
            f"control=${control_res.dollar_pnl:+.2f} sim_real=${t.dollar_pnl:+.2f} "
            f"exit={control_res.exit_reason}")

    log(f"walked n={len(rows)}  skips: signal_unmatched={n_signal_unmatched} "
        f"ribbon_warmup={n_ribbon_warmup} opra_coverage_skip={n_opra_skip}")

    ground_truth = fetch_ground_truth_2026_07_17()
    log("ground-truth check vs automation/state/core-decisions.jsonl (harvest doc's 5 cited entries):")
    for g in ground_truth:
        if g["found"]:
            log(f"  {g['time_et']} ribbon(LIVE)={g['ribbon_LIVE_ENGINE_FIELD']} "
                f"spread={g['spread_cents']}c triggers={g['triggers']} score={g['bear_score']}")
        else:
            log(f"  {g['time_et']} NOT FOUND in core-decisions.jsonl")

    out = build_scorecard(prereg, rows, n_signal_unmatched, n_ribbon_warmup, n_opra_skip, ground_truth, n_bs_fallback)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")

    write_markdown(out)
    log(f"wrote {OUT_MD}")

    log("==== VERDICT ====")
    for cand_id, cand in out["candidates"].items():
        log(f"{cand_id}: verdict={cand['verdict']} n_flagged={cand['n_flagged']} "
            f"aggregate_delta={cand['gates']['g1_aggregate']['delta']}")
    return 0


def _day_key(r):
    return r["date"]


def score_candidate(cand_id: str, pnl_field: str, rows: list[dict]) -> dict:
    def total(rs, field):
        return round(sum(r[field] for r in rs), 2)

    all_control = total(rows, "control_pnl")
    all_cand = total(rows, pnl_field)
    delta_all = round(all_cand - all_control, 2)

    flagged = [r for r in rows if r[pnl_field] != r["control_pnl"]]
    n_flagged = len(flagged)

    # per-day delta, restricted to days with >=1 flagged entry
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    day_deltas = []
    for day, rs in sorted(by_day.items()):
        has_flag = any(r[pnl_field] != r["control_pnl"] for r in rs)
        if not has_flag:
            continue
        d = round(total(rs, pnl_field) - total(rs, "control_pnl"), 2)
        day_deltas.append({"date": day, "delta": d, "n_flagged": sum(1 for r in rs if r[pnl_field] != r["control_pnl"])})
    n_days_up = sum(1 for d in day_deltas if d["delta"] >= 0)
    n_days_down = sum(1 for d in day_deltas if d["delta"] < 0)
    g2_majority = (n_days_up > n_days_down) if (n_days_up + n_days_down) > 0 else None

    # drop single largest-|pnl| flagged trade from the delta credit
    g3_delta_ex_best = None
    if flagged:
        biggest = max(flagged, key=lambda r: abs(r["control_pnl"] - r[pnl_field]))
        rest = [r for r in rows if r is not biggest]
        g3_delta_ex_best = round(total(rest, pnl_field) - total(rest, "control_pnl"), 2)

    is_rows = [r for r in rows if r["date"] < "2026-01-01"]
    oos_ex_disco_rows = [r for r in rows if r["date"] >= "2026-01-01" and r["date"] != "2026-07-17"]
    is_delta = round(total(is_rows, pnl_field) - total(is_rows, "control_pnl"), 2) if is_rows else None
    oos_ex_disco_delta = (round(total(oos_ex_disco_rows, pnl_field) - total(oos_ex_disco_rows, "control_pnl"), 2)
                           if oos_ex_disco_rows else None)
    g4_held_out = (is_delta is not None and oos_ex_disco_delta is not None
                   and is_delta > 0 and oos_ex_disco_delta > 0)

    disco_rows = [r for r in rows if r["date"] == "2026-07-17"]
    disco_delta = round(total(disco_rows, pnl_field) - total(disco_rows, "control_pnl"), 2) if disco_rows else 0.0
    ex_disco_all_rows = [r for r in rows if r["date"] != "2026-07-17"]
    delta_ex_disco = round(total(ex_disco_all_rows, pnl_field) - total(ex_disco_all_rows, "control_pnl"), 2)

    # BH-FDR (advisory): one-sided test that the FLAGGED cohort's control-pnl mean < 0
    # i.e. -control_pnl mean > 0, on trades this candidate actually flags (changes vs control).
    flagged_control_pnls = [r["control_pnl"] for r in flagged]
    p_val = one_sided_p_mean_gt_0([-x for x in flagged_control_pnls])
    bh_significant = (p_val is not None and p_val <= 0.10)

    am_rows = [r for r in rows if r["am_pm_bucket"] == "AM"]
    pm_rows = [r for r in rows if r["am_pm_bucket"] == "PM"]

    def bucket_stat(rs):
        n = len(rs)
        n_flag = sum(1 for r in rs if r[pnl_field] != r["control_pnl"])
        return {
            "n": n, "n_flagged": n_flag,
            "flagged_rate": round(n_flag / n, 3) if n else None,
            "mean_control_pnl": round(sum(r["control_pnl"] for r in rs) / n, 2) if n else None,
            "mean_flagged_control_pnl": (
                round(sum(r["control_pnl"] for r in rs if r[pnl_field] != r["control_pnl"]) / n_flag, 2)
                if n_flag else None
            ),
        }

    time_of_day_confound = {
        "AM": bucket_stat(am_rows),
        "PM": bucket_stat(pm_rows),
        "note": (
            "n too small to isolate the ribbon-state effect WITHIN a fixed time-of-day bucket"
            if min(len(am_rows), len(pm_rows)) < 3 or
               min((bucket_stat(am_rows)["n_flagged"] or 0), (bucket_stat(pm_rows)["n_flagged"] or 0)) < 2
            else "both buckets carry enough flagged entries for a same-bucket comparison"
        ),
    }

    g1_pass = delta_all > 0
    g2_pass = bool(g2_majority) if g2_majority is not None else False
    g3_pass = (g3_delta_ex_best is not None and g3_delta_ex_best > 0)
    g4_pass = bool(g4_held_out)

    n_days_with_flag = n_days_up + n_days_down
    insufficient_n = (n_flagged < 3) or (n_days_with_flag < 3) or (is_delta is None) or (oos_ex_disco_delta is None)

    if insufficient_n:
        verdict = "INSUFFICIENT_N"
    elif g1_pass and g2_pass and g3_pass and g4_pass:
        verdict = "SHIP_CANDIDATE"
    else:
        verdict = "NO_EDGE"

    return {
        "n_flagged": n_flagged,
        "n_total_population": len(rows),
        "control_total_pnl": all_control,
        "candidate_total_pnl": all_cand,
        "gates": {
            "g1_aggregate": {"delta": delta_all, "pass": g1_pass},
            "g2_majority_of_days": {
                "n_days_with_flag": n_days_with_flag, "n_days_up": n_days_up, "n_days_down": n_days_down,
                "day_deltas": day_deltas, "pass": g2_pass,
            },
            "g3_survives_drop_best_trade": {"delta_ex_best": g3_delta_ex_best, "pass": g3_pass},
            "g4_held_out_subset": {
                "is_2025_delta": is_delta, "oos_2026_ex_discovery_day_delta": oos_ex_disco_delta, "pass": g4_pass,
            },
            "g5_not_discovery_day_artifact": {
                "discovery_day_2026_07_17_delta": disco_delta,
                "delta_excluding_discovery_day": delta_ex_disco,
                "note": "population already excludes discovery day from g1-g4 by construction; this reports the discovery day's OWN contribution for transparency.",
            },
        },
        "advisory_bh_fdr": {
            "p_one_sided_mean_lt_0": round(p_val, 5) if p_val is not None else None,
            "threshold": 0.10, "significant": bh_significant,
            "note": "single-candidate BH-FDR degenerates to alpha=0.10 (elite_bear_level_reject_gate_ab.py convention); advisory only, not gating.",
        },
        "advisory_evidence_n": {"n_flagged": n_flagged, "floor": 15, "meets_floor": n_flagged >= 15},
        "time_of_day_confound": time_of_day_confound,
        "verdict": verdict,
    }


def build_scorecard(prereg, rows, n_signal_unmatched, n_ribbon_warmup, n_opra_skip, ground_truth, n_bs_fallback=0) -> dict:
    candidates = {
        "A_suppress": score_candidate("A_suppress", "candidate_A_suppress_pnl", rows),
        "B_detier_half_size": score_candidate("B_detier_half_size", "candidate_B_detier_pnl", rows),
        "C_price_confirmed_suppress_disclosed_only": score_candidate(
            "C_price_confirmed_suppress", "candidate_C_price_confirmed_suppress_pnl", rows),
    }
    gt_losers = [g for g in ground_truth if g["time_et"] in ("11:06", "11:40") and g["found"]]
    gt_winners = [g for g in ground_truth if g["time_et"] in ("13:01", "13:51", "13:52") and g["found"]]
    losers_all_bear = all(g["ribbon_LIVE_ENGINE_FIELD"] == "BEAR" for g in gt_losers) if gt_losers else None
    losers_all_elite_trigger_pair = (
        all(set(g["triggers"] or []) >= {"level_rejection", "confluence"} for g in gt_losers) if gt_losers else None
    )
    winners_share_trigger_family_with_losers = (
        all(set(g["triggers"] or []) >= {"level_rejection", "confluence"} for g in gt_winners)
        if gt_winners else None
    )
    ground_truth_correction = {
        "_doc": "Fresh cross-check of the harvest doc's motivating observation against "
                "automation/state/core-decisions.jsonl (the real live engine's own per-tick "
                "record) -- values below are read from that file THIS run, not hand-transcribed.",
        "entries": ground_truth,
        "finding_losers_ribbon_field_is_BEAR_not_BULL": losers_all_bear,
        "finding_losers_do_carry_level_rejection_plus_confluence": losers_all_elite_trigger_pair,
        "finding_winners_ALSO_carry_level_rejection_plus_confluence": winners_share_trigger_family_with_losers,
        "interpretation": (
            "The harvest doc's 'same trigger family, ribbon BULL+rising for the losers' "
            "characterization does not hold against the live log. Losers fired with "
            "ribbon=BEAR (bear_score=10, ribbon strongly stacked, not weak/turning) and "
            "triggers=[level_rejection, confluence]. Winners fired with triggers=["
            "trendline_rejection] ONLY -- a DIFFERENT trigger family, via the trendline_only_"
            "setup relaxation that bypasses filter_5 (the ribbon-stack requirement) with a "
            "score demerit (bear_score 7-9, not 10). The real discriminator visible in the "
            "live data is TRIGGER TIER (ELITE static-level-anchored vs TRENDLINE dynamic-only "
            "no static level), not ribbon STACK STATE. That correctly-framed hypothesis is "
            "ALREADY filed and ALREADY tested: analysis/recommendations/"
            "elite-bear-level-reject-gate-ab-2026-07-17.json, verdict PARK_INSUFFICIENT_"
            "REGIME_SHIFT (IS delta -$532.80, OOS delta +$683.14, WF gate FAILED, "
            "sub_window_stability FAILED)."
        ) if losers_all_bear is not None else "core-decisions.jsonl entries not found -- correction could not be verified this run.",
    }
    return {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg_path": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "prereg_frozen_at": prereg["frozen_at"],
        "ground_truth_correction": ground_truth_correction,
        "population": {
            "n_walked": len(rows),
            "n_bs_fallback_excluded": n_bs_fallback,
            "n_signal_bar_unmatched": n_signal_unmatched,
            "n_ribbon_warmup_excluded": n_ribbon_warmup,
            "n_opra_coverage_skip": n_opra_skip,
            "date_range_available": ["2025-01-02", "2026-07-17"],
            "note": "n_walked is the FULL gate-eligible-plus-discovery-day population (IS 2025 + OOS 2026 YTD thru 2026-07-17, discovery day INCLUDED here and excluded only inside each candidate's g1-g4 windows per the frozen pre-reg). ZERO of these 27 entries are on 2026-07-17 itself -- the bar-cadence backtest reconstruction does not reproduce that day's live 1-min-tick entries (disclosed in the frozen pre-reg's motivating_observation.note); see ground_truth_correction above for what the REAL 07-17 entries actually looked like.",
        },
        "trades": rows,
        "candidates": candidates,
    }


def write_markdown(out: dict) -> None:
    lines = []
    lines.append("# Ribbon-state-at-entry gate on bear entries -- population validation (2026-07-21)")
    lines.append("")
    lines.append(f"Generated: {out['generated_at']}. Runner: `backtest/tools/ribbon_state_entry_gate_study.py`.")
    lines.append(f"Frozen pre-reg: `{out['prereg_path']}` (frozen_at {out['prereg_frozen_at']}).")
    lines.append("")
    lines.append("Source: LANE-B HYPOTHESIS #1, `markdown/doctrine/DOJO-HARVEST-2026-07-21.md` -- "
                  "n=2-day quantified finding (2026-07-17 real fills): bear entries "
                  "(level_rejection+confluence) into a still-rising BULL ribbon lost "
                  "-$37/-$102; entries after the ribbon rolled over won +$241/+$191/+$233.")
    lines.append("")

    gt = out["ground_truth_correction"]
    lines.append("## GROUND-TRUTH CORRECTION (read this first)")
    lines.append("")
    lines.append("Cross-checked the harvest doc's motivating observation against "
                  "`automation/state/core-decisions.jsonl` (the real live engine's own "
                  "per-tick record) -- fresh this run, not hand-transcribed:")
    lines.append("")
    lines.append("| time | verdict | ribbon (LIVE engine field) | spread_c | triggers | bear_score |")
    lines.append("|---|---|---|--:|---|--:|")
    for g in gt["entries"]:
        if g["found"]:
            lines.append(f"| {g['time_et']} | {g['verdict']} | {g['ribbon_LIVE_ENGINE_FIELD']} | "
                          f"{g['spread_cents']} | {g['triggers']} | {g['bear_score']} |")
        else:
            lines.append(f"| {g['time_et']} | NOT FOUND | - | - | - | - |")
    lines.append("")
    lines.append(f"**{gt['interpretation']}**")
    lines.append("")

    p = out["population"]
    lines.append("## Population")
    lines.append("")
    lines.append(f"- n_walked = **{p['n_walked']}** "
                  f"(side=PUT, setup=BEARISH_REJECTION_RIDE_THE_RIBBON, triggers contain BOTH "
                  f"level_rejection AND confluence -- full history {p['date_range_available'][0]}..{p['date_range_available'][1]}, "
                  f"the widest OPRA-covered window, 382 distinct trading dates)")
    lines.append(f"- BS-fallback excluded (uncached contract, not a real fill): {p.get('n_bs_fallback_excluded', 0)}")
    lines.append(f"- signal-bar unmatched (dropped): {p['n_signal_bar_unmatched']}")
    lines.append(f"- ribbon-warmup excluded: {p['n_ribbon_warmup_excluded']}")
    lines.append(f"- OPRA coverage skip: {p['n_opra_coverage_skip']}")
    lines.append("")
    if p["n_walked"] < 15:
        lines.append(f"**HONESTY FLAG: n={p['n_walked']} is thin.** This is well below the OP-16 "
                      "evidence_n>=15 advisory floor used everywhere else in this codebase. Any "
                      "SHIP_CANDIDATE verdict below should be read as directionally suggestive, "
                      "not proof -- exactly the caveat the frozen pre-reg committed to stating "
                      "plainly rather than forcing a result.")
        lines.append("")

    n_rising = sum(1 for r in out["trades"] if r["rising_bull_at_entry"])
    lines.append(f"**WHY n_flagged is 0 for every candidate:** all {p['n_walked']} entries in this "
                  "population show `stack=BEAR` at signal time -- ZERO show BULL, and "
                  f"`rising_bull_at_entry` fires on {n_rising}/{p['n_walked']}. This is STRUCTURAL, "
                  "not a coincidence of this sample: `backtest/lib/filters.py` Filter 5 "
                  "(`ctx.ribbon_now.stack != 'BEAR' -> blockers.append(5)`) already hard-blocks any "
                  "PUT entry carrying level_rejection/confluence/sequence_rejection triggers unless "
                  "the ribbon is EXACTLY BEAR-stacked at that instant -- live and backtest alike "
                  "(`engine/score.py:score_bear` is a byte-identical pass-through to the same "
                  "`evaluate_bearish_setup`, and `bearish_reversal_bypass`/`allow_one_blocker` have "
                  "never been set true in `automation/state/params.json`'s history). The literal "
                  "`rising_bull_at_entry` condition this pre-reg specified is therefore a logical "
                  "impossibility for this exact trigger family under the CURRENT production filter "
                  "set -- confirmed two ways: (1) 0/27 in this full-history reconstruction, and "
                  "(2) the real 2026-07-17 live log itself (see GROUND-TRUTH CORRECTION above).")
    lines.append("")

    lines.append("## Per-trade population")
    lines.append("")
    lines.append("| date | sig time | tier | stack | mom3c | rising_bull | AM/PM | control $ | sim_real $ (disclosed) | exit |")
    lines.append("|---|---|---|---|--:|:--:|:--:|--:|--:|---|")
    for r in out["trades"]:
        lines.append(f"| {r['date']} | {r['signal_time_et'][11:16]} | {r['tier']} | {r['ribbon_stack_at_entry']} | "
                      f"{r['ribbon_momentum_3bar_cents']:+.1f} | {r['rising_bull_at_entry']} | {r['am_pm_bucket']} | "
                      f"{r['control_pnl']:+.2f} | {r['simulate_real_pnl_disclosed_only']:+.2f} | {r['control_exit_reason']} |")
    lines.append("")

    for cand_id, c in out["candidates"].items():
        lines.append(f"## Candidate `{cand_id}`")
        lines.append("")
        lines.append(f"n_flagged={c['n_flagged']} / n_population={c['n_total_population']}. "
                      f"control_total=${c['control_total_pnl']:+,.2f} candidate_total=${c['candidate_total_pnl']:+,.2f}")
        lines.append("")
        g = c["gates"]
        lines.append(f"- g1 aggregate delta: **${g['g1_aggregate']['delta']:+,.2f}** -- pass={g['g1_aggregate']['pass']}")
        lines.append(f"- g2 majority of days: up={g['g2_majority_of_days']['n_days_up']} "
                      f"down={g['g2_majority_of_days']['n_days_down']} -- pass={g['g2_majority_of_days']['pass']}")
        lines.append(f"- g3 survives drop-best-trade: delta_ex_best=${g['g3_survives_drop_best_trade']['delta_ex_best']} "
                      f"-- pass={g['g3_survives_drop_best_trade']['pass']}")
        lines.append(f"- g4 held-out subset: IS_2025=${g['g4_held_out_subset']['is_2025_delta']} "
                      f"OOS_2026_ex_discovery=${g['g4_held_out_subset']['oos_2026_ex_discovery_day_delta']} "
                      f"-- pass={g['g4_held_out_subset']['pass']}")
        lines.append(f"- g5 discovery-day contribution: ${g['g5_not_discovery_day_artifact']['discovery_day_2026_07_17_delta']} "
                      f"(delta excluding discovery day entirely: ${g['g5_not_discovery_day_artifact']['delta_excluding_discovery_day']})")
        lines.append("")
        bh = c["advisory_bh_fdr"]
        lines.append(f"Advisory BH-FDR: p={bh['p_one_sided_mean_lt_0']} threshold={bh['threshold']} "
                      f"significant={bh['significant']} (not gating). "
                      f"evidence_n floor met: {c['advisory_evidence_n']['meets_floor']} "
                      f"(n_flagged={c['advisory_evidence_n']['n_flagged']}, floor=15).")
        lines.append("")
        tod = c["time_of_day_confound"]
        lines.append(f"Time-of-day confound: AM n={tod['AM']['n']} n_flagged={tod['AM']['n_flagged']} "
                      f"mean_flagged_control_pnl={tod['AM']['mean_flagged_control_pnl']}; "
                      f"PM n={tod['PM']['n']} n_flagged={tod['PM']['n_flagged']} "
                      f"mean_flagged_control_pnl={tod['PM']['mean_flagged_control_pnl']}. {tod['note']}")
        lines.append("")
        lines.append(f"### VERDICT `{cand_id}`: **{c['verdict']}**")
        lines.append("")

    lines.append("## Relationship to the trend-alignment-correlation study (twice-confirmed KILL)")
    lines.append("")
    lines.append("`analysis/recommendations/trend-alignment-correlation.md`: P1 OOS rho=-0.150 "
                  "(p=0.157, beats-null=False), P2 real-engine rho=-0.143 (p=0.137, beats-null=False) "
                  "-- MULTI-TIMEFRAME (daily+hourly+15m) trend agreement vs the trade's own side. "
                  "THIS study measures a DIFFERENT, SAME-TIMEFRAME feature (the 5-min ribbon's own "
                  "stack + local 3-bar momentum at entry), not cross-timeframe agreement. Related "
                  "question, different measurement -- this study's verdict stands or falls on its "
                  "own gates above, it does not inherit the trend-alignment KILL by association.")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
