<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=2.388s | action=forage_entry_spike_nbbo_source -->
<!-- reason: Autopsy T-AUTOPSY-H-2026-09-01 (entry spike, median +0.105 paid above min low) is MED and proposed, but we have no tooling to even measure it next session — forager on a concrete defect-bounding data need is higher-value than another ideation round (queue.md flags NLWB pullback already killed twice). Also rotates verb (forager not used recently in tail) and avoids the banned critic/validator/coder patterns. -->

**Selected Source:** Polygon.io (Free Tier)

*   **Source URL:** `https://polygon.io/docs/options` (Free tier endpoint: `/v3/quotes/{optionsTicker}` or WebSocket options feed).
*   **Auth / Cost:** Free tier. Requires a standard API key (free registration). Rate limit: 5 API requests per minute for REST endpoints, though historical/delayed data access varies; the real-time WebSocket free tier covers delayed SIP feeds depending on the subscription, but for exact-minute historical autopsy replay, their free REST quotes historical endpoint or basic tier is standard. *Correction for sub-second real-time needs:* Polygon’s free tier provides end-of-day and limited real-time/delayed WebSocket access. For precise sub-second historical ticks, Theta Data's Free Tier is the superior match.

**Revised Best Candidate:** **Theta Data (Free Tier / Terminal)**

*   **Source URL:** `https://www.thetadata.us/`
*   **Auth / Cost:** Free (requires downloading their local terminal client or using their free API tier). Zero cost for basic delayed/historical data tiers. Rate limits: Generous local loopback limits via their desktop terminal app (no strict HTTP rate limits for local API calls).
*   **Resolution Field:** The `/v2/hist/option/quote` endpoint returns exact arrays of `ms_of_day`, `bid_price`, `bid_size`, `ask_price`, and `ask_size`. This directly resolves the exact printed NBBO at `signal_minute` (down to the millisecond).
*   **Coverage:** Full RTH coverage from 09:30:00 to 16:00:00 ET for all SPY and /ES options chains, providing the sub-second tick granularity needed to audit `median_paid_above_min_low = 0.105` slippage.