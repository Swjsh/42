# 01-02 SUMMARY — Alpaca Retry Instructions

**Status:** COMPLETE

## What was built

### automation/prompts/heartbeat.md (EDITED — Safe)
Three retry points added:
1. **Step 0b self-test** (`get_account_info`): 3-retry exp-backoff (2s wait, log `ALPACA_RETRY attempt=N`).
2. **FLAT_VERIFIED gate** (`get_all_positions`): 2-retry backoff before treating as `CONNECTIVITY_RED`.
3. **Bracket order** (`place_option_order`): 3-retry backoff; on exhaustion log `ALPACA_RETRY_EXHAUSTED`, emit `ERROR_ALPACA`, do NOT write phantom ENTER row.

### automation/prompts/aggressive/heartbeat.md (EDITED — Bold)
Two retry points (Bold heartbeat has no formal Step 0b self-test):
1. **Flat check** (`get_all_positions`): 2-retry backoff, log `FLAT_VERIFY_RETRY` / `CONNECTIVITY_RED node=FLAT_VERIFIED_BOLD`.
2. **Bracket order** (`mcp__alpaca_aggressive__place_option_order`): 3-retry backoff, same `ALPACA_RETRY_EXHAUSTED` + no-phantom-order guarantee.

## Verification passed
- `grep -c "ALPACA_RETRY" heartbeat.md` → 4 ✓
- `grep -c "ALPACA_RETRY" aggressive/heartbeat.md` → 3 ✓
- No Safe tools in Bold prompt / no Bold tools in Safe prompt ✓
- TV_FALLBACK blocks from 01-01 intact in both files ✓
