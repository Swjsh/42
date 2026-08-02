#!/usr/bin/env python
"""entry_execution_cost_2026_08_02.py -- ENTRY EXECUTION COST DECOMPOSITION.

Motivating exhibit (analysis/deep-research/WINNER-AUTOPSY-2026-07-31-SYNTHESIS.md section
2.1): the 2026-07-31 12:19 ET winner filled at $0.33 while the SAME contract traded $0.27
three minutes earlier -- $30 on a $126 trade, 24% of realized P&L, lost to entry pricing and
latency. And the logged mid AT FILL was exactly $0.30 against a $0.30 min_entry_premium floor
-- paying MORE is what made the trade legal at all. This script generalizes that n=1 forensic
reconstruction to the FULL real-fill history and answers, in dollars:

  1. MECHANISM: entry_px = ask_at_decision + entry_cross_buffer (heartbeat_core._execute /
     fleet_live._place_live, both call fleet_broker.marketable_limit_price). buffer is read
     as params.get("entry_cross_buffer", 0.03) in BOTH lanes; automation/state/params.json,
     aggressive/params.json, and every arm's params_patch in accounts.json carry NO
     entry_cross_buffer key (grep-verified, git-history-verified -- 0 hits ever). The buffer
     is therefore a bare CODE DEFAULT, never ratified, never A/B'd, never ONCE promoted to a
     tunable param in this repo's own doctrine sense. $0.03 is not a considered number; it is
     whatever the person who typed the function signature happened to write.

  2. COST: for every real entry fill (fills-ledger.jsonl, broker truth), decompose the price
     paid into 4 honestly-labelled components:
       mid_signal      -- real OPRA trade price at the setup's OWN trigger bar (the earliest
                           real print reflecting the signal, reconstructed from
                           backtest/data/options/{symbol}.csv, fetched live for any symbol not
                           yet cached -- never fabricated, never Black-Scholes)
       latency_drift    = mid_decision - mid_signal        (price move while the pipeline ran)
       spread_crossed   = ask_decision  - mid_decision      (cost of buying at the ask, not mid)
       cross_buffer     = entry_px      - ask_decision      (the extra padding -- always exactly
                                                              entry_cross_buffer by construction)
       price_improvement = entry_px - fill_price            (a limit can fill BETTER than offered
                                                              -- this recovers some of the above)
     identity: entry_px == mid_signal + latency_drift + spread_crossed + cross_buffer
               fill_price == entry_px - price_improvement
     mid_decision and entry_px are REAL LOGGED NUMBERS (core: exec.premium/exec.entry_px/
     exec.nbbo in core-decisions.jsonl since 2026-07-20; fleet: placement.mid/placement.entry_px
     in automation/state/fleet/{arm}/decisions.jsonl) -- not modeled. Only mid_signal requires
     external OPRA reconstruction.

  3. FLOOR INTERACTION: for fleet arms, decide_arm() gates min_entry_premium against a
     SEPARATE, EARLIER read (the arm decision row's top-level "premium", fixed at signal/
     risk-gate time) than the one placement.mid/entry_px are built from (a later, fresh read).
     Counts how many ACTUALLY-TAKEN entries would have failed the $0.30 floor had the engine
     acted on the earlier (cheaper) mid_signal instead of the drifted mid_gating -- i.e. how
     much of "the floor cleared" is actually "the delay let it clear."

  4. Reuses analysis/recommendations/min-entry-premium-2026-07-31.json (already-shipped
     provenance + blocked-cohort replay) rather than re-deriving it -- see that file for the
     floor's own KEEP verdict, untouched here.

INSTRUMENT, NOT A TRADE-PATH CHANGE. Zero edits to heartbeat_core.py, fleet_live.py,
fleet_broker.py, fleet_executor.py, or any params file -- read-only over existing ledgers +
an additive-only OPRA cache extension (new cache files for previously-uncached symbols;
no existing cache file is modified).

Run:
    backtest/.venv/Scripts/python.exe backtest/tools/entry_execution_cost_2026_08_02.py
    backtest/.venv/Scripts/python.exe backtest/tools/entry_execution_cost_2026_08_02.py --no-fetch
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _alpaca_creds import resolve_alpaca_creds  # noqa: E402
import lib.option_pricing_real as _opr  # noqa: E402
from lib.option_pricing_real import CACHE_DIR, bar_containing, load_contract_bars  # noqa: E402

FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
TRADES_CSV = REPO / "journal" / "trades.csv"
OUT_JSON = REPO / "analysis" / "recommendations" / "entry-execution-cost-2026-08-02.json"

CORE_ARMS = ("safe-2", "bold-2")
FLEET_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
ALL_ARMS = CORE_ARMS + FLEET_ARMS

CROSS_BUFFER = 0.03                    # confirmed uniform code default -- see module docstring
FLOOR_SHIP_DATE = "2026-07-09"         # min_entry_premium=0.30 shipped this date
FLOOR_VALUE = 0.30
DRIVING_ROW_MAX_LOOKBACK_S = 20 * 60   # fleet decision must trail a core ENTER tick by < this
PRE_MECHANISM_EPS = 0.005              # entry_px == mid within this -> no buffer was applied yet

ET = dt.timezone(dt.timedelta(hours=-4))


# =============================================================================
# Pure helpers (unit-tested in backtest/tests/test_entry_execution_cost_2026_08_02.py)
# =============================================================================

def side_from_symbol(symbol: str) -> str:
    """OCC symbol -> 'C'/'P'. Mirrors shadow_entry_backfill.py's own convention exactly."""
    return "C" if "C" in symbol[-9:] else "P"


