# Futures EOD Flatten — 15:55 ET Safety Net

NON-INTERACTIVE. Fires 15:55 ET weekdays (after Futures_EodFlatten trigger).
Runtime target: < 60 seconds.

DO NOT use ScheduleWakeup, AskUserQuestion, or any prompting tool.

---

## Purpose

Safety net for any open futures position (MNQ or MES) not closed by the futures heartbeat's
15:50 time stop. Hard rule: flat by EOD on all futures positions. This task uses TT sandbox
(Tastytrade watch-only mode) to close any lingering position.

This is NOT the SPY 0DTE EOD flatten — see `automation/prompts/eod-flatten.md` for that.

---

## Step 0 — pre-flight

1. Read `automation/state/futures/position.json`.
2. Read `automation/state/futures/risk.json` — check kill-switch state.
3. Get today's date in ET (`YYYY-MM-DD`).
4. Confirm it IS 15:55–16:05 ET (the EOD flatten window).

---

## Step 1 — check open position

1. Read `automation/state/futures/position.json`.
   - If `"side": "flat"` or `null`: log `FUTURES_EOD_FLATTEN_NOOP` and exit (nothing to close).
2. If position is open: proceed to Step 2.

---

## Step 2 — cancel_all open orders, then flatten

**CRITICAL: cancel_all open contingent orders FIRST before placing the flatten market order.**
Leaving a bracket leg live while placing a market close causes a double-fill (opens a new position).

Actions:
1. Call `cancel_all` (TT sandbox order cancel) — cancels any bracket/stop/limit legs.
2. Log `FUTURES_CANCEL_ALL instrument={instrument} reason=eod_flatten`.
3. Place a market close for the full open qty:
   - Instrument: value from `position.json` (`MNQ` or `MES`)
   - Side: opposite of the position side (LONG → SELL, SHORT → BUY)
   - Qty: full open qty
   - Type: market order

---

## Step 3 — verify flat

1. Read updated `automation/state/futures/position.json` (or query TT sandbox state).
2. If still shows open position after close attempt:
   - Log `FUTURES_EOD_FLATTEN_PARTIAL — manual intervention required`.
   - Write `automation/state/futures/risk.json` with `{"kill_switch": true, "reason": "FUTURES_EOD_FLATTEN_FAILED", "at": "<ISO>"}`.
3. If flat: log `FUTURES_EOD_FLATTEN_COMPLETE instrument={instrument} exit_px={price}`.

---

## Step 4 — update state and journal

1. Write `automation/state/futures/position.json`:
   ```json
   {"side": "flat", "updated_at": "<ISO>", "reason": "EOD_FLATTEN"}
   ```
2. Append to `journal/futures/{today}.md`:
   ```
   ## EOD Flatten (15:55 ET)
   - Instrument: {instrument}
   - Side closed: {side}
   - Exit px: {price}
   - Reason: EOD_SAFETY_NET
   ```
3. Log to `automation/state/futures/logs/eod-flatten-{today}.log`.

---

## Constraints

- This task ALWAYS runs, even on zero-trade days (NOOP path is fast).
- NO new positions. This is a close-only operation.
- NO ScheduleWakeup or CronCreate.
- If TT sandbox unreachable: write `futures/risk.json` kill-switch and log the failure.
- Total runtime: < 60 seconds.
