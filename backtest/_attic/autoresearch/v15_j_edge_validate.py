"""Full validate-window backtest comparing v14 (ITM-2) vs v15-J-edge (OTM-2)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import runner

REPO = Path(__file__).resolve().parent.parent
PARAMS_BASE = json.loads((REPO.parent / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))


def run(label: str, params: dict, start: dt.date, end: dt.date) -> None:
    spy, vix = runner.load_data(start, end)
    _, m = runner.run_with_params(params, start, end, spy, vix)
    print(f"  {label:<22} pnl=${m.total_pnl:+8.0f} sh={m.sharpe_daily:+5.2f} n={m.n_trades:3d} wr={m.win_rate*100:5.1f}% wlr={m.wl_ratio:5.2f}x avg_w=${m.avg_winner:+6.0f} avg_l=${m.avg_loser:+6.0f}")


def main() -> int:
    train_start = dt.date(2025, 1, 1)
    train_end   = dt.date(2026, 2, 13)
    val_start   = dt.date(2026, 2, 14)
    val_end     = dt.date(2026, 5, 7)

    v14 = dict(PARAMS_BASE)
    v14_je = dict(PARAMS_BASE)
    v14_je["strike_offset_bear"] = 2
    v14_je["strike_offset_bull"] = 2
    v14_je.pop("strike_offset_itm", None)

    print(f"{'='*100}")
    print("VALIDATE WINDOW (Feb 14 - May 7 2026)")
    print(f"{'='*100}")
    run("v14 (ITM-2)", v14, val_start, val_end)
    run("v14 + OTM-2 strike", v14_je, val_start, val_end)
    print()
    print(f"{'='*100}")
    print("TRAIN WINDOW (Jan 1 2025 - Feb 13 2026)")
    print(f"{'='*100}")
    run("v14 (ITM-2)", v14, train_start, train_end)
    run("v14 + OTM-2 strike", v14_je, train_start, train_end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
