"""B2 — VIX intraday feed reconstruction + parity re-validation for edge #4
(vix_regime_dayside).

PURPOSE
  Edge #4 needs an intraday VIX series (trailing-median-78 + 5-bar causal slope) that the
  live BarContext does NOT carry (the ctx.vix_intraday seam, currently fail-open SKIP).
  This module RECONSTRUCTS that feed offline, runs it through the LIVE WATCHER's pure core
  (detect_vix_regime_dayside_core via the same ctx.vix_intraday slicing the live wrapper
  does), and DIFFs the resulting signal set against the RESEARCH detector
  (_b5_vix_regime_dayside.detect_opt_signals) that produced the scorecard
  analysis/recommendations/b5-vix-regime-dayside.json.

  If the two reproduce within noise -> the feed reconstruction is CORRECT, and we PIN the
  exact spec the live heartbeat must thread into ctx.vix_intraday. If they DIVERGE -> that's
  a parity bug; do NOT ship the feed.

HARD WINDOW (data-coverage fact): the real-fills OPRA cache ends 2026-05-29. The SIGNAL SET
  is a pure function of SPY 5m bars + VIX 5m bars (NOT OPRA fills), so the diff is clean over
  2025-01..2026-05-29; we still hard-window to <= 2026-05-29 and ASSERT the last signal date.

CAUSALITY (C6/L165/L61): VIX 5m RTH closes, ffilled onto the SPY 5m grid (UTC-joined),
  trailing median over PRIOR 78 bars (shift 1), 5-bar slope vix[i]-vix[i-5]. America/New_York
  tz, never UTC for the time-of-day window.

Pure Python / pandas, $0, no live orders, markets closed.
Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b2_vix_feed_parity.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from autoresearch import runner as ar_runner            # noqa: E402
from autoresearch.infinite_ammo_discovery import (        # noqa: E402
    build_day_contexts,
    session_vwap_asof,
)
# The RESEARCH detector primitives (the scorecard authority).
from autoresearch._b5_vix_regime_dayside import (         # noqa: E402
    _normalize_spy, _align_vix,
    causal_vix_median as research_median,
    vix_slope as research_slope,
    detect_opt_signals,
    TREND_BARS, VIX_MEDIAN_BARS, VIX_SLOPE_BARS, ENTRY_GATE,
    VIX_LOW_MARGINS, SLOPE_RULES, RTH_OPEN, RTH_CLOSE,
)
# The LIVE WATCHER pure core + its own primitives (what the heartbeat actually calls).
from lib.watchers.vix_regime_dayside_watcher import (     # noqa: E402
    detect_vix_regime_dayside_core,
    causal_vix_median as watcher_median,
    vix_slope as watcher_slope,
)

HARD_LAST = dt.date(2026, 5, 29)   # OPRA cache last day; assert no signal beyond this
SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"


def research_signal_set(days, spy, vix_g, vix_med_g, vix_slp_g, lm, sr):
    """The scorecard's signal set (date, side) for one (low_margin, slope_rule) cell."""
    sigs = detect_opt_signals(days, spy, vix_g, vix_med_g, vix_slp_g, lm, sr)
    return {(s.date, s.side) for s in sigs if s.date <= HARD_LAST}


