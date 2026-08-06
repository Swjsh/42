#!/usr/bin/env python
"""chop_admissibility_2026_08_06.py -- LANE 5: DON'T TRADE CHOP, honestly.

Pre-registration: analysis/recommendations/chop-defense-prereg-2026-08-06.json
(commit 5737488a, frozen BEFORE this file existed -- provable with
`git merge-base --is-ancestor 5737488a <this file's first commit>`).

The day-level chop classifier is DEAD (20.9% vs 39.1% baseline) and is NOT resurrected
here. This lane asks whether PER-TRADE, INTRA-DAY proxies -- computable at entry time from
closed bars and the arm's own booked outcomes -- achieve what the day-level classifier
could not. Twelve frozen cells, three families:

  A  consecutive-loss state on the SAME (arm,date,contract) / (arm,date,setup) key
  B  realized intraday range at entry vs the 20-day median at the same time-of-day cutoff
  C  structure timing (BOS/CHoCH on the day's closed 5m bars): none-yet / stale / against

Semantics per prereg: taken-counted sequential walk (family A) -- a BLOCKED position
contributes $0 and never increments any counter; exits book before entries at equal
timestamps. Families B/C are stateless predicates (deletion arithmetic). ABSTAIN never
blocks. Verdict cap: NOTHING here may exceed PREREG; C-AGAINST is capped at SHADOW
(graveyard-adjacent: structure_shift_confirmation died 2026-07-28).

Run: backtest/.venv/Scripts/python.exe backtest/tools/chop_admissibility_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lever_entry_count_2026_08_06 as L4  # noqa: E402  (the trusted substrate)
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import walk_structure  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
OUT_JSON = REPO / "analysis" / "deep-research" / "CHOP-DEFENSE-2026-08-06.json"
PREREG = "analysis/recommendations/chop-defense-prereg-2026-08-06.json @ 5737488a"
STRUCT_WINDOW = 2          # DEFAULT_WINDOW, frozen in prereg
RR_MIN_PRIOR_DAYS = 15     # frozen: ABSTAIN below this
RR_PRIOR_DAYS = 20


# ══════════════════════════════════════════════════════ structure events per day
def day_structure_events(bars5: list[dict]) -> list[dict]:
    """BOS/CHoCH events for ONE day's 5m RTH bars (list of {t,o,h,l,c}, closed bars,
    chronological). Returns [{kind, direction, break_close_et}] where break_close_et is
    the CLOSE time of the break bar -- the moment the event becomes knowable. Per-day
    only (no cross-day memory), per prereg."""
    rth = [b for b in bars5 if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)]
    if len(rth) < 2 * STRUCT_WINDOW + 1:
        return []
    utc = dt.timezone.utc
    bars = [Bar(open_time=b["t"].replace(tzinfo=utc), open=b["o"], high=b["h"],
                low=b["l"], close=b["c"], volume=0.0, granularity_seconds=300,
                source="spy5m") for b in rth]
    swings = find_swing_points(bars, window=STRUCT_WINDOW, inclusive_right=True)
    _trend, events = walk_structure(bars, swings, STRUCT_WINDOW)
    return [{"kind": e.kind, "direction": e.direction,
             "break_close_et": rth[e.break_index]["t"] + dt.timedelta(minutes=5)}
            for e in events]


def annotate_structure(rows: list[dict], m5: dict, cache: dict) -> None:
    """Per entry: n_struct_events_done, minutes_since_last_event, last_event_dir --
    all from events whose break bar is FULLY CLOSED at/<= the entry timestamp."""
    for p in rows:
        d, cut = p["date_et"], p["entry_dt"]
        if d not in cache:
            cache[d] = day_structure_events(m5.get(d, []))
        done = [e for e in cache[d] if cut is not None and e["break_close_et"] <= cut]
        p["n_struct_events_done"] = len(done) if cut is not None else None
        p["mins_since_struct"] = (
            round((cut - done[-1]["break_close_et"]).total_seconds() / 60.0, 1)
            if done else None)
        p["last_struct_dir"] = done[-1]["direction"] if done else None


# ══════════════════════════════════════════════════════ realized-range ratio
def _cutoff_range(bars5: list[dict], cutoff_t: dt.time) -> "float | None":
    """Session high-low over 5m RTH bars fully closed by wall-clock `cutoff_t`."""
    xs = [b for b in bars5
          if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
          and (b["t"] + dt.timedelta(minutes=5)).time() <= cutoff_t]
    if not xs:
        return None
    return max(b["h"] for b in xs) - min(b["l"] for b in xs)


def annotate_rr(rows: list[dict], m5: dict) -> None:
    """rr = today's realized range at entry / median of the prior 20 trading days'
    ranges at the SAME time-of-day cutoff. ABSTAIN (None) if <15 prior days or no
    closed bar yet today. Prior days = dates present in the 5m dataset, strictly
    before the entry's date -- completed history only, no look-ahead."""
    all_days = sorted(m5)
    for p in rows:
        p["rr"] = None
        d, cut = p["date_et"], p["entry_dt"]
        if cut is None or d not in m5:
            continue
        cutoff_t = cut.time()
        today_rng = _cutoff_range(m5[d], cutoff_t)
        if today_rng is None:
            continue
        priors = [x for x in all_days if x < d][-RR_PRIOR_DAYS:]
        if len(priors) < RR_MIN_PRIOR_DAYS:
            continue
        vals = [r for x in priors if (r := _cutoff_range(m5[x], cutoff_t)) is not None]
        if len(vals) < RR_MIN_PRIOR_DAYS:
            continue
        med = statistics.median(vals)
        if med > 0:
            p["rr"] = round(today_rng / med, 4)