def parse_et(ts: "str | None") -> "dt.datetime | None":
    """Tolerant ISO8601 -> tz-aware ET datetime. Naive strings are ASSUMED already ET (every
    producer in this pipeline writes ET wall-clock either naive or with -04:00 -- see
    fill_latency.py's own _parse_iso for the same convention). Never raises."""
    if not isinstance(ts, str) or not ts:
        return None
    s = ts.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d.replace(tzinfo=ET) if d.tzinfo is None else d.astimezone(ET)


def decompose(*, fill_price: float, qty: float, entry_px: float, mid_decision: float,
             mid_signal: "float | None", buffer: float = CROSS_BUFFER) -> dict:
    """PURE. Per-contract $ decomposition of one real entry fill -- never raises, never
    fabricates: mid_signal=None propagates to latency_drift=None (excluded, not zero-filled).

    Identity (verified by test_entry_execution_cost_2026_08_02.py):
        entry_px == mid_signal + latency_drift + spread_crossed + cross_buffer  (when mid_signal
                                                                                  is resolvable)
        entry_px == fill_price + price_improvement
    """
    ask_decision = round(entry_px - buffer, 4)
    spread_crossed = round(ask_decision - mid_decision, 4)
    cross_buffer = round(entry_px - ask_decision, 4)      # arithmetic identity, not re-assumed
    price_improvement = round(entry_px - fill_price, 4)   # >=0 typical: limit fills at/better
    latency_drift = round(mid_decision - mid_signal, 4) if mid_signal is not None else None

    row = {
        "ask_decision": ask_decision, "mid_decision": mid_decision, "mid_signal": mid_signal,
        "spread_crossed": spread_crossed, "cross_buffer": cross_buffer,
        "latency_drift": latency_drift, "price_improvement": price_improvement,
        "entry_px": entry_px, "fill_price": fill_price, "qty": qty,
    }
    for k in ("spread_crossed", "cross_buffer", "latency_drift", "price_improvement"):
        v = row[k]
        row[f"{k}_dollars"] = None if v is None else round(v * qty * 100, 2)
    return row


def is_pre_mechanism(entry_px: float, mid_decision: float, eps: float = PRE_MECHANISM_EPS) -> bool:
    """True when entry_px ~= mid_decision -- the marketable-limit-plus-buffer mechanism (#15,
    shipped 2026-06-30) was not yet active for this row (limit was placed AT mid, no buffer)."""
    return abs(entry_px - mid_decision) < eps


