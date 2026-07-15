"""spread_executor -- vertical DEBIT-spread order machinery (Alpaca mleg).

BUILT DISARMED (2026-07-14, EDGE-2-DEBIT-SPREAD-AB build lane). This module is
pure execution machinery so that IF the parallel pre-registered A/B study
(analysis/recommendations/debit-spread-ab.json, produced by a separate lane)
clears the OP-11 eval-first gates, arming is a params flag-flip, not a build.
NOTHING imports this on the live path yet -- heartbeat_core wiring is a
separate, post-scorecard step (see INTEGRATION POINT below).

WHY DEBIT SPREADS (markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md)
--------------------------------------------------------------------------------
The losing retail-0DTE cohort's exact profile is ours: single-leg, ATM/OTM,
upfront debit. In the same dataset, multi-leg is "significantly MORE
profitable": the short leg sells back part of the 0DTE variance risk premium,
cuts theta bleed, and defines risk. A vertical DEBIT spread pays its net debit
in full -> viable in a CASH account (credit spreads/naked shorts are not).

ALPACA MLEG API (verified against docs.alpaca.markets 2026-07-14)
------------------------------------------------------------------
POST /v2/orders with order_class="mleg", qty=<spreads>, type="limit",
time_in_force="day", legs=[{symbol, ratio_qty, side, position_intent}].
- position_intent: buy_to_open / sell_to_open / buy_to_close / sell_to_close.
- limit_price SIGN CONVENTION (docs.alpaca.markets/reference/postorder):
  "A positive value indicates a debit ... A negative value signifies a
  credit" -- so OPEN (pay net debit) is POSITIVE, CLOSE (receive net credit)
  is NEGATIVE.
- GCD of ratio_qty values must be 1; all legs covered within the same order;
  no equity legs. Brackets/OTO remain unsupported on options (Alpaca 42210000;
  memory: project_alpaca_options_no_brackets) -- exit_manager owns TP/stop;
  the spread is exited via ONE closing mleg (close_spread below).

ARMED GATING (OP-11 / never-armed-by-default)
---------------------------------------------
submit_spread refuses unless params["spread_execution_enabled"] is the bool
True. The key ships FALSE in BOTH automation/state/params.json and
automation/state/aggressive/params.json and flips ONLY per the A/B scorecard
(OP-11: OOS_positive AND WF >= 0.70 AND sub_window_stable AND
anchor_no_regression). close_spread is NEVER gated -- an exit must never be
blocked by a config flag (fail-open doctrine, OP-25).

CASH-ACCOUNT SETTLEMENT (Rule 7, setup/scripts/settlement_ledger.py)
--------------------------------------------------------------------
A spread's net debit is paid in full from settled cash exactly like a
single-leg premium. On successful placement, submit_spread records
notional = net_debit * qty * 100 into the same per-account settlement ledger
heartbeat_core._execute feeds (commit fd09a78), so the Rule-7 cash-settlement
gate sees spread capital commitments identically.

SHORT-LEG / PIN RISK (SPY = PHYSICAL settlement)
-------------------------------------------------
SPY options settle in SHARES, not cash. If only the SHORT leg finishes ITM at
expiry (spot pins between the strikes), assignment delivers/demands 100 shares
per contract -- ~$56K of SPY neither core account (~$1.7K) can carry. The long
leg only covers assignment when BOTH legs finish ITM. HARD GUARD: the short
leg must never be open into the close -- both legs are closed together by
SPREAD_CLOSE_DEADLINE_ET (default 15:45 ET, ahead of the 15:50 flatten /
15:55 EodFlatten safety net). This module enforces the OPEN side (no new
spread at/after the deadline); the post-scorecard exit_manager integration
MUST call close_spread when past_close_deadline() fires on any open spread.

INTEGRATION POINT (post-scorecard, NOT in this build)
------------------------------------------------------
heartbeat_core._execute, AFTER risk_gate.check_order approves the single-leg
plan: when is_armed(params), replace _place_simple_entry with
build_debit_spread_legs -> net_debit_limit -> submit_spread(settlement_ctx=...)
and register both legs with exit_manager; exit_manager's per-tick close path
and the 15:45 deadline both route through close_spread. Until that ship, the
only callers are tests and the read-only --dry-run CLI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ, et_now  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MCP_JSON = PROJECT_ROOT / ".mcp.json"
_SERVER_MAP = {"safe": "alpaca", "bold": "alpaca_aggressive"}

ARMED_PARAM_KEY = "spread_execution_enabled"
DEFAULT_WIDTH = 1
SPREAD_CLOSE_DEADLINE_ET = "15:45"
OPTIONS_DATA_HOST = "https://data.alpaca.markets"

_OCC_RE = re.compile(r"^(?P<und>[A-Z]{1,6})(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


# ---------------------------------------------------------------- OCC symbols
def parse_occ(symbol: str) -> Optional[dict]:
    """Parse an OCC symbol (e.g. SPY260715C00625000) -> {underlying, expiry
    'YYMMDD', cp 'C'|'P', strike float}. None when it doesn't parse."""
    m = _OCC_RE.match(str(symbol or "").strip())
    if not m:
        return None
    return {"underlying": m["und"], "expiry": m["exp"], "cp": m["cp"],
            "strike": int(m["strike"]) / 1000.0}


