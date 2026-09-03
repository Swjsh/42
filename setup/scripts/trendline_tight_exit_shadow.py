#!/usr/bin/env python
"""trendline_tight_exit_shadow.py -- FORWARD ACCRUAL for TRENDLINE-TIGHT-EXIT-ACCRETE
(queue.md, MED, filed as a "watch candidate from the kitchen's best near-miss").

BACKGROUND. The overnight kitchen's class-conditional-exits study (13-cell grid,
analysis/kitchen/class-conditional-exits-episodes.json, prereg
analysis/kitchen/prereg-class-conditional-exits-2026-07-23.json) tightened TRENDLINE-tier
premium_stop_pct -20% -> -12% and the post-TP1 chandelier trail_pct 15% -> 10% (cell
A6_T-TIGHT_TR-TIGHT). That cell was the night's ONLY 4/4-gate cell and had the best day-WR
of any candidate (67.4%, n=95 real-fills-derived episodes) -- but after the 83-cell
portfolio-wide Benjamini-Hochberg correction it lands at q=0.31 (own-lane q=0.066 was
homework-self-grading -- correcting only within its own 13-cell family hides that 82 OTHER
cells were tested that night). NOT a ship. It IS the best-evidenced exit lead since SS-B.
Full cell table: analysis/kitchen/CLASS-CONDITIONAL-EXITS-2026-07-23.md.

THE ACCRUAL PATH (the queue item's own words): "live SHADOW-score the tightened exit on
every real trendline-class fill going forward until a pre-registered bar clears." This
module is that clock. Same contract as stop_mode_shadow_ledger.py / tp1_r50_forward_shadow.
py: it writes a ledger + a summary, flips no knob, proposes no change, places no order.

WHAT "TRENDLINE-CLASS" MEANS FOR A REAL FILL (disclosed proxy, not guessed). The kitchen
study's tier came from `elite_bear_level_reject_gate_ab.classify_tier(triggers_fired)`, which
needs a backtest-only `triggers_fired` list real broker fills never carry. That SAME study's
own preflight mechanism check (class_conditional_exits_ab.py docstring) found the split is
EXACT and causal-at-entry: "ALL 124 TRENDLINE-tier trades have trigger_level=None -> ...
premium; ALL 66 non-TRENDLINE trades (SUPER+ELITE+LEVEL) have trigger_level set ->
... structure". `trigger_level` IS carried on every real fill (entry-quality-ledger.json's
enrichment). This module therefore classifies a real fill as trendline-class using that
verified 100%/0% proxy: setup canonicalizes (via backtest/lib/setup_taxonomy.py, the ONE
canonical setup-name mapping, so the pre-rename `BULLISH_RECLAIM` alias is caught too) to a
`ribbon_ride` entry setup AND `trigger_level is None`. This is causal-at-entry (trigger_level
is fixed the instant a setup fires, exactly like the backtest tier) and reuses a mechanism
already audited in this codebase rather than inventing a new one.

TIGHTENED-KNOB CONSTRUCTION -- byte-identical to cell A6, not per-arm. The shadow exit shape
is `dict(fleet_strategies.by_name("ribbon_ride").exit.to_dict())` with ONLY
`premium_stop_pct=-0.12` and `trail_pct=0.10` overridden -- the SAME single global control
cell A6 itself used (class_conditional_exits_ab.py's `control_shape`), not a per-arm
resolution. accounts.json's per-arm exit_patch overrides (safe-3: stop_mode=structure +
profit_lock_mode=trailing; risky-1: tp1_premium_pct=0.5 + stop_mode=structure; risky-3:
stop_mode=premium) are irrelevant to `premium_stop_pct` resolution here regardless (trendline
trades have trigger_level=None, so ExitState.from_entry ALWAYS resolves premium mode no
matter what stop_mode the shape declares -- see exit_manager.py's `from_entry` docstring),
but they DO mean an arm's live `profit_lock_mode` can differ from the shadow's. Modeling
each arm's own profit_lock_mode/tp1_premium_pct in the shadow arm would silently blend a
SECOND untested variable into the A6 read; staying byte-identical to the audited cell is the
only faithful accrual of ITS specific evidence. Documented gap, not a silent one.

WHAT IS COMPARED, AND WHY THE DOLLAR MAGNITUDE IS SIGN-ONLY. `recorded_exit` is the REAL
broker-truth dollar P&L already on the enriched ledger (entry-quality-ledger.json events[]
.pnl) -- actual fills, actual slippage, actual spread. `shadow_exit` is a RE-SIMULATION
(exit_manager_walk.walk_exit_manager driving the real exit_manager.py decision core) over
cached OPRA bars under the tightened shape. These two numbers are NOT apples-to-apples:
every other shadow ledger in this codebase (stop_mode_shadow_ledger.py, tp1_r50_forward_
shadow.py) compares two SIMULATED walks against each other, which cancels most re-simulation
bias in the paired delta. Comparing one REAL and one SIMULATED number does not cancel that
bias -- option-bar-resolution effects, cached-quote-vs-actual-fill spread, and exit-timing
granularity all show up as a fixed sign-preserving-but-magnitude-distorting wedge (measured
elsewhere in this codebase at up to $1,821.75 aggregate one-directional, see
option_pricing_real.py's OPTION-BAR-RESOLUTION-BIAS-2026-08-02 disclosure). The DIRECTION of
delta_pnl (did tightening the stop/trail move this trade's outcome toward better or worse)
is informative; its DOLLAR MAGNITUDE is not trustworthy for sizing a verdict. Every summary
this module writes carries `dollar_caveat` stating this explicitly, and the pre-registered
decision rule leans on `sign_agreement` (does the shadow land on the same win/loss side as
the real trade) as a THIRD, sign-only-safe gate alongside the (still-reported, still-gated,
but caveated) dollar-CI gate -- see analysis/recommendations/prereg-trendline-tight-exit-
shadow-2026-09-03.md.

EXTEND, DON'T FORK -- one source of truth each, no re-derivation:
  analysis/entry-quality/entry-quality-ledger.json    ENRICHED broker-truth fills (setup,
                                                       trigger_level, pnl -- see stop_mode_
                                                       shadow_ledger.py's own note on why the
                                                       ENRICHED ledger is required, not
                                                       eql.build_population() directly)
  entry_quality_ledger.load_bars                       cached SIP 5m SPY bars
  lib.option_pricing_real.load_contract_bars            real cached OPRA option bars (disk
                                                        cache ONLY -- returns None on a miss,
                                                        never fetches; a miss is recorded as
                                                        SKIPPED_NO_BARS, never silently
                                                        dropped and never backfilled by a
                                                        network call from this module)
  lib.exit_manager_walk.walk_exit_manager               THE live exit core (never simulator_
                                                        real); walker defaults (frame,
                                                        exit_slippage, all_exits_market) are
                                                        left untouched -- only the exit_shape
                                                        dict's two knobs change
  engine_fullhist_replay.build_ribbon_lookup /
    ribbon_tick_df_for / TIME_STOP_ET                   ribbon alignment, no-look-ahead as-of
                                                        join (identical block to stop_mode_
                                                        shadow_ledger.py's own warmup logic)
  backtest/lib/setup_taxonomy.canonical_setup            the ONE canonical setup-name mapping
  automation/state/fleet/strategies.py                   ribbon_ride's shipped ExitShape,
                                                        read not typed

NO BACKFILL. `ACCRUAL_START_DATE` is pinned to this build's own date (2026-09-03) -- forward-
only by construction, matching tp1_r50_forward_shadow.py's own convention and the queue
item's "going forward" wording.

COST: $0. Pure local computation over already-cached SIP + OPRA bars -- no OPRA fetch, no
new network call, no LLM. Own scheduled task (`Gamma_TrendlineTightExitShadow`, 16:45 ET
weekdays) rather than riding another fire's try-block, matching the sibling `Gamma_
Tp1R50ForwardShadow` / `Gamma_LadderRungShadow` slot convention.

Outputs:
  analysis/recommendations/trendline-tight-exit-shadow-ledger.jsonl   append-only, dedup on
                                                                       activity_id
  analysis/recommendations/trendline-tight-exit-shadow-summary.json   running totals + gate
                                                                       status
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "backtest" / "tools"),
           str(REPO / "backtest" / "lib"), str(REPO / "automation" / "state" / "fleet"),
           str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ENTRY_QUALITY_LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "trendline-tight-exit-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "trendline-tight-exit-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-trendline-tight-exit-shadow-2026-09-03.md"

ACCRUAL_START_DATE = "2026-09-03"   # this build's own date -- no backfill (queue item: "going forward")
WARMUP_DAYS = 12                    # ribbon EMAs are stateful -- cold-starting per day would
                                     # misprice every early-session exit (C12)
BAR_TRADING_DAYS = 20               # pre-registered forward bar (a)
BAR_N_TRENDLINE = 25                # pre-registered forward bar (b)
PREREG = f"TRENDLINE-TIGHT-EXIT-ACCRETE (queue.md) -- {PREREG_REL}"

TIGHTENED_PREMIUM_STOP_PCT = -0.12   # cell A6: -20% -> -12%
TIGHTENED_TRAIL_PCT = 0.10           # cell A6: 15% -> 10%

RIBBON_ENTRY_SETUPS = frozenset({"BEARISH_REJECTION_RIDE_THE_RIBBON",
                                  "BULLISH_RECLAIM_RIDE_THE_RIBBON"})

DOLLAR_CAVEAT = (
    "SIGN-ONLY CAVEAT: recorded_exit is REAL broker-truth P&L; shadow_exit is a "
    "RE-SIMULATION over cached OPRA bars. The pair is not apples-to-apples -- treat "
    "delta_pnl's SIGN (did tightening help or hurt this trade) as informative and its "
    "DOLLAR MAGNITUDE as not sizing-grade. sign_agreement is the safe read; the dollar CI "
    "is reported but caveated the same way in the pre-registered decision rule."
)


# ------------------------------------------------------------------------------------------
# ledger I/O (same tolerant-of-a-torn-last-line contract as the sibling shadow ledgers)
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn last line must never kill the accrual
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


def _sign(x: float) -> int:
    if x > 1e-9:
        return 1
    if x < -1e-9:
        return -1
    return 0


# ------------------------------------------------------------------------------------------
# class assignment -- causal-at-entry proxy, see module docstring
# ------------------------------------------------------------------------------------------
def is_trendline_class(event: dict) -> bool:
    """setup canonicalizes (setup_taxonomy.canonical_setup) to a ribbon_ride entry setup AND
    trigger_level is None -- the verified 100%/0% proxy for the backtest tier's TRENDLINE
    class (see module docstring's MECHANISM section)."""
    from setup_taxonomy import canonical_setup  # noqa: PLC0415
    canon = canonical_setup(event.get("setup"))
    return canon in RIBBON_ENTRY_SETUPS and event.get("trigger_level") is None


# ------------------------------------------------------------------------------------------
# knob pass-through -- byte-identical to cell A6 (see module docstring), only the two
# tightened knobs change; everything else + every walker default stays untouched
# ------------------------------------------------------------------------------------------
def _shapes() -> tuple[dict, dict]:
    import strategies as fleet_strategies  # noqa: PLC0415
    control = dict(fleet_strategies.by_name("ribbon_ride").exit.to_dict())
    tightened = dict(control)
    tightened["premium_stop_pct"] = TIGHTENED_PREMIUM_STOP_PCT
    tightened["trail_pct"] = TIGHTENED_TRAIL_PCT
    return control, tightened


def _walk_tightened(ev: dict, tightened_shape: dict, opt_df, day_spy, ribbon_lookup) -> dict:
    """Replay ONLY the exit under the tightened shape (walker defaults untouched: frame,
    exit_slippage, all_exits_market all left at walk_exit_manager's own defaults)."""
    import engine_fullhist_replay as efr  # noqa: PLC0415
    from lib.exit_manager_walk import walk_exit_manager  # noqa: PLC0415

    entry_time = dt.datetime.fromisoformat(ev["ts_et"]).replace(microsecond=0)
    trigger = ev.get("trigger_level")
    res = walk_exit_manager(
        symbol=ev["symbol"], side=ev["opt_side"], entry_time_et=entry_time,
        entry_premium=float(ev["price"]), qty=int(ev["qty"]), exit_shape=tightened_shape,
        structure_stop_enabled=True,   # inert here: trigger_level is None by construction
        trigger_level=(float(trigger) if trigger is not None else None),
        strategy=str(ev.get("setup") or "ribbon_ride"), time_stop_et=efr.TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
        five_min_spy_df=day_spy, opt_df_resolution="5min", allow_5min=True)
    return {"pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "hold_minutes": res.hold_minutes,
            "reached_tp1": any(leg.stage == "tp1" for leg in res.legs)}


# ------------------------------------------------------------------------------------------
# summary statistics (session-clustered bootstrap CI, top-3 concentration, sign agreement)
# ------------------------------------------------------------------------------------------
def _bootstrap_day_clustered_mean(rows: list[dict], n_boot: int = 2000,
                                   seed: int = 20260903) -> dict | None:
    """Percentile bootstrap resampling trading DAYS with replacement (matches go_live_gate.
    bootstrap_pf_ci's methodology / tp1_r50_forward_shadow's own CI). None below 2 days."""
    by_day: dict[str, list[float]] = collections.defaultdict(list)
    for r in rows:
        by_day[r["date_et"]].append(r["delta_pnl"])
    days = sorted(by_day)
    n_days = len(days)
    if n_days < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample_days = [days[rng.randrange(n_days)] for _ in range(n_days)]
        vals = [v for d in sample_days for v in by_day[d]]
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return {"n_boot": n_boot, "n_days_clustered": n_days,
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def _top3_concentration_share(rows: list[dict]) -> float:
    deltas = [r["delta_pnl"] for r in rows]
    total_abs = sum(abs(d) for d in deltas)
    if total_abs <= 1e-9:
        return 0.0
    top3_abs = sum(sorted((abs(d) for d in deltas), reverse=True)[:3])
    return round(top3_abs / total_abs, 4)


def _summarize(rows: list[dict]) -> dict:
    """`rows` is the FULL ledger (scored + skipped). Stats are computed on the SCORED subset
    only -- a skip carries no delta to average in."""
    scored = [r for r in rows if r.get("status") == "SCORED"]
    skipped = [r for r in rows if r.get("status") != "SCORED"]
    n = len(rows)
    days = sorted({r["date_et"] for r in scored})
    skipped_by_reason: dict[str, int] = collections.defaultdict(int)
    for r in skipped:
        skipped_by_reason[r.get("status", "SKIPPED_UNKNOWN")] += 1

    base = {
        "prereg": PREREG_REL, "generated_at_et": _stamp_now_et(),
        "accrual_start": ACCRUAL_START_DATE,
        "tightened_knobs": {"premium_stop_pct": TIGHTENED_PREMIUM_STOP_PCT,
                            "trail_pct": TIGHTENED_TRAIL_PCT},
        "dollar_caveat": DOLLAR_CAVEAT,
        "n": n, "n_scored": len(scored), "n_skipped": len(skipped),
        "n_skipped_by_reason": dict(skipped_by_reason),
        "days_to_bar": max(0, BAR_TRADING_DAYS - len(days)),
        "trendline_to_bar": max(0, BAR_N_TRENDLINE - len(scored)),
    }

    if not scored:
        base.update({
            "days_accrued": 0, "sum_delta": 0.0, "mean_delta": None,
            "session_clustered_ci": None, "top3_share": 0.0, "sign_agreement": None,
            "bar_met": False, "status": "ARMED_AWAITING_FILLS",
            "note": ("No scored trendline-class closed trades on/after the accrual start "
                     "yet. An empty clock on day 0 is expected, NOT a failure -- but a clock "
                     "still empty after several trading days means the upstream enriched "
                     "ledger stopped feeding it, or every trendline fill so far lacks cached "
                     "OPRA bars (check n_skipped_by_reason)."),
        })
        return base

    sum_delta = round(sum(r["delta_pnl"] for r in scored), 2)
    mean_delta = round(sum_delta / len(scored), 4)
    ci = _bootstrap_day_clustered_mean(scored)
    top3_share = _top3_concentration_share(scored)
    sign_agreement = round(sum(1 for r in scored if r["sign_agree"]) / len(scored), 4)

    by_day_total: dict[str, float] = collections.defaultdict(float)
    for r in scored:
        by_day_total[r["date_et"]] += r["delta_pnl"]
    best_day_total = max(by_day_total.values(), default=0.0)
    ex_best_day_sum_delta = round(sum_delta - best_day_total, 2)

    bar_met = (len(days) >= BAR_TRADING_DAYS) and (len(scored) >= BAR_N_TRENDLINE)

    base.update({
        "days_accrued": len(days), "date_span": f"{days[0]}..{days[-1]}",
        "sum_delta": sum_delta, "mean_delta": mean_delta,
        "session_clustered_ci": ci, "top3_share": top3_share,
        "sign_agreement": sign_agreement,
        "ex_best_day_sum_delta": ex_best_day_sum_delta,
        "bar_met": bar_met,
        "status": "BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING",
        "decision_rule": (
            "This ledger NEVER flips premium_stop_pct/trail_pct by itself. At "
            f"days_accrued>={BAR_TRADING_DAYS} AND n_scored>={BAR_N_TRENDLINE} it becomes "
            "eligible for the FROZEN decision rule in "
            f"{PREREG_REL}: ship-candidate only if session_clustered_ci.ci_lower_2.5 > 0 "
            "AND top3_share < 0.50 AND sign_agreement >= 0.85. Reaching the bar is "
            "permission to READ the verdict, not to ship -- not softenable."),
    })
    return base


def _input_health(events: list[dict]) -> dict:
    newest = max((e.get("date_et", "") for e in events), default="")
    today = dt.date.today()
    back = 1 if today.weekday() != 0 else 3          # Mon looks back to Fri
    prev_session = today - dt.timedelta(days=back)
    while prev_session.weekday() >= 5:               # skip Sat/Sun
        prev_session -= dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_ledger_newest_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- entry-quality-ledger.json has not advanced to the last "
                           "completed session; this clock is not being fed and its counts "
                           "are frozen, NOT a real absence of trendline fills." if stale
                           else "fed")}


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Fail-open by contract: the caller must never be broken by a
    failure here."""
    try:
        import pandas as pd
        import entry_quality_ledger as eql
        import engine_fullhist_replay as efr
        from lib.option_pricing_real import load_contract_bars

        if not ENTRY_QUALITY_LEDGER.exists():
            raise RuntimeError(f"enriched ledger missing: {ENTRY_QUALITY_LEDGER}")
        doc = json.loads(ENTRY_QUALITY_LEDGER.read_text(encoding="utf-8"))
        events = doc.get("events", [])
        if events and not any("trigger_level" in e for e in events):
            raise RuntimeError("enriched ledger carries no trigger_level field -- the "
                               "trendline-class proxy cannot be computed; refusing to "
                               "accrue a meaningless population")

        fresh = [e for e in events
                 if e.get("is_option") and e.get("attribution") == "engine"
                 and e.get("side") == "buy" and e.get("date_et", "") >= ACCRUAL_START_DATE
                 and float(e.get("exit_qty") or 0) >= float(e.get("qty") or 0) - 1e-6
                 and is_trendline_class(e)]

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen = {r.get("activity_id") for r in existing}
        todo = [e for e in fresh if e.get("activity_id") not in seen]

        if not todo:
            summary = _summarize(existing)
            summary["new_this_run"] = 0
            summary.update(_input_health(events))
            SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            return summary

        _, tightened_shape = _shapes()

        # Ribbon EMAs are stateful -- build the lookup over a continuous warmup window ending
        # at the newest date needed, never per-day cold (C12), identical block to
        # stop_mode_shadow_ledger.py.
        need_dates = sorted({e["date_et"] for e in todo})
        all_days = sorted({e["date_et"] for e in events})
        first_i = max(0, all_days.index(need_dates[0]) - WARMUP_DAYS)
        window = all_days[first_i:all_days.index(need_dates[-1]) + 1]
        bars5 = eql.load_bars("5m", window)
        flat = [b for d in window for b in bars5.get(d, [])]
        if not flat:
            raise RuntimeError(f"no 5m SPY bars for window {window[0]}..{window[-1]}")
        spy = pd.DataFrame(flat).rename(columns={"t": "timestamp_et", "o": "open", "h": "high",
                                                 "l": "low", "c": "close", "v": "volume"})
        spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
        if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
            spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
        spy = (spy.sort_values("timestamp_et").drop_duplicates(subset="timestamp_et")
                  .reset_index(drop=True))
        ribbon_lookup = efr.build_ribbon_lookup(spy)
        rth = spy.loc[(spy["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)

        appended = []
        for ev in sorted(todo, key=lambda e: e["ts_et"]):
            recorded_pnl = float(ev.get("pnl") or 0.0)
            recorded_exit = {"pnl": round(recorded_pnl, 2),
                              "source": "broker_truth (entry-quality-ledger.json events[].pnl)"}
            base_row = {
                "activity_id": ev.get("activity_id"), "date_et": ev["date_et"],
                "ts_et": ev["ts_et"], "arm": ev.get("arm"), "symbol": ev["symbol"],
                "opt_side": ev.get("opt_side"), "setup": ev.get("setup"),
                "qty": int(ev["qty"]), "entry_premium": float(ev["price"]),
                "recorded_exit": recorded_exit,
            }

            opt_df = load_contract_bars(ev["symbol"])
            if opt_df is None or getattr(opt_df, "empty", True):
                appended.append({**base_row, "shadow_exit": None, "delta_pnl": None,
                                  "sign_agree": None, "bars_source": None,
                                  "status": "SKIPPED_NO_BARS"})
                continue
            entry_time = dt.datetime.fromisoformat(ev["ts_et"])
            day_spy = rth.loc[rth["timestamp_et"].dt.date == entry_time.date()].reset_index(drop=True)
            if day_spy.empty:
                appended.append({**base_row, "shadow_exit": None, "delta_pnl": None,
                                  "sign_agree": None, "bars_source": None,
                                  "status": "SKIPPED_NO_SPY_DAY"})
                continue
            try:
                shadow_exit = _walk_tightened(ev, tightened_shape, opt_df, day_spy, ribbon_lookup)
            except Exception as walk_err:  # noqa: BLE001 -- one bad trade must never kill the run
                appended.append({**base_row, "shadow_exit": None, "delta_pnl": None,
                                  "sign_agree": None, "bars_source": None,
                                  "status": "SKIPPED_WALK_FAILED",
                                  "skip_reason": f"{type(walk_err).__name__}: {walk_err}"[:200]})
                continue

            delta_pnl = round(shadow_exit["pnl"] - recorded_pnl, 2)
            sign_agree = bool(_sign(shadow_exit["pnl"]) == _sign(recorded_pnl))
            appended.append({**base_row, "shadow_exit": shadow_exit, "delta_pnl": delta_pnl,
                              "sign_agree": sign_agree,
                              "bars_source": f"opra_5min_cache:{ev['symbol']}",
                              "status": "SCORED"})

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        summary = _summarize(existing + appended)
        summary["new_this_run"] = len(appended)
        summary.update(_input_health(events))
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:300], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
