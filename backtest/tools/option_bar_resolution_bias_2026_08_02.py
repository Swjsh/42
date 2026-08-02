"""option_bar_resolution_bias_2026_08_02.py -- STEP 1 of the OPTION-BAR-RESOLUTION-BIAS
investigation (2026-08-02 overnight, INTEGRITY lane).

QUESTION: backtest/lib/option_pricing_real.py serves OPRA option bars at a silent-default
5-MINUTE resolution (backtest/tools/fetch_option_data.py hardcodes timeframe="5Min"). A stop
that is breached and recovers INSIDE a 5-minute bar is invisible at that resolution -- no stop
hit is recorded where a real 1-minute tick (and the live engine) would have taken one. This
script quantifies that bias, cheaply and generally, BEFORE deciding whether to re-run anything
expensive (per task instruction: establish materiality first, don't manufacture a crisis).

PRIOR EVIDENCE (tonight, level_target_exit_study.py / level-target-exit-2026-08-02.json): on
this SAME population (real fills, all 6 arms), the incumbent-shape harness-vs-live parity gap
was $3,637.85 at 5-min cached bars, shrinking to $1,920.40 once refetched at 1-min -- a
$1,717.45 swing attributable to resolution alone, root-caused exactly on SPY260709C00750000
(risky-3): the real position stopped out on a dip to $0.40 inside a 5-min bar whose own open
was $0.52, so the 5-min walk rode straight through the stop and posted a phantom gain. That
number was a byproduct of a different study (the level-target overlay's G8 parity check); this
script is the DEDICATED, ISOLATED measurement the task asks for -- same population, same
production decision core, ONLY resolution varies, with an explicit stop-hit count (not just an
aggregate parity gap).

METHOD: take the CANONICAL real-fills population (backtest/tools/level_target_exit_study.
build_population(), REUSED UNCHANGED -- OP-22 -- 129 positions, ALL_LIVE_ARMS, each joined to
its own REAL fired exit shape / stop_mode / trigger_level) and walk EVERY position TWICE
through the SAME production decision core (backtest/lib/exit_manager_walk.walk_exit_manager,
byte-identical both times) -- once on 5-minute option bars (lib.option_pricing_real.
load_contract_bars, the exact function named in tonight's defect), once on 1-minute option bars
(exit_shape_parity_study.fetch_option_bars, live REST, the SAME path the level-target-exit lane
proved out on this exact population tonight). The ONLY variable that changes between the two
walks is option-bar resolution -- entry price (REGISTERED, from the real decision log, not
derived from either bar source), exit shape, trigger level, stop mode, qty, strategy, and
time_stop_et are all held byte-identical. The 5-min SPY series (structure_stop's
last_closed_5m_close input) is also held identical in both walks -- structure_stop is 5-min-
native by v15.3 design (exit_manager_walk.py's own documented convention), not part of the
resolution variable under test here.

REPORTS: (1) how many positions' exit reclassifies from non-stop to stop-only-at-1-min (the
"invisible-at-5-min" stops) and the reverse (rare, reported for symmetry, not assumed away);
(2) the aggregate P&L delta (5-min total minus 1-min total) and its direction; (3) full
per-position detail for both stop-flip cohorts.

ANALYSIS ONLY. No trading-path file touched, no orders placed. 1-min bars persisted to
backtest/data/highres/{symbol}_1m_{date}.csv (existing, already-populated naming convention --
see GOAL-REPLAY-TODAY-GREEN.md iteration 3 / level_target_exit_study.py) so a re-run of this
script never re-fetches.

Run: backtest/.venv/Scripts/python.exe backtest/tools/option_bar_resolution_bias_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts",
           REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import level_target_exit_study as ltes                    # noqa: E402  (build_population -- reused unchanged)
from lib.option_pricing_real import load_contract_bars      # noqa: E402  (5-min disk cache -- the defect fn)
from exit_manager_walk import walk_exit_manager             # noqa: E402  (production decision core, unchanged)
from _option_bars_1min_cache import fetch_1min_cached, ET_OFFSET  # noqa: E402  (shared 1-min fetch+cache)

FIVEMIN_CACHE = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
OUT_JSON = REPO / "analysis" / "recommendations" / "option-bar-resolution-bias-2026-08-02.json"

TIME_STOP_ET = dt.time(15, 50)   # exit_manager.TIME_STOP_ET convention -- the LIVE default
STOP_STAGES = {"structure_stop", "premium_stop", "profit_lock_floor"}


def log(msg: str) -> None:
    print(f"[resbias] {msg}", flush=True)


def load_spy5() -> pd.DataFrame:
    df = pd.read_csv(FIVEMIN_CACHE)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
    return df


def bars_5min(symbol: str) -> Optional[pd.DataFrame]:
    """The exact defect path: lib.option_pricing_real.load_contract_bars -- silent 5-minute
    OPRA cache (backtest/data/options/{symbol}.csv)."""
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    df = df.copy()
    ts = df["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        df["timestamp_et"] = ts.dt.tz_localize(None)
    return df


def classify(stages: set[str]) -> str:
    return "stop" if stages & STOP_STAGES else "non_stop"


def walk(pos: dict, opt_df: pd.DataFrame, spy5: pd.DataFrame) -> dict:
    result = walk_exit_manager(
        symbol=pos["symbol"], side=pos["side"], entry_time_et=pos["_entry_ts_et_naive"],
        entry_premium=pos["entry_price_registered"], qty=pos["qty"], exit_shape=pos["exit_shape"],
        structure_stop_enabled=pos["structure_stop_enabled"], trigger_level=pos["trigger_level"],
        strategy=pos["strategy"], time_stop_et=TIME_STOP_ET, opt_df=opt_df,
        ribbon_tick_df=None, five_min_spy_df=spy5,
    )
    pnl = sum((leg.fill_price - pos["entry_price_fill"]) * leg.qty * 100.0 for leg in result.legs)
    stages = {leg.stage for leg in result.legs}
    return {"pnl": round(pnl, 2), "stages": sorted(stages), "classification": classify(stages),
            "exit_reason": result.exit_reason, "resolved": result.resolved,
            "n_ticks": result.n_ticks_walked}


def main() -> int:
    log("building canonical real-fills population (level_target_exit_study.build_population, reused unchanged)")
    positions, excluded = ltes.build_population()
    log(f"population: {len(positions)} positions, excluded={excluded}")

    spy5 = load_spy5()

    rows = []
    n_5min_missing = 0
    n_1min_missing = 0
    for i, raw_pos in enumerate(positions):
        entry_dt_utc = dt.datetime.fromisoformat(raw_pos["entry_ts_utc"].replace("Z", "+00:00"))
        entry_et = entry_dt_utc.astimezone(ET_OFFSET).replace(tzinfo=None)
        pos = dict(raw_pos)
        pos["_entry_ts_et_naive"] = entry_et

        df5 = bars_5min(pos["symbol"])
        df1, src1 = fetch_1min_cached(pos["symbol"], pos["date_et"])

        row = {"arm": pos["arm"], "symbol": pos["symbol"], "date_et": pos["date_et"],
               "side": pos["side"], "qty": pos["qty"], "actual_exit_pnl": pos["actual_exit_pnl"],
               "structure_stop_enabled": pos["structure_stop_enabled"],
               "resolution_1min_source": src1}

        row["walk_5min"] = None if (df5 is None or df5.empty) else walk(pos, df5, spy5)
        if row["walk_5min"] is None:
            n_5min_missing += 1
        row["walk_1min"] = None if (df1 is None or df1.empty) else walk(pos, df1, spy5)
        if row["walk_1min"] is None:
            n_1min_missing += 1

        rows.append(row)
        if (i + 1) % 20 == 0:
            log(f"  ...{i + 1}/{len(positions)}")

    both = [r for r in rows if r["walk_5min"] is not None and r["walk_1min"] is not None]
    log(f"positions with BOTH resolutions available: {len(both)}/{len(rows)} "
        f"(5min missing={n_5min_missing}, 1min missing={n_1min_missing})")

    stop_only_1min = [r for r in both
                       if r["walk_1min"]["classification"] == "stop"
                       and r["walk_5min"]["classification"] == "non_stop"]
    stop_only_5min = [r for r in both
                       if r["walk_5min"]["classification"] == "stop"
                       and r["walk_1min"]["classification"] == "non_stop"]

    total_5min = round(sum(r["walk_5min"]["pnl"] for r in both), 2)
    total_1min = round(sum(r["walk_1min"]["pnl"] for r in both), 2)
    gap = round(total_5min - total_1min, 2)
    actual_total = round(sum(r["actual_exit_pnl"] for r in both), 2)

    out = {
        "_doc": "STEP 1 of OPTION-BAR-RESOLUTION-BIAS-2026-08-02: quantifies the 5-min-vs-1-min "
                "option-bar resolution bias on the canonical real-fills population, walked through "
                "the SAME production exit_manager decision core both times (only resolution varies).",
        "generated_at": dt.datetime.now().isoformat(),
        "population_source": "level_target_exit_study.build_population() (REUSED unchanged, OP-22)",
        "n_positions_total": len(rows),
        "n_positions_both_resolutions": len(both),
        "n_5min_missing": n_5min_missing, "n_1min_missing": n_1min_missing,
        "stop_stages_definition": sorted(STOP_STAGES),
        "n_stop_only_at_1min": len(stop_only_1min),
        "n_stop_only_at_5min": len(stop_only_5min),
        "aggregate_pnl_5min": total_5min,
        "aggregate_pnl_1min": total_1min,
        "actual_real_fills_total": actual_total,
        "gap_5min_minus_1min": gap,
        "direction": ("5-min FLATTERS (overstates P&L vs honest 1-min)" if gap > 0
                      else ("5-min UNDERSTATES P&L vs honest 1-min" if gap < 0 else "no difference")),
        "stop_only_at_1min_detail": [
            {"arm": r["arm"], "symbol": r["symbol"], "date_et": r["date_et"],
             "pnl_5min": r["walk_5min"]["pnl"], "pnl_1min": r["walk_1min"]["pnl"],
             "delta_5min_minus_1min": round(r["walk_5min"]["pnl"] - r["walk_1min"]["pnl"], 2),
             "stages_5min": r["walk_5min"]["stages"], "stages_1min": r["walk_1min"]["stages"]}
            for r in stop_only_1min
        ],
        "stop_only_at_5min_detail": [
            {"arm": r["arm"], "symbol": r["symbol"], "date_et": r["date_et"],
             "pnl_5min": r["walk_5min"]["pnl"], "pnl_1min": r["walk_1min"]["pnl"],
             "delta_5min_minus_1min": round(r["walk_5min"]["pnl"] - r["walk_1min"]["pnl"], 2)}
            for r in stop_only_5min
        ],
        "all_rows": rows,
        "disclosures": [
            "Population = level_target_exit_study.build_population() UNCHANGED (129 real-fills "
            "positions, ALL_LIVE_ARMS, each joined to its own REAL fired exit_shape/stop_mode/"
            "trigger_level) -- the canonical real-fills population several other studies in this "
            "codebase already reuse (OP-22, not re-derived here).",
            "Both walks use exit_manager_walk.walk_exit_manager (the production decision core) "
            "UNCHANGED -- entry price (REGISTERED, from the real decision log), exit shape, "
            "trigger level, stop mode, qty, strategy, and time_stop_et (15:50 ET, exit_manager."
            "TIME_STOP_ET) are IDENTICAL between the two walks. The ONLY variable is the option-"
            "bar resolution fed as opt_df.",
            "5-min bars: lib.option_pricing_real.load_contract_bars(symbol) -- the exact function "
            "named in the defect (backtest/data/options/*.csv, silently 5-minute).",
            "1-min bars: exit_shape_parity_study.fetch_option_bars(symbol, date_et) -- live REST, "
            "the SAME path the level-target-exit lane (2026-08-02) proved out on this exact "
            "population tonight; persisted to backtest/data/highres/ (existing naming convention) "
            "so a re-run of this script does not re-fetch.",
            "stop_stages = {structure_stop, premium_stop, profit_lock_floor} -- the loss/"
            "protective-stop-realizing exit_manager stages (v15.3 CHART-STOP-PRIMARY doctrine's "
            "own 'chart-level stop / premium catastrophe cap' vocabulary); tp1/runner_target/"
            "trail/be_stop/time_stop/ribbon_flip are profit-taking or rule-exits, not counted as "
            "stops for this classification -- a disclosed, not silently picked, definition.",
            "SPY 5-min series (structure_stop's last_closed_5m_close input) is IDENTICAL in both "
            "walks -- structure_stop is 5-min-native by v15.3 design (exit_manager_walk.py's own "
            "documented convention), not part of the resolution variable under test here; only the "
            "OPTION premium bar resolution varies.",
            "n_5min_missing / n_1min_missing positions are EXCLUDED from the aggregate (never "
            "imputed) -- both counts disclosed, not silently dropped (C7).",
            "actual_real_fills_total is reported for context only (same real-fills anchor number "
            "other studies in this codebase cite) -- this script's own comparison is 5-min-walk "
            "vs 1-min-walk, not walk-vs-actual (that parity question is level_target_exit_study's "
            "G8, already answered tonight: gap shrank $3,637.85 -> $1,920.40 swapping resolution).",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"n_stop_only_at_1min={len(stop_only_1min)} n_stop_only_at_5min={len(stop_only_5min)} "
        f"aggregate_5min=${total_5min} aggregate_1min=${total_1min} gap=${gap} "
        f"direction={out['direction']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
