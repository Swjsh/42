"""Compute trendline context into automation/state/trendlines.json.

STATUS -- READ THIS BEFORE TRUSTING OR REVIVING THIS SCRIPT (audited 2026-08-06):

  * This is a LEGACY producer with ZERO downstream consumers. A repo-wide search on
    2026-08-06 found no code that reads `automation/state/trendlines.json` -- only
    this file writes it, and two prompt docs mention it.
  * ITS CLI ENTRY POINT (`main()`, `python compute_trendlines.py`) is still called from
    exactly one place: automation/prompts/premarket.md step 2, an LLM instruction, once
    daily. That is the whole reason the artifact sat stale from 2026-05-14 to 2026-08-06:
    the premarket deliverable-gate in setup/scripts/run-premarket.ps1 checks only
    today-bias.json, so an LLM run that silently skipped step 2 still reported success
    (C7 -- audit outputs, not exit codes).
  * The engine's `trendline_rejection` trigger DOES NOT depend on this file. It
    computes its own line in-process from prior_bars via
    backtest/lib/filters.py::detect_trendline_rejection_bearish. Measured over the
    387-session population on 2026-08-06 it fires 653 times on 185 days (47.8% of
    sessions, 1.69/day) -- the trigger was never dead, only this artifact was.
  * The LIVE trendline organ is backtest/autoresearch/trendline_engine.py
    (Gamma_Trendlines, every 5 min RTH) -> trendlines-live.json / trendline-watch.json,
    which were both fresh at 16:00 ET on 2026-08-06.
  * UPDATE 2026-08-18 (J: "the engine reads his hand-drawn TradingView trendlines ONLY
    at premarket, so anything he draws during the session is never seen"): `compute()`
    (this module's real work function, as opposed to the CLI-only `main()` above) is now
    ALSO called intraday, every 5 min RTH, piggybacked on the Gamma_Trendlines task via
    backtest/autoresearch/trendline_manual.py::refresh() -- see that module's docstring.
    That module ALSO refreshes automation/state/chart_drawings.json itself (previously
    only touched by the once-daily premarket ui_evaluate step, and observed stale for
    two months in the live state dir) via setup/scripts/tv_cdp.py, the existing headless
    CDP client -- so J's manual lines are now visible within one 5-min tick of drawing
    them, not just the next morning. Both call sites share this file's SAME `compute()`
    function and SAME staleness/significance filters -- there is exactly one manual-line
    reader and one set of thresholds, never two that could silently disagree (L251).
    A NEW higher-timeframe significance filter (`score_manual_significance`, see
    MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES below) additionally keeps `manual_significant`
    down to a few structurally meaningful lines instead of every scribble -- J's second
    ask ("I wanna do this on a higher time frame... so we don't have a bunch of small
    individual trend lines").

  Consumption stays SHADOW. Promotion bar is stated in
  analysis/deep-research/EOD-2026-08-06-INSTRUMENTS.md.

Reads:
  - SPY 5m CSV in backtest/data/ with the newest END date (auto-detection input)
  - automation/state/chart_drawings.json (J's manually-drawn trendlines)

Usage:
    python automation/scripts/compute_trendlines.py
    python automation/scripts/compute_trendlines.py --spot 767.96
    python automation/scripts/compute_trendlines.py --lookback-sessions 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backtest"))

from lib.trendlines import (  # noqa: E402
    Trendline,
    TOUCH_TOLERANCE_USD,
    detect_trendlines,
    trendline_from_two_points,
)

ET = pytz.timezone("America/New_York")
STATE_DIR = REPO_ROOT / "automation" / "state"
DATA_DIR = REPO_ROOT / "backtest" / "data"

# Manual chart-draw hygiene (2026-08-06). A hand-drawn line is only context while it
# is still anywhere near the tape; beyond these bounds it is extrapolation noise.
MANUAL_MAX_AGE_DAYS = 10.0
MANUAL_MAX_DISTANCE = 15.0

# HIGHER-TIMEFRAME SIGNIFICANCE FILTER (2026-08-18, J verbatim: "I wanna do this on a
# higher time frame, though, so we don't have a bunch of small individual trend lines").
# The staleness filters above answer "is this line still near the tape"; this answers
# "is this line big enough to matter". A manual line whose two anchors are 6 minutes
# apart is a scribble even when it is 2 minutes old and sits right on spot.
MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES = 120.0
# Anchors must be >= 2 trading hours apart. SPY RTH is 390 min/session, so this floors
# out anything under ~1/3 of a session. Chosen to sit clearly ABOVE the auto-detector's
# own 30-min noise floor (see the `relevant` auto-line filter in compute() below) since
# J's ask was specifically for a HIGHER timeframe than what already counts as "not
# noise" for auto-detected lines -- a manual line is held to a stricter bar than that,
# not a looser one, precisely because a human drew it and it will get drawn again.

MANUAL_TOUCH_TOLERANCE_USD = TOUCH_TOLERANCE_USD
# Reuse backtest.lib.trendlines' own $0.20 touch tolerance (mined from the existing
# auto-detector) rather than inventing a second one.

MANUAL_SIGNIFICANT_CAP = 5
# Top-K by (span_minutes x max(respect_count_recent, 1)) -- mirrors this file's own
# "top 5 per direction" auto-line cap a few lines below, and the trendline-draw skill's
# "way too many trend lines on the screen" cap precedent (J, 2026-07-15).


def _latest_spy_csv() -> Path:
    """Pick the SPY 5m CSV with the newest END date.

    BUG FIXED 2026-08-06: this used `sorted(glob(...))[-1]`, a LEXICOGRAPHIC sort. The
    data dir holds both range files (`spy_5m_2026-05-19_2026-08-06.csv`, 594KB, current)
    and one-day patches (`spy_5m_2026-07-23_supplement.csv`, 5KB). Lexicographically
    "spy_5m_2026-07..." sorts AFTER "spy_5m_2026-05...", so `[-1]` returned the tiny
    July-23 supplement and every trendline was fitted to one stale session -- which is
    why the last output carried auto-detected anchors dated 2026-07-23 while claiming to
    be current. Same family as the beacon asc+limit truncation and L242.

    Sort by the END date parsed out of the filename instead, and break ties by bar count
    (a full range file beats a same-dated supplement).
    """
    candidates = list(DATA_DIR.glob("spy_5m_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No SPY 5m CSV in {DATA_DIR}. Run backtest/tools/fetch_data.py first.")

    def _end_date(p: Path) -> tuple[dt.date, int]:
        dates = []
        for tok in p.stem.split("_"):
            try:
                dates.append(dt.date.fromisoformat(tok))
            except ValueError:
                continue
        # No parseable date -> sort to the very back, never silently chosen over a dated file.
        return (max(dates) if dates else dt.date.min, p.stat().st_size)

    return max(candidates, key=_end_date)


def _load_recent_bars(lookback_sessions: int) -> pd.DataFrame:
    csv_path = _latest_spy_csv()
    df = pd.read_csv(csv_path, parse_dates=["timestamp_et"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET)

    # Keep RTH bars only (09:30-16:00) — premarket bars confuse swing detection.
    rth_mask = (df["timestamp_et"].dt.time >= dt.time(9, 30)) & (df["timestamp_et"].dt.time < dt.time(16, 0))
    df = df.loc[rth_mask].copy()

    # Take the last `lookback_sessions` unique trading days.
    df["date"] = df["timestamp_et"].dt.date
    unique_days = sorted(df["date"].unique())
    keep = unique_days[-lookback_sessions:]
    df = df.loc[df["date"].isin(keep)].copy()

    # Add unix-second timestamp column for the detector.
    df["timestamp_unix"] = df["timestamp_et"].astype("int64") // 1_000_000_000

    df = df.reset_index(drop=True)
    return df


def _load_manual_drawings() -> list[Trendline]:
    path = STATE_DIR / "chart_drawings.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[Trendline] = []
    for d in payload.get("drawings", []):
        if (d.get("title") or "").lower() not in ("trendline", "trend line"):
            continue
        pts = d.get("points") or []
        if len(pts) != 2:
            continue
        p1, p2 = pts
        t1, pr1 = p1.get("time"), p1.get("price")
        t2, pr2 = p2.get("time"), p2.get("price")
        if None in (t1, pr1, t2, pr2):
            continue
        line = trendline_from_two_points(int(t1), float(pr1), int(t2), float(pr2))
        out.append(line)
    return out


def _enrich(line: Trendline, source: str, spot: float | None, now_ts: int, manual_id: str | None = None) -> dict:
    body = line.to_dict()
    body["source"] = source
    if manual_id is not None:
        body["chart_drawing_id"] = manual_id
    if spot is not None:
        proj = line.price_at(now_ts)
        body["projected_price_now"] = round(proj, 4)
        body["distance_from_spot_dollars"] = round(spot - proj, 4)
        # Sign convention: positive = price ABOVE the line, negative = BELOW.
    body["projected_at_close_today"] = round(line.price_at(_today_close_ts(now_ts)), 4)
    return body


def _today_close_ts(now_ts: int) -> int:
    """Project to today's 16:00 ET close."""
    now = dt.datetime.fromtimestamp(now_ts, tz=ET)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return int(close.timestamp())


