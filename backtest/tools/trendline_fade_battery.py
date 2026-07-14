"""trendline_fade_battery.py -- TREND-FADE-PREREG (A4, 2026-07-14 after-4pm work block).

Runs the FROZEN pre-registration at
analysis/recommendations/prereg-trendline-fade-battery-2026-07-14.json verbatim: 3 FADE entry
variants (F1 fade-immediate, F2 fade-reclaim-confirmed, F3 fade-low-volume) x 2 line families
(wick, body) x 2 directions = 12 candidate cells, replayed through the LIVE exit_manager
decision core (SS-B shape) on real local OPRA option bars. A fade trade takes the OPPOSITE
side of the break's own continuation trade (S1's trendline_break_battery.py studied and KILLED
12/12 continuation entries). Two nulls per real fade episode: random-entry, and
break_direction (S1's own continuation trade -- the load-bearing "does fading beat the break"
comparison). IS/OOS split, BH-FDR across the 12 cells, concentration disclosure, OP-16-style
anchor-day check (informational -- nothing is currently armed).

READ-ONLY of the audit-owned trendline subsystem and of S1's own break battery: imports
trendline_break_replay.py's pure line-geometry helpers (_line_value, TOL, day-bar loading) to
reconstruct F2's reclaim bar WITHOUT look-ahead; never imports or edits trendline_engine.py,
trendline_break_battery.py, any drawing-bridge script, or the audit doc.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trendline_fade_battery.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time as _time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
sys.path.insert(0, str(BACKTEST))
sys.path.insert(0, str(BACKTEST / "tools"))
sys.path.insert(0, str(BACKTEST / "autoresearch"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
import t4_exit_matrix as t4  # noqa: E402
import trendline_break_replay as tbr  # noqa: E402 -- READ-ONLY reuse, never edited
from autoresearch.strategy_space_grind import (  # noqa: E402
    J_WINNERS, J_LOSERS, OOS_BOUNDARY,
)

DS_PATH = REPO / "analysis" / "trendlines" / "break-dataset.jsonl"
SUMMARY_PATH = REPO / "analysis" / "trendlines" / "break-dataset-summary.json"
PREREG_PATH = REPO / "analysis" / "recommendations" / "prereg-trendline-fade-battery-2026-07-14.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "trendline-fade-battery.json"
OUT_MD = REPO / "analysis" / "recommendations" / "trendline-fade-battery.md"

TIME_STOP_ET = dt.time(15, 50)
SS_B_SHAPE = {
    "premium_stop_pct": -0.5, "tp1_premium_pct": 0.5, "tp1_qty_fraction": 0.8,
    "profit_lock_mode": "fixed", "profit_lock_arm_pct": 0.05, "trail_pct": 0.125,
    "runner_target_pct": 2.5,
}
VOL_LOW_MAX = 1.0  # F3: below-average-volume breaks (mirror of S1 V3's >=1.5 threshold)
RECLAIM_HORIZON_BARS = 10
RANDOM_SEED = 1407  # identical seed to S1 for direct comparability

_WIN_DAYS = {d for d, _s, _p in J_WINNERS}
_LOSE_DAYS = {d for d, _s, _p in J_LOSERS}


def log(msg: str) -> None:
    print(f"[tl-fade-battery] {msg}", flush=True)


# --------------------------------------------------------------------------- bar loading
def load_all_day_bars() -> dict[str, list[dict]]:
    """Same cache reload as S1 -- guarantees identical bar_idx alignment to break-dataset.jsonl."""
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    primary = REPO / summary["primary_cache"].replace("\\", "/")
    ext = REPO / summary["extension_cache"].replace("\\", "/")
    df = tbr.load_cache(primary)
    if ext.exists():
        df2 = tbr.load_cache(ext)
        df = pd.concat([df, df2], ignore_index=True)
        df = df.drop_duplicates(subset="unix").sort_values("unix").reset_index(drop=True)
    by_date: dict[str, list[dict]] = {}
    for date_et, g in df.groupby("date_et"):
        by_date[date_et] = tbr.day_bar_list(g)
    return by_date


# --------------------------------------------------------------------------- episode building
class Episode:
    __slots__ = ("date", "family", "kind", "break_direction", "fade_side", "variant",
                 "entry_time_et", "entry_spot", "volume_ratio")

    def __init__(self, date, family, kind, break_direction, fade_side, variant,
                 entry_time_et, entry_spot, volume_ratio):
        self.date = date
        self.family = family
        self.kind = kind
        self.break_direction = break_direction   # 'bearish' | 'bullish' -- the BREAK's own direction
        self.fade_side = fade_side                # 'C' | 'P' -- the FADE trade's side (opposite of break)
        self.variant = variant
        self.entry_time_et = entry_time_et        # "HH:MM" DST-correct ET wall-clock string
        self.entry_spot = entry_spot
        self.volume_ratio = volume_ratio


def _find_reclaim_entry(rec: dict, day_bars: list[dict]) -> tuple[int, float] | None:
    """No-look-ahead reclaim walk: from break_bar_idx+1 through +RECLAIM_HORIZON_BARS, using the
    SAME line-value math as trendline_break_replay.py (imported, never forked). Returns the
    FIRST bar whose CLOSE re-crosses the line back to the PRE-BREAK side by >= dynamic
    tolerance (support break: close > line_value + tol; resistance break: close < line_value -
    tol) -- i.e. direct evidence the break has already started failing. Unlike S1's V2 (which
    requires a separate touch-then-confirm step), F2 fires on the reclaim close itself -- a
    simpler, genuinely different condition, not a re-derivation of V2.
    Returns (reclaim_bar_idx, reclaim_bar_close) or None."""
    br = rec["break"]
    i1 = rec["a_bar_idx"]
    p1 = rec["a_price"]
    slope = rec["slope_per_bar"]
    kind = rec["kind"]
    j_break = br["break_bar_idx"]
    day_len = len(day_bars)
    horizon_end = min(j_break + 1 + RECLAIM_HORIZON_BARS, day_len)
    for k in range(j_break + 1, horizon_end):
        lv_k = tbr._line_value(p1, slope, i1, k)
        tol_k = max(tbr.TOL, 0.0015 * lv_k)
        close_k = day_bars[k]["c"]
        if kind == "support":       # break was bearish (down through support) -- reclaim = close back ABOVE
            reclaimed = close_k > lv_k + tol_k
        else:                        # break was bullish (up through resistance) -- reclaim = close back BELOW
            reclaimed = close_k < lv_k - tol_k
        if reclaimed:
            return k, close_k
    return None


def build_episodes(records: list[dict], day_bars_by_date: dict[str, list[dict]]) -> dict[str, list[Episode]]:
    """Returns {variant_name: [Episode, ...]} across all 4 family/kind cells. Every episode's
    fade_side is the OPPOSITE of the break's own continuation side (C6-safe: computed from
    information already known at the break bar's close)."""
    out: dict[str, list[Episode]] = {"F1_fade_immediate": [], "F2_fade_reclaim_confirmed": [],
                                      "F3_fade_low_volume": []}
    n_no_break = n_wick_only = n_f2_no_reclaim = n_missing_daybars = 0
    for rec in records:
        br = rec.get("break")
        if not br:
            n_no_break += 1
            continue
        if br["break_type"] != "close_through":
            n_wick_only += 1
            continue
        family = rec["anchor_family"]
        kind = rec["kind"]
        break_direction = br["break_direction"]
        fade_side = "C" if break_direction == "bearish" else "P"  # OPPOSITE of the break's own side
        date = rec["date_et"]

        day_bars = day_bars_by_date.get(date)
        if day_bars is None:
            n_missing_daybars += 1
            continue

        entry_idx = br["break_bar_idx"] + 1  # next bar after break bar's close (C6)
        if entry_idx < len(day_bars):
            entry_hm = day_bars[entry_idx]["hm"]
            out["F1_fade_immediate"].append(Episode(
                date, family, kind, break_direction, fade_side, "F1_fade_immediate",
                entry_hm, br["close_at_break"], br["volume_ratio"],
            ))
            vr = br.get("volume_ratio")
            if vr is not None and vr < VOL_LOW_MAX:
                out["F3_fade_low_volume"].append(Episode(
                    date, family, kind, break_direction, fade_side, "F3_fade_low_volume",
                    entry_hm, br["close_at_break"], vr,
                ))

        # F2: reconstruct reclaim bar with no look-ahead.
        reclaim = _find_reclaim_entry(rec, day_bars)
        if reclaim is None:
            n_f2_no_reclaim += 1
        else:
            reclaim_idx, reclaim_close = reclaim
            if reclaim_idx + 1 < len(day_bars):
                entry_hm_f2 = day_bars[reclaim_idx + 1]["hm"]
                out["F2_fade_reclaim_confirmed"].append(Episode(
                    date, family, kind, break_direction, fade_side, "F2_fade_reclaim_confirmed",
                    entry_hm_f2, reclaim_close, br["volume_ratio"],
                ))
    log(f"skip: no_break={n_no_break} wick_through_only(excluded)={n_wick_only} "
        f"f2_no_reclaim_in_{RECLAIM_HORIZON_BARS}bars={n_f2_no_reclaim} missing_daybars={n_missing_daybars}")
    return out


