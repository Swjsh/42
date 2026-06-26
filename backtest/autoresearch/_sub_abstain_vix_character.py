"""SUBTRACTIVE abstention study: VIX *CHARACTER* (slope) vs VIX *level* tercile.

THESIS (CLAUDE.md C5 — "VIX *character* > VIX *level*"; the selection campaign's one
SUBTRACTIVE win = ``skip_top_tercile_only`` cleared all 8 gates -> OOS +$142/tr,
maxDD -$424). This study asks the NEXT C5 question on REAL OPRA fills:

    Does abstaining from vwap_continuation entries by VIX CHARACTER (the as-of
    5-bar VIX SLOPE agreeing with the trade) beat the LEVEL-tercile skip?

VIX-character abstention rule (as-of, look-ahead-safe — slope read AT the entry bar):
    * CALL (bullish) is taken ONLY when VIX is FALLING (5-bar slope < 0) — risk-on,
      vol bleeding lower = the regime calls win in.
    * PUT  (bearish) is taken ONLY when VIX is RISING (5-bar slope > 0) — risk-off,
      vol expanding = the regime puts win in.
    * SKIP every entry whose VIX character CONTRADICTS the trade (calls into rising
      VIX, puts into falling VIX). This is pure SUBTRACTION of bad-regime entries —
      the same shape as the campaign survivor, but keyed on CHANGE not LEVEL.
    * Two variants reported (no cherry-pick): LOOSE keeps slope==0 (flat) on the
      with-trade side; STRICT also skips flat (demands a real character agreement).

NULLS THIS GATE MUST BEAT (the comparison the task asks for):
    * ungated baseline (full vwap_continuation signal set, survivor config).
    * skip_top_tercile_only — the campaign survivor: SKIP entries whose entry_VIX is
      in the WORST (top/highest) tercile of the in-sample VIX level distribution
      (terciles computed on the FULL sample's entry_VIX; an entry is dropped if its
      entry_VIX > the 2/3 quantile). Reproduced here as the level-skip benchmark.
    * INVERSE character gate (take ONLY contra-character entries) — the L166 causality
      cross-check: a real character edge must make its INVERSE materially WORSE, and the
      inverse's sign must be OOS-stable in the OPPOSITE direction. If the inverse also
      looks fine, the "edge" is not character.

CONFIG (FIXED, no drift — C14): SURVIVOR structure strike_offset=-2 (ITM-2) PRIMARY,
premium_stop_pct=-0.08, v15 default exits. Per C29 (gates don't transfer across strike
tiers) the FULL gate panel is ALSO re-run at strike_offset=+2 (OTM-2 = Safe-2's actual
$2K tier) and reported side-by-side.

Detector: BYTE-FOR-BYTE the validated vwap_continuation detector, imported from
``_edgehunt_vwap_continuation`` (no drift). Signals detected ONCE; every gate is a
PARTITION of that same set re-simulated on the SAME real-fills path -> isolates the
gate's NET effect (per-trade lift vs total P&L kept).

ALL 8 MANDATORY GATES (anti-2.10, no cherry-pick), applied to the CHARACTER gate at
EACH strike tier:
    G1 OOS(2026) per-trade > 0
    G2 positive_quarters >= 4/6
    G3 top5_day_pct < 200
    G4 n >= 20
    G5 drop-top5 per-trade > 0   (concentration-robust)
    G6 IS(2025) first-HALF per-trade > 0   (in-sample stability)
    G7 beats random-entry NULL (L172, ~20 seeds; same days+sides + a pure coin-flip)
    G8 no-truncation (L171): per-trade SIGN holds from -8% stop -> chart-stop-only -0.99

Fills authority: real OPRA via lib.simulator_real.simulate_trade_real (C1).
Pure Python, $0 (no LLM, no live orders). Markets CLOSED (weekend).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_abstain_vix_character.py
Writes analysis/recommendations/sub-abstain-vix-character.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# REUSE the validated detector + data normalizers (byte-for-byte signal set, no drift).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals,
    _normalize_spy,
    _align_vix,
    _vix_slope,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-abstain-vix-character.json"

# ── SURVIVOR config (FIXED) ─────────────────────────────────────────────────────
PRIMARY_STRIKE_OFFSET = -2     # ITM-2 (survivor structure)
SECONDARY_STRIKE_OFFSET = +2   # OTM-2 (Safe-2 actual $2K tier; C29 cross-check)
SURV_PREMIUM_STOP = -0.08      # -8% premium stop
CHART_STOP_ONLY = -0.99        # no-truncation fraud cell

VIX_SLOPE_LOOK = 5             # 5-bar as-of slope (the C5 character window)
TOP_TERCILE_Q = 2.0 / 3.0     # entry_VIX above the 2/3 quantile = WORST level tercile
N_NULL_SEEDS = 20             # L172


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set at a (strike,stop). v15 default exits.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset,
                 premium_stop_pct=SURV_PREMIUM_STOP) -> tuple[list[TradeRow], dict]:
    """Real-fills sim of a signal subset at one (strike,stop)."""
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="JVWAP_VIXCHAR", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side,
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            trig=sg.note,
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure block)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day_top5_pct(rows: list[TradeRow]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_topN_day_per_trade(rows: list[TradeRow], k: int = 5) -> Optional[float]:
    """Per-trade mean after removing the k highest-P&L *days* entirely."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _is_first_half_per_trade(rows: list[TradeRow]) -> Optional[float]:
    """G6: per-trade mean over the FIRST HALF of the IS(2025) trades (chronological).

    In-sample stability: split the IS(2025) trades in two by date order; the EARLIER
    half must be positive on its own (the edge isn't a single late-IS run)."""
    is_rows = sorted((r for r in rows if int(r.date[:4]) != OOS_YEAR), key=lambda r: r.date)
    if len(is_rows) < 2:
        return None
    half = len(is_rows) // 2
    first = is_rows[:half]
    return round(float(np.mean([r.pnl for r in first])), 2) if first else None


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    # max drawdown on the chronological per-trade equity curve
    eq = np.cumsum(pnl[np.argsort([r.date for r in rows])])
    running_max = np.maximum.accumulate(eq)
    max_dd = round(float(np.min(eq - running_max)), 2) if len(eq) else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown": max_dd,
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_per_trade": _is_first_half_per_trade(rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# FRAUD GATE — random-entry null (G7). Two flavors:
#   (a) same-day, same-side random morning entry (the HARD control — isolates trigger
#       precision over an arbitrary morning entry on a day already on the right side).
#   (b) pure coin-flip: random day + random side + random morning bar (the SOFT control
#       — isolates the whole signal from the exit bracket).
# A real signal must beat the same-day null mean+1std AND the coin-flip null MAX.
# ─────────────────────────────────────────────────────────────────────────────
def random_null(signals, spy, ribbon, vix, days, *, strike_offset,
                seeds=N_NULL_SEEDS, premium_stop_pct=SURV_PREMIUM_STOP) -> dict:
    # date -> eligible morning RTH global idxs
    day_bars: dict[dt.date, list[int]] = {}
    all_elig: list[int] = []
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(TREND_BARS, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
            all_elig.extend(elig)
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))
    n_sig = len(sig_specs)
    n_call = sum(1 for _, sd, _ in sig_specs if sd == "C")
    n_put = n_sig - n_call

    sameday_exp, sameday_oos = [], []
    coin_exp, coin_oos = [], []
    for seed in range(seeds):
        # (a) same-day, same-side
        rng = np.random.default_rng(1000 + seed)
        rs = []
        for d, side, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            rs.append(Signal(bar_idx=int(rng.choice(elig)), side=side,
                             stop_level=stop, note="rand_sameday"))
        rows, _ = simulate_set(rs, spy, ribbon, vix, strike_offset=strike_offset,
                               premium_stop_pct=premium_stop_pct)
        if rows:
            m = metrics(rows)
            sameday_exp.append(m["exp_dollar"]); sameday_oos.append(m["oos_exp"])
        # (b) pure coin-flip: random day+bar+side, preserve overall side mix
        rng2 = np.random.default_rng(5000 + seed)
        sides = np.array(["C"] * n_call + ["P"] * n_put)
        rng2.shuffle(sides)
        rc = []
        if all_elig:
            picks = rng2.choice(all_elig, size=n_sig, replace=True)
            for k in range(n_sig):
                bidx = int(picks[k])
                side = sides[k] if k < len(sides) else "C"
                bar = spy.iloc[bidx]
                # generic chart stop from prior 12 bars (matches null_baseline geometry)
                lo = max(0, bidx - 11)
                win = spy.iloc[lo: bidx + 1]
                c = float(bar["close"])
                if side == "C":
                    rej = float(win["low"].min()); rej = rej if rej < c else c - 1.0
                else:
                    rej = float(win["high"].max()); rej = rej if rej > c else c + 1.0
                rc.append(Signal(bar_idx=bidx, side=side, stop_level=round(rej, 2),
                                 note="coinflip"))
        rows2, _ = simulate_set(rc, spy, ribbon, vix, strike_offset=strike_offset,
                                premium_stop_pct=premium_stop_pct)
        if rows2:
            m2 = metrics(rows2)
            coin_exp.append(m2["exp_dollar"]); coin_oos.append(m2["oos_exp"])

    def _agg(xs):
        if not xs:
            return {"seeds": 0}
        a = np.array(xs, float)
        return {"seeds": len(xs), "mean": round(float(a.mean()), 2),
                "min": round(float(a.min()), 2), "max": round(float(a.max()), 2),
                "std": round(float(a.std()), 2)}

    return {
        "sameday_sameside": {**_agg(sameday_exp),
                             "oos_mean": round(float(np.mean(sameday_oos)), 2) if sameday_oos else None},
        "coinflip": {**_agg(coin_exp),
                     "oos_mean": round(float(np.mean(coin_oos)), 2) if coin_oos else None},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Partition + full gate-panel evaluation for ONE strike tier
# ─────────────────────────────────────────────────────────────────────────────
def partition(signals, predicate: Callable[[Signal], bool]) -> list:
    return [s for s in signals if predicate(s)]


def eval_panel(name, desc, kept, spy, ribbon, vix, days, base_m, *,
               strike_offset, run_fraud=True) -> dict:
    rows, cov = simulate_set(kept, spy, ribbon, vix, strike_offset=strike_offset)
    m = metrics(rows)
    block = {"gate": name, "desc": desc, "strike_offset": strike_offset,
             "n_signals_kept": len(kept), "coverage": cov, "metrics": m}
    if m.get("n"):
        block["vs_baseline"] = {
            "oos_per_trade_lift": round((m.get("oos_exp", 0) or 0) - (base_m.get("oos_exp", 0) or 0), 2),
            "oos_total_kept_frac": (round((m.get("oos_total", 0) or 0) / base_m["oos_total"], 3)
                                    if base_m.get("oos_total") else None),
            "maxdd_delta": round((m.get("max_drawdown", 0) or 0) - (base_m.get("max_drawdown", 0) or 0), 2),
        }
    if run_fraud and m.get("n"):
        cs_rows, _ = simulate_set(kept, spy, ribbon, vix, strike_offset=strike_offset,
                                  premium_stop_pct=CHART_STOP_ONLY)
        cs_m = metrics(cs_rows)
        sign_stable = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m.get("exp_dollar", 0) > 0))
        block["no_truncation"] = {
            "stop8_exp": m["exp_dollar"], "chartstop_exp": cs_m.get("exp_dollar"),
            "stop8_oos_exp": m.get("oos_exp"), "chartstop_oos_exp": cs_m.get("oos_exp"),
            "sign_stable": sign_stable,
        }
        nm = random_null(kept, spy, ribbon, vix, days, strike_offset=strike_offset)
        block["random_null"] = nm
        sd = nm.get("sameday_sameside", {})
        cf = nm.get("coinflip", {})
        beats_sameday = bool(sd.get("seeds") and m["exp_dollar"] > sd["mean"] + sd.get("std", 0.0))
        beats_coin_max = bool(cf.get("seeds") and m["exp_dollar"] > cf.get("max", 9e9))
        block["random_null"]["beats_sameday_mean1std"] = beats_sameday
        block["random_null"]["beats_coinflip_max"] = beats_coin_max
        # G7 = beat BOTH the same-day mean+1std AND the coin-flip MAX
        block["random_null"]["beats_null"] = bool(beats_sameday and beats_coin_max)
    return block


