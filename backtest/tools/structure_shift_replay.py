"""structure_shift_replay.py -- THE PHILOSOPHY BUILD. Implements EXACTLY the frozen
pre-registration `analysis/recommendations/prereg-structure-shift-confirmation-2026-07-28.json`
(commit 773a17f0) -- STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS, J's dictated market philosophy
(markdown/doctrine/J-MARKET-PHILOSOPHY.md): for LEVEL-TIED setups, replace the lagging-EMA
confirmations (bear: filter 5 ribbon-stack; bull: htf_15m agreement) with a MICRO
STRUCTURE-SHIFT confirmation at the zone -- a failed push / rejection bar -- so the engine
catches the SAME winners 2-4 bars earlier plus the class its lagging gates block outright
(2026-07-27 09:40 bear @744.9, 2026-07-28 11:05 bull @~738.1).

NO KNOBS BEYOND THE FROZEN K SEARCH SPACE {3 primary, 2 sensitivity}. If the predicate
looks wrong, it still runs AS FROZEN -- any concern goes in the report, never into a
silent "improvement" to the predicate itself. This tool does not touch filters.py,
engine_cli.py, heartbeat_core.py, params, or any fleet file -- read-only reuse only.

===========================================================================================
MACHINERY REUSED WHOLESALE (per task instruction) from
backtest/tools/ladder_fullhist_replay.py (`lfr`) and backtest/tools/engine_fullhist_replay.py
(`efr`):
===========================================================================================
  lfr.build_rth_frame       the bar_idx misresolution trap fix -- orchestrator.run_backtest
                            internally rebuilds spy_df = spy_df_full.loc[rth_mask].reset_
                            index(drop=True) BEFORE scoring; every bar_idx it logs is a
                            position into THAT frame, not the raw (premarket-inclusive) input.
  lfr.load_extended_data    the byte-identical-prefix OLD file + strictly-after-07-22 tail of
                            the NEW file, 2025-01-02..2026-07-27, no dedup ambiguity.
  lfr.run_baseline          re-derives the binary engine's OWN entries' exits via the REAL
                            exit_manager (walk_exit_manager), discarding run_backtest's raw
                            (wrong-exit-shape) dollar_pnl -- reused VERBATIM for book (c).
  lfr.lane_stats            day-majority / drop-best / held-out stat shape, reused verbatim
                            for every book (baseline, K=3, K=2) so all three are apples-to-
                            apples comparable.
  efr.naive_dt / efr.build_ribbon_lookup / efr.ribbon_tick_df_for / efr.TIME_STOP_ET / efr.
  SAFE_BASE_LIVE            entry/gate/filter cascade config + ribbon alignment machinery.
  walk_exit_manager         the REAL exit_manager.plan_exit_actions decision core, structure-
                            stop enabled, trigger_level=the raw trigger's own level, RIBBON_
                            RIDE exit shape -- IDENTICAL exit layer to both cited tools.
  Real-OPRA-only P&L        any candidate resolving to a BS-synthetic entry premium (no cached
                            OPRA bar at the exact confirmation-close timestamp) is counted and
                            EXCLUDED from P&L, never blended -- same C1 discipline.
  One-position-at-a-time    NOT_FLAT discipline: a candidate whose TRIGGER bar falls inside an
                            already-open position's window is never even confirmation-scanned.

===========================================================================================
ONE DELIBERATE EXTENSION beyond ladder_fullhist_replay's own candidate extraction (disclosed,
not a silent divergence): ladder_fullhist_replay's `is_ladder_candidate` is BEAR-ONLY and
requires `passed is False` (mirrors production's "neither side passed scoring" gate). The
frozen pre-reg's population is broader: "for every bar where a LEVEL-TIED raw trigger fired
... REGARDLESS of whether the engine's lagging gates passed it" -- and BOTH sides (bear AND
bull). Reproducing that population from `BacktestResult.decisions` is not possible: bear's
raw fields are logged on every bar's base "always logged" row, but bull's raw fields are
logged ONLY on a WINNING-bull row (ladder_fullhist_replay's own module docstring, "BULL-PASSED
CAPTURE" section, documents this gap and works around it for `passed` alone via a monkeypatch
of `evaluate_bullish_setup`). This tool extends that SAME proven, pure-pass-through-wrapper
technique to BOTH `evaluate_bearish_setup` and `evaluate_bullish_setup`, capturing the FULL
raw result (score/blockers/triggers_fired/level/passed) per bar_idx for both sides in ONE
`run_backtest` call -- zero orchestrator.py edits, functions restored in `finally` regardless
of outcome.

===========================================================================================
THE PREDICATE, AS FROZEN (verbatim from the pre-reg's `predicate_frozen` block, reproduced
here for the one place it required disambiguation -- the pre-reg's own bull clause is terser
than its bear clause; the fuller task-prompt clause is exactly binding and reproduced below):
===========================================================================================
  BEAR : trigger = a level_rejection/fhh_level_rejection/confluence/sequence_rejection raw
         trigger fired on the trigger bar (its OWN rejection_level, whatever the engine's
         filter-5/HTF gates ultimately decided). Confirmation: within K bars after the
         trigger bar (same calendar day only), a bar with (1) HIGH < trigger bar's HIGH
         [structural lower high, no level involved] AND (2) LOW < min(trigger_bar_low, level)
         [price actually trades below BOTH the recent low structure AND the level itself,
         whichever is tighter]. First bar within K satisfying BOTH wins.
  BULL (mirror): trigger = level_reclaim/confluence/sequence_reclaim (bull has no fhh
         variant -- confirmed absent from filters.py). Confirmation: within K bars, a bar
         with (1) LOW > max(trigger_bar_low, level) [a higher low that ALSO sits above the
         level -- the level appears in this clause instead of bear's clause 2, since for a
         bull reclaim the level is naturally already beneath the trigger bar; DISCLOSED
         DESIGN CHOICE, not a typo -- each side references the level exactly once] AND (2)
         HIGH > trigger bar's HIGH [structural break of the trigger's own high, mirroring
         bear's level-free clause 1]. First bar within K satisfying BOTH wins.
  No confirmation within K -> no trade (counted as "expired_unconfirmed", never a fallback
  entry). Entry: confirmation bar's OWN CLOSE (SPY price) -> the corresponding option bar's
  OWN close (same 5-min interval, EXACT timestamp match only -- never "next bar", never
  "at or after"). Exit: walked from confirmation-bar+1 via walk_exit_manager (per markdown/
  audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md's entry+1 canonical convention: entry_time_
  et = the confirmation bar's OWN timestamp, so the exit walk's first eligible check is
  strictly the next bar).

Run: backtest/.venv/Scripts/python.exe backtest/tools/structure_shift_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS_DIR = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS_DIR), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies                       # noqa: E402
import fleet_executor as fx                                   # noqa: E402  -- PROBE_STRIKE_TIERS
import ladder_fullhist_replay as lfr                            # noqa: E402  -- reused wholesale
import engine_fullhist_replay as efr                             # noqa: E402  -- reused wholesale
import lib.orchestrator as orch_mod                                # noqa: E402
from lib.orchestrator import run_backtest                            # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                   # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from crypto.lib.strike_selection import pick_strike                      # noqa: E402
from _alpaca_creds import masked, resolve_alpaca_creds                    # noqa: E402

# =============================================================================== constants

# BEAR: identical to build_shared_signal.LADDER_LEVEL_TIED (production's own set) -- reused
# by name, not hand-copied, so this tool tracks production if that set ever changes.
import build_shared_signal as bss  # noqa: E402
BEAR_LEVEL_TIED = bss.LADDER_LEVEL_TIED   # {level_rejection, fhh_level_rejection, confluence, sequence_rejection}
# BULL: mirrors filters.py's own inline `level_tied` set at evaluate_bearish_setup's filter-10
# defensive check (bear) / evaluate_bullish_setup's filter-11 defensive check (bull) -- no
# fhh_level_reclaim exists anywhere in this codebase (confirmed by grep before writing this).
BULL_LEVEL_TIED = frozenset({"level_reclaim", "confluence", "sequence_reclaim"})

# The ENTIRE search space per the frozen pre-reg -- no other K value, ever.
K_PRIMARY = 3
K_SENSITIVITY = 2

MIN_CONTRACTS = lfr.MIN_CONTRACTS                # 3, Rule 6 floor
REF_EQUITY_FOR_STRIKE = lfr.REF_EQUITY_FOR_STRIKE  # 2000.0, irrelevant to strike (ATM either way)
LEVEL_MATCH_TOL = 0.05                            # same tolerance filters.py itself uses for level_state price matching

STORED_BASELINE_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"

# G5 incident anchors, as named in the frozen pre-reg's gates_frozen list.
BEAR_ANCHOR_DATE = dt.date(2026, 7, 27)
BEAR_ANCHOR_TIME = dt.time(9, 40)
BULL_ANCHOR_DATE = dt.date(2026, 7, 28)
BULL_ANCHOR_TIME = dt.time(11, 5)
# Cited from markdown/doctrine/J-MARKET-PHILOSOPHY.md ("bull 7/10 at the 738.1 reclaim on the
# 11:05 bar") -- used as the STARTING hypothesis level for the bull anchor's signal-level-only
# check (no orchestrator re-score for 07-28; see g5_bull_anchor_check docstring for why).
BULL_ANCHOR_LEVEL_CITED = 738.1

OUT_JSON = ROOT / "analysis" / "recommendations" / "structure-shift-replay-2026-07-28.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "structure-shift-replay-2026-07-28.md"


def log(msg: str) -> None:
    print(f"[structure-shift-replay] {msg}", flush=True)


# =============================================================================== dual capture

def run_backtest_with_full_capture(spy_df, vix_df, start_date, end_date, **kwargs):
    """run_backtest, plus a {bar_idx: {...}} side-channel for BOTH bear and bull raw scoring
    results (score/blockers/triggers_fired/level/passed/vix), captured via a pure pass-through
    monkeypatch of orch_mod.evaluate_bearish_setup / evaluate_bullish_setup -- extends
    ladder_fullhist_replay.run_backtest_with_bull_capture's proven technique (which captures
    bull's `passed` alone) to the FULL raw result on both sides. Restores both originals in
    `finally` regardless of outcome; zero orchestrator.py edits."""
    bear_raw: dict[int, dict] = {}
    bull_raw: dict[int, dict] = {}
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup

    def _capture_bear(ctx, **kw):
        res = orig_bear(ctx, **kw)
        bear_raw[ctx.bar_idx] = {
            "score": res.bear_score, "blockers": list(res.blockers),
            "triggers_fired": list(res.triggers_fired), "level": res.rejection_level,
            "passed": bool(res.passed), "vix": float(ctx.vix_now),
        }
        return res

    def _capture_bull(ctx, **kw):
        res = orig_bull(ctx, **kw)
        bull_raw[ctx.bar_idx] = {
            "score": res.bull_score, "blockers": list(res.blockers),
            "triggers_fired": list(res.triggers_fired), "level": res.reclaim_level,
            "passed": bool(res.passed), "vix": float(ctx.vix_now),
        }
        return res

    orch_mod.evaluate_bearish_setup = _capture_bear
    orch_mod.evaluate_bullish_setup = _capture_bull
    try:
        r = run_backtest(spy_df, vix_df, start_date=start_date, end_date=end_date, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
    return r, bear_raw, bull_raw


def build_population(bear_raw: dict[int, dict], bull_raw: dict[int, dict]) -> list[dict]:
    """Full population: every bar where a level-tied raw trigger fired on EITHER side,
    REGARDLESS of `passed`. Sorted by (bar_idx, side) so bear is processed before bull on any
    bar where both happen to fire (disclosed, deterministic tie-break)."""
    out: list[dict] = []
    for bar_idx, d in bear_raw.items():
        if any(t in BEAR_LEVEL_TIED for t in d["triggers_fired"]) and isinstance(d["level"], (int, float)):
            out.append({"bar_idx": bar_idx, "side": "P", "level": float(d["level"]),
                        "triggers_raw": d["triggers_fired"], "score": d["score"],
                        "blockers": d["blockers"], "passed": d["passed"], "vix": d["vix"]})
    for bar_idx, d in bull_raw.items():
        if any(t in BULL_LEVEL_TIED for t in d["triggers_fired"]) and isinstance(d["level"], (int, float)):
            out.append({"bar_idx": bar_idx, "side": "C", "level": float(d["level"]),
                        "triggers_raw": d["triggers_fired"], "score": d["score"],
                        "blockers": d["blockers"], "passed": d["passed"], "vix": d["vix"]})
    out.sort(key=lambda c: (c["bar_idx"], 0 if c["side"] == "P" else 1))
    return out


# =============================================================================== the predicate

def scan_confirmation(
    spy_rth: pd.DataFrame, trigger_idx: int, level: float, side: str, k: int,
) -> tuple[Optional[int], list[dict]]:
    """THE FROZEN PREDICATE. Scans up to K bars strictly after trigger_idx, SAME CALENDAR DAY
    only (a level-tied trigger's confirmation is a same-session fact; the scan never crosses
    into the next day's premarket/open). Returns (confirmation_bar_idx_or_None, checked) --
    `checked` is the full bar-by-bar record (for G5 disclosure). First bar satisfying BOTH
    conditions wins; timestamp-agnostic (works on tz-aware or naive frames) so it is reused
    verbatim for the G5 bull anchor's freshly-fetched (naive) 2026-07-28 frame."""
    trig = spy_rth.iloc[trigger_idx]
    trig_date = trig["timestamp_et"].date()
    trig_high = float(trig["high"])
    trig_low = float(trig["low"])
    checked: list[dict] = []
    for i in range(1, k + 1):
        j = trigger_idx + i
        if j >= len(spy_rth):
            break
        cbar = spy_rth.iloc[j]
        if cbar["timestamp_et"].date() != trig_date:
            break
        c_high = float(cbar["high"])
        c_low = float(cbar["low"])
        if side == "P":
            cond1 = c_high < trig_high                      # structural: lower high
            threshold = min(trig_low, level)
            cond2 = c_low < threshold                         # trades below floor(low, level)
        else:
            threshold = max(trig_low, level)
            cond1 = c_low > threshold                          # higher low, ABOVE the level
            cond2 = c_high > trig_high                          # structural: breaks trigger's high
        checked.append({"bar_idx": j, "cond1": bool(cond1), "cond2": bool(cond2),
                        "high": c_high, "low": c_low, "threshold": threshold})
        if cond1 and cond2:
            return j, checked
    return None, checked


def _naive_ts_col(df: pd.DataFrame) -> pd.Series:
    ts = df["timestamp_et"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    return ts


def resolve_confirmation_entry(
    opt_df: Optional[pd.DataFrame], confirmation_ts_naive: dt.datetime,
    vix_now: float, spot: float, strike: int, side: str,
) -> dict:
    """Entry price = the option bar's OWN CLOSE at the EXACT confirmation-bar timestamp (same
    5-min interval as the SPY confirmation bar) -- never 'next bar', never 'at or after'.
    Falls back to a BS-synthetic premium for disclosure ONLY (never fed through the exit walk,
    same C1 discipline as ladder_fullhist_replay.resolve_ladder_entry)."""
    if opt_df is not None:
        naive_opt = opt_df.assign(timestamp_et=_naive_ts_col(opt_df))
        exact = naive_opt.loc[naive_opt["timestamp_et"] == confirmation_ts_naive]
        if not exact.empty:
            row = exact.iloc[0]
            return {"ok": True, "entry_premium": round(float(row["close"]), 4)}
        reason = "no_exact_bar_at_confirmation_close"
    else:
        reason = "no_opra_cache"
    iv = vix_to_iv(vix_now)
    tte = time_to_expiry_years(confirmation_ts_naive)
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=(side == "C"))
    return {"ok": False, "reason": reason, "synthetic_entry_premium": round(max(price, 0.01), 4)}


# =============================================================================== one book (one K)

def run_predicate_book(
    k: int, population: list[dict], spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame,
    exit_shape: dict, min_contracts: int = MIN_CONTRACTS, ref_equity: float = REF_EQUITY_FOR_STRIKE,
    opt_loader: Callable[[str], Optional[pd.DataFrame]] = load_contract_bars,
) -> dict:
    """Walks the FULL population chronologically by trigger bar, ONE POSITION AT A TIME: a
    candidate whose trigger bar falls inside an already-open position's window is skipped
    (never even confirmation-scanned -- still flat, free for the next candidate). Returns
    {"trades": [...], "expired": [...], "excluded": [...], "skipped_not_flat": [...]}."""
    trades: list[dict] = []
    expired: list[dict] = []
    excluded: list[dict] = []
    skipped_not_flat: list[dict] = []
    flat_until: Optional[dt.datetime] = None

    for cand in population:
        trig_idx = cand["bar_idx"]
        trig_row = spy_rth.iloc[trig_idx]
        trig_ts = efr.naive_dt(trig_row["timestamp_et"])
        trig_date = trig_row["timestamp_et"].date()
        base = {"trigger_bar_idx": trig_idx, "side": cand["side"], "level": cand["level"],
                "triggers_raw": cand["triggers_raw"], "origin_passed": cand["passed"],
                "trigger_time_et": trig_ts.isoformat(), "date": trig_date.isoformat()}

        if flat_until is not None and trig_ts <= flat_until:
            skipped_not_flat.append({**base, "held_position_until": flat_until.isoformat()})
            continue

        conf_idx, checked = scan_confirmation(spy_rth, trig_idx, cand["level"], cand["side"], k)
        if conf_idx is None:
            expired.append({**base, "k": k, "n_bars_checked": len(checked),
                            "any_cond1_true": any(c["cond1"] for c in checked),
                            "any_cond2_true": any(c["cond2"] for c in checked)})
            continue

        conf_row = spy_rth.iloc[conf_idx]
        conf_ts = efr.naive_dt(conf_row["timestamp_et"])
        spot = float(conf_row["close"])
        trade_date = conf_row["timestamp_et"].date()
        strike = pick_strike(spot, ref_equity, cand["side"], fx.PROBE_STRIKE_TIERS)
        symbol = option_symbol(trade_date, strike, cand["side"])
        opt_df = opt_loader(symbol)
        res = resolve_confirmation_entry(opt_df, conf_ts, cand["vix"], spot, strike, cand["side"])

        if not res["ok"]:
            excluded.append({**base, "k": k, "confirmation_bar_idx": conf_idx,
                             "confirmation_time_et": conf_ts.isoformat(), "strike": strike,
                             "exclude_reason": res["reason"],
                             "synthetic_entry_premium": res["synthetic_entry_premium"],
                             "is_synthetic": True})
            continue  # never entered -- still flat, free for the NEXT candidate

        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == trade_date].reset_index(drop=True)
        walk = walk_exit_manager(
            symbol=symbol, side=cand["side"], entry_time_et=conf_ts,
            entry_premium=res["entry_premium"], qty=min_contracts, exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=float(cand["level"]),
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        exit_ts = walk.exit_time_et if walk.exit_time_et is not None else conf_ts
        flat_until = exit_ts

        trades.append({
            **base, "k": k, "confirmation_bar_idx": conf_idx,
            "confirmation_time_et": conf_ts.isoformat(), "bars_to_confirm": conf_idx - trig_idx,
            "confirmation_close_spy": round(spot, 4),
            "entry_time_et": conf_ts.isoformat(), "entry_premium": res["entry_premium"],
            "strike": strike, "qty": min_contracts, "symbol": symbol,
            "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
            "exit_time_et": exit_ts.isoformat() if exit_ts else None,
            "hold_minutes": walk.hold_minutes, "resolved": walk.resolved,
            "n_ticks_walked": walk.n_ticks_walked, "is_synthetic": False,
        })
    return {"trades": trades, "expired": expired, "excluded": excluded,
            "skipped_not_flat": skipped_not_flat}


# =============================================================================== trigger-class + matching

LEVEL_TIED_TRIGGERS_ANY_SIDE = BEAR_LEVEL_TIED | BULL_LEVEL_TIED


def trigger_class(triggers: Optional[list[str]]) -> str:
    """LEVEL_tied / TL_only / BOTH / NEITHER -- same taxonomy as pnl_attribution_2026_07_28.py
    (inlined here, not imported, to avoid coupling to that script's unrelated journal/trades.csv
    reads). ONE disclosed difference: this set additionally includes fhh_level_rejection,
    matching the frozen pre-reg's explicit scope ("level_rejection / fhh_level_rejection /
    confluence / sequence_rejection") -- PNL-ATTRIBUTION-2026-07-28's own LEVEL_TIED_TRIGGERS
    omitted fhh_level_rejection, so a recomputed subtable here may differ from the cited
    66-trade/$6,894.85 number by at most the fhh-only trades (disclosed in the report, not
    silently reconciled)."""
    trig = set(triggers or [])
    tl = "trendline_rejection" in trig
    lv = bool(trig & LEVEL_TIED_TRIGGERS_ANY_SIDE)
    if tl and lv:
        return "BOTH"
    if tl:
        return "TL_only"
    if lv:
        return "LEVEL_tied"
    return "NEITHER"


def find_best_population_match(
    population: list[dict], spy_rth: pd.DataFrame, date_: dt.date, side: str,
    level: Optional[float], entry_dt_naive: dt.datetime, tol: float = LEVEL_MATCH_TOL,
) -> Optional[dict]:
    """Links a KNOWN entry (baseline TradeFill or a stored scorecard row) back to its
    population trigger bar_idx by (date, side, level within tolerance, trigger time <= entry
    time) -- picks the LATEST such trigger at/before the entry (the trigger closest to, and
    causally preceding, the known entry). v_pullback is OFF in SAFE_BASE_LIVE, so production's
    own `actual_entry_idx == idx` (the trigger bar itself) in every case this tool matches
    against; this is therefore a high-confidence match, not a fuzzy heuristic, though still
    disclosed as a match (not an identity) since it is computed independently."""
    if level is None:
        return None
    best = None
    best_ts = None
    for c in population:
        if c["side"] != side or abs(c["level"] - level) > tol:
            continue
        row = spy_rth.iloc[c["bar_idx"]]
        ts = efr.naive_dt(row["timestamp_et"])
        if ts.date() != date_ or ts > entry_dt_naive:
            continue
        if best_ts is None or ts > best_ts:
            best, best_ts = c, ts
    return best


# =============================================================================== gates G1-G3

def day_pnl_series(trades: list[dict]) -> dict:
    per_day: dict[str, float] = defaultdict(float)
    for t in trades:
        per_day[t["date"]] += float(t["dollar_pnl"])
    return per_day


def changed_days_majority(new_trades: list[dict], baseline_trades: list[dict]) -> dict:
    """G2: among calendar days that DIFFER between the new book and the baseline level-tied
    book (non-zero delta), the majority must be positive (the change made that day better,
    not worse)."""
    new_by_day = day_pnl_series(new_trades)
    base_by_day = day_pnl_series(baseline_trades)
    all_days = set(new_by_day) | set(base_by_day)
    changed = []
    wins = 0
    for d in sorted(all_days):
        delta = round(new_by_day.get(d, 0.0) - base_by_day.get(d, 0.0), 2)
        if abs(delta) > 1e-6:
            changed.append({"date": d, "new_pnl": round(new_by_day.get(d, 0.0), 2),
                            "baseline_pnl": round(base_by_day.get(d, 0.0), 2), "delta": delta})
            if delta > 0:
                wins += 1
    n_changed = len(changed)
    return {"n_changed_days": n_changed, "win_days": wins,
            "is_majority": (wins > n_changed / 2.0) if n_changed else None,
            "changed_days_detail": changed}


def survives_drop_best(new_trades: list[dict], baseline_total_pnl: float) -> dict:
    """G3: drop the single best trade from the NEW book; the delta vs baseline must still be
    positive."""
    if not new_trades:
        return {"best_trade_pnl": None, "total_minus_best_delta_vs_baseline": None,
                "still_positive": None}
    best = max(new_trades, key=lambda t: t["dollar_pnl"])
    total = sum(t["dollar_pnl"] for t in new_trades)
    total_minus_best = round(total - best["dollar_pnl"], 2)
    delta = round(total_minus_best - baseline_total_pnl, 2)
    return {"best_trade_pnl": round(best["dollar_pnl"], 2),
            "total_minus_best_delta_vs_baseline": delta, "still_positive": delta > 0}


def compute_gates(books: dict, baseline_level_tied: list[dict], all_calendar_dates, held_out_cutoff) -> dict:
    bstats = lfr.lane_stats(baseline_level_tied, all_calendar_dates, held_out_cutoff)
    out = {"baseline_level_tied_stats": bstats}
    for k, res in books.items():
        trades = res["trades"]
        stats = lfr.lane_stats(trades, all_calendar_dates, held_out_cutoff)
        g1_delta = round(stats["total_pnl"] - bstats["total_pnl"], 2)
        g2 = changed_days_majority(trades, baseline_level_tied)
        g3 = survives_drop_best(trades, bstats["total_pnl"])
        out[f"K={k}"] = {
            "stats": stats, "G1_delta_vs_baseline_level_tied": g1_delta,
            "G1_pass": g1_delta > 0, "G2": g2, "G3": g3,
            "n_expired_unconfirmed": len(res["expired"]),
            "n_excluded_synthetic": len(res["excluded"]),
            "n_skipped_not_flat": len(res["skipped_not_flat"]),
        }
    return out


# =============================================================================== G4 -- 35 RUNNER_TRAIL anchor

def g4_runner_trail_check(
    population: list[dict], spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame, exit_shape: dict,
    k: int = K_PRIMARY, opt_loader: Callable[[str], Optional[pd.DataFrame]] = load_contract_bars,
) -> dict:
    """G4 anchor-no-regression: the 35 trades in the STORED 2026-07-23 scorecard whose
    exit_reason starts with 'runner_stop' (total +$15,774.05, verified by direct count against
    the stored JSON before writing this function). For each: if it is NOT level-tied in scope
    (trendline-only), mark pass-by-scope (the new confirmation path never touches it). If it
    IS in scope, locate its trigger bar in THIS run's population, run the SAME K=3 predicate in
    isolation (not embedded in the shared one-position walk -- these are winners the engine
    ALREADY entered; the question is whether the new confirmation path degrades them if it
    touches them at all, not whether they'd win a portfolio-level flat-check race), and compare
    the resulting P&L to the stored baseline P&L."""
    stored = json.loads(STORED_BASELINE_JSON.read_text(encoding="utf-8"))
    runner_trades = [t for t in stored["trades"] if str(t["exit_reason"]).startswith("runner_stop")]
    results = []
    for rt in runner_trades:
        cls = trigger_class(rt.get("triggers"))
        if cls not in ("LEVEL_tied", "BOTH"):
            results.append({"date": rt["date"], "side": rt["side"], "baseline_pnl": rt["dollar_pnl"],
                            "triggers": rt.get("triggers"), "status": "pass_by_scope_trendline_only"})
            continue
        level = rt.get("trigger_level")
        side = rt["side"]
        d = dt.date.fromisoformat(rt["date"])
        entry_dt = dt.datetime.fromisoformat(rt["entry_time_et"])
        match = find_best_population_match(population, spy_rth, d, side, level, entry_dt)
        if match is None:
            results.append({"date": rt["date"], "side": side, "baseline_pnl": rt["dollar_pnl"],
                            "level": level, "status": "match_not_found_in_population"})
            continue
        trig_idx = match["bar_idx"]
        conf_idx, checked = scan_confirmation(spy_rth, trig_idx, level, side, k)
        if conf_idx is None:
            results.append({"date": rt["date"], "side": side, "baseline_pnl": rt["dollar_pnl"],
                            "level": level, "matched_trigger_bar_idx": trig_idx,
                            "status": "predicate_would_expire_unconfirmed"})
            continue
        conf_row = spy_rth.iloc[conf_idx]
        conf_ts = efr.naive_dt(conf_row["timestamp_et"])
        spot = float(conf_row["close"])
        trade_date = conf_row["timestamp_et"].date()
        strike = pick_strike(spot, REF_EQUITY_FOR_STRIKE, side, fx.PROBE_STRIKE_TIERS)
        symbol = option_symbol(trade_date, strike, side)
        opt_df = opt_loader(symbol)
        res = resolve_confirmation_entry(opt_df, conf_ts, match["vix"], spot, strike, side)
        if not res["ok"]:
            results.append({"date": rt["date"], "side": side, "baseline_pnl": rt["dollar_pnl"],
                            "level": level, "matched_trigger_bar_idx": trig_idx,
                            "confirmation_bar_idx": conf_idx, "status": "excluded_no_opra_at_confirmation",
                            "exclude_reason": res["reason"]})
            continue
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == trade_date].reset_index(drop=True)
        walk = walk_exit_manager(
            symbol=symbol, side=side, entry_time_et=conf_ts, entry_premium=res["entry_premium"],
            qty=MIN_CONTRACTS, exit_shape=exit_shape, structure_stop_enabled=True,
            trigger_level=float(level), strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        degraded = walk.dollar_pnl < rt["dollar_pnl"]
        results.append({
            "date": rt["date"], "side": side, "level": level,
            "baseline_entry_time_et": rt["entry_time_et"], "baseline_pnl": rt["dollar_pnl"],
            "baseline_exit_reason": rt["exit_reason"], "matched_trigger_bar_idx": trig_idx,
            "confirmation_bar_idx": conf_idx, "new_entry_time_et": conf_ts.isoformat(),
            "new_entry_premium": res["entry_premium"], "new_pnl": walk.dollar_pnl,
            "new_exit_reason": walk.exit_reason,
            "status": "degraded" if degraded else "held_or_improved",
        })
    n_in_scope = sum(1 for r_ in results if r_["status"] != "pass_by_scope_trendline_only")
    n_degraded = sum(1 for r_ in results if r_["status"] == "degraded")
    return {"n_total": len(runner_trades), "n_in_scope": n_in_scope, "n_degraded": n_degraded,
            "g4_pass": n_degraded == 0, "detail": results,
            "stored_baseline_total_pnl": round(sum(t["dollar_pnl"] for t in runner_trades), 2)}


# =============================================================================== G5 -- incident anchors

def g5_bear_anchor_check(population: list[dict], spy_rth: pd.DataFrame) -> dict:
    """2026-07-27 09:40 bear @744.9 -- fully within this run's own window/population, no
    external fetch needed."""
    mask = ((spy_rth["timestamp_et"].dt.date == BEAR_ANCHOR_DATE)
            & (spy_rth["timestamp_et"].dt.time == BEAR_ANCHOR_TIME))
    rows = spy_rth.loc[mask]
    if rows.empty:
        return {"found_bar": False, "note": "2026-07-27 09:40 bar not present in the RTH frame"}
    bar_idx = int(rows.index[0])
    bar = rows.iloc[0]
    out = {"found_bar": True, "bar_idx": bar_idx,
           "bar_ohlc": {"open": float(bar["open"]), "high": float(bar["high"]),
                        "low": float(bar["low"]), "close": float(bar["close"])}}
    cand = next((c for c in population if c["bar_idx"] == bar_idx and c["side"] == "P"), None)
    out["candidate_found_in_population"] = cand is not None
    if cand is None:
        out["note"] = "no bear level-tied candidate captured at this bar_idx"
        return out
    out["candidate"] = {"level": cand["level"], "triggers_raw": cand["triggers_raw"],
                        "score": cand["score"], "blockers": cand["blockers"], "passed": cand["passed"]}
    for k in (K_PRIMARY, K_SENSITIVITY):
        conf_idx, checked = scan_confirmation(spy_rth, bar_idx, cand["level"], "P", k)
        checked_fmt = []
        for ck in checked:
            crow = spy_rth.iloc[ck["bar_idx"]]
            checked_fmt.append({
                "bar_idx": ck["bar_idx"], "timestamp_et": efr.naive_dt(crow["timestamp_et"]).isoformat(),
                "high": ck["high"], "low": ck["low"], "threshold": ck["threshold"],
                "cond1_lower_high": ck["cond1"], "cond2_breaks_floor": ck["cond2"],
            })
        out[f"k={k}"] = {
            "confirmed": conf_idx is not None, "confirmation_bar_idx": conf_idx,
            "confirmation_time_et": (efr.naive_dt(spy_rth.iloc[conf_idx]["timestamp_et"]).isoformat()
                                     if conf_idx is not None else None),
            "confirmation_close": (float(spy_rth.iloc[conf_idx]["close"]) if conf_idx is not None else None),
            "checked": checked_fmt,
        }
    return out


def _fetch_spy_5m_via_feed(date_str: str, feed: str, creds) -> list[dict]:
    url = "https://data.alpaca.markets/v2/stocks/SPY/bars"
    params = {"timeframe": "5Min", "start": f"{date_str}T13:30:00Z",
              "end": f"{date_str}T20:05:00Z", "limit": 200, "feed": feed}
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={"APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("bars", []) or []


def fetch_spy_5m_for_date(date_str: str) -> tuple[pd.DataFrame, str]:
    """5-min SPY RTH bars for one date via Alpaca REST, same pattern as
    backtest/tools/_fetch_spy_5m_2026_07_23.py (_alpaca_creds.py, .mcp.json creds, never
    printed -- only `masked()` output is logged). Tries SIP first (the established convention
    for every other historical fetch in this codebase); on a 403 (this key's plan lacks the
    real-time SIP add-on for same-day data -- confirmed live this session, 2026-07-28 12:06 ET,
    well outside any 15-min-delay window, so this is a plan/entitlement 403, not a recency
    block) falls back to the free IEX feed, DISCLOSED via the returned feed name. Returns
    (naive-timestamp DataFrame, feed_used)."""
    creds = resolve_alpaca_creds()
    log(f"  Alpaca creds source={creds.source} key={masked(creds.key)}")
    feed_used = "sip"
    try:
        bars = _fetch_spy_5m_via_feed(date_str, "sip", creds)
    except Exception as e:  # noqa: BLE001 -- e.g. HTTPError 403 (no SIP real-time entitlement)
        log(f"  SIP feed failed ({type(e).__name__}: {e}) -- falling back to IEX (free tier, disclosed)")
        feed_used = "iex"
        bars = _fetch_spy_5m_via_feed(date_str, "iex", creds)
    rows = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = (ts_utc - dt.timedelta(hours=4)).replace(tzinfo=None)  # EDT, July -- see POWERSHELL/DST notes
        rows.append({"timestamp_et": ts_et, "open": b["o"], "high": b["h"], "low": b["l"],
                    "close": b["c"], "volume": b["v"]})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
        df = df.sort_values("timestamp_et").reset_index(drop=True)
    return df, feed_used


def g5_bull_anchor_check() -> dict:
    """2026-07-28 11:05 bull @~738.1 -- ENTRY-SIGNAL-LEVEL VERIFICATION ONLY. No OPRA cache
    exists for 2026-07-28 (backtest/data/options/ has no 07-28 contracts), so no option premium
    or P&L is computed for this anchor. Also no orchestrator re-score is run for 07-28 (that
    would require a second ~390-day-plus-one run_backtest call, or a separately-warmed shorter
    window, purely to re-derive a trigger/level ALREADY established live and cited in
    markdown/doctrine/J-MARKET-PHILOSOPHY.md: 'bull 7/10 at the 738.1 reclaim on the 11:05 bar
    (level_reclaim + ribbon_flip + confluence), blocked'). This function fetches ONLY fresh
    5-min SPY bars for 07-28 (Alpaca REST, .mcp.json creds, SIP-then-IEX fallback -- see
    fetch_spy_5m_for_date) and applies the SAME frozen scan_confirmation predicate directly
    against real price action -- disclosed as a narrower check than the bear anchor's full
    population-integrated one."""
    try:
        df, feed_used = fetch_spy_5m_for_date("2026-07-28")
    except Exception as e:  # noqa: BLE001 -- network/creds failure must not crash the whole tool
        return {"found_bar": False, "error": f"{type(e).__name__}: {e}"}
    if df.empty:
        return {"found_bar": False, "feed_used": feed_used,
                "note": "Alpaca fetch returned zero bars for 2026-07-28"}
    mask = ((df["timestamp_et"].dt.date == BULL_ANCHOR_DATE)
            & (df["timestamp_et"].dt.time == BULL_ANCHOR_TIME))
    rows = df.loc[mask]
    if rows.empty:
        return {"found_bar": False, "n_bars_fetched": len(df), "feed_used": feed_used,
                "note": "no 11:05 ET bar in fetched data"}
    bar_idx = int(rows.index[0])
    bar = rows.iloc[0]
    out = {
        "found_bar": True, "bar_idx_in_fetched_frame": bar_idx, "n_bars_fetched": len(df),
        "feed_used": feed_used,
        "bar_ohlc": {"open": float(bar["open"]), "high": float(bar["high"]),
                    "low": float(bar["low"]), "close": float(bar["close"])},
        "level_cited_from_philosophy_doc": BULL_ANCHOR_LEVEL_CITED,
        "scope_disclosure": (
            "ENTRY-SIGNAL-LEVEL VERIFICATION ONLY -- no OPRA cache for 2026-07-28, so no option "
            "premium/P&L computed. Trigger+level (level_reclaim+ribbon_flip+confluence @738.1, "
            "blocked) cited from markdown/doctrine/J-MARKET-PHILOSOPHY.md, not re-derived via a "
            f"second orchestrator run. feed_used={feed_used} (SIP attempted first per this "
            "codebase's established convention; fell back to free IEX on a 403 -- confirmed live "
            "this session to be a same-day real-time-SIP entitlement gap, not a recency block, "
            "since the fetch ran at 12:06 ET, ~1hr after the anchor bar). Checks ONLY whether the "
            "frozen structure-shift predicate's price-action condition confirms, against "
            "freshly-fetched real 5-min bars."
        ),
    }
    for k in (K_PRIMARY, K_SENSITIVITY):
        conf_idx, checked = scan_confirmation(df, bar_idx, BULL_ANCHOR_LEVEL_CITED, "C", k)
        checked_fmt = [{
            "bar_idx": ck["bar_idx"], "timestamp_et": df.iloc[ck["bar_idx"]]["timestamp_et"].isoformat(),
            "high": ck["high"], "low": ck["low"], "threshold": ck["threshold"],
            "cond1_higher_low_above_level": ck["cond1"], "cond2_breaks_trigger_high": ck["cond2"],
        } for ck in checked]
        out[f"k={k}"] = {
            "confirmed": conf_idx is not None, "confirmation_bar_idx": conf_idx,
            "confirmation_time_et": (df.iloc[conf_idx]["timestamp_et"].isoformat() if conf_idx is not None else None),
            "confirmation_close_spy_price": (float(df.iloc[conf_idx]["close"]) if conf_idx is not None else None),
            "checked": checked_fmt,
        }
    return out


# =============================================================================== also-entered cohort

def compare_also_entered_cohort(r_trades, population: list[dict], spy_rth: pd.DataFrame, book_k3: dict) -> dict:
    """Answers the pre-reg comparison's first half: for trigger-bars the engine ALSO entered
    (its lagging gates passed, so r_trades has a real TradeFill), what did the new confirmation
    path do with the SAME trigger bar -- entered earlier/later at what SPY price, expired
    unconfirmed, or excluded for missing OPRA?"""
    outcomes_by_bar_idx: dict[int, tuple[str, dict]] = {}
    for t in book_k3["trades"]:
        outcomes_by_bar_idx[t["trigger_bar_idx"]] = ("entered", t)
    for t in book_k3["expired"]:
        outcomes_by_bar_idx.setdefault(t["trigger_bar_idx"], ("expired_unconfirmed", t))
    for t in book_k3["excluded"]:
        outcomes_by_bar_idx.setdefault(t["trigger_bar_idx"], ("excluded_synthetic", t))
    for t in book_k3["skipped_not_flat"]:
        outcomes_by_bar_idx.setdefault(t["trigger_bar_idx"], ("skipped_not_flat", t))

    detail = []
    for tr in r_trades:
        cls = trigger_class(tr.triggers_fired)
        if cls not in ("LEVEL_tied", "BOTH"):
            continue
        entry_dt = efr.naive_dt(tr.entry_time_et)
        d = entry_dt.date()
        match = find_best_population_match(population, spy_rth, d, tr.side, float(tr.rejection_level), entry_dt)
        if match is None:
            continue
        rec = {"date": d.isoformat(), "side": tr.side, "level": match["level"],
               "baseline_entry_time_et": entry_dt.isoformat(),
               "baseline_entry_spot": round(float(tr.entry_spot), 2),
               "trigger_bar_idx": match["bar_idx"], "origin_passed": match["passed"]}
        outcome = outcomes_by_bar_idx.get(match["bar_idx"])
        if outcome is None:
            rec["new_outcome"] = "not_walked"
        else:
            kind, t2 = outcome
            rec["new_outcome"] = kind
            if kind == "entered":
                new_spy = t2["confirmation_close_spy"]
                spy_delta = round(new_spy - float(tr.entry_spot), 4)
                rec.update({
                    "new_entry_time_et": t2["entry_time_et"], "new_entry_spy_price": new_spy,
                    "bars_to_confirm": t2["bars_to_confirm"],
                    "spy_price_delta_new_minus_baseline": spy_delta,
                    # bear (P): earlier/higher entry = MORE of the drop captured = better.
                    # bull (C): earlier/lower entry = MORE of the rise captured = better.
                    "earlier_and_better_for_side": (spy_delta > 0) if tr.side == "P" else (spy_delta < 0),
                })
        detail.append(rec)
    return {"n_baseline_level_tied_trades_checked": len(detail), "detail": detail}


# =============================================================================== main

def main() -> int:
    t_start = time.time()
    log(f"loading extended SPY/VIX data (reusing lfr.load_extended_data: {lfr.FULL_START}..{lfr.FULL_END})")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    log(f"  spy_df_raw rows={len(spy_df_raw)}  spy_rth (RTH-only, orchestrator-aligned) rows={len(spy_rth)}")

    log("running run_backtest(**SAFE_BASE_LIVE) with dual bear+bull full-raw capture")
    t0 = time.time()
    r, bear_raw, bull_raw = run_backtest_with_full_capture(
        spy_df_raw, vix_df, start_date=lfr.FULL_START, end_date=lfr.FULL_END, **efr.SAFE_BASE_LIVE,
    )
    entry_elapsed = time.time() - t0
    log(f"  done in {entry_elapsed:.1f}s -- {len(r.trades)} baseline entries, "
        f"bear_raw bars={len(bear_raw)} bull_raw bars={len(bull_raw)}")

    population = build_population(bear_raw, bull_raw)
    n_bear = sum(1 for c in population if c["side"] == "P")
    n_bull = sum(1 for c in population if c["side"] == "C")
    n_passed = sum(1 for c in population if c["passed"])
    log(f"  population: {len(population)} level-tied trigger candidates "
        f"({n_bear} bear / {n_bull} bull), {n_passed} passed / {len(population) - n_passed} blocked")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    log("baseline book (c): binary engine's own entries, exit re-derived (lfr.run_baseline, reused verbatim)")
    t1 = time.time()
    baseline_rows, baseline_dq = lfr.run_baseline(r, spy_rth, ribbon_lookup, exit_shape)
    baseline_total = round(sum(t["dollar_pnl"] for t in baseline_rows), 2)
    log(f"  baseline: n={len(baseline_rows)} total=${baseline_total:+.2f} ({time.time() - t1:.1f}s)")

    baseline_level_tied = [t for t in baseline_rows if trigger_class(t["triggers"]) in ("LEVEL_tied", "BOTH")]
    bl_total = round(sum(t["dollar_pnl"] for t in baseline_level_tied), 2)
    log(f"  baseline level-tied subset: n={len(baseline_level_tied)} total=${bl_total:+.2f} "
        f"(cited pre-reg reference: 66 trades, +$6,895 over the shorter 2026-07-23 window)")

    books: dict[int, dict] = {}
    for k in (K_PRIMARY, K_SENSITIVITY):
        t2 = time.time()
        res = run_predicate_book(k, population, spy_rth, ribbon_lookup, exit_shape)
        books[k] = res
        tot = round(sum(t["dollar_pnl"] for t in res["trades"]), 2)
        log(f"  K={k}: n_trades={len(res['trades'])} total=${tot:+.2f} "
            f"n_expired={len(res['expired'])} n_excluded_synth={len(res['excluded'])} "
            f"n_skipped_not_flat={len(res['skipped_not_flat'])} ({time.time() - t2:.1f}s)")

    all_calendar_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_days = (lfr.FULL_END - lfr.FULL_START).days
    held_out_cutoff = lfr.FULL_START + dt.timedelta(days=round(window_days * 0.75))

    gates = compute_gates(books, baseline_level_tied, all_calendar_dates, held_out_cutoff)
    log(f"  G1 (K=3): delta=${gates['K=3']['G1_delta_vs_baseline_level_tied']:+.2f} "
        f"pass={gates['K=3']['G1_pass']}")

    log("G4: 35 RUNNER_TRAIL anchor no-regression check")
    t3 = time.time()
    g4 = g4_runner_trail_check(population, spy_rth, ribbon_lookup, exit_shape)
    log(f"  G4: n_in_scope={g4['n_in_scope']}/{g4['n_total']} n_degraded={g4['n_degraded']} "
        f"pass={g4['g4_pass']} ({time.time() - t3:.1f}s)")

    log("G5: incident anchors")
    g5_bear = g5_bear_anchor_check(population, spy_rth)
    g5_bull = g5_bull_anchor_check()
    log(f"  G5 bear 07-27 09:40: found={g5_bear.get('found_bar')} "
        f"k=3 confirmed={g5_bear.get('k=3', {}).get('confirmed')}")
    log(f"  G5 bull 07-28 11:05: found={g5_bull.get('found_bar')} "
        f"k=3 confirmed={g5_bull.get('k=3', {}).get('confirmed')}")

    also_entered = compare_also_entered_cohort(r.trades, population, spy_rth, books[K_PRIMARY])

    total_elapsed = time.time() - t_start
    write_outputs(
        population=population, books=books, baseline_rows=baseline_rows, baseline_dq=baseline_dq,
        baseline_level_tied=baseline_level_tied, gates=gates, g4=g4, g5_bear=g5_bear, g5_bull=g5_bull,
        also_entered=also_entered, all_calendar_dates=all_calendar_dates, held_out_cutoff=held_out_cutoff,
        entry_elapsed=entry_elapsed, total_elapsed=total_elapsed,
    )
    return 0


# =============================================================================== outputs

def write_outputs(*, population, books, baseline_rows, baseline_dq, baseline_level_tied, gates,
                  g4, g5_bear, g5_bull, also_entered, all_calendar_dates, held_out_cutoff,
                  entry_elapsed, total_elapsed) -> None:
    stored = json.loads(STORED_BASELINE_JSON.read_text(encoding="utf-8"))
    g1k3 = gates["K=3"]["G1_pass"]
    g2k3 = gates["K=3"]["G2"]["is_majority"]
    g3k3 = gates["K=3"]["G3"]["still_positive"]
    g4pass = g4["g4_pass"]
    g5pass = bool(g5_bear.get("k=3", {}).get("confirmed")) and bool(g5_bull.get("k=3", {}).get("confirmed"))
    n_gates_pass = sum(1 for v in (g1k3, g2k3, g3k3, g4pass, g5pass) if v)

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": "analysis/recommendations/prereg-structure-shift-confirmation-2026-07-28.json (commit 773a17f0)",
        "window": {"start": lfr.FULL_START.isoformat(), "end": lfr.FULL_END.isoformat(),
                    "n_calendar_rth_days": len(all_calendar_dates)},
        "population": {
            "n_candidates": len(population),
            "n_bear": sum(1 for c in population if c["side"] == "P"),
            "n_bull": sum(1 for c in population if c["side"] == "C"),
            "n_passed_by_engine": sum(1 for c in population if c["passed"]),
            "n_blocked_by_engine": sum(1 for c in population if not c["passed"]),
        },
        "baseline_c": {
            "recomputed_over_this_window": {
                "n_trades": len(baseline_rows), "total_pnl": round(sum(t["dollar_pnl"] for t in baseline_rows), 2),
                "data_quality": baseline_dq,
                "level_tied_subset": {"n_trades": len(baseline_level_tied),
                                       "total_pnl": round(sum(t["dollar_pnl"] for t in baseline_level_tied), 2)},
                "trades": baseline_rows,
            },
            "stored_cited_reference_2026_07_23_window": {
                "n_trades": stored["headline"]["n_trades"], "total_pnl": stored["headline"]["total_pnl"],
                "note": "shorter window (2025-01-02..2026-07-22); this tool's own window runs through "
                        "2026-07-27 (the ladder_fullhist_replay tail) -- 3 extra trading days explain any "
                        "difference from the recomputed figure above.",
            },
        },
        "K=3_primary": books[K_PRIMARY],
        "K=2_sensitivity": books[K_SENSITIVITY],
        "gates": gates,
        "G4_runner_trail_anchor": g4,
        "G5_incident_anchors": {"bear_2026_07_27_0940": g5_bear, "bull_2026_07_28_1105": g5_bull},
        "also_entered_cohort_comparison": also_entered,
        "held_out_split": {"cutoff_date": held_out_cutoff.isoformat()},
        "verdict": {
            "G1_positive_aggregate_delta": g1k3, "G2_day_majority_changed_days": g2k3,
            "G3_survives_drop_best": g3k3, "G4_anchor_no_regression": g4pass,
            "G5_incident_anchors_captured": g5pass, "n_gates_pass_of_5": n_gates_pass,
            "all_pass": n_gates_pass == 5,
        },
        "runtime_seconds": {"entry_layer": round(entry_elapsed, 1), "total": round(total_elapsed, 1)},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def write_markdown(out: dict) -> None:
    v = out["verdict"]
    L = ["# Structure-shift confirmation replay -- THE PHILOSOPHY BUILD (2026-07-28)", ""]
    L.append(f"Generated {out['generated_at']}. Runner: `backtest/tools/structure_shift_replay.py`. "
              f"Pre-reg: `{out['prereg']}`. Runtime: {out['runtime_seconds']['total']}s total "
              f"({out['runtime_seconds']['entry_layer']}s entry/scoring layer).")
    L.append("")
    L.append(f"## VERDICT: {v['n_gates_pass_of_5']}/5 gates pass -- ALL_PASS={v['all_pass']}")
    L.append("")
    L.append("| Gate | Pass |")
    L.append("|---|---|")
    L.append(f"| G1 positive aggregate delta (K=3 vs baseline level-tied) | {v['G1_positive_aggregate_delta']} |")
    L.append(f"| G2 day-majority of changed days positive | {v['G2_day_majority_changed_days']} |")
    L.append(f"| G3 survives dropping single best changed trade | {v['G3_survives_drop_best']} |")
    L.append(f"| G4 anchor-no-regression (35 RUNNER_TRAIL, +$15,774) | {v['G4_anchor_no_regression']} |")
    L.append(f"| G5 both incident anchors captured (bear 07-27 + bull 07-28) | {v['G5_incident_anchors_captured']} |")
    L.append("")

    bl = out["baseline_c"]["recomputed_over_this_window"]["level_tied_subset"]
    L.append("## Book totals")
    L.append("")
    L.append("| Book | N trades | Total P&L | N expired unconfirmed | N excluded synthetic |")
    L.append("|---|---|---|---|---|")
    k3 = out["gates"]["K=3"]["stats"]
    k2 = out["gates"]["K=2"]["stats"]
    L.append(f"| **BASELINE (level-tied subset, this window)** | {bl['n_trades']} | {_fmt(bl['total_pnl'])} | -- | -- |")
    L.append(f"| **K=3 (primary)** | {k3['n_trades']} | {_fmt(k3['total_pnl'])} | "
              f"{out['gates']['K=3']['n_expired_unconfirmed']} | {out['gates']['K=3']['n_excluded_synthetic']} |")
    L.append(f"| **K=2 (sensitivity)** | {k2['n_trades']} | {_fmt(k2['total_pnl'])} | "
              f"{out['gates']['K=2']['n_expired_unconfirmed']} | {out['gates']['K=2']['n_excluded_synthetic']} |")
    L.append("")

    g4 = out["G4_runner_trail_anchor"]
    L.append(f"## G4 detail -- 35 RUNNER_TRAIL anchor (stored total {_fmt(g4['stored_baseline_total_pnl'])})")
    L.append("")
    L.append(f"n_in_scope={g4['n_in_scope']}/{g4['n_total']} (rest pass-by-scope, trendline-only). "
              f"n_degraded={g4['n_degraded']}. **G4 pass = {g4['g4_pass']}**.")
    L.append("")

    gb, gu = out["G5_incident_anchors"]["bear_2026_07_27_0940"], out["G5_incident_anchors"]["bull_2026_07_28_1105"]
    L.append("## G5 detail -- incident anchors")
    L.append("")
    L.append(f"**Bear 2026-07-27 09:40 @744.9:** found_bar={gb.get('found_bar')}, "
              f"candidate_found={gb.get('candidate_found_in_population')}")
    if gb.get("candidate_found_in_population"):
        L.append(f"  - K=3: confirmed={gb['k=3']['confirmed']}, "
                  f"confirmation_time={gb['k=3']['confirmation_time_et']}, "
                  f"confirmation_close={gb['k=3']['confirmation_close']}")
        L.append(f"  - K=2: confirmed={gb['k=2']['confirmed']}, "
                  f"confirmation_time={gb['k=2']['confirmation_time_et']}, "
                  f"confirmation_close={gb['k=2']['confirmation_close']}")
    L.append("")
    L.append(f"**Bull 2026-07-28 11:05 @~738.1:** found_bar={gu.get('found_bar')} "
              f"({gu.get('scope_disclosure', gu.get('note', gu.get('error', '')))})")
    if gu.get("found_bar"):
        L.append(f"  - K=3: confirmed={gu['k=3']['confirmed']}, "
                  f"confirmation_time={gu['k=3']['confirmation_time_et']}, "
                  f"confirmation_close_spy={gu['k=3']['confirmation_close_spy_price']}")
        L.append(f"  - K=2: confirmed={gu['k=2']['confirmed']}, "
                  f"confirmation_time={gu['k=2']['confirmation_time_et']}, "
                  f"confirmation_close_spy={gu['k=2']['confirmation_close_spy_price']}")
    L.append("")

    ae = out["also_entered_cohort_comparison"]
    L.append(f"## Also-entered cohort (engine's lagging gates already passed): "
              f"n={ae['n_baseline_level_tied_trades_checked']}")
    L.append("")
    outcomes = defaultdict(int)
    for d in ae["detail"]:
        outcomes[d["new_outcome"]] += 1
    for k_, v_ in outcomes.items():
        L.append(f"- {k_}: {v_}")
    L.append("")
    L.append("---")
    L.append("_Raw JSON with full per-trade/per-candidate detail: "
              "`analysis/recommendations/structure-shift-replay-2026-07-28.json`._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
