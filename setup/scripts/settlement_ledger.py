"""settlement_ledger -- REPLACES the margin-PDT day-trade counter as the live
gate feed for Rule 7 (CLAUDE.md), for CASH accounts (verified live 2026-07-14:
both core accounts return multiplier="1" and Alpaca reports pattern_day_trader
/daytrade_count as null -- PDT is structurally inapplicable to a cash account;
research: markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md).

WHAT THIS MODELS (cash-account settlement, not margin PDT)
------------------------------------------------------------
A cash account may re-trade freely using SETTLED funds. Options settle T+1
("payment of the premium for an options trade is finalized the next trading
day" -- Options Industry Council, cited in the research doc above). The
account starts each ET trading day with a pool of SETTLED cash: whatever cash
sat in the account overnight (clean by construction -- both core accounts are
flat overnight, so nothing from a prior day is still "unsettled" by today;
T+1 means everything from D-1 or earlier has already settled).

As entries are placed today:
  - Each entry DEBITS its notional (premium * qty * 100) from the settled
    pool. This reflects capital COMMITTED today, independent of whether that
    specific contract has closed yet.
  - Closing (selling) a position does NOT credit the pool back intraday --
    those proceeds are UNSETTLED until T+1. Funding a NEW entry from them,
    then closing that new entry the SAME day, is exactly the Good-Faith-
    Violation pattern documented by every broker-compliance source in the
    research doc (E*TRADE worked example: sell A (unsettled proceeds) -> buy
    B with those proceeds -> sell B same day -> GFV on B's close).
  - This naturally caps same-day entries at roughly
    (SOD settled cash) / (typical notional per entry) -- ~2-3 entries for
    both core accounts at today's equity and Rule-6 sizing -- which IS the
    correct cash-account behavior (the number of round trips a cash account
    can actually fund from settled capital), not an arbitrary knob.

This module tracks the running settled-pool debit in a small per-account
DAILY JSON ledger (reset automatically the first call of a new ET trading
day) and exposes `get_settlement_status` for risk_gate's "cash_settlement"
pdt_gate_mode to gate on (see backtest/lib/risk_gate.py).

FAIL-OPEN CONTRACT (matches pdt_tracker.py's established precedent for this
exact gate family -- see that module's docstring): a ledger FILE read/write
error resets to "0 entries used today, full SOD settled cash available" --
i.e. an I/O failure can only let a trade through that a WORKING ledger would
have blocked, never invent a NEW block on real (paper) money. The caller,
risk_gate.check_order, has the opposite (correct) contract for its OWN inputs
-- it DENIES on a missing/unreadable NUMBER (fail-closed). The fail-open
lives entirely in this module's I/O layer, never in the numbers once they
reach the pure gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def compute_settled_cash_remaining(sod_settled_cash: float, entries_notionals: Any) -> float:
    """PURE. settled_cash_remaining = sod_settled_cash - sum(today's entry
    notionals so far), clipped at 0 (never negative -- the gate is supposed
    to prevent overshoot, but a defensive floor costs nothing)."""
    total = 0.0
    for n in (entries_notionals or []):
        try:
            total += float(n)
        except (TypeError, ValueError):
            continue
    return max(0.0, float(sod_settled_cash) - total)


def _fresh_ledger(today_et_date: str, sod_settled_cash: float) -> dict:
    return {"date": today_et_date, "sod_settled_cash": float(sod_settled_cash), "entries": []}


def load_ledger(path: Path, today_et_date: str, sod_settled_cash: float) -> dict:
    """Load today's ledger. Resets to a fresh ledger (0 entries, this call's
    sod_settled_cash) when: the file doesn't exist yet, the persisted date !=
    today_et_date (new ET trading day), or the file is corrupt/unreadable
    (fail-open -- see module docstring)."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("date") == today_et_date:
                return data
    except Exception:
        pass
    return _fresh_ledger(today_et_date, sod_settled_cash)


def save_ledger(path: Path, ledger: dict) -> bool:
    """Persist. Fail-open: a write error is swallowed (never blocks the order
    path on a state-file write -- matches heartbeat_core._execute's existing
    circuit-breaker write pattern for day_trades_used_5d). Returns True on a
    successful write, False otherwise (caller may use this for visibility)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def record_entry(path: Path, today_et_date: str, sod_settled_cash: float,
                  notional: float, ts_et: str) -> dict:
    """Load (or reset) today's ledger, append this entry's notional, persist,
    and return the updated ledger. Call this ONCE per successful order
    PLACEMENT (not per dry-run/check) -- mirrors where pdt_tracker's
    day_trades_used_5d visibility write happens in heartbeat_core._execute."""
    ledger = load_ledger(path, today_et_date, sod_settled_cash)
    ledger.setdefault("entries", []).append({"ts_et": ts_et, "notional": float(notional)})
    save_ledger(path, ledger)
    return ledger


def get_settlement_status(path: Path, today_et_date: str, sod_settled_cash: float) -> dict:
    """READ-ONLY: the current settlement status for risk_gate to gate on.
    Does not record anything. Fail-open per module docstring (a read error
    behaves exactly like a brand-new empty ledger for today).

    Returns:
        {"settled_cash_remaining": float, "entries_used_today": int,
         "sod_settled_cash": float, "date": str}
    """
    ledger = load_ledger(path, today_et_date, sod_settled_cash)
    notionals = [e.get("notional") for e in ledger.get("entries", []) if isinstance(e, dict)]
    sod = ledger.get("sod_settled_cash", sod_settled_cash)
    try:
        sod = float(sod)
    except (TypeError, ValueError):
        sod = float(sod_settled_cash)
    remaining = compute_settled_cash_remaining(sod, notionals)
    return {
        "settled_cash_remaining": remaining,
        "entries_used_today": len(notionals),
        "sod_settled_cash": sod,
        "date": ledger.get("date", today_et_date),
    }


def ledger_path(state_dir: Path, account: str) -> Path:
    """Canonical per-account ledger path. account: "safe" or "bold" (matches
    heartbeat_core.py's existing circuit-breaker path convention: safe ->
    STATE/settlement-ledger.json, bold -> STATE/aggressive/settlement-ledger.json)."""
    if str(account).lower() == "bold":
        return state_dir / "aggressive" / "settlement-ledger.json"
    return state_dir / "settlement-ledger.json"
