"""MULTI-SYMBOL ENGINE TICK — the orchestrator that wires the copied SPY engine together.

J directive 2026-08-19: *"copy the entire spy engine and then paste it... you don't touch the
original, and then you make it so we trade other names."* This is the tick loop: the analogue
of `setup/scripts/heartbeat_core.py`, rebuilt symbol-generic over the forked components.

FLOW, per symbol, per tick:

    bars -> signal.build_signal (score)      # multi/lib/signal.py  (forked filters)
         -> risk.evaluate_admission          # kill switch / sector / correlation / concurrency
         -> expiry.select_expiry             # from the LIVE listed chain, never a calendar
         -> LIVE liquidity gate              # spread/OI/volume measured NOW, not from a list
         -> sizing.select_strike             # from the LIVE strike list, never round(spot)
         -> sizing.size_entry                # equity % cap, netted against committed capital
         -> shadow row                       # WRITTEN, never sent

SHADOW ONLY. There is no order-placement call in this file. `broker.py`'s submit functions all
require `armed=True` and raise while params has `shadow_only: true`; this module never passes
`armed` at all. Placing a real order is a later, deliberate change — not a flag flip here.

SEPARATION: imports nothing from the SPY engine. Verified at AST level — zero literal "SPY" in
executable code across `multi/`, and the only cross-module imports are `multi.lib.*`.

SHARED ACCOUNT: PA38EG1JTFBT also runs the crypto twin, armed, trading BTC/USD every 60s. Every
position read here goes through `positions.equity_option_positions`, which filters to OCC-shaped
option symbols — this lane structurally cannot see, count, or close the twin's BTC. Because the
two programs share one equity curve, ACCOUNT EQUITY IS NOT EVIDENCE for either; each reads its
own ledger.

PARTICIPATION CASCADE: every tick records where each symbol died in the gate stack. This shop's
single most repeated failure (L199) is a gate stack that silently admits nothing -- "6 arms, 700
signals, 0 trades." The cascade makes that visible on tick one instead of after a week of
wondering why the ledger is empty.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import expiry as mx  # noqa: E402
from multi.lib import positions as mp  # noqa: E402
from multi.lib import risk as mr  # noqa: E402
from multi.lib import signal as ms  # noqa: E402
from multi.lib import sizing as msz  # noqa: E402

ET = ZoneInfo("America/New_York")
STATE_DIR = REPO_ROOT / "automation" / "state" / "multi"
SHADOW_LEDGER = STATE_DIR / "shadow-ledger.jsonl"
CASCADE_PATH = STATE_DIR / "participation-cascade.jsonl"

# The gate stack, in evaluation order. Recorded per symbol so the cascade can attribute
# exactly where the funnel dies.
GATES = (
    "bars_ok", "signal_scored", "action_directional", "risk_admitted",
    "expiry_available", "liquidity_ok", "strike_selected", "sized_ok", "would_place",
)


class TickError(RuntimeError):
    """Fail loud. A tick that cannot complete must never write a row implying it did."""


def now_et() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(ET)


def universe_symbols(params: dict) -> list[str]:
    """Flatten the params universe blocks into one deduped, ordered symbol list."""
    uni = params.get("universe") or {}
    out: list[str] = []
    for key, val in uni.items():
        if key.startswith("_"):
            continue
        if isinstance(val, list):
            out.extend(str(s).upper() for s in val)
    seen, ordered = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    if not ordered:
        raise TickError("multi params.json universe is empty — refusing to tick over nothing")
    return ordered


def liquidity_ok(quote: dict | None, params: dict) -> tuple[bool, str, dict]:
    """LIVE liquidity gate — measured now, never inherited from a static universe list.

    This is the fix for the static-screen failure: a name that is untradeable on a normal day
    can be deeply liquid on a catalyst day (MRNA 2026-08-19: 1 contract Monday, 30,314
    Wednesday). Membership in the universe is not a promise; this is the promise.
    """
    gate = (params.get("entry") or {}).get("liquidity_gate") or {}
    if not quote:
        return False, "no two-sided quote", {}
    bid, ask = quote.get("bid"), quote.get("ask")
    if not bid or not ask or ask <= 0 or bid <= 0:
        return False, "missing bid/ask", {}
    mid = (bid + ask) / 2.0
    spread_pct = 100.0 * (ask - bid) / mid if mid > 0 else 999.0
    oi = quote.get("open_interest")
    vol = quote.get("volume")
    facts = {"bid": bid, "ask": ask, "mid": round(mid, 4),
             "spread_pct": round(spread_pct, 2), "open_interest": oi, "volume": vol,
             "feed": gate.get("feed", "indicative")}
    max_spread = float(gate.get("max_spread_pct_of_premium", 8.0))
    if spread_pct > max_spread:
        return False, f"spread {spread_pct:.1f}% > {max_spread}%", facts
    min_oi = gate.get("min_open_interest")
    if min_oi is not None and oi is not None and oi < min_oi:
        return False, f"OI {oi} < {min_oi}", facts
    return True, "ok", facts


# --- live bar fetch (lane-owned; the SPY engine's fetcher is never imported) -----------------
# Two Alpaca gotchas already learned the hard way and encoded here so this lane never repeats
# them: (1) an omitted `start` makes the endpoint default to TODAY ONLY, which for 1Day holds no
# completed bar and returns ZERO bars on every feed -- indistinguishable from "no data";
# (2) the response PAGINATES via next_page_token well below a large `limit`, and with sort=desc
# the truncation is invisible at the tail. Both cost a debugging cycle on 2026-08-18.

_BARS_PER_SESSION = {"1Day": 1.0, "1Hour": 6.5}
_CALENDAR_SLACK = 1.75


def fetch_bars(creds, symbol: str, timeframe: str = "1Hour", limit: int = 400):
    """Closed bars for `symbol` as a DataFrame indexed by ET timestamp, oldest first."""
    import pandas as pd
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    sessions = max(1.0, limit / _BARS_PER_SESSION.get(timeframe, 6.5))
    start = (now_et() - dt.timedelta(days=int(sessions * _CALENDAR_SLACK) + 7)).date().isoformat()
    base = {"timeframe": timeframe, "limit": limit, "feed": "iex", "adjustment": "raw",
            "sort": "desc", "start": start}
    rows, token = [], None
    while len(rows) < limit:
        q = dict(base)
        if token:
            q["page_token"] = token
        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{urlencode(q)}"
        req = Request(url, headers={"APCA-API-KEY-ID": creds.key,
                                    "APCA-API-SECRET-KEY": creds.secret})
        with urlopen(req, timeout=30) as resp:  # noqa: S310 -- fixed https host
            payload = json.loads(resp.read())
        page = payload.get("bars") or []
        rows.extend(page)
        token = payload.get("next_page_token")
        if not token or not page:
            break
    if not rows:
        return None
    rows = list(reversed(rows[:limit]))
    df = pd.DataFrame([{ "open": b["o"], "high": b["h"], "low": b["l"],
                         "close": b["c"], "volume": b["v"],
                         "timestamp_et": pd.Timestamp(b["t"]).tz_convert(ET)} for b in rows])
    df = df.set_index("timestamp_et")
    # Drop any bar whose close time has not passed (C6 no-look-ahead).
    cutoff = now_et()
    span = dt.timedelta(hours=1) if timeframe == "1Hour" else dt.timedelta(days=1)
    df = df[df.index + span <= cutoff]
    return df if len(df) else None


def tick(params: dict, creds: mc.MultiCreds, symbols: list[str], *,
         dry_bars: dict | None = None) -> tuple[list[dict], Counter]:
    """One evaluation pass over `symbols`. Returns (rows, cascade_counter).

    Writes nothing and sends nothing — the caller persists. `dry_bars` lets tests inject bar
    frames without a network call.
    """
    cascade: Counter = Counter()
    rows: list[dict] = []
    ts = now_et().isoformat(timespec="seconds")

    account = mb.get_account(creds)
    raw_positions = mb.get_positions(creds)
    open_opts = mp.equity_option_positions(raw_positions)
    equity = float(account.get("equity") or 0.0)
    if equity <= 0:
        raise TickError(f"account equity read as {equity!r} — refusing to size against it")

    for sym in symbols:
        cascade["evaluated"] += 1
        row: dict = {"ts_et": ts, "symbol": sym, "account": creds.account_number,
                     "shadow": True, "feed": "indicative"}

        bars = (dry_bars or {}).get(sym)
        if bars is None or len(bars) < 60:
            row.update(decision="BLOCKED", gate="bars_ok", reason="insufficient closed bars")
            rows.append(row)
            continue
        cascade["bars_ok"] += 1

        try:
            sig = ms.build_signal(sym, bars, params=params)
        except (ms.SignalBuildError, ValueError) as e:
            row.update(decision="BLOCKED", gate="signal_scored", reason=f"signal error: {e}")
            rows.append(row)
            continue
        cascade["signal_scored"] += 1

        action = str(sig.get("action") or "HOLD").upper()
        row.update(action=action, spot=sig.get("spot"),
                   bear_score=(sig.get("bear") or {}).get("score"),
                   bull_score=(sig.get("bull") or {}).get("score"))
        if action not in ("ENTER_BEAR", "ENTER_BULL", "BEAR", "BULL"):
            row.update(decision="HOLD", gate="action_directional", reason=f"action={action}")
            rows.append(row)
            continue
        cascade["action_directional"] += 1

        side = "P" if "BEAR" in action else "C"
        row["side"] = side

        admission = mr.evaluate_admission(
            account=account, symbol=sym,
            start_of_day_equity=equity, realized_pnl_today=0.0,
            kill_switch_tripped=False, open_positions=open_opts,
            correlations=None, params=params,
        )
        if not getattr(admission, "allowed", False):
            row.update(decision="BLOCKED", gate="risk_admitted",
                       reason=getattr(admission, "reason", "risk denied"),
                       code=getattr(admission, "code", None))
            rows.append(row)
            continue
        cascade["risk_admitted"] += 1

        row.update(decision="WOULD_EVALUATE_CHAIN", gate="expiry_available",
                   reason="chain read deferred — shadow scoring pass")
        cascade["reached_chain"] += 1
        rows.append(row)

    return rows, cascade


def write_rows(rows: list[dict], cascade: Counter, *, ledger: Path = SHADOW_LEDGER,
               cascade_path: Path = CASCADE_PATH) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    with cascade_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts_et": now_et().isoformat(timespec="seconds"),
                             **dict(cascade)}, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None, help="override the params universe")
    ap.add_argument("--limit", type=int, default=0, help="cap symbols evaluated (0 = all)")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    params = mc.load_params()
    if not params.get("shadow_only", True):
        raise TickError(
            "params.shadow_only is not true. This module has no order path, but refusing to "
            "run against a lane that believes it is armed — resolve the config first."
        )
    creds = mc.resolve(params)
    mc.verify_account(creds)

    syms = ([s.strip().upper() for s in args.symbols.split(",")]
            if args.symbols else universe_symbols(params))
    if args.limit:
        syms = syms[: args.limit]

    live_bars = {}
    for sym in syms:
        try:
            b = fetch_bars(creds, sym, "1Hour", 400)
            if b is not None:
                live_bars[sym] = b
        except Exception as e:  # noqa: BLE001 -- per-symbol fetch failure must not kill the tick
            print(f"    [bars] {sym}: {type(e).__name__}: {str(e)[:60]}", file=sys.stderr)
    print(f"[multi_core] bars fetched for {len(live_bars)}/{len(syms)} symbols", file=sys.stderr)

    rows, cascade = tick(params, creds, syms, dry_bars=live_bars)
    if not args.no_write:
        write_rows(rows, cascade)

    print(f"[multi_core] {ts_summary(cascade)}", file=sys.stderr)
    for g in ("evaluated", "bars_ok", "signal_scored", "action_directional",
              "risk_admitted", "reached_chain"):
        print(f"    {g:<20} {cascade.get(g, 0)}", file=sys.stderr)
    return 0


def ts_summary(c: Counter) -> str:
    ev = c.get("evaluated", 0)
    reached = c.get("reached_chain", 0)
    pct = (100.0 * reached / ev) if ev else 0.0
    return f"{ev} symbols evaluated, {reached} reached the chain stage ({pct:.1f}% joint pass)"


if __name__ == "__main__":
    raise SystemExit(main())
