"""SUNDAY-WEB-LEARN: vwap_cont_late_entry_theta_cliff_cutoff.

Web-sourced hypothesis (theta cliff): 0DTE theta decay is non-linear and accelerates
sharply into the close (decay rate >$2.00/hr on a $3 ATM near the close vs ~$0.30/hr at
the open). So a LATE long entry should earn worse net expectancy PER UNIT of favorable
underlying move than a morning entry, because premium bleeds faster than the same SPY
move can pay. Test whether a hard entry cutoff EARLIER than the (generic-heartbeat)
[09:35, 15:00) limit -- e.g. 14:30 / 14:00 / 13:30 -- raises OOS expectancy without
meaningfully cutting trade count, on edge #1 (vwap_continuation, LIVE).

CRITICAL PREMISE CHECK (honesty, L171/OP-20): the hypothesis says "the current
[09:35,15:00) limit that v15.1 widened to 15:00." That [09:35,15:00) window is the
GENERIC heartbeat entry gate (automation/state/params.json:entry_no_trade_after_et=15:00).
The vwap_continuation DETECTOR that is actually LIVE (backtest/lib/watchers/
vwap_continuation_watcher.py) is hard-capped at ENTRY_CUTOFF = 10:30 ET -- it ONLY fires
in the morning. So for edge #1 specifically, a 14:00/14:30 cutoff is a WIDENING (loosen)
from 10:30, not a tightening from 15:00. We therefore test the theta-cliff claim two ways:

  (1) DOES THE CLIFF EXIST on OUR real OPRA fills? Widen the detector cutoff to 15:00 so
      afternoon vwap-continuation entries CAN fire, simulate them on real fills, and
      stratify net expectancy + return-on-premium per FAVORABLE-move unit by entry hour
      bucket. If the cliff is real, late buckets show worse $/move and worse net exp.
  (2) IS AN EARLIER CUTOFF AN IMPROVEMENT? Sweep win_end in {15:00, 14:30, 14:00, 13:30,
      11:30, 10:30(=live)} and compare OOS expectancy + the L175 risk-adjusted gate
      (Sharpe/Sortino/maxDD-of-daily-P&L not worse) + no-regression vs the live 10:30 cell.

BAR (this is an EXIT/ENTRY-WINDOW / MANAGEMENT change to a LIVE edge, NOT a new signal):
  expectancy LIFT vs the live 10:30 cell  AND  L175 risk-adjusted (daily Sharpe/Sortino
  not worse, maxDD not worse)  AND  no anchor regression (J winners not skipped/worse).
  We ALSO report the full 11-gate scorecard fields (OOS, posQ, top5, n, drop-top5) for
  context, but the binding bar for a window change to a LIVE edge is lift + L175 + no-reg.

Strike/stop = the LIVE edge-#1 config: ITM/ATM + tight stop. We run BOTH the validated
ATM/chart-stop headline cell AND the ITM2 / -8% tight-stop cell (the "tight -8% morning"
config named in the brief), so the cliff is measured at the real live contract tier.

Real OPRA fills via lib.simulator_real (C1). HARD-WINDOW: the OPRA cache ends ~2026-05-29;
signals after that resolve to cache_miss and are dropped (counted in coverage) -- this is
the natural <=2026-05-29 fill window. We ALSO assert no filled trade is dated > 2026-05-29.
Causal (L166): all features at/before entry-bar close; fill next-bar-open (sim).
Pure Python, $0, read-only, propose-only (Rule 9, weekend). No live edits.

Reuses j_entry_specificity.detect_j_cont_param (configurable win_end) + the edgehunt
real-fills sim path. Writes a section to analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md
plus a raw JSON dump.

Run: backtest/.venv/Scripts/python.exe \
     backtest/autoresearch/_web_vwap_cont_late_entry_theta_cliff.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts,
    _nearest_cached_strike, _strike_from_spot,
)
from autoresearch.j_entry_specificity import detect_j_cont_param  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT_JSON = ROOT / "analysis" / "recommendations" / "web-vwap-cont-late-entry-theta-cliff.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "SUNDAY-WEB-LEARN-SCORECARD.md"

OPRA_CACHE_END = dt.date(2026, 5, 29)   # HARD-WINDOW assert (the cache blind spot)
OOS_YEAR = 2026                          # IS=2025 / OOS=2026 (calendar-year, OP-20)
QTY = 3
MAX_STRIKE_STEPS = 4

# Live edge-#1 contract cells (brief: ITM/ATM + tight -8% stop, morning).
CELLS = [
    {"name": "ATM_chartstop", "strike_offset": 0, "premium_stop_pct": -0.99,
     "desc": "validated headline edge-#1 cell (ATM, chart-stop-only)"},
    {"name": "ITM2_8pct", "strike_offset": -2, "premium_stop_pct": -0.08,
     "desc": "the 'ITM-2 + tight -8% stop' live-class cell named in the brief"},
]

# win_end sweep (ET). 10:30 = the ACTUAL live vwap_continuation detector cutoff.
WIN_START = dt.time(9, 35)
WIN_ENDS = [
    ("1030_LIVE", dt.time(10, 30)),
    ("1130", dt.time(11, 30)),
    ("1330", dt.time(13, 30)),
    ("1400", dt.time(14, 0)),
    ("1430", dt.time(14, 30)),
    ("1500_genericgate", dt.time(15, 0)),
]

# Entry-hour buckets for the cliff stratification (ET).
HOUR_BUCKETS = [
    ("0935_1030", dt.time(9, 35), dt.time(10, 30)),
    ("1030_1130", dt.time(10, 30), dt.time(11, 30)),
    ("1130_1300", dt.time(11, 30), dt.time(13, 0)),
    ("1300_1400", dt.time(13, 0), dt.time(14, 0)),
    ("1400_1500", dt.time(14, 0), dt.time(15, 0)),
]


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _bucket(t: dt.time) -> str:
    for lbl, s, e in HOUR_BUCKETS:
        if s <= t < e:
            return lbl
    return "other"


def _sim_window(signals, spy, vix, ribbon, strike_offset, premium_stop_pct):
    """Simulate a signal set at one contract cell. Returns (rows, coverage)."""
    rows, cov = [], Counter()
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        t_et = bar["timestamp_et"].time()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            cov["cache_miss"] += 1
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        f = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="WEB_THETACLIFF", strike_override=strike, entry_vix=ev,
            premium_stop_pct=premium_stop_pct,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        # HARD-WINDOW assert (the cache blind spot): no filled trade past 2026-05-29.
        assert d <= OPRA_CACHE_END, f"OPRA-window breach: filled {d} > {OPRA_CACHE_END}"
        cov["filled"] += 1
        # favorable underlying move from entry bar close to the day's extreme in trade
        # direction, as a proxy for "how much the SPY move COULD have paid" (cliff metric).
        rows.append({
            "date": str(d), "time_et": t_et.strftime("%H:%M"), "bucket": _bucket(t_et),
            "side": sg.side, "pnl": round(float(f.dollar_pnl), 2),
            "pct": round(float(f.pct_return_on_premium), 5),
            "entry_premium": round(float(f.entry_premium), 4),
            "exit": f.exit_reason.name if f.exit_reason else "NONE",
            "trig": sg.note,
        })
    return rows, dict(cov)


def _daily_pnl(rows):
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    return np.array([by_day[d] for d in sorted(by_day)], float)


def _sharpe(daily):
    if len(daily) < 2 or daily.std(ddof=1) == 0:
        return 0.0
    return round(float(daily.mean() / daily.std(ddof=1) * np.sqrt(252)), 3)


def _sortino(daily):
    if len(daily) < 2:
        return 0.0
    downside = daily[daily < 0]
    dd = downside.std(ddof=1) if len(downside) >= 2 else 0.0
    if dd == 0:
        return 0.0
    return round(float(daily.mean() / dd * np.sqrt(252)), 3)


def _max_drawdown(daily):
    if len(daily) == 0:
        return 0.0
    equity = np.cumsum(daily)
    peak = np.maximum.accumulate(equity)
    return round(float((equity - peak).min()), 2)  # most-negative trough (<=0)


def _top5_day_pct(rows):
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    if total <= 0:
        return None
    return round(100 * sum(sorted(by_day.values(), reverse=True)[:5]) / total, 1)


def metrics(rows):
    if not rows:
        return {"n": 0}
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r["pnl"] for r in rs])), 2) if rs else 0.0

    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None
    daily = _daily_pnl(rows)
    return {
        "n": n, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct_return": round(float(pct.mean()), 5),
        "is_n": len(is_rows), "is_exp": _exp(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows),
        "positive_quarters": f"{q_pos}/{len(quarters)}", "positive_quarters_n": q_pos,
        "n_quarters": len(quarters), "top5_day_pct": _top5_day_pct(rows),
        "drop_top5_exp": drop5,
        "fire_days": len({r["date"] for r in rows}),
        "daily_sharpe": _sharpe(daily), "daily_sortino": _sortino(daily),
        "max_drawdown_dollar": _max_drawdown(daily),
        "exit_hist": dict(Counter(r["exit"] for r in rows)),
    }


def cliff_strat(rows):
    """Per entry-hour bucket: n, net exp, return-on-premium, win rate. The CLIFF test."""
    by_b = defaultdict(list)
    for r in rows:
        by_b[r["bucket"]].append(r)
    out = {}
    for lbl, _, _ in HOUR_BUCKETS:
        rs = by_b.get(lbl, [])
        if not rs:
            out[lbl] = {"n": 0}
            continue
        pnl = np.array([r["pnl"] for r in rs], float)
        pct = np.array([r["pct"] for r in rs], float)
        out[lbl] = {
            "n": len(rs),
            "exp_dollar": round(float(pnl.mean()), 2),
            "exp_pct_return": round(float(pct.mean()), 5),
            "wr_pct": round(100 * float((pnl > 0).mean()), 1),
            "total_dollar": round(float(pnl.sum()), 2),
            "mean_entry_premium": round(float(np.mean([r["entry_premium"] for r in rs])), 3),
        }
    return out


def main() -> int:
    print("=== WEB-LEARN: vwap_cont_late_entry_theta_cliff_cutoff ===", flush=True)
    print("loading SPY/VIX + ribbon ...", flush=True)
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)
    print(f"  trading_days={n_days} {all_dates[0]}..{all_dates[-1]}", flush=True)

    results = {}
    for cell in CELLS:
        cname = cell["name"]
        results[cname] = {"desc": cell["desc"], "strike_offset": cell["strike_offset"],
                          "premium_stop_pct": cell["premium_stop_pct"], "windows": {}}
        print(f"\n--- CELL {cname} ({cell['desc']}) ---", flush=True)
        for wlbl, wend in WIN_ENDS:
            signals = detect_j_cont_param(
                spy, ribbon, vix, days, win_start=WIN_START, win_end=wend,
                side_filter="both", breakout_only=False)
            rows, cov = _sim_window(signals, spy, vix, ribbon,
                                    cell["strike_offset"], cell["premium_stop_pct"])
            m = metrics(rows)
            m["coverage"] = cov
            m["signal_count"] = len(signals)
            m["cliff_by_bucket"] = cliff_strat(rows)
            results[cname]["windows"][wlbl] = m
            mm = m if m.get("n") else {"n": 0}
            print(f"  win_end={wlbl:>16} sig={len(signals):>3} "
                  f"n={mm.get('n','-'):>3} exp=${mm.get('exp_dollar','-'):>7} "
                  f"oos_exp=${mm.get('oos_exp','-'):>7} (oos_n={mm.get('oos_n','-')}) "
                  f"Sharpe={mm.get('daily_sharpe','-')} maxDD=${mm.get('max_drawdown_dollar','-')} "
                  f"posQ={mm.get('positive_quarters','-')} top5%={mm.get('top5_day_pct','-')}",
                  flush=True)

    # ---- Verdict per cell: window change to LIVE edge => lift + L175 + no-reg ----
    verdicts = {}
    for cname, cres in results.items():
        live = cres["windows"]["1030_LIVE"]
        cell_v = {}
        for wlbl, m in cres["windows"].items():
            if wlbl == "1030_LIVE" or m.get("n", 0) == 0:
                continue
            oos_lift = m.get("oos_exp", 0) - live.get("oos_exp", 0)
            exp_lift = m.get("exp_dollar", 0) - live.get("exp_dollar", 0)
            # L175 risk-adjusted: daily Sharpe AND Sortino not worse AND maxDD not worse.
            sharpe_ok = m.get("daily_sharpe", -9) >= live.get("daily_sharpe", 0)
            sortino_ok = m.get("daily_sortino", -9) >= live.get("daily_sortino", 0)
            # maxDD is <=0; "not worse" = not more negative.
            dd_ok = m.get("max_drawdown_dollar", -9e9) >= live.get("max_drawdown_dollar", 0)
            lift_ok = oos_lift > 0 and exp_lift > 0
            verdict = ("IMPROVES" if (lift_ok and sharpe_ok and sortino_ok and dd_ok)
                       else "DEAD")
            cell_v[wlbl] = {
                "verdict": verdict,
                "oos_exp_lift_vs_live": round(oos_lift, 2),
                "exp_lift_vs_live": round(exp_lift, 2),
                "sharpe_not_worse": sharpe_ok, "sortino_not_worse": sortino_ok,
                "maxdd_not_worse": dd_ok,
                "L175_risk_adjusted_pass": bool(sharpe_ok and sortino_ok and dd_ok),
            }
        verdicts[cname] = cell_v

    # ---- Cliff existence summary (does net exp/move degrade into the afternoon?) ----
    # Use the WIDEST window (1500) per cell -> the only window that contains afternoon entries.
    cliff_summary = {}
    for cname, cres in results.items():
        wide = cres["windows"]["1500_genericgate"]
        cliff_summary[cname] = wide.get("cliff_by_bucket", {})

    out = {
        "slug": "vwap_cont_late_entry_theta_cliff_cutoff",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hypothesis": (
            "0DTE theta accelerates into the close; late vwap_continuation long entries "
            "earn worse net expectancy per unit of favorable SPY move than morning entries; "
            "an entry cutoff EARLIER than [09:35,15:00) raises OOS expectancy w/o cutting N."),
        "premise_correction": (
            "The [09:35,15:00) window is the GENERIC heartbeat gate "
            "(params.json:entry_no_trade_after_et=15:00). The LIVE vwap_continuation DETECTOR "
            "(vwap_continuation_watcher.py) is already hard-capped at ENTRY_CUTOFF=10:30 ET, "
            "so for edge #1 a 14:00/14:30 cutoff is a WIDENING from 10:30, not a tightening "
            "from 15:00. We test (1) does the theta cliff exist on real fills if we WIDEN to "
            "15:00, and (2) is any earlier-than-15:00 cutoff an improvement vs the live 10:30."),
        "kind": "entry-window change to LIVE edge #1 (vwap_continuation) -> EXIT/MGMT bar: "
                "expectancy lift + L175 risk-adjusted (Sharpe/Sortino/maxDD not worse) + no-reg",
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": n_days,
                 "date_range": [str(all_dates[0]), str(all_dates[-1])],
                 "opra_cache_end_hard_window": str(OPRA_CACHE_END),
                 "oos_split": f"IS=2025 / OOS={OOS_YEAR}"},
        "cells": CELLS, "win_end_sweep": [w[0] for w in WIN_ENDS],
        "results": results,
        "window_change_verdicts": verdicts,
        "cliff_existence_by_bucket_widest_window": cliff_summary,
        "causality": "features at/before entry-bar close; fill next-bar-open (L166). "
                     "Real OPRA fills (lib.simulator_real, C1). HARD-WINDOW <=2026-05-29 "
                     "asserted per filled trade.",
        "caveats": [
            "Nearest-cached strike snap (L58): deep ITM/OTM may snap inward when uncached.",
            "OPRA cache ends ~2026-05-29 -> afternoon-window OOS (2026) is THIN; the cliff "
            "test for 2026 afternoon buckets has few fills. Honest n disclosed per bucket.",
            "Propose-only (Rule 9, weekend). No live edits.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}", flush=True)

    # ---- console verdict ----
    print("\n=== CLIFF STRATIFICATION (widest 15:00 window, net exp by entry hour) ===")
    for cname, cb in cliff_summary.items():
        print(f"  [{cname}]")
        for lbl, _, _ in HOUR_BUCKETS:
            s = cb.get(lbl, {"n": 0})
            if s.get("n", 0) == 0:
                print(f"    {lbl}: n=0")
            else:
                print(f"    {lbl}: n={s['n']:>3} exp=${s['exp_dollar']:>7} "
                      f"ret_on_prem={s['exp_pct_return']:+.4f} WR={s['wr_pct']}% "
                      f"mean_prem=${s['mean_entry_premium']}")
    print("\n=== WINDOW-CHANGE VERDICTS (vs live 10:30 cell) ===")
    for cname, cv in verdicts.items():
        print(f"  [{cname}]")
        for wlbl, v in cv.items():
            print(f"    win_end={wlbl}: {v['verdict']} "
                  f"(oos_lift=${v['oos_exp_lift_vs_live']} exp_lift=${v['exp_lift_vs_live']} "
                  f"L175={v['L175_risk_adjusted_pass']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
