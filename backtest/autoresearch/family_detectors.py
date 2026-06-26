"""Brand-NEW 0DTE entry detectors for the family-grind (real OPRA fills downstream).

Four genuinely-new ENTRIES (not strike/exit variations of the live ribbon-ride edge),
sourced from the SwjshAlgoKnife extraction shortlist
(markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md):

  1. supply_demand_zone   — fresh impulse-candle S/D zone, reversal on first retest (09:30-11:00)
  2. ema_adx              — EMA(9/21) cross GATED by ADX(14) > 25 (trend, not chop)
  3. three_ducks          — intraday multi-timeframe SMA alignment (5m/15m/30m agree)
  4. bollinger_squeeze    — BB(20,2) bandwidth squeeze -> expansion breakout + volume

Each `detect_*` scans the RTH 5-min SPY frame ONCE and returns a list of signal dicts:
    {date, time, bar_idx, side, entry_spot, rejection_level, meta...}
where `bar_idx` is the POSITIONAL index into the passed `rth` frame (the same frame the
caller hands to simulate_trade_real as spy_df) and `side` is "C" (call/bullish) or "P"
(put/bearish). The entry FILLS on the next bar (simulate_trade_real convention) -> the
decision at bar i uses only bar i's CLOSED values (no look-ahead, C6).

CAUSALITY DISCIPLINE (C6 / L14,34,57,61):
  - SMA / EMA: continuous causal smoothers over the RTH series (rolling / ewm, no future
    bars). Level smoothers are overnight-gap-robust and give the MTF detector real
    higher-timeframe context.
  - ATR / ADX / Bollinger(std): computed PER SESSION (reset each calendar date) so an
    overnight gap never injects a spurious true-range / stdev spike at the open.
  - Squeeze percentile: trailing causal window WITHIN the session (<= current bar).
  - Cross / breakout checks read only bars i and i-1.

STOP GEOMETRY (null parity): every signal's `rejection_level` is the SAME 12-bar swing
invalidation the random-entry null uses (null_baseline._swing_invalidation). This makes
the null a clean ENTRY-TIMING control: signal vs random differ ONLY in WHERE the entry
is, not in the stop geometry (C3/L58/L171). The detector decides WHEN/WHERE to enter; the
exit bracket (swept by the harness) and the swing stop are held identical to the null.

Pure Python, $0. No LLM, no orders, no production module touched.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent          # backtest/
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch.null_baseline import _swing_invalidation  # noqa: E402 — shared stop geometry

# ── shared windows / params ──────────────────────────────────────────────────
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ENTRY_GATE = (dt.time(9, 35), dt.time(15, 45))    # general entry window (matches null default)
COOLDOWN_MIN = 30                                  # min gap between same-family signals
SWING_LOOKBACK = 12                               # swing-stop lookback (== null default)

SIDE_CALL = "C"
SIDE_PUT = "P"


# ── frame prep ───────────────────────────────────────────────────────────────
def build_rth(spy: pd.DataFrame) -> pd.DataFrame:
    """RTH-only frame with a reset RangeIndex + tz-naive timestamp_et + a `date` column.
    Positional index == the bar_idx every detector emits and simulate_trade_real consumes."""
    df = spy.copy()
    ts = pd.to_datetime(df["timestamp_et"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    df["timestamp_et"] = ts
    times = ts.dt.time
    df = df[(times >= RTH_OPEN) & (times < RTH_CLOSE)].reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    return df


def _in_window(t: dt.time, window: tuple[dt.time, dt.time]) -> bool:
    return window[0] <= t <= window[1]


# ── causal indicators ────────────────────────────────────────────────────────
def sma_continuous(close: pd.Series, n: int) -> np.ndarray:
    """Causal SMA over the RTH series (no per-session reset; level smoother)."""
    return close.rolling(n, min_periods=n).mean().to_numpy()


def ema_continuous(close: pd.Series, n: int) -> np.ndarray:
    """Causal EMA over the RTH series (ewm adjust=False; standard, gap-robust)."""
    return close.ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def _wilder_rma(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder smoothing (RMA): seed = mean of first n, then rma[i]=(rma[i-1]*(n-1)+x[i])/n.
    Leading values (< n) are NaN. Operates on ONE session's array."""
    m = len(x)
    out = np.full(m, np.nan)
    if m < n:
        return out
    seed = np.nanmean(x[:n])
    out[n - 1] = seed
    for i in range(n, m):
        prev = out[i - 1]
        xi = x[i]
        if np.isnan(prev) or np.isnan(xi):
            out[i] = prev
            continue
        out[i] = (prev * (n - 1) + xi) / n
    return out


