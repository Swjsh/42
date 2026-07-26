## [2026-07-26 ~15:47-16:25 ET] OK -- conductor (WEEKEND): AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS closed, commit pending

> **STAGE 0/1:** ET confirmed 15:47 Sunday (market closed, weekend mode). Budget gate PROCEED
> ($20.35/$30, 3/4 fires -- this fire pushes toward the daily cap). `engine-health.json`
> GREEN/YELLOW (14 checks, 0 RED, gex_archive 1-day-stale YELLOW non-critical). `task_scorer.py`
> top item `TWIN-DOCTRINE-FIRST-DEPLOY` (MED, 6.5) is still J's REVOKE surface, propose-only,
> correctly not picked (Nth fire confirming). Next 3 tied at 5.0: `CATASTROPHE-CAP-WIDEN-WATCH`
> and `TRENDLINE-TIGHT-EXIT-ACCRETE` are both accrue-then-decide watch-only items (no new
> action per multiple prior fires' own notes); `OFF-BOX-DEADMAN-SWITCH` is a real but separate
> monitoring-nicety build. Per STAGE-1 priority-3 (self-audit gaps outrank queue HIGH), read
> `analysis/self-audit/new-gaps-flagged.md`'s newest un-triaged batch (2026-07-25T17:32:35, 10
> items) and found one of its 8 real (non-scaffold) lines pointed at a still-open, concretely
> actionable queue item: `AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS` (MED) -- picked it, since closing
> it closes BOTH the queue item and the matching self-audit gap in one shot (compound, not
> accumulate).

> **What I found + built:** `audit_scheduled_tasks.py` only ever knew about `Gamma_*` Windows
> Task Scheduler entries -- Claude-native scheduled skills at `~/.claude/scheduled-tasks/`
> (a completely separate scheduling mechanism) were invisible to every governance surface,
> which is how `gamma-sniper-shadow-eod` (a daily **opus** fire, ~$100/mo) ran ungoverned for
> 2 months before the 2026-07-25 cost pass caught and retired it by hand. Built
> `_claude_native_tasks()` (enumerates `~/.claude/scheduled-tasks/*/SKILL.md`, extracts the
> `name:` frontmatter field, falls back to the dirname) wired into `audit()` as a new
> `CLAUDE_NATIVE_TASK_UNGOVERNED` flag against a new `KNOWN_CLAUDE_NATIVE_TASKS` allowlist
> (empty by design -- both prior offenders are retired, not allowlisted; a future one must be
> reviewed + added there + given a real SCHEDULED-TASKS.md row, or retired). Deliberately scans
> ONLY the live directory, never a `-retired-*` sibling. New `claude_native_registered` count
> added to the JSON summary for visibility.

> **Verified this fire (OP-33), not claimed:** 11 new guard tests
> (`backtest/tests/test_audit_scheduled_tasks_claude_native.py`) -- RED-proofed via a scoped
> `git stash -- setup/scripts/audit_scheduled_tasks.py` (all 11 failed with the exact expected
> `AttributeError`/behavior gap against pre-fix code, `git stash pop` restored cleanly,
> re-verified 11/11 green). Ran the real script against the live box: `claude_native_registered:
> 0`, no false `CLAUDE_NATIVE_TASK_UNGOVERNED` flag (the directory is genuinely empty right now
> -- both prior offenders correctly live under the `-retired-2026-07-25` sibling, confirmed by a
> direct `ls`). Curated safety gate (`run_safety_gate.py`): 31+5 PASS. `py_compile` clean on both
> touched files.

> **Also closed the matching self-audit gap:** the 2026-07-25T17:32:35 batch in
> `analysis/self-audit/new-gaps-flagged.md` had 10 un-triaged lines; appended a DONE marker
> disposing all 10 (2 scaffold headers, 1 already-ruled, 2 already-fixed via the existing
> `conductor_budget.py` `SELF_REPORT_CORRECTION=2.2` governor, 1 tracked-but-not-yet-built
> (`OFF-BOX-DEADMAN-SWITCH`), 1 closed this fire (the Claude-native-tasks gap itself), 1 tracked
> HIGH item (`ZERO-FOR-TWELVE-POSTMORTEM`), 2 synthesis-commentary noise) -- so the batch stops
> reading as open on the next fire.

> **Scope + revert:** 3 files (`setup/scripts/audit_scheduled_tasks.py`,
> `backtest/tests/test_audit_scheduled_tasks_claude_native.py` [new], plus the queue.md +
> self-audit-gaps.md doc updates). Zero trading-path touched (no params/heartbeat_core/
> filters/CLAUDE.md) -- pure observability tooling. Revert: `git revert <this commit>`.

---

## [2026-07-26 ~00:12-00:20 ET] OK -- conductor (AFTERHOURS): DRESS-REHEARSAL false-RED root-caused + fixed, commit `e370b0dc`

> **STAGE 0/1:** ET confirmed 00:12 Sunday (market closed). Budget gate PROCEED ($10.67/$30,
> 2/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED, gex_archive 1-day-stale
> YELLOW non-critical). `self-check-last.json` verdict **BROKEN** — 2 problems: `DRESS-
> REHEARSAL RED` (fresh, un-triaged) + `ENGINE DARK ALL DAY` (already tracked as
> `OFF-BOX-DEADMAN-SWITCH`, queue.md, status:pending). Per STAGE-1 priority-2 (Engine
> RED/BROKEN flags outrank queue HIGH/self-audit-gaps/inboxes), picked the fresh
> DRESS-REHEARSAL RED to investigate + fix.

> **Root cause (confirmed, not theorized):** `Gamma_DressRehearsal` is registered
> `DaysInterval=1` (every calendar day, incl. weekends — verified via `Get-ScheduledTask`).
> Its `check3_sanity` beacon-freshness sub-check enforced a hard `<24h` threshold with
> **no weekend exemption** — unlike `engine_health.py`'s `check_sight_beacon`/
> `check_engine_core`/etc., which all carry the `market_open` -> "(market closed -- quiet
> OK)" idiom. Every Saturday/Sunday night the beacon is CORRECTLY >24h stale (last ticked
> Friday's RTH close) and the rehearsal RED'd on it forever. Tonight's artifact
> (`dress-rehearsal.json`, 2026-07-25T20:45:01, Saturday): check1/check2 (real broker
> order-acceptance + crypto round-trip) both GREEN; only `check3_sanity` RED'd, on
> "sight-beacon.json age 52.3h (must be <24h)".

> **Fix:** `check3_sanity(creds_map, next_day, *, is_weekend: bool = False)` — `main()`
> derives `is_weekend` via the canonical `et_clock.et_weekday() >= 5` (same convention as
> `is_market_hours`, no new logic invented). A stale-but-PRESENT beacon on a weekend is now
> GREEN "quiet OK"; a MISSING beacon still RED's regardless of day (genuine unknown, not
> known-quiet). 5 new guard tests (`TestCheck3SanityWeekendExemption`,
> `backtest/tests/test_dress_rehearsal.py`) — RED-proofed via a **scoped** `git stash --
> setup/scripts/dress_rehearsal.py` (single-pathspec, not tree-wide) confirming all 5 fail
> against pre-fix code with the exact expected `TypeError`/`AssertionError`, then popped
> clean. Full suite 34/34 pass. Curated pre-commit safety gate (5 suites) PASS.

> **Verified this fire (OP-33), not claimed:** re-ran `dress_rehearsal.py` live post-fix
> (real paper-broker round-trips, $0/idempotent/self-cleaning per its own docstring) —
> `overall=GREEN` (was RED), all 4 checks GREEN including `check3_sanity`. Re-ran
> `self_check.py` — `DRESS-REHEARSAL RED` problem gone; only the already-tracked
> `ENGINE DARK ALL DAY` (OFF-BOX-DEADMAN-SWITCH, untouched, correctly left alone — separate
> scope) remains. Post-commit `git show e370b0dc --stat --name-status` confirms exactly the
> 2 intended files (L247 discipline).

