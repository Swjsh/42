"""NLWB chart-stop tightening sweep.

All 12 NLWB losses exit via EXIT_ALL_LEVEL_STOP. Tightening the chart stop
(making rejection_level closer to PDL) exits losers earlier (when SPY hasn't
fallen as far) → better exit price → smaller per-trade loss.

Risk: current winners exit via TP1/ribbon (NOT chart stop), so tightening
the stop should NOT convert any winners to losses — verified by watching WR
across the sweep.

Current: rejection_level = pdl - 0.30 → effective stop = pdl - 0.80
(LEVEL_STOP_BUFFER=0.50 hardcoded in simulator_real.py)

Chart-stop offsets to test (rejection_level = pdl - offset):
  -0.30 → effective pdl - 0.80  (current baseline)
  -0.10 → effective pdl - 0.60
   0.00 → effective pdl - 0.50  (stop when SPY closes AT pdl)
   0.20 → effective pdl - 0.30  (tight — SPY only 30c below PDL)
   0.40 → effective pdl - 0.10  (very tight — any close below PDL triggers)

Output: analysis/recommendations/nlwb_chart_stop_sweep.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

IN_JSON  = ROOT / "analysis" / "recommendations" / "nlwb_full_real_fills.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "nlwb_chart_stop_sweep.json"

START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)
QTY   = 3
PREMIUM_STOP = -0.99    # chart-stop only per L55
STRIKE_OFFSET = 0       # ATM calls

# Chart-stop offset from PDL — rejection_level = pdl - OFFSET
# LEVEL_STOP_BUFFER = 0.50 (hardcoded in simulator_real.py)
# effective stop = pdl - OFFSET - 0.50
CHART_STOP_OFFSETS = [0.30, 0.10, 0.00, -0.20, -0.40]


def _build_bar_index(rth: pd.DataFrame) -> dict[tuple[str, str], int]:
    idx_map: dict[tuple[str, str], int] = {}
    for pos, row in rth.iterrows():
        ts = row["timestamp_et"]
        if hasattr(ts, "tz_localize") and ts.tz is not None:
            ts = ts.tz_localize(None).to_pydatetime()
        else:
            ts = pd.Timestamp(ts).to_pydatetime()
        key = (ts.date().isoformat(), ts.strftime("%H:%M"))
        idx_map[key] = int(pos)
    return idx_map


def _simulate_one(
    sig: dict,
    rth: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    bar_index: dict[tuple[str, str], int],
    chart_stop_offset: float,
) -> Optional[dict]:
    key = (sig["date"], sig["time"])
    idx = bar_index.get(key)
    if idx is None:
        return None

    trigger_bar = rth.iloc[idx]
    pdl = float(sig["pdl"])
    rejection_level = round(pdl - chart_stop_offset, 4)  # effective stop = rejection_level - 0.50
    effective_stop = round(rejection_level - 0.50, 4)

    fill = simulate_trade_real(
        entry_bar_idx=idx,
        entry_bar=trigger_bar,
        spy_df=rth,
        ribbon_df=ribbon_df,
        rejection_level=rejection_level,
        triggers_fired=["NLWB_CS_SWEEP"],
        side="C",
        qty=QTY,
        setup="NLWB_CS_SWEEP",
        entry_slippage=DEFAULT_ENTRY_SLIPPAGE,
        exit_slippage=DEFAULT_EXIT_SLIPPAGE,
        premium_stop_pct=PREMIUM_STOP,
        strike_offset=STRIKE_OFFSET,
        strike_override=int(sig["strike"]),
    )
    if fill is None:
        return None

    pnl = fill.dollar_pnl
    exit_prem = fill.runner_exit_premium if fill.runner_exit_premium is not None else fill.entry_premium
    return {
        "date": sig["date"],
        "time": sig["time"],
        "vix_bucket": sig.get("vix_bucket", "?"),
        "pdl": pdl,
        "rejection_level": rejection_level,
        "effective_stop_from_pdl": round(pdl - effective_stop, 3),
        "entry_premium": round(fill.entry_premium, 4),
        "exit_premium": round(exit_prem, 4),
        "tp1_premium": round(fill.tp1_premium, 4) if fill.tp1_premium else None,
        "exit_reason": fill.exit_reason.name if hasattr(fill.exit_reason, "name") else str(fill.exit_reason),
        "dollar_pnl": round(pnl, 2),
        "outcome": "WIN" if pnl > 0 else "LOSS",
    }


def run_sweep() -> dict:
    log.info("Loading 16-month SPY data...")
    spy_full, _ = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    ribbon_df = compute_ribbon(rth["close"])
    bar_index = _build_bar_index(rth)
    log.info("Bar index: %d entries", len(bar_index))

    with open(IN_JSON) as f:
        data = json.load(f)
    completed = [r for r in data["results"] if r.get("status") == "COMPLETE"]
    log.info("Signals: %d completed", len(completed))

    sweep_results: list[dict] = []
    per_trade_detail: list[dict] = []

    for offset in CHART_STOP_OFFSETS:
        effective = offset + 0.50   # distance below PDL when stop fires
        log.info("--- chart_stop_offset=%.2f (effective pdl-%.2f) ---", offset, effective)

        wins = losses = 0
        total_pnl = 0.0
        trade_detail: list[dict] = []

        for sig in completed:
            r = _simulate_one(sig, rth, ribbon_df, bar_index, offset)
            if r is None:
                continue
            if r["dollar_pnl"] > 0:
                wins += 1
            else:
                losses += 1
            total_pnl += r["dollar_pnl"]
            trade_detail.append({**r, "chart_stop_offset": offset})
            log.info(
                "  %s %s  exit=%s  pnl=$%.0f",
                r["date"], r["time"], r["exit_reason"], r["dollar_pnl"]
            )

        n = wins + losses
        wr = wins / n if n > 0 else 0.0
        win_pnls  = [r["dollar_pnl"] for r in trade_detail if r["dollar_pnl"] > 0]
        loss_pnls = [r["dollar_pnl"] for r in trade_detail if r["dollar_pnl"] <= 0]
        avg_win  = sum(win_pnls)  / len(win_pnls)  if win_pnls  else 0.0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
        be_wr = abs(avg_loss) / (abs(avg_loss) + avg_win) if (avg_loss < 0 and avg_win > 0) else None

        row = {
            "chart_stop_offset": offset,
            "effective_stop_below_pdl": round(effective, 2),
            "n": n,
            "wins": wins,
            "losses": losses,
            "wr_pct": round(wr * 100, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "be_wr_pct": round(be_wr * 100, 1) if be_wr is not None else None,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / n, 2) if n > 0 else 0.0,
            "verdict": "POSITIVE" if total_pnl > 0 else "NEGATIVE",
        }
        sweep_results.append(row)
        per_trade_detail.extend(trade_detail)

        log.info(
            "  offset=%.2f (pdl-%.2f): WR=%.1f%% (%dW/%dL) total=$%.0f avg_loss=$%.0f %s",
            offset, effective, wr * 100, wins, losses, total_pnl, avg_loss,
            "POSITIVE" if total_pnl > 0 else "NEGATIVE",
        )

    positive_rows = [r for r in sweep_results if r["verdict"] == "POSITIVE"]
    rescue_found = bool(positive_rows)
    if positive_rows:
        best = max(positive_rows, key=lambda r: r["total_pnl"])
        recommendation = (
            f"chart_stop_offset={best['chart_stop_offset']:.2f} (effective pdl-{best['effective_stop_below_pdl']:.2f}): "
            f"WR={best['wr_pct']}%, P&L=${best['total_pnl']:.0f}"
        )
    else:
        best = max(sweep_results, key=lambda r: r["total_pnl"])
        recommendation = (
            f"No chart stop rescues NLWB. Best: offset={best['chart_stop_offset']:.2f} "
            f"(pdl-{best['effective_stop_below_pdl']:.2f}), P&L=${best['total_pnl']:.0f}"
        )

    output = {
        "run_date": dt.date.today().isoformat(),
        "sweep_offsets": CHART_STOP_OFFSETS,
        "n_completed_signals": len(completed),
        "rescue_found": rescue_found,
        "recommendation": recommendation,
        "summary_table": sweep_results,
        "per_trade_detail": per_trade_detail,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    log.info("Wrote %s", OUT_JSON)
    return output


if __name__ == "__main__":
    output = run_sweep()
    # Print results (ASCII only for Windows console compatibility)
    print()
    print("=== NLWB CHART-STOP SWEEP RESULTS ===")
    print(f"{'Offset':>8}  {'EffStop':>8}  {'WR%':>6}  {'W/L':>8}  {'AvgWin':>8}  {'AvgLoss':>9}  {'Total$':>10}  {'Verdict':>8}")
    print("-" * 80)
    for row in output["summary_table"]:
        flag = " <- BEST" if row["total_pnl"] == max(r["total_pnl"] for r in output["summary_table"]) else ""
        print(
            f"{row['chart_stop_offset']:>8.2f}  pdl-{row['effective_stop_below_pdl']:<4.2f}  "
            f"{row['wr_pct']:>6.1f}  {row['wins']:>3}/{row['losses']:<4}  "
            f"{row['avg_win']:>8.2f}  {row['avg_loss']:>9.2f}  "
            f"{row['total_pnl']:>10.2f}  {row['verdict']:>8}{flag}"
        )
    print()
    print("RECOMMENDATION:", output["recommendation"])
