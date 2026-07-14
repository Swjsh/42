"""trendline_break_replay.py -- G1: historical trendline break detector + dataset (2026-07-14).

Built per J's directive ("this needs a proper review. charting skills and a full research
agent on trend lines and their breaks") after the live 2026-07-14 ascending-support break
(anchored premarket wick low ~747.4, respected 10:20-30's higher lows, dumped through
~12:10-12:15 ET) exposed that trendline_engine.py's live detector SEES structure but the
engine trades on none of it (shadow-only, A/B NEEDS-REVIEW). This is the STUDY SUBSTRATE:
a walk-forward, no-repaint replay of the full cached SPY 5m history that answers "when a
line breaks, what actually happens next" -- so a future entry-wire decision has real evidence
behind it instead of one anecdote.

STANDALONE, READ-ONLY of the audit-owned subsystem: a separate crew is mid-flight on
trendline_engine.py / the drawing bridge / markdown/audits/TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md
this session. This file imports trendline_engine's PURE, side-effect-free primitives
(find_pivots, _body_extreme, the TOL/PIVOT_K/MIN_SPAN/WICK_MIN_* constants) and edits NOTHING
in that module. In particular the wick-vs-body split reuses te.find_pivots(family=...)
UNCHANGED -- it already implements exactly what this task asked for (wick anchors require a
protruding wick >= max(WICK_MIN_CENTS, WICK_MIN_FRACTION * bar_range), body anchors are
min/max(open,close)) with a named, evidenced, already-tested threshold (te.WICK_MIN_FRACTION=
0.10, te.WICK_MIN_CENTS=0.05, landed 2026-07-14 same day off real same-day evidence -- see
trendline_engine.py's own docstring). Forking a second wick threshold here would make the
live engine and this study disagree about what a "wick" is; reusing te's is the only choice
that keeps the dataset representative of what the live engine would actually detect.

J'S RULES, ENFORCED STRUCTURALLY (not just tested):
  1. Anchors ALL-wick or ALL-body, never mixed per line -- `_px_accessor` picks ONE accessor
     per (kind, family) and both anchors of every candidate line are read through it (mirrors
     te._fit's own tripwire assert; see `_candidate_pairs`).
  2. A WICK anchor requires an actual protruding wick -- delegated entirely to
     te.find_pivots(family="wick"), which already excludes bars whose low/high is a body point
     in disguise (e.g. open==low) from the wick pivot list.
  3. Quality = RESPECT COUNT BEYOND THE 2 ANCHORS (MIN_RESPECT_BEYOND_ANCHORS=2 below) -- a
     candidate line that never earns >=2 non-anchor touches before it would otherwise be
     violated is DROPPED ENTIRELY (`_scan_line` returns None), never written to the dataset.
     This is the fix for the "2-point lines through extremes that nothing else touches"
     garbage J caught live -- te._fit's own gate (`respect >= 1`, and that count INCLUDES the
     anchor bars themselves) was not strict enough; this tool's gate is.

NO REPAINT (C6): decisions at bar T use ONLY bars[0:T+1]. This holds by construction --
`_scan_line` walks forward one bar at a time (`for j in range(i1, day_len)`) and every
qualification/break/respect decision at step j reads only `bars[j]` and the fixed anchor
geometry (i1,i2,p1,p2 -- both already-past bars). Pivot CONFIRMATION is inherently causal too
(a pivot at index i needs only bars[i-k:i+k+1], all i+PIVOT_K in the past relative to any bar
after it) -- te.find_pivots is called once per day for convenience/speed, not because it looks
ahead; see test_no_lookahead_truncation_invariance in the test file for the proof (replaying
bars[:break_idx+1] produces the byte-identical break record to replaying the full day).

OUTPUT: analysis/trendlines/break-dataset.jsonl -- one row per QUALIFYING line-instance
(family, kind, both anchors, respects, qualification bar) with a nested `break` object (null
if the line was still intact at EOD) carrying: break_type (close_through | wick_through_only
-- see WICK-THROUGH-ONLY note below), break-bar volume vs the trailing 20-bar average,
time-of-day, and the post-break path (retest within 10/20 bars, MFE/MAE over 30/60/90 min).

WICK-THROUGH-ONLY vs CLOSE-THROUGH: te.detect()'s production BROKEN flag is close-only (a
wick that pierces the line but closes back inside is invisible to it). For a "full research
agent on breaks" that distinction IS the interesting axis (fakeout vs genuine break), so this
tool's break trigger is the wider one -- the FIRST bar after qualification whose EXTREME
crosses the line by tolerance -- tagged by whether the SAME bar's close also confirmed it.
The QUALIFICATION gate stays close-only (matching te._fit's violation definition) so a noisy
wick during line formation doesn't kill an otherwise-good candidate.

Run: cd backtest && .venv/Scripts/python.exe autoresearch/trendline_break_replay.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
DATA_DIR = BACKTEST / "data"
OUT_PATH = REPO / "analysis" / "trendlines" / "break-dataset.jsonl"

for _p in (BACKTEST, BACKTEST / "autoresearch"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.et_frame import FRAME_ET_V2, parse_timestamp_et  # noqa: E402
import trendline_engine as te  # noqa: E402 -- READ-ONLY: this file never edits trendline_engine.py

# Reuse trendline_engine's constants verbatim -- single source of truth, never redefine/fork.
TOL = te.TOL
PIVOT_K = te.PIVOT_K
MIN_SPAN = te.MIN_SPAN

# J's rule (2026-07-14): quality = respects BEYOND the 2 anchors. te._fit's own gate
# (respect >= 1, INCLUDING the anchor bars in that count) is not strict enough -- this is the
# fix. See module docstring point 3.
MIN_RESPECT_BEYOND_ANCHORS = 2

FAMILIES: tuple[str, ...] = ("wick", "body")
KINDS: tuple[str, ...] = ("support", "resistance")
HORIZONS_MIN: tuple[int, ...] = (30, 60, 90)
RETEST_WINDOWS_BARS: tuple[int, ...] = (10, 20)
VOL_LOOKBACK = 20
BAR_MINUTES = 5

# RTH-only, matching trendline_engine.fetch_spy_5m's own filter (13:30:00-20:00:00 UTC ==
# 09:30-16:00 ET). Discovered live during this build (2026-07-14): the spy_5m_*.csv caches are
# NOT RTH-only -- they carry extended-hours bars from 04:00 ET, which thin/whippy premarket
# tape was silently ~doubling the per-day bar count and inflating qualifying-line counts with
# low-liquidity noise the live engine never sees (fetch_spy_5m always RTH-filters). Filtering
# here keeps this dataset comparable to what trendline_engine would actually detect.
# CAVEAT: J's own 2026-07-14 example line anchored at a PREMARKET wick low (~747.4) -- outside
# this (and production's) RTH scope. That is a real gap between what J draws by eye and what
# the live detector ever considers, worth a separate follow-up; this tool stays RTH-only by
# default for apples-to-apples comparability with production, with the exclusion documented
# here rather than silently patched over.
RTH_START_ET = "09:30"
RTH_END_ET = "15:55"  # last 5m bar OPEN time before the 16:00 close (78 bars/session)


# --------------------------------------------------------------------------- cache discovery
def find_broadest_cache(data_dir: Path = DATA_DIR) -> Path:
    """Pick the spy_5m_*.csv with the widest filename-encoded [start,end] span (earliest start,
    then latest end among those). Falls back to the largest file by size if no candidate parses
    cleanly as `spy_5m_{YYYY-MM-DD}_{YYYY-MM-DD}[...].csv`."""
    candidates: list[tuple[str, str, Path]] = []
    for p in sorted(data_dir.glob("spy_5m_*.csv")):
        parts = p.stem.split("_")
        if len(parts) >= 4:
            start, end = parts[2], parts[3]
            if len(start) == 10 and len(end) == 10 and start[4] == "-" and end[4] == "-":
                candidates.append((start, end, p))
    if not candidates:
        all_files = list(data_dir.glob("spy_5m_*.csv"))
        if not all_files:
            raise FileNotFoundError(f"no spy_5m_*.csv found under {data_dir}")
        return max(all_files, key=lambda p: p.stat().st_size)
    earliest_start = min(c[0] for c in candidates)
    same_start = [c for c in candidates if c[0] == earliest_start]
    best = max(same_start, key=lambda c: c[1])
    return best[2]


def find_extension_cache(after_date: str, data_dir: Path = DATA_DIR) -> Path | None:
    """Find a spy_5m_*.csv whose filename-encoded end date is LATER than `after_date` -- used
    to append the most-recent trading days that the broadest historical file (find_broadest_cache)
    hasn't caught up to yet (incremental grabs are re-cut more often than the full-history
    master gets re-merged). Picks the candidate with the latest end date; ties broken by the
    latest (tightest/freshest) start. Returns None if nothing extends past `after_date`."""
    candidates: list[tuple[str, str, Path]] = []
    for p in sorted(data_dir.glob("spy_5m_*.csv")):
        parts = p.stem.split("_")
        if len(parts) >= 4:
            start, end = parts[2], parts[3]
            if len(start) == 10 and len(end) == 10 and start[4] == "-" and end[4] == "-" and end > after_date:
                candidates.append((start, end, p))
    if not candidates:
        return None
    latest_end = max(c[1] for c in candidates)
    same_end = [c for c in candidates if c[1] == latest_end]
    best = max(same_end, key=lambda c: c[0])  # freshest/tightest start among ties
    return best[2]


def load_cache(path: Path) -> pd.DataFrame:
    """Load a spy_5m_*.csv and attach TRUE DST-correct ET wall time + absolute unix seconds.

    Uses et_frame's et-v2 frame (opt-in, per et_frame.py's migration discipline) rather than
    the wall-v1 default: this cache's timestamp_et column carries a FIXED -04:00 offset
    year-round (see backtest/lib/et_frame.py), so a naive parse mislabels every EST-month
    (Nov-Mar) bar's hour by +1 and can clip the last true RTH hour. `time_of_day_et` in the
    output dataset needs the correct wall clock, not the mislabeled one.
    """
    df = pd.read_csv(path)
    df["et_wall"] = parse_timestamp_et(df["timestamp_et"], frame=FRAME_ET_V2)
    # The stored offset (however mislabeled for EST display) round-trips to the correct UTC
    # instant -- see et_frame.py's docstring ("UTC INSTANT of every row is correct"). This is
    # frame-invariant: wall-v1 and et-v2 parses of the same string yield the same UTC instant.
    df["unix"] = pd.to_datetime(df["timestamp_et"], utc=True).astype("int64") // 10**9
    df["date_et"] = df["et_wall"].dt.strftime("%Y-%m-%d")
    df["hm_et"] = df["et_wall"].dt.strftime("%H:%M")
    # RTH-only -- see RTH_START_ET/RTH_END_ET module comment (cache includes premarket bars).
    df = df[(df["hm_et"] >= RTH_START_ET) & (df["hm_et"] <= RTH_END_ET)].reset_index(drop=True)
    return df


def day_bar_list(day_df: pd.DataFrame) -> list[dict]:
    """DataFrame slice for one trading day -> list of plain dicts (o,h,l,c,v,unix,hm) in
    chronological order. Deliberately does NOT carry a 't' ISO-string key (te.find_pivots /
    te._body_extreme only ever read o/h/l/c -- verified by inspection of trendline_engine.py)."""
    day_df = day_df.sort_values("unix")
    return [
        {
            "o": float(r.open), "h": float(r.high), "l": float(r.low), "c": float(r.close),
            "v": float(r.volume), "unix": int(r.unix), "hm": r.hm_et,
        }
        for r in day_df.itertuples(index=False)
    ]


# --------------------------------------------------------------------------- line geometry
def _px_accessor(kind: str, family: str):
    """Same-accessor-per-line invariant (J's rule #1): ONE function, reused for both anchors
    of every candidate line of this (kind, family). Never mixes wick and body fields."""
    if family == "wick":
        return (lambda b: b["l"]) if kind == "support" else (lambda b: b["h"])
    return lambda b: te._body_extreme(b, kind)


def _line_value(p1: float, slope: float, i1: int, j: int) -> float:
    return p1 + slope * (j - i1)


def _candidate_pairs(bars: list[dict], pivots: list[int], kind: str, family: str):
    """Every same-kind, same-family pivot pair >= MIN_SPAN apart, ascending (support) /
    descending (resistance) through the SAME accessor -- structurally guarded (assert) exactly
    like te._fit's own tripwire, so a future edit here can't accidentally mix accessors."""
    px = _px_accessor(kind, family)
    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, i2 = pivots[a], pivots[b]
            if i2 - i1 < MIN_SPAN:
                continue
            p1, p2 = px(bars[i1]), px(bars[i2])
            if family == "wick":
                wf = "l" if kind == "support" else "h"
                assert p1 == bars[i1][wf] and p2 == bars[i2][wf], (
                    "wick-only anchor invariant violated in trendline_break_replay")
            else:
                assert p1 == te._body_extreme(bars[i1], kind) and p2 == te._body_extreme(bars[i2], kind), (
                    "body-only anchor invariant violated in trendline_break_replay")
            if kind == "support" and p2 <= p1:
                continue
            if kind == "resistance" and p2 >= p1:
                continue
            yield i1, i2, p1, p2


# --------------------------------------------------------------------------- walk-forward scan
def _scan_line(bars: list[dict], kind: str, family: str, i1: int, i2: int, p1: float,
                p2: float, day_len: int) -> dict | None:
    """Walk forward from the first anchor to end-of-day, bar by bar, using ONLY bars[i1:j+1]
    at step j (no repaint -- see module docstring). Returns None if the candidate never earns
    MIN_RESPECT_BEYOND_ANCHORS non-anchor touches before a close-through kills it (garbage
    line, J's rule #3) -- such candidates are never written to the dataset."""
    slope = (p2 - p1) / (i2 - i1)
    px = _px_accessor(kind, family)
    respects_excl_anchors = 0
    qualified_at: int | None = None
    break_rec: dict | None = None

    for j in range(i1, day_len):
        lv = _line_value(p1, slope, i1, j)
        extreme = px(bars[j])
        close = bars[j]["c"]
        is_anchor = j == i1 or j == i2
        tol = max(TOL, 0.0015 * lv)

        if kind == "support":
            closed_through = close < lv - tol
            breached = extreme < lv - tol
        else:
            closed_through = close > lv + tol
            breached = extreme > lv + tol

        if qualified_at is None:
            # Pre-qualification gate: production-faithful (close-only violation, matching
            # te._fit) so a noisy wick during formation doesn't kill an otherwise-good line.
            if closed_through:
                return None  # garbage line -- died before ever earning quality
            if not is_anchor and not breached and abs(extreme - lv) <= tol:
                respects_excl_anchors += 1
                if respects_excl_anchors >= MIN_RESPECT_BEYOND_ANCHORS:
                    qualified_at = j
            continue

        # Post-qualification: watching for the first meaningful challenge to the line. Wider
        # trigger than production (extreme, not just close) -- see WICK-THROUGH-ONLY note in
        # the module docstring; break_type records which kind it actually was.
        if breached:
            break_rec = _build_break_record(
                bars, kind, family, i1, p1, slope, j, lv, extreme, close, closed_through, day_len,
            )
            break
        if not is_anchor and abs(extreme - lv) <= tol:
            respects_excl_anchors += 1

    if qualified_at is None:
        return None
    return {
        "kind": kind, "family": family, "i1": i1, "i2": i2, "p1": p1, "p2": p2,
        "slope": slope, "respects_excl_anchors": respects_excl_anchors,
        "qualified_at": qualified_at, "break": break_rec,
    }


def _build_break_record(bars: list[dict], kind: str, family: str, i1: int, p1: float,
                         slope: float, j: int, lv: float, extreme: float, close: float,
                         closed_through: bool, day_len: int) -> dict:
    lookback = bars[max(0, j - VOL_LOOKBACK):j]
    avg_vol20 = (sum(b["v"] for b in lookback) / len(lookback)) if lookback else None
    break_vol = bars[j]["v"]
    direction = "bearish" if kind == "support" else "bullish"

    rec: dict = {
        "break_bar_idx": j,
        "break_unix": bars[j]["unix"],
        "time_of_day_et": bars[j]["hm"],
        "break_type": "close_through" if closed_through else "wick_through_only",
        "break_direction": direction,
        "line_value_at_break": round(lv, 4),
        "close_at_break": round(close, 2),
        "extreme_at_break": round(extreme, 2),
        "breach_amount_close": round(close - lv, 4),
        "breach_amount_extreme": round(extreme - lv, 4),
        "break_bar_volume": break_vol,
        "avg_volume_20bar": round(avg_vol20, 2) if avg_vol20 is not None else None,
        "volume_ratio": round(break_vol / avg_vol20, 3) if avg_vol20 else None,
        "vol_lookback_bars_available": len(lookback),
    }

    ref_close = close
    for h_min in HORIZONS_MIN:
        n_bars = h_min // BAR_MINUTES
        window = bars[j + 1: j + 1 + n_bars]
        if window:
            highs = [b["h"] for b in window]
            lows = [b["l"] for b in window]
            if direction == "bearish":
                mfe, mae = ref_close - min(lows), max(highs) - ref_close
            else:
                mfe, mae = max(highs) - ref_close, ref_close - min(lows)
        else:
            mfe = mae = None
        rec[f"mfe_{h_min}min"] = round(mfe, 4) if mfe is not None else None
        rec[f"mae_{h_min}min"] = round(mae, 4) if mae is not None else None
        rec[f"bars_available_{h_min}min"] = len(window)

    px = _px_accessor(kind, family)
    for nb in RETEST_WINDOWS_BARS:
        window_idx = range(j + 1, min(j + 1 + nb, day_len))
        retested = False
        for k in window_idx:
            lv_k = _line_value(p1, slope, i1, k)
            tol_k = max(TOL, 0.0015 * lv_k)
            if abs(px(bars[k]) - lv_k) <= tol_k:
                retested = True
                break
        rec[f"retest_within_{nb}bar"] = retested

    return rec


# --------------------------------------------------------------------------- day driver
def replay_day(bars: list[dict], date_et: str) -> list[dict]:
    """Detect every qualifying wick+body support+resistance line for one trading day and its
    break outcome (if any). Pure function of `bars` -- caller controls day-scoping so no
    cross-day bleed."""
    rows: list[dict] = []
    day_len = len(bars)
    if day_len < MIN_SPAN + 2 * PIVOT_K + 2:
        return rows
    for family in FAMILIES:
        lows, highs = te.find_pivots(bars, k=PIVOT_K, family=family)
        for kind, pivots in (("support", lows), ("resistance", highs)):
            for i1, i2, p1, p2 in _candidate_pairs(bars, pivots, kind, family):
                res = _scan_line(bars, kind, family, i1, i2, p1, p2, day_len)
                if res is None:
                    continue
                rows.append(_format_row(bars, date_et, res))
    return rows


def _format_row(bars: list[dict], date_et: str, res: dict) -> dict:
    i1, i2 = res["i1"], res["i2"]
    q = res["qualified_at"]
    return {
        "date_et": date_et,
        "kind": res["kind"],
        "anchor_family": res["family"],
        "a_bar_idx": i1, "a_et": bars[i1]["hm"], "a_unix": bars[i1]["unix"], "a_price": round(res["p1"], 2),
        "b_bar_idx": i2, "b_et": bars[i2]["hm"], "b_unix": bars[i2]["unix"], "b_price": round(res["p2"], 2),
        "slope_per_bar": round(res["slope"], 4),
        "span_bars": i2 - i1,
        "respects_excl_anchors": res["respects_excl_anchors"],
        "respect_count_incl_anchors": res["respects_excl_anchors"] + 2,  # cf. te.Trendline.respect_count
        "qualified_at_bar_idx": q,
        "qualified_at_et": bars[q]["hm"],
        "break": res["break"],
        "intact_eod": res["break"] is None,
    }


# --------------------------------------------------------------------------- main
def replay_cache(df: pd.DataFrame, start: str | None = None, end: str | None = None,
                  limit_days: int | None = None) -> tuple[list[dict], int]:
    dates = sorted(df["date_et"].unique())
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]
    if limit_days:
        dates = dates[:limit_days]

    all_rows: list[dict] = []
    for d in dates:
        day_df = df[df["date_et"] == d]
        bars = day_bar_list(day_df)
        all_rows.extend(replay_day(bars, d))
    return all_rows, len(dates)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return round(s[mid], 4) if n % 2 else round((s[mid - 1] + s[mid]) / 2, 4)


def build_summary(rows: list[dict], cache_path: Path, ext_path: Path | None, n_days: int) -> dict:
    """Small, git-trackable aggregate rollup of the (large, gitignored) full dataset -- counts,
    respect/span distributions, break-type split, and MFE/MAE/retest stats per family+direction,
    so a reviewer can see the shape of the study without opening the 67MB+ JSONL."""
    breaks = [r for r in rows if r["break"] is not None]
    by_cell: dict[str, dict] = {}
    for family in FAMILIES:
        for kind in KINDS:
            cell_rows = [r for r in rows if r["anchor_family"] == family and r["kind"] == kind]
            cell_breaks = [r for r in breaks if r["anchor_family"] == family and r["kind"] == kind]
            close_rows = [r for r in cell_breaks if r["break"]["break_type"] == "close_through"]
            wick_rows = [r for r in cell_breaks if r["break"]["break_type"] == "wick_through_only"]
            by_cell[f"{family}_{kind}"] = {
                "direction": "bearish" if kind == "support" else "bullish",
                "qualified": len(cell_rows),
                "broke": len(cell_breaks),
                "close_through": len(close_rows),
                "wick_through_only": len(wick_rows),
                "intact_eod": len(cell_rows) - len(cell_breaks),
                "median_span_bars": _median([r["span_bars"] for r in cell_rows]),
                "median_respects_excl_anchors": _median([r["respects_excl_anchors"] for r in cell_rows]),
                "mean_volume_ratio_at_break": _mean(
                    [r["break"]["volume_ratio"] for r in cell_breaks if r["break"]["volume_ratio"] is not None]),
                "retest_within_10bar_rate": _mean(
                    [1.0 if r["break"]["retest_within_10bar"] else 0.0 for r in cell_breaks]),
                "retest_within_20bar_rate": _mean(
                    [1.0 if r["break"]["retest_within_20bar"] else 0.0 for r in cell_breaks]),
                "mean_mfe_30min": _mean([r["break"]["mfe_30min"] for r in cell_breaks if r["break"]["mfe_30min"] is not None]),
                "mean_mae_30min": _mean([r["break"]["mae_30min"] for r in cell_breaks if r["break"]["mae_30min"] is not None]),
                "mean_mfe_60min": _mean([r["break"]["mfe_60min"] for r in cell_breaks if r["break"]["mfe_60min"] is not None]),
                "mean_mae_60min": _mean([r["break"]["mae_60min"] for r in cell_breaks if r["break"]["mae_60min"] is not None]),
                "mean_mfe_90min": _mean([r["break"]["mfe_90min"] for r in cell_breaks if r["break"]["mfe_90min"] is not None]),
                "mean_mae_90min": _mean([r["break"]["mae_90min"] for r in cell_breaks if r["break"]["mae_90min"] is not None]),
            }
    return {
        "generated_at_note": "G1 trendline_break_replay -- historical walk-forward break dataset",
        "primary_cache": str(cache_path.relative_to(REPO)) if _is_relative(cache_path) else str(cache_path),
        "extension_cache": (str(ext_path.relative_to(REPO)) if ext_path and _is_relative(ext_path) else
                             (str(ext_path) if ext_path else None)),
        "trading_days_replayed": n_days,
        "date_range": [min((r["date_et"] for r in rows), default=None), max((r["date_et"] for r in rows), default=None)],
        "total_qualifying_lines": len(rows),
        "total_breaks": len(breaks),
        "total_close_through": sum(1 for r in breaks if r["break"]["break_type"] == "close_through"),
        "total_wick_through_only": sum(1 for r in breaks if r["break"]["break_type"] == "wick_through_only"),
        "min_respect_beyond_anchors_gate": MIN_RESPECT_BEYOND_ANCHORS,
        "rth_window_et": [RTH_START_ET, RTH_END_ET],
        "by_family_direction": by_cell,
        "full_dataset_path": "analysis/trendlines/break-dataset.jsonl (gitignored -- regenerate via "
                              "backtest/autoresearch/trendline_break_replay.py)",
    }


def _is_relative(p: Path) -> bool:
    try:
        p.relative_to(REPO)
        return True
    except ValueError:
        return False


def summarize(rows: list[dict]) -> str:
    total = len(rows)
    breaks = [r for r in rows if r["break"] is not None]
    lines = [f"trendline_break_replay: {total} qualifying line-instances, {len(breaks)} broke"]
    for family in FAMILIES:
        for kind in KINDS:
            n_q = sum(1 for r in rows if r["anchor_family"] == family and r["kind"] == kind)
            n_b = sum(1 for r in breaks if r["anchor_family"] == family and r["kind"] == kind)
            n_close = sum(1 for r in breaks if r["anchor_family"] == family and r["kind"] == kind
                          and r["break"]["break_type"] == "close_through")
            n_wick = n_b - n_close
            direction = "bearish" if kind == "support" else "bullish"
            lines.append(f"  {family:5s}/{kind:10s} ({direction:7s}): {n_q:5d} qualified, "
                        f"{n_b:5d} broke ({n_close} close_through / {n_wick} wick_through_only)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=None, help="override spy_5m_*.csv path")
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD inclusive")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD inclusive")
    ap.add_argument("--limit-days", type=int, default=None, help="cap number of trading days (dev use)")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--summary-out", type=Path, default=OUT_PATH.with_name("break-dataset-summary.json"))
    args = ap.parse_args()

    out_path = args.out.resolve()

    def _disp(p: Path) -> str:
        try:
            return str(p.relative_to(REPO))
        except ValueError:
            return str(p)

    cache_path = args.cache or find_broadest_cache()
    ext_path_used: Path | None = None
    print(f"trendline_break_replay: loading {_disp(cache_path)}")
    df = load_cache(cache_path)

    rows, n_days = replay_cache(df, start=args.start, end=args.end, limit_days=args.limit_days)
    cache_max_date = str(df["date_et"].max())
    print(f"trendline_break_replay: replayed {n_days} trading days ({df['date_et'].min()}..{cache_max_date} "
          f"cache span)")

    # Extend with the freshest incremental cache past the broadest file's tail, if one exists
    # and the caller didn't pin an explicit --cache/--end (those mean "I chose my window on
    # purpose", so don't silently append more).
    if args.cache is None and args.end is None:
        ext_path = find_extension_cache(cache_max_date)
        if ext_path is not None:
            ext_path_used = ext_path
            ext_df = load_cache(ext_path)
            ext_rows, ext_days = replay_cache(ext_df, start=cache_max_date)
            # replay_cache's start filter is INCLUSIVE; cache_max_date was already replayed above.
            ext_rows_new = [r for r in ext_rows if r["date_et"] > cache_max_date]
            new_dates = sorted({r["date_et"] for r in ext_rows_new} | {
                d for d in ext_df["date_et"].unique() if d > cache_max_date})
            print(f"trendline_break_replay: extending with {_disp(ext_path)} "
                  f"({len(new_dates)} new trading days past {cache_max_date})")
            rows.extend(ext_rows_new)
            n_days += len(new_dates)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"trendline_break_replay: wrote {len(rows)} rows ({n_days} trading days total) -> {_disp(out_path)}")
    print(summarize(rows))

    summary_path = args.summary_out.resolve()
    summary = build_summary(rows, cache_path, ext_path_used, n_days)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"trendline_break_replay: wrote summary -> {_disp(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
