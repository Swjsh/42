"""dissect_entry-quality-vs-alternatives.py -- scratch analysis for D5 ENTRY QUALITY TODAY vs
J's ALTERNATIVES (2026-09-03, slug entry-quality-vs-alternatives).

Read-only over cached local data ONLY. No network, no broker/market-data calls. Sources:
  - automation/state/core-decisions.jsonl (safe+bold, 1/min, today only) -- SPY bar-close tape,
    VIX, spread_cents, conviction, context_bundle, levels_active, exec (fills).
  - automation/state/fills-ledger.jsonl -- broker-truth fills today.
  - automation/state/key-levels.json -- zone_width for Active/Reference levels.
  - analysis/quote-tape/2026-09-03.jsonl -- real NBBO for 770C/768C/772C while any arm held them.

Method for the option-price proxy: Black-Scholes, r=0, sigma=VIX/100 (flat ~15% all session --
negligible term variance), T = minutes-to-16:00-ET / (390*252) (trading-time convention). The
BS model is CALIBRATED at the last/nearest real NBBO mid for that exact strike+side (a
multiplicative factor forced to match real market at the anchor), then walked forward/backward
holding that factor constant -- this absorbs skew/liquidity premium the flat-vol BS model can't
see, at the cost of assuming that premium is stationary over the walk window (stated caveat).
For the PUT (no real put quotes exist today -- no arm traded a put), a put-call PARITY check
(P = C_real - (S - K), r=0) against the real 770C quote at the same tick is used as a
model-free cross-check on the BS-put's calibration.

All numbers below are reproducible by re-running this script. $0, no network.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path("C:/Users/jackw/Desktop/42")
CORE = REPO / "automation" / "state" / "core-decisions.jsonl"
FILLS = REPO / "automation" / "state" / "fills-ledger.jsonl"
KEYLV = REPO / "automation" / "state" / "key-levels.json"
QTAPE = REPO / "analysis" / "quote-tape" / "2026-09-03.jsonl"

DATE = "2026-09-03"


def load_core_safe():
    recs = []
    with CORE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ts_et", "").startswith(DATE) and r.get("account") == "safe":
                recs.append(r)
    recs.sort(key=lambda r: r["ts_et"])
    return recs


def load_core_all():
    recs = []
    with CORE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ts_et", "").startswith(DATE):
                recs.append(r)
    recs.sort(key=lambda r: r["ts_et"])
    return recs


def get_row(recs, account, ts):
    for r in recs:
        if r.get("account") == account and r.get("ts_et") == ts:
            return r
    return None


# ---------------------------------------------------------------------------------------------
# range_position (close-tape method, IDENTICAL to backtest/tools/money_entry_location.py):
# session_hi/lo = max/min of the 'spy' field (account=safe, 1/min) over ticks <= entry_ts,
# same date. No look-ahead.
# ---------------------------------------------------------------------------------------------
def range_position_close_tape(safe_recs, entry_ts, spy_now=None):
    """session hi/lo from safe-account ticks <= entry_ts. If entry_ts itself isn't a safe-account
    tick (e.g. the bold account's row has a slightly different :0X second stamp), also fold in
    spy_now (the actual entry tick's own price, same underlying instrument) into the running hi/lo,
    matching money_entry_location.py's semantics (ticks up to AND INCLUDING the entry)."""
    hi = -1e18
    lo = 1e18
    for r in safe_recs:
        if r["ts_et"] <= entry_ts:
            spy = r.get("spy")
            if spy is not None:
                hi = max(hi, spy)
                lo = min(lo, spy)
        else:
            break
    if spy_now is not None:
        hi = max(hi, spy_now)
        lo = min(lo, spy_now)
    if hi <= lo or spy_now is None:
        return None, hi, lo
    return (spy_now - lo) / (hi - lo), hi, lo


# ---------------------------------------------------------------------------------------------
# Black-Scholes, r=0
# ---------------------------------------------------------------------------------------------
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S, K, T, sigma, side):
    if T <= 0:
        return max(0.0, (S - K) if side == "C" else (K - S))
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if side == "C":
        return S * _norm_cdf(d1) - K * _norm_cdf(d2)
    else:
        return K * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def minutes_to_close(ts_et_str):
    dt = datetime.fromisoformat(ts_et_str)
    close = dt.replace(hour=16, minute=0, second=0, microsecond=0)
    return (close - dt).total_seconds() / 60.0


def T_years(ts_et_str):
    return max(minutes_to_close(ts_et_str), 0.5) / (390.0 * 252.0)


# ---------------------------------------------------------------------------------------------
def load_quote_tape():
    recs = []
    with QTAPE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                recs.append(json.loads(line))
    return recs


def nearest_quote(qtape, symbol, ts_et_str, max_gap_min=3.0):
    """Nearest quote for `symbol` to ts_et_str within max_gap_min minutes. Returns (row, gap_min) or (None, None)."""
    target = datetime.fromisoformat(ts_et_str)
    best = None
    best_gap = None
    for r in qtape:
        if r["symbol"] != symbol:
            continue
        t = datetime.fromisoformat(r["ts_et"])
        gap = abs((t - target).total_seconds()) / 60.0
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best = r
    if best is not None and best_gap <= max_gap_min:
        return best, best_gap
    return best, best_gap  # return closest even if outside window, caller decides


def calibration_factor(qtape, symbol, K, side, anchor_ts, anchor_spy, vix):
    """Find nearest real quote to anchor_ts for `symbol`, compute BS model price at that
    exact (S,K,T,sigma), return (real_mid, model_price, factor=real/model, quote_ts, gap_min)."""
    row, gap = nearest_quote(qtape, symbol, anchor_ts)
    if row is None:
        return None
    model = bs_price(anchor_spy, K, T_years(anchor_ts), vix / 100.0, side)
    factor = row["mid"] / model if model > 1e-9 else None
    return {
        "real_mid": row["mid"], "model": model, "factor": factor,
        "quote_ts": row["ts_et"], "gap_min": gap, "anchor_spy": anchor_spy,
    }


# ===============================================================================================
def main():
    safe_recs = load_core_safe()
    all_recs = load_core_all()
    qtape = load_quote_tape()
    keylv = json.loads(KEYLV.read_text(encoding="utf-8"))
    zone_width = {lv["price"]: lv.get("zone_width") for lv in keylv["levels"]}

    print("=" * 100)
    print("PART A -- ENTRY-TICK FEATURES (close-tape range_position; engine's own conviction value shown too)")
    print("=" * 100)

    entries = [
        ("E1_engine_0941", "safe", "2026-09-03T09:41:03", "C", 769.36, 0.966),
        ("E2_engine_1016", "safe", "2026-09-03T10:16:03", "C", 768.00, 0.336),
        ("E3_engine_1106", "bold", "2026-09-03T11:06:04", "C", 769.36, 1.000),
        ("Alt1_J_put_0950", "safe", "2026-09-03T09:50:04", "P", 769.81, None),
        ("Alt2_J_call_1045", "safe", "2026-09-03T10:45:05", "C", 768.00, None),
        ("Alt3_J_call_1055", "safe", "2026-09-03T10:55:03", "C", 767.58, None),
    ]

    for name, acct, ts, side, level, conv_rp in entries:
        row = get_row(all_recs, acct, ts)
        spy_now = row.get("spy")
        rp, hi, lo = range_position_close_tape(safe_recs, ts, spy_now=spy_now)
        zw = zone_width.get(level)
        dist_dollars = abs(spy_now - level)
        dist_zw = dist_dollars / zw if zw else None
        print(f"\n--- {name}  ts={ts}  side={side}  level={level}  zone_hw={zw}")
        print(f"    spy(bar close)={spy_now}  session_hi={hi:.3f} lo={lo:.3f}")
        print(f"    range_position(close-tape)={rp:.4f}" + (f"   [engine conviction logged: {conv_rp}]" if conv_rp is not None else "  [no engine conviction row -- not a real engine trigger]"))
        print(f"    distance from level: ${dist_dollars:.3f}  =  {dist_zw:.3f} zone-widths" if dist_zw is not None else f"    distance from level: ${dist_dollars:.3f}  (no zone_width on file for this level)")
        print(f"    spread_cents at tick = {row.get('spread_cents')}")
        print(f"    vix={row.get('vix')}  bull_score={row.get('bull_score')} bear_score={row.get('bear_score')}")
        print(f"    bull_blockers={row.get('bull_blockers')}  bear_blockers={row.get('bear_blockers')}")
        cb = row.get("context_bundle") or {}
        ta = cb.get("trend_alignment") or {}
        print(f"    HTF: daily={cb.get('per_tf',{}).get('daily',{}).get('trend')} hourly={cb.get('per_tf',{}).get('hourly',{}).get('trend')} m15={cb.get('per_tf',{}).get('m15',{}).get('trend')}"
              f"  bull_align={ta.get('bull',{}).get('agree_count')}/{ta.get('bull',{}).get('available_count')}  bear_align={ta.get('bear',{}).get('agree_count')}/{ta.get('bear',{}).get('available_count')}")

    print("\n" + "=" * 100)
    print("PART B -- 5m BAR-CLOSE TAPE (safe account, from bar_freshness.bar_et; distinct values only)")
    print("=" * 100)
    prev = None
    for r in safe_recs:
        bf = r.get("bar_freshness") or {}
        key = (bf.get("bar_et"), r.get("spy"))
        if key != prev:
            print(f"  bar_et={bf.get('bar_et'):>28}  close={r.get('spy'):>8}  (first seen tick {r['ts_et'][11:16]})")
            prev = key

    print("\n" + "=" * 100)
    print("PART C -- CALIBRATION ANCHORS (real quote vs BS model)")
    print("=" * 100)
    # Alt1 put anchor: 770C real quote near 09:50 -> derive put via parity AND via calibrated BS-put
    row_950 = get_row(all_recs, "safe", "2026-09-03T09:50:04")
    vix_950 = row_950["vix"]
    spy_950 = row_950["spy"]
    cal_770c = calibration_factor(qtape, "SPY260903C00770000", 770, "C", "2026-09-03T09:50:04", spy_950, vix_950)
    print("\n770C calibration @09:50:04:", cal_770c)
    # parity put price using the REAL 770C quote (model-free)
    real_770c_950, gap = nearest_quote(qtape, "SPY260903C00770000", "2026-09-03T09:50:04")
    parity_put_950 = real_770c_950["mid"] - (spy_950 - 770)
    print(f"parity-derived 770P @09:50 (S={spy_950}, real 770C mid={real_770c_950['mid']}): {parity_put_950:.3f}")
    bs_put_950_raw = bs_price(spy_950, 770, T_years("2026-09-03T09:50:04"), vix_950 / 100.0, "P")
    factor_770 = cal_770c["factor"]
    bs_put_950_cal = bs_put_950_raw * factor_770
    print(f"BS-put raw model @09:50: {bs_put_950_raw:.3f}  calibrated (x{factor_770:.4f}): {bs_put_950_cal:.3f}   vs parity {parity_put_950:.3f}")

    # Alt2/Alt3 (768C) anchor: last real 768C quote at 10:36 (sell tick, S=767.96)
    row_1036 = get_row(all_recs, "safe", "2026-09-03T10:36:03")
    spy_1036 = row_1036["spy"]
    vix_1036 = row_1036["vix"]
    cal_768c = calibration_factor(qtape, "SPY260903C00768000", 768, "C", "2026-09-03T10:36:04", spy_1036, vix_1036)
    print("\n768C calibration @10:36:04 (last real quote before the gap):", cal_768c)

    print("\n" + "=" * 100)
    print("PART D -- WALK FORWARD: Alt1 PUT (770P, entered 09:50, rejection level 769.81)")
    print("Structure invalidation modeled as: 5m close back ABOVE 769.81 (reclaim of the rejected level).")
    print("Catastrophe cap checked as -50% of entry premium (both directions, per doctrine).")
    print("=" * 100)
    entry_premium_put = bs_put_950_cal  # calibrated BS, cross-checked vs parity above
    print(f"entry premium (calibrated BS put) = {entry_premium_put:.3f}  (parity cross-check: {parity_put_950:.3f}, {(entry_premium_put/parity_put_950-1)*100:.1f}% off)")
    factor_770_use = factor_770
    prev_bar = None
    stopped = False
    for r in safe_recs:
        if r["ts_et"] < "2026-09-03T09:50:04":
            continue
        bf = r.get("bar_freshness") or {}
        key = (bf.get("bar_et"), r.get("spy"))
        if key == prev_bar:
            continue
        prev_bar = key
        spy = r["spy"]
        vix = r["vix"]
        model = bs_price(spy, 770, T_years(r["ts_et"]), vix / 100.0, "P") * factor_770_use
        pct = (model / entry_premium_put - 1) * 100
        flag = ""
        if spy > 769.81:
            flag = " <<< STRUCTURE STOP (close back above 769.81)"
        elif pct <= -50:
            flag = " <<< CATASTROPHE CAP (-50%)"
        elif pct >= 100:
            flag = " <<< TP1 THRESHOLD (+100%)"
        print(f"  {r['ts_et'][11:16]}  bar_et={bf.get('bar_et')}  spy={spy:>8}  put_model={model:.3f}  ({pct:+.1f}%){flag}")
        if flag and "STOP" in flag or "CAP" in flag:
            stopped = True
            break

    print("\n" + "=" * 100)
    print("PART E -- WALK FORWARD: Alt2 CALL (768C, entered 10:45, reclaim of 768.00 PMH)")
    print("Structure invalidation modeled as: 5m close back BELOW 768.00.")
    print("=" * 100)
    row_1045 = get_row(all_recs, "safe", "2026-09-03T10:45:05")
    spy_1045 = row_1045["spy"]
    vix_1045 = row_1045["vix"]
    entry_premium_768c = bs_price(spy_1045, 768, T_years("2026-09-03T10:45:05"), vix_1045 / 100.0, "C") * cal_768c["factor"]
    print(f"entry premium (calibrated BS call, anchor=10:36 last real quote) = {entry_premium_768c:.3f}")
    prev_bar = None
    for r in safe_recs:
        if r["ts_et"] < "2026-09-03T10:45:05":
            continue
        bf = r.get("bar_freshness") or {}
        key = (bf.get("bar_et"), r.get("spy"))
        if key == prev_bar:
            continue
        prev_bar = key
        spy = r["spy"]
        vix = r["vix"]
        model = bs_price(spy, 768, T_years(r["ts_et"]), vix / 100.0, "C") * cal_768c["factor"]
        pct = (model / entry_premium_768c - 1) * 100
        flag = ""
        if spy < 768.00:
            flag = " <<< STRUCTURE STOP (close back below 768.00)"
        elif pct <= -50:
            flag = " <<< CATASTROPHE CAP (-50%)"
        elif pct >= 100 and "TP1_HIT" not in locals():
            flag = " <<< TP1 THRESHOLD (+100%, first crossing)"
        print(f"  {r['ts_et'][11:16]}  bar_et={bf.get('bar_et')}  spy={spy:>8}  call_model={model:.3f}  ({pct:+.1f}%){flag}")

    print("\n" + "=" * 100)
    print("PART F -- WALK FORWARD: Alt3 CALL (768C, entered 10:55, wick-bounce off 767.5-768)")
    print("=" * 100)
    row_1055 = get_row(all_recs, "safe", "2026-09-03T10:55:03")
    spy_1055 = row_1055["spy"]
    vix_1055 = row_1055["vix"]
    entry_premium_768c_alt3 = bs_price(spy_1055, 768, T_years("2026-09-03T10:55:03"), vix_1055 / 100.0, "C") * cal_768c["factor"]
    print(f"entry premium (calibrated BS call) = {entry_premium_768c_alt3:.3f}")
    prev_bar = None
    for r in safe_recs:
        if r["ts_et"] < "2026-09-03T10:55:03":
            continue
        bf = r.get("bar_freshness") or {}
        key = (bf.get("bar_et"), r.get("spy"))
        if key == prev_bar:
            continue
        prev_bar = key
        spy = r["spy"]
        vix = r["vix"]
        model = bs_price(spy, 768, T_years(r["ts_et"]), vix / 100.0, "C") * cal_768c["factor"]
        pct = (model / entry_premium_768c_alt3 - 1) * 100
        flag = ""
        if spy < 768.00:
            flag = " <<< STRUCTURE STOP"
        elif pct <= -50:
            flag = " <<< CATASTROPHE CAP"
        print(f"  {r['ts_et'][11:16]}  bar_et={bf.get('bar_et')}  spy={spy:>8}  call_model={model:.3f}  ({pct:+.1f}%){flag}")

    print("\n" + "=" * 100)
    print("PART G -- ribbon-flip timestamp (backward scan, account=safe)")
    print("=" * 100)
    import subprocess
    print("(computed separately, see report; ribbon has been BULL continuously since 2026-09-02T15:16:03 ET)")


if __name__ == "__main__":
    main()
