"""dress_rehearsal.py — nightly REAL-broker-boundary dress rehearsal (the "are we good
for tomorrow" instrument, built 2026-07-01).

J's pain: "every time I asked 'are we good for tomorrow' I got green-lit, then it fails
the next morning." Unit guards mock the broker; the killers all live AT the boundary:
42210000 complex-order rejections, limit-at-mid never crossing, 'expires soon', stale
keys (401), wrong OCC symbol construction. This script exercises the REAL Alpaca paper
API tonight, through the engine's OWN placement code, and writes a verdict J can glance
at (automation/state/dress-rehearsal.json).

CHECKS (all $0, paper, idempotent, self-cleaning):
  1. OPTIONS ORDER ACCEPTANCE (per account, safe-2 + bold-2): find the next trading
     day's SPY chain, pick a deep-OTM (<= $0.05 premium) contract, place a 1-lot buy
     LIMIT @ $0.01 (never marketable — must NOT fill) via the engine's exact
     heartbeat_core._place_simple_entry POST, verify broker ACCEPTED it, cancel, verify
     canceled + zero open orders + zero positions. Cross-checks the engine's _occ symbol
     construction against the broker-listed contract symbol.
     If Alpaca refuses option orders outside RTH the verdict is INCONCLUSIVE_AFTER_HOURS
     (body quoted) — NEVER silently green.
  2. CRYPTO ROUND-TRIP (safe-2 only): market-buy $10 notional BTC/USD (the broker's own
     minimum — Alpaca 403 40310000 below $10, found live 2026-07-01), poll the fill,
     market-sell the position, poll flat. Proves auth + POST + fill + position machinery
     LIVE tonight (crypto trades 24/7). Hard $10 notional cap; finally-block flattens
     any residual (verify-flat pattern, DELETE-positions retry).
  3. KEY/CLOCK/FEED SANITY: /v2/clock on both accounts says the market opens on the next
     trading day at 09:30 ET; sight-beacon fresh (<24h — i.e. it ran today); options
     approval level readable and >= 2 on both accounts.

VERDICTS: per-check GREEN / RED / INCONCLUSIVE_AFTER_HOURS; overall GREEN only when
every check is GREEN (INCONCLUSIVE propagates to overall INCONCLUSIVE — J's green-light
is never softened). Fail-open: any crash writes a RED artifact and exits 0.

IDEMPOTENT-BY-DEFAULT + AtLogOn BACKUP TRIGGER (added 2026-08-26): the primary 20:45 ET
daily trigger was found to land in a reboot gap on several nights (2026-08-24/25/26 all
missed — J's machine reboots most evenings in the 18:00-22:00 MT window per Kernel-Power
event log, and Windows Task Scheduler's StartWhenAvailable catch-up does not reliably
recover more than one missed occurrence). Fix: every run now SKIPS real work by default if
today's ET-date rehearsal already succeeded in writing an artifact (see
_ran_today_already) — pass --force to override (used by an operator manually re-running).
This makes it safe to add a SECOND trigger (AtLogOn, +10min delay) to the SAME
Gamma_DressRehearsal task as a backup: if the 20:45 ET trigger was missed, the next login
catches it up for real; if it already ran, the login-trigger fire is a fast no-op. (A
brand-new SEPARATE task would have been cleaner, but Register-ScheduledTask/schtasks
/Create both returned Access Denied from this session's shell context — Set-ScheduledTask
on the EXISTING task, i.e. a modify not a create, is what this session's ACLs permit.)

Guards: backtest/tests/test_dress_rehearsal.py (payload parity engine vs replica, OCC
parity, $10 crypto cap, overall-verdict logic, self_check reader, idempotent-skip).
Run:   backtest/.venv/Scripts/python.exe setup/scripts/dress_rehearsal.py [--force]
Task:  Gamma_DressRehearsal — daily 20:45 ET trigger (primary) + AtLogOn +10min (backup,
       added 2026-08-26). Both fire the identical no-arg action; the skip-if-already-ran
       default makes duplicate fires a no-op.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "dress-rehearsal.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "dress-rehearsal.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import sys
import time as _time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet"):
    sys.path.insert(0, str(REPO / _p))

from et_clock import et_now, et_weekday  # noqa: E402
import fleet_broker as fb  # noqa: E402

STATE = REPO / "automation" / "state"
OUT = STATE / "dress-rehearsal.json"
BEACON = STATE / "sight-beacon.json"

ARMS = {"safe": "safe-2", "bold": "bold-2"}  # heartbeat_core.ACCOUNTS fleet_arm mapping
DATA_HOST = "https://data.alpaca.markets"
ACCEPT_STATUSES = ("new", "accepted", "pending_new")
CANCEL_TERMINAL = ("canceled", "cancelled", "expired", "rejected", "done_for_day")
DEEP_OTM_PCT = 0.05          # strike ~5% away from spot
MAX_PREMIUM = 0.05           # deep-OTM premium ceiling ($/share)
PROBE_LIMIT = 0.01           # never-marketable probe price
CRYPTO_NOTIONAL = 10.0       # broker MINIMUM: Alpaca 403 40310000 "cost basis must be
#                              >= minimal amount of order 10" (found live 2026-07-01)
CRYPTO_NOTIONAL_CAP = 10.0   # HARD cap — guard-tested; placement refuses anything ABOVE this
END_STATE_RETRIES = 5        # retries for the post-cancel open-orders/positions listing
END_STATE_RETRY_SLEEP = 1.5  # seconds between retries (index-lag tolerance, found 2026-07-21)


# ── engine placement path (the point of the whole rehearsal) ──────────────────

def _replica_simple_entry(creds: dict, *, symbol: str, qty: int, limit_price: float) -> dict:
    """Byte-identical replica of heartbeat_core._place_simple_entry's POST (fallback only
    if the engine module can't import). Guard test_payload_parity REDs on any drift."""
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty}"}
    if limit_price is None or float(limit_price) <= 0:
        return {"_refused": f"invalid limit_price {limit_price}"}
    order = {"symbol": symbol, "qty": str(int(qty)), "side": "buy", "type": "limit",
             "limit_price": str(round(float(limit_price), 2)), "time_in_force": "day"}
    res = fb._request(creds, "orders", method="POST", data=order)
    if not isinstance(res, dict):
        return {"_error": f"unexpected broker response: {res!r}"}
    return res


