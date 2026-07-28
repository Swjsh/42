"""levels_v2_retro_ab.py -- DO CORRECT LEVELS CHANGE THE ANSWER? (pre-registered A/B,
2026-07-27 overnight lane).

One treatment vs one control across the full 390-day window (2025-01-02..2026-07-27):

  CONTROL    the binary engine full-history replay, byte-identical machinery to
             ladder_fullhist_replay.py's BASELINE lane: run_backtest(**SAFE_BASE_LIVE)
             entries, dollar_pnl discarded, exits re-derived via the REAL
             exit_manager_walk.walk_exit_manager under strategies.py#RIBBON_RIDE.exit.
             CALIBRATION GATE: must reproduce the pinned LADDER-FULLHIST-2026-07-27
             baseline (n=191, +$5306.95, WR 0.2984) or the full-window run ABORTS.

  TREATMENT  identical, except lib.orchestrator._detect_from_history is wrapped
             (monkeypatched for the duration of ONE run_backtest call, restored in
             finally -- the exact pattern ladder_fullhist_replay.py established for its
             bull-passed capture) to augment each session D's per-day level set with
             shelf-zone points computed AS-OF-DATE:
               - shelf zones from setup/scripts/daily_context.py's
                 _find_shelf_candidates + _merge_shelf_candidates (imported read-only,
                 module defaults: band $1.60, >=3 touches, >=10-session span),
               - run on daily OHLC aggregated from the cached 5m RTH bars,
                 dates in [D - 60 calendar days, D) -- STRICTLY before D (C6),
               - each zone [lo,hi] -> points {lo, mid, hi} (rounded to cents),
               - STRICTLY ADDITIVE: a point within $0.05 of an existing base level is
                 dropped; base levels never move; added points go to BOTH active and
                 multi_day (>=10-session structure = multi-day by construction, which
                 makes them confluence-eligible).

Pre-registration (hypothesis + pass bar, written BEFORE this tool first ran):
analysis/deep-research/LEVELS-V2-RETRO-2026-07-28.md (frozen block above the
RESULTS-BELOW marker). This tool preserves that block verbatim and appends results
below the marker.

Real OPRA fills only in P&L (C1); no-OPRA entries excluded and counted per lane.
No knob grid, no BH -- single pre-registered A/B.

Run: backtest/.venv/Scripts/python.exe backtest/tools/levels_v2_retro_ab.py
     [--start YYYY-MM-DD --end YYYY-MM-DD --smoke]   (smoke: short window, outputs to
     scratch names, calibration gate reported but not enforced)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "setup" / "scripts"),
           str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import daily_context as dcx                                  # noqa: E402  -- read-only import
import elite_bear_level_reject_gate_ab as eb                   # noqa: E402
import strategies as fleet_strategies                            # noqa: E402
import engine_fullhist_replay as efr                               # noqa: E402
import ladder_fullhist_replay as lfr                                 # noqa: E402  -- data loader reuse
import lib.orchestrator as orch_mod                                    # noqa: E402
from lib.orchestrator import run_backtest                                # noqa: E402
from lib.levels import LevelSet                                            # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                          # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol          # noqa: E402

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 27)
HELD_OUT_CUTOFF = dt.date(2026, 3, 6)   # same cutoff LADDER-FULLHIST-2026-07-27 used
SHELF_LOOKBACK_CAL_DAYS = 60             # mirrors daily_context.LOOKBACK_DAYS
ADD_TOLERANCE = 0.05                     # lib.levels._dedupe tolerance -- strictly-additive gate

# Pinned control calibration (analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json,
# baseline_binary_engine.stats) -- the harness is broken if it cannot reproduce this.
PINNED_CONTROL = {"n_trades": 191, "total_pnl": 5306.95, "win_rate": 0.2984}

OUT_DIR = ROOT / "analysis" / "deep-research"
OUT_MD = OUT_DIR / "LEVELS-V2-RETRO-2026-07-28.md"
OUT_JSON = OUT_DIR / "LEVELS-V2-RETRO-2026-07-28.json"
RESULTS_MARKER = "<!-- RESULTS-BELOW -->"


def log(msg: str) -> None:
    print(f"[levels-v2-retro] {msg}", flush=True)


# ====================================================================== shelf computation

def build_daily_bars(spy_rth: pd.DataFrame) -> list[dict]:
    """Aggregate the RTH-only 5m frame to per-session daily OHLCV dicts in
    daily_context's bar schema ({date,o,h,l,c,v}), chronological. Disclosed difference
    from live: live daily_context uses Alpaca 1Day SIP bars; this retro derives dailies
    from the same cached 5m RTH bars the replay itself trades on."""
    out: list[dict] = []
    for d, day in spy_rth.groupby(spy_rth["timestamp_et"].dt.date, sort=True):
        out.append({
            "date": d.isoformat(),
            "o": float(day["open"].iloc[0]), "h": float(day["high"].max()),
            "l": float(day["low"].min()), "c": float(day["close"].iloc[-1]),
            "v": float(day["volume"].sum()) if "volume" in day.columns else 0.0,
        })
    return out


def shelf_zones_asof(daily_bars: list[dict], session: dt.date,
                     lookback_cal_days: int = SHELF_LOOKBACK_CAL_DAYS) -> list[dict]:
    """Merged shelf zones for `session`, computed from daily bars with
    date in [session - lookback, session) -- STRICTLY before session (C6: no bar of the
    session itself contributes). Uses daily_context's own detection functions with its
    own module defaults; nothing re-tuned here."""
    lo_date = (session - dt.timedelta(days=lookback_cal_days)).isoformat()
    hi_date = session.isoformat()
    window = [b for b in daily_bars if lo_date <= b["date"] < hi_date]
    if len(window) < dcx.SHELF_MIN_TOUCHES:
        return []
    cands = dcx._find_shelf_candidates(window)
    return dcx._merge_shelf_candidates(cands)


def zone_points(zones: list[dict]) -> list[float]:
    """[lo, mid, hi] per zone, rounded to cents -- the pre-registered ONE mapping."""
    pts: list[float] = []
    for z in zones:
        lo, hi = float(z["band_low"]), float(z["band_high"])
        pts.extend([round(lo, 2), round((lo + hi) / 2.0, 2), round(hi, 2)])
    return pts


def augment_level_set(base: LevelSet, pts: list[float],
                      tolerance: float = ADD_TOLERANCE) -> tuple[LevelSet, list[float]]:
    """STRICTLY ADDITIVE merge: candidate points within `tolerance` of an existing base
    ACTIVE level are dropped (base levels never move/disappear); survivors are added to
    both active and multi_day, sorted. Returns (new_level_set, added_points)."""
    added: list[float] = []
    for p in sorted(set(pts)):
        if any(abs(p - b) <= tolerance for b in base.active):
            continue
        if any(abs(p - a) <= tolerance for a in added):
            continue
        added.append(p)
    if not added:
        return base, []
    new_active = sorted(base.active + added)
    new_multi = sorted(base.multi_day + added)
    return LevelSet(active=new_active, multi_day=new_multi,
                    swept_levels=list(base.swept_levels)), added


def run_backtest_with_shelf_levels(spy_df_raw, vix_df, start_date, end_date,
                                   daily_bars: list[dict], added_log: dict, **kwargs):
    """run_backtest with orch_mod._detect_from_history wrapped to append as-of-date shelf
    points. Pure additive wrapper; original restored in finally (ladder_fullhist_replay's
    established monkeypatch pattern). added_log[date] records what changed per session."""
    orig = orch_mod._detect_from_history

    def _patched(history, today, **kw):
        base = orig(history, today, **kw)
        zones = shelf_zones_asof(daily_bars, today)
        aug, added = augment_level_set(base, zone_points(zones))
        added_log[today.isoformat()] = {
            "n_zones": len(zones),
            "zones": [[z["band_low"], z["band_high"], z["touches"]] for z in zones],
            "n_base_active": len(base.active),
            "added_points": added,
        }
        return aug

    orch_mod._detect_from_history = _patched
    try:
        return run_backtest(spy_df_raw, vix_df, start_date=start_date, end_date=end_date, **kwargs)
    finally:
        orch_mod._detect_from_history = orig


# ====================================================================== exit re-derivation

def rederive_exits(r, spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame,
                   exit_shape: dict) -> tuple[list[dict], dict]:
    """Byte-identical to ladder_fullhist_replay.run_baseline (same walk, same conventions)
    -- re-derives every run_backtest entry's exit via the REAL exit core."""
    rows: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(t.rejection_level) if t.rejection_level else None),
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": list(t.triggers_fired or []),
            "rejection_level": t.rejection_level, "dollar_pnl": res.dollar_pnl,
            "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
            "resolved": res.resolved,
        })
    return rows, {"n_excluded_no_opra": n_no_opra, "n_excluded_no_spy_day": n_no_spy_day}


