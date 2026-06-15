"""ONE script, ONE call, FAST: OOS + stop-PL-candidate + anchor-gate.

SPEED FIX (prior version timed out): the entry TRIGGER set is essentially stop/PL/strike-
independent (those only change the EXIT sim). So we derive each day's signals ONCE with a
single run_backtest, then re-sim the whole (stop x PL x strike) grid via simulate_trade_real
directly — which just walks cached option bars (~100x cheaper than a full backtest). This turns
~hundreds of engine runs into ~30 engine runs + cheap re-sims.

Cascade-proof (single call), each stage try/wrapped, JSON dumps (L77 structural). Real fills.
"""
from __future__ import annotations
import sys, json, datetime as dt, traceback
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"
PL_OFF, PL_ON = SM.PL_OFF, SM.PL_ON
MDATES = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]
log = []
def LG(s): log.append(str(s)); _flush()
def _flush(): (DATA / "_run_all_sniper.log").write_text("\n".join(log), encoding="utf-8")


def oos_setup():
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    oos = [d for d in fill_days if d in spy_dates and d not in set(MDATES)]
    # Cap to the most recent 60 cached-fill days for tractable runtime (each day = 1
    # run_backtest for signal derivation). 60 days is ample for a walk-forward; the
    # wider-span re-run is a separately-queued data cook.
    oos = sorted(oos)[-60:]
    return master, oos


def signals_once(spy_str, vix_str, dates):
    """ONE run_backtest over the FULL [min,max] span (orchestrator handles multi-day in a
    single pass — same as run.py). ~1 engine run instead of len(dates). Filter to the target
    date set. Cached signal set reused across the whole stop/PL/strike grid."""
    if not dates:
        return []
    dset = set(dates)
    out = []
    try:
        r = SM.run_backtest(spy_str, vix_str, start_date=min(dates), end_date=max(dates),
                            use_real_fills=True, premium_stop_pct=-0.20, strike_offset=0,
                            min_triggers_bull=1, no_trade_before=dt.time(9, 35), **PL_OFF)
        for t in r.trades:
            d = t.entry_time_et.date()
            if d in dset:
                out.append({"fill_dt": t.entry_time_et, "side": "C" if "BULLISH" in t.setup else "P",
                            "level": t.rejection_level, "date": d})
    except Exception:
        import traceback as _tb
        LG(f"  signals_once ERROR:\n{_tb.format_exc()[-400:]}")
    return out


def resim_v0(rth, ribbon, sigs, dates, stop, pl, soff=0):
    pc_ = {d: 0.0 for d in dates}; worst = 0.0; n = 0; cap = {}
    for s in sigs:
        fi = SM.fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue
        f = SM.sim(rth, ribbon, fi - 1, s["side"], s["level"], soff, stop, pl)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pc_[s["date"]] += pcv; worst = min(worst, pcv); n += 1
        if f.dollar_pnl > 0:
            cap.setdefault(s["date"], round(pcv, 1))
    return {"green": sum(1 for d in dates if pc_[d] > 0),
            "days_traded": len([d for d in dates if pc_[d] != 0]),
            "totpc": round(sum(pc_.values()), 1), "n": n, "worst_pc": round(worst, 1), "cap": cap}


def resim_d1(rth, ribbon, sigs, dates, window, prox, stop, soff=0):
    pc_ = {d: 0.0 for d in dates}; worst = 0.0; n = 0
    for s in sigs:
        fi = SM.fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue
        trig = None
        if s["level"] is not None:
            tol = max(prox * SM.atr5(rth, fi), 0.05)
            for R in range(fi, min(fi + window + 1, len(rth) - 1)):
                b = rth.iloc[R]
                if s["side"] == "C" and b["low"] <= s["level"] + tol and b["close"] > s["level"] and b["close"] > b["open"]:
                    trig = R; break
                if s["side"] == "P" and b["high"] >= s["level"] - tol and b["close"] < s["level"] and b["close"] < b["open"]:
                    trig = R; break
        f = SM.sim(rth, ribbon, trig, s["side"], s["level"], soff, stop, PL_OFF)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pc_[s["date"]] += pcv; worst = min(worst, pcv); n += 1
    return {"green": sum(1 for d in dates if pc_[d] > 0),
            "days_traded": len([d for d in dates if pc_[d] != 0]),
            "totpc": round(sum(pc_.values()), 1), "n": n, "worst_pc": round(worst, 1)}