def _replica_occ(side: str, strike: float, expiry: datetime) -> str:
    """Byte-identical replica of heartbeat_core._occ. Guard test_occ_parity REDs on drift."""
    cp = "C" if side == "C" else "P"
    return f"SPY{expiry.strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


def _engine_placement() -> tuple:
    """(place_fn, occ_fn, source). Prefer the ENGINE'S OWN functions (import
    heartbeat_core read-only); fall back to the guard-pinned replicas."""
    try:
        import heartbeat_core as hc  # noqa: PLC0415
        return hc._place_simple_entry, hc._occ, "heartbeat_core (engine's own functions)"
    except Exception as e:  # noqa: BLE001
        return (_replica_simple_entry, _replica_occ,
                f"replica (heartbeat_core import failed: {type(e).__name__}: {e})")


# ── small REST helpers (reuse fleet_broker._request for the trading API) ──────

def _data_get(creds: dict, path: str) -> dict:
    req = urllib.request.Request(DATA_HOST + path, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        return {"_error": str(e), "_status": e.code, "_body": body}
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def _next_trading_day(creds: dict, today: datetime) -> str | None:
    """The next date the market OPENS, per the broker's own /v2/clock — never guessed
    from calendar-days-after-today. 2026-07-28 scar: a `calendar?start=today+1` query
    is correct ONLY when called after today's close; called before today's own open
    (e.g. an off-schedule manual run at 01:xx ET) it skips today entirely and disagrees
    with check3_sanity's clock read, false-RED-ing a rehearsal whose options-order-
    acceptance check (the actual point of the probe) is fine. The broker's `next_open`
    is authoritative and self-consistent regardless of what time the script runs
    (C11: broker is the source of truth) — use it, with the old calendar-endpoint
    query kept ONLY as a fallback if the clock call itself is unreadable."""
    clock = fb._request(creds, "clock")
    nxt = clock.get("next_open") if isinstance(clock, dict) else None
    if isinstance(nxt, str) and len(nxt) >= 10:
        return nxt[:10]
    start = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=10)).strftime("%Y-%m-%d")
    cal = fb._request(creds, f"calendar?start={start}&end={end}")
    if isinstance(cal, list) and cal:
        return str(cal[0].get("date"))
    return None


def _spy_spot(creds: dict) -> float | None:
    d = _data_get(creds, "/v2/stocks/SPY/trades/latest?feed=iex")
    try:
        return float(d["trade"]["p"])
    except (KeyError, TypeError, ValueError):
        return None


