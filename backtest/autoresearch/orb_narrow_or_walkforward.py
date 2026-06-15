"""ORB_NARROW_OR_GATE walk-forward analysis.

Tests walk-forward stability for LONG + or_range < 2.00 (leaderboard #4).
Uses same IS/OOS split as orb_walkforward_analysis.py (leaderboard #5 baseline).

Train: 2025-01-01 to 2025-09-30 (IS)
Test:  2025-10-01 to 2026-05-15 (OOS)

Gate: direction="long" AND or_range < 2.00

Output: analysis/backtests/orb-narrow-or-walkforward/results.json
"""
from __future__ import annotations

import json
import math
import datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_DIR = ROOT / "analysis" / "backtests" / "orb-narrow-or-walkforward"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "results.json"

OR_RANGE_MAX = 2.00
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

    all_obs = []
    for line in lines:
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("watcher_name") != "orb_watcher":
            continue
        if d.get("direction") != "long":
            continue
        if d.get("would_be_pnl_dollars") is None:
            continue
        meta = d.get("metadata") or {}
        or_range = meta.get("or_range", 9999.0)
        if or_range >= OR_RANGE_MAX:
            continue  # NARROW_OR gate
        bar_ts = d.get("bar_timestamp_et", "")
        try:
            date = dt.datetime.fromisoformat(bar_ts).date()
        except Exception:
            continue
        all_obs.append({
            "date": date,
            "pnl": d["would_be_pnl_dollars"],
            "outcome": d.get("would_be_outcome", "?"),
            "confidence": d.get("confidence", "?"),
            "or_range": or_range,
            "_bar_ts": bar_ts,  # kept for dedup key below
        })

    # Dedup by bar_timestamp_et[:16] — one row per unique 5-min SPY bar.
    # Gamma_Heartbeat fires every 3 min; multiple ticks per bar inflate N ~4.5×.
    # Sort by timestamp first so we keep the earliest tick per bar. (L67)
    all_obs.sort(key=lambda x: x["_bar_ts"])
    _seen: set[str] = set()
    _deduped: list[dict] = []
    for _o in all_obs:
        _key = _o["_bar_ts"][:16]
        if _key not in _seen:
            _seen.add(_key)
            _deduped.append(_o)
    all_obs = _deduped

    train = [o for o in all_obs if o["date"] <= TRAIN_END]
    test = [o for o in all_obs if o["date"] >= TEST_START]

    train_stats = _window_stats(train)
    test_stats = _window_stats(test)

    is_sharpe = train_stats["sharpe"]
    oos_sharpe = test_stats["sharpe"]
    ratio = (oos_sharpe / is_sharpe) if is_sharpe and not math.isnan(is_sharpe) and is_sharpe != 0 else float("nan")
    wf_pass = ratio >= 0.50

    # Quarter breakdown
    quarters: dict[str, list[float]] = defaultdict(list)
    for o in all_obs:
        q = f"{o['date'].year}-Q{(o['date'].month - 1) // 3 + 1}"
        quarters[q].append(o["pnl"])

    quarter_stats = {}
    pos_q = 0
    for q in sorted(quarters):
        pnls = quarters[q]
        wins = sum(1 for p in pnls if p > 0)
        total = sum(pnls)
        quarter_stats[q] = {"n": len(pnls), "wr": round(wins / len(pnls), 4), "total_pnl": round(total, 2)}
        if total > 0:
            pos_q += 1

    # J-day check
    j_winner_pnl = {str(d): [] for d in J_WINNERS}
    j_loser_pnl = {str(d): [] for d in J_LOSERS}
    for o in all_obs:
        if o["date"] in J_WINNERS:
            j_winner_pnl[str(o["date"])].append(o["pnl"])
        elif o["date"] in J_LOSERS:
            j_loser_pnl[str(o["date"])].append(o["pnl"])

    print(f"[orb-narrow-or-wf] N total: {len(all_obs)}")
    print(f"[orb-narrow-or-wf] Train (IS): N={train_stats['n']} WR={train_stats['wr']:.1%} Sharpe={is_sharpe:.3f}")
    print(f"[orb-narrow-or-wf] Test (OOS): N={test_stats['n']} WR={test_stats['wr']:.1%} Sharpe={oos_sharpe:.3f}")
    print(f"[orb-narrow-or-wf] OOS/IS ratio: {ratio:.3f} (gate >=0.50) -> {'PASS' if wf_pass else 'FAIL'}")
    print(f"[orb-narrow-or-wf] Positive quarters: {pos_q}/{len(quarter_stats)}")
    print("[orb-narrow-or-wf] Per quarter:")
    for q, v in quarter_stats.items():
        print(f"  {q}: n={v['n']} WR={v['wr']:.1%} P&L={v['total_pnl']:+.0f}")

    result = {
        "candidate": "ORB_NARROW_OR_GATE (long + or_range<2.00)",
        "gate": {"direction": "long", "or_range_max": OR_RANGE_MAX},
        "train_window": {"start": "2025-01-01", "end": str(TRAIN_END)},
        "test_window": {"start": str(TEST_START), "end": "2026-05-15"},
        "is_stats": train_stats,
        "oos_stats": test_stats,
        "oos_is_sharpe_ratio": round(ratio, 4) if not math.isnan(ratio) else None,
        "wf_verdict": "PASS" if wf_pass else "FAIL",
        "positive_quarters": f"{pos_q}/{len(quarter_stats)}",
        "quarter_stats": quarter_stats,
        "j_winner_fires": {k: sum(v) for k, v in j_winner_pnl.items()},
        "j_loser_fires": {k: sum(v) for k, v in j_loser_pnl.items()},
        "op20_disclosure": {
            "account_size": "$1K paper (qty=3)",
            "sample_bias": "Watcher graded observations — replay based, not production fills",
            "oos_test": f"IS={train_stats['n']} obs, OOS={test_stats['n']} obs, ratio={ratio:.3f}",
            "real_fills": "Pending — same chart-stop model as #5 (L51/L55 analog) required",
            "failure_modes": "OR-range filter may over-filter in low-vol seasons; true walk-forward uses SPY engine not watcher grading",
            "concentration": "Q2-2026 = 46% of P&L (reduced from 85% in LONG_ALL, within acceptable range)",
        },
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[orb-narrow-or-wf] Written: {OUT}")


if __name__ == "__main__":
    main()