def occ_symbol(cp: str, strike: float, expiry_yymmdd: str, underlying: str = "SPY") -> str:
    return f"{underlying}{expiry_yymmdd}{cp}{int(round(strike * 1000)):08d}"


def normalize_chain(chain: Any) -> list[dict]:
    """Accept an Alpaca chain in any of the shapes we see in this repo --
    iterable of OCC strings, iterable of contract dicts with a 'symbol' key
    (GET /v2/options/contracts), or a dict keyed by symbol (MCP snapshot) --
    and return parsed [{symbol, underlying, expiry, cp, strike}]. Unparseable
    entries are skipped (validated downstream by build_debit_spread_legs)."""
    if isinstance(chain, dict):
        symbols: Iterable[Any] = chain.keys()
    else:
        symbols = chain or []
    out: list[dict] = []
    for item in symbols:
        sym = item.get("symbol") if isinstance(item, dict) else item
        parsed = parse_occ(sym) if sym else None
        if parsed:
            parsed["symbol"] = str(sym)
            out.append(parsed)
    return out


# ---------------------------------------------------------- leg construction
def build_debit_spread_legs(side: str, spy_px: float, chain: Any,
                            width: int = DEFAULT_WIDTH) -> list[dict]:
    """Build the 2 legs of a vertical DEBIT spread: long ATM + short `width`
    strikes further OTM, both selected FROM the supplied chain (never invented
    symbols). side: 'C' (bull call debit) or 'P' (bear put debit), matching
    strike_selection.py's convention. ATM = round(spy_px) (strike_selection.
    atm_strike; V15_SAFE_TIERS trades ATM under $10K). When the chain spans
    multiple expiries, the EARLIEST expiry containing both strikes wins
    (0DTE-first). Raises ValueError on any invalid input -- fail fast at the
    boundary; the order path's refusal dicts live in submit_spread."""
    if side not in ("C", "P"):
        raise ValueError(f"side must be 'C' or 'P', got {side!r}")
    if not isinstance(width, int) or width < 1:
        raise ValueError(f"width must be an int >= 1, got {width!r}")
    if not spy_px or float(spy_px) <= 0:
        raise ValueError(f"spy_px must be positive, got {spy_px!r}")
    atm = int(round(float(spy_px)))
    long_strike = float(atm)
    short_strike = float(atm + width) if side == "C" else float(atm - width)
    contracts = [c for c in normalize_chain(chain) if c["cp"] == side]
    if not contracts:
        raise ValueError(f"chain has no {side} contracts to build from")

    def _find(expiry: str, strike: float) -> Optional[dict]:
        for c in contracts:
            if c["expiry"] == expiry and abs(c["strike"] - strike) < 1e-6:
                return c
        return None

    for expiry in sorted({c["expiry"] for c in contracts}):
        long_c = _find(expiry, long_strike)
        short_c = _find(expiry, short_strike)
        if long_c and short_c:
            return [
                {"symbol": long_c["symbol"], "ratio_qty": "1",
                 "side": "buy", "position_intent": "buy_to_open"},
                {"symbol": short_c["symbol"], "ratio_qty": "1",
                 "side": "sell", "position_intent": "sell_to_open"},
            ]
    raise ValueError(
        f"chain missing strikes for {side} debit spread: long {long_strike} "
        f"+ short {short_strike} not both present in any single expiry")