# ══════════════════════════════════════════════════════ family A sequential walk
def walk_consec(rows: list[dict], keyfn, n: int) -> "tuple[list[dict], int]":
    """Taken-counted sequential walk per prereg: per ET date, one chronological event
    stream, exits book BEFORE entries at equal timestamps. Block an entry when the
    key's consecutive-TAKEN-loser count >= n. A blocked position books nothing and
    never increments the counter. keyfn -> hashable or None (None = ABSTAIN)."""
    by_date: dict = defaultdict(list)
    for p in rows:
        by_date[p["date_et"]].append(p)
    blocked: list[dict] = []
    n_abstain = 0
    for date in sorted(by_date):
        consec: dict = defaultdict(int)
        entries = sorted(by_date[date], key=lambda q: (q["entry_dt"], q["arm"]))
        pending: list = []          # (exit_dt, id, key, pnl)
        ei = 0
        while ei < len(entries) or pending:
            nxt = entries[ei] if ei < len(entries) else None
            pending.sort(key=lambda e: e[0])
            take_exit = pending and (nxt is None or pending[0][0] <= nxt["entry_dt"])
            if take_exit:
                _ts, _i, key, pnl = pending.pop(0)
                if pnl < 0:
                    consec[key] += 1
                else:
                    consec[key] = 0
                continue
            ei += 1
            p = nxt
            key = keyfn(p)
            if key is None:
                n_abstain += 1
                continue                       # ABSTAIN -- never block on a guess
            if consec[key] >= n:
                blocked.append(p)
                continue                       # blocked: books nothing, queues nothing
            if p["exit_dt"] is not None:
                pending.append((p["exit_dt"], id(p), key, p["pnl"]))
    return blocked, n_abstain


