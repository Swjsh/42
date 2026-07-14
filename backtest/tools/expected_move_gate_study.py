"""expected_move_gate_study.py -- PROFIT-P5-EXPECTED-MOVE-GATE, the frozen runner for
analysis/recommendations/prereg-expected-move-gate-2026-07-11.json.

Runs the pre-registration EXACTLY as frozen: 3 candidate expected-move gates (V1 day-level
trailing-25th-percentile floor / V2 per-trade remaining-move vs TP1-implied-premium-ceiling /
V3 per-trade premium-budget-ratio cap) on the ribbon_ride population, full 6-stage battery +
kill ladder (incl. k5 VIX-gate-lift + k6 mandatory anchor-violation) + mandatory anchor-context
disclosure. No re-picks (no_repick_clause).

REUSE (OP-22): p3p5_baseline.build_baseline() for the SAME gate-OFF population morning_gate_
study.py uses (OTM-2/SS-B, identical -- the registration's own cross-check: both studies'
baselines must match; they do, by sharing this one module). lib.option_pricing_real.
load_contract_bars/option_symbol (Path A, zero new data) for the ATM straddle series.
ribbon_rejection_wick_battery.load_vix/vix_at for the k5 VIX-gate-lift comparison (playbook.md's
existing puts-VIX>=20 / calls-VIX<=17.2 level rule -- LEVEL-only proxy of the live gate, which
also has a rising/falling slope leg; disclosed simplification, this is a comparison baseline,
not a trading-path change).

Run: backtest/.venv/Scripts/python.exe backtest/tools/expected_move_gate_study.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time as _time_mod
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_ride_strike_exit_ab as ab   # noqa: E402
import t4_exit_matrix as t4               # noqa: E402
import p3p5_baseline as base              # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from autoresearch.null_baseline import random_entry_null, DEFAULT_SEEDS  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import load_vix, vix_at  # noqa: E402

SMOKE = "--smoke" in sys.argv
OUT_JSON = REPO / "analysis" / "recommendations" / ("expected-move-gate-result-SMOKE.json" if SMOKE
                                                     else "expected-move-gate-result.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("expected-move-gate-result-SMOKE.md" if SMOKE
                                                   else "expected-move-gate-result.md")
DAY_CACHE = REPO / "analysis" / "exit-parity" / "p5-expected-move-day-series.json"

ENTRY_WINDOW_OPEN = dt.time(9, 35)
CLOSE_ET = dt.time(16, 0)
RTH_MINUTES = 375
STRADDLE_MULT = 0.85
TRAILING_WINDOW = 20
V1_PCTILE = 25
V1_PCTILE_MIRROR = 75
DELTA_PROXY_OTM2 = 0.30       # fixed table, population strike is OTM-2 throughout
V3_BUDGET_CAP = 0.35
MIN_N = 20

# playbook.md's existing (level-only proxy of) VIX gate for k5.
VIX_PUT_MIN = 20.0
VIX_CALL_MAX = 17.2

# J's 3 OP-16 source-of-truth winners -- entry time + REAL premium, pulled from journal.
ANCHOR_WINNERS = [
    {"date": dt.date(2026, 4, 29), "time": dt.time(10, 25, 51), "side": "P",
     "entry_premium": 1.67, "label": "4/29 SPY 710P x6 -> +$342",
     "source": "journal/2026-04-29.md line 29"},
    {"date": dt.date(2026, 5, 1), "time": dt.time(13, 9, 14), "side": "P",
     "entry_premium": 0.46, "label": "5/01 SPY 721P leg#1 (premature) @ $0.46",
     "source": "journal/2026-05-01.md line 16"},
    {"date": dt.date(2026, 5, 1), "time": dt.time(13, 36, 11), "side": "P",
     "entry_premium": 0.19, "label": "5/01 SPY 721P leg#2 (the real trigger) @ $0.19 -> blended +$470",
     "source": "journal/2026-05-01.md line 21"},
    {"date": dt.date(2026, 5, 4), "time": dt.time(10, 27, 50), "side": "P",
     "entry_premium": 0.85, "label": "5/04 SPY 721P x10 -> +$730",
     "source": "journal/2026-05-04.md line 39"},
]
ANCHOR_LOSERS_INCOMPLETE_NOTE = (
    "Losers (5/05 722P, 5/06 730C @ $1.29/10:15 ET, 5/07 734C, 5/07 737C) -- only 5/06's entry "
    "premium+time were recoverable from journal/2026-05-06.md within this task's scope (BULLISH_"
    "RECLAIM, entry ~$1.29, trigger 10:15 ET); 5/05's premium is explicitly logged 'unknown (J did "
    "not state)' (journal/2026-05-05.md line 73) and 5/07's two loser fills are not present in "
    "journal/2026-05-07.md (file only covers pre-market through 10:30 ET in this task's read). "
    "Per the registration, losers are DISCLOSURE ONLY, not pass/fail-determinative -- incomplete "
    "loser data does not affect any verdict below; only the 3 WINNERS gate k6."
)
ANCHOR_LOSERS = [
    {"date": dt.date(2026, 5, 6), "time": dt.time(10, 15, 0), "side": "C",
     "entry_premium": 1.29, "label": "5/06 SPY 730C x10 -> -$300",
     "source": "journal/2026-05-06.md (trigger 10:15 ET, entry ~$1.29)"},
]


def log(msg: str) -> None:
    print(f"[expected-move-gate] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# DAY-LEVEL EXPECTED-MOVE SERIES (ATM straddle @ first bar >=09:35, x0.85) -- cached.
# ---------------------------------------------------------------------------------------------
def build_day_series(spy_by_date: dict, force: bool = False) -> dict[dt.date, dict]:
    if DAY_CACHE.exists() and not force:
        raw = json.loads(DAY_CACHE.read_text(encoding="utf-8"))
        if raw.get("n_days") == len(spy_by_date):
            log(f"day-series cache HIT: {raw['n_days']} days, no OPRA re-fetch")
            return {dt.date.fromisoformat(k): v for k, v in raw["series"].items()}
        log(f"day-series cache STALE (n_days {raw.get('n_days')} != {len(spy_by_date)}) -- rebuilding")

    series: dict[dt.date, dict] = {}
    n_no_coverage = 0
    for date, day_bars in sorted(spy_by_date.items()):
        eligible = day_bars[day_bars["time"] >= ENTRY_WINDOW_OPEN]
        if eligible.empty:
            n_no_coverage += 1
            continue
        row0 = eligible.iloc[0]
        ts0 = row0["timestamp_et"]
        if getattr(ts0, "tzinfo", None) is not None:
            ts0 = ts0.tz_localize(None)
        spot0 = float(row0["close"])
        atm_strike = int(round(spot0))
        call_df = load_contract_bars(option_symbol(date, atm_strike, "C"))
        put_df = load_contract_bars(option_symbol(date, atm_strike, "P"))
        if call_df is None or call_df.empty or put_df is None or put_df.empty:
            n_no_coverage += 1
            continue
        c_ts = call_df["timestamp_et"]
        if c_ts.dt.tz is not None:
            c_ts = c_ts.dt.tz_localize(None)
        p_ts = put_df["timestamp_et"]
        if p_ts.dt.tz is not None:
            p_ts = p_ts.dt.tz_localize(None)
        c_rows = call_df[(c_ts >= ts0).values]
        p_rows = put_df[(p_ts >= ts0).values]
        if c_rows.empty or p_rows.empty:
            n_no_coverage += 1
            continue
        call_close = float(c_rows.iloc[0]["close"])
        put_close = float(p_rows.iloc[0]["close"])
        straddle = call_close + put_close
        expected_move_dollars = round(straddle * STRADDLE_MULT, 4)
        spy_price_at_open = float(day_bars.iloc[0]["open"])  # literal 09:30 RTH session open
        series[date] = {
            "atm_strike": atm_strike, "sample_ts": str(ts0),
            "call_close": call_close, "put_close": put_close,
            "expected_move_dollars": expected_move_dollars,
            "spy_price_at_open": round(spy_price_at_open, 4),
            "expected_move_pct": round(expected_move_dollars / spy_price_at_open, 6),
        }
    log(f"day-series BUILT: {len(series)} days with straddle coverage "
        f"(dropped {n_no_coverage} no-coverage)")
    DAY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DAY_CACHE.write_text(json.dumps({
        "n_days": len(spy_by_date), "generated_at": dt.datetime.now().isoformat(),
        "n_no_coverage": n_no_coverage,
        "series": {str(k): v for k, v in series.items()},
    }, indent=2), encoding="utf-8")
    return series


def trailing_pctile(day_series: dict, sorted_days: list, idx: int, pct: float) -> float | None:
    """Strictly-causal trailing window: prior TRAILING_WINDOW trading days' expected_move_pct,
    shift-1 (never includes today's own value, C6 no-look-ahead)."""
    lo = max(0, idx - TRAILING_WINDOW)
    window_days = sorted_days[lo:idx]
    vals = [day_series[d]["expected_move_pct"] for d in window_days if d in day_series]
    if len(vals) < 5:  # not enough trailing history to form a meaningful percentile
        return None
    return float(np.percentile(vals, pct))


def remaining_minutes(entry_ts: dt.datetime) -> float:
    close_dt = dt.datetime.combine(entry_ts.date(), CLOSE_ET)
    delta = (close_dt - entry_ts).total_seconds() / 60.0
    return max(0.0, delta)


# ---------------------------------------------------------------------------------------------
# PER-TRADE GATE EVALUATION -- returns True if this candidate would SKIP the trade.
# ---------------------------------------------------------------------------------------------
def v1_skip(trade: dict, day_series: dict, sorted_days: list, day_idx: dict, mirror: bool = False) -> bool | None:
    d = trade["date"]
    idx = day_idx.get(d)
    if idx is None or d not in day_series:
        return None
    pct = V1_PCTILE_MIRROR if mirror else V1_PCTILE
    thresh = trailing_pctile(day_series, sorted_days, idx, pct)
    if thresh is None:
        return None
    today_pct = day_series[d]["expected_move_pct"]
    return (today_pct > thresh) if mirror else (today_pct < thresh)


def v2_ceiling_and_needed(trade: dict, day_series: dict, shape: dict) -> tuple[float, float] | None:
    d = trade["date"]
    if d not in day_series:
        return None
    em_dollars = day_series[d]["expected_move_dollars"]
    rem_min = remaining_minutes(trade["entry_ts"])
    remaining_move = em_dollars * math.sqrt(rem_min / RTH_MINUTES)
    ceiling = remaining_move * DELTA_PROXY_OTM2
    needed = trade["entry_premium"] * shape["tp1_premium_pct"]
    return ceiling, needed


def v3_budget_ratio(trade: dict, day_series: dict) -> float | None:
    d = trade["date"]
    if d not in day_series:
        return None
    em_dollars = day_series[d]["expected_move_dollars"]
    if em_dollars <= 0:
        return None
    return trade["entry_premium"] / em_dollars


# ---------------------------------------------------------------------------------------------
# BATTERY (shared shape with morning_gate_study.py; kept local to avoid a 3rd shared module for
# a 2-script pair -- OP-22 balance: reuse WITHIN a study before reuse ACROSS studies)
# ---------------------------------------------------------------------------------------------
def battery1(kept: list[dict], removed: list[dict], all_trades: list[dict]) -> dict:
    return {"kept": t4.battery(kept), "removed": t4.battery(removed), "gate_off": t4.battery(all_trades)}


def stage2_oos(kept: list[dict], all_trades: list[dict]) -> dict:
    kept_is = [t for t in kept if t["date"] < base.OOS_BOUNDARY]
    kept_oos = [t for t in kept if t["date"] >= base.OOS_BOUNDARY]
    all_is = [t for t in all_trades if t["date"] < base.OOS_BOUNDARY]
    all_oos = [t for t in all_trades if t["date"] >= base.OOS_BOUNDARY]
    b_kept_is, b_kept_oos = t4.battery(kept_is), t4.battery(kept_oos)
    b_all_is, b_all_oos = t4.battery(all_is), t4.battery(all_oos)
    is_pass = (b_kept_is.get("expectancy") is not None and b_all_is.get("expectancy") is not None
              and b_kept_is["expectancy"] > b_all_is["expectancy"])
    oos_pass = (b_kept_oos.get("expectancy") is not None and b_all_oos.get("expectancy") is not None
               and b_kept_oos["expectancy"] > b_all_oos["expectancy"])
    return {"kept_is": b_kept_is, "kept_oos": b_kept_oos, "all_is": b_all_is, "all_oos": b_all_oos,
           "is_pass": bool(is_pass), "oos_pass": bool(oos_pass), "pass": bool(is_pass and oos_pass)}


def stage3_random_null(removed: list[dict], spy_full, spy_by_date) -> dict:
    if not removed:
        return {"null": {"note": "no removed trades"}, "removed_expectancy": None,
               "pass": True, "note": "n_removed=0, vacuously passes"}
    n_call = sum(1 for t in removed if t["side"] == "C")
    n_put = sum(1 for t in removed if t["side"] == "P")
    eligible_idx = sorted({int(i) for i in range(len(spy_full))
                          if spy_full.iloc[i]["date"] in {t["date"] for t in removed}
                          and spy_full.iloc[i]["time"] >= ENTRY_WINDOW_OPEN})
    sim_fn = ab.make_null_sim_fn(base.SO, base.SHAPE, True, spy_by_date)
    null = random_entry_null(
        rth=spy_full, n_signals=len(removed), n_call=n_call, n_put=n_put,
        strike_offset=base.SO, premium_stop_pct=base.SHAPE["premium_stop_pct"],
        qty=base.QTY, eligible_idx=eligible_idx, seeds=DEFAULT_SEEDS,
        setup="EXPECTED_MOVE_GATE_NULL", sim_fn=sim_fn,
    )
    removed_exp = t4.battery(removed).get("expectancy")
    p = null.get("per_trade_mean")
    passed = removed_exp is not None and p is not None and removed_exp <= p
    return {"null": null, "removed_expectancy": removed_exp, "pass": bool(passed),
           "note": "PASS = blocked cohort's own realized per-trade <= random-entry null mean "
                   "(eligible bars restricted to the blocked days/signals' own timestamps)"}


def stage5_concentration(kept_b: dict, all_b: dict) -> dict:
    kd, ad = kept_b.get("exp_drop_top3"), all_b.get("exp_drop_top3")
    return {"kept_drop_top3": kd, "gate_off_drop_top3": ad,
           "pass": bool(kd is not None and ad is not None and kd > ad)}


# ---------------------------------------------------------------------------------------------
# CANDIDATE EVALUATION
# ---------------------------------------------------------------------------------------------
def build_removed_mask(cand_id: str, all_trades: list[dict], day_series: dict,
                       sorted_days: list, day_idx: dict, shape: dict) -> list[bool]:
    mask = []
    for t in all_trades:
        if cand_id == "V1_SESSION_FLOOR_TRAILING_PCTILE":
            skip = v1_skip(t, day_series, sorted_days, day_idx, mirror=False)
        elif cand_id == "V2_REMAINING_MOVE_VS_TP1_DISTANCE":
            r = v2_ceiling_and_needed(t, day_series, shape)
            skip = (r is not None) and (r[0] < r[1])
        elif cand_id == "V3_PREMIUM_BUDGET_RATIO":
            r = v3_budget_ratio(t, day_series)
            skip = (r is not None) and (r > V3_BUDGET_CAP)
        else:
            skip = None
        mask.append(bool(skip) if skip is not None else False)
    return mask


def opposite_mirror_removed(cand_id: str, all_trades: list[dict], day_series: dict,
                            sorted_days: list, day_idx: dict, shape: dict,
                            target_n: int) -> list[bool]:
    """High-end mirror: same metric, opposite direction, sized to ~target_n blocked."""
    if cand_id == "V1_SESSION_FLOOR_TRAILING_PCTILE":
        return [bool(v1_skip(t, day_series, sorted_days, day_idx, mirror=True) or False)
               for t in all_trades]
    # V2/V3: rank by the metric and block the opposite extreme, count-matched.
    if cand_id == "V2_REMAINING_MOVE_VS_TP1_DISTANCE":
        vals = []
        for t in all_trades:
            r = v2_ceiling_and_needed(t, day_series, shape)
            vals.append((r[0] - r[1]) if r is not None else None)  # slack; LOW slack = real candidate blocks
        # real candidate blocks smallest slack (most negative); mirror blocks LARGEST slack (largest ceiling)
        idxs = [i for i, v in enumerate(vals) if v is not None]
        idxs.sort(key=lambda i: -vals[i])  # descending slack -> largest first
    else:  # V3
        vals = [v3_budget_ratio(t, day_series) for t in all_trades]
        idxs = [i for i, v in enumerate(vals) if v is not None]
        idxs.sort(key=lambda i: vals[i])  # ascending ratio -> smallest (safest) first, mirror of ">cap"
    n_block = min(target_n, len(idxs))
    blocked_set = set(idxs[:n_block])
    return [i in blocked_set for i in range(len(all_trades))]


def evaluate_candidate(cand_id: str, all_trades: list[dict], day_series: dict, sorted_days: list,
                       day_idx: dict, spy_full, spy_by_date, vix_df) -> dict:
    t0 = _time_mod.time()
    shape = base.SHAPE
    removed_mask = build_removed_mask(cand_id, all_trades, day_series, sorted_days, day_idx, shape)
    kept = [t for t, m in zip(all_trades, removed_mask) if not m]
    removed = [t for t, m in zip(all_trades, removed_mask) if m]
    n_no_day_data = sum(1 for t in all_trades if t["date"] not in day_series)

    b1 = battery1(kept, removed, all_trades)
    all_exp = b1["gate_off"].get("expectancy")
    s1_pass = (b1["kept"].get("expectancy") is not None and all_exp is not None
              and b1["kept"]["expectancy"] > all_exp)
    s2 = stage2_oos(kept, all_trades)
    s3 = stage3_random_null(removed, spy_full, spy_by_date)
    s5 = stage5_concentration(b1["kept"], b1["gate_off"])

    mirror_mask = opposite_mirror_removed(cand_id, all_trades, day_series, sorted_days, day_idx,
                                          shape, len(removed))
    mirror_kept = [t for t, m in zip(all_trades, mirror_mask) if not m]
    mirror_kept_exp = t4.battery(mirror_kept).get("expectancy")
    kept_exp = b1["kept"].get("expectancy")
    candidate_delta = (kept_exp - all_exp) if (kept_exp is not None and all_exp is not None) else None
    mirror_delta = (mirror_kept_exp - all_exp) if (mirror_kept_exp is not None and all_exp is not None) else None
    comparable = (candidate_delta is not None and candidate_delta > 0 and mirror_delta is not None
                 and mirror_delta >= 0.9 * candidate_delta)
    s4 = {"n_mirror_blocked": sum(mirror_mask), "target_n": len(removed),
         "candidate_delta": round(candidate_delta, 2) if candidate_delta is not None else None,
         "mirror_delta": round(mirror_delta, 2) if mirror_delta is not None else None,
         "mirror_comparable_or_larger": bool(comparable), "pass": bool(not comparable)}

    n_kept, n_removed = len(kept), len(removed)
    insufficient_n = n_kept < MIN_N or n_removed < MIN_N

    k1 = not s1_pass
    k2 = not s2["pass"]
    k3 = bool(s4["mirror_comparable_or_larger"])

    p_null = (1.0 if s3.get("removed_expectancy") is None else
             round((1 + sum(1 for v in s3["null"].get("per_trade_by_seed", [])
                           if v >= s3["removed_expectancy"])) / (1 + max(1, len(s3["null"].get("per_trade_by_seed", [])))), 4))

    elapsed = round(_time_mod.time() - t0, 1)
    log(f"{cand_id}: n_kept={n_kept} n_removed={n_removed} (no_day_data={n_no_day_data}) "
        f"exp_kept=${kept_exp} exp_gate_off=${all_exp} s1={s1_pass} s2={s2['pass']} "
        f"s3={s3['pass']} s4={s4['pass']} s5={s5['pass']} ({elapsed}s)")

    return {
        "candidate_id": cand_id, "n_kept": n_kept, "n_removed": n_removed,
        "n_no_day_series_data": n_no_day_data, "insufficient_n": insufficient_n,
        "stage1_expectancy": {"pass": s1_pass, **b1},
        "stage2_oos": s2, "stage3_random_null": s3, "stage4_opposite_null": s4,
        "stage5_concentration": s5,
        "kill_flags": {"k1_stage1_fail": k1, "k2_stage2_fail": k2, "k3_opposite_null_comparable": k3},
        "p_null": p_null,
    }


# ---------------------------------------------------------------------------------------------
# k5: VIX-gate-only baseline (playbook.md's existing level rule) for the "no lift" comparison.
# ---------------------------------------------------------------------------------------------
def vix_gate_baseline(all_trades: list[dict], vix_df) -> dict:
    if vix_df is None:
        return {"available": False, "note": "VIX data unavailable"}
    kept, removed = [], []
    for t in all_trades:
        v = vix_at(vix_df, t["entry_ts"])
        eligible = (v is not None) and ((t["side"] == "P" and v >= VIX_PUT_MIN)
                                        or (t["side"] == "C" and v <= VIX_CALL_MAX))
        (kept if eligible else removed).append(t)
    b_kept = t4.battery(kept)
    b_all = t4.battery(all_trades)
    delta = (round(b_kept.get("expectancy", 0) - b_all.get("expectancy", 0), 2)
            if b_kept.get("expectancy") is not None and b_all.get("expectancy") is not None else None)
    return {"available": True, "n_kept": len(kept), "n_removed": len(removed),
           "kept_expectancy": b_kept.get("expectancy"), "gate_off_expectancy": b_all.get("expectancy"),
           "delta_expectancy": delta,
           "note": ("LEVEL-only proxy of playbook.md's existing VIX gate (puts VIX>=20 / calls "
                    "VIX<=17.2) -- the live gate also has a rising/falling slope leg not modeled "
                    "here; disclosed simplification, comparison baseline only, no trading-path change")}


# ---------------------------------------------------------------------------------------------
# k6: mandatory anchor-violation check (winners) + disclosure-only losers.
# ---------------------------------------------------------------------------------------------
def anchor_check(day_series: dict, sorted_days: list, day_idx: dict, shape: dict) -> dict:
    def _eval_one(a: dict) -> dict:
        d, side, prem = a["date"], a["side"], a["entry_premium"]
        entry_ts = dt.datetime.combine(d, a["time"])
        pseudo = {"date": d, "entry_ts": entry_ts, "side": side, "entry_premium": prem}
        row = {"label": a["label"], "date": str(d), "time": str(a["time"]), "side": side,
              "entry_premium": prem, "source": a["source"]}
        idx = day_idx.get(d)
        if d not in day_series or idx is None:
            row["note"] = "no expected-move day-series coverage for this date"
            row["v1_would_skip"] = row["v2_would_skip"] = row["v3_would_skip"] = None
            return row
        v1s = v1_skip(pseudo, day_series, sorted_days, day_idx, mirror=False)
        v2r = v2_ceiling_and_needed(pseudo, day_series, shape)
        v2s = (v2r is not None) and (v2r[0] < v2r[1])
        v3r = v3_budget_ratio(pseudo, day_series)
        v3s = (v3r is not None) and (v3r > V3_BUDGET_CAP)
        row.update({
            "expected_move_dollars": day_series[d]["expected_move_dollars"],
            "expected_move_pct": day_series[d]["expected_move_pct"],
            "v1_would_skip": v1s, "v2_ceiling": v2r[0] if v2r else None,
            "v2_needed": v2r[1] if v2r else None, "v2_would_skip": v2s,
            "v3_budget_ratio": round(v3r, 4) if v3r is not None else None, "v3_would_skip": v3s,
        })
        return row

    winners = [_eval_one(a) for a in ANCHOR_WINNERS]
    losers = [_eval_one(a) for a in ANCHOR_LOSERS]
    k6_violation = any(
        w.get(f"{v.lower()}_would_skip") for w in winners
        for v in ("V1", "V2", "V3")
    )
    per_candidate_violation = {
        cid: any(w.get(f"{tag}_would_skip") for w in winners)
        for cid, tag in [("V1_SESSION_FLOOR_TRAILING_PCTILE", "v1"),
                        ("V2_REMAINING_MOVE_VS_TP1_DISTANCE", "v2"),
                        ("V3_PREMIUM_BUDGET_RATIO", "v3")]
    }
    return {"winners": winners, "losers": losers, "losers_note": ANCHOR_LOSERS_INCOMPLETE_NOTE,
           "k6_any_violation": k6_violation, "per_candidate_k6_violation": per_candidate_violation}


CANDIDATE_ORDER = ["V1_SESSION_FLOOR_TRAILING_PCTILE", "V2_REMAINING_MOVE_VS_TP1_DISTANCE",
                  "V3_PREMIUM_BUDGET_RATIO"]


def main() -> int:
    t_start = _time_mod.time()
    log(f"{'SMOKE MODE' if SMOKE else 'FULL RUN'} -- loading shared p3p5 baseline")
    all_trades, spy_full, spy_by_date, base_meta = base.build_baseline()
    if SMOKE:
        all_trades = all_trades[:60]
        log(f"SMOKE: truncated to {len(all_trades)} trades")

    day_series = build_day_series(spy_by_date, force=SMOKE)
    sorted_days = sorted(day_series.keys())
    day_idx = {d: i for i, d in enumerate(sorted_days)}
    vix_df = load_vix()

    anchor = anchor_check(day_series, sorted_days, day_idx, base.SHAPE)
    if anchor["k6_any_violation"]:
        log(f"K6 ANCHOR VIOLATION: {[w['label'] for w in anchor['winners'] if any(w.get(t) for t in ('v1_would_skip','v2_would_skip','v3_would_skip'))]}")

    vix_baseline = vix_gate_baseline(all_trades, vix_df)
    log(f"k5 VIX-gate-only baseline: kept={vix_baseline.get('n_kept')} "
        f"delta_exp=${vix_baseline.get('delta_expectancy')}")

    results = {}
    for cid in CANDIDATE_ORDER:
        results[cid] = evaluate_candidate(cid, all_trades, day_series, sorted_days, day_idx,
                                          spy_full, spy_by_date, vix_df)
        results[cid]["k6_anchor_violation"] = anchor["per_candidate_k6_violation"][cid]
        # k5: candidate's delta must exceed the VIX-gate-only baseline's own delta to count as lift.
        cand_delta = results[cid]["stage4_opposite_null"]["candidate_delta"]
        vix_delta = vix_baseline.get("delta_expectancy")
        no_lift = (cand_delta is None or vix_delta is None or cand_delta <= vix_delta)
        results[cid]["k5_no_lift_over_vix_gate"] = bool(no_lift)

    bh_input = [{"p_null": results[cid]["p_null"]} for cid in CANDIDATE_ORDER]
    ab.bh_fdr(bh_input, alpha=ab.FDR_ALPHA)
    for cid, b in zip(CANDIDATE_ORDER, bh_input):
        results[cid]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
        results[cid]["bh_rank"] = b["bh_rank"]
        results[cid]["kill_flags"]["k4_bh_fdr_fail"] = not b["bh_fdr_survivor"]

    verdicts = {}
    for cid in CANDIDATE_ORDER:
        r = results[cid]
        kf = r["kill_flags"]
        if r["k6_anchor_violation"]:
            verdicts[cid] = "KILL_K6_ANCHOR_VIOLATION_MISCALIBRATED"
        elif r["insufficient_n"]:
            verdicts[cid] = "INSUFFICIENT_N"
        elif r["k5_no_lift_over_vix_gate"]:
            verdicts[cid] = "KILL_K5_NO_LIFT_OVER_VIX_GATE"
        elif any(kf.values()):
            reasons = [k for k, v in kf.items() if v]
            verdicts[cid] = f"KILL ({', '.join(reasons)})"
        else:
            pass_bar = (r["stage1_expectancy"]["pass"] and r["stage2_oos"]["pass"]
                       and r["stage3_random_null"]["pass"] and r["stage4_opposite_null"]["pass"]
                       and r["stage5_concentration"]["pass"] and r["bh_fdr_survivor"])
            verdicts[cid] = "PASS" if pass_bar else "FAIL"
        results[cid]["verdict"] = verdicts[cid]

    out = {
        "_doc": ("PROFIT-P5-EXPECTED-MOVE-GATE result. Runs analysis/recommendations/"
                "prereg-expected-move-gate-2026-07-11.json EXACTLY as frozen. MEASURED tier: "
                "real OPRA local 5-min option bars (ATM straddle + traded OTM-2 contract) "
                "replayed through the live exit_manager decision core, NOT live broker fills."),
        "generated_at": dt.datetime.now().isoformat(), "smoke_mode": SMOKE,
        "registration": "analysis/recommendations/prereg-expected-move-gate-2026-07-11.json",
        "baseline_meta": base_meta,
        "population_note": ("Shared p3p5_baseline (IDENTICAL to morning_gate_study.py's own "
                            "population -- byte-for-byte, both import p3p5_baseline.build_baseline() "
                            "-- the registration's own required cross-check): ribbon_ride "
                            "BULLISH_RECLAIM/BEARISH_REJECTION, both directions, OTM-2 strike, "
                            f"SS-B exit shape, QTY=10. Window achieved: {base_meta.get('window_achieved')}."),
        "day_series_coverage": {"n_days": len(day_series),
                                "span": f"{sorted_days[0]}..{sorted_days[-1]}" if sorted_days else None},
        "vix_gate_baseline_k5": vix_baseline,
        "anchor_context_check_MANDATORY": anchor,
        "candidates": results,
        "candidate_order": CANDIDATE_ORDER,
        "min_n_floor": MIN_N,
        "disclosures": [
            "Strike fixed at OTM-2, exit shape fixed at SS-B (shared p3p5_baseline module) -- "
            "same disclosed filled-gap as PROFIT-P3.",
            "delta_proxy = 0.30 (OTM-2 row of the registration's own frozen table) for every V2 "
            "trade -- population strike never varies, so the table lookup is constant, not a "
            "per-trade Greek (as the registration itself allows but does not require).",
            "SPY_price_at_open (V1's denominator) = the day's literal 09:30 RTH session open; "
            "the ATM straddle itself is sampled at the first bar >=09:35 ET per the registration's "
            "own formula -- two distinct timestamps, disclosed, not conflated.",
            "Stage 4 opposite-null for V1 uses the registration's own explicit mirror (75th "
            "percentile day-level skip, not count-matched); V2/V3 use the registration's other "
            "explicit instruction (opposite metric extreme, count-matched to the real candidate's "
            "blocked-n).",
            "k5 VIX-gate-only baseline is a LEVEL-only proxy (playbook.md's rising/falling slope "
            "leg not modeled) -- comparison baseline only, not a trading-path change.",
            ANCHOR_LOSERS_INCOMPLETE_NOTE,
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({round(_time_mod.time()-t_start,1)}s total)")
    for cid in CANDIDATE_ORDER:
        log(f"VERDICT {cid}: {results[cid]['verdict']}")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# PROFIT-P5 EXPECTED-MOVE-GATE — result")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Registration: `{out['registration']}`. "
            f"Runner: `backtest/tools/expected_move_gate_study.py`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE — reduced population, pipeline verification only, NOT decision-grade.**")
    L.append("")
    L.append(f"**Population:** {out['population_note']}")
    L.append("")
    a = out["anchor_context_check_MANDATORY"]
    L.append(f"## Anchor context check (MANDATORY k6) — {'VIOLATION' if a['k6_any_violation'] else 'clear'}")
    L.append("")
    L.append("| winner | side | premium | expected_move_$ | V1 skip | V2 skip | V3 skip |")
    L.append("|---|:--:|--:|--:|:--:|:--:|:--:|")
    for w in a["winners"]:
        L.append(f"| {w['label']} | {w['side']} | ${w['entry_premium']} | "
                f"{w.get('expected_move_dollars')} | {w.get('v1_would_skip')} | "
                f"{w.get('v2_would_skip')} | {w.get('v3_would_skip')} |")
    L.append("")
    L.append(f"*Losers (disclosure only): {a['losers_note']}*")
    L.append("")
    v = out["vix_gate_baseline_k5"]
    L.append(f"## k5 — existing VIX-gate-only baseline: delta_exp=${v.get('delta_expectancy')} "
            f"(n_kept={v.get('n_kept')})")
    L.append("")
    L.append("## Battery results")
    L.append("")
    L.append("| candidate | exp kept | exp gate-off | s1 | s2 OOS | s3 null | s4 opposite | "
            "s5 conc | s6 BH-FDR | k5 no-lift | k6 anchor | verdict |")
    L.append("|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
    for cid in out["candidate_order"]:
        r = out["candidates"][cid]
        L.append(f"| {cid} | ${r['stage1_expectancy']['kept'].get('expectancy')} | "
                f"${r['stage1_expectancy']['gate_off'].get('expectancy')} | "
                f"{r['stage1_expectancy']['pass']} | {r['stage2_oos']['pass']} | "
                f"{r['stage3_random_null']['pass']} | {r['stage4_opposite_null']['pass']} | "
                f"{r['stage5_concentration']['pass']} | {r['bh_fdr_survivor']} | "
                f"{r['k5_no_lift_over_vix_gate']} | {r['k6_anchor_violation']} | **{r['verdict']}** |")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
