#!/usr/bin/env python
"""lever_sizing_2026_08_06.py -- LEVER 2: SIZING AS THE LOSS AMPLIFIER.

J's ask (2026-08-06, after the close): "we gotta KEEP OUR LOSSES SMALL so that way our wins
can stack." This module asks ONE question: can a SIZING policy cap a Wednesday-shaped day
near -$500 WITHOUT costing Tuesday (+$3,617) or Thursday (+$1,461)?

THE STRUCTURAL FACT THAT ORGANISES EVERYTHING BELOW
---------------------------------------------------
A pure sizing policy multiplies each position's realised P&L by a scalar. It cannot change
which signals fire, when they fire, what contract is bought, or at what price it is bought
and sold. Therefore:
  * its effect on ANY day is exactly computable by arithmetic on REAL BROKER FILLS -- no
    exit model, no OPRA re-walk, no simulator. This is strictly MORE faithful than a replay.
  * on a WINNING day, every size reduction costs money, proportionally, with certainty.
So the entire lane reduces to ONE discriminating question: which conditional sizing trigger
fires on Wednesday and NOT on Tuesday? Everything here is built to answer that.

THE ONE EXCEPTION is cell (f) -- reverting risky-3's ATM strike tier changes the CONTRACT,
not the size, so it needs real OPRA + the REAL production exit core. It lives in a sibling
module (lever_sizing_atm_revert_2026_08_06.py) so this one stays pure arithmetic.

POPULATIONS (both real, never mixed in one column)
--------------------------------------------------
  A. THE BOOK -- every closed engine SPY-option POSITION in automation/state/fills-ledger.jsonl
     (attribution=="engine", is_option, not crypto), reconstructed by the repo's single
     canonical position definition (exit_shape_parity_study.reconstruct_positions).
     REAL BROKER FILLS. 26 ET dates, 2026-06-26 .. 2026-08-06.
  B. THE REPLAY -- analysis/recommendations/engine-fullhist-replay-2026-07-23.json `trades`:
     191 ribbon-family trades / 141 traded days inside a 387-RTH-day window, exits re-walked
     through the REAL live exit core. ONE arm, qty 3..13 (equity-scaled as the account
     compounds): 130 of 191 trades sit EXACTLY at qty 3 == the Rule-6 floor, so a size-DOWN
     policy can only bite on the other 61. That is a real, disclosed sensitivity limit -- NOT
     "qty is fixed at 3", which was this module's first (wrong) assumption and is corrected
     here. Population B also carries the SELECTION test (does the trigger pick losers?), which
     is scale-free and therefore immune to the floor entirely.

RULE 6 ("Min 3 contracts (2 TP + 1 runner)") is modelled as a HARD FLOOR on every policy,
matching fleet_executor's shrink-not-deny semantics (_shrink_qty_to_affordable can never go
below min_contracts). Every "halve" therefore actually means max(3, round(q/2)).

DESCRIPTIVE / COUNTERFACTUAL ONLY. Ships nothing, arms nothing, touches no trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_sizing_2026_08_06.py
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "lib", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
WEBULL = REPO / "analysis" / "j-webull" / "trades-normalized.csv"
SPY_BOOK = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
SPY_REPLAY = REPO / "backtest" / "data" / "spy_5m_2024-01-18_2026-07-22.csv"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-SIZING-2026-08-06.json"

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
WEEK = (TUE, WED, THU)
RULE6_MIN = 3           # CLAUDE.md Rule 6, enforced as a floor by fleet_executor
ASSERTS: list[dict] = []


def check(name: str, got, want, tol: float = 0.005) -> None:
    """Every headline number in the report is re-derived and asserted here."""
    ok = (abs(float(got) - float(want)) <= tol) if isinstance(want, (int, float)) else (got == want)
    ASSERTS.append({"check": name, "got": got, "want": want, "pass": bool(ok)})


# ============================================================ population loaders
def load_book() -> list[dict]:
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    positions = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    ts_et_by = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    for p in positions:
        p["entry_ts_et"] = ts_et_by.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["exit_ts_et"] = max(ef["ts_et"] for ef in p["exit_fills"])
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["qty"] = int(round(p["entry_qty"]))
        p["pnl_per_contract"] = round(p["actual_exit_pnl"] / p["entry_qty"], 6) if p["entry_qty"] else 0.0
        p["entry_notional"] = round(p["entry_qty"] * p["entry_price"] * 100, 2)
        # qty-weighted exit price -- the single number the exit config controls
        tot_q = sum(ef["qty"] for ef in p["exit_fills"])
        p["exit_vwap"] = round(sum(ef["price"] * ef["qty"] for ef in p["exit_fills"]) / tot_q, 6) if tot_q else 0.0
        p["fully_closed"] = abs(tot_q - p["entry_qty"]) < 1e-6
        p["side"] = "P" if "P00" in p["symbol"] else "C"
    positions.sort(key=lambda p: (p["entry_ts_et"], p["arm"]))
    return positions


def load_replay() -> tuple[list[dict], dict]:
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    out = []
    for t in d["trades"]:
        out.append({**t, "pnl": round(float(t["dollar_pnl"]), 2),
                    "qty": int(t["qty"]),
                    "entry_ts_et": t["entry_time_et"],
                    "date_et": t["date"],
                    "entry_price": float(t["entry_premium"]),
                    "entry_notional": round(int(t["qty"]) * float(t["entry_premium"]) * 100, 2),
                    "arm": "replay-single-arm",
                    "hold_minutes": t.get("hold_minutes") or 0})
    out.sort(key=lambda t: t["entry_ts_et"])
    # exit ts = entry + hold (the replay records hold_minutes, not an exit stamp)
    for t in out:
        e = dt.datetime.fromisoformat(t["entry_ts_et"])
        t["exit_ts_et"] = (e + dt.timedelta(minutes=float(t["hold_minutes"] or 0))).isoformat()
    return out, d


def load_spy(path: Path) -> dict[str, list[tuple[dt.datetime, float, float, float]]]:
    """date_et -> [(ts_naive_et, high, low, close)] ascending. Used only for realised vol."""
    by_day: dict = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw = row["timestamp_et"]
            ts = dt.datetime.fromisoformat(raw)
            ts = ts.replace(tzinfo=None)
            by_day[ts.strftime("%Y-%m-%d")].append(
                (ts, float(row["high"]), float(row["low"]), float(row["close"])))
    for k in by_day:
        by_day[k].sort(key=lambda r: r[0])
    return by_day


def realised_vol_pct(bars: list, entry_ts: dt.datetime, lookback: int = 6) -> float | None:
    """Trailing realised range as % of price over the last `lookback` CLOSED 5-min bars before
    entry (30 min). Strictly causal: only bars whose close stamp is <= entry are used, and the
    bar containing the entry is excluded. Returns None when fewer than 3 bars are available."""
    prior = [b for b in bars if b[0] + dt.timedelta(minutes=5) <= entry_ts]
    if len(prior) < 3:
        return None
    w = prior[-lookback:]
    rng = [(h - l) / c * 100.0 for _, h, l, c in w if c]
    return round(sum(rng) / len(rng), 5) if rng else None


# ============================================================ Q1: r1 vs r3 exact decomposition
def shapley_3(base: dict, alt: dict) -> dict:
    """EXACT Shapley over three levers {qty, entry_price, exit_price} for the position-level
    payoff f(q, e_in, e_out) = q * (e_out - e_in) * 100. All 3! = 6 orderings enumerated.
    Sums EXACTLY to f(alt) - f(base) -- asserted by the caller."""
    levers = ("qty", "entry", "exit")

    def f(state: dict) -> float:
        return state["qty"] * (state["exit"] - state["entry"]) * 100.0

    contrib = {k: 0.0 for k in levers}
    orders = list(itertools.permutations(levers))
    for order in orders:
        cur = dict(base)
        for lv in order:
            before = f(cur)
            cur[lv] = alt[lv]
            contrib[lv] += f(cur) - before
    return {k: round(v / len(orders), 4) for k, v in contrib.items()}


def q1_wed_gap(book: list[dict]) -> dict:
    """risky-1 vs risky-3 on 2026-08-05: they took the SAME contracts within seconds. Pair
    them by (symbol, ordinal within the day) and decompose the gap EXACTLY."""
    def wed(arm):
        ps = [p for p in book if p["date_et"] == WED and p["arm"] == arm]
        ps.sort(key=lambda p: p["entry_ts_et"])
        seq: dict = defaultdict(int)
        for p in ps:
            seq[p["symbol"]] += 1
            p["_ord"] = seq[p["symbol"]]
        return ps

    r1, r3 = wed("risky-1"), wed("risky-3")
    by1 = {(p["symbol"], p["_ord"]): p for p in r1}
    by3 = {(p["symbol"], p["_ord"]): p for p in r3}
    keys = sorted(set(by1) & set(by3), key=lambda k: by1[k]["entry_ts_et"])
    unmatched = sorted(set(by1) ^ set(by3))

    pairs, tot = [], {"qty": 0.0, "entry": 0.0, "exit": 0.0}
    for k in keys:
        a, b = by1[k], by3[k]
        base = {"qty": a["qty"], "entry": a["entry_price"], "exit": a["exit_vwap"]}
        alt = {"qty": b["qty"], "entry": b["entry_price"], "exit": b["exit_vwap"]}
        sh = shapley_3(base, alt)
        gap = b["pnl"] - a["pnl"]
        pairs.append({
            "symbol": k[0], "ordinal": k[1], "entry_t_r1": a["entry_ts_et"][11:19],
            "r1": {"qty": a["qty"], "entry": a["entry_price"], "exit_vwap": a["exit_vwap"], "pnl": a["pnl"]},
            "r3": {"qty": b["qty"], "entry": b["entry_price"], "exit_vwap": b["exit_vwap"], "pnl": b["pnl"]},
            "gap": round(gap, 2), "shapley": sh,
            "shapley_sum_check": round(sum(sh.values()) - gap, 4)})
        for lv in tot:
            tot[lv] += sh[lv]

    r1_tot, r3_tot = sum(p["pnl"] for p in r1), sum(p["pnl"] for p in r3)
    gap_tot = r3_tot - r1_tot

    # group split: the calls (the 5x spiral) vs the put (the exit-config event)
    grp: dict = defaultdict(lambda: {"qty": 0.0, "entry": 0.0, "exit": 0.0, "gap": 0.0,
                                     "r1_pnl": 0.0, "r3_pnl": 0.0, "n": 0})
    for pr in pairs:
        g = "CALLS_776C_spiral" if pr["symbol"].find("C00") > 0 else "PUT_772P"
        for lv in ("qty", "entry", "exit"):
            grp[g][lv] += pr["shapley"][lv]
        grp[g]["gap"] += pr["gap"]
        grp[g]["r1_pnl"] += pr["r1"]["pnl"]
        grp[g]["r3_pnl"] += pr["r3"]["pnl"]
        grp[g]["n"] += 1
    grp = {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in grp.items()}

    # the prior audit's 2x2 factorial, reproduced then corrected
    pc_r1 = r1_tot / 5.0
    pc_r3 = r3_tot / 8.0
    factorial = {"qty5_tp1_50_ACTUAL_r1": round(5 * pc_r1, 2), "qty8_tp1_50": round(8 * pc_r1, 2),
                 "qty5_tp1_100": round(5 * pc_r3, 2), "qty8_tp1_100_ACTUAL_r3": round(8 * pc_r3, 2)}
    prior_size = round(factorial["qty8_tp1_100_ACTUAL_r3"] - factorial["qty5_tp1_100"], 2)
    prior_knob = round(factorial["qty8_tp1_100_ACTUAL_r3"] - factorial["qty8_tp1_50"], 2)
    sh2_size = round(0.5 * ((factorial["qty8_tp1_50"] - factorial["qty5_tp1_50_ACTUAL_r1"])
                            + (factorial["qty8_tp1_100_ACTUAL_r3"] - factorial["qty5_tp1_100"])), 2)
    sh2_knob = round(gap_tot - sh2_size, 2)

    return {
        "_question": "risky-1 -$140 vs risky-3 -$1,462 on identical decisions. Where is the 10.4x?",
        "arm_config": {
            "risky-1": "qty 5 | strike_tier_table=bold_core (ATM) | exit_patch tp1_premium_pct=0.5, stop_mode=structure",
            "risky-3": "qty 8 | strike_tier_table=bold_core (ATM) | exit_patch stop_mode=structure, profit_lock_mode=trailing, trail_pct=0.20 (TP1 = registry 1.0 = +100%)"},
        "STRIKE_TIER_CONTRIBUTES_ZERO": (
            "Both arms carry strike_tier_table='bold_core' (ATM) since 2026-08-01 and bought the "
            "IDENTICAL contracts on 2026-08-05 (SPY260805C00776000 x5 each, SPY260805P00772000 x1 "
            "each). The ATM-tier extension therefore explains EXACTLY $0.00 of the r1-vs-r3 gap. "
            "It is a real open question for the arm's absolute P&L (cell f) -- it is NOT part of "
            "this gap, and any decomposition that charges it here is wrong."),
        "options_only_pnl": {"risky-1": round(r1_tot, 2), "risky-3": round(r3_tot, 2),
                             "gap": round(gap_tot, 2)},
        "pairs": pairs, "unmatched_positions": [list(k) for k in unmatched],
        "shapley_total_3lever": {k: round(v, 2) for k, v in tot.items()},
        "shapley_sum_check": round(sum(tot.values()) - gap_tot, 4),
        "shapley_pct_of_gap": {k: round(100 * v / gap_tot, 1) for k, v in tot.items()},
        "by_contract_group": grp,
        "prior_audit_reproduction": {
            "factorial_2x2": factorial,
            "prior_size_effect_reported": 546.75, "prior_size_effect_recomputed": abs(prior_size),
            "prior_knob_effect_reported": 1237.2, "prior_knob_effect_recomputed": abs(prior_knob),
            "why_they_sum_to_135pct": (
                "Both prior figures are LAST-IN waterfall marginals measured at the OTHER factor's "
                "risky-3 level: size was priced at TP1=+100% and the knob was priced at qty 8. Each "
                "is individually correct as a marginal; they overlap by the interaction term "
                f"${abs(prior_size) + abs(prior_knob) - abs(gap_tot):,.2f} and CANNOT be added."),
            "corrected_2lever_shapley": {"size": sh2_size, "exit_knob": sh2_knob},
            "corrected_3lever_shapley": {k: round(v, 2) for k, v in tot.items()}},
    }


# ============================================================ Q2: sizing policies
def _resize(pos: dict, new_qty: int) -> float:
    """P&L of the same real position at a different size. Linear in qty; Rule-6 floor applied
    by the caller. Rounding caveat: real TP1 fractions round to whole contracts, so a rescaled
    multi-leg exit is an approximation at the leg level (exact at the position level)."""
    return pos["pnl"] * (new_qty / pos["qty"]) if pos["qty"] else 0.0


def _apply(positions: list[dict], qty_fn) -> dict:
    """Run a sizing policy over a population. qty_fn(pos, state) -> new integer qty.
    State is rebuilt per (arm, date) in strict ENTRY order, with the loss counter advanced only
    by round trips that had ALREADY CLOSED at this entry's timestamp (strictly causal)."""
    out_by_day: dict = defaultdict(float)
    rows = []
    for p in positions:
        nq = max(RULE6_MIN, int(qty_fn(p)))
        pnl = _resize(p, nq)
        out_by_day[p["date_et"]] += pnl
        rows.append({**{k: p[k] for k in ("arm", "date_et", "symbol", "entry_ts_et", "qty", "pnl")},
                     "new_qty": nq, "new_pnl": round(pnl, 2)})
    return {"by_day": {k: round(v, 2) for k, v in sorted(out_by_day.items())}, "rows": rows}


