"""H1/H6 — absorption at prior-day levels: does tape-level absorption predict
level HOLD vs BREAK, and does the engine's existing bar-proxy agree with it?

Context (per markdown/research/BACKTESTING-PLAYBOOK.md OP-16/OP-20 + C6 no-look-ahead):
  J's ONE verified edge (backtest/autoresearch/j_level_midday_probe.py, E1) is price
  at a prior-day level (PDH/PDL/PDC, within 0.1%), VWAP-aligned, midday. That detector's
  AT-LEVEL / DIRECTION / touch_hold logic is REUSED here verbatim (not reinvented).

  The live engine grades a level touch's absorption quality with a BAR PROXY: "high
  volume + narrow range at the level" (markdown/trading-knowledge/market-structure-
  execution.md §5). That proxy has NEVER been checked against real trade-level tape.
  H3 (h3_ofi_latency.py) already showed UNCONDITIONAL order-flow imbalance at random
  clock times has ~zero forward edge (corr ~0.002) against a validated +0.30 same-bar
  pipeline. This script asks the CONDITIONAL question: does flow AT A LEVEL touch carry
  information the bar proxy misses?

Data (all already cached, ZERO new API calls):
  - SPY 5m bars: backtest/data/spy_5m_2026-05-19_2026-09-04.csv (covers the 20-day tape
    window 2026-08-10..2026-09-04). Columns: timestamp_et, open, high, low, close, volume.
  - SIP trade tape: backtest/data/sip_tape/SPY/<date>/... loaded via
    h3_ofi_latency.fetch_day_signed_tape() (Lee-Ready signed trades, zero fetches — the
    cache is already on disk for the 20 sessions).

Events: every touch of PDH/PDL/PDC on the 20 cached days, RTH 10:00-15:30 ET, using the
j_level_midday_probe AT-LEVEL definition (close within 0.1% of level) evaluated on the
5-MINUTE bar close (stated explicitly per task: 5m bars used for level-touch detection —
simpler than reconstructing 1m bars from tape, and the existing validated detector already
operates on 5m closes; the TAPE itself supplies sub-second resolution for the absorption
features). De-duplicated: one event per level per 15 minutes (>=3 bars gap between repeat
touches of the SAME level).

Tape features, computed ONLY from trades with t_ns <= touch_ns (C6 causal):
  a. absorption_ratio = aggressor volume INTO the level / price progress THROUGH the level
     (in ticks, $0.01, floored at 1 tick) over [t-300s, t] and [t-60s, t].
     "Into the level" = buy volume at resistance (PDH short-side touch) or sell volume at
     support (PDL/PDC long-side touch) -- i.e. volume pushing price TOWARD/THROUGH the level
     in the direction that would BREAK it. "Progress through" = how far price actually moved
     in that break direction over the window (ticks), floored at 1 tick so a stalled tape
     (aggression with no progress = classic absorption) yields a large, not divide-by-zero,
     ratio.
  b. into_level_share = signed volume toward the level / total volume over the window.
  c. big_print_share = volume from trades >= that day's 95th-percentile trade size / total
     volume in the window, and its signed version (signed by aggressor side).
  d. bar proxy (from the SAME 5m bar that produced the touch): touching-bar volume vs its
     trailing-20-bar median, and its range vs trailing-20-bar median; proxy flag =
     (vol_ratio >= 1.5 AND range_ratio <= 0.7) per market-structure-execution.md §5 language
     ("high volume + narrow range").

Outcome, strictly using bars/tape AFTER the touch bar:
  HOLD    = price reverses away from the level by >= 0.10% within 15 min AND does not
            close beyond the level by > 0.05% first.
  BREAK   = closes beyond the level by > 0.05% within 15 min (checked bar-by-bar, in order,
            so a BREAK that happens before the HOLD condition is satisfied wins).
  NEITHER = neither condition met in the 15-min window.
  Also recorded: 30-min signed return in the hold-direction (positive = price behaved as
  the "hold" trade would want).

Null (direction-controlled, STRATEGY-BACKLOG-style control per h3's own pattern): the same
tape features computed at random non-level timestamps on the SAME 20 days (>=30 draws/day,
seed fixed at 20260907), with a pseudo-level = the current price at the draw (so "progress
through the level" and "into-level side" are still well-defined, just not anchored to a
real PDH/PDL/PDC). This exposes any feature that "works" purely from within-window
autocorrelation rather than genuine level interaction.

Measure: AUC (real vs null) of each feature for HOLD vs BREAK (NEITHER excluded from the
AUC calc, standard practice — it is not a class of the binary outcome), and mean 30-min
hold-direction return by feature tercile. H6 verdict = correlation between the bar-proxy
flag and absorption_ratio, and a head-to-head AUC comparison of which better predicts HOLD.

Rail-4 CLEAR: pure research probe. Touches NO params/heartbeat/filters/doctrine. Places NO
order. Arms NOTHING. Owns ONLY this file and analysis/recommendations/h1-absorption-at-
levels.json (per task assignment) -- does NOT touch h_edge_capture_tape.py (concurrent
agent's file).

Run:
    backtest/.venv/Scripts/python.exe -u -m autoresearch.h1_absorption_at_levels
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "backtest")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.h3_ofi_latency import fetch_day_signed_tape  # noqa: E402

ET = ZoneInfo("America/New_York")

SPY_CSV = _REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-04.csv"
OUT_PATH = _REPO / "analysis" / "recommendations" / "h1-absorption-at-levels.json"

TAPE_DAYS = [
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14",
    "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
]

AT_LEVEL_PCT = 0.10          # j_level_midday_probe AT-LEVEL definition
WIN_START = dt.time(10, 0)
WIN_END = dt.time(15, 30)
DEDUP_MIN = 15               # one event per level per 15 minutes
TICK = 0.01                  # SPY min tick, $
HOLD_MOVE_PCT = 0.10         # >= this % reversal away from level = HOLD
BREAK_MOVE_PCT = 0.05        # > this % beyond level = BREAK
OUTCOME_WINDOW_MIN = 15
RETURN_WINDOW_MIN = 30
LOOKBACK_WINDOWS_SEC = [60, 300]
NULL_DRAWS_PER_DAY = 30
SEED = 20260907
BIG_PRINT_PCTL = 95.0
BAR_PROXY_LOOKBACK = 20
PROXY_VOL_RATIO_MIN = 1.5
PROXY_RANGE_RATIO_MAX = 0.7


# ---------------------------------------------------------------------------
# Bars + levels (reuses j_level_midday_probe's PDH/PDL/PDC logic, causal)
# ---------------------------------------------------------------------------

def load_bars() -> pd.DataFrame:
    df = pd.read_csv(SPY_CSV)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert(ET)
        .dt.tz_localize(None)
    )
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    rth = df[(df["timestamp_et"].dt.time >= dt.time(9, 30))
             & (df["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    return rth


def prior_day_levels(rth: pd.DataFrame) -> dict:
    daily = rth.groupby("date").agg(h=("high", "max"), l=("low", "min"))
    daily["c"] = rth.groupby("date")["close"].last()
    prior = daily.sort_index().shift(1)
    return {
        d: {"PDH": float(r["h"]), "PDL": float(r["l"]), "PDC": float(r["c"])}
        for d, r in prior.iterrows() if not np.isnan(r["h"])
    }


def bar_proxy_features(day_bars: pd.DataFrame, j: int) -> dict:
    """High-volume + narrow-range bar proxy, trailing-20-bar median (causal: bars < j)."""
    lo = max(0, j - BAR_PROXY_LOOKBACK)
    hist = day_bars.iloc[lo:j]
    if len(hist) < 5:
        return {"vol_ratio": None, "range_ratio": None, "proxy_flag": None}
    vol_med = hist["volume"].median()
    rng_med = (hist["high"] - hist["low"]).median()
    bar = day_bars.iloc[j]
    vol_ratio = float(bar["volume"] / vol_med) if vol_med > 0 else None
    range_ratio = float((bar["high"] - bar["low"]) / rng_med) if rng_med > 0 else None
    flag = None
    if vol_ratio is not None and range_ratio is not None:
        flag = bool(vol_ratio >= PROXY_VOL_RATIO_MIN and range_ratio <= PROXY_RANGE_RATIO_MAX)
    return {"vol_ratio": vol_ratio, "range_ratio": range_ratio, "proxy_flag": flag}


def find_touch_events(rth: pd.DataFrame, lvl_map: dict) -> list[dict]:
    """AT-LEVEL touches on the 5m close, j_level_midday_probe definition, dedup 15min/level."""
    events = []
    for d, day in rth.groupby("date"):
        d_str = d.isoformat()
        if d_str not in TAPE_DAYS:
            continue
        if d not in lvl_map:
            continue
        day = day.reset_index(drop=True)
        levels = lvl_map[d]
        last_touch_ts: dict = {}
        for j in range(len(day)):
            t = day["timestamp_et"].iloc[j].time()
            if not (WIN_START <= t < WIN_END):
                continue
            c = float(day["close"].iloc[j])
            for lvl_name, lvl_px in levels.items():
                if lvl_px <= 0:
                    continue
                d_pct = abs(c / lvl_px - 1.0) * 100.0
                if d_pct > AT_LEVEL_PCT:
                    continue
                ts = day["timestamp_et"].iloc[j]
                prev_ts = last_touch_ts.get(lvl_name)
                if prev_ts is not None and (ts - prev_ts).total_seconds() < DEDUP_MIN * 60:
                    continue
                last_touch_ts[lvl_name] = ts
                side = "resistance" if lvl_name == "PDH" else "support"
                # PDC can act as either; use direction of approach in the last 3 bars.
                if lvl_name == "PDC":
                    lookback = day["close"].iloc[max(0, j - 3):j]
                    side = "resistance" if (len(lookback) and lookback.mean() < lvl_px) else "support"
                proxy = bar_proxy_features(day, j)
                events.append({
                    "date": d_str, "j": j, "level_name": lvl_name, "level_px": lvl_px,
                    "side": side, "touch_ts": ts, "touch_close": c,
                    "level_dist_pct": round(d_pct, 4),
                    "bar_proxy": proxy,
                })
    return events


# ---------------------------------------------------------------------------
# Tape features (causal: trades with t_ns <= touch_ns only)
# ---------------------------------------------------------------------------

def _ns(ts: pd.Timestamp) -> int:
    return int(ts.tz_localize(ET).value)


def _day_p95_size(signed: pd.DataFrame) -> float:
    return float(np.percentile(signed["size"].to_numpy(dtype=float), BIG_PRINT_PCTL))


def tape_features_at(signed: pd.DataFrame, touch_ns: int, level_px: float, side: str,
                      p95_size: float) -> dict:
    """Absorption features over trailing windows ending at touch_ns, causal only."""
    out = {}
    ts = signed["t_ns"].to_numpy()
    hi_idx = np.searchsorted(ts, touch_ns, side="right")
    for lb_sec in LOOKBACK_WINDOWS_SEC:
        lo_ns = touch_ns - lb_sec * 1_000_000_000
        lo_idx = np.searchsorted(ts, lo_ns, side="right")
        window = signed.iloc[lo_idx:hi_idx]
        n = len(window)
        key = f"{lb_sec}s"
        if n == 0:
            out[key] = {"absorption_ratio": None, "into_level_share": None,
                       "big_print_share": None, "big_print_share_signed": None, "n_trades": 0}
            continue
        total_vol = float(window["size"].sum())
        # "into the level" direction = the BREAK direction: at resistance (side="resistance")
        # that's buy-side aggression (+1); at support that's sell-side aggression (-1).
        into_sign = 1 if side == "resistance" else -1
        into_vol = float(window.loc[window["sign"] == into_sign, "size"].sum())
        signed_vol = float(window["signed_size"].sum())
        into_level_share = (signed_vol * into_sign) / total_vol if total_vol > 0 else None
        # price progress THROUGH the level in the break direction, in ticks, floored at 1 tick
        first_px = float(window["price"].iloc[0])
        last_px = float(window["price"].iloc[-1])
        progress_signed = (last_px - first_px) * into_sign
        progress_ticks = max(progress_signed / TICK, 1.0)
        absorption_ratio = into_vol / progress_ticks if into_vol > 0 else 0.0
        big_mask = window["size"] >= p95_size
        big_vol = float(window.loc[big_mask, "size"].sum())
        big_signed_vol = float(window.loc[big_mask, "signed_size"].sum())
        out[key] = {
            "absorption_ratio": round(absorption_ratio, 2),
            "into_level_share": round(into_level_share, 4) if into_level_share is not None else None,
            "big_print_share": round(big_vol / total_vol, 4) if total_vol > 0 else None,
            "big_print_share_signed": round(big_signed_vol / total_vol, 4) if total_vol > 0 else None,
            "n_trades": n,
        }
    return out


# ---------------------------------------------------------------------------
# Outcome labeling (strictly after touch)
# ---------------------------------------------------------------------------

def label_outcome(day_bars: pd.DataFrame, j: int, level_px: float, side: str) -> dict:
    """HOLD / BREAK / NEITHER using bars strictly after the touch bar, in order."""
    hold_target = level_px * (1 - HOLD_MOVE_PCT / 100.0) if side == "resistance" else \
        level_px * (1 + HOLD_MOVE_PCT / 100.0)
    break_target = level_px * (1 + BREAK_MOVE_PCT / 100.0) if side == "resistance" else \
        level_px * (1 - BREAK_MOVE_PCT / 100.0)
    touch_ts = day_bars["timestamp_et"].iloc[j]
    deadline = touch_ts + pd.Timedelta(minutes=OUTCOME_WINDOW_MIN)
    outcome = "NEITHER"
    for k in range(j + 1, len(day_bars)):
        ts_k = day_bars["timestamp_et"].iloc[k]
        if ts_k > deadline:
            break
        c = float(day_bars["close"].iloc[k])
        broke = c >= break_target if side == "resistance" else c <= break_target
        held = c <= hold_target if side == "resistance" else c >= hold_target
        if broke:
            outcome = "BREAK"
            break
        if held:
            outcome = "HOLD"
            break
    # 30-min signed return in the hold direction (positive = level behaved as hold-trade wants)
    ret_deadline = touch_ts + pd.Timedelta(minutes=RETURN_WINDOW_MIN)
    later = day_bars[(day_bars["timestamp_et"] > touch_ts) & (day_bars["timestamp_et"] <= ret_deadline)]
    hold_dir_return = None
    if len(later):
        c30 = float(later["close"].iloc[-1])
        raw_ret = (c30 - level_px) / level_px
        hold_dir_return = -raw_ret if side == "resistance" else raw_ret
    return {"outcome": outcome, "return_30m_hold_dir": round(hold_dir_return, 5)
            if hold_dir_return is not None else None}


# ---------------------------------------------------------------------------
# Null: direction-controlled random-timestamp draws
# ---------------------------------------------------------------------------

def find_null_events(rth: pd.DataFrame, rng: random.Random) -> list[dict]:
    events = []
    for d, day in rth.groupby("date"):
        d_str = d.isoformat()
        if d_str not in TAPE_DAYS:
            continue
        day = day.reset_index(drop=True)
        candidates = [j for j in range(BAR_PROXY_LOOKBACK, len(day) - 3)
                      if WIN_START <= day["timestamp_et"].iloc[j].time() < WIN_END]
        if not candidates:
            continue
        picks = rng.sample(candidates, k=min(NULL_DRAWS_PER_DAY, len(candidates)))
        for j in picks:
            side = rng.choice(["resistance", "support"])
            level_px = float(day["close"].iloc[j])  # pseudo-level = current price
            proxy = bar_proxy_features(day, j)
            events.append({
                "date": d_str, "j": j, "level_name": "NULL", "level_px": level_px,
                "side": side, "touch_ts": day["timestamp_et"].iloc[j],
                "touch_close": level_px, "level_dist_pct": 0.0, "bar_proxy": proxy,
            })
    return events


# ---------------------------------------------------------------------------
# AUC + tercile helpers
# ---------------------------------------------------------------------------

def auc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney AUC: P(score_pos > score_neg). labels: 1=HOLD, 0=BREAK."""
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return None
    n_pos, n_neg = len(pos), len(neg)
    ranks = pd.Series(pos + neg).rank().to_numpy()
    rank_sum_pos = ranks[:n_pos].sum()
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return round(float(u / (n_pos * n_neg)), 4)


