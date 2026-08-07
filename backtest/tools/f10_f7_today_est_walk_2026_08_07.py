"""f10_f7_today_est_walk_2026_08_07.py -- LANE 2 part 1: what did the filter-10/filter-7
bull refusal cost TODAY (2026-08-07), per arm and book. EST-LABELED THROUGHOUT.

CONTEXT (broker-verified, core-decisions.jsonl-verified this session):
  - Morning: all 4 active arms entered 09:46-09:47 on the PDH-771.82 push (772C/774C),
    stopped 10:01-10:02 on the pullback. Day -$629.46 realized at 11:46 ET. ZERO re-entries
    in the morning (Wednesday spiral shape did NOT recur).
  - 10:15-11:45: 182 verdicts ALL HOLD. Sole-blocked bull ticks (score 10/11, level_reclaim
    + confluence carried): filter 10 x27/account, filter 7 x5/account, filter 11 x5/account
    (Rule-2 firewalled, NOT liftable, reported only).
  - The refusal actually extended to 12:05 (sole-[10] 11:46-11:55, joint [7,10] 11:56-12:05)
    and the engine ENTERED at 12:06:03 (safe 3x 773C @ 1.11; fleet arms mirrored;
    bold-2/core-bold RISK_DENY_PDT -- dark all day). SPY 770.50 -> 773.17 underneath the
    10:15-11:46 refusal.

WHAT THIS SCRIPT DOES (no OPRA for today until ~16:21 ET -- the 403 wall):
  1. Builds an EST premium surface: Black-Scholes calls, IV calibrated by bisection at 6
     REAL fill anchors from today (09:46 772C 1.67 / 09:47 774C 0.62 / 10:02 772C 1.16 /
     10:02 774C 0.45 / 12:06 773C 1.11 / 12:06 775C 0.31), sigma interpolated linearly in
     moneyness (K-S) and entry-time between anchor time-nodes. SPY 1-min bars from Alpaca
     stock data API (serves live; provenance logged) -- fallback yfinance.
     VALIDATION: the surface is scored OUT-OF-SAMPLE against the engine's own exit_pass
     best/worst premium marks (772C, 09:48-10:01, never used in calibration); MAE reported.
  2. Sequentially walks the FIRST admissible relaxed entry per cell through the REAL
     production exit engine (lib.exit_manager_walk.walk_exit_manager ->
     exit_manager.plan_exit_actions -- NEVER simulator_real, 07-09 scar):
       relax_f10  : first sole-[10] tick  = 10:15:03 ET (trigger 770.46)
       relax_f7   : first sole-[7] tick   = 10:21:03 ET (trigger 771.51)
       relax_both : first sole-[10 or 7]  = 10:15:03 ET (same as relax_f10 -- they overlap;
                    sequential walk, never summed)
     One position at a time, NO re-entries after the walked trade (PDT-conservative: the
     walked trade REPLACES the actual 12:06 entry, so each arm still makes exactly 2 round
     trips today -- proven PDT-legal by the fact the arms actually DID re-enter at 12:06).
     bold-2/core-bold excluded ($0 cells): RISK_DENY_PDT at both 09:46 and 12:06 -- the
     relaxation cannot manufacture PDT headroom.
  3. HONEST COUNTER-CELL (morning loser under the same relaxation): census-verified ZERO
     pre-09:46 sole-[10]/[7] ticks exist (09:35-09:45 blockers were [1,5,6,11] then
     [6,10,11] -- multi-blocked; lifting 10 and/or 7 admits nothing earlier), and the
     actual 09:46 entry fired with ZERO blockers, so it is IDENTICAL under relaxation.
     Morning delta = $0.00 exactly. The netting is therefore:
       refusal_cost(cell) = walk_pnl(cell) - actual_1206_pnl_marked_at_same_bar
     (both legs EST-marked at the same terminal bar; morning leg cancels).

  Per-arm exit shapes come from the PRODUCTION fleet_executor._exit_shape_dict(strat, arm)
  (RIBBON_RIDE base + accounts.json params_patch.exit_patch overlay), parity-checked
  against each arm's live exit-state.json row from today. ribbon_tick_df=None (ribbon-flip
  exit unavailable in the walk -- same disclosed limitation as every prior walk study;
  chandelier + structure-stop + TP1 + catastrophe are all active).

EVERY DOLLAR CELL PRODUCED HERE IS "EST" -- the evening re-price addendum on real OPRA
(after ~16:21 ET) is part of the staged package, not this run.

Rail-4 CLEAR: analysis only, reads live state, writes only analysis/recommendations/.
Run: backtest/.venv/Scripts/python.exe backtest/tools/f10_f7_today_est_walk_2026_08_07.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import fleet_broker  # noqa: E402
import fleet_executor  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402

TODAY = dt.date(2026, 8, 7)
DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
ACCOUNTS = ROOT / "automation" / "state" / "fleet" / "accounts.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "f10-f7-today-est-walk-2026-08-07.json"
TIME_STOP_ET = dt.time(15, 40)

# REAL fill anchors (broker-verified this morning + live exit-state.json at ~12:07 ET).
# (ts_et, strike, premium)
ANCHORS = [
    ("2026-08-07T09:46:34", 772, 1.67),
    ("2026-08-07T09:47:00", 774, 0.62),
    ("2026-08-07T10:02:00", 772, 1.16),
    ("2026-08-07T10:02:00", 774, 0.45),
    ("2026-08-07T12:06:34", 773, 1.11),
    ("2026-08-07T12:06:34", 775, 0.31),
]

# Arms: (arm_id, qty_today, strike_offset_from_round_atm). bold-2 excluded (PDT-dark).
ARMS = [
    ("safe-2", 3, 0),
    ("safe-3", 8, 0),
    ("risky-1", 5, 0),
    ("risky-3", 12, 2),
]

# Actual 12:06 entries (live exit-state.json truth, quoted this session).
ACTUAL_1206 = {
    "safe-2": {"strike": 773, "qty": 3, "entry_premium": 1.11},
    "safe-3": {"strike": 773, "qty": 8, "entry_premium": 1.10},
    "risky-1": {"strike": 773, "qty": 5, "entry_premium": 1.09},
    "risky-3": {"strike": 775, "qty": 12, "entry_premium": 0.31},
}
ACTUAL_MORNING_REALIZED = {  # broker-verified, REAL (not EST)
    "safe-2": -153.0, "safe-3": -176.0, "risky-1": -95.0, "risky-3": -205.0,
}


def log(m: str) -> None:
    print(f"[today-est-walk] {m}", flush=True)


# ============================================================ SPY 1-min bars (live-legal)
def fetch_spy_1min() -> tuple[pd.DataFrame, str]:
    start = f"{TODAY}T09:30:00-04:00"
    end = f"{TODAY}T16:00:00-04:00"
    for cred_name, arm in fleet_broker.load_creds().items():
        for feed in ("sip", "iex"):
            url = (f"{fleet_broker.OPTIONS_DATA_HOST}/v2/stocks/SPY/bars?timeframe=1Min"
                   f"&start={urllib.request.quote(start)}&end={urllib.request.quote(end)}"
                   f"&feed={feed}&limit=10000")
            req = urllib.request.Request(url, headers={
                "APCA-API-KEY-ID": arm["key"], "APCA-API-SECRET-KEY": arm["secret"]})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except Exception as e:  # noqa: BLE001 -- provenance matters more than type
                log(f"creds={cred_name} feed={feed} fetch failed: {e}")
                continue
            bars = data.get("bars") or []
            if not bars:
                continue
            df = pd.DataFrame(bars)
            # Alpaca returns RFC3339 UTC 't'; convert to naive ET wall time (summer: EDT).
            ts = (pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
                  .dt.tz_localize(None))
            out = pd.DataFrame({"timestamp_et": ts, "open": df["o"], "high": df["h"],
                                "low": df["l"], "close": df["c"], "volume": df["v"]})
            out = out[(out["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (out["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
            return out, f"alpaca:{feed} (creds={cred_name})"
    # keyless fallback: yfinance 1-min (sight-beacon fallback pattern; provenance labeled)
    try:
        import yfinance as yf  # noqa: PLC0415
        df = yf.download("SPY", interval="1m", period="1d", progress=False,
                         auto_adjust=False)
        if df is not None and not df.empty:
            if hasattr(df.columns, "get_level_values") and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)
            idx = pd.to_datetime(df.index)
            if idx.tz is not None:
                idx = idx.tz_convert("America/New_York").tz_localize(None)
            out = pd.DataFrame({
                "timestamp_et": idx, "open": df["Open"].values, "high": df["High"].values,
                "low": df["Low"].values, "close": df["Close"].values,
                "volume": df["Volume"].values})
            out = out[(out["timestamp_et"].dt.date == TODAY)
                      & (out["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (out["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
            if not out.empty:
                return out, "yfinance:1m"
    except Exception as e:  # noqa: BLE001
        log(f"yfinance fallback failed: {e}")
    raise RuntimeError("no SPY 1-min bars from any source -- aborting (no silent fallback)")


def to_5min(one_min: pd.DataFrame) -> pd.DataFrame:
    g = one_min.set_index("timestamp_et").resample("5min", label="left", closed="left")
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(),
        "low": g["low"].min(), "close": g["close"].last(),
        "volume": g["volume"].sum(),
    }).dropna(subset=["close"]).reset_index()
    return out


def engine_tape_5min(rows: list[dict], iex_5min: pd.DataFrame) -> pd.DataFrame:
    """5-min SPY frame whose CLOSES are the ENGINE'S OWN logged closed-bar values
    ((trigger_bar_et -> spy) pairs from core-decisions.jsonl -- the SIP-fed tape the live
    engine actually saw), OHL filled from the IEX resample. Motivation: the structure stop
    compares closed-5m CLOSE vs trigger level; today's first relaxed entry (770.495 vs
    trigger 770.46) sits 3.5c above the level, and an IEX-vs-SIP close discrepancy at that
    razor edge flips the stop. Feeding the engine's own closes removes that artifact."""
    closes: dict[dt.datetime, float] = {}
    for r in rows:
        tb = r.get("trigger_bar_et")
        spy = r.get("spy")
        if not tb or spy is None:
            continue
        try:
            ts = pd.Timestamp(tb)
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
        except (ValueError, TypeError):
            continue
        closes[ts.to_pydatetime()] = float(spy)
    out = iex_5min.copy()
    matched = 0
    new_close = []
    for _, b in out.iterrows():
        ts = pd.Timestamp(b["timestamp_et"]).to_pydatetime()
        if ts in closes:
            new_close.append(closes[ts])
            matched += 1
        else:
            new_close.append(float(b["close"]))
    out["close"] = new_close
    log(f"engine-tape 5m closes: {matched}/{len(out)} bars from engine rows, "
        f"rest IEX-resampled")
    return out