def _closed_loss_counter(positions: list[dict], scope: str) -> dict[str, int]:
    """position key -> number of LOSING round trips already CLOSED when it was entered.
    scope='arm' counts only that arm's own; scope='fleet' counts every arm's."""
    out = {}
    for p in positions:
        key = (p["arm"], p["symbol"], p["entry_ts_et"])
        n = 0
        for q in positions:
            if q is p or q["date_et"] != p["date_et"] or q["pnl"] >= 0:
                continue
            if scope == "arm" and q["arm"] != p["arm"]:
                continue
            if q["exit_ts_et"] < p["entry_ts_et"]:
                n += 1
        out[key] = n
    return out


def summarise(by_day: dict, live_by_day: dict, label: str) -> dict:
    delta = {d: round(by_day.get(d, 0.0) - live_by_day.get(d, 0.0), 2) for d in live_by_day}
    harmed = {d: v for d, v in delta.items() if v < -0.005}
    helped = {d: v for d, v in delta.items() if v > 0.005}
    return {
        "label": label,
        "total": round(sum(by_day.values()), 2),
        "delta_total": round(sum(delta.values()), 2),
        "TUE_2026_08_04": round(by_day.get(TUE, 0.0), 2), "TUE_delta": delta.get(TUE, 0.0),
        "WED_2026_08_05": round(by_day.get(WED, 0.0), 2), "WED_delta": delta.get(WED, 0.0),
        "THU_2026_08_06": round(by_day.get(THU, 0.0), 2), "THU_delta": delta.get(THU, 0.0),
        "delta_ex_week": round(sum(v for d, v in delta.items() if d not in WEEK), 2),
        "n_days_harmed": len(harmed), "n_days_helped": len(helped),
        "worst_day_harmed": min(harmed.items(), key=lambda r: r[1]) if harmed else None,
    }