> **Scope + revert:** 2 files (`setup/scripts/dress_rehearsal.py`, its test file). No
> trading-path touched (params/heartbeat_core/filters/placement/exit code untouched) — this
> is an observability-instrument fix (dress_rehearsal is a nightly diagnostic, not a live
> trading path). Revert: `git revert e370b0dc`.

> **Learn:** this is the SAME lexical class as engine_health.py's existing weekend/market-
> closed exemption pattern, just not applied consistently to a sibling instrument built
> later — filed `_lesson-inbox/2026-07-26-dress-rehearsal-weekend-beacon-false-red.md` for
> `lesson-author` (generalizable: any freshness/liveness check built against a producer that
> only runs during weekday RTH needs the SAME weekend/holiday exemption idiom as
> engine_health.py, not a bespoke re-derivation — check for the idiom before shipping a new
> one).

---

## [2026-07-25] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 3tr $+75.00 ($+25.00/tr, 66.7% WR) [2d/2 day+side buckets -- 3 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 24d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 1tr $+18.00 ($+18.00/tr, 100.0% WR)
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-07-25] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-17..2026-07-23), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-23). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-276.48); Bold_ATM_1+2=YELLOW ($-166.9)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-07-25 ~21:12-21:50 ET] OK -- conductor (AFTERHOURS): ZERO-FOR-TWELVE-POSTMORTEM live sample day-clustered (12 rows = 4 days), commit `9ad0a907`

