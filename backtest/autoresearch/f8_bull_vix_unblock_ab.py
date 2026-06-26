"""F8 BULL VIX gate (filter 8) re-validation under the CURRENT engine.

Re-validates the BULL-direction block:
    Filter 8: bull entry requires  VIX < 17.20  OR  vix_falling.
A soft directional VIX gate, ratified pre-2026-06-18 on the OLD engine
(OTM strikes + BS-sim + premium-stops). This tool re-runs the A/B on the
CURRENT engine: REAL OPRA fills (use_real_fills=True) + the managed exit
structure that params.json now carries (chart-stop-primary, -50% cap,
chandelier, partial TP1 + runner).

BASELINE  (block ON):  bull path runs all filters incl. F8.
UNBLOCKED (block OFF):  bull path drops blocker 8 (VIX gate removed).

The block fires ONLY on the BULLISH_RECLAIM_RIDE_THE_RIBBON path, so we
monkey-patch orch_mod.evaluate_bullish_setup (mirror of the bear-side
f8_flat_vix_engine_backtest.py) and remove blocker 8 from its result —
bear-side F8 is untouched, so J's bearish source-of-truth is unaffected by
construction (anchor-no-regression is verified empirically below anyway).

Output:
    analysis/recommendations/f8-bull-vix-unblock-ab-YYYY-MM-DD.json

Author: Chef persona. READ-ONLY re-validation. DOES NOT modify
    params.json / filters.py / heartbeat.md.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")  # we patch evaluate_bullish_setup; skip the oracle assert

REPO = Path(__file__).resolve().parent.parent   # .../backtest/
ROOT = REPO.parent                               # .../42/
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from lib import orchestrator as orch_mod  # noqa: E402
from lib.filters import BullishSetupResult  # noqa: E402
from autoresearch import runner  # noqa: E402
from autoresearch.j_edge_tracker import (  # noqa: E402
    score_candidate, print_score_card, V15_J_EDGE_OVERRIDES,
    J_WINNERS, J_LOSERS, J_TOTAL_WINNERS,
)


# === Unblock patch: drop blocker 8 from the bull setup result ===

@contextlib.contextmanager
def _bull_f8_unblock_patch():
    """Temporarily make evaluate_bullish_setup behave as if F8 were disabled.

    Removes blocker 8 from the result and restores the +1 score point, then
    re-derives `passed` from the remaining blockers. Cleanup guaranteed.
    """
    original_fn = orch_mod.evaluate_bullish_setup

    def _patched(ctx, **kwargs):
        result = original_fn(ctx, **kwargs)
        if 8 in result.blockers:
            new_blockers = [b for b in result.blockers if b != 8]
            return BullishSetupResult(
                passed=(len(new_blockers) == 0),
                bull_score=min(11, result.bull_score + 1),
                blockers=sorted(new_blockers),
                triggers_fired=result.triggers_fired,
                reclaim_level=result.reclaim_level,
                ribbon_just_flipped_bullish=result.ribbon_just_flipped_bullish,
                confluence_match=result.confluence_match,
            )
        return result

    orch_mod.evaluate_bullish_setup = _patched
    try:
        yield
    finally:
        orch_mod.evaluate_bullish_setup = original_fn


def _real_fills_params() -> dict:
    """Production params.json + OP-16 j-edge overrides + REAL FILLS forced on."""
    params = json.loads(
        (ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig")
    )
    params.update(V15_J_EDGE_OVERRIDES)
    params["use_real_fills"] = True  # C1: real OPRA fills are the only WR authority
    return params


def _bull_metrics(result) -> dict:
    """Extract bull-only (side==C) trade metrics from an orchestrator result.

    NOTE: the TradeFill P&L field is `dollar_pnl` (lib/simulator.py:111), NOT
    `pnl_dollars` — the latter does not exist (j_edge_tracker's per-trade DISPLAY
    reads the wrong name and shows $0, but day totals come from m.total_pnl).
    """
    bull = [t for t in result.trades if getattr(t, "side", "?") == "C"]
    n = len(bull)
    wins = sum(1 for t in bull if getattr(t, "dollar_pnl", 0) > 0)
    pnl = sum(getattr(t, "dollar_pnl", 0) for t in bull)
    return {
        "n_bull": n,
        "n_bull_wins": wins,
        "bull_wr": round(wins / n, 3) if n else 0.0,
        "bull_pnl": round(pnl, 2),
        "bull_avg": round(pnl / n, 2) if n else 0.0,
    }


def _run_window(params, start, end, spy, vix, use_unblock):
    cm = _bull_f8_unblock_patch() if use_unblock else contextlib.nullcontext()
    with cm:
        result, m = runner.run_with_params(params, start, end, spy, vix)
    bull = _bull_metrics(result)
    return {
        "n_trades": m.n_trades,
        "total_pnl": round(m.total_pnl, 2),
        "win_rate": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0.0,
        "sharpe": round(getattr(m, "sharpe", 0.0), 3),
        "max_drawdown": round(getattr(m, "max_drawdown", 0.0), 2),
        **bull,
    }


def _score(params, spy, vix, use_unblock):
    cm = _bull_f8_unblock_patch() if use_unblock else contextlib.nullcontext()
    with cm:
        return score_candidate(params, spy, vix)


def main() -> None:
    today = dt.date.today()
    out_path = ROOT / "analysis" / "recommendations" / f"f8-bull-vix-unblock-ab-{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    params = _real_fills_params()

    print("=" * 78)
    print("F8 BULL-VIX GATE RE-VALIDATION (CURRENT ENGINE: real fills + managed exits)")
    print(f"  Block:  bull entry needs VIX < 17.20 OR vix_falling")
    print(f"  A/B:    BASELINE (block ON)  vs  UNBLOCKED (drop F8 on bull path)")
    print(f"  Fills:  use_real_fills = {params['use_real_fills']}  (C1 authority)")
    print(f"  Output: {out_path}")
    print("=" * 78)

    # --- Anchor window (J source-of-truth: anchor-no-regression on the BEAR trades) ---
    anchor_start, anchor_end = dt.date(2026, 4, 28), dt.date(2026, 5, 8)
    print(f"\nLoading anchor data ({anchor_start} -> {anchor_end})...")
    spy_a, vix_a = runner.load_data(anchor_start, anchor_end)

    print("\n--- J-EDGE: BASELINE (F8 block ON) ---")
    base_score = _score(params, spy_a, vix_a, use_unblock=False)
    print_score_card(base_score)

    print("\n--- J-EDGE: UNBLOCKED (F8 dropped on bull path) ---")
    unb_score = _score(params, spy_a, vix_a, use_unblock=True)
    print_score_card(unb_score)

    # Anchor-no-regression: J's trades are all bearish puts; unblocking a BULL
    # gate must not change them. edge_capture must be identical (delta == 0).
    edge_delta = round(unb_score["edge_capture"] - base_score["edge_capture"], 2)
    anchor_no_regression = abs(edge_delta) < 1.0
    op16_floor_pass = unb_score["edge_capture"] >= J_TOTAL_WINNERS * 0.50
    print(f"\n  anchor edge_capture: baseline=${base_score['edge_capture']:.0f} "
          f"-> unblocked=${unb_score['edge_capture']:.0f}  (delta ${edge_delta:+.0f})")
    print(f"  anchor-no-regression (|delta|<1): {'PASS' if anchor_no_regression else 'FAIL'}")
    print(f"  OP-16 floor (>= $771): {'PASS' if op16_floor_pass else 'FAIL'}")

    # --- Full-window A/B: does the F8 BULL block still earn its keep? ---
    full_start, full_end = dt.date(2025, 1, 2), dt.date(2026, 6, 18)
    print(f"\nLoading full window ({full_start} -> {full_end})...")
    spy_f, vix_f = runner.load_data(full_start, full_end)
    print(f"  SPY {len(spy_f)} bars | VIX {len(vix_f)} bars")

    windows = {
        "train_2025":     (dt.date(2025, 1, 2),  dt.date(2025, 12, 31)),
        "oos_2026":       (dt.date(2026, 1, 2),  dt.date(2026, 6, 18)),
        "full":           (full_start,            full_end),
    }
    # Quarter sub-windows for OP-19 stability (the bars J's source-of-truth lives in).
    quarters = {
        "2025Q1": (dt.date(2025, 1, 2),  dt.date(2025, 3, 31)),
        "2025Q2": (dt.date(2025, 4, 1),  dt.date(2025, 6, 30)),
        "2025Q3": (dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
        "2025Q4": (dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
        "2026Q1": (dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
        "2026Q2": (dt.date(2026, 4, 1),  dt.date(2026, 6, 18)),
    }

    ab = {}
    for name, (s, e) in {**windows, **quarters}.items():
        base = _run_window(params, s, e, spy_f, vix_f, use_unblock=False)
        unb = _run_window(params, s, e, spy_f, vix_f, use_unblock=True)
        # Delta attributable to the unblock = the NEW bull trades it admits.
        delta_bull_n = unb["n_bull"] - base["n_bull"]
        delta_bull_pnl = round(unb["bull_pnl"] - base["bull_pnl"], 2)
        ab[name] = {
            "baseline": base, "unblocked": unb,
            "delta_bull_n": delta_bull_n,
            "delta_bull_pnl": delta_bull_pnl,
            "delta_total_pnl": round(unb["total_pnl"] - base["total_pnl"], 2),
        }
        print(f"  {name:<10} bull n {base['n_bull']:3d}->{unb['n_bull']:3d} "
              f"({delta_bull_n:+d})  bull$ {base['bull_pnl']:+8.0f}->{unb['bull_pnl']:+8.0f} "
              f"(d${delta_bull_pnl:+.0f})  blockNewBull$={-delta_bull_pnl:+.0f}")

    # --- Verdict logic ---
    # The block "earns its keep" if the trades it SUPPRESSES are net losers,
    # i.e. admitting them (unblock) makes bull P&L WORSE: delta_bull_pnl < 0.
    # It is STALE if the suppressed trades are net winners: delta_bull_pnl > 0.
    full_delta = ab["full"]["delta_bull_pnl"]
    oos_delta = ab["oos_2026"]["delta_bull_pnl"]
    train_delta = ab["train_2025"]["delta_bull_pnl"]
    n_suppressed_full = ab["full"]["delta_bull_n"]

    pos_quarters = sum(1 for q in quarters if ab[q]["delta_bull_pnl"] > 0)
    neg_quarters = sum(1 for q in quarters if ab[q]["delta_bull_pnl"] < 0)

    if n_suppressed_full == 0:
        recommendation = "REVALIDATE_INCONCLUSIVE"
        still_justified = None
        reason = ("Block suppresses ZERO bull trades across full history under the "
                  "current engine (other gates already exclude every F8-failing bull bar). "
                  "F8 is redundant here — cannot earn its keep, but cannot prove harm either.")
    elif full_delta > 0 and oos_delta >= 0:
        # Suppressed trades are net WINNERS -> block now suppresses winners -> STALE.
        recommendation = "UNBLOCK"
        still_justified = False
        reason = (f"Block suppresses {n_suppressed_full} bull trades worth ${full_delta:+.0f} "
                  f"(OOS ${oos_delta:+.0f}) under real fills + managed exits. The new exit "
                  f"structure turned the formerly-losing OTM bull config into a net winner; "
                  f"F8 now blocks winners. STALE.")
    elif full_delta < 0:
        recommendation = "KEEP"
        still_justified = True
        reason = (f"Block suppresses {n_suppressed_full} bull trades that are net LOSERS "
                  f"(${full_delta:+.0f} full, ${oos_delta:+.0f} OOS). Admitting them degrades "
                  f"P&L -> F8 still earns its keep under the current engine.")
    else:
        recommendation = "REVALIDATE_INCONCLUSIVE"
        still_justified = None
        reason = (f"Mixed: full ${full_delta:+.0f} but OOS ${oos_delta:+.0f}. Sign unstable "
                  f"across IS/OOS -> not a clean keep or unblock. Hold the block.")

    print("\n" + "=" * 78)
    print(f"VERDICT: {recommendation}")
    print(f"  {reason}")
    print(f"  full delta_bull_pnl=${full_delta:+.0f}  oos=${oos_delta:+.0f}  train=${train_delta:+.0f}")
    print(f"  quarters: {pos_quarters} positive / {neg_quarters} negative (of 6)")
    print(f"  anchor-no-regression={anchor_no_regression}  op16_floor={op16_floor_pass}")
    print("=" * 78)

    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "block": "VIX_BULL_LOW_THRESHOLD (filter 8) — bull entry needs VIX<17.20 OR vix_falling",
        "account": "safe",
        "engine": "CURRENT: use_real_fills=True + V15 managed exits (chart-stop-primary, -50% cap, chandelier, tp1=0.667/runner=2.5)",
        "recommendation": recommendation,
        "still_justified": still_justified,
        "reason": reason,
        "anchor_no_regression": anchor_no_regression,
        "op16_floor_pass": op16_floor_pass,
        "anchor_edge_capture": {
            "baseline": base_score["edge_capture"],
            "unblocked": unb_score["edge_capture"],
            "delta": edge_delta,
        },
        "full_delta_bull_pnl": full_delta,
        "oos_delta_bull_pnl": oos_delta,
        "train_delta_bull_pnl": train_delta,
        "n_suppressed_bull_full": n_suppressed_full,
        "quarters_positive": pos_quarters,
        "quarters_negative": neg_quarters,
        "ab": ab,
        "param_diff_to_unblock": "filters.py evaluate_bullish_setup filter 8: remove the VIX<17.20-OR-falling block on the bull path (or expose params.json key 'disable_bull_filter_8': true / 'block_bull_vix_low': false). No params.json knob exists today — F8 is hardcoded.",
    }
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
