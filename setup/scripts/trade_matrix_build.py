#!/usr/bin/env python
"""trade_matrix_build.py -- THE CANONICAL TRADE TABLE for Project Gamma's real-fills book.

ONE row per CLOSED round trip, across all 5 active real-fills arms (safe-2, bold-2, safe-3,
risky-1, risky-3), across all history in automation/state/fills-ledger.jsonl. Every downstream
right-tail study (stop-width counterfactuals, strike-tier dollar-vs-percent, exit-timing
replays) reads THIS file instead of re-deriving its own join and re-inventing its own bugs.

Output: analysis/recommendations/trade-matrix.json

WHAT ONE ROW CARRIES
  entry   : arm, date, entry_ts_et, symbol, strike, side, moneyness vs SPY at entry, qty,
            entry_premium, notional, arm equity at entry, pct_of_equity
  engine  : bull/bear score, ribbon, ribbon spread cents, VIX, HTF, triggers fired, quality
            tier, setup name, minutes since open, filters that had just released
  exit    : exit_ts_et, exit_premium (QTY-WEIGHTED AVERAGE across legs), n_exit_legs,
            hold_minutes, exit reason (stage + text, per leg)
  outcome : real_pnl gross, fee_total_ex_cat, CAT allocation, real_pnl net
  path    : MAE/MFE in premium and %, time-to-MAE/MFE, first-touch minute for a frozen grid
            of stop and target levels, plus the full 1-minute OHLC premium series

=============================== THE TWO TRAPS ==================================
TRAP 1 -- MULTI-LEG EXITS. fills_fifo.mine_real_arm_fills returns exit_premium=None whenever
>1 sell leg resolved a position (TP1 + runner). Its real_pnl is still exact, but a consumer
that reads exit_premium and drops None rows silently deletes real trades -- and on 2026-08-19
two of fourteen round trips were split exits, one of them the day's biggest winner (+$299).
This module reconstructs the legs itself and ALWAYS computes exit_premium as the qty-weighted
average sell price. It never returns None, never drops, never zeroes. Every row is then
CROSS-CHECKED field-by-field against fills_fifo's own output (count, qty, gross P&L); any
disagreement is a hard, itemized failure in the report, not a swallowed exception.

TRAP 2 -- BROKER IS TRUTH (C11). A ledger is a copy. `--verify` re-pulls FILL activities
straight from each broker account and reconciles leg count + FIFO P&L against this table.
If the broker disagrees, that is a FINDING and the verdict is UNRECONCILED. If the broker is
unreachable, the verdict is UNRECONCILED (reason recorded) -- never a silent pass.

NO LOOK-AHEAD (C6). Every engine-state field is read from the decision row that PRODUCED the
order (joined on the broker order id, not on time), i.e. information that existed at the
instant the order was sent. Path fields are explicitly labelled as outcome data: they exist
to evaluate counterfactual exits, and the entry-bar-inclusive vs entry-bar-exclusive MAE/MFE
variants are BOTH emitted so a downstream stop study cannot accidentally fire a stop on a
print that happened before the fill landed.

COSTS. Fees come from setup/scripts/cost_model.py (fee_breakdown -> fee_total_ex_cat: OCC,
ORF, TAF, SEC). CAT is a flat $0.01 per arm per trading day, so it cannot be attributed to a
single round trip -- it is allocated evenly across that arm-day's round trips into a separate
field (`fee_cat_allocated`) and both nets are reported. Exit-side spread realism
(setup/scripts/exit_fill_realism.py: paper exits land ~0.13 of the traded range better than a
real market sell) is NOT applied here -- it is a separate, non-fee adjustment; this table
stays a fee-only net so the two effects never get silently blended.

SCOPE / INDEPENDENCE WARNING (carried into the JSON header so no consumer can miss it): the 5
arms trade ONE shared signal. 303 round trips are NOT 303 independent decisions. Any
significance claim must be made on the ~60-90 independent signal-level events, not the row
count of this file.

safe-1 is EXCLUDED: retired 2026-07-11, and its broker account (PA3POKNV46VG) was reassigned
to safe-2 -- including it would double-count one account under two labels.

USAGE
  python setup/scripts/trade_matrix_build.py                # build (fetches missing OPRA bars)
  python setup/scripts/trade_matrix_build.py --no-fetch     # build from cached bars only
  python setup/scripts/trade_matrix_build.py --verify       # verify + broker reconciliation
  python setup/scripts/trade_matrix_build.py --verify --no-broker   # offline verify
Guard: backtest/tests/test_trade_matrix_build.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- paths (C9: anchor to __file__)
REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import cost_model  # noqa: E402
import fills_fifo  # noqa: E402

STATE = REPO / "automation" / "state"
FLEET = STATE / "fleet"
FILLS_LEDGER = STATE / "fills-ledger.jsonl"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
ACCOUNTS_JSON = FLEET / "accounts.json"
OPRA_CACHE = REPO / "backtest" / "data" / "opra_1m_cache"
OUT_JSON = REPO / "analysis" / "recommendations" / "trade-matrix.json"
MCP_JSON = REPO / ".mcp.json"

OPTIONS_BARS_URL = "https://data.alpaca.markets/v1beta1/options/bars"
_ET = ZoneInfo("America/New_York")

# ---------------------------------------------------------------- frozen config
ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
EXCLUDED_ARMS = {"safe-1": "retired 2026-07-11; its account PA3POKNV46VG was reassigned to "
                           "safe-2 -- including it double-counts one account under two labels"}
CORE_ARMS = {"safe-2": "safe", "bold-2": "bold"}   # arm -> core-decisions `account` value
FLEET_ARMS = ("safe-3", "risky-1", "risky-3")      # -> automation/state/fleet/<arm>/decisions.jsonl

BROKER_BACKFILL_SINCE = "2026-06-25T00:00:00Z"     # same anchor broker_fills.py uses
MARKET_STATE_TOL_MIN = 5.0                          # nearest-core-tick fallback tolerance
FILTERS_RELEASED_LOOKBACK_MIN = 15.0                # "which filters just released" scan window
MARKET_OPEN_ET = dt.time(9, 30)
PATH_BAR_CAP = 420                                  # 1-min bars retained per row (RTH is 390)

# Pre-registered counterfactual grid, frozen BEFORE any result was looked at. Stops are read
# against the bar LOW, targets against the bar HIGH, both as a fraction of entry premium.
STOP_GRID_PCT = (-0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50)
TARGET_GRID_PCT = (0.20, 0.30, 0.50, 0.75, 1.00, 1.50, 2.00)

# A "filter release" = an engine action that BLOCKED an entry shortly before this one landed.
BLOCKING_ACTION_PREFIXES = ("SKIP_", "RISK_DENY_", "VETOED_", "NOT_FLAT", "PLACE_FAIL")


# ================================================================ small helpers
def _f(x: Any) -> Optional[float]:
    """float() that returns None instead of fabricating a 0.0 for missing/garbage input."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_et(ts: Any) -> Optional[dt.datetime]:
    """Parse an ET timestamp that may or may not carry an offset -> naive ET datetime."""
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return d.replace(tzinfo=None) if d.tzinfo is not None else d


