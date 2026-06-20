"""j_archetype_discovery — ROUND 2: J's real-winner archetypes -> standalone detectors.

Round 1 (``infinite_ammo_discovery.py``) created edge from first principles and
found 2 survivors: VWAP trend-day pullback (H4) and gap-and-go (H2b). Round 2
converts the ARCHETYPES revealed by J's *actual* winning trades
(``markdown/0dte/J-WEBULL-EDGE-2021-2023.md``) into detectors and standalone-backtests
them with the SAME rigor (real OPRA fills, ATM+ITM1, chronological OOS split,
DSR via lib.validation, drop-top-5 outlier kill).

J's winning trades clustered into four archetypes — every winner on the correct
side of session VWAP, most entries midday (~11:00-13:00 ET):
  * trend-continuation
  * reversal-off-extreme   (fade a push to a session high/low / VWAP extreme)
  * momentum-breakout
  * pullback-resumption    (pullback to VWAP/MA then resume)

Round 1 already covered trend-continuation/pullback (H4 VWAP-pullback) and
momentum-breakout (H2b gap-and-go). Round 2 tests the archetypes NOT yet
covered, keyed on the SPECIFIC signal J's winners used:

  A1  REVERSAL-OFF-VWAP-EXTREME (both directions). Price stretches >= K sigma
      away from session VWAP (sigma = stdev of bar closes' VWAP-deviation so far)
      AND prints a NEW session extreme, then a reversion candle confirms the turn
      back toward VWAP -> FADE it. up-extreme -> PUTS, down-extreme -> CALLS.
      This is J's two reversal winners (3/14, 5/12: faded price pushed above VWAP
      into a session high). Causal: VWAP, sigma, extreme, and the reversal candle
      are all read at-or-before the trigger bar close; fill is the next bar open.

  A2  MA-TOUCH PULLBACK-RESUMPTION (both directions). In an EMA-defined intraday
      trend (price + fast-EMA on one side of slow-EMA), enter the pullback that
      TAGS the fast EMA and then prints a resumption candle closing back in the
      trend direction. Distinct from H4: H4 keys on "first 30m all one side of
      session VWAP + a VWAP tag"; A2 keys on an EMA(9)-touch + a resumption candle
      and can fire any time the EMA trend is intact (J's 6/01 + 6/06 pullback
      winners). pullback-up-in-uptrend -> CALLS, pullback-down-in-downtrend -> PUTS.

  A3  MIDDAY-WINDOW OVERLAY. J's edge is concentrated 11:00-13:30 ET (13:00 hour
      = 72.7% WR / +$69; 11:00 = +$29; 12:00 = +$19). We re-summarize A1, A2 AND
      round-1's two survivors (gap-and-go, VWAP-pullback) restricted to entries
      whose trigger bar falls in [11:00, 13:30) ET, and compare IN-window vs
      OUT-of-window standalone expectancy. This is a time-of-day overlay test,
      NOT a new detector.

PROPOSE-ONLY (Rule 9). Nothing here touches the live engine, params, or the order
path. Survivors become WATCH-ONLY candidate slots for the regime-aware book
(``backtest/lib/engine/regime_book.py``). Output is a scorecard JSON only.

THE GATE (honest, identical to round 1): a signal set SURVIVES only if
  standalone real-fills exp_pct > 0 AND exp_dollar > 0 AND OOS sign-stable AND
  DSR != FAIL AND robust to dropping the top-5 winners (kills lottery edges).

REUSE, not a framework
----------------------
Imports the round-1 harness wholesale (``infinite_ammo_discovery``): the SPY/VIX
loaders, ``DayCtx``/``build_day_contexts``, ``session_vwap_asof``, the ``Signal``
contract, ``simulate_signals`` (real fills, nearest-cached strike, OP-20 proxy
disclosure) and ``summarize`` (drop-top-5 + OOS + DSR). We only add three
detectors + the midday overlay + a driver. No fill logic is re-implemented.

Usage
-----
    python backtest/autoresearch/j_archetype_discovery.py
        [--spy PATH] [--vix PATH] [--qty 3] [--max-strike-steps 4]
        [--out analysis/recommendations/j-archetype-discovery.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Reuse the entire round-1 harness — DO NOT re-implement fills / stats.
from autoresearch.infinite_ammo_discovery import (   # noqa: E402
    DayCtx,
    OOS_SPLIT_FRAC,
    Signal,
    align_vix,
    build_day_contexts,
    detect_gap_and_go,
    detect_vwap_pullback,
    load_spy,
    session_vwap_asof,
    simulate_signals,
    summarize,
)
from lib.ribbon import compute_ribbon                # noqa: E402

# A detector reads (spy_df, ribbon_df, vix, day_contexts) and returns Signals.
Detector = Callable[[pd.DataFrame, pd.DataFrame, pd.Series, list[DayCtx]], list[Signal]]

# J's documented edge window (markdown/0dte/J-WEBULL-EDGE-2021-2023.md "edge axis"):
# 11:00, 12:00, 13:00, 14:30 are his positive-expectancy buckets; the open and
# late-afternoon bleed. We use the contiguous core 11:00-13:30 as the overlay
# window (captures 11:00/12:00/13:00 hours; excludes the 13:30 dead bucket and
# the open). Treated as a hypothesis given small per-bucket n in J's data.
MIDDAY_START = dt.time(11, 0)
MIDDAY_END = dt.time(13, 30)


# ─────────────────────────────────────────────────────────────────────────────
# A1 — REVERSAL OFF A VWAP EXTREME (fade a session-extreme push back toward VWAP)
# ─────────────────────────────────────────────────────────────────────────────
def detect_vwap_extreme_reversal(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """Fade a >= K-sigma VWAP stretch into a NEW session extreme, on reversal.

    For each session, walk the RTH bars keeping look-ahead-safe running state:
      * session VWAP as-of (typical-price cumulative);
      * the per-bar VWAP deviation `dev_i = close_i - vwap_i`, whose running
        standard deviation `sigma_i` (population, over bars[0..i]) is the
        stretch yardstick;
      * the running session high / low (as-of).

    A *bullish reversal* (-> CALLS, fade a down-extreme) triggers at bar i when:
      - dev_i <= -K * sigma_i           (price stretched FAR below VWAP), AND
      - low_i is a NEW session low as-of i (a fresh down-extreme), AND
      - close_i > open_i                (reversal candle: closes green), AND
      - i is past a short warmup (need a stable sigma).
    Stop = the session low at i (just printed) — a structural fade stop.
    The *bearish* mirror (-> PUTS) flips high/low, sign and candle colour.
    One entry per day (first qualifying bar). All inputs are as-of bar i.
    """
    K_SIGMA = 1.6        # >= 1.6 stdev VWAP stretch = "extreme"
    WARMUP = 6           # need >= 6 bars for a meaningful running sigma
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < WARMUP + 3:
            continue
        vwap = session_vwap_asof(rth).values
        o = rth["open"].values
        h = rth["high"].values
        low = rth["low"].values
        c = rth["close"].values
        idxs = rth.index.tolist()
        dev = c - vwap
        run_high = -np.inf
        run_low = np.inf
        fired = False
        for j in range(len(rth)):
            # update running extremes AFTER capturing the prior-bar state for the
            # "new extreme" test (a new low at j means low[j] < min(low[:j])).
            prev_high = run_high
            prev_low = run_low
            run_high = max(run_high, h[j])
            run_low = min(run_low, low[j])
            if fired or j < WARMUP or vwap[j] <= 0:
                continue
            sigma = float(np.std(dev[: j + 1]))     # population stdev, as-of j
            if sigma <= 0:
                continue
            new_low = low[j] < prev_low
            new_high = h[j] > prev_high
            green = c[j] > o[j]
            red = c[j] < o[j]
            # down-extreme + green reversal candle -> fade up -> CALLS
            if dev[j] <= -K_SIGMA * sigma and new_low and green:
                out.append(Signal(bar_idx=int(idxs[j]), side="C",
                                  stop_level=float(low[j]),
                                  note=f"vwap_rev dev={dev[j]:+.2f} k={dev[j]/sigma:+.2f}sig low_ext"))
                fired = True
            # up-extreme + red reversal candle -> fade down -> PUTS
            elif dev[j] >= K_SIGMA * sigma and new_high and red:
                out.append(Signal(bar_idx=int(idxs[j]), side="P",
                                  stop_level=float(h[j]),
                                  note=f"vwap_rev dev={dev[j]:+.2f} k={dev[j]/sigma:+.2f}sig high_ext"))
                fired = True
    return out


# ─────────────────────────────────────────────────────────────────────────────
# A2 — MA-TOUCH PULLBACK RESUMPTION (EMA-trend pullback that resumes)
# ─────────────────────────────────────────────────────────────────────────────
def _ema(arr: np.ndarray, span: int) -> np.ndarray:
    """Causal EMA (pandas ewm, adjust=False) — value at i uses only arr[0..i]."""
    return pd.Series(arr).ewm(span=span, adjust=False).mean().values


def detect_ma_pullback_resumption(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """In an EMA(fast/slow) intraday trend, enter the EMA-touch pullback that resumes.

    Per session compute causal EMA_fast (9) and EMA_slow (21) over the RTH closes.
    Uptrend at bar i := EMA_fast[i] > EMA_slow[i] AND close[i] > EMA_slow[i].
    Trigger an *uptrend* resumption (-> CALLS) at bar i when:
      - uptrend holds at i, AND
      - the bar TAGS the fast EMA (low[i] <= EMA_fast[i] <= high[i], i.e. price
        pulled back into the EMA), AND
      - a resumption candle: close[i] > open[i] AND close[i] > EMA_fast[i]
        (pullback rejected, closing back above the fast EMA in trend direction).
    Stop = the bar's low (structural pullback low). Downtrend mirror -> PUTS with
    high-tag + red resumption close below the fast EMA. One entry per day (first).

    Distinct from H4 (round 1): H4 requires the first 30m all on one side of
    *session VWAP* then a VWAP tag; A2 keys on an EMA(9) touch + resumption candle
    and can fire whenever the EMA trend is intact — a different signal surface.
    Causal: EMAs and the candle are all read at-or-before bar i; fill is next bar.
    """
    FAST, SLOW = 9, 21
    WARMUP = SLOW            # need the slow EMA to be meaningful
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < WARMUP + 3:
            continue
        o = rth["open"].values
        h = rth["high"].values
        low = rth["low"].values
        c = rth["close"].values
        idxs = rth.index.tolist()
        ef = _ema(c, FAST)
        es = _ema(c, SLOW)
        fired = False
        for j in range(WARMUP, len(rth)):
            if fired:
                break
            up = ef[j] > es[j] and c[j] > es[j]
            dn = ef[j] < es[j] and c[j] < es[j]
            tag_fast = low[j] <= ef[j] <= h[j]      # bar straddles the fast EMA
            if not tag_fast:
                continue
            green = c[j] > o[j]
            red = c[j] < o[j]
            if up and green and c[j] > ef[j]:
                out.append(Signal(bar_idx=int(idxs[j]), side="C",
                                  stop_level=float(low[j]),
                                  note=f"ema_pull up ef={ef[j]:.2f} es={es[j]:.2f}"))
                fired = True
            elif dn and red and c[j] < ef[j]:
                out.append(Signal(bar_idx=int(idxs[j]), side="P",
                                  stop_level=float(h[j]),
                                  note=f"ema_pull dn ef={ef[j]:.2f} es={es[j]:.2f}"))
                fired = True
    return out


# ─────────────────────────────────────────────────────────────────────────────
# A3 — MIDDAY-WINDOW OVERLAY (time-of-day conditioning, not a new detector)
# ─────────────────────────────────────────────────────────────────────────────
def _in_midday(spy_df: pd.DataFrame, bar_idx: int) -> bool:
    """True if the signal's trigger bar falls in [MIDDAY_START, MIDDAY_END) ET."""
    t = spy_df.iloc[bar_idx]["timestamp_et"].time()
    return MIDDAY_START <= t < MIDDAY_END


