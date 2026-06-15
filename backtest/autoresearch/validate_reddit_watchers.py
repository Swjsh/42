"""Stage-1 price-space scan + real-fills validation for the two Reddit-adopted setups:
ORB-15 (break & retest modes) and ERL->IRL. Mirrors watcher_replay context-building and
hs/nlwb real-fills harness. OP-16 anchor-day preservation reported.

Usage: python -m autoresearch.validate_reddit_watchers --start 2025-01-01 --end 2026-05-22 [--realfills]
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys
from collections import defaultdict
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(ROOT))

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext
from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import grade_observation
from lib.watchers.orb15_watcher import detect_orb15_break, _orb15_state
from lib.watchers.erl_irl_watcher import detect_erl_irl_setup

DATA = REPO / "data"
def _load_data(start, end):
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-05-22.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-22.csv")
    for df in (spy, vix):
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df.drop_duplicates("_ts", inplace=True)
        df.drop(columns=["_ts"], inplace=True)
    return spy.reset_index(drop=True), vix.reset_index(drop=True)

ANCHORS = {
    dt.date(2026,4,29):"WIN", dt.date(2026,5,1):"WIN", dt.date(2026,5,4):"WIN",
    dt.date(2026,5,5):"LOSS", dt.date(2026,5,6):"LOSS", dt.date(2026,5,7):"LOSS",
}
EOD = dt.time(15,50)

def _sig_to_obs(s):
    return {"direction":s.direction,"entry_price":s.entry_price,"stop_price":s.stop_price,
            "tp1_price":s.tp1_price,"runner_price":s.runner_price,"would_be_outcome":None}

def _grade(sig, rth, idx, bar_date):
    day = rth[(rth["timestamp_et"].dt.date==bar_date)]
    fut = day[(day["timestamp_et"]>rth.iloc[idx]["timestamp_et"]) & (day["timestamp_et"].dt.time<=EOD)]
    o = grade_observation(_sig_to_obs(sig), fut)
    return o.get("would_be_outcome"), float(o.get("would_be_pnl_dollars") or 0.0)

def _stats(rows):
    n=len(rows)
    if n==0: return {"n":0,"wr":0.0,"total_pnl":0.0,"exp":0.0}
    wins=sum(1 for r in rows if r["pnl"]>0); tot=sum(r["pnl"] for r in rows)
    return {"n":n,"wr":round(100*wins/n,1),"total_pnl":round(tot,2),"exp":round(tot/n,2)}

def run(start, end, do_realfills):
    spy_full, vix_full = _load_data(start, end)
    spy_full["timestamp_et"]=pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"]=spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time>=dt.time(9,30)) &
                   (spy_full["timestamp_et"].dt.time<dt.time(16,0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    streams = {"ORB15_break":[], "ORB15_retest":[], "ERL_IRL":[]}
    anchor_hits = defaultdict(list)
    realfills_inputs = {"ORB15_retest":[], "ERL_IRL":[]}

    # ---- Main loop: ERL (stateless) + ORB15-retest (global state, clear per day) ----
    level_states={}; ribbon_history=[]; last_date=None
    _lvl_cache=[None]; _lvl_date=[None]
    _day_groups={d:g.reset_index(drop=True) for d,g in rth.groupby(rth['timestamp_et'].dt.date)}
    _ts_to_gidx={t:i for i,t in enumerate(rth['timestamp_et'])}
    _orb15_state.clear()
    for idx in range(len(rth)):
        bar=rth.iloc[idx]; bar_time=bar["timestamp_et"]; bar_date=bar_time.date()
        if start and bar_date<start: continue
        if end and bar_date>end: continue
        if last_date is not None and bar_date!=last_date:
            ribbon_history=[]; level_states={}
        last_date=bar_date
        if idx<60: continue
        try:
            r=ribbon_df.iloc[idx]
            ribbon_state=RibbonState(fast=float(r["fast"]),pivot=float(r["pivot"]),slow=float(r["slow"]),
                                     stack=str(r["stack"]),spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state); ribbon_history=ribbon_history[-10:]
        vol_baseline=vol_baseline_20bar(rth,idx); range_baseline=range_baseline_20bar(rth,idx)
        vix_now=float(vix_aligned.iloc[idx]) if idx<len(vix_aligned) else 17.0
        vix_prior=float(vix_aligned.iloc[max(0,idx-3)]) if max(0,idx-3)<len(vix_aligned) else vix_now
        if bar_date!=_lvl_date[0]:
            full_history=spy_full[spy_full["timestamp_et"]<=bar_time]
            _lvl_cache[0]=_detect_from_history(full_history,bar_date); _lvl_date[0]=bar_date
        level_set=_lvl_cache[0]
        _update_level_states(level_states,level_set.active,bar,idx)
        htf=htf_stacks[idx] if idx<len(htf_stacks) else None
        ctx=BarContext(bar_idx=idx,timestamp_et=bar_time.to_pydatetime(),bar=bar,
                       prior_bars=rth.iloc[:idx+1],ribbon_now=ribbon_state,ribbon_history=ribbon_history,
                       vix_now=vix_now,vix_prior=vix_prior,vol_baseline_20=vol_baseline,
                       range_baseline_20=range_baseline,levels_active=level_set.active,
                       multi_day_levels=level_set.multi_day,htf_15m_stack=htf,level_states=level_states)
        day_bars=_day_groups[bar_date]
        bidx=int((day_bars["timestamp_et"]==bar_time).values.argmax())
        # ERL->IRL
        erl=detect_erl_irl_setup(ctx)
        if erl is not None:
            out,pnl=_grade(erl,rth,idx,bar_date)
            streams["ERL_IRL"].append({"date":str(bar_date),"conf":erl.confidence,"dir":erl.direction,"out":out,"pnl":pnl,"vix":round(vix_now,1)})
            if bar_date in ANCHORS: anchor_hits[bar_date].append(("ERL_IRL",erl.direction,erl.confidence))
            realfills_inputs["ERL_IRL"].append((idx,bar,erl))
        # ORB15 retest
        o15=detect_orb15_break(bar,day_bars,bidx,vol_baseline,entry_mode="retest")
        if o15 is not None:
            out,pnl=_grade(o15,rth,idx,bar_date)
            streams["ORB15_retest"].append({"date":str(bar_date),"conf":o15.confidence,"out":out,"pnl":pnl,"vix":round(vix_now,1)})
            if bar_date in ANCHORS: anchor_hits[bar_date].append(("ORB15_retest",o15.direction,o15.confidence))
            realfills_inputs["ORB15_retest"].append((idx,bar,o15))

    # ---- Fast secondary loop: ORB15-break (no levels needed) ----
    _orb15_state.clear()
    for bar_date,day in rth.groupby(rth["timestamp_et"].dt.date):
        if start and bar_date<start: continue
        if end and bar_date>end: continue
        day_bars=day.reset_index(drop=True)
        for j in range(len(day_bars)):
            b=day_bars.iloc[j]
            sig=detect_orb15_break(b,day_bars,j,float(day_bars["volume"].iloc[max(0,j-20):j].mean() or 0),entry_mode="break")
            if sig is not None:
                gidx=_ts_to_gidx[b["timestamp_et"]]
                out,pnl=_grade(sig,rth,gidx,bar_date)
                streams["ORB15_break"].append({"date":str(bar_date),"conf":sig.confidence,"out":out,"pnl":pnl})
                if bar_date in ANCHORS: anchor_hits[bar_date].append(("ORB15_break",sig.direction,sig.confidence))

    result={"window":f"{start}..{end}","streams":{k:_stats(v) for k,v in streams.items()},
            "streams_raw":streams,
            "anchor_days":{str(d):{"label":ANCHORS[d],"fires":anchor_hits.get(d,[])} for d in sorted(ANCHORS)}}

    # ---- Real-fills (optional) ----
    if do_realfills:
        from lib.simulator_real import simulate_trade_real
        rf={}
        for stream,inputs in realfills_inputs.items():
            for label,offset in (("ATM",0),("ITM2",-2)):
                rows=[]
                for (idx,bar,sig) in inputs[:80]:
                    side="C" if sig.direction=="long" else "P"
                    rej=sig.metadata.get("swept_level") or sig.metadata.get("or_high") or sig.stop_price
                    try:
                        fill=simulate_trade_real(entry_bar_idx=idx,entry_bar=bar,spy_df=rth,ribbon_df=ribbon_df,
                            rejection_level=float(rej),triggers_fired=sig.triggers_fired,side=side,qty=3,
                            setup=sig.setup_name,premium_stop_pct=-0.99,strike_offset=offset)
                    except Exception as e:
                        fill=None
                    if fill is not None and getattr(fill,"dollar_pnl",None) is not None:
                        rows.append({"pnl":float(fill.dollar_pnl)})
                if stream=="ORB15_retest" and label=="ITM2": continue  # ORB long uses ATM/OTM, ITM2 not the design
                rf[f"{stream}_{label}"]=_stats(rows)
        result["real_fills"]=rf
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",default="2025-01-01"); ap.add_argument("--end",default="2026-05-22")
    ap.add_argument("--realfills",action="store_true")
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    res=run(dt.date.fromisoformat(a.start),dt.date.fromisoformat(a.end),a.realfills)
    print(json.dumps(res,indent=2,default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(res,indent=2,default=str)); print("wrote",a.out)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
