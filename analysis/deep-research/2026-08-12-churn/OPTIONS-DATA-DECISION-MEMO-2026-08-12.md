# Options-data decision memo (agent research, 2026-08-12 evening)

**VERDICT: never blocked. The free Alpaca tier already serves 1-min per-contract OPRA bars,
same-day 0DTE included, back to Feb 2024, at $0/mo, 200 req/min.** J does nothing — no signup,
no agreement, no subscription. All prior "blockers" were misdiagnoses.

## Live-probed capability matrix (both keys, identical, 2026-08-12 ~19:47 ET)

| endpoint | status |
|---|---|
| `/v1beta1/options/bars` 1Min + 5Min, incl. same-day 0DTE, history to 2024-02 | ✅ 200 |
| `/v1beta1/options/bars?feed=...` | 400 — bars take NO feed param |
| `/v1beta1/options/trades` (ticks, exch+condition codes) | ✅ 200 |
| `/v1beta1/options/quotes` (historical) | ❌ 404 — **does not exist at ANY tier** (product gap) |
| `/v1beta1/options/quotes/latest` (default / `feed=indicative`) | ✅ 200 |
| `/v1beta1/options/quotes/latest?feed=opra` | 403 "OPRA agreement is not signed" ← the ONLY source of that error |
| `/v1beta1/options/snapshots` (incl. greeks + IV) | ✅ 200 |
| `/v2/stocks/bars?feed=sip` older than ~15 min | ✅ 200 (incl. premarket) |
| `/v2/stocks/bars?feed=sip` younger than ~15 min | 403 |

**Misdiagnoses corrected:** (1) the "bars 403" was a quotes-with-feed=opra probe misattributed
to bars; (2) SIP is free for >15-min-old data — the IEX fallback returned **3 premarket bars
where SIP has 274 (1% coverage)** on 08-11; (3) the 08-12 cache gap was
`fetch_option_data.py`'s **hardcoded 19-contract list frozen 2026-05-07**, not an API block.

**Quality vs broker truth:** all 85 of 08-12's fills matched a 1-min bar (zero gaps), ~4c mean
abs deviation on ~$1 premiums, +1.2c buy-side skew = paper-fills-at-ask signature. Throughput:
42 contracts x 1 day x 1-min = 11,938 bars in 1.9s; a year ≈ <10 min.

## Ranked alternatives (only if the $0 path is outgrown)

Massive/Polygon $29 (15-min delayed) · ThetaData $40 (4y history, Java daemon) · **Alpaca Algo
Trader Plus $99 (only adds realtime OPRA — engine already has broker snapshots; useless for
research)** · Databento ~$199 byte-metered. TRAPS verified: MarketData.app + FirstRate = EOD
only; IBKR structurally EOD-for-options; CBOE $5k/mo. **Buy nothing.**

## Queued repo fixes (Opus)

1. **Unfreeze `backtest/tools/fetch_option_data.py` CONTRACTS** — derive from the fills ledger.
2. **DST bug**: `fetch_option_data.py:91` and `_option_bars_1min_cache.py` hardcode UTC-4 —
   mislabels every EST-month bar. Route through `lib/et_frame.py` (known artifact class).
3. **Premarket levels → SIP** for >15-min-old reads (IEX 1% coverage is why premarket highs
   disagree between surfaces).

Unresolved: whether "indicative" bars differ numerically from paid OPRA (no paid key to A/B —
circumstantially real: exchange codes + 4c fill reconciliation); Databento $/GB; the engine's
774.20 premarket figure vs SIP's 774.96 (window definition, untraced).
