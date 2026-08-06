#!/usr/bin/env python
"""loss_anatomy_2026_08_06.py -- LANE 0: WHERE DO THE LOSS DOLLARS ACTUALLY LIVE?

J's ask (2026-08-06, after the close): "we need to dial in on how to NOT LOSE TWO THOUSAND
DOLLARS on Wednesday... we gotta KEEP OUR LOSSES SMALL so that way our wins can stack."

This is a LOSS-MAGNITUDE question, not a why-did-we-lose question. This module measures the
SHAPE of the loss distribution so the downstream lanes know whether a TAIL CAP or per-trade
tuning is the right instrument -- and decomposes 2026-08-05 into buckets that SUM.

DESCRIPTIVE ONLY. Validates nothing, ships nothing, arms nothing. Writes only under
analysis/deep-research/.

POPULATIONS (both real, both disclosed, never mixed in one column):
  A. THE BOOK -- every closed engine SPY-option POSITION in automation/state/fills-ledger.jsonl
     (attribution=="engine", is_option, not crypto), reconstructed by the repo's single
     canonical definition of a position (exit_shape_parity_study.reconstruct_positions).
     REAL BROKER FILLS. 26 distinct ET dates, 2026-06-26 .. 2026-08-06.
     (The brief calls this "the 25-day book" -- that count predates today's session; today
     2026-08-06 is the 26th date and is INCLUDED here. Both n's are reported.)
  B. THE REPLAY -- analysis/recommendations/engine-fullhist-replay-2026-07-23.json `trades`:
     191 RIDE_THE_RIBBON-family trades over 141 traded days inside a 387-RTH-day window
     (2025-01-02 .. 2026-07-22), entries frozen, exits re-walked through the REAL live
     exit core (exit_manager.plan_exit_actions via exit_manager_walk.walk_exit_manager).
     The brief's "391-day" population; the artifact's own metadata says 387 calendar RTH
     days -- reported as measured, not as remembered.

Run: backtest/.venv/Scripts/python.exe backtest/tools/loss_anatomy_2026_08_06.py
"""
from __future__ import annotations

import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
ARCHETYPES = REPO / "analysis" / "regime-library" / "day-archetypes.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "LOSS-ANATOMY-2026-08-06.json"

WED = "2026-08-05"
TUE = "2026-08-04"
THU = "2026-08-06"
MIN_CONTRACTS_RULE6 = 3          # CLAUDE.md Rule 6: "Min 3 contracts (2 TP + 1 runner)"


# ---------------------------------------------------------------- distribution primitives
def pct(sorted_vals: list[float], q: float) -> float:
    """Nearest-rank percentile on an ascending list. q in [0,1]. Explicit + testable;
    avoids numpy's interpolation so a reader can reproduce any cell by hand."""
    if not sorted_vals:
        return float("nan")
    k = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[min(k, len(sorted_vals)) - 1]


