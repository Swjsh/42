"""NLWB TP1 sweep — finds the TP1_PREMIUM_PCT that rescues the NLWB setup.

The base real-fills run (nlwb_full_real_fills.json) showed WR=47.8% at TP1=+30%.
Break-even WR for TP1=+30% is ~70% (loss avg $234 vs win avg $138).
At TP1=+100% break-even WR drops to ~41% — below actual 47.8% — theoretically rescuing P&L.

Key concern: 9/11 wins exit TP1_THEN_RUNNER_RIBBON (runner at breakeven).
If those winners don't reach TP1=+100%, raising TP1 turns marginal wins into losses.
This sweep answers that definitively by re-simulating all 23 completed trades.

Monkey-patching approach: lib.simulator_real imports TP1_PREMIUM_PCT from lib.simulator
at module load time. To vary it, we reassign `lib.simulator_real.TP1_PREMIUM_PCT`
before each batch run (the function reads the module-level name at call time).

Output: analysis/recommendations/nlwb_tp1_sweep.json
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

import lib.simulator_real as _sim_real  # noqa: E402  — must import BEFORE monkey-patching
from autoresearch import runner as ar_runner  # noqa: E402
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.simulator_real import simulate_trade_real, DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
IN_JSON  = ROOT / "analysis" / "recommendations" / "nlwb_full_real_fills.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "nlwb_tp1_sweep.json"

# ── Sweep values ──────────────────────────────────────────────────────────────
TP1_VALUES = [0.30, 0.50, 0.75, 1.00, 1.50, 2.00]

# ── Fixed simulation params (same as original nlwb_full_real_fills_validate.py) ──
START         = dt.date(2025, 1, 1)
END           = dt.date(2026, 5, 15)
QTY           = 3
PREMIUM_STOP  = -0.99   # chart-stop only per L55
STRIKE_OFFSET = 0       # ATM calls


def _load_completed_signals(path: Path) -> list[dict]:
    """Return only the COMPLETE signals from the stored JSON."""
    with open(path) as f:
        data = json.load(f)
    results = data.get("results", [])
    completed = [r for r in results if r.get("status") == "COMPLETE"]
    log.info("Loaded %d completed signals (of %d total)", len(completed), len(results))
    return completed


def _build_bar_index(rth: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Build (date_str, HH:MM) -> rth row index for fast lookup."""
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
) -> Optional[dict]:
    """Re-simulate a single signal. Returns result dict or None if bar not found."""
    key = (sig["date"], sig["time"])
    idx = bar_index.get(key)
    if idx is None:
        log.warning("Bar not found for %s %s", sig["date"], sig["time"])
        return None

    trigger_bar = rth.iloc[idx]
    rejection_level = float(sig["rejection_level"])

    fill = simulate_trade_real(
        entry_bar_idx=idx,
        entry_bar=trigger_bar,
        spy_df=rth,
        ribbon_df=ribbon_df,
        rejection_level=rejection_level,
        triggers_fired=["NLWB_SWEEP"],
        side="C",
        qty=QTY,
        setup="NLWB_TP1_SWEEP",
        entry_slippage=DEFAULT_ENTRY_SLIPPAGE,
        exit_slippage=DEFAULT_EXIT_SLIPPAGE,
        premium_stop_pct=PREMIUM_STOP,
        strike_offset=STRIKE_OFFSET,
        strike_override=int(sig["strike"]),  # pin strike so sweep is apples-to-apples
    )
    if fill is None:
        return None

    pnl = fill.dollar_pnl  # already computed by simulator (tp1 + runner split accounted for)
    exit_prem = fill.runner_exit_premium if fill.runner_exit_premium is not None else fill.entry_premium
    return {
        "date": sig["date"],
        "time": sig["time"],
        "vix_bucket": sig.get("vix_bucket", "?"),
        "entry_premium": round(fill.entry_premium, 4),
        "exit_premium": round(exit_prem, 4),
        "tp1_premium": round(fill.tp1_premium, 4) if fill.tp1_premium else None,
        "exit_reason": fill.exit_reason.name if hasattr(fill.exit_reason, "name") else str(fill.exit_reason),
        "dollar_pnl": round(pnl, 2),
        "outcome": "WIN" if pnl > 0 else "LOSS",
    }