# ══════════════════════════════════════════════════════ cells
def run_cells(book, base, m5, label_prefix="") -> "tuple[list[dict], dict]":
    """All 12 frozen cells on one population. Returns (rows, feature_census)."""
    struct_cache: dict = {}
    annotate_structure(book, m5, struct_cache)
    annotate_rr(book, m5)

    census = {
        "n": len(book),
        "zero_struct_entries": sum(1 for p in book if p.get("n_struct_events_done") == 0),
        "struct_unmeasurable": sum(1 for p in book if p.get("n_struct_events_done") is None),
        "rr_measured": sum(1 for p in book if p.get("rr") is not None),
        "rr_quartiles": None,
        "mins_since_struct_median": None,
    }
    rrs = sorted(p["rr"] for p in book if p.get("rr") is not None)
    if len(rrs) >= 4:
        census["rr_quartiles"] = [round(rrs[len(rrs) // 4], 3), round(rrs[len(rrs) // 2], 3),
                                  round(rrs[3 * len(rrs) // 4], 3)]
    mins = sorted(p["mins_since_struct"] for p in book
                  if p.get("mins_since_struct") is not None)
    if mins:
        census["mins_since_struct_median"] = mins[len(mins) // 2]

    cells = []

    # family A -- sequential walk
    for kind, keyfn in (
            ("CONTRACT", lambda p: (p["arm"], p["date_et"], p["symbol"])),
            ("SETUP", lambda p: (p["arm"], p["date_et"], p["setup"])
             if p.get("setup") is not None else None)):
        for n in (2, 3):
            bl, ab = walk_consec(book, keyfn, n)
            r = L4.score(base, bl, book, f"{label_prefix}A-CONSEC-{kind}-{n}", n_abstain=ab)
            r["family"] = "A"
            cells.append((r, bl))

    # family B -- stateless predicate
    for x in (0.50, 0.60, 0.70, 0.80):
        bl, ab = L4.apply_predicate(
            book, lambda p, x=x: (None if p.get("rr") is None else p["rr"] < x))
        r = L4.score(base, bl, book, f"{label_prefix}B-RR-{int(x*100):03d}", n_abstain=ab)
        r["family"] = "B"
        cells.append((r, bl))

    # family C -- stateless predicates
    def c_noevt(p):
        v = p.get("n_struct_events_done")
        return None if v is None else (v == 0)

    def c_tsse(p, m):
        if p.get("n_struct_events_done") in (None, 0):
            return None                          # NOEVT measured by C-NOEVT, never here
        return p["mins_since_struct"] > m

    def c_against(p):
        if p.get("last_struct_dir") is None:
            return None
        want = "bullish" if p["side"] == "C" else "bearish"
        return p["last_struct_dir"] != want

    for cid, pred in (("C-NOEVT", c_noevt),
                      ("C-TSSE-30", lambda p: c_tsse(p, 30)),
                      ("C-TSSE-60", lambda p: c_tsse(p, 60)),
                      ("C-AGAINST", c_against)):
        bl, ab = L4.apply_predicate(book, pred)
        r = L4.score(base, bl, book, f"{label_prefix}{cid}", n_abstain=ab)
        r["family"] = "C"
        cells.append((r, bl))

    return cells, census


def main() -> int:
    print("[chop] loading population A (broker fills) ...")
    book = L4.load_book()
    base = L4.day_totals(book)
    dates = sorted(base)
    book_total = round(sum(base.values()), 2)

    # ── TRUST GATE (frozen in prereg): refuse to print any cell if base != broker truth
    checks = {"book_total": (book_total, 1782.01), "n_positions": (len(book), 208),
              "n_dates": (len(dates), 26), "tue": (base[TUE], 3624.00),
              "wed": (base[WED], -1935.00), "thu": (base[THU], 1465.00)}
    print("=== TRUST GATE ===")
    ok = True
    for k, (got, want) in checks.items():
        good = abs(got - want) < 0.02
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {k:12s} got {got} want {want}")
    if not ok:
        print("BASE DOES NOT RECONCILE -- refusing to report any cell.")
        return 1

    m5 = L4.load_5m()
    cells_a, census_a = run_cells(book, base, m5)

    # ── population B (391-day replay, pinned 2025 lineage)
    print("[chop] loading population B (replay) ...")
    replay, replay_meta = L4.load_replay()
    rbase = L4.day_totals(replay)
    b5 = L4.load_5m(REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-22.csv")
    # B rows need side ('C'/'P') for C-AGAINST; replay trades carry direction via symbol
    for t in replay:
        t.setdefault("side", "C" if "C00" in str(t.get("symbol", "")) else "P")
        t.setdefault("arm", "replay")
        t.setdefault("setup", t.get("setup_name") or "replay_setup")
        t.setdefault("exit_dt", None)
    # family A structural claim on B -- VERIFY, don't assume (prereg)
    seq: dict = defaultdict(int)
    max_consec_contract = 0
    for t in sorted(replay, key=lambda q: (q["date_et"], str(q.get("entry_time_et")))):
        k = (t["date_et"], t["symbol"])
        if t["pnl"] < 0:
            seq[k] += 1
            max_consec_contract = max(max_consec_contract, seq[k])
        else:
            seq[k] = 0
    popB_A_noop = max_consec_contract < 2
    print(f"[chop] population B max consecutive same-contract losers = "
          f"{max_consec_contract} -> family A {'NO-OP' if popB_A_noop else 'MEASURABLE'}")

    cells_b, census_b = run_cells(replay, rbase, b5, label_prefix="B|")

    # ── gates + multiplicity on population A
    popB_by_id: dict = {}
    for r, _bl in cells_b:
        popB_by_id[r["cell"].removeprefix("B|")] = (
            "NO_OP" if r["n_blocked"] == 0 else r["delta_total"])
    rows = []
    for r, bl in cells_a:
        cid = r["cell"]
        popB = popB_by_id.get(cid, "NO_OP")
        if r["family"] == "A" and popB_A_noop:
            popB = "NO_OP"
        L4.gates(r, is_defect_fix=False, popB=popB)
        r["p_within_day"] = L4.within_day_permutation(book, bl)
        # frozen verdict caps: battery-wide PREREG ceiling; C-AGAINST capped SHADOW
        if r["verdict"] == "SHIP":
            r["verdict"] = "PREREG"
        if cid == "C-AGAINST" and r["verdict"] in ("SHIP", "PREREG"):
            r["verdict"] = "SHADOW (capped: graveyard-adjacent)"
        rows.append(r)

    praw = {r["cell"]: r.get("p_within_day") for r in rows}
    q = L4.bh_adjust(praw)
    for r in rows:
        p = r.get("p_within_day")
        r["p_bonferroni_x17"] = (round(min(1.0, p * 17), 4) if p is not None else None)
        r["q_benjamini_hochberg"] = q.get(r["cell"])

    out = {
        "_doc": __doc__.strip().splitlines()[0],
        "artifact": "CHOP-DEFENSE-2026-08-06",
        "prereg": PREREG,
        "population_A": {"n_positions": len(book), "n_dates": len(dates),
                         "net_usd": book_total, "window": [dates[0], dates[-1]],
                         "feature_census": census_a},
        "population_B": {"n_trades": len(replay), "n_traded_days": len(rbase),
                         "net_usd": round(sum(rbase.values()), 2),
                         "family_A_structural": {
                             "max_consec_same_contract_losers": max_consec_contract,
                             "family_A_is_noop_on_B": popB_A_noop},
                         "feature_census": census_b,
                         "lineage": "spy_5m_2025-01-01_2026-07-22.csv (pinned)"},
        "cells": rows,
        "cells_population_B_detail": [r for r, _ in cells_b],
    }
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    hdr = ["cell", "n_blocked", "n_abstain", "delta_total", "delta_tue_2026_08_04",
           "delta_wed_2026_08_05", "delta_thu_2026_08_06", "delta_ex_wed",
           "n_days_harmed", "popB", "p_within_day", "q_benjamini_hochberg",
           "gates", "verdict"]
    print()
    print(" | ".join(f"{h:<22}" if h == "cell" else f"{h:>10}" for h in hdr))
    for r in rows:
        print(" | ".join((f"{r['cell']:<22}" if h == "cell" else f"{str(r.get(h)):>10}")
                         for h in hdr))
    print(f"\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
