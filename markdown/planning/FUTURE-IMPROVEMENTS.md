# Future improvements — queued for after current sprint

> Created 2026-05-10 per J's "build slow and steady, don't get ahead of ourselves" guidance.
> Each item has a clear trigger to start work, a scope, and a rough estimate.

## ENFORCED — params.json + orchestrator + heartbeat all updated

### [ENFORCED-1] SAFE block conf+lvl_rec afternoon — IS+$412 OOS+$176 WF=2.644 ✅
- **Ratified:** 2026-06-17 | **Fully enforced:** 2026-06-17 | **Scorecard:** `analysis/recommendations/safe_time_class_gate.json`
- **What:** Block conf+level_reclaim entries in afternoon window (14:00-15:55 ET). IS 5 trades all 100% stop; OOS 1 trade 100% stop.
- **Params.json:** `"block_conf_lvl_rec_afternoon": true` in `automation/state/params.json` ✅
- **Orchestrator:** `block_conf_lvl_rec_afternoon` kwarg in `run_backtest` ✅
- **Heartbeat:** Gate D in `automation/prompts/heartbeat.md` RIBBON CONVICTION GATE section ✅

### [ENFORCED-2] AGG block conf+lvl_rec afternoon — IS+$468 OOS+$176 WF=2.194 ✅
- **Ratified:** 2026-06-17 | **Fully enforced:** 2026-06-17 | **Scorecard:** `analysis/recommendations/agg_time_class_gate.json`
- **What:** Same gate as Safe but for AGG params. IS 5 trades all 100% stop (avg=-$94); OOS 1 trade 100% stop (-$176).
- **Params.json:** `"block_conf_lvl_rec_afternoon": true` in `automation/state/aggressive/params.json` ✅
- **Heartbeat:** Gate AGG-1 in `automation/prompts/aggressive/heartbeat.md` Time-class gates section ✅

### [ENFORCED-3] AGG block conf+lvl_rej midday+afternoon — REVERSED 2026-06-18 ⚠️
- **Originally ratified:** 2026-06-17 | **REVERSED:** 2026-06-18
- **Reversal reason:** 6-fold WF validation (item 4) showed 0/6 OOS folds benefiting from this gate. In ALL 6 rolling OOS windows, the gate hurt performance (never helped when it fired: fold2=-$495, fold6=-$67, all others=$0). 4-way A/B in 5-gate context: IS+$1,020, OOS+$67. C15 interaction: `require_bearish_fill_bar` changed the conf+lvl_rej trade composition — trades passing fill_bar are quality trades this gate then removes.
- **Params.json:** `"block_conf_lvl_rej_midday_afternoon": false` in `automation/state/aggressive/params.json` ✅ REVERSED
- **Heartbeat:** Gate AGG-2 line 281 reads params.json dynamically — picks up `false` automatically. No heartbeat edit needed.
- **Scorecard:** `analysis/recommendations/agg_wf_gate_removal_2026_06_18.json`

### [ENFORCED-4] SAFE no_trade_window 11:30-12:00 ET — IS+$10 OOS+$424 WF=247.282 ✅
- **Ratified:** 2026-06-17 | **Auto-ratified (all 4 gates pass, NOT C22 inverted)** | **Scorecard:** `analysis/recommendations/safe_no_trade_window_sweep.json`
- **What:** Block any SAFE setup where the *signal bar* falls in 11:30-12:00 ET. Entry at next bar open (11:35-12:05). Early lunch zone: morning momentum exhausted, theta not yet accelerating. n=3 IS signals blocked; n=1 OOS signal blocked. Both IS and OOS are negative — structurally bad time, not regime-dependent.
- **Evidence:** IS_delta=+$10, OOS_delta=+$424, WF=247.282, SW_hurt=0/4, ANCHOR=PASS. Dropped IS n=3 (all near-zero P&L). OOS avg per dropped trade = -$424.
- **NOT C22 inverted:** IS avg=-$112 stop=88.9%; OOS avg=-$424. Both regimes agree the window is bad.
- **Params.json:** `"entry_no_trade_window_et": ["11:30", "12:00"]` in `automation/state/params.json` ✅
- **Orchestrator:** `entry_no_trade_window_et` → `no_trade_window=(dt.time(11,30), dt.time(12,0))` via `_params_to_kwargs()` ✅
- **Heartbeat:** Filter 1 EXCEPTION bullet in `automation/prompts/heartbeat.md` ✅
- **AGG:** ✅ CLOSED 2026-06-17 (post-ENFORCED-5). Time distribution audit found 11:30-12:00 IS n=2 signal bars avg=-$516/signal, but OOS n=0 signal bars in window → OOS_delta=$0 → WF=0 → REJECT. ENFORCED-5 cascade: fill bar gate removed profitable lunch-zone ITM-2 trades (bullish-fill-bar wins), leaving only losses. But no_trade_window blocks signal bars (not entry times) so few signals actually fall inside. Scorecard: `analysis/recommendations/agg_post_enforced5_ntw_sweep.json`. Wait Q3 2026.

