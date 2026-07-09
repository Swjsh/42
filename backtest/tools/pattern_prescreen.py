"""pattern_prescreen.py — the C27 pre-screen: the cheap filter that saves weeks.

Runs every backtest.lib.patterns.registry rule over the cached SPY master history on
5m/15m/30m bars and reports, per (rule, timeframe): fire-rate (% of trading days that
fired at least once, fires/day), fires/month, a "cluster" concentration stat (what % of
all fires came from the busiest 5 days), and the C27 verdict:

    pct_days_fired > 80%    -> NOISE-KILL  (fires on almost every day -- not selective)
    fires_per_month < 2     -> TOO-RARE    (not enough signal to ever validate)
    else                    -> TESTABLE    (a real candidate for the battery)

Also splits every stat into a FULL-HISTORY window and a RECENT-90-CALENDAR-DAY window so
regime drift is visible (`drift_flag` = the verdict differs between the two windows).

NO P&L MATH HERE. Frequency/objectivity only — P&L belongs to the standard battery
(backtest_design_swarm.py canonical battery + discovery_shadow_ledger.py's FDR screen;
see markdown/research/PATTERN-GRAMMAR.md sec 3 for the exact handoff).

TIMESTAMP CONVENTION — a deliberate DEPARTURE from this codebase's wall-v1 default:
  The SPY master CSVs store a fixed "-04:00" offset year-round (see
  automation/state/frame-migration-evidence/DST-FRAME-AUDIT-2026-07-02.md). Most of the
  validated pipeline (orchestrator.py, family_grind, build_rth) stays on the naive
  "wall-v1" parse for BYTE-FOR-BYTE parity with an already-validated scorecard. This tool
  has no such baseline to preserve (it is brand new), and wall-v1 silently clips the
  first true RTH hour on ~35% of trading days (winter) — directly verified: 2025-01-02's
  first row parses as wall-clock 10:30 under wall-v1 vs the true 09:30 RTH open under a
  correct parse. A frequency-only screen would be measurably distorted by that clip, so
  this tool parses timestamps CORRECTLY throughout (`pd.to_datetime(..., utc=True)
  .dt.tz_convert("America/New_York")`) instead. Consequence: a rule's exact fire count
  here is a TRIAGE estimate, not a byte-exact preview of what backtest_design_swarm.py's
  (currently wall-v1) battery will later measure for the same rule — any TESTABLE rule
  gets re-measured there before anything is claimed as an edge.

Run (from repo root):
  backtest\\.venv\\Scripts\\python.exe backtest\\tools\\pattern_prescreen.py
  backtest\\.venv\\Scripts\\python.exe backtest\\tools\\pattern_prescreen.py --timeframes 5m,15m
  backtest\\.venv\\Scripts\\python.exe backtest\\tools\\pattern_prescreen.py --max-bars 4000  (fast dev run)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from crypto.lib.bar import Bar  # noqa: E402
from lib.patterns import PatternContext, REGISTRY, evaluate_rule_over_range, levels_from_level_memory  # noqa: E402
from lib.patterns.grammar import GrammarHit  # noqa: E402
from lib.watchers.level_memory import LevelMemory  # noqa: E402

DATA_DIR = REPO / "backtest" / "data"
OUT_PATH = REPO / "analysis" / "recommendations" / "pattern-prescreen.json"

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

DEFAULT_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "30m")
TIMEFRAME_MINUTES: dict = {"5m": 5, "15m": 15, "30m": 30}

# C27 verdict thresholds (per the module docstring)
NOISE_KILL_PCT_DAYS = 80.0
TOO_RARE_FIRES_PER_MONTH = 2.0
TRADING_DAYS_PER_MONTH = 21.0   # standard approximation used for fires_per_month

# level_memory calibration (matches setup/scripts/level_memory_producer.py's own
# defaults — same primitive, run once per historical day instead of once live)
LEVEL_MEMORY_LOOKBACK_DAYS = 10
LEVEL_MEMORY_MIN_MEMORY = 20.0

RECENT_WINDOW_DAYS = 90


# ── data loading ────────────────────────────────────────────────────────────────

def find_master_csv(data_dir: Path = DATA_DIR) -> Path:
    """The widest-history spy_5m_{start}_{end}.csv on disk (earliest start, then
    latest end among ties) — avoids hardcoding a filename that goes stale as new
    extends land."""
    pattern = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_\w+)?\.csv$")
    candidates = []
    for p in data_dir.glob("spy_5m_*.csv"):
        m = pattern.match(p.name)
        if m:
            candidates.append((m.group(1), m.group(2), p))
    if not candidates:
        raise FileNotFoundError(f"no spy_5m_*.csv under {data_dir}")
    candidates.sort(key=lambda c: c[0])
    earliest_start = candidates[0][0]
    tied = sorted((c for c in candidates if c[0] == earliest_start), key=lambda c: c[1])
    return tied[-1][2]


def load_master(csv_path: Path, *, max_rows: Optional[int] = None) -> pd.DataFrame:
    """Raw master frame; `timestamp_et` parsed CORRECTLY (tz-aware ET) — see module
    docstring's TIMESTAMP CONVENTION note. `date`/`time_et` helper columns added."""
    df = pd.read_csv(csv_path, nrows=max_rows)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(timestamp_et=ts, date=ts.dt.date, time_et=ts.dt.time)
    return df