def main():
    master, oos = oos_setup()
    LG(f"OOS master={master.name} days={len(oos)} ({oos[0] if oos else '-'}..{oos[-1] if oos else '-'})")
    ospy = SM.norm_str(pd.read_csv(master)); ovix = SM.norm_str(pd.read_csv(DATA / master.name.replace("spy_5m", "vix_5m")))
    orth, oribbon = SM.load_rth(master)
    mspy = SM.norm_str(pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv"))
    mvix = SM.norm_str(pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv"))
    mrth, mribbon = SM.load_rth(DATA / "spy_5m_2026-05-19_2026-05-29.csv")

    LG("deriving signals ONCE per window...")
    oos_sigs = signals_once(ospy, ovix, oos)
    m_sigs = signals_once(mspy, mvix, MDATES)
    LG(f"  OOS signals={len(oos_sigs)} | missed signals={len(m_sigs)}")

    # STAGE 1: OOS V0@-8, V0@-50, D1@-20  (re-sim on cached signal set)
    try:
        res = {"oos_days": len(oos), "signals": len(oos_sigs)}
        res["V0_8"] = resim_v0(orth, oribbon, oos_sigs, oos, 0.08, PL_OFF)
        res["V0_50"] = resim_v0(orth, oribbon, oos_sigs, oos, 0.50, PL_OFF)
        res["D1_20"] = resim_d1(orth, oribbon, oos_sigs, oos, 4, 0.10, 0.20)
        # stringify any date-keyed cap dicts (json can't use date keys)
        for kk in ("V0_8", "V0_50"):
            if "cap" in res[kk]:
                res[kk]["cap"] = {str(d): v for d, v in res[kk]["cap"].items()}
        (ABT / "_sniper_oos.json").write_text(json.dumps(res, indent=2, default=str))
        LG(f"  OOS: V0_8 {res['V0_8']['totpc']}/c({res['V0_8']['green']}g) | "
           f"V0_50 {res['V0_50']['totpc']}/c({res['V0_50']['green']}g) | D1_20 {res['D1_20']['totpc']}/c({res['D1_20']['green']}g)")
    except Exception:
        LG(f"  OOS ERROR:\n{traceback.format_exc()[-500:]}")

    # STAGE 2: stop x PL on production entry (missed + OOS) — re-sim cached signals
    try:
        rows = []
        for stop in [0.08, 0.12, 0.15, 0.20, 0.25, 0.30]:
            for plname, pl in [("PLoff", PL_OFF), ("PLon", PL_ON)]:
                mr = resim_v0(mrth, mribbon, m_sigs, MDATES, stop, pl)
                orr = resim_v0(orth, oribbon, oos_sigs, oos, stop, pl)
                for rr in (mr, orr):
                    if "cap" in rr:
                        rr["cap"] = {str(d): v for d, v in rr["cap"].items()}
                rows.append({"stop": stop, "pl": plname, "missed": mr, "oos": orr})
        (ABT / "_stop_pl_candidate.json").write_text(json.dumps({"rows": rows, "oos_days": len(oos)}, indent=2, default=str))
        LG(f"  STOP_PL: {len(rows)} rows written")
    except Exception:
        LG(f"  STOP_PL ERROR:\n{traceback.format_exc()[-500:]}")

    # STAGE 3: anchor gate (bear-put book, production entry wider stop) — re-sim cached signals
    try:
        aspy_p = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
        aspy = SM.norm_str(pd.read_csv(aspy_p)); avix = SM.norm_str(pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-07.csv"))
        arth, aribbon = SM.load_rth(aspy_p)
        ad0, ad1 = dt.date(2026, 4, 27), dt.date(2026, 5, 7)
        adates = [ad0 + dt.timedelta(days=k) for k in range((ad1 - ad0).days + 1)]
        a_sigs = [s for s in signals_once(aspy, avix, adates) if s["side"] == "P"]
        LG(f"  anchor put-signals={len(a_sigs)}")
        res = {}
        for stop in [0.08, 0.15, 0.20, 0.30]:
            for plname, pl in [("PLoff", PL_OFF), ("PLon", PL_ON)]:
                r = resim_v0(arth, aribbon, a_sigs, adates, stop, pl)
                res[f"-{int(stop*100)}%/{plname}"] = {"cap_504": r["cap"].get(dt.date(2026, 5, 4)),
                                                       "totpc": r["totpc"], "worst_pc": r["worst_pc"], "n": r["n"]}
        (ABT / "_anchor_v0.json").write_text(json.dumps(res, indent=2, default=str))
        LG(f"  ANCHOR: {len(res)} configs written")
    except Exception:
        LG(f"  ANCHOR ERROR:\n{traceback.format_exc()[-500:]}")

    LG("ALL DONE")
    print("ALL DONE")


if __name__ == "__main__":
    raise SystemExit(main())