def atr_session(high, low, close, n: int) -> np.ndarray:
    """Wilder ATR for ONE session (TR[0]=high-low; no cross-session prior close)."""
    m = len(close)
    tr = np.full(m, np.nan)
    if m == 0:
        return tr
    tr[0] = high[0] - low[0]
    for i in range(1, m):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return _wilder_rma(tr, n)


def adx_session(high, low, close, n: int) -> np.ndarray:
    """Wilder ADX for ONE session. Returns the ADX array (NaN until ~2n bars warm up).

    +DM/-DM directional movement -> Wilder-smoothed -> +DI/-DI -> DX -> ADX (RMA of DX).
    Standard Wilder construction; values stabilise after ~2*n bars."""
    m = len(close)
    adx = np.full(m, np.nan)
    nan_di = np.full(m, np.nan)
    if m < 2 * n:
        return adx, nan_di, nan_di.copy()
    tr = np.full(m, np.nan)
    plus_dm = np.zeros(m)
    minus_dm = np.zeros(m)
    tr[0] = high[0] - low[0]
    for i in range(1, m):
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = _wilder_rma(tr, n)
    pdm = _wilder_rma(plus_dm, n)
    mdm = _wilder_rma(minus_dm, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * pdm / atr
        mdi = 100.0 * mdm / atr
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    dx = np.where(np.isfinite(dx), dx, np.nan)
    # ADX = Wilder RMA of DX, but DX itself only exists from index n-1; seed the ADX RMA
    # over the first n VALID DX values (Wilder's standard 2n warmup).
    first = n - 1
    valid = dx[first:]
    if len(valid) < n:
        return adx, pdi, mdi
    adx_tail = _wilder_rma(valid, n)
    adx[first:] = adx_tail
    return adx, pdi, mdi


def per_session(rth: pd.DataFrame, fn: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
                ncols: int = 1):
    """Apply a per-session OHLC function, scattering results into full-length array(s).
    `fn(high, low, close) -> ndarray or tuple-of-ndarray`. Returns ndarray or tuple."""
    n = len(rth)
    outs = [np.full(n, np.nan) for _ in range(ncols)]
    h = rth["high"].to_numpy(); lo = rth["low"].to_numpy(); c = rth["close"].to_numpy()
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        res = fn(h[idx], lo[idx], c[idx])
        if not isinstance(res, tuple):
            res = (res,)
        for k in range(ncols):
            outs[k][idx] = res[k]
    return outs[0] if ncols == 1 else tuple(outs)


def bollinger_session(rth: pd.DataFrame, n: int = 20, k: float = 2.0):
    """Per-session Bollinger mid/upper/lower/bandwidth (population stdev, TV ta.stdev)."""
    N = len(rth)
    mid = np.full(N, np.nan); up = np.full(N, np.nan)
    lo = np.full(N, np.nan); bw = np.full(N, np.nan)
    close = rth["close"]
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        s = close.loc[idx]
        m = s.rolling(n, min_periods=n).mean()
        sd = s.rolling(n, min_periods=n).std(ddof=0)   # population stdev (TV convention)
        u = m + k * sd
        d = m - k * sd
        b = (u - d) / m
        mid[idx] = m.to_numpy(); up[idx] = u.to_numpy()
        lo[idx] = d.to_numpy(); bw[idx] = b.to_numpy()
    return mid, up, lo, bw


# ── signal record + cooldown ─────────────────────────────────────────────────
def _emit(rth, idx, side, family, **meta) -> dict:
    bar = rth.iloc[idx]
    rej = _swing_invalidation(rth, idx, side, SWING_LOOKBACK)
    return {
        "family": family,
        "date": bar["date"],
        "time": bar["timestamp_et"].strftime("%H:%M"),
        "bar_idx": int(idx),
        "side": side,
        "entry_spot": round(float(bar["close"]), 2),
        "rejection_level": round(float(rej), 2),
        "meta": meta,
    }


def _cooldown_ok(last: dict, bar_time, side) -> bool:
    """Per-side 30-min cooldown (no back-to-back same-direction churn, anti-pattern 2.7)."""
    prev = last.get(side)
    if prev is None:
        return True
    return (bar_time - prev).total_seconds() / 60.0 >= COOLDOWN_MIN


# ════════════════════════════════════════════════════════════════════════════
# 1. SUPPLY / DEMAND ZONE REVERSAL
# ════════════════════════════════════════════════════════════════════════════
IMPULSE_RANGE_MULT = 1.8   # impulse bar range > 1.8x the trailing mean range (per session)
IMPULSE_BODY_FRAC = 0.5    # ... AND body is >= 50% of the bar's range (directional)
IMPULSE_REF = 10           # trailing bars for the mean-range baseline (warm by ~10:20 ET)
ZONE_RETEST_TOL = 0.10     # $ tolerance for "price entered the zone"
SD_GATE = (dt.time(9, 40), dt.time(14, 0))   # zones form/retest intraday (ATR-warmup-safe)


def detect_supply_demand_zone(rth: pd.DataFrame) -> list[dict]:
    """Fresh impulse-candle S/D zone, reversal entry on FIRST retest.

    Impulse = a bar whose RANGE exceeds 1.8x the trailing mean range AND whose body is
    >= 50% of its range (a decisive directional candle). Range-vs-trailing-mean is warm
    by ~bar 11 (unlike ATR(14), whose warmup outran the original 09:30-11:00 window).
    A bullish impulse leaves a DEMAND zone [low, open]; the first dip back INTO it that
    closes back ABOVE the proximal edge -> LONG. A bearish impulse leaves a SUPPLY zone
    [open, high]; first poke back UP that closes back BELOW the proximal edge -> SHORT.
    Each zone fires at most once (fresh -> consumed); zones expire at session end.
    """
    o = rth["open"].to_numpy(); h = rth["high"].to_numpy()
    lo = rth["low"].to_numpy(); c = rth["close"].to_numpy()
    out: list[dict] = []
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        rng = (pd.Series(h[idx] - lo[idx]))
        # trailing mean range EXCLUDING the current bar (causal: bars [k-REF, k-1])
        avg_rng = rng.shift(1).rolling(IMPULSE_REF, min_periods=IMPULSE_REF).mean().to_numpy()
        zones: list[dict] = []   # active fresh zones for this session
        last: dict = {}
        for k, i in enumerate(idx):
            t = rth.at[i, "t"]
            # (a) check retests of existing fresh zones FIRST (price action at bar i)
            for z in zones:
                if z["used"]:
                    continue
                if z["kind"] == "demand":
                    entered = lo[i] <= z["proximal"] + ZONE_RETEST_TOL and lo[i] >= z["distal"] - ZONE_RETEST_TOL
                    reclaim = c[i] > z["proximal"]
                    if entered and reclaim and _in_window(t, SD_GATE):
                        bt = rth.at[i, "timestamp_et"]
                        if _cooldown_ok(last, bt, SIDE_CALL):
                            out.append(_emit(rth, i, SIDE_CALL, "supply_demand_zone",
                                             zone_kind="demand", proximal=round(z["proximal"], 2),
                                             distal=round(z["distal"], 2)))
                            last[SIDE_CALL] = bt
                        z["used"] = True
                else:  # supply
                    entered = h[i] >= z["proximal"] - ZONE_RETEST_TOL and h[i] <= z["distal"] + ZONE_RETEST_TOL
                    reject = c[i] < z["proximal"]
                    if entered and reject and _in_window(t, SD_GATE):
                        bt = rth.at[i, "timestamp_et"]
                        if _cooldown_ok(last, bt, SIDE_PUT):
                            out.append(_emit(rth, i, SIDE_PUT, "supply_demand_zone",
                                             zone_kind="supply", proximal=round(z["proximal"], 2),
                                             distal=round(z["distal"], 2)))
                            last[SIDE_PUT] = bt
                        z["used"] = True
            # (b) does bar i CREATE a new impulse zone? (registered for FUTURE retests)
            ar = avg_rng[k]
            if not np.isnan(ar) and ar > 0:
                rng_i = h[i] - lo[i]
                body = abs(c[i] - o[i])
                if rng_i > IMPULSE_RANGE_MULT * ar and rng_i > 0 and body / rng_i >= IMPULSE_BODY_FRAC:
                    if c[i] > o[i]:   # bullish impulse -> demand zone at origin
                        zones.append({"kind": "demand", "proximal": o[i], "distal": lo[i], "used": False})
                    else:             # bearish impulse -> supply zone at origin
                        zones.append({"kind": "supply", "proximal": o[i], "distal": h[i], "used": False})
    return out


# ════════════════════════════════════════════════════════════════════════════
# 2. EMA(9/21) CROSS + ADX(14) > 25 GATE
# ════════════════════════════════════════════════════════════════════════════
ADX_TREND_FLOOR = 25.0


def detect_ema_adx(rth: pd.DataFrame) -> list[dict]:
    """EMA9 x EMA21 cross, taken ONLY when ADX(14) > 25 (the SwjshAK regime gate: the
    ADX filter is the new idea — trend, not chop). Bullish cross -> call; bearish -> put."""
    ema9 = ema_continuous(rth["close"], 9)
    ema21 = ema_continuous(rth["close"], 21)
    adx, _pdi, _mdi = per_session(rth, lambda h, l, c: adx_session(h, l, c, 14), ncols=3)
    out: list[dict] = []
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        last: dict = {}
        for k, i in enumerate(idx):
            if k == 0:
                continue
            j = idx[k - 1]
            if np.isnan(ema9[i]) or np.isnan(ema21[i]) or np.isnan(ema9[j]) or np.isnan(ema21[j]):
                continue
            if np.isnan(adx[i]) or adx[i] <= ADX_TREND_FLOOR:
                continue
            t = rth.at[i, "t"]
            if not _in_window(t, ENTRY_GATE):
                continue
            bull_cross = ema9[j] <= ema21[j] and ema9[i] > ema21[i]
            bear_cross = ema9[j] >= ema21[j] and ema9[i] < ema21[i]
            side = SIDE_CALL if bull_cross else (SIDE_PUT if bear_cross else None)
            if side is None:
                continue
            bt = rth.at[i, "timestamp_et"]
            if not _cooldown_ok(last, bt, side):
                continue
            out.append(_emit(rth, i, side, "ema_adx", adx=round(float(adx[i]), 1)))
            last[side] = bt
    return out


# ════════════════════════════════════════════════════════════════════════════
# 3. THREE DUCKS — intraday multi-timeframe SMA alignment
# ════════════════════════════════════════════════════════════════════════════
# Three Ducks' essence is SLOW, STABLE higher-TF trend filters (original: SMA60 on 4H/1H)
# that rarely flip intraday, gating a fast 5m trigger. SHORT intraday SMAs hug price and
# toggle "alignment" every wiggle (2600 fires on 100% of days = noise, C27). So the higher
# ducks are LONG CONTINUOUS SMAs over the 5m RTH series: SMA78 ~= one trading day (the
# "daily" duck), SMA39 ~= half day (the "hourly" duck). The fast duck is a 5m pullback-cross
# of SMA9. Long = price above BOTH slow trends AND a fresh up-cross of the fast SMA (buy the
# dip inside an established multi-session uptrend). Continuous SMAs warm from ~day 2.
DUCK_FAST_N = 9      # 5m fast SMA (the pullback-cross trigger)
DUCK_MID_N = 39      # ~half trading day (the "hourly" duck)
DUCK_SLOW_N = 78     # ~one trading day (the "daily" duck)


def detect_three_ducks(rth: pd.DataFrame) -> list[dict]:
    """Three Ducks MTF alignment (0DTE adaptation): higher ducks = slow continuous SMA39
    (~half day) + SMA78 (~full day); fast duck = a 5m up/down cross of SMA9. Enter LONG when
    price is above BOTH slow SMAs AND the 5m closes back UP through SMA9 (pullback-resume in
    an established uptrend); mirror for SHORT. The slow continuous SMAs are stable across
    sessions (the multi-TF trend the original captures via 4H/1H); the cross is the trigger."""
    fast = sma_continuous(rth["close"], DUCK_FAST_N)
    mid = sma_continuous(rth["close"], DUCK_MID_N)
    slow = sma_continuous(rth["close"], DUCK_SLOW_N)
    c = rth["close"].to_numpy()
    out: list[dict] = []
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        last: dict = {}
        for k, i in enumerate(idx):
            if k == 0:
                continue
            j = idx[k - 1]
            if any(np.isnan(v) for v in (fast[i], fast[j], mid[i], slow[i])):
                continue
            t = rth.at[i, "t"]
            if not _in_window(t, ENTRY_GATE):
                continue
            up_cross = c[j] <= fast[j] and c[i] > fast[i]      # fast duck flips up
            dn_cross = c[j] >= fast[j] and c[i] < fast[i]
            # The higher ducks must POINT the same way (slope), not merely be below price —
            # a flat-trend price>SMA gate fires every wiggle (C27). Slope over 3 bars (the
            # continuous SMA78 slope IS the multi-session trend the original 4H duck encodes).
            rising = i >= 3 and mid[i] > mid[i - 3] and slow[i] > slow[i - 3]
            falling = i >= 3 and mid[i] < mid[i - 3] and slow[i] < slow[i - 3]
            long_align = c[i] > mid[i] and c[i] > slow[i] and rising
            short_align = c[i] < mid[i] and c[i] < slow[i] and falling
            side = SIDE_CALL if (up_cross and long_align) else (
                SIDE_PUT if (dn_cross and short_align) else None)
            if side is None:
                continue
            bt = rth.at[i, "timestamp_et"]
            if not _cooldown_ok(last, bt, side):
                continue
            out.append(_emit(rth, i, side, "three_ducks"))
            last[side] = bt
    return out


# ════════════════════════════════════════════════════════════════════════════
# 4. BOLLINGER SQUEEZE -> EXPANSION BREAKOUT
# ════════════════════════════════════════════════════════════════════════════
SQ_LOOKBACK = 20          # trailing window for the squeeze percentile (within session)
SQ_QUANTILE = 0.20        # bandwidth in bottom 20% of the trailing window = "squeeze"
SQ_RECENT = 4             # breakout must occur within 4 bars of a squeeze
VOL_MULT = 1.3            # breakout bar volume >= 1.3x its 20-bar trailing average


def detect_bollinger_squeeze(rth: pd.DataFrame) -> list[dict]:
    """BB(20,2) bandwidth squeeze (bottom-quartile of its trailing window) FOLLOWED BY an
    expansion breakout: close crosses the PRIOR bar's band with volume confirmation.
    Up-break -> call; down-break -> put. Direction = breakout direction."""
    mid, up, lo, bw = bollinger_session(rth, 20, 2.0)
    vol = rth["volume"].to_numpy()
    c = rth["close"].to_numpy()
    out: list[dict] = []
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        # trailing causal squeeze flag per session bar
        bw_s = pd.Series(bw[idx])
        q = bw_s.rolling(SQ_LOOKBACK, min_periods=SQ_LOOKBACK).quantile(SQ_QUANTILE)
        squeeze = (bw_s <= q).to_numpy()
        volavg = pd.Series(vol[idx]).rolling(20, min_periods=20).mean().to_numpy()
        last: dict = {}
        for k, i in enumerate(idx):
            if k == 0:
                continue
            j = idx[k - 1]
            if any(np.isnan(v) for v in (up[j], lo[j], volavg[k])):
                continue
            # squeeze active within the recent SQ_RECENT bars (but not necessarily THIS bar)
            recent = squeeze[max(0, k - SQ_RECENT):k]
            if not recent.any():
                continue
            t = rth.at[i, "t"]
            if not _in_window(t, ENTRY_GATE):
                continue
            vol_ok = volavg[k] > 0 and vol[i] >= VOL_MULT * volavg[k]
            if not vol_ok:
                continue
            up_break = c[i] > up[j]
            dn_break = c[i] < lo[j]
            side = SIDE_CALL if up_break else (SIDE_PUT if dn_break else None)
            if side is None:
                continue
            bt = rth.at[i, "timestamp_et"]
            if not _cooldown_ok(last, bt, side):
                continue
            out.append(_emit(rth, i, side, "bollinger_squeeze"))
            last[side] = bt
    return out


# ── registry ─────────────────────────────────────────────────────────────────
FAMILIES: dict[str, Callable[[pd.DataFrame], list[dict]]] = {
    "supply_demand_zone": detect_supply_demand_zone,
    "ema_adx": detect_ema_adx,
    "three_ducks": detect_three_ducks,
    "bollinger_squeeze": detect_bollinger_squeeze,
}

# entry-gate window per family (drives the null's eligible-bar set so the coin-flip
# benchmark draws from the SAME window the detector could have fired in).
FAMILY_WINDOW: dict[str, tuple[dt.time, dt.time]] = {
    "supply_demand_zone": SD_GATE,
    "ema_adx": ENTRY_GATE,
    "three_ducks": ENTRY_GATE,
    "bollinger_squeeze": ENTRY_GATE,
}
