"""quote_recorder.py -- independent, read-only EXIT-QUOTE side-channel (Task B1, 2026-08-28).

WHY THIS EXISTS
----------------
We log NBBO on ~25 of 128 entry events (order_intent_log.py, only "when already in hand at
submit") and ZERO on exits. Every slippage number in every analysis in this repo is therefore
an ASSUMPTION -- and slippage is the difference between August reading +$619 (at an assumed
$1.00/contract) and -$506 (at the repo's own conservative $2.00/contract). We cannot keep
assuming. This starts MEASURING: an independent poller snapshots real option NBBO while any
arm holds an open position, so a future join against the fill price gives an OBSERVED slippage
number instead of a modeled one.

THE CONSTRAINT THAT DOMINATES THE DESIGN
-----------------------------------------
This must be PHYSICALLY INCAPABLE of affecting a live trade. It is therefore:
  1. A SEPARATE PROCESS, invoked by its own scheduled task (proposed, not created here) --
     never imported by, and never importing, any live-order-path module. It does not import
     fleet_broker.py, heartbeat_core.py, exit_manager.py, risk_gate.py, fleet_executor.py, or
     any params*.json loader. Every REST call and every credential-read below is a from-scratch
     minimal re-implementation, verified against fleet_broker.py's proven shapes (same URL
     hosts, same header names, same field names) but with ZERO import-time or runtime coupling
     -- a bug in this file cannot raise inside the engine's process, and a bug in the engine
     cannot raise inside this file's process, because they never share a stack.
  2. READ-ONLY on the broker: the only two calls this script ever makes are GET /v2/positions
     (does the account currently hold a SPY option?) and GET /v1beta1/options/quotes/latest
     (what is the NBBO on that symbol right now?). No POST, no DELETE, no order/cancel/replace
     endpoint exists anywhere in this file.
  3. READ-ONLY on engine state: this script never opens any file under automation/state/ for
     WRITING except its own status file (STATUS_PATH, below) and never touches
     current-position*.json, decisions.jsonl, loop-state.json, params*.json, or accounts.json
     for anything but an optional best-effort read (account_number labelling only, wrapped in
     its own try/except, never load-bearing).
  4. TOTAL fail-open: every network call, every file write, and the top-level loop itself is
     wrapped so this process can never raise an unhandled exception. A failure updates this
     script's OWN status file loudly (never silently) and logs to stderr; it never blocks,
     slows, or is on the path of anything the trading engine does.

KEY / RATE-LIMIT DESIGN (C10 -- "separate prod key" doctrine, applied to Alpaca's own
per-key rate bucket, not just the Claude-session pool the existing C10 lessons documented)
--------------------------------------------------------------------------------------------
automation/state/fleet/secrets.json holds exactly one Alpaca PAPER key per account (safe-2,
bold-2, safe-3, risky-1, risky-3, plus a dead safe-1 tombstone and an unrelated kalshi-1) --
there is NO separate "market-data-only" key in this repo to use instead. Given that, this
script queries EACH account's positions/quotes using ONLY that account's OWN key -- never a
different arm's key for a different arm's symbol. That keeps each key's incremental load
bounded to its own account's own position count (0 or 1 SPY option, essentially always),
completely isolated from every other arm's key, and isolated from the SAME key's own trading
calls by volume: at the default cadence (20s active / 60s idle) this adds at most 2 requests
(positions + quote) every 20s = 6 req/min per key while that arm holds a position, 1 req/min
per key while flat. Alpaca's documented paper-trading limit is 200 req/min PER KEY -- 6 req/min
is 3% of budget, and the live engine's OWN call volume on that same key (order placement +
exit-manager quote polling, ~1/min at heartbeat cadence) is far larger than this adds. Verified
by inspection of automation/state/fleet/secrets.json (2026-08-28, redacted key/secret lengths
only) -- see this script's own report for the exact math reproduced against real cadence data.

OUTPUT
------
analysis/quote-tape/YYYY-MM-DD.jsonl -- append-only. One row per (arm, symbol) NBBO snapshot
("kind":"option", unchanged shape). PLUS (added 2026-09-03, queue RTH-SPY-PER-MINUTE-TAPE):
one "kind":"underlying" SPY row per cycle inside literal RTH (09:30-16:00 ET), positions open
or not -- fixes the gap release_blackout_shadow.py's docstring used to note explicitly
("quote-tape carries no SPY underlying quote"), and the 5-min-bar-close blind spot in
core-decisions.jsonl's `spy` field that made a 1-minute 30% option gap at 10:00->10:01 ET
(2026-09-03 ISM Services release) misread as "flat SPY, pure decay" in same-day analysis.
automation/state/quote-recorder-status.json -- this script's own health surface (never engine
state; nothing on the trading path reads this file).

RETENTION (OP-22)
------------------
Per-day files older than RETENTION_DAYS are deleted at the start of every cycle (cheap glob +
filename-date parse, matches ledger_archive.py's RETENTION_DAYS=30 pattern; this stays larger,
90d, so the file line stays intact through J's November go-live decision window).

CLI
---
  python quote_recorder.py --once                 # one cycle, print + exit (smoke test)
  python quote_recorder.py --loop --duration-sec 0   # run forever (0 = no time limit)
  python quote_recorder.py --loop --duration-sec 120 --interval-active 5 --interval-idle 10
  python quote_recorder.py --once --dry-run --arms safe-2,bold-2   # no writes, stdout only

Guard: setup/scripts/test_quote_recorder.py (pure-logic tests, no network) +
       backtest/tests/test_quote_recorder_underlying_2026_09_03.py (underlying-row tests).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
SECRETS_PATH = REPO / "automation" / "state" / "fleet" / "secrets.json"
ACCOUNTS_PATH = REPO / "automation" / "state" / "fleet" / "accounts.json"
QUOTE_TAPE_DIR = REPO / "analysis" / "quote-tape"
STATUS_PATH = REPO / "automation" / "state" / "quote-recorder-status.json"

sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from et_clock import et_now  # DST-aware; see project_tz_systemic_fix -- never naive now()
except Exception:  # noqa: BLE001 -- degrade, never go dark for a clock import failure
    def et_now() -> dt.datetime:
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

FLEET_DIR = ACCOUNTS_PATH.parent
sys.path.insert(0, str(FLEET_DIR))
from arm_roster import active_arms  # noqa: E402 -- ONE roster def; queue.md THREE-MODULES-...

SCHEMA = "quote-tape/1"
STATUS_SCHEMA = "quote-recorder-status/1"
OPTIONS_DATA_HOST = "https://data.alpaca.markets"
DEFAULT_BASE_URL = "https://paper-api.alpaca.markets"


def _default_arms() -> "tuple[str, ...]":
    """The SPY-options arms this script polls -- read from arm_roster.active_arms() on every
    call, never cached at import, so a retirement or a new arm needs no edit here (was a
    hardcoded 5-tuple incl. retired risky-3 -- queue.md
    THREE-MODULES-SHOULD-READ-THE-ROSTER-DYNAMICALLY, 2026-09-03)."""
    return tuple(active_arms())


def __getattr__(name: str):  # PEP 562 -- qr.ARMS always reflects the CURRENT roster
    if name == "ARMS":
        return _default_arms()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


ACTIVE_INTERVAL_S = 20   # cadence while >=1 tracked arm holds an open SPY option position
IDLE_INTERVAL_S = 60     # cadence while book-wide flat -- just enough to notice a new entry
RETENTION_DAYS = 90      # OP-22 cap on analysis/quote-tape/*.jsonl


# --------------------------------------------------------------------------------------- #
# Credentials + broker reads -- FROM SCRATCH, deliberately not imported from fleet_broker.py
# (see module docstring #1). Shapes verified against that module's load_creds/_request/
# get_positions/get_option_quote_hilo on 2026-08-28; zero code or import shared with it.
# --------------------------------------------------------------------------------------- #

def load_creds(secrets_path: Path = SECRETS_PATH, arms: "Optional[tuple[str, ...]]" = None
               ) -> "dict[str, dict[str, str]]":
    """{arm: {key, secret, base_url}} for exactly the requested arms. Missing/malformed
    entries are skipped (never raise) -- a missing key shows up as a per-arm status gap,
    not a crashed process. `arms` defaults to the LIVE roster (arm_roster.active_arms()),
    resolved at call time, not at import."""
    if arms is None:
        arms = _default_arms()
    out: "dict[str, dict[str, str]]" = {}
    if not secrets_path.exists():
        return out
    try:
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    accounts = data.get("accounts", data) if isinstance(data, dict) else {}
    for arm in arms:
        c = accounts.get(arm)
        if not isinstance(c, dict):
            continue
        key, secret = c.get("key"), c.get("secret")
        base = (c.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        if key and secret:
            out[arm] = {"key": key, "secret": secret, "base_url": base}
    return out


def load_account_numbers(accounts_path: Path = ACCOUNTS_PATH) -> "dict[str, str]":
    """{arm: account_number}, best-effort label only -- never load-bearing. Any failure
    (missing file, bad json, unexpected shape) returns {} silently; callers must treat a
    missing account_number as cosmetic, never as a gate."""
    try:
        data = json.loads(accounts_path.read_text(encoding="utf-8"))
        out = {}
        for row in data.get("arms", []):
            if isinstance(row, dict) and row.get("id") and row.get("account_number"):
                out[row["id"]] = row["account_number"]
        return out
    except Exception:  # noqa: BLE001
        return {}


def _get_json(url: str, headers: "dict[str, str]", timeout: float = 10.0
              ) -> "tuple[Any, Optional[str]]":
    """(payload, error). Never raises. error is a short human string on any failure."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8")
            return (json.loads(txt) if txt else {}), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001
            body = ""
        return None, f"HTTP {e.code}: {body}"
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        return None, f"{type(e).__name__}: {e}"


