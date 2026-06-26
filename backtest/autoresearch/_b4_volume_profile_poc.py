"""B4 NOVEL-DATA HUNT: volume_profile_poc — market-profile POC / value-area rejection -> 0DTE SPY.

The engine has VWAP, named levels, floor-trader pivots, swings — but NO volume-profile /
market-profile (TPO) layer. This script builds a session volume profile and tests the classic
market-profile MEAN-REVERSION reversal: price tags the POC or the value-area edges (VAH/VAL)
and REJECTS back into value -> fade it with a 0DTE single-leg directional option.

==============================================================================
SOURCED RULES (no invention — every rule maps to canonical market-profile lore)
==============================================================================
1. VOLUME PROFILE / POC / VALUE AREA (Steidlmayer market profile; canonical, e.g. CME
   "Market Profile" primer, TradingView VRVP docs, Dalton "Mind Over Markets"):
     - Bin the session by PRICE; sum traded volume per price bin.
     - POC (Point of Control) = the price bin with the MAX volume (fairest price / magnet).
     - Value Area = the contiguous band around POC containing ~70% of total volume.
       VAH = value-area HIGH, VAL = value-area LOW. Standard 70% (1 sigma) per Steidlmayer.
   src: https://www.tradingview.com/support/solutions/43000502040-volume-profile/
   src: Dalton, Mind Over Markets (value area = 70% of volume around POC)

2. VALUE-AREA / POC REVERSION ("the 80% rule" + "fade the edges back to POC"):
   "Price tends to rotate around the POC and revert to value. A tag of the value-area
    edge (VAH/VAL) that fails to find acceptance OUTSIDE value rotates back toward POC."
   -> rejection at VAH (price pokes above VAH, closes back below) = fade SHORT -> BUY PUT,
      target = POC.
   -> bounce at VAL (price pokes below VAL, closes back above) = fade LONG -> BUY CALL,
      target = POC.
   -> POC first-touch reversal: an approach INTO the POC from one side that stalls and
      reverses is the lower-quality variant; we tag it but lead with the value-edge fades.
   src: market-profile "value area edge fade" + the Initial-Balance/80%-rule lore (Dalton).

   NOTE (C4/L58, the whole point of B4): the published profile lore is a CONTEXT/probability
   framing on the UNDERLYING (futures/equity), NOT a per-trade 0DTE option edge. Theta +
   delta + stop-misfire routinely erase a directional-underlying read in 0DTE. STEP "real
   fills" is exactly the test of whether ANY of it survives that translation. Expectation LOW.

3. PROFILE SOURCE VARIANTS (both fully CAUSAL, no look-ahead — C6):
   (a) PRIOR-DAY profile: profile is built from the PRIOR RTH session's bars; its POC/VAH/VAL
       are FROZEN and known at today's 09:30 open. Today's bars are faded against yesterday's
       value. This is the cleanest causal form (the level is fixed before any of today's bars).
   (b) DEVELOPING profile: profile is built from THIS session's bars 09:30..(current bar-1);
       POC/VAH/VAL recomputed each bar from CLOSED bars only. The trigger bar's own volume is
       included only up to its close (it is a closed bar). Entry still fills NEXT bar open.

4. INVALIDATION (chart-stop, so the level-stop is meaningful):
     - PUT faded at VAH -> invalidation = above the value-edge tag's swing HIGH (acceptance
       above value kills the fade). rejection_level = swing high over the trailing window.
     - CALL faded at VAL -> invalidation = below the tag's swing LOW.
   Passed as rejection_level (simulator_real level-stop).

STEP real-fills (C1 authority): simulator_real.simulate_trade_real, v15 default exits, qty=3.
Grid: strike_offset {-2,-1,0,1,2} x premium_stop_pct {-0.08,-0.20,-0.50,-0.99}.
Reports BOTH the survivor tier (ITM-2 / -8% = the production sizing) AND ATM (Safe-2 tier).

ALL 8 GATES (anti-2.10, no cherry-pick), evaluated on the per-trade-BEST cell (n>=20):
  1. OOS(2026) per-trade > 0
  2. positive_quarters >= 4/6
  3. top5_day_pct < 200
  4. n_trades >= 20
  5. drop-top5-days per-trade > 0
  6. IS(2025)-HALF per-trade > 0  (split IS chronologically in two; first half must be >0)
  7. beats random-entry NULL  (L172, null_baseline: beat null MAX + drop-top5 beats null MEAN)
  8. NO truncation artifact   (L171, truncation_guard: same-strike chart-stop-only sign holds)

Pure Python, $0 (no LLM). No live orders. Markets CLOSED.
Output: analysis/recommendations/b4-volume_profile_poc.json

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b4_volume_profile_poc.py
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "b4-volume_profile_poc.json"

# ── Strategy parameters ──────────────────────────────────────────────────────
BIN_WIDTH = 0.25                # price-bin width ($) for the volume profile
VALUE_AREA_FRACTION = 0.70      # Steidlmayer canonical 70% value area
EDGE_TOUCH_BUFFER = 0.15        # price within this $ of VAH/VAL/POC counts as a "tag"
SWING_LOOKBACK = 12             # bars for invalidation swing low/high (~60 min)
QTY = 3
COOLDOWN_MIN = 45               # anti-pattern 2.7: no back-to-back same-setup churn
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
ENTRY_GATE_START = dt.time(9, 35)   # match prod 09:35 entry gate (no first-bar)
ENTRY_GATE_END = dt.time(15, 45)    # leave room before 15:50 time stop
DEVELOPING_MIN_BARS = 6             # need >= this many closed bars before a developing profile
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# Grid (task spec)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

# Profile-source variants
PROFILE_VARIANTS = ["prior_day", "developing"]

# Self-verify gate thresholds
GATE = {"oos_per_trade": 0.0, "positive_quarters_min": 4, "top5_max_pct": 200.0,
        "n_min": 20, "drop_top5_per_trade_min": 0.0, "is_half_per_trade_min": 0.0}


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ─────────────────────────────────────────────────────────────────────────────
# VOLUME PROFILE: POC / VAH / VAL from a set of bars (price-binned volume)
# ─────────────────────────────────────────────────────────────────────────────
def compute_profile(bars: pd.DataFrame, bin_width: float = BIN_WIDTH,
                    va_frac: float = VALUE_AREA_FRACTION) -> dict | None:
    """Build a volume profile from `bars` -> {poc, vah, val, lo, hi}.

    Each bar's volume is spread across the price bins it spans (typical-price weighting is
    overkill at 5m; we attribute the bar's full volume to its CLOSE bin — the standard
    'last-price' VP approximation, deterministic and causal). Value area = the contiguous
    band of bins around the POC bin that accumulates >= va_frac of total volume, grown by
    the canonical 'add the larger neighbour' rule (Steidlmayer/Dalton).

    Returns None if bars are empty or carry no volume.
    """
    if bars is None or len(bars) == 0:
        return None
    closes = bars["close"].astype(float).to_numpy()
    vols = bars["volume"].astype(float).to_numpy()
    total_vol = float(vols.sum())
    if total_vol <= 0:
        return None

    lo = float(np.floor(closes.min() / bin_width) * bin_width)
    hi = float(np.ceil(closes.max() / bin_width) * bin_width)
    n_bins = max(1, int(round((hi - lo) / bin_width)) + 1)
    edges = lo + bin_width * np.arange(n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0

    bin_idx = np.clip(((closes - lo) / bin_width).astype(int), 0, n_bins - 1)
    vol_by_bin = np.zeros(n_bins, dtype=float)
    np.add.at(vol_by_bin, bin_idx, vols)

    poc_i = int(np.argmax(vol_by_bin))
    poc = float(centers[poc_i])

    # Grow the value area outward from POC by the 'larger-neighbour' rule until >=70% vol.
    target = va_frac * total_vol
    acc = vol_by_bin[poc_i]
    lo_i = hi_i = poc_i
    while acc < target and (lo_i > 0 or hi_i < n_bins - 1):
        down = vol_by_bin[lo_i - 1] if lo_i > 0 else -1.0
        up = vol_by_bin[hi_i + 1] if hi_i < n_bins - 1 else -1.0
        if up >= down:
            hi_i += 1
            acc += vol_by_bin[hi_i] if up >= 0 else 0.0
        else:
            lo_i -= 1
            acc += vol_by_bin[lo_i] if down >= 0 else 0.0
    val = float(centers[lo_i])
    vah = float(centers[hi_i])
    return {"poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2),
            "lo": round(lo, 2), "hi": round(hi, 2), "total_vol": total_vol}


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _drop_top5_per_trade(rows: list[dict]) -> tuple[float, int, float]:
    """Per-trade expectancy after removing the 5 best P&L days."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    top5_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    kept = [r for r in rows if r["date"] not in top5_days]
    dropped_pnl = sum(by_day[d] for d in top5_days)
    if not kept:
        return 0.0, 0, dropped_pnl
    return sum(r["pnl"] for r in kept) / len(kept), len(kept), dropped_pnl


