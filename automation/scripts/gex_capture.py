"""Daily dealer-GEX (gamma exposure) capture + regime-tag job.

WHAT THIS IS (the forward-looking unblock for the one peer-reviewed regime signal)
---------------------------------------------------------------------------------
The dealer-gamma regime (short-gamma -> trend-amplifying / long-gamma -> pinning) is
the one peer-reviewed regime signal the weekend research validated, and
``backtest/lib/engine/gex_regime.py`` already computes it. But we have NO historical
full-chain open-interest+gamma snapshots, so it could neither be backtested NOR read
live. This once-per-day job fixes BOTH:

  1. **Snapshots the raw SPY chain** (strike, right, gamma, OI, spot, timestamp) to a
     dated archive ``journal/gex-archive/{YYYY-MM-DD}.json`` — the backtestable history
     that accrues going forward (the key unblock; see
     ``gex_regime.assess_backtest_feasibility``: a GEX backtest becomes possible once a
     few months of these accumulate).
  2. **Computes the live regime tag** via ``gex_regime.from_alpaca_snapshot`` +
     ``compute_gex_regime`` (REUSED — the GEX math is NOT reimplemented here) and writes
     it to ``automation/state/gex-regime.json`` for premarket/heartbeat to read going
     forward. (Wiring the tag INTO premarket/heartbeat is a separate proposal — this job
     only WRITES the state file; per Rule 9 nothing is auto-enabled.)

DATA SOURCE
-----------
Alpaca options snapshots REST endpoint (the same wire shape ``from_alpaca_snapshot``
adapts): ``GET data.alpaca.markets/v1beta1/options/snapshots/SPY``. Each contract entry
carries ``greeks.gamma`` + ``openInterest`` + an OCC symbol (strike/right parsed from
it). We use stdlib ``urllib`` with the project's paper data key (the exact pattern in
``backtest/tools/fetch_option_data.py`` / ``extend_data.py``) so this script has ZERO
new dependencies and runs even from the system interpreter — though the scheduled task
uses the backtest venv because importing ``gex_regime`` pulls in the engine package.

FAIL-SAFE / IDEMPOTENT (Rule 9 propose-only, OP-25 fail-loud-never-silent)
--------------------------------------------------------------------------
* Idempotent: if today's archive snapshot already exists, logs SKIP_EXISTS and exits 0
  without re-pulling (cheap re-runs; a scheduled retry never double-writes).
* Fail-safe: if the chain is unavailable (market closed / holiday / rate-limit / empty
  greeks) it NEVER crashes — it writes a ``status: "not_computed"`` regime tag (with the
  reason) so a downstream reader always finds a well-formed file, and exits 0. The raw
  archive is only written when a non-empty chain was actually pulled.

Paths anchored to ``__file__`` (L21/L60 convention). Reads nothing from production
state; writes only NEW files (the dated archive + the regime tag). Never places orders,
never edits params/heartbeat/CLAUDE.md.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ── repo-anchored paths (L21/L60) ─────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
# Make the engine package importable so we can REUSE gex_regime (don't reimplement).
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ARCHIVE_DIR = REPO / "journal" / "gex-archive"          # backtestable history (accrues)
REGIME_TAG = REPO / "automation" / "state" / "gex-regime.json"  # live tag for readers

# ── Alpaca data API (same key/host the repo's other fetchers use) ──────────────
ALPACA_KEY = "PK33J2RV4PNIY6TCOLUG3WYGRX"
ALPACA_SECRET = "FxbJshSbhJ8Rn7KPENssS4eWsLpxCyYeyxavxywV9Bbs"
OPTIONS_SNAPSHOT_URL = "https://data.alpaca.markets/v1beta1/options/snapshots/SPY"
STOCK_SNAPSHOT_URL = "https://data.alpaca.markets/v2/stocks/SPY/snapshot"
# Open interest is NOT on the snapshot (market-data) feed — it lives on the trading API
# contracts catalog as a daily end-of-day figure. We enrich the snapshot greeks with OI
# from here, joined by OCC symbol. (Empirically verified 2026-06-19: the snapshot feed
# returns greeks+IV but open_interest is always null; this endpoint carries it.)
OPTIONS_CONTRACTS_URL = "https://paper-api.alpaca.markets/v2/options/contracts"

UNDERLYING = "SPY"
HTTP_TIMEOUT = 30
# How far out to pull the OI catalog (days). The liquid SPY chain that drives dealer GEX
# is the front ~6 weeks; pulling further just adds illiquid wings with tiny gamma.
OI_HORIZON_DAYS = 45


# ── tiny HTTP helper (stdlib only, mirrors fetch_option_data.py) ───────────────
def _get_json(url: str) -> dict:
    """GET a JSON document with the Alpaca auth headers. Raises on transport error."""
    req = Request(url, headers={
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "accept": "application/json",
    })
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 (trusted host)
        return json.loads(resp.read().decode("utf-8"))


def fetch_option_snapshots() -> dict:
    """Pull the full SPY option-chain snapshot (greeks) and enrich it with open interest.

    Returns the Alpaca payload shape ``{"snapshots": {OCC_SYMBOL: {...}, ...}}`` — the
    exact shape ``gex_regime.from_alpaca_snapshot`` expects. The market-data snapshot
    feed (``feed=indicative``) carries greeks + IV but NOT open interest, so we fetch OI
    separately from the trading-API contracts catalog and merge it onto each contract by
    OCC symbol (``snap["open_interest"]``). Both numbers are required for GEX; on a normal
    trading day both are present, so this yields a usable chain. Pages are merged so the
    whole chain (all expiries) is captured.
    """
    merged: dict[str, dict] = {}
    page_token = None
    pages = 0
    while True:
        params = {"feed": "indicative", "limit": 1000}
        if page_token:
            params["page_token"] = page_token
        payload = _get_json(f"{OPTIONS_SNAPSHOT_URL}?{urlencode(params)}")
        snaps = payload.get("snapshots") or {}
        if isinstance(snaps, dict):
            merged.update(snaps)
        pages += 1
        page_token = payload.get("next_page_token")
        if not page_token or pages >= 50:  # hard page cap (safety: full SPY chain << 50k)
            break

    # Enrich with OI by symbol (best-effort — if the catalog is empty/null today, the
    # snapshot still carries greeks and the regime computer fails safe downstream).
    oi_by_symbol = fetch_open_interest()
    for sym, oi in oi_by_symbol.items():
        if sym in merged and isinstance(merged[sym], dict):
            merged[sym]["open_interest"] = oi
    return {"snapshots": merged}


def fetch_open_interest() -> dict[str, float]:
    """Map OCC symbol -> open interest from the trading-API contracts catalog.

    OI is a daily end-of-day figure not carried on the market-data snapshot feed. We page
    the SPY contracts catalog from today out to ``OI_HORIZON_DAYS`` (the liquid chain that
    drives dealer GEX) and collect every non-null ``open_interest``. Returns ``{}`` on any
    error or when OI hasn't settled (e.g. before the session / on a holiday) — the caller
    treats a missing OI as "not usable" and fails safe, never crashes.
    """
    today = dt.date.today()
    lo = today.isoformat()
    hi = (today + dt.timedelta(days=OI_HORIZON_DAYS)).isoformat()
    out: dict[str, float] = {}
    page_token = None
    pages = 0
    while True:
        params = {
            "underlying_symbols": UNDERLYING,
            "expiration_date_gte": lo,
            "expiration_date_lte": hi,
            "limit": 10000,
        }
        if page_token:
            params["page_token"] = page_token
        try:
            payload = _get_json(f"{OPTIONS_CONTRACTS_URL}?{urlencode(params)}")
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            break  # OI enrichment is best-effort; greeks snapshot already captured
        contracts = payload.get("option_contracts") or []
        for c in contracts:
            if not isinstance(c, dict):
                continue
            sym = c.get("symbol")
            oi = c.get("open_interest")
            if sym and oi is not None and _is_number(oi):
                out[str(sym)] = float(oi)
        pages += 1
        page_token = payload.get("next_page_token") or payload.get("page_token")
        if not page_token or pages >= 50:
            break
    return out


def fetch_spot() -> float | None:
    """Best-effort SPY spot from the stock snapshot (latest trade -> daily close)."""
    try:
        snap = _get_json(STOCK_SNAPSHOT_URL)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None
    for key in ("latestTrade", "minuteBar", "dailyBar", "prevDailyBar"):
        node = snap.get(key) if isinstance(snap, dict) else None
        if isinstance(node, dict):
            price = node.get("p", node.get("c"))
            try:
                p = float(price)
                if p > 0:
                    return p
            except (TypeError, ValueError):
                continue
    return None


def _raw_rows(snapshots: dict) -> list[dict]:
    """Flatten the Alpaca snapshot into the backtestable per-contract row schema.

    One row per contract: ``{symbol, strike, right, gamma, open_interest}``. Strike/right
    are parsed from the OCC symbol via the engine's own parser so the archive matches the
    convention ``from_alpaca_snapshot`` will read back. Rows missing gamma OR OI are still
    archived (with nulls) so the raw snapshot is a faithful capture — the regime computer
    does its own filtering.
    """
    from lib.engine.gex_regime import _parse_occ_symbol  # reuse the canonical parser

    rows: dict = snapshots.get("snapshots", snapshots)
    out: list[dict] = []
    if not isinstance(rows, dict):
        return out
    for sym, snap in rows.items():
        if not isinstance(snap, dict):
            continue
        greeks = snap.get("greeks") or snap.get("latestGreeks") or {}
        gamma = greeks.get("gamma") if isinstance(greeks, dict) else None
        oi = snap.get("open_interest", snap.get("openInterest"))
        strike = snap.get("strike_price", snap.get("strike"))
        right = snap.get("type") or snap.get("option_type")
        if strike is None or right is None:
            parsed = _parse_occ_symbol(str(sym))
            if parsed is not None:
                right, strike = parsed
        out.append({
            "symbol": str(sym),
            "strike": (float(strike) if strike is not None else None),
            "right": (str(right) if right is not None else None),
            "gamma": (float(gamma) if _is_number(gamma) else None),
            "open_interest": (float(oi) if _is_number(oi) else None),
        })
    return out


def _is_number(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _write_json(path: Path, obj: dict) -> None:
    """Atomic-ish JSON write (write temp, replace) so a reader never sees a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _not_computed_tag(session_date: str, ts_iso: str, reason: str) -> dict:
    """A well-formed regime tag for the fail-safe path (chain unavailable)."""
    return {
        "status": "not_computed",
        "reason": reason,
        "underlying": UNDERLYING,
        "session_date": session_date,
        "captured_at": ts_iso,
        "regime": None,
        "net_gex_sign": None,
        "zero_gamma_flip": None,
        "call_wall": None,
        "put_wall": None,
        "spot": None,
        "n_contracts": 0,
        "source": "alpaca:v1beta1/options/snapshots/SPY",
    }


