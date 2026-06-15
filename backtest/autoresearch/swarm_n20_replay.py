"""
SWARM N20 GATE — Cycle 12
Run missing swarm replays for 2026-05-16, 2026-05-18, 2026-05-19 and rebuild aggregate.json.

Context:
  - aggregate.json currently has N=18 UNTESTED tradeable days (N=20 needed to ratify
    internals-dissent penalty formula in swarm v5).
  - Master CSV covers through 2026-05-15; new dates need the extend CSV merged in.
  - This script: merges CSVs, builds overlays, runs swarm stages 2-4, grades, rebuilds aggregate.

Output:
  - analysis/swarm-benchmark/replay-2026-05-{16,18,19}-0600/ (swarm_output.json + grade.json)
  - analysis/swarm-benchmark/aggregate.json (rebuilt from all grade.json files)
  - analysis/swarm-benchmark/n20-gate-report.json (N20 status + per-day breakdown)

Per OP-25 ENGINE-BENEFIT AUTONOMY PRINCIPLE — no live orders, no production doctrine changes.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent       # .../backtest/
ROOT = REPO.parent                                   # .../42/
REPLAY_DIR = ROOT / "automation" / "swarm" / "replay"
BENCHMARK_BASE = ROOT / "analysis" / "swarm-benchmark"
DATA_DIR = REPO / "data"

# Inject replay module path so runner_replay can import build_* siblings
sys.path.insert(0, str(REPLAY_DIR))
sys.path.insert(0, str(REPO))          # for lib.* imports inside build_raw_data

# ── Data paths ────────────────────────────────────────────────────────────────
MASTER_SPY = DATA_DIR / "spy_5m_2025-01-01_2026-05-15.csv"
EXTEND_SPY  = DATA_DIR / "spy_5m_2026-05-08_2026-05-19.csv"
MASTER_VIX  = DATA_DIR / "vix_5m_2025-01-01_2026-05-15.csv"
EXTEND_VIX  = DATA_DIR / "vix_5m_2026-05-08_2026-05-19.csv"
MERGED_SPY  = DATA_DIR / "spy_5m_2025-01-01_2026-05-19_merged.csv"
MERGED_VIX  = DATA_DIR / "vix_5m_2025-01-01_2026-05-19_merged.csv"

DATES_TO_REPLAY: list[str] = ["2026-05-16", "2026-05-18", "2026-05-19"]
AS_OF = "06:00"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[n20 {ts}] {msg}", flush=True)


# ── Step 1: Merge CSVs ────────────────────────────────────────────────────────

_TZ_OFFSET_RE = re.compile(r"[+-]\d{2}:\d{2}$")


def _normalize_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Strip trailing timezone offset (e.g. -04:00) from timestamp_et strings.

    The master CSVs store naive ET timestamps ('2025-01-01 09:30:00').
    The extend CSVs store tz-aware ISO8601 ('2026-05-08 09:30:00-04:00').
    After stripping the offset both are consistent naive ET strings.
    """
    df = df.copy()
    df["timestamp_et"] = df["timestamp_et"].astype(str).str.replace(
        _TZ_OFFSET_RE, "", regex=True
    )
    return df


def _merge_csv(master: Path, extend: Path, out: Path, label: str) -> Path:
    """Merge master + extend CSV, normalise timestamps, dedup, sort, write."""
    if out.exists():
        _log(f"{label}: merged CSV already exists at {out} — reusing")
        return out
    _log(f"{label}: merging {master.name} + {extend.name}")
    df_master = _normalize_timestamps(pd.read_csv(master))
    df_extend = _normalize_timestamps(pd.read_csv(extend))
    merged = (
        pd.concat([df_master, df_extend], ignore_index=True)
        .drop_duplicates(subset=["timestamp_et"])
        .sort_values("timestamp_et")
        .reset_index(drop=True)
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out, index=False)
    _log(f"{label}: merged {len(df_master)}+{len(df_extend)} -> {len(merged)} rows -> {out.name}")
    return out


# ── Step 2: Build overlay for one date ───────────────────────────────────────