def _is_half_per_trade(rows: list[dict]) -> float | None:
    """First-half-of-IS(2025) per-trade expectancy (gate 6). Split IS rows chronologically
    by date into two halves; return per-trade of the FIRST half (the earliest in-sample
    window — if the edge only appears late in IS it is suspect)."""
    is_rows = sorted([r for r in rows if r["year"] == 2025], key=lambda r: (r["date"], r["time"]))
    if len(is_rows) < 2:
        return None
    half = len(is_rows) // 2
    first = is_rows[:half]
    if not first:
        return None
    return round(sum(r["pnl"] for r in first) / len(first), 2)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL GENERATION — value-edge / POC rejection, fully causal
# ─────────────────────────────────────────────────────────────────────────────
def build_signals(rth: pd.DataFrame, vix_arr: list[float], variant: str) -> list[dict]:
    """One pass over the continuous RTH frame; emit value-area / POC rejection fades.

    variant 'prior_day'   -> fade against the PRIOR session's frozen profile.
    variant 'developing'  -> fade against this session's developing profile (closed bars only).

    Causality (C6): for prior_day the profile is frozen before today opens. For developing the
    profile uses bars[session_open .. idx] (all CLOSED — the trigger bar closes at its own
    timestamp). Entry fills NEXT bar open via simulate_trade_real (no look-ahead).
    """
    rth = rth.reset_index(drop=True)
    rth["date"] = pd.to_datetime(rth["timestamp_et"]).dt.date
    days = sorted(rth["date"].unique())

    # Pre-compute per-day RTH slices and prior-day frozen profiles.
    day_slices: dict = {}
    for d in days:
        sl = rth[rth["date"] == d]
        day_slices[d] = sl
    prior_profile: dict = {}
    for i, d in enumerate(days):
        if i == 0:
            prior_profile[d] = None
        else:
            prior_profile[d] = compute_profile(day_slices[days[i - 1]])

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None

    for d in days:
        sl = day_slices[d]
        idxs = sl.index.to_list()
        if variant == "prior_day":
            prof = prior_profile[d]
            if prof is None:
                continue

        for pos, idx in enumerate(idxs):
            bar = rth.iloc[idx]
            ts = pd.Timestamp(bar["timestamp_et"])
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            bar_dt = ts.to_pydatetime()
            t = bar_dt.time()
            if t < ENTRY_GATE_START or t > ENTRY_GATE_END:
                continue
            bd = bar_dt.date()
            if bd < START or bd > END:
                continue

            if variant == "developing":
                if pos < DEVELOPING_MIN_BARS:
                    continue
                prof = compute_profile(sl.iloc[: pos + 1])  # closed bars incl. trigger bar
                if prof is None:
                    continue

            vah, val, poc = prof["vah"], prof["val"], prof["poc"]
            hi = float(bar["high"]); lo = float(bar["low"]); c = float(bar["close"])

            side = None
            level = None
            tag = None
            # VAH rejection (acceptance fails above value) -> PUT, target POC
            if hi >= vah - EDGE_TOUCH_BUFFER and c < vah:
                side, level, tag = "P", vah, "vah_reject"
            # VAL bounce (acceptance fails below value) -> CALL, target POC
            elif lo <= val + EDGE_TOUCH_BUFFER and c > val:
                side, level, tag = "C", val, "val_bounce"
            # POC first-touch reversal (lower quality): approach POC from above & close back up
            elif lo <= poc + EDGE_TOUCH_BUFFER and lo > val and c > poc and c < vah:
                side, level, tag = "C", poc, "poc_bounce_from_above"
            elif hi >= poc - EDGE_TOUCH_BUFFER and hi < vah and c < poc and c > val:
                side, level, tag = "P", poc, "poc_reject_from_below"

            if side is None:
                continue

            if last_sig_time is not None and (bar_dt - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
                continue

            # Invalidation (chart-stop): acceptance beyond the faded level kills the thesis.
            lo_start = max(idxs[0], idx - SWING_LOOKBACK + 1)
            win = rth.iloc[lo_start: idx + 1]
            if side == "C":
                swing = float(win["low"].min())
                rej = swing if swing < c else round(c - 1.0, 2)
            else:
                swing = float(win["high"].max())
                rej = swing if swing > c else round(c + 1.0, 2)

            last_sig_time = bar_dt
            signals.append({
                "idx": idx, "date": bd, "time": bar_dt.strftime("%H:%M"), "side": side,
                "tag": tag, "level": round(float(level), 2),
                "poc": poc, "vah": vah, "val": val,
                "entry_spot": round(c, 2), "rejection_level": round(float(rej), 2),
                "vix": round(vix_arr[idx], 1) if idx < len(vix_arr) else 0.0,
            })
    return signals


def simulate_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                  premium_stop_pct: float) -> tuple[_Acc, list[dict], int]:
    overall = _Acc()
    rows: list[dict] = []
    no_data = 0
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["volume_profile_poc", s["tag"]],
            side=s["side"], qty=QTY, setup="VOLUME_PROFILE_POC",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "tag": s["tag"],
            "vix": s["vix"], "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2), "year": s["date"].year, "quarter": _quarter(s["date"]),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })
    return overall, rows, no_data


