"""ENTRY-QUALITY analysis — reconstruct J's entry "theory" and separate his
genuinely-GOOD entries from his genuinely-BAD ones (Project Gamma task #78).

Companion to webull_loser_stopped_then_printed.py (which proved the HOLD/exit on
his losers). This module does the ENTRY side: for EVERY closed SPX/SPY-family
round-trip (winners AND losers) it reconstructs the chart state at J's entry bar
(his inferred READ), then labels each entry GOOD-thesis vs BAD-thesis by what the
underlying did AFTER his entry, and tests which entry features separate the two.

HONESTY CONTRACT
----------------
  * His behaviour (entry time, entry price, qty, exit) is EXACT (his fills).
  * The "theory"/read at entry is INFERRED from look-ahead-free price action
    (VWAP relation, trend, level proximity, trigger, extension). We did NOT have
    his notes — Webull records the trade, not the thought. Every read is a
    reconstruction from the tape.
  * The GOOD/BAD-thesis label uses the EXACT underlying path AFTER his entry
    (SPY 5m IEX, SPX/SPY ~10:1 proxy). Direction is EXACT.
  * The premium-MAE "poke" uses a Black-Scholes estimate (IV implied from his own
    entry fill) — labelled _EST. The underlying-points poke is EXACT.

GOOD vs BAD THESIS (the core split)
-----------------------------------
For each entry we walk the underlying forward from the entry bar to min(his exit,
EOD) and to EOD, and measure the favorable continuation (up for calls, down for
puts) vs the adverse excursion. An entry is:

  GOOD-thesis : the underlying continued his way MEANINGFULLY after entry
                (favorable move >= MEANINGFUL_FRAC of spot before it went
                 adverse-and-stayed) — i.e. the READ was right, regardless of
                whether his exit captured it. = all winners + the right-thesis
                losers (the 68% "stopped then printed" cohort).
  BAD-thesis  : the underlying went against him and STAYED against him
                (never gave a meaningful favorable move; closed adverse) — the
                read itself was wrong. = the ~32% wrong-thesis losers.

ENTRY-QUALITY FEATURES tested as discriminators
-----------------------------------------------
  * vwap_aligned        : trade side == price's side of session VWAP (known leak)
  * vwap_dist_bp        : signed distance to VWAP (bp); |.| = extension from VWAP
  * extension_from_open : signed % from session open in trade direction (chasing)
  * stretched_atr       : favorable distance already travelled / mean-bar-range
                          (how far had it already run = mean-revert/chase risk)
  * confirmed_close     : did the entry bar CLOSE in the thesis direction
                          (entered after a confirming close) vs entered into a
                          wick/poke (open-vs-close against thesis)?
  * entry_mae_pts_EXACT : worst adverse underlying excursion in first N bars
  * entry_mae_prem_EST  : worst adverse premium drawdown in first N bars (BS)
  * near_level          : entered within X% of a reference level vs mid-air
  * time_bucket         : 30-min ET entry bucket
  * trigger / archetype : reclaim / rejection / breakout / pullback / reversal

For each discriminator we report, GOOD vs BAD: count, win-rate, and (where it is
the split itself) the lift. Discriminators are ranked by how cleanly they
separate GOOD from BAD entries (separation = |good_rate - bad_rate| weighted by
support, plus the WR lift of the TAKE vs AVOID side).

Reuses: webull_daily_pattern_miner.extract_features (the canonical look-ahead-free
entry-read extractor), the loser module's DST-correct ET conversion + Alpaca
credential loader + bar fetch + _spot_at + _tte_years + black_scholes, and the
winner+loser bar caches. Pure stdlib + repo pricer. py_compile clean. Propose-only.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/webull_entry_quality.py
  backtest/.venv/Scripts/python.exe backtest/autoresearch/webull_entry_quality.py --no-fetch
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]          # .../42/backtest
PROJECT = REPO.parent                                # .../42
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "autoresearch"))

from lib.pricing import black_scholes  # noqa: E402

# Reuse the canonical look-ahead-free entry-read extractor + bar helpers.
from autoresearch.webull_daily_pattern_miner import (  # noqa: E402
    Bar,
    extract_features,
)
# Reuse the loser module's robust cache builder + DST-correct conversion + creds.
from autoresearch.webull_loser_stopped_then_printed import (  # noqa: E402
    RoundTrip,
    _rth_bars,
    _spot_at,
    _tte_years,
    _implied_iv_from_entry,
    build_loser_cache,
    load_roundtrips,
    _load_cache,
    WINNER_CACHE,
    LOSER_CACHE,
    SPX_SPY,
    RISK_FREE,
)

OUT_DIR = PROJECT / "analysis" / "webull-j-trades"
ENTRY_JSON = OUT_DIR / "entry_quality.json"
REC_JSON = PROJECT / "analysis" / "recommendations" / "j-entry-quality.json"

# --- thesis-label thresholds --------------------------------------------------
# "meaningful" favorable continuation = >= 0.25% of spot (~$1 on SPY) — same bar
# as the loser module's "continued meaningfully" so the two analyses are
# comparable. A move smaller than this is tape noise, not a right read.
MEANINGFUL_FRAC = 0.0025
# An entry is BAD-thesis if the favorable move never reached MEANINGFUL_FRAC AND
# the underlying closed adverse at his exit horizon (went against and stayed).
# --- entry-quality feature params ---------------------------------------------
MAE_BARS = 4                 # first 4 x 5m = 20 min post-entry "immediate" window
NEAR_LEVEL_PCT = 0.0015      # within 0.15% of a reference level = "at a level"
STRETCH_ATR_HI = 2.5         # favorable run already >= 2.5x mean-bar = "stretched"


# --------------------------------------------------------------------------- #
# Level reconstruction (look-ahead-free, at entry bar) — light reuse of the
# winner-journal idea but kept local to avoid a heavy import chain.
# --------------------------------------------------------------------------- #
def _nearest_level_dist(bars: list[Bar], idx: int) -> float:
    """Signed % distance from entry close to the NEAREST same-session reference
    level (round number / session open / pre-entry intraday hi / lo). Causal:
    only same-session bars up to entry. Returns abs % for proximity test."""
    entry = bars[idx]
    px = entry.c
    pre = bars[:idx] if idx > 0 else bars[:1]
    cands = [
        round(px),                      # nearest round dollar
        bars[0].o,                      # session open
        max(b.h for b in pre),          # intraday high before entry
        min(b.l for b in pre),          # intraday low before entry
    ]
    nearest = min(cands, key=lambda lvl: abs(px - lvl))
    return abs(px - nearest) / nearest * 100 if nearest else 99.9


def _mean_bar_range(bars: list[Bar], idx: int) -> float:
    pre = bars[: idx + 1]
    if not pre:
        return 0.0
    return sum(b.h - b.l for b in pre) / len(pre)


# --------------------------------------------------------------------------- #
# Forward thesis label + immediate adverse excursion
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThesisOutcome:
    continued_meaningfully: bool          # favorable move >= MEANINGFUL_FRAC after entry
    fav_move_pts: float                   # best favorable underlying move post-entry
    adverse_first: bool                   # did it go adverse-meaningful BEFORE favorable?
    closed_adverse: bool                  # underlying at exit horizon was adverse vs entry
    good_thesis: bool                     # the GOOD/BAD label
    mae_pts: float                        # worst adverse underlying excursion (first MAE_BARS)
    mae_prem_frac_est: Optional[float]    # worst premium drawdown frac (first MAE_BARS), BS


def _forward_thesis(bars: list[Bar], entry_idx: int, is_call: bool,
                    entry_spot: float, exit_dt: dt.datetime,
                    strike_spy: float, iv: Optional[float],
                    entry_dt: dt.datetime) -> ThesisOutcome:
    """Walk the underlying forward from the entry bar. Look-FORWARD is intentional
    here — this defines whether the READ was right, not an entry signal.

    Horizon = up to his exit bar (inclusive) for the close-adverse test; the
    favorable-extreme scan runs to min(exit, EOD) so a right read he bailed on
    early still counts as GOOD-thesis (the read was right; the exit failed)."""
    post = bars[entry_idx + 1:]            # strictly after the entry bar
    if not post:
        # no forward bars — treat as neutral, fall back to entry-bar body.
        return ThesisOutcome(False, 0.0, False, False, False, 0.0, None)

    # Horizon bar index for the "closed adverse" test = his exit bar (floor to 5m).
    m = exit_dt.minute - (exit_dt.minute % 5)
    exit_floor = exit_dt.replace(minute=m, second=0, microsecond=0)
    horizon = [b for b in post if b.t_et <= exit_floor] or post

    # Favorable + adverse extremes over the horizon (EXACT underlying).
    if is_call:
        fav_extreme = max(b.h for b in horizon)
        adv_extreme = min(b.l for b in horizon)
        fav_move = fav_extreme - entry_spot
        adv_move = entry_spot - adv_extreme
        close_px = horizon[-1].c
        closed_adverse = close_px < entry_spot
    else:
        fav_extreme = min(b.l for b in horizon)
        adv_extreme = max(b.h for b in horizon)
        fav_move = entry_spot - fav_extreme
        adv_move = adv_extreme - entry_spot
        close_px = horizon[-1].c
        closed_adverse = close_px > entry_spot

    meaningful = MEANINGFUL_FRAC * entry_spot
    continued_meaningfully = fav_move >= meaningful

    # Did it go adverse-meaningful in the same window? (for the "went against" test)
    adverse_meaningful = adv_move >= meaningful

    # GOOD-thesis = the read was right: a meaningful favorable move materialised.
    # BAD-thesis  = no meaningful favorable move AND it closed adverse (against+stayed).
    good_thesis = continued_meaningfully or (not closed_adverse and not adverse_meaningful)

    # Which came first — favorable or adverse — over the first few bars (the poke).
    adverse_first = False
    for b in post[:MAE_BARS * 2]:
        if is_call:
            if (entry_spot - b.l) >= meaningful:
                adverse_first = True
                break
            if (b.h - entry_spot) >= meaningful:
                break
        else:
            if (b.h - entry_spot) >= meaningful:
                adverse_first = True
                break
            if (entry_spot - b.l) >= meaningful:
                break

    # Immediate adverse excursion (first MAE_BARS bars) — EXACT underlying.
    window = post[:MAE_BARS]
    if is_call:
        mae_pts = max(0.0, entry_spot - min(b.l for b in window)) if window else 0.0
    else:
        mae_pts = max(0.0, max(b.h for b in window) - entry_spot) if window else 0.0

    # Immediate adverse premium drawdown (first MAE_BARS) — BS ESTIMATE.
    mae_prem_frac = None
    if iv is not None and window:
        entry_tte = _tte_years(entry_dt)
        entry_prem, _ = black_scholes(entry_spot, strike_spy, iv, entry_tte, is_call, RISK_FREE)
        if entry_prem > 0:
            worst = entry_prem
            for b in window:
                adverse_spot = b.l if is_call else b.h
                tte = _tte_years(b.t_et)
                prem, _ = black_scholes(adverse_spot, strike_spy, iv, tte, is_call, RISK_FREE)
                worst = min(worst, prem)
            mae_prem_frac = (worst - entry_prem) / entry_prem  # negative

    return ThesisOutcome(
        continued_meaningfully=continued_meaningfully,
        fav_move_pts=round(fav_move, 3),
        adverse_first=adverse_first,
        closed_adverse=closed_adverse,
        good_thesis=good_thesis,
        mae_pts=round(mae_pts, 3),
        mae_prem_frac_est=round(mae_prem_frac, 4) if mae_prem_frac is not None else None,
    )


# --------------------------------------------------------------------------- #
# Per-trade entry-quality record
# --------------------------------------------------------------------------- #
def _entry_index(bars: list[Bar], entry_hhmm: str) -> Optional[int]:
    h, m = (int(x) for x in entry_hhmm.split(":"))
    floored = m - (m % 5)
    if not bars:
        return None
    target = bars[0].t_et.replace(hour=h, minute=floored, second=0)
    best = None
    for i, b in enumerate(bars):
        if b.t_et == target:
            return i
        if b.t_et <= target:
            best = i
    return best


def build_records(rts: list[RoundTrip],
                  cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """One entry-quality record per closed trade with cached bars + locatable entry."""
    out: list[dict[str, Any]] = []
    for r in rts:
        raw = cache.get(r.date)
        if not raw:
            continue
        bars = _rth_bars(raw)
        if not bars:
            continue
        entry_hhmm = r.entry_dt.strftime("%H:%M")
        idx = _entry_index(bars, entry_hhmm)
        if idx is None or idx >= len(bars):
            continue
        side = r.right  # 'C'/'P'
        feats = extract_features(bars, entry_hhmm, side)
        if "error" in feats:
            continue

        entry = bars[idx]
        is_call = side == "C"
        strike_spy = r.strike_spy
        entry_spot = _spot_at(bars, r.entry_dt)
        if entry_spot is None:
            entry_spot = entry.c

        # IV implied from his actual entry fill (anchors the premium-MAE estimate).
        iv = _implied_iv_from_entry(entry_spot, strike_spy, is_call,
                                    _tte_years(r.entry_dt), r.entry_px)

        outcome = _forward_thesis(bars, idx, is_call, entry_spot, r.exit_dt,
                                  strike_spy, iv, r.entry_dt)

        # --- entry-quality features (all causal / at-entry except the forward label) ---
        vwap_dist_bp = feats["vwap_dist_bp"]
        vwap_aligned = (is_call and feats["vwap_side"] == "above") or \
                       (not is_call and feats["vwap_side"] == "below")
        # |extension from VWAP| in the trade direction (bp). If aligned, this is how
        # FAR past VWAP he chased; if counter, it's how far offside he was.
        ext_from_vwap_bp = abs(vwap_dist_bp)

        # extension from session open in the trade direction (% — chasing tell).
        sess_open = bars[0].o
        raw_ext_open = (entry.c - sess_open) / sess_open * 100 if sess_open else 0.0
        ext_from_open = raw_ext_open if is_call else -raw_ext_open  # +ve = with thesis

        # stretched: favorable distance already travelled from session open / mean-bar.
        mean_bar = _mean_bar_range(bars, idx)
        if is_call:
            run_pts = max(0.0, entry.c - sess_open)
        else:
            run_pts = max(0.0, sess_open - entry.c)
        stretched_atr = run_pts / mean_bar if mean_bar > 0 else 0.0

        # confirmed close: did the ENTRY bar close in the thesis direction (entered
        # after a confirming close), or did he enter into a counter-thesis bar (a poke)?
        bar_body = entry.c - entry.o
        confirmed_close = (bar_body >= 0) if is_call else (bar_body <= 0)

        near_level = _nearest_level_dist(bars, idx) <= NEAR_LEVEL_PCT * 100

        out.append({
            "date": r.date,
            "symbol": r.symbol,
            "underlier": r.underlier,
            "side": side,
            "bias": r.bias,
            "is_0dte": r.is_0dte,
            "qty": r.qty,
            "pnl": r.pnl,
            "is_win": r.pnl > 0,
            "entry_hhmm": entry_hhmm,
            "hold_min": r.hold_min,
            "pct_move": round(r.pct_move * 100, 1),     # realized premium move at exit
            # --- entry read (inferred) ---
            "time_bucket": feats["time_bucket"],
            "vwap_side": feats["vwap_side"],
            "vwap_dist_bp": vwap_dist_bp,
            "trigger": feats["trigger"],
            "archetype": feats["archetype"],
            "new_session_extreme": feats["new_session_extreme"],
            "open_drive_bucket": feats["open_drive_bucket"],
            "day_type": feats["day_type"],
            "prior_trend_30m_pct": feats["prior_trend_30m_pct"],
            # --- entry-quality candidates ---
            "vwap_aligned": vwap_aligned,
            "ext_from_vwap_bp": round(ext_from_vwap_bp, 1),
            "ext_from_open_pct": round(ext_from_open, 3),
            "stretched_atr": round(stretched_atr, 2),
            "confirmed_close": confirmed_close,
            "near_level": near_level,
            "entry_mae_pts": outcome.mae_pts,
            "entry_mae_prem_frac_est": outcome.mae_prem_frac_est,
            # --- forward thesis label (look-forward, defines GOOD/BAD) ---
            "fav_move_pts": outcome.fav_move_pts,
            "continued_meaningfully": outcome.continued_meaningfully,
            "adverse_first": outcome.adverse_first,
            "closed_adverse": outcome.closed_adverse,
            "good_thesis": outcome.good_thesis,
        })
    return out


# --------------------------------------------------------------------------- #
# PART A — entry-read distribution
# --------------------------------------------------------------------------- #
def part_a_distribution(recs: list[dict[str, Any]]) -> dict[str, Any]:
    def _tally(field: str) -> dict[str, int]:
        return dict(Counter(r[field] for r in recs).most_common())

    def _wr(field: str) -> dict[str, dict[str, Any]]:
        groups: dict[Any, list[dict]] = defaultdict(list)
        for r in recs:
            groups[r[field]].append(r)
        out = {}
        for k, g in groups.items():
            wins = sum(1 for x in g if x["is_win"])
            out[str(k)] = {
                "n": len(g),
                "win_rate_pct": round(100 * wins / len(g), 1),
                "avg_pnl": round(statistics.mean([x["pnl"] for x in g]), 1),
                "good_thesis_pct": round(100 * sum(1 for x in g if x["good_thesis"]) / len(g), 1),
            }
        return out

    return {
        "n_trades": len(recs),
        "n_winners": sum(1 for r in recs if r["is_win"]),
        "n_losers": sum(1 for r in recs if not r["is_win"]),
        "overall_win_rate_pct": round(100 * sum(1 for r in recs if r["is_win"]) / len(recs), 1),
        "overall_good_thesis_pct": round(100 * sum(1 for r in recs if r["good_thesis"]) / len(recs), 1),
        "by_vwap_alignment": _wr("vwap_aligned"),
        "by_trigger": _wr("trigger"),
        "by_archetype": _wr("archetype"),
        "by_time_bucket": _wr("time_bucket"),
        "by_confirmed_close": _wr("confirmed_close"),
        "by_near_level": _wr("near_level"),
        "by_new_session_extreme": _wr("new_session_extreme"),
        "tally_trigger": _tally("trigger"),
        "tally_archetype": _tally("archetype"),
        "tally_time_bucket": _tally("time_bucket"),
    }


# --------------------------------------------------------------------------- #
# PART B — discriminator analysis: GOOD-thesis vs BAD-thesis
# --------------------------------------------------------------------------- #
def _good_bad(recs: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    good = [r for r in recs if r["good_thesis"]]
    bad = [r for r in recs if not r["good_thesis"]]
    return good, bad


def _binary_discriminator(name: str, recs: list[dict[str, Any]],
                          pred) -> dict[str, Any]:
    """Test a boolean predicate as a TAKE-filter: among entries where pred is True
    (TAKE) vs False (AVOID), report good-thesis rate, win-rate, avg P&L, support.

    'separation' = good_thesis_rate(TAKE) - good_thesis_rate(AVOID).
    'wr_lift'    = win_rate(TAKE) - win_rate(AVOID).
    A clean TAKE-filter has high positive separation + wr_lift with decent support
    on both sides.
    """
    take = [r for r in recs if pred(r)]
    avoid = [r for r in recs if not pred(r)]
    if not take or not avoid:
        return {"name": name, "skipped": "degenerate split (all one side)"}

    def _stat(g):
        wins = sum(1 for x in g if x["is_win"])
        good = sum(1 for x in g if x["good_thesis"])
        return {
            "n": len(g),
            "win_rate_pct": round(100 * wins / len(g), 1),
            "good_thesis_pct": round(100 * good / len(g), 1),
            "avg_pnl": round(statistics.mean([x["pnl"] for x in g]), 1),
            "total_pnl": round(sum(x["pnl"] for x in g), 0),
        }

    ts, az = _stat(take), _stat(avoid)
    return {
        "name": name,
        "TAKE_side": ts,
        "AVOID_side": az,
        "good_thesis_separation_pp": round(ts["good_thesis_pct"] - az["good_thesis_pct"], 1),
        "win_rate_lift_pp": round(ts["win_rate_pct"] - az["win_rate_pct"], 1),
        "avg_pnl_lift": round(ts["avg_pnl"] - az["avg_pnl"], 1),
        # support weight = harmonic mean of the two side counts / total (penalises
        # tiny-support splits that look clean but are noise).
        "support_weight": round(
            2 * ts["n"] * az["n"] / (ts["n"] + az["n"]) / len(recs), 3),
    }


def part_b_discriminators(recs: list[dict[str, Any]]) -> dict[str, Any]:
    good, bad = _good_bad(recs)

    # Continuous-feature contrast: mean of each feature for GOOD vs BAD entries.
    cont_feats = ["ext_from_vwap_bp", "ext_from_open_pct", "stretched_atr",
                  "entry_mae_pts", "vwap_dist_bp", "prior_trend_30m_pct"]

    def _mean(g, f):
        vals = [x[f] for x in g if x[f] is not None]
        return round(statistics.mean(vals), 3) if vals else None

    def _median(g, f):
        vals = [x[f] for x in g if x[f] is not None]
        return round(statistics.median(vals), 3) if vals else None

    contrast = {}
    for f in cont_feats:
        contrast[f] = {
            "good_mean": _mean(good, f), "bad_mean": _mean(bad, f),
            "good_median": _median(good, f), "bad_median": _median(bad, f),
        }
    # premium MAE separately (estimate; only where solvable)
    contrast["entry_mae_prem_frac_est"] = {
        "good_mean": _mean(good, "entry_mae_prem_frac_est"),
        "bad_mean": _mean(bad, "entry_mae_prem_frac_est"),
        "good_median": _median(good, "entry_mae_prem_frac_est"),
        "bad_median": _median(bad, "entry_mae_prem_frac_est"),
        "_note": "ESTIMATE (BS, IV implied from entry fill); only solvable subset",
    }

    # Boolean / threshold discriminators ranked by separation.
    discs = [
        _binary_discriminator("vwap_aligned", recs, lambda r: r["vwap_aligned"]),
        _binary_discriminator("confirmed_close", recs, lambda r: r["confirmed_close"]),
        _binary_discriminator("near_level", recs, lambda r: r["near_level"]),
        _binary_discriminator("not_stretched (atr<2.5)", recs,
                              lambda r: r["stretched_atr"] < STRETCH_ATR_HI),
        _binary_discriminator("near_vwap (|dist|<=15bp)", recs,
                              lambda r: abs(r["vwap_dist_bp"]) <= 15),
        _binary_discriminator("not_chasing_open (ext<0.5%)", recs,
                              lambda r: r["ext_from_open_pct"] < 0.5),
        _binary_discriminator("morning (<11:00)", recs,
                              lambda r: int(r["entry_hhmm"][:2]) < 11),
        _binary_discriminator("trigger=pullback", recs,
                              lambda r: r["trigger"] == "pullback"),
        _binary_discriminator("trigger=breakout", recs,
                              lambda r: r["trigger"] == "breakout"),
        _binary_discriminator("not_reclaim (not counter-VWAP)", recs,
                              lambda r: r["trigger"] != "reclaim"),
        # composite TAKE filter: aligned AND not chasing-extended
        _binary_discriminator("aligned & not_stretched", recs,
                              lambda r: r["vwap_aligned"] and r["stretched_atr"] < STRETCH_ATR_HI),
        # composite TAKE: aligned AND near-vwap (the pullback-not-chase ideal)
        _binary_discriminator("aligned & near_vwap", recs,
                              lambda r: r["vwap_aligned"] and abs(r["vwap_dist_bp"]) <= 25),
        # composite TAKE: aligned AND confirmed close
        _binary_discriminator("aligned & confirmed_close", recs,
                              lambda r: r["vwap_aligned"] and r["confirmed_close"]),
    ]
    discs = [d for d in discs if "skipped" not in d]
    # rank by separation, support-weighted
    for d in discs:
        d["rank_score"] = round(
            (d["good_thesis_separation_pp"] + d["win_rate_lift_pp"]) *
            (0.5 + d["support_weight"]), 2)
    discs.sort(key=lambda d: d["rank_score"], reverse=True)

    # The timing/poke finding: does entering a hair EARLY (into a poke / unconfirmed
    # bar) cause a bigger immediate adverse excursion? Compare MAE by confirmed_close.
    conf = [r for r in recs if r["confirmed_close"]]
    unconf = [r for r in recs if not r["confirmed_close"]]
    poke_finding = {
        "_question": "Does entering before a confirming close cause a bigger poke?",
        "confirmed_close": {
            "n": len(conf),
            "median_mae_pts": _median(conf, "entry_mae_pts"),
            "mean_mae_pts": _mean(conf, "entry_mae_pts"),
            "median_mae_prem_frac_est": _median(conf, "entry_mae_prem_frac_est"),
            "win_rate_pct": round(100 * sum(1 for r in conf if r["is_win"]) / len(conf), 1) if conf else None,
            "good_thesis_pct": round(100 * sum(1 for r in conf if r["good_thesis"]) / len(conf), 1) if conf else None,
        },
        "unconfirmed_close": {
            "n": len(unconf),
            "median_mae_pts": _median(unconf, "entry_mae_pts"),
            "mean_mae_pts": _mean(unconf, "entry_mae_pts"),
            "median_mae_prem_frac_est": _median(unconf, "entry_mae_prem_frac_est"),
            "win_rate_pct": round(100 * sum(1 for r in unconf if r["is_win"]) / len(unconf), 1) if unconf else None,
            "good_thesis_pct": round(100 * sum(1 for r in unconf if r["good_thesis"]) / len(unconf), 1) if unconf else None,
        },
    }
    # Among the RIGHT-thesis trades (read was correct), did unconfirmed entries get
    # shaken harder (bigger poke) — i.e. the link between bad timing + the hold problem?
    rt = [r for r in recs if r["good_thesis"]]
    rt_conf = [r for r in rt if r["confirmed_close"]]
    rt_unconf = [r for r in rt if not r["confirmed_close"]]
    poke_finding["right_thesis_only"] = {
        "_note": "GOOD-thesis trades only — bigger poke here = harder to hold a correct read",
        "confirmed_median_mae_pts": _median(rt_conf, "entry_mae_pts"),
        "unconfirmed_median_mae_pts": _median(rt_unconf, "entry_mae_pts"),
        "confirmed_median_mae_prem_frac_est": _median(rt_conf, "entry_mae_prem_frac_est"),
        "unconfirmed_median_mae_prem_frac_est": _median(rt_unconf, "entry_mae_prem_frac_est"),
        "n_confirmed": len(rt_conf), "n_unconfirmed": len(rt_unconf),
    }

    return {
        "n_good_thesis": len(good),
        "n_bad_thesis": len(bad),
        "good_thesis_pct": round(100 * len(good) / len(recs), 1),
        "good_thesis_win_rate_pct": round(100 * sum(1 for r in good if r["is_win"]) / len(good), 1) if good else None,
        "bad_thesis_win_rate_pct": round(100 * sum(1 for r in bad if r["is_win"]) / len(bad), 1) if bad else None,
        "continuous_feature_contrast_good_vs_bad": contrast,
        "discriminators_ranked": discs,
        "timing_poke_finding": poke_finding,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="cache-only; do not hit Alpaca for the few uncached dates")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rts = load_roundtrips()
    if args.limit:
        rts = rts[: args.limit]
    all_dates = sorted({r.date for r in rts})
    print(f"loaded {len(rts)} spx-family closed round-trips over {len(all_dates)} dates")

    # union cache = winner + loser caches; pull any remaining misses (unless --no-fetch)
    cache = _load_cache(WINNER_CACHE)
    cache.update(_load_cache(LOSER_CACHE))
    missing = [d for d in all_dates if d not in cache]
    print(f"cache covers {len(all_dates) - len(missing)}/{len(all_dates)} dates "
          f"({len(missing)} missing)")
    if missing and not args.no_fetch:
        # reuse the loser cache builder to pull + persist the misses
        more = build_loser_cache(missing)
        cache.update(more)
        still = [d for d in all_dates if d not in cache]
        print(f"after fetch: {len(all_dates) - len(still)}/{len(all_dates)} covered")

    recs = build_records(rts, cache)
    print(f"built {len(recs)} entry-quality records "
          f"({sum(1 for r in recs if r['is_win'])} win / "
          f"{sum(1 for r in recs if not r['is_win'])} loss)")

    part_a = part_a_distribution(recs)
    part_b = part_b_discriminators(recs)

    payload = {
        "_generated": dt.datetime.now().isoformat(timespec="seconds"),
        "_what": "J's ENTRY-QUALITY analysis — reconstruct entry reads + GOOD vs BAD-thesis discriminators",
        "_honesty": {
            "behaviour": "EXACT — his real entry/exit fills, qty, P&L",
            "entry_read": "INFERRED — reconstructed look-ahead-free from SPY 5m tape (no notes)",
            "thesis_label": "EXACT direction — SPY underlying continued his way after entry (SPX/SPY ~10:1)",
            "premium_MAE": "ESTIMATE — BS, IV implied from his own entry fill (labelled _est)",
        },
        "params": {
            "meaningful_frac_of_spot": MEANINGFUL_FRAC,
            "mae_window_bars_5m": MAE_BARS,
            "near_level_pct": NEAR_LEVEL_PCT,
            "stretched_atr_hi": STRETCH_ATR_HI,
        },
        "universe": {
            "closed_roundtrips": len(rts),
            "records_built": len(recs),
            "dates": len(all_dates),
            "dates_covered": len(all_dates) - len([d for d in all_dates if d not in cache]),
        },
        "part_a_entry_read_distribution": part_a,
        "part_b_discriminators": part_b,
        "records": recs,
    }
    ENTRY_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"wrote {ENTRY_JSON}")

    # console headline
    print("\n" + "=" * 78)
    print(f"GOOD-thesis: {part_b['n_good_thesis']} ({part_b['good_thesis_pct']}%)  |  "
          f"BAD-thesis: {part_b['n_bad_thesis']}")
    print(f"GOOD-thesis WR: {part_b['good_thesis_win_rate_pct']}%  |  "
          f"BAD-thesis WR: {part_b['bad_thesis_win_rate_pct']}%")
    print("\nTOP DISCRIMINATORS (by separation + WR-lift, support-weighted):")
    print(f"  {'filter':34s} {'TAKE-WR':>8s} {'AVOID-WR':>9s} {'sep-pp':>7s} {'wr-lift':>8s} {'score':>7s}")
    for d in part_b["discriminators_ranked"][:10]:
        print(f"  {d['name']:34.34s} {d['TAKE_side']['win_rate_pct']:>8.1f} "
              f"{d['AVOID_side']['win_rate_pct']:>9.1f} "
              f"{d['good_thesis_separation_pp']:>7.1f} {d['win_rate_lift_pp']:>8.1f} "
              f"{d['rank_score']:>7.2f}")
    pf = part_b["timing_poke_finding"]
    print("\nPOKE / TIMING (confirmed vs unconfirmed entry-bar close):")
    print(f"  confirmed   n={pf['confirmed_close']['n']:4d}  median MAE pts={pf['confirmed_close']['median_mae_pts']}  WR={pf['confirmed_close']['win_rate_pct']}%")
    print(f"  unconfirmed n={pf['unconfirmed_close']['n']:4d}  median MAE pts={pf['unconfirmed_close']['median_mae_pts']}  WR={pf['unconfirmed_close']['win_rate_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