def occ_strike(symbol: str) -> Optional[float]:
    """Strike from an OCC symbol: last 8 chars are strike * 1000."""
    try:
        return int(symbol[-8:]) / 1000.0
    except (ValueError, TypeError, IndexError):
        return None


def moneyness_label(side: str, strike: Optional[float],
                    spy: Optional[float]) -> tuple[Optional[str], Optional[int]]:
    """(label, signed offset) vs the $1 SPY strike grid. OTM positive, ITM negative.
    Returns (None, None) when SPY at entry is unknown -- never a fabricated 'ATM'."""
    if spy is None or strike is None:
        return None, None
    off = int(round(strike - round(spy)))      # +ve = strike above spot
    n = off if side == "C" else -off           # +ve = further OTM for this side
    if n == 0:
        return "ATM", 0
    return (f"OTM+{n}" if n > 0 else f"ITM-{abs(n)}"), n


def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ================================================================ 1. FIFO reconstruction
def _ledger_rows(arm: str, ledger_path: Path) -> list[dict]:
    return [r for r in _iter_jsonl(ledger_path)
            if r.get("arm") == arm and r.get("attribution") == "engine"]


def reconstruct_round_trips(arm: str, ledger_path: Path = FILLS_LEDGER) -> list[dict]:
    """FIFO-reconstruct CLOSED round trips for `arm` from the RAW ledger, keeping every leg.

    Same accumulator shape as fills_fifo.mine_real_arm_fills -- including the load-bearing
    flush-and-reset the instant open_qty returns to zero, so a same-day re-entry on the same
    OCC symbol is a SEPARATE round trip and never a blended fictional average -- but this
    version keeps the individual buy/sell legs so exit_premium can be a real qty-weighted
    average on multi-leg exits instead of None (TRAP 1).
    """
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for r in _ledger_rows(arm, ledger_path):
        by_symbol[r["symbol"]].append(r)

    out: list[dict] = []
    for symbol, legs in by_symbol.items():
        legs = sorted(legs, key=lambda r: r["ts_et"])
        side = symbol[-9]
        if side not in ("C", "P"):
            continue  # malformed symbol -- skip rather than fabricate a side
        open_qty = 0.0
        buy_legs: list[dict] = []
        sell_legs: list[dict] = []
        for leg in legs:
            s = leg.get("side")
            q, px = _f(leg.get("qty")), _f(leg.get("price"))
            if q is None or px is None:
                continue
            if s == "buy":
                if open_qty <= 1e-9:
                    buy_legs, sell_legs = [], []          # fresh round trip
                open_qty += q
                buy_legs.append(leg)
            elif s == "sell":
                if open_qty <= 1e-9:
                    continue                              # sell with nothing open -- anomaly
                open_qty -= q
                sell_legs.append(leg)
                if abs(open_qty) > 1e-6:
                    continue                              # partial exit, still open
                buy_notional = sum(_f(b["qty"]) * _f(b["price"]) for b in buy_legs)
                buy_qty = sum(_f(b["qty"]) for b in buy_legs)
                sell_notional = sum(_f(x["qty"]) * _f(x["price"]) for x in sell_legs)
                sell_qty = sum(_f(x["qty"]) for x in sell_legs)
                out.append({
                    "arm": arm,
                    "date": buy_legs[0]["date_et"],
                    "symbol": symbol,
                    "side": side,
                    "entry_ts_et": buy_legs[0]["ts_et"],
                    "exit_ts_et": sell_legs[-1]["ts_et"],
                    "qty": int(round(buy_qty)),
                    "n_entry_legs": len(buy_legs),
                    "n_exit_legs": len(sell_legs),
                    "entry_premium": round(buy_notional / buy_qty, 4) if buy_qty else None,
                    # ALWAYS a real number: qty-weighted average across ALL sell legs.
                    "exit_premium": round(sell_notional / sell_qty, 4) if sell_qty else None,
                    "real_pnl": round((sell_notional - buy_notional) * 100.0, 2),
                    "entry_order_ids": [b.get("order_id") for b in buy_legs],
                    "exit_order_ids": [x.get("order_id") for x in sell_legs],
                    "exit_legs": [{"ts_et": x["ts_et"], "qty": int(round(_f(x["qty"]))),
                                   "price": _f(x["price"]), "order_id": x.get("order_id")}
                                  for x in sell_legs],
                })
        # leftover open_qty > 0 is a STILL-OPEN position -- deliberately not flushed.
    return sorted(out, key=lambda r: (r["entry_ts_et"], r["symbol"]))


def crosscheck_against_fills_fifo(arm: str, rows: list[dict],
                                  ledger_path: Path = FILLS_LEDGER) -> list[str]:
    """Row-for-row cross-check vs the repo's standing reconstructor. Returns a list of
    human-readable disagreements (empty == agreement). Never raises, never hides."""
    ref = fills_fifo.mine_real_arm_fills(arm, ledger_path)
    problems: list[str] = []
    if len(ref) != len(rows):
        problems.append(f"{arm}: row count {len(rows)} != fills_fifo {len(ref)}")
    mine = {(r["symbol"], r["entry_ts_et"]): r for r in rows}
    theirs = {(r["symbol"], r["entry_ts_et"]): r for r in ref}
    for k in sorted(set(mine) | set(theirs)):
        a, b = mine.get(k), theirs.get(k)
        if a is None:
            problems.append(f"{arm}: {k} present in fills_fifo, MISSING here")
            continue
        if b is None:
            problems.append(f"{arm}: {k} present here, MISSING in fills_fifo")
            continue
        if abs(a["real_pnl"] - b["real_pnl"]) > 0.005:
            problems.append(f"{arm}: {k} gross {a['real_pnl']} != fills_fifo {b['real_pnl']}")
        if a["qty"] != b["qty"]:
            problems.append(f"{arm}: {k} qty {a['qty']} != fills_fifo {b['qty']}")
        if a["exit_ts_et"] != b["exit_ts_et"]:
            problems.append(f"{arm}: {k} exit_ts {a['exit_ts_et']} != fills_fifo {b['exit_ts_et']}")
    return problems


# ================================================================ 2. engine-state joins
def _tier_from_reason(reason: Optional[str]) -> Optional[str]:
    if not reason:
        return None
    i = reason.find("tier ")
    if i < 0:
        return None
    tok = reason[i + 5:].strip().split()
    return tok[0].strip("()").strip() if tok else None


