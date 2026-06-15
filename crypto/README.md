# crypto/ — 24/7 Engine Primitive Validation Harness

**Not a trading bot. A regression test bed.**

The Project Gamma engine reads OHLCV bars, computes indicators, detects candlestick patterns, identifies levels, and makes deterministic decisions on SPY 0DTE during the 09:30–15:55 ET window. The SPY market is closed 17.5 hours per weekday and all weekend — so a bug in our bar-reading logic (like the 2026-05-14 in-progress-bar foot-gun, OP 25 / L34 / R4) takes 24+ hours to surface and another 24+ hours to validate the fix.

**Crypto is on 24/7.** OHLCV bars on BTC-USD 5m have identical structure to SPY 5m. So if our bar-reading / indicator / pattern-recognition primitives are correct on crypto, they're correct on SPY. And we can validate them RIGHT NOW instead of waiting for market open.

## What this validates (~70% of the chart-reading stack)

| Primitive | Ports to SPY? | Why |
|---|---|---|
| Closed-vs-in-progress bar detection | YES | OHLCV structure is identical |
| RSI / EMA / MACD / BB / ATR / VWAP math | YES | Indicator definitions are timeframe + asset agnostic |
| Candlestick pattern recognition | YES | Pattern definitions are price-action universal |
| Trendline / level detection from prior highs/lows | YES | Pure price-geometry math |
| Volume confirmation thresholds | MOSTLY | Crypto volume conventions are quote-currency, but ratios port |
| Regime classification (trend vs chop) | MOSTLY | Crypto chops differently but principles port |

## What this does NOT validate (SPY-only)

- Options Greeks, theta decay, IV skew
- Opening range dynamics (different open times)
- VIX-based regime gating
- Macro calendar reactions (FOMC, CPI, NFP, mega-cap earnings)
- 0DTE-specific session dynamics
- PDT rules, daily P&L kill switches

## Quick start

```powershell
# Pull live BTC 5m bars from Coinbase + check closed-bar filter
python crypto\validators\v01_closed_bar.py --source coinbase --symbol BTC-USD

# Cross-source parity check (Coinbase vs yfinance)
python crypto\validators\v02_source_parity.py --symbol BTC-USD

# Run the full validator suite
python crypto\validators\runner.py
```

## Layout

```
crypto/
├── README.md                 # this file
├── CLAUDE.md                 # mini-doctrine for crypto-folder work
├── docs/
│   ├── DESIGN.md             # full design rationale + scope discipline
│   ├── PARITY-PROTOCOL.md    # how crypto validation translates to SPY confidence
│   └── DATA-SOURCES.md       # source comparison (Coinbase / yfinance / Alpaca crypto)
├── lib/
│   ├── bar.py                # Bar dataclass
│   ├── data_sources.py       # multi-source fetcher
│   ├── bar_reader.py         # closed-bar logic (port of heartbeat.md v15.1 fix)
│   ├── indicators.py         # RSI / EMA / VWAP math (matches TV's Pine implementations)
│   └── candlesticks.py       # pattern recognition (engulfing / hammer / pin / doji)
├── validators/
│   ├── v01_closed_bar.py     # offline + live closed-bar validation
│   ├── v02_source_parity.py  # cross-source agreement check
│   ├── v03_indicators.py     # indicator math vs reference
│   ├── v04_candlesticks.py   # pattern recognition on labeled bars
│   └── runner.py             # runs all + writes scorecard
└── data/
    └── *.csv                 # cached historical bars (gitignored)
```

## Why this exists (one-line)

> Every primitive that fails on crypto bars at 03:47 ET would fail on SPY bars at 13:47 ET. We catch it now instead of after a misaligned live trade.

## Scope discipline (READ BEFORE EXTENDING)

This folder is for **validating engine primitives**, NOT for:
- Trading crypto live (different broker risk model, different liquidity, different regs)
- Building crypto-specific strategies (out of scope; this is a parity harness)
- Modifying production SPY logic from inside this folder (zero-risk to live trading)

If you want to add a crypto trading strategy, that goes in a separate folder (`crypto-trading/` or similar). This folder stays a validation harness.
