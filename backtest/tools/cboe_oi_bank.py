"""Daily SPY (+SPX) per-strike OI + NATIVE-gamma banker — the free-CBOE forward archive.

WHAT THIS IS (the N=2 banker that unblocks a GEX BACKTEST)
---------------------------------------------------------
``gex_regime.py`` computes the one peer-reviewed regime signal (dealer short-gamma ->
trend-amplifying / long-gamma -> pinning), but per ``assess_backtest_feasibility`` it can
NEITHER be backtested NOR read live without a historical full-chain OI+gamma snapshot
archive. ``automation/scripts/gex_capture.py`` is the N=1 banker (Alpaca; greeks from one
feed + OI joined from a second, with a BS-style gamma). THIS is the N=2 banker on a
*different, free, native* source: the CBOE delayed-quotes CDN, which ships per-contract
``open_interest`` AND a native ``gamma`` in ONE document — no auth, no BS inversion, no
join. Two independent sources de-risk the single-vendor archive and let us cross-check the
net-GEX sign once history accrues (~60-90 days).

DATA SOURCE (verified by the scout)
-----------------------------------
``https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json`` -> 200, ~5.9 MB,
~13.4k contracts, each ``{option, open_interest, gamma, delta, theta, vega, iv, ...}``
plus a top-level ``data.current_price`` (spot). Also ``_SPX.json`` (free) for the
broad-expiry net-GEX sign the literature prefers. Current-day snapshot ONLY (no historical
URL) -> we forward-bank one snapshot per day.

ADDITIVE / NO-CLOBBER (HARD CONSTRAINT 2)
-----------------------------------------
Writes ``journal/gex-archive/{date}-cboe.json`` — DISTINCT from the Alpaca banker's
``{date}.json``. The two archives coexist; neither overwrites the other.

ROBUST / IDEMPOTENT / FAIL-SAFE (HARD CONSTRAINT 4, OP-25)
----------------------------------------------------------
* Timeout + bounded retry on every GET.
* On HTTP failure / malformed JSON for a symbol: LOG + skip that symbol (never crash).
* If NEITHER symbol yields contracts: LOG + exit 0 (never throw into the scheduler).
* Idempotent: a re-run the same day OVERWRITES today's ``{date}-cboe.json`` cleanly
  (atomic temp-then-replace), so a scheduled retry never half-writes or double-appends.

ZERO new dependencies (stdlib ``urllib`` only) and ZERO engine imports — the CBOE doc
carries native gamma+OI, so unlike the Alpaca banker this does NOT need pandas/the engine
package and runs on ANY interpreter. Paths anchored to ``__file__`` (L21/L60). Reads no
production state; writes only the NEW dated archive. Never places orders; never edits
params/heartbeat/CLAUDE.md. $0 (free CBOE CDN). Data-banking only — no live-trading edit.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# -- repo-anchored paths (L21/L60) --------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO / "journal" / "gex-archive"  # shared dir; distinct {date}-cboe.json file

# -- CBOE free delayed-quotes CDN (no auth) -----------------------------------------------
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
# SPY is the tradable underlying; _SPX (note the leading underscore) is the cash index the
# net-GEX literature prefers for the broad-expiry sign. Both are free on this CDN.
SYMBOLS = ("SPY", "_SPX")

HTTP_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0
USER_AGENT = "gamma-cboe-oi-bank/1.0 (+research; data-banking only)"


def _get_json(url: str) -> dict:
    """GET a JSON doc with timeout + bounded retry. Raises on final transport failure.

    Handles gzip transparently (the CDN may gzip the ~6 MB doc). Retries on transient
    transport errors with linear backoff; a 4xx (client) error is NOT retried.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            })
            with urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 (trusted host)
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except HTTPError as e:
            last_exc = e
            if 400 <= e.code < 500:  # client error -> not worth retrying
                raise
        except (URLError, TimeoutError, ValueError, OSError) as e:
            last_exc = e
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise last_exc if last_exc else RuntimeError(f"GET failed with no exception: {url}")


def _is_number(x) -> bool:
    try:
        f = float(x)
        return f == f  # not NaN
    except (TypeError, ValueError):
        return False


def _parse_option_symbol(opt: str) -> tuple[str, str, float] | None:
    """Parse a CBOE/OCC option string -> (expiry_iso, right, strike).

    CBOE 'option' field is OCC-style: ROOT + YYMMDD + {C,P} + strike*1000 zero-padded to
    8 digits, e.g. ``SPY260620C00600000`` -> ('2026-06-20', 'C', 600.0). Returns ``None``
    if it does not match (caller skips the row).
    """
    s = opt.strip()
    # Walk back from the end: last C/P followed by exactly 8 digits is the strike marker.
    for i in range(len(s) - 9, -1, -1):
        ch = s[i]
        if ch in ("C", "P"):
            tail = s[i + 1:]
            if len(tail) == 8 and tail.isdigit():
                date_part = s[i - 6:i]  # 6 digits immediately before the C/P
                if len(date_part) == 6 and date_part.isdigit():
                    yy, mm, dd = date_part[:2], date_part[2:4], date_part[4:]
                    try:
                        expiry = dt.date(2000 + int(yy), int(mm), int(dd)).isoformat()
                    except ValueError:
                        expiry = None
                else:
                    expiry = None
                if expiry is not None:
                    return (expiry, ch, int(tail) / 1000.0)
    return None