# =============================================================================
# I/O -- ledger loaders (all fail-open: a missing/corrupt file yields an empty population)
# =============================================================================

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def load_buy_fills() -> list[dict]:
    """Real option BUY fills (fills-ledger.jsonl, broker truth), grouped by order_id with a
    qty-weighted average fill price (Alpaca can split one order across multiple print rows --
    20 of 167 real entry orders in this window did). Crypto excluded. All 6 arms included."""
    raw = [r for r in _read_jsonl(FILLS_LEDGER)
           if r.get("side") == "buy" and r.get("is_option") and not r.get("is_crypto")
           and r.get("arm") in ALL_ARMS]
    by_oid: dict[str, list[dict]] = {}
    for r in raw:
        by_oid.setdefault(r["order_id"], []).append(r)
    out = []
    for oid, rows in by_oid.items():
        total_qty = sum(float(r["qty"]) for r in rows)
        if total_qty <= 0:
            continue
        vwap_price = sum(float(r["qty"]) * float(r["price"]) for r in rows) / total_qty
        first = min(rows, key=lambda r: r["ts_et"])
        out.append({
            "order_id": oid, "arm": first["arm"], "symbol": first["symbol"],
            "qty": total_qty, "fill_price": round(vwap_price, 4),
            "ts_et": first["ts_et"], "date_et": first["date_et"], "n_fill_rows": len(rows),
        })
    return out


def load_core_decisions() -> "tuple[dict, dict]":
    """(by_order_id, triggered_rows_by_date) from core-decisions.jsonl (19.6K rows, safe+bold).

    CORRECTED IN THIS SESSION: the driving-row index was originally filtered to
    verdict in (ENTER_BULL, ENTER_BEAR) -- but the WINNER-AUTOPSY anchor trade's own driving
    ticks (2026-07-31 12:16:02-12:18:03, trigger_bar_et=12:10:00, trigger_level_exact=743.25)
    carry verdict "SKIP_ELITE_BULL_LEVEL_RECLAIM", never "ENTER_BULL" -- CORE blocked its own
    entry on a gate unrelated to whether the trigger existed, while the FLEET lane (reading
    the same underlying trigger via the shared signal) went on to place the trade this whole
    lane is about. Verdict strings do not gate "did a trigger fire" -- trigger_level_exact
    does. Filtering on verdict silently excluded the exact row this measurement most needed;
    caught by reproducing the anchor trade end-to-end and finding it unmatched."""
    by_order_id: dict[str, dict] = {}
    triggered_by_date: dict[str, list[dict]] = {}
    for r in _read_jsonl(CORE_DECISIONS):
        ex = r.get("exec") or {}
        oid = (ex.get("broker") or {}).get("id")
        if oid:
            by_order_id[oid] = r
        if r.get("trigger_bar_et") and r.get("trigger_level_exact") is not None and r.get("side"):
            d = (r.get("ts_et") or "")[:10]
            triggered_by_date.setdefault(d, []).append(r)
    for d in triggered_by_date:
        triggered_by_date[d].sort(key=lambda r: r.get("ts_et") or "")
    return by_order_id, triggered_by_date


def load_fleet_decisions(arm: str) -> dict:
    """{order_id: decision_row} for one fleet arm's own decisions.jsonl."""
    out: dict[str, dict] = {}
    for r in _read_jsonl(FLEET_DIR / arm / "decisions.jsonl"):
        oid = ((r.get("placement") or {}).get("broker") or {}).get("id")
        if oid:
            out[oid] = r
    return out


def find_driving_core_row(triggered_by_date: dict, date_et: str, side: str, fleet_ts_et: str,
                          max_lookback_s: float = DRIVING_ROW_MAX_LOOKBACK_S) -> "tuple[Optional[dict], Optional[float]]":
    """The most recent core row (matching side, same date, a real trigger_level_exact present
    -- see load_core_decisions docstring for why this is NOT filtered by verdict) at/before the
    fleet arm's own decision tick -- the real-time signal the fleet arm most plausibly acted
    on (fleet has no core_tick_id join key before 2026-08-01 -- see fill_latency.py docstring
    -- so this is a disclosed BEST-MATCH heuristic, not an exact join). None/None if nothing
    qualifies within max_lookback_s (excluded upstream, never guessed)."""
    fleet_dt = parse_et(fleet_ts_et)
    if fleet_dt is None:
        return None, None
    best, best_gap = None, None
    for r in triggered_by_date.get(date_et, []):
        if r.get("side") != side:
            continue
        r_dt = parse_et(r.get("ts_et"))
        if r_dt is None or r_dt > fleet_dt:
            continue
        gap = (fleet_dt - r_dt).total_seconds()
        if gap > max_lookback_s:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = r, gap
    return best, best_gap


