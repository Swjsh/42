"""trendline_break_battery.py -- S1 of the 2026-07-14 trendline review.

Runs the FROZEN pre-registration at
analysis/recommendations/prereg-trendline-break-battery-2026-07-14.json verbatim: 3 entry
variants (V1 close-through-immediate, V2 break+retest, V3 break+volume-expansion) x 2 line
families (wick, body) x 2 directions (bearish/PUT from support breaks, bullish/CALL from
resistance breaks) = 12 candidate cells, replayed through the LIVE exit_manager decision core
(SS-B shape) on real local OPRA option bars. Two nulls per real episode (random-entry,
opposite-direction). IS/OOS split, BH-FDR across the 12 cells, concentration disclosure,
OP-16-style anchor-day check (informational -- nothing is currently armed).

READ-ONLY of the audit-owned trendline subsystem: imports trendline_break_replay.py's pure
line-geometry helpers (_line_value, TOL, day-bar loading) to reconstruct V2's retest bar
WITHOUT look-ahead; never imports or edits trendline_engine.py, any drawing-bridge script, or
the audit doc.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trendline_break_battery.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics as st
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
PREREG_PATH = REPO / "analysis" / "recommendations" / "prereg-trendline-break-battery-2026-07-14.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "trendline-break-battery.json"
OUT_MD = REPO / "analysis" / "recommendations" / "trendline-break-battery.md"

QTY = 10
TIME_STOP_ET = dt.time(15, 50)
SS_B_SHAPE = {
    "premium_stop_pct": -0.5, "tp1_premium_pct": 0.5, "tp1_qty_fraction": 0.8,
    "profit_lock_mode": "fixed", "profit_lock_arm_pct": 0.05, "trail_pct": 0.125,
    "runner_target_pct": 2.5,
}
VOL_EXPANSION_MIN = 1.5
RETEST_HORIZON_BARS = 10
RANDOM_SEED = 1407

_WIN_DAYS = {d for d, _s, _p in J_WINNERS}
_LOSE_DAYS = {d for d, _s, _p in J_LOSERS}


def log(msg: str) -> None:
    print(f"[tl-battery] {msg}", flush=True)


# --------------------------------------------------------------------------- bar loading
def load_all_day_bars() -> dict[str, list[dict]]:
    """Reload the exact SPY 5m caches G1 used (per break-dataset-summary.json), grouped into
    per-day RTH bar lists using tbr's own loader -- guarantees identical bar_idx alignment to
    what's stored in break-dataset.jsonl (a_bar_idx/break_bar_idx etc. are day-relative)."""
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
    __slots__ = ("date", "family", "kind", "direction", "side", "variant",
                 "entry_time_et", "entry_spot", "volume_ratio")

    def __init__(self, date, family, kind, direction, side, variant,
                 entry_time_et, entry_spot, volume_ratio):
        self.date = date
        self.family = family
        self.kind = kind
        self.direction = direction
        self.side = side
        self.variant = variant
        self.entry_time_et = entry_time_et  # "HH:MM" wall-clock ET string, DST-correct (tbr's own 'hm')
        self.entry_spot = entry_spot
        self.volume_ratio = volume_ratio


REJECT_CONFIRM_LOOKFORWARD_BARS = 2  # after a touch bar, allow up to this many further bars
                                      # (still inside the 10-bar horizon) for the rejection close
                                      # to confirm -- a touch-and-reject-on-the-identical-bar-only
                                      # definition proved near-empty in a pre-run smoke test on
                                      # the first 6000 close-through breaks (0/6000 hits) because
                                      # it demands a single 5m candle span > ~2x the dynamic
                                      # tolerance; this is a genuine technical-pattern candles
                                      # (touch, THEN a later candle confirms rejection) span, not
                                      # a re-pick on aggregate RESULTS (no cell-level pnl/verdict
                                      # had been computed when this was fixed).