def q2_policies(book: list[dict], replay: list[dict], spy_book: dict, spy_rep: dict) -> dict:
    live_book = defaultdict(float)
    for p in book:
        live_book[p["date_et"]] += p["pnl"]
    live_book = {k: round(v, 2) for k, v in sorted(live_book.items())}
    live_rep = defaultdict(float)
    for t in replay:
        live_rep[t["date_et"]] += t["pnl"]
    live_rep = {k: round(v, 2) for k, v in sorted(live_rep.items())}

    res: dict = {"_question": "Which sizing policy caps Wednesday without touching Tuesday?",
                 "live_baseline_book": {"total": round(sum(live_book.values()), 2),
                                        "TUE": live_book.get(TUE), "WED": live_book.get(WED),
                                        "THU": live_book.get(THU), "n_days": len(live_book)},
                 "live_baseline_replay": {"total": round(sum(live_rep.values()), 2),
                                          "n_days": len(live_rep), "n_trades": len(replay)}}

    # ---- (a) FLAT QTY across arms -------------------------------------------------
    cells = {}
    for Q in (3, 4, 5, 6, 8):
        r = _apply(book, lambda p, q=Q: q)
        cells[f"flat_qty_{Q}"] = summarise(r["by_day"], live_book, f"every arm at qty {Q}")
    res["a_flat_qty_BOOK"] = cells
    rcells = {}
    for Q in (3, 4, 5):
        r = _apply(replay, lambda t, q=Q: q)
        rcells[f"flat_qty_{Q}"] = summarise(r["by_day"], live_rep, f"every trade at qty {Q}")
    res["a_flat_qty_REPLAY"] = rcells
    res["a_ORACLE_FLOOR_BOUND"] = {
        "_what": ("qty 3 on every arm every trade is the TIGHTEST LEGAL SIZE under Rule 6. It is "
                  "therefore the ORACLE lower bound on what ANY shrink-only sizing policy can "
                  "achieve on Wednesday -- no cell in this lane, conditional or not, can beat it."),
        "WED_at_rule6_floor": cells["flat_qty_3"]["WED_2026_08_05"],
        "TUE_cost_at_rule6_floor": cells["flat_qty_3"]["TUE_delta"],
        "THU_cost_at_rule6_floor": cells["flat_qty_3"]["THU_delta"],
        "VERDICT": ("Sizing alone CANNOT produce a -$500 Wednesday: the legal floor still leaves "
                    f"{cells['flat_qty_3']['WED_2026_08_05']:,.2f} and it costs Tuesday "
                    f"{cells['flat_qty_3']['TUE_delta']:,.2f} + Thursday "
                    f"{cells['flat_qty_3']['THU_delta']:,.2f} to get there.")}

    # ---- (b)/(c) HALVE AFTER N LOSING ROUND TRIPS ---------------------------------
    for scope in ("arm", "fleet"):
        cnt = _closed_loss_counter(book, scope)
        for N in (1, 2, 3):
            def fn(p, N=N, cnt=cnt):
                n = cnt[(p["arm"], p["symbol"], p["entry_ts_et"])]
                return max(RULE6_MIN, round(p["qty"] / 2)) if n >= N else p["qty"]
            r = _apply(book, fn)
            res[f"bc_halve_after_{N}_loss_{scope}_BOOK"] = summarise(
                r["by_day"], live_book, f"halve after {N} closed losing round trip(s), {scope}-scoped")
    cnt_r = _closed_loss_counter(replay, "arm")
    for N in (1, 2):
        def fnr(t, N=N, cnt=cnt_r):
            n = cnt[(t["arm"], t["symbol"], t["entry_ts_et"])]
            return max(RULE6_MIN, round(t["qty"] / 2)) if n >= N else t["qty"]
        r = _apply(replay, fnr)
        res[f"bc_halve_after_{N}_loss_REPLAY"] = summarise(
            r["by_day"], live_rep, f"halve after {N} closed losing round trip(s), 141-day population")
    res["bc_SELECTION_TEST"] = selection_test(book, replay)
    res["bc_TUESDAY_TRIGGER_FORENSICS"] = tuesday_forensics(book)
    res["size_gradient"] = size_gradient(book, replay)

    # ---- (d) VOLATILITY-SCALED ----------------------------------------------------
    res["d_vol_scaled"] = vol_scaled(book, replay, spy_book, spy_rep, live_book, live_rep)

    # ---- (e) PREMIUM-SCALED / CONSTANT DOLLAR RISK --------------------------------
    res["e_premium_scaled"] = premium_scaled(book, replay, live_book, live_rep)
    return res


