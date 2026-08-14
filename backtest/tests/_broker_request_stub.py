"""ONE shared contract for what a stubbed `fleet_broker._request` returns per endpoint.

WHY THIS EXISTS (2026-08-14). Thirteen test files each defined their own `fake_request`, all
copy-pasted to the same three lines:

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})
        return {"id": "ord-1", "status": "accepted"}

An order DICT for every endpoint. That was fine until the order-level idempotency guard
shipped 2026-08-02: `open_buy_orders_checked` / `symbol_position_qty_checked` query the
COLLECTION endpoints (`orders?status=open...`, `positions`) and fail **CLOSED** unless the
response `isinstance(res, list)`. A dict is "unparseable", so every stub made the guard report
`ok=False`, and `_execute` returned `SKIP_ORDER_QUERY_ERROR` instead of placing.

Result: **21 tests across 12 files went RED simultaneously** and stayed that way -- every guard
on the money path (strike override, trigger-level provenance, never-average-down's control
arm, exit-shape wiring, fill reconciliation) silently stopped asserting what it claimed to.

This is L294 exactly -- copy-pasted fixed-shape loaders breaking identically across every
sibling on the same trigger day -- and C7: a permanently-red guard is indistinguishable from
no guard. The repair is not 13 edits; it is ONE contract the siblings share, so the next
broker-shape change breaks in one place instead of thirteen.

USAGE -- add two lines to any fake_request, after its bookkeeping append:

    _lst = broker_list_stub(endpoint)
    if _lst is not None:
        return _lst

Returning None means "not a collection endpoint -- the caller's own stub logic applies", which
keeps each test's bespoke order-poll behaviour intact.
"""
from __future__ import annotations

from typing import Any, Optional

def order_posts(posts: list) -> list:
    """The PLACEMENT calls only, out of a stub's recorded broker traffic.

    `assert len(posts) == 1` was written when placement was the only broker call `_execute`
    made. The 2026-08-02 idempotency guard added a GET (`orders?status=open...`) ahead of it,
    so that assertion now counts a read plus a write and fails -- while what every one of
    those tests actually means is "exactly ONE order was placed". Counting POSTs says that
    directly and stays true the next time a read is added ahead of placement.
    """
    return [p for p in posts if str(p.get("method", "")).upper() == "POST"]


def broker_list_stub(endpoint: Any, method: str = "GET", *, orders: Optional[list] = None,
                     positions: Optional[list] = None) -> Optional[list]:
    """List-shaped response for a GET on a COLLECTION endpoint; None for anything else.

    None means "not a collection read -- the caller's own stub logic applies", which keeps
    each test's bespoke placement/poll behaviour intact.

    THREE DISTINCTIONS THIS MUST GET RIGHT (each one broke the suite while this was written):

    1. `method` is load-bearing. A **POST** to `orders` is the placement itself and must
       return the caller's order DICT. Returning `[]` there silently unplaced every order.
    2. `orders/{id}` (single-order poll, used by fill reconciliation) is a DICT endpoint.
       Only `orders` and `orders?...` are collections. A prefix match on `orders/` broke
       every reconciliation test.
    3. `[]` means "confirmed nothing"; an unparseable response means "unknown" and makes the
       live guards refuse. The whole point of this helper is to let a stub express the former
       -- see the module docstring for the 21-test outage caused by conflating them.

    Defaults are the confirmed-empty broker (no pending BUY, no open position), the state the
    placement guards need in order to proceed. Pass `orders=` / `positions=` to stub a
    non-empty broker for tests exercising the duplicate-entry refusal paths.
    """
    if str(method).upper() != "GET":
        return None
    e = str(endpoint).lstrip("/")
    if e == "orders" or e.startswith("orders?"):
        return list(orders or [])
    if e == "positions" or e.startswith("positions?"):
        return list(positions or [])
    return None
