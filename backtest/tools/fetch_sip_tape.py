"""Fetch and cache Alpaca SIP trade/quote tape data, and sign trades (Lee-Ready).

New capability (2026-09-06): this repo has only ever fetched bars. This module
fetches raw trade-level and quote-level SIP data via Alpaca's v2 market-data
REST endpoints, paginates to completion, caches to disk (parquet — pyarrow is
already in the backtest venv), and classifies each trade as buyer- or
seller-initiated using the Lee-Ready rule.

Verified live 2026-09-06 against SPY with the project's paper-key Alpaca creds
(read via `_alpaca_creds.resolve_alpaca_creds`, itself sourced from `.mcp.json`
— never hardcode keys here). Endpoints:

    GET https://data.alpaca.markets/v2/stocks/{symbol}/trades
    GET https://data.alpaca.markets/v2/stocks/{symbol}/quotes

Both take start/end (RFC3339 UTC), limit, feed=sip, and page via
`next_page_token` until the field is absent/null.

Design notes:
  - Nanosecond timestamps from Alpaca ("t": "2026-09-04T14:30:00.123456789Z")
    are kept as int64 nanoseconds-since-epoch throughout — never round-tripped
    through float — to avoid losing sub-microsecond precision.
  - No silent truncation: if the API stops paginating (`next_page_token` goes
    missing) before we have reason to believe the window is exhausted, that's
    normal (it means "done"). What we refuse to do silently is give up after
    hitting MAX_REQUESTS_PER_CALL — that raises loudly instead of returning a
    partial result that looks complete.
  - Cache is keyed by symbol + kind (trades/quotes) + feed + exact UTC window,
    so a repeated pull of the same window costs zero API calls.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import io
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - pandas is a hard requirement here
    raise RuntimeError(
        "fetch_sip_tape requires pandas, which is expected to already be installed "
        "in the backtest venv. Do not add it ad hoc without checking blast radius."
    ) from exc

try:
    import pyarrow  # noqa: F401

    _HAVE_PYARROW = True
except ImportError:
    _HAVE_PYARROW = False

BASE_URL = "https://data.alpaca.markets/v2/stocks"
DEFAULT_FEED = "sip"
DEFAULT_LIMIT = 10000
MAX_REQUESTS_PER_CALL = 500  # hard cap: a bad/huge window fails loud, not slow-spins
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1.0

CACHE_ROOT = Path(__file__).resolve().parents[1] / "data" / "sip_tape"

TapeKind = Literal["trades", "quotes"]


class TapeFetchError(RuntimeError):
    """Raised when the tape cannot be fetched/paginated to completion."""


# --------------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------------


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_ns_timestamp(t: str) -> int:
    """Parse Alpaca's RFC3339 nanosecond timestamp string to int64 ns since epoch.

    Never goes through float. Alpaca emits e.g. "2026-09-04T14:30:00.123456789Z".
    """
    assert t.endswith("Z"), f"unexpected timestamp format (no Z): {t!r}"
    body = t[:-1]
    if "." in body:
        date_part, frac_part = body.split(".", 1)
    else:
        date_part, frac_part = body, ""
    frac_part = (frac_part + "000000000")[:9]  # pad/truncate to exactly ns precision
    dt = datetime.strptime(date_part, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    epoch_ns = int(dt.timestamp()) * 1_000_000_000
    return epoch_ns + int(frac_part)


# --------------------------------------------------------------------------------
# Cache path / key
# --------------------------------------------------------------------------------


def _cache_key(symbol: str, kind: TapeKind, feed: str, start: datetime, end: datetime) -> str:
    def stamp(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")

    return f"{symbol.upper()}_{kind}_{feed}_{stamp(start)}_{stamp(end)}"


def _cache_path(symbol: str, kind: TapeKind, feed: str, start: datetime, end: datetime) -> Path:
    ext = "parquet" if _HAVE_PYARROW else "csv.gz"
    day_dir = CACHE_ROOT / symbol.upper() / start.strftime("%Y-%m-%d")
    return day_dir / f"{_cache_key(symbol, kind, feed, start, end)}.{ext}"


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if path.suffix == ".parquet":
        df.to_parquet(tmp, index=False)
    else:
        with gzip.open(tmp, "wt", newline="") as fh:
            df.to_csv(fh, index=False)
    tmp.replace(path)  # atomic-ish swap; avoids a half-written cache file on crash


def _read_cache(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    with gzip.open(path, "rt") as fh:
        return pd.read_csv(fh)


# --------------------------------------------------------------------------------
# HTTP fetch with pagination + retry
# --------------------------------------------------------------------------------


def _request_with_retry(url: str, params: dict, headers: dict) -> dict:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            continue

        raise TapeFetchError(
            f"Alpaca request failed: {resp.status_code} {resp.text[:500]!r} "
            f"(url={url}, params={ {k: v for k, v in params.items()} })"
        )
    raise TapeFetchError(f"Alpaca request failed after {MAX_RETRIES} retries: {last_exc}")


def _fetch_raw_pages(
    symbol: str,
    kind: TapeKind,
    start: datetime,
    end: datetime,
    feed: str,
    limit: int,
    api_key: str,
    api_secret: str,
) -> list[dict]:
    """Fetch every page for [start, end), following next_page_token to completion.

    Raises TapeFetchError (never silently truncates) if MAX_REQUESTS_PER_CALL is
    hit before the API reports it's done.
    """
    url = f"{BASE_URL}/{symbol}/{kind}"
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    params = {
        "start": _to_rfc3339(start),
        "end": _to_rfc3339(end),
        "limit": limit,
        "feed": feed,
    }

    records: list[dict] = []
    page_token: str | None = None
    field = kind  # "trades" or "quotes" -> same key in response body

    for request_num in range(1, MAX_REQUESTS_PER_CALL + 1):
        page_params = dict(params)
        if page_token:
            page_params["page_token"] = page_token

        body = _request_with_retry(url, page_params, headers)
        page_records = body.get(field) or []
        records.extend(page_records)

        page_token = body.get("next_page_token")
        if not page_token:
            return records

    raise TapeFetchError(
        f"Hit MAX_REQUESTS_PER_CALL={MAX_REQUESTS_PER_CALL} for {symbol} {kind} "
        f"{start}..{end} without the API signalling completion (next_page_token "
        "still present). Refusing to return a silently-truncated tape — narrow "
        "the window or raise MAX_REQUESTS_PER_CALL deliberately."
    )


def _trades_to_frame(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(
            columns=["t_ns", "price", "size", "exchange", "conditions", "trade_id", "tape"]
        )
    return pd.DataFrame(
        {
            "t_ns": [_parse_ns_timestamp(r["t"]) for r in records],
            "price": [r["p"] for r in records],
            "size": [r["s"] for r in records],
            "exchange": [r.get("x") for r in records],
            "conditions": [",".join(r.get("c", []) or []) for r in records],
            "trade_id": [r.get("i") for r in records],
            "tape": [r.get("z") for r in records],
        }
    )


def _quotes_to_frame(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(
            columns=[
                "t_ns", "ask_px", "ask_size", "ask_exchange",
                "bid_px", "bid_size", "bid_exchange", "conditions", "tape",
            ]
        )
    return pd.DataFrame(
        {
            "t_ns": [_parse_ns_timestamp(r["t"]) for r in records],
            "ask_px": [r.get("ap") for r in records],
            "ask_size": [r.get("as") for r in records],
            "ask_exchange": [r.get("ax") for r in records],
            "bid_px": [r.get("bp") for r in records],
            "bid_size": [r.get("bs") for r in records],
            "bid_exchange": [r.get("bx") for r in records],
            "conditions": [",".join(r.get("c", []) or []) for r in records],
            "tape": [r.get("z") for r in records],
        }
    )


# --------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------


def fetch_tape(
    symbol: str,
    kind: TapeKind,
    start: datetime,
    end: datetime,
    feed: str = DEFAULT_FEED,
    limit: int = DEFAULT_LIMIT,
    use_cache: bool = True,
    creds_server: str = "alpaca",
    session: Any = None,  # unused hook, kept for test injection clarity
) -> pd.DataFrame:
    """Fetch trades or quotes for `symbol` over UTC window [start, end).

    Returns a DataFrame sorted by t_ns. Served from on-disk cache when present
    (zero API calls). Raises TapeFetchError on incomplete pagination instead of
    silently truncating.
    """
    if kind not in ("trades", "quotes"):
        raise ValueError(f"kind must be 'trades' or 'quotes', got {kind!r}")

    cache_path = _cache_path(symbol, kind, feed, start, end)
    if use_cache and cache_path.exists():
        return _read_cache(cache_path)

    creds = resolve_alpaca_creds(creds_server)
    records = _fetch_raw_pages(symbol, kind, start, end, feed, limit, creds.key, creds.secret)
    df = _trades_to_frame(records) if kind == "trades" else _quotes_to_frame(records)
    df = df.sort_values("t_ns", kind="mergesort").reset_index(drop=True)

    if use_cache:
        _write_cache(df, cache_path)

    return df


def fetch_trades(symbol: str, start: datetime, end: datetime, **kwargs) -> pd.DataFrame:
    return fetch_tape(symbol, "trades", start, end, **kwargs)


def fetch_quotes(symbol: str, start: datetime, end: datetime, **kwargs) -> pd.DataFrame:
    return fetch_tape(symbol, "quotes", start, end, **kwargs)


# --------------------------------------------------------------------------------
# Lee-Ready trade signing
# --------------------------------------------------------------------------------


def sign_trades(trades: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Classify each trade buyer- (+1) or seller-initiated (-1) via Lee-Ready.

    Rule: compare trade price to the prevailing NBBO midpoint (the most recent
    quote at or before the trade timestamp).
      - price > midpoint -> buyer-initiated (+1)
      - price < midpoint -> seller-initiated (-1)
      - price == midpoint (or no prevailing quote) -> tick rule: compare to the
        previous trade's price (uptick -> +1, downtick -> -1, no change ->
        carry forward the previous sign, or 0 for the very first trade with no
        prior reference).

    Returns a copy of `trades` with added columns: mid, sign, signed_size.
    Never mutates the input frames (repo immutability convention).
    """
    if trades.empty:
        out = trades.copy()
        out["mid"] = pd.Series(dtype="float64")
        out["sign"] = pd.Series(dtype="int64")
        out["signed_size"] = pd.Series(dtype="int64")
        return out

    trades = trades.sort_values("t_ns", kind="mergesort").reset_index(drop=True)
    quotes = quotes.sort_values("t_ns", kind="mergesort").reset_index(drop=True)

    quote_ts = quotes["t_ns"].tolist()
    quote_mid = (
        ((quotes["bid_px"] + quotes["ask_px"]) / 2.0).tolist() if not quotes.empty else []
    )

    mids: list[float | None] = []
    for t_ns in trades["t_ns"]:
        idx = bisect.bisect_right(quote_ts, t_ns) - 1
        mids.append(quote_mid[idx] if idx >= 0 else None)

    signs: list[int] = []
    prev_sign = 0
    prev_price: float | None = None
    for price, mid in zip(trades["price"], mids):
        if mid is not None and price > mid:
            sign = 1
        elif mid is not None and price < mid:
            sign = -1
        else:
            # midpoint tie or no prevailing quote -> tick rule
            if prev_price is None:
                sign = 0
            elif price > prev_price:
                sign = 1
            elif price < prev_price:
                sign = -1
            else:
                sign = prev_sign  # zero-tick: carry forward
        signs.append(sign)
        prev_sign = sign
        prev_price = price

    out = trades.copy()
    out["mid"] = mids
    out["sign"] = signs
    out["signed_size"] = out["sign"] * out["size"]
    return out


