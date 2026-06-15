# DATA-SOURCES.md — Provider reference

Three sources for crypto OHLCV bars; this folder uses two from script + one from MCP.

## 1. Coinbase Exchange REST (primary)

- **URL**: `https://api.exchange.coinbase.com/products/{PRODUCT}/candles`
- **Auth**: None (public market-data endpoint)
- **Geo**: US-OK (Coinbase's primary jurisdiction)
- **Symbols**: BTC-USD, ETH-USD, SOL-USD, etc. (dash-separated, base-quote)
- **Granularities (fixed set)**: 60, 300, 900, 3600, 21600, 86400 seconds
- **Bars per request**: max 300
- **Rate limit**: 10 req/s public, 15 burst
- **Row format**: `[time, low, high, open, close, volume]` (note the non-standard order — Coinbase puts low/high before open/close)
- **Time**: UNIX seconds, START of bar
- **Ordering returned**: newest-first
- **In-progress bar**: present as `rows[0]` typically; `rows[0][0] + granularity > now()` means in-progress
- **Quirks**: occasional duplicate rows on boundary fetches — `data_sources._fetch_coinbase` sorts ascending and trims to `count`

Use for: live in-the-moment validation, foot-gun reproduction, source-parity baseline.

## 2. yfinance (Yahoo Finance via `yfinance` Python package)

- **Auth**: None
- **Symbols**: `BTC-USD`, `ETH-USD` (same convention as Coinbase, helpful coincidence)
- **Granularities for crypto**: 1m / 2m / 5m / 15m / 30m / 60m / 90m / 1h / 1d / 5d / 1wk / 1mo / 3mo
- **History limits**:
  - 1m: last 7 days
  - 5m: last 60 days
  - daily: full history
- **In-progress bar**: yfinance flags it with `V=0` (volume zero) sentinel on equity intraday — for crypto the behavior is similar
- **Quirks (KNOWN, encoded in `data_sources.py`)**:
  - MultiIndex columns: `df.columns` may be `[('Open','BTC-USD'), ('Close','BTC-USD'), ...]` — must flatten
  - tz-aware UTC timestamps — convert with `tz_convert("UTC")`
  - Empty DataFrame on rate limit — handle with `if df.empty: raise`

Use for: 60-day historical backfills, cross-source parity check vs Coinbase.

## 3. Alpaca Crypto MCP (`mcp__alpaca__get_crypto_bars`)

- **Auth**: Project API key (already in `~/.claude/.mcp.json` under `alpaca` server)
- **Symbols**: `BTC/USD`, `ETH/USD` (slash-separated — different from Coinbase!)
- **Granularities**: 1Min, 5Min, 15Min, 1H, 1D
- **History**: substantial (multi-year)
- **In-progress bar**: TBD — needs validation (same primitive, run v01 against Alpaca crypto when extending harness)

Use for: third-source parity, interactive Claude validation, integration sanity with the SAME MCP server that handles SPY options trades. Cannot be called from a stand-alone Python script — must be invoked from within an interactive Claude session.

**Note on Alpaca symbol convention**: when adding Alpaca to `v02_source_parity`, the symbol mapping function must translate `BTC-USD` (Coinbase / yfinance) ↔ `BTC/USD` (Alpaca).

## Cross-source tolerance

`v02_source_parity` uses **0.05% (5 bp) tolerance** on each OHLC field. Why this number:

- Coinbase prints from its own order book; yfinance aggregates across venues
- Crypto venues at any moment trade within ~2-5 bp of each other (high-volume pairs)
- A drift > 5 bp on a CLOSED bar means one source has bad data, not market-driven spread
- The window is generous enough to avoid false alarms, tight enough to catch real bugs (a 50-bp drift would be a 4-figure dollar error on BTC at $80k)

Volume is **NOT compared** cross-source — different venues have different volume conventions (base currency vs quote currency, taker-only vs both sides).

## Picking a source for new validators

| Scenario | Source |
|---|---|
| Live in-the-moment validation | Coinbase REST |
| Long historical replay (>5 days) | yfinance |
| Multi-source parity check | Coinbase + yfinance |
| Validation from inside Claude (MCP-callable) | Alpaca crypto MCP |
| Avoiding rate-limits | yfinance (no documented limit for moderate use) |
| Reproducing TradingView chart-data foot-gun | TradingView MCP on BTCUSD (future v05) |

## Symbol catalog (verified 2026-05-16)

| Coinbase | yfinance | Alpaca | Notes |
|---|---|---|---|
| BTC-USD | BTC-USD | BTC/USD | High-vol, low-spread — primary validation target |
| ETH-USD | ETH-USD | ETH/USD | Secondary target |
| SOL-USD | SOL-USD | SOL/USD | Higher vol — useful for stress-testing pattern recognition |
| LTC-USD | LTC-USD | LTC/USD | Lower vol — useful for edge cases |
