#!/usr/bin/env python
"""walker_fidelity.py -- WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY runner (2026-09-03, RESEARCH).

QUESTION (from the queue item, verbatim intent): every exit-walk study in this repo validates
its harness on SIGN agreement only. The PDT-blocked-counterfactual's anchor set cleared 95.35%
sign agreement (n=43) while replaying to -$2,201.60 against an actual -$538.00 (~4x aggregate-
negative bias, median abs error $32.40). Is that bias explained by (a) coarse 5-min bars mis-
detecting intrabar touches, or (b) the walker's zero-slippage optimism on limit-style stages --
or something else? What magnitude criterion should sit beside the sign-agreement bar?

FINDING (this run, numbers below): NEITHER named candidate mechanism is the driver.
  - Slippage: toggling slippage 0.01 -> 0.00 on the 43-row PDT anchor moves the aggregate
    replay total by only ~$143 (~8.6% of the $1,663.60 gap).
  - Fill mode (bar-extreme vs bar-close vs mixed): the LOSER-side aggregate ratio is BIT-
    IDENTICAL across all three modes (1.5900444748546014, every digit) on the 43-row set --
    fill_mode has literally zero effect on how a losing leg prices.
  - Bar resolution (1-min vs 5-min, same walker, same fill_mode, paired on the 72 anchor rows
    both resolutions had cached bars for): loser-side ratio is AGAIN bit-identical
    (1.4296851574212892 either way). Rules out (a) for this walker.
  - Exit-stage agreement: the walker's own final leg stage matches the recorded (broker-truth)
    exit_reason on 29/32 losing anchor rows (91%); the 3 disagreeing rows carry only $33.50 of
    $1,769.20 total loser abs error (1.9%). Rules out "the walker picked a different event".

ROOT CAUSE (found by code reading, `backtest/tools/multileg_exit_walk.py`, confirmed by the
fill_mode/resolution invariance above): `ExitAction` (automation/state/fleet/exit_manager.py)
carries no `price` field, so `walk()`'s `px = getattr(a, "price", None)` is ALWAYS None, and
every non-tp1 SELL leg falls through to `state.runner_stop_premium or worst_in`.
`runner_stop_premium` is set at `ExitState.from_entry` to `entry_premium * (1 + stop_pct)`
(exit_manager.py:290) and is NEVER None after entry -- so `worst_in` (the bar price `fill_mode`
is supposed to control) is dead code for every stage except tp1. structure_stop, ribbon_flip,
and time_stop -- market-style exits that should fill at whatever the option was actually
trading when the live event fired -- instead silently price at the STATIC catastrophe/premium-
stop level, regardless of which stage actually triggered them. Direct evidence: replayed loss
% on structure-mode anchor rows clusters at -50.7% to -51.9% (catastrophe_stop_pct = -50%) and
premium-mode rows cluster at -20.6% to -21.3% (premium_stop_pct = -20%), while the ACTUAL
realized loss % on those SAME rows ranges from -6% to -55% -- the walker prices every stop-out
as the worst case, never where the live exit really fired.

FIX SHIPPED THIS RUN, BEHIND A FLAG (multileg_exit_walk.walk(..., market_stage_fill_fix=True),
default False -- every existing caller of `walk()` is byte-identical unless it opts in, same
discipline as exit_manager_walk.py's `all_exits_market` kwarg): market-stage legs
(structure_stop/ribbon_flip/time_stop) now price at the bar's own worst-case price instead of
the static stop level. BEFORE/AFTER on the 43-row PDT anchor (fill_mode="extreme",
slippage=0.01, everything else unchanged): aggregate_ratio 4.092 -> 2.836, median_abs_error
$32.40 -> $31.80. Real, meaningful (39.8% reduction in |ratio-1| excess), NOT a full fix --
still fails the magnitude criterion below. The remaining gap is not diagnosed further here.

MAGNITUDE CRITERION (implemented in backtest/lib/walker_magnitude_fidelity.py, shared by this
study, whole_engine_null.py, and pdt_blocked_counterfactual.py): N>=20 (this repo's standing
decision floor), |aggregate_ratio-1| <= 0.40, median_abs_error_dollars <= $40 -- both derived
from whole_engine_null.py's V9 (n=121, 2026-09-02: aggregate_ratio 0.6452, median_abs_error
$15.00), the best-attested walker application in this repo, with the tolerance set generously
above V9's own numbers rather than fitted flush to them. See that module for the full
derivation and why both conditions are required.

VERDICT ON THE 3 OUTSTANDING PREREG RUNS: they use `multileg_exit_walk.walk()` (same walker as
the PDT study, via `harness_fidelity_anchor.py` / a sibling harness), which this run shows
FAILS the magnitude criterion even after the market-stage fix. Their dollar-denominated gates
(G1-G4 style, net $, drop-best $) stay SIGN-trustworthy, MAGNITUDE-suspect -- unchanged from
this item's original caveat, now quantified rather than asserted.

$0, deterministic, no network (every bar source is a pre-fetched on-disk cache; a missing
cache is reported as skipped, never estimated). Writes only under analysis/harness-fidelity/.
"""
from __future__ import annotations

