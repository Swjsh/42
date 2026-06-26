"""EVENT-IV-CRUSH DE-BIAS — re-price the PROPER defined-risk iron condor on the
WIDE-band OPRA cache (backtest/data/options_event_wide/), the geometry the +/-$5
cache could not reach.

THE DECISIVE TEST (this is the de-bias that can KILL the lead):
  The +/-$5 cache dropped ~63% of days = the BIG-MOVE days = the short condor's
  LOSER days, so the +$32.15 event exp/tr was magnitude-biased UP and the real
  max-loss tail was unpriced. The wide fetch (45 event + 45 non-event dual-side
  days, ATM +/-~$17/side) now PRICES the loser tail at TRUE 0DTE expiry intrinsic.

  We re-price a PROPER iron condor:
    - short strikes ~16-delta (selected via the day's ATM-straddle expected-move
      proxy, ~0.8*EM OTM -- the band could not reach this before),
    - $10-wide protective long wings (proper geometry vs the band's $1-$2 wings),
    - hold to the 0DTE close, settled at EXPIRY INTRINSIC (the real loser-day tail).

  Then: event vs non-event vs the L172 random-DAY null (many seeds). Compare the
  DE-BIASED event exp/tr to the +/-$5 cache's +$32.15: did it SHRINK (loser days
  bit) or HOLD? Does it STILL beat the null at proper geometry + adequate n? Is it
  L173-concentrated now the tail is priced? Worst-day inside the kill-switch?

GATE (edge_survives = ALL of):
  (a) event exp/tr positive DE-BIASED (real loser tail included),
  (b) BEATS the random-DAY null (L172) at >= p95 on proper geometry,
  (c) NOT L173-concentrated (drop-worst-2 EV stays positive; no single day carries it),
  (d) defined-risk worst-day INSIDE the kill-switch (Safe q3/$600, Bold $824),
  (e) adequate n (target ~30-46).

REUSE byte-for-byte: lib.simulator_credit (17/17), lib.multileg_structures,
  lib.cap_admission, and the spot/entry/eligibility plumbing from the precheck.
  simulator_real.py UNTOUCHED. Pure offline, $0. NO live edit, DEFINED-RISK ONLY.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import random
import re
import statistics
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

# ---- POINT THE OPRA LOADER AT THE WIDE CACHE (the whole point of the de-bias) ----
# option_pricing_real.CACHE_DIR is module-level; simulator_credit imports the loader
# functions which close over it. We rebind it BEFORE any leg load + clear the in-proc
# bar cache so nothing leaks from the +/-$5 dir.
from lib import option_pricing_real as opr                       # noqa: E402
WIDE_DIR = _BT / "data" / "options_event_wide"
opr.CACHE_DIR = WIDE_DIR
opr._CONTRACT_BAR_CACHE.clear()

from lib import simulator_credit as sc                           # noqa: E402
from lib.multileg_structures import Leg, max_loss_per_contract   # noqa: E402
from lib import cap_admission as ca                              # noqa: E402

from autoresearch._pivot_premium_selling import (                # noqa: E402
    _load_spy_master,
    _spot_and_decision,
)
from autoresearch._event_iv_crush_precheck import build_event_days  # noqa: E402

WINDOW_START = dt.date(2025, 1, 2)
WINDOW_END = dt.date(2026, 6, 18)

ENTRY_TIME = dt.time(10, 0)     # same 10:00 ET entry as the precheck (post 08:30 print)
WING_WIDTH = 10                 # PROPER $10-wide protective wing
DELTA16_EM_FRAC = 0.80          # short strike ~0.8 * expected-move OTM (~16-delta proxy)
PT_FRAC = 0.50
STOP_MULT = None                # EOD-only: hold the defined-risk condor to 0DTE close
SETTLE = "expiry_intrinsic"     # PRICE THE REAL LOSER TAIL at the day's intrinsic
COMMISSION = 0.65


# ── wide-cache strike universe (per expiry, from the CSVs actually present) ──────
def _wide_strikes(date: dt.date, side: str) -> set[int]:
    yymmdd = date.strftime("%y%m%d")
    out: set[int] = set()
    for p in glob.glob(str(WIDE_DIR / f"SPY{yymmdd}{side}*.csv")):
        m = re.search(rf"SPY{yymmdd}{side}0*(\d+)000\.csv$", os.path.basename(p))
        if m:
            out.add(int(m.group(1)))
    return out


def _wide_dual_dates() -> set[dt.date]:
    """All expiry dates with BOTH a call and a put CSV in the wide cache."""
    dates: dict[dt.date, dict] = {}
    for p in glob.glob(str(WIDE_DIR / "SPY*.csv")):
        m = re.search(r"SPY(\d{6})([CP])", os.path.basename(p))
        if not m:
            continue
        try:
            d = dt.datetime.strptime(m.group(1), "%y%m%d").date()
        except ValueError:
            continue
        dates.setdefault(d, {"C": 0, "P": 0})[m.group(2)] += 1
    return {d for d, c in dates.items() if c["C"] > 0 and c["P"] > 0}


def _atm_straddle_em(date: dt.date, atm: int, decision_dt: dt.datetime) -> Optional[float]:
    """Expected move ($) = ATM call + ATM put entry-bar premium (straddle price).
    The market's own 1-sigma estimate for the day. None if either ATM leg missing.
    """
    next_bar = decision_dt + dt.timedelta(minutes=5)
    c_df = opr.load_contract_bars(opr.option_symbol(date, atm, "C"))
    p_df = opr.load_contract_bars(opr.option_symbol(date, atm, "P"))
    if c_df is None or p_df is None:
        return None
    if c_df["timestamp_et"].dt.tz is not None:
        c_df = c_df.copy(); c_df["timestamp_et"] = c_df["timestamp_et"].dt.tz_localize(None)
    if p_df["timestamp_et"].dt.tz is not None:
        p_df = p_df.copy(); p_df["timestamp_et"] = p_df["timestamp_et"].dt.tz_localize(None)
    cb = opr.bar_at_or_after(c_df, next_bar)
    pb = opr.bar_at_or_after(p_df, next_bar)
    if cb is None or pb is None or cb.open <= 0 or pb.open <= 0:
        return None
    return cb.open + pb.open


def _build_condor_legs(date: dt.date, spot: float, decision_dt: dt.datetime):
    """PROPER iron condor: ~16-delta shorts (0.8*EM OTM) + $10-wide wings, snapped
    to the wide cache's available strikes. Returns (legs, meta) or (None, reason)."""
    atm = int(round(spot))
    em = _atm_straddle_em(date, atm, decision_dt)
    if em is None or em <= 0:
        return None, "no_em"
    off = max(1, int(round(DELTA16_EM_FRAC * em)))   # $-offset of the short strikes
    short_p = atm - off
    short_c = atm + off
    long_p = short_p - WING_WIDTH
    long_c = short_c + WING_WIDTH

    pstk = _wide_strikes(date, "P")
    cstk = _wide_strikes(date, "C")
    # snap each leg to the NEAREST available strike in the right direction; require all 4.
    def _snap(target, universe, prefer_lower):
        if target in universe:
            return target
        cands = sorted(universe)
        if prefer_lower:
            below = [s for s in cands if s <= target]
            return below[-1] if below else (cands[0] if cands else None)
        above = [s for s in cands if s >= target]
        return above[0] if above else (cands[-1] if cands else None)

    sp = _snap(short_p, pstk, prefer_lower=False)   # short put: don't go further OTM than target
    lp = _snap(long_p, pstk, prefer_lower=True)      # long put: at/below target (further OTM ok)
    sck = _snap(short_c, cstk, prefer_lower=True)
    lc = _snap(long_c, cstk, prefer_lower=False)
    if None in (sp, lp, sck, lc):
        return None, "snap_fail"
    if not (lp < sp < sck < lc):
        return None, "geometry_fail"
    legs = [
        Leg(sp, "P", -1), Leg(lp, "P", +1),
        Leg(sck, "C", -1), Leg(lc, "C", +1),
    ]
    # binding wing = the WIDER of the two realised wings (defined-risk gate number)
    binding_wing = max(sp - lp, lc - sck)
    meta = {"em": round(em, 2), "off": off, "short_p": sp, "long_p": lp,
            "short_c": sck, "long_c": lc, "binding_wing": binding_wing}
    return legs, meta


