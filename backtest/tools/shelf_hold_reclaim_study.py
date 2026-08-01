"""shelf_hold_reclaim_study.py -- WS5: SHELF_HOLD_RECLAIM full-population study (2026-08-01).

FROZEN PRE-REG: analysis/recommendations/shelf-hold-reclaim-prereg-2026-08-01.md, committed
96a85efc BEFORE this file existed (et_clock 2026-08-01 12:45:56 Saturday EDT). Parent spec:
analysis/deep-research/J-CALLED-ENTRIES-2026-07-31.md section 5. This runner implements the
prereg faithfully; every deviation is disclosed in the output under "deviations".

FRAME DISCLOSURE (decided BEFORE first run, zero cells seen): the prereg cited
ladder_fullhist_replay.load_extended_data for FILE LINEAGE (which CSVs merge). That loader
parses wall-v1 (lib/et_frame.py): winter labels +1h, RTH slice clips the last true trading
hour on 129 EST days, and naive VIX joins gain 1h of winter LOOK-AHEAD (C6 violation). This
runner opts into et-v2 explicitly (lib.et_frame.parse_timestamp_et, frame="et-v2") for SPY,
VIX, and OPRA alike -- honoring the prereg's own ET-time semantics (09:35 gate, 15:40 stop,
anchor windows) and C6. SPY+OPRA share the fixed -04:00 storage, so parsing BOTH et-v2 keeps
joins frame-consistent (et_frame.py's stated rule). The harness fidelity gate is the three
2026-07-31 tape anchors (EDT => frame-invariant).

ANALYSIS ONLY: no live config/param/gate/order touched. Real OPRA only; exclusions counted,
never synthetic. Entry+1 (ruling 2026-07-25). qty=3 min size. All 96 cells reported.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/shelf_hold_reclaim_study.py
      [--smoke]      last 4 sessions only, scratch outputs, anchors still checked
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent                                       # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "setup" / "scripts"),
           str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import daily_context as dcx  # noqa: E402  -- read-only import (shelf detection)
import strategies as fleet_strategies  # noqa: E402
from lib.et_frame import parse_timestamp_et  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.filters import (  # noqa: E402
    RIBBON_SPREAD_MIN_CENTS, VIX_BULL_HARD_CAP, VIX_BULL_LOW_THRESHOLD,
    detect_level_reclaim, detect_pullback_hold_bullish, detect_wick_reclaim_bullish,
    vix_direction, vol_baseline_20bar,
)
from lib.orchestrator import _precompute_htf_15m_stacks  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_VIX = DATA / "vix_5m_2026-05-19_2026-07-31.csv"
OPT_DIR = DATA / "options"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)
EXPECTED_DAYS = 391
# Half-day sessions (13:00 close) excluded to match the VERIFIED 391-day population
# (WS6 et-v2 lineage recon: merged frame has 394 RTH sessions; 394 - these 3 = 391).
# Decided BEFORE the full run; no cell was ever computed on them. 2026-06-15 (12-bar
# data-gap day) stays IN population per the verified lineage, disclosed.
HALF_DAYS = {dt.date(2025, 7, 3), dt.date(2025, 11, 28), dt.date(2025, 12, 24)}

QTY = 3
PREMIUM_FLOOR = 0.30
TIME_STOP_ET = dt.time(15, 40)          # live Safe params.json time_stop_et
ENTRY_NOT_BEFORE = dt.time(9, 35)       # SAFE_BASE no_trade_before
BLACKOUT = (dt.time(15, 0), dt.time(16, 0))  # SAFE_BASE entry cutoff window
SPOT_BAND = 20.0                         # refresh_levels_intraday SHELF_UPSERT_BAND parity
SHELF_LOOKBACK_CAL_DAYS = 60             # daily_context LOOKBACK parity (levels_v2 retro feed)
PULLBACK_MIN_HOLD = 2
PULLBACK_LOOKBACK = 12
F10_VOL_MULT = 0.7

GEOMETRIES = ("A_wick", "B_hold", "C_cross", "UNION")
F5_MODES = ("require", "drop", "htf")
LANES = ("CONTROL", "ZONE_RIDE")
UNION_PRIORITY = {"A_wick": 0, "B_hold": 1, "C_cross": 2}  # frozen same-bar tie-break

PRIMARY_COMBO = {"f5": "drop", "f8": False, "f10": False, "lane": "CONTROL"}

OUT_JSON = ROOT / "analysis" / "recommendations" / "shelf-hold-reclaim-2026-08-01.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "shelf-hold-reclaim-2026-08-01.md"
SMOKE_JSON = ROOT / "analysis" / "recommendations" / "shelf-hold-reclaim-2026-08-01.smoke.json"

ANCHORS = [
    {"tag": "e1", "geometry": "A_wick", "day": "2026-07-31",
     "entry_tick_lo": "10:20", "entry_tick_hi": "10:45", "level": 737.68, "tol": 0.80},
    {"tag": "e2", "geometry": "B_hold", "day": "2026-07-31",
     "entry_tick_lo": "11:40", "entry_tick_hi": "12:05", "level": 739.73, "tol": 0.80},
    {"tag": "e3", "geometry": "C_cross", "day": "2026-07-31",
     "entry_tick_lo": "12:15", "entry_tick_hi": "12:40", "level": 743.25, "tol": 0.80},
]


def log(msg: str) -> None:
    print(f"[shelf-hold] {msg}", flush=True)


# ================================================================== data (et-v2 frame)

def _load_csv_et2(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    return df


def load_merged(old_path: Path, new_path: Path) -> pd.DataFrame:
    """OLD file + strictly-after-07-22 tail of NEW file (ladder lineage, et-v2 parsed)."""
    old = _load_csv_et2(old_path)
    new = _load_csv_et2(new_path)
    tail = new[new["timestamp_et"].dt.date > dt.date(2026, 7, 22)]
    out = (pd.concat([old, tail], ignore_index=True)
             .sort_values("timestamp_et").reset_index(drop=True))
    return out.drop_duplicates(subset="timestamp_et").reset_index(drop=True)


def build_rth(spy_df: pd.DataFrame) -> pd.DataFrame:
    mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    return spy_df.loc[mask].reset_index(drop=True)


def build_daily_bars(spy_rth: pd.DataFrame) -> list[dict]:
    """daily_context bar schema from RTH 5m bars (levels_v2 retro-feed convention;
    et-v2 => true full-session daily H/L/C year-round)."""
    out: list[dict] = []
    for d, day in spy_rth.groupby(spy_rth["timestamp_et"].dt.date, sort=True):
        out.append({
            "date": d.isoformat(),
            "o": float(day["open"].iloc[0]), "h": float(day["high"].max()),
            "l": float(day["low"].min()), "c": float(day["close"].iloc[-1]),
            "v": float(day["volume"].sum()) if "volume" in day.columns else 0.0,
        })
    return out


def shelf_zones_asof(daily_bars: list[dict], session: dt.date) -> list[dict]:
    """Merged shelf zones as-of `session`, window [session-60cal, session) STRICTLY before
    (C6). daily_context's own functions + module defaults -- nothing re-tuned."""
    lo = (session - dt.timedelta(days=SHELF_LOOKBACK_CAL_DAYS)).isoformat()
    hi = session.isoformat()
    window = [b for b in daily_bars if lo <= b["date"] < hi]
    if len(window) < dcx.SHELF_MIN_TOUCHES:
        return []
    return dcx._merge_shelf_candidates(dcx._find_shelf_candidates(window))


