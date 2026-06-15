"""Walk-forward OOS validation for NAMED_LEVEL_WICK_BOUNCE (NLWB).

Split: train = 2025-01-02 to 2025-09-30 (9 months)
       test  = 2025-10-01 to 2026-05-15 (~7.5 months, held-out)

Addresses OP-20 disclosure 3: out-of-sample test required before promotion.

Runs the PDL relaxed variant (min_wick=8c, min_vol=1.0x, consol=0) and the
PDL calibrated variant (min_wick=8c, min_vol=1.2x, consol=1, range=0.30)
across both windows and reports:
  - WR in train vs test window
  - Guard status (loser-day fires) in test window
  - Monthly WR distribution in test window (L48 regime check)
  - Verdict: stable (WR within 10pp), degraded (10-20pp drop), or failed (>20pp drop)

Output: analysis/recommendations/nlwb_walk_forward.json

Usage:
  python backtest/autoresearch/nlwb_walk_forward.py
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch.named_level_bounce_scan import run_scan  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "nlwb_walk_forward.json"

# ── Window definitions ─────────────────────────────────────────────────────────
TRAIN_START = dt.date(2025, 1, 2)
TRAIN_END   = dt.date(2025, 9, 30)
TEST_START  = dt.date(2025, 10, 1)
TEST_END    = dt.date(2026, 5, 15)

# ── Variants to test ───────────────────────────────────────────────────────────
VARIANTS = [
    {
        "name": "pdl_relaxed",
        "description": "PDL, min_wick=8c, vol=1.0x, consol=0 — the highest-N variant",
        "kwargs": {
            "level_type": "pdl",
            "min_wick_below_cents": 8.0,
            "min_vol_mult": 1.0,
            "consol_bars": 0,
            "consol_range": 0.30,
        },
    },
    {
        "name": "pdl_calibrated",
        "description": "PDL, min_wick=8c, vol=1.2x, consol=1 — production watcher defaults",
        "kwargs": {
            "level_type": "pdl",
            "min_wick_below_cents": 8.0,
            "min_vol_mult": 1.2,
            "consol_bars": 1,
            "consol_range": 0.30,
        },
    },
    {
        "name": "round5_tight",
        "description": "Round-$5, min_wick=10c, vol=1.2x, consol=2 — round-level variant",
        "kwargs": {
            "level_type": "round5",
            "min_wick_below_cents": 10.0,
            "min_vol_mult": 1.2,
            "consol_bars": 2,
            "consol_range": 0.20,
        },
    },
]


def _stability_verdict(train_wr: float, test_wr: float) -> str:
    """Classify the OOS stability of the walk-forward split."""
    delta = train_wr - test_wr
    if abs(delta) <= 0.10:
        return "STABLE"
    elif delta <= 0.20:
        return "DEGRADED"
    else:
        return "FAILED"


def main() -> int:
    results: dict = {
        "generated_at": dt.datetime.now().isoformat(),
        "purpose": "Walk-forward OOS validation for NLWB (OP-20 disclosure 3)",
        "train_window": f"{TRAIN_START} to {TRAIN_END}",
        "test_window":  f"{TEST_START} to {TEST_END}",
        "variants": {},
    }

    overall_stable = True

    for var in VARIANTS:
        name = var["name"]
        kwargs = var["kwargs"]
        log.info("\n" + "=" * 60)
        log.info("Variant: %s", name)
        log.info("Description: %s", var["description"])

        # ── Train window ──────────────────────────────────────────────────────
        log.info("[TRAIN] %s to %s ...", TRAIN_START, TRAIN_END)
        train_result = run_scan(
            **kwargs,
            date_start=TRAIN_START,
            date_end=TRAIN_END,
        )
        train_s = train_result["summary"]
        train_wr = train_s["wr_overall"]
        train_n  = train_s["n_signals"]

        # ── Test window ───────────────────────────────────────────────────────
        log.info("[TEST]  %s to %s ...", TEST_START, TEST_END)
        test_result = run_scan(
            **kwargs,
            date_start=TEST_START,
            date_end=TEST_END,
        )
        test_s = test_result["summary"]
        test_wr = test_s["wr_overall"]
        test_n  = test_s["n_signals"]

        # ── Stability assessment ──────────────────────────────────────────────
        verdict = _stability_verdict(train_wr, test_wr)
        delta_pp = round((test_wr - train_wr) * 100, 1)

        # Guard check in test window (loser-day fires)
        test_guard = test_s["op16_guard_check"]["guard_pass"]
        test_guard_note = test_s["op16_guard_check"]["guard_note"]

        # Monthly distribution in test window (L48 regime check)
        test_monthly = test_s.get("monthly_distribution", {})
        test_months_below_45pct = [
            ym for ym, m in test_monthly.items()
            if m["n"] >= 3 and m["wr"] < 0.45
        ]

        stable_flag = (verdict != "FAILED" and test_guard and len(test_months_below_45pct) == 0)
        if not stable_flag:
            overall_stable = False

        log.info("  TRAIN: N=%d  WR=%.1f%%", train_n, train_wr * 100)
        log.info("  TEST:  N=%d  WR=%.1f%%  delta=%+.1fpp", test_n, test_wr * 100, delta_pp)
        log.info("  Verdict: %s  Guard: %s  Stable: %s",
                 verdict,
                 "PASS" if test_guard else "FAIL",
                 "YES" if stable_flag else "NO")

        results["variants"][name] = {
            "description": var["description"],
            "train": {
                "window": f"{TRAIN_START} to {TRAIN_END}",
                "n_signals": train_n,
                "wr_overall": train_wr,
                "wr_near_session_low": train_s["wr_near_session_low"],
                "wr_ribbon_favorable": train_s["wr_ribbon_favorable"],
                "wr_by_vix_regime": train_s["wr_by_vix_regime"],
                "monthly_distribution": train_s.get("monthly_distribution", {}),
                "op16_guard": train_s["op16_guard_check"],
            },
            "test": {
                "window": f"{TEST_START} to {TEST_END}",
                "n_signals": test_n,
                "wr_overall": test_wr,
                "wr_near_session_low": test_s["wr_near_session_low"],
                "wr_ribbon_favorable": test_s["wr_ribbon_favorable"],
                "wr_by_vix_regime": test_s["wr_by_vix_regime"],
                "monthly_distribution": test_monthly,
                "op16_guard": test_s["op16_guard_check"],
                "months_below_45pct_wr": test_months_below_45pct,
            },
            "comparison": {
                "train_wr": train_wr,
                "test_wr": test_wr,
                "delta_pp": delta_pp,
                "verdict": verdict,
                "test_guard_pass": test_guard,
                "test_guard_note": test_guard_note,
                "stable_for_promotion": stable_flag,
            },
        }

    # ── Overall conclusion ────────────────────────────────────────────────────
    results["overall"] = {
        "all_stable": overall_stable,
        "promotion_path": (
            "PROCEED to real-fills validation (simulator_real.py)" if overall_stable
            else "BLOCKED — OOS degradation detected, investigate before promotion"
        ),
        "notes": [
            "Walk-forward split validates in-sample WR doesn't degrade OOS.",
            "STABLE = WR delta < 10pp AND loser-day guard PASS AND no month < 45% WR (N>=3).",
            "After OOS + real-fills: accumulate 3+ live J confirmations before promotion.",
        ],
    }

    log.info("\n" + "=" * 60)
    log.info("OVERALL: all_stable=%s", overall_stable)
    log.info("Promotion path: %s", results["overall"]["promotion_path"])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    log.info("Results written to %s", OUT_JSON)
    return 0 if overall_stable else 1


if __name__ == "__main__":
    sys.exit(main())
