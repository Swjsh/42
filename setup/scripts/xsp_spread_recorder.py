"""xsp_spread_recorder.py -- independent, read-only XSP vs SPY NBBO spread probe
(work order §2b, 2026-09-03).

WHY THIS EXISTS
----------------
`markdown/planning/OPUS-WORK-ORDER-2026-09.md`'s XSP box names ONE measurement that
settles "is XSP worth a lane": XSP vs SPY NBBO spread at MATCHED ATM strikes, every
5 min across 3+ RTH sessions, expressed as $/round-trip on a 3-lot. The 2026-09-02
single live sample (`analysis/xsp/xsp-rth-spread-sample-2026-09-02.json`) found
spreads identical at $0.05 on both sides but flagged that the strikes may not have
been moneyness-matched, because XSP is an index-linked product with NO equity quote
feed -- its own spot cannot be read the way SPY's can. This script closes that gap:
it resolves each side's TRUE ATM strike independently every cycle instead of assuming
"same strike number = same moneyness".

XSP SPOT METHOD (state this plainly, because it is an inference, not a read)
------------------------------------------------------------------------------
XSP = SPX/10, but SPX is not in Alpaca's equity quote feed and this script does not
touch the TradingView chart (`tv_cdp.py`) to read it -- switching the live chart's
displayed symbol on every 5-minute fire would visibly disrupt J's own chart while he
may be working on it (`feedback_dont_disturb_user`), and CDP requires TradingView
Desktop to be up with a page open, which this read-only probe should not depend on.
Instead this uses PUT-CALL PARITY on XSP's OWN option chain: for a European,
cash-settled 0DTE contract with negligible time-to-expiry discounting and no
dividend timing effect at the ATM strike, C - P ~= S - K, so S ~= K + (call_mid -
put_mid). Two adjacent strikes (S0 = SPY's own rounded ATM strike as the starting
guess -- XSP trades numerically close to SPY, verified 2026-09-02: both quoted the
same "765" strike) are used and averaged when both resolve; one strike alone is
accepted (labelled) if only one has two-sided quotes; if NEITHER strike has a
two-sided quote on both legs, this FALLS BACK to using SPY's own spot as the XSP
strike guess (method="spy_proxy_fallback", clearly labelled in every row) rather
than fabricate a number. CAVEAT: parity ignores the (tiny, 0DTE) discount/dividend
term and is only as good as the very quotes it depends on -- if XSP's own book is
thin, the spot estimate inherits that noise. This is the documented, cheap,
self-contained method; a future run COULD switch to a real SPX feed if one gets
wired without disturbing the live chart.

THE CONSTRAINT THAT DOMINATES THE DESIGN (mirrors quote_recorder.py's own doctrine)
-------------------------------------------------------------------------------------
Read-only market-data probe. It is a SEPARATE PROCESS, never imported by and never
importing any live-order-path module (heartbeat_core.py, filters.py, risk_gate.py,
exit_manager.py, exit_actuator.py, fleet_executor.py, fleet_live.py, strategies.py,
build_shared_signal.py, accounts.json, params.json). Every REST call here is a
from-scratch minimal re-implementation (same doctrine as quote_recorder.py's own
module docstring #1) -- zero import-time or runtime coupling to the trading engine.
The only calls made are GET /v2/stocks/SPY/quotes/latest (SPY spot) and GET
/v1beta1/options/quotes/latest (option NBBO, batched). No POST, no DELETE, no
order/cancel/replace endpoint exists anywhere in this file. TOTAL fail-open: a
missing/unreadable quote never fabricates a value -- the row records
`status: "MISSING_<leg>[,MISSING_<leg>...]"` and every numeric field for that leg is
null. This can never raise into anything that could be mistaken for a trading-path
failure.

OUTPUT
------
analysis/xsp/xsp-spread-tape-YYYY-MM-DD.jsonl -- append-only, one row per 5-min cycle.
automation/state/xsp-spread-recorder-status.json -- this script's own health surface
(never engine state; nothing on the trading path reads this file).

CLI
---
  python xsp_spread_recorder.py --once                       # one cycle, smoke test
  python xsp_spread_recorder.py --once --dry-run              # no writes, stdout only
  python xsp_spread_recorder.py --loop --duration-sec 0        # run forever (RTH-gated)
  python xsp_spread_recorder.py --summarize --days 5           # read N days, print stats

Guard: backtest/tests/test_xsp_spread_recorder_2026_09_03.py (pure-logic, no network).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
SECRETS_PATH = REPO / "automation" / "state" / "fleet" / "secrets.json"
OUT_DIR = REPO / "analysis" / "xsp"
STATUS_PATH = REPO / "automation" / "state" / "xsp-spread-recorder-status.json"

sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from et_clock import et_now  # DST-aware; project_tz_systemic_fix -- never naive now()
except Exception:  # noqa: BLE001 -- degrade, never go dark for a clock import failure
    def et_now() -> dt.datetime:
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

SCHEMA = "xsp-spread-tape/1"
STATUS_SCHEMA = "xsp-spread-recorder-status/1"
OPTIONS_DATA_HOST = "https://data.alpaca.markets"

# Preference order for whose Alpaca key to use for these READ-ONLY market-data calls --
# any active arm's key works identically for public quote data; first available wins.
ARM_PREFERENCE = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")

DEFAULT_INTERVAL_S = 300     # 5 minutes, per the work order's measurement spec
RTH_START = "09:35"
RTH_END = "15:55"
RETENTION_DAYS = 120         # OP-22 cap -- generous; this is a small, low-cadence study
STRIKE_INCREMENT = 1.0       # both SPY and XSP 0DTE quote in $1 strikes (verified 09-02 sample)
QTY_3LOT = 3


# --------------------------------------------------------------------------------------- #
# Pure logic -- no network, no filesystem. What test_xsp_spread_recorder_2026_09_03.py
# exercises directly.
# --------------------------------------------------------------------------------------- #

def build_occ_symbol(root: str, trade_date: dt.date, side: str, strike: float) -> str:
    """OCC-style option symbol, UNPADDED root -- matches real Alpaca/broker symbols
    (same convention verified live for SPY in backtest/lib/option_pricing_real.py;
    re-implemented from scratch here per this file's independence doctrine)."""
    yymmdd = trade_date.strftime("%y%m%d")
    s = side.upper()
    assert s in ("C", "P"), f"side must be C or P, got {side!r}"
    root_u = root.upper()
    assert root_u.isalnum() and 1 <= len(root_u) <= 6, (
        f"root must be 1-6 alphanumeric characters (OSI root field width), got {root!r}"
    )
    return f"{root_u}{yymmdd}{s}{int(round(strike)) * 1000:08d}"


def round_to_atm_strike(spot: float, increment: float = STRIKE_INCREMENT) -> int:
    """Nearest strike on a fixed increment grid. Both SPY and XSP 0DTE quote $1
    strikes (verified in the 2026-09-02 sample: both used strike 765)."""
    return int(round(spot / increment) * increment)


def estimate_xsp_spot_via_parity(strike_quotes: "dict[int, dict[str, Optional[dict]]]"
                                 ) -> "tuple[Optional[float], str, dict]":
    """PUT-CALL PARITY spot estimate from XSP's own chain.

    strike_quotes: {strike: {"call": {"bid","ask"} | None, "put": {"bid","ask"} | None}}

    For each strike where BOTH legs have a two-sided quote: parity_est = strike +
    (call_mid - put_mid) (0DTE, discount/dividend term treated as negligible -- see
    module docstring caveat). Averages across however many strikes resolved.

    Returns (spot_est_or_None, method, detail):
      method == "put_call_parity_Nstrike" when >=1 strike resolved (N = count used)
      method == "parity_failed" (spot_est None) when no strike had two-sided quotes
      on both legs -- caller is responsible for falling back, this function never
      fabricates a fallback value itself.
    """
    per_strike: "dict[int, float]" = {}
    for strike, legs in strike_quotes.items():
        call = legs.get("call")
        put = legs.get("put")
        if not call or not put:
            continue
        cb, ca = call.get("bid"), call.get("ask")
        pb, pa = put.get("bid"), put.get("ask")
        if None in (cb, ca, pb, pa):
            continue
        call_mid = (cb + ca) / 2.0
        put_mid = (pb + pa) / 2.0
        per_strike[strike] = strike + (call_mid - put_mid)

    if not per_strike:
        return None, "parity_failed", {}
    spot_est = sum(per_strike.values()) / len(per_strike)
    return spot_est, f"put_call_parity_{len(per_strike)}strike", {"per_strike": per_strike}


def leg_metrics(quote: "Optional[dict]", qty: int = QTY_3LOT) -> dict:
    """One leg's row fields. quote = {"bid","ask","bid_size","ask_size"} or None.
    NEVER fabricates: a None/incomplete quote yields status MISSING with every
    numeric field null, not a zero or an interpolated guess."""
    if not quote or quote.get("bid") is None or quote.get("ask") is None:
        return {
            "status": "MISSING", "bid": None, "ask": None, "mid": None,
            "bid_size": None, "ask_size": None,
            "spread_abs": None, "spread_pct_of_mid": None, "rt_cost_3lot": None,
        }
    bid, ask = float(quote["bid"]), float(quote["ask"])
    mid = (bid + ask) / 2.0
    spread_abs = round(ask - bid, 4)
    spread_pct = round(spread_abs / mid, 6) if mid else None
    rt_cost = round(spread_abs * qty * 100, 2)
    return {
        "status": "OK", "bid": bid, "ask": ask, "mid": round(mid, 4),
        "bid_size": quote.get("bid_size"), "ask_size": quote.get("ask_size"),
        "spread_abs": spread_abs, "spread_pct_of_mid": spread_pct, "rt_cost_3lot": rt_cost,
    }


LEG_ORDER = ("spy_call", "spy_put", "xsp_call", "xsp_put")


def build_sample_row(now: dt.datetime, cycle_id: int, *, spy_spot: "Optional[float]",
                      xsp_spot_est: "Optional[float]", xsp_spot_method: str,
                      spy_strike: "Optional[int]", xsp_strike: "Optional[int]",
                      symbols: "dict[str, Optional[str]]",
                      quotes: "dict[str, Optional[dict]]",
                      qty: int = QTY_3LOT) -> dict:
    """PURE: assemble one output row from resolved strikes/symbols/quotes. A leg with
    no symbol (upstream resolution failed, e.g. no spot at all) or no quote is
    recorded MISSING -- never fabricated. `status` is OK only if every leg is OK."""
    legs = {}
    missing = []
    for leg in LEG_ORDER:
        sym = symbols.get(leg)
        q = quotes.get(sym) if sym else None
        m = leg_metrics(q, qty=qty)
        m["symbol"] = sym
        legs[leg] = m
        if m["status"] != "OK":
            missing.append(f"MISSING_{leg.upper()}")

    row = {
        "schema": SCHEMA,
        "ts_et": now.isoformat(),
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_et": now.strftime("%Y-%m-%d"),
        "cycle_id": cycle_id,
        "spy_spot": spy_spot,
        "xsp_spot_est": xsp_spot_est,
        "xsp_spot_method": xsp_spot_method,
        "spy_strike": spy_strike,
        "xsp_strike": xsp_strike,
        "legs": legs,
        "status": "OK" if not missing else ",".join(missing),
        "source": "alpaca_options_quotes_latest+stocks_quotes_latest",
    }
    return row


def summarize_rows(rows: "list[dict]") -> dict:
    """PURE: matched-time comparison stats over a batch of rows already loaded from
    disk. Only OK legs contribute to that leg's numbers (a MISSING leg contributes
    to nothing but is visible in `n_missing_by_leg`). Returns medians/p90s for
    spread_abs and rt_cost_3lot per side (SPY = spy_call+spy_put pooled, XSP =
    xsp_call+xsp_put pooled), depth medians (min(bid_size,ask_size) per OK leg), and
    the % of XSP-side leg-samples with depth < 3 lots."""
    def pct(values: "list[float]", p: float) -> "Optional[float]":
        if not values:
            return None
        s = sorted(values)
        idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
        return s[idx]

    per_side_spread: "dict[str, list[float]]" = {"spy": [], "xsp": []}
    per_side_rt: "dict[str, list[float]]" = {"spy": [], "xsp": []}
    per_side_depth: "dict[str, list[int]]" = {"spy": [], "xsp": []}
    xsp_thin_count = 0
    xsp_leg_count = 0
    n_missing_by_leg = {leg: 0 for leg in LEG_ORDER}
    n_rows = len(rows)
    n_rows_all_ok = 0

    for row in rows:
        legs = row.get("legs", {}) or {}
        row_all_ok = True
        for leg in LEG_ORDER:
            m = legs.get(leg) or {}
            side = "spy" if leg.startswith("spy") else "xsp"
            if m.get("status") != "OK":
                n_missing_by_leg[leg] = n_missing_by_leg.get(leg, 0) + 1
                row_all_ok = False
                continue
            if m.get("spread_abs") is not None:
                per_side_spread[side].append(m["spread_abs"])
            if m.get("rt_cost_3lot") is not None:
                per_side_rt[side].append(m["rt_cost_3lot"])
            bs, asz = m.get("bid_size"), m.get("ask_size")
            if isinstance(bs, (int, float)) and isinstance(asz, (int, float)):
                depth = min(bs, asz)
                per_side_depth[side].append(depth)
                if side == "xsp":
                    xsp_leg_count += 1
                    if depth < 3:
                        xsp_thin_count += 1
        if row_all_ok:
            n_rows_all_ok += 1

    out = {"n_rows": n_rows, "n_rows_all_legs_ok": n_rows_all_ok,
           "n_missing_by_leg": n_missing_by_leg}
    for side in ("spy", "xsp"):
        sp = per_side_spread[side]
        rt = per_side_rt[side]
        dp = per_side_depth[side]
        out[side] = {
            "n_leg_samples": len(sp),
            "median_spread_abs": statistics.median(sp) if sp else None,
            "p90_spread_abs": pct(sp, 90),
            "median_rt_cost_3lot": statistics.median(rt) if rt else None,
            "p90_rt_cost_3lot": pct(rt, 90),
            "median_depth": statistics.median(dp) if dp else None,
        }
    out["xsp_pct_depth_below_3lot"] = (
        round(100.0 * xsp_thin_count / xsp_leg_count, 1) if xsp_leg_count else None
    )
    return out


def is_rth_window(now: dt.datetime) -> bool:
    if now.weekday() >= 5:
        return False
    hm = now.strftime("%H:%M")
    return RTH_START <= hm <= RTH_END


def prune_old_files(directory: Path, cutoff_date: dt.date,
                     pattern: str = "xsp-spread-tape-*.jsonl") -> "list[str]":
    deleted = []
    if not directory.exists():
        return deleted
    for p in sorted(directory.glob(pattern)):
        stem = p.stem.replace("xsp-spread-tape-", "")
        try:
            file_date = dt.datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff_date:
            try:
                p.unlink()
                deleted.append(p.name)
            except OSError:
                pass
    return deleted


# --------------------------------------------------------------------------------------- #
# Network -- from-scratch, minimal, read-only. Never imported by / never importing any
# live-order-path module (see module docstring).
# --------------------------------------------------------------------------------------- #

def load_one_key(secrets_path: Path = SECRETS_PATH,
                  preference: "tuple[str, ...]" = ARM_PREFERENCE) -> "Optional[dict]":
    """{key, secret, base_url, arm} for the first available arm in `preference`, or
    None if secrets.json is missing/unreadable/empty. Any active arm's key works
    identically for these public read-only quote endpoints."""
    if not secrets_path.exists():
        return None
    try:
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    accounts = data.get("accounts", data) if isinstance(data, dict) else {}
    for arm in preference:
        c = accounts.get(arm)
        if isinstance(c, dict) and c.get("key") and c.get("secret"):
            return {"key": c["key"], "secret": c["secret"], "arm": arm}
    return None


def _get_json(url: str, headers: "dict[str, str]", timeout: float = 10.0
              ) -> "tuple[Any, Optional[str]]":
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


def get_spy_spot(creds: dict) -> "tuple[Optional[float], Optional[str]]":
    """(mid, error) from SPY's equity NBBO. error is None on a normal (possibly
    two-sided-missing) read; a two-sided-missing quote returns (None, None) --
    genuinely no quote right now, not a fetch error."""
    url = f"{OPTIONS_DATA_HOST}/v2/stocks/SPY/quotes/latest"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    payload, err = _get_json(url, headers)
    if err is not None:
        return None, err
    q = (payload or {}).get("quote") if isinstance(payload, dict) else None
    if not isinstance(q, dict):
        return None, None
    bid, ask = q.get("bp"), q.get("ap")
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and bid > 0 and ask > 0:
        return round((bid + ask) / 2.0, 4), None
    return None, None


def get_option_nbbo_batch(creds: dict, symbols: "list[str]"
                          ) -> "tuple[dict[str, dict], Optional[str]]":
    """({symbol: {"bid","ask","bid_size","ask_size"}}, error). One batched request
    for all requested symbols (Alpaca's /quotes/latest accepts a comma-separated
    `symbols` list) -- keeps this at ~2 requests/cycle regardless of leg count."""
    symbols = [s for s in dict.fromkeys(symbols) if s]  # de-dupe, preserve order
    if not symbols:
        return {}, None
    qs = urllib.parse.quote(",".join(symbols), safe=",")
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={qs}"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    payload, err = _get_json(url, headers)
    if err is not None:
        return {}, err
    raw = (payload or {}).get("quotes", {}) if isinstance(payload, dict) else {}
    out: "dict[str, dict]" = {}
    for sym, q in (raw or {}).items():
        if not isinstance(q, dict):
            continue
        bid, ask = q.get("bp"), q.get("ap")
        out[sym] = {
            "bid": float(bid) if isinstance(bid, (int, float)) and bid > 0 else None,
            "ask": float(ask) if isinstance(ask, (int, float)) and ask > 0 else None,
            "bid_size": q.get("bs"),
            "ask_size": q.get("as"),
        }
    return out, None


# --------------------------------------------------------------------------------------- #
# Status file -- this script's own health surface (never engine state).
# --------------------------------------------------------------------------------------- #

def write_status(status: dict, path: Path = STATUS_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def read_status(path: Path = STATUS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------------------- #
# One cycle
# --------------------------------------------------------------------------------------- #

def run_cycle(creds: "Optional[dict]", cycle_id: int, *, dry_run: bool = False,
              out_dir: Path = OUT_DIR) -> dict:
    """One full poll: SPY spot -> XSP parity strikes -> final ATM legs -> row.
    NEVER raises -- every network sub-step is individually guarded."""
    now = et_now()
    trade_date = now.date()
    errors: "dict[str, str]" = {}

    if creds is None:
        row = build_sample_row(now, cycle_id, spy_spot=None, xsp_spot_est=None,
                                xsp_spot_method="no_creds", spy_strike=None,
                                xsp_strike=None, symbols={leg: None for leg in LEG_ORDER},
                                quotes={})
        errors["_creds"] = "no Alpaca key available in secrets.json"
        return _finish_cycle(now, cycle_id, row, errors, dry_run, out_dir)

    try:
        spy_spot, err = get_spy_spot(creds)
    except Exception as exc:  # noqa: BLE001
        spy_spot, err = None, f"unexpected: {exc!r}"[:300]
    if err:
        errors["spy_spot"] = err

    if spy_spot is None:
        row = build_sample_row(now, cycle_id, spy_spot=None, xsp_spot_est=None,
                                xsp_spot_method="no_spy_spot", spy_strike=None,
                                xsp_strike=None, symbols={leg: None for leg in LEG_ORDER},
                                quotes={})
        errors.setdefault("spy_spot", "no two-sided SPY quote this cycle")
        return _finish_cycle(now, cycle_id, row, errors, dry_run, out_dir)

    spy_strike = round_to_atm_strike(spy_spot)
    k0 = spy_strike
    k1 = spy_strike + 1

    parity_symbols = {
        (k0, "call"): build_occ_symbol("XSP", trade_date, "C", k0),
        (k0, "put"): build_occ_symbol("XSP", trade_date, "P", k0),
        (k1, "call"): build_occ_symbol("XSP", trade_date, "C", k1),
        (k1, "put"): build_occ_symbol("XSP", trade_date, "P", k1),
    }
    try:
        parity_quotes, err = get_option_nbbo_batch(creds, list(parity_symbols.values()))
    except Exception as exc:  # noqa: BLE001
        parity_quotes, err = {}, f"unexpected: {exc!r}"[:300]
    if err:
        errors["xsp_parity_quotes"] = err

    strike_quotes = {
        k0: {"call": parity_quotes.get(parity_symbols[(k0, "call")]),
             "put": parity_quotes.get(parity_symbols[(k0, "put")])},
        k1: {"call": parity_quotes.get(parity_symbols[(k1, "call")]),
             "put": parity_quotes.get(parity_symbols[(k1, "put")])},
    }
    xsp_spot_est, xsp_spot_method, _detail = estimate_xsp_spot_via_parity(strike_quotes)

    if xsp_spot_est is not None:
        xsp_strike = round_to_atm_strike(xsp_spot_est)
    else:
        xsp_strike = spy_strike
        xsp_spot_method = "spy_proxy_fallback"
        errors.setdefault("xsp_spot", "parity failed on both candidate strikes; used SPY spot as XSP strike guess")

    symbols = {
        "spy_call": build_occ_symbol("SPY", trade_date, "C", spy_strike),
        "spy_put": build_occ_symbol("SPY", trade_date, "P", spy_strike),
        "xsp_call": build_occ_symbol("XSP", trade_date, "C", xsp_strike),
        "xsp_put": build_occ_symbol("XSP", trade_date, "P", xsp_strike),
    }
    final_quotes = dict(parity_quotes)  # reuse anything already fetched at k0/k1
    need = [s for s in symbols.values() if s not in final_quotes]
    if need:
        try:
            fetched, err = get_option_nbbo_batch(creds, need)
        except Exception as exc:  # noqa: BLE001
            fetched, err = {}, f"unexpected: {exc!r}"[:300]
        if err:
            errors["final_quotes"] = err
        final_quotes.update(fetched)

    row = build_sample_row(now, cycle_id, spy_spot=spy_spot, xsp_spot_est=xsp_spot_est,
                            xsp_spot_method=xsp_spot_method, spy_strike=spy_strike,
                            xsp_strike=xsp_strike, symbols=symbols, quotes=final_quotes)
    return _finish_cycle(now, cycle_id, row, errors, dry_run, out_dir)


def _finish_cycle(now: dt.datetime, cycle_id: int, row: dict, errors: dict,
                   dry_run: bool, out_dir: Path) -> dict:
    written = 0
    if not dry_run:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"xsp-spread-tape-{now.strftime('%Y-%m-%d')}.jsonl"
            with out_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            written = 1
        except OSError as exc:
            errors["_write"] = f"{type(exc).__name__}: {exc}"
    else:
        print(json.dumps(row, indent=2, default=str))
        written = 1
    return {
        "ts_et": now.isoformat(), "cycle_id": cycle_id, "row_status": row.get("status"),
        "rows_written": written, "errors": errors, "ok": not errors,
    }


# --------------------------------------------------------------------------------------- #
# Summarize mode
# --------------------------------------------------------------------------------------- #

def load_tape_rows(out_dir: Path, days: int, now: "Optional[dt.datetime]" = None) -> "list[dict]":
    now = now or et_now()
    cutoff = now.date() - dt.timedelta(days=days - 1)
    rows: "list[dict]" = []
    if not out_dir.exists():
        return rows
    for p in sorted(out_dir.glob("xsp-spread-tape-*.jsonl")):
        stem = p.stem.replace("xsp-spread-tape-", "")
        try:
            file_date = dt.datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            continue
    return rows


def run_summarize(out_dir: Path, days: int) -> int:
    rows = load_tape_rows(out_dir, days)
    stats = summarize_rows(rows)
    print(f"XSP vs SPY spread study -- last {days} day(s), {stats['n_rows']} sample(s) "
          f"({stats['n_rows_all_legs_ok']} with all 4 legs OK)")
    if stats["n_rows"] == 0:
        print("No tape data found -- nothing to summarize yet.")
        return 0
    for side in ("spy", "xsp"):
        s = stats[side]
        print(f"  {side.upper()}: n_leg_samples={s['n_leg_samples']} "
              f"median_spread=${s['median_spread_abs']} p90_spread=${s['p90_spread_abs']} "
              f"median_rt_cost_3lot=${s['median_rt_cost_3lot']} "
              f"p90_rt_cost_3lot=${s['p90_rt_cost_3lot']} median_depth={s['median_depth']}")
    print(f"  XSP legs with depth < 3 lots: {stats['xsp_pct_depth_below_3lot']}%")
    print(f"  missing-by-leg: {stats['n_missing_by_leg']}")
    return 0


# --------------------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------------------- #

def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--duration-sec", type=int, default=0)
    ap.add_argument("--interval-sec", type=int, default=DEFAULT_INTERVAL_S)
    ap.add_argument("--rth-only", dest="rth_only", action="store_true", default=True)
    ap.add_argument("--no-rth-only", dest="rth_only", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--status-path", default=str(STATUS_PATH))
    ap.add_argument("--secrets-path", default=str(SECRETS_PATH))
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--days", type=int, default=5, help="--summarize only: how many days to read")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)

    if args.summarize:
        return run_summarize(out_dir, args.days)

    if not args.once and not args.loop:
        args.once = True

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

    while True:
        cycle_id += 1
        now = et_now()
        try:
            deleted = prune_old_files(out_dir, now.date() - dt.timedelta(days=RETENTION_DAYS))
        except Exception:  # noqa: BLE001
            deleted = []

        skip_reason = None
        if args.rth_only and not is_rth_window(now):
            skip_reason = f"outside RTH window ({RTH_START}-{RTH_END} ET weekdays)"
            summary = {"ts_et": now.isoformat(), "cycle_id": cycle_id, "row_status": None,
                       "rows_written": 0, "errors": {}, "ok": True}
        else:
            try:
                creds = load_one_key(secrets_path)
            except Exception as exc:  # noqa: BLE001
                creds = None
                creds_err = repr(exc)[:300]
            else:
                creds_err = None
            try:
                summary = run_cycle(creds, cycle_id, dry_run=args.dry_run, out_dir=out_dir)
            except Exception as exc:  # noqa: BLE001
                summary = {"ts_et": now.isoformat(), "cycle_id": cycle_id, "row_status": None,
                           "rows_written": 0, "errors": {"_cycle": repr(exc)[:300]}, "ok": False}
            if creds_err:
                summary["errors"]["_creds"] = creds_err
                summary["ok"] = False

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
            "last_cycle_row_status": summary.get("row_status"),
            "last_cycle_rows_written": summary.get("rows_written"),
            "last_cycle_errors": summary.get("errors"),
            "last_success_ts_et": last_success_ts,
            "consecutive_cycle_failures": consecutive_failures,
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

        interval = args.interval_sec
        if skip_reason:
            interval = max(interval, 300)
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
    except Exception as exc:  # noqa: BLE001 -- absolute last resort
        try:
            write_status({"schema": STATUS_SCHEMA, "fatal_error": repr(exc)[:500],
                          "ts_et": et_now().isoformat()})
        except Exception:  # noqa: BLE001
            pass
        print(f"[xsp_spread_recorder] FATAL (non-trading-path, contained): {exc!r}", file=sys.stderr)
        sys.exit(1)