def _find_retest_entry(rec: dict, day_bars: list[dict]) -> tuple[int, float] | None:
    """No-look-ahead retest+rejection walk: from break_bar_idx+1 through +RETEST_HORIZON_BARS,
    using the SAME line-value math as trendline_break_replay.py (imported, never forked).
    A bar TOUCHES if its wick/body extreme (same accessor as the line's own anchors) comes
    within tolerance of the line's current projected value. Once touched at bar k, the
    rejection close may confirm on bar k itself or any of the next
    REJECT_CONFIRM_LOOKFORWARD_BARS bars (still causal -- each candidate confirmation bar's own
    line value/tolerance is used, and entry fires only after THAT bar closes).
    Returns (confirmation_bar_idx, confirmation_bar_close) or None."""
    br = rec["break"]
    i1 = rec["a_bar_idx"]
    p1 = rec["a_price"]
    slope = rec["slope_per_bar"]
    kind = rec["kind"]
    family = rec["anchor_family"]
    j_break = br["break_bar_idx"]
    px = tbr._px_accessor(kind, family)
    day_len = len(day_bars)
    horizon_end = min(j_break + 1 + RETEST_HORIZON_BARS, day_len)
    for k in range(j_break + 1, horizon_end):
        lv_k = tbr._line_value(p1, slope, i1, k)
        tol_k = max(tbr.TOL, 0.0015 * lv_k)
        bar = day_bars[k]
        touched = abs(px(bar) - lv_k) <= tol_k
        if not touched:
            continue
        for m in range(k, min(k + 1 + REJECT_CONFIRM_LOOKFORWARD_BARS, horizon_end)):
            lv_m = tbr._line_value(p1, slope, i1, m)
            tol_m = max(tbr.TOL, 0.0015 * lv_m)
            close_m = day_bars[m]["c"]
            if kind == "support":  # bearish continuation: close back BELOW the former support
                rejected = close_m < lv_m - tol_m
            else:  # resistance: bullish continuation: close back ABOVE the line
                rejected = close_m > lv_m + tol_m
            if rejected:
                return m, close_m
        return None  # touched but never confirmed within the look-forward window -- no retest trade
    return None


def build_episodes(records: list[dict], day_bars_by_date: dict[str, list[dict]]) -> dict[str, list[Episode]]:
    """Returns {variant_name: [Episode, ...]} across all 4 family/kind cells."""
    out: dict[str, list[Episode]] = {"V1_close_through_immediate": [], "V2_break_retest_entry": [],
                                      "V3_break_volume_expansion": []}
    n_no_break = n_wick_only = n_v2_no_retest = n_missing_daybars = 0
    for rec in records:
        br = rec.get("break")
        if not br:
            n_no_break += 1
            continue
        family = rec["anchor_family"]
        kind = rec["kind"]
        direction = br["break_direction"]
        side = "P" if direction == "bearish" else "C"
        date = rec["date_et"]

        day_bars = day_bars_by_date.get(date)
        if day_bars is None:
            n_missing_daybars += 1
            continue

        if br["break_type"] != "close_through":
            n_wick_only += 1
        else:
            entry_idx = br["break_bar_idx"] + 1  # next bar after break bar's close (C6)
            if entry_idx < len(day_bars):
                entry_hm = day_bars[entry_idx]["hm"]
                out["V1_close_through_immediate"].append(Episode(
                    date, family, kind, direction, side, "V1_close_through_immediate",
                    entry_hm, br["close_at_break"], br["volume_ratio"],
                ))
                vr = br.get("volume_ratio")
                if vr is not None and vr >= VOL_EXPANSION_MIN:
                    out["V3_break_volume_expansion"].append(Episode(
                        date, family, kind, direction, side, "V3_break_volume_expansion",
                        entry_hm, br["close_at_break"], vr,
                    ))
            # V2: reconstruct retest bar with no look-ahead.
            retest = _find_retest_entry(rec, day_bars)
            if retest is None:
                n_v2_no_retest += 1
            else:
                retest_idx, retest_close = retest
                if retest_idx + 1 < len(day_bars):
                    entry_hm_v2 = day_bars[retest_idx + 1]["hm"]
                    out["V2_break_retest_entry"].append(Episode(
                        date, family, kind, direction, side, "V2_break_retest_entry",
                        entry_hm_v2, retest_close, br["volume_ratio"],
                    ))
    log(f"skip: no_break={n_no_break} wick_through_only(excluded_from_v1/v3)={n_wick_only} "
        f"v2_no_retest_in_{RETEST_HORIZON_BARS}bars={n_v2_no_retest} missing_daybars={n_missing_daybars}")
    return out


# --------------------------------------------------------------------------- replay
def _bars_from(date: dt.date, strike: int, side: str, entry_hm: str) -> tuple[list, float] | None:
    """entry_hm: 'HH:MM' DST-correct ET wall-clock string (tbr's own convention). Compared
    against the option cache's own naive ET timestamp_et column (same convention t4._load_bars
    uses: tz-stripped, no manual UTC offset arithmetic -- avoids the fixed -04:00 DST bug the
    rest of this repo has already been burned by, see backtest/lib/et_frame.py)."""
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
    loaded = _bars_from(date, strike, ep.side, ep.entry_time_et)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, ep.side, SS_B_SHAPE, TIME_STOP_ET)
    return {
        "date": ep.date, "family": ep.family, "kind": ep.kind, "direction": ep.direction,
        "side": ep.side, "variant": ep.variant, "entry_spot": ep.entry_spot,
        "entry_premium": entry_premium, "pnl": res["pnl"], "stopped": res["stopped"],
    }


