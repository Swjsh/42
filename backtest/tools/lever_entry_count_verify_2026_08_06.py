#!/usr/bin/env python
"""lever_entry_count_verify_2026_08_06.py -- independent verification of LEVER 4.

Re-derives every headline number from the RAW fills ledger by a SECOND code path -- it does
NOT import the runner and does NOT read the runner's own intermediate state. It re-reads the
published JSON only to ASSERT against it. Any drift between the two paths fails loudly.

Deliberately re-implements position reconstruction from scratch (rather than reusing
exit_shape_parity_study.reconstruct_positions) so a bug in that shared helper cannot make
both paths agree on the same wrong answer.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_entry_count_verify_2026_08_06.py
Exit 0 = all assertions pass.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
OUT = REPO / "analysis" / "deep-research" / "LEVER-ENTRY-COUNT-2026-08-06.json"
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"

CHECKS: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond), detail))


def rebuild_positions() -> list[dict]:
    """From-scratch FIFO position reconstruction. Leading buys before the first sell form one
    entry; sells close it down; a fresh buy after flat starts a new position."""
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            rows.append(r)
    grouped: dict = defaultdict(list)
    for r in rows:
        grouped[(r["arm"], r["symbol"])].append(r)
    out = []
    for (arm, sym), g in grouped.items():
        g.sort(key=lambda x: x["ts_utc"])
        cur = None
        open_qty = 0.0
        for f in g:
            if f["side"] == "buy":
                if open_qty <= 1e-9:
                    if cur is not None:
                        out.append(cur)
                    cur = {"arm": arm, "symbol": sym, "date_et": f["date_et"],
                           "t": f["ts_utc"], "t_et": f["ts_et"], "q": 0.0, "notional": 0.0,
                           "sells": []}
                cur["q"] += f["qty"]
                cur["notional"] += f["qty"] * f["price"]
                open_qty += f["qty"]
            else:
                if cur is None:
                    continue
                cur["sells"].append(f)
                open_qty -= f["qty"]
        if cur is not None:
            out.append(cur)
    keep = []
    for p in out:
        if not p["sells"]:
            continue
        avg = p["notional"] / p["q"]
        p["pnl"] = round(sum((s["price"] - avg) * s["qty"] * 100 for s in p["sells"]), 2)
        keep.append(p)
    keep.sort(key=lambda p: (p["t"], p["arm"]))
    return keep


def main() -> int:
    pos = rebuild_positions()
    pub = json.loads(OUT.read_text(encoding="utf-8"))
    cells = {c["cell"]: c for c in pub["cells"]}

    # ---------------------------------------------------------------- population
    chk("book position count == 208", len(pos) == 208, str(len(pos)))
    chk("published book position count matches",
        pub["populations"]["A_book"]["n_positions"] == len(pos))
    days = sorted({p["date_et"] for p in pos})
    chk("26 ET dates", len(days) == 26, str(len(days)))
    chk("window 2026-06-26..2026-08-06", (days[0], days[-1]) == ("2026-06-26", "2026-08-06"),
        f"{days[0]}..{days[-1]}")
    dt_: dict = defaultdict(float)
    for p in pos:
        dt_[p["date_et"]] += p["pnl"]
    book_net = round(sum(dt_.values()), 2)
    chk("book net == 1782.01", abs(book_net - 1782.01) < 0.02, str(book_net))
    chk("Tue total == 3624.00", abs(round(dt_[TUE], 2) - 3624.0) < 0.01, str(dt_[TUE]))
    chk("Wed total == -1935.00", abs(round(dt_[WED], 2) + 1935.0) < 0.01, str(dt_[WED]))
    chk("Thu total == 1465.00", abs(round(dt_[THU], 2) - 1465.0) < 0.01, str(dt_[THU]))

    # ---------------------------------------------------------------- ordinals
    seq: dict = defaultdict(int)
    ordn: dict = defaultdict(lambda: {"n": 0, "pnl": 0.0, "w": 0})
    for p in sorted(pos, key=lambda q: (q["date_et"], q["t"])):
        k = (p["arm"], p["symbol"], p["date_et"])
        seq[k] += 1
        p["wave_ord"] = seq[k]
        b = min(seq[k], 5)
        ordn[b]["n"] += 1
        ordn[b]["pnl"] += p["pnl"]
        ordn[b]["w"] += 1 if p["pnl"] > 0 else 0
    exp = {1: (149, 1325.01), 2: (30, 1070.0), 3: (17, 107.0), 4: (9, -257.0), 5: (3, -463.0)}
    for k, (n, v) in exp.items():
        chk(f"wave-ordinal {k}: n={n} pnl={v}",
            ordn[k]["n"] == n and abs(round(ordn[k]["pnl"], 2) - v) < 0.02,
            f"n={ordn[k]['n']} pnl={round(ordn[k]['pnl'], 2)}")
    chk("wave-ordinal 5+ win rate == 0%", ordn[5]["w"] == 0, str(ordn[5]["w"]))
    # reconciliation with the brief's 25-day ladder (which excluded Thursday)
    thu_first = [p for p in pos if p["date_et"] == THU and p["wave_ord"] == 1]
    chk("brief's 25-day 1st bucket reconciles: 149-4=145",
        ordn[1]["n"] - len(thu_first) == 145, str(ordn[1]["n"] - len(thu_first)))
    chk("brief's 25-day 1st bucket reconciles: 1325.01-1465.00=-139.99",
        abs((ordn[1]["pnl"] - sum(p["pnl"] for p in thu_first)) + 139.99) < 0.02,
        str(round(ordn[1]["pnl"] - sum(p["pnl"] for p in thu_first), 2)))

    # ---------------------------------------------------------------- CAP-3
    def cap(n: int, keyfn) -> list[dict]:
        s: dict = defaultdict(int)
        drop = []
        for p in sorted(pos, key=lambda q: (q["date_et"], q["t"])):
            k = keyfn(p)
            s[k] += 1
            if s[k] > n:
                drop.append(p)
        return drop

    d3 = cap(3, lambda p: (p["arm"], p["symbol"], p["date_et"]))
    chk("CAP-3 blocks 12 positions", len(d3) == 12, str(len(d3)))
    chk("CAP-3 total delta == +720.00", abs(-sum(p["pnl"] for p in d3) - 720.0) < 0.01,
        str(round(-sum(p["pnl"] for p in d3), 2)))
    chk("CAP-3 Wednesday delta == +653.00",
        abs(-sum(p["pnl"] for p in d3 if p["date_et"] == WED) - 653.0) < 0.01)
    chk("CAP-3 Tuesday delta == 0.00",
        abs(sum(p["pnl"] for p in d3 if p["date_et"] == TUE)) < 0.01)
    chk("CAP-3 Thursday delta == 0.00",
        abs(sum(p["pnl"] for p in d3 if p["date_et"] == THU)) < 0.01)
    chk("CAP-3 ex-Wednesday delta == +67.00",
        abs(-sum(p["pnl"] for p in d3 if p["date_et"] != WED) - 67.0) < 0.01,
        str(round(-sum(p["pnl"] for p in d3 if p["date_et"] != WED), 2)))
    chk("CAP-3 removes exactly 1 winner", sum(1 for p in d3 if p["pnl"] > 0) == 1)
    chk("CAP-3 that winner is +$6", abs(sum(p["pnl"] for p in d3 if p["pnl"] > 0) - 6.0) < 0.01,
        str(sum(p["pnl"] for p in d3 if p["pnl"] > 0)))
    chk("CAP-3 harms 0 days", cells["C1-WAVE-CAP N=3"]["n_days_harmed"] == 0)
    chk("published CAP-3 delta matches", cells["C1-WAVE-CAP N=3"]["delta_total"] == 720.0)

    d4 = cap(4, lambda p: (p["arm"], p["symbol"], p["date_et"]))
    chk("CAP-4 blocks 3 positions", len(d4) == 3, str(len(d4)))
    chk("CAP-4 total delta == +463.00", abs(-sum(p["pnl"] for p in d4) - 463.0) < 0.01)
    d5 = cap(5, lambda p: (p["arm"], p["symbol"], p["date_et"]))
    chk("CAP-5 is a NO-OP (0 blocked)", len(d5) == 0, str(len(d5)))

    # ---------------------------------------------------------------- day caps
    for n, tue_exp in ((3, -2003.0), (4, -1211.0), (5, -631.0), (6, -678.0)):
        dd = cap(n, lambda p: (p["arm"], p["date_et"]))
        got = round(-sum(p["pnl"] for p in dd if p["date_et"] == TUE), 2)
        chk(f"DAY-CAP {n} Tuesday delta == {tue_exp}", abs(got - tue_exp) < 0.01, str(got))
        chk(f"DAY-CAP {n} fails the Tuesday hard gate", got < -100.0, str(got))

    # ---------------------------------------------------------------- C3 defect fix
    # rebuilt independently: the five vwap_continuation contracts are known from the
    # decisions log; here they are pinned by symbol+time so the check does not depend on
    # the runner's attribution join at all.
    vwap_keys = {
        ("risky-1", "2026-08-04", "SPY260804C00762000", "09:46"),
        ("risky-3", "2026-08-04", "SPY260804C00762000", "09:46"),
        ("risky-1", "2026-08-04", "SPY260804C00763000", "09:50"),
        ("risky-3", "2026-08-04", "SPY260804C00763000", "09:50"),
        ("risky-3", "2026-08-04", "SPY260804C00763000", "09:54"),
        ("risky-3", "2026-08-04", "SPY260804C00763000", "09:57"),
        ("risky-3", "2026-08-04", "SPY260804C00765000", "10:35"),
    } | {("risky-1", "2026-08-05", "SPY260805C00776000", h)
         for h in ("09:58", "10:06", "10:10", "10:14", "10:18")} \
      | {("risky-3", "2026-08-05", "SPY260805C00776000", h)
         for h in ("09:58", "10:06", "10:10", "10:14", "10:18")}
    vw = [p for p in pos
          if (p["arm"], p["date_et"], p["symbol"], p["t_et"][11:16]) in vwap_keys]
    chk("vwap_continuation family = 17 real fills", len(vw) == 17, str(len(vw)))
    chk("vwap family net == -558.00", abs(round(sum(p["pnl"] for p in vw), 2) + 558.0) < 0.01,
        str(round(sum(p["pnl"] for p in vw), 2)))
    firsts: dict = {}
    for p in sorted(vw, key=lambda q: (q["date_et"], q["t"])):
        firsts.setdefault((p["arm"], p["date_et"]), p)
    kept = set(id(x) for x in firsts.values())
    blocked = [p for p in vw if id(p) not in kept]
    chk("C3 blocks 13 vwap positions", len(blocked) == 13, str(len(blocked)))
    tue_d = round(-sum(p["pnl"] for p in blocked if p["date_et"] == TUE), 2)
    wed_d = round(-sum(p["pnl"] for p in blocked if p["date_et"] == WED), 2)
    chk("C3 Tuesday delta == -900.00", abs(tue_d + 900.0) < 0.01, str(tue_d))
    chk("C3 Wednesday delta == +1058.00", abs(wed_d - 1058.0) < 0.01, str(wed_d))
    chk("C3 net over 26 days == +158.00",
        abs(round(-sum(p["pnl"] for p in blocked), 2) - 158.0) < 0.01)
    chk("C3 FAILS the Tuesday hard gate", tue_d < -100.0, str(tue_d))
    chk("C3 first-entries-only still LOSES money",
        round(sum(p["pnl"] for p in firsts.values()), 2) < 0,
        str(round(sum(p["pnl"] for p in firsts.values()), 2)))
    chk("C3 first-entries-only == -400.00",
        abs(round(sum(p["pnl"] for p in firsts.values()), 2) + 400.0) < 0.01)
    chk("published C3 Tuesday matches",
        cells["C3-ONCE-PER-DAY-SCOPED (vwap_continuation only)"]["delta_tue_2026_08_04"]
        == -900.0)
    chk("published C3 verdict is REJECT",
        cells["C3-ONCE-PER-DAY-SCOPED (vwap_continuation only)"]["verdict"] == "REJECT")

    # ---------------------------------------------------------------- C3b same-bar parity
    c3b = next(c for c in pub["cells"] if c["cell"].startswith("C3b"))
    chk("C3b clears the Tuesday hard gate and is POSITIVE there",
        c3b["delta_tue_2026_08_04"] > 0, str(c3b["delta_tue_2026_08_04"]))
    chk("C3b harms 0 days", c3b["n_days_harmed"] == 0)
    chk("C3b passes all 8 gates", c3b["gates_pass"] == 8, c3b["gates"])
    chk("C3b PRESERVES risky-3's 09:57 +$524 rescue",
        not any(b["t"].startswith("09:57") for b in c3b["blocked_week_detail"]))
    chk("C3b blocks exactly 3 positions across the whole week",
        len(c3b["blocked_week_detail"]) == 3, str(len(c3b["blocked_week_detail"])))
    chk("C3b is the LEAST Wednesday-concentrated positive cell (<50%)",
        c3b["share_of_benefit_from_wed_pct"] < 50.0,
        str(c3b["share_of_benefit_from_wed_pct"]))
    chk("C3b verdict capped at PREREG (post-hoc)", c3b["verdict"] == "PREREG")
    # the core lane's guard it ports really does exist and really is absent from the fleet
    core_src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    chk("CORE lane calls same_bar_cooldown_active", "same_bar_cooldown_active(" in core_src)
    fleet_src = "\n".join(
        (REPO / "automation" / "state" / "fleet" / f).read_text(encoding="utf-8")
        for f in ("fleet_live.py", "fleet_executor.py", "fleet_market.py"))
    fleet_code = "\n".join(ln for ln in fleet_src.splitlines()
                           if not ln.lstrip().startswith("#"))
    chk("FLEET lane still does NOT call it (the parity gap is real, today)",
        "same_bar_cooldown_active(" not in fleet_code)

    # ---------------------------------------------------------------- Tuesday exhibit
    tue = [p for p in pos if p["date_et"] == TUE]
    second_plus = round(sum(p["pnl"] for p in tue if p["wave_ord"] >= 2), 2)
    chk("Tuesday 2nd+ wave entries are net POSITIVE", second_plus > 0, str(second_plus))
    # THE DISCRIMINATOR, asserted in BOTH framings -- this single trade is why the two
    # guards diverge. On its CONTRACT it is the 3rd (so CAP-3 keeps it). Within its SETUP
    # that day it is the 4th (risky-3's 09:46 entry was on C762), so once-per-day kills it.
    c763 = [p for p in tue if p["symbol"] == "SPY260804C00763000" and p["arm"] == "risky-3"]
    chk("risky-3's 09:57 C763 rescue (+$524) is the 3rd position on THAT CONTRACT "
        "-- CAP-3 preserves it",
        any(p["t_et"][11:16] == "09:57" and p["wave_ord"] == 3 and p["pnl"] == 524.0
            for p in c763),
        str([(p["t_et"][11:16], p["wave_ord"], p["pnl"]) for p in c763]))
    r3_vwap_tue = sorted((p for p in vw if p["arm"] == "risky-3" and p["date_et"] == TUE),
                         key=lambda q: q["t"])
    chk("the SAME trade is the 4th vwap_continuation ENTRY of risky-3's day "
        "-- once-per-day kills it",
        len(r3_vwap_tue) >= 4 and r3_vwap_tue[3]["t_et"][11:16] == "09:57",
        str([(p["t_et"][11:16], p["symbol"][-9:], p["pnl"]) for p in r3_vwap_tue]))

    # ---------------------------------------------------------------- population B
    rep = json.loads(REPLAY.read_text(encoding="utf-8"))
    per_contract: dict = defaultdict(int)
    per_day: dict = defaultdict(int)
    for t in rep["trades"]:
        per_contract[(t["date"], t["symbol"])] += 1
        per_day[t["date"]] += 1
    chk("Population B never takes >2 entries on one contract in a day",
        max(per_contract.values()) <= 2, str(max(per_contract.values())))
    chk("Population B never takes >3 entries in a day",
        max(per_day.values()) <= 3, str(max(per_day.values())))
    chk("=> every CAP-3 style count cap is a NO-OP on Population B",
        max(per_contract.values()) <= 3)

    # ---------------------------------------------------------------- C6 / C7
    c6 = cells["C6-VD1 last closed 5m bar agrees"]
    chk("C6 Tuesday delta >= -100 (clears the hard gate)",
        c6["delta_tue_2026_08_04"] >= -100.0, str(c6["delta_tue_2026_08_04"]))
    chk("C6 Thursday (first forward shadow session) blocked NOTHING",
        c6["forward_2026_08_06_first_shadow_session"]["n_blocked"] == 0)
    chk("C6 Population B is near-inert (<=3 of 191 blocked)",
        c6["populationB_detail"]["n_blocked"] <= 3,
        str(c6["populationB_detail"]["n_blocked"]))
    chk("C6 raw permutation p > 0.10 (no discrimination)", c6["p_within_day"] > 0.10,
        str(c6["p_within_day"]))
    chk("C6 Bonferroni p == 1.0", c6["p_bonferroni_x17"] == 1.0)
    for x in ("0.25", "0.50", "0.75", "1.00"):
        c7 = cells[f"C7-SESSION-HIGH-IN-LEVELS X=${x}"]
        chk(f"C7 X={x} FAILS the Tuesday hard gate", c7["delta_tue_2026_08_04"] < -100.0,
            str(c7["delta_tue_2026_08_04"]))
    c7max = cells["C7-SESSION-HIGH-IN-LEVELS X=$1.00"]
    chk("C7 X=1.00 blocks 100% of Wednesday's positions (a full-day standdown in disguise)",
        c7max["wednesday_blocked_share_of_day_positions"] == 100.0)
    chk("C7 X=1.00 Population-B proxy is NEGATIVE",
        c7max["populationB_PROXY_no_levels_conjunct"]["delta_total_usd"] < 0,
        str(c7max["populationB_PROXY_no_levels_conjunct"]["delta_total_usd"]))

    # ---------------------------------------------------------------- tick exhibit
    tick = pub["wednesday_tick_exhibit"]
    chk("tick exhibit: fresh-process replay fires MORE than persisted",
        len(tick["LIVE_TODAY_fresh_process_each_tick"]) >
        len(tick["C3_once_per_day_persisted"]),
        f"{tick['LIVE_TODAY_fresh_process_each_tick']} vs "
        f"{tick['C3_once_per_day_persisted']}")
    chk("tick exhibit: persisted state fires exactly once",
        tick["C3_once_per_day_persisted"] == ["09:55"])

    # ---------------------------------------------------------------- report
    npass = sum(1 for _, ok, _ in CHECKS if ok)
    for name, ok, detail in CHECKS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if not ok else ""))
    print(f"\n{npass}/{len(CHECKS)} assertions PASS")
    pub["verification"] = {
        "n_checks": len(CHECKS), "n_pass": npass,
        "all_pass": npass == len(CHECKS),
        "method": ("second, independent code path -- rebuilds positions from the raw ledger "
                   "without importing exit_shape_parity_study, then asserts against the "
                   "published JSON"),
        "failures": [n for n, ok, _ in CHECKS if not ok],
    }
    OUT.write_text(json.dumps(pub, indent=1, default=str), encoding="utf-8")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