import json
import statistics as stt
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as pd  # noqa: E402

import pdt_blocked_counterfactual as pdtc  # noqa: E402 -- reuse anchor-row machinery
import whole_engine_null as wen  # noqa: E402 -- reuse V9's OWN P1 anchor-population machinery
from multileg_exit_walk import walk as walk_multileg  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
import refused_setup_ledger as refusals  # noqa: E402 -- 1-min highres cache reuse
from walker_magnitude_fidelity import (  # noqa: E402
    magnitude_fidelity, evaluate_magnitude_fidelity, stage_decomposition, side_decomposition,
    MAGNITUDE_FIDELITY_MIN_N, AGGREGATE_RATIO_TOLERANCE, MEDIAN_ABS_ERROR_DOLLARS_MAX,
)

OUT_DIR = REPO / "analysis" / "harness-fidelity"
OUT_JSON = OUT_DIR / "WALKER-MAGNITUDE-2026-09-03.json"
OUT_MD = OUT_DIR / "WALKER-MAGNITUDE-2026-09-03.md"

# The larger anchor set the task named: every safe-2/bold-2 engine-attributed row
# trades-enriched.jsonl supports, not just the PDT study's original 2026-07-08..08-07 window.
BIG_WINDOW_START = "2026-06-01"
BIG_WINDOW_END = "2026-09-02"

V9_REFERENCE = REPO / "analysis" / "whole-engine-null" / "2026-09-02.json"  # already-shipped
                                                                             # exit_manager_walk (1-min) numbers, reused not recomputed


def log(msg: str) -> None:
    print(f"[walker-fidelity] {msg}", flush=True)


# ============================================================================================ #
# 1. THE MULTILEG WALKER (5-min OPRA, matches pdt_blocked_counterfactual.py /
#    harness_fidelity_anchor.py exactly when called with default kwargs)
# ============================================================================================ #
def _get_1min_df(symbol: str, date: str) -> Optional[pd.DataFrame]:
    """Cache-only 1-minute bars (backtest/data/highres/, built by refused_setup_ledger's daily
    fire) -- NO network fetch. Returns None (honest gap) when nothing is cached."""
    try:
        bars = refusals._load_highres(symbol, date)
    except Exception:  # noqa: BLE001 -- a malformed/legacy cache row is a gap, not a crash
        return None
    if not bars:
        return None
    rows = [{"t": t, "open": o, "high": h, "low": lo, "close": c} for (t, o, h, lo, c) in bars]
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(date + " " + df["t"])
    return df[["timestamp_et", "open", "high", "low", "close"]]


def walk_anchor_row(r: dict, bars: pd.DataFrame, spy_map: dict, *, fill_mode: str = "extreme",
                    slippage: float = 0.01, market_stage_fill_fix: bool = False) -> Optional[dict]:
    """One anchor row through multileg_exit_walk, using the SAME shape/trigger resolution
    pdt_blocked_counterfactual.py's own harness_validation() uses (reused, not reimplemented)."""
    shape = pdtc.canonical_shape(r["date"])
    mode = r.get("stop_mode")
    if mode in ("structure", "premium"):
        shape = dict(shape)
        shape["stop_mode"] = mode
    trig = pdtc.anchor_trigger_level(r)
    fill = {"entry_premium": r["entry_px"], "qty": int(r["qty"]), "symbol": r["symbol"],
            "date": r["date"], "entry_time": r["entry_ts_et"][11:19], "strategy": "RIBBON"}
    res = walk_multileg(fill, shape, bars, trigger_level=trig, fill_mode=fill_mode,
                        spy_closes=spy_map.get(r["date"]), slippage=slippage,
                        market_stage_fill_fix=market_stage_fill_fix)
    if "error" in res:
        return None
    return {
        "symbol": r["symbol"], "date": r["date"], "arm": r["arm"], "right": r.get("right"),
        "actual": float(r["pnl_dollars"]), "replay": res["pnl"],
        "recorded_exit_reason": r.get("exit_reason"), "recorded_stop_mode": mode,
        "walked_final_stage": (res["legs"][-1]["stage"] if res["legs"] else None),
        "n_legs": res.get("n_legs", 0),
    }