# ====================================================================== stats

def lane_stats(trades: list[dict], all_dates: list[dt.date],
               held_out_cutoff: dt.date) -> dict:
    if not trades:
        return {"n_trades": 0, "total_pnl": 0.0, "win_rate": None, "avg_pnl_per_trade": None,
                "max_drawdown": 0.0, "n_entry_days": 0,
                "day_majority": {"win_days": 0, "total_trading_days": 0, "is_majority": None},
                "survives_dropping_best_trade": {"best_trade_pnl": None,
                                                  "total_minus_best": 0.0, "still_positive": None},
                "held_out_last_25pct": {"cutoff_date": held_out_cutoff.isoformat(),
                                         "n_trades": 0, "total_pnl": 0.0, "win_rate": None}}
    df = pd.DataFrame(trades)
    df["dollar_pnl"] = df["dollar_pnl"].astype(float)
    total = round(float(df["dollar_pnl"].sum()), 2)
    n = len(df)
    per_day = df.groupby("date")["dollar_pnl"].sum()
    day_series = pd.Series({str(d): float(per_day.get(str(d), 0.0)) for d in all_dates})
    cum = day_series.cumsum()
    dd = cum - cum.cummax()
    best_pnl = float(df["dollar_pnl"].max())
    held = df[df["date"] >= held_out_cutoff.isoformat()]
    return {
        "n_trades": n, "total_pnl": total,
        "win_rate": round(float((df["dollar_pnl"] > 0).mean()), 4),
        "avg_pnl_per_trade": round(total / n, 2),
        "max_drawdown": round(float(dd.min()), 2),
        "n_entry_days": int(per_day.size),
        "day_majority": {
            "win_days": int((per_day > 0).sum()), "total_trading_days": len(per_day),
            "is_majority": bool((per_day > 0).sum() > len(per_day) / 2.0),
        },
        "survives_dropping_best_trade": {
            "best_trade_pnl": round(best_pnl, 2),
            "total_minus_best": round(total - best_pnl, 2),
            "still_positive": (total - best_pnl) > 0,
        },
        "held_out_last_25pct": {
            "cutoff_date": held_out_cutoff.isoformat(), "n_trades": len(held),
            "total_pnl": round(float(held["dollar_pnl"].sum()), 2) if len(held) else 0.0,
            "win_rate": (round(float((held["dollar_pnl"] > 0).mean()), 4) if len(held) else None),
        },
    }


