"""Gate threshold relaxation sweep — Category A (pure score) + Category G (VIX regime).

Tests the effect of lowering the bear/bull entry score threshold below the
production 10/10 (all-pass) baseline. Implements score-based relaxation by
monkey-patching evaluate_bearish_setup / evaluate_bullish_setup before
calling run_backtest.

FAST MODE: scenarios run on J-days only (6 days) for edge_capture ranking.
           Full-window Sharpe computed only for top OP-16-passing candidates.

Output: analysis/recommendations/gate_sweep_threshold.json

J edge reference (OP-16 immutable):
  Winners: 4/29 +342 | 5/01 +470 | 5/04 +730
  Losers:  5/05 -260 | 5/06 -300 | 5/07 -165
  Max edge: 1542. Floor: 771 (50%).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

import lib.filters as _filters_mod
import lib.orchestrator as _orchestrator_mod
from lib.filters import evaluate_bearish_setup as _orig_bear
from lib.filters import evaluate_bullish_setup as _orig_bull
from lib.filters import SetupResult, BullishSetupResult, BarContext
from lib.orchestrator import run_backtest

# ─────────────────────────────────────────────────────────────────
# Production baseline kwargs (v15.3 params per task spec)
# ─────────────────────────────────────────────────────────────────
BASE_KWARGS: dict = dict(
    use_real_fills=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    strike_offset=0,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    f9_vol_mult=0.7,
)

# ─────────────────────────────────────────────────────────────────
# J edge source of truth (OP-16)
# ─────────────────────────────────────────────────────────────────
J_WINNERS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS  = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
OP16_FLOOR = 771
MAX_EDGE = 1542
ALL_J_DAYS = list(J_WINNERS) + list(J_LOSERS)

# ─────────────────────────────────────────────────────────────────
# Data paths
# ─────────────────────────────────────────────────────────────────
DATA_DIR = REPO / "backtest" / "data"
SPY_PATH = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_PATH = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

# ─────────────────────────────────────────────────────────────────
# Patch factories
# ─────────────────────────────────────────────────────────────────
STRUCTURAL_REQUIRED = {1, 2, 3, 4, 5}


def _make_bear_patch(min_score: int,
                     vix_min: Optional[float] = None,
                     vix_max: Optional[float] = None,
                     vix_delta_min: Optional[float] = None):
    """Return a patched evaluate_bearish_setup that gates on bear_score >= min_score.

    Structural filters {1,2,3,4,5} are still enforced — they cannot be relaxed.
    VIX conditions are additional gates (not relaxations).
    """
    def patched(*args, **kwargs):
        result: SetupResult = _orig_bear(*args, **kwargs)
        if result.passed:
            return result  # Already passes strict gate
        # Structural check — cannot bypass
        if any(b in STRUCTURAL_REQUIRED for b in result.blockers):
            return result
        # Score gate
        if result.bear_score < min_score:
            return result
        # Must have at least 1 trigger (filter 10)
        if not result.triggers_fired:
            return result
        # VIX regime conditions
        ctx: BarContext = args[0]
        if vix_min is not None and ctx.vix_now <= vix_min:
            return result
        if vix_max is not None and ctx.vix_now >= vix_max:
            return result
        if vix_delta_min is not None and (ctx.vix_now - ctx.vix_prior) < vix_delta_min:
            return result
        # All gates met — override passed=True
        return SetupResult(
            passed=True,
            bear_score=result.bear_score,
            blockers=result.blockers,
            triggers_fired=result.triggers_fired,
            rejection_level=result.rejection_level,
            ribbon_just_flipped_bearish=result.ribbon_just_flipped_bearish,
            confluence_match=result.confluence_match,
        )
    return patched


def _make_bull_patch(min_score: int, vix_max: Optional[float] = None):
    """Return a patched evaluate_bullish_setup that gates on bull_score >= min_score."""
    def patched(*args, **kwargs):
        result: BullishSetupResult = _orig_bull(*args, **kwargs)
        if result.passed:
            return result
        if any(b in STRUCTURAL_REQUIRED for b in result.blockers):
            return result
        if result.bull_score < min_score:
            return result
        if not result.triggers_fired:
            return result
        ctx: BarContext = args[0]
        if vix_max is not None and ctx.vix_now >= vix_max:
            return result
        return BullishSetupResult(
            passed=True,
            bull_score=result.bull_score,
            blockers=result.blockers,
            triggers_fired=result.triggers_fired,
            reclaim_level=result.reclaim_level,
            ribbon_just_flipped_bullish=result.ribbon_just_flipped_bullish,
            confluence_match=result.confluence_match,
        )
    return patched


# ─────────────────────────────────────────────────────────────────
# Run helpers
# ─────────────────────────────────────────────────────────────────

def _apply_patches(bear_patch, bull_patch):
    """Apply patches to both the filters module AND orchestrator module namespaces."""
    if bear_patch is not None:
        _filters_mod.evaluate_bearish_setup = bear_patch
        _orchestrator_mod.evaluate_bearish_setup = bear_patch
    if bull_patch is not None:
        _filters_mod.evaluate_bullish_setup = bull_patch
        _orchestrator_mod.evaluate_bullish_setup = bull_patch


def _restore_patches():
    """Restore original functions in both namespaces."""
    _filters_mod.evaluate_bearish_setup = _orig_bear
    _orchestrator_mod.evaluate_bearish_setup = _orig_bear
    _filters_mod.evaluate_bullish_setup = _orig_bull
    _orchestrator_mod.evaluate_bullish_setup = _orig_bull


def _run_day(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
             date_str: str, bear_patch=None, bull_patch=None) -> list:
    """Run backtest on a single day. Returns trades list."""
    d = dt.date.fromisoformat(date_str)
    # Include full history up to EOD for ribbon warmup
    spy_w = spy_df[spy_df["_date"] <= date_str].copy()
    vix_w = vix_df[vix_df["_date"] <= date_str].copy()

    _apply_patches(bear_patch, bull_patch)
    try:
        res = run_backtest(
            spy_df=spy_w, vix_df=vix_w,
            start_date=d, end_date=d,
            **BASE_KWARGS,
        )
    finally:
        _restore_patches()

    return res.trades


def _run_j_days(spy_df, vix_df, bear_patch=None, bull_patch=None) -> dict:
    """Run all 6 J days. Returns per-day P&L, trade count, and win count dicts."""
    daily_pnl: dict[str, float] = {}
    daily_n: dict[str, int] = {}
    daily_wins: dict[str, int] = {}
    for date_str in ALL_J_DAYS:
        trades = _run_day(spy_df, vix_df, date_str, bear_patch, bull_patch)
        if trades:
            daily_pnl[date_str] = round(sum(t.dollar_pnl for t in trades), 2)
            daily_n[date_str] = len(trades)
            daily_wins[date_str] = sum(1 for t in trades if t.dollar_pnl > 0)
        else:
            daily_n[date_str] = 0
            daily_wins[date_str] = 0
    return {"pnl": daily_pnl, "n": daily_n, "wins": daily_wins}


def _run_full_window(spy_df, vix_df,
                     start=dt.date(2025, 1, 2), end=dt.date(2026, 6, 16),
                     bear_patch=None, bull_patch=None) -> dict:
    """Run backtest on the full window. Returns aggregate metrics."""
    _apply_patches(bear_patch, bull_patch)
    try:
        res = run_backtest(
            spy_df=spy_df, vix_df=vix_df,
            start_date=start, end_date=end,
            **BASE_KWARGS,
        )
    finally:
        _restore_patches()

    trades = res.trades
    if not trades:
        return {"n": 0, "wr": 0.0, "pnl": 0.0, "sharpe": 0.0, "daily_pnl": {}}

    daily_pnl: dict[str, float] = {}
    for t in trades:
        et = getattr(t, "entry_time_et", None) or getattr(t, "entry_time", None)
        if et is None:
            continue
        day = str(et.date())
        daily_pnl[day] = daily_pnl.get(day, 0.0) + t.dollar_pnl

    trading_days = pd.bdate_range(start=start, end=end)
    all_daily = [daily_pnl.get(str(d.date()), 0.0) for d in trading_days]
    arr = pd.Series(all_daily, dtype=float)
    sharpe = 0.0
    if arr.std() > 0 and len(arr) >= 5:
        sharpe = round(float(arr.mean() / arr.std() * (252 ** 0.5)), 3)

    n = len(trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    return {
        "n": n,
        "wr": round(wins / n, 4),
        "pnl": round(sum(t.dollar_pnl for t in trades), 2),
        "sharpe": sharpe,
        "daily_pnl": daily_pnl,
    }


def _calc_edge(daily_pnl: dict) -> float:
    winner_contrib = sum(daily_pnl.get(d, 0.0) for d in J_WINNERS)
    loser_exposure = sum(max(0.0, -daily_pnl.get(d, 0.0)) for d in J_LOSERS)
    return round(winner_contrib - loser_exposure, 2)


def _verdict(marginal_wr: float, marginal_pnl: float, edge_capture: float) -> str:
    if marginal_pnl < 0:
        return "REJECT"
    if edge_capture >= OP16_FLOOR and marginal_wr >= 0.45 and marginal_pnl > 0:
        return "PROMOTE"
    return "VALIDATE"


# ─────────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    # ── Category A: pure score threshold ──────────────────────────────────
    {"id": "A1", "name": "1-Miss Bear",           "gate": "bear_score>=9",
     "bp": _make_bear_patch(9), "cp": None},
    {"id": "A2", "name": "2-Miss Bear",           "gate": "bear_score>=8",
     "bp": _make_bear_patch(8), "cp": None},
    {"id": "A3", "name": "3-Miss Bear",           "gate": "bear_score>=7",
     "bp": _make_bear_patch(7), "cp": None},
    {"id": "A4", "name": "1-Miss Bull",           "gate": "bull_score>=10",
     "bp": None, "cp": _make_bull_patch(10)},
    {"id": "A5", "name": "2-Miss Bull",           "gate": "bull_score>=9",
     "bp": None, "cp": _make_bull_patch(9)},
    # ── Category G: VIX regime specific ───────────────────────────────────
    {"id": "G1", "name": "2-Miss Bear + VIX>22",  "gate": "bear_score>=8 AND vix>22",
     "bp": _make_bear_patch(8, vix_min=22.0), "cp": None},
    {"id": "G2", "name": "3-Miss Bear + VIX>25",  "gate": "bear_score>=7 AND vix>25",
     "bp": _make_bear_patch(7, vix_min=25.0), "cp": None},
    {"id": "G3", "name": "1-Miss Bear + 17<VIX<21", "gate": "bear_score>=9 AND 17<vix<21",
     "bp": _make_bear_patch(9, vix_min=17.0, vix_max=21.0), "cp": None},
    {"id": "G4", "name": "2-Miss Bull + VIX<14",  "gate": "bull_score>=9 AND vix<14",
     "bp": None, "cp": _make_bull_patch(9, vix_max=14.0)},
    {"id": "G5", "name": "2-Miss Bear + VIX spike", "gate": "bear_score>=8 AND vix_delta>=0.5",
     "bp": _make_bear_patch(8, vix_delta_min=0.5), "cp": None},
]


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main() -> int:
    print("Loading data...", flush=True)
    if not SPY_PATH.exists():
        print(f"ERROR: {SPY_PATH} not found"); return 1
    if not VIX_PATH.exists():
        print(f"ERROR: {VIX_PATH} not found"); return 1

    spy_df = pd.read_csv(str(SPY_PATH))
    vix_df = pd.read_csv(str(VIX_PATH))
    # Pre-compute date column for fast filtering
    spy_df["_date"] = pd.to_datetime(spy_df["timestamp_et"], utc=True).dt.strftime("%Y-%m-%d")
    vix_df["_date"] = pd.to_datetime(vix_df["timestamp_et"], utc=True).dt.strftime("%Y-%m-%d")
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows", flush=True)

    # ── Step 1: Baseline on J days (fast) ────────────────────────
    print("\n[BASELINE] J-days only (10/10 strict)...", flush=True)
    base_j = _run_j_days(spy_df, vix_df)
    base_edge = _calc_edge(base_j["pnl"])
    print(f"  J-day P&L per day:")
    for d in ALL_J_DAYS:
        pnl = base_j["pnl"].get(d, None)
        n = base_j["n"].get(d, 0)
        lbl = "W" if d in J_WINNERS else "L"
        status = f"${pnl:,.0f} (n={n})" if pnl is not None else "no trade"
        print(f"    [{lbl}] {d}: {status}")
    print(f"  Baseline edge_capture: ${base_edge:.0f}", flush=True)

    # ── Step 2: Baseline full-window (for Sharpe reference) ──────
    print("\n[BASELINE] Full window (Jan 2025 – Jun 2026)...", flush=True)
    base_full = _run_full_window(spy_df, vix_df)
    print(f"  n={base_full['n']}, WR={base_full['wr']:.1%}, "
          f"P&L=${base_full['pnl']:,.0f}, Sharpe={base_full['sharpe']:.3f}", flush=True)
    base_sharpe = base_full["sharpe"]
    base_final = round(base_edge * base_sharpe, 2)

    baseline_result = {
        "n_trades": base_full["n"],
        "wr": base_full["wr"],
        "total_pnl": base_full["pnl"],
        "sharpe": base_sharpe,
        "edge_capture": base_edge,
        "final_score": base_final,
        "j_days": {d: round(base_j["pnl"].get(d, 0.0), 2) for d in ALL_J_DAYS},
    }

    # ── Step 3: Scenario sweep on J days ────────────────────────
    print(f"\n[SWEEP] Running {len(SCENARIOS)} scenarios on J days...", flush=True)
    results = []

    for sc in SCENARIOS:
        print(f"  [{sc['id']}] {sc['name']}: {sc['gate']}", flush=True)
        j = _run_j_days(spy_df, vix_df, bear_patch=sc["bp"], bull_patch=sc["cp"])
        edge = _calc_edge(j["pnl"])
        op16 = edge >= OP16_FLOOR

        # Marginal vs baseline
        marg_pnl = sum(j["pnl"].get(d, 0.0) - base_j["pnl"].get(d, 0.0)
                       for d in ALL_J_DAYS)
        marg_n = sum(max(0, j["n"].get(d, 0) - base_j["n"].get(d, 0))
                     for d in ALL_J_DAYS)
        marg_wins = sum(max(0, j["wins"].get(d, 0) - base_j["wins"].get(d, 0))
                        for d in ALL_J_DAYS)
        marg_wr = (marg_wins / marg_n) if marg_n > 0 else 0.0
        verdict = _verdict(marg_wr, marg_pnl, edge)

        # Print per-day
        for d in ALL_J_DAYS:
            pnl = j["pnl"].get(d, None)
            base_pnl = base_j["pnl"].get(d, None)
            delta = (pnl or 0.0) - (base_pnl or 0.0)
            lbl = "W" if d in J_WINNERS else "L"
            delta_str = f" ({delta:+.0f})" if abs(delta) > 0.5 else ""
            status = f"${pnl:,.0f}{delta_str}" if pnl is not None else "no trade"
            print(f"    [{lbl}] {d}: {status}")

        op16_str = "PASS" if op16 else "fail"
        print(f"    -> edge=${edge:.0f} {op16_str} | marg: n={marg_n} WR={marg_wr:.0%} "
              f"P&L=${marg_pnl:+,.0f} | {verdict}", flush=True)

        results.append({
            "id": sc["id"],
            "name": sc["name"],
            "gate": sc["gate"],
            "n_trades": None,  # populated in Step 4 for passing candidates
            "wr": None,
            "total_pnl": None,
            "sharpe": None,
            "edge_capture": edge,
            "op16_pass": op16,
            "final_score": None,  # populated in Step 4
            "marginal_trades": marg_n,
            "marginal_pnl": round(marg_pnl, 2),
            "marginal_wr": round(marg_wr, 4),
            "j_days": {d: round(j["pnl"].get(d, 0.0), 2) for d in ALL_J_DAYS},
            "verdict": verdict,
        })

    # ── Step 4: Full-window for top OP-16-passing scenarios ───────
    passing = sorted([r for r in results if r["op16_pass"]],
                     key=lambda x: -x["edge_capture"])
    print(f"\n[FULL-WINDOW] {len(passing)} OP-16-passing scenarios...", flush=True)

    for r in passing[:5]:
        sc = next(s for s in SCENARIOS if s["id"] == r["id"])
        print(f"  [{r['id']}] {r['name']}...", flush=True)
        fw = _run_full_window(spy_df, vix_df, bear_patch=sc["bp"], bull_patch=sc["cp"])
        r["n_trades"] = fw["n"]
        r["wr"] = fw["wr"]
        r["total_pnl"] = fw["pnl"]
        r["sharpe"] = fw["sharpe"]
        r["final_score"] = round(r["edge_capture"] * fw["sharpe"], 2) if fw["sharpe"] else 0.0
        print(f"    n={fw['n']}, WR={fw['wr']:.1%}, P&L=${fw['pnl']:,.0f}, "
              f"Sharpe={fw['sharpe']:.3f}, FinalScore={r['final_score']:.1f}", flush=True)

    # For non-validated scenarios: fill in baseline Sharpe as proxy
    for r in results:
        if r["n_trades"] is None:
            r["n_trades"] = base_full["n"]
            r["wr"] = base_full["wr"]
            r["total_pnl"] = base_full["pnl"]
            r["sharpe"] = base_sharpe
            r["final_score"] = round(r["edge_capture"] * base_sharpe, 2)

    # ── Summary table ─────────────────────────────────────────────
    print(f"\n{'':=<110}")
    print(f"{'ID':>4}  {'Gate':>40}  {'N':>5}  {'WR':>6}  {'Edge':>7}  "
          f"{'OP16':>5}  {'Score':>8}  {'MargN':>6}  {'MargWR':>7}  {'Verdict'}")
    print(f"{'BASE':>4}  {'10/10 strict':>40}  {base_full['n']:>5}  "
          f"{base_full['wr']:>6.1%}  {base_edge:>7.0f}  {'--':>5}  "
          f"{base_final:>8.1f}  {'--':>6}  {'--':>7}  BASELINE")
    for r in sorted(results, key=lambda x: -x["edge_capture"]):
        op16_str = "PASS" if r["op16_pass"] else "fail"
        n_str = str(r["n_trades"]) if r["n_trades"] is not None else "-"
        wr_str = f"{r['wr']:.1%}" if r["wr"] is not None else "-"
        sc_str = f"{r['final_score']:.1f}" if r["final_score"] is not None else "-"
        print(f"{r['id']:>4}  {r['gate']:>40}  {n_str:>5}  {wr_str:>6}  "
              f"{r['edge_capture']:>7.0f}  {op16_str:>5}  {sc_str:>8}  "
              f"{r['marginal_trades']:>6}  {r['marginal_wr']:>7.0%}  {r['verdict']}")

    # Best candidate
    op16_passing = [r for r in results if r["op16_pass"]]
    if op16_passing:
        best = max(op16_passing, key=lambda x: x["final_score"] or 0)
        print(f"\nTop OP-16 candidate: {best['id']} — {best['name']}")
        print(f"  edge={best['edge_capture']:.0f}, final_score={best['final_score']:.1f}, "
              f"verdict={best['verdict']}")
    else:
        print(f"\nNo OP-16 passing candidates (floor: {OP16_FLOOR})")

    # ── Write output ──────────────────────────────────────────────
    output = {
        "generated": dt.datetime.now().isoformat(),
        "data_window": "2025-01-02 to 2026-06-16",
        "op16_floor": OP16_FLOOR,
        "max_edge": MAX_EDGE,
        "baseline_10_10": baseline_result,
        "scenarios": results,
    }
    out_path = REPO / "analysis" / "recommendations" / "gate_sweep_threshold.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out_path), "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