# ================================================================== OPRA (et-v2 frame)

_OPT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def load_opt_et2(symbol: str) -> Optional[pd.DataFrame]:
    """Cached OPRA contract bars parsed et-v2 (same fixed -04:00 storage as SPY -- parsing
    both et-v2 keeps the join frame-consistent per lib/et_frame.py)."""
    if symbol in _OPT_CACHE:
        return _OPT_CACHE[symbol]
    path = OPT_DIR / f"{symbol}.csv"
    if not path.exists():
        _OPT_CACHE[symbol] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    _OPT_CACHE[symbol] = df
    return df


def option_symbol(day: dt.date, strike: int) -> str:
    return f"SPY{day.strftime('%y%m%d')}C{strike * 1000:08d}"


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    """Backward as-of join of the continuous RTH ribbon stack onto option bar timestamps
    (engine_fullhist_replay.ribbon_tick_df_for semantics, et-v2 naive frames both sides)."""
    left = opt_df[["timestamp_et"]].copy()
    merged = pd.merge_asof(left, ribbon_lookup, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df), "ribbon merge row drift"
    return merged.reset_index(drop=True)[["stack"]]


# ================================================================== stats helpers

def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    t = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


# ================================================================== signal scan

def scan_day(day: dt.date, day_df: pd.DataFrame, gidx0: int, anchors: list[dict],
             stack_arr, spread_arr, htf_arr, vix_now_arr, vix_prior_arr,
             spy_rth: pd.DataFrame) -> list[dict]:
    """Raw geometry fires for one session. day_df is the day's RTH frame (local idx),
    gidx0 the global row index of its first bar. Returns signal dicts with filter flags.
    <=1 signal per geometry per bar."""
    signals: list[dict] = []
    mids = [a["mid"] for a in anchors]
    by_mid = {a["mid"]: a for a in anchors}
    n = len(day_df)
    lows = day_df["low"].to_numpy()
    highs = day_df["high"].to_numpy()
    closes = day_df["close"].to_numpy()
    opens = day_df["open"].to_numpy()

    # cheap per-anchor "low entered band" prefix for the B pre-screen
    inband = {a["mid"]: (abs(lows - a["mid"]) <= a["width"]) for a in anchors}

    for i in range(n):
        bar = day_df.iloc[i]
        g = gidx0 + i
        ts = bar["timestamp_et"]

        fires: dict[str, tuple[float, dict]] = {}

        # A. wick-defense (existing detector, module defaults; all mids in one call)
        lvl = detect_wick_reclaim_bullish(bar, mids)
        if lvl is not None:
            a = min(by_mid.values(), key=lambda x: abs(x["mid"] - lvl))
            fires["A_wick"] = (lvl, a)

        # B. touch-and-hold (existing detector, per-anchor with the anchor's OWN zone_width;
        # necessary-condition pre-screen only -- the real detector stays authoritative)
        b_hits: list[tuple[float, dict]] = []
        if i >= PULLBACK_MIN_HOLD:
            w0 = max(0, i - PULLBACK_LOOKBACK)
            for a in anchors:
                if not inband[a["mid"]][w0:max(w0, i - PULLBACK_MIN_HOLD + 1)].any():
                    continue
                lvl_b = detect_pullback_hold_bullish(
                    bar, day_df, i, [a["mid"]],
                    zone_band_dollars=a["width"],
                    min_hold_bars=PULLBACK_MIN_HOLD, lookback_bars=PULLBACK_LOOKBACK)
                if lvl_b is not None:
                    b_hits.append((lvl_b, a))
        if b_hits:
            # frozen tie-break: tightest |bar low - mid|
            lvl_b, a_b = min(b_hits, key=lambda t: abs(float(bar["low"]) - t[1]["mid"]))
            fires["B_hold"] = (lvl_b, a_b)

        # C. close-cross reclaim (existing live trigger; block_elite_bull NOT applied)
        lvl_c = detect_level_reclaim(bar, mids)
        if lvl_c is not None:
            a_c = min(by_mid.values(), key=lambda x: abs(x["mid"] - lvl_c))
            fires["C_cross"] = (lvl_c, a_c)

        if not fires:
            continue

        t = ts.time()
        f1_ok = (t >= ENTRY_NOT_BEFORE) and not (BLACKOUT[0] <= t < BLACKOUT[1])
        f6_ok = bool(spread_arr[g] >= RIBBON_SPREAD_MIN_CENTS)
        vix_now = float(vix_now_arr[g])
        vix_prior = float(vix_prior_arr[g])
        f9_ok = vix_now < VIX_BULL_HARD_CAP
        f5_bull = stack_arr[g] == "BULL"
        f5_htf_ok = htf_arr[g] != "BEAR"        # None passes (orchestrator convention)
        f8_ok = (vix_now < VIX_BULL_LOW_THRESHOLD
                 or vix_direction(vix_now, vix_prior) == "falling")
        vol_base = vol_baseline_20bar(spy_rth, g)
        f10_ok = bool(closes[i] > opens[i] and vol_base > 0
                      and float(bar["volume"]) >= F10_VOL_MULT * vol_base)

        for geom, (lvl_f, a_f) in fires.items():
            signals.append({
                "day": day.isoformat(), "bar_i": i, "gidx": g,
                "bar_ts": ts.isoformat(), "entry_tick": (ts + pd.Timedelta(minutes=5)).isoformat(),
                "geometry": geom, "level": float(lvl_f),
                "anchor_mid": a_f["mid"], "zone_floor": a_f["floor"],
                "zone_width": a_f["width"], "touches": a_f["touches"],
                "span_sessions": a_f["span"], "trig_close": float(closes[i]),
                "f1_ok": f1_ok, "f6_ok": f6_ok, "f9_ok": f9_ok,
                "f5_bull": bool(f5_bull), "f5_htf_ok": bool(f5_htf_ok),
                "f8_ok": bool(f8_ok), "f10_ok": bool(f10_ok),
                "vix_now": round(vix_now, 2),
            })
    return signals


