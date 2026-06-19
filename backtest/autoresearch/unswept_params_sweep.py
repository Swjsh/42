"""
Sweep the three previously-unswept _FILTER_CONST_MAP params against the corrected baseline:
  - ribbon_spread_min_cents  (default=30)
  - ribbon_flip_lookback_bars (default=3)
  - confluence_tolerance_dollars (default=0.30)

Corrected baseline (post-Rank-31 + L117 fix):
  IS n=239 pnl=-$3,942.61 / OOS n=15 pnl=+$2,659.00
  Params: use_real_fills=True, bear_stop=-0.20, tp1_qty_fraction=0.667,
          time_stop_minutes_before_close=20, midday_trendline_gate=True,
          no_trade_window=None

IS  window : 2025-01-02 -> 2026-05-07
OOS window : 2026-05-08 -> 2026-05-22
"""
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backtest.lib.orchestrator import run_backtest

# Production baseline params (post-Rank-31 + L117 fix)
_BASE = dict(
    use_real_fills=True,
    bear_stop=-0.20,
    tp1_qty_fraction=0.667,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    entry_no_trade_window_et=None,
)

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

KNOWN_IS_BASELINE  = (-3942.61, 239)
KNOWN_OOS_BASELINE = ( 2659.00,  15)

WF_GATE = 0.70


def _run(overrides: dict, *, is_run: bool) -> tuple[float, int]:
    params = {**_BASE, **overrides}
    start = IS_START if is_run else OOS_START
    end   = IS_END   if is_run else OOS_END
    result = run_backtest(
        start_date=start,
        end_date=end,
        params_overrides=params,
    )
    fills = result.get("fills", [])
    pnl = sum(f.get("net_pnl", 0.0) for f in fills)
    return pnl, len(fills)


def sweep(param: str, values: list, description: str) -> None:
    print(f"\n{'='*70}")
    print(f"SWEEP: {param}  ({description})")
    print(f"{'='*70}")
    print(f"{'Value':>10}  {'IS n':>6}  {'IS pnl':>10}  {'IS delta':>10}  "
          f"{'OOS n':>6}  {'OOS pnl':>10}  {'OOS delta':>10}  {'WF':>7}  Verdict")
    print(f"{'-'*115}")

    base_is_pnl, base_is_n  = KNOWN_IS_BASELINE
    base_oos_pnl, base_oos_n = KNOWN_OOS_BASELINE

    for v in values:
        overrides = {param: v}
        is_pnl, is_n   = _run(overrides, is_run=True)
        oos_pnl, oos_n = _run(overrides, is_run=False)

        is_delta  = is_pnl  - base_is_pnl
        oos_delta = oos_pnl - base_oos_pnl

        marker = " <-- DEFAULT" if v is None else ""
        if is_delta > 0 and oos_delta > 0:
            wf = oos_delta / is_delta if is_delta != 0 else float("nan")
            if wf >= WF_GATE:
                verdict = f"PASS WF={wf:.3f}"
            else:
                verdict = f"WF={wf:.3f} FAIL"
        elif is_delta <= 0 and oos_delta <= 0:
            verdict = "BOTH_WORSE"
        else:
            verdict = "IS+OOS_OPPOSING"

        print(f"{str(v):>10}  {is_n:>6}  {is_pnl:>10.2f}  {is_delta:>+10.2f}  "
              f"{oos_n:>6}  {oos_pnl:>10.2f}  {oos_delta:>+10.2f}  "
              f"{'N/A':>7}  {verdict}{marker}")

    print()


def verify_liveness(param: str, values: list) -> None:
    """Quick dead-knob check: if all P&L identical → still dead."""
    print(f"\n[LIVENESS CHECK] {param}  values={values}")
    pnls = []
    for v in values:
        pnl, n = _run({param: v}, is_run=True)
        pnls.append(pnl)
        print(f"  {param}={v}: IS pnl={pnl:.2f} n={n}")
    spread = max(pnls) - min(pnls)
    if spread < 50:
        print(f"  *** DEAD KNOB DETECTED: spread={spread:.2f} < $50 ***")
    else:
        print(f"  LIVE: spread={spread:.2f}")


if __name__ == "__main__":
    print("=" * 70)
    print("UNSWEPT PARAMS SWEEP — corrected baseline IS=-$3,942.61 / OOS=+$2,659.00")
    print("Params: urf=True bear=-0.20 tp1_frac=0.667 time_stop=20min midday=True")
    print("=" * 70)

    # ── 1. ribbon_spread_min_cents (default=30) ──────────────────────────────
    verify_liveness("ribbon_spread_min_cents", [10, 30, 60])
    sweep(
        "ribbon_spread_min_cents",
        [5, 10, 15, 20, 25, 30, 40, 50, 60, 80],
        "min ribbon spread for BEAR filter (cents); default=30",
    )

    # ── 2. ribbon_flip_lookback_bars (default=3) ─────────────────────────────
    verify_liveness("ribbon_flip_lookback_bars", [1, 3, 8])
    sweep(
        "ribbon_flip_lookback_bars",
        [1, 2, 3, 4, 5, 8, 12],
        "bars to look back for ribbon flip; default=3 (15 min)",
    )

    # ── 3. confluence_tolerance_dollars (default=0.30) ───────────────────────
    verify_liveness("confluence_tolerance_dollars", [0.10, 0.30, 0.80])
    sweep(
        "confluence_tolerance_dollars",
        [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00],
        "tolerance for multi-day confluence touch (dollars); default=$0.30",
    )

    print("\nSWEEP COMPLETE.")
