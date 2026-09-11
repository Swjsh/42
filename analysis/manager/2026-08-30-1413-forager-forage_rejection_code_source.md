<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=1.52s | action=forage_rejection_code_source -->
<!-- reason: Repeated critic/strategist turns this week have saturated the ideation/critique lanes; the futures RED state is the highest-value unresolved diagnostic and we lack internal visibility on ENTER_REFUSED root cause. Foraging a free rejection-code source directly unlocks a fix path. This is a different verb (forage) and a different target (broker-rejection taxonomy) than the recent critic/strategist streak. -->

* **Name:** Interactive Brokers API (TWS/Gateway) API Documentation – Order Status and Error Messages
* **URL:** `https://interactivebrokers.github.io/tws-api/message_codes.html`
* **Auth Required:** No (Public documentation)
* **Freshness:** Static / Reference documentation
* **Field Answering Question:** Error code integers (e.g., `202` for "Order rejected because of insufficient margin", `103` for "Duplicate order id", `399` for exchange/broker rejection messages).
* **Verdict:** Would have caught the silent-fail by mapping the specific IBkr API rejection error codes emitted during the 23 refused sessions to differentiate broker risk gates from exchange closes.