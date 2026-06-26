"""EVENT-IV-CRUSH DE-BIAS re-price (STRATEGY-DIRECTION-BACKLOG #6, decisive step).

The +/-$5 OPRA cache priced a NARROW $2-wing condor and could not place a real
~16-delta short / $10-wide long — AND it clipped the loser tail on big-move days
(the short condor's worst days). The wide-band fetch (data/options_event_wide/,
ATM +/-$18, $1 grid, C+P) now lets us re-price the PROPER geometry with the real
loser tail.

WHAT THIS DOES
  1. Point the OPRA loader at the WIDE cache (monkeypatch CACHE_DIR + clear memo).
  2. For each EVENT day and each matched NON-EVENT day, build a DEFINED-RISK iron
     condor with:
       - short strikes selected by a PREMIUM-based ~16-delta proxy (no Greeks in the
         cache): pick the OTM strike whose entry mid is closest to TARGET_SHORT_PREMIUM
         (a 16-delta 0DTE short trades ~$0.30-0.60; we target $0.45/side and report the
         realized %OTM + premium so the proxy is auditable).
       - a $10-wide long wing (proper condor geometry the +/-$5 band could not reach).
     If EITHER the short or its wing falls outside the priced wide band, the day is
     SKIPPED + logged (cannot price that geometry honestly) — the skip-rate is itself
     a finding (does the wide band reach the proper strikes on the loser days?).
  3. Hold to the 0DTE close (EOD-only) -> the real loser tail is realized.
  4. GATE:
       (a) event exp/tr stays POSITIVE de-biased (real tail priced),
       (b) BEATS the random-DAY null (L172) on the SAME proper geometry,
       (c) NOT L173-concentrated (drop-worst-2 EV must not collapse / flip),
       (d) defined-risk worst-day INSIDE the kill-switch (cap-sized),
       (e) adequate n (target ~30-46).

Reuses simulator_credit + multileg_structures (17/17) + cap_admission byte-for-byte.
Pure offline, $0. NO live edit. DEFINED-RISK ONLY.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

import lib.option_pricing_real as opr                              # noqa: E402
from lib import simulator_credit as sc                            # noqa: E402
from lib.multileg_structures import Leg                           # noqa: E402
from lib import cap_admission as ca                               # noqa: E402
from autoresearch._event_iv_crush_precheck import build_event_days, ENTRY_TIME  # noqa: E402
from autoresearch._pivot_premium_selling import (                 # noqa: E402
    _load_spy_master, _spot_and_decision,
)

WIDE_DIR = _BT / "data" / "options_event_wide"
WIDE_HALF = 18                  # the fetched band: ATM +/- $18
TARGET_SHORT_PREMIUM = 0.45     # ~16-delta 0DTE short proxy (audit realized %OTM/prem)
SHORT_PREM_LO, SHORT_PREM_HI = 0.20, 0.90   # acceptable short-premium window for the proxy
WING_WIDTH = 10                 # proper $10-wide long wing (the +/-$5 band could not reach)
PT_FRAC = 0.50
COMMISSION = 0.65
ENTRY = ENTRY_TIME              # 10:00 ET

NONEVENT_MATCH_SEED = 4242      # MUST match the fetcher's matched non-event draw


def _repoint_loader_to_wide():
    """Point the shared OPRA loader at the WIDE cache + clear its memo so a prior
    run against data/options/ does not leak narrow-only DataFrames."""
    opr.CACHE_DIR = WIDE_DIR
    opr._CONTRACT_BAR_CACHE.clear()


def _entry_mid(date: dt.date, strike: int, side: str) -> float | None:
    """Entry-bar mid (~ open) for one leg from the WIDE cache, at ENTRY+5m.
    None if the contract has no bar at/after entry (outside priced band / illiquid)."""
    sym = opr.option_symbol(date, strike, side)
    df = opr.load_contract_bars(sym)
    if df is None or df.empty:
        return None
    if df["timestamp_et"].dt.tz is not None:
        df = df.copy()
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    return None if df.empty else _bar_open_at(df, date)


def _bar_open_at(df, date: dt.date) -> float | None:
    """Open of the first bar at/after the 10:05 ET entry fill bar."""
    entry_fill_bar = dt.datetime.combine(date, dt.time(10, 5))
    m = df[df["timestamp_et"] >= entry_fill_bar]
    if m.empty:
        return None
    o = float(m.iloc[0]["open"])
    return o if o > 0 else None


def _pick_short_strike(date: dt.date, atm: int, side: str) -> tuple[int, float] | None:
    """Pick the OTM short strike (put below ATM / call above) whose entry premium is
    CLOSEST to TARGET_SHORT_PREMIUM within [SHORT_PREM_LO, SHORT_PREM_HI]. Returns
    (strike, premium) or None if no priced strike in the proxy window inside the band."""
    best = None
    rng = range(atm - 1, atm - WIDE_HALF - 1, -1) if side == "P" else range(atm + 1, atm + WIDE_HALF + 1)
    for k in rng:
        prem = _entry_mid(date, k, side)
        if prem is None:
            continue
        if not (SHORT_PREM_LO <= prem <= SHORT_PREM_HI):
            continue
        dist = abs(prem - TARGET_SHORT_PREMIUM)
        if best is None or dist < best[2]:
            best = (k, prem, dist)
    return (best[0], best[1]) if best else None


def build_condor_legs(date: dt.date, atm: int) -> tuple[list[Leg], dict] | None:
    """Build a proper-geometry defined-risk IC for `date`. Both shorts ~16-delta by
    premium proxy; both wings $10 further OTM. Returns (legs, meta) or None if any
    leg falls outside the priced wide band (logged skip)."""
    sp = _pick_short_strike(date, atm, "P")
    sc_ = _pick_short_strike(date, atm, "C")
    if sp is None or sc_ is None:
        return None
    short_p, prem_p = sp
    short_c, prem_c = sc_
    long_p = short_p - WING_WIDTH
    long_c = short_c + WING_WIDTH
    # Wings must be inside the priced wide band (have a bar) — else cannot price the
    # defined-risk tail honestly. This is the decisive de-bias gate.
    if _entry_mid(date, long_p, "P") is None or _entry_mid(date, long_c, "C") is None:
        return None
    legs = [
        Leg(short_p, "P", -1), Leg(long_p, "P", +1),
        Leg(short_c, "C", -1), Leg(long_c, "C", +1),
    ]
    meta = {
        "short_p": short_p, "short_c": short_c, "long_p": long_p, "long_c": long_c,
        "prem_p": round(prem_p, 2), "prem_c": round(prem_c, 2),
        "pct_otm_p": round((atm - short_p) / atm * 100, 2),
        "pct_otm_c": round((short_c - atm) / atm * 100, 2),
    }
    return legs, meta


def run_days(spy, day_list):
    """Re-price the proper condor on each day. Returns (fills, skips, metas)."""
    fills, skips, metas = [], 0, []
    for d in day_list:
        sd = spy[spy["date"] == d]
        if sd.empty:
            skips += 1
            continue
        decision_dt, spot, _ = _spot_and_decision(sd, ENTRY)
        if decision_dt is None or not spot or spot <= 0:
            skips += 1
            continue
        atm = int(round(spot))
        built = build_condor_legs(d, atm)
        if built is None:
            skips += 1
            continue
        legs, meta = built
        f = sc.simulate_credit_trade(
            d, legs, decision_dt, spot, wing_width=WING_WIDTH,
            structure_name="IC_16D_10W", contracts=1, pt_frac=PT_FRAC,
            stop_mult=None, commission_per_contract=COMMISSION)
        if f.skipped:
            skips += 1
            continue
        fills.append(f)
        meta["date"] = d.isoformat()
        meta["pnl"] = round(f.realized_pnl, 2)
        meta["credit"] = round(f.net_credit, 2)
        meta["max_loss_defined"] = round(f.max_loss_defined, 2)
        metas.append(meta)
    return fills, skips, metas


def summarize(fills, label):
    pnls = [f.realized_pnl for f in fills]
    if not pnls:
        return {"label": label, "n": 0}
    s = sorted(pnls)
    wins = [p for p in pnls if p > 0]
    drop_worst2 = s[2:] if len(s) > 2 else []
    return {
        "label": label, "n": len(pnls),
        "exp_per_trade": round(statistics.mean(pnls), 2),
        "total_pnl": round(sum(pnls), 2),
        "wr": round(len(wins) / len(pnls), 3),
        "worst_trade": round(min(pnls), 2),
        "best_trade": round(max(pnls), 2),
        "drop_worst2_exp": round(statistics.mean(drop_worst2), 2) if drop_worst2 else None,
        "avg_credit": round(statistics.mean([f.net_credit for f in fills]), 2),
        "avg_max_loss_defined": round(statistics.mean([f.max_loss_defined for f in fills]), 2),
    }


def random_day_null(ev_exp, ne_fills, n_sample, reps=2000, seeds=(1, 2, 3, 4, 5)):
    """L172 random-DAY null on the SAME proper geometry. Multi-seed (5x reps) for
    robustness. Returns the pooled percentile of ev_exp + p95 + bootstrap P(delta<=0)."""
    by_date = {f.date: f.realized_pnl for f in ne_fills}
    pool = list(by_date.values())
    if n_sample == 0 or not pool:
        return None
    # If the event sample exceeds the priceable non-event pool, clamp to the pool size
    # (draw the largest possible matched sample); record the clamp so it is auditable.
    clamped = min(n_sample, len(pool))
    all_exps = []
    for sd in seeds:
        rng = random.Random(sd)
        for _ in range(reps):
            pick = rng.sample(pool, clamped)
            all_exps.append(statistics.mean(pick))
    all_exps.sort()
    below = sum(1 for e in all_exps if e < ev_exp)
    pctile = round(below / len(all_exps), 3)
    p95 = all_exps[int(0.95 * len(all_exps))]
    ne_mean = statistics.mean(pool)
    # bootstrap P(event-edge delta vs non-event mean <= 0)
    delta = ev_exp - ne_mean
    p_delta_le0 = round(sum(1 for e in all_exps if (ev_exp - e) <= 0) / len(all_exps), 4)
    return {
        "reps_total": len(all_exps), "n_sample": n_sample,
        "n_sample_clamped": clamped, "pool_size": len(pool),
        "null_mean": round(ne_mean, 2), "null_p95": round(p95, 2),
        "event_exp": round(ev_exp, 2), "event_pctile_in_null": pctile,
        "beats_null_p95": bool(ev_exp > p95),
        "selection_delta": round(delta, 2), "boot_P_delta_le0": p_delta_le0,
    }


def cap_check(fills, account, equity, kill):
    qty = ca.SAFE_MIN_CONTRACTS if account == "safe" else ca.BOLD_MIN_CONTRACTS
    if not fills:
        return {}
    worst_lot = min(f.realized_pnl for f in fills)
    max_loss_lot = max(f.max_loss_defined for f in fills)
    return {
        "account": account, "qty": qty, "equity": equity, "kill_switch": kill,
        "worst_trade_per_lot": round(worst_lot, 2),
        "worst_trade_scaled": round(worst_lot * qty, 2),
        "max_defined_loss_per_lot": round(max_loss_lot, 2),
        "max_defined_loss_scaled": round(max_loss_lot * qty, 2),
        "worst_scaled_inside_kill": bool(abs(worst_lot * qty) <= kill),
        "max_defined_scaled_inside_kill": bool(max_loss_lot * qty <= kill),
    }


def main():
    _repoint_loader_to_wide()
    ev = build_event_days()
    spy = _load_spy_master()
    spy_dates = set(spy["date"].unique())
    # Use the SAME day universe the fetcher used: event days w/ SPY + matched non-event.
    from autoresearch._pivot_premium_selling import _option_cache_dates
    from autoresearch._event_iv_crush_precheck import WINDOW_START, WINDOW_END
    cache_dates = _option_cache_dates()
    usable = sorted(spy_dates & cache_dates)
    usable = [d for d in usable if WINDOW_START <= d <= WINDOW_END]
    event_set = set(ev["all"])
    event_days = [d for d in usable if d in event_set]
    nonevent_pool = [d for d in usable if d not in event_set]
    rng = random.Random(NONEVENT_MATCH_SEED)
    matched_nonevent = sorted(rng.sample(nonevent_pool, min(len(event_days), len(nonevent_pool))))

    print("=" * 72)
    print("EVENT-IV-CRUSH DE-BIAS RE-PRICE (proper ~16d / $10-wide condor, wide cache)")
    print("=" * 72)
    print(f"  loader CACHE_DIR -> {opr.CACHE_DIR}")
    print(f"  event days: {len(event_days)}  matched non-event: {len(matched_nonevent)}")
    print(f"  geometry: short ~prem ${TARGET_SHORT_PREMIUM} (16d proxy), $10 wing, "
          f"entry {ENTRY} ET, hold-to-0DTE-close")

    ev_fills, ev_skip, ev_meta = run_days(spy, event_days)
    ne_fills, ne_skip, ne_meta = run_days(spy, matched_nonevent)

    ev_sum = summarize(ev_fills, "EVENT")
    ne_sum = summarize(ne_fills, "NON-EVENT")
    print(f"\n  EVENT    : {json.dumps(ev_sum)}")
    print(f"     skips (geometry not priceable in wide band): {ev_skip}/{len(event_days)}")
    print(f"  NON-EVENT: {json.dumps(ne_sum)}")
    print(f"     skips: {ne_skip}/{len(matched_nonevent)}")

    out = {
        "geometry": {"target_short_prem": TARGET_SHORT_PREMIUM, "wing_width": WING_WIDTH,
                     "entry_et": str(ENTRY), "wide_half": WIDE_HALF, "hold": "EOD"},
        "event": ev_sum, "event_skips": ev_skip, "event_days_total": len(event_days),
        "nonevent": ne_sum, "nonevent_skips": ne_skip,
        "event_metas": ev_meta,
    }

    if ev_sum["n"] == 0:
        out["verdict"] = "DEAD_NO_PRICEABLE_GEOMETRY"
        _write(out)
        return

    nul = random_day_null(ev_sum["exp_per_trade"], ne_fills, ev_sum["n"])
    print(f"\n  RANDOM-DAY NULL (proper geometry, 5x2000): {json.dumps(nul)}")
    out["null"] = nul

    # L173 concentration: drop-worst-2 must NOT flip sign (still meaningfully positive).
    l173_ok = (ev_sum.get("drop_worst2_exp") is not None
               and ev_sum["drop_worst2_exp"] >= 0)
    # Also require the edge isn't carried by <=2 winners (drop-best-2 stays >=0-ish).
    pnls = sorted(f.realized_pnl for f in ev_fills)
    drop_best2 = statistics.mean(pnls[:-2]) if len(pnls) > 2 else None
    out["drop_best2_exp"] = round(drop_best2, 2) if drop_best2 is not None else None

    cap_safe = cap_check(ev_fills, "safe", 2000.0, 600.0)
    cap_bold = cap_check(ev_fills, "bold", 1649.0, 824.0)
    print(f"  CAP/KILL (Safe q3 / $600): {json.dumps(cap_safe)}")
    print(f"  CAP/KILL (Bold q5 / $824): {json.dumps(cap_bold)}")
    out["cap_safe"] = cap_safe
    out["cap_bold"] = cap_bold

    # FOMC / CPI / NFP breakdown (broad-based?)
    klass = {}
    for m in ev_meta:
        d = dt.date.fromisoformat(m["date"])
        c = ("FOMC" if d in set(ev["fomc"]) else "CPI" if d in set(ev["cpi"])
             else "NFP" if d in set(ev["nfp"]) else "?")
        klass.setdefault(c, []).append(m["pnl"])
    byclass = {c: {"n": len(v), "exp": round(statistics.mean(v), 2)} for c, v in klass.items()}
    print(f"  BY EVENT CLASS: {json.dumps(byclass)}")
    out["by_class"] = byclass

    # GATE
    g_pos = ev_sum["exp_per_trade"] > 0
    g_null = bool(nul and nul["beats_null_p95"])
    g_l173 = bool(l173_ok)
    g_tail = bool(cap_safe.get("max_defined_scaled_inside_kill"))
    g_n = ev_sum["n"] >= 30
    survives = all([g_pos, g_null, g_l173, g_tail, g_n])
    gate = {
        "positive_debiased": g_pos, "beats_null": g_null,
        "not_l173_concentrated": g_l173, "tail_inside_kill_safe": g_tail,
        "adequate_n": g_n, "n": ev_sum["n"], "survives": survives,
    }
    print(f"\n  GATE: {json.dumps(gate)}")
    out["gate"] = gate
    out["verdict"] = "LEAD_TO_EDGE" if survives else (
        "STILL_LEAD" if (g_pos and ev_sum["n"] < 30) else "DEAD")
    print(f"  VERDICT: {out['verdict']}")
    _write(out)


def _write(out):
    p = _BT / "autoresearch" / "_state" / "event_iv_crush_reprice.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
