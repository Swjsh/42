#!/usr/bin/env python
"""lever_correlation_2026_08_06.py -- LEVER 5: FLEET CONCENTRATION.

J's ask (2026-08-06, after the close): "we need to dial in on how to NOT LOSE TWO THOUSAND
DOLLARS on Wednesday ... we gotta KEEP OUR LOSSES SMALL so that way our wins can stack."

THIS LANE'S QUESTION: are we five bets, or ONE BET IN FIVE SIZES? And if it is one bet,
does capping the pile-on cut the tail -- or does it just de-lever the whole distribution?

POPULATION -- ONE, REAL, DISCLOSED
  Every closed engine SPY-OPTION POSITION in automation/state/fills-ledger.jsonl
  (attribution=="engine", is_option, not is_crypto), reconstructed by the repo's single
  canonical definition of a position (exit_shape_parity_study.reconstruct_positions).
  REAL BROKER FILLS ONLY. No simulator. No model. 26 ET dates, 2026-06-26 .. 2026-08-06.

  There is NO second population for this lane and that is a STRUCTURAL fact, not laziness:
  the 391-day engine-fullhist replay is ONE arm at qty 3. A single-arm population cannot
  express a fleet-concentration effect at all. Any cross-arm number here is n=26 days.
  LABELLED n-small everywhere it matters.

WHAT THIS MODULE DOES *NOT* DO
  Nothing here is modelled. Every dollar in sections Q1-Q3c and Q4-Tuesday is arithmetic on
  realized broker fills: either a position's own P&L, or a SIBLING ARM'S OWN REALIZED
  per-contract result on the IDENTICAL contract in the SAME minutes. The only modelled cells
  live in the companion module (lever_correlation_stagger_2026_08_06.py), which routes every
  exit through the real production core via walk_exit_manager -> plan_exit_actions.

HARD GATE (task-specified): 2026-08-04 (Tuesday, +$3,617 all-in) must not be harmed by any
proposed cell. Reported PER CELL, never aggregated away.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_correlation_2026_08_06.py
"""
from __future__ import annotations

import json
import math
import random
import statistics as stats
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-CORRELATION-2026-08-06.json"

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
WEEK = (TUE, WED, THU)
WAVE_WINDOW_S = 120          # two arms "took the same bet" if entries are <=120s apart
N_DRAWS = 20000              # resampling draws (bootstrap + permutation nulls)
SEED = 20260806              # frozen; every random cell in this file is reproducible


# --------------------------------------------------------------------------- primitives
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = stats.mean(xs), stats.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    k = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[min(k, len(sorted_vals)) - 1]


def secs(a: str, b: str) -> float:
    """Absolute seconds between two 'YYYY-MM-DDTHH:MM:SS.ffffff' ET strings."""
    import datetime as dt
    fa = dt.datetime.fromisoformat(a)
    fb = dt.datetime.fromisoformat(b)
    return abs((fa - fb).total_seconds())


# --------------------------------------------------------------------------- population
def load_book() -> list[dict]:
    """Real broker fills -> canonical positions, sorted by entry time. Identical loader
    contract to LANE 0 (loss_anatomy_2026_08_06.load_book) so the two lanes are comparable
    line-for-line; re-implemented here rather than imported so this lane is an INDEPENDENT
    code path over the same raw ledger (a cross-check, not a shared bug)."""
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
        p["qty"] = int(p["entry_qty"])
        p["ppc"] = round(p["actual_exit_pnl"] / p["entry_qty"], 4) if p["entry_qty"] else 0.0
    positions.sort(key=lambda p: (p["entry_ts_et"], p["arm"]))
    return positions


def day_arm_matrix(book):
    m = defaultdict(lambda: defaultdict(float))
    for p in book:
        m[p["date_et"]][p["arm"]] += p["pnl"]
    return {d: dict(v) for d, v in m.items()}


