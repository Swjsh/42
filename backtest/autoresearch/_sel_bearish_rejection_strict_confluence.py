"""SELECTION test: BEARISH_REJECTION_RIDE_THE_RIBBON at STRICT >=2-confluence (real fills).

THESIS UNDER TEST (the user's brief): THE REAL J-EDGE is BEARISH_REJECTION_RIDE_THE_RIBBON
-- J's source-of-truth setup (4/29 710P +$342, 5/01 721P +$470, 5/04 721P +$730). The
earlier ``bearish_rejection_morning`` watcher fired at LOW confluence and failed. The
question: does STRICT selection -- entry ONLY when >= 2 of four INDEPENDENT confirmations
fire TOGETHER in the morning (09:35-11:00 ET) -- convert the coin-flip into a real
per-trade option edge?

THE FOUR INDEPENDENT CONFLUENCE COMPONENTS (each a pure-Python read on closed bars):
  1. NAMED-LEVEL REJECTION   -- bar high touches (within $0.50) a per-day structural named
     level (prior-day high, overnight/premarket high, prior-day close) AND closes >= 15c
     below it. (the bearish_rejection_morning_watcher logic, levels derived structurally
     per-day so it is HISTORICAL -- live key-levels.json is today-only and unusable in a
     16mo backtest.)
  2. RIBBON-FLIP-TO-BEAR      -- Saty 13/20/48 ribbon stack == BEAR now AND was NOT BEAR
     `FLIP_LOOKBACK` bars ago (a genuine flip, not a standing bear stack).
  3. MULTI-DAY-TRENDLINE CONF -- a descending RESISTANCE trendline fit over the prior
     ~3 sessions' swing highs projects within tolerance of THIS bar's high (price testing
     a multi-day down-trendline from below = the J "trendline" confluence on 5/04).
  4. SEQUENCE-REJECTION       -- market_structure.analyze_structure over the trailing
     intraday window prints a FRESH bearish event (CHoCH/BOS at the last bar) OR a fresh
     lower-high (LH) -- the swing-SEQUENCE rejection (HH->LH roll-over).

STRICT GATE: count the four; require count >= MIN_CONFLUENCE (default 2). Puts only
(survivor structure = bearish). Morning window 09:35-11:00 ET. One causal entry/day
(first bar that clears the gate); next-bar-open fill, no look-ahead.

SURVIVOR STRUCTURE (the user's brief, primary): strike_offset=-2 (ITM-2),
premium_stop_pct=-0.08, qty=3, v15 exits. Real OPRA fills via simulate_trade_real (C1).

ALL MANDATORY GATES (deterministic, in-script -- anti-pattern 2.10, no cherry-pick):
  GATE_OOS    : OOS(2026) per-trade > 0
  GATE_IS     : IN-SAMPLE(2025) per-trade > 0     (reject IS-neg/OOS-pos single-regime
                                                    artifacts -- the futures trap)
  GATE_Q      : positive_quarters >= 4/6
  GATE_CONC   : top5-day < 200%  AND  drop-top-5-days per-trade > 0
  GATE_N      : n >= 20
  GATE_NULL   : beats a RANDOM-entry null (same exit/stop/strike/side, 20 seeds): beat the
                null MAX AND drop-top5 beats the null MEAN  (null_baseline.py / L172)
  GATE_TRUNC  : sign does NOT invert at chart-stop-only (-0.99)  (truncation_guard / L171)

Plus the OP-16 J-ANCHOR edge-capture check (disclosure, not a numeric gate here because
the strict morning detector may not fire on every anchor day -- a non-firing winner day
is a missed-capture flag, a fired-and-lost loser day is a regression flag).

Pure Python, $0 in the sim loop. No live orders. Markets closed.
Writes analysis/recommendations/sel-bearish-rejection-strict-confluence.json.
Run: backtest/.venv/Scripts/python.exe \
        backtest/autoresearch/_sel_bearish_rejection_strict_confluence.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # backtest/
ROOT = REPO.parent                            # repo root (42/)
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _align_vix, _normalize_spy  # noqa: E402
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402
from crypto.lib.trendlines import find_swing_points, fit_trendline  # noqa: E402

SLUG = "bearish-rejection-strict-confluence"
OUT = ROOT / "analysis" / "recommendations" / f"sel-{SLUG}.json"

# ── SURVIVOR STRUCTURE (the user's brief: use as primary) ──────────────────────
STRIKE_OFFSET = -2            # ITM-2 (for puts: strike = atm - offset = atm + 2, ITM)
PREMIUM_STOP_PCT = -0.08      # v15 asymmetric tight stop
QTY = 3                       # 2 TP + 1 runner
MAX_STRIKE_STEPS = 4          # nearest-cached snap radius (matches the edge-hunt path)
SETUP = "BEARISH_REJECTION_RIDE_THE_RIBBON"
OOS_YEAR = 2026
NULL_SEEDS = 20

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── Confluence detector params ─────────────────────────────────────────────────
MORNING_START = dt.time(9, 35)
MORNING_END = dt.time(11, 0)
MIN_CONFLUENCE = 2                 # STRICT: >= 2 of the 4 components must fire together
LEVEL_PROXIMITY = 0.50             # bar high within $0.50 of a named level (touch)
REJECTION_BODY_MIN = 0.15          # close >= $0.15 below the level (rejection body)
FLIP_LOOKBACK = 3                  # ribbon was not BEAR this many bars ago => a flip
TRENDLINE_DAYS = 3                 # prior sessions feeding the multi-day resistance line
TRENDLINE_TOL_PCT = 0.0010         # |high - projected| <= 0.10% of price = a touch
STRUCTURE_WINDOW = 2               # market_structure fractal window (SPY 5m default)
STRUCTURE_TRAIL = 60               # trailing bars fed to analyze_structure
WARMUP_BARS = 6                    # bars into the day before evaluating (ribbon/structure)

# ── OP-16 J-anchor source-of-truth trades (immutable) ──────────────────────────
J_WINNERS = {  # engine MUST take (or it's a missed-capture flag)
    "2026-04-29": 342.0, "2026-05-01": 470.0, "2026-05-04": 730.0,
}
J_LOSERS = {  # engine MUST skip or lose less (firing+losing here is a regression flag)
    "2026-05-05": -260.0, "2026-05-06": -300.0, "2026-05-07": -120.0,
}

# ── Mandatory gate bars ────────────────────────────────────────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


@dataclass
class Sig:
    bar_idx_full: int      # index into the full (normalized) spy frame
    date: dt.date
    rejection_level: float
    confluence: int
    components: list


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _rows_to_bars(sub: pd.DataFrame) -> list[Bar]:
    """Build crypto Bar objects (UTC open_time placeholder; only ordering/levels matter)."""
    bars: list[Bar] = []
    for _, r in sub.iterrows():
        ts = pd.Timestamp(r["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        bars.append(Bar(
            open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
            open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
            close=float(r["close"]), volume=int(r.get("volume", 50000) or 50000),
            granularity_seconds=300, source="spy"))
    return bars


def _named_levels_for_day(spy: pd.DataFrame, day_rows: list[int],
                          prior_day_rows: list[int], premarket_rows: list[int]) -> list[float]:
    """Structurally-derived per-day named levels (HISTORICAL substitute for the live
    today-only key-levels.json): prior-day HIGH, prior-day CLOSE, and overnight/premarket
    HIGH. Resistance candidates a morning bear rejection would test from below."""
    levels: list[float] = []
    if prior_day_rows:
        pd_high = float(spy.iloc[prior_day_rows]["high"].max())
        pd_close = float(spy.iloc[prior_day_rows[-1]]["close"])
        levels += [pd_high, pd_close]
    if premarket_rows:
        pm_high = float(spy.iloc[premarket_rows]["high"].max())
        levels.append(pm_high)
    # unique, drop non-positive
    return sorted({round(l, 2) for l in levels if l > 0})


def _trendline_resistance_at(prior_bars: list[Bar], bar_time_unix: float) -> Optional[float]:
    """Fit a descending resistance trendline over prior-session swing highs; return its
    projected price at bar_time_unix (None if no valid descending line / <2 swing highs)."""
    if len(prior_bars) < 10:
        return None
    swings = find_swing_points(prior_bars, window=3, inclusive_right=False)
    line = fit_trendline(swings, kind="resistance")
    if line is None:
        return None
    if line.slope >= 0:          # only a DESCENDING resistance line is the bear confluence
        return None
    proj = line.price_at(bar_time_unix)
    return proj if proj > 0 else None


def detect_signals(spy: pd.DataFrame, ribbon: pd.DataFrame) -> list[Sig]:
    """Walk every RTH morning bar; emit the first bar/day where >= MIN_CONFLUENCE of the
    four bearish components fire together. Causal: every read uses only bars up to idx."""
    spy = spy.copy()
    spy["date"] = spy["timestamp_et"].dt.date
    spy["t"] = spy["timestamp_et"].dt.time

    # index lists per day for RTH + premarket; and the prior trading day's RTH rows
    rth_idx_by_day: dict[dt.date, list[int]] = defaultdict(list)
    pm_idx_by_day: dict[dt.date, list[int]] = defaultdict(list)
    for i in range(len(spy)):
        t = spy.iloc[i]["t"]
        d = spy.iloc[i]["date"]
        if dt.time(9, 30) <= t < dt.time(16, 0):
            rth_idx_by_day[d].append(i)
        elif dt.time(4, 0) <= t < dt.time(9, 30):
            pm_idx_by_day[d].append(i)

    ordered_days = sorted(rth_idx_by_day.keys())
    prior_of: dict[dt.date, Optional[dt.date]] = {}
    for k, d in enumerate(ordered_days):
        prior_of[d] = ordered_days[k - 1] if k > 0 else None

    out: list[Sig] = []
    for d in ordered_days:
        rth_rows = rth_idx_by_day[d]
        prior_d = prior_of[d]
        prior_rows = rth_idx_by_day.get(prior_d, []) if prior_d else []
        pm_rows = pm_idx_by_day.get(d, [])
        levels = _named_levels_for_day(spy, rth_rows, prior_rows, pm_rows)

        # prior-sessions bars for the multi-day trendline (last TRENDLINE_DAYS days, RTH)
        td_days = ordered_days[max(0, ordered_days.index(d) - TRENDLINE_DAYS):ordered_days.index(d)]
        td_rows: list[int] = []
        for pd_ in td_days:
            td_rows += rth_idx_by_day[pd_]
        prior_bars = _rows_to_bars(spy.iloc[td_rows]) if td_rows else []

        i0 = rth_rows[0]
        for local, idx in enumerate(rth_rows):
            t = spy.iloc[idx]["t"]
            if t < MORNING_START:
                continue
            if t > MORNING_END:
                break
            if local < WARMUP_BARS:
                continue

            bar = spy.iloc[idx]
            bar_high = float(bar["high"])
            bar_close = float(bar["close"])
            bar_open = float(bar["open"])

            components: list[str] = []
            rejection_level: Optional[float] = None

            # (1) NAMED-LEVEL REJECTION
            best_body = 0.0
            for lv in levels:
                if bar_high >= lv - LEVEL_PROXIMITY:
                    body = lv - bar_close
                    if body >= REJECTION_BODY_MIN and body > best_body:
                        best_body = body
                        rejection_level = lv
            if rejection_level is not None:
                components.append("named_level_rejection")

            # (2) RIBBON-FLIP-TO-BEAR
            rb_now = ribbon.iloc[idx]
            flip_ref_pos = max(i0, idx - FLIP_LOOKBACK)
            rb_prev = ribbon.iloc[flip_ref_pos]
            if (str(rb_now["stack"]) == "BEAR" and str(rb_prev["stack"]) != "BEAR"):
                components.append("ribbon_flip_to_bear")

            # (3) MULTI-DAY-TRENDLINE CONFLUENCE
            if prior_bars:
                bt_unix = pd.Timestamp(bar["timestamp_et"]).tz_localize(None).timestamp() \
                    if pd.Timestamp(bar["timestamp_et"]).tzinfo is not None \
                    else pd.Timestamp(bar["timestamp_et"]).timestamp()
                proj = _trendline_resistance_at(prior_bars, bt_unix)
                if proj is not None:
                    tol = proj * TRENDLINE_TOL_PCT
                    if abs(bar_high - proj) <= max(tol, LEVEL_PROXIMITY) and bar_close < proj:
                        components.append("multiday_trendline")

            # (4) SEQUENCE-REJECTION (fresh bearish structure event OR fresh LH)
            trail_start = max(i0, idx - STRUCTURE_TRAIL + 1)
            trail_bars = _rows_to_bars(spy.iloc[trail_start: idx + 1])
            if len(trail_bars) >= 10:
                ms = analyze_structure(trail_bars, window=STRUCTURE_WINDOW)
                fresh_bear_event = (
                    ms.last_event is not None
                    and ms.last_event.direction == "bearish"
                    and ms.last_event.break_index >= len(trail_bars) - 1 - STRUCTURE_WINDOW
                )
                # fresh LH: most recent swing high is labeled LH and printed recently
                recent_highs = [s for s in ms.labeled_swings if s.kind == "swing_high"]
                fresh_lh = bool(recent_highs and recent_highs[-1].label == "LH"
                                and recent_highs[-1].bar_index >= len(trail_bars) - 1 - 2 * STRUCTURE_WINDOW)
                if fresh_bear_event or fresh_lh:
                    components.append("sequence_rejection")

            if len(components) >= MIN_CONFLUENCE:
                # rejection_level: prefer the named level; fall back to bar high (chart stop
                # above the rejection high) so a non-named-level confluence still has a stop.
                rej = rejection_level if rejection_level is not None else bar_high
                out.append(Sig(bar_idx_full=idx, date=d, rejection_level=float(rej),
                               confluence=len(components), components=list(components)))
                break  # one causal entry per day

    return out


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(day: str) -> str:
    y, m, _ = day.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _per_trade(rows):
    return round(float(np.mean([r["pnl"] for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows):
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    if not by_day:
        return None
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(float(np.mean(kept)), 2) if kept else None


def _top5_day_pct(rows):
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def main() -> int:
    print(f"[sel] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)          # tz-naive ET, date/t/minute, floats
    vix = _align_vix(spy, vix_raw)

    # RTH-only reset-index frame for the fraud-gate re-sim + null draws.
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)
    n_days = rth["timestamp_et"].dt.date.nunique()

    print(f"[sel] computing ribbon over full frame ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    ribbon.index = spy.index  # align to spy positional index

    print(f"[sel] scanning morning bars for >= {MIN_CONFLUENCE}-confluence bearish rejections ...",
          flush=True)
    signals = detect_signals(spy, ribbon)
    sig_days = len({s.date for s in signals})
    conf_hist = defaultdict(int)
    comp_hist = defaultdict(int)
    for s in signals:
        conf_hist[s.confluence] += 1
        for c in s.components:
            comp_hist[c] += 1
    print(f"[sel] signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of {n_days}) "
          f"confluence_hist={dict(sorted(conf_hist.items()))} components={dict(comp_hist)}",
          flush=True)

    # ── Re-simulate the SURVIVOR STRUCTURE on real OPRA fills (puts only) ───────
    rows = []
    n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx_full]
        d = sg.date
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - STRIKE_OFFSET     # puts: ITM = strike above spot
        strike = _nearest_cached_strike(d, target, "P", MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx_full]) if sg.bar_idx_full < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx_full, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.rejection_level,
            triggers_fired=["bearish_rejection"] + sg.components,
            side="P", qty=QTY, setup=SETUP, strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        rows.append({"date": str(d), "side": "P", "pnl": round(float(fill.dollar_pnl), 2),
                     "confluence": sg.confluence, "components": sg.components,
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})

    n = len(rows)
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "per_trade": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    pos_q = sum(1 for v in quarters.values() if v["per_trade"] > 0)

    overall_pt = _per_trade(rows)
    is_pt = _per_trade(is_rows)
    oos_pt = _per_trade(oos_rows)
    drop_top5_pt = _drop_top5_per_trade(rows)
    top5 = _top5_day_pct(rows)

    # ── FRAUD GATES via the graduated harness (per-trade re-simulation) ────────
    # Map each signal's full-frame bar onto the RTH reset-index frame.
    ts_to_rth_idx = {ts: i for i, ts in enumerate(rth["timestamp_et"])}
    cand_signals = []
    for s in signals:
        ts = spy.iloc[s.bar_idx_full]["timestamp_et"]
        ridx = ts_to_rth_idx.get(ts)
        if ridx is not None:
            cand_signals.append(CandidateSignal(bar_idx=int(ridx), side="P",
                                                rejection_level=float(s.rejection_level),
                                                note="bearish_rejection"))
    print(f"[sel] running fraud gates (re-sim chosen + chart-stop-only + {NULL_SEEDS}-seed null) ...",
          flush=True)
    fraud = verify_candidate(
        cand_signals, rth, strike_offset=STRIKE_OFFSET, premium_stop_pct=PREMIUM_STOP_PCT,
        qty=QTY, setup=SETUP, seeds=NULL_SEEDS)

    # ── OP-16 J-ANCHOR edge-capture disclosure ─────────────────────────────────
    pnl_by_day = defaultdict(float)
    for r in rows:
        pnl_by_day[r["date"]] += r["pnl"]
    anchor = {"winners": {}, "losers": {}}
    for d in J_WINNERS:
        anchor["winners"][d] = {"fired": d in pnl_by_day,
                                "engine_pnl": round(pnl_by_day.get(d, 0.0), 2),
                                "j_pnl": J_WINNERS[d]}
    for d in J_LOSERS:
        fired = d in pnl_by_day
        anchor["losers"][d] = {"fired": fired,
                               "engine_pnl": round(pnl_by_day.get(d, 0.0), 2),
                               "j_pnl": J_LOSERS[d],
                               "regression": bool(fired and pnl_by_day.get(d, 0.0) < J_LOSERS[d])}
    # edge_capture = sum engine pnl on J winning days - sum max(0, engine loss on J losing days)
    cap_win = sum(pnl_by_day.get(d, 0.0) for d in J_WINNERS)
    cap_loss = sum(max(0.0, -pnl_by_day.get(d, 0.0)) for d in J_LOSERS)
    edge_capture = round(cap_win - cap_loss, 2)
    anchor["edge_capture"] = edge_capture
    anchor["edge_capture_formula"] = ("sum(engine_pnl on J winning days) - sum(max(0, engine "
                                      "loss on J losing days)); winners not fired = missed capture")
    anchor["no_loser_regression"] = all(not v["regression"] for v in anchor["losers"].values())

    # ── ALL MANDATORY GATES (deterministic, in-script) ─────────────────────────
    gates = {
        "GATE_OOS_pt_gt0": bool(oos_pt is not None and oos_pt > 0),
        "GATE_IS_pt_gt0": bool(is_pt is not None and is_pt > 0),
        "GATE_pos_quarters_ge4of6": bool(pos_q >= BAR_POS_Q and len(quarters) >= 6),
        "GATE_top5_day_lt200": bool(top5 is not None and top5 < BAR_TOP5),
        "GATE_drop_top5_pt_gt0": bool(drop_top5_pt is not None and drop_top5_pt > 0),
        "GATE_n_ge20": bool(n >= BAR_N),
        "GATE_beats_random_null": bool(fraud.null_pass),
        "GATE_no_truncation": bool(fraud.no_truncation_pass),
    }
    fails = [k for k, v in gates.items() if not v]
    selection_edge = len(fails) == 0

    summary = {
        "slug": SLUG,
        "thesis": ("THE REAL J-EDGE: BEARISH_REJECTION_RIDE_THE_RIBBON at STRICT >=2-confluence "
                   "selection (named-level rejection / ribbon-flip-to-bear / multi-day trendline / "
                   "sequence-rejection) in the morning (09:35-11:00 ET), puts only. Does strict "
                   "selection convert the low-confluence coin-flip into a real per-trade option "
                   "edge? Tested honestly; may also fail."),
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "detector": ("STRICT >=2-of-4 confluence on closed bars, causal one-entry/day, "
                     "next-bar-open fill (no look-ahead). Components: named_level_rejection "
                     "(structural per-day levels), ribbon_flip_to_bear (Saty 13/20/48 stack "
                     "flip), multiday_trendline (descending resistance line projected to bar), "
                     "sequence_rejection (market_structure fresh bearish CHoCH/BOS or fresh LH)"),
        "confluence_rule": {"min_confluence": MIN_CONFLUENCE, "morning_window": "09:35-11:00 ET",
                            "side": "P (puts only)", "components": 4},
        "structure": {"strike_offset": STRIKE_OFFSET, "strike_tier": "ITM-2",
                      "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY, "exits": "v15"},
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "signals": {"n": len(signals), "on_days": sig_days,
                    "fire_day_pct": round(100 * sig_days / n_days, 1),
                    "confluence_hist": dict(sorted(conf_hist.items())),
                    "component_hist": dict(comp_hist)},
        "coverage": {"signals": len(signals), "filled": n,
                     "cache_miss": n_cache_miss, "sim_none": n_sim_none,
                     "fill_rate": round(n / len(signals), 3) if signals else 0.0},
        "metrics": {
            "n": n,
            "overall_per_trade": overall_pt,
            "is_n": len(is_rows), "is_per_trade": is_pt,
            "oos_n": len(oos_rows), "oos_per_trade": oos_pt,
            "drop_top5_per_trade": drop_top5_pt,
            "top5_day_pct": top5,
            "positive_quarters": f"{pos_q}/{len(quarters)}",
            "quarters": quarters,
            "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None,
            "total_dollar": round(sum(r["pnl"] for r in rows), 2),
            "exit_hist": {k: sum(1 for r in rows if r["exit"] == k)
                          for k in sorted({r["exit"] for r in rows})},
        },
        "j_anchor_edge_capture": anchor,
        "fraud_gates": fraud.as_dict(),
        "gates": gates,
        "fails": fails,
        "selection_edge": selection_edge,
        "verdict": ("SELECTION_EDGE: all mandatory gates hold (incl. both graduated fraud gates) "
                    "-> strict >=2-confluence selection converts the bearish-rejection coin-flip "
                    "into a real per-trade option edge"
                    if selection_edge else
                    f"NOT A SELECTION_EDGE: fails {fails}"),
        "DISCLOSURE": {
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "is_oos": "IS=2025 AND OOS=2026 BOTH required positive (rejects single-regime artifacts)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade (OP-20 #5)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "fraud_gates": ("random-entry-null (L172) AND no-truncation (L171) -- the two "
                            "discriminators that caught RSI2/IBS/ema_adx after the naive 5-gate bar"),
            "named_levels_caveat": ("live key-levels.json is today-only; for the 16mo backtest "
                                    "named levels are derived STRUCTURALLY per-day (prior-day "
                                    "high/close, overnight/premarket high) -- a documented "
                                    "substitute, NOT J's curated star levels"),
            "j_anchor": ("OP-16 edge-capture is DISCLOSED not gated -- the strict morning detector "
                         "need not fire on every anchor day; a non-firing winner = missed capture, "
                         "a fired-and-worse loser = regression (anchor.no_loser_regression)"),
            "no_cherry_pick": "single fixed structure (ITM-2/-8%/v15), MIN_CONFLUENCE=2; no grid pick (2.10)",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sel] wrote {OUT}", flush=True)

    print("\n=== SELECTION VERDICT (bearish_rejection_strict_confluence) ===")
    print(f"signals={len(signals)} filled={n}  WR={summary['metrics']['wr_pct']}%  "
          f"fires {summary['signals']['fire_day_pct']}% of days")
    print(f"per-trade: overall=${overall_pt}  IS=${is_pt}  OOS=${oos_pt}  drop-top5=${drop_top5_pt}")
    print(f"posQ={pos_q}/{len(quarters)}  top5_day%={top5}")
    print(f"NULL: chosen=${fraud.chosen_per_trade}/tr  null_max=${fraud.null.get('per_trade_max')}  "
          f"null_mean=${fraud.null.get('per_trade_mean')}  -> null_pass={fraud.null_pass}")
    print(f"TRUNC: chart-stop-only=${fraud.chart_stop_only_per_trade}/tr  "
          f"-> no_truncation_pass={fraud.no_truncation_pass}")
    print(f"J-ANCHOR: edge_capture=${edge_capture}  no_loser_regression={anchor['no_loser_regression']}")
    for d, v in anchor["winners"].items():
        print(f"    WIN {d}: fired={v['fired']} engine=${v['engine_pnl']} (J=${v['j_pnl']})")
    for d, v in anchor["losers"].items():
        print(f"    LOSS {d}: fired={v['fired']} engine=${v['engine_pnl']} (J=${v['j_pnl']}) "
              f"regression={v['regression']}")
    print(f"GATES: {gates}")
    print(f"VERDICT: {summary['verdict']}")
    return 0 if selection_edge else 1


if __name__ == "__main__":
    sys.exit(main())
