"""arm_participation_growth_2026_08_03.py -- PER-ARM PARTICIPATION funnel + growth-path model.

WHY THIS EXISTS (task, 2026-08-02 overnight into Monday 2026-08-03): the weekend's other
research (FREQUENCY-CEILING / CAPITAL-EFFICIENCY / SIZING-SCALING-DECISION, all
2026-08-03) exhaustively measured core Safe/Bold's SELECTION and SIZING axes and found
both near a ceiling. Nobody had measured the axis this tool covers: of the 5 live paper
arms (safe-2, bold-2, safe-3, risky-1, risky-3) trading off overlapping signal streams,
how many of the signals each arm was CONFIGURED to take did it mechanically drop, and why
-- a PARTICIPATION question, not a selection or sizing question.

REUSE, NOT REBUILD (repo's own C17 doctrine): this module is a thin aggregation layer over
backtest/tools/participation_cascade.py, the existing, tested (test_participation_cascade.py)
joint-gate-cascade instrument that already reconstructs every tick in
automation/state/core-decisions.jsonl and automation/state/fleet/<arm>/decisions.jsonl into
terminal-classified, run-length-encoded SIGNAL EVENTS per arm per day. This module adds:
  1. full-window aggregation (participation_cascade's own CLI is per-day / trailing-N-day)
  2. a mapping from its (category, blocker, stage) triples onto the task's own mechanism
     vocabulary (gate / min_premium_floor / sizing_deadlock / not_flat / arm_disabled /
     no_signal_from_producer / risk_cap / pdt / execution_other)
  3. real-$ aggregation from journal/trades.csv, per arm per trading day (leg-count-safe:
     trades.csv logs partial TP1/runner legs as separate rows for one entry, so summing by
     DATE rather than by ROW is the only leg-multiplicity-safe way to get a $/day rate)
  4. a growth-path day-count model (order-of-operations, never calendar dates, per J's
     standing no-timeline-guesses rule) from TODAY's live-verified equity to the ~$5,000
     flat-curve-to-scaling inflection CAPITAL-EFFICIENCY-2026-08-03.md identified

SCOPE: measurement + arithmetic only. Zero edits to any trading-path file. Read-only
against automation/state/core-decisions.jsonl, automation/state/fleet/<arm>/decisions.jsonl,
journal/trades.csv, automation/state/fleet/accounts.json. The one live write this module's
CLI performs is its own output JSON under analysis/deep-research/ -- never trading state.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
import participation_cascade as pc  # noqa: E402

ARMS: tuple[str, ...] = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")  # task scope; excludes retired safe-1
NON_SCORING_STAGES = frozenset({"NO_DATA", "NO_SIGNAL"})
SUCCESS_STAGES = frozenset({"PLACED", "FILLED"})
TRADES_CSV_ACCOUNT_ID = {  # journal/trades.csv account_id -> arm_id (task scope only)
    "safe": "safe-2", "bold": "bold-2", "safe-3": "safe-3", "risky-1": "risky-1", "risky-3": "risky-3",
}

# ---------------------------------------------------------------------------
# pure functions (unit-tested, RED-proofed -- see test_arm_participation_growth_2026_08_03.py)
# ---------------------------------------------------------------------------


def mechanism_bucket(category: str, blocker: Optional[str], stage: str) -> str:
    """Map participation_cascade.py's (category, blocker, stage) onto the task's own
    mechanism vocabulary: gate / min_premium_floor / sizing_deadlock / not_flat /
    arm_disabled / no_signal_from_producer / risk_cap / pdt / execution_other.

    `sizing_deadlock` is NOT auto-detected here (risk_gate.explain_block's `binding.deadlock`
    telemetry exists in the code -- backtest/lib/risk_gate.py -- but was found EMPTY on
    every row of both core-decisions.jsonl and every fleet arm's ledger across the full
    live window checked, 2026-08-02 -- disclosed, not silently assumed absent). `risk_cap`
    events are reported as their own bucket; a caller wanting the deadlock-specific SUBSET
    must additionally read each event's own `binding` field once it starts being populated.
    """
    b = (blocker or "").lower()
    if stage == "NO_SIGNAL":
        return "no_signal_from_producer"
    if stage == "NO_DATA":
        if b in ("signal_feed",) or "stale" in b or "unreadable" in b:
            return "producer_signal_unavailable"
        return "no_data_other"
    if b == "not_flat_rule4":
        return "not_flat"
    if b == "min_premium_floor":
        return "min_premium_floor"
    if b == "pdt":
        return "pdt"
    if b in ("risk_cap", "risk_deny_risk_cap"):
        return "risk_cap"
    if b == "quality_lock":
        return "quality_lock"
    if stage == "STRUCTURE_VETO":
        return "gate_structure_veto"
    if stage in ("GATE_BLOCK", "WINDOW_BLOCK"):
        return "gate_arm_selectivity" if b in ("arm_selectivity_gate", "direction_lock") else "gate_named"
    if stage == "STALE_TRIGGER":
        return "execution_stale_trigger"
    if stage == "PLACE_FAIL":
        return "execution_place_fail"
    if b in ("no_creds", "arm_inactive"):
        return "arm_disabled"
    return f"other_block:{b or stage.lower()}"


def days_to_target(current_equity: float, target_equity: float, dollar_per_trading_day: Optional[float]) -> Optional[float]:
    """Order-of-operations day-count, never a calendar date (J's standing rule). Pure
    arithmetic: (target - current) / rate, holding the rate constant (the flat-curve
    regime CAPITAL-EFFICIENCY-2026-08-03.md measured below ~$5K -- $/day does not itself
    depend on equity in that band, so this is NOT compounding, it is a linear runway).
    Returns:
      0.0                    if already at/above target
      None                   if the rate is <=0 (never gets there holding the rate flat --
                              the honest answer is "not on this trajectory", not a huge number)
      positive float         trading days needed at the given constant rate
    """
    if current_equity >= target_equity:
        return 0.0
    if dollar_per_trading_day is None or dollar_per_trading_day <= 0:
        return None
    return (target_equity - current_equity) / dollar_per_trading_day


def windowed_real_pnl(daily_pnl: dict[str, float], window_start: str, window_end: str) -> tuple[float, int]:
    """Sum a {date: pnl} map restricted to [window_start, window_end] (inclusive, ISO
    string comparison -- safe because journal/trades.csv dates are always YYYY-MM-DD).
    Returns (total_pnl, n_distinct_days_with_a_real_fill_in_window)."""
    in_window = {d: v for d, v in daily_pnl.items() if d and window_start <= d <= window_end}
    return round(sum(in_window.values()), 2), len(in_window)


def split_recent_vs_early(dates_sorted: list[str], daily_pnl: dict[str, float]) -> dict:
    """Split a sorted distinct-date list into an early half and a recent half (recent =
    the back half, ties go to the recent half so a lone odd-day-out is treated as more
    current information, matching this repo's own recent-N convention of favoring the
    freshest slice). Returns per-half (n_days, total, rate) plus the full-window rate --
    THREE numbers, never collapsed to one, so a caller cannot accidentally point-estimate
    off a single thin half (J's no-point-estimate stress-test rule, task step 4)."""
    n = len(dates_sorted)
    if n == 0:
        return {"full": {"n_days": 0, "total": 0.0, "rate": None},
                "early": {"n_days": 0, "total": 0.0, "rate": None},
                "recent": {"n_days": 0, "total": 0.0, "rate": None}}
    half = n - n // 2  # ceiling(n/2): the recent half gets the larger share on an odd split
    recent_dates = dates_sorted[-half:]
    early_dates = dates_sorted[:-half]
    full_total = round(sum(daily_pnl[d] for d in dates_sorted), 2)
    recent_total = round(sum(daily_pnl[d] for d in recent_dates), 2)
    early_total = round(sum(daily_pnl[d] for d in early_dates), 2) if early_dates else 0.0

    def _rate(total: float, days: list[str]) -> Optional[float]:
        return round(total / len(days), 2) if days else None

    return {
        "full": {"n_days": n, "total": full_total, "rate": _rate(full_total, dates_sorted),
                  "range": [dates_sorted[0], dates_sorted[-1]]},
        "early": {"n_days": len(early_dates), "total": early_total, "rate": _rate(early_total, early_dates),
                   "range": [early_dates[0], early_dates[-1]] if early_dates else None},
        "recent": {"n_days": len(recent_dates), "total": recent_total, "rate": _rate(recent_total, recent_dates),
                    "range": [recent_dates[0], recent_dates[-1]] if recent_dates else None},
    }


def load_real_fills_daily_pnl(trades_csv_path: Path) -> dict[str, dict[str, float]]:
    """journal/trades.csv -> {arm_id: {date: summed dollar_pnl}}. Rows whose account_id
    is not one of the 5 in-scope arms (corrupted rows from unescaped-quote overflow in the
    notes_short column, or account_id values outside task scope e.g. the retired safe-1)
    are skipped, not guessed at -- the caller gets an explicit count of what was skipped."""
    per_arm_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total_rows = 0
    unattributable = 0
    with open(trades_csv_path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            total_rows += 1
            arm = TRADES_CSV_ACCOUNT_ID.get(row.get("account_id"))
            if arm is None:
                unattributable += 1
                continue
            try:
                pnl = float(row.get("dollar_pnl") or 0)
            except (TypeError, ValueError):
                unattributable += 1
                continue
            date = row.get("date") or ""
            per_arm_daily[arm][date] += pnl
    return {"per_arm_daily": {a: dict(d) for a, d in per_arm_daily.items()},
            "total_rows": total_rows, "unattributable_rows": unattributable}


def build_full_window_events(days: list[str]) -> dict[str, list[dict]]:
    """Run participation_cascade.compute_cascade_day() over every day, tag each event
    with its date, and regroup by arm. The one non-pure function here (does file I/O via
    participation_cascade) -- kept a thin, obvious pass-through so the pure functions
    above can be tested without touching disk."""
    per_arm_events: dict[str, list[dict]] = defaultdict(list)
    day_records = []
    for d in days:
        rec = pc.compute_cascade_day(d)
        day_records.append(rec)
        for e in rec["events"]:
            e2 = dict(e)
            e2["date"] = d
            per_arm_events[e2["arm"]].append(e2)
    return {"per_arm_events": dict(per_arm_events), "day_records": day_records}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def run(*, target_equity: float = 5000.0) -> dict:
    days = pc.discover_sessions(0)
    built = build_full_window_events(days)
    per_arm_events = built["per_arm_events"]
    day_records = built["day_records"]

    fills = load_real_fills_daily_pnl(REPO / "journal" / "trades.csv")

    out: dict = {
        "generated_note": "arm_participation_growth_2026_08_03.py -- read-only, $0, reuses participation_cascade.py",
        "days_covered": {"first": days[0], "last": days[-1], "n_calendar_days": len(days)},
        "real_fills_trades_csv": {"total_rows": fills["total_rows"], "unattributable_rows": fills["unattributable_rows"]},
        "arms": {},
    }

    for arm in ARMS:
        events = per_arm_events.get(arm, [])
        arm_out: dict = {"n_events_total": len(events)}
        if events:
            active_dates = sorted({e["date"] for e in events})
            passed = [e for e in events if e["stage"] not in NON_SCORING_STAGES]
            orders = [e for e in events if e["stage"] in SUCCESS_STAGES]
            blocked = [e for e in passed if e["stage"] not in SUCCESS_STAGES]
            passed_dates = sorted({e["date"] for e in passed})
            order_dates = sorted({e["date"] for e in orders})
            signal_no_order_dates = sorted(set(passed_dates) - set(order_dates))

            mech_events: Counter = Counter()
            mech_ticks: Counter = Counter()
            mech_days: dict[str, set] = defaultdict(set)
            mech_side: dict[str, Counter] = defaultdict(Counter)
            for e in blocked:
                m = mechanism_bucket(e["category"], e["blocker"], e["stage"])
                mech_events[m] += 1
                mech_ticks[m] += e.get("n_ticks", 1)
                mech_days[m].add(e["date"])
                mech_side[m][e.get("side")] += e.get("n_ticks", 1)

            arm_out.update({
                "first_active_date": active_dates[0], "last_active_date": active_dates[-1],
                "n_days_with_any_ledger_row": len(active_dates),
                "n_passed_scoring_events": len(passed),
                "n_orders_placed_or_filled": len(orders),
                "n_days_with_passed_signal": len(passed_dates),
                "n_days_with_order": len(order_dates),
                "n_days_signal_but_zero_orders": len(signal_no_order_dates),
                "signal_but_zero_order_dates": signal_no_order_dates,
                "mechanism_breakdown_events": dict(mech_events.most_common()),
                "mechanism_breakdown_ticks": dict(mech_ticks.most_common()),
                "mechanism_breakdown_n_days": {k: len(v) for k, v in mech_days.items()},
                "mechanism_side_breakdown_ticks": {k: dict(v) for k, v in mech_side.items()},
            })

            daily_pnl = fills["per_arm_daily"].get(arm, {})
            win_pnl, win_days = windowed_real_pnl(daily_pnl, active_dates[0], active_dates[-1])
            arm_out["real_fills_in_ledger_window"] = {
                "total_pnl": win_pnl, "n_real_trading_days": win_days,
                "n_orders_ledger": len(orders),
                "pnl_per_order": round(win_pnl / len(orders), 2) if orders else None,
            }
            all_dates_with_fills = sorted(d for d in daily_pnl if d)
            arm_out["real_fills_full_history"] = {
                "n_distinct_trading_days": len(all_dates_with_fills),
                "first_date": all_dates_with_fills[0] if all_dates_with_fills else None,
                "last_date": all_dates_with_fills[-1] if all_dates_with_fills else None,
                "total_pnl": round(sum(daily_pnl.values()), 2) if daily_pnl else 0.0,
                "recency_split": split_recent_vs_early(all_dates_with_fills, daily_pnl),
            }
        out["arms"][arm] = arm_out

    # spotlight date (task's own cited 2026-07-31 anecdote)
    spotlight_date = "2026-07-31"
    spot = {}
    for rec in day_records:
        if rec["date"] == spotlight_date:
            for arm in ARMS:
                spot[arm] = rec["per_arm_funnel"].get(arm, {})
            break
    out["spotlight_2026_07_31"] = spot

    # per-day order table (full window)
    per_day_orders = []
    for rec in day_records:
        row = {"date": rec["date"]}
        for arm in ARMS:
            row[arm] = rec["per_arm_funnel"].get(arm, {}).get("orders", 0)
        row["spy_range_pct"] = rec.get("spy_range_pct")
        per_day_orders.append(row)
    out["per_day_orders"] = per_day_orders

    # growth model: verified live equities (fleet_broker.get_account, read-only, this session)
    live_equity = {
        "safe-2": 1160.24, "bold-2": 1197.52, "safe-3": 1967.81, "risky-1": 1756.87, "risky-3": 2121.61,
    }
    growth = {}
    for arm in ARMS:
        eq = live_equity[arm]
        arm_data = out["arms"].get(arm, {})
        recency = arm_data.get("real_fills_full_history", {}).get("recency_split", {})
        rates = {
            "full_real": recency.get("full", {}).get("rate"),
            "recent_half_real": recency.get("recent", {}).get("rate"),
            "early_half_real": recency.get("early", {}).get("rate"),
        }
        days_est = {k: days_to_target(eq, target_equity, v) for k, v in rates.items()}
        growth[arm] = {"live_equity_verified": eq, "target_equity": target_equity,
                        "dollar_needed": round(target_equity - eq, 2),
                        "rates_dollar_per_trading_day": rates,
                        "trading_days_to_target": days_est}
    out["growth_model_regime1_flat_curve"] = growth

    return out


def main() -> int:
    out = run()
    out_dir = REPO / "analysis" / "deep-research"
    out_json = out_dir / "ARM-PARTICIPATION-AND-GROWTH-2026-08-03.json"
    out_json.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[arm-participation-growth] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
