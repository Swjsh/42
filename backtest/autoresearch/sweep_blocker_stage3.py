"""Stage-3 for BEARISH_SWEEP_BLOCKER candidate.

Measures the aggregate SPY Sharpe and P&L impact of enabling the sweep_blocker
gate over the full 16-month dataset (2025-01-01 ->2026-05-07).

Runs two passes:
  BASELINE  — standard production params (sweep_blocker_enabled=False)
  WITH_GATE — same params + sweep_blocker_enabled=True

Outputs:
  analysis/recommendations/sweep-blocker-stage3.json  — machine-readable scorecard
  analysis/recommendations/sweep-blocker-stage3.md    — human-readable report

Reports:
  1. Aggregate metrics: P&L, Sharpe, WR, trades/day, max-drawdown
  2. Delta (WITH_GATE minus BASELINE) for every metric
  3. Blocked trades log (date, time, level, direction, estimated reason)
  4. J-edge check: verifies all 7 source-of-truth days unaffected
  5. Threshold sensitivity: re-runs with min_wick_pct ∈ {0.0002, 0.0003, 0.0005}

Usage:
  python backtest/autoresearch/sweep_blocker_stage3.py
  python backtest/autoresearch/sweep_blocker_stage3.py --quick   # skip sensitivity sweep
"""

from __future__ import annotations

# ── OP-27 L41: self-redirect I/O when running under pythonw.exe (GUI subsystem).
# Prevents stdout-pipe deadlock when parent PS session times out before the
# ~30-minute run completes. The process owns these file handles; parent dying
# has no effect. See LESSONS-LEARNED.md L41 + sweep3-v2 post-mortem 2026-05-21.
import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "sweep-blocker-stage3.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "sweep-blocker-stage3.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[sweep-blocker-stage3] stdout redirected to log file (pid={_os.getpid()})")

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest  # noqa: E402

DATA_DIR = REPO / "data"
OUT_DIR = ROOT / "analysis" / "recommendations"
OUT_JSON = OUT_DIR / "sweep-blocker-stage3.json"
OUT_MD = OUT_DIR / "sweep-blocker-stage3.md"

# --- Production knobs (v15.2 params from params.json / heartbeat.md) --------
# Mirroring the standard run_backtest() defaults used in production validation.
PROD_KWARGS: dict = dict(
    premium_stop_pct_bear=-0.20,      # v15 asymmetric: -20% bear stop
    premium_stop_pct_bull=-0.08,      # v15 asymmetric: -8% bull stop
    tp1_premium_pct=0.75,             # v15 TP1 at +75%
    tp1_qty_fraction=0.50,            # v15 sell half at TP1
    runner_target_premium_pct=2.5,    # v15 runner at 2.5×
    profit_lock_threshold_pct=0.05,   # v15 chandelier arms at +5%
    profit_lock_stop_offset_pct=0.0,  # floor to entry (no negative trade)
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,       # 20% off HWM chandelier
    use_real_fills=True,
    min_triggers_bear=1,
    min_triggers_bull=2,
    strike_offset_bear=-3,            # OTM-3 at $1K tier (Stage-3 uses $1K-tier to match paper account)
    strike_offset_bull=-3,
    f9_vol_mult=0.7,
    enable_bullish=True,
)

# J source-of-truth days: winners the engine MUST take, losers it MUST skip/lose-less
J_WINNERS = [
    dt.date(2026, 4, 29),
    dt.date(2026, 5, 1),
    dt.date(2026, 5, 4),
]
J_LOSERS = [
    dt.date(2026, 5, 5),
    dt.date(2026, 5, 6),
    dt.date(2026, 5, 7),
]
J_ALL = J_WINNERS + J_LOSERS

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 7)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # noqa: F841


