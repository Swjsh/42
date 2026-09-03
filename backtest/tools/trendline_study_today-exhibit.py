"""trendline_study_today-exhibit — T2 mechanical reproduction of J's 2026-09-03 exhibit.

READ-ONLY study script. Imports backtest/lib/trendline_detector.py and crypto/lib/bar.py
as libraries (never modifies them). No network, no broker, no writes to automation/state.

Question: reproduce J's hand-drawn rising support line (08:20 premarket low -> 10:10
double-bottom low, 5m; 08:15 -> 10:00, 15m) three mechanical ways (all-wick, all-body,
J's own mixed body->wick draw), quote its value/touch/break behavior at 10:55 and 14:30,
and then ask whether the repo's own pivot-anchored detector (backtest/lib/trendline_detector.py)
would have found the same line, with or without premarket bars, and whether it had the
anchors available at 10:55 with no look-ahead.

Aggregation convention (stated up front, matches the existing spy_5m_<date>.json cache —
verified below): a bar labeled with timestamp T is the OPEN of the interval [T, T+granularity).
5m bar "08:20:00" = 1m bars 08:20..08:24 inclusive. open=first 1m open, high=max(1m highs),
low=min(1m lows), close=last 1m close, volume=sum. Same rule for 15m (3x 5m width, or 15x 1m).

Bar timestamps in the SIP cache are naive local strings already in ET (04:00 = premarket
open, matches doctrine) -- no additional TZ conversion applied; et_clock.py used only to
timestamp this report, never to reinterpret the cached bar times.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402
from backtest.lib.trendline_detector import (  # noqa: E402
    detect_trendlines,
    _fit_candidate,
    DETECTOR_VERSION,
    DEFAULT_TOUCH_TOLERANCE_DOLLARS,
    DEFAULT_PIVOT_WINDOW,
    DEFAULT_MIN_TOUCHES,
    DEFAULT_MIN_BARS_BETWEEN_TOUCHES,
    DEFAULT_MIN_SPAN_BARS,
)

DATE = "2026-09-03"
CACHE_1M = REPO_ROOT / "backtest" / "data" / "spy_sip_cache" / f"spy_1m_{DATE}.json"
CACHE_5M = REPO_ROOT / "backtest" / "data" / "spy_sip_cache" / f"spy_5m_{DATE}.json"
OUT_DIR = REPO_ROOT / "analysis" / "deep-research" / "2026-09-03-money"
OUT_JSON = OUT_DIR / "trendline-today-exhibit.json"
OUT_MD = OUT_DIR / "trendline-today-exhibit.md"


@dataclass(frozen=True)
class M1:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


def load_1m() -> list[M1]:
    raw = json.loads(CACHE_1M.read_text())["bars"]
    return [M1(b["t"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)) for b in raw]


def aggregate(bars_1m: list[M1], minutes: int, cutoff_dt: datetime | None = None) -> list[dict]:
    """Group 1m bars into `minutes`-wide buckets keyed by bar-OPEN time, floored to the
    grid implied by the 04:00 session start (04:00, 04:05, 04:10... for 5m; 04:00, 04:15...
    for 15m). Bar label = the bucket's own start timestamp (open-of-interval convention,
    matches the existing 5m cache -- verified in main() against spy_5m_<date>.json).

    `cutoff_dt`, if given, drops any 1m bar whose timestamp >= cutoff_dt BEFORE bucketing --
    this is the no-look-ahead control: a bucket is only ever built from 1m bars that were
    themselves already closed as of cutoff_dt, so the LAST bucket returned is either fully
    complete or entirely absent (never a partial/truncated bucket masquerading as a closed one).
    """
    buckets: dict[str, list[M1]] = {}
    session_start = datetime.fromisoformat(bars_1m[0].t)
    for b in bars_1m:
        ts = datetime.fromisoformat(b.t)
        if cutoff_dt is not None and ts >= cutoff_dt:
            continue
        delta_min = int((ts - session_start).total_seconds() // 60)
        bucket_idx = delta_min // minutes
        bucket_start = session_start + timedelta(minutes=bucket_idx * minutes)
        key = bucket_start.isoformat()
        buckets.setdefault(key, []).append(b)
    out = []
    for key in sorted(buckets.keys()):
        grp = buckets[key]
        if cutoff_dt is not None and len(grp) < minutes:
            continue  # incomplete trailing bucket -- not yet closed as of cutoff_dt, drop it
        out.append({
            "t": key,
            "o": grp[0].o,
            "h": max(x.h for x in grp),
            "l": min(x.l for x in grp),
            "c": grp[-1].c,
            "v": sum(x.v for x in grp),
            "n_1m_bars": len(grp),
        })
    return out


def find_bar(bars: list[dict], hhmm: str) -> dict | None:
    for b in bars:
        if b["t"][11:16] == hhmm:
            return b
    return None


def line_value(t1: str, y1: float, t2: str, y2: float, t_query: str, date: str = DATE) -> float:
    d1 = datetime.fromisoformat(f"{date}T{t1}:00")
    d2 = datetime.fromisoformat(f"{date}T{t2}:00")
    dq = datetime.fromisoformat(f"{date}T{t_query}:00")
    slope = (y2 - y1) / (d2 - d1).total_seconds()
    return y1 + slope * (dq - d1).total_seconds()


def next_n_min_high_low(bars_1m: list[M1], close_ts: str, n_min: int) -> dict:
    start = datetime.fromisoformat(f"{DATE}T{close_ts}:00")
    end = start + timedelta(minutes=n_min)
    window = [b for b in bars_1m if start <= datetime.fromisoformat(b.t) < end]
    if not window:
        return {"n_bars": 0, "high": None, "low": None}
    return {
        "n_bars": len(window),
        "high": max(b.h for b in window),
        "low": min(b.l for b in window),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }


def bars_to_Bar_tuple(bars: list[dict]) -> tuple[Bar, ...]:
    out = []
    for b in bars:
        ts = datetime.fromisoformat(b["t"]).replace(tzinfo=timezone.utc)  # tz-aware wrapper only;
        # NOTE: these are ET-labeled local timestamps stamped as tz-aware UTC purely to satisfy
        # the Bar dataclass's tz-aware invariant -- detect_trendlines only uses relative bar
        # ordering/spacing (bar_index-based slope) and open_time.timestamp() for anchor unix
        # stamps (diagnostic field only), so the UTC/ET label mismatch does not affect any
        # touch/violation/slope computation below (all of which are bar-index-relative).
        out.append(Bar(
            open_time=ts, open=b["o"], high=b["h"], low=b["l"], close=b["c"],
            volume=b.get("v", 0.0), granularity_seconds=b.get("_gran", 300), source="spy_sip_cache",
        ))
    return tuple(out)


def rth_only(bars: list[dict]) -> list[dict]:
    return [b for b in bars if "09:30" <= b["t"][11:16] < "16:00"]


def run_detector(bars: list[dict], gran_seconds: int, label: str, timeframe: str) -> dict:
    """Run the detector over exactly the bars given (caller controls truncation/no-lookahead
    by pre-filtering `bars`, e.g. via aggregate(..., cutoff_dt=...) -- never truncates here)."""
    tagged = [dict(b, _gran=gran_seconds) for b in bars]
    bar_objs = bars_to_Bar_tuple(tagged)
    lines = detect_trendlines(
        bar_objs, kinds=("support",),
        anchor_mode="wick", require_slope="rising",
        pivot_window=DEFAULT_PIVOT_WINDOW, min_touches=DEFAULT_MIN_TOUCHES,
        min_bars_between_touches=DEFAULT_MIN_BARS_BETWEEN_TOUCHES,
        min_span_bars=DEFAULT_MIN_SPAN_BARS,
        touch_tolerance_dollars=DEFAULT_TOUCH_TOLERANCE_DOLLARS,
        max_lines_per_kind=5, symbol="SPY", timeframe=timeframe,
    )
    result = {
        "label": label, "timeframe": timeframe,
        "n_bars_available": len(bars),
        "first_bar_t": bars[0]["t"] if bars else None,
        "last_bar_t": bars[-1]["t"] if bars else None,
        "n_lines_found": len(lines),
        "lines": [ln.to_dict() for ln in lines],
    }
    return result


def pivot_and_candidate_check(bars: list[dict], gran_seconds: int, anchor_a_hhmm: str,
                               anchor_b_hhmm: str, label: str) -> dict:
    """Direct check (bypassing detect_trendlines' own ranking/dedup): does J's SPECIFIC
    anchor pair register as a pair of confirmed swing-low pivots in this bar set, and if
    both do, what does _fit_candidate say about the resulting line (touches/violations/score)
    using the SAME rules the top-level detector uses? This answers 'did the detector have
    the anchors it needed' independent of whether that pair happens to be the #1-ranked line.
    """
    tagged = [dict(b, _gran=gran_seconds) for b in bars]
    bar_objs = bars_to_Bar_tuple(tagged)
    swings = find_swing_points(bar_objs, window=DEFAULT_PIVOT_WINDOW, inclusive_right=True)
    lows = sorted([s for s in swings if s.kind == "swing_low"], key=lambda s: s.bar_index)
    by_idx = {s.bar_index: s for s in lows}
    idx_a = next((i for i, b in enumerate(bars) if b["t"][11:16] == anchor_a_hhmm), None)
    idx_b = next((i for i, b in enumerate(bars) if b["t"][11:16] == anchor_b_hhmm), None)
    out = {
        "label": label, "n_bars": len(bars),
        "last_bar_t": bars[-1]["t"] if bars else None,
        "anchor_a_hhmm": anchor_a_hhmm, "anchor_a_bar_index": idx_a,
        "anchor_a_is_confirmed_pivot": idx_a in by_idx if idx_a is not None else False,
        "anchor_b_hhmm": anchor_b_hhmm, "anchor_b_bar_index": idx_b,
        "anchor_b_is_confirmed_pivot": idx_b in by_idx if idx_b is not None else False,
        "all_swing_lows": [
            {"bar_index": s.bar_index, "t": bar_objs[s.bar_index].open_time.strftime("%H:%M"), "price": s.price}
            for s in lows
        ],
        "candidate_fit": None,
    }
    if idx_a in by_idx and idx_b in by_idx:
        cand = _fit_candidate(
            by_idx[idx_a], by_idx[idx_b], kind="support", view_bars=bar_objs, same_kind_swings=lows,
            touch_tolerance_dollars=DEFAULT_TOUCH_TOLERANCE_DOLLARS,
            min_bars_between_touches=DEFAULT_MIN_BARS_BETWEEN_TOUCHES,
            min_touches=DEFAULT_MIN_TOUCHES, require_slope="rising",
        )
        if cand is None:
            out["candidate_fit"] = {"accepted": False, "reason": "rejected by _fit_candidate (insufficient touches and/or wrong slope sign)"}
        else:
            out["candidate_fit"] = {
                "accepted": True,
                "touch_bar_indices": list(cand.touch_bar_indices),
                "touches_as_times": [bar_objs[i].open_time.strftime("%H:%M") for i in cand.touch_bar_indices],
                "violation_bar_indices": list(cand.violation_bar_indices),
                "violations_as_times": [bar_objs[i].open_time.strftime("%H:%M") for i in cand.violation_bar_indices],
                "score": round(cand.score, 3),
            }
    return out


def break_time_search(bars: list[dict], anchor_a_hhmm: str, anchor_a_price: float,
                       anchor_b_hhmm: str, anchor_b_price: float, scan_from_hhmm: str,
                       tolerance: float = DEFAULT_TOUCH_TOLERANCE_DOLLARS) -> dict | None:
    """First bar (scanning forward from scan_from_hhmm) whose CLOSE breaks the line by more
    than `tolerance` (mirrors the detector's own support 'broken' rule: close < projected -
    tolerance). Returns None if never broken in the scanned range."""
    for b in bars:
        hhmm = b["t"][11:16]
        if hhmm < scan_from_hhmm:
            continue
        lv = line_value(anchor_a_hhmm, anchor_a_price, anchor_b_hhmm, anchor_b_price, hhmm)
        if b["c"] < lv - tolerance:
            return {"broke_at": hhmm, "line_value": round(lv, 4), "close": b["c"], "dist": round(b["c"] - lv, 4)}
    return None


def main() -> None:
    bars_1m = load_1m()
    print(f"1m bars loaded: {len(bars_1m)}  {bars_1m[0].t} .. {bars_1m[-1].t}")

    bars_5m = aggregate(bars_1m, 5)
    bars_15m = aggregate(bars_1m, 15)
    print(f"aggregated 5m bars: {len(bars_5m)}   15m bars: {len(bars_15m)}")

    # --- validate 5m aggregation convention against the existing cached 5m file ---
    cached_5m = json.loads(CACHE_5M.read_text())
    cached_5m_bars = cached_5m["bars"] if isinstance(cached_5m, dict) else cached_5m
    mismatches = []
    cached_by_t = {b["t"]: b for b in cached_5m_bars}
    for b in bars_5m:
        cb = cached_by_t.get(b["t"])
        if cb is None:
            continue
        for k in ("o", "h", "l", "c"):
            if abs(cb[k] - b[k]) > 1e-6:
                mismatches.append((b["t"], k, cb[k], b[k]))
    print(f"5m aggregation vs cache: {len(cached_by_t)} bars compared, {len(mismatches)} mismatches")
    if mismatches[:5]:
        print("  sample mismatches:", mismatches[:5])

    # --- data-gap check: any bucket built from fewer than the expected count of 1m bars? ---
    incomplete_5m = [b for b in bars_5m if b["n_1m_bars"] != 5]
    incomplete_15m = [b for b in bars_15m if b["n_1m_bars"] != 15]
    print(f"incomplete 5m buckets (1m data gaps): {[(b['t'], b['n_1m_bars']) for b in incomplete_5m]}")
    print(f"incomplete 15m buckets (1m data gaps): {[(b['t'], b['n_1m_bars']) for b in incomplete_15m]}")

    # --- anchor bars ---
    anchor_5m_a = find_bar(bars_5m, "08:20")
    anchor_5m_b = find_bar(bars_5m, "10:10")
    anchor_15m_a = find_bar(bars_15m, "08:15")
    anchor_15m_b = find_bar(bars_15m, "10:00")
    print("5m anchor A (08:20):", anchor_5m_a)
    print("5m anchor B (10:10):", anchor_5m_b)
    print("15m anchor A (08:15):", anchor_15m_a)
    print("15m anchor B (10:00):", anchor_15m_b)

    # --- premarket / session low context: is 08:20 the actual premarket low? ---
    premarket_5m = [b for b in bars_5m if b["t"][11:16] < "09:30"]
    premarket_min_low = min(b["l"] for b in premarket_5m)
    premarket_low_bar = [b for b in premarket_5m if b["l"] == premarket_min_low][0]
    print(f"premarket (04:00-09:30) 5m low: {premarket_min_low} at {premarket_low_bar['t']}")

    # =====================================================================
    # 5m: three line variants
    # =====================================================================
    def body_val(b):
        return min(b["o"], b["c"])

    variants_5m = {
        "all_wick": (anchor_5m_a["l"], anchor_5m_b["l"]),
        "all_body": (body_val(anchor_5m_a), body_val(anchor_5m_b)),
        "mixed_body_to_wick": (body_val(anchor_5m_a), anchor_5m_b["l"]),
    }

    candle_1055_5m = find_bar(bars_5m, "10:55")
    candle_1430_5m = find_bar(bars_5m, "14:30")

    # break-time search (close < line - $0.20), scanning forward from 13:00
    breaks_5m = {name: break_time_search(bars_5m, "08:20", y1, "10:10", y2, "13:00")
                 for name, (y1, y2) in variants_5m.items()}

    report_5m = {}
    for name, (y1, y2) in variants_5m.items():
        val_1055 = line_value("08:20", y1, "10:10", y2, "10:55")
        val_1430 = line_value("08:20", y1, "10:10", y2, "14:30")
        low_dist = candle_1055_5m["l"] - val_1055
        close_dist = candle_1055_5m["c"] - val_1055
        next60_after_1055 = next_n_min_high_low(bars_1m, "11:00", 60)  # candle closes 11:00
        close_1430_dist = candle_1430_5m["c"] - val_1430
        next60_after_1430 = next_n_min_high_low(bars_1m, "14:35", 60)  # candle closes 14:35
        report_5m[name] = {
            "anchor_a_price": y1, "anchor_b_price": y2,
            "slope_dollars_per_min": (y2 - y1) / ((datetime.fromisoformat(f"{DATE}T10:10:00") - datetime.fromisoformat(f"{DATE}T08:20:00")).total_seconds() / 60),
            "line_value_at_1055": round(val_1055, 4),
            "line_value_at_1430": round(val_1430, 4),
            "candle_1055": {"o": candle_1055_5m["o"], "h": candle_1055_5m["h"], "l": candle_1055_5m["l"], "c": candle_1055_5m["c"]},
            "1055_low_minus_line": round(low_dist, 4),
            "1055_close_minus_line": round(close_dist, 4),
            "1055_touch_inside_0.10": abs(low_dist) <= 0.10,
            "1055_touch_inside_0.20": abs(low_dist) <= 0.20,
            "1055_touch_inside_0.30": abs(low_dist) <= 0.30,
            "1055_close_above_line": close_dist > 0,
            "next_60min_high_after_1055_candle": next60_after_1055,
            "candle_1430": {"o": candle_1430_5m["o"], "h": candle_1430_5m["h"], "l": candle_1430_5m["l"], "c": candle_1430_5m["c"]},
            "1430_close_minus_line": round(close_1430_dist, 4),
            "1430_broken_by_tolerance": close_1430_dist < -DEFAULT_TOUCH_TOLERANCE_DOLLARS,
            "1430_below_line_at_all": close_1430_dist < 0,
            "first_close_break_scanning_from_1300": breaks_5m[name],
            "next_60min_low_after_1430_candle": next60_after_1430,
        }

    # =====================================================================
    # 15m: three line variants (J's own quote for 15m = wick->wick)
    # =====================================================================
    variants_15m = {
        "all_wick": (anchor_15m_a["l"], anchor_15m_b["l"]),
        "all_body": (body_val(anchor_15m_a), body_val(anchor_15m_b)),
        "mixed_body_to_wick": (body_val(anchor_15m_a), anchor_15m_b["l"]),
    }
    candle_1055_15m = find_bar(bars_15m, "10:45")  # 15m bar covering 10:45-11:00, contains 10:55
    candle_1430_15m = find_bar(bars_15m, "14:30")  # exact 15m boundary

    breaks_15m = {name: break_time_search(bars_15m, "08:15", y1, "10:00", y2, "13:00")
                  for name, (y1, y2) in variants_15m.items()}

    report_15m = {}
    for name, (y1, y2) in variants_15m.items():
        val_1055 = line_value("08:15", y1, "10:00", y2, "10:55")
        val_1430 = line_value("08:15", y1, "10:00", y2, "14:30")
        low_dist = candle_1055_15m["l"] - val_1055
        close_dist = candle_1055_15m["c"] - val_1055
        next60_after_1055 = next_n_min_high_low(bars_1m, "11:00", 60)
        close_1430_dist = candle_1430_15m["c"] - val_1430
        next60_after_1430 = next_n_min_high_low(bars_1m, "14:45", 60)
        report_15m[name] = {
            "anchor_a_price": y1, "anchor_b_price": y2,
            "slope_dollars_per_min": (y2 - y1) / ((datetime.fromisoformat(f"{DATE}T10:00:00") - datetime.fromisoformat(f"{DATE}T08:15:00")).total_seconds() / 60),
            "line_value_at_1055": round(val_1055, 4),
            "line_value_at_1430": round(val_1430, 4),
            "candle_containing_1055_[10:45-11:00]": {"o": candle_1055_15m["o"], "h": candle_1055_15m["h"], "l": candle_1055_15m["l"], "c": candle_1055_15m["c"]},
            "1055_low_minus_line": round(low_dist, 4),
            "1055_close_minus_line": round(close_dist, 4),
            "1055_touch_inside_0.10": abs(low_dist) <= 0.10,
            "1055_touch_inside_0.20": abs(low_dist) <= 0.20,
            "1055_touch_inside_0.30": abs(low_dist) <= 0.30,
            "1055_close_above_line": close_dist > 0,
            "next_60min_high_after_1055_candle": next60_after_1055,
            "candle_1430_[14:30-14:45]": {"o": candle_1430_15m["o"], "h": candle_1430_15m["h"], "l": candle_1430_15m["l"], "c": candle_1430_15m["c"]},
            "1430_close_minus_line": round(close_1430_dist, 4),
            "1430_broken_by_tolerance": close_1430_dist < -DEFAULT_TOUCH_TOLERANCE_DOLLARS,
            "1430_below_line_at_all": close_1430_dist < 0,
            "first_close_break_scanning_from_1300": breaks_15m[name],
            "next_60min_low_after_1430_candle": next60_after_1430,
        }

    # =====================================================================
    # Detector runs -- EOD (hindsight, full session) on RTH-only vs premarket-included
    # =====================================================================
    bars_5m_rth = rth_only(bars_5m)
    bars_15m_rth = rth_only(bars_15m)

    detector_runs = {
        "5m_full_day_incl_premarket_eod": run_detector(bars_5m, 300, "5m+premarket, as-of EOD", "5m"),
        "5m_rth_only_eod": run_detector(bars_5m_rth, 300, "5m RTH-only, as-of EOD", "5m"),
        "15m_full_day_incl_premarket_eod": run_detector(bars_15m, 900, "15m+premarket, as-of EOD", "15m"),
        "15m_rth_only_eod": run_detector(bars_15m_rth, 900, "15m RTH-only, as-of EOD", "15m"),
    }

    # =====================================================================
    # No-look-ahead detector runs: only bars whose CLOSE TIME <= 10:55 are visible.
    # A 5m/15m bucket is included only if COMPLETE (aggregate(..., cutoff_dt=...) drops any
    # trailing partial bucket) -- this is what makes "last bar" == "last CLOSED bar" here,
    # not an off-by-one on the bucket boundary.
    # =====================================================================
    cutoff_1055 = datetime.fromisoformat(f"{DATE}T10:55:00")
    bars_5m_asof1055 = aggregate(bars_1m, 5, cutoff_dt=cutoff_1055)
    bars_15m_asof1055 = aggregate(bars_1m, 15, cutoff_dt=cutoff_1055)
    bars_5m_rth_asof1055 = rth_only(bars_5m_asof1055)
    bars_15m_rth_asof1055 = rth_only(bars_15m_asof1055)

    detector_runs["5m_full_day_incl_premarket_asof_1055_nolookahead"] = run_detector(
        bars_5m_asof1055, 300, "5m+premarket, as-of last-CLOSED-bar<=10:55 (no lookahead)", "5m")
    detector_runs["5m_rth_only_asof_1055_nolookahead"] = run_detector(
        bars_5m_rth_asof1055, 300, "5m RTH-only, as-of last-CLOSED-bar<=10:55 (no lookahead)", "5m")
    detector_runs["15m_full_day_incl_premarket_asof_1055_nolookahead"] = run_detector(
        bars_15m_asof1055, 900, "15m+premarket, as-of last-CLOSED-bar<=10:55 (no lookahead)", "15m")
    detector_runs["15m_rth_only_asof_1055_nolookahead"] = run_detector(
        bars_15m_rth_asof1055, 900, "15m RTH-only, as-of last-CLOSED-bar<=10:55 (no lookahead)", "15m")

    for key, res in detector_runs.items():
        print(f"\n--- detector run: {key} ---")
        print(f"  bars used: {res['n_bars_available']}  ({res['first_bar_t']} .. {res['last_bar_t']})")
        print(f"  support lines (rising) found: {res['n_lines_found']}")
        for ln in res["lines"]:
            anchors_str = " -> ".join(f"idx{a['bar_index']}@{a['price']}" for a in ln["anchors"])
            print(f"    {ln['line_id']}  touches={ln['touch_count']}  anchors={anchors_str}  status={ln['status']}")

    # =====================================================================
    # Direct anchor-pivot / candidate-fit checks (bypasses ranking -- answers "did the
    # detector have J's SPECIFIC anchors available, and would that specific pair have
    # qualified as a line at all" independent of whether it's the #1-ranked candidate).
    # =====================================================================
    pivot_checks = {
        "5m_0820_1010_incl_premarket_asof1055_nolookahead": pivot_and_candidate_check(
            bars_5m_asof1055, 300, "08:20", "10:10", "5m 08:20->10:10, premarket incl., as-of<=10:55"),
        "5m_0820_1010_incl_premarket_eod": pivot_and_candidate_check(
            bars_5m, 300, "08:20", "10:10", "5m 08:20->10:10, premarket incl., EOD hindsight"),
        "15m_0815_1000_incl_premarket_asof1055_nolookahead": pivot_and_candidate_check(
            bars_15m_asof1055, 900, "08:15", "10:00", "15m 08:15->10:00, premarket incl., as-of<=10:55"),
        "15m_0815_1000_incl_premarket_eod": pivot_and_candidate_check(
            bars_15m, 900, "08:15", "10:00", "15m 08:15->10:00, premarket incl., EOD hindsight"),
        # nearest ACTUAL mechanical pivot to J's 08:20 anchor is one 5m bar earlier (08:15,
        # $0.01 lower -- 08:20 fails the strict-left-higher swing-low test because 08:15 is
        # itself marginally lower). Test that adjusted pair too, both no-lookahead and EOD.
        "5m_0815_1010_ADJUSTED_asof1055_nolookahead": pivot_and_candidate_check(
            bars_5m_asof1055, 300, "08:15", "10:10", "5m 08:15(nearest actual pivot to J's 08:20)->10:10, as-of<=10:55"),
        "5m_0815_1010_ADJUSTED_eod": pivot_and_candidate_check(
            bars_5m, 300, "08:15", "10:10", "5m 08:15(nearest actual pivot to J's 08:20)->10:10, EOD hindsight"),
    }
    for key, res in pivot_checks.items():
        print(f"\n--- pivot/candidate check: {key} ---")
        print(f"  A({res['anchor_a_hhmm']}) confirmed pivot: {res['anchor_a_is_confirmed_pivot']}   "
              f"B({res['anchor_b_hhmm']}) confirmed pivot: {res['anchor_b_is_confirmed_pivot']}")
        print(f"  candidate_fit: {res['candidate_fit']}")

    full_report = {
        "meta": {
            "date": DATE,
            "stamp_et": "2026-09-03T17:30",
            "detector_version": DETECTOR_VERSION,
            "aggregation_convention": "bar label = open-of-interval; 5m label 08:20 = 1m bars 08:20-08:24 inclusive; 15m label 08:15 = 1m bars 08:15-08:29 inclusive",
            "n_1m_bars": len(bars_1m),
            "session_first_bar": bars_1m[0].t,
            "session_last_bar": bars_1m[-1].t,
            "5m_agg_vs_cache_mismatches": len(mismatches),
            "5m_agg_vs_cache_mismatch_detail": mismatches,
            "incomplete_5m_buckets_1m_data_gaps": [(b["t"], b["n_1m_bars"]) for b in incomplete_5m],
            "incomplete_15m_buckets_1m_data_gaps": [(b["t"], b["n_1m_bars"]) for b in incomplete_15m],
            "premarket_5m_low": {"value": premarket_min_low, "bar_t": premarket_low_bar["t"]},
        },
        "anchors": {
            "5m_08:20": anchor_5m_a, "5m_10:10": anchor_5m_b,
            "15m_08:15": anchor_15m_a, "15m_10:00": anchor_15m_b,
        },
        "line_5m": report_5m,
        "line_15m": report_15m,
        "detector_runs": detector_runs,
        "pivot_and_candidate_checks": pivot_checks,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(full_report, indent=2, default=str))
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
