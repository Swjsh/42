"""money_retest_entry_variant.py -- H10 RETEST ENTRY hypothesis replay.

Defines a retest variant of RIDE_THE_RIBBON (BULLISH_RECLAIM_RIDE_THE_RIBBON /
BEARISH_REJECTION_RIDE_THE_RIBBON): instead of entering on the breakout tick, wait for the
first pullback that touches the trigger zone (trigger_level +/- zone_width, $0.30 default --
no historical key-levels.json snapshot exists for this window, see report caveats) and then
prints a 1-minute CLOSE back in the trade direction, within 30 minutes of the original trigger
tick. Cancel (no trade) if a bar closes through the far side of the zone first.

Replays every actual engine-filled RIDE_THE_RIBBON entry since 2026-08-06 (safe-2, bold-2,
safe-3, risky-1, risky-3 -- the 5 active real-fills arms per CLAUDE.md) through this variant,
using ONLY cached bars (backtest/data/spy_5m_2026-05-19_2026-09-02.csv,
backtest/data/spy_sip_cache/spy_1m_<date>.json, backtest/data/options/<symbol>.csv +
backtest/data/highres/<symbol>_1m_<date>.csv fallback). Both the ACTUAL breakout entry and the
RETEST variant entry (when one occurs) are walked through the SAME production exit code
(backtest/lib/exit_manager_walk.walk_exit_manager -> automation/state/fleet/exit_manager.py
plan_exit_actions) with the SAME exit shape (fleet_strategies.by_name("ribbon_ride")), so the
comparison isolates the ENTRY-TIMING change, not an exit-model difference. This is a
SIMULATED-vs-SIMULATED comparison, not simulated-vs-real-fill -- see report for why (multiple
same-day re-entries on 22/82 (arm,symbol) groups make real sell-fill attribution to a specific
buy order ambiguous; exit_manager_walk gives a consistent apples-to-apples engine on both
sides instead).

FIDELITY CAVEAT (read before trusting any dollar figure): per
analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md, walk_exit_manager's
magnitude fidelity vs real fills PASSES only for safe-2 (aggregate_ratio 0.96). bold-2/risky-1/
safe-3 individually FAIL the magnitude criterion (ratios 1.7-6.4x, one arm sign-flipped) --
dollars for those arms are SIGN-ONLY (direction of P&L), not magnitude-trustworthy. risky-3 was
not covered by that anchor at all (not a go-live-gate ACTIVE_ARMS member) -- treat as SIGN-ONLY
too, unverified even for sign. Read-only against automation/state/** and journal/** throughout.

Run: backtest/.venv/Scripts/python.exe backtest/tools/money_retest_entry_variant.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
RAW_ENTRIES_PATH = OUT_DIR / "retest-entry-variant-raw-entries.json"
SPY_5M_PATH = BACKTEST / "data" / "spy_5m_2026-05-19_2026-09-02.csv"
SIP_1M_DIR = BACKTEST / "data" / "spy_sip_cache"
OPTIONS_5M_DIR = BACKTEST / "data" / "options"
HIGHRES_DIR = BACKTEST / "data" / "highres"
CORE_DECISIONS_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"

import os  # noqa: E402
ZONE_WIDTH_DEFAULT = float(os.environ.get("RETEST_ZONE_WIDTH", "0.30"))
RETEST_WINDOW_MIN = 30
TODAY_CUTOFF = "2026-09-03"  # excluded: no cached SPY/option bars for the live session
BIG_WINNER_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}

RIBBON_RIDE = fleet_strategies.by_name("ribbon_ride")
EXIT_SHAPE = RIBBON_RIDE.exit.to_dict()
TIME_STOP_ET = dt.time(15, 40)  # params.json + aggressive/params.json, both accounts, verified


def log(msg: str) -> None:
    print(f"[retest-entry] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# SHARED CONTEXT -- loaded once
# ---------------------------------------------------------------------------------------------
def load_spy_5m_and_ribbon():
    spy = pd.read_csv(SPY_5M_PATH)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if spy["timestamp_et"].dt.tz is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    rth = (spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    spy_rth = spy.loc[rth].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])  # causal EMAs -- no look-ahead
    return spy_rth, ribbon


def day_slice(spy_rth: pd.DataFrame, ribbon: pd.DataFrame, date_str: str):
    mask = spy_rth["timestamp_et"].dt.strftime("%Y-%m-%d") == date_str
    idx = spy_rth.index[mask]
    return ribbon.loc[idx].reset_index(drop=True), len(idx)


_1M_CACHE: dict[str, pd.DataFrame] = {}


def load_spy_1m(date_str: str) -> pd.DataFrame | None:
    if date_str in _1M_CACHE:
        return _1M_CACHE[date_str]
    path = SIP_1M_DIR / f"spy_1m_{date_str}.json"
    if not path.exists():
        _1M_CACHE[date_str] = None
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    bars = raw.get("bars", [])
    df = pd.DataFrame(bars)
    df = df.rename(columns={"t": "timestamp_et", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    rth = (df["timestamp_et"].dt.time >= dt.time(9, 30)) & (df["timestamp_et"].dt.time < dt.time(16, 0))
    df = df.loc[rth].sort_values("timestamp_et").reset_index(drop=True)
    _1M_CACHE[date_str] = df
    return df


def load_core_tick_vix():
    """core_tick_id -> vix, tick-level (not account-specific), for regime splits on fleet rows
    that don't carry vix directly."""
    out = {}
    if not CORE_DECISIONS_PATH.exists():
        return out
    with CORE_DECISIONS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ctid = d.get("core_tick_id")
            if ctid and ctid not in out and d.get("vix") is not None:
                out[ctid] = d["vix"]
    return out


