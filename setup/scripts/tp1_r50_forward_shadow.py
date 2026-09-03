#!/usr/bin/env python
"""tp1_r50_forward_shadow.py -- FORWARD ACCRUAL for R_tp100_f50 (queue.md
TP1-R50-FORWARD-SHADOW, HIGH, filed 2026-08-23 Opus adjudication).

BACKGROUND. R_tp100_f50 (TP1 at +100% premium, sell 50% instead of the live 66.7%) was
re-adjudicated on extended popA (n=213, commit 97f3c864) and STILL failed gate G4
(sub-window stability, >=3-of-4 fixed CALENDAR windows). The failure is STRUCTURAL, not
statistical: 2025H1 and 2026Q1 are CLOSED calendar windows with only 4 changed trades each,
so forward extension can never grow them past the floor -- G4 is unreachable for this cell
BY CONSTRUCTION, independent of how good the knob actually is. The cell's profile is
otherwise strong (7/8 gates pass, all 4 windows positive, runner_anchor +$628.05 POSITIVE,
p=0.002617, sole BH survivor of 28 cells). Full detail: the queue item itself and
analysis/recommendations/tp1-r50-readjudication-2026-08-23.json.

⛔ TWO THINGS THIS MODULE DELIBERATELY DOES NOT DO (per the queue item's own DO-NOTs):
  1. It does NOT re-spec G4 to let the cell pass -- rewriting a gate after seeing which
     cell it blocked is forking-paths, and the original prereg says the bar is not
     softened.
  2. It does NOT write a new backtest prereg on the SAME (already-seen) data -- popA is
     contaminated; that population's answer is already known.

THE ONLY CLEAN PATH (the queue item's words): build a forward counterfactual SHADOW
following the established stop_mode_shadow_ledger.py / day_throttle_shadow.py pattern --
nightly, per-trade delta of an f=0.5 TP1 sell vs the LIVE f=0.667 (ribbon_ride's own
tp1_qty_fraction), with a PRE-REGISTERED forward bar frozen BEFORE any data accrues
(analysis/recommendations/prereg-tp1-r50-forward-shadow-2026-09-03.md). Judge only on
forward data nobody has seen. This module is that clock.

WHAT IT MEASURES, PER TRADE (using ONLY recorded broker legs, never a re-simulation)
-------------------------------------------------------------------------------------
For every CLOSED ribbon_ride entry (setup in BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON) on an arm whose LIVE tp1_qty_fraction is 0.667:
  - the actual TP1 leg (first chronological SELL fill against that buy) and its price,
  - the actual runner leg(s) (every subsequent SELL fill against that buy) and their
    quantity-weighted average price.
The counterfactual moves `int(qty*0.667) - int(qty*0.5)` contracts (the ENGINE's own
int-floor rounding, exit_manager.ExitState.from_entry: `tp1_qty = int(qty * frac)`, read
not re-derived) from being sold at the TP1 price to riding to the runner's average exit
price. delta_pnl = qty_moved * (runner_avg_price - tp1_price) * multiplier. A trade whose
whole position closed in ONE sell leg never reached TP1 and contributes exactly $0 (counted
separately, `tp1_reached=False`). When qty_moved rounds to 0 (both fractions floor to the
same whole-contract count) the row is `no_op_rounding=True`, delta 0 -- honestly reported,
not silently dropped.

LIVE FRACTION IS CONFIRMED, NEVER HARDCODED. Per arm, per trade: read
`strategies.by_name("ribbon_ride").exit.tp1_qty_fraction` (0.667, the shipped cell) and
check accounts.json's `params_patch.exit_patch` for a per-arm override of that SAME key
(none exists today for any of the 6 SPY-option arms -- risky-1's own exit_patch overrides
`tp1_premium_pct`, a DIFFERENT knob, the TP1 *trigger* threshold not the *quantity split*;
confirmed by direct read this build). The resolved fraction + its provenance are recorded
on every row (`live_tp1_fraction` / `live_tp1_fraction_source`). Any arm whose resolved
fraction is not byte-identical to 0.667 is out of THIS study's scope and its trades are
skipped with a stated reason -- never silently included nor silently dropped without a
trace. A live per-position `automation/state/fleet/<arm>/exit-state.json` exists only while
a position is OPEN (confirmed empty/null for all 6 arms at build time -- there is no
historical per-trade record there), so it cannot source *closed*-trade fractions; the
static strategies.py + accounts.json config path above is the only source of truth for
history, exactly as `stop_mode_shadow_ledger.py` reads its control shape from the same
`strategies.py` registry rather than re-typing it.

EXTEND, DON'T FORK -- one source of truth each, no re-derivation:
  analysis/entry-quality/entry-quality-ledger.json   ENRICHED broker-truth fills (carries
                                                      `setup` via entry_quality_ledger's own
                                                      decision-ledger join; refreshed nightly
                                                      by the same producer stop_mode_shadow
                                                      already depends on)
  automation/state/fills-ledger.jsonl                 the RAW per-fill broker activity log
                                                      (each partial SELL is its own row) --
                                                      the ONLY place the TP1-vs-runner leg
                                                      split actually lives; this module's own
                                                      `_legs_by_activity_id` reproduces
                                                      entry_quality_ledger.build_population's
                                                      IDENTICAL (arm,symbol,date_et) FIFO
                                                      grouping so activity_id joins align,
                                                      but (unlike build_population, which
                                                      collapses every sell into one aggregate
                                                      pnl) keeps each sell as its own leg.
  automation/state/fleet/strategies.py                 ribbon_ride's ExitShape, read not typed
  automation/state/fleet/accounts.json                 per-arm params_patch.exit_patch, read
                                                        not typed
  automation/state/fleet/exit_manager.py               `ExitState.from_entry`'s int-floor
                                                        split (`int(qty * frac)`), READ not
                                                        re-derived, mirrored exactly here

NO BACKFILL. `ACCRUAL_START_DATE` is pinned to this build's own date (2026-09-03) -- the
queue item is explicit: "the clock starts at the first scheduled run", forward-only is the
whole point of building a shadow instead of re-reading popA.

COST: $0. Pure local computation over two already-written JSON/JSONL artifacts -- no bar
fetch, no OPRA, no replay, no LLM, no network call of any kind. Runs as its own scheduled
task (`Gamma_Tp1R50ForwardShadow`, 16:40 ET weekdays) rather than riding another fire's
try-block, matching the sibling `Gamma_DayThrottleShadow` / `Gamma_LadderRungShadow` slot.

Outputs:
  analysis/recommendations/tp1-r50-forward-shadow-ledger.jsonl   append-only, dedup on
                                                                  activity_id
  analysis/recommendations/tp1-r50-forward-shadow-summary.json   running totals + gate status
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "automation" / "state" / "fleet"), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
ACCOUNTS_PATH = REPO / "automation" / "state" / "fleet" / "accounts.json"
ENTRY_QUALITY_LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "tp1-r50-forward-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "tp1-r50-forward-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-tp1-r50-forward-shadow-2026-09-03.md"

ACCRUAL_START_DATE = "2026-09-03"     # this build's own date -- no backfill (queue item is explicit)
CF_FRACTION = 0.5                     # the counterfactual TP1 quantity fraction under test
LIVE_FRACTION_IN_SCOPE = 0.667        # ribbon_ride's shipped cell -- the study's scope
BAR_TRADING_DAYS = 20                 # pre-registered forward bar (a)
BAR_N_TP1 = 25                        # pre-registered forward bar (b)
RIBBON_ENTRY_SETUPS = frozenset({"BEARISH_REJECTION_RIDE_THE_RIBBON",
                                  "BULLISH_RECLAIM_RIDE_THE_RIBBON"})


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


# ------------------------------------------------------------------------------------------
# live fraction resolution -- confirmed from strategies.py + accounts.json, never hardcoded
# ------------------------------------------------------------------------------------------
def _live_fraction_for_arm(arm: str, ribbon_frac: float, exit_patches: dict) -> tuple[float, str]:
    patch = exit_patches.get(arm) or {}
    override = patch.get("tp1_qty_fraction")
    if override is not None:
        return float(override), (
            f"accounts.json arm {arm!r} params_patch.exit_patch OVERRIDES "
            f"tp1_qty_fraction={float(override)} (ribbon_ride's own shape is {ribbon_frac})")
    return ribbon_frac, (
        f"strategies.by_name('ribbon_ride').exit.tp1_qty_fraction={ribbon_frac}; "
        f"accounts.json arm {arm!r} params_patch.exit_patch carries no tp1_qty_fraction key")


# ------------------------------------------------------------------------------------------
# raw-fill FIFO leg extraction (mirrors entry_quality_ledger.build_population's grouping
# EXACTLY so activity_id joins line up -- see module docstring, EXTEND-DONT-FORK)
# ------------------------------------------------------------------------------------------
def _load_raw_fills() -> list[dict]:
    seen: set = set()
    fills: list[dict] = []
    if not FILLS_LEDGER.exists():
        return fills
    with FILLS_LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("is_option") or r.get("attribution") != "engine":
                continue
            aid = r.get("activity_id")
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            fills.append(r)
    fills.sort(key=lambda r: r["ts_utc"])
    return fills


def legs_by_activity_id(fills: list[dict]) -> dict[str, dict]:
    """Per-buy record of {legs: [{price,qty,ts_utc,ts_et}, ...], remaining, total_qty}.

    `legs` is ordered chronologically: legs[0] is always the FIRST sell fill against that buy
    (the TP1 partial, when TP1 was reached at all); legs[1:] are every subsequent sell (the
    runner exit, possibly split across a trail/time-stop sequence -- 'price(s)' in the queue
    item's own wording). Sorts defensively by ts_utc itself (never trusts the caller's
    ordering) -- `_load_raw_fills` already sorts, but this function's correctness must not
    depend on that invariant holding at every call site."""
    fills = sorted(fills, key=lambda r: r["ts_utc"])
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in fills:
        groups[(r["arm"], r["symbol"], r["date_et"])].append(r)

    by_activity: dict[str, dict] = {}
    for g in groups.values():
        buys = [dict(r, remaining=r["qty"], legs=[]) for r in g if r["side"] == "buy"]
        pending, active = collections.deque(buys), collections.deque()
        for r in g:
            if r["side"] == "buy":
                active.append(pending.popleft())
                continue
            sq = r["qty"]
            while sq > 1e-9 and active:
                b = active[0]
                take = min(sq, b["remaining"])
                b["remaining"] -= take
                b["legs"].append({"price": float(r["price"]), "qty": take,
                                   "ts_utc": r["ts_utc"], "ts_et": r.get("ts_et")})
                sq -= take
                if b["remaining"] <= 1e-9:
                    active.popleft()
        for b in buys:
            by_activity[b["activity_id"]] = {"legs": b["legs"], "remaining": b["remaining"],
                                              "total_qty": b["qty"]}
    return by_activity


# ------------------------------------------------------------------------------------------
# per-trade scoring
# ------------------------------------------------------------------------------------------
def score_trade(event: dict, legs_rec: dict | None, live_frac: float,
                 live_frac_src: str) -> dict | None:
    """Returns None (skip, never fabricate) when the raw fills-ledger does not show this
    activity fully closed -- a still-open or expired-without-a-sell-fill position carries no
    real TP1/runner legs to measure."""
    if legs_rec is None or legs_rec["remaining"] > 1e-6:
        return None

    total_qty = int(round(event["qty"]))
    multiplier = float(event.get("multiplier", 100))
    legs_sorted = sorted(legs_rec["legs"], key=lambda l: l["ts_utc"])
    n_legs = len(legs_sorted)

    # THE ENGINE'S OWN ROUNDING, mirrored exactly (exit_manager.ExitState.from_entry):
    #   frac = float(exit_shape.get("tp1_qty_fraction", 0.667)); tp1_qty = int(qty * frac)
    tp1_qty_live_r = int(total_qty * live_frac)
    tp1_qty_cf_r = int(total_qty * CF_FRACTION)
    qty_moved = tp1_qty_live_r - tp1_qty_cf_r

    row = {
        "activity_id": event["activity_id"], "order_id": event.get("order_id"),
        "date_et": event["date_et"], "ts_et": event["ts_et"], "arm": event["arm"],
        "symbol": event["symbol"], "opt_side": event.get("opt_side"), "setup": event.get("setup"),
        "total_qty": total_qty, "entry_price": float(event["price"]), "multiplier": multiplier,
        "live_tp1_fraction": live_frac, "live_tp1_fraction_source": live_frac_src,
        "counterfactual_tp1_fraction": CF_FRACTION,
        "n_sell_legs": n_legs,
        "tp1_qty_live_rounded": tp1_qty_live_r, "tp1_qty_cf_rounded": tp1_qty_cf_r,
        "qty_moved": qty_moved,
        "broker_pnl": event.get("pnl"),
    }

    if n_legs < 2:
        row.update({
            "tp1_reached": False, "tp1_price": None, "tp1_qty_observed": None,
            "tp1_qty_observed_matches_rounded": None,
            "runner_legs": [], "runner_avg_price": None,
            "no_op_rounding": False, "delta_pnl": 0.0,
            "note": ("single exit leg -- TP1 was never filled separately; a stop/time/trail "
                     "closed the whole position in one sell. Contributes $0 by definition, "
                     "counted in n_trades but NOT n_tp1_reached."),
        })
        return row

    tp1_leg, runner_legs = legs_sorted[0], legs_sorted[1:]
    runner_qty_sum = sum(l["qty"] for l in runner_legs)
    runner_avg_price = (sum(l["price"] * l["qty"] for l in runner_legs) / runner_qty_sum
                         if runner_qty_sum > 1e-9 else None)
    no_op = (qty_moved == 0)
    delta = 0.0 if (no_op or runner_avg_price is None) else round(
        qty_moved * (runner_avg_price - tp1_leg["price"]) * multiplier, 2)

    row.update({
        "tp1_reached": True, "tp1_price": tp1_leg["price"], "tp1_qty_observed": tp1_leg["qty"],
        "tp1_qty_observed_matches_rounded": (abs(tp1_leg["qty"] - tp1_qty_live_r) < 1e-6),
        "runner_legs": runner_legs,
        "runner_avg_price": (round(runner_avg_price, 4) if runner_avg_price is not None else None),
        "no_op_rounding": no_op,
        "delta_pnl": delta,
    })
    if no_op:
        row["note"] = ("both fractions floor to the SAME whole-contract TP1 count at this "
                        "qty -- rounding makes 0.667 and 0.5 no-ops for this trade size.")
    return row


# ------------------------------------------------------------------------------------------
# summary statistics (session-clustered bootstrap CI, top-3 concentration, ex-best-day)
# ------------------------------------------------------------------------------------------
def _bootstrap_day_clustered_mean(rows: list[dict], n_boot: int = 2000,
                                   seed: int = 20260903) -> dict | None:
    """Percentile bootstrap resampling trading DAYS with replacement (not trades), matching
    go_live_gate.bootstrap_pf_ci's methodology (day-resampling respects within-day trade
    correlation -- several ribbon entries in one session are not independent draws).
    Returns None when fewer than 2 distinct days -- a CI is not meaningful on n<2."""
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
    """Share of total |delta| explained by the 3 largest-magnitude per-trade deltas -- a
    magnitude-based concentration read (sign-agnostic) so a handful of trades cannot quietly
    carry the whole verdict either direction."""
    deltas = [r["delta_pnl"] for r in rows]
    total_abs = sum(abs(d) for d in deltas)
    if total_abs <= 1e-9:
        return 0.0
    top3_abs = sum(sorted((abs(d) for d in deltas), reverse=True)[:3])
    return round(top3_abs / total_abs, 4)


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    days = sorted({r["date_et"] for r in rows})
    if not n:
        return {"prereg": PREREG_REL, "generated_at_et": _stamp_now_et(),
                "accrual_start": ACCRUAL_START_DATE, "n_trades": 0, "n_tp1_reached": 0,
                "n_never_reached_tp1": 0, "n_no_op_rounding": 0, "sum_delta": 0.0,
                "mean_delta": None, "session_clustered_ci": None, "top3_concentration_share": 0.0,
                "days_accrued": 0, "days_to_bar": BAR_TRADING_DAYS, "tp1_reached_to_bar": BAR_N_TP1,
                "bar_met": False, "status": "ARMED_AWAITING_FILLS",
                "note": ("No qualifying ribbon_ride (live tp1_qty_fraction=0.667) closed "
                         "trades on/after the accrual start yet. An empty clock on day 0 is "
                         "expected, NOT a failure -- but a clock still empty after several "
                         "trading days means the upstream entry-quality-ledger stopped "
                         "feeding it.")}

    reached = [r for r in rows if r["tp1_reached"]]
    no_op = [r for r in rows if r.get("no_op_rounding")]
    sum_delta = round(sum(r["delta_pnl"] for r in rows), 2)
    mean_delta = round(sum_delta / n, 4)

    by_day_total: dict[str, float] = collections.defaultdict(float)
    for r in rows:
        by_day_total[r["date_et"]] += r["delta_pnl"]
    best_day_total = max(by_day_total.values(), default=0.0)
    ex_best_day_sum = round(sum_delta - best_day_total, 2)

    ci = _bootstrap_day_clustered_mean(rows)
    top3_share = _top3_concentration_share(rows)
    bar_met = (len(days) >= BAR_TRADING_DAYS) and (len(reached) >= BAR_N_TP1)

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "accrual_start": ACCRUAL_START_DATE,
        "n_trades": n,
        "n_tp1_reached": len(reached),
        "n_never_reached_tp1": n - len(reached),
        "n_no_op_rounding": len(no_op),
        "days_accrued": len(days),
        "date_span": f"{days[0]}..{days[-1]}" if days else None,
        "sum_delta": sum_delta,
        "mean_delta": mean_delta,
        "mean_delta_given_tp1_reached": (
            round(sum(r["delta_pnl"] for r in reached) / len(reached), 4) if reached else None),
        "ex_best_day_sum_delta": ex_best_day_sum,
        "session_clustered_ci": ci,
        "top3_concentration_share": top3_share,
        "days_to_bar": max(0, BAR_TRADING_DAYS - len(days)),
        "tp1_reached_to_bar": max(0, BAR_N_TP1 - len(reached)),
        "bar_met": bar_met,
        "status": "BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING",
        "decision_rule": (
            "This ledger NEVER ships R_tp100_f50 by itself. At days_accrued>=20 AND "
            f"n_tp1_reached>=25 it becomes eligible for the FROZEN decision rule in "
            f"{PREREG_REL}: ship-candidate only if session_clustered_ci.ci_lower_2.5 > 0 AND "
            "top3_concentration_share < 0.50 AND ex_best_day_sum_delta > 0. Reaching the bar "
            "is permission to READ the verdict, not to ship -- and the bar is not softened."),
    }


def _input_health(events: list[dict]) -> dict:
    """A clock whose INPUT silently stops updating reads exactly like a clock with nothing to
    report. Make the distinction visible rather than inferable (OP-33: silent failure is the
    only true failure)."""
    newest = max((e.get("date_et", "") for e in events), default="")
    today = dt.date.today()
    back = 1 if today.weekday() != 0 else 3          # Mon looks back to Fri
    prev_session = today - dt.timedelta(days=back)
    while prev_session.weekday() >= 5:                # skip Sat/Sun
        prev_session -= dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_ledger_newest_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- entry-quality-ledger.json has not advanced to the last "
                           "completed session; this clock is not being fed and its counts are "
                           "frozen, NOT a real absence of ribbon fills." if stale else "fed")}


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Fail-open by contract, own scheduled task (never folded into
    another producer's try-block)."""
    try:
        import strategies as fleet_strategies  # automation/state/fleet, read-only import

        ribbon = fleet_strategies.by_name("ribbon_ride")
        if ribbon is None:
            raise RuntimeError("strategies.by_name('ribbon_ride') returned None -- registry drift")
        ribbon_frac = float(ribbon.exit.tp1_qty_fraction)

        if not ACCOUNTS_PATH.exists():
            raise RuntimeError(f"accounts.json missing: {ACCOUNTS_PATH}")
        accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
        exit_patches: dict[str, dict] = {}
        for a in accounts.get("arms", []):
            patch = (a.get("params_patch") or {}).get("exit_patch") or {}
            exit_patches[a.get("id")] = patch

        if not ENTRY_QUALITY_LEDGER.exists():
            raise RuntimeError(f"enriched entry-quality ledger missing: {ENTRY_QUALITY_LEDGER}")
        doc = json.loads(ENTRY_QUALITY_LEDGER.read_text(encoding="utf-8"))
        events = doc.get("events", [])

        fresh = [e for e in events
                 if e.get("setup") in RIBBON_ENTRY_SETUPS
                 and e.get("date_et", "") >= ACCRUAL_START_DATE
                 and float(e.get("exit_qty") or 0) >= float(e.get("qty") or 0) - 1e-6]

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen_ids = {r.get("activity_id") for r in existing}
        todo = [e for e in fresh if e.get("activity_id") not in seen_ids]

        appended: list[dict] = []
        skipped: list[dict] = []
        if todo:
            raw_fills = _load_raw_fills()
            legs_index = legs_by_activity_id(raw_fills)
            for e in sorted(todo, key=lambda e: e["ts_et"]):
                live_frac, live_frac_src = _live_fraction_for_arm(e["arm"], ribbon_frac, exit_patches)
                if abs(live_frac - LIVE_FRACTION_IN_SCOPE) > 1e-9:
                    skipped.append({"activity_id": e.get("activity_id"),
                                     "reason": (f"arm {e['arm']} live tp1 fraction {live_frac} "
                                                f"!= {LIVE_FRACTION_IN_SCOPE} -- out of scope")})
                    continue
                legs_rec = legs_index.get(e["activity_id"])
                row = score_trade(e, legs_rec, live_frac, live_frac_src)
                if row is None:
                    skipped.append({"activity_id": e.get("activity_id"),
                                     "reason": "not fully closed in raw fills-ledger.jsonl "
                                               "(still open / no matching sell fill)"})
                    continue
                appended.append(row)

            if appended:
                with LEDGER.open("a", encoding="utf-8") as fh:
                    for r in appended:
                        fh.write(json.dumps(r) + "\n")

        summary = _summarize(existing + appended)
        summary["new_this_run"] = len(appended)
        summary["skipped_this_run"] = skipped
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
