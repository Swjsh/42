"""trendline_shadow.py -- SHADOW ledger for intraday trendline geometry. Zero entry effect.

WHY THIS EXISTS (J, 2026-08-20)
-------------------------------
J hand-drew an ASCENDING SUPPORT line through the 2026-08-20 lows of 08:35
(764.15), 10:20 (765.36) and 11:30 (765.83). Price broke it at 11:35, retested it
at 12:40, rejected, and ran to 763.04. He asked why the engine never saw it.

It structurally cannot. `filters.py::detect_trendline_rejection_bearish` -- the ONLY
trendline detector on the entry path -- reads pivot HIGHS and hard-rejects any
non-decreasing slope. Ascending support, its break, and its retest are invisible to
it by construction.

But `backtest/lib/trendlines.py::detect_trendlines` ALREADY fits ascending lines
from swing lows, is well-tested, and has ZERO consumers anywhere in the engine.
Fed the 2026-08-20 session up to 12:40 it returns J's line as its top-ranked
ascending fit: anchor 764.15 (his exact 08:35 low), touch_count 4, R^2 0.983
against his own hand-fit of 0.982.

So the gap is not detection. The gap is that nothing MEASURES these lines, which
means there is no evidence to A/B against and no honest way to argue for putting
them on the entry path.

WHAT THIS DOES
  For each session, walks bars forward and records every trendline EVENT --
  FORMED / TOUCH / BREAK / RETEST / REJECT -- plus forward MFE/MAE at 15m, 30m and
  60m after each event. Appends to analysis/trendlines/shadow-ledger.jsonl.

WHAT IT DOES NOT DO
  It does not place an order, touch params, or feed any live decision. It is an
  observation surface, and it must stay one until it has >= 15 firings with a
  measured forward edge AND a pre-registered A/B. That sequence is not optional:
  the ATM strike tier shipped in July on a chart read without it and cost $808.

NO LOOK-AHEAD (C6)
  At bar i the fit uses bars[0:i] ONLY, and events are evaluated on bar i's own
  OHLC. Forward MFE/MAE deliberately DO look ahead -- that is the measurement, and
  it is never available to a decision, only to this ledger.

ANCHOR FLAVOR (J directive 2026-07-14)
  A line's anchors must be ALL-body or ALL-wick, never mixed. detect_trendlines
  fits ascending lines through swing LOWS and descending through swing HIGHS --
  wick extremes. Every row is therefore stamped flavor="wick" so a future body-
  anchored variant is distinguishable rather than silently conflated.

USAGE
  backtest/.venv/Scripts/python.exe setup/scripts/trendline_shadow.py --date 2026-08-20
  backtest/.venv/Scripts/python.exe setup/scripts/trendline_shadow.py --seed   # replay all
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))

import pandas as pd                                     # noqa: E402
from lib.trendlines import detect_trendlines            # noqa: E402

# A NEW spy_5m_2026-05-19_<date>.csv is written every session at ~14:16 MT / 16:16 ET,
# so pinning ONE filename would have frozen this shadow at 2026-08-20: every later fire
# would have found no bars for "today" and logged nothing, while still exiting 0. Glob
# and merge instead -- the same idiom regime_shadow_counter.py already uses -- which also
# picks up the one-off supplement file.
BARS_GLOB = str(REPO / "backtest" / "data" / "spy_5m_*.csv")
OUT = REPO / "analysis" / "trendlines" / "shadow-ledger.jsonl"

REFIT_EVERY_BARS = 6        # refit every 30 min; events evaluate on EVERY bar
MIN_BARS_BEFORE_FIT = 24    # ~2h of context before a line is trustworthy
TOUCH_TOL_USD = 0.15        # within this of the line == a touch
FORWARD_WINDOWS = (3, 6, 12)  # 15m / 30m / 60m in 5m bars



def load_bars() -> pd.DataFrame:
    """The newest CUMULATIVE daily bar file -- one stratum, never a merge.

    WHY NOT MERGE EVERY spy_5m_*.csv: backtest/data holds ~78 of them and they are a
    FEED PATCHWORK, not one dataset. The daily family carries offset-aware stamps
    ("2026-05-19 04:00:00-04:00") while older caches carry NAIVE ones
    ("2025-01-02 10:30:00"). Concatenating the two raises on parse -- and if it had
    not raised, a naive/aware join is precisely the DST frame artifact that produced
    silent winter look-ahead once already (lib/et_frame.py exists because of it).

    WHY NOT PIN ONE FILENAME: a new cumulative file lands every session at ~14:16 MT.
    A pinned name would have frozen this shadow at its build date, finding no bars for
    every later session while still exiting 0.

    So: among files whose FIRST data row is offset-aware, take the one with the latest
    end-date in its name. Those files are cumulative, so the newest contains the rest.
    """
    best, best_end = None, ""
    for f in sorted(glob.glob(BARS_GLOB)):
        m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", f)
        if not m:
            continue                                     # supplements / odd names
        try:
            with open(f, encoding="utf-8") as fh:
                fh.readline()
                first = fh.readline().split(",")[0]
        except OSError:
            continue
        if not re.search(r"[+-]\d{2}:\d{2}$", first):
            continue                                     # naive stratum -- do not mix
        if m.group(1) > best_end:
            best, best_end = f, m.group(1)
    if best is None:
        raise SystemExit(f"[trendline-shadow] FATAL: no offset-aware bar file matched {BARS_GLOB}")
    d = pd.read_csv(best)
    d["ts"] = pd.to_datetime(d["timestamp_et"])
    d = d.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    d["day"] = d["ts"].dt.date.astype(str)
    d.attrs["source"] = Path(best).name
    return d


def _events_for_session(day: pd.DataFrame, date_iso: str) -> list:
    """Walk one session forward, emitting geometry events with no look-ahead."""
    day = day.reset_index(drop=True)
    day["timestamp_unix"] = (day["ts"].astype("int64") // 10**9)
    rows, lines, state = [], [], {}

    for i in range(len(day)):
        # ---- refit on PRIOR bars only (C6: never include the bar being judged)
        if i >= MIN_BARS_BEFORE_FIT and i % REFIT_EVERY_BARS == 0:
            try:
                lines = detect_trendlines(day.iloc[:i])
            except Exception:                            # noqa: BLE001 - shadow must never crash a run
                lines = []

        bar = day.iloc[i]
        ts = int(bar["timestamp_unix"])
        for ln in lines:
            proj = ln.price_at(ts)
            if not (proj == proj) or proj <= 0:          # NaN guard
                continue
            key = (ln.direction, round(ln.slope_per_sec, 10), round(ln.intercept_price, 4))
            st = state.setdefault(key, {"broken": False, "reported": set()})

            # ---- classify this bar against this line
            asc = ln.direction == "ascending"
            touched = (bar["low"] - TOUCH_TOL_USD) <= proj <= (bar["high"] + TOUCH_TOL_USD)
            broke = (bar["close"] < proj) if asc else (bar["close"] > proj)

            ev = None
            if not st["broken"] and broke:
                st["broken"] = True
                ev = "BREAK"
            elif st["broken"] and touched:
                # came back to the line from the far side
                ev = "REJECT" if broke else "RETEST"
            elif not st["broken"] and touched:
                ev = "TOUCH"

            if ev is None or ev in st["reported"]:
                continue
            if ev in ("TOUCH",):                          # touches repeat; keep them all
                pass
            else:
                st["reported"].add(ev)

            row = {
                "date": date_iso, "ts_et": bar["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
                "event": ev, "direction": ln.direction, "flavor": "wick",
                "line_price": round(proj, 2), "bar_close": round(float(bar["close"]), 2),
                "bar_high": round(float(bar["high"]), 2), "bar_low": round(float(bar["low"]), 2),
                "touch_count": ln.touch_count, "r_squared": round(ln.r_squared, 4),
                "slope_per_hour": round(ln.slope_per_hour(), 4),
                "anchors": [{"ts": int(t), "price": round(float(p), 2)} for t, p in ln.anchor_points],
                "bar_idx": i,
            }
            # Which way is favourable does NOT depend on the forward window, so it
            # is decided ONCE, here. It used to be assigned INSIDE the loop below and
            # after a `continue`, so an event on the final bars of a session -- where
            # there are no forward bars -- never got a bias at all, and the theoretical
            # trade raised KeyError. An invariant belongs outside the loop that reads it.
            bearish = (
                (ln.direction == "ascending" and ev in ("BREAK", "REJECT"))
                or (ln.direction == "descending" and ev in ("REJECT", "TOUCH"))
            )
            row["bias"] = "bearish" if bearish else "bullish"

            # ---- forward MFE/MAE. This DOES look ahead; it is the measurement and
            #      is never available to a decision, only to this ledger.
            close = float(bar["close"])
            for w in FORWARD_WINDOWS:
                fwd = day.iloc[i + 1: i + 1 + w]
                if len(fwd) == 0:
                    row[f"mfe_{w*5}m"] = None
                    row[f"mae_{w*5}m"] = None
                    continue
                up = float(fwd["high"].max()) - close
                dn = float(fwd["low"].min()) - close
                row[f"mfe_{w*5}m"] = round(-dn if bearish else up, 2)
                row[f"mae_{w*5}m"] = round(up if bearish else -dn, 2)

            # THE LINE AS AN EXTRA GATE: only a real line, only a tradeable shape.
            # The len(day) guard matters: an event on the session's final bar has
            # nothing to walk forward into. Logging it as a flat 0.0 would pad the
            # sample with non-trades and drag any measured edge toward zero for free.
            qualifies = ((ln.direction, ev) in THEO_EVENTS
                         and ln.touch_count >= THEO_MIN_TOUCHES
                         and ln.r_squared >= THEO_MIN_R2
                         and i + 1 < len(day))
            row["theo_qualifies"] = bool(qualifies)
            if qualifies:
                tr = _theoretical_trade(day, i, bearish=row["bias"] == "bearish")
                row["theo_points"] = tr["points"]
                row["theo_outcome"] = tr["outcome"]
                row["theo_bars_held"] = tr["bars_held"]
            rows.append(row)
    return rows



# --- THEORETICAL TRADES (J, 2026-08-20: "it's gonna take theoretical trades that
# --- are influenced by the line, like the line's an extra GATE") ----------------
# The line is scored as an EXTRA GATE, not as a standalone signal: a qualifying
# event opens a theoretical position and it is walked forward bar by bar under the
# engine's own exit shape. Order of arrival matters, so this is simulated on the
# bars rather than inferred from MFE/MAE (which cannot say which came first).
#
# QUALITY BAR -- a line has to be a real line before its break means anything.
# Both thresholds are stated here so a future A/B can vary them explicitly rather
# than discovering them by accident.
THEO_MIN_TOUCHES = 3
THEO_MIN_R2 = 0.70
THEO_TP_POINTS = 1.00      # ~TP1 shape in SPY points
THEO_STOP_POINTS = 0.50    # chart-stop shape
THEO_TIME_STOP_BARS = 12   # 60 minutes

# Only these shapes are tradeable reads. An ascending line BREAKING or being
# REJECTED from below is J's setup; a descending line rejected is the engine's
# existing bear shape. A plain TOUCH is context, not a trigger.
THEO_EVENTS = {("ascending", "BREAK"), ("ascending", "REJECT"),
               ("descending", "REJECT")}


def _theoretical_trade(day, i: int, bearish: bool) -> dict:
    """Walk the position forward from bar i+1. TP / stop / time-stop, first to hit."""
    entry = float(day.iloc[i]["close"])
    for k in range(1, THEO_TIME_STOP_BARS + 1):
        if i + k >= len(day):
            break
        b = day.iloc[i + k]
        hi, lo = float(b["high"]), float(b["low"])
        fav = (entry - lo) if bearish else (hi - entry)
        adv = (hi - entry) if bearish else (entry - lo)
        # Stop checked FIRST within a bar: the pessimistic assumption, since we
        # cannot know intrabar order. Never flatter the theoretical trade.
        if adv >= THEO_STOP_POINTS:
            return {"outcome": "stop", "points": -THEO_STOP_POINTS, "bars_held": k}
        if fav >= THEO_TP_POINTS:
            return {"outcome": "tp", "points": THEO_TP_POINTS, "bars_held": k}
    last = day.iloc[min(i + THEO_TIME_STOP_BARS, len(day) - 1)]
    pts = (entry - float(last["close"])) if bearish else (float(last["close"]) - entry)
    return {"outcome": "time_stop", "points": round(pts, 2),
            "bars_held": min(THEO_TIME_STOP_BARS, len(day) - 1 - i)}


def daily_rollup(date_iso: str, path: Path = None) -> dict:
    """The answer to 'did we see any trendlines today, and how would we have acted?'

    Consumed by the EOD report. Returns zeros-with-a-reason rather than an empty
    dict when nothing fired, so the EOD line is never silently blank.
    """
    p = path or OUT
    rows = []
    try:
        for line in p.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("date") == date_iso:
                rows.append(r)
    except OSError:
        return {"date": date_iso, "logged": False, "reason": "shadow ledger unreadable"}

    if not rows:
        return {"date": date_iso, "logged": False, "reason": "no events logged for this date"}

    theo = [r for r in rows if r.get("theo_points") is not None]
    wins = [r for r in theo if r["theo_points"] > 0]
    total = round(sum(r["theo_points"] for r in theo), 2)
    lines_seen = {(r["direction"], r["line_price"], r["touch_count"]) for r in rows}
    return {
        "date": date_iso, "logged": True,
        "events": len(rows),
        "distinct_lines": len(lines_seen),
        "ascending": sum(1 for r in rows if r["direction"] == "ascending"),
        "descending": sum(1 for r in rows if r["direction"] == "descending"),
        "breaks": sum(1 for r in rows if r["event"] == "BREAK"),
        "rejects": sum(1 for r in rows if r["event"] == "REJECT"),
        "theo_trades": len(theo),
        "theo_wins": len(wins),
        "theo_wr": round(len(wins) / len(theo), 3) if theo else None,
        "theo_points": total,
        "theo_points_per_trade": round(total / len(theo), 3) if theo else None,
        "best": max((r["theo_points"] for r in theo), default=None),
        "worst": min((r["theo_points"] for r in theo), default=None),
        "note": "SHADOW ONLY -- no order was placed and no live decision saw this.",
    }


def week_audit(end_date: str, sessions: int = 5, path: Path = None) -> dict:
    """Rolling audit over the last N SESSIONS present in the ledger, ending at end_date.

    Sessions, not calendar days: a week that contains a holiday still gets five
    trading days of evidence rather than four.

    The observed number is deliberately reported next to the RANDOM-ENTRY NULL
    (2026-08-20: standalone line trades ran +0.041 pts/trade against a null median
    of -0.008, but the session-clustered 95% CI was [-0.039, +0.124] -- ABOVE null,
    NOT distinguishable from zero, and smaller than the SPY 0DTE bid-ask spread).
    Anything here is EVIDENCE ACCUMULATING, never a green light.
    """
    p = path or OUT
    rows = []
    try:
        for line in p.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("date") and r["date"] <= end_date:
                rows.append(r)
    except OSError:
        return {"sessions": 0, "reason": "shadow ledger unreadable"}

    dates = sorted({r["date"] for r in rows})[-sessions:]
    win = [r for r in rows if r["date"] in dates]
    theo = [r for r in win if r.get("theo_points") is not None]
    pts = [r["theo_points"] for r in theo]
    return {
        "sessions": len(dates),
        "from": dates[0] if dates else None, "to": dates[-1] if dates else None,
        "events": len(win),
        "theo_trades": len(theo),
        "theo_wr": round(sum(1 for v in pts if v > 0) / len(pts), 3) if pts else None,
        "theo_points": round(sum(pts), 2) if pts else 0.0,
        "theo_points_per_trade": round(sum(pts) / len(pts), 4) if pts else None,
        "by_session": {d: round(sum(r["theo_points"] for r in theo if r["date"] == d), 2)
                       for d in dates},
    }


def baseline(end_date: str, sessions: int = 5, path: Path = None) -> dict:
    """Whole-sample context for a trailing window, so a hot streak cannot read as edge.

    THE TRAP THIS CLOSES (found 2026-08-20, before this ever reached J)
      The first version of the EOD section reported the trailing 5 sessions alone:
      "56 trades, WR 64%, +17.14 pts". True, and deeply misleading -- that window is
      the BEST of all 61 in the sample, one session supplied 48% of it, and across
      the whole sample the top 3 sessions contribute MORE than 100% of total profit
      (i.e. everything else nets negative). 46% of all 5-session windows are losers.

      A trailing window with no baseline is a cherry-picker that re-picks itself
      every day, and the reader has no way to see it. So every trailing number this
      module publishes ships next to its percentile and its concentration.
    """
    p = path or OUT
    rows = []
    try:
        for line in p.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("theo_points") is not None and r.get("date"):
                rows.append(r)
    except OSError:
        return {"ok": False, "reason": "shadow ledger unreadable"}
    if not rows:
        return {"ok": False, "reason": "no theoretical trades logged yet"}

    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r["theo_points"])
    dates = sorted(by_day)
    tot = sum(sum(v) for v in by_day.values())
    day_totals = sorted(sum(v) for v in by_day.values())

    # every trailing window of the same width, so "is this one special?" is answerable
    wins = []
    for i in range(len(dates) - sessions + 1):
        pts = [v for d in dates[i:i + sessions] for v in by_day[d]]
        if pts:
            wins.append(sum(pts) / len(pts))
    cur_dates = [d for d in dates if d <= end_date][-sessions:]
    cur_pts = [v for d in cur_dates for v in by_day[d]]
    cur = (sum(cur_pts) / len(cur_pts)) if cur_pts else None

    all_pts = [v for v in (x for vs in by_day.values() for x in vs)]
    top_share = None
    if cur_pts and sum(cur_pts) > 0:
        top_share = max(sum(by_day[d]) for d in cur_dates) / sum(cur_pts)
    return {
        "ok": True,
        "sessions_total": len(dates),
        "all_trades": len(all_pts),
        "all_wr": round(sum(1 for v in all_pts if v > 0) / len(all_pts), 3),
        "all_points_per_trade": round(tot / len(all_pts), 4),
        "sessions_positive": sum(1 for v in day_totals if v > 0),
        "top3_share_of_total": round(sum(day_totals[-3:]) / tot, 3) if tot else None,
        "windows": len(wins),
        "windows_negative": sum(1 for w in wins if w < 0),
        "window_percentile": (round(sum(1 for w in wins if w < cur) / len(wins), 3)
                              if wins and cur is not None else None),
        "top_session_share_of_window": round(top_share, 3) if top_share else None,
    }

def run(dates: list, out: Path = OUT) -> int:
    d = load_bars()
    print(f"[trendline-shadow] bars: {d.attrs['source']} "
          f"({len(d)} rows, {d['day'].nunique()} sessions)")
    out.parent.mkdir(parents=True, exist_ok=True)

    # idempotent: never double-log a session (the ladder-ledger lesson, 2026-08-20)
    seen = set()
    if out.exists():
        for line in out.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line).get("date"))
                except ValueError:
                    pass

    total = 0
    skipped = []
    with out.open("a", encoding="utf-8") as f:
        for date_iso in dates:
            if date_iso in seen:
                print(f"[trendline-shadow] {date_iso} already logged -- skipping")
                continue
            day = d[d.day == date_iso]
            if len(day) < MIN_BARS_BEFORE_FIT + 5:
                # Say WHY. A session skipped in silence is indistinguishable from a
                # session with no trendlines, and that is the whole failure this
                # ledger exists to prevent (C7).
                print(f"[trendline-shadow] {date_iso}: only {len(day)} bar(s) "
                      f"(need >= {MIN_BARS_BEFORE_FIT + 5}) -- SKIPPED, not empty")
                skipped.append(date_iso)
                continue
            rows = _events_for_session(day, date_iso)
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
            total += len(rows)
            print(f"[trendline-shadow] {date_iso}: {len(rows)} events")
    # relative_to raises for any path outside the repo (a tmp_path in tests, or a
    # ledger relocated to another drive). A cosmetic path shortening must never be
    # able to take down the run that produced the data.
    try:
        shown = out.relative_to(REPO)
    except ValueError:
        shown = out
    print(f"[trendline-shadow] wrote {total} event(s) -> {shown}")
    # Asking for ONE date and getting nothing is a FAILURE, not a quiet success:
    # it means the bar file for that session never landed. Exit non-zero so the
    # scheduled fire is visibly red instead of reporting a clean run.
    if len(dates) == 1 and dates[0] in skipped:
        print(f"[trendline-shadow] FAILED: no usable bars for {dates[0]}")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Shadow-log intraday trendline geometry. No entry effect.")
    ap.add_argument("--date")
    ap.add_argument("--seed", action="store_true", help="replay every session in the bar file")
    a = ap.parse_args()
    all_days = sorted(load_bars()["day"].unique())
    dates = all_days if a.seed else [a.date or all_days[-1]]
    return run(dates)


if __name__ == "__main__":
    raise SystemExit(main())