# ============================================================== Q1  CORRELATION
def q1_correlation(book) -> dict:
    res = {"_question": "Five bets, or one bet in five sizes?"}
    arms = sorted({p["arm"] for p in book})
    mat = day_arm_matrix(book)
    days = sorted(mat)
    res["arms"] = arms
    res["n_days"] = len(days)
    res["arm_day_pnl"] = {d: {a: round(v, 2) for a, v in sorted(mat[d].items())} for d in days}

    # ---- (1a) DAILY P&L pairwise, on days BOTH arms traded
    daily = []
    for a, b in combinations(arms, 2):
        xs, ys, ds = [], [], []
        for d in days:
            if a in mat[d] and b in mat[d]:
                xs.append(mat[d][a]); ys.append(mat[d][b]); ds.append(d)
        r = pearson(xs, ys)
        sign_agree = sum(1 for x, y in zip(xs, ys) if (x > 0) == (y > 0)) / len(xs) if xs else None
        daily.append({"pair": f"{a}|{b}", "n_days": len(xs),
                      "pearson_r": round(r, 4) if r is not None else None,
                      "sign_agreement": round(sign_agree, 4) if sign_agree is not None else None,
                      "dates": ds})
    daily.sort(key=lambda z: -z["n_days"])
    res["daily_pairwise"] = daily
    rs = [d["pearson_r"] for d in daily if d["pearson_r"] is not None]
    res["daily_mean_pairwise_r"] = round(stats.mean(rs), 4) if rs else None
    rs7 = [d["pearson_r"] for d in daily if d["pearson_r"] is not None and d["n_days"] >= 7]
    res["daily_mean_pairwise_r_n_ge_7"] = round(stats.mean(rs7), 4) if rs7 else None
    res["daily_min_pairwise_r"] = round(min(rs), 4) if rs else None

    # ---- (1b) TRADE-LEVEL pairwise. Two positions are THE SAME BET when they are the same
    #      contract on the same date entered within WAVE_WINDOW_S of each other. Correlate
    #      PER-CONTRACT P&L so sizing (the only thing arms are supposed to differ by) is
    #      divided out -- if the residual r is still ~1, the arms are not making different
    #      decisions, only different-sized copies of ONE decision.
    by_cluster = defaultdict(list)
    for p in book:
        by_cluster[(p["date_et"], p["symbol"])].append(p)
    pair_obs = defaultdict(list)          # (a,b) -> [(ppc_a, ppc_b), ...]
    matched_pairs = []
    for key, plist in by_cluster.items():
        plist = sorted(plist, key=lambda z: z["entry_ts_et"])
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                pi, pj = plist[i], plist[j]
                if pi["arm"] == pj["arm"]:
                    continue
                if secs(pi["entry_ts_et"], pj["entry_ts_et"]) > WAVE_WINDOW_S:
                    continue
                a, b = sorted((pi["arm"], pj["arm"]))
                va = pi["ppc"] if pi["arm"] == a else pj["ppc"]
                vb = pj["ppc"] if pj["arm"] == b else pi["ppc"]
                pair_obs[(a, b)].append((va, vb))
                matched_pairs.append({
                    "date": key[0], "symbol": key[1], "a": a, "b": b,
                    "ppc_a": round(va, 2), "ppc_b": round(vb, 2),
                    "gap_s": round(secs(pi["entry_ts_et"], pj["entry_ts_et"]), 1),
                    "entry_px_a": pi["entry_price"] if pi["arm"] == a else pj["entry_price"],
                    "entry_px_b": pj["entry_price"] if pj["arm"] == b else pi["entry_price"]})
    trade = []
    for (a, b), obs in sorted(pair_obs.items()):
        xs = [o[0] for o in obs]; ys = [o[1] for o in obs]
        r = pearson(xs, ys)
        sa = sum(1 for x, y in zip(xs, ys) if (x > 0) == (y > 0)) / len(xs) if xs else None
        trade.append({"pair": f"{a}|{b}", "n_matched_trades": len(obs),
                      "pearson_r_per_contract": round(r, 4) if r is not None else None,
                      "sign_agreement": round(sa, 4) if sa is not None else None,
                      "mean_abs_ppc_gap": round(stats.mean(abs(x - y) for x, y in obs), 2)})
    trade.sort(key=lambda z: -z["n_matched_trades"])
    res["trade_level_pairwise"] = trade
    tr = [t["pearson_r_per_contract"] for t in trade if t["pearson_r_per_contract"] is not None]
    res["trade_level_mean_pairwise_r"] = round(stats.mean(tr), 4) if tr else None
    res["trade_level_n_matched_pairs_total"] = len(matched_pairs)
    # pooled: ALL matched observations in one regression, both orderings symmetrised
    px = [o[0] for obs in pair_obs.values() for o in obs] + \
         [o[1] for obs in pair_obs.values() for o in obs]
    py = [o[1] for obs in pair_obs.values() for o in obs] + \
         [o[0] for obs in pair_obs.values() for o in obs]
    rp = pearson(px, py)
    res["trade_level_pooled_r"] = round(rp, 4) if rp is not None else None
    res["trade_level_pooled_r2"] = round(rp * rp, 4) if rp is not None else None
    res["trade_level_pooled_n"] = len(px) // 2
    res["trade_level_sign_agreement_pooled"] = round(
        sum(1 for o in (o for obs in pair_obs.values() for o in obs)
            if (o[0] > 0) == (o[1] > 0)) / max(1, res["trade_level_pooled_n"]), 4)

    # ---- (1c) diversification ratio + cluster share
    per_arm_sd = []
    for a in arms:
        v = [mat[d][a] for d in days if a in mat[d]]
        if len(v) >= 2:
            per_arm_sd.append(stats.pstdev(v))
    fleet_day = [sum(mat[d].values()) for d in days]
    res["diversification_ratio_traded_days_only"] = round(
        stats.pstdev(fleet_day) / sum(per_arm_sd), 4) if per_arm_sd and sum(per_arm_sd) else None
    # zeros-filled convention (what LANE 0 reports) -- both given so the two lanes reconcile
    per_arm_sd_z = [stats.pstdev([mat[d].get(a, 0.0) for d in days]) for a in arms]
    res["diversification_ratio_zeros_filled"] = round(
        stats.pstdev(fleet_day) / sum(per_arm_sd_z), 4) if sum(per_arm_sd_z) else None
    res["diversification_ratio_if_independent"] = round(1 / math.sqrt(len(arms)), 4)
    res["_dr_note"] = (
        "sd(sum of arms) / sum(sd of each arm). 1.0 = perfectly correlated, "
        f"{round(1/math.sqrt(len(arms)),3)} = {len(arms)} independent equal-sd arms. TWO "
        "conventions given because they differ materially: 'traded_days_only' computes each "
        "arm's sd over the days IT traded (the honest per-arm volatility); 'zeros_filled' "
        "scores a non-trading day as 0.00 (LANE 0's convention, which understates a "
        "sporadic arm's sd and therefore INFLATES the ratio). Neither is wrong; quoting one "
        "without naming it is.")

    # ---- (1d) does the PILE-ON predict a bad day? (the whole premise of a concentration cap)
    n_arms_day = {d: len(mat[d]) for d in days}
    day_pnl = {d: sum(mat[d].values()) for d in days}
    xs = [n_arms_day[d] for d in days]; ys = [day_pnl[d] for d in days]
    r_part = pearson(xs, ys)
    by_n = defaultdict(list)
    for d in days:
        by_n[n_arms_day[d]].append(day_pnl[d])
    res["participation_vs_outcome"] = {
        "_question": "Do MORE arms on a day mean a WORSE day? (if not, a cap is aimed backwards)",
        "pearson_r_n_arms_vs_day_pnl": round(r_part, 4) if r_part is not None else None,
        "day_pnl_by_n_arms_active": {
            str(k): {"n_days": len(v), "mean_day_pnl": round(stats.mean(v), 2),
                     "total": round(sum(v), 2), "worst": round(min(v), 2)}
            for k, v in sorted(by_n.items())},
        "n_arms_on_tuesday_2026_08_04": n_arms_day.get(TUE),
        "n_arms_on_wednesday_2026_08_05": n_arms_day.get(WED),
        "n_arms_on_thursday_2026_08_06": n_arms_day.get(THU)}

    # ---- (1e) within a wave, does the BIGGEST arm get the WORST per-contract result?
    wave_rank_obs = []
    for _k, plist in by_cluster.items():
        plist = sorted(plist, key=lambda z: z["entry_ts_et"])
        groups = []
        cur = [plist[0]]
        for p in plist[1:]:
            if secs(p["entry_ts_et"], cur[0]["entry_ts_et"]) <= WAVE_WINDOW_S:
                cur.append(p)
            else:
                groups.append(cur); cur = [p]
        groups.append(cur)
        for g in groups:
            if len({p["arm"] for p in g}) < 2:
                continue
            for p in g:
                wave_rank_obs.append((p["qty"], p["ppc"] - stats.mean(q["ppc"] for q in g)))
    rq = pearson([o[0] for o in wave_rank_obs], [o[1] for o in wave_rank_obs])
    res["size_vs_per_contract_edge_within_wave"] = {
        "_question": "Is the LARGEST position in a wave systematically the WORST per contract?",
        "n_legs": len(wave_rank_obs),
        "pearson_r_qty_vs_ppc_minus_wave_mean": round(rq, 4) if rq is not None else None,
        "_interpretation": "negative r == the fleet systematically puts the most contracts "
                           "behind the worst-performing exit configuration."}

    multi = {k: v for k, v in by_cluster.items() if len({p['arm'] for p in v}) > 1}
    in_multi = [p for v in multi.values() for p in v]
    all_loss = sum(-p["pnl"] for p in book if p["pnl"] < 0)
    res["cluster_share"] = {
        "n_contract_days": len(by_cluster), "n_multi_arm_contract_days": len(multi),
        "n_positions_total": len(book), "n_positions_in_multi_arm_clusters": len(in_multi),
        "share_positions_in_multi_arm_clusters": round(len(in_multi) / len(book), 4),
        "net_pnl_in_multi_arm_clusters": round(sum(p["pnl"] for p in in_multi), 2),
        "net_pnl_book": round(sum(p["pnl"] for p in book), 2),
        "loss_dollars_in_multi_arm_clusters": round(
            sum(-p["pnl"] for p in in_multi if p["pnl"] < 0), 2),
        "share_of_all_loss_dollars": round(
            sum(-p["pnl"] for p in in_multi if p["pnl"] < 0) / all_loss, 4) if all_loss else None,
    }
    res["_matched_pairs_sample"] = matched_pairs[:8]
    return res, matched_pairs, by_cluster


