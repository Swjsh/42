"""day_report_card.py -- THE DAY REPORT CARD, bounded v1 (most recent 90 trading days).

The approved-but-never-built per-day diagnostic (J 2026-07-27 night: "figure out what we
need to replay to make money"). For EVERY one of the last 90 RTH days it derives, from the
SAME full-history replay machinery the published scorecards use:

  - did the engine trade? what did it make? (binary engine's own entries, REAL exit walk)
  - if flat: was there a score>=8 moment with a raw LEVEL-TIED trigger (the exact
    fleet-production candidate extraction `ladder_fullhist_replay.py` already surfaces --
    build_shared_signal.LADDER_LEVEL_TIED, bear-refused + bull-refused, level exists)?
  - and what would the BEST available same-day level-tied entry have made through the REAL
    exit walk (labelled ORACLE BOUND -- max over all same-day candidates, each walked
    independently at min-size; NOT achievable, it picks the day's best candidate with
    hindsight)?
  - ONE cause per day from a FIXED taxonomy (below). The aggregate cause histogram
    (cause x day-count x $-magnitude, ranked) IS the hypothesis generator.

===========================================================================================
FIXED TAXONOMY (closed enum -- guarded by backtest/tests/test_day_report_card.py)
===========================================================================================
  GREEN                   traded, day P&L > 0 (detail flags whether the $100 floor was met)
  EXIT_LEFT_MONEY         traded, and the exit surrendered a >=$100 day that was there
                          AFTER it bailed: either 0 < day P&L < $100 with >=$100 more
                          available at the post-exit peak, OR day P&L <= 0 with no pre-exit
                          +30% winner but the position ran >=$100 past the exit (stopped
                          out, then it ran WITHOUT us -- point-sample opens, full position)
  EXIT_TOO_LATE           traded, day P&L <= 0, but some trade's PRE-EXIT max favorable
                          excursion reached >= +30% of entry premium -- held a doctrine-
                          sized winner and rode it back to a loss (peak strictly before the
                          exit fill; a post-exit run is EXIT_LEFT_MONEY, the opposite fix)
  SHOULD_NOT_HAVE_TRADED  traded, day P&L <= 0, no pre-exit +30% winner, and the exit left
                          nothing behind either -- the entries themselves never worked
  GATE_BLOCKED            flat, but >= 1 score>=8 level-tied qualifying moment existed and
                          was blocked -- cause_detail names the MODAL blocking filter
                          (tie -> lowest id); $-magnitude = the day's ORACLE BOUND (signed:
                          negative means the gate SAVED money that day)
  CORRECTLY_FLAT          flat, triggers fired somewhere during the day but nothing reached
                          the score>=8 + level-tied qualifying bar
  NO_VOCABULARY           flat and NOT ONE trigger fired on any scored bar all day -- the
                          engine had no language for the day at all

Decision tree is ORDERED, first match wins; a day with walked trades ALWAYS classifies via
the traded tree (blocked moments on traded days are recorded descriptively, never the cause).

===========================================================================================
PRE-REGISTERED THRESHOLDS (doctrine constants, not tuned knobs)
===========================================================================================
  FOCUS_DAILY_FLOOR = $100        markdown/doctrine/FOCUS-DOCTRINE.md ($100-200/day = ONE
                                  clean +30% level trade at ~$2K)
  MFE_WINNER_PCT    = +30%        the same doctrine's "one clean +30% trade" bar (also the
                                  v15 Safe TP1 fallback percent)
  QUALIFYING_SCORE_FLOOR = 8      task-specified (LADDER-SUBSET-PREREG's floor; production
                                  risky-3 ladder arm runs floor=7 -- NOT re-derived here)

This is DESCRIPTIVE ATTRIBUTION (slicing existing replay output by pre-existing fields +
pre-registered doctrine constants) -- NOT a rule search; no BH correction applies. Any RULE
proposal derived from a cohort this surfaces must separately clear: positive aggregate AND
day-majority AND survives-drop-best AND held-out positive.

===========================================================================================
MACHINERY REUSED (nothing re-derived)
===========================================================================================
  Scoring/entry layer   lib.orchestrator.run_backtest(**engine_fullhist_replay.SAFE_BASE_LIVE)
                        over the IDENTICAL extended window (2025-01-02..2026-07-27) and the
                        IDENTICAL two-file data merge as ladder_fullhist_replay.py
                        (load_extended_data) -- so this run's full-window baseline is
                        cross-checkable against the PUBLISHED
                        analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json numbers
                        (n=191, +$5,306.95, WR 0.2984; candidates@8=2308). The cross-check
                        result is REPORTED in the output (anchor_crosscheck block).
  Candidate extraction  ladder_fullhist_replay.build_candidates / is_ladder_candidate
                        (production LADDER_LEVEL_TIED set imported from build_shared_signal,
                        bull-passed side-channel capture included)
  Entry+1 + pricing     ladder_fullhist_replay.resolve_ladder_entry (next option bar's OPEN;
                        markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md; real OPRA
                        cache only -- BS-synthetic candidates are COUNTED + disclosed and
                        excluded from every $ figure)
  Exit walk             backtest/lib/exit_manager_walk.walk_exit_manager -- the REAL live
                        exit_manager.plan_exit_actions core, RIBBON_RIDE.exit shape,
                        structure-stop enabled, 15:40 ET time stop
  Oracle sizing         min 3 contracts, ATM put via fleet_executor.PROBE_STRIKE_TIERS --
                        identical to the ladder lanes, so oracle bounds are directly
                        comparable to the published (HONEST-NULL) ladder lane numbers.

MFE / LEFT-MONEY CONVENTION: point-sample at bar OPENs (the walk's own documented NBBO-
snapshot analog), bars strictly after entry through the 15:40 time stop, split at the exit
fill: mfe_pct/peak_dollars use ONLY pre-exit bars (what was in hand while holding);
left_dollars uses ONLY post-exit bars = (post-exit peak open - entry) x 100 x qty -
realized (what the exit surrendered). Both ORACLE-flavored (peak-picking), disclosed.

KNOWN LIMITS (inherited, disclosed):
  - Replay-vs-live entry divergence: trade-level anchors 1/4 on 2026-07-17 (live reads a
    curated multi-day key-levels.json feed; the batch orchestrator recomputes levels from
    bars). Cards describe the REPLAY engine's days, not the live ledger's.
  - Bear-side candidates only (the base decision row carries bear fields; a bull-side
    oracle would need a different extraction -- out of scope for v1).
  - Historical levels here are OHLC-derived; the 2026-07-27 SIP/weighted-levels fix
    (7b4aa3f4) changes the LIVE feed, not this replay.

Run: backtest/.venv/Scripts/python.exe backtest/tools/day_report_card.py
Outputs: analysis/deep-research/DAY-CARDS-90D-2026-07-28.md
         analysis/deep-research/day-cards-90d/{date}.json   (one card per day)
         analysis/deep-research/day-cards-90d/_aggregate.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ------------------------------------------------------------------ fixed taxonomy (guarded)

VALID_CAUSES = frozenset({
    "GREEN", "CORRECTLY_FLAT", "NO_VOCABULARY", "GATE_BLOCKED",
    "EXIT_LEFT_MONEY", "EXIT_TOO_LATE", "SHOULD_NOT_HAVE_TRADED",
})

FOCUS_DAILY_FLOOR = 100.0      # FOCUS-DOCTRINE $100/day floor
MFE_WINNER_PCT = 0.30          # the +30% clean-trade bar
QUALIFYING_SCORE_FLOOR = 8     # task-specified qualifying-moment score floor
N_WINDOW_DAYS = 90

# Bear-side filter id -> short name (backtest/lib/filters.py:1406-1669, verified this build)
FILTER_NAMES = {
    1: "entry_time_window", 2: "news", 3: "budget", 4: "day_trades",
    5: "ribbon_not_BEAR_5m", 6: "ribbon_spread_lt_30c", 7: "volume_divergence",
    8: "vix_regime", 9: "breakdown_bar_vol_confirm", 10: "min_triggers",
    11: "bullish_sweep_blocker",
}


def modal_blocker_of(blockers_lists: list[list[int]]) -> Optional[int]:
    """Most frequent blocking filter id across a day's qualifying candidates; tie -> lowest
    id. None when no blockers at all (shouldn't happen for passed=False rows -- guarded by
    the caller recording it as 'blocker_unknown')."""
    counts: Counter = Counter()
    for bl in blockers_lists:
        counts.update(bl)
    if not counts:
        return None
    max_n = max(counts.values())
    return min(b for b, n in counts.items() if n == max_n)


def classify_day(
    *, n_walked_trades: int, day_pnl: Optional[float], best_left_dollars: float,
    best_mfe_pct: float, best_peak_dollars: float, n_qualifying_blocked: int,
    modal_blocker: Optional[int], oracle_bound_dollars: Optional[float],
    any_trigger_fired: bool,
) -> dict:
    """PURE, DETERMINISTIC, TOTAL. Ordered decision tree, first match wins. Returns exactly
    {cause, cause_detail, cause_dollars}. Guarded: backtest/tests/test_day_report_card.py."""
    if n_walked_trades > 0:
        pnl = float(day_pnl)
        if pnl >= FOCUS_DAILY_FLOOR:
            return {"cause": "GREEN", "cause_detail": "day_pnl>=focus_floor",
                    "cause_dollars": round(pnl, 2)}
        if pnl > 0.0 and best_left_dollars >= FOCUS_DAILY_FLOOR:
            return {"cause": "EXIT_LEFT_MONEY", "cause_detail": "positive_day_left>=focus_floor",
                    "cause_dollars": round(best_left_dollars, 2)}
        if pnl > 0.0:
            return {"cause": "GREEN", "cause_detail": "positive_below_focus_floor",
                    "cause_dollars": round(pnl, 2)}
        if best_mfe_pct >= MFE_WINNER_PCT:
            return {"cause": "EXIT_TOO_LATE", "cause_detail": "held_+30pct_winner_exited<=0",
                    "cause_dollars": round(best_peak_dollars - pnl, 2)}
        if best_left_dollars >= FOCUS_DAILY_FLOOR:
            return {"cause": "EXIT_LEFT_MONEY", "cause_detail": "exited<=0_then_ran>=focus_floor",
                    "cause_dollars": round(best_left_dollars, 2)}
        return {"cause": "SHOULD_NOT_HAVE_TRADED", "cause_detail": "never_reached_+30pct",
                "cause_dollars": round(pnl, 2)}
    if n_qualifying_blocked > 0:
        detail = f"filter_{modal_blocker}" if modal_blocker is not None else "blocker_unknown"
        dollars = round(oracle_bound_dollars, 2) if oracle_bound_dollars is not None else None
        return {"cause": "GATE_BLOCKED", "cause_detail": detail, "cause_dollars": dollars}
    if any_trigger_fired:
        return {"cause": "CORRECTLY_FLAT", "cause_detail": "triggers_seen_none_qualifying",
                "cause_dollars": 0.0}
    return {"cause": "NO_VOCABULARY", "cause_detail": "zero_triggers_all_day",
            "cause_dollars": 0.0}


def aggregate_cards(cards: list[dict]) -> dict:
    """cause histogram x day-count x $-magnitude, GATE_BLOCKED split per blocking filter,
    ranked by |total $|. Fail-loud on any cause outside the fixed taxonomy."""
    buckets: dict[str, dict] = {}
    for c in cards:
        if c["cause"] not in VALID_CAUSES:
            raise ValueError(f"unknown cause {c['cause']!r} on {c.get('date')} -- taxonomy is closed")
        key = (f"GATE_BLOCKED[{c['cause_detail']}]" if c["cause"] == "GATE_BLOCKED"
               else c["cause"])
        b = buckets.setdefault(key, {"cause_key": key, "cause": c["cause"], "n_days": 0,
                                       "total_dollars": 0.0, "n_days_dollars_unknown": 0,
                                       "dates": []})
        b["n_days"] += 1
        b["dates"].append(c["date"])
        if c["cause_dollars"] is None:
            b["n_days_dollars_unknown"] += 1
        else:
            b["total_dollars"] = round(b["total_dollars"] + c["cause_dollars"], 2)
    for b in buckets.values():
        b["dates"] = sorted(b["dates"])
        priced = b["n_days"] - b["n_days_dollars_unknown"]
        b["avg_dollars_per_day"] = round(b["total_dollars"] / priced, 2) if priced else None
    ranked = sorted(buckets.values(),
                    key=lambda b: (-abs(b["total_dollars"]), b["cause_key"]))
    return {"n_days": len(cards), "ranked": ranked}


# =========================================================================================
# Heavy pipeline below -- lazy imports so the guard test imports stay light/pure.
# =========================================================================================

TIME_STOP_ET = dt.time(15, 40)
MIN_CONTRACTS = 3
REF_EQUITY_FOR_STRIKE = 2000.0   # ATM either way at $0-10K (see ladder_fullhist_replay docstring)

OUT_DIR = ROOT / "analysis" / "deep-research" / "day-cards-90d"
OUT_MD = ROOT / "analysis" / "deep-research" / "DAY-CARDS-90D-2026-07-28.md"

# Published anchors this run must reproduce (analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json)
ANCHOR_BASELINE_N = 191
ANCHOR_BASELINE_PNL = 5306.95
ANCHOR_CANDIDATES_AT_8 = 2308


def log(msg: str) -> None:
    print(f"[day-cards] {msg}", flush=True)


def _naive(ts):
    import pandas as pd
    t = pd.Timestamp(ts)
    return t.tz_localize(None) if t.tzinfo is not None else t


def _day_opt_bars(opt_df, edate: dt.date):
    """This contract's bars on the entry date, tz-naive, chronological."""
    import pandas as pd
    ts = opt_df["timestamp_et"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    d = opt_df.assign(timestamp_et=ts)
    return d.loc[d["timestamp_et"].dt.date == edate].sort_values("timestamp_et")


def trade_excursions(opt_df, edate: dt.date, entry_ts, exit_ts,
                      entry_premium: float, qty: int, dollar_pnl: float) -> dict:
    """Point-sample (bar OPEN) favorable-excursion metrics -- see module docstring.

    mfe_pct / peak_dollars are STRICTLY PRE-EXIT (bars after entry, at or before the exit
    fill bar): they measure what was IN HAND while still holding. left_dollars is STRICTLY
    POST-EXIT (bars after the exit fill, through the 15:40 time stop): full-position value
    at the post-exit peak minus realized -- what the exit surrendered. Conflating the two
    windows flips the EXIT_TOO_LATE vs EXIT_LEFT_MONEY diagnosis (opposite fixes), which is
    exactly the bug the first draft of this tool had and the 2026-06-09 card exposed
    (MFE +378% with walked P&L -$390 is impossible pre-exit -- TP1 at +100% would have
    fired; the run was entirely post-stop-out)."""
    day = _day_opt_bars(opt_df, edate)
    entry_ts = _naive(entry_ts)
    win = day.loc[(day["timestamp_et"] > entry_ts)
                  & (day["timestamp_et"].dt.time <= TIME_STOP_ET)]
    if win.empty:
        return {"mfe_pct": 0.0, "peak_dollars": 0.0, "left_dollars": 0.0}
    if exit_ts is not None:
        exit_ts_n = _naive(exit_ts)
        pre = win.loc[win["timestamp_et"] <= exit_ts_n]
        post = win.loc[win["timestamp_et"] > exit_ts_n]
    else:
        pre, post = win, win.iloc[0:0]   # no exit fill recorded -> everything counts as held
    mfe_pct = 0.0
    peak_dollars = 0.0
    if not pre.empty:
        peak_open = float(pre["open"].max())
        mfe_pct = max(0.0, (peak_open - entry_premium) / entry_premium)
        peak_dollars = max(0.0, (peak_open - entry_premium) * 100.0 * qty)
    left_dollars = 0.0
    if not post.empty:
        post_peak = float(post["open"].max())
        left_dollars = max(0.0, (post_peak - entry_premium) * 100.0 * qty - dollar_pnl)
    return {"mfe_pct": round(mfe_pct, 4), "peak_dollars": round(peak_dollars, 2),
            "left_dollars": round(left_dollars, 2)}


def main() -> int:
    t_start = time.time()
    import pandas as pd  # noqa: F401

    import elite_bear_level_reject_gate_ab as eb
    import engine_fullhist_replay as efr
    import fleet_executor as fx
    import ladder_fullhist_replay as lfr
    import strategies as fleet_strategies
    from crypto.lib.strike_selection import pick_strike
    from lib.exit_manager_walk import walk_exit_manager
    from lib.option_pricing_real import load_contract_bars, option_symbol

    log("loading extended SPY/VIX data (identical merge to ladder_fullhist_replay)")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    all_rth_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_dates = all_rth_dates[-N_WINDOW_DAYS:]
    window_set = set(window_dates)
    log(f"  window: {window_dates[0]}..{window_dates[-1]} ({len(window_dates)} RTH days "
        f"of {len(all_rth_dates)} total)")

    log("running run_backtest(**SAFE_BASE_LIVE) with bull-passed capture (~2min)")
    t0 = time.time()
    r, bull_passed_by_idx = lfr.run_backtest_with_bull_capture(
        spy_df_raw, vix_df, start_date=lfr.FULL_START, end_date=lfr.FULL_END,
        **efr.SAFE_BASE_LIVE)
    log(f"  done in {time.time()-t0:.1f}s -- {len(r.trades)} raw entries, "
        f"{len(r.decisions)} decision rows")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    # ---------------------------------------------------------- baseline walks (all trades)
    log("walking baseline exits (full window, for anchor cross-check + in-window detail)")
    baseline_rows: list[dict] = []
    unpriceable_by_date: Counter = Counter()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            unpriceable_by_date[edate] += 1
            continue
        day_spy = spy_df_raw.loc[spy_df_raw["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            unpriceable_by_date[edate] += 1
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        walk = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(t.rejection_level) if t.rejection_level else None),
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        row = {
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": t.triggers_fired, "tier": eb.classify_tier(t.triggers_fired),
            "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
            "exit_time_et": (walk.exit_time_et.isoformat() if walk.exit_time_et else None),
            "hold_minutes": walk.hold_minutes,
        }
        if edate in window_set:
            row.update(trade_excursions(opt_df, edate, entry_time_et, walk.exit_time_et,
                                          float(t.entry_premium), int(t.qty), walk.dollar_pnl))
        baseline_rows.append(row)

    full_total = round(sum(x["dollar_pnl"] for x in baseline_rows), 2)
    full_n = len(baseline_rows)
    full_wr = round(sum(1 for x in baseline_rows if x["dollar_pnl"] > 0) / full_n, 4) if full_n else None
    log(f"  full-window baseline: n={full_n} total=${full_total:+.2f} WR={full_wr}")

    # ---------------------------------------------------------- candidates (score>=8, level-tied)
    log("extracting qualifying candidates (ladder extraction, floor>=8)")
    candidates = [c for c in lfr.build_candidates(r.decisions, bull_passed_by_idx)
                  if c["bear_score"] >= QUALIFYING_SCORE_FLOOR]
    n_cand_full = len(candidates)
    log(f"  {n_cand_full} full-window qualifying candidates (anchor expects {ANCHOR_CANDIDATES_AT_8})")

    cand_by_date: dict[dt.date, list[dict]] = {}
    for c in candidates:
        d = spy_rth.iloc[c["bar_idx"]]["timestamp_et"].date()
        cand_by_date.setdefault(d, []).append(c)

    # any-trigger-fired + scored-bar counts per day (base decision rows only)
    triggers_by_date: dict[dt.date, bool] = {}
    scored_bars_by_date: Counter = Counter()
    for row in r.decisions:
        if "action" in row:
            continue
        d = row["timestamp_et"].date()
        scored_bars_by_date[d] += 1
        if row.get("triggers_fired"):
            triggers_by_date[d] = True

    # ---------------------------------------------------------- per-day cards
    log("building day cards (oracle walks on flat days)")
    trades_by_date: dict[str, list[dict]] = {}
    for row in baseline_rows:
        trades_by_date.setdefault(row["date"], []).append(row)

    cards: list[dict] = []
    n_oracle_walks = 0
    for d in window_dates:
        iso = d.isoformat()
        day_trades = trades_by_date.get(iso, [])
        day_cands = sorted(cand_by_date.get(d, []), key=lambda c: c["bar_idx"])
        day_spy_rth = spy_rth.loc[spy_rth["timestamp_et"].dt.date == d]
        day_open = float(day_spy_rth.iloc[0]["open"]) if len(day_spy_rth) else None
        day_range_pct = (round((float(day_spy_rth["high"].max()) - float(day_spy_rth["low"].min()))
                                / day_open * 100.0, 3) if day_open else None)

        day_pnl = round(sum(t["dollar_pnl"] for t in day_trades), 2) if day_trades else None
        best_mfe = max((t.get("mfe_pct", 0.0) for t in day_trades), default=0.0)
        best_peak = max((t.get("peak_dollars", 0.0) for t in day_trades), default=0.0)
        best_left = max((t.get("left_dollars", 0.0) for t in day_trades), default=0.0)

        oracle_walks: list[dict] = []
        n_synth = 0
        oracle_bound = None
        if not day_trades and day_cands:
            day_spy_full = spy_df_raw.loc[spy_df_raw["timestamp_et"].dt.date == d].reset_index(drop=True)
            for c in day_cands:
                spot = float(c["spy_close"])
                strike = pick_strike(spot, REF_EQUITY_FOR_STRIKE, "P", fx.PROBE_STRIKE_TIERS)
                res = lfr.resolve_ladder_entry(spy_rth, c["bar_idx"], strike, d,
                                                 float(c["vix"]), spot)
                if not res["ok"]:
                    n_synth += 1
                    oracle_walks.append({
                        "trigger_time_et": _naive(spy_rth.iloc[c["bar_idx"]]["timestamp_et"]).isoformat(),
                        "bear_score": c["bear_score"], "blockers": c["blockers"],
                        "triggers": c["triggers_fired"], "rejection_level": c["rejection_level"],
                        "strike": strike, "excluded": res["reason"],
                        "synthetic_entry_premium": res.get("synthetic_entry_premium"),
                        "dollar_pnl": None,
                    })
                    continue
                rtd = efr.ribbon_tick_df_for(res["opt_df"], ribbon_lookup)
                walk = walk_exit_manager(
                    symbol=res["symbol"], side="P", entry_time_et=res["entry_time_et"],
                    entry_premium=res["entry_premium"], qty=MIN_CONTRACTS,
                    exit_shape=exit_shape, structure_stop_enabled=True,
                    trigger_level=float(c["rejection_level"]), strategy="ribbon_ride",
                    time_stop_et=TIME_STOP_ET, opt_df=res["opt_df"], ribbon_tick_df=rtd,
                    five_min_spy_df=day_spy_full,
                )
                n_oracle_walks += 1
                oracle_walks.append({
                    "trigger_time_et": _naive(spy_rth.iloc[c["bar_idx"]]["timestamp_et"]).isoformat(),
                    "bear_score": c["bear_score"], "blockers": c["blockers"],
                    "triggers": c["triggers_fired"], "rejection_level": c["rejection_level"],
                    "strike": strike, "symbol": res["symbol"],
                    "entry_premium": round(res["entry_premium"], 4),
                    "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason,
                })
                if oracle_bound is None or walk.dollar_pnl > oracle_bound:
                    oracle_bound = walk.dollar_pnl

        cls = classify_day(
            n_walked_trades=len(day_trades), day_pnl=day_pnl,
            best_left_dollars=best_left, best_mfe_pct=best_mfe, best_peak_dollars=best_peak,
            n_qualifying_blocked=len(day_cands) if not day_trades else 0,
            modal_blocker=modal_blocker_of([c["blockers"] for c in day_cands]) if (
                day_cands and not day_trades) else None,
            oracle_bound_dollars=oracle_bound,
            any_trigger_fired=triggers_by_date.get(d, False),
        )
        cards.append({
            "date": iso,
            "cause": cls["cause"], "cause_detail": cls["cause_detail"],
            "cause_dollars": cls["cause_dollars"],
            "engine": {
                "n_walked_trades": len(day_trades), "day_pnl": day_pnl,
                "n_unpriceable_raw_entries": int(unpriceable_by_date.get(d, 0)),
                "trades": day_trades,
                "best_mfe_pct": round(best_mfe, 4), "best_peak_dollars": round(best_peak, 2),
                "best_left_dollars": round(best_left, 2),
            },
            "qualifying_moments": {
                "n": len(day_cands),
                "note": ("descriptive only -- day classified by traded tree"
                          if (day_trades and day_cands) else None),
                "oracle_bound_dollars": oracle_bound,
                "oracle_label": ("ORACLE BOUND -- best same-day candidate with hindsight, "
                                  "NOT achievable") if oracle_bound is not None else None,
                "n_synthetic_excluded": n_synth,
                "candidates": oracle_walks if not day_trades else [
                    {"trigger_time_et": _naive(spy_rth.iloc[c["bar_idx"]]["timestamp_et"]).isoformat(),
                     "bear_score": c["bear_score"], "blockers": c["blockers"],
                     "triggers": c["triggers_fired"], "rejection_level": c["rejection_level"]}
                    for c in day_cands],
            },
            "day_context": {"spy_range_pct": day_range_pct,
                             "n_scored_bars": int(scored_bars_by_date.get(d, 0)),
                             "any_trigger_fired": triggers_by_date.get(d, False)},
        })

    log(f"  {len(cards)} cards, {n_oracle_walks} oracle walks")

    # ---------------------------------------------------------- aggregate + anchors
    agg = aggregate_cards(cards)
    window_pnl = round(sum(c["engine"]["day_pnl"] or 0.0 for c in cards), 2)
    anchor = {
        "baseline_n_trades": {"got": full_n, "expected": ANCHOR_BASELINE_N,
                               "pass": full_n == ANCHOR_BASELINE_N},
        "baseline_total_pnl": {"got": full_total, "expected": ANCHOR_BASELINE_PNL,
                                "pass": abs(full_total - ANCHOR_BASELINE_PNL) < 1.0},
        "candidates_at_floor8": {"got": n_cand_full, "expected": ANCHOR_CANDIDATES_AT_8,
                                  "pass": n_cand_full == ANCHOR_CANDIDATES_AT_8},
        "source": "analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json",
    }
    all_pass = all(v["pass"] for k, v in anchor.items() if isinstance(v, dict))
    log(f"anchor cross-check vs published ladder JSON: ALL PASS = {all_pass}")

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "tool": "backtest/tools/day_report_card.py",
        "window": {"start": window_dates[0].isoformat(), "end": window_dates[-1].isoformat(),
                    "n_days": len(window_dates)},
        "taxonomy": sorted(VALID_CAUSES),
        "thresholds": {"FOCUS_DAILY_FLOOR": FOCUS_DAILY_FLOOR,
                        "MFE_WINNER_PCT": MFE_WINNER_PCT,
                        "QUALIFYING_SCORE_FLOOR": QUALIFYING_SCORE_FLOOR},
        "anchor_crosscheck": {"all_pass": all_pass, **anchor},
        "engine_window_pnl": window_pnl,
        "aggregate": agg,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for c in cards:
        (OUT_DIR / f"{c['date']}.json").write_text(
            json.dumps(c, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "_aggregate.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {len(cards)} per-day cards + _aggregate.json -> {OUT_DIR}")
    write_markdown(out, cards)
    log(f"wrote {OUT_MD}")
    return 0


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def write_markdown(out: dict, cards: list[dict]) -> None:
    agg = out["aggregate"]
    L = ["# THE DAY REPORT CARD -- last 90 trading days "
         f"({out['window']['start']}..{out['window']['end']})", ""]
    L.append(f"Generated {out['generated_at']}. Tool: `{out['tool']}` "
              f"({out['runtime_seconds']}s). Per-day cards: "
              "`analysis/deep-research/day-cards-90d/{date}.json`.")
    L.append("")
    L.append("## Verdict first -- the ranked hypothesis generator")
    L.append("")
    L.append(f"Engine actual over the window: **{_fmt(out['engine_window_pnl'])}** across "
              f"{out['window']['n_days']} days. Cause histogram (ranked by |$|):")
    L.append("")
    L.append("| Rank | Cause | N days | Total $ | Avg $/day | $-unknown days |")
    L.append("|---|---|---|---|---|---|")
    for i, b in enumerate(agg["ranked"], 1):
        L.append(f"| {i} | **{b['cause_key']}** | {b['n_days']} | {_fmt(b['total_dollars'])} | "
                  f"{_fmt(b['avg_dollars_per_day']) if b['avg_dollars_per_day'] is not None else 'n/a'} | "
                  f"{b['n_days_dollars_unknown']} |")
    L.append("")
    L.append("$-semantics per cause: GREEN/SHOULD_NOT_HAVE_TRADED = the day's realized P&L; "
              "EXIT_LEFT_MONEY = money available at the POST-exit peak minus realized "
              "(oracle-flavored); EXIT_TOO_LATE = give-back from the best PRE-exit peak; "
              "GATE_BLOCKED = the day's ORACLE BOUND (signed -- negative means the gate "
              "SAVED money); CORRECTLY_FLAT/NO_VOCABULARY = $0.")
    L.append("")
    L.append("## Anchor cross-check (this run vs the published ladder-replay JSON)")
    L.append("")
    ac = out["anchor_crosscheck"]
    L.append(f"- ALL PASS: **{ac['all_pass']}** (source: `{ac['source']}`)")
    for k in ("baseline_n_trades", "baseline_total_pnl", "candidates_at_floor8"):
        v = ac[k]
        L.append(f"- {k}: got {v['got']} vs expected {v['expected']} -> "
                  f"{'PASS' if v['pass'] else 'FAIL'}")
    L.append("")
    L.append("## Pre-registered thresholds (doctrine constants, not tuned)")
    L.append("")
    th = out["thresholds"]
    L.append(f"- FOCUS_DAILY_FLOOR = ${th['FOCUS_DAILY_FLOOR']:.0f} (FOCUS-DOCTRINE)")
    L.append(f"- MFE_WINNER_PCT = +{th['MFE_WINNER_PCT']:.0%} (the one-clean-trade bar)")
    L.append(f"- QUALIFYING_SCORE_FLOOR = {th['QUALIFYING_SCORE_FLOOR']} (task-specified)")
    L.append("")
    L.append("## Filter legend (GATE_BLOCKED sub-causes)")
    L.append("")
    for fid, name in sorted(FILTER_NAMES.items()):
        L.append(f"- filter_{fid} = {name}")
    L.append("")
    L.append("## Per-day cards")
    L.append("")
    L.append("| Date | Cause | $ | Engine P&L | Trades | Qual. moments | Oracle bound | SPY range % |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c in cards:
        q = c["qualifying_moments"]
        L.append(f"| {c['date']} | {c['cause']}"
                  + (f"[{c['cause_detail']}]" if c["cause"] == "GATE_BLOCKED" else "")
                  + f" | {_fmt(c['cause_dollars']) if c['cause_dollars'] is not None else 'n/a'}"
                  f" | {_fmt(c['engine']['day_pnl']) if c['engine']['day_pnl'] is not None else '--'}"
                  f" | {c['engine']['n_walked_trades']} | {q['n']}"
                  f" | {_fmt(q['oracle_bound_dollars']) if q['oracle_bound_dollars'] is not None else '--'}"
                  f" | {c['day_context']['spy_range_pct']} |")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    L.append("- DESCRIPTIVE ATTRIBUTION, not search -- no BH applies; any RULE derived from a "
              "cohort here must separately clear positive-aggregate AND day-majority AND "
              "survives-drop-best AND held-out-positive.")
    L.append("- ORACLE BOUND picks the day's best candidate WITH HINDSIGHT and walks it at "
              "min-size (3x ATM put) through the real exit walk -- an upper bound, never an "
              "achievable expectation. Left-money/give-back metrics are likewise peak-picking.")
    L.append("- Entry+1 convention (next option bar's OPEN); point-sample-at-open excursions; "
              "real OPRA fills only -- BS-synthetic candidates counted+disclosed per card, "
              "excluded from every $ figure.")
    L.append("- Replay-vs-live divergence is KNOWN (trade-level anchors 1/4 on 2026-07-17; "
              "live reads curated key-levels.json, the batch orchestrator recomputes levels "
              "from bars). These cards describe the REPLAY engine's days.")
    L.append("- Bear-side candidates only; extra setups (bollinger_squeeze etc.) and "
              "Bold/aggressive out of scope (same scope as the published fullhist scorecard).")
    n_unpriceable = sum(1 for c in cards if c["engine"]["n_unpriceable_raw_entries"] > 0
                         and c["engine"]["n_walked_trades"] == 0)
    L.append(f"- Days with raw entries but ZERO priceable (no OPRA cache): {n_unpriceable} "
              "(flagged per-card as n_unpriceable_raw_entries; classified via the flat tree).")
    L.append("")
    L.append("---")
    L.append("_Guard: `backtest/tests/test_day_report_card.py` (taxonomy enum + determinism, "
              "RED-proofed). Aggregate JSON: `analysis/deep-research/day-cards-90d/_aggregate.json`._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
