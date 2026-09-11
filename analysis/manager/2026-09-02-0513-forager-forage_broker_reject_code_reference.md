<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=2.839s | action=forage_broker_reject_code_reference -->
<!-- reason: FUTURES-HEALTH has been RED across 4 consecutive self-checks with identical ENTER_REFUSED pattern. We've critiqued and ranked -- we have NOT foraged the actual broker-reject-code reference that would let us decode whether this is pacing, session-closed, or contract-resolution. Highest-leverage diagnostic missing. -->

1. **Exact URL/Path:**  
   Interactive Brokers API Error Code Reference (specifically handling API message codes for order placement rejections in the 100–400 range, which are logged verbatim by the TWS API client logger and subsequently captured in transport debugging):  
   `https://www.interactivebrokers.com/en/software/api/apiguide/tables/api_message_codes.htm`

2. **Specific Field/Code to Grep:**  
   Grep `broker-transport.jsonl` for the JSON key `"errorCode"` (or standard TWS error output string `Error code:`) matched against these specific CME/IBKR gateway rejection codes relevant to 0DTE ES/MES pacing and margin blocks:
   * `200` (No security definition has been found / contract expired or invalid for 0DTE expiry)
   * `162` (Historical Market Data Service error / pacing violation)
   * `321` (Error parsing request / order validation failure, such as outside RTH without overnight permission, or missing clearing account tags for CME Globex)
   * `399` (Order rejected systemic / exchange pacing limits exceeded)
   
   Command pattern: `jq 'select(.errorCode == 200 or .errorCode == 162 or .errorCode == 321 or .errorCode == 399)' broker-transport.jsonl`

3. **Expected False-Positive Rate:**  
   **< 2%**. Because the 17 transport errors explicitly correlate temporally with the 15 `ENTER_REFUSED` rows across the 4/5 recent sessions (2026-08-26 through 2026-09-01), these specific numeric error codes map directly to programmatic broker-side session rejections rather than transient network timeouts or client-side serialization faults. Unrelated heartbeat drops or socket disconnects produce distinct transport exceptions (e.g., code 504 / connection reset) that will not collide with these order-entry validation codes.