# ================================================================== trade resolution

class TradeResolver:
    """Signal -> (fill, CONTROL walk, ZONE_RIDE walk), cached by identity. Real OPRA only."""

    def __init__(self, shapes: dict, ribbon_lookup: pd.DataFrame,
                 spy_day_frames: dict[str, pd.DataFrame]):
        self.shapes = shapes
        self.ribbon_lookup = ribbon_lookup
        self.spy_day_frames = spy_day_frames
        self.cache: dict[tuple, dict] = {}

    def resolve(self, sig: dict) -> dict:
        day = dt.date.fromisoformat(sig["day"])
        strike = int(round(sig["trig_close"]))
        key = (sig["day"], sig["entry_tick"], strike, round(sig["zone_floor"], 2))
        if key in self.cache:
            return self.cache[key]
        out: dict = {"symbol": option_symbol(day, strike), "strike": strike}
        opt_df = load_opt_et2(out["symbol"])
        if opt_df is None or opt_df.empty:
            out["status"] = "EXCLUDED_NO_OPRA"
            self.cache[key] = out
            return out
        entry_tick = pd.Timestamp(sig["entry_tick"])
        after = opt_df[opt_df["timestamp_et"] >= entry_tick]
        if after.empty:
            out["status"] = "EXCLUDED_NO_PRINT"
            self.cache[key] = out
            return out
        fill = after.iloc[0]
        entry_premium = float(fill["open"])
        if entry_premium <= 0:
            out["status"] = "EXCLUDED_ZERO_PRINT"
            self.cache[key] = out
            return out
        if entry_premium < PREMIUM_FLOOR:
            out["status"] = "EXCLUDED_FLOOR"
            out["entry_premium"] = entry_premium
            self.cache[key] = out
            return out
        fill_ts = pd.Timestamp(fill["timestamp_et"])
        rtd = ribbon_tick_df_for(opt_df, self.ribbon_lookup)
        spy_day = self.spy_day_frames[sig["day"]]
        out.update(status="FILLED", entry_premium=round(entry_premium, 4),
                   fill_ts=fill_ts.isoformat())
        for lane, shape in self.shapes.items():
            r = walk_exit_manager(
                symbol=out["symbol"], side="C", entry_time_et=fill_ts.to_pydatetime(),
                entry_premium=entry_premium, qty=QTY, exit_shape=shape,
                structure_stop_enabled=True, trigger_level=float(sig["zone_floor"]),
                strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
                opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=spy_day)
            out[lane] = {"pnl": round(r.dollar_pnl, 2), "exit_reason": r.exit_reason,
                         "exit_time": (r.exit_time_et.isoformat() if r.exit_time_et else None),
                         "hold_minutes": r.hold_minutes, "resolved": r.resolved}
        if out["CONTROL"]["exit_time"] is None:
            # fill landed on the day's last OPRA bar -- no walkable tick exists (entry+1);
            # excluded rather than silently contributing a $0 row (C7).
            out = {"symbol": out["symbol"], "strike": strike, "status": "EXCLUDED_NO_WALK"}
        self.cache[key] = out
        return out