def describe_losses(vals: list[float], label: str) -> dict:
    """vals = SIGNED P&L. Loss magnitudes are the |negative| entries. Everything positive is
    reported as context so a reader never has to guess the denominator."""
    losses = sorted(-v for v in vals if v < 0)          # ascending magnitudes, all > 0
    wins = [v for v in vals if v > 0]
    flats = [v for v in vals if v == 0]
    total_loss = sum(losses)
    n = len(losses)
    if n == 0:
        return {"label": label, "n_total": len(vals), "n_loss": 0, "total_loss_dollars": 0.0}
    # Pareto: what share of all loss dollars comes from the worst k?
    desc = sorted(losses, reverse=True)
    n_top10 = max(1, math.ceil(0.10 * n))
    n_top20 = max(1, math.ceil(0.20 * n))
    return {
        "label": label,
        "n_total": len(vals),
        "n_loss": n, "n_win": len(wins), "n_flat": len(flats),
        "loss_rate": round(n / len(vals), 4) if vals else None,
        "total_loss_dollars": round(total_loss, 2),
        "total_win_dollars": round(sum(wins), 2),
        "net_dollars": round(sum(vals), 2),
        "mean_loss": round(stats.mean(losses), 2),
        "median_loss": round(stats.median(losses), 2),
        "p75_loss": round(pct(losses, 0.75), 2),
        "p90_loss": round(pct(losses, 0.90), 2),
        "p95_loss": round(pct(losses, 0.95), 2),
        "max_loss": round(losses[-1], 2),
        "worst_single_share": round(desc[0] / total_loss, 4) if total_loss else None,
        "n_worst_10pct": n_top10,
        "worst_10pct_share": round(sum(desc[:n_top10]) / total_loss, 4) if total_loss else None,
        "n_worst_20pct": n_top20,
        "worst_20pct_share": round(sum(desc[:n_top20]) / total_loss, 4) if total_loss else None,
        "worst_5_values": [round(x, 2) for x in desc[:5]],
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
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


# ---------------------------------------------------------------- population loaders
def load_book() -> list[dict]:
    """Population A. Real broker fills -> canonical positions. Adds entry_ts_et, ordinal
    (1-based index of this position within its own (arm, symbol, date) wave), and per-contract
    P&L. Sorted by entry time."""
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    by_id = {f["activity_id"]: f for f in fills}
    positions = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    # entry ts_et: recover from the first buy fill of the wave (reconstruct_positions keeps
    # entry_ts_utc only). Match on (arm, symbol, ts_utc).
    ts_et_by = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    for p in positions:
        p["entry_ts_et"] = ts_et_by.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["exit_ts_et"] = max(ef["ts_et"] for ef in p["exit_fills"])
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["pnl_per_contract"] = round(p["actual_exit_pnl"] / p["entry_qty"], 4) if p["entry_qty"] else 0.0
    positions.sort(key=lambda p: (p["entry_ts_utc"], p["arm"]))
    seq: dict = defaultdict(int)
    for p in positions:
        k = (p["arm"], p["symbol"], p["date_et"])
        seq[k] += 1
        p["ordinal"] = seq[k]
    for p in positions:                       # wave size = final ordinal for that key
        p["wave_n"] = seq[(p["arm"], p["symbol"], p["date_et"])]
    _ = by_id
    return positions


def load_replay() -> list[dict]:
    """Population B."""
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    out = []
    for t in d["trades"]:
        out.append({**t, "pnl": round(float(t["dollar_pnl"]), 2)})
    out.sort(key=lambda t: t["entry_time_et"])
    return out, d


# ---------------------------------------------------------------- Q1 distributions
def q1(book: list[dict], replay: list[dict], replay_meta: dict) -> dict:
    res: dict = {"_question": "Where do the loss dollars live? Pareto or spread?"}

    # --- BOOK, per day
    day_book: dict = defaultdict(float)
    for p in book:
        day_book[p["date_et"]] += p["pnl"]
    day_vals = [round(v, 2) for _, v in sorted(day_book.items())]
    res["book_per_day"] = describe_losses(day_vals, "BOOK / per trading day (real fills)")
    res["book_per_day"]["n_days"] = len(day_vals)
    res["book_per_day"]["days"] = {k: round(v, 2) for k, v in sorted(day_book.items())}

    # --- BOOK, per trade (position)
    res["book_per_trade"] = describe_losses([p["pnl"] for p in book],
                                            "BOOK / per position (real fills)")

    # --- BOOK ex-this-week (does the shape survive removing the week that motivated it?)
    week = {TUE, WED, THU}
    day_ex = [round(v, 2) for k, v in sorted(day_book.items()) if k not in week]
    res["book_per_day_ex_week"] = describe_losses(day_ex, "BOOK / per day, EX 08-04..08-06")
    res["book_per_day_ex_week"]["n_days"] = len(day_ex)
    res["book_per_trade_ex_week"] = describe_losses(
        [p["pnl"] for p in book if p["date_et"] not in week],
        "BOOK / per position, EX 08-04..08-06")

    # --- REPLAY, per day
    day_rep: dict = defaultdict(float)
    for t in replay:
        day_rep[t["date"]] += t["pnl"]
    rep_day_vals = [round(v, 2) for _, v in sorted(day_rep.items())]
    res["replay_per_day"] = describe_losses(rep_day_vals, "REPLAY / per traded day")
    res["replay_per_day"]["n_days"] = len(rep_day_vals)
    res["replay_per_day"]["n_calendar_rth_days"] = replay_meta["window"]["n_calendar_rth_days"]
    res["replay_per_day"]["worst_10_days"] = sorted(
        ({"date": k, "pnl": round(v, 2)} for k, v in day_rep.items()),
        key=lambda r: r["pnl"])[:10]

    # --- REPLAY, per trade
    res["replay_per_trade"] = describe_losses([t["pnl"] for t in replay],
                                              "REPLAY / per trade")

    # --- the instrument verdict: how much of ALL loss dollars does a per-DAY floor at
    #     various levels recover, vs a per-TRADE cap?
    def day_floor_recovery(vals: list[float], floor: float) -> float:
        """Dollars saved if every day were truncated at -floor (ORACLE bound -- a real
        daily kill switch fires INTRA-day and cannot be this efficient). LABELLED."""
        return round(sum(max(0.0, -v - floor) for v in vals), 2)

    res["oracle_day_floor_recovery_LABEL"] = (
        "ORACLE BOUND -- assumes a day is truncated at exactly -X with zero overshoot and "
        "zero cost to winning days. A live daily kill switch fires on a threshold CROSS and "
        "carries slippage + it also kills any recovery. NOT live-executable. Upper bound only.")
    res["oracle_day_floor_recovery_book"] = {
        f"-{f}": day_floor_recovery(day_vals, f) for f in (250, 400, 500, 750, 1000)}
    res["oracle_day_floor_recovery_replay"] = {
        f"-{f}": day_floor_recovery(rep_day_vals, f) for f in (250, 400, 500, 750, 1000)}
    return res


# ---------------------------------------------------------------- Q3 concentration
def q3(book: list[dict]) -> dict:
    res: dict = {"_question": "Is the fleet five bets or one bet in five sizes?"}
    arms = sorted({p["arm"] for p in book})
    day_arm: dict = defaultdict(lambda: defaultdict(float))
    for p in book:
        day_arm[p["date_et"]][p["arm"]] += p["pnl"]
    days = sorted(day_arm)

    per_arm = {}
    for a in arms:
        vals = [day_arm[d].get(a, 0.0) for d in days]
        traded = [p for p in book if p["arm"] == a]
        loss_d = sum(-p["pnl"] for p in traded if p["pnl"] < 0)
        per_arm[a] = {
            "n_positions": len(traded),
            "net_pnl": round(sum(p["pnl"] for p in traded), 2),
            "loss_dollars": round(loss_d, 2),
            "win_dollars": round(sum(p["pnl"] for p in traded if p["pnl"] > 0), 2),
            "n_days_traded": sum(1 for d in days if a in day_arm[d]),
            "worst_day": min(((d, round(day_arm[d].get(a, 0.0), 2)) for d in days),
                             key=lambda r: r[1]),
        }
    tot_loss = sum(v["loss_dollars"] for v in per_arm.values())
    for a in per_arm:
        per_arm[a]["share_of_all_loss_dollars"] = (
            round(per_arm[a]["loss_dollars"] / tot_loss, 4) if tot_loss else None)
    res["per_arm"] = per_arm
    res["total_loss_dollars_all_arms"] = round(tot_loss, 2)

    # pairwise correlation of arm DAILY P&L -- only over days where BOTH arms traded
    corr = {}
    overlap = {}
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            common = [d for d in days if a in day_arm[d] and b in day_arm[d]]
            xs = [day_arm[d][a] for d in common]
            ys = [day_arm[d][b] for d in common]
            r = pearson(xs, ys)
            corr[f"{a}|{b}"] = None if r is None else round(r, 4)
            overlap[f"{a}|{b}"] = len(common)
    res["pairwise_daily_pnl_correlation"] = corr
    res["pairwise_n_common_days"] = overlap
    rs = [v for v in corr.values() if v is not None]
    res["mean_pairwise_correlation"] = round(stats.mean(rs), 4) if rs else None

    # SAME-DIRECTION rate: on days both traded, how often do they agree in sign?
    same = {}
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            common = [d for d in days if a in day_arm[d] and b in day_arm[d]]
            if not common:
                continue
            agree = sum(1 for d in common
                        if (day_arm[d][a] > 0) == (day_arm[d][b] > 0))
            same[f"{a}|{b}"] = {"n": len(common), "same_sign": agree,
                                "rate": round(agree / len(common), 4)}
    res["daily_sign_agreement"] = same

    # diversification ratio: sd(portfolio) vs sum of sd(arms). 1.0 == zero diversification.
    port = [sum(day_arm[d].values()) for d in days]
    sd_port = stats.pstdev(port) if len(port) > 1 else 0.0
    sd_sum = sum(stats.pstdev([day_arm[d].get(a, 0.0) for d in days]) for a in arms) \
        if len(days) > 1 else 0.0
    res["portfolio_daily_sd"] = round(sd_port, 2)
    res["sum_of_arm_daily_sd"] = round(sd_sum, 2)
    res["diversification_ratio"] = round(sd_port / sd_sum, 4) if sd_sum else None
    res["diversification_ratio_note"] = (
        "sd(sum of arms) / sum(sd of arms). 1.0 == arms are perfectly co-moving (the fleet is "
        "ONE bet in N sizes). 1/sqrt(N)=0.447 for 5 independent equal-sized arms.")

    # SAME-CONTRACT-SAME-MINUTE overlap: the mechanical reason correlation is high.
    # NOTE: cluster membership is counted in POSITIONS, not in distinct arms -- an arm that
    # opens two positions on the same contract in the same minute contributes two. (An earlier
    # draft keyed the cluster on a set-of-arms and silently counted arms; caught by a
    # cross-check against an independent count, 133 vs 131.)
    by_key: dict = defaultdict(list)
    for p in book:
        by_key[(p["date_et"], p["symbol"], p["entry_ts_et"][:16])].append(p)
    multi = [k for k, v in by_key.items() if len({q["arm"] for q in v}) > 1]
    res["n_entry_minutes_total"] = len(by_key)
    res["n_entry_minutes_multi_arm"] = len(multi)
    res["multi_arm_entry_minute_rate"] = round(len(multi) / len(by_key), 4) if by_key else None
    multi_pos = [q for k in multi for q in by_key[k]]
    solo_pos = [q for k, v in by_key.items() if k not in set(multi) for q in v]
    res["n_positions_in_multi_arm_clusters"] = len(multi_pos)
    res["pct_positions_in_multi_arm_clusters"] = round(len(multi_pos) / len(book), 4)
    ml = sum(-q["pnl"] for q in multi_pos if q["pnl"] < 0)
    sl = sum(-q["pnl"] for q in solo_pos if q["pnl"] < 0)
    res["multi_arm_cluster_loss_dollars"] = round(ml, 2)
    res["solo_loss_dollars"] = round(sl, 2)
    res["multi_arm_share_of_loss_dollars"] = round(ml / (ml + sl), 4) if (ml + sl) else None
    res["multi_arm_cluster_net"] = round(sum(q["pnl"] for q in multi_pos), 2)
    res["solo_net"] = round(sum(q["pnl"] for q in solo_pos), 2)

    # count-vs-magnitude: does trade count PREDICT loss size? (counter-evidence to a bare cap)
    day_n: dict = defaultdict(int)
    day_pnl: dict = defaultdict(float)
    for p in book:
        day_n[p["date_et"]] += 1
        day_pnl[p["date_et"]] += p["pnl"]
    lx = [day_n[d] for d in day_pnl if day_pnl[d] < 0]
    ly = [-day_pnl[d] for d in day_pnl if day_pnl[d] < 0]
    res["corr_positions_vs_loss_magnitude_losing_days"] = (
        None if pearson(lx, ly) is None else round(pearson(lx, ly), 4))
    res["corr_positions_vs_loss_n_days"] = len(lx)
    res["losing_days_n_positions_vs_loss"] = sorted(
        ([day_n[d], round(-day_pnl[d], 2)] for d in day_pnl if day_pnl[d] < 0), reverse=True)
    return res


# ---------------------------------------------------------------- Q4 time of day
def bucket30(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    m30 = 0 if m < 30 else 30
    return f"{h:02d}:{m30:02d}"


def q4(book: list[dict], replay: list[dict]) -> dict:
    res: dict = {"_question": "Is loss magnitude concentrated in a time window? "
                              "(normalised by opportunity)"}

    def by_bucket(rows: list[dict], tkey) -> dict:
        b: dict = defaultdict(lambda: {"n": 0, "loss_dollars": 0.0, "win_dollars": 0.0,
                                       "net": 0.0, "n_loss": 0})
        for r in rows:
            k = bucket30(tkey(r))
            b[k]["n"] += 1
            b[k]["net"] += r["pnl"]
            if r["pnl"] < 0:
                b[k]["loss_dollars"] += -r["pnl"]
                b[k]["n_loss"] += 1
            else:
                b[k]["win_dollars"] += r["pnl"]
        out = {}
        tot_loss = sum(v["loss_dollars"] for v in b.values())
        for k in sorted(b):
            v = b[k]
            out[k] = {
                "n_entries": v["n"],
                "n_loss": v["n_loss"],
                "loss_dollars": round(v["loss_dollars"], 2),
                "share_of_all_loss_dollars": round(v["loss_dollars"] / tot_loss, 4) if tot_loss else None,
                "loss_dollars_per_entry": round(v["loss_dollars"] / v["n"], 2),
                "net": round(v["net"], 2),
                "net_per_entry": round(v["net"] / v["n"], 2),
            }
        return out

    res["book_by_entry_bucket"] = by_bucket(book, lambda p: p["entry_ts_et"][11:16])
    res["replay_by_entry_bucket"] = by_bucket(replay, lambda t: t["entry_time_et"][11:16])
    # book, ex-this-week -- is the first-45-min story a Wednesday artifact?
    week = {TUE, WED, THU}
    res["book_by_entry_bucket_ex_week"] = by_bucket(
        [p for p in book if p["date_et"] not in week], lambda p: p["entry_ts_et"][11:16])
    res["normalisation_note"] = (
        "loss_dollars_per_entry is the opportunity-normalised column. A bucket with more "
        "entries shows more raw loss dollars trivially; only the per-entry column is "
        "comparable across buckets. n_entries is stated in every row so no cell is read blind.")
    return res


def main() -> int:
    book = load_book()
    replay, replay_meta = load_replay()
    out = {
        "_doc": __doc__.strip().splitlines()[0],
        "generated_at_et": None,
        "populations": {
            "A_book": {
                "source": "automation/state/fills-ledger.jsonl (attribution=engine, is_option, "
                          "not crypto) -> exit_shape_parity_study.reconstruct_positions",
                "authority": "REAL BROKER FILLS",
                "n_positions": len(book),
                "n_distinct_et_dates": len({p["date_et"] for p in book}),
                "first_date": min(p["date_et"] for p in book),
                "last_date": max(p["date_et"] for p in book),
                "net_pnl": round(sum(p["pnl"] for p in book), 2),
            },
            "B_replay": {
                "source": "analysis/recommendations/engine-fullhist-replay-2026-07-23.json",
                "authority": "REAL OPRA entries frozen + exits re-walked through the LIVE "
                             "exit_manager.plan_exit_actions (exit_manager_walk.walk_exit_manager)",
                "family": "RIDE_THE_RIBBON (BEARISH_REJECTION + BULLISH_RECLAIM)",
                "n_trades": len(replay),
                "n_traded_days": len({t["date"] for t in replay}),
                "window": replay_meta["window"],
                "net_pnl": round(sum(t["pnl"] for t in replay), 2),
            },
        },
        "q1_distribution": q1(book, replay, replay_meta),
        "q3_concentration": q3(book),
        "q4_time_of_day": q4(book, replay),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[loss-anatomy] wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