def capture(now: dt.datetime | None = None) -> dict:
    """Run one capture. Returns the regime-tag dict that was written (for tests/logging).

    Steps: (1) idempotency check on the dated archive; (2) pull chain; (3) write raw
    archive; (4) compute regime via the REUSED gex_regime; (5) write the regime tag.
    Any failure to obtain a usable chain writes a ``not_computed`` tag and returns it.
    """
    now = now or dt.datetime.now()
    session_date = now.strftime("%Y-%m-%d")
    ts_iso = now.replace(microsecond=0).isoformat()
    archive_path = ARCHIVE_DIR / f"{session_date}.json"
    log = lambda m: print(f"[{ts_iso}] {m}")  # noqa: E731 (tiny local logger)

    # (1) Idempotent: today's raw snapshot already captured -> nothing to do.
    if archive_path.exists():
        log(f"SKIP_EXISTS raw GEX archive for {session_date} already at {archive_path}")
        # Still surface what the existing tag says (don't recompute / don't overwrite).
        if REGIME_TAG.exists():
            try:
                return json.loads(REGIME_TAG.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 (best-effort echo only)
                pass
        return {"status": "skip_exists", "session_date": session_date}

    # (2) Pull the chain (fail-safe — any transport error -> not_computed tag).
    try:
        snapshot = fetch_option_snapshots()
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as e:
        reason = f"chain fetch failed: {type(e).__name__}: {e}"
        log(f"FAILSAFE {reason}")
        tag = _not_computed_tag(session_date, ts_iso, reason)
        _write_json(REGIME_TAG, tag)
        log(f"WROTE not_computed tag -> {REGIME_TAG}")
        return tag

    rows = _raw_rows(snapshot)
    n_rows = len(rows)
    if n_rows == 0:
        reason = "chain returned 0 contracts (market closed / no data on this feed)"
        log(f"FAILSAFE {reason}")
        tag = _not_computed_tag(session_date, ts_iso, reason)
        _write_json(REGIME_TAG, tag)
        log(f"WROTE not_computed tag -> {REGIME_TAG}")
        return tag

    # (3) Persist the RAW chain — the backtestable history that accrues going forward.
    spot = fetch_spot()
    raw_doc = {
        "underlying": UNDERLYING,
        "session_date": session_date,
        "captured_at": ts_iso,
        "spot": spot,
        "source": "alpaca:v1beta1/options/snapshots/SPY",
        "n_contracts": n_rows,
        "contracts": rows,
    }
    _write_json(archive_path, raw_doc)
    log(f"ARCHIVED raw chain ({n_rows} contracts) -> {archive_path}")

    # (4) Compute the regime — REUSE gex_regime (no reimplementation of the GEX math).
    from lib.engine.gex_regime import compute_gex_regime, from_alpaca_snapshot

    contracts = from_alpaca_snapshot(snapshot)
    if spot is None:
        # Fall back to the median strike of usable contracts so we can still tag.
        strikes = sorted(c.strike for c in contracts) if contracts else []
        spot = strikes[len(strikes) // 2] if strikes else None

    if not contracts or spot is None or spot <= 0:
        reason = (f"usable_contracts={len(contracts)} spot={spot} — cannot compute regime "
                  "(greeks/OI absent on this feed or spot unavailable)")
        log(f"FAILSAFE {reason}")
        tag = _not_computed_tag(session_date, ts_iso, reason)
        tag["raw_archive"] = str(archive_path)  # the raw snapshot DID land
        _write_json(REGIME_TAG, tag)
        log(f"WROTE not_computed tag (raw archive kept) -> {REGIME_TAG}")
        return tag

    try:
        regime = compute_gex_regime(contracts, float(spot))
    except ValueError as e:
        reason = f"compute_gex_regime rejected the chain: {e}"
        log(f"FAILSAFE {reason}")
        tag = _not_computed_tag(session_date, ts_iso, reason)
        tag["raw_archive"] = str(archive_path)
        _write_json(REGIME_TAG, tag)
        log(f"WROTE not_computed tag (raw archive kept) -> {REGIME_TAG}")
        return tag

    # (5) Write the live regime TAG (going-forward; readers consult this file).
    tag = {
        "status": "ok",
        "underlying": UNDERLYING,
        "session_date": session_date,
        "captured_at": ts_iso,
        "source": "alpaca:v1beta1/options/snapshots/SPY",
        "raw_archive": str(archive_path),
        "usable_contracts": regime.n_contracts,
        **regime.to_dict(),
    }
    _write_json(REGIME_TAG, tag)
    log(f"WROTE regime tag: {regime.regime} "
        f"(net_gex_sign={regime.net_gex_sign}, flip={regime.zero_gamma_flip}, "
        f"spot={regime.spot}) -> {REGIME_TAG}")
    return tag


def main() -> int:
    """Entry point. Always returns 0 except on a truly unexpected crash (OP-25: a tag is
    always written on the expected failure paths so a reader never finds nothing)."""
    try:
        capture()
        return 0
    except Exception as e:  # noqa: BLE001 — last-resort guard; still leave a breadcrumb
        ts = dt.datetime.now().replace(microsecond=0).isoformat()
        print(f"[{ts}] UNEXPECTED gex_capture error: {type(e).__name__}: {e}",
              file=sys.stderr)
        try:
            session_date = dt.date.today().isoformat()
            _write_json(REGIME_TAG, _not_computed_tag(
                session_date, ts, f"unexpected error: {type(e).__name__}: {e}"))
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
