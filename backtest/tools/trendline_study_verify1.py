"""trendline_study_verify1.py -- SKEPTIC verification pass on the trendline shadow-lane
verdict (analysis/trendlines/shadow-verdict.json), for the finding
"trendline-capability-and-shadow" (2026-09-03).

Read-only w.r.t. every existing file. Writes nothing except stdout (captured by the
caller into the verify note). Never touches trading-path files or the shadow ledger.

What this does, in order:
 1. Independently reload analysis/trendlines/shadow-ledger.jsonl and recompute whole-sample
    n / WR / pts-per-trade for the THEO_EVENTS set, both matching the reported end_date
    (2026-09-02, 73 sessions) and on the full ledger through today (74 sessions) -- to check
    whether the reported verdict is current.
 2. Re-run the session-clustered day-level bootstrap CI independently (own RNG stream,
    higher n_boot) and compare to the stored CI.
 3. Remove the top-3 sessions by total theo profit and recompute mean + CI on the remainder,
    to size how much of the "above zero" reading survives without them.
 4. Time-of-day check: bucket theo trades by ET hour, report n/WR/pts per bucket, and compare
    against a baseline of ALL 5m bars' next-30m realized move at the same hour-of-day (same
    74 sessions) to see whether the "edge" just tracks a volatility/drift-by-hour pattern
    rather than the trendline geometry specifically.
 5. Threshold robustness: re-run the actual detector (backtest/lib/trendlines.detect_trendlines)
    and the shadow's own event classifier (setup/scripts/trendline_shadow._events_for_session)
    with TOUCH_TOL_USD and trendlines.TOUCH_TOLERANCE_USD both scaled by 0.5x and 2x (both
    knobs move together since the shadow lane never varies them independently), over the SAME
    74 sessions the live ledger covers, and report n_theo_trades / pts_per_trade / WR at each
    setting next to the baseline (1.0x) reproduction.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trendline_study_verify1.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))
sys.path.insert(0, str(SCRIPTS))

LEDGER = REPO / "analysis" / "trendlines" / "shadow-ledger.jsonl"

THEO_EVENTS = {("ascending", "BREAK"), ("ascending", "REJECT"), ("descending", "REJECT")}


def load_ledger():
    rows = []
    for line in LEDGER.open(encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def theo_rows(rows, end_date=None):
    out = [r for r in rows if r.get("theo_points") is not None and r.get("date")]
    if end_date:
        out = [r for r in out if r["date"] <= end_date]
    return out


def whole_sample_stats(theo):
    by_day = {}
    for r in theo:
        by_day.setdefault(r["date"], []).append(r["theo_points"])
    n = len(theo)
    wr = sum(1 for r in theo if r["theo_points"] > 0) / n if n else None
    ppt = sum(r["theo_points"] for r in theo) / n if n else None
    day_totals = {d: sum(v) for d, v in by_day.items()}
    tot = sum(day_totals.values())
    top3 = sorted(day_totals.values())[-3:]
    top3_share = sum(top3) / tot if tot else None
    return {
        "n_sessions": len(by_day), "n_trades": n, "wr": round(wr, 4) if wr is not None else None,
        "pts_per_trade": round(ppt, 4) if ppt is not None else None,
        "top3_share_of_total": round(top3_share, 4) if top3_share is not None else None,
        "by_day": by_day, "day_totals": day_totals, "total_pts": round(tot, 3),
    }


def session_clustered_ci(by_day: dict, n_boot=5000, seed=20260903, ci_level=0.95):
    dates = sorted(by_day.keys())
    n_days = len(dates)
    if n_days < 2:
        return {"n_sessions": n_days, "mean": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    day_lists = [by_day[d] for d in dates]
    means = []
    for _ in range(n_boot):
        picks = [day_lists[rng.randrange(n_days)] for _ in range(n_days)]
        pooled = [p for day in picks for p in day]
        if pooled:
            means.append(sum(pooled) / len(pooled))
    means.sort()
    n = len(means)
    lo = int((1 - ci_level) / 2 * n)
    hi = min(int((1 + ci_level) / 2 * n) - 1, n - 1)
    return {
        "n_sessions": n_days, "n_boot": n_boot, "seed": seed,
        "mean": round(sum(means) / n, 4),
        "ci_low": round(means[lo], 4), "ci_high": round(means[hi], 4),
    }


def drop_top_n_sessions(by_day: dict, n_drop=3):
    ordered = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    dropped = dict(ordered[:n_drop])
    remaining = dict(ordered[n_drop:])
    return remaining, dropped


def hour_bucket(ts_et: str) -> str:
    # "2026-09-03T10:55:00" -> "10"
    return ts_et.split("T")[1][:2]


def time_of_day_theo(theo):
    buckets = {}
    for r in theo:
        h = hour_bucket(r["ts_et"])
        buckets.setdefault(h, []).append(r["theo_points"])
    out = {}
    for h, pts in sorted(buckets.items()):
        n = len(pts)
        out[h] = {
            "n": n, "wr": round(sum(1 for p in pts if p > 0) / n, 3),
            "pts_per_trade": round(sum(pts) / n, 4), "total_pts": round(sum(pts), 2),
        }
    return out


def load_bars_all():
    import pandas as pd
    f = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-03.csv"
    d = pd.read_csv(f)
    d["ts"] = pd.to_datetime(d["timestamp_et"])
    d = d.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    d["day"] = d["ts"].dt.date.astype(str)
    d["timestamp_unix"] = (d["ts"].astype("int64") // 10 ** 9)
    return d


def time_of_day_baseline(d, ledger_dates):
    """For every 5m bar in the same session set, the realized |next-30m move|,
    bucketed by hour-of-day. NOT direction-matched to any trendline bias -- this is
    a plain 'how much does price move in this hour, on average, all days' baseline,
    to see whether theo-trade hours are just the naturally highest-realized-range hours."""
    d = d[d["day"].isin(ledger_dates)].reset_index(drop=True)
    by_hour = {}
    for day, grp in d.groupby("day"):
        grp = grp.reset_index(drop=True)
        n = len(grp)
        for i in range(n):
            h = grp.loc[i, "ts"].strftime("%H")
            close = float(grp.loc[i, "close"])
            fwd = grp.iloc[i + 1: i + 1 + 6]  # 30m
            if len(fwd) == 0:
                continue
            up = float(fwd["high"].max()) - close
            dn = close - float(fwd["low"].min())
            move = max(up, dn)  # realized range, undirected
            by_hour.setdefault(h, []).append(move)
    out = {}
    for h, vals in sorted(by_hour.items()):
        out[h] = {"n_bars": len(vals), "mean_abs_30m_move": round(sum(vals) / len(vals), 4)}
    return out


def rerun_with_tolerance(d, dates, tol_scale: float, max_seconds=90):
    """Re-run the shadow's own event/theo classifier with TOUCH_TOL_USD and
    trendlines.TOUCH_TOLERANCE_USD both scaled by tol_scale. Imports the real modules and
    monkeypatches their module-level tolerance constants for the duration of this call only,
    then restores them -- never leaves global state mutated for any other importer in this
    process."""
    import trendlines as TL
    import trendline_shadow as TS

    orig_tl_tol = TL.TOUCH_TOLERANCE_USD
    orig_ts_tol = TS.TOUCH_TOL_USD
    TL.TOUCH_TOLERANCE_USD = round(orig_tl_tol * tol_scale, 4)
    TS.TOUCH_TOL_USD = round(orig_ts_tol * tol_scale, 4)
    t0 = time.time()
    all_theo = []
    try:
        for date_iso in dates:
            if time.time() - t0 > max_seconds:
                print(f"    [rerun tol={tol_scale}x] time budget hit after {date_iso}; "
                      f"partial run over {len(all_theo)} trades so far this pass")
                break
            day = d[d.day == date_iso]
            if len(day) < TS.MIN_BARS_BEFORE_FIT + 5:
                continue
            rows = TS._events_for_session(day, date_iso)
            for r in rows:
                if r.get("theo_qualifies") and (r["direction"], r["event"]) in THEO_EVENTS:
                    all_theo.append(r)
    finally:
        TL.TOUCH_TOLERANCE_USD = orig_tl_tol
        TS.TOUCH_TOL_USD = orig_ts_tol
    return all_theo


def main():
    rows = load_ledger()
    theo_full = theo_rows(rows)  # through today, 2026-09-03
    theo_reported = theo_rows(rows, end_date="2026-09-02")  # matches shadow-verdict.json

    print("=" * 70)
    print("1. REPRODUCE reported verdict (end_date=2026-09-02)")
    ss_reported = whole_sample_stats(theo_reported)
    print({k: v for k, v in ss_reported.items() if k not in ("by_day", "day_totals")})
    ci_reported = session_clustered_ci(ss_reported["by_day"])
    print("independent CI recompute (own RNG, n_boot=5000):", ci_reported)
    print("stored verdict CI was: [-0.0301, 0.1177], mean 0.0386")

    print("=" * 70)
    print("2. FULL ledger through today (2026-09-03) -- is the stored verdict current?")
    ss_full = whole_sample_stats(theo_full)
    print({k: v for k, v in ss_full.items() if k not in ("by_day", "day_totals")})
    ci_full = session_clustered_ci(ss_full["by_day"])
    print("CI on full ledger:", ci_full)

    print("=" * 70)
    print("3. Drop top-3 sessions by profit (from the FULL ledger's day totals)")
    remaining, dropped = drop_top_n_sessions(ss_full["by_day"], n_drop=3)
    print("dropped sessions (date: total_pts):", {k: round(sum(v), 2) for k, v in dropped.items()})
    n_remaining = sum(len(v) for v in remaining.values())
    pts_remaining = sum(sum(v) for v in remaining.values())
    print(f"remaining: {len(remaining)} sessions, {n_remaining} trades, "
          f"pts/trade = {round(pts_remaining / n_remaining, 4) if n_remaining else None}, "
          f"total_pts = {round(pts_remaining, 2)}")
    ci_remaining = session_clustered_ci(remaining)
    print("CI without top-3:", ci_remaining)

    print("=" * 70)
    print("4. Time-of-day: theo trades by ET hour")
    tod = time_of_day_theo(theo_full)
    for h, v in tod.items():
        print(f"  {h}:00  {v}")

    print("  ... baseline: mean |30m realized move|, ALL 5m bars, same 74 sessions")
    d = load_bars_all()
    ledger_dates = sorted(ss_full["by_day"].keys())
    tod_base = time_of_day_baseline(d, ledger_dates)
    for h, v in tod_base.items():
        print(f"  {h}:00  {v}")

    print("=" * 70)
    print("5. Threshold robustness -- rerun detector at 0.5x / 1.0x / 2.0x touch tolerance")
    print(f"   over the same {len(ledger_dates)} sessions as the live ledger (time-boxed)")
    for scale in (0.5, 1.0, 2.0):
        t0 = time.time()
        theo = rerun_with_tolerance(d, ledger_dates, scale, max_seconds=90)
        elapsed = round(time.time() - t0, 1)
        if theo:
            n = len(theo)
            wr = sum(1 for r in theo if r["theo_points"] > 0) / n
            ppt = sum(r["theo_points"] for r in theo) / n
            by_day = {}
            for r in theo:
                by_day.setdefault(r["date"], []).append(r["theo_points"])
            ci = session_clustered_ci(by_day, n_boot=2000)
            print(f"  tol x{scale}: n={n} wr={round(wr,3)} pts/trade={round(ppt,4)} "
                  f"ci={ (ci['ci_low'], ci['ci_high']) } sessions_covered={len(by_day)} "
                  f"elapsed={elapsed}s")
        else:
            print(f"  tol x{scale}: n=0 theo trades elapsed={elapsed}s")


if __name__ == "__main__":
    main()
