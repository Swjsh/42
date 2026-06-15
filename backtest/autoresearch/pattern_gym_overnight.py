"""pattern_gym_overnight -- nightly continuous-regression for chart-pattern detectors.

Fires nightly via Gamma_PatternGymOvernight task. Each run:
  1. Replays the LATEST 5 trading days through pattern_backtest
  2. Appends scorecard to analysis/pattern-gym-history.jsonl (one row per day per run)
  3. Drift-detects: alerts if any detector's rolling-7-day WR falls > 5pp vs its
     16-mo baseline (the historical edge benchmark)
  4. Updates analysis/pattern-gym-latest.json with the freshest snapshot

This is the "doing reps all night" arm of OP-26 gym. Production heartbeat never
modifies; this is read-only validation continuously catching:
  - Detector code regressions (e.g. tightened threshold breaks signal density)
  - Regime shifts (WR collapse means the edge is gone)
  - New variant proposals (when a chef-cooked variant lands, it gets graded here)

Cost: $0 (pure Python, no LLM in the loop).

CLI:
    python backtest/autoresearch/pattern_gym_overnight.py
    python backtest/autoresearch/pattern_gym_overnight.py --days 10  # extended look-back
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Direct-file import: backtest.autoresearch.__init__ imports `runner` which
# pulls heavy filter modules; we only need pattern_backtest pure-Python helpers.
import importlib.util
_pb_spec = importlib.util.spec_from_file_location(
    "pattern_backtest_direct",
    Path(__file__).parent / "pattern_backtest.py",
)
_pb = importlib.util.module_from_spec(_pb_spec)  # type: ignore[arg-type]
_pb_spec.loader.exec_module(_pb)  # type: ignore[union-attr]
run_pattern_backtest = _pb.run_pattern_backtest
_autodetect_csv = _pb._autodetect_csv


# 16-mo baseline WR (from analysis/pattern-backtest-range-2025-01-02-to-2026-05-15.json)
BASELINE_16MO_WR_PCT = {
    "double_bottom": 52.9,
    "double_top": 46.6,
    "failed_breakdown_wick": 50.8,
    "rejection_at_level_bearish": 44.4,
    "momentum_acceleration": 46.1,
    "inside_bar_consolidation": None,  # neutral bias, never graded
}
# Per-detector minimum rolling-7-day sample size before drift alert fires
DRIFT_MIN_N = 10
DRIFT_THRESHOLD_PP = 5.0


def _latest_n_trading_days(n: int) -> list[Date]:
    """Return the latest N weekdays ending at yesterday (skip today)."""
    today = datetime.now(timezone.utc).date()
    out: list[Date] = []
    d = today - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:  # Mon-Fri
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def _drift_check(history_path: Path) -> dict:
    """Roll-up the last 7 trading days; flag any detector WR drift > 5pp."""
    if not history_path.exists():
        return {"drift_detected": False, "alerts": [], "reason": "no_history_yet"}

    cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
    rolling: dict[str, dict[str, int]] = {}
    with history_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                d = Date.fromisoformat(rec["date"])
            except (KeyError, ValueError):
                continue
            if d < cutoff:
                continue
            for det, s in rec.get("by_detector", {}).items():
                rolling.setdefault(det, {"wins": 0, "losses": 0})
                rolling[det]["wins"] += s.get("wins", 0)
                rolling[det]["losses"] += s.get("losses", 0)

    alerts = []
    for det, baseline in BASELINE_16MO_WR_PCT.items():
        if baseline is None:
            continue
        s = rolling.get(det, {})
        graded = s.get("wins", 0) + s.get("losses", 0)
        if graded < DRIFT_MIN_N:
            continue
        wr = s["wins"] / graded * 100
        delta = wr - baseline
        if abs(delta) >= DRIFT_THRESHOLD_PP:
            alerts.append({
                "detector": det,
                "rolling_wr_pct": round(wr, 1),
                "baseline_16mo_wr_pct": baseline,
                "delta_pp": round(delta, 1),
                "rolling_n": graded,
                "severity": "RED" if abs(delta) >= 10 else "AMBER",
            })

    return {
        "drift_detected": len(alerts) > 0,
        "alerts": alerts,
        "rolling_window_days": 14,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def run(days: int = 5) -> dict:
    """Replay the latest N trading days; write history + latest snapshot."""
    analysis_dir = PROJECT_ROOT / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    history_path = analysis_dir / "pattern-gym-history.jsonl"
    latest_path = analysis_dir / "pattern-gym-latest.json"

    targets = _latest_n_trading_days(days)
    started = datetime.now(timezone.utc).isoformat()
    per_day: list[dict] = []

    for d in targets:
        csv_path = _autodetect_csv(d)
        if not csv_path:
            per_day.append({"date": d.isoformat(), "skipped": "no_csv_covering"})
            continue
        try:
            day_result = run_pattern_backtest(d, csv_path)
        except Exception as e:
            per_day.append({"date": d.isoformat(), "error": f"{type(e).__name__}: {e}"})
            continue

        if day_result.get("error") or day_result.get("bars_count", 0) == 0:
            per_day.append({"date": d.isoformat(), "skipped": day_result.get("error", "no_bars")})
            continue

        compact = {
            "date": d.isoformat(),
            "bars_count": day_result["bars_count"],
            "total_hits": day_result["total_hits"],
            "by_detector": {
                k: {"hits": v["hits"], "wins": v["wins"], "losses": v["losses"]}
                for k, v in day_result["summary_by_detector"].items()
            },
            "disambiguated": day_result.get("disambiguated_summary", {}),
        }
        per_day.append(compact)
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"run_at": started, **compact}) + "\n")

    drift = _drift_check(history_path)
    snapshot = {
        "run_at": started,
        "days_replayed": [d.isoformat() for d in targets],
        "per_day": per_day,
        "drift": drift,
    }
    latest_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    snap = run(days=args.days)

    if not args.quiet:
        print(f"=== PATTERN GYM REPS  @  {snap['run_at']} ===")
        print(f"  Days replayed: {len(snap['days_replayed'])}")
        for r in snap["per_day"]:
            if "skipped" in r:
                print(f"  {r['date']}: SKIPPED ({r['skipped']})")
            elif "error" in r:
                print(f"  {r['date']}: ERROR {r['error']}")
            else:
                dis = r.get("disambiguated", {})
                wr = dis.get("win_rate_pct")
                hits = r["total_hits"]
                print(f"  {r['date']}: hits={hits:3d}  dis_WR={wr}%  "
                      f"conflicts={dis.get('conflicts_total', 0)}  "
                      f"resolved={dis.get('conflicts_resolved', 0)}")
        drift = snap["drift"]
        if drift["drift_detected"]:
            print()
            print(f"  !!! DRIFT DETECTED ({len(drift['alerts'])} alert(s)) !!!")
            for a in drift["alerts"]:
                print(f"    {a['severity']}: {a['detector']:35s}  "
                      f"rolling {a['rolling_wr_pct']}% vs baseline {a['baseline_16mo_wr_pct']}%  "
                      f"({a['delta_pp']:+.1f}pp, n={a['rolling_n']})")
        else:
            print()
            print(f"  drift: {drift.get('reason', 'none — all detectors within 5pp of baseline')}")

    return 0 if not snap["drift"]["drift_detected"] else 0  # exit 0 even on drift; STATUS.md handles severity


if __name__ == "__main__":
    sys.exit(main())
