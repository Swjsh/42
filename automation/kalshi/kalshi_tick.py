#!/usr/bin/env python3
"""One Kalshi lane tick: read Gamma's signal -> map to a contract -> log (and, if armed, place).

SAFETY POSTURE -- read this before changing anything:
  * SHADOW IS THE DEFAULT. Placing a real order requires BOTH:
        env GAMMA_KALSHI_ARMED=1   AND   credentials present in the gitignored store
    Missing either -> shadow. There is no other path to a live order.
  * MAKER ONLY. kalshi_client exposes no market-order call at all.
  * Fails CLOSED for entries (any doubt -> no trade), OPEN for reads.
  * Every tick appends to the ledger whether it trades or not. A tick that decided
    nothing is still evidence -- silent skips are how you lose the ability to audit.

Usage:
    python kalshi_tick.py                 # shadow (safe, no creds needed)
    python kalshi_tick.py --status        # account + lane health, no decision
    GAMMA_KALSHI_ARMED=1 python kalshi_tick.py    # live, only with creds present
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kalshi_client import (  # noqa: E402
    KalshiClient, KalshiError, load_credentials, fee_dollars,
)
from kalshi_signal_map import decide, load_params, load_signal, Decision  # noqa: E402

REPO = HERE.parents[1]
STATE_DIR = REPO / "automation" / "state" / "kalshi"
LEDGER = STATE_DIR / "shadow-ledger.jsonl"
LAST_TICK = STATE_DIR / "last-tick.json"

ARM_ENV = "GAMMA_KALSHI_ARMED"
MAX_SIGNAL_AGE_MIN = 10


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def signal_age_minutes(signal: dict) -> float | None:
    """Age of the shared signal. None if unparseable -- treated as fatal by the caller."""
    stamp = signal.get("written_at") or signal.get("beacon_ts_et")
    if not stamp:
        return None
    try:
        return (_now_utc() - datetime.fromisoformat(stamp)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None


def is_armed() -> bool:
    return os.environ.get(ARM_ENV, "").strip() == "1"


def append_ledger(row: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    LAST_TICK.write_text(json.dumps(row, indent=2))


def realised_pnl_today(date_str: str) -> float:
    """Sum of recorded live fills today. Drives the daily loss cap."""
    if not LEDGER.exists():
        return 0.0
    total = 0.0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("date") == date_str and row.get("mode") == "LIVE":
            total += float(row.get("realised_pnl") or 0.0)
    return total


def run_status(client: KalshiClient, creds) -> int:
    st = client.exchange_status()
    print(f"exchange_active = {st.get('exchange_active')}   trading_active = {st.get('trading_active')}")
    print(f"credentials     = {'LOADED (' + creds.label + ')' if creds else 'ABSENT'}")
    print(f"armed           = {is_armed()}  (env {ARM_ENV})")
    print(f"mode            = {'LIVE' if (is_armed() and creds) else 'SHADOW'}")
    if creds:
        try:
            bal = client.balance()
            cents = bal.get("balance")
            print(f"balance         = ${cents / 100:.2f}" if isinstance(cents, (int, float))
                  else f"balance         = {bal}")
            pos = client.positions()
            mp = [p for p in (pos.get("market_positions") or []) if p.get("position")]
            print(f"open positions  = {len(mp)}")
            for p in mp[:5]:
                print(f"   {p.get('ticker')}  qty={p.get('position')}")
        except KalshiError as e:
            print(f"balance         = UNAVAILABLE ({e})")
    try:
        sig = load_signal()
        age = signal_age_minutes(sig)
        print(f"signal          = {sig.get('production_action')} @ {sig.get('time_et')} "
              f"(age {age:.1f} min)" if age is not None else
              f"signal          = {sig.get('production_action')} (age UNKNOWN)")
    except FileNotFoundError as e:
        print(f"signal          = MISSING ({e})")
    n = sum(1 for _ in LEDGER.open()) if LEDGER.exists() else 0
    print(f"ledger rows     = {n}  ({LEDGER.relative_to(REPO)})")
    return 0


def run_tick(client: KalshiClient, creds, params: dict, dry: bool) -> int:
    armed = is_armed() and creds is not None and not dry
    mode = "LIVE" if armed else "SHADOW"
    now = _now_utc()
    row: dict = {
        "ts_utc": now.isoformat(),
        "date": now.date().isoformat(),
        "mode": mode,
        "arm": params.get("arm", "kalshi-1"),
    }

    # --- never-blind: a stale signal is a refusal, not a guess -------------
    try:
        signal = load_signal()
    except FileNotFoundError as e:
        row |= {"take": False, "reason": f"signal file missing: {e}"}
        append_ledger(row)
        print(f"[{mode}] SKIP - {row['reason']}")
        return 1

    age = signal_age_minutes(signal)
    row["signal_age_min"] = round(age, 2) if age is not None else None
    row["signal_action"] = signal.get("production_action")
    row["spy_spot"] = signal.get("spot")

    if age is None:
        row |= {"take": False, "reason": "signal timestamp unparseable (fail closed)"}
        append_ledger(row)
        print(f"[{mode}] SKIP - {row['reason']}")
        return 1
    if age > MAX_SIGNAL_AGE_MIN and mode == "LIVE":
        row |= {"take": False, "reason": f"signal stale ({age:.1f} min > {MAX_SIGNAL_AGE_MIN})"}
        append_ledger(row)
        print(f"[{mode}] SKIP - {row['reason']}")
        return 1

    # --- daily loss cap ----------------------------------------------------
    pnl = realised_pnl_today(row["date"])
    row["realised_pnl_today"] = round(pnl, 2)
    cap = params["daily_loss_cap_dollars"]
    if pnl <= -abs(cap):
        row |= {"take": False, "reason": f"daily loss cap hit ({pnl:.2f} <= -{cap})"}
        append_ledger(row)
        print(f"[{mode}] HALT - {row['reason']}")
        return 0

    # --- concurrency -------------------------------------------------------
    if armed:
        try:
            open_pos = [p for p in (client.positions().get("market_positions") or [])
                        if p.get("position")]
            if len(open_pos) >= params["max_concurrent_positions"]:
                row |= {"take": False,
                        "reason": f"{len(open_pos)} open >= max {params['max_concurrent_positions']}"}
                append_ledger(row)
                print(f"[{mode}] SKIP - {row['reason']}")
                return 0
        except KalshiError as e:
            row |= {"take": False, "reason": f"position check failed, failing closed: {e}"}
            append_ledger(row)
            print(f"[{mode}] SKIP - {row['reason']}")
            return 1

    # --- the decision ------------------------------------------------------
    try:
        d: Decision = decide(client, params, signal)
    except KalshiError as e:
        row |= {"take": False, "reason": f"market data failure: {e}"}
        append_ledger(row)
        print(f"[{mode}] SKIP - {row['reason']}")
        return 1

    row |= d.to_json()

    if not d.take:
        append_ledger(row)
        print(f"[{mode}] NO TRADE - {d.reason}")
        return 0

    print(f"[{mode}] SIGNAL {d.direction} score={d.signal_score} setup={d.setup_name}")
    print(f"        {d.ticker}  {d.side.upper()} x{d.contracts} @ {d.limit_price_cents}c")
    print(f"        stake=${d.stake_dollars:.2f}  fee=${d.est_fee_dollars:.2f}  "
          f"breakeven={d.breakeven_prob:.2%}  spread={d.spread_cents:.1f}c  depth={d.depth_contracts:.0f}")

    if not armed:
        row["placed"] = False
        row["would_place"] = True
        append_ledger(row)
        print(f"        SHADOW - not placed. Arm with {ARM_ENV}=1 (requires credentials).")
        return 0

    coid = f"gamma-kalshi-{uuid.uuid4().hex[:16]}"
    try:
        resp = client.place_order(
            ticker=d.ticker, side=d.side, action="buy", count=d.contracts,
            limit_price_cents=d.limit_price_cents, client_order_id=coid,
            time_in_force=params.get("time_in_force", ""),
        )
    except (KalshiError, ValueError) as e:
        row |= {"placed": False, "error": str(e)}
        append_ledger(row)
        print(f"        ORDER FAILED: {e}")
        return 1

    order = resp.get("order") or {}
    row |= {"placed": True, "client_order_id": coid,
            "order_id": order.get("order_id"), "order_status": order.get("status")}
    append_ledger(row)
    print(f"        PLACED order_id={order.get('order_id')} status={order.get('status')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kalshi lane tick")
    ap.add_argument("--status", action="store_true", help="health only, make no decision")
    ap.add_argument("--dry-run", action="store_true", help="force shadow even if armed")
    args = ap.parse_args()

    params = load_params()
    try:
        creds = load_credentials(params.get("arm", "kalshi-1"))
    except KalshiError as e:
        print(f"CREDENTIAL ERROR: {e}", file=sys.stderr)
        return 2
    client = KalshiClient(creds)

    if args.status:
        return run_status(client, creds)
    return run_tick(client, creds, params, dry=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
