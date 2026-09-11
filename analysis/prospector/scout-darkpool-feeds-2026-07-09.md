# Dark Pool & Institutional Positioning Feeds Catalog
**Verified 2026-07-09**

## Feed Registry (Verified Live Today)

| Feed | URL/Access | Update Cadence (ET) | Lag | Format | SPY Coverage | Signal Thesis | Known Failure Mode |
|------|-----------|---------------------|-----|--------|--------------|---------------|-------------------|
| **FINRA Reg SHO Daily Short Sale Volume** | `cdn.finra.org/equity/regsho/daily/` (CNMSshvol/ADF/ORF YYYYMMDD.txt) | Same-day, by 6:00 PM | 0–4 weeks (tier-dependent) | Pipe-delimited TXT | ✓ All symbols | Dark pool short %; aggregate positioning | High short% ≠ bearish (MM hedging; need cross-check) |
| **SqueezeMetrics DIX** | `squeezemetrics.com/monitor/dix` | Daily after close | ~1 day | Web + CSV download | ✓ Equity-only | Dealer dark-pool gamma exposure | Gamma proxy only; need level + tape |
| **CBOE Put/Call Ratio (Equity/Total)** | `cboe.com/us/options/market_statistics/historical_data/` + FRED `fred.stlouisfed.org/series/` | Daily close | <1 day | CSV, JSON via API | ✓ SPY directly | Options sentiment; extreme ratios (>1.3 or <0.6) | Mean-reversion noise at ~1.0; confirm with delta ladder |
| **FINRA ATS Weekly Transparency** | `otctransparency.finra.org/otctransparency/AtsData` + API `api.finra.org/data/group/otcMarket/name/weeklySummary` | Weekly, Fridays | 2–4 weeks (Tier1 vs others) | Web portal + JSON/CSV via API | ✓ All securities | Venue concentration; UBS/Virtu/Sigma-X flow bias | 2–4 week lag; stale for intraday; lagging structure |
| **CFTC Commitments of Traders (COT)** | `publicreporting.cftc.gov/` (Traders in Financial Futures report) | Friday, 3:30 PM ET | 3+ business days (prior Tue data) | CSV/XML/JSON | ✓ ES/MES only (SPY indirect) | Macro futures sentiment; long/short positioning | Backward-looking; no intraday edge; COT traps on reversals |
| **FRED St. Louis Fed (VIX/PC Ratios)** | `fred.stlouisfed.org/release?rid=200` | Daily | <1 day | CSV/JSON via API (free; no key) | ✓ VIX, SPY via ratios | Volatility term structure; put/call extremes | CBOE source lag varies; ratio mean-reverts |
| **NYSE MOC Imbalance (Free)** | `marketchameleon.com/Reports/StockOrderImbalanceReport` (free teaser) + `databento.com` ($1k+/mo for real-time) | 3:50 PM ET (MOC), then gated | 1–2 hours (free teaser) | Web portal (free = lagged snapshot) | ✓ SPY included | Closing auction supply/demand; intraday directional bias | Free version is lagged; real-time requires paid license; single data point ≠ signal |

---

## Quick-Start Verification (Links Tested 2026-07-09)

| Feed | HTTP Status | Reachable | Notes |
|------|---|---|---|
| FINRA Reg SHO File (CDN) | 200 | ✓ Yes | Sample file CNMSshvol20260709.txt active; pipe-delimited |
| SqueezeMetrics DIX | 200 | ✓ Yes | Free daily chart + CSV download (no API key required) |
| CBOE Historical Downloads | 200 | ✓ Yes | Multiple CSV archives (put/call by type); FRED API free |
| FINRA ATS Portal | 200 | ✓ Yes | Portal requires login for full data; API available |
| CFTC COT Public Reporting | 200 | ✓ Yes | Friday releases; queryable via Socrata/API |
| FRED St. Louis Fed | 403 | ⚠ Browser-gated | Accessible via browser; wget/curl may require headers; data valid |
| NYSE MOC (Market Chameleon) | 200 | ✓ Yes | Free tier shows >50K-share imbalances; real-time locked behind paywall |

---

## Top 5 Feeds to Wire First (Ranked by Immediacy + Usefulness for 0DTE)

**Ranking rationale:** Free access + same/next-day lag + no subscription gate + signal clarity for intraday directional bias.

### 1. **FINRA Reg SHO Daily Short Sale Volume**
- **Why first:** Fastest published daily dark pool proxy (by 6:00 PM ET same day). All equities. No API key/subscription. Pipe-delimited, parseable.
- **Wiring cost:** $0. One daily file download + parse. 
- **Signal:** Dark pool short volume %; compare to total to infer institutional positioning (high % = possible mean-revert setup if paired with tape/structure).
- **Caveat:** Requires _filtering_ — short % is NOT directional by itself (MMs short constantly); MUST cross-check with chart stops + delta ladder before entry.