def load_core_rows() -> dict[str, list[dict]]:
    """core-decisions.jsonl grouped by account ('safe'/'bold'), each sorted by ts."""
    by_acct: dict[str, list[dict]] = defaultdict(list)
    for r in _iter_jsonl(CORE_DECISIONS):
        acct, ts = r.get("account"), _parse_et(r.get("ts_et"))
        if not acct or ts is None:
            continue
        r["_ts"] = ts
        by_acct[acct].append(r)
    for acct in by_acct:
        by_acct[acct].sort(key=lambda r: r["_ts"])
    return by_acct


def _market_state(row: dict) -> dict:
    return {
        "spy": _f(row.get("spy")),
        "ribbon": row.get("ribbon"),
        "ribbon_spread_cents": _f(row.get("spread_cents")),
        "vix": _f(row.get("vix")),
        "htf_15m": row.get("htf_15m"),
        "bull_score": _f(row.get("bull_score")),
        "bear_score": _f(row.get("bear_score")),
    }


def build_indexes(core_by_acct: dict[str, list[dict]]) -> dict[str, Any]:
    """Order-id -> decision context, for BOTH execution paths.

    entry_by_order : the decision row that PRODUCED the buy order (no look-ahead -- this is
                     state as of order submission).
    exit_by_order  : the exit_pass action that produced a sell order (stage + reason).
    core_by_tick   : core_tick_id -> core market state. This is how a fleet arm inherits the
                     shared signal's market context, which its own decisions.jsonl lacks.
    """
    entry_by_order: dict[str, dict] = {}
    exit_by_order: dict[str, dict] = {}
    core_by_tick: dict[str, dict] = {}

    def _record_exit_pass(rows: Iterable[dict], src: str) -> None:
        for r in rows:
            for ep in (r.get("exit_pass") or []):
                if not isinstance(ep, dict):
                    continue
                for act in (ep.get("actions") or []):
                    if not isinstance(act, dict):
                        continue
                    oid = (act.get("broker") or {}).get("id")
                    if not oid:
                        continue
                    exit_by_order[oid] = {
                        "exit_kind": act.get("kind"),
                        "exit_stage": act.get("stage"),
                        "exit_reason": act.get("reason"),
                        "exit_best_premium": _f(ep.get("best_premium")),
                        "exit_worst_premium": _f(ep.get("worst_premium")),
                        "exit_tp1_filled": ep.get("tp1_filled"),
                        "source": src,
                    }

    # ---- core path (safe-2 / bold-2 via heartbeat_core)
    for acct, rows in core_by_acct.items():
        for r in rows:
            tick = r.get("core_tick_id")
            if tick and tick not in core_by_tick:
                core_by_tick[tick] = _market_state(r)
            execs = [r.get("exec")] + [ee.get("exec") for ee in (r.get("extra_exec") or [])
                                       if isinstance(ee, dict)]
            for exec_ in execs:
                if not isinstance(exec_, dict):
                    continue
                oid = (exec_.get("broker") or {}).get("id")
                if not oid:
                    continue
                tl = _f(exec_.get("trigger_level"))
                entry_by_order[oid] = {
                    "setup": exec_.get("setup") or r.get("setup"),
                    "quality_tier": exec_.get("quality_tier") or _tier_from_reason(r.get("reason")),
                    "triggers": r.get("triggers") or [],
                    "shadow_triggers_fired": r.get("shadow_triggers_fired") or [],
                    "trigger_level": tl if tl is not None else _f(r.get("trigger_level_exact")),
                    "equity_at_entry": _f(exec_.get("equity")),
                    "planned_tp": _f(exec_.get("tp")),
                    "planned_stop": _f(exec_.get("stop")),
                    "stop_mode": exec_.get("stop_mode"),
                    "nbbo_at_entry": exec_.get("nbbo"),
                    "decision_ts_et": r.get("ts_et"),
                    "decision_account": acct,
                    "core_tick_id": tick,
                    "market": _market_state(r),
                    "market_state_source": "core-decisions:own-row",
                    "engine_state_source": "core-decisions:exec.broker.id",
                }
        _record_exit_pass(rows, "core-decisions")

    # ---- fleet_rest path (safe-3 / risky-1 / risky-3)
    for arm in FLEET_ARMS:
        arm_rows = list(_iter_jsonl(FLEET / arm / "decisions.jsonl"))
        for r in arm_rows:
            pl = r.get("placement") or {}
            oid = (pl.get("broker") or {}).get("id")
            if not oid:
                continue
            tick = r.get("core_tick_id")
            market = dict(core_by_tick.get(tick) or {})
            tl = _f(r.get("trigger_level"))
            entry_by_order[oid] = {
                "setup": r.get("setup_name"),
                "quality_tier": r.get("quality"),
                "triggers": r.get("triggers") or [],
                "shadow_triggers_fired": [],
                "trigger_level": tl if tl is not None else _f(pl.get("trigger_level")),
                "equity_at_entry": _f(r.get("equity")),
                "planned_tp": _f(pl.get("tp")),
                "planned_stop": _f(pl.get("stop")),
                "stop_mode": pl.get("stop_mode"),
                "nbbo_at_entry": None,
                "decision_ts_et": r.get("ts_et"),
                "decision_account": arm,
                "core_tick_id": tick,
                "risk_code": r.get("risk_code"),
                "market": market,
                "market_state_source": ("core-decisions:core_tick_id" if market
                                        else "MISSING:no core_tick_id match"),
                "engine_state_source": f"fleet/{arm}/decisions.jsonl:placement.broker.id",
            }
        _record_exit_pass(arm_rows, f"fleet/{arm}")

    return {"entry_by_order": entry_by_order, "exit_by_order": exit_by_order,
            "core_by_tick": core_by_tick}


def nearest_core_state(core_by_acct: dict[str, list[dict]], acct: str, ts: dt.datetime,
                       tol_min: float = MARKET_STATE_TOL_MIN) -> Optional[dict]:
    """Last core-decisions row for `acct` at or before `ts` (never after -- no look-ahead)."""
    best = None
    for r in core_by_acct.get(acct) or []:
        if r["_ts"] > ts:
            break
        best = r
    if best is None:
        return None
    if (ts - best["_ts"]).total_seconds() / 60.0 > tol_min:
        return None
    return _market_state(best)


