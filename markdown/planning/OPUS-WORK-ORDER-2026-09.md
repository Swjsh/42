# OPUS WORK ORDER — September → October 30, 2026

> Written 2026-09-01 ~21:40 ET by Fable 5.1, same session as the full audit
> ([FABLE-FULL-AUDIT-2026-09-01.md](../../analysis/deep-research/FABLE-FULL-AUDIT-2026-09-01.md), commit `04f80c3f`).
> J: *"time to get to work. think through it methodically and layout a roadmap and things that need
> further review and auditing and testing for opus."*
>
> **This is the living execution order for every Opus/Sonnet session until the 2026-10-30 decision.**
> Tick boxes here as work lands; the canonical destination/gates stay in [ROADMAP.md](ROADMAP.md);
> the item-level backlog stays in `automation/overnight/queue.md` (section `FABLE-FULL-AUDIT-2026-09-01 follow-ups`).
> Model routing (J's doctrine): **Opus = judgment** (adjudicate, review, design, root-cause);
> **Sonnet = hands** (build, test, docs); **$0 scripts** for anything recurring. Fable is not required
> for any item below; where a decision is genuinely contested, it is marked `[FABLE-OR-J]`.
> Nothing here arms money. OP-0 #1 stands.

---

## 0. The one decision this order rests on — the clock and the freeze

**Problem.** Two frozen documents disagreed: the 08-29 review froze config to ~09-29 and planned an
October arm; `PREREG-TIGHT-LADDER-2026-08-28` registered a **40-trading-day** window closing
**2026-10-30** and says interim readings "MUST NOT change the configuration." The audit showed the
20-day plan could not reach the gate under any realistic tape.

**Decision (Gamma-decides; recorded here tonight; the hook constant and CLAUDE.md text change on
Saturday 09-05 per Rule 9; revoke = `git revert`):**

1. **The governing clock is 2026-10-30.** The gate is re-scored every Friday and at the 09-29
   checkpoint, but nothing is *decided* before 10-30.
2. **The freeze on SHAPE-CHANGING edits extends to 2026-10-30.** Shape = anything that changes
   which trades are taken, how big, or how they exit: entry gates/filters, strike tier, sizing
   caps, exit shape, the data feed the scorer reads (`feed=iex→sip` changes filter-10's firing).
   The hook's `FREEZE_END` moves to 2026-10-30 on 09-05.
3. **Pre-registered SAFETY changes ship at the 09-29 checkpoint** (the freeze exception already
   in doctrine: "kill-type risk reductions"): time stop ≤15:20 (prereg filed), early-close entry
   cutoff, exit-pass mutex + wrapper fix, `executed_stop` logging, canary out of safe-2, safe-2
   retirement mechanics. None of these change entry selection or size on a normal day; each
   ships with guard + RED-proof + one-line revert and is listed in §3.
4. **Everything that IS a shape change waits for 10-30** and is prepared in a branch, pre-registered,
   ready to ship the evening of the decision regardless of its colour (§4).

**Why this is not bar-softening:** the 40-day window is the harder test — it cannot borrow 08-04,
it demands the sign survive ex-best-day, and it is scored on the frozen candidate profile net of
costs (criterion 5). The 20-day plan was easier and still unreachable.

---

## 1. Phase 0 — this week (Tue 09-01 → Sat 09-05)

### Landed tonight (04f80c3f) — verify they behave on their first live day
- [x] Dead-man's switch (`Gamma_DeadMansSwitch`, /2 min RTH), kill-switch wiring, conductor picker,
  gate criterion 5 + disclosures, generator fixes, preregs, docs. See audit §6.
- [ ] **09-02 16:30 ET — first-live-day review — MECHANISED 2026-09-02 02:15 ET, box stays OPEN until
  today's fire produces a verdict.** This was a 20-minute checklist a human had to remember to run; §5's own
  cadence rule says recurring work becomes a $0 script, so it is one: `setup/scripts/first_live_day_review.py`
  → `analysis/first-live-day/{date}.json`, fired by `Gamma_FirstLiveDayReview` daily 16:30 ET
  (registered + fired end-to-end, `exit=0`, artifact written — commit `ccf128e1`). Seven checks, pure stdlib,
  no LLM. **Nothing is ticked by building it:** the DMS's own first production fire is 09:32 ET *today*, so the
  first real verdict does not exist until 16:30 ET. A later session reads that JSON and closes this box —
  and must read the `guards_full` check's reason FIRST, because `Gamma_GuardsFull` has produced no verdict
  since 08-31 and a fresh-looking count off a stale state file is the failure this review must not launder.
  Two build defects worth naming, both C7: `NO_DATA` was first ranked *better than GREEN* (a day with no state
  files at all would have graded a clean pass), and `check_guards_full` reported its count before its staleness.
  Manual fallback if the task is dark — read `automation/state/dead-mans-switch.json`
  + `automation/state/logs/dead-mans-switch-2026-09-02.jsonl`: fired every 2 min 09:32–15:58? every
  arm `LIVE_NO_ACTION`/`STALE_BUT_FLAT`, zero `FLATTENED`, zero `ERROR`? `engine_health.py` →
  `escalation_flags` GREEN, `duplicate_ticks` clean? Did `Gamma_EodFlatten_Aggressive` reach the
  broker MCP at 15:55 (3rd day) — if not, file the root-cause item (same-second collision with the
  safe flattener? cold MCP start inside a 2-min window?) and consider retiring the two LLM
  flatteners in favour of the Core alone (`[FABLE-OR-J]`: defense-in-depth vs. noise that writes
  false halts). Conductor fires overnight: did any pick a `GATE-BLOCKING` item first?

- [x] **The safety net itself was dark, and the cause is quiet mode — CLOSED 2026-09-02 05:00 ET.**
  `Gamma_GuardsFull` (the ~11,400-test suite) produced no verdict 08-31 → 09-02 while every surface
  read healthy: `State=Ready`, `LastTaskResult=0`. **Neither field moves when a task never starts** —
  `LastRunTime` and `NumberOfMissedRuns` were read by nothing. Root cause, proven 7/7 rather than
  assumed: quiet mode disables ~120 tasks for J's evening and **holds past its own 23:00 ET clock
  while a fullscreen app is foreground**; a trigger inside a hold is skipped, and because the task
  was *Disabled* rather than merely unavailable, `StartWhenAvailable` cannot recover it. On 09-01 the
  holds (23:02–23:22, 00:07–00:42) ate `FuturesBrokerProbe` 23:05, `GuardsFull` 23:15,
  `GuardsNightly` 00:30 — while `SpendSummary` 23:30, `OosCheck` 23:40, `LicenseMonitor` 23:58 and
  `GateExpiryCheck` 01:00 all ran. **Shipped:** `Gamma_TaskStaleness` (daily 05:45 ET, $0,
  report-only, 53 tests) → `self_check.py` item 22 → quiet mode's `ESSENTIAL` set, so the blackout
  cannot silence the alarm about the blackout. `GuardsFull` + `GuardsNightly` caught up by hand;
  GuardsFull's first verdict since 08-31 is **11,461 passed / 5 failed**, four of them the known
  pre-existing set. **The cause is NOT fixed** — a catch-up sweep needs a decision on which tasks may
  be auto-restarted hours late (a report-only producer, yes; `Gamma_KalshiAuto` placing orders off
  stale next-day weather, no), so it is filed as `QUIET-HOLD-CATCH-UP-SWEEP` with that constraint
  rather than shipped on a guess. Also fixed en route: `## Known broken` had drifted back below the
  first STATUS.md entry (the 2026-08-20 two-month-discard scar), now pinned in the preamble by a
  test; and the first-live-day review's **outer** aggregator still ranked `NO_DATA` as GREEN, so an
  all-absent day — the box dead — graded clean.

### Wave 2 (Sonnet builders launched 21:30 ET; verify + review inside the workflow, then commit)
- [x] B1 `setup/scripts/whole_engine_null.py` per `prereg-whole-engine-null-2026-09-01.json` — BUILT + RUN
  2026-09-01 evening (300 resamples/day, cache-warm, 0 network fetches); task `Gamma_WholeEngineNull`
  Fridays 16:55 ET (`State: Ready`). **First reading: verdict WITHHELD (HARNESS_UNRELIABLE).** The
  exit walker replayed the engine's own 121 P1 entries with **79.3% sign agreement** (bar 85%,
  mean bias −$20.76/trade), so no PASS/FAIL is reported. The mechanical sub-checks are all green on
  the raw numbers (engine +$3,562 > N_a p95 $2,546; > N_b_call −$2,642 + IQR; P3 +$19 ≥ 0; N_c
  −$4,676 ≤ 0) and are published as such — but a verdict computed by an unfaithful walker is a
  statement about the harness, not the engine (02-VALIDATION V9). A 2026-09-01 review pass tried to
  promote this to PASS on the grounds that the frozen JSON did not name V9; Fable reversed it and
  wrote the rule into the prereg as a dated addendum (`addendum_2026_09_01_validator_fidelity`).
  **RESOLVED 2026-09-02 (Opus): V9 79.3% → 89.3% (n=121, bar 85%), mean bias −$20.76 → −$10.44,
  `harness_reliable=True`, study verdict WITHHELD → PASS.** ⚠️ **The root cause named above was
  WRONG, and the way it was wrong is the lesson.** The trigger-level story was a *confounded
  correlation*: rows with a recorded level agreed 96.3% vs 74.5% for proxy rows, but all 27
  real-level rows were calls from core arms. The controlled differential — same 25 rows, same
  cached bars, same production `exit_manager` core, walked twice with **only** the level changed —
  returned **real 96.0% vs proxy 96.0%, delta +0.0%** (proxy error vs real: median $0.27, max
  $2.33). The proxy was accurate and never the cause. The real cause was a second hardcode in the
  same function: `walk_one` passed `structure_stop_enabled=True` for every row while 26.9% of the
  population resolved to **premium** mode live (`exit_manager.py:268`). Attribution, one variable
  at a time over 135 rows: base 80.0% · +stop_mode **86.7% (+6.7pp)** · +exit-shape keys 80.0%
  (**+0.0pp**, i.e. the first fix proposed *after* the falsification was also worthless and also
  died to the decomposition). Residual `ribbon_flip` blindness (`ribbon_tick_df=None`, 40.0%,
  concentrated in risky-1 at 29.7% of its exits) closed by reconstructing the series from
  `core-decisions.jsonl` with a look-ahead-safe backward-as-of merge → 66.7%, 121/121 rows served.
  Null legs left byte-identical (frozen prereg) with the mismatch disclosed. The enrichment defect
  was real and fixed on its own merits (structure-mode rows carrying a level 27/186 → **186/186**;
  puts 0/72 → 51/72; safe-3 0/20 → 20/20) — it just was not the V9 cause. **Note the mechanical
  sub-checks were already PASS on 09-01; what changed is that a faithful walker now certifies
  them.** Lesson filed: `automation/overnight/_lesson-inbox/2026-09-01-confounded-root-cause-written-into-a-prereg.md`.
  Full numbers + deviations: `analysis/whole-engine-null/{latest,2026-09-02}.{json,md}`,
  `summary-line.txt`.
- [x] B2 early-close flatten: `calendar.json` gains `early_closes`; `eod_flatten.py --only-if-early-close`;
  task `Gamma_EodFlattenEarlyClose` 12:32 ET. (Entry-cutoff half waits for 09-29 — heartbeat_core is frozen.)
- [x] B3 monitors: `duplicate_ticks` + `early_close_today` in engine_health; `prereg_hygiene.py` nightly;
  REGIME COVERAGE block in the gate.
- [x] B4 HOME.md `## The gate` block (the one number: frozen-window book PF ex-best-day, days scored/needed,
  reachability, null status, the 10-30 clock).
- [x] B5 Discord `HALT <arm>` / `HALT <arm> FLATTEN` / `RESUME <arm>` (allowlisted authors). **J drills it
  from the phone once, on paper, before 10-30** (§6).
- [x] B6 time-stop band measurement → mechanical SHIP/KILL for the ≤15:20 prereg at 09-29.
- [x] B7 LIVE-FLIP-RUNBOOK rewritten against the live caps and tonight's prerequisites.
- [x] B8 `journal/trades.csv` writer fixed + 25 rows repaired (backup kept) + parse guard.

### Gate reading 2026-09-02 05:04 ET (off-cadence, disclosure — the Friday box below is still open)

**OVERALL RED.** 1 STATISTICAL **FAIL** · 2 OPERATIONAL PASS (6/6) · 3 RECONCILIATION PASS (4/4 arms
within tolerance) · 4 BEHAVIOURAL **PASS_UNVERIFIED** · 5 PROD-SHADOW **INSUFFICIENT_DAYS 0/20**.

- Criterion 1 is not close and it is not close on any arm: day-level bootstrap PF CI-lower vs a 1.0 bar
  — safe-3 0.356 (n=26) · safe-2 0.333 (n=30) · risky-1 0.412 (n=26) · bold-2 0.347 (n=20). Distance to
  the bar **0.71–0.75** on all four. Book ex-best-day `P(PF<=1)=0.573` — a coin flip.
- Criterion 4 reports `PASS_UNVERIFIED` honestly: `rule-breaks.jsonl` was last written **2026-05-18**,
  before the window even starts, so "0 breaks" cannot be distinguished from an abandoned ledger.
- Regime is still the known problem: frozen window `n_days=1`, VIX daily-max 16.8, **zero** days VIX>20,
  **zero** days down >1%. The gate prints its own warning — *calm-only window, a GREEN here is untested
  in stress.*

- [x] 🚨 **CRITERION 5 HAS ZERO SLACK — new 2026-09-02, quantified, not previously stated anywhere.**
  The window `2026-09-01..2026-09-29` contains **exactly 20 trading days** (verified against
  `automation/state/calendar.json`: Labor Day 2026-09-07 is the only Sept/Oct holiday), against a bar of
  **20 scored days**. One elapsed, 19 to go, and **every one of them must score**. A single unscored day
  puts criterion 5 out of reach of its own registered window — and tonight proved the rig silently loses
  scheduled days: `Gamma_GuardsFull` was dark 08-31→09-02 because quiet mode's presence hold ate its
  trigger and `StartWhenAvailable` cannot recover a fire missed while Disabled. **These two facts had
  never been put next to each other.** The extended clock to 10-30 has 3 days of slack (43 trading days
  vs a 40-day bar), so it absorbs a miss; the 09-29 reading does not. ACTION: decide whether the 09-29
  criterion-5 reading is worth defending (which means the `QUIET-HOLD-CATCH-UP-SWEEP` item is no longer
  hygiene, it is gate-blocking) or whether 10-30 is the only reading that was ever going to matter — in
  which case say so in writing and stop treating 09-29 as a gate date.
  **ANSWERED 2026-09-02 05:45 ET, and it was never a fork.** `automation/state/prod-shadow-designation.json` (frozen `2026-09-01T20:22:26-04:00`, before any result) registers `2026-09-01..2026-09-29 / min_days 20` as THE bar and calls the 10-30 clock *“EXTENDED disclosure view only -- it never substitutes for or lowers this shorter, harder pass window.”* **09-29 is binding**, so the zero-slack finding is load-bearing and the catch-up sweep is gate-blocking work — shipped `6c8d7dc3` with a curated 9-name report-only allowlist that excludes `Gamma_KalshiAuto` (trades on stale weather), the broker probe, both HEAVY guard suites and the weekend conductor. Verified live: it caught up 5 tasks, all `rc=0`, and the staleness reporter went 5 RED → 3 RED — the 3 remaining being exactly the deliberately-excluded set. *The framing error is worth keeping:* this was called “a genuine fork with no right answer” when it was a question whose answer was already filed. Read the window's own designation before treating its terms as open.

### Fri 09-04 — first Friday cadence
- [ ] `go_live_gate.py` re-run → HOME gate block; null study first Friday reading; **WEEK ORDER revived**
  (`analysis/deep-research/WEEK-ORDER-2026-09-08.md`, Thursday-evening synthesis; queue item
  WEEK-ORDER-CADENCE-REVIVAL) — 12 lines for J max, per the 08-10 template.

### Sat 09-05 — Rule-9 doctrine pass (Opus, one session, one commit)
- [ ] `CLAUDE.md:65` live threshold → *arming = go-live criterion 5 (designated prod-shadow profile on
  the frozen window, PF CI-lower(2.5%) > 1.0 on as-traded, ex-best-day, cost-adjusted, ≥40 scored days)
  + criteria 2–4 green; criterion 1 = lifetime-robustness disclosure; governing clock 2026-10-30.*
- [ ] `CLAUDE.md` Rule 7 (FINRA repealed the $25K PDT floor 2026-06-04; both accounts on the IML regime),
  Goal line (one live account + paper lab; $25K = compounding waypoint), `tp1_qty_fraction 0.8/0.667`
  (shadowed — strategies.py hardcodes 0.667 both), 3× `decisions.jsonl` → `core-decisions.jsonl`,
  Rule 5/6 text gains "tighter of the % cap and the live $ caps ($1,000/position, $400/day)".
- [x] `setup/hooks/doctrine.py` `FREEZE_END = 2026-10-30`; freeze banner text names the 09-29 safety
  checkpoint and the override token for pre-registered kill-type reductions. **DONE 2026-09-02 05:10 ET,
  pulled forward from the Sat 09-05 pass — commit `3f6a1ad9`.** The constant was still `2026-09-29`, so
  on **09-30 the hook would simply have stopped blocking trading-path edits**, mid-scoring-window, with
  no symptom but the banner changing to "freeze closed". Silent + dated + one-line = does not wait for a
  session that might not happen. Extending a freeze only ever blocks more, and it is git-revertible.
  Banner now names the checkpoint and `GAMMA_FREEZE_OVERRIDE` on both sides of it and says risk
  EXPANSIONS wait for 10-30 regardless. `test_freeze_window_boundaries` had asserted
  `not freeze_active(2026-09-30)` — it pinned the bug, so it was rewritten (stronger, not weakened) plus
  two new tests; RED-proofed, 189 passed. **The rest of the Sat 09-05 pass is untouched and still open.**
- [ ] CHANGELOG rows; `markdown/doctrine/LESSONS-LEARNED.md` L302–L30x for tonight's field lessons
  (three-filename kill-switch; parser scope hides items above a heading; a plan whose gate pools
  history cannot be reached by adding days; broker expiry sweep unmodeled; early-close blind stack).

---

## 2. Phase 1 — the freeze window (Mon 09-08 → Fri 09-26): review, research, drills, non-shape builds

Ordered by value to the 10-30 decision. Each row: **who** · what "done" means.

### 2a. Further review and auditing (Opus judgment; Sonnet fact-packs)
- [x] **Fleet money path at R1 depth.** — **DONE 2026-09-02 (Opus judgment + Sonnet fact-pack).** Full
  file:line fact-pack answering all six questions; findings filed in queue.md as
  `FLEET-KILL-SWITCH-NOT-LATCHED` (headline) and `FLEET-PATH-AUDIT-FINDINGS` (residuals).
  **HEADLINE — Rule 5 is not latched on the fleet arms, safe-3 included.** Rule 5 says *"Day closed
  for that account. No revenge trades."* Nothing closes the day on this path. Verified cold on three
  legs: `daily_loss_guard.py` (the durable-latch producer) has **zero** references to any fleet arm;
  fleet Rule-5 enforcement is a **live per-tick recompute** at `risk_gate.py:750-755` whose denial
  message reads *"day closed, no revenge trades"* while persisting nothing; and the only production
  writers of `tripped=True` are `daily_loss_guard.py:295` (core), `eod_flatten.py:207` (escalation) and
  `halt_command.py:224/243` (phone). Because equity = cash + position MARK, an arm can breach −30% on
  an underwater open 0DTE, be blocked, then have the mark recover and **silently resume entering the
  same session**. **Calibration, measured: 0 observed breaches to date** — worst intraday draws risky-3
  **−24.4%** (5.6pp from the floor), safe-3 **−18.2%**. Latent and reachable, not yet exercised; it
  becomes a real-money defect the moment anything is armed. The fix is a kill-type risk reduction, so it
  belongs in the **09-29 safety bundle (§3)**.
  **Also found:** no broker-side stop EVER exists (entries are a bare marketable limit; every exit is an
  unconditional market order; the runner ratchet is tick-managed), so 100% of between-tick protection is
  software that must actually run — and the one independent backstop, `Gamma_DeadMansSwitch`, **does**
  cover fleet arms but shows `LastRunTime = 11/30/1999` / `LastTaskResult = 267011` (never run). **Its
  first production fire is 2026-09-02 09:32 ET — exactly what the §1 first-live-day review must check.**
  Plus an UNVERIFIED exit-state batch-save race, PDT computed-but-not-enforced (decide it with the Sat
  09-05 Rule 7 rewrite), and three stale comments.
  **Verified GOOD, no action:** phone-HALT genuinely works tick-to-tick; exits are deliberately never
  halted (2026-08-10 fix); entry idempotency is double-guarded (claim TTL + fail-CLOSED broker query)
  with Task Scheduler `IgnoreNew` preventing overlap; a stale signal blocks entries only, never exits.
  **Correction to this order's own text:** "it reads NO halt file today — confirm" is STALE — it does
  read one, every tick, since B5 shipped 2026-09-01.
- [x] **risky-1 FULL-SEND lane.** — **DONE 2026-09-02 (Opus). The lane is NOT inert end to end, and the
  key is NOT dead — so the 10-30 "strip it" option is a SHAPE CHANGE, not housekeeping.**
  *Producer: disarmed, confirmed.* `build_shared_signal.FULL_SEND_LIVE = False` (line 1208), so the
  full-send ENTRY lane (the extra trades it used to admit via `FULL_SEND_ALLOWED_VERDICTS`) is dead.
  *Consumer: STILL LIVE.* risky-1's `gate_override` still carries `full_send: true`, and
  `fleet_executor._is_full_send` (line 176-178) reads **that key**, not `FULL_SEND_LIVE`. It gates
  `_apply_full_send_min_sizing` (line 300), which is called on BOTH live entry paths (lines 763 and 962)
  and *"clamps qty DOWN to params.min_contracts on EVERY entry a full-send arm makes"*. That function's
  own comment says it outright: *"risky-1 is full_send=true AND live=true"*.
  *Production evidence, not inference:* risky-1's `decisions.jsonl` carries **30 clamp firings** —
  **27× `qty clamped 8->5: FULL_SEND min size`** and **3× `12->5`** — most recently 2026-08-12. So the
  arm's realized sizing is the FULL-SEND min-size profile, not its nominal "risky" sizing.
  **Consequences.** (a) risky-1 appears in the gate's `$/day needed` table (52.45) as a risky-sized arm;
  it is in fact structurally min-sized, so its dollar capacity is capped in a way the table does not say.
  (b) Removing `full_send: true` would CHANGE risky-1's live sizing — that is a shape change and waits
  for 10-30 under §0 regardless of the producer being dead. (c) The `full_send_doc` remains accurate as
  history but its "disarmed" framing is incomplete: say **producer disarmed, sizing clamp still live**.
  *Decision for the 10-30 menu:* strip the key AND the clamp together, or keep both — never strip the doc
  while leaving the clamp, which is the state that would read as inert while still acting.
- [x] **WATCHER-LANE-PROVENANCE-AUDIT** — **DONE 2026-09-02 (Opus). The item's own premise — "5
  extra_signals with zero real trades" — is WRONG, and the reason is the taxonomy gap found the same
  night.** Measured across BOTH P&L surfaces (fill basis `journal/trades.csv` | flat_to_flat
  `analysis/trades-enriched.jsonl`):

  | detector flag | setup label | csv n / $ | enriched n / $ | fires? |
  |---|---|---:|---:|---|
  | `j_vwap_cont_enabled` | VWAP_CONTINUATION | 52 / **−$1,278** | 34 / −$1,046 | yes |
  | `j_vwap_reclaim_fb_enabled` | VWAP_RECLAIM_FAILED_BREAK | 12 / **−$479** | 3 / −$200 | yes |
  | `j_vix_dayside_enabled` | VIX_REGIME_DAYSIDE | 10 / **−$306** | **0 — invisible** | yes |
  | `bollinger_squeeze_enabled` | BOLLINGER_SQUEEZE | 15 / **−$121** | **0 — invisible** | yes |
  | `gap_and_go_enabled` | GAP_AND_GO | **0** | **0** | yes (17,328 emissions) |
  | `db_base_quiet_enabled` | DOUBLE_BOTTOM_BASE_QUIET | **0** | **0** | yes (16,573 emissions) |

  **Four have traded and every one is negative — −$2,184 over 89 fills**, against ribbon_ride's
  +$5,815/302. The extra-signal lane is a net drag while ribbon carries the book. **Two of the four are
  invisible in `trades-enriched.jsonl`** (VIX_REGIME_DAYSIDE, BOLLINGER_SQUEEZE) — that invisibility IS
  the `SETUP-TAXONOMY-UNNORMALIZED-ACROSS-PNL-SURFACES` defect, and it is why the "zero real trades"
  claim looked true: it was read off the enriched surface alone.
  **The other two fire constantly and have NEVER produced a trade** — `gap_and_go` and
  `double_bottom_base_quiet` emit on essentially every tick yet converted 0 entries in the ledger's whole
  life. They cost nothing in P&L but "enabled" implies they do something; they are dead weight until
  someone shows why they never convert.
  **Provenance — and a caveat.** The `j_` prefix looks like a J-ratified marker (`j_vwap_cont`,
  `j_vwap_reclaim_fb`, `j_vix_dayside` carry it; `gap_and_go`, `db_base_quiet`, `bollinger_squeeze` do
  not). **It is NOT a reliable provenance signal** — J-prefixed *strike-override* keys exist for two of
  the non-prefixed detectors (`j_bollinger_squeeze_strike_override_enabled`,
  `j_db_base_quiet_strike_override_enabled`), so J demonstrably ratified parts of lanes whose detector
  flag is unprefixed. Do not use the prefix as a citation; each flag still needs a real one.
  **Also corrected:** `engine_health.dispatch_health` reads **GREEN** ("safe 386/386") because it only
  asks whether ANY `extra_signals` exist on a tick — it is aggregate, not per-detector, so it cannot see
  a single detector going dark. That is the exact G16 silent-dispatch-death class it was built for,
  one level down.
  **STAGED for the 10-30 bundle (params.json is frozen — nothing ships now):** move all four traded
  detectors to SHADOW; decide gap_and_go / double_bottom_base_quiet on a firing-conversion investigation
  rather than a P&L verdict; make `dispatch_health` per-detector. n is small (10–52 each) and these are
  fill-basis figures — this is a disclosure, not a validated A/B.
- [~] **The frozen, never-run preregs — IN PROGRESS 2026-09-02, 52 → 42.** The box said 15; the real
  count was **52**, and the useful split is not age but whether a runner exists: **12 named a runner
  on disk that had simply never been executed; 40 were written with no execution path at all.** A
  prereg with no runner is a wish, not a study — that 77% is the systemic finding, not the backlog
  size. Ten of the twelve were attempted this session:
  | prereg | frozen | outcome |
  |---|---|---|
  | structure-stop | 55d | **SS-B PASSES** — confirms the already-live shape; SS-A/SS-C fail layer (a) |
  | headroom-retest | 55d | RETEST **FAIL**; HEADROOM **INCONCLUSIVE_SMALL_N** (re-open on population only) |
  | measured-move | 55d | **KILL** — shuffle-null p=0.998, Spearman p=0.1155; control trail-only stands |
  | trendline-break-battery | 50d | **KILL 0/12** — every cell negative IS *and* OOS |
  | trendline-fade-battery | 50d | **1/12 survivor → SHADOW**, not armed (see wf caveat below) |
  | trend-alignment-correlation | 50d | **KILL** — every population's Spearman NEGATIVE |
  | level-memory-wire | 49d | **BLOCKED** — runner bit-rotted (orchestrator kwarg drift) |
  | premarket-touch-credit | 44d | **KILL** — p_random 0.21, p_shuffled 0.208, both nulls fail |
  | structure-stop-reference-level | 44d | **REJECT_ALL** |
  | structure-stop-zone-band | 44d | **REJECT_ALL** |
  **Three consolidated reads worth carrying forward.** (1) The structure stop now has three
  independent studies agreeing: the live SS-B shape, trigger-exact reference, zero band, is unbeaten
  on every axis tested. (2) `trend-alignment` KILL has an operational consequence — `Gamma_ContextBundle`
  computes that exact score every 5 min in RTH and its registry row describes a deferred *"Phase 2
  (wiring a validated read into conviction/sizing)"*; that read is now measured and killed, so **Phase 2
  must not be built**. (3) The fade battery's lone survivor cleared BH-FDR and both nulls honestly, but
  its `wf=21.224` comes from `oos_mean/is_mean` with IS expectancy at **$3.79** — it clears a
  *stability* bar by being maximally unstable. The pre-registered bar was **not** changed after seeing
  that; the survivor goes to forward shadow.
  **Method note that cost time and should not be repeated:** runner-exists ≠ runner-works, and an
  import-level smoke test does not close the gap — all 11 named runners returned IMPORT_OK including
  the one that dies at runtime. Only running proves it.
  **ALL 12 NOW ATTEMPTED** — `vwapcont_entry_exit_matrix` → **CONTROL-STANDS** (zero candidates clear
  either bar) and `lbfs_shadow_revalidation` → **FAILS_BAR, shadow only** (headline +$746.60 is entirely
  in-sample: wf −0.44, IS +$1,340, OOS −$593; its "stable" sub-window flag tolerates one hurt third and
  should never be quoted without the thirds beside it). Only `level_memory_wire_ab` remains, blocked on
  bit-rot.

  ### 🚨 The 40 "no-runner" preregs are NOT a research backlog — the count was a monitor defect
  Adjudication started, and stopped, on the first real check: cross-referencing each against result
  artifacts anywhere under `analysis/` (excluding self-hits, prereg-to-prereg mentions, and artifacts
  with no verdict field) found **31 of the 40 already had a real result on disk**. Their `status` field
  was stale; the research was done. `analysis/multi-lane/intraday-null-stageA.json` carries
  `verdict: FAIL_stop_the_lane` and names its prereg explicitly; `analysis/whole-engine-null/` ran the
  same night and returned PASS while its prereg still read *"FROZEN — NOT RUN"*.
  **Root cause:** `prereg_hygiene._results_index()` scanned only the top level of
  `analysis/recommendations/`, so it structurally could not see a result in a sibling subtree. Fixed
  (`993edd42`): recursive index over `analysis/`, plus filename-stem matching, files >3MB skipped,
  1s → 20s. `n_has_results_file` **12 → 105**.
  **The real backlog is 7, of which 3 were filed in the last 48h — so FOUR aged items:**
  `entry-exit-matrix-stop-a` (56d, awaiting STOP-A sign-off, not a run) · `safe3-risky1-gate-retest`
  (47d) · `require-bearish-fill-bar-lift` (29d) · `prereg-pre-tp1-ratchet-cost` (18d).
  **The box's premise was wrong and so was my restatement of it:** it said 15, I counted 52, the answer
  is 4. Guarded so the phantom cannot return — and guarded in the other direction too, since widening a
  "has this been answered?" search is precisely how a monitor silences itself (a test asserts preregs can
  never satisfy each other, and that the reported backlog is neither 0 nor ≥25).
- [x] **BEARISH_REJECTION sign flip** — **DONE 2026-09-02 (Opus). There is NO sign flip by unit of
  account.** `winner_signature.wavify` sets `w["pnl"] = sum(row pnl)`, so Σ(wave) ≡ Σ(trip) by
  construction — a regrouping cannot move a total. Verified: 349 trips → 109 waves, totals identical
  to the dollar. The apparent flip decomposes into two unrelated causes:
  **(1) WINDOW, and it is the whole story.** SIGNATURE spans 2026-04-29→09-01; trades-enriched carries
  BEARISH rows only from 06-26. Just **4 trades before 2026-06-26 are worth +$772** — they alone carry
  the positive sign. Scope SIGNATURE's OWN source to 06-26..09-01 and it reads **−$381** (n=131). Both
  surfaces agree BEARISH is negative in the window that matters.
  **(2) BASIS + an unnormalized taxonomy ($308).** Same window: `journal/trades.csv` (fill basis)
  −$381/131 vs `analysis/trades-enriched.jsonl` (flat_to_flat) −$73/104. **Grand totals reconcile to
  −$11** ($+1,275 vs $+1,286), so neither file is wrong about money — only about attribution. The
  attribution gap is real and filed: trades.csv splits one setup across **case-variant duplicate
  labels** (`VWAP_CONTINUATION` n=45 AND `vwap_continuation` n=7; `VWAP_RECLAIM_FAILED_BREAK` n=3 AND
  `vwap_reclaim_failed_break` n=9), carries an `UNKNOWN` bucket (n=25) and legacy strategy names
  (`bollinger_squeeze` −$121, `vix_regime_dayside` −$306) absent from the enriched taxonomy, while
  trades-enriched has **36 unjoined blank-setup rows worth −$896**. See queue.md
  `SETUP-TAXONOMY-UNNORMALIZED-ACROSS-PNL-SURFACES`.
  **CANONICAL UNIT (declared):** `analysis/trades-enriched.jsonl` flat_to_flat **trip** is the unit for
  behavioural/attribution work; `journal/trades.csv` fill basis is the unit for accounting. Every
  generator must state BOTH its unit and its window — this whole episode was a window difference
  reported as a unit difference.
  **Side effect, disclosed:** SIGNATURE.md was stale against the 09-01 `trades.csv` repair (generated
  20:22 ET, before it). Regenerated 2026-09-02 00:44 ET: fills 521→544, waves 130→137, sessions 49→52,
  **net $3,027 → $2,208**, BEARISH $821→$709. Any number quoted from the pre-repair file is wrong.
- [x] **`planned_stop ≠ executed_stop` (79%) root cause** — **DONE 2026-09-02 (Opus). NOT a bug; a
  field-semantics gap, and neither posted hypothesis was right.** *Mechanism, one sentence:* `planned_stop`
  records the **premium-price floor armed at entry**, but in structure mode that floor is the −50%
  **catastrophe cap** while the operative invalidation is a **SPY chart level** held only in `trigger_level`
  / the `stop_display` string, so the realized exit premium is wherever the contract traded when SPY crossed
  the level and has no reason to equal the recorded number. *Evidence:* structure-mode `planned_stop /
  entry_px` median **0.503** (80% within ±0.03 of 0.50, n=186) vs premium-mode 0.907; the ledger's own
  `stop_display` reads `STRUCTURE@754.00 (cat -50%)` with `premium_stop_pct: -0.5`; **77% of structure
  stop-exits filled ABOVE the cap, median +$0.275/contract** — the chart stop firing before the cap, i.e.
  chart-stop-primary working as designed. Secondary class: **trailed exits are 53/53 = 100% "mismatched"**
  because the chandelier ratchets after entry and nothing writes the ratcheted floor back — median +$1.207
  above the entry-time field at a median **+91.4% realized return**, i.e. they exited in PROFIT, which an
  entry-time stop price cannot describe. Third class: every exit is an unconditional MARKET order, so even a
  premium stop fills at touch ± spread, never exactly at the level. **`executed_stop` field spec for the
  09-29 bundle filed in `queue.md` (`EXECUTED-STOP-FIELD-SPEC`)** — the load-bearing new field is
  `armed_stop_at_exit_premium` (the floor in force at the moment of exit, post-ratchet); without it no
  trailed exit can ever be reconciled, and `stop_exit_slack_dollars` is what the gate's 2¢ slippage
  assumption should be recalibrated against. Pure logging: no entry selection, size, or exit rule changes.
- [x] **safe-3 exit_patch provenance** — **DONE 2026-09-02 (Opus). Provenance EXISTS; the patch is
  PROVABLY INERT; and no, the frozen-window shadow is NOT its validation — there is nothing to
  validate.** *Provenance (written, two places):* `accounts.json#update_note_2026_07_20` carries the full
  EXIT-PARAMETER A/B design under J's directive (*"every fleet arm takes the SAME engine signals but with
  DIFFERENT exit/risk parameters"*) — safe-3 = RIBBON lane, risky-1 = untouched control, risky-3 = wider
  trail; and safe-3's own `note` states the assignment's scope verbatim: the patch forces
  chart-stop-primary + trailing lock onto EVERY strategy the arm trades, *"for ribbon_ride this is a
  **no-op (already the REGISTRY default)**, for vwap_continuation it's a real change"*.
  *Why it is inert, measured:* `RIBBON_RIDE.exit` resolves `stop_mode='structure'` /
  `profit_lock_mode='trailing'` — **byte-identical to the patch**. And safe-3 has traded **59 labelled
  positions across its entire history, 100% ribbon_ride** (54 BULLISH_RECLAIM + 5 BEARISH_REJECTION);
  **0 rows** where the patch could bite. So the override has never changed a single exit decision on this
  arm, and the frozen-window shadow measures the registry shape, not a treatment.
  **Implication for 10-30:** safe-3's "safe × tight" cell is effectively **registry-verbatim ribbon_ride**
  differing from its siblings only by gate and sizing — which is what risky-3's own `_exit_patch_doc`
  already asserts ("safe-3 (registry-verbatim, but a different cell)"). Read the prod-shadow result as a
  test of the registry exit shape under a tight gate, never as a test of the 07-20 exit A/B.
  *Hygiene gap (minor):* risky-3 carries a dedicated `_exit_patch_doc` key; safe-3 and risky-1 do not —
  their provenance lives only in the shared `update_note_2026_07_20`, whose own text is **self-documented
  as STALE** on the control question (risky-3's doc: "risky-1 is NOT the control ... the
  update_note_2026_07_20 text above is STALE on this point"). Filed as part of the fleet findings.
- [x] **Overlapping-tick cessation since 08-15** — **DONE 2026-09-02 (Opus). Neither luck nor unlogged:
  the mechanism is identified, dated and attributable — but the underlying defect is NOT fixed, only
  made unreachable.** *First, a date correction:* the last duplicated minute was **2026-08-14**, not
  08-15, and there have been **12 clean trading days** since (08-17 .. 09-01).
  *Not luck:* measured over the whole ledger (16,954 rows carrying `core_tick_id`, 22 days, the field's
  entire life), duplicates ran 08-04 (2), 08-05 (3), 08-06 (1), 08-10 (4), **08-11 (10), 08-12 (11)**,
  08-14 (2), then zero. Base rate was 7 of 10 trading days; 12 consecutive clean days at that rate is
  ~5×10⁻⁷.
  *The mechanism.* An overlap is only possible when a tick outlives its 60-second slot and the
  fire-and-forget wrapper starts the next one. Per-day intra-tick span (proxy for tick duration) shows a
  cliff: max **94s** with **13** ticks ≥60s on 08-12 → max **5s** with **0** on 08-13, and no day since
  has exceeded 13s or produced a single ≥60s tick. Duplicate counts track it exactly (7 slow → 10 dups;
  13 slow → 11 dups; 0 slow → 0 dups).
  *The cause.* Commit `073469a9` (2026-08-12) disabled the free-model veto on the money path, and its own
  message names the latency outright: *"31.2% accuracy, **60s entry-timing cost**, then passes the same
  trade"* — and critically it *"skips the CALL not just the authority"*, i.e. it removed the round-trip,
  not merely the veto power. `heartbeat_core.py:1092` now reads
  `FREE_MODEL_VETO_ENABLED = os.environ.get("GAMMA_FREE_MODEL_VETO", "0") == "1"`. Guard:
  `test_free_model_veto_disabled_2026_08_12.py`. **So it WAS logged — in a commit about veto accuracy.
  The overlap cessation was an unremarked side effect of a change made for an unrelated reason**, which
  is exactly why this question had to be asked at all.
  ⚠️ **The defect itself is untouched.** The fire-and-forget wrapper still permits overlap; it is merely
  unreachable while every tick finishes in single-digit seconds. **Put any latency back on the hot path
  and overlaps return.** That is why B3's `duplicate_ticks` monitor stays armed and why the §3 09-29
  bundle item (exit-pass pidfile mutex + heartbeat task registered without the fire-and-forget hop)
  is still required rather than closable on this evidence.
- [x] **Alpaca paper fill model vs live** — **DONE 2026-09-02 (Opus): documented from Alpaca's own docs,
  fee model re-verified against LIVE broker rows, and TWO corrections — one to their docs, one to a
  field this repo could easily misuse.**
  *What paper does NOT simulate (`us/paper-trading`):* market impact, information leakage, **price
  slippage due to latency**, order-queue position for non-marketable limits, price improvement, and
  dividends. Orders fill only when marketable and are **matched against NBBO**. Critically: *"your order
  quantity is **not checked against the NBBO quantities** — you can submit and receive a fill for an
  order much larger than the actual available liquidity"*, with random partial fills ~10% of the time.
  Since **every one of our exits is an unconditional market order**, paper fills them at the touch with
  zero latency cost — so the gate's slippage constant stands in for the WHOLE of what paper refuses to
  model, not part of it.
  *⚠️ CORRECTION TO THE DOCS, verified against the live account.* Alpaca's page lists "Regulatory fees"
  among the things paper does not account for. **That is false for this account.** `PA3POKNV46VG` books
  real `FEE` activities with sub-types **ORF, OCC, REG, TAF and CAT**. Trust the account, not the page.
  *Fee model re-verified, so §2d's FEE-RECALIBRATION needs no build — it is already calibrated:* every
  rate in `go_live_gate.FEE_RATES` matches live broker rows — ORF $0.015/contract (5 samples), TAF
  $0.00329 (5), SEC/REG 2.06e-05 per sell-dollar (all 9 observations match under ceil-to-cent), OCC
  $0.025/contract (consistent across 1/2/3/6-contract fills), CAT $0.01/arm-day.
  *The 2¢ slippage constant CANNOT yet be recalibrated — the instrument is nearly dark.* The quote tape
  holds exactly **one session** (`2026-09-01.jsonl`, 310 rows) and `trades-enriched`'s exit-quote join is
  **3/391 = 0.77%**. This item's own plan said "≥20 days by late September"; we have 1. Re-check late
  September — until then 2¢ is a stated assumption, not a measurement.
  *⚠️ TRAP — do NOT use `spread_cents` as a bid/ask spread.* `trades-enriched.jsonl`'s `spread_cents`
  comes from `lib.ribbon` via `heartbeat_core.py:780` — it is the **EMA ribbon spread** (a trend-strength
  measure), NOT the quote spread. Its median reads ~70 "cents" on rows whose real NBBO spread is
  $0.00–$0.02, and the values are 17-decimal floats. I nearly calibrated the 2¢ assumption against it.
  The real quote fields are `exit_quote_bid/ask_before/after` (0.77% populated) and the core ledger's
  `exec.nbbo.spread`.
- [x] **The 13 known-RED tests** — **DIAGNOSED 2026-09-02 (Opus). The count is stale and the two halves
  need OPPOSITE treatments — one is fixture rot, the other is a real interaction bug.**
  *Count:* the order cites 13 (08-29 baseline). The last real verdict
  (`automation/state/guard-watch-full.json`, 2026-08-31 09:55 ET) reads **11,097 passed / 8 failed / 11
  skipped**. **DEFINITIVE full-suite re-run completed 2026-09-02: 9 failed, 11,367 passed, 11 skipped,
  46 deselected, 8 xfailed in 51m49s.** (An earlier note here said "6 currently RED" from targeted
  runs — wrong: two failures were absent from the 08-31 baseline I was working from, and a third is
  order-dependent. Targeted runs are not a substitute for the suite.) **The nightly net has produced no
  verdict since 08-31** — see `GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING`; that is why nobody saw any
  of it. The 9 break down as: 3 boost + 3 trades_enriched (below), plus
  **`test_window_leak_compliance::test_no_py_subprocess_missing_creationflags` — FIXED 2026-09-02**
  (`prereg_hygiene.py:147` shelled out to ripgrep with no `creationflags`, and that task runs nightly at
  16:58 ET, so it would flash a conhost window on J's desktop every night — J's standing #1 priority,
  shipped only the night before in wave 2 B3); **`test_graduated_guards::test_free_model_cost_estimate_is_zero`
  — ORDER-DEPENDENT**, passes in isolation, fails in the suite, so its colour is evidence of nothing
  until isolated (`TEST-ISOLATION-GRADUATED-GUARDS-FREE-MODEL-COST`); and
  **`test_entry_block_watch` — copy drift**, it asserts the alert says "say the word to arm it" while
  the composer now says "Logged for gate review; no action needed from you" (the copy was deliberately
  reworded away from prompting J — fix the fixture, do NOT re-introduce the prompt).
  `test_quiet_mode_weekend_research_2026_08_30` now passes.
  **✅ DEFINITIVE BASELINE, clean run 2026-09-02: `4 failed, 11,400 passed, 11 skipped, 46 deselected,
  8 xfailed` in 46m19s.** Down from 9. Fixed tonight: `window_leak_compliance` (a real nightly popup,
  `6bf61edc`), the 3 `trades_enriched` pins and `entry_block_watch` (`105a6a08`). **The remaining 4 are
  the 3 `cheap_contract_qty_boost` failures — a real tight-ladder interaction bug that stays RED BY
  DECISION until the 10-30 menu — plus the order-dependent `graduated_guards` test.** So
  `Gamma_GuardsFull` now has a trustworthy target: **4 is the expected count, not 0**, and anything
  else is news.
  ⚠️ *One earlier "confirming" run reported 5 and named a 5th failure
  (`test_entry_floor_2026_07_02::test_place_live_wires_floor`). That was MY contamination — I ran
  `git checkout` onto the safety branch while that suite was executing, so it read a mixed tree. The
  test passes cleanly on main. Do not mutate the working tree during a 45-minute measurement; it is
  the same class of error as the test that rewrote the artifact it was verifying.*
  *Half one — FIXTURE ROT (3): `test_trades_enriched.py`* pins an August total of **$1,744** that is now
  **$3,048** as more days accrued. Proven pre-existing (identical with tonight's changes stashed). Fix the
  pin, not the assertion — or better, make it a range/recomputed expectation so it cannot rot again.
  *Half two — A REAL BUG (3): `test_cheap_contract_qty_boost_2026_08_03.py`*, failing
  "expected boosted qty 10, got 5". **This is NOT a stale fixture.** J's verbatim directive was *"if it's
  under point five o for a contract, let's buy ten of them"*; `fleet_executor` applies the boost and then
  hands it to `risk_gate.cap_entry_qty`, and **`max_contracts_per_entry = 5`** — shipped 2026-08-29 by
  PREREG-TIGHT-LADDER — caps the boosted 10 straight back to 5. The knob is **doubly dead**: it can never
  raise qty above 5 (and on bold-tier params, where `min_contracts` is already 5, it changes nothing at
  all), AND its only consumer arm is **risky-3, `status: retired, live: false`**. So there is no live P&L
  impact — but the code no longer does what the directive said, and the guard that caught it is a
  vary-and-assert written for exactly this dead-knob class (C14) sitting on exactly this gates-compose
  cascade (C15). **Leave it RED with this reason recorded; do NOT weaken it.** Resolution is a decision,
  not a fixture edit, and all three options are SHAPE changes for the 10-30 menu: exempt boosted entries
  from `max_contracts_per_entry`, re-point the boost to a live arm, or delete boost + test together.
  *Third sighting of the same root:* risky-3's retirement has now invalidated a prereg
  (`ladder-x-premium`), this boost lane, and its own exit A/B leg. **A retired arm's dependents are not
  swept** — worth a one-time sweep when any arm is retired.
- [ ] **ARCHITECTURE.md refresh** (stale since 06-25, omits the fleet layer that holds 3 of 4 scored
  arms, exit_manager, tight-ladder caps, multi lane). *Done:* current wiring + the mixed live/paper
  process topology (heartbeat_core drives safe-2 + bold-2 only).
- [ ] **Complexity kill-list pass** (Sunday work): one-off `backtest/autoresearch|tools` scripts with
  no importers → `_attic/` (sample said 77%); stale queue items closed; `claude/*` branches reviewed
  and pruned (`git log main..branch` first); `requirements.txt` lockfile. *Done:* counts before/after
  in STATUS; nothing live-path touched.

### 2b. Research (analysis only, $0, freeze-compatible)
- [ ] **Null study weekly** (B1) — the single most important number on the board. Opus reads each
  Friday; a FAIL on P1 (post-08-11) ends any 10-30 arming talk before the gate colour matters.
- [ ] **Stress replay of the current engine** over historical high-VIX windows with real OPRA bars
  (the April 2025 tariff week, Aug 2024, any −2%+ day in 2025–26): what do the −50% cap, structure
  stops and the ladder actually do in a −3% day? Pre-register the questions; label sim-only.
  *Done:* a REGIME-STRESS study + the gate's REGIME COVERAGE block cites it.
- [ ] **XSP as an expression of the same read** — cash-settled (kills assignment/sweep risk),
  Section 1256, ~1/10 SPY notional (finer sizing at $5K). Prereg first: same entries, XSP contract,
  real quotes if available (paper-only support at Alpaca per REGULATORY doc), else labeled sim.
  *Done:* prereg + first battery + an after-tax comparison line. `[FABLE-OR-J]` on whether it ever
  becomes a lane — this month only answers "is it worth a lane".
- [x] **Per-hour and bear-side entry study** — **DONE 2026-09-02 (Opus). Two preregs filed; and the
  audit's own 11:xx candidate is KILLED by the measurement that was meant to support it.**
  *⚠️ 11:xx SIGN-FLIPS BY ERA.* Full window (06-26..09-01) 11:xx = −$599; **post-ladder (≥08-11) 11:xx =
  +$882** (per-trade +$28.45, WR 38.7%, ex-best-day +$107). The combined 11+12 window is −$1,583 on the
  full window but **+$26 — flat — post-ladder**. Shipping the audit's proposed 11:xx+12:xx no-trade
  window would have **removed +$882 from the era we actually trade**. The candidate was an artifact of
  the pre-ladder engine. KILLED; do not carry 11:xx to the 10-30 menu.
  *12:xx survives* — the only hour negative in BOTH eras and ex-best-day in both: −$984 full (n=48),
  −$856 post-ladder (n=18, per-trade −$47.56, WR 16.7%). Filed as
  `analysis/recommendations/prereg-hour-gate-12xx-2026-09-02.json` with nails ERA_FLIP / UNPOWERED /
  CANNIBALISATION / CONCENTRATION. n=18 post-ladder is thin and the prereg says so.
  *Bear side is the strongest candidate on the menu* — unlike 11:xx it does NOT flip: puts −$1,160 full
  (n=144), −$826 post-ladder (n=72, per-trade −$11.47), **negative ex-best-day in both** (−$2,661 /
  −$1,691), against calls post-ladder +$3,709 (per-trade +$44.15, ex-best-day **+$1,692**). Filed as
  `analysis/recommendations/prereg-bear-side-2026-09-02.json`.
  **That prereg refuses to let "disarm" be the default reading.** BEARISH_REJECTION enters on
  `trendline_rejection`, whose trigger is a SLOPED line with no single price, so its structure stop keys
  on a reconstructed level (conviction.py:64). *A directional edge exited badly reads identically to no
  edge at trip level.* The prereg therefore REQUIRES an exit discriminator (re-walk the puts under the
  recorded stop vs a premium stop) before any disarm may be proposed — because **a disarmed lane stops
  generating the data that would refute the disarm**. Nails: EXIT_ARTIFACT / REGIME_BOUND / UNPOWERED /
  DOCTRINE (OP-16 holds both directions ACTIVE; disarming one is a doctrine change needing J, not a knob).
  Neither ships in-window — both are SHAPE changes, 10-30 menu only.
- [ ] **After-tax target.** SPY options = ordinary short-term + wash-sale. *Done:* an after-tax version of
  the $100–200/day target under two illustrative brackets, labeled NOT TAX ADVICE, plus the CPA
  question list for J (§6).
- [x] **First-live-month dollar model for safe-3 — DONE 2026-09-02.** Table lives in
  `LIVE-FLIP-RUNBOOK.md` §4a; producer `setup/scripts/first_live_month_model.py` →
  `analysis/first-live-month/<arm>.json`; guards `test_first_live_month_model_2026_09_02.py` (16).
  Computed for **all six arms**, not just safe-3, since the marginal cost was zero and the comparison
  is the point. **safe-3: P(month<0) 0.322 → 0.164 with the −$400/day cap, month p5 −$1,821 → −$684,
  maxDD p95 −$2,553 → −$1,294.**
  Three things it says that nothing else on the board did: (1) **the −$400 cap does most of the work**
  — it halves P(month<0) and cuts the p5 month by 62% — yet §4's ramp only reaches that cap in
  **Week 2**, so Week 1 runs uncapped where a bad path is −$2,553, ~**48% of a $5.3K account**;
  (2) **the cap has never bound on safe-2 — by $8.67** (worst observed day −$391.33 against a −$400
  cap), so it is untested there, not proven harmless; (3) safe-3 is the better arm on this measure
  (P(month<0) 0.164 vs safe-2's 0.577), consistent with its prod-shadow designation.
  **Note the deliberate frame:** the box asked for bootstraps on *frozen-window days as they accrue*,
  and the frozen window holds ONE day — so this is computed on each arm's full real-fills history
  instead, and says so. It is what the month looks like IF the edge is real; criterion 1 still FAILS
  on every arm, and every tail is a **lower bound** because the entire history is calm-regime.
  **Method cross-checked, not asserted:** the audit's independent safe-2 figures were 0.55 /
  −$1,895 / −$2,225; this producer gets **0.577 / −$1,965 / −$2,293** on the same arm — agreement to a
  few percent on all three.

### 2c. Drills (paper; scheduled, announced in STATUS the day before)
- [ ] **Dead-man's-switch kill drill** — ≥5 kills of `Gamma_HeartbeatCore` mid-session with an open
  PAPER position on **safe-2** (the retiring arm; never the prod-shadow), across different times of
  day; measure time-to-flat (target ≤12 min: 8-min heal window + 2-min DMS cadence + fill).
  ⚠️ heartbeat_core drives safe-2 AND bold-2 in one process: drill only when bold-2 is flat, or accept
  that a bold-2 position gets DMS-flattened and note it in the gate's behavioural window as a drill.
  *Done:* 5/5 flattened, drill log in `analysis/drills/`, runbook §2 box ticked.
- [ ] **Phone HALT drill** (J, 2 minutes): `HALT safe-2` from the phone → breaker tripped, reply
  received; `RESUME safe-2`. Then once with `FLATTEN` on an open paper position.
- [x] **Early-close dry run — DONE 2026-09-02 06:16 ET, and made permanent.** All three branches
  exercised: a real 16:00 day → `EARLY_CLOSE_NOOP`; a forced 13:00 close asked at 06:14 →
  `EARLY_CLOSE_WAIT` naming the 12:30 window; asked at 12:45 → `EARLY_CLOSE_TRIGGER` → full sweep over
  all four arms tagged `reason=EARLY_CLOSE` (so the ledger can tell it from the normal 15:52/15:55
  flatten), every arm `NOOP` because already flat, `EOD_FLATTEN_COMPLETE`. **Pinned as a test rather
  than left as a one-off** (`backtest/tests/test_early_close_dry_run_2026_09_02.py`, 6) because the
  branch that matters is otherwise unreachable until **2026-11-27** — without this, the task's real
  behaviour would first be exercised in production, on a half day, with live positions.
  **Safety property verified, not assumed:** `eod_flatten` gates DIFFERENTLY from `dead_mans_switch`
  and more strongly — the DMS passes `live=(not DRY)` into the broker call, whereas this file's
  `if DRY:` returns with `outcome=DRY_RUN` before reaching the call at all. I asserted the DMS pattern
  here first and the test correctly failed. *Twice* in this session a substring search found the
  module docstring's PROSE mention of `close_all_spy_options` instead of the call site, once
  concluding the order path ran before the DRY guard; the assertion now locates the call through the
  `ast` parser, which is the only way to ask "where is the call" and get an answer about code.
- [ ] **Broker expiry-sweep observation** (paper): on a non-scored account (weekly-1's or safe-2 after
  retirement) hold one ITM 0DTE past 15:30 ET and record what Alpaca PAPER does (does it simulate the
  sweep? at what price?). Ledger the OPEXC/OPASN/OPEXP activity types. *Done:* one observation write-up.
- [ ] **Recovery drill**: TV CDP dead + Alpaca REST 5xx + Windows restart mid-session, each once,
  read-only observation of what the healers and DMS do. *Done:* a table of failure → first automated
  action → time.

### 2d. Non-shape builds (Sonnet; freeze-compatible)
- [ ] CANARY-OUT-OF-SAFE-2 (+ FIFO dust threshold; attribute `canary`).
- [ ] FEE-RECALIBRATION-FROM-BROKER (weekly pull of Alpaca FEE activities vs `FEE_RATES`).
- [ ] CONDUCTOR-2030-FIRE-VS-QUIET-MODE; STATUS-BROKEN-BLOCKS-DRAIN; WEEKLY-CIRCUIT-BREAKER-CORE (prereg
  + build, block-new-entries semantics; SHIP at 09-29 as a kill-type reduction).
- [ ] The 09-29 safety bundle prepared in a branch with tests (see §3) — built now, merged at the checkpoint.

---

## 3. Phase 2 — the 09-29 checkpoint (Mon 09-29 → Fri 10-03)

- [ ] Gate re-run at ≥20 frozen-window days: criterion 5 first real reading, all disclosures, null
  study, regime coverage. **Publish, do not decide.**
- [ ] Ship the **SAFETY bundle** (pre-registered kill-type reductions; each guard + RED-proof + revert;
  one commit each): `time_stop_et ≤15:20` (per B6's measurement) · early-close entry cutoff +
  calendar-relative `_is_rth` · exit-pass pidfile mutex + heartbeat task registered without the
  fire-and-forget hop · `executed_stop_pct/price` logging · weekly circuit breaker (block-only) ·
  safe-2 retirement mechanics (ACCOUNTS from accounts.json, not hardcoded) · canary already moved.
- [ ] **Do NOT ship** anything from §4. If J wants `feed=sip` earlier for data fidelity, that is a
  `[FABLE-OR-J]` trade of clock purity for realism; default is wait.
- [ ] TIGHT-LADDER interim reading published as "interim, not decisive" (its own §5 forbids acting on it).

---

## 4. Phase 3 — 2026-10-30, the decision, and the two branches after it

**The decision inputs (all must exist by 10-30 evening):** criterion 5 verdict on ≥40 days ·
criteria 2–4 · null-study verdict on P1 and P2 · regime coverage line · TIGHT-LADDER H1 result ·
drills 2c all ticked · runbook prerequisites ticked · after-tax line · J's OPRA decision.

**If GREEN:** J's bounded accept/decline (OP-0 #1). If accepted: LIVE-FLIP-RUNBOOK §2–§3 —
J creates and funds ONE live account, live keys in the gitignored secrets store, a NEW arm row
(`safe-3-live`, `status: paused`) so paper safe-3 keeps running as the lab; Day 1 = 3 contracts
≤$0.50 under the live caps; DMS, HALT, early-close, time stop all live; weekly gate; the quote tape
is the paper-vs-live parity instrument. Nov–Dec live at tens of dollars a day.

**If RED (base case):** no arming; write the post-mortem the same night; open the **shape-change
menu** that has been pre-registered all month and ship it as A/Bs on the paper fleet:
- bear-side fix or bear-side disarm (puts −$1,160);
- hour gates (11:xx–12:xx) as a pre-registered no-trade window extension;
- diversification: re-arm one non-ribbon strategy only if its own null passes;
- `feed=sip` + filter-10 recalibration (if OPRA signed);
- XSP lane decision;
- safe-2 exit A/B v2 (single-variable `tp1_premium_pct`).
Then a new 20–40 day window → the next arming question is **2027-Q1**.

---

## 5. Standing cadence for every Opus session until 10-30

1. Orient: `MAP.md` → `HOME.md` (the gate block) → `automation/overnight/STATUS.md` top → this file.
2. Pick the top open box in the current phase; read the matching `markdown/doctrine/fable-judgment/`
   chapter (01 investigate / 02 validate / 03 execute / 04 judgment).
3. Judgment stays with Opus; hands go to Sonnet (`model: "sonnet"`); recurring work becomes a $0 script.
4. Verify cold before claiming (quote the command); commit with a one-line revert; STATUS entry; tick
   the box here; file anything new in queue.md under the audit follow-ups section with a tag.
5. Fridays: gate + null re-run → HOME; WEEK ORDER synthesis for J (12 lines). Sundays: prereg
   adjudication + doc fold (DOC-ARCHITECTURE) + kill-list pass.
6. Never touch a frozen file in-window; never ship a shape change before 10-30; never end a turn
   asking J for permission on sanctioned paper work.

---

## 6. J's items (the only things Gamma cannot do)

- [ ] **OPRA / Algo Trader Plus (~$99/mo):** yes or no. Yes → `feed=sip` + filter-10 recalibration join
  the 10-30 menu (or earlier by your call). No → the paper record stays on delayed indicative quotes
  and the runbook says so in writing.
- [ ] **Phone HALT drill** (2 minutes, any afternoon after B5 lands).
- [ ] **DMS drill window:** say which afternoon(s) the engine may be killed on purpose (paper).
- [ ] **CPA question list** (delivered with the after-tax study): wash-sale exposure at ~500 round
  trips/yr with same-day re-entries; SPY vs XSP treatment; estimated-tax cadence.
- [ ] **Kalshi API key** (unchanged from 08-29).
- [ ] **10-30:** the accept/decline itself, if and only if the inputs in §4 are all green.

---

## 7. Risk register for the window (what could still spoil the 40 days)

| Risk | Monitor | First automated action |
|---|---|---|
| Engine process dies with a position open | `Gamma_DeadMansSwitch` (/2 min) · `heal-engine.ps1` (8 min) | restart, then flatten at 10 min stale |
| Overlapping engine ticks (fire-and-forget wrapper) | `engine_health.duplicate_ticks` (B3) | YELLOW/RED → STATUS; mutex lands 09-29 |
| Flattener cannot reach the broker MCP at 15:55 | Core `eod_flatten.py` at 15:52 is primary; LLM prompts now defer to it | escalation trips the per-account breaker only on a real partial fill |
| Early close (none until 11-27) | `Gamma_EodFlattenEarlyClose` (B2) | flatten at close−30 min |
| Broker expiry sweep from 15:30 | time stop ≤15:20 ships 09-29 | until then: exposure disclosed (2.7% of exits after 15:25) |
| A drill contaminates the scored window | drills on safe-2 only, announced in STATUS | behavioural window notes the drill |
| Someone edits a frozen file | PreToolUse hook hard-block (`GAMMA_FREEZE_OVERRIDE` only for pre-registered kill-type) | blocked |
| The window is "green" on a calm-only tape | REGIME COVERAGE block (B3) + stress replay (2b) | the gate says so in words |
| Stale monitors (the L298 class) | `state_freshness_audit`, `prereg_hygiene` (B3), `Gamma_GuardsFull` nightly | RED to STATUS Known broken |

---

## 8. Change log of this order

- 2026-09-01 21:40 ET — created (Fable 5.1). Wave 2 builders launched; §0 freeze decision recorded;
  hook/CLAUDE.md text changes scheduled for Sat 09-05.