# ============================================================ EST premium surface (BS)
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(s: float, k: float, t_years: float, sigma: float) -> float:
    if t_years <= 0 or sigma <= 0:
        return max(0.0, s - k)
    sq = sigma * math.sqrt(t_years)
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t_years) / sq
    return s * _norm_cdf(d1) - k * _norm_cdf(d1 - sq)


def t_to_close_years(ts: dt.datetime) -> float:
    close = dt.datetime.combine(ts.date(), dt.time(16, 0))
    mins = max(0.0, (close - ts).total_seconds() / 60.0)
    return mins / (365.0 * 24.0 * 60.0)


def implied_sigma(s: float, k: float, t_years: float, price: float) -> float:
    lo, hi = 0.01, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if bs_call(s, k, t_years, mid) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


class EstSurface:
    """sigma(t, moneyness) from real-fill anchors: linear in moneyness (K-S) inside each
    anchor time-node, linear in time between nodes, clamped outside. EST by construction."""

    def __init__(self, one_min: pd.DataFrame):
        self.nodes: list[tuple[dt.datetime, list[tuple[float, float]]]] = []
        by_time: dict[str, list] = {}
        for ts_s, k, prem in ANCHORS:
            # bucket to 10-minute windows so the 09:46 ATM + 09:47 OTM anchors form ONE
            # 2-point moneyness node (single-point nodes make sigma flat in moneyness)
            bucket = ts_s[:15]
            by_time.setdefault(bucket, []).append((ts_s, k, prem))
        for _, group in sorted(by_time.items()):
            pts = []
            t_node = None
            for ts_s, k, prem in group:
                ts = dt.datetime.fromisoformat(ts_s)
                t_node = ts
                s = self.spot_at(one_min, ts)
                sig = implied_sigma(s, k, t_to_close_years(ts), prem)
                pts.append((k - s, sig))
            pts.sort()
            self.nodes.append((t_node, pts))
        self.one_min = one_min

    @staticmethod
    def spot_at(one_min: pd.DataFrame, ts: dt.datetime) -> float:
        prior = one_min[one_min["timestamp_et"] <= ts]
        if prior.empty:
            return float(one_min.iloc[0]["open"])
        return float(prior.iloc[-1]["close"])

    @staticmethod
    def _interp_m(pts: list[tuple[float, float]], m: float) -> float:
        if len(pts) == 1:
            return pts[0][1]
        (m0, s0), (m1, s1) = pts[0], pts[-1]
        if m1 == m0:
            return s0
        # linear, extrapolation clamped to the segment slope inside [m0-1, m1+1]
        w = (m - m0) / (m1 - m0)
        return s0 + (s1 - s0) * max(-0.5, min(1.5, w))

    def sigma(self, ts: dt.datetime, m: float) -> float:
        nodes = self.nodes
        if ts <= nodes[0][0]:
            return self._interp_m(nodes[0][1], m)
        if ts >= nodes[-1][0]:
            return self._interp_m(nodes[-1][1], m)
        for i in range(len(nodes) - 1):
            t0, p0 = nodes[i]
            t1, p1 = nodes[i + 1]
            if t0 <= ts <= t1:
                s0, s1 = self._interp_m(p0, m), self._interp_m(p1, m)
                w = (ts - t0).total_seconds() / max(1.0, (t1 - t0).total_seconds())
                return s0 + (s1 - s0) * w
        return self._interp_m(nodes[-1][1], m)

    def price(self, ts: dt.datetime, s: float, k: float) -> float:
        return bs_call(s, k, t_to_close_years(ts), self.sigma(ts, k - s))

    def contract_frame(self, strike: int, start: dt.datetime) -> pd.DataFrame:
        """EST 1-min OHLC premium frame for one call contract from `start` to data end.
        Calls are monotone-increasing in S, so SPY O/H/L/C map to premium O/H/L/C."""
        rows = []
        for _, b in self.one_min[self.one_min["timestamp_et"] >= start].iterrows():
            ts = b["timestamp_et"].to_pydatetime()
            rows.append({
                "timestamp_et": ts,
                "open": self.price(ts, float(b["open"]), strike),
                "high": self.price(ts, float(b["high"]), strike),
                "low": self.price(ts, float(b["low"]), strike),
                "close": self.price(ts, float(b["close"]), strike),
            })
        return pd.DataFrame(rows)


