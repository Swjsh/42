"""LANE 1 (2026-08-07): bull filters 7 & 10 — name, mechanism, provenance, history.

Produces the data half of analysis/deep-research/FRIDAY-BLOCKERS-2026-08-07.{md,json}.

What it does (read-only on all trading-path files):
  1. Per-session bull-side block-rate history for filters 7 and 10 from
     automation/state/core-decisions.jsonl (safe-account rows; bold differs only in
     min_triggers on f11, f7/f10 inputs identical).
  2. Sole-blocker-ELITE exposure series: ticks where bull_score >= 9 and exactly one
     of {7} / {10} is the entire bull_blockers list, per session.
  3. IEX-vs-SIP flip test: for every sole-[10] and sole-[7] tick in the last 15
     sessions, recompute the filter on (a) the same IEX feed the live engine uses
     (heartbeat_core._fetch_spy_5m, feed=iex, unchanged since 2026-06-26) and
     (b) SIP bars — the feed family the 0.7x constant was ratified on (v11 backtest
     cache). A tick that FAILS on IEX but PASSES on SIP is a feed-calibration flip.
  4. Today's tick-by-tick refusal table 10:15-11:46 with recomputed inputs.

LABELS: reconstructions re-fetch historical bars; late corrections possible but feed
identity matches the live path. Window math replicates heartbeat_core._build_payload
(RTH-only, W=150, trig_idx=n-2, vol_baseline_20 = mean of 20 bars before trig).
Validated 3/3 against today's ledger exhibits before this run.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "FRIDAY-BLOCKERS-2026-08-07.json"
CACHE_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
F10_VOL_MULT = 0.7  # live: params filter_9_vol_multiplier=0.7 -> bull_kwargs f10_vol_mult (heartbeat_core.py:647,654)

LAST_15 = ["2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23",
           "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
           "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]


# ---------------------------------------------------------------- bars fetch
def _creds():
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def fetch_5m(feed: str, start_iso: str) -> pd.DataFrame:
    """Paginated 5m SPY bars for `feed` from start_iso to now. Cached to scratch."""
    cache = CACHE_DIR / f"spy5m_{feed}.json"
    if cache.exists():
        bars = json.loads(cache.read_text())
    else:
        key, sec = _creds()
        bars, token = [], None
        while True:
            url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min"
                   f"&start={start_iso}&limit=10000&feed={feed}&adjustment=raw&sort=asc")
            if token:
                url += f"&page_token={token}"
            req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key,
                                                       "APCA-API-SECRET-KEY": sec})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            bars.extend(data.get("bars") or [])
            token = data.get("next_page_token")
            if not token:
                break
        cache.write_text(json.dumps(bars))
    df = pd.DataFrame([{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b["v"]} for b in bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    ts = df["timestamp"]
    df = df[(ts.dt.time >= dt.time(9, 30)) & (ts.dt.time < dt.time(16, 0))]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- filter mirrors
def f10_eval(win: pd.DataFrame, trig_idx: int) -> dict:
    trig = win.iloc[trig_idx]
    vol20 = float(win["volume"].iloc[max(0, trig_idx - 20):trig_idx].mean())
    green = bool(trig["close"] > trig["open"])
    ratio = float(trig["volume"]) / vol20 if vol20 else None
    passed = green and ratio is not None and float(trig["volume"]) >= F10_VOL_MULT * vol20
    leg = "pass" if passed else ("red_bar" if not green else "volume")
    return {"green": green, "vol": float(trig["volume"]), "baseline": round(vol20, 1),
            "ratio": round(ratio, 3) if ratio else None, "pass": passed, "fail_leg": leg}


def f7_eval(win: pd.DataFrame, idx: int) -> dict:
    """Mirror of filters.py:1352 _bullish_volume_divergence_failed."""
    if idx < 2:
        return {"blocked": False, "pair": None}
    candidates = [(idx - 1, idx), (idx - 2, idx - 1), (idx - 2, idx)]
    for bo_idx, rec_idx in candidates:
        bo, rec = win.iloc[bo_idx], win.iloc[rec_idx]
        if bo["close"] <= bo["open"]:
            continue
        if rec["close"] < rec["open"] and rec["volume"] >= bo["volume"]:
            return {"blocked": True,
                    "pair": {"bo_t": str(bo["timestamp"])[11:16], "bo_body": round(float(bo["close"] - bo["open"]), 3),
                             "bo_vol": float(bo["volume"]), "rec_t": str(rec["timestamp"])[11:16],
                             "rec_body": round(float(rec["close"] - rec["open"]), 3), "rec_vol": float(rec["volume"])}}
    return {"blocked": False, "pair": None}


def window_at(df_rth: pd.DataFrame, trig_ts: pd.Timestamp) -> "tuple[pd.DataFrame,int] | None":
    """Frame truncated one bar after trig, last 150 RTH bars (heartbeat_core._build_payload)."""
    mask = df_rth["timestamp"] <= (trig_ts + pd.Timedelta(minutes=5))
    frame = df_rth[mask].iloc[-150:].reset_index(drop=True)
    n = len(frame)
    if n < 22:
        return None
    trig_idx = n - 2
    if frame["timestamp"].iloc[trig_idx] != trig_ts:
        return None  # bar missing on this feed at this stamp
    return frame, trig_idx


# ---------------------------------------------------------------- main
def main() -> None:
    rows = []
    with LEDGER.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    safe = [r for r in rows if r.get("account") == "safe"]

    # ---- 1+2: per-session history -------------------------------------------
    per_session: dict[str, dict] = defaultdict(lambda: {
        "n_ticks": 0, "f10_block": 0, "f7_block": 0,
        "sole10_elite": 0, "sole7_elite": 0, "bull_trigger_ticks": 0})
    sole_ticks: list[dict] = []
    for r in safe:
        d = r.get("ts_et", "")[:10]
        if not d:
            continue
        s = per_session[d]
        s["n_ticks"] += 1
        bb = r.get("bull_blockers") or []
        score = r.get("bull_score")
        trig_raw = r.get("bull_triggers_raw") or []
        if 10 in bb:
            s["f10_block"] += 1
        if 7 in bb:
            s["f7_block"] += 1
        if trig_raw:
            s["bull_trigger_ticks"] += 1
        if isinstance(score, int) and score >= 9 and len(bb) == 1 and bb[0] in (7, 10):
            key = "sole10_elite" if bb[0] == 10 else "sole7_elite"
            s[key] += 1
            sole_ticks.append({"date": d, "ts_et": r["ts_et"], "blocker": bb[0],
                               "trig_bar_et": r.get("trigger_bar_et"), "spy": r.get("spy"),
                               "score": score, "triggers": trig_raw})

    history = {d: dict(v) for d, v in sorted(per_session.items()) if v["n_ticks"] >= 100}

    # ---- 3: IEX vs SIP flip test on last-15-session sole ticks ---------------
    iex = fetch_5m("iex", "2026-07-08T00:00:00Z")
    sip = fetch_5m("sip", "2026-07-08T00:00:00Z")
    flips = {"f10": {"n": 0, "iex_fail_sip_pass": 0, "both_fail": 0, "iex_pass": 0,
                     "green_mismatch": 0, "unresolvable": 0, "examples": []},
             "f7": {"n": 0, "iex_block_sip_clear": 0, "both_block": 0, "iex_clear": 0,
                    "unresolvable": 0, "examples": []}}
    today_table = []
    for t in sole_ticks:
        if t["date"] not in LAST_15 or not t["trig_bar_et"]:
            continue
        trig_ts = pd.Timestamp(t["trig_bar_et"])
        wi = window_at(iex, trig_ts)
        ws = window_at(sip, trig_ts)
        which = "f10" if t["blocker"] == 10 else "f7"
        rec = flips[which]
        rec["n"] += 1
        if wi is None or ws is None:
            rec["unresolvable"] += 1
            continue
        if which == "f10":
            ri, rs = f10_eval(*wi), f10_eval(*ws)
            if ri["pass"]:
                rec["iex_pass"] += 1          # recon disagrees with live block (late data)
            elif rs["pass"]:
                rec["iex_fail_sip_pass"] += 1
                if len(rec["examples"]) < 12:
                    rec["examples"].append({**t, "iex": ri, "sip": rs})
            else:
                rec["both_fail"] += 1
            if ri["green"] != rs["green"]:
                rec["green_mismatch"] += 1
            if t["date"] == "2026-08-07":
                today_table.append({**t, "iex": ri, "sip": rs})
        else:
            ri, rs = f7_eval(*wi), f7_eval(*ws)
            if not ri["blocked"]:
                rec["iex_clear"] += 1
            elif not rs["blocked"]:
                rec["iex_block_sip_clear"] += 1
                if len(rec["examples"]) < 12:
                    rec["examples"].append({**t, "iex": ri, "sip": rs})
            else:
                rec["both_block"] += 1
            if t["date"] == "2026-08-07":
                today_table.append({**t, "iex": ri, "sip": rs})

    out = {
        "generated_at_et": dt.datetime.now().astimezone().isoformat(),
        "lane": "LANE1-name-and-mechanism",
        "labels": ["RECONSTRUCTION: bars re-fetched post-hoc, same feeds as live path",
                   "SIP cells = feed the 0.7x constant was ratified on (v11 cache)",
                   "sole-elite = bull_score>=9 AND bull_blockers == [7] or [10], safe rows"],
        "filter_identity": {
            "f7_bull": "_bullish_volume_divergence_failed (filters.py:1352): green bar followed "
                       "within 1-2 bars by red bar with volume >= green bar's volume -> block. "
                       "No minimum body/volume on the 'breakout' leg.",
            "f10_bull": "buyer_pressure_bar_v11 (filters.py:1343): trig bar must be green AND "
                        "volume >= 0.7 x mean(prior 20 bars). Also blocks if ribbon_now is None "
                        "(filters.py:1211-1212) - not the case today (ribbon=BULL logged).",
            "f10_knob_wiring": "heartbeat_core.py:647+654: bull f10_vol_mult and bear f9_vol_mult "
                               "BOTH read params filter_9_vol_multiplier=0.7 - one knob, two filters."},
        "per_session_history": history,
        "flip_test_last15": flips,
        "today_sole_tick_table": today_table,
    }
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(json.dumps({"sessions": len(history), "flips": {k: {kk: vv for kk, vv in v.items() if kk != 'examples'}
                                                          for k, v in flips.items()}}, indent=1))
    print("\nper-session (date  ticks  f10%  f7%  sole10  sole7  trig_ticks):")
    for d, s in history.items():
        print(f"{d}  {s['n_ticks']:4d}  {100*s['f10_block']/s['n_ticks']:5.1f}  "
              f"{100*s['f7_block']/s['n_ticks']:5.1f}  {s['sole10_elite']:3d}  {s['sole7_elite']:3d}  "
              f"{s['bull_trigger_ticks']:4d}")


if __name__ == "__main__":
    main()
