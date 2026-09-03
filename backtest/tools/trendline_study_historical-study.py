"""trendline_study_historical-study.py — T3 historical study, rising-support trendlines.

Frozen design: analysis/recommendations/prereg-trendline-rising-support-2026-09-03.md
Run this AFTER reading that file — every constant/rule here must match it verbatim.

Scratch tool (not a trading-path file). Imports crypto.lib.trendlines.find_swing_points
and crypto.lib.bar.Bar READ-ONLY (never edits them). No network/broker calls — reads only
backtest/data/spy_sip_cache/*.json (cached) and journal/trades.csv (read-only, for the
engine cross-reference cell).

Output: analysis/deep-research/2026-09-03-money/trendline-historical-study.json
"""
from __future__ import annotations

import csv
import json
import random
import statistics
import sys
import time as _time
import datetime as dt
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

CACHE_DIR = REPO_ROOT / "backtest" / "data" / "spy_sip_cache"
TRADES_CSV = REPO_ROOT / "journal" / "trades.csv"
OUT_JSON = REPO_ROOT / "analysis" / "deep-research" / "2026-09-03-money" / "trendline-historical-study.json"

DATE_START = "2026-06-26"
DATE_END = "2026-09-03"

PIVOT_WINDOW = 2
MIN_BARS_SINCE_ANCHOR2 = 3
TOL = {"5m": 0.15, "15m": 0.25}
GRAN_SEC = {"5m": 300, "15m": 900}
HORIZON_BARS = {"5m": {15: 3, 30: 6, 60: 12}, "15m": {15: 1, 30: 2, 60: 4}}
HORIZONS = (15, 30, 60)
B_BOOT = 2000
SEED = 42

BAR_SETS = ["5m_premkt", "5m_rth", "15m_premkt", "15m_rth"]
ANCHOR_MODES = ["wick", "body"]
PRIMARY = ("5m_premkt", "wick")


# ---------------------------------------------------------------------------
# Data loading / aggregation
# ---------------------------------------------------------------------------

def list_sessions() -> list[str]:
    dates = []
    for f in sorted(CACHE_DIR.glob("spy_1m_*.json")):
        d = f.stem.replace("spy_1m_", "")
        if DATE_START <= d <= DATE_END:
            if (CACHE_DIR / f"spy_5m_{d}.json").exists():
                dates.append(d)
    return dates


def load_bars(path: Path) -> list[dict]:
    d = json.load(open(path, encoding="utf-8"))
    return d["bars"]


def parse_t(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t)