def load_trade_pnl_by_entry_order_id() -> dict:
    """{entry_order_id: summed dollar_pnl} from journal/trades.csv (partial-TP1 + runner legs
    of ONE entry share one entry_order_id -- summed to the trade's TOTAL realized P&L,
    matching how WINNER-AUTOPSY itself groups legs). CORRECTED IN THIS SESSION: the
    entry_order_id/exit_order_id pair lives in the `archetype_match_json` column (verified by
    direct read), NOT `notes_short` (a plain human-readable sentence) -- an earlier draft of
    this loader read the wrong column and joined 0/105 rows before this fix."""
    out: dict[str, list[float]] = {}
    if not TRADES_CSV.exists():
        return {}
    with TRADES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                meta = json.loads(row.get("archetype_match_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            eoid = meta.get("entry_order_id")
            if not eoid:
                continue
            try:
                pnl = float(row.get("dollar_pnl") or 0)
            except ValueError:
                pnl = 0.0
            out.setdefault(eoid, []).append(pnl)
    return {k: round(sum(v), 2) for k, v in out.items()}


# =============================================================================
# OPRA reconstruction (local cache first, additive live-fetch fallback)
# =============================================================================

def ensure_cached(symbol: str, date_et: str, creds) -> bool:
    """Fetch+cache one symbol's 5-min OPRA bars if not already on disk. ADDITIVE ONLY -- never
    overwrites an existing cache file. Returns False (fail-open) on any fetch error.

    BUG FOUND + FIXED IN THIS SESSION: option_pricing_real.load_contract_bars() memoizes a
    miss as `_CONTRACT_BAR_CACHE[symbol] = None` the FIRST time it's asked (before this
    function has a chance to fetch). Without the explicit `.pop()` below, every post-fetch
    re-read of the same symbol silently returns the stale None from that first miss instead
    of the freshly-written CSV -- caught by comparing a direct fetch_contract_bars() call
    (81 real bars) against the pipeline's own no_bars_cached verdict for the same symbol."""
    path = CACHE_DIR / f"{symbol}.csv"
    if path.exists():
        _opr._CONTRACT_BAR_CACHE.pop(symbol, None)
        return True
    if creds is None:
        return False
    try:
        from fetch_option_data import fetch_contract_bars  # noqa: PLC0415
        rows = fetch_contract_bars(symbol, date_et, creds.key, creds.secret)
    except Exception:  # noqa: BLE001 -- a fetch failure must never crash the measurement
        return False
    if not rows:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["timestamp_et", "open", "high", "low", "close",
                                           "volume", "vwap", "trade_count"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    _opr._CONTRACT_BAR_CACHE.pop(symbol, None)   # invalidate the stale None-memo -- see docstring
    return True


def mid_signal_from_opra(symbol: str, signal_anchor_ts: "str | None") -> "tuple[Optional[float], str]":
    """Real OPRA trade-price proxy for 'mid at signal' -- the closing print of the 5-min bar
    CONTAINING signal_anchor_ts. DISCLOSED: this is a TRADE price (last print in that 5-min
    bar), not a bid/ask quote mid -- the local cache (backtest/data/options/*.csv, populated
    by fetch_option_data.py) only carries OHLCV, matching every other consumer of this cache
    in the repo (simulator_real.py, shadow_entry_backfill.py).

    ANCHOR CHOICE (corrected in this session -- see build_rows()'s driving-row wiring): the
    caller must pass the driving core row's OWN ts_et (when the engine actually evaluated
    trigger_level_exact and scored the setup), NOT trigger_bar_et (the underlying candle's
    START timestamp, ~1-6 minutes EARLIER than the evaluation). Using trigger_bar_et directly
    was tried first and caught by reproducing the WINNER-AUTOPSY 2026-07-31 12:19 anchor trade
    end-to-end: it returned $0.35 (the 12:10-12:15 bar's close) against WINNER-AUTOPSY's own
    hand-verified $0.27 (the 12:16 1-min print, at core's actual evaluation instant) -- the
    WRONG bar. Anchoring on ts_et instead lands in the 12:15-12:20 bar (close $0.32), much
    closer to the hand-verified value; the residual gap is the disclosed 5-min-vs-1-min
    resolution limit (see module docstring), not a second bar-selection error.

    Returns (None, reason) on any failure -- never fabricated, never Black-Scholes."""
    if not signal_anchor_ts:
        return None, "no_signal_anchor"
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None, "no_bars_cached"
    when = parse_et(signal_anchor_ts)
    if when is None:
        return None, "bad_signal_anchor_ts"
    bar = bar_containing(df, when)
    if bar is None:
        return None, "no_bar_at_signal_anchor"
    return float(bar.close), "ok"


# =============================================================================
# Orchestration
# =============================================================================

def build_rows(fetch_missing: bool = True) -> "tuple[list[dict], dict]":
    fills = load_buy_fills()
    core_by_oid, enter_by_date = load_core_decisions()
    fleet_by_oid = {arm: load_fleet_decisions(arm) for arm in FLEET_ARMS}
    trade_pnl = load_trade_pnl_by_entry_order_id()

    creds = None
    if fetch_missing:
        try:
            creds = resolve_alpaca_creds()
        except RuntimeError:
            creds = None

    rows: list[dict] = []
    excluded = {"no_decision_row": 0, "no_entry_px_or_mid": 0, "pre_mechanism": 0}

    for f in fills:
        arm = f["arm"]
        if arm in CORE_ARMS:
            drow = core_by_oid.get(f["order_id"])
            if drow is None:
                excluded["no_decision_row"] += 1
                continue
            ex = drow.get("exec") or {}
            broker = ex.get("broker") or {}
            entry_px = ex.get("entry_px")
            if entry_px is None:
                entry_px = broker.get("limit_price")
            mid_decision = ex.get("premium")
            mid_gating = mid_decision            # single read in heartbeat_core._execute
            trigger_bar_et = drow.get("trigger_bar_et")
            decision_ts = drow.get("ts_et")
            signal_anchor_ts = None               # CORE has NO separate signal-read hop (single
                                                   # get_option_mid call serves both the verdict
                                                   # AND the entry price -- see fill_latency.py's
                                                   # own identical scope decision to exclude
                                                   # core from its latency instrument). Forcing
                                                   # an OPRA lookup at decision_ts would compare
                                                   # a real logged quote-mid against a nearby
                                                   # 5-min TRADE print at the SAME instant --
                                                   # that measures bid/ask-vs-print noise, not
                                                   # latency. core_same_read_no_relay below skips
                                                   # OPRA and sets mid_signal = mid_decision
                                                   # directly: a clean, honest, mechanical zero.
            nbbo_logged = ex.get("nbbo")
            match_gap_s = 0.0
            match_quality = "exact"              # order_id join, same-tick execution
        else:
            drow = fleet_by_oid.get(arm, {}).get(f["order_id"])
            if drow is None:
                excluded["no_decision_row"] += 1
                continue
            placement = drow.get("placement") or {}
            broker = placement.get("broker") or {}
            entry_px = placement.get("entry_px")
            if entry_px is None:
                entry_px = broker.get("limit_price")
            mid_decision = placement.get("mid")
            mid_gating = drow.get("premium")     # decide_arm's OWN (earlier) read -- the floor
                                                  # gate compares THIS, not placement.mid
            decision_ts = drow.get("ts_et")
            nbbo_logged = None
            side = side_from_symbol(f["symbol"])
            core_row, gap = find_driving_core_row(enter_by_date, f["date_et"], side, decision_ts)
            trigger_bar_et = core_row.get("trigger_bar_et") if core_row else None
            # FLEET signal anchor = the DRIVING CORE ROW'S OWN ts_et (when core actually
            # evaluated/scored the trigger), NOT trigger_bar_et (the underlying candle's start,
            # 1-6 minutes earlier). See mid_signal_from_opra's docstring for how this was
            # caught: anchoring on trigger_bar_et reproduced the WINNER-AUTOPSY 2026-07-31
            # 12:19 anchor trade at $0.35 (the wrong bar) vs the hand-verified $0.27 (the
            # 12:16 print, at core's evaluation instant) -- ts_et anchoring lands at $0.32,
            # the closest a 5-min-bar proxy can get to a hand-picked 1-min print.
            signal_anchor_ts = core_row.get("ts_et") if core_row else None
            match_gap_s = gap
            match_quality = "best_match_lte_20min" if core_row is not None else "unmatched"

        if entry_px is None or mid_decision is None:
            excluded["no_entry_px_or_mid"] += 1
            continue
        entry_px = float(entry_px)
        mid_decision = float(mid_decision)

        if is_pre_mechanism(entry_px, mid_decision):
            excluded["pre_mechanism"] += 1
            continue

        if arm in CORE_ARMS:
            # no separate signal-read hop -- see the signal_anchor_ts=None comment above.
            mid_signal, signal_status = mid_decision, "core_same_read_no_relay"
        else:
            mid_signal, signal_status = mid_signal_from_opra(f["symbol"], signal_anchor_ts)
            if mid_signal is None and signal_status == "no_bars_cached" and fetch_missing:
                if ensure_cached(f["symbol"], f["date_et"], creds):
                    mid_signal, signal_status = mid_signal_from_opra(f["symbol"], signal_anchor_ts)

        comp = decompose(fill_price=f["fill_price"], qty=f["qty"], entry_px=entry_px,
                         mid_decision=mid_decision, mid_signal=mid_signal)

        pnl = trade_pnl.get(f["order_id"])
        label = "UNKNOWN" if pnl is None else ("WINNER" if pnl > 0 else "LOSER")

        rows.append({
            **f, **comp,
            "arm_lane": "core" if arm in CORE_ARMS else "fleet",
            "mid_gating": mid_gating,
            "trigger_bar_et": trigger_bar_et,
            "signal_anchor_ts": signal_anchor_ts,
            "decision_ts_et": decision_ts,
            "signal_match_gap_s": match_gap_s,
            "signal_match_quality": match_quality,
            "signal_status": signal_status,
            "nbbo_logged": nbbo_logged,
            "trade_pnl": pnl,
            "label": label,
            "floor_active": f["date_et"] >= FLOOR_SHIP_DATE,
        })

    return rows, excluded


# =============================================================================
# Aggregation
# =============================================================================

def _vals(rows: list[dict], key: str) -> list[float]:
    return [r[key] for r in rows if r.get(key) is not None]


def _sum(rows: list[dict], key: str) -> float:
    return round(sum(_vals(rows, key)), 2)


def _avg_cents(rows: list[dict], key: str) -> "float | None":
    v = _vals(rows, key)
    return round((sum(v) / len(v)) * 100, 2) if v else None


def cost_block(rows: list[dict]) -> dict:
    n = len(rows)
    n_lat = len(_vals(rows, "latency_drift_dollars"))
    total_spread = _sum(rows, "spread_crossed_dollars")
    total_buffer = _sum(rows, "cross_buffer_dollars")
    total_latency = _sum(rows, "latency_drift_dollars")
    total_improve = _sum(rows, "price_improvement_dollars")
    return {
        "n": n, "n_latency_resolved": n_lat, "n_latency_excluded": n - n_lat,
        "total_spread_crossed_dollars": total_spread,
        "total_cross_buffer_dollars": total_buffer,
        "total_latency_drift_dollars": total_latency,
        "total_price_improvement_dollars": total_improve,
        "total_excess_cost_dollars": round(total_spread + total_buffer + total_latency, 2),
        "total_net_of_improvement_dollars": round(
            total_spread + total_buffer + total_latency - total_improve, 2),
        "avg_spread_crossed_cents_per_contract": _avg_cents(rows, "spread_crossed"),
        "avg_cross_buffer_cents_per_contract": _avg_cents(rows, "cross_buffer"),
        "avg_latency_drift_cents_per_contract": _avg_cents(rows, "latency_drift"),
        "avg_price_improvement_cents_per_contract": _avg_cents(rows, "price_improvement"),
    }


def drop_best(rows: list[dict], key: str = "latency_drift_dollars") -> list[dict]:
    """Robustness check: exclude the single largest-magnitude cost row on `key` -- mirrors
    this repo's own expectancy_drop_best convention (min-entry-premium-blocked-replay, T5)."""
    resolved = [r for r in rows if r.get(key) is not None]
    if not resolved:
        return rows
    worst = max(resolved, key=lambda r: r[key])
    return [r for r in rows if r is not worst]


def floor_interaction(rows: list[dict]) -> dict:
    """Task #3: of the entries we ACTUALLY TOOK (floor active, so they cleared it), how many
    would have FAILED the $0.30 floor had the engine gated on mid_signal (the real, earlier,
    un-drifted OPRA print) instead of mid_gating (the value the floor check actually used)?"""
    pop = [r for r in rows if r["floor_active"] and r.get("mid_signal") is not None]
    cleared_on_gating = [r for r in pop if r["mid_gating"] is not None and r["mid_gating"] >= FLOOR_VALUE]
    would_have_failed = [r for r in cleared_on_gating if r["mid_signal"] < FLOOR_VALUE]
    saved_cents_total = sum(-(r["latency_drift_dollars"] or 0) for r in would_have_failed)
    pnl_at_risk = [r["trade_pnl"] for r in would_have_failed if r["trade_pnl"] is not None]
    return {
        "population_floor_active_with_signal": len(pop),
        "n_cleared_floor_on_gating_read": len(cleared_on_gating),
        "n_would_have_failed_floor_on_signal_read": len(would_have_failed),
        "pct_of_cleared_that_are_delay_dependent": (
            round(100 * len(would_have_failed) / len(cleared_on_gating), 1)
            if cleared_on_gating else None),
        "pnl_on_delay_dependent_trades": round(sum(pnl_at_risk), 2) if pnl_at_risk else None,
        "n_delay_dependent_with_known_pnl": len(pnl_at_risk),
        "aggregate_latency_drift_dollars_on_delay_dependent_trades": round(saved_cents_total, 2),
        "rows": [{"order_id": r["order_id"], "arm": r["arm"], "symbol": r["symbol"],
                  "date_et": r["date_et"], "mid_signal": r["mid_signal"],
                  "mid_gating": r["mid_gating"], "trade_pnl": r["trade_pnl"]}
                 for r in would_have_failed],
    }


def summarize(rows: list[dict], excluded: dict) -> dict:
    winners = [r for r in rows if r["label"] == "WINNER"]
    losers = [r for r in rows if r["label"] == "LOSER"]
    unknown = [r for r in rows if r["label"] == "UNKNOWN"]
    core_rows = [r for r in rows if r["arm_lane"] == "core"]
    fleet_rows = [r for r in rows if r["arm_lane"] == "fleet"]

    return {
        "n_priced_rows": len(rows),
        "excluded": excluded,
        "overall": cost_block(rows),
        "overall_drop_best_latency": cost_block(drop_best(rows, "latency_drift_dollars")),
        "by_label": {"winners": cost_block(winners), "losers": cost_block(losers),
                    "unknown_pnl": cost_block(unknown)},
        "by_lane": {"core": cost_block(core_rows), "fleet": cost_block(fleet_rows)},
        "by_arm": {arm: cost_block([r for r in rows if r["arm"] == arm]) for arm in ALL_ARMS},
        "floor_interaction": floor_interaction(rows),
        "winner_loser_counts": {"winners": len(winners), "losers": len(losers),
                                "unknown_pnl": len(unknown)},
    }


# =============================================================================
# main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-fetch", action="store_true",
                    help="skip live OPRA fetch for uncached symbols (local cache only)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows, excluded = build_rows(fetch_missing=not args.no_fetch)
    summary = summarize(rows, excluded)

    out_path = Path(args.out) if args.out else OUT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_doc": ("Entry execution cost decomposition -- real fills, real OPRA, real logged "
                "quotes. INSTRUMENT ONLY, descriptive. See module docstring for full method."),
        "generated_at": dt.datetime.now(ET).isoformat(),
        "buffer_used": CROSS_BUFFER, "floor_ship_date": FLOOR_SHIP_DATE, "floor_value": FLOOR_VALUE,
        "summary": summary,
        "rows": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(json.dumps(summary, indent=2, default=str))
    print(f"\nwrote {len(rows)} priced rows -> {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
