"""PHASE 1 — MES multiday swing battery grinder.

Implements DESIGN.md (committed 3c31bf2, BEFORE this ran) verbatim:
  - 24 signal combos (RRW-short FDR family x8, E2 level+VWAP contexts x4,
    daily BOS/CHoCH-aligned variants x12) on MES RTH 5m bars.
  - 36 exit shapes (ATR14-daily stops {1.0,1.5,2.0} x targets {2xS,3xS,TRAIL}
    x max-hold {3d,5d} x {flat_friday, hold_weekend}) walked on ETH 5m bars,
    gap-aware fills (open beyond stop -> fill at open), stop-first tie-break.
  - Train 2025 / test 2026, rank on train only, top-K<=12 (<=3 per signal
    combo) to ONE test pass, BH-FDR alpha=0.1 vs random-entry null, plus
    opposite-direction null / drop-top3 / halves / recovery on survivors.

Costs: $1.24 RT commission + 1 tick ($1.25) slippage per side = $3.74/RT.
Sizing: 1 MES contract, $5/point. Research only, $0, no broker.

Run (ONE process, backtest/.venv is reaper-exempt):
  backtest/.venv/Scripts/python.exe swing_battery.py [--smoke]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # .../42
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from lib.ribbon import compute_ribbon                                  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import RRWParams, detect  # noqa: E402
from crypto.lib.bar import Bar                                         # noqa: E402
from crypto.lib.market_structure import walk_structure                 # noqa: E402
from crypto.lib.trendlines import find_swing_points                    # noqa: E402

# ---------------------------------------------------------------- constants
DATA_CSV = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
DERIVED_DIR = REPO / "backtest" / "data" / "futures" / "derived"
POINT_VALUE = 5.0
TICK = 0.25
COST_RT = 1.24 + 2 * (TICK * POINT_VALUE)  # 3.74 per round turn per contract
TRAIN_END = dt.date(2025, 12, 31)
HALF_SPLIT = dt.date(2026, 3, 22)
ATR_PERIOD = 14
TOP_K = 12
PER_COMBO_CAP = 3
MIN_TRAIN_N = 15
FDR_ALPHA = 0.10
NULL_POOL_M = 250
BOOT_B = 4000
RNG = np.random.default_rng(42)

RTH_OPEN = dt.time(9, 30)
RTH_END = dt.time(16, 0)
SIG_MIN = dt.time(9, 35)   # earliest eligible signal-bar label
SIG_MAX = dt.time(15, 30)  # latest eligible signal-bar label

WINDOWS = {
    "RRW_ALL": (dt.time(9, 35), dt.time(15, 30)),    # [9:35, 15:30] INCLUSIVE both ends
    "MIDDAY": (dt.time(11, 0), dt.time(14, 0)),      # [11:00, 14:00)
    "FULL": (dt.time(10, 0), dt.time(15, 0)),        # [10:00, 15:00)
}


# ---------------------------------------------------------------- data prep
def load_frames(smoke: bool) -> dict:
    df = pd.read_csv(DATA_CSV)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts.dt.tz_localize(None)  # naive ET everywhere downstream
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    if smoke:
        df = df[df["timestamp_et"] < pd.Timestamp("2025-04-01")].reset_index(drop=True)

    md5 = hashlib.md5(DATA_CSV.read_bytes()).hexdigest()

    idx = df.set_index("timestamp_et")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

    eth5 = (idx.resample("5min", label="left", closed="left").agg(agg)
            .dropna(subset=["open"]).reset_index())
    h4 = (idx.resample("4h", label="left", closed="left", offset="2h").agg(agg)
          .dropna(subset=["open"]).reset_index())

    t = eth5["timestamp_et"].dt.time
    rth5 = eth5[(t >= RTH_OPEN) & (t < RTH_END)].copy()
    rth5["eth_pos"] = rth5.index.values  # position in eth5 (RangeIndex)
    rth5 = rth5.reset_index(drop=True)

    rth5["date"] = rth5["timestamp_et"].dt.date
    daily = rth5.groupby("date").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).reset_index()

    DERIVED_DIR.mkdir(exist_ok=True)
    if not smoke:
        eth5.to_csv(DERIVED_DIR / "MES_5m_eth.csv", index=False)
        rth5.drop(columns=["eth_pos"]).to_csv(DERIVED_DIR / "MES_5m_rth.csv", index=False)
        h4.to_csv(DERIVED_DIR / "MES_4h_eth.csv", index=False)
        daily.to_csv(DERIVED_DIR / "MES_daily_rth.csv", index=False)

    return {"eth5": eth5, "rth5": rth5, "daily": daily, "md5": md5, "rows_1m": len(df),
            "span": [str(df['timestamp_et'].iloc[0]), str(df['timestamp_et'].iloc[-1])]}


def wilder_atr(daily: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    h, l, c = daily["high"].values, daily["low"].values, daily["close"].values
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = np.full(len(tr), np.nan)
    if len(tr) > period:
        atr[period] = np.nanmean(tr[1:period + 1])
        for i in range(period + 1, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(atr, index=daily.index)


def build_daily_context(daily: pd.DataFrame) -> dict:
    """ATR-asof, prior-day/week levels, BOS/CHoCH working trend — all causal."""
    dates = list(daily["date"])
    d2i = {d: i for i, d in enumerate(dates)}
    atr = wilder_atr(daily)

    # ATR / levels available to a signal on date d = values as of dates[i-1]
    atr_asof, lvl_asof = {}, {}
    weekly: dict[tuple, dict] = {}
    for i, d in enumerate(dates):
        iso = d.isocalendar()
        wk = (iso[0], iso[1])
        weekly.setdefault(wk, {"high": -np.inf, "low": np.inf})
        weekly[wk]["high"] = max(weekly[wk]["high"], daily["high"].iloc[i])
        weekly[wk]["low"] = min(weekly[wk]["low"], daily["low"].iloc[i])
    wk_keys = sorted(weekly)
    wk_prev = {wk_keys[i]: wk_keys[i - 1] for i in range(1, len(wk_keys))}

    for i, d in enumerate(dates):
        if i == 0:
            continue
        j = i - 1
        if not np.isnan(atr.iloc[j]):
            atr_asof[d] = float(atr.iloc[j])
        iso = d.isocalendar()
        pw = wk_prev.get((iso[0], iso[1]))
        lv = {"PDH": float(daily["high"].iloc[j]), "PDL": float(daily["low"].iloc[j]),
              "PDC": float(daily["close"].iloc[j])}
        if pw is not None:
            lv["PWH"] = float(weekly[pw]["high"])
            lv["PWL"] = float(weekly[pw]["low"])
        lvl_asof[d] = lv

    # BOS/CHoCH working trend on daily bars (fractal window 2, causal walk)
    bars = [Bar(open_time=pd.Timestamp(d).tz_localize("America/New_York").to_pydatetime(),
                open=float(r.open), high=float(r.high), low=float(r.low),
                close=float(r.close), volume=float(r.volume),
                granularity_seconds=86400, source="databento_mes_daily_rth")
            for d, r in zip(dates, daily.itertuples())]
    swings = find_swing_points(bars, window=2, inclusive_right=True)
    _, events = walk_structure(bars, swings, window=2)
    ev_by_break: dict[int, list] = {}
    for e in events:
        ev_by_break.setdefault(e.break_index, []).append(e)
    trend_after = []
    cur = "unknown"
    for i in range(len(dates)):
        for e in ev_by_break.get(i, []):
            cur = "uptrend" if e.direction == "bullish" else "downtrend"
        trend_after.append(cur)
    # trend available to a signal on date d = trend after the PRIOR daily close
    trend_asof = {d: (trend_after[i - 1] if i > 0 else "unknown")
                  for i, d in enumerate(dates)}
    return {"dates": dates, "d2i": d2i, "atr_asof": atr_asof, "lvl_asof": lvl_asof,
            "trend_asof": trend_asof, "n_structure_events": len(events)}


# ---------------------------------------------------------------- signal scans
def scan_rrw(rth5: pd.DataFrame) -> pd.DataFrame:
    """Superset scan (loosest knobs, MES-scaled dollar constants), bear only."""
    params = RRWParams(wick_frac_min=0.35, break_lookback_bars=12, vol_mult_min=0.0,
                       require_stack_not_flipped=False,
                       close_margin_dollars=0.10, min_bar_range_dollars=1.00)
    bars = rth5[["timestamp_et", "open", "high", "low", "close", "volume"]].copy()
    ribbon = compute_ribbon(bars["close"])
    tt = rth5["timestamp_et"].dt.time
    eligible = np.flatnonzero((tt >= SIG_MIN) & (tt <= SIG_MAX))
    rows = []
    for i in eligible:
        if i < 48:
            continue
        sig = detect(bars, int(i), params, direction="bear", ribbon_df=ribbon)
        if sig is None:
            continue
        rows.append({"ts": rth5["timestamp_et"].iloc[i], "date": rth5["date"].iloc[i],
                     "eth_pos": int(rth5["eth_pos"].iloc[i]), "direction": -1,
                     "wick_frac": sig["wick_frac"], "bars_since_break": sig["bars_since_break"],
                     "vol_break_ratio": sig["vol_break_ratio"]})
    return pd.DataFrame(rows)


def scan_e2(rth5: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """Level-touch + VWAP-aligned close, both directions, superset (loosest tol,
    widest window); per-combo tol/window filters applied post-hoc.
    Dedupe (first per day per direction) happens AFTER combo filtering so each
    window sees its own first signal."""
    df = rth5.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    df["cum_pv"] = pv.groupby(df["date"]).cumsum()
    df["cum_v"] = df["volume"].groupby(df["date"]).cumsum()
    df["vwap"] = df["cum_pv"] / df["cum_v"].replace(0, np.nan)

    tol_max = 0.001  # loosest tol in the grid
    tt = df["timestamp_et"].dt.time
    w = (tt >= WINDOWS["FULL"][0]) & (tt < WINDOWS["FULL"][1])
    w |= (tt >= WINDOWS["MIDDAY"][0]) & (tt < WINDOWS["MIDDAY"][1])
    rows = []
    for r in df[w].itertuples():
        lv = ctx["lvl_asof"].get(r.date)
        if not lv or pd.isna(r.vwap):
            continue
        for lname, L in lv.items():
            if r.low <= L * (1 + tol_max) and r.close > L and r.close > r.vwap:
                dist = abs(r.low - L) / L if r.low > L else 0.0
                rows.append({"ts": r.timestamp_et, "date": r.date, "eth_pos": int(r.eth_pos),
                             "direction": +1, "level": lname, "tol_needed": dist})
            elif r.high >= L * (1 - tol_max) and r.close < L and r.close < r.vwap:
                dist = abs(L - r.high) / L if r.high < L else 0.0
                rows.append({"ts": r.timestamp_et, "date": r.date, "eth_pos": int(r.eth_pos),
                             "direction": -1, "level": lname, "tol_needed": dist})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- combos
def build_combos() -> list[dict]:
    combos = []
    for wf in (0.35, 0.5):
        for lb in (6, 12):
            for vm in (1.5, 2.5):
                combos.append({"id": f"A_rrw_w{wf}_lb{lb}_v{vm}", "seed": "RRW",
                               "window": "RRW_ALL", "wf": wf, "lb": lb, "vm": vm,
                               "struct": False})
    for tol in (0.0005, 0.001):
        for win in ("MIDDAY", "FULL"):
            combos.append({"id": f"B_e2_t{tol}_{win.lower()}", "seed": "E2",
                           "window": win, "tol": tol, "struct": False})
    out = list(combos)
    for c in combos:
        cc = dict(c)
        cc["id"] = "C_" + c["id"][2:] + "_struct"
        cc["struct"] = True
        out.append(cc)
    assert len(out) == 24
    return out


def events_for_combo(combo: dict, rrw: pd.DataFrame, e2: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    if combo["seed"] == "RRW":
        ev = rrw[(rrw["wick_frac"] >= combo["wf"])
                 & (rrw["bars_since_break"] <= combo["lb"])
                 & (rrw["vol_break_ratio"] >= combo["vm"])].copy()
    else:
        lo, hi = WINDOWS[combo["window"]]
        tt = pd.to_datetime(e2["ts"]).dt.time if len(e2) else pd.Series(dtype=object)
        ev = e2[(e2["tol_needed"] <= combo["tol"])
                & (tt >= lo) & (tt < hi)].copy() if len(e2) else e2.copy()
        if len(ev):  # first per day per direction
            ev = ev.sort_values("ts").groupby(["date", "direction"], as_index=False).first()
    if combo["struct"] and len(ev):
        want = ev["direction"].map(lambda d: "uptrend" if d > 0 else "downtrend")
        have = ev["date"].map(lambda d: ctx["trend_asof"].get(d, "unknown"))
        ev = ev[want == have]
    if len(ev):
        ev = ev.sort_values("eth_pos").reset_index(drop=True)
    return ev


# ---------------------------------------------------------------- exit engine
@dataclass(frozen=True)
class Shape:
    sid: str
    stop_mult: float
    target: str           # "2x" | "3x" | "trail"
    max_hold: int         # trading days
    flat_friday: bool


def build_shapes() -> list[Shape]:
    out = []
    for sm in (1.0, 1.5, 2.0):
        for tg in ("2x", "3x", "trail"):
            for mh in (3, 5):
                for ff in (True, False):
                    out.append(Shape(f"s{sm}_{tg}_h{mh}_{'ff' if ff else 'hw'}",
                                     sm, tg, mh, ff))
    assert len(out) == 36
    return out


class ExitEngine:
    def __init__(self, eth5: pd.DataFrame, rth5: pd.DataFrame):
        self.o = eth5["open"].values.astype(float)
        self.h = eth5["high"].values.astype(float)
        self.l = eth5["low"].values.astype(float)
        self.c = eth5["close"].values.astype(float)
        self.ts = eth5["timestamp_et"].values
        self.n = len(eth5)
        self.date_of = eth5["timestamp_et"].dt.date.values

        rc = rth5.groupby("date")["eth_pos"].max()
        self.rth_close_idx = {d: int(i) for d, i in rc.items()}
        self.trading_dates = sorted(self.rth_close_idx)
        self.d2i = {d: i for i, d in enumerate(self.trading_dates)}
        wk_last: dict[tuple, dt.date] = {}
        for d in self.trading_dates:
            iso = d.isocalendar()
            wk_last[(iso[0], iso[1])] = d
        self.week_end = {d: wk_last[(d.isocalendar()[0], d.isocalendar()[1])]
                         for d in self.trading_dates}
        self.td_arr = np.array(self.trading_dates, dtype=object)

    def _horizon(self, entry_idx: int, shape: Shape) -> tuple[int, str]:
        d = self.date_of[entry_idx]
        di = self.d2i[d]
        cands = []
        if di + shape.max_hold < len(self.trading_dates):
            cands.append((self.trading_dates[di + shape.max_hold], "TIME"))
        if shape.flat_friday:
            cands.append((self.week_end[d], "FRIDAY"))
        if not cands:
            return self.n - 1, "DATA_END"
        xd, why = min(cands, key=lambda x: x[0])
        return self.rth_close_idx[xd], why

    def _first(self, mask: np.ndarray) -> int:
        return int(np.argmax(mask)) if mask.any() else -1

    def sim(self, entry_idx: int, direction: int, atr: float, shape: Shape) -> dict:
        S = shape.stop_mult * atr
        e = self.o[entry_idx]
        hor, twhy = self._horizon(entry_idx, shape)
        hor = max(hor, entry_idx)

        if shape.target == "trail":
            xi, xp, why = self._sim_trail(entry_idx, direction, e, S, hor)
        else:
            tmult = 2.0 if shape.target == "2x" else 3.0
            stop = e - direction * S
            tgt = e + direction * tmult * S
            sl = slice(entry_idx, hor + 1)
            if direction > 0:
                smask, tmask = self.l[sl] <= stop, self.h[sl] >= tgt
            else:
                smask, tmask = self.h[sl] >= stop, self.l[sl] <= tgt
            si, ti = self._first(smask), self._first(tmask)
            if si < 0 and ti < 0:
                xi, xp, why = hor, self.c[hor], twhy
            elif ti < 0 or (0 <= si <= ti):
                xi = entry_idx + si
                op = self.o[xi]
                gap = xi > entry_idx and ((direction > 0 and op <= stop)
                                          or (direction < 0 and op >= stop))
                xp, why = (op if gap else stop), "STOP"
            else:
                xi = entry_idx + ti
                op = self.o[xi]
                gap = xi > entry_idx and ((direction > 0 and op >= tgt)
                                          or (direction < 0 and op <= tgt))
                xp, why = (op if gap else tgt), "TARGET"

        if why in ("TIME", "FRIDAY") and hor == self.n - 1 \
                and self.date_of[hor] == self.trading_dates[-1] and twhy == "DATA_END":
            why = "DATA_END"
        pts = float((xp - e) * direction)
        ed, xd = self.date_of[entry_idx], self.date_of[xi]
        xdi = int(np.searchsorted(self.td_arr, xd, side="right")) - 1
        span_days = (xd - ed).days
        wk_held = any((ed + dt.timedelta(days=k)).weekday() == 5
                      for k in range(1, span_days + 1))
        return {"entry_idx": int(entry_idx), "exit_idx": int(xi),
                "entry_ts": str(self.ts[entry_idx]),
                "exit_ts": str(self.ts[xi]), "entry_date": str(ed),
                "direction": int(direction),
                "entry_px": round(float(e), 2), "exit_px": round(float(xp), 2),
                "pnl_pts": round(pts, 2),
                "pnl_usd": round(pts * POINT_VALUE - COST_RT, 2),
                "reason": why, "hold_tdays": xdi - self.d2i[ed],
                "weekend_held": bool(wk_held)}

    def _sim_trail(self, entry_idx: int, direction: int, e: float, S: float,
                   hor: int) -> tuple[int, float, str]:
        stop = e - direction * S
        best = -np.inf if direction > 0 else np.inf
        seg = entry_idx
        d = self.date_of[entry_idx]
        di = self.d2i[d]
        while seg <= hor:
            if di < len(self.trading_dates):
                rc = self.rth_close_idx[self.trading_dates[di]]
            else:
                rc = hor  # past the last trading day (DATA_END tail)
            seg_end = min(rc, hor)
            sl = slice(seg, seg_end + 1)
            mask = (self.l[sl] <= stop) if direction > 0 else (self.h[sl] >= stop)
            fi = self._first(mask)
            if fi >= 0:
                xi = seg + fi
                op = self.o[xi]
                gap = xi > entry_idx and ((direction > 0 and op <= stop)
                                          or (direction < 0 and op >= stop))
                return xi, (op if gap else stop), "TRAIL_STOP"
            if seg_end == hor:
                return hor, self.c[hor], "TIME"
            dc = self.c[rc]
            if direction > 0:
                best = max(best, dc)
                stop = max(stop, best - S)
            else:
                best = min(best, dc)
                stop = min(stop, best + S)
            seg = rc + 1
            di += 1
        return hor, self.c[hor], "TIME"


def run_cell(events: pd.DataFrame, shape: Shape, eng: ExitEngine,
             atr_asof: dict) -> list[dict]:
    trades, open_until = [], -1
    for r in events.itertuples():
        ei = r.eth_pos + 1
        if ei >= eng.n or ei <= open_until:
            continue
        atr = atr_asof.get(eng.date_of[ei])
        if atr is None:
            continue
        tr = eng.sim(ei, int(r.direction), atr, shape)
        trades.append(tr)
        open_until = tr["exit_idx"]
    return trades


# ---------------------------------------------------------------- metrics
def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "pnl": 0.0, "exp": 0.0, "wr": 0.0, "max_dd": 0.0,
                "drop_top3": 0.0}
    p = np.array([t["pnl_usd"] for t in trades])
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    top3 = np.sort(p)[-3:].sum() if len(p) >= 3 else p.sum()
    return {"n": len(p), "pnl": round(float(p.sum()), 2),
            "exp": round(float(p.mean()), 2),
            "wr": round(float((p > 0).mean()), 3),
            "max_dd": round(dd, 2),
            "drop_top3": round(float(p.sum() - top3), 2)}


def split_trades(trades: list[dict]):
    tr = [t for t in trades if dt.date.fromisoformat(t["entry_date"]) <= TRAIN_END]
    te = [t for t in trades if dt.date.fromisoformat(t["entry_date"]) > TRAIN_END]
    return tr, te


# ---------------------------------------------------------------- nulls & FDR
def null_pool(eng: ExitEngine, rth5: pd.DataFrame, ctx: dict, shape: Shape,
              window: str, direction: int) -> np.ndarray:
    lo, hi = WINDOWS[window]
    tt = rth5["timestamp_et"].dt.time
    m = (tt >= lo) & (tt <= hi) if window == "RRW_ALL" else (tt >= lo) & (tt < hi)
    m &= rth5["date"] > TRAIN_END
    m &= rth5["date"].map(lambda d: d in ctx["atr_asof"])
    pos = rth5.loc[m, "eth_pos"].values
    pos = pos[pos + 1 < eng.n]
    picks = RNG.choice(pos, size=min(NULL_POOL_M, len(pos)), replace=True)
    out = []
    for p in picks:
        ei = int(p) + 1
        atr = ctx["atr_asof"][eng.date_of[ei]]
        out.append(eng.sim(ei, direction, atr, shape)["pnl_usd"])
    return np.array(out)


def boot_p(obs_mean: float, n: int, frac_short: float,
           pool_s: np.ndarray, pool_l: np.ndarray) -> float:
    n_s = int(round(n * frac_short))
    n_l = n - n_s
    means = np.zeros(BOOT_B)
    if n_s and len(pool_s):
        means += pool_s[RNG.integers(0, len(pool_s), (BOOT_B, n_s))].sum(axis=1)
    if n_l and len(pool_l):
        means += pool_l[RNG.integers(0, len(pool_l), (BOOT_B, n_l))].sum(axis=1)
    means /= max(n, 1)
    return float(((means >= obs_mean).sum() + 1) / (BOOT_B + 1))


def bh_fdr(pvals: list[float], alpha: float) -> list[bool]:
    m = len(pvals)
    order = np.argsort(pvals)
    thresh = -1.0
    for rank, oi in enumerate(order, start=1):
        if pvals[oi] <= alpha * rank / m:
            thresh = pvals[oi]
    return [p <= thresh for p in pvals] if thresh >= 0 else [False] * m


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    frames = load_frames(args.smoke)
    eth5, rth5, daily = frames["eth5"], frames["rth5"], frames["daily"]
    print(f"[{time.time()-t0:6.1f}s] frames: eth5={len(eth5)} rth5={len(rth5)} daily={len(daily)}",
          flush=True)

    ctx = build_daily_context(daily)
    eng = ExitEngine(eth5, rth5)
    print(f"[{time.time()-t0:6.1f}s] daily ctx: atr_days={len(ctx['atr_asof'])} "
          f"structure_events={ctx['n_structure_events']}", flush=True)

    rrw = scan_rrw(rth5)
    print(f"[{time.time()-t0:6.1f}s] RRW superset events: {len(rrw)}", flush=True)
    e2 = scan_e2(rth5, ctx)
    print(f"[{time.time()-t0:6.1f}s] E2 superset events: {len(e2)}", flush=True)

    combos = build_combos()
    shapes = build_shapes()

    cells = {}
    combo_events = {}
    for cb in combos:
        ev = events_for_combo(cb, rrw, e2, ctx)
        combo_events[cb["id"]] = ev
        for sh in shapes:
            trades = run_cell(ev, sh, eng, ctx["atr_asof"])
            tr, te = split_trades(trades)
            cells[(cb["id"], sh.sid)] = {"combo": cb, "shape": sh, "trades": trades,
                                         "train": metrics(tr), "test_trades": te}
    print(f"[{time.time()-t0:6.1f}s] grid done: {len(cells)} cells", flush=True)

    # ---- weekend vs flat-friday, train-level descriptive across all cells
    wk_pairs = []
    for cb in combos:
        for sm in (1.0, 1.5, 2.0):
            for tg in ("2x", "3x", "trail"):
                for mh in (3, 5):
                    ff = cells[(cb["id"], f"s{sm}_{tg}_h{mh}_ff")]["train"]
                    hw = cells[(cb["id"], f"s{sm}_{tg}_h{mh}_hw")]["train"]
                    if ff["n"] >= 10 and hw["n"] >= 10:
                        wk_pairs.append({"combo": cb["id"], "shape": f"s{sm}_{tg}_h{mh}",
                                         "ff_exp": ff["exp"], "hw_exp": hw["exp"],
                                         "delta_hw_minus_ff": round(hw["exp"] - ff["exp"], 2)})
    deltas = [p["delta_hw_minus_ff"] for p in wk_pairs]
    weekend_summary = {
        "n_pairs_train_n>=10_both": len(wk_pairs),
        "mean_delta_exp_hw_minus_ff": round(float(np.mean(deltas)), 2) if deltas else None,
        "median_delta": round(float(np.median(deltas)), 2) if deltas else None,
        "pct_pairs_hw_better": round(float(np.mean([d > 0 for d in deltas])), 3) if deltas else None,
    }

    # ---- selection on train only
    eligible = [(k, v) for k, v in cells.items()
                if v["train"]["n"] >= MIN_TRAIN_N and v["train"]["exp"] > 0]
    eligible.sort(key=lambda kv: kv[1]["train"]["exp"], reverse=True)
    selected, per_combo = [], {}
    for k, v in eligible:
        if per_combo.get(k[0], 0) >= PER_COMBO_CAP:
            continue
        selected.append((k, v))
        per_combo[k[0]] = per_combo.get(k[0], 0) + 1
        if len(selected) >= TOP_K:
            break
    print(f"[{time.time()-t0:6.1f}s] eligible={len(eligible)} selected={len(selected)}",
          flush=True)

    # ---- one test pass + nulls
    pool_cache: dict = {}
    tested = []
    for (cid, sid), v in selected:
        te = v["test_trades"]
        mte = metrics(te)
        h1 = metrics([t for t in te if dt.date.fromisoformat(t["entry_date"]) <= HALF_SPLIT])
        h2 = metrics([t for t in te if dt.date.fromisoformat(t["entry_date"]) > HALF_SPLIT])
        window = v["combo"]["window"]
        frac_s = (float(np.mean([t["direction"] < 0 for t in te])) if te else 1.0)
        p = None
        if mte["n"] > 0:
            key_s, key_l = (sid, window, -1), (sid, window, +1)
            if frac_s > 0 and key_s not in pool_cache:
                pool_cache[key_s] = null_pool(eng, rth5, ctx, v["shape"], window, -1)
            if frac_s < 1 and key_l not in pool_cache:
                pool_cache[key_l] = null_pool(eng, rth5, ctx, v["shape"], window, +1)
            p = boot_p(mte["exp"], mte["n"], frac_s,
                       pool_cache.get(key_s, np.array([])),
                       pool_cache.get(key_l, np.array([])))
        # opposite-direction null: same entries flipped, sequential non-overlap
        opp_trades, open_until = [], -1
        for t in te:
            if t["entry_idx"] <= open_until:
                continue
            atr = ctx["atr_asof"].get(eng.date_of[t["entry_idx"]])
            if atr is None:
                continue
            ot = eng.sim(t["entry_idx"], -t["direction"], atr, v["shape"])
            opp_trades.append(ot)
            open_until = ot["exit_idx"]
        mopp = metrics(opp_trades)
        tested.append({"combo_id": cid, "shape_id": sid,
                       "train": v["train"], "test": mte,
                       "test_half1": h1, "test_half2": h2,
                       "p_null": p, "frac_short": round(frac_s, 3),
                       "opp": {"n": mopp["n"], "exp": mopp["exp"], "pnl": mopp["pnl"]},
                       "n_data_end": sum(1 for t in te if t["reason"] == "DATA_END"),
                       "exit_reasons": {r: sum(1 for t in te if t["reason"] == r)
                                        for r in set(t["reason"] for t in te)} if te else {},
                       "test_trades": te})
    print(f"[{time.time()-t0:6.1f}s] test pass + nulls done", flush=True)

    # ---- FDR + pre-registered gates
    with_p = [c for c in tested if c["p_null"] is not None]
    flags = bh_fdr([c["p_null"] for c in with_p], FDR_ALPHA) if with_p else []
    for c, f in zip(with_p, flags):
        c["bh_fdr_survivor"] = bool(f)
    for c in tested:
        c.setdefault("bh_fdr_survivor", False)
        te, h1, h2, opp = c["test"], c["test_half1"], c["test_half2"], c["opp"]
        rec = (te["pnl"] / te["max_dd"]) if te["max_dd"] > 0 else (np.inf if te["pnl"] > 0 else 0)
        checks = {
            "bh_fdr": c["bh_fdr_survivor"],
            "test_n>=15": te["n"] >= 15,
            "test_exp>0": te["exp"] > 0,
            "opp_exp<=0": opp["exp"] <= 0 and te["exp"] - opp["exp"] > 0,
            "drop_top3>0": te["drop_top3"] > 0,
            "halves_both>0_n>=8": h1["pnl"] > 0 and h2["pnl"] > 0 and h1["n"] >= 8 and h2["n"] >= 8,
            "recovery>=1": bool(rec >= 1.0),
        }
        c["recovery_factor"] = None if np.isinf(rec) else round(float(rec), 2)
        c["checks"] = checks
        c["clears_all"] = all(checks.values())
        c["weak_core"] = checks["bh_fdr"] and checks["test_exp>0"] and checks["opp_exp<=0"]

    n_clear = sum(1 for c in tested if c["clears_all"])
    n_weak = sum(1 for c in tested if c["weak_core"] and not c["clears_all"])
    if n_clear:
        verdict = "DIRECTION_TRANSFERS"
    elif n_weak:
        verdict = "WEAK"
    else:
        verdict = "DOES_NOT_TRANSFER"

    funnel = {
        "rrw_superset_events": int(len(rrw)),
        "e2_superset_events": int(len(e2)),
        "combos": 24, "exit_shapes": 36, "cells": len(cells),
        "combo_event_counts": {cid: int(len(ev)) for cid, ev in combo_events.items()},
        "cells_eligible_train": len(eligible),
        "cells_selected_topK": len(selected),
        "bh_fdr_survivors": int(sum(flags)) if flags else 0,
        "full_gate_survivors": n_clear,
        "weak_core_survivors": n_weak,
    }

    results = {
        "battery": "PHASE1-swing-battery", "instrument": "MES",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "design": "DESIGN.md @ commit 3c31bf2 (pre-registered)",
        "smoke": args.smoke,
        "data": {"source": str(DATA_CSV), "md5": frames["md5"],
                 "rows_1m": frames["rows_1m"], "span_et": frames["span"],
                 "sessions": "ETH walk / RTH signals / RTH daily context"},
        "costs": {"commission_rt": 1.24, "slippage_per_side_ticks": 1,
                  "total_rt_usd": COST_RT},
        "split": {"train_end": str(TRAIN_END), "half_split": str(HALF_SPLIT)},
        "verdict": verdict,
        "funnel": funnel,
        "weekend_vs_flat_friday_train": weekend_summary,
        "weekend_pairs_top20_by_train_exp": sorted(
            wk_pairs, key=lambda p: max(p["ff_exp"], p["hw_exp"]), reverse=True)[:20],
        "tested_cells": [{k: v for k, v in c.items() if k != "test_trades"}
                         for c in tested],
        "survivor_trades": {f"{c['combo_id']}|{c['shape_id']}": c["test_trades"]
                            for c in tested if c["clears_all"] or c["weak_core"]},
        "train_leaderboard_top25": [
            {"combo": k[0], "shape": k[1], **v["train"]}
            for k, v in eligible[:25]],
        "runtime_sec": round(time.time() - t0, 1),
    }
    def _np(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return str(o)

    out = HERE / ("results-smoke.json" if args.smoke else "results.json")
    out.write_text(json.dumps(results, indent=1, default=_np))
    print(f"[{time.time()-t0:6.1f}s] VERDICT={verdict}  "
          f"clear={n_clear} weak={n_weak} -> {out}", flush=True)

    if not args.smoke:
        prov = {"ran_at": dt.datetime.now().isoformat(timespec="seconds"),
                "symbol": "mes_futures", "as_of": str(dt.date.today()),
                "status": "ok", "action": "phase1_swing_battery",
                "source": str(DATA_CSV), "md5": frames["md5"],
                "rows_1m": frames["rows_1m"], "span_et": frames["span"],
                "derived": [str(DERIVED_DIR / f) for f in
                            ("MES_5m_eth.csv", "MES_5m_rth.csv",
                             "MES_4h_eth.csv", "MES_daily_rth.csv")]}
        with open(REPO / "analysis" / "backtests" / "data-versions.jsonl", "a") as f:
            f.write(json.dumps(prov) + "\n")


if __name__ == "__main__":
    main()
