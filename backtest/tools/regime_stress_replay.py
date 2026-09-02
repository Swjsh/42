"""regime_stress_replay -- what the engine's protections actually DO on a high-volatility day.

Runner for `analysis/recommendations/prereg-regime-stress-replay-2026-09-02.json`
(work-order §2b). SIM-ONLY, MEASUREMENT-ONLY: places nothing, arms nothing, changes no params.

IT READS THE FROZEN DAY LIST; IT DOES NOT DERIVE ONE. The prereg's `no_repick_clause` freezes
the population rule, the window and the 24 enumerated days. Re-deriving them here would let a
later edit to the rule silently re-cut the sample after seeing P&L -- the exact metric-picking
the prereg exists to prevent. If the prereg is missing, this aborts rather than falling back to
a rule of its own.

WHY THE FULL WINDOW IS REPLAYED AND THEN FILTERED, rather than replaying 24 isolated days. The
engine carries cross-day state -- prior-day levels, level memory, recency gates -- so a day run
in isolation would face a stripped context that never existed. Running 2024-08-01..2026-07-22
once and keeping the trades whose ENTRY DATE is a stress day is both simpler and strictly more
faithful. Cost: the run is long. Measured elapsed is written into the scorecard.

REUSED, NOT REBUILT: the entry cascade (`lib.orchestrator.run_backtest` under
`engine_fullhist_replay.SAFE_BASE_LIVE`) and the exit walk (`lib.exit_manager_walk`, driving the
REAL `strategies.py#RIBBON_RIDE.exit` shape) are the same two layers `engine_fullhist_replay`
uses, so a stress day is scored by exactly the machinery that scores an ordinary one. The
SIM-EXIT-SHAPE-PARITY trap that module documents is routed around identically.

DATA. SPY comes from the WIDE file (2024-01-18..2026-07-22) because the population starts
2024-08-05, which the standard 2025-01-01 file does not reach. VIX has no single file spanning
it, so two are concatenated -- disclosed in the scorecard, since a silent join is exactly the
provenance seam this repo has been bitten by (2026-07-14).

Run:
    backtest\\.venv\\Scripts\\python.exe backtest\\tools\\regime_stress_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path

BT = Path(__file__).resolve().parents[1]
ROOT = BT.parent
for _p in (str(BT), str(BT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- SAFE_BASE_LIVE, ribbon lookup, helpers
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- entry_date, classify_tier
import strategies as fleet_strategies  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402 (same as efr)

PREREG = ROOT / "analysis" / "recommendations" / "prereg-regime-stress-replay-2026-09-02.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "regime-stress-replay-2026-09-02.json"

DATA = BT / "data"
SPY_FILE = DATA / "spy_5m_2024-01-18_2026-07-22.csv"
VIX_FILES = (DATA / "vix_5m_2024-08-01_2024-12-31.csv",
             DATA / "vix_5m_2025-01-01_2026-07-22.csv")

# The April 2025 tariff block, pre-registered as ONE macro event rather than nine observations.
CONCENTRATION_BLOCK = (dt.date(2025, 4, 3), dt.date(2025, 4, 21))


def log(msg: str) -> None:
    print(f"[regime_stress] {msg}", flush=True)


def load_prereg() -> dict:
    if not PREREG.exists():
        raise SystemExit(f"FATAL: prereg absent at {PREREG}. This runner will not invent a "
                         f"population -- the frozen day list IS the study's integrity.")
    return json.loads(PREREG.read_text(encoding="utf-8"))


def frozen_days(prereg: dict) -> list:
    pop = prereg["population_rule_frozen"]
    days = [dt.date.fromisoformat(d) for d in pop["enumerated_days"]]
    assert len(days) == int(pop["enumerated_days_n"]), (
        "the prereg's own day count disagrees with its list -- refusing to run on an "
        "inconsistent population"
    )
    return days


def assert_single_time_frame(raw: "pd.Series", label: str) -> None:
    """Refuse a bar file that mixes UTC-offset conventions. FAIL LOUD, never normalise silently.

    FOUND 2026-09-02 while wiring this runner, and it is why the study is blocked rather than
    reported. `spy_5m_2024-01-18_2026-07-22.csv` is a MERGE of two differently-framed sources:

        2024-12-18 09:30:00-0500   <- DST-aware. Winter session starts 09:30 ET. CORRECT.
        2025-01-03 10:30:00-04:00  <- fixed -04:00 all year. Winter session starts 10:30. WRONG.

    The second frame is a whole hour late in winter. Proof it is a shift and not extended hours:
    2025-01-03 holds exactly 78 bars -- 6.5h, precisely one RTH session -- labelled 10:30..16:55
    instead of 09:30..15:55. The two offset FORMATS (-0500 vs -04:00) are the seam between the
    producers.

    Why this must abort rather than be quietly corrected: every gate in the entry cascade is
    wall-clock (09:35 entry floor, 15:00 ceiling, 15:40 time stop), so a +1h winter shift moves
    which bars are eligible. Normalising here would produce numbers that disagree with every
    prior study built on the same file WITHOUT anyone knowing which was right -- and this repo
    spent 2026-09-02 retiring exactly one such unreproducible result. The data is the thing to
    fix; a study is not the place to paper over it.

    Same class as the standing DST-frame lesson (naive joins = winter look-ahead).
    """
    offsets = {str(x)[-6:] if ":" in str(x)[-6:] else str(x)[-5:] for x in raw}
    normalised = {o.replace(":", "") for o in offsets}
    if len(normalised) <= 1:
        return
    raise SystemExit(
        f"FATAL: {label} mixes UTC-offset conventions {sorted(offsets)}. This file contains "
        f"more than one time frame (see assert_single_time_frame's docstring: the 2025+ portion "
        f"labels winter bars a full hour late). Refusing to emit a scorecard from bars whose "
        f"wall clock is not one consistent thing -- fix the data, then re-run. Filed as "
        f"SPY-BAR-FILE-MIXES-TWO-TIME-FRAMES in automation/overnight/queue.md."
    )


def load_bars() -> "tuple[pd.DataFrame, pd.DataFrame]":
    log(f"SPY: {SPY_FILE.name}")
    spy = pd.read_csv(SPY_FILE)
    assert_single_time_frame(spy["timestamp_et"].astype(str), SPY_FILE.name)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    frames = []
    for f in VIX_FILES:
        log(f"VIX: {f.name}")
        frames.append(pd.read_csv(f))
    vix = pd.concat(frames, ignore_index=True)
    if "timestamp_et" in vix.columns:
        vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
        vix = vix.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et")
        vix = vix.reset_index(drop=True)
    return spy, vix


def replay(spy_df, vix_df, start: dt.date, end: dt.date) -> list:
    log("computing ribbon lookup (exit-layer ribbon_flip_back fidelity)")
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    log(f"run_backtest {start}..{end} -- the SAME entry cascade an ordinary day gets")
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **efr.SAFE_BASE_LIVE)
    log(f"  entries={len(r.trades)} in {time.time()-t0:.0f}s (dollar_pnl DISCARDED -- wrong shape)")

    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    rows, n_no_opra, n_no_spy = [], 0, 0
    t1 = time.time()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy += 1
            continue
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=efr.naive_dt(t.entry_time_et),
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=shape,
            structure_stop_enabled=True,
            trigger_level=float(t.rejection_level) if t.rejection_level else None,
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "side": t.side, "setup": t.setup,
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
        })
    log(f"  exits re-derived in {time.time()-t1:.0f}s -- replayed={len(rows)} "
        f"no_opra={n_no_opra} no_spy_day={n_no_spy}")
    return rows, n_no_opra, n_no_spy


def _agg(rows: list) -> dict:
    """Q1/Q2/Q5: mechanism mix, side split, worst case."""
    if not rows:
        return {"n": 0}
    pnl = [r["dollar_pnl"] for r in rows]
    by_day = {}
    for r in rows:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["dollar_pnl"]
    return {
        "n": len(rows),
        "total_pnl": round(sum(pnl), 2),
        "exit_reason_mix": dict(Counter(r["exit_reason"] for r in rows).most_common()),
        "stop_mode_mix": dict(Counter(r["resolved_stop_mode"] for r in rows).most_common()),
        "by_side": {s: {"n": sum(1 for r in rows if r["side"] == s),
                        "pnl": round(sum(r["dollar_pnl"] for r in rows if r["side"] == s), 2)}
                    for s in sorted({r["side"] for r in rows})},
        "worst_day": (min(by_day.items(), key=lambda kv: kv[1]) if by_day else None),
        "days_with_entries": len(by_day),
    }


def main() -> int:
    t_start = time.time()
    prereg = load_prereg()
    days = frozen_days(prereg)
    log(f"frozen population: {len(days)} stress days, {days[0]} .. {days[-1]} (READ, not derived)")

    spy_df, vix_df = load_bars()
    window = prereg["population_rule_frozen"]["data_window"].split("..")
    start = dt.date.fromisoformat(window[0].strip())
    end = dt.date.fromisoformat(window[1].strip())

    rows, n_no_opra, n_no_spy = replay(spy_df, vix_df, start, end)
    stress = {d.isoformat() for d in days}
    hit = [r for r in rows if r["date"] in stress]
    log(f"of {len(rows)} replayed entries, {len(hit)} fall on a frozen stress day")

    lo, hi = CONCENTRATION_BLOCK
    in_block = [r for r in hit if lo <= dt.date.fromisoformat(r["date"]) <= hi]
    ex_block = [r for r in hit if not (lo <= dt.date.fromisoformat(r["date"]) <= hi)]

    out = {
        "id": "REGIME-STRESS-REPLAY-2026-09-02",
        "measures_prereg": prereg["rule_id"],
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "label": "SIM-ONLY. Measurement only -- arms nothing, gates nothing, changes no params.",
        "population": {
            "days_frozen": len(days), "read_from_prereg": True, "derived_here": False,
            "window": f"{start}..{end}",
        },
        "participation_Q6": {
            "stress_days_with_at_least_one_entry": len({r["date"] for r in hit}),
            "of_frozen_days": len(days),
            "note": ("A stress-day study where the engine mostly sits out is a finding about the "
                     "GATES, not the exits, and must not be read as an exit result."),
        },
        "all_stress_days": _agg(hit),
        "STRATIFIED_excluding_april_2025_block": _agg(ex_block),
        "STRATIFIED_april_2025_block_only": _agg(in_block),
        "exclusions": {"n_no_opra_contract": n_no_opra, "n_no_spy_day": n_no_spy,
                       "note": "excluded and COUNTED, never silently dropped or modelled"},
        "disclosures": prereg["disclosures_that_bound_every_number_this_study_will_produce"],
        "elapsed_s": round(time.time() - t_start, 1),
        "rows": hit,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    a = out["all_stress_days"]
    log(f"SUMMARY n={a.get('n')} pnl={a.get('total_pnl')} "
        f"exit_mix={a.get('exit_reason_mix')} days={a.get('days_with_entries')}/{len(days)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
