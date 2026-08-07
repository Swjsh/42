"""ladder_rung_replay_2026_08_07.py -- LANE 1 replay harness for the SCORE-LADDER-RUNG
proposal (J's 4th+ ask, 2026-08-07: "risky accounts are able to get in on an eight out of
ten, a seven out of ten ... why are we sitting out of anything that's a ten out of eleven?").

Runs EXACTLY the mechanism frozen in
`analysis/recommendations/prereg-score-ladder-rung-2026-08-07.md` (commit a780122e,
committed BEFORE this file existed -- verify with
`git merge-base --is-ancestor a780122e <runner commit>`).

MECHANISM UNDER TEST (see the prereg for the full partition tables + filters.py line cites):
for LADDER arms, DEMOTABLE filters no longer veto -- each active demotable blocker costs its
scorer demerit (exactly 1 point each: filters.py:1758 `bear_score = 10 - len(blockers)`,
:1273 `bull_score = 11 - len(blockers)`, so adjusted score == the logged score) -- and the
arm enters when score >= its rung, PROVIDED no NON-DEMOTABLE blocker is active:

    BULL  demotable {5,7,8,10}            non-demotable {1,6,9,11,12}
    BEAR  demotable {5,7,9} + {8 iff vix<=23.0}   non-demotable {1,6,10,11} + {8 iff vix>23.0}

(bear F8 decomposes hard-vs-soft on the row's own vix because VIX_HARD_CAP_BEAR=23.0 is
embedded inside blocker 8, filters.py:1521, and the L115 declining-regime branch is disarmed,
filters.py:44). risk_gate / min_entry_premium / level-tied requirement stay absolute -- the
level-tied trigger + numeric raw level are candidate-gate requirements here, exactly as in
the production block producer.

GRAVEYARD DISTINCTION (prereg section 3): this is NOT the 2026-07-27 `score_ladder_floor`
lane (DISARMED on evidence: floor=8 -$16,642/725tr) -- that lane ignored blocker identity
(spread/window/hard-VIX ticks admitted) and was bear-only. The killed lane's numbers are
re-quoted below as reference cells, never hidden.

TWO MODES
=========
--ledger <dates>   Replay the LIVE safe-account core-decisions.jsonl rows for each date with
                   per-arm rungs applied at signal level (risky-3 rung 7, risky-1 rung 8;
                   binary walk = control). Sequential ONE-POSITION per arm, kill-switch-aware
                   (-50% SoD equity), PDT-aware (counts day-trades always; enforces the
                   3-in-5d cap only when the arm's own ledger says pdt_enforced -- live
                   risky arms currently run pdt_enforced=false, mirrored + disclosed).
                   Pricing: real 1-min OPRA via _option_bars_1min_cache.fetch_1min_cached for
                   prior days; for TODAY (same-day OPRA 403s until ~16:21) the engine's OWN
                   per-tick spy/vix track priced through the repo BS lib -- every such cell
                   is labeled EST and never blended with real-OPRA cells. The EST pricer's
                   calibration error vs the engine's real fetched mids (the day's priced
                   proposal ticks) is computed and reported.
--population       390-RTH-day lanes (2025-01-02..2026-07-27) via the ladder_fullhist_replay
                   machinery (run_backtest + real-OPRA-only walk), rung semantics BOTH sides,
                   rungs {7,8}, vs binary baseline + the killed raw-floor lanes (reference
                   cells quoted from analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json).
                   qty=3 for lane comparability (disclosed; ledger mode uses the risky arms'
                   real min_contracts=5).

Exits: backtest/lib/exit_manager_walk.walk_exit_manager (the REAL exit_manager.
plan_exit_actions core) ONLY -- never simulator_real (SIM-EXIT-SHAPE-PARITY scar).
RIBBON_RIDE exit shape, structure stop, trigger_level = the raw detection's own level.
Entry convention: NEXT option bar strictly after the admission tick, its OPEN (entry+1,
markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md).

ANALYSIS ONLY: writes only under analysis/arm-ladder/. No trading-path file touched, no
orders placed. Run (backtest venv):
    backtest/.venv/Scripts/python.exe backtest/tools/ladder_rung_replay_2026_08_07.py --ledger 2026-08-07
    backtest/.venv/Scripts/python.exe backtest/tools/ladder_rung_replay_2026_08_07.py --population
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

BACKTEST = Path(__file__).resolve().parents[1]
ROOT = BACKTEST.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(BACKTEST), str(BACKTEST / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import option_symbol  # noqa: E402
from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from crypto.lib.strike_selection import pick_strike  # noqa: E402
import fleet_executor as fx  # noqa: E402  -- PROBE_STRIKE_TIERS (ATM class, the ladder lane's table)

CORE_LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
FLEET_LEDGER = {arm: ROOT / "automation" / "state" / "fleet" / arm / "decisions.jsonl"
                for arm in ("risky-3", "risky-1")}
SPY_WEEK_FILE = BACKTEST / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
OUT_DIR = ROOT / "analysis" / "arm-ladder"
KILLED_LANE_JSON = OUT_DIR / "LADDER-FULLHIST-2026-07-27.json"

TIME_STOP_ET = dt.time(15, 40)
MIN_ENTRY_PREMIUM = 0.30           # live floor, both param files (verified this session)
VIX_HARD_CAP_BEAR = 23.0           # automation/state/params.json#vix_bear_hard_cap (live)
QTY_LEDGER = 5                     # risky arms' real min_contracts (aggressive/params.json)
QTY_POPULATION = 3                 # killed-lane/baseline comparability (disclosed)
WEEK_DATES = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
EST_DATES = {"2026-08-07"}         # same-day OPRA 403 -> engine-track BS pricing, LABEL EST

# Frozen partition (prereg section 1). Bear F8 handled dynamically on the row's vix.
DEMOTABLE_BULL = {5, 7, 8, 10}
DEMOTABLE_BEAR_STATIC = {5, 7, 9}
LEVEL_TIED_BEAR = {"level_rejection", "fhh_level_rejection", "confluence", "sequence_rejection"}
LEVEL_TIED_BULL = {"level_reclaim", "confluence", "sequence_reclaim"}

ARMS = [
    {"id": "risky-3", "rung": 7},
    {"id": "risky-1", "rung": 8},
]

# Which sides the RESCUE lane may admit (binary/control entries are never filtered).
# Default both -- the evidence runs that measured the per-side verdict used "CP"; the
# bull-only ship variant re-runs with "C" so the ship cell measures the EXACT shipped
# mechanism (a mixed lane's bear positions displace bull entries via NOT_FLAT, so per-side
# slices of a mixed walk are NOT the same number as a bull-only lane walk).
ALLOWED_RESCUE_SIDES = {"C", "P"}


def log(msg: str) -> None:
    print(f"[ladder-rung] {msg}", flush=True)


# ==================================================================== admission (the prereg rule)

def demotable_only(side: str, blockers: list, vix: Optional[float]) -> bool:
    """True iff every active blocker is DEMOTABLE for this side (prereg partition)."""
    bset = set(int(b) for b in (blockers or []))
    if side == "C":
        return bset <= DEMOTABLE_BULL
    demotable = set(DEMOTABLE_BEAR_STATIC)
    if isinstance(vix, (int, float)) and float(vix) <= VIX_HARD_CAP_BEAR:
        demotable.add(8)   # soft-VIX block -- demotable; vix>23 keeps 8 non-demotable (veto)
    return bset <= demotable


def rung_admits(side: str, score, blockers: list, triggers_raw: list, level,
                vix: Optional[float], rung: int) -> bool:
    """The complete frozen admission rule for a SCORING-refused tick."""
    if not isinstance(score, (int, float)) or score < rung:
        return False
    tied = LEVEL_TIED_BULL if side == "C" else LEVEL_TIED_BEAR
    raw = [t for t in (triggers_raw or []) if isinstance(t, str)]
    if not any(t in tied for t in raw):
        return False               # level-tied requirement -- absolute on every rung
    if not isinstance(level, (int, float)):
        return False               # no chart-stop anchor, no trade
    return demotable_only(side, blockers, vix)


# ==================================================================== ledger loading

def load_core_rows(date_iso: str) -> list[dict]:
    rows = []
    with open(CORE_LEDGER, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("ts_et", "")).startswith(date_iso) and r.get("account") == "safe":
                rows.append(r)
    rows.sort(key=lambda r: str(r.get("ts_et")))
    return rows


def arm_day_config(arm_id: str, date_iso: str) -> dict:
    """SoD equity + pdt_enforced, from the arm's OWN ledger rows that day (live truth)."""
    out = {"sod_equity": None, "pdt_enforced": False, "day_trades_true_start": 0}
    path = FLEET_LEDGER[arm_id]
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("ts_et", "")).startswith(date_iso):
                out["sod_equity"] = float(r.get("equity") or 0) or None
                out["pdt_enforced"] = bool(r.get("pdt_enforced", False))
                out["day_trades_true_start"] = int(r.get("day_trades_true") or 0)
                return out
    return out


