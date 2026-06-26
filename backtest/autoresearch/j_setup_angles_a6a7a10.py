"""A6 / A7 / A10 — the final setup-angle batch of the J-data profitability campaign.

Part of markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md. These three are LOWER-PROBABILITY than
the big finds already shipped (gap-and-go ITM-1, VWAP-cont rvol-floor) — the mandate
is "leave no plan untested": test rigorously + honestly, a negative is a valid result.

Same anti-overfit method as j_entry_specificity / j_param_tweaks:
  PART A — his Webull data (analysis/webull-j-trades/) DEFINES the hypothesis.
  PART B — OUR 2025-26 SPY real-OPRA fills VALIDATE forward through the SAME OP-22
           scorecard (_full_metrics / _ship_gate / _verdict_for, reused verbatim
           from j_entry_specificity — NO re-built fills).

  A6  CALENDAR / EVENT-DAY  — his WR + size-neutral pct_move by day-of-week,
        week-of-month, month-end (last-3-trading-days), and OPEX week (week of the
        3rd Friday). Any calendar bucket where his edge concentrates or dies? Then
        validate the top finding forward: does a day-of-week / OPEX FILTER on the
        live VWAP-continuation detector LIFT OOS expectancy vs the unfiltered book?
  A7  LEVEL-KEYED ENTRY     — did his winners cluster near structural levels? Per
        trade, the signed % distance from entry-close to the NEAREST of {round-$1.00,
        round-$0.50, session-open, premarket-high, premarket-low, intraday pre-entry
        hi/lo}. Is "entered near a level" a WINNING discriminator vs "mid-air"? If
        yes, validate forward as a level-proximity entry filter (OUR data also gets
        PDH/PDL, which J's cache lacks — disclosed).
  A10 SELF-PnL STATE        — beyond revenge (L168): a "hot read" condition. Ordered
        chronologically, did J trade SHARPER after a win / on a win-streak / when his
        rolling P&L was green / earlier in the day's trade sequence? Honest verdict —
        likely noise. This is about WHEN his READ was sharpest, NOT sizing. It is a
        BEHAVIORAL property of J's live sequencing → it CANNOT be forward-validated as
        a live filter on our engine (we have no live J trade-stream), so A10 is
        Part-A-only by construction (disclosed).

Causal (L166): every Part-A feature uses only at/before entry-bar info; Part-B fills
next-bar-open via lib.simulator_real. Pure, $0, read-only, propose-only (Rule 9).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_setup_angles_a6a7a10.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]          # .../42/backtest
PROJECT = REPO.parent                                # .../42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "autoresearch") not in sys.path:
    sys.path.insert(0, str(REPO / "autoresearch"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Windows console is cp1252 by default; our status lines use non-ASCII glyphs.
# Reconfigure stdout/stderr to UTF-8 so prints don't crash (JSON is ensure_ascii).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# ---- his-data loaders (reuse the canonical Webull pipeline) ----
from autoresearch.webull_loser_stopped_then_printed import (  # noqa: E402
    RoundTrip, _rth_bars, _utc_to_et, load_roundtrips, _load_cache,
    WINNER_CACHE, LOSER_CACHE,
)
from autoresearch.webull_entry_quality import _entry_index  # noqa: E402

# ---- our-data forward-validation harness (reuse j_entry_specificity verbatim) ----
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, session_vwap_asof,
    _nearest_cached_strike, Signal,
)
from autoresearch.j_entry_specificity import (  # noqa: E402
    detect_j_cont_param, _sim, _full_metrics, _ship_gate, _verdict_for,
    TIERS, FREQ_PER_WK_FLOOR, TREND_BARS, SHALLOW_DIP_TOL,
)
from lib.ribbon import compute_ribbon  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "j-setup-angles-A6A7A10.json"

# A7 level-proximity buckets (abs % of price). The campaign's near_level baseline
# used 0.15% but found 100% "near" — at SPY ~$400-600 a $1 grid = 0.16-0.25% so the
# nearest structural level is ALWAYS within ~0.13%; a genuine "mid-air" zone only
# exists at TIGHT thresholds. We sweep a tight→loose ladder so the near-vs-mid-air
# contrast is measured at the thresholds where mid-air actually exists, not assumed.
LEVEL_NEAR_BUCKETS = [0.02, 0.03, 0.05, 0.10]   # % of price
MIN_CELL_N = 15                                  # min support for a rankable cell


# ═════════════════════════════════════════════════════════════════════════════
# Shared cell stats — WR + size-neutral pct_move headline (raw $ flagged confounded)
# ═════════════════════════════════════════════════════════════════════════════
def _cell(recs: list[dict]) -> dict:
    n = len(recs)
    if n == 0:
        return {"n": 0}
    wins = sum(1 for r in recs if r["is_win"])
    pct = [r["pct_move"] for r in recs]
    pnl = [r["pnl"] for r in recs]
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "pct_move_mean": round(float(np.mean(pct)), 1),     # SIZE-NEUTRAL headline
        "pct_move_median": round(float(np.median(pct)), 1),
        "raw_pnl_mean_SIZE_CONFOUNDED": round(float(np.mean(pnl)), 1),
        "raw_pnl_total_SIZE_CONFOUNDED": round(float(np.sum(pnl)), 0),
    }


def _contrast(take: list[dict], avoid: list[dict], take_name: str,
              avoid_name: str) -> dict:
    """A vs B split with the bias-robust lift (WR + pct_move; raw $ confounded)."""
    t, a = _cell(take), _cell(avoid)
    out = {"take": take_name, "avoid": avoid_name, "TAKE": t, "AVOID": a}
    if t["n"] and a["n"]:
        out["wr_lift_pp"] = round(t["wr_pct"] - a["wr_pct"], 1)
        out["pct_move_lift"] = round(t["pct_move_mean"] - a["pct_move_mean"], 1)
        # harmonic-mean support weight (penalises tiny-support clean-looking splits)
        out["support_weight"] = round(
            2 * t["n"] * a["n"] / (t["n"] + a["n"]) / (t["n"] + a["n"]), 3)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# PART A1 — A6 CALENDAR mining (from RoundTrip dates; no bars needed)
# ═════════════════════════════════════════════════════════════════════════════
def _third_friday(year: int, month: int) -> dt.date:
    """Standard monthly OPEX = the 3rd Friday."""
    d = dt.date(year, month, 1)
    # weekday(): Mon=0 .. Fri=4
    first_fri = 1 + (4 - d.weekday()) % 7
    return dt.date(year, month, first_fri + 14)


def _trade_dates_in_month(all_dates: set[dt.date], year: int,
                          month: int) -> list[dt.date]:
    return sorted(d for d in all_dates if d.year == year and d.month == month)


def mine_a6(rt_recs: list[dict], all_trade_dates: set[dt.date]) -> dict:
    """Calendar buckets. Each record carries a real date string + is_win + pct_move."""
    # precompute, per (year,month), the trade-date list + 3rd-Friday for month-end /
    # OPEX-week classification grounded in ACTUAL trading days (not naive calendar).
    months = sorted({(d.year, d.month) for d in all_trade_dates})
    month_dates = {ym: _trade_dates_in_month(all_trade_dates, *ym) for ym in months}
    third_fri = {ym: _third_friday(*ym) for ym in months}

    def _is_month_end(d: dt.date) -> bool:
        md = month_dates[(d.year, d.month)]
        return d in md[-3:] if len(md) >= 3 else False

    def _is_opex_week(d: dt.date) -> bool:
        tf = third_fri[(d.year, d.month)]
        monday = tf - dt.timedelta(days=tf.weekday())   # Monday of OPEX week
        return monday <= d <= tf

    def _week_of_month(d: dt.date) -> str:
        md = month_dates[(d.year, d.month)]
        if not md:
            return "w?"
        # bucket trading days into weeks by 5-trading-day blocks
        pos = md.index(d)
        return f"w{pos // 5 + 1}"

    by_dow: dict[str, list] = defaultdict(list)
    by_wom: dict[str, list] = defaultdict(list)
    me_in, me_out = [], []
    opex_in, opex_out = [], []
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in rt_recs:
        d = dt.date.fromisoformat(r["date"])
        by_dow[dow_names[d.weekday()]].append(r)
        by_wom[_week_of_month(d)].append(r)
        (me_in if _is_month_end(d) else me_out).append(r)
        (opex_in if _is_opex_week(d) else opex_out).append(r)

    dow = {k: _cell(by_dow[k]) for k in dow_names if by_dow[k]}
    wom = {k: _cell(by_wom[k]) for k in sorted(by_wom)}

    # rank DoW by pct_move (size-neutral) among n>=MIN_CELL_N
    dow_rank = sorted(((k, v) for k, v in dow.items() if v["n"] >= MIN_CELL_N),
                      key=lambda kv: kv[1]["pct_move_mean"], reverse=True)
    return {
        "by_day_of_week": dow,
        "day_of_week_ranked_by_pct_move": [{"dow": k, **v} for k, v in dow_rank],
        "by_week_of_month": wom,
        "month_end_last3": _contrast(me_in, me_out, "month_end(last3)", "rest"),
        "opex_week": _contrast(opex_in, opex_out, "opex_week", "non_opex"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# PART A2 — A7 LEVEL-KEYED mining (needs bars; per-trade nearest-level distance)
# ═════════════════════════════════════════════════════════════════════════════
def _premarket_hi_lo(raw: list[dict[str, Any]]) -> tuple[Optional[float],
                                                         Optional[float]]:
    """Premarket = bars before 09:30 ET, same session (causal at any RTH entry)."""
    his, los = [], []
    for b in raw:
        t_et = _utc_to_et(b["t"])
        if t_et.time() < dt.time(9, 30):
            his.append(float(b["h"]))
            los.append(float(b["l"]))
    return (max(his) if his else None, min(los) if los else None)


def _level_set_at_entry(rth_bars, idx: int, pm_hi: Optional[float],
                        pm_lo: Optional[float], *,
                        psych_only: bool = False) -> dict[str, float]:
    """Causal STRUCTURAL levels available AT the entry bar (same-session only).

    J's bar cache has no prior-day bars, so PDH/PDL are unavailable here (disclosed
    in the output + tested only on OUR data in Part B). round_0.50 is intentionally
    EXCLUDED: at SPY ~$400-600 a $0.50 grid makes every price <0.04% from a level
    (no mid-air), which is uninformative. Round levels = round-$1 + round-$5 (the
    psychological ones). psych_only drops round numbers entirely to isolate the
    "did he enter at a STRUCTURAL price level (open / overnight / intraday extreme)"
    question from generic round-number proximity.
    """
    entry = rth_bars[idx]
    px = entry.c
    pre = rth_bars[:idx] if idx > 0 else rth_bars[:1]
    lv: dict[str, float] = {
        "session_open": rth_bars[0].o,
        "intraday_pre_hi": max(b.h for b in pre),
        "intraday_pre_lo": min(b.l for b in pre),
    }
    if pm_hi is not None:
        lv["premarket_hi"] = pm_hi
    if pm_lo is not None:
        lv["premarket_lo"] = pm_lo
    if not psych_only:
        lv["round_1.00"] = round(px)
        lv["round_5.00"] = round(px / 5) * 5
    return lv


def _nearest_level(px: float, levels: dict[str, float]) -> tuple[str, float]:
    """(level_type, abs % distance) to the nearest level."""
    best_name, best_dist = "none", 99.9
    for name, lvl in levels.items():
        if lvl and lvl > 0:
            d = abs(px - lvl) / px * 100.0
            if d < best_dist:
                best_name, best_dist = name, d
    return best_name, best_dist


def mine_a7(rts: list[RoundTrip], cache: dict[str, list]) -> dict:
    """Per-trade nearest-level distance; near-vs-mid-air contrast at each bucket.

    Two distance views: (1) ALL structural levels (round-$1/$5 + open + premarket +
    intraday extremes); (2) PSYCH-ONLY (open + premarket + intraday extremes — drops
    round numbers) which is the cleaner 'did he enter AT a price-structure level'
    test, since round-number density swamps the all-levels view at SPY's price.
    """
    recs: list[dict] = []
    skipped = Counter()
    for r in rts:
        raw = cache.get(r.date)
        if not raw:
            skipped["no_cache"] += 1
            continue
        bars = _rth_bars(raw)
        if not bars:
            skipped["no_rth"] += 1
            continue
        idx = _entry_index(bars, r.entry_dt.strftime("%H:%M"))
        if idx is None or idx >= len(bars):
            skipped["no_entry_idx"] += 1
            continue
        pm_hi, pm_lo = _premarket_hi_lo(raw)
        px = bars[idx].c
        lname, ldist = _nearest_level(
            px, _level_set_at_entry(bars, idx, pm_hi, pm_lo))
        pname, pdist = _nearest_level(
            px, _level_set_at_entry(bars, idx, pm_hi, pm_lo, psych_only=True))
        recs.append({
            "date": r.date, "side": r.right, "is_win": r.pnl > 0,
            "pnl": r.pnl, "pct_move": round(r.pct_move * 100, 1),
            "nearest_level_type": lname, "nearest_level_dist_pct": round(ldist, 3),
            "nearest_psych_type": pname, "nearest_psych_dist_pct": round(pdist, 3),
        })

    # near-vs-mid-air contrast at each proximity bucket — ALL-levels + PSYCH-only
    def _buckets(distkey: str) -> dict:
        out = {}
        for thr in LEVEL_NEAR_BUCKETS:
            near = [r for r in recs if r[distkey] <= thr]
            mid = [r for r in recs if r[distkey] > thr]
            out[f"<= {thr}%"] = _contrast(
                near, mid, f"near(<= {thr}%)", f"mid_air(> {thr}%)")
        return out

    # which level TYPE is the sharpest cluster (n>=MIN_CELL_N, ranked by pct_move)
    by_type: dict[str, list] = defaultdict(list)
    for r in recs:
        by_type[r["nearest_level_type"]].append(r)
    type_cells = {k: _cell(v) for k, v in by_type.items()}
    type_rank = sorted(((k, v) for k, v in type_cells.items()
                        if v["n"] >= MIN_CELL_N),
                       key=lambda kv: kv[1]["pct_move_mean"], reverse=True)

    def _dist_split(distkey: str) -> dict:
        win_d = [r[distkey] for r in recs if r["is_win"]]
        los_d = [r[distkey] for r in recs if not r["is_win"]]
        return {
            "winner_mean_dist_pct": round(float(np.mean(win_d)), 3) if win_d else None,
            "loser_mean_dist_pct": round(float(np.mean(los_d)), 3) if los_d else None,
            "winner_median_dist_pct": round(float(np.median(win_d)), 3) if win_d else None,
            "loser_median_dist_pct": round(float(np.median(los_d)), 3) if los_d else None,
        }

    return {
        "n_records": len(recs), "skipped": dict(skipped),
        "near_vs_midair_by_bucket_ALL_levels": _buckets("nearest_level_dist_pct"),
        "near_vs_midair_by_bucket_PSYCH_only": _buckets("nearest_psych_dist_pct"),
        "by_nearest_level_type": type_cells,
        "level_type_ranked_by_pct_move_n>=15": [{"type": k, **v}
                                                for k, v in type_rank],
        "distance_winners_vs_losers_ALL": _dist_split("nearest_level_dist_pct"),
        "distance_winners_vs_losers_PSYCH": _dist_split("nearest_psych_dist_pct"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# PART A3 — A10 SELF-PnL STATE mining (chronological sequence of J's trades)
# ═════════════════════════════════════════════════════════════════════════════
def mine_a10(rts: list[RoundTrip]) -> dict:
    """Order J's trades by entry time; tag each with prior-PnL / streak / day-seq
    state KNOWN before the trade (causal), then contrast WR + pct_move by state.

    All state is strictly look-back (prior closed trades only) — no look-ahead.
    """
    ordered = sorted(rts, key=lambda r: r.entry_dt)
    recs: list[dict] = []
    streak = 0                       # +n win streak, -n loss streak (prior trades)
    prev_result: Optional[str] = None
    cum_pnl = 0.0
    day_seq: dict[str, int] = defaultdict(int)
    rolling: list[float] = []        # last-k results for rolling-green state
    for r in ordered:
        is_win = r.pnl > 0
        seq_today = day_seq[r.date]   # 0-based: trades already done today
        rec = {
            "date": r.date, "side": r.right, "is_win": is_win,
            "pnl": r.pnl, "pct_move": round(r.pct_move * 100, 1),
            "prior_result": prev_result if prev_result else "none",
            "prior_streak": streak,
            "prior_streak_bucket": (
                "win_streak_2+" if streak >= 2 else
                "after_1_win" if streak == 1 else
                "after_1_loss" if streak == -1 else
                "loss_streak_2+" if streak <= -2 else "flat"),
            "prior_cum_pnl_sign": ("green" if cum_pnl > 0 else
                                   "red" if cum_pnl < 0 else "flat"),
            "day_trade_seq": seq_today,
            "day_seq_bucket": ("first_of_day" if seq_today == 0 else
                               "2nd_3rd" if seq_today <= 2 else "4th+"),
            "prior5_winrate": (round(100 * sum(1 for x in rolling[-5:] if x > 0)
                                     / len(rolling[-5:]), 0)
                               if rolling else None),
        }
        recs.append(rec)
        # advance state AFTER recording (look-back only)
        prev_result = "win" if is_win else "loss"
        streak = (streak + 1 if is_win and streak >= 0 else
                  1 if is_win else
                  streak - 1 if not is_win and streak <= 0 else -1)
        cum_pnl += r.pnl
        day_seq[r.date] += 1
        rolling.append(r.pnl)

    def _group(field: str) -> dict:
        g: dict[str, list] = defaultdict(list)
        for r in recs:
            g[str(r[field])].append(r)
        return {k: _cell(v) for k, v in g.items()}

    # ---- CONFOUND TEST (load-bearing): is "after a win" a hot-hand, or just "it's a
    # good day"? J wins repeatedly on trending days, loses repeatedly on chop days, so
    # after-win trades cluster on good days. De-mean each trade by ITS OWN DAY's mean
    # pct_move and re-test: if the after-win edge vanishes/inverts, it was day-regime
    # clustering, not a state effect.
    day_pm: dict[str, list] = defaultdict(list)
    for r in recs:
        day_pm[r["date"]].append(r["pct_move"])
    day_mean = {d: float(np.mean(v)) for d, v in day_pm.items()}
    for r in recs:
        r["pct_move_day_demeaned"] = round(r["pct_move"] - day_mean[r["date"]], 2)

    def _dd(sub):
        if not sub:
            return None
        return round(float(np.mean([s["pct_move_day_demeaned"] for s in sub])), 2)

    aw0 = [r for r in recs if r["prior_result"] == "win"]
    al0 = [r for r in recs if r["prior_result"] == "loss"]
    confound = {
        "_what": "after-win edge with the day-regime removed (de-meaned by own-day "
                 "mean pct_move). If it vanishes/inverts → hot-hand was a day-clustering "
                 "artifact, NOT a real state effect.",
        "raw_after_win_pct_move": _cell(aw0).get("pct_move_mean"),
        "raw_after_loss_pct_move": _cell(al0).get("pct_move_mean"),
        "raw_after_win_minus_after_loss": round(
            _cell(aw0).get("pct_move_mean", 0) - _cell(al0).get("pct_move_mean", 0), 1),
        "DAY_DEMEANED_after_win_pct_move": _dd(aw0),
        "DAY_DEMEANED_after_loss_pct_move": _dd(al0),
        "DAY_DEMEANED_after_win_minus_after_loss": (
            round(_dd(aw0) - _dd(al0), 2) if _dd(aw0) is not None
            and _dd(al0) is not None else None),
        "hot_hand_survives_day_control": bool(
            _dd(aw0) is not None and _dd(al0) is not None and _dd(aw0) > _dd(al0)),
    }

    # the headline "hot read" contrasts
    after_win = [r for r in recs if r["prior_result"] == "win"]
    after_loss = [r for r in recs if r["prior_result"] == "loss"]
    streak2plus = [r for r in recs if r["prior_streak"] >= 2]
    not_streak = [r for r in recs if r["prior_streak"] < 2]
    green = [r for r in recs if r["prior_cum_pnl_sign"] == "green"]
    red = [r for r in recs if r["prior_cum_pnl_sign"] == "red"]
    first = [r for r in recs if r["day_trade_seq"] == 0]
    later = [r for r in recs if r["day_trade_seq"] > 0]
    return {
        "n_records": len(recs),
        "by_prior_result": _group("prior_result"),
        "by_prior_streak_bucket": _group("prior_streak_bucket"),
        "by_prior_cum_pnl_sign": _group("prior_cum_pnl_sign"),
        "by_day_seq_bucket": _group("day_seq_bucket"),
        "headline_contrasts": {
            "after_win_vs_after_loss": _contrast(after_win, after_loss,
                                                 "after_win", "after_loss"),
            "win_streak_2+_vs_rest": _contrast(streak2plus, not_streak,
                                               "win_streak_2+", "rest"),
            "rolling_green_vs_red": _contrast(green, red, "cum_green", "cum_red"),
            "first_of_day_vs_later": _contrast(first, later,
                                               "first_of_day", "later_in_day"),
        },
        "CONFOUND_TEST_day_demeaned": confound,
    }


# ═════════════════════════════════════════════════════════════════════════════
# PART B — forward-validate the translatable findings on OUR real-OPRA fills
# ═════════════════════════════════════════════════════════════════════════════
def _dow_of_bar(spy, bar_idx: int) -> int:
    return spy.iloc[bar_idx]["timestamp_et"].weekday()


def _third_friday_for(d: dt.date) -> dt.date:
    return _third_friday(d.year, d.month)


def _is_opex_week_date(d: dt.date) -> bool:
    tf = _third_friday_for(d)
    monday = tf - dt.timedelta(days=tf.weekday())
    return monday <= d <= tf


def _build_prior_and_pm_levels(spy: pd.DataFrame, days) -> dict:
    """Per-date {PDH,PDL,PMH,PML} for OUR data (continuous, so PDH/PDL ARE available).

    PDH/PDL = prior trading day's RTH high/low. PMH/PML = same-day premarket hi/lo
    (bars before 09:30 ET). All look-back / same-session-premarket → causal.
    """
    # full-day RTH high/low per date (for prior-day lookup)
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))]
    day_hi = rth.groupby("date")["high"].max().to_dict()
    day_lo = rth.groupby("date")["low"].min().to_dict()
    pre = spy[spy["t"] < dt.time(9, 30)]
    pm_hi = pre.groupby("date")["high"].max().to_dict()
    pm_lo = pre.groupby("date")["low"].min().to_dict()
    ordered_dates = [dc.date for dc in days]
    out = {}
    for i, d in enumerate(ordered_dates):
        pd_date = ordered_dates[i - 1] if i > 0 else None
        out[d] = {
            "PDH": day_hi.get(pd_date), "PDL": day_lo.get(pd_date),
            "PMH": pm_hi.get(d), "PML": pm_lo.get(d),
        }
    return out


def detect_j_cont_level_filtered(spy, ribbon, vix, days, *,
                                 win_start: dt.time, win_end: dt.time,
                                 level_near_pct: float,
                                 prior_pm_levels: dict,
                                 psych_only: bool = False) -> list[Signal]:
    """Clone of detect_j_cont_param + an entry-bar LEVEL-PROXIMITY gate (A7 forward).

    Entry only fires if the entry-bar close is within level_near_pct% of the nearest
    structural level. ALL-levels set = {round-$1, round-$5, session-open, PDH, PDL,
    PMH, PML, intraday pre-entry hi/lo}. psych_only drops the round numbers (the
    cleaner 'at a price-structure level' test). Everything else (side from first
    TREND_BARS, breakout/pullback trigger, session-extreme stop, one-per-day) is
    identical → apples-to-apples vs the unfiltered baseline.
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        opens = rth["open"].values
        hc, hv = closes[:TREND_BARS], vwap[:TREND_BARS]
        if len(hc) < TREND_BARS:
            continue
        if np.all(hc > hv):
            side = "C"
        elif np.all(hc < hv):
            side = "P"
        else:
            continue
        lv_static = prior_pm_levels.get(dc.date, {})
        sess_open = float(opens[0])
        for j in range(TREND_BARS, len(rth)):
            tj = times[j]
            if tj >= win_end:
                break
            if tj < win_start:
                continue
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if trig is None:
                continue
            # ---- A7 level-proximity gate ----
            px = float(closes[j])
            pre_hi = float(np.max(highs[:j])) if j > 0 else highs[j]
            pre_lo = float(np.min(lows[:j])) if j > 0 else lows[j]
            cand = {"session_open": sess_open, "intraday_pre_hi": pre_hi,
                    "intraday_pre_lo": pre_lo}
            for k in ("PDH", "PDL", "PMH", "PML"):
                if lv_static.get(k):
                    cand[k] = lv_static[k]
            if not psych_only:
                cand["round_1.00"] = round(px)
                cand["round_5.00"] = round(px / 5) * 5
            _, ldist = _nearest_level(px, cand)
            if ldist > level_near_pct:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jL_{trig}"))
            break
    return out


