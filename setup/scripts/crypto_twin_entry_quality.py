"""crypto_twin_entry_quality.py -- TWIN-B3 / EDGE-1: passive-limit entry LIVE measurement.

GRADUATES entry_manager (automation/state/fleet/entry_manager.py, T-W5 -- sim-shadow only
since 2026-07-08) to LIVE measurement on the crypto twin, per markdown/planning/
TWIN-PROGRAM.md stream 3 ("passive-limit entry machinery (T-W5) runs LIVE here and
graduates on real fills before SPY") and queue item TWIN-B3-ENTRY-MANAGER-LIVE /
EDGE-1-PASSIVE-LIMIT-GRADUATION (SEC-DERA-verified: non-marketable limits roughly halve
the dominant measured transaction cost vs marketable orders).

WHAT THIS MODULE DOES (mechanism-only, NEVER an edge claim -- twin doctrine):
  * A/B ALTERNATION: every LIVE twin entry attempt is deterministically assigned a cohort
    off a persisted counter (entry-quality.json's `ab_counter`): EVEN -> "marketable"
    (the pre-B3 market-order path, byte-identical), ODD -> "passive" (a real resting
    limit inside the spread, driven by entry_manager's own patience/cancel decision core).
    Marketable-first is deliberate: a FRESH state_dir's first entry takes the legacy path,
    so every pre-B3 test fixture (one entry per tmp dir) is byte-identical to before.
  * PASSIVE ACTUATOR: place_passive_entry() is the LIVE actuator entry_manager's docstring
    always promised ("a thin live actuator the caller wires to the broker"). It places a
    REAL non-marketable limit (default: mid-spread -- `limit_fraction` of the spread above
    the bid), then runs entry_manager.plan_entry_action once per poll as the patience/
    cancel governor while the BROKER stays the fill authority (C11: broker is source of
    truth; the sim core's own fill verdict is recorded as `sim_fill_divergence` parity
    data, exactly the sim-live comparison T6 wants -- never trusted for a real fill).
    Patience exhausted -> REAL cancel_order, with a fill-during-cancel race re-check and
    a partial-fill crumb flatten (unit-lot integrity: a fractional remnant is market-sold
    immediately, never left to corrupt the 3-unit exit split).
  * PARAMETER PROVENANCE: patience=3 ticks and policy="cancel" are entry-2's frozen
    pre-registration values (entry_manager.py docstring), reused verbatim. delta is the
    ONE crypto-recalibrated knob: the options pre-reg's delta=0.10 (10% under signal
    premium) is an options-premium-scale number -- 10% under spot BTC would never fill
    inside a patience window, so the twin computes delta per-entry such that the limit
    lands mid-spread ("rest a limit inside/below the spread", the task spec). Same
    mechanism-calibration precedent as TwinConfig.exit_shape's own recalibrated
    percentages: chosen so the code path is REACHABLE, never cited as a trading edge.
  * METRICS: automation/state/crypto-twin/entry-quality.json (namespace-isolated via
    cfg.state_dir, like every other twin ledger) carries lifetime per-cohort aggregates
    (fill rate, abandonment rate, avg time-to-fill, avg price improvement vs the
    marketable baseline in $/BTC and bps) + a `recent` attempt list CAPPED at
    RECENT_ATTEMPTS_CAP rows (OP-22: every append-only producer has a retention cap).
    Baseline for BOTH cohorts = the ask at signal time (what a marketable order would
    have paid), so improvement is directly comparable across cohorts.

GRADUATION BAR FOR SPY (documented here per the task spec -- NOT implemented yet):
  >= 20 twin passive FILLS accrued with fill-rate + improvement stats in
  entry-quality.json, THEN a frozen SPY A/B pre-registration (entry-2's existing frozen
  params: delta=0.10, patience=3, policy=cancel) before any SPY path change. Twin
  numbers inform the MECHANISM (does the place/poll/cancel/race machinery work; what
  does abandonment cost); they are never themselves SPY evidence (twin doctrine:
  markdown/planning/TWIN-PROGRAM.md "Kill criteria").

FAIL-OPEN EVERYWHERE: a metrics/counter hiccup can never block an entry (allocate_cohort
degrades to the legacy marketable path; record_attempt swallows + journals its own
failure); a passive-path hiccup (no quote, order rejected, unexpected exception) falls
back to the marketable path so the twin still enters -- the fallback itself is recorded.

This module writes ONLY under the state_dir it is handed (production: automation/state/
crypto-twin/) -- covered by test_crypto_twin_core.py's static AST namespace guard.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import sys

REPO = Path(__file__).resolve().parents[2]
for _p in ("automation/state/fleet", "setup/scripts"):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

import entry_manager as enm  # noqa: E402  -- the T-W5 decision core, reused verbatim
import crypto_twin_broker as broker  # noqa: E402

ENTRY_QUALITY_FILENAME = "entry-quality.json"
RECENT_ATTEMPTS_CAP = 500  # OP-22 retention cap on the append-style `recent` list

_COHORTS = ("passive", "marketable")


# --- entry-quality.json load/save ---------------------------------------------------------
def _eq_path(state_dir: Path) -> Path:
    return Path(state_dir) / ENTRY_QUALITY_FILENAME


def _fresh_cohort_aggregate() -> dict:
    return {
        "attempts": 0, "fills": 0, "misses": 0, "failures": 0, "fallbacks": 0,
        "fill_rate": None, "abandonment_rate": None,
        "sum_time_to_fill_sec": 0.0, "avg_time_to_fill_sec": None,
        "sum_improvement_usd_per_btc": 0.0, "avg_improvement_usd_per_btc": None,
        "sum_improvement_bps": 0.0, "avg_improvement_bps": None,
    }


def _fresh_doc() -> dict:
    return {
        "updated_utc": None,
        "ab_counter": 0,
        "cohorts": {c: _fresh_cohort_aggregate() for c in _COHORTS},
        "recent": [],
    }


def load_entry_quality(state_dir: Path) -> dict:
    """Load-or-default. A missing/corrupt file degrades to a fresh doc (fail-open --
    metrics must never block an entry); individual missing keys are backfilled so a
    schema-older file keeps working after an additive change."""
    p = _eq_path(state_dir)
    doc = _fresh_doc()
    if not p.exists():
        return doc
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return doc
    if not isinstance(raw, dict):
        return doc
    doc["updated_utc"] = raw.get("updated_utc")
    try:
        doc["ab_counter"] = int(raw.get("ab_counter", 0))
    except (TypeError, ValueError):
        doc["ab_counter"] = 0
    cohorts = raw.get("cohorts")
    if isinstance(cohorts, dict):
        for c in _COHORTS:
            rec = cohorts.get(c)
            if isinstance(rec, dict):
                merged = _fresh_cohort_aggregate()
                merged.update({k: rec[k] for k in merged if k in rec})
                doc["cohorts"][c] = merged
    recent = raw.get("recent")
    if isinstance(recent, list):
        doc["recent"] = [r for r in recent if isinstance(r, dict)][-RECENT_ATTEMPTS_CAP:]
    return doc


def save_entry_quality(state_dir: Path, doc: dict) -> None:
    p = _eq_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


# --- A/B alternation ----------------------------------------------------------------------
def allocate_cohort(state_dir: Path) -> "tuple[str, int]":
    """Deterministic alternation: returns (cohort, ab_index) and persists the incremented
    counter IMMEDIATELY (so a crash mid-entry never reuses an index). EVEN index ->
    "marketable", ODD -> "passive" -- marketable-first (see module docstring for why).
    FAIL-OPEN: any load/save error returns ("marketable", -1) -- the legacy path -- so a
    metrics hiccup can never block or distort an entry."""
    try:
        doc = load_entry_quality(state_dir)
        ab_index = int(doc["ab_counter"])
        doc["ab_counter"] = ab_index + 1
        doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
        save_entry_quality(state_dir, doc)
        return ("marketable" if ab_index % 2 == 0 else "passive", ab_index)
    except Exception:  # noqa: BLE001 -- fail-open by contract (see docstring)
        return ("marketable", -1)


# --- metrics ------------------------------------------------------------------------------
def compute_improvement(baseline_ask: Optional[float],
                        fill_price: Optional[float]) -> "tuple[Optional[float], Optional[float]]":
    """(improvement_usd_per_btc, improvement_bps) vs the marketable baseline (the ask at
    signal time). POSITIVE = filled better (cheaper) than a marketable order would have.
    None/None when either side is unknown (a miss has no fill price)."""
    if baseline_ask is None or fill_price is None or baseline_ask <= 0:
        return None, None
    usd = round(float(baseline_ask) - float(fill_price), 4)
    bps = round(usd / float(baseline_ask) * 10_000.0, 4)
    return usd, bps


def _apply_to_aggregate(agg: dict, attempt: dict) -> dict:
    """Returns a NEW aggregate dict with `attempt` folded in (immutability rule)."""
    out = dict(agg)
    outcome = attempt.get("outcome")
    if outcome == "fallback":
        out["fallbacks"] = int(out.get("fallbacks", 0)) + 1
        return out  # fallbacks never enter fill/abandonment denominators
    out["attempts"] = int(out.get("attempts", 0)) + 1
    if outcome == "filled":
        out["fills"] = int(out.get("fills", 0)) + 1
        ttf = attempt.get("time_to_fill_sec")
        if isinstance(ttf, (int, float)):
            out["sum_time_to_fill_sec"] = round(float(out.get("sum_time_to_fill_sec", 0.0)) + float(ttf), 3)
        usd, bps = attempt.get("improvement_usd_per_btc"), attempt.get("improvement_bps")
        if isinstance(usd, (int, float)):
            out["sum_improvement_usd_per_btc"] = round(
                float(out.get("sum_improvement_usd_per_btc", 0.0)) + float(usd), 4)
        if isinstance(bps, (int, float)):
            out["sum_improvement_bps"] = round(float(out.get("sum_improvement_bps", 0.0)) + float(bps), 4)
    elif outcome == "missed":
        out["misses"] = int(out.get("misses", 0)) + 1
    else:  # "failed" -- a real order attempt the broker rejected/errored
        out["failures"] = int(out.get("failures", 0)) + 1
    attempts = out["attempts"]
    fills = out["fills"]
    out["fill_rate"] = round(fills / attempts, 4) if attempts else None
    out["abandonment_rate"] = round(out["misses"] / attempts, 4) if attempts else None
    out["avg_time_to_fill_sec"] = round(out["sum_time_to_fill_sec"] / fills, 3) if fills else None
    out["avg_improvement_usd_per_btc"] = (round(out["sum_improvement_usd_per_btc"] / fills, 4)
                                          if fills else None)
    out["avg_improvement_bps"] = round(out["sum_improvement_bps"] / fills, 4) if fills else None
    return out


def record_attempt(state_dir: Path, attempt: dict,
                   journal: Optional[Callable[..., None]] = None) -> Optional[dict]:
    """Fold ONE completed attempt into entry-quality.json (lifetime aggregates + capped
    `recent` list). Computes improvement fields when a fill price is present. NEVER
    raises (fail-open); a write failure is journaled via `journal` when provided (C7:
    silent failure is failure) and otherwise swallowed. Returns the attempt row as
    persisted, or None on failure."""
    try:
        row = dict(attempt)
        row.setdefault("ts_utc", datetime.now(timezone.utc).isoformat())
        usd, bps = compute_improvement(row.get("baseline_ask"), row.get("fill_price"))
        row.setdefault("improvement_usd_per_btc", usd)
        row.setdefault("improvement_bps", bps)
        cohort = row.get("cohort")
        doc = load_entry_quality(state_dir)
        if cohort in _COHORTS:
            doc["cohorts"][cohort] = _apply_to_aggregate(doc["cohorts"][cohort], row)
        doc["recent"] = (doc["recent"] + [row])[-RECENT_ATTEMPTS_CAP:]
        doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
        save_entry_quality(state_dir, doc)
        return row
    except Exception as e:  # noqa: BLE001 -- metrics must never block the entry path
        if journal is not None:
            try:
                journal("ENTRY_QUALITY_WRITE_FAILED", error=f"{type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001
                pass
        return None


# --- the passive-limit LIVE actuator ------------------------------------------------------
def passive_limit_price(ask: float, bid: float, limit_fraction: float) -> Optional[float]:
    """The resting BUY limit: `limit_fraction` of the spread above the bid (0.5 = mid),
    clamped strictly BELOW the ask (non-marketable by construction -- if the spread is
    tighter than a cent, rest at the bid). None on a degenerate quote."""
    if ask is None or bid is None or ask <= 0 or bid <= 0 or ask < bid:
        return None
    limit = round(bid + limit_fraction * (ask - bid), 2)
    if limit >= ask:
        limit = min(round(ask - 0.01, 2), round(bid, 2))
    if limit <= 0:
        return None
    return limit


def _order_status_qty(o: dict) -> "tuple[str, float, Optional[float]]":
    """(status_lower, filled_qty, filled_avg_price) from a get_order response, tolerating
    _error/malformed responses (treated as not-filled -- caller keeps waiting)."""
    if not isinstance(o, dict) or o.get("_error"):
        return "", 0.0, None
    status = str(o.get("status", "")).lower()
    try:
        fq = float(o.get("filled_qty") or 0)
    except (TypeError, ValueError):
        fq = 0.0
    try:
        fap = float(o["filled_avg_price"]) if o.get("filled_avg_price") is not None else None
    except (TypeError, ValueError, KeyError):
        fap = None
    return status, fq, fap


def place_passive_entry(*, creds: dict, symbol: str, qty_btc: float, units: int,
                        unit_qty_btc: float, side: str, price: float,
                        trigger_level: Optional[float], scenario_tag: Optional[str],
                        ab_index: Optional[int], live: bool,
                        patience_polls: int, poll_seconds: float, limit_fraction: float,
                        journal: Callable[..., None]) -> dict:
    """ONE passive-limit entry attempt: real resting limit -> poll/patience/cancel, with
    entry_manager.plan_entry_action as the patience governor and the BROKER as the fill
    authority (C11). Returns a dict whose `outcome` is one of:
      "filled"   -- real fill (incl. the fill-during-cancel race); carries fill_price,
                    time_to_fill_sec, order/fill details.
      "missed"   -- patience exhausted, order cancelled (abandonment); any partial-fill
                    crumb was market-sold immediately (unit-lot integrity).
      "fallback" -- passive path unavailable this attempt (no quote / order rejected /
                    no order id); caller routes to the marketable path. fallback_reason
                    says why.
    Never raises for broker-shaped failures; caller wraps for truly unexpected ones."""
    quote = broker.get_crypto_quote_hilo(symbol, creds=creds)
    if quote is None:
        return {"outcome": "fallback", "fallback_reason": "no_quote"}
    ask, bid = quote
    limit_price = passive_limit_price(ask, bid, limit_fraction)
    if limit_price is None:
        return {"outcome": "fallback", "fallback_reason": f"degenerate_quote ask={ask} bid={bid}"}

    # entry_manager's decision core, reused verbatim: patience=frozen pre-reg 3,
    # policy="cancel"; delta recomputed per-entry so limit == mid-spread (see module
    # docstring "PARAMETER PROVENANCE").
    delta = max(0.0, 1.0 - (limit_price / ask))
    state = enm.EntryState.from_signal(symbol=symbol, side="C", signal_premium=ask,
                                       delta=delta, patience_ticks=patience_polls,
                                       policy="cancel")

    order = broker.place_crypto_order(creds, symbol=symbol, side="buy", qty=qty_btc,
                                      order_type="limit", limit_price=limit_price, live=live)
    journal("PLACED", symbol=symbol, side=side, units=units, unit_qty_btc=unit_qty_btc,
            qty_btc=qty_btc, price=price, trigger_level=trigger_level, scenario=scenario_tag,
            order=order, live=live, entry_mode="passive", ab_index=ab_index,
            limit_price=limit_price, baseline_ask=ask, baseline_bid=bid)
    if not live or order.get("_error") or order.get("_refused") or order.get("_skipped"):
        return {"outcome": "fallback", "fallback_reason": "order_rejected", "order": order,
                "limit_price": limit_price, "baseline_ask": ask, "baseline_bid": bid}
    order_id = order.get("id")
    if not order_id:
        return {"outcome": "fallback", "fallback_reason": "no_order_id", "order": order,
                "limit_price": limit_price, "baseline_ask": ask, "baseline_bid": bid}

    t0 = time.monotonic()
    sim_fill_divergence = False
    polls_used = 0
    cancelled_by_core = False
    for check in range(1, max(1, int(patience_polls)) + 1):
        if poll_seconds > 0:
            time.sleep(poll_seconds)  # rest the limit BEFORE each check (the live analog
            #                            of "the next tick's look at the market")
        polls_used = check
        o = broker.get_order(creds, order_id)
        status, filled_qty, fap = _order_status_qty(o)
        if status == "filled" and filled_qty > 0:
            fill_price = fap if fap is not None else limit_price
            return {"outcome": "filled", "order": order, "order_id": order_id,
                    "fill": {"filled": True, "status": status, "filled_qty": filled_qty,
                             "filled_avg_price": fill_price, "order": o},
                    "fill_price": fill_price,
                    "time_to_fill_sec": round(time.monotonic() - t0, 3),
                    "limit_price": limit_price, "baseline_ask": ask, "baseline_bid": bid,
                    "polls_used": polls_used, "sim_fill_divergence": sim_fill_divergence,
                    "race_fill": False, "entry_manager_state": state.to_dict()}
        # entry_manager governs patience/cancel off the FRESH ask (its fill verdict is
        # parity data only -- broker stays the authority; see module docstring).
        fresh = broker.get_crypto_quote_hilo(symbol, creds=creds)
        tick_ask = fresh[0] if fresh else ask
        decision = enm.plan_entry_action(state, ask=tick_ask)
        state = decision.state
        if state.status == "filled":
            sim_fill_divergence = True  # sim core says filled, broker says not (yet)
        if decision.action.kind == "CANCEL":
            cancelled_by_core = True
            break

    # Patience exhausted -> REAL cancel, then the fill-during-cancel race re-check.
    cancel_res = broker.cancel_order(creds, order_id, live=live)
    final = broker.get_order(creds, order_id)
    f_status, f_qty, f_fap = _order_status_qty(final)
    if f_status == "filled" and f_qty > 0:
        fill_price = f_fap if f_fap is not None else limit_price
        return {"outcome": "filled", "order": order, "order_id": order_id,
                "fill": {"filled": True, "status": f_status, "filled_qty": f_qty,
                         "filled_avg_price": fill_price, "order": final},
                "fill_price": fill_price,
                "time_to_fill_sec": round(time.monotonic() - t0, 3),
                "limit_price": limit_price, "baseline_ask": ask, "baseline_bid": bid,
                "polls_used": polls_used, "sim_fill_divergence": sim_fill_divergence,
                "race_fill": True, "entry_manager_state": state.to_dict()}

    partial_flattened = None
    if f_qty > 0:  # partial fill remnant -- flatten crumbs (unit-lot integrity, B1a)
        sell = broker.market_sell_crypto(creds, symbol=symbol, qty=round(f_qty, 8), live=live)
        partial_flattened = {"qty_btc": round(f_qty, 8), "broker": sell}
        journal("ENTRY_PARTIAL_FLATTENED", symbol=symbol, order_id=order_id,
                qty_btc=round(f_qty, 8), entry_mode="passive", ab_index=ab_index, broker=sell)

    return {"outcome": "missed", "order": order, "order_id": order_id,
            "cancel": cancel_res, "cancelled_by_core": cancelled_by_core,
            "partial_flattened": partial_flattened,
            "time_resting_sec": round(time.monotonic() - t0, 3),
            "limit_price": limit_price, "baseline_ask": ask, "baseline_bid": bid,
            "polls_used": polls_used, "sim_fill_divergence": sim_fill_divergence,
            "entry_manager_state": state.to_dict()}