def parse_ts(ts: str) -> dt.datetime:
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t.to_pydatetime()


def tick_events(rows: list[dict]) -> list[dict]:
    """Chronological signal events: BINARY (core ENTER verdicts) + RESCUE candidates
    (scoring-refused HOLDs; per-side score/blockers/raw-trigger/raw-level payloads)."""
    events = []
    for r in rows:
        ts = parse_ts(r["ts_et"])
        v = str(r.get("verdict") or "")
        if v in ("ENTER_BULL", "ENTER_BEAR"):
            side = "C" if v == "ENTER_BULL" else "P"
            events.append({
                "kind": "BINARY", "ts": ts, "side": side,
                "spot": r.get("spy"), "vix": r.get("vix"),
                "level": r.get("trigger_level_exact"),
                "score": r.get("bull_score") if side == "C" else r.get("bear_score"),
                "blockers": [],
                "triggers": list(r.get("triggers") or []),
            })
            continue
        if v != "HOLD" or "no setup passed scoring" not in str(r.get("reason") or ""):
            continue
        for side, sk, bk, tk, lk in (
            ("C", "bull_score", "bull_blockers", "bull_triggers_raw", "bull_reclaim_level_raw"),
            ("P", "bear_score", "bear_blockers", "bear_triggers_raw", "bear_rejection_level_raw"),
        ):
            events.append({
                "kind": "RESCUE", "ts": ts, "side": side,
                "spot": r.get("spy"), "vix": r.get("vix"),
                "level": r.get(lk), "score": r.get(sk),
                "blockers": list(r.get(bk) or []),
                "triggers": list(r.get(tk) or []),
            })
    return events


