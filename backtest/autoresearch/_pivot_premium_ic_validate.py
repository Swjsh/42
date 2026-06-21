"""IC LEAD validation — completes the assigned diagnostic set for the iron-condor LEAD.

The premium-selling pivot left the IC cell (IC / 10:30 ET / short_offset=2 / wing=2 /
pt=0.50 / stop=1.5x) as a LEAD: OOS-positive (+$23.03/tr), 82.7% WR, drop-worst-5 still
+$19.81, tiny book DD (-$269) — but it fails the gate on ONE axis (posQ=2<4, structurally
unreachable in a 2-quarter OOS window). Before it can be called an EDGE the spec demands
four checks. Two were already run by _pivot_premium_finalize.py (null=FAIL, posQ-respec=PASS);
two were NOT quantified for the IC cell. This script runs ALL FOUR, self-contained, so the
verdict rests on one reproducible artifact.

  CHECK 1  RANDOM-STRIKE / RANDOM-ENTRY NULL (L172) — independent re-seed (was: FAIL).
  CHECK 2  BAND-SKIP SURVIVORSHIP — is the +EV purely "we only traded the calm days"?
           (a) skip-reason mechanism tally, (b) SPY excursion of TRADED vs SKIPPED days,
           (c) force-a-trade-on-skip-days counterfactual (nearest cached-band condor).
  CHECK 3  POSQ RE-SPEC — monthly posMonth>=K/6 + IS+OOS combined quarter count.
  CHECK 4  INTRABAR-STOP HONESTY — intrabar_stop_would_hit rate for the stop variants
           (bar.close MTM understates stops; report how many trades a tighter intrabar
           stop would have tripped that the close-basis sim let ride).

Pure offline, $0. Reuses _pivot_premium_selling.py + simulator_credit.py +
multileg_structures.py byte-for-byte (simulator_real.py UNTOUCHED). Writes
_state/pivot_premium_selling/ic_validate.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_premium_ic_validate.py
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

import pandas as pd

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib import simulator_credit as sc                              # noqa: E402
from lib.multileg_structures import build_legs, Leg   # noqa: E402
import _pivot_premium_selling as piv                                # noqa: E402

OUT = _BT / "autoresearch" / "_state" / "pivot_premium_selling" / "ic_validate.json"
OPT_DIR = _BT / "data" / "options"
OOS_START = dt.date(2026, 1, 1)
IS_START, IS_END = dt.date(2025, 1, 1), dt.date(2025, 6, 30)

# The LEAD cell under test.
STRUCT, ENTRY, OFF, WING, PT = "IC", dt.time(10, 30), 2, 2, 0.5
STOP_VARIANTS = [None, 1.5, 2.0]   # EOD-only + the two premium stops

# Independent re-seed. NOTE: the p95 boolean is SEED-FRAGILE at low iters (a 60-iter
# run spuriously passed; the 500-iter x 3-seed cross-check converged to actual at the
# ~76th pctile of the strike-null = FAIL). We run 400 iters so check1 is seed-stable, and
# we treat the PERCENTILE RANK (not the p95 boolean) as the honest headline statistic.
NULL_SEED, NULL_ITERS = 99, 400


# ── small stats helpers ────────────────────────────────────────────────────
def _expc(xs):
    return statistics.mean(xs) if xs else 0.0


def _pct(dist, q):
    s = sorted(dist)
    if not s:
        return 0.0
    return s[int(q * (len(s) - 1))]


def _month(d):
    return f"{d.year}-{d.month:02d}"


def _quarter(d):
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ── cached-strike coverage per date (for CHECK 2 mechanism + counterfactual) ─
_SYM_RE = re.compile(r"SPY(\d{6})([CP])(\d{8})")


def cached_strikes(date: dt.date) -> dict:
    """Return {'C': set(int_strikes), 'P': set(int_strikes)} cached for this date."""
    ymd = date.strftime("%y%m%d")
    out = {"C": set(), "P": set()}
    for p in glob.glob(str(OPT_DIR / f"SPY{ymd}*.csv")):
        m = _SYM_RE.search(os.path.basename(p))
        if m and m.group(1) == ymd:
            out[m.group(2)].add(int(m.group(3)) // 1000)
    return out


# ── per-day fill (reuses piv geometry + sim) ───────────────────────────────
def fill_for_day(spy, d, entry_time, off, wing, pt, stop):
    spy_day = spy[spy["date"] == d]
    if spy_day.empty:
        return None
    decision_dt, spot, _ = piv._spot_and_decision(spy_day, entry_time)
    if decision_dt is None or spot is None or spot <= 0:
        return None
    legs = piv._build_variant_legs("IC", spot, off, wing)
    # PRODUCTION PARITY (OP-16 / L177): run_variant() in _pivot_premium_selling.py AND the
    # standalone null both apply this band pre-filter before pricing, so off=4
    # (longC=ATM+6 > +/-5 band) is always skipped. Omitting it here let the random-offset
    # null trade off=4 "if-cached" condors the production geometry never takes -> polluted
    # the null mean and INFLATED the actual's apparent percentile (94.8th vs the true
    # ~76th). Mirror production EXACTLY via the shared eligible() helper.
    if not piv.eligible(legs, spot):
        skip = sc.CreditFill(date=d.strftime("%Y-%m-%d"), structure="IC",
                             skipped=True, skip_reason="out_of_band")
        return skip
    f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=wing,
                                 structure_name="IC", contracts=1, pt_frac=pt,
                                 stop_mult=stop, commission_per_contract=0.65)
    return f


def spy_day_excursion(spy, d, entry_time):
    """(range_pct, move_to_close_abs_pct, max_excursion_from_entry_pct) — the directional
    pain a condor's short strikes must survive AFTER entry."""
    spy_day = spy[spy["date"] == d]
    if spy_day.empty:
        return None
    _, spot, _ = piv._spot_and_decision(spy_day, entry_time)
    if not spot or spot <= 0:
        return None
    day_open = float(spy_day.iloc[0]["open"])
    day_high = float(spy_day["high"].max())
    day_low = float(spy_day["low"].min())
    day_close = float(spy_day.iloc[-1]["close"])
    post = spy_day[spy_day["time_et"] >= entry_time]
    if post.empty:
        post = spy_day
    max_exc = max(abs(float(post["high"].max()) - spot),
                  abs(float(post["low"].min()) - spot))
    return {
        "range_pct": (day_high - day_low) / day_open * 100.0,
        "move_to_close_pct": abs(day_close - spot) / spot * 100.0,
        "max_excursion_pct": max_exc / spot * 100.0,
    }