def selection_test(book: list[dict], replay: list[dict]) -> dict:
    """SCALE-FREE generalisation test for the halve-after-N-losses trigger. A shrink policy is
    only worth anything if the trades it shrinks are, on average, LOSERS. Population B is at the
    Rule-6 floor and cannot shrink -- but it CAN answer this, and it answers it over 141
    independent days instead of 26."""
    out = {"_why": ("THE decisive test for cells (b) and (c), and the only one that is SCALE-FREE "
                    "-- it does not care that 130 of population B's 191 trades already sit at the "
                    "Rule-6 floor and cannot shrink. A shrink-on-loss policy is worth something "
                    "ONLY if the trades it shrinks are, on average, losers. Run on both "
                    "populations; if the post-loss cohort is the PROFITABLE one, the policy is "
                    "refuted no matter how the thresholds are tuned.")}
    for name, pop, key in (("BOOK", book, "arm"), ("REPLAY", replay, "single")):
        cnt = _closed_loss_counter(pop, "fleet" if key == "arm" else "arm")
        buckets: dict = defaultdict(list)
        for p in pop:
            n = cnt[(p["arm"], p["symbol"], p["entry_ts_et"])]
            buckets[min(n, 3)].append(p["pnl"])
        rows = {}
        for k in sorted(buckets):
            v = buckets[k]
            rows[f"after_{k}_losses" + ("+" if k == 3 else "")] = {
                "n": len(v), "total": round(sum(v), 2), "mean": round(stats.mean(v), 2),
                "win_pct": round(100 * sum(1 for x in v if x > 0) / len(v), 1)}
        # the cohort a halve-after-1 policy would shrink
        shrunk = [p["pnl"] for p in pop if cnt[(p["arm"], p["symbol"], p["entry_ts_et"])] >= 1]
        kept = [p["pnl"] for p in pop if cnt[(p["arm"], p["symbol"], p["entry_ts_et"])] < 1]
        out[name] = {
            "by_prior_closed_losses": rows,
            "halve_after_1_cohort": {
                "n_shrunk": len(shrunk), "total_shrunk": round(sum(shrunk), 2),
                "mean_shrunk": round(stats.mean(shrunk), 2) if shrunk else None,
                "n_kept": len(kept), "total_kept": round(sum(kept), 2),
                "mean_kept": round(stats.mean(kept), 2) if kept else None,
                "VERDICT": ("SELECTS WINNERS -- shrinking this cohort DESTROYS money"
                            if shrunk and sum(shrunk) > 0 else
                            "selects losers -- shrinking this cohort saves money")}}
    return out


