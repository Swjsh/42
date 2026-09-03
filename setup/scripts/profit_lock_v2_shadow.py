#!/usr/bin/env python
"""profit_lock_v2_shadow.py -- FORWARD ACCRUAL for the PROFIT-LOCK V2 candidate (F1
profit-lock-v2-shadow, filed 2026-09-03, descends from
analysis/deep-research/2026-09-03-money/profit-lock-scope.md's H4 finding).

BACKGROUND. H4 measured `profit_lock_arm_scope='full'` (arm the chandelier at the LIVE
+5% favor, DEFAULT_PROFIT_LOCK_ARM_PCT, before any TP1 fill) against today's live
'post_tp1' default, replayed through the real production `exit_manager.plan_exit_actions`
over the 394-trade `analysis/pain-ledger/mae-mfe.json` population. Verdict (quoted): "MIXED
-- do not ship as tested." The one arm whose dollars this codebase trusts (safe-2, walker
magnitude-fidelity ratio 0.96 per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md) showed a real
but thin aggregate edge (+$2,578.41/88 trades, bootstrap CI [$0.59, $55.86]/trade) that (a)
was NOT recency-stable (most recent quarter net -$327.45) and (b) truncated 3 of the 4 named
big winning days (08-06/08-27/08-28) to a combined -$880.90, including two trades cut to
EXACTLY $0 -- the pre-TP1 trail arming on an early +5% tick and stopping the trade back out
before its real move developed. This is precisely the failure mode the ORIGINAL
2026-08-06 prereg (analysis/recommendations/profit-lock-arm-scope-prereg-2026-08-06.json)
named by name and never measured -- H4 measured it, and it is real.

H4's own conclusion (quoted): "A narrower candidate (e.g., a higher arm threshold than +5%,
or a ladder that only activates after some minimum time-in-trade / minimum favorable
excursion rather than the first +5% tick) is a plausible next step but must be its own fresh
pre-registration against data not yet seen by this run ... the 394-trade population here is
now SEEN data for the +5%/15%-trail cell." THIS MODULE IS THAT NEXT PREREG'S FORWARD CLOCK.

THE CANDIDATE UNDER TEST ("V2"): profit_lock_arm_scope='full' (same mechanism), but with
TWO changes meant to specifically avoid H4's own failure mode -- arm later, not on the
first favorable tick:
  1. profit_lock_arm_pct raised from the live 0.05 (+5% favor) to 0.20 (+20% favor) --
     TREATMENT_ARM_PCT below. A REAL exit_manager.py knob (ExitState.profit_lock_arm_pct,
     ExitState.from_entry reads exit_shape['profit_lock_arm_pct']), passed through the shape
     dict exactly like any other exit_shape key -- no code change, no wrapper needed for
     this half.
  2. An ADDITIONAL minimum-time-in-trade of 10 minutes before the pre-TP1 lock may arm
     (TREATMENT_MIN_ARM_MINUTES below). exit_manager.py HAS NO SUCH KNOB -- confirmed by
     grep this build (`grep -n "min_time" -e "entry_time" automation/state/fleet/exit_manager.py`
     returns nothing relevant to a trade-age gate). Per this task's explicit instruction,
     the time condition is implemented IN THE WALKER WRAPPER ONLY, by MASKING
     profit_lock_arm_scope to 'post_tp1' for every bar whose timestamp is still inside the
     first 10 minutes after entry, then restoring it to 'full' for every bar after that --
     see `_walk_exit_manager_time_gated` below for the exact mechanism and why this is
     provably equivalent to "the favor-based early-arm branch is inert before entry+10min,
     unaffected after it" without touching a single line of the real exit_manager.py.
     ⛔ THIS IS A SHADOW-ONLY SIMULATION OF A KNOB THAT DOES NOT EXIST LIVE. If this
     candidate's forward evidence ever clears its decision rule (analysis/recommendations/
     prereg-profit-lock-v2-forward-shadow-2026-09-03.md), the REAL implementation still
     needs a genuine min-time-in-trade field added to exit_manager.ExitState / from_entry /
     plan_exit_actions -- that is a 2026-10-30+ (config-freeze-end) ratification-path build
     item, NOT something this shadow ships or approximates as already-live.
  trail_pct is UNCHANGED from canonical_shape(date)'s own value (today's live 0.125 chandelier
  width, per regime-chandelier-sweep.md's already-adopted finding) -- only the arm CONDITION
  changes, never the trail width, exactly matching H4's own control-holds-trail-constant
  design.

METHOD (reuses the H4 harness, never re-implements the decision core):
  For every CLOSED engine fill (entry_quality_ledger.json, itself sourced from
  automation/state/fills-ledger.jsonl attribution=='engine', EXTEND-DON'T-FORK per this
  codebase's established convention -- see tp1_r50_forward_shadow.py's own docstring for the
  precedent), on EVERY arm: replay through
  `setup/scripts/pdt_blocked_counterfactual.py`'s `canonical_shape(date)` + `_price_via_walker`
  (walker='exit_manager' -> `backtest/lib/exit_manager_walk.walk_exit_manager`, which ticks
  the REAL production `automation/state/fleet/exit_manager.py#plan_exit_actions` decision
  core, exactly as H4's `money_profit_lock_scope.py` already does) for CONTROL, and through
  this module's own `_price_via_walker_time_gated` (same production `plan_exit_actions`,
  same fill-price convention, same frame handling -- the ONLY difference is the profit_lock_
  arm_scope masking described above) for TREATMENT.

BARS: 1-min disk cache first (`backtest/data/highres/`, cache-only, reused via
`money_profit_lock_scope.load_1min_cache_only` -- EXTEND not fork), falling back to the 5-min
OPRA cache (`option_pricing_real.load_contract_bars`, also cache-only). No network call of
any kind. A trade with neither cached is SKIPPED and counted, never estimated.

TRUSTED DOLLARS: per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md and H4's own independent
confirmation, ONLY safe-2 individually clears the walker's magnitude-fidelity bar. Every
other arm's dollars are SIGN-ONLY in this ledger's `trusted_dollars` field and in every
summary statistic -- never read a non-safe-2 dollar figure as a trustworthy magnitude.

BACKFILL (ONE-TIME, DISCLOSED IN-SAMPLE PRIOR): `entry_quality_ledger.json` already covers
2026-06-26..2026-09-02 at build time. Every one of those historical closed fills is scored
and written to the ledger on this module's FIRST run, marked `in_sample=True` -- an honest
prior measurement of the V2 candidate against ALREADY-SEEN data (same population H4 itself
drew from), never hidden. `in_sample=False` marks any row whose `date < FORWARD_START_DATE`
is false, i.e. every row dated 2026-09-03 or later -- the genuinely forward, not-yet-seen
population the frozen prereg's decision rule is scored against exclusively. Ledger rows are
deduped on `activity_id` (the SAME idempotent-append contract every sibling shadow ledger in
this codebase uses), so the backfill naturally happens ONCE: a historical activity_id already
on disk is never re-scored, and only genuinely new (forward) activity_ids get appended on
each nightly fire -- exactly `tp1_r50_forward_shadow.py`'s own dedup mechanism, just without
that module's date floor on the SOURCE population (this module deliberately DOES read
pre-2026-09-03 events, once, disclosed as in_sample=True, per this task's explicit ask).

DECISION RULE: frozen BEFORE any forward data accrues in
analysis/recommendations/prereg-profit-lock-v2-forward-shadow-2026-09-03.md. NOTHING SHIPS
before 2026-10-30 (config freeze) regardless of what this ledger ever reads -- and even past
that date, this module's own docstring plus the prereg both flag that the live implementation
of the 10-minute mask does not exist yet and is a separate build item.

$0. Pure local replay over already-written cached bars + JSON/JSONL artifacts. No paid API,
no LLM, no broker/market-data call of any kind.
"""
from __future__ import annotations