def get_open_spy_option_positions(creds: "dict[str, str]") -> "tuple[list, Optional[str]]":
    """(positions, error). positions = broker's own list of dicts for SPY option legs only
    (mirrors fleet_broker.open_spy_option_positions's exact filter, independently
    re-implemented). error is None on a normal (possibly empty) read; non-None means the READ
    ITSELF failed and an empty list must NOT be trusted as "flat" (same C11/2026-08-13 lesson
    fleet_broker.open_spy_option_positions_checked exists for -- this script has no live
    decision riding on the answer, so it simply skips the cycle for that arm on a read error
    rather than emitting a false snapshot)."""
    url = f"{creds['base_url']}/v2/positions"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    payload, err = _get_json(url, headers, timeout=10.0)
    if err is not None:
        return [], err
    if not isinstance(payload, list):
        return [], f"unexpected /v2/positions shape: {type(payload).__name__}"
    out = [p for p in payload
           if isinstance(p, dict) and str(p.get("symbol", "")).startswith("SPY")
           and len(str(p.get("symbol", ""))) >= 15
           and str(p.get("asset_class", "")) in ("option", "us_option", "")]
    return out, None


def get_stock_snapshot(creds: "dict[str, str]", symbol: str = "SPY"
                       ) -> "tuple[Optional[dict], Optional[str]]":
    """(snapshot, error) for the underlying's latest quote+trade -- ONE HTTP GET to
    /v2/stocks/{symbol}/snapshot on Alpaca's stock market-data feed. That single response
    carries BOTH `latestQuote` (bid/ask, keys bp/ap -- same field names as the options NBBO
    feed) AND `latestTrade` (last price + timestamp, keys p/t) in one payload, which is why
    this is "one extra stock latest-quote/trade request per cycle": one call, not two.
    Endpoint verified against automation/scripts/gex_capture.py#STOCK_SNAPSHOT_URL (same host
    + path, independently re-implemented here per this module's zero-import-coupling rule --
    see module docstring #1). Uses the SAME `_get_json` transport and the SAME
    APCA-API-KEY-ID/APCA-API-SECRET-KEY header pair every option/position call in this file
    uses -- just pointed at one arm's own creds (any arm's key works identically here since
    SPY's own quote/trade is not account-scoped; run_cycle picks exactly one).
    snapshot = {"bid","ask","mid","last","last_ts"} or None if the feed returned nothing
    usable (not an error -- a genuinely quote-less moment)."""
    url = f"{OPTIONS_DATA_HOST}/v2/stocks/{symbol}/snapshot"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    payload, err = _get_json(url, headers, timeout=10.0)
    if err is not None:
        return None, err
    if not isinstance(payload, dict):
        return None, None

    def _num(v: Any) -> Optional[float]:
        return float(v) if isinstance(v, (int, float)) and v > 0 else None

    lq = payload.get("latestQuote")
    lt = payload.get("latestTrade")
    bid = _num(lq.get("bp")) if isinstance(lq, dict) else None
    ask = _num(lq.get("ap")) if isinstance(lq, dict) else None
    last = _num(lt.get("p")) if isinstance(lt, dict) else None
    last_ts = lt.get("t") if isinstance(lt, dict) else None
    if bid is None and ask is None and last is None:
        return None, None
    mid = round((bid + ask) / 2, 4) if bid is not None and ask is not None else None
    return {"bid": bid, "ask": ask, "mid": mid, "last": last, "last_ts": last_ts}, None


