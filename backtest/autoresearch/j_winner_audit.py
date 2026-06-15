"""J-winner audit — compute OP-16 edge_capture scorecard for any candidate params.

For each of J's 7 source-of-truth trades (3 winners + 4 losers, OP-16), runs a
single-day backtest and classifies engine behavior:

  CAUGHT     = winner day, engine P&L > 0
  MISSED     = winner day, engine P&L <= 0  (engine skipped/lost on a J win)
  AVOIDED    = loser day, engine P&L >= 0   (engine correctly ducked J's loss)
  OVERTRADED = loser day, engine P&L < 0    (engine lost on a day it should have avoided)

edge_capture = sum(engine_pnl_winning_days) - sum(max(0, engine_loss_on_losing_days))
OP-16 floor = $771 (50% of max $1542).  Candidates below floor are REJECTED.

Usage:
  python backtest/autoresearch/j_winner_audit.py                         # current params.json
  python backtest/autoresearch/j_winner_audit.py --params automation/state/params_safe.json
  python backtest/autoresearch/j_winner_audit.py --slug v15.2-safe

Output:
  analysis/j-edge/{date}-{slug}.json   machine-readable scorecard
  analysis/j-edge/{date}-{slug}.md     narrative report

Cost: $0 (pure Python)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest

# OP-16 source-of-truth J trades (immutable per CLAUDE.md OP-16)
J_WINNER_DAYS: dict[str, float] = {
    "2026-04-29": 342.0,
    "2026-05-01": 470.0,
    "2026-05-04": 730.0,
}
J_LOSER_DAYS: dict[str, float] = {
    "2026-05-05": -260.0,
    "2026-05-06": -300.0,
    "2026-05-07": -165.0,   # sum of bear (-45) + bull (-120)
}
ALL_J_DAYS: set[str] = set(J_WINNER_DAYS) | set(J_LOSER_DAYS)
OP16_FLOOR = 771.0
MAX_EDGE = 1542.0


# ---------------------------------------------------------------------------
# Helpers — same logic as vix_soft_walk_forward.py window helpers
# ---------------------------------------------------------------------------

def _get_daily(result) -> dict[str, float]:
    """Aggregate P&L by trade-entry date from a backtest result."""
    daily: dict[str, float] = {}
    for t in result.trades:
        if t.entry_time_et:
            day = str(t.entry_time_et)[:10]
            daily[day] = daily.get(day, 0) + t.dollar_pnl
    return daily


def _classify(day: str, engine_pnl: float) -> str:
    if day in J_WINNER_DAYS:
        return "CAUGHT" if engine_pnl > 0 else "MISSED"
    else:
        return "AVOIDED" if engine_pnl >= 0 else "OVERTRADED"


def run_audit(
    params: dict,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    slug: str,
) -> dict:
    """Run backtest over J-day window and compute OP-16 scorecard."""
    # J-days span 2026-04-29 to 2026-05-07
    start = dt.date(2026, 4, 28)   # one day before first J-day for context
    end   = dt.date(2026, 5, 7)

    spy_window = spy_df[spy_df["timestamp_et"] <= f"{end.isoformat()}T23:59:59"].copy()
    vix_window = vix_df[vix_df["timestamp_et"] <= f"{end.isoformat()}T23:59:59"].copy()

    result = run_backtest(
        spy_df=spy_window,
        vix_df=vix_window,
        start_date=start,
        end_date=end,
        **params,
    )
    daily = _get_daily(result)

    # OP-16 scoring
    winner_total = sum(daily.get(d, 0.0) for d in J_WINNER_DAYS)
    loser_exposure = sum(max(0.0, -daily.get(d, 0.0)) for d in J_LOSER_DAYS)
    edge_capture = winner_total - loser_exposure
    op16_pass = edge_capture >= OP16_FLOOR
    edge_pct = round(edge_capture / MAX_EDGE * 100, 1)

    per_day: list[dict] = []
    for day, j_pnl in sorted({**J_WINNER_DAYS, **J_LOSER_DAYS}.items()):
        engine_pnl = daily.get(day, 0.0)
        per_day.append({
            "date": day,
            "role": "winner" if day in J_WINNER_DAYS else "loser",
            "j_pnl": j_pnl,
            "engine_pnl": round(engine_pnl, 2),
            "classification": _classify(day, engine_pnl),
            "delta_vs_j": round(engine_pnl - j_pnl, 2),
        })

    return {
        "slug": slug,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "op16": {
            "edge_capture": round(edge_capture, 2),
            "edge_capture_pct": edge_pct,
            "winner_total": round(winner_total, 2),
            "loser_exposure": round(loser_exposure, 2),
            "op16_pass": op16_pass,
            "verdict": "PROMISING" if op16_pass else "REJECTED",
        },
        "per_day": per_day,
        "summary": {
            "caught": sum(1 for d in per_day if d["classification"] == "CAUGHT"),
            "missed": sum(1 for d in per_day if d["classification"] == "MISSED"),
            "avoided": sum(1 for d in per_day if d["classification"] == "AVOIDED"),
            "overtraded": sum(1 for d in per_day if d["classification"] == "OVERTRADED"),
        },
    }


def _write_report(scorecard: dict, out_dir: Path) -> tuple[Path, Path]:
    """Write JSON + Markdown report.  Returns (json_path, md_path)."""
    slug = scorecard["slug"]
    today = dt.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{today}-{slug}.json"
    json_path.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")

    op16 = scorecard["op16"]
    per_day = scorecard["per_day"]
    s = scorecard["summary"]
    lines = [
        f"# J-Winner Audit — {slug} — {today}",
        "",
        f"**OP-16 verdict:** `{op16['verdict']}`  "
        f"edge_capture={op16['edge_capture']:.0f} / {MAX_EDGE:.0f} ({op16['edge_capture_pct']:.1f}%)",
        f"winner_total={op16['winner_total']:.0f}  loser_exposure={op16['loser_exposure']:.0f}",
        "",
        f"**Day classification:** {s['caught']}×CAUGHT  {s['missed']}×MISSED  "
        f"{s['avoided']}×AVOIDED  {s['overtraded']}×OVERTRADED",
        "",
        "| Date | Role | J P&L | Engine P&L | Classification | Δ vs J |",
        "|------|------|-------|------------|----------------|--------|",
    ]
    for d in per_day:
        lines.append(
            f"| {d['date']} | {d['role']} | ${d['j_pnl']:+.0f} | "
            f"${d['engine_pnl']:+.0f} | {d['classification']} | ${d['delta_vs_j']:+.0f} |"
        )
    lines += [
        "",
        f"> OP-16 floor = ${OP16_FLOOR:.0f} (50% of ${MAX_EDGE:.0f} max). "
        f"Candidates below floor are REJECTED regardless of aggregate metrics.",
    ]

    md_path = out_dir / f"{today}-{slug}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _compare_recent(out_dir: Path, current_slug: str) -> list[dict]:
    """Load up to 5 most-recent prior scorecards for comparison."""
    prior: list[dict] = []
    for p in sorted(out_dir.glob("*.json"), reverse=True):
        if current_slug in p.stem:
            continue   # skip the current one we just wrote
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "op16" in data:
                prior.append({
                    "file": p.name,
                    "edge_capture": data["op16"]["edge_capture"],
                    "verdict": data["op16"]["verdict"],
                })
        except Exception:
            pass
        if len(prior) >= 5:
            break
    return prior


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--params",
        type=Path,
        default=ROOT / "automation" / "state" / "params.json",
        help="Path to params JSON file (default: automation/state/params.json)",
    )
    p.add_argument(
        "--slug",
        default=None,
        help="Label for the candidate (default: rule_version from params)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "analysis" / "j-edge",
        help="Output directory for JSON + MD reports",
    )
    p.add_argument(
        "--spy",
        type=Path,
        default=REPO / "data" / "spy_5m_2025-01-01_2026-05-15.csv",
        help="Path to SPY 5m CSV",
    )
    p.add_argument(
        "--vix",
        type=Path,
        default=REPO / "data" / "vix_5m_2025-01-01_2026-05-15.csv",
        help="Path to VIX 5m CSV",
    )
    args = p.parse_args(argv)

    if not args.params.exists():
        print(f"ERROR: params file not found: {args.params}", file=sys.stderr)
        return 1

    raw_params = json.loads(args.params.read_text(encoding="utf-8"))
    slug = args.slug or raw_params.get("rule_version", "unknown")

    # Strip non-backtest keys that run_backtest doesn't accept
    BACKTEST_KEYS = {
        "use_real_fills", "premium_stop_pct", "premium_stop_pct_bear",
        "premium_stop_pct_bull", "tp1_premium_pct", "tp1_qty_fraction",
        "runner_target_premium_pct", "strike_offset", "no_trade_before",
        "no_trade_window", "profit_lock_mode", "profit_lock_threshold_pct",
        "profit_lock_stop_offset_pct", "profit_lock_trail_pct", "f9_vol_mult",
        "vix_soft_mode", "allow_one_blocker", "allow_one_blocker_min_spread_cents",
    }
    backtest_params = {k: v for k, v in raw_params.items() if k in BACKTEST_KEYS}

    # Convert string time to dt.time if needed
    if "no_trade_before" in backtest_params and isinstance(backtest_params["no_trade_before"], str):
        h, m = backtest_params["no_trade_before"].split(":")
        backtest_params["no_trade_before"] = dt.time(int(h), int(m))

    print(f"Loading SPY + VIX data...")
    spy_df = pd.read_csv(args.spy)
    vix_df = pd.read_csv(args.vix)
    print(f"  {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows")

    print(f"Running OP-16 J-winner audit for slug='{slug}'...")
    scorecard = run_audit(backtest_params, spy_df, vix_df, slug)

    # Print results
    op16 = scorecard["op16"]
    s = scorecard["summary"]
    print()
    print(f"  OP-16 verdict:    {op16['verdict']}")
    print(f"  edge_capture:     ${op16['edge_capture']:+.0f}  ({op16['edge_capture_pct']:.1f}% of ${MAX_EDGE:.0f} max)")
    print(f"  winner_total:     ${op16['winner_total']:+.0f}")
    print(f"  loser_exposure:   ${op16['loser_exposure']:+.0f}")
    print(f"  classifications:  {s['caught']}×CAUGHT  {s['missed']}×MISSED  "
          f"{s['avoided']}×AVOIDED  {s['overtraded']}×OVERTRADED")
    print()
    print(f"  {'Date':<12} {'Role':<8} {'J P&L':>8}  {'Engine P&L':>12}  {'Classification':<16} {'Δ vs J':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*8}  {'-'*12}  {'-'*16} {'-'*8}")
    for d in scorecard["per_day"]:
        marker = "✓" if d["classification"] in ("CAUGHT", "AVOIDED") else "✗"
        print(f"  {marker} {d['date']:<11} {d['role']:<8} ${d['j_pnl']:+7.0f}  "
              f"${d['engine_pnl']:+11.2f}  {d['classification']:<16} ${d['delta_vs_j']:+7.0f}")

    # Write output
    json_path, md_path = _write_report(scorecard, args.out_dir)
    print()
    print(f"  Wrote: {json_path}")
    print(f"  Wrote: {md_path}")

    # Comparison vs recent
    prior = _compare_recent(args.out_dir, slug)
    if prior:
        print()
        print("  Recent candidates for comparison:")
        for pr in prior:
            print(f"    {pr['file']:<50} edge={pr['edge_capture']:+.0f}  {pr['verdict']}")

    return 0 if op16["op16_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