def _detected_id(line: Trendline) -> str:
    """Stable ID derived from anchors so the same line gets the same ID across runs."""
    h = abs(hash((line.direction, round(line.slope_per_sec, 8), round(line.intercept_price, 2))))
    return f"auto_{h % 1_000_000:06d}"


def _manual_respect_count(entry: dict, bars: pd.DataFrame, tolerance: float = MANUAL_TOUCH_TOLERANCE_USD) -> int:
    """How many bars in `bars` came within `tolerance` of this manual line's projected price
    without closing through it -- the same 'respected touch' idea trendlines-live.json already
    computes for auto lines (backtest/autoresearch/trendline_engine.py::_fit's respect/
    violations walk), MINED here rather than reinvented (task doctrine: don't build a second
    scoring scheme). Manual lines only ever carry their 2 drawn anchors as touch_count
    (backtest/lib/trendlines.py::trendline_from_two_points hard-codes touch_count=2) -- this
    gives J's hand-drawn lines a REAL respect measurement against the actual tape instead of
    that placeholder."""
    if bars is None or bars.empty:
        return 0
    direction = entry.get("direction")
    intercept_price = entry.get("intercept_price")
    intercept_ts = entry.get("intercept_timestamp")
    slope = entry.get("slope_per_sec")
    if None in (direction, intercept_price, intercept_ts, slope):
        return 0
    count = 0
    for row in bars.itertuples():
        proj = intercept_price + slope * (int(row.timestamp_unix) - intercept_ts)
        if not ((row.low - tolerance) <= proj <= (row.high + tolerance)):
            continue
        violated = (row.close < proj - tolerance) if direction == "ascending" else (row.close > proj + tolerance)
        if not violated:
            count += 1
    return count