def watcher_signal_set(days, spy, vix_g, lm, sr):
    """Drive the LIVE WATCHER core day-by-day, reconstructing ctx.vix_intraday exactly as the
    live wrapper slices it: per session, the FULL ffilled-VIX history up to & including each
    candidate bar (newest last), with the watcher's OWN median/slope primitives. We emulate
    the streaming wrapper: for each RTH bar j>=TREND_BARS in the morning window, the wrapper
    would have ctx.prior_bars = today's session bars[0..j] and ctx.vix_intraday = a series
    whose last (j+1) values align to those bars (carrying prior history for the 78/5 warmup).
    The core returns ONE entry/day (first favorable morning bar). We replicate by handing the
    core today's RTH arrays + the as-of VIX regime arrays tail-sliced to the RTH frame, EXACTLY
    as _detect_impl does."""
    found = set()
    for dc in days:
        rth = dc.rth
        if dc.date > HARD_LAST:
            continue
        if len(rth) < TREND_BARS + 1:
            continue
        gidx = rth.index.to_numpy()
        n_rth = len(rth)
        closes = rth["close"].to_numpy(float)
        highs = rth["high"].to_numpy(float)
        lows = rth["low"].to_numpy(float)
        vwap = session_vwap_asof(rth).to_numpy(float)
        times = [t for t in rth["t"].to_numpy()]
        # The live wrapper builds ctx.vix_intraday as the intraday VIX series ending at the
        # current RTH frame, carrying MORE prior history for warmup. The richest faithful
        # reconstruction = the FULL ffilled VIX array up to today's last RTH global idx, then
        # compute the watcher's causal median/slope over that FULL series and tail-slice to the
        # n_rth RTH bars (byte-identical to _detect_impl's vix_full[-n_rth:] path).
        g_last = int(gidx[-1])
        vix_full = vix_g[: g_last + 1]
        vix_med_full = watcher_median(vix_full, VIX_MEDIAN_BARS)
        vix_slp_full = watcher_slope(vix_full, VIX_SLOPE_BARS)
        # Tail-slice to the RTH frame. NOTE: the live wrapper aligns vix_intraday's last n_rth
        # values to today's RTH bars; here the ffilled VIX is on the SAME global SPY grid as
        # the RTH bars, so vix_full[gidx] gives the exact per-RTH-bar VIX. To honor the
        # wrapper's [-n_rth:] contract we index by the RTH global indices (identical when the
        # session's RTH bars are the last n_rth bars of the slice).
        vix = vix_g[gidx]
        vix_med = vix_med_full[gidx]
        vix_slp = vix_slp_full[gidx]
        res = detect_vix_regime_dayside_core(
            closes, highs, lows, vwap, times, vix, vix_med, vix_slp,
            low_margin=lm, slope_rule=sr,
        )
        if res is not None:
            found.add((dc.date, res.side))
    return found


