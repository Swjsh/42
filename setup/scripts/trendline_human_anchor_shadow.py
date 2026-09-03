#!/usr/bin/env python
"""trendline_human_anchor_shadow.py -- FORWARD + BACKFILLED shadow for the rising-support
"human anchor" trendline rule (queue TRENDLINE-RISING-SUPPORT-HUMAN-ANCHOR-SHADOW).

BACKGROUND. T2 (trendline-today-exhibit.md) showed the repo's pivot-anchored detector
(min_touches=3, strict fractal-neighbor pivots) could not construct J's own 2026-09-03
rising support line (5m 08:20->10:10 / 15m 08:15->10:00) at the moment he drew it, with or
without premarket bars. T3 (trendline-historical-study.md) then tested the LITERAL "first
two confirmed pivot lows of the session" rule over 45 sessions and REFUTED it (3 of 4
falsifier conditions fired) -- but T3's own section 6 found J is not picking the
chronologically-first two pivots at all: he is picking "the low that ends the pre-move
decline, and the first higher low after it" -- a DIFFERENT, untested hypothesis. This
module is the frozen instrument for that different hypothesis, per
analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md --
read that file for every exact rule; this module implements it, does not restate it.

THE ANCHOR RULE (frozen, prereg section 3 -- summarized, prereg is authoritative):
  A = the running MINIMUM low of the session so far (not a pivot -- a raw running min).
      Resets whenever a new bar undercuts it (killing any active line).
  B = the first swing-low pivot (window k=2, inclusive-right) confirmed AFTER A was set,
      priced above A, at least MIN_GAP bars after A (6 on 5m / 2 on 15m -- matched
      wall-clock gap, not matched bar-count).
  The line through A/B is a candidate the INSTANT B confirms -- no third touch required
  (the explicit, named difference from backtest/lib/trendline_detector.py's min_touches=3
  default; that module is NOT imported here -- this is a from-scratch reimplementation of
  a different rule, never wired to any live/shadow trigger).
  Re-anchor (line death, new search restarts) on EITHER: a new lower low prints (A resets),
  OR the line breaks (A stays, B search restarts from the same A).

EVENTS (prereg section 4): TOUCH = |low-line|<=tol AND close>line. BREAK = first
close < line-tol. tol = $0.20 (5m) / $0.30 (15m).

OUTCOMES (prereg section 5): close-to-close move + max-favourable-excursion over the next
15/30/60 min in the event's implied direction, vs a time-of-day baseline pooled from every
non-event bar at the same HH:MM across all sessions of that bar_set.

BACKFILL (prereg section 6): runs ONCE over every session with both a spy_1m and spy_5m
cache file present (no date floor). Every row is flagged in_sample=true when
date_et <= "2026-09-03", in_sample=false afterward. Idempotent per (date_et, bar_set,
anchor_mode) via a `session_marker` row -- a session/config already marked is never
re-processed. The in-sample prior is reported every run but NEVER counts toward the
forward decision-rule bar in prereg section 7 (n_sessions_forward / n_events_forward use
in_sample=false rows only).

SHADOW ONLY, FOREVER (prereg section 9): this instrument imports nothing from
backtest/lib/filters.py or trendline_detector.py, calls no broker, and is never wired to
any live or paper trigger. Its own decision rule (prereg section 7) caps out at "proceeds
to a real ratification pass" -- a separate, later, explicitly-authorized step this file
does not itself perform -- and even that is gated to not read a verdict before 2026-10-30.

COST: $0. Pure Python stdlib + one read-only import (crypto/lib/trendlines.py,
crypto/lib/bar.py -- swing-point detection only, never edited). No network/broker calls;
reads only backtest/data/spy_sip_cache/*.json (cached).

Outputs:
  analysis/recommendations/trendline-human-anchor-ledger.jsonl   append-only, 3 row kinds
                                                                  (session_marker, line,
                                                                  event), deduped on
                                                                  (date_et, bar_set,
                                                                  anchor_mode) at the
                                                                  session_marker level
  analysis/recommendations/trendline-human-anchor-summary.json   per-config aggregates +
                                                                  gate status
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

CACHE_DIR = REPO / "backtest" / "data" / "spy_sip_cache"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "trendline-human-anchor-ledger.jsonl"
SUMMARY = OUT_DIR / "trendline-human-anchor-summary.json"
PREREG_REL = "analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md"

IN_SAMPLE_CUTOFF = "2026-09-03"     # dates <= this are in-sample backfill (prereg section 6)
HARD_DATE_GATE = "2026-10-30"       # no verdict read before this, even if the bar is met

PIVOT_WINDOW = 2                     # k, both timeframes (prereg section 3)
MIN_GAP_BARS = {"5m": 6, "15m": 2}   # min bars between A and B (prereg section 3)
TOL = {"5m": 0.20, "15m": 0.30}      # touch/break tolerance (prereg section 4)
GRAN_SEC = {"5m": 300, "15m": 900}
HORIZON_BARS = {"5m": {15: 3, 30: 6, 60: 12}, "15m": {15: 1, 30: 2, 60: 4}}
HORIZONS = (15, 30, 60)
B_BOOT = 1000   # trimmed from the 2000 sibling-clock default -- see _clustered_bootstrap's
                # docstring: this instrument's event counts (100K+) make 2000 draws too slow
                # to finish in the nightly time budget; 1000 is still ample resolution for a
                # 2.5th-percentile read
SEED = 20260903

BAR_SETS = ["5m_premkt", "5m_rth", "15m_premkt", "15m_rth"]
ANCHOR_MODES = ["wick", "body"]
PRIMARY_BAR_SETS = ["5m_premkt", "15m_premkt"]     # prereg section 2 / section 7
PRIMARY_MODE = "wick"
BAR_MIN_SESSIONS_FORWARD = 25
BAR_MIN_EVENTS_FORWARD = 40
FALSIFIER_TOP3_CONCENTRATION = 0.60


# ------------------------------------------------------------------------------------------
# bar aggregation -- identical convention to trendline_study_today-exhibit.py /
# trendline_study_historical-study.py (verified there 146/148 exact match vs cached 5m file)
# ------------------------------------------------------------------------------------------
def list_sessions() -> list[str]:
    """Every session with BOTH a 1m and 5m cache file present. No date floor -- 'every
    cached session' per the prereg, not a fixed window."""
    dates = []
    for f in sorted(CACHE_DIR.glob("spy_1m_*.json")):
        d = f.stem.replace("spy_1m_", "")
        if (CACHE_DIR / f"spy_5m_{d}.json").exists():
            dates.append(d)
    return dates