def score_manual_significance(manual_lines: list[dict], bars: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    """HIGHER-TIMEFRAME FILTER (J, 2026-08-18) -- see MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES.

    Every age/distance-surviving manual line gets two new informational fields
    (`span_minutes`, `respect_count_recent`) -- additive, never changes an existing key's
    meaning. Lines are then gated down to a `significant` subset by two named-constant
    criteria:
      1. SPAN FLOOR -- anchors must be >= MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES apart. This is
         the primary "higher timeframe" gate J asked for verbatim.
      2. TOP-K CAP by (span_minutes x max(respect_count_recent, 1)) -- ranks span-floor
         survivors by a blend of how long-lived AND how respected they are, keeps only the
         top MANUAL_SIGNIFICANT_CAP.

    Returns (all_enriched, significant, dropped). `dropped` entries use the SAME
    {chart_drawing_id, reason} shape as the age/distance `manual_dropped` list in compute()
    below, so a caller can merge both lists without a schema branch."""
    all_enriched: list[dict] = []
    for m in manual_lines:
        anchors = m.get("anchor_points") or []
        times = [a["time"] for a in anchors if "time" in a]
        span_minutes = (max(times) - min(times)) / 60.0 if len(times) >= 2 else 0.0
        all_enriched.append({
            **m,
            "span_minutes": round(span_minutes, 1),
            "respect_count_recent": _manual_respect_count(m, bars),
        })

    dropped: list[dict] = []
    survivors: list[dict] = []
    for m in all_enriched:
        if m["span_minutes"] < MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES:
            dropped.append({
                "chart_drawing_id": m.get("chart_drawing_id"),
                "span_minutes": m["span_minutes"],
                "reason": (f"insignificant: span {m['span_minutes']:.1f}min < "
                           f"{MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES:.0f}min floor "
                           f"(scribble, not higher-timeframe)"),
            })
            continue
        survivors.append(m)

    survivors.sort(key=lambda m: m["span_minutes"] * max(m["respect_count_recent"], 1), reverse=True)
    significant = survivors[:MANUAL_SIGNIFICANT_CAP]
    for m in survivors[MANUAL_SIGNIFICANT_CAP:]:
        dropped.append({
            "chart_drawing_id": m.get("chart_drawing_id"),
            "span_minutes": m["span_minutes"],
            "reason": f"insignificant: ranked below top {MANUAL_SIGNIFICANT_CAP} by span x respect",
        })
    return all_enriched, significant, dropped


def compute(spot: float | None, lookback_sessions: int) -> dict:
    bars = _load_recent_bars(lookback_sessions)
    detected = detect_trendlines(bars)
    manual_drawings = _load_manual_drawings()

    now_et = dt.datetime.now(ET)
    now_ts = int(now_et.timestamp())

    if spot is None and not bars.empty:
        spot = float(bars["close"].iloc[-1])

    # Read manual chart_drawings.json a second time for the IDs.
    drawings_path = STATE_DIR / "chart_drawings.json"
    manual_id_lookup: dict[tuple[int, float, int, float], str] = {}
    if drawings_path.exists():
        drawings = json.loads(drawings_path.read_text(encoding="utf-8")).get("drawings", [])
        for d in drawings:
            if (d.get("title") or "").lower() not in ("trendline", "trend line"):
                continue
            pts = d.get("points") or []
            if len(pts) != 2:
                continue
            key = (
                int(pts[0]["time"]), round(float(pts[0]["price"]), 4),
                int(pts[1]["time"]), round(float(pts[1]["price"]), 4),
            )
            manual_id_lookup[key] = d.get("id") or "manual_unknown"

    # STALENESS FILTER (added 2026-08-06). Auto lines already get a +/-$5 proximity
    # filter below; manual ones got NONE, so J's May chart-draws were still being
    # extrapolated months forward and emitted as if current -- the 2026-08-06 audit
    # found this file publishing projected_price_now of $2,825.07 and -$1,117.96
    # against a $770 spot. A line whose projection is off-planet is not "context",
    # it is noise that makes the whole artifact untrustworthy (C7).
    manual_lines = []
    manual_dropped = []
    for line in manual_drawings:
        anchors = line.anchor_points
        if len(anchors) >= 2:
            t1, p1 = anchors[0]
            t2, p2 = anchors[1]
            key = (int(t1), round(float(p1), 4), int(t2), round(float(p2), 4))
            mid = manual_id_lookup.get(key)
        else:
            mid = None

        enriched = _enrich(line, "manual_chart_draw", spot, now_ts, manual_id=mid)
        age_days = None
        if anchors:
            age_days = round((now_ts - max(a[0] for a in anchors)) / 86400.0, 1)
        proj = enriched.get("projected_price_now")
        drop_reason = None
        if age_days is not None and age_days > MANUAL_MAX_AGE_DAYS:
            drop_reason = f"anchors {age_days}d old (> {MANUAL_MAX_AGE_DAYS}d)"
        elif spot is not None and proj is not None and abs(float(proj) - spot) > MANUAL_MAX_DISTANCE:
            drop_reason = f"projects ${float(proj):.2f} vs spot ${spot:.2f} (> ${MANUAL_MAX_DISTANCE:.0f} away)"

        if drop_reason:
            manual_dropped.append({"chart_drawing_id": mid, "age_days": age_days,
                                   "projected_price_now": proj, "reason": drop_reason})
            continue
        enriched["anchor_age_days"] = age_days
        manual_lines.append(enriched)

    # HIGHER-TIMEFRAME SIGNIFICANCE FILTER (2026-08-18) -- see score_manual_significance's
    # docstring. Runs AFTER the age/distance staleness filter above (a line has to be valid
    # context before it's worth ranking); reassigns manual_lines to the enriched version so
    # every surviving entry (not just the significant ones) carries span_minutes /
    # respect_count_recent for visibility.
    manual_lines, manual_significant, manual_insignificant = score_manual_significance(manual_lines, bars)
    manual_dropped.extend(manual_insignificant)

    # Filter auto-detected lines to actionable ones:
    #   - Within ±$5 of spot at the projection time (closer than that to be relevant
    #     for an entry trigger)
    #   - Anchor span ≥ 30 minutes (1800 sec) — shorter spans are bar-to-bar noise
    #   - Last touched within the bar window (not stale projections)
    bar_window_start = int(bars["timestamp_unix"].min()) if not bars.empty else 0
    bar_window_end = int(bars["timestamp_unix"].max()) if not bars.empty else now_ts
    relevant: list[Trendline] = []
    for line in detected:
        anchors = line.anchor_points
        if len(anchors) < 2:
            continue
        anchor_ts = [a[0] for a in anchors]
        if max(anchor_ts) - min(anchor_ts) < 1800:
            continue
        if line.last_touched_at < bar_window_start:
            continue
        if spot is not None:
            proj_now = line.price_at(now_ts)
            if abs(proj_now - spot) > 5.0:
                continue
        relevant.append(line)

    # Take top 5 per direction by (touch_count, r_squared) so the heartbeat doesn't
    # have to sift through dozens.
    asc = sorted([line for line in relevant if line.direction == "ascending"],
                 key=lambda line: (line.touch_count, line.r_squared), reverse=True)[:5]
    desc = sorted([line for line in relevant if line.direction == "descending"],
                  key=lambda line: (line.touch_count, line.r_squared), reverse=True)[:5]
    top_auto = asc + desc

    auto_lines = [
        _enrich(line, "auto_detected", spot, now_ts, manual_id=_detected_id(line))
        for line in top_auto
    ]

    return {
        "schema_version": 1,
        "as_of": now_et.isoformat(),
        "spot": spot,
        "lookback_sessions": lookback_sessions,
        "bars_used": int(len(bars)),
        "manual_count": len(manual_lines),
        "manual_significant_count": len(manual_significant),
        "auto_count": len(auto_lines),
        "manual": manual_lines,
        "manual_significant": manual_significant,
        "auto": auto_lines,
        "manual_dropped": manual_dropped,
        "source_csv": _latest_spy_csv().name,
        "bars_end_et": (
            bars["timestamp_et"].max().isoformat() if not bars.empty else None
        ),
        "status_note": (
            "SHADOW / no downstream consumer. Verified 2026-08-06: NO code reads this "
            "file -- the engine's trendline_rejection trigger computes its own line "
            "in-process from prior_bars (backtest/lib/filters.py "
            "detect_trendline_rejection_bearish) and does NOT depend on this artifact. "
            "The LIVE trendline organ is backtest/autoresearch/trendline_engine.py -> "
            "trendlines-live.json + trendline-watch.json (Gamma_Trendlines, every 5 min RTH). "
            "This file's CLI entry point (main()) is legacy and is invoked only by "
            "automation/prompts/premarket.md step 2, once daily. UPDATE 2026-08-18: "
            "compute() itself (this payload) is now ALSO refreshed every 5 min RTH, "
            "piggybacked on the Gamma_Trendlines task, via "
            "backtest/autoresearch/trendline_manual.py::refresh() -- see that module for "
            "the manual-line intraday-visibility fix. Still zero code consumers by design; "
            "still SHADOW; entries never read this file."
        ),
        "doctrine_note": (
            "Trendlines are CONTEXT data — heartbeat does NOT score them as entry triggers "
            "until a backtest demonstrates positive expectancy uplift over v14 baseline. "
            "See operating principle 6 + markdown/0dte/playbook.md TRENDLINE_BREAK_RETEST (DRAFT). "
            "manual_significant is a VISIBILITY-ONLY higher-timeframe view of manual — nothing "
            "in this file is wired to entries, full stop."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spot", type=float, default=None,
                        help="Current SPY price (defaults to latest close in CSV).")
    parser.add_argument("--lookback-sessions", type=int, default=2,
                        help="How many trading sessions of bars to scan (default 2).")
    parser.add_argument("--out", type=Path, default=STATE_DIR / "trendlines.json",
                        help="Output path (default automation/state/trendlines.json).")
    args = parser.parse_args()

    payload = compute(spot=args.spot, lookback_sessions=args.lookback_sessions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.out} — {payload['manual_count']} manual "
          f"({payload['manual_significant_count']} significant) + {payload['auto_count']} auto trendlines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