# ================================================================== cell machinery

def admitted(sig: dict, f5: str, f8: bool, f10: bool) -> bool:
    if not (sig["f1_ok"] and sig["f6_ok"] and sig["f9_ok"]):
        return False
    if f5 == "require" and not sig["f5_bull"]:
        return False
    if f5 == "htf" and not sig["f5_htf_ok"]:
        return False
    if f8 and not sig["f8_ok"]:
        return False
    if f10 and not sig["f10_ok"]:
        return False
    return True


def run_entry_cell(stream: list[dict], f5: str, f8: bool, f10: bool,
                   resolver: TradeResolver) -> dict:
    """Occupancy pass (one-position-at-a-time; busy-until = CONTROL exit time -- prereg
    convention so both lanes share an identical trade set). Exclusions do NOT consume
    occupancy (disclosed). Returns taken trades + exclusion counts."""
    taken: list[dict] = []
    excl = {"EXCLUDED_NO_OPRA": 0, "EXCLUDED_NO_PRINT": 0, "EXCLUDED_ZERO_PRINT": 0,
            "EXCLUDED_FLOOR": 0, "EXCLUDED_NO_WALK": 0}
    n_admitted = 0
    n_occupied = 0
    busy_until: Optional[pd.Timestamp] = None
    cur_day = None
    for sig in stream:
        if not admitted(sig, f5, f8, f10):
            continue
        n_admitted += 1
        if sig["day"] != cur_day:
            cur_day = sig["day"]
            busy_until = None
        entry_tick = pd.Timestamp(sig["entry_tick"])
        if busy_until is not None and not (entry_tick > busy_until):
            n_occupied += 1
            continue
        res = resolver.resolve(sig)
        if res["status"] != "FILLED":
            excl[res["status"]] += 1
            continue
        ctl_exit = res["CONTROL"]["exit_time"]
        busy_until = pd.Timestamp(ctl_exit) if ctl_exit else entry_tick
        taken.append({**sig, **{k: res[k] for k in ("symbol", "strike", "entry_premium",
                                                     "fill_ts", "CONTROL", "ZONE_RIDE")}})
    return {"taken": taken, "n_admitted": n_admitted, "n_occupied_skips": n_occupied,
            "exclusions": excl}


