"""broker_canary -- the BROKER CANARY: 24/7 Alpaca API health signal piggybacked on the
crypto twin (markdown/planning/TWIN-PROGRAM.md).

WHY THIS EXISTS: the crypto twin already talks to Alpaca's API 24/7 (BTC/USD bars +,
once its dedicated account is configured, account reads). SPY only opens 09:30 ET --
if Alpaca's API is degraded (slow, erroring, auth dead) overnight, the FIRST the rig
would ever find out is when the 09:30 heartbeat tries to trade. This module rides along
on calls the twin already makes (or would make one lightweight version of) so a broker
problem surfaces at the 08:25 ET pre-open gate, hours before it would otherwise be
discovered -- see preopen_readiness.py's new "broker_canary" check.

HARD RAILS (non-negotiable):
  * $0. Pure Python, stdlib + the twin's OWN broker client -- no new dependency, no paid
    API, no new vendor.
  * PIGGYBACK, NOT POLL: probe() adds exactly ONE lightweight unauthenticated crypto-bars
    request (limit=1, the smallest useful call) + ONE authenticated GET /v2/account (only
    when the twin's dedicated account is configured) per call -- it does not add a new
    polling loop of its own. Whoever wires probe() into a scheduled tick (see queue.md)
    controls the cadence; this module never schedules itself.
  * DOES NOT TOUCH crypto_twin_core.py / crypto_twin_health.py -- two other crews own
    those files this session. This module only IMPORTS crypto_twin_broker's existing,
    already-tested request functions (fetch_crypto_bars / get_twin_creds / get_account)
    -- it reuses the SAME HTTP client the twin itself uses, it does not roll its own.
  * FAIL-OPEN, ALWAYS: probe()/assess() never raise. A network/HTTP exception on either
    probe leg is recorded as an ok=False observation with the exception text, never
    propagated to the caller (a scheduled tick must never die because Alpaca is down --
    that IS the signal this module exists to capture, not a crash).

THE TWO STORES:
  * automation/state/broker-canary.jsonl -- the rolling observation ledger. ONE row per
    probe leg (kind="crypto_bars_unauth" | "account_auth"), append-only, size-capped to
    the last ROLLING_CAP (~2000) rows (old rows are trimmed off the FRONT, rewritten in
    one shot, when the cap is exceeded -- see _enforce_rolling_cap).
  * automation/state/broker-canary.json -- the glanceable: assess()'s verdict snapshot,
    written every time assess() runs. This is the ONLY file preopen_readiness.py reads
    (it never reads the raw jsonl) -- see assess_broker_canary()/fetch_broker_canary().

VERDICT RULES (assess(), from the rolling jsonl, all windows relative to `now_et`):
  YELLOW when EITHER:
    - p50 latency over the last 1h > 2x the trailing-24h baseline median (the (1h, 24h]
      window -- a genuinely PRIOR period, not the same window compared to itself), OR
    - any auth (account_auth) observation failed within the last 1h.
  RED when EITHER (RED overrides YELLOW):
    - the most recent >=3 observations (any kind, chronological) are ALL failures, OR
    - auth has been dead (no successful account_auth observation) for > 15 minutes,
      given at least one account_auth attempt has ever been made.
  Insufficient history (e.g. no 24h-old baseline yet, or no auth observations at all
  because the twin account isn't configured) never manufactures a RED/YELLOW out of
  absent data -- each rule simply does not fire when its inputs are missing.

Every timestamp is ET via et_clock.et_now() (naive, matching the rest of this repo's ET
convention -- see et_clock.py's own module docstring on why naive-ET is deliberate here),
paired with a UTC ISO string for cross-referencing. Never Bash TZ / never a bare
datetime.now().
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

import crypto_twin_broker as ctb  # noqa: E402  -- REUSE: the twin's own tested HTTP client

STATE = REPO / "automation" / "state"
ROLLING_PATH = STATE / "broker-canary.jsonl"
CANARY_JSON_PATH = STATE / "broker-canary.json"

ROLLING_CAP = 2000  # size-capped rolling log; rewritten (trimmed) when exceeded

KIND_BARS = "crypto_bars_unauth"
KIND_AUTH = "account_auth"
PROBE_KINDS = (KIND_BARS, KIND_AUTH)
PROBE_BAR_LIMIT = 1  # smallest useful request -- this is a latency/reachability probe, not a data fetch

# --- verdict-rule constants (see module docstring "VERDICT RULES") ---
RECENT_WINDOW_MINUTES = 60.0          # "last 1h" for error_rate_1h / auth-failure-in-1h / current p50
BASELINE_WINDOW_MINUTES = 24 * 60.0   # trailing-24h baseline window, (RECENT, BASELINE] minutes-ago
YELLOW_LATENCY_MULTIPLIER = 2.0
RED_CONSECUTIVE_FAILURES = 3
RED_AUTH_DEAD_MINUTES = 15.0

_MAX_DETAIL_LEN = 300  # defensive cap so one giant exception string can't bloat the rolling log


# ----------------------------- section 1: canary collection -----------------------------

def record_observation(kind: str, latency_ms: float, ok: bool, detail: str, *,
                       now_et: Optional[datetime] = None, now_utc: Optional[datetime] = None,
                       path: Path = ROLLING_PATH, cap: int = ROLLING_CAP) -> dict:
    """Append ONE observation row to the rolling jsonl, then enforce the size cap.

    `now_et`/`now_utc`/`path`/`cap` are injectable (mirror crypto_twin_core's own
    now_utc/raw_bars injectable-clock convention) so tests never touch the real state
    file or the real clock. Production callers pass none of them.
    """
    now_et = now_et or et_now()
    now_utc = now_utc or datetime.now(timezone.utc)
    row = {
        "ts_et": now_et.isoformat(),
        "ts_utc": now_utc.isoformat(),
        "kind": kind,
        "latency_ms": round(float(latency_ms), 1),
        "ok": bool(ok),
        "detail": str(detail)[:_MAX_DETAIL_LEN],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    _enforce_rolling_cap(path, cap)
    return row


def _enforce_rolling_cap(path: Path, cap: int) -> None:
    """Keep only the last `cap` rows. Rewrites the WHOLE file in one shot only when the
    cap is exceeded (not on every call) -- cheap at this file's size (a few hundred KB at
    cap), and simple/correct beats a fancier incremental trim for a $0 local ledger."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= cap:
        return
    trimmed = lines[-cap:]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")


