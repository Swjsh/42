"""B6-EXTERNAL: turn-of-the-month directional drift — 0DTE SPY CALL, real-fills + 8 fraud gates.

SOURCED STRATEGY (external, NOT one of the ~41 families we have already tested):
  Turn-of-the-month (McConnell-Xu) directional drift. A decades-persistent calendar
  anomaly: ~all of SPY's positive monthly drift accrues in the band from the LAST trading
  day of the month (TD-1) through the THIRD trading day of the next (TD+3) — TD+1 and TD+3
  contribute the most. The hypothesis under test is whether stacking that calendar tailwind
  on top of the ONE survivor structure we know clears the 0DTE wall (ITM/ATM CALL + tight
  -8% premium stop + morning entry, ridden as trend-continuation) yields a REAL per-trade
  OPTION edge — or whether, like the other ~40 directional-underlying ideas, it dies on
  0DTE real fills (theta / delta / stop-misfire / random-null / truncation).

CALENDAR FILTER (the whole novelty): active window = TD-1 .. TD+3 of each month boundary
  (the 4-5 session band). Computed purely from the trading-day sequence in the loaded SPY
  data (no exchange-calendar dependency, no look-ahead — membership of a date depends only
  on that date's position within its own/neighboring month's realized trading days).

ENTRY (CALL ONLY — bull-only window, never a put): on each session inside the window, at
  the morning entry gate (first RTH bar at/after 09:35 ET, capped 09:45), provided the open
  is NOT a hard risk-off open. RISK-OFF SKIP = open gaps DOWN >= GAP_DN_PCT vs prior close
  AND VIX is SPIKING (>= VIX_SPIKE_ABS and rising vs prior session) — the drift is a
  tailwind, not a knife-catch (per the sourced rule).

EXIT: v15 defaults via simulate_trade_real (TP1 partial at chart level/+30%, runner trails
  20% off HWM via chandelier, 15:50 ET hard time stop). rejection_level = the morning swing
  LOW (session low at entry) — the chart-stop invalidation (C2: first-strike chart-stop, no
  premium stop in spirit; the -8% PRIMARY is the survivor cell, chart-stop-only is the (c)
  truncation comparator).

STRIKE: PRIMARY = survivor structure ITM-1 (strike_offset=-1) + -8% stop. Per the task spec
  ("ITM/ATM, per tier") we headline ITM-1 (the conservative-tier ATM/ITM-1 call) and disclose
  the ATM..ITM-2 x stop sweep. NO cherry-pick: the PRIMARY survivor cell is the verdict head.

THE 8 FRAUD GATES (all must hold for EDGE; reuse backtest/autoresearch/fraud_gates.py):
  1 OOS-positive            OOS(2026) per-trade expectancy > 0
  2 positive_quarters       >= 4/6 quarters positive
  3 concentration           top5-winning-day % of total P&L < 200
  4 n_trades                >= 20 completed real-fills trades
  5 drop-top-5-days         per-trade still > 0 after removing 5 best days
  6 beats-random-null       per-trade beats the coin-flip null MAX AND drop-top5 beats null MEAN
  7 no-truncation           sign of per-trade does NOT invert between -8% stop and chart-stop-only
  8 (composite) passes      fraud_gates.verify_candidate .passes (gates 6+7 wired) AND 1-5 clear

DOCTRINE: real OPRA fills (lib.simulator_real) are the ONLY WR/expectancy authority (C1).
WR is a theta trap — per-trade EXPECTANCY is the edge (OP-14). A SPY-price/calendar edge is
NOT automatically an option edge (C3/L58). Pure Python, $0, no LLM, no live orders.

Output: analysis/recommendations/b6-turn-of-month-drift.json  (B6-EXTERNAL section)
Run:    backtest/.venv/Scripts/python.exe backtest/autoresearch/_b6_turn_of_month_drift.py
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
from autoresearch.null_baseline import random_entry_null  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "b6-turn-of-month-drift.json"

# ── Strategy parameters ──────────────────────────────────────────────────────
TD_BEFORE = 1          # include the LAST trading day of the month (TD -1)
TD_AFTER = 3           # ... through the 3rd trading day of the next month (TD +3)
ENTRY_GATE_START = dt.time(9, 35)
ENTRY_GATE_END = dt.time(9, 45)
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
GAP_DN_PCT = -0.0075   # open gaps down >= 0.75% vs prior close -> potential risk-off
VIX_SPIKE_ABS = 22.0   # AND VIX >= 22 and rising vs prior session -> SKIP (knife-catch)
QTY = 3
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# PRIMARY survivor config (the live vwap_continuation shape, conservative tier = ATM/ITM-1)
PRIMARY_STRIKE_OFFSET = -1     # ITM-1 (negative = ITM, verified simulator_real)
PRIMARY_STOP = -0.08
TRUNCATION_STOP = -0.99        # chart-stop only — the no-truncation comparator

# Secondary sweep (disclosure only — NOT a winner-picker)
STRIKE_OFFSETS = [0, -1, -2]   # ATM, ITM-1, ITM-2
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

RANDOM_SEEDS = 20

# OP-11 self-verify gate (gates 1-5)
GATE = {"oos_per_trade": 0.0, "positive_quarters_min": 4, "top5_max_pct": 200.0,
        "n_min": 20, "drop_top5_per_trade_min": 0.0}


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _drop_top5_per_trade(rows: list[dict]) -> tuple[float, int, float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    top5_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    kept = [r for r in rows if r["date"] not in top5_days]
    dropped_pnl = sum(by_day[d] for d in top5_days)
    if not kept:
        return 0.0, 0, dropped_pnl
    return sum(r["pnl"] for r in kept) / len(kept), len(kept), dropped_pnl


# ─────────────────────────────────────────────────────────────────────────────
# CALENDAR: turn-of-the-month window membership (TD-1 .. TD+3), no look-ahead.
# Membership of date D depends only on D's ordinal position within its own month's
# realized trading days and the next month's first-N — a static calendar fact, never
# a function of intraday/future price. (C6: causal.)
# ─────────────────────────────────────────────────────────────────────────────
def turn_of_month_dates(trading_days: list[dt.date]) -> set[dt.date]:
    """Return the set of trading days inside any TD-1..TD+3 turn-of-month band.

    For each calendar (year, month): the LAST `TD_BEFORE` trading days of that month
    (TD -1, counting back) PLUS the FIRST `TD_AFTER` trading days of the NEXT month.
    """
    by_month: dict[tuple[int, int], list[dt.date]] = defaultdict(list)
    for d in sorted(set(trading_days)):
        by_month[(d.year, d.month)].append(d)
    members: set[dt.date] = set()
    months = sorted(by_month.keys())
    for i, ym in enumerate(months):
        days = by_month[ym]
        # last TD_BEFORE trading days of this month (the TD -1 leg)
        for d in days[-TD_BEFORE:]:
            members.add(d)
        # first TD_AFTER trading days of the NEXT month (TD +1 .. TD +TD_AFTER)
        if i + 1 < len(months):
            nxt = by_month[months[i + 1]]
            for d in nxt[:TD_AFTER]:
                members.add(d)
    return members


# ─────────────────────────────────────────────────────────────────────────────
# SIGNALS: one CALL entry per in-window session, morning gate, risk-off skip.
# bar_idx indexes into the reset-RangeIndex RTH frame (fraud_gates contract).
# ─────────────────────────────────────────────────────────────────────────────
def build_signals(rth: pd.DataFrame, vix_by_day: dict[dt.date, float]) -> tuple[list[dict], dict]:
    trading_days = sorted(rth["date"].unique().tolist())
    tom = turn_of_month_dates(trading_days)
    prior_close: dict[dt.date, float] = {}
    prior_vix: dict[dt.date, float] = {}
    last_close = None
    last_vix = None
    # prior-session close + vix (last RTH close / vix of the previous trading day)
    for d in trading_days:
        if last_close is not None:
            prior_close[d] = last_close
        if last_vix is not None:
            prior_vix[d] = last_vix
        day_rth = rth[rth["date"] == d]
        last_close = float(day_rth["close"].iloc[-1])
        last_vix = vix_by_day.get(d, last_vix)

    signals: list[dict] = []
    diag = {"in_window_days": 0, "skipped_riskoff": 0, "no_gate_bar": 0}
    for d in trading_days:
        if d not in tom:
            continue
        diag["in_window_days"] += 1
        day = rth[rth["date"] == d]
        gate = day[(day["t"] >= ENTRY_GATE_START) & (day["t"] <= ENTRY_GATE_END)]
        if gate.empty:
            diag["no_gate_bar"] += 1
            continue
        entry_row = gate.iloc[0]
        idx = int(entry_row.name)  # positional == label (reset RangeIndex)
        sess_open = float(day["open"].iloc[0])
        pc = prior_close.get(d)
        vix_now = vix_by_day.get(d, 17.0)
        vix_prev = prior_vix.get(d, vix_now)
        gap = (sess_open / pc - 1.0) if pc else 0.0
        vix_spiking = (vix_now >= VIX_SPIKE_ABS) and (vix_now > vix_prev)
        if gap <= GAP_DN_PCT and vix_spiking:
            diag["skipped_riskoff"] += 1
            continue
        # chart-stop invalidation = morning session low up to/including the entry bar
        upto = day[day["t"] <= entry_row["t"]]
        swing_low = float(upto["low"].min())
        signals.append({
            "idx": idx, "date": d, "time": str(entry_row["t"]), "side": "C",
            "rejection_level": round(swing_low, 2), "vix": round(vix_now, 2),
            "gap_pct": round(gap, 4),
        })
    return signals, {"tom_days_total": len(tom & set(trading_days)), **diag}


def simulate_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                  premium_stop_pct: float) -> tuple[_Acc, list[dict], int]:
    overall = _Acc()
    rows: list[dict] = []
    no_data = 0
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["turn_of_month_drift", "td_window", "morning_gate"],
            side=s["side"], qty=QTY, setup="TOM_DRIFT",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "vix": s["vix"],
            "gap_pct": s["gap_pct"], "strike": fill.strike,
            "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2), "year": s["date"].year, "quarter": _quarter(s["date"]),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })
    return overall, rows, no_data


def verify_cell(rows: list[dict]) -> dict:
    """Gates 1-5 (OP-11 structural self-verify) for one cell's per-trade rows."""
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    overall = _Acc()
    for r in rows:
        overall.add(r["pnl"], r["date"])
        by_sample["IS_2025" if r["year"] == 2025 else "OOS_2026"].add(r["pnl"], r["date"])
        by_q[r["quarter"]].add(r["pnl"], r["date"])

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for v in q_reports.values() if v.get("total_pnl", 0) and v["total_pnl"] > 0)
    is_r, oos_r = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    drop_pt, n_ex, dropped = _drop_top5_per_trade(rows)
    ov = overall.report()

    oos_pt = oos_r.get("per_trade") if oos_r.get("n") else None
    g1 = oos_pt is not None and oos_pt > GATE["oos_per_trade"]
    g2 = pos_q >= GATE["positive_quarters_min"]
    g3 = ov.get("top5_day_pct") is not None and ov["top5_day_pct"] < GATE["top5_max_pct"]
    g4 = ov["n"] >= GATE["n_min"]
    g5 = drop_pt > GATE["drop_top5_per_trade_min"]
    return {
        "overall": ov,
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "positive_quarters_n": pos_q,
        "n_quarters": len(q_reports),
        "oos_per_trade": oos_pt,
        "drop_top5_per_trade": round(drop_pt, 2),
        "drop_top5_n": n_ex,
        "dropped_top5_pnl": round(dropped, 0),
        "top5_day_pct": ov.get("top5_day_pct"),
        "gate1_oos_positive": bool(g1),
        "gate2_positive_quarters": bool(g2),
        "gate3_concentration": bool(g3),
        "gate4_n_trades": bool(g4),
        "gate5_drop_top5": bool(g5),
        "clears_bar": bool(g1 and g2 and g3 and g4 and g5),
    }