def verify_cell(rows: list[dict]) -> dict:
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    overall = _Acc()
    for r in rows:
        overall.add(r["pnl"], r["date"])
        by_sample["IS_2025" if r["year"] == 2025 else "OOS_2026"].add(r["pnl"], r["date"])
        by_q[r["quarter"]].add(r["pnl"], r["date"])

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for v in q_reports.values() if v.get("total_pnl", 0) and v["total_pnl"] > 0)
    is_r, oos_r = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    drop_pt, n_ex, dropped = _drop_top5_per_trade(rows)
    is_half = _is_half_per_trade(rows)
    ov = overall.report()

    oos_pt = oos_r.get("per_trade") if oos_r.get("n") else None
    clears = bool(
        (oos_pt is not None and oos_pt > GATE["oos_per_trade"]) and
        (pos_q >= GATE["positive_quarters_min"]) and
        (ov.get("top5_day_pct") is not None and ov["top5_day_pct"] < GATE["top5_max_pct"]) and
        (ov["n"] >= GATE["n_min"]) and
        (drop_pt > GATE["drop_top5_per_trade_min"]) and
        (is_half is not None and is_half > GATE["is_half_per_trade_min"])
    )
    return {
        "overall": ov,
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "positive_quarters_n": pos_q,
        "n_quarters": len(q_reports),
        "oos_per_trade": oos_pt,
        "drop_top5_per_trade": round(drop_pt, 2),
        "drop_top5_n": n_ex,
        "dropped_top5_pnl": round(dropped, 0),
        "is_half_per_trade": is_half,
        "top5_day_pct": ov.get("top5_day_pct"),
        "clears_structural": clears,
    }