def get_option_nbbo(creds: "dict[str, str]", symbol: str) -> "tuple[Optional[dict], Optional[str]]":
    """(quote, error) for one OCC option symbol from Alpaca's options data feed.
    quote = {"bid","ask","mid","bid_size","ask_size","quote_ts"} or None if the feed
    returned no two-sided quote (not an error -- a genuinely wide/empty book)."""
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={symbol}"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    payload, err = _get_json(url, headers, timeout=10.0)
    if err is not None:
        return None, err
    q = (payload or {}).get("quotes", {}).get(symbol) if isinstance(payload, dict) else None
    if not isinstance(q, dict):
        return None, None  # no error, just nothing quoted for this symbol right now
    bid, ask = q.get("bp"), q.get("ap")
    out = {
        "bid": float(bid) if isinstance(bid, (int, float)) and bid > 0 else None,
        "ask": float(ask) if isinstance(ask, (int, float)) and ask > 0 else None,
        "bid_size": q.get("bs"),
        "ask_size": q.get("as"),
        "quote_ts": q.get("t"),
    }
    if out["bid"] is not None and out["ask"] is not None:
        out["mid"] = round((out["bid"] + out["ask"]) / 2, 4)
    else:
        out["mid"] = None
    return out, None


# --------------------------------------------------------------------------------------- #
# Pure logic (no network, no filesystem) -- what test_quote_recorder.py exercises directly.
# --------------------------------------------------------------------------------------- #

