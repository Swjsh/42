## [2026-07-15 ~00:44 ET] BUILD+LIVE — TWIN-B4: weekly chaos drill + resilience ledger, all 4 injections run FOR REAL against the twin tonight, all recovered [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-15 00:44:09 Wednesday EDT market_hours=False`).** Lane A overnight task: build the weekly failure-injection drill for the CRYPTO TWIN ONLY per queue.md `TWIN-B4-CHAOS-DRILL` / `markdown/planning/TWIN-PROGRAM.md` value stream #4. Crypto twin paper only — zero SPY/fleet/core writes, zero params/config changes.
>
> **Shipped:** `setup/scripts/twin_chaos_drill.py` — four failure injections, run one at a time, each restoring clean state before the next starts. Every drill drives REAL production functions (`crypto_twin_core.run_tick`/`place_entry`/`load_breaker`/`_risk_gate_check`, `crypto_twin_broker`'s REST calls, `crypto.lib.kill_switch.tick`) — no new decision logic invented. **(1) process_kill_mid_position** — opens a real tagged position, launches a real managing tick as a subprocess (the exact `crypto_twin_health.py --live` entrypoint), force-kills it mid-flight (`TerminateProcess`), proves a fresh tick recovers via `classify_recovery()`'s decision table, force-flattens regardless. **(2) corrupt_state_file** — malforms `exit-state.json`, proves fail-open (never raises), restores exact bytes. **(3) stale_feed** — feeds `run_tick` a bar closed 3h stale via the real injectable `raw_bars` param, proves staleness detection fires (`HOLD_BAD_BARS`, zero order risk). **(4) breaker_mid_trip** — overwrites `breaker.json` with a LATCHED-tripped doc (healthy equity, isolating the latch property), proves the real halt chain (`code=KILL_SWITCH`) and re-arm off the restored file. Every rep appends one row to `automation/state/crypto-twin/resilience-ledger.jsonl`.
>
> **REAL drill cycle run tonight, not just built (per the task's explicit authorization — "it's the validation ground, this is exactly its job"):** all 4 drills `recovered: true` against the live twin. `stale_feed` — staleness correctly detected, 0 new orders. `breaker_mid_trip` — real HALT (`code=KILL_SWITCH`), real RE-ARM (`code=ALLOW`), `breaker.json` restored byte-identical. `corrupt_state_file` — fail-open confirmed, `exit-state.json` restored byte-identical. `process_kill_mid_position` — real BTC/USD entry at $64,697.78, managing subprocess genuinely killed mid-flight (`killed_before_completion: true`), recovery classified `STATE_CONSISTENT_WITH_BROKER`, force-flattened clean. Twin verified flat post-drill (`exit-state.json: {}`, `scenario-state.json: {}`). A first process-kill rep at the 2.5s default timeout finished before the kill landed (honestly logged as a weaker rep, still recovered, not hidden) — added a `--kill-after-sec` CLI knob and retried at 0.3s for a genuine kill.
>
> **Bug caught + fixed same session:** the first two offline pytest runs silently wrote fake test rows into the REAL `resilience-ledger.jsonl` — `cfg`'s `state_dir` was tmp_path-isolated but `append_resilience_row`'s `ledger_path` defaulted to the real production path regardless of `cfg`. Caught by inspecting the ledger after the first live run and finding fake-broker-shaped rows (`"$65,000.00"`, `"no twin creds"`) interleaved with genuine ones. Fixed by threading `ledger_path` through every `drill_*()` function, resolved inside the body rather than as a bound default — the identical bug class `force_flatten_position`'s own `close_fn` default hit first (caught by its own offline test before this one landed). 18 polluted rows removed from the real ledger; 5 genuine rows kept.
>
> **Registered:** `Gamma_TwinChaos` — Weekly, Sunday 03:00 ET (01:00 MT), `wscript->run_exe_hidden.vbs->backtest\.venv\Scripts\pythonw.exe->twin_chaos_drill.py --all`, same reaper-exemption pattern as `Gamma_CryptoTwin`/`Gamma_TwinSentinel`. Verified: `Get-ScheduledTask` `State=Ready`, real trigger `DaysOfWeek=1` (Sunday)/`WeeksInterval=1` (not a one-time/bare-interval trigger), `NextRunTime=2026-07-19 01:00:00` (confirmed a real Sunday). **Concurrency note:** a parallel session's pre-commit safety gate independently caught the same task registered-but-undocumented and auto-stubbed a duplicate row in `SCHEDULED-TASKS.md` moments after mine landed — reconciled in place (stub removed, header note corrected, no work lost).
>
> **Tests:** 30 new (`test_twin_chaos_drill.py`, fully offline/deterministic — `classify_recovery`'s 5-branch decision table, inject/restore-state round-trips, `force_flatten_position` with an injectable close_fn, `build_tripped_breaker_doc`+`verify_gate`'s real halt/re-arm chain, `detect_stale_feed`'s real `run_tick(raw_bars=...)` path, one fully-mocked `drill_process_kill` orchestration) + 13 new (`test_twin_chaos_drill_reaper_exemption.py`, static installer guards: reaper exemption, Weekly-not-one-time trigger, ET->MT conversion). Twin-related suite: 199/199 passed, zero regressions. Confirmed test isolation: real `resilience-ledger.jsonl` line count unchanged (23->23) across a full offline test-suite re-run after the ledger_path fix.
>
> **REVOKE:** `Unregister-ScheduledTask Gamma_TwinChaos` (or `install-twin-chaos-drill.ps1 -Uninstall`); revert `setup/scripts/twin_chaos_drill.py` + the two new test files + `SCHEDULED-TASKS.md`/`TWIN-PROGRAM.md` doc rows. Twin state fully restored to flat/clean regardless (`exit-state.json`/`breaker.json`/`scenario-state.json` all verified pre-drill-equivalent).

## [2026-07-15 ~00:35 ET] BUILD — AUDIT-HARNESS-B3: prospector + swarm_consult wired into free_model_audit.py, both real runs INSUFFICIENT EVIDENCE (honest, not oversold) [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-15 00:13:07 Wednesday EDT market_hours=False`).** Lane B overnight task: wire the two remaining TODO-stub `AUDIT_SUBJECTS` (queue.md `AUDIT-HARNESS-B3`) into `setup/scripts/free_model_audit.py`, following the pattern of the two already-wired adapters (`free_model_audit_heartbeat_veto.py`, `free_model_audit_twin_review.py`). No live-order path touched, no params/config changed, read-only on production decision paths per the framework's own non-goals.
>
> **`prospector` (`setup/scripts/free_model_audit_prospector.py`) — grades idea-promotion judgment by pure record-linkage, NO LLM call (`grading_method: deterministic_cross_check`).** For every idea `prospector.py` promoted into `strategy/candidates/_chef-inbox/`, checks whether it later shows up as a `kind:"kill"` row in `ideas-ledger.jsonl` (prospector's own authoritative kill mechanism) or with a KILL/CLEAR verdict word next to its dedupe_key anywhere under `analysis/recommendations/`; neither found = still pending, honestly ungraded. **Found-and-disclosed, not silently fixed:** `state.json`'s `promoted_dedupe_keys` counter (4) undercounts the REAL filesystem promotion history (29 `*-prospector-*.md` files in `_chef-inbox/`) — a pre-existing prospector.py bookkeeping drift. `collect_items` reads the filesystem listing directly instead, so the audit isn't blind to 25 of the 29 real promotions.
>
> **`swarm_consult` (`setup/scripts/free_model_audit_swarm_consult.py`) — grades open-ended brainstorm/decide/critique/audit quality via blind Sonnet re-judgment, PROMOTED to primary method** (no $ counterfactual or 2nd deterministic source exists for prose, unlike heartbeat_veto/twin_review): Sonnet answers the same question blind (never shown the swarm's synthesis first — anti-anchoring), then a SEPARATE Sonnet call scores whether that blind answer and the swarm's answer reach the same conclusion (`grading_method: llm_judgment`). Capped at `MAX_SAMPLE_PER_RUN=5` consults/run (2 real Sonnet subprocess calls each = 10 calls max), most-recent-first regardless of backlog size, to bound cost per J's explicit instruction.
>
> **VERIFIED — 97/97 pytest** across the full `free_model_audit` family (19 framework `test_free_model_audit.py` incl. 3 updated/new registry tests + 19 `test_free_model_audit_heartbeat_veto.py` + 20 `test_free_model_audit_twin_review.py` (both pre-existing, unchanged, re-run as a regression check) + 20 new `test_free_model_audit_prospector.py` + 19 new `test_free_model_audit_swarm_consult.py`, zero regressions). `test_registry_has_stub_subjects_unwired` (asserted both were UNWIRED) replaced with `test_registry_has_prospector_wired` / `test_registry_has_swarm_consult_wired` / `test_registry_has_exactly_four_wired_subjects`, since flipping `wired=True` is the whole point of this task.
>
> **REAL runs, not mocked (`--subject prospector --force` + `--subject swarm_consult --force`, real subprocess Sonnet calls for the second):**
> - `prospector`: **31/31 promoted ideas graded, 0 correct / 0 wrong, INSUFFICIENT EVIDENCE (0/15)** — every currently-promoted idea is still pending; none has cycled through a full battery to a `analysis/recommendations/` scorecard yet. Exactly as predicted before running.
> - `swarm_consult`: **5/5 graded** (the 5 most recent daily "audit Project Gamma" consults, 2026-07-09..07-13 — the whole in-window backlog was audit-mode dailies), **1/5 agreed with Sonnet's blind re-answer (20%)**, **INSUFFICIENT EVIDENCE (5/15)** — n=5 correctly NOT extrapolated into any verdict on swarm-consult quality (the low agreement rate is a genuinely interesting first read but far too small a sample to act on).
> - Confirmed `backtest/.venv` is reaper-exempt (`_shared.ps1` `EXEMPT_DAEMONS`) BEFORE relying on it: the swarm_consult run took ~5.5 min wall-clock (10 real Sonnet subprocess calls, some near the 180s per-call timeout) and was NOT killed mid-run by the 5-min stale-process reaper.
> - Scorecards: `analysis/free-model-audit/prospector/2026-07-15-scorecard.md`, `analysis/free-model-audit/swarm-consult/2026-07-15-scorecard.md`. Bar state: `automation/state/free-model-audit-state.json` now carries all 4 subjects.
>
> **NOT DONE (out of this task's granted scope, flagged not fixed — same follow-up AUDIT-HARNESS-B1/B2 already logged):** `Gamma_FreeModelAudit`'s scheduled-task command line still hardcodes `--subject heartbeat_veto` only. `--subject all` now automatically picks up all 4 wired subjects (the registry is built dynamically), so the fix is a one-line command-line change whenever a session is granted scheduler access — not touched here since this task's CONSTRAINTS didn't authorize it.
> - **Queue:** `automation/overnight/queue.md` `AUDIT-HARNESS-B3` moved to `status:done`.
> - **REVOKE:** two new adapter files + two new test files + the registry wiring in `free_model_audit.py` (stub removal, 2 real `try/import` blocks replacing 2 stub entries) + doc updates (`markdown/infra/FREE-MODEL-AUDIT-HARNESS.md`) — `git diff` the 5 touched files to revert; the framework itself (`free_model_audit.py`'s core loop/confidence-bar math) is unchanged, only the registry entries.

## [2026-07-15 ~00:32 ET] FIX — crypto-gym CRYPTO-GYM-V02-V12-FOLLOWUP: v02/v12 rolling-window degradations root-caused + fixed, both were monitoring-layer bugs not engine bugs [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-15 00:32:19 Wednesday EDT market_hours=False`).** Lane C overnight task: root-cause the two crypto-gym validator stages flagged as "self-diagnosed but not fixed" in the 2026-07-11 CRYPTO-GYM-V53-DRIFT-TRIAGE note. Neither turned out to be a validator logic bug in the engine-facing sense — both were monitoring/alerting-layer bugs that let an already-diagnosed-benign condition still gate severity RED. No live-order path touched. No params/config changed.
>
> **v02_source_parity** — the diagnosis already existed and was already correct (`v15_three_source_parity.py`'s docstring: yfinance settles its close later than Coinbase, a strict 2-source check structurally can't avoid disagreeing on that, v15 is the documented 2-of-3 quorum ratifier). The bug: `crypto/benchmarks/track_drift.py::build_report` computed that exact diagnosis into the alert TEXT and then still let it flip `overall_health` to RED regardless — diagnosing an artifact and gating on it anyway is why the 2026-07-02/07-11 self-diagnoses never closed the loop, and why raising `PRICE_TOLERANCE_PCT` 5bp→7bp (2026-05-23) didn't help (wrong mechanism — timing, not tolerance width). **Fix:** `build_report` now returns `blocking_alerts` (drives `overall_health`) separate from `alerts` (everything, still fully visible, OP-33). A v02 dip is demoted to informational-only when v15 ratifies it healthy — both at the 24h stage-rate level (>=95%) and, more rigorously, at the grinder per-iteration level (>=90% of the specific drifting iterations also had `v15_parity.pass=True` in the SAME iteration, not just a coincidental aggregate). `setup/scripts/run-crypto-regression.ps1`'s STATUS.md writer now keys its 6h-cooldown change-detection off `blocking_alerts` too.
>
> **v12_multi_timeframe.live** — genuinely had no prior diagnosis. Pulled all 17,656 grinder.jsonl iterations (2026-06-15..07-15): exactly 2 distinct bars EVER produced a volume disagreement (2026-06-28T17:35Z agg=79.53/native=47.86 +66.2%; 2026-07-11T07:50Z agg=2.972/native=1.874 +58.6%), both directionally consistent (agg always > native, never the reverse), both isolated single bars (0 price disagreements in 17,656 iterations — the offline `_aggregate()` math is exact per T1-T6), both persisted UNCHANGED for ~91 consecutive fetches (~3h, the width of the 200-bar 1m fetch window) before aging out — i.e. Coinbase's own native multi-minute candle never reconciled toward the 1m-summed value over time. Root cause: a rare, real, same-provider cross-granularity settlement artifact (Coinbase's multi-minute candle endpoint occasionally freezes volume before some late-reconciling trades attribute, while the finer 1m endpoint already reflects them) — not a cross-provider issue (can't quorum-vote it the way v02/v15 do; no 3rd venue reports crypto volume comparably) and not an `_aggregate()` bug. The old zero-tolerance criterion let 1 isolated confirmed-benign bar fail the whole run for the ~3h it stayed in-window, dragging the 24h rate to ~87.5%. **Fix:** `_compare()` gained `max_vol_outlier_bars=1` — volume tolerates 1 isolated bar per run; price stays true zero-tolerance (never legitimately disagreed).
>
> **Verified fresh this fire:** `python crypto/validators/runner.py --skip-replay` → `SUMMARY: passed=103/103 overall_pass=True` (v02_source_parity, v12_multi_timeframe.offline, v12_multi_timeframe.live all PASS). `python -m pytest crypto/ -q` → `91 passed` (new: 5 in `crypto/benchmarks/test_track_drift.py`, 3 new offline guard tests T7-T9 in v12's `run_offline`). Regenerated `drift_report.json` live with the fix: v02's alert is now tagged `[info-only]` and correctly absent from `blocking_alerts`.
>
> **`overall_health` is still RED right now — NOT from v02 or v12, and NOT a new break.** `v53_setup_dispatch.live` shows 13 consecutive fails 2026-07-14 13:27-18:27 UTC (~09:27-14:27 ET, i.e. during yesterday's market hours) still inside the 24h rolling window, but has posted 16 consecutive PASSES since 19:27 UTC and `consecutive_fail_streak: 0` confirms the engine is healthy right now (also confirmed by the fresh 103/103 full-suite run above). This is the exact same "self-diagnosed, already fixed, rolling-window hasn't aged it out yet" pattern v02/v12 had — just for a stage outside this task's Lane C scope. Did not investigate further or touch it (out of scope, already resolved); will self-heal from the 24h window by ~2026-07-15 18:27 UTC. Flagging per OP-33 visibility, no action needed unless it recurs after that.
>
> **Files:** `crypto/benchmarks/track_drift.py`, `crypto/validators/v12_multi_timeframe.py`, `setup/scripts/run-crypto-regression.ps1`, new `crypto/benchmarks/test_track_drift.py`. Lesson candidate queued: `strategy/candidates/_lesson-inbox/2026-07-14-quorum-ratified-alert-still-gated-health.md` (suggested L201, for `lesson-author` to graduate into `LESSONS-LEARNED.md` + CLAUDE.md OP-25 index).
> - **Queue:** `automation/overnight/queue.md` CRYPTO-GYM-V02-V12-FOLLOWUP moved to `status:done`.
> - **REVOKE:** all changes are to test/monitoring code (`crypto/benchmarks/`, `crypto/validators/v12_*`, the STATUS.md writer in `run-crypto-regression.ps1`) — nothing on the live-order or params path. `git diff` the 3 files to revert if any downstream consumer of `drift_report.json` expected the old flat-`alerts`-only shape (new `blocking_alerts` field is additive, `alerts` unchanged in meaning).

## [2026-07-15 ~00:25 ET] RESEARCH — EDGE-2 debit-spread A/B + EDGE-3 hold-posture A/B: BOTH KILL, mleg execution stays disarmed [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-15 00:13:08 Wednesday EDT market_hours=False`).** Two sequential pre-registered studies from `markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md` (items #2 and #3), one OPRA lane, job 1 fully before job 2. Both frozen-before-run (commits `619a4fe` / `a3ac288`), both KILL. No orders, no params/config changes, $0 cost (local OPRA cache only).
>
> **JOB 1 — EDGE-2-DEBIT-SPREAD-AB (`analysis/recommendations/debit-spread-ab.{json,md}`, commit `f321314`): KILL both variants (OTM-1, OTM-2).** ATM long leg (matches live tier) + OTM-1/OTM-2 short leg vs naked ATM control, on the 250-signal ribbon_ride cohort (n=244 replayed) + 110 real-fill corroboration (n=92 replayed), exits via the live `exit_manager` decision core at live `params.json` scope. Expectancy -$63.06 / -$52.65 per episode vs naked's -$5.24; OOS negative, qpf=0.0 (every quarter net-negative), BH-FDR confirms the delta vs naked is significant but it's a WORSENING not an improvement. **Mechanism, not noise:** `friction_pct_of_premium` is ~3-4x the naked control's (25.7%/17.0% vs 5.8%) because the SAME $0.02/leg + $0.65/leg/side haircut applies to a net-debit base 2.5-4x thinner than the naked premium — confirms the deep-research synthesis's own named competing hypothesis (friction eats the VRP benefit). No OP-16 anchor regression, but heavily caveated: the naked ATM-convention baseline itself does not reproduce J's real winning P&L on the 3 anchor days (different strike than J's actual historical fills), so the anchor check's real job couldn't be fully exercised. **Consequence:** the sibling BUILD lane's `spread_executor.py` mleg machinery (this same evening, `spread_execution_enabled: false` in both params.json files) stays DISARMED — this scorecard is the gate it was built to wait on, and it did not clear.
> - **Found-and-fixed before reporting any verdict:** v1's first run produced an implausible WR=3.7% (premium_stop fired 233/244 episodes) — traced to feeding the intrabar long.low-short.high "worst-of-both-independent-extrema" combo directly into the touch-based stop trigger, more pessimistic than `backtest/lib/simulator_debit.py`'s own precedent (which gates its actual PT/STOP on bar-CLOSE net premium, using the intrabar combo only as a disclosure flag). Corrected to match that precedent; pre-reg bumped v1→v2 with the defect disclosed in-place, hash repinned, re-run — WR moved to a sane 45.5%/48.0%, same directional verdict (KILL), now trustworthy.
>
> **JOB 2 — EDGE-3-HOLD-POSTURE-PREREG (`analysis/recommendations/hold-posture-ab.{json,md}`, commit `cb73fdc`): KILL both variants, but TRAIL_ONLY_60 is nuanced, not a clean negative.** Same cohort + corroboration, single-leg only (no structure change — that's EDGE-2's scope), reusing EDGE-2's population/battery/null/BH-FDR machinery as a library import. **MIN_HOLD_30** (30min floor before any non-catastrophe exit): clean decisive KILL, exp -$60.57/episode, OOS negative, qpf=0.167, BH-FDR-significant WORSENING. **TRAIL_ONLY_60** (trailing-primary via `profit_lock_arm_scope="full"`, TP1 deferred past 60min): aggregate exp -$1.37 (near-breakeven, slightly BETTER than control's -$5.24), OOS positive, qpf=0.667 — but the delta vs control (observed_mean_diff +$3.88) is NOT statistically distinguishable from the shuffle null (p_null=0.917), so it fails the pre-registered significance gate → verdict KILL per the frozen pass bar. Worth flagging: on J's 3 real OP-16 anchor days specifically, TRAIL_ONLY_60 swings from control's -$674 to **+$141.80** — a real, directionally-consistent improvement on exactly the multi-hour-ride days the falsification-literature hypothesis targets, even with no significant aggregate lift over 244 signals. 110-episode corroboration agrees in sign for both variants.
> - **Found-and-fixed before reporting any verdict:** `exit_manager`'s `"premium_stop"` stage label doesn't distinguish the static -50% catastrophe cap from a pre-TP1 profit-lock-floor exit under `profit_lock_arm_scope="full"` — using the static formula for both produced an implausible TRAIL_ONLY_60 first-run result (WR=0%, exp=-$597/episode). Fixed to use the actual `runner_stop_premium` exit_manager computed (same fix applied to `debit_spread_ab_study.py` for correctness; confirmed byte-identical/no-op against EDGE-2's already-committed numbers, which never exercised `arm_scope="full"`).
>
> **EDGE-KILL-LEDGER candidate (not yet actioned):** both structure (debit-spread) and posture (hold-floor / TP1-deferral) changes to the current SHAPE, tested honestly per the mission's own "let the data decide" framing, came back KILL against the frozen pass bar. TRAIL_ONLY_60's anchor-day-specific improvement is real but not (yet) aggregate-significant — flag for a future, larger-n or anchor-stratified follow-up rather than a registry closure; not formally closing this thread tonight (only the 5 items EDGE-KILL-LEDGER itself named earlier this session were closed).
> - **Queue:** `automation/overnight/queue.md` EDGE-2-DEBIT-SPREAD-AB and EDGE-3-HOLD-POSTURE-PREREG both moved to `status:done-killed`.
> - **REVOKE:** both are read-only research artifacts (`analysis/recommendations/*`, `backtest/tools/*_ab_study.py`) — nothing to revert on the trading path; `spread_execution_enabled` was never flipped.

## [2026-07-15 ~00:15 ET] BUILD+LIVE — TWIN-B3/EDGE-1: passive-limit entry A/B LIVE on the crypto twin, first real passive fill quoted, +2 mechanism bugs caught-and-fixed on rep #1 [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-14 23:45:54 Tuesday EDT market_hours=False`).** Graduates entry_manager (T-W5, sim-shadow since 07-08) to LIVE measurement per TWIN-PROGRAM.md stream 3 + queue TWIN-B3/EDGE-1 (SEC-DERA: non-marketable limits ~halve the dominant transaction cost). **Crypto twin paper only — zero SPY-path changes.**
>
> - **Shipped:** `setup/scripts/crypto_twin_entry_quality.py` (passive actuator + A/B alternation + metrics) + `crypto_twin_core.place_entry_ab` wiring. Every LIVE twin entry now alternates deterministically (persisted `ab_counter`, even=marketable/odd=passive, tagged per order); passive rests a REAL mid-spread limit, entry_manager's frozen patience=3/policy=cancel governs, broker is fill authority (C11), fill-during-cancel race + partial-crumb flatten handled. Metrics → `automation/state/crypto-twin/entry-quality.json` (fill rate, abandonment, time-to-fill, improvement $/BTC + bps vs ask-at-signal; recent capped 500 per OP-22) + tier-tagged `ENTRY_QUALITY` journal rows. Passive miss = `PASSIVE_ENTRY_MISSED`, scheduler-compatible (branch retried, never a false INCIDENT). Fail-open everywhere (any passive degradation → marketable path).
> - **FIRST LIVE REP (end-to-end, real fill):** order `6ca7aa4b-6f2f-4ba2-869d-41339774e471` — limit BUY 0.0024 BTC @ **$64,764.15** vs quote ask $64,803.88/bid $64,724.41, rested **60.7s** (3 polls), **FILLED at the limit** → improvement **$39.73/BTC = 6.13 bps** vs marketable baseline. entry-quality.json cohort passive: fills=1, fill_rate=1.0.
> - **ROI ledger — rep #1 caught 2 REAL pre-existing bugs (both fixed + guard-tested):** (1) sell-qty `round(,8)` rounded UP past the fee-shaved balance → Alpaca 403 on SELL_ALL — sells now FLOOR to 8dp (fix verified live: the same close that 403'd then filled, order `8a9d662f`, twin back to flat; 9e-09 BTC sub-increment dust remains, economically zero). (2) `manage_positions` deleted the position record even when the close FAILED at the broker → orphaned real holdings — failed closes now KEEP the record (pre-tick state) + journal `CLOSE_FAILED` + retry next tick (max-hold path guarded too).
> - **Tests:** 26 new (`test_crypto_twin_entry_quality.py`: alternation determinism, metric computation on fixture fills, timeout/cancel, race, partial flatten, run_tick integration, scenario compat, BRANCH_REGISTRY untouched) + 5 bug guards. Twin-related suite **429 → 434 passed** (baseline 194 crypto_twin-only → 220), zero regressions. BRANCH_REGISTRY schema untouched; twin_sentinel parser unaffected (freshness keys only); unit-lot preserved (qty=3); no LIVE-ledger writes from tests (tmp-dir isolation).
> - **Graduation bar for SPY (documented in TWIN-PROGRAM.md §B3, NOT implemented):** ≥20 twin passive FILLS with fill-rate+improvement stats → then the frozen SPY A/B pre-reg. Twin numbers = mechanism evidence only, never SPY evidence.
> - **Known boundary (pre-existing, noted):** exit_manager `time_stop_15:50` insta-closes any twin position entered 15:50–23:59 ET on the next tick (graded always-acceptable) — rep #1's position closed this way 23s after fill, which is exactly how the 2 bugs surfaced.
> - **REVOKE:** revert the B3 commit — place_entry path returns byte-identical to pre-B3 (first entry per fresh counter is marketable; override flag is verification-only).

---

## [2026-07-14 ~23:55 ET] BUILD — EDGE-2 debit-spread mleg execution machinery SHIPPED **DISARMED** (arming = 1 params flag, gated on the A/B scorecard) [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-14 23:45:50 Tuesday EDT market_hours=False`).** Build lane for EDGE-2-DEBIT-SPREAD-AB (synthesis: `markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md`) — pure execution machinery so that IF the sibling lane's pre-registered A/B (`analysis/recommendations/debit-spread-ab.json`, NOT read by this lane) clears OP-11, arming is a flag-flip, not a build. **No live orders placed. No live-path consumer wired.**
>
> - **New `setup/scripts/spread_executor.py`:** Alpaca `order_class:"mleg"` vertical DEBIT spreads — `build_debit_spread_legs` (long ATM + short N-strikes-OTM, legs selected FROM the real chain, earliest-expiry-first), `net_debit_limit` (mid + marketable pricing from real quote shapes), `submit_spread` (armed-gate → leg validation → debit<width guard → 15:45 ET short-leg deadline → single POST), `close_spread` (ONE closing mleg, `sell_to_close` long + `buy_to_close` short — brackets/OTO still unsupported on options, exit_manager owns exits; **deliberately UNGATED**: an exit is never blocked by a config flag). API shape re-verified against docs.alpaca.markets tonight, incl. the load-bearing sign convention: **mleg `limit_price` positive = net debit, NEGATIVE = net credit** (close orders carry the negative).
> - **Gating:** `spread_execution_enabled: false` added to BOTH `automation/state/params.json` + `aggressive/params.json` with `_doc`s — only the literal bool `true` arms; flips ONLY per the A/B scorecard clearing OP-11 (kill criterion: OP-16 anchor regression). `ParamsModel` is `extra="allow"` — additive keys contract-safe.
> - **Cash/settlement fidelity:** a placed spread's net debit records `debit×qty×100` into the SAME Rule-7 settlement ledger heartbeat_core feeds (`settlement_ledger.record_entry`, fd09a78) — spread capital commitments debit the settled pool exactly like single-leg premium. **Pin risk:** SPY is PHYSICAL settlement — short-leg-alone-ITM assignment ≈ $56K we don't have; hard guard refuses any NEW spread at/after 15:45 ET and the module docstring binds the post-scorecard integration to close both legs by then.
> - **Tests:** `backtest/tests/test_spread_executor.py` → **37 passed in 0.13s** (fresh this session): leg construction both sides × widths 1/2/5, chain-shape tolerance, credit-geometry refusal, mid/marketable pricing from quote fixtures, RED-proofed never-armed guard (broker POST monkeypatched to AssertionError — proves disarmed paths never touch the wire; + a live-file assertion that goes RED if either params.json is flipped without updating the guard WITH the scorecard), settlement-ledger integration (placed=debited, refused/failed=untouched, bold→aggressive path), deadline guard, close-mleg construction + negative-credit limit.
> - **Dry-run against the REAL chain (read-only, quoted):** SPY spot 752.05 → C/width-1: long `SPY260714C00752000` + short `SPY260714C00753000`, quotes (close, 15:59:59 ET) long 0.15/0.17 × short 0.03/0.04 → net debit mid **$0.12** / marketable $0.14, qty-3 notional $36. P/width-2: long `SPY260714P00752000` + short `SPY260714P00750000`, mid $0.21, qty-3 notional $63. `armed: false` confirmed from live params in the same output.
> - **What arms it (nothing else):** A/B scorecard clears OP-11 → flip `spread_execution_enabled` true (per account; Bold separate per C29) + update the RED-proof test with the scorecard ref + the separate heartbeat_core/exit_manager wiring step (integration point documented in the module docstring). REVOKE: key stays false / delete it — byte-identical to pre-build.

---

## [2026-07-14 ~23:50 ET] HYGIENE+RELEASE — EDGE-KILL-LEDGER closed in the strategy-space registry (5 DEAD family rows) + queue fold + audit-GREEN push [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-14 23:48:22 Tuesday EDT market_hours=False`).** Worker-tier hygiene+release lane (no OPRA, no builds). Three jobs, all done:
>
> **1. EDGE-KILL-LEDGER (registry closure):** 5 formal DEAD rows appended to `analysis/backtests/STRATEGY-SPACE-REGISTRY.jsonl` (6067→6072 lines, all 5 verified JSON-parse-clean post-append; schema matched to the `mechanical_external_timing_64families` family-closure precedent; each row carries what / why-killed / evidence-artifact / reopen-condition = "new NON-OHLCV data only"; cross-linked `markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md`):
> - `gex_dealer_gamma_alpha_family` — 1,972-day SPY study: no lift after VIX+ATM-IV controls; CBOE de-minimis 0DTE MM flow (~0.2% of liquidity); internal `b4-gamma-wall-interaction.json` INFEASIBLE_NO_HISTORICAL_DATA. gex_context stays calm-regime descriptor only.
> - `orderflow_imbalance_intraday_family` — properly-lagged OFI OOS R²~3%, Sharpe ~0.12, decays away from HFT horizons.
> - `ohlcv_bar_pattern_mining_family` — two independent internal batteries (futures Phase-1: 0/12 DOES_NOT_TRANSFER 07-02 + 0/96 KILL-all-seeds 07-09; trendline 12/12 break + 12/12 fade FAIL 07-14) converging with the external 14-family/947-day battery. Closes NEW mining only; validated setups stay live.
> - `post_news_drift_family` + `volume_magnitude_signal_family` — precise nulls; news stays defense-only (blackout/veto), volume stays confluence-only.
>
> **2. Queue fold (`automation/overnight/queue.md`):** EDGE-KILL-LEDGER → done. FUTURES-PHASE1-BATTERY → done-kill (stale checkbox; battery ran 2026-07-09, KILL all 3 seeds, scorecards exist — artifact wins over checkbox). FUTURES-FILLSIM-ARM → done-folded-superseded (dependency KILLed; futures arming path = FUTURES-MIRROR-SHADOW forward evidence, currently 0/20 round trips). BOLLINGER-MES-SWING-PORT-SPEC → closed-superseded (a new OHLCV battery on futures = the registry-closed class; bollinger_squeeze's validated 0DTE lane untouched). **FUTURES-MIRROR-SHADOW verified no-contradiction and STAYS** (forward paper evidence, not OHLCV mining). **TWIN-B7-FREE-MODEL-BENCH untouched (stays).** Synthesis doc's queue section updated with statuses.
>
> **3. Release:** `python setup/scripts/github_audit.py` → **"VERDICT: GREEN -- safe to push"** (6936 tracked files, no findings). Push executed after-hours (23:4x ET), pathspec-committed hygiene files only; push confirmation quoted in the session report (HEAD == origin/main verified post-push).

---

## [2026-07-14] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-02..2026-07-08), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-08). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-526.56); Bold_ATM_1+2=YELLOW ($-262.0)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-07-14 ~20:42 ET] D — RULE 7 REWRITE: cash-account settlement gate REPLACES the fictional margin-PDT block that halted core Safe all day — shipped paper-side, proposed Rule 7 rewrite below for J ratification [REVOKE-report + doctrine proposal]

> **Context (`et_clock.py`: `2026-07-14 20:42:18 Tuesday EDT market_hours=False`).** J flagged core Safe blocked all day on `RISK_DENY_PDT` (`circuit-breaker.json day_trades_used_5d: 7`). Verified LIVE (not from memory) before touching anything: both core accounts — Gamma-Safe-2 `PA3DHPT7KIQE` and Gamma-Risky-2 `PA33W2KUAT40` — return `multiplier: "1"`, and Alpaca reports `pattern_day_trader` / `daytrade_count` as **null** on both. That's not missing data — Alpaca returns null there BECAUSE PDT is structurally inapplicable to a cash account. Full research (`markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md`, all claims sourced live 2026-07-14): FINRA Rule 4210's day-trade-counting PDT framework is, and always was, **margin-account only** — a cash account was never subject to it — and FINRA retired even the margin-account version of it 2026-06-04, replacing it with real-time intraday-margin-deficit monitoring. The constraint that actually binds a CASH account is Good-Faith-Violations (GFV) / freeriding under Reg T: a cash account may re-trade freely on SETTLED funds; funding a new entry from TODAY's still-unsettled closing proceeds (options settle T+1) and closing that new entry the same day is a GFV. `setup/scripts/pdt_tracker.py` had zero representation of settlement at all — it counted trade PAIRS in a rolling window, a completely different mechanism.
>
> **Concrete cost of the bug, today alone:** 4 real `RISK_DENY_PDT` denials on core Safe (`core-decisions.jsonl` @10:38/13:36/13:37/13:38 ET), each individually well inside every real risk control (notional $207-$357 vs the $1,746.63 SOD equity and Rule 6's 30% cap). None of the 4 was a GFV risk under the real cash-account model — replayed all 4 sequentially (worst case, zero exits crediting anything back) and the cumulative notional ($996) never exceeded the settled pool. Provenance layer on top: the `day_trades_used_5d=7` count itself partly reflects fill history INHERITED from the account's 2026-07-11 repoint (commit `61cfca0`, prior life as fleet arm `safe-1`) — a second, compounding bug.
>
> **Shipped (paper-side, reversible, guard-tested):**
> - `backtest/lib/risk_gate.py#check_order` gains `params.pdt_gate_mode`: `"margin_pdt"` (LEGACY — function-level default when the key is absent, so every pre-existing caller/test is byte-identical, unchanged) vs `"cash_settlement"` (NEW — gates on a settled-cash pool + a `CODE_SETTLEMENT` deny code; requires the caller to supply `settled_cash_available` + `same_day_entries_used`, both fail-CLOSED if missing — same posture as every other required numeric input in this module).
> - New `setup/scripts/settlement_ledger.py`: per-account daily JSON ledger. Starts each ET day with the broker's actual SOD cash (genuinely settled — both accounts are flat overnight). Each entry DEBITS its notional; closes do NOT credit back intraday (today's proceeds are unsettled until T+1 — the real GFV mechanism, modeled directly rather than approximated). Fail-open on I/O errors (matches `pdt_tracker.py`'s established precedent for this exact gate family — a ledger read/write failure can only widen availability, never invent a new block).
> - `setup/scripts/heartbeat_core.py#_execute` wired: computes settlement status before `check_order`, debits the ledger only on a REAL accepted placement (never on dry/shadow calls or a `PLACE_FAIL`).
> - Both live accounts' `params.json` now default to `pdt_gate_mode: "cash_settlement"` + `max_same_day_roundtrips: 5` (generous sanity cap, belt-and-suspenders on top of the settlement math). **Revert is one line**: set the key back to `"margin_pdt"` (or delete it) — byte-identical to pre-2026-07-14 behavior.
> - **Blast-radius finding + fix, before shipping:** `automation/state/fleet/fleet_executor.py#finalize` reads the SAME shared `params.json` files but never computes the new settlement inputs — inheriting `cash_settlement` mode from the shared file would have fail-closed EVERY fleet-arm order to `UNREADABLE_INPUT` (fleet arms are outside this task's scope; they're a separate, still-ticking 128x/day component per today's fill-funnel). Pinned `fleet_executor.finalize()` to force `pdt_gate_mode="margin_pdt"` regardless of the caller's params dict — fleet arms are byte-identical, unaffected. `crypto_twin_core.py`, `pre_order_gate.py`, `backtest/lib/{orchestrator,cap_admission}.py` all build their own inline params dicts (never read the shared file's new key) — confirmed unaffected, no change needed.
> - `pdt_tracker.py` NOT deleted — kept for legacy-mode revert + the existing VISIBILITY surfaces (`self_check.py`/`firm_brief.py`) that read its count independent of which rule gates the order.
>
> **Guard tests, all fresh this session:** `cd backtest && python -m pytest tests/test_risk_gate.py tests/test_settlement_ledger.py tests/test_pdt_tracker_2026_07_06.py tests/test_pdt_tracker_visibility.py tests/test_min_entry_premium_floor.py tests/test_firm_brief_pdt_section.py tests/test_self_check_pdt_status.py -q` → **163 passed**. `automation/state/fleet` → `python -m pytest test_fleet_executor.py test_structure_stop_wiring.py -q` → **48 passed** (incl. the new blast-radius pin test). Rule 5 (kill-switch) and Rule 6 (risk cap/min-contracts) guards untouched and still green in the same run — this change touches ONLY gate #2 (PDT/settlement); the surrounding gate order and every other rule's tests pass unmodified. New tests: 17 cash_settlement-mode tests in `test_risk_gate.py` (incl. a byte-for-byte replay of today's 4 real blocked trades — all Allow under the new gate) + 13 in `test_settlement_ledger.py` (pure-function + I/O fail-open + an end-to-end replay of today's exact sequence) + 1 fleet blast-radius pin.
>
> **No live orders. No Rule 5/6 changes.** Paper-only, both accounts already default to the new mode (J's "act, don't ask" standing authorization for paper-side, reversible engine fixes — OP-0). Not yet committed to git as of this entry.
>
> ---
>
> ### PROPOSED RULE 7 REWRITE (for J ratification — the 10 rules are J's, not self-edited)
>
> **Current Rule 7:** *"PDT awareness. Under $25K: 3 day-trades per rolling 5 business days (margin) or respect settlement (cash)."*
>
> The current text already technically distinguishes margin vs cash — the BUG was that the code never implemented the "(cash)" half, and the engine treated both accounts as margin. Proposed replacement, now that the cash-account gate actually exists and both accounts are confirmed cash:
>
> > **7. Settlement awareness (cash accounts).** Both Gamma-Safe-2 and Gamma-Risky-2 are CASH accounts (verified: `multiplier=1`, Alpaca `pattern_day_trader`/`daytrade_count` both null) — the margin-account Pattern Day Trader rule (FINRA Rule 4210, 4-trades/5-days, $25K minimum) does NOT apply and never has. The real constraint is SETTLEMENT: a new entry may not be funded by today's own still-unsettled closing proceeds (options settle T+1) — doing so and closing that position the same day is a Good Faith Violation (GFV) under Reg T. The engine enforces this via a daily settled-cash ledger (`setup/scripts/settlement_ledger.py`) that debits each entry's notional from the day's settled pool and never credits closes back intraday — naturally capping same-day entries at roughly (SOD settled cash) / (typical notional per entry), currently ~2-3 for both accounts. A generous `max_same_day_roundtrips` sanity cap sits on top. If either account is ever converted to margin (not currently planned), `pdt_gate_mode` reverts to the classic day-trade-count rule via a one-line params.json change.
>
> Sources for this proposal: `markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md` (live-sourced 2026-07-14, FINRA Regulatory Notice 26-10 + broker-compliance pages fetched directly). Ratification just means updating `CLAUDE.md`'s Rule 7 line + the `## The 10 rules` section to this text (or J's edited version) — the CODE is already live under this model tonight; the doctrine text is the only thing lagging.
>
> **Lesson folded:** `markdown/doctrine/LESSONS-LEARNED.md` L200 — "verify the account type before modeling the rule that governs it."

## [2026-07-14 ~19:49 ET] C — TREND-ALIGNMENT PHASE 1: KILL confirmed, look-ahead leak found+fixed, corrected re-run REINFORCES the kill [REVOKE-report]

> **Context (`et_clock.py`: `2026-07-14 19:49:38 Tuesday EDT market_hours=False`):** worker-tier synthesis of the trend-alignment-correlation study (context-enrichment Phase 1, following Phase 0's shadow-only `context-bundle.json` tag, commit `b1597a6`). Question: does multi-timeframe (daily/hourly/15m) trend alignment predict trade outcome? Frozen pre-reg: `analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json`.
>
> **Original scored run (commit `6400a61`):** P1 (MODELED, SS-B replay @ OTM-2, n=250 canonical `ribbon_ride` cohort, real OPRA bars) OOS n=90 rho=-0.054 (null); P2 (MEASURED, real broker fills, n=110 engine episodes) rho=+0.041 (opposite sign — condition_5 corroboration FAILED); P3 (J's OP-16 anchor, n=7, context-only) rho=+0.150. Kill ladder 3/4 conditions failed (condition_1 OOS-positive-beats-null FALSE, condition_4 both-halves-same-sign FALSE: first half +0.008, second half -0.146). **P1 verdict = KILL, overall verdict = KILL.**
>
> **Adversarial verify pass (too-good + look-ahead hunts) found a REAL bug, but it didn't overturn the verdict.** `alignment_for_decision`'s `_slice()` in `backtest/tools/trend_alignment_correlation_study.py:191` sliced on bar-OPEN (`timestamp <= ts`) instead of bar-CLOSE (`timestamp + granularity <= ts`) — every entry_ts is intraday, so the still-forming daily/hourly/15m bar's already-realized future close leaked into every single historical reconstruction (systematic C6 violation, hand-verified on 2 real P1 signals). Direction of the bias: TOWARD manufacturing a spurious POSITIVE correlation (a leaked same-day move tends to agree with a winning trade's own direction) — yet P1 still scored null/negative *despite* that pro-hypothesis bias, so the pre-fix KILL was not overturned by the leak, if anything it was conservative.
>
> **Fixed the leak and RE-RAN the frozen scoring pass** (not just reasoned about it): `_BAR_GRANULARITY` map (daily=1day / hourly=1h / m15=15min) applied per-timeframe in `_slice`, +2 regression guard tests (`test_alignment_for_decision_excludes_still_forming_bar_mid_span` — a decision_ts strictly mid-bar, the exact shape every prior guard test missed since they only ever used exact fixture-row timestamps). 31/31 tests green (Phase 0 + Phase 1 suites). Self-check re-verified: P1 replay still reproduces `ribbon_ride_strike_exit_ab.py`'s certified `replay_cell()` output byte-for-byte (`ref_total=4465.6`, `my_total=4465.6`).
>
> **Corrected numbers — the kill got MORE decisive, not less:**
>
> | Metric | Pre-fix (leaky) | Post-fix (bar-close correct) |
> |---|---|---|
> | P1_OOS spearman rho | -0.054 (p=0.61) | **-0.150 (p=0.16)** |
> | P2_engine spearman rho | +0.041 (p=0.67) | **-0.143 (p=0.14)** |
> | condition_5 (P2 corroborates P1's sign) | FAIL (opposite signs) | **PASS (both negative)** |
> | condition_2 (monotonic-ish, ≤1 inversion) | PASS | **FAIL** (bucket means -3:$200.40, -1:$42.23, +1:$56.53, +3:-$148.43 — not monotone) |
> | Full-alignment bucket (+3), the strongest form of the hypothesis | worst-performing (found in adversarial pass, didn't move the mechanical verdict) | **still the worst bucket, now visible directly in the frozen scoring output** ($-148.43 mean, n=16) |
>
> Post-fix, P1 and P2 now AGREE in sign (both mildly negative, neither statistically significant, p>0.10 both — don't over-read a real effect here) instead of disagreeing as they did pre-fix. That's a materially CLEANER, more internally-consistent kill than the one that shipped in `6400a61`.
>
> **Verdict: KILL. No orders placed, no live params/config touched.** Phase 0's `context_bundle`/`alignment_score` tag on the decision row stays LOGGED-ONLY per the original Phase 0 design — it was never wired to any gate/veto/sizing input, and this result gives no reason to wire it. A kill here is a valuable, honest result: it says the mechanical entry logic (trigger + structure_veto) already prices in what multi-TF alignment would add: the SAME structure primitive (`market_structure.analyze_structure`) already runs inside `structure_veto` on the live 5m bars at entry time, so a slower-cadence daily/hourly/15m read on top of it appears to be redundant information, not incremental edge — bolting a slower-cadence read of the same primitive on top adds noise, not signal, on this engine's current entries.
>
> **Shipped:** `backtest/tools/trend_alignment_correlation_study.py` (fix), `backtest/tests/test_trend_alignment_correlation_study.py` (+2 guards, 9→11 tests, all pass), `analysis/recommendations/trend-alignment-correlation.{json,md}` (re-scored), `automation/overnight/queue.md` (TREND-ALIGNMENT-PHASE1-CORRELATION moved to Completed, done-killed). Not yet committed to git as of this entry — see next action.
>
> **No Phase 2 spec written.** Per the branching instructions this session ran under: Phase 2 (conviction-modulation spec) only gets written on a CLEAN look-ahead pass with surviving separation. This result is neither — the leak was real (now fixed) and the separation, even corrected, is null/mildly negative. Phase 2 does not ship. Any future phase that reuses `alignment_for_decision`'s bar-close slicing pattern gets the FIXED version for free (single source of truth, same file) — no separate follow-up item needed.

## [2026-07-14 ~17:15 ET] B — SHIP GATE: closed TRENDLINE-CONVICTION-OVERRIDE (KILL), re-verified A5-PREMARKET (ship candidate, already committed, test-count claim corrected), re-confirmed the 5 evening scorecards' verdicts against their own artifacts, ran github-audit, pushed to origin/main [REVOKE-report]

> **Ship gate ran at 17:08 ET** (`et_clock.py`: `2026-07-14 17:08:53 Tuesday EDT market_hours=False` — quoted, not assumed). Re-verified all 6 evening scorecards against their actual artifact files rather than trusting the handoff summary. Only one artifact had unclosed loose ends (TRENDLINE-CONVICTION-OVERRIDE, below) and one had a claim discrepancy worth flagging (A5-PREMARKET, below); the other 4 (deadzone/bearFloor/fade/veto) were already correctly closed in `queue.md`/`STATUS.md` by earlier same-day sessions with verdicts matching their artifacts — re-read, not re-run, nothing to add.
>
> **TRENDLINE-CONVICTION-OVERRIDE — closed KILL.** The audit crew's own frozen `trendline-structure-conviction-preregistration.json` had already been run (`backtest/tools/trendline_conviction_override_study.py`, result files timestamped 14:40 ET) but sat uncommitted and unclosed in `queue.md`. Re-verified the result file's own numbers before closing anything: n=93 (IS=85/OOS=8) ELITE-bull level_reclaim signals in VIX[15,17.5). TL-A/TL-B FAIL condition_1 outright (rescued mean -$0.28/tr, n=18, WR=22.2%). TL-C mechanically PASSes (+$23.57/tr, n=26) but the study's own leave-largest-winner-out diagnostic shows one +$1,949.80 trade is 318.2% of the rescued population's net P&L — excluding it flips the mean to -$53.48/tr. Condition_2 (remainder no-regression) and condition_4 (no-lookahead, `backtest/tests/test_trendline_conviction_override_no_lookahead.py`, **re-ran fresh this session: 2/2 passed**) both PASS for all 3 candidates. **No candidate clears the evidence bar — block_elite_bull's VIX[15,17.5) band stands, nothing overrides it.** Committed the 5 result/study/guard files + the pre-registration's in-place `RUN_COMPLETE` status update (no re-pick — result pointer only), closed the item in `queue.md`. Zero params/config/trading-path edits, zero orders.
>
> **A5-PREMARKET-DETERMINISTIC-FALLBACK — re-verified, ships as already committed (`79bac4d`), one claim corrected.** Re-ran both guard suites fresh this session: `test_premarket_deterministic_fallback.py` **23/23 passed**, `test_premarket_fallback_wiring_guard.py` **7/7 passed** (30/30 combined). **Correction to the commit message / queue.md / STATUS.md 16:40 ET entry's claim of "11/11" wiring tests and "34/34" total:** `grep -c "^def test_" backtest/tests/test_premarket_fallback_wiring_guard.py` and a fresh pytest collection both show **7 tests in that file, not 11** (30 total, not 34). This does not change the ship verdict — all 30 actual tests are green, the feature is correctly fail-safe/additive-only per its own code, and the discrepancy looks like a stale draft count left in the commit message rather than a missing/broken test — but OP-33 requires flagging a claim that doesn't match a fresh count rather than silently repeating it. Full `backtest/` collection re-run fresh this session: **3843 tests collected, 2 pre-existing collection errors** (`backtest/autoresearch/_archive/sniper/t48_sniper_watcher_test.py`, `backtest/futures/tastytrade_e2e_test.py` — both last touched in commit `5d84a5e`, unrelated to and pre-dating today's premarket work; the "3711 tests collects clean" claim in the same commit message is also stale, likely from a smaller collection scope, not a regression this session introduced or found). No further action needed — A5 stays shipped, no revert.
>
> **github-audit run before push:** `python setup/scripts/github_audit.py` → `GREEN -- 6921 tracked files checked in 48.6s, 0 findings, safe to push`. **Pushed:** `git push origin main` — `8d19186..3a8cd62 main -> main` (2 commits, 89 ahead → synced; remote warned on a pre-existing 66.95MB `rejections.jsonl` LFS-recommendation, non-blocking, not a secrets finding).
>
> No orders placed. No live params/config edits (all 5 evening research artifacts were KILL/KEEP-CURRENT verdicts already correctly landing as no-ops; A5 was the only SHIP_CANDIDATE and it was already applied by an earlier session before this gate ran).

**Ship table (2026-07-14 evening batch):**

| Item | Verdict | Evidence (n, key numbers) | Action taken |
|---|---|---|---|
| A5-PREMARKET-DETERMINISTIC-FALLBACK | **SHIPPED** | 30/30 guard tests green (re-run fresh; commit claimed 34/34 — corrected, not a functional gap) | Already committed `79bac4d` by earlier session; re-verified this gate, test-count claim corrected in STATUS.md |
| TRENDLINE-CONVICTION-OVERRIDE | **KILLED** | n=93; TL-A/B mean -$0.28/tr FAIL cond.1; TL-C +$23.57/tr mechanically PASSes but outlier-dependent (1 trade = 318% of P&L, ex-outlier -$53.48/tr) | Committed result + closed `queue.md` (commit `1908388`) |
| VIX-DEADZONE-MAP | **KEPT (block_elite_bull)** | SS-B n=28 KEEP (-$3,873.60 vs old -$560.00); only 28/146 (19.2%) of today's blocks were VIX-attributable | Already closed by earlier session; re-read only |
| A3-BEAR-VIX-FLOOR-SSB | **KILLED (voided pre-run)** | 0 live consumers in `gates.py`'s 15-gate list; `vix_entry_thresholds` vestigial | Already closed by earlier session; re-read only |
| TREND-FADE-PREREG | **KILLED** | 12/12 cells FAIL; the 1 mechanical PASS downgraded on post-hoc stability audit (OOS positive total = 1 concentrated month) | Already closed by earlier session; re-read only |
| A6-VETO-GRADE | **KEPT (veto layer)** | 29.73% false-veto rate today vs 6.67% historical — misses the pre-declared 30% trigger by 0.27pp; net dollar value +$565.50 today | Already closed by earlier session; re-read only |

**Blocked on evidence (none this session):** every candidate that reached a KILL verdict did so on its own frozen pre-registration's pass_bar or a disclosed robustness diagnostic — no item was blocked short of a verdict for lack of time/resources.

## [2026-07-14 ~17:06 ET] A4 — TREND-FADE-PREREG (OPRA-sequential job 3/3) RUN — 12/12 cells FAIL, KILL [REVOKE-report]

> **TREND-FADE-PREREG per queue.md**, following S1's break-continuation battery (12/12 KILL, disclosed-not-tested: opposite-direction null beat the real trade OOS in 10/12 cells). Froze `analysis/recommendations/prereg-trendline-fade-battery-2026-07-14.json` BEFORE any run — 3 fade variants (F1_fade_immediate = S1's opposite-direction null promoted to a first-class hypothesis; F2_fade_reclaim_confirmed = NEW, causal no-look-ahead reclaim-of-the-line detection within the 10-bar horizon; F3_fade_low_volume = NEW, mirror of S1's volume≥1.5 continuation filter inverted to volume_ratio<1.0 low-conviction breaks) × 2 line families (wick/body, never blended) × 2 directions = 12 cells, same OOS_BOUNDARY/seed=1407/SS-B exit shape/BH-FDR alpha=0.10 as S1 for direct comparability, plus a load-bearing `break_direction_null` (does fading actually beat taking the original break trade S1 already killed).
>
> **Ran verbatim** via new `backtest/tools/trendline_fade_battery.py` (read-only reuse of `trendline_break_replay.py`'s line geometry, never touches the audit-owned subsystem) on the full 380-day `break-dataset.jsonl` (78,191 lines) through the LIVE exit_manager core (SS-B shape) on real local OPRA option bars — 51,534 candidate episodes, 180.8s. **Mechanical result per the frozen pass_bar: 1/12 cells PASS** (`F3_fade_low_volume::body::resistance(fade-of-bullish)`, n=4072, oos_expectancy=$78.16/tr, BH-FDR-significant, beat both nulls).
>
> **That PASS did not survive scrutiny.** Its own summary carried a tell (`is_expectancy=$3.79/tr` ≈ 0 vs `oos_expectancy=$78.16/tr` → `wf=20.6`, an extreme ratio from a near-zero denominator) — exactly the shape OP-33/`/fable-too-good` says to hunt before reporting. This study's own frozen pass_bar never tested sub-window stability, but the mission's OP-11 auto-ratify bar does (`OOS_positive AND WF≥0.70 AND sub_window_stable AND anchor_no_regression`), so before any ship/REVOKE call the cell was re-derived (zero threshold/variant/null edits — pure diagnostic, `backtest/tools/_fade_battery_artifact_hunt.py`) for monthly/quarterly/date-concentration checks. **Result: decisive fail.** OOS-only monthly: 2026-01 = **−$630/tr**, 2026-02 = **−$322/tr** (2 of 7 months strongly negative); **the entire OOS-positive total ($111,139) traces to March 2026 alone** (+$169,955 — OOS excluding March is net **−$58,816**); **top-10 single days = 249.2% of the cell's ENTIRE full-sample total_pnl** (2026-03-27 alone = 52.4%, one day, 38 trades). A concentration artifact, not a generalizable edge. Downgraded to FAIL, disclosed in-place (not silently discarded) via a new `post_hoc_stability_audit` block in the scorecard JSON + a matching section in the .md.
>
> **Final verdict: 12/12 cells FAIL.** Both break-continuation (S1) AND break-fade (this study) are now KILLED for this signal source on this dataset/exit-shape — the 10/12-cells disclosure that motivated this study does not translate into a standalone tradeable edge once tested as its own pre-registered hypothesis with its own nulls and (critically) sub-window stability. **This is a publishable KILL, not a gap** — per the no-repick clause, FAIL/INCONCLUSIVE is informative, not a reason to adjust and re-run.
>
> Zero orders placed. Zero live params/config/trading-path edits (ran after 16:05 ET regardless, per HARD RULES — nothing here clears the OP-11 bar to ship anyway). Sequential OPRA lane released clean after this job (was job 3/3; job 2/3 `A3-BEAR-VIX-FLOOR-SSB` voided itself earlier, lane was already clear). Files: `analysis/recommendations/prereg-trendline-fade-battery-2026-07-14.json` (new, frozen), `backtest/tools/trendline_fade_battery.py` (new), `backtest/tools/_fade_battery_artifact_hunt.py` (new, ad hoc diagnostic), `analysis/recommendations/trendline-fade-battery.{json,md}` (new scorecard), `automation/overnight/queue.md` (TREND-FADE-PREREG marked done).

## [2026-07-14 ~16:40 ET] A5 — PREMARKET DETERMINISTIC FALLBACK built + wired + guard-tested (shipped, not yet fire-tested live)

> **Built the spec from `analysis/deep-research/2026-07-14-premarket-reliability.md`** (3-week audit: premarket LLM step missed 25-44% of trading days across 3 failure shapes -- CCR/auth outage, hollow-success exit-0-empty-predictions, reaped-silent -- all degrading to the same stale `today-bias.json`). New `setup/scripts/premarket_deterministic_fallback.py`: $0, pure Python, zero LLM/MCP/CDP dependency. Mechanical bias formula (premarket-close-vs-prior-close pct_change + overnight-range position, 5bps deadband) over the SAME un-blockable Alpaca-REST/yfinance paths `sight_beacon.py`/`heartbeat_core.py` already survive the exact outages that kill the LLM. VIX context reads the EXISTING `params.json#vix_iv_regime_bands`/`vix_entry_thresholds` (never a new hardcoded number). `key_levels` prefers today's already-fresh `key-levels.json` (an independent deterministic producer) filtered to near-price non-expired entries, falls back to prior-day H/L computed straight from the fetched bars if that file is itself stale. `news_calendar` delegates to `macro_calendar.py#run(do_fetch=False)` -- genuinely sourced, never fabricated. The LOAD-BEARING `safe_equity_confirmed`/`bold_equity`/`daily_loss_budget_dollars` fields are read from the SAME run's already-fresh `daily_loss_guard.rearm()` output (that step runs unconditionally before the LLM attempt) -- no extra network call, and it degrades to a direct REST fetch only if that rearm itself hadn't landed today. `rule_version_pin` reads `RULE_VERSION_EXPECTED` straight out of `premarket.md`'s own constant (single source, never hand-duplicated). Every successful write carries `degraded:true, source:"deterministic_fallback"`, `updated_by` that cannot match the OP-33 gate's banned-hand-rebuild-author list, and ZERO `falsifiable_predictions` (never fabricates a qualitative call it can't back).
>
> **FAIL-SAFE by design:** if the PRIMARY input (SPY 5m bars) is unavailable from BOTH Alpaca REST and yfinance, the script returns `ok:false` and writes NOTHING -- verified live: `run(fetch_bars=lambda: ([], "..."))` leaves the target file untouched. Secondary inputs (VIX, equity, key-levels, news) degrade independently with an explicit null + `readiness_flags` note rather than blocking the whole write or inventing a number.
>
> **Wired into `run-premarket.ps1`** strictly inside the pre-existing OP-33 `deliverableMsg` failure branch (only fires after BOTH LLM attempts are exhausted AND the silent-failure gate has already determined the LLM produced nothing usable) -- never overrides a real LLM pass. After invoking it, the wrapper RE-READS `today-bias.json` and only trusts it if `date==today AND degraded==true AND source=="deterministic_fallback"`; on a confirmed fresh degraded write it logs a NEW `### DEGRADED: premarket {date}` STATUS.md heading (distinct from the pre-existing `### BROKEN:` heading -- this is spec point 4's explicit "distinguish stale from degraded-fresh" ask) and reclassifies `exit` 3->0 (covered, not silent -- a degraded-fresh bias is not a hard scheduler failure). If the fallback ALSO fails, the original BROKEN/exit=3 path is untouched. `self_check.py` gained the parallel distinction: a `PREMARKET DEGRADED` problem (verified via `_problem_is_broken()` to classify as DEGRADED not BROKEN) that only fires when the file IS fresh-dated but carries the fallback's markers -- the pre-existing date-only `PREMARKET STALE` check still fires first/instead when the date itself is stale.
>
> **Verification this session (OP-33, quoting the actual checks, not claiming):**
> - `python -m py_compile` + `ast.parse` clean; live dry-run against REAL current market data produced a plausible bullish bias (`premarket_close=751.91 vs prior_close=749.13, pct_change=0.0037, overnight_position=0.651 -> bullish`, VIX 16.5 -> MID_below_bear_threshold) with all load-bearing fields populated (`safe_equity_confirmed=1746.63`, `bold_equity=1963.04`, `rule_version_pin.match=true`).
> - DST-aware offset verified both ways: July fire -> `-04:00`, a January-dated injected fire -> `-05:00` (the exact TZ-SYSTEMIC bug class this rig has scars for -- no hardcoded `-04:00` left in the new file).
> - `backtest/tests/test_premarket_deterministic_fallback.py`: **23/23 green** (bias formula incl. deadband + signal-disagreement + no-prior-data cases, VIX threshold bucketing LOW/MID/HIGH x above/below, rule-version-pin match/mismatch/missing-file, key-levels fresh-then-fallback-then-no-data, and the STALE-DATE-DETECTION guard: fed ancient 2019-dated bars + a 2026-08-03 injected clock, asserted the output `date` is 2026-08-03 -- proving the fallback can never reproduce the 06-30 class of bug where a write LOOKS fresh-dated without actually being produced this run).
> - `backtest/tests/test_premarket_fallback_wiring_guard.py`: **11/11 green**, and **RED-proofed live this session** -- temporarily broke the `### DEGRADED:` heading (changed it to `### BROKEN:`), reran the suite, confirmed `test_wrapper_distinguishes_degraded_from_broken_in_status_md` FAILED as expected, then reverted and reconfirmed green (`git diff --stat` shows only the intended 35-line insertion, no corruption).
> - Companion guards unaffected: `test_premarket_deliverable_gate_guard.py` (4/4), `test_self_check_pdt_status.py`+`test_self_check_tradeability.py` (17/17), `test_graduated_guards.py -m "not slow"` (71 passed/1 skipped, was already skipped pre-change). Full `backtest/tests/` collection: **3711 tests, zero collection errors** (no import breakage from the 2 new files). `run-premarket.ps1` PS 5.1 `Parser::ParseFile` clean.
>
> **NOT yet verified (honest gap, UNVERIFIED label per OP-33):** this has never fired for real inside `run-premarket.ps1`'s actual failure path (would need a genuine LLM-step failure tomorrow morning, or a deliberate forced-failure dry run of the wrapper itself, neither of which this after-hours session can safely do without either faking a failure signal or waiting for market hours). The next real premarket LLM miss is the first live proof; watch tomorrow's `automation/state/logs/premarket-*.log` for a `FALLBACK exit=` line and `today-bias.json#degraded` if that happens.
>
> Zero orders placed. Zero live trading-path/param edits (this is a pure failure-path addition per the mission brief's own framing, and landed after 16:05 ET regardless). Files: `setup/scripts/premarket_deterministic_fallback.py` (new), `setup/scripts/run-premarket.ps1` (+35 lines, additive only), `setup/scripts/self_check.py` (+9 lines), `backtest/tests/test_premarket_deterministic_fallback.py` (new, 23 tests), `backtest/tests/test_premarket_fallback_wiring_guard.py` (new, 11 tests), `automation/overnight/queue.md` (Completed entry `A5-PREMARKET-DETERMINISTIC-FALLBACK`).

## [2026-07-14 ~16:20 ET] A6 — TODAY'S FREE-MODEL VETOES GRADED same-day: 29.73% false-veto rate, BELOW the 30% pre-reg trigger by 0.27pp -- no doctrine change shipped

> **Ran `free_model_audit.py --subject heartbeat_veto --force` mid-day** (not waiting for tonight's scheduled cadence) per J's "make money this week" directive to check whether the 2 free-model veto lane's 22-vetoes-on-zero-trades day (queue.md VIX-DEADZONE-MAP) was itself a bad gate, before that pressure could turn into an evidence-optional rule change. Counterfactual-replayed all of today's veto/go decisions against real OPRA bars (`core-decisions.jsonl` `free_eval.veto`): **37 vetoes + 6 gos graded, not 22** (22 was VIX-DEADZONE-MAP's rough same-day headcount; 37 is the authoritative full-day count from the same log).
>
> **Result: today's veto-only false-veto rate = 11/37 = 29.73%**, vs the historical baseline **1/15 = 6.67%** (2026-07-11 scorecard, the largest prior veto sample) -- a 4.46x elevation. **Does NOT cross the pre-declared >30% pre-registration trigger** (misses by 0.27 percentage points, n=37 well over the n>=10 floor). Per the standing "never a vibe-flip" rule (queue.md's own VIX-DEADZONE-MAP language) and OP-33, did **NOT** write a veto-scope pre-registration today -- rounding 29.73% up to "basically 30%" under this week's P&L pressure would be exactly the evidence-optional move the bright line exists to prevent.
>
> **Net dollar framing (why this isn't a clean "gate failed" story either):** the 11 false vetoes cost $391.20 in foregone winners; the 26 true vetoes saved $956.70 in avoided losers -> **net veto value today is still +$565.50 positive**, despite the elevated false-veto rate. Cumulative (all-time, this subject) rate unchanged at 68.9%/151 evidence points, still not confident (bar 85%, streak 0/3).
>
> **Flagged forward, not force-shipped:** logged as `A6-VETO-GRADE-2026-07-14` in queue.md (status:done) with a note to watch the next 1-2 graded cycles -- if the elevated rate persists, cumulative evidence clears the bar honestly instead of needing today's number rounded up. No params/config/trading-path file touched. No orders placed. Scorecard: `analysis/free-model-audit/heartbeat-veto/2026-07-14-scorecard.md`.

## [2026-07-14] TRENDLINE BREAK BATTERY (S1) + CALL-VETO SS-B RE-VAL (S2) RUN -- S1: 12/12 cells KILLED (real, decisive), S2: premise false (nothing to re-validate) [REVOKE-report]

> **Full trendline review per J's "this needs a proper review" directive** (follow-on to today's TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14, which stayed read-only and froze a DIFFERENT spec of its own -- `trendline-structure-conviction-preregistration.json`, a conviction-override study, still `FROZEN_PENDING_RUN`, not run here, not this crew's artifact). Checked first whether that spec covered the break-entry battery the task asked for -- it doesn't (different mechanism: rescues blocked ELITE-bull signals, not an enter-on-break study) -- so froze a fresh one: `analysis/recommendations/prereg-trendline-break-battery-2026-07-14.json`, run VERBATIM after freezing (one mid-freeze fix to the V2 retest-confirmation window, made BEFORE any cell pnl was computed, disclosed in the prereg text itself, not a post-hoc re-pick).
>
> **S1 result: ALL 12 candidate cells FAIL.** 3 entry variants (V1 close-through-immediate, V2 break+retest, V3 break+volume-expansion>=1.5x) x 2 line families (wick/body, per J's anchor-family rule, never blended) x 2 directions (bearish/PUT from support breaks, bullish/CALL from resistance breaks), replayed on the FULL 380-day walk-forward population (`analysis/trendlines/break-dataset.jsonl`, G1) through the LIVE exit_manager core (SS-B shape, current shipped ribbon_ride params) on real local OPRA option bars -- 48,336 real episodes total (33,950 V1 + 3,179 V2 + 11,207 V3), zero subsampling needed (replay throughput ~1.3ms/episode, full run 187s). Every cell's expectancy is negative (-$41 to -$252/trade at qty=10), BH-FDR-significant (p approx 0 in 11/12 cells), OOS-negative, and none clears the null bar. **Informative sub-pattern (disclosed, NOT shipped or re-tested per the frozen no-repick clause):** the opposite-direction null (same timestamp/spot, flipped side) outperforms the real same-direction trade in 10/12 cells -- suggestive that trendline-break direction has near-zero or even adverse predictive value under this exit shape, but this was a NULL comparison, not a pre-registered candidate; a genuine "fade the break" study would need its own fresh pre-registration, not a re-pick on this one. Zero anchor-day (J's 7 OP-16 winner/loser days) participation in any cell. Runner: `backtest/tools/trendline_break_battery.py` (new, imports `trendline_break_replay.py`'s pure line-geometry helpers read-only, never touches `trendline_engine.py`/the drawing bridge/the audit doc). Full verdict table + per-cell nulls/WF/concentration: `analysis/recommendations/trendline-break-battery.{json,md}`.
>
> **S2 result: task premise was FALSE, not re-run as a re-validation.** The instruction asked to "find the original scorecard [for trendline-as-CALL-veto] and rerun under SS-B" -- searched `analysis/recommendations/` (grep for veto+trendline, zero hits across the 5 existing trendline recommendation files) and `strategy/candidates/` (10 dated Chef DRAFT attempts, 2026-06-26 through 2026-07-12, every one still `NEEDS-OOS`/`NEEDS-REAL-FILLS`/"unknown -- requires Stage-1 backtest," self-rated confidence 4/10). **No scorecard ever existed to go stale.** This independently reproduces today's own audit doc's Q2 finding (same conclusion, found separately). Fabricating a stand-in "original" would have been an OP-33 overclaim (misrepresenting an untested hypothesis as a previously-validated one), so S2 is delivered as: premise-false verdict + the search trail + a pointer to S1's bearish/support-break cells as the nearest real (but not equivalent) evidence + a correctly-scoped follow-up recommendation (a real CALL-veto A/B needs actual ribbon_ride CALL signal timestamps conditioned on trendline state, not built here -- out of today's scope). Full disclosure: `analysis/recommendations/trendline-call-veto-ssb-reval.json`.
>
> **No params/config/trading-path file touched. No orders placed. Audit-owned files (`trendline_engine.py`, drawing bridge, `TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md`, the audit's own conviction-override prereg) untouched, import-only.** Both scorecards are publishable KILLs per their own no-repick clauses -- a KILL is a first-class outcome, not a reason to adjust and re-run.

## [2026-07-14] PC SLEPT 7.5h OVERNIGHT, KILLING THE CRYPTO TWIN'S 24/7 PREMISE -- root cause found, ONE-LINE FIX FOR J TO RUN (not applied -- system/power settings are J's click, not mine)

> **JOB 4 (ultracode-review), report only, zero system changes.** `Get-WinEvent` (System log, Event IDs 42/1) confirms the box slept from **2026-07-13 22:01:46 PM local (Mountain) time** to **2026-07-14 05:35:27 AM local** -- **7h 33m** (matches the reported ~7.5h). **Correcting the task's own "22:01->05:35 ET" framing**: those are LOCAL (Mountain) clock times, not ET -- this is the exact "local time mistaken for ET" pattern CLAUDE.md's TZ doctrine already warns about (`project_tz_systemic_fix`). Converted properly via the event's own embedded UTC timestamps: **sleep = 2026-07-14T00:01:45 ET (12:01 AM), wake = 2026-07-14T07:35:26 ET (7:35 AM)** -- the twin was down through the entire pre-market/early-session window in real ET terms.
>
> **ROOT CAUSE (verified, not guessed): a MANUAL Start-Menu "Sleep" click, not an idle timeout.** Event ID 1074 (User32) at 22:01:43 local: *"The process ...StartMenuExperienceHost.exe (DABOX) has initiated the power off of computer DABOX on behalf of user DaBox\jackw ... Reason: Other (Unplanned)."* Immediately followed by Event 187 (Kernel-Power): *"User-mode process attempted to change the system state by calling SetSuspendState or SetSystemPowerState APIs,"* then Event 42: *"The system is entering sleep. Sleep Reason: Application API."* This is the Start Menu's own power-button Sleep tile being clicked by the logged-in user -- **not** a policy, **not** an unattended idle timeout, **not** the power button hardware switch.
>
> **Idle-timeout hypothesis DISPROVEN by direct evidence** -- `powercfg /query SCHEME_CURRENT SUB_SLEEP` shows `STANDBYIDLE` (Sleep after) = `0x00000000` (Never) on **both AC and DC**, and `HIBERNATEIDLE` (Hibernate after) = `0x00000000` (Never) on both too. Nothing was configured to sleep this box on its own -- there is no idle-timeout misconfiguration to fix. A `powercfg /change standby-timeout-ac 0` style command would be a no-op; already correctly set.
>
> **Wake source: genuinely unattributed.** `powercfg /lastwake` and the Power-Troubleshooter event both report `Wake Source: Unknown`. Checked the obvious candidate (a Task-Scheduler wake timer) and ruled it out: `Gamma_CryptoDaily`/`Gamma_GuardsNightly`/`Gamma_ScoutPremarket` all show `WakeToRun: False` and none of their trigger times align with 05:35 -- their 05:41 `LastRunTime` cluster is Task Scheduler's normal catch-up behavior for tasks that were missed *during* the sleep window, not the cause of the wake. Left unattributed rather than guessed.
>
> **THE FIX J CAN RUN HIMSELF (not applied -- system/power settings are prohibited for me to change per the standing safety rule):** since this was a deliberate Start-Menu click and idle timeouts are already correctly Never/Never, there is no idle-timeout `powercfg` command to give -- that hypothesis is closed. The one-line lever that actually prevents a repeat is a **registry policy that hides the Sleep option from the Start Menu power button** (the standard, long-documented Microsoft mechanism for exactly this -- I have NOT verified this specific value against a live registry read on this box beyond confirming the parent key path exists, so treat as high-confidence-but-J-should-confirm-it-worked after running it, not a guaranteed one-shot):
> ```
> reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v NoStartMenuSleepOption /t REG_DWORD /d 1 /f
> ```
> This does not touch any power SCHEME (nothing above needs fixing there) -- it removes the accidental-click surface. A sign-out/sign-in (or `gpupdate /force`) may be needed for it to take effect. If J would rather keep manual sleep available but just recover faster from an accidental one, the belt-and-suspenders alternative is a scheduled task with **"Wake the computer to run this task"** checked on a task that already runs pre-market (e.g. `Gamma_LaunchTV`) -- `RTCWAKE` (Allow wake timers) is already `Enable` on AC power, so this lever is available without any other change; not applied here since it treats the symptom, not the cause.

## [2026-07-14] FUTURES-MIRROR-SHADOW extended (core-decisions.jsonl + arming-bar tracker) + CORE/FLEET DECISION LEDGERS FOUND STALE (unrelated pre-existing finding) [REVOKE-report]

> **J directive: "make sure you trade futures today too."** The honest, doctrine-compliant form is the FUTURES-MIRROR-SHADOW lane (queue.md) — Phase-1 backtests KILLED every futures setup (0/96 cells), so no futures setup may be armed; the only path to the 7th arm is FORWARD evidence, mirroring the LIVE 0DTE engine's signals as would-be MES trades. **Discovered before building anything: this was already shipped 2026-07-09** (`setup/scripts/futures_mirror_shadow.py`, `Gamma_FuturesMirror` registered every 5 min RTH + 16:05 sweep, `test_futures_mirror_shadow.py` 43/43) — not a from-scratch build. Verified registered + healthy first (`Get-ScheduledTaskInfo`: `LastTaskResult=0` through 2026-07-13, `NextRunTime` today), then extended it rather than duplicating it.
>
> **What shipped today:**
> 1. **`core-decisions.jsonl` coverage** — the 07-09 build's fleet-arm glob (`automation/state/fleet/*/decisions.jsonl`) structurally never watched the 2 PRIMARY accounts (Gamma-Safe-2/Gamma-Risky-2), which is what CLAUDE.md actually describes as the source-of-truth lane. Added as a 5th watched source, cross-deduped against fleet arms by (direction, minute) exactly like the existing 4-arm dedup. Real schema bug found and fixed en route: core rows name the setup field `setup`, every fleet row names it `setup_name` — `scan_arm_lines` now reads `setup_name or setup` so core-derived mirror trades don't silently lose setup provenance.
> 2. **`setup/scripts/futures_shadow_progress.py`** — the arming-bar tracker the 07-09 build deliberately deferred ("evaluated by a LATER session, not this one"). Computes `n_round_trips` / `total_pnl_usd` / `positive_expectancy` from `mirror-would-be.jsonl` every poll (piggybacks on the existing 5-min cadence, no new scheduled task), computes the buy-hold null **only once `n_round_trips>=20`** — both the RESULT and the yfinance fetch itself are gated on the floor (regression-guarded: a monkeypatch that raises if the fetcher is even constructed below 20 round trips, confirmed it's never called). Writes `automation/state/futures/shadow-progress.json`.
> 3. **`firm-brief.md` line** — `render_futures_shadow_lines` (fail-open, additive), wired into `build_brief()` + the Sources footer.
> 4. **Doc-drift fix**: `SCHEDULED-TASKS.md`'s `Gamma_FuturesMirror` row still said stop=1.5xATR14 — stale since the 07-09 evening v1→v2 spec bump to 2.0x. Corrected.
>
> **Verified real, 09:45-09:46 ET, ran `futures_mirror_shadow.py --once` twice back-to-back against real production ledgers (not mocked):** 2nd run's watermarks byte-identical to the 1st — `{"risky-1":525,"risky-3":525,"safe-1":259,"safe-3":525,"core":1032}` both times, only `last_run_et` advanced — proving idempotent catch-up (the explicit property J asked to test: a poll at 16:00 must produce the same rows as live-all-day polling, since the outcome derives from the watermarked ledger, not accumulated side effects). `core-decisions.jsonl` cold-started cleanly to line 1032, correctly ignoring the pre-existing stale backlog (see finding below) per the SAME anti-look-ahead guard the 07-09 build already proved live once (an unguarded first run once opened 7 positions off signals up to 18 days stale before that guard existed). Real `shadow-progress.json` output: `n_round_trips=0, total_pnl_usd=0, armable=false` — honest, not a bug: the v2-spec mirror ledger has accumulated zero closed round trips since 07-09 (0/20 toward the bar), no arming decision pending.
>
> **Tests: 103/103, zero regressions** — `test_futures_mirror_shadow.py` 70/70 (was 43/43, +27 new: core-ledger scanning, cross-source core+fleet dedup, the core `setup`-field-name fallback, 2 explicit idempotent-catch-up tests), `test_futures_shadow_progress.py` 27/27 (new file: round-trip aggregation, the null floor-gate, buy-hold null math, atomic write), `test_firm_brief_futures_shadow_section.py` 6/6 (new file). One pre-existing test's exact-dict-equality assertion updated (new `"core"` watermark key is expected, not a regression).
>
> **Untouched, deliberately**: `install-futures-mirror.ps1` / the launcher chain (already registered+healthy; this morning's separate popup-storm-fix session already rewired its Class-3 launcher wiring — out of scope to touch again, per this session's own instruction to stay away from that machinery entirely), `params*.json`, `heartbeat_core.py`, all exit paths. Read-only on every ledger. No orders, no broker, $0.
>
> **CORE/FLEET DECISION LEDGERS FOUND STALE (discovered while diagnosing feasibility, NOT fixed — out of scope, flagged for a dedicated session):** `automation/state/core-decisions.jsonl` and 3 of 4 fleet arms' `decisions.jsonl` sat byte-identical to their last git commit (core: `667217a`, 2026-06-26; fleet: same) — i.e. the LOCAL working-tree ledger had recorded ZERO new rows between 2026-06-26 and this morning, despite `Gamma_HeartbeatCore` reporting `LastTaskResult=0` every day in between and `heartbeat-tick-audit-*.json` files existing for every one of those dates. Root cause NOT chased (would require git-reflog archaeology outside this task's scope) — leading hypothesis: a `git checkout`/reset touched `automation/state/` sometime after 07-09 (mirror-shadow-state.json's OWN watermark shows the identical pattern — working copy pinned to its `06191cd` 07-09 commit content, confirmed via `git diff`, fleet watermarks reading LOWER than committed, e.g. `risky-1: 520` current vs `1564` committed — consistent with the underlying `decisions.jsonl` files being reverted out from under an already-running watermark). **This is a local forensic-history loss (06-27→07-13 decision rows), not a live-trading outage**: confirmed today's 09:30-09:33 ET ticks landed fine (`core-decisions.jsonl` shows fresh HOLD rows for both `safe`/`bold` at real SPY 749.13, 3 of 4 fleet arms show fresh `M` diffs too) — the engine itself is healthy and trading today; only the LOCAL on-disk decision-forensics record for that 2.5-week window appears to be gone from this working tree. Queued for a dedicated `/fable-differential` session (git-reflog + commit-log archaeology to pin the exact operation and whether the data is recoverable from an intermediate commit or truly gone).

## [2026-07-14] PROFIT-P3 + PROFIT-P5 pre-registered gates RUN — both KILLED, both frozen contracts honored [REVOKE-report]

> Ran the 2 frozen pre-registrations left `AWAITING RUN` since 2026-07-11 (OPRA cache dependency, now clear). **Both jobs: KILL, all 6 candidates.** No re-picks — evaluated exactly as frozen (`no_repick_clause` honored on both).
>
> **Shared build:** `backtest/tools/p3p5_baseline.py` — one gate-OFF population (ribbon_ride BULLISH_RECLAIM/BEARISH_REJECTION, OTM-2 strike, SS-B exit shape, QTY=10, n=250, 2025-01-06..2026-06-17) reused by BOTH studies (the P5 registration's own required cross-check: "the two studies' gate-OFF baselines must match exactly" — true by construction, both scripts import the same module). **Pre-flight integrity check:** this baseline's OTM-2/SS-B numbers (n=250, exp=$17.86, total=$4,465.60) matched PROFIT-P2's already-shipped `ribbon-ride-strike-exit-ab.json` OTM-2 cell EXACTLY before any P3/P5 candidate was evaluated — independent confirmation the replay pipeline is correct, not a fresh untested implementation.
>
> **JOB 1 — PROFIT-P3-MORNING-GATE** (`backtest/tools/morning_gate_study.py`, scorecard `analysis/recommendations/morning-gate-result.{json,md}`): 3 candidates (block-entries-before 11:00 / 10:30 / 10:35 ET). **All 3 FAIL stage 1 on the full net window** — gate-ON expectancy ($0.98 / $12.98 / -$0.91) is WORSE than gate-OFF ($17.86) for every candidate, the OPPOSITE of the 9-day hypothesis-source finding (34/34 morning losers, 2026-06-26..07-09) once tested on the full 2025-01-06..2026-06-17 history. k1 (expectancy) + k2 (OOS) + k4 (BH-FDR, alpha=0.10) all fail on all 3. **Anchor disclosure:** all 3 candidates would have blocked 2 of J's 3 OP-16 winners' actual entries (4/29 10:25:51 ET, 5/04 10:27:50 ET — both before every candidate's cutoff) — flagged MISCALIBRATED per the registration's own instruction (disclosure-only for P3, not itself a kill gate).
>
> **JOB 2 — PROFIT-P5-EXPECTED-MOVE-GATE** (`backtest/tools/expected_move_gate_study.py`, scorecard `analysis/recommendations/expected-move-gate-result.{json,md}`): 3 candidates (day-level trailing-25th-pctile floor / per-trade remaining-move-vs-TP1-ceiling / per-trade premium-budget-ratio). **All 3 KILLED on k6 (mandatory anchor violation)** — every candidate would have SKIPPED at least one of J's 3 real winners: the 4/29 ($1.67 premium) and 5/04 ($0.85 premium) trades both fail V2 and V3 because their premium was a LARGE share of a comparatively modest day's own expected move — the exact anti-edge failure mode `EXTERNAL-0DTE-MECHANISMS-2026-07-11.md` mechanism #1 itself named as disqualifying, now CONFIRMED not hypothetical. Also disclosed: the EXISTING VIX-level gate already captures +$26.45/tr lift on this population — larger than any candidate's own gate-ON delta ($15.53 / -$30.04 / -$7.34) — so k5 ("no lift over existing VIX gates") independently fails all 3 too.
>
> **No params/config/trading-path file touched. No orders placed.** `queue.md` PROFIT-P3/P5 → `done-kill`. Both scorecards are publishable FAILs per each registration's own no_repick_clause ("A FAIL ... is a publishable, informative outcome, not a reason to adjust the pre-registration and re-run").

## [2026-07-14] POPUP-STORM root-caused + fixed — 3 distinct leak classes, live detector re-armed, both auditors' blind spots closed [REVOKE-report]

> **J directive #2 verbatim: "stop the fkin popus on my screen."** Enumerated the LIVE Task Scheduler registry (not the audit JSON, which was reporting near-clean while the popups were happening — audit blind spot, root-caused and fixed, see below). Found and fixed **3 distinct popup classes**, discovered a 4th, harder one via the freshly re-armed live detector, and mitigated it.
>
> **Class 1 — retired ShellExecute chain still live on 4 tasks + 1 non-Gamma task.** `Gamma_DiscordBridge` (every 5 min, 24/7 — the dominant source), `Gamma_EveningNarrative`, `Gamma_McpDailyAudit`, `Gamma_ShadowEval` were still on `wscript→run_hidden.vbs→powershell.exe` — the exact pattern retired 2026-05-17 for leaking a `WindowsTerminal -Embedding` window via `Shell.Run`/ShellExecute routing through the Win11 DefaultTerminal handler. `SwjshAK-BrainSync` (SwjshAlgoKnife's daily git-sync, registered directly as a Scheduled Task on this account) was on a bare `powershell.exe -WindowStyle Hidden` action — same OpenConsole-before-hidden flash. All 5 rewrapped onto the proven `wscript→run_exe_hidden.vbs→pythonw→run_ps1_hidden.py` chain via `setup/scripts/fix-window-leak-task-actions.ps1` (action-only `Set-ScheduledTask` swap — triggers/settings/target `.ps1` content untouched, including SwjshAK-BrainSync's, which lives in a different, scope-frozen repo). Verified: `run_ps1_hidden.py`'s own log shows real `exit=0` for `ensure-discord-bridge-alive.ps1` at the exact fire timestamp, independent of Task Scheduler's `LastTaskResult` (which wscript fire-and-forget always masks to 0 regardless of the real outcome — same lesson as `Gamma_EodFlattenCore`).
>
> **Class 2 — 3 pre-existing `PY_SUBPROCESS_NO_CREATIONFLAGS` violations, already correctly flagged by the audit but never fixed.** `gamma_narrative.py:76` (`git log`) + `:429` (TTS via console `python.exe`) and `twin_gauntlet_conductor_hook.py:105` (`git log`) — all missing `creationflags=CREATE_NO_WINDOW`. Fixed (added the standard `_CREATE_NO_WINDOW` module-level constant + wired into each call).
>
> **Class 3 (the big one) — 18 tasks directly launching `backtest\.venv\Scripts\pythonw.exe`, invisible to BOTH auditors, invisible to the classification logic that approves `pythonw.exe`-ending Execute strings without checking WHICH pythonw or what it runs.** Live-fire proof (re-armed `window-leak-detector.py`, dark since 2026-05-23 — see below): a minimal stdlib-only script under `backtest`-venv-pythonw is clean; a script that does `import pandas` (pulling numpy) leaks a `WindowsTerminal -Embedding` window on **every** launcher mechanism tested — `Shell.Run`, `WshShell.Exec` (a new `run_exe_hidden_exec.vbs` built and tested live), and Python `subprocess.Popen(creationflags=CREATE_NO_WINDOW)` from inside a relay — all three independently reproduced leaking in clean, isolated `Start-ScheduledTask` windows (no other task firing within the poll window). Also ruled out as the trigger: Python-level `sys.stdout`/`sys.stderr` redirection, OS-level `os.dup2` fd redirection, and `warnings.filterwarnings("ignore")` — all three tested live via a purpose-built `import pandas` isolation script, none prevented it. **Formal root cause of the console-allocation trigger itself is UNRESOLVED** — most likely a native call inside numpy/pandas' Windows import path that touches console state below anything Python-level or `CREATE_NO_WINDOW` can intercept. Not chased further past this point (time-boxed; flagged in queue.md for anyone who wants to go deeper — candidates: MKL/OpenBLAS threading-layer init, a `ctypes`/ `ImportError`-recovery path that calls `AllocConsole`).
>
> **The 4 affected tasks (`Gamma_BrokerFills`, `Gamma_CboeOiBank`, `Gamma_Confluence`, `Gamma_CryptoTwin`, `Gamma_DressRehearsal`, `Gamma_EmaSnapshot`, `Gamma_FirmBrief`, `Gamma_FreeModelAudit`, `Gamma_FuturesMirror`, `Gamma_GuardsNightly`, `Gamma_LevelMemory`, `Gamma_OosCheck`, `Gamma_Prospector`, `Gamma_SelfAudit`, `Gamma_TradeAutopsy`, `Gamma_TradeToday`, `Gamma_Trendlines`, `Gamma_TwinSentinel` — 18 total) got TWO fixes:**
> 1. **Headless-stdio-redirect guard added to all 17 that lacked it** (`twin_sentinel.py` already had it) — doesn't stop the leak (proven above) but is still correct OP-27 L41 discipline and closes an independent, real gap.
> 2. **Rewired onto the relay chain** `wscript→run_exe_hidden.vbs→SYSTEM-pythonw→run_cmd_hidden.py --cwd <repo> -- <venv-pythonw> <target.py> [args]` via `setup/scripts/fix-venv-pythonw-console-leak.ps1` — gets a REAL captured exit code (the old direct-venv-pythonw wiring went through `Shell.Run`, which Task Scheduler always reports as `LastTaskResult=0` regardless of outcome) and reuses the codebase's own existing precedent (`run_cmd_hidden.py`, previously only wired for the disabled Funnel/Grind tasks). This does NOT by itself suppress the leak either (same root cause) — its value is exit-code visibility + consistency, disclosed as such, not oversold as "the fix."
>
> **The actual popup suppression for Class 3: `window-leak-detector.py` now auto-hides.** Added `ShowWindow(hwnd, SW_HIDE)` (never kill — zero risk to the underlying scheduled-task work, since this only changes on-screen visibility, not process state) for any newly-detected console-host window (`WindowsTerminal.exe`/`OpenConsole.exe`/`conhost.exe`) whose process ancestry is **service-rooted** (`svchost.exe`→`services.exe`→`wininit.exe` in the first few hops) rather than **explorer-rooted** — the latter is how a window J opens himself (Start Menu/taskbar/shortcut) would always show up, so this is a safe, precise discriminator that will never touch a real terminal J is using. Verified live end-to-end on `Gamma_Confluence` before rollout: leak still logged (`"mitigated": true`), but `confluence-zones.json` still produced fresh + correct, `run_cmd_hidden.py`'s own log shows real `exit=0` — the underlying work is provably unaffected by the hide. Re-confirmed after the full 18-task rollout via a live `Gamma_CryptoTwin` fire: leak logged, `mitigated: true`, `twin-health.json` fresh.
>
> **Class 4 (discovery, not this session's popups) — the live detector itself was dark for ~2 months.** `window-leak-detector.py` (built 2026-05-17, real-time `EnumWindows` poll every 0.5s, logs any suspect window's full `command_line`+ancestry) ran cleanly for a week (2026-05-17→05-23, 4200 polls, 7 real leaks caught) and then was never re-registered — `Get-ScheduledTask '*WindowLeak*'` returned nothing this session. Every task built after 2026-05-23 (which includes most of the Class-3 list, all built 2026-07-08→07-11) had therefore NEVER been under live observation. Re-armed as `Gamma_WindowLeakDetectorKeepalive` (5 min, 24/7, same proven `wscript→run_exe_hidden.vbs→pythonw→<keepalive>` chain as its siblings). Registered in `automation/state/SCHEDULED-TASKS.md`'s Active table + count bumped 77→78.
>
> **Auditor blind spot — root cause and fix.** `automation/state/window-leak-compliance-audit.json` (the file J was looking at) was reporting 0-or-near-0 violations NOT because there were none, but because `audit_window_leak_compliance.py`'s three checks are ALL static source-text scans over repo files (`.ps1` regex for bare `python`, `.py` regex for `subprocess.run` without `creationflags`, `.mcp.json` for unwrapped MCP launchers) — **it never once enumerated what Windows Task Scheduler actually has registered**, and never scanned `.vbs` launcher files at all (so `run_hidden.vbs`'s own leaky `Shell.Run` line was structurally invisible to it, living inside a file type it doesn't read). A SEPARATE script, `audit_scheduled_tasks.py`, already did correct live-registry enumeration — but (a) it was scoped to `Gamma_*` tasks only (`_list-gamma-tasks-json.ps1`'s `Get-ScheduledTask -TaskName "Gamma_*"` filter), structurally blind to `SwjshAK-BrainSync`, and (b) its own `_is_hidden()` classifier had been **silently approving `run_hidden.vbs` as safe** ("older pattern, still approved") ever since the 2026-05-17 escalation that actually retired it — the docstring was never updated after the fix, so the one auditor that DID look at live tasks was working off a stale allowlist entry that contradicted the very investigation that produced it. **Fixed:** `_is_hidden()` corrected (only `run_exe_hidden.vbs`/`run_hidden_exec.vbs` approved now); `_list-gamma-tasks-json.ps1` extended with an explicit `$ExtraTaskNames` allowlist (currently `SwjshAK-BrainSync`) so non-Gamma repo-managed tasks are covered without false-flagging vendor autostart entries; `_is_bare_console_launcher()` extended to catch bare `.bat`/`.cmd`/`pwsh.exe` actions, not just `cmd.exe`/`powershell.exe`; `audit_window_leak_compliance.py` gained a 4th check (`_audit_live_task_registry()`) that delegates to `audit_scheduled_tasks.py`'s now-correct live enumeration + classifiers (single source of truth, not reimplemented) — its flags now merge into the SAME JSON file J was originally looking at. **Structural empty-scan guard added to both auditors** (0 tasks/files scanned now hard-fails RED with an explicit `EMPTY_SCAN`/`LIVE_TASK_SCAN_EMPTY` flag + a `scan_coverage` field proving real file/task counts) — per C7 doctrine, a scan that silently looked at nothing must never read identically to "0 violations found".
>
> **Verification, quoted:**
> - `audit_window_leak_compliance.py` BEFORE this session's fixes were applied: `HEALTH: RED`, 3 flags, ZERO of them about the live task registry (the actual popups were structurally invisible to it). AFTER: `HEALTH: GREEN`, `scan coverage: 144 .ps1 files, 1039 .py files`, `LIVE task registry violations: 0`.
> - `audit_scheduled_tasks.py` AFTER: `HEALTH: RED`, 1 flag (`SILENT_TASK Gamma_GitHubAudit` — pre-existing, unrelated, filed to queue.md, NOT a popup issue).
> - `backtest/tests/test_window_leak_compliance.py`: 3/3 passed (was previously silently RED on `test_no_py_subprocess_missing_creationflags` before the Class-2 fix — nothing had been running this guard to notice).
> - Full existing test suites for all 17 patched scripts (`test_broker_fills.py`, `test_crypto_twin_health.py`, `test_trade_autopsy.py`, `test_prospector.py`, etc., 15 files): **332 passed**, zero regressions from either the stdio-guard insertion or the relay-chain rewiring.
> - Manual `Start-ScheduledTask` fires with REAL artifact checks (not just `LastTaskResult`), post-fix: `Gamma_DiscordBridge` (`run_ps1_hidden.py` log shows real `exit=0`, twice — one scheduled + one manual), `Gamma_CryptoTwin` (`twin-health.json` fresh, leak logged+`mitigated:true`), `Gamma_CcrKeepalive` (`ccr-keepalive.json` fresh, zero leak), `Gamma_TvWatchdog` (`tv-watchdog-status.json` fresh, zero leak), `Gamma_McpDailyAudit` (fired clean through the new chain; failed on its OWN pre-existing, 2-day-old, unrelated `claude` CLI auth issue — confirmed pre-existing by diffing against 2026-07-13's identical failure BEFORE this session's changes, not a regression, filed to queue.md).
>
> **NOT done this session (disclosed, not hidden):**
> - `Gamma_EveningNarrative` / `Gamma_ShadowEval` were fixed but NOT manually fired (would have posted a premature/incomplete Discord message or run an expensive multi-model eval mid-morning) — will self-verify at their next natural scheduled fire; worth a human glance at tomorrow's real fire.
> - `SwjshAK-BrainSync` was fixed but NOT manually fired (its script does a real `git commit`+`git push` on a different repo — didn't want to trigger that as a side effect of a launcher test); will self-verify at its 04:00 MT slot tonight.
> - Two SwjshAlgoKnife-owned HKCU Run-key entries (`SwjshAK-SystemStart`, `SwjshAK-HALOWatchdog`) use bare `powershell -WindowStyle Hidden` — same leak class, but fire only at boot (not the repeating-popup pattern J is seeing) and registry-key edits for a different, scope-frozen project were judged out of bounds for a same-session silent fix. Exact fix ready if wanted. `OpenClaw Gateway.cmd` (Startup folder, `start "" /min cmd.exe ...`) is a genuinely unrelated third-party tool (`~/.openclaw`) outside both this project and SwjshAlgoKnife — flagged only.
> - Disabled `Gamma_Funnel_0`-`_5`/`Gamma_Grind_all` still use `run_cmd_hidden.py` under **venv**-pythonw as the outer wscript target (the OLD, now-corrected docstring claim) — harmless since `run_cmd_hidden.py` itself is stdlib-only, but inconsistent with the other 18; low priority since disabled, noted for whenever they're revived.
> - `Gamma_ShadowEval`'s live trigger is `MSFT_TaskWeeklyTrigger`, but its own `.ps1` comment + `SCHEDULED-TASKS.md` both say "daily weekdays" — a real discrepancy, unrelated to this task, filed to queue.md.
>
> **Files:** `setup/scripts/audit_scheduled_tasks.py`, `audit_window_leak_compliance.py`, `_list-gamma-tasks-json.ps1`, `window-leak-detector.py`, `run_cmd_hidden.py`, `gamma_narrative.py`, `twin_gauntlet_conductor_hook.py`, the 17 Class-3 target scripts, `fix-window-leak-task-actions.ps1` (new), `install-window-leak-detector-keepalive.ps1` (new), `fix-venv-pythonw-console-leak.ps1` (new), `run_exe_hidden_exec.vbs` (new, built + tested, not load-bearing for the shipped fix but a genuinely proven alternative launcher kept for future use). `automation/state/SCHEDULED-TASKS.md` (new task documented), `window-leak-compliance-audit.json` / `scheduled-tasks-audit.json` (GREEN / down-to-1-unrelated-flag proof).
>
> **Revert:** `git revert` this commit for the code; scheduled-task actions can be restored via `Set-ScheduledTask` back to each task's quoted BEFORE string above (all preserved verbatim in this entry and in `automation/state/window-leak-task-fix-log.json` / `venv-pythonw-console-leak-fix-log.json`).

---

## [2026-07-11] SAFE-2-ACCOUNT-REPLACEMENT resolved — retired fleet arm safe-1, repointed core Safe at its account (paper, fully reversible, no J action needed) [REVOKE-report]

> **SHIPPED:** core Safe (`heartbeat_core.py` `ACCOUNTS["safe"]`, the `alpaca` MCP server) is trading again. Its account `PA3S2PYAS2WQ` was accidentally deleted 2026-07-10 evening (J, making room for the crypto twin account) — confirmed dead via live probe (`status=ACCOUNT_CLOSED` / HTTP 401), corroborating `self_check.py`'s standing `BROKER KEY STALE/REVOKED` flag and the independent `analysis/deep-research/2026-07-11-strike-tier-reconciliation.md` finding from earlier today. queue.md filed this as `SAFE-2-ACCOUNT-REPLACEMENT`, `depends:J-creates-account`, `status:blocked`. **Resolved WITHOUT waiting on J:** repointed core Safe at the fleet champion/challenger roster's OWN `safe-1` arm — a real, ACTIVE, already-provisioned paper account (`PA3DHPT7KIQE`) — and retired the `safe-1` fleet arm to free it for reuse, since one broker account can't safely serve two independent execution paths (`mcp_heartbeat` + `fleet_rest`) at once without fills getting double-processed/misattributed. Paper-only, fully reversible, sanctioned under standing autonomy doctrine (OP-0: reversible + paper + sanctioned = act, report for REVOKE).
>
> **Evidence (live-verified this session, direct REST, not MCP-cached):**
> ```
> account_number: PA3DHPT7KIQE
> status: ACTIVE
> equity: 1746.75
> trading_blocked: False | account_blocked: False
> options_approved_level: 3 | options_trading_level: 3
> ```
> Re-confirmed a second time via the now-fixed `accounts_status.py` (5 distinct accounts, no duplicate row, TOTAL unchanged at $8,635.88 — same capital, correct labels). `self_check.py` re-run this session: the `BROKER KEY STALE/REVOKED: safe-2` problem is GONE (only the separate, PRE-FIX `DRESS-REHEARSAL RED` snapshot from 20:45:01 remains — timestamped before this fix, not re-run here, worth a fresh look next session).
>
> **Mechanism:** `.mcp.json`'s `alpaca` server env (`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`/`_account_label`) repointed to the former safe-1 credentials. `automation/state/fleet/secrets.json`'s `safe-2` entry updated to match (mirrors `.mcp.json` per house convention); `safe-1` entry KEPT (not deleted, same creds now duplicated there) but labeled RETIRED so id-keyed lookups still resolve without a KeyError. `automation/state/fleet/accounts.json`: `safe-2` arm's `account_number` → `PA3DHPT7KIQE` + a dated `_repoint_2026_07_11` doc field; `safe-1` arm's `status` flipped `active`→`retired` (+`live`→`false`) + a dated `_retired_doc` field with the full mechanism and revert path — its historical `decisions.jsonl` and `automation/state/fleet/safe-1/circuit-breaker.json` are UNTOUCHED (24 real episodes stay as real history). `heartbeat_core.py`'s `ACCOUNTS["safe"]` was confirmed to resolve credentials ONLY via `alpaca_keys.py` reading `.mcp.json` (no second hardcoded key anywhere) — the repoint took effect for the production engine immediately, no reload needed (each scheduled-task fire is a fresh process reading the current file).
>
> **Consumer table (blast-radius mapped before editing anything — 3 REAL bugs found, not just cosmetic drift):**
>
> | Consumer | Risk if left unfixed | Fix |
> |---|---|---|
> | `setup/scripts/broker_fills.py` `FLEET_REST_ARMS` (4-tuple incl. safe-1) | **REAL BUG:** `creds_all` (from secrets.json) now has safe-1/safe-2 sharing one account; dict order puts safe-1 first, so `main()`'s fill loop would attribute core Safe's future fills to `arm="safe-1"` with `engine_ids=None` → misclassified "manual" instead of "engine", corrupting `total_engine_pnl`/`total_manual_pnl` | dropped safe-1 → 3-tuple; fills now correctly route through `CORE_ARMS["safe-2"]="safe"` |
> | `setup/scripts/mcp_audit.py` + `mcp_audit_direct.py` (hardcoded expected account `PA3S2PYAS2WQ`) | **REAL BUG:** weekly MCP audit would start FALSE-FAILING the instant the credential fix landed (comparing the new, correct, ACTIVE account against the old dead number) | both updated to `PA3DHPT7KIQE` |
> | `setup/scripts/context_audit.py` ("both account numbers present" CLAUDE.md integrity check) | **REAL BUG:** same false-fail mode — CLAUDE.md no longer contains the old number once fixed | updated to check for `PA3DHPT7KIQE` |
> | `setup/scripts/accounts_status.py` `ORDER`/`ENGINE_WIRING` (6-entry, incl. safe-1) | duplicate-account row (safe-1 and safe-2 both showing PA3DHPT7KIQE) + double-counted TOTAL | dropped safe-1 → 5-entry, TOTAL text 6→5 |
> | `setup/scripts/fleet_journal_bridge.py` `FLEET_REST_ARMS` (independently re-declared) | low risk (reads local per-arm decisions.jsonl files, not credentials) but stale/inconsistent | dropped safe-1 → 3-tuple, for consistency |
> | `fleet_live.py#_arm_is_processable`, `fleet_executor.py#run_dry`, `fleet_eod.py` | none — all filter on `accounts.json`'s `status` field dynamically | no code change (self-corrects from the accounts.json edit); fleet_eod.py comment fixed to say "3" |
> | `build_shared_signal.py` | none — `PROBE_LEDGER_ACCOUNT="safe"` is a core-ledger role name, not tied to the fleet arm id | reviewed, no change |
> | Tests reading real `accounts.json` (`test_six_account_routing.py`, `test_six_account_exit_shapes.py`) | would assert against a stale 6/4-arm world | updated to 5/3 active arms; added explicit guard `test_safe1_is_retired_not_dispatched` |
> | `test_broker_fills.py::test_fleet_rest_arm_option_is_engine` | fixture used `"safe-1"` as its example fleet_rest arm — flipped `engine`→`manual` the moment safe-1 left `FLEET_REST_ARMS` | caught by RUNNING the suite (not by inspection); swapped fixture to `"safe-3"` |
> | Tests using `"safe-1"` as a purely SYNTHETIC fixture id (`test_fleet_executor.py`, `test_probe_arm.py`, `test_money_path_simple_fallback.py`, `test_fleet_keystone_consumer.py`, `test_structure_stop_wiring.py`) | none — never read real `accounts.json`, id is just a label | reviewed, deliberately left as-is |
> | `replay_fleet_arms.py` / `test_replay_fleet_arms.py` / `test_fleet_arm_parity.py` (entry-fidelity fixtures over a frozen 2026-05-19..06-24 historical window) | none — validate the mechanism against safe-1's PRESERVED config shape, not its current status | reviewed, deliberately left as-is (safe-1's arm definition is still present, just inactive) |
> | Docs: `CLAUDE.md`, `dual-account-design.md`, `ARCHITECTURE.md`, `mcp-install.md`, `mcp-weekly-audit.md`, `SKILL.md`, `cockpit/server.js` | stale account number/labels | all updated |
> | `automation/state/circuit-breaker.json` (core Safe kill-switch baseline) | kill-switch math pinned to the DEAD account's stale $1,512.71 | reset off a fresh live equity re-query at write time ($1,746.75); `daily_loss_limit_dollars` recomputed (524.02) |
> | `automation/state/today-bias.json` | stale equity fields | patched to match (will be naturally overwritten by Monday's real premarket fire) |
> | `automation/state/dashboard-dialogue.json`, dashboard app | reads position/decision state, not account numbers directly | no change needed |
>
> **Known gaps, NOT fixed here (disclosed, not hidden):**
> - `params.json`'s `_j_ribbon_ride_strike_override_doc` (a giant embedded doc-string) still says core Safe "is DELETED pending J's replacement" — cosmetic only, the feature itself reads a live flag not that prose, so **the PROFIT-P2-ARMED ribbon_ride ATM override (shipped in the entry directly below this one) is now UN-DORMANT and live** as a side effect of this fix. Not hand-edited (giant single-line JSON string, not worth the risk for a cosmetic fix).
> - `automation/state/dress-rehearsal.json` (RED at 20:45:01, before this fix) not re-run — its `check3_sanity` "safe" sub-checks were failing on the same 401 this fix resolves; likely clears at the next natural fire, worth a human eyeball Monday premarket.
> - This session's OWN interactive `mcp__alpaca__*` tool calls still 401 (attempted, confirmed) — the long-running MCP server process was spawned before this edit and holds the old key in memory; per the existing `MCP-401-RESTART-RUNBOOK.md`, this requires restarting the consuming session/task, not something to force mid-session. Does NOT block production trading: `heartbeat_core.py` never uses this MCP connection — it resolves credentials via `alpaca_keys.py` reading `.mcp.json` directly and makes fresh REST calls every scheduled-task fire (a new process each time), already proven working by the direct-REST verification above.
> - A fully "read the active roster from accounts.json instead of a hardcoded set" refactor of `test_six_account_routing.py`/`test_six_account_exit_shapes.py` was considered and deliberately NOT done — hardcoded truth-anchors were judged more valuable as a regression guard than a self-referential dynamic check that could pass vacuously; flagged as a nice-to-have, not a gap.
> - **NEW FINDING (incidental, not this task's doing):** `backtest/tests/test_replay_fleet_arms.py` is RED on 3 tests — `safe-1` now shows `extra=1 missed=1` on the committed 2026-05-19..06-24 replay window vs a ratchet cap of 0/0. **Proven via controlled A/B NOT caused by this fix**: re-ran the identical suite against a git-HEAD (pre-session) `accounts.json` and got the byte-identical failure — pre-existing, most likely from one of today's EARLIER ships touching ribbon_ride entry/strike behavior (not root-caused here, out of scope). Filed as `automation/overnight/queue.md` `REPLAY-FLEET-ARMS-FIDELITY-DRIFT`, not silently left red.
>
> **Guards:** new `test_safe1_is_retired_not_dispatched` (`automation/state/fleet/test_six_account_routing.py`) pins three things — safe-1 present-but-retired (not deleted) in accounts.json, the active fleet_rest roster is EXACTLY `{safe-3, risky-1, risky-3}`, and neither `run_dry` nor `fleet_live._arm_is_processable` (under either `FLEET_OWNS_ALL_6` setting) ever addresses `"safe-1"` again.
>
> **Test counts (quoted, this session):** fleet suite (`automation/state/fleet/` + `test_fleet_arm_parity.py` + `test_fleet_keystone_consumer.py` + `test_participation_cascade.py` + `test_fleet_time_stop_threaded.py` + `test_broker_fills.py` + `test_fleet_journal_bridge.py` + `test_trade_autopsy.py` + `test_sim_live_parity.py` + `test_engine_contract_drift.py`) — baseline **5 failed, 305 passed** (narrower initial scope) → final combined run **5 failed (BYTE-IDENTICAL pre-existing recency-min-sizing qty-clamp failures, confirmed same 5 test names throughout, unrelated to this task), 376 passed**, zero new failures. `test_broker_fills.py`: **26/27 → 27/27** (one fixture-drift fix, safe-1→safe-3 example arm). `test_trade_autopsy.py`: 33/33 (after a tried-and-reverted `FLEET_REST_ARMS` edit — see its own code comment for why that constant must NOT mirror broker_fills.py's on this point). `test_engine_contract_drift.py`: 5/5 after regenerating `automation/state/engine-contract.md`. `test_replay_fleet_arms.py` (slow, ~36s+, run separately): 3 passed / 3 failed, proven pre-existing (see finding above) — excluded from the combined count above since it's unrelated and slow.
>
> **Revert (harder than a flag flip — two things, not one):**
> 1. **Un-retire the fleet arm:** in `accounts.json`, flip `safe-1.status` back to `"active"` and `live` back to `true`.
> 2. **Un-repoint the credential:** move `.mcp.json`'s `alpaca` server env + `fleet/secrets.json`'s `safe-2` entry back to a DISTINCT account — either `PA3S2PYAS2WQ` if J un-deletes it (no self-service path found on Alpaca as of this session), or a freshly provisioned one.
> Do **not** do only one of these — running safe-2 and safe-1 live off the SAME account simultaneously reintroduces the exact double-fill/misattribution risk this repoint exists to avoid. `accounts.json`'s per-arm `_repoint_2026_07_11`/`_retired_doc` fields carry the same instructions inline for whoever executes the revert.

---

## [2026-07-11] STRIKE-TIER-RECONCILIATION — real fills settle the 3-way doctrine conflict: only core Safe is ATM, both "safe" fleet arms trade OTM, tonight's own blast-radius table has a bug

> **Spawned from `task_265ea4d0` / the PROFIT-P2-ARMED open finding below.** Three sources
> disagreed about Safe-side strike tiers (`crypto/lib/strike_selection.py#V15_SAFE_TIERS`,
> `params.json#v15_strike_offset_per_tier`, CLAUDE.md's tier-table prose). Resolved against
> ground truth: 112 real entry orders (109 engine), 2026-06-26→2026-07-09, reconstructed from
> `automation/state/fills-ledger.jsonl` + SPY spot-at-entry via `core-decisions.jsonl`'s `spy`
> field (nearest-timestamp join, median gap 1.5s, max 25.2s). Entry-order count and engine/manual
> split (112 / 109) **exactly match** `analysis/deep-research/2026-07-11-ledger-forensics.md`'s
> independently-computed totals — cross-validated via a second reconstruction method. Full
> writeup: `analysis/deep-research/2026-07-11-strike-tier-reconciliation.md`. Read-only —
> no params/config/accounts.json touched, no orders placed.
>
> **Headline: only `safe-2` (core Safe) trades ATM — 100% of 17 engine fills. Every other
> account, including BOTH "safe" fleet arms, trades OTM 100% of the time.**
>
> | Account | Lane | n (engine) | ATM | OTM-2 | OTM-3 | % ATM |
> |---|---|--:|--:|--:|--:|--:|
> | safe-2 (core Safe) | core | 17 | **17** | 0 | 0 | **100%** |
> | bold-2 (core Bold) | core | 3 | 0 | 0 | 3 | 0% |
> | safe-1 | fleet | 24 | 0 | 7 | 17 | 0% |
> | safe-3 | fleet | 19 | 0 | 2 | 17 | 0% |
> | risky-1 | fleet | 19 | 0 | 2 | 17 | 0% |
> | risky-3 | fleet | 27 | 0 | 5 | 22 | 0% |
>
> **Why:** core Safe's generic strike fallback (`heartbeat_core.py:1229`) hardcodes
> `crypto/lib/strike_selection.py#V15_SAFE_TIERS` (ATM/ATM/ITM-1/ITM-2) directly, never reads
> `params.json`'s own `v15_strike_offset_per_tier` (OTM-3/-2/-1/ITM-2 — the ladder CLAUDE.md's
> prose describes). The two "safe" fleet arms (`safe-1`/`safe-3`) are explicitly patched to the
> OTM table in `automation/state/fleet/accounts.json` (`params_patch: {"strike_tier_table":
> "bold"}`) — documented there as deliberate, "to fit the $600 notional cap at $2K — ATM doesn't
> place this small." `risky-1`/`risky-3` default to the OTM table by id-prefix. Root cause: BOTH
> `automation/state/params_safe.json` and `params_bold.json` were retired 2026-06-18 (commit
> `5da0da2`) in favor of the hardcoded Python constants — the migration moved the values
> correctly but never swept `strike_selection.py`'s own docstring, `params.json`'s now-vestigial
> ladder (on this ONE path only — the sim/backtest lane genuinely still reads it), CLAUDE.md's
> prose, or `orchestrator.py:359`'s stale comment.
>
> **Bug found in tonight's OWN `81b25b4` blast-radius table (below):** it states
> `safe-1`/`safe-3` resolve to `V15_SAFE_TIERS` via `_tiers_for_arm`. They resolve to
> `V15_BOLD_TIERS` — the table missed `accounts.json`'s `params_patch` override. Confirmed both
> in code (`fleet_executor.py:146-158`, `params_patch` is checked before any id-prefix default)
> and in 100% of both arms' real fills (43/43 engine entries, zero ATM). The table's bottom-line
> ("net Monday behavior change is ZERO") is still right, just for the wrong stated reason — the
> fleet is unreachable by the new key regardless of which tier table it happens to match.
>
> **Answers to the task's four questions** (full reasoning in the linked report):
> - **(a)** Real window: core Safe 100% ATM; every other account 100% OTM (§2 above).
> - **(b)** Monday: **zero live behavior change anywhere.** Core Safe's Alpaca credential is
>   returning **401 Unauthorized** — independently verified live this session
>   (`mcp__alpaca__get_account_info`; control call to `mcp__alpaca_aggressive__*` succeeded
>   normally, `equity=$1,963.04`, so the 401 is credential-specific, not an outage). Whenever
>   reprovisioned, ribbon_ride trades ATM — **identical** to what the generic fallback already
>   gave it (the override's flat offset 0 == the fallback's tier-0 offset 0 at any equity under
>   $10K). Fleet arms are structurally unreachable by the new override key regardless.
> - **(c)** The AB scorecard (`ribbon-ride-strike-exit-ab.json`) labels OTM-2 "control, live
>   tier" for core-Safe ribbon_ride — **not accurate**; the true live control was already ATM.
>   Delta (+$47.96/tr ATM over OTM-2) is a legitimate simulated comparison, clearly disclosed as
>   MEASURED-not-REALIZED, but doesn't describe a change from what core Safe was actually doing.
> - **(d)** To put fleet safe arms on ATM (evidence only, NOT applied): delete
>   `params_patch.strike_tier_table` from `safe-1`/`safe-3` in `accounts.json` (default then
>   resolves to `"safe"` automatically). Not a free move — the patch exists specifically so ATM's
>   higher premium doesn't fail the Rule-6 min-3-contract floor at $2K equity.
>
> **Smaller drift also found:** `accounts.json`'s `safe-2` entry still reads `"status": "active"`
> despite the live 401 — registry hasn't caught up with the dormancy either.
>
> Queue item filed: `STRIKE-TIER-RECONCILIATION-FOLLOWUP` (`queue.md`). Doctrine edits
> (CLAUDE.md prose, `params.json` ladder cleanup, `strike_selection.py` docstring) are OUT OF
> SCOPE here by task design — evidence report only.

---

## [2026-07-11] PROFIT-P2-ARMED — core Safe ribbon_ride strike OTM-2 → ATM (paper, OP-11 auto-ratify, J-revocable) [REVOKE-report]

> **SHIPPED:** core Safe `ribbon_ride` now trades **ATM** (offset 0) instead of the generic v15 OTM-2/equity-banded strike. Mirrors the WP-5 per-setup-override pattern byte-for-byte — no new mechanism invented.
>
> **Evidence** (re-verified directly from the JSON before this ship, not taken on faith): `analysis/recommendations/ribbon-ride-strike-exit-ab.json`, `axis1_strike.comparisons.ATM` — delta_expectancy **+$47.96/tr**, delta_oos_total **+$8,573.6** (IS-2025 +$4,727.6 / OOS-2026 +$11,333.4, both positive), WF **4.25**, both chronological halves positive, drop-top-3 **+$36.64** (the OTM-2 control's OWN drop-top-3 is **NEGATIVE -$2.13/tr** — its live-tier edge rides its 3 best trades), beats its 20-seed random-entry null (p=0.0476), BH-FDR survivor (rank 1/6), STABLE on the fill-bar sensitivity toggle (+$52.32 old convention, same sign). `clears_auto_ratify_bar=true`, `anchor_no_regression_op16=true`, `unstable_on_open_audit=false`, `smoke_mode=false`. OTM-1 (+$19.12/tr) clears the arithmetic too but FAILS its own random-entry null (non-BH-survivor, dominated by ATM) — **not armed**. ITM-2 fails WF/sub_window_stable (C22 regime-concentration, IS-2025 -$17.0K) — **not armed**.
>
> **Mechanism:** added `ribbon_ride`'s 2 entry_setups (`bearish_rejection_ride_the_ribbon` / `bullish_reclaim_ride_the_ribbon`, lowercased) to `setup/scripts/heartbeat_core.py`'s existing `_SETUP_STRIKE_OVERRIDES` dispatch table — same 3-key params shape (`j_ribbon_ride_strike_override_enabled` / `_strike_offset_safe` / `_strike_offset_bold`) the 5 WP-5/trade-to-learn extra-setup overrides already use (vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, double_bottom_base_quiet, bollinger_squeeze).
>
> **Consumer table** (blast-radius mapped before editing anything):
>
> | Consumer | Reads the new key? | Effect |
> |---|---|---|
> | `heartbeat_core.py#_execute`, `ACCOUNTS["safe"]` (core lane) | YES — `_SETUP_STRIKE_OVERRIDES` | ATM, once re-wired (account currently deleted) |
> | `heartbeat_core.py#_execute`, `ACCOUNTS["bold"]` (core lane) | NO — reads `automation/state/aggressive/params.json`, a wholly separate file, never touched | structurally unaffected (enable flag absent) |
> | `fleet_executor.py` (`safe-1`/`safe-3` fleet arms) | NO — strike comes from `_tiers_for_arm` → `crypto/lib/strike_selection.py#V15_SAFE_TIERS`, zero per-setup dispatch exists in the fleet lane | unaffected by this key either way |
> | `fleet_executor.py` (`risky-1`/`risky-3`/`bold-2`) | NO — same separate mechanism, Bold-sizing table | unaffected |
> | `backtest/lib/risk_gate.py#select_strike_offset` (sim/replay lane — `orchestrator.py`, `live_order_resolver.py`) | NO — its own separate `_PER_SETUP_STRIKE_OVERRIDES` dict has ONLY `VWAP_CONTINUATION` (pre-existing gap shared by the other 4 WP-5 setups too, not introduced here) | replay/backtest tools still simulate the OLD generic tier for ribbon_ride — disclosed, not fixed (would need its own evidence/scope) |
> | Guard tests pinning the old tier | 2 found + updated (not deleted) | now pin the NEW correct behavior |
> | Dashboard (`dashboard/`) | reads `journal`/`decisions.jsonl`, not params.json strike keys directly | no change needed |
>
> **DORMANCY:** core Safe account (`safe-2`, `PA3S2PYAS2WQ`) is DELETED pending J's replacement — this override is INERT on the core lane until re-wired. **The safe-* FLEET arms (safe-1, safe-3) are the live surface Monday, and they do NOT inherit this change** (fleet_executor.py never consults `_SETUP_STRIKE_OVERRIDES`). **Net live behavior change Monday = ZERO** either way; this ship prepares the core lane for when J's replacement account lands.
>
> **Open finding, NOT fixed here (out of scope, flagged separately):** `crypto/lib/strike_selection.py#V15_SAFE_TIERS` — the table BOTH the core lane's generic pre-override fallback AND every fleet arm's strike selection ultimately resolve to — is ALREADY `ATM`/`ATM` for the $0-2K/$2K-10K equity bands. This does **not** match this same file's own `v15_strike_offset_per_tier` (OTM-3/OTM-2) or the CLAUDE.md tier-table prose. Possible pre-existing silent doctrine/code drift, unrelated to this ship — flagged via a spawned task, not fixed here (touching it would affect every setup on every safe-sizing fleet arm, well beyond ribbon_ride).
>
> **Guards:** 2 pre-existing pins broke as EXPECTED — they asserted "no per-setup override ever touches ribbon_ride," which stopped being true. Both updated to pin the new correct behavior (never deleted-to-pass): `test_trade_to_learn_2026_07_01.py::TestStrikeOverride::test_ribbon_setup_now_uses_its_own_atm_override`, `test_money_path_2026_07_01.py::TestVwapContinuationArmed::test_ribbon_setup_now_uses_its_own_atm_override`. New dedicated file `backtest/tests/test_ribbon_ride_strike_override_2026_07_11.py` (11 tests: bear+bull vary-and-assert at $25K equity where the generic ITM-2 tier is distinguishable from ATM, bold structural+behavioral non-leak, `setup_name`-fallback path, offset-math sanity, cross-setup non-leak).
>
> **Test counts (quoted, this session):** strike/trade-to-learn/money-path/new-guard suites — baseline **128 passed** → after fix **139 passed** (128 + 11 new), **0 failed**. Fleet lane (`test_six_account_routing/exit_shapes`, `test_fleet_arm_parity`, `test_strategies`, `test_fleet_executor`, `test_recency_min_sizing`, `test_probe_arm`) — **124 passed / 4 failed BOTH before and after** (byte-identical pre-existing failures: `_apply_recency_min_sizing` clamping qty on live `recency-confirmation.json` RED state, unrelated to strike selection, confirmed NOT introduced by this ship).
>
> **Revert (single value):** set `j_ribbon_ride_strike_override_enabled` to `false` in `automation/state/params.json` (byte-identical to pre-ship: core ribbon_ride falls back to the generic v15 Safe tier). J-revocable.

---

## [2026-07-11] PROFIT-P2-RIBBON-RIDE-STRIKE-AB (extended) — strike axis: ATM wins (+$47.96/tr, MAY SHIP per OP-11); exit axis: SS-B stays (challenger unstable on the open-audit toggle)

> Queue P2, unblocked tonight (OPRA cache freed by the FDR-16/P5 crew), EXTENDED per task brief with a same-run SS-B-vs-P5-topcell exit head-to-head. Built `backtest/tools/ribbon_ride_strike_exit_ab.py`: ONE sequential process (`backtest/.venv`), TWO axes, LIVE-scope (`post_tp1`) exit_manager replay on the canonical `_signal_cache` ribbon_ride cohort — n=250 signals both directions (2025-01-06..2026-06-17), real local OPRA 5-min bars, zero network. Machinery reused unchanged: `structure_stop_study` SS_B_SHAPE/replay_structure_aware (the PROFIT-P1-certified engine — BOTH exit shapes replay through this same code path, apples-to-apples), `tw8_level_context` DIRECT trigger-level recovery (39.2% recoverable; rest premium-only cat-cap fallback, never dropped), `t4_exit_matrix.battery`, `null_baseline.random_entry_null` (20 seeds, injected through the same replay engine via `sim_fn`), `ribbon_rejection_wick_battery.bh_fdr` (alpha=0.10 across all 6 cells: 3 survivors). Every cell also replayed under the OLD `>=` fill-bar convention as a sensitivity column (the two open audit chips task_4935ea80/task_86001855 cover exactly this) — a sign-flip on the toggle = UNSTABLE_ON_OPEN_AUDIT, pre-declared, cannot ship.
>
> **AXIS 1 — strike (SS-B held fixed). VERDICT: ATM.** The only cell clearing OP-11 auto-ratify AND the full battery:
>
> | strike | n | exp $/tr | IS-2025 | OOS-2026 | WF | drop3 exp | null | BH | toggle |
> |---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
> | OTM-2 (control, live tier) | 250 | +$17.86 | +$1,706 | +$2,760 | 2.88 | **-$2.13** | FAIL | — | stable |
> | OTM-1 | 249 | +$36.98 | +$2,456 | +$6,753 | 4.86 | +$12.72 | FAIL | — | stable |
> | **ATM** | 244 | **+$65.82** | **+$4,728** | **+$11,333** | **4.25** | **+$36.64** | **PASS** | **survivor** | **stable (+$52.32)** |
> | ITM-2 | 231 | +$11.08 | **-$16,994** | +$19,554 | None (IS<0) | -$30.19 | PASS | survivor | stable |
>
> ATM − OTM-2 = **+$47.96/tr** (delta-OOS +$8,574), anchor no-regression (edge_capture_rel 361.4 vs -24.4), both halves positive → **MAY SHIP per OP-11 (OOS+ / WF≥0.70 / sub-window stable / anchor no-regression, toggle-stable) as the v15.4 weekend rule update — scorecard only, params NOT touched, arming is the separate step.** OTM-1 clears the OP-11 arithmetic (+$19.12/tr) but FAILS its own random-entry null → don't arm the dominated cell. **ITM-2 is killed as a gradient endpoint on this cohort** — its OOS total is the biggest but it rides a -$17.0K IS-2025 with negative drop-top-3 and top3-day share 5.5x (C22 regime-concentration profile; the ranked plan's kill criterion "gradient doesn't reproduce" PARTIALLY triggered: WP5's ITM>ATM>OTM reproduces through ATM, breaks at ITM-2). Corroborating detail: the OTM-2 control's own drop-top-3 expectancy is NEGATIVE — the live tier's entire full-sample edge rides its 3 best trades, independently confirming the friction-stream/WP5 "fragile at OTM-2" read on core ribbon_ride itself.
>
> **AXIS 2 — exit (P5-topcell challenger stop-8%/tp+30%/sell50%/trail15/ts10 vs SS-B, identical episodes per strike). VERDICT: SS-B stays; nothing ships tonight.** At OTM-2 the challenger wins +$19.04/tr on the corrected convention but the delta **sign-flips to -$9.45/tr** under the old fill-bar convention → **UNSTABLE_ON_OPEN_AUDIT — blocked until chips task_4935ea80/task_86001855 land** (mechanism: a -8% stop is same-bar-reachable from the fill price, so this shape family is maximally toggle-sensitive; SS-B's -50% cat cap is not, which is why axis 1 is stable). At ITM-2 the challenger is toggle-stable (+$58.34/tr) but **regresses the OP-16 J-anchor** (edge_capture_rel 576 vs SS-B's 1149 — tp+30% banks early and caps exactly J's big winner days) → WAIT_EVIDENCE. Honest flag for the rematch after the chips land: the challenger's risk profile is dramatically smoother (OTM-2 maxdd -$687 vs SS-B's -$4,798; top3-day share 0.30 vs 1.19) — real signal, just not shippable on an unstable toggle / an anchor regression.
>
> Files: `analysis/recommendations/ribbon-ride-strike-exit-ab.{json,md}` (per-cell battery + sensitivity column + explicit ship-vs-wait split), `backtest/tools/ribbon_ride_strike_exit_ab.py`. queue.md `PROFIT-P2-RIBBON-RIDE-STRIKE-AB` → done-with-verdict. No params/config touched, no orders placed.

---

## [2026-07-11] P5-TOPCELL-REAL-FILLS-CONFIRM — mass-grind P5 survivors on real OPRA fills via exit_manager: 5/6 PASS, 1/6 MIXED

> Second half of the dormant-asset audit's top-2 (`analysis/deep-research/2026-07-11-dormant-assets.md` §1, run sequentially AFTER FDR-16-OPRA-CONFIRM per the hard OPRA-cache constraint — one process at a time). Built `backtest/tools/p5_topcell_real_fills_confirm.py`. Per standing doctrine ("exit-shape RATIFICATION evidence = exit_manager replay on real fills, never sim absolute dollars") this does NOT trust `mass-grind-phase5-summary.json`'s backtest numbers directly — it replays the SAME entry population through the ACTUAL LIVE `exit_manager.plan_exit_actions` decision core, both on local 5-min bars and on real fleet fills.
>
> **SCOPE FINDING (before running anything):** the literal "top 5 by the summary's own ranking" turned out to be ONE distinct shape wearing 5 cosmetic labels — verified directly against the raw funnel data: `tp+30%/sell50%` and `tp+100%/sell100%` variants of the same core combo (OTM-1, stop-8%, trailing15%) show **byte-identical** n=399, expectancy=$34.32, WR=0.3584, max_dd=-$386.89. Mechanism: `simulate_trade_real`'s zero-arm-threshold trailing branch (mass_grind never sets `profit_lock_threshold_pct`) resolves every trade via the lock or the -8% stop before ANY tested TP1 level (30%-150%) is ever reached — `tp1_premium_pct`/`tp1_qty_fraction` are dead axes within the P5-survivor population. Ran all **6 genuinely distinct** (strike, stop, lock, trail, time-stop) shapes among the 106 survivors instead — same "handful, not a grind" compute budget the ticket specified, materially more informative.
>
> **Verdict: 5/6 PASS, 1/6 MIXED — the edge is real but smaller live than the backtest number, not a KILL.** Top-ranked cell (OTM-1/stop-8%/trailing15%, the one the task's own framing centered on): LIVE `post_tp1` (production) scope expectancy **+$25.62/tr** (n=381) vs the sim-reported +$34.32/tr — the scope-mismatch's real cost is **-$8.70/tr**, present but not catastrophic. Real-fleet anchor (18 real PUT positions, same shape replayed via the identical `exit_manager` call as the control) shows `no_regression=True`: $68.33 candidate vs $23.70 control. Other 4 shapes similarly PASS with LIVE deltas from -$25/tr to +$7.79/tr vs their sim numbers, all still net positive. Only `OTM-1/stop-12%/trailing15%` is MIXED: LIVE positive (+$18.98/tr) but the real-fleet anchor shows regression (-$33.83 vs $23.70 control).
>
> **2 methodological findings surfaced while validating this, both disclosed in the artifact and flagged for follow-up (not silently fixed, not silently ignored):**
> 1. **`t4_exit_matrix.py`/`t5_confirmatory_matrix.py`'s shared `_load_bars` includes the fill bar itself** in the exit-management replay loop (`>=` on entry timestamp) — but `simulate_trade_real`'s own bar-walk starts ONE BAR LATER (`simulator_real.py:492`, `opt_idx = entry_idx_opt + 1`) and never checks the fill bar's own high/low against any stop. Confirmed this materially matters: fixing it in this script's own bar-loader moved the top P5 cell's LIVE expectancy from **-$20.23/tr to +$25.62/tr** — a sign flip. T4/T5's own prior conclusions (already used for the STOP-A/STOP-B sign-offs) used the un-fixed `>=` convention and were NOT re-audited here (out of this task's scope) — they may carry a mild pessimism bias on any candidate whose stop/arm condition is reachable from the fill price itself.
> 2. **`exit_manager.py`'s `ARM_SCOPE_FULL` ("full = simulator parity" per its own docstring) does not actually reconcile with `simulate_trade_real`'s real recorded number** on a bar-level trace — verified on a specific trade where `simulate_trade_real` rode a 45%-adverse excursion ($0.49 low against a $0.89 entry, deep past both the raw -8% stop and the ratcheted profit-lock floor) to a later profitable exit at $1.003, while the `ARM_SCOPE_FULL` replica stopped the same trade out immediately. Root cause NOT isolated within this session's time budget (traced through simulate_trade_real's bar-walk sequencing without finding the exact divergence point). Consequence: the "sim full-scope" comparison column in the artifact is reported as **exploratory/unreconciled**, explicitly NOT used for any verdict (LIVE `post_tp1` is the ratification number throughout, consistent with standing doctrine that simulate_trade_real was never supposed to be the ratification authority anyway).
>
> **Anchor sample-size caveat:** the real-fleet anchor uses only 18 PUT-only positions from the CURRENT ledger (`exit_shape_parity_study.replay_position` hardcodes `side="P"`, a pre-existing limitation not touched here; 71 CALL positions counted and excluded, not silently dropped) — NOT the ~79-position full set that produced the commonly-cited -$757/-$893 `actual_ribbon_ride` figures. This run's control total ($23.70) is a different, smaller, more recent sample — not comparable to those headline numbers; the candidate-vs-control DELTA on the identical 18-position pool is still a valid relative read.
>
> **Downstream unblock:** `queue.md`'s `PROFIT-P2-RIBBON-RIDE-STRIKE-AB` was explicitly waiting on `depends:FDR16-P5-crew-done` — both legs are now done, P2 is unblocked (not run this session, out of assigned scope).
>
> Files: `analysis/recommendations/p5-topcell-real-fills-confirm.{json,md}`, `backtest/tools/p5_topcell_real_fills_confirm.py`. Ticket added done in `queue.md` (`P5-TOPCELL-REAL-FILLS-CONFIRM`).

---

## [2026-07-11] PROFIT-P1/P3/P5 — fleet exit-parity scorecards (4 arms) + 2 frozen pre-registrations

> Deep-research ranked plan (`markdown/research/PROFITABILITY-DEEP-RESEARCH-2026-07-11.md`) items P1/P3/P5, worker-tier (Sonnet), read-only/no-orders/no-config-flip per task constraint.
>
> **P1 — FLEET-EXIT-PARITY (scorecards done, migration NOT done — separate reviewed step):** built `backtest/tools/fleet_exit_parity_per_arm.py`, reusing `structure_stop_study.py`'s certified CONTROL_SHAPE (-20%/+150%/sell80/fixed, the shape that actually produced these fills) + SS_B_SHAPE (-50% cat cap/+100% TP1 sell66/trailing-15%/structure-primary) + `replay_structure_aware`/`recover_trigger_level_real_position` verbatim, and `exit_shape_parity_study.py`'s fill-ledger episode reconstruction verbatim. One disclosed non-reuse: `structure_stop_study`'s bar-fetcher hardcodes `TODAY=2026-07-09` for its own one-off run day — reusing it blindly today would silently truncate 07-09's option bars to whatever wall-clock hour this script runs at, so a small adapted `prepare_positions_historical` always uses the plain historical fetcher instead.
>
> Ran for real (`backtest/.venv`, live Alpaca OPRA option-bar fetches — bounded, ~1 call per unique symbol/date; SPY 5m data 100% local cache, zero network calls there). **VERIFIED** (OP-33): reconstructed n + actual P&L per arm matches `analysis/deep-research/2026-07-11-ledger-forensics.md`'s independently-computed per-account table EXACTLY — safe-1 n=24/-$242.00, safe-3 n=19/-$272.00, risky-1 n=19/-$486.00, risky-3 n=27/-$274.00 (cross-check via a second, independently-authored method).
>
> | Arm | n | CONTROL replay | SS-B replay | SS-B − CONTROL | Verdict |
> |---|--:|--:|--:|--:|---|
> | safe-1 | 24 | -$186.40 | -$201.65 | -$15.25 | **KEEP_CURRENT_SHAPE** |
> | safe-3 | 19 | -$245.60 | +$4.25 | +$249.85 | SS_B_BETTER_BUT_FRAGILE |
> | risky-1 | 19 | -$407.60 | -$39.50 | +$368.10 | SS_B_BETTER_BUT_FRAGILE |
> | risky-3 | 27 | -$317.70 | -$229.30 | +$88.40 | SS_B_BETTER_BUT_FRAGILE |
>
> "FRAGILE" = SS-B beats CONTROL on raw total but the drop-top-3 concentration check (t4_exit_matrix.battery convention) flips the comparison in all 3 cases — the improvement rides on a handful of big trades, not a broad shift. None of the 4 arms clears all 3 robustness checks (raw total + drop-top3 + both-halves) needed for a clean migrate call; no arm was worse across the board except safe-1. **No config flipped — per C29 each arm gets its own verdict, and none of these clear cleanly enough to ratify on n=19-27.**
>
> **CAVEAT surfaced, not acted on:** `structure_stop_enabled=true` is ALREADY live in both `automation/state/params.json` and `aggressive/params.json`, and `strategies.py`'s ribbon_ride registry already declares `stop_mode="structure"` for all 6 SPY arms including the 4 fleet_rest arms (`test_six_account_exit_shapes.py`) — because `fleet_executor._params_for` reads the SAME 2 params files core uses (no per-arm override exists today except via `accounts.json` `params_patch`, which COULD carry a per-arm `structure_stop_enabled:false` override if J wants safe-1 opted out specifically). Confirmed via `decisions.jsonl`/`exit-state.json`: all 4 arms flat, 0 fleet fills since 07-09, so this is unobserved forward, not contradicted by anything above — but the "migration" this ticket frames as a future decision may already be config-armed fleet-wide today.
>
> Scorecards: `analysis/recommendations/fleet-exit-parity-{safe-1,safe-3,risky-1,risky-3}.json` (per-episode detail + aggregate + drop-top3 + both-halves).
>
> **P3 — MORNING-GATE (pre-registered, NOT run — OPRA cache busy with another crew):** `analysis/recommendations/prereg-morning-gate-2026-07-11.json`. 3 frozen candidates (block-before-11:00 / block-before-10:30 / first-hour-relative-to-09:35-open), scoped to ribbon_ride ONLY both directions — explicitly excludes vwap_continuation/j_vwap_reclaim_fb/j_vix_dayside (structurally morning-native by their own validated design; a blanket gate would silently neuter them — a scoping catch made before freezing). Eval window = full OPRA cache (2025-01-02..2026-07-08, verified via directory listing) minus the 06-26..07-09 hypothesis-source window (no peeking) → net 2025-01-02..2026-06-25, IS/OOS at the established 2026-01-01 boundary. Battery: expectancy + OOS + random-entry null + opposite (late-session mirror) null + drop-top3 concentration + BH-FDR (alpha=0.10, reusing `ribbon_rejection_wick_battery.bh_fdr`) across the 3 candidates, plus a mandatory anchor-context check against J's 3 OP-16 winners.
>
> **P5 — EXPECTED-MOVE GATE (pre-registered, NOT run — same cache dependency):** `analysis/recommendations/prereg-expected-move-gate-2026-07-11.json`. 3 frozen formula variants on ribbon_ride ONLY — V1 day-level trailing-25th-percentile expected-move floor, V2 per-trade remaining-move (sqrt-time-decayed) vs TP1-implied-premium-ceiling (disclosed FIXED delta-proxy table per strike tier, not a live Greek), V3 per-trade premium/expected-move budget-ratio (simplest, Path-A-only, zero timing model). Expected move = ATM straddle at first bar ≥09:35 ET × 0.85, computed from the same cached OPRA bars (zero new data/infra). Same window/OOS/battery/BH-FDR convention as P3. Kill ladder includes the queue's own stated bar ("no lift over existing VIX gates" — runner must report the VIX-gate-only baseline) plus the mechanism doc's own anchor-violation kill (blocking any OP-16 winner = automatic MISCALIBRATED).
>
> `queue.md` PROFIT-P1/P3/P5 updated: P1 → `scorecards-done-migration-pending`, P3/P5 → `pre-registered-awaiting-run`. No test suite written for the new per-arm replay script (research artifact, not a trading-path file; correctness leans on reusing already-tested `exit_manager`/`structure_stop_study` machinery verbatim plus the independent ledger-forensics cross-check above) — flagged here rather than silently skipped.

---

## [2026-07-11] FDR-16-OPRA-CONFIRM — both top-2 non-redundant FDR survivors KILLED on real OPRA fills

> Dormant-asset audit (`analysis/deep-research/2026-07-11-dormant-assets.md` §8) ranked this #1 by effort/leverage — 9-day-idle ticket (`queue.md` `FDR-16-OPRA-CONFIRM`), tool already existed (`lib.simulator_real`), fully specified. Ran it. New tool: `backtest/tools/fdr16_opra_confirm.py`. Full battery: signal replay + opposite-direction null + 20-seed random-entry null (`autoresearch.null_baseline`, the standing repo gate) + n-honesty + IS/OOS split + top-3-day concentration.
>
> **Verdict: KILL both.** Neither of the FDR screen's top-2 non-redundant survivors (by p-value, deduped across setup/direction/regime) converts to a real edge:
> - **Group A `level_rejection`/long/vix_lo** (the single strongest statistical prior in the whole sweep — reported n=1318, p≈1e-7): real-fills signal expectancy IS positive (n=619, $39.12/tr) and edges the null MAX ($33.36) — but **fails the concentration-robust half of the standard gate**: drop-top5 expectancy ($5.72/tr) does NOT beat the null MEAN ($9.87/tr). Top-3 days alone are 56% of total P&L. Classic "a few great days, not a durable edge" — exactly the null_gate this repo's real-fills validators standardize on (`autoresearch/null_baseline.py`) exists to catch. Opposite-direction (short) loses (-$22.94/tr), so directionality itself isn't the problem — the edge just isn't real once big days are removed.
> - **Group B `trendline_rejection`/long/vix_hi** (n=338, p≈7.7e-5): real-fills expectancy is outright negative (n=160, **-$20.32/tr**), fails the null gate on both legs. Clean kill, no ambiguity.
>
> **N-HONESTY finding (applies to the ORIGINAL FDR screen, found while building the confirm tool):** `shadow-ledger.jsonl` logs duplicate decision rows per bar (an unfiltered raw-trigger record + a separate gate-audit record both get written) that `discovery_shadow_ledger.py` never dedupes before the FDR screen consumes it. Verified directly: Group A's reported n=1318 is actually **840 true distinct bars** (1.57x inflation); Group B's reported n=338 is **180 true** (1.88x inflation). Doesn't change the sample mean (duplicates carry identical values) but inflates the screen's own t-stat/p-value optimism. Not fixed here (read-only mandate) — worth a follow-up on `discovery_shadow_ledger.generate()`'s dedupe.
>
> **Spec-vs-reality:** this run regenerated decisions with CURRENT params (`automation/state/params.json`, 2026-07-09) vs the params in effect when the ledger was built (2026-06-29, 10 days earlier) — the likely reason true-bar counts don't exactly match a naive re-derivation from the frozen ledger. Arguably the more relevant test (does the edge exist under what we'd deploy today); disclosed in the artifact, doesn't change either verdict.
>
> Files: `analysis/recommendations/fdr16-opra-confirm.json` + `.md`. Ticket `FDR-16-OPRA-CONFIRM` closed done-KILLED in `queue.md`. 16 FDR survivors out of 162 comparisons being mostly multiplicity noise on real fills is a fully valid outcome (same failure mode as NLWB) — not a tool or methodology failure.

---

## [2026-07-11] ORCHESTRATOR-RIBBON-ZERO-FIX — the flagged follow-up from MIN-RIBBON-SEMI-ARMED-FIX, closed (1 commit)

> Completes the follow-up explicitly flagged (not fixed) in the earlier MIN-RIBBON-SEMI-ARMED-FIX entry below and in `automation/overnight/queue.md`: gates.py's `min_ribbon_momentum_cents` zero-is-off fix (commit `49e3c40`) only closed the LIVE path — `backtest/lib/orchestrator.py`'s own inline gate cascade (the backtest/A-B research engine gates.py was extracted FROM) had the IDENTICAL `is not None` bug, untouched. Same L106/L107-shaped "backtest and production silently disagree" failure class this codebase has been burned by twice before.

- **BUG A (min_ribbon_momentum_cents), root cause:** `orchestrator.py:1482` checked `is not None` — since `0 is not None` is True, a future backtest/A-B run setting `min_ribbon_momentum_cents=0` (very plausible; 0 reads as "no minimum" almost everywhere else in this codebase) would silently re-arm the L107-reverted gate in the RESEARCH path even though the live path (gates.py) was already fixed. **Fix:** `is not None` → truthy (`if min_ribbon_momentum_cents and idx >= 3:`), 1 line.
- **BUG B (max_ribbon_duration_bars), root cause:** identical `is not None` pattern in BOTH `gates.py:342` AND `orchestrator.py:1503`. Lower urgency than Bug A — Safe's `params.json` currently pins this at `999` (an inert workaround, not this bug; Bold's `aggressive/params.json` doesn't carry the key at all — already-inert on both live accounts). GATE-PROVENANCE-AUDIT-2026-07-02 finding G9 rated this "KILL (remove key for hygiene)." **Decision: code-fix, not key-deletion.** Matches Bug A / commit `49e3c40`'s exact precedent (that fix ALSO left params.json's data-side untouched — the lesson from L107 is specifically that a data-only fix doesn't survive a future config write; the code must be inert-at-0 on its own merits). Deleting the params.json key would be pure hygiene on the LIVE production source-of-truth file, outside this fix's "pure backtest/research-path" scope — left as an optional follow-up, not done tonight. **Fix:** `is not None` → truthy in both files (`if _rdur_max:` / `if max_ribbon_duration_bars:`), 2 lines. Confirmed CURRENT live behavior unchanged either way (999 is truthy under both the old and new check — the difference only matters at threshold 0, which no live account sets).
- **Real-data proof, not just hand fixtures:** while writing the guard test, the assert-agree oracle (`GAMMA_ENGINE_GATES_ASSERT=1`) caught a LIVE disagreement on 2025-06-03 bar 7451 (10:00 ET) — with both knobs at 0 pre-fix, orchestrator's inline cascade fired `SKIP_RIBBON_MOMENTUM_GATE` (Bug A) while gates.py (Bug A already fixed, Bug B not yet) instead fell through to `SKIP_RIBBON_DURATION_GATE` (Bug B) — both wrong, for different reasons, on the same bar, silently eating the day's only trade (a bull `C` entry). This day became the integration guard's anchor.
- **Guards:** `test_gate_max_ribbon_duration_bars_zero_is_off` (gates.py unit-level, mirrors `test_gate_min_ribbon_momentum_cents_zero_is_off`) + `test_oracle_agrees_zero_ribbon_knobs_on_2025_06_03` (NEW class — orchestrator-level; the existing gates.py-only unit tests never exercised orchestrator.py's separate inline cascade at all, so they couldn't have caught Bug A). Both RED-proved against the pre-fix code (quoted failures, including the live oracle disagreement above), then GREEN after the fix. Non-vacuity: a real threshold (50.0 / 3) on the identical 2025-06-03 day still blocks (`SKIP_RIBBON_MOMENTUM_GATE`, 0 trades) — proves the fix narrowly targets zero/None, not the whole gate mechanism.
- **Tests (quoted):** `test_engine_gates_parity.py` — before **26/26 passed** (8.82s), after **28/28 passed** (14.32s), including all 6 real-anchor-day oracle-vs-orchestrator integration parity tests (unaffected) + the 1 new 2025-06-03 anchor. `test_graduated_guards.py` (references these keys in several places incl. an L107 scorecard-correctness guard) — before **11 failed / 95 passed / 1 skipped** (1239.23s), after **11 failed / 95 passed / 1 skipped** (952.42s) — byte-identical failing-test set (`test_l108_tp1_qty_fraction_wired_in_real_fills`, `test_l109_runner_target_wired_in_real_fills`, `test_vix_bull_low_threshold_wired_in_orchestrator`, `test_wick_min_pct_of_range_wired_in_orchestrator`, `test_l122_level_oos_profitable_before_blocking`, `test_block_elite_bull_vix_range`, `test_l124_level_reclaim_positive_oos_expectancy`, `test_rank36_safe_tp1_50pct_oos_improvement`, `test_l177_event_condor_narrow_cache_fails_band_coverage` ×2, `test_run_ps1_ascii_or_bom`) — all pre-existing, none reference either ribbon key, zero regressions introduced.
- **Scope discipline:** pure backtest/research-path hygiene, zero live-trading-behavior change. Did not touch `heartbeat_core.py`, `crypto_twin_*.py`, `participation_cascade.py`, or `automation/state/params.json`/`aggressive/params.json`.

---

## [2026-07-11] PROBE ARM WAS DEAD ON ARRIVAL SINCE SHIP — ledger-source fix (closed, 1 commit)

> Bug confirmed in code review before dispatch (not a hunch, not inferred). `_probe_passed_blocks()` (`automation/state/fleet/build_shared_signal.py`) read `account="bold"` -- a copy-paste of `_bold_passed_blocks`' own read; the docstring even said "off the BOLD ledger (same source `_bold_passed_blocks` already reads)". But the probe arm's ONLY allowlisted cohort (`PROBE_ALLOWED_VERDICTS = {"SKIP_BULL_1100_1200"}`, narrowed same-session by the gate-provenance sweep, commit `54d5840`) maps to `block_bull_1100_1200`, a gate that lives ONLY in Safe's `automation/state/params.json` (confirmed absent from `aggressive/params.json`). Each account's `heartbeat_core.GATE_KEYS`-driven engine (`setup/scripts/heartbeat_core.py:125-133`) reads gate knobs from ITS OWN params file, so Bold's engine has no such key and can never emit `action=="SKIP_BULL_1100_1200"` -- corroborated against 4,342 real bold `core-decisions.jsonl` rows: 0 BULL_1100_1200 hits, ever. The arm built specifically to convert this ONE blocked cohort into forward evidence was reading a ledger where that cohort structurally can never appear. Dead on arrival, silently, from ship (2026-07-10) through this fix.
>
> **Full cohort x account-scope table** (every `block_*` cohort gate in `heartbeat_core.GATE_KEYS`, cross-checked live against both real params files; verdict names confirmed from `backtest/lib/engine/gates.py`, not inferred):
>
> | gate key | verdict | Safe `params.json` | Bold `aggressive/params.json` | on probe allowlist? |
> |---|---|---|---|---|
> | `block_bull_1100_1200` | `SKIP_BULL_1100_1200` | **true** | absent | **YES — the only bypassed cohort** |
> | `block_elite_bull` (+vix band) | `SKIP_ELITE_BULL_LEVEL_RECLAIM` | true (VIX 0-25) | true (VIX 15-18) | no — KEEP, SS-B revalidation ~6.9x worse |
> | `block_bull_ribbon_flip` | `SKIP_BULL_RIBBON_FLIP` | absent | absent | n/a — never armed either side (3rd independent audit) |
> | `block_bull_morning_agg` | `SKIP_BULL_MORNING_AGG` | absent | false (armed off) | no — excluded |
> | `block_level_rejection` | `SKIP_LEVEL_REJECTION_GATE` | true | false | no — excluded (bear-side; allowlist is bull-only anyway) |
> | `block_conf_lvl_rej_midday_afternoon` | `SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON` | absent | false | no — excluded |
> | `block_conf_lvl_rec_afternoon` | `SKIP_CONF_LVL_REC_AFTERNOON` | absent | true | no — excluded (proven stale-bar-echo artifact) |
>
> 100% of today's allowlist is Safe-side, so the fix reads Safe. Note the wider table is genuinely mixed (some gates Bold-only-armed) -- confirms this needed checking per-cohort, not assuming one side.
>
> **Fix (surgical, `build_shared_signal.py` only):** new module constants `PROBE_LEDGER_ACCOUNT = "safe"` + `PROBE_COHORT_GATE_KEYS = {"SKIP_BULL_1100_1200": "block_bull_1100_1200"}`; `_probe_passed_blocks()` now reads `account=PROBE_LEDGER_ACCOUNT` instead of hardcoded `"bold"`. Corrected the stale "off the BOLD ledger" claims in both `build_shared_signal.py`'s comments/docstrings AND `accounts.json`'s `probe_arm._doc`. `_bold_passed_blocks`/`build_shadow`/`SCORING_PEAK_LIVE` (the separate dual-perception scoring-peak paths) untouched -- surgical, not a refactor.
>
> **Guards (`test_probe_arm.py`):** (1) `test_probe_passed_blocks_dead_on_bold_ledger_reads_safe_instead` -- non-vacuity: seeds ONLY a safe-account row with the cohort verdict, asserts `passed=True`. **Verified by ACTUAL execution against the pre-fix code** (git-stashed just the production fix, kept the test, ran it): **FAILED** (`assert False is True`) -- proves the fix changed real behavior, not just a docstring. (2) `test_probe_allowlist_gates_present_on_read_account_params` -- drift guard: for every verdict in `PROBE_ALLOWED_VERDICTS`, asserts its mapped gate key is present in the REAL params file of whichever account the probe reads; **also FAILED pre-fix** (`AttributeError: no attribute 'PROBE_LEDGER_ACCOUNT'`). 3 pre-existing tests had gone silently vacuous (seeded `account="bold"` for a Safe-only cohort, coincidentally passing via a not-found-row empty stub rather than exercising the real block) -- corrected to `account="safe"`: `test_probe_passed_blocks_tags_the_bull_side_with_blocked_verdict`, `test_probe_passed_blocks_elite_verdict_never_passes`, `test_probe_passed_blocks_side_discrimination_bear` (this last one would have started genuinely FAILING post-fix if left unfixed, not just gone vacuous).
>
> **Tests (quoted):** `automation/state/fleet/` full suite -- before **239 passed** (baseline, commit `f799298`), after **241 passed** (+2 net-new guards, zero regressions). `test_probe_arm.py` alone: **41/41** (was 39/39). Daily-cap plumbing (`fleet_live._load_probe_count`/`_record_probe_entry`, the "probe-arm daily-cap counter" fix) re-verified green and unaffected -- `signal['probe']`'s shape is byte-identical, only its source ledger changed, and the daily-cap counter has no coupling to which ledger produced the signal.
>
> De-arm unaffected: `accounts.json`'s `probe_arm.enabled=false` still instantly kills the arm regardless of this fix.

---

## [2026-07-11] GATE-PROVENANCE FOLLOW-UP FIXES — MIN-RIBBON-SEMI-ARMED-FIX + SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (both closed, 2 independent commits)

> From `markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md` findings G8/F1 (ribbon-momentum) and E5/F6 (safe-3 confidence gate), tracked in `automation/overnight/queue.md`. Same investigation also touches the "6 fleet arms, 700+ signals, zero trades" participation-cascade thread from earlier tonight — these two bugs are part of why some of those arms couldn't fire.

- **MIN-RIBBON-SEMI-ARMED-FIX (HIGH), root cause:** `backtest/lib/engine/gates.py:322` checked `params.get("min_ribbon_momentum_cents") is not None` — since `0 is not None` is True, setting the param to `0` (J's L107 revert: "turn this gate off") left it ARMED at threshold 0, silently blocking any bar where the 3-bar ribbon spread didn't strictly widen. Real evidence at the 07-02 audit: 16 blocked rows / 3 should-be-0 episodes in a 30-day window. **Fix:** `is not None` → truthy (`if _rmom_thresh:`) — 1 line, gates.py:323; 0 and None both now mean off, any real nonzero threshold still arms it correctly. Also closed the duplicate queue entry `F1-RIBBON-MOMENTUM-GATE-INVERTED-DISABLE` (same bug, recovered independently 2026-07-08) — the DATA side (params.json 0→null) was already fixed by an earlier session, this closes the remaining CODE-level gap. **Guard:** new `test_gate_min_ribbon_momentum_cents_zero_is_off` in `backtest/tests/test_engine_gates_parity.py` — vary-and-assert on a sharply-contracting ribbon (momentum -30, the exact shape that used to false-block): threshold 0/0.0/None all allow; a real threshold (5.0) on the SAME context still blocks. **Tests:** `test_engine_gates_parity.py` + `test_f1_ribbon_momentum_disabled.py` — before 26/26 passed, after 27/27 passed, including all 6 real-anchor-day oracle-vs-orchestrator integration parity tests (unaffected — none of the pinned anchors exercise this gate at 0). Commit `49e3c40`.
- **Flagged, not fixed tonight (spawned as a separate follow-up, out of tonight's surgical scope):** `backtest/lib/orchestrator.py:1482` has the IDENTICAL `is not None` bug in its own inline gate cascade (the backtest/A-B research path gates.py was extracted FROM — `test_engine_gates_parity.py`'s whole purpose is keeping these two in sync) — a future param sweep that hits `min_ribbon_momentum_cents=0` there would still silently misbehave, an L106/L107-shaped trap. `max_ribbon_duration_bars` has the identical-shaped `is not None` pattern in both files too (currently inert at value 999, not 0 — no live evidence of harm, lower urgency).

- **SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (MED), root cause:** `automation/state/fleet/fleet_executor.py`'s `plan_entry`/`_gate_check` read `blk.get("confidence", signal.get("confidence"))` for the arm's `min_confidence` gate — but `build_shared_signal.py` has NEVER populated a `confidence` field on any signal it emits (its own docstring discloses this: "confidence/confluence/est_premium" omitted, "the pre-LIVE step" that would populate it was never built). Any arm with `min_confidence` set would read `conf=None` forever and ALWAYS hold — not real selectivity, a silent permanent starve. Confirmed the field-name mismatch directly on both sides (not assumed). Git archaeology: `accounts.json.bak-2026-06-25-pre-grid` shows safe-3's original intent was real (`min_confidence: 0.65`, the "A+" arm design, dated back to the 2026-06-22 fleet-go-live commit `3da3747`) — but the 2026-06-25 grid rebuild already dropped `min_confidence` from every LIVE arm (current `accounts.json` has zero `"confidence"` occurrences anywhere), independently corroborated by `backtest/replay_fleet_arms.py`'s own comment ("confidence intentionally ABSENT... is moot now — current accounts.json safe-3 has no min_confidence"). Real evidence at the 07-02 audit: 4 blocked rows in that window (from before the 06-25 rebuild); safe-3 was down to 1 trade/30d. **Fix: DELETED** the dead check from both `plan_entry` and `_gate_check` — chose delete over "fix forward" because populating a genuine confidence score would mean inventing/validating a new scoring model tonight (out of scope for a surgical fix), current live behavior is BYTE-IDENTICAL either way (no arm reads it today), and the grid rebuild had already moved the design away from confidence-gating. **Guard:** new `test_min_confidence_gate_removed_and_inert` in `automation/state/fleet/test_fleet_executor.py` — proves a STALE `min_confidence` key in `gate_override`, fed a confidence-free signal (the real production shape), still ENTERs; plus a source-level check that the read is structurally gone, not just coincidentally unreachable. **Tests:** `test_fleet_executor.py` — before 22/22 passed, after 23/23 passed; full `automation/state/fleet/` test directory (all files) — 239/239 passed after, zero regressions anywhere in the fleet suite.

---

## 🌅 MORNING BRIEF — Friday 2026-07-10 (Fable night watch, ~01:45 ET) — READ THIS FIRST

**Thursday's truth: fleet −$381, core $0, account curve DOWN. Everything below is process until today's P&L says otherwise.**

**✅ OPEN-READINESS: GREEN** (fresh post-reboot audit, `markdown/audits/OPEN-READINESS-2026-07-10.md`, certified at HEAD 2c9b08b + re-verified after later commits): cold-boot imports clean, structure-stop contract wired both lanes, stale exit-states `{}`, breaker rearm dry-run `WOULD_REARM → 2026-07-10`, all triggers valid, CCR up (keepalive auto-revived it post-reboot at 00:07 — its first real save). Macro calendar: **no major prints today**; next = CPI Tue 07-14.

**What trades differently TODAY (all committed, all flag-revertible):**
1. **SS-B structure-stop KEPT + now cent-exact to the validated cell** — same-tick ordering fixed (`53631e2`), certification parity **10/10 MATCH** ($138.5 == study). Instant de-arm: `structure_stop_enabled:false`.
2. **STOP-B DEVIATION RECORD (read if you read nothing else):** the pre-registered de-arm trigger DID fire — SS-B flips all 3 OP-16 J-anchor winners negative (edge_capture −$618, FAIL). **Kept anyway, documented, because the SAME test scores the old control shape WORSE (−$804, also flips all 3)** — the anchors were captured with J's discretionary holds on heuristically-recovered levels; NEITHER mechanical shape passes, so reverting = strictly worse on anchors AND on yesterday's real fills (+$114 vs −$400). The ill-posed pre-commitment is superseded by the paired comparison, not ignored. Full data: `analysis/recommendations/ssb-certification-2026-07-09.json`.
3. **Recency min-sizing LIVE** (`fd08059`): ribbon_ride trades MINIMUM size while its recency is RED (it is) — A/B on 8 real days: −$1,274 → −$793. De-arm: `recency_min_size_enabled:false`.
4. **Veto payload fixed** (`2c9b08b`): free models no longer veto validated setups over `side=None` malformed prompts (~1–2 of yesterday's 14 vetoes were pure artifacts — honest estimate, not the census's 7).
5. **Autopsy sees everything now** (`270f803`) — root cause was NOT core-blindness (my wrong guess): OPRA bar-lag at 16:15 silently rendered 10 real positions as "nothing to autopsy." Fixed + retro-run: **10/10 stopped-then-paid** yesterday.
6. **Mirror spec v2** (`06191cd`): 7th-arm shadow stop widened out of bar noise (1.5→2.0×ATR), forward count reset at zero cost.

**Watch today:** 08:30 breakers re-arm (health flips GREEN) → 09:36 open-bell ping → first structure-stop position shows `STRUCTURE@<level>` on fill pings/glance → clamp line `qty clamped X->3: recency RED` in decisions.

**Pending (owed tonight/evening, not morning-blocking):** ~~final phase5~~ **DONE 03:48 ET, honest stamp `input_complete:true` — 7,560/7,560 grind + 1,081/1,081 funnel → 582 P4 elites → 106 P5 survivors** (top cells = tight-stop/quick-TP/trailing premium shapes, qpf 1.0 full plateaus; premium-only universe, no SS-B bearing by design/waiver; survivor-neighborhood read + too-good audit + promote-pipeline consumption = evening cycle). Still owed evening: block_elite_bull SS-B revalidation (died in reboot); state-truth-table / silent-failure / research-loop auditors (same).

**Night-watch honesty ledger (mine):** wrong autopsy diagnosis (crew corrected with evidence), buggy first funnel watcher (fired instantly, premature phase5 → quarantined), completeness stamp measured one layer of two (hardened to `input_complete`). All three caught same-session because outputs were checked, not trusted.

**J-owed:** cross-ticker brainstorm → `markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md` (written tonight, verdict inside).

- 2026-07-11 ~10:51 ET [weekend grind, free-model-trust, AUDIT-HARNESS-B2] **WIRED `twin_review` as the free-model-audit harness's second subject** (`setup/scripts/free_model_audit_twin_review.py`, registered in `free_model_audit.py`'s `AUDIT_SUBJECTS`). Ground truth here is agreement with a SECOND deterministic judge (`twin_sentinel.py`'s RED/YELLOW/GREEN), not counterfactual replay — new 4th `grading_method` tag `deterministic_cross_check` (GREEN<->HEALTHY, YELLOW<->DEGRADED, RED<->CONCERNING): prefers a same-day recorded `twin-sentinel.json` snapshot (most trustworthy — a real point-in-time judgement), falls back to calling `twin_sentinel.evaluate()` directly since no append-only sentinel-history file exists yet — disclosed caveat that the reconstruction path's BREAKER_TRIPPED/ACCOUNT_REGRESSION rules reflect CURRENT `twin-health.json` state rather than the historical target date (only matters for dates other than "today"). Confirmed the real `automation/state/crypto-twin/reviews/2026-07-11.json` sidecar shape by reading it directly before building against it, per this task's own instruction not to trust the description alone. **REAL dry-run** (`free_model_audit.py --subject twin_review --force`) against the only review that exists (day one, as expected): **1 evidence point, 1/1 correct this run (100%), honestly reported INSUFFICIENT EVIDENCE (1/15 floor)** — no synthetic padding, confidence-bar math reported far below threshold exactly as instructed. **TESTS (quoted, all green):** **56/56** across the full `free_model_audit` family — 17 framework (`test_free_model_audit.py`, 2 updated for the now-wired registry entry + the new 4-tag `GRADING_METHODS` set) + 19 `test_free_model_audit_heartbeat_veto.py` (unchanged, zero regressions) + **20 new** `test_free_model_audit_twin_review.py` (real-sidecar parsing incl. verbatim fixture from the real 2026-07-11.json, date-window filtering, recorded-snapshot vs evaluate()-reconstruction ground-truth dispatch, correct/wrong/ungraded grading paths, real-registry end-to-end). Scorecard: `analysis/free-model-audit/twin-review/2026-07-11-scorecard.md`. Read-only throughout on `heartbeat_core.py`/`crypto_twin_core.py`/`crypto_twin_health.py`/`crypto_twin_scenarios.py`/`twin_sentinel.py`/`twin_review.py` — no order placed, no `params*.json` touched. **FOLLOW-UP FLAGGED, not fixed here (spawned as a separate background task):** `Gamma_FreeModelAudit`'s registered scheduled-task command line (`install-free-model-audit.ps1`) still hardcodes `--subject heartbeat_veto` only — the registry being wired does NOT mean twin_review is actually graded on any cadence yet; needs either a second scheduled action or a loop-over-wired-subjects change. REVERT: delete `setup/scripts/free_model_audit_twin_review.py` + the additive-only registry/`GRADING_METHODS`/docstring edits in `free_model_audit.py` (git revert restores byte-identical; the stub registration this replaces is preserved in git history) + the new `analysis/free-model-audit/twin-review/` dir + this run's 2 new rows in `automation/state/free-model-audit-{history.jsonl,state.json}`.

- 2026-07-11 ~10:20 ET [weekend grind, twin OVERSIGHT PYRAMID, B1] **SHIPPED B1 — UNIT-LOT MODE + the SCENARIO SCHEDULER + path-coverage scoreboard (`markdown/planning/TWIN-PROGRAM.md` value stream #1, "force every exit lifecycle branch through REAL paper fills daily").** B1a: entries now buy a FIXED 3-unit lot (`TwinConfig.units_per_entry=3`, `unit_qty_btc=0.0008` — picked from the live BTC/USD close read this session, $64,178.06, so 3 units = 0.0024 BTC ≈ $154.03, stated not silently derived) instead of a notional amount, so `exit_manager.ExitState.from_entry` sees a REAL integer qty=3 and runs the exact production int-floor split (tp1_qty=2, runner_qty=1 — verified both via fixture AND live). Retires the old `EXIT_UNITS=1000` proxy, which never actually exercised the int-floor arithmetic. B1b: new `setup/scripts/crypto_twin_scenarios.py` forces one of 5 LIVE lifecycle branches/day (ENTRY_TP1_TRAIL, ENTRY_STRUCTURE_STOP, ENTRY_CAT_CAP, ENTRY_MAX_HOLD, RESTART_OPEN_POSITION) via scenario-scoped `dataclasses.replace` overrides (param-freeze: never persisted into the default `TwinConfig`) + passively marks ORGANIC_SIGNAL green on any natural entry; one-at-a-time, N=6/day cap, skips on tripped breaker or an open organic position; grades GREEN on the expected exit stage (or "ribbon_flip"/"time_stop" — genuinely independent live conditions, not a mechanism bug) else INCIDENT, logged loud to new `incidents.jsonl` (the ROI ledger). 3 SIM-tier bear-branch placeholders (`ENTRY_TP1_TRAIL_BEAR`/`ENTRY_STRUCTURE_STOP_BEAR`/`ENTRY_CAT_CAP_BEAR`) seeded `NOT_YET_COVERED` per the coordinator's schema amendment, queued for TWIN-B1.5 (never built this session). `crypto_twin_health.py`'s wrapper now calls the scenario-wrapped tick + extends `twin-health.json` with `{path_coverage, branches_green_today, incidents_today}` (RE-DERIVED every call from `path-coverage.json`, no second source of truth). **2 LATENT BUGS CAUGHT + FIXED while wiring** (this build's own ROI, per TWIN-PROGRAM.md's kill criteria): (1) `manage_positions` passed the raw UTC clock as `exit_manager`'s ET-labeled `time_stop_et` param — any position open when UTC (not ET) crossed 15:50 would've been spuriously force-closed once/day; fixed to `et_clock.et_now(now_utc=...)`. (2) `run_tick` never threaded its own fetched price into `manage_positions`' `last_closed_close` — `stop_mode="structure"` positions could NEVER exit via the dedicated chart-level branch in production (silently fell through to catastrophe-cap/time-stop/max-hold instead); fixed by mirroring `exit_actuator.manage_tick`'s existing real wiring. Neither had ever fired live (n_orders_lifetime was 0 before this session). **LIVE VERIFICATION (real, not simulated):** the REAL `Gamma_CryptoTwin` scheduled task picked up this code autonomously and forced ENTRY_TP1_TRAIL for real ~09:48:50 ET — PLACED (order `8086a471-...`, qty 0.0024 BTC) → FILLED (`filled_avg_price=$64,245.90`) → persisted `ExitState{total_qty:3, tp1_qty:2, runner_qty:1}` (the 2/1 split, live, via the real exit_manager) → `path-coverage.json` correctly shows `ENTRY_TP1_TRAIL: IN_PROGRESS` → every subsequent real 5-min tick (`decisions.jsonl`) correctly carries `scenario:"ENTRY_TP1_TRAIL"` + `position_status:"open"` through MANAGED rows. As of this entry (~29 min in) BTC is oscillating $64,150-64,250 and hasn't yet cleared the +0.15% TP1 level ($64,342) or the -2% stop — still resolving via the real scheduled task (will complete via TP1→trail, the premium stop, ribbon-flip, time-stop, or the 6h max-hold backstop; not a rejection, not a bug — genuinely market-timing-dependent). The exit LEG specifically (TP1 partial + trailing-stop close, MAX_HOLD_FLATTEN, premium_stop cap, a fresh-`TwinConfig`-still-manages-it restart) is separately proven end-to-end via mocked-broker fixtures driving the SAME real `exit_manager`/`run_scenario_tick` code (not faked, disclosed as fixture where live hadn't concluded by report time). **TESTS (quoted, all green):** 38/38 `test_crypto_twin_core.py` (was 25 — 13 new/updated: unit-lot 2/1 split, both ET bugfix directions, structure-stop reachable via `run_tick` not just `manage_positions`, `trigger_level_offset_pct`/`scenario_tag` threading, `get_open_position`/`read_breaker_tripped`), 52/52 new `test_crypto_twin_scenarios.py` (registry shape, coverage day-rollover, branch-priority selection, param-freeze vary-and-assert, one-at-a-time + daily-cap + breaker/organic-position skip, GREEN via MAX_HOLD/CAT_CAP end-to-end, INCIDENT-on-wrong-stage + `incidents.jsonl` full context, staleness timeout, ORGANIC_SIGNAL passive marking, RESTART_OPEN_POSITION's fresh-config property, bookkeeping-error isolation), 32/32 `test_crypto_twin_health.py` (was 25 — 7 new: `summarize_path_coverage` schema/fail-open, real-file integration, the B1b wiring end-to-end). **171/171 total crypto-twin suite green** (99 baseline + 72 net new), zero regressions on `test_crypto_twin_broker.py`/`_reaper_exemption.py`/`_soak_report.py`/`test_firm_brief_twin_section.py` (unchanged) or `test_trade_autopsy.py`/`test_broker_canary.py` (71/71, other crews' consumers). Curated safety gate: **PASS** (31 + 5 suites). **CROSS-SESSION NOTE:** found `firm_brief.py`'s already-shipped B2c coverage renderer reads `path-coverage.json` with a mismatched schema (expects top-level `"paths"` + lowercase `"green"`; the real file — confirmed independently by `twin_sentinel.py`'s own "CONFIRMED... not guessed" schema note — uses `"branches"` + uppercase `GREEN`/`INCIDENT`/etc.) — fails open (renders "no data yet" instead of crashing) but is a real visibility gap; flagged as a spawn_task for whoever owns `firm_brief.py`, not fixed here (out of B1's surface). REVERT: delete `setup/scripts/crypto_twin_scenarios.py` + the additive-only edits to `crypto_twin_core.py`/`crypto_twin_health.py` (every new kwarg defaults None/backward-compatible — `git revert` restores byte-identical organic behavior) + the 2 new `automation/state/crypto-twin/{path-coverage.json,scenario-state.json}` files; the real open BTC position keeps being managed by the unmodified exit_manager either way.

- 2026-07-11 ~10:04 ET [weekend grind, twin OVERSIGHT PYRAMID, B2] **SHIPPED B2 — the TWIN GAUNTLET + conductor hook + autopsy/firm-brief integration (`markdown/planning/TWIN-PROGRAM.md` value stream #2, the "fix -> live-verified in minutes" GATE).** CODE-fix-only lane throughout (doctrine rail: twin validates mechanism, never edge; twin findings never propose SPY parameters). NEW files only in B2's surface (twin_gauntlet.py / twin_gauntlet_conductor_hook.py / 3 test files); `crypto_twin_core.py`/`crypto_twin_health.py`/`crypto_twin_scenarios.py` untouched (B1's concurrent surface, confirmed via zero diffs from this session on any of the three).
  **B2a `setup/scripts/twin_gauntlet.py`:** CLI `twin_gauntlet --paths <ids> [--n N] [--timeout-min 45] [--dry]` over 6 paths (`tp1_trail, structure_stop, catastrophe_cap, max_hold, restart_open_position, entry`). LIVE mode writes APPEND-ONLY REQUEST rows to `automation/state/crypto-twin/gauntlet-queue.jsonl` and polls TWO independent evidence sources (path-coverage.json + the twin's own journal.jsonl directly) up to an honest `--timeout-min` (real BTC lifecycles take minutes — never silently treated as a pass on timeout). `--dry` drives the REAL `crypto_twin_core.place_entry`/`manage_positions` (imported read-only) against an in-process mocked broker for instant, $0, CI-grade feedback — verified live against the actual current `crypto_twin_core.py`: **all 6 paths PASS by default, all 6 correctly FAIL under a deliberately wrong-stage fixture** (the bite VERIFY called for — a --dry mode that always says PASS would be worse than no gate). Ready-made writer (`record_path_result`) + reader (`pending_requests`) for whoever wires B1's scenario scheduler to it — "the one-line hook," documented in the module docstring + `TWIN-PROGRAM.md`'s new "B2 interfaces" section.
  **B2b `setup/scripts/twin_gauntlet_conductor_hook.py`:** advisory, fail-open (every exception caught internally, ALWAYS returns cleanly), NEVER a commit-blocker. Detects trading-path commits (`exit_manager.py`/`exit_actuator.py` -> all 5 exit branches; `fleet_executor.py`/`fleet_live.py`/`heartbeat_core.py` -> all 6 paths; `strategies.py`/`build_shared_signal.py`/`risk_gate.py` -> `entry`) since the last check with no fresh gauntlet-green for their mapped path(s), and emits ONE loud, deduplicated (by newest implicated commit sha — no re-spam of a persisting gap) flag to STATUS.md `## Known broken
[2026-07-11T18:30:04] MCP_AUDIT_RED: Alpaca Safe MCP unreachable (401 auth failure). Bold & TradingView healthy.` + a pickable `queue.md` backlog item. Wired into TWO call-sites sharing one watermark (idempotent): `run-conductor.ps1` (primary, same `Invoke-PythonHidden` pattern as the existing L181 status_retention autowire) + `setup/guard_runner_slow.py` (guaranteed-nightly fallback, a plain try/except'd import — a quiet conductor night no longer leaves this uncovered). **NOT fired live against production STATUS.md/queue.md this session** (deliberate — B1's scenario scheduler is actively mid-flight per its own `scenario-state.json`; firing now would flag a gap that's actively closing rather than prove anything new beyond what the fixture/integration tests already proved cold; UNVERIFIED in production until the next natural conductor/guard fire, labeled honestly rather than implied).
  **B2c** `trade_autopsy.py`: separate `## TWIN (mechanism)` section appended to the SAME daily `.md` (never mixed into the SPY table), sourcing the twin's own `journal.jsonl` — classifies each CLOSED event's `stage`/`reason` against the known `exit_manager` vocabulary (never a $ counterfactual, never P&L — mechanism-only per doctrine). Twin hypotheses land in `automation/state/crypto-twin/twin-hypotheses.jsonl` — a DOCTRINE-RAIL bite test (behavioral + AST-static) proves they can never reach the main `hypothesis-queue.jsonl`. `firm_brief.py`: `render_twin_lines()` extended (backward-compatible — every old single-argument call site renders byte-identical) with a path-coverage scoreboard clause, e.g. `"...orders=3 lifetime. | coverage: 5/6 branches green today, 1 incident(s), gauntlet: PASS 20:41."`, fail-open on missing sources.
  **REAL SCHEMA MISMATCH FOUND + DOCUMENTED, not silently worked around:** B1's live `path-coverage.json` (verified by reading the actual file, not guessing) uses a different shape (`branches`/`ENTRY_TP1_TRAIL`-style names/`PENDING`|`IN_PROGRESS`|... status, corroborated further by the Twin-Sentinel entry directly below showing the confirmed real enum incl. `GREEN`/`INCIDENT`) than the `paths`/green-red schema B2 designed against (per this task's own instruction: "coordinate with B1's schema by reading the doc, not their code" — the doc didn't pin one, so B2 proposed + documented one). Both crews independently converged on the SAME conceptual 6(+3 bear/SIM)-branch battery — a 1:1 name-mapping table + two concrete reconciliation options are in `TWIN-PROGRAM.md`'s new section. B2's readers stay fail-open/honest against the mismatch (render "no path-coverage data yet" rather than fabricate a number) rather than guess-adapting to a still-settling external schema mid-flight.
  **A REAL BUG FOUND AND FIXED IN MY OWN CODE, not just SPY autopsies:** `twin_gauntlet.py`'s `_write_last_result` had a Python def-time-default-binding gotcha — `monkeypatch.setattr(tg, "LAST_RESULT_PATH", tmp)` silently did NOT redirect `main()`'s no-arg call, so my OWN first CLI smoke test wrote a real (if honest) result into the actual production `gauntlet-last.json` before the fix landed; caught by inspecting `git status` for unexpected new files (not by the test suite, which had "passed"), fixed (None-sentinel resolved inside the function body, not a bound default), the stray pre-fix artifact deleted, re-verified the fix actually stops the write. Same bug class, same fix pattern, independently also caught and fixed in `trade_autopsy.py`'s `write_twin_hypotheses`/`append_twin_queue_md` before it ever shipped.
  **TESTS (quoted, all green):** `test_twin_gauntlet.py` **28/28** (queue-contract round-trip, dual-source poll resolution + honest timeout, --dry mode all-6-pass + all-6-wrong-stage-fails, CLI). `test_twin_gauntlet_conductor_hook.py` **21/21** (file->path mapping, detect_gap fresh/stale-evidence/dedup, end-to-end run_check against fixture STATUS.md/queue.md, fail-open, a real read-only smoke test of the git-log parser against this actual repo). `test_trade_autopsy_twin_section.py` **27/27** (classifier, UTC-day filter, rolling detector, render, the doctrine-rail bite test x2 incl. AST-static). `test_trade_autopsy.py` **33/33** unchanged (zero regressions). `test_firm_brief_twin_section.py` **19/19** (9 pre-existing + 10 new coverage/gauntlet tests, incl. a byte-for-byte backward-compat proof for every old call site). = **148 new/updated, zero regressions.** Fast safety gate (`test_graduated_guards.py -m "not slow"`): **71 passed, 1 skipped, 35 deselected** — clean. B1's own suites independently re-verified untouched: `test_crypto_twin_broker.py`/`_reaper_exemption.py`/`_soak_report.py` all green (their `test_crypto_twin_core.py`/`_health.py` in-flight state is theirs to own, not touched by this commit).
  REVERT: `git revert` the commit (all-new-files + additive-only edits to `run-conductor.ps1`/`guard_runner_slow.py`/`trade_autopsy.py`/`firm_brief.py`) restores byte-identical; the two conductor-hook call-sites are each a single wrapped `try/catch`/`try/except` block, trivially removable independently.

- 2026-07-11 ~10:02 ET [weekend grind, twin OVERSIGHT PYRAMID] **SHIPPED Gamma_TwinSentinel — the deterministic RED/YELLOW/GREEN judge for the CRYPTO TWIN (`markdown/planning/TWIN-PROGRAM.md`) + nightly FREE-LLM review, REGISTERED + VERIFIED LIVE (every 15 min, 24/7).** New: `setup/scripts/twin_sentinel.py` (pure Python, $0 — reads `decisions.jsonl`+`twin-health.json`+`path-coverage.json`+`incidents.jsonl`, all READ-ONLY, never edits any B1/B2-owned file) + `setup/scripts/twin_review.py` (nightly free-LLM review, one call via `swarm_client.call_role_json`) + `setup/scripts/install-twin-sentinel.ps1`. **6 rules:** TICK_GAP (RED, >20min stale or no tick ever), LOW_UPTIME (YELLOW, <70% of expected UTC-day ticks once ≥1h elapsed — this module's own derived threshold, documented as such since the task spec only named an explicit number for the other rules), INCIDENT_SPIKE (RED, ≥3/day — **dual-sourced**: an `incidents.jsonl` scan `max()`'d with `path-coverage.json`'s own per-branch `status=="INCIDENT"` count), COVERAGE_LAG (YELLOW, <50% branches green by 18:00 UTC), BREAKER_TRIPPED (RED), ACCOUNT_REGRESSION (RED, `LIVE`→anything else vs the sentinel's OWN prior run since `twin-health.json` has no history). **CONCURRENT-EDIT CATCH (verify-don't-assume, OP-33):** B1 shipped `path-coverage.json`'s real schema (`{date_utc, branches: {name: {tier, status, count_today, last_exercised_utc, last_result}}}`, status ∈ {PENDING,IN_PROGRESS,NOT_YET_COVERED,GREEN,INCIDENT}) DURING this build — my first draft had *guessed* a case-insensitive `"green"/"pass"/"ok"/"true"` string-match schema that would have silently mis-parsed the real dict-of-dicts shape (0 green ever detected). Caught via the crypto-twin family's OWN regression sweep (an unrelated pre-existing test in `test_crypto_twin_health.py` failed on B1's new fields, which is what surfaced the concurrent ship) — rewrote `parse_path_coverage()` against the confirmed real producer (`crypto_twin_scenarios.py` + `crypto_twin_health.summarize_path_coverage()`) before shipping, added dedicated tests locking in the real shape + case-sensitivity + the dual-incident-source `max()` behavior. **Escalation:** on a NEW transition into RED, one `automation/overnight/queue.md` row under `## Twin escalations` ("dispatch a Sonnet investigation") + one Discord ping, de-duped PER EPISODE (persisted in `twin-sentinel.json`'s own `escalation` block, resets on recovery, re-arms next RED, self-heals a failed write by retrying next fire). **Nightly review:** triggered internally by the SAME task once/day after 23:30 UTC (no second task) — asks ONE free-tier model (`critic` role: OpenRouter free-tier → Cerebras free dev tier → local Ollama floor) for structured JSON (`assessment` HEALTHY/DEGRADED/CONCERNING + `confidence` + `flags_raised` + `summary`), writes BOTH `reviews/YYYY-MM-DD.md` (human) and a `.json` sidecar (coordinator request mid-build, for a separate cross-component free-model audit harness being built in parallel to grade mechanically without re-parsing prose) — confirmed shipped this session. If all free lanes are down, writes the deterministic NO-LLM stats-only version (mechanically classified from tick-error/incident counts, confidence fixed low at 0.4) — never skips silently. **DELIBERATE DEVIATION (disclosed, not silent):** does NOT fall back to `kitchen_daemon.MODEL_LADDER`/`run_minimax.call_minimax` the way `kitchen_seeder.py` does — verified (not assumed) that ladder's `DEFAULT_MODEL` (`minimax/minimax-m2.5`) is a PAID OpenRouter model (real `$/token` PRICING dict, de-tagged from free 2026-07-01, `DAILY_CAP_USD=$5`) before deciding to exclude it; wiring a paid fallback into a new unattended-forever nightly task would violate this build's own $0 HARD COST RULE — guarded by a static source-scan test (`test_twin_review_never_references_the_paid_model_ladder`) so it can't silently creep back in. Sonnet/Claude is NEVER scheduled — only summoned by the queue.md escalation row. **TESTS (quoted, all green):** `test_twin_sentinel.py` 63/63 + `test_twin_review.py` 26/26 = **89/89 new**, zero regressions on the crypto-twin family (`test_crypto_twin_core.py`+`_broker.py`+`_reaper_exemption.py`+`_soak_report.py`+`test_firm_brief_twin_section.py`+`test_ccr_keepalive.py` = 121/122 — the 1 failure, `test_write_twin_health_schema_keys`, is PRE-EXISTING and NOT mine: B1's own concurrent `path_coverage`/`branches_green_today`/`incidents_today` ship to `crypto_twin_health.py` (a file I never touched — confirmed via `git status` showing zero diffs from me on any B1/B2-owned file) needs its OWN test's `expected_keys` set updated, out of this task's scope). `test_scheduled_tasks_doc.py` 5/5 (count bumped 75→76, new Active row documented). Curated safety gate: **PASS** (31 + 5 suites). **REGISTERED + VERIFIED LIVE:** `Get-ScheduledTask` → `State=Ready`, real command line confirmed (`wscript.exe //nologo run_exe_hidden.vbs backtest\.venv\Scripts\pythonw.exe twin_sentinel.py`), trigger `PT15M`/`P3650D` (15 min, 10-year repetition — not the one-time-trigger foot-gun), reaper exemption independently re-verified against the LIVE `_shared.ps1` source this session (`pythonw.exe` absent from the `Win32_Process` Name filter + `backtest\.venv` in `$EXEMPT_DAEMONS`). `Start-ScheduledTask` fired manually: real `twin-sentinel.json` updated (`ticks_today_utc` 155→156, `checked_at_utc` matching `LastRunTime` exactly), verdict `GREEN` against real live twin state (93% uptime, 0/9 coverage branches green — correctly not yet COVERAGE_LAG'd since pre-18:00-UTC, 0 incidents both sources, breaker clear, `account_status: LIVE`). **Cost: $0/day baseline** (pure-Python judge + free-tier-only nightly review; Sonnet/Claude summoned only by escalation, never scheduled). **Note for the BROKER CANARY crew (see entry directly below):** `Gamma_TwinSentinel` now exists — their queued `BROKER-CANARY-SENTINEL-HOOKUP` (queue.md) can ride this task's cadence instead of waiting on `Gamma_CryptoTwin`. REVERT: `Unregister-ScheduledTask Gamma_TwinSentinel` (or `install-twin-sentinel.ps1 -Uninstall`) + delete the 3 new files; `SCHEDULED-TASKS.md` edits are additive-only.

- 2026-07-11 ~09:47 ET [build, market CLOSED Saturday] **SHIPPED the BROKER CANARY — the 24/7 crypto twin's own Alpaca API calls now feed the 08:25 ET pre-open readiness gate** (`markdown/planning/TWIN-PROGRAM.md`). NEW files only — `crypto_twin_core.py`/`crypto_twin_health.py` untouched (another crew owns those this session, confirmed via `git diff --stat` showing 195 uncommitted insertions already in `crypto_twin_core.py` before this build touched anything). `setup/scripts/broker_canary.py` (library + tiny CLI, $0, piggybacks ONE unauthenticated crypto-bars request (limit=1, `creds={}` forces no auth header) + ONE authenticated `GET /v2/account` when the twin's dedicated account is configured — reuses `crypto_twin_broker`'s own already-tested HTTP client, adds zero new client code): `record_observation()` appends to a size-capped rolling `automation/state/broker-canary.jsonl` (~2000 rows, trimmed on exceed); `assess()` computes `{verdict,p50_latency_ms,error_rate_1h,auth_ok,last_ok_et,detail}` (YELLOW: p50 > 2x trailing-24h median OR any auth failure in the last hour; RED: >=3 consecutive failures OR auth dead > 15m) and writes the glance `automation/state/broker-canary.json`; `probe()` IS the one-line hookup — calling it alone runs both legs AND refreshes the glance file, nothing else to wire. `setup/scripts/preopen_readiness.py` gained a new `broker_canary` check (`assess_broker_canary`/`fetch_broker_canary`, wired into `build_report`/`main`): a RED canary REDs the fused pre-open verdict (the actual payoff — an Alpaca outage surfaces hours before the 09:30 open instead of at it); a missing/stale (>60min) canary file degrades to non-critical INFO, never RED — deliberately the OPPOSITE fail-direction from the other preopen checks (which fail TOWARD red), because the canary is a piggybacked enhancer riding on the twin, never a new single point of failure for the live chain. **LIVE-VERIFIED for real, not simulated:** bars leg 160.2ms ok (BTC $64,196.5575), account leg 128.6ms ok (twin's dedicated paper account, `status=ACTIVE`), `assess()` → GREEN, `n_observations=2` — both real rows + the glance json are committed state (`automation/state/broker-canary.jsonl`/`.json`). **NO scheduled task registered** (checked for `Gamma_TwinSentinel` first — zero hits repo-wide via grep, so per the build's HARD RULES this ships as a library, not a new task/sprawl) — the one-line hookup (`broker_canary.probe()`) is queued in `queue.md` → `BROKER-CANARY-SENTINEL-HOOKUP` for whichever tick already owns the twin's 24/7 cadence (`Gamma_CryptoTwin` today). **TESTS (all quoted, all green):** new `backtest/tests/test_broker_canary.py` **38/38** (rolling-cap trim + exact-boundary-no-trim; probe() forces `creds={}` + `limit=1`, skips the auth leg with zero phantom rows when no twin account is configured, fail-open on EITHER leg's exception, exactly ONE authenticated call per probe — not two via `get_twin_creds(verify_crypto_status=False)`; assess() verdict rules bite-tested per rule: latency-spike YELLOW + no-baseline-skips-the-rule, auth-failure-in-1h YELLOW, 3-consecutive RED + 2-consecutive-boundary stays GREEN + streak-resets-on-recovery, auth-dead>15m RED + <15m stays YELLOW (the escalation ladder) + never-configured stays GREEN, RED-overrides-YELLOW-both-reasons-disclosed, error_rate_1h/last_ok_et/auth_ok field bites, never-raises-on-malformed-rows (a real latent `auth_rows[-1]["ok"]` KeyError bug caught + fixed to `.get("ok")` before shipping), CLI `--assess-only` never calls `probe()`). `backtest/tests/test_preopen_readiness.py` **59/59** (was 42 — +17 new: INFO-not-RED on missing/empty/unrecognized canary verdict with a non-vacuous `fuse()` check, RED/YELLOW/GREEN verdict mapping, fetch fail-open on missing/malformed/no-timestamp file, staleness-window boundary bites just-inside/just-outside `CANARY_MAX_AGE_MIN`, `build_report` end-to-end: RED canary REDs the fused verdict, absent/`None` canary never REDs alone, a healthy canary never masks an unrelated real RED elsewhere). Zero regressions on the other crew's own suite (`test_crypto_twin_broker.py`/`test_crypto_twin_health.py`/`test_crypto_twin_reaper_exemption.py`/`test_crypto_twin_soak_report.py`/`test_firm_brief_twin_section.py`, 106/106 combined incl. their 2 pre-existing in-flight FAILs in `test_crypto_twin_core.py`, confirmed not caused by this build and left untouched per the hard rule not to edit that file). Curated safety gate: **PASS** (31 + 5 suites green). REVERT: delete `setup/scripts/broker_canary.py` + the additive-only `broker_canary` block in `preopen_readiness.py` (new constants + 2 new functions + one extra `build_report`/`main` arg — `git revert` restores byte-identical) + the 2 new `automation/state/broker-canary.*` files; the queue.md hookup note is inert until someone adds the one line.

- 2026-07-10 ~21:44 ET [J requirement, crypto twin T3] **SHIPPED T3 — Gamma_CryptoTwin REGISTERED (every 5 min, 24/7, reaper-exempt) + full OP-33c visibility stack; soak data now accruing tonight even though T2's order path is still the disclosed `BLOCKED_NO_ACCOUNT` no-op.** New: `setup/scripts/crypto_twin_health.py` (thin wrapper AROUND `crypto_twin_core.run_tick()` — T1/T2's tested 40/40 surface is imported, never edited — catches ANY exception so a genuine network/HTTP failure, which `crypto_twin_broker` deliberately fail-louds on, can never silently vanish under pythonw's discarded stderr; logs a `TICK_ERROR` decision row + always writes the health/soak snapshots regardless of tick outcome) + `setup/scripts/crypto_twin_soak_report.py` (T4's Sunday reader: tick count, uptime estimate, action distribution, recent errors, from `soak-log.jsonl` + `decisions.jsonl`) + `setup/scripts/install-crypto-twin.ps1`. **REAPER EXEMPTION VERIFIED, not assumed** (this class of bug has silently killed grinds here before): launched via `backtest\.venv\Scripts\pythonw.exe`, not system python — `pythonw.exe` sits outside `Stop-StaleClaudeProcesses`'s `Win32_Process` Name filter entirely (`Name='claude.exe' OR 'node.exe' OR 'python.exe' OR 'uv.exe' OR 'uvx.exe'`, confirmed by reading the live source), so the twin's process is never even fetched by the reaper's query — PLUS the `backtest\.venv` path substring independently matches an existing `$EXEMPT_DAEMONS` entry as defense in depth. **REGISTERED + VERIFIED LIVE THIS SESSION:** `Get-ScheduledTask` → `State=Ready`, real command line confirmed (`wscript.exe //nologo run_exe_hidden.vbs backtest\.venv\Scripts\pythonw.exe crypto_twin_health.py --live`), trigger `PT5M` / `P3650D` (5 min, 10-year repetition — not the one-time-trigger foot-gun). `Start-ScheduledTask` fired manually: `decisions.jsonl` went 6→7 real rows (new row `ts_et 2026-07-10T21:43:18`, real BTC $64,017.995, `armed:true`), `automation/state/twin-health.json` created for the first time (`ticks_today:7, last_action:HOLD, breaker_tripped:false, account_status:BLOCKED_NO_ACCOUNT, n_orders_lifetime:0, last_error:null`), `soak-log.jsonl` + `soak-watermark.json` created with a correct first hourly rollup. `NextRunTime` recalculated to +5 min post-fire (not dark). Visibility: ONE `TWIN:` line folded into the existing `firm_brief.py` generator (fail-open, reads `twin-health.json`, zero new report surface) — `render_twin_lines()`. **TESTS (quoted, all green):** `test_crypto_twin_health.py` 25/25 (ticks/orders counters, account_status, health-json schema + fail-open, soak-row watermarking incl. restart-survival + multi-hour-gap-is-one-row-not-a-backfill-loop, the error-capture wrapper never raising) + `test_crypto_twin_reaper_exemption.py` 14/14 (static, parses the REAL `_shared.ps1`/`install-crypto-twin.ps1` source — no live Windows calls) + `test_crypto_twin_soak_report.py` 15/15 + `test_firm_brief_twin_section.py` 9/9 = **63/63 new**, zero regressions on `test_crypto_twin_core.py`+`test_crypto_twin_broker.py` (40/40 unchanged) or the 20 other `firm_brief`-keyword tests. Curated safety gate: PASS (31 + 5 suites). **J-OWED (unchanged blocker, not new):** T2 still needs ONE more dedicated Alpaca paper account — drop `key`/`secret` into `automation/state/crypto-twin/secrets.json` (gitignored; template = `secrets.json.example` in the same dir) — zero code changes needed, the very next 5-min tick starts placing real crypto paper orders. REVERT: `Unregister-ScheduledTask Gamma_CryptoTwin` (or `install-crypto-twin.ps1 -Uninstall`) + delete the 3 new files; `firm_brief.py`/`SCHEDULED-TASKS.md` edits are additive-only (git revert restores byte-identical).
- 2026-07-10 ~21:10 ET [J requirement, crypto twin T1+T2] **SHIPPED the CRYPTO TWIN — 24/7 mechanism-validation training ground for BTC/USD on Alpaca crypto paper** (`markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md`, J verbatim: "get an MCP that trades crypto and just replicate the engine there... I can't keep fixing four things and waiting for the next day"). NEW namespace only: `setup/scripts/crypto_twin_{core,broker,levels,signal}.py` (~1,230 lines) + `automation/state/crypto-twin/` — zero writes outside it (static AST guard + runtime `_assert_twin_namespace`), zero edits to `heartbeat_core.py` (another crew owns its stale-trigger fix tonight) or any SPY/fleet state.
  **T1 (SEE/DECIDE) — LIVE-VERIFIED, real BTC/USD, needs no credentials:** fetches real 5m Alpaca crypto bars (public market-data endpoint, confirmed live even fully UNAUTHENTICATED), closed-bar-only (C6, `crypto.lib.bar_reader`), UTC-day session anchors (prior-UTC-day H/L/C + intraday H/L, `crypto_twin_levels.py`), ribbon (fast=13/pivot=20/slow=48 — the exact fingerprinted production periods, `crypto.lib.ribbon`) + level-reaction trigger (`crypto_twin_signal.py`) -> `automation/state/crypto-twin/decisions.jsonl`, same key set as `core-decisions.jsonl` + `twin:true`. 3 real ticks quoted this session: BTC $64,083.10, ribbon BULL, real prior-day levels ($64,682.13 H / $62,904.09 L / $64,124.21 C).
  **T2 (ACT/EXIT) — CODE COMPLETE + fixture-verified against the REAL exit_manager, LIVE ROUND-TRIP BLOCKED (disclosed, not faked):** placement via `crypto_twin_broker.place_crypto_order` (notional-based market orders, time_in_force=gtc — crypto rejects "day"), exit management is the REAL `exit_manager.ExitState`/`plan_exit_actions` (structure stop = close through the twin's own level, catastrophe-cap fallback, TP1 partial + BE ratchet, trailing chandelier runner — percentages recalibrated to spot-BTC volatility, not options-premium scale, so every stage gets a realistic chance to fire during a soak), UTC-day breaker (`crypto.lib.kill_switch`, equity carries forward day-to-day), max-hold flatten (6h), journal lifecycle rows (PLACED/FILLED/MANAGED/CLOSED). `risk_gate.check_order` genuinely executes via a documented whole-number proxy (qty=1/premium=$2.00 so premium*qty*100==$200 notional) since it's built for integer option contracts, not fractional BTC.
  **THE BLOCKER (why T2 has no live order tonight):** all 6 Alpaca paper accounts this repo holds credentials for (`automation/state/fleet/secrets.json` + `.mcp.json`) are ALREADY the SPY fleet's 4 challenger arms or the 2 core (safe-2/bold-2) controls — confirmed via `fleet_live.py:444` that the grid's kill-switch/risk-cap math reads LIVE BROKER EQUITY (`GET /v2/account`, a unified per-account total across every asset class), so adding BTC positions to any of them would corrupt that arm's SPY-attribution, not just look untidy. Refused rather than risk it. `--force-entry bull --live` was run for real tonight: verdict/risk_gate/breaker all fired correctly (risk_gate ALLOW, "$200 within all caps"), and the run correctly stopped at `BLOCKED_NO_ACCOUNT` rather than placing anywhere or faking a fill. **UNBLOCKS WITH:** J creates ONE more Alpaca paper account via the dashboard (same 2-minute action taken 6 times already per CHANGELOG — 2026-05-17 evening, 2026-06-24 grid rebuild) and drops key+secret into `automation/state/crypto-twin/secrets.json` (gitignored; `secrets.json.example` in the same dir is the tracked template) — zero code changes needed, the very next tick places for real.
  **TESTS (quoted, all green):** `backtest/tests/test_crypto_twin_core.py` 25/25 (closed-bar adapter, UTC-day level anchors + no-look-ahead, breaker seed/trip-latch/day-rollover-carry-forward, risk_gate proxy, exit_manager integration on twin fixtures via a mocked broker — structure stop, catastrophe-fallback, TP1 partial, TRAILING ratchet-then-stop, max-hold flatten, BLOCKED_NO_ACCOUNT fail-closed, bear-verdict never shorts, static namespace-isolation guard, decision-row schema compat) + `backtest/tests/test_crypto_twin_broker.py` 15/15 (creds load/error paths, order refusal logic, gtc time-in-force, fractional-qty position read). Zero regressions: fleet's own `test_exit_manager.py`/`test_fleet_executor.py`/`test_probe_arm.py` 112/112 unchanged. Curated safety gate: PASS (31 + 5 suites).
  REVERT: delete `automation/state/crypto-twin/` + the 4 new `setup/scripts/crypto_twin_*.py` files; nothing else touched (`heartbeat_core.py`, `params*.json`, `fleet/*` all untouched).
- 2026-07-10 ~01:03 ET [paper-autonomy ship, market CLOSED] **SHIPPED recency-conditioned min-sizing for ribbon_ride (A/B: -1274->-793 on 8 real days) flag-gated, flag-ON both accounts** (`recency_min_size_enabled=true`, Safe + aggressive params.json) — at entry-sizing time (`automation/state/fleet/fleet_executor.py#_apply_recency_min_sizing`, wrapping all 3 `_qty_for` call sites: `plan_entry` L~322, `_plan_from_strategies` L~422, `plan_all`'s side-block fallback L~488), when ribbon_ride's CURRENT recency verdict (new `_recency_verdict` helper, reading `automation/state/recency-confirmation.json` `headline.any_red`/`edges_confirmed_on_recent` — the SAME field `contender_oos_check.assess_recency_gate`/`autonomy_actuator._recency_gate_clears`/`task_scorer._recency_explicitly_red` already gate capital on) is RED, qty is clamped DOWN to the account's `min_contracts` floor (Safe 3 / Bold 5) via `min()` (a ceiling, never a floor-raise); YELLOW/GREEN pass through unchanged; missing/unreadable recency file fails OPEN (normal sizing, never blocks a trade). Scope: ribbon_ride ONLY (the A/B's population, C29) — vwap_continuation untouched even with the flag on. EVIDENCE: `analysis/recommendations/recency-sizing-ab.json` (`policy_dominates=true`, 8 REAL fleet-fill trading days 2026-06-29..2026-07-09, point-in-time verdicts / no look-ahead leak, its own leak-bite test) — total -$1,274 -> -$793, worst day -$388 -> -$297 (54/89 real positions were sized above the floor and get capped). Staged mechanism the A/B crew handed off: `analysis/recommendations/recency-sizing-proposal.json`. CAVEAT (disclosed in the A/B, honored here): every one of the 8 sampled days verdicted RED, so ONLY the RED->floor branch is evidence-backed — the staged proposal's YELLOW->0.5x tier is UNPROVEN on real data (no YELLOW/GREEN day in the sample) and deliberately NOT implemented; ships RED-floor-only, not the full 3-tier shape. Glance surface (OP-33): a placement-log line fires when the clamp actually engages (`"qty clamped 5->3: recency RED"`, printed to stdout + folded into the plan's `.reason`, so it lands in `decisions/*.jsonl`). TESTS (quoted, all green): new `automation/state/fleet/test_recency_min_sizing.py` 25/25 (RED->clamped-to-floor, GREEN/YELLOW->unchanged, missing-file->fail-open-unchanged, malformed-JSON->fail-open, flag-off->byte-identical vary-and-assert, vwap_continuation->unaffected even RED+flag-on, already-at-floor->no spurious note, wired end-to-end through all 3 real call sites not just the helper, live-params-shape pin); full fleet suite `automation/state/fleet/` 199/199 (3 pre-existing tests fixed: `test_params_patch_qty_drives_plan_qty`/`test_bold_loose_places_at_equity_within_cap`/`test_safe_loose_places_at_equity_within_cap` read the LIVE params.json via `_params_for` for an unrelated tier-patch/risk-cap axis and were incidentally exposed to the live recency-confirmation.json's real RED state once the flag shipped true; now explicitly neutralize `recency_min_size_enabled` inline since that axis has its own dedicated test file — root cause was accidental coupling to global mutable state, not a logic bug); curated safety gate PASS (31 + 5 suites green, `test_params_filters_drift.py` confirmed the new key does not match v25's gate-key patterns so no heartbeat.md presence assertion was needed); broader `backtest/tests -k recency` sweep 54/54 green (untouched). REVERT: instant de-arm = set `recency_min_size_enabled:false` in `automation/state/params.json` + `automation/state/aggressive/params.json` (byte-identical to pre-ship sizing, proven by the flag-off vary-and-assert test); full revert = git revert this commit.

- 2026-07-10 ~18:30 ET [paper-autonomy ship, market CLOSED] **SHIPPED the PROBE ARM — risky-3 trades ONE gate-provenance-reviewed blocked cohort (SKIP_BULL_1100_1200) at min size + a nearer strike, flag-ON** (J directive 2026-07-10, verbatim: "6 arms and nothing took a trade... why isn't 1 arm set to take riskier trades? we have 3 risky and 3 bold"). DIAGNOSIS (grounded in real 07-10 evidence): every fleet arm's `_gate_check` only ADDS selectivity on top of an already `passed=True` shared-signal tick — it can never RESCUE a `passed=False` one, however loose `gate_override` is — so the cohort/tier gates baked into `build_shared_signal.py`'s passed-derivation apply UNIFORMLY to every arm regardless of individual looseness. ARM CHOSEN: **risky-3** ("risky x loose" cell — already the fleet's loosest gate_override + riskiest sizing + `fleet_rest` execution, a code path fully separate from the `mcp_heartbeat` safe-2/bold-2 controls — ZERO risk to core behavior — over risky-1 (inverted-intent TIGHT), safe-1/safe-3 (contradicts "riskier"), or safe-2/bold-2 (off-limits core controls). **This build went through TWO mid-flight amendments from concurrent research sessions — both independently VERIFIED against primary artifacts before being applied, neither taken on faith:**
  1. **AMENDMENT 1** (`automation/state/participation-cascade.json`): `min_entry_premium` — NOT the cohort gates — is the real #1 blocker in practice (18 of 31 arm-events on 07-10 alone). Verified directly by reading `top_blockers` (`min_premium_floor n=18` vs `block_elite_bull n=4`) and by this build's OWN earlier real-log reads (`decisions.jsonl` 11:22/11:34/11:52/11:55 ET all terminal-HOLD'd on `"premium 0.06-0.15 < floor 0.3"`). Fix: the $0.30 floor is NEVER bypassed (stays fully intact for every arm) — instead `fleet_executor.PROBE_STRIKE_TIERS` (a standalone nearer/ATM-class table, NOT a reference to `V15_SAFE_TIERS`) gives probe's own contracts a nearer strike than the arm's normal bold/OTM table, so they clear the SAME floor on their own merits.
  2. **AMENDMENT 2** (`markdown/audits/GATE-PROVENANCE-SWEEP-2026-07-10.md`, commit `54d5840` — a rigorous, pre-registered, hash-pinned, 19/19-test-covered per-gate audit): NARROWED the bypass from a broad "any cohort gate except a hard-safety exclude-list" blocklist to an explicit allowlist, `build_shared_signal.PROBE_ALLOWED_VERDICTS = {"SKIP_BULL_1100_1200"}` exactly. Verified directly by reading `analysis/recommendations/block-elite-bull-ssb-revalidation.json` in full: `block_elite_bull`'s SS-B revalidation (relaunched THIS session under a frozen pre-reg) proved **KEEP** — n=28, OLD total -$560.00 -> SS-B total -$3,873.60, **~6.9x WORSE** under the SAME structure-stop exit shape probe's own `ribbon_ride` entries use. Bypassing a hash-pin-proven loser cohort under the exact shape that just re-proved it a loser would spend real paper capital re-answering an already-answered question — **removed entirely, never bypassed.** `SKIP_BULL_1100_1200` stays bypassed (verdict: REVALIDATE — thin `n=11 IS/n=1 OOS`, pre-SS-B, first genuinely-live SUPER-tier block since ratification: exactly the shape of gate a min-size forward probe should test). `block_bull_ribbon_flip` reconfirmed a 3rd independent time — absent/unarmed, no bypass built for it (never was).
MECHANISM (flag-gated, default = exactly what ships): (1) `build_shared_signal.py` — new `passed_probe_cohort()`/`_probe_passed_blocks()` (`PROBE_COHORT_LIVE=true`) emit `signal['probe']` off the BOLD ledger: `passed=True` ONLY when `action` is in `PROBE_ALLOWED_VERDICTS` AND a real named `ENTRY_TRIGGERS`-member trigger actually fired — everything else, including `block_elite_bull`'s `SKIP_ELITE_*` verdicts and a bare `"HOLD"` (which `_map_core_row` collapses the 3 time-gate skips into while still copying `triggers_fired` through — a subtlety a red test caught before shipping), returns `False`. `blocked_verdict` carries the original verdict for attribution. (2) `fleet_executor.py` — new `_is_probe_active()`/`_cohort_tag()`/`_probe_plan()`/`PROBE_STRIKE_TIERS`, wired into `plan_all()` as an ADDITIVE tail step: fires ONLY when `accounts.json` top-level `probe_arm.enabled=true` AND `arm.id == probe_arm.arm_id` AND the arm's NORMAL pass (FIX2 `_plan_from_strategies` or the v1 side-block fallback, UNCHANGED — pure structural move) produced no ENTER this tick (never double-fires). Scope: `ribbon_ride` ONLY — `vwap_continuation` is a live REST detector, no core-gate cohort to bypass. qty = `params.min_contracts` HARD-CLAMPED. Strike = `PROBE_STRIKE_TIERS` (nearer than `_tiers_for_arm`'s normal result). Reason tag `"PROBE_ARM cohort=bull_1100_1200"` on every fill. (3) `fleet_live.py` — new persisted `{arm}/probe-count.json` daily counter (`_load_probe_count`/`_record_probe_entry`, same date-reset pattern as `_load_or_arm_breaker`'s kill-switch), threaded through `decide_arm`/`plan_all`; increments ONLY on a risk_gate-`ALLOW`ed `PROBE_ARM`-tagged `ENTER_BULL` (never on HOLD/deny). RAILS (non-negotiable, verified not asserted): kill-switch/PDT/`min_entry_premium` floor (unweakened)/per-trade risk cap/entry-time floor-ceiling/one-position ALL still bind — none of that logic was touched; all run downstream in the SAME `finalize()`/`risk_gate.check_order`/`_place_live` every other arm uses. Daily cap = 3, enforced pre-ALLOW with a distinct `"...blocked: daily cap reached (N/cap)"` HOLD reason, resets on date rollover. `structure_stop_enabled` SS-B exit shape is UNCHANGED for probe fills — same `RIBBON_RIDE` registry entry every other arm trades. ATTRIBUTION: arm id already separates probe fills in `pnl-statement`/journal; `decisions.jsonl` reason carries the cohort tag; `gamma_glance.py` gained a new `PROBE ARM` block (`PROBE: risky-3 N/3 entries today, cohorts x/y`, pure disclosure, never RED on its own, ASCII-safe — guard `test_gamma_glance_guard.py` still 3/3 green). INSTANT DE-ARM: `automation/state/fleet/accounts.json` → `probe_arm.enabled: false` (byte-identical revert — `_is_probe_active` short-circuits False; proved by `test_plan_all_flag_off_byte_identical_across_all_fleet_arms`). Full revert = git revert this commit. TESTS (all quoted, all green): new `automation/state/fleet/test_probe_arm.py` **39/39** — 4 layers: (A) producer allowlist behavior (`SKIP_BULL_1100_1200` bypasses; `block_elite_bull`'s verdicts, other cohort gates, all safety/time-gate skips, and bare HOLD all explicitly do NOT; side discrimination via the ledger's OWN `side` field; `build()` end-to-end with paired safe+bold fixtures matching real production row-pairing; flag-off → no `'probe'` key); (B) consumer `plan_all` (flag-off byte-identical across all 4 real fleet arms AND vs the pre-ship call signature; flag-on fires ONLY for risky-3, other 3 BYTE-IDENTICAL; **AMENDMENT 2's explicit acceptance test: an ELITE-blocked signal produces zero ENTER on EVERY arm including the probe**; min-size clamp holds against `elite_qty=12` AND `min_contracts=5`; daily cap at the boundary; scope-guard rejects non-ribbon setups; no double-fire when the normal path already entered; the SKIP_BULL_1100_1200 acceptance fixture); (C) `fleet_live` persisted counter (fresh/persist/reset-next-session) + `decide_arm` end-to-end through the REAL `risk_gate.check_order` (ALLOW, premium-floor denial, kill-switch denial, not-flat denial, cap-boundary, non-probe-arm untouched, ELITE-blocked-signal-never-allowed); (D) **AMENDMENT 1's named acceptance fixture** — probe's strike verified NEARER to spot than the arm's own bold/OTM strike (a strike-delta assertion), `PROBE_STRIKE_TIERS` proven a standalone object (not a `V15_SAFE_TIERS` alias) with matching values, and: a far-OTM $0.07 premium denies with `SKIP_MIN_PREMIUM_FLOOR` (floor still binds) while the SAME tick's nearer-strike $0.35 premium ALLOWs at the ATM strike, qty 3. Full fleet suite `automation/state/fleet/` **238/238** (199 prior + 39 new, zero regressions). Curated safety gate: **PASS** (31 + 5 suites green). Consumer sweep outside the fleet dir (incl. the OTHER session's own `test_block_elite_bull_ssb_revalidation.py`, verifying the study this ship relies on is itself internally consistent): **57/57**. DISCLOSED, NOT MINE: `backtest/tests/test_fleet_arm_parity.py` (4 tests) + `test_fleet_keystone_consumer.py` (1 test) FAIL on this branch — verified PRE-EXISTING by `git stash`-isolating the changed files and re-running against clean HEAD: identical 5 failures reproduce with ZERO probe-arm code present. Root cause: both files call `fx._params_for(...)` which reads the LIVE `automation/state/params.json`/`aggressive/params.json` (`recency_min_size_enabled=true`, shipped this morning, `recency-confirmation.json` currently RED) for an unrelated qty-tier-pin assertion — the SAME "accidental coupling to global mutable state" bug class the 01:03 ET entry above already fixed in 3 OTHER files; these 2 were simply not in that earlier sweep. Genuinely out of scope for a probe-arm ship — flagged as a follow-up, not silently absorbed into this commit's test count. WATCH MONDAY: `Gamma_FleetExecutor` already fires `fleet_live.py --live` every 3 min 09:30-15:55 ET and risky-3 already carries `live:true` — so Monday's open is the FIRST REAL test of a probe fill (paper account `PA31WIU8X15Q`), not a WATCH-only dry run, on a MUCH narrower target than the mission's original framing (one specific thin-evidence window gate, not "every cohort gate"). Glance at `gamma_glance.py`'s new `PROBE ARM` line through the day; a real probe fill will show `PROBE: risky-3 N/3 entries today, cohorts bull_1100_1200` and a `decisions.jsonl` row reason starting `PROBE_ARM cohort=bull_1100_1200`.

- 2026-07-10 ~21:15 ET [paper-autonomy fix, market CLOSED] **SHIPPED gate-provenance ordering fix — a stale trigger bar can no longer masquerade as a live gate block** (the headline bug in `markdown/audits/GATE-PROVENANCE-SWEEP-2026-07-10.md`). ROOT CAUSE (one sentence): `run_account()`'s post-verdict ladder in `setup/scripts/heartbeat_core.py` only ever re-checked `_stale_trigger_bar` when the raw engine_cli verdict was ALREADY `ENTER_BEAR`/`ENTER_BULL`, so a stale (prior-session) trigger bar that instead satisfied one of the 15 `GATE_ORDER` time-window gates (`evaluate_gates()` runs unconditionally INSIDE `_engine_verdict`'s `engine_cli` subprocess call, before this ladder ever executes) fell through to the ladder's `else: rec["action"] = v` branch and got logged under the GATE's own name instead of `SKIP_STALE_TRIGGER` — proven today via cross-account evidence: bold's 5x `SKIP_CONF_LVL_REC_AFTERNOON` 09:31-09:35 ET and safe's `SKIP_STALE_TRIGGER` at the SAME instants were the SAME phantom bar (`2026-07-09T15:55:00-04:00`), correctly diagnosed by safe (doesn't arm that gate) and misdiagnosed by bold (does).

  **SEAM** (smallest correct one, chosen after reading the real call order across `heartbeat_core.py` + `engine_cli.py` + `gates.py`): `setup/scripts/heartbeat_core.py:860` — hoisted `_stale_trigger_bar(payload, et)` to the FIRST check of `run_account`'s post-verdict ladder, unconditional on the raw verdict `v`. `gates.py`/`engine_cli.py` deliberately UNTOUCHED: `decide_payload`/`evaluate_gates` are PURE and SHARED with the backtest orchestrator (reused there as its parity-oracle assert-agree check) — staleness-vs-wall-clock has no backtest equivalent (a backtest bar legitimately IS "now" for its simulated tick), so threading it into the shared engine would risk backtest determinism for zero benefit; heartbeat_core.py's LIVE-only post-verdict ladder (already keyed off `_et_now()`) is the correct and only seam.

  **CAUGHT DURING VERIFICATION, disclosed not swept under:** the first version of this reorder made the new staleness check a hard short-circuit ahead of the WHOLE ladder, which accidentally also skipped the G4 extra-setup-dispatch block (it used to live inside the ladder's `else:` clause) — 2 real pre-existing tests (`test_g4_extra_setup_routing.py::test_structure_veto_blocks_extra_setup_route` + `::test_non_veto_hold_still_routes_extra_setup`) caught it RED immediately on the first verification pass. Fixed by decoupling G4 dispatch from the action-ladder entirely (line ~927) — now gated purely on `v not in ("ENTER_BEAR","ENTER_BULL")`, reproducing the pre-fix `else`-branch gating exactly, independent of what staleness relabels `rec["action"]` to. Opportunistic 1-line fix in the same comment block: corrected a pre-existing stale guard-pointer (`Guard: test_graduated_guards.py::test_structure_veto_blocks_extra_setup_route` — that test lives in `test_g4_extra_setup_routing.py`, not there; predates this session, left as found until now).

  **TESTS (all quoted, all green):** new `backtest/tests/test_gate_provenance_ordering_2026_07_10.py` **17/17** — RED-proofed: 8/17 FAILED against the pre-fix ladder (byte-accurate replay of today's real contaminated bold row from `core-decisions.jsonl:7954`, a 5-gate sweep across `GATE_ORDER`, a stale-bar HOLD case, a source-ordering structural pin, + the G4-interaction regression above), then all 8 flipped GREEN post-fix; the other 9 (fresh-bar vary-and-assert tape + the already-correct ENTER-on-stale case) were already green pre-fix, proving the fix is a no-op for every case that already worked. Full heartbeat+gates+engine_cli+structure_veto+G4 cluster (26 files, junit-verified): **574/574** (0 failures, 0 errors, 3 pre-existing STAGED-Wave-2 skips in `test_no_stale_blocks.py`, unrelated). Curated safety gate (`run_safety_gate.py`): **31/31 PASS**.

  **MONDAY'S TELEMETRY DIFFERENCE:** any prior-session trigger bar the engine reads at/near the open now ALWAYS logs `action: SKIP_STALE_TRIGGER` in `core-decisions.jsonl` (both accounts, whatever the raw verdict — any of the 15 `GATE_ORDER` names or HOLD), instead of sometimes reading a gate's own name — gate fire-counts in future census/provenance audits are trustworthy again for the open-tick window. KNOWN RESIDUAL (flagged not fixed here, separate spawned task): `backtest/tools/participation_cascade.py`'s own `classify_core_row()` derives gate attribution from `row["reason"]` (a field this fix never touches) BEFORE checking `action`, so its cascade counts will still misattribute a future stale-bar phantom until that follow-up lands.

  **REVOKE / REVERT:** `git revert` this commit — pure code-ordering, no params/config touched, self-contained to `setup/scripts/heartbeat_core.py` (+ the new test file); reverting restores the exact pre-fix ladder (the new suite's 8 RED-on-revert assertions prove it). No live-money/order-placement behavior changed — the `ENTER_*` → `_execute` path is byte-identical (proven by the fresh-bar tape), and `_execute`'s own belt-and-suspenders staleness recheck (line ~1100) is untouched. LOGGING/ATTRIBUTION-only fix.

- 2026-07-09 ~18:50 ET [visibility build, render-only] **SHIPPED structure-stop truth on every surface J looks at** — closes the STOP-B ship-1 known-cosmetic-gap ("plan-log 'stop' shows the −20% fallback even in structure mode") the night before SS-B's first live day. Zero decision-logic touched (`exit_manager.py` untouched, frozen); every edit is additive reporting or a corrected LOG-ONLY number (never sent to the broker). 5 surfaces:
  1. **Fleet exit_pass rows** (`exit_actuator.manage_tick`) now carry `stop_mode`/`trigger_level` on EVERY row (managed tick, FLAT_PRUNED, no-quote HOLD) + `last_closed_5m_close` on the managed row — additive keys only, `actions` computed before the new dict fields exist. New `exit_actuator.describe_stop()` pure formatter (`STRUCTURE@<level> (cat -50%)` / `<price> (<pct>)`).
  2. **Plan/placement log fix** (`fleet_live._place_live` + `heartbeat_core._execute`): when `register_entry` resolves STRUCTURE mode, `stop`/`premium_stop_pct` are corrected to the REAL catastrophe floor (entry_px-anchored, not the stale mid-anchored −20%/−50% fallback text) and new `stop_mode`/`trigger_level`/`stop_display` fields are added. Premium-mode positions are byte-identical to before. Known gap: the DRY/`WOULD_PLACE` shadow-preview branch in `_execute` (unarmed-mode only) still shows the old text — fixing it needs hoisting the trigger-level/shape resolution earlier in the function, deliberately not attempted tonight to keep the diff minimal on a frozen-adjacent surface; the REAL `dry=False` placed path (what fires tomorrow, `GAMMA_CORE_ARMED=1`) is fully fixed.
  3. **`automation/state/engine-contract.md`** — new `## 2b. Structure-stop (SS-B, v15.3 chart-stop-primary)` section (flag state per account, which strategies declare `stop_mode="structure"`, the catastrophe cap vs flag-off fallback, the resolution rule, instant de-arm). `_shape_str` now appends `mode STRUCTURE (cat -50%)` / `mode premium` to §2's table too. Regenerated via `engine_contract.py`; drift guard green (§ below).
  4. **Glance surfaces** (`gamma_status.py` + `gamma_glance.py`) — new line: `EXIT MODE: structure (SS-B) since 2026-07-09 [safe=ON bold=ON]; positions open under structure: N; last structure exit: <ts or none>` (currently 0/none — honest, expected before the first real fill under the flag).
  5. **Discord fill-ping** (`trade_today_watcher.py`) — `_structure_exit_label` extends the EXISTING composer (no new Discord path): an ENTRY fill reads the live exit-state ledger (`structure@<level> (armed)`); an EXIT fill falls back to the decision log's `exit_pass` history (exit-state.json is pruned the SAME tick a structure-stop closes a position, so the ledger alone would miss it).
  - **Opportunistic fix (in-scope file, zero logic risk):** `exit_actuator.py`'s own `sys.path.insert` used `parents[2]` instead of `parents[3]` (an off-by-one predating tonight — `et_clock` importable only by import-order luck from another file inserting the path first). Fixed so `test_exit_actuator.py` runs standalone; root-caused before fixing (diagnosed via reproduction: file failed alone, passed combined with `test_structure_stop_wiring.py`).
  - **TESTS (all quoted, all green):** `automation/state/fleet/` full dir 161/161 (was 157; +4 new `test_place_live_stop_display.py`, exit_actuator.py gained 6 new visibility tests in `test_exit_actuator.py`). `backtest/tests/test_execute_stop_display.py` 3/3 (new — proves the structure-mode correction + the isolated-setup/flag-off no-ops, using the REAL production `strategies.py` + a `register_entry` fake that resolves through the REAL frozen `exit_manager.ExitState.from_entry`). `backtest/tests/test_engine_contract_drift.py` 5/5 (regenerated card matches; red-proof anchor still discriminates). `backtest/tests/test_exit_mode_glance.py` 5/5 (new). `backtest/tests/test_gamma_glance_guard.py` 3/3 (ASCII-safety intact). `backtest/tests/test_trade_today_watcher.py` 10/10 (was 4; +6 new). Regression sweep of every file with a `register_entry` mock that could plausibly reach the edited registration blocks — `test_trade_to_learn_2026_07_01.py`, `test_money_path_2026_07_01.py`, `test_audit_fix_heartbeat.py`, `test_min_entry_premium_floor.py`, `test_tz_quality_lock_2026_07_02.py`, `test_wire_bollinger_squeeze.py`, `test_trigger_level_exact_provenance.py` — 121/121 (every existing `res["stop"]==0.80/0.94/0.50`-style pin untouched, traced field-by-field before editing). Curated safety gate: **PASS** (31 + 5 suites green). VARY-AND-ASSERT (render-only proof, the mission's explicit ask): `test_exit_actuator.py::test_visibility_fields_are_additive_actions_unchanged` cross-checks the actuator's emitted actions against an INDEPENDENT direct call to the untouched `exit_manager.plan_exit_actions` on the same inputs — identical. `test_place_live_stop_display.py`/`test_execute_stop_display.py` assert the ONE broker POST carries no stop/tp key either way.
  - **UNVERIFIED, disclosed not hidden (OP-33):** a full non-slow sweep of all 2628 `backtest/tests` (not the curated gate) showed exactly one `F` around the 40-50% mark before I killed the run (2+ hrs wall-clock on this heavily-loaded always-on box — a full sweep is NOT how this project verifies itself, per `run_safety_gate.py`'s own curated-vs-full split). Bisected the likely zone (`test_graduated_guards.py` — the doc-flagged "validates mutable LIVE runtime state" file — 71/71 clean; all 16 `test_g*.py` files — 272/272 clean) without reproducing it; did not find it. Flagging as an open, UNCONFIRMED item rather than claiming the full suite is green — nothing in the bisected zone touches a file this build edited.
  - **REVERT:** each of the 5 surfaces is independently revertible (git revert the touched file); nothing here is load-bearing for tomorrow's SS-B first live day — reverting removes VISIBILITY, not the SS-B exit behavior itself (that stays governed by `structure_stop_enabled` per the ship-1 entry above).

---

- 2026-07-09 ~16:20 ET [STOP-B ship 1, Fable] **SHIPPED SS-B STRUCTURE-STOP for ribbon_ride, BOTH exit lanes, flag-ON** (`structure_stop_enabled=true`, Safe + aggressive params) — v15.3 chart-stop-primary finally implemented: exit on first 5m SPY CLOSE through the entry trigger level (side-aware), −50% intrabar catastrophe cap, TP1 +100% sell 66%, trailing 15% runner, tgt-none. EVIDENCE: `analysis/recommendations/structure-stop-2026-07-09.json` — SS-B = the ONLY candidate this week passing BOTH pre-registered layers (fresh-slice −$47.34/tr vs control −$100.67; 79-real-fills anchor −$604.70 vs −$757.10; today's 07-09 exhibit +$138.50 vs actual −$381, exhibit-only). Wire built in an isolated worktree, applied post-close, end-to-end verified on LIVE files (flag ON → stop_mode=structure/trigger threaded/cat −0.5/tp1 1.0; flag OFF → premium). Fleet suite 136/136 (6 old-cell pins re-pinned to SS-B), reconciliation+time-stop guards 7/7, safety gate PASS. WAIVER: structure stops sit OUTSIDE the premium-grind P5 universe → J-directive waiver (J 07-09: "1 call hold... get this all built"). FORWARD KILL-CHECKS: (a) fresh P5 grind (running, ~5.9k/7,560) → too-good audit on its 216 P4 survivors, (b) 2-week paper watch, (c) trigger-level recovery is a proximity heuristic — no-nearby-level positions fail OPEN to premium mode (61-78% recovery in study, disclosed). HONEST: SS-B = "bleed less + hold through noise," both layers still net-negative — ribbon_ride recency COLD (1/18 fresh winners), sizing/recency question OPEN. REVERT: instant de-arm = `structure_stop_enabled:false` both params (new entries → −20% premium + quick TP1 fallback); full = git revert the STOP-B commit. Known cosmetic: plan-log "stop" shows the −20% fallback even in structure mode (display only).
- 2026-07-09 01:52 ET [overnight-drive W1 wire] SHIPPED entry-1 premium floor $0.30 engine-wide BOTH lanes (commit f8978fb) — evidence: T3 n=157 + real-fills anchor −$72.50 vs −$757.10 (floor refused the toxic sub-$0.20 cohort); guard 11-passed + red-proofed (3 rejection tests RED with enforcement stashed) — REVERT: set min_entry_premium: 0 in params.json + aggressive/params.json (or delete key); optionally git revert f8978fb; rejection tests REDing confirms off.
- 2026-07-09 01:52 ET [overnight-drive W1 wire] SHIPPED vwap_continuation fleet-shape port to the FULL validated core cell −0.06/+0.40/0.8/fixed (commit b125055) — evidence: 07-07 all-5-OP-22-gates-PASS scorecard + T-W6 provenance, waiver j_signed per J directive, two-lane drift closed, fleet 101-passed + p5 gate red-proofed, stale trade_to_learn pins fixed (clears 2 of known-15) — REVERT: restore old ExitShape literal (−0.08/0.3/0.667/trailing) + prior waiver block (parent of b125055) + revert test pins.
- 2026-07-09 01:52 ET [overnight-drive W1 wire] SHIPPED fleet time_stop_et threading (D2 #5, commit 1f3629d) — evidence: fleet arms time-stopped at hardcoded 15:50 vs params 15:40 (dead knob, C14 class); guard red-proofed (kwarg dropped → time_stop_et=None FAIL) — REVERT: drop the time_stop_et kwarg from fleet_live.run()'s ea.manage_tick call + delete test_fleet_time_stop_threaded.py.
- 2026-07-09 01:52 ET [overnight-drive W1 wire] SHIPPED engine-contract card regen: min_entry_premium on §3b + vwap two-lane parity visible (commit 7adebaf) — evidence: drift guard 5-passed; card renders the floor FROM params (params edit w/o regen trips the guard) — REVERT: git revert 7adebaf (generator+card together) + regen + drift guard.
- 2026-07-09 01:32 ET [overnight-drive W1b] SHIPPED EOD-flatten non-LLM backstop (Gamma_EodFlattenCore 15:52 ET) + preopen gate now reads REAL exit codes — root cause: LLM flatten died on $1 budget cap + Task Scheduler masked it. Evidence: both `Gamma_EodFlatten`/`_Aggressive` real logs showed `=== END tick exit=1 ===` 2026-07-08 while `Get-ScheduledTaskInfo` reported `LastTaskResult: 0` (wscript fire-and-forget masking). Registered `Gamma_EodFlattenCore` (pure-Python `eod_flatten.py`, safe-2+bold-2, one fire, no LLM); smoke-fired via `Start-ScheduledTask`, real log confirmed `EOD_FLATTEN_COMPLETE outcomes=['NOOP', 'NOOP']`. LLM tasks left registered untouched (defense-in-depth). `preopen_readiness.py` no longer trusts `LastTaskResult` for any of the 3 flatten tasks — new `assess_eod_flatten_reality()` reads each one's real log/jsonl tail (42/42 preopen_readiness + 12/12 eod_flatten guards green; safety gate green). REVERT: `Unregister-ScheduledTask -TaskName "Gamma_EodFlattenCore" -Confirm:$false`; `git revert` the preopen_readiness.py + SCHEDULED-TASKS.md commit; the LLM tasks were never touched so nothing else to restore.
- 2026-07-09 00:20 ET [FABLE REVIEW of CONFIRM-AND-WIRE] Execution CONFIRMED sound; 4 corrections shipped: (1) engine-contract card §3c read UNTRACKED entry-shadow.jsonl -> fresh-clone CI drift RED — card now renders committed-source facts only (drift guard 5/5); (2) grid lacked stop -35 = exit-C's exact stop — added to STOPS + phase5 STOP_VALS, grind restarted on 7560 combos (resume kept all 324 done, probe PASS); (3) funnel/phase5 no-shard glob hole fixed; (4) T-W6 rec sharpened (C29: validated cell = the FULL core shape −0.06/+0.40/0.8/fixed/ATM; naive 2-field sync to the fleet's 0.667/trailing shape = untested 3rd combo). GUIDANCE findings: grind "trailing" ≠ exit_manager "trailing" (simulator profit-lock is whole-position, arms at first uptick w/ BE anchor at threshold=0 — verified simulator_real.py L540-584/L644) so T-W7 layer-(c) judges FULL combos not ShapeSig and treats trailing P5-membership as approximate; T-W5 parity is sim-vs-sim on real timestamps (forward live shadow not scheduled). WATCH: grind ETA lands ~09:00-11:00 ET INTO RTH — if ticks slow, Stop-Process the mass_grind pythons (resume-safe) + relaunch after 16:00. Addendum: markdown/planning/CONFIRM-AND-WIRE-REPORT-2026-07-08.md
- 2026-07-08 23:50 ET [CONFIRM-AND-WIRE] T-W1..T-W6 DONE, T-W7/STOP-B correctly NOT started (STOP-A unsigned). T-W2: fixed the profit_lock_mode/trail_pct dead knob at strategy_space_grind.run_cell (explicit kwargs) instead of _params_to_kwargs — the literal handoff text would have violated the L156 guard (test_profit_lock_not_in_baseline.py), the SAME misdiagnosis class STATUS already killed once (2026-07-02 ~03:55 entry below). Red-proofed. T-W3: v2 grind (6720 combos, real trail_pct{0.15,0.22}+time-exit axes) code-verified + LAUNCHED in background (12 workers + funnel), running for hours — not claimed complete. T-W4 per_band_stop.py + T-W5 entry_manager.py + shadow ledger (98 real entries/8 sessions, fill-rate 85.9% vs T3 backtest 77.6% — sim-live parity PASS) shipped shadow-only, red-proofed. T-W6: vwap two-lane answered (-0.06/+0.40 is validated; -0.08/+0.30 in strategies.py is stale — git-confirmed single-commit provenance), J-decision queued. Engine-contract card §3c extended (drift guard green). Full report: markdown/planning/CONFIRM-AND-WIRE-REPORT-2026-07-08.md
- 2026-07-08 09:44 ET [vision-loop] V4 DONE (KILL): rejection->continuation ENTRY killed by measurement (all 4 rejection variants incl. selective FAILED; nail=premium bleed C3). DETECT ships via V1c. **ENGINE-VISION BUILD COMPLETE (V0-V4+Vtrade).** HONEST: engine HOLDing 28 ticks on a real -3.8pt dump — F1-off wasn't sufficient, entry frontier remains.
- 2026-07-08 09:40 ET [vision-loop] V3 DONE (shadow): trendlines-live.json + Gamma_Trendlines (5min RTH) — engine can SEE J's trendlines. Entry-wire NEEDS-REVIEW. Engine live: 12+ ticks all HOLD (bearish-aligned), 0 fills.
- 2026-07-08 09:31 ET [vision-loop] Vtrade DONE (OP-33e): Gamma_TradeToday auto-pings J on the first engine fill (Alpaca source-of-truth) + trade-today.json glanceable. Verified firing. Market open; engine live (F1 off, gap_and_go alive). Currently 0 fills / 2 placed-not-filled.
- 2026-07-08 09:22 ET [vision-loop] V2 DONE: gap_and_go un-dead (was 100% SKIP_NO_FEED) — prior RTH close 751.31 now derived from bars + gap-magnet level written. Engine can evaluate gap setups today. 3 red-proofed guards, fail-open.
- 2026-07-08 09:12 ET [vision-loop] V1c DONE: engine now PINGS J on a memory-level rejection (verified on 747.41 — J's level). Auto-live via the 10-min task, 30-min dedup, notify-only. V1-entry (merge into live entries) -> NEEDS-REVIEW (=G11 A/B). Next V2 gap-fill.
- 2026-07-08 09:01 ET [vision-loop] V1b DONE+VERIFIED: Gamma_LevelMemory scheduled (every 10min RTH) — triggered, shadow map refreshed (exit 0). Multi-day memory levels now auto-update live.
- 2026-07-08 08:56 ET [vision-loop] V1 producer DONE: multi-day level-memory shadow producer built+guarded+committed — captures J's exact reads (747.41/746.7/745.88). Shadow-only (entry-wire A/B NEEDS-REVIEW). Follow-ups: schedule refresh + wire G5-alert/dashboard consumers.
- 2026-07-08 08:44 ET [vision-loop] V0 DONE: F1 ribbon-momentum gate DISABLED (0->null) — A/B confirmed it was removing a +$585 cohort of big-down-day puts (J's edge). Engine unblocked for the 09:30 open. Guard red-proofed, REVOKE=positive threshold+OOS.
- 2026-07-08 00:30 ET [overnight-loop] G6 DONE (KILL): weekly-put hold-to-Friday fails null (p>0.05 @ 3-4DTE) + gap-bleed -$4-6K + doesn't hold. GAP-AUDIT COMPLETE (10 shipped+guarded, G4/G11 review-blocked, G13/G6 analysis). Loop stopping.
- 2026-07-08 00:27 ET [overnight-loop] G4 review packet COMPLETE (replay: 3/4 arms clean, risky-1 +1 extra @ bar 1801, parity 98.1% — one dedup fix from arm-ready). G6 weekly-put multi-day-hold sim RUNNING (_dte34_multiday_hold_sim.py, OPRA single-process). Last gap-audit item.
- 2026-07-08 00:16 ET [overnight-loop] G4 + G11 -> BLOCKED-NEEDS-REVIEW (both entry-path; specs in markdown/audits/G4-FLEET-DIVERGENCE-SPEC.md + G11-LEVEL-MEMORY-PRODUCER-SPEC.md — J nod + supervised A/B). G13 delegated to treasurer agent (real Alpaca equity + reconcile the 0-fills-vs-drawdown puzzle). G6 weekly battery pending (waits for OPRA). Ultracode ON -> G6 + capstone will be workflow-driven.
- 2026-07-08 01:44 ET [overnight-loop] G12 DONE: htf_15m morning suppression measured — contradicts realized trend 35%, ~16 near-threshold bear suppressions (marginal). Verdict real-but-not-costly, no fix (per measure-first). Confirmed SKIP_RIBBON_MOMENTUM_GATE (F1) fired 29x live.
- 2026-07-08 01:38 ET [overnight-loop] G10 DONE (recovered): read the truncated audit tail off disk (27 findings, no re-run). NEW CRITICAL F1: min_ribbon_momentum_cents=0 silently ARMS a 'disabled' ribbon-momentum gate on Safe (0 != None) -> blocks entries on contracting ribbon. Queued for A/B (entry-path). 6 new backlog items.
- 2026-07-08 01:30 ET [overnight-loop] G5 DONE (327479e): alert/capture flywheel. FIX: discord-bridge was dropping 113 `message`-schema alerts (spend WARN + self-check DEGRADED — J wasn't getting them); now delivers both schemas. + level_memory reject-ping + j-call anchor capture. 6 red-proofed tests.
- 2026-07-08 01:20 ET [overnight-loop] G17 DONE (8c672c0): autonomy_actuator ET/market-hours deduped onto et_clock (C14 verbatim-copy eliminated), parity verified, guard red-proofed.
- 2026-07-08 01:15 ET [overnight-loop] G15 DONE (dd84573): stale vwap_cont docs fixed (were 'DORMANT' while LIVE-armed) + doc/flag drift guard; queue.md consolidated (25 done->Completed); SIP price = $99/mo (Algo Trader Plus) handed to J for D-SIP.
- 2026-07-08 01:05 ET [overnight-loop] G9 DONE (412ec93): sim-live parity ledger shipped. FINDING: 0 reconciled fills across core + 6 fleet arms (filled_avg_price null everywhere) — rig places but has never filled. Now standing-monitored via analysis/parity/. 4 red-proofed tests.
- 2026-07-08 00:58 ET [overnight-loop] G8 DONE (addb959): engine now logs per-entry greeks/IV (delta/gamma/theta/vega/rho+IV) to core-decisions.jsonl — log-only, fail-open (never slows a fill), 6 red-proofed tests. UNVERIFIED: live snapshot URL confirms on first real fill.
- 2026-07-08 00:45 ET [overnight-loop] G7 DONE (d553fe5): armability gate — promote scorecards now disclose min-lot affordability per account (Safe floor <=$2.00/contract, Bold <=$2.78). 9 red-proofed tests, gate PASS.
- 2026-07-08 00:33 ET [overnight-loop] G16 DONE (54ce9b6): et_clock.py now runnable (`python et_clock.py` -> ET + market_hours) + is_market_hours() gate; 2 red-proofed guards, safety gate PASS. Queued G17 (autonomy_actuator ET dedup).
## [2026-07-07 ~22:45 ET] OPUS — Tier-1 gap-audit execution COMPLETE (before-open safety)

> **G1 DONE (commit 55fd164):** adopted manual positions are now CAP-ONLY per D2 -- shape tp1_qty_fraction 0.0 (no TP1 -> no chandelier) + ribbon-flip excluded for strategy 'adopted_manual' + Discord ping on adoption. So a J-manual put can NO LONGER be auto-sold at a TP1 he never chose; only the -50% cap + 15:50 flatten manage it. Guard TestAdoptedShapeCapOnly (3 tests, both directions red-proofed). Curated safety gate green.
> **G2 DONE (verify-only):** the gap-audit assumed the live tick runs under backtest/.venv -- WRONG. run-heartbeat-core.ps1:24-36 launches SYSTEM pythonw with PYTHONPATH=backtest/.venv/Lib/site-packages (L41: venv pythonw re-execs a new console -> window flash). Verified heartbeat_core + exit_actuator + my edits import CLEAN under that faithful env (pandas 2.3.3). Import-dead-at-open retired. FUTURE VERIFICATION NOTE: test under system-python+venv-PYTHONPATH, not bare venv, to be production-faithful.
> **G3 DONE (commit fc8ee27):** today's runners auto-liquidated 15:45 ET (Alpaca 0DTE auto_liquidate; both accounts confirmed FLAT). Safe 747P runner -$13, Bold 750P runner +$125. **DAY TOTAL = +$489 realized** (Safe +$162 / Bold +$327) -- corrects the +$377 (TP1-only) reported all evening. Journal EOD written. Minor flag: a $0.01 SPY 07-08 710P + a $10 BTC round-trip appear ~20:45 ET post-session (canceled/tiny, source unclear) -- flagged for provenance.
> NEXT (Opus, per FABLE gap-audit order): G10 audit-tail recovery, then G5 alert/capture, G8 greeks-capture, G9 parity-ledger, G7 armability-gate.

---

## [2026-07-07 ~21:45 ET] FABLE DECISION MEMO — 7 open judgment calls CLOSED (companion to the gap audit)

> **Full memo: `markdown/audits/FABLE-DECISIONS-2026-07-07.md`.** D1 FREEZE new options-entry batteries ~30d (axis exhausted + OOS burned; effort -> fleet/alert/greeks/parity/futures; exceptions: J's-exact-weekly-spec battery + log-analysis). D2 adopted manual positions = CAP-ONLY + flatten + Discord ping (never impose TP1/chandelier on J's trade; guard it). D3 vwap -0.06/0.40 pre-registered REVOKE trigger: realized expectancy < $0 after 15 live fills -> revert (fill-funnel owns the counter). D7 fleet 6-arm profiles pre-designed (2 controls + one-gate-away + 2DTE-forward $10K + scalp-shape + J-mirror), explicitly inside J's arms-are-RISK-PROFILES-not-strategies rule. **J one-word ratifications owed: D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: yes); D5 min-1 contract for single-exit shapes, min-3 stays for split shapes (his Rule 6); D6 activate G7 EOD-flatten backstop (rec: yes).** Tomorrow-morning watch order included. Nothing left waiting on Fable.

---

## [2026-07-07 ~21:30 ET] FABLE GAP AUDIT — the unknown-unknowns handoff (J at 95% Fable; Opus executes)

> **Full doc: `markdown/audits/FABLE-GAP-AUDIT-2026-07-07.md`** — 15 gaps ranked by trading impact + 3 reframes + execution order. Headlines: (R1) the 2026 OOS window is BURNED (~130 configs read it tonight; forward paper fills = the only virgin holdout; the FLEET is the unused forward-validation farm); (R2) tonight's code meets its first live open tomorrow — G1 adoption-exit-shape is UNSPECIFIED (pin + ping before 09:30), G2 dress-tick under the production interpreter, G3 today's runner exits never verified/journaled; (R3) stop running batteries at J's discretionary edge — build DETECT->ALERT->CAPTURE (the J-call flywheel) instead. Dropped J-directives to build: fleet divergence keystone (G4), alert loop (G5), J's EXACT weekly spec (OTM + underlying-level stop + hold-to-Friday) never actually tested (G6, cache now exists). Cheap compounding instruments: armability gate (G7), live greeks capture (G8), sim-vs-live fill parity ledger (G9), recover the 6 truncated audit findings via resumeFromRunId wf_a6e5356c-0e7 (G10). J-decisions: futures provisioning 5WW73759, Safe-2 equity reset policy (down ~32% in 3wk — sizing doom-loop), paid SIP (~$99/mo, verify).

---

## [2026-07-07 ~21:00 ET] CORRECTION to the evening entry: the "DTE win" is a HOLD, not a shipped edge

> **Verify-don't-claim (OP-33):** the evening entry called DTE "real and validated, +82% OOS, the night's headline." That was OVERCLAIMED — it was the RESEARCH cell (ITM2) without the full OP-22 gate / recency / sizing. Validated on the LIVE ATM Safe-2 cell (vwapcont-dte-atm-ab.json): VERDICT **HOLD** — WF 0.556 (<0.70), loses vs 0DTE in 4/4 most-recent months (2026-03..06), null p=0.065 (concentration in 2025Q4/2026Q1, not regime-robust), AND 2DTE ATM premium 2.33x -> 1.6 lots at the $600 budget < min-3-lot floor (hard Rule-6 blocker at $2K). The DTE *effect* is real (0DTE theta trap is real) but it is NOT a shippable/sizeable edge on the live cell now. Change is STAGED (j_vwap_cont_dte_override + picker patch + guard, in strategy/candidates/2026-07-07-204650-vwapcont-dte-override.md) -> re-opens if a later run re-clears all 6 gates (regime turn / higher equity for 3 lots). Lesson: fable-too-good — scaled confidence with the exciting number instead of suspicion.
> **The night's REAL shipped wins stand:** 75f3a0c vwap exit (+$8.64/tr OOS validated), 35de43f 5 audit fixes, 5d84a5e futures engine (dry-run green, 1 broker-setting from live). Dynamic stops = STATIC-IS-FINE (dynamic-stop-ab.json; burden now on a real greeks feed). J action: provision futures on Tastytrade 5WW73759.

---

## [2026-07-07 EVENING] interactive (J + Gamma) marathon — DTE LEVER FOUND (+82% OOS), 5 audit fixes + vwap exit SHIPPED, edge SHAPE diagnosed

> **Signal J wakes to:** the night's headline is real and validated — **DTE is a monotone edge lever**: same signal 0DTE $36 -> 1DTE $59 -> 2DTE **$66 OOS/tr** (null-crushed, drop-top3 healthy). "Options die to theta" was a **0DTE artifact** (J was right). True 3-4 DTE multi-day-hold test RUNNING (backfill ~40min) — answers whether holding across days pays more or gaps out.
> - **SHIPPED (committed, guarded, revert-able):** `75f3a0c` vwap_continuation exit -0.08/0.30 -> -0.06/0.40 (+$8.64/tr OOS, all OP-22 gates) + `e0160b1` guard-pin fix; `35de43f` 5 AUDIT FIXES (manual-lockout adopted-not-frozen, expired-levels dropped, fill-reconcile poll, funnel false-RED, time_stop dead-knob wired) — each red-proofed, adversarial review OVERALL SHIP, full regression gate green.
> - **LIVE:** J called the 07-07 dump, Gamma executed manual paper puts -> +$377 (Safe 5x747P +$175, Bold 3x750P +$202). Engine generated 18 ENTER_BEAR but NOT_FLAT behind the manual position (the lockout — now fixed).
> - **KILLED (evidence):** ribbon-rejection as a 0DTE entry (6 configs) — RE-OPENED on the DTE axis; confluence (additive/structural/multi-lens all die — adding lenses overfits); "multi-TF=bigger move" REFUTED (predicts SMALLER, corr -0.27); volume-profile 0DTE data-blocked (needs paid SIP).
> - **DIAGNOSED:** J's edge = TREND/REGIME direction, timed at levels, needs DAYS + right DTE (levels=where, regime=why; order-book-mechanical per the literature, not folklore). His winning PUTs were at levels a mechanical engine reads as SUPPORT -> he trades regime, not local level-role.
> - **BUILT:** GENERATIVE-LENS discipline (enumerate market-structure levers before writing "dead") + markdown/trading-knowledge/ base (Greeks/structures, DTE/IV, market-structure) + param_provenance.py (133 params: 23 validated / 93 bare) + level_memory.py perception layer.
> - **QUEUED (evidence-pointed):** (1) true 3-4 DTE multi-day hold [RUNNING]; (2) regime-prior x multi-day options; (3) fleet-divergence (each arm independent + own DTE/exit profile — keystone: build_shared_signal ties all arms to Safe ENTER -> inert when Safe HOLDs); (4) XSP/SPX for multi-day holds (cash-settled, no assignment, 60/40 tax).
> - **REVOKE:** git revert 35de43f / 75f3a0c. Scorecards: multiday-dte-compare / vwapcont-exit-ab-ship-gate / confluence-matrix / ribbon-rejection-{exitgrid,hold,selective,spread}.json.

---

﻿## [2026-07-06 ~10:05 ET] interactive (J + Gamma): full system re-verify + fresh premarket chart cross-check — MCP reconnected, engine GREEN, opening-30-min price action read

> J returned ~30 min post-open to prep for the day. Re-verified everything the 09:52 premarket run flagged, from a second independent source: (1) **Alpaca MCP (both accounts) + TradingView MCP all reconnected** and round-tripped clean this session (`get_clock`/`get_account_info`/`get_all_positions` both accounts, `tv_health_check`) — the 09:52 `MCP_UNRESPONSIVE_REST_FALLBACK` was session-scoped, not a standing outage. Alpaca clock: `is_open=true`, `timestamp=2026-07-06T10:03:34-04:00` (next_open tomorrow — no holiday weirdness). (2) `engine-health.json` cross-checked directly: both heartbeats ticking 1/min, both accounts flat (confirmed via live `get_all_positions`, not just REST), kill-switches armed, level feed 2.8m fresh. Equity matches exactly: Safe $1,425.11 / Bold $1,636.27. (3) Fresh TV chart read confirms the bullish bias 13 min later: ribbon still BULL-stacked (fast 748.55 > pivot 748.36 > slow 748.28). (4) **New since premarket:** SPY spiked to 749.52 in the 09:30-09:35 volume surge, tagging just above the 749.42/749.53 resistance band, then rejected back to the 748.3 pivot/50-SMA area where it's now consolidating — the day's first real test of the key level already happened and faded.
> **Unchanged / still open:** recency-confirmation RED-blocks Safe2_ATM *live-capital* scaling (paper unaffected, per J's 07-01 TRADE-TO-LEARN ruling); macro calendar stale 22 days, Sunday weekly-review silently failing 3+ weeks (flagged for follow-up); overnight Conductor/Drive/ManagerOverseer quiet 4 straight nights, consistent with 07-02 token-saving mode still in effect (no commits or STATUS entries since Fri 07-03 12:01 either way — nothing broke, nothing new shipped over the weekend); `today-bias.json`'s `key_levels.ema_fast/pivot/slow` fields (746.66/745.69/744.47) are stale/mismatched vs the live ribbon — cosmetic, the bias prose + fresh TV read agree with each other, just that structured sub-block lags.
> No code/params changed this session — read-only verification + one live chart pull.

---

## [2026-07-06 09:52 ET] premarket: OK — bullish bias seeded, both accounts flat, ALPACA MCP DOWN (REST fallback used)

> **Known broken:** (1) Alpaca MCP servers (`alpaca`, `alpaca_aggressive`) unresponsive this session — ToolSearch returned no tools after repeated retries. Fell back to direct REST via `.mcp.json` keys for clock/account/positions (confirmed both accounts flat, market open, Safe equity $1425.11, Bold equity $1636.27). Heartbeat should verify MCP connectivity independently before first tick — if still down, it has its own REST fallback per CLAUDE.md tech-stack row. (2) `daytrade_count` field absent from both Alpaca REST account responses — wrote `day_trades_used_5d=0` (permissive default) to both circuit-breaker files. (3) Crypto harness DEGRADED: `v53_setup_dispatch.live` failing (103/104 stages pass) — yellow flag only, not trading-blocking. (4) Macro calendar STALE 22 days (last refresh 2026-06-14, threshold 7) — no confirmed events today, Sunday weekly-review has silently failed for 3+ weeks running.
> Bias: bullish (moderate) — SPY 748.55 pinned between 747.46 support / 749.42 resistance, ribbon BULL tight (17c spread), VIX 16.32 MID (bull-eligible). Both kill-switches re-armed on fresh live equity. Chart wipe/redraw deferred to first heartbeat tick (cost discipline — key-levels.json already current via 5-min intraday refresh).

---

## [2026-07-04T18:31 ET] MCP_AUDIT_YELLOW: Alpaca Safe/Bold healthy, TradingView required relaunch after weekend idle, all operational

---

## [2026-07-02 ~07:53 ET] conductor: OK -- CLOSED THE 4-DAY-OLD OPEN J DECISION cd-2026-06-29-001 (TP1/PROFIT-LOCK REVERT) → KEEP, ZERO PARAMS CHANGE. Adjudicated on evidence, not deferred to J another day; ships nothing to the trading path right before today's first-ever clean money-path proof. No commit (state-only: proposal shelved + queue + lesson).

> **Signal J wakes to (OP-33 verify-don't-claim + close-a-loop > artifact): the standing OPEN decision that has cluttered every STATUS for 4 days is RESOLVED — the 06-28 auto-applied `tp1_qty_fraction 0.8` + `v15_profit_lock_mode fixed` STAY (KEEP), grounded in the actual scorecard + the actual live-code behavior, with zero perturbation before the proof.** After-hours conductor fire, market CLOSED (Thu 07:53 ET, premarket; engine-health **GREEN** — both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat, reds:[]; self-check **GREEN**, problems:[] → FUNCTION-first satisfied, no funnel BROKEN; last trading day 07-01 calendar-gated on TODAY's real tape). No `### BROKEN:` flags. Self-audit tail DONE-marked through 07-01T17:33. task_scorer #1 of the 6-way HIGH tie = ADJUDICATE (a genuine loop-CLOSER on 4-day standing debt) — picked it over the FUNCTION-path needle-mover PROMOTER-WRITES-LIVE-KEY *because* it's premarket right before the first-ever clean money-path proof and the right move is to NOT touch the arm/trading surface now (ADJUDICATE ships zero trading-path change; PROMOTER edits the arm-key wiring).
> - **DIAGNOSED before deciding (OP-33, every claim from source):** the proposal (written 06-30 under the OLD propose-only rail) framed the 06-28 change as a "recency-RED CONFIRM-BEFORE-CAPITAL bypass = revert candidate." Read the source: (1) the change came from **pk-2026-06-28-001**, whose scorecard = **CLEARED / eval_bar_cleared=true** (WF 3.566, OOS +$56.86/tr, anchor 1692) → it PASSED the full 4-gate auto-ratify eval; only the *recency* gate was skipped (the bug cb82456 later fixed). (2) **J's own 07-01 TRADE-TO-LEARN grant made recency LIVE-money-ONLY** — these are PAPER accounts, so the "capital bypass" premise is *superseded by J's newer ruling*; the passed eval gate IS the paper bar. (3) `tp1_qty_fraction=0.8` is live-read correctly (`heartbeat_core:1054`, correct key) + doctrine-documented (CLAUDE.md:28, pk-2026-06-28-001). (4) `v15_profit_lock_mode=fixed` is a **DEAD KNOB in live core** — BOTH exit branches force "fixed": L1055 hardcodes it on the primary TRADE-TO-LEARN per-setup path, L1068 fallback reads the **un-prefixed** `profit_lock_mode` (params key is `v15_profit_lock_mode` → absent → default "fixed"). Reverting to "trailing" = **ZERO live effect**.
> - **DECISION = KEEP (shelved the revert), ZERO params change** — validated (scorecard CLEARED) + doctrine-documented (tp1) + behaviorally-inert (profit_lock) + no perturbation before the proof. Proposal `cd-2026-06-29-001` status pending→**shelved** with the full evidence resolution + `resolved_at`. Autonomous-safe: KEEP-status-quo is the null action (changes nothing live); J REVOKE surface = near-inert, trivially re-openable if he prefers revert. Deliberately did NOT do the "shelve=update CLAUDE.md to FIXED" half the proposal offered — CLAUDE.md is rail-4 propose-only → queued CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE instead.
> - **LEARN (4.5):** the dead-knob has a real blind-spot — `v15_profit_lock_mode` PASSES tonight's own just-shipped reconciliation guard (95a603b) because `promote_keeper.py:130` reads it, but that is a READ-TO-MUTATE (writer) reference, not a behavior-path consumer → a behaviorally-dead knob evades the ratchet. Lesson-inbox `2026-07-02-read-to-mutate-consumer-masks-dead-knob.md` + queued fix RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT (LOW). Corollary to C14/L156/L197: a string reference ≠ a behavior dependency.
> - **VALIDATED ($0):** no code/params change → no test run needed; state edits only (proposal JSONL, queue.md, lesson-inbox .md). Confirmed live params UNCHANGED (`tp1_qty_fraction`=0.8, `v15_profit_lock_mode`=fixed both intact). Evidence reads: pk-2026-06-28-001 scorecard verdict=CLEARED; heartbeat_core:1054/1055/1068 quoted; promote_keeper:130 quoted.
> - **REVERT:** state-only, no commit — re-open the proposal by flipping its `status` back to `pending` (or J reacts on Discord). Live behavior untouched either way.
> - **NEXT FIRE picks up:** the Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops that are the RIGHT post-proof FUNCTION-path work — **PROMOTER-WRITES-LIVE-KEY** (research→arm bridge, audit break #2), **SCHEDULED-OOS-CHECK-FOR-PROMOTE-PROPOSALS** (register the eval-clear schedule), **SINGLE-STRATEGY-REGISTRY-DESIGN** (bigger). NEW LOW residuals queued: CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE (propose-only) + RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT. **The only remaining money-path PROOF is TODAY's (2026-07-02) real tape** — the first engine-originated core fill via the simple-first path (self_check/fill_funnel auto-report it during RTH). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions now cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate) — cd-2026-06-29-001 is now CLOSED.
> - Files: `automation/state/conductor-proposals.jsonl` (cd-2026-06-29-001 pending→shelved + resolution), `automation/overnight/queue.md` (ADJUDICATE→done + 2 follow-ups queued), `strategy/candidates/_lesson-inbox/2026-07-02-read-to-mutate-consumer-masks-dead-knob.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~05:56 ET] conductor: OK -- SHIPPED THE GENERAL FORM OF THE DEAD-KNOB CLASS: a BROAD params<->consumer reconciliation ratchet that REDs on ANY ratified-but-unread params key. Measured the real gap: 24 of 114 ratified knobs have ZERO live reader (audit break #7's whole class, one of which -- entry_no_trade_after_et -- caused 10 PLACE_FAIL late ENTER_BEARs on 07-01). Commit 95a603b.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION-adjacent): the C14 dead-knob class is now GUARDED at build time, not audited by hand. A newly-ratified-but-unwired params key can no longer sit silent and mis-steer the money path -- it REDs LOUD.** After-hours conductor fire, market CLOSED (Thu 05:56 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check **GREEN**, problems:[] -> FUNCTION-first satisfied, no funnel BROKEN; last trading day calendar-gated on 07-02's real tape). task_scorer had 8 HIGH items tied at 6.0 -> picked PARAMS-CONSUMER-RECONCILE-TEST: the last ~5 fires' persistent signal was "trend regressing on small loop-closers, prefer a genuine needle-mover," the 03:55 fire EXPLICITLY named it "the RIGHT general form of tonight's finding," and it's the structural fix for the whole C14 class rather than one knob.
> - **DIAGNOSED before building (OP-33, every number measured):** the EXISTING coverage (`test_params_filters_drift.py` + v25 presence guard) reconciles ONLY the gate family (`block_*`/`*_gate`/`*_min`/`*_hard_cap`/`*_required`) vs the HEARTBEAT PROSE -- its docstring even concludes "no clean NEW hard parity to add," reading as if params<->consumer were fully covered. It is NOT: a broad word-boundary scan of the live consumer surface (code+prompts+installers, excluding the archived `analysis/backtests/*/metadata.json` param snapshots which are copies-not-consumers) found **24 of 114 ratified knobs with ZERO reader** -- exit flags, sizing tiers, entry-window, 5 liquidity thresholds, 4 macro-bias-v2 knobs, 6 session-timing, 4 resilience-harness. Whole-repo cross-check confirmed the only refs are archived snapshots + CHANGELOG (docs) -> genuinely orphaned, not read via a translated name.
> - **SHIPPED (rail-4 CLEAR -- test-only, touches NO params/orders/filters/heartbeat/CLAUDE, arms nothing, ships on green gate):** `backtest/tests/test_params_consumer_reconciliation.py` (4/4). Ratchet: (1) `test_no_new_dead_params_knob` -- dead set MUST be a subset of KNOWN_DEAD; a new unwired key REDs. (2) `test_known_dead_allowlist_shrinks_only` -- a KNOWN_DEAD key that GAINS a consumer must be removed (ratchet can only shrink) -> forces "restore-or-remove each dead key" to actually close. (3) hygiene: no stale allowlist entry. (4) NON-VACUOUS BITE both directions. KNOWN_DEAD documents all 24 with a RESTORE/REMOVE disposition tag.
> - **VALIDATED ($0, verify-now-not-later):** in-process proof BOTH ratchets bite -- injecting a fresh orphan knob REDs test1; feeding a revived `min_disk_free_mb` into the corpus REDs test2. Suite 4/4 (19.8s); siblings test_params_filters_drift + test_validated_setups_enabled 21/21; pre-commit curated safety gate **31 + 5 suites PASS** at 95a603b; verify-committed clean (file in commit, porcelain clean).
> - **LEARN (4.5):** lesson-inbox `2026-07-02-family-scoped-reconcile-guard-masks-other-families.md` -- a reconciliation guard scoped to ONE key family (gates) is easily mistaken for full config<->consumer coverage; its confident "no new parity" docstring HID the 24-knob gap. Corollary to C14/C7: a subset-scoped guard must state its coverage as a fraction of the whole, or a broad guard sits above it.
> - **REVERT:** `git revert 95a603b` removes the guard.
> - **NEXT FIRE picks up:** the follow-up **PARAMS-DEAD-KNOB-DISPOSITION** (MED, now queued) -- drain the 24-key KNOWN_DEAD allowlist by deciding RESTORE-or-REMOVE per knob (the shrinks-only ratchet auto-verifies each close). Other ready HIGH close-a-loops: PROMOTER-WRITES-LIVE-KEY (research->arm bridge), SINGLE-STRATEGY-REGISTRY-DESIGN, ADJUDICATE-CD-2026-06-29-001-TP1-REVERT (bookkeeping). The only remaining money-path PROOF stays 2026-07-02's real tape (first engine-originated core fill via simple-first path; funnel auto-reports). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/tests/test_params_consumer_reconciliation.py` (new 4/4, 95a603b); `automation/overnight/queue.md` (item->done + follow-up queued), `strategy/candidates/_lesson-inbox/2026-07-02-family-scoped-reconcile-guard-masks-other-families.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~03:55 ET] conductor: OK -- KILLED A MISDIAGNOSED HIGH QUEUE ITEM AT ITS FRAME: PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB would have VIOLATED L156 + RED'd its guard. The "dead-knob to fix" was an INTENTIONAL, lesson-encoded, guard-protected design. Resolved WONT-FIX-BY-DESIGN + strengthened the guard + corrected the misdiagnosis at its source. Commit 0480ced.

> **Signal J wakes to (OP-33 frame-audit + close-a-loop): a HIGH-priority "validation-fidelity bug" was a misdiagnosis — executing it as written would have re-introduced the exact measurement-integrity foot-gun L156 exists to prevent. Caught it BEFORE building, closed the loop, and hardened the guard so the misdiagnosis-applied-as-code cannot land.** After-hours conductor fire, market CLOSED (Thu 03:55 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check **GREEN**, problems:[]). FUNCTION-first satisfied (no BROKEN funnel; last day calendar-gated on 07-02 tape). No RED/BROKEN; self-audit tail DONE-marked through 07-01T17:33; validator/skill/chef inboxes clear. task_scorer had 6 HIGH items tied at 6.0 — picked the genuine needle-mover (PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB, "sim-accuracy gate class") over a small loop-close, since trend has been regressing on small loops.
> - **DIAGNOSED BEFORE BUILDING (OP-33, every claim evidenced):** the task said `_params_to_kwargs` "silently drops the v15 chandelier keys → every params-path A/B models exits WITHOUT the chandelier → C14 dead-knob, fix the mapping." Read the mapper (orchestrator.py L319-459): it maps premium_stop/tp1/qty/runner/filters/strike-tiers/entry-windows but ZERO chandelier keys — confirmed across the whole function. Then found `test_profit_lock_not_in_baseline.py` graduating **L156**: the drop is INTENTIONAL — the chandelier is regime-conditional (net-negative on the volume-dominant trending IS windows), so mapping it into the baseline would permanently bias EVERY candidate comparison negative. "Fixing" the mapping would VIOLATE L156 and RED its guard.
> - **THE TASK'S PREMISE IS FALSE:** "every A/B verdict suspect" is wrong because the drop is SYMMETRIC across both A/B arms (baseline + candidate both traverse the mapper) → relative verdicts unaffected; only the baseline's absolute-vs-live P&L is conservative, exactly the tradeoff L156 chose. PHASEC RESULTS.md itself: "Does not affect port cells." The mislabel originated in PHASEC caveat 7 ("C14 dead-knob class — flagged for fix") and was transcribed verbatim into the HIGH queue.
> - **SHIPPED (rail-4 CLEAR — guard test + docs; touches NO params/heartbeat/orders/filters/CLAUDE, arms nothing, ships on green tests):** (a) resolved the queue item WONT-FIX-BY-DESIGN with the L156 citation; (b) corrected PHASEC RESULTS.md caveat 7 (the misdiagnosis source); (c) STRENGTHENED the L156 guard — added the REAL production key names (`v15_profit_lock_*`, which the old synthetic un-prefixed `profit_lock_mode` list never exercised = the L197/G16 "test didn't exercise the production surface" vacuousness) + a non-vacuous real-params.json bite `test_real_params_chandelier_keys_dropped` (loads live params.json, asserts its 6 chandelier keys don't leak). Guard 2→3.
> - **VALIDATED ($0, verify-now-not-later):** in-process proof — real mapper leaks [] (green), a simulated leaky "fix" mapper leaks `profit_lock_mode` (the new test would RED); guard 3/3 (0.80s). Live params.json carries 6 chandelier keys (3 real + 3 doc-strings) so the real-data assertion is non-vacuous.
> - **LEARN (4.5):** lesson-inbox `2026-07-02-flagged-for-fix-caveat-was-guarded-intentional-design.md` — a "flagged-for-fix / silently-drops-X" research caveat is a HYPOTHESIS, not a work order; grep the guards + LESSONS for the symbol before queueing/executing a restore. A dead-knob is only dead if NO guard and NO lesson defend its absence. Corollary to L156/L197.
> - **REVERT:** `git revert 0480ced` restores the misleading caveat + weaker guard + reopens the (mis-framed) queue item.
> - **NEXT FIRE picks up:** the Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops — PARAMS-CONSUMER-RECONCILE-TEST (dead-knob reconciliation, the RIGHT general form of tonight's finding), PROMOTER-WRITES-LIVE-KEY (research→arm bridge), SINGLE-STRATEGY-REGISTRY-DESIGN, ADJUDICATE-CD-2026-06-29-001-TP1-REVERT (bookkeeping close). The only remaining money-path PROOF is 2026-07-02's real tape (first engine-originated core fill via simple-first path; funnel auto-reports). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/tests/test_profit_lock_not_in_baseline.py` (guard 2→3), `analysis/j-webull/PHASEC-port/RESULTS.md` (caveat 7 corrected), `automation/overnight/queue.md` (item→done), `strategy/candidates/_lesson-inbox/2026-07-02-flagged-for-fix-caveat-was-guarded-intentional-design.md` (new); `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-02 ~01:54 ET] conductor: OK -- CLOSED A LIVE APPROVE-BUS INTEGRITY HAZARD: proposal_id cd-2026-06-28-002 was reused on TWO different active proposals, and the actuator resolves a dup id TWO INCOMPATIBLE WAYS in one module -> a J `ship` could approve one row and apply/revert the other. Split the ids + shipped a uniqueness guard. Commit 5e536ca.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION-adjacent): the async approve bus (Discord `ship <id>` / companion wrist Approve) is now UNAMBIGUOUS -- an approval can no longer land on the wrong proposal.** After-hours conductor fire, market CLOSED (Thu 01:54 ET; engine-health **GREEN**, both accounts flat, reds:[]; self-check GREEN, no funnel BROKEN; last trading day 07-01 = 16 ENTER / 4 accepted / 0 fills, still calendar-gated on 07-02's real tape). No RED/BROKEN flags; self-audit tail (07-01T17:33) DONE-marked. task_scorer had 7 HIGH items tied at 6.0 -> picked FIX-CD-2026-06-28-002-ID-COLLISION as the close-a-loop that reduces a KNOWN risk on an order/arm-adjacent surface.
> - **DIAGNOSED before fixing (OP-33, quoted the mechanism):** `conductor-proposals.jsonl` had `cd-2026-06-28-002` on line 24 (BOLD-FLEET per-arm params_patch → accounts.json, `needs_structured_apply` + needs_j_gate) AND line 26 (L192 CLAUDE.md doc-fold, `approved`). Read `autonomy_actuator.py`: `sync_companion_approvals` builds `by_id = {r["proposal_id"]: r ...}` (L155, dict → LAST row wins → doc-fold) while `apply_approved`/`revert` use `next((r ... if id==pid))` (L580/L699, first-match → FIRST row → BOLD-FLEET). Same id, two rows, resolved DIFFERENTLY per code path. **Proof it was actively biting:** line 24 (BOLD-FLEET) carried an `actuator_note` "op[0] find-string not present in CLAUDE.md" dated 2026-07-02T05:30 — but BOLD-FLEET has NO CLAUDE.md op (its ops target accounts.json); the note came from the actuator processing the OTHER -002 (doc-fold's CLAUDE.md op) and mis-attributing it.
> - **SHIPPED (rail-4 CLEAR — approval-bus STATE, zero live-trading behavior change; ships on green tests):** re-id'd the BOLD-FLEET orphan → `cd-2026-06-28-003` (the doc-fold KEEPS `cd-2026-06-28-002` because it is the CANONICAL id-owner in `test_op25_index_reconciliation` baseline comments (5 lines) + 6+ STATUS CLAUDE-INDEX-FOLD refs + J's mental model; BOLD-FLEET is referenced only by title). Deliberately deviated from the queue's literal "re-id the later row" wording — re-id'ing the doc-fold would break MORE references (OP-0 pick-the-obvious-correct). Cleared the mis-attributed actuator_note with an accurate `reid_note`.
> - **GRADUATED TO A GUARD (OP-25, $0):** `backtest/tests/test_proposal_id_uniqueness.py` (4/4) — asserts no two ACTIVE-status rows (`pending`/`approved`/`needs_structured_apply`) share a proposal_id, with a non-vacuous bite (synthetic dup detected) + terminal-re-emission-allowed (a promote_keeper id that already `applied` once is harmless) + a regression pin that the -002 pair is now split.
> - **LEARN (4.5):** lesson-inbox `2026-07-02-same-id-resolved-two-ways-in-one-module.md` — the deeper foot-gun is the actuator's DIVERGENT dup resolution (dict last-wins vs next() first-wins in one module); the guard kills the symptom (dup active id), the owed follow-up (queued LOW `ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD`) is to route both paths through one `resolve_proposal()` that fails LOUD on a dup. Generalizable: two consumers of one key with different container semantics silently disagree.
> - **VALIDATED ($0, verify-now-not-later):** in-process re-parse — all 32 rows parse, ACTIVE-id collisions == {}, -002→doc-fold(approved) / -003→BOLD-FLEET(needs_structured_apply) cleanly split; reconciliation + actuator + new guard suites **37/37 PASS**; commit 5e536ca contains EXACTLY the 2 intended files (verify-committed clean). Metric: net improving, 0 regressions, trend **improving**.
> - **REVERT:** `git revert 5e536ca` restores the collided id + removes the guard.
> - **NEXT FIRE picks up:** approve bus is unambiguous + guarded. The owed defense-in-depth is `ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD` (LOW). The Tier-0.1 pipeline-audit HIGH stack still has ready close-a-loops (PARAMS-CONSUMER-RECONCILE-TEST, PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB, PROMOTER-WRITES-LIVE-KEY). **The only remaining money-path PROOF is 2026-07-02's real tape** — the first engine-originated core fill via the simple-first path (funnel auto-reports it). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198, now uniquely the doc-fold), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `automation/state/conductor-proposals.jsonl` (re-id + note fix), `backtest/tests/test_proposal_id_uniqueness.py` (new 4/4) — both 5e536ca; `strategy/candidates/_lesson-inbox/2026-07-02-same-id-resolved-two-ways-in-one-module.md`, `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-02 ~00:02 ET] conductor: OK -- FUNCTION-FIRST: RETIRED THE PERSISTENT FALSE-BROKEN on the fill-funnel. self_check was RED on 2026-07-01's IMMUTABLE pre-fix history; a retired-bracket/oto-ladder rejection is provably NOT a live fault -> frame-corrected to DEGRADED. self_check verified live BROKEN -> DEGRADED. Commit 1e3a6ab.

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION FIRST): the priority-1 fill-funnel BROKEN was a false-RED on stale pre-fix data, not a money-path fault -- and I proved it in the code before touching the frame.** After-hours conductor fire, market CLOSED (Wed 23:48 ET; engine-health **GREEN**, both accounts flat, reds:[]). `self-check-last.json` verdict was **BROKEN** (Stage-1 priority-1 FUNCTION signal): core:safe+bold each 5 ENTER / 5 attempted / 0 broker-accepted + ENTER-after-15:00.
> - **DIAGNOSED (OP-33, did NOT trust the 20:15 STATUS "stale artifact" claim):** re-read today's live core-decisions -- all 10 ENTER rows are 15:51-15:55 ET (RTH ran BEFORE b0d6ca0 committed ~19:30), and every rejection's `exec.broker` carries `bracket_err` + `oto_err` + `simple_err` (`_error`="bracket, oto, and simple all rejected"). Then VERIFIED the shipped code: FIX1 15:00 ceiling (SKIP_LATE_ENTRY L649/L921) + FIX2 simple-first (`_place_simple_entry` L693, called direct L1037) ARE in the code. So the funnel BROKEN was stale pre-fix history -- but it will stay RED until tomorrow's tape and MASK any genuinely-new fault (L189/L197 recurrence) + mis-steer every conductor fire's priority-1 pick.
> - **THE FRAME (why bracket/oto is a hard tell):** the shipped `_place_simple_entry` posts ONE plain marketable limit -- NO order_class -- so it can only ever emit `simple_err`/`_error`, NEVER `bracket_err`/`oto_err`. A rejection carrying those is DEFINITIVELY from the retired bracket->oto->simple ladder = pre-fix. The code invariant is guarded build-side (`test_money_path_2026_07_01`: AST `test_no_place_bracket_call_left_in_either_live_path` + behavioral `test_execute_first_and_only_order_call_is_simple_marketable`), so a regression re-adding the ladder REDs at BUILD before it ever reaches the funnel -> two-layer, no masking.
> - **SHIPPED (rail-4 PAPER trading-path monitor-correctness -- guard + revert + REVOKE):** `fill_funnel.py` `_acct_funnel` tracks `retired_ladder_fails`; `_evaluate` classifies an all-retired-ladder placement day as DEGRADED **"PLACEMENT PRE-FIX ARTIFACT"** (still surfaced for J's visibility) instead of RED **"PLACEMENT BROKEN"**. A day with ANY simple-only rejection (no bracket/oto) STILL fires RED. self_check re-run LIVE: **BROKEN -> DEGRADED** (6 problems, none `_problem_is_broken`).
> - **GUARD (frame-corrected SAME commit, L197 applied):** `test_fill_funnel_guard.py` -- `test_real_day_core_placement_broken_red` -> `test_real_day_core_is_pre_fix_artifact_degraded` (today's fixture now asserts pre-fix DEGRADED, `retired_ladder_fails==attempted`, no "PLACEMENT BROKEN"); `test_self_check_flags_placement_broken_as_broken` -> `test_self_check_pre_fix_artifact_not_broken`. Added the NON-VACUOUS BITE: `test_genuine_simple_only_rejection_is_placement_broken_red` + `test_self_check_genuine_placement_fault_is_broken` (a real simple-first reject -> RED/BROKEN). A revert to the old frame REDs these.
> - **VALIDATED ($0):** funnel+money-path suites 50/50; self_check live verdict DEGRADED (was BROKEN 9m prior); graduated_guards confirmed 0 references to fill_funnel (change can't affect it); pre-commit curated safety gate **31 + 5 suites PASS** at 1e3a6ab; verify-committed CLEAN (both files absent from porcelain). Metric: net improving, 0 regressions.
> - **LEARN (4.5):** no new L## -- this is L197 APPLIED (frame-fix the guard in the same commit; don't treat a pre-existing guard as ground truth) + the L189 mask-anti-pattern (a persistently-RED monitor masks new faults), both already encoded. Compound, not accumulate.
> - **REVERT:** `git revert 1e3a6ab` restores the old (false-RED) frame + guard.
> - **NEXT FIRE picks up:** self_check is DEGRADED (honest -- today had pre-fix late-enters + retired-ladder rejects, no live fault); tomorrow's simple-first code with the 15:00 ceiling should produce a clean GREEN (no ladder, no post-ceiling ENTER). **The ONLY remaining money-path proof is 2026-07-02's real tape** -- the first engine-originated core fill via the simple-first path (funnel auto-reports it). Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/fill_funnel.py` (retired_ladder_fails + pre-fix classification + docstring), `backtest/tests/test_fill_funnel_guard.py` (frame-corrected 2 + 2 new bite tests) -- all 1e3a6ab; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-02 ~00:50 ET] REVOKE-report: vwap_continuation now exit-managed by its VALIDATED cell (stop -8% / TP1 +30%), not ribbon_ride's WR-22% lotto shape. Commit 5ff20b4.

> **Shipped (rail-4 paper autonomy, xp-2026-07-02-vwapcont-exit-parity):** `_SETUP_EXIT_OVERRIDES` omitted vwap_continuation, so an armed fill's exit_manager ran strategies.ribbon_ride's shape (−20% stop / TP1 +150% sell 80%: WR 22.1%, top5-day 47.2%, J-anchor capture −97.2). Now it trades the OP-16 winner cell (stop −0.08 / tp1 0.30: OOS +$66.83/tr, WF 1.688, 6/6 quarters, anchor +44.52). Evidence: `analysis/recommendations/vwapcont-exit-parity.json`. Guards RED on regression (real strategies module wired — the old by_name→None mask is gone); 90/90 green + boot `skipped (not RTH)`. **UNVERIFIED until a real vwap_continuation fill exercises the exit_manager.** Revert: `git revert 5ff20b4`.

---

## [2026-07-01 ~20:15 ET] conductor: OK -- FUNCTION-FIRST: VERIFIED tonight's money-path fix (entry funnel) is real, THEN CLOSED THE EXIT HALF -- the v15.3 PRIMARY exit was SILENTLY DEAD (ribbon-flip-back never fired) + the guard that should have caught it was VACUOUS. Commit f76ac48 (guard) + concurrent-fire 4e71618 (prod).

> **Signal J wakes to (OP-33 verify-don't-claim + FUNCTION FIRST): the engine can now (a) place a fillable order AND (b) actually run its v15.3 chart-stop-PRIMARY exit tomorrow -- both halves of the money path verified, not claimed.** After-hours conductor fire, market CLOSED (Wed 20:15 ET; engine-health **GREEN**, both accounts flat, reds:[]). The live self_check verdict was **BROKEN** (Stage-1 priority-1 FUNCTION signal): today's core:safe+bold had 5 ENTER / 0 broker-accepted + 5 ENTER-after-15:00-ceiling. **DIAGNOSED (OP-33, not trusted the STATUS claim):** those are TODAY's PRE-fix decisions (RTH trading ran before b0d6ca0 committed ~19:30) -> stale-day artifact, not a live code fault. VERIFIED the money-path fix is genuinely shipped: FIX1 ceiling enforced at decision (L635) + placement (L906); FIX2 simple-first (`_place_simple_entry` mirrors the fleet primitive that PROVED filled today); wrapper arms BOTH `GAMMA_CORE_ARMED=1`+`GAMMA_CORE_MANAGES_EXITS=1`; end-to-end guarded (`test_money_path_2026_07_01.py` 35/35 incl. `test_execute_first_and_only_order_call_is_simple_marketable`). Entry funnel = closed-pending-tomorrow's-tape.
> - **THE PICK (the EXIT half of FUNCTION, task_scorer HIGH tied 6.0 -- G14-EXIT-RIBBON-FLIPBACK-WIRE):** the natural sequel -- we made entries fillable tonight; the first fill tomorrow needs its exits correct. Audit #6 said the v15.3 PRIMARY invalidation (ribbon-flip-back) has "no live consumer (`ribbon_flip_back_fn=None`)".
> - **OP-33 FINDING -- the queue claim was STALE but a REAL, WORSE bug sat underneath:** the wiring EXISTS (`_ribbon_flip_fn` L564 + `_manage_exits` passes `flip_fn` L586), so "fn=None" was already fixed. BUT `_ribbon_flip_fn` compared `ribbon_stack == ("BULLISH"/"BEARISH")` while the producer (`backtest/lib/ribbon.py` L102-104) ONLY emits `"BULL"/"BEAR"/"MIXED"/"WARMUP"/"UNKNOWN"` -> the comparison could NEVER match -> **the v15.3 chart-stop-PRIMARY exit silently never fired on ANY live position** (only the -50% catastrophe cap / target / time stops ran). A C14 string-mismatch dead-knob. Verified `manage_tick` (fleet/exit_actuator.py L121) calls the fn with `st.side`="P"/"C" -> invoked exactly as designed; the ONLY defect was the literal.
> - **HIDDEN BY A VACUOUS GUARD (the L197/G16 class):** `test_g14_ribbon_flip_fn_direction` RE-IMPLEMENTED the buggy logic INLINE (asserting the wrong `"BULLISH"` literals) instead of importing the real fn -> it green-lit a dead exit. Exactly L197 (a guard baking in the frame you later need to correct) + the G13/G16 "the test mocked the thing it should exercise" hole.
> - **SHIPPED (rail-4 PAPER trading-path fix -- guard + revert + REVOKE):** prod fix `_ribbon_flip_fn` `"BULLISH"/"BEARISH"` -> `"BULL"/"BEAR"` landed in **concurrent-fire commit 4e71618** (a parallel gamma-drive "arm 3 setups" fire independently converged on the identical fix, byte-identical comment -- same model/context -- but LEFT the vacuous guard, violating L197). MY commit **f76ac48** closed that hole: rewrote the guard to **import the REAL `heartbeat_core._ribbon_flip_fn`**, assert against the producer's ACTUAL literals, pin a producer-alphabet contract (REDs if ribbon.py renames its tokens), add MIXED/UNKNOWN/WARMUP hold cases + a BITE that the retired `"BULLISH"`/`"BEARISH"` literals are dead. Anchor 5/04 721P +$730 (ribbon stayed BEAR -> no premature flip exit) preserved. The guard now PROTECTS the prod fix -> a revert to `"BULLISH"` REDs.
> - **VALIDATED ($0, verify-now-not-later):** in-process behavioral check of the fixed fn vs real literals PASS (`f('BULL')('SPY','P') is True`, `f('BULLISH')...is False`); G14 guard 1/1; money-path 35/35; exit/funnel/trade-to-learn 45/45; **full graduated_guards 105 passed / 1 skipped**; pre-commit curated safety gate **31 + 5 suites PASS** at f76ac48.
> - **LEARN (4.5):** the concurrent fire's 4e71618 fixed prod but left the vacuous guard = a fresh instance of L197 (frame-fix the guard IN THE SAME COMMIT). Not a new L## -- L197 already encodes it; this fire is L197 APPLIED. Compound, not accumulate.
> - **REVERT PATH:** `git revert f76ac48` restores the prior (vacuous) guard; prod behavior lives in 4e71618 (validated-correct, so revert is not indicated -- REVOKE is the surface, not rollback).
> - **NEXT FIRE picks up:** both money-path halves are code-verified + guarded; the ONLY remaining proof is tomorrow's real tape (self_check/fill_funnel auto-report the first engine-originated core fill + that the v15.3 ribbon-flip-back exit fires on a real reversal). NOTE: a concurrent Gamma fire committed 5+ commits during this fire (e03aca5..67fd8ab) -- expect parallel work; STATUS.md saw a mid-fire external modification. Standing direction beyond the money path stays GEX-calendar-gated (premium axis dead L182-184; instrument+bull+range-scalp all closed; ~9 of ~60-90 GEX days accrued). J: OPEN decisions cd-2026-06-29-001 (TP1 revert), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/heartbeat_core.py` (`_ribbon_flip_fn` literal, via concurrent 4e71618), `backtest/tests/test_graduated_guards.py` (non-vacuous G14 guard, f76ac48); `automation/overnight/queue.md`, `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-01 ~19:30 ET] interactive (J + Gamma): FULL PIPELINE AUDIT -> J RATIFIED 4 DOCTRINE CHANGES -> MONEY-PATH FIX BURST SHIPPED (5 commits, ~92 new guards)

> **Signal J wakes to (OP-33): the engine can now actually place a fillable order tomorrow, and the fill funnel will prove it either way.** J commissioned a full swarm->kitchen->winners->engine->Alpaca audit ("not functional, not trading, crashing"). 7-agent recon found every research->engine handoff broken — full report `markdown/audits/PIPELINE-AUDIT-2026-07-01.md`. J then ratified: (1) FULL PAPER AUTONOMY (rail-4 rewritten — paper trading-path edits ship w/ guard+revert+REVOKE); (2) TRADE-TO-LEARN on paper; (3) CONSOLIDATE HARD; (4) success bar = daily paper trading + honest digest.
> - **Money path (b0d6ca0):** 15:00 entry ceiling now ENFORCED core+fleet (today's 10 late ENTERs -> PLACE_FAIL class is dead); placement goes straight to marketable simple limit (bracket/OTO 422 ladder removed); GATE_KEYS forwards the ratified elite-bull VIX bands; **vwap_continuation ARMED on Safe-2 paper** (extra_setup_exec_armed, ATM qty3, WP-5 override now honored — J's #1 edge, n=153 +$38.3/tr scorecard).
> - **Crash-loops (652bed9):** kitchen stage5 argv poison pill FIXED (daemon survived 158s + completed the poison task exit_code=0, was dying in 1-7s x10 today); fresh stage5 scorecard regenerated (was 2026-05-16-stale); promoter freshness guard; watcher_grader now grades all 584 obs (KeyError x3 days fixed); wrapper exit codes propagate.
> - **Truth instruments (commit 3):** fill_funnel.py per-day funnel (ENTER->attempted->accepted->filled->exited) wired into self_check (BROKEN on ENTER>0/accepted=0) + gamma_glance; EOD quant section now code-generated (today's journal regenerated: 16 ENTERs incl. 4 fleet fills w/ order IDs — replaces the fabricated "ENTER signals: 0"); loop-state ticks_today lie fixed.
> - **Autonomy re-aim (commit 4):** conductor Stage-1 = FUNCTION FIRST (fill-funnel drives the pick); outcome metric now records enters/accepted/fills per fire and trend weights FUNCTION; task_scorer depends-annotation + expense-penalty bugs fixed — J's buried HIGH engine items now top the ready list (9 trading-path HIGH items).
> - **Consolidate-hard (commit 5):** rank_contenders SKIP_UNCHANGED (no more restamping frozen data); kitchen_reviewer requires numeric scorecard evidence (hallucinated "$25000" auto-promotes dead); 8 dead grind/funnel tasks DISABLED (registry reconciled, 58 active rows); crypto drift spam cooldown + PS5.1 -NoNewline fix.
> - **FIRST ENGINE ROUND TRIPS EVER (today 11:22-11:34 ET):** 4 fleet arms placed marketable ENTER_BULL orders, filled, exit-managed to flat (fix #15 PROVEN on the fleet path). Core accounts still 0 post-fix fills — that is tomorrow's UNVERIFIED item; the funnel auto-reports it.
> - **UNVERIFIED until 2026-07-02 open:** engine-originated core-account fill via simple-first path; SKIP_LATE_ENTRY rows on any post-15:00 signal; armed vwap_continuation routing end-to-end on real tape; FUNCTION-FIRST steering the next conductor fire. Gamma_Conductor + Gamma_AutoApply re-enabled after the burst.
> - J: OPEN decisions now queued as HIGH items (ADJUDICATE-CD-2026-06-29-001-TP1-REVERT, FIX-CD-2026-06-28-002-ID-COLLISION, G7 EOD-flatten) — the loop can now pick them.

---

## [2026-07-01 ~17:50 ET] conductor: OK -- CLOSED A RECURRING SELF-AUDIT NOISE HOLE AT ITS FRAME (the 06-29 L-lesson recurred = a missing guardrail): tonight's un-actioned self-audit batch (9 gaps) had **5 of 9 = SCAFFOLD** the 06-29 `_is_real_gap` filter never anticipated. Hardened the filter + graduated the guard + DONE-marked the batch. Commit aab30bb.

> **Signal J wakes to (OP-25) -- the proactive gap-finder organ was flagging its own reasoning-scaffold as "gaps," crowding real gaps out of the [:12] budget (the exact 06-29 crowding-out failure, recurring). Fixed at the producer + guarded so it can't regress; the batch's 4 substantive items are all already-tracked, so no new actionable gap tonight.** After-hours conductor fire, market CLOSED (Wed 17:50 ET; engine-health verdict **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat, gex-archive healthy 9 sessions). No `### BROKEN:` flags (reds:[]). All 4 author inboxes clear (skill correction-queue 3/3 processed). task_scorer top-3 all MED multi-day / LOW rail-4 doc-folds -> the priority-2 pick (un-actioned self-audit batch) beat them.
> - **THE PICK (priority-2 self-audit gap > the MED multi-day queue):** the `2026-07-01T17:33:35` batch of 9 gaps was NOT DONE-marked. Triaged each (OP-33 skepticism, not hand-wave "noise"): 5 are SCAFFOLD -- "Question for reviewer" (3 words, passed the <3-word gate) + four "Perspective N flags/zeroes/warns/enumerates ..." cross-reference lead-ins (the SYNTHESIS describing perspectives, not stating gaps). The 4 substantive items all overlap tracked/just-fixed work (slippage=range-scalp closed + SKIP_LIQUIDITY; data-feed health=engine-health beacon; lesson-inbox-quarantine-risks-Rule-9=a misconception, conductor never applies lessons to params; volatility-adaptive sizing=SAFE-VIX-CONDITIONAL-SIZING MED queue).
> - **SHIPPED (engine-benefit observability code, rail-4 CLEAR -- self_audit.py is the gap-finder organ, touches NO params/doctrine-rules/orders/heartbeat/filters/CLAUDE, places NO order, arms NOTHING -> ships on green gate):** added "question for reviewer"/"question for the reviewer" to `_SCAFFOLD_PREFIXES` + a `_PERSPECTIVE_REF_RE` (`^perspective\s*\d`) lead-in reject to `_is_real_gap`. Verified in-process ($0): 5 scaffold now rejected, 5 substantive kept (incl. a mid-sentence "per-perspective backtest validation" survivor proving no over-rejection). The narrow-nbsp+CRLF in the real flagged text normalizes to "perspective5" -> still caught.
> - **GRADUATED TO A GUARD (OP-25, $0):** `test_self_audit_extract.py` 41->47 -- +5 scaffold cases (this batch's exact 5) + 1 non-over-rejection survivor. The load-bearing crowding-out regression test already covers the [:12]-budget mechanism.
> - **LEARN (4.5):** no new L## -- this is the SAME L-lesson the 06-29 `_is_real_gap` filter encoded (self-audit scaffold crowds real gaps), now with two more scaffold classes it didn't anticipate. Extending an existing guard, not a new foot-gun (compound, not accumulate).
> - **VALIDATED ($0, verify-now-not-later):** in-process scaffold/substantive check PASS; guard 47/47 (0.10s); pre-commit curated safety gate **31 + 5 suites PASS** at aab30bb; verify-committed clean (all 3 files absent from porcelain). Metric: net +25, 0 regressions, $2.48/drained, trend **regressing** (recent fires close small correctness loops -> low per-fire net; not a break, but next fire should prefer a genuine needle-mover if one is unblocked).
> - **NEXT FIRE picks up:** self-audit batches now DONE-marked through 07-01; the gap-finder organ won't re-flag "Perspective N"/"Question for reviewer" scaffold. Standing direction unchanged: NO armable edge tonight -- premium axis dead (L182-184), instrument rung closed (04adc35), range-scalp DIES_ON_SLIPPAGE on full history (c2bfe39), bull frontier FAILS_WALK_FORWARD on full history / EDGE-gated (6250b15), GEX class rung CALENDAR-gated (~9 of ~60-90 days accrued, free CBOE banker healthy). The high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `setup/scripts/self_audit.py` (+_PERSPECTIVE_REF_RE +2 scaffold prefixes), `backtest/tests/test_self_audit_extract.py` (41->47), `analysis/self-audit/new-gaps-flagged.md` (batch DONE-marked) -- all aab30bb; `conductor-outcomes.jsonl`, this STATUS entry.

---

## [2026-07-01 ~07:52 ET] conductor: OK -- DRAINED THE LAST ACTIVE LESSON-INBOX ITEM, CLOSED THE LEARN LOOP ON TONIGHT'S OWN FRAME-AUDIT (close-a-loop > artifact): the 04:02 range-scalp + 05:57 bull fires PROVED the "25-day OPRA wall" was a hardcoded-CSV misread over a 533-day master that already existed, and both dropped/referenced the foot-gun into `_lesson-inbox/2026-07-01-hardcoded-window-csv-masks-available-data.md` -- but the learn loop's final encode step (prose into permanent doctrine) had not run. Encoded it as **L198** in LESSONS-LEARNED.md. Commit a78c0f2.

> **Signal J wakes to (OP-25) -- the learn loop closes on tonight's own foot-gun; L198 cites the two already-shipped+guarded wide-window probes (test_range_scalp_widewindow 7/7 + test_bull_unblock_structural_widewindow 9/9), so this is pure encoding (compound, not accumulate). Lesson-inbox is now CLEAR (0 active .md).** After-hours conductor fire, market CLOSED (Wed 07:52 ET; engine-health verdict **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch all GREEN, both accounts flat, gex-archive healthy 8 sessions). No `### BROKEN:` flags (reds:[] in engine-health). Self-audit gaps ALL DONE-marked/noise (5 batches: 06-26 x2 DONE, 06-27 DONE, 06-28 DONE, 06-29 100%-noise DONE). task_scorer top-3 all MED multi-day (EOD-PHASE-2.x / MORNING-BULL J-gated / SAFE-VIX) -> rail-3 excludes; LOW items are rail-4 CLAUDE-index doc-folds.
> - **THE PICK (priority-4 author-inbox beats the MED multi-day queue):** the lesson-inbox had **1 ACTIVE (non-.DONE) item** dated 2026-07-01, and LESSONS-LEARNED.md topped out at L197 with it NOT encoded -> a genuine open LEARN loop (gamma.md step 6). The 05:57 fire's "already encoded 3h earlier" referred to the item being CAPTURED (inbox .md), not encoded to doctrine -- the still-`.md` suffix confirmed the encode step was owed. Closing it is a loop-closer, not a new artifact.
> - **NOTE (tool reality, OP-33):** no Agent/Task tool exposed this session -> could NOT fan out `lesson-author`. Did the mechanical encoding directly (read item -> append L## -> baseline the reconciliation guard -> rename inbox -> commit), the conductor's documented fallback. The CONDUCTOR-vs-lesson-author boundary HELD: appended L## prose to LESSONS-LEARNED.md (engine-benefit authoring, NOT rail-4) but did NOT edit the CLAUDE.md OP-25 index (rail-4 -> tracked in KNOWN_UNINDEXED_BASELINE +198).
> - **SHIPPED (engine-benefit doc authoring, rail-4 CLEAR -- LESSONS-LEARNED.md + a test baseline; touches NO params/doctrine-rules/orders/heartbeat/filters/CLAUDE, places NO order, arms NOTHING -> ships on green gate):** **L198** (a hardcoded recent-window data file + a stale comment can fake a "data-blocked" wall over data you already have; re-MEASURE the data span from source before inheriting a data-coverage claim, especially a *shared* wall cited across threads. C14/C4/C7 + L61 mirror-image). Cites exact files/tests/numbers (n 8->155 range-scalp DIES_ON_SLIPPAGE; n 8->82 bull FAILS_WALK_FORWARD; the retired 25-day CSV vs the 533-day master) + the two existing guards that enforce it.
> - **GUARD INTERACTION (caught + honored, not bypassed):** the pre-commit `test_op25_index_reconciliation::test_no_new_unindexed_lessons_beyond_baseline` would RED (L198 defined but not in the CLAUDE.md OP-25 index). Its documented escape hatch is `KNOWN_UNINDEXED_BASELINE` (where L192-197 already sit pending the same batch). Added 198 with the C14/C4/C7 fold target noted -> the ratchet trims it when cd-2026-06-28-002 applies the CLAUDE.md fold. Honest rail-4-deferred fold, NOT a --no-verify bypass.
> - **LEARN (4.5):** no new L## -- "the learn loop's final encode step had not run for tonight's frame-audit" is the normal author-inbox cadence (lesson-author/conductor runs after the fire that drops the item), not a new foot-gun. Loop closed > artifact added.
> - **VALIDATED ($0, verify-now-not-later):** L198 defined (grep 1/1); reconciliation guard 9/9 (0.06s); full pre-commit curated safety gate **31 + 5 suites PASS** at a78c0f2; verify-committed clean (all 3 intentional files absent from porcelain). Metric: net +25, 0 regressions, $2.50/drained, trend **regressing** (recent fires close small foot-gun loops -> low per-fire net; not a break, but next fire should prefer a genuine needle-mover if one is unblocked).
> - **NEXT FIRE picks up:** lesson-inbox is now CLEAR (0 active .md; glob-clean). The OP-25 index fold for L192-198 is the rail-4 batch cd-2026-06-28-002 awaiting J (one interactive CLAUDE.md edit drains all). Standing direction stays GEX-calendar-gated: premium axis dead (L182-184), instrument rung closed (04adc35), range-scalp DIES_ON_SLIPPAGE on full history (c2bfe39), bull frontier EDGE-gated / FAILS_WALK_FORWARD on full history (6250b15), GEX class rung CALENDAR-gated (~8 of ~60-90 days accrued, free CBOE banker healthy). **The honest state is NO armable edge tonight; no lever remains where more data would help.** The high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE (the stray untracked `2026-06-27-persistently-red-audit-masks-new-orphans.md.DONE`, seen again this fire) + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-198), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `markdown/doctrine/LESSONS-LEARNED.md` (+L198), `backtest/tests/test_op25_index_reconciliation.py` (baseline +198), `_lesson-inbox/2026-07-01-hardcoded-window-csv-masks-available-data.md.DONE` (renamed) -- all a78c0f2; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---

## [2026-07-01 ~05:57 ET] conductor: OK -- ACTED ON THE 04:02 FIRE'S EXPLICIT CARRY-FORWARD: re-ran the LAST open bull-unblock lever over the FULL 533-day OPRA history (the "25-day OPRA wall" was the SAME false-data-blocked frame the range-scalp fire proved false 3h earlier). Got the DECISIVE full-history verdict the 25-day window couldn't: **FAILS_WALK_FORWARD_SIGN_FLIP** -- the structural bull-unblock is NOT a real edge, it was a 2026-only OOS tail. Commit 6250b15.

> **Signal J wakes to (OP-33d frame-audit + close-a-loop) -- the 04:02 fire proved the range-scalp "data-blocked" wall was a hardcoded-25-day-CSV misread and EXPLICITLY named the carry-forward: "the bull-frontier '25-day OPRA wall' (BULL-UNBLOCK-REPLAY-PROBE) was the SAME misread -- re-run those probes over the FULL 370-day OPRA history before accepting 'bull data-gated.'" This fire did exactly that on the one bull lever whose verdict could genuinely FLIP with more data, and closed it for the RIGHT (data-rich) reason.** After-hours conductor fire, market CLOSED (Wed 05:57 ET; engine-health **GREEN** -- both heartbeats/beacon/watcher-feed/kill-switches/level-feed/gex/dispatch GREEN, both accounts flat). No `### BROKEN:` flags (grep 0). All self-audit gaps DONE/noise. task_scorer top-3 all MED multi-day (rail-3 excluded); LOW items are rail-4 CLAUDE-index doc-folds -> the honest pick was the named needle-mover.
> - **THE PICK (the #1 project thread + the 04:02 carry-forward > the MED queue):** the rig has never filled an ENTER_BULL in 2544 decisions. Of the 3 bull-unblock levers, SLICE-1 (elite) was decisively net-NEGATIVE (-$241, KEEP) and SLICE-3 (sequence_reclaim) is structurally coupled-off -- widening those only re-confirms. ONLY the STRUCTURAL lever (min_triggers_bull 2->1) was blocked purely by INCONCLUSIVE n=8 (+$76 GROSS), i.e. the exact "n<10 data-blocked" frame the range-scalp fire proved false -> the single lever whose verdict could FLIP with more data.
> - **DIAGNOSED before building (OP-33):** confirmed the full master exists (`spy_5m_2025-01-01_2026-06-18.csv` + VIX, 533d; OPRA real-fills 370 0DTE days via data-coverage.json) -- the SAME masters range_scalp_widewindow used. The 25-day bull probes hardcode `spy_5m_2026-05-19_2026-06-30.csv` -- the identical hardcoded-recent-CSV pattern. Smoke (Q1-2025, 15s) already showed the added cohort net -$194 (opposite of the 25-day +$76) -> the 25-day positive was a slice artifact.
> - **SHIPPED (engine-benefit research + guard, rail-4 CLEAR -- new probe + guard + result JSON; touches NO params/orders/filters/heartbeat-PROMPT/CLAUDE, places NO order, arms NOTHING, PROPOSES NOTHING since not-proposable -> ships on green tests, no A/B):** `bull_unblock_structural_widewindow_probe.py` runs the SAME min_triggers 2-vs-1 A/B (block_elite_bull held FIXED at prod True to isolate the structural lever) via the REAL engine (`run_backtest`, use_real_fills=True) over 2025-01-02..2026-06-18, splitting the added-bull cohort IS(2025)/OOS(2026), REUSING `_bull_cfg`/`_key`/`_date`/`ANCHOR_DATES` + probe_stats. RESULT (real OPRA fills, 533 days, 2m2s): BASE(min=2) n=243/+$3811, UNBL(min=1) n=323/+$4154 -> added bull cohort **n=82, pooled net +$607.58** BUT **IS-2025 net -$299.70 (exp -$5.55) / OOS-2026 net +$907.28 (exp +$32.4)** -> signs FLIP + FRAGILE_TO_SLIPPAGE (breakeven 0.0123c << 5c) + 215% day-concentrated. **VERDICT = FAILS_WALK_FORWARD_SIGN_FLIP.** The 25-day +$76 was purely a slice of the 2026-only OOS tail; the 2-trigger requirement correctly starves losers IN-SAMPLE. Result JSON `analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json`.
> - **GRADUATED TO A GUARD (OP-25, $0):** `backtest/tests/test_bull_unblock_structural_widewindow.py` (9/9, siblings 30/30) -- pins the committed golden finding (verdict FAILS_WALK_FORWARD, pooled n>=10, IS<0 & OOS>0 sign-flip, slippage-fragile, top3>150%), the full ladder + precedence, a **non-vacuous bite** (fixing the 3 genuine defects -> UNBLOCK_ADDS_EDGE_PROPOSE, so the reject is real not hardcoded), + the **frame-audit anti-regression** (probe MUST use the full master: window>365d, files exist, NOT the retired 25-day CSV) so the false "n<10 data-blocked" conclusion cannot silently return.
> - **LEARN (4.5):** no new L## -- this is the SAME frame-audit anti-pattern already encoded 3h earlier (lesson-inbox `2026-07-01-hardcoded-window-csv-masks-available-data.md`: "'data-blocked' is a testable statement, never a standing assumption, and never a *shared* wall cited by other threads without one fresh measurement"). This fire is that lesson APPLIED to the exact "shared wall" the lesson warned about. Loop closed > artifact added.
> - **VALIDATED ($0, verify-now-not-later):** smoke Q1-2025 (15s) confirmed mechanics + sign; full run 82 added / 533 days in 2m2s (backtest .venv reaper-exempt); guard 9/9 + siblings 30/30 (0.95s); curated safety gate **31 + 5 suites PASS** at 6250b15; verify-committed clean (all 3 files absent from porcelain).
> - **NEXT FIRE picks up:** the bull-unblock thread is now CLOSED for the RIGHT reason -- bull is **EDGE-gated (walk-forward failure on full history), NOT data-gated.** The "25-day OPRA wall" is retired as a false frame for BOTH range-scalp AND bull (same hardcoded-CSV misread). No lever remains where more data would help. Standing direction stays on the GEX 'class' rung (calendar-gated, ~8/60-90 days accrued; premium axis dead L182-184; instrument rung closed; range-scalp DIES_ON_SLIPPAGE; bull EDGE-gated) -- the honest state is NO armable edge tonight; the high-value genre remains engine-correctness close-a-loops + foot-gun guards until GEX fills OR a genuinely-new needle-mover is unblocked. Two LOW hygiene items still open (rail-3): LESSON-INBOX-ORPHAN-DOTDONE + LEVELS-UPSTREAM-DEDUP-SOURCE. J: OPEN decisions cd-2026-06-29-001 (revert vs keep+doc the 06-28 live params change), cd-2026-06-28-002 (CLAUDE-INDEX-FOLD, carries L192-197), cd-2026-06-27-001 (G7 EOD-flatten activate).
> - Files: `backtest/autoresearch/bull_unblock_structural_widewindow_probe.py` (new), `backtest/tests/test_bull_unblock_structural_widewindow.py` (new, 9/9), `analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json` (new) -- all 6250b15; `conductor-outcomes.jsonl`, `queue.md`, this STATUS entry.

---


- [2026-07-02 05:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T11:57:01.727977+00:00) | fail streak: 27 consecutive fires | stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 43.75% in last 24h (21/48) | v02 source parity drift in 35.18% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 05:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 06:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T12:27:01.923376+00:00) | fail streak: 28 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 41.67% in last 24h (20/48) | v02 source parity drift in 36.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 06:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T12:57:01.789250+00:00) | fail streak: 29 consecutive fires | stage v02_source_parity pass rate dropped to 60.42% in last 24h (29/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 39.58% in last 24h (19/48) | v02 source parity drift in 38.45% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T13:27:02.065371+00:00) | fail streak: 30 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 37.5% in last 24h (18/48) | v02 source parity drift in 40.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T13:57:02.009400+00:00) | fail streak: 31 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 35.42% in last 24h (17/48) | v02 source parity drift in 42.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T14:27:01.843803+00:00) | fail streak: 32 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 33.33% in last 24h (16/48) | v02 source parity drift in 42.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T14:57:02.010742+00:00) | fail streak: 33 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 31.25% in last 24h (15/48) | v02 source parity drift in 42.57% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T15:27:02.306773+00:00) | fail streak: 34 consecutive fires | stage v02_source_parity pass rate dropped to 60.42% in last 24h (29/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 29.17% in last 24h (14/48) | v02 source parity drift in 41.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T15:57:02.200596+00:00) | fail streak: 35 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 27.08% in last 24h (13/48) | v02 source parity drift in 39.36% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T16:27:02.217307+00:00) | fail streak: 36 consecutive fires | stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 25.0% in last 24h (12/48) | v02 source parity drift in 37.32% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T16:57:02.599113+00:00) | fail streak: 37 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 22.92% in last 24h (11/48) | v02 source parity drift in 35.42% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 11:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T17:27:02.145522+00:00) | fail streak: 38 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 20.83% in last 24h (10/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 11:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

## Kitchen
Kitchen: alive, queue 61 pending, last cook 0 min ago, today $0.00, model=openrouter::nvidia/nemotron-3-super-120b-a12b:free

- [2026-07-02 11:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T17:57:02.061643+00:00) | fail streak: 39 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 18.75% in last 24h (9/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 11:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 12:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T18:27:02.023835+00:00) | fail streak: 40 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 16.67% in last 24h (8/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 12:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 12:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T18:57:02.118323+00:00) | fail streak: 41 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 14.58% in last 24h (7/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 12:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 13:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T19:27:02.332688+00:00) | fail streak: 42 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 12.5% in last 24h (6/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 13:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 13:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T19:57:02.269461+00:00) | fail streak: 43 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 10.42% in last 24h (5/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 13:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-02T20:00:21+00:00
- task: eod-summary
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 14:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T20:27:03.461389+00:00) | fail streak: 44 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 8.33% in last 24h (4/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 14:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-02T20:45:43+00:00
- task: analyst
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 14:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T20:57:03.142930+00:00) | fail streak: 45 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 6.25% in last 24h (3/48) | v02 source parity drift in 34.89% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 14:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 21:00:01] gym-session (2026-07-02) → **RED** :: see `automation\state\gym-scorecard-2026-07-02.json`
- [2026-07-02 15:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T21:27:03.006225+00:00) | fail streak: 46 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 4.17% in last 24h (2/48) | v02 source parity drift in 35.08% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 15:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-02T21:30:29+00:00
- task: manager
- date_et: 2026-07-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-02 15:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T21:57:03.199521+00:00) | fail streak: 47 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 2.08% in last 24h (1/48) | v02 source parity drift in 34.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 15:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 16:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T22:27:03.169897+00:00) | fail streak: 48 consecutive fires | stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 33.09% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 16:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 16:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T22:57:02.958297+00:00) | fail streak: 49 consecutive fires | stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 31.0% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 16:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 17:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T23:27:03.055347+00:00) | fail streak: 50 consecutive fires | stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 17:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 17:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-02T23:57:02.989629+00:00) | fail streak: 51 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 17:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 18:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T00:27:02.989104+00:00) | fail streak: 52 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 18:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 18:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T00:57:03.190964+00:00) | fail streak: 53 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 18:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 19:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T01:27:03.129819+00:00) | fail streak: 54 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 19:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 19:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T01:57:03.032623+00:00) | fail streak: 55 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 19:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 20:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T02:27:03.369429+00:00) | fail streak: 56 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 20:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 20:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T02:57:02.896009+00:00) | fail streak: 57 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 20:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 21:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T03:27:02.921837+00:00) | fail streak: 58 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 21:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

### WARN: spend-summary threshold breach
- ts: 2026-07-03T03:30:35+00:00
- date_et: 2026-07-02
- total: $261.95 (threshold $30.00)
- claude: $261.90  minimax: $0.04
- claude_sessions: 23

- [2026-07-02 21:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T03:57:02.728141+00:00) | fail streak: 59 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 21:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 22:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T04:27:02.340980+00:00) | fail streak: 60 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 22:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 22:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T04:57:01.736981+00:00) | fail streak: 61 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 22:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 23:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T05:27:01.766732+00:00) | fail streak: 62 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 23:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-02 23:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T05:57:01.757797+00:00) | fail streak: 63 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-02 23:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-02.log

- [2026-07-03 00:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T06:27:01.681140+00:00) | fail streak: 64 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 00:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 00:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T06:57:01.660258+00:00) | fail streak: 65 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 00:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 01:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T07:27:01.698743+00:00) | fail streak: 66 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 01:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 01:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T07:57:01.870943+00:00) | fail streak: 67 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 01:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 02:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T08:27:01.759105+00:00) | fail streak: 68 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 02:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 02:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T08:57:01.659763+00:00) | fail streak: 69 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 02:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 03:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T09:27:01.643077+00:00) | fail streak: 70 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 03:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 03:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T09:57:01.643815+00:00) | fail streak: 71 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 03:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

[2026-07-03 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-03.md

- [2026-07-03 04:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T10:27:01.706981+00:00) | fail streak: 72 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 04:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 04:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T10:57:01.642006+00:00) | fail streak: 73 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 04:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 05:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T11:27:01.657842+00:00) | fail streak: 74 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 05:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 05:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T11:57:01.659899+00:00) | fail streak: 75 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 05:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 06:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T12:27:01.628211+00:00) | fail streak: 76 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 06:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: premarket 2026-07-03
- PREMARKET SILENT FAILURE: claude exit=0 but today-bias.falsifiable_predictions is empty (0) -- the premarket LLM produced no predictions (silent failure).


- [2026-07-03 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T12:57:01.672325+00:00) | fail streak: 77 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T13:27:01.730560+00:00) | fail streak: 78 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T13:57:01.727552+00:00) | fail streak: 79 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: self-check 2026-07-03T10:09:56
- engine-health RED: reds=['watcher_feed: PRODUCER DARK: newest bar 2026-07-02 != today 2026-07-03 -- feed not writing during RTH']

- [2026-07-03 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T14:27:01.906149+00:00) | fail streak: 80 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T14:57:01.989363+00:00) | fail streak: 81 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T15:27:02.012017+00:00) | fail streak: 82 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T15:57:01.708656+00:00) | fail streak: 83 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T16:27:01.801662+00:00) | fail streak: 84 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 10:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T16:57:03.220784+00:00) | fail streak: 85 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 10:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T17:27:02.985713+00:00) | fail streak: 86 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T17:57:03.128805+00:00) | fail streak: 87 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T18:27:02.935352+00:00) | fail streak: 88 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T18:57:03.519232+00:00) | fail streak: 89 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-03T19:27:02.932974+00:00) | fail streak: 90 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### BROKEN: self-check 2026-07-03T23:05:07
- DRESS-REHEARSAL STALE (RED): last rehearsal '2026-07-02T20:45:01' is >24h old on a weekday evening -- Gamma_DressRehearsal likely not firing.

- [2026-07-04 03:05:13] gym-session (2026-07-03) → **RED** :: see `automation\state\gym-scorecard-2026-07-03.json`
### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-04T03:05:31+00:00
- task: analyst
- date_et: 2026-07-03
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-04T03:05:54+00:00
- task: manager
- date_et: 2026-07-03
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

---

## Known broken
[2026-07-14T15:15:00-04:00] 🚨 DATA-LOSS INCIDENT — RECOVERED (root-caused + spliced back, permanent fix pending tonight's commit). At 09:15:00 ET a workflow subagent (strike-tier doc task, session 21375492/wf_45432f88) ran `git stash && pytest && git stash pop` in the SHARED main checkout; the pop never landed, the agent recovered only its own 3 files from the stash, then ran `git stash drop` at 09:16:36 ET — wiping ~3 weeks (2026-06-27→07-13) of uncommitted tracked state across 211 files, incl. core-decisions.jsonl (9,504 lines), all 3 fleet arms' decisions.jsonl, trades.csv (+2 rows), and ~21 append-only jsonl logs. RECOVERY: dropped stash found via `git fsck --unreachable` = commit `232a161`, pinned gc-proof as branch `recovery/stash-data-loss-2026-07-14`. 140 dormant-writer files restored intraday (verified idempotent); ledgers + live-writer logs splice-merged at 15:57 ET by `setup/scripts/recovery_splice_2026_07_14.py` (log: automation/state/recovered/splice-log-2026-07-14.txt). Today's live rows were never lost (continuous from 09:30:06). ROOT-CAUSE FIX (tonight): gitignore + untrack the 4 decision ledgers (verified: nothing reads their git history); lesson filed (_lesson-inbox/2026-07-14-git-stash-drop-wipes-shared-checkout.md) — tree-wide `git stash`/`reset --hard` in the shared checkout is BANNED for agents; use worktrees or pathspec-scoped ops.

[2026-07-08T18:30:33Z] MCP_AUDIT_RED: TradingView unresponsive after relaunch; Alpaca Safe+Bold healthy
[2026-07-08T08:35:00-04:00] PREMARKET TV_NOT_RUNNING: CDP unreachable after launch_tv_debug.ps1 self-heal + 3 retries (10-15s gaps). bias=no-trade-tv-fail written to today-bias.json; both kill-switches re-armed on live equity (Safe $1512.83 / Bold $1963.04, both flat). Crypto harness DEGRADED (v53_setup_dispatch.live failing, 103/104 pass) -- yellow, not trading-blocking. Macro calendar STALE 24 days (last refresh 2026-06-14) -- Sunday weekly-review has silently failed for 4+ weeks running, needs a manual `run-weekly-review.ps1` fire. daytrade_count field absent from Alpaca account_info again -- wrote day_trades_used_5d=0 to both breakers (was 7/4 from manual tracking). Heartbeat must retry TV at first tick; if still down, no entries this session.

[2026-07-07T18:30:26-04:00] MCP_AUDIT_RED: TradingView MCP bridge wedged (CDP listening but health_check failing after relaunch attempt). Alpaca accounts recovered (Safe+Bold healthy, auth errors from 07-06 cleared).

[2026-07-06T13:45:15Z] MCP_AUDIT_RED: Alpaca API auth failing (401 Unauthorized) on both Safe and Bold accounts

[2026-07-03T23:06:30-04:00] MCP_AUDIT_YELLOW: All systems healthy; TradingView CDP required relaunch

- [2026-07-03 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T03:27:03.867952+00:00) | fail streak: 91 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

### WARN: spend-summary threshold breach
- ts: 2026-07-04T03:30:29+00:00
- date_et: 2026-07-03
- total: $67.49 (threshold $30.00)
- claude: $67.46  minimax: $0.03
- claude_sessions: 6

- [2026-07-03 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T03:57:03.751642+00:00) | fail streak: 92 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T04:27:03.762857+00:00) | fail streak: 93 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 22:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T04:57:03.800537+00:00) | fail streak: 94 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 22:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

- [2026-07-03 23:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T05:27:03.777193+00:00) | fail streak: 95 consecutive fires | stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-03 23:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-03.log

[2026-07-04 08:49:35] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-04.md

- [2026-07-04 08:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T14:57:03.512409+00:00) | fail streak: 96 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 86.67% in last 24h (13/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 08:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 09:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T15:27:03.536698+00:00) | fail streak: 97 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 86.67% in last 24h (13/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 09:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 09:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T15:57:03.864239+00:00) | fail streak: 98 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 80.0% in last 24h (12/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 09:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T16:27:01.914749+00:00) | fail streak: 99 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 10:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T16:57:03.205720+00:00) | fail streak: 100 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 10:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T17:27:03.741384+00:00) | fail streak: 101 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 11:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T17:57:03.731461+00:00) | fail streak: 102 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 11:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 12:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T18:27:03.626606+00:00) | fail streak: 103 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 12:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 12:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T18:57:03.620375+00:00) | fail streak: 104 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 12:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 13:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T19:27:03.638347+00:00) | fail streak: 105 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.33% in last 24h (14/15) | stage v02_source_parity pass rate dropped to 73.33% in last 24h (11/15) | stage v03_indicators.live pass rate dropped to 93.33% in last 24h (14/15) | stage v04_candlesticks.live pass rate dropped to 93.33% in last 24h (14/15) | stage v05_levels.live pass rate dropped to 93.33% in last 24h (14/15) | stage v06_trendlines.live pass rate dropped to 93.33% in last 24h (14/15) | stage v07_volume.live pass rate dropped to 93.33% in last 24h (14/15) | stage v08_ribbon.live pass rate dropped to 93.33% in last 24h (14/15) | stage v09_regime.live pass rate dropped to 93.33% in last 24h (14/15) | stage v10_divergence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v11_breakout.live pass rate dropped to 93.33% in last 24h (14/15) | stage v12_multi_timeframe.live pass rate dropped to 93.33% in last 24h (14/15) | stage v14_sweep.live pass rate dropped to 93.33% in last 24h (14/15) | stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (14/15) | stage v46_market_structure.live pass rate dropped to 93.33% in last 24h (14/15) | stage v50_confluence.live pass rate dropped to 93.33% in last 24h (14/15) | stage v51_structure_veto_gate.live pass rate dropped to 93.33% in last 24h (14/15) | stage v52_trendline_break.live pass rate dropped to 93.33% in last 24h (14/15) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 13:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 13:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T19:57:03.652819+00:00) | fail streak: 106 consecutive fires | stage v01_closed_bar.live pass rate dropped to 93.75% in last 24h (15/16) | stage v02_source_parity pass rate dropped to 75.0% in last 24h (12/16) | stage v03_indicators.live pass rate dropped to 93.75% in last 24h (15/16) | stage v04_candlesticks.live pass rate dropped to 93.75% in last 24h (15/16) | stage v05_levels.live pass rate dropped to 93.75% in last 24h (15/16) | stage v06_trendlines.live pass rate dropped to 93.75% in last 24h (15/16) | stage v07_volume.live pass rate dropped to 93.75% in last 24h (15/16) | stage v08_ribbon.live pass rate dropped to 93.75% in last 24h (15/16) | stage v09_regime.live pass rate dropped to 93.75% in last 24h (15/16) | stage v10_divergence.live pass rate dropped to 93.75% in last 24h (15/16) | stage v11_breakout.live pass rate dropped to 93.75% in last 24h (15/16) | stage v12_multi_timeframe.live pass rate dropped to 93.75% in last 24h (15/16) | stage v14_sweep.live pass rate dropped to 93.75% in last 24h (15/16) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (15/16) | stage v46_market_structure.live pass rate dropped to 93.75% in last 24h (15/16) | stage v50_confluence.live pass rate dropped to 93.75% in last 24h (15/16) | stage v51_structure_veto_gate.live pass rate dropped to 93.75% in last 24h (15/16) | stage v52_trendline_break.live pass rate dropped to 93.75% in last 24h (15/16) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/16) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 13:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T20:27:03.618132+00:00) | fail streak: 107 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.12% in last 24h (16/17) | stage v02_source_parity pass rate dropped to 76.47% in last 24h (13/17) | stage v03_indicators.live pass rate dropped to 94.12% in last 24h (16/17) | stage v04_candlesticks.live pass rate dropped to 94.12% in last 24h (16/17) | stage v05_levels.live pass rate dropped to 94.12% in last 24h (16/17) | stage v06_trendlines.live pass rate dropped to 94.12% in last 24h (16/17) | stage v07_volume.live pass rate dropped to 94.12% in last 24h (16/17) | stage v08_ribbon.live pass rate dropped to 94.12% in last 24h (16/17) | stage v09_regime.live pass rate dropped to 94.12% in last 24h (16/17) | stage v10_divergence.live pass rate dropped to 94.12% in last 24h (16/17) | stage v11_breakout.live pass rate dropped to 94.12% in last 24h (16/17) | stage v12_multi_timeframe.live pass rate dropped to 94.12% in last 24h (16/17) | stage v14_sweep.live pass rate dropped to 94.12% in last 24h (16/17) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (16/17) | stage v46_market_structure.live pass rate dropped to 94.12% in last 24h (16/17) | stage v50_confluence.live pass rate dropped to 94.12% in last 24h (16/17) | stage v51_structure_veto_gate.live pass rate dropped to 94.12% in last 24h (16/17) | stage v52_trendline_break.live pass rate dropped to 94.12% in last 24h (16/17) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/17) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T20:57:03.571807+00:00) | fail streak: 108 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.44% in last 24h (17/18) | stage v02_source_parity pass rate dropped to 77.78% in last 24h (14/18) | stage v03_indicators.live pass rate dropped to 94.44% in last 24h (17/18) | stage v04_candlesticks.live pass rate dropped to 94.44% in last 24h (17/18) | stage v05_levels.live pass rate dropped to 94.44% in last 24h (17/18) | stage v06_trendlines.live pass rate dropped to 94.44% in last 24h (17/18) | stage v07_volume.live pass rate dropped to 94.44% in last 24h (17/18) | stage v08_ribbon.live pass rate dropped to 94.44% in last 24h (17/18) | stage v09_regime.live pass rate dropped to 94.44% in last 24h (17/18) | stage v10_divergence.live pass rate dropped to 94.44% in last 24h (17/18) | stage v11_breakout.live pass rate dropped to 94.44% in last 24h (17/18) | stage v12_multi_timeframe.live pass rate dropped to 94.44% in last 24h (17/18) | stage v14_sweep.live pass rate dropped to 94.44% in last 24h (17/18) | stage v15_three_source_parity.live pass rate dropped to 94.44% in last 24h (17/18) | stage v46_market_structure.live pass rate dropped to 94.44% in last 24h (17/18) | stage v50_confluence.live pass rate dropped to 94.44% in last 24h (17/18) | stage v51_structure_veto_gate.live pass rate dropped to 94.44% in last 24h (17/18) | stage v52_trendline_break.live pass rate dropped to 94.44% in last 24h (17/18) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/18) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T21:27:03.581796+00:00) | fail streak: 109 consecutive fires | stage v01_closed_bar.live pass rate dropped to 94.74% in last 24h (18/19) | stage v02_source_parity pass rate dropped to 78.95% in last 24h (15/19) | stage v03_indicators.live pass rate dropped to 94.74% in last 24h (18/19) | stage v04_candlesticks.live pass rate dropped to 94.74% in last 24h (18/19) | stage v05_levels.live pass rate dropped to 94.74% in last 24h (18/19) | stage v06_trendlines.live pass rate dropped to 94.74% in last 24h (18/19) | stage v07_volume.live pass rate dropped to 94.74% in last 24h (18/19) | stage v08_ribbon.live pass rate dropped to 94.74% in last 24h (18/19) | stage v09_regime.live pass rate dropped to 94.74% in last 24h (18/19) | stage v10_divergence.live pass rate dropped to 94.74% in last 24h (18/19) | stage v11_breakout.live pass rate dropped to 94.74% in last 24h (18/19) | stage v12_multi_timeframe.live pass rate dropped to 94.74% in last 24h (18/19) | stage v14_sweep.live pass rate dropped to 94.74% in last 24h (18/19) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (18/19) | stage v46_market_structure.live pass rate dropped to 94.74% in last 24h (18/19) | stage v50_confluence.live pass rate dropped to 94.74% in last 24h (18/19) | stage v51_structure_veto_gate.live pass rate dropped to 94.74% in last 24h (18/19) | stage v52_trendline_break.live pass rate dropped to 94.74% in last 24h (18/19) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/19) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 15:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T21:57:03.613416+00:00) | fail streak: 110 consecutive fires | stage v02_source_parity pass rate dropped to 80.0% in last 24h (16/20) -- but v15 (3-source) = 95.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/20) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 15:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T22:27:03.625455+00:00) | fail streak: 111 consecutive fires | stage v02_source_parity pass rate dropped to 80.95% in last 24h (17/21) -- but v15 (3-source) = 95.24% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/21) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T22:57:03.632696+00:00) | fail streak: 112 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (18/22) -- but v15 (3-source) = 95.45% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/22) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T23:27:03.721596+00:00) | fail streak: 113 consecutive fires | stage v02_source_parity pass rate dropped to 82.61% in last 24h (19/23) -- but v15 (3-source) = 95.65% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/23) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-04T23:57:03.589061+00:00) | fail streak: 114 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (20/24) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/24) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 18:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T00:27:03.649795+00:00) | fail streak: 115 consecutive fires | stage v02_source_parity pass rate dropped to 84.0% in last 24h (21/25) -- but v15 (3-source) = 96.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/25) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 18:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T00:57:03.675242+00:00) | fail streak: 116 consecutive fires | stage v02_source_parity pass rate dropped to 84.62% in last 24h (22/26) -- but v15 (3-source) = 96.15% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/26) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T01:27:03.646668+00:00) | fail streak: 117 consecutive fires | stage v02_source_parity pass rate dropped to 85.19% in last 24h (23/27) -- but v15 (3-source) = 96.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/27) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T01:57:03.652310+00:00) | fail streak: 118 consecutive fires | stage v02_source_parity pass rate dropped to 85.71% in last 24h (24/28) -- but v15 (3-source) = 96.43% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/28) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T02:27:03.684220+00:00) | fail streak: 119 consecutive fires | stage v02_source_parity pass rate dropped to 86.21% in last 24h (25/29) -- but v15 (3-source) = 96.55% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/29) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T02:57:03.413016+00:00) | fail streak: 120 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T03:27:03.351932+00:00) | fail streak: 121 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T03:57:03.383170+00:00) | fail streak: 122 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

- [2026-07-04 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-05T04:27:03.501210+00:00) | fail streak: 123 consecutive fires | stage v02_source_parity pass rate dropped to 86.67% in last 24h (26/30) -- but v15 (3-source) = 96.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-04 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-04.log

### DEGRADED: self-check 2026-07-06T09:43:26
- Gamma_LevelRefresh STALE in RTH: key-levels.json 1985m old (should be <10m). Engine may be blind to live structure.
- Gamma_SightBeacon STALE in RTH: beacon 2473m old (should be <2m). Engine eye may be dark.
- Gamma_HeartbeatCore STALE in RTH: last decision 3956m ago (should be ~1m). Engine may not be ticking.
- PREMARKET STALE: today-bias.json date=2026-07-03 != today 2026-07-06 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-06 07:43:26] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-06 07:43:27] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T13:43:42.257022+00:00) | fail streak: 124 consecutive fires :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 07:43:27] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

[2026-07-06 07:43:26] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-06.md

### BROKEN: self-check 2026-07-06T10:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 08:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T14:13:27.984737+00:00) | fail streak: 125 consecutive fires :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 08:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T10:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 08:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T14:43:28.143561+00:00) | fail streak: 126 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/3) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 08:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T11:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 09:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T15:13:27.852825+00:00) | fail streak: 127 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/4) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 09:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T11:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 09:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T15:43:27.956680+00:00) | fail streak: 128 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/5) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 09:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T12:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 10:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:13:27.627837+00:00) | fail streak: 129 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/6) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T12:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 10:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:43:27.934672+00:00) | fail streak: 130 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/7) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T16:57:02.415097+00:00) | fail streak: 131 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/8) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T13:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 11:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:13:27.651872+00:00) | fail streak: 132 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/9) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:27:02.929082+00:00) | fail streak: 133 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/10) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T13:39:56
- ENGINE CANNOT ENTER: 238 ticks today, 0 ENTER, 3x SKIP_STRUCTURE_VETO -- setups scored AND fired a trigger but every entry was gate-blocked by a NON-data-gated verdict. The engine is structurally sitting out (the 2026-06-30 zero-trade signature).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 11:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:43:27.932233+00:00) | fail streak: 134 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/11) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T17:57:02.927690+00:00) | fail streak: 135 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/12) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T14:09:56
- ENGINE CANNOT ENTER: 268 ticks today, 0 ENTER, 3x SKIP_STRUCTURE_VETO -- setups scored AND fired a trigger but every entry was gate-blocked by a NON-data-gated verdict. The engine is structurally sitting out (the 2026-06-30 zero-trade signature).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 12:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:13:27.737506+00:00) | fail streak: 136 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/13) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:27:02.898476+00:00) | fail streak: 137 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/14) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T14:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 12:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:43:27.815245+00:00) | fail streak: 138 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T18:57:02.845483+00:00) | fail streak: 139 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/16) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T15:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 13:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:13:27.773335+00:00) | fail streak: 140 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/17) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:27:02.853759+00:00) | fail streak: 141 consecutive fires | stage v02_source_parity pass rate dropped to 94.44% in last 24h (17/18) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/18) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T15:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 13:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:43:28.149761+00:00) | fail streak: 142 consecutive fires | stage v02_source_parity pass rate dropped to 94.74% in last 24h (18/19) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/19) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T19:57:02.851238+00:00) | fail streak: 143 consecutive fires | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/20) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-06T20:00:35+00:00
- task: eod-summary
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-06T16:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 14:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:13:27.643460+00:00) | fail streak: 144 consecutive fires | stage v02_source_parity pass rate dropped to 90.48% in last 24h (19/21) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/21) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 14:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:27:02.876824+00:00) | fail streak: 145 consecutive fires | stage v02_source_parity pass rate dropped to 86.36% in last 24h (19/22) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/22) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T16:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 14:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:43:28.008736+00:00) | fail streak: 146 consecutive fires | stage v02_source_parity pass rate dropped to 82.61% in last 24h (19/23) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/23) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-06T20:45:42+00:00
- task: analyst
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-06 09:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=STALE_47min TV up but CDP dead for 833s - kill+relaunch

- [2026-07-06 14:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T20:57:03.012059+00:00) | fail streak: 147 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (19/24) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/24) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 14:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 21:00:01] gym-session (2026-07-06) → **RED** :: see `automation\state\gym-scorecard-2026-07-06.json`
### BROKEN: self-check 2026-07-06T17:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 15:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:13:27.757864+00:00) | fail streak: 148 consecutive fires | stage v02_source_parity pass rate dropped to 76.0% in last 24h (19/25) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/25) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 15:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:27:02.894166+00:00) | fail streak: 149 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (19/26) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/26) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-06T21:30:45+00:00
- task: manager
- date_et: 2026-07-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-06T17:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 15:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:43:27.766806+00:00) | fail streak: 150 consecutive fires | stage v02_source_parity pass rate dropped to 70.37% in last 24h (19/27) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/27) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 15:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T21:57:02.927620+00:00) | fail streak: 151 consecutive fires | stage v02_source_parity pass rate dropped to 67.86% in last 24h (19/28) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/28) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 15:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T18:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 16:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:13:27.478806+00:00) | fail streak: 152 consecutive fires | stage v02_source_parity pass rate dropped to 65.52% in last 24h (19/29) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/29) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 16:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:27:02.923368+00:00) | fail streak: 153 consecutive fires | stage v02_source_parity pass rate dropped to 63.33% in last 24h (19/30) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T18:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 16:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:43:27.673307+00:00) | fail streak: 154 consecutive fires | stage v02_source_parity pass rate dropped to 61.29% in last 24h (19/31) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/31) | v02 source parity drift in 30.77% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 16:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T22:57:02.879942+00:00) | fail streak: 155 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (20/32) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/32) | v02 source parity drift in 31.2% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 16:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T19:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 17:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:13:27.600075+00:00) | fail streak: 156 consecutive fires | stage v02_source_parity pass rate dropped to 63.64% in last 24h (21/33) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/33) | v02 source parity drift in 30.29% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 17:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:27:02.907545+00:00) | fail streak: 157 consecutive fires | stage v02_source_parity pass rate dropped to 64.71% in last 24h (22/34) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/34) | v02 source parity drift in 30.36% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T19:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 17:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:43:27.825631+00:00) | fail streak: 158 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 17:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-06T23:57:02.908278+00:00) | fail streak: 159 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (24/36) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 17:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T20:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 18:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:13:27.586047+00:00) | fail streak: 160 consecutive fires | stage v02_source_parity pass rate dropped to 64.86% in last 24h (24/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 18:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:27:02.886999+00:00) | fail streak: 161 consecutive fires | stage v02_source_parity pass rate dropped to 65.79% in last 24h (25/38) -- but v15 (3-source) = 97.37% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### BROKEN: self-check 2026-07-06T20:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-06T09:43:29 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-06 18:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:43:27.491083+00:00) | fail streak: 162 consecutive fires | stage v02_source_parity pass rate dropped to 64.1% in last 24h (25/39) -- but v15 (3-source) = 97.44% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/39) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 18:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T00:57:02.909367+00:00) | fail streak: 163 consecutive fires | stage v02_source_parity pass rate dropped to 62.5% in last 24h (25/40) -- but v15 (3-source) = 97.5% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/40) :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 18:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T21:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 19:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:13:27.505098+00:00) | fail streak: 164 consecutive fires | stage v02_source_parity pass rate dropped to 60.98% in last 24h (25/41) -- but v15 (3-source) = 97.56% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/41) | v02 source parity drift in 30.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 19:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:27:02.912312+00:00) | fail streak: 165 consecutive fires | stage v02_source_parity pass rate dropped to 59.52% in last 24h (25/42) -- but v15 (3-source) = 97.62% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/42) | v02 source parity drift in 31.95% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T21:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 19:43:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:43:28.724100+00:00) | fail streak: 166 consecutive fires | stage v02_source_parity pass rate dropped to 58.14% in last 24h (25/43) -- but v15 (3-source) = 97.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/43) | v02 source parity drift in 33.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:43:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 19:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T01:57:02.907033+00:00) | fail streak: 167 consecutive fires | stage v02_source_parity pass rate dropped to 56.82% in last 24h (25/44) -- but v15 (3-source) = 97.73% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/44) | v02 source parity drift in 34.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 19:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T22:09:57
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 20:13:26] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:13:28.972693+00:00) | fail streak: 168 consecutive fires | stage v02_source_parity pass rate dropped to 57.78% in last 24h (26/45) -- but v15 (3-source) = 97.78% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/45) | v02 source parity drift in 35.46% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:13:26] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-06 20:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:27:01.673840+00:00) | fail streak: 169 consecutive fires | stage v02_source_parity pass rate dropped to 58.7% in last 24h (27/46) -- but v15 (3-source) = 97.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/46) | v02 source parity drift in 34.88% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T22:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 20:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T02:57:01.771810+00:00) | fail streak: 170 consecutive fires | stage v02_source_parity pass rate dropped to 59.57% in last 24h (28/47) -- but v15 (3-source) = 97.87% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/47) | v02 source parity drift in 33.6% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 20:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### DEGRADED: self-check 2026-07-06T23:09:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 21:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T03:27:02.022532+00:00) | fail streak: 171 consecutive fires | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 34.09% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 21:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

### WARN: spend-summary threshold breach
- ts: 2026-07-07T03:30:06+00:00
- date_et: 2026-07-06
- total: $190.19 (threshold $30.00)
- claude: $189.48  minimax: $0.04
- claude_sessions: 14

### DEGRADED: self-check 2026-07-06T23:39:56
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:risky-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-1]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']
- FILL-FUNNEL ENTER AFTER CEILING[fleet:safe-3]: 3 ENTER after 15:00 ET: ['15:22 ENTER_BULL ?', '15:25 ENTER_BULL ?', '15:28 ENTER_BULL ?']

- [2026-07-06 21:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T03:57:01.695157+00:00) | fail streak: 172 consecutive fires | stage v02_source_parity pass rate dropped to 57.14% in last 24h (28/49) -- but v15 (3-source) = 97.96% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) | v02 source parity drift in 35.61% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-06 21:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-06.log

- [2026-07-07 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T12:57:01.637833+00:00) | fail streak: 173 consecutive fires | stage v02_source_parity pass rate dropped to 58.0% in last 24h (29/50) -- but v15 (3-source) = 98.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) | v02 source parity drift in 35.84% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T08:58:54
- PREMARKET STALE: today-bias.json date=2026-07-06 != today 2026-07-07 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

[2026-07-07 06:58:54] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-07.md
- [07-07 09:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 827s - kill+relaunch
- [07-07 09:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1127s - kill+relaunch
- [07-07 09:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1427s - kill+relaunch

- [2026-07-07 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T13:27:01.727254+00:00) | fail streak: 174 consecutive fires | stage v02_source_parity pass rate dropped to 58.82% in last 24h (30/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 34.58% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 09:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 1727s - kill+relaunch
- [07-07 09:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 2027s - kill+relaunch
- [07-07 09:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2327s - kill+relaunch
- [07-07 09:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 372s - kill+relaunch
- [07-07 09:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 672s - kill+relaunch

- [2026-07-07 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T13:57:01.972249+00:00) | fail streak: 175 consecutive fires | stage v02_source_parity pass rate dropped to 58.82% in last 24h (30/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 34.02% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 09:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 973s - kill+relaunch
- [07-07 10:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1273s - kill+relaunch
- [07-07 10:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1572s - kill+relaunch
- [07-07 10:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 1872s - kill+relaunch
- [07-07 10:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2172s - kill+relaunch
- [07-07 10:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2472s - kill+relaunch

- [2026-07-07 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T14:27:01.733758+00:00) | fail streak: 176 consecutive fires | stage v02_source_parity pass rate dropped to 56.86% in last 24h (29/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 35.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 10:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 2772s - kill+relaunch
- [07-07 10:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3072s - kill+relaunch
- [07-07 10:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3372s - kill+relaunch
- [07-07 10:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3672s - kill+relaunch
- [07-07 10:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 3972s - kill+relaunch
- [07-07 10:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4272s - kill+relaunch

- [2026-07-07 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T14:57:01.687942+00:00) | fail streak: 177 consecutive fires | stage v02_source_parity pass rate dropped to 54.9% in last 24h (28/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 39.31% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 10:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4572s - kill+relaunch
- [07-07 11:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 4872s - kill+relaunch
- [07-07 11:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5172s - kill+relaunch

### BROKEN: self-check 2026-07-07T11:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 11:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5472s - kill+relaunch
- [07-07 11:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 5772s - kill+relaunch
- [07-07 11:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6072s - kill+relaunch

- [2026-07-07 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T15:27:01.737005+00:00) | fail streak: 178 consecutive fires | stage v02_source_parity pass rate dropped to 52.94% in last 24h (27/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 42.53% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 11:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6372s - kill+relaunch
- [07-07 11:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6672s - kill+relaunch
- [07-07 11:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 6972s - kill+relaunch

### BROKEN: self-check 2026-07-07T11:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 11:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7272s - kill+relaunch
- [07-07 11:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7572s - kill+relaunch
- [07-07 11:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 7872s - kill+relaunch

- [2026-07-07 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T15:57:01.726683+00:00) | fail streak: 179 consecutive fires | stage v02_source_parity pass rate dropped to 50.98% in last 24h (26/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 45.16% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 11:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8172s - kill+relaunch
- [07-07 12:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8472s - kill+relaunch
- [07-07 12:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 8772s - kill+relaunch

### BROKEN: self-check 2026-07-07T12:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 12:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9072s - kill+relaunch
- [07-07 12:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9372s - kill+relaunch
- [07-07 12:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9672s - kill+relaunch

- [2026-07-07 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T16:27:01.824786+00:00) | fail streak: 180 consecutive fires | stage v02_source_parity pass rate dropped to 49.02% in last 24h (25/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 48.51% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 12:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 9972s - kill+relaunch
- [07-07 12:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10272s - kill+relaunch
- [07-07 12:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10572s - kill+relaunch

### BROKEN: self-check 2026-07-07T12:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 12:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 10872s - kill+relaunch
- [07-07 12:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11172s - kill+relaunch
- [07-07 12:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11472s - kill+relaunch

- [2026-07-07 10:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T16:57:02.962902+00:00) | fail streak: 182 consecutive fires | stage v02_source_parity pass rate dropped to 45.1% in last 24h (23/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) | v02 source parity drift in 51.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 10:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 12:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 11772s - kill+relaunch
- [07-07 13:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12072s - kill+relaunch
- [07-07 13:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12372s - kill+relaunch

### BROKEN: self-check 2026-07-07T13:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 13:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12672s - kill+relaunch
- [07-07 13:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 12972s - kill+relaunch
- [07-07 13:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13272s - kill+relaunch

- [2026-07-07 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T17:27:03.322205+00:00) | fail streak: 183 consecutive fires | stage v02_source_parity pass rate dropped to 44.0% in last 24h (22/50) -- but v15 (3-source) = 98.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) | v02 source parity drift in 53.79% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 13:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13572s - kill+relaunch
- [07-07 13:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 13872s - kill+relaunch
- [07-07 13:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14172s - kill+relaunch

### BROKEN: self-check 2026-07-07T13:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 13:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14472s - kill+relaunch
- [07-07 13:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 14772s - kill+relaunch
- [07-07 13:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15072s - kill+relaunch

- [2026-07-07 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T17:57:02.457099+00:00) | fail streak: 184 consecutive fires | stage v02_source_parity pass rate dropped to 42.86% in last 24h (21/49) -- but v15 (3-source) = 97.96% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) | v02 source parity drift in 53.79% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 13:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15372s - kill+relaunch
- [07-07 14:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15672s - kill+relaunch
- [07-07 14:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 15972s - kill+relaunch

### BROKEN: self-check 2026-07-07T14:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 3 ENTER, 3 attempted, 0 broker-accepted. Reasons: 3x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 14:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16272s - kill+relaunch
- [07-07 14:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16572s - kill+relaunch
- [07-07 14:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 16872s - kill+relaunch

- [2026-07-07 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T18:27:02.462625+00:00) | fail streak: 185 consecutive fires | stage v02_source_parity pass rate dropped to 41.67% in last 24h (20/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) | v02 source parity drift in 53.92% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 14:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17172s - kill+relaunch
- [07-07 14:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17472s - kill+relaunch
- [07-07 14:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 17772s - kill+relaunch

### BROKEN: self-check 2026-07-07T14:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 14:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18072s - kill+relaunch
- [07-07 14:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18372s - kill+relaunch
- [07-07 14:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18672s - kill+relaunch

- [2026-07-07 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T18:57:02.483038+00:00) | fail streak: 186 consecutive fires | stage v02_source_parity pass rate dropped to 40.43% in last 24h (19/47) -- but v15 (3-source) = 97.87% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/47) | v02 source parity drift in 53.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 14:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 18973s - kill+relaunch
- [07-07 15:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19272s - kill+relaunch
- [07-07 15:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19572s - kill+relaunch

### BROKEN: self-check 2026-07-07T15:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 15:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 19872s - kill+relaunch
- [07-07 15:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20172s - kill+relaunch
- [07-07 15:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20472s - kill+relaunch

- [2026-07-07 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T19:27:02.408568+00:00) | fail streak: 187 consecutive fires | stage v02_source_parity pass rate dropped to 39.13% in last 24h (18/46) -- but v15 (3-source) = 97.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/46) | v02 source parity drift in 54.71% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 15:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 20772s - kill+relaunch
- [07-07 15:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21072s - kill+relaunch
- [07-07 15:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21372s - kill+relaunch

### BROKEN: self-check 2026-07-07T15:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-07 15:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21672s - kill+relaunch
- [07-07 15:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 21972s - kill+relaunch
- [07-07 15:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 22272s - kill+relaunch

- [2026-07-07 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T19:57:02.408401+00:00) | fail streak: 188 consecutive fires | stage v02_source_parity pass rate dropped to 35.56% in last 24h (16/45) -- but v15 (3-source) = 97.78% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/45) | v02 source parity drift in 57.83% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 15:58 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 22572s - kill+relaunch

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-07T20:00:21+00:00
- task: eod-summary
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-07 16:03 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 22872s - kill+relaunch
- [07-07 16:08 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23172s - kill+relaunch

### BROKEN: self-check 2026-07-07T16:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']
- [07-07 16:13 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23472s - kill+relaunch
- [07-07 16:18 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 23772s - kill+relaunch
- [07-07 16:23 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24072s - kill+relaunch

- [2026-07-07 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T20:27:03.296538+00:00) | fail streak: 189 consecutive fires | stage v02_source_parity pass rate dropped to 36.36% in last 24h (16/44) -- but v15 (3-source) = 95.45% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/44) | v02 source parity drift in 57.83% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log
- [07-07 16:28 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24372s - kill+relaunch
- [07-07 16:33 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24672s - kill+relaunch
- [07-07 16:38 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 24972s - kill+relaunch

### BROKEN: self-check 2026-07-07T16:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']
- [07-07 16:43 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25272s - kill+relaunch

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-07T20:45:14+00:00
- task: analyst
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000
- [07-07 16:48 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25572s - kill+relaunch
- [07-07 16:53 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 25872s - kill+relaunch

- [2026-07-07 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T20:57:03.321808+00:00) | fail streak: 190 consecutive fires | stage v02_source_parity pass rate dropped to 39.53% in last 24h (17/43) -- but v15 (3-source) = 95.35% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/43) | v02 source parity drift in 55.76% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 21:00:01] gym-session (2026-07-07) → **RED** :: see `automation\state\gym-scorecard-2026-07-07.json`
### BROKEN: self-check 2026-07-07T17:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T21:27:03.545450+00:00) | fail streak: 191 consecutive fires | stage v02_source_parity pass rate dropped to 42.86% in last 24h (18/42) -- but v15 (3-source) = 95.24% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/42) | v02 source parity drift in 52.53% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-07T21:30:32+00:00
- task: manager
- date_et: 2026-07-07
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-07T17:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 15:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T21:57:03.594678+00:00) | fail streak: 192 consecutive fires | stage v02_source_parity pass rate dropped to 46.34% in last 24h (19/41) -- but v15 (3-source) = 95.12% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/41) | v02 source parity drift in 49.31% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 15:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### BROKEN: self-check 2026-07-07T18:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 8 ENTER, 8 attempted, 0 broker-accepted. Reasons: 8x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 10 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T22:27:03.527362+00:00) | fail streak: 193 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (20/40) -- but v15 (3-source) = 95.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/40) | v02 source parity drift in 45.85% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T18:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T22:57:03.734286+00:00) | fail streak: 194 consecutive fires | stage v02_source_parity pass rate dropped to 51.28% in last 24h (20/39) | stage v15_three_source_parity.live pass rate dropped to 94.87% in last 24h (37/39) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/39) | v02 source parity drift in 43.32% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T19:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T23:27:03.625589+00:00) | fail streak: 195 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (19/38) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (36/38) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T19:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-07T23:57:03.658909+00:00) | fail streak: 197 consecutive fires | stage v02_source_parity pass rate dropped to 50.0% in last 24h (19/38) | stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (36/38) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T20:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 18:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T00:27:03.566269+00:00) | fail streak: 198 consecutive fires | stage v02_source_parity pass rate dropped to 51.35% in last 24h (19/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) | v02 source parity drift in 42.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 18:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T20:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T00:57:03.322358+00:00) | fail streak: 201 consecutive fires | stage v02_source_parity pass rate dropped to 57.89% in last 24h (22/38) -- but v15 (3-source) = 97.37% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) | v02 source parity drift in 40.78% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T21:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T01:27:03.407903+00:00) | fail streak: 202 consecutive fires | stage v02_source_parity pass rate dropped to 62.16% in last 24h (23/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) | v02 source parity drift in 37.56% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T21:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T01:57:03.377938+00:00) | fail streak: 203 consecutive fires | stage v02_source_parity pass rate dropped to 66.67% in last 24h (24/36) -- but v15 (3-source) = 97.22% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) | v02 source parity drift in 34.33% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T22:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T02:27:03.813780+00:00) | fail streak: 204 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 32.95% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T22:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T02:57:03.713484+00:00) | fail streak: 205 consecutive fires | stage v02_source_parity pass rate dropped to 65.71% in last 24h (23/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 32.87% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### DEGRADED: self-check 2026-07-07T23:09:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T03:27:03.617558+00:00) | fail streak: 206 consecutive fires | stage v02_source_parity pass rate dropped to 68.57% in last 24h (24/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) | v02 source parity drift in 31.34% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

### WARN: spend-summary threshold breach
- ts: 2026-07-08T03:30:33+00:00
- date_et: 2026-07-07
- total: $780.71 (threshold $30.00)
- claude: $780.67  minimax: $0.04
- claude_sessions: 8

### DEGRADED: self-check 2026-07-07T23:39:57
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BEAR ?', '15:47 ENTER_BEAR ?', '15:48 ENTER_BEAR ?']

- [2026-07-07 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T03:57:03.671139+00:00) | fail streak: 207 consecutive fires | stage v02_source_parity pass rate dropped to 71.43% in last 24h (25/35) -- but v15 (3-source) = 97.14% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/35) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T04:27:03.288932+00:00) | fail streak: 208 consecutive fires | stage v02_source_parity pass rate dropped to 72.22% in last 24h (26/36) -- but v15 (3-source) = 97.22% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/36) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 22:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T04:57:03.344302+00:00) | fail streak: 209 consecutive fires | stage v02_source_parity pass rate dropped to 72.97% in last 24h (27/37) -- but v15 (3-source) = 97.3% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/37) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 22:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 23:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T05:27:03.321197+00:00) | fail streak: 210 consecutive fires | stage v02_source_parity pass rate dropped to 73.68% in last 24h (28/38) -- but v15 (3-source) = 97.37% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/38) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 23:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-07 23:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T05:57:03.353974+00:00) | fail streak: 211 consecutive fires | stage v02_source_parity pass rate dropped to 74.36% in last 24h (29/39) -- but v15 (3-source) = 97.44% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/39) :: see crypto/data/scorecards/drift_report.json

- [2026-07-07 23:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-07.log

- [2026-07-08 00:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T06:27:03.339609+00:00) | fail streak: 212 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (30/40) -- but v15 (3-source) = 97.5% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/40) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 00:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 00:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T06:57:03.373884+00:00) | fail streak: 213 consecutive fires | stage v02_source_parity pass rate dropped to 75.61% in last 24h (31/41) -- but v15 (3-source) = 97.56% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/41) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 00:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 01:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T07:27:03.329818+00:00) | fail streak: 214 consecutive fires | stage v02_source_parity pass rate dropped to 76.19% in last 24h (32/42) -- but v15 (3-source) = 97.62% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/42) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 01:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 01:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T07:57:03.352471+00:00) | fail streak: 215 consecutive fires | stage v02_source_parity pass rate dropped to 76.74% in last 24h (33/43) -- but v15 (3-source) = 97.67% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/43) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 01:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 02:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T08:27:03.341533+00:00) | fail streak: 216 consecutive fires | stage v02_source_parity pass rate dropped to 77.27% in last 24h (34/44) -- but v15 (3-source) = 97.73% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/44) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 02:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 02:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T08:57:03.388108+00:00) | fail streak: 217 consecutive fires | stage v02_source_parity pass rate dropped to 75.56% in last 24h (34/45) -- but v15 (3-source) = 97.78% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/45) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 02:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 03:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T09:27:03.343985+00:00) | fail streak: 218 consecutive fires | stage v02_source_parity pass rate dropped to 73.91% in last 24h (34/46) -- but v15 (3-source) = 97.83% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/46) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 03:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 03:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T09:57:03.351970+00:00) | fail streak: 219 consecutive fires | stage v02_source_parity pass rate dropped to 72.34% in last 24h (34/47) -- but v15 (3-source) = 97.87% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/47) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 03:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 04:00:02] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

[2026-07-08 04:00:02] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-08.md

- [2026-07-08 04:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T10:27:03.332210+00:00) | fail streak: 220 consecutive fires | stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 04:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 04:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T10:57:03.389766+00:00) | fail streak: 221 consecutive fires | stage v02_source_parity pass rate dropped to 73.47% in last 24h (36/49) -- but v15 (3-source) = 97.96% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 04:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 05:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T11:27:03.826168+00:00) | fail streak: 222 consecutive fires | stage v02_source_parity pass rate dropped to 74.0% in last 24h (37/50) -- but v15 (3-source) = 98.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 05:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 05:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T11:57:03.543342+00:00) | fail streak: 223 consecutive fires | stage v02_source_parity pass rate dropped to 74.51% in last 24h (38/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 05:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 08:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 80539s - kill+relaunch
- [07-08 08:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 80840s - kill+relaunch
- [07-08 08:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 81140s - kill+relaunch
- [07-08 08:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 81440s - kill+relaunch
- [07-08 08:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 81740s - kill+relaunch

- [2026-07-08 06:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T12:27:03.486288+00:00) | fail streak: 224 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (39/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 06:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 08:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 82040s - kill+relaunch
- [07-08 08:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 82340s - kill+relaunch
- [07-08 08:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 82640s - kill+relaunch
- [07-08 08:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 82940s - kill+relaunch
- [07-08 08:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 83240s - kill+relaunch
- [07-08 08:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 83540s - kill+relaunch

- [2026-07-08 06:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T12:57:03.612683+00:00) | fail streak: 225 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (39/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 06:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 09:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 83840s - kill+relaunch
- [07-08 09:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 84140s - kill+relaunch
- [07-08 09:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 84439s - kill+relaunch
- [07-08 09:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 84740s - kill+relaunch
- [07-08 09:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 85039s - kill+relaunch
- [07-08 09:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 85340s - kill+relaunch

- [2026-07-08 07:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T13:27:03.551127+00:00) | fail streak: 226 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (39/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 07:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 09:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 85639s - kill+relaunch
- [07-08 09:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 85940s - kill+relaunch
- [07-08 09:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 86239s - kill+relaunch
- [07-08 09:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 86539s - kill+relaunch
- [07-08 09:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 86839s - kill+relaunch
- [07-08 09:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 87139s - kill+relaunch

- [2026-07-08 07:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T13:57:02.625825+00:00) | fail streak: 227 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 07:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 10:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 87439s - kill+relaunch
- [07-08 10:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 87739s - kill+relaunch

### BROKEN: self-check 2026-07-08T10:09:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 10:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 88039s - kill+relaunch
- [07-08 10:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 88339s - kill+relaunch
- [07-08 10:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 88639s - kill+relaunch
- [07-08 10:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 88939s - kill+relaunch

- [2026-07-08 08:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T14:27:02.621665+00:00) | fail streak: 228 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 08:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 10:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 89239s - kill+relaunch
- [07-08 10:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 89539s - kill+relaunch

### BROKEN: self-check 2026-07-08T10:39:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 10:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 89839s - kill+relaunch
- [07-08 10:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 90139s - kill+relaunch
- [07-08 10:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 90439s - kill+relaunch
- [07-08 10:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 90739s - kill+relaunch

- [2026-07-08 08:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T14:57:02.845870+00:00) | fail streak: 229 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 08:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 11:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 91039s - kill+relaunch
- [07-08 11:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 91339s - kill+relaunch

### BROKEN: self-check 2026-07-08T11:09:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 11:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 91639s - kill+relaunch
- [07-08 11:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 91939s - kill+relaunch
- [07-08 11:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 92239s - kill+relaunch
- [07-08 11:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 92539s - kill+relaunch

- [2026-07-08 09:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T15:27:02.721710+00:00) | fail streak: 230 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 09:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 11:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 92839s - kill+relaunch
- [07-08 11:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 93139s - kill+relaunch

### BROKEN: self-check 2026-07-08T11:39:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 11:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 93439s - kill+relaunch
- [07-08 11:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 93739s - kill+relaunch
- [07-08 11:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 94039s - kill+relaunch
- [07-08 11:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 94339s - kill+relaunch

- [2026-07-08 09:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T15:57:02.629699+00:00) | fail streak: 231 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 09:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 12:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 94639s - kill+relaunch
- [07-08 12:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 94939s - kill+relaunch

### BROKEN: self-check 2026-07-08T12:09:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 12:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 95239s - kill+relaunch
- [07-08 12:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 95539s - kill+relaunch
- [07-08 12:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 95839s - kill+relaunch
- [07-08 12:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 96139s - kill+relaunch

- [2026-07-08 10:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T16:27:02.570841+00:00) | fail streak: 232 consecutive fires | stage v02_source_parity pass rate dropped to 73.08% in last 24h (38/52) -- but v15 (3-source) = 98.08% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/52) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 10:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 12:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 96439s - kill+relaunch
- [07-08 12:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 96739s - kill+relaunch

### BROKEN: self-check 2026-07-08T12:39:57
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- [07-08 12:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 97039s - kill+relaunch
- [07-08 12:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 97339s - kill+relaunch
- [07-08 12:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 97639s - kill+relaunch
- [07-08 12:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 97939s - kill+relaunch

- [2026-07-08 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T16:57:03.054473+00:00) | fail streak: 233 consecutive fires | stage v02_source_parity pass rate dropped to 76.47% in last 24h (39/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 13:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 98239s - kill+relaunch
- [07-08 13:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 98539s - kill+relaunch

### BROKEN: self-check 2026-07-08T13:09:57
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 5 ENTER, 5 attempted, 0 broker-accepted. Reasons: 5x no broker response recorded
- [07-08 13:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 98839s - kill+relaunch
- [07-08 13:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 99139s - kill+relaunch
- [07-08 13:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 99439s - kill+relaunch
- [07-08 13:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 99739s - kill+relaunch

- [2026-07-08 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T17:27:02.662551+00:00) | fail streak: 234 consecutive fires | stage v02_source_parity pass rate dropped to 76.47% in last 24h (39/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 13:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 100039s - kill+relaunch
- [07-08 13:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 100339s - kill+relaunch

### BROKEN: self-check 2026-07-08T13:39:57
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded
- [07-08 13:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 100639s - kill+relaunch
- [07-08 13:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 100939s - kill+relaunch
- [07-08 13:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 101239s - kill+relaunch
- [07-08 13:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 101539s - kill+relaunch

- [2026-07-08 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T17:57:02.646041+00:00) | fail streak: 235 consecutive fires | stage v02_source_parity pass rate dropped to 76.47% in last 24h (39/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 14:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 101839s - kill+relaunch
- [07-08 14:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 102139s - kill+relaunch

### BROKEN: self-check 2026-07-08T14:09:57
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded
- [07-08 14:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 102439s - kill+relaunch
- [07-08 14:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 102739s - kill+relaunch
- [07-08 14:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 103039s - kill+relaunch
- [07-08 14:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 103339s - kill+relaunch

- [2026-07-08 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T18:27:02.724611+00:00) | fail streak: 236 consecutive fires | stage v02_source_parity pass rate dropped to 76.47% in last 24h (39/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 14:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 103639s - kill+relaunch
- [07-08 14:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 103939s - kill+relaunch

### BROKEN: self-check 2026-07-08T14:39:57
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded
- [07-08 14:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 104239s - kill+relaunch
- [07-08 14:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 104539s - kill+relaunch
- [07-08 14:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 104839s - kill+relaunch
- [07-08 14:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 105139s - kill+relaunch

- [2026-07-08 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T18:57:02.610480+00:00) | fail streak: 237 consecutive fires | stage v02_source_parity pass rate dropped to 76.47% in last 24h (39/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 15:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 105439s - kill+relaunch
- [07-08 15:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 105739s - kill+relaunch

### BROKEN: self-check 2026-07-08T15:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded
- [07-08 15:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 106039s - kill+relaunch
- [07-08 15:15 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 106339s - kill+relaunch
- [07-08 15:20 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 106639s - kill+relaunch
- [07-08 15:25 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 106939s - kill+relaunch

- [2026-07-08 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T19:27:02.692254+00:00) | fail streak: 238 consecutive fires | stage v02_source_parity pass rate dropped to 78.43% in last 24h (40/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 15:30 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 107239s - kill+relaunch
- [07-08 15:35 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 107539s - kill+relaunch

### BROKEN: self-check 2026-07-08T15:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded
- [07-08 15:40 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 107839s - kill+relaunch
- [07-08 15:45 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 108139s - kill+relaunch
- [07-08 15:50 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 108439s - kill+relaunch
- [07-08 15:55 ET] TvWatchdog: tv=relaunch_kill heartbeat=fresh TV up but CDP dead for 108739s - kill+relaunch

- [2026-07-08 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T19:57:02.495689+00:00) | fail streak: 239 consecutive fires | stage v02_source_parity pass rate dropped to 80.39% in last 24h (41/51) -- but v15 (3-source) = 98.04% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log
- [07-08 16:00 ET] TvWatchdog: tv=relaunch_kill heartbeat=na TV up but CDP dead for 109039s - kill+relaunch

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-08T20:00:16+00:00
- task: eod-summary
- date_et: 2026-07-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-08T16:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T20:27:03.599887+00:00) | fail streak: 240 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### BROKEN: self-check 2026-07-08T16:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-08T20:45:14+00:00
- task: analyst
- date_et: 2026-07-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-08 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T20:57:03.625372+00:00) | fail streak: 241 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-08 21:00:02] gym-session (2026-07-08) → **RED** :: see `automation\state\gym-scorecard-2026-07-08.json`
### BROKEN: self-check 2026-07-08T17:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T21:27:03.581572+00:00) | fail streak: 242 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-08T21:30:20+00:00
- task: manager
- date_et: 2026-07-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-08T17:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 15:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T21:57:03.553460+00:00) | fail streak: 243 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 15:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### BROKEN: self-check 2026-07-08T18:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T22:27:03.482709+00:00) | fail streak: 244 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log


### BROKEN: self-check 2026-07-08T18:39:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T22:57:03.995903+00:00) | fail streak: 245 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### BROKEN: self-check 2026-07-08T19:09:56
- FILL-FUNNEL PLACEMENT BROKEN[core:bold]: 4 ENTER, 4 attempted, 0 broker-accepted. Reasons: 4x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[core:safe]: 9 ENTER, 9 attempted, 0 broker-accepted. Reasons: 9x no broker response recorded

- [2026-07-08 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T23:27:04.125981+00:00) | fail streak: 246 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (42/51) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/51) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T19:39:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-08T23:57:05.103363+00:00) | fail streak: 247 consecutive fires | stage v02_source_parity pass rate dropped to 82.0% in last 24h (41/50) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T20:09:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 18:27:12] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T00:27:14.501010+00:00) | fail streak: 248 consecutive fires | stage v02_source_parity pass rate dropped to 82.0% in last 24h (41/50) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/50) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 18:27:12] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T20:39:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 18:57:03] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T00:57:16.245566+00:00) | fail streak: 249 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 18:57:03] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T21:09:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T01:27:05.099182+00:00) | fail streak: 250 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T21:39:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T01:57:03.849182+00:00) | fail streak: 251 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T22:09:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T02:27:03.875455+00:00) | fail streak: 252 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T22:39:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T02:57:03.476093+00:00) | fail streak: 253 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### DEGRADED: self-check 2026-07-08T23:09:56
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T03:27:03.666356+00:00) | fail streak: 254 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

### WARN: spend-summary threshold breach
- ts: 2026-07-09T03:30:29+00:00
- date_et: 2026-07-08
- total: $1452.15 (threshold $30.00)
- claude: $1452.07  minimax: $0.04
- claude_sessions: 27

### DEGRADED: self-check 2026-07-08T23:40:05
- FILL-FUNNEL RULE-BLOCKED[core:bold]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x bold: 4 day-trades in 5d at equity $1,963 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 9 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 9x safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-08 22:27:22] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T04:28:34.046264+00:00) | fail streak: 256 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-08 22:27:22] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-08.log

- [2026-07-09 01:27:13] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T07:27:21.808666+00:00) | fail streak: 262 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 01:27:13] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 01:57:18] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T07:58:01.644339+00:00) | fail streak: 263 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 01:57:18] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 02:27:13] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T08:27:20.019284+00:00) | fail streak: 264 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 02:27:13] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 02:57:07] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T08:57:16.901636+00:00) | fail streak: 265 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 02:57:07] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 03:27:15] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T09:27:33.604242+00:00) | fail streak: 266 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 03:27:15] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 03:57:10] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T09:57:49.330323+00:00) | fail streak: 267 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 03:57:10] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 04:00:24] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-09 04:00:24] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-09.md

- [2026-07-09 04:27:10] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T10:27:50.710286+00:00) | fail streak: 268 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 04:27:10] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 04:57:06] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T10:57:32.979595+00:00) | fail streak: 269 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 04:57:06] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 05:27:29] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T11:27:49.120719+00:00) | fail streak: 270 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 05:27:29] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 05:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T11:57:04.114370+00:00) | fail streak: 271 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 05:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 06:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T12:27:03.840726+00:00) | fail streak: 272 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 06:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### BROKEN: premarket 2026-07-09
- PREMARKET SILENT FAILURE: claude exit=1 but today-bias.date=2026-07-08 != today 2026-07-09 (no fresh bias written). Engine would open on a STALE bias.


### DEGRADED: self-check 2026-07-09T08:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 06:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T12:57:03.787447+00:00) | fail streak: 273 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 06:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 09:05 ET] SHIPPED G11 level-memory wire -- refresh_levels_intraday now UNIONs the shadow multi-day memory map into key-levels.json so heartbeat_core sees J-called flip levels. VERIFIED: 747.13 + 747.93 in the live consumer active+multi as resistance (memory_merged=6); persisted across the 08:58 refresher write. Flag: params.level_memory_live_merge=true. Guard: test_refresh_levels_intraday.py G11 24/24 + curated safety-gate PASS + KeyLevelsModel + check_level_integrity GREEN. Revert: set level_memory_live_merge=false (merge no-ops). commit 0aa4ef9.

### DEGRADED: self-check 2026-07-09T09:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 07:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T13:27:03.778152+00:00) | fail streak: 274 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 07:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T09:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 07:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T13:57:02.553608+00:00) | fail streak: 275 consecutive fires | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 07:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T10:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 08:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T14:27:02.509379+00:00) | fail streak: 276 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 08:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T10:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 08:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T14:57:02.467670+00:00) | fail streak: 277 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 08:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T11:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 09:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T15:27:02.486823+00:00) | fail streak: 278 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 09:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T11:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 09:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T15:57:02.706240+00:00) | fail streak: 279 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 09:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T12:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 10:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T16:27:02.486772+00:00) | fail streak: 280 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 10:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T12:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T16:57:02.910738+00:00) | fail streak: 281 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T13:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 11:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T17:27:03.728454+00:00) | fail streak: 282 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 11:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T13:39:59
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 11:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T17:57:03.142662+00:00) | fail streak: 283 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 11:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T14:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 12:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T18:27:06.509676+00:00) | fail streak: 284 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 12:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T14:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 12:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T18:57:04.030084+00:00) | fail streak: 285 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 12:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T15:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 13:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T19:27:03.148638+00:00) | fail streak: 286 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 13:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T15:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-09 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T19:57:03.350050+00:00) | fail streak: 287 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-09T20:01:30+00:00
- task: eod-summary
- date_et: 2026-07-09
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-09T16:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 14:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T20:27:04.536862+00:00) | fail streak: 288 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 14:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T16:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-09T20:45:33+00:00
- task: analyst
- date_et: 2026-07-09
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-09 14:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T20:57:04.428442+00:00) | fail streak: 289 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 14:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 21:00:02] gym-session (2026-07-09) → **RED** :: see `automation\state\gym-scorecard-2026-07-09.json`
### DEGRADED: self-check 2026-07-09T17:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 15:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T21:27:04.185769+00:00) | fail streak: 290 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 15:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-09T21:30:59+00:00
- task: manager
- date_et: 2026-07-09
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-09T17:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 15:57:03] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T21:57:08.521619+00:00) | fail streak: 291 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 15:57:03] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T18:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T22:27:04.919484+00:00) | fail streak: 292 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T18:39:57
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 16:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T22:57:04.382937+00:00) | fail streak: 293 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 16:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T19:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 17:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T23:27:04.947589+00:00) | fail streak: 294 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 17:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T19:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 17:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-09T23:57:04.641362+00:00) | fail streak: 295 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 17:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T20:09:57
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 18:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T00:27:04.001431+00:00) | fail streak: 296 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 18:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T20:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T00:57:03.862279+00:00) | fail streak: 297 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T21:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T01:27:03.860251+00:00) | fail streak: 298 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T21:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T01:57:05.499925+00:00) | fail streak: 299 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T22:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T02:27:04.058739+00:00) | fail streak: 300 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-09T22:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T02:57:03.329181+00:00) | fail streak: 301 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### DEGRADED: self-check 2026-07-09T23:09:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T03:27:04.228075+00:00) | fail streak: 302 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

### WARN: spend-summary threshold breach
- ts: 2026-07-10T03:30:08+00:00
- date_et: 2026-07-09
- total: $281.77 (threshold $30.00)
- claude: $281.77  minimax: $0.00
- claude_sessions: 14

### DEGRADED: self-check 2026-07-09T23:39:56
- PREMARKET STALE: today-bias.json date=2026-07-08 != today 2026-07-09 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:46 ENTER_BULL ?', '15:47 ENTER_BULL ?', '15:48 ENTER_BULL ?']

- [2026-07-09 21:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T03:57:03.334797+00:00) | fail streak: 303 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 21:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 22:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T04:27:02.529448+00:00) | fail streak: 304 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 22:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 22:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T04:57:02.292995+00:00) | fail streak: 305 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 22:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 23:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T05:27:01.970838+00:00) | fail streak: 306 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 23:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-09 23:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T05:57:01.914103+00:00) | fail streak: 307 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-09 23:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-09.log

- [2026-07-10 00:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T06:27:01.785324+00:00) | fail streak: 308 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 00:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 00:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T06:57:01.789347+00:00) | fail streak: 309 consecutive fires | stage v02_source_parity pass rate dropped to 83.67% in last 24h (41/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 00:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 01:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T07:27:01.866460+00:00) | fail streak: 310 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 01:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 01:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T07:57:01.868525+00:00) | fail streak: 311 consecutive fires | stage v02_source_parity pass rate dropped to 85.71% in last 24h (42/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 01:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 02:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T08:27:01.859564+00:00) | fail streak: 312 consecutive fires | stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 02:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 02:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T08:57:01.677093+00:00) | fail streak: 313 consecutive fires | stage v02_source_parity pass rate dropped to 89.8% in last 24h (44/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 02:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 03:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T09:27:01.740467+00:00) | fail streak: 314 consecutive fires | stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 03:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 03:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T09:57:01.675791+00:00) | fail streak: 315 consecutive fires | stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 03:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 04:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-10 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-10 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-10.md

- [2026-07-10 04:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T10:27:01.735077+00:00) | fail streak: 316 consecutive fires | stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 04:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 04:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T10:57:01.711653+00:00) | fail streak: 317 consecutive fires | stage v02_source_parity pass rate dropped to 89.8% in last 24h (44/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 04:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 05:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T11:27:01.740319+00:00) | fail streak: 318 consecutive fires | stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 05:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 05:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T11:57:01.682528+00:00) | fail streak: 319 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 05:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 06:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T12:27:01.754152+00:00) | fail streak: 320 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 06:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 06:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T12:57:01.823243+00:00) | fail streak: 321 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 06:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T13:27:01.882633+00:00) | fail streak: 322 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T13:57:01.938315+00:00) | fail streak: 323 consecutive fires | stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T10:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T14:27:01.794843+00:00) | fail streak: 324 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T10:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T14:57:02.000996+00:00) | fail streak: 325 consecutive fires | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T11:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T15:27:02.066683+00:00) | fail streak: 326 consecutive fires | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T11:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T15:57:01.977013+00:00) | fail streak: 327 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T12:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T16:27:01.840846+00:00) | fail streak: 328 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T12:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 10:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T16:57:02.421852+00:00) | fail streak: 329 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 10:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T13:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T17:27:02.926726+00:00) | fail streak: 330 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T13:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 11:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T17:57:02.971770+00:00) | fail streak: 331 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 11:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T14:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 12:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T18:27:03.027640+00:00) | fail streak: 332 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 12:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T14:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 12:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T18:57:03.032707+00:00) | fail streak: 333 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 12:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T15:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 13:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T19:27:02.998598+00:00) | fail streak: 334 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 13:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T15:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 13:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T19:57:02.935711+00:00) | fail streak: 335 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 13:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-10T20:00:33+00:00
- task: eod-summary
- date_et: 2026-07-10
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-10T16:09:57
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 14:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T20:27:03.025516+00:00) | fail streak: 336 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 14:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T16:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-10T20:45:15+00:00
- task: analyst
- date_et: 2026-07-10
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-10 14:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T20:57:03.062436+00:00) | fail streak: 337 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 14:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 21:00:01] gym-session (2026-07-10) → **RED** :: see `automation\state\gym-scorecard-2026-07-10.json`
### BROKEN: self-check 2026-07-10T17:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 15:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T21:27:03.000166+00:00) | fail streak: 338 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 15:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-10T21:30:25+00:00
- task: manager
- date_et: 2026-07-10
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### BROKEN: self-check 2026-07-10T17:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 15:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T21:57:03.135459+00:00) | fail streak: 339 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 15:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T18:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 16:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T22:27:03.648884+00:00) | fail streak: 340 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 16:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T18:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 16:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T22:57:03.613482+00:00) | fail streak: 341 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 16:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T19:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 17:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T23:27:03.738496+00:00) | fail streak: 342 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 17:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T19:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 17:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-10T23:57:03.215556+00:00) | fail streak: 343 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 17:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T20:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 18:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T00:27:03.475690+00:00) | fail streak: 344 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 18:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T20:40:00
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 18:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T00:57:03.509167+00:00) | fail streak: 345 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 18:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T21:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 19:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T01:27:04.102533+00:00) | fail streak: 346 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 19:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T21:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 19:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T01:57:03.738200+00:00) | fail streak: 347 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 19:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T22:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 20:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T02:27:03.571919+00:00) | fail streak: 348 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 20:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T22:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 20:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T02:57:03.155037+00:00) | fail streak: 349 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 20:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### BROKEN: self-check 2026-07-10T23:09:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 21:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T03:27:03.329155+00:00) | fail streak: 350 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 21:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

### WARN: spend-summary threshold breach
- ts: 2026-07-11T03:30:37+00:00
- date_et: 2026-07-10
- total: $117.90 (threshold $30.00)
- claude: $117.86  minimax: $0.04
- claude_sessions: 8

### BROKEN: self-check 2026-07-10T23:39:56
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:risky-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-1]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded
- FILL-FUNNEL PLACEMENT BROKEN[fleet:safe-3]: 1 ENTER, 1 attempted, 0 broker-accepted. Reasons: 1x no broker response recorded

- [2026-07-10 21:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T03:57:03.038984+00:00) | fail streak: 351 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 21:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 22:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T04:27:03.638534+00:00) | fail streak: 352 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 22:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 22:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T04:57:03.283154+00:00) | fail streak: 353 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 22:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 23:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T05:27:03.644799+00:00) | fail streak: 354 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 23:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-10 23:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T05:57:03.043894+00:00) | fail streak: 355 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-10 23:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-10.log

- [2026-07-11 00:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T06:27:03.336045+00:00) | fail streak: 356 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 00:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 00:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T06:57:03.391017+00:00) | fail streak: 357 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 00:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 01:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T07:27:03.351756+00:00) | fail streak: 358 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 01:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 01:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T07:57:03.043187+00:00) | fail streak: 359 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 01:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 02:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T08:27:03.498470+00:00) | fail streak: 360 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 02:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 02:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T08:57:03.399852+00:00) | fail streak: 361 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 02:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 03:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T09:27:03.407304+00:00) | fail streak: 362 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 93.75% in last 24h (45/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 03:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 03:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T09:57:03.217464+00:00) | fail streak: 363 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 91.67% in last 24h (44/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 03:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-11 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-11.md

- [2026-07-11 04:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T10:27:03.490218+00:00) | fail streak: 364 consecutive fires | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 89.58% in last 24h (43/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 04:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 04:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T10:57:03.107665+00:00) | fail streak: 365 consecutive fires | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 04:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 05:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T11:27:03.428733+00:00) | fail streak: 366 consecutive fires | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 05:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 05:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T11:57:03.074257+00:00) | fail streak: 367 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 05:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 06:27:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T12:27:03.341118+00:00) | fail streak: 368 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 06:27:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

- [2026-07-11 06:57:01] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T12:57:03.501059+00:00) | fail streak: 369 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json

- [2026-07-11 06:57:01] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

### DEGRADED: self-check 2026-07-11T09:09:56
- BROKER account safe-2 status=ACCOUNT_CLOSED (not ACTIVE) -- trades may be blocked.

- [2026-07-11 07:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-11T13:27:03.634071+00:00) | fail streak: 370 consecutive fires | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v53_setup_dispatch.live pass rate dropped to 0.0% in last 24h (0/48) :: see crypto/data/scorecards/drift_report.json
- [2026-07-11 09:47 ET] coach: RED→GREEN — root cause: v53_setup_dispatch.live's `_KNOWN_SETUP_NAMES` allowlist (crypto/validators/v53_setup_dispatch.py) never updated when `double_bottom_base_quiet` (07-01) and `bollinger_squeeze` (07-02) setups were wired into setup_dispatch.py — deterministic `names_ok=False` on every live fire since 2026-07-02 (confirmed via `python crypto/validators/v53_setup_dispatch.py`: `names_ok: false`, both unrecognized names present in results). NOT caused by tonight's Safe-2-deletion/crypto-account churn — STATUS.md shows v53 already at 0.0%/48 as of 2026-07-02 15:xx, 9 days before tonight's account work; no shared credential/account-status path touched. Fix: added both names to the allowlist. Verified fresh: `python crypto/validators/runner.py` → `SUMMARY: passed=104/104 overall_pass=True`; `python crypto/benchmarks/track_drift.py` → `CONSECUTIVE FAIL STREAK: 0`. v02_source_parity (83.33%, self-diagnosed single-provider artifact, v15 3-source=100%) and v12_multi_timeframe.live (87.5%) are separate pre-existing rolling-window degradations, NOT explained by this fix — logged as CRYPTO-GYM-V02-V12-FOLLOWUP (MED) in queue.md, not chased tonight. 24h drift-window numbers will self-heal as pre-fix history ages out over the next 24h even though the fix is already live.

- [2026-07-11 07:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-11.log

### BROKEN: self-check 2026-07-11T09:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 07:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.71% in last 24h (42/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 4.08% in last 24h (2/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T10:10:02
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 10:16 ET] free-model-audit (AUDIT-HARNESS-B1): SHIPPED — reusable harness `setup/scripts/free_model_audit.py` (+ `free_model_audit_heartbeat_veto.py` adapter) that grades free-tier model decisions against ground truth instead of trusting them blindly (J 2026-07-11: "audit it every other day until we're confident in it... reusable harness framework we can benchmark and score"). First subject: heartbeat_core.py's 2-lane free-model veto gate. Grading priority: real fill P&L > counterfactual replay (reuses trade_autopsy.py's exit_shape_parity_study.replay_position mechanism against REAL OPRA bars, strike reconstructed via the same pure strike_selection.pick_strike production uses) > blind Sonnet re-judgment fallback (proven live: one real `claude --print` round-trip, 11s) > `ungraded_insufficient_data` (never fabricated). 35/35 pytest green. REAL dry-run against the actual production ledger (zero mocking): 106/106 evaluated ticks graded, 0 needed the LLM fallback — **veto-only accuracy 93.3%** (14/15 TRUE veto, 1 FALSE veto), **GO-only accuracy 67.0%** (61/91 — largely reflects the underlying strategy's own win rate, not veto-layer judgment), blended 70.8%/106pts — below the 85% confidence bar (same bar as the Nemotron shadow-model promotion standard), correctly reported as NOT YET CONFIDENT (no oversell). `Gamma_FreeModelAudit` scheduled task registered (DailyTrigger 21:00 ET, self-gates internally to every-other-day, auto-relaxes to weekly once confident), fired once for real and independently re-verified past the wscript exit-code-masking gap. Registry framework (`AUDIT_SUBJECTS`) ready for `twin_review`/`prospector`/`swarm_consult` (AUDIT-HARNESS-B2/B3) as TODO stubs, not built tonight. Read-only on every decisions.jsonl. Cost: $0 incremental (replay hits already-paid Alpaca market data; Sonnet fallback rides the Max pool, empirically 0% usage rate on the real 106-item sweep). Scorecard: analysis/free-model-audit/heartbeat-veto/2026-07-11-scorecard.md.

- [2026-07-11 08:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 6.12% in last 24h (3/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T10:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

## [2026-07-11] LESSON-AUTHOR — L199 encoded (joint participation-cascade blindness, C15 fold)

Inbox item `strategy/candidates/_lesson-inbox/2026-07-10-joint-cascade-blindness.md` processed: L199 appended to `markdown/doctrine/LESSONS-LEARNED.md` (6 fleet arms, 0 orders across 700+ signals on a trending day — components verified in isolation, no joint-cascade instrument existed). C15 row in CLAUDE.md OP-25 Lessons index updated (L07,08,09,66,95,163,180,199) + index marker bumped to "through L199 as of 2026-07-10". No matching `journal/mistakes.md` 2026-07-10 entry existed, so no cross-ref added. Inbox item deleted.

- [2026-07-11 08:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.8% in last 24h (44/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 8.16% in last 24h (4/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T11:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 09:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 10.2% in last 24h (5/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T11:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 09:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 12.24% in last 24h (6/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T12:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 10:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.8% in last 24h (44/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 14.29% in last 24h (7/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T12:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 10:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 16.33% in last 24h (8/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T13:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 11:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 18.37% in last 24h (9/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T13:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 11:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 20.41% in last 24h (10/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T14:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 12:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 22.45% in last 24h (11/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T14:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 12:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 24.49% in last 24h (12/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T15:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 13:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.76% in last 24h (43/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 26.53% in last 24h (13/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T15:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 13:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.8% in last 24h (44/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 28.57% in last 24h (14/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T16:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 14:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 30.61% in last 24h (15/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T16:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 14:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 32.65% in last 24h (16/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T17:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 15:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 34.69% in last 24h (17/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T17:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 15:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 36.73% in last 24h (18/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T18:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 16:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 38.78% in last 24h (19/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T18:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 16:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 40.82% in last 24h (20/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T19:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 17:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 42.86% in last 24h (21/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T19:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 17:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 44.9% in last 24h (22/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T20:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 18:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 46.94% in last 24h (23/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T20:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).

- [2026-07-11 18:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 48.98% in last 24h (24/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T21:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 19:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 51.02% in last 24h (25/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T21:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 19:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 53.06% in last 24h (26/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T22:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 20:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 55.1% in last 24h (27/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T22:39:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 20:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 57.14% in last 24h (28/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-11T23:09:57
- BROKER KEY STALE/REVOKED: safe-2 account-ping HTTP 401 -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-11T23:25:45
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 21:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 59.18% in last 24h (29/49) :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-07-12T03:30:38+00:00
- date_et: 2026-07-11
- total: $112.99 (threshold $30.00)
- claude: $112.99  minimax: $0.00
- claude_sessions: 3

### BROKEN: self-check 2026-07-11T23:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 21:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 61.22% in last 24h (30/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T00:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T00:10:24
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 22:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 63.27% in last 24h (31/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T00:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 22:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 65.31% in last 24h (32/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T01:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 23:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 67.35% in last 24h (33/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T01:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-11 23:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 69.39% in last 24h (34/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T02:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 00:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 71.43% in last 24h (35/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T02:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 00:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 73.47% in last 24h (36/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T03:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 01:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 75.51% in last 24h (37/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T03:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 01:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 87.76% in last 24h (43/49) | stage v53_setup_dispatch.live pass rate dropped to 77.55% in last 24h (38/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T04:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 02:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 89.8% in last 24h (44/49) | stage v53_setup_dispatch.live pass rate dropped to 79.59% in last 24h (39/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T04:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 02:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 91.84% in last 24h (45/49) | stage v53_setup_dispatch.live pass rate dropped to 81.63% in last 24h (40/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T05:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 03:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v12_multi_timeframe.live pass rate dropped to 93.88% in last 24h (46/49) | stage v53_setup_dispatch.live pass rate dropped to 83.67% in last 24h (41/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T05:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 03:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 85.71% in last 24h (42/49) :: see crypto/data/scorecards/drift_report.json

- [2026-07-12 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-12 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-12.md

### BROKEN: self-check 2026-07-12T06:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 04:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T06:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 04:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 89.8% in last 24h (44/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T07:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 05:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 91.84% in last 24h (45/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T07:39:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 05:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 93.88% in last 24h (46/49) :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T08:09:57
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 06:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.88% in last 24h (46/49) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T08:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T09:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T09:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 07:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.75% in last 24h (45/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T10:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T10:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T11:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 09:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T11:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T12:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T12:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 10:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.75% in last 24h (45/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T13:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T13:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T14:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T14:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T15:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T15:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T16:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T16:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T17:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T17:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T18:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 16:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T18:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 16:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T19:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 17:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T19:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

### BROKEN: self-check 2026-07-12T20:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 18:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: self-check 2026-07-12T20:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-11T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.

- [2026-07-12 18:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-07-12 19:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-07-12 22:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-07-13 01:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-07-13 04:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-13 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-13 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-13.md

- [2026-07-13 05:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### BROKEN: premarket 2026-07-13
- PREMARKET SILENT FAILURE: claude exit=1 but today-bias.date=2026-07-10 != today 2026-07-13 (no fresh bias written). Engine would open on a STALE bias.


### DEGRADED: self-check 2026-07-13T08:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

### DEGRADED: self-check 2026-07-13T09:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

### DEGRADED: self-check 2026-07-13T09:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

### DEGRADED: self-check 2026-07-13T10:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

### DEGRADED: self-check 2026-07-13T10:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

### DEGRADED: self-check 2026-07-13T11:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-13 09:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T11:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-13 09:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T12:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-13 10:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T12:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-13 10:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (45/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T13:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

### DEGRADED: self-check 2026-07-13T13:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

### DEGRADED: self-check 2026-07-13T14:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-13 12:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (45/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T14:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

- [2026-07-13 12:57:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T15:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade

### DEGRADED: self-check 2026-07-13T15:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-13T20:01:14+00:00
- task: eod-summary
- date_et: 2026-07-13
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-13T16:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T16:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-13T20:45:21+00:00
- task: analyst
- date_et: 2026-07-13
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-13 21:00:02] gym-session (2026-07-13) → **YELLOW** :: see `automation\state\gym-scorecard-2026-07-13.json`
### DEGRADED: self-check 2026-07-13T17:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-13T21:30:27+00:00
- task: manager
- date_et: 2026-07-13
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-13T17:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T18:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 16:27:01] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T18:39:57
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 16:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T19:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 17:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T19:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T20:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 18:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T20:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T21:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 19:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.75% in last 24h (45/48) | stage v15_three_source_parity.live pass rate dropped to 89.58% in last 24h (43/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T21:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T22:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-13 20:27:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) | stage v15_three_source_parity.live pass rate dropped to 89.58% in last 24h (43/48) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-13T22:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T23:09:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

### DEGRADED: self-check 2026-07-13T23:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-13 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 8 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:20 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 2 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 2x safe: 9 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:16 ENTER_BEAR ?', '15:17 ENTER_BEAR ?', '15:18 ENTER_BEAR ?']

- [2026-07-14 05:41:25] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-14 05:41:25] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-14 05:41:25] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-14.md
[2026-07-14 05:54:31] analyst: 1 trade audited (6 accts, 1 fill), 0 rule breaks, 3 inbox items queued (1 chef/1 lesson/1 validator) � full zero-supervision review of 07-13, see analysis/daily-brief/2026-07-13-FULL-AUDIT.md

- [2026-07-14 05:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 90.91% in last 24h (30/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) :: see crypto/data/scorecards/drift_report.json

[2026-07-14 08:11:40] CCR DESKTOP-APP LOCKOUT root-caused + FIXED (J's #1 directive this morning) -- J's Claude Desktop app got silently served local Ollama for a full workday after Monday's PC restart. Root cause (one sentence): `~/.claude/settings.json`'s global `env`/`apiKeyHelper` keys (wired 2026-07-08 "brain sovereignty," meant for automation) pointed EVERY claude entrypoint -- including J's interactive Desktop app -- at the CCR gateway, whose static fallback router (`~/.claude-code-router/config.json` Router.default) is hardcoded to ollama with ZERO Anthropic provider entry, so any cold boot leaving CCR's fuller profile stack not-yet-live still answers on port 3456 (keepalive's TCP probe reports "up") while silently serving Ollama instead of Claude. FIX: removed the global override from `~/.claude/settings.json` (Desktop app + bare `claude` CLI now hit Anthropic directly, unconditionally -- backup at `~/.claude/settings.json.pre-ccr-fix-2026-07-14.bak`); audited every claude-CLI-invoking automation script in the repo and confirmed NONE currently depends on CCR (kitchen routes direct REST to Ollama :11434 via model-roster.json, conductor/overnight-grinder explicitly request real Sonnet) so nothing broke; extended `ccr_keepalive.py` with `_check_and_fix_interactive_settings()` -- runs every 5-min fire independent of the TCP probe, auto-heals + same-day forensic backup + Discord ping if the interactive override ever comes back. LIVE-VERIFIED (not just unit-tested): killed CCR (pids 17416/14680), restarted via the exact keepalive restart command, and CCR's OWN `start` sequence re-injected the identical hijack into settings.json -- confirming this is CCR's NORMAL restart behavior, not a rare fluke, so the guard is load-bearing, not defense-in-depth theater. The very next unattended scheduled fire (5 min later, zero human input) detected the re-injected hijack, fixed it, wrote `~/.claude/settings.json.router-leak-2026-07-14.bak`, and sent a real Discord ping -- logged verbatim in `automation/state/logs/ccr-keepalive-2026-07-14.log`. New guard suite `backtest/tests/test_ccr_interactive_isolation.py` (14/14: RED-proofed detector, live acceptance check against the real settings.json, repo-wide allowlist scan proving the CCR port string appears nowhere else). heartbeat_core.py confirmed UNAFFECTED throughout (pure Python REST, no LLM/claude-CLI on the hot path). J's 10-second Monday-morning self-check: Settings -> Developer (or `cat ~/.claude/settings.json`) should show NO `apiKeyHelper` key and NO `env` key at all -- if either is back, the keepalive will self-heal within 5 min and ping automatically, but that absence is the thing to eyeball. Lesson: `strategy/candidates/_lesson-inbox/2026-07-14-ccr-boot-lockout.md`. Queue item CCR-GATEWAY-KEEPALIVE closed (was marked pending since 07-09; the 07-09 build only ever covered the automation half).

### BROKEN: premarket 2026-07-14
- PREMARKET SILENT FAILURE: claude exit=1 but today-bias.date=2026-07-10 != today 2026-07-14 (no fresh bias written). Engine would open on a STALE bias.


### BROKEN: premarket 2026-07-14
- PREMARKET SILENT FAILURE: claude exit=1 but today-bias.date=2026-07-10 != today 2026-07-14 (no fresh bias written). Engine would open on a STALE bias.


### DEGRADED: self-check 2026-07-14T08:39:56
- PREMARKET STALE: today-bias.json date=2026-07-10 != today 2026-07-14 -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.

- [2026-07-14 06:57:00] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.88% in last 24h (29/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 07:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T13:27:02.321477+00:00) | stage v02_source_parity pass rate dropped to 84.85% in last 24h (28/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 07:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T09:39:56
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 07:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T13:57:01.903426+00:00) | fail streak: 2 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 93.94% in last 24h (31/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 07:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T10:09:56
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 08:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T14:27:01.975266+00:00) | fail streak: 3 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 90.91% in last 24h (30/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 08:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T10:39:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 08:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T14:57:01.846243+00:00) | fail streak: 4 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 87.88% in last 24h (29/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 08:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T11:09:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 09:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T15:27:01.652510+00:00) | fail streak: 5 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 84.85% in last 24h (28/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 09:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T11:39:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 09:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T15:57:01.941128+00:00) | fail streak: 6 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 81.82% in last 24h (27/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 09:57:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T12:09:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 10:27:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T16:27:01.927812+00:00) | fail streak: 7 consecutive fires | stage v02_source_parity pass rate dropped to 81.82% in last 24h (27/33) | stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (30/33) | stage v53_setup_dispatch.live pass rate dropped to 78.79% in last 24h (26/33) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 10:27:00] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T12:39:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 10:57:00] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T16:57:02.670576+00:00) | fail streak: 9 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (28/34) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (32/34) | stage v53_setup_dispatch.live pass rate dropped to 73.53% in last 24h (25/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T13:09:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 1 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 1x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 11:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T17:27:03.255239+00:00) | fail streak: 10 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (28/34) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (32/34) | stage v53_setup_dispatch.live pass rate dropped to 70.59% in last 24h (24/34) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 11:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T13:39:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 11:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T17:57:03.255285+00:00) | fail streak: 11 consecutive fires | stage v02_source_parity pass rate dropped to 82.35% in last 24h (28/34) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (32/34) | stage v53_setup_dispatch.live pass rate dropped to 67.65% in last 24h (23/34) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 11:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T14:09:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 12:27:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T18:27:03.210451+00:00) | fail streak: 12 consecutive fires | stage v02_source_parity pass rate dropped to 85.29% in last 24h (29/34) | stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (32/34) | stage v53_setup_dispatch.live pass rate dropped to 64.71% in last 24h (22/34) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 12:27:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T14:39:56
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 12:57:02] crypto-harness drift RED :: latest cron fire FAILED (2026-07-14T18:57:03.781026+00:00) | fail streak: 13 consecutive fires | stage v02_source_parity pass rate dropped to 85.29% in last 24h (29/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

- [2026-07-14 12:57:02] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-07-14.log

### DEGRADED: self-check 2026-07-14T15:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 5 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 4 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 13:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.29% in last 24h (29/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T15:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-14T20:00:32+00:00
- task: eod-summary
- date_et: 2026-07-14
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-14T16:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T16:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-14T20:45:15+00:00
- task: analyst
- date_et: 2026-07-14
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000


### INFO: A3-BEAR-VIX-FLOOR-SSB task VOID -- no live gate, no OPRA grind run (2026-07-14 ~16:5x ET)
- Briefed to pre-register + SS-B-revalidate a "bear-entry VIX floor 17.30" that today's VIX 16.80
  supposedly floored. Independently re-verified (grep of backtest/lib/engine/gates.py's canonical
  15-gate list, cross-checked against core-decisions.jsonl) that this gate has ZERO live
  consumers -- it never gates a real order for either account. Corroborates VIX-DEADZONE-MAP
  (status:done, same day). No pre-registration frozen, no OPRA lane time spent, no live params
  behavior touched. Applied the flagged VIX-VESTIGIAL-KNOB-CLEANUP doc-hygiene fix instead
  (both params.json files, comment-only). Full trace: analysis/recommendations/bear-vix-floor-ssb.md.

- [2026-07-14 21:00:01] gym-session (2026-07-14) → **YELLOW** :: see `automation\state\gym-scorecard-2026-07-14.json`
### DEGRADED: self-check 2026-07-14T17:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-14T21:30:50+00:00
- task: manager
- date_et: 2026-07-14
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-14T17:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T18:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 16:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 82.35% in last 24h (28/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T18:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 16:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.41% in last 24h (27/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

## [2026-07-14 ~19:05 ET] Context-Enrichment Phase 0 — TREND-ALIGNMENT bundle producer + LOGGED-ONLY tag shipped (zero-behavior-change, no scorecard needed)

> **Answers J's 2026-07-14 question** ("how are we properly reviewing previous day levels and correlating them into our 'eyes' of the day and trends... do we cross-correlate any information before acting on signals? maybe it should be calculated beforehand and tagged onto the signal"). A same-session audit (3-agent, file:line-backed) proved the engine cross-correlates prior-day LEVELS well (`key-levels.json` -> `_read_levels` -> filters.py triggers) but never factors the multi-timeframe trend into whether/how strongly it acts — `today-bias.json`/`trendlines-live.json`/`confluence-zones.json`/BOS-CHoCH structure are all computed on a rolling cadence and left on disk UNREAD by score/gates. J's two calls: (1) v1 modulates conviction/sizing only, never a hard gate — Phase 2, later; (2) v1 scope = TREND ALIGNMENT ONLY, macro/confluence deferred.
>
> **Built (Phase 0, logged-only by construction):**
> - `setup/scripts/context_bundle_producer.py` (new) — pure `compute_trend_alignment(daily_df, hourly_df, m15_df)` runs `crypto/lib/market_structure.analyze_structure` per timeframe — the SAME structure primitive the live `structure_veto` gate already uses on today's 5m bars (`engine_cli._classify_sameday_5m`). Scoring: each TF votes +1 uptrend/-1 downtrend/0 range-unknown-unavailable; `alignment_score` = sum, sign = net lean, magnitude = stacked-agreement strength; `trend_alignment.bull/bear.aligned` = strict "ALL available TFs agree" read. `main()` pulls SPY daily(~6mo)/hourly(~3wk)/15m(~5d) via direct Alpaca REST (same un-blockable path as `heartbeat_core._fetch_spy_5m`, never TradingView MCP), writes `automation/state/context-bundle.json`, fail-open `degraded:true`+reason on any TF fetch failure. Carries the OP-27 L41 headless-stdio-redirect header verbatim (confluence_producer.py/firm_brief.py/free_model_audit.py's 2026-07-14 popup-storm fix).
> - **AMENDMENT (mid-session, J via coordinator): made `compute_trend_alignment` first-class historically-replayable so Phase 1 doesn't have to wait weeks for tagged data.** It was already architecturally pure (verified: `grep "_et_now\|datetime.now" context_bundle_producer.py` shows both only inside `_fetch_bars`/`main()`, never inside `compute_trend_alignment`/`_tf_state`/`_df_to_bars`) — this pass made the AS-OF-BOUNDED contract explicit in the docstring (a caller-truncated `bars<=T` slice reproduces exactly what a live run at T would have computed) and added 2 non-vacuous guard tests: (1) a `<=T` slice of a LONGER series matches an independently-built series that never had any future rows at all, at 4 different cutoffs; (2) truncation is proven NECESSARY (not cosmetic) — the same series left un-truncated reads a different `n_bars`, so the no-look-ahead guarantee genuinely lives in the caller's slicing discipline, not hidden self-truncation. Per-TF raw states (trend/confidence/trend_basis/available/n_bars/reason) were already emitted, not just the aggregate score — Phase 1 can test alternative aggregations without re-deriving. Fetch (`_fetch_bars`) was already architecturally separate from the pure math. All 3 amendment asks were either already true by construction or closed this pass — nothing deferred.
> - `setup/scripts/heartbeat_core.py` (surgical, 2 tag lines + 1 helper, +50/-1 lines) — new `_read_context_bundle()` (cloned from `_read_levels`'s disk-read pattern, `CONTEXT_BUNDLE_STALE_MIN=20` — a stale multi-day read is treated as absent, not ground truth) called once in `_build_payload`'s `bar_ctx` literal (~L479, now `bar_ctx["context_bundle"]`) and tagged again onto `run_account`'s `rec` dict (~L796, `rec["context_bundle"] = bc.get("context_bundle")`) for the decision-row ledger. **PURITY VERIFIED:** `grep -rn "context_bundle" backtest/lib/engine/engine_cli.py backtest/lib/engine/score.py backtest/lib/engine/gates.py backtest/lib/filters.py` → zero matches — `build_bar_context` reads only its own named allowlist off `bar_ctx`, so `score_bar`/`evaluate_gates`/`_derive_tier` never see this key. Zero-behavior-change by construction, not by convention.
> - `setup/scripts/install-context-bundle.ps1` (new) — registers `Gamma_ContextBundle`, cloned from `install-futures-mirror.ps1`'s verified-live pattern (wscript -> `run_exe_hidden.vbs` -> `backtest\.venv\Scripts\pythonw.exe` -> `context_bundle_producer.py --once`, `-Once`+5-min `RepetitionInterval`+6h30m `RepetitionDuration` spanning 09:30-16:00 ET, never a one-shot TimeTrigger). Registered in `automation/state/SCHEDULED-TASKS.md`.
> - `backtest/tests/test_context_bundle_producer.py` (new, **14 tests**) — aligned-up/-down score +3/-3 + `aligned:true`, mixed nets to the SIGNED sum not the max (2-up-1-down = +1, `aligned:false`), full disagreement nets to 0, missing/empty/too-short timeframe degrades `available:false` and contributes 0 (never crashes, never fabricates a trend), malformed rows skipped not fatal, 2 no-I/O tests (`builtins.open`/`urllib.request.urlopen` monkeypatched to raise), and 2 no-look-ahead tests (the amendment).
> - `backtest/tests/test_context_bundle_tag_no_behavior_change.py` (new, 6 tests) — THE zero-behavior-change proof: `_build_payload`+`_engine_verdict` (real wiring, no mocks) produce a byte-identical verdict whether `context-bundle.json` is absent/fresh/stale on disk; `CONTEXT_BUNDLE_STALE_MIN` boundary pinned exact; `_read_context_bundle` fail-open on missing/malformed/no-timestamp/unparseable-timestamp; `run_account`'s `rec["context_bundle"]` tag verified present-vs-absent with every OTHER `rec` field byte-identical (ENTER_BEAR + HOLD verdicts), and the logged ledger row proven to carry the same bundle the returned `rec` does. **RED-PROOFED live this session:** temporarily added `result["bear_score"] += context_bundle["alignment_score"]` inside `_engine_verdict`, re-ran the wiring test — FAILED exactly as expected (`bear_score`: 6 != 9, absent vs present), then reverted (`git diff` after revert shows only the 3 intended additions, zero residue) and reconfirmed green.
>
> **Verification (OP-33, quoting real checks this session):**
> - `python setup/scripts/context_bundle_producer.py --once` against tonight's live tape: `alignment_score=3`, `degraded=false`, all 3 timeframes `uptrend` (daily conf=0.733/130 bars, hourly conf=0.8/134 bars, m15 conf=0.867/144 bars), `trend_alignment.bull.aligned=true`. File written: `automation/state/context-bundle.json` (confirmed via `ls -la`, timestamp matches the run).
> - `backtest/tests/test_context_bundle_producer.py` + `test_context_bundle_tag_no_behavior_change.py`: **20/20 passed** (14 + 6, includes the amendment's 2 new no-look-ahead tests).
> - Targeted regression, the files most directly touched (`test_heartbeat_core_no_trade_window.py`, `test_trigger_level_exact_provenance.py`, `test_g6_vix_intraday_feed.py`, `test_structure_veto_classifier_live.py`, `test_structure_veto.py`): **74/74 passed**.
> - **Full heartbeat_core/engine_cli-adjacent sweep, slow-inclusive** (`money_path`/`gate_provenance`/`g4_extra_setup`/`entry_floor`/`graduated_guards`/`structure_veto`/`heartbeat_core`/`trigger_level_exact`/`g6_vix`, no `-m` exclusion — includes `test_graduated_guards.py`'s 9 data-heavy backtests, 733.5s / 12m13s): **335 passed, 1 skipped, 1 failed**. The 1 failure (`test_graduated_guards.py::test_free_model_cost_estimate_is_zero`) is a **pre-existing, unrelated `run_minimax` module-caching test-order flake** — isolated and proven NOT caused by this session: passes alone (1/1 in isolation), the module genuinely has `_estimate_cost` at line 220 (`git diff --stat -- setup/scripts/run_minimax.py` is empty — untouched this session), and the failure reproduces IDENTICALLY with this session's 2 new test files explicitly `--ignore`d from collection (`money_path or gate_provenance or g4_extra_setup or entry_floor or graduated_guards` -m "not slow" --ignore=test_context_bundle_producer.py --ignore=test_context_bundle_tag_no_behavior_change.py` → same single failure, 182 passed/1 skipped) — a pre-existing suite-wide collection-order bug, not a regression from this build.
> - Task registration: `Get-ScheduledTask -TaskName Gamma_ContextBundle` → `State=Ready`. Reaper-exemption confirmed by construction (`grep Win32_Process setup/scripts/_shared.ps1` → the reaper's Name filter is `claude.exe/node.exe/python.exe/uv.exe/uvx.exe` — `pythonw.exe` is not in it). Fired twice independently: (1) `Start-ScheduledTask -TaskName Gamma_ContextBundle` → `LastTaskResult=0`; (2) bypassing wscript's exit-code masking (Gamma_EodFlattenCore lesson) — launched the EXACT registered `backtest\.venv\Scripts\pythonw.exe ... context_bundle_producer.py --once` directly and read its OP-27-L41-redirected stdout log (`automation/state/logs/context-bundle-producer.stdout.log`): full bundle JSON present, `alignment_score=3`, empty stderr log — proves the real process ran end-to-end, not just wscript exiting 0.
> - Decision-row carrying the field: proven via the `run_account` guard tests above (mocked engine, real tagging code path) rather than waiting for a live tick — `Gamma_ContextBundle` only just registered (`NextRunTime: 2026-07-15 09:30`), so no real `core-decisions.jsonl` row exists yet tonight; tomorrow's first RTH tick will carry a live `context_bundle` value once the 09:30 ET task fire has run at least once.
>
> **Deferred (per plan, not v1):** Phase 1 (`backtest/tools/trend_alignment_correlation_study.py` — walk-forward correlation study measuring whether alignment predicts real-fill outcomes, now unblocked by the amendment's as-of-bounded contract; a KILL here is a valid, valuable result) and Phase 2 (wiring a validated read into conviction/sizing at the `rec` seam, never inside `engine_cli`) are NOT built — this ship is Phase 0 only, by design (measure before wiring).
>
> **Revert (one line + one task):** remove the two tag lines in `setup/scripts/heartbeat_core.py` (`bar_ctx["context_bundle"] = _read_context_bundle()` in `_build_payload`, and `"context_bundle": bc.get("context_bundle")` in `run_account`'s `rec` dict — the `_read_context_bundle`/`CONTEXT_BUNDLE_STALE_MIN` helper can stay, it's inert without a caller) + `Unregister-ScheduledTask -TaskName "Gamma_ContextBundle" -Confirm:$false`. No params/doctrine/order-path changes to revert — this phase never touched any of those.
>
> Zero orders placed. Zero live params/doctrine edits. Ships without a trading scorecard per the mission brief (logged-only = no trades change = nothing to A/B).

### DEGRADED: self-check 2026-07-14T19:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 17:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.47% in last 24h (26/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T19:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T20:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T20:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.63 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 18:57:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.41% in last 24h (27/34) -- but v15 (3-source) = 97.06% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T21:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 19:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.41% in last 24h (27/34) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T21:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T22:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

- [2026-07-14 20:27:02] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 82.35% in last 24h (28/34) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | stage v53_setup_dispatch.live pass rate dropped to 61.76% in last 24h (21/34) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-14T22:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-14T23:09:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### WARN: spend-summary threshold breach
- ts: 2026-07-15T03:30:33+00:00
- date_et: 2026-07-14
- total: $342.47 (threshold $30.00)
- claude: $342.43  minimax: $0.04
- claude_sessions: 17

### DEGRADED: self-check 2026-07-14T23:39:56
- FILL-FUNNEL ENTER AFTER CEILING[core:bold]: 6 ENTER after 15:00 ET: ['15:02 ENTER_BEAR ?', '15:03 ENTER_BEAR ?', '15:04 ENTER_BEAR ?']
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 4 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 4x safe: 7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade
- FILL-FUNNEL ENTER AFTER CEILING[core:safe]: 5 ENTER after 15:00 ET: ['15:06 ENTER_BEAR ?', '15:07 ENTER_BEAR ?', '15:08 ENTER_BEAR ?']
- PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-15.

### DEGRADED: self-check 2026-07-15T00:09:56
- PDT-BLOCKED[safe]: 5/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-16.

- [2026-07-14 22:27:02] crypto-harness drift RED :: stage v53_setup_dispatch.live pass rate dropped to 62.86% in last 24h (22/35) :: see crypto/data/scorecards/drift_report.json

### DEGRADED: self-check 2026-07-15T00:39:56
- PDT-BLOCKED[safe]: 5/3 day-trades used (rolling 5bd) at equity $1,746.56 -- blocks a 4th day-trade until it rolls off 2026-07-16.