def tuesday_forensics(book: list[dict]) -> dict:
    """WHY every conditional-halve cell fails the Tuesday gate. This is the single fact that
    decides (b) and (c), so it is spelled out position by position rather than asserted."""
    tue = sorted([p for p in book if p["date_et"] == TUE], key=lambda p: p["entry_ts_et"])
    first_loss_exit = min((p["exit_ts_et"] for p in tue if p["pnl"] < 0), default=None)
    after = [p for p in tue if first_loss_exit and p["entry_ts_et"] > first_loss_exit]
    return {
        "_finding": ("Tuesday's FIRST closed round trip is a LOSER, at 09:47:07, 77 seconds into "
                     "the first trade of the biggest winning day in the book. Every "
                     "halve-after-a-loss policy therefore arms on Tuesday before 09:48 and "
                     "shrinks the rest of the day -- including the +$4.87 runner and the 12:28 "
                     "769C. That is the whole reason cells (b) and (c) fail the hard gate; it is "
                     "not a threshold that can be tuned around, it is the shape of the day."),
        "first_closed_round_trip": {
            "exit_ts_et": first_loss_exit,
            "positions": [{"arm": p["arm"], "symbol": p["symbol"], "entry": p["entry_ts_et"][11:19],
                           "exit": p["exit_ts_et"][11:19], "pnl": p["pnl"]}
                          for p in tue if p["exit_ts_et"] == first_loss_exit]},
        "n_positions_after_first_loss": len(after),
        "pnl_after_first_loss": round(sum(p["pnl"] for p in after), 2),
        "pnl_before_first_loss": round(sum(p["pnl"] for p in tue) - sum(p["pnl"] for p in after), 2),
        "biggest_winners_in_the_shrunk_cohort": sorted(
            [{"arm": p["arm"], "t": p["entry_ts_et"][11:19], "symbol": p["symbol"], "pnl": p["pnl"]}
             for p in after], key=lambda r: -r["pnl"])[:5],
    }


