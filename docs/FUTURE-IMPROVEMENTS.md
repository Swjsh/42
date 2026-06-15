# Future improvements — queued for after current sprint

> Created 2026-05-10 per J's "build slow and steady, don't get ahead of ourselves" guidance.
> Each item has a clear trigger to start work, a scope, and a rough estimate.

## High value, deferred

### 1. Bullish-side grinder optimization
- **Trigger:** when J has 3+ live BULLISH winners documented in `journal/trades.csv`
- **Scope:** mirror the 5-stage bearish pipeline (qty/stop/TP1 per quality tier) for bullish triggers
- **Estimate:** 1 day of dev + 24h grinder run
- **Note:** First-pass bullish grinder ALREADY built today (2026-05-10) using floor protection ("do no harm to bearish wins") since no J bullish source-of-truth exists yet. Once J has 3 wins, swap to J-edge primary scoring.

### 2. Sweep the 23 unexplored knobs
Current grinder varies 7 knobs. Unexplored (rough list):
- Strike offsets per quality tier (only OTM-2 tested + reverted; could explore OTM-1, ITM-1, etc per tier)
- `no_trade_window` start/end times (current 14:00-15:00 fixed; sweep alternatives)
- `f9_vol_mult` per tier (currently 0.7 globally)
- `RIBBON_SPREAD_MIN_CENTS` per tier (currently 30 globally)
- `LEVEL_PROXIMITY_DOLLARS` (currently $0.50)
- `CONFLUENCE_TOLERANCE_DOLLARS` (currently $0.30)
- `MIN_PREMIUM_FOR_LEVEL_TIERS` (currently $0.50)
- `time_stop_minutes_before_close` (currently 10 = 15:50 ET)
- `tp1_qty_fraction` per tier (currently 0.5 globally)
- ELITE tier specifics (qty=10, stop=-15%, tp1=+50% are hardcoded — should sweep)
- TRENDLINE quality threshold (which trigger combos qualify)
- `min_swings` for trendline (currently 3)
- `lookback_bars` for trendline (currently 60)
- Wick-rejection thresholds (currently 50%/$0.15/$0.10)
- VIX_BEAR_THRESHOLD (currently 17.30)
- VIX_BULL_LOW_THRESHOLD (currently 17.20)
- VIX_BULL_HARD_CAP (currently 22.0)
- `BREAKDOWN_VOL_MULT` (currently 1.3)
- Quality-rank thresholds (when does ELITE become SUPER, etc.)
- Per-quality 45-min gap rule (currently global)
- Day-trade count limits (currently always-pass)

- **Trigger:** after Monday market open + first week of live data validates current params work
- **Scope:** stage-6 grinder iterating one tier at a time
- **Estimate:** 2-3 days of dev + 1 week of grinder runs (sequential, not parallel — too many combos)

### 3. Real OPRA fills validation on top candidates
- **Trigger:** before any params.json bump
- **Scope:** re-run top-3 v15-final candidates with `simulator_real` (real OPRA cached fills) instead of BS sim, compare deltas
- **Estimate:** 4 hours
- **Note:** BS-sim discrepancy on 5/01 already documented; this would extend the check to more days

### 4. Walk-forward validation (proper cross-validation)
- **Trigger:** when current pipeline finishes
- **Scope:** train on rolling 6-month windows, validate on next 1-month, repeat across 16 months
- **Estimate:** 1 day dev + 4h run
- **Why:** catches overfit better than single train/test split

### 5. Setup expansion beyond ribbon_ride
- **Trigger:** when J develops named patterns for new setups (e.g. "VWAP_RECLAIM_FADE", "OPENING_DRIVE_CONTINUATION")
- **Scope:** add new setup name to `strategy/playbook.md`, then grinder optimization
- **Estimate:** 1 day per new setup

## Lower value, brainstorm only

### 6. Multi-timeframe confirmation (5min + 15min ribbon)
- 15min HTF stack already used as score modifier — could promote to hard filter
- Risk: more conservative = fewer trades
- Estimate: 4h