# ============================================================== Q2  BOOK-LEVEL TAIL
def q2_tail(book) -> dict:
    """How much of the fleet's fat day-tail is CORRELATION rather than strategy?

    Comparator: a DECORRELATED fleet. Each arm keeps its OWN realized daily-P&L values and
    its OWN set of traded days; the values are permuted WITHIN the arm, independently across
    arms, then re-summed by day. That destroys the cross-arm common factor and preserves
    every marginal. Anything the actual fleet's tail has that the permuted fleet's does not
    IS the pile-on."""
    rng = random.Random(SEED)
    res = {"_question": "What does the correlation do to the BOOK-level daily loss tail?"}
    mat = day_arm_matrix(book)
    days = sorted(mat)
    arms = sorted({a for d in mat.values() for a in d})
    actual = [round(sum(mat[d].values()), 2) for d in days]
    a_sorted = sorted(actual)
    res["actual_fleet_daily"] = {
        "n_days": len(actual), "worst_day": round(min(actual), 2),
        "p05_day": round(pct(a_sorted, 0.05), 2), "p10_day": round(pct(a_sorted, 0.10), 2),
        "median_day": round(stats.median(actual), 2),
        "sd_day": round(stats.pstdev(actual), 2),
        "mean_day": round(stats.mean(actual), 2),
        "sum": round(sum(actual), 2),
        "worst_3": [round(x, 2) for x in a_sorted[:3]]}

    per_arm_vals = {a: [mat[d][a] for d in days if a in mat[d]] for a in arms}
    per_arm_days = {a: [d for d in days if a in mat[d]] for a in arms}
    worsts, sds, p10s, sums = [], [], [], []
    for _ in range(N_DRAWS):
        acc = defaultdict(float)
        for a in arms:
            v = per_arm_vals[a][:]
            rng.shuffle(v)
            for d, x in zip(per_arm_days[a], v):
                acc[d] += x
        s = [acc[d] for d in days]
        worsts.append(min(s)); sds.append(stats.pstdev(s)); sums.append(sum(s))
        p10s.append(pct(sorted(s), 0.10))
    worsts.sort(); sds.sort(); p10s.sort()
    res["decorrelated_fleet_bootstrap"] = {
        "n_draws": N_DRAWS, "seed": SEED,
        "_method": ("each arm's own realized daily P&L permuted within its own traded days, "
                    "independently per arm, re-summed by day. Marginals + participation "
                    "preserved exactly; ONLY the cross-arm common factor is destroyed."),
        "worst_day_mean": round(stats.mean(worsts), 2),
        "worst_day_p05": round(pct(worsts, 0.05), 2),
        "worst_day_p50": round(pct(worsts, 0.50), 2),
        "sd_day_mean": round(stats.mean(sds), 2),
        "p10_day_mean": round(stats.mean(p10s), 2),
        "sum_is_invariant": round(stats.mean(sums), 2),
        "p_worst_day_at_or_below_actual": round(
            sum(1 for w in worsts if w <= min(actual)) / N_DRAWS, 4),
        "sd_inflation_from_correlation_x": round(
            stats.pstdev(actual) / stats.mean(sds), 3) if stats.mean(sds) else None,
        "worst_day_inflation_from_correlation_x": round(
            min(actual) / stats.mean(worsts), 3) if stats.mean(worsts) else None}

    # capital-matched single-arm comparator: run the WHOLE DAY'S fleet contract count through
    # ONE arm's realized per-contract result. Real per-contract numbers, real contract counts.
    day_qty = defaultdict(int)
    for p in book:
        day_qty[p["date_et"]] += p["qty"]
    single = {}
    for a in arms:
        vals = []
        for d in days:
            aq = sum(p["qty"] for p in book if p["date_et"] == d and p["arm"] == a)
            if aq == 0:
                continue
            appc = mat[d][a] / aq
            vals.append(appc * day_qty[d])
        if len(vals) >= 3:
            sv = sorted(vals)
            single[a] = {"n_days": len(vals), "worst_day": round(min(vals), 2),
                         "sd_day": round(stats.pstdev(vals), 2), "sum": round(sum(vals), 2),
                         "p10_day": round(pct(sv, 0.10), 2)}
    res["capital_matched_single_arm"] = single
    res["_capital_matched_note"] = (
        "Each arm's OWN realized per-contract P&L for the day, multiplied by the FLEET's total "
        "contract count that day. Answers: if all the money ran through ONE arm's decisions, "
        "how fat is the tail? Real per-contract dollars, real contract counts, no model.")
    return res


