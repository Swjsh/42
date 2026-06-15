# PARITY-PROTOCOL.md — How crypto validates SPY

> This is the operational handbook. Read it before extending the harness or
> using its output to gate a production SPY change.

## The invariant

> **A chart-reading primitive that fails on BTC-USD 5m bars at 03:47 ET would fail on SPY 5m bars at 13:47 ET. Conversely, a primitive that passes 24/7 on crypto is a primitive we can ship to SPY heartbeat with high confidence.**

This invariant only holds for primitives whose correctness depends on **bar structure + price-geometry + indicator math**. It does NOT hold for primitives whose correctness depends on session structure, macro context, or options-specific math.

## Translation table

| Concept | SPY | Crypto | Portable? |
|---|---|---|---|
| Bar granularity | 1m / 5m / 15m / 1h | Same | YES |
| Closed-bar definition | `bar.close_time ≤ now` | Same | YES |
| In-progress-bar pathology | `data_get_ohlcv[-1]` | `coinbase /candles[0]`, `yfinance .iloc[-1]` | YES |
| RSI(14) Wilder | TV Pine RSI(14) | Same math | YES |
| EMA(20) | `alpha = 2/(L+1)`, SMA seed | Same | YES |
| VWAP | Session-anchored at 09:30 ET | Day-anchored at 00:00 UTC by convention | YES (with explicit anchor) |
| Engulfing candle | Same body geometry | Same | YES |
| Inside bar | Same range comparison | Same | YES |
| Prior-day H/L | Yesterday's RTH H/L | Yesterday's 00–24 UTC H/L | YES (with explicit window) |
| Round-number levels | 720, 725, 730 SPY | 78000, 80000, 82000 BTC | YES |
| Trendline slope | Connect ≥2 swing points | Same | YES |
| Volume confirmation | Curr vol / 20-bar avg ≥ 1.5 | Same RATIO | YES |
| Opening range | 09:30–09:45 ET | N/A | NO |
| VIX regime gate | VIX > 20 ⇒ wider stops | DVOL, not portable | NO |
| Theta decay | 0DTE option decay | Crypto options have theta but DTE structure differs | NO |
| Macro calendar | FOMC / CPI / NFP / earnings | Partial overlap, different reactions | NO |

## The four use cases for this harness

### 1. Regression test (pre-flight)

Before merging any change to:
- `automation/prompts/heartbeat.md` (LLM bar-reading logic)
- `backtest/lib/filters.py` (programmatic bar-reading logic)
- Any indicator code in `backtest/autoresearch/`

Run `python crypto/validators/runner.py`. Expect OVERALL: PASS. If FAIL, the change has introduced a regression in a primitive the SPY engine depends on. Don't merge until green.

### 2. Foot-gun reproducer

When a new bar-reading or indicator foot-gun is reported (e.g., "the heartbeat scored on bar X but bar X was still open"):

1. Add a test to the relevant `crypto/validators/vNN_*.py` that reproduces the pathology on synthetic data.
2. Verify it fails before the fix, passes after.
3. The test stays in the suite as a permanent regression check.

### 3. Multi-source drift detection

`v02_source_parity.py` compares Coinbase vs yfinance bars within 0.05% (5 bp) tolerance on each OHLC field. If a future run reports `disagreements_above_tolerance > 0`, one of the providers has drifted (corporate action, data backfill, or upstream bug). Investigate before trusting either source.

### 4. New-primitive development

When adding a new chart-reading primitive (e.g., "detect a 3-bar consolidation pattern"):

1. Implement in `crypto/lib/` (pure function over `Bar` / `BarSeries`).
2. Write `crypto/validators/vNN_*.py` with synthetic positive + negative tests.
3. Run against live BTC bars for at least 24h to confirm fire rate is sensible.
4. Only then port to SPY heartbeat / backtest engines.

## Integration cycle

```
   [SPY foot-gun detected]
            │
            ▼
   Add test case to crypto/validators/vNN_*.py
   (reproduces pathology on synthetic or live crypto bar)
            │
            ▼
   Fix primitive in crypto/lib/
            │
            ▼
   Verify: python crypto/validators/runner.py → OVERALL: PASS
            │
            ▼
   Port corrected primitive to one of:
      ① backtest/lib/filters.py     (programmatic SPY engine)
      ② automation/prompts/heartbeat.md  (LLM-driven SPY engine)
   ──── per OP 4 (no code drift) — BOTH if both have the primitive
            │
            ▼
   Append entry to CLAUDE.md `Lessons absorbed` (OP 25)
            │
            ▼
   Continuous: runner.py runs on next code change or cron schedule
   ──── any future regression fires the same test, no new investigation needed
```

## Verdict semantics (across all validators)

| Verdict | Meaning | Action |
|---|---|---|
| `ok` | Primitive working correctly on this fetch | None |
| `no_closed_bars` | Empty series or all-future bars | Investigate source (rate-limit? auth?) |
| `future_bar` | Only bar(s) returned are after `now` | Clock skew or test data error |
| `stale_data` | Last closed bar > 2× granularity old | Source is lagging — switch sources |
| `disagreements_above_tolerance` (v02) | OHLC drift > 0.05% between sources | One source has bad data — investigate |
| `pass=False` (live indicators) | Math invariant violated | Math bug — fix immediately |

## What `OVERALL: PASS` means

- All offline tests passed (deterministic correctness of math + filtering)
- Live integrations returned `verdict=ok` (no in-progress leakage, no stale data)
- Multi-source parity within tolerance
- Indicator math sanity checks passed
- Candlestick detection ran without exceptions

This is a STRONG SIGNAL that chart-reading primitives are healthy. It is **not** a signal that SPY trading strategy is healthy — that's a separate, larger validation surface.

## What this protocol does NOT protect against

- Strategy-level bugs (wrong threshold, wrong stop math, wrong sizing)
- Doctrine drift (rule changes that aren't propagated to code)
- Order-routing bugs (Alpaca options API)
- Risk-management bugs (kill switches, daily loss limits)
- Account-state bugs (position tracking, fill reconciliation)

Those have their own protections — backtest grinders, scorecards, `walk_forward_validate.py`, `simulator_real.py`, the kill-switch tests in `backtest/tests/`, etc.

## When to invalidate this harness

This harness should be retired or substantially refactored if:

- We move off OHLCV bars to tick-level data
- We add primitives whose correctness depends on equity-specific microstructure (e.g., NBBO, dark pools, halt detection)
- Crypto and SPY diverge fundamentally (e.g., SPY 0DTE goes intraday-only and crypto is removed from scope)

Until then: it's a $0/mo regression check that catches a real class of bug in seconds.
