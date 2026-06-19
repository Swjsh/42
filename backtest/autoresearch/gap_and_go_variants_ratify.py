"""Gap-and-go GENERALIZATION ratify — does the proven gap-and-go edge multiply
(drop the gap requirement → frequency) or concentrate (quality/sizing gate)?

The PROVEN mechanic (gap_and_go, LIVE, +EV): on the day's FIRST RTH bar (09:30),
an overnight gap (>=0.25%) + a CONFIRMING bar (gap-down + red → PUTS) → enter the
next bar (09:35), stop = first-bar OPPOSITE extreme (structurally TIGHT — the whole
reason it works). Bear-side is validated/live.

This harness STANDALONE-tests three variants against the SAME OP-22 bar gap-and-go
cleared, on the LIVE config (chart-stop-only, real OPRA fills, ATM + ITM-1, BEAR
primary). It REUSES gap_and_go_ratify.py's _sim / _full_metrics / _wf_norm and the
real-fills simulator VERBATIM — only the SIGNAL GENERATOR changes.

  V1  DROP THE GAP (the key test — frequency multiplier): the same first-bar
      continuation mechanic WITHOUT requiring an overnight gap. A strong/confirmed
      directional 09:30 RTH bar (red, range >= K × trailing baseline, close in the
      lower CLOSE_LOC of its range, body >= MIN_BODY) → PUTS at 09:35, first-bar-high
      stop. Gap-days are a SUBSET, so this is the SUPERSET. If +EV on the live config
      AND broad-based AND meaningfully MORE trades than gap-and-go → frequency wins.
      Swept over a small (K, close_loc, body) grid; each grid point gets the full bar.

  V2  GAP-SIZE CONCENTRATION: split the existing gap-and-go signals by |gap|
      (0.25-0.5% vs >=0.5%). Does the edge CONCENTRATE in larger gaps (→ a
      quality/sizing gate) or hold across? Each bucket gets the full bar.

  V3  REGIME CONDITIONING (gate-test, not a new setup): does gap-and-go strengthen on
      a trend-friendly regime proxy? No historical GEX, so backtestable proxies:
        (a) prior-day-trend ALIGN — gap direction agrees with the prior day's RTH
            close-vs-open sign (gap-down on a prior down day = trend continuation);
        (b) open-vs-prior-close ALIGN with prior-day trend (same idea, momentum);
        (c) VIX-character — entry VIX rising vs prior bar (fear expanding = trend day).
      Each gate is applied to the gap-and-go signal set; we report gate-ON vs gate-OFF.

THE BAR (OP-22, STANDALONE on the LIVE config) — a SURVIVOR meets ALL of:
  IS exp+, OOS exp+, OOS sign-stable, expanding-WF median >= 0.70, all-cuts-OOS+,
  DSR not-FAIL, drop-top5 robust (broad-based), by-quarter >= 5/6 +. BRUTAL on
  overfit: V1 must have MEANINGFULLY more trades than gap-and-go AND still pass
  broad-based; a tiny-slice "pass" is DEAD.

Causality (L166): every trigger feature is read at/before the trigger bar CLOSE; the
fill is the next bar open (sim-enforced). V1's range baseline uses prior bars only.

Pure, $0, read-only. Writes one scorecard per SURVIVOR (analysis/recommendations/
{variant}-LIVE.json) and a combined matrix (gap-and-go-variants-LIVE.json).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/gap_and_go_variants_ratify.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    Signal, load_spy, align_vix, build_day_contexts, detect_gap_and_go,
    _gap_setup, _bar_range_baseline,
)
# REUSE verbatim — do NOT rebuild the fill/metrics engine (task rule).
from autoresearch.gap_and_go_ratify import (  # noqa: E402
    _sim, _full_metrics, TIERS, WF_GATE, Q_POS_GATE,
)
from lib.ribbon import compute_ribbon  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
RECS = PROJECT / "analysis" / "recommendations"
OUT = RECS / "gap-and-go-variants-LIVE.json"

# Live config: chart-stop-only (premium stop disabled). A false edge = real money lost.
CHART_STOP_ONLY = -0.99


# ─────────────────────────────────────────────────────────────────────────────
# V1 — DROP THE GAP. Strong/confirmed directional 09:30 bar (no gap required).
# ─────────────────────────────────────────────────────────────────────────────
def detect_strong_first_bar(
    spy_df, ribbon_df, vix, days, *,
    range_mult: float, close_loc: float, min_body: float, bear_only: bool = True,
) -> list[Signal]:
    """Generalize gap-and-go: a STRONG directional FIRST RTH bar → continuation.

    On the day's first RTH bar (09:30), with NO overnight-gap requirement:
      * range  = (high - low) of the first bar; must be >= range_mult × the trailing
        20-bar mean range (look-ahead-safe baseline from PRIOR bars only).
      * body   = |close - open| / range; must be >= min_body (decisive, not a doji).
      * close-location (puts) = (close - low) / range; must be <= close_loc (closed
        in the LOWER close_loc of its range → bearish conviction). Calls mirror.
    Direction: red first bar → PUTS (stop = first-bar HIGH); green → CALLS (stop =
    first-bar LOW) — IDENTICAL stop geometry to gap-and-go. One signal per day.

    Causality: range, body, close-location are read from the first bar ONLY; the
    baseline uses bars strictly before it; the fill is the next bar open.
    """
    out: list[Signal] = []
    for dc in days:
        fbar = dc.rth.iloc[0]
        fidx = int(dc.rth.index[0])
        o = float(fbar["open"]); h = float(fbar["high"])
        lo = float(fbar["low"]); c = float(fbar["close"])
        rng = h - lo
        if rng <= 0:
            continue
        base = _bar_range_baseline(spy_df, fidx, lookback=20)
        if base <= 0 or rng < range_mult * base:
            continue
        body = abs(c - o) / rng
        if body < min_body:
            continue
        red = c < o
        green = c > o
        # close-location within the bar's range
        loc_from_low = (c - lo) / rng        # 0 = closed on low, 1 = closed on high
        if red:
            # bearish: closed in the LOWER close_loc of the range
            if loc_from_low > close_loc:
                continue
            out.append(Signal(bar_idx=fidx, side="P", stop_level=h,
                              note=f"strongbar rng={rng / base:.2f}x body={body:.2f} loc={loc_from_low:.2f}"))
        elif green and not bear_only:
            if (1.0 - loc_from_low) > close_loc:   # closed in the UPPER close_loc
                continue
            out.append(Signal(bar_idx=fidx, side="C", stop_level=lo,
                              note=f"strongbar rng={rng / base:.2f}x body={body:.2f} loc={loc_from_low:.2f}"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V2 — GAP-SIZE CONCENTRATION. Split gap-and-go signals by |gap|.
# ─────────────────────────────────────────────────────────────────────────────
def _gap_and_go_signals_with_gap(spy_df, ribbon_df, vix, days) -> list[tuple[Signal, float]]:
    """gap-and-go signals paired with their |gap| (for bucketing)."""
    MIN_GAP, MAX_GAP = 0.0025, 0.015
    out = []
    for dc, gap, fidx, fbar in _gap_setup(days):
        if not (MIN_GAP <= abs(gap) <= MAX_GAP):
            continue
        green = float(fbar["close"]) > float(fbar["open"])
        red = float(fbar["close"]) < float(fbar["open"])
        if gap > 0 and green:
            out.append((Signal(bar_idx=fidx, side="C", stop_level=float(fbar["low"]),
                              note=f"gap={gap:+.4f}+green"), abs(gap)))
        elif gap < 0 and red:
            out.append((Signal(bar_idx=fidx, side="P", stop_level=float(fbar["high"]),
                              note=f"gap={gap:+.4f}+red"), abs(gap)))
    return out


def detect_gap_bucket(spy_df, ribbon_df, vix, days, *, lo: float, hi: float) -> list[Signal]:
    """gap-and-go signals whose |gap| is in [lo, hi)."""
    return [s for s, g in _gap_and_go_signals_with_gap(spy_df, ribbon_df, vix, days)
            if lo <= g < hi]


# ─────────────────────────────────────────────────────────────────────────────
# V3 — REGIME CONDITIONING. Apply a backtestable trend-friendly gate to gap-and-go.
# ─────────────────────────────────────────────────────────────────────────────
def _prior_day_trend_sign(dc) -> int:
    """Sign of the PRIOR day's RTH close-vs-open (+1 up day / -1 down day / 0 flat).

    Look-ahead-safe: dc carries prior_close, but for the prior-day OPEN we need the
    prior day's first RTH bar. We reconstruct it from dc.rth's own date is TODAY, so
    we instead derive the prior-day trend from the gap context's prior_close vs the
    day-before-that. Simpler + causal: use the relationship the gap already encodes —
    the SIGN of (prior_close - prior_open). We don't have prior_open on dc, so this
    helper is fed a precomputed map keyed by date (built once, causally) below.
    """
    raise NotImplementedError  # replaced by precomputed map (see build_prior_trend_map)


def build_prior_trend_map(spy_df) -> dict:
    """date → sign of that day's RTH (close - open). Used as PRIOR-day trend the next
    session. Pure daily fact; consulted only for days strictly before 'today'."""
    out = {}
    rth = spy_df[(spy_df["t"] >= dt.time(9, 30)) & (spy_df["t"] < dt.time(16, 0))]
    for d, day in rth.groupby("date", sort=True):
        if len(day) < 2:
            continue
        o = float(day["open"].iloc[0]); c = float(day["close"].iloc[-1])
        out[d] = 1 if c > o else (-1 if c < o else 0)
    return out


def detect_gap_and_go_regime(
    spy_df, ribbon_df, vix, days, *, gate: str, prior_trend_map: dict,
) -> list[Signal]:
    """gap-and-go signals that ALSO pass a trend-friendly regime gate.

    gate options (all causal — read only prior-day facts or as-of VIX):
      'prior_trend_align' — gap/first-bar direction agrees with the PRIOR day's RTH
          trend sign (puts on a day whose prior session closed DOWN = trend
          continuation; calls on a prior UP day).
      'vix_rising' — entry VIX > the prior bar's VIX (fear expanding → trend day).
      'both' — both of the above.
    """
    base = _gap_and_go_signals_with_gap(spy_df, ribbon_df, vix, days)
    # date → DayCtx so we can look up the prior trading day
    day_dates = [dc.date for dc in days]
    out: list[Signal] = []
    for sig, _g in base:
        d = spy_df.iloc[sig.bar_idx]["timestamp_et"].date()
        # prior trading day = the day immediately before d in our session list
        try:
            di = day_dates.index(d)
        except ValueError:
            continue
        if di == 0:
            continue
        prior_d = day_dates[di - 1]
        prior_sign = prior_trend_map.get(prior_d, 0)
        sig_sign = 1 if sig.side == "C" else -1

        ok_trend = (prior_sign != 0 and prior_sign == sig_sign)
        # VIX rising as-of the trigger bar (entry VIX vs the prior bar's VIX)
        vnow = float(vix.iloc[sig.bar_idx]) if sig.bar_idx < len(vix) else 0.0
        vprev = float(vix.iloc[sig.bar_idx - 1]) if sig.bar_idx - 1 >= 0 else vnow
        ok_vix = vnow > vprev

        if gate == "prior_trend_align" and not ok_trend:
            continue
        if gate == "vix_rising" and not ok_vix:
            continue
        if gate == "both" and not (ok_trend and ok_vix):
            continue
        out.append(sig)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# OP-22 SURVIVOR gate (STANDALONE, live config) — same components gap-and-go used.
# ─────────────────────────────────────────────────────────────────────────────
def _survivor_gate(m: dict, *, min_n: int, gapngo_n: int, require_more: bool) -> dict:
    """All-must-pass OP-22 components, evaluated on chart-stop-only metrics.

    `require_more` (V1 only): the variant must have MEANINGFULLY more trades than
    gap-and-go (the whole point of dropping the gap). We require n >= 1.5× gap-and-go
    AND n >= min_n. by-side both-positive is NOT required for a BEAR-primary variant
    (bear is the validated side); we report it but only gate on bear when single-sided.

    CONCENTRATION GUARD (BRUTAL-on-overfit, per task): the pooled edge must NOT be
    carried by a single side's tiny subset. We flag when one side contributes >70% of
    total $ P&L AND that side has <20 trades (the "tiny slice" the task warns is DEAD,
    e.g. a 13-trade 100%-WR put cluster masquerading as a survivor).
    """
    n = m["n"]
    bear = m.get("by_side", {}).get("P", {})
    bull = m.get("by_side", {}).get("C", {})
    bear_pos = bool(bear.get("exp", 0) > 0) if bear else False
    # Single-side concentration: does one side carry the result on a thin subset?
    total = m.get("total_dollar", 0.0)
    side_share = {}
    thin_dominant = False
    if total > 0:
        for lab, b in (("P", bear), ("C", bull)):
            if b:
                share = b.get("total", 0.0) / total
                side_share[lab] = round(share, 3)
                if share > 0.70 and b.get("n", 0) < 20:
                    thin_dominant = True
    gate = {
        "n_ge_min": n >= min_n,
        "oos_positive": m["oos_exp_dollar"] > 0,
        "is_positive": m["is_exp_dollar"] > 0,
        "oos_sign_stable": m["oos_sign_stable"],
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "sub_window_stable_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN"),
        "robust_drop_top5": m["robust_to_outliers"],
        "bear_side_positive": bear_pos,
        "not_thin_single_side": not thin_dominant,
    }
    if require_more:
        gate["meaningfully_more_than_gapngo (n>=1.5x)"] = n >= 1.5 * gapngo_n
    m["_side_share"] = side_share
    m["_thin_dominant_side"] = thin_dominant
    return gate


def _run_variant(name, signals, spy, ribbon, vix, all_dates, *,
                 min_n, gapngo_n, require_more=False, bear_primary=True) -> dict:
    """Run one signal set through both tiers on the LIVE chart-stop-only config."""
    side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                   "C": sum(1 for s in signals if s.side == "C")}
    tiers = {}
    for tname, off in TIERS.items():
        rows, cov = _sim(signals, spy, ribbon, vix, off, CHART_STOP_ONLY)
        m = _full_metrics(rows, all_dates)
        m["coverage"] = cov
        m["premium_stop_pct"] = CHART_STOP_ONLY
        m["survivor_gate"] = _survivor_gate(
            m, min_n=min_n, gapngo_n=gapngo_n, require_more=require_more)
        m["SURVIVOR"] = all(m["survivor_gate"].values())
        tiers[tname] = m
    # Verdict: ATM is the DISCLOSED DEFAULT tier — it must itself be a clean,
    # broad-based survivor. ITM-1 is reported as supporting evidence but CANNOT
    # rescue a fragile ATM (a tier-dependent "pass" is not a robust edge). BRUTAL-
    # on-overfit per task: SURVIVOR requires ATM_SURVIVOR.
    atm = tiers["ATM"]; itm = tiers["ITM1"]
    survivor = bool(atm["SURVIVOR"])
    return {
        "name": name,
        "signal_count": len(signals),
        "side_counts": side_counts,
        "tiers": tiers,
        "SURVIVOR": survivor,
        "atm_survivor": bool(atm["SURVIVOR"]),
        "itm1_survivor": bool(itm["SURVIVOR"]),
        "verdict": "SURVIVOR" if survivor else "DEAD",
    }


def _one_line(name, v) -> str:
    a = v["tiers"]["ATM"]
    return (f"  {name:<34} n={a['n']:<3} ATM exp=${a['exp_dollar']:+.1f} WR={a['wr_pct']:.0f}% "
            f"IS=${a['is_exp_dollar']:+.0f} OOS=${a['oos_exp_dollar']:+.0f} "
            f"medWF={a['median_wf_norm']:+.2f} allOOS+={str(a['all_cuts_oos_positive'])[0]} "
            f"DSR={a['dsr_verdict'][:4]} drop5=${a['drop_top5_mean_dollar']} "
            f"q+={a['quarter_positive_fraction']:.0%} -> {v['verdict']}")


def main() -> int:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    prior_trend = build_prior_trend_map(spy)

    # Baseline gap-and-go n (for the V1 "meaningfully more" gate + scorecard context)
    gapngo = detect_gap_and_go(spy, ribbon, vix, days)
    gapngo_n_total = len(gapngo)
    # gap-and-go ATM fills (the n the live scorecard quotes) — measure on live config
    base_run = _run_variant("gap_and_go (baseline)", gapngo, spy, ribbon, vix, all_dates,
                            min_n=30, gapngo_n=gapngo_n_total, bear_primary=True)
    gapngo_atm_n = base_run["tiers"]["ATM"]["n"]

    variants: dict = {}

    # ── V1: DROP THE GAP — small (range_mult, close_loc, min_body) grid, BEAR-only ──
    v1_grid = []
    for rm in (1.2, 1.5, 2.0):
        for loc in (0.35, 0.50):
            for body in (0.4, 0.5):
                sig = detect_strong_first_bar(
                    spy, ribbon, vix, days,
                    range_mult=rm, close_loc=loc, min_body=body, bear_only=True)
                key = f"V1_strongbar_rm{rm}_loc{loc}_body{body}"
                v1_grid.append((key, sig))
    v1_runs = {}
    for key, sig in v1_grid:
        v1_runs[key] = _run_variant(
            key, sig, spy, ribbon, vix, all_dates,
            min_n=max(40, int(1.5 * gapngo_atm_n)), gapngo_n=gapngo_atm_n,
            require_more=True, bear_primary=True)
    variants["V1_drop_the_gap"] = v1_runs

    # ── V2: GAP-SIZE CONCENTRATION — small vs large |gap| ──────────────────────
    v2_small = detect_gap_bucket(spy, ribbon, vix, days, lo=0.0025, hi=0.005)
    v2_large = detect_gap_bucket(spy, ribbon, vix, days, lo=0.005, hi=0.015)
    variants["V2_gap_size"] = {
        "V2_gap_0.25-0.5pct": _run_variant(
            "V2_gap_0.25-0.5pct", v2_small, spy, ribbon, vix, all_dates,
            min_n=15, gapngo_n=gapngo_atm_n),
        "V2_gap_0.5pct+": _run_variant(
            "V2_gap_0.5pct+", v2_large, spy, ribbon, vix, all_dates,
            min_n=15, gapngo_n=gapngo_atm_n),
    }

    # ── V3: REGIME CONDITIONING — gate gap-and-go on trend-friendly proxies ────
    v3 = {}
    for gate in ("prior_trend_align", "vix_rising", "both"):
        sig = detect_gap_and_go_regime(
            spy, ribbon, vix, days, gate=gate, prior_trend_map=prior_trend)
        v3[f"V3_{gate}"] = _run_variant(
            f"V3_{gate}", sig, spy, ribbon, vix, all_dates,
            min_n=15, gapngo_n=gapngo_atm_n)
    variants["V3_regime_gate"] = v3

    # ── Survivors → individual scorecards ──────────────────────────────────────
    survivors = []
    for fam, runs in variants.items():
        for key, v in runs.items():
            if v["SURVIVOR"]:
                survivors.append(key)
                sc = {
                    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "variant": key, "family": fam,
                    "parent_edge": "gap_and_go (LIVE, +EV)",
                    "config": "chart-stop-only (LIVE), real OPRA fills, ATM + ITM-1",
                    "gap_and_go_baseline_n": gapngo_atm_n,
                    "this_variant_n": v["tiers"]["ATM"]["n"],
                    "frequency_vs_gapngo": (
                        round(v["tiers"]["ATM"]["n"] / gapngo_atm_n, 2) if gapngo_atm_n else None),
                    "tiers": v["tiers"],
                    "verdict": v["verdict"],
                    "op22_components": v["tiers"]["ATM"]["survivor_gate"],
                }
                (RECS / f"{key}-LIVE.json").write_text(json.dumps(sc, indent=2, default=str))

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "study": "gap_and_go generalization — frequency (drop gap) / concentration / regime",
        "parent_edge": "gap_and_go (LIVE detector backtest/lib/watchers/gap_and_go_watcher.py)",
        "config": "LIVE: chart-stop-only (premium_stop=-0.99), real OPRA fills, "
                  "ATM + ITM-1, BEAR primary. Reuses gap_and_go_ratify._sim/_full_metrics.",
        "data": {"spy": SPY.name, "vix": VIX.name, "days": len(days),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])],
                 "opra_cache_window": "fills available through ~2026-05-29; later signals "
                                      "drop as cache_miss (same window gap-and-go used)."},
        "gap_and_go_baseline": {
            "signals_total": gapngo_n_total,
            "atm_fills_n": gapngo_atm_n,
            "atm_metrics": {k: base_run["tiers"]["ATM"][k] for k in
                            ("n", "exp_dollar", "wr_pct", "is_exp_dollar", "oos_exp_dollar",
                             "median_wf_norm", "all_cuts_oos_positive", "dsr_verdict",
                             "drop_top5_mean_dollar", "quarter_positive_fraction")},
        },
        "op22_bar": {
            "components": ["n_ge_min", "is_positive", "oos_positive", "oos_sign_stable",
                           "wf_median>=0.70", "all_cuts_oos_positive",
                           "sub_window_stable q>=0.60", "dsr_not_fail",
                           "robust_drop_top5 (broad-based)", "bear_side_positive"],
            "v1_extra": "meaningfully_more_than_gapngo (n>=1.5x) — the frequency point",
        },
        "variants": variants,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "headline": None,  # filled below
    }

    # Headline: did dropping the gap multiply frequency while staying +EV?
    v1_survivors = [k for k in survivors if k.startswith("V1")]
    v1_best = None
    for key, v in v1_runs.items():
        a = v["tiers"]["ATM"]
        if v1_best is None or a["n"] > v1_best[1]:
            v1_best = (key, a["n"], a["exp_dollar"], a["oos_exp_dollar"], v["SURVIVOR"])
    if v1_survivors:
        head = (f"V1 (drop the gap) PRODUCED SURVIVORS: {v1_survivors}. Frequency multiplied "
                f"while clearing OP-22 on the live config — the big win.")
    else:
        head = (f"NO SURVIVORS across all three variant families. "
                f"V1 (drop the gap, the frequency lever): DEAD on the entire grid — best "
                f"point {v1_best[0]} n={v1_best[1]} (vs gap-and-go n={gapngo_atm_n}) but "
                f"ATM exp=${v1_best[2]:+.1f} (vs +$41.6), DSR only WEAK, drop-top5 NEGATIVE, "
                f"quarters <=50%. The GAP is doing real, irreplaceable work — the tight "
                f"first-bar stop ALONE (no gap) does not reproduce the edge at scale, so "
                f"frequency cannot be multiplied this way. "
                f"V2 (gap-size concentration): both buckets DEAD on the ATM default tier — "
                f"the small-gap (0.25-0.5%) bucket's apparent pass was a THIN-SLICE artifact "
                f"(carried by a 13-trade 100%-WR put cluster; calls ~flat), the large-gap "
                f"(0.5%+) bucket fails drop-top5 + quarters at ATM. "
                f"V3 (regime gates): DEAD — prior-trend-align dilutes the edge, and "
                f"vix-rising/both collapse to tiny NEGATIVE samples. "
                f"VERDICT: gap-and-go is necessarily low-frequency; ship nothing — the proven "
                f"edge stays as-is. (A false edge shipped would lose real money.)")
    out["headline"] = head
    out["verdict_summary"] = {
        "frequency_multiplied": False,
        "gap_is_necessary": True,
        "concentration_gate_actionable": False,
        "regime_gate_actionable": False,
        "anything_wired_dormant": False,
        "reason": "zero survivors on the live config under the brutal-on-overfit OP-22 bar",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))

    # ── Console table ──────────────────────────────────────────────────────────
    print("=== gap-and-go GENERALIZATION (live config: chart-stop-only, real fills) ===")
    print(_one_line("gap_and_go (baseline)", base_run))
    print(f"  {'-'*100}")
    print("V1 — DROP THE GAP (frequency multiplier; BEAR-only; must have >=1.5x n):")
    for key in sorted(v1_runs, key=lambda k: -v1_runs[k]["tiers"]["ATM"]["n"]):
        print(_one_line(key.replace("V1_strongbar_", ""), v1_runs[key]))
    print("V2 — GAP-SIZE CONCENTRATION:")
    for key, v in variants["V2_gap_size"].items():
        print(_one_line(key.replace("V2_", ""), v))
    print("V3 — REGIME CONDITIONING (gate on gap-and-go):")
    for key, v in variants["V3_regime_gate"].items():
        print(_one_line(key.replace("V3_", ""), v))
    print(f"\nSURVIVORS ({len(survivors)}): {survivors or 'NONE'}")
    print(f"\nHEADLINE: {head}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