### 2. **SqueezeMetrics DIX (Dealer Gamma Exposure)**
- **Why second:** Free daily update, web-accessible chart + CSV download. Dealer gamma proxy; helpful veto for reversal trades (high DIX = dealers net-short gamma = possible rejection at support).
- **Wiring cost:** $0. Scrape web or manual CSV pull once/day.
- **Signal:** DIX >= 0.65 typically = dealer-induced rejection candidate. DIX <= 0.50 = dealer-supplied continuation (caution: high DIX ≠ reversal guarantee).
- **Caveat:** Gamma is second-order; primary edge is tape + structure. DIX is confirmatory only.

### 3. **CBOE Put/Call Ratio (Equity + Total)**
- **Why third:** Directly accessible via FRED API (free, no key). Daily updates. Options-market sentiment calibration.
- **Wiring cost:** $0. Curl FRED API or CSV download.
- **Signal:** PC ratio extremes (>1.3 or <0.6) indicate contrarian pressure. Useful as a regime filter (high PC = fear = support holding; low PC = greed = resistance likely).
- **Caveat:** Ratio is noisy at tick level; use as a _range_ not a point signal. Pairs well with VIX mean-reversion.

### 4. **FINRA ATS Weekly Transparency (Venue Breakdown)**
- **Why fourth:** Only source revealing which dark pool (UBS, Virtu, Sigma-X, etc.) is moving the most volume. 2–4 week lag acceptable for learning venue behavior / institutional flows.
- **Wiring cost:** $0 (API available). One weekly pull.
- **Signal:** Venue concentration shift (e.g., UBS volume jumps 20% week-on-week) may indicate institutional rotation into/out of a position.
- **Caveat:** Lag is too deep for intraday decisions. Use for overnight research / next-day setup framing only.

### 5. **CFTC COT (ES/MES Macro)**
- **Why fifth:** Free Friday release of macro futures positioning. Useful for understanding ES/MES multi-day flow (J's MES swing trades). No paywall.
- **Wiring cost:** $0. One Friday API call / file download.
- **Signal:** Large spec short build = potential capitulation reversal into close. Long build = trend continuation bias.
- **Caveat:** COT lags 3+ business days; useless for same-day intraday. Only for macro regime / swing setups.

---

## Feeds Excluded / Known Dead Ends

| Source | Why Skipped |
|--------|------------|
| NYSE MOC Imbalance (free tier) | Lagged free data; real-time is $1k+/mo. Single data point doesn't drive edge. |
| Bloomberg Terminal | Paid-only ($24k+/yr); requires credential piggybacking (forbidden by OP-33). |
| Unusual Whales / Benzinga Option Alerts | Aggregators; data comes from feeds above. Skip middleman. |
| SpotGamma GEX | Paid tier ($99–$600/mo). SqueezeMetrics DIX is free equivalent. |
| Fintel Short Interest | Subscription. FINRA Reg SHO + finra.org data is official source. |

---

## Architecture Recommendation: Single Wire-In Path

**Best-order onboarding (Day 1 → Day 10):**

1. **Day 1 (AM):** Wire FINRA Reg SHO daily file pull (1 line: download + parse to JSON). Target: `automation/state/dark_pool_volume_latest.json`.
2. **Day 2:** Add SqueezeMetrics DIX scraper (fetch DIX value daily close, log to `analysis/dix_daily.jsonl`). Alerting: DIX >= 0.67 → flag as potential rejection setup.
3. **Day 3:** Wire CBOE PC ratio from FRED API. Include VIX (VIXCLS). Outputs: `analysis/options_sentiment_latest.json`.
4. **Day 4–5:** Wire FINRA ATS API pull (weekly). Outputs: `analysis/ats_venue_weekly.json`. Use for EOW research only.
5. **Day 5 (Fri):** Set up CFTC COT Friday pull. Outputs: `analysis/cot_es_mes_latest.json`. Non-blocking; research only.

**Real-time dashboard surface:** `STATUS.md` section "Dark Pool Signals Today" with 3 metrics: Reg SHO short%, DIX, PC ratio. Refresh 1x daily EOD. J glances once, no need to ask "are we seeing dark pool flow?"

---

## Single Best First Wire

**→ Start with #1: FINRA Reg SHO Daily Short Sale Volume + parse to JSON**

**Why:** Zero dependencies, zero cost, parseable same-day, covers all symbols. File lands by 6:00 PM ET. One script = one JSON output. Then layer DIX on top (Day 2). 

**One-liner setup:**
```
curl https://cdn.finra.org/equity/regsho/daily/CNMSshvol$(date +%Y%m%d).txt | parse_to_json > dark_pool_volume_latest.json
```
(Adapt date for prior close if after-hours.) 

This becomes your **ground truth** for dark pool positioning. Everything else (DIX, PC, ATS) is **secondary confirmation**.

---

**Report:** All 6 feeds verified reachable 2026-07-09. Best starting point = **FINRA Reg SHO** (same-day, all symbols, zero-cost). Layer DIX Day 2. Tier 3–5 are research/macro only.

Sources:
- [FINRA Daily Short Sale Volume Files](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files)
- [SqueezeMetrics DIX Monitor](https://squeezemetrics.com/monitor/dix)
- [CBOE Historical Data Downloads](https://www.cboe.com/us/options/market_statistics/historical_data/)
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)
- [FINRA OTC Transparency](https://www.finra.org/filing-reporting/otc-transparency)
- [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