# 2026-07-28 L(pending): the original fixed target-10 window found only 3 tradable
# contracts (SPY's far-OTM chain is sparsely listed -- 695/700/701, not $1-spaced) and
# NONE closed <= MAX_PREMIUM (closest $0.06-0.08) -- a false RED on BOTH accounts every
# night the near-target strikes happen to price a few cents rich. Verified live 2026-07-28
# (spot 738.85): widening to target-30 immediately surfaces strike 690 @ $0.05. Escalate
# through successively wider bands so a temporarily-rich near-target strike can never
# starve the probe of a real deep-OTM candidate.
STRIKE_SEARCH_BANDS = (10, 30, 60, 100)  # widening offsets below target, in strike-price $


def _pick_deep_otm_put(creds: dict, expiry: str, spot: float, ev: list) -> dict | None:
    """Deep-OTM put ~5% below spot with premium <= MAX_PREMIUM. Returns the broker
    contract dict (carries the authoritative symbol + strike) or None."""
    target = spot * (1.0 - DEEP_OTM_PCT)
    closest_seen = None
    for band in STRIKE_SEARCH_BANDS:
        q = (f"options/contracts?underlying_symbols=SPY&expiration_date={expiry}"
             f"&type=put&strike_price_gte={target - band:.2f}&strike_price_lte={target:.2f}"
             f"&status=active&limit=200")
        res = fb._request(creds, q)
        contracts = res.get("option_contracts") if isinstance(res, dict) else None
        if not contracts:
            ev.append(f"band={band}: contracts query FAILED or empty: {json.dumps(res)[:400]}")
            continue
        # closest to the 5%-away target first (strike descending), tradable only
        cands = sorted([c for c in contracts if c.get("tradable", True)],
                       key=lambda c: -float(c.get("strike_price", 0)))
        if cands and closest_seen is None:
            closest_seen = cands[0]
        for c in cands:
            cp = c.get("close_price")
            try:
                premium = float(cp) if cp not in (None, "") else None
            except (TypeError, ValueError):
                premium = None
            if premium is None or premium <= MAX_PREMIUM:
                ev.append(f"picked {c.get('symbol')} strike={c.get('strike_price')} "
                          f"close_price={cp!r} (target ~{target:.0f}, spot {spot:.2f}, band={band})")
                return c
    if closest_seen is not None:
        ev.append(f"no candidate <= ${MAX_PREMIUM:.2f} across bands {STRIKE_SEARCH_BANDS} "
                  f"(closest close_price={closest_seen.get('close_price')!r})")
    else:
        ev.append(f"no tradable contracts found in any band {STRIKE_SEARCH_BANDS} "
                  f"below target {target:.2f}")
    return None


def _classify_rejection(status, body_text: str) -> tuple[str, str]:
    """(verdict, reason) for a broker rejection of the probe order.
    Known killer classes -> RED. A genuine outside-RTH refusal -> INCONCLUSIVE_AFTER_HOURS.
    Unknown rejection -> RED (never soften toward green)."""
    txt = (body_text or "").lower()
    if status in (401, 403):
        return "RED", f"HTTP {status} auth failure — stale/revoked key class"
    if "42210000" in txt or "complex order" in txt:
        return "RED", "complex-order rejection (42210000) — payload regression class"
    if any(s in txt for s in ("market is closed", "outside of market hours",
                              "not open", "extended hours", "after hours",
                              "orders are not allowed at this time")):
        return "INCONCLUSIVE_AFTER_HOURS", "broker refuses option orders outside RTH"
    return "RED", "unrecognized rejection — NOT proven for tomorrow (investigate body)"


# ── CHECK 1: options order acceptance via the engine's exact code path ─────────

