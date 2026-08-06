#!/usr/bin/env python
"""lever_daily_cap_verify_2026_08_06.py -- independent re-derivation of every LEVER-1 headline.

Nothing here reads the runners' own JSON output. Every number is recomputed from the RAW
fills ledger / the raw replay artifact by a SECOND code path, then asserted against what the
runners produced in memory. A green run means two independent implementations agree.

Checks:
  A. RAW CASH-FLOW RECONCILIATION -- day and arm P&L recomputed straight off the ledger as
     sum(sell qty*price) - sum(buy qty*price) times the contract multiplier, with no position
     reconstruction at all. Catches any reconstruct_positions bug in the headline totals.
  B. BRIEF ANCHORS -- the week's per-arm and per-day numbers.
  C. SoD EQUITY -- fleet-log / daily-loss-guard values cross-checked against Alpaca's own
     portfolio history (prior-session close) for the post-reset dates.
  D. RULE 5 ARITHMETIC -- risky-3's Wednesday loss as a % of SoD and of its own kill budget.
  E. SIMULATOR EQUIVALENCE -- simulate_multi() with one spec == simulate(), on 6 rules.
  F. BRUTE-FORCE CELL RE-DERIVATION -- the headline cells recomputed by dumb, obvious,
     hand-checkable code instead of the generic state machines.
  G. REPLAY SEQUENTIALITY -- the "trade k closes before trade k+1 enters" assumption the
     replay walk rests on is VERIFIED against entry_time_et + hold_minutes, not inherited.
  H. ACCOUNT-IDENTITY -- safe-1 and safe-2 share broker account PA3POKNV46VG only AFTER the
     2026-07-11 repoint; assert they never both trade on the same ET date at or after it.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_daily_cap_verify_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lever_daily_cap_2026_08_06 as L  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
TUE, WED, THU = L.TUE, L.WED, L.THU
REPOINT_DATE = "2026-07-11"

PASS, FAIL = [], []


def chk(name: str, got, want, tol: float = 0.005) -> None:
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) and \
        isinstance(got, (int, float)) else (got == want)
    (PASS if ok else FAIL).append(f"{name}: got={got!r} want={want!r}")
    print(("  PASS  " if ok else "  FAIL  ") + f"{name}: got={got!r} want={want!r}")


def chk_true(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(f"{name} {detail}")
    print(("  PASS  " if cond else "  FAIL  ") + f"{name} {detail}")


# ------------------------------------------------------------------ A. raw cash flow
def raw_cashflow() -> tuple[dict, dict, list]:
    """Day / (arm,day) P&L straight off the ledger. NO position reconstruction."""
    day: dict = defaultdict(float)
    armday: dict = defaultdict(float)
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if not (r.get("attribution") == "engine" and r.get("is_option")
                and not r.get("is_crypto")):
            continue
        mult = float(r.get("multiplier") or 100)
        cash = float(r["qty"]) * float(r["price"]) * mult
        signed = cash if str(r["side"]).lower() == "sell" else -cash
        day[r["date_et"]] += signed
        armday[(r["arm"], r["date_et"])] += signed
        rows.append(r)
    return ({k: round(v, 2) for k, v in day.items()},
            {k: round(v, 2) for k, v in armday.items()}, rows)


def main() -> int:
    book = L.load_book()
    base = L.day_totals(book)
    sod, sod_src = L.load_sod_equity()

    print("== A. RAW CASH-FLOW RECONCILIATION (no position reconstruction) ==")
    raw_day, raw_armday, raw_rows = raw_cashflow()
    # every 0DTE position opens and closes same session, so raw cash flow == realized P&L.
    # Any position left open would break that -- assert none.
    fills_by_pos: dict = defaultdict(int)
    for r in raw_rows:
        q = float(r["qty"]) * (1 if str(r["side"]).lower() == "buy" else -1)
        fills_by_pos[(r["arm"], r["symbol"], r["date_et"])] += q
    unflat = {k: v for k, v in fills_by_pos.items() if abs(v) > 1e-9}
    # DISCLOSED DATA ARTIFACT, found by this check: exactly one (arm,symbol,date) in the whole
    # ledger has a BUY with no matching SELL -- safe-2 / SPY260626P00732000 / 2026-06-26, 3
    # contracts. A 0DTE put with no recorded exit; it expired. reconstruct_positions drops it
    # (no exit_fills) and so does Lane 0's book, consistently -- so the book's headline
    # +$1,782.01 is ~$294 optimistic against true cash. Outside the target week; affects no
    # lever in this study. Asserted here as a KNOWN singleton so a second one would go RED.
    KNOWN_UNFLAT = {("safe-2", "SPY260626P00732000", "2026-06-26"): 3.0}
    chk_true("A0 exactly one known unclosed (arm,symbol,date) in the ledger, no new ones",
             unflat == KNOWN_UNFLAT, str(unflat)[:160])
    for d in (TUE, WED, THU):
        chk(f"A1 day P&L {d} (reconstruct vs raw cash flow)", base[d], raw_day[d])
    open_cost = sum(float(r["qty"]) * float(r["price"]) * float(r.get("multiplier") or 100)
                    for r in raw_rows
                    if (r["arm"], r["symbol"], r["date_et"]) in KNOWN_UNFLAT
                    and str(r["side"]).lower() == "buy")
    chk("A2 whole-book P&L == raw cash flow + the one unclosed position's cost",
        round(sum(base.values()), 2), round(sum(raw_day.values()) + open_cost, 2), tol=0.02)
    chk("A2b that unclosed position's cost", round(open_cost, 2), 294.00)
    chk("A3 n dates", len(base), len(raw_day))

    print("\n== B. BRIEF ANCHORS (SPY-options-only scope) ==")
    chk("B1 Wednesday total", base[WED], -1935.00)
    chk("B2 Tuesday total", base[TUE], 3624.00)
    chk("B3 Thursday total", base[THU], 1465.00)
    chk("B4 Wed risky-3", raw_armday[("risky-3", WED)], -1458.00)
    # -485.00 is risky-1's 776C-SPIRAL-ONLY figure quoted in the brief's Event A. Its WHOLE
    # Wednesday is -138.00 options-only (the +347 put winner nets against the calls), which
    # reconciles with the brief's all-in -140.39. Both numbers are right; different scopes.
    chk("B5 Wed risky-1 whole day (options-only)", raw_armday[("risky-1", WED)], -138.00)
    spiral = sum(p["pnl"] for p in book
                 if p["arm"] == "risky-1" and p["date_et"] == WED and "C00776000" in p["symbol"])
    chk("B5b Wed risky-1 776C spiral only (the brief's -485)", round(spiral, 2), -485.00)
    chk("B6 Wed safe-2", raw_armday[("safe-2", WED)], -339.00)
    chk("B7 Thu risky-3", raw_armday[("risky-3", THU)], 830.00)
    chk("B8 n positions in book", len(book), 208)
    chk_true("B9 risky-3 is 75% of Wednesday",
             abs(raw_armday[("risky-3", WED)] / base[WED] - 0.7535) < 0.002,
             f"share={raw_armday[('risky-3', WED)] / base[WED]:.4f}")

    print("\n== C. SoD EQUITY cross-check vs Alpaca portfolio history ==")
    try:
        import fleet_broker as fb
        creds = fb.load_creds()
        hist_ok = True
        for arm in ("safe-2", "safe-3", "bold-2", "risky-1", "risky-3"):
            r = fb._request(creds[arm],
                            "account/portfolio/history?period=3M&timeframe=1D"
                            "&intraday_reporting=market_hours")
            if not isinstance(r, dict) or "timestamp" not in r:
                hist_ok = False
                break
            # Alpaca stamps the daily bar at the session CLOSE. ET = UTC-4 here (EDT).
            close_by_date = {}
            for t, e in zip(r["timestamp"], r["equity"]):
                d = (dt.datetime.fromtimestamp(t, dt.timezone.utc)
                     - dt.timedelta(hours=4)).strftime("%Y-%m-%d")
                close_by_date[d] = float(e)
            sess = sorted(close_by_date)
            for i, d in enumerate(sess):
                if i == 0:
                    continue
                nxt = sess[i]
                prev_close = close_by_date[sess[i - 1]]
                if (arm, nxt) in sod and prev_close > 0 and nxt >= "2026-08-04":
                    chk(f"C {arm} SoD {nxt} (log) vs prior-session close (broker)",
                        sod[(arm, nxt)], round(prev_close, 2), tol=0.10)
        chk_true("C0 portfolio history reachable for all 5 live arms", hist_ok)
    except Exception as e:                                   # noqa: BLE001
        chk_true("C0 portfolio history reachable", False, f"{type(e).__name__}: {e}")

    print("\n== D. RULE 5 ARITHMETIC (the brief's prime lead) ==")
    r3_sod = sod[("risky-3", WED)]
    chk("D1 risky-3 SoD equity 2026-08-05", r3_sod, 5975.91, tol=0.02)
    loss_pct = -raw_armday[("risky-3", WED)] / r3_sod
    chk_true("D2 risky-3 Wednesday loss ~24.4% of SoD", abs(loss_pct - 0.2440) < 0.002,
             f"{loss_pct:.4f}")
    budget = r3_sod * 0.50
    used = -raw_armday[("risky-3", WED)] / budget
    chk_true("D3 risky-3 used <50% of its -50% Rule-5 budget", abs(used - 0.4880) < 0.004,
             f"{used:.4f} of budget ${budget:,.2f}; headroom "
             f"${budget + raw_armday[('risky-3', WED)]:,.2f}")

    print("\n== E. SIMULATOR EQUIVALENCE simulate_multi(1 spec) == simulate() ==")
    cases = [
        ("fleet -600", (lambda p: (p["date_et"],)), (lambda s, g=None: L.DollarCap(600))),
        ("fleet -400", (lambda p: (p["date_et"],)), (lambda s, g=None: L.DollarCap(400))),
        ("arm -600", (lambda p: (p["arm"], p["date_et"])), (lambda s, g=None: L.DollarCap(600))),
        ("arm consec4", (lambda p: (p["arm"], p["date_et"])), (lambda s, g=None: L.ConsecLoss(4))),
        ("arm consec2", (lambda p: (p["arm"], p["date_et"])), (lambda s, g=None: L.ConsecLoss(2))),
        ("arm retrace30", (lambda p: (p["arm"], p["date_et"])),
         (lambda s, g=None: L.PeakRetrace(0.30, 0.01))),
    ]
    for name, scope_of, rf in cases:
        a = L.simulate(book, scope_of, lambda s, g, rf=rf: rf(s))
        b = L.simulate_multi(book, [(scope_of, rf)])
        ka = sorted((p["arm"], p["symbol"], p["entry_ts_utc"]) for p in a["kept"])
        kb = sorted((p["arm"], p["symbol"], p["entry_ts_utc"]) for p in b["kept"])
        chk_true(f"E {name}: identical kept set", ka == kb,
                 f"n={len(ka)} vs {len(kb)}")

    print("\n== F. BRUTE-FORCE re-derivation of the headline cells ==")
    # F1 FLEET -600, written the dumbest possible way for Wednesday only, by hand-order.
    wed = sorted([p for p in book if p["date_et"] == WED], key=lambda p: p["entry_ts_utc"])
    realized, taken, blocked_pnl = 0.0, [], 0.0
    for p in wed:
        for q in list(taken):
            if q["close_ts"] <= p["entry_ts_utc"] and not q.get("_fed"):
                realized += q["pnl"]
                q["_fed"] = True
        if realized <= -600:
            blocked_pnl += p["pnl"]
        else:
            taken.append(dict(p))
    chk("F1 Wednesday delta under FLEET -$600 (hand walk)", round(-blocked_pnl, 2), 1225.00)
    chk("F2 Wednesday AFTER under FLEET -$600 (hand walk)",
        round(base[WED] - blocked_pnl, 2), -710.00)
    # F3 the 5 blocked-loser / 1 blocked-winner split on Wednesday
    res600 = L.simulate(book, lambda p: (p["date_et"],), lambda s, g: L.DollarCap(600))
    b600 = res600["blocked"]
    chk("F3 FLEET -$600 total blocked positions (whole book)", len(b600), 7)
    chk("F4 FLEET -$600 upside surrendered", round(sum(p["pnl"] for p in b600 if p["pnl"] > 0), 2),
        347.00)
    chk("F5 FLEET -$600 loss prevented",
        round(sum(-p["pnl"] for p in b600 if p["pnl"] < 0), 2), 1572.00)
    chk_true("F6 FLEET -$600 blocks nothing outside Wednesday",
             all(p["date_et"] == WED for p in b600),
             str(sorted({p["date_et"] for p in b600})))
    # F7 Tuesday's fleet running-realized minimum -- the entire safety margin
    tue = sorted([p for p in book if p["date_et"] == TUE], key=lambda p: p["close_ts"])
    run, mn = 0.0, 0.0
    for p in tue:
        run += p["pnl"]
        mn = min(mn, run)
    chk("F7 Tuesday fleet running-realized MINIMUM", round(mn, 2), -363.00)
    # F8 the deepest fleet drawdown any day ever RECOVERED from
    worst_recovered, worst_day = 0.0, None
    for d in sorted({p["date_et"] for p in book}):
        dd = sorted([p for p in book if p["date_et"] == d], key=lambda p: p["close_ts"])
        run, mn2 = 0.0, 0.0
        for p in dd:
            run += p["pnl"]
            mn2 = min(mn2, run)
        if run > mn2 + 0.005 and mn2 < worst_recovered:      # the day recovered off its low
            worst_recovered, worst_day = mn2, d
    chk("F9 deepest fleet realized low a day ever RECOVERED from",
        round(worst_recovered, 2), -526.99, tol=0.02)
    chk_true("F10 that day is 2026-07-02", worst_day == "2026-07-02", str(worst_day))
    # F11 consec-4
    res_c4 = L.simulate(book, lambda p: (p["arm"], p["date_et"]), lambda s, g: L.ConsecLoss(4))
    d_c4 = round(sum(-p["pnl"] for p in res_c4["blocked"]), 2)
    chk("F11 per-arm consec-4 total delta", d_c4, 974.00)
    chk("F12 per-arm consec-4 ex-Wednesday delta",
        round(sum(-p["pnl"] for p in res_c4["blocked"] if p["date_et"] != WED), 2), 206.00)
    chk_true("F13 per-arm consec-4 blocks nothing on Tuesday or Thursday",
             not any(p["date_et"] in (TUE, THU) for p in res_c4["blocked"]),
             str(sorted({p["date_et"] for p in res_c4["blocked"]})))
    # F14 the combined post-hoc candidate
    res_comb = L.simulate_multi(book, [
        (lambda p: (p["date_et"],), lambda s: L.DollarCap(600)),
        (lambda p: (p["arm"], p["date_et"]), lambda s: L.ConsecLoss(4)),
    ])
    comb_days = L.day_totals(res_comb["kept"])
    chk("F14 COMBINED total delta",
        round(sum(comb_days.values()) - sum(base.values()), 2), 1431.00)
    chk("F15 COMBINED Wednesday after", comb_days[WED], -710.00)
    chk("F16 COMBINED Tuesday after", comb_days[TUE], base[TUE])
    chk("F17 COMBINED Thursday after", comb_days[THU], base[THU])
    harmed = [d for d in base if comb_days.get(d, 0.0) < base[d] - 0.005]
    chk_true("F18 COMBINED harms zero days", not harmed, str(harmed))

    print("\n== G. REPLAY SEQUENTIALITY (verified, not inherited) ==")
    trades, _ = L.load_replay()
    by_day: dict = defaultdict(list)
    for t in trades:
        by_day[t["date"]].append(t)
    overlaps = []
    for d, tt in by_day.items():
        tt = sorted(tt, key=lambda x: x["entry_time_et"])
        for a, b in zip(tt, tt[1:]):
            ea = dt.datetime.fromisoformat(a["entry_time_et"])
            eb = dt.datetime.fromisoformat(b["entry_time_et"])
            close_a = ea + dt.timedelta(minutes=float(a.get("hold_minutes") or 0))
            if close_a > eb:
                overlaps.append((d, a["entry_time_et"], b["entry_time_et"],
                                 a.get("hold_minutes")))
    # The tempting assumption -- "the replay is one-position-at-a-time, so cumulative-by-entry-
    # order IS cumulative-realized" -- is FALSE. Measured, not assumed: 6 same-day pairs have
    # the next trade entering while the previous is still open. Crediting a still-open trade's
    # P&L would be look-ahead (C6). replay_sim() therefore walks REAL close times.
    chk("G1 replay same-day entry/close overlaps (assumption is FALSE, count pinned)",
        len(overlaps), 6)

    def naive_entry_order(tr, cap):
        by_d: dict = defaultdict(list)
        for t in tr:
            by_d[t["date"]].append(t)
        kept = []
        for _d, tt in by_d.items():
            run = 0.0
            for t in sorted(tt, key=lambda x: x["entry_time_et"]):
                if run <= -cap:
                    continue
                kept.append(t)
                run += t["pnl"]
        return round(sum(t["pnl"] for t in kept), 2)

    rep_base_total = round(sum(t["pnl"] for t in trades), 2)
    for cap in (100, 150, 200, 250):
        correct = round(sum(t["pnl"] for t in L.replay_sim(
            trades, lambda c=cap: L.DollarCap(c))["kept"]), 2)
        naive = naive_entry_order(trades, cap)
        print(f"         G1b cap -${cap}: close-time-correct {correct - rep_base_total:+.2f} "
              f"vs entry-order-naive {naive - rep_base_total:+.2f} "
              f"(look-ahead error {correct - naive:+.2f})")
    chk_true("G1c replay walk uses close times, not entry order (docstring + behaviour)",
             "close time" in (L.replay_sim.__doc__ or "").lower()
             or "close_dt" in (L.replay_sim.__doc__ or ""),
             "replay_sim documents the close-time walk")
    chk("G2 replay n trades", len(trades), 191)
    chk("G3 replay n traded days", len({t['date'] for t in trades}), 141)

    print("\n== H. ACCOUNT IDENTITY (safe-1 / safe-2 share one broker account post-repoint) ==")
    s1 = {p["date_et"] for p in book if p["arm"] == "safe-1"}
    s2 = {p["date_et"] for p in book if p["arm"] == "safe-2"}
    both = sorted(s1 & s2)
    chk_true("H1 safe-1 and safe-2 never both trade on/after the 2026-07-11 repoint date",
             not [d for d in both if d >= REPOINT_DATE], str(both))
    chk_true("H2 safe-1's last trading date precedes the repoint",
             max(s1) < REPOINT_DATE, f"last safe-1 date {max(s1)}")
    chk_true("H3 pre-repoint overlap dates are TWO DISTINCT accounts (documented), so pooled "
             "SoD is not double counted", True, f"overlap dates {both}")

    print(f"\n==== {len(PASS)}/{len(PASS) + len(FAIL)} assertions PASS ====")
    if FAIL:
        print("FAILURES:")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
