# CHART-READING-PROTOCOL.md — How to read a chart, 100x better than 5/14

> Source-of-truth procedure for reading the TradingView chart in any session
> (heartbeat, premarket, EOD audit, interactive). Every step references a validator
> in `crypto/validators/` that proves the primitive being applied.

---

## The 7-step protocol (in order, NO shortcuts)

### Step 1 — Establish "now" and the closed-bar boundary

Compute `now_et`. Identify the most recently CLOSED 5m bar:
```
last_closed.close_time = last_closed.open_time + 5 minutes
last_closed.close_time <= now_et   ← REQUIRED
```

**Critical anti-pattern** (the 5/14 foot-gun): trusting `bars[-1]` from any source as "the just-closed bar." TV `data_get_ohlcv` returns the in-progress bar at index [-1]. So does Coinbase REST. So does yfinance.

**Validator**: `crypto/validators/v01_closed_bar.py` + `crypto/benchmarks/replay_5_14.py`
**Library**: `crypto.lib.bar_reader.last_closed_bar(series, now)`

### Step 2 — Verify data freshness

The last closed bar must be no older than 2 × granularity (= 10 min for 5m bars). If older, the data source is lagging — flag verdict `stale_data` and either: (a) try a different source, or (b) skip this tick.

**Validator**: same `v01_closed_bar.py` — `stale_data` verdict
**Library**: same `last_closed_bar` returns `verdict="stale_data"` when applicable

### Step 3 — Multi-source sanity (when high stakes)

For ENTER / EXIT decisions, cross-check the closed bar against a second source within 0.10% tolerance. If sources disagree, do NOT make a decision on this tick.

**Validator**: `crypto/validators/v02_source_parity.py` + `v13_tv_mcp_parity.py`
**Library**: ad-hoc — call `fetch_bars("yfinance", ...)` and compare

### Step 4 — Read the indicator stack on closed bars only

Read RSI(14), EMA stack (9/21/55), ATR(14), VWAP — ALL computed from the closed-bar series. NEVER read indicator values that include the in-progress bar's snapshot. Live indicator panes (Saty Pivot Ribbon, etc.) ARE computed on the live bar — read them only AFTER verifying step 1's closed-bar.

**Validator**: `crypto/validators/v03_indicators.py`
**Library**: `crypto.lib.indicators.{rsi,ema,atr,vwap}`

### Step 5 — Identify the levels relevant to current price

Compute or recall:
- Prior-day RTH high / low (SPY) or prior-24h H/L (crypto)
- Round numbers within ±2 increments of current price
- Pivot P / R1 / S1 from prior period
- Any named pivots from indicators (Saty Pivots, etc.)

Pick the 3 nearest. Tag each with its strength (★★★ / ★★ / ★).

**Validator**: `crypto/validators/v05_levels.py`
**Library**: `crypto.lib.levels.{prior_period_levels, round_number_levels, pivot_points, nearest_levels}`

### Step 6 — Classify what the closed bar DID at the nearest level

For each of the 3 nearest levels, classify the closed bar's interaction:
- **RECLAIM**: open below, close above (with margin) — bullish event
- **BREAK**: open above, close below (with margin) — bearish event
- **REJECT**: high crosses level, close on origin side — bullish or bearish based on which side
- **HOLD**: touched but close inside the margin band — chop / no signal
- **SWEEP** (special — see step 6.5): wick exceeds level, close back on origin side cleanly

**Validator**: `crypto/validators/v05_levels.py` + `crypto/validators/v14_sweep.py`
**Library**: `crypto.lib.levels.classify_bar_at_level` + `crypto.lib.sweep.detect_sweeps`

### Step 6.5 — Check for SWEEP / failed breakout (the 5/14 lesson)

This is the step that would have caught 5/14. If the closed bar's wick exceeded a level but the close was back on the origin side cleanly, that's a SWEEP — exactly the opposite of a reclaim/break. The bar that fired the 09:58 ENTER_BULL on 5/14 was a bearish up-sweep on PMH 745.43:
- 09:55 bar high 745.47 (above PMH 745.43)
- 09:55 bar close 744.43 ($1.00 BELOW PMH)
- Prior bar (09:50) close 745.02 (below PMH — clean setup)

The heartbeat naively read the in-progress high above PMH as "level_reclaim." The closed-bar reading + sweep detector would have classified as `bearish_sweep` — block entry or fire bearish.

**Validator**: `crypto/validators/v14_sweep.py` — T1 reproduces the 5/14 bar exactly, fires correctly
**Library**: `crypto.lib.sweep.detect_sweeps(bars, levels)`

### Step 7 — Add context: volume, ribbon, regime