def load_bars(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["bars"]


def parse_t(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t)


def to_barset(bars_1m: list[dict], bars_5m: list[dict], date: str, tf: str, rth: bool) -> list[dict]:
    """Return a list of {t_dt,o,h,l,c,v} for the given timeframe/scope, sorted ascending."""
    if tf == "5m":
        out = []
        for b in bars_5m:
            ts = parse_t(b["t"])
            if rth and ts.time() < dt.time(9, 30):
                continue
            out.append({"t_dt": ts, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                        "v": b.get("v", 0.0)})
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
            group = sorted(buckets[key], key=lambda x: x["t"])
            if len(group) < 15:
                continue          # only full 15-bar buckets (no partial trailing bucket)
            bh, bm = key
            out.append({
                "t_dt": dt.datetime.combine(session_date, dt.time(bh, bm)),
                "o": group[0]["o"], "h": max(g["h"] for g in group),
                "l": min(g["l"] for g in group), "c": group[-1]["c"],
                "v": sum(g.get("v", 0.0) for g in group),
            })
        return out
    raise ValueError(tf)


def build_bar_objects(bar_dicts: list[dict], anchor_mode: str, tf: str) -> tuple[Bar, ...]:
    """Bar objects with high/low swapped for body-min-of-open-close under mode='body' --
    swing detection then runs identically for either mode via the same find_swing_points
    call (doctrine: ALL-wick or ALL-body, never mixed within one line)."""
    gran = GRAN_SEC[tf]
    out = []
    for b in bar_dicts:
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        if anchor_mode == "body":
            top, bot = max(o, c), min(o, c)
        else:
            top, bot = h, l
        out.append(Bar(open_time=b["t_dt"].replace(tzinfo=dt.timezone.utc), open=o,
                        high=top, low=bot, close=c, volume=b.get("v", 0.0),
                        granularity_seconds=gran, source="trendline_human_anchor_shadow"))
    return tuple(out)


def _get_low(bar_dicts: list[dict], i: int, mode: str) -> float:
    b = bar_dicts[i]
    return b["l"] if mode == "wick" else min(b["o"], b["c"])


# ------------------------------------------------------------------------------------------
# the anchor rule + event detection (prereg sections 3-4) -- see module docstring
# ------------------------------------------------------------------------------------------
def detect_session_lines(bar_dicts: list[dict], tf: str, mode: str) -> list[dict]:
    """Returns a list of line dicts (dead or still-active-at-session-end), each carrying
    its own touches/break. A/B tracked as a running state machine walking the session
    bar-by-bar -- see module docstring for the exact re-anchor semantics."""
    n = len(bar_dicts)
    min_gap = MIN_GAP_BARS[tf]
    tol = TOL[tf]
    k = PIVOT_WINDOW
    if n < 2 * k + min_gap + 1:
        return []

    bars_obj = build_bar_objects(bar_dicts, mode, tf)
    swings = find_swing_points(bars_obj, window=k, inclusive_right=True)
    lows = sorted((s for s in swings if s.kind == "swing_low"), key=lambda s: s.bar_index)
    pivot_confirm_at = {s.bar_index + k: s for s in lows}   # confirmed exactly when i == bar_index+k

    lines: list[dict] = []
    a_idx: int | None = None
    a_price: float | None = None
    active: dict | None = None

    def line_value(a_i: int, a_p: float, b_i: int, b_p: float, j: int) -> float:
        slope = (b_p - a_p) / (b_i - a_i)
        return a_p + slope * (j - a_i)

    for i in range(n):
        cur_low = _get_low(bar_dicts, i, mode)

        # 1. running-min A tracking -- a new lower low kills any active line
        if a_idx is None or cur_low < a_price:
            a_idx, a_price = i, cur_low
            if active is not None:
                active["end_reason"] = "reanchor_lower_low"
                active["end_idx"] = i
                lines.append(active)
                active = None

        # 2. a pivot confirming exactly at this bar may become the new B
        pivot = pivot_confirm_at.get(i)
        if pivot is not None and active is None and a_idx is not None:
            if (pivot.bar_index > a_idx and pivot.price > a_price
                    and (pivot.bar_index - a_idx) >= min_gap):
                active = {"a_idx": a_idx, "a_price": a_price, "b_idx": pivot.bar_index,
                          "b_price": pivot.price, "confirm_idx": i, "touches": [],
                          "break_idx": None, "end_reason": None, "end_idx": None}

        # 3. evaluate touch/break for an active, confirmed line at this bar
        if active is not None and i >= active["confirm_idx"]:
            lv = line_value(active["a_idx"], active["a_price"], active["b_idx"],
                             active["b_price"], i)
            close = bar_dicts[i]["c"]
            if close < lv - tol:
                active["break_idx"] = i
                active["end_reason"] = "break"
                active["end_idx"] = i
                lines.append(active)
                active = None
            elif abs(cur_low - lv) <= tol and close > lv:
                active["touches"].append(i)

    if active is not None:
        active["end_reason"] = "session_end_still_active"
        active["end_idx"] = n - 1
        lines.append(active)
    return lines


def _outcome(bar_dicts: list[dict], j: int, tf: str, direction: str, horizon: int) -> dict | None:
    n = len(bar_dicts)
    N = HORIZON_BARS[tf][horizon]
    if j + N >= n:
        return None
    c0 = bar_dicts[j]["c"]
    cN = bar_dicts[j + N]["c"]
    window = bar_dicts[j + 1: j + N + 1]
    if direction == "up":
        c2c = cN - c0
        mfe = max(b["h"] for b in window) - c0
    else:
        c2c = c0 - cN
        mfe = c0 - min(b["l"] for b in window)
    return {"c2c": c2c, "favorable": c2c > 0, "mfe": mfe}


# ------------------------------------------------------------------------------------------
# ledger I/O -- 3 row kinds, deduped on (date_et, bar_set, anchor_mode) via session_marker
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn last line must never kill the accrual
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


def _processed_session_configs(rows: list[dict]) -> set[tuple[str, str, str]]:
    return {(r["date_et"], r["bar_set"], r["anchor_mode"])
            for r in rows if r.get("kind") == "session_marker"}


def process_session_config(date: str, bars_1m: list[dict], bars_5m: list[dict],
                            bar_set: str, mode: str) -> list[dict]:
    """Returns the new ledger rows for one (date, bar_set, anchor_mode) triple: one
    session_marker, one `line` row per detected line, one `event` row per touch/break."""
    tf, scope = bar_set.split("_")
    rth = (scope == "rth")
    bd = to_barset(bars_1m, bars_5m, date, tf, rth)
    in_sample = date <= IN_SAMPLE_CUTOFF

    lines = detect_session_lines(bd, tf, mode)
    rows: list[dict] = []
    n_touches = 0
    n_breaks = 0

    for li, ln in enumerate(lines):
        a_t = bd[ln["a_idx"]]["t_dt"].isoformat()
        b_t = bd[ln["b_idx"]]["t_dt"].isoformat()
        break_t = bd[ln["break_idx"]]["t_dt"].isoformat() if ln["break_idx"] is not None else None
        rows.append({
            "kind": "line", "date_et": date, "bar_set": bar_set, "anchor_mode": mode,
            "line_ordinal": li, "in_sample": in_sample,
            "a_idx": ln["a_idx"], "a_t": a_t, "a_price": round(ln["a_price"], 4),
            "b_idx": ln["b_idx"], "b_t": b_t, "b_price": round(ln["b_price"], 4),
            "confirm_idx": ln["confirm_idx"], "confirm_t": bd[ln["confirm_idx"]]["t_dt"].isoformat(),
            "n_touches": len(ln["touches"]), "break_idx": ln["break_idx"], "break_t": break_t,
            "end_reason": ln["end_reason"],
        })
        n_touches += len(ln["touches"])
        if ln["break_idx"] is not None:
            n_breaks += 1

        for j in ln["touches"]:
            outcomes = {str(h): _outcome(bd, j, tf, "up", h) for h in HORIZONS}
            rows.append({
                "kind": "event", "date_et": date, "bar_set": bar_set, "anchor_mode": mode,
                "line_ordinal": li, "in_sample": in_sample, "event_type": "touch",
                "bar_idx": j, "bar_t": bd[j]["t_dt"].isoformat(),
                "close": bd[j]["c"], "low": bd[j]["l"], "outcomes": outcomes,
            })
        if ln["break_idx"] is not None:
            j = ln["break_idx"]
            outcomes = {str(h): _outcome(bd, j, tf, "down", h) for h in HORIZONS}
            rows.append({
                "kind": "event", "date_et": date, "bar_set": bar_set, "anchor_mode": mode,
                "line_ordinal": li, "in_sample": in_sample, "event_type": "break",
                "bar_idx": j, "bar_t": bd[j]["t_dt"].isoformat(),
                "close": bd[j]["c"], "low": bd[j]["l"], "outcomes": outcomes,
            })

    rows.append({"kind": "session_marker", "date_et": date, "bar_set": bar_set,
                 "anchor_mode": mode, "in_sample": in_sample, "n_bars": len(bd),
                 "n_lines": len(lines), "n_touches": n_touches, "n_breaks": n_breaks})
    return rows


# ------------------------------------------------------------------------------------------
# summary statistics -- session-clustered bootstrap CI + time-of-day baseline (prereg sec 5)
# ------------------------------------------------------------------------------------------
def _clustered_bootstrap(events_by_session: dict[str, list[dict]], rng: random.Random,
                          n_boot: int = B_BOOT) -> dict:
    """Percentile bootstrap resampling trading DAYS with replacement (day-resampling
    respects within-day correlation, matching go_live_gate.bootstrap_pf_ci's methodology
    and the tp1_r50 sibling clock).

    PERFORMANCE: pools thousands of raw events per session across hundreds of sessions --
    re-concatenating the full pooled list on every one of n_boot draws (the naive approach)
    is O(n_boot * n_events) and does not finish in reasonable time at this instrument's
    real scale (100K+ events, 600+ sessions). Instead this reduces each session to a
    (count, n_favorable, sum_c2c) aggregate ONCE, then every bootstrap draw only sums
    n_sessions small tuples -- O(n_boot * n_sessions), ~20-100x fewer operations here,
    with an IDENTICAL statistical result (the point estimate and every resampled draw's
    rate/mean are exact functions of those three per-session sums, not an approximation)."""
    sessions = list(events_by_session.keys())
    pooled = [e for v in events_by_session.values() for e in v]
    n = len(pooled)
    if n == 0 or not sessions:
        return {"n": 0, "n_sessions": 0, "rate": None, "rate_ci": None,
                "mean_move": None, "mean_move_ci": None}
    point_rate = sum(1 for e in pooled if e["favorable"]) / n
    point_mean = statistics.mean(e["c2c"] for e in pooled)

    agg = []
    for s in sessions:
        evs = events_by_session[s]
        agg.append((len(evs), sum(1 for e in evs if e["favorable"]), sum(e["c2c"] for e in evs)))
    n_sessions = len(sessions)

    rates, means = [], []
    randrange = rng.randrange
    for _ in range(n_boot):
        tot_n = tot_nf = 0
        tot_s = 0.0
        for _ in range(n_sessions):
            cn, cnf, cs = agg[randrange(n_sessions)]
            tot_n += cn
            tot_nf += cnf
            tot_s += cs
        if tot_n:
            rates.append(tot_nf / tot_n)
            means.append(tot_s / tot_n)
    rates.sort()
    means.sort()

    def pct(arr, p):
        if not arr:
            return None
        idx = min(len(arr) - 1, max(0, int(round(p * (len(arr) - 1)))))
        return arr[idx]

    return {"n": n, "n_sessions": len(events_by_session), "rate": point_rate,
            "rate_ci": [pct(rates, 0.025), pct(rates, 0.975)],
            "mean_move": point_mean, "mean_move_ci": [pct(means, 0.025), pct(means, 0.975)]}


def _build_hhmm_index(bar_data_by_date: dict[str, list[dict]]) -> dict[str, list[tuple[str, int]]]:
    """date/bar_index pairs bucketed by clock time, built ONCE per bar_set and reused for
    every (event_type x horizon x mode) baseline lookup -- avoids re-scanning every bar of
    every session (and re-computing strftime on each) on every one of the ~dozen baseline
    calls a config makes."""
    idx: dict[str, list[tuple[str, int]]] = {}
    for date, bd in bar_data_by_date.items():
        for j, b in enumerate(bd):
            idx.setdefault(b["t_dt"].strftime("%H:%M"), []).append((date, j))
    return idx


def _baseline_stats(hhmm_index: dict[str, list[tuple[str, int]]],
                     bar_data_by_date: dict[str, list[dict]], event_bar_set: set[tuple[str, int]],
                     event_hhmm: set[str], direction: str, horizon: int, tf: str) -> dict:
    N = HORIZON_BARS[tf][horizon]
    pooled = []
    for hhmm in event_hhmm:
        for date, j in hhmm_index.get(hhmm, ()):
            if (date, j) in event_bar_set:
                continue
            bd = bar_data_by_date[date]
            if j + N >= len(bd):
                continue
            c0 = bd[j]["c"]
            cN = bd[j + N]["c"]
            pooled.append((cN - c0) if direction == "up" else (c0 - cN))
    if not pooled:
        return {"n": 0, "rate": None, "mean_move": None}
    return {"n": len(pooled), "rate": sum(1 for x in pooled if x > 0) / len(pooled),
            "mean_move": statistics.mean(pooled)}


def _top3_concentration(events_by_session: dict[str, list[dict]]) -> float:
    counts = sorted((len(v) for v in events_by_session.values()), reverse=True)
    total = sum(counts)
    if total == 0:
        return 0.0
    return round(sum(counts[:3]) / total, 4)


def _summarize(rows: list[dict]) -> dict:
    rng = random.Random(SEED)
    lines = [r for r in rows if r["kind"] == "line"]
    events = [r for r in rows if r["kind"] == "event"]
    markers = [r for r in rows if r["kind"] == "session_marker"]

    configs = {}
    for bar_set in BAR_SETS:
        # bar data + the hhmm lookup index depend only on bar_set (never on anchor_mode) --
        # build both ONCE per bar_set and share across wick/body, instead of re-loading and
        # re-scanning the cache twice per bar_set (this was the dominant nightly-runtime
        # cost before this fix: full-cache re-reads x 8 configs x 12 baseline calls each).
        tf = bar_set.split("_")[0]
        rth = bar_set.endswith("_rth")
        bs_markers = [m for m in markers if m["bar_set"] == bar_set]
        bar_data_by_date: dict[str, list[dict]] = {}
        for date in {m["date_et"] for m in bs_markers}:
            bars_1m = load_bars(CACHE_DIR / f"spy_1m_{date}.json")
            bars_5m = load_bars(CACHE_DIR / f"spy_5m_{date}.json")
            bar_data_by_date[date] = to_barset(bars_1m, bars_5m, date, tf, rth)
        hhmm_index = _build_hhmm_index(bar_data_by_date)

        for mode in ANCHOR_MODES:
            key = f"{bar_set}|{mode}"
            cfg_lines = [r for r in lines if r["bar_set"] == bar_set and r["anchor_mode"] == mode]
            cfg_events = [r for r in events if r["bar_set"] == bar_set and r["anchor_mode"] == mode]
            cfg_markers = [r for r in markers if r["bar_set"] == bar_set and r["anchor_mode"] == mode]

            event_bar_set = {(r["date_et"], r["bar_idx"]) for r in cfg_events}

            def per_type(etype: str, direction: str, forward_only: bool) -> dict:
                sel = [r for r in cfg_events if r["event_type"] == etype
                       and (not forward_only or not r["in_sample"])]
                by_h = {}
                for h in HORIZONS:
                    by_session: dict[str, list[dict]] = {}
                    hhmm: set[str] = set()
                    for r in sel:
                        oc = r["outcomes"].get(str(h))
                        if oc is None:
                            continue
                        by_session.setdefault(r["date_et"], []).append(oc)
                        hhmm.add(r["bar_t"][11:16])
                    stats = _clustered_bootstrap(by_session, rng)
                    stats["baseline"] = _baseline_stats(hhmm_index, bar_data_by_date, event_bar_set,
                                                          hhmm, direction, h, tf)
                    by_h[str(h)] = stats
                events_by_session_count = {d: sum(1 for r in sel if r["date_et"] == d)
                                            for d in {r["date_et"] for r in sel}}
                return {"by_horizon": by_h,
                        "top3_concentration": _top3_concentration(
                            {d: [None] * c for d, c in events_by_session_count.items()}),
                        "n_events": len(sel), "n_sessions": len(events_by_session_count)}

            configs[key] = {
                "bar_set": bar_set, "anchor_mode": mode,
                "n_sessions_total": len({m["date_et"] for m in cfg_markers}),
                "n_sessions_in_sample": len({m["date_et"] for m in cfg_markers if m["in_sample"]}),
                "n_sessions_forward": len({m["date_et"] for m in cfg_markers if not m["in_sample"]}),
                "n_lines": len(cfg_lines),
                "n_lines_in_sample": sum(1 for r in cfg_lines if r["in_sample"]),
                "n_lines_forward": sum(1 for r in cfg_lines if not r["in_sample"]),
                "touch_all": per_type("touch", "up", forward_only=False),
                "break_all": per_type("break", "down", forward_only=False),
                "touch_forward": per_type("touch", "up", forward_only=True),
                "break_forward": per_type("break", "down", forward_only=True),
            }

    # ---- decision rule (prereg section 7): primary bar_sets, wick mode, H=60, forward-only
    decision = {}
    today = _stamp_now_et()[:10] or dt.date.today().isoformat()
    date_gate_open = today >= HARD_DATE_GATE
    for bar_set in PRIMARY_BAR_SETS:
        key = f"{bar_set}|{PRIMARY_MODE}"
        cfg = configs.get(key)
        if cfg is None:
            continue
        for etype, cell_key in (("touch", "touch_forward"), ("break", "break_forward")):
            cell = cfg[cell_key]
            h60 = cell["by_horizon"]["60"]
            n_ok = (cell["n_sessions"] >= BAR_MIN_SESSIONS_FORWARD
                    and cell["n_events"] >= BAR_MIN_EVENTS_FORWARD)
            baseline_rate = h60["baseline"]["rate"]
            rate_ci = h60.get("rate_ci")
            mean_ci = h60.get("mean_move_ci")
            rate_ok = (rate_ci is not None and rate_ci[0] is not None
                       and baseline_rate is not None and rate_ci[0] > baseline_rate)
            mean_ok = mean_ci is not None and mean_ci[0] is not None and mean_ci[0] > 0
            falsified = (rate_ci is not None and rate_ci[0] is not None
                         and baseline_rate is not None and rate_ci[0] <= baseline_rate) \
                or (mean_ci is not None and mean_ci[0] is not None and mean_ci[0] <= 0) \
                or (cell["top3_concentration"] >= FALSIFIER_TOP3_CONCENTRATION)
            bar_met = n_ok
            if not bar_met:
                status = "ACCRUING"
            elif not date_gate_open:
                status = "BAR_MET_DATE_GATED"
            elif rate_ok and mean_ok and cell["top3_concentration"] < FALSIFIER_TOP3_CONCENTRATION:
                status = "SUPPORTED_PROCEED_TO_RATIFICATION"
            elif falsified:
                status = "FALSIFIED"
            else:
                status = "BAR_MET_INCONCLUSIVE"
            decision[f"{bar_set}|{etype}"] = {
                "n_sessions_forward": cell["n_sessions"], "n_events_forward": cell["n_events"],
                "bar_met": bar_met, "date_gate_open": date_gate_open,
                "baseline_rate": baseline_rate, "rate_ci_lower": rate_ci[0] if rate_ci else None,
                "rate_clears_baseline": rate_ok,
                "mean_move_ci_lower": mean_ci[0] if mean_ci else None, "mean_move_positive": mean_ok,
                "top3_concentration": cell["top3_concentration"], "status": status,
            }

    return {
        "prereg": PREREG_REL, "generated_at_et": _stamp_now_et(),
        "in_sample_cutoff": IN_SAMPLE_CUTOFF, "hard_date_gate": HARD_DATE_GATE,
        "configs": configs, "decision": decision,
    }


def _today_rows(rows: list[dict], date: str = "2026-09-03") -> list[dict]:
    return [r for r in rows if r.get("date_et") == date and r["kind"] in ("line", "event")]


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Backfills once over every cached session (idempotent per date/bar_set/anchor_mode),
    then always rewrites the summary from the full ledger. Fail-open by contract."""
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        done = _processed_session_configs(existing)

        sessions = list_sessions()
        appended: list[dict] = []
        for date in sessions:
            need = [(bs, m) for bs in BAR_SETS for m in ANCHOR_MODES
                    if (date, bs, m) not in done]
            if not need:
                continue
            bars_1m = load_bars(CACHE_DIR / f"spy_1m_{date}.json")
            bars_5m = load_bars(CACHE_DIR / f"spy_5m_{date}.json")
            for bs, m in need:
                appended.extend(process_session_config(date, bars_1m, bars_5m, bs, m))

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        all_rows = existing + appended
        summary = _summarize(all_rows)
        summary["new_rows_this_run"] = len(appended)
        summary["n_sessions_ledger"] = len({(r["date_et"]) for r in all_rows
                                             if r["kind"] == "session_marker"})
        summary["today_2026_09_03"] = _today_rows(all_rows)
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:500], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    printable = {k: v for k, v in out.items() if k != "today_2026_09_03"}
    print(json.dumps(printable, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