# ============================================================== Q3c  CONCURRENCY CAP
def apply_cap(book, n_cap: int, order_key):
    """Only n_cap arms may HOLD the same contract simultaneously. Positions are offered in
    `order_key` order inside each (date, symbol) cluster; a position is BLOCKED if n_cap
    already-allowed positions on that contract are still open at its entry instant. A blocked
    position occupies no slot and is dropped entirely (the arm simply does not take it).

    ASSUMPTION, STATED: a blocked arm does NOT substitute a different contract. Live, the
    fleet executor would deny the entry for that tick; whether the arm re-fires later is
    already captured because later entries are separate positions and are re-offered."""
    clusters = defaultdict(list)
    for p in book:
        clusters[(p["date_et"], p["symbol"])].append(p)
    allowed, blocked = [], []
    for _key, plist in clusters.items():
        held = []      # exit_ts_et of currently-allowed open positions
        for p in sorted(plist, key=order_key):
            t = p["entry_ts_et"]
            active = [x for x in held if x > t]
            if len(active) >= n_cap:
                blocked.append(p)
            else:
                allowed.append(p)
                held = active + [p["exit_ts_et"]]
    return allowed, blocked


def _cell(book, allowed, blocked, label) -> dict:
    base_days = defaultdict(float)
    new_days = defaultdict(float)
    for p in book:
        base_days[p["date_et"]] += p["pnl"]
    for p in allowed:
        new_days[p["date_et"]] += p["pnl"]
    deltas = {d: round(new_days[d] - base_days[d], 2) for d in sorted(base_days)}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    helped = {d: v for d, v in deltas.items() if v > 0.005}
    bw = [p["pnl"] for p in blocked if p["pnl"] > 0]
    bl = [p["pnl"] for p in blocked if p["pnl"] < 0]
    return {
        "cell": label,
        "n_blocked": len(blocked),
        "blocked_winners_n": len(bw), "blocked_winners_dollars": round(sum(bw), 2),
        "blocked_losers_n": len(bl), "blocked_losers_dollars": round(sum(bl), 2),
        "blocked_net_pnl_removed": round(sum(p["pnl"] for p in blocked), 2),
        "book_delta": round(-sum(p["pnl"] for p in blocked), 2),
        "book_before": round(sum(p["pnl"] for p in book), 2),
        "book_after": round(sum(p["pnl"] for p in allowed), 2),
        "tuesday_delta_2026_08_04": deltas.get(TUE, 0.0),
        "wednesday_delta_2026_08_05": deltas.get(WED, 0.0),
        "thursday_delta_2026_08_06": deltas.get(THU, 0.0),
        "TUESDAY_NO_HARM_GATE": "PASS" if deltas.get(TUE, 0.0) >= -0.005 else "FAIL",
        "n_days_harmed": len(harmed), "n_days_helped": len(helped),
        "days_harmed": harmed,
        "worst_day_before": round(min(base_days.values()), 2),
        "worst_day_after": round(min(new_days[d] for d in base_days), 2),
        "blocked_mean_pnl": round(stats.mean([p["pnl"] for p in blocked]), 2) if blocked else None,
        "population_mean_pnl": round(stats.mean([p["pnl"] for p in book]), 2),
        "all_day_deltas": {d: v for d, v in deltas.items() if abs(v) > 0.005},
    }


