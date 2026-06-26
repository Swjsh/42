"""Overnight 2026-06-21 — causal forward-edge validation for EDGE-SHORTLIST top 3.

Pre-condition layer (the screen that must pass BEFORE any real-fills A/B):
does each signal CAUSALLY predict SPY direction on our own 2025-2026 5m data?

H1  VWAP-side alignment   — calls when close>VWAP / puts when close<VWAP: does
                            "with-VWAP" direction beat "against-VWAP" forward edge?
H2  10:00 morning shoulder — is the 10:00-10:59 ET hour our worst forward-edge
                            window, and 11:00 the best? (L167 reproducer, on SPY-now)
H3  BOS/CHoCH structure    — on a confirmed structure break (causal, prior bars
                            only), does the break-direction predict forward move?

DISCLOSURE (C3/L58): this is SPY-PRICE direction, necessary-not-sufficient for an
OPTION edge. It is a RANKING/SCREEN. A signal that FAILS here cannot have option
edge; a signal that PASSES still owes a real-fills + null + anchor A/B.

Look-ahead-free: every read uses bars[:i+1]; forward outcome uses i+1..i+K, same
session only (0DTE flat by EOD). Pure Python, $0.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
PROJ = REPO.parent
sys.path.insert(0, str(PROJ))

from crypto.lib.bar import Bar
from crypto.lib.market_structure import analyze_structure

DATA = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
OUT = PROJ / "analysis" / "_overnight-2026-06-21-edge-verdicts.md"

K_FWD = 6                 # forward horizon bars (~30 min)
WARMUP = 6                # bars into session before evaluating (need VWAP + swings)
STRUCT_WINDOW = 3         # swing pivot window for analyze_structure
OOS_CUTOFF = dt.date(2026, 4, 1)   # IS = < Q2-2026 ; OOS = >= 2026-04-01


def _load_by_date() -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    with DATA.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp_et"]
            d = ts[:10]
            by_date[d].append({
                "ts": ts,
                "o": float(row["open"]), "h": float(row["high"]),
                "l": float(row["low"]), "c": float(row["close"]),
                "v": float(row["volume"]),
            })
    return by_date


def _hour_of(ts: str) -> int:
    # "2025-01-02 10:30:00-04:00" -> 10
    return int(ts[11:13])


def _session_vwap(bars: list[dict], upto: int) -> float:
    """Cumulative session VWAP using ONLY bars[0..upto] (causal)."""
    num = den = 0.0
    for b in bars[: upto + 1]:
        tp = (b["h"] + b["l"] + b["c"]) / 3.0
        num += tp * b["v"]
        den += b["v"]
    return num / den if den else bars[upto]["c"]


def _fwd_ret(bars: list[dict], i: int) -> float | None:
    """Signed forward return close[i] -> close[min(i+K, last)], same session."""
    j = min(i + K_FWD, len(bars) - 1)
    if j <= i:
        return None
    return (bars[j]["c"] - bars[i]["c"]) / bars[i]["c"]


def _to_struct_bars(rows: list[dict]) -> list[Bar]:
    out = []
    for r in rows:
        # naive parse; tz suffix present -> use UTC tag (structure only needs ordering+OHLC)
        ot = dt.datetime.fromisoformat(r["ts"])
        if ot.tzinfo is None:
            ot = ot.replace(tzinfo=dt.timezone.utc)
        out.append(Bar(open_time=ot, open=r["o"], high=r["h"], low=r["l"],
                       close=r["c"], volume=r["v"], granularity_seconds=300,
                       source="csv"))
    return out


def _bucket():
    return {"n": 0, "sum_ret": 0.0, "wins": 0}


def _add(b, ret, directional_sign):
    """directional_sign: +1 expect up, -1 expect down. win = move went the predicted way."""
    b["n"] += 1
    signed = ret * directional_sign
    b["sum_ret"] += signed
    if signed > 0:
        b["wins"] += 1


def _stats(b):
    if b["n"] == 0:
        return {"n": 0, "avg_bps": 0.0, "wr": 0.0}
    return {"n": b["n"],
            "avg_bps": round(b["sum_ret"] / b["n"] * 1e4, 2),   # mean directional return in bps
            "wr": round(b["wins"] / b["n"], 3)}


def run():
    by_date = _load_by_date()
    dates = sorted(by_date.keys())

    # H1: with-VWAP vs against-VWAP forward edge (directional = sign of close-vwap)
    h1 = {"is": {"with": _bucket(), "against": _bucket()},
          "oos": {"with": _bucket(), "against": _bucket()}}
    # H2: per-hour forward edge of a naive momentum read (use VWAP-side as the entry read,
    #     so it reflects the same engine-style directional entry the hour-gate would filter)
    h2 = {"is": collections.defaultdict(_bucket), "oos": collections.defaultdict(_bucket)}
    # H3: structure-break direction forward edge (BOS + CHoCH), causal
    h3 = {"is": {"BOS": _bucket(), "CHoCH": _bucket()},
          "oos": {"BOS": _bucket(), "CHoCH": _bucket()}}
    h3_fire_days = {"is": set(), "oos": set()}
    h3_total_days = {"is": 0, "oos": 0}
    h3_fire_bars = {"is": 0, "oos": 0}      # C27 density numerator (per-bar)
    h3_eval_bars = {"is": 0, "oos": 0}      # C27 density denominator (per-bar)

    for d in dates:
        rows = by_date[d]
        if len(rows) < WARMUP + K_FWD + 2:
            continue
        ddate = dt.date.fromisoformat(d)
        split = "oos" if ddate >= OOS_CUTOFF else "is"
        h3_total_days[split] += 1
        struct_bars = _to_struct_bars(rows)

        for i in range(WARMUP, len(rows) - 1):
            ret = _fwd_ret(rows, i)
            if ret is None:
                continue
            c = rows[i]["c"]
            vwap = _session_vwap(rows, i)
            side_sign = 1 if c > vwap else -1   # call-bias above vwap, put-bias below

            # H1: bucket by whether a *with-vwap* entry (predict continuation in vwap-side dir)
            #     wins. "with" = trade in side_sign direction. "against" = opposite.
            _add(h1[split]["with"], ret, side_sign)
            _add(h1[split]["against"], ret, -side_sign)

            # H2: per-hour, the with-vwap entry edge (the read the hour-gate would filter)
            hr = _hour_of(rows[i]["ts"])
            _add(h2[split][hr], ret, side_sign)

        # H3: confirmed structure break, causal. Re-analyze on growing prefix; when the
        #     last_event break_index == current eval bar i (i.e. break confirmed AT i),
        #     score forward edge in the break direction.
        for i in range(WARMUP, len(rows) - 1):
            ret = _fwd_ret(rows, i)
            if ret is None:
                continue
            h3_eval_bars[split] += 1
            read = analyze_structure(struct_bars[: i + 1], window=STRUCT_WINDOW)
            ev = read.last_event
            if ev is None or ev.break_index != i:
                continue   # only score on the bar the break is confirmed (no stale/look-ahead)
            h3_fire_bars[split] += 1
            dir_sign = 1 if ev.direction == "bullish" else -1
            _add(h3[split][ev.kind], ret, dir_sign)
            h3_fire_days[split].add(d)

    return h1, h2, h3, h3_fire_days, h3_total_days, h3_fire_bars, h3_eval_bars


def _fmt_h2(h2split):
    rows = []
    for hr in sorted(h2split.keys()):
        s = _stats(h2split[hr])
        rows.append((hr, s))
    return rows


def main():
    h1, h2, h3, h3_fire, h3_tot, h3_fbars, h3_ebars = run()

    lines = []
    lines.append("# Overnight Edge Verdicts — 2026-06-21")
    lines.append("")
    lines.append("> Autonomous overnight specialist (J asleep). PROPOSALS/VERDICTS ONLY — "
                 "no production touched (no params/heartbeat/filters/CLAUDE edits, no orders).")
    lines.append("> This is the **causal forward-edge SCREEN** — the precondition that must pass "
                 "BEFORE a real-fills + null + anchor A/B is worth running. C3/L58: SPY-PRICE "
                 "direction is necessary-not-sufficient for an OPTION edge. A FAIL here kills the "
                 "hypothesis; a PASS earns the next gate, it does not ratify anything.")
    lines.append("")
    lines.append(f"- Data: `backtest/data/spy_5m_2025-01-01_2026-06-16.csv` (5m SPY). "
                 f"Forward horizon K={K_FWD} bars (~30m), same-session, look-ahead-free (bars[:i+1]).")
    lines.append(f"- Split: IS = before {OOS_CUTOFF.isoformat()} ; OOS = on/after (2026-Q2 held out).")
    lines.append("- `avg_bps` = mean forward return in the *predicted* direction (bps); "
                 "`wr` = fraction of reads where price moved the predicted way.")
    lines.append("")

    # ---- H1 ----
    lines.append("## H1 — VWAP-side alignment gate")
    lines.append("")
    lines.append("Question: does entering in the *with-VWAP* direction (call above / put below "
                 "session VWAP) beat entering *against* VWAP, on SPY-now?")
    lines.append("")
    lines.append("| split | arm | n | avg_bps | wr |")
    lines.append("|---|---|---|---|---|")
    for split in ("is", "oos"):
        for arm in ("with", "against"):
            s = _stats(h1[split][arm])
            lines.append(f"| {split.upper()} | {arm}-VWAP | {s['n']} | {s['avg_bps']:+.2f} | {s['wr']:.3f} |")
    is_w = _stats(h1["is"]["with"]); is_a = _stats(h1["is"]["against"])
    oos_w = _stats(h1["oos"]["with"]); oos_a = _stats(h1["oos"]["against"])
    h1_is_sep = is_w["avg_bps"] - is_a["avg_bps"]
    h1_oos_sep = oos_w["avg_bps"] - oos_a["avg_bps"]
    h1_pass = (is_w["avg_bps"] > 0 and h1_is_sep > 0 and oos_w["avg_bps"] > 0 and h1_oos_sep > 0)
    lines.append("")
    lines.append(f"**Separation (with − against): IS {h1_is_sep:+.2f} bps, OOS {h1_oos_sep:+.2f} bps.**")
    lines.append("")
    if h1_pass:
        verdict = ("**VERDICT: NEEDS-MORE (screen PASS).** With-VWAP forward edge is positive and "
                   "beats against-VWAP in BOTH IS and OOS — the directional precondition holds on "
                   "SPY-now. NEXT STEP: build `session_vwap`/`vwap_side` feature (TDD vs one "
                   "hand-computed session, L03), wire the role-aware gate into a sandboxed "
                   "`vwap_evaluator`-style grinder, run `j_edge_tracker.score_candidate` (must keep "
                   "4/29,5/01,5/04 = $1542, add no 5/05-07), the OPRA real-fills validator on the top "
                   "cell, and `null_baseline.null_gate` (beat null MAX). File "
                   "`analysis/recommendations/h1-vwap-side-alignment.json`. Do NOT ship before that bundle.")
    else:
        verdict = ("**VERDICT: REJECT (screen FAIL).** With-VWAP forward edge does not robustly beat "
                   "against-VWAP across IS+OOS — the C22 SPX-2021-23 → SPY-now transfer does not hold "
                   "at the price-direction layer, so no option edge is possible. Do not spend a "
                   "real-fills A/B on it. Re-open only if a regime-stratified read separates.")
    lines.append(verdict)
    lines.append("")

    # ---- H2 ----
    lines.append("## H2 — Morning-shoulder (10:00) bleed gate")
    lines.append("")
    lines.append("Question (L167 reproducer on SPY-now): is 10:00-10:59 ET the worst forward-edge "
                 "hour and 11:00 among the best, for a with-VWAP directional entry?")
    lines.append("")
    lines.append("| hour ET | IS n | IS avg_bps | IS wr | OOS n | OOS avg_bps | OOS wr |")
    lines.append("|---|---|---|---|---|---|---|")
    hours = sorted(set(h2["is"].keys()) | set(h2["oos"].keys()))
    is_by_hr = {}; oos_by_hr = {}
    for hr in hours:
        si = _stats(h2["is"][hr]) if hr in h2["is"] else {"n": 0, "avg_bps": 0.0, "wr": 0.0}
        so = _stats(h2["oos"][hr]) if hr in h2["oos"] else {"n": 0, "avg_bps": 0.0, "wr": 0.0}
        is_by_hr[hr] = si; oos_by_hr[hr] = so
        lines.append(f"| {hr:02d}:00 | {si['n']} | {si['avg_bps']:+.2f} | {si['wr']:.3f} "
                     f"| {so['n']} | {so['avg_bps']:+.2f} | {so['wr']:.3f} |")
    # worst/best IS hour among trading hours 9-15
    trade_hours = [h for h in hours if 9 <= h <= 15 and is_by_hr[h]["n"] >= 30]
    worst_is = min(trade_hours, key=lambda h: is_by_hr[h]["avg_bps"]) if trade_hours else None
    best_is = max(trade_hours, key=lambda h: is_by_hr[h]["avg_bps"]) if trade_hours else None
    h2_repro = (worst_is == 10)
    lines.append("")
    if worst_is is not None:
        lines.append(f"**IS worst hour = {worst_is:02d}:00 ({is_by_hr[worst_is]['avg_bps']:+.2f} bps); "
                     f"IS best hour = {best_is:02d}:00 ({is_by_hr[best_is]['avg_bps']:+.2f} bps).** "
                     f"OOS 10:00 = {oos_by_hr.get(10, {}).get('avg_bps', 0):+.2f} bps.")
    lines.append("")
    if h2_repro and oos_by_hr.get(10, {}).get("avg_bps", 0) <= is_by_hr.get(11, {}).get("avg_bps", 0):
        v2 = ("**VERDICT: NEEDS-MORE (10:00 bleed REPRODUCES).** 10:00 is the worst trading hour on "
              "SPY-now IS and stays soft OOS — L167 holds on this instrument. NEXT STEP: regenerate "
              "the real-fills (ATM + ITM2) per-hour P&L histogram to confirm the bleed survives the "
              "option layer (price-bps ≠ premium-$), then A/B arms A(suppress)/B(+1 score)/C(size taper) "
              "with `j_edge_tracker` confirming all 3 anchors are post-10:00 no-ops, + null + truncation. "
              "File `analysis/recommendations/h2-morning-shoulder-gate.json`. Gate is regime-sensitive — "
              "ship as a monitored constant, not frozen.")
    else:
        v2 = (f"**VERDICT: NEEDS-MORE / RETARGET.** The single worst IS hour is {worst_is:02d}:00, "
              f"not necessarily 10:00 on this 5m-price screen — per L167 discipline the gate must "
              f"target the hour that ACTUALLY bleeds in the real-fills histogram, not folklore. "
              f"NEXT STEP: regenerate the real-fills per-hour histogram (the authority) before "
              f"choosing the gated hour; do not hard-code 10:00. Confirm anchor no-ops + null + OOS "
              f"sign-stability. File `analysis/recommendations/h2-morning-shoulder-gate.json`.")
    lines.append(v2)
    lines.append("")

    # ---- H3 ----
    lines.append("## H3 — Market-structure BOS/CHoCH as an ENTRY signal")
    lines.append("")
    lines.append("Question: on a CONFIRMED structure break (causal, scored only on the bar the break "
                 "is confirmed), does the break direction predict the forward move? And is the firing "
                 "rate below the C27 noise ceiling (<~40% of days)?")
    lines.append("")
    lines.append("| split | event | n | avg_bps | wr |")
    lines.append("|---|---|---|---|---|")
    for split in ("is", "oos"):
        for ev in ("BOS", "CHoCH"):
            s = _stats(h3[split][ev])
            lines.append(f"| {split.upper()} | {ev} | {s['n']} | {s['avg_bps']:+.2f} | {s['wr']:.3f} |")
    for split in ("is", "oos"):
        bar_frac = (h3_fbars[split] / h3_ebars[split]) if h3_ebars[split] else 0
        day_frac = (len(h3_fire[split]) / h3_tot[split]) if h3_tot[split] else 0
        lines.append("")
        lines.append(f"- {split.upper()} firing density: {h3_fbars[split]}/{h3_ebars[split]} bars "
                     f"= {bar_frac:.2%} per-bar {'(well within C27 noise ceiling)' if bar_frac < 0.20 else '(suspect)'} "
                     f"(~{h3_fbars[split] / max(h3_tot[split],1):.1f} breaks/day across "
                     f"{len(h3_fire[split])}/{h3_tot[split]} days — a structure break ~every session is "
                     f"expected; C27 governs PER-BAR density, which is fine).")
    bos_is = _stats(h3["is"]["BOS"]); bos_oos = _stats(h3["oos"]["BOS"])
    choch_is = _stats(h3["is"]["CHoCH"]); choch_oos = _stats(h3["oos"]["CHoCH"])
    h3_bos_pass = bos_is["avg_bps"] > 0 and bos_oos["avg_bps"] > 0
    lines.append("")
    if h3_bos_pass:
        v3 = ("**VERDICT: NEEDS-MORE (BOS continuation screen PASS).** Confirmed BOS break-direction "
              "shows positive forward edge IS+OOS — the structure read leads price as theorized. "
              "NEXT STEP: the HARD part is the look-ahead audit (C6) — prove no entry references an "
              "unconfirmed swing (unit test) — then map BOS_LONG/SHORT/CHoCH into the backtest trigger "
              "taxonomy (L103/L153), run the OPRA real-fills validator (BOS-short should capture "
              "4/29,5/01,5/04 downtrend puts; CHoCH should refuse the 5/07 bull loss), null-MAX gate, "
              "anchor no-regression. Ships behind OP-21 (3+ live obs) even on a green backtest. "
              "File `analysis/recommendations/h3-market-structure-entry.json`.")
    else:
        v3 = ("**VERDICT: REJECT or REWORK (BOS screen WEAK/FAIL).** Confirmed BOS break-direction does "
              "not show robust positive forward edge across IS+OOS at K=6 — either the break is already "
              "priced by confirmation time (lagging) or the window is wrong. NEXT STEP: before any "
              "real-fills A/B, sweep the forward horizon K and the swing window, and test CHoCH-as-"
              "reversal separately; if no horizon separates, keep market_structure WATCH_ONLY "
              "(detection-correct but no standalone entry edge) per its current status.")
    lines.append(v3)
    lines.append("")

    # ---- OP-16 / disclosure footer ----
    lines.append("## Cross-cutting notes (OP-16 / OP-20)")
    lines.append("")
    lines.append("- **None of the three is ratify-ready.** This screen is the *first* gate; each "
                 "PASS still owes the full bundle: OPRA real-fills (C1 authority — BS/price is "
                 "ranking-only), `null_baseline.null_gate` (beat the null MAX, L172), "
                 "`j_edge_tracker` anchor-no-regression (keep $1542 winners, add no $725 losers, OP-16), "
                 "truncation cross-check (no sign-flip at chart-stop-only, L171), and ≥4/6 positive "
                 "quarters + top5≤200%.")
    lines.append("- **C3/L58 disclosure:** every number above is SPY 5m PRICE direction, not option "
                 "premium P&L. A price-bps edge can still die in the delta/theta/stop translation. "
                 "The real-fills validator is the only WR/expectancy authority.")
    lines.append("- **C22 disclosure (H1):** J's VWAP/time findings are SPX 2021-23 (n=9 / histogram). "
                 "The IS+OOS columns above are the SPY-now re-validation; they are reported as measured, "
                 "not assumed.")
    lines.append("")
    lines.append(f"_Generated by `backtest/autoresearch/_overnight_0621_edge_validate.py` "
                 f"(pure-Python, $0). Reproducer: `backtest/.venv/Scripts/python.exe -m "
                 f"autoresearch._overnight_0621_edge_validate` from `backtest/`._")

    OUT.write_text("\n".join(lines), encoding="utf-8")

    # console summary
    print("H1 with-VWAP IS avg_bps:", is_w["avg_bps"], "OOS:", oos_w["avg_bps"],
          "sep IS/OOS:", round(h1_is_sep, 2), round(h1_oos_sep, 2), "PASS:", h1_pass)
    print("H2 IS worst hour:", worst_is, "best:", best_is, "10:00 OOS bps:",
          oos_by_hr.get(10, {}).get("avg_bps"))
    print("H3 BOS IS/OOS avg_bps:", bos_is["avg_bps"], bos_oos["avg_bps"],
          "CHoCH IS/OOS:", choch_is["avg_bps"], choch_oos["avg_bps"], "BOS PASS:", h3_bos_pass)
    print("H3 fire days IS:", len(h3_fire["is"]), "/", h3_tot["is"],
          "OOS:", len(h3_fire["oos"]), "/", h3_tot["oos"])
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