def _load_data(start: dt.date, end: dt.date):
    """Load SPY + VIX 5m CSVs for [start, end]. Mirrors run.py logic."""
    candidates = [
        ("2025-01-01", "2026-05-07"),
        ("2025-01-01", "2026-05-12"),
        ("2025-01-01", "2026-05-15"),
        ("2025-01-01", "2026-05-19_merged"),
    ]
    for cs, ce in candidates:
        sp = DATA_DIR / f"spy_5m_{cs}_{ce}.csv"
        vp = DATA_DIR / f"vix_5m_{cs}_{ce}.csv"
        # Check vix file without _merged suffix too
        if not vp.exists():
            ce_base = ce.replace("_merged", "")
            vp = DATA_DIR / f"vix_5m_{cs}_{ce_base}.csv"
        if sp.exists() and vp.exists():
            spy = pd.read_csv(sp)
            vix = pd.read_csv(vp)
            start_str = start.isoformat()
            end_str = f"{end.isoformat()}T23:59:59"
            spy = spy[(spy["timestamp_et"] >= start_str) & (spy["timestamp_et"] < end_str)].reset_index(drop=True)
            vix = vix[(vix["timestamp_et"] >= start_str) & (vix["timestamp_et"] < end_str)].reset_index(drop=True)
            print(f"  Loaded: {sp.name} ->SPY {len(spy):,} bars, VIX {len(vix):,} bars")
            return spy, vix
    raise FileNotFoundError(
        f"No SPY/VIX CSV covering {start}..{end} in {DATA_DIR}. "
        "Run: python tools/fetch_data.py --start 2025-01-01 --end 2026-05-07"
    )


def _sharpe(pnls: list[float]) -> float:
    """Annualized Sharpe from per-trade P&L series. Uses 252 trading-days proxy."""
    if len(pnls) < 2:
        return float("nan")
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    if var <= 0:
        return float("nan")
    return (mean / math.sqrt(var)) * math.sqrt(252)


def _max_drawdown(pnls: list[float]) -> float:
    """Peak-to-trough drawdown (sequential cumulative). Returns a negative number."""
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def _metrics(trades, decisions) -> dict:
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "n_winners": 0, "n_losers": 0,
            "total_pnl": 0.0, "avg_pnl": 0.0,
            "win_rate": 0.0, "sharpe": float("nan"),
            "max_drawdown": 0.0, "avg_hold_min": 0.0,
            "trades_per_day": 0.0,
        }
    n_days = len(set(
        pd.Timestamp(d["timestamp_et"]).date() for d in decisions
    ))
    pnls = [t.dollar_pnl for t in trades]
    n_w = sum(1 for p in pnls if p > 0)
    n_l = sum(1 for p in pnls if p < 0)
    total = sum(pnls)
    return {
        "n_trades": n,
        "n_winners": n_w,
        "n_losers": n_l,
        "total_pnl": round(total, 2),
        "avg_pnl": round(total / n, 2),
        "win_rate": round(n_w / n, 4),
        "sharpe": round(_sharpe(pnls), 4),
        "max_drawdown": round(_max_drawdown(pnls), 2),
        "avg_hold_min": round(sum(t.hold_minutes for t in trades) / n, 1),
        "trades_per_day": round(n / max(1, n_days), 3),
    }


def _j_edge_check(trades, label: str) -> dict:
    """Report P&L on each of the 7 J source-of-truth days."""
    by_date: dict[dt.date, list] = {}
    for t in trades:
        d = t.entry_time_et.date()
        by_date.setdefault(d, []).append(t.dollar_pnl)
    result = {}
    for d in J_ALL:
        pnls_on_day = by_date.get(d, [])
        result[d.isoformat()] = {
            "category": "WINNER" if d in J_WINNERS else "LOSER",
            "engine_pnl": round(sum(pnls_on_day), 2),
            "n_trades": len(pnls_on_day),
        }
    return result


def _blocked_trades(baseline_trades, gate_trades) -> list[dict]:
    """Find trades present in baseline but absent in gate run (blocked by sweep)."""
    gate_keys = {(t.entry_time_et.date(), t.entry_time_et.time()): True for t in gate_trades}
    blocked = []
    for t in baseline_trades:
        key = (t.entry_time_et.date(), t.entry_time_et.time())
        if key not in gate_keys:
            blocked.append({
                "date": t.entry_time_et.date().isoformat(),
                "time": t.entry_time_et.strftime("%H:%M"),
                "direction": "P" if hasattr(t, "side") and t.side == "P" else
                             ("P" if "BEARISH" in (t.setup or "") else "C"),
                "pnl_blocked": round(t.dollar_pnl, 2),
                "triggers": getattr(t, "triggers_fired", []),
                "rejection_level": getattr(t, "rejection_level", None),
            })
    blocked.sort(key=lambda x: (x["date"], x["time"]))
    return blocked


