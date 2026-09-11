# FUTURES BROKER RESEARCH — micros (MES/MNQ), SIM this week, API-first, Windows, cheap/free

**Date:** 2026-08-09 · **Scope:** web research only, no code changed, no accounts created (J creates any account himself — Claude never handles credentials or KYC).
**Why:** Alpaca does not offer futures (confirmed — see Alpaca section). J wants MES/possibly MNQ, SIM/PAPER this week, real money only after proven edge, on the existing pure-Python REST/WS engine shape (`crypto_twin_core.py`'s adapter pattern).

---

## VERDICT — for J (read this, skip the rest unless you want the receipts)

- **Start THIS WEEK: Tastytrade sandbox.** Only candidate with a genuinely free, self-serve, no-funded-account API sandbox (`developer.tastytrade.com` → Create Sandbox Account) + a well-maintained Python SDK (`pip install tastytrade`) with auto-refreshing OAuth — the least friction of anything reviewed to get a headless Python loop placing simulated orders. **One unresolved check before committing:** futures trading needs "The Works" permission enabled, a 1-3 day approval process on live accounts — whether sandbox skips this is UNVERIFIED, first thing to test.
- **Data gotcha that applies to EVERY broker, not just Tastytrade:** sandbox/demo/paper market data is delayed (10-15min) unless you fund a LIVE account. This is a CME licensing rule, not broker stinginess — no broker reviewed gets around it for free.
- **The actual fix: don't get futures data from the broker at all.** The project already has TradingView MCP wired (Plus plan). CME real-time futures data there is a **$7.00/month non-pro add-on** (confirmed price) — dramatically cheaper than any broker's real-time-via-API fee ($125-$500+/month, see table). Use TradingView for the chart/signal, use whichever broker for order execution only — this is literally the workaround Tradovate's own developer community landed on independently.
- **Runner-up / real-money-later pick: Interactive Brokers paper**, via `ib_async` (the actively-maintained fork of the now-archived `ib_insync`). Not instant — paper access rides on a real account-application/KYC flow, not literally same-day like Alpaca — so start the application this week even though it's not the $0-friction pick. Cheapest micro commission found anywhere: **$0.25/contract** (MES/MNQ). Most mature Python ecosystem by far.
- **Data-only fallback if account creation stalls: `yfinance` (`MES=F`/`ES=F`)** — $0, works today, but Yahoo's own page labels it a delayed quote and it has documented gap/outage issues on futures symbols specifically (cited GitHub issues below) — needs a staleness watchdog, same "never-blind" pattern already used for the crypto twin.
- **Reject for "this week, free": Ironbeam and TradeStation** — both confirmed (via their own docs) to gate real API access behind funded accounts ($1,000 and $10,000 respectively). **Reject NinjaTrader (classic NT8)** outright — confirmed not headless-Python-capable; note "NinjaTrader's API" as marketed today is actually **Tradovate's API** (NinjaTrader acquired Tradovate Jan 2022) — same company, evaluate under Tradovate.
- **Rithmic (via AMP/Ironbeam/Optimus) is the best Python library and the most professional infra** (`async_rithmic`, actively maintained, updated Aug 3 2026) but costs a real **$125/month + $0.10/contract** once past a 14-day trial, and that trial's suitability for API-driven (not just GUI) forward-testing is contested by a direct forum report. Revisit this once real money is proven, not for "free this week."
- **Tradovate is the wildcard** — marketing says free 2-week demo with real-time data and full API access; a direct Tradovate staff quote in their own community forum says API credentials require a $1,000 funded live account + $25/month, full stop, demo/eval excluded. These two claims genuinely conflict in my research (both sides below). **5-minute ask for J:** hit Tradovate's support chat and ask "can I get `demo.tradovateapi.com` credentials without funding a live account, yes or no" — if yes, Tradovate leapfrogs Tastytrade as the pick, since it's the only one offering real-time data through the API itself for free.

---

## Comparison table

| Venue | Free API sim (no funding)? | Data in sim | Python story | Cost once live (micros) | Verdict |
|---|---|---|---|---|---|
| **Tastytrade** | **Yes** — self-serve sandbox, no funded-account gate found | 15-min delayed | Unofficial `tastyware/tastytrade` (active); official SDK archived Mar 2026 | $0 platform, $0.75/contract/side micros | **Start here** |
| **Interactive Brokers** | Paper is free but requires a real account-application (KYC-style), not instant | 15-min delayed on paper unless you fund + subscribe live | `ib_async` (maintained fork of archived `ib_insync`) — most mature ecosystem found | $0.25/contract micros (cheapest found) | **Runner-up / real-money path** |
| **Tradovate** (= "NinjaTrader API") | **CONTESTED** — marketing says yes; Tradovate staff quote says API needs $1,000 funded live + $25/mo | Real-time claimed in demo; $290-500/mo CME sub-vendor fee if via API live | No official SDK; thin unofficial wrappers; raw REST/WS is usable directly | $0.09-0.39/side micros depending on plan tier | Verify directly before building on it |
| **Ironbeam** | **No** — Ironbeam's own KB: unfunded/paper accounts do not qualify for API access, any tier | GUI demo = free but delayed; API sim-with-live-data = $99/mo add-on | Clean OpenAPI-spec'd REST (auto-gens Python client); community wrapper is WIP-quality | $249/mo API fee unless ≥5 contracts/mo traded live | Good design, not free |
| **Rithmic** (AMP/Ironbeam/Optimus) | 14-day trial (first-time only); API-specific paper access murky (forum: broker couldn't get one issued) | Trial reportedly real-time; unconfirmed for custom-code access | `async_rithmic` — best-maintained lib of the field (v1.6.5, Aug 3 2026) | **$125/mo flat** (API+TraderID) + $0.10/contract routing | Best infra, not free ongoing |
| **TradeStation** | **No** — retail API path requires $10,000 funded account per their own signup page | N/A (gated) | No official SDK | ~$40/mo data unless ≥$40/mo commissions generated | Disqualified by funding gate |
| **NinjaTrader (NT8/NinjaScript)** | Sim101 free but real-time data free only 14 days | N/A | **C#/.NET only** — confirmed "not currently possible to run completely headless" per their own forum; CrossTrade bridge still needs the desktop process alive, $49/mo | N/A | Reject — not headless-Python-capable |
| **yfinance** (data-only) | $0, no account | CME-labeled delayed quote, exact minutes undisclosed | Unofficial but ubiquitous `pip install yfinance` | N/A — data only, no execution | Fallback if broker setup stalls |
| **Databento** (data-only) | $125 one-time free credit (historical) | Live streaming = paid only | Official package, well-maintained | Live ≈ $230+/mo all-in (Standard $179-199 + CME pass-through) | Good for backfill, not free live |
| **Massive/Polygon.io** (data-only) | $0 Futures Basic tier | **Historical only**, no current data on free tier | Official Python client | $29/mo Starter = 10-min delayed + WS | Cheap paid option if ever needed |
| **TradingView** (signal source, already wired) | N/A — already have Plus plan | 10-min delayed by default, same as everyone else | N/A — MCP already wired into this project | **$7.00/month** non-pro CME real-time add-on | **Cheapest real-time fix found**, reuses existing wiring |

---

## Per-candidate detail

### Tastytrade — the "this week" pick

- **Sim/paper access.** `developer.tastytrade.com/getting-started/` offers a self-serve "Create Sandbox Account" flow with no evident funded-account gate. Sandbox resets every 24 hours (positions/trades cleared). [Sandbox docs](https://developer.tastytrade.com/sandbox/), [Getting Started](https://developer.tastytrade.com/getting-started/).
- **API reality for Python.** REST + WebSocket, OAuth2. Session (access) token lives **15 minutes**; refresh token **never expires**; SDK versions ≥12.0.0 auto-refresh behind the scenes — about as headless-daemon-friendly as this research found. [Sessions docs](https://tastyworks-api.readthedocs.io/en/latest/sessions.html). The **official** SDK (`tastytrade/tastytrade-sdk-python`) was **archived March 13, 2026** — dead, do not build on it. The **unofficial** `tastyware/tastytrade` (`pip install tastytrade`) is the de facto standard: typed, async, actively released. [GitHub](https://github.com/tastyware/tastytrade).
- **Micro contract support.** Confirmed real product line — MES and other CME micros listed, IRA net-liq threshold $5K for micros vs $25K standard-size. [tastytrade.com/futures](https://tastytrade.com/futures/). **Open question:** futures require enabling "The Works" trading-permission tier, which on a LIVE account is an application taking 1-3 business days ([support article](https://support.tastytrade.com/support/s/solutions/articles/43000494633)) — whether the sandbox/cert environment requires this same approval flow or grants full permissions by default is **UNVERIFIED**; test this in the first 10 minutes of setup before assuming it's frictionless.
- **Market data in sandbox:** confirmed **15-minutes delayed**, not real-time, not simulated-tick.
- **Cost table (for the later live phase).** $0 account minimum, $0 monthly platform fee, no inactivity fee. Futures $1/contract/side standard, **$0.75/contract/side micros**, plus exchange/clearing/regulatory pass-through. [Pricing](https://support.tastytrade.com/support/s/solutions/articles/43000435233).
- **Reliability/reputation.** Public API launched ~May 2023 ([Business Wire](https://www.businesswire.com/news/home/20230501005254/en/Tastytrade-Releases-tastytrade-API)) — younger than IB's stack but futures is a real, documented product line, not an afterthought.

### Interactive Brokers — the durable runner-up

- **Sim/paper access.** Every new client automatically gets a linked paper account with $1M virtual equity ([IBKR Campus](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)), but getting there means going through IBKR's real account-application process (identity verification etc.) — **not** instant/anonymous like Alpaca, even though the Cash account itself needs **$0** to open ([confirmed $0 minimum, Feb 2026](https://brokerrank.net/broker/interactive-brokers/minimum-deposit)). Approval is typically fast (same-day to a few days), not weeks — still workable "this week," just not zero-friction.
- **Data in paper.** Paper trading market-data permissions mirror the linked LIVE account's subscriptions. Without a funded live account + purchased/shared CME data packages, paper defaults to **delayed data** (IB's own "Paper Trader Delayed Data" page title confirms the framing). Real-time futures quotes on paper require: funded account, trading permissions, and market-data subscriptions shared from the live username to the paper username. [Confirmed via multiple IBKR Campus/pricing pages].
- **API reality for Python.** TWS API / IB Gateway — mature, extensively documented ([TWS API intro](https://interactivebrokers.github.io/tws-api/introduction.html)). Requires a local TWS or IB Gateway **process** running (default ports 7497 paper / 7496 live TWS, 4002 paper / 4001 live Gateway) — not literally "no software," but IB Gateway is a lightweight, scriptably-headless Java process, not an interactive GUI you drive by hand. **`ib_insync` was orphaned** when its sole maintainer Ewald de Wit passed away in early 2024; the original repo was archived March 14, 2024. The community fork **`ib_async`** (GitHub org `ib-api-reloaded`) is the actively-maintained, drop-in-compatible successor as of 2026 (open issues through May 2026 show ongoing work) — build on `ib_async`, not the archived original. [Migration notes](https://glama.ai/mcp/servers/@haymant/tws-mcp/blob/706b86a649da7c2944d1164ce0da2fbe9f04b7d1/docs/MIGRATION_TO_IB_ASYNC.md).
- **Headless Windows operation — a solved problem.** `IbcAlpha/IBC` (formerly IBController) auto-fills the TWS/Gateway login dialog and supports an **autorestart** mode so the app can run Sunday-to-Sunday with a single login. Standard pattern: IBC + Windows Task Scheduler for a daily health-check/restart. [IBC user guide](https://github.com/IbcAlpha/IBC/blob/master/userguide.md).
- **Micro contract support + cost.** MES/MNQ supported. Commission **$0.25/contract** — the cheapest found in this entire research pass. Non-pro market-data subscription fees are commonly waived if the account generates enough commission in a month (~$5-20 threshold depending on the data bundle) — relevant once live, not for paper-only.
- **Reliability/reputation.** Longest-established API and largest developer community of anything reviewed here; `ib_async`/`ib_insync` is the most cited Python futures/options wrapper in the algo-trading community.

### Tradovate (== "NinjaTrader's API" since Jan 2022) — contested, verify before building

- **The NinjaTrader connection.** `developer.ninjatrader.com`/`docs.ninjatrader.com/api` markets a REST+WebSocket "Trade API" with Swagger docs — this is literally Tradovate's API (`demo.tradovateapi.com` / `live.tradovateapi.com`), rebadged under NinjaTrader's developer site since NinjaTrader acquired Tradovate in January 2022. [NinjaTrader support confirms](https://support.ninjatrader.com/s/article/Tradovate-API-Access). Treat "NinjaTrader API" and "Tradovate API" as the same evaluation.
- **Sim/paper access — the conflict.** Multiple secondary sources describe the 2-week free trial ($50K virtual funds, no card) as giving genuinely free, headless, real-time-data API access ([info.tradovate.com/simulated-trading](https://info.tradovate.com/simulated-trading)). But a **direct Tradovate staff reply** ("Alexander") in Tradovate's own community forum states plainly: API credentials require a **live account with $1,000+ equity and a $25/month subscription**; "prop firm and evaluation accounts are excluded from Tradovate's API program regardless of the balance showing on the dashboard" — simulation balances don't count toward the threshold. [Forum thread](https://community.tradovate.com/t/could-i-user-api-access-the-simulation-env-by-a-simulation-account/4033). My read: the GUI/platform trial is genuinely free; getting your OWN raw API keys against it is the part that's gated — but I could not fully reconcile the two claims from public sources. **Flagged UNVERIFIED — confirm directly with Tradovate before committing engineering time.**
- **CME data via the API.** Independent of the above, streaming real-time market data through Tradovate's own WebSocket API triggers a CME Individual License Agreement (sub-vendor registration), cited at **$290-500/month** ([forum](https://community.tradovate.com/t/is-cme-sub-vendor-requirement-for-api-access-is-290-per-month/6215), [pickmytrade](https://blog.pickmytrade.trade/tradovate-automation-skip-the-api-fee-and-cme-license/)). **Order placement alone does not require this** — the community's own workaround is "bring your own data source (e.g., DataBento, TradingView), use Tradovate purely for order execution," which is exactly the pattern this report recommends project-wide (see TradingView $7/mo note above).
- **Python.** No official SDK. Thin unofficial wrappers exist (`cullen-b/Tradovate-Python-Client`, `antonio-hickey/TradovatePy`) but the REST+WS surface is OpenAPI-documented and plain enough to hit directly with `requests`/`websockets`, matching this project's existing "no SDK dependency, urllib/stdlib only" convention (see crypto_twin_broker.py).
- **Micro contracts + cost.** Full support. Commissions: Free plan $0.39/side micro, Monthly ($99/mo) $0.29/side, Lifetime ($1,499 one-time or 4×$499) $0.09/side — cheapest micro commissions found if the Lifetime tier is ever worth it. [Pricing](https://www.tradovate.com/pricing/).

### Ironbeam — clean API, not free for programmatic access

- **Sim/paper access.** The GUI/platform demo is genuinely free and requires no deposit to open a live account either ("no minimum deposit required," ["fast, free, no minimum"](https://www.ironbeam.com/gettingstarted/)) — but the demo is explicitly **delayed data**: "if you prefer to test drive the platform on a demo account with delayed market data you can sign up."
- **API specifically.** Ironbeam's own knowledge-base article states a funded live account with a **$1,000 minimum** is required for API access **at every tier, including simulation** — paper/unfunded accounts do not qualify. [ironbeam.com/knowledge-base/ironbeam-api-access](https://www.ironbeam.com/knowledge-base/ironbeam-api-access/) (independently fetched twice, by me and by a parallel research pass, with consistent results — higher confidence than the Tradovate picture). Free API access is available to live accounts trading ≥5 contracts/month; otherwise **$249/month**. A sim-with-real-time-data add-on is **~$99/month**.
- **API design quality.** Genuinely good: OpenAPI-spec'd REST that auto-generates client libraries in Python/C#/TypeScript/Java/PHP, Bearer-token auth via a dedicated `/auth` endpoint, distinct `demo.ironbeamapi.com` / `live.ironbeamapi.com` base URLs, WebSocket streaming. [API docs](https://docs.ironbeamapi.com/). Rate limit reported around **15 requests/second**, bucketed (some users report tighter effective throttling — [429 rate limiting thread](https://www.ironbeam.com/community/t/429-rate-limiting/1024)).
- **Python.** Community wrapper `dmckim1977/ironbeam` exists but its own README calls it "a work in progress" and notes "there are some typos and stuff with the docs" requiring workarounds — treat as immature; the OpenAPI-generated client route is more reliable.
- **Verdict.** Best-designed REST API of the field, but fails the "free this week, no funding" requirement outright per its own documentation.

### Rithmic (via AMP Futures / Ironbeam / Optimus Futures) — best infra, real ongoing cost

- **Sim/paper access.** Rithmic runs a **14-day free trial**, first-time registrants only, auto-blocked on repeat signups, typically accessed via a broker's hosted signup form (e.g., [AMP's "Rithmic FREE Demo"](https://www.ampfutures.com/trading-platform/rithmic-free-demo)). Separately, a lower-level **"Rithmic Test"** development environment exists that developers can request directly — [async_rithmic's own docs](https://async-rithmic.readthedocs.io/en/latest/connection.html) say "you can develop against Rithmic Test without conformance needed," but the access process itself is just "contact Rithmic," opaque from outside. A real user with an active **live** Ironbeam account, asking specifically for an API-accessible Rithmic **paper** account with live data for forward-testing, was told by Ironbeam's own team: *"Rithmic will not issue me one. They only offer a test account to access their test environment."* [Ironbeam community thread](https://www.ironbeam.com/community/t/rithimic-paper-trading-account/380). Read together, this suggests the GUI demo (R|Trader Pro) is a smooth, well-trodden path, but a **custom-code, API-driven** paper loop against live-moving data is a murkier ask that may need a direct conversation with Rithmic or a broker's API team, not a pure self-serve flow.
- **API reality for Python.** Proprietary Protocol-Buffers-over-SSL binary protocol, no official SDK from Rithmic itself. `async_rithmic` (PyPI/GitHub, `rundef/async_rithmic`, MIT license) is genuinely the best third-party library found in this entire research pass — actively maintained (**v1.6.5 released August 3, 2026**), async-first, Python 3.10-3.13, built-in reconnection/backoff, L1 + L2 order-book streaming. [PyPI](https://pypi.org/project/async-rithmic/), [GitHub](https://github.com/rundef/async_rithmic). Genuinely headless — no desktop app required once connected, unlike NinjaTrader.
- **Cost once past any trial.** Consistently quoted across AMP/Optimus sources: **$100/month API connection fee + $25/month Trader ID fee = $125/month flat**, plus a **$0.10/contract** live trade-routing fee, plus separate CME data-package fees (roughly $3-41/month per exchange/tier depending on bundle). [AMP Rithmic pricing](https://faq.ampfutures.com/hc/en-us/articles/360060137993-Rithmic-Pricing) (search-corroborated; direct fetch blocked by 403 — moderate confidence), corroborated independently by [Optimus community pricing thread](https://community.optimusfutures.com/t/new-rithmic-pricing-12-01-20/3889). This is a real, non-trivial recurring cost — not free.
- **Reliability/reputation.** Decades-old infrastructure underlying many prop firms and retail futures brokers — a long track record by proxy. A first-hand developer writeup on the ecosystem describes Rithmic's own documentation as dated ("Windows 98-era") and support as slow ("radio silence for days"), while praising the raw tick-data quality as "unfiltered, non-aggregated" ([quantlabsnet.com writeup](https://www.quantlabsnet.com/post/the-iron-gatekeeper-the-high-cost-of-low-latency-in-the-rithmic-api-ecosystem)) — no independently-verifiable outage/breach history was found in this research pass either way; treat reliability as "mature by longevity, uneven by direct developer account," not confirmed via any uptime record.
- **Verdict.** The strongest Python library and infra of the field, and worth revisiting once real money is on the line — but not a "free this week" answer, and the trial's fit for a custom API forward-test loop (vs. GUI demo trading) is genuinely unconfirmed.

### TradeStation — disqualified by the funding gate

- **Sim/paper access.** The SIM environment is excellently designed at the API level — literally swap the hostname (`api.tradestation.com/v3` → `sim-api.tradestation.com/v3`), same auth, same semantics, clearly documented. [SIM vs LIVE docs](https://api.tradestation.com/docs/fundamentals/sim-vs-live/).
- **The gate.** TradeStation's own retail API signup page describes the onboarding path as opening an account with a promo code and **funding it with a minimum $10,000 balance** to get an API key ([tradestation.com/platforms-and-tools/trading-api](https://www.tradestation.com/platforms-and-tools/trading-api/)), consistent with the official API FAQ's "you must have a funded TradeStation account." A separate no-funding "Fintech/Developer" business track exists but targets companies going through a business-development review, not solo retail algo traders. Futures accounts specifically also carry their own **$5,000 minimum** ([BrokerChooser](https://brokerchooser.com/broker-reviews/tradestation-review/tradestation-minimum-deposit)) as a second, related gate.
- **Data cost (for later).** Real-time futures data free if the account generates ≥$40/month in futures commissions the prior month (90-day grace period for new funded accounts); otherwise ~$40/month (two $20 packages). [Cost breakdown](https://emini-watch.com/tradestation/tradestation-data-feed/).
- **Verdict.** Best-documented SIM/LIVE symmetry of anything reviewed, but the **$10,000 funding requirement to get an API key at all** is the single highest bar found in this research — disqualifying for "this week, free."

### NinjaTrader (classic NT8 / NinjaScript) — reject for headless Python

- **Sim/paper access.** Sim101 is free with no time limit for simulated trading itself, but **real-time data on Sim101 is only free for 14 days per new account**; delayed/EOD data stays free indefinitely after that. [NinjaTrader demo guide](https://brokerchooser.com/broker-reviews/ninjatrader-review/ninjatrader-demo-account).
- **The core problem.** NT8/NinjaScript is fundamentally C#/.NET, and NinjaTrader's own support forum confirms: *"NinjaTrader is not currently possible to run completely headless — you would need a Windows UI to run the platform."* [NinjaTrader forum](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1098048-headless-strategy-optimization). The Automated Trading Interface (ATI) lets external code (Python, Excel, MATLAB) trigger trades, but only by feeding a **permanently-running desktop GUI process** — not a standalone REST/WS surface. The third-party **CrossTrade** add-on (~$49/month, part of a Pro plan) does provide real REST+WebSocket access, but it still requires "the desktop... a remote execution engine," i.e., the NT8 GUI must stay running in the background regardless. [CrossTrade](https://crosstrade.io/crosstrade-api).
- **Verdict.** Worst fit of anything reviewed for "pure Python REST/WS, no desktop app, headless Windows." If the NinjaTrader *brand* is appealing, the actual path there is Tradovate (see above) — NinjaScript itself should be ruled out.

### Alpaca — confirmed, still no futures

Confirmed current as of this research: Alpaca does not offer futures trading; the retail broker has no public 2026 roadmap commitment to add it (feature requests on Alpaca's own community forum go back to 2019-2020 with no resolution). [Alpaca community forum](https://forum.alpaca.markets/t/support-for-futures-trading/1476). This is foundational context, not a candidate.

---

## Data-only fallback path (if account creation stalls)

For a pure shadow/mechanism-validation harness — no execution, just prices in, hypothetical fills logged, mirroring how the crypto twin validates plumbing against live-moving BTC data:

- **`yfinance` (`MES=F`, `MNQ=F`, `ES=F`, `NQ=F`) — the $0 pick.** Works today, no signup. Direct fetch of the `MES=F` quote page is explicitly labeled **"CME - Delayed Quote"** by Yahoo itself (exact delay minutes undisclosed, consistent with CME's standard ~10-15min non-real-time policy). Intraday granularity: 1-minute bars limited to the **last 7 days**, other intraday intervals (5m/15m) limited to the **last 60 days**. **Known risk, not hypothetical:** recent GitHub issues on `ranaroussi/yfinance` document real breakage specifically on futures symbols — [#2620](https://github.com/ranaroussi/yfinance/issues/2620) (missing/delayed data starting Nov 3 2025 across NG=F, GC=F and others), [#2635](https://github.com/ranaroussi/yfinance/issues/2635) (multi-day gap Nov 24-Dec 3 2025), [#1021](https://github.com/ranaroussi/yfinance/issues/1021) (no weekend bars for index futures, open since 2022, closed "not planned" — it's Yahoo's backend, not fixable in yfinance). This is Yahoo's undocumented endpoint shifting under the library, the same category of fragility already known from other parts of this project — needs a staleness/freshness watchdog (compare bar timestamp to wall clock every poll, alert on gap) mirroring the existing NEVER-BLIND `sight_beacon.py` doctrine, not a bolt-on afterthought.
- **Databento — good for backfill, not for a live feed.** $125 one-time free credit for new signups (historical data, ~6-month expiry) is genuinely useful for backtesting/cross-validation at near-zero cost, official Python package is well-maintained. But live/real-time CME streaming discontinued usage-based pricing in April 2025; now sits on a **Standard plan at $179-199/month** plus a separate CME non-pro exchange license pass-through (**$32.65-36.50/month**) — realistic all-in floor for a live feed is **≈$230+/month**, not the headline $32.65 figure alone. Not a free live-data path.
- **Massive (Polygon.io's 2026 rebrand) — free tier is historical-only.** A genuine $0 "Futures Basic" tier exists (CME/CBOT/NYMEX/COMEX tickers, 5 calls/min, 2-year history) but explicitly **historical data only**, no current/live quotes — same ceiling as Databento's free credit. If ever willing to spend a little, the $29/month Starter tier gets 10-minute-delayed data plus WebSockets — cheaper than every broker-side data fee found, worth remembering as a paid escape hatch.
- **CME Group direct** has no simple self-serve free API for individuals; DataMine is enterprise/licensing-agreement-oriented. Free EOD settlement prices exist on cmegroup.com but with no formal API — scrape-only, and end-of-day only.
- **Barchart OnDemand, dxFeed, Alpha Vantage, Twelve Data, Finnhub, Tiingo** — none offer a meaningful free ongoing tier with real CME futures coverage; ruled out.
- **Broker "free" data is not a shortcut.** Every broker reviewed (Tradovate, Ironbeam, IBKR, TradeStation) gates real API-reachable market data behind a funded live account — the exact same pattern repeats regardless of broker, because it is a CME redistribution-licensing rule, not a broker policy choice.
- **The actual answer: TradingView, already wired into this project.** CME futures default to a 10-minute-delayed feed on TradingView regardless of subscription tier — Plus/Premium do **not** include real-time CME data, it's billed separately no matter what plan you're on. A dedicated real-time add-on (CME + CBOT + COMEX + NYMEX bundle) costs **$7.00/month non-pro** — this is the cheapest real-time futures data path found anywhere in this research, by a wide margin, and it reuses infrastructure the project already has a live MCP connection to. (Note: this is still net-new recurring spend — small enough to be an easy call, but flagging per the cost-discipline rule rather than silently assuming it's pre-approved.)

---

## Fits our model — mapping onto `crypto_twin_core.py`'s adapter pattern

The project's own precedent (`setup/scripts/crypto_twin_core.py` + `crypto_twin_broker.py`) is the template to port, not reinvent:

- **Broker adapter = a minimal stdlib REST client, no SDK dependency.** `crypto_twin_broker.py` is `urllib`-only, mirrors `fleet_broker.py`'s generic reads (`get_account`, `get_positions`, `get_order`, `poll_fill`, `cancel_order`) and adds only the asset-class-specific pieces. A `futures_twin_broker.py` should follow the identical shape — and for Tastytrade/Tradovate/Ironbeam specifically, their REST+WS surfaces are plain enough (OpenAPI-documented or simple JSON-over-HTTPS) that this "no SDK, stdlib only" convention is realistic to keep, exactly like the existing pattern. Rithmic is the one candidate where hand-rolling the protobuf wire format is impractical — `async_rithmic` would be a justified, explicit exception to the no-SDK convention if that path is ever taken.
- **Order placement gated behind an explicit `live=True`.** `crypto_twin_broker.place_crypto_order()` refuses to fire unless `live=True` is passed explicitly; read-only calls (account/positions/bars) never require it. Same shape maps directly onto a futures adapter — trivial to carry over.
- **Dedicated, gitignored secrets per namespace.** `crypto_twin_broker.py` loads creds from its own `automation/state/crypto-twin/secrets.json`, deliberately never sharing keys with the existing fleet/core SPY accounts (explicitly to avoid corrupting per-arm equity attribution). A futures twin needs the identical isolation — its own `automation/state/futures-twin/secrets.json`, never touching `.mcp.json` or the fleet accounts.
- **Easier fit than crypto for `risk_gate.check_order`, not harder.** The crypto twin had to invent a "whole-number proxy unit" workaround because `risk_gate.check_order`'s qty/premium math assumes integer option contracts, but BTC qty is fractional. **Futures contracts are whole-number quantities by nature** (like options, unlike crypto) — a futures twin should be able to call `risk_gate.check_order` with real contract counts directly, no proxy-unit indirection needed. This is a genuine simplification versus the crypto precedent.
- **`exit_manager.ExitState` / `plan_exit_actions` reused verbatim.** The crypto twin's percent-based exits (structure stop mapped to a chart level, catastrophe cap as a % adverse move, TP1 partial + ratchet-to-breakeven, chandelier-trailing runner) already map cleanly onto a spot price the same way SPY's options premium does. A futures price (MES points) is yet another spot-like series — same shape, different tick size/multiplier ($5/point for MES) to thread through the sizing math, no exit-logic fork needed.
- **Kill-switch anchoring needs a deliberate choice, not a copy-paste.** The crypto twin's `kill_switch` is UTC-day-anchored (matches BTC's true 24/7 nature). SPY's production kill-switch is ET-day-anchored (matches RTH). Futures trade nearly 24 hours but still have a defined CME session/settlement boundary (typically ~5pm ET rollover) — worth an explicit decision on which anchor a futures twin should inherit rather than defaulting to either existing pattern by accident.
- **Signal/bar plumbing is already asset-agnostic.** `crypto.lib.{bar,bar_reader,ribbon,levels}` operate on generic OHLCV and don't know or care that the crypto twin feeds them BTC — a futures adapter would feed the same detectors MES/MNQ bars sourced from TradingView (real-time, $7/mo) or yfinance (delayed, $0) with no detector-side changes.
- **Don't force `heartbeat_core.py` to generalize.** The crypto twin's own docstring explicitly rejected reusing `heartbeat_core.py` directly (it's SPY-RTH-options-entangled: pandas RTH filtering, 15 SPY-specific gates, PDT, option-premium economics) and instead built a sibling module. A futures twin should follow that same precedent — a new `futures_twin_core.py` sibling, not a forced fit into the SPY engine.

---

## Gotchas — the things that bite a headless 24/7ish Windows loop specifically

- **CME data licensing in "demo" is a licensing rule, not a broker choice.** Every broker reviewed here (Tradovate, Ironbeam, IBKR, TradeStation, Rithmic) gates real-time market data delivered *through their own API* behind either a funded live account, a separate paid data add-on, or both — because CME's redistribution-agreement rules key off "is this API consumer receiving real-time data," not "is the account funded/live." Picking a different broker will not make this go away. The only escape hatch found: source real-time data from somewhere already licensed for it (TradingView's $7/month non-pro CME package, already wired into this project) and use the broker purely for order execution — independently rediscovered by Tradovate's own developer community as their standard workaround.
- **Session-token expiry patterns vary a lot, and matter for an unattended daemon.** Tastytrade: 15-minute access token, non-expiring refresh token, SDK v12+ auto-refreshes — best-behaved of the field for a set-and-forget loop. Tradovate: token behavior is inconsistently reported (docs vs. ~1-hour practical expiry per user reports) and every WebSocket connection hard-caps at **24 hours** regardless of activity — the client must renew proactively AND expect to reconnect at least daily, not just on error. IBKR: the session lives inside the whole TWS/Gateway *application process*, which IBKR itself designs to restart daily (maintenance window ~11:45pm-12:45am ET) and expects a fresh login weekly — solved via IBC's autologin + autorestart, not something to hand-roll from scratch.
- **WebSocket keepalive needs differ sharply.** Tradovate requires an explicit application-level heartbeat frame (`[]`) roughly every **2.5 seconds** or the connection drops — stricter than most APIs, needs a dedicated timer, not just relying on TCP keepalive. `async_rithmic` bakes reconnection/backoff into the library itself, less for the caller to hand-roll. Tastytrade's WS is used mainly for account/data streaming alongside the REST order path.
- **"Headless" is not equally true across the field.** Tastytrade, Tradovate, Ironbeam, and Rithmic's REST+WS APIs genuinely need no local desktop process — the cleanest fit for a scheduled 1-minute Python loop. Interactive Brokers needs a lightweight local TWS/Gateway process (scriptable via IBC, well-trodden, but still a process to supervise). NinjaTrader needs its **full desktop GUI** alive at all times regardless of API path chosen — disqualifying for a genuinely headless box.
- **Rate limits are real but under-documented for most of these.** Ironbeam: ~15 req/sec, bucketed, some users see tighter effective throttling in practice. Tradovate: no precise published number, community reports of throttling under heavy polling. IBKR: long-standing, well-documented pacing-violation rules with mature community tooling already built around them. Build conservative client-side throttling into any new adapter regardless of the vendor's stated ceiling.
- **Marketing "free demo" and "free API" are usually two different products.** The single most repeated pattern in this research: the GUI/platform demo is genuinely free and full-featured, while *programmatic* API access to that same demo environment is a separate tier — sometimes paid (Ironbeam $249/mo, TradeStation's $10K funding gate), sometimes just funding-gated (Tradovate's contested $1,000+$25/mo claim). Verify the literal question — "can I get raw API keys, for free, without funding anything" — directly with support chat before writing code against any vendor's marketing page.

---

## Plain recommendation

**This week:** stand up the Tastytrade sandbox (`developer.tastytrade.com`) for order-placement/mechanism plumbing — $0, self-serve, best-behaved token refresh of the field — wired to TradingView (already connected, $7/month CME real-time add-on if the free 10-minute delay proves too slow for signal timing) for the actual chart/signal leg. This sidesteps every broker's real-time-data paywall in one move. First concrete action inside that setup: confirm futures trading permission actually works in the sandbox without the live-side 1-3 day approval delay — that's the one open question standing between "works today" and "needs a workaround."

**In parallel, start the Interactive Brokers paper account application.** It is not instant, so there is zero cost to starting the clock now. IB is the most durable choice for when real money is proven — cheapest micro commissions found ($0.25/contract), the most mature and widely-used Python library (`ib_async`), and a well-solved headless-Windows pattern (IBC + Task Scheduler).

**If Tastytrade's futures permission turns out blocked or slow even in sandbox**, fall back immediately to a pure data-only shadow harness on `yfinance` (`MES=F`/`ES=F`) — $0, works today, same "never-blind" staleness-watchdog discipline the crypto twin already uses — while the IB application clears in the background.

**Do not spend engineering time on Ironbeam or TradeStation** for the "this week, free" goal — both confirmed, from their own documentation, to gate real API access behind $1,000 and $10,000 funded accounts respectively. **Revisit Rithmic** once real money is actually on the line and its $125/month + $0.10/contract is worth paying for the best tick data and Python library found in this research — not before.

**What would change this verdict:** a direct confirmation from Tradovate support that demo-only API keys are genuinely free and include real-time data (contested above, not resolved by public sources) would move Tradovate to the top spot, since it would be the only candidate offering free real-time data through the API itself rather than needing the TradingView bring-your-own-data workaround. That is a 5-minute support-chat question, not a research gap that needs more searching.

---

# 2026-08-21 UPDATE — 3-agent re-survey (fold, not a new doc)

> Trigger: J, live during the 08-21 session, after watching theta eat a correct directional
> call ("this is why I want to simultaneously trade futures"). Three Sonnet web agents:
> Tastytrade approval steps · broker landscape ranked · demo-API/prop routes.
> This section RESOLVES two of the 08-09 open questions and supersedes the 08-09 verdict.

## Resolved vs 08-09

1. **Tastytrade sandbox futures: CLOSED — NO.** The 08-09 "first thing to test" is settled
   twice over: our own `futures_broker_probe.py` (cert acct 5WW73759, `is_futures_approved:
   false`) and their developer docs ("certification environment currently only supports
   equity and equity option trading"). The 08-09 pick ("start this week: Tastytrade
   sandbox") is DEAD for futures. Production API DOES place futures orders (QuantConnect
   integration docs confirm) — but with no sandbox rehearsal and reportedly no futures
   market data over the API (UNVERIFIED), the first API futures order would be live and cold.
2. **IBKR runner-up: DEAD.** J was denied by IBKR's suitability gate — the one broker in the
   survey structurally built to deny. Paper requires an approved live account; reapplying
   with the same financial profile risks the same result. Removed from the path.
3. **Tradovate wildcard: PROMOTED to primary, one check outstanding.** 2026 sources:
   email-only demo signup, no card, REST (`demo.tradovateapi.com/v1`) + WebSocket on the
   SAME API as live, sim fills against a real order book, $50 MES day margin, $0 account
   minimum, tiered commissions $0.09–$0.39/side. The 08-09 conflict (staff quote: API needs
   $1,000 funded + $25/mo) vs marketing (free demo API) is STILL the open question —
   specifically whether demo API access survives past the 14-day trial. The 5-minute
   support-chat ask stands: "can I get demo.tradovateapi.com credentials without funding a
   live account, and do they persist past 14 days?"

## New findings (2026-08-21 agents)

- **Tastytrade futures enable, step-by-step (J's ask):** my.tastytrade.com → account
  settings → Trading Preferences/Permissions → Futures → Enable ("The Works" tier) →
  questionnaire (experience/income/net worth — answer with the real 0DTE track record) →
  risk disclosures → 1–3 business days (timing UNVERIFIED). IBKR denial does not
  cross-propagate; per-broker underwriting. Micro-only intraday margin informally ~$2,500
  net-liq (UNVERIFIED — one support-chat question before applying); $25K figures apply to
  IRA/full 4x tier, likely not micros-in-margin. Micros $0.75/side + exchange fees.
  Intraday margin window ends 15:00 Chicago; past that = full SPAN.
- **Broker ranking for $5K + Python bot + low friction:** 1) Tradovate 2) AMP/Rithmic
  (best infra, but $125/mo flat = ~2.5%/mo drag on $5K — revisit only at real size)
  3) TradeStation (OAuth2 REST WebAPI + Python SDKs; key numbers UNVERIFIED).
  REJECT: Robinhood (futures API "coming soon"), Schwab (no retail API), Webull (MES day
  margin $268.73 ≈ 5x Tradovate), Plus500 US (no evidence of an order API), IBKR (above).
- **Prop/funded route: REJECTED for this engine's shape.** Even the friendliest (Topstep)
  prohibits VPS/unattended automation — precisely what a scheduled-task engine is. Apex
  restricts fully-autonomous entry+exit. MyFundedFutures permits algos (July 2025 policy)
  but the structural read stands: ~78–85% of evals fail, only ~7% of funded accounts ever
  see a payout, and fee-churn firms have collapsed before (My Forex Funds, $310M). This is
  an eval-fee business first. Gate any future prop attempt on the automation policy IN
  WRITING, not marketing pages.
- **CME data-fee trap (confirmed mechanism):** streaming quotes THROUGH a broker API can
  trigger CME's sub-vendor ILA — $290–500/mo at Tradovate — independent of the $10-20/mo
  retail UI rate. The dodge, confirmed by Tradovate's own support: broker API for ORDERS
  ONLY, price data from our own feeds (TradingView Plus + the existing 5-min poll). This is
  already our architecture; keep it.

## Superseding verdict (2026-08-21)

1. **NOW ($0, no approval):** J creates a Tradovate demo (email-only signup — account
   creation is J's, never Claude's). Wire `futures_mirror_shadow.py` to place its would-be
   orders into the demo via REST — upgrades mirror evidence from delayed-yfinance-sim to
   real-order-book sim fills, on the same API any later live account would use. First
   settle the persistence question via support chat.
2. **PARALLEL (1–3 days):** J submits the Tastytrade futures application (steps above) —
   it costs nothing, the account exists, and it gives a second live-capable path.
3. **REAL MONEY (later, needs J per OP-0 #1):** decided AFTER the demo mirror produces
   evidence; Tradovate leads on margin/commissions/API-continuity, Tastytrade on
   account-already-exists. Not a today decision.
4. **Data:** never stream quotes via broker API (ILA trap). Orders-only. Own feeds.
