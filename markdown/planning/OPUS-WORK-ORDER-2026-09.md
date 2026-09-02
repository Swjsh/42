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
- [ ] **09-02 16:30 ET — first-live-day review (Opus, 20 min).** Read `automation/state/dead-mans-switch.json`
  + `automation/state/logs/dead-mans-switch-2026-09-02.jsonl`: fired every 2 min 09:32–15:58? every
  arm `LIVE_NO_ACTION`/`STALE_BUT_FLAT`, zero `FLATTENED`, zero `ERROR`? `engine_health.py` →
  `escalation_flags` GREEN, `duplicate_ticks` clean? Did `Gamma_EodFlatten_Aggressive` reach the
  broker MCP at 15:55 (3rd day) — if not, file the root-cause item (same-second collision with the
  safe flattener? cold MCP start inside a 2-min window?) and consider retiring the two LLM
  flatteners in favour of the Core alone (`[FABLE-OR-J]`: defense-in-depth vs. noise that writes
  false halts). Conductor fires overnight: did any pick a `GATE-BLOCKING` item first?

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
- [ ] `setup/hooks/doctrine.py` `FREEZE_END = 2026-10-30`; freeze banner text names the 09-29 safety
  checkpoint and the override token for pre-registered kill-type reductions.
- [ ] CHANGELOG rows; `markdown/doctrine/LESSONS-LEARNED.md` L302–L30x for tonight's field lessons
  (three-filename kill-switch; parser scope hides items above a heading; a plan whose gate pools
  history cannot be reached by adding days; broker expiry sweep unmodeled; early-close blind stack).

---

## 2. Phase 1 — the freeze window (Mon 09-08 → Fri 09-26): review, research, drills, non-shape builds

Ordered by value to the 10-30 decision. Each row: **who** · what "done" means.

### 2a. Further review and auditing (Opus judgment; Sonnet fact-packs)
- [ ] **Fleet money path at R1 depth.** The audit read `heartbeat_core.py` end-to-end; the fleet arms
  (safe-3 = the prod-shadow candidate!) run `fleet_live.py` → `fleet_executor.py` → `exit_manager.py`
  in a separate process. Walk that path the same way: order types, idempotency, exit management on
  process death, what halts it (it reads NO halt file today — confirm), how `Gamma_FleetExecutor`
  is launched (same fire-and-forget wrapper?), tick timing vs the core. *Done:* a fact-pack with
  file:line evidence and any gap filed with a tag. `[Opus + 1 Sonnet]`
- [ ] **risky-1 FULL-SEND lane.** `a9c157a9` (08-29) disarmed the never-fired FULL-SEND producer;
  accounts.json still carries `full_send: true` and a long doc. Confirm the lane is inert end to end
  (producer flag + consumer), then decide: strip the dead key at 10-30 or keep as documented history.
- [ ] **WATCHER-LANE-PROVENANCE-AUDIT** (HIGH, open since 08-23): 5 extra_signals with zero real trades,
  VWAP_CONTINUATION −$1,046. *Done:* per-signal provenance (J-ratified with citation vs Claude-invented),
  verdict SHADOW/KEEP, staged params change for the 10-30 bundle (params.json is frozen).
- [ ] **The 15 frozen, never-run preregs** (list in `analysis/recommendations/prereg-hygiene.json` once
  B3 runs). *Done:* each is RUN (Sonnet, on the existing harness) or KILLED with a named nail, or
  PARKED with a re-open condition. No "still frozen" survives the month.
- [ ] **BEARISH_REJECTION sign flip** (wave-level +$821 vs trip-level −$73). *Done:* both units scoped
  to 06-26..09-01; one canonical unit declared project-wide (trip = flat-to-flat) and every
  generator labels its unit.
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
- [ ] **safe-3 exit_patch provenance** (`{stop_mode: structure, profit_lock_mode: trailing}`, assigned
  07-20 A/B). *Done:* written provenance + whether the frozen-window shadow IS its validation.
- [ ] **Overlapping-tick cessation since 08-15** — luck or an unlogged fix? *Done:* root cause or
  "unknown, monitor armed" (B3's `duplicate_ticks`).
- [ ] **Alpaca paper fill model vs live** — document exactly what Alpaca simulates (NBBO match, no
  impact, no queue) from their docs; pair with the quote tape (≥20 days by late September) to
  measure paper-exit-vs-quote slippage; recalibrate the gate's 2¢ assumption with data, not a guess.
- [ ] **The 13 known-RED tests** (08-29 baseline: 10,888 passed / 13 failed). *Done:* fixtures fixed
  (never assertions weakened), `Gamma_GuardsFull` reports 0 failed, and STATUS `## Known broken` shows
  the nightly result line.
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
- [ ] **Per-hour and bear-side entry study** for the 10-30 menu: 11:xx/12:xx (−$599/−$984) vs 10:xx/14:xx;
  puts −$1,160. Pre-register as candidate gates; DO NOT ship in-window. *Done:* preregs with kill nails.
- [ ] **After-tax target.** SPY options = ordinary short-term + wash-sale. *Done:* an after-tax version of
  the $100–200/day target under two illustrative brackets, labeled NOT TAX ADVICE, plus the CPA
  question list for J (§6).
- [ ] **First-live-month dollar model for safe-3** (the audit computed safe-2's): 20-day bootstraps on
  the frozen-window days as they accrue; P(month<0), p5, maxDD p95, under the live caps.
  *Done:* a table in the runbook §4.

### 2c. Drills (paper; scheduled, announced in STATUS the day before)
- [ ] **Dead-man's-switch kill drill** — ≥5 kills of `Gamma_HeartbeatCore` mid-session with an open
  PAPER position on **safe-2** (the retiring arm; never the prod-shadow), across different times of
  day; measure time-to-flat (target ≤12 min: 8-min heal window + 2-min DMS cadence + fill).
  ⚠️ heartbeat_core drives safe-2 AND bold-2 in one process: drill only when bold-2 is flat, or accept
  that a bold-2 position gets DMS-flattened and note it in the gate's behavioural window as a drill.
  *Done:* 5/5 flattened, drill log in `analysis/drills/`, runbook §2 box ticked.
- [ ] **Phone HALT drill** (J, 2 minutes): `HALT safe-2` from the phone → breaker tripped, reply
  received; `RESUME safe-2`. Then once with `FLATTEN` on an open paper position.
- [ ] **Early-close dry run**: force the calendar helper to report a 13:00 close on a normal day with
  `DRY=1` → `--only-if-early-close` acts at 12:30; `Gamma_EodFlattenEarlyClose` fires and NOOPs on a
  real 16:00 day.
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
