"""Quick validate-window check — does the qty=22 LEVEL change over-risk?

Runs the v15-j-edge candidate against the 2026-02-14 to 2026-05-07 validate window
and reports total P&L, trade count, win rate, max drawdown. Compares against v14
baseline to verify the new orchestrator changes don't catastrophically over-risk.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import runner
from .j_edge_tracker import V15_J_EDGE_OVERRIDES

REPO = Path(__file__).resolve().parent.parent
VALIDATE_START = dt.date(2026, 2, 14)
VALIDATE_END = dt.date(2026, 5, 7)


def _summary(label: str, params: dict, spy, vix) -> dict:
    result, m = runner.run_with_params(params, VALIDATE_START, VALIDATE_END, spy, vix)
    pnls = [t.dollar_pnl for t in result.trades]
    n_trades = len(pnls)
    n_winners = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    avg = total / n_trades if n_trades else 0
    max_loss = min(pnls) if pnls else 0
    max_win = max(pnls) if pnls else 0
    print(f"\n{label}")
    print(f"  total_pnl: ${total:+,.0f}")
    print(f"  n_trades:  {n_trades}")
    print(f"  n_winners: {n_winners} ({n_winners/n_trades*100:.0f}% WR)" if n_trades else "  n_winners: 0")
    print(f"  avg_pnl:   ${avg:+,.0f}")
    print(f"  max_win:   ${max_win:+,.0f}")
    print(f"  max_loss:  ${max_loss:+,.0f}")
    return {
        "label": label,
        "total_pnl": total,
        "n_trades": n_trades,
        "n_winners": n_winners,
        "win_rate": n_winners / n_trades if n_trades else 0,
        "avg_pnl": avg,
        "max_loss": max_loss,
        "max_win": max_win,
    }


def main() -> int:
    spy, vix = runner.load_data(VALIDATE_START, VALIDATE_END)

    params_path = REPO.parent / "automation" / "state" / "params.json"
    base = json.loads(params_path.read_text(encoding="utf-8-sig"))

    print(f"Validate window: {VALIDATE_START} to {VALIDATE_END}")
    print(f"  bars loaded: {len(spy)} SPY, {len(vix)} VIX")

    # v14 baseline (production params, no overrides)
    v14_summary = _summary("v14 baseline (production params.json)", base, spy, vix)

    # v15-j-edge candidate (production + V15_J_EDGE_OVERRIDES)
    candidate = dict(base)
    candidate.update(V15_J_EDGE_OVERRIDES)
    cand_summary = _summary("v15-j-edge candidate (overrides applied)", candidate, spy, vix)

    print("\n=== v15-j-edge vs v14 ===")
    delta = cand_summary["total_pnl"] - v14_summary["total_pnl"]
    pct = (delta / abs(v14_summary["total_pnl"])) * 100 if v14_summary["total_pnl"] else 0
    print(f"  pnl delta: ${delta:+,.0f} ({pct:+.0f}%)")
    print(f"  trade delta: {cand_summary['n_trades'] - v14_summary['n_trades']:+d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
