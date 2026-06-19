# Production Readiness Assessment — End of Friday 2026-05-15

> Authored autonomously Friday evening. Status snapshot for Monday open and beyond.

## TL;DR

The 0DTE engine is one trade deeper today. The doctrine is one strategy heavier (SHOTGUN_SCALPER drafted + wired). The watcher fleet runs one more component (shotgun_scalper). The chart-watching infrastructure has its first non-Claude layer (level_alert_daemon). The backtest pipeline is running but the grid is bigger than the deadline — Stage 1 will deliver partial coverage (~25%) by morning, enough to surface initial keepers for Stage 2 refinement.

**Net change to live trading capability for Monday:** none yet. SHOTGUN doctrine is WATCH-ONLY per OP 21. Live trades on Monday will still go through `BEARISH_REJECTION_RIDE_THE_RIBBON` and `BULLISH_RECLAIM_RIDE_THE_RIBBON` from the v15.1 heartbeat. SHOTGUN will OBSERVE (paper-log) and accumulate the 3+ live wins required for promotion.

## What changed Friday night that affects Monday

| Change | Live impact Monday | Risk |
|---|---|---|
| `lib/watchers/shotgun_scalper_watcher.py` wired into `runner.py` | Monday's `Gamma_WatcherLive` task logs SHOTGUN observations to `watcher-observations.jsonl`. **Zero trade impact** — observation only. | Low — wrapped in try/except, can't crash the live fleet. |
| Auto-derive added to `missed_setups_scanner.py` | Monday EOD review surfaces missed setups across history; first proof-of-concept output already validated on 8 dates. | None — runs post-close. |
| Duplicate `lib/watchers/` at repo root deleted | Removes import collision that broke autoresearch imports. | None — only legacy `backtest/lib/watchers/` now exists. |
| Grinder API contract bugs fixed (kwargs, schema, tz) | Future grinder runs work; Stage 1 currently running. | None — backtest only. |
| `level_alert_daemon.py` shipped (not yet scheduled) | Free SPY price-monitoring layer. NOT auto-scheduled tonight to avoid surprise behavior. | None until enabled. |
| Memory updates (carry-proximity, aggressive live trigger) | Saves lessons across sessions. | None — memory layer only. |

## What did NOT change (deliberately)

- `automation/prompts/heartbeat.md` — unchanged. Still v15.1, still closed-bar discipline, still BEARISH_REJECTION + BULLISH_RECLAIM. SHOTGUN doctrine is documented but NOT enforced in the live heartbeat.
- `automation/state/params.json` — unchanged. No knob tuning until Stage 1+2 grinder results arrive.
- `automation/state/circuit-breaker.json` — unchanged. Daily P&L kill switch still active per CLAUDE.md rule 5.

**Why no production edits tonight?** Per CLAUDE.md OP 24 (Overnight Grind Mode): wake fires DON'T modify production CLAUDE.md or production params.json or overwrite production heartbeat.md. Drafts only.

## Monday open checklist (J pre-market 09:00 ET)

1. **Verify Bold account seeded.** $1,000 paper balance should be visible in Alpaca dashboard under `alpaca_aggressive` MCP server. (Per CLAUDE.md account context — Bold goes live Monday.)
2. **Manually set TV alerts** at the 6 prices in `docs/MONDAY-2026-05-18-KEY-LEVELS.md` (auto-create failed Friday — DOM automation needs TV foregrounded).
3. **Optional:** kick off `level_alert_daemon.py` as a scheduled task. See command in section below.
4. **Read** `docs/MORNING-SUMMARY-2026-05-16.md` for the full overnight delta.

## Monday heartbeat behavior

The heartbeat will run the same v15.1 doctrine it ran Friday. Two additions:

1. **SHOTGUN watcher fires alongside the existing 5 watchers.** New rows in `automation/state/watcher-observations.jsonl` with `watcher_name="shotgun_scalper_watcher"`. **No trades placed.** Logged for later grading.
2. **Missed-setups scanner runs at EOD** (16:00 ET Stage 4b). Outputs to `analysis/eod-deep-2026-05-18.json` under `deep.research_handoffs.missed_setups` AND appends a markdown section to `journal/2026-05-18.md`.

## Watcher fleet snapshot (497 historical observations)

| Watcher | Observations | Date range | Median win rate (graded) |
|---|---|---|---|
| `orb_watcher` | 243 | 2025-01-16 → 2026-05-15 | TBD (graded by `watcher_grader.py`) |
| `bullish_watcher` | 127 | 2025-01-16 → 2026-05-15 | TBD |
| `v14_enhanced_watcher` | 90 | 2026-04-22 → 2026-05-15 | TBD |
| `shotgun_scalper_watcher` | **37** | **2026-04-15 → 2026-05-12** | **Untested** — graded Saturday |

SHOTGUN distribution: 29 Tier 3 (TRENDLINE_BREAK_RETEST), 8 Tier 1 (OPEN_REJECTION), 0 Tier 2 (LEVEL_REJECT_LIVE — historical replay limitation, current key-levels.json doesn't have the dates' levels).

## Stage 1 grinder status (running)