def validate_spread_legs(legs: Any) -> Optional[str]:
    """Structural validation of OPENING legs. Returns an error string or None.
    Enforces: exactly 2 legs, 1:1 ratio, buy_to_open + sell_to_open, same
    underlying/expiry/type, distinct strikes, and DEBIT geometry (the long leg
    is closer to the money -- calls: buy < sell; puts: buy > sell). Credit
    geometry is refused outright: margin + assignment tail we cannot carry."""
    if not isinstance(legs, list) or len(legs) != 2:
        return "exactly 2 legs required"
    parsed = []
    for leg in legs:
        if not isinstance(leg, dict):
            return "legs must be dicts"
        if str(leg.get("ratio_qty")) != "1":
            return f"ratio_qty must be '1' for a 1:1 vertical, got {leg.get('ratio_qty')!r}"
        p = parse_occ(leg.get("symbol", ""))
        if not p:
            return f"unparseable OCC symbol {leg.get('symbol')!r}"
        p["intent"] = leg.get("position_intent")
        p["side"] = leg.get("side")
        parsed.append(p)
    intents = {p["intent"] for p in parsed}
    if intents != {"buy_to_open", "sell_to_open"}:
        return f"opening legs must be buy_to_open + sell_to_open, got {sorted(map(str, intents))}"
    buy = next(p for p in parsed if p["intent"] == "buy_to_open")
    sell = next(p for p in parsed if p["intent"] == "sell_to_open")
    if buy["side"] != "buy" or sell["side"] != "sell":
        return "leg side does not match its position_intent"
    if buy["underlying"] != sell["underlying"]:
        return "legs must share an underlying"
    if buy["expiry"] != sell["expiry"]:
        return f"legs must share an expiry, got {buy['expiry']} vs {sell['expiry']}"
    if buy["cp"] != sell["cp"]:
        return "legs must be the same type (both C or both P)"
    if abs(buy["strike"] - sell["strike"]) < 1e-6:
        return "legs must have distinct strikes"
    if buy["cp"] == "C" and not buy["strike"] < sell["strike"]:
        return "call DEBIT spread requires long strike < short strike (credit geometry refused)"
    if buy["cp"] == "P" and not buy["strike"] > sell["strike"]:
        return "put DEBIT spread requires long strike > short strike (credit geometry refused)"
    return None


def spread_width(legs: list[dict]) -> float:
    """Strike distance between the two legs (dollars) -- the spread's max value."""
    strikes = [parse_occ(leg["symbol"])["strike"] for leg in legs]
    return abs(strikes[0] - strikes[1])


# --------------------------------------------------------------- limit pricing
def _mid(quote: Any) -> Optional[float]:
    if not isinstance(quote, dict):
        return None
    bid, ask = quote.get("bp"), quote.get("ap")
    if bid and ask and bid > 0 and ask > 0:
        return (bid + ask) / 2
    return None


def net_debit_limit(long_quote: Any, short_quote: Any, mode: str = "mid") -> Optional[float]:
    """Net-debit limit for the OPENING mleg from the two legs' latest quotes
    ({'bp': bid, 'ap': ask} -- the Alpaca v1beta1 latest-quotes shape,
    fleet_broker.get_option_mid's exact source). mode='mid' = long mid - short
    mid (passive-ish; the EDGE-1 friction finding favors non-marketable);
    mode='marketable' = long ask - short bid (pay up to fill now). Rounded to
    cents, floored at $0.01. None when either quote is unusable."""
    if mode == "mid":
        long_px, short_px = _mid(long_quote), _mid(short_quote)
    elif mode == "marketable":
        long_px = long_quote.get("ap") if isinstance(long_quote, dict) else None
        short_px = short_quote.get("bp") if isinstance(short_quote, dict) else None
    else:
        raise ValueError(f"mode must be 'mid' or 'marketable', got {mode!r}")
    if not long_px or not short_px or long_px <= 0 or short_px <= 0:
        return None
    return max(0.01, round(float(long_px) - float(short_px), 2))