def concurrency_profile(book) -> dict:
    """THE SINGLE MOST DECISIVE TABLE IN THIS LANE. For every (date, contract), what is the
    MAXIMUM number of arms that ever held it at the same instant -- and what did that
    contract-day earn? If a cap is the right instrument, money must be LOST at the
    high-concurrency end. Pure ledger arithmetic."""
    cl = defaultdict(list)
    for p in book:
        cl[(p["date_et"], p["symbol"])].append(p)
    dist, pnl, npos = defaultdict(int), defaultdict(float), defaultdict(int)
    per_day_week = defaultdict(dict)
    for (d, sym), v in cl.items():
        m = max(sum(1 for q in v if q["entry_ts_et"] <= p["entry_ts_et"] < q["exit_ts_et"])
                for p in v)
        dist[m] += 1
        pnl[m] += sum(x["pnl"] for x in v)
        npos[m] += len(v)
        if d in WEEK:
            per_day_week[d][sym] = {"max_concurrent_arms": m, "n_entries": len(v),
                                    "net_pnl": round(sum(x["pnl"] for x in v), 2)}
    return {
        "_question": "Where in the concentration spectrum do the dollars actually sit?",
        "by_max_concurrent_arms": {
            str(k): {"n_contract_days": dist[k], "n_positions": npos[k],
                     "net_pnl": round(pnl[k], 2)} for k in sorted(dist)},
        "week_detail": {d: per_day_week[d] for d in WEEK if d in per_day_week},
        "_headline": ("If this table slopes UP with concurrency, an arm-concurrency cap is "
                      "aimed at the profitable end of the book and cannot be the loss-"
                      "magnitude instrument.")}


def q3c_concurrency(book) -> dict:
    rng = random.Random(SEED + 1)
    res = {"_question": "Only N of 5 arms may hold the same contract simultaneously (N=1,2,3)."}
    res["concurrency_profile"] = concurrency_profile(book)
    res["_priority_rule"] = (
        "FCFS by exact broker fill timestamp (microsecond). This is the only priority rule "
        "that is live-implementable without a new arbiter, but note it is a RACE: several "
        "clusters have two arms filling in the SAME second. The tie-break sweep below is "
        "therefore not decoration -- it is the honesty check on the whole cell.")
    cells = {}
    for n in (1, 2, 3, 4):
        allowed, blocked = apply_cap(book, n, order_key=lambda p: (p["entry_ts_et"], p["arm"]))
        cells[f"cap_{n}_fcfs_exact"] = _cell(book, allowed, blocked, f"cap-{n} FCFS-exact")

    # --- tie-break robustness: randomise order WITHIN the same entry MINUTE, N draws
    def minute_key_factory(r):
        cache = {}
        def key(p):
            m = p["entry_ts_et"][:16]
            k = (p["date_et"], p["symbol"], m, p["arm"])
            if k not in cache:
                cache[k] = r.random()
            return (m, cache[k])
        return key
    tie = {}
    for n in (1, 2, 3):
        totals, tues, weds = [], [], []
        for _ in range(2000):
            r2 = random.Random(rng.randrange(1 << 30))
            allowed, blocked = apply_cap(book, n, order_key=minute_key_factory(r2))
            c = _cell(book, allowed, blocked, "")
            totals.append(c["book_delta"]); tues.append(c["tuesday_delta_2026_08_04"])
            weds.append(c["wednesday_delta_2026_08_05"])
        totals.sort(); tues.sort(); weds.sort()
        tie[f"cap_{n}"] = {
            "n_draws": 2000,
            "book_delta_p05": round(pct(totals, 0.05), 2),
            "book_delta_p50": round(pct(totals, 0.50), 2),
            "book_delta_p95": round(pct(totals, 0.95), 2),
            "book_delta_best": round(totals[-1], 2), "book_delta_worst": round(totals[0], 2),
            "tuesday_delta_p50": round(pct(tues, 0.50), 2),
            "tuesday_delta_best": round(tues[-1], 2),
            "tuesday_never_harmed": bool(tues[-1] >= -0.005 and tues[0] >= -0.005),
            "share_of_draws_with_tuesday_harm": round(
                sum(1 for t in tues if t < -0.005) / len(tues), 4),
            "wednesday_delta_p50": round(pct(weds, 0.50), 2)}
    res["cells"] = cells
    res["tie_break_sweep"] = tie

    # --- THE DECISIVE TEST: does the cap SELECT bad trades, or just remove trades?
    #     Null = block the same NUMBER of positions, drawn at random from the positions that
    #     were ELIGIBLE to be blocked (i.e. not the first entrant on their contract-day, since
    #     no cap can ever block a first entrant). If the cap's realized delta sits inside this
    #     null, the cap has ZERO selective skill and is a pure leverage reduction.
    clusters = defaultdict(list)
    for p in book:
        clusters[(p["date_et"], p["symbol"])].append(p)
    eligible = []
    for plist in clusters.values():
        s = sorted(plist, key=lambda z: z["entry_ts_et"])
        eligible.extend(s[1:])
    nulls = {}
    for n in (1, 2, 3):
        obs = cells[f"cap_{n}_fcfs_exact"]["book_delta"]
        k = cells[f"cap_{n}_fcfs_exact"]["n_blocked"]
        draws = []
        r3 = random.Random(SEED + 100 + n)
        for _ in range(N_DRAWS):
            samp = r3.sample(eligible, min(k, len(eligible)))
            draws.append(-sum(p["pnl"] for p in samp))
        draws.sort()
        pctile = sum(1 for d in draws if d <= obs) / N_DRAWS
        nulls[f"cap_{n}"] = {
            "observed_book_delta": obs, "n_blocked": k, "n_eligible_pool": len(eligible),
            "null_mean_delta": round(stats.mean(draws), 2),
            "null_p05": round(pct(draws, 0.05), 2), "null_p50": round(pct(draws, 0.50), 2),
            "null_p95": round(pct(draws, 0.95), 2),
            "observed_percentile_in_null": round(pctile, 4),
            "one_sided_p_value_better_than_random": round(1 - pctile, 4),
            "verdict": ("NO SELECTIVE SKILL -- indistinguishable from removing the same number "
                        "of trades at random" if 0.05 <= pctile <= 0.95 else
                        "SELECTIVE (outside the random-removal null)")}
    res["random_removal_null"] = nulls
    return res