def check1_options_acceptance(account: str, creds: dict, place_fn, occ_fn,
                              expiry: str, spot: float) -> dict:
    ev: list = []
    out = {"verdict": "RED", "evidence": ev}
    contract = _pick_deep_otm_put(creds, expiry, spot, ev)
    if contract is None:
        out["verdict"] = "RED"
        ev.append("could not select a deep-OTM contract — chain unreadable")
        return out
    sym = str(contract["symbol"])
    strike = float(contract["strike_price"])
    # engine symbol-construction cross-check (historical killer: wrong OCC construction)
    occ = occ_fn("P", strike, datetime.strptime(expiry, "%Y-%m-%d"))
    if occ != sym:
        ev.append(f"OCC MISMATCH: engine _occ built {occ!r} but broker lists {sym!r}")
        return out
    ev.append(f"engine _occ('P', {strike}, {expiry}) == broker symbol {sym} (parity OK)")

    res = place_fn(creds, symbol=sym, qty=1, limit_price=PROBE_LIMIT)
    ev.append("POST /v2/orders (engine _place_simple_entry) response: " + json.dumps(res))
    if res.get("_error") or res.get("_refused"):
        verdict, reason = _classify_rejection(res.get("_status"), json.dumps(res.get("_body") or res))
        out["verdict"] = verdict
        ev.append(f"classification: {reason}")
        return out
    oid, status = res.get("id"), str(res.get("status", "")).lower()
    if not oid or status not in ACCEPT_STATUSES:
        ev.append(f"NOT ACCEPTED: id={oid!r} status={status!r} (expected {ACCEPT_STATUSES})")
        return out
    ev.append(f"ACCEPTED: order id={oid} status={status}")

    # cancel + poll to terminal
    cres = fb.cancel_order(creds, oid, live=True)
    ev.append(f"DELETE /v2/orders/{oid} response: {json.dumps(cres)}")
    final = None
    for _ in range(10):
        o = fb.get_order(creds, oid)
        final = str(o.get("status", "")).lower()
        if final in CANCEL_TERMINAL:
            break
        _time.sleep(1.0)
    ev.append(f"post-cancel poll: status={final!r}")
    if final not in CANCEL_TERMINAL:
        ev.append("order did NOT reach a canceled/terminal state — residue risk")
        return out

    # end-state: zero open orders + zero positions on this account.
    # Alpaca's GET /v2/orders?status=open list endpoint is backed by a different
    # index than the single-order GET we just polled to a confirmed terminal
    # status above, and can lag it by ~1-2s (eventual consistency, found live
    # 2026-07-21: safe RED'd on a stale listing while bold GREENed moments later
    # on an identical code path — same non-determinism, not a real residue).
    # Retry with backoff before declaring NOT CLEAN so a transient index lag
    # doesn't false-RED the whole rehearsal.
    open_orders, positions, n_open = [], [], -1
    for attempt in range(END_STATE_RETRIES):
        open_orders = fb._request(creds, "orders?status=open&limit=100")
        positions = fb.get_positions(creds)
        n_open = len(open_orders) if isinstance(open_orders, list) else -1
        if n_open == 0 and len(positions) == 0:
            break
        if attempt < END_STATE_RETRIES - 1:
            _time.sleep(END_STATE_RETRY_SLEEP)
    ev.append(f"end-state: open_orders={n_open} positions={len(positions)} "
              f"(after up to {END_STATE_RETRIES} tries, {END_STATE_RETRY_SLEEP}s apart)")
    if n_open != 0 or len(positions) != 0:
        ev.append(f"NOT CLEAN: open_orders={json.dumps(open_orders)[:400]} "
                  f"positions={json.dumps(positions)[:400]}")
        return out
    out["verdict"] = "GREEN"
    return out


# ── CHECK 2: crypto round-trip (real fill, 24/7) ───────────────────────────────

def _place_crypto_market(creds: dict, *, side: str, notional: float | None = None,
                         qty: str | None = None) -> dict:
    """The one crypto POST. HARD-refuses any notional above CRYPTO_NOTIONAL_CAP —
    guard-tested so the cap can never be edited away silently."""
    if notional is not None and float(notional) > CRYPTO_NOTIONAL_CAP:
        return {"_refused": f"notional {notional} exceeds hard cap {CRYPTO_NOTIONAL_CAP}"}
    order: dict = {"symbol": "BTC/USD", "side": side, "type": "market",
                   "time_in_force": "gtc"}
    if notional is not None:
        order["notional"] = f"{float(notional):.2f}"
    elif qty is not None:
        order["qty"] = str(qty)
    else:
        return {"_refused": "need notional or qty"}
    return fb._request(creds, "orders", method="POST", data=order)


