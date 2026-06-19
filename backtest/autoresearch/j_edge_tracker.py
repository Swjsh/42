"""J-edge tracker — the CANONICAL scorer per CLAUDE.md operating principle 16.

For any candidate parameter set, computes:
  edge_capture = sum(engine_pnl on J's winning days) - sum(max(0, engine_loss on J's losing days))

A perfect candidate captures J's $1,542 of winners and adds zero of his losses
on losing days = score 1542. A candidate that misses winners and skips losers
scores 0. A candidate that takes losing trades on J's winners scores NEGATIVE.

This is the PRIMARY metric. Aggregate Sharpe / total P&L are SECONDARY tiebreakers
between candidates with similar edge_capture.

USAGE:
    from autoresearch.j_edge_tracker import score_candidate
    result = score_candidate(params, spy_df, vix_df)
    print(f"edge_capture: ${result['edge_capture']:.0f}  detail: {result['by_day']}")
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import runner

REPO = Path(__file__).resolve().parent.parent

# Source-of-truth trades from CLAUDE.md operating principle 16.
J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342, "side": "P", "strike": 710,
     "note": "711.4 rejection + ribbon flip"},
    {"date": "2026-05-01", "j_pnl": 470, "side": "P", "strike": 721,
     "note": "trendline rejection at 13:36 (leg #2 was real trigger)"},
    {"date": "2026-05-04", "j_pnl": 730, "side": "P", "strike": 721,
     "note": "premarket level + multi-day trendline + ribbon flip = CONFLUENCE"},
]

J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260, "side": "P", "strike": 722,
     "note": "chop-trap manual entry, no real setup"},
    {"date": "2026-05-06", "j_pnl": -300, "side": "P", "strike": 730,
     "note": "held to zero, no stop"},
    {"date": "2026-05-07", "j_pnl": -45, "side": "C", "strike": 734,
     "note": "engine BULL into pre-FOMC bear sequence"},
    {"date": "2026-05-07", "j_pnl": -120, "side": "C", "strike": 737,
     "note": "manual bullish anticipation at session high"},
]

J_TOTAL_WINNERS = sum(t["j_pnl"] for t in J_WINNERS)  # 1542
J_TOTAL_LOSERS_ABS = sum(-t["j_pnl"] for t in J_LOSERS)  # 725


def _run_one_day(params: dict, date_str: str, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """Run engine on one day, return concise summary."""
    d = dt.date.fromisoformat(date_str)
    try:
        result, m = runner.run_with_params(params, d, d, spy_df, vix_df)
    except Exception as exc:  # noqa: BLE001
        return {"date": date_str, "error": repr(exc)}
    trades = []
    for t in result.trades:
        trades.append({
            "side": getattr(t, "side", "?"),
            "strike": getattr(t, "strike", None),
            "entry_premium": round(getattr(t, "entry_premium", 0), 3),
            "exit_premium": round(getattr(t, "exit_premium", 0), 3),
            "pnl": round(getattr(t, "pnl_dollars", 0), 2),
        })
    return {
        "date": date_str, "n_trades": m.n_trades, "n_winners": m.n_winners,
        "total_pnl": round(m.total_pnl, 2), "trades": trades,
    }


def score_candidate(params: dict, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """Compute edge_capture for a candidate.

    Returns dict with:
        edge_capture: float (PRIMARY metric)
        winners_capture: float (sum of engine pnl on J's winning days, capped at 0 below)
        losers_added: float (sum of engine LOSSES on J's losing days, as positive number)
        winners_capture_pct: % of J_TOTAL_WINNERS captured
        by_day: per-day detail
    """
    by_day = []
    winners_capture = 0.0
    losers_added = 0.0

    for w in J_WINNERS:
        r = _run_one_day(params, w["date"], spy_df, vix_df)
        if "error" not in r:
            engine_pnl = r["total_pnl"]
            winners_capture += engine_pnl  # positive contributions sum; losses subtract
            r["j_pnl"] = w["j_pnl"]
            r["edge_kind"] = "WIN"
            r["capture_pct"] = round(engine_pnl / w["j_pnl"], 3) if w["j_pnl"] else 0
        by_day.append(r)

    for l in J_LOSERS:
        r = _run_one_day(params, l["date"], spy_df, vix_df)
        if "error" not in r:
            engine_pnl = r["total_pnl"]
            # Engine loss on J's losing day is BAD. Engine profit there is bonus (don't add to losers_added).
            if engine_pnl < 0:
                losers_added += -engine_pnl
            r["j_pnl"] = l["j_pnl"]
            r["edge_kind"] = "LOSS"
            r["engine_did_skip"] = (r["n_trades"] == 0)
        by_day.append(r)

    edge_capture = winners_capture - losers_added

    return {
        "edge_capture": round(edge_capture, 2),
        "winners_capture": round(winners_capture, 2),
        "winners_capture_pct": round(winners_capture / J_TOTAL_WINNERS, 3) if J_TOTAL_WINNERS else 0,
        "losers_added": round(losers_added, 2),
        "j_total_winners": J_TOTAL_WINNERS,
        "j_total_losers_abs": J_TOTAL_LOSERS_ABS,
        "max_possible_score": J_TOTAL_WINNERS,  # if engine perfectly captures + skips
        "by_day": by_day,
    }


def print_score_card(result: dict) -> None:
    print(f"\n  edge_capture:        ${result['edge_capture']:+.0f}")
    print(f"  winners_capture:     ${result['winners_capture']:+.0f} ({result['winners_capture_pct']*100:.0f}% of J's ${result['j_total_winners']})")
    print(f"  losers_added:        ${result['losers_added']:.0f}")
    print(f"  max possible:        ${result['max_possible_score']}")
    print()
    print(f"  {'date':<12} {'kind':<5} {'engine_pnl':>11} {'j_pnl':>8} {'capture%':>9}  trades")
    for r in result["by_day"]:
        if "error" in r:
            print(f"  {r['date']:<12} ERROR")
            continue
        kind = r.get("edge_kind", "?")
        cap = r.get("capture_pct", 0)
        engine_pnl = r["total_pnl"]
        n = r["n_trades"]
        cap_str = f"{cap*100:+.0f}%" if kind == "WIN" else ("SKIP" if r.get("engine_did_skip") else "TOOK")
        trades_summary = " | ".join(
            f"{t['side']}{t.get('strike', '?')} ${t['entry_premium']:.2f}->${t['exit_premium']:.2f} ${t['pnl']:+.0f}"
            for t in r.get("trades", [])
        ) or "(none)"
        print(f"  {r['date']:<12} {kind:<5} ${engine_pnl:+10.0f} ${r.get('j_pnl', 0):+7.0f} {cap_str:>9}  {trades_summary[:80]}")


# v15-j-edge candidate overrides — locked doctrine + Config 1 entry knobs.
# Per CLAUDE.md OP 17 these 4 exit knobs (seed10095 doctrine) are LOCKED on every
# winner the engine takes. Config 1 entry knobs (strike_offset_bear=0,
# min_triggers_bear=1) are the proven baseline that fires on all 3 of J's winning
# days. This is the canonical baseline the j_edge_tracker scores against until
# all 5 OP 17 BEAT-J conditions are met and params.json is bumped.
V15_J_EDGE_OVERRIDES = {
    # Config 1 entry knobs (proven to fire on all 3 J winning days)
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    # Exit knobs — updated 2026-05-23 to match ACTUAL v15.2 production heartbeat.md.
    # (Prior values were v15.0 initial doctrine from 2026-05-13; v14_enhanced_grinder
    # param sweep confirmed tp1=0.30 + runner=2.50 is the $26,601 optimum and v15.2
    # heartbeat already runs exactly these values per docs/V15-ACTIVATION-2026-05-13.md.)
    "tp1_premium_pct": 0.50,           # heartbeat.md: premium >= entry * 1.50 fallback (Rank-36 2026-06-17)
    "tp1_qty_fraction": 0.667,          # params.json: 66.7% off at TP1 (synced 2026-06-17)
    "runner_max_premium_pct": 2.5,     # heartbeat.md: runner_target_premium_pct = 2.50 (params.json key = runner_max_premium_pct)
    "premium_stop_pct_bear": -0.10,    # params.json: -10% bear premium stop (Rank 33, 2026-06-17)
}


def main() -> int:
    """CLI: score the v15-j-edge candidate baseline against J's source-of-truth trades.

    Loads production params.json then APPLIES v15-j-edge candidate overrides
    (locked seed10095 exit doctrine + Config 1 entry knobs). This is the
    canonical baseline the j_edge_tracker scores against until all 5 OP 17
    BEAT-J conditions are met and params.json is bumped (rule 9 — needs J's
    ratification before bump).
    """
    params_path = REPO.parent / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    print("=" * 100)
    print(f"J-EDGE SCORE: v15-j-edge candidate (production rule_version={params.get('rule_version', '?')} + locked doctrine + Config 1)")
    print("=" * 100)

    # Load enough data to cover all J days
    min_d = dt.date.fromisoformat(min(t["date"] for t in J_WINNERS + J_LOSERS))
    max_d = dt.date.fromisoformat(max(t["date"] for t in J_WINNERS + J_LOSERS))
    spy, vix = runner.load_data(min_d, max_d)

    result = score_candidate(params, spy, vix)
    print_score_card(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