# ==================================================================== pricing tracks

class DayBars:
    """Per (date, symbol) option bars + the day's SPY 5m frame + ribbon lookup.
    Real-OPRA for prior days; EST (engine-track BS) for dates in EST_DATES."""

    def __init__(self, date_iso: str, core_rows: list[dict]):
        self.date_iso = date_iso
        self.est = date_iso in EST_DATES
        self.core_rows = core_rows
        self._opt: dict[str, Optional[pd.DataFrame]] = {}
        self._sources: dict[str, str] = {}
        self.spy_5m = self._build_spy_5m()
        self.ribbon_lookup = self._build_ribbon_lookup()

    # ---- SPY 5m + ribbon
    def _build_spy_5m(self) -> pd.DataFrame:
        d = dt.date.fromisoformat(self.date_iso)
        if SPY_WEEK_FILE.exists():
            df = pd.read_csv(SPY_WEEK_FILE)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(
                "America/New_York").dt.tz_localize(None)
            day = df[df["timestamp_et"].dt.date == d].reset_index(drop=True)
            if len(day):
                return day
        # EST fallback: aggregate the ENGINE'S OWN per-tick spy track to 5m bars (labeled EST)
        pts = [(parse_ts(r["ts_et"]), float(r["spy"])) for r in self.core_rows
               if isinstance(r.get("spy"), (int, float))]
        s = pd.DataFrame(pts, columns=["timestamp_et", "px"]).set_index("timestamp_et").sort_index()
        o = s["px"].resample("5min").ohlc().dropna()
        out = o.reset_index().rename(columns={"index": "timestamp_et"})
        out["volume"] = 0
        return out

    def _build_ribbon_lookup(self) -> pd.DataFrame:
        if SPY_WEEK_FILE.exists() and not self.est:
            df = pd.read_csv(SPY_WEEK_FILE)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(
                "America/New_York").dt.tz_localize(None)
            rth = df[(df["timestamp_et"].dt.time >= dt.time(9, 30))
                     & (df["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
            ribbon = compute_ribbon(rth["close"])
            out = rth[["timestamp_et"]].copy()
            out["stack"] = ribbon["stack"].values
            return out
        # EST: the engine's OWN logged ribbon state per tick (more faithful than recompute)
        pts = [(parse_ts(r["ts_et"]), str(r.get("ribbon") or "MIXED")) for r in self.core_rows]
        return pd.DataFrame(pts, columns=["timestamp_et", "stack"]).sort_values(
            "timestamp_et").reset_index(drop=True)

    def ribbon_tick_df_for(self, opt_df: pd.DataFrame) -> pd.DataFrame:
        left = opt_df[["timestamp_et"]].copy()
        merged = pd.merge_asof(left, self.ribbon_lookup.sort_values("timestamp_et"),
                               on="timestamp_et", direction="backward")
        merged["stack"] = merged["stack"].fillna("MIXED")
        assert len(merged) == len(opt_df), "ribbon merge_asof row count drifted"
        return merged

    # ---- option bars
    def opt_bars(self, symbol: str) -> tuple[Optional[pd.DataFrame], str]:
        if symbol in self._opt:
            return self._opt[symbol], self._sources[symbol]
        if self.est:
            df, src = self._est_bars(symbol), "EST_engine_track_bs"
        else:
            df, src = self._fetch_1min_normalized(symbol)
        self._opt[symbol] = df
        self._sources[symbol] = src
        return df, src

    def _fetch_1min_normalized(self, symbol: str) -> tuple[Optional[pd.DataFrame], str]:
        """fetch_1min_cached, tolerant of the `timestamp` (not `timestamp_et`) column name a
        DIFFERENT producer wrote into some backtest/data/highres cache files (found 4 such
        files for 2026-08-05 during this build). Normalizes locally -- the shared helper is
        NOT edited (other live lanes read it this session)."""
        cache_path = Path(r"C:\Users\jackw\Desktop\42") / "backtest" / "data" / "highres" / \
            f"{symbol}_1m_{self.date_iso}.csv"
        if cache_path.exists():
            df = pd.read_csv(cache_path)
            if "timestamp_et" not in df.columns and "timestamp" in df.columns:
                df = df.rename(columns={"timestamp": "timestamp_et"})
            if "timestamp_et" not in df.columns or df.empty:
                return None, "cache_malformed"
            ts = pd.to_datetime(df["timestamp_et"])
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
            df["timestamp_et"] = ts
            return df, "cache_hit_normalized"
        return fetch_1min_cached(symbol, self.date_iso)

    def _est_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        """EST premium series from the engine's own per-tick spy/vix observations, priced
        via the repo BS lib. One bar per core tick (~1/min), O=H=L=C=BS price. LABEL EST."""
        strike = int(symbol[-8:-3])  # OCC: root+yymmdd+C/P+8-digit strike*1000
        side = symbol[-9]
        rows = []
        for r in self.core_rows:
            spy, vix = r.get("spy"), r.get("vix")
            if not isinstance(spy, (int, float)) or not isinstance(vix, (int, float)):
                continue
            ts = parse_ts(r["ts_et"])
            iv = vix_to_iv(float(vix))
            tte = time_to_expiry_years(ts)
            px, _ = black_scholes(float(spy), strike, iv, tte, is_call=(side == "C"))
            px = max(round(float(px), 4), 0.01)
            rows.append({"timestamp_et": ts, "open": px, "high": px, "low": px,
                         "close": px, "volume": 0})
        if not rows:
            return None
        return pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)

    def calibration(self, fleet_rows: list[dict]) -> dict:
        """EST-vs-real error on the day's engine-priced proposal ticks (real fetched mids)."""
        errs = []
        for r in fleet_rows:
            prem, strike, side_setup = r.get("premium"), r.get("strike"), str(r.get("side") or "")
            if not isinstance(prem, (int, float)) or not isinstance(strike, (int, float)):
                continue
            side = side_setup if side_setup in ("C", "P") else None
            if side is None:
                continue
            ts = parse_ts(r["ts_et"])
            sym = option_symbol(dt.date.fromisoformat(self.date_iso), int(strike), side)
            df, _ = self.opt_bars(sym)
            if df is None or df.empty:
                continue
            sub = df[df["timestamp_et"] <= ts]
            if sub.empty:
                continue
            est = float(sub.iloc[-1]["close"])
            errs.append({"ts": r["ts_et"], "symbol": sym, "real_mid": float(prem),
                         "est": est, "err": round(est - float(prem), 4)})
        if not errs:
            return {"n": 0}
        e = [x["err"] for x in errs]
        return {"n": len(errs), "mean_err": round(sum(e) / len(e), 4),
                "max_abs_err": round(max(abs(v) for v in e), 4), "rows": errs}


def entry_bar_after(df: pd.DataFrame, ts: dt.datetime):
    sub = df[df["timestamp_et"] > ts]
    return None if sub.empty else sub.iloc[0]


# ==================================================================== the walk

def walk_day(arm: dict, events: list[dict], bars: DayBars, cfg: dict,
             include_rescues: bool, qty: int) -> dict:
    """Sequential one-position walk. include_rescues=False -> BINARY control walk;
    True -> LADDER walk (binary entries + rung-admitted rescues)."""
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    trades, skipped = [], []
    flat_until: Optional[dt.datetime] = None
    day_pnl = 0.0
    day_trades_used = 0
    sod = cfg.get("sod_equity") or 5000.0
    kill_level = -0.5 * sod
    trade_date = dt.date.fromisoformat(bars.date_iso)

    for ev in events:
        admit = ev["kind"] == "BINARY" or (
            include_rescues and ev["kind"] == "RESCUE"
            and ev["side"] in ALLOWED_RESCUE_SIDES
            and rung_admits(ev["side"], ev["score"], ev["blockers"], ev["triggers"],
                            ev["level"], ev["vix"], arm["rung"]))
        if not admit:
            continue
        lane = "binary" if ev["kind"] == "BINARY" else "rescue"
        if flat_until is not None and ev["ts"] <= flat_until:
            continue                                    # NOT_FLAT (Rule 4)
        if day_pnl <= kill_level:
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "why": "KILL_SWITCH"})
            continue                                    # Rule 5 -- absolute
        if cfg.get("pdt_enforced") and day_trades_used >= 3:
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "why": "PDT_CAP"})
            continue                                    # Rule 7 -- absolute when enforced
        if not isinstance(ev.get("spot"), (int, float)):
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "why": "NO_SPOT"})
            continue
        strike = pick_strike(float(ev["spot"]), sod, ev["side"], fx.PROBE_STRIKE_TIERS)
        sym = option_symbol(trade_date, int(strike), ev["side"])
        opt_df, src = bars.opt_bars(sym)
        if opt_df is None or opt_df.empty:
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "why": f"NO_BARS:{src}",
                            "symbol": sym})
            continue
        eb = entry_bar_after(opt_df, ev["ts"])
        if eb is None:
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "why": "NO_NEXT_BAR",
                            "symbol": sym})
            continue
        entry_premium = float(eb["open"])
        if entry_premium < MIN_ENTRY_PREMIUM:
            skipped.append({"ts": ev["ts"].isoformat(), "lane": lane, "symbol": sym,
                            "why": f"MIN_PREMIUM_FLOOR:{entry_premium:.2f}"})
            continue                                    # absolute floor, untouched
        entry_time = pd.Timestamp(eb["timestamp_et"]).to_pydatetime()
        walk = walk_exit_manager(
            symbol=sym, side=ev["side"], entry_time_et=entry_time,
            entry_premium=entry_premium, qty=qty, exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(ev["level"]) if isinstance(ev["level"], (int, float)) else None),
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=bars.ribbon_tick_df_for(opt_df),
            five_min_spy_df=bars.spy_5m,
        )
        exit_ts = walk.exit_time_et or entry_time
        flat_until = exit_ts
        day_pnl += float(walk.dollar_pnl or 0.0)
        day_trades_used += 1
        trades.append({
            "lane": lane, "side": ev["side"], "signal_ts": ev["ts"].isoformat(),
            "entry_time": entry_time.isoformat(), "symbol": sym, "qty": qty,
            "entry_premium": round(entry_premium, 4),
            "score": ev["score"], "blockers": ev["blockers"], "triggers": ev["triggers"],
            "dollar_pnl": round(float(walk.dollar_pnl or 0.0), 2),
            "exit_reason": walk.exit_reason,
            "exit_time": exit_ts.isoformat() if exit_ts else None,
            "pricing": ("EST" if bars.est else "REAL_OPRA_1MIN"),
        })
    return {"trades": trades, "skipped": skipped, "day_pnl": round(day_pnl, 2),
            "day_trades_used": day_trades_used,
            "pdt_enforced": bool(cfg.get("pdt_enforced")), "sod_equity": sod}


