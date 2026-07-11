"""crypto_twin_soak_report.py -- T4 (Sunday) reads this. Prints a human-glanceable
summary of the crypto twin's soak run so a report can be pulled any time without
re-deriving everything from raw decisions.jsonl by hand.

Reads (never writes):
  * automation/state/crypto-twin/soak-log.jsonl -- T3's hourly rollups, for the
    historical per-hour breakdown (trend visibility across the soak).
  * automation/state/crypto-twin/decisions.jsonl -- the source of truth. Totals
    (tick count, error count, action distribution, uptime estimate) are ALWAYS a
    full recompute over this file, not summed from soak-log.jsonl rows -- the
    current, still-open hour hasn't been rolled up yet, so summing only soak-log
    would silently undercount the most recent partial hour. soak-log.jsonl's row
    count is reported separately as a "how many hourly checkpoints exist" fact.

$0, pure stdlib, read-only, no network. Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/crypto_twin_soak_report.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
SOAK_LOG_PATH = TWIN_DIR / "soak-log.jsonl"
DECISIONS_PATH = TWIN_DIR / "decisions.jsonl"

# Gamma_CryptoTwin fires every 5 min, 24/7 -- see setup/scripts/install-crypto-twin.ps1.
EXPECTED_CADENCE_MINUTES = 5


def _read_jsonl(path: Path) -> list[dict]:
    """Fail-open: missing file -> []. Skips (never aborts on) a malformed line."""
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize(soak_rows: list[dict], decision_rows: list[dict]) -> dict:
    """PURE (testable without real files): builds the summary dict from already-
    loaded rows. Uptime is estimated as observed-ticks / expected-ticks over the
    observed first->last tick span at the known 5-min cadence, capped at 100% (a
    span shorter than one cadence interval, or a single tick, reports None rather
    than a meaningless ratio)."""
    n_ticks = len(decision_rows)
    dist = Counter(str(r.get("action", "UNKNOWN")) for r in decision_rows)
    n_errors = dist.get("TICK_ERROR", 0)
    error_rows = [r for r in decision_rows if r.get("action") == "TICK_ERROR"]

    ts_list = sorted(str(r.get("ts_et", "")) for r in decision_rows if r.get("ts_et"))
    first_tick = ts_list[0] if ts_list else None
    last_tick = ts_list[-1] if ts_list else None

    uptime_pct: Optional[float] = None
    if first_tick and last_tick and n_ticks > 1:
        try:
            t0 = datetime.fromisoformat(first_tick)
            t1 = datetime.fromisoformat(last_tick)
            span_minutes = max((t1 - t0).total_seconds() / 60.0, 0.0)
            if span_minutes >= EXPECTED_CADENCE_MINUTES:
                expected_ticks = max(span_minutes / EXPECTED_CADENCE_MINUTES, 1.0)
                uptime_pct = round(min(n_ticks / expected_ticks, 1.0) * 100.0, 1)
        except ValueError:
            uptime_pct = None

    return {
        "n_soak_rows": len(soak_rows),
        "n_ticks_total": n_ticks,
        "n_errors_total": n_errors,
        "first_tick_et": first_tick,
        "last_tick_et": last_tick,
        "uptime_pct_estimate": uptime_pct,
        "action_distribution": dict(dist),
        "recent_errors": [
            {"ts_et": r.get("ts_et"), "reason": r.get("reason")} for r in error_rows[-5:]
        ],
    }


def format_report(summary: dict) -> str:
    uptime_line = (f"Uptime estimate:     {summary['uptime_pct_estimate']}%"
                  if summary["uptime_pct_estimate"] is not None
                  else "Uptime estimate:     n/a (insufficient span)")
    lines = [
        "=== Crypto Twin Soak Report ===",
        f"Ticks logged:        {summary['n_ticks_total']}",
        f"Errors logged:       {summary['n_errors_total']}",
        f"First tick (ET):     {summary['first_tick_et'] or 'n/a'}",
        f"Last tick (ET):      {summary['last_tick_et'] or 'n/a'}",
        uptime_line,
        f"Hourly rollups:      {summary['n_soak_rows']} rows (soak-log.jsonl)",
        "",
        "Action distribution:",
    ]
    for action, count in sorted(summary["action_distribution"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {action:<24s} {count}")
    if summary["recent_errors"]:
        lines.append("")
        lines.append("Recent errors (last 5):")
        for e in summary["recent_errors"]:
            lines.append(f"  {e['ts_et']}: {e['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    soak_rows = _read_jsonl(SOAK_LOG_PATH)
    decision_rows = _read_jsonl(DECISIONS_PATH)
    summary = summarize(soak_rows, decision_rows)
    print(format_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