import collections
import json
import random
import sys
from dataclasses import replace as _dc_replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "backtest/tools", "backtest/lib", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as pd  # noqa: E402

import pdt_blocked_counterfactual as pbc  # noqa: E402  -- canonical_shape, _price_via_walker, ARM2ACCOUNT
import money_profit_lock_scope as mpls  # noqa: E402  -- EXTEND not fork: bar loader + bootstrap_ci
from option_pricing_real import load_contract_bars  # noqa: E402
from exit_manager_walk import (  # noqa: E402
    _reframe_series, FRAME_WALL_V1, DEFAULT_EXIT_SLIPPAGE,
    ribbon_stack_at, last_closed_bar_close_at, _stage_fill_level, _fill_price, ExitLeg,
)
import exit_manager as em  # noqa: E402  -- automation/state/fleet, read-only import
from exit_manager import TIME_STOP_ET, ARM_SCOPE_FULL, ARM_SCOPE_POST_TP1  # noqa: E402

ENTRY_QUALITY_LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "profit-lock-v2-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "profit-lock-v2-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-profit-lock-v2-forward-shadow-2026-09-03.md"

FORWARD_START_DATE = "2026-09-03"      # this build's own date -- rows on/after this are forward
TRUSTED_ARMS = frozenset({"safe-2"})   # per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md

