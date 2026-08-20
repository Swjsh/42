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
from multi.lib import exits as mex  # noqa: E402
from multi.lib import levels as mlv  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402
from multi.lib import watchlist as mw  # noqa: E402
from multi.lib import positions as mp  # noqa: E402
from multi.lib import risk as mr  # noqa: E402
from multi.lib import scanners as msc  # noqa: E402
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


# --- chain reads (lane-owned; the contracts endpoint lives on the PAPER trading host) --------
# A paper key 401s against api.alpaca.markets for /v2/options/contracts -- the trading API is
# host-partitioned by account type while the market-DATA host is shared. Learned 2026-08-18.

def _paper_get(creds, path: str, params: dict) -> dict:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    url = creds.base_url + path + "?" + urlencode(params)
    req = Request(url, headers={"APCA-API-KEY-ID": creds.key,
                                "APCA-API-SECRET-KEY": creds.secret})
    with urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read())


def _data_get(creds, path: str, params: dict) -> dict:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    url = "https://data.alpaca.markets" + path + "?" + urlencode(params)
    req = Request(url, headers={"APCA-API-KEY-ID": creds.key,
                                "APCA-API-SECRET-KEY": creds.secret})
    with urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read())


def fetch_chain(creds, symbol: str, right: str, max_dte: int = 45) -> list:
    """Listed contracts for `symbol` as [{expiry, strike, contract}] -- a LIVE chain read.

    Never a computed calendar: an expiry can be absent because earnings land that day
    (verified -- NVDA has no 2026-08-26 expiry for exactly that reason).
    """
    today = now_et().date()
    payload = _paper_get(creds, "/v2/options/contracts", {
        "underlying_symbols": symbol, "status": "active",
        "expiration_date_gte": today.isoformat(),
        "expiration_date_lte": (today + dt.timedelta(days=max_dte)).isoformat(),
        "type": "call" if right == "C" else "put",
        "limit": 10000,
    })
    out = []
    for c in payload.get("option_contracts") or []:
        try:
            out.append({"expiry": dt.date.fromisoformat(c["expiration_date"]),
                        "strike": float(c["strike_price"]),
                        "contract": c["symbol"]})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_option_quote(creds, occ: str):
    """Live quote for ONE contract. Returns None rather than a default when the quote is
    missing -- a fabricated mid would silently pass the liquidity gate."""
    d = _data_get(creds, "/v1beta1/options/snapshots/" + occ, {"feed": "indicative"})
    snap = (d.get("snapshots") or {}).get(occ) or d.get("snapshot") or {}
    q = snap.get("latestQuote") or {}
    bid, ask = q.get("bp"), q.get("ap")
    if not bid or not ask:
        return None
    return {"bid": float(bid), "ask": float(ask),
            "open_interest": snap.get("openInterest"),
            "volume": (snap.get("dailyBar") or {}).get("v")}


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def attention_from_bars(bars_by_symbol: dict) -> dict:
    """Derive stage-2 attention facts from bars ALREADY fetched -- no extra API calls.

    relative volume is the field that matters (see watchlist.py): it normalizes against each
    symbol's OWN baseline, so a 9.8x reading means the same thing for an $18 stock and a $700
    ETF, which raw volume or %-change never can.
    """
    out = {}
    for sym, df in (bars_by_symbol or {}).items():
        try:
            if df is None or len(df) < 30:
                continue
            vols = df["volume"].to_numpy(dtype=float)
            recent = float(vols[-6:].mean()) if len(vols) >= 6 else float(vols[-1])
            base = float(vols[:-6].mean()) if len(vols) > 12 else float(vols.mean())
            rel = (recent / base) if base > 0 else 1.0
            closes = df["close"].to_numpy(dtype=float)
            span = min(len(closes) - 1, 7)
            pct = 100.0 * (closes[-1] / closes[-1 - span] - 1.0) if span > 0 else 0.0
            out[sym] = {"rel_volume": round(rel, 3), "pct_change": round(pct, 3),
                        "dollar_volume": round(float(closes[-1]) * recent, 2),
                        "scanner_hits": 0}
        except (KeyError, IndexError, ValueError, ZeroDivisionError):
            continue
    return out


