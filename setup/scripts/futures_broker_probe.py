"""futures_broker_probe.py -- settle the Tastytrade sandbox futures question with evidence.

THE OPEN QUESTION (2026-08-09). On 2026-07-07 a real futures order was routed to the
Tastytrade cert account 5WW73759 and came back `Rejected: Session offline`. That was
recorded as "the sandbox account is not provisioned for futures" and the futures lane has
been treated as broker-blocked ever since.

Re-probing today (Sunday 15:2x ET, CME closed) produced a DIFFERENT and more specific
error from the same account:

    tif.futures_session_not_active: The Futures trading session is not currently active.

That is a MARKET-HOURS condition, not a permissions condition -- and the account's own
trading-status endpoint reports `is_futures_enabled: true`. So the July diagnosis is
UNCONFIRMED: both observations are equally consistent with "futures are fine, the session
was simply not active at that moment".

The two hypotheses make different predictions, which is what makes this probe worth running:

    H1  account not futures-approved  -> a dry run during an OPEN session still fails,
                                         with a permissions/buying-power error
    H2  session-hours artifact        -> a dry run during an OPEN session VALIDATES,
                                         returning a buying-power effect and no errors

This script runs the identical dry run and records which prediction came true. A dry run
is broker-side validation: it routes NOTHING, fills NOTHING, and cannot touch money. It is
a sandbox account regardless, and no live venue is involved.

USAGE
    python setup/scripts/futures_broker_probe.py              # probe now
    python setup/scripts/futures_broker_probe.py --wait       # wait for the session, then probe

Result lands in automation/state/futures/broker-probe.jsonl (append-only, one row per run).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures.futures_session import et_now, is_session_open, next_open, session_phase  # noqa: E402

OUT = REPO / "automation" / "state" / "futures" / "broker-probe.jsonl"
ENV_FILE = REPO / ".env.tastytrade"


def _load_env() -> None:
    """Read sandbox credentials from the gitignored store. Never printed, never logged."""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


async def _probe() -> dict:
    from tastytrade import Account, Session  # noqa: PLC0415
    from tastytrade.instruments import Future as TTFuture  # noqa: PLC0415
    from tastytrade.order import (  # noqa: PLC0415
        NewOrder, OrderAction, OrderTimeInForce, OrderType,
    )

    now = et_now()
    out: dict = {
        "at_et": now.isoformat(timespec="seconds"),
        "session_phase": session_phase(now),
        "session_open": is_session_open(now),
    }

    sess = Session("", "", is_test=True)
    acct = (await Account.get(sess))[0]
    out["account"] = acct.account_number
    out["is_futures_approved"] = getattr(acct, "is_futures_approved", None)
    out["futures_account_purpose"] = getattr(acct, "futures_account_purpose", None)

    bals = await acct.get_balances(sess)
    out["net_liq"] = float(bals.net_liquidating_value)
    out["futures_buying_power"] = float(getattr(bals, "futures_buying_power", 0) or 0)

    status = await acct.get_trading_status(sess)
    out["is_futures_enabled"] = getattr(status, "is_futures_enabled", None)
    out["is_futures_intra_day_enabled"] = getattr(status, "is_futures_intra_day_enabled", None)

    res = await TTFuture.get(sess, product_codes=["MES"])
    contracts = res if isinstance(res, list) else [res]
    front = sorted([c for c in contracts if not getattr(c, "is_expired", False)],
                   key=lambda c: c.expiration_date)[0]
    out["front_month"] = front.symbol

    # A deliberately absurd, non-marketable resting BUY. Signed negative because a BUY is
    # a debit (an unsigned price fails with cant_buy_for_credit -- learned 2026-07-06).
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=[front.build_leg(Decimal(1), OrderAction.BUY_TO_OPEN)],
        price=Decimal("-1000.00"),
    )
    try:
        resp = await acct.place_order(sess, order, dry_run=True)
        out["dry_run_ok"] = True
        out["errors"] = resp.errors
        out["warnings"] = resp.warnings
        bp = resp.buying_power_effect
        out["bp_effect_change"] = (
            float(bp.change_in_buying_power) if bp is not None else None)
        out["verdict"] = "H2_SESSION_ARTIFACT" if not resp.errors else "H1_PERMISSIONS"
    except Exception as e:  # noqa: BLE001 -- the error TEXT is the evidence here
        out["dry_run_ok"] = False
        out["error"] = f"{type(e).__name__}: {e}"
        msg = str(e).lower()
        if "session" in msg and "active" in msg:
            out["verdict"] = "SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)"
        else:
            out["verdict"] = "H1_PERMISSIONS"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tastytrade sandbox futures dry-run probe")
    ap.add_argument("--wait", action="store_true",
                    help="sleep until the CME session opens, then probe")
    ap.add_argument("--max-wait-hours", type=float, default=4.0)
    args = ap.parse_args(argv)

    if args.wait and not is_session_open():
        target = next_open()
        deadline = time.time() + args.max_wait_hours * 3600
        print(f"waiting for CME open at {target} ET (now {et_now()})", flush=True)
        while not is_session_open() and time.time() < deadline:
            time.sleep(60)
        # A few minutes past the bell: the matching session needs a moment to come up.
        if is_session_open():
            time.sleep(300)

    _load_env()
    try:
        result = asyncio.run(_probe())
    except Exception as e:  # noqa: BLE001
        result = {"at_et": et_now().isoformat(timespec="seconds"),
                  "verdict": "PROBE_FAILED", "error": f"{type(e).__name__}: {e}"}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