# ============================================================ decision-row mining
def load_today_rows() -> list[dict]:
    rows = []
    with DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            if '"2026-08-07' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("ts_et", "")).startswith("2026-08-07"):
                rows.append(r)
    return rows


def census(rows: list[dict]) -> dict:
    def hhmm(r):
        return r["ts_et"][11:16]
    win = [r for r in rows if "10:15" <= hhmm(r) <= "11:45"]
    ext = [r for r in rows if "11:46" <= hhmm(r) <= "12:05"]
    morn = [r for r in rows if "09:35" <= hhmm(r) <= "09:45"]

    def sole(rs, fid):
        return [r for r in rs if r["bull_blockers"] == [fid]]

    morning_sole = [r for r in morn if len(r["bull_blockers"]) == 1
                    and r["bull_blockers"][0] in (7, 10)]
    return {
        "window_10_15_to_11_45": {
            "verdicts": len(win), "all_hold": all(r["verdict"] == "HOLD" for r in win),
            "sole_f10_per_account": len(sole([r for r in win if r["account"] == "safe"], 10)),
            "sole_f7_per_account": len(sole([r for r in win if r["account"] == "safe"], 7)),
            "sole_f11_per_account_firewalled_not_liftable": len(
                sole([r for r in win if r["account"] == "safe"], 11)),
        },
        "extension_11_46_to_12_05": {
            "sole_f10_per_account": len(sole([r for r in ext if r["account"] == "safe"], 10)),
            "joint_f7_f10_per_account": len(
                [r for r in ext if r["account"] == "safe" and r["bull_blockers"] == [7, 10]]),
            "note": "with f10 relaxed the latest possible entry was 11:46, vs actual 12:06",
        },
        "morning_counter_cell": {
            "pre_0946_sole_f10_or_f7_ticks": len(morning_sole),
            "actual_0946_entry_blockers": [],
            "delta_dollars": 0.0,
            "verdict": "relaxation does NOT enlarge the morning loser -- 09:35-09:45 all "
                       "multi-blocked ([1,5,6,11] then [6,10,11]); 09:46 entry identical",
        },
    }