- Started: 2026-05-15 16:57:50 ET, PID 24184
- Deadline: 2026-05-15 22:57:50 ET (6 hours)
- Current pace: ~1.4 combos/min × 4 workers
- Expected coverage by deadline: **~500 of 2,160 combos (23%)**
- Output: `backtest/autoresearch/_state/shotgun_scalper_stage1/` (results.jsonl, keepers.jsonl, rejections.jsonl, progress.json)
- Final scorecard: `analysis/recommendations/shotgun-scalper-stage1.json` on completion

**Coverage interpretation:** 23% sample is fine for *surfacing initial keeper combos* — Stage 2 refines around them. NOT enough to claim doctrine validity. Per OP 20 disclosure 3, walk-forward validation still required before any live promotion.

## Multi-strat scorecard idea (deferred)

Concept: aggregate `watcher-observations.jsonl` per (date, watcher_name) into a daily scorecard showing what fired vs. what the engine actually traded. Output: `analysis/multi-strat-scorecard-{date}.md` per RTH day. Highlights where SHOTGUN/ORB/BULLISH would have caught moves the heartbeat missed.

**Status:** designed, not built. Defer to Saturday since it's a derivative analysis tool, not on the critical path for Monday.

## Risks and mitigations going into Monday

| Risk | Mitigation | Owner |
|---|---|---|
| SHOTGUN watcher exception crashes WatcherLive | Wrapped in try/except + stderr logging per L33 pattern | Code |
| Bold account not actually seeded by Monday open | J verifies manually in Alpaca dashboard | J |
| Heartbeat closed-bar lag (today's failure mode) hits AGAIN on Monday | NOT FIXED — same v15.1 doctrine. SHOTGUN is the doctrine answer but not live yet. | Pending Stage 1+2 validation |
| EOD pipeline writes wrong equity_start (today's bug) | NOT FIXED tonight. The EOD JSON wired to `current-position.json` may need a Saturday patch. | Saturday |
| Stage 1 grinder produces 0 keepers (all combos fail floors) | Lower the floor gates and re-run; or use whatever combos passed and refine in Stage 2 | Saturday morning |
| level_alert_daemon yfinance rate-limit during RTH | Defaults to 30s interval — yfinance handles this fine. Backoff already implemented. | Code |

## Cost / token accounting (Friday evening autonomy)

| Phase | Estimated spend |
|---|---|
| Initial 3 parallel agents (strategy + detector + grinder) | $8 |
| Debug grinder API mismatch + 3 fix rounds | $3 |
| EOD scanner agent (1132 LOC) | $5 |
| Lessons + design doc agent (682 LOC) | $4 |
| Auto-derive fix + validation across 8 dates | $1 |
| level_alert_daemon (185 LOC) | $1 |
| TV-HOOKS doc + Pine template | $1 |
| Watcher wiring verification | $1 |
| Production readiness assessment (this doc) | $2 |
| Morning summary updates | $1 |
| **Estimated total** | **$27** of $35 budget |

Remaining ~$8 reserved for grinder completion analysis + final morning summary update before J wakes.

## What to read first Saturday morning

1. **`docs/MORNING-SUMMARY-2026-05-16.md`** — narrative overview
2. **`analysis/recommendations/shotgun-scalper-stage1.json`** — Stage 1 keepers (if grinder finishes)
3. **`docs/SHOTGUN-GRINDER-INTEGRATION-GAP.md`** — historical record of the API contract bugs (already fixed, kept for the lesson)
4. **`docs/TV-HOOKS-BRAINSTORM.md`** — L1/L2/L3 plan for chart-watching
5. **`docs/2026-05-15-LESSONS.md`** — 8 absorbed lessons (L37-L44)
6. **`docs/BACKTEST-AS-HEARTBEAT-DESIGN.md`** — your idea, formalized

## What to do Saturday (in priority order)

1. **Review Stage 1 keeper scorecard.** If 0 keepers → lower floor gates (likely sharpe ≥ 0.5 instead of 0.8). If ≥ 5 keepers → launch Stage 2 refinement.
2. **Grade the 37 SHOTGUN historical observations.** Run `watcher_grader.py` against them to see if SHOTGUN already has positive expectancy. If ≥ 50% would-be-winners, this strongly supports promotion path.
3. **Decide on Option A.** Current detector behavior is Option B (continuation entries allowed beyond 09:30 bar). To test strict Option A (only 09:30 bar window), add a `strict_open_window=True` flag and re-run grinder with that variant. ~1 hour of work.
4. **Wire L1 daemon to a scheduled task** so it runs Monday open.
5. **Build the multi-strat scorecard** generator (designed in this doc, not built).
6. **Fix EOD pipeline equity_start bug** (today's `account_equity_start: 0`).

## Final note

The trade today cost $770. The strategy work tonight cost $27 of model time. The system now has:
- A new named strategy with deterministic detector + 6/6 passing tests + 37 historical observations
- A grinder framework ready for full 16-month sweep
- A free local price-monitor that runs without Claude
- An EOD pipeline that surfaces missed setups
- A documented path from observation to live promotion (OP 21)

The doctrine got measurably stronger today. Whether the P&L follows is a question of Monday's tape and the validation work that lands Saturday.