def trade_key(t: dict) -> tuple:
    return (t["date"], t["entry_time_et"], t["side"], t["symbol"])


def cross_lane_analysis(control: list[dict], treatment: list[dict],
                        added_log: dict) -> dict:
    """Day-set diff, paired daily deltas, trade identity split, shelf attribution."""
    c_by_key = {trade_key(t): t for t in control}
    t_by_key = {trade_key(t): t for t in treatment}
    identical = [k for k in t_by_key if k in c_by_key]
    new_trades = [t_by_key[k] for k in t_by_key if k not in c_by_key]
    lost_trades = [c_by_key[k] for k in c_by_key if k not in t_by_key]

    c_days = {t["date"] for t in control}
    t_days = {t["date"] for t in treatment}
    c_day_pnl: dict[str, float] = {}
    for t in control:
        c_day_pnl[t["date"]] = c_day_pnl.get(t["date"], 0.0) + float(t["dollar_pnl"])
    t_day_pnl: dict[str, float] = {}
    for t in treatment:
        t_day_pnl[t["date"]] = t_day_pnl.get(t["date"], 0.0) + float(t["dollar_pnl"])

    union_days = sorted(c_days | t_days)
    deltas = []
    for d in union_days:
        dc = c_day_pnl.get(d, 0.0)
        dtv = t_day_pnl.get(d, 0.0)
        if abs(dtv - dc) > 0.005:
            deltas.append({"date": d, "control": round(dc, 2), "treatment": round(dtv, 2),
                           "delta": round(dtv - dc, 2)})
    n_pos = sum(1 for x in deltas if x["delta"] > 0)

    # Shelf attribution: treatment entries whose rejection_level lands on an added point.
    def attributed(t: dict) -> bool:
        lvl = t.get("rejection_level")
        if not isinstance(lvl, (int, float)):
            return False
        pts = (added_log.get(t["date"]) or {}).get("added_points") or []
        return any(abs(float(lvl) - p) <= 0.005 for p in pts)

    shelf_attr = [t for t in treatment if attributed(t)]
    days_gained = sorted(t_days - c_days)
    days_lost = sorted(c_days - t_days)
    return {
        "n_identical_trades": len(identical),
        "n_new_trades": len(new_trades),
        "n_lost_trades": len(lost_trades),
        "new_trades": new_trades,
        "lost_trades": lost_trades,
        "day_sets": {
            "n_control_entry_days": len(c_days), "n_treatment_entry_days": len(t_days),
            "n_shared": len(c_days & t_days),
            "days_gained_by_treatment": days_gained,
            "days_gained_pnl": round(sum(t_day_pnl[d] for d in days_gained), 2),
            "days_lost_by_treatment": days_lost,
            "days_lost_control_pnl": round(sum(c_day_pnl[d] for d in days_lost), 2),
        },
        "daily_deltas_nonzero": deltas,
        "n_days_delta_nonzero": len(deltas),
        "n_days_delta_positive": n_pos,
        "delta_day_majority_favors_treatment": (n_pos > len(deltas) / 2.0) if deltas else None,
        "shelf_attributed_treatment_trades": {
            "n": len(shelf_attr),
            "total_pnl": round(sum(float(t["dollar_pnl"]) for t in shelf_attr), 2),
            "trades": shelf_attr,
        },
    }