def _build_overlay(date_et: str, replay_dir: Path,
                   merged_spy: Path, merged_vix: Path) -> None:
    """Build raw_data.json, key-levels.json, macro-calendar.json for the replay dir."""
    from build_raw_data import build_raw_data
    from build_key_levels import build_key_levels
    from build_macro_calendar import build_macro_calendar

    replay_dir.mkdir(parents=True, exist_ok=True)

    # raw_data — needs both SPY + VIX merged CSVs
    if not (replay_dir / "raw_data.json").exists():
        _log(f"  {date_et}: building raw_data.json")
        build_raw_data(date_et, AS_OF,
                       spy_csv=merged_spy, vix_csv=merged_vix,
                       output_path=replay_dir / "raw_data.json")
    else:
        _log(f"  {date_et}: raw_data.json exists — skip")

    # key-levels — needs SPY merged CSV
    if not (replay_dir / "key-levels.json").exists():
        _log(f"  {date_et}: building key-levels.json")
        build_key_levels(date_et, AS_OF,
                         spy_csv=merged_spy,
                         output_path=replay_dir / "key-levels.json")
    else:
        _log(f"  {date_et}: key-levels.json exists — skip")

    # macro-calendar — reads from live automation/state/macro-calendar.json
    if not (replay_dir / "macro-calendar.json").exists():
        _log(f"  {date_et}: building macro-calendar.json")
        build_macro_calendar(date_et, output_path=replay_dir / "macro-calendar.json")
    else:
        _log(f"  {date_et}: macro-calendar.json exists — skip")


# ── Step 3: Run swarm stages 2-4 ─────────────────────────────────────────────

def _run_swarm_stages(date_et: str) -> dict:
    """Call runner_replay.run_replay with skip_build=True (overlay already built)."""
    from runner_replay import run_replay
    _log(f"  {date_et}: running swarm stages 2-4 (skip_build=True)")
    result = run_replay(date_et, AS_OF, skip_build=True)
    if result.get("status") == "failed":
        _log(f"  {date_et}: SWARM FAILED stage={result.get('stage_failed')}")
    else:
        bias = result.get("consensus_bias", "?")
        conf = result.get("swarm_confidence", "?")
        _log(f"  {date_et}: swarm done — bias={bias} conf={conf}")
    return result


# ── Step 4: Grade one date ────────────────────────────────────────────────────

def _grade_date(date_et: str, merged_spy: Path) -> dict | None:
    """Grade a replay dir against actual outcomes using merged SPY CSV."""
    from grader_replay import grade_replay
    replay_dir = BENCHMARK_BASE / f"replay-{date_et}-0600"
    if not (replay_dir / "swarm_output.json").exists():
        _log(f"  {date_et}: no swarm_output.json — skipping grade")
        return None
    grade = grade_replay(date_et, AS_OF, spy_csv=merged_spy)
    if grade.get("status") in ("missing_swarm_output", "no_rth_bars"):
        _log(f"  {date_et}: grade status={grade.get('status')}")
        return None
    dir_grade = grade["grades"]["direction"]["grade"]
    btl_grade = grade["grades"]["battle_level"]["grade"]
    _log(f"  {date_et}: direction={dir_grade} battle={btl_grade}")
    return grade


# ── Step 5: Rebuild aggregate.json from all grade.json files ──────────────────

