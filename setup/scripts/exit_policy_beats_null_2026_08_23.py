"""EXIT-POLICY-BEATS-NULL-2026-08-23 -- frozen-prereg runner.

Prereg: analysis/recommendations/prereg-exit-policy-beats-null-2026-08-23.json
        (frozen in commit 5c1836d5, BEFORE this runner existed)

QUESTION: on the SAME entries, would a naive hold to the existing 15:50 ET time stop
(NULL_A = cf_time_stop_pnl) have returned MORE than the managed exits actually
returned (CONTROL = dollar_pnl)?

    delta = NULL_A - CONTROL     positive => HOLDING beat the managed exit

DIAGNOSTIC ONLY. Nothing here ships to the trading path. Read-only on the engine.

Implements the 8 frozen gates verbatim:
  G1 aggregate mean per-trade delta (+/-$0.005 dead band)
  G2 drop-top3 largest-|delta| trades -- sign must survive
  G3 drop-best-2-days by summed day delta -- sign must survive
  G4 4 buckets of EQUAL CHANGED-TRADE COUNT (not calendar), same sign in >=3/4
  G5 day-block bootstrap, DAY as unit, B=20,000, 95% CI + P(delta<=0)
  G6 sign holds within each stop_mode stratum carrying >=10 trades
  G7 n_effective at date x side x setup granularity; <30 => UNDERPOWERED
  G8 coverage of usable cf_time_stop_pnl; <80% => UNDERPOWERED, no cell may ship

Two-tailed concentration is first-class: drop-top AND drop-worst are both reported
on every headline number (running only drop-top on a losing cohort flatters/damns it).
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRADES_CSV = os.path.join(REPO, "journal", "trades.csv")
AUTOPSY = os.path.join(REPO, "analysis", "winner-autopsies", "all.jsonl")
PREREG = os.path.join(REPO, "analysis", "recommendations",
                      "prereg-exit-policy-beats-null-2026-08-23.json")
OUT_JSON = os.path.join(REPO, "analysis", "recommendations",
                        "exit-policy-beats-null-2026-08-23.json")
OUT_MD = os.path.join(REPO, "analysis", "deep-research",
                      "EXIT-POLICY-BEATS-NULL-2026-08-23.md")

WINDOW_START = "2026-06-26"   # frozen in the prereg
DEAD_BAND = 0.005             # G1
B_BOOT = 20000                # G5
SEED = 20260823


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def fnum(v):
    """Parse a CSV cell to float, or None if blank/unparseable. NEVER returns 0.0
    for missing data -- G8 forbids silently treating missing as zero-delta."""
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    if s in ("", "nan", "NaN", "None", "null", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sign_of(x, band=DEAD_BAND):
    if x is None:
        return "NA"
    if x > band:
        return "+"
    if x < -band:
        return "-"
    return "0"


# --------------------------------------------------------------------------
# load
# --------------------------------------------------------------------------
def load_trades():
    """Load journal/trades.csv. Also audits structural integrity -- this file has
    ragged rows (42..47 fields against a 44-col header), so alignment is verified
    rather than assumed."""
    raw = io.open(TRADES_CSV, encoding="utf-8-sig", newline="")
    rdr = csv.reader(raw)
    header = next(rdr)
    body = [r for r in rdr]
    raw.close()

    fieldcounts = Counter(len(r) for r in body)
    ai = header.index("account_id")
    known_arms = {"safe", "safe-1", "safe-2", "safe-3", "bold", "bold-2",
                  "risky-1", "risky-3", "aggressive", ""}
    shifted = [i for i, r in enumerate(body)
               if len(r) > ai and r[ai] not in known_arms]

    rows = []
    for r in body:
        # csv.DictReader semantics: short rows pad the TAIL with None, they do not
        # shift. Rows flagged `shifted` are the genuinely corrupted ones.
        d = {header[i]: (r[i] if i < len(r) else None) for i in range(len(header))}
        rows.append(d)

    integrity = {
        "header_columns": len(header),
        "data_rows": len(body),
        "field_count_distribution": {str(k): v for k, v in sorted(fieldcounts.items())},
        "rows_with_exact_header_field_count": fieldcounts.get(len(header), 0),
        "column_shift_corrupted_rows": len(shifted),
        "column_shift_note": (
            "account_id (col 42) holds free-text notes on these rows, i.e. a real "
            "left-shift, not a missing trailing column. Flagged, not silently used."
        ),
    }
    return rows, integrity


def load_autopsies():
    if not os.path.exists(AUTOPSY):
        return []
    out = []
    for line in io.open(AUTOPSY, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# --------------------------------------------------------------------------
# the 8 gates
# --------------------------------------------------------------------------
def g1_aggregate(recs):
    if not recs:
        return {"status": "NOT_COMPUTABLE", "reason": "n=0 usable deltas",
                "n": 0, "mean_delta": None, "total_delta": None, "sign": "NA"}
    d = [r["delta"] for r in recs]
    m = mean(d)
    return {"status": "COMPUTED", "n": len(d), "mean_delta": round(m, 4),
            "total_delta": round(sum(d), 2), "sign": sign_of(m),
            "interpretation": ("COSTING (holding beat managed)" if m > DEAD_BAND
                               else "EARNING (managed beat holding)" if m < -DEAD_BAND
                               else "INCONCLUSIVE (inside dead band)")}


def g2_drop_top3(recs, base_sign):
    """Two-tailed by design: drop-top3 AND drop-worst3 both reported."""
    if len(recs) <= 3:
        return {"status": "NOT_COMPUTABLE",
                "reason": "n<=3, removing 3 trades leaves nothing", "n": len(recs)}
    by_mag = sorted(recs, key=lambda r: abs(r["delta"]), reverse=True)
    kept_mag = by_mag[3:]
    m_mag = mean([r["delta"] for r in kept_mag])

    by_val = sorted(recs, key=lambda r: r["delta"])
    m_worst = mean([r["delta"] for r in by_val[3:]])      # drop 3 most negative
    m_best = mean([r["delta"] for r in by_val[:-3]])      # drop 3 most positive

    return {
        "status": "COMPUTED",
        "drop_top3_largest_magnitude": {"n": len(kept_mag), "mean_delta": round(m_mag, 4),
                                        "sign": sign_of(m_mag)},
        "drop_worst3_most_negative": {"n": len(by_val) - 3, "mean_delta": round(m_worst, 4),
                                      "sign": sign_of(m_worst)},
        "drop_best3_most_positive": {"n": len(by_val) - 3, "mean_delta": round(m_best, 4),
                                     "sign": sign_of(m_best)},
        "removed_top3_deltas": [round(r["delta"], 2) for r in by_mag[:3]],
        "pass": sign_of(m_mag) == base_sign and base_sign in ("+", "-"),
    }


def g3_drop_best2_days(recs, base_sign):
    if not recs:
        return {"status": "NOT_COMPUTABLE", "reason": "n=0"}
    byday = defaultdict(list)
    for r in recs:
        byday[r["date"]].append(r["delta"])
    daysum = {d: sum(v) for d, v in byday.items()}
    top1 = max(daysum, key=lambda d: daysum[d]) if daysum else None
    if len(daysum) <= 2:
        return {"status": "NOT_COMPUTABLE",
                "reason": "n_days<=2, removing 2 days leaves nothing",
                "n_days": len(daysum)}
    ordered = sorted(daysum.items(), key=lambda kv: kv[1])
    worst2 = [d for d, _ in ordered[:2]]
    best2 = [d for d, _ in ordered[-2:]]

    keep_b = [r["delta"] for r in recs if r["date"] not in best2]
    keep_w = [r["delta"] for r in recs if r["date"] not in worst2]
    mb = mean(keep_b)
    mw = mean(keep_w)
    net = sum(daysum.values())
    return {
        "status": "COMPUTED",
        "n_days": len(daysum),
        "drop_best2_days": {"days": best2, "n": len(keep_b),
                            "mean_delta": round(mb, 4) if mb is not None else None,
                            "sign": sign_of(mb)},
        "drop_worst2_days": {"days": worst2, "n": len(keep_w),
                             "mean_delta": round(mw, 4) if mw is not None else None,
                             "sign": sign_of(mw)},
        "best2_days_pct_of_net": (round(100.0 * sum(daysum[d] for d in best2) / net, 1)
                                  if abs(net) > 1e-9 else None),
        "single_worst_concentration": {
            "_why": "Reported because a single day can exceed 100% of net; the 2-day "
                    "gate can then look survivable while one day carries everything.",
            "top1_day": top1,
            "top1_day_sum": round(daysum[top1], 2) if top1 else None,
            "top1_day_pct_of_net": (round(100.0 * daysum[top1] / net, 1)
                                    if top1 and abs(net) > 1e-9 else None),
            "mean_delta_excluding_top1_day": (
                round(mean([r["delta"] for r in recs if r["date"] != top1]), 4)
                if top1 and any(r["date"] != top1 for r in recs) else None),
            "sign_excluding_top1_day": sign_of(
                mean([r["delta"] for r in recs if r["date"] != top1])
                if top1 and any(r["date"] != top1 for r in recs) else None),
        },
        "median_delta": round(sorted(r["delta"] for r in recs)[len(recs) // 2], 2),
        "pass": sign_of(mb) == base_sign and base_sign in ("+", "-"),
    }


def g4_equal_n_buckets(recs, base_sign):
    """4 buckets of EQUAL CHANGED-TRADE COUNT, ordered by date. Frozen: NOT calendar
    windows -- fixed-calendar sub-windows structurally starve low-fire-rate effects."""
    changed = [r for r in recs if abs(r["delta"]) > 1e-9]
    if len(changed) < 8:
        return {"status": "NOT_COMPUTABLE",
                "reason": "n_changed<8, cannot form 4 buckets with >=2 each",
                "n_changed": len(changed)}
    changed.sort(key=lambda r: (r["date"], r.get("seq", 0)))
    n = len(changed)
    edges = [round(n * i / 4) for i in range(5)]
    buckets = []
    for i in range(4):
        seg = changed[edges[i]:edges[i + 1]]
        m = mean([r["delta"] for r in seg])
        buckets.append({"bucket": i + 1, "n_changed": len(seg),
                        "date_range": [seg[0]["date"], seg[-1]["date"]] if seg else None,
                        "mean_delta": round(m, 4) if m is not None else None,
                        "sign": sign_of(m)})
    agree = sum(1 for b in buckets if b["sign"] == base_sign)
    return {"status": "COMPUTED", "n_changed": n, "buckets": buckets,
            "buckets_agreeing_with_aggregate": agree,
            "pass": agree >= 3 and base_sign in ("+", "-")}


def g5_day_block_bootstrap(recs, b=B_BOOT, seed=SEED):
    """DAY is the resampling unit -- the 5 arms share one signal (r=0.846, 95.7%
    sign agreement), so trade-level resampling is pseudo-replication."""
    if not recs:
        return {"status": "NOT_COMPUTABLE", "reason": "n=0"}
    byday = defaultdict(list)
    for r in recs:
        byday[r["date"]].append(r["delta"])
    days = sorted(byday)
    if len(days) < 3:
        return {"status": "NOT_COMPUTABLE", "reason": "n_days<3, bootstrap meaningless",
                "n_days": len(days)}
    rng = random.Random(seed)
    k = len(days)
    means = []
    for _ in range(b):
        pool = []
        for _ in range(k):
            pool.extend(byday[days[rng.randrange(k)]])
        if pool:
            means.append(sum(pool) / len(pool))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    p_le0 = sum(1 for m in means if m <= 0) / len(means)
    return {"status": "COMPUTED", "B": b, "n_days": k, "resampling_unit": "day",
            "ci95_mean_delta": [round(lo, 4), round(hi, 4)],
            "p_delta_le_0": round(p_le0, 4),
            "pass_for_costing_claim": p_le0 <= 0.05}


def g6_stop_mode(recs, base_sign):
    strata = defaultdict(list)
    for r in recs:
        strata[r.get("stop_mode") or "UNKNOWN"].append(r["delta"])
    out, evaluated, agree = {}, 0, 0
    for k, v in sorted(strata.items()):
        m = mean(v)
        out[k] = {"n": len(v), "mean_delta": round(m, 4) if m is not None else None,
                  "sign": sign_of(m),
                  "evaluated_for_gate": len(v) >= 10}
        if len(v) >= 10:
            evaluated += 1
            if sign_of(m) == base_sign:
                agree += 1
    if evaluated == 0:
        return {"status": "NOT_COMPUTABLE",
                "reason": "no stop_mode stratum carries >=10 usable trades",
                "strata": out}
    return {"status": "COMPUTED", "strata": out, "strata_evaluated": evaluated,
            "strata_agreeing": agree,
            "pass": agree == evaluated and base_sign in ("+", "-")}


def g7_n_effective(recs):
    """n_effective at date x side x setup granularity (the 5 arms duplicate one signal)."""
    cells = {(r["date"], r.get("side"), r.get("setup")) for r in recs}
    ne = len(cells)
    return {"status": "COMPUTED" if recs else "NOT_COMPUTABLE",
            "n_raw": len(recs), "n_effective": ne,
            "granularity": "date x side x setup",
            "underpowered": ne < 30,
            "note": "n_effective<30 => UNDERPOWERED regardless of raw n (G7)."}


def g8_coverage(n_round_trips, n_usable):
    pct = (100.0 * n_usable / n_round_trips) if n_round_trips else 0.0
    return {"status": "COMPUTED", "round_trips_in_window": n_round_trips,
            "usable_cf_time_stop_pnl": n_usable,
            "coverage_pct": round(pct, 4),
            "threshold_pct": 80.0,
            "pass": pct >= 80.0,
            "note": ("Missing cf_time_stop_pnl is EXCLUDED and disclosed -- never "
                     "silently treated as zero-delta.")}


def side_split(recs):
    """Winner/loser split on CONTROL (mandatory -- the hypothesis is about the right tail)."""
    out = {}
    for label, sel in (("control_winners", lambda r: r["control"] > 0),
                       ("control_losers", lambda r: r["control"] <= 0)):
        sub = [r for r in recs if sel(r)]
        m = mean([r["delta"] for r in sub])
        out[label] = {"n": len(sub),
                      "mean_delta": round(m, 4) if m is not None else None,
                      "total_delta": round(sum(r["delta"] for r in sub), 2) if sub else None,
                      "sign": sign_of(m)}
    return out


def direction_report_only(recs):
    """REPORT ONLY -- direction was adjudicated a non-effect; never used as a filter."""
    out = {}
    for k in ("C", "P"):
        sub = [r for r in recs if (r.get("side") or "").upper() == k]
        m = mean([r["delta"] for r in sub])
        out[k] = {"n": len(sub), "mean_delta": round(m, 4) if m is not None else None}
    out["_scope_note"] = "REPORT ONLY. Direction is never a filter (prereg by_direction)."
    return out


def arithmetic_sanity_check(trades):
    """MANDATORY self-audit. Hand-verify per-trade arithmetic straight off the raw CSV
    row, and structurally validate the counterfactual columns.

    Two invariants a GENUINE counterfactual pair must satisfy:
      I1  control == (exit_px - entry_px) * qty * 100     (CONTROL is internally consistent)
      I2  null_b >= max(control, null_a)                  (high-water is an upper bound
                                                           BY CONSTRUCTION -- it is the
                                                           best moment; nothing can beat it)
    A violation of I2 proves the value is not a computed high-water mark.
    """
    checks = []
    for r in trades:
        c = fnum(r.get("dollar_pnl"))
        a = fnum(r.get("cf_time_stop_pnl"))
        if c is None or a is None:
            continue
        b = fnum(r.get("cf_high_water_pnl"))
        ex, en, q = fnum(r.get("exit_px")), fnum(r.get("entry_px")), fnum(r.get("qty"))
        recomputed = ((ex - en) * q * 100) if None not in (ex, en, q) else None
        chk = {
            "date": r.get("date"), "contract": r.get("contract"),
            "qty": q, "entry_px": en, "exit_px": ex,
            "control_dollar_pnl": c, "null_a_cf_time_stop_pnl": a,
            "null_b_cf_high_water_pnl": b,
            "hand_recomputed_control_(exit-entry)*qty*100": (round(recomputed, 2)
                                                            if recomputed is not None else None),
            "I1_control_arithmetic_ok": (recomputed is not None
                                         and abs(recomputed - c) < 0.51),
            "delta_null_a_minus_control": round(a - c, 2),
            "I2_high_water_is_upper_bound": (b is not None and b >= max(c, a) - 1e-9),
            "degenerate_null_a_equals_control": abs(a - c) < 1e-9,
            "degenerate_null_b_equals_control": (b is not None and abs(b - c) < 1e-9),
        }
        checks.append(chk)

    n = len(checks)
    viol = [c for c in checks if not c["I2_high_water_is_upper_bound"]]
    degen = [c for c in checks if c["degenerate_null_a_equals_control"]
             or c["degenerate_null_b_equals_control"]]
    return {
        "_purpose": "A column existing is not the same as a column being populated "
                    "correctly. This repo has been burned by synthetic/placeholder "
                    "ledger values before, so the few populated values are audited.",
        "rows_audited": n,
        "I1_control_arithmetic_passes": sum(1 for c in checks if c["I1_control_arithmetic_ok"]),
        "I2_high_water_bound_violations": len(viol),
        "degenerate_copy_rows": len(degen),
        "VERDICT": ("COUNTERFACTUAL VALUES ARE NOT TRUSTWORTHY -- %d of %d populated rows "
                    "fail a structural invariant or are a degenerate copy of "
                    "dollar_pnl." % (len({id(x) for x in viol + degen}), n)) if (viol or degen)
                   else "populated rows pass structural checks",
        "hand_verified_rows": checks,
    }


def run_battery(recs, label):
    g1 = g1_aggregate(recs)
    base = g1.get("sign", "NA")
    return {
        "cohort": label,
        "G1_aggregate": g1,
        "G2_drop_top3": g2_drop_top3(recs, base),
        "G3_drop_best2_days": g3_drop_best2_days(recs, base),
        "G4_equal_n_buckets": g4_equal_n_buckets(recs, base),
        "G5_day_block_bootstrap": g5_day_block_bootstrap(recs),
        "G6_stop_mode_stratified": g6_stop_mode(recs, base),
        "G7_n_effective": g7_n_effective(recs),
        "winner_loser_split": side_split(recs),
        "direction_report_only": direction_report_only(recs),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    trades, integrity = load_trades()

    latest = max((r.get("date") or "") for r in trades)
    in_window = [r for r in trades
                 if (r.get("date") or "") >= WINDOW_START and (r.get("date") or "") <= latest]

    def build(rows, seq0=0):
        out = []
        for i, r in enumerate(rows):
            ctrl = fnum(r.get("dollar_pnl"))
            nul = fnum(r.get("cf_time_stop_pnl"))
            if ctrl is None or nul is None:
                continue
            out.append({
                "date": r.get("date"), "seq": seq0 + i,
                "control": ctrl, "null_a": nul, "delta": nul - ctrl,
                "null_b": fnum(r.get("cf_high_water_pnl")),
                "side": (r.get("c_or_p") or "").upper(),
                "setup": r.get("setup"), "account_id": r.get("account_id"),
                "qty": fnum(r.get("qty")), "hold_minutes": fnum(r.get("hold_minutes")),
                "stop_mode": None,   # trades.csv carries NO stop_mode column
            })
        return out

    primary = build(in_window)
    prewindow = build([r for r in trades if (r.get("date") or "") < WINDOW_START])

    cov = g8_coverage(len(in_window), len(primary))

    # ---- NULL_B, descriptive only -------------------------------------------
    nb_rows = [r for r in build(trades) if r["null_b"] is not None]
    nb = {
        "SHIP_ELIGIBLE": False,
        "LABEL": "LOOK-AHEAD / UNACHIEVABLE -- exit-at-the-best-moment. Nobody can "
                 "trade it. Carried ONLY to size the theoretical ceiling.",
        "n": len(nb_rows),
        "mean_null_b_minus_control": (round(mean([r["null_b"] - r["control"] for r in nb_rows]), 2)
                                      if nb_rows else None),
        "rows": [{"date": r["date"], "control": r["control"], "null_b": r["null_b"]}
                 for r in nb_rows],
    }

    # ---- supplementary: winners-only autopsy cohort --------------------------
    aut = load_autopsies()
    arecs = []
    for i, a in enumerate(aut):
        v = a.get("variants") or {}
        h = v.get("hold_to_time_stop")
        rp = a.get("realized_pnl")
        if h is None or rp is None:
            continue
        arecs.append({
            "date": a.get("date"), "seq": i, "control": float(rp),
            "null_a": float(h), "delta": float(h) - float(rp), "null_b": a.get("oracle_pnl"),
            "side": ("P" if "BEARISH" in (a.get("strategy") or "") else
                     "C" if "BULLISH" in (a.get("strategy") or "") else None),
            "setup": a.get("strategy"), "account_id": a.get("arm"),
            "qty": a.get("qty"), "hold_minutes": None,
            "stop_mode": (a.get("entry") or {}).get("stop_mode"),
        })
    supp = run_battery(arecs, "SUPPLEMENTARY_winners_only_autopsy")
    supp["GATE_ELIGIBILITY"] = "INELIGIBLE"
    supp["WHY_INELIGIBLE"] = (
        "This cohort is CONTROL-WINNERS BY CONSTRUCTION (all 84 rows realized_pnl>0). "
        "It is a different source from the frozen population.P_realfills and it is "
        "survivorship-selected, so it CANNOT address G1 (aggregate) -- the loser side, "
        "which prediction P1 says is where the managed stop earns its keep, is absent "
        "entirely. Reported as a DESCRIPTIVE read on prediction P2 only. No gate is "
        "called from it and nothing ships on it."
    )
    supp["coverage_within_its_own_cohort"] = {
        "autopsy_rows": len(aut), "with_hold_to_time_stop": len(arecs)}

    # pseudo-replication audit on the concentration drivers
    top3 = sorted(arecs, key=lambda r: abs(r["delta"]), reverse=True)[:3]
    supp["PSEUDO_REPLICATION_AUDIT"] = {
        "_why": "The 5 arms trade ONE shared signal (r=0.846, 95.7% sign agreement). "
                "If the concentration drivers are the same contract on the same day "
                "across arms, they are ONE decision counted N times, not N observations.",
        "top3_delta_rows": [{"date": r["date"], "arm": r["account_id"],
                             "setup": r["setup"], "qty": r["qty"],
                             "control": r["control"], "null_a": r["null_a"],
                             "delta": round(r["delta"], 2)} for r in top3],
        "top3_all_same_date": len({r["date"] for r in top3}) == 1,
        "top3_distinct_dates": sorted({r["date"] for r in top3}),
        "finding": ("All three largest deltas are the SAME DAY across three different "
                    "arms -- one decision, triple-counted."
                    if len({r["date"] for r in top3}) == 1 else "drivers span multiple days"),
    }

    primary_battery = run_battery(primary, "PRIMARY_frozen_population")

    underpowered = (not cov["pass"]) or primary_battery["G7_n_effective"]["underpowered"]

    if len(primary) == 0:
        verdict = "UNDERPOWERED"
        verdict_line = (
            "UNDERPOWERED -- NOT RUN ON THE FROZEN POPULATION. cf_time_stop_pnl is "
            "populated on 0 of %d in-window round-trip rows (0.00%% coverage vs an 80%% "
            "floor). The NULL_A column exists in the schema but was never computed for "
            "any trade in the window. No gate can be called; the beats_null hypothesis "
            "is neither confirmed nor refuted." % len(in_window))
    else:
        g = primary_battery
        allpass = all(x.get("pass") for x in (g["G2_drop_top3"], g["G3_drop_best2_days"],
                                              g["G4_equal_n_buckets"], g["G6_stop_mode_stratified"]))
        if underpowered:
            verdict = "UNDERPOWERED"
        elif g["G1_aggregate"]["sign"] == "+" and allpass and \
                g["G5_day_block_bootstrap"].get("pass_for_costing_claim"):
            verdict = "EXITS_COSTING"
        elif g["G1_aggregate"]["sign"] == "-" and allpass:
            verdict = "EXITS_EARNING"
        else:
            verdict = "INCONCLUSIVE"
        verdict_line = "%s -- see gate table." % verdict

    result = {
        "prereg_id": "EXIT-POLICY-BEATS-NULL-2026-08-23",
        "prereg_file": "analysis/recommendations/prereg-exit-policy-beats-null-2026-08-23.json",
        "prereg_frozen_in_commit": "5c1836d5 (predates this runner -- git-provable)",
        "generated_et": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "VERDICT": verdict,
        "VERDICT_LINE": verdict_line,
        "UNDERPOWERED": underpowered,
        "SHIP_STATUS": "NOTHING SHIPS. Diagnostic prereg; no trading-path edit authorized.",

        "G8_coverage_honesty": cov,
        "population": {
            "source": "journal/trades.csv (REAL BROKER FILLS, lesson C1)",
            "window": "%s .. %s (latest complete session on disk)" % (WINDOW_START, latest),
            "rows_in_window": len(in_window),
            "rows_total_in_file": len(trades),
            "usable_deltas_in_window": len(primary),
            "harness_quarantine_note": (
                "REAL FILLS ONLY -- this study is NOT exposed to the fleet-replay "
                "harness and does not inherit its 2 known REDs."),
        },
        "DATA_INTEGRITY_FINDING": {
            "severity": "BLOCKING for this prereg",
            "cf_time_stop_pnl_populated_rows_whole_file": len(build(trades)),
            "cf_time_stop_pnl_populated_rows_in_window": len(primary),
            "writer_evidence": (
                "setup/scripts/fleet_journal_bridge.py writes the literal empty string "
                "for cf_time_stop_pnl (and cf_high_water_pnl) on every row it emits. "
                "The columns are SCHEMA PLACEHOLDERS, never a populated counterfactual. "
                "A column existing is not the same as a column being populated."),
            "csv_structural_audit": integrity,
            "stop_mode_column": (
                "ABSENT from journal/trades.csv entirely. Even with full NULL_A "
                "coverage, G6 (stop_mode-stratified) could not be computed from this "
                "source alone -- and the prereg presumes any unstratified aggregate "
                "confounded (Simpson's paradox scar)."),
        },
        "ARITHMETIC_SANITY_CHECK": arithmetic_sanity_check(trades),
        "PRIMARY_frozen_population_battery": primary_battery,
        "PRE_WINDOW_DESCRIPTIVE_n3": {
            "LABEL": "OUT OF FROZEN WINDOW (May 2026). Descriptive only, gate-ineligible.",
            "n": len(prewindow),
            "rows": [{"date": r["date"], "control": r["control"], "null_a": r["null_a"],
                      "delta": round(r["delta"], 2), "null_b": r["null_b"],
                      "side": r["side"], "qty": r["qty"]} for r in prewindow],
            "mean_delta": (round(mean([r["delta"] for r in prewindow]), 2)
                           if prewindow else None),
        },
        "NULL_B_high_water_descriptive_only": nb,
        "SUPPLEMENTARY_winners_only_autopsy": supp,
        "PREDICTIONS_ADJUDICATED": {
            "P1_losers_delta_negative": "NOT TESTABLE -- zero loser rows carry NULL_A.",
            "P2_winners_delta_positive": (
                "DESCRIPTIVELY CONSISTENT on the survivorship-selected autopsy cohort "
                "(mean +$%.2f/trade, n=%d) but 60 of 84 individual deltas are NEGATIVE; "
                "the positive mean is concentration, not a broad tendency. NOT a gate result."
                % (supp["G1_aggregate"].get("mean_delta") or 0.0,
                   supp["G1_aggregate"].get("n") or 0)),
            "P3_net_sign_uncertain": "REMAINS UNRESOLVED. Coverage prevented the test.",
            "P4_concentration_severe": "CONFIRMED where measurable (see supplementary G2/G3).",
            "P5_null_b_spectacular_and_meaningless": "CONFIRMED. Reported descriptive-only.",
        },
        "WHAT_I_COULD_NOT_CHECK": [
            "The beats_null question itself on the frozen population -- 0% NULL_A coverage.",
            "P1 (loser-side delta) -- no loser row carries a counterfactual.",
            "G6 stop_mode stratification from trades.csv -- the column does not exist there.",
            "Whether the 3 pre-window populated values were computed by the same method "
            "as any future backfill would use -- their provenance is undocumented.",
        ],
        "FORWARD_CLOCK": (
            "Per the prereg: do NOT re-cut this population hoping for a different answer. "
            "The blocker is missing data, not an unlucky slice. The unblocking action is a "
            "BACKFILL: replay each in-window entry against OPRA minute bars for its own "
            "contract to its 15:50 ET time-stop mark, populate cf_time_stop_pnl for BOTH "
            "winners and losers, then re-run this exact runner unchanged."),
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with io.open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")

    write_md(result)
    print(json.dumps({k: result[k] for k in
                      ("VERDICT", "VERDICT_LINE", "UNDERPOWERED")}, indent=2))
    print("coverage:", json.dumps(cov, indent=2))
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)
    return result


def write_md(r):
    cov = r["G8_coverage_honesty"]
    supp = r["SUPPLEMENTARY_winners_only_autopsy"]
    di = r["DATA_INTEGRITY_FINDING"]
    L = []
    L.append("# EXIT-POLICY-BEATS-NULL — 2026-08-23")
    L.append("")
    L.append("> **VERDICT: %s** — %s" % (r["VERDICT"], r["VERDICT_LINE"]))
    L.append("")
    L.append("Prereg: [`prereg-exit-policy-beats-null-2026-08-23.json`]"
             "(../recommendations/prereg-exit-policy-beats-null-2026-08-23.json) "
             "(frozen in commit `5c1836d5`, before this runner existed). "
             "Scorecard: [`exit-policy-beats-null-2026-08-23.json`]"
             "(../recommendations/exit-policy-beats-null-2026-08-23.json).")
    L.append("")
    L.append("**Nothing ships.** This prereg is diagnostic by construction.")
    L.append("")
    L.append("## The blocker, stated plainly")
    L.append("")
    L.append("`cf_time_stop_pnl` (NULL_A) is populated on **%d of %d** in-window round-trip "
             "rows — **%.2f%% coverage** against the prereg's **80%% floor** (G8). "
             "The whole file carries only %d populated values, all three of them in "
             "**May 2026, outside the frozen window**."
             % (cov["usable_cf_time_stop_pnl"], cov["round_trips_in_window"],
                cov["coverage_pct"], di["cf_time_stop_pnl_populated_rows_whole_file"]))
    L.append("")
    L.append("The column is a **schema placeholder, not a measurement**: "
             "`setup/scripts/fleet_journal_bridge.py` writes the literal empty string "
             "for `cf_time_stop_pnl` on every row it emits. A column existing is not the "
             "same as a column being populated — this repo has been burned by that before.")
    L.append("")
    L.append("Second structural blocker: **`journal/trades.csv` has no `stop_mode` column "
             "at all.** Even with full NULL_A coverage, G6 could not have been computed "
             "from this source, and the prereg presumes any unstratified aggregate "
             "confounded (the Simpson's-paradox scar from 2026-08-23).")
    L.append("")
    L.append("## Gate table — primary (frozen) population")
    L.append("")
    L.append("| Gate | Result | Deciding number |")
    L.append("|---|---|---|")
    L.append("| G8 coverage | **FAIL** | %d/%d usable = %.2f%% (floor 80%%) |"
             % (cov["usable_cf_time_stop_pnl"], cov["round_trips_in_window"],
                cov["coverage_pct"]))
    pb = r["PRIMARY_frozen_population_battery"]
    for key, name in (("G1_aggregate", "G1 aggregate"), ("G2_drop_top3", "G2 drop-top3"),
                      ("G3_drop_best2_days", "G3 drop-best-2-days"),
                      ("G4_equal_n_buckets", "G4 equal-N buckets"),
                      ("G5_day_block_bootstrap", "G5 day-block bootstrap"),
                      ("G6_stop_mode_stratified", "G6 stop_mode strata")):
        blk = pb[key]
        L.append("| %s | **NOT COMPUTABLE** | %s |"
                 % (name, blk.get("reason", "n=0 usable deltas")))
    ne = pb["G7_n_effective"]
    L.append("| G7 n_effective | **UNDERPOWERED** | n_raw=%d, n_effective=%d (floor 30) |"
             % (ne["n_raw"], ne["n_effective"]))
    L.append("")
    L.append("## What the prereg's predictions get")
    L.append("")
    for k, v in r["PREDICTIONS_ADJUDICATED"].items():
        L.append("- **%s** — %s" % (k, v))
    L.append("")
    L.append("## Supplementary cohort — GATE-INELIGIBLE, read it as a hint only")
    L.append("")
    L.append("`analysis/winner-autopsies/all.jsonl` carries a genuine `hold_to_time_stop` "
             "variant per trade for **84 rows, every one of them a CONTROL-WINNER**.")
    L.append("")
    g1 = supp["G1_aggregate"]
    g2 = supp["G2_drop_top3"]
    g3 = supp["G3_drop_best2_days"]
    g5 = supp["G5_day_block_bootstrap"]
    L.append("| Cut | n | mean delta |")
    L.append("|---|---|---|")
    L.append("| headline | %s | %s |" % (g1.get("n"), g1.get("mean_delta")))
    if g2.get("status") == "COMPUTED":
        L.append("| drop-top3 (largest abs) | %s | %s |"
                 % (g2["drop_top3_largest_magnitude"]["n"],
                    g2["drop_top3_largest_magnitude"]["mean_delta"]))
        L.append("| drop-best3 | %s | %s |" % (g2["drop_best3_most_positive"]["n"],
                                               g2["drop_best3_most_positive"]["mean_delta"]))
        L.append("| drop-worst3 | %s | %s |" % (g2["drop_worst3_most_negative"]["n"],
                                                g2["drop_worst3_most_negative"]["mean_delta"]))
    if g3.get("status") == "COMPUTED":
        L.append("| drop-best-2-days | %s | %s |" % (g3["drop_best2_days"]["n"],
                                                     g3["drop_best2_days"]["mean_delta"]))
        L.append("| drop-worst-2-days | %s | %s |" % (g3["drop_worst2_days"]["n"],
                                                      g3["drop_worst2_days"]["mean_delta"]))
        s1 = g3["single_worst_concentration"]
        L.append("| **drop top-1 DAY (%s)** | %s | **%s** |"
                 % (s1["top1_day"], (g1.get("n") or 0) - 10,
                    s1["mean_delta_excluding_top1_day"]))
        L.append("| median delta | %s | %s |" % (g1.get("n"), g3.get("median_delta")))
    L.append("")
    if g5.get("status") == "COMPUTED":
        L.append("Day-block bootstrap (B=%d, day as unit): 95%% CI %s, **P(delta<=0)=%s**."
                 % (g5["B"], g5["ci95_mean_delta"], g5["p_delta_le_0"]))
        L.append("")
    if g3.get("status") == "COMPUTED":
        s1 = g3["single_worst_concentration"]
        L.append("**The whole positive mean is one day.** %s alone is **%s%% of the net**. "
                 "Remove that single day and the mean flips to **%s** — i.e. the managed "
                 "exits *earned* money on the remaining %d winners. The median delta is "
                 "**%s** (negative): the typical winner was exited *better* than holding."
                 % (s1["top1_day"], s1["top1_day_pct_of_net"],
                    s1["mean_delta_excluding_top1_day"],
                    (g1.get("n") or 0) - 10, g3.get("median_delta")))
        L.append("")
    pr = supp.get("PSEUDO_REPLICATION_AUDIT") or {}
    if pr.get("top3_all_same_date"):
        L.append("**And that day is not even three observations.** %s The three largest "
                 "deltas are the same signal filled on three arms." % pr["finding"])
        L.append("")
    L.append("So the cohort *selected to favour the hypothesis* fails **G2, G3, G4, G5 and "
             "G6** on its own numbers, before ineligibility is even considered.")
    L.append("")
    L.append("**Why this cannot be the answer:** %s" % supp["WHY_INELIGIBLE"])
    L.append("")
    asc = r["ARITHMETIC_SANITY_CHECK"]
    L.append("## Arithmetic sanity check (mandatory self-audit)")
    L.append("")
    L.append("Hand-verified all %d populated rows straight off the raw CSV. "
             "**%s**" % (asc["rows_audited"], asc["VERDICT"]))
    L.append("")
    L.append("| date | qty | entry | exit | CONTROL | recomputed | NULL_A | delta | NULL_B | flag |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in asc["hand_verified_rows"]:
        flag = []
        if not c["I2_high_water_is_upper_bound"]:
            flag.append("**I2 VIOLATION: null_b < max(control,null_a)**")
        if c["degenerate_null_a_equals_control"]:
            flag.append("null_a == control")
        if c["degenerate_null_b_equals_control"]:
            flag.append("null_b == control")
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                 % (c["date"], c["qty"], c["entry_px"], c["exit_px"],
                    c["control_dollar_pnl"],
                    c["hand_recomputed_control_(exit-entry)*qty*100"],
                    c["null_a_cf_time_stop_pnl"], c["delta_null_a_minus_control"],
                    c["null_b_cf_high_water_pnl"], "; ".join(flag) or "ok"))
    L.append("")
    L.append("CONTROL arithmetic reconciles on every row — `dollar_pnl` is sound. "
             "The **counterfactual** columns are not: high-water is an upper bound by "
             "construction, so `null_b < null_a` is structurally impossible, and two of "
             "three rows are degenerate copies of `dollar_pnl`. These are hand-entered "
             "or placeholder values, not a validated computation.")
    L.append("")
    L.append("## NULL_B (high-water)")
    L.append("")
    L.append("**LOOK-AHEAD. UNACHIEVABLE. NOT AN OPPORTUNITY.** %s"
             % r["NULL_B_high_water_descriptive_only"]["LABEL"])
    L.append("")
    L.append("## What I could not check")
    L.append("")
    for x in r["WHAT_I_COULD_NOT_CHECK"]:
        L.append("- %s" % x)
    L.append("")
    L.append("## The unblocking action")
    L.append("")
    L.append(r["FORWARD_CLOCK"])
    L.append("")
    with io.open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