### 7. Greeks-aware exits (theta-decay aware)
- Currently exits use premium % only
- Could exit when delta < threshold (deeply OTM 0DTE = no upside)
- Estimate: 2 days

### 8. Multi-account portfolio sizing
- When account scales past $25K, add a second account for risk diversification
- Way out — only relevant if live trading goes well for 6+ months

---

## NEW 2026-05-13 evening — added from tonight's research findings

### 9. v15 ACTIVATION (T50d) ✅ DONE 2026-05-13 23:30 ET
- J authorized "v15 can go live that is chill lets let er rip". Subagent shipped 7 file changes.
- `params.json#rule_version="v15"`, `heartbeat.md RULE_VERSION="v15"`, `premarket.md RULE_VERSION_EXPECTED="v15"`, all 4 pin-chain files synced.
- v14 backup preserved at `automation/prompts/heartbeat-v14-prod-backup.md` for <60s revert.
- First live session 5/14 09:30 ET (Thursday, jobless claims day).
- **Doctrine ref:** `docs/V15-ACTIVATION-2026-05-13.md`

### 10. v14e grinder silent-death root cause (T39) ✅ FORENSICS DONE 2026-05-14 03:20 ET
- **Forensics doc:** `docs/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md` (Fire #23).
- **Root cause:** pythonw.exe + Windows multiprocessing.spawn → silent OOM kill after ~50 combos × 4 workers × ~150MB master CSV per worker = ~2.5GB committed. Status="running" in progress.json + last_update 17+ hours stale = silent death signature.
- **NOT cause:** code bug in evaluator (try/except catches all Python exceptions), data corruption, deadlock.
- **Mitigations queued T70-T74** (see item 19 below).
- **Production impact:** ZERO. v14_enhanced is RESEARCH-ONLY; v15 is what's live.

### 11. T41 retire BS sim entirely (deferred from tonight)
- **Trigger:** after T50d v15 activation + 1 week of live v14_enhanced data confirms parameter stability
- **Scope:** refactor `simulator.py` → thin wrapper around `simulator_real.py`. All evaluators move to real-fills. Adds hard dependency on warm OPRA cache.
- **Caveat:** 20-30x slowdown per combo; grinders take longer; may need batched OPRA pre-fetch
- **Estimate:** 4-8h refactor + 1 day grinder runtime impact

### 12. Level-detection expansions (T51-T60 from KEY-LEVELS-DEEPDIVE)
- **T51 ✅ DONE 2026-05-13** — Globex H/L (overnight 18:00→09:30 session) auto-detected
- **T52 ✅ DONE 2026-05-13 23:48** — daily/weekly/monthly opens (today RTH open, week open, prior week close, prior month close)
- **T53 ✅ DONE 2026-05-16 evening** — Volume Profile POC for prior-day RTH session (high-volume node = magnet). `_compute_poc_prior_day()` in `backtest/lib/levels.py`.
- **T54 ✅ DONE 2026-05-17** — Smooth touch_score: log2 curve `min(0.5 * log2(n+1), 2.0)` in `backtest/lib/level_strength.py`. `StrengthComponents.touch_score` now `float`. 18/18 tests pass.
- **T55 ✅ DONE 2026-05-16 evening** — Cluster confluence weighting: `min(confluent_with_count, 3)` (0/1/2/3). Docs updated.
- **T56 ✅ DONE 2026-05-17** — EMA alignment scoring: `ema_alignment_score` (0-1) in `StrengthComponents`, optional `level_price`+`ema_values` params to `score_level()`. 6 smoke tests pass.
- **T57 ✅ DONE 2026-05-14 00:18** — Anchored VWAP from significant pivots (dynamic S/R)
- **T58 ✅ DONE 2026-05-14 00:48** — Liquidity sweep detection (wick-through-close-inside pattern)
- **T59 ✅ DONE 2026-05-17** — Body-vs-wick ratio gate: `is_decisive_bar(bar, min_body_ratio=0.50)` added to `backtest/lib/filters.py` using existing `_bar_geometry`. 6 unit tests added to `test_filters.py`. 43/43 filter+level_strength suite PASS.
- **T60** — TradingView MCP J-drawn-line capture → key-levels.json
- **Doctrine ref:** `docs/KEY-LEVELS-DEEPDIVE-2026-05-13.md`
- **Status: 9 of 10 shipped (T51-T59). 1 remaining (T60 — needs TradingView interactive session).**

### 13. Volume gate — slow-grind breakouts (T48) — ⚠️ PREMISE WAS WRONG
- **CORRECTED 2026-05-14 01:50 Fire #20:** the 5/13 12:20 ATH break bar values quoted in original T48 task were WRONG (queue said body $0.25 / vol 31K; reality body $0.96 / vol 536K / vol_mult 1.55x). SNIPER detector + watcher both fire HIGH-confidence on 5/13 12:20 in offline simulation. **The miss was NOT a vol-gate issue.**
- **Actual root cause:** silent zero-observations in `watcher_live.py` — 5 of 8 watchers have ZERO observations EVER (sniper / vwap / opening_drive_fade / pinfade / premarket_fail_fade). All 5 depend on `multi_day_rth`.
- **Mitigations shipped Fire #20 + #22:**
  - Per-fire diag-trail at `automation/state/watcher-live-diag.jsonl` (Fire #20 watcher_live.py patch)
  - T62 multi_day_rth invariant check (Fire #22 runner.py patch — WARNING on stderr when None during live call)
  - T63 silent-except remove (Fire #22 runner.py patch — per-watcher exceptions surface to stderr)
- **Doc:** `docs/T48-SNIPER-5-13-MISSFIRE-2026-05-14.md`
- **Still TBD:** volume gate as cumulative-N-bar alternative IS still a valid improvement (lower priority now — the immediate slot for tomorrow's CPI day is the diag-trail revealing actual failure mode).

### 14. decisions.jsonl logging gap (T49)
- **Symptom:** heartbeat ENTER decisions don't write to `decisions.jsonl` (only HOLD decisions). Missed engine activity all afternoon 2026-05-13.
- **Fix:** trace heartbeat.md → find where ENTER actions skip the ledger write → add the write. Edit production heartbeat.md (per OP 24 needs J authorization).
- **Estimate:** 30 min code + smoke test

### 15. SNIPER aggregate-only ratification (T42d)
- **Trigger:** J morning decision per `docs/SNIPER-FINAL-VERDICT-2026-05-13.md`
- **Scope:** ratify SNIPER on AGGREGATE metrics (drop OP-16 J-anchor floor). Best real-fills combo: stop=-0.10, PL=0.05/0.08, ITM-2, wide $14K over 16mo, 193 trades, 58.5% WR, edge_per_trade ~$74.
- **Recommendation:** retire SNIPER unless J wants the small marginal edge — v14_enhanced + PFF cover the same setups better.

### 16. REGIME_SWITCHER prepass macro-logic bug ✅ FIXED 2026-05-16 evening
- **Symptom:** `is_event_macro=True` for all 338 days (picks closest event regardless of distance). Only 2 days actually trigger MACRO_VETO.
- **Fix applied:** `_IS_MACRO_WINDOW_HR = 48.0` cap added to `regime_switcher_prepass.py#_macro_proximity`. `is_event_macro=True` now only when event is within 48h. Regime classifier still applies its own `macro_proximity_hr <= knobs.macro_proximity_hr` (24h default) distance gate — evaluator behavior unchanged. Fix is cosmetic (prepass JSON no longer misleading). Smoke-testable by re-running prepass — should show ~10-15 days with is_event_macro=True instead of 338.
- **Cosmetic, not blocking. Encoded in `regime_switcher_prepass.py` comment block + T37 doc.**

### 17. Per-tier sizing rules ratification
- **Trigger:** J reviews `docs/DOCTRINE-CHANGE-2026-05-13-EVENING.md` `v15_strike_offset_per_tier` table
- **Scope:** approve/refine the per-tier strike offset rules ($1K → OTM-3, $25K+ → ITM-2) + max premium % caps (40/30/25/20%)
- **Recommendation:** activate as part of v15 (T50d). The hard gate prevents 315%-leverage scenarios.

### 18. Silent watcher fleet failure (NEW Fire #21 audit 2026-05-14 02:25 ET)
- **Symptom:** 5 of 8 watchers (sniper / vwap / opening_drive_fade / pinfade / premarket_fail_fade) have **ZERO observations EVER** in `automation/state/watcher-observations.jsonl`. Only orb / bullish / v14_enhanced fire.
- **All 5 silent watchers depend on `multi_day_rth`.** Either (a) replay callers never pass it, (b) live-mode timestamp lookup fails silently, or (c) per-watcher exceptions were swallowed.
- **Mitigations shipped Fire #20-22:**
  - Diag-trail at `automation/state/watcher-live-diag.jsonl` writes per-fire bar OHLCV + multi_day_rth_rows + sniper_5d_high + signals_emitted
  - T62 stderr WARNING when multi_day_rth is None during apparent live call
  - T63 per-watcher exception surfaces with type + message
- **Verification window:** tomorrow 5/14 09:30-16:00 ET — first WatcherLive fire writes first diag-trail entry, then verify hourly. If signals_emitted > 0 → mitigation works. If still silent → drill into runner.py per-watcher branches.
- **Doc:** `docs/T48-SNIPER-5-13-MISSFIRE-2026-05-14.md`

### 19. v14e grinder mitigations T70-T74 (NEW Fire #23 forensics 2026-05-14 03:20 ET)
- **T70 (HIGH)** — Add `maxtasksperchild=10` to `mp.Pool(workers)` call in `v14_enhanced_grinder.py` L303. Forces worker recycle every 10 combos. Bounds memory commit.
- **T71 (HIGH)** — Update `setup/scripts/launch-v14-enhanced-stage1.ps1` to redirect pythonw stderr → log file (UseShellExecute=false + stdio pipes).
- **T72 ✅ DONE 2026-05-17** — `gc.collect()` after each combo result in `evaluate_v14_enhanced_combo`. Import added. ~10ms overhead, prevents fragmentation growth.
- **T73 ✅ DONE 2026-05-17** — Flush all logging handlers every 5 combos in main loop. Smoke-tested: import OK.
- **T74 ✅ DONE 2026-05-16 evening** — `setup/scripts/grinder-rss-monitor.ps1` sidecar polling RSS every 30s via WMI. Reads `current_pid` from `progress.json`, queries master + worker pythonw WorkingSetSize. Alerts RED at >2GB. CSV log to `_state/{stage}/rss-monitor.csv`. Smoke-tested: PASS.
- **All T70-T74 DONE.** T70 (maxtasksperchild=10) ✅, T71 (stderr redirect) ✅, T72 (gc.collect) ✅, T73 (log flush) ✅, T74 (RSS monitor) ✅.
- **Doc:** `docs/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md`

### 20. Premarket news.json live-refresh (NEW Fire #21 2026-05-14 02:25 ET)
- **Current state:** `automation/state/news.json` is refreshed manually by overnight wake fires using inference from data files. No live-news API integration.
- **Tomorrow 5/14 08:30 ET premarket task SHOULD re-fetch fresh headlines + jobless-claims consensus + Fed speakers** via Exa / web search if available.
- **Scope:** add Step 1f to premarket.md that does an Exa search ("today economic events", "fed speakers schedule today", "WMT earnings preview") and overwrites news.json's catalyst_summary + primary_catalyst section.
- **Estimate:** 1-2h dev. Has Exa/WebFetch dependency.

## Tracking

When starting any item:
1. Move from this file to an active task in `automation/state/research-queue.json`
2. Create matching CLAUDE.md operating principle if it changes doctrine
3. Update CHANGELOG.md row