TREATMENT_ARM_PCT = 0.20               # was live 0.05 (DEFAULT_PROFIT_LOCK_ARM_PCT) -- see docstring
TREATMENT_MIN_ARM_MINUTES = 10.0       # wrapper-level mask, NOT a live exit_manager.py knob

BAR_FORWARD_SESSIONS = 20              # pre-registered forward bar (a): distinct forward dates, any arm
BAR_FORWARD_SAFE2_SCORED = 25          # pre-registered forward bar (b): forward safe-2 scored fills
                                         # (the exact population the CI decision below is computed over)

WINNER_ANCHOR_DATES = ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")
RUNNER_DATE = "2026-08-04"
RUNNER_SYMBOL = "SPY260804C00769000"
RUNNER_ARM = "safe-2"                  # the only arm+symbol+date match that is dollar-trusted;
                                        # matches H4's own "08-04 bonus check" (identical trade)


# ------------------------------------------------------------------------------------------
# ledger I/O -- same tolerant-of-a-torn-last-line, dedup-on-activity_id contract every
# sibling shadow ledger in this codebase uses (tp1_r50_forward_shadow.py, day_throttle_
# shadow.py, stop_mode_shadow_ledger.py, ...).
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


# ------------------------------------------------------------------------------------------
# TREATMENT walker -- production exit_manager.plan_exit_actions, ticked bar-by-bar, with the
# profit_lock_arm_scope MASK described in the module docstring. Mirrors
# `exit_manager_walk.walk_exit_manager`'s loop structure and every helper call it makes
# (same _stage_fill_level / _fill_price / ribbon_stack_at / last_closed_bar_close_at, all
# IMPORTED not re-derived) -- the only new logic is the per-tick scope substitution.
# ------------------------------------------------------------------------------------------
def _walk_exit_manager_time_gated(
    *, symbol: str, side: str, entry_time_et, entry_premium: float, qty: int,
    exit_shape: dict, structure_stop_enabled: bool, trigger_level, strategy: str,
    time_stop_et, opt_df: pd.DataFrame, ribbon_tick_df,
    five_min_spy_df: pd.DataFrame, min_arm_minutes: float,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
) -> dict:
    """Returns the same {"pnl","legs","n_legs","walked_stage"} / {"error"} shape convention
    `pbc._price_via_walker` already returns, so callers below never need to branch on which
    walker priced a given trade.

    THE MASK, precisely: on every tick whose bar timestamp is still < entry_time_et +
    min_arm_minutes, `em.plan_exit_actions` is called on a COPY of the live state with
    `profit_lock_arm_scope` forced to `ARM_SCOPE_POST_TP1` -- this suppresses ONLY
    exit_manager.py's own `if state.profit_lock_arm_scope == ARM_SCOPE_FULL: ...` pre-TP1
    favor-arming branch for that one tick (see automation/state/fleet/exit_manager.py's own
    comment at that branch). Every OTHER mechanism plan_exit_actions runs on that same tick
    -- TP1's own UNCONDITIONAL profit_lock_armed=True, the catastrophe/premium stop,
    structure stop, ribbon-flip, time stop -- is completely unaffected, because none of them
    branch on profit_lock_arm_scope. Immediately after the call, `profit_lock_arm_scope` is
    restored to `ARM_SCOPE_FULL` on the returned state (every OTHER field the tick computed --
    profit_lock_armed, hwm_premium, runner_stop_premium -- is kept exactly as computed) before
    the next tick, so a tick at/after entry+10min sees the real 'full' scope and the
    favor-based branch can arm normally (still gated on the RAISED profit_lock_arm_pct=0.20
    already baked into `exit_shape`, since that part IS a real exit_manager.py knob passed
    through `exit_shape` -- no masking needed for it)."""
    state = em.ExitState.from_entry(
        symbol=symbol, side=side, entry_premium=entry_premium, qty=qty,
        exit_shape=exit_shape, strategy=strategy, trigger_level=trigger_level,
        structure_stop_enabled=structure_stop_enabled)

    opt_df = opt_df.reset_index(drop=True)
    opt_df = opt_df.assign(timestamp_et=_reframe_series(opt_df["timestamp_et"], FRAME_WALL_V1))

    entry_ts = pd.Timestamp(entry_time_et)
    if entry_ts.tzinfo is not None:
        entry_ts = entry_ts.tz_localize(None)

    after = opt_df.index[opt_df["timestamp_et"] > entry_ts]
    if len(after) == 0:
        return {"error": "no bars at/after entry", "pnl": 0.0, "legs": []}
    start_idx = int(after[0])

    open_qty = qty
    realized = 0.0
    legs: list[dict] = []
    n_ticks = 0
    n_masked_ticks = 0
    resolved = False
    exit_reason = ""

    for idx in range(start_idx, len(opt_df)):
        bar = opt_df.iloc[idx]
        ts = bar["timestamp_et"]
        best = float(bar["open"])
        worst = float(bar["open"])
        now_et = ts.time()
        n_ticks += 1

        flip = False
        if ribbon_tick_df is not None and idx < len(ribbon_tick_df) and strategy != "adopted_manual":
            stack = ribbon_stack_at(ribbon_tick_df, idx)
            if stack in ("BULL", "BEAR"):
                flip = (stack == "BULL") if side == "P" else (stack == "BEAR")

        closed5 = last_closed_bar_close_at(five_min_spy_df, ts, frame=FRAME_WALL_V1)

        elapsed_min = (ts - entry_ts).total_seconds() / 60.0
        masked = (elapsed_min < min_arm_minutes) and (state.profit_lock_arm_scope == ARM_SCOPE_FULL)
        state_in = _dc_replace(state, profit_lock_arm_scope=ARM_SCOPE_POST_TP1) if masked else state
        if masked:
            n_masked_ticks += 1

        dec = em.plan_exit_actions(
            state_in, best_premium=best, worst_premium=worst, open_qty=open_qty,
            now_et=now_et, ribbon_flip_back=flip, time_stop_et=time_stop_et,
            last_closed_5m_close=closed5)
        state = dec.state
        if masked:
            state = _dc_replace(state, profit_lock_arm_scope=ARM_SCOPE_FULL)

        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            level = _stage_fill_level(a.stage, state_in, state)
            px = _fill_price(a.stage, level, float(bar["close"]), exit_slippage=exit_slippage)
            leg_pnl = (px - entry_premium) * a.qty * 100.0
            realized += leg_pnl
            open_qty -= a.qty
            legs.append({"t": ts.strftime("%H:%M"), "stage": a.stage, "qty": a.qty,
                        "px": round(px, 4), "pnl": round(leg_pnl, 2)})
        if dec.closes_position:
            resolved = True
            exit_reason = dec.actions[-1].reason
            break

    if not resolved and open_qty > 0:
        last_bar = opt_df.iloc[-1]
        px = max(0.01, float(last_bar["close"]) - DEFAULT_EXIT_SLIPPAGE)
        leg_pnl = (px - entry_premium) * open_qty * 100.0
        realized += leg_pnl
        legs.append({"t": last_bar["timestamp_et"].strftime("%H:%M"), "stage": "force_close",
                    "qty": open_qty, "px": round(px, 4), "pnl": round(leg_pnl, 2)})
        exit_reason = "data_exhausted_force_close"

    return {"pnl": round(realized, 2), "legs": legs, "n_legs": len(legs),
            "walked_stage": ("+".join(l["stage"] for l in legs) if legs else exit_reason),
            "n_ticks_walked": n_ticks, "n_masked_ticks": n_masked_ticks}