def run_multileg_variant(rows: list[dict], spy_map: dict, resolution: str = "5min", *,
                         fill_mode: str = "extreme", slippage: float = 0.01,
                         market_stage_fill_fix: bool = False) -> tuple[list[dict], int]:
    """Walks every anchor row via multileg_exit_walk. `resolution` picks the bar source:
    "5min" -> load_contract_bars (OPRA cache, matches every prior study); "1min" -> the
    highres 1-minute cache (cache-only, honest None on a miss -- see _get_1min_df)."""
    cache: dict = {}
    out: list[dict] = []
    n_missing = 0
    for r in rows:
        sym = r["symbol"]
        if resolution == "5min":
            if sym not in cache:
                try:
                    cache[sym] = load_contract_bars(sym)
                except Exception:  # noqa: BLE001
                    cache[sym] = None
            bars = cache[sym]
        else:
            bars = _get_1min_df(sym, r["date"])
        if bars is None or bars.empty:
            n_missing += 1
            continue
        row = walk_anchor_row(r, bars, spy_map, fill_mode=fill_mode, slippage=slippage,
                              market_stage_fill_fix=market_stage_fill_fix)
        if row is None:
            n_missing += 1
            continue
        out.append(row)
    return out, n_missing


# ============================================================================================ #
# 2. MECHANISM TESTS
# ============================================================================================ #
def _loser_ratio(rows: list[dict]) -> Optional[float]:
    loss = [r for r in rows if r["actual"] < 0]
    den = sum(r["actual"] for r in loss)
    return round(sum(r["replay"] for r in loss) / den, 6) if abs(den) > 1e-9 else None


def mechanism_slippage(anchor_43: list[dict], spy_map: dict) -> dict:
    r_slip, _ = run_multileg_variant(anchor_43, spy_map, "5min", slippage=0.01)
    r_noslip, _ = run_multileg_variant(anchor_43, spy_map, "5min", slippage=0.0)
    a = sum(r["actual"] for r in r_slip)
    tot_slip = sum(r["replay"] for r in r_slip)
    tot_noslip = sum(r["replay"] for r in r_noslip)
    gap = tot_slip - a  # the total error this run is trying to explain
    contribution = tot_slip - tot_noslip
    return {
        "n": len(r_slip), "actual_total": round(a, 2),
        "replay_total_slip_1c": round(tot_slip, 2), "replay_total_slip_0c": round(tot_noslip, 2),
        "slippage_contribution_dollars": round(contribution, 2),
        "total_gap_dollars": round(gap, 2),
        "slippage_share_of_gap": round(contribution / gap, 4) if abs(gap) > 1e-9 else None,
        "verdict": "RULED OUT as dominant" if abs(contribution) < 0.25 * abs(gap) else "MATERIAL",
    }


def mechanism_fill_mode(anchor_43: list[dict], spy_map: dict) -> dict:
    out = {}
    for fm in ("extreme", "close", "mixed"):
        rows, _ = run_multileg_variant(anchor_43, spy_map, "5min", fill_mode=fm, slippage=0.01)
        out[fm] = {"loser_ratio": _loser_ratio(rows),
                   "winner_ratio": _winner_ratio(rows)}
    lr = {v["loser_ratio"] for v in out.values()}
    return {
        "by_fill_mode": out,
        "loser_ratio_invariant": len(lr) == 1,
        "verdict": ("RULED OUT as loser-side driver (loser_ratio identical across fill modes)"
                    if len(lr) == 1 else "MATERIAL (loser_ratio varies by fill mode)"),
    }


def _winner_ratio(rows: list[dict]) -> Optional[float]:
    wins = [r for r in rows if r["actual"] > 0]
    den = sum(r["actual"] for r in wins)
    return round(sum(r["replay"] for r in wins) / den, 6) if abs(den) > 1e-9 else None


def mechanism_bar_resolution(big_rows: list[dict], spy_map: dict) -> dict:
    r5, n_missing5 = run_multileg_variant(big_rows, spy_map, "5min", slippage=0.01)
    r1, n_missing1 = run_multileg_variant(big_rows, spy_map, "1min", slippage=0.01)
    keys5 = {(r["symbol"], r["date"]): r for r in r5}
    keys1 = {(r["symbol"], r["date"]): r for r in r1}
    common = sorted(set(keys5) & set(keys1))
    if len(common) < MAGNITUDE_FIDELITY_MIN_N:
        return {"n_common": len(common), "note": "DATA_MISSING: too few rows with both a 5-min "
                "OPRA cache and a 1-min highres cache to test this mechanism at n>=20",
                "verdict": "INCONCLUSIVE (insufficient paired n)"}
    s5 = [keys5[k] for k in common]
    s1 = [keys1[k] for k in common]
    lr5, lr1 = _loser_ratio(s5), _loser_ratio(s1)
    wr5, wr1 = _winner_ratio(s5), _winner_ratio(s1)
    invariant = lr5 is not None and lr1 is not None and abs(lr5 - lr1) < 1e-6
    return {
        "n_common": len(common), "n_5min_missing": n_missing5, "n_1min_missing": n_missing1,
        "loser_ratio_5min": lr5, "loser_ratio_1min": lr1,
        "winner_ratio_5min": wr5, "winner_ratio_1min": wr1,
        "loser_ratio_invariant": invariant,
        "verdict": ("RULED OUT as loser-side driver (loser_ratio identical 1-min vs 5-min)"
                    if invariant else "MATERIAL (loser_ratio differs by bar resolution)"),
    }