def run_on_days(spy, day_list):
    """Sim the proper condor across day_list with EXPIRY-INTRINSIC settlement
    (prices the real loser-day tail). Returns list[(CreditFill, meta)] for taken."""
    out = []
    for d in day_list:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, spot_close = _spot_and_decision(spy_day, ENTRY_TIME)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs, meta = _build_condor_legs(d, spot, decision_dt)
        if legs is None:
            continue
        f = sc.simulate_credit_trade(
            d, legs, decision_dt, spot, wing_width=meta["binding_wing"],
            structure_name="IC", contracts=1, pt_frac=PT_FRAC, stop_mult=STOP_MULT,
            settle_mode="eod_close_mark", commission_per_contract=COMMISSION)
        if f.skipped:
            continue
        # RE-SETTLE at TRUE 0DTE expiry intrinsic using the day's SPY close so the
        # big-move LOSER days are priced at intrinsic, not a possibly-stale bar.close.
        # Only override when the trade reached EOD (no intraday PT/STOP fired).
        if f.exit_reason == "EOD" and spot_close and spot_close > 0:
            intrinsic_pnl = sc.settle_expiry_intrinsic(
                legs, f.net_credit, spot_close, contracts=1,
                commission_per_contract=COMMISSION)
            f.realized_pnl = intrinsic_pnl
            f.exit_reason = "EXPIRY"
        out.append((f, meta))
    return out


