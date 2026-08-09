"""/fable-too-good audit of the matrix's winning cell: ATR_STOP.

The 96-cell run made ATR_STOP the dominant exit column by a wide margin -- ~$95/trade against
~$16/trade for the as-shipped control, and it won on every non-ladder entry row in BOTH
populations. That is exactly the shape that demands an artifact hunt BEFORE it is reported as an
edge, and the hunt found two structural problems with the column as built:

  1. LOOK-AHEAD. `_atr_stop_col` derives the stop width from `opt_df[:6]` where opt_df is
     `_opt_bars_from(...)` = bars with ts >= entry. So the stop is computed from the realized
     high/low of the first 6 bars AFTER entry, and `walk_exit_manager` then tests that stop
     against those same bars. A trade that whipsaws right after entry gets a large ATR -> a wide
     stop -> it is NOT stopped on the whipsaw; a quiet trade gets a tight one. The rule hands the
     widest stops precisely to the trades that would otherwise have been stopped out. That
     manufactures expectancy out of hindsight (C6).

  2. MODE CONFOUND. Control is `stop_mode="structure"` (so walk_exit_manager runs with
     structure_stop_enabled=True). `_atr_stop_col` returns `stop_mode="premium"`, which turns
     structure stops OFF. The column therefore changes two things at once, and "dynamic stop
     beats static" cannot be separated from "no structure stop beats structure stop".

  (A third suspicion -- that the column silently drops `profit_lock_arm_scope` -- was checked and
  is NOT a real confound: exit_manager defaults that key to ARM_SCOPE_POST_TP1, the same value
  control carries. Recorded so the next reader does not re-hunt it.)

This script runs four columns over the SAME entry row through the SAME twin walker, so the
walker is held constant and each difference is attributable:

  TWIN_CONTROL   control static shape -> parity check against sl.walk_lane's own CONTROL cell.
                 If this does not reproduce it, the twin walker itself is a confound and the
                 whole ATR_STOP column was a cross-engine comparison (the SIM-EXIT-SHAPE-PARITY
                 scar) rather than an exit-rule comparison.
  ATR_LOOKAHEAD  the column exactly as it ran -- must reproduce the headline number.
  ATR_CLEAN      identical formula, but ATR measured on the 6 bars STRICTLY BEFORE entry.
                 This is the honest version of J's dynamic stop.
  PREM_STATIC_20 premium-mode static -20% (structure off) -- isolates the mode confound, so the
                 ATR_CLEAN vs PREM_STATIC_20 gap is the dynamic-width effect ALONE.
"""

from __future__ import annotations