def _price_via_walker_time_gated(fill: dict, shape: dict, bars: pd.DataFrame, *,
                                  trigger_level: float, spy_map: dict,
                                  min_arm_minutes: float = TREATMENT_MIN_ARM_MINUTES,
                                  exit_slippage: float = 0.01) -> dict:
    """TREATMENT-side counterpart of `pbc._price_via_walker("exit_manager", ...)` -- builds
    the same `ribbon_tick_df` / `five_min_spy_df` inputs that module's own `_walk_via_
    exit_manager` builds (reusing `pbc._five_min_spy_df_for_date` and `pbc.wen.
    build_ribbon_tick_df`, never re-derived), but calls `_walk_exit_manager_time_gated`
    above instead of the unmodified `exit_manager_walk.walk_exit_manager`."""
    entry = float(fill["entry_premium"])
    qty = int(fill["qty"])
    sym = fill["symbol"]
    side = "P" if "P00" in sym else "C"
    entry_time_et = pd.Timestamp(f"{fill['date']} {fill['entry_time']}")
    five_min_spy_df = pbc._five_min_spy_df_for_date(fill["date"], spy_map or {})
    account = fill.get("account")
    ribbon_tick_df = None
    if account:
        reframed = bars.assign(timestamp_et=_reframe_series(bars["timestamp_et"], FRAME_WALL_V1))
        ribbon_tick_df = pbc.wen.build_ribbon_tick_df(reframed, fill["date"], account)
    try:
        return _walk_exit_manager_time_gated(
            symbol=sym, side=side, entry_time_et=entry_time_et, entry_premium=entry, qty=qty,
            exit_shape=shape, structure_stop_enabled=bool(trigger_level),
            trigger_level=trigger_level, strategy=str(fill.get("strategy", "RIBBON")),
            time_stop_et=TIME_STOP_ET, opt_df=bars, ribbon_tick_df=ribbon_tick_df,
            five_min_spy_df=five_min_spy_df, min_arm_minutes=min_arm_minutes,
            exit_slippage=exit_slippage)
    except Exception as exc:  # noqa: BLE001 -- mirror pbc._walk_via_exit_manager's error-as-data contract
        return {"error": f"{type(exc).__name__}: {exc}", "pnl": 0.0, "legs": []}


