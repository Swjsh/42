# PRE-FLIGHT READINESS — 2026-05-14 v15 first session

> Generated Fire #25 (04:14 ET 2026-05-14). v15 RULE_VERSION live across all 4 pin files. All 11 operational Gamma_* tasks Ready with correct NextRun times.

## Critical-path timeline for 5/14

| Time ET | Task | Verified |
|---|---|---|
| 08:00 | `Gamma_LaunchTV` runs `run-launch-tv.ps1` | ✅ Ready, NextRun 5/14 08:00 |
| 08:30 | `Gamma_Premarket` runs `run-premarket.ps1` → reads `automation/prompts/premarket.md` (RULE_VERSION_EXPECTED="v15") → reads `params.json#rule_version="v15"` → **PIN CHECK PASSES** → writes `today-bias.json` for 5/14 | ✅ Ready, NextRun 5/14 08:30 |
| 08:30 | `Gamma_WatcherMorningReport` runs `run-watcher-morning-report.ps1` | ✅ Ready, NextRun 5/14 08:30 |
| 09:30 | Market open. `Gamma_Heartbeat` runs `run-heartbeat.ps1` → reads `automation/prompts/heartbeat.md` (RULE_VERSION="v15"). Repeats every 3 min until 15:55 (Duration PT6H25M). | ✅ Ready, NextRun 5/14 09:30, Interval PT3M |
| 09:30 | `Gamma_WatcherLive` runs `run-watcher-live.ps1` → calls `watcher_live.py` → writes `automation/state/watcher-live-diag.jsonl` (NEW per Fire #20). Repeats every 5 min until 15:55. | ✅ Ready, NextRun 5/14 09:30, Interval PT5M |
| 15:55 | `Gamma_EodFlatten` runs `run-eod-flatten.ps1` (closes any open position) | ✅ Ready, NextRun 5/14 15:55 |
| 16:00 | `Gamma_EodSummary` runs `run-eod-summary.ps1` | ✅ Ready, NextRun 5/14 16:00 |
| 16:30 | `Gamma_DailyReview` runs `run-daily-review.ps1` | ✅ Ready, NextRun 5/14 16:30 (LastResult=124 from 5/13 — claude --print return code, non-blocking) |
| 17:00 | `Gamma_WatcherReplay` runs `run-watcher-replay.ps1` | ✅ Ready, NextRun 5/14 17:00 |
| Every 15 min | `Gamma_DiscordWatchdog` keeps bridge alive | ✅ Ready, NextRun ~5min |

## State-file readiness

| File | Current state | Will refresh? |
|---|---|---|
| `automation/state/params.json` | rule_version=v15, ratified_at=2026-05-13 | No — locked per rule 9 |
| `automation/prompts/heartbeat.md` | RULE_VERSION="v15" | No — locked per rule 9 |
| `automation/prompts/heartbeat-v14-prod-backup.md` | byte-for-byte v14 preserved | No — revert path |
| `automation/prompts/premarket.md` | RULE_VERSION_EXPECTED="v15" | No — locked |
| `automation/state/news.json` | for_session=2026-05-14, regime=post_macro_drift_day | refreshed Fire #21 |
| `automation/state/today-bias.json` | dated 5/13 | YES — premarket 08:30 ET overwrites for 5/14 |
| `automation/state/loop-state.json` | session_id=2026-05-13 | YES — heartbeat first tick at 09:30 ET resets for 5/14 (session_id != today → defaults haiku + BASE mode) |
| `automation/state/current-position.json` | status=null (no open position from 5/07 close) | YES — heartbeat writes on entry/exit |
| `automation/state/watcher-live-diag.jsonl` | does not exist yet (first WatcherLive fire creates it) | YES — first 09:30 ET WatcherLive fire writes first entry |

## Mitigations active going into 5/14

| Mitigation | Where | Effect |
|---|---|---|
| **Diag-trail** (Fire #20) | `watcher_live.py` writes `watcher-live-diag.jsonl` per fire with bar OHLCV + multi_day_rth_rows + sniper_5d_high + signals_emitted | Reveals silent zero-observations in real-time |
| **T62 invariant** (Fire #22) | `lib/watchers/runner.py` writes stderr WARNING when `multi_day_rth is None` during live call | Surfaces silent skip of 5 multi-day watchers |
| **T63 stderr unmask** (Fire #22) | `lib/watchers/runner.py` 5 except blocks write watcher-name + exception to stderr | Per-watcher exceptions visible in scheduled-task stderr |
| **T70 maxtasksperchild** (Fire #24) | `v14_enhanced_grinder.py` L303 — workers recycle every 10 combos | Bounds research-grinder memory commit (zero impact on production) |
| **T71 launcher stderr** (Fire #24) | `launch-v14-enhanced-stage1.ps1` redirects pythonw stderr+stdout to log files | Captures grinder silent-kill traceback (zero impact on production) |
| **TV CDP recovery** (Fire #19) | `setup\launch_tv_debug.ps1` re-launched TV with `--remote-debugging-port=9222` | Premarket Step 1c will reach TV chart for level audit |

## What to watch tomorrow morning

1. **08:30:01 ET** — `Gamma_Premarket` should run with LastResult=0. Verify pin check passes ("v15 matches expected v15"). Verify today-bias.json date=2026-05-14.
2. **09:30:01 ET** — `Gamma_Heartbeat` first tick. Should NOT write any LastResult > 0. Loop-state.json session_id should flip to "2026-05-14".
3. **09:30:01 ET** — `Gamma_WatcherLive` first tick. **Critical check:** `automation/state/watcher-live-diag.jsonl` should have first entry written. Look for:
   - `multi_day_rth_rows > 0` (if 0, T62 WARNING fires and we know multi_day_rth is broken)
   - `sniper_5d_high` populated (around 743.61 per news.json levels)
   - `signals_emitted` — could be 0 on the first bar (no setups yet), but should be > 0 by 11:00 ET if SPY moves meaningfully
4. **Throughout RTH** — Discord pings on `medium`/`high` confidence signals via `_queue_alert()` in watcher_live.py.

## Known anomalies (non-blocking)

- `Gamma_DailyReview` 5/13 LastResult=124 (claude --print return code, daily-review.md timed out or returned non-zero). Non-critical — daily review is post-session strategic, not real-time. Will re-fire normally tonight at 16:30 ET.
- 8 of 20 Gamma_* tasks are Disabled by design (Aggressive variants, DiscordResponder, DiscordNotify, GrinderMonitor, AR_Watchdog, MondayReadyCheck, DailyStatus, EodFlatten_Aggressive, Heartbeat_Aggressive). These aren't supposed to run in normal operation.
- v14_enhanced grinder is silent-killed (T39) — research only, ZERO production impact. T70 + T71 patches shipped for next weekend's run.

## Verdict

**5/14 PRE-FLIGHT GREEN.** All operational tasks Ready. All state files will refresh correctly on their first 5/14 fire. v15 pin chain INTACT. Diag-trail + stderr-unmask mitigations in place to surface any silent failure within 5 minutes of market open.
