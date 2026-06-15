"""Inspect a single grinder combo: per-day P&L, max drawdown, per-quarter split.

Use after the overnight grinder finishes to verify a top candidate's wide-window
P&L isn't coming from a few outsized winners (regime-fragile) — true regime-robust
candidates spread profit across many days.

Usage:
    python -m autoresearch.inspect_combo --combo-json '{"super_stop":-0.20,...}'
    python -m autoresearch.inspect_combo --rank 1   # top from keepers.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "autoresearch" / "_state" / "overnight_grinder"


def _load_top_combo(rank: int) -> dict:
    keepers_path = OUT / "keepers.jsonl"
    if not keepers_path.exists():
        raise SystemExit("no keepers.jsonl found — has the grinder run yet?")
    rows = []
    for line in keepers_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    rows.sort(key=lambda r: -r.get("wide_pnl", 0))
    if rank > len(rows):
        raise SystemExit(f"only {len(rows)} keepers; cannot rank #{rank}")
    return rows[rank - 1]["combo"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combo-json", type=str, default=None)
    parser.add_argument("--rank", type=int, default=1)
    parser.add_argument("--start", type=str, default="2025-01-01")
    parser.add_argument("--end", type=str, default="2026-05-07")
    args = parser.parse_args()

    if args.combo_json:
        combo = json.loads(args.combo_json)
    else:
        combo = _load_top_combo(args.rank)

    print("Loading data and patching engine...")
    import sys
    sys.path.insert(0, str(REPO))
    from autoresearch import runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_WINNERS, J_LOSERS
    from autoresearch.overnight_grinder import _patch_orchestrator

    params_path = REPO.parent / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    spy, vix = runner.load_data(start, end)

    print(f"\nINSPECTING combo: {combo}")
    print("=" * 100)

    with _patch_orchestrator(combo):
        result, m = runner.run_with_params(params, start, end, spy, vix)

    trades = result.trades
    print(f"\nWide window {start} to {end}:")
    print(f"  trades:    {m.n_trades}")
    print(f"  winners:   {m.n_winners}")
    print(f"  win rate:  {(m.n_winners/m.n_trades*100) if m.n_trades else 0:.1f}%")
    print(f"  total P&L: ${m.total_pnl:.0f}")
    print(f"  avg/trade: ${(m.total_pnl/m.n_trades) if m.n_trades else 0:.2f}")

    # Per-quarter breakdown
    if trades:
        from collections import defaultdict
        quarter_pnl = defaultdict(float)
        quarter_count = defaultdict(int)
        for t in trades:
            ts = t.entry_time_et
            q = f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"
            quarter_pnl[q] += t.dollar_pnl
            quarter_count[q] += 1

        print(f"\nPer-quarter breakdown:")
        for q in sorted(quarter_pnl.keys()):
            print(f"  {q}: ${quarter_pnl[q]:>+8.0f}  n={quarter_count[q]:>3}  avg=${quarter_pnl[q]/quarter_count[q]:>+6.2f}")

        # Top 10 winning days
        from collections import defaultdict
        day_pnl = defaultdict(float)
        for t in trades:
            d = t.entry_time_et.date()
            day_pnl[d] += t.dollar_pnl

        sorted_days = sorted(day_pnl.items(), key=lambda kv: -kv[1])
        print(f"\nTop 10 winning days:")
        for d, p in sorted_days[:10]:
            print(f"  {d}: ${p:>+7.0f}")
        print(f"\nWorst 5 losing days:")
        for d, p in sorted_days[-5:]:
            print(f"  {d}: ${p:>+7.0f}")

        # Max drawdown (intraday-aggregated)
        sorted_by_time = sorted(trades, key=lambda t: t.entry_time_et)
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted_by_time:
            cum += t.dollar_pnl
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        print(f"\nMax drawdown (sequential trades): ${max_dd:.0f}")

        # Concentration check: is wide_pnl from <5 days?
        top5_sum = sum(p for _, p in sorted_days[:5])
        top5_pct = (top5_sum / m.total_pnl * 100) if m.total_pnl > 0 else 0
        print(f"Top-5 days = ${top5_sum:.0f} = {top5_pct:.0f}% of total P&L")
        if top5_pct > 80:
            print(f"  ⚠ CONCENTRATION RISK — wide_pnl driven by < 5 days. Regime-fragile candidate.")
        else:
            print(f"  ✓ Spread across many days (regime-robust).")

    # Per-J-day check
    print(f"\nPer-J-day verification:")
    by_day = {}
    for w in J_WINNERS:
        d = dt.date.fromisoformat(w["date"])
        if start <= d <= end:
            sub = [t for t in trades if t.entry_time_et.date() == d]
            day_p = sum(t.dollar_pnl for t in sub)
            print(f"  {w['date']:<12} J=+${w['j_pnl']:<4} engine=${day_p:>+6.0f}  ({len(sub)} trades) {'✓ BEAT' if day_p > w['j_pnl'] else '✗ short'}")
    for l in J_LOSERS:
        d = dt.date.fromisoformat(l["date"])
        if start <= d <= end:
            sub = [t for t in trades if t.entry_time_et.date() == d]
            day_p = sum(t.dollar_pnl for t in sub)
            print(f"  {l['date']:<12} J=${l['j_pnl']:<5} engine=${day_p:>+6.0f}  ({len(sub)} trades) {'✓' if day_p >= 0 else '✗'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