> **STAGE 0/1:** ET confirmed 21:12 Saturday (market closed). Budget gate PROCEED ($22/$30,
> 2/4 fires -> this fire pushes to 3/4). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED,
> gex_archive 1-day-stale YELLOW non-critical). `task_scorer.py --top` returned
> `TWIN-DOCTRINE-FIRST-DEPLOY` again (still J's REVOKE surface, unpicked, Nth fire confirming).
> Picked up `ZERO-FOR-TWELVE-POSTMORTEM` (HIGH) again -- the prior fire's own named NOT-DONE
> step: "day-cluster the OOS trades and check how many genuinely distinct day+side buckets fed
> the sample."

> **What I found:** pulled the actual 12 CSV rows behind the "0-for-12" headline
> (`journal/trades.csv`, setup=vwap_continuation/vix_regime_dayside since 2026-07-01 arm). They
> are **4 distinct calendar days** (07-16, 07-20, 07-21, 07-22) and **4 distinct (day,side)
> buckets** -- not 12 independent trials. Two mechanisms: (a) same-day re-entries / same-signal
> TP1+runner leg splits (2026-07-20 vix_regime_dayside logged 4 rows, two sharing an IDENTICAL
> entry timestamp 09:54:19; 2026-07-21 vwap_continuation logged 2 rows both at 10:11:29); (b) on
> 2026-07-21 BOTH setups fired PUT the SAME day -- confirms in DATA the mechanism an earlier fire
> today proved in CODE (both derive `side` from the identical `session_vwap_asof` day-trend
> classifier) -- one wrong day-read counted as two setup failures.

> **Reframe (correction of surprise-magnitude, not a reversal of the disarm):** "0-for-12 at
> claimed 55-64% WR is p<1%" reframes to "0-for-4 correlated day-outcomes at the same claimed WR
> is ~1.7%-4.1%" -- still worth the disarm-and-investigate call already made, no longer a clean
> statistical-pipeline-falsification signal standing alone.

> **Graduated to code** (`backtest/autoresearch/trade_to_learn_digest.py`, commit `9ad0a907`):
> `compute_since_arm()` now reports `n_distinct_days` / `n_distinct_day_side_buckets` per setup
> + a new `cross_setup_same_day_side` field flagging when 2+ armed setups fire the same
> (date,side) -- generalizes past this one pair. `format_lines()` warns inline. 4 new guard
> tests (`backtest/tests/test_trade_to_learn_digest.py`, 13/13 pass) + fixed 1 unrelated
> pre-existing stale test (hardcoded 2026-07-18 arm-list assertion broke when today's earlier
> disarm changed params.json -- verified via `git stash` that the failure is identical with or
> without this commit, so this fix is incidental cleanup not scope creep).

> **Learn:** lesson filed
> `_lesson-inbox/2026-07-25-since-arm-fills-are-not-independent-trials.md` (generalizable:
> "N fills, X% WR" is a row count, not a trial count -- any since-arm digest needs distinct-day
> disclosure before it's used for a disarm/keep call).

> **Verified this fire (OP-33):** all dates/sides/timestamps are direct `journal/trades.csv`
> reads (quoted above), not inferred. Ran `trade_to_learn_digest.py --dry-run` post-commit --
> output matches. `pytest backtest/tests/test_trade_to_learn_digest.py -q` = 13/13 PASS. Curated
> safety gate (pre-commit hook) PASS. Post-commit `git show 9ad0a907 --stat --name-status` +
> `git status --porcelain` on touched paths confirmed clean (L247 discipline).

> **Scope + revert:** 2 files (digest script + its test file) + this STATUS entry + queue.md
> progress note + 1 new lesson-inbox item. Zero trading-path touched (no params/heartbeat_core/
> filters/CLAUDE.md). Revert: `git revert 9ad0a907`.

> **STILL OPEN (named next step):** the HISTORICAL OOS(2026) side of the original ask (day-cluster
> the 42-trade/21-trade validation-time OOS populations to quantify L174's "day+side selection"
> claim on the VALIDATION side, not the live-sample side just closed) -- needs a `detect_signals()`
> re-run over 2026 from each autoresearch script (detection only, no full sim sweep), not yet done.

> **STAGE 0/1:** ET confirmed 20:30 Saturday (market closed). Budget gate PROCEED ($22/$30, 2/4
> fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED; gex_archive 1-day-stale YELLOW,
> non-critical). `self-check-last.json` BROKEN flag is the known, already-diagnosed 2026-07-24
> off-box incident (`OFF-BOX-DEADMAN-SWITCH` queue item already tracks it; position_safe/bold
> confirmed flat, kill-switches armed-not-tripped -- nothing live-risk pending). `task_scorer.py
> --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again (still J's REVOKE surface, unchanged, Nth
> fire confirming). Picked the prior fire's own named NEXT STEP on `ZERO-FOR-TWELVE-POSTMORTEM`
> (HIGH) instead: audit whether `_b5_vix_regime_dayside.py`/`_edgehunt_vwap_continuation.py`
> source entry levels the same batch-only way as `orchestrator.run_backtest` (the mechanism that
> explained the RIDE_THE_RIBBON entry-layer gap).

> **What I found:** NO -- ruled out for both disarmed setups. Both entry triggers compute from
> `session_vwap_asof` (one shared implementation in `autoresearch/infinite_ammo_discovery.py`,
> imported verbatim by both scripts) -- a pure cumulative-VWAP-from-RTH-bars calc with zero
> `key_levels`/`key.levels` references in either file (grepped). There is no curated/memory-merged
> level source for either setup to diverge on, live vs backtest. Both scripts' exit sim is also
> `lib.simulator_real.simulate_trade_real` directly -- the SAME entry+1 convention
> `ENTRY-BAR-CONVENTION-RULING-2026-07-25.md` ruled live-faithful earlier today. So the
> entry-bar-convention / batch-vs-live-level-divergence hypothesis is now fully closed off for
> these two setups specifically (it only ever applied to the RIDE_THE_RIBBON family).

> **Leading remaining hypothesis (not new, already disclosed at arm-time):** params.json's own
> "L174 NOT INDEPENDENT / lift is largely day+side selection" caveat. vwap_continuation's arm-time
> evidence shows oos_n=42 (not tiny) -- which actually strengthens the selection-bias reading over
> a pure small-n one: if day+side was itself chosen post-hoc against the same data used to grade
> it, effective independent trials < nominal n, and 0-for-12 stops looking like p<1% surprise and
> starts looking like ordinary post-hoc-selection decay. Named the concrete next test (day-cluster
> the OOS trades, compare distinct day+side buckets vs the 0-for-12 sample) as NOT DONE -- research
> only, no engine implication either way yet.

> **Verified this fire (OP-33):** every claim above is a direct grep/read quote, not an inference
> (`session_vwap_asof` single-source import confirmed both files; zero `key_levels` hits confirmed
> both files; `simulate_trade_real` import+call confirmed both files; EDGE-HUNT-VERIFIED.json n/oos_n
> quoted directly). Zero files edited except `queue.md` (progress note) + this STATUS entry -- no
> code/trading-path touched, nothing to revert beyond the doc note.

> **Scope + revert:** 2 files (queue.md progress append, this STATUS entry). No commit needed
> (doc-only progress note on an already-tracked item) -- next fire: `git add automation/overnight/{queue.md,STATUS.md}` if J wants it committed, else it rides the next commit that touches these files.

> **STAGE 0/1:** ET confirmed 17:42 Saturday (market closed). Budget gate PROCEED ($14.30/$30,
> 1/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED, only gex_archive 1-day-stale
> YELLOW, non-critical). `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again
> (still J's REVOKE surface, unchanged). Picked `ZERO-FOR-TWELVE-POSTMORTEM` (HIGH, filed today
> with the vwap_continuation/vix_regime_dayside disarm) instead: it named a concrete, doable-now
> next step (the already-RULED `EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT` escalation pointed at
> `engine_fullhist_replay`'s entry-layer divergence -- "matched an 11:40 live fill to a 13:55
> replay entry, 2h15m apart" -- as the next suspect after partially exonerating the entry-bar
> convention itself).

> **What I found:** reproduced the raw divergence directly (`run_backtest` on 2026-07-17): the
> batch engine fires only 2 signals that day vs 4 live fills. Then found the deeper bug: the
> anchor-matcher paired on strike+side ALONE with no time bound, so it silently accepted the
> 11:40->13:55 pairing (a genuinely different signal, not a near-miss) as a PASS -- true
> trade-level fidelity on that day is **1/4, not the previously-reported 2/4**. Root cause of the
> gap itself was already disclosed pre-fire (live sources levels from a curated + multi-day
> memory-merged key-levels.json feed; `orchestrator.run_backtest` recomputes from bars only) --
> this fire's contribution is correcting the magnitude (3/4 missing, not 2/4) and killing the
> false-positive matcher class.

> **Scope discipline (OP-33, did not over-claim):** this does NOT explain the 0-for-12 directly
> -- `vwap_continuation`/`vix_regime_dayside` were validated by a DIFFERENT harness
> (`backtest/autoresearch/_b5_vix_regime_dayside.py` + siblings), not `orchestrator.run_backtest`
> (confirmed via each script's own scope disclosure + `analysis/recommendations/
> vix_regime_dayside.json#generated_by`). Named the concrete next step in queue.md: audit
> whether that autoresearch harness family has the same batch-computed-only level source.

> **Verified this fire (OP-33):** `match_entries_by_strike_side_time` extracted top-level +
> unit-tested (2 new tests: rejects the 2h15m collision, still matches an exact-time hit) --
> `test_engine_fullhist_replay.py` 7/7 fast tests pass. Curated safety gate (31+5) PASS pre- and
> post-commit. Post-commit `git show 6b7c07ac --stat --name-status` + `git status --porcelain`
> on touched paths confirmed clean (L247 discipline).

> **Learn:** filed `_lesson-inbox/2026-07-25-anchor-matcher-strike-side-only-false-positive.md`
> -- generalizable rule: any anchor/ground-truth matcher joining on a coarse key (strike+side,
> symbol, setup name) needs a time-proximity bound, or a coincidental collision silently reports
> as a false PASS.

> **Scope + revert:** 6 files (1 fix, 1 test, 2 scorecard corrections appended not overwritten,
> 1 new lesson-inbox item, 1 queue.md progress note). Zero trading-path touched (no params/
> heartbeat_core/filters/CLAUDE.md). Revert: `git revert 6b7c07ac`.

## [2026-07-25 ~14:42-15:00 ET] OK -- conductor (WEEKEND): ENGULFING-AT-STRUCTURE-TRIGGER CLOSED, commit `73902fa1`

> **STAGE 0/1:** ET confirmed 14:42 Saturday (market closed, weekend mode). Budget gate
> PROCEED ($0/$30, 0/4 fires). `engine-health.json` GREEN/YELLOW (13 checks, 0 RED,
> only gex_archive 1-day-stale YELLOW, non-critical). `task_scorer.py --top` returned
> `TWIN-DOCTRINE-FIRST-DEPLOY` (still pending J's REVOKE surface, gp-2026-07-23-twin-
> doctrine-001 -- Nth fire confirming, propose-only doctrine edit, correctly not picked).
> Next-ranked ready item: `ENGULFING-AT-STRUCTURE-TRIGGER` (HIGH) -- its own queue text
> named a concrete, doable-now next step ("frozen pre-reg <=16 cells + real-fills
> replay ... confirming the winning cell still fires on both anchor bars"), unlike the
> other MED items (`CATASTROPHE-CAP-WIDEN-WATCH`/`TRENDLINE-TIGHT-EXIT-ACCRETE`, both
> accrue-only, no new action) or `DOJO-BUILD-HANDOFF` (no TV MCP tools bound this fire).

> **What I found before building anything (avoided duplicate work):** the item has TWO
> parallel tracks. Lane-B (`edge_matrix_engulfing_at_structure.py`, commit `83dce261`,
> 2026-07-23 16:31) already ran this exact kind of frozen-pre-reg + real-fills replay
> for a DIFFERENT (one-sided-shelf) detector -- HONEST NULL, 0/12 cells, already
> committed. That did NOT close the item because Lane-A's own SHIPPED, anchor-verified
> primitive (`engulfing_at_local_cluster`, commit `8aed997a`, 2026-07-23 ~23:03) never
> got its own real-fills replay -- the queue text's "NEXT STEP" was still open.

> **Built + ran it.** Zero-fork grid adapter
> (`backtest/tools/engulfing_at_local_cluster_detector.py`) imports the registry's own
> `engulfing`/`local_extreme_cluster` predicate factories (not a re-derivation) and
> grid-sweeps their params -- verified byte-identical to the live registry predicate
> over the full 30k-bar sequence (not just the 2 anchors) before freezing the pre-reg.
> 16-cell grid (`min_touches`{3,4} x `min_body_dollars`{0,0.40,0.60,0.80} x
> `tolerance`{0.15,0.20}), same edge-matrix harness (RIBBON_RIDE exit via
> `exit_manager_walk`, 386-day frozen OPRA inventory, 4-gate+BH) as every other family.

> **Result: HONEST NULL, 0/16 cells clear the ship bar.** Both anchors fire on 6/16
> cells incl. the exact shipped config (`touch3|body0.40|tol0.20`) -- itself solidly
> negative (n=87, expectancy -$20.11/tr, total -$1,749.14, held-out -$2,314.82, 0/4
> gates). Loosening the body floor toward 0 makes it MUCH worse (-$10,201 to
> -$11,672), not better -- same "wider admits noisier reactions" shape Lane-B found
> independently. **ENGULFING-AT-STRUCTURE-TRIGGER is now CLOSED** -- both independent
> tracks born from J's 07-21/07-23 live exhibits agree: correct entry vocabulary, zero
> real-fills edge under the live exit shape. Not wired; `engulfing_at_local_cluster`
> stays registry.py discovery-only. Named next honest lever (new pre-reg, not
> attempted): the EXIT side, since both lanes only tuned entry against a fixed
> RIBBON_RIDE shape not built for this trigger's hold profile.

> **Verified this fire (OP-33):** `test_engulfing_at_local_cluster.py` 6/6 new (incl.
> byte-identical-vs-registry over the full bar sequence + C6 causality RED-proof via
> future-bar mutation). Full pattern-grammar suite 106/106 green. Curated safety gate
> (31+5) PASS pre- and post-commit (pre-commit hook ran it automatically). Post-commit
> `git show 73902fa1 --stat --name-status` + `git status --porcelain` on the touched
> paths confirmed clean (L247 discipline -- verified committed, not just staged).

> **Scope + revert:** 7 new files (detector, runner, guard tests, pre-reg + 2 results +
> 1 markdown summary) + 1 queue.md edit (closing this item). Zero trading-path touched
> (no params/heartbeat_core/filters/CLAUDE.md). Revert: `git revert 73902fa1`.

## [2026-07-23 ~23:12-23:45 ET] OK -- conductor (AFTERHOURS): EXIT-ENGINE-PARITY-RESIDUAL root-caused (91% of a $40/tr research-parity gap explained + confirmed via ablation), commit pending

> **STAGE 0/1:** ET confirmed 23:12 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again -- STILL
> `status:pending` on J's REVOKE surface (`gp-2026-07-23-twin-doctrine-001`, 6th fire confirming,
> nothing new). Self-audit gaps file: 2026-07-23's own batch already actioned earlier today, no
> new un-triaged batches. Next 3 MED items (`CATASTROPHE-CAP-WIDEN-WATCH` n=4 accrue-to-10,
> `TRENDLINE-TIGHT-EXIT-ACCRETE` shadow-accrual) confirmed still watch-only, no action possible.
> `EXIT-ENGINE-PARITY-RESIDUAL` (MED, filed 2026-07-09, re-flagged "research-diagnosis" not
> "watch-only" by the prior 2 fires but never picked) DID have a concrete, doable-now diagnosis
> step ("per-trade exit-reason diff on the 149-trade control set") -- picked it.

> **What I found:** built `backtest/tools/vwapcont_parity_diagnose.py` (per-signal diff, reuses
> `vwapcont_entry_exit_matrix.py`'s own signal-loading/prep helpers verbatim, ANALYSIS ONLY).
> Reproduced the known scorecard exactly (bar-replay $15.02/tr vs simulate_trade_real $54.73/tr,
> n=149 both -- preflight hash/version/parity all OK, confirms the diagnostic is aligned with the
> frozen study). Bucketed per-trade by (bar-replay terminal stage, sim exit_reason): the single
> biggest driver is 19/149 trades where bar-replay says `premium_stop` but sim says
> `TP1_THEN_RUNNER_*` (sum delta -$4,164 of the -$5,917 total gap); the 96 trades where both
> engines agree on the terminal mechanism still carry a consistent -$16.72/tr drag.

> **Root-caused with a controlled experiment, not hand-waved (OP-33 discipline):** code-read
> found `lib/simulator_real.py:534-535` (`spy_idx=entry_bar_idx+2` / `opt_idx=entry_idx_opt+1`)
> never checks the ENTRY bar's own high/low for a stop/TP1 -- sim's exit loop starts at the bar
> AFTER entry. `structure_stop_study.replay_structure_aware`'s `norm_bars` (every bar-replay-family
> tool's own `load_atm_bars`) start AT the entry bar itself, and the exit loop evaluates that
> SAME bar's high/low on iteration 1 -- one bar earlier than sim. **Confirmatory ablation:**
> re-ran bar-replay on the identical 149-signal population with `norm_bars[1:]` (entry bar
> excluded, matching sim's convention) -- exp $15.02 -> $58.28 vs sim $54.73, closing **91.1% of
> the $39.71/tr gap**; residual -$3.55/tr fully consistent with the two ALREADY-confirmed smaller
> mechanisms (pre-TP1 profit-lock scope ~$0.72/tr + ribbon-flip-back). This **supersedes** the
> queue item's own prior guess ("mostly ribbon-flip modeling + fill conventions") -- those are
> real but minor; the entry-bar-eligibility convention is the dominant driver by an order of
> magnitude.

> **Deliberately NOT adjudicated this fire (escalated instead):** which convention -- bar-replay's
> entry-bar-inclusion (precedented by `t4_exit_matrix`/`structure_stop_study`) vs
> `simulate_trade_real`'s entry-bar-exclusion (the ratified ship-gate C1 authority's own
> long-standing convention) -- is more faithful to live risk exposure is a genuine real-money-
> adjacent judgment call per the conductor's own FABLE-ESCALATION criterion (a wrong guess here
> could plausibly move real money or ship a validated-looking edge that isn't). Filed
> `FABLE-ESCALATION: EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT` (queue.md, HIGH) for a top-tier
> session to adjudicate + scope whether any already-ratified study's conclusion (not just its
> absolute $/tr) is sensitive to this.

> **Verified this fire (OP-33):** preflight hash/version/parity all matched the frozen
> pre-registration both runs (no population drift). `test_vwapcont_entry_exit_matrix.py` 23/23
> green (nothing in the existing study touched -- new script only imports its functions).
> `py_compile` clean. Re-ran the diagnostic script twice (once without, once with the
> confirmatory ablation) -- identical base numbers both times ($15.02/$54.73/n=149), confirming
> determinism. Full writeup: `analysis/recommendations/vwapcont-parity-diagnose-2026-07-23.{json,md}`.

> **Zero trading-path touched:** ANALYSIS ONLY -- no `params.json`/`heartbeat_core.py`/
> `filters.py`/live decision-core (`exit_manager.plan_exit_actions`) file modified; both replay
> engines' HARNESS code (`simulator_real.py`, `structure_stop_study.py`) left byte-unchanged, the
> ablation ran on a throwaway `norm_bars[1:]` slice inside the new diagnostic script only.

> **Learn (STAGE 4.5):** filed
> `_lesson-inbox/2026-07-23-entry-bar-eligibility-diverges-between-replay-engines.md` -- the
> generalizable rule (fold target C6 or a C4 sibling): when two independently-implemented replay
> engines disagree, diff PER-TRADE by terminal exit stage before trusting an aggregate $/tr gap,
> and CONFIRM a root-cause hypothesis with a targeted ablation experiment rather than a hand-waved
> list of partial explanations.

> **Scope + revert:** 5 files, all additive (1 new tool, 2 new analysis outputs, 1 new
> lesson-inbox item, 1 queue.md edit closing this item + filing the escalation). Revert:
> `git revert <this commit>`.

## [2026-07-23 ~22:42-23:03 ET] OK -- conductor (AFTERHOURS): ENGULFING-AT-STRUCTURE-TRIGGER's rolling-K-bar cluster primitive shipped, commits `8aed997a` + `77e048be`

> **STAGE 0/1:** ET confirmed 22:42 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again -- still
> correctly `status:pending` on J's REVOKE surface (5th fire in a row confirming, nothing new
> until J responds). Next 3 ranked MED items (`CATASTROPHE-CAP-WIDEN-WATCH`,
> `EXIT-ENGINE-PARITY-RESIDUAL`, `TRENDLINE-TIGHT-EXIT-ACCRETE`) are all "keep accruing/watching"
> per prior fires' own notes (no new action available). `DOJO-BUILD-HANDOFF` (HIGH) confirmed
> still not pickable (no TV MCP tools bound to this conductor session). Picked
> `ENGULFING-AT-STRUCTURE-TRIGGER`'s own named next step from its progress thread: build the
> rolling-K-bar local-extreme-cluster primitive `engulfing_at_swing_shelf`'s anchor notes called
> for, and re-run the 2-anchor falsification BEFORE any pre-reg.

> **Built `local_extreme_cluster()`** (predicates.py sec 12b) -- causal, C6-safe, reads only
> `ctx.bars[<=t]`, zero `ctx.structure` dependency. First design (anchor clustering to the
> window's GLOBAL min/max) FAILED both anchors on first verification run -- debugged with a
> standalone reproducer (OP-33: verify before disclosing): an unrelated spike bar 30-40min prior
> in the lookback window swamps the real, tighter, more-recent cluster the current bar is
> actually reacting to. Redesigned to anchor clustering to BAR T's OWN extreme instead --
> `pattern_anchor_verify.py --rule engulfing_at_local_cluster` then confirmed 2/2 anchors match
> (unlike `engulfing_at_swing_shelf`, which honestly does not fire on either).

> **Caught a real near-miss before shipping (the actual discipline, not just the headline):** ran
> the bare composition through the C27 prescreen immediately after anchor verification passed --
> NOISE-KILL, 92-99% days fired across every tolerance grid-searched (0.05-0.20). Anchor-pass and
> prescreen-pass are INDEPENDENT properties (precision on 2 named exhibits vs population-level
> selectivity); shipping on the anchor pass alone would have shipped a rule with near-zero
> cross-day signal. Grid-searched two discriminators (`local_cluster_min_touches` 2->3,
> `local_cluster_min_body_dollars` 0->0.40) re-checking BOTH anchors after every candidate --
> final config clears C27 (**TESTABLE, 33.3% days, 0.46 fires/day, recent-90d stable, no drift**,
> comparable selectivity to `engulfing_at_swing_shelf`'s 28.9%/0.42) while both anchors still
> fire. Filed the methodology gap to `_lesson-inbox` (anchor-verified != not-noise, the inverse
> of the swing-shelf fire's own "clean prescreen can still fail a targeted anchor" finding).

> **Verified this fire (OP-33):** `test_pattern_grammar.py` + `test_pattern_anchor_verify.py` +
> `test_pattern_prescreen.py` = 81/81 green (registry count 12->13, tier-2 set +1, ratchet tests
> updated in the same commit -- not left to silently drift). `pattern_anchor_verify.py` (no
> `--rule` filter, whole registry) = 4/4 anchors match declared state. Curated safety gate
> (31+5) PASS at both commits. Post-commit `git show 8aed997a --stat --name-status` confirmed
> exactly the 4 intended files (predicates.py, registry.py, test_pattern_grammar.py,
> pattern-prescreen.json evidence).

> **NO WIRING preserved** (unchanged from every other registry rule): `registry.py` has zero
> live-engine/watcher/setup_dispatch consumers -- this is prescreen/discovery-only, PAPER-safe
> by construction (nothing to revert on a real account). **Scope + revert:** 2 commits, 6 files
> total (4 code/test + queue.md progress note + 1 new lesson-inbox candidate). Revert:
> `git revert 77e048be 8aed997a`.

> **Next step (not this fire, rail 3):** the item's own BUILD spec's step (c) -- a frozen
> pre-reg (<=16 cells) + real-fills replay through `exit_manager_walk` over the 386-day history,
> confirming the winning cell still fires on both anchor bars. Item stays `status:pending` in
> queue.md pending that replay.

> **Cost: ~$6.7** (STAGE 0/1 reads incl. 3475-line queue.md targeted sections, task_scorer +
> 4-way item comparison, pattern-grammar/registry/predicates source reads (~600 lines), 2 failed
> design iterations debugged with standalone reproducers before the working design, C27
> prescreen run x3 (bare/touches-only/final-tuned, ~70s each), grid-search script across 20
> tolerance/touches combos + a targeted per-anchor touch-count sweep, 2 commits + verification,
> queue/STATUS/lesson-inbox write-up).

## [2026-07-23 ~22:12-22:29 ET] OK -- conductor (AFTERHOURS): EXITMGR-STAGE-LABEL-CONFLATION closed, commit `c4ee425a`

> **STAGE 0/1:** ET confirmed 22:12 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again -- STILL
> correctly `status:pending` on J's REVOKE surface (`gp-2026-07-23-twin-doctrine-001` confirmed
> via `conductor-proposals.jsonl`, 4th fire in a row confirming, nothing new until J responds).
> Full ranked list: 4 items tied at score 5.0 (`CATASTROPHE-CAP-WIDEN-WATCH` accrue-only n=4,
> `EXIT-ENGINE-PARITY-RESIDUAL` research-diagnosis, `EXITMGR-STAGE-LABEL-CONFLATION`,
> `TRENDLINE-TIGHT-EXIT-ACCRETE` accrue-only shadow). Picked `EXITMGR-STAGE-LABEL-CONFLATION`
> (MED, ledger-hygiene, filed 2026-07-14) -- a bounded, closable bugfix vs. the other three
> which are all "keep accruing / keep watching" (no new action available this fire).

> **What I found:** `exit_manager.py`'s pre-TP1 exit-ALL check hardcoded
> `stage="premium_stop"` even when `profit_lock_arm_scope="full"` made the actual exit a
> pre-TP1 profit-lock-floor scratch -- the human-readable `reason` string already said
> `"profit_lock_floor @ X"`, but the machine-readable `stage` field didn't, so any analytics
> keyed off `stage` (not `reason`) would silently conflate the static -50% catastrophe cap
> with the lock-floor exit. Fixed at the source: `stage` now reads `"profit_lock_floor"` when
> `floor_active`, matching `reason`.

> **Blast-radius audit (the actual work, not just the 1-line fix) found + fixed 2 REAL
> downstream consumers** that read `ExitAction.stage` and would have silently mis-fired on
> the new label: (1) `backtest/lib/exit_manager_walk.py`'s `_stage_fill_level` -- the
> live-parity bar walker several backtest tools ride -- would have fallen through to
> `None` -> market-fill for a floor exit instead of its correct limit-style fill; (2)
> `backtest/tools/t4_exit_matrix.py` + `backtest/tools/hold_posture_ab_study.py`'s
> `ARM_SCOPE_FULL` branches (the FIRST feeds `strike_ab_convention_reconciliation.py`'s
> `shape_sim`; the SECOND is the `TRAIL60-REOPEN-WATCH` queue item's planned re-run once
> >=50 new fills accrue -- so this was a live landmine for a FUTURE fire, not just a stale
> comment). Both fixed with the actual ratcheted floor level, not a naive fallback. Checked
> and confirmed SAFE/unaffected: `fleet_live.py`'s `first-entry-lock.json` reader (the file
> is never written anywhere in the repo -- dead code, always returns `[]`, out of scope to
> fix this fire); `debit_spread_ab_study.py`'s 2 defensive comments (never actually sets
> `scope="full"`, so its branch is unreachable either way); `ribbon_ride_strike_exit_ab.py`,
> `p5_topcell_real_fills_confirm.py`, `edge_matrix_range_*.py` (all pin `ARM_SCOPE_POST_TP1`
> explicitly, never full).

> **Verified this fire (OP-33):** new guard test
> `test_stage_disambiguates_catastrophe_cap_from_profit_lock_floor` in
> `automation/state/fleet/test_exit_manager.py` (REDs if stage is ever re-conflated) + 2
> existing assertions updated to the correct label + new
> `backtest/tests/test_exit_manager_walk_stage_labels.py` (3 tests pinning
> `exit_manager_walk.py`'s fill-level parity between the two stages). Ran the full relevant
> surface: `test_exit_manager.py` + `test_exit_actuator.py` + `test_exit_manager_replay.py`
> + `test_profit_lock_scope_pin.py` + `test_ssb_certification.py` + `test_structure_stop_
> study.py` + `test_exit_manager_walk_stage_labels.py` + `test_t4_exit_matrix.py` +
> `test_audit_fix_heartbeat.py` + `test_audit_fix_exit.py` + `test_dojo_sim_executor.py` +
> the 3 crypto-twin exit-touching suites = **265/265 green**. Curated safety gate
> (`run_safety_gate.py`): 31+5 PASS (also ran automatically via the pre-commit hook).
> Post-commit `git show c4ee425a --stat --name-status` confirms exactly the 6 intended
> files landed (5 modified + 1 new test file).

> **Zero live behavior change today:** no live/paper shape currently sets
> `profit_lock_arm_scope="full"` (STOP-B stays unarmed per the 2026-07-09 doctrine) --
> this only activates the correct label the day that scope is armed, or a frozen
> full-scope study is re-run. This is why it shipped directly under rail 4 (guard test +
> clean revert + this REVOKE report) rather than needing a J ping: it's a ledger-hygiene
> correctness fix with a verified-empty live blast radius, not a behavior/edge change.

> **Learn (STAGE 4.5):** no new lesson filed -- this is the existing blast-radius discipline
> (grep every consumer of a shared field before shipping, per C34/`/fable-blast-radius`)
> working exactly as designed on a real case, not a novel foot-gun.

> **Scope + revert:** 6 files (`exit_manager.py`, `test_exit_manager.py`,
> `exit_manager_walk.py`, `t4_exit_matrix.py`, `hold_posture_ab_study.py`,
> `test_exit_manager_walk_stage_labels.py` [new]). Zero `params.json`/`heartbeat_core.py`/
> `filters.py`/`CLAUDE.md` touched. Revert: `git revert c4ee425a`.

> **Cost: ~$4.8** (STAGE 0/1 reads, task_scorer + 4-way tied-item comparison, exit_manager.py
> source read + edit, blast-radius grep sweep across ~30 files for `stage`/`exit_reason`
> consumers, 2 downstream-consumer investigations that each needed their own read-through
> before deciding safe-vs-fix, 2 real fixes + 1 new test file, 3 rounds of test verification
> at increasing scope, safety gate, commit + verify, queue/STATUS write-up).

## [2026-07-23 ~21:52-22:20 ET] OK -- conductor (AFTERHOURS): TWIN-B6-SIM-FRICTION-CALIBRATION infra shipped, commit `465487f7`

> **STAGE 0/1:** ET confirmed 21:48 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again -- still
> correctly `status:pending` on J's REVOKE surface (`gp-2026-07-23-twin-doctrine-001`, nothing
> new until J responds -- 3rd fire in a row confirming this, per STATUS.md precedent). Next
> ranked ready item: `TWIN-B6-SIM-FRICTION-CALIBRATION` (HIGH, score 6.0, `depends:TWIN-B1`
> done). TWIN-PROGRAM.md has NO existing "B6"/"stream 6" spec -- the queue item's own text was
> the only spec, so this fire scoped it from scratch before building.

> **What scoping found (a real gap, not a design choice):** entries already capture the TRUE
> `filled_avg_price` via `poll_fill()` + a "FILLED" journal row (TWIN-B3 entry-quality
> machinery, `entry-quality.json` already has n=51 "marketable"-cohort real fills: avg
> slippage ≈ **+0.80bps favorable**, avg latency 0.29s -- directly usable friction data).
> EXITS never did the same: `manage_positions`' SELL_PARTIAL/SELL_ALL journals a CLOSED/
> MANAGED row whose `"broker"` field is the raw un-polled PLACE response (`status=
> "pending_new"`, `filled_avg_price=null`) -- confirmed by reading all 70 real CLOSED events
> + all 70 FILLED events in `journal.jsonl` directly: zero sell-side FILLED rows exist. Exit
> friction was silently un-measurable despite 70 real exits already on file.

> **Shipped:** `crypto_twin_core.manage_positions` now polls the SAME `broker.poll_fill()`
> helper after a live SELL_PARTIAL/SELL_ALL and journals an additive `"EXIT_FILLED"` row
> (`expected_price` parsed from `a.reason`'s `"kind @ price"` convention, `fill_price`,
> `time_to_fill_sec`, `slippage_bps`) -- purely additive telemetry, zero change to
> `close_failed`/`dec.closes_position` control flow (fails open on a poll exception via
> `EXIT_FILLED_CAPTURE_ERROR`). New reader `setup/scripts/crypto_twin_friction_calibration.py`
> combines both legs and cross-references `backtest/lib/simulator_real.py`'s
> `DEFAULT_ENTRY_SLIPPAGE`/`DEFAULT_EXIT_SLIPPAGE` via a LIVE import (not a hand-copied
> number -- caught the `backtest.lib` relative-import footgun mid-build: `simulator_real.py`
> uses `from .et_frame import ...`, so it must be imported as `backtest.lib.simulator_real`
> with the repo root on `sys.path`, not by putting `backtest/lib` on `sys.path` directly).
> Ran live against real state: `n=51 avg_slippage_bps=-0.8045` (entry), `n=0 verdict=ACCRUING`
> (exit, correctly honest about zero samples at ship time).

> **Honest caveat surfaced, not fixed this fire:** every twin exit stage (structure_stop /
> catastrophe cap / TP1-trail / premium_stop / runner_stop / time_stop / max_hold) is placed
> as a MARKET order unconditionally -- the twin has no exit-side passive/limit lane (only
> entries got the TWIN-B3 passive-limit graduation). So exit calibration data will only ever
> be comparable to `simulator_real.py`'s market-exit slippage bucket, never its "TP1/
> premium_stop/BE-stop fill exactly at the bracket level, zero slippage" limit-exit
> assumption. Flagged in TWIN-PROGRAM.md's new "B6 shipped" section as a TWIN-B6b follow-up
> (not queued as a separate item yet -- deliberately, per rail 3 one-bounded-task-per-fire;
> a future fire can promote it if J/conductor wants the exit-limit-lane build).

> **Verified this fire (OP-33) -- caught+fixed a REAL regression before it could ship:**
> `python -m pytest backtest/tests/test_crypto_twin_core.py` initially passed (44/44) because
> the fixture's `poll_fill` always returns a fixed price -- but running
> `python setup/scripts/twin_gauntlet.py --paths tp1_trail,structure_stop,catastrophe_cap,
> max_hold --dry` (the "diffs vs expected" backpressure TWIN-PROGRAM.md names as the
> conductor hook for exactly this class of bug) showed **3/4 touched paths FAIL**
> (`git stash` isolation confirmed 4/4 PASS pre-change, 1/4 PASS post-change -- root cause,
> not coincidence). Mechanism: `twin_gauntlet.py`'s `_dry_tp1_trail`/`_dry_structure_stop`/
> `_dry_catastrophe_cap` all assumed `journal[-1]["event"] == "CLOSED"` -- an assumption that
> was ALSO baked into 2 pre-existing `test_crypto_twin_core.py` assertions (same class, same
> fire, same root cause: EXIT_FILLED now legitimately trails CLOSED). Fixed both: find the
> last CLOSED row explicitly rather than assuming journal-tail position. Re-ran
> `--dry` over all 6 known paths (`tp1_trail,structure_stop,catastrophe_cap,max_hold,
> restart_open_position,entry`): **6/6 PASS**. Full suite:
> `test_crypto_twin_core.py` + `test_crypto_twin_friction_calibration.py` (7 new tests:
> sign-convention, stage-grouping, accruing-verdict, real-import-resolves-non-None) +
> `test_crypto_twin_scenarios/_entry_quality/_health/_broker/_sim_bear/_soak_report/
> _reaper_exemption.py` + `test_twin_gauntlet.py` = **268/268 green**. Curated safety gate
> (`backtest/tests/run_safety_gate.py`): 31+5 PASS. Post-commit
> `git show 465487f7 --stat --name-status` confirms exactly the 6 intended files landed.

> **Learn (STAGE 4.5):** the gauntlet caught a real bug this fire was about to ship blind on
> (pytest alone would have shipped it green) -- this is TWIN-PROGRAM.md's "Conductor hook"
> value stream #2 working exactly as designed, not a new lesson to encode; no lesson-inbox
> item filed (the guardrail that caught it already exists and just did its job).

> **Scope + revert:** 6 files (`crypto_twin_core.py`, `crypto_twin_friction_calibration.py`
> [new], `twin_gauntlet.py`, `test_crypto_twin_core.py`, `test_crypto_twin_friction_
> calibration.py` [new], `TWIN-PROGRAM.md`). Zero `params.json`/`heartbeat_core.py`/
> `filters.py`/`CLAUDE.md` touched -- twin-only (paper, crypto gym-only per project scope),
> rail-4 clear, purely additive telemetry + a read-only reader. Revert: `git revert 465487f7`.
> `automation/state/crypto-twin/friction-calibration.json` is a regenerated report artifact
> (same untracked-by-design precedent as `entry-quality.json`) -- not committed.

> **Cost: ~$4.3** (STAGE 0/1 reads, TWIN-PROGRAM.md scope search, journal.jsonl/entry-
> quality.json direct data investigation to find the real gap, crypto_twin_core.py edit +
> docstring, 6 new/updated core tests, calibration script build + 7 tests, live script run +
> import-path debug, twin_gauntlet.py regression hunt via git-stash isolation + 3-function
> fix + full 6-path re-verify, TWIN-PROGRAM.md fold, commit + verify, queue/STATUS write-up,
> conductor_outcome record+metric).

## [2026-07-23 ~21:42-22:00 ET] OK -- conductor (AFTERHOURS): OPEN-BELL-STATUS-PUSH closed (stale checkbox, work already fully shipped)

> **STAGE 0/1:** ET confirmed 21:42 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again -- still
> correctly `status:pending` on J's REVOKE surface (`gp-2026-07-23-twin-doctrine-001`, filed
> last fire, nothing new until J responds). Read the full ranked list: 2nd item was
> `OPEN-BELL-STATUS-PUSH` (HIGH, visibility, OP-33e, `depends:none`).

> **What I found:** the queue item's own text describes a build (09:36 ET one-shot Discord
> push of engine-health + kill-switch status + tick freshness + fills-so-far, retiring J's
> repeated "is it running today?" question). Investigated before building anything (tiebreak
> rule: closing a loop > creating an artifact) -- `setup/scripts/open_bell_status.py` +
> `install-open-bell-status.ps1` already exist, fully match the spec, and
> `Get-ScheduledTask -TaskName Gamma_OpenBellStatus` confirms `State=Ready`, registered.

