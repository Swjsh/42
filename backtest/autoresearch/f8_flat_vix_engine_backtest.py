"""F8 flat-VIX unblock — full engine backtest validation.

Tests the proposed F8 filter change: allow flat VIX when vix_now > 17.50 for
bear entries. Currently F8 requires vix_direction=="rising"; this change adds
a second path: vd=="flat" AND vix_now > 17.50 (higher floor to guard 5/05
borderline MID-regime days where VIX max was only 17.44).

CURRENT:  vix_pass = ctx.vix_now > 17.30  AND  vd == "rising"
PROPOSED: vix_pass = (ctx.vix_now > 17.30  AND  vd == "rising")
                  OR (ctx.vix_now > 17.50  AND  vd == "flat")
          # "falling" still always blocks — genuine VIX collapse warning.

Output:
    analysis/recommendations/f8-flat-vix-backtest-YYYY-MM-DD.json

Author: Chef persona. Engine-benefit work per OP-25. DOES NOT modify:
    - automation/prompts/heartbeat.md
    - automation/state/params*.json
    - backtest/lib/filters.py (production code)
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable

# --- Path setup (mirrors inspect_combo.py convention) ---
# REPO = backtest/ directory (contains lib/ autoresearch/ data/)
# ROOT = project root (contains automation/ analysis/ strategy/ ...)
REPO = Path(__file__).resolve().parent.parent   # .../backtest/
ROOT = REPO.parent                               # .../42/
sys.path.insert(0, str(REPO))

import pandas as pd

from lib import orchestrator as orch_mod
from lib import filters as filters_mod
from lib.filters import SetupResult
from autoresearch import runner
from autoresearch.j_edge_tracker import (
    score_candidate, print_score_card, V15_J_EDGE_OVERRIDES,
    J_WINNERS, J_LOSERS, J_TOTAL_WINNERS,
)
from autoresearch.metrics import compute_metrics

# === F8 flat-VIX proposal constants ===
VIX_FLAT_BEAR_THRESHOLD = 17.50   # higher floor for flat-VIX path (guards 5/05 max=17.44)
VIX_BEAR_THRESHOLD_ORIG = filters_mod.VIX_BEAR_THRESHOLD  # 17.30 — existing constant


# === Monkey-patch context manager ===

@contextlib.contextmanager
def _f8_flat_vix_patch():
    """Temporarily swap evaluate_bearish_setup in the orchestrator module.

    The orchestrator imports evaluate_bearish_setup via
    `from .filters import evaluate_bearish_setup`, which creates a module-level
    name in orchestrator's namespace. Patching orch_mod.evaluate_bearish_setup
    causes all subsequent calls from within run_backtest to use our wrapper
    (Python resolves it as a global lookup in orch_mod's namespace).

    Cleanup is guaranteed via finally block — no state leak between runs.
    """
    original_fn = orch_mod.evaluate_bearish_setup

    def _patched(
        ctx,
        disable_filters=None,
        min_triggers=1,
        vix_soft_mode=False,
        allow_one_blocker=False,
        allow_one_blocker_min_spread_cents=0,
        no_trade_before=None,
        no_trade_window=None,
        f9_vol_mult=0.7,
    ):
        result = original_fn(
            ctx,
            disable_filters=disable_filters,
            min_triggers=min_triggers,
            vix_soft_mode=vix_soft_mode,
            allow_one_blocker=allow_one_blocker,
            allow_one_blocker_min_spread_cents=allow_one_blocker_min_spread_cents,
            no_trade_before=no_trade_before,
            no_trade_window=no_trade_window,
            f9_vol_mult=f9_vol_mult,
        )
        # Apply flat-VIX rescue only when F8 is among blockers.
        if 8 in result.blockers:
            vd = filters_mod.vix_direction(ctx.vix_now, ctx.vix_prior)
            if vd == "flat" and ctx.vix_now > VIX_FLAT_BEAR_THRESHOLD:
                # F8 passes via flat path — remove from blockers.
                new_blockers = [b for b in result.blockers if b != 8]
                new_passed = len(new_blockers) == 0
                # bear_score: recompute as 10 - blockers. Existing demerits from
                # htf_disagrees / trendline_chop_demerit are NOT re-added here
                # (conservative — we don't inflate score above what baseline gave).
                new_score = result.bear_score + 1  # restore the F8 point
                return SetupResult(
                    passed=new_passed,
                    bear_score=min(10, new_score),
                    blockers=sorted(new_blockers),
                    triggers_fired=result.triggers_fired,
                    rejection_level=result.rejection_level,
                    ribbon_just_flipped_bearish=result.ribbon_just_flipped_bearish,
                    confluence_match=result.confluence_match,
                )
        return result

    orch_mod.evaluate_bearish_setup = _patched
    try:
        yield
    finally:
        orch_mod.evaluate_bearish_setup = original_fn


# === Per-window runners ===

def _run_window(
    params: dict,
    start: dt.date,
    end: dt.date,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    label: str,
) -> dict:
    """Run engine over a date range, return compact metrics dict."""
    try:
        result, m = runner.run_with_params(params, start, end, spy_df, vix_df)
    except Exception as exc:
        return {"label": label, "error": repr(exc)}
    return {
        "label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "n_trades": m.n_trades,
        "n_winners": m.n_winners,
        "win_rate": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0.0,
        "total_pnl": round(m.total_pnl, 2),
        "avg_per_trade": round(m.total_pnl / m.n_trades, 2) if m.n_trades else 0.0,
        "max_drawdown": round(getattr(m, "max_drawdown", 0.0), 2),
        "sharpe": round(getattr(m, "sharpe", 0.0), 3),
    }


def _score_with_patch(
    params: dict,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    use_patch: bool,
) -> dict:
    """Run score_candidate with or without F8 flat-VIX patch."""
    if use_patch:
        with _f8_flat_vix_patch():
            return score_candidate(params, spy_df, vix_df)
    return score_candidate(params, spy_df, vix_df)


def _run_window_with_patch(
    params: dict,
    start: dt.date,
    end: dt.date,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    label: str,
    use_patch: bool,
) -> dict:
    """Run _run_window with or without F8 flat-VIX patch."""
    if use_patch:
        with _f8_flat_vix_patch():
            return _run_window(params, start, end, spy_df, vix_df, label)
    return _run_window(params, start, end, spy_df, vix_df, label)


# === VIX profile per day (diagnostic) ===

def _vix_profile_day(vix_df: pd.DataFrame, date: dt.date) -> dict:
    """Return VIX direction counts + max/min for a single trading day."""
    day_str = date.isoformat()
    mask = vix_df["timestamp_et"].str.startswith(day_str)
    day = vix_df[mask].copy()
    if len(day) == 0:
        return {"date": day_str, "bars": 0, "max_vix": None, "min_vix": None}

    # Compute per-bar vix_direction
    vix_vals = day["close"].values
    rising = flat = falling = 0
    for i in range(1, len(vix_vals)):
        vd = filters_mod.vix_direction(float(vix_vals[i]), float(vix_vals[i - 1]))
        if vd == "rising":
            rising += 1
        elif vd == "flat":
            flat += 1
        else:
            falling += 1

    above_1730 = int((day["close"] > VIX_BEAR_THRESHOLD_ORIG).sum())
    above_1750 = int((day["close"] > VIX_FLAT_BEAR_THRESHOLD).sum())

    return {
        "date": day_str,
        "bars": len(day),
        "max_vix": round(float(day["close"].max()), 2),
        "min_vix": round(float(day["close"].min()), 2),
        "rising": rising,
        "flat": flat,
        "falling": falling,
        "bars_above_1730": above_1730,
        "bars_above_1750": above_1750,
        "flat_bars_above_1750": above_1750,  # all above-1750 flat bars are unlocked by proposed fix
    }


# === Main ===

def main() -> None:
    today = dt.date.today()
    out_path = ROOT / "analysis" / "recommendations" / f"f8-flat-vix-backtest-{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Build params (production baseline + OP-16 j_edge overrides) ---
    params_path = ROOT / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    print("=" * 72)
    print("F8 FLAT-VIX ENGINE BACKTEST VALIDATION")
    print(f"  Proposed:  vix_flat_bear_threshold = {VIX_FLAT_BEAR_THRESHOLD}")
    print(f"  Existing:  vix_bear_threshold       = {VIX_BEAR_THRESHOLD_ORIG}")
    print(f"  Output:    {out_path}")
    print("=" * 72)

    # --- Load data for J's anchor days (wide enough window for context) ---
    anchor_start = dt.date(2026, 4, 28)  # one day before 4/29 for warmup
    anchor_end   = dt.date(2026, 5, 8)   # one day after 5/07
    print(f"\nLoading anchor-day data ({anchor_start} ->{anchor_end})...")
    spy_anchor, vix_anchor = runner.load_data(anchor_start, anchor_end)
    print(f"  SPY: {len(spy_anchor)} bars | VIX: {len(vix_anchor)} bars")

    # --- Load full window data ---
    full_start = dt.date(2025, 1, 2)
    full_end   = dt.date(2026, 5, 16)  # latest available in spy_5m_2025-01-01_2026-05-15.csv
    print(f"\nLoading full window data ({full_start} ->{full_end})...")
    try:
        spy_full, vix_full = runner.load_data(full_start, full_end)
        print(f"  SPY: {len(spy_full)} bars | VIX: {len(vix_full)} bars")
        has_full_data = True
    except FileNotFoundError as exc:
        print(f"  WARNING: full data not available ({exc})")
        print("  Will skip full-window comparison (anchor days only).")
        spy_full = vix_full = None
        has_full_data = False

    # --- VIX profile for key dates ---
    print("\n--- VIX profile (anchor days) ---")
    anchor_dates = [
        dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
        dt.date(2026, 5, 5),  dt.date(2026, 5, 6), dt.date(2026, 5, 7),
    ]
    vix_profiles = {}
    for d in anchor_dates:
        prof = _vix_profile_day(vix_anchor, d)
        vix_profiles[d.isoformat()] = prof
        flat_unlocked = prof.get("flat_bars_above_1750", 0)
        print(
            f"  {d}  max={prof['max_vix']:5.2f}  "
            f"rising={prof['rising']:2d}  flat={prof['flat']:2d}  falling={prof['falling']:2d}  "
            f"above1750={prof['bars_above_1750']:2d}  flat_unlocked={flat_unlocked:2d}"
        )

    # --- J-edge score: BASELINE ---
    print("\n--- Anchor days: BASELINE (F8 unchanged) ---")
    baseline_score = _score_with_patch(params, spy_anchor, vix_anchor, use_patch=False)
    print_score_card(baseline_score)

    # --- J-edge score: PROPOSED ---
    print("\n--- Anchor days: PROPOSED (F8 + flat-VIX >= 17.50) ---")
    proposed_score = _score_with_patch(params, spy_anchor, vix_anchor, use_patch=True)
    print_score_card(proposed_score)

    # --- Guard checks ---
    print("\n--- Guard checks ---")

    # 5/05 loser-day guard: VIX max was 17.44 < 17.50 ->flat bars should STILL be blocked
    p505 = vix_profiles.get("2026-05-05", {})
    guard_505_ok = p505.get("max_vix", 99.0) < VIX_FLAT_BEAR_THRESHOLD
    print(f"  5/05 VIX max={p505.get('max_vix', '?')} < {VIX_FLAT_BEAR_THRESHOLD}: "
          f"{'PASS (protected)' if guard_505_ok else 'FAIL (unprotected!)'}")

    # 5/01 unaffected: VIX was below 17.30 main threshold all day
    p501 = vix_profiles.get("2026-05-01", {})
    guard_501_unaffected = p501.get("max_vix", 99.0) < VIX_BEAR_THRESHOLD_ORIG
    print(f"  5/01 VIX max={p501.get('max_vix', '?')} < {VIX_BEAR_THRESHOLD_ORIG} (main threshold): "
          f"{'PASS (unaffected)' if guard_501_unaffected else 'NOTE (may be partially affected)'}")

    # OP-16 floor check
    proposed_edge = proposed_score["edge_capture"]
    op16_pass = proposed_edge >= J_TOTAL_WINNERS * 0.50  # 50% of $1,542 = $771
    print(f"\n  OP-16 edge_capture floor: ${proposed_edge:.0f} >= $771 "
          f"({'PASS' if op16_pass else 'FAIL'})")
    losers_added = proposed_score["losers_added"]
    losers_guard_pass = losers_added <= baseline_score["losers_added"] + 50  # allow $50 tolerance
    print(f"  losers_added delta: baseline=${baseline_score['losers_added']:.0f} "
          f"-> proposed=${losers_added:.0f} "
          f"({'PASS' if losers_guard_pass else 'WARNING: loser guard degraded'})")

    # --- Full-window comparison (optional) ---
    full_results = {}
    if has_full_data:
        print(f"\n--- Full-window comparison ({full_start} ->{full_end}) ---")

        train_start = dt.date(2025, 1, 2)
        train_end   = dt.date(2025, 12, 31)
        oos_start   = dt.date(2026, 1, 2)
        oos_end     = full_end

        for label, s, e, use_patch in [
            ("train_baseline",  train_start, train_end,  False),
            ("train_proposed",  train_start, train_end,  True),
            ("oos_baseline",    oos_start,   oos_end,    False),
            ("oos_proposed",    oos_start,   oos_end,    True),
        ]:
            print(f"  Running {label} ({s} ->{e})...", end=" ", flush=True)
            res = _run_window_with_patch(params, s, e, spy_full, vix_full, label, use_patch)
            full_results[label] = res
            if "error" in res:
                print(f"ERROR: {res['error']}")
            else:
                print(
                    f"n={res['n_trades']:3d}  WR={res['win_rate']*100:.0f}%  "
                    f"PnL=${res['total_pnl']:+.0f}  avg=${res['avg_per_trade']:+.0f}"
                )

        # Print comparison table
        if all(k in full_results for k in ("train_baseline", "train_proposed")):
            print("\n  --- Train window delta ---")
            b = full_results["train_baseline"]
            p = full_results["train_proposed"]
            if "error" not in b and "error" not in p:
                print(f"    trades:  {b['n_trades']} ->{p['n_trades']} ({p['n_trades']-b['n_trades']:+d})")
                print(f"    WR:      {b['win_rate']*100:.0f}% ->{p['win_rate']*100:.0f}%")
                print(f"    PnL:     ${b['total_pnl']:+.0f} ->${p['total_pnl']:+.0f}")
                print(f"    avg:     ${b['avg_per_trade']:+.0f} ->${p['avg_per_trade']:+.0f}")

        if all(k in full_results for k in ("oos_baseline", "oos_proposed")):
            print("\n  --- OOS window delta ---")
            b = full_results["oos_baseline"]
            p = full_results["oos_proposed"]
            if "error" not in b and "error" not in p:
                print(f"    trades:  {b['n_trades']} ->{p['n_trades']} ({p['n_trades']-b['n_trades']:+d})")
                print(f"    WR:      {b['win_rate']*100:.0f}% ->{p['win_rate']*100:.0f}%")
                print(f"    PnL:     ${b['total_pnl']:+.0f} ->${p['total_pnl']:+.0f}")
                print(f"    avg:     ${b['avg_per_trade']:+.0f} ->${p['avg_per_trade']:+.0f}")

    # --- Confidence score update ---
    baseline_edge = baseline_score["edge_capture"]
    proposed_winners_pct = proposed_score.get("winners_capture_pct", 0.0)

    if op16_pass and guard_505_ok and losers_guard_pass:
        if proposed_edge > baseline_edge + 50:
            new_confidence = 7
            verdict = "PROMISING — OP-16 pass, 5/05 protected, losers contained, edge improves"
        elif proposed_edge >= baseline_edge:
            new_confidence = 6
            verdict = "BORDERLINE — OP-16 pass, guards hold, no regression"
        else:
            new_confidence = 5
            verdict = "WEAK — OP-16 pass but edge doesn't improve vs baseline"
    else:
        new_confidence = 3
        failed_guards = []
        if not op16_pass:
            failed_guards.append(f"OP-16 FAIL (edge_capture=${proposed_edge:.0f} < $771)")
        if not guard_505_ok:
            failed_guards.append(f"5/05 guard FAIL (VIX max={p505.get('max_vix')} >= 17.50)")
        if not losers_guard_pass:
            failed_guards.append(f"losers_added degraded (${losers_added:.0f})")
        verdict = "FAIL — " + " | ".join(failed_guards)

    print(f"\n=== VERDICT ===")
    print(f"  {verdict}")
    print(f"  Confidence: {new_confidence}/10")
    print(f"  Baseline edge_capture:  ${baseline_edge:+.0f}")
    print(f"  Proposed edge_capture:  ${proposed_edge:+.0f}")
    print(f"  Delta:                  ${proposed_edge - baseline_edge:+.0f}")

    # --- Write JSON output ---
    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "candidate": "f8-flat-vix-unblock",
        "proposed_change": {
            "filter": "F8",
            "description": "Allow flat VIX when vix_now > 17.50 for bear entries",
            "current": f"vix_now > {VIX_BEAR_THRESHOLD_ORIG} AND vd == 'rising'",
            "proposed": (
                f"(vix_now > {VIX_BEAR_THRESHOLD_ORIG} AND vd == 'rising') "
                f"OR (vix_now > {VIX_FLAT_BEAR_THRESHOLD} AND vd == 'flat')"
            ),
            "vix_flat_bear_threshold": VIX_FLAT_BEAR_THRESHOLD,
        },
        "verdict": verdict,
        "confidence_score": new_confidence,
        "op16_pass": op16_pass,
        "guard_505_protected": guard_505_ok,
        "losers_guard_pass": losers_guard_pass,
        "anchor_day_scores": {
            "baseline": baseline_score,
            "proposed": proposed_score,
            "edge_capture_delta": round(proposed_edge - baseline_edge, 2),
        },
        "vix_profiles": vix_profiles,
        "full_window_comparison": full_results,
        "params_used": {k: params.get(k) for k in V15_J_EDGE_OVERRIDES},
    }

    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\n  Results written to: {out_path}")

    # --- Recommend next steps ---
    print("\n--- Next steps ---")
    if new_confidence >= 7:
        print("  1. Update candidate file confidence score to 7/10")
        print("  2. Write entry to strategy/candidates/_chef-inbox/ with READY-FOR-J-RATIFICATION")
        print("  3. J ratifies ->add VIX_FLAT_BEAR_THRESHOLD=17.50 to filters.py + params.json")
    elif new_confidence >= 5:
        print("  1. Run simulator_real.py on J's winner days to check option-level P&L")
        print("  2. Verify full-window WR doesn't regress before promoting")
    else:
        print("  1. Investigate failed guards before proceeding")
        print("  2. Consider raising VIX_FLAT_BEAR_THRESHOLD further (17.60?) if 5/05 unprotected")


if __name__ == "__main__":
    main()
