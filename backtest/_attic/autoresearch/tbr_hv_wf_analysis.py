"""TBR_HIGH_VOL ITM-2 walk-forward analysis.

Runs IS (2025-01-01 to 2025-09-30) + OOS (2025-10-01 to 2026-05-22) for the
best combo found in tbr_hv_itm_sweep.py: strike_offset=-2 (ITM-2), stop=-35%.

Computes WF ratio = OOS_exp / IS_exp. Gate: WF ratio >= 0.50.

Also runs the full 9-combo sweep on IS to show the IS landscape.

CLI::

    python -m autoresearch.tbr_hv_wf_analysis
    python -m autoresearch.tbr_hv_wf_analysis --out analysis/recommendations/tbr_hv_wf.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.tbr_hv_real_fills_val import (
    DEFAULT_COMBO,
    _run_tbr_hv_real_fills,
    _report,
)

IS_START  = dt.date(2025, 1, 1)
IS_END    = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END   = dt.date(2026, 5, 22)

# Best combo from itm sweep
BEST_COMBO = replace(DEFAULT_COMBO, strike_offset=-2, stop_premium_pct=-0.35)


def run_wf(out_path: Path | None = None) -> dict:
    print("=== TBR_HIGH_VOL ITM-2 Walk-Forward Analysis ===")
    print(f"IS : {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print(f"Combo: strike_offset=-2 (ITM-2), stop_premium_pct=-35%")
    print()

    print(f"Loading IS data ({IS_START} to {IS_END})...")
    is_trades = _run_tbr_hv_real_fills(IS_START, IS_END, combo=BEST_COMBO)
    is_summary = _report(is_trades, f"IS  ({IS_START} to {IS_END})  ITM-2 stop=-35%")

    print()
    print(f"Loading OOS data ({OOS_START} to {OOS_END})...")
    oos_trades = _run_tbr_hv_real_fills(OOS_START, OOS_END, combo=BEST_COMBO)
    oos_summary = _report(oos_trades, f"OOS ({OOS_START} to {OOS_END})  ITM-2 stop=-35%")

    # WF ratio
    is_exp  = is_summary.get("exp",  0.0)
    oos_exp = oos_summary.get("exp", 0.0)
    if is_exp == 0.0:
        wf_ratio = float("inf") if oos_exp > 0 else 0.0
    else:
        wf_ratio = oos_exp / is_exp

    wf_pass = wf_ratio >= 0.50 and oos_summary.get("passes", False)

    print()
    print("=" * 60)
    print(f"WALK-FORWARD RESULT")
    print(f"  IS  exp/obs = ${is_exp:+.2f}  n={is_summary.get('n', 0)}  WR={is_summary.get('wr', 0):.1%}")
    print(f"  OOS exp/obs = ${oos_exp:+.2f}  n={oos_summary.get('n', 0)}  WR={oos_summary.get('wr', 0):.1%}")
    print(f"  WF ratio    = {wf_ratio:.3f}  (gate >= 0.50)")
    wf_label = "PASS" if wf_pass else "FAIL"
    print(f"  Gate (ratio>=0.50 AND OOS WR>=55%): {wf_label}")
    print()

    result = {
        "run_date": dt.date.today().isoformat(),
        "combo": {"strike_offset": -2, "stop_premium_pct": -0.35},
        "is_period": {"start": str(IS_START), "end": str(IS_END), **is_summary},
        "oos_period": {"start": str(OOS_START), "end": str(OOS_END), **oos_summary},
        "wf_ratio": round(wf_ratio, 4) if wf_ratio != float("inf") else None,
        "wf_pass": wf_pass,
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(
                {"result": result, "is_trades": is_trades, "oos_trades": oos_trades},
                f, indent=2, default=str,
            )
        print(f"Results written to {out_path}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TBR high-vol ITM-2 walk-forward analysis")
    parser.add_argument("--out", default=None, help="Write JSON results to this path")
    args = parser.parse_args()

    result = run_wf(
        out_path=Path(args.out) if args.out else None,
    )
    return 0 if result.get("wf_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