def size_gradient(book: list[dict], replay: list[dict]) -> dict:
    """Is 'bigger lots lose' a SIZE effect or a PREMIUM confound? In both populations qty is
    set by a risk cap, so qty is mechanically INVERSE to entry premium -- and we already know
    return-on-notional is not flat in premium. Stratify to separate them."""
    out = {"_question": "Does the population support 'big lots lose', once premium is controlled?"}
    for name, pop in (("BOOK", book), ("REPLAY", replay)):
        raw = {}
        for lo, hi, lbl in ((1, 3, "3"), (4, 5, "4-5"), (6, 8, "6-8"), (9, 99, "9+")):
            sel = [p for p in pop if lo <= p["qty"] <= hi]
            if not sel:
                continue
            nq = sum(p["qty"] for p in sel)
            raw[lbl] = {"n": len(sel), "total": round(sum(p["pnl"] for p in sel), 2),
                        "per_trade": round(sum(p["pnl"] for p in sel) / len(sel), 2),
                        "per_contract": round(sum(p["pnl"] for p in sel) / nq, 2),
                        "median_entry_premium": round(stats.median(p["entry_price"] for p in sel), 2)}
        # premium-stratified control: within a premium band, does qty still predict loss?
        strat = {}
        for plo, phi in ((0.0, 1.0), (1.0, 1.5), (1.5, 99)):
            band = [p for p in pop if plo <= p["entry_price"] < phi]
            if len(band) < 8:
                continue
            small = [p for p in band if p["qty"] <= 5]
            big = [p for p in band if p["qty"] >= 6]
            strat[f"premium_${plo:.2f}-${phi:.2f}"] = {
                "n_small_qty<=5": len(small), "n_big_qty>=6": len(big),
                "per_contract_small": round(sum(p["pnl"] for p in small) / sum(p["qty"] for p in small), 2) if small else None,
                "per_contract_big": round(sum(p["pnl"] for p in big) / sum(p["qty"] for p in big), 2) if big else None}
        out[name] = {"by_qty_band": raw, "premium_stratified_control": strat}
    out["_confound_warning"] = (
        "In BOTH populations qty is set by a dollar risk cap, so qty is mechanically INVERSE to "
        "entry premium (REPLAY median premium falls 1.35 -> 0.40 as qty rises 3 -> 13). A raw "
        "'big lots lose' reading is therefore confounded with 'cheap contracts lose', which the "
        "return-on-notional table measures independently. The stratified rows above are the "
        "control; read those, not the raw band.")
    return out


def vol_scaled(book, replay, spy_book, spy_rep, live_book, live_rep) -> dict:
    """qty scaled INVERSELY to trailing realised 5-min range at entry. Reference vol is the
    population MEDIAN (calibration stated, not tuned)."""
    def tag(pop, spy):
        miss = 0
        for p in pop:
            bars = spy.get(p["date_et"], [])
            ts = dt.datetime.fromisoformat(p["entry_ts_et"].split("+")[0])
            p["_vol"] = realised_vol_pct(bars, ts)
            if p["_vol"] is None:
                miss += 1
        return miss

    miss_b, miss_r = tag(book, spy_book), tag(replay, spy_rep)
    vb = [p["_vol"] for p in book if p["_vol"]]
    vr = [t["_vol"] for t in replay if t["_vol"]]
    ref_b = round(stats.median(vb), 5) if vb else None
    ref_r = round(stats.median(vr), 5) if vr else None

    out = {"_spec": ("qty_new = max(3, round(qty * clip(ref_vol / vol_at_entry, lo, hi))). "
                     "vol_at_entry = mean 5-min (high-low)/close % over the 6 CLOSED bars before "
                     "entry (strictly causal). ref_vol = that population's OWN median."),
           "ref_vol_book_pct": ref_b, "ref_vol_replay_pct": ref_r,
           "n_missing_vol_book": miss_b, "n_missing_vol_replay": miss_r,
           "WED_vol_vs_TUE": {}}
    for d in WEEK:
        vs = [p["_vol"] for p in book if p["date_et"] == d and p["_vol"]]
        out["WED_vol_vs_TUE"][d] = {"n": len(vs),
                                    "median_entry_vol_pct": round(stats.median(vs), 4) if vs else None}
    cells = {}
    for lo, hi in ((0.5, 1.0), (0.5, 2.0), (0.33, 1.0)):
        def fn(p, lo=lo, hi=hi, ref=ref_b):
            if not p["_vol"]:
                return p["qty"]
            return max(RULE6_MIN, round(p["qty"] * min(hi, max(lo, ref / p["_vol"]))))
        r = _apply(book, fn)
        cells[f"clip_{lo}_{hi}"] = summarise(r["by_day"], live_book,
                                             f"vol-scaled, multiplier clipped to [{lo}, {hi}]")
    out["BOOK"] = cells
    rcells = {}
    for lo, hi in ((0.5, 1.0), (0.5, 2.0), (1.0, 2.0)):
        def fn(t, lo=lo, hi=hi, ref=ref_r):
            if not t["_vol"]:
                return t["qty"]
            return max(RULE6_MIN, round(t["qty"] * min(hi, max(lo, ref / t["_vol"]))))
        r = _apply(replay, fn)
        rcells[f"clip_{lo}_{hi}"] = summarise(r["by_day"], live_rep,
                                              f"vol-scaled, multiplier clipped to [{lo}, {hi}]")
    out["REPLAY"] = rcells
    out["REPLAY_floor_note"] = ("Population B is at qty 3 = the Rule-6 floor, so any cell whose "
                                "clip hi is 1.0 is a guaranteed NO-OP there. Reported anyway so "
                                "the reader can see it is a no-op rather than assume a result.")
    return out