def _extract_contracts(payload: dict) -> tuple[list[dict], float | None]:
    """Flatten one CBOE delayed-quotes payload into per-strike rows + spot.

    The CDN shape is ``{"data": {"current_price": <spot>, "options": [ {...}, ... ]}}``.
    Each option carries ``option`` (OCC string), ``open_interest``, ``gamma``, ``delta``,
    ``iv``, and a price (``theo`` preferred, else ``last_trade_price``/``close``). Returns
    ``(rows, spot)``. Rows with an unparseable symbol are skipped; missing numerics become
    ``None`` (faithful capture — the GEX computer does its own filtering).
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return [], None
    spot = None
    for k in ("current_price", "close", "prev_day_close"):
        if _is_number(data.get(k)):
            spot = float(data[k])
            break
    options = data.get("options")
    rows: list[dict] = []
    if not isinstance(options, list):
        return rows, spot
    for o in options:
        if not isinstance(o, dict):
            continue
        sym = o.get("option")
        if not sym:
            continue
        parsed = _parse_option_symbol(str(sym))
        if parsed is None:
            continue
        expiry, right, strike = parsed
        theo = None
        for pk in ("theo", "last_trade_price", "close", "bid"):
            if _is_number(o.get(pk)):
                theo = float(o[pk])
                break
        rows.append({
            "symbol": str(sym),
            "expiry": expiry,
            "strike": strike,
            "right": right,  # 'C' / 'P' (native CBOE convention)
            "open_interest": (float(o["open_interest"]) if _is_number(o.get("open_interest")) else None),
            "gamma": (float(o["gamma"]) if _is_number(o.get("gamma")) else None),
            "delta": (float(o["delta"]) if _is_number(o.get("delta")) else None),
            "iv": (float(o["iv"]) if _is_number(o.get("iv")) else None),
            "theo": theo,
        })
    return rows, spot


def _write_json(path: Path, obj: dict) -> None:
    """Atomic-ish JSON write (temp then replace) so a reader never sees a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def capture(now: dt.datetime | None = None) -> dict:
    """Run one CBOE capture across all SYMBOLS. Returns the doc that was written.

    Per-symbol failures are logged and skipped (best-effort). The archive lands only if at
    least one symbol yielded contracts; otherwise a status doc is returned and exit is 0.
    """
    now = now or dt.datetime.now()
    session_date = now.strftime("%Y-%m-%d")
    ts_iso = now.replace(microsecond=0).isoformat()
    archive_path = ARCHIVE_DIR / f"{session_date}-cboe.json"
    log = lambda m: print(f"[{ts_iso}] {m}")  # noqa: E731 (tiny local logger)

    per_symbol: dict[str, dict] = {}
    total_contracts = 0
    native_gamma_present = False
    spy_spot: float | None = None

    for sym in SYMBOLS:
        url = CBOE_URL.format(sym=sym)
        try:
            payload = _get_json(url)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as e:
            log(f"SKIP {sym}: fetch failed ({type(e).__name__}: {e})")
            per_symbol[sym] = {"error": f"{type(e).__name__}: {e}", "n_contracts": 0,
                               "spot": None, "contracts": []}
            continue
        try:
            rows, spot = _extract_contracts(payload)
        except Exception as e:  # noqa: BLE001 — malformed doc must not crash the banker
            log(f"SKIP {sym}: parse failed ({type(e).__name__}: {e})")
            per_symbol[sym] = {"error": f"parse: {type(e).__name__}: {e}", "n_contracts": 0,
                               "spot": None, "contracts": []}
            continue

        n_gamma = sum(1 for r in rows if r["gamma"] is not None)
        n_oi = sum(1 for r in rows if r["open_interest"] is not None)
        if n_gamma > 0:
            native_gamma_present = True
        if sym == "SPY" and _is_number(spot):
            spy_spot = float(spot)
        per_symbol[sym] = {
            "spot": spot,
            "n_contracts": len(rows),
            "n_with_gamma": n_gamma,
            "n_with_oi": n_oi,
            "contracts": rows,
        }
        total_contracts += len(rows)
        log(f"OK   {sym}: {len(rows)} contracts (gamma:{n_gamma} oi:{n_oi} spot:{spot})")

    if total_contracts == 0:
        log("FAILSAFE no contracts from any symbol (CDN down / all malformed) — exit 0, no write")
        return {"status": "not_captured", "reason": "no contracts from any symbol",
                "session_date": session_date, "captured_at": ts_iso}

    doc = {
        "source": "cboe_cdn",
        "url_template": CBOE_URL,
        "session_date": session_date,
        "captured_at": ts_iso,
        "n_contracts": total_contracts,
        "spy_spot": spy_spot,
        "has_native_gamma": native_gamma_present,
        "symbols": list(SYMBOLS),
        "by_symbol": per_symbol,
    }
    _write_json(archive_path, doc)
    log(f"BANKED {total_contracts} contracts (native_gamma={native_gamma_present}) "
        f"-> {archive_path}")
    return doc


def main() -> int:
    """Entry point. Always returns 0 except on a truly unexpected crash (OP-25)."""
    try:
        capture()
        return 0
    except Exception as e:  # noqa: BLE001 — last-resort guard; never throw into scheduler
        ts = dt.datetime.now().replace(microsecond=0).isoformat()
        print(f"[{ts}] UNEXPECTED cboe_oi_bank error: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0  # data-banking job: a crash must NOT fail the scheduler (still exit 0)


if __name__ == "__main__":
    sys.exit(main())