def build_snapshot_rows(now: dt.datetime, cycle_id: int, arm_positions: "dict[str, list]",
                         arm_quotes: "dict[str, dict[str, dict]]",
                         account_numbers: "dict[str, str]" = None) -> "list[dict]":
    """PURE: turn {arm: [position,...]} + {arm: {symbol: quote}} into output rows. One row
    per (arm, symbol) that has BOTH an open position AND a successfully-fetched quote --
    a position with no quote yet is simply not emitted this cycle (never a fabricated row)."""
    account_numbers = account_numbers or {}
    rows = []
    for arm, positions in arm_positions.items():
        quotes = arm_quotes.get(arm, {})
        for pos in positions:
            sym = pos.get("symbol")
            q = quotes.get(sym)
            if not sym or not q:
                continue
            rows.append({
                "schema": SCHEMA,
                "kind": "option",
                "ts_et": now.isoformat(),
                "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "date_et": now.strftime("%Y-%m-%d"),
                "cycle_id": cycle_id,
                "arm": arm,
                "account_number": account_numbers.get(arm),
                "symbol": sym,
                "qty_open": pos.get("qty"),
                "side": pos.get("side"),
                "avg_entry_price": pos.get("avg_entry_price"),
                "bid": q.get("bid"),
                "ask": q.get("ask"),
                "mid": q.get("mid"),
                "bid_size": q.get("bid_size"),
                "ask_size": q.get("ask_size"),
                "quote_ts": q.get("quote_ts"),
                "source": "alpaca_options_quotes_latest",
            })
    return rows


