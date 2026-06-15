"""SNIPER-ENTRY experiment harness — Project Gamma.

GOAL (J directive 2026-05-31): the missed week lost because entries were too far
from the move, so a normal retest tripped the stop before the EMA-ribbon ride began.
Test ENTRY-TIMING variants (get closer to the move WITHOUT being too late) against
REAL option fills, per day. Co-sweep the stop. Target: every missed day profitable
per-contract, WITHOUT regressing the J-edge anchors.

This reuses production primitives (compute_ribbon + simulate_trade_real + real OPRA
fills) so results are faithful (no engine drift). It only VARIES the entry bar index
and the stop — exactly the levers under study. Engine-benefit R&D (OP-22): writes only
to analysis/. Never touches params/heartbeat/orders.

Entry variants (relative to the production trigger bar T; production fills at T+1):
  V0_baseline      enter T+1 (production)
  V_mom_gate       enter T+1 only if trigger bar T had vol>=1.3x & body>=0.5 in-dir (skip weak reclaims)
  V_confirm1       enter T+2 only if bar T+1 closed in-dir AND held past the level (1-bar confirmation)
  V_confirm2       enter T+3 only if bars T+1,T+2 both held in-dir past the level
  V_pullback       after T, wait up to 6 bars for price to pull back to level+/-0.20, enter on the bounce bar
  V_ribbon_prox    enter T+1 only if entry spot within $0.35 of the fast EMA (not extended)
  V_mom_and_prox   V_mom_gate AND V_ribbon_prox (both conditions)

Stops (premium_stop_pct): 0.08, 0.15, 0.20, 0.95(=chart-stop-dominant; level stop $0.50 governs)
Strikes: ATM (offset 0, SAFE) and ITM-2 (offset 2, BOLD) — for calls, ITM = strike below spot.

Usage:
    python tools/entry_experiment.py                 # missed week, full matrix
    python tools/entry_experiment.py --anchors       # also run J-edge anchor non-regression
"""
from __future__ import annotations
import argparse
import sys
import json
import datetime as dt
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

ANALYSIS = REPO.parent / "analysis" / "backtests"
DATA = REPO / "data"
MISSED = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]

PL = dict(profit_lock_mode="trailing", profit_lock_threshold_pct=0.05, profit_lock_trail_pct=0.20)