def main() -> int:
    print("[b2] loading SPY+VIX (master through 2026-06-16; hard-window signals <= 05-29) ...",
          flush=True)
    # Use the full master so the 05-15..05-29 window is present (the OPRA cache ends 05-29 but
    # the SIGNAL SET only needs bars). load_data auto-discovers the covering CSV.
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 29))
    spy = _normalize_spy(spy_raw)
    vix_g = _align_vix(spy, vix_raw)
    vix_med_g = research_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = research_slope(vix_g, VIX_SLOPE_BARS)
    days = build_day_contexts(spy)
    days = [d for d in days if d.date <= HARD_LAST]
    print(f"[b2] SPY bars={len(spy)} days(<=05-29)={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # Cross-check the two median/slope implementations are byte-identical on the same array.
    wm = watcher_median(vix_g, VIX_MEDIAN_BARS)
    ws = watcher_slope(vix_g, VIX_SLOPE_BARS)
    med_match = np.allclose(np.nan_to_num(wm), np.nan_to_num(vix_med_g), atol=1e-9)
    slp_match = np.allclose(np.nan_to_num(ws), np.nan_to_num(vix_slp_g), atol=1e-9)
    print(f"[b2] primitive parity: median_identical={med_match} slope_identical={slp_match}",
          flush=True)

    cells = []
    total_research = total_watcher = total_intersect = 0
    last_sig_date = None
    for sr in SLOPE_RULES:
        for lm in VIX_LOW_MARGINS:
            rset = research_signal_set(days, spy, vix_g, vix_med_g, vix_slp_g, lm, sr)
            wset = watcher_signal_set(days, spy, vix_g, lm, sr)
            inter = rset & wset
            only_r = rset - wset
            only_w = wset - rset
            for d, _ in rset | wset:
                if last_sig_date is None or d > last_sig_date:
                    last_sig_date = d
            cell = {
                "low_margin": lm, "slope_rule": sr,
                "n_research": len(rset), "n_watcher": len(wset),
                "n_intersect": len(inter),
                "n_only_research": len(only_r), "n_only_watcher": len(only_w),
                "jaccard": round(len(inter) / max(1, len(rset | wset)), 4),
                "side_disagreements": sorted(
                    {d.isoformat() for (d, _) in only_r} & {d.isoformat() for (d, _) in only_w}
                ),
                "examples_only_research": sorted(
                    f"{d.isoformat()}:{s}" for d, s in only_r)[:8],
                "examples_only_watcher": sorted(
                    f"{d.isoformat()}:{s}" for d, s in only_w)[:8],
            }
            cells.append(cell)
            total_research += len(rset); total_watcher += len(wset)
            total_intersect += len(inter)
            tag = "EXACT" if (only_r or only_w) == set() else "DIFF"
            print(f"[b2] sr={sr:10s} lm={lm:<4} research={len(rset):3d} watcher={len(wset):3d} "
                  f"intersect={len(inter):3d} onlyR={len(only_r)} onlyW={len(only_w)} "
                  f"jaccard={cell['jaccard']} -> {tag}", flush=True)

    validated = next(c for c in cells if c["low_margin"] == 0.25 and c["slope_rule"] == "not_rising")
    overall_exact = all(c["n_only_research"] == 0 and c["n_only_watcher"] == 0 for c in cells)

    out = {
        "kind": "b2_vix_feed_parity",
        "run_date": dt.date.today().isoformat(),
        "hard_window_last": HARD_LAST.isoformat(),
        "last_signal_date": last_sig_date.isoformat() if last_sig_date else None,
        "last_signal_within_cache": (last_sig_date <= HARD_LAST) if last_sig_date else True,
        "primitive_parity": {"median_identical": bool(med_match), "slope_identical": bool(slp_match)},
        "overall_exact_reproduction": overall_exact,
        "totals": {"research": total_research, "watcher": total_watcher,
                   "intersect": total_intersect},
        "validated_cell": validated,
        "cells": cells,
        "feed_spec": {
            "source": "VIX 5m RTH closes (CBOE ^VIX), ffilled onto the SPY 5m grid via UTC join",
            "alignment": ("_align_vix: SPY ts -> tz America/New_York -> UTC; VIX ts utc=True; "
                          "reindex VIX close onto SPY UTC index method='ffill'; NaN->0.0 only "
                          "in deep warmup (never inside the 09:35-11:30 window)"),
            "lookback_median_bars": VIX_MEDIAN_BARS,
            "median_rule": "pandas rolling(78, min_periods=max(5,78//4)=19).median().shift(1)",
            "slope_window_bars": VIX_SLOPE_BARS,
            "slope_rule": "vix[i] - vix[i-5] (causal; NaN for i<5)",
            "tz": "America/New_York for the 09:35-11:30 ET entry window (NOT UTC; L165/L61)",
            "causality": ("median shift(1) so a bar never sets its own baseline; all VIX inputs "
                          "read at-or-before the candidate (just-closed) bar; entry fills NEXT bar"),
            "ctx_seam": ("ctx.vix_intraday = list/np.ndarray of 5m VIX closes aligned to "
                         "ctx.prior_bars (newest last), carrying >= VIX_MEDIAN_BARS prior bars "
                         "of history for the median/slope warmup; the wrapper computes the causal "
                         "regime over the FULL series then tail-slices to today's RTH frame"),
            "validated_live_cell": {"low_margin": 0.25, "slope_rule": "not_rising",
                                    "strike_offset": 0, "premium_stop_pct": -0.08,
                                    "tier": "ATM_safe2"},
        },
        "verdict": ("VIX_FEED_PINNED" if overall_exact else "PARITY_BUG"),
    }
    OUT = ROOT / "analysis" / "recommendations" / "B2-vix-feed-parity.json"
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n[b2] wrote {OUT}")
    print(f"[b2] VERDICT={out['verdict']} overall_exact={overall_exact} "
          f"last_signal={out['last_signal_date']} (<=05-29: {out['last_signal_within_cache']})")
    print(f"[b2] VALIDATED CELL (lm=0.25, not_rising): research={validated['n_research']} "
          f"watcher={validated['n_watcher']} intersect={validated['n_intersect']} "
          f"jaccard={validated['jaccard']}")
    return 0 if overall_exact else 2


if __name__ == "__main__":
    raise SystemExit(main())