# ============================================================== Q3c-ext  FLEET ENTRY CAP
def q3c_ext_fleet_entry_cap(book) -> dict:
    """Adjacent cell (an EXTENSION of the task's 3(c), labelled as such): cap the TOTAL number
    of entries the whole fleet may make in one contract on one day, regardless of which arm.
    This is the asymmetric cousin of the concurrency cap -- it lets the first wave through at
    full size and only bites on the pile-on. Pure ledger arithmetic."""
    res = {"_question": "Cap TOTAL fleet entries per (date, contract), any arm."}
    clusters = defaultdict(list)
    for p in book:
        clusters[(p["date_et"], p["symbol"])].append(p)
    cells = {}
    for k in (3, 4, 5, 6, 7, 8):
        allowed, blocked = [], []
        for plist in clusters.values():
            for i, p in enumerate(sorted(plist, key=lambda z: z["entry_ts_et"])):
                (allowed if i < k else blocked).append(p)
        cells[f"fleet_entry_cap_{k}"] = _cell(book, allowed, blocked, f"fleet-entry-cap-{k}")
    res["cells"] = cells
    return res


# ============================================================== Q3b  EXIT STAGGER VALUE
def q3b_exit_stagger(book, by_cluster) -> dict:
    """What is the CURRENT dispersion of exit configs across arms actually worth?

    Method -- ledger arithmetic on real fills, ZERO modelling: inside a WAVE (same date, same
    contract, entries within WAVE_WINDOW_S, >=2 distinct arms) every arm bought effectively
    the same thing at effectively the same instant. Substituting one arm's OWN REALIZED
    per-contract result onto another arm's OWN REALIZED quantity is therefore a real,
    observed counterfactual, not a model. Four uniform comparators:
        worst-uniform : every arm gets the wave's WORST realized per-contract result
        mean-uniform  : every arm gets the wave's MEAN realized per-contract result
        best-uniform  : every arm gets the wave's BEST realized per-contract result  (ORACLE)
    ACTUAL - mean-uniform  = what the CURRENT (arbitrary) config-to-size assignment is worth.
    best  - worst          = the SPREAD the exit-config lane could in principle capture."""
    res = {"_question": "Do the arms' different TP1s / exit shapes actually buy anything?"}
    waves = []
    for (date, symbol), plist in by_cluster.items():
        plist = sorted(plist, key=lambda z: z["entry_ts_et"])
        # greedy wave grouping by entry proximity
        cur = [plist[0]]
        for p in plist[1:]:
            if secs(p["entry_ts_et"], cur[0]["entry_ts_et"]) <= WAVE_WINDOW_S:
                cur.append(p)
            else:
                waves.append((date, symbol, cur)); cur = [p]
        waves.append((date, symbol, cur))
    multi = [(d, s, w) for d, s, w in waves if len({p["arm"] for p in w}) > 1]

    rows, tot_actual, tot_worst, tot_mean, tot_best = [], 0.0, 0.0, 0.0, 0.0
    for d, s, w in multi:
        q = sum(p["qty"] for p in w)
        ppcs = [p["ppc"] for p in w]
        act = sum(p["pnl"] for p in w)
        wo, me, be = min(ppcs) * q, stats.mean(ppcs) * q, max(ppcs) * q
        tot_actual += act; tot_worst += wo; tot_mean += me; tot_best += be
        rows.append({"date": d, "symbol": s, "n_legs": len(w),
                     "arms": sorted({p["arm"] for p in w}), "total_qty": q,
                     "actual": round(act, 2), "worst_uniform": round(wo, 2),
                     "mean_uniform": round(me, 2), "best_uniform": round(be, 2),
                     "dispersion_value_vs_mean": round(act - me, 2),
                     "capturable_spread": round(be - wo, 2),
                     "ppc_by_arm": {p["arm"]: round(p["ppc"], 2) for p in w},
                     "qty_by_arm": {p["arm"]: p["qty"] for p in w}})
    rows.sort(key=lambda r: -abs(r["capturable_spread"]))
    res["n_multi_arm_waves"] = len(multi)
    res["totals"] = {
        "actual": round(tot_actual, 2), "worst_uniform": round(tot_worst, 2),
        "mean_uniform": round(tot_mean, 2), "best_uniform_ORACLE": round(tot_best, 2),
        "dispersion_value_vs_mean": round(tot_actual - tot_mean, 2),
        "insurance_vs_worst_uniform": round(tot_actual - tot_worst, 2),
        "capturable_spread_ORACLE": round(tot_best - tot_worst, 2),
        "_labels": {"best_uniform_ORACLE": "ORACLE BOUND -- requires knowing ex-ante which "
                                           "arm's exit config wins. NOT live-executable.",
                    "dispersion_value_vs_mean": "The live, realized value of having different "
                                                "exit configs across arms. Signed. This IS the "
                                                "answer to task 3(b)."}}
    # is the dispersion value distinguishable from a random config-to-size assignment?
    rng = random.Random(SEED + 7)
    draws = []
    for _ in range(N_DRAWS):
        t = 0.0
        for d, s, w in multi:
            ppcs = [p["ppc"] for p in w]
            perm = ppcs[:]
            rng.shuffle(perm)
            t += sum(x * p["qty"] for x, p in zip(perm, w))
        draws.append(t)
    draws.sort()
    obs = tot_actual
    res["random_config_assignment_null"] = {
        "n_draws": N_DRAWS, "observed_actual": round(obs, 2),
        "null_mean": round(stats.mean(draws), 2), "null_p05": round(pct(draws, 0.05), 2),
        "null_p50": round(pct(draws, 0.50), 2), "null_p95": round(pct(draws, 0.95), 2),
        "observed_percentile": round(sum(1 for x in draws if x <= obs) / N_DRAWS, 4),
        "_method": ("shuffle WHICH arm's realized per-contract outcome lands on WHICH arm's "
                    "realized quantity, within each wave. Tests whether the current "
                    "config-to-size pairing is better than a coin flip.")}
    res["waves_top10_by_spread"] = rows[:10]
    res["week_waves"] = [r for r in rows if r["date"] in WEEK]
    return res


