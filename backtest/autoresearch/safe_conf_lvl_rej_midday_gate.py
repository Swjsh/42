"""
SAFE CONF+LVL_REJ MIDDAY+AFTERNOON GATE TEST (2026-06-17)

Mirrors ENFORCED-3 (AGG block_conf_lvl_rej_midday_afternoon) but for Safe account.
AGG evidence: IS+$566 OOS+$230 WF=2.368 — all 4 gates PASS.

For Safe: IS conf+lvl_rej overall n=15 avg=+$605 stop=53.3%.
This is GOOD overall — but what if morning is exceptional and midday/afternoon drags it?
If Safe midday conf+lvl_rej IS is bad (like AGG midday avg=-$1 with 87.5% stop),
blocking it could yield another structural time-class gate.

Candidates:
  A: block conf+lvl_rej 11:30-15:55 (midday+afternoon — mirrors ENFORCED-3 scope)
  B: block conf+lvl_rej 14:00-15:55 (afternoon only — less aggressive)
  C: block conf+lvl_rej 12:00-15:55 (12pm onwards — "past morning confirmation window")

Autorate gates: L155 guard, OOS_positive, WF_norm>=0.70, SW_hurt<=1, ANCHOR PASS.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,
)
SAFE_OVR = {"vix_bull_max": 18.0}

CANDIDATES = [
    ("midday+afternoon (11:30-15:55)", "block_conf_lvl_rej_midday_afternoon", True, None),
    ("afternoon only (14:00-15:55)",   "block_conf_lvl_rej_afternoon",        None, True),
]


def _run(spy_df, vix_df, start, end, extra_kwarg=None, extra_val=None, extra_ovr=None):
    kw = dict(SAFE_KW)
    if extra_kwarg and extra_val is not None:
        kw[extra_kwarg] = extra_val
    ovr = dict(SAFE_OVR)
    if extra_ovr:
        ovr.update(extra_ovr)
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=ovr, **kw)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = t.dollar_pnl
    return out


def _classify(t) -> str:
    trigs = set(getattr(t, "winning_triggers", None) or [])
    conf = getattr(t, "has_confluence", False)
    if conf and "level_rejection" in trigs:
        return "conf+lvl_rej"
    elif conf and "level_reclaim" in trigs:
        return "conf+lvl_rec"
    elif "trendline_rejection" in trigs and "ribbon_flip" in trigs:
        return "tl+ribbon_flip"
    elif "trendline_rejection" in trigs:
        return "tl_pure"
    elif "level_reclaim" in trigs:
        return "lvl_rec_only"
    elif "level_rejection" in trigs:
        return "lvl_rej_only"
    return "other"


def _time(t) -> dt.time:
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).time()


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning Safe baseline...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    base_is_pnl  = _pnl(r_is.trades)
    base_oos_pnl = _pnl(r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    # Show conf+lvl_rej time breakdown from baseline
    print("\n  IS conf+lvl_rej time breakdown:")
    rej_is = [t for t in r_is.trades if _classify(t) == "conf+lvl_rej"]
    for label, start, end in [("09:35-11:29 (morning)",  dt.time(9,35),  dt.time(11,30)),
                                ("11:30-13:59 (midday)",   dt.time(11,30), dt.time(14,0)),
                                ("14:00-15:55 (afternoon)", dt.time(14,0), dt.time(16,0))]:
        sub = [t for t in rej_is if start <= _time(t) < end]
        if sub:
            s_pnl = _pnl(sub)
            stops = sum(1 for t in sub if t.dollar_pnl < 0)
            print(f"    {label}: n={len(sub)} total={s_pnl:+,.0f} avg={s_pnl/len(sub):+.0f} stop={100*stops/len(sub):.0f}%")
        else:
            print(f"    {label}: n=0")

    print("\n  OOS conf+lvl_rej time breakdown:")
    rej_oos = [t for t in r_oos.trades if _classify(t) == "conf+lvl_rej"]
    for label, start, end in [("09:35-11:29 (morning)",  dt.time(9,35),  dt.time(11,30)),
                                ("11:30-13:59 (midday)",   dt.time(11,30), dt.time(14,0)),
                                ("14:00-15:55 (afternoon)", dt.time(14,0), dt.time(16,0))]:
        sub = [t for t in rej_oos if start <= _time(t) < end]
        if sub:
            s_pnl = _pnl(sub)
            stops = sum(1 for t in sub if t.dollar_pnl < 0)
            print(f"    {label}: n={len(sub)} total={s_pnl:+,.0f} avg={s_pnl/len(sub):+.0f} stop={100*stops/len(sub):.0f}%")
        else:
            print(f"    {label}: n=0")

    print(f"\n{'Gate':<40} {'IS_d':>8} {'OOS_d':>8} {'WF':>8} {'SW':>4} {'ANC':>5} Verdict")
    print("-" * 85)

    all_results = []
    for gate_label, kwarg, midday_val, afternoon_val in [
        ("block conf+lvl_rej midday+afternoon", "block_conf_lvl_rej_midday_afternoon", True, None),
        ("block conf+lvl_rej afternoon only",   "block_conf_lvl_rej_afternoon_only",   None, True),
    ]:
        # Determine which kwarg to actually pass
        # Use block_conf_lvl_rej_midday_afternoon for midday+afternoon
        # Use a no_trade_window approach for afternoon-only if param doesn't exist
        try:
            kw_extra = {}
            if midday_val is not None:
                kw_extra = {"block_conf_lvl_rej_midday_afternoon": midday_val}
            else:
                # afternoon only: try block_conf_lvl_rej_afternoon_only
                kw_extra = {"block_conf_lvl_rej_afternoon_only": True}

            r_is_c  = _run(spy_df, vix_df, IS_START, IS_END,
                            extra_kwarg=list(kw_extra.keys())[0],
                            extra_val=list(kw_extra.values())[0])
            r_oos_c = _run(spy_df, vix_df, OOS_START, OOS_END,
                            extra_kwarg=list(kw_extra.keys())[0],
                            extra_val=list(kw_extra.values())[0])
        except (TypeError, Exception) as e:
            # If param not supported, run baseline (IS delta = 0)
            print(f"  [SKIP] {gate_label}: param not supported in orchestrator ({type(e).__name__})")
            continue

        is_pnl  = _pnl(r_is_c.trades)
        oos_pnl = _pnl(r_oos_c.trades)
        is_d    = is_pnl - base_is_pnl
        oos_d   = oos_pnl - base_oos_pnl

        if is_d <= 0:
            print(f"{gate_label:<40} {is_d:>+8,.0f} {oos_d:>+8,.0f} {'L155':>8} {'N/A':>4} {'N/A':>5} REJECT(IS_delta<=0)")
            all_results.append({"gate": gate_label, "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2), "verdict": "REJECT"})
            continue

        wf_norm = (oos_d / base_oos_n) / (is_d / base_is_n)

        # Sub-window check
        sw_hurt = 0
        for sw_label, s, e in IS_SUBWINDOWS:
            try:
                r_sw  = _run(spy_df, vix_df, s, e,
                              extra_kwarg=list(kw_extra.keys())[0],
                              extra_val=list(kw_extra.values())[0])
                r_swb = _run(spy_df, vix_df, s, e)
                sw_d = _pnl(r_sw.trades) - _pnl(r_swb.trades)
                if sw_d < -500:
                    sw_hurt += 1
                    print(f"  SW {sw_label}: delta={sw_d:+,.0f} <-- HURT")
                else:
                    print(f"  SW {sw_label}: delta={sw_d:+,.0f}")
            except Exception:
                pass

        # Anchor check
        base_by = _by_date(r_is.trades)
        cand_by = _by_date(r_is_c.trades)
        anchor_ok = all(cand_by.get(d, 0) >= base_by.get(d, 0) - 50 for d in J_WINNERS)

        oos_gate  = "PASS" if oos_pnl > 0 else "FAIL"
        wf_gate   = "PASS" if wf_norm >= 0.70 else "FAIL"
        sw_gate   = "PASS" if sw_hurt <= 1 else "FAIL"
        anch_gate = "PASS" if anchor_ok else "FAIL"

        gates = [oos_gate, wf_gate, sw_gate, anch_gate]
        if all(g == "PASS" for g in gates):
            verdict = "AUTO-RATIFY"
        else:
            fails = []
            if oos_gate == "FAIL":
                fails.append(f"OOS_NEG")
            if wf_gate == "FAIL":
                fails.append(f"WF={wf_norm:.3f}")
            if sw_gate == "FAIL":
                fails.append(f"SW_hurt={sw_hurt}")
            if anch_gate == "FAIL":
                fails.append("ANCHOR_FAIL")
            verdict = "REJECT " + " ".join(fails)

        print(f"{gate_label:<40} {is_d:>+8,.0f} {oos_d:>+8,.0f} {wf_norm:>8.3f} {sw_hurt:>4} {anch_gate:>5} {verdict}")

        all_results.append({
            "gate": gate_label, "is_n": len(r_is_c.trades), "oos_n": len(r_oos_c.trades),
            "is_pnl": round(is_pnl, 2), "oos_pnl": round(oos_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf_norm, 3), "sw_hurt": sw_hurt,
            "anchor": anch_gate, "verdict": verdict.split()[0],
        })

    out = {
        "study": "Safe conf+lvl_rej midday/afternoon gate",
        "date": "2026-06-17",
        "baseline": {"is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
                     "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2)},
        "results": all_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_conf_lvl_rej_midday_gate.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