_OPT_5M_CACHE: dict[str, pd.DataFrame] = {}
_OPT_1M_CACHE: dict[str, pd.DataFrame] = {}


def load_opt_bars(symbol: str, date_str: str):
    """Returns (df, resolution) -- 5-min from CACHE_DIR preferred, 1-min highres fallback."""
    if symbol in _OPT_5M_CACHE:
        df = _OPT_5M_CACHE[symbol]
    else:
        df = load_contract_bars(symbol, frame="wall-v1")
        _OPT_5M_CACHE[symbol] = df
    if df is not None:
        return df, "5min"
    key = f"{symbol}_{date_str}"
    if key in _OPT_1M_CACHE:
        df1 = _OPT_1M_CACHE[key]
    else:
        path = HIGHRES_DIR / f"{symbol}_1m_{date_str}.csv"
        if path.exists():
            df1 = pd.read_csv(path)
            df1["timestamp_et"] = pd.to_datetime(df1["timestamp_et"])
        else:
            df1 = None
        _OPT_1M_CACHE[key] = df1
    return df1, "1min"


def bar_open_at_or_after(df: pd.DataFrame, when_et: dt.datetime) -> float | None:
    """Local minimal replacement for option_pricing_real.bar_at_or_after: that helper requires
    vwap/trade_count columns the 1-min highres fallback cache doesn't carry. Returns the OPEN
    of the first bar with timestamp_et >= when_et -- same point-sample convention
    exit_manager_walk itself uses for entry-adjacent fills (bar open as the NBBO proxy)."""
    matches = df[df["timestamp_et"] >= when_et]
    if matches.empty:
        return None
    return float(matches.iloc[0]["open"])


# ---------------------------------------------------------------------------------------------
# RETEST DECISION -- 1-minute SPY bars, strictly after t0, within RETEST_WINDOW_MIN
# ---------------------------------------------------------------------------------------------
def retest_decision(spy_1m: pd.DataFrame, t0: dt.datetime, trigger_level: float, side: str,
                     zone_width: float = ZONE_WIDTH_DEFAULT):
    zone_low = trigger_level - zone_width
    zone_high = trigger_level + zone_width
    window_end = t0 + dt.timedelta(minutes=RETEST_WINDOW_MIN)
    bars = spy_1m.loc[(spy_1m["timestamp_et"] > t0) & (spy_1m["timestamp_et"] <= window_end)]
    seen_touch = False
    for _, b in bars.iterrows():
        c, lo, hi = float(b["close"]), float(b["low"]), float(b["high"])
        if side == "C":
            if c < zone_low:
                return {"outcome": "invalidated", "ts": b["timestamp_et"].to_pydatetime(),
                        "zone_low": zone_low, "zone_high": zone_high}
            if not seen_touch and lo <= zone_high:
                seen_touch = True
            if seen_touch and c >= trigger_level:
                return {"outcome": "confirmed", "ts": b["timestamp_et"].to_pydatetime(),
                        "confirm_close": c, "zone_low": zone_low, "zone_high": zone_high}
        else:  # P -- bearish rejection
            if c > zone_high:
                return {"outcome": "invalidated", "ts": b["timestamp_et"].to_pydatetime(),
                        "zone_low": zone_low, "zone_high": zone_high}
            if not seen_touch and hi >= zone_low:
                seen_touch = True
            if seen_touch and c <= trigger_level:
                return {"outcome": "confirmed", "ts": b["timestamp_et"].to_pydatetime(),
                        "confirm_close": c, "zone_low": zone_low, "zone_high": zone_high}
    if bars.empty:
        return {"outcome": "no_bars", "zone_low": zone_low, "zone_high": zone_high}
    return {"outcome": "timeout", "zone_low": zone_low, "zone_high": zone_high,
            "seen_touch": seen_touch}