def run() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_START)
                   & (spy_full["timestamp_et"].dt.time < RTH_END)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) — same pattern as the rsi2 new-hunt
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr: list[float] = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)

    all_variant_summaries: dict = {}
    # global_best: (per_trade, variant, so, ps, rows)
    global_best = None

    for variant in PROFILE_VARIANTS:
        signals = build_signals(rth, vix_arr, variant)
        n_call = sum(1 for s in signals if s["side"] == "C")
        n_put = sum(1 for s in signals if s["side"] == "P")
        tag_ct = defaultdict(int)
        for s in signals:
            tag_ct[s["tag"]] += 1
        log.info("[%s] signals=%d (CALL=%d PUT=%d) tags=%s", variant, len(signals), n_call, n_put, dict(tag_ct))

        cells = []
        for so in STRIKE_OFFSETS:
            for ps in PREMIUM_STOPS:
                overall, rows, no_data = simulate_cell(rth, signals, so, ps)
                rep = overall.report()
                cells.append({"strike_offset": so, "premium_stop_pct": ps,
                              "report": rep, "n_no_opra_data": no_data, "_rows": rows})
                pt = rep.get("per_trade")
                log.info("  [%s] so=%+d ps=%.2f -> n=%s per_trade=%s total=%s top5%%=%s",
                         variant, so, ps, rep.get("n"), pt, rep.get("total_pnl"), rep.get("top5_day_pct"))
                if pt is not None and rep.get("n", 0) >= GATE["n_min"]:
                    if global_best is None or pt > global_best[0]:
                        global_best = (pt, variant, so, ps, rows)

        # capture per-strike chart-stop-only cells for the truncation cross-check
        ranked = sorted([c for c in cells if c["report"].get("per_trade") is not None],
                        key=lambda c: c["report"]["per_trade"], reverse=True)
        # survivor (ITM-2/-8%) + ATM (Safe-2 tier) explicit reports per task spec
        def _cell(so, ps):
            for c in cells:
                if c["strike_offset"] == so and c["premium_stop_pct"] == ps:
                    return c["report"]
            return None
        all_variant_summaries[variant] = {
            "n_signals": len(signals), "n_call": n_call, "n_put": n_put, "tags": dict(tag_ct),
            "survivor_itm2_8pct": _cell(-2, -0.08),
            "atm_safe2_8pct": _cell(0, -0.08),
            "cells": [{k: v for k, v in c.items() if k != "_rows"} for c in ranked],
            # keep rows of chart-stop-only cells (for truncation guard lookups)
            "_chartstop_rows": {so: next((c["_rows"] for c in cells
                                          if c["strike_offset"] == so and c["premium_stop_pct"] == -0.99), [])
                                for so in STRIKE_OFFSETS},
        }

    # ── 8-gate verification on the GLOBAL best cell (per-trade, n>=20) ──
    best_block = None
    if global_best is not None:
        pt, variant, so, ps, rows = global_best
        verify = verify_cell(rows)
        n_call_best = sum(1 for r in rows if r["side"] == "C")
        n_put_best = sum(1 for r in rows if r["side"] == "P")

        # Gate 7: random-entry NULL (L172, C3/L58 structure-vs-signal probe)
        log.info("Running random-entry NULL for best cell (%s so=%+d ps=%.2f)...", variant, so, ps)
        null = random_entry_null(rth, n_signals=len(rows), n_call=n_call_best,
                                 n_put=n_put_best, strike_offset=so, premium_stop_pct=ps,
                                 entry_gate=(ENTRY_GATE_START, ENTRY_GATE_END),
                                 swing_lookback=SWING_LOOKBACK, qty=QTY)
        gate = null_gate(pt, verify["drop_top5_per_trade"], null)
        null.update({
            "edge_over_null_per_trade": gate["edge_over_null_per_trade"],
            "beats_null_mean": gate["beats_null_mean"],
            "beats_null_max": gate["beats_null_max"],
            "drop_top5_beats_null_mean": gate["drop_top5_beats_null_mean"],
            "null_pass": gate["null_pass"],
        })

        # Gate 8: truncation artifact (L171) — same-strike chart-stop-only sign hold.
        chartstop_rows = all_variant_summaries[variant]["_chartstop_rows"].get(so, [])
        cs_overall = _Acc()
        for r in chartstop_rows:
            cs_overall.add(r["pnl"], r["date"])
        cs_rep = cs_overall.report()
        chart_stop_only_pt = cs_rep.get("per_trade") if cs_rep.get("n") else None
        trunc_artifact = is_truncation_artifact(
            best_per_trade=pt, chart_stop_only_per_trade=chart_stop_only_pt,
            best_premium_stop_pct=ps)
        # no-truncation gate PASSES when NOT an artifact.
        truncation_safe = not trunc_artifact

        best_block = {
            "variant": variant, "strike_offset": so, "premium_stop_pct": ps,
            "per_trade": pt, "verify": verify, "random_entry_null": null,
            "truncation": {"chart_stop_only_per_trade": chart_stop_only_pt,
                           "is_artifact": trunc_artifact, "truncation_safe": truncation_safe,
                           "n_chartstop": cs_rep.get("n")},
            "sample_rows": rows[:25],
        }
        log.info("=== GLOBAL BEST: %s so=%+d ps=%.2f per_trade=%.2f ===", variant, so, ps, pt)
        log.info("    verify: %s", {k: verify[k] for k in
                 ("overall", "by_sample", "positive_quarters", "oos_per_trade",
                  "drop_top5_per_trade", "is_half_per_trade", "top5_day_pct", "clears_structural")})
        log.info("    NULL: mean=%s max=%s beats_max=%s drop_beats_mean=%s | trunc_safe=%s (cs_pt=%s)",
                 null["per_trade_mean"], null["per_trade_max"], null["beats_null_max"],
                 null["drop_top5_beats_null_mean"], truncation_safe, chart_stop_only_pt)

    # ── Final 8-gate verdict (no cherry-pick: uses the per-trade-BEST cell) ──
    def _gate_flags(bb) -> dict:
        v = bb["verify"]; nl = bb["random_entry_null"]; tr = bb["truncation"]
        return {
            "oos_per_trade_gt0": bool(v["oos_per_trade"] is not None and v["oos_per_trade"] > 0),
            "positive_quarters_ge4": bool(v["positive_quarters_n"] >= GATE["positive_quarters_min"]),
            "top5_lt200": bool(v["top5_day_pct"] is not None and v["top5_day_pct"] < GATE["top5_max_pct"]),
            "n_ge20": bool(v["overall"]["n"] >= GATE["n_min"]),
            "drop_top5_gt0": bool(v["drop_top5_per_trade"] > 0),
            "is_half_gt0": bool(v["is_half_per_trade"] is not None and v["is_half_per_trade"] > 0),
            "beats_null": bool(nl["null_pass"]),
            "no_truncation": bool(tr["truncation_safe"]),
        }

    if best_block is None:
        clears_all_gates = False
        gate_flags = {}
        verdict = "NO_CANDIDATE: no cell reached n>=20 — volume-profile reversal too sparse on SPY 0DTE"
    else:
        gate_flags = _gate_flags(best_block)
        clears_all_gates = all(gate_flags.values())
        if clears_all_gates:
            verdict = ("REAL CANDIDATE: best cell clears ALL 8 gates — volume-profile POC/value-area "
                       "rejection adds per-trade edge beyond exit structure + day-concentration.")
        else:
            fails = [k for k, ok in gate_flags.items() if not ok]
            v = best_block["verify"]; nl = best_block["random_entry_null"]; tr = best_block["truncation"]
            detail = {
                "oos_per_trade": v["oos_per_trade"], "positive_quarters": v["positive_quarters"],
                "top5_day_pct": v["top5_day_pct"], "n": v["overall"]["n"],
                "drop_top5_per_trade": v["drop_top5_per_trade"], "is_half_per_trade": v["is_half_per_trade"],
                "null_max": nl["per_trade_max"], "null_mean": nl["per_trade_mean"],
                "edge_over_null": nl["edge_over_null_per_trade"],
                "chart_stop_only_per_trade": tr["chart_stop_only_per_trade"],
            }
            verdict = (f"NOT A CANDIDATE (no cherry-pick): per-trade-best cell fails gate(s) {fails}. "
                       f"detail={detail}")

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "volume_profile_poc",
        "kind": "novel-data",
        "hypothesis": ("Volume-profile POC / value-area rejection (market profile / TPO): build a "
                       "session/prior-day volume profile; fade rejections at POC + value-area-high/low "
                       "back toward value. Engine has VWAP/levels/pivots but NO volume-profile layer."),
        "window": f"{START}..{END}",
        "sourced_rules": {
            "profile": "price-binned volume; POC=max-volume bin; value area=70% of vol around POC "
                       "(Steidlmayer/Dalton, TradingView VRVP)",
            "entry": "VAH rejection->PUT(target POC); VAL bounce->CALL(target POC); POC first-touch "
                     "reversal = lower-quality variant; all faded back into value",
            "invalidation": "chart-stop beyond the faded value-edge (acceptance kills the fade)",
            "exits": "v15 production intraday stack (TP1 +30%/chart-level, BE runner, 15:50 time stop)",
            "published_edge_caveat": "profile lore is an UNDERLYING context/probability framing, NOT a "
                                     "0DTE option edge (C4/L58); real fills are the test",
        },
        "sources": [
            "https://www.tradingview.com/support/solutions/43000502040-volume-profile/",
            "Dalton, Mind Over Markets (value area = 70% of volume around POC)",
            "CME Group, A Six-Part Study Guide to Market Profile",
        ],
        "adaptation": {
            "instrument": "SPY 0DTE single-leg directional (fade->CALL/PUT)",
            "bin_width": BIN_WIDTH, "value_area_fraction": VALUE_AREA_FRACTION,
            "edge_touch_buffer": EDGE_TOUCH_BUFFER, "swing_lookback_bars": SWING_LOOKBACK,
            "cooldown_min": COOLDOWN_MIN, "entry_gate": f"{ENTRY_GATE_START}-{ENTRY_GATE_END}",
            "profile_variants": PROFILE_VARIANTS, "developing_min_bars": DEVELOPING_MIN_BARS,
            "qty": QTY, "timeframe": "5min RTH", "causality": "C6 — profile from CLOSED bars only; "
            "prior_day profile frozen at open; entry fills NEXT bar open",
        },
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS,
                 "profile_variants": PROFILE_VARIANTS},
        "self_verify_gate": GATE,
        "all_8_gates": [
            "1 OOS(2026) per-trade>0", "2 positive_quarters>=4/6", "3 top5_day_pct<200",
            "4 n>=20", "5 drop-top5 per-trade>0", "6 IS(2025)-half per-trade>0",
            "7 beats random-entry NULL (L172)", "8 no truncation artifact (L171)",
        ],
        "variants": {k: {kk: vv for kk, vv in v.items() if kk != "_chartstop_rows"}
                     for k, v in all_variant_summaries.items()},
        "best_cell": best_block,
        "gate_flags": gate_flags,
        "clears_all_gates": clears_all_gates,
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14)",
            "is_oos": "IS=2025, OOS=2026 + IS-first-half gate shown for the best cell",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5; anti-pattern 2.10)",
            "no_cherry_pick": "verdict uses the per-trade-BEST cell across BOTH profile variants and the "
                              "full strike x stop grid; thin-N/high-conc/OOS-neg cells say so",
            "spy_vs_option": "C3/L58 — a SPY-price/underlying profile read is NOT an option edge; "
                             "theta+delta+stop-misfire routinely erase a directional-underlying edge in 0DTE",
            "random_entry_null": "L172 — best cell vs coin-flip null (random RTH entries, same count/side-"
                                 "mix/stop/strike). Must beat null MAX + drop-top5 beats null MEAN.",
            "truncation_guard": "L171 — same-strike chart-stop-only sign must hold (a tight stop can "
                                "manufacture a positive average by truncating losers).",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== VOLUME_PROFILE_POC B4 NOVEL-DATA HUNT VERDICT ===")
    for variant, vs in all_variant_summaries.items():
        top = vs["cells"][0] if vs["cells"] else None
        print(f"[{variant}] n_signals={vs['n_signals']} (CALL={vs['n_call']} PUT={vs['n_put']}) tags={vs['tags']}")
        print(f"    survivor ITM-2/-8%: {vs['survivor_itm2_8pct']}")
        print(f"    ATM Safe-2/-8%:     {vs['atm_safe2_8pct']}")
        print(f"    best_cell={top['report'] if top else None} "
              f"(so={top['strike_offset'] if top else '-'} ps={top['premium_stop_pct'] if top else '-'})")
    if best_block:
        v = best_block["verify"]
        print(f"\nGLOBAL BEST: {best_block['variant']} so={best_block['strike_offset']:+d} "
              f"ps={best_block['premium_stop_pct']}  per_trade={best_block['per_trade']}")
        print(f"  overall={v['overall']}")
        print(f"  IS={v['by_sample']['IS_2025']}  OOS={v['by_sample']['OOS_2026']}")
        print(f"  positive_quarters={v['positive_quarters']}  oos_per_trade={v['oos_per_trade']}  "
              f"is_half_per_trade={v['is_half_per_trade']}")
        print(f"  drop_top5_per_trade={v['drop_top5_per_trade']} (n={v['drop_top5_n']})  "
              f"top5_day_pct={v['top5_day_pct']}")
        nl = best_block["random_entry_null"]
        print(f"  NULL per_trade mean={nl['per_trade_mean']} [{nl['per_trade_min']}..{nl['per_trade_max']}]  "
              f"beats_max={nl['beats_null_max']} drop_beats_mean={nl['drop_top5_beats_null_mean']}")
        tr = best_block["truncation"]
        print(f"  TRUNCATION chart_stop_only_pt={tr['chart_stop_only_per_trade']} safe={tr['truncation_safe']}")
        print(f"  GATE FLAGS: {gate_flags}")
    print(f"\nCLEARS ALL 8 GATES: {clears_all_gates}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    run()