def eight_gates(block) -> dict:
    """Apply the 8 mandatory gates. Returns per-gate pass/fail + overall."""
    m = block.get("metrics", {})
    vb = block.get("vs_baseline", {})
    nt = block.get("no_truncation", {})
    rn = block.get("random_null", {})
    g = {}
    g["G1_oos_per_trade_pos"] = bool((m.get("oos_exp") or 0) > 0)
    g["G2_posQ_ge_4"] = bool(m.get("positive_quarters_n", 0) >= 4)
    t5 = m.get("top5_day_pct")
    g["G3_top5_lt_200"] = bool(t5 is not None and t5 < 200.0)
    g["G4_n_ge_20"] = bool(m.get("n", 0) >= 20)
    g["G5_drop_top5_pos"] = bool((m.get("drop_top5_day_per_trade") or 0) > 0)
    g["G6_is_first_half_pos"] = bool((m.get("is_first_half_per_trade") or 0) > 0)
    g["G7_beats_random_null"] = bool(rn.get("beats_null"))
    g["G8_truncation_sign_stable"] = bool(nt.get("sign_stable"))
    g["ALL_8_PASS"] = all(v for k, v in g.items() if k.startswith("G"))
    g["n_failed"] = sum(1 for k, v in g.items() if k.startswith("G") and not v)
    return g


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sub-vixchar] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sub-vixchar] bars={len(spy)} days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # Detect the family signal set ONCE (byte-for-byte detector, full pattern).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sub-vixchar] signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # Per-signal as-of features (look-ahead-safe): 5-bar VIX slope + entry_vix level.
    feat = {}
    evix_all = []
    for sg in signals:
        vslope = _vix_slope(vix, int(sg.bar_idx), VIX_SLOPE_LOOK)
        evix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        feat[id(sg)] = {"vix_slope": vslope, "entry_vix": evix, "side": sg.side}
        if evix > 0:
            evix_all.append(evix)
    # Level tercile cut (the campaign survivor's "worst regime") — computed on the FULL
    # sample's entry_VIX. An entry is in the WORST tercile when entry_VIX > 2/3 quantile.
    top_tercile_cut = float(np.quantile(evix_all, TOP_TERCILE_Q)) if evix_all else 0.0
    # character side-agreement counts (disclosure)
    char_agree = sum(1 for sg in signals
                     if (feat[id(sg)]["side"] == "C" and feat[id(sg)]["vix_slope"] < 0)
                     or (feat[id(sg)]["side"] == "P" and feat[id(sg)]["vix_slope"] > 0))
    char_flat = sum(1 for sg in signals if feat[id(sg)]["vix_slope"] == 0)
    char_contra = len(signals) - char_agree - char_flat
    print(f"[sub-vixchar] VIX-char: agree={char_agree} flat={char_flat} contra={char_contra} "
          f"| top-tercile cut entry_VIX>{top_tercile_cut:.2f}", flush=True)

    # ── predicates ────────────────────────────────────────────────────────────
    def p_char_loose(s):  # take with-trade OR flat; skip only contra
        f = feat[id(s)]
        if f["side"] == "C":
            return f["vix_slope"] <= 0      # falling or flat OK for calls
        return f["vix_slope"] >= 0          # rising or flat OK for puts

    def p_char_strict(s):  # demand real agreement; skip contra AND flat
        f = feat[id(s)]
        if f["side"] == "C":
            return f["vix_slope"] < 0
        return f["vix_slope"] > 0

    def p_char_inverse(s):  # the L166 cross-check: take ONLY contra-character
        f = feat[id(s)]
        if f["side"] == "C":
            return f["vix_slope"] > 0
        return f["vix_slope"] < 0

    def p_skip_top_tercile(s):  # campaign survivor: skip WORST VIX-level tercile
        ev = feat[id(s)]["entry_vix"]
        return ev <= 0 or ev <= top_tercile_cut

    result_by_tier = {}
    for tier_off in (PRIMARY_STRIKE_OFFSET, SECONDARY_STRIKE_OFFSET):
        tier_label = f"ITM{abs(tier_off)}" if tier_off < 0 else f"OTM{tier_off}"
        print(f"\n===== STRIKE TIER {tier_label} (offset {tier_off:+d}) =====", flush=True)

        # ungated baseline
        base_rows, base_cov = simulate_set(signals, spy, ribbon, vix, strike_offset=tier_off)
        base_m = metrics(base_rows)
        print(f"[BASELINE ungated {tier_label}] n={base_m.get('n')} exp=${base_m.get('exp_dollar')} "
              f"oos_exp=${base_m.get('oos_exp')} oos_total=${base_m.get('oos_total')} "
              f"maxDD=${base_m.get('max_drawdown')} posQ={base_m.get('positive_quarters')} "
              f"top5%={base_m.get('top5_day_pct')}", flush=True)
        base_cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=tier_off,
                                       premium_stop_pct=CHART_STOP_ONLY)
        base_cs_m = metrics(base_cs_rows)
        base_null = random_null(signals, spy, ribbon, vix, days, strike_offset=tier_off)
        base_block = {
            "config": {"strike_offset": tier_off, "strike_tier": tier_label,
                       "premium_stop_pct": SURV_PREMIUM_STOP, "exits": "v15 default"},
            "coverage": base_cov, "metrics": base_m,
            "no_truncation": {"stop8_exp": base_m.get("exp_dollar"),
                              "chartstop_exp": base_cs_m.get("exp_dollar"),
                              "stop8_oos_exp": base_m.get("oos_exp"),
                              "chartstop_oos_exp": base_cs_m.get("oos_exp"),
                              "sign_stable": bool(base_cs_m.get("n") and
                                                  (base_m.get("exp_dollar", 0) > 0) ==
                                                  (base_cs_m.get("exp_dollar", 0) > 0))},
            "random_null": base_null,
        }

        # level-skip benchmark (campaign survivor)
        kept_lvl = partition(signals, p_skip_top_tercile)
        lvl_block = eval_panel(
            "skip_top_tercile_only",
            f"campaign survivor: SKIP entries with entry_VIX > top tercile ({top_tercile_cut:.2f})",
            kept_lvl, spy, ribbon, vix, days, base_m, strike_offset=tier_off)
        lvl_block["eight_gates"] = eight_gates(lvl_block)

        # character gate — loose + strict
        kept_loose = partition(signals, p_char_loose)
        loose_block = eval_panel(
            "vix_character_loose",
            "take calls when VIX falling-or-flat / puts when VIX rising-or-flat; SKIP contra",
            kept_loose, spy, ribbon, vix, days, base_m, strike_offset=tier_off)
        loose_block["eight_gates"] = eight_gates(loose_block)

        kept_strict = partition(signals, p_char_strict)
        strict_block = eval_panel(
            "vix_character_strict",
            "take calls ONLY when VIX falling / puts ONLY when VIX rising; SKIP contra AND flat",
            kept_strict, spy, ribbon, vix, days, base_m, strike_offset=tier_off)
        strict_block["eight_gates"] = eight_gates(strict_block)

        # inverse character (L166 causality cross-check) — gates run for disclosure
        kept_inv = partition(signals, p_char_inverse)
        inv_block = eval_panel(
            "vix_character_inverse",
            "L166 cross-check: take ONLY contra-character entries (calls into rising VIX, "
            "puts into falling VIX) — a real character edge makes this WORSE",
            kept_inv, spy, ribbon, vix, days, base_m, strike_offset=tier_off)
        inv_block["eight_gates"] = eight_gates(inv_block)

        for nm_, blk in (("skip_top_tercile", lvl_block), ("char_loose", loose_block),
                         ("char_strict", strict_block), ("char_inverse", inv_block)):
            mm = blk["metrics"]; vb = blk.get("vs_baseline", {}); eg = blk["eight_gates"]
            print(f"  {nm_:>17}: kept={blk['n_signals_kept']:>3} n={mm.get('n','-'):>3} "
                  f"exp=${mm.get('exp_dollar','-')} oos_exp=${mm.get('oos_exp','-')} "
                  f"oos_lift=${vb.get('oos_per_trade_lift','-')} maxDD=${mm.get('max_drawdown','-')} "
                  f"posQ={mm.get('positive_quarters','-')} 8gates={'ALL PASS' if eg['ALL_8_PASS'] else str(eg['n_failed'])+'fail'}",
                  flush=True)

        result_by_tier[tier_label] = {
            "strike_offset": tier_off,
            "ungated_baseline": base_block,
            "skip_top_tercile_only": lvl_block,
            "vix_character_loose": loose_block,
            "vix_character_strict": strict_block,
            "vix_character_inverse": inv_block,
        }

    # ── headline verdict on the PRIMARY (ITM-2) tier ─────────────────────────
    prim = result_by_tier[f"ITM{abs(PRIMARY_STRIKE_OFFSET)}"]
    loose_p = prim["vix_character_loose"]; strict_p = prim["vix_character_strict"]
    lvl_p = prim["skip_top_tercile_only"]; inv_p = prim["vix_character_inverse"]

    # pick the BEST character variant (most gates passed, tiebreak OOS per-trade)
    char_variants = [("vix_character_loose", loose_p), ("vix_character_strict", strict_p)]
    char_variants.sort(key=lambda kv: (kv[1]["eight_gates"]["ALL_8_PASS"],
                                       -kv[1]["eight_gates"]["n_failed"],
                                       kv[1]["metrics"].get("oos_exp", -9e9)), reverse=True)
    best_char_name, best_char = char_variants[0]
    best_eg = best_char["eight_gates"]
    best_m = best_char["metrics"]

    char_oos = best_m.get("oos_exp")
    lvl_oos = lvl_p["metrics"].get("oos_exp")
    beats_level_skip = bool(char_oos is not None and lvl_oos is not None and char_oos > lvl_oos)
    # L166 causality: inverse must be materially WORSE (lower OOS per-trade) than the gate
    inv_oos = inv_p["metrics"].get("oos_exp")
    inverse_confirms = bool(char_oos is not None and inv_oos is not None and char_oos > inv_oos)

    if best_eg["ALL_8_PASS"] and beats_level_skip:
        verdict = (f"CHARACTER GATE WINS — {best_char_name} clears all 8 gates AND its OOS "
                   f"per-trade (${char_oos}) beats the level-tercile skip (${lvl_oos}). "
                   f"SUBTRACTION by VIX *character* > by VIX *level*. Ship under standing "
                   f"authorization (OP-11/OP-22), report for REVOKE.")
    elif best_eg["ALL_8_PASS"] and not beats_level_skip:
        verdict = (f"CHARACTER GATE VALID but does NOT beat level skip — {best_char_name} clears "
                   f"all 8 gates (OOS ${char_oos}) but the level-tercile skip is >= it "
                   f"(${lvl_oos}). Character abstention is real but the LEVEL skip already "
                   f"captures it; no reason to switch.")
    else:
        verdict = (f"CHARACTER GATE REJECTED — best variant {best_char_name} fails "
                   f"{best_eg['n_failed']} of 8 gates "
                   f"({[k for k,v in best_eg.items() if k.startswith('G') and not v]}). "
                   f"VIX-character abstention does NOT clear the bar on real fills; "
                   f"the level-tercile skip remains the only subtractive survivor.")

    summary = {
        "study": "abstain_vix_character — VIX CHARACTER (5-bar slope) vs VIX LEVEL tercile, subtractive abstention on vwap_continuation",
        "kind": "subtractive_abstention",
        "hypothesis": ("VIX CHARACTER not level (C5): take vwap entries only when as-of VIX 5-bar "
                       "slope agrees (calls when VIX falling, puts when VIX rising), SKIP contra. "
                       "Does character-based abstention beat the level-tercile skip?"),
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation "
                     "(imported from _edgehunt_vwap_continuation; live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py)"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "strike_tiers": {"primary": "ITM-2 (offset -2, survivor structure)",
                         "secondary": "OTM-2 (offset +2, Safe-2 $2K tier; C29 cross-check)"},
        "vix_slope_lookback_bars": VIX_SLOPE_LOOK,
        "character_rule": ("CALL taken when 5-bar VIX slope agrees (falling); PUT when rising; "
                           "as-of at entry bar (look-ahead-safe via _vix_slope idx<=entry)"),
        "level_benchmark": (f"skip_top_tercile_only — drop entries with entry_VIX > {top_tercile_cut:.2f} "
                            f"(the 2/3 quantile of full-sample entry_VIX = WORST VIX-level regime)"),
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "character_breakdown": {"agree": char_agree, "flat": char_flat, "contra": char_contra,
                                "top_tercile_cut": round(top_tercile_cut, 2)},
        "eight_gates_definition": {
            "G1": "OOS(2026) per-trade > 0", "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200", "G4": "n >= 20",
            "G5": "drop-top5 per-trade > 0", "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random null (same-day mean+1std AND coin-flip MAX, 20 seeds)",
            "G8": "no-truncation: per-trade sign holds -8% -> chart-stop-only -0.99",
        },
        "results_by_strike_tier": result_by_tier,
        "headline_primary_tier": {
            "tier": "ITM-2",
            "best_character_variant": best_char_name,
            "best_character_oos_per_trade": char_oos,
            "best_character_eight_gates": best_eg,
            "level_skip_oos_per_trade": lvl_oos,
            "beats_level_skip": beats_level_skip,
            "inverse_oos_per_trade": inv_oos,
            "inverse_confirms_causality": inverse_confirms,
        },
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("character gate reported as BOTH loose (skip contra only) and strict "
                               "(skip contra+flat); level skip reproduced as the comparison benchmark; "
                               "inverse-character gate reported as the L166 causality cross-check "
                               "(anti-pattern 2.10)."),
            "subtractive": "this is a SUBTRACTIVE study (abstain from bad-regime entries), not additive confluence.",
            "as_of": "VIX 5-bar slope + entry_VIX read AT the entry bar via _vix_slope (idx <= entry; look-ahead-safe, C6).",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "strike_transfer": "FULL gate panel re-run at OTM-2 per C29 (gates don't transfer across strike tiers).",
            "fraud_gates": "G7 random-entry null (same-day + coin-flip, 20 seeds, L172) + G8 no-truncation (L171).",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub-vixchar] wrote {OUT}", flush=True)

    print("\n=== ABSTAIN_VIX_CHARACTER VERDICT (ITM-2 primary) ===")
    print(f"best char variant: {best_char_name} | OOS/tr=${char_oos} | 8gates={'ALL PASS' if best_eg['ALL_8_PASS'] else str(best_eg['n_failed'])+' fail'}")
    print(f"level-tercile skip OOS/tr=${lvl_oos} | char beats level? {beats_level_skip}")
    print(f"inverse OOS/tr=${inv_oos} | inverse confirms causality? {inverse_confirms}")
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