# ------------------------------------------------------------------------------------------
# population -- entry_quality_ledger.json, EXTEND not fork (see module docstring)
# ------------------------------------------------------------------------------------------
def _load_closed_events() -> list[dict]:
    if not ENTRY_QUALITY_LEDGER.exists():
        raise RuntimeError(f"enriched entry-quality ledger missing: {ENTRY_QUALITY_LEDGER}")
    doc = json.loads(ENTRY_QUALITY_LEDGER.read_text(encoding="utf-8"))
    events = doc.get("events", [])
    return [e for e in events
            if e.get("attribution") == "engine" and e.get("is_option")
            and float(e.get("exit_qty") or 0) >= float(e.get("qty") or 0) - 1e-6]


def _et_time_of_day(ts_et: str) -> str:
    """'2026-08-04T12:28:43.618110' -> '12:28:43'."""
    if not ts_et or "T" not in ts_et:
        return "09:31:00"
    return ts_et.split("T", 1)[1][:8]


# ------------------------------------------------------------------------------------------
# per-trade scoring
# ------------------------------------------------------------------------------------------
def score_event(e: dict, spy_map: dict) -> tuple[dict | None, str | None]:
    """Returns (row, None) or (None, skip_reason) -- never fabricates, never silently drops."""
    arm = e.get("arm")
    symbol = e.get("symbol")
    date = e.get("date_et")
    if not (arm and symbol and date):
        return None, "missing_arm_symbol_or_date"

    qty = int(round(float(e.get("qty") or 0)))
    entry_price = float(e.get("price") or 0)
    if qty <= 0 or entry_price <= 0:
        return None, "non_positive_qty_or_price"

    bars = mpls.load_1min_cache_only(symbol, date)
    bar_res = "1min"
    if bars is None or len(bars) == 0:
        bars = load_contract_bars(symbol)
        bar_res = "5min"
    if bars is None or len(bars) == 0:
        return None, "no_bars"

    et_time = _et_time_of_day(e.get("ts_et"))
    setup = e.get("setup") or "RIBBON"
    account = pbc.ARM2ACCOUNT.get(arm)
    shape = pbc.canonical_shape(date)
    trig = pbc.resolve_trigger_level(date, e.get("trigger_level"))

    fill = {"entry_premium": entry_price, "qty": qty, "symbol": symbol, "date": date,
            "entry_time": et_time, "strategy": setup, "account": account}

    try:
        res_control = pbc._price_via_walker(
            "exit_manager", fill, shape, bars, trigger_level=trig, spy_map=spy_map)
    except Exception as exc:  # noqa: BLE001
        return None, f"control_walk_error:{type(exc).__name__}:{exc}"

    shape_treat = dict(shape)
    shape_treat["profit_lock_arm_scope"] = "full"
    shape_treat["profit_lock_arm_pct"] = TREATMENT_ARM_PCT
    # trail_pct deliberately NOT touched -- inherited unchanged from canonical_shape(date)
    res_treat = _price_via_walker_time_gated(
        fill, shape_treat, bars, trigger_level=trig, spy_map=spy_map,
        min_arm_minutes=TREATMENT_MIN_ARM_MINUTES)

    if "error" in res_control:
        return None, f"control_walk_error:{res_control['error']}"
    if "error" in res_treat:
        return None, f"treatment_walk_error:{res_treat['error']}"

    control_pnl = float(res_control["pnl"])
    treatment_pnl = float(res_treat["pnl"])
    delta = round(treatment_pnl - control_pnl, 2)
    trusted = arm in TRUSTED_ARMS

    row = {
        "activity_id": e.get("activity_id"),
        "date": date, "arm": arm, "symbol": symbol, "setup": setup,
        "qty": qty, "entry_price": entry_price, "ts_et": e.get("ts_et"),
        "control_pnl": control_pnl, "treatment_pnl": treatment_pnl, "delta": delta,
        "mfe_pct": e.get("mfe_pct"),   # fraction convention (0.20 == +20% MFE), passed through
        "bars_source": bar_res,
        "trusted_dollars": trusted,
        "in_sample": bool(date < FORWARD_START_DATE),
        "control_walked_stage": res_control.get("walked_stage"),
        "treatment_walked_stage": res_treat.get("walked_stage"),
        "treatment_n_masked_ticks": res_treat.get("n_masked_ticks"),
        "actual_broker_pnl": e.get("pnl"),
    }
    return row, None


