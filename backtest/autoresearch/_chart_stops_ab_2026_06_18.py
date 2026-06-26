"""TASK 1 — chart-stops-as-default validation (A vs B), real-fills.

Question: should the BEAR-side premium stop be DEMOTED from the primary exit
(-10% now) to a WIDE catastrophe cap (-50%), letting the chart/level stop +
profit-lock chandelier + ribbon-flip-back be the primary invalidation?

Method (clean single-variable A/B):
  - Config A (current live): params.json as-is. bear premium stop = -10%.
  - Config B (chart-stop primary): identical EXCEPT premium_stop_pct_bear = -0.50.
  - EVERYTHING else held constant (same chart-stop buffer, profit-lock, TP1,
    runner, all entry gates). The ONLY variable is the bear premium-stop width.
  - Real fills (use_real_fills=True) over: (1) the 7 J-anchor days and (2) a
    recent OOS window. Real OPRA option bars only exist through ~2026-05-29, so
    the OOS window is bounded there (honest data-coverage limit).

Decision gate (ship B only if ALL hold):
  1. edge_capture(B) >= edge_capture(A)         (no J-edge regression)
  2. anchor: B does not turn a J-winner-day negative that A had positive,
     and B does not add a NEW loss on a J-loser day that A skipped/won.
  3. total OOS P&L(B) not materially worse than A (allow a small band).
  + DSR/PSR advisory via backtest.lib.validation.gate (informational).

Pure Python, $0 cost. Writes a JSON scorecard. NEVER edits live doctrine.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner
from autoresearch.j_edge_tracker import score_candidate
from lib.validation.gate import evaluate_candidate

PARAMS_PATH = REPO / "automation" / "state" / "params.json"

# OOS window — bounded by real OPRA option coverage (through ~2026-05-29).
OOS_START = dt.date(2026, 3, 1)
OOS_END = dt.date(2026, 5, 29)

# Catastrophe-cap value for config B (blueprint: -0.50 wide cap).
B_BEAR_STOP = -0.50


def _load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))


def _config_a() -> dict:
    """Current live config, forced to real fills."""
    p = _load_params()
    p["use_real_fills"] = True
    return p


def _config_b() -> dict:
    """Chart-stop-primary: identical to A except bear premium stop = -50%."""
    p = _config_a()
    p["premium_stop_pct_bear"] = B_BEAR_STOP
    return p


def _oos_metrics(params: dict, spy, vix) -> dict:
    result, m = runner.run_with_params(params, OOS_START, OOS_END, spy, vix)
    trades = result.trades
    pnls = [float(getattr(t, "dollar_pnl", 0.0)) for t in trades]
    n = len(pnls)
    n_win = sum(1 for x in pnls if x > 0)
    total = sum(pnls)
    # exit-reason histogram (shows whether the premium stop even bound)
    by_exit: dict[str, int] = {}
    for t in trades:
        er = getattr(t, "exit_reason", None)
        key = er.value if hasattr(er, "value") else (str(er) if er else "NONE")
        by_exit[key] = by_exit.get(key, 0) + 1
    return {
        "n_trades": n,
        "n_winners": n_win,
        "wr": round(n_win / n, 4) if n else 0.0,
        "total_pnl": round(total, 2),
        "avg_pnl": round(total / n, 2) if n else 0.0,
        "by_exit_reason": by_exit,
        "pnls": pnls,
    }


def _dsr_gate(pnls: list[float], n_trials: int) -> dict:
    if not pnls:
        return {"verdict": "N/A", "note": "no trades"}
    # Per-trade returns proxy: dollar PnL stream (scale-invariant for Sharpe sign).
    res = evaluate_candidate(pnls, n_trials=n_trials)
    return res.to_dict()


def main() -> int:
    print("=" * 92)
    print("TASK 1 — chart-stops-as-default A/B (real-fills)")
    print(f"  A = current live (bear stop {_config_a().get('premium_stop_pct_bear')})")
    print(f"  B = chart-stop primary (bear stop {B_BEAR_STOP})")
    print("=" * 92)

    cfg_a, cfg_b = _config_a(), _config_b()

    # ---- J-edge (anchor days) ----
    print("\n[1/3] J-edge anchor scoring (real-fills)...")
    spy_anchor, vix_anchor = runner.load_data(dt.date(2026, 4, 29), dt.date(2026, 5, 7))
    edge_a = score_candidate(cfg_a, spy_anchor, vix_anchor)
    edge_b = score_candidate(cfg_b, spy_anchor, vix_anchor)
    print(f"  A edge_capture=${edge_a['edge_capture']:+.0f} "
          f"(winners ${edge_a['winners_capture']:+.0f}, losers_added ${edge_a['losers_added']:.0f})")
    print(f"  B edge_capture=${edge_b['edge_capture']:+.0f} "
          f"(winners ${edge_b['winners_capture']:+.0f}, losers_added ${edge_b['losers_added']:.0f})")

    # ---- OOS window ----
    print(f"\n[2/3] OOS real-fills {OOS_START}..{OOS_END}...")
    spy_oos, vix_oos = runner.load_data(OOS_START, OOS_END)
    oos_a = _oos_metrics(cfg_a, spy_oos, vix_oos)
    oos_b = _oos_metrics(cfg_b, spy_oos, vix_oos)
    print(f"  A: n={oos_a['n_trades']} wr={oos_a['wr']*100:.0f}% total=${oos_a['total_pnl']:+.0f} "
          f"avg=${oos_a['avg_pnl']:+.0f}")
    print(f"     exits={oos_a['by_exit_reason']}")
    print(f"  B: n={oos_b['n_trades']} wr={oos_b['wr']*100:.0f}% total=${oos_b['total_pnl']:+.0f} "
          f"avg=${oos_b['avg_pnl']:+.0f}")
    print(f"     exits={oos_b['by_exit_reason']}")

    # ---- DSR/PSR advisory ----
    print("\n[3/3] DSR/PSR advisory (n_trials=2 — this single A/B)...")
    dsr_a = _dsr_gate(oos_a["pnls"], n_trials=2)
    dsr_b = _dsr_gate(oos_b["pnls"], n_trials=2)
    print(f"  A: {dsr_a.get('verdict')} (PSR={dsr_a.get('psr')}, DSR={dsr_a.get('dsr')}, n={dsr_a.get('n_obs')})")
    print(f"  B: {dsr_b.get('verdict')} (PSR={dsr_b.get('psr')}, DSR={dsr_b.get('dsr')}, n={dsr_b.get('n_obs')})")

    # ---- DECISION GATE ----
    edge_ok = edge_b["edge_capture"] >= edge_a["edge_capture"]

    # Anchor no-regression: per J-winner day B must stay >= 0 where A was >= 0;
    # per J-loser day B must not add a new loss where A had none.
    def _by_date(edge):
        return {r["date"]: r for r in edge["by_day"] if "error" not in r}
    a_days, b_days = _by_date(edge_a), _by_date(edge_b)
    anchor_ok = True
    anchor_detail = []
    for d, ar in a_days.items():
        br = b_days.get(d, {})
        a_pnl = ar.get("total_pnl", 0.0)
        b_pnl = br.get("total_pnl", 0.0)
        kind = ar.get("edge_kind")
        regressed = False
        if kind == "WIN" and a_pnl > 0 and b_pnl < a_pnl - 1.0:
            regressed = True  # B captured less of a J winner
        if kind == "LOSS" and a_pnl >= 0 and b_pnl < -1.0:
            regressed = True  # B added a loss A didn't have
        if regressed:
            anchor_ok = False
        anchor_detail.append({"date": d, "kind": kind, "a_pnl": a_pnl, "b_pnl": b_pnl, "regressed": regressed})

    # Material P&L band: B within 10% (or +$200 absolute floor) of A on OOS total.
    band = max(200.0, abs(oos_a["total_pnl"]) * 0.10)
    pnl_ok = oos_b["total_pnl"] >= oos_a["total_pnl"] - band

    ship = bool(edge_ok and anchor_ok and pnl_ok)

    print("\n" + "=" * 92)
    print("DECISION GATE")
    print(f"  edge_capture no-regression:  {'PASS' if edge_ok else 'FAIL'} "
          f"(B ${edge_b['edge_capture']:+.0f} vs A ${edge_a['edge_capture']:+.0f})")
    print(f"  anchor no-regression:        {'PASS' if anchor_ok else 'FAIL'}")
    print(f"  OOS P&L not materially worse: {'PASS' if pnl_ok else 'FAIL'} "
          f"(B ${oos_b['total_pnl']:+.0f} vs A ${oos_a['total_pnl']:+.0f}, band +/-${band:.0f})")
    print(f"\n  >>> {'SHIP B (chart-stop primary)' if ship else 'NO-SHIP — keep premium stops (config A)'} <<<")
    print("=" * 92)

    scorecard = {
        "task": "chart-stops-as-default A/B",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "config_a": {"label": "current live (-10% bear stop)", "premium_stop_pct_bear": cfg_a.get("premium_stop_pct_bear")},
        "config_b": {"label": "chart-stop primary (-50% catastrophe cap)", "premium_stop_pct_bear": B_BEAR_STOP},
        "oos_window": [OOS_START.isoformat(), OOS_END.isoformat()],
        "oos_window_note": "bounded by real OPRA option coverage (~through 2026-05-29)",
        "edge_capture": {"A": edge_a["edge_capture"], "B": edge_b["edge_capture"],
                         "A_detail": edge_a, "B_detail": edge_b},
        "oos": {"A": {k: v for k, v in oos_a.items() if k != "pnls"},
                "B": {k: v for k, v in oos_b.items() if k != "pnls"}},
        "dsr_advisory": {"A": dsr_a, "B": dsr_b},
        "gate": {"edge_ok": edge_ok, "anchor_ok": anchor_ok, "pnl_ok": pnl_ok,
                 "anchor_detail": anchor_detail, "pnl_band": band},
        "decision": "SHIP_B" if ship else "NO_SHIP",
    }
    out = REPO / "analysis" / "recommendations" / "chart-stops-ab-2026-06-18.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nScorecard: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