def verdict(control_stats: dict, treatment_stats: dict, cross: dict) -> dict:
    """The four pre-registered pass-bar gates + NULL/HARMFUL classification."""
    improvement = round(treatment_stats["total_pnl"] - control_stats["total_pnl"], 2)
    new_pnls = [float(t["dollar_pnl"]) for t in cross["new_trades"]]
    best_new = max(new_pnls) if new_pnls else 0.0
    gate1 = treatment_stats["total_pnl"] > control_stats["total_pnl"]
    gate2 = bool(cross["delta_day_majority_favors_treatment"]) if cross["n_days_delta_nonzero"] else False
    gate3 = (improvement - best_new) > 0
    gate4 = (treatment_stats["held_out_last_25pct"]["total_pnl"]
             >= control_stats["held_out_last_25pct"]["total_pnl"])
    n_changed = cross["n_new_trades"] + cross["n_lost_trades"]
    if n_changed < 5:
        klass = "NULL"
    elif improvement < 0:
        klass = "HARMFUL"
    elif gate1 and gate2 and gate3 and gate4:
        klass = "SHIP_SIGNAL"
    else:
        klass = "NO_SHIP"
    return {
        "improvement_total_pnl": improvement,
        "gate1_treatment_beats_control": gate1,
        "gate2_delta_day_majority": gate2,
        "gate3_survives_drop_best_new_trade": {"best_new_trade_pnl": round(best_new, 2),
                                                "improvement_minus_best_new": round(improvement - best_new, 2),
                                                "passes": gate3},
        "gate4_held_out_not_worse": gate4,
        "n_trades_changed": n_changed,
        "classification": klass,
    }