def _rebuild_aggregate() -> dict:
    """
    Rebuild aggregate.json by reading all grade.json files.
    Mirrors grader_replay.grade_all() logic but reads grade.json directly
    instead of re-running grade_replay() (which would need the merged CSV for newer dates).
    """
    import re
    grades: list[dict] = []
    for d in sorted(BENCHMARK_BASE.glob("replay-*")):
        m = re.match(r"replay-(\d{4}-\d{2}-\d{2})-(\d{4})", d.name)
        if not m:
            continue
        grade_path = d / "grade.json"
        if not grade_path.exists():
            continue
        try:
            with open(grade_path, encoding="utf-8") as f:
                g = json.load(f)
        except Exception as exc:
            _log(f"  WARN: {d.name}/grade.json unreadable: {exc}")
            continue
        if g.get("status") in ("missing_swarm_output", "no_rth_bars"):
            continue
        if "grades" not in g:
            continue
        grades.append(g)

    if not grades:
        return {"n_days_graded": 0}

    n = len(grades)
    direction_grades = [g["grades"]["direction"]["grade"] for g in grades]
    n_correct = sum(1 for x in direction_grades if x == "CORRECT")
    n_wrong   = sum(1 for x in direction_grades if x == "WRONG")
    n_abstain = sum(1 for x in direction_grades if x in ("ABSTAIN", "ABSTAIN_ACTUAL"))

    battle_grades_all = [g["grades"]["battle_level"]["grade"] for g in grades]
    n_tested   = sum(1 for x in battle_grades_all if x in ("HELD", "BROKE", "TESTED_MIXED"))
    n_untested = sum(1 for x in battle_grades_all if x == "UNTESTED")

    high_conf = [g for g in grades if (g["swarm"].get("swarm_confidence") or 0) >= 70]
    high_conf_correct = sum(1 for g in high_conf if g["grades"]["direction"]["grade"] == "CORRECT")

    agg = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "n_days_graded": n,
        "direction": {
            "n_correct": n_correct,
            "n_wrong": n_wrong,
            "n_abstain": n_abstain,
            "accuracy_pct": round(n_correct / (n_correct + n_wrong) * 100, 1) if (n_correct + n_wrong) else None,
        },
        "battle_level": {
            "n_tested": n_tested,
            "n_untested": n_untested,
            "tested_rate_pct": round(n_tested / n * 100, 1),
        },
        "confidence_calibration": {
            "high_conf_days": len(high_conf),
            "high_conf_correct_pct": round(high_conf_correct / len(high_conf) * 100, 1) if high_conf else None,
        },
        "per_day": [
            {
                "date": g["date"],
                "swarm_bias": g["swarm"]["consensus_bias"],
                "swarm_conf": g["swarm"]["swarm_confidence"],
                "actual_bias": g["actual"]["actual_bias"],
                "actual_move": g["actual"]["move_dollars"],
                "direction_grade": g["grades"]["direction"]["grade"],
                "battle_level": g["swarm"]["battle_level"].get("price"),
                "battle_grade": g["grades"]["battle_level"]["grade"],
            }
            for g in grades
        ],
    }

    out = BENCHMARK_BASE / "aggregate.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)
    _log(f"aggregate.json rebuilt: {n} days, accuracy={agg['direction']['accuracy_pct']}%")
    return agg


# ── Step 6: Count UNTESTED tradeable (N20 gate) ────────────────────────────────

