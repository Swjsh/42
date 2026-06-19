"""BEARISH_REJECTION quality map — stratify J's ONE confirmed edge by CONDITION.

We have ONE edge-aligned entry: BEARISH_REJECTION_RIDE_THE_RIBBON, codified as the
`bearish_rejection_morning_watcher` (the BASELINE / PROMOTE-only variant in
validate_bearish_continuation_family.py). The leverage now is not adding more gates
blindly (the morning-sign / lunch gates failed as untethered hypotheses) but
characterizing WHEN this confirmed setup's REAL-FILLS outcomes concentrate — so we can
say take-full-size / size-down / skip from data, not from a fresh hypothesis.

This script does NOT add a detector or change any production knob (Rule 9, propose-only).
It reuses the validate_breakout_family harness verbatim (bootstrap, _load_data, per-bar
BarContext pipeline with historically-rebuilt levels, _grade, _stats) and the SAME
real-fills model as validate_bearish_continuation_family (simulate_trade_real, side=P,
qty=3, chart-stop only premium_stop_pct=-0.99, ATM offset 0 + ITM2 offset -2). It takes
EVERY bearish_rejection_morning fire over the window, tags each fill with its entry-time
CONDITIONS, then stratifies real-fills expectancy / WR / total / edge_capture by:

  1. VIX CHARACTER at entry: rising / falling / flat (vix_now vs vix 3 bars prior, +/-0.15
     deadband) x VIX LEVEL bucket (<15 / 15-20 / 20+). The production engine gates on
     "VIX rising"; this asks the data whether rising is actually best, and whether there
     is a level interaction.
  2. RIBBON SPREAD magnitude at entry (cents). The detector already excludes compressed
     ribbons implicitly (it needs a BEAR stack); among qualifying fires we bucket
     <30 / 30-50 / 50-80 / 80+ to ask whether a wider/cleaner ribbon = better.
  3. LEVEL TIER of the rejected level (PROXY, OP-20): the historically-rebuilt level set
     has no production ★★★/Carry labels, so we proxy tier by the level's evidence in the
     historical detector — multi_day (the strongest historical proxy, ~"Carry/★★★") vs
     active-only vs round-number ($X.00 within 10c). Disclosed as a proxy.
  4. TIME-OF-DAY bucket: 09:35-09:59 / 10:00-10:29 / 10:30-10:55 (the watcher's window is
     09:35-10:55). Prior research flagged the 10:00 hour bleeding and 11:00 green; the
     watcher never fires after 10:55 so we characterize precisely inside its window.
  5. DAY STRUCTURE: trend vs range, derived cheaply from the opening range (first 6 bars =
     09:30-10:00). trend_day = bar's close is already outside [OR_low, OR_high] in the
     setup direction (price has broken the OR down) at entry; range_day = still inside OR.
     This is a cheap, causal (as-of-entry) proxy, not a full end-of-day trend classifier.

EDGE_CAPTURE per bucket: sum of real-fills P&L on J's WIN anchor days (4/29, 5/01, 5/04)
minus sum(max(0,-pnl)) on J's LOSS anchor days (5/05, 5/06, 5/07) for fills landing in
that bucket. With only a handful of anchor days this is thin per bucket; reported with n.

OP-20 / honesty:
  * Real-fills authority: simulate_trade_real over OPRA bars. The OPRA cache ends
    ~2026-05-29 (latest contract date in backtest/data/options = SPY260529), so the
    REAL-FILLS window is effectively 2025-01-02 .. 2026-05-29, NOT the full 16 months
    through 2026-06-16. Fills beyond ~05-29 silently return no data (counted as no_fill).
    The SPY-space grade (grade_observation) IS available across the full window and is
    reported alongside as a directional proxy (lessons C1/C3: SPY edge != option edge).
  * Levels are historically-rebuilt ★★ proxies (active + multi_day from
    _detect_from_history as-of each day), NOT the production ★★★ named set. Tier
    stratification is therefore a PROXY. Disclosed.
  * Small-n per bucket is expected. Every bucket reports n; buckets with n < 8 are flagged
    low_power and must NOT drive a sizing/skip rule on their own.

Propose-only: the output flags the 1-2 highest-signal conditions worth PROPOSING as
quality-tier sizing or skip rules. It changes nothing live.

Usage:
  python -m autoresearch.stratify_bearish_rejection_quality --realfills \
      --out ../analysis/recommendations/bearish-rejection-quality-map.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the breakout-family harness wholesale (bootstrap, data, ctx, grading, stats).
from autoresearch import validate_breakout_family as vbf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.watchers import bearish_rejection_morning_watcher as _brm  # noqa: E402

# OP-16 anchors reused from the breakout-family module (single source of truth).
ANCHORS = vbf.ANCHORS  # {date: "WIN"|"LOSS"}
EOD = vbf.EOD
pd = vbf.pd

# Real-fills model — IDENTICAL to validate_bearish_continuation_family.
_OFFSETS = (("ATM", 0), ("ITM2", -2))
_VIX_DEADBAND = 0.15        # |vix_now - vix_prior| <= 0.15 => "flat"
_LOW_POWER_N = 8            # buckets with n < this are flagged low_power


# ──────────────────────────────────────────────────────────────────────────────
# Condition taggers (all computed AS-OF the entry bar — no look-ahead).
# ──────────────────────────────────────────────────────────────────────────────
def _vix_character(vix_now: float, vix_prior: float) -> str:
    d = vix_now - vix_prior
    if d > _VIX_DEADBAND:
        return "rising"
    if d < -_VIX_DEADBAND:
        return "falling"
    return "flat"


def _vix_level_bucket(vix_now: float) -> str:
    if vix_now < 15.0:
        return "<15"
    if vix_now < 20.0:
        return "15-20"
    return "20+"


def _spread_bucket(spread_cents: float) -> str:
    if spread_cents < 30.0:
        return "<30c"
    if spread_cents < 50.0:
        return "30-50c"
    if spread_cents < 80.0:
        return "50-80c"
    return "80c+"


def _level_tier_proxy(level: float, multi_day_levels: list[float],
                      active_levels: list[float]) -> str:
    """PROXY tier (OP-20). No production ★★★/Carry labels in the historical set.

    multi_day (level persisted across multiple sessions in _detect_from_history) is the
    strongest historical proxy for a ★★★/Carry level. Round-number = within 10c of $X.00.
    Otherwise active-only.
    """
    eps = 0.06
    if any(abs(level - m) <= eps for m in (multi_day_levels or [])):
        return "multi_day(~Carry/3star_proxy)"
    if abs(round(level) - level) <= 0.10:
        return "round_number"
    return "active_only"


def _tod_bucket(t: dt.time) -> str:
    if t < dt.time(10, 0):
        return "0935-0959"
    if t < dt.time(10, 30):
        return "1000-1029"
    return "1030-1055"


def _day_structure(spy_day: pd.DataFrame, entry_idx_in_day: int, entry_close: float) -> str:
    """trend vs range, cheap & causal: opening range = first 6 bars (09:30-10:00).

    For a bearish setup, trend_day = price has already broken BELOW the OR low by entry;
    range_day = entry close still inside [OR_low, OR_high]; reclaim_up = above OR high.
    Uses only bars up to and including the entry bar (no look-ahead).
    """
    if entry_idx_in_day < 6:
        # Not enough bars to define an OR yet — treat as opening (pre-OR).
        return "pre_OR"
    or_bars = spy_day.iloc[:6]
    or_low = float(or_bars["low"].min())
    or_high = float(or_bars["high"].max())
    if entry_close < or_low:
        return "trend_down(below_OR)"
    if entry_close > or_high:
        return "above_OR"
    return "range(inside_OR)"


# ──────────────────────────────────────────────────────────────────────────────
# Replay: collect every BEARISH_REJECTION_MORNING fire with condition tags + fills.
# ──────────────────────────────────────────────────────────────────────────────
def _collect(start: dt.date, end: dt.date, do_realfills: bool) -> dict:
    spy_full, vix_full = vbf._load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    # Per-day frames (for day-structure OR + entry index within day).
    day_groups = {d: g.reset_index(drop=True) for d, g in rth.groupby(rth["timestamp_et"].dt.date)}
    day_first_global_idx: dict = {}
    _seen = set()
    for gi, d in enumerate(rth["timestamp_et"].dt.date):
        if d not in _seen:
            day_first_global_idx[d] = gi
            _seen.add(d)

    fires: list[dict] = []      # one row per RAW fire, with tags + (idx,bar,sig) for real-fills
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue
        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]),
                                       slow=float(r["slow"]), stack=str(r["stack"]),
                                       spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]
        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        if bar_date != _lvl_date[0]:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            _lvl_cache[0] = _detect_from_history(full_history, bar_date)
            _lvl_date[0] = bar_date
        level_set = _lvl_cache[0]
        _update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )

        try:
            sig = _brm.detect_bearish_rejection_morning(ctx)
        except Exception as _e:
            sys.stderr.write(f"brm bar={bar_time}: {type(_e).__name__}: {_e}\n")
            sig = None
        if sig is None:
            continue

        # ── Condition tags (as-of entry) ──
        out, spy_pnl = vbf._grade(sig, rth, idx, bar_date)
        rej_level = float(sig.metadata.get("rejection_level") or sig.stop_price)
        day_df = day_groups.get(bar_date)
        entry_idx_in_day = idx - day_first_global_idx.get(bar_date, idx)
        fires.append({
            "idx": idx,
            "date": str(bar_date),
            "time": bar_time.strftime("%H:%M"),
            "is_anchor": bar_date in ANCHORS,
            "anchor_label": ANCHORS.get(bar_date),
            "conf": sig.confidence,
            "vix_now": round(vix_now, 2),
            "vix_prior": round(vix_prior, 2),
            "vix_character": _vix_character(vix_now, vix_prior),
            "vix_level_bucket": _vix_level_bucket(vix_now),
            "spread_cents": round(ribbon_state.spread_cents, 1),
            "spread_bucket": _spread_bucket(ribbon_state.spread_cents),
            "level_tier_proxy": _level_tier_proxy(rej_level, level_set.multi_day, level_set.active),
            "tod_bucket": _tod_bucket(bar_time.time()),
            "day_structure": _day_structure(day_df, entry_idx_in_day, float(bar["close"]))
                              if day_df is not None else "unknown",
            "rejection_body_cents": round(float(sig.metadata.get("rejection_body_cents") or 0.0), 1),
            "vol_ratio": round(float(sig.metadata.get("vol_ratio") or 0.0), 2),
            "spy_proxy_outcome": out,
            "spy_proxy_pnl": round(spy_pnl, 2),
            # real-fills filled lazily below:
            "_sig": sig, "_bar": bar, "_rej": rej_level,
        })

    # ── Real-fills per fire (ATM + ITM2) ──
    rf_window_max = None
    if do_realfills and fires:
        from lib.simulator_real import simulate_trade_real
        n_filled = {"ATM": 0, "ITM2": 0}
        n_nofill = {"ATM": 0, "ITM2": 0}
        for f in fires:
            sig = f["_sig"]
            for label, offset in _OFFSETS:
                try:
                    fill = simulate_trade_real(
                        entry_bar_idx=f["idx"], entry_bar=f["_bar"], spy_df=rth, ribbon_df=ribbon_df,
                        rejection_level=float(f["_rej"]), triggers_fired=sig.triggers_fired,
                        side="P", qty=3, setup=sig.setup_name,
                        premium_stop_pct=-0.99, strike_offset=offset)
                except Exception as _e:
                    sys.stderr.write(f"rf {label} {f['date']} {f['time']}: {type(_e).__name__}: {_e}\n")
                    fill = None
                if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                    f[f"rf_{label}_pnl"] = round(float(fill.dollar_pnl), 2)
                    f[f"rf_{label}_exit"] = fill.exit_reason
                    n_filled[label] += 1
                    if label == "ATM":
                        d = f["date"]
                        rf_window_max = d if rf_window_max is None or d > rf_window_max else rf_window_max
                else:
                    f[f"rf_{label}_pnl"] = None
                    n_nofill[label] += 1
        diag = {"n_fires": len(fires),
                "atm_filled": n_filled["ATM"], "atm_no_fill": n_nofill["ATM"],
                "itm2_filled": n_filled["ITM2"], "itm2_no_fill": n_nofill["ITM2"],
                "realfills_last_filled_date": rf_window_max}
    else:
        diag = {"n_fires": len(fires)}

    # strip the heavy carriers before returning
    for f in fires:
        f.pop("_sig", None); f.pop("_bar", None); f.pop("_rej", None)

    return {"fires": fires, "diagnostics": diag}


# ──────────────────────────────────────────────────────────────────────────────
# Stratification.
# ──────────────────────────────────────────────────────────────────────────────
def _bucket_stats(rows: list[dict], pnl_key: str) -> dict:
    """exp/WR/total/n over rows that have a non-None pnl under pnl_key, + anchor edge."""
    vals = [r for r in rows if r.get(pnl_key) is not None]
    n = len(vals)
    if n == 0:
        base = {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0}
    else:
        wins = sum(1 for r in vals if r[pnl_key] > 0)
        tot = sum(r[pnl_key] for r in vals)
        base = {"n": n, "wr": round(100 * wins / n, 1), "total": round(tot, 2),
                "exp": round(tot / n, 2)}
    # anchor edge_capture within this bucket (real money on J's days)
    win_pnl = sum(r[pnl_key] for r in vals if r.get("anchor_label") == "WIN")
    loss_loss = sum(max(0.0, -r[pnl_key]) for r in vals if r.get("anchor_label") == "LOSS")
    n_anchor = sum(1 for r in vals if r.get("is_anchor"))
    base["edge_capture"] = round(win_pnl - loss_loss, 2)
    base["n_anchor_fills"] = n_anchor
    base["low_power"] = n < _LOW_POWER_N
    return base


def _verdict_for_bucket(st: dict) -> str:
    """take_full / size_down / skip / insufficient — on REAL-FILLS exp (+ edge sign)."""
    if st["n"] == 0:
        return "no_real_fills"
    if st["low_power"]:
        # still report the lean, but flag power
        if st["exp"] > 0:
            return "lean_positive_LOW_POWER"
        if st["exp"] < 0:
            return "lean_negative_LOW_POWER"
        return "flat_LOW_POWER"
    if st["exp"] > 0 and st["edge_capture"] >= 0:
        return "TAKE_FULL"
    if st["exp"] > 0 and st["edge_capture"] < 0:
        return "TAKE_FULL_but_anchor_neg"
    if -20.0 <= st["exp"] <= 0:
        return "SIZE_DOWN(marginal)"
    return "SKIP(negative)"


def _stratify_one(fires: list[dict], key: str, pnl_key: str) -> dict:
    buckets: dict[str, list] = defaultdict(list)
    for f in fires:
        buckets[f[key]].append(f)
    out = {}
    for b in sorted(buckets):
        st = _bucket_stats(buckets[b], pnl_key)
        st["verdict"] = _verdict_for_bucket(st)
        out[b] = st
    return out


def _stratify_cross_vix(fires: list[dict], pnl_key: str) -> dict:
    """VIX character x VIX level interaction (the gate-relevant 2D cut)."""
    buckets: dict[str, list] = defaultdict(list)
    for f in fires:
        buckets[f"{f['vix_character']} / {f['vix_level_bucket']}"].append(f)
    out = {}
    for b in sorted(buckets):
        st = _bucket_stats(buckets[b], pnl_key)
        st["verdict"] = _verdict_for_bucket(st)
        out[b] = st
    return out


def _highest_signal(strat_atm: dict) -> list[dict]:
    """Pick the 1-2 highest-signal conditions worth PROPOSING (propose-only, Rule 9).

    Signal = a non-low-power bucket whose real-fills exp is strongly + or - AND whose sign
    agrees with its anchor edge_capture sign (or is exp-driven for skip). We rank by
    |exp| * sqrt(n) among non-low-power buckets and surface the best positive and the
    worst negative as proposable take-full / skip conditions.
    """
    cands = []
    for dim, buckets in strat_atm.items():
        for name, st in buckets.items():
            if st["n"] == 0 or st["low_power"]:
                continue
            score = abs(st["exp"]) * (st["n"] ** 0.5)
            cands.append({"dimension": dim, "bucket": name, "exp": st["exp"],
                          "wr": st["wr"], "n": st["n"], "edge_capture": st["edge_capture"],
                          "total": st["total"], "verdict": st["verdict"], "_score": score})
    best_pos = sorted([c for c in cands if c["exp"] > 0], key=lambda c: c["_score"], reverse=True)
    worst_neg = sorted([c for c in cands if c["exp"] < 0], key=lambda c: c["_score"], reverse=True)
    picks = []
    if best_pos:
        c = dict(best_pos[0]); c.pop("_score")
        c["proposal"] = (f"TAKE FULL-SIZE when {c['dimension']}={c['bucket']} "
                         f"(real-fills exp ${c['exp']}, WR {c['wr']}%, N={c['n']}).")
        picks.append(c)
    if worst_neg:
        c = dict(worst_neg[0]); c.pop("_score")
        c["proposal"] = (f"SIZE DOWN / SKIP when {c['dimension']}={c['bucket']} "
                         f"(real-fills exp ${c['exp']}, WR {c['wr']}%, N={c['n']}).")
        picks.append(c)
    return picks


# ──────────────────────────────────────────────────────────────────────────────
# Validation layer (added 2026-06-19): OOS sign-stability + combined conditioned
# book + confidence-tier root-cause. Operates on the SAME `fires` rows the
# stratifier already builds (each carries date / vix_character / tod_bucket / conf
# / rejection_body_cents / vol_ratio / rf_ATM_pnl / rf_ITM2_pnl / anchor_label), so
# it can run either inline after a replay or `--analyze-from` an existing artifact
# (reproducible, no 16-month re-replay needed). Propose-only (Rule 9).
# ──────────────────────────────────────────────────────────────────────────────
def _psr_block(pnls: list[float], n_trials: int = 7) -> dict:
    """PSR(>0) + DSR + one-sided t-test on a per-trade P&L stream. Advisory colour.

    Reuses lib.validation.deflated_sharpe (Bailey & Lopez de Prado). low_power when
    n < MIN_RELIABLE_OBS (=20). DSR deflates for n_trials independent cuts swept.
    """
    import numpy as _np
    from scipy import stats as _ss
    from lib.validation.deflated_sharpe import (
        probabilistic_sharpe_ratio, deflated_sharpe_ratio, MIN_RELIABLE_OBS)
    a = _np.asarray([p for p in pnls if p is not None], dtype=float)
    n = int(a.size)
    if n < 2:
        return {"n": n, "mean": None, "sharpe": None, "psr_gt0": None,
                "dsr": None, "t": None, "p_one_sided_gt0": None, "low_power": True}
    mu = float(a.mean()); sd = float(a.std(ddof=0))
    sr = mu / sd if sd > 0 else 0.0
    sk = float(_ss.skew(a, bias=True)); ku = float(_ss.kurtosis(a, fisher=False, bias=True))
    psr = probabilistic_sharpe_ratio(sharpe=sr, n_obs=n, skew=sk, kurtosis=ku, sharpe_benchmark=0.0)
    dsr = deflated_sharpe_ratio(a, n_trials=n_trials)
    t, p = _ss.ttest_1samp(a, 0.0)
    p1 = (p / 2) if t > 0 else (1 - p / 2)        # P(mean > 0) one-sided
    return {"n": n, "mean": round(mu, 2), "sharpe": round(sr, 4),
            "psr_gt0": round(float(psr.psr), 4), "dsr": round(float(dsr.dsr), 4),
            "t": round(float(t), 3), "p_one_sided_gt0": round(float(p1), 4),
            "low_power": bool(n < MIN_RELIABLE_OBS)}


def _book_stats(rows: list[dict], pnl_key: str) -> dict:
    """exp/WR/total/edge_capture/n for an arbitrary subset (the 'conditioned book')."""
    st = _bucket_stats(rows, pnl_key)
    return {k: st[k] for k in ("n", "wr", "total", "exp", "edge_capture",
                               "n_anchor_fills", "low_power")}


def _oos_split(fires: list[dict], pnl_key: str) -> dict:
    """Sign-stability of the two proposable rules across IS/OOS, two split methods.

    Split 1: calendar 2025 (IS) vs 2026 (OOS).
    Split 2: balanced median-fill-date (half the FILLED rows each side).
    A rule is sign-stable iff its bucket exp keeps the SAME sign in BOTH halves of a split.
    """
    filled = sorted([f for f in fires if f.get(pnl_key) is not None],
                    key=lambda f: (f["date"], f["time"]))
    if not filled:
        return {"note": "no real fills under " + pnl_key}
    dates = [f["date"] for f in filled]
    median_date = dates[len(dates) // 2]

    splits = {
        "calendar_2025_vs_2026": {
            "IS": [f for f in filled if f["date"] < "2026-01-01"],
            "OOS": [f for f in filled if f["date"] >= "2026-01-01"],
            "boundary": "2026-01-01",
        },
        "balanced_median_date": {
            "IS": [f for f in filled if f["date"] < median_date],
            "OOS": [f for f in filled if f["date"] >= median_date],
            "boundary": median_date,
        },
    }

    def _bucket(rows, pred):
        return _book_stats([f for f in rows if pred(f)], pnl_key)

    rules = {
        "vix_falling_skip": lambda f: f["vix_character"] == "falling",
        "vix_rising_take":  lambda f: f["vix_character"] == "rising",
        "tod_1000_1029":    lambda f: f["tod_bucket"] == "1000-1029",
        "tod_1030_1055":    lambda f: f["tod_bucket"] == "1030-1055",
    }

    out = {}
    for sp_name, sp in splits.items():
        sp_out = {"boundary": sp["boundary"]}
        for r_name, pred in rules.items():
            is_st = _bucket(sp["IS"], pred)
            oos_st = _bucket(sp["OOS"], pred)
            # sign agreement on exp (treat exact-0 / empty as non-informative)
            si, so = is_st["exp"], oos_st["exp"]
            if is_st["n"] == 0 or oos_st["n"] == 0:
                stable = "no_data_one_half"
            elif (si > 0 and so > 0) or (si < 0 and so < 0):
                stable = "SAME_SIGN"
            else:
                stable = "SIGN_FLIP"
            sp_out[r_name] = {"IS": is_st, "OOS": oos_st, "sign_stability": stable}
        out[sp_name] = sp_out
    return out


def _combined_book(fires: list[dict], pnl_key: str) -> dict:
    """Net real-fills book under candidate skip/select rules vs baseline.

    The prize question: does conditioning turn the BEARISH_REJECTION book positive?
    Each variant reports exp/WR/total/edge_capture/n + PSR/DSR colour. edge_capture
    here is dominated by the single 4/29 anchor WIN fill (see op20 anchor caveat),
    so a variant that drops 4/29 shows edge_capture collapse = anchor regression flag.
    """
    filled = [f for f in fires if f.get(pnl_key) is not None]

    def book(pred):
        rows = [f for f in filled if pred(f)]
        st = _book_stats(rows, pnl_key)
        st["psr"] = _psr_block([f[pnl_key] for f in rows])
        return st

    variants = {
        "baseline_all": book(lambda f: True),
        "A_skip_vix_falling": book(lambda f: f["vix_character"] != "falling"),
        "B_skip_tod_1030plus": book(lambda f: f["tod_bucket"] != "1030-1055"),
        "AB_skip_both": book(lambda f: f["vix_character"] != "falling"
                                       and f["tod_bucket"] != "1030-1055"),
        "R_take_only_vix_rising": book(lambda f: f["vix_character"] == "rising"),
        "R_rising_and_not_late": book(lambda f: f["vix_character"] == "rising"
                                                 and f["tod_bucket"] != "1030-1055"),
    }
    # Anchor-regression flag: does the variant still include the 4/29 WIN anchor fill?
    for name, st in variants.items():
        st["keeps_anchor_win_fill"] = st["n_anchor_fills"] >= 1
    return variants


def _confidence_drivers(fires: list[dict], pnl_key: str) -> dict:
    """Root-cause the confidence-tier surprise: HIGH underperforms LOW on real fills.

    Reports, per tier: stats + median rejection_body / vol_ratio + the regime/time mix.
    Then a body-magnitude sweep to test whether 'bigger rejection bar = worse entry'
    (chart-stop sits just above the level, so a large-body bar enters far from the stop —
    more $ at risk; a normal retrace stops it). Disclosed as a detector-scoring finding.
    """
    import statistics as _st
    filled = [f for f in fires if f.get(pnl_key) is not None]

    tiers = {}
    for c in ("high", "medium", "low"):
        rows = [f for f in filled if f["conf"] == c]
        st = _book_stats(rows, pnl_key)
        bodies = [f.get("rejection_body_cents") or 0.0 for f in rows]
        vols = [f.get("vol_ratio") or 0.0 for f in rows]
        vc, td = defaultdict(int), defaultdict(int)
        for f in rows:
            vc[f["vix_character"]] += 1
            td[f["tod_bucket"]] += 1
        st["median_rejection_body_cents"] = round(_st.median(bodies), 1) if bodies else 0.0
        st["median_vol_ratio"] = round(_st.median(vols), 2) if vols else 0.0
        st["vix_character_mix"] = dict(vc)
        st["tod_mix"] = dict(td)
        tiers[c] = st

    body_buckets = {}
    for lo, hi, lab in ((0, 30, "<30c"), (30, 60, "30-60c"),
                        (60, 120, "60-120c"), (120, 10**9, "120c+")):
        rows = [f for f in filled
                if lo <= (f.get("rejection_body_cents") or 0.0) < hi]
        body_buckets[lab] = _book_stats(rows, pnl_key)

    # Spearman rank corr between rejection_body_cents and pnl (sign of the bug).
    corr = None
    try:
        from scipy import stats as _ss
        xs = [f.get("rejection_body_cents") or 0.0 for f in filled]
        ys = [f[pnl_key] for f in filled]
        if len(xs) > 5:
            rho, p = _ss.spearmanr(xs, ys)
            corr = {"spearman_rho_body_vs_pnl": round(float(rho), 4),
                    "p": round(float(p), 4), "n": len(xs)}
    except Exception:
        corr = None

    return {
        "tiers": tiers,
        "body_magnitude_sweep": body_buckets,
        "body_vs_pnl_correlation": corr,
        "scoring_rule": ("HIGH := rejection_body>=30c AND vol_ratio>=2.5x AND bear_candle "
                         "(bearish_rejection_morning_watcher.py L146). The HIGH gate rewards "
                         "the LARGEST/most-violent rejection bars; on real fills these enter "
                         "farthest from the chart-stop (stop = level+0.25) so a normal retrace "
                         "stops them out. The score therefore ANTI-correlates with realized "
                         "edge (lesson C3: SPY-structure edge != option edge; lesson C13: "
                         "confidence tiers must track realized P&L)."),
    }


def _validation_layer(fires: list[dict]) -> dict:
    """Bundle OOS-split + combined-book + confidence-driver for ATM (primary) + ITM2."""
    out = {}
    for label, pnl_key in (("ATM", "rf_ATM_pnl"), ("ITM2", "rf_ITM2_pnl")):
        out[label] = {
            "oos_sign_stability": _oos_split(fires, pnl_key),
            "combined_conditioned_book": _combined_book(fires, pnl_key),
            "confidence_tier_rootcause": _confidence_drivers(fires, pnl_key),
        }
    return out


def _verdicts() -> dict:
    """Propose-only verdicts (Rule 9) synthesised from the validation layer.

    Hardcoded prose conclusions are NOT auto-derived — they are written by the analyst
    after reading the numbers (the script computes the numbers; the analyst owns the
    PROPOSE/WATCH/REJECT call). Stored here so the scorecard is self-contained.
    """
    return {
        "vix_falling_skip": {
            "verdict": "PROPOSE (skip / size-to-zero)",
            "basis": ("VIX-falling is negative in BOTH halves of BOTH splits "
                      "(ATM: 2025 -$143 / 2026 -$311; medianA -$111 / medianB -$283; "
                      "ITM2 2025 -$185 / 2026 -$432). PSR(>0)=0.008, t=-3.15. Sign-stable "
                      "negative and the mirror of the proven VIX-rising-positive gate "
                      "(lesson C5: VIX character > level). n=11 total is low_power so "
                      "propose as SKIP, not as a sized rule."),
            "caveat": ("Skipping falling alone does NOT make the book positive (skip-falling "
                       "book exp still -$18.9, PSR 0.17). It removes the worst tail, not the "
                       "negative drift — the VIX-flat majority bucket also bled in OOS."),
        },
        "time_tier_1000_1029_full_1030_down": {
            "verdict": "REJECT (early-window full-size) / WATCH (late-window de-emphasis)",
            "basis": ("The 10:00-10:29 'take-full' edge SIGN-FLIPS OOS: IS +$112 (N=11) -> "
                      "OOS -$30 (N=3). The entire positive came from 2025 — textbook L166 "
                      "single-window artifact. In-sample t=2.05/p=0.03 is a selection mirage "
                      "(low_power n=14). REJECT it as a full-size rule. The 10:30+ 'bleed' is "
                      "negative in OOS (-$90, N=43) but was ~flat IS (-$5) so it is not cleanly "
                      "sign-stable either — WATCH, do not ship."),
        },
        "confidence_tier": {
            "verdict": "FLAG — detector confidence score does NOT track realized edge (mis-ranked)",
            "basis": ("HIGH-conf real-fills exp -$83 < MEDIUM -$27 < LOW -$15 (ATM): the tier "
                      "ordering is inverted vs P&L. HIGH is gated on body>=30c AND vol>=2.5x AND "
                      "bear_candle => median HIGH fire is a 131c-body / 3.4x-vol violent rejection "
                      "bar. NOTE: body magnitude ALONE is ~uncorrelated with pnl (Spearman rho "
                      "+0.04, p=0.61) — so it is the CONJUNCTION that mis-ranks, compounded by "
                      "regime clustering: 82% of HIGH fires land in the worst 10:30+ window and "
                      "most are VIX-flat. Plausible mechanical contributor: a big-body bar enters "
                      "farther above the chart-stop (level+0.25), so a normal retrace stops it. "
                      "Net: the confidence score is not a usable sizing signal as built; a detector "
                      "fix should re-rank by realized edge (lesson C13) — at minimum, do not size UP "
                      "on HIGH. Flag only (Rule 9)."),
        },
        "overall_book": {
            "verdict": "BEARISH_REJECTION real-fills book is NEGATIVE and NO conditioning tested "
                       "makes it cleanly, robustly positive.",
            "basis": ("Baseline ATM exp -$32.8 (PSR(>0)=0.04, significantly negative). The ONLY "
                      "variant that crosses zero is take-ONLY-VIX-rising (+$53, WR 83%) but it is "
                      "(a) not significant (PSR 0.84 < 0.95, DSR 0.35) and (b) drops the 4/29 "
                      "anchor WIN fill (edge_capture -> 0 = anchor regression, violates OP-16). "
                      "ITM2 rising-only is only breakeven (-$0.69) — the lean does NOT transfer "
                      "to the Bold strike tier (lesson C29). Net: refine by SKIPPING VIX-falling "
                      "as a do-no-harm tail trim; do NOT treat rising-only as a shippable edge."),
        },
    }


def _op20() -> dict:
    return {
        "authority": ("Real-fills (simulate_trade_real over OPRA bars) is the WR/expectancy "
                      "authority. SPY-space grade_observation is a directional proxy only "
                      "(lessons C1/C3: SPY edge != option edge)."),
        "realfills_window": ("OPRA contract cache ends ~2026-05-29 (latest file date "
                             "SPY260529 in backtest/data/options). The REAL-FILLS window is "
                             "therefore ~2025-01-02..2026-05-29, NOT the full 16 months through "
                             "2026-06-16. Fires after ~05-29 return no OPRA data (counted "
                             "no_fill). SPY-space strat covers the full window for context."),
        "levels": ("Historically-rebuilt level proxies (active + multi_day from "
                   "_detect_from_history as-of each day), NOT the production star/Carry named "
                   "set. level_tier_proxy is a PROXY: multi_day ~ Carry/3star; round_number = "
                   "within 10c of $X.00; else active_only. Disclosed per OP-20."),
        "small_n": (f"Per-bucket n is small; buckets with n < {_LOW_POWER_N} are flagged "
                    "low_power and must NOT drive a sizing/skip rule alone. Anchor-day fills "
                    "per bucket are tiny (3 WIN + 3 LOSS anchor days total) so per-bucket "
                    "edge_capture is directional, not conclusive."),
        "as_of": ("All condition tags (VIX character/level, spread, tier, time, day "
                  "structure) are computed AS-OF the entry bar — no look-ahead (lessons C6)."),
        "scope": ("Stratification of the ONE confirmed edge (bearish_rejection_morning = "
                  "BEARISH_REJECTION_RIDE_THE_RIBBON). NOT a new detector; no production knob "
                  "changed (Rule 9, propose-only)."),
    }


def build(start: dt.date, end: dt.date, do_realfills: bool) -> dict:
    coll = _collect(start, end, do_realfills)
    fires = coll["fires"]
    dims = ["vix_character", "vix_level_bucket", "spread_bucket",
            "level_tier_proxy", "tod_bucket", "day_structure", "conf"]

    # ATM real-fills is the primary authority (anchor strike class); ITM2 is the Bold class.
    strat_atm = {d: _stratify_one(fires, d, "rf_ATM_pnl") for d in dims}
    strat_atm["vix_character_x_level"] = _stratify_cross_vix(fires, "rf_ATM_pnl")
    strat_itm2 = {d: _stratify_one(fires, d, "rf_ITM2_pnl") for d in dims}
    strat_spy = {d: _stratify_one(fires, d, "spy_proxy_pnl") for d in dims}

    overall_atm = _bucket_stats(fires, "rf_ATM_pnl")
    overall_itm2 = _bucket_stats(fires, "rf_ITM2_pnl")
    overall_spy = _bucket_stats(fires, "spy_proxy_pnl")

    highest = _highest_signal(strat_atm)

    result = {
        "generated_at": dt.datetime.now().isoformat(),
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON (bearish_rejection_morning_watcher)",
        "window_requested": f"{start}..{end}",
        "purpose": ("Quality map: stratify the ONE confirmed edge-aligned entry's REAL-FILLS "
                    "outcomes by condition (VIX character/level, ribbon spread, level tier, "
                    "time-of-day, day structure) to say take-full / size-down / skip from "
                    "data. Propose-only (Rule 9)."),
        "diagnostics": coll["diagnostics"],
        "overall": {
            "real_fills_ATM": overall_atm,
            "real_fills_ITM2": overall_itm2,
            "spy_proxy_full_window": overall_spy,
        },
        "stratification_real_fills_ATM": strat_atm,
        "stratification_real_fills_ITM2": strat_itm2,
        "stratification_spy_proxy_full_window": strat_spy,
        "highest_signal_proposals": highest,
        "validation_layer": _validation_layer(fires),
        "propose_only_verdicts": _verdicts(),
        "fires": fires,
        "op20_disclosures": _op20(),
    }
    return result


def build_validation_scorecard(fires: list[dict], source: str) -> dict:
    """Self-contained validation scorecard from an existing fires array.

    Used by `--analyze-from <quality-map.json>` so the OOS / combined-book / confidence
    analysis is reproducible off a frozen artifact without re-running the 16-month replay.
    """
    return {
        "generated_at": dt.datetime.now().isoformat(),
        "kind": "bearish_rejection_quality_validation",
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON (bearish_rejection_morning_watcher)",
        "source_artifact": source,
        "purpose": ("OOS sign-stability + combined conditioned-book + confidence-tier "
                    "root-cause for the two proposable quality rules (VIX-falling-skip, "
                    "time-tier). Converts the quality map into validated propose/reject "
                    "edge-refinements. Propose-only (Rule 9)."),
        "n_fires": len(fires),
        "n_filled_ATM": sum(1 for f in fires if f.get("rf_ATM_pnl") is not None),
        "n_filled_ITM2": sum(1 for f in fires if f.get("rf_ITM2_pnl") is not None),
        "validation_layer": _validation_layer(fires),
        "propose_only_verdicts": _verdicts(),
        "op20_disclosures": _op20(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--realfills", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--analyze-from", default=None,
                    help="Read fires[] from an existing quality-map JSON and emit ONLY the "
                         "validation scorecard (OOS-split + combined-book + conf root-cause). "
                         "Reproducible — no 16-month replay.")
    a = ap.parse_args()

    if a.analyze_from:
        src = Path(a.analyze_from)
        if not src.is_absolute():
            src = (Path.cwd() / src).resolve()
        fires = json.loads(src.read_text(encoding="utf-8")).get("fires", [])
        res = build_validation_scorecard(fires, source=str(src))
        print(json.dumps(res, indent=2, default=str))
        if a.out:
            outp = Path(a.out)
            if not outp.is_absolute():
                outp = (Path.cwd() / outp).resolve()
            outp.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
            print("wrote", outp)
        return 0

    res = build(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), a.realfills)
    txt = json.dumps(res, indent=2, default=str)
    # Print a compact human summary to stdout; full JSON goes to --out.
    print(json.dumps({k: v for k, v in res.items() if k != "fires"}, indent=2, default=str))
    if a.out:
        outp = Path(a.out)
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.write_text(txt, encoding="utf-8")
        print("wrote", outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
