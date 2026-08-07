"""friday_replay_2026_08_07.py -- LANE 3: replay Friday 2026-08-07 end-to-end.

READ-ONLY on every trading-path file (market-hours run). Writes ONLY:
  - fetched bar CSVs -> scratchpad dir (env FRIDAY_REPLAY_SCRATCH or ./_friday_replay_scratch)
  - raw results JSON -> analysis/deep-research/_friday_replay_raw_2026_08_07.json

WHAT IT DOES
  phase=fetch     Pull the live engine's OWN sight feed (Alpaca IEX 5m, the exact URL shape
                  heartbeat_core._fetch_spy_5m uses) + IEX 1m today + SIP 5m today (f10
                  provenance cross-check). Same-day OPRA is 403-walled until ~16:21 ET, so
                  ALL counterfactual option pricing here is EST (BS calibrated on today's
                  real morning fills) -- disclosed per cell. Evening re-price on real OPRA
                  is a staged addendum, not this run.
  phase=fidelity  Re-decide every 5m trigger bar 09:30->latest through the REAL live path
                  (hc._build_payload -> hc._engine_verdict -> engine_cli subprocess; nothing
                  re-implemented) with live-recorded VIX + levels_active INJECTED from
                  core-decisions.jsonl (the exact values the live engine consumed). Diff
                  verdict/scores/blockers/triggers per account vs the live ledger.
  phase=variants  Same path, bull_kwargs.disable_filters injected IN-MEMORY into the payload
                  ([10] / [7] / [7,10]) -- filters.py untouched. Sequential one-position walk
                  per variant via lib.exit_manager_walk.walk_exit_manager (the REAL
                  exit_manager.plan_exit_actions core -- NEVER simulator_real, 07-09 scar),
                  EST premium track, safe-core shape (REGISTRY ribbon_ride, ATM, qty 3).

SCOPE: core lane (safe/bold) ONLY. Fleet arms (safe-3/risky-1/risky-3) carry standing
anchor-fidelity REDs (test_anchor_pass_rate, STATUS.md Known broken) and are NOT replayed
here; fleet conclusions are scoped out by design.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import pandas as pd  # noqa: E402

import heartbeat_core as hc  # noqa: E402  -- the REAL live decision path
import engine_step as es  # noqa: E402  -- dojo helpers (levels-as-of, vix MA, tz)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402

ET = ZoneInfo("America/New_York")
DAY = "2026-08-07"
DAY_D = dt.date(2026, 8, 7)
SCRATCH = Path(os.environ.get("FRIDAY_REPLAY_SCRATCH", str(ROOT / "backtest" / "tools" / "_friday_replay_scratch")))
OUT_JSON = ROOT / "analysis" / "deep-research" / "_friday_replay_raw_2026_08_07.json"
LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"

IEX5_CSV = SCRATCH / "spy_5m_iex_livetwin.csv"
IEX1_CSV = SCRATCH / "spy_1m_iex_today.csv"
SIP5_CSV = SCRATCH / "spy_5m_sip_today.csv"

# safe-core live exit shape -- REGISTRY_SHAPES["ribbon_ride"] convention (verbatim from the
# repo's own walk harnesses, e.g. tp1_reachability_2026_08_06.py; matches today's live exec
# row: tp1_premium_pct=1.0, stop_mode structure, cat cap -50%).
SAFE_SHAPE = dict(
    premium_stop_pct=-0.20, tp1_premium_pct=1.0, tp1_qty_fraction=0.667,
    profit_lock_mode="trailing", runner_target_pct=99.0, trail_pct=0.15,
    profit_lock_arm_pct=0.05, stop_mode="structure", catastrophe_stop_pct=-0.50,
    profit_lock_arm_scope="post_tp1")
TIME_STOP = dt.time(15, 40)
QTY = 3  # today's real safe-core qty

# Today's REAL broker fills -- BS calibration points. Spots are the entry-quality ledger's
# own SIP 1m joins where available (fills-ledger truth), NOT bar guesses.
# (name, ET time, strike, premium, spot)
CAL_FILLS = [
    ("772C entry safe-2 09:46:34", "09:46:34", 772, 1.67, 771.57),
    ("772C entry safe-3 09:47:06", "09:47:06", 772, 1.33, 771.42),
    ("774C entry risky-3 09:47:09", "09:47:09", 774, 0.62, 771.42),
    ("772C stop safe-2 ~10:01:30", "10:01:30", 772, 1.16, 771.09),
    ("772C stop safe-3 ~10:02:00", "10:02:00", 772, 1.11, 771.30),
    ("774C stop risky-3 ~10:02:00", "10:02:00", 774, 0.45, 771.30),
]


# --------------------------------------------------------------------------- data fetch
def _creds() -> tuple[str, str]:
    m = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def _get(url: str) -> dict:
    key, sec = _creds()
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b["v"]} for b in bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    return df.reset_index(drop=True)


def fetch_all() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # (1) live-twin IEX 5m: EXACT heartbeat_core._fetch_spy_5m URL shape (7d back, limit 600,
    # feed=iex, sort=asc). This is the frame the live engine actually scored today.
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min&start={start}"
           f"&limit=600&feed=iex&adjustment=raw&sort=asc")
    d = _get(url)
    df = _bars_to_df(d.get("bars", []))
    df.to_csv(IEX5_CSV, index=False)
    print(f"IEX5 live-twin: {len(df)} bars {df['timestamp'].iloc[0]} .. {df['timestamp'].iloc[-1]}")

    # (2) IEX 1m today (premium walk + morning-entry structure factors)
    rows: list[dict] = []
    page = None
    start1 = f"{DAY}T13:25:00Z"  # 09:25 ET
    while True:
        u = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&start={start1}"
             f"&limit=1000&feed=iex&adjustment=raw&sort=asc")
        if page:
            u += f"&page_token={page}"
        d = _get(u)
        rows.extend(d.get("bars", []))
        page = d.get("next_page_token")
        if not page:
            break
    df1 = _bars_to_df(rows)
    df1.to_csv(IEX1_CSV, index=False)
    print(f"IEX1 today: {len(df1)} bars, last {df1['timestamp'].iloc[-1] if len(df1) else 'NONE'}")

    # (3) SIP 5m today, 16+ min delayed tail (free-tier SIP rule) -- f10 provenance check
    end = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    u = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min&start={DAY}T08:00:00Z"
         f"&end={end}&limit=1000&feed=sip&adjustment=raw&sort=asc")
    try:
        d = _get(u)
        dfs = _bars_to_df(d.get("bars", []))
        dfs.to_csv(SIP5_CSV, index=False)
        print(f"SIP5 today: {len(dfs)} bars")
    except Exception as e:  # noqa: BLE001 -- SIP entitlement can 403; provenance check is optional
        print(f"SIP5 fetch failed (disclosed, optional): {type(e).__name__}: {e}")


# --------------------------------------------------------------------------- ledger load
def load_today_rows() -> list[dict]:
    rows = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("ts_et", "")).startswith(DAY):
                r.pop("context_bundle", None)
                rows.append(r)
    return rows


def group_by_trigger(rows: list[dict], account: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("account") != account:
            continue
        tb = r.get("trigger_bar_et")
        if not tb or not str(tb).startswith(DAY):
            continue
        out.setdefault(str(tb)[:16], []).append(r)  # key 'YYYY-MM-DDTHH:MM'
    for k in out:
        out[k].sort(key=lambda r: r["ts_et"])
    return out


# --------------------------------------------------------------------------- replay core
def load_iex5() -> pd.DataFrame:
    df = pd.read_csv(IEX5_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    return df


def vix_context(groups_safe: dict) -> tuple[dict, dict, float, float]:
    """Per-trigger-bar VIX injection reconstructed from the LIVE ledger (the exact vix_now the
    engine consumed at each trigger bar) + daily MAs from the (prior-days-only) vix cache."""
    keys = sorted(groups_safe)
    vix_now_map: dict[str, float] = {}
    vix_prior_map: dict[str, float] = {}
    prev = None
    for k in keys:
        v = float(groups_safe[k][-1].get("vix") or 0.0)
        vix_now_map[k] = v
        vix_prior_map[k] = prev if prev is not None else v
        prev = v
    vix_df = es._load_vix_cache(DAY_D - dt.timedelta(days=1))  # cache through 08-06 (prior days)
    ma5, ma20 = es._vix_daily_ma_asof(vix_df, DAY_D)
    return vix_now_map, vix_prior_map, ma5, ma20


def replay_bar(account: str, params: dict, bars5: pd.DataFrame, trig_key: str,
               vix_now: float, vix_prior: float, ma5: float, ma20: float,
               vix_intraday: list[float], levels_active: list[float], multi: list[float],
               disable_filters: list[int] | None = None) -> dict:
    """One trigger bar through the REAL path. trig_key='YYYY-MM-DDTHH:MM' (wall ET)."""
    B = dt.datetime.fromisoformat(trig_key).replace(tzinfo=ET)
    cut = pd.Timestamp(B + dt.timedelta(minutes=5))
    sliced = bars5[bars5["timestamp"] <= cut].reset_index(drop=True)
    if len(sliced) == 0 or sliced["timestamp"].iloc[-1] != cut:
        return {"trigger_bar": trig_key, "status": "NO_NEXT_BAR"}
    payload = hc._build_payload(
        sliced, params, vix=(vix_now, vix_prior), levels=(levels_active, multi),
        vix_ma=(ma5, ma20), vix_intraday=vix_intraday or None)
    if payload is None:
        return {"trigger_bar": trig_key, "status": "SKIP_NO_DATA"}
    got = str(payload["bar_ctx"]["timestamp_et"])[:16]
    if got != trig_key:
        return {"trigger_bar": trig_key, "status": f"TRIG_MISMATCH:{got}"}
    if disable_filters:
        payload = copy.deepcopy(payload)
        bk = dict(payload["score_params"].get("bull_kwargs") or {})
        bk["disable_filters"] = list(disable_filters)
        payload["score_params"]["bull_kwargs"] = bk
    v = hc._engine_verdict(payload)
    return {"trigger_bar": trig_key, "status": "OK",
            "spy": payload["bar_ctx"]["bar"]["close"],
            "verdict": v.get("verdict"), "side": v.get("side"), "setup": v.get("setup_name"),
            "bear_score": v.get("bear_score"), "bull_score": v.get("bull_score"),
            "triggers": v.get("triggers_fired") or [],
            "bear_blockers": v.get("bear_blockers"), "bull_blockers": v.get("bull_blockers"),
            "trigger_level": v.get("rejection_level")}


FIDELITY_FIELDS = ("verdict", "side", "setup", "bear_score", "bull_score",
                   "bear_blockers", "bull_blockers", "triggers")


def run_fidelity() -> dict:
    rows = load_today_rows()
    bars5 = load_iex5()
    out: dict = {"accounts": {}}
    groups_safe = group_by_trigger(rows, "safe")
    vix_now_map, vix_prior_map, ma5, ma20 = vix_context(groups_safe)
    out["vix_ma"] = {"ma5": ma5, "ma20": ma20}
    for account in ("safe", "bold"):
        groups = group_by_trigger(rows, account)
        params = json.loads(hc.ACCOUNTS[account]["params"].read_text(encoding="utf-8"))
        acct_rows = []
        intraday: list[float] = []
        for k in sorted(groups):
            ref = groups[k][-1]
            vnow = vix_now_map.get(k, float(ref.get("vix") or 0.0))
            intraday = intraday + [vnow]
            lv_live = [float(x) for x in (ref.get("levels_active") or [])]
            spy_ref = float(ref.get("spy") or 0.0)
            lv_recon, multi = es._load_levels_as_of(DAY_D, spy_ref)
            rep = replay_bar(account, params, bars5, k, vnow, vix_prior_map.get(k, vnow),
                             ma5, ma20, list(intraday), lv_live, multi)
            live = {f: ref.get(f) for f in FIDELITY_FIELDS}
            live["spy"] = ref.get("spy")
            match = {}
            for f in FIDELITY_FIELDS:
                a, b = live.get(f), rep.get(f)
                if f in ("bear_blockers", "bull_blockers", "triggers"):
                    a = sorted(a) if isinstance(a, list) else a
                    b = sorted(b) if isinstance(b, list) else b
                match[f] = (a == b)
            n_ticks = len(groups[k])
            verdicts_in_group = sorted({r.get("verdict") for r in groups[k]})
            acct_rows.append({
                "trigger_bar": k, "n_live_ticks": n_ticks,
                "live_group_verdicts": verdicts_in_group,
                "live": live, "replay": rep, "match": match,
                "all_match": all(match.values()) and rep.get("status") == "OK",
                "levels_live_vs_recon": {
                    "live_n": len(lv_live), "recon_n": len(lv_recon),
                    "identical": sorted(lv_live) == sorted(lv_recon),
                    "only_live": sorted(set(lv_live) - set(lv_recon)),
                    "only_recon": sorted(set(lv_recon) - set(lv_live))},
            })
        n_ok = sum(1 for r in acct_rows if r["replay"].get("status") == "OK")
        n_all = sum(1 for r in acct_rows if r["all_match"])
        n_verdict = sum(1 for r in acct_rows if r["match"].get("verdict") and r["replay"].get("status") == "OK")
        out["accounts"][account] = {
            "n_trigger_bars": len(acct_rows), "n_replayed_ok": n_ok,
            "verdict_match": n_verdict, "full_match": n_all, "rows": acct_rows}
        print(f"[fidelity] {account}: bars={len(acct_rows)} ok={n_ok} "
              f"verdict_match={n_verdict} full_match={n_all}")
    return out


# --------------------------------------------------------------------------- EST pricing
def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _ncdf(d1) - K * _ncdf(d2)


def implied_vol(price: float, S: float, K: float, T: float) -> float:
    lo, hi = 0.005, 4.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bs_call(S, K, T, mid) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _t_years(ts_et: dt.datetime) -> float:
    close = dt.datetime.combine(ts_et.date(), dt.time(16, 0))
    if ts_et.tzinfo is not None:
        ts_et = ts_et.replace(tzinfo=None)
    return max(1.0, (close - ts_et).total_seconds()) / (365.0 * 86400.0)


def load_iex1() -> pd.DataFrame:
    df = pd.read_csv(IEX1_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    df["ts_naive"] = df["timestamp"].dt.tz_localize(None)
    return df


def calibrate_iv(df1: pd.DataFrame) -> dict:
    """Least-squares single IV over ALL 6 real morning fills (spots from the fills ledger's
    own SIP joins). All downstream premiums are EST -- BS, constant IV, no skew/IV-path
    modeling; residuals reported per fill. NOTE the fills themselves are mutually
    inconsistent at any single IV (772C printed 1.67 -> 1.33 in 32s on a -0.15 SPY move),
    so EST cells carry real quote-noise error; treat as directional, never cents."""
    pts = []
    for name, t_str, K, prem, spot in CAL_FILLS:
        t = dt.datetime.combine(DAY_D, dt.time.fromisoformat(t_str))
        pts.append((name, t, K, prem, spot))

    def sse(sig: float) -> float:
        return sum((bs_call(S, K, _t_years(t), sig) - p) ** 2 for _, t, K, p, S in pts)

    lo, hi = 0.02, 1.5
    for _ in range(120):  # golden-ish ternary search on smooth 1-D SSE
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if sse(m1) < sse(m2):
            hi = m2
        else:
            lo = m1
    iv = 0.5 * (lo + hi)
    checks = []
    for name, t, K, prem, S in pts:
        est = bs_call(S, K, _t_years(t), iv)
        checks.append({"fill": name, "actual": prem, "est": round(est, 3),
                       "err_pct": round(100.0 * (est - prem) / prem, 1), "spy_at": S})
    return {"iv": iv, "fit": "least-squares over 6 real fills", "checks": checks}


def est_opt_df(df1: pd.DataFrame, K: int, iv: float, start_naive: dt.datetime) -> pd.DataFrame:
    """1m EST premium OHLC frame for strike K from SPY 1m bars (call: monotone in S)."""
    d = df1[(df1["ts_naive"] >= start_naive - dt.timedelta(minutes=1))
            & (df1["ts_naive"].dt.time >= dt.time(9, 30))
            & (df1["ts_naive"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rows = []
    for _, r in d.iterrows():
        t = r["ts_naive"].to_pydatetime()
        T = _t_years(t)
        rows.append({"timestamp_et": r["ts_naive"],
                     "open": round(bs_call(float(r["open"]), K, T, iv), 3),
                     "high": round(bs_call(float(r["high"]), K, T, iv), 3),
                     "low": round(bs_call(float(r["low"]), K, T, iv), 3),
                     "close": round(bs_call(float(r["close"]), K, T, iv), 3)})
    return pd.DataFrame(rows)


def ribbon_lookup_5m(bars5: pd.DataFrame) -> pd.DataFrame:
    ts = bars5["timestamp"].dt.tz_localize(None)
    rth = (ts.dt.time >= dt.time(9, 30)) & (ts.dt.time < dt.time(16, 0))
    spy_rth = bars5.loc[rth].reset_index(drop=True)
    rib = compute_ribbon(spy_rth["close"])
    out = pd.DataFrame({"timestamp_et": spy_rth["timestamp"].dt.tz_localize(None),
                        "stack": rib["stack"].values})
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    merged = pd.merge_asof(left.sort_values("timestamp_et", kind="stable"),
                           lookup.sort_values("timestamp_et", kind="stable"),
                           on="timestamp_et", direction="backward")
    return merged


# --------------------------------------------------------------------------- variants
VARIANTS = {"HEAD": None, "f10_relaxed": [10], "f7_relaxed": [7], "f7_f10_relaxed": [7, 10]}


def run_variants() -> dict:
    rows = load_today_rows()
    bars5 = load_iex5()
    df1 = load_iex1()
    cal = calibrate_iv(df1)
    iv = cal["iv"]
    groups_safe = group_by_trigger(rows, "safe")
    vix_now_map, vix_prior_map, ma5, ma20 = vix_context(groups_safe)
    params = json.loads(hc.ACCOUNTS["safe"]["params"].read_text(encoding="utf-8"))
    lookup = ribbon_lookup_5m(bars5)
    spy5_naive = pd.DataFrame({
        "timestamp_et": bars5["timestamp"].dt.tz_localize(None),
        "open": bars5["open"], "high": bars5["high"], "low": bars5["low"],
        "close": bars5["close"]})
    out: dict = {"est_calibration": cal, "variants": {}}
    keys = sorted(k for k in groups_safe if k >= f"{DAY}T09:35")
    for vname, disable in VARIANTS.items():
        trades = []
        scan = []
        flat_after: dt.datetime | None = None
        intraday: list[float] = [vix_now_map[k] for k in sorted(groups_safe) if k < keys[0]] if keys else []
        for k in keys:
            ref = groups_safe[k][-1]
            vnow = vix_now_map[k]
            intraday.append(vnow)
            entry_tick = dt.datetime.fromisoformat(k) + dt.timedelta(minutes=6)  # naive wall ET
            if flat_after is not None and entry_tick <= flat_after:
                scan.append({"trigger_bar": k, "skipped": "IN_POSITION"})
                continue
            lv_live = [float(x) for x in (ref.get("levels_active") or [])]
            _, multi = es._load_levels_as_of(DAY_D, float(ref.get("spy") or 0.0))
            rep = replay_bar("safe", params, bars5, k, vnow, vix_prior_map.get(k, vnow),
                             ma5, ma20, list(intraday), lv_live, multi,
                             disable_filters=disable)
            scan.append({"trigger_bar": k, "verdict": rep.get("verdict"),
                         "bull_score": rep.get("bull_score"),
                         "bull_blockers": rep.get("bull_blockers"),
                         "status": rep.get("status")})
            if rep.get("status") == "OK" and rep.get("verdict") == "ENTER_BULL":
                bar1 = df1[df1["ts_naive"] >= entry_tick]
                if len(bar1) == 0:
                    scan[-1]["note"] = "no 1m bar at entry tick (tape ends)"
                    continue
                S_entry = float(bar1["open"].iloc[0])
                K = int(round(S_entry))
                entry_prem = round(bs_call(S_entry, K, _t_years(entry_tick), iv), 3)
                if entry_prem < 0.05:
                    scan[-1]["note"] = "EST premium < 0.05, skipped"
                    continue
                opt_df = est_opt_df(df1, K, iv, entry_tick)
                rtd = ribbon_tick_df_for(opt_df, lookup)
                res = walk_exit_manager(
                    symbol=f"SPY260807C{K:05d}000", side="C", entry_time_et=entry_tick,
                    entry_premium=entry_prem, qty=QTY, exit_shape=dict(SAFE_SHAPE),
                    structure_stop_enabled=True, trigger_level=rep.get("trigger_level"),
                    strategy="ribbon_ride", time_stop_et=TIME_STOP,
                    opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=spy5_naive)
                exit_t = res.exit_time_et
                open_at_eod = exit_t is None
                if open_at_eod:
                    # position still open at end of available tape -- mark-to-last EST close
                    last = opt_df.iloc[-1]
                    mtm = (float(last["close"]) - entry_prem) * 100 * QTY
                    trades.append({"trigger_bar": k, "entry_tick": entry_tick.isoformat(),
                                   "strike": K, "entry_premium_EST": entry_prem, "qty": QTY,
                                   "exit": "OPEN_AT_TAPE_END", "mtm_usd_EST": round(mtm, 2),
                                   "legs": [], "spy_entry": S_entry})
                    flat_after = opt_df["timestamp_et"].iloc[-1].to_pydatetime()
                else:
                    trades.append({"trigger_bar": k, "entry_tick": entry_tick.isoformat(),
                                   "strike": K, "entry_premium_EST": entry_prem, "qty": QTY,
                                   "exit_reason": res.exit_reason,
                                   "exit_time": str(exit_t),
                                   "pnl_usd_EST": round(res.dollar_pnl, 2),
                                   "legs": [{"stage": l.stage, "kind": l.kind, "qty": l.qty,
                                             "price": l.fill_price, "ts": str(l.ts_et),
                                             "leg_pnl": round(l.leg_pnl, 2)} for l in res.legs],
                                   "spy_entry": S_entry})
                    flat_after = pd.Timestamp(exit_t).to_pydatetime()
        closed = [t for t in trades if "pnl_usd_EST" in t]
        openp = [t for t in trades if t.get("exit") == "OPEN_AT_TAPE_END"]
        out["variants"][vname] = {
            "disable_filters": disable, "n_entries": len(trades),
            "closed_pnl_usd_EST": round(sum(t["pnl_usd_EST"] for t in closed), 2),
            "open_mtm_usd_EST": round(sum(t["mtm_usd_EST"] for t in openp), 2),
            "trades": trades, "scan": scan}
        print(f"[variant {vname}] entries={len(trades)} closed_EST="
              f"{out['variants'][vname]['closed_pnl_usd_EST']} open_mtm_EST="
              f"{out['variants'][vname]['open_mtm_usd_EST']}")
    return out


# --------------------------------------------------------------------------- f10 provenance
def run_f10_provenance() -> dict:
    """f10 arithmetic (green bar + vol >= 0.7 x 20-bar mean) on IEX-vs-SIP today's RTH bars.
    Live is IEX/IEX (heartbeat_core._fetch_spy_5m feed=iex); SIP is what the backtest cache
    carries. A pass-rate gap here = backtest-vs-live parity risk on filter 10."""
    out: dict = {"note": "green(close>open) AND vol>=0.7*mean(prior 20 bars), per feed"}
    frames = {}
    iex = load_iex5()
    ts = iex["timestamp"].dt.tz_localize(None)
    frames["iex"] = iex[(ts.dt.date == DAY_D) | (ts.dt.date < DAY_D)]
    if SIP5_CSV.exists():
        sip = pd.read_csv(SIP5_CSV)
        sip["timestamp"] = pd.to_datetime(sip["timestamp"], utc=True).dt.tz_convert("America/New_York")
        frames["sip"] = sip
    res = {}
    for feed, df in frames.items():
        t = df["timestamp"].dt.tz_localize(None)
        rth = (t.dt.time >= dt.time(9, 30)) & (t.dt.time < dt.time(16, 0))
        d = df.loc[rth].reset_index(drop=True)
        d_t = d["timestamp"].dt.tz_localize(None)
        rows = []
        for i in range(len(d)):
            if d_t.iloc[i].date() != DAY_D:
                continue
            base = d["volume"].iloc[max(0, i - 20):i]
            if len(base) < 5:
                continue
            vol_ok = float(d["volume"].iloc[i]) >= 0.7 * float(base.mean())
            green = float(d["close"].iloc[i]) > float(d["open"].iloc[i])
            rows.append({"bar": d_t.iloc[i].strftime("%H:%M"), "green": green,
                         "vol_ok": vol_ok, "f10_pass": green and vol_ok})
        res[feed] = {"n": len(rows),
                     "f10_pass_rate": round(sum(r["f10_pass"] for r in rows) / max(1, len(rows)), 3),
                     "vol_ok_rate": round(sum(r["vol_ok"] for r in rows) / max(1, len(rows)), 3),
                     "green_rate": round(sum(r["green"] for r in rows) / max(1, len(rows)), 3),
                     "bars": rows}
    if "iex" in res and "sip" in res:
        by_iex = {r["bar"]: r for r in res["iex"]["bars"]}
        diffs = [b["bar"] for b in res["sip"]["bars"]
                 if b["bar"] in by_iex and by_iex[b["bar"]]["f10_pass"] != b["f10_pass"]]
        res["disagreement_bars"] = diffs
    out["feeds"] = res
    return out


# --------------------------------------------------------------------------- main
def main() -> None:
    phases = sys.argv[1:] or ["all"]
    results: dict = {}
    if OUT_JSON.exists():
        try:
            results = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results = {}
    if "fetch" in phases or "all" in phases:
        fetch_all()
    if "fidelity" in phases or "all" in phases:
        results["fidelity"] = run_fidelity()
    if "variants" in phases or "all" in phases:
        results["variants"] = run_variants()
    if "provenance" in phases or "all" in phases:
        results["f10_provenance"] = run_f10_provenance()
    results["generated_at"] = dt.datetime.now(ET).isoformat()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
