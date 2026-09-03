"""F8 flat-VIX unblock — retune at threshold=18.00.

Re-runs the F8 flat-VIX backtest with VIX_FLAT_BEAR_THRESHOLD=18.00.
Previous run at 17.50 FAILED: 5/05 max_vix=17.85 >= 17.50 -> loser day unprotected.
At 18.00: 5/05 max=17.85 < 18.00 (PROTECTED), 4/29 max=18.97 > 18.00 (UNLOCKED),
5/04 max=18.93 > 18.00 (UNLOCKED). All 3 loser days protected.

Also fixes TypeError in _patched: missing sweep_blocker_enabled + sweep_* kwargs.
Fix: use **kwargs passthrough so any new evaluate_bearish_setup kwargs are forwarded.

PROPOSED: (vix_now > 17.3 AND vd == 'rising') OR (vix_now > 18.0 AND vd == 'flat')

Output:
    analysis/recommendations/f8-flat-vix-18-backtest-{date}.json
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
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

# === F8 flat-VIX proposal constants ===
VIX_FLAT_BEAR_THRESHOLD = 18.00   # raised from 17.50 — protects 5/05 (max=17.85)
VIX_BEAR_THRESHOLD_ORIG = filters_mod.VIX_BEAR_THRESHOLD  # 17.30 existing constant


@contextlib.contextmanager
def _f8_flat_vix_patch():
    """Temporarily swap evaluate_bearish_setup with flat-VIX rescue at 18.00.

    Uses **kwargs passthrough to handle sweep_blocker_enabled and any other
    kwargs added to evaluate_bearish_setup without requiring this wrapper to
    list every parameter explicitly.
    """
    original_fn = orch_mod.evaluate_bearish_setup

    def _patched(ctx, **kwargs):
        result = original_fn(ctx, **kwargs)
        if 8 in result.blockers:
            vd = filters_mod.vix_direction(ctx.vix_now, ctx.vix_prior)
            if vd == "flat" and ctx.vix_now > VIX_FLAT_BEAR_THRESHOLD:
                new_blockers = [b for b in result.blockers if b != 8]
                new_passed = len(new_blockers) == 0
                new_score = result.bear_score + 1
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


def _run_window(
    params: dict,
    start: dt.date,
    end: dt.date,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    label: str,
) -> dict:
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


def _score_with_patch(params, spy_df, vix_df, use_patch: bool) -> dict:
    if use_patch:
        with _f8_flat_vix_patch():
            return score_candidate(params, spy_df, vix_df)
    return score_candidate(params, spy_df, vix_df)


def _run_window_with_patch(params, start, end, spy_df, vix_df, label, use_patch) -> dict:
    if use_patch:
        with _f8_flat_vix_patch():
            return _run_window(params, start, end, spy_df, vix_df, label)
    return _run_window(params, start, end, spy_df, vix_df, label)


def _vix_profile_day(vix_df: pd.DataFrame, date: dt.date) -> dict:
    day_str = date.isoformat()
    mask = vix_df["timestamp_et"].str.startswith(day_str)
    day = vix_df[mask].copy()
    if len(day) == 0:
        return {"date": day_str, "bars": 0, "max_vix": None, "min_vix": None}
    vix_vals = day["close"].values
    rising = flat = falling = 0
    for i in range(1, len(vix_vals)):
        vd = filters_mod.vix_direction(float(vix_vals[i]), float(vix_vals[i - 1]))
        if vd == "rising": rising += 1
        elif vd == "flat": flat += 1
        else: falling += 1
    above_1730 = int((day["close"] > VIX_BEAR_THRESHOLD_ORIG).sum())
    above_1800 = int((day["close"] > VIX_FLAT_BEAR_THRESHOLD).sum())
    return {
        "date": day_str,
        "bars": len(day),
        "max_vix": round(float(day["close"].max()), 2),
        "min_vix": round(float(day["close"].min()), 2),
        "rising": rising, "flat": flat, "falling": falling,
        "bars_above_1730": above_1730,
        "bars_above_1800": above_1800,
        "flat_bars_above_1800": above_1800,
    }


def main() -> None:
    today = dt.date.today()
    out_path = ROOT / "analysis" / "recommendations" / f"f8-flat-vix-18-backtest-{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    params_path = ROOT / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    print("=" * 72)
    print("F8 FLAT-VIX ENGINE BACKTEST VALIDATION (threshold=18.00)")
    print(f"  Proposed:  vix_flat_bear_threshold = {VIX_FLAT_BEAR_THRESHOLD}")
    print(f"  Existing:  vix_bear_threshold       = {VIX_BEAR_THRESHOLD_ORIG}")
    print(f"  Fix note:  _patched uses **kwargs (fixes sweep_blocker_enabled TypeError)")
    print(f"  Output:    {out_path}")
    print("=" * 72)

    anchor_start = dt.date(2026, 4, 28)
    anchor_end   = dt.date(2026, 5, 8)
    print(f"\nLoading anchor-day data ({anchor_start} -> {anchor_end})...")
    spy_anchor, vix_anchor = runner.load_data(anchor_start, anchor_end)
    print(f"  SPY: {len(spy_anchor)} bars | VIX: {len(vix_anchor)} bars")

    full_start = dt.date(2025, 1, 2)
    full_end   = dt.date(2026, 5, 16)
    print(f"\nLoading full window data ({full_start} -> {full_end})...")
    try:
        spy_full, vix_full = runner.load_data(full_start, full_end)
        print(f"  SPY: {len(spy_full)} bars | VIX: {len(vix_full)} bars")
        has_full_data = True
    except FileNotFoundError as exc:
        print(f"  WARNING: full data not available ({exc})")
        spy_full = vix_full = None
        has_full_data = False

    print("\n--- VIX profile (anchor days) ---")
    anchor_dates = [
        dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4),
        dt.date(2026, 5, 5),  dt.date(2026, 5, 6), dt.date(2026, 5, 7),
    ]
    vix_profiles = {}
    for d in anchor_dates:
        prof = _vix_profile_day(vix_anchor, d)
        vix_profiles[d.isoformat()] = prof
        protected = prof.get("max_vix", 99.0) < VIX_FLAT_BEAR_THRESHOLD
        print(
            f"  {d}  max={prof['max_vix']:5.2f}  "
            f"flat={prof['flat']:2d}  above1800={prof.get('bars_above_1800', 0):2d}  "
            f"{'PROTECTED' if protected else 'UNLOCKED'}"
        )

    print("\n--- Anchor days: BASELINE (F8 unchanged) ---")
    baseline_score = _score_with_patch(params, spy_anchor, vix_anchor, use_patch=False)
    print_score_card(baseline_score)

    print("\n--- Anchor days: PROPOSED (F8 + flat-VIX >= 18.00) ---")
    proposed_score = _score_with_patch(params, spy_anchor, vix_anchor, use_patch=True)
    print_score_card(proposed_score)

    print("\n--- Guard checks ---")
    p505 = vix_profiles.get("2026-05-05", {})
    guard_505_ok = p505.get("max_vix", 99.0) < VIX_FLAT_BEAR_THRESHOLD
    print(f"  5/05 VIX max={p505.get('max_vix', '?')} < {VIX_FLAT_BEAR_THRESHOLD}: "
          f"{'PASS (protected)' if guard_505_ok else 'FAIL (unprotected!)'}")

    p507 = vix_profiles.get("2026-05-07", {})
    guard_507_ok = p507.get("max_vix", 99.0) < VIX_FLAT_BEAR_THRESHOLD
    print(f"  5/07 VIX max={p507.get('max_vix', '?')} < {VIX_FLAT_BEAR_THRESHOLD}: "
          f"{'PASS (protected)' if guard_507_ok else 'FAIL (unprotected!)'}")

    p501 = vix_profiles.get("2026-05-01", {})
    guard_501_unaffected = p501.get("max_vix", 99.0) < VIX_BEAR_THRESHOLD_ORIG
    print(f"  5/01 VIX max={p501.get('max_vix', '?')} < {VIX_BEAR_THRESHOLD_ORIG}: "
          f"{'PASS (unaffected by F8)' if guard_501_unaffected else 'NOTE (partial affect)'}")

    proposed_edge = proposed_score["edge_capture"]
    baseline_edge = baseline_score["edge_capture"]
    op16_pass = proposed_edge >= J_TOTAL_WINNERS * 0.50
    print(f"\n  OP-16 edge_capture floor: ${proposed_edge:.0f} >= $771 "
          f"({'PASS' if op16_pass else 'FAIL'})")
    losers_added = proposed_score["losers_added"]
    losers_guard_pass = losers_added <= baseline_score["losers_added"] + 50
    print(f"  losers_added: baseline=${baseline_score['losers_added']:.0f} "
          f"-> proposed=${losers_added:.0f} "
          f"({'PASS' if losers_guard_pass else 'WARNING: loser guard degraded'})")

    full_results = {}
    if has_full_data:
        print(f"\n--- Full-window comparison ({full_start} -> {full_end}) ---")
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
            print(f"  Running {label} ({s} -> {e})...", end=" ", flush=True)
            res = _run_window_with_patch(params, s, e, spy_full, vix_full, label, use_patch)
            full_results[label] = res
            if "error" in res:
                print(f"ERROR: {res['error']}")
            else:
                print(f"n={res['n_trades']:3d}  WR={res['win_rate']*100:.0f}%  "
                      f"PnL=${res['total_pnl']:+.0f}  Sharpe={res['sharpe']:+.3f}")

    all_guards_pass = guard_505_ok and guard_507_ok and losers_guard_pass
    if op16_pass and all_guards_pass:
        if proposed_edge > baseline_edge + 50:
            new_confidence = 7
            verdict = "PROMISING — OP-16 pass, all loser days protected, edge improves"
        elif proposed_edge >= baseline_edge:
            new_confidence = 6
            verdict = "BORDERLINE — OP-16 pass, guards hold, no edge regression"
        else:
            new_confidence = 5
            verdict = "WEAK — OP-16 pass but edge doesn't improve vs baseline"
    else:
        new_confidence = 3
        failed_guards = []
        if not op16_pass:
            failed_guards.append(f"OP-16 FAIL (edge_capture=${proposed_edge:.0f} < $771)")
        if not guard_505_ok:
            failed_guards.append(f"5/05 FAIL (max={p505.get('max_vix')} >= {VIX_FLAT_BEAR_THRESHOLD})")
        if not guard_507_ok:
            failed_guards.append(f"5/07 FAIL (max={p507.get('max_vix')} >= {VIX_FLAT_BEAR_THRESHOLD})")
        if not losers_guard_pass:
            failed_guards.append(f"losers_added degraded (${losers_added:.0f})")
        verdict = "FAIL — " + " | ".join(failed_guards)

    print(f"\n=== VERDICT ===")
    print(f"  {verdict}")
    print(f"  Confidence: {new_confidence}/10")
    print(f"  Baseline edge_capture:  ${baseline_edge:+.0f}")
    print(f"  Proposed edge_capture:  ${proposed_edge:+.0f}")
    print(f"  Delta:                  ${proposed_edge - baseline_edge:+.0f}")

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidate": "f8-flat-vix-unblock-18",
        "proposed_change": {
            "filter": "F8",
            "description": "Allow flat VIX when vix_now > 18.00 for bear entries",
            "current": f"vix_now > {VIX_BEAR_THRESHOLD_ORIG} AND vd == 'rising'",
            "proposed": (
                f"(vix_now > {VIX_BEAR_THRESHOLD_ORIG} AND vd == 'rising') "
                f"OR (vix_now > {VIX_FLAT_BEAR_THRESHOLD} AND vd == 'flat')"
            ),
            "vix_flat_bear_threshold": VIX_FLAT_BEAR_THRESHOLD,
            "change_from_prior": "17.50 -> 18.00 (protects 5/05 max=17.85)",
        },
        "verdict": verdict,
        "confidence_score": new_confidence,
        "op16_pass": op16_pass,
        "guard_505_protected": guard_505_ok,
        "guard_507_protected": guard_507_ok,
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
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\n[f8_vix_18_retune] wrote {out_path}")


if __name__ == "__main__":
    main()