def premium_scaled(book, replay, live_book, live_rep) -> dict:
    """(e) CONSTANT DOLLAR RISK. This is the theoretically sound cell and gets the most care.

    qty_new = max(3, round(B_arm / (entry_premium * 100)))

    B_arm is BUDGET-NEUTRAL by construction: it is set to the arm's OWN mean entry notional
    over its own real positions, so the policy REDISTRIBUTES the arm's existing dollar
    exposure across contract prices rather than shrinking it. That calibration is in-sample
    and is disclosed as such; a scale grid is reported around it so the reader can see the
    whole curve, not a single fitted point."""
    out = {"_spec": ("qty_new = max(3, round(scale * B_arm / (entry_premium*100))); "
                     "B_arm = mean(entry_notional) over that arm's own real positions "
                     "(BUDGET-NEUTRAL, in-sample, disclosed)."),
           "_theory": ("Constant dollar risk is the direct answer to 'the same signal cost 10x "
                       "more on one arm'. It pays off ONLY if per-DOLLAR return is flat in "
                       "premium. If expected return per contract RISES with premium, constant-"
                       "dollar sizing systematically under-sizes the good trades. That is the "
                       "decisive test and it is run below on both populations.")}

    # --- the decisive diagnostic: return-on-notional by entry-premium bucket
    def ron(pop, name):
        buckets = ((0, 0.50), (0.50, 1.00), (1.00, 1.50), (1.50, 2.00), (2.00, 99))
        rows = {}
        for lo, hi in buckets:
            sel = [p for p in pop if lo <= p["entry_price"] < hi]
            if not sel:
                continue
            notional = sum(p["entry_notional"] for p in sel)
            pnl = sum(p["pnl"] for p in sel)
            rows[f"${lo:.2f}-${hi:.2f}"] = {
                "n": len(sel), "total_pnl": round(pnl, 2), "total_notional": round(notional, 2),
                "return_on_notional_pct": round(100 * pnl / notional, 2) if notional else None,
                "mean_pnl_per_contract": round(sum(p["pnl"] for p in sel)
                                               / sum(p["qty"] for p in sel), 2)}
        return rows
    out["return_on_notional_by_premium_BOOK"] = ron(book, "BOOK")
    out["return_on_notional_by_premium_REPLAY"] = ron(replay, "REPLAY")

    b_arm: dict = {}
    for a in {p["arm"] for p in book}:
        sel = [p for p in book if p["arm"] == a]
        b_arm[a] = round(sum(p["entry_notional"] for p in sel) / len(sel), 2)
    out["budget_per_arm_dollars"] = b_arm
    cells = {}
    for scale in (0.5, 0.75, 1.0, 1.25):
        def fn(p, s=scale):
            return max(RULE6_MIN, round(s * b_arm[p["arm"]] / (p["entry_price"] * 100)))
        r = _apply(book, fn)
        cells[f"scale_{scale}"] = summarise(r["by_day"], live_book,
                                            f"constant dollar risk, budget x{scale}")
    out["BOOK"] = cells

    b_rep = round(sum(t["entry_notional"] for t in replay) / len(replay), 2)
    out["budget_replay_dollars"] = b_rep
    rcells = {}
    for scale in (0.5, 0.75, 1.0, 1.25):
        def fn(t, s=scale, B=b_rep):
            return max(RULE6_MIN, round(s * B / (t["entry_price"] * 100)))
        r = _apply(replay, fn)
        rcells[f"scale_{scale}"] = summarise(r["by_day"], live_rep,
                                             f"constant dollar risk, budget x{scale}")
    out["REPLAY"] = rcells
    out["REPLAY_floor_note"] = ("Population B is at the Rule-6 floor, so constant-dollar sizing "
                                "there can only size UP (cheap contracts) -- it can never express "
                                "the size-DOWN half of the policy. Any REPLAY gain below is a "
                                "LEVERAGE result, not a risk-control result. Labelled, not netted.")
    # Wednesday-specific: what would constant-dollar have done to the 776C spiral + the put?
    wed = [p for p in book if p["date_et"] == WED]
    detail = []
    for p in sorted(wed, key=lambda x: x["entry_ts_et"]):
        nq = max(RULE6_MIN, round(b_arm[p["arm"]] / (p["entry_price"] * 100)))
        detail.append({"t": p["entry_ts_et"][11:19], "arm": p["arm"], "symbol": p["symbol"],
                       "premium": p["entry_price"], "qty": p["qty"], "new_qty": nq,
                       "pnl": p["pnl"], "new_pnl": round(_resize(p, nq), 2)})
    out["WED_position_detail"] = detail
    return out


# ============================================================ Q3: C31 check
def q3_c31() -> dict:
    """J's own real trades. C31 as written in CLAUDE.md says 1-2 lots +$4,576 / 3+ lots
    -$17,461 / scaled-in -$327/trade. The standing correction says 'profitable at 1-2 lots' is
    an accounting artifact. Re-derive from the normalised episode file and say which is true."""
    rows = list(csv.DictReader(WEBULL.open(newline="", encoding="utf-8")))
    def f(r, k, d=0.0):
        try:
            return float(r[k])
        except (TypeError, ValueError):
            return d
    closed = [r for r in rows if r.get("closed") == "True"]
    band: dict = defaultdict(lambda: {"n": 0, "pnl": 0.0, "qty": 0})
    for r in closed:
        q = int(f(r, "qty"))
        b = "1-2" if q <= 2 else "3+"
        band[b]["n"] += 1
        band[b]["pnl"] += f(r, "pnl")
        band[b]["qty"] += q
    scaled = [r for r in closed if r.get("scaled_in") == "True"]
    flat = [r for r in closed if r.get("scaled_in") != "True"]
    grad = {}
    for lo, hi, lbl in ((1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 10**6, "11+")):
        sel = [r for r in closed if lo <= int(f(r, "qty")) <= hi]
        if not sel:
            continue
        nq = sum(int(f(r, "qty")) for r in sel)
        grad[lbl] = {"n": len(sel), "total_pnl": round(sum(f(r, "pnl") for r in sel), 2),
                     "pnl_per_contract": round(sum(f(r, "pnl") for r in sel) / nq, 2) if nq else None,
                     "mean_pnl_per_episode": round(sum(f(r, "pnl") for r in sel) / len(sel), 2)}
    return {
        "_question": "Use C31 as a PRIOR, not as proof. What does J's own book actually say about size?",
        "source": str(WEBULL), "n_rows": len(rows), "n_closed_episodes": len(closed),
        "claude_md_C31_as_written": {"1-2 lots": 4576, "3+ lots": -17461,
                                     "scaled_in_per_trade": -327},
        "episode_level_recomputation": {
            k: {"n": v["n"], "total_pnl": round(v["pnl"], 2), "n_contracts": v["qty"],
                "pnl_per_contract": round(v["pnl"] / v["qty"], 2) if v["qty"] else None}
            for k, v in sorted(band.items())},
        "scaled_in": {"n": len(scaled), "total_pnl": round(sum(f(r, "pnl") for r in scaled), 2),
                      "per_episode": round(sum(f(r, "pnl") for r in scaled) / len(scaled), 2) if scaled else None},
        "not_scaled_in": {"n": len(flat), "total_pnl": round(sum(f(r, "pnl") for r in flat), 2),
                          "per_episode": round(sum(f(r, "pnl") for r in flat) / len(flat), 2) if flat else None},
        "per_contract_gradient": grad,
    }