### [ENFORCED-5] AGG one-bar bearish fill bar confirmation (RULE-9-1) — IS+$363 OOS+$1,153 WF=18.522 ✅
- **Ratified:** 2026-06-17 | **J-RATIFIED** ("i apprve to ad d this") | **Scorecard:** `analysis/recommendations/fill-bar-gate-sweep.json`
- **What:** After AGG BEAR signal fires (all gates pass), wait one tick (5 min). Check if fill bar (bar N+1) closed bearish. If yes → enter at N+2 open. If bullish/doji close → `BEAR_FILL_BAR_SKIP`. If >2 ticks elapsed → `BEAR_FILL_BAR_EXPIRED`.
- **Evidence:** IS n=105→79 (-26 stops removed), IS_delta=+$363; OOS n=18→15, OOS_delta=+$1,153 (+$238→+$1,391). WF=18.522 (largest WF tested to date). SW_hurt=1/4. ANCHOR=PASS.
- **Params.json:** `"require_bearish_fill_bar": true` in `automation/state/aggressive/params.json` ✅
- **Heartbeat:** Gate AGG-3 in `automation/prompts/aggressive/heartbeat.md`: Part A (pending check after flat verification) + Part B (set pending in Time-class gates) ✅
- **Safe:** REJECT (IS_delta=-$860, WF=-7.927, anchor FAIL). AGG-only gate.

## HIGH VALUE — Pending Rule 9 sign-off

> *(Empty — RULE-9-1 J-ratified 2026-06-17 and moved to ENFORCED-5 above.)*

## Framework fixes

### [FIX-1] Autorate IS_delta guard (L155)
- **Filed:** 2026-06-17 | **Test:** `backtest/tests/test_graduated_guards.py::test_l155_autorate_rejects_negative_is_delta`
- **Bug:** WF_norm formula gives false-positive AUTO-RATIFY when IS_delta ≤ 0. Both-negative deltas → WF = (-/-) = positive → spurious ratification.
- **Fix:** All gate sweep scripts now include `if is_delta <= 0: return REJECT` guard before WF evaluation. L155 guard added to: `fill_bar_gate_sweep.py`, `safe_conj_lvl_rej_vix_split.py`, `safe_time_class_gate.py`.
- **Status:** ✅ FIXED in all active gate scripts (2026-06-17). Graduated guard test passes.
- **TODO:** Add guard to any new gate sweep script as standard boilerplate (template in `backtest/autoresearch/_gate_template.py` if created).

## High value, deferred