def filters_released_before(core_by_acct: dict[str, list[dict]], acct: str, ts: dt.datetime,
                            lookback_min: float = FILTERS_RELEASED_LOOKBACK_MIN) -> list[dict]:
    """Blocking engine actions on this account in the `lookback_min` BEFORE the entry -- the
    gates that were holding the trade back and had just stopped firing. Strictly
    backward-looking; decidable at the entry instant."""
    lo = ts - dt.timedelta(minutes=lookback_min)
    hits: dict[str, dict] = {}
    for r in core_by_acct.get(acct) or []:
        if r["_ts"] < lo:
            continue
        if r["_ts"] >= ts:
            break
        action = str(r.get("action") or "")
        if not action.startswith(BLOCKING_ACTION_PREFIXES):
            continue
        h = hits.setdefault(action, {"action": action, "count": 0, "last_minutes_before": None})
        h["count"] += 1
        h["last_minutes_before"] = round((ts - r["_ts"]).total_seconds() / 60.0, 2)
    return sorted(hits.values(), key=lambda h: h["last_minutes_before"])


# ================================================================ 3. OPRA 1-minute path
def _data_creds() -> Optional[tuple[str, str]]:
    """Market-data key: env first, else the project-root .mcp.json `alpaca` server env block.
    READ-ONLY market data -- this module never places an order."""
    k = os.environ.get("ALPACA_API_KEY")
    s = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if k and s:
        return k, s
    if not MCP_JSON.exists():
        return None
    try:
        cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    env = (cfg.get("mcpServers", {}).get("alpaca", {}) or {}).get("env", {}) or {}
    k = env.get("ALPACA_API_KEY")
    s = env.get("ALPACA_SECRET_KEY") or env.get("ALPACA_API_SECRET")
    return (k, s) if k and s else None


def cache_path(symbol: str, date: str) -> Path:
    return OPRA_CACHE / f"{symbol}_{date}.csv"


def load_cached_bars(symbol: str, date: str) -> Optional[list[dict]]:
    """Cached 1-min bars -> [{ts(naive ET), o,h,l,c}] sorted, or None if not cached.
    Cache schema is the pre-existing shared one: t,o,h,l,c,v with t in UTC."""
    p = cache_path(symbol, date)
    if not p.exists():
        return None
    rows: list[dict] = []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            t = r.get("t")
            if not t:
                continue
            try:
                ts = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is not None:
                ts = ts.astimezone(_ET).replace(tzinfo=None)
            o, h, lo, c = _f(r.get("o")), _f(r.get("h")), _f(r.get("l")), _f(r.get("c"))
            if None in (o, h, lo, c):
                continue
            rows.append({"ts": ts, "o": o, "h": h, "l": lo, "c": c})
    rows.sort(key=lambda r: r["ts"])
    return rows


def fetch_and_cache_bars(symbol: str, date: str, creds: tuple[str, str],
                         timeout: float = 25.0) -> Optional[list[dict]]:
    """Fetch 1-min OPRA bars for one 0DTE contract and write the shared cache.
    Returns None on any transport/auth failure -- LOUD, the caller records the miss."""
    key, secret = creds
    params = {"symbols": symbol, "timeframe": "1Min",
              "start": f"{date}T12:00:00Z", "end": f"{date}T21:00:00Z", "limit": 10000}
    base = f"{OPTIONS_BARS_URL}?{urllib.parse.urlencode(params)}"
    bars: list[dict] = []
    page = None
    for _ in range(20):
        url = base + (f"&page_token={urllib.parse.quote(page)}" if page else "")
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key,
                                                   "APCA-API-SECRET-KEY": secret})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ConnectionError, json.JSONDecodeError, OSError) as exc:
            print(f"[trade_matrix] OPRA fetch FAILED {symbol} {date}: {exc}", file=sys.stderr)
            return None
        bars.extend((payload.get("bars", {}) or {}).get(symbol, []) or [])
        page = payload.get("next_page_token")
        if not page:
            break
    OPRA_CACHE.mkdir(parents=True, exist_ok=True)
    with cache_path(symbol, date).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for b in bars:
            w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)])
    return load_cached_bars(symbol, date)


def path_metrics(bars: list[dict], entry_ts: dt.datetime, exit_ts: dt.datetime,
                 entry_premium: float) -> dict:
    """MAE/MFE + counterfactual first-touch grid over the HELD window.

    Window = bars whose minute lies in [floor(entry_ts) .. floor(exit_ts)], inclusive. The
    entry bar is a judgement call, so BOTH variants ship: the primary includes it (a stop CAN
    fire in the same minute the fill landed), and *_excl_entry_bar excludes it (a stop CANNOT
    fire on a print that printed before the fill). A downstream stop study must choose
    explicitly rather than inherit an unlabelled default.
    """
    e0 = entry_ts.replace(second=0, microsecond=0)
    x0 = exit_ts.replace(second=0, microsecond=0)
    win = [b for b in bars if e0 <= b["ts"] <= x0]
    if not win:
        return {"path_bars": 0, "path_status": "NO_BARS_IN_WINDOW"}

    def _extremes(seq: list[dict]) -> dict:
        if not seq:
            return {}
        lo = min(seq, key=lambda b: b["l"])
        hi = max(seq, key=lambda b: b["h"])
        return {
            "mae_premium": round(lo["l"] - entry_premium, 4),
            "mae_pct": round((lo["l"] - entry_premium) / entry_premium, 6),
            "mae_minutes": round((lo["ts"] - e0).total_seconds() / 60.0, 1),
            "mfe_premium": round(hi["h"] - entry_premium, 4),
            "mfe_pct": round((hi["h"] - entry_premium) / entry_premium, 6),
            "mfe_minutes": round((hi["ts"] - e0).total_seconds() / 60.0, 1),
        }

    out: dict[str, Any] = {"path_bars": len(win), "path_status": "OK",
                           "path_first_bar_et": win[0]["ts"].isoformat(),
                           "path_last_bar_et": win[-1]["ts"].isoformat()}
    out.update(_extremes(win))
    for k, v in _extremes(win[1:]).items():
        out[f"{k}_excl_entry_bar"] = v

    stops, targets = {}, {}
    for pct in STOP_GRID_PCT:
        lvl = entry_premium * (1.0 + pct)
        hit = next((b for b in win if b["l"] <= lvl), None)
        stops[str(int(round(pct * 100)))] = (round((hit["ts"] - e0).total_seconds() / 60.0, 1)
                                             if hit else None)
    for pct in TARGET_GRID_PCT:
        lvl = entry_premium * (1.0 + pct)
        hit = next((b for b in win if b["h"] >= lvl), None)
        targets[f"+{int(round(pct * 100))}"] = (round((hit["ts"] - e0).total_seconds() / 60.0, 1)
                                                if hit else None)
    out["stop_first_touch_min_pct"] = stops
    out["target_first_touch_min_pct"] = targets
    out["path_truncated"] = len(win) > PATH_BAR_CAP
    out["path"] = [[round((b["ts"] - e0).total_seconds() / 60.0, 1), b["o"], b["h"], b["l"], b["c"]]
                   for b in win[:PATH_BAR_CAP]]
    return out


