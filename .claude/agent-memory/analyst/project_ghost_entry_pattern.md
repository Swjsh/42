---
name: ghost-entry-pattern
description: Ghost entry pattern — decisions.jsonl shows ENTER but no Alpaca order placed. Must cross-check after every session.
metadata:
  type: project
---

Ghost entry: heartbeat generates ENTER_* reasoning text in decisions.jsonl but mcp__alpaca__place_option_order never executes.

**5/19 instance:** HB#11 10:03 ET ENTER_BEAR at 735.24. Zero Alpaca orders in either account. Root cause: rate-limit truncation mid-generation.

**Detection method:** After any session, cross-check every ENTER_* in decisions.jsonl against Alpaca order history. Any ENTER without a matching order_id is a ghost entry.

**Validator queued:** `_validator-inbox/2026-05-19-ghost-entry-detector.md` → v26_ghost_entry_detection.py

**Why this matters:** A ghost entry can cause:
1. decisions.jsonl to show "in position" when flat — EOD summary may skip EOD flatten
2. current-position.json to show a phantom open position
3. Risk calculations to be wrong if ghost position is not cleared

**How to apply:** In every future EOD audit, scan decisions.jsonl for ENTER_* actions and verify each one has a corresponding EXIT_* later in the same session OR verify Alpaca order history shows the order. If any ENTER has no EXIT and no Alpaca order: flag as ghost, add to mistakes.md, route to validator-inbox if v26 is not yet shipped.
