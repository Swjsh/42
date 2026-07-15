"""daytype_gate_study.py -- EX-ANTE DAY-TYPE GATE (JOB2, 2026-07-15).

Frozen pre-registration: analysis/recommendations/prereg-daytype-gate-2026-07-15.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift between what's frozen
on disk and what this runner executes).

WHAT THIS TESTS: does the ribbon_ride cohort's positive expectancy (measured under JOB1's
honest, friction-inclusive, SS-B-fixed conventions) concentrate in trading days classifiable
as TREND using ONLY information available by 10:30 ET -- and are CHOP days, so classified,
unrescuable? 3 classifiers (V1 opening-range extension+hold, V2 RVOL+close-location, V3
inverted compression-ratio), each zero-look-ahead by construction (bars < 10:30 ET on the
current day + a trailing-20-classifiable-day baseline built from strictly earlier days only).

METHOD (see the frozen pre-reg for the full spec; summarized here):
  * Population: JOB1's OTM-2 control cell (strike_ab_convention_reconciliation.py's honest
    job1a settings: SS-B shape+structure ON, corrected fill-bar convention, friction ON,
    stage-fix ON), filtered to entry_ts >= 10:30 ET (respects the classifiers' own information
    time -- a signal that fired before 10:30 cannot be gated by a 10:30-computed label).
  * Day classifiability: full 09:30-10:25 ET (12-bar) SPY coverage AND >=20 prior classifiable
    days for the trailing-median baseline; unclassifiable days -> disclosure-only bucket.
  * Test: TREND vs CHOP vs POOLED expectancy per variant, day-label-shuffle null (2000 perms,
    seed 4242), BH-FDR across the 3 variants, both-halves + drop-top-3 robustness, and the
    J-anchor catch rate (does each variant call the 3 J_WINNERS days TREND, ex-ante?).
  * Kill criteria frozen in the pre-reg: direction_correct, trend_bucket_positive,
    bh_fdr_survivor, trend_bucket_robust, j_anchor_catch>=2/3 -- ALL required for CANDIDATE_PASS.

REUSE (OP-22): tw8_level_context.load_spy_full (via ribbon_ride_strike_exit_ab.load_cohort,
already caches spy_full/spy_by_date), strike_ab_convention_reconciliation.{fetch_raw_bars,
select_walk_bars,replay_generic,SS_B_SHAPE,SS_B_TIME_STOP}, t4_exit_matrix.battery,
ribbon_rejection_wick_battery.bh_fdr, autoresearch.strategy_space_grind.{OOS_BOUNDARY,J_WINNERS}.

ANALYSIS ONLY. No params/config/trading-path file touched. No orders.

Run: backtest/.venv/Scripts/python.exe backtest/tools/daytype_gate_study.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_ride_strike_exit_ab as rrse                              # noqa: E402
import strike_ab_convention_reconciliation as sacr                     # noqa: E402
import t4_exit_matrix as t4                                            # noqa: E402
from autoresearch.strategy_space_grind import OOS_BOUNDARY, J_WINNERS  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402

SMOKE = "--smoke" in sys.argv
PREREG = REPO / "analysis" / "recommendations" / "prereg-daytype-gate-2026-07-15.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "daytype-gate-result.json"
OUT_MD = REPO / "analysis" / "recommendations" / "daytype-gate-result.md"

EXPECTED_PREREG_VERSION = 1
EXPECTED_PREREG_SHA16 = "1e8134795424be0d"

QTY = 10
CONTROL_SO = 2  # OTM-2, simulator convention
FIRST_HOUR_START = dt.time(9, 30)
FIRST_HOUR_END = dt.time(10, 30)      # exclusive upper bound -- bars 09:30..10:25 (12 bars)
OR30_END = dt.time(10, 0)             # exclusive upper bound -- bars 09:30..09:55 (6 bars)
INFO_CUTOFF = dt.time(10, 30)         # population entry_ts must be >= this
K_RANGE = 1.20
K_RVOL = 1.20
K_LOC = 0.30
BASELINE_LOOKBACK_DAYS = 20
N_PERMUTATIONS = 3 if SMOKE else 2000
SEED = 4242


def log(msg: str) -> None:
    print(f"[daytype-gate] {msg}", flush=True)


# --- preflight: never run a drifted spec ---------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored and preg.get("version") == EXPECTED_PREREG_VERSION)
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
           "version": preg.get("version"), "status": preg.get("status")}


# ---------------------------------------------------------------------------------------------
# DAY-TYPE CLASSIFICATION -- zero look-ahead: current-day bars < 10:30 ET + trailing baseline
# built ONLY from strictly-earlier classifiable days.
# ---------------------------------------------------------------------------------------------
def build_day_features(spy_by_date: dict) -> dict:
    """Returns {date: {classifiable, first_hour_range, first_hour_vol, or30_high, or30_low,
    close_at_1030}} for every date with full 12-bar 09:30-10:25 coverage; dates without it are
    simply absent (== unclassifiable)."""
    feats = {}
    for date, day_df in spy_by_date.items():
        fh = day_df[(day_df["timestamp_et"].dt.time >= FIRST_HOUR_START) &
                   (day_df["timestamp_et"].dt.time < FIRST_HOUR_END)]
        if len(fh) != 12:
            continue
        or30 = fh[fh["timestamp_et"].dt.time < OR30_END]
        if len(or30) != 6:
            continue
        fh_sorted = fh.sort_values("timestamp_et")
        feats[date] = {
            "first_hour_range": float(fh_sorted["high"].max() - fh_sorted["low"].min()),
            "first_hour_vol": float(fh_sorted["volume"].sum()),
            "first_hour_high": float(fh_sorted["high"].max()),
            "first_hour_low": float(fh_sorted["low"].min()),
            "or30_high": float(or30["high"].max()),
            "or30_low": float(or30["low"].min()),
            "close_at_1030": float(fh_sorted.iloc[-1]["close"]),
        }
    return feats


def median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def classify_all_days(day_feats: dict) -> dict:
    """dates -> {classifiable(bool w/ baseline), V1,V2,V3 labels, median20_range, median20_vol}.
    Trailing baseline uses ONLY strictly-earlier dates present in day_feats (i.e. themselves
    12-bar-classifiable) -- chronological, zero look-ahead."""
    dates_sorted = sorted(day_feats.keys())
    out = {}
    for i, date in enumerate(dates_sorted):
        prior_dates = dates_sorted[:i]
        if len(prior_dates) < BASELINE_LOOKBACK_DAYS:
            out[date] = {"classifiable": False, "reason": "insufficient_baseline_history"}
            continue
        trailing = prior_dates[-BASELINE_LOOKBACK_DAYS:]
        med_range = median([day_feats[d]["first_hour_range"] for d in trailing])
        med_vol = median([day_feats[d]["first_hour_vol"] for d in trailing])
        f = day_feats[date]
        range_ratio = (f["first_hour_range"] / med_range) if med_range else None
        rvol = (f["first_hour_vol"] / med_vol) if med_vol else None
        hi, lo = f["first_hour_high"], f["first_hour_low"]
        close_loc = ((f["close_at_1030"] - lo) / (hi - lo)) if (hi - lo) > 0 else 0.5

        v1 = bool(range_ratio is not None and range_ratio >= K_RANGE and
                 (f["close_at_1030"] > f["or30_high"] or f["close_at_1030"] < f["or30_low"]))
        v2 = bool(rvol is not None and rvol >= K_RVOL and abs(close_loc - 0.5) >= K_LOC)
        v3 = bool(range_ratio is not None and range_ratio >= K_RANGE)

        out[date] = {"classifiable": True, "median20_range": med_range, "median20_vol": med_vol,
                    "range_ratio": range_ratio, "rvol": rvol, "close_location": round(close_loc, 4),
                    "V1": "TREND" if v1 else "CHOP", "V2": "TREND" if v2 else "CHOP",
                    "V3": "TREND" if v3 else "CHOP"}
    return out


# ---------------------------------------------------------------------------------------------
# POPULATION REPLAY -- JOB1's honest OTM-2 control convention, entry_ts >= 10:30 ET only.
# ---------------------------------------------------------------------------------------------
def build_population(prepped: list[dict], bars_by_signal: dict) -> tuple[list[dict], dict]:
    """Returns (episodes, counts). episodes: [{date, entry_ts, pnl}]. counts: exclusion tally."""
    counts = {"raw_signals": len(prepped), "before_1030": 0, "no_local_bars": 0, "retained": 0}
    episodes = []
    for s in prepped:
        if s["entry_ts_obj"].time() < INFO_CUTOFF:
            counts["before_1030"] += 1
            continue
        key = (s["date_obj"], s["side"], s["entry_ts_obj"], CONTROL_SO)
        fetched = bars_by_signal.get(key)
        if fetched is None:
            counts["no_local_bars"] += 1
            continue
        entry_premium_raw, full_bars = fetched
        walk = sacr.select_walk_bars(full_bars, old_fillbar=False)   # corrected convention
        if not walk:
            counts["no_local_bars"] += 1
            continue
        r = sacr.replay_generic(entry_premium_raw, s["side"], QTY, walk, s["ss_time"],
                                sacr.SS_B_SHAPE, sacr.SS_B_TIME_STOP,
                                friction=True, stage_fix=True, use_structure=True)
        episodes.append({"date": s["date_obj"], "entry_ts": s["entry_ts_obj"].isoformat(),
                         "direction": s["direction"], "pnl": r["pnl"]})
        counts["retained"] += 1
    return episodes, counts


# ---------------------------------------------------------------------------------------------
# BUCKET BATTERY + SHUFFLE NULL
# ---------------------------------------------------------------------------------------------
def both_halves(trades: list[dict]) -> bool:
    ordered = sorted(trades, key=lambda t: t["date"])
    n = len(ordered)
    mid = n // 2
    first, second = ordered[:mid], ordered[mid:]
    f_tot = sum(t["pnl"] for t in first)
    s_tot = sum(t["pnl"] for t in second)
    return bool(first and second and f_tot > 0 and s_tot > 0)


def bucket_summary(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "expectancy": None}
    b = t4.battery([{"date": t["date"], "direction": t.get("direction", "bull"), "pnl": t["pnl"]} for t in trades])
    return {"n": b.get("n"), "total": b.get("total"), "expectancy": b.get("expectancy"),
           "wr": b.get("wr"), "oos_total": b.get("oos_total"), "oos_positive": b.get("oos_positive"),
           "exp_drop_top3": b.get("exp_drop_top3"), "sub_window_stable": both_halves(trades)}


def variant_split(episodes: list[dict], labels_by_date: dict, variant: str) -> dict:
    trend, chop, unclassifiable = [], [], []
    for e in episodes:
        lab = labels_by_date.get(e["date"])
        if lab is None or not lab.get("classifiable"):
            unclassifiable.append(e)
        elif lab[variant] == "TREND":
            trend.append(e)
        else:
            chop.append(e)
    return {"trend_episodes": trend, "chop_episodes": chop, "unclassifiable_episodes": unclassifiable,
           "trend": bucket_summary(trend), "chop": bucket_summary(chop),
           "pooled": bucket_summary(trend + chop), "unclassifiable": bucket_summary(unclassifiable)}


def shuffle_null(episodes: list[dict], labels_by_date: dict, variant: str, n_trend_days: int,
                 classifiable_dates: list, seed: int, n_perm: int) -> dict:
    """Day-label shuffle: draw n_trend_days random days from the classifiable universe (that
    have >=1 retained episode), relabel TREND, recompute (trend_exp - chop_exp), compare to the
    real observed delta. One-sided empirical p (add-one smoothed)."""
    by_date: dict = {}
    for e in episodes:
        lab = labels_by_date.get(e["date"])
        if lab is not None and lab.get("classifiable"):
            by_date.setdefault(e["date"], []).append(e["pnl"])
    eligible_dates = [d for d in classifiable_dates if d in by_date]
    if not eligible_dates or n_trend_days <= 0 or n_trend_days >= len(eligible_dates):
        return {"n_eligible_days": len(eligible_dates), "n_trend_days": n_trend_days,
               "p_null": None, "note": "degenerate split -- null not computed"}

    real_trend = [e["pnl"] for e in episodes if labels_by_date.get(e["date"], {}).get(variant) == "TREND"
                  and labels_by_date.get(e["date"], {}).get("classifiable")]
    real_chop = [e["pnl"] for e in episodes if labels_by_date.get(e["date"], {}).get(variant) == "CHOP"
                 and labels_by_date.get(e["date"], {}).get("classifiable")]
    obs_delta = ((sum(real_trend) / len(real_trend)) if real_trend else 0.0) - \
               ((sum(real_chop) / len(real_chop)) if real_chop else 0.0)

    rng = random.Random(seed)
    ge = 0
    deltas = []
    for _ in range(n_perm):
        shuffled_trend_dates = set(rng.sample(eligible_dates, n_trend_days))
        t_pnls = [p for d in shuffled_trend_dates for p in by_date[d]]
        c_pnls = [p for d in eligible_dates if d not in shuffled_trend_dates for p in by_date[d]]
        d = ((sum(t_pnls) / len(t_pnls)) if t_pnls else 0.0) - ((sum(c_pnls) / len(c_pnls)) if c_pnls else 0.0)
        deltas.append(d)
        if d >= obs_delta:
            ge += 1
    p_null = round((1 + ge) / (1 + n_perm), 4)
    return {"n_eligible_days": len(eligible_dates), "n_trend_days": n_trend_days,
           "observed_trend_minus_chop": round(obs_delta, 2), "p_null": p_null,
           "null_mean_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
           "n_permutations": n_perm, "seed": seed}


def j_anchor_catch(day_feats: dict, labels_by_date: dict, variant: str) -> dict:
    rows = []
    n_caught = 0
    for wdate, side, pnl in J_WINNERS:
        lab = labels_by_date.get(wdate)
        caught = bool(lab is not None and lab.get("classifiable") and lab[variant] == "TREND")
        n_caught += int(caught)
        rows.append({"date": str(wdate), "side": side, "j_actual_pnl": pnl,
                    "classifiable": bool(lab is not None and lab.get("classifiable")),
                    "label": (lab[variant] if lab and lab.get("classifiable") else "unclassifiable"),
                    "caught": caught})
    return {"rows": rows, "n_caught": n_caught, "n_total": len(J_WINNERS),
           "catch_rate": round(n_caught / len(J_WINNERS), 3)}


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        print("[daytype-gate] PREREG DRIFT DETECTED -- refusing to run. Fix the freeze first.", file=sys.stderr)
        return 2

    log(f"{'SMOKE' if SMOKE else 'FULL'} run -- loading cohort (reused from ribbon_ride_strike_exit_ab)")
    prepped, spy_full, spy_by_date = rrse.load_cohort()
    log(f"cohort n={len(prepped)}")

    log("building day-level opening-range/RVOL features (12-bar-coverage days only)...")
    day_feats = build_day_features(spy_by_date)
    log(f"  {len(day_feats)}/{len(spy_by_date)} calendar days have full 09:30-10:25 coverage")

    labels_by_date = classify_all_days(day_feats)
    classifiable_dates = sorted(d for d, v in labels_by_date.items() if v.get("classifiable"))
    log(f"  {len(classifiable_dates)}/{len(day_feats)} coverage-qualifying days also have a valid "
        f"{BASELINE_LOOKBACK_DAYS}-day trailing baseline -> classifiable")
    for variant in ("V1", "V2", "V3"):
        n_trend = sum(1 for d in classifiable_dates if labels_by_date[d][variant] == "TREND")
        log(f"  {variant}: {n_trend}/{len(classifiable_dates)} classifiable days labeled TREND")

    log("prefetching raw OPRA bars at OTM-2 (control strike)...")
    bars_by_signal = {}
    n_hit = 0
    for s in prepped:
        key = (s["date_obj"], s["side"], s["entry_ts_obj"], CONTROL_SO)
        fetched = sacr.fetch_raw_bars(float(s["entry_spot"]), s["side"], s["date_obj"],
                                      s["entry_ts_obj"], CONTROL_SO)
        bars_by_signal[key] = fetched
        if fetched is not None:
            n_hit += 1
    log(f"  {n_hit}/{len(prepped)} signals with local OTM-2 OPRA coverage")

    episodes, pop_counts = build_population(prepped, bars_by_signal)
    log(f"population: {pop_counts}")
    pop_battery = bucket_summary(episodes)
    log(f"  retained-population (pre-day-type-split) battery: {pop_battery}")

    variants_out = {}
    for variant in ("V1", "V2", "V3"):
        split = variant_split(episodes, labels_by_date, variant)
        n_trend_days = sum(1 for d in classifiable_dates if labels_by_date[d][variant] == "TREND")
        null = shuffle_null(episodes, labels_by_date, variant, n_trend_days, classifiable_dates,
                            SEED, N_PERMUTATIONS)
        anchor = j_anchor_catch(day_feats, labels_by_date, variant)
        variants_out[variant] = {
            "n_trend_days": n_trend_days, "n_classifiable_days": len(classifiable_dates),
            "trend": split["trend"], "chop": split["chop"], "pooled": split["pooled"],
            "unclassifiable": split["unclassifiable"],
            "null": null, "j_anchor": anchor,
        }
        log(f"  {variant}: trend_n={split['trend']['n']} trend_exp=${split['trend']['expectancy']} "
            f"chop_n={split['chop']['n']} chop_exp=${split['chop']['expectancy']} "
            f"p_null={null.get('p_null')} anchor_catch={anchor['catch_rate']}")

    # --- BH-FDR across the 3 variants ---
    bh_input = [{"variant": v, "p_null": variants_out[v]["null"].get("p_null")} for v in ("V1", "V2", "V3")
               if variants_out[v]["null"].get("p_null") is not None]
    if bh_input:
        bh_fdr(bh_input, alpha=FDR_ALPHA)
    bh_by_variant = {row["variant"]: row for row in bh_input}
    for v in ("V1", "V2", "V3"):
        variants_out[v]["bh_fdr_survivor"] = bh_by_variant.get(v, {}).get("bh_fdr_survivor", False)
        variants_out[v]["bh_rank"] = bh_by_variant.get(v, {}).get("bh_rank")

    # --- frozen kill criteria ---
    verdicts = {}
    for v in ("V1", "V2", "V3"):
        d = variants_out[v]
        trend_exp = d["trend"].get("expectancy")
        chop_exp = d["chop"].get("expectancy")
        conds = {
            "1_direction_correct": bool(trend_exp is not None and chop_exp is not None and trend_exp > chop_exp),
            "2_trend_bucket_positive": bool(trend_exp is not None and trend_exp > 0),
            "3_bh_fdr_survivor": bool(d["bh_fdr_survivor"]),
            "4_trend_bucket_robust": bool(d["trend"].get("sub_window_stable")
                                         and (d["trend"].get("exp_drop_top3") or 0) > 0),
            "5_j_anchor_catch": bool(d["j_anchor"]["catch_rate"] >= (2.0 / 3.0) - 1e-9),
        }
        verdict = "CANDIDATE_PASS" if all(conds.values()) else "KILL"
        chop_unrescuable = bool(chop_exp is not None and chop_exp <= 0)
        verdicts[v] = {"conditions": conds, "verdict": verdict,
                       "chop_unrescuable_confirmation": chop_unrescuable}
        log(f"  {v} VERDICT: {verdict} (conds={conds}, chop_unrescuable={chop_unrescuable})")

    elapsed = round(_time_mod.time() - t_start, 1)
    out = {
        "_doc": ("DAYTYPE-GATE-RESULT (JOB2). ANALYSIS ONLY -- no params/config/trading-path "
                "file touched, no orders placed. Population = JOB1's honest-convention OTM-2 "
                "control, entry_ts>=10:30 ET only. See prereg-daytype-gate-2026-07-15.json for "
                "the frozen classifier/threshold/kill-criteria spec."),
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "prereg": str(PREREG.relative_to(REPO)),
        "prereg_preflight": pf,
        "day_coverage": {"n_calendar_days_in_window": len(spy_by_date),
                         "n_days_full_first_hour_coverage": len(day_feats),
                         "n_days_classifiable_with_baseline": len(classifiable_dates)},
        "population": {"counts": pop_counts, "pre_split_battery": pop_battery},
        "variants": variants_out,
        "verdicts": verdicts,
        "fdr_alpha": FDR_ALPHA,
        "thresholds": {"k_range": K_RANGE, "k_rvol": K_RVOL, "k_loc": K_LOC,
                       "baseline_lookback_days": BASELINE_LOOKBACK_DAYS,
                       "info_cutoff_et": str(INFO_CUTOFF)},
        "disclosures": [
            "MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay "
            "artifact; episode pnl is exactly JOB1's honest OTM-2 control replay, unmodified.",
            "entry_ts>=10:30 filter drops any signal firing in the first hour -- see "
            "population.counts.before_1030 for the exact count; this population is NOT the "
            "same as JOB1's full 250-signal OTM-2 cell and its own battery is reported "
            "(population.pre_split_battery) before any day-type split so the two are never "
            "conflated.",
            "day_classifiability requires FULL 12-bar 09:30-10:25 coverage (strict, no partial-"
            "window imputation) AND >=20 prior classifiable days for the trailing baseline -- "
            "see day_coverage for the funnel from raw calendar days to classifiable days.",
            "V1's condition is a strict superset of V3's (V1 = V3's range-expansion test AND "
            "the OR-hold confirmation) -- comparing V1 vs V3's pass/kill outcome directly "
            "answers whether the hold-confirmation leg adds anything beyond pure range "
            "expansion, not 3 independent guesses.",
            "shuffle_null preserves the REAL classifier's TREND-day COUNT (draws n_trend_days "
            "random days from the same classifiable-day universe) -- it tests whether THIS "
            "classifier's specific day selection beats a random subset of the same size, not "
            "whether trend days in general differ from chop days by construction.",
            "No re-tuning of K_RANGE/K_RVOL/K_LOC after seeing any result -- frozen in the "
            "pre-reg before this script was run; a KILL is not grounds to adjust and re-run "
            "under this study's own name (a materially different classifier design would be a "
            "new, separately pre-registered study).",
        ],
        "runtime_seconds": elapsed,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON.name} + {OUT_MD.name} ({elapsed}s total)")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# Ex-ante day-type gate — JOB2 result")
    L.append("")
    L.append(f"Pre-registration: `{out['prereg']}` (preflight ok={out['prereg_preflight']['ok']}). "
             f"Cost: $0. Generated {out['generated_at']}.")
    L.append("")
    dc = out["day_coverage"]
    L.append(f"**Day coverage funnel:** {dc['n_calendar_days_in_window']} calendar days -> "
             f"{dc['n_days_full_first_hour_coverage']} with full 09:30-10:25 coverage -> "
             f"{dc['n_days_classifiable_with_baseline']} classifiable (>=20-day trailing baseline).")
    L.append("")
    pc = out["population"]["counts"]
    pb = out["population"]["pre_split_battery"]
    L.append(f"**Population (JOB1 honest OTM-2, entry>=10:30 ET):** {pc['raw_signals']} raw signals "
             f"-> {pc['before_1030']} dropped (before 10:30) -> {pc['no_local_bars']} dropped "
             f"(no local bars) -> **{pc['retained']} retained**. Pre-split battery: "
             f"n={pb.get('n')} exp=${pb.get('expectancy')} WR={pb.get('wr')}.")
    L.append("")
    L.append("## Variants")
    L.append("")
    L.append("| variant | trend n | trend exp | chop n | chop exp | p_null | BH-survivor | anchor catch | verdict |")
    L.append("|---|--:|--:|--:|--:|--:|:--:|:--:|---|")
    for v in ("V1", "V2", "V3"):
        d = out["variants"][v]
        vd = out["verdicts"][v]
        L.append(f"| {v} | {d['trend']['n']} | ${d['trend']['expectancy']} | {d['chop']['n']} | "
                 f"${d['chop']['expectancy']} | {d['null'].get('p_null')} | "
                 f"{'Y' if d['bh_fdr_survivor'] else 'N'} | {d['j_anchor']['catch_rate']} | "
                 f"**{vd['verdict']}** |")
    L.append("")
    for v in ("V1", "V2", "V3"):
        d = out["variants"][v]
        vd = out["verdicts"][v]
        L.append(f"### {v}")
        L.append("")
        L.append(f"- trend: n={d['trend']['n']} total=${d['trend'].get('total')} exp=${d['trend']['expectancy']} "
                 f"WR={d['trend'].get('wr')} OOS+={d['trend'].get('oos_positive')} "
                 f"stable={d['trend'].get('sub_window_stable')} drop3=${d['trend'].get('exp_drop_top3')}")
        L.append(f"- chop: n={d['chop']['n']} total=${d['chop'].get('total')} exp=${d['chop']['expectancy']} "
                 f"WR={d['chop'].get('wr')} OOS+={d['chop'].get('oos_positive')} "
                 f"stable={d['chop'].get('sub_window_stable')}")
        L.append(f"- pooled: n={d['pooled']['n']} exp=${d['pooled']['expectancy']} | "
                 f"unclassifiable: n={d['unclassifiable']['n']} exp=${d['unclassifiable'].get('expectancy')}")
        L.append(f"- null: n_trend_days={d['null'].get('n_trend_days')}/{d['null'].get('n_eligible_days')}, "
                 f"observed(trend-chop)=${d['null'].get('observed_trend_minus_chop')}, "
                 f"null_mean=${d['null'].get('null_mean_delta')}, p_null={d['null'].get('p_null')}, "
                 f"BH-survivor={d['bh_fdr_survivor']}")
        L.append(f"- J-anchor: {d['j_anchor']['n_caught']}/{d['j_anchor']['n_total']} caught "
                 f"({d['j_anchor']['catch_rate']}) -- " +
                 "; ".join(f"{r['date']}={r['label']}({'caught' if r['caught'] else 'missed'})"
                          for r in d['j_anchor']['rows']))
        L.append(f"- conditions: {vd['conditions']}")
        L.append(f"- **VERDICT: {vd['verdict']}** | chop_unrescuable_confirmation={vd['chop_unrescuable_confirmation']}")
        L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/daytype_gate_study.py`. A CANDIDATE_PASS is SPECIFIED, never "
             "auto-built or auto-wired -- still owes a J-visible REVOKE window per standing doctrine._")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