def split_midday(signals: list[Signal], spy_df: pd.DataFrame) -> tuple[list[Signal], list[Signal]]:
    """Partition signals into (in-window, out-of-window) by trigger-bar ET time."""
    inw = [s for s in signals if _in_midday(spy_df, s.bar_idx)]
    outw = [s for s in signals if not _in_midday(spy_df, s.bar_idx)]
    return inw, outw


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────────
# Round-2 NEW detectors (the archetypes round 1 did not cover).
NEW_ARCHETYPES: dict[str, tuple[str, Detector, str]] = {
    "A1_vwap_extreme_reversal": (
        "Reversal off a >=1.6-sigma VWAP extreme into a new session high/low (fade)",
        detect_vwap_extreme_reversal, "range_pin / high_vol (mean-reversion)"),
    "A2_ma_pullback_resumption": (
        "EMA(9/21) trend pullback to the fast EMA that resumes (resumption candle)",
        detect_ma_pullback_resumption, "bull_trend / bear_trend"),
}

# For the midday overlay we also re-run round-1's two SURVIVORS so the time-of-day
# question is answered for the candidates already in the book, not just the new ones.
OVERLAY_DETECTORS: dict[str, tuple[str, Detector]] = {
    "A1_vwap_extreme_reversal": ("Reversal off VWAP extreme (round 2)",
                                 detect_vwap_extreme_reversal),
    "A2_ma_pullback_resumption": ("EMA pullback resumption (round 2)",
                                  detect_ma_pullback_resumption),
    "R1_gap_and_go": ("Gap-and-go (round-1 survivor)", detect_gap_and_go),
    "R1_vwap_pullback": ("VWAP trend-day pullback (round-1 survivor)",
                         detect_vwap_pullback),
}