def close_credit_limit(long_quote: Any, short_quote: Any) -> Optional[float]:
    """Marketable MIN-CREDIT to close (sell long at bid, buy short back at
    ask): long bid - short ask, floored at $0.01. None when unusable. The
    caller passes this to close_spread(min_credit=...); the payload carries it
    NEGATIVE per Alpaca's sign convention (negative = credit received)."""
    long_bid = long_quote.get("bp") if isinstance(long_quote, dict) else None
    short_ask = short_quote.get("ap") if isinstance(short_quote, dict) else None
    if not long_bid or not short_ask or long_bid <= 0 or short_ask <= 0:
        return None
    return max(0.01, round(float(long_bid) - float(short_ask), 2))


# ------------------------------------------------------------------- gating
def is_armed(params: Any) -> bool:
    """True ONLY when params carries the literal bool True for
    spread_execution_enabled. Absent key, None, False, 1, 'true' -> DISARMED.
    Guard: backtest/tests/test_spread_executor.py (never-armed-by-default)."""
    return isinstance(params, dict) and params.get(ARMED_PARAM_KEY) is True


def past_close_deadline(now_et: datetime, deadline: str = SPREAD_CLOSE_DEADLINE_ET) -> bool:
    """True at/after the both-legs-must-be-closed ET wall-clock deadline.
    PURE -- caller supplies now_et from et_clock (never Bash TZ)."""
    h, m = str(deadline).split(":")
    return now_et.time() >= dtime(int(h), int(m))


def spread_notional(net_debit: float, qty: int) -> float:
    """Settled-cash commitment of a debit spread: net debit paid in full."""
    return float(net_debit) * int(qty) * 100.0


# ------------------------------------------------------------------ broker IO
def load_core_creds(account: str) -> dict:
    """Core-account creds from the gitignored .mcp.json (the ONLY credential
    store -- CLAUDE.md secrets rule; pattern: fast_path_executor.py). Loaded
    lazily so tests never need the file."""
    server = _SERVER_MAP.get(account)
    if not server:
        raise ValueError(f"account must be one of {sorted(_SERVER_MAP)}, got {account!r}")
    env = json.loads(_MCP_JSON.read_text(encoding="utf-8"))["mcpServers"][server]["env"]
    return {"key": env["ALPACA_API_KEY"], "secret": env["ALPACA_SECRET_KEY"],
            "base_url": env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")}


def _request(creds: dict, endpoint: str, method: str = "GET",
             data: dict | None = None, timeout: int = 15,
             host: str | None = None) -> Any:
    """Alpaca REST -- byte-for-byte the fleet_broker._request error contract
    ({_error,...} on failure, parsed JSON on success)."""
    base = (host or creds["base_url"]).rstrip("/")
    prefix = "" if host else "/v2"
    url = f"{base}{prefix}/{endpoint.lstrip('/')}"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"],
               "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            err = {"raw": str(e)}
        return {"_error": str(e), "_status": e.code, "_body": err}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"_error": str(e)}


