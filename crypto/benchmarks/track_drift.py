"""track_drift — outer-loop benchmark over time (the missing OP-11 OUTER layer for crypto).

Reads:
  crypto/data/scorecards/history.jsonl  — every Gamma_CryptoRegression fire's summary
  crypto/data/scorecards/grinder.jsonl  — every live_grinder iteration's result

Computes:
  - PASS rate over rolling windows (last 1h, 6h, 24h, 7d)
  - FAIL streak detection
  - Per-stage trend: did any stage's pass rate drop below 95% in the last 24h?
  - Foot-gun catch rate trend (v01)
  - Source parity drift trend (v02)
  - Indicator value drift (v03 RSI / EMA range over time)

Writes:
  crypto/data/scorecards/drift_report.json
  console summary

Designed to be called by Gamma_CryptoRegression's wrapper after each PASS,
OR ad-hoc to ratify/reject knob changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _load_history(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                d["_ts"] = datetime.fromisoformat(d["started_at"].replace("Z", "+00:00"))
                out.append(d)
            except Exception:
                continue
    return out


def _load_grinder(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                d["_ts"] = datetime.fromisoformat(d["started_at"].replace("Z", "+00:00"))
                out.append(d)
            except Exception:
                continue
    return out


def _window(items: list[dict], now: datetime, hours: float) -> list[dict]:
    cutoff = now.timestamp() - hours * 3600
    return [x for x in items if x["_ts"].timestamp() >= cutoff]


def _stage_pass_rate(history: list[dict]) -> dict:
    """For each stage name, fraction of fires where it passed."""
    seen = defaultdict(lambda: [0, 0])  # [passes, total]
    for h in history:
        for stage, ok in h.get("per_stage", {}).items():
            seen[stage][1] += 1
            if ok:
                seen[stage][0] += 1
    return {stage: {"passed": p, "total": t, "rate": round(p / t * 100, 2) if t else 0}
            for stage, (p, t) in seen.items()}


def _fail_streak(history: list[dict]) -> int:
    """Number of consecutive FAILs ending at the most recent fire."""
    streak = 0
    for h in reversed(history):
        if h.get("overall_pass"):
            break
        streak += 1
    return streak


def _grinder_foot_gun_rate(grinder: list[dict]) -> dict:
    eligible = 0
    catches = 0
    for it in grinder:
        v01 = it.get("results", {}).get("v01_live", {})
        if v01.get("naive_last_bar_in_progress") is True:
            eligible += 1
            if v01.get("foot_gun_caught_this_fetch") is True:
                catches += 1
    return {
        "eligible_iterations": eligible,
        "catches": catches,
        "catch_rate_pct": round(100 * catches / eligible, 2) if eligible else None,
    }


def _grinder_source_parity_drift(grinder: list[dict]) -> dict:
    iters = len(grinder)
    with_drift = 0
    max_disagreements = 0
    for it in grinder:
        v02 = it.get("results", {}).get("v02_parity", {})
        d = v02.get("disagreements_above_tolerance", 0)
        if d > 0:
            with_drift += 1
        max_disagreements = max(max_disagreements, d)
    return {
        "iterations": iters,
        "iters_with_drift": with_drift,
        "drift_rate_pct": round(100 * with_drift / iters, 2) if iters else 0,
        "max_disagreements_per_iter": max_disagreements,
    }


def _grinder_rsi_range(grinder: list[dict]) -> dict:
    vals = []
    for it in grinder:
        v = it.get("results", {}).get("v03_indicators_live", {}).get("rsi_14_last")
        if v is not None:
            vals.append(v)
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "mean": round(sum(vals) / len(vals), 2),
    }


def build_report(history_path: Path, grinder_path: Path) -> dict:
    now = datetime.now(timezone.utc)
    history = _load_history(history_path)
    grinder = _load_grinder(grinder_path)

    # Rolling windows of history (Gamma_CryptoRegression fires)
    win = {
        "1h": _window(history, now, 1),
        "6h": _window(history, now, 6),
        "24h": _window(history, now, 24),
        "7d": _window(history, now, 24 * 7),
    }

    def _rate(items):
        if not items:
            return None
        passed = sum(1 for x in items if x.get("overall_pass"))
        return {"passed": passed, "total": len(items), "rate_pct": round(100 * passed / len(items), 2)}

    # Grinder windows
    gwin = {
        "1h": _window(grinder, now, 1),
        "6h": _window(grinder, now, 6),
        "24h": _window(grinder, now, 24),
    }

    # Alerts
    alerts = []
    if history and not history[-1].get("overall_pass"):
        alerts.append(f"latest cron fire FAILED ({history[-1]['started_at']})")
    streak = _fail_streak(history)
    if streak >= 2:
        alerts.append(f"fail streak: {streak} consecutive fires")
    stage_rates = _stage_pass_rate(_window(history, now, 24))

    # OP-26 + v15 explainer: if v02 alerts but v15 passed >= 95%, the v02 failures
    # are likely single-provider artifacts (yfinance settling late), not real foot-guns.
    v15_rate = stage_rates.get("v15_three_source_parity.live", {}).get("rate", None)
    for stage, info in stage_rates.items():
        if info["rate"] < 95 and info["total"] >= 3:
            msg = f"stage {stage} pass rate dropped to {info['rate']}% in last 24h ({info['passed']}/{info['total']})"
            if stage == "v02_source_parity" and v15_rate is not None and v15_rate >= 95:
                msg += f" -- but v15 (3-source) = {v15_rate}% in same window, likely single-provider artifact"
            alerts.append(msg)

    foot_gun = _grinder_foot_gun_rate(_window(grinder, now, 24))
    if foot_gun.get("catch_rate_pct") is not None and foot_gun["catch_rate_pct"] < 99 and foot_gun["eligible_iterations"] >= 10:
        alerts.append(f"v01 foot-gun catch rate {foot_gun['catch_rate_pct']}% (should be ~100%)")

    parity = _grinder_source_parity_drift(_window(grinder, now, 24))
    if parity["drift_rate_pct"] > 30:
        alerts.append(f"v02 source parity drift in {parity['drift_rate_pct']}% of last-24h iterations")

    return {
        "generated_at": now.isoformat(),
        "history_total_fires": len(history),
        "grinder_total_iterations": len(grinder),
        "cron_pass_rate_by_window": {k: _rate(v) for k, v in win.items()},
        "grinder_count_by_window": {k: len(v) for k, v in gwin.items()},
        "stage_pass_rate_24h": stage_rates,
        "consecutive_fail_streak": streak,
        "foot_gun_catch_rate_24h": foot_gun,
        "source_parity_drift_24h": parity,
        "rsi_range_24h": _grinder_rsi_range(_window(grinder, now, 24)),
        "alerts": alerts,
        "overall_health": "RED" if alerts else "GREEN",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history", type=Path, default=Path("crypto/data/scorecards/history.jsonl"))
    p.add_argument("--grinder", type=Path, default=Path("crypto/data/scorecards/grinder.jsonl"))
    p.add_argument("--json-out", type=Path, default=Path("crypto/data/scorecards/drift_report.json"))
    args = p.parse_args(argv)

    r = build_report(args.history, args.grinder)
    print("=" * 70)
    print("CRYPTO HARNESS DRIFT REPORT")
    print("=" * 70)
    print(f"  generated_at:                  {r['generated_at']}")
    print(f"  total cron fires:              {r['history_total_fires']}")
    print(f"  total grinder iterations:      {r['grinder_total_iterations']}")
    print()
    print(f"  CRON PASS RATE BY WINDOW:")
    for window, info in r["cron_pass_rate_by_window"].items():
        if info:
            print(f"    last {window:<4}: {info['passed']}/{info['total']} ({info['rate_pct']}%)")
        else:
            print(f"    last {window:<4}: no data")
    print()
    print(f"  GRINDER ITERATIONS BY WINDOW:")
    for window, n in r["grinder_count_by_window"].items():
        print(f"    last {window:<4}: {n}")
    print()
    print(f"  PER-STAGE PASS RATE (last 24h):")
    for stage, info in sorted(r["stage_pass_rate_24h"].items()):
        flag = " !ALERT" if info["rate"] < 95 else ""
        print(f"    {stage:<40s} {info['passed']:>3d}/{info['total']:<3d}  {info['rate']:>6.2f}%{flag}")
    print()
    print(f"  FOOT-GUN CATCH RATE (last 24h):  {r['foot_gun_catch_rate_24h']}")
    print(f"  SOURCE PARITY DRIFT (last 24h):  {r['source_parity_drift_24h']}")
    print(f"  RSI(14) RANGE (last 24h):        {r['rsi_range_24h']}")
    print()
    print(f"  CONSECUTIVE FAIL STREAK:         {r['consecutive_fail_streak']}")
    print(f"  OVERALL HEALTH:                  {r['overall_health']}")
    if r["alerts"]:
        print(f"  ALERTS ({len(r['alerts'])}):")
        for a in r["alerts"]:
            print(f"    - {a}")
    else:
        print(f"  ALERTS: none")
    print("=" * 70)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(r, indent=2, default=str))
    print(f"\n  full report: {args.json_out}")


if __name__ == "__main__":
    main()