# --------------------------------------------------------------------------- replay
def _bars_from(date: dt.date, strike: int, side: str, entry_hm: str) -> tuple[list, float] | None:
    """entry_hm: 'HH:MM' DST-correct ET wall-clock string (tbr's own convention), compared
    against the option cache's own naive ET timestamp_et column -- avoids the fixed -04:00 DST
    bug the rest of this repo has already been burned by (see backtest/lib/et_frame.py)."""
    sym = option_symbol(date, strike, side)
    df = load_contract_bars(sym)
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    hm = ts.dt.strftime("%H:%M")
    mask = (hm >= entry_hm) & (ts.dt.date == date)
    sub = df[mask.values]
    if sub.empty:
        return None
    bars = [(r["timestamp_et"].time(), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
            for _, r in sub.iterrows()]
    if not bars or bars[0][1] <= 0:
        return None
    return bars, bars[0][1]


def replay_episode(ep: Episode) -> dict | None:
    date = dt.date.fromisoformat(ep.date)
    strike = int(round(ep.entry_spot))
    loaded = _bars_from(date, strike, ep.fade_side, ep.entry_time_et)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, ep.fade_side, SS_B_SHAPE, TIME_STOP_ET)
    return {
        "date": ep.date, "family": ep.family, "kind": ep.kind,
        "break_direction": ep.break_direction, "fade_side": ep.fade_side, "variant": ep.variant,
        "entry_spot": ep.entry_spot, "entry_premium": entry_premium,
        "pnl": res["pnl"], "stopped": res["stopped"],
    }