def build_underlying_row(now: dt.datetime, cycle_id: int, snap: "Optional[dict]"
                         ) -> "Optional[dict]":
    """PURE: turn one stock-snapshot dict into ONE underlying row, or None if `snap` is
    falsy (fetch failed, or the feed had nothing usable this cycle) -- same
    never-fabricate-a-row contract as build_snapshot_rows above."""
    if not snap:
        return None
    return {
        "schema": SCHEMA,
        "kind": "underlying",
        "symbol": "SPY",
        "ts_et": now.isoformat(),
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_et": now.strftime("%Y-%m-%d"),
        "cycle_id": cycle_id,
        "bid": snap.get("bid"),
        "ask": snap.get("ask"),
        "mid": snap.get("mid"),
        "last": snap.get("last"),
        "last_ts": snap.get("last_ts"),
        "source": "alpaca_stock_quotes_latest",
    }


def _pick_any_creds(creds_by_arm: "dict[str, dict[str, str]]") -> "Optional[dict[str, str]]":
    """PURE: one credential set to use for the account-agnostic SPY underlying quote --
    the arm whose id sorts first, so the choice is deterministic across cycles/tests rather
    than dict-iteration-order-dependent. Any configured arm's key works identically here
    (SPY's own NBBO is not account-scoped); None if no arm has usable creds this cycle."""
    if not creds_by_arm:
        return None
    return creds_by_arm[sorted(creds_by_arm)[0]]


def prune_old_files(directory: Path, cutoff_date: dt.date,
                     pattern: str = "*.jsonl") -> "list[str]":
    """PURE-ish (one glob, filesystem side effect): delete <YYYY-MM-DD>.jsonl files in
    `directory` dated strictly before cutoff_date. Returns the names deleted. A filename
    that doesn't parse as a date is left alone (never guess-delete)."""
    deleted = []
    if not directory.exists():
        return deleted
    for p in sorted(directory.glob(pattern)):
        try:
            file_date = dt.datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff_date:
            try:
                p.unlink()
                deleted.append(p.name)
            except OSError:
                pass
    return deleted


def is_rth_window(now: dt.datetime) -> bool:
    """08:55-16:05 ET weekdays -- a few minutes either side of RTH so a position opened in
    the last seconds of the day or a very early pre-open test fill is still covered."""
    if now.weekday() >= 5:
        return False
    hm = now.strftime("%H:%M")
    return "08:55" <= hm <= "16:05"


def is_underlying_rth_window(now: dt.datetime) -> bool:
    """09:30-16:00 ET weekdays -- literal RTH, deliberately NARROWER than is_rth_window's
    08:55-16:05 pre/post pad above (that one still gates the OPTION side unchanged). The
    underlying SPY row is written on every cycle inside this window regardless of whether
    any arm holds a position; outside it, no underlying row is written this cycle."""
    if now.weekday() >= 5:
        return False
    hm = now.strftime("%H:%M")
    return "09:30" <= hm <= "16:00"


# --------------------------------------------------------------------------------------- #
# Status file -- this script's OWN health surface. Never read by anything on the trading
# path; read by the self_check.py addition (check_quote_recorder_alive) added alongside this.
# --------------------------------------------------------------------------------------- #

def write_status(status: dict, path: Path = STATUS_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)  # atomic on Windows too -- never a half-written status file
    except OSError:
        pass  # even the status write is fail-open; stderr already got the same information


