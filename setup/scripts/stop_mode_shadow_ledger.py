#!/usr/bin/env python
"""stop_mode_shadow_ledger.py -- FORWARD ACCRUAL for STOP-MODE-STRUCTURE-VS-PREMIUM.

BACKGROUND (2026-08-09). The 96-cell entry x exit matrix made ATR_STOP look dominant
(~$95/tr vs ~$16/tr control). A /fable-too-good audit decomposed that gap and inverted the
headline: +$60.55 of it was `stop_mode` (structure -> premium), +$25.59 was a LOOK-AHEAD
artifact (ATR measured on bars AFTER entry, then tested against those same bars), and the
per-trade dynamic width itself was NEGATIVE (-$6.94). A pre-registered confirmatory A/B
(prereg commit 2a36724a, results analysis/recommendations/stop-mode-structure-vs-premium-2026-08-09.json)
then found:

  - Population A (399-day replay): 8/8 entry rows positive, +$24-61/trade, ALL 16 premium
    cells surviving BH-FDR at q=0.10, mechanism signature (expectancy UP while WR DOWN)
    holding 8/8.
  - Population B (244 real broker fills, 26 days): all 4 rows positive in sign, but ZERO BH
    survivors, and the MECHANISM SIGNATURE FAILED 0/4 -- win rate did not fall. One day
    (+$3,020.20) exceeded both arms' entire total, so ex-best-day BOTH arms lose money.

The pre-registered kill criterion ("mechanism signature fails -> the dollar result is
unexplained and does not advance") FIRED on the real-fills layer. The honest reading is not
"population B refutes it" -- 26 days and 64 walked trades cannot resolve a $60/trade effect
against 0DTE variance -- it is "the retrospective real-fills window is too small, and its
mechanism reading disagrees." Only FORWARD evidence settles that.

THIS MODULE IS THAT FORWARD CLOCK. It is descriptive-only: it writes a ledger + a summary,
flips no knob, proposes no change, and places no order. It is never itself sufficient to
change stop_mode -- the eventual decision is its OWN pre-registered A/B that may cite this
ledger as its evidence base. Same contract as catastrophe_cap_shadow_ledger.py.

PAIRED, NOT SEQUENTIAL -- and why. Each real broker fill is walked TWICE from the identical
entry (same symbol, timestamp, premium, qty): once under the shipped CONTROL exit shape, once
under PREMIUM_20. The per-trade delta is therefore within-trade, which removes population
variance and is far more powerful at small n than comparing two aggregates -- and it is the
only shape that yields a clean paired WR delta, which is exactly the mechanism gate that
failed retrospectively.
  DISCLOSED LIMITATION: because both arms see the identical event set, this does NOT model
  how a different stop would have changed SUBSEQUENT entry opportunities (a wider/tighter stop
  holds a position longer/shorter and suppresses or frees later re-entries). The retrospective
  study measured that sequentially; this forward clock deliberately holds entries fixed to
  isolate the exit rule. Both readings are needed; neither replaces the other.

ACCRUAL_START_DATE = 2026-08-10 -- the first trading day strictly AFTER the retrospective
study's 2026-08-07 population cutoff. Scanning from here can never double-count a fill already
scored there, and keeps this clock genuinely out-of-sample. (Same discipline as
catastrophe_cap_shadow_ledger's own ACCRUAL_START_DATE note.)

EXTEND, DON'T FORK -- one source of truth each, no re-derivation:
  analysis/entry-quality/entry-quality-ledger.json    ENRICHED broker-truth fills (carries
                                                      trigger_level; the RAW build_population()
                                                      does NOT -- see run()'s note)
  entry_quality_ledger.load_bars                      cached SIP 5m bars
  lib.option_pricing_real.load_contract_bars          real cached OPRA option bars
  lib.exit_manager_walk.walk_exit_manager             THE live exit core (never simulator_real)
  engine_fullhist_replay.build_ribbon_lookup /
    ribbon_tick_df_for / TIME_STOP_ET                 ribbon alignment, no-look-ahead as-of join
  automation/state/fleet/strategies.ribbon_ride.exit  the shipped CONTROL shape, read not typed

COST: $0. Pure local computation over already-cached SIP + OPRA bars. No LLM, no paid API, no
new scheduled task. In the steady state there is no network call at all: entry_quality_ledger
has already cached every day in the window by the time this runs. A cold warmup window can
trigger ONE ranged SIP fetch through eql.load_bars, which then caches to disk forever -- that
path is the existing ledger's own, not a new dependency. It rides the nightly Gamma_WinnerAutopsy fire (16:25 ET)
under the same fail-open fold contract as pain_ledger / fill_latency / catastrophe_cap_shadow /
entry_shadow_counter. Revert: delete the try-block in winner_autopsy.py.

Outputs:
  analysis/recommendations/stop-mode-shadow-ledger.jsonl   append-only, dedup on activity_id
  analysis/recommendations/stop-mode-shadow-summary.json   running totals + gate status
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "backtest" / "tools"),
           str(REPO / "backtest" / "lib"), str(REPO / "automation" / "state" / "fleet"),
           str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "stop-mode-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "stop-mode-shadow-summary.json"

ACCRUAL_START_DATE = "2026-08-10"   # strictly after the retrospective cutoff 2026-08-07
WARMUP_DAYS = 12                    # ribbon EMAs are stateful -- cold-starting them per day
                                    # would misprice every early-session exit (C12)
BAR_GATE_DAYS = 20                  # pre-registered: >= 20 independent trading days
PREREG = "STOP-MODE-STRUCTURE-VS-PREMIUM-2026-08-09 (prereg commit 2a36724a)"


def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn last line must never kill the accrual
    return rows


def _shapes() -> tuple[dict, dict]:
    """CONTROL is READ from the shipped strategy, never re-typed here -- if the live exit
    shape changes, this clock's control arm follows it automatically."""
    import strategies as fleet_strategies
    control = dict(fleet_strategies.by_name("ribbon_ride").exit.to_dict())
    premium = dict(control)
    premium["stop_mode"] = "premium"      # the ONE variable
    return control, premium