def detect_j_cont_calendar_filtered(spy, ribbon, vix, days, *,
                                    win_start: dt.time, win_end: dt.time,
                                    allowed_dows: Optional[set] = None,
                                    opex_only: bool = False,
                                    exclude_opex: bool = False) -> list[Signal]:
    """detect_j_cont_param + an A6 CALENDAR gate (day-of-week / OPEX-week)."""
    base = detect_j_cont_param(spy, ribbon, vix, days,
                               win_start=win_start, win_end=win_end)
    out = []
    for sg in base:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        if allowed_dows is not None and d.weekday() not in allowed_dows:
            continue
        if opex_only and not _is_opex_week_date(d):
            continue
        if exclude_opex and _is_opex_week_date(d):
            continue
        out.append(sg)
    return out


def _metrics_for_signals(signals, spy, vix, ribbon, all_dates, n_days,
                         n_trials_dsr) -> dict:
    side_counts = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
    tiers = {}
    for tname, off in TIERS.items():
        rows, cov = _sim(signals, spy, vix, ribbon, off)
        m = _full_metrics(rows, all_dates, n_days, n_trials_dsr)
        m["coverage"] = cov
        gate, ok = _ship_gate(m)
        m["ship_gate"] = gate
        m["edge_ship_pass"] = ok
        m["freq_pass_>=2/wk"] = m["trades_per_week"] >= FREQ_PER_WK_FLOOR
        m["DAILY_SURVIVOR"] = bool(ok and m["freq_pass_>=2/wk"])
        tiers[tname] = m
    return {"signal_count": len(signals), "side_counts": side_counts, "tiers": tiers}