def run_ledger_mode(dates: list[str]) -> dict:
    out = {"mode": "ledger", "qty": QTY_LEDGER, "dates": {}, "per_arm_week": {}}
    for date_iso in dates:
        core = load_core_rows(date_iso)
        if not core:
            out["dates"][date_iso] = {"error": "no safe-account core rows"}
            continue
        events = tick_events(core)
        bars = DayBars(date_iso, core)
        day_out = {"est": bars.est, "n_core_rows": len(core),
                   "n_binary_events": sum(1 for e in events if e["kind"] == "BINARY"),
                   "arms": {}}
        for arm in ARMS:
            cfg = arm_day_config(arm["id"], date_iso)
            binary = walk_day(arm, events, bars, cfg, include_rescues=False, qty=QTY_LEDGER)
            ladder = walk_day(arm, events, bars, cfg, include_rescues=True, qty=QTY_LEDGER)
            added = [t for t in ladder["trades"] if t["lane"] == "rescue"]
            day_out["arms"][arm["id"]] = {
                "rung": arm["rung"], "sod_equity": cfg.get("sod_equity"),
                "pdt_enforced": cfg.get("pdt_enforced"),
                "binary": binary, "ladder": ladder,
                "n_added": len(added),
                "added_pnl": round(sum(t["dollar_pnl"] for t in added), 2),
                "delta_pnl": round(ladder["day_pnl"] - binary["day_pnl"], 2),
            }
        if bars.est:
            fr = []
            for aid in FLEET_LEDGER:
                with open(FLEET_LEDGER[aid], encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            r = json.loads(line)
                            if str(r.get("ts_et", "")).startswith(date_iso):
                                fr.append(r)
            day_out["est_calibration"] = bars.calibration(fr)
        out["dates"][date_iso] = day_out
    for arm in ARMS:
        tot_added, tot_delta, n_added = 0.0, 0.0, 0
        for date_iso, d in out["dates"].items():
            a = (d.get("arms") or {}).get(arm["id"])
            if a:
                tot_added += a["added_pnl"]
                tot_delta += a["delta_pnl"]
                n_added += a["n_added"]
        out["per_arm_week"][arm["id"]] = {"rung": arm["rung"], "n_added": n_added,
                                          "added_pnl": round(tot_added, 2),
                                          "delta_pnl": round(tot_delta, 2)}
    return out


# ==================================================================== population mode

def run_population_mode() -> dict:
    import ladder_fullhist_replay as lfr
    import lib.orchestrator as orch_mod
    import engine_fullhist_replay as efr
    from lib.orchestrator import run_backtest
    from lib.option_pricing_real import load_contract_bars, bar_at_or_after

    log("population: loading extended SPY/VIX (2025-01-02..2026-07-27)")
    spy_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_raw)

    bull_by_idx: dict[int, dict] = {}
    orig = orch_mod.evaluate_bullish_setup

    def _capture(ctx, **kw):
        res = orig(ctx, **kw)
        bull_by_idx[ctx.bar_idx] = {
            "passed": bool(res.passed), "score": int(res.bull_score),
            "blockers": list(res.blockers), "triggers": list(res.triggers_fired),
            "level": res.reclaim_level,
        }
        return res

    log("population: run_backtest(**SAFE_BASE_LIVE) with FULL bull capture")
    t0 = time.time()
    orch_mod.evaluate_bullish_setup = _capture
    try:
        r = run_backtest(spy_raw, vix_df, start_date=lfr.FULL_START, end_date=lfr.FULL_END,
                         **efr.SAFE_BASE_LIVE)
    finally:
        orch_mod.evaluate_bullish_setup = orig
    log(f"  done in {time.time()-t0:.1f}s -- {len(r.trades)} baseline entries, "
        f"{len(r.decisions)} decision rows")

    # Candidates under RUNG semantics (both sides), from the scoring layer's own rows.
    cands = []
    for row in r.decisions:
        if "action" in row or row.get("passed") is not False:
            continue
        bidx = row.get("bar_idx")
        bull = bull_by_idx.get(bidx) or {}
        if bull.get("passed"):
            continue                                     # neither side passed scoring
        vix = float(row.get("vix") or 0.0)
        # bear side (base row carries bear's own raw fields)
        cands.append({"side": "P", "bar_idx": bidx, "score": row.get("bear_score"),
                      "blockers": list(row.get("blockers") or []),
                      "triggers": list(row.get("triggers_fired") or []),
                      "level": row.get("rejection_level"), "vix": vix,
                      "spot": float(row.get("spy_close") or 0.0)})
        cands.append({"side": "C", "bar_idx": bidx, "score": bull.get("score"),
                      "blockers": list(bull.get("blockers") or []),
                      "triggers": list(bull.get("triggers") or []),
                      "level": bull.get("level"), "vix": vix,
                      "spot": float(row.get("spy_close") or 0.0)})

    ribbon_lookup = efr.build_ribbon_lookup(spy_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    all_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_days = (lfr.FULL_END - lfr.FULL_START).days
    held_out_cutoff = lfr.FULL_START + dt.timedelta(days=round(window_days * 0.75))

    lanes = {}
    for rung in (7, 8):
        admitted = sorted(
            (c for c in cands if c["side"] in ALLOWED_RESCUE_SIDES
             and rung_admits(c["side"], c["score"], c["blockers"],
                             c["triggers"], c["level"], c["vix"], rung)),
            key=lambda c: c["bar_idx"])
        trades, excluded = [], []
        flat_until = None
        for c in admitted:
            trig_row = spy_rth.iloc[c["bar_idx"]]
            trig_ts = efr.naive_dt(trig_row["timestamp_et"])
            if flat_until is not None and trig_ts <= flat_until:
                continue
            trade_date = trig_row["timestamp_et"].date()
            strike = pick_strike(c["spot"], lfr.REF_EQUITY_FOR_STRIKE, c["side"],
                                 fx.PROBE_STRIKE_TIERS)
            nb = lfr.next_bar_same_day(spy_rth, c["bar_idx"])
            if nb is None:
                excluded.append({"why": "no_next_bar", "date": str(trade_date)})
                continue
            sym = option_symbol(trade_date, int(strike), c["side"])
            opt_df = load_contract_bars(sym)
            if opt_df is None:
                excluded.append({"why": "no_opra_cache", "date": str(trade_date),
                                 "symbol": sym, "side": c["side"]})
                continue
            next_ts = spy_rth.iloc[nb]["timestamp_et"]
            ob = bar_at_or_after(opt_df, next_ts)
            if ob is None:
                excluded.append({"why": "no_bar_at_or_after", "date": str(trade_date),
                                 "symbol": sym, "side": c["side"]})
                continue
            entry_premium = float(ob.open)
            if entry_premium < MIN_ENTRY_PREMIUM:
                excluded.append({"why": f"min_premium_floor:{entry_premium:.2f}",
                                 "date": str(trade_date), "symbol": sym})
                continue
            day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == trade_date].reset_index(drop=True)
            walk = walk_exit_manager(
                symbol=sym, side=c["side"], entry_time_et=efr.naive_dt(ob.timestamp_et),
                entry_premium=entry_premium, qty=QTY_POPULATION, exit_shape=exit_shape,
                structure_stop_enabled=True,
                trigger_level=(float(c["level"]) if isinstance(c["level"], (int, float)) else None),
                strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
                opt_df=opt_df, ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
                five_min_spy_df=day_spy,
            )
            exit_ts = walk.exit_time_et or efr.naive_dt(ob.timestamp_et)
            flat_until = exit_ts
            trades.append({"date": str(trade_date), "side": c["side"],
                           "trigger_time_et": trig_ts.isoformat(), "score": c["score"],
                           "blockers": c["blockers"], "triggers": c["triggers"],
                           "symbol": sym, "qty": QTY_POPULATION,
                           "entry_premium": round(entry_premium, 4),
                           "dollar_pnl": walk.dollar_pnl, "exit_reason": walk.exit_reason})
        stats = lfr.lane_stats(trades, all_dates, held_out_cutoff)
        stats["n_admitted_signals"] = len(admitted)
        stats["n_excluded"] = len(excluded)
        stats["n_excluded_no_opra"] = sum(1 for e in excluded if e["why"] == "no_opra_cache")
        by_side = {}
        for s in ("P", "C"):
            st = [t for t in trades if t["side"] == s]
            by_side[s] = {"n": len(st), "pnl": round(sum(t["dollar_pnl"] for t in st), 2)}
        stats["by_side"] = by_side
        lanes[rung] = {"stats": stats, "trades": trades, "excluded_sample": excluded[:50]}
        log(f"  rung={rung}: admitted={len(admitted)} entered={stats['n_trades']} "
            f"pnl=${stats['total_pnl']:+.2f} WR={stats['win_rate']} bySide={by_side}")

    reference = {}
    if KILLED_LANE_JSON.exists():
        kj = json.loads(KILLED_LANE_JSON.read_text(encoding="utf-8"))
        reference["baseline_binary"] = kj["baseline_binary_engine"]["stats"]
        reference["killed_floor_lanes"] = {f: kj["lanes"][f]["stats"] for f in ("7", "8", "9")}
    return {"mode": "population", "qty": QTY_POPULATION,
            "window": {"start": str(lfr.FULL_START), "end": str(lfr.FULL_END)},
            "lanes": {str(k): v for k, v in lanes.items()}, "reference": reference}