def summarize(rows, label):
    fills = [f for f, _ in rows]
    pnls = [f.realized_pnl for f in fills]
    if not pnls:
        return {"label": label, "n": 0}
    dated = sorted(((f.date, f.realized_pnl) for f in fills), key=lambda x: x[0])
    eq = peak = mdd = 0.0
    for _, p in dated:
        eq += p; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    wins = [p for p in pnls if p > 0]
    by_month: dict[str, list[float]] = {}
    for f in fills:
        by_month.setdefault(f.date[:7], []).append(f.realized_pnl)
    pos_months = sum(1 for v in by_month.values() if statistics.mean(v) > 0)
    s = sorted(pnls)
    # L173 concentration: EV after dropping the single best, and the best-2.
    def _ev(xs): return statistics.mean(xs) if xs else 0.0
    drop_best1 = _ev(s[:-1]) if len(s) > 1 else 0.0
    drop_best2 = _ev(s[:-2]) if len(s) > 2 else 0.0
    drop_worst2 = _ev(s[2:]) if len(s) > 2 else 0.0
    top1_share = (max(pnls) / sum(pnls)) if sum(pnls) > 0 else None
    return {
        "label": label, "n": len(pnls),
        "exp_per_trade": round(statistics.mean(pnls), 2),
        "total_pnl": round(sum(pnls), 2),
        "wr": round(len(wins) / len(pnls), 3),
        "worst_day": round(min(pnls), 2),
        "best_day": round(max(pnls), 2),
        "book_max_dd": round(mdd, 2),
        "avg_credit": round(statistics.mean([f.net_credit for f in fills]), 2),
        "avg_max_loss_defined": round(statistics.mean([f.max_loss_defined for f in fills]), 2),
        "n_months": len(by_month), "pos_months": pos_months,
        "drop_best1_exp": round(drop_best1, 2),
        "drop_best2_exp": round(drop_best2, 2),
        "drop_worst2_exp": round(drop_worst2, 2),
        "top1_pnl_share_of_total": round(top1_share, 3) if top1_share is not None else None,
    }