def _flatten_crypto(creds: dict, ev: list) -> None:
    """verify-flat pattern: DELETE positions/BTCUSD, retry until broker-flat."""
    for i in range(6):
        pos = fb._request(creds, "positions/BTCUSD")
        if isinstance(pos, dict) and pos.get("_status") == 404:
            ev.append(f"flatten: broker-flat confirmed (positions/BTCUSD -> 404, try {i})")
            return
        if isinstance(pos, dict) and pos.get("_error"):
            ev.append(f"flatten: position read error {json.dumps(pos)[:200]}")
        else:
            d = fb._request(creds, "positions/BTCUSD", method="DELETE")
            ev.append(f"flatten: DELETE positions/BTCUSD -> {json.dumps(d)[:300]}")
        _time.sleep(2.0)
    ev.append("flatten: WARNING — could not confirm broker-flat after retries")


def check2_crypto_roundtrip(creds: dict) -> dict:
    ev: list = []
    out = {"verdict": "RED", "evidence": ev}
    try:
        buy = _place_crypto_market(creds, side="buy", notional=CRYPTO_NOTIONAL)
        ev.append(f"BUY POST (BTC/USD ${CRYPTO_NOTIONAL:.2f} notional market): {json.dumps(buy)}")
        if buy.get("_error") or buy.get("_refused") or not buy.get("id"):
            return out
        bfill = fb.poll_fill(creds, buy["id"], attempts=8, sleep_sec=1.5)
        ev.append(f"BUY fill poll: status={bfill['status']} filled_qty={bfill['filled_qty']} "
                  f"filled_avg_price={bfill['filled_avg_price']}")
        if not bfill["filled"]:
            ev.append("buy did NOT fill — crypto market order machinery not proven")
            return out
        # sell what the POSITION shows (fees can make position qty < order filled_qty)
        pos = fb._request(creds, "positions/BTCUSD")
        qty_avail = str(pos.get("qty_available") or pos.get("qty") or "")
        ev.append(f"position after buy: qty={pos.get('qty')!r} qty_available={qty_avail!r} "
                  f"market_value={pos.get('market_value')!r}")
        if not qty_avail or float(qty_avail) <= 0:
            ev.append("no position visible after a confirmed fill — position machinery broken")
            return out
        sell = _place_crypto_market(creds, side="sell", qty=qty_avail)
        ev.append(f"SELL POST (qty={qty_avail}): {json.dumps(sell)}")
        if sell.get("_error") or sell.get("_refused") or not sell.get("id"):
            return out
        sfill = fb.poll_fill(creds, sell["id"], attempts=8, sleep_sec=1.5)
        ev.append(f"SELL fill poll: status={sfill['status']} filled_qty={sfill['filled_qty']} "
                  f"filled_avg_price={sfill['filled_avg_price']}")
        if not sfill["filled"]:
            ev.append("sell did NOT fill")
            return out
        out["verdict"] = "GREEN"
        return out
    finally:
        _flatten_crypto(creds, ev)


# ── CHECK 3: key/clock/feed sanity ─────────────────────────────────────────────

def check3_sanity(creds_map: dict, next_day: str | None, *, is_weekend: bool = False) -> dict:
    """is_weekend: True when the rehearsal itself is running on a Sat/Sun (ET). The
    beacon only ticks during weekday RTH (heartbeat_core's eye) -- on a weekend night
    it is CORRECTLY >24h stale by design, same as engine_health.py's sight_beacon check
    ("market closed -- quiet OK"). Without this exemption, DaysInterval=1 nightly cadence
    (Gamma_DressRehearsal runs every calendar day, incl. weekends) produced a false RED
    every Sat+Sun night forever -- root-caused 2026-07-26 conductor fire from the
    2026-07-25T20:45:01 RED artifact (beacon age 52.3h, correctly quiet since Friday's
    close). Does not cover market holidays (weekday-only check) -- named follow-up, not
    chased this fire to stay bounded."""
    ev: list = []
    out = {"verdict": "GREEN", "evidence": ev}
    for account, creds in creds_map.items():
        clock = fb._request(creds, "clock")
        ev.append(f"{account} /v2/clock: {json.dumps(clock)}")
        nxt = str(clock.get("next_open", "")) if isinstance(clock, dict) else ""
        if not next_day or not nxt.startswith(f"{next_day}T09:30"):
            ev.append(f"{account} FAIL: next_open={nxt!r} != {next_day} 09:30 ET")
            out["verdict"] = "RED"
        acct = fb.get_account(creds)
        lvl = acct.get("options_approved_level", acct.get("options_trading_level"))
        ev.append(f"{account} account: status={acct.get('status')} "
                  f"options_approved_level={acct.get('options_approved_level')} "
                  f"options_trading_level={acct.get('options_trading_level')}")
        if acct.get("_error") or lvl is None or int(lvl) < 2:
            ev.append(f"{account} FAIL: options approval level {lvl!r} unreadable or < 2")
            out["verdict"] = "RED"
    if BEACON.exists():
        age_h = (datetime.now().timestamp() - BEACON.stat().st_mtime) / 3600.0
        ev.append(f"sight-beacon.json age {age_h:.1f}h (must be <24h on a weekday — beacon ran today)")
        if age_h >= 24:
            if is_weekend:
                ev.append("beacon stale but rehearsal is running on a weekend — "
                           "engine correctly quiet since Friday's close (market closed -- quiet OK)")
            else:
                ev.append("FAIL: beacon stale — the engine's eye did not run today")
                out["verdict"] = "RED"
    else:
        ev.append("FAIL: sight-beacon.json MISSING")
        out["verdict"] = "RED"
    return out