# --------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------


def _parse_cli_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch + sign Alpaca SIP tape for one window.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", required=True, help="UTC RFC3339, e.g. 2026-09-04T14:30:00Z")
    parser.add_argument("--end", required=True, help="UTC RFC3339, e.g. 2026-09-04T14:35:00Z")
    parser.add_argument("--feed", default=DEFAULT_FEED)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    start = _parse_cli_dt(args.start)
    end = _parse_cli_dt(args.end)
    use_cache = not args.no_cache

    t0 = time.monotonic()
    trades = fetch_trades(args.symbol, start, end, feed=args.feed, use_cache=use_cache)
    quotes = fetch_quotes(args.symbol, start, end, feed=args.feed, use_cache=use_cache)
    elapsed = time.monotonic() - t0

    signed = sign_trades(trades, quotes)
    buy_vol = int(signed.loc[signed["sign"] == 1, "size"].sum())
    sell_vol = int(signed.loc[signed["sign"] == -1, "size"].sum())
    unsigned_vol = int(signed.loc[signed["sign"] == 0, "size"].sum())

    trades_path = _cache_path(args.symbol, "trades", args.feed, start, end)
    quotes_path = _cache_path(args.symbol, "quotes", args.feed, start, end)
    trades_bytes = trades_path.stat().st_size if trades_path.exists() else 0
    quotes_bytes = quotes_path.stat().st_size if quotes_path.exists() else 0

    print(f"symbol={args.symbol} window={args.start}..{args.end} feed={args.feed}")
    print(f"trades={len(trades)} quotes={len(quotes)} wall_seconds={elapsed:.3f}")
    print(f"cache trades_file={trades_path} bytes={trades_bytes}")
    print(f"cache quotes_file={quotes_path} bytes={quotes_bytes}")
    print(f"signed buy_volume={buy_vol} sell_volume={sell_vol} unsigned_volume={unsigned_vol}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