def _n20_status(agg: dict) -> dict:
    """
    UNTESTED tradeable = days where:
      - direction_grade in (CORRECT, WRONG)  -- swarm had a tradeable bias
      - battle_grade == UNTESTED             -- SPY never touched the predicted level

    N=20 needed to ratify internals-dissent penalty in swarm v5.
    """
    per_day = agg.get("per_day", [])
    untested_tradeable = [
        d for d in per_day
        if d["direction_grade"] in ("CORRECT", "WRONG")
        and d["battle_grade"] == "UNTESTED"
    ]
    n = len(untested_tradeable)
    gate_met = n >= 20
    return {
        "n_untested_tradeable": n,
        "gate_met": gate_met,
        "gate_threshold": 20,
        "days": [d["date"] for d in untested_tradeable],
        "verdict": "N20 GATE MET — internals-dissent penalty can be ratified" if gate_met
                   else f"N20 GATE PENDING — need {20 - n} more UNTESTED tradeable days",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SWARM N20 Gate Replay — runs swarm replay for specified dates."
    )
    parser.add_argument(
        "--dates",
        type=str,
        default=None,
        help="Comma-separated YYYY-MM-DD dates to replay (default: hardcoded DATES_TO_REPLAY)",
    )
    parser.add_argument(
        "--cycle",
        type=str,
        default="",
        help="Optional cycle label for log header (e.g. 'Backfill-05-05-to-05-09')",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dates_to_run = (
        [d.strip() for d in args.dates.split(",") if d.strip()]
        if args.dates
        else DATES_TO_REPLAY
    )
    cycle_label = args.cycle or "Cycle 12"

    run_start = time.monotonic()
    _log("=" * 60)
    _log(f"SWARM N20 GATE REPLAY — {cycle_label}")
    _log(f"Dates: {dates_to_run}")
    _log("=" * 60)

    # 1. Merge CSVs (reuse if already merged; for backfill dates <= 2026-05-15
    #    the master CSV already covers them, but merged CSV is the authoritative source)
    _log("\n[1/6] Merging SPY + VIX CSVs")
    merged_spy = _merge_csv(MASTER_SPY, EXTEND_SPY, MERGED_SPY, "SPY")
    merged_vix = _merge_csv(MASTER_VIX, EXTEND_VIX, MERGED_VIX, "VIX")

    new_dates_succeeded: list[str] = []

    for date_et in dates_to_run:
        _log(f"\n{'='*50}")
        _log(f"Processing {date_et}")
        _log(f"{'='*50}")

        replay_dir = BENCHMARK_BASE / f"replay-{date_et}-0600"

        # Check if already complete
        if (replay_dir / "swarm_output.json").exists() and (replay_dir / "grade.json").exists():
            _log(f"  {date_et}: already fully replayed + graded — skip")
            new_dates_succeeded.append(date_et)
            continue

        # 2. Build overlay
        _log(f"\n[overlay] Building Stage 1 overlay for {date_et}")
        try:
            _build_overlay(date_et, replay_dir, merged_spy, merged_vix)
        except Exception as exc:
            _log(f"  ERROR building overlay for {date_et}: {exc}")
            import traceback; traceback.print_exc()
            continue

        # 3. Run swarm stages 2-4
        _log(f"\n[swarm] Running swarm stages 2-4 for {date_et}")
        try:
            result = _run_swarm_stages(date_et)
            if result.get("status") == "failed":
                _log(f"  SKIP {date_et} — swarm failed")
                continue
        except Exception as exc:
            _log(f"  ERROR in swarm run for {date_et}: {exc}")
            import traceback; traceback.print_exc()
            continue

        # 4. Grade
        _log(f"\n[grade] Grading {date_et}")
        try:
            grade = _grade_date(date_et, merged_spy)
            if grade is not None:
                new_dates_succeeded.append(date_et)
        except Exception as exc:
            _log(f"  ERROR grading {date_et}: {exc}")
            import traceback; traceback.print_exc()

    # 5. Rebuild aggregate.json
    _log(f"\n[5/6] Rebuilding aggregate.json from all grade.json files")
    agg = _rebuild_aggregate()

    # 6. N20 gate status
    _log(f"\n[6/6] N20 gate evaluation")
    n20 = _n20_status(agg)
    _log(f"  N_UNTESTED_TRADEABLE = {n20['n_untested_tradeable']} / 20")
    _log(f"  GATE MET: {n20['gate_met']}")
    _log(f"  VERDICT: {n20['verdict']}")

    # Write report
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle_label,
        "dates_processed": dates_to_run,
        "dates_succeeded": new_dates_succeeded,
        "total_graded_days": agg.get("n_days_graded", 0),
        "direction_accuracy_pct": agg.get("direction", {}).get("accuracy_pct"),
        "n20_gate": n20,
        "aggregate_summary": {
            "n_correct": agg.get("direction", {}).get("n_correct"),
            "n_wrong": agg.get("direction", {}).get("n_wrong"),
            "n_abstain": agg.get("direction", {}).get("n_abstain"),
            "n_battle_tested": agg.get("battle_level", {}).get("n_tested"),
            "n_battle_untested": agg.get("battle_level", {}).get("n_untested"),
        },
        "elapsed_s": round(time.monotonic() - run_start, 1),
    }
    report_path = BENCHMARK_BASE / "n20-gate-report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _log(f"\nReport written -> {report_path}")

    total_elapsed = round(time.monotonic() - run_start, 1)
    _log(f"\nDone in {total_elapsed}s")
    return 0 if new_dates_succeeded else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()   # Required for Windows when using Pool
    sys.exit(main())