# ====================================================================== outputs

def _fmt(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def write_outputs(out: dict, md_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {json_path}")

    # Preserve the frozen pre-registration block verbatim; replace below the marker.
    prereg = ""
    if md_path.exists():
        txt = md_path.read_text(encoding="utf-8")
        if RESULTS_MARKER in txt:
            prereg = txt.split(RESULTS_MARKER)[0]
    cs, ts = out["control"]["stats"], out["treatment"]["stats"]
    x, v = out["cross_lane"], out["verdict"]
    cal = out["control_calibration"]
    shelf = out["shelf_coverage"]
    L = [prereg + RESULTS_MARKER, ""]
    L.append(f"## RESULTS — generated {out['generated_at']} (runner `backtest/tools/levels_v2_retro_ab.py`, "
             f"runtime {out['runtime_seconds']['total']}s)")
    L.append("")
    L.append(f"### Verdict: **{v['classification']}** (improvement {_fmt(v['improvement_total_pnl'])})")
    L.append("")
    L.append("| Lane | N trades | Total P&L | WR | Avg/trade | Max DD | Entry-days | Day-majority | Drop-best | Held-out (last 25%) | No-OPRA excluded |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, s, dq in (("CONTROL (baseline levels)", cs, out["control"]["data_quality"]),
                        ("TREATMENT (shelf-augmented)", ts, out["treatment"]["data_quality"])):
        L.append(f"| **{name}** | {s['n_trades']} | {_fmt(s['total_pnl'])} | {s['win_rate']} | "
                 f"{_fmt(s['avg_pnl_per_trade'])} | {_fmt(s['max_drawdown'])} | {s['n_entry_days']} | "
                 f"{s['day_majority']['win_days']}/{s['day_majority']['total_trading_days']} "
                 f"({s['day_majority']['is_majority']}) | "
                 f"{_fmt(s['survives_dropping_best_trade']['total_minus_best'])} "
                 f"({s['survives_dropping_best_trade']['still_positive']}) | "
                 f"{s['held_out_last_25pct']['n_trades']}tr {_fmt(s['held_out_last_25pct']['total_pnl'])} | "
                 f"{dq['n_excluded_no_opra']} |")
    L.append("")
    L.append("### Control calibration vs pinned LADDER-FULLHIST-2026-07-27 baseline")
    L.append("")
    L.append(f"- Reproduced: n={cal['reproduced']['n_trades']} total={_fmt(cal['reproduced']['total_pnl'])} "
             f"WR={cal['reproduced']['win_rate']} | Pinned: n={cal['pinned']['n_trades']} "
             f"total={_fmt(cal['pinned']['total_pnl'])} WR={cal['pinned']['win_rate']} | "
             f"**match={cal['match']}**")
    L.append("")
    L.append("### Pre-registered pass-bar gates")
    L.append("")
    L.append(f"1. Treatment beats control on total P&L: **{v['gate1_treatment_beats_control']}**")
    L.append(f"2. Majority of changed days favor treatment: **{v['gate2_delta_day_majority']}** "
             f"({x['n_days_delta_positive']}/{x['n_days_delta_nonzero']} changed days positive)")
    L.append(f"3. Survives dropping best NEW trade ({_fmt(v['gate3_survives_drop_best_new_trade']['best_new_trade_pnl'])}): "
             f"**{v['gate3_survives_drop_best_new_trade']['passes']}** "
             f"(improvement minus best-new = {_fmt(v['gate3_survives_drop_best_new_trade']['improvement_minus_best_new'])})")
    L.append(f"4. Held-out not worse: **{v['gate4_held_out_not_worse']}** "
             f"(treatment {_fmt(ts['held_out_last_25pct']['total_pnl'])} vs control "
             f"{_fmt(cs['held_out_last_25pct']['total_pnl'])})")
    L.append("")
    L.append("### What actually changed")
    L.append("")
    ds = x["day_sets"]
    L.append(f"- Trades identical across lanes: {x['n_identical_trades']} | new in treatment: "
             f"{x['n_new_trades']} | lost from control: {x['n_lost_trades']}")
    L.append(f"- Entry-days: control {ds['n_control_entry_days']} vs treatment {ds['n_treatment_entry_days']} "
             f"(shared {ds['n_shared']}; gained {len(ds['days_gained_by_treatment'])} days worth "
             f"{_fmt(ds['days_gained_pnl'])}; lost {len(ds['days_lost_by_treatment'])} days that had "
             f"{_fmt(ds['days_lost_control_pnl'])} in control)")
    sa = x["shelf_attributed_treatment_trades"]
    L.append(f"- Treatment entries whose rejection_level IS an added shelf point: {sa['n']} "
             f"({_fmt(sa['total_pnl'])})")
    L.append(f"- Shelf coverage: {shelf['n_days_with_zones']}/{shelf['n_days_total']} sessions had >=1 "
             f"as-of-date shelf zone (mean {shelf['mean_zones_per_day']} zones, mean "
             f"{shelf['mean_added_points_per_day']} added points/day; {shelf['n_days_zero_added']} "
             f"days had zones but zero NEW points after the $0.05 additive gate)")
    L.append("")
    L.append("_Full per-trade / per-day detail: `analysis/deep-research/LEVELS-V2-RETRO-2026-07-28.json`._")
    L.append("")
    md_path.write_text("\n".join(L), encoding="utf-8")
    log(f"wrote {md_path}")


# ====================================================================== main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=dt.date.fromisoformat, default=FULL_START)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=FULL_END)
    ap.add_argument("--smoke", action="store_true",
                    help="short-window plumbing check: scratch outputs, calibration reported not enforced")
    args = ap.parse_args()
    full_window = (args.start == FULL_START and args.end == FULL_END and not args.smoke)

    t_start = time.time()
    log(f"window {args.start}..{args.end} (full_window={full_window})")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    log(f"spy raw={len(spy_df_raw)} rth={len(spy_rth)} rows")

    daily_bars = build_daily_bars(spy_rth)
    log(f"daily bars aggregated: {len(daily_bars)} sessions "
        f"({daily_bars[0]['date']}..{daily_bars[-1]['date']})")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    all_dates = [d for d in sorted(spy_rth["timestamp_et"].dt.date.unique())
                 if args.start <= d <= args.end]

    # ---------------- CONTROL ----------------
    log("CONTROL: run_backtest(**SAFE_BASE_LIVE), baseline levels")
    t0 = time.time()
    r_control = run_backtest(spy_df_raw, vix_df, start_date=args.start, end_date=args.end,
                             **efr.SAFE_BASE_LIVE)
    log(f"  entry layer {time.time()-t0:.1f}s -- {len(r_control.trades)} raw entries")
    control_rows, control_dq = rederive_exits(r_control, spy_rth, ribbon_lookup, exit_shape)
    control_stats = lane_stats(control_rows, all_dates, HELD_OUT_CUTOFF)
    log(f"  control: n={control_stats['n_trades']} total={control_stats['total_pnl']:+.2f} "
        f"WR={control_stats['win_rate']}")

    calibration = {
        "pinned": PINNED_CONTROL,
        "reproduced": {"n_trades": control_stats["n_trades"],
                        "total_pnl": control_stats["total_pnl"],
                        "win_rate": control_stats["win_rate"]},
        "match": (control_stats["n_trades"] == PINNED_CONTROL["n_trades"]
                   and abs(control_stats["total_pnl"] - PINNED_CONTROL["total_pnl"]) < 0.01
                   and abs((control_stats["win_rate"] or 0) - PINNED_CONTROL["win_rate"]) < 0.001),
        "enforced": full_window,
    }
    if full_window and not calibration["match"]:
        log("FATAL: control does not reproduce the pinned LADDER-FULLHIST baseline -- "
            "harness broken, ABORTING before any treatment number is reported")
        log(f"  pinned={PINNED_CONTROL} reproduced={calibration['reproduced']}")
        return 1
    log(f"  calibration match={calibration['match']} (enforced={full_window})")

    # ---------------- TREATMENT ----------------
    log("TREATMENT: run_backtest with as-of-date shelf-augmented levels")
    added_log: dict = {}
    t1 = time.time()
    r_treat = run_backtest_with_shelf_levels(
        spy_df_raw, vix_df, args.start, args.end, daily_bars, added_log, **efr.SAFE_BASE_LIVE)
    log(f"  entry layer {time.time()-t1:.1f}s -- {len(r_treat.trades)} raw entries")
    treat_rows, treat_dq = rederive_exits(r_treat, spy_rth, ribbon_lookup, exit_shape)
    treat_stats = lane_stats(treat_rows, all_dates, HELD_OUT_CUTOFF)
    log(f"  treatment: n={treat_stats['n_trades']} total={treat_stats['total_pnl']:+.2f} "
        f"WR={treat_stats['win_rate']}")

    # in-window added-level coverage
    in_window = {d: v for d, v in added_log.items()
                 if args.start.isoformat() <= d <= args.end.isoformat()}
    n_days = len(in_window)
    n_with_zones = sum(1 for v in in_window.values() if v["n_zones"] > 0)
    n_zero_added = sum(1 for v in in_window.values() if v["n_zones"] > 0 and not v["added_points"])
    shelf_coverage = {
        "n_days_total": n_days, "n_days_with_zones": n_with_zones,
        "n_days_zero_added": n_zero_added,
        "mean_zones_per_day": round(sum(v["n_zones"] for v in in_window.values()) / n_days, 2) if n_days else 0,
        "mean_added_points_per_day": round(
            sum(len(v["added_points"]) for v in in_window.values()) / n_days, 2) if n_days else 0,
    }
    log(f"  shelf coverage: {n_with_zones}/{n_days} days with zones, "
        f"mean added pts/day={shelf_coverage['mean_added_points_per_day']}")

    cross = cross_lane_analysis(control_rows, treat_rows, added_log)
    v = verdict(control_stats, treat_stats, cross)
    log(f"VERDICT: {v['classification']} improvement={v['improvement_total_pnl']:+.2f} "
        f"changed_trades={v['n_trades_changed']} gates="
        f"[{v['gate1_treatment_beats_control']},{v['gate2_delta_day_majority']},"
        f"{v['gate3_survives_drop_best_new_trade']['passes']},{v['gate4_held_out_not_worse']}]")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": args.start.isoformat(), "end": args.end.isoformat(),
                    "n_rth_days": len(all_dates), "full_window": full_window},
        "prereg_file": "analysis/deep-research/LEVELS-V2-RETRO-2026-07-28.md (frozen block)",
        "control_calibration": calibration,
        "control": {"stats": control_stats, "data_quality": control_dq, "trades": control_rows},
        "treatment": {"stats": treat_stats, "data_quality": treat_dq, "trades": treat_rows},
        "shelf_coverage": shelf_coverage,
        "added_levels_by_day": in_window,
        "cross_lane": cross,
        "verdict": v,
        "runtime_seconds": {"total": round(time.time() - t_start, 1)},
    }
    if full_window:
        write_outputs(out, OUT_MD, OUT_JSON)
    else:
        smoke_json = OUT_DIR / "LEVELS-V2-RETRO-2026-07-28.smoke.json"
        smoke_json.parent.mkdir(parents=True, exist_ok=True)
        smoke_json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        log(f"SMOKE outputs -> {smoke_json} (real MD/JSON untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