def lane_stats(trades: list[dict], lane: str, cutoff_oos: str, recent_start: str) -> dict:
    n = len(trades)
    base = {"n": n, "total_pnl": 0.0, "win_rate": None, "expectancy": None,
            "p_value_raw": 1.0}
    if n == 0:
        return {**base, "day_majority": {"win_days": 0, "days": 0, "is_majority": None},
                "drop_best": {"best": None, "total_minus_best": 0.0, "still_positive": None},
                "held_out": {"cutoff": cutoff_oos, "n": 0, "total_pnl": 0.0},
                "recent_25": {"start": recent_start, "n": 0, "total_pnl": 0.0,
                               "win_rate": None, "expectancy": None},
                "concentration_top_day_share": None}
    pnls = [t[lane]["pnl"] for t in trades]
    total = round(sum(pnls), 2)
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t["day"]] = by_day.get(t["day"], 0.0) + t[lane]["pnl"]
    win_days = sum(1 for v in by_day.values() if v > 0)
    best = max(pnls)
    held = [t[lane]["pnl"] for t in trades if t["day"] >= cutoff_oos]
    recent = [t[lane]["pnl"] for t in trades if t["day"] >= recent_start]
    pos_share = None
    if total > 0:
        top_day = max(by_day.values())
        pos_share = round(top_day / total, 3) if total else None
    return {
        "n": n, "total_pnl": total,
        "win_rate": round(sum(1 for x in pnls if x > 0) / n, 4),
        "expectancy": round(total / n, 2),
        "p_value_raw": round(one_sample_p(pnls), 5),
        "day_majority": {"win_days": win_days, "days": len(by_day),
                          "is_majority": win_days > len(by_day) / 2.0},
        "drop_best": {"best": round(best, 2), "total_minus_best": round(total - best, 2),
                       "still_positive": (total - best) > 0},
        "held_out": {"cutoff": cutoff_oos, "n": len(held),
                      "total_pnl": round(sum(held), 2)},
        "recent_25": {"start": recent_start, "n": len(recent),
                       "total_pnl": round(sum(recent), 2),
                       "win_rate": (round(sum(1 for x in recent if x > 0) / len(recent), 4)
                                     if recent else None),
                       "expectancy": (round(sum(recent) / len(recent), 2) if recent else None)},
        "concentration_top_day_share": pos_share,
    }


# ================================================================== anchors