def admissible_ticks(rows: list[dict], fids: tuple[int, ...]) -> list[dict]:
    """All sole-blocked ticks in the 10:15-11:45 window admissible under the given
    relaxation, chronological (safe-side rows; bold rows are the same minutes)."""
    out = []
    for r in sorted(rows, key=lambda x: x["ts_et"]):
        if r["account"] != "safe":
            continue
        hh = r["ts_et"][11:16]
        if not ("10:15" <= hh <= "11:45"):
            continue
        if len(r["bull_blockers"]) == 1 and r["bull_blockers"][0] in fids:
            out.append(r)
    if not out:
        raise RuntimeError(f"no admissible tick for fids={fids}")
    return out


# ============================================================ per-arm exit shapes
def arm_shapes() -> dict[str, dict]:
    acc = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    arm_list = acc.get("accounts") or acc.get("arms") or []
    arm_recs = {a["id"]: a for a in arm_list if isinstance(a, dict) and a.get("id")}
    strat = fleet_strategies.RIBBON_RIDE
    out = {}
    for arm_id, _, _ in ARMS:
        rec = arm_recs.get(arm_id)
        out[arm_id] = fleet_executor._exit_shape_dict(strat, rec)
    return out


def parity_check_shapes(shapes: dict[str, dict]) -> dict:
    """Compare produced shapes vs today's live exit-state.json rows (the ground truth of
    what the production exit engine is running RIGHT NOW per arm)."""
    checks = {}
    for arm_id, shape in shapes.items():
        p = ROOT / "automation" / "state" / "fleet" / arm_id / "exit-state.json"
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            checks[arm_id] = {"status": "no exit-state"}
            continue
        if not st:
            checks[arm_id] = {"status": "flat"}
            continue
        row = next(iter(st.values()))
        checks[arm_id] = {
            "status": "compared",
            "trail_pct": {"shape": shape.get("trail_pct"), "live": row.get("trail_pct"),
                          "match": shape.get("trail_pct") == row.get("trail_pct")},
            "tp1_premium_pct": {"shape": shape.get("tp1_premium_pct"),
                                "live": row.get("tp1_premium_pct"),
                                "match": shape.get("tp1_premium_pct") == row.get("tp1_premium_pct")},
            "profit_lock_mode": {"shape": shape.get("profit_lock_mode"),
                                 "live": row.get("profit_lock_mode"),
                                 "match": shape.get("profit_lock_mode") == row.get("profit_lock_mode")},
        }
    return checks


