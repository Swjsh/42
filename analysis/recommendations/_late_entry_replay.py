"""_late_entry_replay.py -- counterfactual replay for the SKIP_LATE_ENTRY ceiling review
(strategy/candidates/_chef-inbox/2026-07-14-late-entry-ceiling-review.md).

Replays the two identified 15:00-15:35 ET SKIP_LATE_ENTRY block events (2026-07-06, 2026-07-13)
through the ACTUAL production exit_manager.plan_exit_actions decision core (the identical
methodology ssb_certification_study.replay_production_path uses for SS-B certification), fed
REAL Alpaca OPRA 1-min option bars and REAL SPY 5-min bars, with a hard 15:50 ET time stop
(exit_manager.TIME_STOP_ET, matching the flatten doctrine).

Entry premium = the option bar's OPEN at the minute the SKIP_LATE_ENTRY block fired (the
earliest of a repeated-fire cluster on the same level -- only the FIRST fire is a genuinely
new trigger per Rule 4, later re-fires are the same signal re-confirming, not new entries).

ANALYSIS ONLY. Touches no trading-path file, no params.json. Writes to analysis/recommendations/.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import pandas as pd  # noqa: E402
import structure_stop_study as sss  # noqa: E402
from et_clock import et_now  # noqa: E402
from exit_manager import ExitState, plan_exit_actions, TIME_STOP_ET  # noqa: E402
import strategies  # noqa: E402

RAW = json.loads((REPO / "analysis" / "recommendations" / "_late_entry_raw_bars.json")
                  .read_text(encoding="utf-8"))


def spy_lifetime_df(bars_5m: list) -> pd.DataFrame:
    rows = []
    for b in bars_5m:
        t_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        t_et = et_now(t_utc)
        rows.append({"timestamp_et": t_et, "close": float(b["c"])})
    return pd.DataFrame(rows)


def last_closed_5m_close_asof(spy_lifetime: pd.DataFrame, t: dt.datetime):
    if spy_lifetime.empty:
        return None
    cutoff = t - dt.timedelta(minutes=5)
    closed = spy_lifetime[spy_lifetime["timestamp_et"] <= cutoff]
    if closed.empty:
        return None
    return float(closed.iloc[-1]["close"])


def replay_production_path(entry_premium, side, qty, norm_bars, spy_lifetime, exit_shape,
                            trigger_level, structure_stop_enabled, time_stop_et=TIME_STOP_ET,
                            strategy="ribbon_ride"):
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty,
                                  exit_shape=exit_shape, strategy=strategy,
                                  trigger_level=trigger_level,
                                  structure_stop_enabled=structure_stop_enabled)
    open_qty = qty
    realized = 0.0
    exits = []
    last_close = entry_premium
    for bar in norm_bars:
        if open_qty <= 0:
            break
        last_close = bar.c
        lc5 = last_closed_5m_close_asof(spy_lifetime, bar.dt)
        now_et = bar.dt.time()
        dec = plan_exit_actions(state, best_premium=bar.h, worst_premium=bar.l,
                                 open_qty=open_qty, now_et=now_et, ribbon_flip_back=False,
                                 time_stop_et=time_stop_et, last_closed_5m_close=lc5)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                fp = entry_premium * (1.0 + state.premium_stop_pct)
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            elif a.stage == "structure_stop":
                fp = bar.o
            else:
                fp = bar.c
            realized += (fp - entry_premium) * a.qty * 100.0
            open_qty -= a.qty
            exits.append({"stage": a.stage, "qty": a.qty, "fill_price": round(fp, 4),
                          "dt": bar.dt.isoformat(), "reason": a.reason})
        state = dec.state
    if open_qty > 0:
        realized += (last_close - entry_premium) * open_qty * 100.0
        exits.append({"stage": "eod_mark", "qty": open_qty, "fill_price": round(last_close, 4)})
        open_qty = 0
    return {"pnl": round(realized, 2), "exits": exits,
            "structure_fired": any(e["stage"] == "structure_stop" for e in exits),
            "final_stop_mode": state.stop_mode}


def run_case(label, option_bars_key, entry_ts_utc, entry_premium_override, side, qty,
             trigger_level, spy_5m_key):
    bars = RAW[option_bars_key]
    norm_bars = sss.norm_bars_from_esp(bars, entry_ts_utc=entry_ts_utc)
    if not norm_bars:
        return {"label": label, "pnl": None, "reason": "no bars at/after entry"}
    entry_premium = entry_premium_override if entry_premium_override is not None else norm_bars[0].o
    spy_life = spy_lifetime_df(RAW[spy_5m_key])
    exit_shape = strategies.RIBBON_RIDE.exit.to_dict()
    result = replay_production_path(entry_premium=entry_premium, side=side, qty=qty,
                                     norm_bars=norm_bars, spy_lifetime=spy_life,
                                     exit_shape=exit_shape, trigger_level=trigger_level,
                                     structure_stop_enabled=True, time_stop_et=TIME_STOP_ET)
    result["label"] = label
    result["entry_premium"] = entry_premium
    result["qty"] = qty
    result["side"] = side
    result["trigger_level"] = trigger_level
    result["n_bars"] = len(norm_bars)
    return result


def main():
    cases = []

    # --- 2026-07-13 15:16 ET event: BEARISH_REJECTION, level 750.30 (same level risky-3's
    # real 12:40 fill used -- structure_stop @ 750.30, per analysis/daily-brief/
    # 2026-07-13-FULL-AUDIT.md line 32). First re-confirmation fire = 15:16:03/04 ET.
    cases.append(run_case(
        "2026-07-13_core_safe_749P_entry1516",
        "2026-07-13_safe_749P", "2026-07-13T19:16:00Z", None, "P", 3, 750.30,
        "2026-07-13_spy_5min"))
    cases.append(run_case(
        "2026-07-13_core_bold_746P_entry1516",
        "2026-07-13_bold_746P", "2026-07-13T19:16:00Z", None, "P", 5, 750.30,
        "2026-07-13_spy_5min"))

    # --- 2026-07-06 15:22 ET event: BULLISH_RECLAIM, 755C, ELITE, all 4 fleet arms
    # identical strike/premium (shared_signal fan-out). No trigger_level captured in the
    # decisions.jsonl row for this event -- use the ELITE-quality entry premium (0.04) as
    # entry and let structure_stop_enabled=True with trigger_level=None (fails open per
    # exit_manager._structure_stop_hit's None-safety -- disclosed, not silently assumed).
    # NOTE: decisions.jsonl's logged "premium": 0.04 for this event is the engine's INTERNAL
    # quote snapshot at decision time, not the traded tape -- the REAL OPRA 1-min bar at the
    # entry minute (19:22Z) prints o=0.02/h=0.02/l=0.01/c=0.02 on only 15 trades (illiquid,
    # 100%+ spread). Using the REAL traded bar open (0.02) per this study's own real-data
    # discipline, not the internal snapshot; disclosed as a data-quality flag, not corrected
    # silently.
    cases.append(run_case(
        "2026-07-06_fleet_755C_entry1522_no_level_failclosed",
        "2026-07-06_755C", "2026-07-06T19:22:00Z", None, "C", 5, None,
        "2026-07-06_spy_5min"))
    # Sensitivity check: no trigger_level was logged for this pre-SS-B-era event (structure
    # stop didn't exist yet on 07-06; SS-B shipped 2026-07-09). SPY 1-min tape 14:40-15:35 ET
    # shows the whole session pinned 751.0-752.4 (never breaks below ~751.5 after entry) --
    # 751.0 (round-number reclaim level, ~$1 OTM-3 buffer under the 752 entry spot) is used
    # here ONLY as a disclosed sensitivity check, not a recovered fact.
    cases.append(run_case(
        "2026-07-06_fleet_755C_entry1522_level751_sensitivity",
        "2026-07-06_755C", "2026-07-06T19:22:00Z", None, "C", 5, 751.0,
        "2026-07-06_spy_5min"))

    out = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
           "exit_shape_used": strategies.RIBBON_RIDE.exit.to_dict(),
           "time_stop_et": str(TIME_STOP_ET), "cases": cases}
    out_path = REPO / "analysis" / "recommendations" / "_late_entry_replay_output.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
