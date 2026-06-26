"""B6-EXTERNAL — NR7 / Inside-Day compression -> ORB expansion (Crabel) real-fills test.

SOURCED STRATEGY (external, slug=nr7-inside-day-compression-orb-expansion):
  REGIME FILTER (the novel part): the PRIOR trading day must be NR7 (its high-low range
  is the narrowest of the last 7 trading days) AND/OR an Inside Day (prior day's high <
  day-2 high AND low > day-2 low). This "double compression" (NR7ID) flags pent-up energy.
  Daily H/L/range are aggregated from the 5m RTH bars (09:30-16:00 ET) per day.

  ENTRY (only on days following such compression): mark the opening-range high/low
  (first 15 min, 09:30-09:45 ET => the 3 RTH 5m bars 09:30/09:35/09:40). Buy a 0DTE CALL
  (ATM/ITM-1) on a 5m CLOSE above the OR high; buy a PUT on a 5m close below the OR low.
  ONE side per day; if the first break reverses and the other side later breaks, do NOT
  chase (the prompt's 78%-one-side observation -> first-break-only is enforced here).

  EXIT: chart-stop at the OPPOSITE side of the opening range (mechanical, no premium stop,
  C2). Survivor structure applied: ATM/ITM-1 strike + tight -8% stop + morning window, AND
  a chart-stop-only (-0.99) reference is swept so the no-truncation gate has its anchor.

THE DIFFERENTIATOR vs the generic ORB we already KILLED (orb_real_fills + ORB+RVOL/H3):
  the PRIOR-DAY COMPRESSION GATE. Crabel's thesis: vanilla ORB is noise EXCEPT when
  preceded by volatility contraction. This test asks whether that regime filter rescues
  the ORB structure on REAL OPRA fills.

8 FRAUD-GATES (the project's full bar; .passes only if all clear on the headline cell):
  OP-20 disclosure (4): (1) OOS-positive per-trade  (2) positive_quarters >= 4/6
                        (3) top5_day_pct < 200%       (4) n_trades >= 20
  Graduated fraud_gates.verify_candidate (2): (5) no-truncation (sign holds at chart-stop
                        -only)                 (6) beats-null (vs 20-seed random-entry MAX
                        AND drop-top5 beats null mean)
  Plus the two embedded discriminators the verify harness also surfaces:
                        (7) no-OPRA-truncation (n_chart_stop_only ~ n_chosen, fills exist)
                        (8) is_truncation_artifact == False (the KILLER-COMBO check).

REAL-FILLS AUTHORITY (C1): simulate_trade_real is the only WR authority. SPY-direction
!= option edge (C3/L58). WR is a theta trap; per-trade EXPECTANCY is the edge (OP-14).
Pure Python, $0, no live orders.

Output: analysis/recommendations/nr7-inside-day-compression-orb-expansion.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# ── Window + fixed params ─────────────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
QTY = 3
SETUP = "NR7ID_ORB_EXPANSION"
SLUG = "nr7-inside-day-compression-orb-expansion"

OR_END = dt.time(9, 45)          # opening range = 09:30..09:45 (first 3 RTH 5m bars)
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
TIME_STOP = dt.time(15, 50)      # hard time stop (handled inside simulate_trade_real)
NR7_LOOKBACK = 7                 # narrowest range of last 7 trading days (incl. prior day)

# Survivor structure: ATM / ITM-1, tight -8% stop morning window. Chart-stop-only swept
# as the truncation reference (gate 5/8 needs the -0.99 sign reference).
STRIKE_OFFSETS = [0, -1]                       # ATM, ITM-1 (neg=ITM for both call & put)
PREMIUM_STOPS = [-0.08, -0.99]                 # -0.08 = survivor tight stop; -0.99 = chart-stop-only

# OP-20 candidate-edge bars
BAR_OOS_PER_TRADE_GT = 0.0
BAR_POS_QUARTERS_MIN = 4
BAR_TOP5_DAY_PCT_LT = 200.0
BAR_N_TRADES_MIN = 20


def _is_oos(d: dt.date) -> str:
    return "IS_2025" if d.year == 2025 else "OOS_2026"


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _strike_label(off: int) -> str:
    return "ATM" if off == 0 else (f"ITM{-off}" if off < 0 else f"OTM{off}")


def _stop_label(p: float) -> str:
    return "chartstop" if p <= -0.99 else f"{int(round(-p * 100))}pct"


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day", "by_q", "by_sample")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)
        self.by_q: dict[str, "_Acc"] = {}
        self.by_sample: dict[str, "_Acc"] = {}

    def add(self, pnl, day, q=None, sample=None, _top=True):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl
        if q is not None:
            self.by_q.setdefault(q, _Acc()).add(pnl, day, _top=False)
        if sample is not None:
            self.by_sample.setdefault(sample, _Acc()).add(pnl, day, _top=False)

    def top5_day_pct(self):
        if self.pnl <= 0 or not self.by_day:
            return None
        top5 = sum(sorted(self.by_day.values(), reverse=True)[:5])
        return round(100.0 * top5 / self.pnl, 0)

    def report(self):
        if not self.n:
            return {"n": 0}
        return {"n": self.n, "wr": round(100.0 * self.wins / self.n, 1),
                "total_pnl": round(self.pnl, 0), "per_trade": round(self.pnl / self.n, 1),
                "top5_day_pct": self.top5_day_pct()}


# ── Step 1: daily aggregation + NR7 / Inside-Day compression flag ─────────────
def compute_compression_days(rth: pd.DataFrame) -> dict:
    """Aggregate 5m RTH bars to daily H/L/range; flag each day's PRIOR-day compression.

    Returns {date -> {"nr7": bool, "inside": bool, "compressed": bool}} where the flags
    describe the PRIOR trading day (so 'compressed' == this day is eligible to trade).
    No look-ahead: a day's eligibility uses only days strictly before it.
    """
    daily = (rth.groupby("date")
                .agg(high=("high", "max"), low=("low", "min"))
                .assign(rng=lambda d: d["high"] - d["low"])
                .sort_index())
    dates = list(daily.index)
    flags: dict = {}
    for i, d in enumerate(dates):
        if i < NR7_LOOKBACK:        # need >=7 prior days for NR7 + a day-2 for inside-day
            continue
        prior = dates[i - 1]
        prior2 = dates[i - 2]
        # NR7: prior day's range is the narrowest of the last 7 trading days (the 7-day
        # window ENDING on the prior day, i.e. days [i-7 .. i-1]).
        window = daily.loc[dates[i - NR7_LOOKBACK]:prior, "rng"]
        is_nr7 = float(daily.loc[prior, "rng"]) == float(window.min()) and len(window) == NR7_LOOKBACK
        # Inside day: prior high < day-2 high AND prior low > day-2 low.
        is_inside = (float(daily.loc[prior, "high"]) < float(daily.loc[prior2, "high"]) and
                     float(daily.loc[prior, "low"]) > float(daily.loc[prior2, "low"]))
        flags[d] = {"nr7": bool(is_nr7), "inside": bool(is_inside),
                    "compressed": bool(is_nr7 or is_inside)}   # NR7 AND/OR Inside (prompt)
    return flags


# ── Step 2: detect ONE first-break ORB signal per eligible day ────────────────
def detect_signals(rth: pd.DataFrame, flags: dict) -> list[dict]:
    """One signal per compressed day: first 5m CLOSE above OR-high (call) or below
    OR-low (put), at/after 09:45 ET. First break only — no chasing the other side."""
    signals: list[dict] = []
    for day, day_df in rth.groupby("date", sort=True):
        f = flags.get(day)
        if not f or not f["compressed"]:
            continue
        day_df = day_df.reset_index()  # keeps original rth index in 'index'
        opening = day_df[day_df["timestamp_et"].dt.time < OR_END]
        if len(opening) < 1:
            continue
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        if or_high <= or_low:
            continue
        post = day_df[day_df["timestamp_et"].dt.time >= OR_END]
        for _, row in post.iterrows():
            c = float(row["close"])
            ts = pd.Timestamp(row["timestamp_et"])
            if ts.time() >= TIME_STOP:
                break
            if c > or_high:
                signals.append({"global_idx": int(row["index"]), "date": day,
                                "time": ts.strftime("%H:%M"), "side": "C",
                                "or_high": or_high, "or_low": or_low,
                                "rejection_level": or_low,     # chart stop = opposite OR side
                                "nr7": f["nr7"], "inside": f["inside"]})
                break
            if c < or_low:
                signals.append({"global_idx": int(row["index"]), "date": day,
                                "time": ts.strftime("%H:%M"), "side": "P",
                                "or_high": or_high, "or_low": or_low,
                                "rejection_level": or_high,    # chart stop = opposite OR side
                                "nr7": f["nr7"], "inside": f["inside"]})
                break
    return signals


# ── Step 3: run the real-fills sim for one (strike, stop) cell ────────────────
def run_config(signals, rth, *, strike_offset, premium_stop_pct):
    acc = _Acc()
    no_data = 0
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["global_idx"], entry_bar=rth.iloc[s["global_idx"]], spy_df=rth,
            ribbon_df=None, rejection_level=s["rejection_level"], triggers_fired=[SETUP],
            side=s["side"], qty=QTY, setup=SETUP,
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            no_data += 1
            continue
        acc.add(float(fill.dollar_pnl), s["date"].isoformat(),
                q=_quarter(s["date"]), sample=_is_oos(s["date"]))
    return acc, no_data


def _disclosure(acc, no_data):
    overall = acc.report()
    is_acc = acc.by_sample.get("IS_2025", _Acc())
    oos_acc = acc.by_sample.get("OOS_2026", _Acc())
    pos_q = sum(1 for a in acc.by_q.values() if a.pnl > 0)
    n_q = len(acc.by_q)
    oos_pt = (oos_acc.pnl / oos_acc.n) if oos_acc.n else 0.0
    top5 = acc.top5_day_pct()
    n = acc.n
    reasons = []
    if not (oos_pt > BAR_OOS_PER_TRADE_GT):
        reasons.append(f"OOS per-trade {oos_pt:.1f} <= 0")
    if not (pos_q >= BAR_POS_QUARTERS_MIN):
        reasons.append(f"positive_quarters {pos_q}/{n_q} < {BAR_POS_QUARTERS_MIN}")
    if top5 is None or not (top5 < BAR_TOP5_DAY_PCT_LT):
        reasons.append(f"top5_day_pct {top5} not < {BAR_TOP5_DAY_PCT_LT}")
    if not (n >= BAR_N_TRADES_MIN):
        reasons.append(f"n_trades {n} < {BAR_N_TRADES_MIN}")
    return {"n_trades": n, "n_no_opra_data": no_data, "overall": overall,
            "overall_per_trade": overall.get("per_trade"),
            "IS_2025": is_acc.report(), "OOS_2026": oos_acc.report(),
            "oos_per_trade": round(oos_pt, 2),
            "by_quarter": {q: acc.by_q[q].report() for q in sorted(acc.by_q)},
            "positive_quarters": f"{pos_q}/{n_q}", "top5_day_pct": top5,
            "op20_clears": len(reasons) == 0, "fail_reasons": reasons}


def main() -> int:
    log.info("Loading %s..%s SPY+VIX...", START, END)
    spy_full, _vix = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_START)
                   & (spy_full["timestamp_et"].dt.time < RTH_END)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    flags = compute_compression_days(rth)
    n_compressed = sum(1 for v in flags.values() if v["compressed"])
    n_nr7 = sum(1 for v in flags.values() if v["nr7"])
    n_inside = sum(1 for v in flags.values() if v["inside"])
    log.info("Eligible (compressed-prior-day) days: %d  (NR7=%d, Inside=%d, total-days=%d)",
             n_compressed, n_nr7, n_inside, len(flags) + NR7_LOOKBACK)

    signals = detect_signals(rth, flags)
    n_call = sum(1 for s in signals if s["side"] == "C")
    n_put = sum(1 for s in signals if s["side"] == "P")
    log.info("Signals (first-break, one/day): %d  (calls=%d puts=%d, distinct days=%d)",
             len(signals), n_call, n_put, len({s["date"] for s in signals}))
    if not signals:
        log.error("No NR7ID-ORB signals detected — aborting.")
        return 1

    # ── Step A: strike x stop grid (2x2) — find headline cell ────────────────
    log.info("\n=== STRIKE x STOP GRID (2x2) ===")
    grid = []
    for off in STRIKE_OFFSETS:
        for stop in PREMIUM_STOPS:
            acc, nd = run_config(signals, rth, strike_offset=off, premium_stop_pct=stop)
            disc = _disclosure(acc, nd)
            cfg = f"{_strike_label(off)}/{_stop_label(stop)}"
            grid.append({"config": cfg, "strike_offset": off, "premium_stop_pct": stop, **disc})
            log.info("%-16s N=%-4d overall/tr=%-7s OOS/tr=%-7.1f posQ=%s top5=%s %s",
                     cfg, disc["n_trades"], str(disc["overall_per_trade"]), disc["oos_per_trade"],
                     disc["positive_quarters"], disc["top5_day_pct"],
                     "OP20-CLEARS" if disc["op20_clears"] else "")

    # Headline cell = the survivor structure (tight -8% stop), best strike by OOS/trade.
    tight_cells = [c for c in grid if c["premium_stop_pct"] == -0.08 and c["n_trades"] > 0]
    headline = max(tight_cells, key=lambda c: c["oos_per_trade"]) if tight_cells else grid[0]
    log.info("\nHeadline cell (survivor tight stop): %s  OOS/tr=%s  N=%s",
             headline["config"], headline["oos_per_trade"], headline["n_trades"])

    # ── Step B: the 2 graduated fraud_gates on the headline cell ─────────────
    cand_sigs = [CandidateSignal(bar_idx=s["global_idx"], side=s["side"],
                                 rejection_level=s["rejection_level"], note=SETUP)
                 for s in signals]
    log.info("\n=== GRADUATED FRAUD GATES (verify_candidate, 20-seed null) on headline cell ===")
    fv = verify_candidate(cand_sigs, rth, strike_offset=headline["strike_offset"],
                          premium_stop_pct=headline["premium_stop_pct"], qty=QTY, setup=SETUP)
    log.info("fraud_gates.passes=%s  no_truncation=%s  beats_null=%s  artifact=%s",
             fv.passes, fv.no_truncation_pass, fv.null_pass, fv.is_truncation_artifact)
    log.info("  reason: %s", fv.reason)

    # ── Tally the 8 gates on the headline cell ────────────────────────────────
    oos = headline["OOS_2026"]
    g1 = headline["oos_per_trade"] > BAR_OOS_PER_TRADE_GT
    g2 = "/" in headline["positive_quarters"] and \
        int(headline["positive_quarters"].split("/")[0]) >= BAR_POS_QUARTERS_MIN
    g3 = headline["top5_day_pct"] is not None and headline["top5_day_pct"] < BAR_TOP5_DAY_PCT_LT
    g4 = headline["n_trades"] >= BAR_N_TRADES_MIN
    g5 = fv.no_truncation_pass
    g6 = fv.null_pass
    g7 = (fv.n_chart_stop_only > 0 and fv.n_chosen > 0 and
          fv.n_chart_stop_only >= 0.8 * fv.n_chosen)   # OPRA fills exist, not stop-truncated to nothing
    g8 = not fv.is_truncation_artifact
    gates = {
        "1_oos_positive": g1, "2_pos_quarters_ge_4of6": g2, "3_top5_day_pct_lt_200": g3,
        "4_n_trades_ge_20": g4, "5_no_truncation": g5, "6_beats_null": g6,
        "7_no_opra_truncation": g7, "8_not_truncation_artifact": g8,
    }
    n_pass = sum(1 for v in gates.values() if v)
    all_pass = all(gates.values())

    # Death cause (first failing gate, in evaluation order).
    death_cause = None
    if not all_pass:
        order = [
            ("4_n_trades_ge_20", f"too few trades (N={headline['n_trades']} < 20) — compression "
                                 f"gate is too rare to sustain a real-fills edge claim"),
            ("1_oos_positive", f"OOS-negative per-trade (${headline['oos_per_trade']}/tr) — "
                               f"compression filter does not survive out-of-sample (C3/L58: SPY "
                               f"breakout != option edge; theta+stop-misfire eat the move)"),
            ("2_pos_quarters_ge_4of6", f"unstable across quarters ({headline['positive_quarters']}) "
                                       f"— not regime-robust"),
            ("3_top5_day_pct_lt_200", f"P&L concentrated in top-5 days (top5={headline['top5_day_pct']}%)"),
            ("6_beats_null", "fails RANDOM-NULL — a coin-flip morning entry on the same exit "
                             "bracket reproduces it; the 'edge' is the v15 exit, not the "
                             "compression+ORB signal (L172)"),
            ("5_no_truncation", "TRUNCATION ARTIFACT — positive only because the tight -8% stop "
                                "truncates losers; sign inverts at chart-stop-only (L171)"),
            ("8_not_truncation_artifact", "truncation artifact (killer-combo)"),
            ("7_no_opra_truncation", "insufficient OPRA fills"),
        ]
        for k, msg in order:
            if not gates[k]:
                death_cause = msg
                break

    verdict_label = "EDGE" if all_pass else ("LEAD" if n_pass >= 5 else "DEAD")
    if all_pass:
        verdict = (f"EDGE — NR7/Inside-Day compression -> ORB expansion CLEARS all 8 fraud-gates on "
                   f"{headline['config']}: OOS/tr=${headline['oos_per_trade']}, "
                   f"posQ={headline['positive_quarters']}, top5={headline['top5_day_pct']}%, "
                   f"N={headline['n_trades']}, beats-null + no-truncation. The Crabel "
                   f"compression regime filter rescues ORB on real OPRA fills.")
    else:
        verdict = (f"{verdict_label} — NR7/Inside-Day compression -> ORB expansion FAILS the 8-gate "
                   f"bar ({n_pass}/8 pass) on headline {headline['config']}. DEATH CAUSE: "
                   f"{death_cause}. Headline: OOS/tr=${headline['oos_per_trade']}, "
                   f"posQ={headline['positive_quarters']}, top5={headline['top5_day_pct']}%, "
                   f"N={headline['n_trades']}; fraud_gates: no_trunc={fv.no_truncation_pass}, "
                   f"beats_null={fv.null_pass}. The prior-day-compression gate does NOT make "
                   f"ORB a real option edge — same fate as the generic ORB / ORB+RVOL we killed "
                   f"(C3/L58: SPY-breakout direction != 0DTE option edge).")

    out = {
        "section": "B6-EXTERNAL",
        "slug": SLUG,
        "family": "external-sourced (Crabel NR7 / Inside-Day compression + ORB expansion)",
        "arena": "0dte",
        "generated_at": dt.datetime.now().isoformat(),
        "window": f"{START}..{END}",
        "authority": "real OPRA fills via simulator_real.simulate_trade_real (C1)",
        "regime_filter": ("PRIOR trading day NR7 (narrowest range of last 7 daily-aggregated "
                          "5m-RTH bars) AND/OR Inside Day (prior H<day-2 H AND prior L>day-2 L)"),
        "entry": ("first 5m CLOSE >OR-high (call) or <OR-low (put) at/after 09:45 ET on an "
                  "eligible day; ONE first-break per day, no chasing the second side"),
        "exit": ("chart-stop at opposite OR side (rejection_level); survivor -8% premium stop "
                 "on headline cell; v15 tiered TP1/runner/chandelier inside simulate_trade_real; "
                 "hard time-stop 15:50 ET"),
        "compression_days": {"compressed": n_compressed, "nr7": n_nr7, "inside": n_inside,
                             "total_trading_days": len(flags) + NR7_LOOKBACK},
        "n_signals": len(signals), "n_calls": n_call, "n_puts": n_put,
        "n_distinct_days": len({s["date"] for s in signals}),
        "fixed_params": {"qty": QTY, "setup": SETUP, "or_window": "09:30-09:45 ET",
                         "nr7_lookback": NR7_LOOKBACK},
        "grids": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "candidate_edge_bar": {"oos_per_trade_gt": BAR_OOS_PER_TRADE_GT,
                               "positive_quarters_min": BAR_POS_QUARTERS_MIN,
                               "top5_day_pct_lt": BAR_TOP5_DAY_PCT_LT,
                               "n_trades_min": BAR_N_TRADES_MIN},
        "strike_stop_grid": grid,
        "headline_cell": headline,
        "fraud_gates_verify": fv.as_dict(),
        "eight_gates": gates,
        "n_gates_passed": n_pass,
        "all_eight_pass": all_pass,
        "verdict_label": verdict_label,
        "death_cause": death_cause,
        "honest_verdict": verdict,
        "OP20_DISCLOSURE": {
            "per_trade": "per-trade EXPECTANCY reported for every cell, not WR alone (OP-14)",
            "is_oos": "IS=2025 / OOS=2026; gate keys off OOS per-trade",
            "positive_quarters": "out of quarters in window; gate requires >=4/6",
            "top5_day_pct": "top-5 winning DAYS as % of total P&L; gate <200%",
            "spy_vs_option": "this is the option-edge test, not a SPY-price test (C3/L58)",
            "fraud_gates": "verify_candidate runs 20-seed random-entry null + no-truncation (L171/L172)",
            "already_tested_distinction": ("generic ORB + ORB+RVOL(H3) already KILLED; the ONLY new "
                                           "thing here is the prior-day NR7/Inside-Day compression gate"),
        },
    }

    out_path = ROOT / "analysis" / "recommendations" / f"{SLUG}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("\nWrote %s", out_path)
    print("\n=== B6-EXTERNAL  NR7/INSIDE-DAY -> ORB  VERDICT ===")
    print(verdict)
    print(f"\ngates passed: {n_pass}/8  -> {gates}")
    print(f"verdict_label: {verdict_label}  death_cause: {death_cause}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