# ============================================================ walk one cell for one arm
def walk_cell(arm_id: str, qty: int, offset: int, entry_row: dict, surface: EstSurface,
              five_min: pd.DataFrame, shape: dict) -> dict:
    entry_ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    s_entry = surface.spot_at(surface.one_min, entry_ts)
    strike = int(round(s_entry)) + offset
    opt_df = surface.contract_frame(strike, entry_ts.replace(second=0))
    if opt_df.empty:
        return {"error": "no EST bars"}
    entry_premium = round(float(opt_df.iloc[0]["close"]), 4)
    trigger = entry_row.get("bull_reclaim_level_raw")
    res = walk_exit_manager(
        symbol=f"SPY{TODAY.strftime('%y%m%d')}C{strike * 1000:08d}", side="C",
        entry_time_et=entry_ts, entry_premium=entry_premium, qty=qty,
        exit_shape=shape, structure_stop_enabled=True,
        trigger_level=float(trigger) if trigger is not None else None,
        strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=five_min,
        opt_df_resolution="1min")
    last_bar = opt_df.iloc[-1]
    if res.exit_time_et is None:
        # still open at data end -- mark at last EST close, label OPEN
        pnl = (float(last_bar["close"]) - entry_premium) * qty * 100.0
        return {"arm": arm_id, "strike": strike, "qty": qty,
                "entry_ts_et": entry_ts.isoformat(), "entry_premium_EST": entry_premium,
                "status": "OPEN_AT_DATA_END", "marked_at": str(last_bar["timestamp_et"]),
                "pnl_EST": round(pnl, 2), "exit_reason": None}
    status = ("OPEN_AT_DATA_END (marked, not resolved)"
              if res.exit_reason == "data_exhausted_force_close" else "CLOSED")
    return {"arm": arm_id, "strike": strike, "qty": qty,
            "entry_ts_et": entry_ts.isoformat(), "entry_premium_EST": entry_premium,
            "status": status, "pnl_EST": round(res.dollar_pnl, 2),
            "exit_reason": res.exit_reason,
            "exit_time_et": res.exit_time_et.isoformat(),
            "hold_minutes": res.hold_minutes}


