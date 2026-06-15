"""ORB long-only walk-forward analysis.

Reads existing watcher-observations.jsonl and computes walk-forward Sharpe
for ORB_DIRECTION_FILTER=long candidate (leaderboard #5).

Train window: 2025-01-01 to 2025-09-30 (IS)
Test window:  2025-10-01 to 2026-05-15 (OOS)

Output: automation/state/logs/orb-longonly-walkforward.json
"""
from __future__ import annotations

import json
import math
import datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT = ROOT / "automation" / "state" / "logs" / "orb-longonly-walkforward.json"

TRAIN_END = dt.date(2025, 9, 30)
TEST_START = dt.date(2025, 10, 1)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}


def _sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return float("nan")
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    if var <= 0:
        return float("nan")
    return (mean / math.sqrt(var)) * math.sqrt(252)


def _window_stats(obs: list[dict]) -> dict:
    if not obs:
        return {"n": 0, "total_pnl": 0.0, "wr": 0.0, "sharpe": float("nan"), "avg_pnl": 0.0}
    pnls = [o["pnl"] for o in obs]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(pnls),
        "total_pnl": round(sum(pnls), 2),
        "wr": round(wins / len(pnls), 4),
        "sharpe": round(_sharpe(pnls), 4),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
    }


def main() -> None:
    lines = OBS_PATH.read_text(encoding="utf-8").strip().split("\n")

    orb_long = []
    for line in lines:
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("watcher_name") != "orb_watcher":
            continue
        if d.get("direction") != "long":
            continue
        if d.get("would_be_pnl_dollars") is None:
            continue
        bar_ts = d.get("bar_timestamp_et", "")
        try:
            date = dt.datetime.fromisoformat(bar_ts).date()
        except Exception:
            continue
        orb_long.append({
            "date": date,
            "pnl": d["would_be_pnl_dollars"],
            "outcome": d.get("would_be_outcome", "?"),
            "confidence": d.get("confidence", "?"),
        })

    train = [o for o in orb_long if o["date"] <= TRAIN_END]
    test = [o for o in orb_long if o["date"] >= TEST_START]

    train_stats = _window_stats(train)
    test_stats = _window_stats(test)

    # Sharpe stability ratio
    is_sharpe = train_stats["sharpe"]
    oos_sharpe = test_stats["sharpe"]
    ratio = (oos_sharpe / is_sharpe) if is_sharpe and not math.isnan(is_sharpe) and is_sharpe != 0 else float("nan")

    # Quarterly breakdown
    quarters: dict[str, list[float]] = defaultdict(list)
    for o in orb_long:
        qn = (o["date"].month - 1) // 3 + 1
        q = f"{o['date'].year}-Q{qn}"
        quarters[q].append(o["pnl"])

    quarter_stats = {}
    positive_quarters = 0
    for q in sorted(quarters):
        pnls = quarters[q]
        wins = sum(1 for p in pnls if p > 0)
        total = sum(pnls)
        quarter_stats[q] = {
            "n": len(pnls),
            "wr": round(wins / len(pnls), 4),
            "total_pnl": round(total, 2),
        }
        if total > 0:
            positive_quarters += 1

    # Edge capture on J days
    j_day_pnls = {}
    for o in orb_long:
        d = o["date"]
        if d in J_WINNERS or d in J_LOSERS:
            cat = "WINNER" if d in J_WINNERS else "LOSER"
            j_day_pnls[d.isoformat()] = {"pnl": o["pnl"], "category": cat}

    # Edge capture = sum(winners) - sum(max(0, loss_on_loser_days))
    winner_pnl = sum(v["pnl"] for v in j_day_pnls.values() if v["category"] == "WINNER")
    loser_loss = sum(max(0, -v["pnl"]) for v in j_day_pnls.values() if v["category"] == "LOSER")
    edge_capture = winner_pnl - loser_loss

    # Walk-forward gate
    wf_pass = (
        not math.isnan(ratio) and ratio >= 0.5 and
        oos_sharpe > 0 and
        positive_quarters >= 4
    )

    result = {
        "candidate": "ORB_DIRECTION_FILTER (long-only)",
        "generated_at": dt.datetime.now().isoformat(),
        "train_window": "2025-01-01 to 2025-09-30",
        "test_window": "2025-10-01 to 2026-05-15",
        "train_stats": train_stats,
        "test_stats": test_stats,
        "sharpe_ratio_oos_over_is": round(ratio, 4) if not math.isnan(ratio) else None,
        "walk_forward_pass": wf_pass,
        "positive_quarters": positive_quarters,
        "total_quarters": len(quarters),
        "regime_robust": positive_quarters >= 4,
        "quarterly_breakdown": quarter_stats,
        "j_day_pnls": j_day_pnls,
        "edge_capture": round(edge_capture, 2),
        "edge_capture_gate": edge_capture >= 771,
        "concentration_warning": "2026-Q2 may dominate — check quarterly_breakdown",
    }

    print("=" * 60)
    print("ORB Long-Only Walk-Forward Analysis")
    print("=" * 60)
    print(f"Total ORB long obs: {len(orb_long)}")
    print(f"Train: N={train_stats['n']} WR={train_stats['wr']:.1%} P&L=${train_stats['total_pnl']:+.0f} Sharpe={train_stats['sharpe']:.3f}")
    print(f"Test:  N={test_stats['n']} WR={test_stats['wr']:.1%} P&L=${test_stats['total_pnl']:+.0f} Sharpe={test_stats['sharpe']:.3f}")
    print(f"OOS/IS Sharpe ratio: {ratio:.3f} (gate: >=0.50)")
    print(f"Walk-forward PASS: {wf_pass}")
    print(f"Positive quarters: {positive_quarters}/{len(quarters)}")
    print()
    print("Quarterly breakdown:")
    for q, qs in quarter_stats.items():
        sign = "+" if qs["total_pnl"] > 0 else "-"
        print(f"  {q}: N={qs['n']} WR={qs['wr']:.0%} P&L=${qs['total_pnl']:+.0f}")
    print()
    print(f"Edge capture (J days): ${edge_capture:+.0f} (gate: >=$771)")
    print(f"Edge capture PASS: {edge_capture >= 771}")
    print()
    print(f"J day P&L: {j_day_pnls}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nOutput: {OUT}")


if __name__ == "__main__":
    main()