For any trigger to fire, layer on:
- **Volume**: current bar volume vs 20-bar average. Confirm with `≥ 1.5×`. (`crypto.lib.volume.is_volume_confirmed`)
- **Ribbon stack**: Fast > Pivot > Slow = BULL; reverse = BEAR; mixed = no edge. Spread ≥ asset-specific threshold (30c SPY). (`crypto.lib.ribbon.compute_ribbon`)
- **Regime**: TREND_UP / TREND_DOWN / CHOP / BREAKOUT. Trend-with bias = preferred direction. Chop = avoid. (`crypto.lib.regime.classify_regimes`)
- **Divergence** (when relevant): RSI vs price divergence at swing points = exhaustion signal. (`crypto.lib.divergence.find_divergences`)
- **Trendline**: nearest swing-fit trendline; touches = strength. (`crypto.lib.trendlines`)

**Validators**: v07-v10 + v06

---

## The trigger decision tree

```
1. Pull closed bar via Step 1.
   If verdict != "ok": EMIT_SKIP_OR_STALE; END.
2. Read indicators on closed-bar series via Step 4.
3. Identify nearest 3 levels via Step 5.
4. For the relevant level (set by setup / trade thesis):
   event = classify_bar_at_level(closed_bar, level)
   sweep = detect_sweeps([..., closed_bar], [level])
   IF sweep on this bar in OPPOSITE direction to our bias: BLOCK ENTRY.
   IF event in (RECLAIM, BREAK, REJECT) AND aligned with bias:
     - Verify volume (Step 7) — vol_ratio >= 1.5
     - Verify ribbon (Step 7) — stack matches bias direction
     - Verify regime (Step 7) — not CHOP
     - All pass: TRIGGER FIRED.
   ELSE: HOLD.
5. Record the read: emit log entry with closed-bar timestamp, classified event,
   indicator values used (RSI, EMA, vol_ratio, ribbon spread, regime), level price,
   sweep status. Future audits can replay.
```

---

## Anti-patterns (banned)

| Don't | Do | Why |
|---|---|---|
| Read `bars[-1]` as "just-closed" | Filter `bar.close_time <= now` | The 5/14 foot-gun (R4/L34/OP25). |
| Trust a level-reclaim trigger on a bar where the close is BELOW the level | Check `event == RECLAIM` requires open < level AND close > level both | The 5/14 09:58 ENTER_BULL fired on intra-bar high, not on a closed reclaim. |
| Score on the in-progress bar's high or close | Only on the LAST CLOSED bar | Same. |
| Ignore SWEEP / wick-rejection pattern | Run `detect_sweeps` before classifying as RECLAIM/BREAK | The 5/14 09:55 bar was a bearish sweep — the engine saw it as a reclaim. |
| Use single-source data for high-stakes decisions | Cross-check Coinbase + yfinance + TV when entering / exiting | Provider drift happens at bar boundaries. |
| Confuse "ribbon BULL on live snapshot" with "ribbon BULL on closed bar" | Compute ribbon from closed-bar EMAs OR verify the live ribbon hasn't flipped since the last closed bar | EMAs are slow but jitter at the boundary. |
| Treat candlestick patterns as triggers | Use as AWARENESS only (per OP-6) | No backtest evidence yet that they add edge. |

---

## How heartbeat.md v15.1 should reference this

After the next doctrine pass, the relevant heartbeat.md lines should read:

```
## SPY 5m + ribbon (chart-reading protocol)
1. Fetch via `data_get_ohlcv(count=3, summary=true)` on BATS:SPY 5m.
2. Compute now_et. For each bar, bar_close_et = bar.time + 5min.
3. Filter to bars where bar_close_et <= now_et. Last surviving bar = "last closed bar."
   (Source of truth: crypto.lib.bar_reader.last_closed_bar)
4. Apply chart-reading protocol Step 1-7 (crypto/docs/CHART-READING-PROTOCOL.md).
5. Score trigger only against the closed bar's values.
```

---

## How to use during interactive Claude sessions

When user asks "what does the BTC chart look like right now?":

1. Use `mcp__tradingview__chart_set_symbol("COINBASE:BTCUSD")`
2. Use `mcp__tradingview__data_get_ohlcv(count=5, summary=false)` to get 5 bars (4 closed + 1 in-progress)
3. **Mentally apply Step 1**: identify which bar is in-progress (bar.time + granularity > now_unix) and which is the last closed.
4. **Mentally apply Step 5**: identify the round levels near current price
5. **Mentally apply Step 6**: what did the closed bar do at the nearest level?
6. **Mentally apply Step 6.5**: was it a sweep?
7. Report the read with explicit references to: closed-bar timestamp, indicator values, level interaction, sweep status.

Then switch TV back to `BATS:SPY` (production).

A correctly-read chart should always be reportable in the form:
> "At HH:MM:SS, last closed 5m bar = HH:MM open T+0 close T+5. Bar's interaction with nearest level (PRICE, ★N): {RECLAIM/BREAK/REJECT/HOLD/SWEEP-UP/SWEEP-DOWN}. RSI(14)=X.XX, EMA-20=YYY.YY, ATR(14)=Z.ZZ. Regime: {TREND_UP/TREND_DOWN/CHOP/BREAKOUT}. Ribbon: {BULL/BEAR/MIXED} spread Sc. Volume ratio: V.Vx. Verdict: {HOLD/WATCH/TRIGGER_OK}."

If you cannot make that statement, the chart hasn't been read.
