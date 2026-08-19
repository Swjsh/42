#!/usr/bin/env python
"""journal_calendar.py -- REPORTING-ONLY trading journal calendar for Project Gamma.

J'S ASK (2026-08-19, verbatim intent): "a trading journal visualization, like, calendars.
We can start seeing the days at a glance. We should have this information already." He's
right the data exists -- this turns it into something readable in two seconds, not another
JSON dump.

Arms nothing. Places no orders. Edits no params*.json. Pure read + render.

DATA SOURCES (confirmed against the real files this session, schemas NOT invented):
  - automation/state/fleet/fills_fifo.py#mine_real_arm_fills(arm_id) -- THE ONE FIFO
    round-trip reconstructor (C14: don't drift a second copy). real_pnl is exact per its
    own docstring even for multi-leg exits; only exit_premium goes None on a >1-leg exit.
  - automation/state/fleet/accounts.json -- arm roster, DERIVED (status=='active' AND
    account_number startswith 'PA'), never hardcoded. Currently resolves to the same 5
    arms as CLAUDE.md's "5 active real-fills arms": safe-2, bold-2, safe-3, risky-1, risky-3.
  - setup/scripts/cost_model.py#fee_breakdown -- real empirical Alpaca regulatory fees.
    Key is fee_total_ex_cat (CAT is added separately, once per arm per trading day, at
    aggregation time here -- mirrors cost_model.py's own build_report()).
  - automation/state/core-decisions.jsonl (safe-2/bold-2, core arms only, account field is
    the short form "safe"/"bold") + automation/state/fleet/{arm}/decisions.jsonl (safe-3/
    risky-1/risky-3) -- per-tick engine reasoning, mined ONLY for the "setup" name of each
    ENTER decision that actually got PLACED, matched to a closed round trip by
    (arm, date, symbol, nearest ts_et within a tolerance window). If nothing matches within
    tolerance the trade is shown as "setup: unmatched" -- never guessed, never blank-as-zero.

HONESTY / HEALTH CHECKS (2026-08-19 real evidence, this session):
  - Investigated the two 2026-08-19 round trips fills_fifo flags "2-leg exit" before
    trusting either one:
      * bold-2 SPY260819C00771000 12:36-12:41: raw ledger shows the SAME order_id filled
        in two pieces (qty=2 @0.54, qty=3 @0.54) -- both at the SAME price. real_pnl=0.0 is
        a genuine scratch, not a bug; NOT the day's biggest winner.
      * risky-1 SPY260819C00770000 11:50-12:22: raw ledger shows a REAL TP1(3@1.65) +
        runner(2@1.82) split under two DIFFERENT order_ids at two DIFFERENT prices.
        real_pnl=299.0 IS the day's biggest winner and is verified correct by hand:
        (3*1.65 + 2*1.82 - 5*1.12) * 100 = 299.00.
    In both cases fills_fifo's real_pnl was already exact. This script independently
    reconstructs exit legs from the raw ledger anyway (reconstruct_exit_legs) and cross-
    checks the result against fills_fifo's real_pnl for every multi-leg exit, per the
    standing "reconstruct from raw fills, don't drop, don't treat as $0" instruction --
    belt-and-suspenders, not a replacement for the FIFO reconstructor.
  - Book total for 2026-08-19 (safe-2 + bold-2 + safe-3 + risky-1 + risky-3) verified
    against J's stated cross-check (-114 +90 +186 +254 -150 = $266): matches exactly.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/journal_calendar.py            # writes calendar.html + calendar-data.json
    backtest/.venv/Scripts/python.exe setup/scripts/journal_calendar.py --json     # tiny mode: writes ONLY calendar-data.json, skips HTML render
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402
import fills_fifo  # noqa: E402
import cost_model  # noqa: E402

ACCOUNTS_JSON = REPO / "automation" / "state" / "fleet" / "accounts.json"
FILLS_LEDGER_PATH = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DECISIONS_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
OUT_HTML = REPO / "analysis" / "journal" / "calendar.html"
OUT_JSON = REPO / "analysis" / "journal" / "calendar-data.json"

# Per MAP.md ACT section: heartbeat_core.py (core-decisions.jsonl) covers ONLY the core
# arms safe-2/bold-2, logged there under the short account names "safe"/"bold". Fleet arms
# (safe-3, risky-1, risky-3) log to their own automation/state/fleet/{arm}/decisions.jsonl.
CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
FLEET_ARMS = {"safe-3", "risky-1", "risky-3"}
CAT_FEE_PER_ARM_DAY = cost_model.CAT_FEE_PER_ARM_DAY

CORRELATION_DISCLOSURE = (
    "BOOK is a CORRELATED ROLLUP, not 5 independent samples. All 5 active arms trade the "
    "SAME shared signal (automation/state/fleet/build_shared_signal.py) and differ only in "
    "sizing/gates/exit shape -- r=0.846, 95.7% sign agreement (analysis/deep-research/"
    "LEVER-CORRELATION-2026-08-06.md). Read per-arm first; treat any BOOK number as one "
    "book's economics under 5 risk profiles, never as 5x the statistical confidence of one arm."
)
FEE_DISCLOSURE = (
    "Fees are REAL regulatory pass-through (OCC/ORF/FINRA-TAF/SEC-31/CAT) that Alpaca "
    "charges on paper AND live -- this repo's fills pipeline never ingested them before "
    "setup/scripts/cost_model.py (2026-08-18). Gross = the P&L this repo has always shown. "
    "Net = gross minus those real fees (fee_total_ex_cat + CAT), from the SAME empirical "
    "rates. Exit-side bid/ask spread cost is a separate, still-UNVERIFIED question "
    "(cost_model.py's spread scenarios) and is intentionally NOT folded into net here."
)

_TZ_SUFFIX_RE = re.compile(r"[+-]\d{2}:\d{2}$")


# ============================================================================
# Roster
# ============================================================================

def load_roster(accounts_path: Path = ACCOUNTS_JSON) -> list[str]:
    """Active, real-money-shaped arms -- DERIVED from accounts.json, never hardcoded.
    status=='active' AND account_number startswith 'PA' (paper-account prefix; excludes
    the two futures arms which use a different broker account number, and excludes
    safe-1 which is 'retired')."""
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    canonical_order = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
    ids = [a["id"] for a in data.get("arms", [])
           if a.get("status") == "active" and str(a.get("account_number", "")).startswith("PA")]
    ordered = [a for a in canonical_order if a in ids]
    ordered += sorted(a for a in ids if a not in canonical_order)
    return ordered


# ============================================================================
# Raw ledger + multi-leg exit reconstruction (independent cross-check)
# ============================================================================

def load_raw_ledger_rows(ledger_path: Path = FILLS_LEDGER_PATH) -> list[dict]:
    if not ledger_path.exists():
        return []
    rows = []
    with ledger_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def reconstruct_exit_legs(arm: str, symbol: str, entry_ts_et: str, exit_ts_et: str,
                           raw_rows: list[dict]) -> dict:
    """Pure. Independently rebuilds the SELL side of one closed round trip straight from
    raw fills-ledger rows -- sum(sells) is well-defined even when fills_fifo's own
    exit_premium goes None on a >1-leg exit. The [entry_ts_et, exit_ts_et] window is safe
    against same-day re-entries on the same symbol: fills_fifo only ever advances
    entry_ts_et past ALL of a prior round trip's legs when open_qty returns to zero, so
    this window can never straddle two round trips."""
    legs = [r for r in raw_rows
            if r.get("arm") == arm and r.get("symbol") == symbol
            and r.get("attribution") == "engine" and r.get("side") == "sell"
            and entry_ts_et <= (r.get("ts_et") or "") <= exit_ts_et]
    legs = sorted(legs, key=lambda r: r["ts_et"])
    sell_qty = sum(float(l["qty"]) for l in legs)
    sell_notional = sum(float(l["qty"]) * float(l["price"]) for l in legs)
    avg_exit_premium = round(sell_notional / sell_qty, 4) if sell_qty else None
    return {
        "legs": [{"qty": l["qty"], "price": l["price"], "ts_et": l["ts_et"]} for l in legs],
        "avg_exit_premium": avg_exit_premium,
        "sell_qty": sell_qty,
        "sell_notional": sell_notional,
    }


# ============================================================================
# Setup-name enrichment (best-effort, never fabricated)
# ============================================================================

def _parse_ts(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(_TZ_SUFFIX_RE.sub("", s))
    except ValueError:
        return None


def build_setup_index(roster: list[str],
                       core_path: Path = CORE_DECISIONS_PATH,
                       fleet_dir: Path = FLEET_DIR) -> dict[tuple[str, str, str], list[tuple[str, str | None]]]:
    """(arm, date, symbol) -> sorted [(ts_et, setup_name), ...] for every ENTER decision
    that actually PLACED an order. Streamed with a cheap substring pre-filter before
    json.loads (core-decisions.jsonl runs ~66MB / ~30K lines)."""
    idx: dict[tuple[str, str, str], list[tuple[str, str | None]]] = {}

    core_arms_wanted = {acct: arm for acct, arm in CORE_ACCOUNT_TO_ARM.items() if arm in roster}
    if core_arms_wanted and core_path.exists():
        with core_path.open(encoding="utf-8") as fh:
            for line in fh:
                if '"status": "PLACED"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                verdict = row.get("verdict") or ""
                if not verdict.startswith("ENTER_"):
                    continue
                arm = core_arms_wanted.get(row.get("account"))
                if not arm:
                    continue
                exec_ = row.get("exec") or {}
                if exec_.get("status") != "PLACED":
                    continue
                symbol = exec_.get("symbol")
                ts = row.get("ts_et")
                if not symbol or not ts:
                    continue
                idx.setdefault((arm, ts[:10], symbol), []).append((ts, row.get("setup")))

    for arm in roster:
        if arm not in FLEET_ARMS:
            continue
        p = fleet_dir / arm / "decisions.jsonl"
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if '"placed": true' not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("arm_id") != arm:
                    continue
                action = row.get("action") or ""
                if not action.startswith("ENTER_"):
                    continue
                placement = row.get("placement") or {}
                if not placement.get("placed"):
                    continue
                symbol = placement.get("symbol")
                ts = row.get("ts_et")
                if not symbol or not ts:
                    continue
                idx.setdefault((arm, ts[:10], symbol), []).append((ts, row.get("setup_name")))

    for key in idx:
        idx[key].sort()
    return idx


def lookup_setup(idx: dict, arm: str, date: str, symbol: str, entry_ts_et: str,
                  tolerance_seconds: float = 180.0) -> tuple[str | None, bool]:
    """Nearest ENTER decision (by |delta ts|) within tolerance_seconds. Returns
    (setup_name, matched). Never fabricates -- unmatched returns (None, False), rendered
    in the UI as 'setup: unmatched', never left blank."""
    candidates = idx.get((arm, date, symbol))
    if not candidates:
        return None, False
    entry_dt = _parse_ts(entry_ts_et)
    if entry_dt is None:
        return None, False
    best_setup, best_delta = None, None
    for ts, setup in candidates:
        dt = _parse_ts(ts)
        if dt is None:
            continue
        delta = abs((dt - entry_dt).total_seconds())
        if delta <= tolerance_seconds and (best_delta is None or delta < best_delta):
            best_setup, best_delta = setup, delta
    if best_delta is None:
        return None, False
    return best_setup, True


# ============================================================================
# Per-trip enrichment: strike parse, multi-leg reconstruction, fees, setup
# ============================================================================

def _parse_strike(symbol: str) -> float | None:
    try:
        return int(symbol[-8:]) / 1000.0
    except (ValueError, IndexError):
        return None


def enrich_trip(trip: dict, arm: str, raw_rows: list[dict], setup_idx: dict) -> dict:
    """Pure given a fills_fifo round-trip dict + the raw ledger rows + the setup index.
    Adds: arm, strike, multi_leg, legs, exit_premium_avg, pnl_cross_check_ok, setup,
    setup_matched, fees_total_ex_cat, pnl_gross, pnl_net_ex_cat."""
    t = dict(trip)
    t["arm"] = arm
    t["strike"] = _parse_strike(t["symbol"])

    if t.get("exit_premium") is None:
        recon = reconstruct_exit_legs(arm, t["symbol"], t["entry_ts_et"], t["exit_ts_et"], raw_rows)
        t["multi_leg"] = True
        t["legs"] = recon["legs"]
        t["exit_premium_avg"] = recon["avg_exit_premium"]
        entry_premium = t.get("entry_premium") or 0.0
        qty = t.get("qty") or 0
        recon_pnl = round((recon["sell_notional"] - entry_premium * qty) * 100.0, 2)
        t["pnl_cross_check_ok"] = abs(recon_pnl - (t.get("real_pnl") or 0.0)) < 0.01
    else:
        t["multi_leg"] = False
        t["legs"] = []
        t["exit_premium_avg"] = t["exit_premium"]
        t["pnl_cross_check_ok"] = True

    setup, matched = lookup_setup(setup_idx, arm, t["date"], t["symbol"], t["entry_ts_et"])
    t["setup"] = setup
    t["setup_matched"] = matched

    fb = cost_model.fee_breakdown(t)
    t["fees_total_ex_cat"] = fb["fee_total_ex_cat"]
    t["pnl_gross"] = t.get("real_pnl") or 0.0
    t["pnl_net_ex_cat"] = round(t["pnl_gross"] - t["fees_total_ex_cat"], 2)
    return t


def build_enriched_trips(roster: list[str], ledger_path: Path = FILLS_LEDGER_PATH,
                          core_path: Path = CORE_DECISIONS_PATH,
                          fleet_dir: Path = FLEET_DIR) -> dict[str, list[dict]]:
    raw_rows = load_raw_ledger_rows(ledger_path)
    setup_idx = build_setup_index(roster, core_path=core_path, fleet_dir=fleet_dir)
    out: dict[str, list[dict]] = {}
    for arm in roster:
        trips = fills_fifo.mine_real_arm_fills(arm, ledger_path=ledger_path)
        out[arm] = [enrich_trip(t, arm, raw_rows, setup_idx) for t in trips]
    return out


# ============================================================================
# Aggregation -- pure, testable given already-enriched trip lists
# ============================================================================

def aggregate_view(trips: list[dict]) -> dict[str, dict]:
    """[trip, ...] -> {date: day_dict}. A date with zero trades is simply ABSENT --
    never present with a $0 entry."""
    by_date: dict[str, list[dict]] = {}
    for t in trips:
        by_date.setdefault(t["date"], []).append(t)

    days: dict[str, dict] = {}
    for date, day_trips in sorted(by_date.items()):
        arms_today = {t["arm"] for t in day_trips}
        cat_fee = round(CAT_FEE_PER_ARM_DAY * len(arms_today), 2)
        fees_ex_cat = round(sum(t["fees_total_ex_cat"] for t in day_trips), 2)
        fees_total = round(fees_ex_cat + cat_fee, 2)
        pnl_gross = round(sum(t["pnl_gross"] for t in day_trips), 2)
        pnl_net = round(pnl_gross - fees_total, 2)

        wins_g = sum(1 for t in day_trips if t["pnl_gross"] > 0)
        losses_g = sum(1 for t in day_trips if t["pnl_gross"] < 0)
        wins_n = sum(1 for t in day_trips if t["pnl_net_ex_cat"] > 0)
        losses_n = sum(1 for t in day_trips if t["pnl_net_ex_cat"] < 0)

        days[date] = {
            "date": date, "pnl_gross": pnl_gross, "pnl_net": pnl_net,
            "fees_total": fees_total, "fees_cat": cat_fee,
            "trade_count": len(day_trips),
            "wins_gross": wins_g, "losses_gross": losses_g,
            "scratches_gross": len(day_trips) - wins_g - losses_g,
            "wins_net": wins_n, "losses_net": losses_n,
            "scratches_net": len(day_trips) - wins_n - losses_n,
            "trades": day_trips,
        }
    return days


def compute_summary(days: dict[str, dict]) -> dict:
    dates_sorted = sorted(days.keys())
    trading_days = len(dates_sorted)
    total_trades = sum(d["trade_count"] for d in days.values())
    if not trading_days:
        return {
            "total_pnl_gross": 0.0, "total_pnl_net": 0.0, "total_fees": 0.0,
            "trading_days": 0, "total_trades": 0,
            "win_rate_by_day_gross": None, "win_rate_by_day_net": None,
            "win_rate_by_trade_gross": None, "win_rate_by_trade_net": None,
            "best_day_gross": None, "worst_day_gross": None,
            "best_day_net": None, "worst_day_net": None,
            "current_streak_gross": {"type": "none", "length": 0},
            "current_streak_net": {"type": "none", "length": 0},
        }

    total_pnl_gross = round(sum(d["pnl_gross"] for d in days.values()), 2)
    total_pnl_net = round(sum(d["pnl_net"] for d in days.values()), 2)
    total_fees = round(sum(d["fees_total"] for d in days.values()), 2)

    def win_rate_by_day(metric: str) -> float:
        wins = sum(1 for d in days.values() if d[metric] > 0)
        return round(wins / trading_days, 4)

    def win_rate_by_trade(win_key: str) -> float | None:
        wins = sum(d[win_key] for d in days.values())
        return round(wins / total_trades, 4) if total_trades else None

    def best_worst(metric: str) -> tuple[dict, dict]:
        best_date = max(dates_sorted, key=lambda d: days[d][metric])
        worst_date = min(dates_sorted, key=lambda d: days[d][metric])
        return ({"date": best_date, "pnl": days[best_date][metric]},
                {"date": worst_date, "pnl": days[worst_date][metric]})

    def streak(metric: str) -> dict:
        last = dates_sorted[-1]
        sign = 1 if days[last][metric] > 0 else (-1 if days[last][metric] < 0 else 0)
        length, since = 0, last
        for d in reversed(dates_sorted):
            s = 1 if days[d][metric] > 0 else (-1 if days[d][metric] < 0 else 0)
            if s != sign:
                break
            length += 1
            since = d
        return {"type": {1: "winning", -1: "losing", 0: "scratch"}[sign],
                "length": length, "since_date": since, "through_date": last}

    best_g, worst_g = best_worst("pnl_gross")
    best_n, worst_n = best_worst("pnl_net")

    return {
        "total_pnl_gross": total_pnl_gross, "total_pnl_net": total_pnl_net,
        "total_fees": total_fees, "trading_days": trading_days, "total_trades": total_trades,
        "win_rate_by_day_gross": win_rate_by_day("pnl_gross"),
        "win_rate_by_day_net": win_rate_by_day("pnl_net"),
        "win_rate_by_trade_gross": win_rate_by_trade("wins_gross"),
        "win_rate_by_trade_net": win_rate_by_trade("wins_net"),
        "best_day_gross": best_g, "worst_day_gross": worst_g,
        "best_day_net": best_n, "worst_day_net": worst_n,
        "current_streak_gross": streak("pnl_gross"),
        "current_streak_net": streak("pnl_net"),
    }


def build_payload(roster: list[str], ledger_path: Path = FILLS_LEDGER_PATH,
                   core_path: Path = CORE_DECISIONS_PATH,
                   fleet_dir: Path = FLEET_DIR) -> dict:
    enriched_by_arm = build_enriched_trips(roster, ledger_path=ledger_path,
                                            core_path=core_path, fleet_dir=fleet_dir)

    views: dict[str, dict] = {}
    all_dates: list[str] = []
    row_count = 0
    for arm in roster:
        trips = enriched_by_arm[arm]
        row_count += len(trips)
        days = aggregate_view(trips)
        all_dates.extend(days.keys())
        views[arm] = {"days": days, "summary": compute_summary(days)}

    book_trips = [t for arm in roster for t in enriched_by_arm[arm]]
    book_days = aggregate_view(book_trips)
    views["BOOK"] = {"days": book_days, "summary": compute_summary(book_days)}

    date_range = [min(all_dates), max(all_dates)] if all_dates else [None, None]

    return {
        "_doc": ("Trading journal calendar -- setup/scripts/journal_calendar.py. "
                 "REPORTING ONLY: arms nothing, places no orders, edits no params*.json."),
        "generated_et": et_now().isoformat(),
        "date_range": date_range,
        "row_count": row_count,
        "roster": roster,
        "correlation_disclosure": CORRELATION_DISCLOSURE,
        "fee_disclosure": FEE_DISCLOSURE,
        "views": views,
    }


# ============================================================================
# HTML render -- self-contained, no CDN, dark-friendly, verdict-first
# ============================================================================

_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gamma Journal Calendar</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #0b0d12; --panel: #12151c; --panel2: #171b24; --border: #262b38;
    --text: #e7e9ee; --muted: #8b93a7; --green: #33c17a; --green-dim: #1c6a44;
    --red: #ef5350; --red-dim: #7a2426; --amber: #e0a63a; --accent: #5b8def;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--text); margin: 0; padding: 24px;
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    font-size: 15px; line-height: 1.4;
  }
  h1 { font-size: 22px; margin: 0 0 2px 0; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
  .controls {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    margin-bottom: 16px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px 12px;
  }
  .controls label { color: var(--muted); font-size: 12px; margin-right: 4px; }
  select, button {
    background: var(--panel2); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; font-size: 14px; cursor: pointer;
  }
  button.toggle-on { background: var(--accent); color: #fff; border-color: var(--accent); }
  .month-nav { display: flex; align-items: center; gap: 8px; margin-left: auto; }
  .month-label { min-width: 150px; text-align: center; font-weight: 600; }
  .disclosure {
    font-size: 12px; color: var(--amber); background: #2a220e; border: 1px solid #4a3a12;
    border-radius: 8px; padding: 8px 12px; margin-bottom: 14px; display: none;
  }
  .disclosure.show { display: block; }
  .summary-strip {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 10px; margin-bottom: 18px;
  }
  .stat {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 10px 12px;
  }
  .stat .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
  .stat .value { font-size: 22px; font-weight: 700; margin-top: 2px; }
  .stat .value.pos { color: var(--green); }
  .stat .value.neg { color: var(--red); }
  .stat .sub2 { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .cal-grid {
    display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px;
  }
  .cal-dow { color: var(--muted); font-size: 11px; text-align: center; padding-bottom: 2px; }
  .cal-cell {
    min-height: 84px; border-radius: 8px; border: 1px solid var(--border);
    padding: 6px 8px; background: var(--panel); position: relative;
  }
  .cal-cell.empty { background: transparent; border-color: transparent; }
  .cal-cell.has-trades { cursor: pointer; }
  .cal-cell.has-trades:hover { border-color: var(--accent); }
  .cal-cell .daynum { font-size: 11px; color: var(--muted); }
  .cal-cell .pnl { font-size: 17px; font-weight: 700; margin-top: 4px; }
  .cal-cell .pnl.pos { color: var(--green); }
  .cal-cell .pnl.neg { color: var(--red); }
  .cal-cell .pnl.zero { color: var(--muted); }
  .cal-cell .meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
  .cal-cell .unknown { font-size: 11px; color: var(--amber); margin-top: 6px; }
  .modal-backdrop {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6);
    align-items: center; justify-content: center; z-index: 50; padding: 20px;
  }
  .modal-backdrop.show { display: flex; }
  .modal {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    max-width: 900px; width: 100%; max-height: 85vh; overflow: auto; padding: 18px 20px;
  }
  .modal h2 { margin: 0 0 4px 0; font-size: 18px; }
  .modal .close { position: absolute; }
  .modal-head { display: flex; justify-content: space-between; align-items: flex-start; }
  .modal-head button { font-size: 13px; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; }
  td.pos { color: var(--green); font-weight: 600; }
  td.neg { color: var(--red); font-weight: 600; }
  .badge {
    display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 4px;
    background: var(--panel2); color: var(--muted); border: 1px solid var(--border);
    margin-left: 4px;
  }
  .badge.multileg { color: var(--amber); border-color: var(--amber); }
  .badge.unmatched { color: var(--muted); }
  footer { margin-top: 24px; font-size: 11px; color: var(--muted); }
</style>
</head>
<body>
  <h1>Gamma Trading Journal -- Calendar</h1>
  <div class="sub" id="header-sub"></div>

  <div class="controls">
    <label>Arm</label>
    <select id="arm-select"></select>
    <button id="fee-toggle">Net of fees: OFF</button>
    <div class="month-nav">
      <button id="prev-month">&larr;</button>
      <div class="month-label" id="month-label"></div>
      <button id="next-month">&rarr;</button>
    </div>
  </div>

  <div class="disclosure" id="correlation-note"></div>

  <div class="summary-strip" id="summary-strip"></div>

  <div class="cal-grid" id="cal-dow"></div>
  <div class="cal-grid" id="cal-grid" style="margin-top:6px;"></div>

  <footer id="footer"></footer>

  <div class="modal-backdrop" id="modal-backdrop">
    <div class="modal">
      <div class="modal-head">
        <h2 id="modal-title"></h2>
        <button id="modal-close">Close</button>
      </div>
      <div id="modal-sub" class="sub"></div>
      <table id="modal-table">
        <thead><tr>
          <th>Arm</th><th>Symbol</th><th>Strike/Side</th><th>Qty</th>
          <th>Entry</th><th>Exit</th><th>P&amp;L (gross)</th><th>Fees</th><th>P&amp;L (net)</th><th>Setup</th>
        </tr></thead>
        <tbody id="modal-tbody"></tbody>
      </table>
    </div>
  </div>

<script>
const DATA = __DATA_JSON__;

const state = { arm: "BOOK", netFees: false, monthIdx: 0, months: [] };

function fmtMoney(n) {
  if (n === null || n === undefined) return "N/A";
  const sign = n < 0 ? "-" : "";
  return sign + "$" + Math.abs(n).toFixed(2);
}
function pnlClass(n) { return n > 0 ? "pos" : (n < 0 ? "neg" : "zero"); }
function pct(n) { return (n === null || n === undefined) ? "N/A" : (n * 100).toFixed(1) + "%"; }

function allDatesForView(view) {
  return Object.keys(DATA.views[view].days).sort();
}

function computeMonths() {
  const dates = allDatesForView(state.arm);
  const set = new Set(dates.map(d => d.slice(0, 7)));
  const months = Array.from(set).sort();
  state.months = months;
  state.monthIdx = months.length ? months.length - 1 : 0;
}

function initControls() {
  const sel = document.getElementById("arm-select");
  ["BOOK", ...DATA.roster].forEach(a => {
    const opt = document.createElement("option");
    opt.value = a; opt.textContent = a === "BOOK" ? "BOOK (all 5 arms, correlated)" : a;
    sel.appendChild(opt);
  });
  sel.value = state.arm;
  sel.addEventListener("change", () => { state.arm = sel.value; computeMonths(); render(); });

  document.getElementById("fee-toggle").addEventListener("click", (e) => {
    state.netFees = !state.netFees;
    e.target.textContent = "Net of fees: " + (state.netFees ? "ON" : "OFF");
    e.target.classList.toggle("toggle-on", state.netFees);
    render();
  });
  document.getElementById("prev-month").addEventListener("click", () => {
    if (state.monthIdx > 0) { state.monthIdx--; render(); }
  });
  document.getElementById("next-month").addEventListener("click", () => {
    if (state.monthIdx < state.months.length - 1) { state.monthIdx++; render(); }
  });
  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("modal-backdrop").classList.remove("show");
  });
  document.getElementById("modal-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "modal-backdrop") e.target.classList.remove("show");
  });
}

function renderHeader() {
  document.getElementById("header-sub").textContent =
    "Data: " + DATA.date_range[0] + " to " + DATA.date_range[1] +
    "  |  " + DATA.row_count + " closed round trips  |  generated " + DATA.generated_et;
  document.getElementById("footer").innerHTML =
    "<div>" + DATA.fee_disclosure + "</div>";
}

function renderCorrelationNote() {
  const el = document.getElementById("correlation-note");
  if (state.arm === "BOOK") {
    el.textContent = DATA.correlation_disclosure;
    el.classList.add("show");
  } else {
    el.classList.remove("show");
  }
}

function renderSummary() {
  const s = DATA.views[state.arm].summary;
  const net = state.netFees;
  const strip = document.getElementById("summary-strip");
  const totalPnl = net ? s.total_pnl_net : s.total_pnl_gross;
  const wrDay = net ? s.win_rate_by_day_net : s.win_rate_by_day_gross;
  const wrTrade = net ? s.win_rate_by_trade_net : s.win_rate_by_trade_gross;
  const best = net ? s.best_day_net : s.best_day_gross;
  const worst = net ? s.worst_day_net : s.worst_day_gross;
  const streak = net ? s.current_streak_net : s.current_streak_gross;

  function stat(label, valueHtml, sub) {
    return '<div class="stat"><div class="label">' + label + '</div>' +
      '<div class="value">' + valueHtml + '</div>' +
      (sub ? '<div class="sub2">' + sub + '</div>' : '') + '</div>';
  }

  let html = "";
  html += '<div class="stat"><div class="label">Total P&amp;L (' + (net ? "net" : "gross") + ')</div>' +
    '<div class="value ' + pnlClass(totalPnl) + '">' + fmtMoney(totalPnl) + '</div>' +
    '<div class="sub2">' + s.total_trades + ' trades / ' + s.trading_days + ' days</div></div>';
  html += stat("Win rate (by day)", pct(wrDay));
  html += stat("Win rate (by trade)", pct(wrTrade));
  html += stat("Best day", best ? (best.date + " " + fmtMoney(best.pnl)) : "N/A");
  html += stat("Worst day", worst ? (worst.date + " " + fmtMoney(worst.pnl)) : "N/A");
  html += stat("Current streak", streak.length + " " + streak.type,
    streak.since_date ? (streak.since_date + " to " + streak.through_date) : "");
  html += stat("Total fees paid", fmtMoney(s.total_fees));
  strip.innerHTML = html;
}

function renderDow() {
  const dow = document.getElementById("cal-dow");
  dow.innerHTML = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    .map(d => '<div class="cal-dow">' + d + '</div>').join("");
}

function renderGrid() {
  const grid = document.getElementById("cal-grid");
  grid.innerHTML = "";
  if (!state.months.length) {
    document.getElementById("month-label").textContent = "No trading days";
    return;
  }
  const monthKey = state.months[state.monthIdx];
  const parts = monthKey.split("-").map(Number);
  const y = parts[0], m = parts[1];
  const first = new Date(Date.UTC(y, m - 1, 1));
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const startDow = first.getUTCDay();
  const monthName = first.toLocaleString("en-US", { month: "long", timeZone: "UTC" });
  document.getElementById("month-label").textContent = monthName + " " + y;

  const days = DATA.views[state.arm].days;
  const net = state.netFees;

  for (let i = 0; i < startDow; i++) {
    grid.insertAdjacentHTML("beforeend", '<div class="cal-cell empty"></div>');
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = monthKey + "-" + String(day).padStart(2, "0");
    const rec = days[dateStr];
    if (!rec) {
      grid.insertAdjacentHTML("beforeend",
        '<div class="cal-cell"><div class="daynum">' + day + '</div></div>');
      continue;
    }
    const pnl = net ? rec.pnl_net : rec.pnl_gross;
    const wins = net ? rec.wins_net : rec.wins_gross;
    const losses = net ? rec.losses_net : rec.losses_gross;
    const cell = document.createElement("div");
    cell.className = "cal-cell has-trades";
    const intensity = Math.min(1, Math.abs(pnl) / 300);
    const bg = pnl > 0
      ? "rgba(51,193,122," + (0.10 + 0.35 * intensity) + ")"
      : (pnl < 0 ? "rgba(239,83,80," + (0.10 + 0.35 * intensity) + ")" : "transparent");
    cell.style.background = bg;
    cell.innerHTML =
      '<div class="daynum">' + day + '</div>' +
      '<div class="pnl ' + pnlClass(pnl) + '">' + fmtMoney(pnl) + '</div>' +
      '<div class="meta">' + rec.trade_count + ' trades &middot; ' + wins + 'W/' + losses + 'L</div>';
    cell.addEventListener("click", () => openModal(dateStr, rec));
    grid.appendChild(cell);
  }
}

function openModal(dateStr, rec) {
  document.getElementById("modal-title").textContent = dateStr;
  document.getElementById("modal-sub").textContent =
    "Arm: " + state.arm + "  |  gross " + fmtMoney(rec.pnl_gross) +
    "  |  net " + fmtMoney(rec.pnl_net) + "  |  fees " + fmtMoney(rec.fees_total) +
    " (incl. $" + rec.fees_cat.toFixed(2) + " CAT)";
  const tbody = document.getElementById("modal-tbody");
  tbody.innerHTML = "";
  rec.trades.slice().sort((a, b) => a.entry_ts_et.localeCompare(b.entry_ts_et)).forEach(t => {
    const exitLabel = t.multi_leg
      ? fmtMoney(t.exit_premium_avg) + ' <span class="badge multileg">' + t.legs.length + '-leg avg</span>'
      : fmtMoney(t.exit_premium);
    const setupLabel = t.setup_matched
      ? t.setup
      : '<span class="badge unmatched">unmatched</span>';
    const pnlG = t.pnl_gross, pnlN = t.pnl_net_ex_cat;
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + t.arm + '</td>' +
      '<td>' + t.symbol + '</td>' +
      '<td>' + (t.strike != null ? t.strike : "N/A") + t.side + '</td>' +
      '<td>' + t.qty + '</td>' +
      '<td>' + fmtMoney(t.entry_premium) + '<br><span class="sub2">' + t.entry_ts_et.slice(11, 19) + '</span></td>' +
      '<td>' + exitLabel + '<br><span class="sub2">' + t.exit_ts_et.slice(11, 19) + '</span></td>' +
      '<td class="' + pnlClass(pnlG) + '">' + fmtMoney(pnlG) + '</td>' +
      '<td>' + fmtMoney(t.fees_total_ex_cat) + '</td>' +
      '<td class="' + pnlClass(pnlN) + '">' + fmtMoney(pnlN) + '</td>' +
      '<td>' + setupLabel + '</td>';
    tbody.appendChild(tr);
  });
  document.getElementById("modal-backdrop").classList.add("show");
}

function render() {
  renderCorrelationNote();
  renderSummary();
  renderGrid();
}

initControls();
renderHeader();
renderDow();
computeMonths();
render();
</script>
</body>
</html>
"""


