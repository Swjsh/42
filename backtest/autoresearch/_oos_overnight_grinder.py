"""OOS walk-forward validation for overnight_grinder top keeper combo.

Tests whether the best overnight_grinder result (edge_capture=3224.74,
wide_pnl=$12,105 at qty=25) generalizes out-of-sample.

Keeper #1 parameters (from strategy/candidates/2026-05-23-chef-nemo-grinder-overnight-grinder-20260523-2223.md):
  super_stop=-0.15, super_tp1=0.75, runner_target=2.0,
  level_qty=25, level_stop=-0.12, level_tp1=0.40, trendline_stop=-0.06

Uses the same _patch_orchestrator monkey-patch the overnight_grinder uses,
combined with V15_J_EDGE_OVERRIDES for production param baseline.

IS/OOS split (same as _oos_v14e_26k.py for consistency):
  IS:  2025-01-01 .. 2025-09-30
  OOS: 2025-10-01 .. 2026-05-22

CLI:
  python autoresearch/_oos_overnight_grinder.py
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_WINNERS, J_LOSERS  # noqa: E402

PARAMS_PATH = REPO.parent / "automation" / "state" / "params.json"

# Top keeper from overnight_grinder (2026-05-24 run)
KEEPER_COMBO = {
    "super_stop": -0.15,
    "super_tp1": 0.75,
    "runner_target": 2.0,
    "level_qty": 25,
    "level_stop": -0.12,
    "level_tp1": 0.40,
    "trendline_stop": -0.06,
}

IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END = dt.date(2026, 5, 22)
FULL_START = IS_START
FULL_END = OOS_END

OUT_JSON = REPO / "autoresearch" / "_state" / "oos_overnight_grinder_results.json"


@contextmanager
def _patch_orchestrator(combo: dict):
    """Monkey-patch lib.orchestrator._grinder_overrides for one run."""
    import lib.orchestrator as orc  # noqa: E402
    orig = getattr(orc, "_grinder_overrides", None)
    orc._grinder_overrides = combo
    try:
        yield
    finally:
        if orig is None:
            if hasattr(orc, "_grinder_overrides"):
                del orc._grinder_overrides
        else:
            orc._grinder_overrides = orig


def _sharpe(trades) -> float:
    day_pnl: dict = defaultdict(float)
    for t in trades:
        day_pnl[t.entry_time_et.date()] += t.dollar_pnl
    vals = list(day_pnl.values())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def _stats(res, m, label: str) -> dict:
    trades = res.trades
    day_pnl: dict = defaultdict(float)
    quarter_pnl: dict = defaultdict(float)
    for t in trades:
        d = t.entry_time_et.date()
        day_pnl[d] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl[q] += t.dollar_pnl
    sharpe = _sharpe(trades)
    pos_q = sum(1 for v in quarter_pnl.values() if v > 0)
    total_q = len(quarter_pnl)
    sorted_day = sorted(day_pnl.values(), reverse=True)
    top5 = sum(sorted_day[:5])
    top5_pct = round(top5 / m.total_pnl, 3) if m.total_pnl > 0 else 999.0
    return {
        "window": label,
        "n_trades": m.n_trades,
        "total_pnl": round(m.total_pnl, 2),
        "wr": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0.0,
        "sharpe": round(sharpe, 3),
        "pos_q": pos_q,
        "total_q": total_q,
        "top5_pct": top5_pct,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl.items())},
    }


def main() -> None:
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    print("=" * 72)
    print("OOS Walk-Forward: overnight_grinder top keeper")
    print(f"Keeper combo: {KEEPER_COMBO}")
    print(f"V15 overrides: {V15_J_EDGE_OVERRIDES}")
    print(f"IS: {IS_START}..{IS_END}   OOS: {OOS_START}..{OOS_END}")
    print("=" * 72)
    print()

    print("Loading data...", end=" ", flush=True)
    t0 = time.perf_counter()
    spy_all, vix_all = _runner.load_data(FULL_START, FULL_END)
    print(f"{time.perf_counter() - t0:.1f}s")

    windows = [
        ("FULL", FULL_START, FULL_END),
        ("IS  ", IS_START, IS_END),
        ("OOS ", OOS_START, OOS_END),
    ]

    results: dict = {}
    with _patch_orchestrator(KEEPER_COMBO):
        for label, start, end in windows:
            t0 = time.perf_counter()
            res, m = _runner.run_with_params(params, start, end, spy_all, vix_all)
            elapsed = time.perf_counter() - t0
            stats = _stats(res, m, label)
            results[label.strip()] = stats

            print(f"[{label}] {start}..{end}"
                  f"  n={stats['n_trades']:>3}  pnl=${stats['total_pnl']:>9,.0f}"
                  f"  wr={stats['wr']:.1%}  sharpe={stats['sharpe']:.3f}"
                  f"  +q={stats['pos_q']}/{stats['total_q']}"
                  f"  top5={stats['top5_pct']:.1%}  ({elapsed:.1f}s)")
            if label.strip() in ("IS", "OOS"):
                qd = stats["quarter_pnl"]
                for q, v in sorted(qd.items()):
                    print(f"       {q}: ${v:+,.0f}")
            print()

    # WF gate
    is_s = results.get("IS", {}).get("sharpe", 0)
    oos_s = results.get("OOS", {}).get("sharpe", 0)
    ratio = oos_s / is_s if is_s != 0 else 0.0

    print("=" * 72)
    print("WALK-FORWARD GATE (>= 0.50)")
    print(f"  IS  Sharpe  : {is_s:.3f}")
    print(f"  OOS Sharpe  : {oos_s:.3f}")
    print(f"  WF ratio    : {ratio:.3f}  ->  {'PASS' if ratio >= 0.50 else 'FAIL'}")
    print()

    # Secondary gates
    oos = results.get("OOS", {})
    oos_pnl_pass = oos.get("total_pnl", -1) > 0
    oos_wr_pass = oos.get("wr", 0) >= 0.45
    oos_q_pass = oos.get("pos_q", 0) >= 2

    print("Secondary gates:")
    print(f"  OOS P&L > 0       : ${oos.get('total_pnl', 0):,.0f}  {'PASS' if oos_pnl_pass else 'FAIL'}")
    print(f"  OOS WR >= 45%     : {oos.get('wr', 0):.1%}  {'PASS' if oos_wr_pass else 'FAIL'}")
    print(f"  OOS +q >= 2       : {oos.get('pos_q', 0)}/{oos.get('total_q', 0)}  {'PASS' if oos_q_pass else 'FAIL'}")

    overall = ratio >= 0.50 and oos_pnl_pass and oos_wr_pass and oos_q_pass
    print()
    print(f"VERDICT: {'OOS PASS -- candidate for promotion' if overall else 'OOS FAIL -- do not promote'}")

    # Edge capture on J anchor days (with patch active, reuse the same patched session)
    print()
    print("J-anchor day P&L (keeper combo):")
    with _patch_orchestrator(KEEPER_COMBO):
        anchor_days = sorted(
            set(t["date"] for t in J_WINNERS + J_LOSERS)
        )
        min_d = dt.date.fromisoformat(min(anchor_days))
        max_d = dt.date.fromisoformat(max(anchor_days))
        spy_j, vix_j = _runner.load_data(min_d, max_d)
        by_day: dict = {}
        for entry in J_WINNERS + J_LOSERS:
            d = dt.date.fromisoformat(entry["date"])
            _, m_day = _runner.run_with_params(params, d, d, spy_j, vix_j)
            key = entry["date"]
            if key in by_day:
                key += "_2"
            by_day[key] = round(m_day.total_pnl, 2)

    winners_cap = sum(by_day.get(w["date"], 0) for w in J_WINNERS)
    losers_added = sum(max(0.0, -by_day.get(l["date"], 0)) for l in J_LOSERS)
    edge_capture = winners_cap - losers_added
    print(f"  winners_capture : ${winners_cap:+,.2f}")
    print(f"  losers_added    : ${losers_added:+,.2f}")
    print(f"  edge_capture    : ${edge_capture:+,.2f}  (max possible ~${sum(w['j_pnl'] for w in J_WINNERS):+,.0f})")
    print()
    for k, v in sorted(by_day.items()):
        label = "WINNER" if any(k.startswith(w["date"]) for w in J_WINNERS) else "loser"
        print(f"  {k}  ${v:+,.2f}  [{label}]")

    # Save
    payload = {
        "run_at": dt.datetime.now().isoformat(),
        "keeper_combo": KEEPER_COMBO,
        "v15_overrides": V15_J_EDGE_OVERRIDES,
        "results": {k: v for k, v in results.items()},
        "wf_ratio": round(ratio, 3),
        "wf_pass": ratio >= 0.50,
        "edge_capture": round(edge_capture, 2),
        "winners_capture": round(winners_cap, 2),
        "losers_added": round(losers_added, 2),
        "by_day": by_day,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved to {OUT_JSON}")


if __name__ == "__main__":
    main()
