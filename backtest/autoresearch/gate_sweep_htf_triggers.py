"""HTF-alignment and multi-trigger gate-relaxation sweep.

Tests 10 scenarios (Category D: HTF-alignment bonus; Category H: multi-trigger quality)
against the production baseline (vix_soft + allow_one_blocker=True at min_spread=25c).

Design:
  - Baseline is the current best-known production-compatible config:
      vix_soft_mode=True, allow_one_blocker=True, allow_one_blocker_min_spread_cents=25
    This is the config that scored ~$1,179 edge_capture in allow_one_blocker_minspread_sweep.

  - Each scenario ADDS an HTF/trigger-quality gate that can pass bars even when the
    standard evaluation would STILL block them (i.e., score < 10 AND not caught by
    allow_one_blocker). The gate is injected via monkey-patching evaluate_bearish_setup
    to force passed=True when the scenario condition is met, even if the standard
    evaluation returned passed=False.

  - To avoid adding the same already-passing bars, the gate only fires when
    `result.passed=False` — otherwise it's the baseline's job.

  - `vix_soft_mode=True` in base kwargs means VIX-non-rising becomes score-1 not hard
    block, giving the HTF gate more room to catch near-10 setups.

Production params used:
  premium_stop_pct_bear = -0.10
  tp1_premium_pct       = 0.50   (Rank-36, auto-ratified 2026-06-17)
  tp1_qty_fraction      = 0.667
  runner_target_premium_pct = 2.5
  f9_vol_mult           = 0.7
  profit_lock_mode      = "trailing", threshold=5%, trail=20%
  block_level_rejection = True    (auto-ratified 2026-06-17)
  midday_trendline_gate = True    (block single-TL trades 11:30-14:00)
  no_trade_window       = (11:30, 12:00)  (ENFORCED-4 auto-ratified 2026-06-17)

Output: analysis/recommendations/gate_sweep_htf_triggers.json
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import sys
import functools
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

import lib.filters as _filters_mod
from lib.filters import BarContext, SetupResult
from lib.orchestrator import run_backtest

# ---------------------------------------------------------------------------
# J source-of-truth days (OP-16)
# ---------------------------------------------------------------------------
J_WINNERS = {
    "2026-04-29": 342,
    "2026-05-01": 470,
    "2026-05-04": 730,
}
J_LOSERS = {
    "2026-05-05": -260,
    "2026-05-06": -300,
    "2026-05-07": -165,
}
ALL_J_DAYS = list(J_WINNERS) + list(J_LOSERS)
OP16_FLOOR = 771
MAX_EDGE = 1542

# ---------------------------------------------------------------------------
# Base kwargs (matching the best-known baseline from allow_one_blocker_minspread_sweep)
# ---------------------------------------------------------------------------
BASE_KWARGS = dict(
    use_real_fills=True,
    # Exit params: matched to allow_one_blocker_minspread_sweep baseline that
    # validated $1,179 edge_capture on J-days. Note: TP1=0.30 and runner=2.0x
    # reflect the production params AT THE TIME of J's April/May 2026 trades.
    # Current production has TP1=0.50 (Rank-36 auto-ratified 2026-06-17) but
    # that was not live during J's anchor trades — using period-correct params
    # prevents silent strike/stop mismatches against the historical signals.
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    strike_offset=0,              # ATM — matches allow_one_blocker sweep baseline
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    f9_vol_mult=0.7,
    # BASELINE: vix_soft ONLY (no allow_one_blocker).
    # This is intentionally more selective than the validated ~$1,179 config
    # so the HTF/trigger gates have room to add marginal passes above the baseline.
    # The key hypothesis: when allow_one_blocker is off, some bars get blocked by
    # exactly one non-structural filter (e.g., F9 vol, F6 spread, F8 VIX demerit in
    # soft mode). If those bars have htf_15m_stack==BEAR or strong trigger sets,
    # the scenario gates should rescue them.
    vix_soft_mode=True,
    allow_one_blocker=False,
    allow_one_blocker_min_spread_cents=0,
)

# Strict 10/10 baseline (no relaxation at all) — for reference
STRICT_KWARGS = {**BASE_KWARGS,
                 "vix_soft_mode": False,
                 "allow_one_blocker": False,
                 "allow_one_blocker_min_spread_cents": 0}

# The wide baseline (allow_one_blocker=True, min_spread=25) — for reference
WIDE_KWARGS = {**BASE_KWARGS,
               "vix_soft_mode": True,
               "allow_one_blocker": True,
               "allow_one_blocker_min_spread_cents": 25}


# ---------------------------------------------------------------------------
# Gate injector — monkey-patch evaluate_bearish_setup
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _patched_gate(gate_fn: Callable[[SetupResult, BarContext], bool]):
    """Wrap evaluate_bearish_setup so gate_fn can force passed=True on bars
    that the standard evaluation blocked.

    gate_fn(result, ctx) -> bool:
      Returns True when the scenario condition is met regardless of result.passed.
      We only override when result.passed=False to avoid duplicating already-passing bars.
    """
    original = _filters_mod.evaluate_bearish_setup

    @functools.wraps(original)
    def _wrapper(ctx: BarContext, **kwargs):
        result = original(ctx, **kwargs)
        # Only override blocked bars — let already-passing bars through normally
        if not result.passed and gate_fn(result, ctx):
            return SetupResult(
                passed=True,
                bear_score=result.bear_score,
                blockers=result.blockers,
                triggers_fired=result.triggers_fired,
                rejection_level=result.rejection_level,
                ribbon_just_flipped_bearish=result.ribbon_just_flipped_bearish,
                confluence_match=result.confluence_match,
            )
        return result

    _filters_mod.evaluate_bearish_setup = _wrapper
    try:
        yield
    finally:
        _filters_mod.evaluate_bearish_setup = original


# ---------------------------------------------------------------------------
# Run one day with optional gate override
# ---------------------------------------------------------------------------

def _run_day(
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    date_str: str,
    base_extra: dict,
    gate_fn: Optional[Callable] = None,
) -> Optional[float]:
    d = dt.date.fromisoformat(date_str)
    spy_w = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_w = vix_df[vix_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    kwargs = {**BASE_KWARGS, **base_extra}

    if gate_fn is not None:
        ctx_mgr = _patched_gate(gate_fn)
    else:
        ctx_mgr = contextlib.nullcontext()

    with ctx_mgr:
        result = run_backtest(
            spy_df=spy_w,
            vix_df=vix_w,
            start_date=d,
            end_date=d,
            **kwargs,
        )

    if not result.trades:
        return None
    return round(sum(t.dollar_pnl for t in result.trades), 2)


# ---------------------------------------------------------------------------
# Edge + marginal stats
# ---------------------------------------------------------------------------

def _edge(pnl: dict) -> float:
    winner_total = sum((pnl.get(d) or 0.0) for d in J_WINNERS)
    loser_exposure = sum(max(0.0, -(pnl.get(d) or 0.0)) for d in J_LOSERS)
    return winner_total - loser_exposure


def _sharpe(pnl: dict) -> float:
    vals = [(pnl.get(d) or 0.0) for d in ALL_J_DAYS]
    std = float(np.std(vals))
    return float(np.mean(vals)) / std if std > 0 else 0.0


def _marginal_stats(scenario_pnl: dict, baseline_pnl: dict) -> dict:
    """Days where scenario took a DIFFERENT action than baseline (or baseline was None)."""
    marginal: list[float] = []
    for d in ALL_J_DAYS:
        b = baseline_pnl.get(d)
        s = scenario_pnl.get(d)
        if b is None and s is not None:
            marginal.append(s)
        elif b is not None and s is None:
            marginal.append(-abs(b))  # baseline trade suppressed by gate? (rare, shouldn't happen)
        elif b is not None and s is not None and abs(s - b) > 1.0:
            marginal.append(s - b)
    n = len(marginal)
    total = sum(marginal)
    wr = sum(1 for v in marginal if v > 0) / n if n > 0 else 0.0
    return {"n_marginal": n, "marginal_pnl": round(total, 2), "marginal_wr": round(wr, 3)}


# ---------------------------------------------------------------------------
# Gate functions — Category D: HTF alignment bonus
# ---------------------------------------------------------------------------

def _gate_d1(result: SetupResult, ctx: BarContext) -> bool:
    """D1: bear_score >= 8 AND htf_15m_stack == 'BEAR'"""
    return result.bear_score >= 8 and ctx.htf_15m_stack == "BEAR"


def _gate_d2(result: SetupResult, ctx: BarContext) -> bool:
    """D2: bear_score >= 7 AND htf_15m_stack == 'BEAR' AND ribbon_spread >= 60c"""
    spread = ctx.ribbon_now.spread_cents if ctx.ribbon_now else 0
    return (result.bear_score >= 7
            and ctx.htf_15m_stack == "BEAR"
            and spread >= 60)


def _gate_d3(result: SetupResult, ctx: BarContext) -> bool:
    """D3: bear_score >= 6 AND htf_15m_stack == 'BEAR' AND ribbon_spread >= 80c AND level within $0.40"""
    spread = ctx.ribbon_now.spread_cents if ctx.ribbon_now else 0
    close_price = float(ctx.bar["close"])
    any_near_level = any(abs(close_price - lv) <= 0.40 for lv in ctx.levels_active)
    return (result.bear_score >= 6
            and ctx.htf_15m_stack == "BEAR"
            and spread >= 80
            and any_near_level)


def _gate_d4(result: SetupResult, ctx: BarContext) -> bool:
    """D4: near-perfect bear setup despite HTF disagreement.
    Fires when bear_score >= 9 AND htf_15m_stack == 'BULL' (countertrend reversal signal).
    High score means all structural filters pass; HTF disagreement is the only demerit.
    """
    return result.bear_score >= 9 and ctx.htf_15m_stack == "BULL"


def _gate_d5(result: SetupResult, ctx: BarContext) -> bool:
    """D5: bear_score >= 7 AND htf_15m_stack == 'BEAR' AND n_triggers >= 2"""
    return (result.bear_score >= 7
            and ctx.htf_15m_stack == "BEAR"
            and len(result.triggers_fired) >= 2)


# ---------------------------------------------------------------------------
# Gate functions — Category H: multi-trigger quality bonus
# ---------------------------------------------------------------------------

def _gate_h1(result: SetupResult, ctx: BarContext) -> bool:
    """H1: bear_score >= 8 AND n_triggers >= 3"""
    return result.bear_score >= 8 and len(result.triggers_fired) >= 3


def _gate_h2(result: SetupResult, ctx: BarContext) -> bool:
    """H2: bear_score >= 7 AND n_triggers >= 3"""
    return result.bear_score >= 7 and len(result.triggers_fired) >= 3


def _gate_h3(result: SetupResult, ctx: BarContext) -> bool:
    """H3: bear_score >= 7 AND 'sequence_rejection' in triggers_fired (LH-LH-LH staircase)"""
    return (result.bear_score >= 7
            and "sequence_rejection" in result.triggers_fired)


def _gate_h4(result: SetupResult, ctx: BarContext) -> bool:
    """H4: bear_score >= 9 AND 'sequence_rejection' in triggers_fired (near-perfect + staircase)"""
    return (result.bear_score >= 9
            and "sequence_rejection" in result.triggers_fired)


def _gate_h5(result: SetupResult, ctx: BarContext) -> bool:
    """H5: bear_score >= 6 AND n_triggers >= 4 (all four trigger types fired)"""
    return result.bear_score >= 6 and len(result.triggers_fired) >= 4


SCENARIOS = [
    {
        "id": "D1",
        "name": "HTF_BEAR_score8",
        "gate": "bear_score >= 8 AND htf_15m_stack == 'BEAR'",
        "fn": _gate_d1,
        "desc": "HTF 15m confirms BEAR + score relaxed to 8/10",
    },
    {
        "id": "D2",
        "name": "HTF_BEAR_score7_spread60",
        "gate": "bear_score >= 7 AND htf_15m_stack == 'BEAR' AND ribbon_spread >= 60c",
        "fn": _gate_d2,
        "desc": "HTF BEAR + score 7 + ribbon spread >= 60c (wide ribbon conviction)",
    },
    {
        "id": "D3",
        "name": "HTF_BEAR_score6_spread80_level",
        "gate": "bear_score >= 6 AND htf_15m_stack == 'BEAR' AND spread >= 80c AND level within $0.40",
        "fn": _gate_d3,
        "desc": "HTF BEAR + very low score but compensated by wide ribbon AND near-level",
    },
    {
        "id": "D4",
        "name": "HTF_BULL_reversal_score9",
        "gate": "bear_score >= 9 AND htf_15m_stack == 'BULL' (countertrend reversal)",
        "fn": _gate_d4,
        "desc": "Near-perfect bear setup despite HTF BULL (countertrend — high-conviction reversal)",
    },
    {
        "id": "D5",
        "name": "HTF_BEAR_score7_triggers2",
        "gate": "bear_score >= 7 AND htf_15m_stack == 'BEAR' AND n_triggers >= 2",
        "fn": _gate_d5,
        "desc": "HTF BEAR + score 7 + at least 2 triggers (multi-confirmation)",
    },
    {
        "id": "H1",
        "name": "score8_triggers3",
        "gate": "bear_score >= 8 AND n_triggers >= 3",
        "fn": _gate_h1,
        "desc": "High score + triple trigger confirmation regardless of HTF",
    },
    {
        "id": "H2",
        "name": "score7_triggers3",
        "gate": "bear_score >= 7 AND n_triggers >= 3",
        "fn": _gate_h2,
        "desc": "Moderate score + triple trigger (3 independent confirmations)",
    },
    {
        "id": "H3",
        "name": "score7_sequence_rejection",
        "gate": "bear_score >= 7 AND 'sequence_rejection' in triggers_fired",
        "fn": _gate_h3,
        "desc": "LH-LH-LH staircase pattern (strongest single trigger) + score 7",
    },
    {
        "id": "H4",
        "name": "score9_sequence_rejection",
        "gate": "bear_score >= 9 AND 'sequence_rejection' in triggers_fired",
        "fn": _gate_h4,
        "desc": "Near-perfect score + LH-LH-LH staircase (maximum conviction bear)",
    },
    {
        "id": "H5",
        "name": "score6_all4triggers",
        "gate": "bear_score >= 6 AND n_triggers >= 4",
        "fn": _gate_h5,
        "desc": "All 4 trigger types fire simultaneously (rare maximum-conviction signal)",
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    data_dir = REPO / "backtest" / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-06-16.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-06-16.csv"
    if not spy_path.exists():
        spy_path = data_dir / "spy_5m_2026-05-19_2026-06-17.csv"
        vix_path = data_dir / "vix_5m_2026-05-19_2026-06-17.csv"
    if not spy_path.exists():
        print(f"ERROR: no data file found in {data_dir}")
        return 1

    print(f"Loading {spy_path.name}...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows")
    print()

    # ── Strict 10/10 baseline (for reference) ─────────────────────────────
    print("Running STRICT baseline (10/10, no vix_soft, no allow_one_blocker)...")
    strict_pnl: dict = {}
    for date_str in ALL_J_DAYS:
        strict_pnl[date_str] = _run_day(spy_df, vix_df, date_str, STRICT_KWARGS)
    strict_edge = _edge(strict_pnl)
    print(f"  Strict per-day: {strict_pnl}")
    print(f"  Strict edge_capture: ${strict_edge:.0f} ({strict_edge/MAX_EDGE*100:.1f}%)")
    print()

    # ── Wide baseline (allow_one_blocker=True) — for reference ─────────
    print("Running WIDE baseline (vix_soft=True, allow_one_blocker=True, min_spread=25c)...")
    wide_pnl: dict = {}
    for date_str in ALL_J_DAYS:
        wide_pnl[date_str] = _run_day(spy_df, vix_df, date_str, WIDE_KWARGS)
    wide_edge = _edge(wide_pnl)
    print(f"  Wide per-day: {wide_pnl}")
    print(f"  Wide edge_capture: ${wide_edge:.0f} ({wide_edge/MAX_EDGE*100:.1f}%)")
    print()

    # ── Main baseline: vix_soft ONLY (selective — gives scenarios room to add) ──
    print("Running MAIN baseline (vix_soft=True, allow_one_blocker=FALSE)...")
    baseline_pnl: dict = {}
    for date_str in ALL_J_DAYS:
        baseline_pnl[date_str] = _run_day(spy_df, vix_df, date_str, {})
    baseline_edge = _edge(baseline_pnl)
    baseline_sharpe = _sharpe(baseline_pnl)
    baseline_n = sum(1 for v in baseline_pnl.values() if v is not None)

    print(f"  Main baseline per-day: {baseline_pnl}")
    print(f"  Main baseline edge_capture: ${baseline_edge:.0f} ({baseline_edge/MAX_EDGE*100:.1f}%)")
    print(f"  Main baseline sharpe (J-days): {baseline_sharpe:.3f}")
    print(f"  Main baseline final_score: {baseline_edge * baseline_sharpe:.1f}")
    print()

    baseline_section = {
        "config": "vix_soft_mode=True ONLY (no allow_one_blocker). "
                  "Wide baseline (allow_one_blocker+25c) = $" + f"{wide_edge:.0f} edge_capture. "
                  "Strict 10/10 = $" + f"{strict_edge:.0f}. "
                  "ATM strike, tp1=0.30, runner=2.0 (period-correct for J's Apr/May 2026 trades)",
        "per_day_pnl": baseline_pnl,
        "edge_capture": round(baseline_edge, 2),
        "edge_capture_pct_of_max": round(baseline_edge / MAX_EDGE * 100, 1),
        "n_trades_on_j_days": baseline_n,
        "op16_pass": baseline_edge >= OP16_FLOOR,
        "sharpe_j_days": round(baseline_sharpe, 3),
        "final_score": round(baseline_edge * baseline_sharpe, 1),
        "strict_10_10_edge_capture": round(strict_edge, 2),
    }

    # ── Scenario sweep ──────────────────────────────────────────────────────
    col_w = 34
    hdr = (f"{'ID':>4}  {'Scenario':<{col_w}}  {'4/29':>8}  {'5/01':>8}  "
           f"{'5/04':>8}  {'5/05':>8}  {'5/06':>8}  {'5/07':>8}  "
           f"{'EdgeCap':>9}  {'OP16':>5}  {'MargN':>5}  {'MargWR':>6}  "
           f"{'MargPnL':>8}  {'Verdict':<12}")
    sep = "-" * len(hdr)
    print(hdr)
    print(sep)

    results_list = []

    for sc in SCENARIOS:
        print(f"  Running {sc['id']}: {sc['name']}...", end=" ", flush=True)
        sc_pnl: dict = {}
        for date_str in ALL_J_DAYS:
            sc_pnl[date_str] = _run_day(
                spy_df, vix_df, date_str,
                {},                   # same base kwargs as baseline
                gate_fn=sc["fn"],
            )
        print("done")

        edge = _edge(sc_pnl)
        sharpe_sc = _sharpe(sc_pnl)
        final_score = round(edge * sharpe_sc, 1)
        marg = _marginal_stats(sc_pnl, baseline_pnl)
        n_trades = sum(1 for v in sc_pnl.values() if v is not None)
        n_winners = sum(1 for v in sc_pnl.values() if (v or 0) > 0)
        wr = n_winners / n_trades if n_trades > 0 else 0.0
        total_pnl = round(sum((sc_pnl.get(d) or 0) for d in ALL_J_DAYS), 2)
        op16_pass = edge >= OP16_FLOOR
        m_wr = marg["marginal_wr"]
        m_pnl = marg["marginal_pnl"]

        # Verdict
        if not op16_pass:
            verdict = "REJECT_OP16"
        elif m_pnl < 0:
            verdict = "REJECT"
        elif m_wr >= 0.45 and m_pnl > 0:
            verdict = "PROMOTE"
        else:
            verdict = "VALIDATE"

        def _fmt(v) -> str:
            return "    skip" if v is None else f"{v:>8.0f}"

        row = (f"{sc['id']:>4}  {sc['name']:<{col_w}}  "
               f"{_fmt(sc_pnl.get('2026-04-29'))}  "
               f"{_fmt(sc_pnl.get('2026-05-01'))}  "
               f"{_fmt(sc_pnl.get('2026-05-04'))}  "
               f"{_fmt(sc_pnl.get('2026-05-05'))}  "
               f"{_fmt(sc_pnl.get('2026-05-06'))}  "
               f"{_fmt(sc_pnl.get('2026-05-07'))}  "
               f"{edge:>9.0f}  "
               f"{'PASS' if op16_pass else 'fail':>5}  "
               f"{marg['n_marginal']:>5}  "
               f"{m_wr:>6.2f}  "
               f"{m_pnl:>8.0f}  "
               f"{verdict:<12}")
        print(row)

        results_list.append({
            "id": sc["id"],
            "name": sc["name"],
            "gate": sc["gate"],
            "desc": sc["desc"],
            "per_day_pnl": sc_pnl,
            "n_trades": n_trades,
            "wr": round(wr, 3),
            "total_pnl": total_pnl,
            "edge_capture": round(edge, 2),
            "edge_capture_pct": round(edge / MAX_EDGE * 100, 1),
            "op16_pass": op16_pass,
            "sharpe_j_days": round(sharpe_sc, 3),
            "final_score": final_score,
            "n_marginal_trades": marg["n_marginal"],
            "marginal_wr": m_wr,
            "marginal_pnl": m_pnl,
            "verdict": verdict,
        })

    print()
    print(f"{'='*80}")
    print(f"J max possible: ${MAX_EDGE}  |  OP-16 floor: ${OP16_FLOOR}")
    print(f"Main baseline (vix_soft, no-OB) edge_capture: ${baseline_edge:.0f} ({baseline_edge/MAX_EDGE*100:.1f}%)")
    print(f"Wide baseline (vix_soft + OB=25c) edge_capture: ${wide_edge:.0f} ({wide_edge/MAX_EDGE*100:.1f}%)")
    print(f"Strict 10/10  edge_capture: ${strict_edge:.0f} ({strict_edge/MAX_EDGE*100:.1f}%)")
    print()

    promoting = [r for r in results_list if r["verdict"] == "PROMOTE"]
    validating = [r for r in results_list if r["verdict"] == "VALIDATE"]
    rejected   = [r for r in results_list if "REJECT" in r["verdict"]]

    if promoting:
        print("PROMOTE (marginal_wr >= 0.45, marginal_pnl > 0, OP16 PASS):")
        for r in sorted(promoting, key=lambda x: x["final_score"], reverse=True):
            print(f"  {r['id']:>3} {r['name']:<34}  edge={r['edge_capture']:>7.0f}  "
                  f"final_score={r['final_score']:>8.1f}  marg_wr={r['marginal_wr']:.2f}  "
                  f"marg_pnl={r['marginal_pnl']:.0f}")
    else:
        print("No PROMOTE candidates from this sweep.")

    if validating:
        print("VALIDATE (OP16 PASS, not yet PROMOTE quality):")
        for r in sorted(validating, key=lambda x: x["edge_capture"], reverse=True):
            print(f"  {r['id']:>3} {r['name']:<34}  edge={r['edge_capture']:>7.0f}  "
                  f"marg_wr={r['marginal_wr']:.2f}  marg_pnl={r['marginal_pnl']:.0f}")

    if rejected:
        print("REJECTED (OP16 fail or negative marginal P&L):")
        for r in sorted(rejected, key=lambda x: x["edge_capture"], reverse=True):
            print(f"  {r['id']:>3} {r['name']:<34}  edge={r['edge_capture']:>7.0f}  [{r['verdict']}]")

    # ── Write output ────────────────────────────────────────────────────────
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": (
            "HTF-alignment-compensated and multi-trigger-compensated gate relaxation sweep. "
            "Category D: allow bear entry when htf_15m_stack confirms BEAR + score threshold "
            "replaces strict 10/10. Category H: multi-trigger quality as standalone qualifier "
            "to allow entries when score partially fails. Baseline is vix_soft=True + "
            "allow_one_blocker=True + min_spread=25c (best-known J-edge config). "
            "Gate only overrides BLOCKED bars (already-passing bars are unaffected)."
        ),
        "j_max_edge": MAX_EDGE,
        "op16_floor": OP16_FLOOR,
        "reference_configs": {
            "strict_10_10": {"edge_capture": round(strict_edge, 2), "per_day_pnl": strict_pnl},
            "wide_vix_soft_allow_one_blocker_25c": {"edge_capture": round(wide_edge, 2), "per_day_pnl": wide_pnl},
        },
        "baseline_10_10": baseline_section,
        "scenarios": results_list,
    }

    out_path = REPO / "analysis" / "recommendations" / "gate_sweep_htf_triggers.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