# ============================================================== Q4  SILENT ARMS
def q4_silent_arms(book, by_cluster) -> dict:
    """bold-2 + safe-3: what did the silence do to the WEEK?

    Tuesday: they PARTICIPATED -- read straight off the ledger.
    Wednesday + Thursday: silent. Price each by SIBLING SUBSTITUTION on the identical
    contract in the same minutes (real fills, no model), and cross-check Thursday against the
    already-published real-OPRA / live-exit-core replay in EOD-2026-08-06-SILENT-ARMS.json."""
    res = {"_question": "Is the fleet better or worse off for having bold-2 and safe-3 dark?"}
    silent = ("bold-2", "safe-3")
    mat = day_arm_matrix(book)
    days = sorted(mat)
    # --- honest participation audit: the brief says "four consecutive zero-trade sessions"
    traded = {a: [d for d in days if a in mat[d]] for a in silent}
    last = {a: (traded[a][-1] if traded[a] else None) for a in silent}
    dark_streak = {a: [d for d in days if last[a] and d > last[a]] for a in silent}
    res["participation_audit"] = {
        "arm_traded_dates": traded,
        "last_traded_date": last,
        "consecutive_dark_sessions_by_broker_fills": {a: len(v) for a, v in dark_streak.items()},
        "dark_dates": dark_streak,
        "BRIEF_CORRECTION": ("The task brief states bold-2 and safe-3 have 'four consecutive "
                             "zero-trade sessions'. Broker fills say TWO (2026-08-05 and "
                             "2026-08-06) for BOTH arms -- each has real engine option fills "
                             "on 2026-08-04. Reported as measured. (The '4th session' framing "
                             "in EOD-2026-08-06-SILENT-ARMS counts consecutive EOD lenses "
                             "written, not zero-fill sessions.)")}
    res["week_actual_by_arm"] = {d: {a: round(mat[d].get(a, 0.0), 2) for a in silent}
                                 for d in WEEK}
    res["week_actual_silent_pair_total"] = {
        d: round(sum(mat[d].get(a, 0.0) for a in silent), 2) for d in WEEK}

    # --- sibling substitution for the dark days, CONFIG-MATCHED
    #     bold-2 and safe-3 both run the PLAIN registry ribbon_ride exit shape
    #     (tp1_premium_pct = 1.0). safe-3's exit_patch {stop_mode: structure, profit_lock_mode:
    #     trailing} is a no-op against that default; bold-2 is a core arm with no patch.
    #     risky-1 is the ONE arm carrying exit_patch.tp1_premium_pct = 0.5
    #     (accounts.json arms[3], FLEET-FULLSEND-R) -- its result is NOT transferable to
    #     either silent arm and is EXCLUDED from the substitution basis. Verified against
    #     automation/state/fleet/accounts.json this session.
    CONFIG_MATCHED = ("safe-2", "safe-3", "risky-3", "bold-2", "safe-1")
    # The contract each silent arm would plausibly have taken is the day's RIBBON-FAMILY
    # bearish trade -- the family both arms actually run. Wednesday's 776C came from
    # vwap_continuation, a family bold-2 is structurally never evaluated against (zero
    # extra_exec rows, EOD-2026-08-05-SILENT-ARMS) and that safe-3 was signal-absent for.
    # Attributing the 776C spiral to them would be an invention; it is EXCLUDED and disclosed.
    MARQUEE = {WED: "SPY260805P00772000", THU: "SPY260806P00770000"}

    def substitute(date, arm, qty_basis):
        sym = MARQUEE.get(date)
        plist = by_cluster.get((date, sym))
        if not plist:
            return None
        basis = [p for p in plist if p["arm"] in CONFIG_MATCHED]
        excluded = [p["arm"] for p in plist if p["arm"] not in CONFIG_MATCHED]
        if not basis:
            return None
        ppcs = sorted(p["ppc"] for p in basis)
        return {"contract": sym, "qty_basis": qty_basis,
                "config_matched_siblings": sorted({p["arm"] for p in basis}),
                "excluded_incompatible_config": sorted(set(excluded)),
                "sibling_ppc_min": round(min(ppcs), 2), "sibling_ppc_max": round(max(ppcs), 2),
                "sibling_ppc_median": round(stats.median(ppcs), 2),
                "pnl_range": [round(min(ppcs) * qty_basis, 2), round(max(ppcs) * qty_basis, 2)],
                "pnl_median_estimate": round(stats.median(ppcs) * qty_basis, 2),
                "sibling_detail": {p["arm"]: {"qty": p["qty"], "ppc": round(p["ppc"], 2),
                                              "pnl": p["pnl"]} for p in plist}}

    # qty basis = each arm's own last realized SPY-0DTE fill size (broker truth, not a model)
    qty_basis = {}
    for a in silent:
        sizes = [p["qty"] for p in book if p["arm"] == a and p["date_et"] >= "2026-08-03"]
        qty_basis[a] = int(stats.mode(sizes)) if sizes else 3
    res["qty_basis_from_own_broker_fills_since_08_03"] = qty_basis

    dark_est = {}
    for d in (WED, THU):
        dark_est[d] = {a: substitute(d, a, qty_basis[a]) for a in silent}
    res["dark_day_sibling_substitution"] = dark_est

    wed_pair = sum(dark_est[WED][a]["pnl_median_estimate"] for a in silent
                   if dark_est[WED][a])
    thu_pair = sum(dark_est[THU][a]["pnl_median_estimate"] for a in silent
                   if dark_est[THU][a])
    res["silence_netting"] = {
        "_convention": "POSITIVE = the silence HELPED the fleet (a loss avoided). "
                       "NEGATIVE = the silence COST the fleet (a gain forgone).",
        "tuesday_2026_08_04": {"status": "PARTICIPATED -- not silent",
                               "contribution": res["week_actual_silent_pair_total"][TUE]},
        "wednesday_2026_08_05_silence_effect": round(-wed_pair, 2),
        "thursday_2026_08_06_silence_effect": round(-thu_pair, 2),
        "net_silence_effect_over_the_two_dark_sessions": round(-(wed_pair + thu_pair), 2),
        "cross_check_thursday_published": {
            "source": "analysis/deep-research/EOD-2026-08-06-SILENT-ARMS.json",
            "published_silence_cost_usd": 911.35,
            "published_per_arm": {"bold-2": 564.90, "safe-3": 346.45},
            "method": "real OPRA 1-min bars through live exit_manager.plan_exit_actions "
                      "(that lens's own harness), parity-checked against safe-2 broker truth "
                      "at 2.4% error",
            "this_lane_estimate": round(-thu_pair, 2),
            "agreement_usd": round(abs(-thu_pair) - 911.35, 2),
            "note": "TWO INDEPENDENT METHODS on the same day. This lane substitutes a "
                    "config-matched sibling's REALIZED per-contract result (pure ledger "
                    "arithmetic, no exit model); the published lens replays real OPRA through "
                    "the live exit core. They should agree in sign and rough magnitude, and "
                    "the published figure is the better one -- quote THAT for Thursday."},
        "counterfactual_full_week_if_both_arms_had_been_ON": {
            "_label": "n=2 dark sessions. NOT an evidence bar. Direction only.",
            "wednesday_added_loss": round(wed_pair, 2),
            "thursday_added_gain_published": 911.35,
            "net_two_sessions_published_basis": round(wed_pair + 911.35, 2)}}
    return res


