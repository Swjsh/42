#!/usr/bin/env python
"""Deterministic per-setup performance aggregator (R-0007 fix).

Graduates the fragile EOD-summary Step-8 LLM prose instruction into a pure
Python recompute. Reads journal/trades.csv, groups by `setup`, and FULL-OVERWRITES
setup-performance.json. Runs on every EOD path (wired into run-eod-summary.ps1),
so it no longer depends on the Claude fallback firing (the free-tier EOD migration
silently dropped the recompute, freezing the file at 2026-05-15 for ~37 days).

Writes BOTH reader locations to end the long-standing path mismatch:
  - analysis/setup-performance.json            (weekly-review reader)
  - automation/state/setup-performance.json    (freshness-watchdog + eod-orchestrator gate)

$0, no network, no LLM. Pure stdlib. Idempotent: same trades.csv -> same output
(modulo the last_updated timestamp). Never appends; single-pass overwrite.

Usage:
    python backtest/scripts/update_setup_performance.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

# C9: anchor every path to __file__, never CWD.
REPO = Path(__file__).resolve().parents[2]
TRADES_CSV = REPO / "journal" / "trades.csv"
OUT_PATHS = (
    REPO / "analysis" / "setup-performance.json",
    REPO / "automation" / "state" / "setup-performance.json",
)

TOD_BUCKETS = ["OPEN_DRIVE", "MORNING", "MIDDAY", "AFTERNOON", "POWER_HOUR"]
IV_REGIMES = ["LOW", "MID", "HIGH"]
TAPE_BUCKETS = ["dry", "normal", "favorable", "exceptional", "unfavorable"]
GRADE_SCORES = ["5", "4", "3", "2", "1", "0"]


def _f(row: dict, key: str):
    """Safe float coercion; returns None on blank/non-numeric."""
    v = (row.get(key) or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _wr(rows: list[dict]) -> float | None:
    if not rows:
        return None
    wins = sum(1 for r in rows if (_f(r, "dollar_pnl") or 0.0) > 0)
    return round(wins / len(rows), 4)


def _return_pct(row: dict) -> float | None:
    """% return on capital-at-risk. For a long option the premium paid IS the
    max risk, so use premium_paid; fall back to dollar_risk. (Spec named the
    denominator dollar_risk; premium_paid is the true long-premium risk and the
    two coincide for first-strike longs.)"""
    pnl = _f(row, "dollar_pnl")
    denom = _f(row, "premium_paid") or _f(row, "dollar_risk")
    if pnl is None or not denom:
        return None
    return pnl / denom * 100.0


def _archetype_of(row: dict) -> str:
    raw = (row.get("archetype_match_json") or "").strip()
    if not raw:
        return ""
    try:
        return str(json.loads(raw).get("closest", "") or "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def _bucket_wr(rows: list[dict], key: str, labels: list[str], extra: dict | None = None) -> dict:
    out: dict[str, dict] = {}
    for lbl in labels:
        grp = [r for r in rows if (r.get(key) or "").strip() == lbl]
        out[lbl] = {"n": len(grp), "wr": _wr(grp)}
    if extra:
        for lbl in extra:
            grp = [r for r in rows if _archetype_of(r) == lbl]
            out[lbl] = {"n": len(grp), "wr": _wr(grp)}
    return out


def _aggregate(setup: str, rows: list[dict]) -> dict:
    rets = [p for p in (_return_pct(r) for r in rows) if p is not None]
    holds = [h for h in (_f(r, "hold_minutes") for r in rows) if h is not None]
    holdq = [h for h in (_f(r, "hold_quality_pct") for r in rows) if h is not None]

    by_grade = {}
    for gs in GRADE_SCORES:
        grp = [r for r in rows if (r.get("trade_grade_score") or "").strip() == gs]
        pnls = [p for p in (_f(r, "dollar_pnl") for r in grp) if p is not None]
        by_grade[gs] = {"n": len(grp),
                        "avg_pnl": round(statistics.mean(pnls), 2) if pnls else None}

    # archetypes present in this group (data-driven, plus always-present spec keys)
    arche_labels = sorted({_archetype_of(r) for r in rows if _archetype_of(r)})

    return {
        "n_trades": len(rows),
        "n_wins": sum(1 for r in rows if (_f(r, "dollar_pnl") or 0.0) > 0),
        "hit_rate": _wr(rows),
        "avg_return_pct": round(statistics.mean(rets), 2) if rets else None,
        "stdev_return_pct": round(statistics.stdev(rets), 2) if len(rets) > 1 else None,
        "max_win_pct": round(max(rets), 2) if rets else None,
        "max_loss_pct": round(min(rets), 2) if rets else None,
        "avg_hold_minutes": round(statistics.mean(holds), 1) if holds else None,
        "n_correct_setups": sum(1 for r in rows if (r.get("setup_quality") or "").strip().upper() == "CORRECT"),
        "n_excellent_grades": sum(1 for r in rows if (r.get("trade_grade") or "").strip().upper() == "EXCELLENT"),
        "by_iv_regime": _bucket_wr(rows, "iv_regime", IV_REGIMES),
        "by_tod_bucket": _bucket_wr(rows, "tod_bucket", TOD_BUCKETS),
        "by_tape_assistance": _bucket_wr(rows, "tape_assistance", TAPE_BUCKETS),
        "by_archetype": {lbl: {"n": sum(1 for r in rows if _archetype_of(r) == lbl),
                               "wr": _wr([r for r in rows if _archetype_of(r) == lbl])}
                         for lbl in arche_labels},
        "by_grade_score": by_grade,
        "avg_hold_quality_pct": round(statistics.mean(holdq), 1) if holdq else None,
        "last_updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    if not TRADES_CSV.exists():
        print(f"ERROR: {TRADES_CSV} not found")
        return 1

    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # normalize any BOM-prefixed first column key
    rows = [{(k.lstrip("﻿") if k else k): v for k, v in r.items()} for r in rows]

    groups: dict[str, list[dict]] = {}
    for r in rows:
        setup = (r.get("setup") or "").strip()
        if not setup:
            continue
        groups.setdefault(setup, []).append(r)

    out = {setup: _aggregate(setup, grp) for setup, grp in sorted(groups.items())}
    out["_meta"] = {
        "generator": "backtest/scripts/update_setup_performance.py",
        "source": "journal/trades.csv",
        "total_trades": sum(len(g) for g in groups.values()),
        "n_setups": len(groups),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "note": "R-0007 fix: deterministic recompute replaces the dropped EOD-summary Step-8 LLM prose. "
                "Deployment gate (>=20 trades, hit_rate>=0.45) reads this; full-overwrite, never appends.",
    }

    payload = json.dumps(out, indent=2)
    if args.dry_run:
        print(payload)
        print(f"\n[dry-run] {out['_meta']['total_trades']} trades across {len(groups)} setups; NOT written")
        return 0

    for p in OUT_PATHS:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    print(f"setup-performance: {out['_meta']['total_trades']} trades / {len(groups)} setups "
          f"-> {', '.join(str(p.relative_to(REPO)) for p in OUT_PATHS)}")
    for setup, agg in out.items():
        if setup == "_meta":
            continue
        print(f"  {setup}: n={agg['n_trades']} wr={agg['hit_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
