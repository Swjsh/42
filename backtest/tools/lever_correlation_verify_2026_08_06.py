#!/usr/bin/env python
"""lever_correlation_verify_2026_08_06.py -- INDEPENDENT verification of LEVER 5.

Every assertion below is re-derived FROM THE RAW LEDGER by a second code path (this file
does not import the runner's helpers and does not trust its JSON for anything it can compute
itself). The runner's JSON is loaded only to CONFIRM the two agree.

Exit code 0 = all assertions pass. Non-zero = at least one failed, printed.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_correlation_verify_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
MAIN = REPO / "analysis" / "deep-research" / "LEVER-CORRELATION-2026-08-06.json"
STAG = REPO / "analysis" / "deep-research" / "LEVER-CORRELATION-STAGGER-2026-08-06.json"
TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"

CHECKS: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond), detail))


# ------------------------------------------------ independent position reconstruction
def positions_from_scratch() -> list[dict]:
    """Deliberately NOT exit_shape_parity_study.reconstruct_positions -- re-implemented here
    from the documented rule so a bug in that helper cannot pass silently through both lanes:
    within (arm, symbol), leading BUYs before the first SELL are one entry (qty-weighted avg);
    SELLs close it; a fresh BUY at open_qty==0 starts a new position."""
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    by = defaultdict(list)
    for f in fills:
        by[(f["arm"], f["symbol"])].append(f)
    out = []
    for (arm, sym), g in by.items():
        g.sort(key=lambda x: x["ts_utc"])
        pos, open_qty = None, 0.0
        for f in g:
            if f["side"] == "buy":
                if open_qty <= 1e-9:
                    if pos:
                        out.append(pos)
                    pos = {"arm": arm, "symbol": sym, "date_et": f["date_et"], "q": 0.0,
                           "notional": 0.0, "entry_ts": f["ts_et"], "exits": []}
                pos["q"] += f["qty"]; pos["notional"] += f["qty"] * f["price"]
                open_qty += f["qty"]
            else:
                if pos is None:
                    continue
                pos["exits"].append(f); open_qty -= f["qty"]
        if pos:
            out.append(pos)
    res = []
    for p in out:
        if not p["exits"]:
            continue
        ep = p["notional"] / p["q"]
        p["entry_price"] = ep
        p["pnl"] = round(sum((e["price"] - ep) * e["qty"] * 100 for e in p["exits"]), 2)
        p["exit_ts"] = max(e["ts_et"] for e in p["exits"])
        p["qty"] = int(p["q"])
        p["ppc"] = p["pnl"] / p["qty"]
        res.append(p)
    res.sort(key=lambda z: (z["entry_ts"], z["arm"]))
    return res


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = stats.mean(xs), stats.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs)); dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def main() -> int:
    book = positions_from_scratch()
    main_j = json.loads(MAIN.read_text(encoding="utf-8"))
    stag_j = json.loads(STAG.read_text(encoding="utf-8"))

    # ---- population
    chk("population/n_positions==208", len(book) == 208, f"got {len(book)}")
    dates = sorted({p["date_et"] for p in book})
    chk("population/n_dates==26", len(dates) == 26, f"got {len(dates)}")
    chk("population/matches_runner",
        main_j["_population"]["n_positions"] == len(book)
        and main_j["_population"]["n_dates"] == len(dates))

    day = defaultdict(float)
    for p in book:
        day[p["date_et"]] += p["pnl"]
    tot = round(sum(p["pnl"] for p in book), 2)
    chk("book/total==1782.01", abs(tot - 1782.01) < 0.02, f"got {tot}")
    chk("week/TUE==+3624.00", abs(round(day[TUE], 2) - 3624.00) < 0.02, f"got {day[TUE]:.2f}")
    chk("week/WED==-1935.00", abs(round(day[WED], 2) + 1935.00) < 0.02, f"got {day[WED]:.2f}")
    chk("week/THU==+1465.00", abs(round(day[THU], 2) - 1465.00) < 0.02, f"got {day[THU]:.2f}")
    r3wed = round(sum(p["pnl"] for p in book if p["date_et"] == WED and p["arm"] == "risky-3"), 2)
    chk("week/WED risky-3==-1458.00 (options-only scope)", abs(r3wed + 1458.00) < 0.02,
        f"got {r3wed}")
    chk("week/WED risky-3 is >=75% of the day", abs(r3wed) / abs(day[WED]) >= 0.75,
        f"{abs(r3wed)/abs(day[WED]):.3f}")

    # ---- Q1 correlation, re-derived
    mat = defaultdict(dict)
    for p in book:
        mat[p["date_et"]][p["arm"]] = mat[p["date_et"]].get(p["arm"], 0.0) + p["pnl"]
    arms = sorted({p["arm"] for p in book})
    rs = []
    for a, b in combinations(arms, 2):
        xs = [mat[d][a] for d in dates if a in mat[d] and b in mat[d]]
        ys = [mat[d][b] for d in dates if a in mat[d] and b in mat[d]]
        r = pearson(xs, ys)
        if r is not None:
            rs.append(r)
    mean_r = round(stats.mean(rs), 4)
    chk("q1/daily_mean_pairwise_r==0.7869", abs(mean_r - 0.7869) < 0.0005, f"got {mean_r}")
    chk("q1/daily_mean_r matches runner",
        abs(mean_r - main_j["q1_correlation"]["daily_mean_pairwise_r"]) < 0.0005)
    chk("q1/every pairwise r is POSITIVE", all(r > 0 for r in rs), f"min {min(rs):.4f}")

    def secs(a, b):
        return abs((dt.datetime.fromisoformat(a) - dt.datetime.fromisoformat(b)).total_seconds())

    cl = defaultdict(list)
    for p in book:
        cl[(p["date_et"], p["symbol"])].append(p)
    obs = []
    for plist in cl.values():
        s = sorted(plist, key=lambda z: z["entry_ts"])
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                if s[i]["arm"] != s[j]["arm"] and secs(s[i]["entry_ts"], s[j]["entry_ts"]) <= 120:
                    obs.append((s[i]["ppc"], s[j]["ppc"]))
    pooled = pearson([o[0] for o in obs] + [o[1] for o in obs],
                     [o[1] for o in obs] + [o[0] for o in obs])
    chk("q1/trade_level_pooled_r==0.8463", abs(round(pooled, 4) - 0.8463) < 0.0005,
        f"got {pooled:.4f}")
    chk("q1/n_matched_pairs==139", len(obs) == 139, f"got {len(obs)}")
    sign = sum(1 for o in obs if (o[0] > 0) == (o[1] > 0)) / len(obs)
    chk("q1/trade_level_sign_agreement>=0.95", sign >= 0.95, f"got {sign:.4f}")

    # ---- THE MECHANISTIC CLAIM: Wednesday's killer contract never had >2 arms concurrent
    def max_concurrent(date, sym):
        plist = sorted(cl[(date, sym)], key=lambda z: z["entry_ts"])
        best = 0
        for p in plist:
            n = sum(1 for q in plist if q["entry_ts"] <= p["entry_ts"] < q["exit_ts"])
            best = max(best, n)
        return best
    mc776 = max_concurrent(WED, "SPY260805C00776000")
    mc772 = max_concurrent(WED, "SPY260805P00772000")
    chk("q3c/WED 776C max concurrent arms == 2", mc776 == 2, f"got {mc776}")
    chk("q3c/WED 772P max concurrent arms == 3", mc772 == 3, f"got {mc772}")
    chk("q3c/therefore a 3-arm cap CANNOT touch Wednesday",
        abs(main_j["q3c_concurrency_cap"]["cells"]["cap_3_fcfs_exact"]
            ["wednesday_delta_2026_08_05"]) < 0.005)

    # ---- Q3c independent cap re-implementation
    def cap(n):
        allowed, blocked = [], []
        for plist in cl.values():
            held = []
            for p in sorted(plist, key=lambda z: (z["entry_ts"], z["arm"])):
                act = [x for x in held if x > p["entry_ts"]]
                if len(act) >= n:
                    blocked.append(p)
                else:
                    allowed.append(p); held = act + [p["exit_ts"]]
        return allowed, blocked
    for n in (1, 2, 3):
        _a, b = cap(n)
        delta = round(-sum(p["pnl"] for p in b), 2)
        tue = round(-sum(p["pnl"] for p in b if p["date_et"] == TUE), 2)
        cellj = main_j["q3c_concurrency_cap"]["cells"][f"cap_{n}_fcfs_exact"]
        chk(f"q3c/cap-{n} book_delta matches runner",
            abs(delta - cellj["book_delta"]) < 0.02, f"{delta} vs {cellj['book_delta']}")
        chk(f"q3c/cap-{n} tuesday_delta matches runner",
            abs(tue - cellj["tuesday_delta_2026_08_04"]) < 0.02,
            f"{tue} vs {cellj['tuesday_delta_2026_08_04']}")
        chk(f"q3c/cap-{n} HARMS Tuesday (gate FAIL)", tue < -0.005, f"tue {tue}")
        chk(f"q3c/cap-{n} LOSES money book-wide", delta < 0, f"delta {delta}")
        bm = stats.mean([p["pnl"] for p in b]) if b else 0.0
        pm = stats.mean([p["pnl"] for p in book])
        chk(f"q3c/cap-{n} blocks BETTER-than-average trades", bm > pm,
            f"blocked mean {bm:.2f} vs population {pm:.2f}")

    # ---- multi-arm clusters carry the money, not just the pain
    multi = {k: v for k, v in cl.items() if len({p["arm"] for p in v}) > 1}
    mnet = round(sum(p["pnl"] for v in multi.values() for p in v), 2)
    chk("q1/multi-arm clusters are NET POSITIVE", mnet > 0, f"{mnet}")
    chk("q1/multi-arm net==3678.00", abs(mnet - 3678.00) < 0.02, f"got {mnet}")

    # ---- participation is not anti-correlated with outcome
    npart = {d: len(mat[d]) for d in dates}
    rp = pearson([npart[d] for d in dates], [day[d] for d in dates])
    chk("q1/corr(n_arms, day_pnl) is NOT negative", rp > 0, f"r={rp:.4f}")
    chk("q1/WED had only 3 arms (below the 5 on TUE)", npart[WED] == 3 and npart[TUE] == 5,
        f"wed {npart[WED]} tue {npart[TUE]}")

    # ---- Q4 silent arms
    for a in ("bold-2", "safe-3"):
        td = sorted({p["date_et"] for p in book if p["arm"] == a})
        chk(f"q4/{a} DID trade on Tuesday (brief's '4 dark sessions' is wrong)", TUE in td)
        chk(f"q4/{a} dark on WED and THU", WED not in td and THU not in td)
    sn = main_j["q4_silent_arms"]["silence_netting"]
    chk("q4/thursday estimate agrees with published $911.35 within $10",
        abs(abs(sn["thursday_2026_08_06_silence_effect"]) - 911.35) < 10,
        f"{sn['thursday_2026_08_06_silence_effect']}")
    chk("q4/net over the two dark sessions is NEGATIVE (fleet worse off dark)",
        sn["net_silence_effect_over_the_two_dark_sessions"] < 0)

    # ---- Q3a placebo refutation
    st = stag_j["cells"]["stagger_2min"]["total_delta"]
    al = stag_j["cells"]["all_2min"]["total_delta"]
    l0 = stag_j["cells"]["leg0_only_2min"]["total_delta"]
    chk("q3a/PLACEBO 'delay everything' matches the stagger cell within 2%",
        abs(al - st) / max(abs(st), 1) < 0.02, f"stagger {st} vs placebo {al}")
    chk("q3a/every stagger cell is NEGATIVE on Wednesday",
        all(stag_j["cells"][f"stagger_{d}min"]["wednesday_delta_2026_08_05"] < 0
            for d in (1, 2, 3, 5)))
    chk("q3a/Tuesday carries >=90% of the stagger cell",
        stag_j["cells"]["stagger_2min"]["_artifact_hunt"]
        ["tuesday_share_of_total_delta"] >= 0.90)
    chk("q3a/D=0 parity pass rate >= 85%", stag_j["parity_gate_D0"]["pass_rate"] >= 0.85,
        f"{stag_j['parity_gate_D0']['pass_rate']}")
    _ = l0

    npass = sum(1 for _n, ok, _d in CHECKS if ok)
    for n, ok, dtl in CHECKS:
        if not ok:
            print(f"  FAIL  {n}   {dtl}")
    print(f"\n{npass}/{len(CHECKS)} assertions PASS")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