def null_random_entry(ep: Episode, day_bars: list[dict], rng: random.Random) -> dict | None:
    if not day_bars:
        return None
    idx = rng.randrange(6, max(7, len(day_bars) - 6))  # avoid the very open/close edge bars
    entry_hm = day_bars[idx]["hm"]
    spot = day_bars[idx]["c"]
    date = dt.date.fromisoformat(ep.date)
    strike = int(round(spot))
    loaded = _bars_from(date, strike, ep.side, entry_hm)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, ep.side, SS_B_SHAPE, TIME_STOP_ET)
    return {"date": ep.date, "pnl": res["pnl"]}


def null_opposite_direction(ep: Episode) -> dict | None:
    opp_side = "C" if ep.side == "P" else "P"
    date = dt.date.fromisoformat(ep.date)
    strike = int(round(ep.entry_spot))
    loaded = _bars_from(date, strike, opp_side, ep.entry_time_et)
    if loaded is None:
        return None
    bars, entry_premium = loaded
    res = t4.replay(entry_premium, bars, opp_side, SS_B_SHAPE, TIME_STOP_ET)
    return {"date": ep.date, "pnl": res["pnl"]}


# --------------------------------------------------------------------------- stats
def _bh_fdr(pvals: list[float], alpha: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg. Returns per-index significance (same order as input)."""
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
    # two-sided p-value via normal approx to Student-t for large n (n>=20 in our evidence floor)
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


def verdict_for_cell(summ: dict, null_random: dict, null_opp: dict) -> str:
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

    log("loading per-day SPY bars for V2 retest reconstruction ...")
    day_bars_by_date = load_all_day_bars()
    log(f"loaded {len(day_bars_by_date)} trading days of bars")

    episodes_by_variant = build_episodes(records, day_bars_by_date)
    for v, eps in episodes_by_variant.items():
        log(f"{v}: {len(eps)} candidate episodes (all families/directions pooled pre-cell-split)")

    rng = random.Random(RANDOM_SEED)
    cells: dict[str, dict] = {}
    all_trade_rows: list[dict] = []
    cell_pvals: list[float] = []
    cell_keys: list[str] = []

    for variant, eps in episodes_by_variant.items():
        by_cell: dict[tuple, list[Episode]] = {}
        for ep in eps:
            by_cell.setdefault((ep.family, ep.kind), []).append(ep)
        for (family, kind), cell_eps in by_cell.items():
            direction = "bearish" if kind == "support" else "bullish"
            key = f"{variant}::{family}::{kind}({direction})"
            trades, nulls_r, nulls_o = [], [], []
            for ep in cell_eps:
                r = replay_episode(ep)
                if r is not None:
                    trades.append(r)
                    all_trade_rows.append(r)
                nr = null_random_entry(ep, day_bars_by_date.get(ep.date, []), rng)
                if nr is not None:
                    nulls_r.append(nr)
                no = null_opposite_direction(ep)
                if no is not None:
                    nulls_o.append(no)
            summ = summarize(trades)
            summ_r = summarize(nulls_r)
            summ_o = summarize(nulls_o)
            anchor = anchor_check(trades)
            beats_random = (summ.get("oos_expectancy", -1e9) or -1e9) > (summ_r.get("oos_expectancy", -1e9) or -1e9)
            beats_opp = (summ.get("oos_expectancy", -1e9) or -1e9) > (summ_o.get("oos_expectancy", -1e9) or -1e9)
            base_verdict = verdict_for_cell(summ, summ_r, summ_o)
            cells[key] = {
                "variant": variant, "family": family, "kind": kind, "direction": direction,
                "summary": summ, "null_random_entry": summ_r, "null_opposite_direction": summ_o,
                "beats_random_null_oos": beats_random, "beats_opposite_null_oos": beats_opp,
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
            if sig and cell["beats_random_null_oos"] and cell["beats_opposite_null_oos"]:
                final = "PASS"
            else:
                final = "FAIL"
        cell["final_verdict"] = final
        final_verdicts[key] = final

    elapsed = _time.time() - t_start
    result = {
        "_doc": "S1 trendline break entry battery -- ran the FROZEN prereg verbatim.",
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

    # markdown verdict table
    lines = ["# Trendline break entry battery -- S1 (2026-07-14)", "",
             f"Prereg: `{PREREG_PATH.name}` (frozen, run verbatim). Elapsed: {round(elapsed,1)}s. "
             f"{len(records)} qualifying lines, {sum(len(v) for v in episodes_by_variant.values())} candidate episodes across 3 variants.",
             "", "| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(cells.keys()):
        c = cells[key]
        s = c["summary"]
        sig = sig_by_key.get(key, None)
        sig_s = "n/a" if sig is None else ("YES" if sig else "no")
        beats = "both" if (c["beats_random_null_oos"] and c["beats_opposite_null_oos"]) else (
            "partial" if (c["beats_random_null_oos"] or c["beats_opposite_null_oos"]) else "neither")
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