### 0. RE-RUN level-keyed validations on REAL ★★★ levels once the archive accumulates
- **Trigger:** when `journal/key-levels-archive/` holds **N>=20-30 trading days** of real production key-levels (currently ~10 as of 2026-06-19; accumulating daily via the inline `Gamma_DailyReview` archiver + the standalone `Gamma_ArchiveKeyLevels` safety-net — `setup/install-archive-key-levels.ps1`, `automation/scripts/archive_key_levels.py`).
- **Why this matters (the #1 validation data gap):** every level-keyed watcher/backtest run so far fell back to **synthetic ★★ PDH/PDL/PDC proxies** (`pattern_backtest._derive_named_levels`) because no historical archive of J's real ★★★ levels existed. The proxy-based runs produced **RETIRE verdicts** for the level-keyed family (floor_hold, close_ceiling, BEARISH_REJECTION on levels, bounce-family) — see `backtest/autoresearch/validate_level_family.py` op20_disclosures + project memory `project_watcher_engine_2026_06_18`. Those verdicts were rendered on PROXY levels, not real levels.
- **Scope:** re-run `python -m autoresearch.validate_level_family --start ... --end ... --realfills` (and the relevant `pattern_backtest` level setups) once N>=20-30 real days exist. The archive path is already the primary lookup (`_load_named_levels_from_keyjson` checks `journal/key-levels-archive/` BEFORE the synthetic fallback), so the re-run is automatic once the data is there — no harness change needed. **Compare REAL-level results against the proxy-based RETIRE verdicts: the real ★★★ levels may show edge the synthetic proxies masked, which would REVERSE one or more RETIRE calls.** This is the honest test of our actual level edge.
- **Estimate:** ~1h once the archive is deep enough (re-run + scorecard + verdict diff).

### 1. Bullish-side grinder optimization
- **Trigger:** when J has 3+ live BULLISH winners documented in `journal/trades.csv`
- **Scope:** mirror the 5-stage bearish pipeline (qty/stop/TP1 per quality tier) for bullish triggers
- **Estimate:** 1 day of dev + 24h grinder run
- **Note:** First-pass bullish grinder ALREADY built today (2026-05-10) using floor protection ("do no harm to bearish wins") since no J bullish source-of-truth exists yet. Once J has 3 wins, swap to J-edge primary scoring.

### 2. Sweep the 23 unexplored knobs
Current grinder varies 7 knobs. Unexplored (rough list):
- Strike offsets per quality tier (only OTM-2 tested + reverted; could explore OTM-1, ITM-1, etc per tier)
- **`no_trade_window` 11:30-12:00** — ✅ CLOSED 2026-06-17: SAFE ENFORCED-4 auto-ratified (IS_delta=+$10, OOS_delta=+$424, WF=247.282). AGG REJECT: IS_delta=-$261 (L155) — those 3 AGG signals in that window contribute +$261 IS, different from Safe's near-zero. ITM-2 strikes capture different opportunities in lunch zone. Scorecards: `analysis/recommendations/safe_no_trade_window_sweep.json`, `analysis/recommendations/agg_no_trade_window_sweep.json`.
- **`no_trade_window` 12:00-12:30 (Safe extension)** — ✅ CLOSED 2026-06-17: REJECT. IS n=3 avg=-$258 100%stop (looks structural), but OOS n=0 in that window after ENFORCED-4 baseline → OOS_delta=$0 → WF=0 → fails. Cascade effects: only 1 net IS trade removed (not 3). Retest when OOS covers this window (est. Q3 2026). Scorecard: `analysis/recommendations/safe_no_trade_window_v2_sweep.json`. Note: 12:30-13:00 window is C22-INVERTED (IS good, OOS bad) — do not gate.
- **`no_trade_window` 15:00-15:30 (Safe + AGG)** — ✅ CLOSED 2026-06-17: REJECT. IS n=11 avg=-$91 for Safe (81.8% stop). OOS n=0 → WF=0. AGG: OOS n=1 avg=-$424 (C22 inverted?). Both fail. Wait Q3 2026 OOS before retesting.
- **15:00-15:30 gate** — MONITOR as OOS grows. IS n=11 avg=-$91 stop=81.8% (structural gamma zone). OOS n=0 today → WF=0 → untestable. Retest at 2026-Q3 when OOS covers more late-session data.
- **SAFE morning trendline audit** — ✅ CLOSED 2026-06-17: ALL REJECT. Morning tl_pure IS=-$50/trade but OOS=+$23/trade (C22 inversion: DO NOT GATE). block_09:35-09:59 IS=+$93 OOS=$0. Scorecard: `analysis/recommendations/safe_morning_tl_audit.json`
- **SAFE day-of-week sweep** — ✅ CLOSED 2026-06-17: ALL REJECT. DOW effects are C22-inverted: Mon IS=-$19 but OOS=+$493; Tue IS=+$214 but OOS=-$221. Scorecard: `analysis/recommendations/safe_dow_sweep.json`
- **AGG day-of-week sweep** — ✅ CLOSED 2026-06-17: ALL REJECT. Same C22 pattern. Notable: block AGG Friday afternoon IS+$707 OOS+$19 WF=0.164 — below 0.70 threshold. Monitor as OOS grows. Scorecard: `analysis/recommendations/agg_dow_sweep.json`
- **SAFE block_conf_lvl_rej_midday_afternoon** — ✅ CLOSED 2026-06-17: REJECT (L155). Safe conf+lvl_rej IS PROFITABLE midday/afternoon (IS_delta=-$5,152 when blocked). Unlike AGG where it was bad, Safe's conf+lvl_rej is strong across all time windows. Scorecard: `analysis/recommendations/safe_conf_lvl_rej_midday_gate.json`
- `f9_vol_mult` per tier (currently 0.7 globally) — ✅ CLOSED 2026-06-17: FAIL (C22 regime split; f9_vol_mult candidates all hurt W1/W2)
- `RIBBON_SPREAD_MIN_CENTS` per tier — ✅ CLOSED 2026-06-17: ALL REJECT for AGG. Raising spread ≥35c kills IS conf+lvl_rej winners (avg +$1,809 IS, 4 trades blocked). OOS gain +$411 cannot justify IS loss -$11,827. Keep 30c baseline. Scorecard: `analysis/recommendations/agg_ribbon_spread_sweep.json`
- `LEVEL_PROXIMITY_DOLLARS` — ✅ CLOSED 2026-06-17: DEAD KNOB. Constant removed from filters.py and _FILTER_CONST_MAP (detect_level_rejection() never read it — hard coded level test). Graduated guard `test_level_proximity_dollars_removed_from_const_map` prevents re-adding (C14/L38 resolved).
- `CONFLUENCE_TOLERANCE_DOLLARS` — ✅ CLOSED 2026-06-17: 0.30 is optimal. Sweep run 0.10-0.75; tighter tolerance hurts OOS, looser doesn't help. Mechanism: $0.30 window for "multi-day touch within level" is calibrated. Old params but directionally conclusive. (`confluence_vixbull_minprem_sweep.py`)
- `MIN_PREMIUM_FOR_LEVEL_TIERS` — ✅ CLOSED 2026-06-17: Dead knob. IS_delta=0, OOS_delta=0 across values 0.20-0.80. All current entries already exceed any threshold tested (OTM-2 options at $2K equity ~$1.00+ premium). (`confluence_vixbull_minprem_sweep.py`)
- `time_stop_minutes_before_close` — ✅ CLOSED 2026-06-17: Safe=20min optimal, AGG=20min optimal. All candidates OOS_NEG. Confirmed both accounts: `analysis/recommendations/safe_time_stop_sweep.json` + AGG sweep (task b7x66repy).
- `tp1_qty_fraction` per tier — ✅ CLOSED: Safe=0.50, AGG=0.667 confirmed optimal in production
- `tp1_premium_pct` — ✅ CLOSED 2026-06-17: Safe=0.50 optimal, AGG=0.75 optimal. Confirmed via sweep (agg_tp1_premium_sweep.py). Lower values BOTH IS and OOS worse.
- `BEARISH_REVERSAL_BYPASS` (include_first_hour_high + bearish_reversal_bypass) — ✅ CLOSED 2026-06-17: REJECT both accounts. FHH countertrend bypass (ribbon=BULL, fhh_level_rejection fires, filter_5+8 bypassed) adds 14-25 new IS entries at WR=25-28% and avg=-$17 to -$32 (negative expectancy). OOS: 1 new entry on 2026-05-08, loses -$56 (AGG) / -$80 (Safe). OOS_delta negative both accounts; WF=-0.746 AGG / -0.859 Safe. Phase 1 IS-only window (2025-01 to 2025-09): n=14 bypass entries, WR=28.6%, avg=+$0.36/trade (zero edge). **Root cause (L158):** ribbon=BULL means bulls control tape; FHH rejection fails 72-75% of the time; -7% premium stop fires before bear move develops. The 5/01 J anchor (+$470) captured as only +$24 — the simulated entry path is different from J's live trade (exceptional intraday context not present in general population). Do not enable without J identifying what made 5/01 special (macro catalyst + VIX context + volume). Spec: `markdown/specs/BEARISH-REVERSAL-BYPASS-SPEC.md`. Scorecard: `analysis/recommendations/bearish_reversal_bypass_is.json`.
- `runner_target_premium_pct` — ✅ CLOSED 2026-06-17: AGG=5.0 optimal (target never hit; runner exits via ribbon_flip/time_stop). Safe=2.5 optimal. agg_runner_target_sweep.py: candidates 2.5-4.0 IS_delta=0, OOS_delta=0. **Re-confirmed by exit type audit 2026-06-17:** AGG IS: only 3/109 (2.8%) hit 5x target; OOS: 1/18 (5.6%). Dead knob confirmed. Cook queue task 6b403baf resolved. Scorecard: `analysis/recommendations/agg_exit_type_audit.json`.
- `profit_lock_chandelier` (v15_profit_lock_threshold_pct/mode/trail_pct) — ✅ CLOSED 2026-06-17: ALL REJECT both accounts. ALL 4 candidates L155 (IS_delta < 0). **Regime split:** W1 Jan-Jun 2025 (choppy/bear) HELP (+$3,850 SAFE, +$2,397 AGG) but W2 Jul-Dec 2025 + W3 Jan-Mar 2026 (trending) HURT (-$4,215/-$3,454 SAFE; -$7,053/-$3,454 AGG). Net = IS negative. **Root cause:** (1) 70% of AGG IS trades exit as premium stop before chandelier can arm (+5% threshold); (2) for the 20% that reach runner, chandelier trails 20% off HWM and cuts 0DTE runners short in trending markets. **Decision:** do NOT add profit_lock mappings to `_params_to_kwargs()`. Production chandelier serves live risk management, not backtest optimization. Regime-conditional chandelier (VOLATILE regime only) deferred until VIX-regime classifier ships (item 5a). Scorecard: `analysis/recommendations/profit_lock_sweep.json`.
- `premium_stop_pct_bear` — ✅ CLOSED 2026-06-17: Safe=-0.10 optimal (lower OTM-2 delta = higher %premium/SPY$; -0.07 fires excessively). AGG=-0.07 optimal. safe_premium_stop_sweep.py: all candidates worse. **Re-confirmed 2026-06-17 with correct ENFORCED-4+1 baseline (IS n=123 pnl=+$16,540 | OOS n=20 pnl=+$6,325):** -0.07/-0.08/-0.09/-0.11/-0.12 all L155 REJECT. Tighter stops hurt W3/W4; looser barely neutral but still IS-negative. -0.10 is definitively optimal.
- `ribbon_flip_price_confirm` (exit gate) — ✅ CLOSED 2026-06-17: L155 REJECT both accounts. Safe: IS_delta=-$266, OOS_delta=$0. AGG: IS_delta=-$199, OOS_delta=$0. Root cause: gate suppresses some IS ribbon-flip exits where SPY was close to entry → those held longer and lost more (ribbon was a correct reversal signal, not noise). OOS: no flip-backs were in the $0.50 buffer zone → OOS unaffected. Current immediate-ribbon-exit is optimal. The 5/01 +$470 case is a non-replicable outlier. Scorecard: `analysis/recommendations/ribbon_flip_price_confirm_sweep.json`.
- ELITE tier specifics (qty=10, stop=-15%, tp1=+50% are hardcoded — should sweep)
- TRENDLINE quality threshold — ✅ CLOSED 2026-06-17: `trendline_requires_ribbon_flip=True` FAIL (safe_trendline_ribbon_flip_sweep.py; W1=-315 HURT, W2=-2646 HURT, SW_hurt=2/4)
- `min_swings` for trendline — ✅ CLOSED 2026-06-17: ALL REJECT. 3 confirmed optimal. Stricter (4,5): IS_delta<0 (L155) — C22 inverted (W3 +$1,853 but W1/W2 -$4,401). Looser (2): OOS -$1,062, WF=-10.389. Scorecard: `analysis/recommendations/safe_min_swings_sweep.json`
- `lookback_bars` for trendline (currently 60) — likely C22 blocked
- Wick-rejection thresholds (currently 50%/$0.15/$0.10) — ✅ CLOSED 2026-06-17: DEAD KNOB. Safe wick_rejection trigger barely fires (OTM-2 setups are conf+lvl_rec/rej dominant). 0.30/0.40 = zero impact (no trades change), 0.60/0.70 = adds 1 trade and hurts IS. Optimal = 0.50 (current). Scorecard: `analysis/recommendations/safe_wick_pct_sweep.json`.
- VIX_BEAR_THRESHOLD — ✅ CLOSED (re-confirmed 2026-06-17 post-ENFORCED-5): 15.0 confirmed optimal for AGG. Post-ENFORCED-5 sweep: thresh=16.0 no-op (ENFORCED-5 already filtered all VIX<16 bears), thresh≥17.0 IS_delta=-$2,861 L155. ENFORCED-5 absorbed the VIX<16 OOS problem bears entirely (pre-E5: VIX<17 n=9 WR=33% -$400; post-E5: those trades gone). Safe default 17.30 in production. Scorecard: `analysis/recommendations/aggressive_vix_bear_threshold_sweep.py` results.
- VIX_BULL_LOW_THRESHOLD (currently 17.20) — likely C22 blocked (entry filter by VIX regime)
- VIX_BULL_HARD_CAP — ✅ CLOSED 2026-06-17: `vix_bull_max=18.0` already RATIFIED and in production Safe params (`SAFE_OVR`). Old sweep showed 18.0 WF=2.846, IS+$1,253 OOS+$219. (`confluence_vixbull_minprem_sweep.py`)
- `BREAKDOWN_VOL_MULT` (currently 1.3) — C22 blocked (entry filter)
- Quality-rank thresholds (when does ELITE become SUPER, etc.)
- Per-quality 45-min gap rule (currently global)
- Day-trade count limits (currently always-pass)

**⚠️ C22 BLOCKER (2026-06-17):** W1/W2 (Jan-Dec 2025 bull) vs W3/W4 (Jan-May 2026 volatile) structural VIX regime split blocks virtually all entry filters. Any IS-trained filter that improves OOS (W3/W4-like regime) hurts W1/W2 (bull regime), causing SW_hurt≥2/4. Remaining knob sweeps should be attempted only after OOS grows to cover multiple regime cycles (est. Q3 2026+) OR after a regime classifier is built that segments IS training by VIX regime.

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

### 5a. VIX-regime classifier (architectural fix for C22)
- **Trigger:** after Q3 2026 OOS covers multiple regime cycles, OR when J wants to unlock C22-blocked gates
- **Scope:** Segment IS training by VIX regime (BULL<17.5, NEUTRAL 17.5-22, VOLATILE≥22). Train regime-specific gate sets. heartbeat selects active params based on premarket VIX check.
- **What unlocks:** DOW gates (Mon/Wed IS bad→OOS good), trigger class gates (lvl_rec_only, tl_pure), entry quality filters (min_swings, lookback_bars, wick thresholds). C22 regime split (Jan-May 2026 volatile vs Jan 2025-Mar 2026 bull) currently blocks ~15 candidate gates from auto-ratifying.
- **Estimate:** 2-3 day design + implementation + validation
- **Why high value:** Every gate that fails OOS="PASS but SW_hurt=2 (W1/W2 hurt)" becomes ratifiable under a regime classifier that separates W1/W2 (bull) from W3/W4 (volatile) IS data.

### 5. Setup expansion beyond ribbon_ride
- **Trigger:** when J develops named patterns for new setups (e.g. "VWAP_RECLAIM_FADE", "OPENING_DRIVE_CONTINUATION")
- **Scope:** add new setup name to `markdown/0dte/playbook.md`, then grinder optimization
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
- **Doctrine ref:** `markdown/0dte/V15-ACTIVATION-2026-05-13.md`

### 10. v14e grinder silent-death root cause (T39) ✅ FORENSICS DONE 2026-05-14 03:20 ET
- **Forensics doc:** `markdown/audits/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md` (Fire #23).
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
- **Trigger:** J morning decision per `markdown/research/SNIPER-FINAL-VERDICT-2026-05-13.md`
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
- **Doc:** `markdown/audits/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md`

### 20. Premarket news.json live-refresh (NEW Fire #21 2026-05-14 02:25 ET)
- **Current state:** `automation/state/news.json` is refreshed manually by overnight wake fires using inference from data files. No live-news API integration.
- **Tomorrow 5/14 08:30 ET premarket task SHOULD re-fetch fresh headlines + jobless-claims consensus + Fed speakers** via Exa / web search if available.
- **Scope:** add Step 1f to premarket.md that does an Exa search ("today economic events", "fed speakers schedule today", "WMT earnings preview") and overwrites news.json's catalyst_summary + primary_catalyst section.
- **Estimate:** 1-2h dev. Has Exa/WebFetch dependency.

---

## NEW 2026-06-16 — Unusual Whales integration (smart money / dark pool / GEX)

### 21. Unusual Whales MCP — options flow + dark pool + GEX as heartbeat confluence signals

**Background:** Deep research (2026-06-16, 103 agents, 21 sources) confirmed Unusual Whales is the only viable real-time options flow + dark pool platform. No free alternative exists — FINRA is 2–4 weeks delayed, CBOE Open-Close is $6K/month. UW has an official MCP server that wires into Claude Code identically to Alpaca/TradingView.

**Gate — do NOT start until:**
- [ ] Dedicated API heartbeat has a **clean week of execution**: fills match intent, no ghost positions, no state drift, no missed EOD flatten, decisions.jsonl complete for all ticks
- [ ] Both Safe-2 and Risky-2 heartbeats running without intervention for 5 consecutive trading days
- [ ] No open incidents in `automation/overnight/STATUS.md`

**Phase 1 — $50/week trial (1 week, shadow mode only)**

1. Sign up at unusualwhales.com → get API key from Settings → API Dashboard
2. Add to `.mcp.json` (project-local, same file as `alpaca` + `tradingview`):
   ```json
   "unusualwhales": {
     "type": "remote",
     "url": "https://api.unusualwhales.com/api/mcp",
     "headers": { "Authorization": "Bearer YOUR_KEY" }
   }
   ```
3. Wire into heartbeat — **read-only, log to `decisions.jsonl`, do NOT gate entries yet:**
   - `get_gex_levels` → log nearest dealer gamma wall relative to SPY price
   - `get_dark_pool_prints` → log SPY dark pool volume + direction in last 30 min
   - `get_options_flow` → log net call/put premium flow on SPY in last 15 min
4. After each trade (win or loss), tag the `decisions.jsonl` entry with the UW signal values at entry time
5. At week end: run correlation — do ENTER ticks where `dark_pool_direction == trade_direction` win more? Does entering within $1 of GEX wall change outcomes?

**Decision gate after Phase 1:**
- If ≥60% of winners had confirming dark pool flow AND ≥60% of losers had opposing flow → **confirmed edge → Phase 2**
- If correlation is weak → park UW as premarket-only context (not intraday signal), downgrade to $0 (cancel trial)

**Phase 2 — $150/month Basic (polling, no WebSocket) + ELITE tier upgrade**

1. Promote to paid Basic tier
2. Add UW signals as **CONFLUENCE modifier** in heartbeat rubric:
   - `dark_pool_confirms` = dark pool net direction matches trade direction in last 30 min
   - `gex_wall_clear` = nearest GEX wall ≥$1.00 away from entry (room to run)
   - `flow_confirms` = net SPY options premium flow agrees with direction in last 15 min
3. Scoring: `dark_pool_confirms + gex_wall_clear + flow_confirms` → 0/1/2/3 confluence points
4. Wire to ELITE tier gate: ELITE requires confluence ≥ 2 (adds to existing ELITE conditions)
5. Update `decisions.jsonl` schema to include `uw_dark_pool_direction`, `uw_gex_wall_distance`, `uw_flow_score`

**What NOT to do:**
- Do NOT use UW flow as a standalone entry signal — it is confluence only, J's chart setups remain primary
- Do NOT gate HOLD/SKIP on UW (missing UW signal ≠ no trade; it's additive, not blocking)
- Do NOT subscribe to Advanced ($375/mo) or Historical add-on ($250/mo) until Phase 2 proves edge at 20+ trades
- Do NOT wire during market hours (09:30–15:55 ET) without J authorization for the phase transition

**Cost math (per current account):**
- Phase 1: $50/week × 1 week = $50 one-time
- Phase 2: $150/month = ~4% of $3.67K combined capital
- Break-even: 1 avoided loss of $150 or 1 extra win of $150 covers the month
- Kill switch: cancel if 30-day impact on decisions.jsonl shows <$150 net improvement

**Key contacts / links:**
- Sign up: unusualwhales.com/public-api
- MCP repo: github.com/unusual-whales/unusual-whales-official-mcp

---

## NEW 2026-06-16 — Futures Edition (MNQ/MES) improvements

### 22. Futures paper trading activation (Steps 6–8)
**Gate:** J creates IBKR account + enables paper trading. Then:
1. `docker run -d --name ib-gateway -p 4002:4002 -e TRADING_MODE=paper -e TWS_USERID=<id> -e TWS_PASSWORD=<pw> ghcr.io/gnzsnz/ib-gateway:latest`
2. `pip install ib_async`
3. Set `WATCH_ONLY = False` in `backtest/futures/ibkr_paper.py`
4. Register `Gamma_FuturesHeartbeat` + `Gamma_FuturesPremarket` + `Gamma_FuturesEodFlatten` in Windows Task Scheduler

**Config:** MNQ v3 first (IS=+$6,860, OOS=+$15,027 PASS); add MES after MNQ validates fleet.

### 23. v14_enhanced short medium regime filter — direction gate
**Context:** v14_enhanced short medium on MNQ shows bimodal OOS: Q1-26 WR=15% (bull market, -$1,414) vs Q2-26 WR=60% (bear market, +$781). R ratio is 2.04x at full-period WR=38% — positive EV overall but unstable.
**Research question:** does a 5-day MNQ trend direction filter (e.g. prior_5d_return > 0 → skip medium-confidence shorts) eliminate Q1 losses without harming Q2 gains?
**Gate before implementing:** confirm Kitchen task results (task_id=3efd6be6-27c1-4287-97a6-79d52ece2ef0). OOS must remain positive overall.

### 24. MES v14_enhanced short medium threshold tuning
**Context:** MES v14_enhanced short medium OOS barely negative (-$165, N=35). Both Q1 and Q2 are marginal negative. The VIX>=18 gate may be too low for MES — S&P mean-reverts more than Nasdaq.
**Research question:** does raising VIX threshold to >=20 or >=22 improve the OOS? Or should this signal be dropped from MES v3_mes entirely?
**Gate:** Kitchen task results (task_id=704fa9ff-5144-46db-91cf-d0fb2ad0a4a0). v3_mes must maintain OOS>0 after change.

### 25. MNQ erl_irl long high Q1-26 loss investigation
**Context:** erl_irl long high has WR=73% in Q1-26 but net=-$1,707 (avg_win tiny vs avg_loss large). In Q2-26 it works brilliantly (WR=85%, +$1,455). Root cause: in Q1-26 bull market at ATH, erl_irl entries are choppy/whipsaw — 73% of entries move slightly in direction before reversing on large bars.
**Research question:** is there a size-of-move filter that improves Q1 without harming Q2? E.g. `min_initial_move_pts >= 10` before entry confirmation.
**Gate:** run only after 22 (IBKR paper) confirms the watcher fleet fires correctly in live mode.

### 26. Futures overnight session exploration
**Context:** current futures engine is RTH-only (flat by EOD). Futures trade 23 hours/day. The overnight Globex session (15:30–09:30 ET next day) often sets critical levels (ONH/ONL) that become support/resistance.
**Research questions:** (a) do the same setups (shotgun long, erl_irl) work in overnight session? (b) can holding through overnight improve runner P&L? (c) what's the prop firm overnight hold rule?
**Gate:** after paper trading validates RTH strategies. New sim required (currently RTH-only `rth_only()` filter). J must authorize overnight holding (Rule 9 — no mid-session rule changes).
- API docs: api.unusualwhales.com/docs
- Pricing page: unusualwhales.com/pricing

**Estimate:** 2h wiring (Phase 1) + 1 week shadow + 2h analysis + 4h Phase 2 promotion if warranted

---

## Tracking

When starting any item:
1. Move from this file to an active task in `automation/state/research-queue.json`
2. Create matching CLAUDE.md operating principle if it changes doctrine
3. Update CHANGELOG.md row