def load_spy_rth(spy_csv: Path):
    spy = pd.read_csv(spy_csv)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30)) &
              (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["vol_avg20"] = rth["volume"].rolling(20, min_periods=5).mean()
    ribbon = compute_ribbon(rth["close"])
    return rth, ribbon


def signals_from_trades(trades_csv: Path, side_filter: str, date_filter):
    """Each production entry -> a signal (date, fill_idx-resolvable time, level, side)."""
    df = pd.read_csv(trades_csv)
    df["date"] = df["date"].astype(str)
    out = []
    for _, r in df.iterrows():
        if str(r["c_or_p"]) != side_filter:
            continue
        if date_filter and r["date"] not in date_filter:
            continue
        lvl = r.get("rejection_level", "")
        try:
            lvl = float(lvl)
        except (TypeError, ValueError):
            lvl = None
        out.append({"date": r["date"], "fill_time": str(r["time_entry"]),
                    "side": str(r["c_or_p"]), "level": lvl,
                    "setup": str(r.get("setup", ""))})
    return out


def fill_idx_for(rth, date_str, fill_time):
    t = dt.time.fromisoformat(fill_time if len(fill_time) > 5 else fill_time + ":00")
    m = rth[(rth["timestamp_et"].dt.date.astype(str) == date_str) &
            (rth["timestamp_et"].dt.time == t)]
    if len(m) == 0:
        return None
    return int(m.index[0])


def bar_dir_ok(rth, idx, side):
    if idx < 0 or idx >= len(rth):
        return False
    b = rth.iloc[idx]
    return (b["close"] > b["open"]) if side == "C" else (b["close"] < b["open"])


def held_past_level(rth, idx, side, level):
    if level is None or idx < 0 or idx >= len(rth):
        return True
    c = float(rth.iloc[idx]["close"])
    return c > level if side == "C" else c < level


def vol_body_ok(rth, idx, side, vmult=1.3, bodymin=0.5):
    if idx < 0 or idx >= len(rth):
        return False
    b = rth.iloc[idx]
    v20 = b["vol_avg20"]
    if not v20 or b["volume"] < vmult * v20:
        return False
    rng = b["high"] - b["low"]
    if rng <= 0:
        return False
    body = abs(b["close"] - b["open"]) / rng
    if body < bodymin:
        return False
    return (b["close"] > b["open"]) if side == "C" else (b["close"] < b["open"])


def near_fast_ema(rth, ribbon, idx, tol=0.35):
    if idx < 0 or idx >= len(ribbon):
        return False
    st = ribbon.iloc[idx]
    if pd.isna(st.get("fast")):
        return False
    return abs(float(rth.iloc[idx]["close"]) - float(st["fast"])) <= tol


# ---- entry variants: return trigger_idx (sim fills at +1) or None to skip ----
def variants(rth, ribbon, fill_idx, side, level):
    T = fill_idx - 1  # production trigger bar
    out = {}
    out["V0_baseline"] = T
    out["V_mom_gate"] = T if vol_body_ok(rth, T, side) else None
    # confirm1: fill bar (T+1) held in-dir past level -> enter next (trigger=T+1, fill T+2)
    out["V_confirm1"] = (fill_idx if (bar_dir_ok(rth, fill_idx, side) and held_past_level(rth, fill_idx, side, level)) else None)
    out["V_confirm2"] = (fill_idx + 1 if (bar_dir_ok(rth, fill_idx, side) and bar_dir_ok(rth, fill_idx + 1, side)
                         and held_past_level(rth, fill_idx + 1, side, level)) else None)
    # pullback: scan T..T+6 for a bar that pulls back to the level, enter the bounce after it
    pb = None
    if level is not None:
        for k in range(fill_idx, min(fill_idx + 7, len(rth))):
            b = rth.iloc[k]
            touched = (b["low"] <= level + 0.20) if side == "C" else (b["high"] >= level - 0.20)
            if touched and k + 1 < len(rth):
                pb = k  # trigger = pullback bar, fill = bounce bar k+1
                break
    out["V_pullback"] = pb
    out["V_ribbon_prox"] = T if near_fast_ema(rth, ribbon, T) else None
    out["V_mom_and_prox"] = T if (vol_body_ok(rth, T, side) and near_fast_ema(rth, ribbon, T)) else None
    return out


def sim_one(rth, ribbon, trig_idx, side, level, strike_offset, stop_pct, qty=3):
    if trig_idx is None or trig_idx < 1 or trig_idx + 2 >= len(rth):
        return None
    row = rth.iloc[trig_idx]
    try:
        fill = simulate_trade_real(
            entry_bar_idx=trig_idx, entry_bar=row, spy_df=rth, ribbon_df=ribbon,
            rejection_level=level, triggers_fired=["level_reclaim", "confluence"],
            side=side, qty=qty, setup="BULLISH_RECLAIM_RIDE_THE_RIBBON" if side == "C" else "BEARISH_REJECTION_RIDE_THE_RIBBON",
            levels_active=[level] if level is not None else [],
            use_tiered_exits=True, strike_offset=strike_offset,
            premium_stop_pct=-abs(stop_pct), **PL,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    if fill is None:
        return None
    return fill


def per_contract(fill, qty=3):
    return fill.dollar_pnl / qty if fill and hasattr(fill, "dollar_pnl") else None


def run(spy_csv, dates, side, label, out_lines, signal_csv=None):
    rth, ribbon = load_spy_rth(spy_csv)
    # signal universe defaults to BOLD entries (most permissive trigger); override for anchors
    if signal_csv is None:
        bold = ANALYSIS / "missed_week_bold" / "trades.csv"
        safe = ANALYSIS / "missed_week_safe" / "trades.csv"
        signal_csv = bold if bold.exists() else safe
    sigs = signals_from_trades(signal_csv, side, set(dates))
    # resolve fill indices
    resolved = []
    for s in sigs:
        fi = fill_idx_for(rth, s["date"], s["fill_time"])
        if fi is not None:
            s["fill_idx"] = fi
            resolved.append(s)
    out_lines.append(f"## {label}: {len(resolved)} signals (side {side}) across {dates[0]}..{dates[-1]}")
    out_lines.append("")

    # ---- Section 1: baseline per-entry trace (the 'review every entry/exit') ----
    out_lines.append("### Baseline per-entry trace (ATM, -8% stop) — are we too early?")
    out_lines.append("| date | trig fill | entry$ | pnl/contract | MFE$ | bars→MFE | MAE$ | stopped_before_MFE | exit |")
    out_lines.append("|---|---|---|---|---|---|---|---|---|")
    for s in resolved:
        fill = sim_one(rth, ribbon, s["fill_idx"] - 1, side, s["level"], 0, 0.08)
        if not fill or isinstance(fill, dict):
            out_lines.append(f"| {s['date']} | {s['fill_time'][:5]} | — | nodata/{fill} | | | | | |")
            continue
        pc = per_contract(fill)
        # bars to MFE
        mfe = fill.max_favorable_premium
        mae = fill.max_adverse_premium
        ep = fill.entry_premium
        # rough: did stop hit (negative) while MFE showed a real run (>+20%)?
        stopped_before = (pc is not None and pc < 0 and mfe >= ep * 1.20)
        out_lines.append(f"| {s['date']} | {s['fill_time'][:5]} | {ep:.2f} | {pc:+.1f} | "
                         f"{mfe:.2f} | {fill.bars_held} | {mae:.2f} | {stopped_before} | "
                         f"{fill.exit_reason.value if fill.exit_reason else '?'} |")
    out_lines.append("")

    # ---- Section 2/3: entry-variant matrix at two profiles ----
    profiles = [("ATM stop-8%", 0, 0.08), ("ITM2 stop-15%", 2, 0.15),
                ("ATM chart-stop", 0, 0.95), ("ITM2 chart-stop", 2, 0.95)]
    variant_names = ["V0_baseline", "V_mom_gate", "V_confirm1", "V_confirm2",
                     "V_pullback", "V_ribbon_prox", "V_mom_and_prox"]
    results = {}
    for pname, off, stop in profiles:
        out_lines.append(f"### Entry-variant matrix — {pname} (per-contract $, by day)")
        out_lines.append("| variant | " + " | ".join(dates) + " | TOTAL | days+ | n |")
        out_lines.append("|" + "---|" * (len(dates) + 4))
        for vn in variant_names:
            per_day = {d: 0.0 for d in dates}
            cnt = {d: 0 for d in dates}
            n = 0
            for s in resolved:
                vv = variants(rth, ribbon, s["fill_idx"], side, s["level"])
                trig = vv.get(vn)
                if trig is None:
                    continue
                fill = sim_one(rth, ribbon, trig, side, s["level"], off, stop)
                if not fill or isinstance(fill, dict):
                    continue
                pc = per_contract(fill)
                if pc is None:
                    continue
                per_day[s["date"]] += pc
                cnt[s["date"]] += 1
                n += 1
            tot = sum(per_day.values())
            daysplus = sum(1 for d in dates if per_day[d] > 0)
            results[(pname, vn)] = {"per_day": per_day, "total": tot, "days_plus": daysplus, "n": n}
            cells = " | ".join(f"{per_day[d]:+.1f}" for d in dates)
            out_lines.append(f"| {vn} | {cells} | {tot:+.1f} | {daysplus}/{len(dates)} | {n} |")
        out_lines.append("")

    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors", action="store_true")
    args = ap.parse_args(argv)

    spy_csv = DATA / "spy_5m_2026-05-19_2026-05-29.csv"
    out = ["# SNIPER-ENTRY EXPERIMENT — missed week 2026-05-26..29",
           "_Real OPRA fills. Reuses production compute_ribbon + simulate_trade_real (no engine drift). "
           "Per-contract P&L (qty=3, /3). Trailing profit-lock engaged. Generated by entry_experiment.py._", ""]
    res = run(spy_csv, MISSED, "C", "MISSED WEEK (BULLISH_RECLAIM calls)", out)

    # verdict: which (profile, variant) makes the most days green, then highest total
    ranked = sorted(res.items(), key=lambda kv: (kv[1]["days_plus"], kv[1]["total"]), reverse=True)
    out.append("## VERDICT — ranked by (days-profitable, then total per-contract)")
    out.append("| rank | profile | variant | days+ | total/contract | n |")
    out.append("|---|---|---|---|---|---|")
    for i, ((p, v), r) in enumerate(ranked[:12], 1):
        out.append(f"| {i} | {p} | {v} | {r['days_plus']}/4 | {r['total']:+.1f} | {r['n']} |")
    out.append("")
    best = ranked[0]
    out.append(f"**Top combo: {best[0][1]} @ {best[0][0]} -> {best[1]['days_plus']}/4 days green, "
               f"{best[1]['total']:+.1f}/contract (n={best[1]['n']}).**")
    out.append("Overfitting caveat: 4 days, 8 signals. A winner here is a HYPOTHESIS, not proof — "
               "must hold on the J-anchor window + an OOS month before any ratification (Rule 9 / OP-16).")

    # ---- J-ANCHOR NON-REGRESSION: same variant matrix on the anchor window ----
    if args.anchors:
        anchor_spy = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
        anchor_dates = ["2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01", "2026-05-04", "2026-05-07"]
        anchor_src = ANALYSIS / "jedge_nonreg_nofilter8_2026-05-31" / "trades.csv"
        if anchor_spy.exists() and anchor_src.exists():
            out.append("")
            out.append("---")
            out.append("# J-ANCHOR NON-REGRESSION (does V_pullback+chart-stop keep the anchors?)")
            out.append("_Bear puts dominate this window. We want the winning missed-week combo to "
                       "NOT destroy 5/04 721P (+$804) and the other J winners._")
            out.append("")
            ares = run(anchor_spy, anchor_dates, "P", "J-ANCHORS (BEARISH_REJECTION puts)",
                       out, signal_csv=anchor_src)
            # report the same combos that won the missed week, on anchors
            out.append("## Cross-check: missed-week-winning combos, on the anchor window")
            out.append("| profile | variant | anchor days+ | anchor total/c | anchor n |")
            out.append("|---|---|---|---|---|")
            for (p, v), r in ranked[:6]:
                ar = ares.get((p, v))
                if ar:
                    out.append(f"| {p} | {v} | {ar['days_plus']}/{len(anchor_dates)} | "
                               f"{ar['total']:+.1f} | {ar['n']} |")
            out.append("")
            out.append("**Read:** a combo that wins the missed week AND stays non-negative on the "
                       "anchor window is a real candidate. One that wins the week but craters the "
                       "anchors is overfit — reject (OP-16 edge-capture floor).")

    outpath = REPO.parent / "analysis" / "sniper-entry-experiment-2026-05-31.md"
    outpath.write_text("\n".join(out), encoding="utf-8")
    (ANALYSIS / "_sniper_results.json").write_text(
        json.dumps({f"{p}||{v}": r for (p, v), r in res.items()}, indent=2, default=str))
    print("wrote", outpath)
    print("wrote", ANALYSIS / "_sniper_results.json")
    print("TOP:", best[0], best[1]["days_plus"], "/4 days,", round(best[1]["total"], 1), "/contract")


if __name__ == "__main__":
    raise SystemExit(main())