# ==================================================================== main

def main() -> int:
    ap = argparse.ArgumentParser(description="SCORE-LADDER-RUNG replay (see module docstring)")
    ap.add_argument("--ledger", nargs="*", default=None,
                    help="dates (YYYY-MM-DD) for ledger mode; empty flag = the week")
    ap.add_argument("--population", action="store_true")
    ap.add_argument("--sides", default="CP", choices=["CP", "C", "P"],
                    help="which sides the RESCUE lane may admit (ship variant: C)")
    ap.add_argument("--no-est", action="store_true",
                    help="disable EST pricing entirely (use after ~16:21 ET when the "
                         "same-day OPRA 403 lifts, to re-price today's cells on real bars)")
    ap.add_argument("--out-tag", default="")
    args = ap.parse_args()

    global ALLOWED_RESCUE_SIDES
    ALLOWED_RESCUE_SIDES = set(args.sides)
    if args.no_est:
        EST_DATES.clear()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {"generated_at": dt.datetime.now().isoformat(),
               "prereg": "analysis/recommendations/prereg-score-ladder-rung-2026-08-07.md (a780122e)"}
    if args.ledger is not None:
        dates = args.ledger or WEEK_DATES
        results["ledger"] = run_ledger_mode(dates)
    if args.population:
        results["population"] = run_population_mode()

    tag = args.out_tag or ("ledger" if args.ledger is not None else "population")
    out_path = OUT_DIR / f"LADDER-RUNG-2026-08-07-{tag}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log(f"wrote {out_path}")
    if args.ledger is not None:
        for aid, s in results["ledger"]["per_arm_week"].items():
            log(f"WEEK {aid} rung={s['rung']}: n_added={s['n_added']} "
                f"added_pnl=${s['added_pnl']:+.2f} delta_pnl=${s['delta_pnl']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