def mechanism_stage_agreement(anchor_43: list[dict]) -> dict:
    losers = [r for r in anchor_43 if r["actual"] < 0]
    decomp = stage_decomposition(
        losers, real_key="actual", walk_key="replay",
        recorded_stage_key="recorded_exit_reason", walked_stage_key="walked_final_stage")
    share = decomp["disagree_share_of_total_abs_error"]
    return {
        "n_losers": len(losers), "decomposition": decomp,
        "verdict": ("RULED OUT as dominant (stage-mismatch is a small minority of loser error)"
                    if share is not None and share < 0.25 else
                    "MATERIAL (stage-mismatch carries a large share of loser error)"),
    }


def mechanism_market_stage_fill_bug(anchor_43: list[dict], spy_map: dict) -> dict:
    """The fix this run actually shipped (behind market_stage_fill_fix=False default) --
    before/after on the same 43-row PDT anchor, everything else held fixed."""
    before, _ = run_multileg_variant(anchor_43, spy_map, "5min", slippage=0.01,
                                     market_stage_fill_fix=False)
    after, _ = run_multileg_variant(anchor_43, spy_map, "5min", slippage=0.01,
                                    market_stage_fill_fix=True)
    mag_before = magnitude_fidelity([(r["actual"], r["replay"]) for r in before])
    mag_after = magnitude_fidelity([(r["actual"], r["replay"]) for r in after])
    excess_before = abs((mag_before.get("aggregate_ratio") or 1.0) - 1.0)
    excess_after = abs((mag_after.get("aggregate_ratio") or 1.0) - 1.0)
    return {
        "before": mag_before, "after": mag_after,
        "excess_ratio_reduction_pct": (round((1 - excess_after / excess_before) * 100, 1)
                                       if excess_before > 1e-9 else None),
        "verdict_before": evaluate_magnitude_fidelity(mag_before),
        "verdict_after": evaluate_magnitude_fidelity(mag_after),
    }


def load_v9_anchor_rows() -> list[dict]:
    """The engine's OWN entries -- reuses whole_engine_null.py's own P1 population machinery
    (load_engine_rows + build_populations["P1_post_ladder"]) verbatim rather than
    reimplementing the date/arm/attribution filter, per WALKER-MARKET-STAGE-FILL-ROOT-FIX's
    instruction to validate on "the whole-engine V9 anchor". Row schema is IDENTICAL to
    pdtc.load_anchor_sample()'s rows (both read raw analysis/trades-enriched.jsonl lines) --
    confirmed by field-for-field comparison against run_v9()'s own row access (symbol, right,
    date, entry_ts_et, entry_px, qty, stop_mode, trigger_level, pnl_dollars, arm, exit_reason)
    -- so walk_anchor_row()/run_multileg_variant() below need no adaptation. This population
    is genuinely INDEPENDENT of the 43-row PDT anchor: different date window (P1_START
    2026-08-11 onward vs the PDT anchor's 2026-07-08..08-07), different arm set (safe-2/
    bold-2/safe-3/risky-1 vs safe-2/bold-2 only). whole_engine_null.py itself is NOT edited by
    this call -- only its pure population-loading functions are reused, read-only."""
    rows = wen.load_engine_rows()
    return wen.build_populations(rows)["P1_post_ladder"]


def v9_anchor_via_multileg(spy_map: dict) -> dict:
    """Re-validates the market-stage fill fix on the V9 anchor population, walked through THE
    SAME multileg_exit_walk.py this session fixed -- independent of exit_manager_walk.py (the
    walker V9 itself uses, untouched by this session). Answers: does the fix generalize beyond
    the 43-row PDT anchor, or is it overfit to that specific population?"""
    v9_rows = load_v9_anchor_rows()
    before, n_missing_before = run_multileg_variant(v9_rows, spy_map, "5min", slippage=0.01,
                                                     market_stage_fill_fix=False)
    after, n_missing_after = run_multileg_variant(v9_rows, spy_map, "5min", slippage=0.01,
                                                   market_stage_fill_fix=True)
    mag_before = magnitude_fidelity([(r["actual"], r["replay"]) for r in before])
    mag_after = magnitude_fidelity([(r["actual"], r["replay"]) for r in after])
    excess_before = abs((mag_before.get("aggregate_ratio") or 1.0) - 1.0)
    excess_after = abs((mag_after.get("aggregate_ratio") or 1.0) - 1.0)
    return {
        "n_rows_loaded": len(v9_rows), "n_missing_bars_before": n_missing_before,
        "n_missing_bars_after": n_missing_after,
        "before": mag_before, "after": mag_after,
        "excess_ratio_reduction_pct": (round((1 - excess_after / excess_before) * 100, 1)
                                       if excess_before > 1e-9 else None),
        "verdict_before": evaluate_magnitude_fidelity(mag_before),
        "verdict_after": evaluate_magnitude_fidelity(mag_after),
    }


