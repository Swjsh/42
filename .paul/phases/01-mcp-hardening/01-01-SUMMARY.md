# 01-01 SUMMARY — TV Fallback + Watchdog

**Status:** COMPLETE

## What was built

### automation/scripts/ribbon_cli.py (NEW)
CLI wrapper for `ribbon_fallback.compute_ribbon()`. Accepts a JSON array of close prices
as argv[1], outputs ribbon JSON (stack/price/ema_fast/ema_pivot/ema_slow/spread_cents/
bars_used/source). Exit 0 on BULL/BEAR/MIXED, exit 1 on UNKNOWN (too few bars) or error.

### automation/prompts/heartbeat.md (EDITED)
- `TV_DATA_LIVE` gate extended with **TV FALLBACK (Layer-1a)** procedure:
  on TV error/stale → call `mcp__alpaca__get_stock_bars(SPY, 5Min, limit=60)` →
  run `ribbon_cli.py` with closes → use fallback ribbon for all downstream checks →
  log `TV_FALLBACK_ACTIVE`. Only emit `SKIP_TV_DATA_STALE` if fallback also fails.
- "SPY 5m + ribbon" section: added explicit trigger clause for both `data_get_ohlcv`
  and `data_get_study_values` errors → route to TV FALLBACK, suppress `ERROR_TV` until
  fallback also fails.
- ACTIONs line updated: added `ALPACA_RETRY_EXHAUSTED` and modifier tokens
  `TV_FALLBACK_ACTIVE TV_FALLBACK_FAILED ALPACA_RETRY`.

### automation/prompts/aggressive/heartbeat.md (EDITED)
Same TV FALLBACK block added to "SPY 5m + ribbon" section, using Bold-scoped
`mcp__alpaca_aggressive__get_stock_bars`. ACTIONs line updated.

### setup/scripts/run-tv-watchdog.ps1 (EDITED)
Hung-bridge detection added inside the RTH heartbeat-freshness block: when
`$cdpReady` is true AND `$ageMin > 6`, sets `$tvAction = "relaunch_hung_bridge"` and
force-relaunches TV via `launch_tv_debug.ps1 -Kill`. Closes the "port alive but MCP
tools frozen" gap that the CDP port check can't see.

## Verification passed
- ribbon_cli.py: 51 values → exit 0, valid JSON ✓
- ribbon_cli.py: 3 values → exit 1, UNKNOWN stack ✓
- ribbon_cli.py: empty array → exit 1, stderr message ✓
- `grep -c "TV_FALLBACK" heartbeat.md` → 3 ✓
- `grep -c "TV_FALLBACK" aggressive/heartbeat.md` → 2 ✓
- Safe/Bold scope isolation: no cross-contamination ✓
- `backtest/tests/test_ribbon_fallback.py` → 11/11 passed ✓