# ================================================================ 4. build
def build(fetch: bool = True) -> dict:
    core_by_acct = load_core_rows()
    idx = build_indexes(core_by_acct)
    entry_by_order = idx["entry_by_order"]
    exit_by_order = idx["exit_by_order"]

    rows: list[dict] = []
    crosscheck_problems: list[str] = []
    for arm in ARMS:
        trips = reconstruct_round_trips(arm)
        crosscheck_problems.extend(crosscheck_against_fills_fifo(arm, trips))
        rows.extend(trips)
    rows.sort(key=lambda r: (r["entry_ts_et"], r["arm"], r["symbol"]))

    # CAT is a flat $0.01 per arm per trading day -- it cannot belong to one round trip.
    per_arm_day: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        per_arm_day[(r["arm"], r["date"])] += 1

    creds = _data_creds() if fetch else None
    if fetch and creds is None:
        print("[trade_matrix] no market-data credentials resolved -- path fields will be "
              "cache-only (recorded in the output, not hidden)", file=sys.stderr)

    bar_cache: dict[tuple[str, str], Optional[list[dict]]] = {}
    fetch_failures: list[str] = []

    def bars_for(symbol: str, date: str) -> Optional[list[dict]]:
        k = (symbol, date)
        if k in bar_cache:
            return bar_cache[k]
        b = load_cached_bars(symbol, date)
        if b is None and creds is not None:
            b = fetch_and_cache_bars(symbol, date, creds)
            if b is None:
                fetch_failures.append(f"{symbol}_{date}")
        bar_cache[k] = b
        return b

    out_rows: list[dict] = []
    for r in rows:
        entry_ts, exit_ts = _parse_et(r["entry_ts_et"]), _parse_et(r["exit_ts_et"])
        strike = occ_strike(r["symbol"])
        entry_premium = r["entry_premium"]

        # ---- engine state: join on the ORDER ID this round trip's buy leg produced
        ctx: dict = {}
        for oid in r["entry_order_ids"]:
            if oid and oid in entry_by_order:
                ctx = entry_by_order[oid]
                break
        market = dict(ctx.get("market") or {})
        market_src = ctx.get("market_state_source")
        if market.get("spy") is None:
            acct = CORE_ARMS.get(r["arm"], "safe")
            fallback = nearest_core_state(core_by_acct, acct, entry_ts) if entry_ts else None
            if fallback:
                market, market_src = fallback, f"core-decisions:nearest<={MARKET_STATE_TOL_MIN}min({acct})"
            elif not market:
                market_src = "MISSING"

        spy_at_entry = market.get("spy")
        mny_label, mny_n = moneyness_label(r["side"], strike, spy_at_entry)
        equity = ctx.get("equity_at_entry")
        notional = round(entry_premium * r["qty"] * 100.0, 2) if entry_premium is not None else None
        pct_equity = round(notional / equity, 6) if (notional is not None and equity) else None
        mins_since_open = None
        if entry_ts is not None:
            open_dt = dt.datetime.combine(entry_ts.date(), MARKET_OPEN_ET)
            mins_since_open = round((entry_ts - open_dt).total_seconds() / 60.0, 1)

        # ---- exit reasons, per leg (a split exit has TWO: TP1 then runner)
        exit_reasons = []
        for leg in r["exit_legs"]:
            info = exit_by_order.get(leg["order_id"] or "")
            exit_reasons.append({
                "ts_et": leg["ts_et"], "qty": leg["qty"], "price": leg["price"],
                "stage": (info or {}).get("exit_stage"),
                "kind": (info or {}).get("exit_kind"),
                "reason": (info or {}).get("exit_reason"),
                "matched": info is not None,
            })
        primary_exit = next((e for e in exit_reasons if e["matched"]), None) or {}
        # An exit with NO matching exit_pass action is not "no reason" -- it is an exit placed
        # by a path that writes no decision row. automation/state/fleet/fleet_eod.py calls
        # fleet_broker.close_all_spy_options() and only PRINTS the result, so the EOD flatten
        # leaves no order id and no reason anywhere in the repo. Labelled, never silently null.
        exit_reason_source = ("decision-ledger:exit_pass.actions" if primary_exit
                              else "UNLOGGED:no exit_pass action for this sell order id "
                                   "(fleet_eod.close_all_spy_options writes no decision row)")

        fees = cost_model.fee_breakdown({"qty": r["qty"], "entry_premium": entry_premium,
                                         "real_pnl": r["real_pnl"]})
        cat_alloc = round(cost_model.CAT_FEE_PER_ARM_DAY / per_arm_day[(r["arm"], r["date"])], 6)
        net = round(r["real_pnl"] - fees["fee_total_ex_cat"], 4)

        row: dict[str, Any] = {
            # ---- identity
            "arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "side": r["side"],
            "strike": strike,
            # ---- entry
            "entry_ts_et": r["entry_ts_et"], "minutes_since_open": mins_since_open,
            "qty": r["qty"], "n_entry_legs": r["n_entry_legs"],
            "entry_premium": entry_premium, "notional": notional,
            "equity_at_entry": equity, "pct_of_equity": pct_equity,
            "spy_at_entry": spy_at_entry,
            "moneyness": mny_label, "moneyness_n": mny_n,
            # ---- engine state at entry (order-id joined; no look-ahead)
            "setup": ctx.get("setup"), "quality_tier": ctx.get("quality_tier"),
            "triggers": ctx.get("triggers"),
            "shadow_triggers_fired": ctx.get("shadow_triggers_fired"),
            "trigger_level": ctx.get("trigger_level"),
            "ribbon": market.get("ribbon"),
            "ribbon_spread_cents": market.get("ribbon_spread_cents"),
            "vix": market.get("vix"), "htf_15m": market.get("htf_15m"),
            "bull_score": market.get("bull_score"), "bear_score": market.get("bear_score"),
            "planned_tp": ctx.get("planned_tp"), "planned_stop": ctx.get("planned_stop"),
            "stop_mode": ctx.get("stop_mode"), "nbbo_at_entry": ctx.get("nbbo_at_entry"),
            "filters_released_before_entry": (
                filters_released_before(core_by_acct, CORE_ARMS.get(r["arm"], "safe"), entry_ts)
                if entry_ts else []),
            "engine_state_source": ctx.get("engine_state_source", "MISSING:order-id unmatched"),
            "market_state_source": market_src,
            # ---- exit
            "exit_ts_et": r["exit_ts_et"], "exit_premium": r["exit_premium"],
            "n_exit_legs": r["n_exit_legs"],
            "hold_minutes": (round((exit_ts - entry_ts).total_seconds() / 60.0, 2)
                             if (entry_ts and exit_ts) else None),
            "exit_stage": primary_exit.get("stage"), "exit_reason": primary_exit.get("reason"),
            "exit_reason_source": exit_reason_source, "exit_legs": exit_reasons,
            # ---- outcome
            "real_pnl_gross": r["real_pnl"],
            "fee_total_ex_cat": fees["fee_total_ex_cat"],
            "fee_breakdown": {k: v for k, v in fees.items()
                              if k not in ("qty", "spread_adjustment_conservative")},
            "fee_cat_allocated": cat_alloc,
            "real_pnl_net": net,
            "real_pnl_net_incl_cat": round(net - cat_alloc, 4),
            "return_on_premium_gross": (round(r["real_pnl"] / notional, 6) if notional else None),
            "is_winner_gross": r["real_pnl"] > 0,
            "is_winner_net": net > 0,
            # ---- provenance
            "entry_order_ids": r["entry_order_ids"], "exit_order_ids": r["exit_order_ids"],
        }

        bars = bars_for(r["symbol"], r["date"])
        if bars and entry_ts and exit_ts and entry_premium:
            row.update(path_metrics(bars, entry_ts, exit_ts, entry_premium))
        else:
            row["path_bars"] = 0
            row["path_status"] = "NO_OPTION_BARS" if not bars else "NO_TIMESTAMPS"
        out_rows.append(row)

    # ---------------- totals + coverage
    gross = round(sum(r["real_pnl_gross"] for r in out_rows), 2)
    fee_tot = round(sum(r["fee_total_ex_cat"] for r in out_rows), 2)
    cat_tot = round(sum(r["fee_cat_allocated"] for r in out_rows), 2)
    net = round(sum(r["real_pnl_net"] for r in out_rows), 2)
    dates = sorted({r["date"] for r in out_rows})
    path_ok = sum(1 for r in out_rows if r.get("path_status") == "OK")

    per_arm = {}
    for arm in ARMS:
        sub = [r for r in out_rows if r["arm"] == arm]
        per_arm[arm] = {
            "n": len(sub),
            "gross": round(sum(r["real_pnl_gross"] for r in sub), 2),
            "net": round(sum(r["real_pnl_net"] for r in sub), 2),
            "wins_gross": sum(1 for r in sub if r["is_winner_gross"]),
            "wins_net": sum(1 for r in sub if r["is_winner_net"]),
            "multi_leg_exits": sum(1 for r in sub if r["n_exit_legs"] > 1),
            "path_covered": sum(1 for r in sub if r.get("path_status") == "OK"),
            "trading_days": len({r["date"] for r in sub}),
        }

    return {
        "_doc": "CANONICAL trade table -- one row per CLOSED round trip, 5 active real-fills "
                "arms, all history. Built by setup/scripts/trade_matrix_build.py.",
        "_independence_warning": "The 5 arms trade ONE shared signal (r=0.846, 95.7% sign "
                                 "agreement). These rows are NOT independent observations -- "
                                 "roughly 60-90 independent signal-level decisions underlie "
                                 "them. Never quote the row count as an independent sample size.",
        "_cost_note": "real_pnl_net = gross - fee_total_ex_cat (OCC+ORF+TAF+SEC, per "
                      "setup/scripts/cost_model.py). CAT ($0.01/arm/day) cannot be attributed "
                      "to a single trip and is carried separately in fee_cat_allocated. "
                      "Exit-side spread realism (exit_fill_realism.py) is NOT applied here.",
        "_lookahead_note": "Engine-state fields are joined on the broker ORDER ID of the buy "
                           "leg -- the decision row that produced the order. Path fields are "
                           "outcome data; MAE/MFE ship in both entry-bar-inclusive and "
                           "entry-bar-exclusive form so a stop study must choose explicitly.",
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "excluded_arms": EXCLUDED_ARMS,
        "row_count": len(out_rows),
        "date_range": [dates[0], dates[-1]] if dates else [None, None],
        "trading_days": len(dates),
        "per_arm": per_arm,
        "totals": {"gross": gross, "fees_ex_cat": fee_tot, "cat_allocated": cat_tot,
                   "net": net, "net_incl_cat": round(net - cat_tot, 2)},
        "path_coverage": {"rows_with_option_bars": path_ok,
                          "rows_without_option_bars": len(out_rows) - path_ok,
                          "fetch_failures": fetch_failures},
        "engine_state_coverage": {
            "order_id_matched": sum(1 for r in out_rows
                                    if not str(r["engine_state_source"]).startswith("MISSING")),
            "unmatched": sum(1 for r in out_rows
                             if str(r["engine_state_source"]).startswith("MISSING")),
            "market_state_missing": sum(
                1 for r in out_rows if str(r.get("market_state_source") or "").startswith("MISSING")),
            "exit_reason_matched": sum(1 for r in out_rows if r.get("exit_stage")),
        },
        "crosscheck_vs_fills_fifo": {
            "status": "AGREE" if not crosscheck_problems else "DISAGREE",
            "problems": crosscheck_problems,
        },
        "known_gaps": {
            "exits_with_no_logged_reason": [
                {"arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                 "exit_ts_et": r["exit_ts_et"], "real_pnl_gross": r["real_pnl_gross"]}
                for r in out_rows if not r.get("exit_stage")],
            "exits_with_no_logged_reason_note":
                "fleet_eod.py force-flattens via fleet_broker.close_all_spy_options() and only "
                "PRINTS the result -- it writes no decision row, so these exits have no order id "
                "and no reason recorded anywhere in the repo. Reported, not imputed.",
            "rows_without_option_bars": [
                {"arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                 "entry_ts_et": r["entry_ts_et"], "exit_ts_et": r["exit_ts_et"],
                 "path_status": r.get("path_status")}
                for r in out_rows if r.get("path_status") != "OK"],
            "rows_without_option_bars_note":
                "NO_BARS_IN_WINDOW means OPRA printed no trade in any minute the position was "
                "held (sub-2-minute holds inside a print gap). The contract has bars that day; "
                "the held window does not. MAE/MFE are omitted, never imputed from adjacent bars.",
        },
        "stop_grid_pct": list(STOP_GRID_PCT),
        "target_grid_pct": list(TARGET_GRID_PCT),
        "rows": out_rows,
    }


# ================================================================ 5. broker reconciliation
def _account_map() -> dict[str, str]:
    data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return {a["id"]: a.get("account_number") for a in data.get("arms", []) if a.get("id")}


def fifo_pnl_over_fills(fills: list[dict]) -> tuple[float, int]:
    """FIFO net P&L over a flat list of option fills ({symbol, side, qty, price, ts}).
    Same flush-on-zero shape as the reconstructor. Returns (pnl, closed_round_trips)."""
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for f in fills:
        by_sym[f["symbol"]].append(f)
    pnl, trips = 0.0, 0
    for _sym, legs in by_sym.items():
        legs = sorted(legs, key=lambda x: x["ts"])
        open_qty = buy_not = sell_not = 0.0
        for leg in legs:
            q, px = leg["qty"], leg["price"]
            if leg["side"] == "buy":
                if open_qty <= 1e-9:
                    buy_not = sell_not = 0.0
                open_qty += q
                buy_not += q * px
            else:
                if open_qty <= 1e-9:
                    continue
                open_qty -= q
                sell_not += q * px
                if abs(open_qty) <= 1e-6:
                    pnl += (sell_not - buy_not) * 100.0
                    trips += 1
    return round(pnl, 2), trips


def _et_date_of(ts_utc: Any) -> Optional[str]:
    """UTC timestamp string -> ET calendar date (YYYY-MM-DD). ET, never local (the box runs
    Mountain time -- a naive local read would be 2 hours wrong year-round)."""
    try:
        d = dt.datetime.fromisoformat(str(ts_utc).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(_ET).date().isoformat()


def reconcile_against_broker(timeout: float = 20.0) -> dict:
    """BROKER IS TRUTH (C11). Re-pull FILL activities per broker ACCOUNT and compare leg
    count + FIFO P&L against the ledger this table was built from.

    Compared at the ACCOUNT level, not the arm level: safe-1 and safe-2 share PA3POKNV46VG,
    and the broker cannot know our engine/manual attribution -- so ALL option fills on both
    sides are compared, and the engine-only subset (what the matrix contains) is reported as
    an explicit delta rather than being quietly compared against a different population.

    ================== THE RETENTION FINDING (measured 2026-08-19) ==================
    Alpaca's paper /v2/account/activities endpoint DOES NOT RETAIN full history. Verified
    live on PA3POKNV46VG: `after=2026-06-25` returns nothing older than 2026-08-03, and an
    explicit `after=2026-07-01&until=2026-07-31` window returns ZERO rows -- the data is gone,
    not mis-queried. Roughly a trailing 2.5 weeks survives.

    So "reconcile against the broker" is only ANSWERABLE over that trailing window. This
    function therefore reconciles strictly on the overlap (both sides clipped to the ET dates
    the broker still returns) and reports everything older as
    `ledger_legs_broker_no_longer_retains` -- UNVERIFIABLE, never quietly counted as agreeing.
    0DTE makes the clip clean: every round trip opens and closes on the same ET date, so a
    date-window restriction never severs a trip across the boundary.

    Consequence worth stating plainly: for the pre-window book the fills ledger is the ONLY
    surviving record. It cannot be re-derived from the broker if it is ever lost or corrupted.
    """
    try:
        import broker_fills as bfl
        import fleet_broker as fb
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "UNRECONCILED", "accounts": {},
                "reason": f"cannot import broker modules: {exc}"}
    try:
        creds_all = fb.load_creds()
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "UNRECONCILED", "accounts": {},
                "reason": f"cannot load fleet credentials: {exc}"}

    acct_of = _account_map()
    ledger_by_acct: dict[str, list[dict]] = defaultdict(list)
    engine_by_acct: dict[str, list[dict]] = defaultdict(list)
    for r in _iter_jsonl(FILLS_LEDGER):
        if not r.get("is_option"):
            continue
        acct = acct_of.get(r.get("arm"))
        if not acct:
            continue
        f = {"symbol": r["symbol"], "side": r["side"], "qty": _f(r["qty"]) or 0.0,
             "price": _f(r["price"]) or 0.0, "ts": r["ts_utc"], "id": r.get("activity_id"),
             "date_et": r.get("date_et") or _et_date_of(r.get("ts_utc"))}
        ledger_by_acct[acct].append(f)
        if r.get("attribution") == "engine":
            engine_by_acct[acct].append(f)

    arm_for_acct: dict[str, str] = {}
    for arm in ARMS:
        a = acct_of.get(arm)
        if a and a not in arm_for_acct:
            arm_for_acct[a] = arm

    results: dict[str, Any] = {}
    all_ok = True
    for acct, arm in sorted(arm_for_acct.items()):
        creds = creds_all.get(arm)
        led = ledger_by_acct.get(acct, [])
        if not creds:
            results[acct] = {"arm": arm, "status": "UNREACHABLE",
                             "reason": f"no credentials for arm {arm} in fleet secrets",
                             "ledger_option_legs": len(led)}
            all_ok = False
            continue
        acts = bfl.fetch_fill_activities(creds, BROKER_BACKFILL_SINCE, timeout=timeout)
        if not acts:
            results[acct] = {"arm": arm, "status": "UNREACHABLE",
                             "reason": "broker returned zero activities (network/auth failure or "
                                       "empty account) -- cannot confirm",
                             "ledger_option_legs": len(led)}
            all_ok = False
            continue
        broker_fills: list[dict] = []
        for a in acts:
            sym = a.get("symbol") or ""
            if "/" in sym or len(sym) < 15:
                continue  # crypto / equity -- this table is options only
            q, px = _f(a.get("qty")), _f(a.get("price"))
            side = str(a.get("side") or "").lower()
            if q is None or px is None or side not in ("buy", "sell") or q <= 0 or px <= 0:
                continue
            broker_fills.append({"symbol": sym, "side": side, "qty": q, "price": px,
                                 "ts": a.get("transaction_time"), "id": a.get("id"),
                                 "date_et": _et_date_of(a.get("transaction_time"))})
        if not broker_fills:
            results[acct] = {"arm": arm, "status": "UNREACHABLE",
                             "reason": "broker returned activities but no OPTION fills",
                             "ledger_option_legs": len(led)}
            all_ok = False
            continue

        # ---- clip BOTH sides to the ET-date window the broker still retains
        b_dates = sorted({f["date_et"] for f in broker_fills if f["date_et"]})
        lo_d, hi_d = b_dates[0], b_dates[-1]
        b_win = [f for f in broker_fills if lo_d <= (f["date_et"] or "") <= hi_d]
        l_win = [f for f in led if lo_d <= (f["date_et"] or "") <= hi_d]
        l_older = [f for f in led if (f["date_et"] or "") < lo_d]

        b_pnl, b_trips = fifo_pnl_over_fills(b_win)
        l_pnl, l_trips = fifo_pnl_over_fills(l_win)
        e_pnl, e_trips = fifo_pnl_over_fills(engine_by_acct.get(acct, []))
        ids_only_broker = {f["id"] for f in b_win} - {f["id"] for f in l_win}
        ids_only_ledger = {f["id"] for f in l_win} - {f["id"] for f in b_win}
        ok = (len(b_win) == len(l_win)) and abs(b_pnl - l_pnl) < 0.01 and not ids_only_broker
        all_ok = all_ok and ok
        results[acct] = {
            "arm": arm, "status": "RECONCILED_IN_WINDOW" if ok else "MISMATCH",
            "broker_retained_window_et": [lo_d, hi_d],
            "broker_option_legs_in_window": len(b_win),
            "ledger_option_legs_in_window": len(l_win),
            "broker_fifo_pnl_in_window": b_pnl, "ledger_fifo_pnl_in_window": l_pnl,
            "broker_round_trips_in_window": b_trips, "ledger_round_trips_in_window": l_trips,
            "ledger_legs_broker_no_longer_retains": len(l_older),
            "ledger_option_legs_all_history": len(led),
            "engine_only_round_trips_all_history": e_trips,
            "engine_only_fifo_pnl_all_history": e_pnl,
            "manual_delta_pnl_all_history": round(fifo_pnl_over_fills(led)[0] - e_pnl, 2),
            "in_broker_not_in_ledger": len(ids_only_broker),
            "in_ledger_not_in_broker": len(ids_only_ledger),
        }

    verifiable = sum(r.get("ledger_option_legs_in_window", 0) for r in results.values())
    total_legs = sum(r.get("ledger_option_legs_all_history", 0) for r in results.values())
    return {
        "verdict": "RECONCILED" if (all_ok and results) else "UNRECONCILED",
        "verdict_scope": "TRAILING_RETENTION_WINDOW_ONLY",
        "full_history_verifiable": False,
        "full_history_reason":
            "Alpaca's paper /v2/account/activities does not retain full history -- measured "
            "2026-08-19: after=2026-06-25 returns nothing older than 2026-08-03, and an "
            "explicit July window returns zero rows. Only a trailing ~2.5 weeks is "
            "broker-verifiable; older rows rest on the fills ledger alone.",
        "legs_broker_verifiable": verifiable,
        "legs_total_in_ledger": total_legs,
        "legs_beyond_broker_retention": total_legs - verifiable,
        "accounts": results,
        "note": "Account-level comparison over ALL option fills (engine + manual), both sides "
                "clipped to the broker's retained ET-date window. The matrix holds the "
                "engine-only subset; engine_only_* and manual_delta_pnl_all_history make that "
                "gap explicit. 0DTE means no round trip straddles the window boundary.",
    }