def _run_set(label, signals, spy, ribbon, vix, qty, steps, strike_tiers,
             oos_cut_date, n_trials) -> dict:
    """Simulate a signal set across strike tiers and summarize (round-1 machinery)."""
    side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                   "C": sum(1 for s in signals if s.side == "C")}
    tier_blocks: dict = {}
    for tname, off in strike_tiers.items():
        rows, cov = simulate_signals(signals, spy, ribbon, vix, qty, off, steps)
        summ = summarize(rows, oos_cut_date, n_trials)
        tier_blocks[tname] = {"coverage": cov, "metrics": summ}
        print(f"    [{label}/{tname}] filled={cov['filled']}/{cov['signals']} "
              f"exp$={summ.get('exp_dollar_per_trade')} WR={summ.get('win_rate_pct')}% "
              f"OOS={summ.get('oos_sign_stable')} drop5={summ.get('drop_top5_mean_dollar')} "
              f"DSR={summ.get('dsr_verdict')} SURV={summ.get('SURVIVOR')}")
    return {"signal_count": len(signals), "side_counts": side_counts, "tiers": tier_blocks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spy", default=str(REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"))
    ap.add_argument("--vix", default=str(REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"))
    ap.add_argument("--qty", type=int, default=3)
    ap.add_argument("--max-strike-steps", type=int, default=4)
    ap.add_argument("--out", default=str(PROJECT / "analysis" / "recommendations" /
                                         "j-archetype-discovery.json"))
    args = ap.parse_args()

    print(f"Loading SPY {args.spy}")
    spy = load_spy(args.spy)
    vix = align_vix(spy, args.vix)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    print(f"SPY bars={len(spy)} days={len(days)} "
          f"range {spy['date'].min()}..{spy['date'].max()} VIX aligned={len(vix)}")

    all_dates = [dc.date for dc in days]
    cut_i = int(len(all_dates) * OOS_SPLIT_FRAC)
    oos_cut_date = str(all_dates[cut_i])
    print(f"OOS cut date = {oos_cut_date} (IS {cut_i} days / OOS {len(all_dates)-cut_i} days)")

    strike_tiers = {"ATM": 0, "ITM1": -1}
    # n_trials for DSR deflation. Round 2 searches 2 new families x 2 directions x
    # 2 strike tiers, plus the midday overlay re-uses 4 families. We keep the same
    # conservative count as round 1 (err strict): 30.
    n_trials = 30

    # ── Phase 1: the two NEW archetype detectors (full population) ──────────────
    archetype_results: dict = {}
    for key, (title, detector, regime_fit) in NEW_ARCHETYPES.items():
        print(f"\n=== {key}: {title} ===")
        signals = detector(spy, ribbon, vix, days)
        print(f"  signals={len(signals)} "
              f"(P={sum(1 for s in signals if s.side=='P')} "
              f"C={sum(1 for s in signals if s.side=='C')})")
        blk = _run_set("full", signals, spy, ribbon, vix, args.qty,
                       args.max_strike_steps, strike_tiers, oos_cut_date, n_trials)
        blk["title"] = title
        blk["regime_fit"] = regime_fit
        archetype_results[key] = blk

    # ── Phase 2: midday-window overlay (A1, A2 + round-1 survivors) ─────────────
    print(f"\n=== A3 midday overlay [{MIDDAY_START}-{MIDDAY_END} ET] ===")
    overlay_results: dict = {}
    for key, (title, detector) in OVERLAY_DETECTORS.items():
        signals = detector(spy, ribbon, vix, days)
        inw, outw = split_midday(signals, spy)
        print(f"  {key}: {len(signals)} signals -> in-window {len(inw)} / out {len(outw)}")
        in_blk = _run_set(f"{key}/IN", inw, spy, ribbon, vix, args.qty,
                          args.max_strike_steps, strike_tiers, oos_cut_date, n_trials)
        out_blk = _run_set(f"{key}/OUT", outw, spy, ribbon, vix, args.qty,
                           args.max_strike_steps, strike_tiers, oos_cut_date, n_trials)
        # Compact ATM lift summary (the headline the overlay is meant to answer).
        def _exp(b):
            m = b["tiers"].get("ATM", {}).get("metrics", {})
            return m.get("exp_dollar_per_trade"), m.get("win_rate_pct"), m.get("n")
        in_exp, in_wr, in_n = _exp(in_blk)
        out_exp, out_wr, out_n = _exp(out_blk)
        overlay_results[key] = {
            "title": title,
            "window": f"{MIDDAY_START}-{MIDDAY_END} ET",
            "in_window": in_blk,
            "out_window": out_blk,
            "atm_lift": {
                "in_n": in_n, "in_exp_dollar": in_exp, "in_wr": in_wr,
                "out_n": out_n, "out_exp_dollar": out_exp, "out_wr": out_wr,
                "exp_dollar_delta": (round(in_exp - out_exp, 2)
                                     if (in_exp is not None and out_exp is not None) else None),
                "midday_stronger": bool(in_exp is not None and out_exp is not None
                                        and in_exp > out_exp),
            },
        }

    # ── Survivor roll-up (NEW archetypes only; overlay is conditioning, not a
    #    standalone candidate). A hypothesis survives if ANY strike tier is SURVIVOR. ─
    survivors = []
    for key, blk in archetype_results.items():
        n_days = len(days)
        for tname, tb in blk["tiers"].items():
            m = tb["metrics"]
            if m.get("SURVIVOR"):
                # Honest caveats the binary gate does not encode (surface, don't hide):
                #  - oos_sign_stable is computed on the % return stream; flag when the
                #    OOS *dollar* expectancy has nonetheless decayed to <=0 (the % edge
                #    survives but the $ edge does not at this tier).
                #  - a detector firing on a very high fraction of days is closer to a
                #    persistent overlay than a selective setup (lesson C27).
                caveats = []
                if m.get("oos_exp_dollar", 0.0) <= 0:
                    caveats.append(
                        f"OOS dollar expectancy <=0 ({m['oos_exp_dollar']}) despite "
                        f"OOS %-return sign-stability — $ edge decays at this tier")
                fire_frac = round(blk["signal_count"] / n_days, 3) if n_days else 0.0
                if fire_frac >= 0.80:
                    caveats.append(
                        f"fires on {fire_frac:.0%} of days (n={blk['signal_count']}/"
                        f"{n_days}) — persistent overlay, not a selective trigger (C27)")
                survivors.append({
                    "hypothesis": key, "title": blk["title"], "tier": tname,
                    "regime_fit": blk["regime_fit"],
                    "n": m["n"], "exp_dollar_per_trade": m["exp_dollar_per_trade"],
                    "exp_pct_return": m["exp_pct_return"], "win_rate_pct": m["win_rate_pct"],
                    "both_dirs_positive": m.get("both_dirs_positive"),
                    "oos_sign_stable": m["oos_sign_stable"],
                    "is_exp_dollar": m.get("is_exp_dollar"),
                    "oos_exp_dollar": m.get("oos_exp_dollar"),
                    "drop_top5_mean_dollar": m["drop_top5_mean_dollar"],
                    "dsr_verdict": m["dsr_verdict"],
                    "caveats": caveats,
                })

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/j_archetype_discovery.py",
        "round": 2,
        "purpose": (
            "ROUND 2 strategy discovery: convert J's REAL-winner archetypes "
            "(markdown/0dte/J-WEBULL-EDGE-2021-2023.md) into standalone detectors and "
            "real-fills-backtest them with round-1 rigor. Reversal-off-VWAP-extreme "
            "+ MA-touch pullback-resumption (the archetypes round 1 did not cover), "
            "plus a midday (11:00-13:30 ET) time-of-day overlay on these and the two "
            "round-1 survivors. Propose-only (Rule 9); survivors are WATCH-ONLY "
            "candidates for the regime-aware book."
        ),
        "round1_reference": {
            "scorecard": "analysis/recommendations/infinite-ammo-discovery.json",
            "survivors": ["H2b_gap_and_go", "H4_vwap_pullback"],
            "note": "round 1 covered trend-continuation/pullback (H4) and "
                    "momentum-breakout (H2b); round 2 adds reversal-off-extreme + "
                    "an EMA-keyed pullback-resumption + the midday overlay.",
        },
        "method": {
            "fills": "lib.simulator_real.simulate_trade_real via "
                     "infinite_ammo_discovery.simulate_signals (real OPRA bars, causal "
                     "next-bar-open entry, chart/level + premium stops, v15 exit stack)",
            "strike_tiers": strike_tiers,
            "qty": args.qty,
            "oos_split": f"chronological {OOS_SPLIT_FRAC:.0%}/{(1-OOS_SPLIT_FRAC):.0%} by day; "
                         f"cut={oos_cut_date}",
            "dsr": f"lib.validation.gate.evaluate_candidate on % return stream; n_trials={n_trials}",
            "midday_window": f"{MIDDAY_START}-{MIDDAY_END} ET (J's positive-expectancy core)",
            "candidate_gate": "exp_pct>0 AND exp_dollar>0 AND oos_sign_stable AND "
                              "DSR!=FAIL AND drop_top5_mean>0 (lottery-edge kill)",
        },
        "disclosure_OP20": {
            "real_fills": True,
            "opra_window": "options cached through ~2026-05-29; later signals have no "
                           "fills and are dropped (coverage.cache_miss).",
            "proxy_strikes": "nearest-cached strike to the target offset used; true offset "
                             "reported per trade (strike_off). ITM/OTM proxy shifts P&L "
                             "modestly (L58) — directionally valid.",
            "no_look_ahead": "VWAP, sigma, running extremes, EMAs and reversal/resumption "
                             "candles all computed at-or-before the trigger bar close; entry "
                             "is the NEXT bar open (sim-enforced).",
            "archetype_caveat": "archetypes hand-derived from n=9 J winners on 5m bars "
                                "(lesson C24 — anchors can be one-off exceptions). These "
                                "detectors are a POPULATION test of the archetype, not a "
                                "replay of J's exact trades. Standalone single-setup eval on "
                                "proxy levels — candidates worth a real-level re-test, NOT "
                                "ready-to-trade.",
            "midday_caveat": "J's per-bucket time-of-day n is small (13:00 hour n=22); the "
                             "overlay is a hypothesis test on the engine's own population, "
                             "not a confirmation of J's bucket stats.",
        },
        "data": {
            "spy": Path(args.spy).name,
            "vix": Path(args.vix).name,
            "days": len(days),
            "date_range": [str(spy["date"].min()), str(spy["date"].max())],
        },
        "archetypes": archetype_results,
        "midday_overlay": overlay_results,
        "survivors": survivors,
        "survivor_count": len(survivors),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nWrote {out_path}")
    print(f"SURVIVORS (new archetypes): {len(survivors)}")
    for s in survivors:
        print(f"  - {s['hypothesis']} [{s['tier']}] exp$={s['exp_dollar_per_trade']} "
              f"WR={s['win_rate_pct']}% n={s['n']} IS$={s['is_exp_dollar']} "
              f"OOS$={s['oos_exp_dollar']} drop5={s['drop_top5_mean_dollar']} "
              f"DSR={s['dsr_verdict']} regime={s['regime_fit']}")
        for cav in s["caveats"]:
            print(f"      ! {cav}")
    print("\nMidday overlay (ATM exp$ in-window vs out-of-window):")
    for key, blk in overlay_results.items():
        lift = blk["atm_lift"]
        print(f"  - {key}: IN n={lift['in_n']} exp$={lift['in_exp_dollar']} "
              f"| OUT n={lift['out_n']} exp$={lift['out_exp_dollar']} "
              f"| delta={lift['exp_dollar_delta']} midday_stronger={lift['midday_stronger']}")


if __name__ == "__main__":
    main()
