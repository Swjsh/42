"""Task 1.3 — Level-quality gym stage.

Reads the trailing N-day ledger (Phase 0) and the benchmark JSON (Phase 1),
emits GREEN / YELLOW / RED on level quality, writes a weekly scorecard, and
appends a Known-broken line to automation/overnight/STATUS.md on RED.

Verdict logic (based on distance-matched null respect lift — the robust signal):
  GREEN  : respect-lift vs DM-null > +2pp over the trailing window
  YELLOW : 0pp to +2pp
  RED    : <= 0pp (no conditional edge; this is the baseline finding)

Usage:
  python level_quality_gym.py           # uses trailing 30 days from ledger
  python level_quality_gym.py --days 60
  python level_quality_gym.py --week 2026-W24

OP-20 disclosure:
  N = days in trailing window. IS/OOS split: benchmark is the baseline (219 days);
  trailing window is the live forward measurement. Metric: respect-lift vs
  distance-matched null (headline number from benchmark). Real-fills authority
  would require option P&L data (L74); this measures SPY-space only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO / "analysis" / "level-quality" / "level-quality-ledger.jsonl"
BENCHMARK_PATH = REPO / "analysis" / "level-quality" / "level-quality-benchmark.json"
WEEKLY_DIR = REPO / "analysis" / "level-quality"
STATUS_PATH = REPO / "automation" / "overnight" / "STATUS.md"

# Verdict thresholds (distance-matched null respect lift in pp)
GREEN_THRESHOLD_PP = 2.0
YELLOW_THRESHOLD_PP = 0.0   # below this = RED


def load_ledger(days: int) -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    rows = []
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("date", "") >= cutoff:
                rows.append(r)
        except Exception:
            pass
    return sorted(rows, key=lambda x: x.get("date", ""))


def load_benchmark() -> dict:
    if not BENCHMARK_PATH.exists():
        raise FileNotFoundError(f"Benchmark JSON not found: {BENCHMARK_PATH}")
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def compute_trailing_metrics(rows: list[dict]) -> dict:
    """Aggregate trailing window metrics from ledger rows."""
    n_total_levels = sum(r.get("n_levels", 0) for r in rows)
    n_touched = sum(r.get("n_touched", 0) for r in rows)
    n_respect = sum(r.get("n_respect", 0) for r in rows)
    n_break = sum(r.get("n_break", 0) for r in rows)

    touch_rate = round(n_touched / n_total_levels, 4) if n_total_levels else None
    respect_rate = round(n_respect / n_touched, 4) if n_touched else None
    break_rate = round(n_break / n_touched, 4) if n_touched else None

    # Per-source breakdown
    by_source: dict[str, dict] = {}
    for row in rows:
        for src, sv in (row.get("by_source") or {}).items():
            if src not in by_source:
                by_source[src] = {"n": 0, "touched": 0, "respect": 0}
            n = sv.get("n", 0)
            t = int((sv.get("touch_rate") or 0) * n) if n else 0
            rs = int((sv.get("respect_rate_of_touched") or 0) * t) if t else 0
            by_source[src]["n"] += n
            by_source[src]["touched"] += t
            by_source[src]["respect"] += rs

    by_source_summary = {
        k: {
            "n": v["n"],
            "respect_rate": round(v["respect"] / v["touched"], 4) if v["touched"] else None,
        }
        for k, v in by_source.items()
    }

    return {
        "n_days": len(rows),
        "n_levels": n_total_levels,
        "n_touched": n_touched,
        "touch_rate": touch_rate,
        "respect_rate_of_touched": respect_rate,
        "break_rate_of_touched": break_rate,
        "by_source": by_source_summary,
    }


def make_verdict(trailing: dict, benchmark: dict) -> tuple[str, str]:
    """Return (verdict, explanation)."""
    # Use the distance-matched null as the baseline (the robust signal)
    dm_null_respect = (benchmark.get("headline", {})
                       .get("null_distance_matched", {})
                       .get("respect_rate_of_touched"))
    trailing_respect = trailing.get("respect_rate_of_touched")

    if trailing_respect is None or dm_null_respect is None:
        return "YELLOW", "Insufficient data to compute lift vs DM-null."

    lift_pp = round((trailing_respect - dm_null_respect) * 100, 1)

    if lift_pp > GREEN_THRESHOLD_PP:
        verdict = "GREEN"
        explanation = (
            f"Trailing respect-lift vs DM-null = +{lift_pp}pp (>{GREEN_THRESHOLD_PP}pp threshold). "
            f"Levels showing conditional edge."
        )
    elif lift_pp >= YELLOW_THRESHOLD_PP:
        verdict = "YELLOW"
        explanation = (
            f"Trailing respect-lift vs DM-null = +{lift_pp}pp (0 to +{GREEN_THRESHOLD_PP}pp). "
            f"Marginal conditional edge — watch trend."
        )
    else:
        verdict = "RED"
        explanation = (
            f"Trailing respect-lift vs DM-null = {lift_pp}pp (<= 0). "
            f"No conditional edge at level touches. Baseline finding confirmed."
        )

    return verdict, explanation


def write_weekly_md(
    week_label: str,
    trailing: dict,
    verdict: str,
    explanation: str,
    benchmark: dict,
) -> Path:
    bm_h = benchmark.get("headline", {})
    bm_real = bm_h.get("real", {})
    bm_dm = bm_h.get("null_distance_matched", {})

    lines = [
        f"# Level-Quality Gym — {week_label}",
        "",
        f"**Verdict: {verdict}**",
        "",
        explanation,
        "",
        "---",
        "",
        "## Trailing Window",
        "",
        f"| Metric | Trailing ({trailing['n_days']} days) | Baseline (219 days) | DM-null baseline |",
        "|---|---|---|---|",
        f"| Days | {trailing['n_days']} | {benchmark.get('days_benchmarked', '?')} | — |",
        f"| Avg levels scored | {round(trailing['n_levels'] / max(trailing['n_days'], 1), 1)} | {benchmark.get('avg_levels_per_day', '?')} | — |",
        f"| Touch rate | {trailing['touch_rate']:.1%} | {bm_real.get('touch_rate', 0):.1%} | {bm_dm.get('touch_rate', 0):.1%} |",
        f"| Respect rate (of touched) | {trailing['respect_rate_of_touched']:.1%} | {bm_real.get('respect_rate_of_touched', 0):.1%} | {bm_dm.get('respect_rate_of_touched', 0):.1%} |",
        f"| Respect lift vs DM-null | **{round((trailing.get('respect_rate_of_touched', 0) - bm_dm.get('respect_rate_of_touched', 0)) * 100, 1)}pp** | {bm_h.get('respect_lift_vs_dm_null_pp', '?')}pp | 0pp (baseline) |",
        "",
        "## By Source (trailing)",
        "",
        "| Source | n | Respect rate |",
        "|---|---|---|",
    ]
    for src, sv in sorted(trailing.get("by_source", {}).items()):
        rr = f"{sv['respect_rate']:.1%}" if sv.get("respect_rate") is not None else "n/a"
        lines.append(f"| {src} | {sv['n']} | {rr} |")

    lines += [
        "",
        "## OP-20 Disclosure",
        "",
        f"- N (trailing): {trailing['n_days']} days, {trailing['n_levels']} levels scored",
        f"- Baseline: benchmark over {benchmark.get('days_benchmarked', 219)} days (2025-08-01 → 2026-06-15)",
        "- Null: distance-matched (same distances from open, random sign) — controls for proximity bias",
        "- Metric: respect-rate-of-touched (price moved >= $0.30 in rejection direction within 6 bars)",
        "- SPY price-space only. Real-fills required for option P&L claim (L74).",
        "",
        "---",
        f"_Generated by `analysis/level-quality/level_quality_gym.py` on {dt.date.today().isoformat()}_",
    ]

    out_path = WEEKLY_DIR / f"weekly-{week_label}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def append_status_red(week_label: str, explanation: str) -> None:
    """Append a Known-broken line to STATUS.md on RED verdict."""
    if not STATUS_PATH.exists():
        print(f"  WARNING: STATUS.md not found at {STATUS_PATH} — skipping append")
        return

    content = STATUS_PATH.read_text(encoding="utf-8")
    entry = (
        f"\n- **[{dt.date.today().isoformat()}] LEVEL_QUALITY RED ({week_label}):** "
        f"{explanation} "
        f"See `analysis/level-quality/weekly-{week_label}.md`"
    )

    if "## Known broken" in content:
        content = content.replace("## Known broken", f"## Known broken\n{entry}", 1)
    else:
        content += f"\n\n## Known broken\n{entry}\n"

    STATUS_PATH.write_text(content, encoding="utf-8")
    print(f"  Appended RED alert to {STATUS_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30,
                        help="Trailing window in calendar days (default: 30)")
    parser.add_argument("--week", default=None,
                        help="Week label e.g. 2026-W24 (default: current ISO week)")
    args = parser.parse_args()

    today = dt.date.today()
    if args.week:
        week_label = args.week
    else:
        week_label = today.strftime("%Y-W%V")

    print(f"Level-Quality Gym — {week_label}")
    print(f"Trailing window: {args.days} days")

    # Load data
    rows = load_ledger(args.days)
    if not rows:
        print("WARNING: No ledger rows found. Run score_level_outcomes.py --backfill first.")
        sys.exit(0)

    benchmark = load_benchmark()
    print(f"Loaded {len(rows)} days from ledger, benchmark has {benchmark.get('days_benchmarked')} days")

    # Compute
    trailing = compute_trailing_metrics(rows)
    verdict, explanation = make_verdict(trailing, benchmark)

    print(f"\nVERDICT: {verdict}")
    print(f"  {explanation}")
    print(f"\nTrailing metrics ({trailing['n_days']} days):")
    print(f"  touch_rate:   {trailing['touch_rate']:.3f}")
    print(f"  respect_rate: {trailing['respect_rate_of_touched']:.3f}")

    # Write weekly scorecard
    out_path = write_weekly_md(week_label, trailing, verdict, explanation, benchmark)
    print(f"\nWrote {out_path}")

    # Append to STATUS.md on RED
    if verdict == "RED":
        append_status_red(week_label, explanation)

    print(f"\nGYM DONE — {verdict}")


if __name__ == "__main__":
    main()