def random_day_null(spy, nonevent_days, n_sample, *, reps=2000, seeds=(11, 23, 47, 99, 1234)):
    """L172 random-DAY-selection null: pre-sim every non-event day ONCE, then draw
    n_sample random non-event days `reps` times per seed. Event exp must sit in the
    RIGHT tail. Returns aggregate over all seeds + the worst-seed percentile."""
    rows = run_on_days(spy, nonevent_days)
    by_date = {f.date: f.realized_pnl for f, _ in rows}
    pool = list(by_date.keys())
    if len(pool) < n_sample or n_sample == 0:
        return None, pool
    # When the non-event pool == n_sample (balanced 1:1 fetch), random.sample without
    # replacement is degenerate (always picks the whole pool -> point mass). Use a
    # BOOTSTRAP (resample n_sample days WITH replacement) so the null is a real
    # distribution of the non-event exp/tr — the honest L172 comparison.
    vals = list(by_date.values())
    all_exps = []
    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(reps):
            pick = [rng.choice(vals) for _ in range(n_sample)]
            all_exps.append(statistics.mean(pick))
    all_exps.sort()
    return {
        "reps_per_seed": reps, "seeds": list(seeds), "n_sample": n_sample,
        "nonevent_pool": len(pool),
        "null_mean": round(statistics.mean(all_exps), 2),
        "null_p50": round(all_exps[len(all_exps)//2], 2),
        "null_p95": round(all_exps[int(0.95*len(all_exps))], 2),
        "null_p99": round(all_exps[int(0.99*len(all_exps))], 2),
        "_dist": all_exps,
    }, pool


def percentile_of(value, dist):
    if not dist:
        return None
    below = sum(1 for e in dist if e < value)
    return round(100.0 * below / len(dist), 2)


def cap_check(rows, account, equity):
    fills = [f for f, _ in rows]
    if not fills:
        return {}
    qty = ca.SAFE_MIN_CONTRACTS if account == "safe" else ca.BOLD_MIN_CONTRACTS
    worst_lot = min(f.realized_pnl for f in fills)
    max_loss_lot = max(f.max_loss_defined for f in fills)
    res = ca.admit_book(
        fills, account, equity, qty,
        premium_getter=lambda f: f.net_credit / 100.0)
    kill = 600.0 if account == "safe" else 824.0
    return {
        "account": account, "qty": qty, "equity": equity,
        "worst_day_per_lot": round(worst_lot, 2),
        "worst_day_scaled_qty": round(worst_lot * qty, 2),
        "max_defined_loss_per_lot": round(max_loss_lot, 2),
        "max_defined_loss_scaled": round(max_loss_lot * qty, 2),
        "kill_switch_dollars": kill,
        "worst_scaled_inside_kill": bool(abs(worst_lot * qty) <= kill),
        "max_defined_scaled_inside_kill": bool(max_loss_lot * qty <= kill),
        "admitted": len(res.admitted), "blocked": len(res.blocked),
        "block_rate": res.block_rate, "block_codes": res.block_codes,
    }


def main():
    ev = build_event_days()
    event_set = set(ev["all"])
    spy = _load_spy_master()
    spy_dates = set(spy["date"].unique())

    dual = _wide_dual_dates()
    dual = {d for d in dual if WINDOW_START <= d <= WINDOW_END and d in spy_dates}
    event_days = sorted(d for d in dual if d in event_set)
    nonevent_days = sorted(d for d in dual if d not in event_set)

    print("=" * 74)
    print("EVENT-IV-CRUSH DE-BIAS  —  PROPER condor on the WIDE cache")
    print("=" * 74)
    print(f"  wide-cache dual-side dates in-window: {len(dual)}")
    print(f"  event days (cache-present): {len(event_days)}  "
          f"non-event: {len(nonevent_days)}")
    print(f"  geometry: ~16-delta short (0.8*EM OTM) + ${WING_WIDTH}-wide wings, "
          f"entry {ENTRY_TIME} ET, hold-to-0DTE-close, settle=EXPIRY INTRINSIC")

    ev_rows = run_on_days(spy, event_days)
    ne_rows = run_on_days(spy, nonevent_days)
    ev_sum = summarize(ev_rows, "EVENT")
    ne_sum = summarize(ne_rows, "NON-EVENT")
    print("\n  EVENT    :", json.dumps(ev_sum))
    print("  NON-EVENT:", json.dumps(ne_sum))

    if ev_sum["n"] == 0:
        print("  >> no event fills; abort."); return

    # provenance: a few realised geometries (did we actually reach ~16-delta / $10 wings?)
    print("\n  sample realised geometries (event days):")
    for f, meta in ev_rows[:6]:
        print(f"    {f.date} EM=${meta['em']} off=${meta['off']} "
              f"P[{meta['long_p']}/{meta['short_p']}] C[{meta['short_c']}/{meta['long_c']}] "
              f"wing=${meta['binding_wing']} credit=${f.net_credit:.0f} "
              f"maxloss=${f.max_loss_defined:.0f} pnl=${f.realized_pnl:.0f} exit={f.exit_reason}")

    delta = round(ev_sum["exp_per_trade"] - ne_sum["exp_per_trade"], 2)
    print(f"\n  IV-CRUSH SELECTION DELTA (event - nonevent exp/tr): ${delta}")
    print(f"  vs +/-$5 cache event exp/tr +$32.15  ->  DE-BIASED = ${ev_sum['exp_per_trade']}  "
          f"({'SHRANK' if ev_sum['exp_per_trade'] < 32.15 else 'HELD/GREW'})")

    nul, pool = random_day_null(spy, nonevent_days, ev_sum["n"])
    if nul is None:
        print("  >> null pool too small; abort gate."); return
    pct = percentile_of(ev_sum["exp_per_trade"], nul["_dist"])
    beats_null = bool(ev_sum["exp_per_trade"] > nul["null_p95"])
    nul_print = {k: v for k, v in nul.items() if k != "_dist"}
    print("\n  RANDOM-DAY NULL:", json.dumps(nul_print))
    print(f"  event exp percentile within null: {pct}th  (beats p95 = {beats_null})")

    # L173 concentration test (now the tail is priced)
    l173 = bool(ev_sum["drop_worst2_exp"] >= 0 and ev_sum["drop_best2_exp"] > 0
                and (ev_sum["top1_pnl_share_of_total"] is None
                     or ev_sum["top1_pnl_share_of_total"] < 0.5))
    print(f"\n  L173 concentration: drop_best2_exp=${ev_sum['drop_best2_exp']} "
          f"drop_worst2_exp=${ev_sum['drop_worst2_exp']} "
          f"top1_share={ev_sum['top1_pnl_share_of_total']}  -> NOT_concentrated={l173}")

    cap_s = cap_check(ev_rows, "safe", 2000.0)
    cap_b = cap_check(ev_rows, "bold", 1649.0)
    print("\n  CAP/KILL (Safe q3/$600):", json.dumps(cap_s))
    print("  CAP/KILL (Bold q4/$824):", json.dumps(cap_b))

    n_ok = ev_sum["n"] >= 30
    positive = ev_sum["exp_per_trade"] > 0
    tail_ok = bool(cap_s.get("worst_scaled_inside_kill")
                   and cap_s.get("max_defined_scaled_inside_kill"))
    edge_survives = bool(positive and beats_null and l173 and tail_ok and n_ok)

    print("\n" + "=" * 74)
    print("GATE")
    print("=" * 74)
    print(f"  (a) positive de-biased exp/tr      : {positive}  (${ev_sum['exp_per_trade']})")
    print(f"  (b) beats random-DAY null (>=p95)  : {beats_null}  ({pct}th pctile)")
    print(f"  (c) NOT L173-concentrated          : {l173}")
    print(f"  (d) tail inside kill-switch (Safe) : {tail_ok}  (worst scaled ${cap_s.get('worst_day_scaled_qty')})")
    print(f"  (e) adequate n (>=30)              : {n_ok}  (n={ev_sum['n']})")
    print(f"\n  >> EDGE_SURVIVES = {edge_survives}")

    out = {
        "geometry": f"~16d-short(0.8EM)+${WING_WIDTH}wide, entry {ENTRY_TIME}, expiry-intrinsic",
        "n_event": ev_sum["n"], "n_nonevent": ne_sum["n"],
        "event": ev_sum, "nonevent": ne_sum,
        "selection_delta": delta,
        "debiased_event_exp": ev_sum["exp_per_trade"],
        "pm5_cache_event_exp": 32.15,
        "shrank_vs_pm5": ev_sum["exp_per_trade"] < 32.15,
        "null": nul_print, "event_percentile_in_null": pct, "beats_null_p95": beats_null,
        "l173_not_concentrated": l173,
        "cap_safe": cap_s, "cap_bold": cap_b,
        "gate": {"positive": positive, "beats_null": beats_null, "not_l173": l173,
                 "tail_ok": tail_ok, "n_ok": n_ok},
        "edge_survives": edge_survives,
    }
    OUT = _BT / "autoresearch" / "_state" / "event_iv_crush_debias.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