def _walk(ev: dict, shape: dict, opt_df, day_spy, ribbon_lookup) -> dict | None:
    import engine_fullhist_replay as efr
    from lib.exit_manager_walk import walk_exit_manager

    entry_time = dt.datetime.fromisoformat(ev["ts_et"]).replace(microsecond=0)
    trigger = ev.get("trigger_level")
    res = walk_exit_manager(
        symbol=ev["symbol"], side=ev["opt_side"], entry_time_et=entry_time,
        entry_premium=float(ev["price"]), qty=int(ev["qty"]), exit_shape=shape,
        structure_stop_enabled=(shape.get("stop_mode") == "structure"),
        trigger_level=(float(trigger) if trigger is not None else None),
        strategy=str(ev.get("setup") or "ribbon_ride"), time_stop_et=efr.TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
        five_min_spy_df=day_spy, opt_df_resolution="5min", allow_5min=True)
    return {"pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "hold_minutes": res.hold_minutes,
            "reached_tp1": any(leg.stage == "tp1" for leg in res.legs)}


def _input_health(events: list[dict]) -> dict:
    """A clock whose INPUT silently stops updating reads exactly like a clock with nothing to
    report. Make the distinction visible rather than inferable (OP-33: silent failure is the
    only true failure)."""
    newest = max((e.get("date_et", "") for e in events), default="")
    today = dt.date.today()
    back = 1 if today.weekday() != 0 else 3          # Mon looks back to Fri
    prev_session = today - dt.timedelta(days=back)
    while prev_session.weekday() >= 5:               # skip Sat/Sun
        prev_session -= dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_ledger_newest_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- entry-quality-ledger.json has not advanced to the last "
                           "completed session; this clock is not being fed and its counts are "
                           "frozen, NOT a real absence of fills." if stale else "fed")}


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    days = sorted({r["date_et"] for r in rows})
    if not n:
        return {"prereg": PREREG, "accrual_start": ACCRUAL_START_DATE, "n_trades": 0,
                "n_days": 0, "days_to_bar": BAR_GATE_DAYS, "status": "ARMED_AWAITING_FILLS",
                "note": "No engine option fills on/after the accrual start yet. An empty clock "
                        "on day 0 is expected, NOT a failure -- but a clock still empty after "
                        "several trading days means the upstream ledger stopped feeding it."}
    d_sum = sum(r["delta_pnl"] for r in rows)
    wr_c = sum(1 for r in rows if r["control"]["pnl"] > 0) / n
    wr_p = sum(1 for r in rows if r["premium"]["pnl"] > 0) / n
    d_wr = wr_p - wr_c
    mean_d = d_sum / n
    return {
        "prereg": PREREG,
        "accrual_start": ACCRUAL_START_DATE,
        "n_trades": n, "n_days": len(days),
        "date_span": f"{days[0]}..{days[-1]}",
        "days_to_bar": max(0, BAR_GATE_DAYS - len(days)),
        "cum_delta_dollars": round(d_sum, 2),
        "mean_delta_per_trade": round(mean_d, 2),
        "control_total": round(sum(r["control"]["pnl"] for r in rows), 2),
        "premium_total": round(sum(r["premium"]["pnl"] for r in rows), 2),
        "wr_control": round(wr_c, 4), "wr_premium": round(wr_p, 4),
        "delta_wr": round(d_wr, 4),
        # The pre-registered mechanism gate: P&L up while WR DOWN. Retrospectively this held
        # 8/8 on the replay population and 0/4 on real fills -- that contradiction is the
        # single most informative thing this clock can resolve.
        "mechanism_signature_holds": bool(mean_d > 0 and d_wr < 0),
        "per_day_delta": {d: round(sum(r["delta_pnl"] for r in rows if r["date_et"] == d), 2)
                          for d in days},
        "days_premium_better": sum(
            1 for d in days if sum(r["delta_pnl"] for r in rows if r["date_et"] == d) > 0),
        "status": "ACCRUING" if len(days) < BAR_GATE_DAYS else "BAR_MET_AWAITING_PREREG_AB",
        "decision_rule": (
            "This ledger NEVER changes stop_mode by itself. At n_days >= 20 it becomes the "
            "evidence base for a separate pre-registered A/B. Reaching the bar is permission "
            "to TEST, not to ship."),
    }


