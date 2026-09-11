<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=1.943s | action=Forage ONE specific free data source tha -->
<!-- reason: ENTER_REFUSED is the actual RED diagnosis (not session-closed noise). 5 recent critic actions in a row have produced critique text but no diagnostic progress on this. A targeted free-data forage directly addresses whether data-staleness is the upstream cause vs broker-rejection vs local guard — the three branches produce very different fixes. Different role (forager) and different verb from the recent critic streak. -->

**Source Name:** CME Group API / Market Data Sandbox (Public Contract & Settlement Data)

**URL:** `https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/446/G` (Example endpoint for Micro E-mini S&P 500 - MES)

**Free-Tier Limits:** Completely open, public-facing unauthenticated web endpoints used by the CME website. No account, API key, or approval required. Rate limit: Standard polite scraping limits (recommend ≤ 1 request per 5 seconds).

**Diagnostic Question Answered:** Resolves **(a) vs. (b)**. By fetching the public last-trade timestamp and settlement state directly from the exchange, we can determine if our local feed's 15.1m staleness (YELLOW) is a *local client-side processing lag* or an *actual exchange-wide halt/freeze*. If CME's public feed shows active trades, the engine's `ENTER_REFUSED` is strictly a local broker-transport or sizing filter issue.

**Concrete Snippet (cURL):**
```bash
curl -s "https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/446/G" \
  -H "User-Agent: Mozilla/5.0" \
  | jq '.quotes[0] | {symbol: .securityId, lastTime: .lasTime, lastPrice: .last, volume: .volume}'
```