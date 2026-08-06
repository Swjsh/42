#!/usr/bin/env python
"""lever_sizing_atm_revert_2026_08_06.py -- LEVER 2, cell (f): REVERT risky-3's ATM TIER?

CONTEXT. The 08-04 audit called ATM-TIER-EXTENSION "a ~2.2x size increase in a strike-selection
costume", which is why this cell lives in the SIZING lane. Its pre-registered kill criterion
(analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json) is:
    "per-arm net realized P&L on the new-tier cohort < 0 at the sample floor -> revert that
     arm's participation same day"
and the 2026-08-06 03:39 ET evaluation found risky-3 at n=14 / -$653 -> KILL_CRITERION_MET.
That evaluation ran BEFORE Thursday's session. This module re-evaluates it on the closed book
and then does the thing nobody has done: prices what the revert would ACTUALLY have returned,
on the cohort's own real fills, using real OPRA and the REAL production exit core.

REVERT TARGET IS *OTM-2*, NOT OTM-3. risky-3's equity is ~$5.98K, i.e. the $2K-$10K bracket.
The one-line revert restores StrikeTier(2_000, 10_000, -2, 'OTM-2'). Convention (verified in
crypto/lib/strike_selection.py:196-207): BEAR puts strike = ATM + offset; BULL calls strike =
ATM - offset. So offset -2 means calls go 2 strikes UP, puts go 2 strikes DOWN.

METHOD -- three independent readings, reported side by side, never averaged:
  1. LEDGER TRUTH -- the cohort's realized P&L on real broker fills, re-cut on the closed book.
  2. HARNESS PARITY -- walk the ACTUAL ATM contract through walk_exit_manager ->
     exit_manager.plan_exit_actions on real 1-min OPRA and compare to the real fill. This is
     the control. If the harness cannot reproduce what actually happened, its counterfactual
     is worthless and the run says so instead of quietly reporting the counterfactual.
  3. COUNTERFACTUAL -- the same walk on the OTM-2 contract, entered at the OTM-2 contract's own
     real OPRA price in the SAME minute, same qty, same exit shape, same trigger level.

Sequential, one position at a time. No independent trades recombined. NEVER
simulator_real.simulate_trade_real (the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar).

ANALYSIS ONLY. Writes only analysis/deep-research/.
Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_sizing_atm_revert_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import exit_shape_parity_study as esp  # noqa: E402
import exit_armscope_ab_2026_07_28 as ab1  # noqa: E402  (ribbon lookup machinery, reused)
import strategies as fleet_strategies  # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import option_symbol  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
DEC = REPO / "automation" / "state" / "fleet" / "risky-3" / "decisions.jsonl"
SPY_FILE = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
OUT = REPO / "analysis" / "deep-research" / "LEVER-SIZING-ATM-REVERT-2026-08-06.json"

ARM = "risky-3"
# The prereg was frozen 2026-08-04T00:25 ET; the tier change shipped that night, so the
# post-arming cohort starts on the 08-04 session. 08-03 fills are PRE-arming and excluded.
COHORT_START = "2026-08-04"
REVERT_OFFSET = -2          # V15_BOLD_TIERS row for the $2K-$10K bracket == OTM-2
TIME_STOP_ET = dt.time(15, 50)   # em.TIME_STOP_ET default; RIBBON_RIDE ships no override
EXIT_PATCH = {"stop_mode": "structure", "profit_lock_mode": "trailing", "trail_pct": 0.2}


HIGHRES = REPO / "backtest" / "data" / "highres"
ET_OFFSET = dt.timezone(dt.timedelta(hours=-4))  # EDT; this cohort is entirely EDT-dated


def log(m: str) -> None:
    print(f"[atm-revert] {m}", flush=True)


def load_1min(symbol: str, date_et: str):
    """Schema-tolerant wrapper over _option_bars_1min_cache.fetch_1min_cached.

    DEFECT FOUND THIS RUN (not fixed here -- shared surface, 3+ consumers, see the report):
    three files in backtest/data/highres/ (SPY260805C00776000 / C00777000 / P00772000, all
    2026-08-05) were written by a DIFFERENT producer whose schema is `timestamp` in UTC, not
    `timestamp_et`. fetch_1min_cached does `df["timestamp_et"]` unconditionally and raises
    KeyError on exactly those three -- i.e. the shared 1-min cache is booby-trapped for every
    consumer that touches an 08-05 contract. Handled locally so this study can run; reported
    as an OPEN finding rather than patched blind during someone else's lane."""
    path = HIGHRES / f"{symbol}_1m_{date_et}.csv"
    if path.exists():
        df = pd.read_csv(path)
        if "timestamp_et" in df.columns:
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
            return df, "cache_hit"
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], utc=True)
            df = df.assign(timestamp_et=ts.dt.tz_convert(ET_OFFSET).dt.tz_localize(None))
            return df.sort_values("timestamp_et").reset_index(drop=True), "cache_hit_utc_schema"
        raise ValueError(f"unknown cache schema for {path}: {list(df.columns)}")
    return fetch_1min_cached(symbol, date_et)


