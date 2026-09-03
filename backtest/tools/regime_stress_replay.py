"""regime_stress_replay -- what the engine's protections actually DO on a high-volatility day.

Runner for `analysis/recommendations/prereg-regime-stress-replay-2026-09-02.json`
(work-order §2b). SIM-ONLY, MEASUREMENT-ONLY: places nothing, arms nothing, changes no params.

IT READS THE FROZEN DAY LIST; IT DOES NOT DERIVE ONE. The prereg's `no_repick_clause` freezes
the population rule, the window and the 24 enumerated days. Re-deriving them here would let a
later edit to the rule silently re-cut the sample after seeing P&L -- the exact metric-picking
the prereg exists to prevent. If the prereg is missing, this aborts rather than falling back to
a rule of its own. This module DOES compute, per frozen day, which pre-registered STRATUM it
falls in (drop-day cc<=-2% vs range-day range>=3% & cc>-2%) -- that is stratifying an already-
frozen list, not deriving membership in it.

WHY THE FULL WINDOW IS REPLAYED AND THEN FILTERED, rather than replaying 24 isolated days. The
engine carries cross-day state -- prior-day levels, level memory, recency gates -- so a day run
in isolation would face a stripped context that never existed. Running 2024-08-01..2026-07-22
once and keeping the trades whose ENTRY DATE is a stress day is both simpler and strictly more
faithful. Cost: the run is long. Measured elapsed is written into the scorecard.

REUSED, NOT REBUILT: the entry cascade (`lib.orchestrator.run_backtest` under
`engine_fullhist_replay.SAFE_BASE_LIVE`) and the exit walk (`lib.exit_manager_walk`, driving the
REAL `strategies.py#RIBBON_RIDE.exit` shape, which is itself the REAL production
`automation/state/fleet/exit_manager.py` decision engine -- read-only import, never edited) are
the same two layers `engine_fullhist_replay` uses, so a stress day is scored by exactly the
machinery that scores an ordinary one. The SIM-EXIT-SHAPE-PARITY trap that module documents is
routed around identically. THE TIGHT LADDER (min_contracts 3 / max_contracts_per_entry 5 /
max_position_dollars 1000) is layered on top via `lib.risk_gate.cap_entry_qty` -- the SAME
function both live money paths call (heartbeat_core.py:2740, fleet_executor.py:1331) -- applied
to each orchestrator-proposed trade's qty/premium. DISCLOSED GAP: the pre-ladder proposed qty
comes from `lib.orchestrator`'s own linear risk-pct sizing, not `fleet_executor._qty_for`'s
tiered sizing table (a materially larger, separate reuse that `engine_fullhist_replay.py` itself
does not attempt either); this module answers "does the ladder further clamp what the entry
cascade already proposed on a stress day", not "is the entry cascade's base sizing identical to
live's tiered table".

DATA. SPY comes from the WIDE file (2024-01-18..2026-07-22) because the population starts
2024-08-05, which the standard 2025-01-01 file does not reach. VIX has no single file spanning
it, so two are concatenated -- disclosed in the scorecard, since a silent join is exactly the
provenance seam this repo has been bitten by (2026-07-14).

UNBLOCKED 2026-09-02 (was ABORTING on write). The wide SPY file and the 2025+ VIX file mix two
timestamp conventions -- filed as SPY-BAR-FILE-MIXES-TWO-TIME-FRAMES in
automation/overnight/queue.md, full analysis there. THE FIX IS NOT A NEW FILE OR A NEW PARSER:
`backtest/lib/et_frame.py` already exists for exactly this ("MIGRATION DISCIPLINE" in its own
docstring), is already used this way by `build_day_archetypes.py` and
`bull_gate_f5class_requal_2026_08_01.py`, and its guard suite
(`backtest/tests/test_et_frame_guards.py`, 8/8 passing) already pins both conventions on a known
winter day. Writing a second, parallel `_etfixed.csv` sibling file would duplicate that
machinery and create a THIRD convention for the next reader to discover -- exactly what the
Obsidian-brain doctrine (append to the existing structure, never fork a parallel one) rules out.
So this runner now parses both SPY and VIX through `et_frame.parse_timestamp_et(col,
frame="et-v2")` (the DST-correct path: parse each row's own attached offset to a UTC instant,
then re-localize to America/New_York -- correct regardless of which of the file's two label
conventions a given row uses, because the UTC instant was never wrong, only the label). The old
`assert_single_time_frame` hard-abort is gone; `_frame_shift_report` below performs the same
"before/after" measurement (per-day bar count and first/last bar under a naive label-strip vs.
under et-v2) the coordinator asked for, and writes it into the scorecard's `frame_fix` block
rather than raising, and a lighter post-parse sanity check (`_assert_rth_sane`) still aborts if
the parse produces a structurally broken frame. `engine_fullhist_replay.py` itself still uses
the unfixed wall-v1 parse for its own SPY/VIX files (a SEPARATE, larger change against a
published anchor -- n=190/191 -- explicitly deferred, not silently re-run here).

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
from lib import et_frame  # noqa: E402 -- DST-correct timestamp frame (see module docstring)
from lib.risk_gate import cap_entry_qty  # noqa: E402 -- READ-ONLY import; tight-ladder qty cap,
                                          # the SAME function both live money paths call

PREREG = ROOT / "analysis" / "recommendations" / "prereg-regime-stress-replay-2026-09-02.json"
OUT_DIR = ROOT / "analysis" / "regime-stress"
OUT_JSON = OUT_DIR / "REGIME-STRESS-2026-09-02.json"
OUT_MD = OUT_DIR / "REGIME-STRESS-2026-09-02.md"

DATA = BT / "data"
SPY_FILE = DATA / "spy_5m_2024-01-18_2026-07-22.csv"
VIX_FILES = (DATA / "vix_5m_2024-08-01_2024-12-31.csv",
             DATA / "vix_5m_2025-01-01_2026-07-22.csv")

# The April 2025 tariff block, pre-registered as ONE macro event rather than nine observations.
CONCENTRATION_BLOCK = (dt.date(2025, 4, 3), dt.date(2025, 4, 21))

# Tight ladder (PREREG-TIGHT-LADDER-2026-08-28 S2), copied verbatim from
# automation/state/params.json (a config-freeze file this study reads but never imports or
# writes). Pinned against the live file by test_regime_stress_replay_2026_09_02.py so a future
# ladder change cannot silently drift this study out of sync with the file it is measuring.
LADDER_PARAMS = {"min_contracts": 3, "max_contracts_per_entry": 5, "max_position_dollars": 1000}

# Rule 5 per-day kill thresholds, and the equity they are evaluated against here (broker-verified
# 2026-08-18, CLAUDE.md "Account context"). Q5 reports worst-day $ P&L as a % of THIS baseline --
# an "arm-equivalent" proxy, not each arm's actual same-day equity (which drifts trade to trade).
KILL_SWITCH_PCT = {"Gamma-Safe": -0.30, "Gamma-Bold": -0.50}
ARM_EQUIVALENT_EQUITY = {"Gamma-Safe": 5266.38, "Gamma-Bold": 5048.40}


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


# ================================================================================================ #
# FRAME FIX -- et_frame et-v2, replacing the old hard-abort (see module docstring)
# ================================================================================================ #
def _frame_shift_report(raw: "pd.Series", days: list) -> dict:
    """Before/after diagnostic for the 24 frozen days: naive label-strip (what a bare
    `pd.to_datetime` on this file's timestamp_et column silently does -- the OLD convention
    every prior study on this file used) vs. `et_frame.parse_timestamp_et(frame="et-v2")` (DST-
    correct). Never aborts -- et-v2 is proven correct regardless of which of the file's two
    label conventions a given row carries (backtest/tests/test_et_frame_guards.py, 8/8 passing);
    this function only MEASURES and reports the delta so the fix is visible, not silent."""
    naive = pd.to_datetime(raw.str.slice(0, 19))
    fixed = et_frame.parse_timestamp_et(raw, frame="et-v2")
    naive_date = naive.dt.strftime("%Y-%m-%d")
    fixed_date = fixed.dt.strftime("%Y-%m-%d")
    out = {}
    for d in days:
        dstr = d.isoformat()
        m_fixed = fixed_date == dstr
        n_fixed = int(m_fixed.sum())
        if n_fixed == 0:
            out[dstr] = {"n_bars_et_v2": 0, "shifted_vs_naive_label": None}
            continue
        m_naive = naive_date == dstr
        n_naive = int(m_naive.sum())
        first_fixed = fixed.loc[m_fixed].min()
        last_fixed = fixed.loc[m_fixed].max()
        first_naive = naive.loc[m_naive].min() if n_naive else None
        shifted = bool(n_naive != n_fixed or (first_naive is not None and first_naive != first_fixed))
        out[dstr] = {
            "n_bars_et_v2": n_fixed,
            "n_bars_naive_label": n_naive,
            "first_bar_et_v2": first_fixed.strftime("%H:%M"),
            "last_bar_et_v2": last_fixed.strftime("%H:%M"),
            "first_bar_naive_label": first_naive.strftime("%H:%M") if first_naive is not None else None,
            "shifted_vs_naive_label": shifted,
        }
    n_shifted = sum(1 for v in out.values() if v.get("shifted_vs_naive_label"))
    log(f"frame fix: {n_shifted}/{len(days)} frozen days had a naive-label winter shift; "
        f"corrected via et_frame.parse_timestamp_et(frame='et-v2')")
    return {
        "method": "et_frame.parse_timestamp_et(frame='et-v2')",
        "n_frozen_days_shifted": n_shifted,
        "of_frozen_days": len(days),
        "per_day": out,
    }


def _assert_rth_sane(df: "pd.DataFrame", label: str, days: list) -> None:
    """Post-parse sanity check -- NOT the old raw-offset hard-abort. Fails loud only if the
    et-v2 parse produced a structurally broken frame (more than half the frozen days have ZERO
    RTH 09:30-16:00 bars), which would mean something new and unexplained is wrong -- the known
    winter-label defect SHIFTS bars by an hour, it does not delete them, so this is a different
    failure class and must not be silently swallowed."""
    ts = df["timestamp_et"]
    rth = df.loc[(ts.dt.time >= dt.time(9, 30)) & (ts.dt.time <= dt.time(16, 0))]
    rth_dates = set(rth["timestamp_et"].dt.date)
    n_zero = sum(1 for d in days if d not in rth_dates)
    if n_zero > len(days) // 2:
        raise SystemExit(
            f"FATAL: {label} -- {n_zero}/{len(days)} frozen days have ZERO RTH bars after "
            f"et_frame et-v2 parsing. That is not the known winter-label defect (which shifts "
            f"bars by an hour, it does not delete them) -- refusing to emit a scorecard from a "
            f"frame this broken."
        )


def load_bars(days: list) -> "tuple[pd.DataFrame, pd.DataFrame, dict]":
    log(f"SPY: {SPY_FILE.name}")
    spy = pd.read_csv(SPY_FILE)
    spy_raw = spy["timestamp_et"].astype(str)
    spy_frame_report = _frame_shift_report(spy_raw, days)
    spy["timestamp_et"] = et_frame.parse_timestamp_et(spy_raw, frame="et-v2")
    _assert_rth_sane(spy, SPY_FILE.name, days)

    frames = []
    vix_frame_reports = {}
    for f in VIX_FILES:
        log(f"VIX: {f.name}")
        vdf = pd.read_csv(f)
        vraw = vdf["timestamp_et"].astype(str)
        vix_frame_reports[f.name] = _frame_shift_report(vraw, days)
        vdf["timestamp_et"] = et_frame.parse_timestamp_et(vraw, frame="et-v2")
        frames.append(vdf)
    vix = pd.concat(frames, ignore_index=True)
    vix = vix.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et")
    vix = vix.reset_index(drop=True)

    frame_report = {"spy": spy_frame_report, "vix": vix_frame_reports}
    return spy, vix, frame_report


# ================================================================================================ #
# STRATIFICATION -- classify each FROZEN day (never derive membership), from et-v2 SPY bars
# ================================================================================================ #
def daily_ohlc_rth(spy_df: "pd.DataFrame") -> "pd.DataFrame":
    ts = spy_df["timestamp_et"]
    rth = spy_df.loc[(ts.dt.time >= dt.time(9, 30)) & (ts.dt.time <= dt.time(16, 0))].copy()
    rth["date"] = rth["timestamp_et"].dt.date
    g = rth.groupby("date").agg(open=("open", "first"), high=("high", "max"),
                                low=("low", "min"), close=("close", "last")).sort_index()
    return g


def classify_strata(daily: "pd.DataFrame", days: list) -> dict:
    """cc<=-2% (drop-day) vs range>=3% & cc>-2% (range-day) -- STRATIFYING the frozen list,
    never deriving membership in it. A day can be neither (e.g. it qualified on the
    open-to-close screen the prereg computed but did not select on) -- reported honestly as
    such rather than forced into one bucket."""
    dates = list(daily.index)
    out = {}
    for d in days:
        if d not in dates:
            out[d.isoformat()] = {"cc_pct": None, "range_pct": None,
                                   "is_drop_day": None, "is_range_day": None,
                                   "note": "no RTH bars for this day in the SPY file"}
            continue
        i = dates.index(d)
        close = float(daily.loc[d, "close"])
        high = float(daily.loc[d, "high"])
        low = float(daily.loc[d, "low"])
        if i == 0:
            out[d.isoformat()] = {"cc_pct": None, "range_pct": round((high - low) / close * 100, 3),
                                   "is_drop_day": None, "is_range_day": None,
                                   "note": "no prior trading day in the loaded window for cc%"}
            continue
        prior_close = float(daily.iloc[i - 1]["close"])
        cc_pct = (close - prior_close) / prior_close * 100
        range_pct = (high - low) / close * 100
        is_drop = cc_pct <= -2.0
        is_range = (range_pct >= 3.0) and not is_drop
        out[d.isoformat()] = {"cc_pct": round(cc_pct, 3), "range_pct": round(range_pct, 3),
                               "is_drop_day": is_drop, "is_range_day": is_range}
    return out


def _stratification_caveat(prereg: dict, strata: dict) -> dict:
    """HONEST DISCLOSURE, found while wiring the stratification (2026-09-02). This module
    recomputes each FROZEN day's own cc%/range% from `backtest/data/spy_5m_2024-01-18_2026-07-
    22.csv` (et-v2 corrected) purely to STRATIFY the already-frozen list -- membership itself is
    never re-derived (no_repick_clause). That recomputation does NOT reproduce the prereg's own
    `subset_counts_frozen_now` (16 cc<=-2%, 15 range>=3% over the full candidate window): this
    module's data source, re-aggregated the same way, finds only 13 cc<=-2% and 10 range>=3%
    among the 24 frozen days, and 5 of the 24 (2026-02-05, 2026-03-23, 2026-03-31, 2026-04-14,
    2026-04-24) satisfy NEITHER threshold at all under this source. Only ONE of those five
    (2026-02-05) is also a frame-shifted day (see frame_fix) -- the other four are not winter-
    label cases, so the frame bug does not explain the gap. The likely cause is that the
    prereg's own population derivation used a different SPY source (e.g. true daily-bar closes
    from a canonical EOD feed, not this file's 5-min-bar RTH aggregation) -- that source was not
    re-derivable within this runner's scope. CONSEQUENCE: the drop-day/range-day split below is
    a BEST-EFFORT, INDEPENDENTLY-SOURCED stratification, not a reproduction of the prereg's own
    membership math, and is labelled UNVERIFIED against that math. The 5 unclassified days are
    excluded from BOTH the drop-day and range-day strata (not forced into either) but remain
    fully included in every non-stratified number (Q1, Q6, worst-case, etc)."""
    neither = [d for d, s in strata.items()
              if s.get("cc_pct") is not None and not s["is_drop_day"] and not s["is_range_day"]]
    return {
        "n_neither": len(neither),
        "days_satisfying_neither_recomputed_threshold": neither,
        "recomputed_drop_day_count": sum(1 for s in strata.values() if s.get("is_drop_day")),
        "prereg_stated_close_to_close_le_neg2pct": (
            prereg["population_rule_frozen"]["subset_counts_frozen_now"]["close_to_close_le_-2pct"]),
        "recomputed_range_day_count_exclusive_of_drop": sum(
            1 for s in strata.values() if s.get("is_range_day")),
        "prereg_stated_intraday_range_ge_3pct": (
            prereg["population_rule_frozen"]["subset_counts_frozen_now"]["intraday_range_ge_3pct"]),
        "verdict": "UNVERIFIED -- this module's stratification does not reproduce the prereg's "
                   "own subset counts; see this function's docstring for the disclosed gap.",
    }


# ================================================================================================ #
# REPLAY -- entry cascade (unchanged) + tight-ladder qty cap (NEW) + exit walk (unchanged)
# ================================================================================================ #
def replay(spy_df, vix_df, start: dt.date, end: dt.date) -> dict:
    log("computing ribbon lookup (exit-layer ribbon_flip_back fidelity)")
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    log(f"run_backtest {start}..{end} -- the SAME entry cascade an ordinary day gets")
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **efr.SAFE_BASE_LIVE)
    log(f"  entries={len(r.trades)} in {time.time()-t0:.0f}s (dollar_pnl DISCARDED -- wrong shape)")

    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    rows, ladder_skips, data_missing = [], [], []
    n_no_opra = n_no_spy = 0
    t1 = time.time()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            # DATA_MISSING (per work-order): counted AND labelled by date, never silently
            # folded into "no entry that day" -- a day whose only proposal was excluded for a
            # missing OPRA contract is a DATA gap, not a GATES finding, and Q6 must not conflate
            # the two.
            data_missing.append({"date": edate.isoformat(), "side": t.side, "setup": t.setup,
                                 "symbol": symbol, "reason": "DATA_MISSING_no_opra_contract"})
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy += 1
            data_missing.append({"date": edate.isoformat(), "side": t.side, "setup": t.setup,
                                 "symbol": symbol, "reason": "DATA_MISSING_no_spy_bars"})
            continue

        # TIGHT LADDER (NEW): clamp the orchestrator's proposed qty exactly as
        # lib.risk_gate.cap_entry_qty does on both live money paths, BEFORE the exit walk sees a
        # qty at all -- so P&L, worst-day, and Q4 all reflect what the ladder actually permits.
        cap = cap_entry_qty(proposed_qty=int(t.qty), premium=float(t.entry_premium),
                            params=LADDER_PARAMS)
        if cap["skip"]:
            ladder_skips.append({
                "date": edate.isoformat(), "side": t.side, "setup": t.setup,
                "proposed_qty": int(t.qty), "entry_premium": round(float(t.entry_premium), 4),
                "reason": cap["reason"],
            })
            continue
        ladder_qty = int(cap["qty"])

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=efr.naive_dt(t.entry_time_et),
            entry_premium=float(t.entry_premium), qty=ladder_qty, exit_shape=shape,
            structure_stop_enabled=True,
            trigger_level=float(t.rejection_level) if t.rejection_level else None,
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        leg_stages = [leg.stage for leg in (res.legs or [])]
        rows.append({
            "date": edate.isoformat(), "side": t.side, "setup": t.setup,
            "symbol": symbol,
            "qty_proposed": int(t.qty), "qty_ladder": ladder_qty,
            "capped_by_contracts": bool(cap["capped_by_contracts"]),
            "capped_by_dollars": bool(cap["capped_by_dollars"]),
            "entry_premium": round(float(t.entry_premium), 4),
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "leg_stages": leg_stages,
            "final_stage": leg_stages[-1] if leg_stages else None,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
        })
    log(f"  exits re-derived in {time.time()-t1:.0f}s -- replayed={len(rows)} "
        f"ladder_skips={len(ladder_skips)} no_opra={n_no_opra} no_spy_day={n_no_spy}")
    return {"rows": rows, "ladder_skips": ladder_skips, "data_missing": data_missing,
            "n_no_opra": n_no_opra, "n_no_spy": n_no_spy}


# ================================================================================================ #
# AGGREGATION -- Q1 (mix), Q2 (side), Q3 (cap-binding), Q4 (ladder), Q5 (worst-case)
# ================================================================================================ #
def _agg(rows: list) -> dict:
    """Q1/Q2/Q5: mechanism mix, side split, worst case."""
    if not rows:
        return {"n": 0}
    pnl = [r["dollar_pnl"] for r in rows]
    by_day: dict = {}
    for r in rows:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["dollar_pnl"]
    worst_day = min(by_day.items(), key=lambda kv: kv[1]) if by_day else None
    return {
        "n": len(rows),
        "total_pnl": round(sum(pnl), 2),
        "final_exit_stage_mix": dict(Counter(r["final_stage"] for r in rows).most_common()),
        "all_leg_stage_mix": dict(Counter(s for r in rows for s in r["leg_stages"]).most_common()),
        "stop_mode_mix": dict(Counter(r["resolved_stop_mode"] for r in rows).most_common()),
        "by_side": {s: {"n": sum(1 for r in rows if r["side"] == s),
                        "pnl": round(sum(r["dollar_pnl"] for r in rows if r["side"] == s), 2)}
                    for s in sorted({r["side"] for r in rows})},
        "worst_day": worst_day,
        "worst_day_vs_kill_switch": _worst_day_vs_kill(worst_day),
        "worst_single_trade_pnl": (min(pnl) if pnl else None),
        "days_with_entries": len(by_day),
    }


def _worst_day_vs_kill(worst_day) -> dict:
    """Q5. WalkResult exposes no intrabar max-adverse-excursion field, so 'worst intraday
    drawdown' is reported as the worst SINGLE-DAY realized $ P&L against an arm-equivalent
    equity baseline -- a LOWER BOUND on true intrabar drawdown (a position can be underwater
    further intraday and still recover before the day's realized close), not an MAE curve.
    Disclosed rather than fabricated."""
    if worst_day is None:
        return {"note": "no entries -- kill-switch comparison not applicable"}
    _, dollars = worst_day
    out = {}
    for label, equity in ARM_EQUIVALENT_EQUITY.items():
        pct_of_equity = dollars / equity
        threshold = KILL_SWITCH_PCT[label]
        out[label] = {
            "worst_day_dollars": round(dollars, 2),
            "arm_equivalent_equity": equity,
            "pct_of_equity": round(pct_of_equity * 100, 2),
            "kill_switch_threshold_pct": round(threshold * 100, 1),
            "would_have_tripped_kill_switch": pct_of_equity <= threshold,
        }
    return out


def _cap_binding_Q3(rows: list) -> dict:
    """Q3: among STRUCTURE-mode trades (stop_mode=='structure', the only population where a
    chart/structure stop can even fire), how often is the FINAL exit stage 'premium_stop' (the
    -50% catastrophe cap, firing alone because no same-tick structure break existed) vs.
    'structure_stop' (the chart stop)? Per exit_manager.py's own documented tie-break, structure
    is checked FIRST on any tick where BOTH conditions land -- so 'premium_stop' here can only
    mean the catastrophe cap fired on a tick where structure did NOT also break, never a same-
    tick race the cap actually won."""
    structure_mode = [r for r in rows if r["resolved_stop_mode"] == "structure"]
    binding = [r for r in structure_mode if r["final_stage"] in ("premium_stop", "structure_stop")]
    cap_fires = [r for r in binding if r["final_stage"] == "premium_stop"]
    chart_fires = [r for r in binding if r["final_stage"] == "structure_stop"]
    return {
        "n_structure_mode_trades": len(structure_mode),
        "n_binding_exits_(cap_or_chart)": len(binding),
        "n_catastrophe_cap_fired": len(cap_fires),
        "n_chart_structure_stop_fired": len(chart_fires),
        "cap_binding_rate": (round(len(cap_fires) / len(binding), 4) if binding else None),
        "note": ("Denominator is exits that were EITHER the -50% catastrophe cap OR the chart "
                 "stop, restricted to structure-mode trades. tp1/runner/time-stop/profit-lock "
                 "exits are excluded from this rate by construction -- they are not the "
                 "invalidation-hierarchy question Q3 asks."),
    }


def _ladder_Q4(rows: list, ladder_skips: list) -> dict:
    """Q4: which of the ladder's two caps actually bound on a stress day, and does the flat
    $1,000 dollar cap bind before the 5-contract cap when premiums are elevated (the opposite
    of the current calm-regime ordering, per the prereg's framing)."""
    n = len(rows)
    n_dollars = sum(1 for r in rows if r["capped_by_dollars"])
    n_contracts = sum(1 for r in rows if r["capped_by_contracts"] and not r["capped_by_dollars"])
    n_both = sum(1 for r in rows if r["capped_by_contracts"] and r["capped_by_dollars"])
    n_uncapped = n - n_dollars - n_contracts if n else 0
    return {
        "n_trades_placed_under_ladder": n,
        "n_capped_by_dollars_(max_position_dollars_binds)": n_dollars,
        "n_capped_by_contracts_only_(max_contracts_per_entry_binds)": n_contracts,
        "n_capped_by_both_simultaneously": n_both,
        "n_uncapped_(min_contracts_never_touched_either_cap)": n_uncapped,
        "n_ladder_conflict_skips_(no_legal_qty_>=_min_contracts)": len(ladder_skips),
        "note": ("A trade is counted 'capped_by_dollars' whenever the flat $1,000 cap reduced "
                 "qty below what max_contracts_per_entry alone would have allowed -- this is "
                 "the direct answer to whether the dollar cap binds before the contract-count "
                 "cap on elevated stress-day premiums."),
    }


# ================================================================================================ #
# MAIN
# ================================================================================================ #
def main() -> int:
    t_start = time.time()
    prereg = load_prereg()
    days = frozen_days(prereg)
    log(f"frozen population: {len(days)} stress days, {days[0]} .. {days[-1]} (READ, not derived)")

    spy_df, vix_df, frame_report = load_bars(days)
    daily = daily_ohlc_rth(spy_df)
    strata = classify_strata(daily, days)
    strat_caveat = _stratification_caveat(prereg, strata)
    if strat_caveat["n_neither"]:
        log(f"STRATIFICATION CAVEAT: {strat_caveat['n_neither']}/{len(days)} frozen days satisfy "
            f"NEITHER recomputed threshold (cc<=-2% nor range>=3%) under this data source -- "
            f"see stratification_caveat in the output. Day list is NOT re-derived (no_repick_"
            f"clause honored); only the stratum LABEL for these days is uncertain.")

    window = prereg["population_rule_frozen"]["data_window"].split("..")
    start = dt.date.fromisoformat(window[0].strip())
    end = dt.date.fromisoformat(window[1].strip())

    replayed = replay(spy_df, vix_df, start, end)
    rows_all, ladder_skips = replayed["rows"], replayed["ladder_skips"]
    n_no_opra, n_no_spy = replayed["n_no_opra"], replayed["n_no_spy"]
    data_missing_all = replayed["data_missing"]

    stress = {d.isoformat() for d in days}
    hit = [r for r in rows_all if r["date"] in stress]
    data_missing_on_stress_days = [m for m in data_missing_all if m["date"] in stress]
    data_missing_days = sorted({m["date"] for m in data_missing_on_stress_days})
    log(f"of {len(rows_all)} replayed entries, {len(hit)} fall on a frozen stress day; "
        f"{len(data_missing_on_stress_days)} DATA_MISSING proposals on "
        f"{len(data_missing_days)} stress day(s)")

    lo, hi = CONCENTRATION_BLOCK
    in_block = [r for r in hit if lo <= dt.date.fromisoformat(r["date"]) <= hi]
    ex_block = [r for r in hit if not (lo <= dt.date.fromisoformat(r["date"]) <= hi)]

    drop_days = {d for d, s in strata.items() if s.get("is_drop_day")}
    range_days = {d for d, s in strata.items() if s.get("is_range_day")}
    drop_rows = [r for r in hit if r["date"] in drop_days]
    range_rows = [r for r in hit if r["date"] in range_days]
    bull_rows = [r for r in hit if r["side"] == "C"]
    bear_rows = [r for r in hit if r["side"] == "P"]

    participating_days = {r["date"] for r in hit}
    days_no_entry = [d.isoformat() for d in days if d.isoformat() not in participating_days]
    days_no_entry_gates_only = [d for d in days_no_entry if d not in data_missing_days]
    days_no_entry_data_missing = [d for d in days_no_entry if d in data_missing_days]

    out = {
        "id": "REGIME-STRESS-REPLAY-2026-09-02",
        "measures_prereg": prereg["rule_id"],
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "label": "SIM-ONLY. Measurement only -- arms nothing, gates nothing, changes no params.",
        "population": {
            "days_frozen": len(days), "read_from_prereg": True, "derived_here": False,
            "window": f"{start}..{end}",
        },
        "frame_fix": frame_report,
        "day_strata": strata,
        "stratification_caveat": strat_caveat,
        "participation_Q6": {
            "stress_days_with_at_least_one_ladder_placed_entry": len(participating_days),
            "of_frozen_days": len(days),
            "days_with_zero_entries": days_no_entry,
            "days_with_zero_entries_gates_only_(no_DATA_MISSING)": days_no_entry_gates_only,
            "days_with_zero_entries_and_a_DATA_MISSING_proposal": days_no_entry_data_missing,
            "note": ("A stress-day study where the engine mostly sits out is a finding about the "
                     "GATES, not the exits, and must not be read as an exit result. 'Entry' here "
                     "means a trade the ladder actually permitted (skip=False) -- a day whose "
                     "only proposal was a ladder-conflict skip counts as NO entry, honestly, "
                     "since the live engine would never have placed that order either. A day in "
                     "the DATA_MISSING sub-list had a real trigger fire but the resulting trade "
                     "was excluded for a missing OPRA contract or SPY bars, NEVER silently "
                     "dropped or modelled -- that day's zero is a DATA gap, not a GATES finding, "
                     "and must not be conflated with the gates-only zeros."),
        },
        "Q1_mechanism_mix_all_stress_days": _agg(hit),
        "Q2_side_split": {
            "bull_calls": _agg(bull_rows),
            "bear_puts": _agg(bear_rows),
        },
        "Q3_cap_binding_rate": _cap_binding_Q3(hit),
        "Q4_ladder_sizing": _ladder_Q4(hit, [s for s in ladder_skips if s["date"] in stress]),
        "Q5_worst_case": {
            "all_stress_days": _agg(hit)["worst_day_vs_kill_switch"],
            "worst_single_trade_pnl": _agg(hit)["worst_single_trade_pnl"],
        },
        "STRATIFIED_excluding_april_2025_block": _agg(ex_block),
        "STRATIFIED_april_2025_block_only": _agg(in_block),
        "STRATIFIED_drop_days_cc_le_neg2pct": _agg(drop_rows),
        "STRATIFIED_range_days_ge_3pct_ex_drop": _agg(range_rows),
        "exclusions": {
            "n_no_opra_contract": n_no_opra, "n_no_spy_day": n_no_spy,
            "n_data_missing_on_stress_days": len(data_missing_on_stress_days),
            "n_ladder_conflict_skips_all_window": len(ladder_skips),
            "n_ladder_conflict_skips_on_stress_days": len(
                [s for s in ladder_skips if s["date"] in stress]),
            "note": "excluded and COUNTED, never silently dropped or modelled",
        },
        "data_missing_rows_on_stress_days": data_missing_on_stress_days,
        "ladder_skip_rows_on_stress_days": [s for s in ladder_skips if s["date"] in stress],
        "disclosures": prereg["disclosures_that_bound_every_number_this_study_will_produce"],
        "elapsed_s": round(time.time() - t_start, 1),
        "rows": hit,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_md(out, days)
    log(f"wrote {OUT_MD}")

    a = out["Q1_mechanism_mix_all_stress_days"]
    log(f"SUMMARY n={a.get('n')} pnl={a.get('total_pnl')} "
        f"stage_mix={a.get('final_exit_stage_mix')} days={a.get('days_with_entries')}/{len(days)}")
    return 0


def write_md(out: dict, days: list) -> None:
    """Per the prereg + work order: the participation count (Q6) MUST lead, before any exit
    result -- a stress-day study where the engine mostly sits out is a gates finding, not an
    exits finding, and must not be buried under P&L."""
    q6 = out["participation_Q6"]
    lines = []
    lines.append("# REGIME-STRESS-2026-09-02")
    lines.append("")
    lines.append(out["label"])
    lines.append(f"Measures: `{out['measures_prereg']}`. Generated {out['generated_at_et']} ET.")
    lines.append("")
    lines.append("## Q6 PARTICIPATION (read this first)")
    lines.append("")
    lines.append(f"**{q6['stress_days_with_at_least_one_ladder_placed_entry']} of "
                 f"{q6['of_frozen_days']} frozen stress days produced at least one ladder-"
                 f"permitted entry.**")
    if q6["days_with_zero_entries"]:
        lines.append("")
        lines.append("Zero-entry days: " + ", ".join(q6["days_with_zero_entries"]))
    dm_days = q6.get("days_with_zero_entries_and_a_DATA_MISSING_proposal") or []
    lines.append("")
    lines.append(f"Of those, **{len(dm_days)} are DATA_MISSING** (a trigger fired but the trade "
                 f"was excluded for a missing OPRA contract/SPY bars, never dropped silently): "
                 + (", ".join(dm_days) if dm_days else "none"))
    lines.append("")
    lines.append(q6["note"])
    lines.append("")
    lines.append("## Frame fix (data provenance)")
    lines.append("")
    ff = out["frame_fix"]["spy"]
    lines.append(f"{ff['n_frozen_days_shifted']}/{ff['of_frozen_days']} frozen days had a "
                 f"naive-label winter shift in the SPY wide file, corrected via "
                 f"`{ff['method']}`. See `automation/overnight/queue.md` item "
                 f"SPY-BAR-FILE-MIXES-TWO-TIME-FRAMES for the full defect analysis.")
    lines.append("")
    lines.append("## Q1 -- mechanism mix (all stress days)")
    lines.append("")
    a = out["Q1_mechanism_mix_all_stress_days"]
    lines.append(f"n={a.get('n')}, total P&L=${a.get('total_pnl')}")
    lines.append("")
    lines.append(f"Final exit stage mix: {a.get('final_exit_stage_mix')}")
    lines.append("")
    lines.append("## Q2 -- side asymmetry")
    lines.append("")
    for side_label, key in (("Bull (calls)", "bull_calls"), ("Bear (puts)", "bear_puts")):
        sa = out["Q2_side_split"][key]
        lines.append(f"- {side_label}: n={sa.get('n')} pnl=${sa.get('total_pnl')}")
    lines.append("")
    lines.append("## Q3 -- cap binding rate")
    lines.append("")
    q3 = out["Q3_cap_binding_rate"]
    lines.append(f"Of {q3['n_binding_exits_(cap_or_chart)']} binding exits (structure-mode "
                 f"trades only), {q3['n_catastrophe_cap_fired']} were the -50% catastrophe cap "
                 f"and {q3['n_chart_structure_stop_fired']} were the chart/structure stop -- "
                 f"cap binding rate = {q3['cap_binding_rate']}.")
    lines.append("")
    lines.append(q3["note"])
    lines.append("")
    lines.append("## Q4 -- ladder sizing")
    lines.append("")
    q4 = out["Q4_ladder_sizing"]
    for k, v in q4.items():
        if k == "note":
            continue
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append(q4["note"])
    lines.append("")
    lines.append("## Q5 -- worst case")
    lines.append("")
    lines.append(f"Worst single trade P&L: ${out['Q5_worst_case']['worst_single_trade_pnl']}")
    for label, v in out["Q5_worst_case"]["all_stress_days"].items():
        if not isinstance(v, dict):
            continue
        lines.append(f"- {label}: worst day ${v['worst_day_dollars']} = "
                     f"{v['pct_of_equity']}% of ${v['arm_equivalent_equity']:,.2f} "
                     f"(kill switch at {v['kill_switch_threshold_pct']}%) -> "
                     f"tripped={v['would_have_tripped_kill_switch']}")
    lines.append("")
    lines.append("## Stratification")
    lines.append("")
    sc = out["stratification_caveat"]
    if sc["n_neither"]:
        lines.append(f"**CAVEAT (UNVERIFIED):** this module's recomputed drop-day/range-day "
                     f"split does not reproduce the prereg's own subset counts "
                     f"(recomputed {sc['recomputed_drop_day_count']} cc<=-2% vs prereg-stated "
                     f"{sc['prereg_stated_close_to_close_le_neg2pct']}; recomputed "
                     f"{sc['recomputed_range_day_count_exclusive_of_drop']} range>=3% vs "
                     f"prereg-stated {sc['prereg_stated_intraday_range_ge_3pct']}). "
                     f"{sc['n_neither']} frozen days satisfy neither recomputed threshold and "
                     f"are excluded from both strata below: "
                     f"{', '.join(sc['days_satisfying_neither_recomputed_threshold'])}. "
                     f"See `_stratification_caveat` in the runner for the full disclosure.")
        lines.append("")
    for label, key in (
        ("Excluding April 2025 block", "STRATIFIED_excluding_april_2025_block"),
        ("April 2025 block only", "STRATIFIED_april_2025_block_only"),
        ("Drop-days (cc<=-2%)", "STRATIFIED_drop_days_cc_le_neg2pct"),
        ("Range-days (range>=3%, cc>-2%)", "STRATIFIED_range_days_ge_3pct_ex_drop"),
    ):
        sa = out[key]
        lines.append(f"- {label}: n={sa.get('n')} pnl=${sa.get('total_pnl')}")
    lines.append("")
    lines.append("## Exclusions (counted, never dropped)")
    lines.append("")
    exc = out["exclusions"]
    for k, v in exc.items():
        if k == "note":
            continue
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Disclosures")
    lines.append("")
    for d in out["disclosures"]:
        lines.append(f"- {d}")
    lines.append("")
    lines.append(f"Elapsed: {out['elapsed_s']}s. Full row-level data: `{OUT_JSON.name}` "
                 f"in this directory.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