# ============================================================================================ #
# 3. ORCHESTRATION
# ============================================================================================ #
def main() -> int:
    deviations: list[str] = []
    log("loading anchor populations (reusing pdt_blocked_counterfactual.load_anchor_sample)...")
    anchor_43 = pdtc.load_anchor_sample()  # original PDT window, for exact reproduction
    anchor_big = pdtc.load_anchor_sample(window_start=BIG_WINDOW_START, window_end=BIG_WINDOW_END)
    log(f"  n_anchor_pdt_window={len(anchor_43)}  n_anchor_big_window={len(anchor_big)}")
    spy_map = pdtc.spy_by_day()

    # -- reproduce the PDT study's own headline numbers as an integrity check ---------------
    repro, n_missing_repro = run_multileg_variant(anchor_43, spy_map, "5min", slippage=0.01)
    mag_repro = magnitude_fidelity([(r["actual"], r["replay"]) for r in repro])
    sign_ok = sum(1 for r in repro if (r["actual"] > 0) == (r["replay"] > 0)
                 or abs(r["replay"] - r["actual"]) < 1e-9)
    repro_ok = (len(repro) == 43 and abs(mag_repro["actual_total_dollars"] - (-538.0)) < 0.01
               and abs(mag_repro["replay_total_dollars"] - (-2201.6)) < 0.01)
    log(f"  REPRODUCTION CHECK: n={len(repro)} actual={mag_repro['actual_total_dollars']} "
        f"replay={mag_repro['replay_total_dollars']} sign_agreement={sign_ok/len(repro):.4f} "
        f"-> {'MATCHES queue-item numbers exactly' if repro_ok else 'DID NOT MATCH -- see deviations'}")
    if not repro_ok:
        deviations.append("Reproduction of the PDT study's own anchor numbers did not match "
                          "exactly -- the ledger/cache may have changed since 2026-09-02. "
                          "Proceeding with THIS run's numbers, disclosed as found not forced.")

    # -- mechanism tests ----------------------------------------------------------------------
    log("mechanism (b) part 1/2: slippage contribution...")
    mech_slippage = mechanism_slippage(anchor_43, spy_map)
    log(f"  {mech_slippage['verdict']}: slippage explains "
        f"{mech_slippage['slippage_share_of_gap']:.1%} of the gap"
        if mech_slippage.get("slippage_share_of_gap") is not None else "  n/a")

    log("mechanism (b) part 2/2: fill-mode (extreme/close/mixed) sensitivity...")
    mech_fill_mode = mechanism_fill_mode(anchor_43, spy_map)
    log(f"  {mech_fill_mode['verdict']}")

    log("mechanism (a): bar resolution (1-min vs 5-min), paired same-walker comparison...")
    mech_resolution = mechanism_bar_resolution(anchor_big, spy_map)
    log(f"  {mech_resolution['verdict']}")

    log("stage-agreement decomposition (does the walker pick the wrong EVENT)...")
    mech_stage = mechanism_stage_agreement(repro)
    log(f"  {mech_stage['verdict']}")

    log("ROOT CAUSE + FIX: market-stage fill bug in multileg_exit_walk.walk() "
        "(structure_stop/ribbon_flip/time_stop always price at the static stop level, "
        "never the bar's real price) -- before/after with market_stage_fill_fix=True...")
    mech_fix = mechanism_market_stage_fill_bug(anchor_43, spy_map)
    log(f"  aggregate_ratio {mech_fix['before']['aggregate_ratio']} -> "
        f"{mech_fix['after']['aggregate_ratio']}  "
        f"(verdict {mech_fix['verdict_before']} -> {mech_fix['verdict_after']}, "
        f"excess-ratio reduced {mech_fix['excess_ratio_reduction_pct']}%)")

    log("re-validating the fix on the WHOLE-ENGINE V9 anchor (whole_engine_null.py's own P1 "
        "population, walked through multileg_exit_walk -- independent of the 43-row PDT "
        "anchor and of exit_manager_walk.py, the walker V9 itself uses)...")
    mech_v9 = v9_anchor_via_multileg(spy_map)
    log(f"  n={mech_v9['n_rows_loaded']}  aggregate_ratio {mech_v9['before']['aggregate_ratio']} "
        f"-> {mech_v9['after']['aggregate_ratio']}  "
        f"(verdict {mech_v9['verdict_before']} -> {mech_v9['verdict_after']})")

    # -- decomposition by side, on the big anchor set (unfixed, matches every prior study) ---
    big_rows, n_missing_big = run_multileg_variant(anchor_big, spy_map, "5min", slippage=0.01)
    mag_big = magnitude_fidelity([(r["actual"], r["replay"]) for r in big_rows])
    by_side = side_decomposition(big_rows, real_key="actual", walk_key="replay", side_key="right")
    stage_decomp_big = stage_decomposition(
        big_rows, real_key="actual", walk_key="replay",
        recorded_stage_key="recorded_exit_reason", walked_stage_key="walked_final_stage")

    # -- apply the criterion to every variant this run produced -------------------------------
    criterion_applications = {
        "pdt_original_anchor_n43_unfixed": {
            "magnitude_fidelity": mag_repro,
            "verdict": evaluate_magnitude_fidelity(mag_repro),
        },
        "pdt_original_anchor_n43_market_stage_fix": {
            "magnitude_fidelity": mech_fix["after"],
            "verdict": mech_fix["verdict_after"],
        },
        "big_anchor_n_unfixed": {
            "n_missing": n_missing_big,
            "magnitude_fidelity": mag_big,
            "verdict": evaluate_magnitude_fidelity(mag_big),
        },
        "v9_anchor_via_multileg_unfixed": {
            "magnitude_fidelity": mech_v9["before"],
            "verdict": mech_v9["verdict_before"],
        },
        "v9_anchor_via_multileg_market_stage_fix": {
            "magnitude_fidelity": mech_v9["after"],
            "verdict": mech_v9["verdict_after"],
        },
    }
    v9_ref = None
    if V9_REFERENCE.exists():
        v9_doc = json.loads(V9_REFERENCE.read_text(encoding="utf-8"))
        v9_mag = v9_doc.get("v9_harness_validation", {}).get("magnitude_fidelity")
        if v9_mag:
            v9_ref = {"source": str(V9_REFERENCE.relative_to(REPO)), "n": v9_mag.get("n"),
                      "aggregate_ratio": v9_mag.get("aggregate_ratio"),
                      "median_abs_error_dollars": v9_mag.get("median_abs_error_dollars"),
                      "verdict": evaluate_magnitude_fidelity(v9_mag),
                      "note": "exit_manager_walk (1-min bars, point-sample fill) via "
                             "whole_engine_null.py's V9 -- REUSED from its own last shipped "
                             "run, not recomputed here (that study owns its own re-run "
                             "cadence). This is the reference the criterion's tolerance was "
                             "anchored against -- see walker_magnitude_fidelity.py."}
    criterion_applications["v9_exit_manager_walk_reference"] = v9_ref

    doc = {
        "study": "WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY", "date": "2026-09-03",
        "label": "RESEARCH", "verdict_scope": "harness fidelity only -- decides no strategy, "
                                              "places no order, arms nothing",
        "criterion": {
            "min_n": MAGNITUDE_FIDELITY_MIN_N,
            "aggregate_ratio_tolerance": AGGREGATE_RATIO_TOLERANCE,
            "median_abs_error_dollars_max": MEDIAN_ABS_ERROR_DOLLARS_MAX,
            "derivation": ("Anchored to whole_engine_null.py's V9 (n=121, 2026-09-02 run): "
                          "aggregate_ratio 0.6452, median_abs_error $15.00 -- the best-"
                          "attested walker application in this repo (it gates a frozen "
                          "prereg's own verdict). Tolerance set generously ABOVE those "
                          "numbers so V9 clears with room rather than being fitted flush to "
                          "it; the PDT anchor's own numbers (ratio 4.09, median $32.40) fail "
                          "the ratio leg by a wide margin (|4.09-1|=3.09 >> 0.40) even though "
                          "its median alone would pass -- which is why both conditions are "
                          "required, not either."),
        },
        "reproduction_check": {"matches_queue_item_numbers": repro_ok,
                              "n": len(repro), "sign_agreement": round(sign_ok / len(repro), 4),
                              "magnitude_fidelity": mag_repro},
        "mechanism_tests": {
            "slippage_contribution": mech_slippage,
            "fill_mode_sensitivity": mech_fill_mode,
            "bar_resolution_sensitivity": mech_resolution,
            "stage_agreement": mech_stage,
        },
        "root_cause_and_fix": {
            "location": "backtest/tools/multileg_exit_walk.py#walk (research tool, not "
                        "trading-path)",
            "mechanism": ("ExitAction carries no `price` field, so every non-tp1 SELL leg "
                         "fell through to `state.runner_stop_premium or worst_in`. "
                         "runner_stop_premium is set at entry to entry_premium*(1+stop_pct) "
                         "and is never None afterward, so worst_in (the bar price fill_mode "
                         "controls) was dead code for structure_stop/ribbon_flip/time_stop -- "
                         "every one of those market-style exits priced at the STATIC "
                         "catastrophe/premium-stop level instead of the bar's real price."),
            "fix": "market_stage_fill_fix=True kwarg on walk(), default False (byte-identical "
                  "for every existing caller until it opts in).",
            "before_after": mech_fix,
            "root_fix_2026_09_03_followup": {
                "queue_item": "WALKER-MARKET-STAGE-FILL-ROOT-FIX",
                "what_changed": ("time_stop ONLY: moved out of the worst_in bucket into its "
                                 "own bar-CLOSE price (a clock event has no price-cross to "
                                 "reuse). structure_stop/ribbon_flip unchanged (still worst_in "
                                 "-- no premium threshold exists for either)."),
                "what_was_tried_and_reverted": ("Extending _MARKET_STAGES to premium_stop, "
                                                "profit_lock_floor, trail, be_stop, "
                                                "runner_target (reasoning: a live market SELL "
                                                "always crosses the bid). MEASURED WORSE on "
                                                "the 43-row PDT anchor: aggregate_ratio "
                                                "4.09 -> 4.88 (not better), driven almost "
                                                "entirely by premium_stop (stage abs error "
                                                "$516.90 -> $930.00). These 4 stages are "
                                                "numeric-threshold crossings of "
                                                "runner_stop_premium; the live engine polls "
                                                "once/minute and fires the instant a poll "
                                                "crosses, so the true fill sits near the "
                                                "THRESHOLD, not the coarse 5-min bar's full "
                                                "wick -- state.runner_stop_premium (unchanged, "
                                                "the OLD/default fallback) already models "
                                                "that. See multileg_exit_walk.py's own "
                                                "module-level note for the full account."),
            },
        },
        "big_anchor_population": {
            "window": [BIG_WINDOW_START, BIG_WINDOW_END], "n_rows_loaded": len(anchor_big),
            "n_walked": len(big_rows), "n_missing_bars": n_missing_big,
            "magnitude_fidelity": mag_big,
            "magnitude_fidelity_verdict": evaluate_magnitude_fidelity(mag_big),
            "decomposition_by_side": by_side,
            "decomposition_by_stage_agreement": stage_decomp_big,
        },
        "v9_anchor_validation": {
            "note": ("Re-validates the market-stage fill fix on whole_engine_null.py's OWN P1 "
                    "population (load_engine_rows + build_populations['P1_post_ladder']), "
                    "walked through multileg_exit_walk (the walker THIS session fixed) -- "
                    "independent of exit_manager_walk.py (the walker V9 itself uses, "
                    "untouched here) and independent of the 43-row PDT anchor (different date "
                    "window, different arm set: safe-2/bold-2/safe-3/risky-1 vs safe-2/bold-2 "
                    "only)."),
            "n_rows_loaded": mech_v9["n_rows_loaded"],
            "n_missing_bars_before": mech_v9["n_missing_bars_before"],
            "n_missing_bars_after": mech_v9["n_missing_bars_after"],
            "before": mech_v9["before"], "after": mech_v9["after"],
            "verdict_before": mech_v9["verdict_before"], "verdict_after": mech_v9["verdict_after"],
            "excess_ratio_reduction_pct": mech_v9["excess_ratio_reduction_pct"],
        },
        "criterion_applied_to_every_variant": criterion_applications,
        "outstanding_prereg_runs_magnitude_readable": {
            "recency-qty-clamp": "NO -- shares multileg_exit_walk with the PDT study; this "
                                 "run shows that walker fails the magnitude criterion even "
                                 "after the market-stage fix. Sign-trustworthy, dollar-"
                                 "suspect, unchanged from this item's original caveat.",
            "runner-finite-tgt": "NO -- same walker family, same caveat.",
            "profit-lock-arm-scope": "NO -- same walker family; ALSO carries its own named "
                                    "sim-vs-live profit-lock scope divergence (queue item's "
                                    "own caveat) on top of this one.",
        },
        "known_limitations": [
            f"big_anchor_population's aggregate_ratio ({mag_big.get('aggregate_ratio')}) is "
            f"inflated by a near-zero denominator: actual_total_dollars="
            f"{mag_big.get('actual_total_dollars')} is a small difference between winners "
            f"(${(mag_big.get('winners') or {}).get('actual')}) and losers "
            f"(${(mag_big.get('losers') or {}).get('actual')}) that mostly cancel. The "
            f"winners_ratio ({(mag_big.get('winners') or {}).get('ratio')}) and losers_ratio "
            f"({(mag_big.get('losers') or {}).get('ratio')}) are the trustworthy read here, "
            "not the aggregate ratio alone -- same caveat whole_engine_null.py's own "
            "magnitude_fidelity note already carries for exactly this reason.",
            "The market-stage fill fix is NOT a full fix -- aggregate_ratio improved but did "
            "not reach the criterion, on either anchor. Stage-level decomposition on the "
            "43-row PDT anchor (post-fix) attributes the LARGEST remaining abs error to "
            "premium_stop ($811.50 of ~$1,780 total, n=22 legs) and structure_stop ($581.00, "
            "n=13), with trail a distant third ($387.50, n=8) -- premium_stop was NOT touched "
            "by this session's fix (see root_cause_and_fix.root_fix_2026_09_03_followup) and "
            "its residual error is a TIMING gap (the 5-min bar's own stop-crossing bar may not "
            "be the exact minute the live once-a-minute poll actually fired on), not a within-"
            "bar PRICING gap this module's fill_mode knob can address -- not diagnosed further "
            "by this run per the queue item's 'do not tune anything else to make the number "
            "move' instruction.",
            "mechanism_bar_resolution restricts to rows with BOTH a 5-min OPRA cache and a "
            "1-min highres cache (paired comparison) -- a smaller n than the full anchor set; "
            "see n_common.",
            "This study reuses pdt_blocked_counterfactual.py's shape/trigger-level resolution "
            "for every variant (canonical_shape / anchor_trigger_level) rather than "
            "reimplementing it -- any defect in THAT resolution logic is inherited here too, "
            "not independently re-verified.",
        ],
        "deviations": deviations,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    OUT_MD.write_text(_render_md(doc), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"wrote {OUT_MD}")
    return 0


def _render_md(doc: dict) -> str:
    c = doc["criterion"]
    rc = doc["root_cause_and_fix"]
    bf = rc["before_after"]
    big = doc["big_anchor_population"]
    lines = [
        f"# {doc['study']} ({doc['date']}) -- {doc['label']}",
        "",
        f"Scope: {doc['verdict_scope']}.",
        "",
        "## Magnitude criterion (pre-registered this run)",
        f"- N floor: {c['min_n']}",
        f"- |aggregate_ratio - 1| <= {c['aggregate_ratio_tolerance']}",
        f"- median_abs_error_dollars <= ${c['median_abs_error_dollars_max']:.0f}",
        f"- Derivation: {c['derivation']}",
        "",
        "## Reproduction check",
        f"- Matches queue-item numbers exactly: **{doc['reproduction_check']['matches_queue_item_numbers']}**",
        f"- n={doc['reproduction_check']['n']}  sign_agreement={doc['reproduction_check']['sign_agreement']:.2%}",
        "",
        "## Mechanism tests (ruling candidates in/out)",
    ]
    for name, m in doc["mechanism_tests"].items():
        lines.append(f"- **{name}**: {m.get('verdict')}")
    lines += [
        "",
        "## Root cause + fix",
        f"- Location: `{rc['location']}`",
        f"- Mechanism: {rc['mechanism']}",
        f"- Fix: {rc['fix']}",
        f"- Before: aggregate_ratio={bf['before'].get('aggregate_ratio')}  "
        f"median_abs_error=${bf['before'].get('median_abs_error_dollars')}  verdict={bf['verdict_before']}",
        f"- After:  aggregate_ratio={bf['after'].get('aggregate_ratio')}  "
        f"median_abs_error=${bf['after'].get('median_abs_error_dollars')}  verdict={bf['verdict_after']}",
        f"- Excess-ratio reduction: {bf['excess_ratio_reduction_pct']}%",
        "",
        "## 2026-09-03 follow-up (WALKER-MARKET-STAGE-FILL-ROOT-FIX)",
        f"- What changed: {rc['root_fix_2026_09_03_followup']['what_changed']}",
        f"- What was tried and reverted: "
        f"{rc['root_fix_2026_09_03_followup']['what_was_tried_and_reverted']}",
        "",
        "## Whole-engine V9 anchor validation (independent of the PDT anchor)",
        f"- n_rows={doc['v9_anchor_validation']['n_rows_loaded']} "
        f"(n_missing_bars before={doc['v9_anchor_validation']['n_missing_bars_before']} "
        f"after={doc['v9_anchor_validation']['n_missing_bars_after']})",
        f"- Before: aggregate_ratio={doc['v9_anchor_validation']['before'].get('aggregate_ratio')}  "
        f"median_abs_error=${doc['v9_anchor_validation']['before'].get('median_abs_error_dollars')}  "
        f"verdict={doc['v9_anchor_validation']['verdict_before']}",
        f"- After:  aggregate_ratio={doc['v9_anchor_validation']['after'].get('aggregate_ratio')}  "
        f"median_abs_error=${doc['v9_anchor_validation']['after'].get('median_abs_error_dollars')}  "
        f"verdict={doc['v9_anchor_validation']['verdict_after']}",
        "",
        "## Big anchor population",
        f"- Window {big['window'][0]}..{big['window'][1]}, n_walked={big['n_walked']} "
        f"(n_missing_bars={big['n_missing_bars']})",
        f"- aggregate_ratio={big['magnitude_fidelity'].get('aggregate_ratio')}  "
        f"verdict={big['magnitude_fidelity_verdict']}",
        "",
        "## Outstanding prereg RUNs -- can they be believed on dollars?",
    ]
    for k, v in doc["outstanding_prereg_runs_magnitude_readable"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Known limitations"]
    for kl in doc["known_limitations"]:
        lines.append(f"- {kl}")
    if doc["deviations"]:
        lines += ["", "## Deviations"]
        for d in doc["deviations"]:
            lines.append(f"- {d}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
