"""Dump the signal-day set for vwap_continuation (+ a dead family) so the DTE backfill
knows EXACTLY which trade days T and ATM strikes to fetch. Reuses the byte-for-byte
detectors. Writes backtest/tools/_dte_signal_days.json. Pure python, $0."""
from __future__ import annotations
import datetime as dt, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]; ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path: sys.path.insert(0, p)
import pandas as pd
from autoresearch import runner as ar_runner
from autoresearch.infinite_ammo_discovery import build_day_contexts, _strike_from_spot, detect_orb_rvol, detect_intraday_momentum, detect_gap_fade, detect_power_hour, detect_vwap_pullback
from lib.ribbon import compute_ribbon
from autoresearch._edgehunt_vwap_continuation import detect_signals as detect_vwap, _normalize_spy, _align_vix
# #2 vwap_reclaim_failed_break — byte-for-byte detector (Signal: bar_idx, side, stop_level)
from autoresearch._sub_struct_vwap_reclaim_failed_break import detect_signals as detect_reclaim_fb
# #4 vix_regime_dayside — byte-for-byte detector (OptSig: gidx, date, side) + its sweep + VIX prep
from autoresearch._b5_vix_regime_dayside import (
    detect_opt_signals as detect_vix_dayside,
    causal_vix_median, vix_slope,
    VIX_MEDIAN_BARS, VIX_SLOPE_BARS, VIX_LOW_MARGINS, SLOPE_RULES,
    _align_vix as _b5_align_vix,
)

spy_raw, vix_raw = ar_runner.load_data(dt.date(2025,1,1), dt.date(2026,6,16))
spy = _normalize_spy(spy_raw); vix = _align_vix(spy, vix_raw)
days = build_day_contexts(spy)
print(f"trading_days={len(days)} window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}")

def dump(name, sigs):
    rows=[]
    for s in sigs:
        bar = spy.iloc[s.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"]); atm = _strike_from_spot(spot)
        rows.append({"date": d.isoformat(), "side": s.side, "atm": int(atm), "spot": round(spot,2), "note": s.note})
    sd = sorted({r["date"] for r in rows})
    print(f"  {name}: {len(rows)} signals on {len(sd)} days  C={sum(1 for r in rows if r['side']=='C')} P={sum(1 for r in rows if r['side']=='P')}")
    return rows

ribbon = compute_ribbon(pd.Series(spy["close"].values))  # power_hour reads ribbon stack

out={}
out["vwap_continuation"] = dump("vwap_continuation", detect_vwap(days, vix, breakout_only=False, put_needs_rising_vix=False))
# DEAD/MARGINAL directional families = the THETA-KILL resurrection probe (NOT fades).
# momentum_morning + orb_continuation + power_hour are right-direction theta-killed at 0DTE.
# vwap_pullback is the trend-ride POSITIVE-CONTROL (already alive at 0DTE => theta-lift ceiling).
# gap_fade kept for reference only (mean-reversion; dead for non-theta reasons -> L173 fail).
for nm, fn in (("orb_continuation", detect_orb_rvol),
               ("momentum_morning", detect_intraday_momentum),
               ("power_hour", detect_power_hour),
               ("vwap_pullback", detect_vwap_pullback),
               ("gap_fade", detect_gap_fade)):
    try:
        out[nm] = dump(nm, fn(spy, ribbon, vix, days))
    except Exception as e:
        print(f"  {nm}: ERR {e!r}")
        out[nm]=[]

# ── #2 vwap_reclaim_failed_break — long-premium directional, the -8%->dollar-stop lever target.
#    Detector returns Signal(bar_idx, side, stop_level) directly => reuse dump() byte-for-byte.
out["vwap_reclaim_failed_break"] = dump("vwap_reclaim_failed_break", detect_reclaim_fb(days))

# ── #4 vix_regime_dayside — long-premium directional, dormant. Detector is PARAM-SWEPT
#    (low_margin x slope_rule). For the backfill we need option bars for EVERY day ANY sweep
#    cell could fire, so we take the UNION of (date, side) across the full sweep. We rebuild the
#    SAME causal VIX features the b5 module builds (byte-for-byte: _align_vix on b5's normalized
#    SPY index, causal trailing median + 5-bar slope), then dedupe to one Signal/day-side at the
#    EARLIEST firing bar (the backfill only needs the trade DAY + SIDE + ATM, not the exact bar).
class _Sig:
    __slots__ = ("bar_idx", "side", "note")
    def __init__(self, bar_idx, side, note=""):
        self.bar_idx = bar_idx; self.side = side; self.note = note

vix_g = _b5_align_vix(spy, vix_raw)            # b5's own VIX alignment (no drift)
vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
seen = {}   # (date, side) -> earliest gidx
for slope_rule in SLOPE_RULES:
    for lm in VIX_LOW_MARGINS:
        for os in detect_vix_dayside(days, spy, vix_g, vix_med_g, vix_slp_g, lm, slope_rule):
            k = (os.date, os.side)
            if k not in seen or os.gidx < seen[k]:
                seen[k] = os.gidx
vix_sigs = [_Sig(gidx, side, f"vix_regime_dayside_union") for (d, side), gidx in seen.items()]
out["vix_regime_dayside"] = dump("vix_regime_dayside", vix_sigs)

(Path(__file__).resolve().parent/"_dte_signal_days.json").write_text(json.dumps(out, indent=2))
print("wrote _dte_signal_days.json")