> **Verified this fire (OP-33):** `automation/state/open-bell-pinged.json` +
> `discord-outbox.jsonl` show the task has fired correctly for 3 CONSECUTIVE trading days
> (2026-07-21, 07-22, 07-23, all `queued_at` 09:36:00 ET, `source: open_bell_status`).
> Today's actually-delivered message: `🟡 OPEN-BELL STATUS 2026-07-23 09:36 ET -- engine:
> YELLOW | Kill-switches: Safe armed re-armed-today YES | Bold armed re-armed-today YES |
> Ticks: last bold tick 09:35:04 (0.9m ago) | Fills: none yet`. Guard test re-run this fire:
> `python -m pytest backtest/tests/test_open_bell_status.py -q` -> 11/11 green. This is the
> stale-checkbox pattern task_scorer's own `--all` fix (previous fire, commit `6d42d211`) was
> built to surface -- work shipped, box never flipped.

> **What shipped this fire:** zero code changes (nothing to build -- verification-only).
> `automation/overnight/queue.md` `OPEN-BELL-STATUS-PUSH` flipped `[ ] -> [x]`,
> `status:pending -> status:done`, with the full evidence trail above appended inline
> (repo convention: completed items stay inline with `[x]`/`status:done`, not moved to a
> separate section -- matches `TASK-SCORER-SECTION-SCOPE-FIX` and `CRYPTO-TWIN-T1-T4`
> precedent in the same file).

> **Learn (STAGE 4.5):** none new -- this fire's discipline was the SAME scoping-before-
> building step the last fire used on GATE-TIERS-IMPLEMENT (check what's already shipped
> before re-doing it). No lesson-inbox item filed; the general pattern is already covered
> by the existing queue-hygiene discipline (OP-22 compound-don't-accumulate).

> **Scope + revert:** 1 file (`queue.md`, 1 checkbox + evidence block). Zero
> params/heartbeat_core/filters/placement/exit/CLAUDE.md touched. Not a trading-path
> change -- pure bookkeeping, trivially revertible (`git checkout -- automation/overnight/
> queue.md` or `git revert` the commit).

> **Cost: ~$1.1** (STAGE 0/1 reads, task_scorer full ranking, targeted queue.md grep,
> open_bell_status.py read, scheduled-task + pinged-file + outbox verification, guard-test
> re-run, STATUS/queue write-up, conductor_outcome record+metric).

## [2026-07-23 ~21:12-21:50 ET] OK -- conductor (AFTERHOURS): GATE-TIERS-IMPLEMENT rank #3 shipped (per-arm hard-skip override), commit `ecde12f8`

> **STAGE 0/1:** ET confirmed 21:12 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again, but it is
> ALREADY drafted + filed for J's REVOKE/APPROVE (last fire, `gp-2026-07-23-twin-doctrine-001`,
> still `status:pending` on J's side -- nothing new to do until J responds). Read the full
> ranked list (`task_scorer.py` with no args): next-highest ready items were `GATE-TIERS-
> IMPLEMENT` (HIGH, trading-path-eligible), `OPEN-BELL-STATUS-PUSH` (HIGH), `TWIN-B6-SIM-
> FRICTION-CALIBRATION` (HIGH). Picked GATE-TIERS-IMPLEMENT: a HIGH, `depends:none`, fully
> pre-specified engineering task (the referenced audit, `markdown/audits/GATE-PROVENANCE-
> AUDIT-2026-07-02.md`, already contains the design + a ranked action list) that is squarely
> a PAPER trading-path change (rail 4 -- ships directly with guard+revert+REVOKE, no J-first
> needed).

> **Scoped BEFORE building (the audit's plan is a 6-step epic; one bounded task per fire,
> rail 3):** re-read `accounts.json` + `build_shared_signal.py` + `fleet_executor.py` first
> to check what the 3 weeks since the audit had already absorbed. Found: ranks #2 (G8 momentum
> bug) and #5 (E5 confidence gate) were ALREADY closed 2026-07-11 by earlier fires; the existing
> tight/base/loose `min_triggers` grid + the `probe_arm` cohort-bypass mechanism (2026-07-10/11)
> already cover a good chunk of "risky arm takes the one-gate-away trade" for OTHER gates. The
> ONE piece still genuinely open and cleanly scoped: rank #3, `_HARD_SKIP_VERDICTS` (require_
> bearish_fill_bar) is a MODULE-LEVEL constant baked into the shared signal's "bold" perception
> block at BUILD time -- every non-safe arm (bold-2 control, risky-1 tight, risky-3 loose)
> inherits the IDENTICAL hard-skip regardless of its own gate tier, so this ONE gate was
> structurally un-relaxable for a risky arm no matter what `gate_override` said.

> **What shipped:** `build_shared_signal.py`'s `_bold_passed_blocks_from_row` now exposes
> `score_peak_passed` (the score/trigger quality check WITHOUT the hard-skip filter) and
> `hard_skip_action` (which global hard-skip verdict fired, if any) alongside the UNCHANGED
> `passed` field -- byte-identical for any reader that only looks at `passed`.
> `fleet_executor._effective_passed(block, arm)` is the new consume-time gate: an arm with NO
> `gate_params.hard_skip_verdicts` key reads `passed` exactly as before (every existing arm,
> unchanged); an arm that carries the key opts INTO a per-verdict allowlist of what it still
> honors as a hard block (empty list = ignore all global hard-skips). Wired risky-3 --
> the only LIVE RISKY/minimum-viable-gate-tier arm since safe-1 retired 2026-07-11 -- with
> `gate_params: {"hard_skip_verdicts": []}`. bold-2 (control) and risky-1 (tight) get zero
> code-path change since they never set the key.

> **Verified this fire (OP-33):** direct smoke-test of `_bold_passed_blocks_from_row` on 3
> synthetic rows (hard-skip-blocked / clean ENTER / HOLD) confirmed the new fields compute
> correctly and `passed` is unchanged in all 3 cases. 6 new guard tests added to
> `test_fleet_executor.py` (byte-identical default for both a blocked and a passing block,
> rescue for the opted-out arm, still-honors-a-named-verdict, unaffected-when-no-hard-skip-
> fired, and an end-to-end `_chosen_side` integration proving a control arm and the rescued
> arm diverge on the SAME input block). `python -m pytest` on `automation/state/fleet/`:
> 283/283 green (was 277 pre-change). Also re-ran `test_probe_arm.py` / `test_plan_all.py` /
> `test_six_account_routing.py` / `test_duplicate_account_guard.py` / `test_arm_display_names.py`
> / `test_exit_patch_overlay.py` / `backtest/tests/test_participation_cascade.py` -- all green,
> nothing else in the fleet path regressed. Curated pre-commit safety gate PASS. Post-commit
> `git show ecde12f8 --stat --name-status` confirms exactly the 4 intended files landed
> (`accounts.json`, `build_shared_signal.py`, `fleet_executor.py`, `test_fleet_executor.py`).

> **Learn (STAGE 4.5):** none new -- this fire's foot-gun-avoidance was the SCOPING step
> itself (checking which ranked audit items were already closed before re-doing them), not
> a fresh bug. No lesson-inbox item filed.

> **Scope + revert:** exactly the 4 files above. Zero `heartbeat_core.py`/`params.json`/
> `CLAUDE.md` touched -- this is a fleet_rest-only (paper) trading-path change per rail 4.
> Revert: delete `accounts.json`'s risky-3 `gate_params`/`gate_params_doc` keys (byte-identical
> to before this fire), or `git revert ecde12f8` for the full mechanism.

> **queue.md** `GATE-TIERS-IMPLEMENT` status updated to `rank3-shipped-ranks1-4-open` with the
> same evidence + an explicit list of what's still open (rank #1 block_elite_bull-relax-for-
> RISKY is the #1 blocker per the audit, ~4.2 eps/wk -- next-fire-ready; rank #4 doji-gate
> relax-for-RISKY needs the same mechanism extended to a score-side gate, not just hard-skip;
> per-arm fill-funnel N=10-day measurement needs live days to accrue before it can run).

> **Cost: ~$3.5** (STAGE 0/1 reads + audit re-read + accounts.json/build_shared_signal.py/
> fleet_executor.py investigation, scoped design, 3-file implementation + 1 test file, smoke
> tests, full fleet suite + adjacent suites, commit + verify, STATUS/queue write-up,
> conductor_outcome record+metric).

> **STAGE 0/1:** ET confirmed 20:42 (Thursday, market closed since 15:55). `engine-health.json`
> GREEN 13/13. `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` (MED, doctrine,
> propose-only, `depends:TWIN-B1`). Verified the dependency: TWIN-B1 has no standalone
> checkbox but every downstream twin task (B1.5/B3/B4/B5/B6/B7) references it as `done` in
> practice (CRYPTO-TWIN-T1-T4 closed 07-11, superseded straight into B1-B2) -- dependency
> satisfied. This is TWIN-PROGRAM.md's last open "Build order" line: "CLAUDE.md one-liner
> proposal (propose-only) folding the amended crypto boundary + this program's existence."

> **What shipped (drafted, not applied to CLAUDE.md -- doctrine stays J-first per rail-4):**
> a new "Doctrine proposal" section in `markdown/planning/TWIN-PROGRAM.md` with the exact
> proposed text -- one sentence appended to existing OP-31 (folds into the Kitchen bullet,
> not a new numbered OP, to avoid extra context-budget cost): "**Twin-first deploy
> (2026-07-23):** any new watcher/detector/exit-lifecycle feature runs 24-48h on the 24/7
> crypto twin (paper, mechanism-validation only -- twin P&L is never SPY evidence) before
> touching a SPY execution path." This formalizes practice `twin_gauntlet_conductor_hook.py`
> has already been advisory-enforcing since B2 (2026-07-11) -- doctrine anchor for an
> existing behavior, not a new one.

> **Context-budget checked before drafting (OP-33):** ran `check-context-budget.ps1` --
> YELLOW 8848/9000 (98%) BEFORE this fire. The proposed sentence is ~60 tokens, landing at
> ~8923/9000 if applied -- stays YELLOW, does NOT cross the 9000 RED line, but leaves
> near-zero headroom. Flagged honestly in the proposal/draft rather than silently absorbed;
> did not scope-creep into an unrelated trim pass this fire (last trim: 2026-07-21).

> **Filed for J's REVOKE/APPROVE surface:** `conductor-proposals.jsonl` id
> `gp-2026-07-23-twin-doctrine-001` (apply_ops targets the exact, verified-unique OP-31
> string in CLAUDE.md; NO `eval_bar_cleared` -- doctrine, not a validated edge, so it will
> NOT auto-apply). Discord ping queued (`gamma-ops`). Companion wrist-card enqueued
> (`gamma-companion/lib/approvals.enqueueApproval`, same id). Reply `ship
> gp-2026-07-23-twin-doctrine-001` (or thumbs-up / wrist Approve) to have `AutoApply`
> perform the edit + safety gate + commit; `shelve ...` / thumbs-down to drop.

> **queue.md** `TWIN-DOCTRINE-FIRST-DEPLOY` updated with the same evidence, left
> `status:pending` (correctly -- CLAUDE.md itself is untouched pending J).

> **Verified this fire (OP-33):** re-ran `check-context-budget.ps1` post-edit -- still
> YELLOW 8848/9000 (CLAUDE.md itself untouched, as intended). Confirmed the `find` string
> occurs exactly once in CLAUDE.md via a Python occurrence-count check before filing
> apply_ops (a non-unique `find` would be refused by AutoApply). Confirmed the discord-bridge
> reads `content` (used) with `message` fallback -- correct schema.

> **Learn (STAGE 4.5):** none new this fire -- straightforward propose-only doctrine
> authoring, no foot-gun hit.

> **Scope + revert:** `markdown/planning/TWIN-PROGRAM.md` (1 new section) +
> `automation/overnight/queue.md` (1 item annotated) + `conductor-proposals.jsonl` (1 append)
> + `discord-outbox.jsonl` (1 append) + 1 new gamma-memory file + `MEMORY.md` index line.
> Zero params/heartbeat_core/filters/placement/exit/CLAUDE.md touched this fire (CLAUDE.md
> change is a PROPOSAL only, applied later by AutoApply if/when J approves). Revert: `git
> revert <this-commit>` (once committed); the CLAUDE.md edit itself has never landed, so
> there is nothing to revert there yet.

> **Cost: ~$2.3** (STAGE 0/1 reads, dependency trace, draft authoring across 2 docs, exact
> unique-string verification, proposal + Discord + companion filing, STATUS/queue write-up,
> conductor_outcome record+metric).

---


### BROKEN: self-check 2026-07-25T21:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-25T22:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-25T22:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-25T23:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### WARN: spend-summary threshold breach
- ts: 2026-07-26T03:30:14+00:00
- date_et: 2026-07-25
- total: $423.39 (threshold $30.00)
- claude: $423.39  minimax: $0.00
- claude_sessions: 12

### BROKEN: self-check 2026-07-25T23:39:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

## Kitchen
Kitchen: alive, queue 16 pending, last cook 0 min ago, today $0.00, model=openrouter::nvidia/nemotron-3-super-120b-a12b:free

### BROKEN: self-check 2026-07-26T00:09:56
- DRESS-REHEARSAL RED: broker-boundary rehearsal at 2026-07-25T20:45:01 FAILED -- see automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-26T00:19:17
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-26T00:39:57
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.
- CANDIDATES-UNTRACKED: 25 untracked files under strategy/candidates/ (threshold 20) -- live chef/kitchen/prospector pipeline state accumulating with no commit history / no disk-loss recovery path. Batch `git add --pathspec-from-file` + commit to clear (see STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22).

### BROKEN: self-check 2026-07-26T13:47:46
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.
- CANDIDATES-UNTRACKED: 37 untracked files under strategy/candidates/ (threshold 20) -- live chef/kitchen/prospector pipeline state accumulating with no commit history / no disk-loss recovery path. Batch `git add --pathspec-from-file` + commit to clear (see STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22).

- [2026-07-26 11:47:47] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-26 11:47:47] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-26 11:47:47] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-26.md

### BROKEN: self-check 2026-07-26T14:09:56
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-26T14:39:56
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-26T15:09:56
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.

### BROKEN: self-check 2026-07-26T15:39:56
- ENGINE DARK ALL DAY (RED): 2026-07-24 was a trading day with ZERO core-decisions.jsonl rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently dropping every task through the gap (WakeToRun=True alone did NOT fix this in the 2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day (engine-health.json position_safe/position_bold) before treating this as cosmetic.