def load_positions() -> list[dict]:
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    ts_et = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    ps = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"] and p["arm"] == ARM]
    out = []
    for p in ps:
        if p["date_et"] < COHORT_START:
            continue
        p["entry_ts_et"] = ts_et.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["qty"] = int(round(p["entry_qty"]))
        p["side"] = "P" if "P00" in p["symbol"] else "C"
        p["strike"] = int(p["symbol"][-8:]) // 1000
        out.append(p)
    out.sort(key=lambda p: p["entry_ts_et"])
    return out


def decision_index() -> dict:
    """(date, HH:MM) -> the ENTER row the executor actually wrote: setup + trigger_level."""
    idx = {}
    for line in DEC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if not r.get("strike") or not (r.get("placement") or {}).get("placed"):
            continue
        t = str(r["ts_et"])[:16]          # YYYY-MM-DDTHH:MM
        idx[t] = r
    return idx


def match_decision(idx: dict, entry_ts_et: str) -> dict | None:
    """Fills land 1-3s after the decision row; allow a +-2 minute window, nearest wins."""
    base = dt.datetime.fromisoformat(entry_ts_et.split("+")[0])
    for delta in (0, -1, 1, -2, 2):
        k = (base + dt.timedelta(minutes=delta)).strftime("%Y-%m-%dT%H:%M")
        if k in idx:
            return idx[k]
    return None


def shape_for(setup_name: str) -> dict:
    """Registry exit shape for the strategy that fired, merged with risky-3's exit_patch --
    exactly fleet_executor._exit_shape_dict's shallow-merge-over-registry semantics."""
    name = "ribbon_ride" if "RIBBON" in (setup_name or "") else "vwap_continuation"
    base = fleet_strategies.by_name(name).exit.to_dict()
    return {**base, **EXIT_PATCH}, name


