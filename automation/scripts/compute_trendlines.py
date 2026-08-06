"""Compute trendline context into automation/state/trendlines.json.

STATUS -- READ THIS BEFORE TRUSTING OR REVIVING THIS SCRIPT (audited 2026-08-06):

  * This is a LEGACY producer with ZERO downstream consumers. A repo-wide search on
    2026-08-06 found no code that reads `automation/state/trendlines.json` -- only
    this file writes it, and two prompt docs mention it.
  * Its only caller is automation/prompts/premarket.md step 2, an LLM instruction.
    It is NOT on any scheduled task. That is the whole reason the artifact sat stale
    from 2026-05-14 to 2026-08-06: the premarket deliverable-gate in
    setup/scripts/run-premarket.ps1 checks only today-bias.json, so an LLM run that
    silently skipped step 2 still reported success (C7 -- audit outputs, not exit codes).
  * The engine's `trendline_rejection` trigger DOES NOT depend on this file. It
    computes its own line in-process from prior_bars via
    backtest/lib/filters.py::detect_trendline_rejection_bearish. Measured over the
    387-session population on 2026-08-06 it fires 653 times on 185 days (47.8% of
    sessions, 1.69/day) -- the trigger was never dead, only this artifact was.
  * The LIVE trendline organ is backtest/autoresearch/trendline_engine.py
    (Gamma_Trendlines, every 5 min RTH) -> trendlines-live.json / trendline-watch.json,
    which were both fresh at 16:00 ET on 2026-08-06.

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
        "auto_count": len(auto_lines),
        "manual": manual_lines,
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
            "This producer is legacy and is invoked only by automation/prompts/premarket.md "
            "step 2; it is NOT on any scheduled task."
        ),
        "doctrine_note": (
            "Trendlines are CONTEXT data — heartbeat does NOT score them as entry triggers "
            "until a backtest demonstrates positive expectancy uplift over v14 baseline. "
            "See operating principle 6 + markdown/0dte/playbook.md TRENDLINE_BREAK_RETEST (DRAFT)."
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
    print(f"wrote {args.out} — {payload['manual_count']} manual + {payload['auto_count']} auto trendlines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
