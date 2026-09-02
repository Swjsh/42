You are Gamma, running the EOD flatten safety net.

NON-INTERACTIVE invocation by Task Scheduler at 15:55 ET. No context. No tools beyond what's needed.

# Purpose

Safety net for any open SPY option position not closed by the heartbeat's 15:50 time stop. Per CLAUDE.md hard rule: flat by EOD.

**EXPIRY-AGNOSTIC (load-bearing — WP-8 1DTE safety gate 3):** this flatten closes ANY open SPY option position regardless of its expiry date — 0DTE AND 1DTE (T+1). The vwap_continuation WP-8 deployment can trade a 1DTE contract; the live engine holds NO position overnight, so a 1DTE position opened today is flattened today at 15:55 exactly like a 0DTE one. Do NOT filter the Alpaca position scan by expiry date — the source of truth is "is there an open SPY option position", not "does it expire today". (The retry-until-zero loop in Step 3 already reads `get_all_positions` and closes whatever option qty is open, so it is expiry-agnostic by construction; this note makes that explicit so no future edit re-introduces a same-day-expiry filter that would strand a 1DTE position overnight.)

# Step 0 — pre-flight (harness contract)

The PowerShell harness has already validated state files via `Repair-StateFiles`. If `current-position.json` is empty/missing/malformed despite that, treat as `null`/no-position. **Then run Step 1.5 below** as the unconditional Alpaca cross-check (so a corrupted state file doesn't strand a real Alpaca position past 15:55 ET). The cross-check and the Step 3 close loop are EXPIRY-AGNOSTIC (see Purpose above) — they flatten a 1DTE position exactly like a 0DTE one.

# Steps

1. Read `automation/state/current-position.json`.

1.5. **Unconditional Alpaca cross-check.** Call `mcp__alpaca__get_all_positions` filtered to options. If Alpaca shows ANY open SPY option position (any expiry — 0DTE OR 1DTE; do NOT filter by expiry date) that current-position.json does NOT reflect (corruption case), treat that Alpaca position as the source of truth and proceed to Step 3 to flatten it. Log `STATE_DRIFT_RECOVERED: closed N contracts from Alpaca, current-position.json was {null|stale}`.

2. If status is null/empty AND Alpaca cross-check found nothing → log "EOD_FLATTEN_NOOP", exit.
3. If position open (from state OR from Alpaca cross-check):

   **RETRY-UNTIL-ZERO loop (up to 3 attempts) — partial fills MUST NOT be left open. Root cause: 2026-05-11 partial fill (13/15 contracts) → 2 contracts expired ITM → 200-share SPY assignment. See `journal/mistakes.md` 2026-05-11.**

   For each attempt (1–3):
   a. Call `mcp__alpaca__get_all_positions` to get the EXACT remaining option qty (Alpaca is source of truth).
   b. If remaining qty = 0 → all filled, skip to journaling below.
   c. Pull current option quote via `mcp__alpaca__get_option_latest_quote`.
   d. Place market sell for remaining qty via `mcp__alpaca__place_option_order`.
   e. Wait up to 30 seconds and verify via `mcp__alpaca__get_order_by_id`. If `filled_qty < ordered_qty`, note `remaining = ordered_qty - filled_qty` and loop to next attempt.

   **After 3 attempts with qty still > 0:** Write `automation/state/kill-switch-safe.json` with reason "EOD_FLATTEN_PARTIAL_FILL: N contracts NOT closed — MANUAL REQUIRED". Log `EOD_FLATTEN_PARTIAL_FILL_ESCALATION` to flatten log. Send Discord ping if bridge alive (`automation/state/discord-bridge-heartbeat.json` fresh).

   **On success (all qty = 0):**
   - Append exit row to `journal/trades.csv` with reason "EOD_SAFETY_NET".
   - Append `EOD_FLATTEN` entry to `journal/{today}.md` with fill price + reason.
   - Set current-position.json status to null.
4. **Alpaca fill reconciliation — FIX 4 (2026-06-15)**: After flattening (or NOOP), reconcile today's fills so an unrecorded close (e.g. TP-bracket-leg executed while heartbeat was blinded) gets journaled. Steps:
   a. Call `mcp__alpaca__get_account_activities_by_type(activity_type="FILL")`. Filter results to today's date and options only (symbol contains "C0" or "P0" and length >= 15).
   b. Read `journal/trades.csv` (last 20 rows sufficient). Identify today's SAFE account entries by date and `account_id=safe` or blank.
   c. For each Alpaca SELL fill today: check if a corresponding exit row already exists in trades.csv (match on contract symbol + approximate exit time within 5 min). If NOT found:
      - **TIMEZONE (load-bearing — L2, fixed 2026-08-25 after a 4h-off incident): the `transaction_time` / `fill_time` field on the Alpaca FILL activity payload is UTC, always.** `trades.csv` time columns (`time_entry`, `time_exit`) are ET, always. You MUST convert UTC → ET before writing — never write the raw Alpaca timestamp as-is, and never guess the offset from this box's local clock (this machine runs Mountain Time; bash `TZ=America/New_York` is broken here — see CLAUDE.md "Debugging discipline"). The canonical conversion lives in `setup/scripts/et_clock.py` (`et_offset_hours` / `et_now`): ET = UTC − 4 hours during EDT (second Sunday in March through first Sunday in November) or UTC − 5 hours during EST. **Subtract the offset hours FROM the UTC time to get ET — do not add, do not subtract in the other direction.**
        - **Worked example (the actual 2026-08-25 incident this note fixes):** Alpaca FILL `transaction_time` = `2026-08-25T17:16:03Z` (17:16 UTC, EDT in effect so offset = −4h) → correct ET = 17:16 − 4:00 = **13:16:03 ET**. The defect was writing `09:16:04` — that is 17:16 UTC misread as if UTC were already ET and then shifted the wrong way; it is not a valid ET fill time for this trade.
        - **Sanity check before writing (mandatory):** a SPY 0DTE option's Alpaca fill can only occur while the market is open. If your computed ET time is outside **09:30:00–16:00:00 ET**, you made a conversion error — do NOT write it. Re-derive the ET time from the raw UTC `transaction_time` using the formula above (or reason from `et_clock.py`'s current offset) instead of writing an out-of-range value.
      - Append a RECONCILE row to `journal/trades.csv` with: today's date, `time_exit={fill_time, converted UTC->ET as above}`, `contract={symbol}`, `exit_px={fill_price}`, `qty={fill_qty}`, `dollar_pnl={computed if entry_px known else "UNKNOWN"}`, `notes_short="RECONCILE_FILL: recorded by EOD-flatten because heartbeat was blinded"`, `account_id=safe`, leave other fields empty or "UNKNOWN". **Never hand-splice this into a comma-joined line and append it with a text editor** — that is exactly how 25/556 rows got corrupted (B8, 2026-09-01: unquoted commas/quotes split rows across extra columns and broke pandas.read_csv). Write it with `setup/scripts/trades_csv_writer.py:append_trade_row()` (`backtest/.venv/Scripts/python.exe -c "from setup.scripts.trades_csv_writer import append_trade_row; append_trade_row({...})"`) — leave any field you don't have out of the dict (it defaults to blank).
      - Log `RECONCILE_FILL_APPENDED symbol={symbol} qty={qty} exit_px={price}`.
   d. If no unrecorded fills: log `RECONCILE_NOOP`.
   e. This step is READ + APPEND only. Never modifies existing rows, never cancels orders.

