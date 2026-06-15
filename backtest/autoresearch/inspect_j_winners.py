"""Per-trade inspection on J's winning days. Reveals which trades hit TP1 vs stopped out."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import runner
from .j_edge_tracker import V15_J_EDGE_OVERRIDES

REPO = Path(__file__).resolve().parent.parent

DAYS = ["2026-04-29", "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"]


def main() -> int:
    params_path = REPO.parent / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    min_d = dt.date.fromisoformat(min(DAYS))
    max_d = dt.date.fromisoformat(max(DAYS))
    spy, vix = runner.load_data(min_d, max_d)

    for date_str in DAYS:
        d = dt.date.fromisoformat(date_str)
        result, m = runner.run_with_params(params, d, d, spy, vix)
        print(f"\n=== {date_str} (engine_pnl=${m.total_pnl:+.0f}, n_trades={m.n_trades}) ===")
        for i, t in enumerate(result.trades):
            entry_t = t.entry_time_et
            entry_p = t.entry_premium
            tp1_t = t.tp1_time_et
            tp1_p = t.tp1_premium
            tp1_hit = tp1_t is not None
            runner_t = t.runner_exit_time_et
            runner_p = t.runner_exit_premium
            exit_reason = t.exit_reason
            pnl = t.dollar_pnl
            triggers = t.triggers_fired
            qty = t.qty
            tp1_str = (
                f"YES (at {tp1_t.strftime('%H:%M')} @ ${tp1_p:.2f})" if tp1_hit
                else f"NO (target was ${(tp1_p or 0):.2f})"
            )
            runner_str = (
                f"{runner_t.strftime('%H:%M')} @ ${(runner_p or 0):.2f}" if runner_t
                else "N/A"
            )
            print(f"  Trade {i+1}: entry={entry_t.strftime('%H:%M')} {t.side}{t.strike} "
                  f"qty={qty} @ ${entry_p:.2f}  pnl=${pnl:+.0f}  reason={exit_reason}")
            print(f"    triggers: {triggers}")
            print(f"    TP1 hit: {tp1_str}")
            print(f"    runner_exit: {runner_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