# ── CHECK 1: independent null ──────────────────────────────────────────────
def check1_null(spy, oos_days):
    rng = random.Random(NULL_SEED)
    actual = [f.realized_pnl for d in oos_days
              if (f := fill_for_day(spy, d, ENTRY, OFF, WING, PT, 1.5)) and not f.skipped]
    actual_exp = _expc(actual)

    strike_exps, entry_exps = [], []
    for _ in range(NULL_ITERS):
        sp, ep = [], []
        for d in oos_days:
            off = rng.choice([2, 3, 4])
            f = fill_for_day(spy, d, ENTRY, off, WING, PT, 1.5)
            if f and not f.skipped:
                sp.append(f.realized_pnl)
            et = rng.choice(piv.ENTRY_TIMES_ET)
            f2 = fill_for_day(spy, d, et, OFF, WING, PT, 1.5)
            if f2 and not f2.skipped:
                ep.append(f2.realized_pnl)
        if sp:
            strike_exps.append(_expc(sp))
        if ep:
            entry_exps.append(_expc(ep))

    rs_p95, re_p95 = _pct(strike_exps, 0.95), _pct(entry_exps, 0.95)
    rs_rank = sum(1 for x in strike_exps if x < actual_exp) / len(strike_exps)
    re_rank = sum(1 for x in entry_exps if x < actual_exp) / len(entry_exps)
    beats_strike = actual_exp > rs_p95
    beats_entry = actual_exp > re_p95
    return {
        "seed": NULL_SEED, "iters": NULL_ITERS, "n_oos": len(actual),
        "actual_oos_exp": round(actual_exp, 2),
        "strike_null_mean": round(_expc(strike_exps), 2),
        "strike_null_p95": round(rs_p95, 2),
        "actual_pctile_vs_strike": round(rs_rank, 3),
        "entry_null_mean": round(_expc(entry_exps), 2),
        "entry_null_p95": round(re_p95, 2),
        "actual_pctile_vs_entry": round(re_rank, 3),
        "beats_strike_null": beats_strike,
        "beats_entry_null": beats_entry,
        "beats_null": beats_strike and beats_entry,
    }