def run() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_START)
                   & (spy_full["timestamp_et"].dt.time < RTH_END)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    rth["t"] = rth["timestamp_et"].dt.time
    for c in ("open", "high", "low", "close", "volume"):
        rth[c] = rth[c].astype(float)
    log.info("RTH bars: %d  trading_days: %d", len(rth), rth["date"].nunique())

    # VIX per-session close (last vix value of each trading day), ffill aligned.
    vix_full = vix_full.copy()
    vix_full["timestamp_et"] = pd.to_datetime(vix_full["timestamp_et"])
    vix_full["date"] = vix_full["timestamp_et"].dt.date
    vix_by_day: dict[dt.date, float] = {}
    for d, g in vix_full.groupby("date"):
        vix_by_day[d] = float(g["close"].astype(float).iloc[-1])

    signals, sig_diag = build_signals(rth, vix_by_day)
    n_call = sum(1 for s in signals if s["side"] == "C")
    n_put = sum(1 for s in signals if s["side"] == "P")
    log.info("TOM signals: %d (CALL=%d PUT=%d)  window_diag=%s",
             len(signals), n_call, n_put, sig_diag)

    # ── Sweep (disclosure) + capture PRIMARY rows ────────────────────────────
    sweep: list[dict] = []
    primary_rows: list[dict] = []
    primary_overall: _Acc | None = None
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            overall, rows, no_data = simulate_cell(rth, signals, so, ps)
            rep = overall.report()
            sweep.append({"strike_offset": so, "premium_stop_pct": ps,
                          "report": rep, "n_no_opra_data": no_data})
            log.info("  so=%+d ps=%.2f -> n=%s per_trade=%s total=%s top5%%=%s",
                     so, ps, rep.get("n"), rep.get("per_trade"), rep.get("total_pnl"),
                     rep.get("top5_day_pct"))
            if so == PRIMARY_STRIKE_OFFSET and abs(ps - PRIMARY_STOP) < 1e-9:
                primary_rows, primary_overall = rows, overall

    n_primary = primary_overall.n if primary_overall else 0

    # ── Gates 1-5: structural self-verify on PRIMARY survivor cell ──
    verify = verify_cell(primary_rows) if primary_rows else {
        "overall": {"n": 0}, "by_sample": {}, "by_quarter": {}, "positive_quarters": "0/0",
        "positive_quarters_n": 0, "n_quarters": 0, "oos_per_trade": None,
        "drop_top5_per_trade": 0.0, "drop_top5_n": 0, "dropped_top5_pnl": 0,
        "top5_day_pct": None, "gate1_oos_positive": False, "gate2_positive_quarters": False,
        "gate3_concentration": False, "gate4_n_trades": False, "gate5_drop_top5": False,
        "clears_bar": False}
    primary_pt = verify["overall"].get("per_trade") if verify["overall"].get("n") else None

    # ── Gates 6+7: fraud_gates.verify_candidate (random-null + no-truncation) ──
    cand_signals = [CandidateSignal(bar_idx=s["idx"], side=s["side"],
                                    rejection_level=s["rejection_level"],
                                    note="tom_drift") for s in signals]
    fraud = None
    fraud_dict = {}
    if n_primary > 0:
        log.info("Running fraud_gates.verify_candidate (random-null %d seeds + no-truncation)...",
                 RANDOM_SEEDS)
        fraud = verify_candidate(
            cand_signals, rth, strike_offset=PRIMARY_STRIKE_OFFSET,
            premium_stop_pct=PRIMARY_STOP, qty=QTY, setup="TOM_DRIFT",
            seeds=RANDOM_SEEDS, chart_stop_pct=TRUNCATION_STOP, sim_fn=simulate_trade_real)
        fraud_dict = fraud.as_dict()
        log.info("  fraud verdict: passes=%s null_pass=%s no_trunc=%s reason=%s",
                 fraud.passes, fraud.null_pass, fraud.no_truncation_pass, fraud.reason)

    gate6_beats_null = bool(fraud.null_pass) if fraud else False
    gate7_no_truncation = bool(fraud.no_truncation_pass) if fraud else False
    gate8_fraud_passes = bool(fraud.passes) if fraud else False

    gates = {
        "gate1_oos_positive": verify["gate1_oos_positive"],
        "gate2_positive_quarters": verify["gate2_positive_quarters"],
        "gate3_concentration": verify["gate3_concentration"],
        "gate4_n_trades": verify["gate4_n_trades"],
        "gate5_drop_top5": verify["gate5_drop_top5"],
        "gate6_beats_random_null": gate6_beats_null,
        "gate7_no_truncation": gate7_no_truncation,
        "gate8_fraud_passes": gate8_fraud_passes,
    }
    gates_passed = sum(1 for v in gates.values() if v)
    all_pass = all(gates.values())

    # ── Verdict (no cherry-pick: PRIMARY survivor config is the headline) ──
    if n_primary == 0:
        death_cause = "no_completed_trades"
        verdict = ("DEAD: PRIMARY survivor cell (ITM-1,-8%) produced 0 completed real-fills "
                   "trades (no OPRA data at strike, or no in-window morning entries).")
    elif n_primary < GATE["n_min"]:
        death_cause = "insufficient_n"
        verdict = (f"DEAD: n={n_primary} < {GATE['n_min']} — the TD-1..TD+3 window only fires "
                   "~4-5 sessions/month, too sparse over the data window to validate.")
    elif all_pass:
        death_cause = ""
        verdict = ("EDGE: TOM directional drift CLEARS ALL 8 FRAUD GATES on real OPRA fills — "
                   "OOS-positive, broad across quarters, not day-concentrated, beats the "
                   "random-entry null, and is truncation-safe. The calendar tailwind adds a "
                   "real per-trade OPTION edge on top of the survivor exit structure.")
    else:
        fails = [k for k, v in gates.items() if not v]
        # name the dominant death cause (the 0DTE failure modes, in priority order)
        if not gate7_no_truncation:
            death_cause = "truncation_artifact"
        elif not gate6_beats_null:
            death_cause = "random_null_reproduces (SPY-price/calendar tilt, not option edge; C3/L58)"
        elif not verify["gate1_oos_positive"]:
            death_cause = "oos_negative (theta/delta erodes the directional drift on 0DTE)"
        elif not verify["gate3_concentration"]:
            death_cause = "day_concentration"
        elif not verify["gate2_positive_quarters"]:
            death_cause = "quarter_instability"
        else:
            death_cause = "; ".join(fails)
        verdict = (f"DEAD ({gates_passed}/8 gates): TOM directional drift fails on 0DTE real "
                   f"fills. Failed gates: {', '.join(fails)}. Primary death cause: {death_cause}.")

    summary = {
        "run_date": dt.date.today().isoformat(),
        "section": "B6-EXTERNAL",
        "slug": "turn-of-the-month-directional-drift",
        "arena": "0dte",
        "cls": "directional_continuation_calendar",
        "hypothesis": ("Turn-of-the-month (McConnell-Xu): SPY's positive monthly drift "
                       "concentrates in TD-1..TD+3. Restrict the survivor structure (ITM/ATM "
                       "CALL + tight -8% morning chart-stop, trend-continuation) to that 4-5 "
                       "session band, stacking the calendar tailwind on the entry shape that "
                       "already clears the 0DTE wall. CALL-only (bull-only window)."),
        "source": ("external academic calendar anomaly (McConnell & Xu, turn-of-the-month "
                   "effect); adapted to SPY 0DTE single-leg CALL per task spec. NOT one of the "
                   "~41 families already tested."),
        "window": f"{START}..{END}",
        "sourced_rule": {
            "calendar_filter": f"active TD-{TD_BEFORE} (last trading day of month) .. TD+{TD_AFTER} (3rd trading day of next month)",
            "entry": f"CALL at first RTH bar in {ENTRY_GATE_START}-{ENTRY_GATE_END} ET, in-window sessions only",
            "risk_off_skip": (f"SKIP if open gaps down >= {abs(GAP_DN_PCT)*100:.2f}% vs prior close "
                              f"AND VIX >= {VIX_SPIKE_ABS} and rising vs prior session"),
            "exit": "chart-stop only (morning swing low) + v15 TP1/runner/chandelier + 15:50 hard time stop",
            "side": "CALL only (bull-only window) — never a put",
        },
        "adaptation": {
            "instrument": "SPY 0DTE single-leg CALL",
            "td_window": [f"TD-{TD_BEFORE}", f"TD+{TD_AFTER}"],
            "calendar_causality": ("window membership = static position within own/neighboring "
                                   "month's realized trading days; never a function of future price (C6)"),
            "rejection_level": "morning session low at/through the entry bar (chart-stop invalidation, C2)",
            "entry_gate": f"{ENTRY_GATE_START}-{ENTRY_GATE_END}",
            "qty": QTY, "exits": "v15 defaults (causal)",
        },
        "primary_config": {
            "label": "SURVIVOR STRUCTURE (live vwap_continuation shape, conservative tier ATM/ITM-1)",
            "strike_offset": PRIMARY_STRIKE_OFFSET, "strike_tier": "ITM-1",
            "premium_stop_pct": PRIMARY_STOP, "exits": "v15 defaults",
        },
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "self_verify_gate": GATE,
        "n_signals": len(signals), "n_call": n_call, "n_put": n_put,
        "window_diagnostics": sig_diag,
        "sweep": sweep,
        "primary_verify_gates_1to5": verify,
        "fraud_gates_6to8": fraud_dict,
        "EIGHT_GATES": gates,
        "gates_passed": f"{gates_passed}/8",
        "primary_per_trade": primary_pt,
        "oos_per_trade": verify.get("oos_per_trade"),
        "all_8_gates_pass": bool(all_pass),
        "death_cause": death_cause,
        "verdict": verdict,
        "sample_rows": primary_rows[:25],
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14, WR is a theta trap)",
            "is_oos": "IS=2025, OOS=2026 split shown for the PRIMARY survivor cell",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5; anti-2.10)",
            "no_cherry_pick": ("verdict uses the PRIMARY survivor config (ITM-1,-8%) as headline, "
                               "NOT the best sweep cell; the sweep is disclosure only"),
            "spy_vs_option": ("C3/L58 — a SPY-price/calendar drift edge is NOT automatically an "
                              "option edge; theta+delta+stop-misfire routinely erase a directional-"
                              "underlying edge on 0DTE"),
            "random_entry_null": ("gate 6: PRIMARY cell vs coin-flip null (random RTH entries, same "
                                  "count/side-mix/stop/strike, 20 seeds). If random reproduces the "
                                  "per-trade, the 'edge' is the exit STRUCTURE, not the calendar signal."),
            "truncation_check": ("gate 7: sign of per-trade must NOT invert between -8% stop and "
                                 "chart-stop-only (-0.99); a +->- flip = the tight stop truncates "
                                 "losers (stop artifact, not directional/calendar signal)."),
            "the_0dte_wall": ("~41-family prior: nearly every directional SPY-price edge dies on 0DTE; "
                              "the only survivor (live vwap_continuation) is ITM/ATM + tight stop + "
                              "morning + sustained-directional — exactly the PRIMARY config tested here."),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)
    log.info("VERDICT: %s", verdict)
    return summary


if __name__ == "__main__":
    run()