# ------------------------------------------------------------------------------------------
# summary
# ------------------------------------------------------------------------------------------
def _per_arm_sums(rows: list[dict]) -> dict:
    out: dict = {}
    for arm in sorted({r["arm"] for r in rows}):
        rows_a = [r for r in rows if r["arm"] == arm]
        out[arm] = {
            "n": len(rows_a),
            "sum_control_pnl": round(sum(r["control_pnl"] for r in rows_a), 2),
            "sum_treatment_pnl": round(sum(r["treatment_pnl"] for r in rows_a), 2),
            "sum_delta": round(sum(r["delta"] for r in rows_a), 2),
            "trusted_dollars": arm in TRUSTED_ARMS,
        }
    return out


def _recent_quarter_delta_safe2(safe2_rows_all: list[dict]) -> dict:
    """Chronological last-quarter split over ALL accrued safe-2 rows (in_sample + forward),
    generalizing H4's own Q4 (2026-08-18..09-02, -$327.45) -- as forward rows accrue this
    quarter naturally absorbs more forward dates over time. Descriptive continuity check, NOT
    itself the frozen forward-only decision input (see prereg §5 / _decision_conditions)."""
    rows_sorted = sorted(safe2_rows_all, key=lambda r: (r["date"], r["ts_et"] or ""))
    n = len(rows_sorted)
    if n == 0:
        return {"n": 0, "delta": None, "date_span": None}
    q = max(1, n // 4)
    tail = rows_sorted[-q:]
    return {"n": len(tail), "delta": round(sum(r["delta"] for r in tail), 2),
            "date_span": f"{tail[0]['date']}..{tail[-1]['date']}"}


def _big_days(safe2_rows_all: list[dict]) -> dict:
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    for r in safe2_rows_all:
        if r["date"] in WINNER_ANCHOR_DATES:
            by_date[r["date"]].append(r)
    result = {}
    for d in WINNER_ANCHOR_DATES:
        rs = by_date.get(d, [])
        result[d] = {"n": len(rs), "delta": round(sum(r["delta"] for r in rs), 2) if rs else None}
    dates_missing = [d for d in WINNER_ANCHOR_DATES if not by_date.get(d)]
    all_ge_zero = (not dates_missing) and all(result[d]["delta"] >= 0 for d in WINNER_ANCHOR_DATES)
    return {"per_date": result, "dates_missing": dates_missing, "all_ge_zero": all_ge_zero}


def _runner_08_04(all_rows: list[dict]) -> dict:
    matches = [r for r in all_rows if r["date"] == RUNNER_DATE and r["symbol"] == RUNNER_SYMBOL
               and r["arm"] == RUNNER_ARM]
    if not matches:
        return {"found": False, "delta": None, "note": (
            f"no {RUNNER_ARM} row for {RUNNER_SYMBOL} on {RUNNER_DATE} yet -- this is a "
            f"backfill-population fact (RUNNER_DATE < FORWARD_START_DATE), so an absence "
            f"here on a run AFTER the first backfill means the source ledger lost the row, "
            f"not that forward accrual hasn't reached it yet.")}
    return {"found": True, "delta": round(sum(r["delta"] for r in matches), 2),
            "n_matches": len(matches)}


def _bootstrap_ci(deltas: list[float]) -> dict | None:
    if not deltas:
        return None
    return mpls.bootstrap_ci(deltas)


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    in_sample_rows = [r for r in rows if r["in_sample"]]
    forward_rows = [r for r in rows if not r["in_sample"]]
    sessions_total = sorted({r["date"] for r in rows})
    sessions_forward = sorted({r["date"] for r in forward_rows})

    safe2_all = [r for r in rows if r["arm"] == "safe-2"]
    safe2_forward = [r for r in forward_rows if r["arm"] == "safe-2"]

    per_arm = _per_arm_sums(rows)
    recent_quarter = _recent_quarter_delta_safe2(safe2_all)
    big_days = _big_days(safe2_all)
    runner = _runner_08_04(rows)
    safe2_forward_ci = _bootstrap_ci([r["delta"] for r in safe2_forward])

    bar_forward_sessions_met = len(sessions_forward) >= BAR_FORWARD_SESSIONS
    bar_forward_safe2_met = len(safe2_forward) >= BAR_FORWARD_SAFE2_SCORED
    bar_met = bar_forward_sessions_met and bar_forward_safe2_met

    decision_conditions = {
        "safe2_forward_ci_lower_gt_zero": (
            None if safe2_forward_ci is None or safe2_forward_ci.get("ci_lo") is None
            else safe2_forward_ci["ci_lo"] > 0),
        "recent_quarter_delta_ge_zero": (
            None if recent_quarter["delta"] is None else recent_quarter["delta"] >= 0),
        "four_big_days_all_ge_zero": big_days["all_ge_zero"] if not big_days["dates_missing"] else None,
        "runner_08_04_delta_ge_zero": (
            None if not runner["found"] else runner["delta"] >= 0),
    }
    conditions_known = [v for v in decision_conditions.values() if v is not None]
    all_conditions_met = bool(conditions_known) and all(conditions_known) and \
        len(conditions_known) == len(decision_conditions)

    if not forward_rows:
        status = "ARMED_AWAITING_FILLS"
    elif not bar_met:
        status = "ACCRUING"
    else:
        status = "BAR_MET_AWAITING_VERDICT"

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "forward_start_date": FORWARD_START_DATE,
        "treatment": {
            "profit_lock_arm_scope": "full",
            "profit_lock_arm_pct": TREATMENT_ARM_PCT,
            "min_time_in_trade_minutes_wrapper_only": TREATMENT_MIN_ARM_MINUTES,
            "trail_pct": "unchanged (canonical_shape(date)'s own value)",
            "live_knob_note": (
                "profit_lock_arm_pct IS a real exit_manager.py knob (ExitState.from_entry "
                "reads exit_shape['profit_lock_arm_pct']) -- no wrapper needed for that half. "
                "The 10-minute minimum-time-in-trade gate has NO live exit_manager.py "
                "equivalent (confirmed by grep this build) and is implemented ONLY in this "
                "shadow's walker wrapper (_walk_exit_manager_time_gated) by masking "
                "profit_lock_arm_scope to 'post_tp1' for bars < entry+10min. A positive "
                "forward verdict would still require a genuine live knob to be built before "
                "shipping -- that is a 2026-10-30+ item, not part of this shadow."),
        },
        "n_total_rows": n,
        "n_in_sample": len(in_sample_rows),
        "n_forward": len(forward_rows),
        "sessions_total": len(sessions_total),
        "sessions_forward": len(sessions_forward),
        "date_span_total": f"{sessions_total[0]}..{sessions_total[-1]}" if sessions_total else None,
        "date_span_forward": f"{sessions_forward[0]}..{sessions_forward[-1]}" if sessions_forward else None,
        "per_arm": per_arm,
        "safe2_trusted": {
            "n_all": len(safe2_all), "n_forward": len(safe2_forward),
            "sum_delta_all": round(sum(r["delta"] for r in safe2_all), 2) if safe2_all else 0.0,
            "sum_delta_forward": round(sum(r["delta"] for r in safe2_forward), 2) if safe2_forward else 0.0,
            "bootstrap_ci_forward": safe2_forward_ci,
        },
        "recent_quarter_delta_safe2_all_time": recent_quarter,
        "big_days": big_days,
        "runner_08_04": runner,
        "bar": {
            "forward_sessions_required": BAR_FORWARD_SESSIONS,
            "forward_sessions_accrued": len(sessions_forward),
            "forward_sessions_met": bar_forward_sessions_met,
            "forward_safe2_scored_required": BAR_FORWARD_SAFE2_SCORED,
            "forward_safe2_scored_accrued": len(safe2_forward),
            "forward_safe2_scored_met": bar_forward_safe2_met,
            "bar_met": bar_met,
        },
        "decision_conditions": decision_conditions,
        "all_decision_conditions_currently_met": all_conditions_met,
        "status": status,
        "no_ship_before": "2026-10-30 (config freeze; see prereg for the fuller reasoning)",
        "seen_data_disclosure": (
            "The four named big days and the 08-04 runner are all in_sample=True (dated "
            "<=2026-09-02) -- they are ALREADY-SEEN facts about this candidate's shape, not "
            "forward evidence, and are re-measured here as a disclosed prior every run, "
            "never as part of the forward bar count. Only safe2_trusted.bootstrap_ci_forward "
            "and the forward session/scored counts are genuinely un-seen at freeze time. This "
            "mirrors H4's own explicit warning that its +5%/15%-trail cell was SEEN data by "
            "the time it was reported -- the same caveat applies here to this V2 cell's "
            "backfill numbers, and remains true even after the forward bar is met: reaching "
            "the bar is permission to READ the verdict, never to ship it (prereg §6)."),
        "decision_rule_reminder": (
            "Ship-candidate ONLY if: safe2_forward_ci_lower_gt_zero AND "
            "recent_quarter_delta_ge_zero AND four_big_days_all_ge_zero AND "
            "runner_08_04_delta_ge_zero -- ALL FOUR, and even then this shadow ships nothing; "
            "see prereg §5-6."),
    }