def tercile_returns(scores: list[float], returns: list[float]) -> dict:
    paired = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    if len(paired) < 9:
        return {"n": len(paired), "low": None, "mid": None, "high": None}
    paired.sort(key=lambda x: x[0])
    n = len(paired)
    t1, t2 = n // 3, 2 * n // 3
    low = [r for _, r in paired[:t1]]
    mid = [r for _, r in paired[t1:t2]]
    high = [r for _, r in paired[t2:]]
    return {
        "n": n,
        "low": round(float(np.mean(low)), 5) if low else None,
        "mid": round(float(np.mean(mid)), 5) if mid else None,
        "high": round(float(np.mean(high)), 5) if high else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FEATURE_KEYS = [
    ("absorption_ratio_60s", ("60s", "absorption_ratio")),
    ("absorption_ratio_300s", ("300s", "absorption_ratio")),
    ("into_level_share_60s", ("60s", "into_level_share")),
    ("into_level_share_300s", ("300s", "into_level_share")),
    ("big_print_share_60s", ("60s", "big_print_share")),
    ("big_print_share_300s", ("300s", "big_print_share")),
    ("big_print_share_signed_60s", ("60s", "big_print_share_signed")),
    ("big_print_share_signed_300s", ("300s", "big_print_share_signed")),
]


def build_rows(events: list[dict], rth: pd.DataFrame, day_tape_cache: dict,
               day_p95_cache: dict) -> list[dict]:
    rows = []
    by_date = {d: g.reset_index(drop=True) for d, g in rth.groupby("date")}
    for ev in events:
        d_str = ev["date"]
        d = dt.date.fromisoformat(d_str)
        day_bars = by_date[d]
        if d_str not in day_tape_cache:
            print(f"  [tape] loading {d_str} ...")
            day_tape_cache[d_str] = fetch_day_signed_tape(d_str).signed
            day_p95_cache[d_str] = _day_p95_size(day_tape_cache[d_str])
        signed = day_tape_cache[d_str]
        p95 = day_p95_cache[d_str]
        touch_ns = _ns(ev["touch_ts"])
        tape_feats = tape_features_at(signed, touch_ns, ev["level_px"], ev["side"], p95)
        outcome = label_outcome(day_bars, ev["j"], ev["level_px"], ev["side"])
        rows.append({**ev, "tape": tape_feats, **outcome})
    return rows


def battery(rows: list[dict], label: str) -> dict:
    binary_rows = [r for r in rows if r["outcome"] in ("HOLD", "BREAK")]
    labels = [1 if r["outcome"] == "HOLD" else 0 for r in binary_rows]
    n_hold = sum(labels)
    n_break = len(labels) - n_hold
    n_neither = sum(1 for r in rows if r["outcome"] == "NEITHER")
    auc_table = {}
    tercile_table = {}
    n_cells = 0
    for feat_name, (win, sub) in FEATURE_KEYS:
        scores = [r["tape"][win][sub] for r in binary_rows]
        valid = [(s, l) for s, l in zip(scores, labels) if s is not None]
        if len(valid) < 10:
            auc_table[feat_name] = None
            tercile_table[feat_name] = {"n": len(valid), "low": None, "mid": None, "high": None}
            n_cells += 1
            continue
        vs, vl = zip(*valid)
        auc_table[feat_name] = auc(list(vs), list(vl))
        all_scores = [r["tape"][win][sub] for r in rows]
        all_returns = [r["return_30m_hold_dir"] for r in rows]
        tercile_table[feat_name] = tercile_returns(all_scores, all_returns)
        n_cells += 1
    # bar proxy
    proxy_scores = [1.0 if r["bar_proxy"]["proxy_flag"] else 0.0
                    for r in binary_rows if r["bar_proxy"]["proxy_flag"] is not None]
    proxy_labels = [l for r, l in zip(binary_rows, labels) if r["bar_proxy"]["proxy_flag"] is not None]
    proxy_auc = auc(proxy_scores, proxy_labels) if len(proxy_scores) >= 10 else None
    n_cells += 1
    return {
        "label": label,
        "n_events": len(rows), "n_hold": n_hold, "n_break": n_break, "n_neither": n_neither,
        "auc_table": auc_table,
        "bar_proxy_auc": proxy_auc,
        "tercile_returns": tercile_table,
        "n_comparison_cells": n_cells,
    }


def h6_verdict(real_rows: list[dict]) -> dict:
    binary_rows = [r for r in real_rows if r["outcome"] in ("HOLD", "BREAK")
                   and r["bar_proxy"]["proxy_flag"] is not None
                   and r["tape"]["300s"]["absorption_ratio"] is not None]
    if len(binary_rows) < 10:
        return {"verdict": "INSUFFICIENT_N", "n": len(binary_rows)}
    proxy_flags = [1.0 if r["bar_proxy"]["proxy_flag"] else 0.0 for r in binary_rows]
    absorption = [r["tape"]["300s"]["absorption_ratio"] for r in binary_rows]
    labels = [1 if r["outcome"] == "HOLD" else 0 for r in binary_rows]
    # agreement: point-biserial-ish correlation between proxy flag and absorption ratio
    corr = float(np.corrcoef(proxy_flags, absorption)[0, 1]) if len(set(proxy_flags)) > 1 else None
    proxy_auc = auc(proxy_flags, labels)
    absorption_auc = auc(absorption, labels)
    better = None
    if proxy_auc is not None and absorption_auc is not None:
        better = "bar_proxy" if abs(proxy_auc - 0.5) > abs(absorption_auc - 0.5) else "absorption_ratio_300s"
    return {
        "n": len(binary_rows),
        "proxy_vs_absorption_corr": round(corr, 4) if corr is not None else None,
        "bar_proxy_auc": proxy_auc,
        "absorption_ratio_300s_auc": absorption_auc,
        "better_predictor": better,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    print("[H1] loading 5m bars ...", flush=True)
    rth = load_bars()
    lvl_map = prior_day_levels(rth)

    print("[H1] finding real touch events (AT-LEVEL, dedup 15min/level) ...", flush=True)
    real_events = find_touch_events(rth, lvl_map)
    print(f"[H1] {len(real_events)} real touch events found across {len(TAPE_DAYS)} days", flush=True)

    rng = random.Random(SEED)
    print("[H1] drawing null events (random timestamps, direction-controlled) ...", flush=True)
    null_events = find_null_events(rth, rng)
    print(f"[H1] {len(null_events)} null events drawn (seed={SEED})", flush=True)

    day_tape_cache: dict = {}
    day_p95_cache: dict = {}

    print("[H1] computing tape features + outcomes for REAL events ...", flush=True)
    real_rows = build_rows(real_events, rth, day_tape_cache, day_p95_cache)
    print("[H1] computing tape features + outcomes for NULL events ...", flush=True)
    null_rows = build_rows(null_events, rth, day_tape_cache, day_p95_cache)

    real_battery = battery(real_rows, "real_at_level")
    null_battery = battery(null_rows, "null_random_timestamp")
    h6 = h6_verdict(real_rows)

    n_cells_disclosed = real_battery["n_comparison_cells"] + null_battery["n_comparison_cells"]

    # H1 verdict: does any real-window feature clear AUC 0.55 in both 60s/300s windows
    # while its null counterpart stays near 0.50, with n>=10 per class?
    h1_hits = []
    for feat_name, _ in FEATURE_KEYS:
        r_auc = real_battery["auc_table"].get(feat_name)
        n_auc = null_battery["auc_table"].get(feat_name)
        if r_auc is not None and n_auc is not None:
            if abs(r_auc - 0.5) >= 0.05 and abs(r_auc - 0.5) > abs(n_auc - 0.5) + 0.03:
                h1_hits.append({"feature": feat_name, "real_auc": r_auc, "null_auc": n_auc})
    if real_battery["n_hold"] < 10 or real_battery["n_break"] < 10:
        h1_verdict = (f"INSUFFICIENT_N (n_hold={real_battery['n_hold']}, "
                      f"n_break={real_battery['n_break']}, need >=10 each)")
    elif h1_hits:
        h1_verdict = f"SIGNAL: {len(h1_hits)} feature(s) beat null by >=0.03 AUC margin: {h1_hits}"
    else:
        h1_verdict = "NULL_RESULT: no absorption feature separates real AUC from null AUC by >=0.03"

    if h6.get("verdict") == "INSUFFICIENT_N":
        h6_verdict_line = f"INSUFFICIENT_N (n={h6['n']})"
    else:
        agree = h6["proxy_vs_absorption_corr"]
        better = h6["better_predictor"]
        h6_verdict_line = (f"bar-proxy vs absorption_ratio corr={agree}; "
                           f"proxy AUC={h6['bar_proxy_auc']} vs absorption AUC="
                           f"{h6['absorption_ratio_300s_auc']}; better={better}")

    result = {
        "rule_id": "h1-absorption-at-levels",
        "kind": "detector-candidate-screen",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hypotheses": {
            "H1": "aggressive volume into a PD-level that is absorbed (little price "
                  "progress) predicts the level HOLDING vs BREAKING",
            "H6": "the engine's bar-proxy (high-vol + narrow-range) agrees with real "
                  "tape-level absorption",
        },
        "detector_reused": "j_level_midday_probe AT-LEVEL (0.1%) + PDH/PDL/PDC, causal",
        "days": TAPE_DAYS,
        "resolution_note": "touch detection on 5m bar closes (stated per task option); "
                           "absorption features computed from full-resolution SIP tape "
                           "in trailing 60s/300s windows ending at the touch bar's close "
                           "timestamp",
        "params": {
            "AT_LEVEL_PCT": AT_LEVEL_PCT, "WIN_START": str(WIN_START), "WIN_END": str(WIN_END),
            "DEDUP_MIN": DEDUP_MIN, "HOLD_MOVE_PCT": HOLD_MOVE_PCT,
            "BREAK_MOVE_PCT": BREAK_MOVE_PCT, "OUTCOME_WINDOW_MIN": OUTCOME_WINDOW_MIN,
            "RETURN_WINDOW_MIN": RETURN_WINDOW_MIN, "NULL_DRAWS_PER_DAY": NULL_DRAWS_PER_DAY,
            "SEED": SEED, "BIG_PRINT_PCTL": BIG_PRINT_PCTL,
        },
        "real": real_battery,
        "null": null_battery,
        "h6_bar_proxy_vs_absorption": h6,
        "multiple_comparisons_disclosure": {
            "n_feature_x_window_cells_real": n_cells_disclosed,
            "note": "8 tape-feature/window cells + 1 bar-proxy cell, x2 (real+null) = "
                    "18 AUC comparisons; H1 threshold requires real-vs-null margin >=0.03 "
                    "AND |real_auc-0.5|>=0.05 to count as a hit, precisely to guard against "
                    "cherry-picking 1 of 18 cells that clears by chance.",
        },
        "H1_verdict": h1_verdict,
        "H6_verdict": h6_verdict_line,
        "caveats": [
            "C6: all tape features computed only from trades with t_ns <= touch timestamp; "
            "outcomes computed only from bars strictly after the touch bar.",
            "Touch detection resolution is 5m bar closes, not 1m — stated per task option; "
            "a touch could occur and reverse within a 5m bar without being detected.",
            "20-day window is short; this is a screen, not a ratification-grade sample.",
            "PDC side (support/resistance) inferred from 3-bar approach direction — a "
            "heuristic, not causal look-ahead, but coarser than PDH/PDL's fixed side.",
            "Do not tune AT_LEVEL_PCT/HOLD/BREAK thresholds after seeing these outcomes — "
            "they are the j_level_midday_probe / task-spec values, unmodified.",
        ],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str))

    print("\n===== H1/H6 SUMMARY =====", flush=True)
    print(f"days={len(TAPE_DAYS)} real_events={real_battery['n_events']} "
          f"(HOLD={real_battery['n_hold']} BREAK={real_battery['n_break']} "
          f"NEITHER={real_battery['n_neither']})", flush=True)
    print(f"null_events={null_battery['n_events']} (HOLD={null_battery['n_hold']} "
          f"BREAK={null_battery['n_break']} NEITHER={null_battery['n_neither']})", flush=True)
    print("\nAUC table (real | null):", flush=True)
    for feat_name, _ in FEATURE_KEYS:
        print(f"  {feat_name:32s} real={real_battery['auc_table'].get(feat_name)} "
              f"null={null_battery['auc_table'].get(feat_name)}", flush=True)
    print(f"  {'bar_proxy_flag':32s} real={real_battery['bar_proxy_auc']} "
          f"null={null_battery['bar_proxy_auc']}", flush=True)
    print(f"\nH6: {h6_verdict_line}", flush=True)
    print(f"\nH1 verdict: {h1_verdict}", flush=True)
    print(f"H6 verdict line: {h6_verdict_line}", flush=True)
    print(f"\nWrote {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