def mark_actual_1206(surface: EstSurface) -> dict:
    """Mark the ACTUAL 12:06 entries at the last EST bar (same terminal bar as the walks)."""
    out = {}
    last = surface.one_min.iloc[-1]
    ts = last["timestamp_et"].to_pydatetime()
    for arm_id, pos in ACTUAL_1206.items():
        mark = surface.price(ts, float(last["close"]), pos["strike"])
        pnl = (mark - pos["entry_premium"]) * pos["qty"] * 100.0
        out[arm_id] = {"strike": pos["strike"], "qty": pos["qty"],
                       "entry_premium_REAL": pos["entry_premium"],
                       "mark_EST": round(mark, 4), "marked_at": ts.isoformat(),
                       "pnl_EST": round(pnl, 2), "status": "OPEN (live)"}
    return out


# ============================================================ validation
def validate_surface(rows: list[dict], surface: EstSurface) -> dict:
    """Out-of-sample: engine's own exit_pass premium marks on 772C 09:48-10:01 (calibration
    used only the 09:46 entry and 10:02 stop endpoints)."""
    errs = []
    for r in rows:
        if r["account"] != "safe" or not r.get("exit_pass"):
            continue
        hh = r["ts_et"][11:16]
        if not ("09:48" <= hh <= "10:01"):
            continue
        for ep in r["exit_pass"]:
            if ep.get("symbol") != "SPY260807C00772000":
                continue
            best, worst = ep.get("best_premium"), ep.get("worst_premium")
            if best is None:
                continue
            obs = (float(best) + float(worst or best)) / 2.0
            ts = dt.datetime.fromisoformat(r["ts_et"])
            s = surface.spot_at(surface.one_min, ts)
            model = surface.price(ts, s, 772)
            errs.append({"ts": r["ts_et"], "obs_mid": round(obs, 3),
                         "model_EST": round(model, 3), "err": round(model - obs, 3)})
    mae = round(sum(abs(e["err"]) for e in errs) / len(errs), 4) if errs else None
    return {"n_marks": len(errs), "mae_dollars_per_contract_unit": mae, "detail": errs}