def run() -> dict:
    """Nightly entry point. Fail-open by contract: the caller folds the returned dict into
    winner-autopsy-last.json and must never be broken by a failure here."""
    try:
        import pandas as pd
        import entry_quality_ledger as eql
        import engine_fullhist_replay as efr
        from lib.option_pricing_real import load_contract_bars

        # SOURCE = the ENRICHED ledger JSON, never eql.build_population() directly.
        # Root-caused 2026-08-09 by this module's own smoke test: build_population() returns
        # RAW fill events with no `trigger_level` key at all (verified: 249/249 missing) --
        # that field is attached later in the ledger pipeline. walk_exit_manager with
        # trigger_level=None has no chart level to invalidate against, so the structure stop
        # can NEVER fire, CONTROL silently collapses to premium-only, and both arms return
        # byte-identical P&L. The clock would have accrued exactly $0.00 forever while
        # reporting itself healthy. Read the enriched artifact instead.
        ledger_path = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
        if not ledger_path.exists():
            raise RuntimeError(f"enriched ledger missing: {ledger_path}")
        doc = json.loads(ledger_path.read_text(encoding="utf-8"))
        events = doc["events"]
        if events and not any("trigger_level" in e for e in events):
            raise RuntimeError("enriched ledger carries no trigger_level field -- structure "
                               "stops cannot fire; refusing to accrue meaningless zeros")
        fresh = [e for e in events
                 if e.get("is_option") and e.get("attribution") == "engine"
                 and e.get("side") == "buy" and e.get("date_et", "") >= ACCRUAL_START_DATE]

        existing = _read_ledger()
        seen = {r.get("activity_id") for r in existing}
        todo = [e for e in fresh if e.get("activity_id") not in seen]
        if not todo:
            summary = _summarize(existing)
            summary["new_this_run"] = 0
            summary.update(_input_health(events))
            SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            return summary

        control_shape, premium_shape = _shapes()

        # Ribbon EMAs are stateful: build the lookup over a continuous warmup window ending at
        # the newest date we need, never per-day cold (C12).
        need_dates = sorted({e["date_et"] for e in todo})
        all_days = sorted({e["date_et"] for e in events})
        first_i = max(0, all_days.index(need_dates[0]) - WARMUP_DAYS)
        window = all_days[first_i:all_days.index(need_dates[-1]) + 1]
        # eql.load_bars keys timeframes "1m"/"5m" and returns {t,o,h,l,c,v} dicts (naive ET),
        # NOT a timestamp_et/close frame -- both were wrong in the first cut and the smoke
        # test caught them. Map explicitly rather than guessing column positions.
        bars5 = eql.load_bars("5m", window)
        flat = [b for d in window for b in bars5.get(d, [])]
        if not flat:
            raise RuntimeError(f"no 5m SPY bars for window {window[0]}..{window[-1]}")
        spy = pd.DataFrame(flat).rename(columns={"t": "timestamp_et", "o": "open", "h": "high",
                                                 "l": "low", "c": "close", "v": "volume"})
        spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
        if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
            spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
        spy = (spy.sort_values("timestamp_et").drop_duplicates(subset="timestamp_et")
                  .reset_index(drop=True))
        ribbon_lookup = efr.build_ribbon_lookup(spy)
        # RTH-only for the per-day frame handed to the exit walker (load_bars returns
        # 04:00-20:00 ET); build_ribbon_lookup does its own RTH masking internally.
        rth = spy.loc[(spy["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)

        appended, skipped = [], []
        for ev in sorted(todo, key=lambda e: e["ts_et"]):
            opt_df = load_contract_bars(ev["symbol"])
            if opt_df is None or getattr(opt_df, "empty", True):
                skipped.append({"activity_id": ev.get("activity_id"), "reason": "no_opra_cache"})
                continue
            entry_time = dt.datetime.fromisoformat(ev["ts_et"])
            day_spy = rth.loc[rth["timestamp_et"].dt.date == entry_time.date()].reset_index(drop=True)
            if day_spy.empty:
                skipped.append({"activity_id": ev.get("activity_id"), "reason": "no_spy_day"})
                continue
            c = _walk(ev, control_shape, opt_df, day_spy, ribbon_lookup)
            p = _walk(ev, premium_shape, opt_df, day_spy, ribbon_lookup)
            if c is None or p is None:
                skipped.append({"activity_id": ev.get("activity_id"), "reason": "walk_failed"})
                continue
            appended.append({
                "activity_id": ev.get("activity_id"), "date_et": ev["date_et"],
                "ts_et": ev["ts_et"], "arm": ev.get("arm"), "symbol": ev["symbol"],
                "opt_side": ev["opt_side"], "qty": int(ev["qty"]),
                "entry_premium": float(ev["price"]), "setup": ev.get("setup"),
                "broker_pnl": ev.get("pnl"),
                "control": c, "premium": p,
                "delta_pnl": round(p["pnl"] - c["pnl"], 2),
            })

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        summary = _summarize(existing + appended)
        summary["new_this_run"] = len(appended)
        summary["skipped_this_run"] = skipped
        summary.update(_input_health(events))
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:300], "prereg": PREREG}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