def null_random_entry(ep: Episode, day_bars: list[dict], rng: random.Random) -> dict | None:
    if not day_bars:
        return None
    idx = rng.randrange(6, max(7, len(day_bars) - 6))  # avoid the very open/close edge bars
    entry_hm = day_bars[idx]["hm"]
    spot = day_bars[idx]["c"]
    date = dt.date.fromisoformat(ep.date)
    strike = int(round(spot))
    loaded = _bars_from(date, strike, ep.fade_side, entry_hm)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, ep.fade_side, SS_B_SHAPE, TIME_STOP_ET)
    return {"date": ep.date, "pnl": res["pnl"]}


def null_break_direction(ep: Episode) -> dict | None:
    """The ORIGINAL break-continuation trade (S1's own side) -- the load-bearing null for the
    entire fade hypothesis: same entry timestamp/spot/strike-basis, side = break's own side."""
    orig_side = "P" if ep.break_direction == "bearish" else "C"
    date = dt.date.fromisoformat(ep.date)
    strike = int(round(ep.entry_spot))
    loaded = _bars_from(date, strike, orig_side, ep.entry_time_et)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, orig_side, SS_B_SHAPE, TIME_STOP_ET)
    return {"date": ep.date, "pnl": res["pnl"]}


# --------------------------------------------------------------------------- stats (identical to S1)
def _bh_fdr(pvals: list[float], alpha: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh_line = [(k + 1) / m * alpha for k in range(m)]
    sig = [False] * m
    max_k = -1
    for k, idx in enumerate(order):
        if pvals[idx] <= thresh_line[k]:
            max_k = k
    for k in range(max_k + 1):
        sig[order[k]] = True
    return sig


def _ttest_1samp_pvalue(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 1.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    if var <= 0:
        return 0.0 if mean != 0 else 1.0
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    t_stat = mean / se
    from math import erf, sqrt
    z = abs(t_stat)
    p = 2.0 * (1.0 - 0.5 * (1.0 + erf(z / sqrt(2.0))))
    return max(0.0, min(1.0, p))


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    is_t = [t["pnl"] for t in trades if t["date"] < OOS_BOUNDARY.isoformat()]
    oos_t = [t["pnl"] for t in trades if t["date"] >= OOS_BOUNDARY.isoformat()]
    is_mean = (sum(is_t) / len(is_t)) if is_t else 0.0
    oos_mean = (sum(oos_t) / len(oos_t)) if oos_t else 0.0
    wf = round(oos_mean / is_mean, 3) if is_mean > 0 else None
    srt = sorted(pnls, reverse=True)
    top5 = srt[:5]
    top5_pct = round(100.0 * sum(top5) / total, 1) if total != 0 else None
    p_value = _ttest_1samp_pvalue(pnls)
    return {
        "n": n, "n_is": len(is_t), "n_oos": len(oos_t),
        "total_pnl": round(total, 2), "expectancy": round(total / n, 2),
        "win_rate": round(wins / n, 3),
        "is_expectancy": round(is_mean, 2), "oos_expectancy": round(oos_mean, 2),
        "oos_total": round(sum(oos_t), 2), "oos_positive": sum(oos_t) > 0 if oos_t else False,
        "wf": wf, "wf_ge_070": bool(is_mean > 0 and oos_mean > 0 and wf is not None and wf >= 0.70),
        "top5_pct_of_total": top5_pct,
        "p_value": round(p_value, 4),
        "n_stopped": sum(1 for t in trades if t.get("stopped")),
    }


def anchor_check(trades: list[dict]) -> dict:
    hits = [t for t in trades if t["date"] in _WIN_DAYS or t["date"] in _LOSE_DAYS]
    return {
        "fires_on_anchor_days": len(hits) > 0,
        "anchor_day_trades": [{"date": t["date"], "pnl": t["pnl"]} for t in hits],
        "anchor_day_total_pnl": round(sum(t["pnl"] for t in hits), 2) if hits else 0.0,
    }


def verdict_for_cell(summ: dict) -> str:
    if summ.get("n", 0) < 20:
        return "INCONCLUSIVE_UNDERPOWERED"
    c1 = summ["expectancy"] > 0
    c2 = summ["oos_positive"]
    c3 = summ["wf_ge_070"]
    return "PASS" if (c1 and c2 and c3) else "FAIL"  # BH-FDR + null-beat applied at battery level


# --------------------------------------------------------------------------- main
def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="smoke-test: cap records read (0=all)")
    args = parser.parse_args()

    t_start = _time.time()
    log("loading break-dataset.jsonl ...")
    records = []
    with DS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
            if args.limit and len(records) >= args.limit:
                break
    log(f"loaded {len(records)} qualifying-line records")

    log("loading per-day SPY bars for F2 reclaim reconstruction ...")
    day_bars_by_date = load_all_day_bars()
    log(f"loaded {len(day_bars_by_date)} trading days of bars")

    episodes_by_variant = build_episodes(records, day_bars_by_date)
    for v, eps in episodes_by_variant.items():
        log(f"{v}: {len(eps)} candidate episodes (all families/directions pooled pre-cell-split)")

    rng = random.Random(RANDOM_SEED)
    cells: dict[str, dict] = {}
    cell_pvals: list[float] = []
    cell_keys: list[str] = []

    for variant, eps in episodes_by_variant.items():
        by_cell: dict[tuple, list[Episode]] = {}
        for ep in eps:
            by_cell.setdefault((ep.family, ep.kind), []).append(ep)
        for (family, kind), cell_eps in by_cell.items():
            break_direction = "bearish" if kind == "support" else "bullish"
            key = f"{variant}::{family}::{kind}(fade-of-{break_direction})"
            trades, nulls_r, nulls_b = [], [], []
            for ep in cell_eps:
                r = replay_episode(ep)
                if r is not None:
                    trades.append(r)
                nr = null_random_entry(ep, day_bars_by_date.get(ep.date, []), rng)
                if nr is not None:
                    nulls_r.append(nr)
                nb = null_break_direction(ep)
                if nb is not None:
                    nulls_b.append(nb)
            summ = summarize(trades)
            summ_r = summarize(nulls_r)
            summ_b = summarize(nulls_b)
            anchor = anchor_check(trades)
            beats_random = (summ.get("oos_expectancy", -1e9) or -1e9) > (summ_r.get("oos_expectancy", -1e9) or -1e9)
            beats_break_dir = (summ.get("oos_expectancy", -1e9) or -1e9) > (summ_b.get("oos_expectancy", -1e9) or -1e9)
            base_verdict = verdict_for_cell(summ)
            cells[key] = {
                "variant": variant, "family": family, "kind": kind,
                "break_direction_faded": break_direction, "fade_side": cell_eps[0].fade_side,
                "summary": summ, "null_random_entry": summ_r, "null_break_direction": summ_b,
                "beats_random_null_oos": beats_random, "beats_break_direction_null_oos": beats_break_dir,
                "anchor_check": anchor, "base_verdict": base_verdict,
            }
            if summ.get("n", 0) >= 20:
                cell_pvals.append(summ["p_value"])
                cell_keys.append(key)
            log(f"{key}: n={summ.get('n',0)} exp={summ.get('expectancy')} oos_exp={summ.get('oos_expectancy')} "
                f"wf={summ.get('wf')} p={summ.get('p_value')} base={base_verdict}")

    sig_flags = _bh_fdr(cell_pvals, alpha=0.10)
    sig_by_key = dict(zip(cell_keys, sig_flags))

    final_verdicts = {}
    for key, cell in cells.items():
        bv = cell["base_verdict"]
        if bv == "INCONCLUSIVE_UNDERPOWERED":
            final = "INCONCLUSIVE_UNDERPOWERED"
        elif bv == "FAIL":
            final = "FAIL"
        else:  # base PASS -> needs BH-FDR significance + beats both nulls
            sig = sig_by_key.get(key, False)
            if sig and cell["beats_random_null_oos"] and cell["beats_break_direction_null_oos"]:
                final = "PASS"
            else:
                final = "FAIL"
        cell["final_verdict"] = final
        final_verdicts[key] = final

    elapsed = _time.time() - t_start
    result = {
        "_doc": "TREND-FADE-PREREG -- ran the FROZEN prereg verbatim.",
        "prereg": str(PREREG_PATH.relative_to(REPO)),
        "generated_at_note": f"elapsed_sec={round(elapsed,1)}",
        "n_records_total": len(records),
        "cells": cells,
        "verdict_counts": {v: list(final_verdicts.values()).count(v)
                            for v in ("PASS", "FAIL", "INCONCLUSIVE_UNDERPOWERED")},
    }
    out_json = OUT_JSON
    out_md = OUT_MD
    if args.limit:
        out_json = OUT_JSON.with_name("_smoke_" + OUT_JSON.name)
        out_md = OUT_MD.with_name("_smoke_" + OUT_MD.name)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = ["# Trendline FADE entry battery -- TREND-FADE-PREREG (2026-07-14)", "",
             f"Prereg: `{PREREG_PATH.name}` (frozen, run verbatim). Elapsed: {round(elapsed,1)}s. "
             f"{len(records)} qualifying lines, {sum(len(v) for v in episodes_by_variant.values())} candidate episodes across 3 fade variants.",
             "",
             "Motivation: S1's break-battery killed CONTINUATION entries 12/12 but disclosed the opposite-direction "
             "null beating the real trade OOS in 10/12 cells. This battery promotes fading to a first-class, "
             "pre-registered hypothesis (own nulls, own pass bar) with 2 new variants S1 never tested.",
             "", "| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(cells.keys()):
        c = cells[key]
        s = c["summary"]
        sig = sig_by_key.get(key, None)
        sig_s = "n/a" if sig is None else ("YES" if sig else "no")
        beats = "both" if (c["beats_random_null_oos"] and c["beats_break_direction_null_oos"]) else (
            "partial" if (c["beats_random_null_oos"] or c["beats_break_direction_null_oos"]) else "neither")
        lines.append(f"| {key} | {s.get('n',0)} | {s.get('expectancy','-')} | {s.get('oos_expectancy','-')} | "
                      f"{s.get('wf','-')} | {s.get('p_value','-')} | {sig_s} | {beats} | **{c['final_verdict']}** |")
    lines.append("")
    lines.append(f"Verdict counts: {result['verdict_counts']}")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    log(f"DONE in {round(elapsed,1)}s. verdict_counts={result['verdict_counts']}")
    log(f"wrote {out_json} + {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