# ── CHECK 2: band-skip survivorship ────────────────────────────────────────
def _summ(xs):
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(_expc(xs), 3),
            "median": round(statistics.median(xs), 3),
            "p90": round(_pct(xs, 0.90), 3), "max": round(max(xs), 3)}


def check2_survivorship(spy, days):
    # (a) classify every day TAKEN vs SKIPPED for the LEAD geometry; tally skip reason.
    reasons = {}
    taken_days, skipped_days = [], []
    for d in days:
        f = fill_for_day(spy, d, ENTRY, OFF, WING, PT, 1.5)
        if f is None:
            reasons["no_spy_or_spot"] = reasons.get("no_spy_or_spot", 0) + 1
            continue
        if f.skipped:
            key = f.skip_reason.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
            skipped_days.append(d)
        else:
            taken_days.append(d)
    n = len(taken_days) + len(skipped_days)
    skip_rate = len(skipped_days) / n if n else 0.0

    # (b) SPY excursion distributions: TRADED vs SKIPPED (full + OOS).
    def exc_split(day_subset):
        rng_, mtc, mxe = [], [], []
        for d in day_subset:
            e = spy_day_excursion(spy, d, ENTRY)
            if e:
                rng_.append(e["range_pct"])
                mtc.append(e["move_to_close_pct"])
                mxe.append(e["max_excursion_pct"])
        return rng_, mtc, mxe

    t_rng, t_mtc, t_mxe = exc_split(taken_days)
    s_rng, s_mtc, s_mxe = exc_split(skipped_days)
    oos_taken = [d for d in taken_days if d >= OOS_START]
    oos_skip = [d for d in skipped_days if d >= OOS_START]
    ot_rng, ot_mtc, ot_mxe = exc_split(oos_taken)
    os_rng, os_mtc, os_mxe = exc_split(oos_skip)

    # (c) force-a-trade counterfactual: on each SKIPPED day, build the off2/w2 IC
    #     re-centered on the day's CACHED band (nearest cached ATM where BOTH a C & P
    #     leg exist at every needed strike). Price it; tally priceable + EV. Then
    #     compare combined EV (taken + forced) vs taken-only.
    forced_pnls, forced_priceable, forced_unpriceable = [], 0, 0
    for d in skipped_days:
        spy_day = spy[spy["date"] == d]
        decision_dt, spot, _ = piv._spot_and_decision(spy_day, ENTRY)
        if decision_dt is None or not spot:
            forced_unpriceable += 1
            continue
        cs = cached_strikes(d)
        both = sorted(cs["C"] & cs["P"])
        if not both:
            forced_unpriceable += 1
            continue
        # nearest cached center s.t. center+/-2 (shorts) and center+/-4 (longs) all cached
        atm_round = int(round(spot))
        center = None
        for c in sorted(both, key=lambda k: abs(k - atm_round)):
            need = {c - OFF, c - (OFF + WING), c + OFF, c + (OFF + WING)}
            if (need <= cs["P"] | cs["C"]
                    and {c - OFF, c - (OFF + WING)} <= cs["P"]
                    and {c + OFF, c + (OFF + WING)} <= cs["C"]):
                center = c
                break
        if center is None:
            forced_unpriceable += 1
            continue
        legs = [Leg(center - OFF, "P", -1), Leg(center - (OFF + WING), "P", +1),
                Leg(center + OFF, "C", -1), Leg(center + (OFF + WING), "C", +1)]
        f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=WING,
                                     structure_name="IC", contracts=1, pt_frac=PT,
                                     stop_mult=1.5, commission_per_contract=0.65)
        if f.skipped:
            forced_unpriceable += 1
        else:
            forced_priceable += 1
            forced_pnls.append(f.realized_pnl)

    taken_pnls = [f.realized_pnl for d in taken_days
                  if (f := fill_for_day(spy, d, ENTRY, OFF, WING, PT, 1.5)) and not f.skipped]
    combined = taken_pnls + forced_pnls
    return {
        "n_days": n, "n_taken": len(taken_days), "n_skipped": len(skipped_days),
        "skip_rate": round(skip_rate, 3), "skip_reasons": reasons,
        "excursion_full": {
            "taken": {"range_pct": _summ(t_rng), "move_to_close_pct": _summ(t_mtc),
                      "max_excursion_pct": _summ(t_mxe)},
            "skipped": {"range_pct": _summ(s_rng), "move_to_close_pct": _summ(s_mtc),
                        "max_excursion_pct": _summ(s_mxe)},
        },
        "excursion_oos": {
            "taken": {"range_pct": _summ(ot_rng), "move_to_close_pct": _summ(ot_mtc),
                      "max_excursion_pct": _summ(ot_mxe)},
            "skipped": {"range_pct": _summ(os_rng), "move_to_close_pct": _summ(os_mtc),
                        "max_excursion_pct": _summ(os_mxe)},
        },
        "forced_trade_counterfactual": {
            "skip_days_total": len(skipped_days),
            "forced_priceable": forced_priceable,
            "forced_unpriceable": forced_unpriceable,
            "forced_only_expectancy": round(_expc(forced_pnls), 2),
            "forced_only_wr": round(sum(1 for p in forced_pnls if p > 0) / len(forced_pnls), 3)
                              if forced_pnls else 0.0,
            "taken_only_expectancy": round(_expc(taken_pnls), 2),
            "combined_expectancy": round(_expc(combined), 2),
            "ev_flips_negative_when_forced": _expc(combined) < 0,
        },
    }


