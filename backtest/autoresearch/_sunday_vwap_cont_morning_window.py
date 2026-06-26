"""SUNDAY WEB-LEARN — vwap_cont_morning_window_outperforms_midday.

Hypothesis (web-sourced): vwap_continuation entries in the morning realized-move-rich
window (09:35-11:00 ET) have MATERIALLY higher per-trade expectancy (return on premium)
than entries 11:00-14:00 ET, because intraday realized variance is U-shaped (highest in
the first hour, collapsing ~38% into the 12:00-13:00 'silent hour'), so a LONG-premium
0DTE directional buyer entered midday rarely gets the move needed to overcome benign theta.

This is an IMPROVES-EXISTING-EDGE test on edge #1 (vwap_continuation, LIVE). It does NOT
introduce a new entry signal — it restricts the live detector's entry_window. So the bar
is: expectancy LIFT vs the current continuous baseline AND OOS-positive AND keep n>=20.

METHOD (anti-overfit, reuse-not-reinvent):
  * Detector + sim + OP-22 scorecard are IMPORTED verbatim from j_entry_specificity.py
    (detect_j_cont_param / _sim / _full_metrics / _ship_gate) — the same parameterized
    clone of detect_j_vwap_continuation through the same _full_metrics stack.
  * HARD-WINDOW <=2026-05-29 (C1 / L171): SPY bars are sliced to the OPRA real-fill cache
    horizon BEFORE day-contexts are built, and ASSERTED, so OOS split / n-counts /
    freq are computed on the same population that actually fills (post-cache signals would
    silently drop as cache_miss and pollute the denominators).
  * The three buckets the hypothesis names, ATM tier (live = ITM/ATM + tight stop):
       MORNING   (09:35, 11:00)   <- the realized-move-rich window
       MIDDAY    (11:00, 14:00)   <- the 'silent hour' band
       BASELINE  (09:35, 15:00)   <- current continuous live entry_window
  * Headline = per-trade expectancy (return on premium = exp_pct + exp_dollar) +
    drop-top5 + OOS-positive, with trade-count / frequency cost reported. n>=20 per bucket
    is REQUIRED to read a bucket (else "n<20, not testable").

Causal (L166): all features at/before entry-bar close; fill next-bar-open (sim).
Real fills (lib.simulator_real). Pure, $0, read-only, propose-only (Rule 9). NO live edits.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_sunday_vwap_cont_morning_window.py
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
    load_spy, align_vix, build_day_contexts,
)
from lib.ribbon import compute_ribbon  # noqa: E402
# Reuse the PROVEN detector + sim + scorecard verbatim (no re-implementation).
from autoresearch.j_entry_specificity import (  # noqa: E402
    detect_j_cont_param, _sim, _full_metrics, _ship_gate,
    FREQ_PER_WK_FLOOR,
)

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "sunday-vwap-cont-morning-window.json"

# HARD-WINDOW: OPRA real-fill cache horizon (C1 / L171). Slice + ASSERT.
CACHE_END = dt.date(2026, 5, 29)

# The three buckets the hypothesis names. (label, start, end_exclusive)
BUCKETS = [
    ("BASELINE_0935_1500", dt.time(9, 35), dt.time(15, 0)),
    ("MORNING_0935_1100", dt.time(9, 35), dt.time(11, 0)),
    ("MIDDAY_1100_1400", dt.time(11, 0), dt.time(14, 0)),
]
MIN_N = 20  # keep n>=20 per bucket (ENV bar) — else the bucket is not readable.


def run_bucket(label, win_start, win_end, spy, vix, ribbon, days, all_dates, n_days,
               n_trials_dsr):
    signals = detect_j_cont_param(spy, ribbon, vix, days,
                                  win_start=win_start, win_end=win_end,
                                  side_filter="both", breakout_only=False)
    side_counts = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
    # ATM tier = offset 0 (live config is ITM/ATM; ATM is the apples-to-apples headline).
    rows, cov = _sim(signals, spy, vix, ribbon, 0)
    m = _full_metrics(rows, all_dates, n_days, n_trials_dsr)
    m["coverage"] = cov
    gate, ok = _ship_gate(m)
    m["ship_gate"] = gate
    m["edge_ship_pass"] = ok
    m["freq_pass_>=2/wk"] = m["trades_per_week"] >= FREQ_PER_WK_FLOOR
    m["DAILY_SURVIVOR"] = bool(ok and m["freq_pass_>=2/wk"])
    m["n_ge_20"] = m["n"] >= MIN_N
    return {"label": label, "window": [str(win_start), str(win_end)],
            "signal_count": len(signals), "side_counts": side_counts, "metrics": m}


def main() -> int:
    print("=== SUNDAY: vwap_cont morning(09:35-11:00) vs midday(11:00-14:00) ===")
    print(f"HARD-WINDOW assert: SPY sliced to <= {CACHE_END} (OPRA cache horizon, C1).")

    spy = load_spy(str(SPY))
    raw_max = spy["date"].max()
    spy = spy[spy["date"] <= CACHE_END].reset_index(drop=True)
    assert spy["date"].max() <= CACHE_END, "HARD-WINDOW slice failed"
    assert len(spy) > 0, "empty after HARD-WINDOW slice"
    print(f"  raw spy max date={raw_max} -> sliced max={spy['date'].max()} "
          f"({len(spy)} bars)")

    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)
    assert all_dates[-1] <= CACHE_END, "day-context leaked past cache horizon"
    print(f"  trading_days={n_days} range {all_dates[0]}..{all_dates[-1]}")

    n_trials = 3  # 3 windows, single tier — conservative DSR haircut for THIS test
    buckets = []
    for label, ws, we in BUCKETS:
        b = run_bucket(label, ws, we, spy, vix, ribbon, days, all_dates, n_days, n_trials)
        buckets.append(b)

    by_label = {b["label"]: b for b in buckets}
    base = by_label["BASELINE_0935_1500"]["metrics"]
    morn = by_label["MORNING_0935_1100"]["metrics"]
    mid = by_label["MIDDAY_1100_1400"]["metrics"]

    # Headline contrasts (size-neutral pct + dollar). Positive = morning richer.
    morn_vs_mid_pct = round(morn["exp_pct_return"] - mid["exp_pct_return"], 5)
    morn_vs_mid_dollar = round(morn["exp_dollar"] - mid["exp_dollar"], 2)
    morn_vs_base_oos = round(morn["oos_exp_dollar"] - base["oos_exp_dollar"], 2)

    # ---- VERDICT ----
    # The HYPOTHESIS is "morning expectancy materially > midday". The SHIP question for
    # the LIVE edge is "does restricting to morning LIFT OOS expectancy vs the continuous
    # baseline AND keep n>=20 AND survive the OP-22 gate?".
    morning_richer = bool(morn["exp_pct_return"] > mid["exp_pct_return"]
                          and morn["exp_dollar"] > mid["exp_dollar"])
    n_ok = bool(morn["n"] >= MIN_N and mid["n"] >= MIN_N)

    if not n_ok:
        verdict = "DEAD"
        reason = (f"Insufficient real fills to test honestly within the HARD-WINDOW: "
                  f"morning n={morn['n']}, midday n={mid['n']} (need >={MIN_N} per bucket). "
                  f"vwap_continuation is a once-per-day MORNING-trend-established detector, "
                  f"so the midday bucket is structurally starved (the trend side is set in "
                  f"the first 3 bars and the one-per-day entry usually fires before 11:00). "
                  f"Cannot validate or refute the realized-variance claim on OUR data.")
    elif (morning_richer and morn["DAILY_SURVIVOR"] and morn_vs_base_oos > 0):
        verdict = "LIVE_EDGE_IMPROVEMENT"
        reason = (f"Morning entries are richer (exp_pct {morn['exp_pct_return']:+.4f} vs "
                  f"{mid['exp_pct_return']:+.4f}) AND restricting to morning LIFTS OOS "
                  f"expectancy by ${morn_vs_base_oos:+.1f} vs the continuous baseline AND "
                  f"clears the OP-22 gate at n={morn['n']}.")
    elif morning_richer and morn_vs_base_oos > 0:
        verdict = "LEAD"
        reason = (f"Directionally confirms the hypothesis (morning richer than midday, OOS "
                  f"lift ${morn_vs_base_oos:+.1f} vs baseline) but the morning-restricted "
                  f"variant FAILS a strict OP-22 gate: {by_label['MORNING_0935_1100']['metrics']['ship_gate']}.")
    else:
        verdict = "DEAD"
        reason = (f"Hypothesis NOT supported on OUR real fills: morning exp_pct "
                  f"{morn['exp_pct_return']:+.4f} vs midday {mid['exp_pct_return']:+.4f}, "
                  f"morning-vs-baseline OOS lift ${morn_vs_base_oos:+.1f}. The realized-"
                  f"variance U-shape does not translate into a per-CONTRACT 0DTE option "
                  f"expectancy edge for this detector (C3/L58: a SPY-price/variance regularity "
                  f"!= an option edge once theta+delta+stop-misfire are paid).")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "slug": "vwap_cont_morning_window_outperforms_midday",
        "kind": "improves existing edge #1 (vwap_continuation, LIVE)",
        "hypothesis": (
            "vwap_continuation entries 09:35-11:00 ET have materially higher per-trade "
            "expectancy (return on premium) than 11:00-14:00 ET because intraday realized "
            "variance is U-shaped (peaks first hour, ~38% lower in the 12-13:00 silent hour), "
            "so a long-premium 0DTE buyer entered midday rarely earns the move to beat theta."),
        "web_sources": [
            "Intraday volatility U-shape / smile (high at open & close, trough midday) — "
            "Wood, McInish & Ord (1985) JoF; Harris (1986) JFE; Andersen & Bollerslev (1997) "
            "'Intraday periodicity and volatility persistence in financial markets' (J. Emp. "
            "Finance) — realized vol bottoms ~12:00-13:00 ET ('lunch lull').",
            "CBOE / practitioner notes on the 0DTE 'theta cliff': intraday theta decay of a "
            "same-day SPX/SPY option accelerates into the afternoon, so a midday long-premium "
            "buyer needs a larger realized move to break even.",
        ],
        "method": (
            "Detector + sim + OP-22 scorecard imported VERBATIM from j_entry_specificity.py "
            "(detect_j_cont_param / _sim / _full_metrics / _ship_gate). HARD-WINDOW <=2026-05-29 "
            "(SPY sliced + asserted BEFORE day-contexts). ATM tier, both sides, real OPRA fills. "
            "Three buckets compared on per-trade expectancy + OOS + drop-top5, n>=20 required."),
        "hard_window": str(CACHE_END),
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": n_days,
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "bar_applied": (
            "IMPROVES-EXISTING-EDGE bar: per-trade expectancy LIFT vs continuous baseline "
            "AND OOS-positive AND keep n>=20 (NOT the full 11-gate new-signal bar, since this "
            "only restricts the live detector's entry_window — no new signal introduced)."),
        "buckets": buckets,
        "contrasts": {
            "morning_minus_midday_exp_pct_return": morn_vs_mid_pct,
            "morning_minus_midday_exp_dollar": morn_vs_mid_dollar,
            "morning_minus_baseline_oos_exp_dollar": morn_vs_base_oos,
            "morning_n": morn["n"], "midday_n": mid["n"], "baseline_n": base["n"],
            "morning_exp_pct": morn["exp_pct_return"], "midday_exp_pct": mid["exp_pct_return"],
            "baseline_exp_pct": base["exp_pct_return"],
        },
        "VERDICT": verdict,
        "verdict_reason": reason,
        "caveats": [
            "vwap_continuation is a ONCE-PER-DAY, morning-trend-established continuation "
            "detector (trend side fixed by first 3 RTH bars; one entry per day). It is NOT a "
            "free intraday entry generator, so the midday bucket is structurally starved and "
            "this test cannot fully isolate the realized-variance claim from detector shape.",
            "Proxy strikes (L58): nearest-cached strike used; OPRA cache ends ~2026-05-29 "
            "(enforced via HARD-WINDOW slice, not just cache_miss drops).",
            "ATM tier headline; live config is ITM/ATM + tight stop. Propose-only (Rule 9). "
            "NO live edits performed (Sunday, markets closed).",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print("\n=== BUCKETS (ATM tier, real fills, HARD-WINDOWed) ===")
    for b in buckets:
        m = b["metrics"]
        print(f"[{b['label']}] sig={b['signal_count']} (C={b['side_counts']['C']} "
              f"P={b['side_counts']['P']}) n={m['n']} (>=20:{m['n_ge_20']}) "
              f"exp=${m['exp_dollar']:+.1f} expPCT={m['exp_pct_return']:+.4f} "
              f"WR={m['wr_pct']}% | {m['trades_per_week']}/wk "
              f"| OOSexp=${m['oos_exp_dollar']:+.1f} stable={m['oos_sign_stable']} "
              f"medWF={m['median_wf_norm']:+.3f} allOOS+={m['all_cuts_oos_positive']} "
              f"q+={m['quarter_positive_fraction']:.0%} DSR={m['dsr_verdict']} "
              f"drop5=${m['drop_top5_mean_dollar']} SURV={m['DAILY_SURVIVOR']}")
        print(f"          coverage={m['coverage']}")
    print("\n=== CONTRAST ===")
    print(f"  morning - midday : exp_pct {morn_vs_mid_pct:+.4f} | "
          f"exp_dollar ${morn_vs_mid_dollar:+.1f}")
    print(f"  morning - baseline OOS exp $: {morn_vs_base_oos:+.1f}")
    print(f"\n  VERDICT: {verdict}")
    print(f"  {reason}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