def render_html(payload: dict) -> str:
    data_json = json.dumps(payload, default=str)
    # Guard against a literal "</script>" inside the embedded JSON breaking the page.
    data_json = data_json.replace("</script>", "<\\/script>")
    return _HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


# ============================================================================
# CLI
# ============================================================================

def _print_human(payload: dict) -> None:
    print(f"date range: {payload['date_range'][0]} .. {payload['date_range'][1]}")
    print(f"row count (closed round trips, all {len(payload['roster'])} arms): {payload['row_count']}")
    print()
    hdr = f"{'arm':<10}{'days':>6}{'trades':>8}{'gross':>12}{'fees':>9}{'net':>12}{'wr-day':>9}{'wr-trade':>10}"
    print(hdr)
    print("-" * len(hdr))
    for arm in payload["roster"] + ["BOOK"]:
        s = payload["views"][arm]["summary"]
        wr_d = f"{s['win_rate_by_day_gross']*100:.0f}%" if s["win_rate_by_day_gross"] is not None else "N/A"
        wr_t = f"{s['win_rate_by_trade_gross']*100:.0f}%" if s["win_rate_by_trade_gross"] is not None else "N/A"
        print(f"{arm:<10}{s['trading_days']:>6}{s['total_trades']:>8}"
              f"{s['total_pnl_gross']:>12,.2f}{s['total_fees']:>9,.2f}{s['total_pnl_net']:>12,.2f}"
              f"{wr_d:>9}{wr_t:>10}")
    print()
    print("BOOK is a correlated rollup (r=0.846) -- not 5 independent samples.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true",
                     help="tiny mode: write ONLY analysis/journal/calendar-data.json, skip HTML render")
    args = ap.parse_args()

    roster = load_roster()
    payload = build_payload(roster)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"wrote -> {OUT_JSON.relative_to(REPO)}")

    if not args.json:
        html = render_html(payload)
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text(html, encoding="utf-8")
        print(f"wrote -> {OUT_HTML.relative_to(REPO)}")

    print()
    _print_human(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
