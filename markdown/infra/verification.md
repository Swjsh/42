# MCP Verification

After install, run these in Claude Code with Gamma. Don't proceed to trading until both pass.

---

## Alpaca paper — sanity checks

Ask Gamma (in Claude Code):

1. "Gamma, call the Alpaca MCP and show me my paper account info."
   - Expected: account ID, equity (starts at $100K paper unless reset), buying power, status `ACTIVE`.
   - **Confirm equity matches what you set the paper account to.** If it's $100K but our project assumes ≤ $5K, reset the paper account in Alpaca's UI to match (or override the size in `risk-rules.md` and re-do the math — but you should match reality).

2. "Gamma, fetch the SPY option chain for next Friday's expiry."
   - Expected: a list with strikes, bid/ask, IV, delta, gamma, theta, vega. If Greeks are missing, the MCP tool may not surface them — note which fields are available and we work with what we have.

3. "Gamma, place a limit BUY for 1 SPY [next Friday] 500c at $0.01 (intentionally bad price so it doesn't fill)."
   - Expected: order accepted, status `new` or `accepted`.
   - Then: "Gamma, cancel that order."
   - Expected: order canceled.
   - This proves end-to-end order routing on paper.

If any of those fail: re-check the API keys, paper-vs-live flag, base URL.

---

## TradingView — sanity checks

1. "Gamma, run `tv_health_check`." (or whatever the MCP names it)
   - Expected: connection OK, debug port reachable.

2. "Gamma, get the current SPY price and 1-min candle data from TradingView."
   - Expected: a recent quote. If TradingView isn't running with the debug flag, this fails.

3. "Gamma, list the indicators currently on my SPY chart."
   - Expected: VWAP, EMAs, whatever you have.

If any fail: confirm TradingView desktop is running with `--remote-debugging-port=9222`, the port matches the MCP env var, and the MCP process didn't crash on startup (check `claude` logs).

---

## Log it

Once both pass, add a row to the CLAUDE.md update table with the date, the package versions, and a one-line "verified" note.

---

## If MCPs misbehave mid-session

- Restart the MCP process before restarting Claude Code (cheaper).
- Restart Claude Code if needed.
- Restart TradingView desktop if its debug port stops responding.
- Don't trade until verification passes again.