# ============================================================ main
def main() -> int:
    log("fetching SPY 1-min bars (live-legal stock data)")
    one_min, provenance = fetch_spy_1min()
    log(f"bars: {len(one_min)} from {provenance}, "
        f"{one_min.iloc[0]['timestamp_et']} .. {one_min.iloc[-1]['timestamp_et']}")
    rows_for_tape = load_today_rows()
    five_min = engine_tape_5min(rows_for_tape, to_5min(one_min))

    surface = EstSurface(one_min)
    for t_node, pts in surface.nodes:
        log(f"sigma node {t_node}: " + ", ".join(f"m={m:+.2f} sig={s:.3f}" for m, s in pts))

    rows = load_today_rows()
    log(f"decision rows today: {len(rows)}")
    cen = census(rows)
    val = validate_surface(rows, surface)
    log(f"surface validation vs exit_pass marks: n={val['n_marks']} MAE={val['mae_dollars_per_contract_unit']}")

    shapes = arm_shapes()
    parity = parity_check_shapes(shapes)

    cell_fids = {"relax_f10": (10,), "relax_f7": (7,), "relax_both": (10, 7)}
    cells = {}
    for cell_name, fids in cell_fids.items():
        ticks = admissible_ticks(rows, fids)
        per_arm = {}
        for arm_id, qty, offset in ARMS:
            # SEQUENTIAL one-position walk: trip 1 = first admissible tick (replaces the
            # actual 12:06 trade -> 2 round trips today, proven PDT-legal). Trips 2+ would
            # be the day's 3rd+ round trip -- never attempted live, PDT headroom UNPROVEN
            # -> walked anyway but labeled pdt_contingent and EXCLUDED from the primary cell.
            trips = []
            cursor = None
            for tick in ticks:
                tick_ts = dt.datetime.fromisoformat(tick["ts_et"])
                if cursor is not None and tick_ts <= cursor:
                    continue
                res = walk_cell(arm_id, qty, offset, tick, surface, five_min,
                                shapes[arm_id])
                res["pdt_contingent"] = len(trips) >= 1
                trips.append(res)
                if res.get("exit_time_et"):
                    cursor = dt.datetime.fromisoformat(res["exit_time_et"])
                else:
                    break   # open at data end -- sequence over
                if len(trips) >= 3:
                    break
            primary = trips[0]
            per_arm[arm_id] = {
                "primary_trip": primary,
                "pnl_EST": primary.get("pnl_EST", 0.0),
                "extension_trips_pdt_contingent": trips[1:],
                "extended_pnl_EST": round(sum(t.get("pnl_EST", 0.0) for t in trips), 2),
            }
        per_arm["bold-2"] = {"pnl_EST": 0.0, "extended_pnl_EST": 0.0,
                             "primary_trip": {"status": "PDT_DARK"},
                             "note": "RISK_DENY_PDT at 09:46 AND 12:06 -- relaxation cannot "
                                     "manufacture PDT headroom"}
        book = round(sum(v.get("pnl_EST", 0.0) for v in per_arm.values()), 2)
        book_ext = round(sum(v.get("extended_pnl_EST", 0.0) for v in per_arm.values()), 2)
        cells[cell_name] = {"admissible_ticks": [t["ts_et"] for t in ticks],
                            "per_arm": per_arm, "book_pnl_EST": book,
                            "book_extended_pnl_EST_pdt_contingent": book_ext}

    actual = mark_actual_1206(surface)
    actual_book = round(sum(v["pnl_EST"] for v in actual.values()), 2)

    netting = {}
    for cell_name, cell in cells.items():
        per_arm_delta = {}
        for arm_id, _, _ in ARMS:
            w = cell["per_arm"][arm_id].get("pnl_EST", 0.0)
            a = actual.get(arm_id, {}).get("pnl_EST", 0.0)
            per_arm_delta[arm_id] = round(w - a, 2)
        per_arm_delta["bold-2"] = 0.0
        netting[cell_name] = {
            "refusal_cost_book_EST": round(cell["book_pnl_EST"] - actual_book, 2),
            "per_arm_delta_EST": per_arm_delta,
            "morning_counter_cell_delta": 0.0,
        }

    out = {
        "_doc": "LANE2 part 1 -- what the f10/f7 bull refusal cost TODAY (2026-08-07), "
                "per arm and book. ALL dollar cells EST (BS surface calibrated on 6 real "
                "fill anchors; evening re-price on real OPRA is part of the staged package). "
                "Walks: walk_exit_manager -> exit_manager.plan_exit_actions ONLY.",
        "generated_at_et": dt.datetime.now().isoformat(),
        "spy_bars_provenance": provenance,
        "n_spy_1min_bars": len(one_min),
        "last_bar_et": str(one_min.iloc[-1]["timestamp_et"]),
        "sigma_nodes": [{"t": t.isoformat(), "points_m_sigma": pts}
                        for t, pts in surface.nodes],
        "surface_validation_oos": val,
        "census": cen,
        "exit_shape_parity_vs_live_exit_state": parity,
        "cells_EST": cells,
        "actual_1206_positions_marked_EST": actual,
        "actual_1206_book_pnl_EST": actual_book,
        "actual_morning_realized_REAL": ACTUAL_MORNING_REALIZED,
        "netting_EST": netting,
        "caveats": [
            "EST premium surface, not OPRA -- same-day 0DTE bars unavailable until ~16:21 ET",
            "ribbon_tick_df=None: ribbon-flip exit unavailable in walk (standing limitation)",
            "walked cells assume the walked trade REPLACES the actual 12:06 entry (2 round "
            "trips/arm today, proven PDT-legal by the actual 12:06 fills)",
            "no re-entry after the walked trade's exit (PDT-conservative)",
            "positions OPEN at data end are marked at the last EST bar, not resolved",
            "sizing held at each arm's actual morning qty (same-day sizing assumption)",
            "5m closes for the structure stop come from the ENGINE'S OWN logged tape "
            "(trigger_bar_et->spy), not the IEX resample -- removes the razor-edge "
            "IEX-vs-SIP stop artifact at trigger 770.46",
            "surface overprices the first ~6 min post-09:46 (IV crush between the 09:46 "
            "fill and the 10:02 stop is only linearly interpolated) -- walk-window cells "
            "price off the POST-crush 10:02/12:06 nodes and do not inherit that bias",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"BOOK refusal cost EST: " + json.dumps(
        {k: v['refusal_cost_book_EST'] for k, v in netting.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