def submit_spread(creds: dict, legs: list[dict], qty: int, limit_price: float, *,
                  params: dict, now_et: datetime | None = None,
                  settlement_ctx: dict | None = None, tif: str = "day") -> dict:
    """Submit the OPENING vertical-debit mleg. Refusal-dict contract (never
    raises on a gate) mirrors heartbeat_core._place_simple_entry.

    Gate order: (1) ARMED flag -- params[spread_execution_enabled] is True,
    else {'_refused': 'SPREAD_DISARMED'}; (2) leg structure (validate_spread_
    legs); (3) qty >= 1; (4) 0 < limit < strike width (a vertical's value is
    capped AT width -- paying >= width is a guaranteed loss, always a pricing
    bug); (5) short-leg deadline -- no NEW spread at/after
    SPREAD_CLOSE_DEADLINE_ET (see module docstring, pin risk).

    settlement_ctx (optional) = {'state_dir': Path, 'account': 'safe'|'bold',
    'sod_settled_cash': float} -> on successful placement the net debit's
    notional is recorded into the SAME Rule-7 settlement ledger heartbeat_core
    feeds (settlement_ledger.record_entry; ledger write failures are fail-open
    per that module's contract and never undo a placed order)."""
    if not is_armed(params):
        return {"_refused": "SPREAD_DISARMED",
                "_note": f"params.{ARMED_PARAM_KEY} is not True -- flips only per "
                         "the debit-spread A/B scorecard (OP-11)"}
    err = validate_spread_legs(legs)
    if err:
        return {"_refused": f"BAD_LEGS: {err}"}
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty!r}"}
    width = spread_width(legs)
    if limit_price is None or float(limit_price) <= 0:
        return {"_refused": f"invalid limit_price {limit_price!r} (open = positive net debit)"}
    if float(limit_price) >= width:
        return {"_refused": f"DEBIT_GE_WIDTH: net debit {limit_price} >= strike width "
                            f"{width} -- max spread value is the width; refusing a "
                            "guaranteed-loss fill"}
    now = now_et or et_now()
    deadline = str(params.get("spread_close_deadline_et") or SPREAD_CLOSE_DEADLINE_ET)
    if past_close_deadline(now, deadline):
        return {"_refused": "SHORT_LEG_DEADLINE",
                "_note": f"no new spread at/after {deadline} ET -- short leg must "
                         "never be open into the close (SPY physical-settlement pin risk)"}
    order = {"order_class": "mleg", "qty": str(int(qty)), "type": "limit",
             "limit_price": str(round(float(limit_price), 2)),
             "time_in_force": tif, "legs": legs}
    res = _request(creds, "orders", method="POST", data=order)
    if not isinstance(res, dict):
        return {"_error": f"unexpected broker response: {res!r}"}
    if not res.get("_error") and settlement_ctx:
        try:
            import settlement_ledger as sl  # noqa: PLC0415
            path = sl.ledger_path(Path(settlement_ctx["state_dir"]), settlement_ctx["account"])
            sl.record_entry(path, now.strftime("%Y-%m-%d"),
                            float(settlement_ctx["sod_settled_cash"]),
                            spread_notional(float(limit_price), int(qty)),
                            now.strftime("%Y-%m-%dT%H:%M:%S"))
            res["_settlement_recorded"] = True
        except Exception as e:  # noqa: BLE001 -- ledger visibility must never undo a placed order
            res["_settlement_recorded"] = False
            res["_settlement_error"] = f"{type(e).__name__}: {e}"[:120]
    return res


def close_spread(creds: dict, position: dict, *, min_credit: float,
                 tif: str = "day") -> dict:
    """Close BOTH legs in ONE mleg: sell_to_close the long + buy_to_close the
    short (brackets/OTO unsupported on options -- exit_manager owns exits and
    calls this). position = {'long_symbol', 'short_symbol', 'qty'}.

    DELIBERATELY UNGATED: no ARMED check, no deadline check -- an exit must
    never be blocked by a config flag (fail-open, OP-25). min_credit is the
    POSITIVE minimum acceptable credit (see close_credit_limit); the payload
    carries limit_price NEGATIVE per Alpaca's mleg sign convention (negative =
    credit to receive)."""
    long_sym = position.get("long_symbol")
    short_sym = position.get("short_symbol")
    qty = position.get("qty")
    if not long_sym or not parse_occ(long_sym):
        return {"_refused": f"invalid long_symbol {long_sym!r}"}
    if not short_sym or not parse_occ(short_sym):
        return {"_refused": f"invalid short_symbol {short_sym!r}"}
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty!r}"}
    if min_credit is None or float(min_credit) <= 0:
        return {"_refused": f"invalid min_credit {min_credit!r} (positive; floor $0.01)"}
    legs = [
        {"symbol": long_sym, "ratio_qty": "1",
         "side": "sell", "position_intent": "sell_to_close"},
        {"symbol": short_sym, "ratio_qty": "1",
         "side": "buy", "position_intent": "buy_to_close"},
    ]
    order = {"order_class": "mleg", "qty": str(int(qty)), "type": "limit",
             "limit_price": str(-abs(round(float(min_credit), 2))),
             "time_in_force": tif, "legs": legs}
    res = _request(creds, "orders", method="POST", data=order)
    return res if isinstance(res, dict) else {"_error": f"unexpected broker response: {res!r}"}