def slice_rth(df: pd.DataFrame) -> pd.DataFrame:
    mask = (df["time_et"] >= RTH_OPEN) & (df["time_et"] < RTH_CLOSE)
    return df.loc[mask].reset_index(drop=True)


def resample_timeframe(rth_5m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Per-session OHLCV resample (never bleeds across a day boundary). No-op for 5m."""
    if minutes == 5:
        return rth_5m
    frames = []
    for _, grp in rth_5m.groupby("date", sort=True):
        g = grp.set_index("timestamp_et").sort_index()
        agg = g.resample(f"{minutes}min", origin="start", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        )
        agg = agg.dropna(subset=["open"]).reset_index()
        agg["date"] = grp["date"].iloc[0]
        agg["time_et"] = agg["timestamp_et"].dt.time
        frames.append(agg)
    if not frames:
        return rth_5m.iloc[0:0]
    return pd.concat(frames, ignore_index=True)


def df_to_bars(df: pd.DataFrame, *, granularity_seconds: int, source: str) -> tuple[Bar, ...]:
    bars = []
    for row in df.itertuples(index=False):
        bars.append(Bar(
            open_time=row.timestamp_et.to_pydatetime(),
            open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close),
            volume=float(row.volume), granularity_seconds=granularity_seconds, source=source,
        ))
    return tuple(bars)


def build_levels_by_date(
    rth_5m: pd.DataFrame,
    *,
    lookback_days: int = LEVEL_MEMORY_LOOKBACK_DAYS,
    min_memory: float = LEVEL_MEMORY_MIN_MEMORY,
) -> dict:
    """ONE LevelMemory computation per trading day, using ONLY bars strictly BEFORE
    that day (today's level set fixed at today's open — see context.py's docstring on
    why this is causal by construction). Same primitive
    setup/scripts/level_memory_producer.py runs live; here it is re-run once per
    historical day. LevelMemory does its own tz parsing internally — feed it the
    already-correctly-tz-aware `timestamp_et` column (do NOT re-strip it; see module
    docstring)."""
    dates = sorted(rth_5m["date"].unique())
    out: dict = {}
    for d in dates:
        prior = rth_5m[rth_5m["date"] < d]
        if len(prior) < 50:
            out[d] = ()
            continue
        lm = LevelMemory(prior[["timestamp_et", "open", "high", "low", "close", "volume"]])
        up_to = len(lm.df) - 1
        raw = lm.levels_at(up_to, lookback_days=lookback_days)
        keep = [lv for lv in raw if lv.memory_score >= min_memory]
        out[d] = levels_from_level_memory(keep)
    return out


# ── stats + verdict ───────────────────────────────────────────────────────────────

def compute_stats(
    hits: list[GrammarHit],
    bars: tuple[Bar, ...],
    *,
    window_start: Optional[dt.date] = None,
    window_end: Optional[dt.date] = None,
) -> dict:
    """Frequency/objectivity stats only. `window_start`/`window_end` (inclusive) narrow
    BOTH the trading-day denominator and the hit set to that date range — used for the
    90-day recent-window split."""
    all_dates = sorted({b.open_time.date() for b in bars})
    if window_start is not None:
        all_dates = [d for d in all_dates if d >= window_start]
    if window_end is not None:
        all_dates = [d for d in all_dates if d <= window_end]
    n_days = len(all_dates)
    if n_days == 0:
        return {
            "n_trading_days": 0, "total_fires": 0, "days_with_fire": 0, "pct_days_fired": 0.0,
            "fires_per_day": 0.0, "fires_per_month": 0.0, "top5_day_concentration_pct": 0.0,
            "max_fires_single_day": 0,
        }
    date_set = set(all_dates)
    fires_by_date: dict = {}
    for h in hits:
        d = bars[h.bar_index].open_time.date()
        if d not in date_set:
            continue
        fires_by_date[d] = fires_by_date.get(d, 0) + 1
    total_fires = sum(fires_by_date.values())
    days_with_fire = len(fires_by_date)
    counts_desc = sorted(fires_by_date.values(), reverse=True)
    top5_pct = (sum(counts_desc[:5]) / total_fires * 100.0) if total_fires else 0.0
    return {
        "n_trading_days": n_days,
        "total_fires": total_fires,
        "days_with_fire": days_with_fire,
        "pct_days_fired": round(days_with_fire / n_days * 100.0, 2),
        "fires_per_day": round(total_fires / n_days, 3),
        "fires_per_month": round(total_fires / (n_days / TRADING_DAYS_PER_MONTH), 3),
        "top5_day_concentration_pct": round(top5_pct, 1),
        "max_fires_single_day": counts_desc[0] if counts_desc else 0,
    }


def classify_verdict(pct_days_fired: float, fires_per_month: float) -> str:
    if pct_days_fired > NOISE_KILL_PCT_DAYS:
        return "NOISE-KILL"
    if fires_per_month < TOO_RARE_FIRES_PER_MONTH:
        return "TOO-RARE"
    return "TESTABLE"


# ── orchestration ──────────────────────────────────────────────────────────────────

def run_prescreen(
    *, data_dir: Path = DATA_DIR, timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    max_rows: Optional[int] = None, recent_window_days: int = RECENT_WINDOW_DAYS,
) -> dict:
    t_start = time.time()
    csv_path = find_master_csv(data_dir)
    raw = load_master(csv_path, max_rows=max_rows)
    rth_5m = slice_rth(raw)
    if rth_5m.empty:
        raise RuntimeError(f"no RTH bars found in {csv_path}")

    levels_by_date = build_levels_by_date(rth_5m)
    last_date = rth_5m["date"].max()
    recent_start = last_date - dt.timedelta(days=recent_window_days)

    contexts: dict = {}
    for tf in timeframes:
        minutes = TIMEFRAME_MINUTES[tf]
        resampled = resample_timeframe(rth_5m, minutes)
        bars = df_to_bars(resampled, granularity_seconds=minutes * 60, source=f"spy_{tf}")
        contexts[tf] = PatternContext.build(bars, levels_by_date=levels_by_date)

    results: list[dict] = []
    for tf in timeframes:
        ctx = contexts[tf]
        for rule in REGISTRY:
            hits = evaluate_rule_over_range(rule, ctx, timeframe=tf)
            full = compute_stats(hits, ctx.bars)
            recent = compute_stats(hits, ctx.bars, window_start=recent_start)
            verdict_full = classify_verdict(full["pct_days_fired"], full["fires_per_month"])
            verdict_recent = (
                classify_verdict(recent["pct_days_fired"], recent["fires_per_month"])
                if recent["n_trading_days"] > 0 else None
            )
            results.append({
                "rule": rule.name, "tier": rule.tier, "timeframe": tf, "direction": rule.direction,
                "verdict": verdict_full, "verdict_recent_90d": verdict_recent,
                "drift_flag": verdict_recent is not None and verdict_recent != verdict_full,
                "full_history": full, "recent_90d": recent,
            })

    testable_ranked = sorted(
        (r for r in results if r["verdict"] == "TESTABLE"),
        key=lambda r: r["full_history"]["fires_per_day"], reverse=True,
    )

    verdict_counts: dict = {}
    for r in results:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - t_start, 1),
        "data_source": str(csv_path.relative_to(REPO)),
        "date_range": {"start": str(rth_5m["date"].min()), "end": str(last_date)},
        "recent_window_days": recent_window_days,
        "recent_window_start": str(recent_start),
        "timeframes": list(timeframes),
        "n_rules": len(REGISTRY),
        "verdict_thresholds": {
            "noise_kill_pct_days_gt": NOISE_KILL_PCT_DAYS,
            "too_rare_fires_per_month_lt": TOO_RARE_FIRES_PER_MONTH,
        },
        "verdict_counts_full_history": verdict_counts,
        "results": results,
        "ranked_testable": [
            {"rule": r["rule"], "timeframe": r["timeframe"], "tier": r["tier"],
             "fires_per_day": r["full_history"]["fires_per_day"],
             "pct_days_fired": r["full_history"]["pct_days_fired"]}
            for r in testable_ranked
        ],
    }
    return out


def print_table(out: dict) -> None:
    header = f"{'rule':30s} {'tf':4s} {'verdict':11s} {'%days':>7s} {'fires/d':>8s} {'fires/mo':>9s} {'top5%':>6s} {'recent90d':>10s}"
    print(header)
    print("-" * len(header))
    for r in out["results"]:
        f = r["full_history"]
        print(
            f"{r['rule']:30s} {r['timeframe']:4s} {r['verdict']:11s} "
            f"{f['pct_days_fired']:7.1f} {f['fires_per_day']:8.3f} {f['fires_per_month']:9.2f} "
            f"{f['top5_day_concentration_pct']:6.1f} {str(r['verdict_recent_90d']):>10s}"
            f"{'  <-- DRIFT' if r['drift_flag'] else ''}"
        )
    print()
    print("verdict counts (full history):", out["verdict_counts_full_history"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    ap.add_argument("--max-rows", type=int, default=None, help="truncate the master CSV read (fast dev runs)")
    ap.add_argument("--recent-days", type=int, default=RECENT_WINDOW_DAYS)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    timeframes = tuple(t.strip() for t in args.timeframes.split(",") if t.strip())
    unknown = set(timeframes) - set(TIMEFRAME_MINUTES)
    if unknown:
        raise SystemExit(f"unknown timeframe(s) {unknown}; expected subset of {set(TIMEFRAME_MINUTES)}")

    out = run_prescreen(timeframes=timeframes, max_rows=args.max_rows, recent_window_days=args.recent_days)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print_table(out)
    print(f"\nwrote {out_path.relative_to(REPO) if out_path.is_relative_to(REPO) else out_path}")
    print(f"elapsed: {out['elapsed_seconds']}s over {out['date_range']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
