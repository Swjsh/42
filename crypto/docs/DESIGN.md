# DESIGN.md — Crypto Validation Harness

## The problem

The Project Gamma SPY 0DTE engine reads OHLCV bars and indicators via the TradingView MCP during the 09:30–15:55 ET window. **The market is closed 17.5 hours per weekday and all weekend.** When a bug appears in our bar-reading or pattern-recognition primitives, the feedback loop to validate a fix is **24+ hours**.

The 2026-05-14 incident (root-cause: `data_get_ohlcv` returning the live in-progress bar at index `[-1]` without `bar_close_et + 5min ≤ now` filtering — see `docs/R4-HEARTBEAT-MISALIGNMENT-2026-05-14.md` and CLAUDE.md OP 25 / L34) is the canonical example: a primitive bug shipped to production, 5/46 ticks misaligned-critical on a $913 winner with the wrong structural premise. We caught it post-hoc. We could have caught it pre-flight if we had a 24/7 validation surface.

## The insight

OHLCV bars on BTC-USD 5m are **structurally identical** to OHLCV bars on SPY 5m:

- Same time-series shape: `[open_time, open, high, low, close, volume]`
- Same in-progress-vs-closed dichotomy
- Same wire-format quirks (newest-first vs oldest-first depending on source)
- Same staleness modes
- Same indicator math (RSI, EMA, MACD, BB, ATR, VWAP — all are timeframe + asset agnostic)
- Same candlestick pattern definitions
- Same trendline and level-detection geometry

**Crypto markets never close.** Therefore: every primitive in our chart-reading stack that breaks on crypto would break on SPY. We can validate the entire bar-reading + indicator + pattern stack **right now**, 24/7, against live multi-source data, without waiting for 09:30 ET.

## The scope discipline

This folder is **NOT**:

- A crypto trading bot (different broker risk model, different liquidity, different regs — a separate folder if ever needed)
- A crypto-specific strategy (out of scope)
- A live-orders surface (zero risk to production SPY trading)
- A replacement for the SPY heartbeat (parallel canary, not a substitute)

This folder **IS**:

- A pure-Python validation harness for the engine's chart-reading primitives
- A regression test bed (the OP 25 / L34 foot-gun becomes a permanent test case)
- A multi-source parity check (Coinbase / yfinance / Alpaca crypto MCP)
- A pre-flight check that runs in seconds, not 24 hours

## What translates (high-confidence reuse)

| SPY engine primitive | Crypto-validatable? | Notes |
|---|---|---|
| Closed-bar filter (`data_get_ohlcv` in heartbeat.md v15.1) | YES | Identical pathology, fix is portable |
| RSI / EMA / MACD / BB / ATR / VWAP math | YES | Identical implementations |
| Candlestick pattern recognition | YES | Pattern definitions are universal |
| Trendline / level-detection geometry | YES | Pure price-geometry, asset-agnostic |
| Volume-confirmation thresholds (ratio of current to 20-bar avg) | YES (ratios) | Absolute volumes differ, ratios port |
| Multi-source data parity (catch silent provider bugs) | YES | Three providers serve crypto + SPY |

## What does NOT translate (SPY-only, stay out of `crypto/`)

| SPY-only primitive | Why crypto can't validate |
|---|---|
| Options Greeks, theta decay, IV skew | Crypto options markets are different (Deribit etc.), and our 0DTE focus is unique to SPY |
| Opening range dynamics | Different open times, different session structure |
| VIX-based regime gating | VIX measures SPX vol; crypto has DVOL but it's a different regime construct |
| Macro calendar reactions (FOMC, CPI, NFP, earnings) | Crypto reacts but with different lag/magnitude — not portable |
| PDT rules, daily P&L kill switches | Session-bound concepts; crypto sessions are arbitrary |
| The dual-account orchestration (Gamma-Safe / Gamma-Bold) | Specific to SPY rule layer |

## Architecture