def run_one(spy, vix, sweep_enabled: bool, wick_pct: float = 0.0003,
            close_back_pct: float = 0.0005) -> tuple:
    """Run backtest with or without sweep_blocker. Returns (result, metrics)."""
    result = run_backtest(
        spy, vix,
        start_date=START,
        end_date=END,
        sweep_blocker_enabled=sweep_enabled,
        sweep_min_wick_pct=wick_pct,
        sweep_min_close_back_pct=close_back_pct,
        **PROD_KWARGS,
    )
    m = _metrics(result.trades, result.decisions)
    return result, m


def main() -> int:
    ap = argparse.ArgumentParser(description="BEARISH_SWEEP_BLOCKER Stage-3 comparison")
    ap.add_argument("--quick", action="store_true",
                    help="Skip threshold sensitivity sweep (only run baseline + default gate)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("BEARISH_SWEEP_BLOCKER — Stage-3 Aggregate Sharpe Measurement")
    print(f"Window: {START} to {END}")
    print("=" * 70)

    print("\nLoading data...")
    spy, vix = _load_data(START, END)

    # ── Pass 1: Baseline ─────────────────────────────────────────────────────
    print("\nRunning BASELINE (sweep_blocker_enabled=False)...")
    base_result, base_m = run_one(spy, vix, sweep_enabled=False)
    print(f"  ->{base_m['n_trades']} trades  P&L=${base_m['total_pnl']:+.0f}  "
          f"WR={base_m['win_rate']*100:.0f}%  Sharpe={base_m['sharpe']:.3f}")

    # ── Pass 2: With sweep gate (default thresholds) ─────────────────────────
    print("\nRunning WITH_GATE (sweep_blocker_enabled=True, wick=0.03%, close=0.05%)...")
    gate_result, gate_m = run_one(spy, vix, sweep_enabled=True,
                                  wick_pct=0.0003, close_back_pct=0.0005)
    print(f"  ->{gate_m['n_trades']} trades  P&L=${gate_m['total_pnl']:+.0f}  "
          f"WR={gate_m['win_rate']*100:.0f}%  Sharpe={gate_m['sharpe']:.3f}")

    # ── Delta ─────────────────────────────────────────────────────────────────
    delta = {
        "n_trades": gate_m["n_trades"] - base_m["n_trades"],
        "total_pnl": round(gate_m["total_pnl"] - base_m["total_pnl"], 2),
        "win_rate": round(gate_m["win_rate"] - base_m["win_rate"], 4),
        "sharpe": round(gate_m["sharpe"] - base_m["sharpe"], 4),
        "max_drawdown": round(gate_m["max_drawdown"] - base_m["max_drawdown"], 2),
        "trades_per_day": round(gate_m["trades_per_day"] - base_m["trades_per_day"], 3),
    }
    print(f"\nDELTA: trades={delta['n_trades']:+d}  "
          f"P&L=${delta['total_pnl']:+.0f}  "
          f"WR={delta['win_rate']*100:+.1f}pp  "
          f"Sharpe={delta['sharpe']:+.3f}  "
          f"MaxDD=${delta['max_drawdown']:+.0f}")

    # ── Blocked trades ────────────────────────────────────────────────────────
    blocked = _blocked_trades(base_result.trades, gate_result.trades)
    print(f"\nBlocked trades: {len(blocked)}")
    blocked_pnl = sum(b["pnl_blocked"] for b in blocked)
    print(f"  Aggregate P&L of blocked trades: ${blocked_pnl:+.0f}")
    for b in blocked[:10]:  # show first 10
        print(f"  {b['date']} {b['time']}  {b['direction']}  "
              f"level={b['rejection_level']}  P&L=${b['pnl_blocked']:+.0f}  "
              f"triggers={b['triggers']}")
    if len(blocked) > 10:
        print(f"  ... +{len(blocked)-10} more (see JSON)")

    # ── J-edge check ─────────────────────────────────────────────────────────
    base_edge = _j_edge_check(base_result.trades, "baseline")
    gate_edge = _j_edge_check(gate_result.trades, "gate")

    print("\nJ source-of-truth day check:")
    edge_capture_base = 0
    edge_capture_gate = 0
    for day_str, info in base_edge.items():
        gate_day = gate_edge.get(day_str, {})
        base_pnl = info["engine_pnl"]
        gate_pnl = gate_day.get("engine_pnl", 0.0)
        delta_day = gate_pnl - base_pnl
        flag = "  PASS" if abs(delta_day) < 0.01 else f"  *** DELTA ${delta_day:+.0f}"
        if info["category"] == "WINNER":
            edge_capture_base += max(0, base_pnl)
            edge_capture_gate += max(0, gate_pnl)
        print(f"  {day_str} [{info['category']}]  "
              f"base=${base_pnl:+.0f}  gate=${gate_pnl:+.0f}{flag}")

    edge_delta = edge_capture_gate - edge_capture_base
    print(f"\nEdge capture: baseline={edge_capture_base:.0f}  "
          f"gate={edge_capture_gate:.0f}  delta={edge_delta:+.0f}")
    edge_ok = edge_capture_gate >= 771  # OP-16 50% of 1542 max floor

    # ── Threshold sensitivity (unless --quick) ────────────────────────────────
    sensitivity: list[dict] = []
    if not args.quick:
        print("\nThreshold sensitivity sweep (wick_pct × close_back_pct)...")
        for wp in [0.0002, 0.0003, 0.0005]:
            for cp in [0.0003, 0.0005, 0.001]:
                label = f"wick={wp*100:.3f}% close={cp*100:.3f}%"
                r, m = run_one(spy, vix, sweep_enabled=True, wick_pct=wp, close_back_pct=cp)
                n_bl = len(_blocked_trades(base_result.trades, r.trades))
                sensitivity.append({
                    "wick_pct": wp, "close_back_pct": cp,
                    "n_trades": m["n_trades"], "total_pnl": m["total_pnl"],
                    "win_rate": m["win_rate"], "sharpe": m["sharpe"],
                    "n_blocked": n_bl,
                })
                print(f"  {label}  ->trades={m['n_trades']}  "
                      f"P&L=${m['total_pnl']:+.0f}  "
                      f"Sharpe={m['sharpe']:.3f}  blocked={n_bl}")

    # ── Scorecard ─────────────────────────────────────────────────────────────
    sharpe_improved = delta["sharpe"] > 0
    pnl_not_regressed = delta["total_pnl"] >= -200  # allow up to $200 regression
    edge_preserved = edge_ok and abs(edge_delta) < 100  # winners unaffected

    gate_recommendation = "APPROVE" if (sharpe_improved and pnl_not_regressed and edge_preserved) \
        else ("CONDITIONAL" if (pnl_not_regressed and edge_preserved) else "REJECT")

    scorecard = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "window": {"start": START.isoformat(), "end": END.isoformat()},
        "baseline": base_m,
        "with_gate": gate_m,
        "delta": delta,
        "blocked_trades": blocked,
        "j_edge": {
            "baseline": base_edge,
            "gate": gate_edge,
            "edge_capture_baseline": edge_capture_base,
            "edge_capture_gate": edge_capture_gate,
            "edge_capture_delta": edge_delta,
            "op16_floor_pass": edge_ok,
        },
        "sensitivity": sensitivity,
        "verdict": {
            "sharpe_improved": sharpe_improved,
            "pnl_not_regressed": pnl_not_regressed,
            "edge_preserved": edge_preserved,
            "recommendation": gate_recommendation,
        },
        "stage3_complete": True,
    }

    OUT_JSON.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    print(f"\nScorecard written ->{OUT_JSON}")

    # ── Markdown report ───────────────────────────────────────────────────────
    md_lines = [
        "# BEARISH_SWEEP_BLOCKER — Stage-3 Aggregate Sharpe Report",
        "",
        f"_Generated: {scorecard['generated_at']}_",
        f"_Window: {START} ->{END} (16 months)_",
        "",
        "## Verdict",
        "",
        f"**Recommendation: {gate_recommendation}**",
        "",
        f"- Sharpe improved: {'PASS' if sharpe_improved else 'FAIL'} "
        f"(Δ{delta['sharpe']:+.3f})",
        f"- P&L not regressed: {'PASS' if pnl_not_regressed else 'FAIL'} "
        f"(Δ${delta['total_pnl']:+.0f})",
        f"- J-edge preserved: {'PASS' if edge_preserved else 'FAIL'} "
        f"(edge_capture Δ{edge_delta:+.0f})",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Baseline | With Gate | Delta |",
        "|---|---:|---:|---:|",
        f"| Trades | {base_m['n_trades']} | {gate_m['n_trades']} | {delta['n_trades']:+d} |",
        f"| Total P&L | ${base_m['total_pnl']:+.0f} | ${gate_m['total_pnl']:+.0f} | ${delta['total_pnl']:+.0f} |",
        f"| Win Rate | {base_m['win_rate']*100:.1f}% | {gate_m['win_rate']*100:.1f}% | {delta['win_rate']*100:+.1f}pp |",
        f"| Sharpe | {base_m['sharpe']:.3f} | {gate_m['sharpe']:.3f} | {delta['sharpe']:+.3f} |",
        f"| Max Drawdown | ${base_m['max_drawdown']:.0f} | ${gate_m['max_drawdown']:.0f} | ${delta['max_drawdown']:+.0f} |",
        f"| Trades/Day | {base_m['trades_per_day']:.3f} | {gate_m['trades_per_day']:.3f} | {delta['trades_per_day']:+.3f} |",
        "",
        "## Blocked Trades Analysis",
        "",
        f"**{len(blocked)} trades blocked by sweep_blocker**  "
        f"(aggregate P&L of blocked trades: ${blocked_pnl:+.0f})",
        "",
        "| Date | Time | Dir | Level | P&L blocked | Triggers |",
        "|---|---|---|---|---:|---|",
    ]
    for b in blocked:
        md_lines.append(
            f"| {b['date']} | {b['time']} | {b['direction']} | "
            f"{b['rejection_level'] or '?'} | ${b['pnl_blocked']:+.0f} | "
            f"{', '.join(b['triggers'])} |"
        )
    md_lines += [
        "",
        "## J Source-of-Truth Day Check",
        "",
        "| Date | Category | Baseline | With Gate | Delta |",
        "|---|---|---:|---:|---:|",
    ]
    for day_str, info in base_edge.items():
        gate_day = gate_edge.get(day_str, {})
        g_pnl = gate_day.get("engine_pnl", 0.0)
        b_pnl = info["engine_pnl"]
        dd = g_pnl - b_pnl
        md_lines.append(
            f"| {day_str} | {info['category']} | ${b_pnl:+.0f} | ${g_pnl:+.0f} | ${dd:+.0f} |"
        )

    if sensitivity:
        md_lines += [
            "",
            "## Threshold Sensitivity",
            "",
            "| wick_pct | close_back_pct | Trades | P&L | Sharpe | Blocked |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for s in sensitivity:
            md_lines.append(
                f"| {s['wick_pct']*100:.3f}% | {s['close_back_pct']*100:.3f}% | "
                f"{s['n_trades']} | ${s['total_pnl']:+.0f} | {s['sharpe']:.3f} | {s['n_blocked']} |"
            )

    md_lines += [
        "",
        "---",
        "",
        f"_Stage-3 script: `backtest/autoresearch/sweep_blocker_stage3.py`_",
        f"_Candidate: `strategy/candidates/2026-05-16-bearish-sweep-blocker.md`_",
        f"_Primitive: `crypto/lib/sweep.py` + `backtest/lib/filters.py` `_detect_sweep_at_level()`_",
    ]

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Markdown report ->{OUT_MD}")

    print(f"\n{'='*70}")
    print(f"FINAL: {gate_recommendation}")
    print(f"  Sharpe: {base_m['sharpe']:.3f} -> {gate_m['sharpe']:.3f} ({delta['sharpe']:+.3f})")
    print(f"  P&L:    ${base_m['total_pnl']:+.0f} -> ${gate_m['total_pnl']:+.0f} (${delta['total_pnl']:+.0f})")
    print(f"  Edge capture: {edge_capture_gate:.0f} ({'+' if edge_preserved else 'DEGRADED'})")
    print(f"  Blocked: {len(blocked)} trades (${blocked_pnl:+.0f} aggregate)")
    print(f"{'='*70}")
    return 0 if gate_recommendation != "REJECT" else 1


if __name__ == "__main__":
    sys.exit(main())