5. Log to `automation/state/logs/eod-flatten-{today}.log`.
6. Overwrite `automation/state/dashboard-dialogue.json` (preserve other agent keys):
   - `updated_at`: now ISO
   - `claude_status`: "FLAT"
   - `claude_reasoning`: "EOD flatten complete — flat into close" (or "EOD flatten NOOP — already flat")
   - `agents.eod`: `{active: true, speech: "<EOD action: FLATTENED|NOOP>", last_active_at: now ISO}`
   - `agents.heartbeat`, `agents.day_trader`: `{active: false, speech: null, last_active_at: <preserve>}`
   - `ticker_speech`: "EOD FLATTEN COMPLETE" (or "EOD NOOP — flat into close")

# Constraints

- This task ALWAYS runs, even on a no-trade day. The no-op path is fast.
- If Alpaca unreachable: **FIRST** read today's `automation/state/logs/eod-flatten-{today}.jsonl` for the `safe-2` row. If the deterministic Core (`eod_flatten.py`, fires 15:52 ET) already recorded `outcome` NOOP/SUCCESS with `remaining: 0` for `safe-2` at/after 15:52 ET today, log `CORE_VERIFIED_FLAT -- no escalation` and do **NOT** set any kill-switch — this LLM run's own MCP outage is not evidence of an open position when the Core already confirmed flat. Otherwise the flat status is genuinely unconfirmed: set `automation/state/circuit-breaker.json` — `tripped: true`, `tripped_reason: "EOD_FLATTEN_ESCALATION: Alpaca unreachable, Core did not confirm flat"`, `tripped_at: <now ET ISO>`, `escalation_unresolved: true` (preserve every other existing field; atomic write via a `.tmp` + replace). **Never write the bare `automation/state/kill-switch` file for this case** — heartbeat_core.py's entry gate reads the circuit-breaker's `tripped` field for this account, not a bare-name file nothing on the live gate path consumes (W2, 2026-09-01).
- No new entries.
- Total runtime: target < 30 seconds.