def manage_open_positions(params: dict, creds, open_opts: list, bars_by_symbol: dict) -> list:
    """Evaluate EXITS for open positions BEFORE considering any new entry.

    Ordering is deliberate: a lane that looks for entries before managing what it already holds
    can breach its own concurrency cap and, worse, can miss an expiry-day flatten while busy
    scoring new names. Exits first, always.

    SHADOW: this records the exit DECISION. It does not send anything -- exits.evaluate_exit is
    a pure function and no broker submission is reachable from here.
    """
    out = []
    try:
        state = mps.load_state()
    except mps.PositionStateError as e:
        # A corrupt/missing state file must never read as "no open positions" -- that is the
        # dangerous direction (it would look like a clean book while positions are live).
        return [{"ts_et": now_et().isoformat(timespec="seconds"), "kind": "exit_eval",
                 "decision": "BLOCKED", "gate": "position_state",
                 "reason": "position state unreadable: %s" % e, "shadow": True}]

    if not state:
        return out

    for contract, rec in state.items():
        row = {"ts_et": now_et().isoformat(timespec="seconds"), "kind": "exit_eval",
               "contract": contract, "symbol": getattr(rec, "symbol", None),
               "shadow": True, "feed": "indicative"}
        try:
            quote = fetch_option_quote(creds, contract)
        except Exception:  # noqa: BLE001
            quote = None
        if not quote:
            row.update(decision="BLOCKED", gate="quote",
                       reason="no two-sided quote for an OPEN position")
            out.append(row)
            continue

        sym = getattr(rec, "symbol", None)
        df = (bars_by_symbol or {}).get(sym)
        underlying = None
        atr14 = None
        if df is not None and len(df) > 15:
            try:
                underlying = float(df["close"].iloc[-1])
                atr14 = mlv._atr(df)
            except Exception:  # noqa: BLE001
                underlying, atr14 = None, None

        try:
            decision = mex.evaluate_exit(
                rec, now_et=now_et(),
                best_premium=float(quote["ask"]), worst_premium=float(quote["bid"]),
                open_qty=getattr(rec, "qty", 0), underlying_price=underlying,
                atr14=atr14, params=params,
            )
        except Exception as e:  # noqa: BLE001
            row.update(decision="BLOCKED", gate="exit_eval",
                       reason="exit evaluation failed: %s" % type(e).__name__)
            out.append(row)
            continue

        row.update(decision=str(getattr(decision, "action", "HOLD")),
                   stage=str(getattr(decision, "stage", "") or getattr(decision, "reason", "")),
                   qty_to_close=getattr(decision, "qty", None),
                   bid=quote["bid"], ask=quote["ask"],
                   days_held=getattr(rec, "days_held", None))
        out.append(row)
    return out


def merge_scanner_attention(base: dict, params: dict, creds) -> dict:
    """Fold the free Alpaca scanners into the bar-derived attention facts.

    The scanners answer a question bars cannot: is anything happening to this name that the
    market at large has noticed? movers/most-actives are corroboration; news is the only
    source that says WHY. Measured 2026-08-19: the stack put MRNA at 9.8x relative volume with
    all four scanners firing, on the day its $120 call ran open-to-high +1,121%.

    FAILS SOFT BY DESIGN, and this is a deliberate asymmetry: a scanner outage must not blind
    the lane, because the bar-derived relative volume (the highest-signal field) is already in
    `base` and stands on its own. So a scanner failure DEGRADES ranking quality rather than
    halting the tick. The failure is recorded on the returned dict, never swallowed silently.
    """
    merged = {k: dict(v) for k, v in (base or {}).items()}
    try:
        results = msc.run_all_scanners(params, creds.key, creds.secret)
    except Exception as e:  # noqa: BLE001 -- see docstring: degrade, do not halt
        merged["_scanner_status"] = {"ok": False, "error": type(e).__name__}
        return merged

    failed = []
    for name, res in (results or {}).items():
        if not getattr(res, "ok", False):
            failed.append(name)
            continue
        for cand in getattr(res, "candidates", ()) or ():
            sym = (cand.get("symbol") if isinstance(cand, dict)
                   else getattr(cand, "symbol", None))
            if not sym:
                continue
            row = merged.setdefault(str(sym).upper(), {})
            row["scanner_hits"] = int(row.get("scanner_hits") or 0) + 1
            get = (cand.get if isinstance(cand, dict) else lambda k, d=None: getattr(cand, k, d))
            if row.get("pct_change") in (None, 0.0):
                pc = get("percent_change", None) or get("pct_change", None)
                if pc is not None:
                    row["pct_change"] = float(pc)
            if not row.get("headline"):
                hl = get("headline", None)
                if hl:
                    row["headline"] = str(hl)[:120]
                    row["news_class"] = get("news_class", None) or get("klass", None)

    merged["_scanner_status"] = {"ok": not failed, "failed": failed,
                                 "scanners": sorted((results or {}).keys())}
    return merged