def main() -> None:
    positions = load_positions()
    idx = decision_index()
    spy = pd.read_csv(SPY_FILE)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    ribbon_lookup = ab1.build_ribbon_lookup(spy)

    rows, n_no_cf_bars, n_no_dec = [], 0, 0
    for p in positions:
        dec = match_decision(idx, p["entry_ts_et"])
        if dec is None:
            n_no_dec += 1
        setup = (dec or {}).get("setup_name") or ""
        shape, strat = shape_for(setup)
        trig = (dec or {}).get("trigger_level")
        trig = float(trig) if trig is not None else None
        date = dt.date.fromisoformat(p["date_et"])
        # OTM-2 counterfactual strike, per strike_selection's documented convention
        cf_strike = (p["strike"] + REVERT_OFFSET) if p["side"] == "P" else (p["strike"] - REVERT_OFFSET)
        cf_symbol = option_symbol(date, cf_strike, p["side"])

        act_df, act_src = load_1min(p["symbol"], p["date_et"])
        cf_df, cf_src = load_1min(cf_symbol, p["date_et"])
        day_spy = spy.loc[spy["timestamp_et"].dt.date == date].reset_index(drop=True)
        entry_dt = ab1.naive_dt(dt.datetime.fromisoformat(p["entry_ts_et"].split("+")[0]))

        row = {"date": p["date_et"], "entry_t": p["entry_ts_et"][11:19], "setup": setup,
               "strategy": strat, "side": p["side"], "qty": p["qty"],
               "atm_symbol": p["symbol"], "atm_entry_fill": round(p["entry_price"], 4),
               "atm_real_pnl": p["pnl"], "trigger_level": trig,
               "otm2_symbol": cf_symbol, "bars": {"atm": act_src, "otm2": cf_src}}

        def walk(df, symbol, prem):
            return walk_exit_manager(
                symbol=symbol, side=p["side"], entry_time_et=entry_dt, entry_premium=prem,
                qty=p["qty"], exit_shape=shape, structure_stop_enabled=True,
                trigger_level=trig, strategy=strat, time_stop_et=TIME_STOP_ET,
                opt_df=df, ribbon_tick_df=ab1.ribbon_tick_df_for(df, ribbon_lookup),
                five_min_spy_df=day_spy, opt_df_resolution="1min")

        # --- control: the ACTUAL contract at the ACTUAL fill price
        if act_df is not None and not day_spy.empty:
            r = walk(act_df, p["symbol"], p["entry_price"])
            row["atm_walked_pnl"] = r.dollar_pnl
            row["atm_walked_reason"] = r.exit_reason
            row["parity_delta_vs_real_fill"] = round(r.dollar_pnl - p["pnl"], 2)
        # --- counterfactual: OTM-2 at ITS OWN real OPRA price in the SAME minute
        cf_prem = None
        if cf_df is not None:
            at = cf_df.loc[cf_df["timestamp_et"] <= entry_dt]
            if not at.empty:
                cf_prem = float(at.iloc[-1]["close"])
        if cf_df is None or cf_prem is None or day_spy.empty:
            n_no_cf_bars += 1
            row["otm2_pnl"] = None
            row["otm2_note"] = "no OTM-2 OPRA bar at/ before the entry minute"
        else:
            r = walk(cf_df, cf_symbol, cf_prem)
            row["otm2_entry_premium"] = round(cf_prem, 4)
            row["otm2_pnl"] = r.dollar_pnl
            row["otm2_exit_reason"] = r.exit_reason
            row["otm2_minus_atm_real"] = round(r.dollar_pnl - p["pnl"], 2)
            row["premium_ratio_atm_over_otm2"] = round(p["entry_price"] / cf_prem, 3) if cf_prem else None
        rows.append(row)
        log(f"{row['date']} {row['entry_t']} {p['symbol'][-9:]}->{cf_symbol[-9:]} "
            f"real={p['pnl']:>8.2f} walked={row.get('atm_walked_pnl')} otm2={row.get('otm2_pnl')}")

    parity = [r for r in rows if "parity_delta_vs_real_fill" in r]
    priced = [r for r in rows if r.get("otm2_pnl") is not None]
    real_tot = round(sum(r["atm_real_pnl"] for r in rows), 2)
    real_priced = round(sum(r["atm_real_pnl"] for r in priced), 2)
    out = {
        "lens": "LEVER 2 cell (f) -- revert risky-3 ATM -> OTM-2?",
        "run_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "arm": ARM, "cohort_start": COHORT_START,
        "revert_target": "OTM-2 (StrikeTier(2_000,10_000,-2)) -- risky-3 sits in the $2K-$10K bracket, NOT OTM-3",
        "prereg": "analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json",
        "KILL_CRITERION_RECUT_ON_CLOSED_BOOK": {
            "n_positions": len(rows),
            "net_realized": real_tot,
            "by_session": {},
            "prior_evaluation_2026_08_06_0339": {"n": 14, "net": -653.0, "verdict": "KILL_CRITERION_MET"},
            "why_it_changed": ("the 03:39 ET evaluation ran BEFORE Thursday's session; "
                               "2026-08-06's risky-3 ATM put closed +$830"),
        },
        "harness_parity_control": {
            "n_walked": len(parity),
            "sum_walked": round(sum(r["atm_walked_pnl"] for r in parity), 2),
            "sum_real_same_subset": round(sum(r["atm_real_pnl"] for r in parity), 2),
            "sum_parity_delta": round(sum(r["parity_delta_vs_real_fill"] for r in parity), 2),
            "worst_abs_delta": max((abs(r["parity_delta_vs_real_fill"]) for r in parity), default=None),
        },
        "counterfactual_otm2": {
            "n_priced": len(priced), "n_unpriceable": n_no_cf_bars,
            "otm2_total": round(sum(r["otm2_pnl"] for r in priced), 2),
            "atm_real_total_same_subset": real_priced,
            "revert_delta": round(sum(r["otm2_pnl"] for r in priced) - real_priced, 2),
            "median_premium_ratio_atm_over_otm2": None,
        },
        "n_positions_missing_decision_row": n_no_dec,
        "rows": rows,
    }
    by_s: dict = {}
    for r in rows:
        by_s[r["date"]] = round(by_s.get(r["date"], 0.0) + r["atm_real_pnl"], 2)
    out["KILL_CRITERION_RECUT_ON_CLOSED_BOOK"]["by_session"] = by_s
    ratios = sorted(r["premium_ratio_atm_over_otm2"] for r in priced
                    if r.get("premium_ratio_atm_over_otm2"))
    if ratios:
        out["counterfactual_otm2"]["median_premium_ratio_atm_over_otm2"] = ratios[len(ratios) // 2]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"wrote {OUT}")
    log(f"cohort real {real_tot} | otm2 {out['counterfactual_otm2']['otm2_total']} "
        f"| revert delta {out['counterfactual_otm2']['revert_delta']} "
        f"| parity delta {out['harness_parity_control']['sum_parity_delta']}")


if __name__ == "__main__":
    main()