# ── CHECK 3: posQ re-spec (monthly + combined-quarter) ─────────────────────
def check3_posq(spy, days):
    res = {}
    for stop in STOP_VARIANTS:
        taken = [(d, f.realized_pnl) for d in days
                 if (f := fill_for_day(spy, d, ENTRY, OFF, WING, PT, stop)) and not f.skipped]
        oos = [(d, p) for d, p in taken if d >= OOS_START]
        by_m, by_q_all = {}, {}
        for d, p in oos:
            by_m.setdefault(_month(d), []).append(p)
        for d, p in taken:
            by_q_all.setdefault(_quarter(d), []).append(p)
        pos_m = sum(1 for v in by_m.values() if len(v) >= 2 and _expc(v) > 0)
        pos_q_all = sum(1 for v in by_q_all.values() if len(v) >= 2 and _expc(v) > 0)
        res[("EOD" if stop is None else f"{stop}x")] = {
            "posMonth_oos": pos_m, "n_oos_months": len(by_m),
            "posQ_combined_IS_OOS": pos_q_all, "n_combined_quarters": len(by_q_all),
            "month_means": {k: round(_expc(v), 2) for k, v in sorted(by_m.items())},
            "passes_posMonth_4of6": pos_m >= 4,
        }
    return res


# ── CHECK 4: intrabar-stop honesty ─────────────────────────────────────────
def check4_intrabar(spy, days):
    res = {}
    for stop in STOP_VARIANTS:
        taken, extra, oos_taken, oos_extra = 0, 0, 0, 0
        actual_stops, oos_actual_stops = 0, 0
        for d in days:
            f = fill_for_day(spy, d, ENTRY, OFF, WING, PT, stop)
            if f is None or f.skipped:
                continue
            taken += 1
            is_oos = d >= OOS_START
            if is_oos:
                oos_taken += 1
            if stop is not None and f.exit_reason == "STOP":
                actual_stops += 1
                if is_oos:
                    oos_actual_stops += 1
            if f.intrabar_stop_would_hit:
                extra += 1
                if is_oos:
                    oos_extra += 1
        label = "EOD" if stop is None else f"{stop}x"
        res[label] = {
            "stop_active": stop is not None,
            "n_taken": taken, "n_oos": oos_taken,
            "actual_close_basis_stops": actual_stops,
            "intrabar_extra_would_hit": extra,
            "intrabar_extra_rate": round(extra / taken, 3) if taken else 0.0,
            "oos_actual_stops": oos_actual_stops,
            "oos_intrabar_extra_would_hit": oos_extra,
            "note": ("EOD-only variant has NO stop -> intrabar-stop dishonesty N/A, but the "
                     "trade-off is an UNCAPPED-intraday hold (defined-risk wing the only cap)")
                    if stop is None else
                    "trades where intrabar-worst MTM <= stop but bar.close did NOT -> real "
                    "fills would have stopped these out; close-basis EV is OPTIMISTIC",
        }
    return res