def tick(params: dict, creds: mc.MultiCreds, symbols: list[str], *,
         dry_bars: dict | None = None,
         attention_override: dict | None = None) -> tuple[list[dict], Counter]:
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

    # EXITS FIRST. Managing what we already hold outranks hunting new entries -- a lane that
    # scores 72 names before checking an expiry-day flatten has its priorities inverted.
    exit_rows = manage_open_positions(params, creds, open_opts, dry_bars or {})
    rows.extend(exit_rows)
    cascade["exit_evaluations"] = len(exit_rows)

    # --- THE FUNNEL: narrow ~72 names to <=5 BEFORE any expensive chain read ---------------
    # Stages 1-3 are cheap (bars we already hold); the per-symbol chain reads that follow are
    # not. Running them on 72 names would be ~72x the API cost for the same decisions, and the
    # rate limit is a real constraint. Narrowing by RANKING (never thresholding) means this
    # cannot silently yield an empty watchlist on a quiet day -- the L199 failure.
    attention = attention_override if attention_override is not None \
        else attention_from_bars(dry_bars or {})
    scan_status = (attention or {}).pop("_scanner_status", None)
    if scan_status and not scan_status.get("ok", True):
        cascade["scanner_degraded"] = 1
    watch, stage_counts = mw.build_watchlist(symbols, attention=attention)
    cascade["funnel_universe"] = stage_counts.get("universe", 0)
    cascade["funnel_liquidity"] = stage_counts.get("liquidity", 0)
    cascade["funnel_attention"] = stage_counts.get("attention", 0)
    cascade["funnel_setup"] = stage_counts.get("setup", 0)
    watch_syms = [c.symbol for c in watch]
    watch_facts = {c.symbol: c for c in watch}

    for sym in symbols:
        cascade["evaluated"] += 1
        if sym not in watch_syms:
            # Not a failure -- the funnel did its job. Recorded so the cascade stays honest
            # about how many names were considered vs actually examined.
            cascade["funnel_filtered_out"] += 1
            continue
        wf = watch_facts.get(sym)
        row: dict = {"ts_et": ts, "symbol": sym, "account": creds.account_number,
                     "shadow": True, "feed": "indicative",
                     "rel_volume": getattr(wf, "rel_volume", None),
                     "attention_score": getattr(wf, "attention_score", None)}

        bars = (dry_bars or {}).get(sym)
        if bars is None or len(bars) < 60:
            row.update(decision="BLOCKED", gate="bars_ok", reason="insufficient closed bars")
            rows.append(row)
            continue
        cascade["bars_ok"] += 1

        # Per-symbol levels. Without these, filter 10 (level-tied trigger required) vetoes
        # EVERY symbol on every tick -- the lane is structurally unable to trade. Found by the
        # participation cascade 2026-08-20.
        try:
            active_lv, multi_lv = mlv.compute_levels(bars)
        except mlv.LevelError as e:
            row.update(decision="BLOCKED", gate="signal_scored", reason=f"levels: {e}")
            rows.append(row)
            continue
        row["n_levels_active"] = len(active_lv)
        try:
            sig = ms.build_signal(sym, bars, params=params,
                                  candidate_levels=active_lv,
                                  candidate_multi_day_levels=multi_lv)
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

        # --- chain stage: expiry -> strike -> liquidity -> size ---------------------------
        try:
            chain = fetch_chain(creds, sym, side)
        except Exception as e:  # noqa: BLE001 -- one bad chain read must not kill the tick
            row.update(decision="BLOCKED", gate="expiry_available",
                       reason="chain read failed: " + type(e).__name__)
            rows.append(row)
            continue
        expiries = sorted({c["expiry"] for c in chain})
        if not expiries:
            row.update(decision="BLOCKED", gate="expiry_available", reason="no listed expiries")
            rows.append(row)
            continue
        try:
            exp_sel = mx.select_expiry(symbol=sym, available_expiries=expiries, params=params)
        except Exception as e:  # noqa: BLE001
            row.update(decision="BLOCKED", gate="expiry_available", reason="expiry: %s" % e)
            rows.append(row)
            continue
        chosen_exp = getattr(exp_sel, "expiry", None)
        if chosen_exp is None:
            row.update(decision="BLOCKED", gate="expiry_available",
                       reason=str(getattr(exp_sel, "reason", "no expiry cleared min DTE")))
            rows.append(row)
            continue
        cascade["expiry_available"] += 1
        if isinstance(chosen_exp, str):
            chosen_exp = dt.date.fromisoformat(chosen_exp)
        row.update(expiry=str(chosen_exp), dte=(chosen_exp - now_et().date()).days)

        strikes = sorted({c["strike"] for c in chain if c["expiry"] == chosen_exp})
        spot = _num(sig.get("spot"))
        if not strikes or spot is None:
            row.update(decision="BLOCKED", gate="strike_selected", reason="no strikes or spot")
            rows.append(row)
            continue
        try:
            k_sel = msz.select_strike(symbol=sym, spot=spot, side=side,
                                      available_strikes=strikes)
        except Exception as e:  # noqa: BLE001
            row.update(decision="BLOCKED", gate="strike_selected", reason="strike: %s" % e)
            rows.append(row)
            continue
        strike = getattr(k_sel, "strike", None)
        occ = next((c["contract"] for c in chain
                    if c["expiry"] == chosen_exp and c["strike"] == strike), None)
        if occ is None:
            row.update(decision="BLOCKED", gate="strike_selected",
                       reason="selected strike is not in the listed chain")
            rows.append(row)
            continue
        cascade["strike_selected"] += 1
        row.update(strike=strike, contract=occ)

        try:
            quote = fetch_option_quote(creds, occ)
        except Exception:  # noqa: BLE001
            quote = None
        ok, why, facts = liquidity_ok(quote, params)
        for k, v in facts.items():
            if k != "feed":
                row[k] = v
        if not ok:
            row.update(decision="BLOCKED", gate="liquidity_ok", reason=why)
            rows.append(row)
            continue
        cascade["liquidity_ok"] += 1

        try:
            sz = msz.size_entry(symbol=sym, equity=equity, premium=facts["mid"],
                                params=params, open_positions=open_opts)
        except Exception as e:  # noqa: BLE001
            row.update(decision="BLOCKED", gate="sized_ok", reason="sizing: %s" % e)
            rows.append(row)
            continue
        if not getattr(sz, "allowed", False):
            row.update(decision="BLOCKED", gate="sized_ok",
                       reason=str(getattr(sz, "reason", "sizing denied")))
            rows.append(row)
            continue
        cascade["sized_ok"] += 1
        cascade["would_place"] += 1
        row.update(decision="WOULD_PLACE", gate="would_place",
                   qty=getattr(sz, "qty", None), notional=getattr(sz, "notional", None),
                   reason="all gates cleared - SHADOW, no order sent")
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

    # Bootstrap the position-state file ONCE, explicitly. position_state deliberately refuses
    # to treat a missing file as "no open positions" -- that is the dangerous direction, since
    # it would read as a clean book while positions are live. So a genuinely-fresh lane creates
    # it here on purpose, and any LATER disappearance or corruption stays a loud alarm rather
    # than being silently re-created every tick.
    mps.ensure_initialized()

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

    base_attention = attention_from_bars(live_bars)
    attention = merge_scanner_attention(base_attention, params, creds)
    st = attention.get("_scanner_status") or {}
    print(f"[multi_core] scanners: {st.get('scanners', [])} "
          f"ok={st.get('ok')} failed={st.get('failed', [])}", file=sys.stderr)

    rows, cascade = tick(params, creds, syms, dry_bars=live_bars,
                         attention_override=attention)
    if not args.no_write:
        write_rows(rows, cascade)

    print(f"[multi_core] {ts_summary(cascade)}", file=sys.stderr)
    for g in ("exit_evaluations", "evaluated", "funnel_filtered_out", "bars_ok",
              "signal_scored",
              "action_directional",
              "risk_admitted", "expiry_available", "strike_selected", "liquidity_ok",
              "sized_ok", "would_place"):
        print(f"    {g:<20} {cascade.get(g, 0)}", file=sys.stderr)
    return 0


def ts_summary(c: Counter) -> str:
    ev = c.get("evaluated", 0)
    reached = c.get("would_place", 0)
    pct = (100.0 * reached / ev) if ev else 0.0
    return f"{ev} symbols evaluated, {reached} WOULD PLACE ({pct:.1f}% joint pass)"


if __name__ == "__main__":
    raise SystemExit(main())
