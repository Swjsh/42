"""B8 — TOUCH-AND-GO vs #1 VWAP_CONTINUATION: matched-day HEAD-TO-HEAD A/B (Angle V).

THE QUESTION (priority re-test). B7 found the S1 VWAP touch-and-go (ITM-2 / call) posts
OOS $178.32/tr vs the LIVE #1 vwap_continuation $120.11/tr (+$58/tr). But the two share
~99% of their call-days. So is the +$58 lift a GENUINE BETTER ENTRY TRIGGER on the SHARED
days, or just a DIFFERENT DAY-SET (a day-selection RELABEL)?

THE TEST. Detect the per-day signal sets of BOTH:
  (a) the UN-refined #1 vwap_continuation  (byte-for-byte the LIVE detector:
      _edgehunt_vwap_continuation.detect_signals, full pattern, breakout+pullback,
      no VIX gate -- this IS what vwap_continuation_watcher ships), and
  (b) the S1 touch-and-go               (_b7_vwap_structures.detect_touch_and_go).

Restrict to ITM-2 / CALL (strike_offset=-2, side='C') -- the EXACT cell B7 reported as
the survivor and the tier J would flip (Bold = ITM-2, C29).

Then take the MATCHED-DAY SUBSET = the set of trading days on which BOTH triggers fire a
call signal. On THAT SAME day-set ONLY, run each trigger through real OPRA fills
(lib.simulator_real.simulate_trade_real, the only WR authority, C1) using EACH trigger's
OWN entry bar (touch-and-go = the 2-bar resume confirmation bar; #1 = its own
first-continuation bar). Same days, same strike, same stop, same exits -> the ONLY thing
that differs is the ENTRY BAR. That isolates the entry trigger from the day filter.

REPORT (REAL numbers, C7):
  * matched-day n (how many shared call-days),
  * matched-day FULL/tr and OOS/tr for EACH trigger, and the delta,
  * OOS-ALONE drop-top5 for each trigger (L173 de-concentration on the matched set),
  * no-truncation for each trigger (L171, sign stable at chart-stop-only),
  * the un-matched (disjoint) days each trigger trades alone, as disclosure.

VERDICT:
  GENUINE_TRIGGER -- the lift SURVIVES on the matched-day subset (touch-and-go OOS/tr > #1
    OOS/tr on the SAME days, touch-and-go OOS-alone drop-top5 still > 0, no truncation).
    A real entry improvement worth J's daytime flip.
  RELABEL -- the lift WASHES on the matched days (touch-and-go <= #1 on the same days):
    the +$58 was just a different day filter, NOT a better trigger. Do NOT ship.

Tier under test: ITM-2 / CALL (C29 -- knobs don't transfer; test the tier you claim).
Stop: v15 -8% tight premium stop. Real OPRA fills. Pure Python, $0. No live orders.

Writes analysis/recommendations/B8-TOUCHANDGO-MATCHED-SCORECARD.{md,json} (REAL numbers).
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b8_touchandgo_matched.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # backtest/
ROOT = REPO.parent                            # repo root (42/)
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._b7_vwap_structures import detect_touch_and_go  # noqa: E402
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_MD = ROOT / "analysis" / "recommendations" / "B8-TOUCHANDGO-MATCHED-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "B8-TOUCHANDGO-MATCHED-SCORECARD.json"

# ── The cell under test (C29: test the tier you claim) ──────────────────────────
STRIKE_OFFSET = -2          # ITM-2 (Bold tier)
SIDE = "C"                  # call only (the B7 survivor)
PREMIUM_STOP_PCT = -0.08    # v15 tight stop
CHART_STOP_ONLY = -0.99
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = 2026
NULL_SEEDS = 20

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)


# ════════════════════════════════════════════════════════════════════════════════
# SIM — re-run ONE trigger's call signals at the ITM-2 cell on real OPRA fills.
# ════════════════════════════════════════════════════════════════════════════════
def simulate_calls(signals, spy, vix, *, strike_offset, premium_stop_pct):
    """Run the CALL signals at (strike_offset, premium_stop_pct) on real OPRA fills."""
    rows = []
    n_cache_miss = n_sim_none = 0
    for sg in signals:
        if sg.side != "C":
            continue
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm + strike_offset            # call: atm + offset (offset<0 => ITM)
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=None,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "b8"],
            side=sg.side, qty=QTY, setup="B8_MATCHED", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        rows.append({"date": str(d), "side": sg.side,
                     "pnl": round(float(fill.dollar_pnl), 2),
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})
    return rows, {"cache_miss": n_cache_miss, "sim_none": n_sim_none}


# ════════════════════════════════════════════════════════════════════════════════
# METRICS
# ════════════════════════════════════════════════════════════════════════════════
def _per_trade(rows) -> Optional[float]:
    return round(float(np.mean([r["pnl"] for r in rows])), 2) if rows else None


def _total(rows) -> Optional[float]:
    return round(float(np.sum([r["pnl"] for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows) -> Optional[float]:
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    if not by_day:
        return None
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(float(np.mean(kept)), 2) if kept else None


def _split_is_oos(rows):
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    return is_rows, oos_rows


def evaluate(rows) -> dict:
    is_rows, oos_rows = _split_is_oos(rows)
    return {
        "n": len(rows),
        "days": len({r["date"] for r in rows}),
        "full_per_trade": _per_trade(rows),
        "full_total": _total(rows),
        "is_n": len(is_rows), "is_per_trade": _per_trade(is_rows),
        "oos_n": len(oos_rows), "oos_per_trade": _per_trade(oos_rows),
        "oos_total": _total(oos_rows),
        "drop_top5_full": _drop_top5_per_trade(rows),
        "drop_top5_oos": _drop_top5_per_trade(oos_rows),     # L173 decisive de-conc
        "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / len(rows), 1) if rows else None,
    }


def map_candidate_signals(call_signals, spy, rth):
    """Build CandidateSignal list (call-only) indexed into RTH-reset frame for fraud_gates."""
    out = []
    for s in call_signals:
        if s.side != "C":
            continue
        ts = spy.iloc[s.bar_idx]["timestamp_et"]
        match = rth.index[rth["timestamp_et"] == ts]
        if len(match) == 0:
            continue
        out.append(CandidateSignal(bar_idx=int(match[0]), side=s.side,
                                   rejection_level=float(s.stop_level),
                                   note=s.note or "b8"))
    return out


def no_truncation_check(call_signals, spy, vix):
    """Sign-stability (L171): does FULL per-trade hold sign at chart-stop-only (-0.99)?

    Returns (no_truncation_pass, chosen_pt, chart_stop_only_pt).
    """
    chosen, _ = simulate_calls(call_signals, spy, vix, strike_offset=STRIKE_OFFSET,
                               premium_stop_pct=PREMIUM_STOP_PCT)
    loose, _ = simulate_calls(call_signals, spy, vix, strike_offset=STRIKE_OFFSET,
                              premium_stop_pct=CHART_STOP_ONLY)
    cpt = _per_trade(chosen)
    lpt = _per_trade(loose)
    # truncation artifact iff chosen>0 but chart-stop-only flips negative (tight stop is the edge)
    artifact = bool(cpt is not None and lpt is not None and cpt > 0 and lpt < 0)
    return (not artifact), cpt, lpt


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b8] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)
    print(f"[b8] trading_days={n_days} window={spy['timestamp_et'].iloc[0].date()}.."
          f"{spy['timestamp_et'].iloc[-1].date()}", flush=True)

    # ── Detect both triggers ────────────────────────────────────────────────────
    cont_sigs = detect_vwap_continuation(days, vix, breakout_only=False,
                                         put_needs_rising_vix=False)
    tg_sigs = detect_touch_and_go(days)

    # call-only, with date mapping
    def call_day_map(sigs):
        m = {}
        for s in sigs:
            if s.side != "C":
                continue
            d = str(spy.iloc[s.bar_idx]["timestamp_et"].date())
            m[d] = s          # one causal entry/day already (detector breaks after first)
        return m

    cont_days = call_day_map(cont_sigs)
    tg_days = call_day_map(tg_sigs)
    matched_dates = sorted(set(cont_days) & set(tg_days))
    cont_only = sorted(set(cont_days) - set(tg_days))
    tg_only = sorted(set(tg_days) - set(cont_days))

    overlap_pct_of_cont = round(100 * len(matched_dates) / len(cont_days), 1) if cont_days else 0.0
    overlap_pct_of_tg = round(100 * len(matched_dates) / len(tg_days), 1) if tg_days else 0.0
    print(f"\n[b8] #1 vwap_continuation CALL-days = {len(cont_days)}", flush=True)
    print(f"[b8] S1 touch-and-go      CALL-days = {len(tg_days)}", flush=True)
    print(f"[b8] MATCHED (both fire)  CALL-days = {len(matched_dates)} "
          f"({overlap_pct_of_cont}% of #1, {overlap_pct_of_tg}% of touch-and-go)", flush=True)
    print(f"[b8] #1-only days = {len(cont_only)}  touch-and-go-only days = {len(tg_only)}",
          flush=True)

    # ── Matched-day signal lists (each trigger's OWN entry bar, shared days only) ─
    cont_matched = [cont_days[d] for d in matched_dates]
    tg_matched = [tg_days[d] for d in matched_dates]

    # ── Simulate each trigger on the MATCHED day-set (ITM-2 / call / -8%) ────────
    cont_rows, cont_cov = simulate_calls(cont_matched, spy, vix,
                                         strike_offset=STRIKE_OFFSET,
                                         premium_stop_pct=PREMIUM_STOP_PCT)
    tg_rows, tg_cov = simulate_calls(tg_matched, spy, vix,
                                     strike_offset=STRIKE_OFFSET,
                                     premium_stop_pct=PREMIUM_STOP_PCT)
    cont_m = evaluate(cont_rows)
    tg_m = evaluate(tg_rows)

    # ── No-truncation (L171) per trigger on the matched set ─────────────────────
    cont_notrunc, cont_cpt, cont_lpt = no_truncation_check(cont_matched, spy, vix)
    tg_notrunc, tg_cpt, tg_lpt = no_truncation_check(tg_matched, spy, vix)

    # ── Random-null (L172) per trigger on the matched set (full fraud verdict) ──
    cont_cand = map_candidate_signals(cont_matched, spy, rth)
    tg_cand = map_candidate_signals(tg_matched, spy, rth)
    cont_fraud = verify_candidate(cont_cand, rth, strike_offset=STRIKE_OFFSET,
                                  premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                  setup="B8_CONT", seeds=NULL_SEEDS)
    tg_fraud = verify_candidate(tg_cand, rth, strike_offset=STRIKE_OFFSET,
                                premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                setup="B8_TG", seeds=NULL_SEEDS)

    # ── Deltas (touch-and-go MINUS #1 on the SAME days) ─────────────────────────
    def _d(a, b):
        return round(a - b, 2) if (a is not None and b is not None) else None

    delta_full = _d(tg_m["full_per_trade"], cont_m["full_per_trade"])
    delta_oos = _d(tg_m["oos_per_trade"], cont_m["oos_per_trade"])
    delta_oos_dt5 = _d(tg_m["drop_top5_oos"], cont_m["drop_top5_oos"])

    print(f"\n[b8] === MATCHED-DAY HEAD-TO-HEAD (ITM-2 / call / -8%) ===", flush=True)
    print(f"  #1  vwap_continuation: n={cont_m['n']} days={cont_m['days']} "
          f"full/tr=${cont_m['full_per_trade']} OOS/tr=${cont_m['oos_per_trade']} "
          f"(oos_n={cont_m['oos_n']}) OOS-dropT5=${cont_m['drop_top5_oos']} "
          f"notrunc={cont_notrunc}(chart=${cont_lpt}) null={cont_fraud.null_pass}", flush=True)
    print(f"  S1  touch_and_go     : n={tg_m['n']} days={tg_m['days']} "
          f"full/tr=${tg_m['full_per_trade']} OOS/tr=${tg_m['oos_per_trade']} "
          f"(oos_n={tg_m['oos_n']}) OOS-dropT5=${tg_m['drop_top5_oos']} "
          f"notrunc={tg_notrunc}(chart=${tg_lpt}) null={tg_fraud.null_pass}", flush=True)
    print(f"  DELTA (TG - #1)      : full/tr={delta_full}  OOS/tr={delta_oos}  "
          f"OOS-dropT5={delta_oos_dt5}", flush=True)

    # ── VERDICT logic ───────────────────────────────────────────────────────────
    tg_oos = tg_m["oos_per_trade"]
    cont_oos = cont_m["oos_per_trade"]
    tg_oos_dt5 = tg_m["drop_top5_oos"]
    lift_survives = bool(
        tg_oos is not None and cont_oos is not None and tg_oos > cont_oos
        and tg_oos_dt5 is not None and tg_oos_dt5 > 0
        and tg_notrunc
    )
    verdict = "GENUINE_TRIGGER" if lift_survives else "RELABEL"

    # Why-string
    if lift_survives:
        why = (f"On the {len(matched_dates)} SHARED call-days, touch-and-go OOS/tr "
               f"${tg_oos} BEATS #1 ${cont_oos} (+${delta_oos}/tr), AND touch-and-go "
               f"OOS-alone drop-top5 ${tg_oos_dt5} > 0, AND no truncation "
               f"(chart-stop-only ${tg_lpt} holds sign). The lift is a BETTER ENTRY "
               f"trigger on the same day-set, not a day-selection relabel.")
    else:
        reasons = []
        if not (tg_oos is not None and cont_oos is not None and tg_oos > cont_oos):
            reasons.append(f"touch-and-go OOS/tr ${tg_oos} does NOT beat #1 ${cont_oos} "
                           f"on the shared days (delta ${delta_oos})")
        if not (tg_oos_dt5 is not None and tg_oos_dt5 > 0):
            reasons.append(f"touch-and-go OOS-alone drop-top5 ${tg_oos_dt5} <= 0 "
                           f"(concentration: lift is a few big days)")
        if not tg_notrunc:
            reasons.append(f"truncation artifact: chart-stop-only ${tg_lpt} flips sign "
                           f"vs ${tg_cpt} (L171)")
        why = ("WASHES on the matched days -> the B7 +$58 lift came from a DIFFERENT "
               "DAY-SET, not a better entry trigger. " + " ; ".join(reasons)
               + " Do NOT touch the live edge.")

    print(f"\n[b8] VERDICT: {verdict}\n  {why}", flush=True)

    # ── Disjoint-day disclosure: what each trigger trades ALONE ─────────────────
    cont_only_sigs = [cont_days[d] for d in cont_only]
    tg_only_sigs = [tg_days[d] for d in tg_only]
    cont_only_rows, _ = simulate_calls(cont_only_sigs, spy, vix,
                                       strike_offset=STRIKE_OFFSET,
                                       premium_stop_pct=PREMIUM_STOP_PCT)
    tg_only_rows, _ = simulate_calls(tg_only_sigs, spy, vix,
                                     strike_offset=STRIKE_OFFSET,
                                     premium_stop_pct=PREMIUM_STOP_PCT)
    cont_only_m = evaluate(cont_only_rows)
    tg_only_m = evaluate(tg_only_rows)

    summary = {
        "campaign": "B8 — touch-and-go vs #1 vwap_continuation matched-day A/B (Angle V)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "cell_under_test": {"strike_offset": STRIKE_OFFSET, "tier": "ITM-2",
                            "side": SIDE, "premium_stop_pct": PREMIUM_STOP_PCT},
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "detectors": {
            "trigger_1_vwap_continuation": ("byte-for-byte LIVE detector "
                "_edgehunt_vwap_continuation.detect_signals (full pattern, breakout+pullback, "
                "no VIX gate; live port = vwap_continuation_watcher.py)"),
            "trigger_S1_touch_and_go": "_b7_vwap_structures.detect_touch_and_go (2-bar touch+resume)",
        },
        "day_overlap": {
            "cont_call_days": len(cont_days),
            "touch_and_go_call_days": len(tg_days),
            "matched_call_days": len(matched_dates),
            "overlap_pct_of_cont": overlap_pct_of_cont,
            "overlap_pct_of_touch_and_go": overlap_pct_of_tg,
            "cont_only_days": len(cont_only),
            "touch_and_go_only_days": len(tg_only),
            "matched_dates": matched_dates,
            "cont_only_dates": cont_only,
            "touch_and_go_only_dates": tg_only,
        },
        "matched_day_head_to_head": {
            "trigger_1_vwap_continuation": {
                "metrics": cont_m, "coverage": cont_cov,
                "no_truncation_pass": cont_notrunc,
                "chosen_per_trade": cont_cpt, "chart_stop_only_per_trade": cont_lpt,
                "fraud": cont_fraud.as_dict(),
            },
            "trigger_S1_touch_and_go": {
                "metrics": tg_m, "coverage": tg_cov,
                "no_truncation_pass": tg_notrunc,
                "chosen_per_trade": tg_cpt, "chart_stop_only_per_trade": tg_lpt,
                "fraud": tg_fraud.as_dict(),
            },
            "delta_tg_minus_cont": {
                "full_per_trade": delta_full,
                "oos_per_trade": delta_oos,
                "oos_drop_top5": delta_oos_dt5,
            },
        },
        "disjoint_day_disclosure": {
            "cont_only_metrics": cont_only_m,
            "touch_and_go_only_metrics": tg_only_m,
        },
        "verdict": verdict,
        "verdict_reason": why,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[b8] wrote {OUT_JSON}\n[b8] wrote {OUT_MD}", flush=True)
    return 0


def write_md(s: dict) -> None:
    h2h = s["matched_day_head_to_head"]
    c = h2h["trigger_1_vwap_continuation"]
    t = h2h["trigger_S1_touch_and_go"]
    cm, tm = c["metrics"], t["metrics"]
    dl = h2h["delta_tg_minus_cont"]
    ov = s["day_overlap"]
    L = []
    L.append("# B8 — Touch-and-Go vs #1 VWAP_Continuation: Matched-Day A/B (Angle V)\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Cell under test: **ITM-2 / CALL / -8% stop** (C29 — test the tier you claim)")
    L.append(f"- Fills: {s['fills_authority']}")
    L.append(f"- OOS split: {s['oos_split']}\n")
    L.append(f"## VERDICT: **{s['verdict']}**\n")
    L.append(f"{s['verdict_reason']}\n")
    L.append("## Day overlap (the crux — do they trade the same days?)\n")
    L.append(f"- #1 vwap_continuation CALL-days: **{ov['cont_call_days']}**")
    L.append(f"- S1 touch-and-go CALL-days: **{ov['touch_and_go_call_days']}**")
    L.append(f"- MATCHED (both fire) CALL-days: **{ov['matched_call_days']}** "
             f"({ov['overlap_pct_of_cont']}% of #1, {ov['overlap_pct_of_touch_and_go']}% of touch-and-go)")
    L.append(f"- #1-only days: {ov['cont_only_days']}  |  touch-and-go-only days: {ov['touch_and_go_only_days']}\n")
    L.append("## Matched-day head-to-head (SAME days, only the ENTRY differs)\n")
    L.append("| trigger | n | days | full/tr | OOS/tr | oos_n | OOS-dropT5 | no-trunc (chart-only/tr) | null pass | WR% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    L.append(f"| #1 vwap_continuation | {cm['n']} | {cm['days']} | ${cm['full_per_trade']} | "
             f"${cm['oos_per_trade']} | {cm['oos_n']} | ${cm['drop_top5_oos']} | "
             f"{c['no_truncation_pass']} (${c['chart_stop_only_per_trade']}) | "
             f"{c['fraud'].get('null_pass')} | {cm['wr_pct']} |")
    L.append(f"| S1 touch-and-go | {tm['n']} | {tm['days']} | ${tm['full_per_trade']} | "
             f"${tm['oos_per_trade']} | {tm['oos_n']} | ${tm['drop_top5_oos']} | "
             f"{t['no_truncation_pass']} (${t['chart_stop_only_per_trade']}) | "
             f"{t['fraud'].get('null_pass')} | {tm['wr_pct']} |")
    L.append(f"| **DELTA (TG − #1)** | | | **${dl['full_per_trade']}** | **${dl['oos_per_trade']}** | | "
             f"**${dl['oos_drop_top5']}** | | | |")
    L.append("")
    L.append("## Disjoint-day disclosure (what each trades ALONE — context, not the test)\n")
    dis = s["disjoint_day_disclosure"]
    com, tom = dis["cont_only_metrics"], dis["touch_and_go_only_metrics"]
    L.append("| trigger-only set | n | days | full/tr | OOS/tr | OOS-dropT5 |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| #1-only days | {com['n']} | {com['days']} | ${com['full_per_trade']} | "
             f"${com['oos_per_trade']} | ${com['drop_top5_oos']} |")
    L.append(f"| touch-and-go-only days | {tom['n']} | {tom['days']} | ${tom['full_per_trade']} | "
             f"${tom['oos_per_trade']} | ${tom['drop_top5_oos']} |")
    L.append("")
    L.append("## How to read this\n")
    L.append("- The test isolates the **entry trigger** from the **day filter**: both columns "
             "trade the SAME matched days at the SAME strike/stop/exits; the ONLY difference is "
             "WHICH BAR each trigger enters on.")
    L.append("- **GENUINE_TRIGGER** iff touch-and-go OOS/tr > #1 OOS/tr on the matched days AND "
             "touch-and-go OOS-alone drop-top5 > 0 AND no truncation (L171/L173).")
    L.append("- **RELABEL** iff the lift washes on the matched days — then B7's +$58 was a "
             "different day-set, not a better trigger; do NOT touch the live edge.")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, "
             "not WR alone (OP-14).")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