def to_barset(bars_1m: list[dict], bars_5m: list[dict], date: str, tf: str, rth: bool) -> list[dict]:
    """Return a list of {t_dt, o,h,l,c,v} for the given timeframe/scope, sorted."""
    if tf == "5m":
        src = bars_5m
        out = []
        for b in src:
            ts = parse_t(b["t"])
            if rth and ts.time() < dt.time(9, 30):
                continue
            out.append({"t_dt": ts, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b.get("v", 0.0)})
        return out
    if tf == "15m":
        session_date = dt.date.fromisoformat(date)
        buckets: dict[tuple[int, int], list[dict]] = {}
        for b in bars_1m:
            ts = parse_t(b["t"])
            if rth and ts.time() < dt.time(9, 30):
                continue
            minute_of_day = ts.hour * 60 + ts.minute
            bucket_start = (minute_of_day // 15) * 15
            key = divmod(bucket_start, 60)
            buckets.setdefault(key, []).append(b)
        out = []
        for key in sorted(buckets.keys()):
            group = buckets[key]
            if len(group) < 15:
                continue  # only full 15-bar buckets (no partial trailing bucket)
            group_sorted = sorted(group, key=lambda x: x["t"])
            bh, bm = key
            t0 = dt.datetime.combine(session_date, dt.time(bh, bm))
            out.append({
                "t_dt": t0,
                "o": group_sorted[0]["o"],
                "h": max(g["h"] for g in group_sorted),
                "l": min(g["l"] for g in group_sorted),
                "c": group_sorted[-1]["c"],
                "v": sum(g.get("v", 0.0) for g in group_sorted),
            })
        return out
    raise ValueError(tf)


# ---------------------------------------------------------------------------
# Pivot / line / event detection (per prereg sections 2-4)
# ---------------------------------------------------------------------------

def build_bar_objects(bar_dicts: list[dict], anchor_mode: str, tf: str) -> tuple[Bar, ...]:
    gran = GRAN_SEC[tf]
    out = []
    for b in bar_dicts:
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        if anchor_mode == "body":
            top, bot = max(o, c), min(o, c)
        else:
            top, bot = h, l
        out.append(Bar(
            open_time=b["t_dt"].replace(tzinfo=dt.timezone.utc),
            open=o, high=top, low=bot, close=c,
            volume=b.get("v", 0.0), granularity_seconds=gran, source="trendline_study",
        ))
    return tuple(out)


def detect_session(bar_dicts: list[dict], tf: str, anchor_mode: str) -> dict | None:
    """Returns None if no valid rising-support line, else a dict with anchors/events."""
    n = len(bar_dicts)
    if n < 6:
        return None
    tol = TOL[tf]
    view = build_bar_objects(bar_dicts, anchor_mode, tf)
    swings = find_swing_points(view, window=PIVOT_WINDOW, inclusive_right=True)
    lows = sorted([s for s in swings if s.kind == "swing_low"], key=lambda s: s.bar_index)
    if len(lows) < 2:
        return None
    anchor_a, anchor_b = lows[0], lows[1]
    if not (anchor_b.price > anchor_a.price):
        return None  # not rising -- no line (non-greedy, per prereg)

    slope = (anchor_b.price - anchor_a.price) / (anchor_b.bar_index - anchor_a.bar_index)

    def line_value(j: int) -> float:
        return anchor_a.price + slope * (j - anchor_a.bar_index)

    eligible_start = anchor_b.bar_index + MIN_BARS_SINCE_ANCHOR2
    touches: list[int] = []
    break_idx: int | None = None
    for j in range(eligible_start, n):
        lv = line_value(j)
        c = bar_dicts[j]["c"]
        if anchor_mode == "body":
            lo = min(bar_dicts[j]["o"], bar_dicts[j]["c"])
        else:
            lo = bar_dicts[j]["l"]
        if c < lv - tol:
            break_idx = j
            break  # line dies here -- no touches/breaks evaluated after
        if lo <= lv + tol and c > lv:
            touches.append(j)

    return {
        "anchor_a_idx": anchor_a.bar_index, "anchor_a_price": anchor_a.price,
        "anchor_a_t": bar_dicts[anchor_a.bar_index]["t_dt"].isoformat(),
        "anchor_b_idx": anchor_b.bar_index, "anchor_b_price": anchor_b.price,
        "anchor_b_t": bar_dicts[anchor_b.bar_index]["t_dt"].isoformat(),
        "slope": slope, "touches": touches, "break_idx": break_idx,
        "line_value_fn": line_value,
        "n_bars": n,
    }


# ---------------------------------------------------------------------------
# Outcome metrics (prereg section 5)
# ---------------------------------------------------------------------------

def event_outcomes(bar_dicts: list[dict], j: int, tf: str, direction: str) -> dict:
    """direction: 'up' (touch) or 'down' (break). Returns per-horizon outcomes, None if
    the horizon's forward window doesn't fully fit in this session's cached bars."""
    n = len(bar_dicts)
    out = {}
    for H in HORIZONS:
        N = HORIZON_BARS[tf][H]
        if j + N >= n:
            out[str(H)] = None
            continue
        c0 = bar_dicts[j]["c"]
        cN = bar_dicts[j + N]["c"]
        window = bar_dicts[j + 1: j + N + 1]
        if direction == "up":
            c2c = cN - c0
            mfe = max(b["h"] for b in window) - c0
        else:
            c2c = c0 - cN
            mfe = c0 - min(b["l"] for b in window)
        out[str(H)] = {"c2c": c2c, "favorable": c2c > 0, "mfe": mfe}
    return out


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def clustered_bootstrap(events_by_session: dict[str, list[dict]], horizon: int, rng: random.Random,
                         b: int = B_BOOT) -> dict:
    """events_by_session: date -> list of outcome dicts (already filtered to non-None for
    this horizon). Returns point estimate + CI for rate and mean_move."""
    sessions = list(events_by_session.keys())
    pooled = [e for v in events_by_session.values() for e in v]
    n = len(pooled)
    if n == 0:
        return {"n": 0, "n_sessions": 0, "rate": None, "rate_ci": None, "mean_move": None, "mean_move_ci": None}
    point_rate = sum(1 for e in pooled if e["favorable"]) / n
    point_mean = statistics.mean(e["c2c"] for e in pooled)
    if not sessions:
        return {"n": n, "n_sessions": 0, "rate": point_rate, "rate_ci": None,
                "mean_move": point_mean, "mean_move_ci": None}
    rates, means = [], []
    for _ in range(b):
        draw = [rng.choice(sessions) for _ in sessions]
        pool = [e for s in draw for e in events_by_session.get(s, [])]
        if not pool:
            continue
        rates.append(sum(1 for e in pool if e["favorable"]) / len(pool))
        means.append(statistics.mean(e["c2c"] for e in pool))
    rates.sort(); means.sort()

    def pct(arr, p):
        if not arr:
            return None
        idx = min(len(arr) - 1, max(0, int(round(p * (len(arr) - 1)))))
        return arr[idx]

    return {
        "n": n, "n_sessions": len(events_by_session),
        "rate": point_rate, "rate_ci": [pct(rates, 0.025), pct(rates, 0.975)], "rate_boot_draws": len(rates),
        "mean_move": point_mean, "mean_move_ci": [pct(means, 0.025), pct(means, 0.975)],
    }


def concentration(events_by_session: dict[str, list[dict]]) -> dict:
    counts = sorted(((s, len(v)) for s, v in events_by_session.items()), key=lambda x: -x[1])
    total = sum(c for _, c in counts)
    top3 = sum(c for _, c in counts[:3])
    return {
        "total_events": total,
        "n_sessions_with_events": len(counts),
        "top3_sessions": [{"date": s, "n": c} for s, c in counts[:3]],
        "top3_share": (top3 / total) if total else None,
    }


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------

def run() -> dict:
    t_start = _time.time()
    sessions = list_sessions()

    # per-config raw detection, keyed by (bar_set, anchor_mode) -> date -> detect_session result
    detections: dict[tuple[str, str], dict[str, dict | None]] = {}
    bar_data: dict[tuple[str, str], dict[str, list[dict]]] = {}  # (bar_set) -> date -> bar_dicts (mode-independent for wick; body handled separately for events but bar_dicts o/h/l/c are raw regardless -- events use raw dict + mode flag)

    for bs in BAR_SETS:
        tf, scope = bs.split("_")
        rth = (scope == "rth")
        bar_data[bs] = {}
        for date in sessions:
            bars_1m = load_bars(CACHE_DIR / f"spy_1m_{date}.json")
            bars_5m = load_bars(CACHE_DIR / f"spy_5m_{date}.json")
            bar_data[bs][date] = to_barset(bars_1m, bars_5m, date, tf, rth)

    for bs in BAR_SETS:
        tf = bs.split("_")[0]
        for mode in ANCHOR_MODES:
            key = (bs, mode)
            detections[key] = {}
            for date in sessions:
                bd = bar_data[bs][date]
                detections[key][date] = detect_session(bd, tf, mode)

    # ---- per-config stats: touches (up) and breaks (down) ----
    rng = random.Random(SEED)
    config_results = {}
    all_touch_events_for_baseline: dict[tuple[str, str], dict[str, list[tuple[int, str]]]] = {}
    # baseline needs: for each (bar_set, mode), a set of (date, bar_index) that are event bars (touch OR break)
    for bs in BAR_SETS:
        tf = bs.split("_")[0]
        for mode in ANCHOR_MODES:
            key = (bs, mode)
            det = detections[key]

            # collect event bars (touch + break) for baseline exclusion
            event_bar_set: set[tuple[str, int]] = set()
            touches_by_session: dict[str, list[int]] = {}
            breaks_by_session: dict[str, list[int]] = {}
            for date, d in det.items():
                if d is None:
                    continue
                if d["touches"]:
                    touches_by_session[date] = d["touches"]
                    for j in d["touches"]:
                        event_bar_set.add((date, j))
                if d["break_idx"] is not None:
                    breaks_by_session[date] = [d["break_idx"]]
                    event_bar_set.add((date, d["break_idx"]))

            n_sessions_with_line = sum(1 for d in det.values() if d is not None)

            # outcomes per horizon
            touch_outcomes_by_h: dict[int, dict[str, list[dict]]] = {H: {} for H in HORIZONS}
            for date, idxs in touches_by_session.items():
                bd = bar_data[bs][date]
                for j in idxs:
                    oc = event_outcomes(bd, j, tf, "up")
                    for H in HORIZONS:
                        if oc[str(H)] is not None:
                            touch_outcomes_by_h[H].setdefault(date, []).append(oc[str(H)])

            break_outcomes_by_h: dict[int, dict[str, list[dict]]] = {H: {} for H in HORIZONS}
            for date, idxs in breaks_by_session.items():
                bd = bar_data[bs][date]
                for j in idxs:
                    oc = event_outcomes(bd, j, tf, "down")
                    for H in HORIZONS:
                        if oc[str(H)] is not None:
                            break_outcomes_by_h[H].setdefault(date, []).append(oc[str(H)])

            # baseline pool: bars at same HH:MM as any touch (resp. break) event, across ALL
            # sessions of this bar_set, excluding event bars, with full horizon available.
            def baseline_stats(event_times_hhmm: set[str], direction: str, H: int) -> dict:
                N = HORIZON_BARS[tf][H]
                pooled = []
                for date, bd in bar_data[bs].items():
                    n = len(bd)
                    for j, b in enumerate(bd):
                        hhmm = b["t_dt"].strftime("%H:%M")
                        if hhmm not in event_times_hhmm:
                            continue
                        if (date, j) in event_bar_set:
                            continue
                        if j + N >= n:
                            continue
                        c0 = bd[j]["c"]; cN = bd[j + N]["c"]
                        window = bd[j + 1: j + N + 1]
                        if direction == "up":
                            c2c = cN - c0
                        else:
                            c2c = c0 - cN
                        pooled.append(c2c)
                if not pooled:
                    return {"n": 0, "rate": None, "mean_move": None}
                rate = sum(1 for x in pooled if x > 0) / len(pooled)
                return {"n": len(pooled), "rate": rate, "mean_move": statistics.mean(pooled)}

            touch_hhmm = {bar_data[bs][date][j]["t_dt"].strftime("%H:%M")
                          for date, idxs in touches_by_session.items() for j in idxs}
            break_hhmm = {bar_data[bs][date][j]["t_dt"].strftime("%H:%M")
                          for date, idxs in breaks_by_session.items() for j in idxs}

            touch_stats_by_h = {}
            break_stats_by_h = {}
            for H in HORIZONS:
                touch_stats_by_h[H] = clustered_bootstrap(touch_outcomes_by_h[H], H, rng)
                touch_stats_by_h[H]["baseline"] = baseline_stats(touch_hhmm, "up", H)
                break_stats_by_h[H] = clustered_bootstrap(break_outcomes_by_h[H], H, rng)
                break_stats_by_h[H]["baseline"] = baseline_stats(break_hhmm, "down", H)

            config_results[f"{bs}|{mode}"] = {
                "bar_set": bs, "anchor_mode": mode,
                "n_sessions_total": len(sessions),
                "n_sessions_with_line": n_sessions_with_line,
                "touch": {
                    "by_horizon": {str(H): touch_stats_by_h[H] for H in HORIZONS},
                    "concentration": concentration(touches_by_session),
                },
                "break": {
                    "by_horizon": {str(H): break_stats_by_h[H] for H in HORIZONS},
                    "concentration": concentration(breaks_by_session),
                },
            }

    # ---- decision rule evaluation (primary config, H=60) ----
    prim_bs, prim_mode = PRIMARY
    prim_key = f"{prim_bs}|{prim_mode}"
    prim = config_results[prim_key]
    decision = {}
    for etype in ("touch", "break"):
        h60 = prim[etype]["by_horizon"]["60"]
        n = h60["n"] or 0
        n_sessions = h60["n_sessions"] or 0
        baseline_rate = h60["baseline"]["rate"]
        rate_ci = h60.get("rate_ci")
        mean_ci = h60.get("mean_move_ci")
        n_ok = n >= 40 and n_sessions >= 25
        rate_ok = (rate_ci is not None and baseline_rate is not None and rate_ci[0] is not None
                   and rate_ci[0] > baseline_rate)
        mean_ok = (mean_ci is not None and mean_ci[0] is not None and mean_ci[0] > 0)
        decision[etype] = {
            "n": n, "n_sessions": n_sessions, "n_ok (>=40 & >=25 sessions)": n_ok,
            "baseline_rate": baseline_rate, "rate_ci_lower": rate_ci[0] if rate_ci else None,
            "rate_clears_baseline": rate_ok,
            "mean_move_ci_lower": mean_ci[0] if mean_ci else None, "mean_move_positive": mean_ok,
            "VERDICT": "WORTH BUILDING" if (n_ok and rate_ok and mean_ok) else "NOT SUPPORTED",
        }

    # ---- today's exhibit row (2026-09-03), all configs ----
    today = "2026-09-03"
    today_rows = []
    for bs in BAR_SETS:
        for mode in ANCHOR_MODES:
            d = detections[(bs, mode)].get(today)
            tf = bs.split("_")[0]
            if d is None:
                today_rows.append({"bar_set": bs, "anchor_mode": mode, "line": None})
                continue
            bd = bar_data[bs][today]
            touch_times = [bd[j]["t_dt"].strftime("%H:%M") for j in d["touches"]]
            break_time = bd[d["break_idx"]]["t_dt"].strftime("%H:%M") if d["break_idx"] is not None else None
            today_rows.append({
                "bar_set": bs, "anchor_mode": mode,
                "anchor_a": {"t": d["anchor_a_t"], "price": round(d["anchor_a_price"], 2)},
                "anchor_b": {"t": d["anchor_b_t"], "price": round(d["anchor_b_price"], 2)},
                "slope_per_bar": round(d["slope"], 5),
                "touch_times": touch_times,
                "break_time": break_time,
            })

    # ---- engine cross-reference (prereg section 9) ----
    bull_entries = []
    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["setup"] != "BULLISH_RECLAIM_RIDE_THE_RIBBON":
                continue
            if not (DATE_START <= row["date"] <= DATE_END):
                continue
            bull_entries.append(row)
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in bull_entries:
        groups.setdefault((r["date"], r["time_entry"]), []).append(r)

    prim_touches_by_date = {date: detections[PRIMARY][date]["touches"]
                             for date in sessions if detections[PRIMARY][date] is not None}
    prim_bar_data = bar_data[prim_bs]

    matched_pnls: dict[str, list[float]] = {}
    unmatched_pnls: dict[str, list[float]] = {}
    match_detail = []
    for (date, time_entry), rows in groups.items():
        try:
            hh, mm, ss = time_entry.split(":")
            entry_dt = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(int(hh), int(mm), int(ss)))
        except Exception:
            continue
        pnl = 0.0
        ok = True
        for r in rows:
            v = r["dollar_pnl"]
            if v in ("", "N/A"):
                ok = False
                break
            pnl += float(v)
        if not ok:
            continue
        touches = prim_touches_by_date.get(date, [])
        bd = prim_bar_data.get(date, [])
        matched = False
        best_dt_diff = None
        for j in touches:
            t_dt = bd[j]["t_dt"]
            diff_min = abs((t_dt - entry_dt).total_seconds()) / 60.0
            if diff_min <= 10.0:
                matched = True
                best_dt_diff = diff_min if best_dt_diff is None else min(best_dt_diff, diff_min)
        if matched:
            matched_pnls.setdefault(date, []).append(pnl)
        else:
            unmatched_pnls.setdefault(date, []).append(pnl)
        match_detail.append({"date": date, "time_entry": time_entry, "pnl": pnl, "matched_third_touch": matched,
                              "min_diff_minutes": round(best_dt_diff, 1) if best_dt_diff is not None else None})

    def pnl_cluster_stats(pnls_by_session: dict[str, list[float]]) -> dict:
        pooled = [x for v in pnls_by_session.values() for x in v]
        n = len(pooled)
        if n == 0:
            return {"n": 0, "n_sessions": 0, "mean_pnl": None, "mean_pnl_ci": None}
        point = statistics.mean(pooled)
        sessions_ = list(pnls_by_session.keys())
        means = []
        rng2 = random.Random(SEED + 1)
        for _ in range(B_BOOT):
            draw = [rng2.choice(sessions_) for _ in sessions_]
            pool = [x for s in draw for x in pnls_by_session.get(s, [])]
            if pool:
                means.append(statistics.mean(pool))
        means.sort()

        def pct(arr, p):
            if not arr:
                return None
            idx = min(len(arr) - 1, max(0, int(round(p * (len(arr) - 1)))))
            return arr[idx]
        return {"n": n, "n_sessions": len(pnls_by_session), "mean_pnl": point,
                "mean_pnl_ci": [pct(means, 0.025), pct(means, 0.975)]}

    engine_xref = {
        "n_entry_events_total": len(match_detail),
        "matched": pnl_cluster_stats(matched_pnls),
        "unmatched": pnl_cluster_stats(unmatched_pnls),
        "note": "matched = a PRIMARY-config (5m_premkt, wick) rising-support TOUCH fired "
                "within +/-10 min of the engine's actual BULLISH_RECLAIM_RIDE_THE_RIBBON "
                "entry (journal/trades.csv). The engine's live trigger geometry "
                "(detect_trendline_reclaim_bullish, backtest/lib/filters.py:1101) is a "
                "descending-resistance breakout through swing HIGHS, NOT this rising-support "
                "line -- this cell measures coincidence, not mechanism agreement.",
    }

    elapsed = _time.time() - t_start

    return {
        "prereg": "analysis/recommendations/prereg-trendline-rising-support-2026-09-03.md",
        "generated_at_note": "stamp via et_clock.py at report-write time (not inside this script)",
        "n_sessions_in_universe": len(sessions),
        "sessions": sessions,
        "config_results": config_results,
        "primary_config": f"{prim_bs}|{prim_mode}",
        "decision_rule_evaluation": decision,
        "today_exhibit_2026_09_03": today_rows,
        "engine_cross_reference": engine_xref,
        "engine_cross_reference_detail": match_detail,
        "runtime_seconds": round(elapsed, 2),
    }


if __name__ == "__main__":
    result = run()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"wrote {OUT_JSON} in {result['runtime_seconds']}s, {result['n_sessions_in_universe']} sessions")