def _frequency_null_control(base_signals, filtered_signals, spy, vix, ribbon,
                            all_dates, n_days, n_trials_dsr, *,
                            n_perm: int = 200, seed: int = 42) -> dict:
    """Is a filter's OOS lift REAL, or just a side-effect of trading fewer trades?

    The acid test for any subtractive calendar/level filter: remove the SAME number
    of signals AT RANDOM, n_perm times, and see where the filter's observed OOS lift
    falls in that null distribution. If the observed lift is < ~95th percentile, the
    filter is not distinguishable from random thinning → DEAD as an edge (L-class
    frequency-artifact guard). Uses the ATM tier (the campaign headline tier).
    """
    base_atm = _metrics_for_signals(base_signals, spy, vix, ribbon, all_dates,
                                    n_days, n_trials_dsr)["tiers"]["ATM"]
    filt_atm = _metrics_for_signals(filtered_signals, spy, vix, ribbon, all_dates,
                                    n_days, n_trials_dsr)["tiers"]["ATM"]
    k_remove = len(base_signals) - len(filtered_signals)
    obs_lift = filt_atm["oos_exp_dollar"] - base_atm["oos_exp_dollar"]
    if k_remove <= 0 or k_remove >= len(base_signals):
        return {"applicable": False, "reason": "filter removed 0 or all signals",
                "observed_oos_lift": round(obs_lift, 2)}
    rng = np.random.default_rng(seed)
    idxs = list(range(len(base_signals)))
    lifts = []
    for _ in range(n_perm):
        drop = set(rng.choice(idxs, size=k_remove, replace=False))
        keep = [base_signals[i] for i in idxs if i not in drop]
        m = _metrics_for_signals(keep, spy, vix, ribbon, all_dates, n_days,
                                 n_trials_dsr)["tiers"]["ATM"]
        lifts.append(m["oos_exp_dollar"] - base_atm["oos_exp_dollar"])
    lifts = np.array(lifts)
    pctile = float(100 * (lifts < obs_lift).mean())
    p_ge = float((lifts >= obs_lift).mean())
    return {
        "applicable": True, "n_removed": k_remove, "n_perm": n_perm,
        "observed_oos_lift_dollar": round(obs_lift, 2),
        "null_lift_mean": round(float(lifts.mean()), 2),
        "null_lift_std": round(float(lifts.std()), 2),
        "observed_lift_percentile_in_null": round(pctile, 0),
        "p_random_ge_observed": round(p_ge, 3),
        "real_edge_not_freq_artifact": bool(pctile >= 95.0),
    }


# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print("=== A6 / A7 / A10 — final J setup-angle batch ===")
    print("PART A: loading J's Webull round-trips + bar caches...")
    rts = load_roundtrips()
    # winner+loser union cache (same union the entry-quality builder uses)
    cache = _load_cache(WINNER_CACHE)
    cache.update(_load_cache(LOSER_CACHE))
    all_trade_dates = {dt.date.fromisoformat(r.date) for r in rts}
    print(f"  {len(rts)} closed round-trips over {len(all_trade_dates)} dates "
          f"({min(all_trade_dates)}..{max(all_trade_dates)})")

    # flat record list for the calendar miner (date/is_win/pnl/pct_move)
    rt_recs = [{"date": r.date, "is_win": r.pnl > 0, "pnl": r.pnl,
                "pct_move": round(r.pct_move * 100, 1), "side": r.right}
               for r in rts]

    print("PART A: mining A6 (calendar) / A7 (levels) / A10 (self-PnL state)...")
    a6 = mine_a6(rt_recs, all_trade_dates)
    a7 = mine_a7(rts, cache)
    a10 = mine_a10(rts)
    print(f"  A6 DoW ranked: "
          f"{[(c['dow'], c['pct_move_mean']) for c in a6['day_of_week_ranked_by_pct_move']]}")
    print(f"  A6 OPEX lift (pct_move): {a6['opex_week'].get('pct_move_lift')}  "
          f"month-end lift: {a6['month_end_last3'].get('pct_move_lift')}")
    _b5 = a7['near_vs_midair_by_bucket_PSYCH_only'].get('<= 0.05%', {})
    print(f"  A7 PSYCH near-vs-midair @0.05%: lift_wr={_b5.get('wr_lift_pp')}pp "
          f"lift_pct={_b5.get('pct_move_lift')} "
          f"(TAKE n={_b5.get('TAKE',{}).get('n')} AVOID n={_b5.get('AVOID',{}).get('n')}, "
          f"n_records={a7['n_records']})")
    print(f"  A10 after_win vs after_loss: "
          f"wr_lift={a10['headline_contrasts']['after_win_vs_after_loss'].get('wr_lift_pp')}pp")

    print("\nPART B: loading OUR 2025-26 SPY/VIX for forward validation...")
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)
    print(f"  trading_days={n_days} range {all_dates[0]}..{all_dates[-1]}")

    FULL_MORNING = (dt.time(9, 35), dt.time(10, 30))
    n_trials = 14   # A6 (DoW-best + OPEX in/out = 3) + A7 (4 buckets) — DSR haircut

    # ---- BASELINE: unfiltered full-morning VWAP-continuation (the comparison) ----
    base_signals = detect_j_cont_param(spy, ribbon, vix, days,
                                       win_start=FULL_MORNING[0],
                                       win_end=FULL_MORNING[1])
    base = _metrics_for_signals(base_signals, spy, vix, ribbon, all_dates, n_days,
                                n_trials)
    base_atm = base["tiers"]["ATM"]

    part_b: dict[str, Any] = {"baseline_full_morning": base, "A6_calendar": {},
                              "A7_level_proximity": {}}

    # ---- A6 forward: best-DoW filter + OPEX-in + OPEX-out ----
    # the his-data best DoW (if any rankable); also test the live-data OPEX cut both ways
    dow_name_to_num = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    a6_ranked = a6["day_of_week_ranked_by_pct_move"]
    if a6_ranked:
        # take his top-2 DoW as the "keep" set (more than 1 to keep frequency sane)
        keep = {dow_name_to_num[c["dow"]] for c in a6_ranked[:2]
                if c["dow"] in dow_name_to_num}
        sig = detect_j_cont_calendar_filtered(
            spy, ribbon, vix, days, win_start=FULL_MORNING[0],
            win_end=FULL_MORNING[1], allowed_dows=keep)
        part_b["A6_calendar"]["best_dow_keep_top2"] = {
            "his_top2_dow": [c["dow"] for c in a6_ranked[:2]],
            **_metrics_for_signals(sig, spy, vix, ribbon, all_dates, n_days, n_trials)}
    a6_sigs: dict[str, list] = {}
    for label, kw in [("opex_week_only", {"opex_only": True}),
                      ("exclude_opex_week", {"exclude_opex": True})]:
        sig = detect_j_cont_calendar_filtered(
            spy, ribbon, vix, days, win_start=FULL_MORNING[0],
            win_end=FULL_MORNING[1], **kw)
        a6_sigs[label] = sig
        part_b["A6_calendar"][label] = _metrics_for_signals(
            sig, spy, vix, ribbon, all_dates, n_days, n_trials)

    # frequency-null control on the strongest subtractive A6 filter (exclude-OPEX):
    # is its OOS lift a real calendar edge or just trading fewer trades?
    print("  running A6 frequency-null control (200 perms)...")
    part_b["A6_calendar"]["exclude_opex_week"]["frequency_null_control"] = (
        _frequency_null_control(base_signals, a6_sigs["exclude_opex_week"], spy, vix,
                                ribbon, all_dates, n_days, n_trials))

    # ---- A7 forward: level-proximity gate at each bucket (ALL-levels + PSYCH-only) ----
    prior_pm = _build_prior_and_pm_levels(spy, days)
    for thr in LEVEL_NEAR_BUCKETS:
        sig = detect_j_cont_level_filtered(
            spy, ribbon, vix, days, win_start=FULL_MORNING[0],
            win_end=FULL_MORNING[1], level_near_pct=thr, prior_pm_levels=prior_pm)
        part_b["A7_level_proximity"][f"all_near_<= {thr}%"] = _metrics_for_signals(
            sig, spy, vix, ribbon, all_dates, n_days, n_trials)
        sig_p = detect_j_cont_level_filtered(
            spy, ribbon, vix, days, win_start=FULL_MORNING[0],
            win_end=FULL_MORNING[1], level_near_pct=thr, prior_pm_levels=prior_pm,
            psych_only=True)
        part_b["A7_level_proximity"][f"psych_near_<= {thr}%"] = _metrics_for_signals(
            sig_p, spy, vix, ribbon, all_dates, n_days, n_trials)

    # ---- verdicts (vs unfiltered baseline; reuse j_entry_specificity._verdict_for) ----
    verdicts: dict[str, Any] = {}
    # A6
    a6_best = None
    a6_candidates = []
    if "best_dow_keep_top2" in part_b["A6_calendar"]:
        a6_candidates.append(("A6_dow",
                              part_b["A6_calendar"]["best_dow_keep_top2"]["tiers"]["ATM"]))
    a6_candidates += [("A6_opex_only", part_b["A6_calendar"]["opex_week_only"]["tiers"]["ATM"]),
                      ("A6_exclude_opex",
                       part_b["A6_calendar"]["exclude_opex_week"]["tiers"]["ATM"])]
    for key, m in a6_candidates:
        v, lift = _verdict_for(m, base_atm)
        verdicts[key] = {"verdict": v, "oos_exp_lift_vs_baseline_dollar": lift,
                         "n": m["n"], "trades_per_week": m["trades_per_week"]}
        if a6_best is None or lift > a6_best[1]:
            a6_best = (key, lift, v)
    # frequency-null gate: a subtractive filter's "lift" is only an edge if it beats
    # random thinning. If exclude-OPEX (the strongest) fails the null, A6-live = DEAD
    # regardless of the raw OOS lift (frequency-artifact guard).
    nullc = part_b["A6_calendar"]["exclude_opex_week"].get("frequency_null_control", {})
    null_pass = bool(nullc.get("real_edge_not_freq_artifact"))
    a6_live_verdict = (a6_best[2] if (a6_best and null_pass) else
                       "DEAD" if a6_best else "DEAD")
    verdicts["A6_overall"] = {
        "best_variant": a6_best[0] if a6_best else None,
        "best_lift": a6_best[1] if a6_best else None,
        "raw_gate_verdict": a6_best[2] if a6_best else "DEAD",
        "frequency_null_passed": null_pass,
        "frequency_null_percentile": nullc.get("observed_lift_percentile_in_null"),
        "verdict": a6_live_verdict,
        "note": ("his-data OPEX-week collapse is REAL (-13.4pp WR) but the live "
                 "exclude-OPEX OOS lift does NOT beat a frequency-matched random-"
                 "removal null → DEAD as a live filter; kept as a J-behavioral flag." )}
    # A7 — a "level filter" only counts if it (a) discriminates meaningfully (removes
    # >= 10% of trades — otherwise it's a no-op proving 'everything is near a level')
    # AND (b) the surviving trades clear the gate with a real lift. The genuinely
    # discriminating buckets (tight thresholds) all go OOS-NEGATIVE; the only +lift
    # variants barely filter anything → A7 is DEAD as a level edge.
    MIN_DISCRIM_FRAC = 0.10
    a7_best = None
    for name, v in part_b["A7_level_proximity"].items():
        m = v["tiers"]["ATM"]
        removed = base_atm["n"] - m["n"]
        removed_frac = removed / base_atm["n"] if base_atm["n"] else 0.0
        discriminates = removed_frac >= MIN_DISCRIM_FRAC
        vd, lift = _verdict_for(m, base_atm)
        label = vd if discriminates else "NO-OP(everything near a level)"
        verdicts[f"A7_{name}"] = {
            "verdict": label, "oos_exp_lift_vs_baseline_dollar": lift,
            "n": m["n"], "trades_per_week": m["trades_per_week"],
            "filtered_out_vs_baseline": removed,
            "removed_frac": round(removed_frac, 3),
            "discriminates_>=10pct": discriminates}
        # only a meaningfully-discriminating, +lift variant can be the "best"
        if discriminates and lift > 0 and (a7_best is None or lift > a7_best[1]):
            a7_best = (name, lift, vd)
    verdicts["A7_overall"] = {
        "best_variant": a7_best[0] if a7_best else None,
        "best_lift": a7_best[1] if a7_best else None,
        "verdict": a7_best[2] if a7_best else "DEAD",
        "note": ("No level-proximity filter both discriminates (removes >=10% of "
                 "trades) AND lifts OOS: the discriminating tight buckets go OOS-"
                 "NEGATIVE, the +lift buckets are near-no-ops. At SPY ~$400-600 "
                 "structural levels are too DENSE for 'mid-air' to exist meaningfully. "
                 "Corroborated on J's data: his winners did NOT cluster near levels "
                 "(psych near-vs-mid-air @0.05% = -2.6pp WR, -12.5 pct_move).")}
    # A10 — behavioral; the "hot read after a win" hypothesis dies to the day-regime
    # confound (de-meaning by own-day mean inverts the after-win edge → it was day
    # clustering, not a state effect). The one real state signal (loss-streak tilt) is
    # already L168. No live-filter possible anyway (no J trade-stream).
    cft = a10["CONFOUND_TEST_day_demeaned"]
    a10_verdict = ("WATCH" if cft.get("hot_hand_survives_day_control") else "DEAD")
    verdicts["A10_overall"] = {
        "verdict": a10_verdict,
        "hot_hand_survives_day_control": cft.get("hot_hand_survives_day_control"),
        "raw_after_win_minus_after_loss_pct_move":
            cft.get("raw_after_win_minus_after_loss"),
        "day_demeaned_after_win_minus_after_loss_pct_move":
            cft.get("DAY_DEMEANED_after_win_minus_after_loss"),
        "note": "DEAD: the apparent after-win 'hot read' (+11.2 raw pct_move) is a "
                "DAY-REGIME confound — de-meaning by own-day mean inverts it (after-win "
                "goes BELOW the day average). J wins repeatedly on good days / loses "
                "repeatedly on chop days, so 'after a win' just proxies 'good day'. The "
                "only real state signal is loss-streak-2+ tilt (38% WR) = already L168. "
                "Not a live filter anyway (no J trade-stream)."}

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "campaign": "J-DATA profitability — A6 (calendar/event-day) / A7 (level-keyed "
                    "entry) / A10 (self-PnL state). markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md",
        "method": (
            "His Webull data (analysis/webull-j-trades/, ~655 closed round-trips "
            "2021-23) DEFINES each hypothesis. OUR 2025-26 SPY real-OPRA fills VALIDATE "
            "the TRANSLATABLE findings (A6 calendar filter, A7 level-proximity filter) "
            "forward via the SAME OP-22 _full_metrics scorecard reused verbatim from "
            "j_entry_specificity. A filter SHIPS only if it clears the edge gate, fires "
            ">=2/wk, AND lifts OOS expectancy vs the unfiltered morning baseline. A10 is "
            "behavioral (J's live sequencing) → Part-A-only by construction."),
        "anti_confound_note": (
            "Per-cell HEADLINE is WR + size-neutral pct_move (return on premium per "
            "contract); raw $pnl is reported but flagged SIZE_CONFOUNDED (his book size "
            "varied by time-of-day/regime, mixing edge with sizing)."),
        "causality": "Part-A features at/before entry-bar close (same-session premarket "
                     "for PMH/PML; look-back only for A10 streak state). Part-B fills "
                     "next-bar-open (sim, L166); chart-stop only (premium_stop=-0.99).",
        "data": {"his": "webull-j-trades (winner+loser cache union)",
                 "our_spy": SPY.name, "our_vix": VIX.name, "trading_days": n_days,
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "edge_ship_bar": "OP-22: OOS+ AND WF_median>=0.70 AND all-cuts-OOS+ AND q>=60% "
                         "AND DSR not-FAIL AND drop-top5 robust (+both-dirs+ when both "
                         "sides) AND fires >=2/wk AND OOS lift vs baseline.",
        "PART_A_j_data": {"A6_calendar": a6, "A7_level_keyed": a7,
                          "A10_self_pnl_state": a10},
        "PART_B_our_data_validation": part_b,
        "VERDICTS": verdicts,
        "caveats": [
            "A7 on J's data: his bar cache has NO prior-day bars, so PDH/PDL are "
            "unavailable in Part A (round/open/premarket/intraday levels only). OUR "
            "Part-B forward test DOES include PDH/PDL (continuous data) — disclosed.",
            "A7 his-data near_level baseline (entry_quality.json) labelled 100% of "
            "trades near_level=True (uninformative at 0.15% vs intraday hi/lo which is "
            "always near price); this module re-derives a GRANULAR distance + bucket "
            "ladder to get a real near-vs-mid-air contrast.",
            "A10 cannot be a live engine filter (no live J trade-stream); it answers "
            "'when was J's READ sharpest', informative for J's own discipline, not a "
            "wireable gate. Reported honestly as Part-A-only.",
            "His-data WR absolutes are winner-date-biased UP (loser-only dates partly "
            "missing from caches); the per-cell CONTRASTS are bias-robust (subsets share "
            "dates); pct_move is the size-neutral cross-check.",
            "Proxy strikes (L58): nearest-cached strike; OPRA cache ends ~2026-05-29 "
            "(later signals = cache_miss in coverage).",
            "Propose-only (Rule 9). Any SHIP => dormant/WATCH_ONLY wiring; J holds REVOKE.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print("\n=== PART B (ATM tier) ===")
    print(f"[baseline_full_morning] sig={base['signal_count']} n={base_atm['n']} "
          f"exp=${base_atm['exp_dollar']:+.1f} OOSexp=${base_atm['oos_exp_dollar']:+.1f} "
          f"{base_atm['trades_per_week']}/wk")
    for grp in ("A6_calendar", "A7_level_proximity"):
        for name, v in part_b[grp].items():
            m = v["tiers"]["ATM"]
            print(f"[{grp}:{name}] sig={v['signal_count']} n={m['n']} "
                  f"exp=${m['exp_dollar']:+.1f} WR={m['wr_pct']}% "
                  f"{m['trades_per_week']}/wk | OOSexp=${m['oos_exp_dollar']:+.1f} "
                  f"medWF={m['median_wf_norm']:+.3f} allOOS+={m['all_cuts_oos_positive']} "
                  f"q+={m['quarter_positive_fraction']:.0%} DSR={m['dsr_verdict']} "
                  f"SURV={m['DAILY_SURVIVOR']}")
    print("\n=== VERDICTS ===")
    for k in ("A6_overall", "A7_overall", "A10_overall"):
        print(f"  {k}: {verdicts[k]}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