# ----------------------------------------------------------- dry-run (READ-only)
def _fetch_spy_last(creds: dict) -> Optional[float]:
    res = _request(creds, "v2/stocks/SPY/trades/latest?feed=iex", host=OPTIONS_DATA_HOST)
    try:
        return float(res["trade"]["p"])
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_chain_symbols(creds: dict, expiry_date: str, lo: float, hi: float) -> list[str]:
    q = urllib.parse.urlencode({"underlying_symbols": "SPY", "expiration_date": expiry_date,
                                "strike_price_gte": f"{lo:.2f}", "strike_price_lte": f"{hi:.2f}",
                                "limit": 500})
    res = _request(creds, f"options/contracts?{q}")
    rows = res.get("option_contracts") if isinstance(res, dict) else None
    return [r["symbol"] for r in rows or [] if isinstance(r, dict) and r.get("symbol")]


def _fetch_leg_quotes(creds: dict, symbols: list[str]) -> dict:
    q = urllib.parse.urlencode({"symbols": ",".join(symbols)})
    res = _request(creds, f"v1beta1/options/quotes/latest?{q}", host=OPTIONS_DATA_HOST)
    return res.get("quotes", {}) if isinstance(res, dict) else {}


def main() -> int:  # pragma: no cover -- CLI shell; logic is unit-tested above
    ap = argparse.ArgumentParser(description="Vertical debit-spread executor (ships DISARMED)")
    ap.add_argument("--dry-run", action="store_true", required=True,
                    help="READ-only: build legs from the real chain + price them. "
                         "This CLI can NEVER submit -- submission requires the armed "
                         "params flag AND a code caller (post-scorecard integration).")
    ap.add_argument("--side", choices=["C", "P"], default="C")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--account", choices=sorted(_SERVER_MAP), default="safe")
    args = ap.parse_args()

    creds = load_core_creds(args.account)
    spot = _fetch_spy_last(creds)
    if not spot:
        print(json.dumps({"error": "could not read SPY last trade"}))
        return 1
    now = et_now()
    legs = None
    for d in range(0, 6):  # today (0DTE) first; after-hours falls to the next listed expiry
        expiry = (now + timedelta(days=d)).strftime("%Y-%m-%d")
        chain = _fetch_chain_symbols(creds, expiry, spot - 10, spot + 10)
        try:
            legs = build_debit_spread_legs(args.side, spot, chain, args.width)
            break
        except ValueError:
            continue
    if not legs:
        print(json.dumps({"error": "no expiry within 5 days had both strikes", "spot": spot}))
        return 1
    quotes = _fetch_leg_quotes(creds, [leg["symbol"] for leg in legs])
    lq, sq = quotes.get(legs[0]["symbol"]), quotes.get(legs[1]["symbol"])
    live_params_path = PROJECT_ROOT / "automation" / "state" / "params.json"
    live_params = json.loads(live_params_path.read_text(encoding="utf-8"))
    print(json.dumps({
        "mode": "DRY-RUN -- NO ORDER SUBMITTED",
        "armed": is_armed(live_params),
        "spy_spot": spot,
        "side": args.side, "width": args.width, "qty": args.qty,
        "legs": legs,
        "quotes": {"long": lq, "short": sq},
        "net_debit_limit_mid": net_debit_limit(lq, sq, "mid"),
        "net_debit_limit_marketable": net_debit_limit(lq, sq, "marketable"),
        "notional_at_mid": (spread_notional(net_debit_limit(lq, sq, "mid"), args.qty)
                            if net_debit_limit(lq, sq, "mid") else None),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