def main():
    spy = piv._load_spy_master()
    cache_dates = piv._option_cache_dates()
    days = sorted(cache_dates & set(spy["date"].unique()))
    oos_days = [d for d in days if d >= OOS_START]
    print(f"[ic-validate] days={len(days)} ({days[0]}..{days[-1]}) OOS={len(oos_days)}")
    print(f"[ic-validate] LEAD = {STRUCT} {ENTRY.strftime('%H:%M')} off{OFF} w{WING} pt{PT}\n")

    print("[1/4] null (independent re-seed)...")
    c1 = check1_null(spy, oos_days)
    print(f"  actual OOS ${c1['actual_oos_exp']} | strike-null p95 ${c1['strike_null_p95']} "
          f"(actual pctile {c1['actual_pctile_vs_strike']:.0%}) "
          f"| entry-null p95 ${c1['entry_null_p95']} -> beats_null={c1['beats_null']}")

    print("[2/4] band-skip survivorship...")
    c2 = check2_survivorship(spy, days)
    ef = c2["excursion_full"]
    print(f"  skip_rate={c2['skip_rate']:.1%} reasons={c2['skip_reasons']}")
    print(f"  FULL move_to_close%: taken median={ef['taken']['move_to_close_pct'].get('median')} "
          f"vs skipped median={ef['skipped']['move_to_close_pct'].get('median')}")
    print(f"  FULL max_excursion%: taken median={ef['taken']['max_excursion_pct'].get('median')} "
          f"vs skipped median={ef['skipped']['max_excursion_pct'].get('median')}")
    fc = c2["forced_trade_counterfactual"]
    print(f"  forced-trade: priceable {fc['forced_priceable']}/{fc['skip_days_total']} "
          f"forced_exp=${fc['forced_only_expectancy']} combined_exp=${fc['combined_expectancy']} "
          f"flips_neg={fc['ev_flips_negative_when_forced']}")

    print("[3/4] posQ re-spec...")
    c3 = check3_posq(spy, days)
    for k, v in c3.items():
        print(f"  {k}: posMonth={v['posMonth_oos']}/{v['n_oos_months']} "
              f"posQ(IS+OOS)={v['posQ_combined_IS_OOS']}/{v['n_combined_quarters']} "
              f"pass4of6={v['passes_posMonth_4of6']}")

    print("[4/4] intrabar-stop honesty...")
    c4 = check4_intrabar(spy, days)
    for k, v in c4.items():
        print(f"  {k}: n={v['n_taken']} close-stops={v['actual_close_basis_stops']} "
              f"intrabar-extra={v['intrabar_extra_would_hit']} "
              f"({v['intrabar_extra_rate']:.0%})")

    report = {
        "lead_cell": f"{STRUCT} {ENTRY.strftime('%H:%M')} off{OFF} w{WING} pt{PT} stop1.5x",
        "data_window": f"{days[0]}..{days[-1]}",
        "n_days": len(days), "n_oos": len(oos_days),
        "check1_null": c1, "check2_survivorship": c2,
        "check3_posq": c3, "check4_intrabar": c4,
    }
    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[ic-validate] wrote {OUT}")


if __name__ == "__main__":
    main()