import json
import sys
import time as _time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "automation" / "state" / "fleet"),
           str(ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import entry_exit_matrix_2026_08_09 as eem  # noqa: E402
import score_ladder_replay_2026_08_07 as sl  # noqa: E402
import engine_fullhist_replay as efr  # noqa: E402

OUT = ROOT / "analysis" / "deep-research" / "ENTRY-EXIT-MATRIX-ATR-AUDIT-2026-08-09.json"

ATR_BARS = 6
ATR_MULT = 2.0
ATR_FLOOR, ATR_CAP = 0.15, 0.60
FALLBACK_PCT = -0.20


def _premium_shape(pct: float) -> dict:
    """Same field set _atr_stop_col emits, with an explicit stop width."""
    return {"premium_stop_pct": round(pct, 4),
            "tp1_premium_pct": eem.BASE_EXIT["tp1_premium_pct"],
            "tp1_qty_fraction": eem.BASE_EXIT["tp1_qty_fraction"],
            "profit_lock_mode": "trailing",
            "runner_target_pct": eem.BASE_EXIT["runner_target_pct"],
            "trail_pct": eem.BASE_EXIT["trail_pct"],
            "profit_lock_arm_pct": eem.BASE_EXIT["profit_lock_arm_pct"],
            "stop_mode": "premium",
            "catastrophe_stop_pct": eem.BASE_EXIT["catastrophe_stop_pct"]}


def _atr_pct(ranges: list[float], entry_premium: float) -> float:
    if len(ranges) < 2 or entry_premium <= 0:
        return FALLBACK_PCT
    atr = sum(ranges) / len(ranges)
    return -min(ATR_CAP, max(ATR_FLOOR, (ATR_MULT * atr) / entry_premium))


def col_twin_control(position, opt_df_from_entry) -> dict:
    return dict(eem.BASE_EXIT)


def col_atr_lookahead(position, opt_df_from_entry) -> dict:
    """Byte-equivalent to the shipped _atr_stop_col: ATR from bars AT/AFTER entry."""
    sample = opt_df_from_entry[:ATR_BARS] if len(opt_df_from_entry) >= 2 else opt_df_from_entry
    ranges = [float(b["high"]) - float(b["low"]) for b in sample]
    return _premium_shape(_atr_pct(ranges, position["entry_premium"]))


def col_atr_clean(position, opt_df_from_entry) -> dict:
    """Honest version: ATR from the 6 bars STRICTLY BEFORE entry. No hindsight."""
    df, entry_time = position.get("opt_df"), position.get("entry_time_et")
    ranges: list[float] = []
    if df is not None and entry_time is not None:
        ts = df["timestamp_et"]
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_localize(None)
        prior = df.loc[(ts < pd.Timestamp(entry_time)).values].tail(ATR_BARS)
        ranges = [float(r["high"]) - float(r["low"]) for _, r in prior.iterrows()]
    return _premium_shape(_atr_pct(ranges, position["entry_premium"]))


def col_prem_static_20(position, opt_df_from_entry) -> dict:
    return _premium_shape(FALLBACK_PCT)


COLUMNS = {"TWIN_CONTROL": col_twin_control,
           "ATR_LOOKAHEAD": col_atr_lookahead,
           "ATR_CLEAN": col_atr_clean,
           "PREM_STATIC_20": col_prem_static_20}


def main() -> int:
    t0 = _time.time()
    print("[atr-audit] loading population (same loader/window as the matrix run)", flush=True)
    spy_raw, vix_df = eem.load_extended_data()
    spy_rth = sl.build_rth_frame(spy_raw)
    r, bear_by_idx, bull_by_idx = sl.run_backtest_with_full_capture(
        spy_raw, vix_df, start_date=eem.FULL_START, end_date=eem.FULL_END, **sl.SAFE_BASE_LIVE_NOW)
    ribbon_lookup = efr.build_ribbon_lookup(spy_raw)
    rows = eem.build_rows_pop_a(r.trades, bear_by_idx, bull_by_idx, spy_rth)
    blk = rows["CONTROL"]
    print(f"[atr-audit]   CONTROL row: {len(blk['binary'])} binary trades "
          f"({_time.time()-t0:.0f}s)", flush=True)

    results = {}
    for name, fn in COLUMNS.items():
        t1 = _time.time()
        lane = eem.walk_lane_dynamic_shape(blk["rung"], blk["candidates"], blk["binary"],
                                           spy_rth, ribbon_lookup, fn)
        b = eem.battery(lane["trades"])
        b["n_excluded"] = len(lane["excluded"])
        b["suppressed_binary"] = lane["suppressed_binary"]
        results[name] = b
        print(f"[atr-audit] {name:15s} n={b['n']:4d} exp=${b['expectancy']:>8.2f} "
              f"total=${b['total']:>11,.2f} wr={b['wr']} p={b['bootstrap_p_mean_gt0']} "
              f"({_time.time()-t1:.0f}s)", flush=True)

    shipped = json.loads((ROOT / "analysis" / "deep-research" /
                          "ENTRY-EXIT-MATRIX-2026-08-09.json").read_text(encoding="utf-8"))
    ship_ctl = shipped["population_a"]["cells"]["CONTROL__CONTROL"]
    ship_atr = shipped["population_a"]["cells"]["CONTROL__ATR_STOP"]

    tc, al = results["TWIN_CONTROL"], results["ATR_LOOKAHEAD"]
    parity_delta = (tc["expectancy"] or 0) - (ship_ctl["expectancy"] or 0)
    verdict = {
        "walker_parity": {
            "twin_control_expectancy": tc["expectancy"], "twin_control_n": tc["n"],
            "sl_walk_lane_control_expectancy": ship_ctl["expectancy"],
            "sl_walk_lane_control_n": ship_ctl["n"],
            "delta_per_trade": round(parity_delta, 2),
            "faithful": abs(parity_delta) < 0.01 and tc["n"] == ship_ctl["n"],
        },
        "lookahead_reproduced": {
            "audit_expectancy": al["expectancy"], "shipped_expectancy": ship_atr["expectancy"],
            "matches": abs((al["expectancy"] or 0) - (ship_atr["expectancy"] or 0)) < 0.01,
        },
        "lookahead_inflation_per_trade": round((results["ATR_LOOKAHEAD"]["expectancy"] or 0)
                                               - (results["ATR_CLEAN"]["expectancy"] or 0), 2),
        "dynamic_width_effect_alone_per_trade": round((results["ATR_CLEAN"]["expectancy"] or 0)
                                                      - (results["PREM_STATIC_20"]["expectancy"] or 0), 2),
        "mode_effect_alone_per_trade": round((results["PREM_STATIC_20"]["expectancy"] or 0)
                                             - (tc["expectancy"] or 0), 2),
    }
    OUT.write_text(json.dumps({"columns": results, "verdict": verdict,
                               "runtime_seconds": round(_time.time() - t0, 1)},
                              indent=1, default=str), encoding="utf-8")
    print(f"\n[atr-audit] {json.dumps(verdict, indent=1)}")
    print(f"[atr-audit] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