def read_status(path: Path = STATUS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------------------- #
# One cycle
# --------------------------------------------------------------------------------------- #

def run_cycle(creds_by_arm: "dict[str, dict[str, str]]", account_numbers: "dict[str, str]",
              cycle_id: int, *, dry_run: bool = False,
              out_dir: Path = QUOTE_TAPE_DIR) -> dict:
    """One full poll: positions -> quotes -> rows -> append. Returns a per-cycle summary dict
    (also folded into the status file by the caller). NEVER raises -- every sub-step is
    individually guarded so one arm's broker outage cannot blank the other four."""
    now = et_now()
    arm_positions: "dict[str, list]" = {}
    arm_errors: "dict[str, str]" = {}
    for arm, creds in creds_by_arm.items():
        try:
            positions, err = get_open_spy_option_positions(creds)
        except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders; the calls above
            positions, err = [], f"unexpected: {exc!r}"[:300]
        if err:
            arm_errors[arm] = err
        else:
            arm_positions[arm] = positions

    arm_quotes: "dict[str, dict[str, dict]]" = {}
    for arm, positions in arm_positions.items():
        creds = creds_by_arm[arm]
        per_symbol: "dict[str, dict]" = {}
        for pos in positions:
            sym = pos.get("symbol")
            if not sym or sym in per_symbol:
                continue
            try:
                q, err = get_option_nbbo(creds, sym)
            except Exception as exc:  # noqa: BLE001
                q, err = None, f"unexpected: {exc!r}"[:300]
            if err:
                arm_errors.setdefault(arm, err)
            elif q:
                per_symbol[sym] = q
        arm_quotes[arm] = per_symbol

    rows = build_snapshot_rows(now, cycle_id, arm_positions, arm_quotes, account_numbers)

    # Underlying SPY row -- every cycle inside literal RTH (09:30-16:00 ET), positions open
    # or not. ONE extra request total (not per-arm): get_stock_snapshot is called at most
    # once, using one arm's own creds (see _pick_any_creds), never blocking the option rows
    # built above -- any exception/error here is recorded under arm_errors["underlying"] and
    # the cycle continues with whatever option rows it already has. Mirrors the option side's
    # own contract: an empty creds_by_arm means nothing configured to check (not an error --
    # same as zero arms meaning zero positions checked above), so the fetch is only attempted
    # when at least one arm actually has usable creds this cycle.
    underlying_rows_written = 0
    if is_underlying_rth_window(now):
        u_creds = _pick_any_creds(creds_by_arm)
        if u_creds is not None:
            try:
                snap, err = get_stock_snapshot(u_creds, "SPY")
            except Exception as exc:  # noqa: BLE001 -- same belt-and-suspenders as options above
                snap, err = None, f"unexpected: {exc!r}"[:300]
            if err:
                arm_errors["underlying"] = err
            else:
                u_row = build_underlying_row(now, cycle_id, snap)
                if u_row:
                    rows = rows + [u_row]
                    underlying_rows_written = 1

    written = 0
    if rows and not dry_run:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
            with out_path.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
            written = len(rows)
        except OSError as exc:
            arm_errors["_write"] = f"{type(exc).__name__}: {exc}"
    elif rows and dry_run:
        for row in rows:
            print(json.dumps(row, default=str))
        written = len(rows)

    total_open = sum(len(v) for v in arm_positions.values())
    return {
        "ts_et": now.isoformat(),
        "cycle_id": cycle_id,
        "arms_open": sorted(a for a, v in arm_positions.items() if v),
        "positions_open_count": total_open,
        "rows_written": written,
        "underlying_rows_written": underlying_rows_written,
        "errors": arm_errors,
        "ok": not arm_errors,
        "mode": "active" if total_open > 0 else "idle",
    }


# --------------------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------------------- #

def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="run exactly one cycle then exit")
    ap.add_argument("--loop", action="store_true", help="run continuously")
    ap.add_argument("--duration-sec", type=int, default=0,
                     help="--loop only: stop after N seconds (0 = run until killed)")
    ap.add_argument("--interval-active", type=int, default=ACTIVE_INTERVAL_S)
    ap.add_argument("--interval-idle", type=int, default=IDLE_INTERVAL_S)
    ap.add_argument("--rth-only", dest="rth_only", action="store_true", default=True)
    ap.add_argument("--no-rth-only", dest="rth_only", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--arms", default=",".join(_default_arms()),
                     help="comma-separated arm ids to poll (default: the live roster's active arms)")
    ap.add_argument("--out-dir", default=str(QUOTE_TAPE_DIR))
    ap.add_argument("--status-path", default=str(STATUS_PATH))
    ap.add_argument("--secrets-path", default=str(SECRETS_PATH))
    args = ap.parse_args(argv)

    if not args.once and not args.loop:
        args.once = True  # default to a single cycle if neither flag given

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    out_dir = Path(args.out_dir)
    status_path = Path(args.status_path)
    secrets_path = Path(args.secrets_path)

    cycle_id = 0
    consecutive_failures = 0
    last_success_ts: Optional[str] = None
    prior = read_status(status_path)
    if isinstance(prior, dict):
        consecutive_failures = int(prior.get("consecutive_cycle_failures", 0) or 0)
        last_success_ts = prior.get("last_success_ts_et")

    started_at = et_now().isoformat()
    deadline = None
    if args.loop and args.duration_sec > 0:
        deadline = time.monotonic() + args.duration_sec

    account_numbers = load_account_numbers()

    while True:
        cycle_id += 1
        now = et_now()
        try:
            deleted = prune_old_files(out_dir, now.date() - dt.timedelta(days=RETENTION_DAYS))
        except Exception:  # noqa: BLE001
            deleted = []

        skip_reason = None
        if args.rth_only and not is_rth_window(now):
            skip_reason = "outside RTH window (08:55-16:05 ET weekdays)"
            summary = {"ts_et": now.isoformat(), "cycle_id": cycle_id, "arms_open": [],
                       "positions_open_count": 0, "rows_written": 0, "errors": {},
                       "ok": True, "mode": "idle_offhours"}
        else:
            try:
                creds_by_arm = load_creds(secrets_path, arms)
            except Exception as exc:  # noqa: BLE001
                creds_by_arm, load_err = {}, repr(exc)[:300]
            else:
                load_err = None
            missing_arms = [a for a in arms if a not in creds_by_arm]
            try:
                summary = run_cycle(creds_by_arm, account_numbers, cycle_id,
                                     dry_run=args.dry_run, out_dir=out_dir)
            except Exception as exc:  # noqa: BLE001 -- the ultimate backstop; run_cycle
                # already guards its own internals, this catches anything unforeseen.
                summary = {"ts_et": now.isoformat(), "cycle_id": cycle_id, "arms_open": [],
                           "positions_open_count": 0, "rows_written": 0,
                           "errors": {"_cycle": repr(exc)[:300]}, "ok": False, "mode": "error"}
            if load_err:
                summary["errors"]["_creds"] = load_err
                summary["ok"] = False
            if missing_arms:
                summary["errors"]["_missing_creds"] = missing_arms

        if summary.get("ok"):
            consecutive_failures = 0
            last_success_ts = summary["ts_et"]
        else:
            consecutive_failures += 1

        status = {
            "schema": STATUS_SCHEMA,
            "started_at_et": started_at,
            "pid": os.getpid(),
            "last_cycle_ts_et": summary["ts_et"],
            "last_cycle_ok": summary.get("ok"),
            "last_cycle_mode": summary.get("mode"),
            "last_cycle_rows_written": summary.get("rows_written"),
            "underlying_rows_written": summary.get("underlying_rows_written", 0),
            "last_cycle_errors": summary.get("errors"),
            "last_success_ts_et": last_success_ts,
            "consecutive_cycle_failures": consecutive_failures,
            "arms_configured": list(arms),
            "arms_open_last_cycle": summary.get("arms_open", []),
            "retention_days": RETENTION_DAYS,
            "pruned_files_last_cycle": deleted,
            "skip_reason": skip_reason,
        }
        if not args.dry_run:
            write_status(status, status_path)
        else:
            print(json.dumps(status, indent=2, default=str))

        if args.once:
            return 0 if summary.get("ok", True) else 1

        interval = args.interval_active if summary.get("mode") == "active" else args.interval_idle
        if skip_reason:
            interval = max(interval, 300)  # off-hours: check every 5 min, not every 20-60s
        if deadline is not None and time.monotonic() + interval >= deadline:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 -- absolute last resort; must never propagate a
        # traceback that could be mistaken for a trading-path failure by anything watching
        # this process's exit code.
        try:
            write_status({"schema": STATUS_SCHEMA, "fatal_error": repr(exc)[:500],
                          "ts_et": et_now().isoformat()})
        except Exception:  # noqa: BLE001
            pass
        print(f"[quote_recorder] FATAL (non-trading-path, contained): {exc!r}", file=sys.stderr)
        sys.exit(1)