```
crypto/
├── lib/         ← pure primitives (no I/O in core math)
│   ├── bar.py             — immutable Bar / BarSeries dataclasses
│   ├── data_sources.py    — fetch from Coinbase REST + yfinance (Alpaca crypto via MCP, separate)
│   ├── bar_reader.py      — closed-bar filter (port of heartbeat v15.1 fix)
│   ├── indicators.py      — RSI/EMA/ATR/VWAP (TradingView Pine v5 conventions)
│   └── candlesticks.py    — pattern recognition (awareness layer per rule 6)
├── validators/  ← scripts that exercise primitives, output JSON scorecards
│   ├── v01_closed_bar.py        — offline + live, 7+1 tests
│   ├── v02_source_parity.py     — cross-provider agreement
│   ├── v03_indicators.py        — math validation, offline + live sanity
│   ├── v04_candlesticks.py      — pattern recognition, offline + live informational
│   └── runner.py                — runs all, writes latest.json + history.jsonl
├── data/
│   └── scorecards/              — JSON output of every validator run
└── docs/
    ├── DESIGN.md                — this file
    ├── PARITY-PROTOCOL.md       — operational handbook
    └── DATA-SOURCES.md          — provider reference
```

**Design principles** (enforced in `crypto/CLAUDE.md`):

1. **No I/O in `lib/`'s math** — `bar.py`, `bar_reader.py`, `indicators.py`, `candlesticks.py` are pure functions over dataclasses. Easy to unit-test, easy to reason about.
2. **All times tz-aware UTC** internally. Display converts to ET only at the edges.
3. **Multi-source by default**. v02 enforces provider parity — no silent reliance on one source.
4. **Scorecards are machine-readable**. Every validator writes JSON. Eventually wires into the EOD pipeline (OP 7 daily backtest ritual) as a regression check.
5. **Validators are deterministic offline + opportunistic live**. Offline tests must always pass. Live tests gate on integration correctness against current market state.

## Cost model

- **Build cost** (this conversation): one-shot.
- **Per-validation-run cost**: $0 (pure Python, no LLM).
- **Recurring cost**: $0 by default. If we add scheduled runs to catch live-integration drift, budget cap: $5/mo.
- **No LLM in the loop**: validators are deterministic. LLM (Claude) writes/extends them; runtime is pure Python.

## How this loops back to production SPY

The integration cycle (per `PARITY-PROTOCOL.md`):

1. **Detection**: `crypto/validators/runner.py` runs (manually, post-edit, or scheduled). A primitive fails → JSON scorecard logs evidence.
2. **Diagnosis**: The failing primitive lives in `crypto/lib/`. Fix the math there. Re-run validators until green.
3. **Port-to-SPY**: The corrected primitive is either (a) imported directly by SPY heartbeat code that lives in `backtest/` or `automation/`, or (b) the logic is mirrored into `automation/prompts/heartbeat.md` if the primitive lives in the LLM prompt layer.
4. **Continuous canary**: Validators stay green as a CI check. Any future regression in the primitive surfaces on the next run, not on the next trading day.

## What this folder is explicitly NOT trying to be

- ❌ Not a Karpathy-style shadow strategy (we have `shadow-version.json` for that on SPY)
- ❌ Not a research grinder (we have `backtest/autoresearch/` for that)
- ❌ Not a journaling surface (we have `journal/`)
- ❌ Not a doctrine layer (CLAUDE.md / OPs stay at project root)
- ❌ Not a live order surface for crypto

It's a **regression test bed for the chart-reading muscle**, full stop.

## Future extensions (queued, not required)

1. **v05_levels** — detect prior-day H/L, session H/L, round-number levels; verify against `key-levels.json` schema.
2. **v06_trendlines** — fit trendlines to swing-points, validate slope continuity.
3. **v07_regime** — classify bar series as trend / chop / breakout; verify regime transitions are stable.
4. **Alpaca-crypto MCP integration** — add a third source to v02_source_parity (runnable only from interactive Claude session, since MCP tools require live MCP connection).
5. **TradingView MCP parity** — port closed-bar logic test to BTCUSD on TV to validate `mcp__tradingview__data_get_ohlcv` directly. The lesson learned from L34 was specifically about TV; this would close the loop on the original source.
6. **Cron-fired regression check** — Windows Task Scheduler entry that runs `runner.py` every 6 hours and pings if FAIL surfaces. Cost: ~$0 (pure Python).