def _read_rolling(path: Path = ROLLING_PATH) -> list[dict]:
    """Fail-open reader: missing file -> []; a malformed individual line is skipped, never
    aborts the whole read (mirrors crypto_twin_health._read_jsonl's exact tolerance)."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def probe(*, now_et: Optional[datetime] = None, now_utc: Optional[datetime] = None,
          rolling_path: Path = ROLLING_PATH, canary_json_path: Path = CANARY_JSON_PATH,
          cap: int = ROLLING_CAP) -> dict:
    """ONE canary probe cycle -- THE one-line hookup (see queue.md): whoever wires this
    into a scheduled tick needs nothing else. PIGGYBACKS on crypto_twin_broker's own
    functions (adds zero new HTTP client code):

      leg 1 -- UNAUTHENTICATED crypto bars (forces creds={} so _data_headers sends no
               auth header -- the public data tier, confirmed live-reachable even fully
               unauthenticated per crypto_twin_broker's own docstring). Always attempted.
      leg 2 -- ONE authenticated GET /v2/account, ONLY when the twin's dedicated account
               is configured. Uses get_twin_creds(verify_crypto_status=False) -- a pure
               local file read, no network -- specifically to avoid get_twin_creds's OWN
               default crypto-status verification making a SECOND implicit account call
               (that would be two auth calls for one probe leg, violating the "one
               lightweight probe" hard rail).

    Both legs are timed + recorded via record_observation() (append + rolling-cap), THEN
    assess() runs so automation/state/broker-canary.json refreshes on every fire. Never
    raises (fail-open) -- an exception on either leg is recorded as an ok=False
    observation with the exception text, not propagated.
    """
    now_et = now_et or et_now()
    now_utc = now_utc or datetime.now(timezone.utc)

    # --- leg 1: unauthenticated crypto bars ---
    t0 = time.monotonic()
    try:
        bars = ctb.fetch_crypto_bars(ctb.CRYPTO_SYMBOL_DEFAULT, granularity_seconds=300,
                                     limit=PROBE_BAR_LIMIT, creds={})
        latency_ms = (time.monotonic() - t0) * 1000.0
        ok = bool(bars)
        detail = f"{len(bars)} bar(s), last close={bars[-1].get('c')}" if bars else "0 bars returned"
    except Exception as e:  # noqa: BLE001 -- fail-open: a probe must never raise into its caller
        latency_ms = (time.monotonic() - t0) * 1000.0
        ok, detail = False, f"{type(e).__name__}: {e}"
    bars_row = record_observation(KIND_BARS, latency_ms, ok, detail, now_et=now_et, now_utc=now_utc,
                                  path=rolling_path, cap=cap)

    # --- leg 2: authenticated account read (only if a twin account is configured) ---
    try:
        creds = ctb.get_twin_creds(verify_crypto_status=False)
    except Exception:  # noqa: BLE001 -- FileNotFoundError/KeyError = not configured yet (expected, not a failure)
        creds = None

    auth_row: Optional[dict] = None
    if creds is not None:
        t1 = time.monotonic()
        try:
            acct = ctb.get_account(creds)
            latency_ms = (time.monotonic() - t1) * 1000.0
            err = acct.get("_error") if isinstance(acct, dict) else "malformed account response"
            ok = not bool(err)
            detail = f"status={acct.get('status')}" if ok else f"error={err}"
        except Exception as e:  # noqa: BLE001
            latency_ms = (time.monotonic() - t1) * 1000.0
            ok, detail = False, f"{type(e).__name__}: {e}"
        auth_row = record_observation(KIND_AUTH, latency_ms, ok, detail, now_et=now_et, now_utc=now_utc,
                                      path=rolling_path, cap=cap)

    assessment = assess(now_et=now_et, out_path=canary_json_path, source_path=rolling_path)
    return {"bars": bars_row, "account": auth_row, "assess": assessment}


# ----------------------------- section 2: health assessment ------------------------------

def _parse_rows(rows: list[dict]) -> list[dict]:
    """Attach a parsed `dt` (naive ET datetime, from ts_et) to each row; rows with a
    missing/unparsable ts_et are dropped (never crash the assessor on one bad row).
    Returned list is sorted oldest-first."""
    out: list[dict] = []
    for r in rows:
        ts = r.get("ts_et")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts))
        except ValueError:
            continue
        out.append({**r, "dt": dt})
    out.sort(key=lambda r: r["dt"])
    return out


def _minutes_ago(now: datetime, then: datetime) -> float:
    return (now - then).total_seconds() / 60.0


def _fail_fraction(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    fails = sum(1 for r in rows if r.get("ok") is False)
    return fails / len(rows)


def _median(values: list[float]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return float(statistics.median(vals))


def _auth_dead_minutes(auth_rows: list[dict], now: datetime) -> Optional[float]:
    """Minutes since the last successful account_auth observation, IF the most recent
    one is currently failing. None when there are no auth observations at all (twin
    account not configured -- not a failure, never manufactures a RED out of absence)
    or the most recent one is ok (auth currently healthy)."""
    if not auth_rows:
        return None
    if auth_rows[-1].get("ok"):
        return None
    oks = [r for r in auth_rows if r.get("ok")]
    dead_since = oks[-1]["dt"] if oks else auth_rows[0]["dt"]
    return _minutes_ago(now, dead_since)


def assess(rows: Optional[list[dict]] = None, *, now_et: Optional[datetime] = None,
          write: bool = True, out_path: Path = CANARY_JSON_PATH,
          source_path: Path = ROLLING_PATH) -> dict:
    """Compute {verdict, p50_latency_ms, error_rate_1h, auth_ok, last_ok_et, detail,
    assessed_at_et, n_observations} from the rolling jsonl and (by default) write it to
    automation/state/broker-canary.json -- the ONLY file preopen_readiness.py reads.

    `rows` is injectable (fixture observations for pure unit tests, bypassing the real
    file); when None (production default) it reads from `source_path` via _read_rolling.
    `now_et` is injectable for deterministic tests; defaults to the real et_now(). See
    the module docstring "VERDICT RULES" for the exact GREEN/YELLOW/RED logic.
    """
    now = now_et or et_now()
    if rows is None:
        rows = _read_rolling(source_path)
    parsed = _parse_rows(rows)

    recent = [r for r in parsed if _minutes_ago(now, r["dt"]) <= RECENT_WINDOW_MINUTES]
    baseline = [r for r in parsed
               if RECENT_WINDOW_MINUTES < _minutes_ago(now, r["dt"]) <= BASELINE_WINDOW_MINUTES]
    auth_rows = [r for r in parsed if r.get("kind") == KIND_AUTH]

    error_rate_1h = _fail_fraction(recent)
    p50_latency_ms = _median([r["latency_ms"] for r in recent if "latency_ms" in r])
    if p50_latency_ms is None:
        p50_latency_ms = float(parsed[-1]["latency_ms"]) if parsed and "latency_ms" in parsed[-1] else 0.0
    baseline_median = _median([r["latency_ms"] for r in baseline if "latency_ms" in r])

    auth_ok: Optional[bool] = bool(auth_rows[-1].get("ok")) if auth_rows else None
    ok_rows = [r for r in parsed if r.get("ok")]
    last_ok_et = ok_rows[-1]["ts_et"] if ok_rows else None

    consecutive_fail = 0
    for r in reversed(parsed):
        if r.get("ok") is False:
            consecutive_fail += 1
        else:
            break

    auth_dead_minutes = _auth_dead_minutes(auth_rows, now)

    reasons: list[str] = []
    verdict = "GREEN"

    # --- YELLOW rules ---
    if baseline_median is not None and baseline_median > 0 and p50_latency_ms > YELLOW_LATENCY_MULTIPLIER * baseline_median:
        verdict = "YELLOW"
        reasons.append(f"p50 {p50_latency_ms:.0f}ms > {YELLOW_LATENCY_MULTIPLIER:g}x trailing-24h "
                       f"median {baseline_median:.0f}ms")
    auth_fail_1h = any(r.get("ok") is False for r in recent if r.get("kind") == KIND_AUTH)
    if auth_fail_1h:
        verdict = "YELLOW"
        reasons.append("auth failure within last hour")

    # --- RED rules (override YELLOW) ---
    if consecutive_fail >= RED_CONSECUTIVE_FAILURES:
        verdict = "RED"
        reasons.append(f"{consecutive_fail} consecutive probe failures")
    if auth_dead_minutes is not None and auth_dead_minutes > RED_AUTH_DEAD_MINUTES:
        verdict = "RED"
        reasons.append(f"auth dead {auth_dead_minutes:.0f}m (> {RED_AUTH_DEAD_MINUTES:g}m)")

    detail = "; ".join(reasons) if reasons else ("nominal" if parsed else "no observations recorded yet")

    result = {
        "verdict": verdict,
        "p50_latency_ms": round(p50_latency_ms, 1),
        "error_rate_1h": round(error_rate_1h, 4),
        "auth_ok": auth_ok,
        "last_ok_et": last_ok_et,
        "detail": detail,
        "assessed_at_et": now.isoformat(),
        "n_observations": len(parsed),
    }
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


# ----------------------------- CLI ------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Broker canary -- lightweight Alpaca health probe piggybacked on the crypto twin's own calls")
    parser.add_argument("--assess-only", action="store_true",
                        help="re-run assess() against the existing rolling log WITHOUT a new network probe")
    args = parser.parse_args(argv)

    result = {"assess": assess()} if args.assess_only else probe()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