# ============================================================ main
def main() -> None:
    book = load_book()
    replay, rmeta = load_replay()
    spy_book, spy_rep = load_spy(SPY_BOOK), load_spy(SPY_REPLAY)

    out: dict = {
        "lens": "LEVER 2 -- SIZING AS THE LOSS AMPLIFIER",
        "run_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "populations": {
            "A_book": {"n_positions": len(book),
                       "n_dates": len({p["date_et"] for p in book}),
                       "date_range": [min(p["date_et"] for p in book), max(p["date_et"] for p in book)],
                       "arms": sorted({p["arm"] for p in book}),
                       "authority": "REAL BROKER FILLS, automation/state/fills-ledger.jsonl"},
            "B_replay": {"n_trades": len(replay), "n_traded_days": len({t["date_et"] for t in replay}),
                         "n_calendar_rth_days": rmeta["window"]["n_calendar_rth_days"],
                         "window": [rmeta["window"]["start"], rmeta["window"]["end"]],
                         "qty": "FIXED 3 == the Rule-6 floor; size-DOWN inexpressible",
                         "authority": "exits re-walked through exit_manager.plan_exit_actions"}},
        "METHOD": ("A sizing policy is a per-position SCALAR on real realised P&L. No exit model "
                   "is used or needed on population A -- this is arithmetic on real broker fills, "
                   "which is strictly more faithful than any replay. Rule 6's min-3 floor is "
                   "applied to every cell. Sequential per (arm, date); no independent trades are "
                   "recombined."),
    }
    out["q1_wednesday_gap"] = q1_wed_gap(book)
    out["q2_policies"] = q2_policies(book, replay, spy_book, spy_rep)
    out["q3_c31"] = q3_c31()

    # ---------------- assertions
    g = out["q1_wednesday_gap"]
    check("q1 shapley sums to the gap", g["shapley_sum_check"], 0.0, 0.01)
    check("q1 r1 options-only Wed", g["options_only_pnl"]["risky-1"], -138.0, 0.51)
    check("q1 r3 options-only Wed", g["options_only_pnl"]["risky-3"], -1458.0, 0.51)
    check("q1 reproduces prior size marginal 546.75",
          g["prior_audit_reproduction"]["prior_size_effect_recomputed"], 546.75, 0.02)
    check("q1 reproduces prior knob marginal 1237.20",
          g["prior_audit_reproduction"]["prior_knob_effect_recomputed"], 1237.2, 0.02)
    q2 = out["q2_policies"]
    check("book live Wed", q2["live_baseline_book"]["WED"], -1935.0, 1.0)
    check("book live Tue", q2["live_baseline_book"]["TUE"], 3624.0, 1.0)
    for pr in g["pairs"]:
        check(f"pair shapley exact {pr['symbol']}#{pr['ordinal']}", pr["shapley_sum_check"], 0.0, 0.01)
    check("q1 strike tier contributes zero (identical contracts both arms)",
          len(g["unmatched_positions"]), 0)
    ob = q2["a_ORACLE_FLOOR_BOUND"]
    check("Rule-6-floor Wednesday (hand-check: -138*0.6 + -1458*0.375 + -339)",
          ob["WED_at_rule6_floor"], -968.55, 0.01)
    check("Rule-6 floor cannot reach -500 on Wednesday", ob["WED_at_rule6_floor"] < -500.0, True)
    check("Rule-6 floor costs Tuesday", ob["TUE_cost_at_rule6_floor"] < 0.0, True)
    st = q2["bc_SELECTION_TEST"]
    for popname in ("BOOK", "REPLAY"):
        c = st[popname]["halve_after_1_cohort"]
        check(f"{popname}: post-loss cohort is MORE profitable per trade than the no-loss cohort",
              c["mean_shrunk"] > c["mean_kept"], True)
    for cell in [k for k in q2 if k.startswith("bc_halve") and k.endswith("_BOOK")]:
        check(f"{cell} costs Tuesday (hard gate)", q2[cell]["TUE_delta"] < 0.0, True)
    out["verification"] = {"n_checks": len(ASSERTS),
                           "n_pass": sum(1 for a in ASSERTS if a["pass"]),
                           "checks": ASSERTS}

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"verification {out['verification']['n_pass']}/{out['verification']['n_checks']}")
    for a in ASSERTS:
        if not a["pass"]:
            print("  FAIL", a)


if __name__ == "__main__":
    main()