# ================================================================ 6. CLI
def _print_verify(report: dict, recon: Optional[dict]) -> None:
    t = report["totals"]
    print("=" * 78)
    print("TRADE MATRIX -- VERIFY")
    print("=" * 78)
    print(f"rows            : {report['row_count']}")
    print(f"date range      : {report['date_range'][0]} .. {report['date_range'][1]} "
          f"({report['trading_days']} trading days)")
    print(f"  {'arm':9s} {'n':>4s} {'days':>5s} {'gross':>10s} {'net':>10s} "
          f"{'winG':>5s} {'winN':>5s} {'mleg':>5s} {'path':>5s}")
    for arm, s in report["per_arm"].items():
        print(f"  {arm:9s} {s['n']:4d} {s['trading_days']:5d} {s['gross']:10.2f} {s['net']:10.2f} "
              f"{s['wins_gross']:5d} {s['wins_net']:5d} {s['multi_leg_exits']:5d} "
              f"{s['path_covered']:5d}")
    print(f"TOTAL gross     : ${t['gross']:,.2f}")
    print(f"      fees      : ${t['fees_ex_cat']:,.2f} ex-CAT  +  ${t['cat_allocated']:,.2f} CAT")
    print(f"TOTAL net       : ${t['net']:,.2f}   (incl CAT ${t['net_incl_cat']:,.2f})")
    pc = report["path_coverage"]
    print(f"MAE/MFE coverage: {pc['rows_with_option_bars']}/{report['row_count']} rows have real "
          f"OPRA bars; {pc['rows_without_option_bars']} do not")
    if pc["fetch_failures"]:
        print(f"  fetch failures: {len(pc['fetch_failures'])} -> {pc['fetch_failures'][:5]}")
    ec = report["engine_state_coverage"]
    print(f"engine state    : {ec['order_id_matched']} order-id matched / {ec['unmatched']} "
          f"unmatched; market state missing {ec['market_state_missing']}; "
          f"exit reason matched {ec['exit_reason_matched']}")
    cc = report["crosscheck_vs_fills_fifo"]
    print(f"fills_fifo x-chk: {cc['status']}"
          + ("" if cc["status"] == "AGREE" else f" -> {len(cc['problems'])} problems"))
    for p in cc["problems"][:10]:
        print(f"  ! {p}")
    print("-" * 78)
    if recon is None:
        print("BROKER          : SKIPPED (--no-broker)")
        print("VERDICT         : UNRECONCILED (broker check not run)")
        return
    for acct, s in recon["accounts"].items():
        if s["status"] == "UNREACHABLE":
            print(f"  {acct} [{s['arm']:8s}] UNREACHABLE: {s['reason']}")
            continue
        w = s["broker_retained_window_et"]
        print(f"  {acct} [{s['arm']:8s}] {s['status']:20s} window {w[0]}..{w[1]}")
        print(f"      in-window legs  broker={s['broker_option_legs_in_window']:4d}  "
              f"ledger={s['ledger_option_legs_in_window']:4d}   "
              f"FIFO broker=${s['broker_fifo_pnl_in_window']:9.2f}  "
              f"ledger=${s['ledger_fifo_pnl_in_window']:9.2f}")
        print(f"      beyond broker retention: {s['ledger_legs_broker_no_longer_retains']:4d} "
              f"ledger legs UNVERIFIABLE (of {s['ledger_option_legs_all_history']} all-history)")
    if recon.get("full_history_verifiable") is False:
        print(f"  ! broker retains only {recon['legs_broker_verifiable']}/"
              f"{recon['legs_total_in_ledger']} ledger legs -- "
              f"{recon['legs_beyond_broker_retention']} are BEYOND ALPACA'S RETENTION and "
              f"cannot be broker-confirmed at all.")
    print(f"VERDICT         : {recon['verdict']} [{recon.get('verdict_scope', '')}]"
          + (f"  ({recon.get('reason')})" if recon.get("reason") else ""))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build the canonical trade table.")
    ap.add_argument("--verify", action="store_true", help="print verification + reconciliation")
    ap.add_argument("--no-fetch", action="store_true", help="cached OPRA bars only, no network")
    ap.add_argument("--no-broker", action="store_true", help="skip the broker reconciliation")
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args(argv)

    report = build(fetch=not args.no_fetch)
    recon = None if args.no_broker else reconcile_against_broker()
    report["broker_reconciliation"] = recon or {"verdict": "UNRECONCILED", "accounts": {},
                                                "reason": "--no-broker: check not run"}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.verify:
        _print_verify(report, recon)
    else:
        print(f"[trade_matrix] wrote {out} -- {report['row_count']} rows, "
              f"gross ${report['totals']['gross']:,.2f} / net ${report['totals']['net']:,.2f}")
    return 1 if report["crosscheck_vs_fills_fifo"]["status"] != "AGREE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
