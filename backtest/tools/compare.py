"""Skill: backtest-compare

Run the current strategy against ALL historical days. Output a P&L-per-day table.
Flag any day that regressed >$50 vs the prior baseline.
Never declare improvement unless every day is flat-or-better.

Usage:
    python tools/compare.py                    # compare vs baseline (creates if missing)
    python tools/compare.py --save             # freeze current run as new baseline
    python tools/compare.py --baseline PATH    # compare vs a specific baseline JSON
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent  # backtest/
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest  # noqa: E402
from autoresearch.metrics import daily_pnl_series  # noqa: E402

DATA = REPO / "data"
BASELINES_DIR = REPO.parent / "analysis" / "backtests" / "baselines"
REGRESSION_THRESHOLD = 50.0  # dollars


def _find_data() -> tuple[Path, Path]:
    """Return (spy_path, vix_path) for the widest available dataset."""
    candidates = [
        ("2025-01-01", "2026-05-07"),
        ("2025-01-01", "2025-05-31"),
        ("2026-01-01", "2026-05-07"),
    ]
    for cs, ce in candidates:
        sp = DATA / f"spy_5m_{cs}_{ce}.csv"
        vp = DATA / f"vix_5m_{cs}_{ce}.csv"
        if sp.exists() and vp.exists():
            return sp, vp
    raise FileNotFoundError(
        f"No SPY/VIX CSV pair found in {DATA}.\n"
        "Run: python tools/fetch_data.py --start 2025-01-01 --end 2026-05-07"
    )


def _all_trading_days(spy_df: pd.DataFrame) -> list[str]:
    return sorted(spy_df["timestamp_et"].str[:10].unique().tolist())


def _day_pnl_from_result(result) -> dict[str, float]:
    """Group trade P&L by ISO date string."""
    out: dict[str, float] = defaultdict(float)
    for t in result.trades:
        ts = t.entry_time_et
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        out[ts.date().isoformat()] += float(t.dollar_pnl)
    return dict(out)


def _render_table(
    all_days: list[str],
    current: dict[str, float],
    baseline: dict[str, float] | None,
) -> tuple[str, int, int, int]:
    """Build the comparison table. Returns (markdown, n_regressions, n_improved, n_flat)."""
    lines: list[str] = []

    if baseline is not None:
        lines.append("| Date | Current | Baseline | Delta | Status |")
        lines.append("|---|---:|---:|---:|---|")
    else:
        lines.append("| Date | P&L | Traded |")
        lines.append("|---|---:|:---:|")

    n_regressions = n_improved = n_flat = 0

    for day in all_days:
        cur = current.get(day, 0.0)

        if baseline is None:
            traded = "yes" if day in current else "—"
            lines.append(f"| {day} | ${cur:+.0f} | {traded} |")
            continue

        base = baseline.get(day, 0.0)
        delta = cur - base

        if delta < -REGRESSION_THRESHOLD:
            status = "REGRESSED"
            n_regressions += 1
        elif delta > REGRESSION_THRESHOLD:
            status = "improved"
            n_improved += 1
        else:
            status = "—"
            n_flat += 1

        lines.append(f"| {day} | ${cur:+.0f} | ${base:+.0f} | {delta:+.0f} | {status} |")

    return "\n".join(lines), n_regressions, n_improved, n_flat


def _load_baseline(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Support both raw {date: pnl} and the wrapped {"days": {date: pnl}} format.
    return raw.get("days", raw) if isinstance(raw.get("days"), dict) else raw


def _save_baseline(path: Path, current: dict[str, float], n_trades: int) -> Path | None:
    """Write current as the new baseline. Returns backup path if one was made."""
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(f".{ts}.bak.json")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    payload = {
        "saved_at": dt.datetime.now().isoformat(),
        "n_trades": n_trades,
        "total_pnl": round(sum(current.values()), 2),
        "days": {d: round(v, 2) for d, v in current.items()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return backup


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", action="store_true",
                    help="Overwrite baseline with the current run (blocked if REGRESSION).")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="Path to a specific baseline JSON (default: baselines/current.json).")
    args = ap.parse_args()

    baseline_path: Path = args.baseline or (BASELINES_DIR / "current.json")
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ──────────────────────────────────────────────────────────────
    print("Loading data...")
    spy_path, vix_path = _find_data()
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    all_days = _all_trading_days(spy_df)
    print(f"  {len(all_days)} trading days | {len(spy_df):,} SPY bars | source: {spy_path.name}")

    # ── Run backtest ───────────────────────────────────────────────────────────
    print("Running full-window backtest (this takes ~30-60 s)...")
    result = run_backtest(spy_df, vix_df)
    current = _day_pnl_from_result(result)

    total_current = sum(current.values())
    print(f"  {len(result.trades)} trades | {len(current)} trading days with fills | total P&L ${total_current:+.0f}")

    # ── No baseline yet — bootstrap ───────────────────────────────────────────
    baseline = _load_baseline(baseline_path)
    if baseline is None:
        print(f"\nNo baseline at {baseline_path} — saving current run as baseline.")
        _save_baseline(baseline_path, current, len(result.trades))
        table, *_ = _render_table(all_days, current, baseline=None)
        print(f"\n{table}")
        print(f"\nBaseline saved. Re-run after a code change to see regressions.")
        return 0

    # ── Compare ────────────────────────────────────────────────────────────────
    total_baseline = sum(baseline.values())
    table, n_regressions, n_improved, n_flat = _render_table(all_days, current, baseline)

    saved_at = ""
    try:
        raw = json.loads(baseline_path.read_text(encoding="utf-8"))
        saved_at = f"  baseline saved: {raw.get('saved_at', 'unknown')}\n"
    except Exception:
        pass

    bar = "=" * 62
    print(f"\n{bar}")
    print(f"BACKTEST COMPARISON  vs  {baseline_path.name}")
    print(saved_at.rstrip())
    print(f"{bar}\n")
    print(table)

    print(f"\n{bar}")
    print("SUMMARY")
    print(f"{bar}")
    print(f"  Current total P&L  : ${total_current:+.0f}")
    print(f"  Baseline total P&L : ${total_baseline:+.0f}")
    print(f"  Delta              : ${total_current - total_baseline:+.0f}")
    print(f"  Days regressed >$50: {n_regressions}")
    print(f"  Days improved  >$50: {n_improved}")
    print(f"  Days flat (±$50)   : {n_flat}")

    # ── Verdict ────────────────────────────────────────────────────────────────
    print(f"\n{bar}")
    print("VERDICT")
    print(f"{bar}")

    if n_regressions > 0:
        print(f"REGRESSION DETECTED — {n_regressions} day(s) worse by >$50.")
        print("Do NOT declare improvement. Fix regressions first.")
        verdict = "REGRESSION"
    elif n_improved > 0:
        print(f"IMPROVEMENT — {n_improved} day(s) better, 0 regressions.")
        print("Every day is flat-or-better. Safe to advance baseline (--save).")
        verdict = "IMPROVEMENT"
    else:
        print("NEUTRAL — no day changed by >$50 in either direction.")
        verdict = "NEUTRAL"

    # ── Save if requested ──────────────────────────────────────────────────────
    if args.save:
        if verdict == "REGRESSION":
            print(f"\n--save requested but REGRESSION detected. Baseline NOT updated.")
            print("Fix regressions first, then re-run with --save.")
        else:
            backup = _save_baseline(baseline_path, current, len(result.trades))
            print(f"\nBaseline updated → {baseline_path}")
            if backup:
                print(f"Prior baseline backed up → {backup.name}")

    return 1 if verdict == "REGRESSION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