def check_anchors(raw_streams: dict[str, list[dict]]) -> list[dict]:
    out = []
    for a in ANCHORS:
        sigs = [s for s in raw_streams[a["geometry"]] if s["day"] == a["day"]]
        lo = pd.Timestamp(f"{a['day']} {a['entry_tick_lo']}:00")
        hi = pd.Timestamp(f"{a['day']} {a['entry_tick_hi']}:00")
        hits = [s for s in sigs
                if lo <= pd.Timestamp(s["entry_tick"]) <= hi
                and abs(s["anchor_mid"] - a["level"]) <= a["tol"]]
        near = None
        if not hits and sigs:
            near = min(sigs, key=lambda s: abs(pd.Timestamp(s["entry_tick"]) - lo))
            near = {"entry_tick": near["entry_tick"], "anchor_mid": near["anchor_mid"],
                    "level": near["level"]}
        out.append({**a, "hit": bool(hits),
                    "matches": [{"entry_tick": h["entry_tick"], "anchor_mid": h["anchor_mid"]}
                                for h in hits[:3]],
                    "nearest_miss": near,
                    "n_day_signals_this_geometry": len(sigs)})
    return out


# ================================================================== main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    # CONTROL byte-identity assertion (runner-cohort no-regression gate, prereg section 9.8)
    control_shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    assert control_shape == fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    zone_ride = dict(control_shape, trail_pct=0.2)
    shapes = {"CONTROL": control_shape, "ZONE_RIDE": zone_ride}
    log(f"CONTROL shape (registry byte-identical): {json.dumps(control_shape)}")
    log(f"ZONE_RIDE  shape: trail_pct=0.2 overlay")

    log("loading SPY/VIX merged frames (et-v2)")
    spy_raw = load_merged(OLD_SPY, NEW_SPY)
    vix_raw = load_merged(OLD_VIX, NEW_VIX)
    spy_rth = build_rth(spy_raw)
    all_days = [d for d in sorted(spy_rth["timestamp_et"].dt.date.unique())
                if FULL_START <= d <= FULL_END and d not in HALF_DAYS]
    log(f"population: {len(all_days)} RTH sessions {all_days[0]}..{all_days[-1]} "
        f"(expected {EXPECTED_DAYS}; 3 half-days excluded)")
    if len(all_days) != EXPECTED_DAYS:
        log("FATAL: population != the verified 391 -- aborting before any cell is computed")
        return 1

    study_days = all_days[-4:] if args.smoke else all_days
    cutoff_oos = all_days[int(len(all_days) * 0.75)].isoformat()   # last-25% OOS
    recent_start = all_days[-25].isoformat()                        # recent-25 first-class
    log(f"held-out cutoff {cutoff_oos} | recent-25 start {recent_start} | "
        f"study_days={len(study_days)} (smoke={args.smoke})")

    log("precomputing continuous series: ribbon(stack,spread), htf-15m, vix align, daily bars")
    ribbon_df = compute_ribbon(spy_rth["close"].reset_index(drop=True))
    stack_arr = ribbon_df["stack"].tolist()
    spread_arr = ribbon_df["spread_cents"].to_numpy()
    htf_arr = _precompute_htf_15m_stacks(spy_rth)
    vix_close = vix_raw[["timestamp_et", "close"]].sort_values("timestamp_et")
    aligned = pd.merge_asof(spy_rth[["timestamp_et"]], vix_close, on="timestamp_et",
                            direction="backward")
    vix_now_arr = aligned["close"].ffill().to_numpy()
    vix_prior_arr = pd.Series(vix_now_arr).shift(1).fillna(pd.Series(vix_now_arr)).to_numpy()
    daily_bars = build_daily_bars(spy_rth)
    ribbon_lookup = spy_rth[["timestamp_et"]].copy()
    ribbon_lookup["stack"] = ribbon_df["stack"].values

    day_frames: dict[str, pd.DataFrame] = {}
    gidx0: dict[str, int] = {}
    for d, grp in spy_rth.groupby(spy_rth["timestamp_et"].dt.date, sort=True):
        day_frames[d.isoformat()] = grp.reset_index(drop=True)
        gidx0[d.isoformat()] = int(grp.index[0])

    # ---------------- per-day anchor feed + raw signal scan ----------------
    raw_streams: dict[str, list[dict]] = {g: [] for g in ("A_wick", "B_hold", "C_cross")}
    n_days_with_anchors = 0
    anchors_per_day: list[int] = []
    for k, day in enumerate(study_days):
        dkey = day.isoformat()
        day_df = day_frames.get(dkey)
        if day_df is None or day_df.empty:
            continue
        zones = shelf_zones_asof(daily_bars, day)
        day_open = float(day_df["open"].iloc[0])
        anchors = []
        for z in zones:
            mid = round((z["band_low"] + z["band_high"]) / 2.0, 2)
            if abs(mid - day_open) > SPOT_BAND:
                continue
            anchors.append({"mid": mid, "floor": float(z["band_low"]),
                            "ceil": float(z["band_high"]),
                            "width": round((z["band_high"] - z["band_low"]) / 2.0, 4),
                            "touches": int(z["touches"]),
                            "span": int(z["span_sessions"])})
        anchors_per_day.append(len(anchors))
        if not anchors:
            continue
        n_days_with_anchors += 1
        sigs = scan_day(day, day_df, gidx0[dkey], anchors, stack_arr, spread_arr,
                        htf_arr, vix_now_arr, vix_prior_arr, spy_rth)
        for s in sigs:
            raw_streams[s["geometry"]].append(s)
        if (k + 1) % 50 == 0:
            log(f"  scanned {k + 1}/{len(study_days)} days "
                f"(raw A={len(raw_streams['A_wick'])} B={len(raw_streams['B_hold'])} "
                f"C={len(raw_streams['C_cross'])})")

    # UNION stream: all fires ordered by bar, frozen priority A>B>C within a bar
    union: list[dict] = []
    all_sigs = sorted((s for g in ("A_wick", "B_hold", "C_cross") for s in raw_streams[g]),
                      key=lambda s: (s["day"], s["bar_i"], UNION_PRIORITY[s["geometry"]]))
    seen_bars: set[tuple] = set()
    for s in all_sigs:
        bk = (s["day"], s["bar_i"])
        if bk in seen_bars:
            continue
        seen_bars.add(bk)
        union.append(s)
    streams = {**raw_streams, "UNION": union}
    log(f"raw fires: A={len(raw_streams['A_wick'])} B={len(raw_streams['B_hold'])} "
        f"C={len(raw_streams['C_cross'])} UNION={len(union)} | "
        f"days with anchors {n_days_with_anchors}/{len(study_days)}")

    anchors_report = check_anchors(raw_streams)
    for a in anchors_report:
        log(f"  anchor {a['tag']} ({a['geometry']}): hit={a['hit']}"
            + (f" nearest_miss={a['nearest_miss']}" if not a["hit"] else ""))

    # ---------------- cells ----------------
    resolver = TradeResolver(shapes, ribbon_lookup, day_frames)
    cells: list[dict] = []
    for geom in GEOMETRIES:
        for f5 in F5_MODES:
            for f8 in (True, False):
                for f10 in (True, False):
                    ec = run_entry_cell(streams[geom], f5, f8, f10, resolver)
                    for lane in LANES:
                        st = lane_stats(ec["taken"], lane, cutoff_oos, recent_start)
                        cells.append({
                            "cell_id": f"{geom}|f5={f5}|f8={'on' if f8 else 'off'}|"
                                       f"f10={'on' if f10 else 'off'}|{lane}",
                            "geometry": geom, "f5": f5, "f8": f8, "f10": f10, "lane": lane,
                            "n_admitted": ec["n_admitted"],
                            "n_occupied_skips": ec["n_occupied_skips"],
                            "exclusions": ec["exclusions"],
                            "stats": st,
                            "is_primary": (
                                f5 == PRIMARY_COMBO["f5"] and f8 == PRIMARY_COMBO["f8"]
                                and f10 == PRIMARY_COMBO["f10"]
                                and lane == PRIMARY_COMBO["lane"]),
                        })
        log(f"  cells done for {geom}")

    sig_flags = bh_fdr([c["stats"]["p_value_raw"] for c in cells], q=0.10)
    for c, s in zip(cells, sig_flags):
        c["stats"]["bh_fdr_significant_q10"] = bool(s)

    # ---------------- gates on primary cells ----------------
    primary = {c["geometry"]: c for c in cells if c["is_primary"]}
    exp = {g: primary[g]["stats"]["expectancy"] for g in GEOMETRIES if g in primary}

    def _num(x):
        return x if isinstance(x, (int, float)) else float("-inf")

    dose = {
        "expectancy_by_geometry": exp,
        "A_gt_C": _num(exp.get("A_wick")) > _num(exp.get("C_cross")),
        "B_gt_C": _num(exp.get("B_hold")) > _num(exp.get("C_cross")),
        "ordering": sorted((g for g in ("A_wick", "B_hold", "C_cross") if g in exp),
                           key=lambda g: _num(exp[g]), reverse=True),
    }

    verdicts = {}
    for g in GEOMETRIES:
        c = primary.get(g)
        if c is None:
            continue
        st = c["stats"]
        n = st["n"]
        if n < 15:
            verdicts[g] = {"verdict": "UNDERPOWERED", "n": n}
            continue
        gates = {
            "g1_positive_aggregate": st["total_pnl"] > 0,
            "g2_day_majority": bool(st["day_majority"]["is_majority"]),
            "g3_drop_best": bool(st["drop_best"]["still_positive"]),
            "g4_held_out_nonneg": st["held_out"]["total_pnl"] >= 0,
            "g5_recent25_nonneg": st["recent_25"]["total_pnl"] >= 0,
            "g6_dose_response": (dose["A_gt_C"] and dose["B_gt_C"]),
            "g7_bh_fdr": bool(st["bh_fdr_significant_q10"]),
        }
        ships_shadow = all(v for k, v in gates.items() if k != "g5_recent25_nonneg")
        verdicts[g] = {
            "verdict": ("SHIP_SHADOW+QUEUE_ARMING" if ships_shadow and gates["g5_recent25_nonneg"]
                        else "SHIP_SHADOW_STALE_EDGE" if ships_shadow
                        else "NULL"),
            "n": n, "gates": gates,
        }

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": "analysis/recommendations/shelf-hold-reclaim-prereg-2026-08-01.md @ 96a85efc",
        "frame": "et-v2 (lib/et_frame.py) -- see module docstring FRAME DISCLOSURE",
        "smoke": bool(args.smoke),
        "population": {"n_days": len(study_days), "start": study_days[0].isoformat(),
                        "end": study_days[-1].isoformat(),
                        "held_out_cutoff": cutoff_oos, "recent_25_start": recent_start,
                        "n_days_with_anchors": n_days_with_anchors,
                        "mean_anchors_per_day": (round(sum(anchors_per_day)
                                                        / len(anchors_per_day), 2)
                                                  if anchors_per_day else 0.0)},
        "conventions": {
            "qty": QTY, "premium_floor": PREMIUM_FLOOR, "time_stop_et": "15:40",
            "entry": "trigger-bar close instant -> first OPRA bar open (entry+1 walk)",
            "strike": "ATM = round(trigger close)", "occupancy": "CONTROL exit time, paired lanes",
            "structure_stop": "zone floor (band_low)", "exclusions_consume_occupancy": False,
        },
        "control_shape": control_shape, "zone_ride_shape": zone_ride,
        "anchors": anchors_report,
        "raw_fire_counts": {g: len(streams[g]) for g in GEOMETRIES},
        "dose_response": dose,
        "verdicts": verdicts,
        "cells": cells,
        "deviations": [
            "frame: et-v2 opt-in (prereg cited ladder loader for file lineage; wall-v1 would "
            "inject winter VIX look-ahead (C6) + clip the last true hour on 129 EST days; "
            "decided before first run)",
            "exclusions do not consume occupancy (unmeasurable != untradeable; disclosed)",
            "F7 volume-divergence not applied (prereg section 5)",
            "population: 3 half-day sessions (2025-07-03, 2025-11-28, 2025-12-24) excluded "
            "to match the VERIFIED 391-day population (WS6 et-v2 lineage); decided before "
            "the full run. 2026-06-15 (12-bar data-gap day) stays in population.",
        ],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    dest = SMOKE_JSON if args.smoke else OUT_JSON
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {dest}")
    log(f"verdicts: { {g: v['verdict'] for g, v in verdicts.items()} }")
    log(f"runtime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
