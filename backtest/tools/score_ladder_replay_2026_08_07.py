"""score_ladder_replay_2026_08_07.py -- SCORE-LADDER-V2 (demerit semantics) replay evidence.

Prereg (frozen + committed BEFORE this file existed, commit c2ec28f3):
    analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json

J's 4th+ ask: per-arm score-conditional admission -- DEMOTABLE filters no longer veto for
LADDER arms; each active demotable blocker subtracts 1 MORE from the reported side score
(double-demerit, pinned by J's worked example: bull_score 10, sole blocker f10 -> adjusted 9);
the arm enters when adjusted_score >= its rung. NON-DEMOTABLE gates stay absolute on every
rung: entry window (f1), spread (f6), bull f9 VIX>=22 hard, bear f8's VIX>23 hard component,
bull f11 / bear f10 in full (trigger count AND level-tied requirement), sweep blockers, and
anything not explicitly demotable (fail-closed). DEMOTABLE: bull {5,7,8,10}, bear {5,7,8,9}
(bear 8 only while vix<=23).

DISTINCT FROM THE DEAD LANES (graveyard guard, per prereg _provenance_audit): NOT filter
deletion, NOT filter-8 relax, NOT the raw-floor bear ladder (deb781ea, disarmed 2026-07-27 on
LADDER-FULLHIST evidence) -- see the prereg for the four material differences.

MECHANICS (mirrors ladder_fullhist_replay.py wherever possible -- same loaders, same
walk_exit_manager exit core, same real-OPRA-only P&L stance):
  * orchestrator.run_backtest(**SAFE_BASE_LIVE_NOW) with pass-through capture of BOTH
    evaluate_bearish_setup and evaluate_bullish_setup (full result per bar_idx).
  * Lane per rung = binary r.trades + ladder-extra candidates, merged chronologically,
    ONE POSITION AT A TIME (NOT_FLAT) -- extras can suppress binary entries (occupancy cost
    is charged honestly). The BASELINE lane runs the SAME occupancy walk with zero extras.
  * Extras: ATM via fleet_executor.PROBE_STRIKE_TIERS (the live _ladder_plan's own table),
    qty=3 study min-size, entry = NEXT option bar OPEN (entry+1), exit via
    walk_exit_manager -> exit_manager.plan_exit_actions ONLY (ribbon_ride registry shape,
    structure stop at the raw rejection/reclaim level), time stop 15:40.
  * BS-synthetic-priced candidates are flagged + counted + EXCLUDED from P&L (C1).

Run: backtest/.venv/Scripts/python.exe backtest/tools/score_ladder_replay_2026_08_07.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb              # noqa: E402
import strategies as fleet_strategies                       # noqa: E402
import fleet_executor as fx                                    # noqa: E402  -- PROBE_STRIKE_TIERS
import engine_fullhist_replay as efr                             # noqa: E402
import lib.orchestrator as orch_mod                                # noqa: E402
from lib.orchestrator import run_backtest                            # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                   # noqa: E402
from lib.option_pricing_real import (                                  # noqa: E402
    bar_at_or_after, load_contract_bars, option_symbol,
)
from crypto.lib.strike_selection import pick_strike                      # noqa: E402

DATA = REPO / "data"
OLD_SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-08-06.csv"
NEW_VIX_FILE = DATA / "vix_5m_2026-05-19_2026-08-06.csv"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 8, 6)
OLD_WINDOW_END = dt.date(2026, 7, 22)

WEEK_DAYS = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]

MIN_CONTRACTS_STUDY = 3
REF_EQUITY_FOR_STRIKE = 2000.0   # PROBE_STRIKE_TIERS resolves ATM across the whole $0-10K band
RUNGS = (6, 7, 8, 9)
SHIP_RUNGS = {"risky-3": 7, "risky-1": 8}

VIX_HARD_CAP_BEAR = 23.0   # params.json vix_bear_hard_cap (bear f8 hard component)

# Demotable sets, per the frozen prereg. Everything else in a blocker list = absolute veto.
DEMOTABLE_BULL = {5, 7, 8, 10}
DEMOTABLE_BEAR = {5, 7, 8, 9}
BULL_BASE = 11
BEAR_BASE = 10

OUT_DIR = ROOT / "analysis" / "deep-research"
OUT_JSON = OUT_DIR / "SCORE-LADDER-REPLAY-2026-08-07.json"

# SAFE_BASE re-verified against CURRENT automation/state/params.json (2026-08-07):
#   block_elite_bull=False (flipped since the 07-27 tools; live 09:46 + 12:06 ELITE bull
#   entries today prove the live path takes these), initial_equity=5727.91 (safe-2 live-read
#   08-06 ~18:55 ET per WEEK-ORDER-2026-08-10.md section 3). All other SAFE_BASE keys diffed
#   against params.json today: match.
SAFE_BASE_LIVE_NOW = dict(eb.SAFE_BASE, initial_equity=5727.91, block_elite_bull=False)


def log(msg: str) -> None:
    print(f"[ladder-v2] {msg}", flush=True)


# =============================================================================== data load

def load_extended_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy_old = pd.read_csv(OLD_SPY_FILE)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY_FILE)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    # BYTE-IDENTICAL loading convention to ladder_fullhist_replay.load_extended_data:
    # plain pd.to_datetime, NO utc=True, NO tz_convert. Both caches carry FIXED -04:00
    # wall-clock stamps year-round (documented wall-v1 frame; tz_convert to
    # America/New_York would shift every WINTER bar by an hour -- the exact DST frame
    # artifact lib/et_frame.py exists to prevent). Component access (.dt.date/.dt.time)
    # on a fixed-offset series yields the stamped WALL values, which is what every
    # downstream consumer (rth mask, ribbon lookup, efr.naive_dt) expects.
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX_FILE)
    vix_old["timestamp_et"] = pd.to_datetime(vix_old["timestamp_et"])
    vix_new = pd.read_csv(NEW_VIX_FILE)
    vix_new["timestamp_et"] = pd.to_datetime(vix_new["timestamp_et"])
    vix_tail = vix_new[vix_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    vix_df = (pd.concat([vix_old, vix_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))
    return spy_df, vix_df


def build_rth_frame(spy_df_full: pd.DataFrame) -> pd.DataFrame:
    """Same rth_mask + reset_index split orchestrator builds internally -- bar_idx space
    parity (see ladder_fullhist_replay.build_rth_frame's docstring)."""
    mask = (
        (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    return spy_df_full.loc[mask].reset_index(drop=True)


# ==================================================================== both-side capture

def run_backtest_with_full_capture(spy_df, vix_df, start_date, end_date, **kwargs):
    """run_backtest + a {bar_idx: result-summary} side channel for BOTH sides. Pure
    pass-through wrappers (same args in, same object out); originals restored in finally."""
    bear_by_idx: dict[int, dict] = {}
    bull_by_idx: dict[int, dict] = {}
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup

    def _cap_bear(ctx, **kw):
        res = orig_bear(ctx, **kw)
        bear_by_idx[ctx.bar_idx] = dict(
            score=int(res.bear_score), blockers=list(res.blockers),
            triggers=list(res.triggers_fired), level=res.rejection_level,
            passed=bool(res.passed), vix=float(ctx.vix_now),
            spot=float(ctx.bar["close"]),
        )
        return res

    def _cap_bull(ctx, **kw):
        res = orig_bull(ctx, **kw)
        bull_by_idx[ctx.bar_idx] = dict(
            score=int(res.bull_score), blockers=list(res.blockers),
            triggers=list(res.triggers_fired), level=res.reclaim_level,
            passed=bool(res.passed), vix=float(ctx.vix_now),
            spot=float(ctx.bar["close"]),
        )
        return res

    orch_mod.evaluate_bearish_setup = _cap_bear
    orch_mod.evaluate_bullish_setup = _cap_bull
    try:
        r = run_backtest(spy_df, vix_df, start_date=start_date, end_date=end_date, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
    return r, bear_by_idx, bull_by_idx


# =============================================================================== admission

def side_admission(side: str, score: int, blockers: list[int], triggers: list[str],
                   level, vix: float) -> Optional[dict]:
    """Frozen SCORE-LADDER-V2 admission for one side of one bar. Returns None when the tick
    can never enter on ANY rung (non-demotable blocker / no level / bear VIX hard), else
    {'adjusted': int, 'n_demotable': int} -- lane code compares adjusted >= rung."""
    demotable = DEMOTABLE_BULL if side == "C" else DEMOTABLE_BEAR
    active = list(blockers or [])
    if not active:
        return None   # binary pass -- handled as a binary trade, not a ladder extra
    non_demotable_hit = [b for b in active if b not in demotable]
    if non_demotable_hit:
        return None
    if side == "P" and 8 in active and vix is not None and vix > VIX_HARD_CAP_BEAR:
        return None   # bear f8 hard component stays absolute
    if level is None or not isinstance(level, (int, float)):
        return None   # a ladder entry is never stop-less
    adjusted = int(score) - len(active)   # double-demerit, pinned by J's 10:15 example
    return {"adjusted": adjusted, "n_demotable": len(active)}


def build_candidates(bear_by_idx: dict, bull_by_idx: dict, spy_rth: pd.DataFrame) -> list[dict]:
    """Floor-independent candidate list (admissible on at least rung 6). Neither side may
    have passed (those bars are binary trades). Side conflict: higher adjusted wins; tie
    -> skip (disclosed)."""
    out = []
    for idx in sorted(set(bear_by_idx) | set(bull_by_idx)):
        bear = bear_by_idx.get(idx)
        bull = bull_by_idx.get(idx)
        if (bear and bear["passed"]) or (bull and bull["passed"]):
            continue
        opts = []
        if bear:
            a = side_admission("P", bear["score"], bear["blockers"], bear["triggers"],
                               bear["level"], bear["vix"])
            if a:
                opts.append(("P", bear, a))
        if bull:
            a = side_admission("C", bull["score"], bull["blockers"], bull["triggers"],
                               bull["level"], bull["vix"])
            if a:
                opts.append(("C", bull, a))
        if not opts:
            continue
        if len(opts) == 2:
            if opts[0][2]["adjusted"] == opts[1][2]["adjusted"]:
                continue   # exact tie -> no entry (prereg side_conflict_rule)
            opts.sort(key=lambda o: -o[2]["adjusted"])
        side, blk, adm = opts[0]
        bar = spy_rth.iloc[idx]
        out.append({
            "bar_idx": int(idx), "side": side,
            "timestamp_et": bar["timestamp_et"],
            "date": bar["timestamp_et"].date().isoformat(),
            "score": blk["score"], "blockers": blk["blockers"],
            "triggers": blk["triggers"], "level": float(blk["level"]),
            "vix": blk["vix"], "spot": blk["spot"],
            "adjusted": adm["adjusted"], "n_demotable": adm["n_demotable"],
        })
    return out


# =============================================================================== entry+1

def next_bar_same_day(spy_df: pd.DataFrame, trigger_idx: int) -> Optional[int]:
    next_idx = trigger_idx + 1
    if next_idx >= len(spy_df):
        return None
    trig_date = spy_df.iloc[trigger_idx]["timestamp_et"].date()
    if spy_df.iloc[next_idx]["timestamp_et"].date() != trig_date:
        return None
    return next_idx


_OPT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def cached_contract_bars(symbol: str):
    if symbol not in _OPT_CACHE:
        _OPT_CACHE[symbol] = load_contract_bars(symbol)
    return _OPT_CACHE[symbol]


def resolve_extra_entry(spy_rth: pd.DataFrame, cand: dict) -> dict:
    next_idx = next_bar_same_day(spy_rth, cand["bar_idx"])
    if next_idx is None:
        return {"ok": False, "reason": "no_next_bar_same_day"}
    next_ts = spy_rth.iloc[next_idx]["timestamp_et"]
    trade_date = spy_rth.iloc[cand["bar_idx"]]["timestamp_et"].date()
    strike = pick_strike(float(cand["spot"]), REF_EQUITY_FOR_STRIKE, cand["side"],
                         fx.PROBE_STRIKE_TIERS)
    symbol = option_symbol(trade_date, int(strike), cand["side"])
    opt_df = cached_contract_bars(symbol)
    if opt_df is None:
        return {"ok": False, "reason": "no_opra_cache", "strike": strike, "symbol": symbol}
    ob = bar_at_or_after(opt_df, next_ts)
    if ob is None:
        return {"ok": False, "reason": "opra_cached_but_no_bar_at_or_after_next",
                "strike": strike, "symbol": symbol}
    return {"ok": True, "symbol": symbol, "strike": strike, "opt_df": opt_df,
            "entry_time_et": efr.naive_dt(ob.timestamp_et),
            "entry_premium": float(ob.open)}


# =============================================================================== lane walk

def walk_lane(rung: Optional[int], candidates: list[dict], binary_trades: list,
              spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame, exit_shape: dict) -> dict:
    """One lane, one rung (None = binary control), chronological, NOT_FLAT.
    Events: binary trades (decision time = entry_time) + rung-admitted extras (decision time
    = trigger bar end). Returns {'trades': [...], 'excluded': [...], 'suppressed_binary': n}."""
    events = []
    for t in binary_trades:
        events.append(("binary", efr.naive_dt(t.entry_time_et), t))
    if rung is not None:
        for c in candidates:
            if c["adjusted"] >= rung:
                trig_end = efr.naive_dt(c["timestamp_et"]) + dt.timedelta(minutes=5)
                events.append(("extra", trig_end, c))
    events.sort(key=lambda e: e[1])

    trades, excluded = [], []
    suppressed_binary = 0
    flat_until: Optional[dt.datetime] = None

    for kind, decision_ts, payload in events:
        if flat_until is not None and decision_ts <= flat_until:
            if kind == "binary":
                suppressed_binary += 1
            continue
        if kind == "binary":
            t = payload
            edate = eb.entry_date(t)
            symbol = option_symbol(edate, int(t.strike), t.side)
            opt_df = cached_contract_bars(symbol)
            if opt_df is None:
                excluded.append({"kind": "binary", "date": edate.isoformat(),
                                 "reason": "no_opra_cache", "symbol": symbol})
                continue
            day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == edate].reset_index(drop=True)
            if day_spy.empty:
                excluded.append({"kind": "binary", "date": edate.isoformat(),
                                 "reason": "no_spy_day", "symbol": symbol})
                continue
            entry_time = efr.naive_dt(t.entry_time_et)
            rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
            res = walk_exit_manager(
                symbol=symbol, side=t.side, entry_time_et=entry_time,
                entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
                structure_stop_enabled=True,
                trigger_level=(float(t.rejection_level) if t.rejection_level else None),
                strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
                opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
            )
            exit_ts = res.exit_time_et if res.exit_time_et is not None else entry_time
            flat_until = exit_ts
            trades.append({
                "kind": "binary", "date": edate.isoformat(),
                "entry_time_et": entry_time.isoformat(), "side": t.side, "symbol": symbol,
                "qty": int(t.qty), "entry_premium": round(float(t.entry_premium), 4),
                "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                "exit_time_et": exit_ts.isoformat() if exit_ts else None,
                "hold_minutes": res.hold_minutes, "setup": t.setup,
            })
        else:
            c = payload
            r = resolve_extra_entry(spy_rth, c)
            if not r.get("ok"):
                excluded.append({"kind": "extra", "date": c["date"],
                                 "reason": r.get("reason"), "side": c["side"],
                                 "score": c["score"], "blockers": c["blockers"],
                                 "adjusted": c["adjusted"]})
                continue
            day_spy = spy_rth.loc[
                spy_rth["timestamp_et"].dt.date == pd.Timestamp(c["timestamp_et"]).date()
            ].reset_index(drop=True)
            rtd = efr.ribbon_tick_df_for(r["opt_df"], ribbon_lookup)
            res = walk_exit_manager(
                symbol=r["symbol"], side=c["side"], entry_time_et=r["entry_time_et"],
                entry_premium=r["entry_premium"], qty=MIN_CONTRACTS_STUDY,
                exit_shape=exit_shape, structure_stop_enabled=True,
                trigger_level=float(c["level"]), strategy="ribbon_ride",
                time_stop_et=efr.TIME_STOP_ET, opt_df=r["opt_df"], ribbon_tick_df=rtd,
                five_min_spy_df=day_spy,
            )
            exit_ts = res.exit_time_et if res.exit_time_et is not None else r["entry_time_et"]
            flat_until = exit_ts
            trades.append({
                "kind": "extra", "date": c["date"],
                "entry_time_et": r["entry_time_et"].isoformat(), "side": c["side"],
                "symbol": r["symbol"], "qty": MIN_CONTRACTS_STUDY,
                "entry_premium": round(r["entry_premium"], 4),
                "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                "exit_time_et": exit_ts.isoformat() if exit_ts else None,
                "hold_minutes": res.hold_minutes,
                "score": c["score"], "blockers": c["blockers"], "adjusted": c["adjusted"],
                "triggers": c["triggers"], "trigger_time_et": efr.naive_dt(c["timestamp_et"]).isoformat(),
            })
    return {"trades": trades, "excluded": excluded, "suppressed_binary": suppressed_binary}


# =============================================================================== stats

def day_pnl_series(trades: list[dict]) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float)
    df = pd.DataFrame(trades)
    return df.groupby("date")["dollar_pnl"].sum()


def lane_stats(lane: dict) -> dict:
    trades = lane["trades"]
    n = len(trades)
    extras = [t for t in trades if t["kind"] == "extra"]
    if n == 0:
        return {"n_trades": 0, "total_pnl": 0.0, "win_rate": None, "n_extras": 0,
                "extras_pnl": 0.0, "suppressed_binary": lane["suppressed_binary"],
                "n_excluded": len(lane["excluded"])}
    df = pd.DataFrame(trades)
    per_day = df.groupby("date")["dollar_pnl"].sum()
    worst_day = float(per_day.min()) if len(per_day) else 0.0
    best_trade = float(df["dollar_pnl"].max())
    return {
        "n_trades": n,
        "total_pnl": round(float(df["dollar_pnl"].sum()), 2),
        "win_rate": round(float((df["dollar_pnl"] > 0).mean()), 4),
        "avg_pnl_per_trade": round(float(df["dollar_pnl"].mean()), 2),
        "n_extras": len(extras),
        "extras_pnl": round(float(sum(t["dollar_pnl"] for t in extras)), 2),
        "extras_win_rate": (round(float(pd.Series([t["dollar_pnl"] for t in extras]).gt(0).mean()), 4)
                             if extras else None),
        "suppressed_binary": lane["suppressed_binary"],
        "n_excluded": len(lane["excluded"]),
        "n_excluded_extra_no_opra": sum(1 for e in lane["excluded"]
                                         if e["kind"] == "extra" and "opra" in str(e["reason"])),
        "worst_day": round(worst_day, 2),
        "worst_day_date": (str(per_day.idxmin()) if len(per_day) else None),
        "best_trade": round(best_trade, 2),
        "total_minus_best_trade": round(float(df["dollar_pnl"].sum()) - best_trade, 2),
        "win_days": int((per_day > 0).sum()),
        "trading_days": int(len(per_day)),
    }


def bootstrap_p_mean_gt0(values: list[float], n_boot: int = 10000, seed: int = 7) -> Optional[float]:
    """One-sided bootstrap p-value for mean(values) <= 0 (small p = mean reliably > 0)."""
    import random
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    hits = 0
    for _ in range(n_boot):
        s = sum(values[rng.randrange(n)] for _ in range(n))
        if s <= 0:
            hits += 1
    return round(hits / n_boot, 5)


def benjamini_hochberg(pvals: dict[str, Optional[float]], q: float = 0.10) -> dict[str, bool]:
    items = [(k, v) for k, v in pvals.items() if v is not None]
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    passed = {k: False for k, _ in items}
    max_i = 0
    for i, (k, p) in enumerate(items, start=1):
        if p <= q * i / m:
            max_i = i
    for i, (k, p) in enumerate(items, start=1):
        if i <= max_i:
            passed[k] = True
    return passed


# =============================================================================== main

def main() -> int:
    t0 = time.time()
    log(f"loading SPY/VIX {FULL_START}..{FULL_END}")
    spy_df_raw, vix_df = load_extended_data()
    spy_rth = build_rth_frame(spy_df_raw)
    log(f"  raw={len(spy_df_raw)} rows, rth={len(spy_rth)} rows, "
        f"days={spy_rth['timestamp_et'].dt.date.nunique()}")

    log("run_backtest(**SAFE_BASE_LIVE_NOW) with BOTH-side capture")
    t1 = time.time()
    r, bear_by_idx, bull_by_idx = run_backtest_with_full_capture(
        spy_df_raw, vix_df, start_date=FULL_START, end_date=FULL_END, **SAFE_BASE_LIVE_NOW,
    )
    log(f"  done {time.time()-t1:.1f}s -- {len(r.trades)} binary trades, "
        f"{len(bear_by_idx)} bear rows, {len(bull_by_idx)} bull rows captured")

    candidates = build_candidates(bear_by_idx, bull_by_idx, spy_rth)
    from collections import Counter
    cnt_by_rung = {rung: sum(1 for c in candidates if c["adjusted"] >= rung) for rung in RUNGS}
    log(f"  candidates (admissible at rung>=6): {len(candidates)}; per rung: {cnt_by_rung}")
    log(f"  by side: {Counter(c['side'] for c in candidates)}")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    lanes: dict = {}
    log("walking BASELINE (binary, occupancy-applied) lane")
    t2 = time.time()
    lanes["binary"] = walk_lane(None, candidates, r.trades, spy_rth, ribbon_lookup, exit_shape)
    log(f"  binary: {lane_stats(lanes['binary'])['n_trades']} trades "
        f"total ${lane_stats(lanes['binary'])['total_pnl']:+.2f} ({time.time()-t2:.1f}s)")

    for rung in RUNGS:
        t3 = time.time()
        lanes[str(rung)] = walk_lane(rung, candidates, r.trades, spy_rth, ribbon_lookup, exit_shape)
        s = lane_stats(lanes[str(rung)])
        log(f"  rung {rung}: n={s['n_trades']} (extras {s['n_extras']}) "
            f"total ${s['total_pnl']:+.2f} extras ${s['extras_pnl']:+.2f} "
            f"suppressed_binary={s['suppressed_binary']} ({time.time()-t3:.1f}s)")

    # ---- per-day tables (week + population), per lane
    out_lanes = {}
    for key, lane in lanes.items():
        stats = lane_stats(lane)
        per_day = day_pnl_series(lane["trades"])
        week = {d: round(float(per_day.get(d, 0.0)), 2) for d in WEEK_DAYS}
        out_lanes[key] = {
            "stats": stats,
            "week_by_day": week,
            "week_total": round(sum(week.values()), 2),
            "per_day": {str(k): round(float(v), 2) for k, v in per_day.items()},
            "trades": lane["trades"],
            "excluded": lane["excluded"],
        }

    out = {
        "_doc": __doc__,
        "prereg": "analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json (commit c2ec28f3)",
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                    "n_rth_days": int(spy_rth["timestamp_et"].dt.date.nunique())},
        "config": {k: (str(v) if isinstance(v, dt.time) else v)
                    for k, v in SAFE_BASE_LIVE_NOW.items()},
        "candidates_total": len(candidates),
        "candidates_per_rung": cnt_by_rung,
        "candidates_by_side": dict(Counter(c["side"] for c in candidates)),
        "lanes": out_lanes,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON} ({time.time()-t0:.1f}s total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