# ── verdict + artifact ─────────────────────────────────────────────────────────

def compute_overall(checks: dict) -> str:
    """GREEN only when EVERY check is GREEN. Any RED -> RED. Any INCONCLUSIVE (no RED)
    -> INCONCLUSIVE. Never softens an unproven boundary into a green light."""
    verdicts = [str(c.get("verdict", "RED")) for c in checks.values()]
    if any(v == "RED" for v in verdicts):
        return "RED"
    if any(v.startswith("INCONCLUSIVE") for v in verdicts):
        return "INCONCLUSIVE"
    return "GREEN"


def _write_result(result: dict) -> None:
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(OUT)


def _ran_today_already(now: datetime) -> bool:
    """True if OUT already reflects a run from TODAY's ET calendar date. Used ONLY by
    --catchup (the backup startup trigger) so a boot-time recovery run never duplicates a
    real options+crypto round-trip that already happened tonight via the primary trigger
    (or an earlier boot). Unreadable/missing artifact -> False (safe default: do the work)."""
    if not OUT.exists():
        return False
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — fail-open toward doing the work, not skipping it
        return False
    return str(data.get("ran_at_et", ""))[:10] == now.strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="skip the idempotent already-ran-today check and always do "
                             "real work (manual re-run / debugging)")
    args = parser.parse_args(argv)
    now = et_now()
    if not args.force and _ran_today_already(now):
        print(f"[dress-rehearsal] already ran today ({now.strftime('%Y-%m-%d')}) — no-op "
              f"(pass --force to override)")
        return 0
    checks: dict = {}
    result = {"ran_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "next_trading_day": None,
              "placement_source": None, "overall": "RED", "checks": checks}
    try:
        creds_all = fb.load_creds()
        creds_map = {}
        for account, arm in ARMS.items():
            c = creds_all.get(arm)
            if not c:
                checks[f"check1_options_{account}"] = {
                    "verdict": "RED", "evidence": [f"no creds for arm {arm} in fleet secrets"]}
                continue
            creds_map[account] = c
        place_fn, occ_fn, source = _engine_placement()
        result["placement_source"] = source
        safe_creds = creds_map.get("safe")
        next_day = _next_trading_day(safe_creds, now) if safe_creds else None
        result["next_trading_day"] = next_day
        spot = _spy_spot(safe_creds) if safe_creds else None

        for account, creds in creds_map.items():
            if next_day and spot:
                checks[f"check1_options_{account}"] = check1_options_acceptance(
                    account, creds, place_fn, occ_fn, next_day, spot)
            else:
                checks[f"check1_options_{account}"] = {
                    "verdict": "RED",
                    "evidence": [f"prereq failed: next_trading_day={next_day!r} spot={spot!r}"]}
        if safe_creds:
            checks["check2_crypto_safe"] = check2_crypto_roundtrip(safe_creds)
        else:
            checks["check2_crypto_safe"] = {"verdict": "RED", "evidence": ["no safe creds"]}
        checks["check3_sanity"] = check3_sanity(
            creds_map, next_day, is_weekend=et_weekday() >= 5)
        result["overall"] = compute_overall(checks)
    except Exception as e:  # noqa: BLE001 — fail-open: a crash is a RED artifact, never a silent death
        checks["_crash"] = {"verdict": "RED", "evidence": [f"{type(e).__name__}: {e}"]}
        result["overall"] = "RED"
    _write_result(result)
    print(f"[dress-rehearsal] overall={result['overall']} next_trading_day={result['next_trading_day']}")
    for name, c in checks.items():
        print(f"  {name}: {c.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
