"""j_called_entries_replay_2026_07_31 -- what would J's 4 called entries have paid?

LANE (2026-07-31 evening grind): J read the chart after close and called 4 entries verbatim
(3 on 07-31, 1 on 07-30). This tool replays each through the REAL live exit core
(exit_manager.plan_exit_actions via exit_manager_walk.walk_exit_manager -- never
simulate_trade_real, per the 2026-07-09 sim-parity scar), on real OPRA 5m bars, under
(a) the engine's stated registry shape (strategies.RIBBON_RIDE.exit -- the cores' CONTROL)
and (b) risky-3's ZONE-RIDE lane (same shape + trail_pct=0.2, its accounts.json exit_patch).

PRE-REGISTRATION -- FROZEN BEFORE ANY FETCH/RUN (et_clock: 2026-07-31 16:51:57 Friday EDT,
market_hours=False):
  Hypothesis: J's four called entries were (a) real on the SIP tape as described,
    (b) visible to the engine as raw/shadow level-tied detections, (c) refused by nameable
    mechanisms, and (d) profitable under the engine's own exit shapes on real OPRA fills.
  Entry convention: trigger bar = the named 5m bar (verified on the SIP tape BEFORE this
    freeze); entry tick = trigger-bar start + 5 min (the bar's close instant); fill = OPEN of
    the first OPRA 5m bar with timestamp_et >= entry tick (the 07-29 blocked-replay template's
    "next available print" convention); exits are walked strictly AFTER the fill timestamp
    (entry+1 ruling, markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md).
  Contract: ATM call = round(trigger-bar close) -> nearest $1 strike. qty=3 (min-contract
    floor, Rule 6). Real OPRA bars only (Alpaca v1beta1); a missing contract or missing entry
    print EXCLUDES the row -- never synthetic.
  Lanes: CORE-CONTROL = strategies.RIBBON_RIDE.exit.to_dict() verbatim,
    structure_stop_enabled=True (live params.json value, read 2026-07-31), trigger_level per
    entry, time_stop 15:50 ET. ZONE-RIDE = same + trail_pct=0.2. ribbon_tick_df=None
    (DISCLOSED: ribbon_flip_back exits cannot fire in this walk; same disclosure as the
    07-29 template).
  Diagnostics (bounds, NOT mechanisms): HOLD-to-15:45 open; ORACLE post-entry peak.
  Validation cell: risky-3's REAL 07-31 12:19 fill (746C @ 0.33, its own broker truth
    +$126 realized on that position) re-walked under ZONE-RIDE to measure walk fidelity.
  n=4 (+1 alt) = ANECDOTE. Nothing arms. Any promising shape earns its own pre-registration
    on the full population. All cells reported, none dropped.

THE FOUR ENTRIES (tape verified against backtest/data/spy_5m_2026-05-19_2026-07-31.csv, SIP):
  e1  07-31 trigger 10:15 bar (RTH-low wick 737.68 EXACT -- J: "bet the house... off the
      wick"); close 738.605; ATM 739C; level 737.68 (inside SHELF_737.05_738.65 w5).
  e2  07-31 trigger 11:30 bar (pullback low 739.81 vs 739.73 shelf w5 -- J called "the
      739.7x level"; 8c above the shelf line); close 740.74; ATM 741C; level 739.73.
  e3  07-31 trigger 12:10 bar (first close 743.55 > 743.25 shelf after the 742.97-retest --
      J: "primo entry"; actual SIP premarket low 742.79, 12:05/12:15 retest lows
      742.46/742.78); ATM 744C; level 743.25 (the engine's own blocked trigger_level).
  e4  07-30 trigger 12:40 bar (retest bounce low 737.755 inside J's called 737.6-737.85
      line -- "bounced 12:40 and rode"); close 738.03; ATM 738C; level 737.60.
  e4alt 07-30 trigger 12:00 power candle (close 738.28 > 737.85 on 770K vol -- "broke back
      through on the 12:00 power candle"); ATM 738C; level 737.60. Secondary/disclosed.

ANALYSIS ONLY. No live file touched, no order placed, no gate/param changed.
Output: analysis/deep-research/J-CALLED-ENTRIES-2026-07-31.json (this tool) + .md (hand-written
synthesis citing this JSON).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

from backtest.lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import strategies  # noqa: E402

ET = "America/New_York"
SPY_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"

FROZEN_ET_CLOCK = "2026-07-31 16:51:57 Friday EDT"
QTY = 3

ENTRIES = [
    {"tag": "e1", "day": "2026-07-31", "trig_bar": "10:15", "trig_close": 738.605,
     "strike": 739, "side_letter": "C", "level": 737.68,
     "j_call": "long off the 737.68 wick/bottom ~10:15-10:20 ET",
     "engine_verdict": "HOLD all window; bull_score peak 9 (blockers 5,8,10); "
                       "wick_reclaim fired SHADOW-only 10:21-10:35"},
    {"tag": "e2", "day": "2026-07-31", "trig_bar": "11:30", "trig_close": 740.74,
     "strike": 741, "side_letter": "C", "level": 739.73,
     "j_call": "long ~11:30 at the 739.7x level",
     "engine_verdict": "HOLD; no live trigger class for touch-and-hold (level_reclaim needs "
                       "low<level<close cross); pullback_hold/wick_reclaim SHADOW-only"},
    {"tag": "e3", "day": "2026-07-31", "trig_bar": "12:10", "trig_close": 743.55,
     "strike": 744, "side_letter": "C", "level": 743.25,
     "j_call": "long ~12:10-12:15 off the 742.97-retest bounce (primo entry)",
     "engine_verdict": "bull 11/11 PASSED 12:16-12:18 -> SKIP_ELITE_BULL_LEVEL_RECLAIM "
                       "(block_elite_bull, old-feed evidence)"},
    {"tag": "e4", "day": "2026-07-30", "trig_bar": "12:40", "trig_close": 738.03,
     "strike": 738, "side_letter": "C", "level": 737.60,
     "j_call": "07-30: bounced 12:40 off the 737.6-737.85 line and rode",
     "engine_verdict": "BLIND day (0 levels all RTH) -> no level trigger possible; engine "
                       "instead ENTER_BEAR 11:31-11:46 near the low"},
    {"tag": "e4alt", "day": "2026-07-30", "trig_bar": "12:00", "trig_close": 738.28,
     "strike": 738, "side_letter": "C", "level": 737.60,
     "j_call": "07-30: broke back through on the 12:00 power candle (secondary read)",
     "engine_verdict": "same blind-day context as e4"},
]

# risky-3's REAL broker fill on the signal the cores refused (validation of walk fidelity).
VALIDATION = {"tag": "v1-risky3-real", "day": "2026-07-31", "symbol": "SPY260731C00746000",
              "entry_tick": "12:19:03", "entry_premium": 0.33, "qty": 5,
              "level": 743.25,
              "broker_truth": "+$126 realized on this position (tp1 3@0.65 +$96, trail 2@0.48 +$30)"}


def _creds() -> tuple[str, str]:
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def _get(url: str) -> dict:
    key, sec = _creds()
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key,
                                               "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _bars_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame([{"timestamp_et": b["t"], "open": b["o"], "high": b["h"],
                        "low": b["l"], "close": b["c"], "volume": b.get("v", 0)}
                       for b in rows])
    if df.empty:
        return df
    df["timestamp_et"] = (pd.to_datetime(df["timestamp_et"], utc=True)
                          .dt.tz_convert(ET).dt.tz_localize(None))
    return df.sort_values("timestamp_et").reset_index(drop=True)


def option_symbol(day: str, strike: int, side_letter: str) -> str:
    yymmdd = day[2:4] + day[5:7] + day[8:10]
    return f"SPY{yymmdd}{side_letter}{strike * 1000:08d}"


def fetch_option(day: str, sym: str) -> pd.DataFrame:
    url = (f"https://data.alpaca.markets/v1beta1/options/bars?symbols={sym}"
           f"&timeframe=5Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=200&sort=asc")
    return _bars_df((_get(url).get("bars") or {}).get(sym) or [])


def load_spy_5m(day: str) -> pd.DataFrame:
    df = pd.read_csv(SPY_CSV)
    df["timestamp_et"] = (pd.to_datetime(df["timestamp_et"], utc=True)
                          .dt.tz_convert(ET).dt.tz_localize(None))
    day_start = pd.Timestamp(f"{day} 09:30:00")
    day_end = pd.Timestamp(f"{day} 16:00:00")
    sel = df[(df["timestamp_et"] >= day_start) & (df["timestamp_et"] < day_end)]
    return sel[["timestamp_et", "open", "high", "low", "close"]].reset_index(drop=True)


def path_stats(opt: pd.DataFrame, entry_ts: pd.Timestamp, entry: float) -> dict:
    after = opt[opt["timestamp_et"] > entry_ts]
    if after.empty:
        return {"mfe_pct": None, "mae_pct": None, "close_pct": None}
    return {
        "mfe_pct": round((after["high"].max() / entry - 1) * 100, 1),
        "mae_pct": round((after["low"].min() / entry - 1) * 100, 1),
        "close_pct": round((float(after.iloc[-1]["close"]) / entry - 1) * 100, 1),
    }


def run_walk(sym: str, level: float, opt: pd.DataFrame, spy: pd.DataFrame, shape: dict,
             entry: float, entry_ts: pd.Timestamp, qty: int):
    return walk_exit_manager(
        symbol=sym, side="C", entry_time_et=entry_ts.to_pydatetime(),
        entry_premium=entry, qty=qty, exit_shape=shape, structure_stop_enabled=True,
        trigger_level=level, strategy="ribbon_ride", time_stop_et=dt.time(15, 50),
        opt_df=opt, ribbon_tick_df=None, five_min_spy_df=spy)


def main() -> int:
    base = strategies.RIBBON_RIDE.exit.to_dict()
    zone_ride = dict(base, trail_pct=0.2)  # risky-3 accounts.json exit_patch overlay
    lanes = {"CORE-CONTROL": base, "ZONE-RIDE": zone_ride}
    print(f"CORE-CONTROL shape: {json.dumps(base)}")
    print(f"ZONE-RIDE shape:    {json.dumps(zone_ride)}\n")

    out = {
        "frozen_et_clock": FROZEN_ET_CLOCK,
        "prereg": "see module docstring (frozen before any fetch/run)",
        "qty": QTY,
        "lanes": {k: v for k, v in lanes.items()},
        "label": "n=4 (+1 alt) ANECDOTE -- real OPRA only, nothing arms",
        "entries": [],
        "validation": None,
    }

    spy_by_day = {d: load_spy_5m(d) for d in ("2026-07-30", "2026-07-31")}
    for d, sdf in spy_by_day.items():
        print(f"SPY 5m {d}: {len(sdf)} RTH bars from SIP cache")

    for e in ENTRIES:
        sym = option_symbol(e["day"], e["strike"], e["side_letter"])
        opt = fetch_option(e["day"], sym)
        row = dict(e, symbol=sym)
        if opt.empty:
            print(f"[{e['tag']}] {sym}: NO OPRA DATA -- excluded")
            row["excluded"] = "no_option_data"
            out["entries"].append(row)
            continue
        trig_start = pd.Timestamp(f"{e['day']} {e['trig_bar']}:00")
        entry_tick = trig_start + pd.Timedelta(minutes=5)
        after = opt[opt["timestamp_et"] >= entry_tick]
        if after.empty:
            print(f"[{e['tag']}] {sym}: no print at/after {entry_tick} -- excluded")
            row["excluded"] = "no_entry_print"
            out["entries"].append(row)
            continue
        fill_bar = after.iloc[0]
        entry = float(fill_bar["open"])
        entry_ts = pd.Timestamp(fill_bar["timestamp_et"])
        if entry <= 0:
            row["excluded"] = "zero_entry_print"
            out["entries"].append(row)
            continue
        ps = path_stats(opt, entry_ts, entry)
        row.update(entry_ts=str(entry_ts), entry_premium=entry, opt_bars=len(opt), path=ps)
        print(f"=== [{e['tag']}] {sym}  trig {e['trig_bar']}  fill {entry_ts.time()} "
              f"@ ${entry:.2f}  (level {e['level']})")
        print(f"    J: {e['j_call']}")
        print(f"    engine: {e['engine_verdict']}")
        print(f"    path after fill: MFE {ps['mfe_pct']}%  MAE {ps['mae_pct']}%  "
              f"close {ps['close_pct']}%")
        walks = []
        for name, shape in lanes.items():
            r = run_walk(sym, e["level"], opt, spy_by_day[e["day"]], shape, entry,
                         entry_ts, QTY)
            legs = [{"stage": leg.stage, "qty": leg.qty, "fill": round(leg.fill_price, 2),
                     "ts": str(leg.ts_et), "leg_pnl": round(leg.leg_pnl, 2)}
                    for leg in r.legs]
            walks.append({"lane": name, "pnl": round(r.dollar_pnl, 2),
                          "exit_reason": r.exit_reason, "exit_time": str(r.exit_time_et),
                          "resolved": r.resolved, "legs": legs})
            print(f"      {name:<14} ${r.dollar_pnl:>8.2f}   {r.exit_reason[:44]}")
        # Diagnostics (bounds, not mechanisms)
        eod = opt[opt["timestamp_et"] >= pd.Timestamp(f"{e['day']} 15:45:00")]
        if len(eod):
            px = float(eod.iloc[0]["open"])
            pnl = round((px - entry) * QTY * 100, 2)
            walks.append({"lane": "HOLD-to-15:45 (diagnostic)", "pnl": pnl,
                          "exit_reason": "fixed_hold", "exit_time": str(eod.iloc[0]["timestamp_et"]),
                          "resolved": True, "legs": []})
            print(f"      {'HOLD-to-15:45':<14} ${pnl:>8.2f}   diagnostic bound")
        after_e = opt[opt["timestamp_et"] > entry_ts]
        orc = round((float(after_e["high"].max()) - entry) * QTY * 100, 2)
        walks.append({"lane": "ORACLE peak (unachievable)", "pnl": orc,
                      "exit_reason": "oracle", "exit_time": None, "resolved": True, "legs": []})
        print(f"      {'ORACLE':<14} ${orc:>8.2f}   diagnostic bound\n")
        row["walks"] = walks
        out["entries"].append(row)

    # Validation cell: risky-3's real 12:19 fill re-walked under ZONE-RIDE.
    v = VALIDATION
    opt = fetch_option(v["day"], v["symbol"])
    if not opt.empty:
        entry_ts = pd.Timestamp(f"{v['day']} {v['entry_tick']}")
        r = run_walk(v["symbol"], v["level"], opt, spy_by_day[v["day"]], zone_ride,
                     v["entry_premium"], entry_ts, v["qty"])
        legs = [{"stage": leg.stage, "qty": leg.qty, "fill": round(leg.fill_price, 2),
                 "ts": str(leg.ts_et), "leg_pnl": round(leg.leg_pnl, 2)} for leg in r.legs]
        out["validation"] = dict(v, walk_pnl=round(r.dollar_pnl, 2),
                                 walk_exit_reason=r.exit_reason, walk_legs=legs)
        print(f"[VALIDATION] risky-3 real {v['symbol']} @ {v['entry_premium']} x{v['qty']}: "
              f"walk ${r.dollar_pnl:.2f} ({r.exit_reason}) vs broker {v['broker_truth']}")
    else:
        out["validation"] = dict(v, excluded="no_option_data")

    p = REPO / "analysis" / "deep-research" / "J-CALLED-ENTRIES-2026-07-31.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {p}")

    core_tot = sum(next(w["pnl"] for w in x["walks"] if w["lane"] == "CORE-CONTROL")
                   for x in out["entries"] if not x.get("excluded") and x["tag"] != "e4alt")
    zr_tot = sum(next(w["pnl"] for w in x["walks"] if w["lane"] == "ZONE-RIDE")
                 for x in out["entries"] if not x.get("excluded") and x["tag"] != "e4alt")
    print(f"\nPRIMARY 4 ENTRIES x {QTY} contracts -- CORE-CONTROL total: ${core_tot:,.2f}"
          f" | ZONE-RIDE total: ${zr_tot:,.2f}  (ANECDOTE, n=4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