def run_sweep() -> dict:
    log.info("Loading 16-month SPY data (%s to %s)...", START, END)
    spy_full, _ = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    ribbon_df = compute_ribbon(rth["close"])
    log.info("Ribbon computed.")

    bar_index = _build_bar_index(rth)
    log.info("Bar index built: %d entries", len(bar_index))

    completed_signals = _load_completed_signals(IN_JSON)

    sweep_results: list[dict] = []
    per_trade_detail: list[dict] = []

    for tp1_val in TP1_VALUES:
        # Monkey-patch the module-level TP1_PREMIUM_PCT used by simulate_trade_real
        _sim_real.TP1_PREMIUM_PCT = tp1_val
        log.info("--- TP1=%.2f ---", tp1_val)

        wins = 0
        losses = 0
        total_pnl = 0.0
        trade_detail: list[dict] = []

        for sig in completed_signals:
            result = _simulate_one(sig, rth, ribbon_df, bar_index)
            if result is None:
                log.warning("  Skipped: %s %s (bar not found or no OPRA)", sig["date"], sig["time"])
                continue

            if result["dollar_pnl"] > 0:
                wins += 1
            else:
                losses += 1
            total_pnl += result["dollar_pnl"]
            trade_detail.append({**result, "tp1_pct": tp1_val})
            log.info(
                "  %s %s  exit=%s  pnl=$%.0f",
                result["date"], result["time"], result["exit_reason"], result["dollar_pnl"]
            )

        n = wins + losses
        wr = wins / n if n > 0 else 0.0

        # Break-even WR for this TP1: loss_avg / (loss_avg + win_avg)
        win_pnls  = [r["dollar_pnl"] for r in trade_detail if r["dollar_pnl"] > 0]
        loss_pnls = [r["dollar_pnl"] for r in trade_detail if r["dollar_pnl"] <= 0]
        avg_win  = (sum(win_pnls)  / len(win_pnls))  if win_pnls  else 0.0
        avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        be_wr = abs(avg_loss) / (abs(avg_loss) + avg_win) if (avg_loss < 0 and avg_win > 0) else None

        verdict = "POSITIVE" if total_pnl > 0 else "NEGATIVE"

        row = {
            "tp1_pct": tp1_val,
            "n": n,
            "wins": wins,
            "losses": losses,
            "wr_pct": round(wr * 100, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "be_wr_pct": round(be_wr * 100, 1) if be_wr is not None else None,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / n, 2) if n > 0 else 0.0,
            "verdict": verdict,
        }
        sweep_results.append(row)
        per_trade_detail.extend(trade_detail)

        log.info(
            "  TP1=%+.0f%%: WR=%.1f%% (%dW/%dL)  total=$%.0f  be_wr=%.1f%%  %s",
            tp1_val * 100, wr * 100, wins, losses, total_pnl,
            be_wr * 100 if be_wr else 0.0, verdict,
        )

    # Find the optimal TP1
    positive_rows = [r for r in sweep_results if r["verdict"] == "POSITIVE"]
    if positive_rows:
        best = max(positive_rows, key=lambda r: r["total_pnl"])
        recommendation = f"TP1={best['tp1_pct']:.2f} (+{best['tp1_pct']*100:.0f}%): WR={best['wr_pct']}%, P&L=${best['total_pnl']:.0f}"
        rescue_found = True
    else:
        best = min(sweep_results, key=lambda r: abs(r["total_pnl"]))
        recommendation = f"No TP1 value rescues NLWB to positive. Best is TP1={best['tp1_pct']:.2f} with P&L=${best['total_pnl']:.0f}"
        rescue_found = False

    output = {
        "run_date": dt.date.today().isoformat(),
        "sweep_values": TP1_VALUES,
        "n_completed_signals": len(completed_signals),
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


def print_table(output: dict) -> None:
    print("\n╔══ NLWB TP1 SWEEP RESULTS ═══════════════════════════════════════════╗")
    print(f"{'TP1':>8}  {'WR%':>6}  {'Wins':>5}  {'Losses':>7}  {'AvgWin':>8}  {'AvgLoss':>9}  {'BE_WR%':>7}  {'Total$':>8}  {'Verdict':>8}")
    print("─" * 78)
    for row in output["summary_table"]:
        be = f"{row['be_wr_pct']:.1f}%" if row["be_wr_pct"] is not None else "  N/A"
        flag = " ◄ BEST" if row["tp1_pct"] == _get_best_tp1(output) else ""
        print(
            f"{row['tp1_pct']*100:>7.0f}%  {row['wr_pct']:>6.1f}  {row['wins']:>5}  "
            f"{row['losses']:>7}  {row['avg_win']:>8.2f}  {row['avg_loss']:>9.2f}  "
            f"{be:>7}  {row['total_pnl']:>8.2f}  {row['verdict']:>8}{flag}"
        )
    print("─" * 78)
    print(f"  RECOMMENDATION: {output['recommendation']}")
    print("╚══════════════════════════════════════════════════════════════════════╝\n")


def _get_best_tp1(output: dict) -> Optional[float]:
    positive = [r for r in output["summary_table"] if r["verdict"] == "POSITIVE"]
    if positive:
        return max(positive, key=lambda r: r["total_pnl"])["tp1_pct"]
    return None


if __name__ == "__main__":
    output = run_sweep()
    print_table(output)
    if output["rescue_found"]:
        print("ACTION: Update DEFAULT_TP1_PREMIUM_PCT in named_level_wick_bounce_watcher.py")
    else:
        print("ACTION: NLWB R:R mismatch is structural — consider tighter chart stop instead.")
