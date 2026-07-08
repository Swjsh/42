"""Standalone Tastytrade SANDBOX end-to-end order-path proof.

Hardcoded sandbox-only (is_test=True) -- never reads TT_PROD_* and never touches
tastytrade_paper.py's WATCH_ONLY flag. Places one guaranteed-no-fill limit order
far off market, verifies broker acceptance, cancels, verifies flat. This is the
first end-to-end proof that the Tastytrade order path (place -> accept -> cancel
-> flat) actually works -- it has never been confirmed before.

Run: set TT_SECRET / TT_REFRESH to the SANDBOX pair, then:
    python backtest/futures/tastytrade_e2e_test.py [INSTRUMENT]
"""
import asyncio
import os
import sys
from decimal import Decimal

import tastytrade as tt
from tastytrade.instruments import Future, InstrumentType
from tastytrade.market_data import get_market_data
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType

INSTRUMENT = sys.argv[1] if len(sys.argv) > 1 else "MNQ"


async def main() -> int:
    client_secret = os.environ["TT_SECRET"]
    refresh_token = os.environ["TT_REFRESH"]

    session = tt.Session(client_secret, refresh_token, is_test=True)
    accounts = await tt.Account.get(session)
    if not accounts:
        print("FAIL: no accounts found")
        return 1
    acct = accounts[0]
    print(f"CONNECTED sandbox=True account={acct.account_number}")

    contracts = await Future.get(session, product_codes=[INSTRUMENT])
    contracts = contracts if isinstance(contracts, list) else [contracts]
    active = sorted(
        (c for c in contracts if not getattr(c, "is_expired", False)),
        key=lambda c: c.expiration_date,
    )
    if not active:
        print(f"FAIL: no active {INSTRUMENT} contracts")
        return 1
    contract = active[0]
    print(f"FRONT MONTH: {contract.symbol} exp={contract.expiration_date}")

    tick = contract.tick_size or Decimal("0.25")
    ref_price = None
    try:
        md = await get_market_data(session, contract.symbol, InstrumentType.FUTURE)
        ref_price = md.mark or md.last or md.close
    except Exception as e:
        print(f"NOTE: market-data fetch failed ({e}) -- falling back to a static reference price")
    if not ref_price:
        ref_price = Decimal("20000")  # rough static fallback, only used for a non-marketable BUY limit
    raw_price = ref_price * Decimal("0.85")  # ~15% below reference -> non-marketable, still realistic
    test_price = (raw_price / tick).to_integral_value() * tick
    print(f"REFERENCE price={ref_price} -> TEST_LIMIT_PRICE={test_price} (tick={tick})")

    # API convention (order.py: "price of the order; negative = debit, positive = credit"):
    # a BUY (opening a long) is a debit -> price must be NEGATIVE, or the API rejects it
    # with "cant_buy_for_credit". tastytrade_paper.py's place_bracket() has this same bug
    # for BUY-side entries (passes entry_price unsigned) -- worth fixing there too.
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=[contract.build_leg(1, OrderAction.BUY)],
        price=-test_price,
    )
    r = await acct.place_order(session, order, dry_run=False)
    if not r.order:
        print(f"FAIL: place_order returned no order. errors={getattr(r, 'errors', None)}")
        return 1
    order_id = r.order.id
    print(f"PLACED id={order_id} status={r.order.status} price={-test_price} (debit)")

    await asyncio.sleep(2)
    live = await acct.get_live_orders(session)
    match = [o for o in live if o.id == order_id]
    print(f"POST-PLACE poll: found={len(match)} status={match[0].status if match else 'GONE'}")

    await acct.delete_order(session, order_id)
    print(f"CANCEL sent id={order_id}")

    await asyncio.sleep(2)
    live2 = await acct.get_live_orders(session)
    match2 = [o for o in live2 if o.id == order_id]
    print(f"POST-CANCEL poll: open_orders_matching={len(match2)}")

    positions = await acct.get_positions(session)
    futs = [
        p for p in positions
        if str(getattr(p.instrument_type, "value", p.instrument_type)).upper() in ("FUTURE", "FUTURES")
    ]
    print(f"POSITIONS after test: {len(futs)} future position(s)")

    clean = not match2 and not futs
    print(f"END-STATE: {'CLEAN' if clean else 'NOT CLEAN'}")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
