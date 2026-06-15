"""Run EVERY engine watcher over the 16-month data, grade each signal with FUTURES point-P&L
(MES proxy: SPY*10 ~= ES/MES index). Resumable + time-budgeted: each invocation grinds as many
days as fit in `budget` seconds, streams rows to a JSONL, and checkpoints to a state file, so it
can be driven to completion across many short calls. Same signals as the live engine.
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext
from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers
from futures.instruments import MES, MNQ
from futures.futures_sim import simulate_futures

DATA = REPO / "data"
EOD = dt.time(15, 55)

def _load():
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-05-22.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-22.csv")
    for df in (spy, vix):
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df.drop_duplicates("_ts", inplace=True); df.drop(columns=["_ts"], inplace=True)
    return spy.reset_index(drop=True), vix.reset_index(drop=True)

def run(start, end, inst, resume_after=None, budget_s=40.0, rows_path=None):
    t0 = time.time()
    spy_full, vix_full = _load()
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9,30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16,0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)
    day_groups = {d: g.reset_index(drop=True) for d, g in rth.groupby(rth["timestamp_et"].dt.date)}

    rows_f = open(rows_path, "a") if rows_path else None
    level_states = {}; ribbon_history = []; last_date = None
    lvl_cache = [None]; lvl_date = [None]

    for idx in range(len(rth)):
        bar = rth.iloc[idx]; bt = bar["timestamp_et"]; bd = bt.date()
        if start and bd < start: continue
        if end and bd > end: continue
        if resume_after is not None and bd <= resume_after: continue
        if bd != last_date:
            if last_date is not None and (time.time() - t0) > budget_s:
                if rows_f: rows_f.flush(); rows_f.close()
                return {"last_done": last_date, "reached_end": False}
            ribbon_history = []; level_states = {}; last_date = bd
        if idx < 60: continue
        try:
            r = ribbon_df.iloc[idx]
            rib = RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                              stack=str(r["stack"]), spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(rib); ribbon_history = ribbon_history[-10:]
        volb = vol_baseline_20bar(rth, idx); rngb = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx-3)]) if max(0, idx-3) < len(vix_aligned) else vix_now
        if bd != lvl_date[0]:
            lvl_cache[0] = _detect_from_history(spy_full[spy_full["timestamp_et"] <= bt], bd); lvl_date[0] = bd
        lset = lvl_cache[0]
        _update_level_states(level_states, lset.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        ctx = BarContext(bar_idx=idx, timestamp_et=bt.to_pydatetime(), bar=bar,
                         prior_bars=rth.iloc[:idx+1], ribbon_now=rib, ribbon_history=ribbon_history,
                         vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=volb, range_baseline_20=rngb,
                         levels_active=lset.active, multi_day_levels=lset.multi_day, htf_15m_stack=htf,
                         level_states=level_states)
        dbars = day_groups[bd]
        bidx = int((dbars["timestamp_et"] == bt).values.argmax())
        try:
            sigs = run_all_watchers(bar, dbars, bidx, volb, ctx, vix_now, multi_day_rth=None)
        except Exception:
            sigs = []
        if not sigs: continue
        fut = dbars[(dbars["timestamp_et"] > bt) & (dbars["timestamp_et"].dt.time <= EOD)]
        if fut.empty: continue
        for s in sigs:
            if s.direction not in ("long", "short"): continue
            res = simulate_futures(s.direction, s.entry_price, s.stop_price, s.tp1_price,
                                   s.runner_price, fut, inst, qty=3)
            if rows_f:
                rows_f.write(json.dumps({"date": str(bd), "watcher": s.watcher_name,
                    "setup": s.setup_name, "dir": s.direction, "conf": s.confidence,
                    "net": res["net"], "outcome": res["outcome"]}) + "\n")
    if rows_f: rows_f.flush(); rows_f.close()
    return {"last_done": last_date, "reached_end": True}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01"); ap.add_argument("--end", default="2026-05-22")
    ap.add_argument("--inst", default="MES"); ap.add_argument("--budget", type=float, default=40.0)
    ap.add_argument("--rows", default="/tmp/gb/fut_rows.jsonl")
    ap.add_argument("--state", default="/tmp/gb/fut_state.json")
    a = ap.parse_args()
    inst = {"MES": MES, "MNQ": MNQ}[a.inst]
    st = json.load(open(a.state)) if Path(a.state).exists() else {"last_done": None}
    resume_after = dt.date.fromisoformat(st["last_done"]) if st.get("last_done") else None
    r = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), inst,
            resume_after=resume_after, budget_s=a.budget, rows_path=a.rows)
    ld = r["last_done"] or st.get("last_done")
    Path(a.state).write_text(json.dumps({"last_done": str(ld) if ld else None, "reached_end": r["reached_end"]}))
    print(json.dumps({"last_done": str(ld) if ld else None, "reached_end": r["reached_end"]}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
