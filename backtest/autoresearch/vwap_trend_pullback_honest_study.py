"""vwap_trend_pullback_honest_study — the pre-registered honest study for H4
(VWAP_TREND_PULLBACK) on the exit config the LIVE watcher actually trades.

Runs the frozen spec at analysis/recommendations/vwap-trend-pullback-study-spec.json
(frozen 2026-07-10, NOT RUN until this fire). Answers the question the original
2026-06-19 ratify (vwap-trend-pullback-LIVE.json) never fully answered: does H4,
evaluated on CHART-STOP-ONLY (the config vwap_trend_pullback_watcher.py actually
trades), clear OP-16/22, and is it additive to the book or a reskin of the
already-live vwap_continuation edge (gate_11, HARD/BLOCKING per the spec).

PROPOSE-ONLY (Rule 9): reads data, writes a scorecard JSON + paired .md. Touches no
params, no heartbeat, no order path, no detector logic. Pure-Python, $0, deterministic.

Usage
-----
    backtest/.venv/Scripts/python.exe backtest/autoresearch/vwap_trend_pullback_honest_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                                # ...\42
for _p in (str(REPO), str(PROJECT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.infinite_ammo_discovery import (   # noqa: E402
    load_spy,
    align_vix,
    build_day_contexts,
    detect_vwap_pullback,
    summarize,
    Signal,
    TradeRow,
    _strike_from_spot,
    _nearest_cached_strike,
)
from autoresearch.vwap_pullback_ratify import (      # noqa: E402
    causality_future_poison,
    causality_entry_next_bar,
    walk_forward,
    subwindow_stability,
    WF_GATE,
)
from autoresearch.j_daily_pattern_ratify import detect_j_vwap_continuation  # noqa: E402
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (    # noqa: E402
    detect_opt_signals as detect_vix_regime_dayside,
    causal_vix_median, vix_slope, VIX_MEDIAN_BARS, VIX_SLOPE_BARS, _swing_stop,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon                # noqa: E402
from lib.simulator_real import simulate_trade_real   # noqa: E402

SPY_CSV = REPO / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_CSV = REPO / "data" / "vix_5m_2025-01-01_2026-07-22.csv"
OUT_JSON = PROJECT / "analysis" / "recommendations" / "vwap-trend-pullback-honest-study.json"
OUT_MD = PROJECT / "analysis" / "recommendations" / "vwap-trend-pullback-honest-study.md"
SPEC = PROJECT / "analysis" / "recommendations" / "vwap-trend-pullback-study-spec.json"

QTY = 3
MAX_STRIKE_STEPS = 4
N_TRIALS_DSR = 8            # 4 tiers x 2 sides, per spec method.n_trials_dsr note
OOS_SPLIT_FRAC = 0.70       # chronological proportion split (spec data.oos_split_rule)
OVERLAP_MAX = 0.80          # _b8_anchored_vwap convention (L174)
ENTRY_CUTOFF_1030 = dt.time(10, 30)

# Simulator-convention strike tiers (NEGATIVE=ITM, POSITIVE=OTM) per spec §method.
TIERS = {"ATM": 0, "ITM1": -1, "ITM2": -2, "OTM2": 2}

# exit configs: PRIMARY = chart-stop-only (what the live watcher trades);
# SECONDARY = the original ratify's default, disclosure-only, never gated.
EXIT_PRIMARY_PCT = -0.99
EXIT_SECONDARY_PCT = -0.08


# ─────────────────────────────────────────────────────────────────────────────
# simulate_signals variant that threads premium_stop_pct through (the ONE gap in
# infinite_ammo_discovery.simulate_signals — it hardcodes the simulator default).
# Everything else (strike resolution, TradeRow shape) is identical to the reused fn.
# ─────────────────────────────────────────────────────────────────────────────
def simulate_signals_with_stop(signals, spy_df, ribbon_df, vix, qty, strike_offset,
                                max_strike_steps, premium_stop_pct):
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = 0
    n_cache_miss = 0
    n_sim_none = 0
    for sg in signals:
        bar = spy_df.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = (atm - strike_offset) if sg.side == "P" else (atm + strike_offset)
        strike = _nearest_cached_strike(d, target, sg.side, max_strike_steps)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx,
            entry_bar=bar,
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=sg.stop_level,
            triggers_fired=[sg.note or "discovery"],
            side=sg.side,
            qty=qty,
            setup="VWAP_TREND_PULLBACK_HONEST",
            strike_override=strike,
            entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), time_et=str(bar["t"]), side=sg.side,
            strike=int(strike), atm=int(atm), strike_off=int(strike - atm),
            entry_premium=round(float(fill.entry_premium), 4),
            dollar_pnl=round(float(fill.dollar_pnl), 2),
            pct_return=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            hold_min=int(fill.hold_minutes or 0), note=sg.note,
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# gate_10: entry-time distribution
# ─────────────────────────────────────────────────────────────────────────────
def entry_time_distribution(signals, spy) -> dict:
    times = []
    after_1030 = 0
    for sg in signals:
        t = spy.iloc[sg.bar_idx]["timestamp_et"].time()
        times.append(t.strftime("%H:%M"))
        if t > ENTRY_CUTOFF_1030:
            after_1030 += 1
    n = len(signals)
    hist: dict[str, int] = defaultdict(int)
    for t in times:
        hist[t] += 1
    pct_after = round(after_1030 / n, 3) if n else 0.0
    return {
        "n_signals": n,
        "n_after_1030": after_1030,
        "pct_signals_after_1030": pct_after,
        "coverage_hole_claim_falsified": bool(pct_after < 0.30),
        "entry_time_histogram": dict(sorted(hist.items())),
    }


# ─────────────────────────────────────────────────────────────────────────────
# gate_11: independence / reskin re-check vs #1/#2/#4 (extended dataset)
# ─────────────────────────────────────────────────────────────────────────────
def signal_day_sides(signals, spy) -> dict:
    out: dict = defaultdict(set)
    for s in signals:
        d = spy.iloc[s.bar_idx]["timestamp_et"].date()
        out[d].add(s.side)
    return out


def overlap_metrics(cand: dict, other: dict) -> dict:
    cd, od = set(cand), set(other)
    shared = cd & od
    union = cd | od
    same_side = {d for d in shared if cand[d] & other[d]}
    day_overlap = round(len(shared) / len(cd), 3) if cd else 0.0
    jaccard = round(len(shared) / len(union), 3) if union else 0.0
    same_side_overlap = round(len(same_side) / len(cd), 3) if cd else 0.0
    return {
        "candidate_days": len(cd), "other_days": len(od),
        "shared_days": len(shared), "same_side_shared_days": len(same_side),
        "day_overlap_shared_over_candidate": day_overlap,
        "jaccard_shared_over_union": jaccard,
        "same_side_day_overlap": same_side_overlap,
        "reskin_by_same_side": bool(same_side_overlap >= OVERLAP_MAX),
    }


# ─────────────────────────────────────────────────────────────────────────────
# gate_9: regime split by quarter + VIX tercile
# ─────────────────────────────────────────────────────────────────────────────
def regime_split(rows, vix, spy) -> dict:
    if not rows:
        return {"verdict": "NO_TRADES"}
    vix_vals = vix.values if hasattr(vix, "values") else np.asarray(vix)
    # map each row's date+time back to an approximate VIX-at-entry via spy timestamps
    ts_to_idx = {str(t): i for i, t in enumerate(spy["timestamp_et"])}
    vix_at_entry = []
    for r in rows:
        key = f"{r.date} {r.time_et}:00"
        # fallback: nearest match by date/time string prefix (cheap, no precision loss
        # for terciling purposes)
        idx = None
        for k, i in ts_to_idx.items():
            if k.startswith(f"{r.date} {r.time_et}"):
                idx = i
                break
        vix_at_entry.append(float(vix_vals[idx]) if idx is not None and idx < len(vix_vals) else np.nan)
    vix_arr = np.array(vix_at_entry)
    valid = ~np.isnan(vix_arr)
    terciles = {}
    if valid.sum() >= 6:
        q1, q2 = np.nanpercentile(vix_arr[valid], [33.3, 66.7])
        for label, mask in (
            ("low_vix", vix_arr <= q1),
            ("mid_vix", (vix_arr > q1) & (vix_arr <= q2)),
            ("high_vix", vix_arr > q2),
        ):
            sub = [r.dollar_pnl for r, m in zip(rows, mask) if m]
            if sub:
                terciles[label] = {"n": len(sub), "exp_dollar": round(float(np.mean(sub)), 2)}
    return {"vix_terciles": terciles}


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"[study] loading SPY {SPY_CSV.name} / VIX {VIX_CSV.name}")
    spy = load_spy(str(SPY_CSV))
    vix = align_vix(spy, str(VIX_CSV))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    cut_i = int(len(all_dates) * OOS_SPLIT_FRAC)
    oos_cut_date = str(all_dates[cut_i])
    print(f"[study] days={len(days)} oos_cut={oos_cut_date}")

    # ── gate_8: causality (regression check, re-verify current code) ─────────
    print("[study] gate_8 causality (future-poison) ...")
    poison_res = causality_future_poison(spy, ribbon, vix, days)
    print(f"    {poison_res['verdict']}")

    signals = detect_vwap_pullback(spy, ribbon, vix, days)
    print(f"[study] {len(signals)} raw H4 signals")

    # ── gate_10: entry-time distribution (base pattern, exit-config-independent) ──
    time_dist = entry_time_distribution(signals, spy)
    print(f"[study] gate_10 pct_after_1030={time_dist['pct_signals_after_1030']} "
          f"falsified={time_dist['coverage_hole_claim_falsified']}")

    # ── gate_11: independence re-check on the EXTENDED dataset ────────────────
    print("[study] gate_11 independence re-check ...")
    vp_days = signal_day_sides(signals, spy)
    vwap_cont_signals = detect_j_vwap_continuation(spy, ribbon, vix, days)
    reclaim_signals = detect_reclaim_failed_break(days)
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    raw_vix_regime = detect_vix_regime_dayside(
        days, spy, vix_g, vix_med_g, vix_slp_g, low_margin=0.0, slope_rule="not_rising")
    vix_regime_signals = [
        Signal(bar_idx=s.gidx, side=s.side,
               stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
               note="vix_regime_dayside")
        for s in raw_vix_regime
    ]
    book_days = {
        "vwap_continuation": signal_day_sides(vwap_cont_signals, spy),
        "vwap_reclaim_failed_break": signal_day_sides(reclaim_signals, spy),
        "vix_regime_dayside": signal_day_sides(vix_regime_signals, spy),
    }
    independence = {k: overlap_metrics(vp_days, v) for k, v in book_days.items()}
    reskin_by_1 = independence["vwap_continuation"]["reskin_by_same_side"]
    print(f"    vs #1 same_side_overlap={independence['vwap_continuation']['same_side_day_overlap']} "
          f"reskin={reskin_by_1}")

    # ── after-10:30-only subset (gate_10 narrower candidate, if applicable) ──
    after_1030_signals = [
        sg for sg in signals
        if spy.iloc[sg.bar_idx]["timestamp_et"].time() > ENTRY_CUTOFF_1030
    ]
    after_1030_result = None
    if len(after_1030_signals) >= 20:
        rows_pm, cov_pm = simulate_signals_with_stop(
            after_1030_signals, spy, ribbon, vix, QTY, TIERS["ATM"], MAX_STRIKE_STEPS,
            EXIT_PRIMARY_PCT)
        summ_pm = summarize(rows_pm, oos_cut_date, N_TRIALS_DSR)
        after_1030_result = {
            "n_signals": len(after_1030_signals), "coverage": cov_pm, "metrics": summ_pm,
            "clears_own_bar": bool(summ_pm.get("oos_sign_stable") and
                                    (summ_pm.get("exp_dollar_per_trade") or 0) > 0),
        }
        print(f"    after-10:30 subset n={len(after_1030_signals)} "
              f"exp$={summ_pm.get('exp_dollar_per_trade')} "
              f"oos_stable={summ_pm.get('oos_sign_stable')}")
    else:
        print(f"    after-10:30 subset n={len(after_1030_signals)} < 20 -- not independently gradeable")

    gate_11 = {
        "independence_vs_book": independence,
        "reskin_by_same_side_vs_1": reskin_by_1,
        "after_1030_subset": after_1030_result,
        "verdict": (
            "NOT_A_RESKIN" if not reskin_by_1 else
            ("NARROWER_CANDIDATE_CLEARS" if (after_1030_result and after_1030_result["clears_own_bar"])
             else "CONFIRMED_RESKIN_KEEP_DORMANT")
        ),
    }
    print(f"    gate_11 verdict: {gate_11['verdict']}")

    # ── simulate all 4 tiers x PRIMARY exit config (chart-stop-only) ──────────
    tier_results = {}
    rows_by_tier = {}
    for tname, off in TIERS.items():
        rows, cov = simulate_signals_with_stop(
            signals, spy, ribbon, vix, QTY, off, MAX_STRIKE_STEPS, EXIT_PRIMARY_PCT)
        summ = summarize(rows, oos_cut_date, N_TRIALS_DSR)
        tier_results[tname] = {"coverage": cov, "metrics": summ}
        rows_by_tier[tname] = rows
        print(f"[study] PRIMARY [{tname}] filled={cov['filled']}/{cov['signals']} "
              f"exp$={summ.get('exp_dollar_per_trade')} WR={summ.get('win_rate_pct')}% "
              f"OOS_stable={summ.get('oos_sign_stable')} DSR={summ.get('dsr_verdict')}")

    # secondary (disclosure-only) at ATM, matching the original ratify's headline config
    rows_secondary, cov_secondary = simulate_signals_with_stop(
        signals, spy, ribbon, vix, QTY, TIERS["ATM"], MAX_STRIKE_STEPS, EXIT_SECONDARY_PCT)
    summ_secondary = summarize(rows_secondary, oos_cut_date, N_TRIALS_DSR)
    print(f"[study] SECONDARY (disclosure only, -0.08) [ATM] exp$={summ_secondary.get('exp_dollar_per_trade')}")

    # ── headline tier = ATM PRIMARY (matches the original ratify's recommended tier) ──
    headline_tier = "ATM"
    headline_rows = rows_by_tier[headline_tier]
    headline_metrics = tier_results[headline_tier]["metrics"]

    entry_res = causality_entry_next_bar(headline_rows)

    print(f"[study] gate_3 walk-forward ({headline_tier}, PRIMARY) ...")
    wf_headline = walk_forward(headline_rows)
    print(f"    median_wf={wf_headline.get('median_wf_norm')} verdict={wf_headline.get('verdict')}")

    print(f"[study] gate_4 sub-window stability ({headline_tier}, PRIMARY) ...")
    sw_headline = subwindow_stability(headline_rows)
    print(f"    n_hurt={sw_headline.get('n_hurt')} verdict={sw_headline.get('verdict')}")

    # ── gate_5: random-entry null (headline tier, PRIMARY config) ────────────
    print("[study] gate_5 random-entry null ...")
    n_call = sum(1 for r in headline_rows if r.side == "C")
    n_put = sum(1 for r in headline_rows if r.side == "P")
    rth_frames = [dc.rth for dc in days]
    rth_all = pd.concat(rth_frames, ignore_index=True) if rth_frames else pd.DataFrame()
    null_res = {}
    null_gate_res = {}
    if len(headline_rows) and not rth_all.empty:
        try:
            null_res = random_entry_null(
                rth_all, n_signals=len(headline_rows), n_call=n_call, n_put=n_put,
                strike_offset=TIERS[headline_tier], premium_stop_pct=EXIT_PRIMARY_PCT,
                qty=QTY, seeds=5,
            )
            null_gate_res = null_gate(
                headline_metrics.get("exp_dollar_per_trade"),
                headline_metrics.get("drop_top5_mean_dollar"), null_res)
            print(f"    null_mean={null_res.get('per_trade_mean')} "
                  f"beats_mean={null_gate_res.get('beats_null_mean')} "
                  f"beats_max={null_gate_res.get('beats_null_max')}")
        except Exception as exc:  # noqa: BLE001 — surface, never crash the run
            null_res = {"error": str(exc)}
            null_gate_res = {"null_pass": None, "error": str(exc)}
            print(f"    null ERROR: {exc}")

    # ── gate_9: regime split (diagnostic) ─────────────────────────────────────
    regime_res = regime_split(headline_rows, vix, spy)

    # ── verdict synthesis (pass_bar.required_for_SHIP_LIVE_verdict) ──────────
    causality_ok = poison_res["verdict"] == "PASS"
    oos_ok = bool(headline_metrics.get("oos_sign_stable"))
    wf_ok = wf_headline.get("verdict") == "PASS"
    sw_ok = sw_headline.get("verdict") == "PASS"
    dsr_ok = headline_metrics.get("dsr_verdict") != "FAIL"
    drop3_ok = (headline_metrics.get("drop_top3_mean_dollar") or 0) > 0
    drop5_ok = (headline_metrics.get("drop_top5_mean_dollar") or 0) > 0
    null_ok = bool(null_gate_res.get("null_pass")) if null_gate_res else False
    gate_11_ok = gate_11["verdict"] != "CONFIRMED_RESKIN_KEEP_DORMANT"

    gates = {
        "gate_2_oos_sign_stable": oos_ok,
        "gate_3_walk_forward_ge_0.70": wf_ok,
        "gate_4_sub_window_stable": sw_ok,
        "gate_5_beats_random_null": null_ok,
        "gate_6_drop_top3_and_top5_positive": bool(drop3_ok and drop5_ok),
        "gate_7_dsr_not_fail": dsr_ok,
        "gate_8_causality": causality_ok,
        "gate_11_independence_hard_gate": gate_11_ok,
    }
    ship = all(gates.values())
    blockers = [k for k, v in gates.items() if not v]

    if gate_11["verdict"] == "CONFIRMED_RESKIN_KEEP_DORMANT":
        verdict = "KEEP-DORMANT (confirmed reskin of #1 vwap_continuation, gate_11 HARD BLOCK — regardless of gates 1-10)"
    elif ship:
        verdict = "SHIP-LIVE-CANDIDATE (WATCH_ONLY -> heartbeat wiring proposal is a SEPARATE J-REVOKE decision, per spec explicit_non_goals)"
    else:
        verdict = "BLOCKED (fails one or more required gates on the PRIMARY chart-stop-only config)"

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/vwap_trend_pullback_honest_study.py",
        "spec": str(SPEC.relative_to(PROJECT)).replace("\\", "/"),
        "setup": "VWAP_TREND_PULLBACK (H4)",
        "data": {"spy": SPY_CSV.name, "vix": VIX_CSV.name, "days": len(days),
                  "oos_cut_date": oos_cut_date},
        "method": {
            "fills": "lib.simulator_real.simulate_trade_real (real OPRA, causal next-bar-open)",
            "qty": QTY, "strike_tiers_sim_convention": TIERS,
            "exit_config_PRIMARY": {"premium_stop_pct": EXIT_PRIMARY_PCT,
                                     "note": "chart-stop-only, matches vwap_trend_pullback_watcher.DEFAULT_PREMIUM_STOP_PCT — the config the live watcher would actually trade"},
            "exit_config_SECONDARY_disclosure_only": {"premium_stop_pct": EXIT_SECONDARY_PCT,
                                                        "metrics_ATM": summ_secondary,
                                                        "note": "NOT gated. Reported for continuity with the 2026-06-19 ratify only."},
            "n_trials_dsr": N_TRIALS_DSR, "wf_gate": WF_GATE, "oos_split_frac": OOS_SPLIT_FRAC,
            "headline_tier": headline_tier,
        },
        "causality": {"future_poison": poison_res, "entry_next_bar": entry_res,
                       "verdict": "PASS" if causality_ok else "FAIL"},
        "gate_9_regime_split": regime_res,
        "gate_10_entry_time_distribution": time_dist,
        "gate_11_independence_reskin_recheck": gate_11,
        "gate_5_random_entry_null": {"null": null_res, "gate": null_gate_res},
        "metrics_by_tier_PRIMARY": {k: v["metrics"] for k, v in tier_results.items()},
        "coverage_by_tier_PRIMARY": {k: v["coverage"] for k, v in tier_results.items()},
        "walk_forward_PRIMARY_headline": wf_headline,
        "sub_window_stability_PRIMARY_headline": sw_headline,
        "gates": gates,
        "blockers": blockers,
        "verdict": verdict,
        "honest_caveats": [
            "Proxy strikes (nearest-cached, L58) — directionally valid, $ modestly off.",
            "SPY-direction != option edge (C3/L58).",
            "gate_11 is HARD/BLOCKING per the pre-registered spec: even if gates 1-10 all "
            "pass, a confirmed reskin (same_side_overlap >= 0.80 vs #1 AND no independently "
            "clearing after-10:30 subset) forces KEEP-DORMANT, full stop.",
            "This study does NOT wire the detector regardless of verdict (explicit_non_goals "
            "in the frozen spec) — a passing scorecard authorizes a NEW proposal doc, not a "
            "silent flag flip. J holds REVOKE per Rule 9/OP-25.",
        ],
        "prior_findings_summary": [
            "Artifact 1 (vwap-trend-pullback-LIVE.json): headline +$45.88/tr used premium_stop=-0.08, not chart-stop-only.",
            "Artifact 2 (vwap-trend-pullback-regime-gate.json): no causal regime gate rescues chart-stop-only.",
            "Artifact 3 (vwap-trend-pullback-gate-own-oos.json): vix_lt_18 was an own-OOS overfit artifact.",
            "Artifact 4 (VWAP-PULLBACK-EDGE-VERIFY.json): H4 signal-days were a 100% same-side subset of #1 on the 2025-01..2026-06-16 window.",
        ],
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[study] wrote {OUT_JSON}")

    md_lines = [
        f"# VWAP_TREND_PULLBACK (H4) — honest real-fills study on the LIVE (chart-stop-only) exit config",
        "",
        f"_Run {dt.date.today().isoformat()} • pre-registered spec `{out['spec']}` (frozen 2026-07-10) "
        f"• real OPRA fills • byte-for-byte detector reuse • $0, pure-Python._",
        "",
        f"## VERDICT: **{verdict}**",
        "",
        f"Data through {SPY_CSV.name.split('_')[-1].replace('.csv','')} ({len(days)} trading days). "
        f"Headline tier: {headline_tier}, PRIMARY exit config (chart-stop-only, premium_stop_pct={EXIT_PRIMARY_PCT}).",
        "",
        "## Gate table",
        "",
        "| gate | result |",
        "|---|---|",
    ]
    for k, v in gates.items():
        md_lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    md_lines += [
        "",
        f"**gate_11 (HARD, BLOCKING) verdict: {gate_11['verdict']}** — "
        f"same-side day-overlap vs #1 vwap_continuation = "
        f"{independence['vwap_continuation']['same_side_day_overlap']} "
        f"(reskin threshold >= {OVERLAP_MAX}).",
        "",
        "## Headline metrics (PRIMARY, chart-stop-only, ATM)",
        "",
        f"- n={headline_metrics.get('n')}, WR={headline_metrics.get('win_rate_pct')}%, "
        f"exp/tr=${headline_metrics.get('exp_dollar_per_trade')}, "
        f"OOS exp/tr=${headline_metrics.get('oos_exp_dollar')}, "
        f"WF median={wf_headline.get('median_wf_norm')}, "
        f"sub-window n_hurt={sw_headline.get('n_hurt')}, "
        f"DSR={headline_metrics.get('dsr_verdict')}",
        "",
        "## gate_10 entry-time distribution",
        "",
        f"- pct_signals_after_1030 = {time_dist['pct_signals_after_1030']} "
        f"({'FALSIFIES' if time_dist['coverage_hole_claim_falsified'] else 'supports'} "
        "the 'fills the afternoon coverage hole' framing per the spec's own hard threshold of 0.30).",
    ]
    if after_1030_result:
        md_lines.append(
            f"- after-10:30-only subset (n={after_1030_result['n_signals']}): "
            f"exp/tr=${after_1030_result['metrics'].get('exp_dollar_per_trade')}, "
            f"OOS stable={after_1030_result['metrics'].get('oos_sign_stable')}, "
            f"clears_own_bar={after_1030_result['clears_own_bar']}"
        )
    md_lines += [
        "",
        "## Honest caveats",
        "",
    ] + [f"- {c}" for c in out["honest_caveats"]]
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"[study] wrote {OUT_MD}")


if __name__ == "__main__":
    main()