def _input_health(events: list[dict]) -> dict:
    newest = max((e.get("date_et", "") for e in events), default="")
    import datetime as _dt
    today = _dt.date.today()
    back = 1 if today.weekday() != 0 else 3
    prev_session = today - _dt.timedelta(days=back)
    while prev_session.weekday() >= 5:
        prev_session -= _dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_ledger_newest_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- entry-quality-ledger.json has not advanced to the last "
                           "completed session; this clock is not being fed and its forward "
                           "counts are frozen, NOT a real absence of engine fills." if stale
                           else "fed")}


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Fail-open by contract, own scheduled task."""
    try:
        events = _load_closed_events()
        spy_map = pbc.spy_by_day()

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen_ids = {r.get("activity_id") for r in existing}
        todo = [e for e in events if e.get("activity_id") not in seen_ids]

        appended: list[dict] = []
        skipped: list[dict] = []
        for e in sorted(todo, key=lambda e: (e.get("date_et") or "", e.get("ts_et") or "")):
            row, reason = score_event(e, spy_map)
            if row is None:
                skipped.append({"activity_id": e.get("activity_id"), "reason": reason})
                continue
            appended.append(row)

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        all_rows = existing + appended
        summary = _summarize(all_rows)
        summary["new_this_run"] = len(appended)
        summary["skipped_this_run_count"] = len(skipped)
        summary["skipped_this_run_sample"] = skipped[:20]
        summary.update(_input_health(events))
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:400], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
