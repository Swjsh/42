#!/usr/bin/env python
"""day_summary.py -- THE ONE CANONICAL ANSWER TO "WHAT DID WE TRADE ON DAY X".

WHY THIS EXISTS (J, 2026-08-19, verbatim): "Every time you figure out how many times we
traded today, you get it wrong. Is it that hard to read the MCP?" -- the 2026-08-19 trade
count was misreported TWICE (12; the truth is 14) because the number was read off a DERIVED
file mid-reconciliation instead of off the broker. This module is the fix: the broker is the
authority, the derived files are cross-checks, and a disagreement is a LOUD, non-zero-exit
UNRECONCILED verdict -- never a silently-preferred number.

THE COUNTING RULE (one definition, stated once, applied everywhere)
------------------------------------------------------------------
A ROUND TRIP is one complete open->flat cycle on a single (arm, OCC option symbol):
  * Opens on the first BUY while flat in that symbol.
  * Scale-ins (further BUYs while open) join the SAME round trip; entry premium is the
    qty-weighted average of the buy legs (`n_entry_legs` records how many).
  * MULTI-LEG EXITS (TP1 + runner) are ONE round trip, not two. `n_exit_legs` records how
    many sell executions closed it; `exit_premium_avg` is the qty-weighted average sell
    price. This is the single most common way the count gets inflated.
  * The cycle FLUSHES the instant net qty returns to zero. A same-symbol re-entry later the
    same day is a NEW round trip (0DTE OCC symbols are date-scoped but NOT trip-scoped --
    the bug fills_fifo.py already carries the fix for; do not "simplify" it away).
  * Still-open positions are NOT round trips. They are reported separately, never dropped.
  * CRYPTO (symbol contains "/") is NOT a SPY round trip. Excluded from the count and the
    P&L, and reported explicitly on its own line so the exclusion is visible, not silent.

On 2026-08-19 this rule yields 14 round trips / +$266.00 gross across 5 arms. The two
numbers most likely to be quoted by mistake: 30 (option FILL executions) and 16 (exit legs
counted as separate trips).

THREE VIEWS, ONE VERDICT
------------------------
  A  BROKER   -- Alpaca REST /v2/account/activities/FILL, per arm. THE AUTHORITY.
  B  LEDGER   -- automation/state/fills-ledger.jsonl, run through the SAME reconstructor.
  C  FIFO LIB -- fills_fifo.mine_real_arm_fills(), the shared library (engine-attribution
                 rows only), which is what the rest of the repo's reporting consumes.

Reconciliation is strict and mechanical:
  A vs B  : activity_id set-diff at the FILL level, plus round-trip count and gross to the
            cent. Any difference -> UNRECONCILED, with the offending ids printed.
  B vs C  : B filtered to attribution=="engine" must equal C exactly. This is an invariant,
            not a courtesy: if it breaks, either the attribution field or the shared FIFO
            library has drifted, and every downstream P&L number is suspect.
Exit code is NON-ZERO on anything but a clean reconcile, so a caller cannot ignore it:
  0 RECONCILED | 2 UNRECONCILED | 3 BROKER_UNREACHABLE (verdict UNVERIFIED) | 1 usage error.
A broker fetch failure NEVER degrades to "use the ledger" -- it degrades to UNVERIFIED.

COSTS -- MEASURED, NOT MODELLED, WHEN THE BROKER HAS POSTED THEM
----------------------------------------------------------------
Alpaca PAPER charges real regulatory pass-through fees (OCC / ORF / TAF / REG=SEC Sec.31 /
CAT); commission is $0 on paper AND live. This tool reads activity_type=FEE straight off the
broker and reports the ACTUAL debit for the trade date. Fee rows post on a lag -- measured
2026-08-19 ~23:45 ET: ZERO FEE rows existed for trade date 2026-08-19 on any of the 5 arms,
while 2026-08-18's had all posted (safe-2 `accrued_fees`=0 and `pending_reg_taf_fees`=0
independently corroborate that nothing was yet accrued). So 2026-08-19's net is necessarily
an estimate tonight and becomes exact tomorrow -- re-run it then.

The FEE query params are a trap worth naming: `after=` and `date=` filter on the row's
CREATION time, not its trade date, and a fee created the next morning belongs to the prior
trade date. `fetch_broker_fees` therefore pages backwards and filters on the row's own
`date` field. Filtering server-side silently drops the CAT row every time.

When fees have not posted the tool says NOT POSTED and shows the cost_model.py MODELLED
estimate clearly labelled as an estimate. It never defaults a missing fee to zero and calls
the result net. Every P&L line is printed GROSS and NET, and names which basis the net used.

MCP vs RAW REST -- MEASURED 2026-08-19 (J's cost question, answered with bytes)
-------------------------------------------------------------------------------
Same three facts (account, positions, FILL activities) for safe-2 on 2026-08-19, response
payload measured in bytes. MCP figures are the `mcp__alpaca__*` tool outputs; REST figures
are the raw urllib response bodies these functions actually use.

    fact                        raw REST      MCP tool     MCP overhead
    account                        973 B       1,204 B      +231 B  (+23.7%)
    positions (flat, empty)          2 B         245 B      +243 B  (+12,150%)
    activities FILL (10 rows)    3,360 B       3,608 B      +248 B   (+7.4%)
    ------------------------------------------------------------------------
    TOTAL, one arm               4,335 B       5,057 B      +722 B  (+16.7%)

The +231/+243/+248 B is a fixed per-call `_alpaca_mcp_security` envelope; the JSON payload
inside it is byte-identical to REST. So MCP is ~17% heavier on this workload, and the
smaller/more frequent the call, the worse the ratio (a flat-positions check is 122x REST).

Two effects dwarf that 17%, and they are the real answer:
  1. COVERAGE. MCP reaches 2 of the 5 active arms -- `alpaca` -> safe-2, `alpaca_aggressive`
     -> bold-2. safe-3, risky-1 and risky-3 have NO MCP server. A book-wide day count is
     therefore IMPOSSIBLE over MCP and always possible over REST. "Is it that hard to read
     the MCP?" -- for 3 of 5 arms, the MCP cannot answer the question at all.
  2. WHERE THE BYTES LAND. An MCP response is spent into the model's CONTEXT WINDOW; a REST
     response is consumed inside this process and only the printed digest reaches the model.
     Measured on 2026-08-19: full-book REST across all 5 arms = 15,334 B on the wire, and
     this script's entire printed answer = 3,063 B. The MCP path would put ~10,114 B of raw
     activity JSON into context for the 2 reachable arms and still leave 3 arms uncounted --
     3.3x the context for 40% of the book.

VERDICT: raw REST is cheaper on every axis that matters -- ~17% fewer bytes per equivalent
call, and 3.3x fewer context bytes for 2.5x more coverage -- and it is the only path that
can see the whole book. MCP stays useful for ad-hoc interactive pokes at safe-2/bold-2; it
is the wrong instrument for counting the day. The honest answer to "is it that hard to read
the MCP?" is that reading the MCP was never the fix: the miscount came from reading a
DERIVED FILE, and MCP could not have caught it for 3 of the 5 arms anyway.

USAGE
-----
    backtest/.venv/Scripts/python.exe setup/scripts/day_summary.py                 # today ET
    backtest/.venv/Scripts/python.exe setup/scripts/day_summary.py --date 2026-08-19
    backtest/.venv/Scripts/python.exe setup/scripts/day_summary.py --date 2026-08-19 --json
    backtest/.venv/Scripts/python.exe setup/scripts/day_summary.py --no-broker     # ledger
                                       # only; always reports UNVERIFIED / exit 3 by design.

Stdlib only + repo-local imports. Network: 3 GETs per arm (+ pagination). Seconds, not
minutes -- well inside the 5-minute reaper budget.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fills_fifo  # noqa: E402
import fleet_broker as fb  # noqa: E402
from et_clock import et_now, et_offset_hours, et_today_str  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
ACCOUNTS_JSON = STATE / "fleet" / "accounts.json"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNRECONCILED = 2
EXIT_BROKER_UNREACHABLE = 3

CENT = 0.005  # equality tolerance for money comparisons


# ---------------------------------------------------------------------------
# roster + time window
# ---------------------------------------------------------------------------

def active_arms() -> "list[str]":
    """Active real-fills arms, DERIVED from accounts.json -- never hardcoded. Excludes
    retired arms and the futures arms (fidelity != real_fills)."""
    data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return [a["id"] for a in data.get("arms", [])
            if a.get("status") == "active" and a.get("fidelity") == "real_fills"]


def et_day_utc_window(day: str) -> "tuple[str, str]":
    """UTC [start, end) covering the ET calendar day `day` (YYYY-MM-DD). DST-aware via
    et_clock -- NEVER a hardcoded -4 (L: the OPRA fixed-offset scar)."""
    d = datetime.strptime(day, "%Y-%m-%d")
    noon_utc_guess = d.replace(hour=16, tzinfo=timezone.utc)  # ~noon ET, safely inside DST
    offset = et_offset_hours(noon_utc_guess)  # -4 (EDT) or -5 (EST)
    start = (d - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
    return (start.isoformat().replace("+00:00", "Z"),
            (start + timedelta(days=1)).isoformat().replace("+00:00", "Z"))


def _is_crypto(symbol: str) -> bool:
    return "/" in (symbol or "")


def _is_option(symbol: str) -> bool:
    return isinstance(symbol, str) and len(symbol) >= 15 and not _is_crypto(symbol)


# ---------------------------------------------------------------------------
# broker reads (the authority)
# ---------------------------------------------------------------------------

def _get_json(creds: dict, path: str, timeout: float = 20.0) -> Any:
    """One raw REST GET. RAISES on failure -- callers turn that into UNVERIFIED, never into
    a silent fallback."""
    url = creds["base_url"].rstrip("/") + path
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def fetch_broker_fills(creds: dict, day: str) -> "list[dict]":
    """FILL activities whose ET date == `day`, paginated. Raises on any HTTP error."""
    after, until = et_day_utc_window(day)
    out: "list[dict]" = []
    token: Optional[str] = None
    for _ in range(50):  # 50 * 100 = 5k fills/day, orders of magnitude above reality
        q = (f"/v2/account/activities/FILL?after={after}&until={until}"
             f"&direction=asc&page_size=100")
        if token:
            q += f"&page_token={token}"
        page = _get_json(creds, q)
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        if len(page) < 100:
            break
        token = page[-1].get("id")
        if not token:
            break
    # Defensive re-filter on ET date: never trust the server-side window alone.
    keep = []
    for a in out:
        ts = a.get("transaction_time")
        if not ts:
            continue
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if et_now(dt).strftime("%Y-%m-%d") == day:
            keep.append(a)
    return keep


def fetch_broker_fees(creds: dict, day: str) -> "list[dict]":
    """FEE activities for TRADE DATE `day` (the row's own `date` field -- fees post on a lag
    and the `after`/`date` query params filter on creation, so filtering server-side would
    drop them; measured 2026-08-19). Pages backwards until safely past the target date."""
    out: "list[dict]" = []
    token: Optional[str] = None
    for _ in range(20):
        q = "/v2/account/activities/FEE?direction=desc&page_size=100"
        if token:
            q += f"&page_token={token}"
        page = _get_json(creds, q)
        if not isinstance(page, list) or not page:
            break
        out.extend(r for r in page if r.get("date") == day)
        oldest = min((r.get("date") or "9999-99-99") for r in page)
        if oldest < day or len(page) < 100:
            break
        token = page[-1].get("id")
        if not token:
            break
    return out


def normalize_broker_fill(a: dict, arm: str) -> "dict | None":
    """One Alpaca FILL activity -> the normalized shape both views share. Returns None on a
    malformed row -- callers COUNT those, they are never silently discarded."""
    if not isinstance(a, dict):
        return None
    aid, symbol, ts = a.get("id"), a.get("symbol"), a.get("transaction_time")
    side = str(a.get("side") or "").lower()
    if not aid or not symbol or side not in ("buy", "sell") or not ts:
        return None
    try:
        price, qty = float(a.get("price") or 0), float(a.get("qty") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0 or qty <= 0:
        return None
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    ts_et = et_now(dt)
    return {"activity_id": aid, "arm": arm, "symbol": symbol, "side": side, "qty": qty,
            "price": price, "ts_et": ts_et.isoformat(), "date_et": ts_et.strftime("%Y-%m-%d"),
            "is_crypto": _is_crypto(symbol), "is_option": _is_option(symbol),
            "attribution": None, "order_id": a.get("order_id")}


# ---------------------------------------------------------------------------
# the reconstructor -- ONE implementation, used for BOTH views
# ---------------------------------------------------------------------------

def round_trips(fills: "list[dict]") -> "tuple[list[dict], list[dict]]":
    """PURE. Group option fills by (arm, symbol), walk in time order, and flush a round trip
    the instant net qty returns to zero. Returns (closed_round_trips, open_or_anomalous).
    Multi-leg exits collapse into ONE trip carrying n_exit_legs + exit_premium_avg."""
    by_key: "dict[tuple, list[dict]]" = {}
    for f in fills:
        if not f.get("is_option"):
            continue
        by_key.setdefault((f["arm"], f["symbol"]), []).append(f)

    closed: "list[dict]" = []
    leftover: "list[dict]" = []
    for (arm, symbol), legs in by_key.items():
        legs = sorted(legs, key=lambda r: (r["ts_et"], r["activity_id"]))
        open_qty = 0.0
        buy_notional = buy_qty = 0.0
        n_entry_legs = 0
        sell_legs: "list[dict]" = []
        entry_ts = None
        for leg in legs:
            q, px = float(leg["qty"]), float(leg["price"])
            if leg["side"] == "buy":
                if open_qty <= 1e-9:  # fresh cycle (first entry, or re-entry after flat)
                    entry_ts, buy_notional, buy_qty, n_entry_legs = leg["ts_et"], 0.0, 0.0, 0
                    sell_legs = []
                open_qty += q
                buy_notional += q * px
                buy_qty += q
                n_entry_legs += 1
            else:  # sell
                if open_qty <= 1e-9:
                    leftover.append({"arm": arm, "symbol": symbol, "qty": q,
                                     "ts_et": leg["ts_et"],
                                     "_anomaly": "sell with no open lot"})
                    continue
                open_qty -= q
                sell_legs.append(leg)
                if abs(open_qty) > 1e-6:
                    continue  # partial exit -- SAME round trip, keep accumulating
                sell_notional = sum(float(s["qty"]) * float(s["price"]) for s in sell_legs)
                sell_qty = sum(float(s["qty"]) for s in sell_legs)
                right = symbol[-9] if len(symbol) >= 9 and symbol[-9] in ("C", "P") else "?"
                closed.append({
                    "arm": arm, "symbol": symbol, "right": right,
                    "date_et": leg["date_et"],
                    "entry_ts_et": entry_ts, "exit_ts_et": sell_legs[-1]["ts_et"],
                    "qty": int(round(buy_qty)),
                    "n_entry_legs": n_entry_legs, "n_exit_legs": len(sell_legs),
                    "entry_premium_avg": round(buy_notional / buy_qty, 4) if buy_qty else None,
                    "exit_premium_avg": round(sell_notional / sell_qty, 4) if sell_qty else None,
                    "gross_pnl": round((sell_notional - buy_notional) * 100.0, 2),
                    "attribution": leg.get("attribution"),
                })
        if open_qty > 1e-9:
            leftover.append({"arm": arm, "symbol": symbol, "open_qty": open_qty,
                             "entry_ts_et": entry_ts,
                             "entry_premium_avg": (round(buy_notional / buy_qty, 4)
                                                   if buy_qty else None),
                             "_anomaly": "still open at end of window"})
    return (sorted(closed, key=lambda r: (r["entry_ts_et"], r["arm"])), leftover)


# A residual under 1% of the opened qty is Alpaca's crypto fee taken IN KIND, not a partial
# exit. Measured 2026-08-19 on safe-2: buy 0.000140949 BTC, sell 0.000140596 -> 0.25% dust,
# consistent with Alpaca's tier-1 crypto fee. 1% leaves margin without ever swallowing a real
# partial exit (which leaves tens of percent).
CRYPTO_DUST_FRACTION = 1e-2


def crypto_activity(fills: "list[dict]") -> dict:
    """Crypto is excluded from the SPY count on purpose -- this reports it so the exclusion
    is VISIBLE rather than silent. `n_fills` is reported alongside `n_round_trips` because
    the two can legitimately differ: Alpaca takes the crypto fee IN KIND, so the sell qty is
    a hair under the buy qty and a naive exact-zero flush would report 0 round trips against
    a real pair of fills (observed 2026-08-19: buy 0.000140949 BTC, sell 0.000140596, dust
    3.53e-7). A residual under CRYPTO_DUST_FRACTION of the opened qty counts as closed; the
    dust itself is reported, never rounded away."""
    by_sym: "dict[tuple, list[dict]]" = {}
    for f in fills:
        if f.get("is_crypto"):
            by_sym.setdefault((f["arm"], f["symbol"]), []).append(f)
    n = 0
    pnl = 0.0
    dust = 0.0
    n_fills = sum(len(v) for v in by_sym.values())
    for legs in by_sym.values():
        legs = sorted(legs, key=lambda r: r["ts_et"])
        open_qty = buy_notional = sell_notional = opened_qty = 0.0
        for leg in legs:
            q, px = float(leg["qty"]), float(leg["price"])
            if leg["side"] == "buy":
                if open_qty <= opened_qty * CRYPTO_DUST_FRACTION:
                    buy_notional = sell_notional = opened_qty = 0.0
                open_qty += q
                opened_qty += q
                buy_notional += q * px
            else:
                if opened_qty <= 0:
                    continue
                open_qty -= q
                sell_notional += q * px
                if abs(open_qty) <= opened_qty * CRYPTO_DUST_FRACTION:
                    n += 1
                    pnl += sell_notional - buy_notional
                    dust += open_qty
    return {"n_fills": n_fills, "n_round_trips": n, "notional_pnl": round(pnl, 4),
            "unclosed_dust_qty": dust}


# ---------------------------------------------------------------------------
# ledger view
# ---------------------------------------------------------------------------

def load_ledger_fills(day: str, arms: "list[str]") -> "list[dict]":
    if not LEDGER.exists():
        return []
    out = []
    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("date_et") != day or r.get("arm") not in arms:
                continue
            out.append(r)
    return out


def freshness(day: str, broker_fills: "list[dict]", ledger_fills: "list[dict]") -> dict:
    """How stale is the derived ledger relative to the broker. The lag that MATTERS is the
    OPTION lag -- that is what the reconciliation covers and what the trade count is made
    of. An all-fills lag is reported too but is easily dominated by an after-hours crypto
    fill the ledger has simply not ingested yet (observed 2026-08-19: a 20:45 ET BTC pair
    made the ledger look 7.7h stale while every option fill was already present)."""
    mtime = (datetime.fromtimestamp(LEDGER.stat().st_mtime, tz=timezone.utc)
             if LEDGER.exists() else None)

    def _lag(bs: "list[dict]", ls: "list[dict]") -> "tuple[Any, Any, Any]":
        lb = max((f["ts_et"] for f in bs), default=None)
        ll = max((f["ts_et"] for f in ls), default=None)
        if not lb or not ll:
            return lb, ll, None
        return lb, ll, round((datetime.fromisoformat(lb)
                              - datetime.fromisoformat(ll)).total_seconds(), 1)

    lb_o, ll_o, lag_o = _lag([f for f in broker_fills if f.get("is_option")],
                             [f for f in ledger_fills if f.get("is_option")])
    lb_a, ll_a, lag_a = _lag(broker_fills, ledger_fills)
    return {"ledger_path": str(LEDGER), "ledger_exists": LEDGER.exists(),
            "ledger_mtime_et": et_now(mtime).isoformat() if mtime else None,
            "last_broker_option_fill_et": lb_o, "last_ledger_option_fill_et": ll_o,
            "option_lag_seconds": lag_o,
            "last_broker_any_fill_et": lb_a, "last_ledger_any_fill_et": ll_a,
            "any_fill_lag_seconds": lag_a}


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------

def reconcile(broker_fills: "list[dict]", ledger_fills: "list[dict]",
              broker_rts: "list[dict]", ledger_rts: "list[dict]") -> dict:
    b_ids = {f["activity_id"] for f in broker_fills if f.get("is_option")}
    l_ids = {f["activity_id"] for f in ledger_fills if f.get("is_option")}
    only_broker, only_ledger = sorted(b_ids - l_ids), sorted(l_ids - b_ids)

    b_gross = round(sum(r["gross_pnl"] for r in broker_rts), 2)
    l_gross = round(sum(r["gross_pnl"] for r in ledger_rts), 2)
    problems = []
    if only_broker:
        problems.append(f"{len(only_broker)} option fill(s) at the BROKER are MISSING from "
                        f"the ledger: {only_broker[:5]}")
    if only_ledger:
        problems.append(f"{len(only_ledger)} option fill(s) in the LEDGER are NOT at the "
                        f"broker: {only_ledger[:5]}")
    if len(broker_rts) != len(ledger_rts):
        problems.append(f"round-trip count differs: broker={len(broker_rts)} "
                        f"ledger={len(ledger_rts)}")
    if abs(b_gross - l_gross) > CENT:
        problems.append(f"gross P&L differs: broker=${b_gross:,.2f} ledger=${l_gross:,.2f}")
    return {"only_broker": only_broker, "only_ledger": only_ledger,
            "broker_n_round_trips": len(broker_rts), "ledger_n_round_trips": len(ledger_rts),
            "broker_gross": b_gross, "ledger_gross": l_gross, "problems": problems}


def reconcile_fifo_lib(day: str, arms: "list[str]", ledger_fills: "list[dict]") -> dict:
    """INVARIANT: the ledger view restricted to attribution=='engine' must equal what the
    shared library (fills_fifo, which every other report in this repo consumes) produces for
    this day. A break means attribution or the shared FIFO has drifted -- and every
    downstream P&L number is then suspect. Loud, not quiet."""
    engine_only = [f for f in ledger_fills if f.get("attribution") == "engine"]
    mine_rts, _ = round_trips(engine_only)
    lib_rts: "list[dict]" = []
    for arm in arms:
        for rt in fills_fifo.mine_real_arm_fills(arm):
            if rt.get("date") == day:
                lib_rts.append({**rt, "arm": arm})
    mine_gross = round(sum(r["gross_pnl"] for r in mine_rts), 2)
    lib_gross = round(sum(r["real_pnl"] for r in lib_rts), 2)
    problems = []
    if len(mine_rts) != len(lib_rts):
        problems.append(f"fills_fifo lib disagrees on engine round-trip count: "
                        f"this_module={len(mine_rts)} fills_fifo={len(lib_rts)}")
    if abs(mine_gross - lib_gross) > CENT:
        problems.append(f"fills_fifo lib disagrees on engine gross: "
                        f"this_module=${mine_gross:,.2f} fills_fifo=${lib_gross:,.2f}")
    return {"engine_n_round_trips": len(mine_rts), "fifo_lib_n_round_trips": len(lib_rts),
            "engine_gross": mine_gross, "fifo_lib_gross": lib_gross, "problems": problems}


# ---------------------------------------------------------------------------
# fees
# ---------------------------------------------------------------------------

def fee_summary(fee_rows_by_arm: dict, round_trips_by_arm: dict) -> dict:
    """ACTUAL broker fees when posted; cost_model MODELLED estimate when not. NEVER zero."""
    actual_total = 0.0
    by_arm: "dict[str, Any]" = {}
    any_posted = False
    for arm, rows in fee_rows_by_arm.items():
        s = round(sum(float(r.get("net_amount") or 0.0) for r in rows), 4)
        sub: "dict[str, float]" = {}
        for r in rows:
            k = r.get("activity_sub_type") or "?"
            sub[k] = round(sub.get(k, 0.0) + float(r.get("net_amount") or 0.0), 4)
        by_arm[arm] = {"n_rows": len(rows), "total": s, "by_sub_type": sub}
        actual_total += s
        any_posted = any_posted or bool(rows)

    modelled_total = 0.0
    modelled_ok = True
    modelled_error = None
    try:
        import cost_model  # noqa: PLC0415 -- only needed on the estimate path
        for _arm, rts in round_trips_by_arm.items():
            if not rts:
                continue
            for rt in rts:
                fbk = cost_model.fee_breakdown({"qty": rt["qty"],
                                                "entry_premium": rt["entry_premium_avg"],
                                                "real_pnl": rt["gross_pnl"]})
                modelled_total += fbk["fee_total_ex_cat"]
            modelled_total += cost_model.CAT_FEE_PER_ARM_DAY
    except Exception as exc:  # noqa: BLE001 -- surfaced in the report, never swallowed
        modelled_ok = False
        modelled_error = f"{type(exc).__name__}: {exc}"

    return {"status": "POSTED" if any_posted else "NOT_POSTED",
            "actual_total": round(actual_total, 4) if any_posted else None,
            "by_arm": by_arm,
            "modelled_total": round(modelled_total, 4) if modelled_ok else None,
            "modelled_available": modelled_ok, "modelled_error": modelled_error}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build(day: str, use_broker: bool = True) -> dict:
    arms = active_arms()
    # /v2/account and /v2/positions have NO historical form -- they describe RIGHT NOW. On a
    # back-dated run they would silently narrate today's equity next to an old day's trades,
    # which is exactly the kind of quiet mislabelling this module exists to prevent. So they
    # are tagged live-only and rendered as n/a unless `day` IS today.
    is_today = (day == et_today_str())
    report: "dict[str, Any]" = {
        "date_et": day, "is_today_et": is_today,
        "generated_at_et": et_now().isoformat(), "arms": arms,
        "counting_rule": ("round trip = one open->flat cycle per (arm, OCC symbol); "
                          "multi-leg exits collapse to ONE trip; crypto excluded"),
    }

    broker_fills: "list[dict]" = []
    fee_rows_by_arm: "dict[str, list[dict]]" = {}
    positions_by_arm: "dict[str, list[dict]]" = {}
    equity_by_arm: "dict[str, dict]" = {}
    broker_errors: "dict[str, str]" = {}
    malformed = 0

    if use_broker:
        creds_all = fb.load_creds()
        for arm in arms:
            creds = creds_all.get(arm)
            if not creds:
                broker_errors[arm] = "no credentials in fleet/secrets.json"
                continue
            try:
                for a in fetch_broker_fills(creds, day):
                    n = normalize_broker_fill(a, arm)
                    if n is None:
                        malformed += 1
                    else:
                        broker_fills.append(n)
                fee_rows_by_arm[arm] = fetch_broker_fees(creds, day)
                pos = _get_json(creds, "/v2/positions")
                positions_by_arm[arm] = [p for p in pos if isinstance(p, dict)]
                acct = _get_json(creds, "/v2/account")
                equity_by_arm[arm] = {
                    "account_number": acct.get("account_number"),
                    "equity": float(acct.get("equity")),
                    "last_equity": float(acct.get("last_equity")),
                    "equity_delta": round(float(acct.get("equity"))
                                          - float(acct.get("last_equity")), 2),
                    "accrued_fees": acct.get("accrued_fees"),
                    "pending_reg_taf_fees": acct.get("pending_reg_taf_fees"),
                }
            except Exception as exc:  # noqa: BLE001 -- recorded, never silently ignored
                broker_errors[arm] = f"{type(exc).__name__}: {exc}"

    ledger_fills = load_ledger_fills(day, arms)
    broker_rts, broker_leftover = round_trips(broker_fills)
    ledger_rts, ledger_leftover = round_trips(ledger_fills)

    rec = reconcile(broker_fills, ledger_fills, broker_rts, ledger_rts)
    fifo = reconcile_fifo_lib(day, arms, ledger_fills)

    broker_complete = use_broker and not broker_errors
    # AUTHORITY: the broker view, whenever it is complete. NEVER the ledger by preference.
    authoritative = broker_rts if broker_complete else ledger_rts
    source = "broker (authority)" if broker_complete else "ledger -- UNVERIFIED, broker not read"

    rts_by_arm: "dict[str, list[dict]]" = {a: [] for a in arms}
    for rt in authoritative:
        rts_by_arm.setdefault(rt["arm"], []).append(rt)

    per_arm = {}
    for arm in arms:
        rts = rts_by_arm.get(arm, [])
        wins = [r for r in rts if r["gross_pnl"] > 0]
        per_arm[arm] = {
            "n_round_trips": len(rts),
            "gross_pnl": round(sum(r["gross_pnl"] for r in rts), 2),
            "n_win": len(wins), "n_loss": len(rts) - len(wins),
            "n_multi_leg_exits": sum(1 for r in rts if r["n_exit_legs"] > 1),
            "n_scale_ins": sum(1 for r in rts if r["n_entry_legs"] > 1),
            "n_open_positions_live": len(positions_by_arm.get(arm, [])),
            "equity_live": equity_by_arm.get(arm, {}),
        }

    gross = round(sum(r["gross_pnl"] for r in authoritative), 2)
    fees = fee_summary(fee_rows_by_arm, rts_by_arm)
    if fees["status"] == "POSTED":
        net = round(gross + fees["actual_total"], 2)  # FEE net_amount rows are negative
        net_basis = "ACTUAL broker fees"
    elif fees["modelled_available"]:
        net = round(gross - fees["modelled_total"], 2)
        net_basis = "MODELLED fees -- broker has NOT posted this day's FEE rows yet"
    else:
        net = None
        net_basis = "UNAVAILABLE -- no posted fees and cost_model unavailable"

    crypto = crypto_activity(broker_fills if broker_complete else ledger_fills)

    problems = list(rec["problems"]) + list(fifo["problems"])
    if malformed:
        problems.append(f"{malformed} broker FILL row(s) were malformed and could not be "
                        f"normalized -- counted here, NOT silently dropped")
    if broker_leftover:
        problems.append(f"{len(broker_leftover)} unclosed/anomalous option lot(s) in the "
                        f"broker view")

    if not broker_complete:
        verdict, exit_code = "UNVERIFIED", EXIT_BROKER_UNREACHABLE
    elif problems:
        verdict, exit_code = "UNRECONCILED", EXIT_UNRECONCILED
    else:
        verdict, exit_code = "RECONCILED", EXIT_OK

    report.update({
        "verdict": verdict, "exit_code": exit_code, "authority": source,
        "n_round_trips": len(authoritative), "gross_pnl": gross,
        "fees": fees, "net_pnl": net, "net_basis": net_basis,
        "per_arm": per_arm, "round_trips": authoritative,
        "open_positions_live": {a: positions_by_arm.get(a, []) for a in arms},
        "live_snapshot_note": ("equity_live / open_positions_live are RIGHT-NOW broker "
                               "reads; Alpaca exposes no as-of form. They describe "
                               f"{et_today_str()}, not necessarily {day}."),
        "n_option_fills_broker": sum(1 for f in broker_fills if f["is_option"]),
        "n_option_fills_ledger": sum(1 for f in ledger_fills if f.get("is_option")),
        "crypto_excluded": crypto,
        "reconciliation": rec, "fifo_lib_check": fifo,
        "broker_errors": broker_errors, "malformed_broker_rows": malformed,
        "open_or_anomalous_lots": broker_leftover + ledger_leftover,
        "freshness": freshness(day, broker_fills, ledger_fills),
        "problems": problems,
    })
    return report


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(rep: dict) -> str:
    L: "list[str]" = []
    a = L.append
    a("=" * 78)
    a(f"DAY SUMMARY  {rep['date_et']}   VERDICT: {rep['verdict']}")
    a(f"authority: {rep['authority']}    generated {rep['generated_at_et'][:19]} ET")
    a("=" * 78)
    a(f"ROUND TRIPS : {rep['n_round_trips']}")
    a(f"GROSS P&L   : ${rep['gross_pnl']:,.2f}")
    f = rep["fees"]
    if f["status"] == "POSTED":
        a(f"FEES        : ${f['actual_total']:,.2f}   ACTUAL (broker FEE activity)")
    else:
        m = (f"${f['modelled_total']:,.2f}" if f["modelled_available"]
             else f"unavailable ({f['modelled_error']})")
        a(f"FEES        : NOT POSTED by the broker for this trade date; "
          f"modelled estimate {m}")
    a("NET P&L     : " + (f"${rep['net_pnl']:,.2f}" if rep["net_pnl"] is not None else "n/a")
      + f"   [{rep['net_basis']}]")
    a("")
    live = rep["is_today_et"]
    if not live:
        a("NOTE: this is a BACK-DATED run. Equity / open-position columns are live-now "
          "broker reads")
        a(f"      (Alpaca has no as-of form), so they are shown as n/a rather than "
          f"mislabelled as {rep['date_et']}.")
    a(f"{'arm':9s} {'RT':>3s} {'W':>3s} {'L':>3s} {'mlegX':>6s} {'gross':>9s} "
      f"{'open*':>5s} {'equity*':>10s} {'d(equity)*':>11s}")
    for arm, s in rep["per_arm"].items():
        eq = s["equity_live"]
        eq_s = f"{eq['equity']:10,.2f}" if (live and "equity" in eq) else f"{'n/a':>10s}"
        dq_s = (f"{eq['equity_delta']:11,.2f}" if (live and "equity_delta" in eq)
                else f"{'n/a':>11s}")
        op_s = f"{s['n_open_positions_live']:5d}" if live else f"{'n/a':>5s}"
        a(f"{arm:9s} {s['n_round_trips']:3d} {s['n_win']:3d} {s['n_loss']:3d} "
          f"{s['n_multi_leg_exits']:6d} {s['gross_pnl']:9,.2f} {op_s} {eq_s} {dq_s}")
    a("      * = live-now broker read, not an as-of-date value")
    a("")
    a("ROUND TRIPS (ONE row per open->flat cycle; legs = entries x exits):")
    a(f"  {'arm':9s} {'symbol':20s} {'qty':>4s} {'in':>8s} {'out':>8s} {'legs':>5s} "
      f"{'entry':>7s} {'exit':>7s} {'gross':>9s}")
    for r in rep["round_trips"]:
        a(f"  {r['arm']:9s} {r['symbol']:20s} {r['qty']:4d} "
          f"{r['entry_ts_et'][11:19]:>8s} {r['exit_ts_et'][11:19]:>8s} "
          f"{str(r['n_entry_legs']) + 'x' + str(r['n_exit_legs']):>5s} "
          f"{r['entry_premium_avg']:7.4f} {r['exit_premium_avg']:7.4f} "
          f"{r['gross_pnl']:9,.2f}")
    a("")
    a(f"fill counts  : broker {rep['n_option_fills_broker']} option executions, "
      f"ledger {rep['n_option_fills_ledger']}")
    ce = rep["crypto_excluded"]
    a(f"crypto       : {ce['n_fills']} fill(s) / {ce['n_round_trips']} round trip(s) "
      f"EXCLUDED from the count above (notional {ce['notional_pnl']:+.4f}, dust "
      f"{ce['unclosed_dust_qty']:.3e}) -- not SPY, by design")
    rc = rep["reconciliation"]
    a(f"reconcile A/B: broker {rc['broker_n_round_trips']} RT / ${rc['broker_gross']:,.2f}"
      f"   vs   ledger {rc['ledger_n_round_trips']} RT / ${rc['ledger_gross']:,.2f}")
    fl = rep["fifo_lib_check"]
    a(f"reconcile B/C: engine-only {fl['engine_n_round_trips']} RT / "
      f"${fl['engine_gross']:,.2f}   vs   fills_fifo lib {fl['fifo_lib_n_round_trips']} RT / "
      f"${fl['fifo_lib_gross']:,.2f}")
    fr = rep["freshness"]
    a(f"freshness    : ledger last written {fr['ledger_mtime_et']} ET")
    a(f"               OPTION lag broker-vs-ledger: {fr['option_lag_seconds']}s "
      f"(broker {str(fr['last_broker_option_fill_et'])[11:19]} / "
      f"ledger {str(fr['last_ledger_option_fill_et'])[11:19]})")
    a(f"               ALL-fill lag (incl. crypto): {fr['any_fill_lag_seconds']}s "
      f"(broker {str(fr['last_broker_any_fill_et'])[11:19]} / "
      f"ledger {str(fr['last_ledger_any_fill_et'])[11:19]})")
    n_open = sum(len(v) for v in rep["open_positions_live"].values())
    a(f"open NOW     : {n_open} broker position(s) across all arms "
      f"(live read at {rep['generated_at_et'][11:19]} ET)")
    for arm, ps in rep["open_positions_live"].items():
        for p in ps:
            a(f"               {arm} {p.get('symbol')} qty={p.get('qty')} "
              f"avg={p.get('avg_entry_price')} upl={p.get('unrealized_pl')}")
    if rep["broker_errors"]:
        a("")
        a("BROKER ERRORS -- verdict forced to UNVERIFIED (no ledger fallback):")
        for arm, err in rep["broker_errors"].items():
            a(f"  {arm}: {err}")
    if rep["problems"]:
        a("")
        a("PROBLEMS:")
        for p in rep["problems"]:
            a(f"  - {p}")
    a("")
    a(f"VERDICT: {rep['verdict']}  (exit {rep['exit_code']})")
    return "\n".join(L)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Canonical broker-truth day summary.")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    ap.add_argument("--no-broker", action="store_true",
                    help="ledger only; always UNVERIFIED / exit 3 by design")
    args = ap.parse_args(argv)

    day = args.date or et_today_str()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        print(f"bad --date {day!r}; expected YYYY-MM-DD", file=sys.stderr)
        return EXIT_USAGE

    rep = build(day, use_broker=not args.no_broker)
    print(json.dumps(rep, indent=2) if args.json else render(rep))
    return rep["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