# ============================================================== main
def main() -> int:
    book = load_book()
    q1, matched, by_cluster = q1_correlation(book)
    out = {
        "_lane": "LEVER 5 -- FLEET CONCENTRATION (are we five bets or one bet in five sizes?)",
        "_generated_by": "backtest/tools/lever_correlation_2026_08_06.py",
        "_population": {
            "source": "automation/state/fills-ledger.jsonl (REAL BROKER FILLS)",
            "filter": "attribution=='engine' AND is_option AND NOT is_crypto",
            "reconstruction": "exit_shape_parity_study.reconstruct_positions",
            "n_positions": len(book),
            "n_dates": len({p["date_et"] for p in book}),
            "date_min": min(p["date_et"] for p in book),
            "date_max": max(p["date_et"] for p in book),
            "n_small": True,
            "n_small_note": "26 ET dates. Every cross-arm statistic here is n<=26 days. "
                            "There is NO second population: the 391-day replay is ONE arm "
                            "and structurally cannot express a fleet effect.",
            "scope_note": "SPY OPTIONS ONLY -- excludes the crypto-twin residual, so per-arm "
                          "and per-day totals differ by cents-to-dollars from the all-in "
                          "figures in the briefing (e.g. Wed risky-3 -1458.00 here vs "
                          "-1462.29 all-in). Both correct, different scopes."},
        "q1_correlation": q1,
        "q2_book_tail": q2_tail(book),
        "q3c_concurrency_cap": q3c_concurrency(book),
        "q3c_ext_fleet_entry_cap": q3c_ext_fleet_entry_cap(book),
        "q3b_exit_stagger": q3b_exit_stagger(book, by_cluster),
        "q4_silent_arms": q4_silent_arms(book, by_cluster),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"positions={len(book)} dates={out['_population']['n_dates']}")
    print("daily mean r  =", q1["daily_mean_pairwise_r"])
    print("trade pooled r=", q1["trade_level_pooled_r"])
    for k, v in out["q3c_concurrency_cap"]["cells"].items():
        print(f"  {k:22s} book {v['book_delta']:+9.2f}  TUE {v['tuesday_delta_2026_08_04']:+9.2f}"
              f"  WED {v['wednesday_delta_2026_08_05']:+9.2f}  gate={v['TUESDAY_NO_HARM_GATE']}")
    for k, v in out["q3c_ext_fleet_entry_cap"]["cells"].items():
        print(f"  {k:22s} book {v['book_delta']:+9.2f}  TUE {v['tuesday_delta_2026_08_04']:+9.2f}"
              f"  WED {v['wednesday_delta_2026_08_05']:+9.2f}  gate={v['TUESDAY_NO_HARM_GATE']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