# ---------------------------------------------------------------------------------------------
# WALK ONE ENTRY through exit_manager_walk
# ---------------------------------------------------------------------------------------------
def walk_one(symbol: str, side: str, entry_time_et: dt.datetime, entry_premium: float, qty: int,
             trigger_level: float, setup: str, opt_df: pd.DataFrame, ribbon_tick_df,
             spy_5m_rth: pd.DataFrame, opt_res: str):
    return walk_exit_manager(
        symbol=symbol, side=side, entry_time_et=entry_time_et, entry_premium=entry_premium,
        qty=int(qty), exit_shape=EXIT_SHAPE, structure_stop_enabled=True,
        trigger_level=trigger_level, strategy=setup, time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_5m_rth,
        opt_df_resolution=opt_res, allow_5min=True,
    )


def _parse_naive(ts_str: str) -> dt.datetime:
    """wall-v1 convention: keep the stored local ET digits, drop any tz offset (core rows are
    already naive; fleet rows carry an explicit -04:00/-05:00 offset that IS local ET, per
    et_frame.py's documented wall-v1 semantics -- see this module's docstring)."""
    ts = dt.datetime.fromisoformat(ts_str)
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def main() -> int:
    entries = json.loads(RAW_ENTRIES_PATH.read_text(encoding="utf-8"))
    entries = [e for e in entries if e["date"] < TODAY_CUTOFF]
    log(f"{len(entries)} candidate entries (excludes {TODAY_CUTOFF}, no cached bars for the live session)")

    n_no_trigger = sum(1 for e in entries if e.get("trigger_level") is None)
    entries = [e for e in entries if e.get("trigger_level") is not None]
    log(f"excluded {n_no_trigger} entries with no trigger_level (can't define a retest zone); {len(entries)} remain")

    log("Loading aggregate SPY 5m + ribbon (2026-05-19..2026-09-02, RTH, causal EMAs)")
    spy_5m_rth, ribbon_5m = load_spy_5m_and_ribbon()
    vix_by_tick = load_core_tick_vix()
    for e in entries:
        e["vix"] = vix_by_tick.get(e.get("core_tick_id"))

    results = []
    for i, e in enumerate(entries):
        symbol, side, date_str = e["symbol"], e["side"], e["date"]
        qty = e["qty"]
        trigger_level = float(e["trigger_level"])
        entry_premium = float(e["entry_premium"])
        t0 = _parse_naive(e["ts_et"])

        opt_df, opt_res = load_opt_bars(symbol, date_str)
        if opt_df is None:
            results.append({**e, "status": "skip_no_option_bars"})
            continue

        if opt_res == "5min":
            ribbon_tick_df, n_day = day_slice(spy_5m_rth, ribbon_5m, date_str)
        else:
            spy_1m_day = load_spy_1m(date_str)
            if spy_1m_day is None:
                results.append({**e, "status": "skip_no_spy_1m_for_ribbon"})
                continue
            day5, _ = day_slice(spy_5m_rth, ribbon_5m, date_str)
            spy_5m_day = spy_5m_rth.loc[spy_5m_rth["timestamp_et"].dt.strftime("%Y-%m-%d") == date_str].reset_index(drop=True)
            five = spy_5m_day[["timestamp_et"]].copy()
            five["five_idx"] = five.index
            merged = pd.merge_asof(spy_1m_day[["timestamp_et"]].sort_values("timestamp_et"),
                                    five.sort_values("timestamp_et"), on="timestamp_et", direction="backward")
            ribbon_tick_df = day5.loc[merged["five_idx"].values].reset_index(drop=True)

        # ---- ACTUAL breakout entry, walked through the same exit engine ----
        actual = walk_one(symbol, side, t0, entry_premium, qty, trigger_level, e["setup"],
                           opt_df, ribbon_tick_df, spy_5m_rth, opt_res)

        # ---- RETEST variant decision ----
        spy_1m_day = load_spy_1m(date_str)
        if spy_1m_day is None or spy_1m_day.empty:
            decision = {"outcome": "no_1m_spy_data"}
        else:
            decision = retest_decision(spy_1m_day, t0, trigger_level, side)

        retest_walk = None
        retest_entry_time = None
        retest_entry_premium = None
        if decision["outcome"] == "confirmed":
            confirm_ts = decision["ts"]
            # Engine acts on the NEXT tick after the confirming bar closes -- mirrors
            # exit_manager_walk's own "strictly after" tick-managed convention.
            retest_entry_time = confirm_ts + dt.timedelta(minutes=1)
            retest_open = bar_open_at_or_after(opt_df, retest_entry_time)
            if retest_open is None:
                decision["outcome"] = "confirmed_no_option_data"
            else:
                retest_entry_premium = retest_open
                retest_walk = walk_one(symbol, side, retest_entry_time, retest_entry_premium, qty,
                                        trigger_level, e["setup"], opt_df, ribbon_tick_df,
                                        spy_5m_rth, opt_res)

        core_tick_id = e.get("order_id")  # not used for vix; keep field name local
        row = {
            **{k: v for k, v in e.items() if k != "order_id"},
            "opt_resolution": opt_res,
            "actual_walk_pnl": actual.dollar_pnl,
            "actual_walk_exit_reason": actual.exit_reason,
            "actual_walk_hold_min": actual.hold_minutes,
            "retest_outcome": decision["outcome"],
            "retest_entry_time": retest_entry_time.isoformat() if retest_entry_time else None,
            "retest_entry_premium": retest_entry_premium,
            "retest_walk_pnl": retest_walk.dollar_pnl if retest_walk else 0.0,
            "retest_walk_exit_reason": retest_walk.exit_reason if retest_walk else None,
            "retest_walk_hold_min": retest_walk.hold_minutes if retest_walk else None,
            "vix": e.get("vix"),
            "big_winner_day": date_str in BIG_WINNER_DAYS,
        }
        results.append(row)
        if (i + 1) % 20 == 0:
            log(f"  ...{i+1}/{len(entries)}")

    suffix = "" if ZONE_WIDTH_DEFAULT == 0.30 else f"-zw{ZONE_WIDTH_DEFAULT:.2f}"
    out_path = OUT_DIR / f"retest-entry-variant-walked{suffix}.json"
    out_path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    log(f"wrote {out_path} ({len(results)} rows)")

    ok = [r for r in results if "status" not in r]
    skipped = [r for r in results if "status" in r]
    log(f"walked OK: {len(ok)}, skipped: {len(skipped)}")
    for s in skipped:
        log(f"  SKIP {s['arm']} {s['date']} {s['symbol']} -- {s['status']}")

    n_confirmed = sum(1 for r in ok if r["retest_outcome"] == "confirmed")
    n_invalid = sum(1 for r in ok if r["retest_outcome"] == "invalidated")
    n_timeout = sum(1 for r in ok if r["retest_outcome"] == "timeout")
    n_other = len(ok) - n_confirmed - n_invalid - n_timeout
    log(f"retest outcomes: confirmed={n_confirmed} invalidated={n_invalid} timeout={n_timeout} other={n_other}")

    actual_total = sum(r["actual_walk_pnl"] for r in ok)
    retest_total = sum(r["retest_walk_pnl"] for r in ok)
    log(f"ACTUAL (walked) total P&L: ${actual_total:,.2f}")
    log(f"RETEST (walked) total P&L: ${retest_total:,.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
