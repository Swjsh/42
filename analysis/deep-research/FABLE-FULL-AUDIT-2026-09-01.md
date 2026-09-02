# FABLE FULL AUDIT — 2026-09-01

> Successor to [FABLE-FULL-REVIEW-2026-08-29.md](FABLE-FULL-REVIEW-2026-08-29.md). J-directed ("full audit on the 42 trading project. Find our edge… what we are doing right, wrong, improvements, additions, things I'm not saying or thinking of").
> Clock verified at start: `2026-09-01 18:10:02 Tuesday EDT / market_hours=False` (`et_clock.py`). Config freeze active (2026-08-31 → ~09-29).
> **Method (first Fable ultracode run on this project):** MAP → HOME → SHADOW → fresh gate re-run, then a 161-agent workflow: 10 domain readers (hot path, armed config, edge re-derivation from raw fills, validation machinery, ops/autonomy, live-money readiness, doctrine, codebase, data integrity, devil's advocate) → every CRITICAL/HIGH finding attacked by 3 independent refuters (evidence / provenance / materiality; killed on ≥2 refutations) → a completeness critic → 5 gap finders (exchange calendar, broker policy, process isolation, economics, the human control surface) → refuted again. 94 raw findings → 32 survivors + 11 gap survivors; 5 killed (listed in §8 so nobody re-finds them). Machine provenance: [`2026-09-01-audit/findings.json`](2026-09-01-audit/findings.json). Every number below was produced or re-run this session; anything not is labeled UNVERIFIED.
> **This document arms nothing.** Live-money arming stays J's decision alone (OP-0 #1).

---

## VERDICT — one paragraph

**The machine is real and the edge is thin, single-setup, and earned entirely in a calm up-tape; the plan to arm real money in October is arithmetically unreachable under the frozen config, and two safety nets the go-live gate depends on were found broken in the field this week.** Fresh gate (18:11 ET): RED on statistics (all 4 arms, CI-lower 0.33–0.41 vs 1.0), RED on operations (dead-man's switch still absent), RED on prod-shadow (still NOT_WIRED), green on reconciliation and behaviour. Re-derived from raw fills with an independent FIFO: the engine's lifetime book is **+$1,220 on 385 round trips (PF 1.06, WR 25.7%)**; the post-08-11 "ladder" era is **+$2,883 on 15 sessions (PF 1.34)** but **−$154 on the 13 sessions that are not 08-27/08-28**; the whole positive edge sits in **one setup (BULLISH_RECLAIM, +$3,435)** and in **calls (+$2,380 vs puts −$1,160)**, and the entire 62-day sample never saw VIX above 20.6 or a −2.1% day. Book P&L correlates +0.23 with SPY's daily return; **no whole-engine null has ever been run**, so "edge" and "long beta in a rising tape" are currently indistinguishable. To turn the gate green by 09-29, safe-2 would need **+$166/day for 19 straight sessions** (actual: −$7/day); the best arm, risky-1, needs +$115/day (actual: +$50). Meanwhile the kill-switch the flatteners write and the kill-switch the engine reads are **three different filenames**, none connected, and it fired twice this week (08-31, 09-01) without halting anything; the engine's own scheduled-task wrapper is fire-and-forget, so Task Scheduler's overlap guards never applied to the live process. The two HIGH gate blockers from 08-29 got **zero conductor fires** because of a parser scope bug plus a priority order that ranks an unbounded self-audit backlog above queue HIGH items. **Decisions tonight (Gamma-decides, revoke = `git revert`): fix the wiring bugs and build the dead-man's switch now (freeze-compatible), designate safe-3 as the prod-shadow candidate on the frozen window, add the honesty disclosures to the gate, and reframe the calendar: the first real arming decision is early November on the 40-day window, not October.** "Real money before 2027" is still possible; it is no longer the base case.

---

## 0. What changed since the 08-29 review (3 days)

| 08-29 said | 09-01 reality |
|---|---|
| #1 DEAD-MANS-SWITCH, #2 PROD-SHADOW "closeable this weekend by fires" | Neither touched in ~9 fires. Root cause: `task_scorer._active_lines()` scans from `## Active backlog` (queue.md:75) onward; both items sit at lines 66-67 and never enter the ranker. Even if visible, conductor STAGE-1 ranks self-audit gaps (tier 3, unbounded, refilled by a swarm) above queue HIGH (tier 4). Autonomy metric: `trend: regressing`. |
| Config freeze declared | **Held cleanly**: zero commits to any frozen file since 08-31 (`git log`); `git status --porcelain` empty on all 7 domain files. |
| safe-2 exit A/B ships before Monday or never | Killed honestly (two analyses disagreed on the sign of `tp1_premium_pct`); v2 deferred to post-freeze. Correct. |
| Post-ladder "$4/session → $200/session … best evidence the machine is improving" | True as a total (+$2,883 / 15 sessions) and false as a trend: **−$154 ex the two best days** on the 4 active arms (−$762 on all arms per the regenerated SIGNATURE table). SIGNATURE.md's own prose said "still red" next to a +$2,883 table (hardcoded string in `winner_signature.py:366-368`, fixed tonight). |
| Gate RED for "known" reasons | Two new field failures this week: the aggressive LLM flattener could not reach `mcp__alpaca_aggressive__` at 15:55 ET on **both** 08-31 and 09-01, wrote `automation/state/kill-switch.json`, which **nothing reads**. bold-2 was flat both times only because the deterministic Core (`eod_flatten.py`, 15:52 ET) had already broker-verified it. |

---

## 1. The edge — re-derived, then attacked

### 1.1 Numbers (engine-attributed fills, `fills-ledger.jsonl` 2026-06-26..09-01, independent FIFO via `fills_fifo.mine_real_arm_fills`; 385/385 trips match `trades-enriched.jsonl` to the cent)

| Population | n trips | WR | PF | Net | Note |
|---|---:|---:|---:|---:|---|
| Book, all engine fills, 6 arms | 385 | 25.7% | 1.058 | **+$1,220** | includes retired safe-1 / risky-3 |
| Book, 4 active arms (fresh `cost_model` re-run) | 266 | — | — | **+$1,992 as-traded / +$1,892 fee-adjusted / −$272 at 2¢ exit slip** | supersedes the stale 08-18 cost-model.json (−$2,201) |
| Pre-ladder era (≤08-10) | 229 / 28 days | 17.5% | 0.868 | −$1,663 | the engine we no longer run |
| Post-ladder era (≥08-11) | 156 / 15 days | 37.8% | 1.338 | **+$2,883** | matches SIGNATURE.md's table |
| Post-ladder, active arms, ex 08-27 (+$1,952) & 08-28 (+$1,764) | 13 days | — | — | **−$154** | the trend is two days |

Per arm (30/20/26/26 scored days): safe-2 −$7.20/day · bold-2 +$3.75/day · safe-3 +$32.35/day · risky-1 +$49.69/day. All four arms share the same single best day (2026-08-04 = 20–26% of each arm's gross winner dollars; top-3 days = 48–62%).

### 1.2 Where the money actually is (ex-ante buckets, trip level)

| Cut | Pays | Bleeds |
|---|---|---|
| Setup | **BULLISH_RECLAIM_RIDE_THE_RIBBON n=208 +$3,435** | BEARISH_REJECTION n=104 **−$73** (SIGNATURE's wave-level table shows it +$821 on a wider, older population — a sign flip by unit of account, unreconciled) · VWAP_CONTINUATION n=34 −$1,046 · unjoined n=36 −$896 |
| Side | Calls n=241 +$2,380 | Puts n=144 −$1,160 |
| Hour of entry | 10:xx +$1,036 (n=62) · 14:xx +$2,132 (n=55) | 11:xx −$599 · 12:xx −$984 · 09:xx −$26 on n=93 (the most-traded hour is flat) |
| Exit multiple (SIGNATURE) | exits ≥1.3× entry = 26% of fills, ~$23.6K of winner dollars | 1.0–1.3× band: 63 fills, $1,643 — "a small win is worth almost nothing" |

**Read:** the edge is *one* setup, *one* direction, *one* exit shape (let the right tail run), in *two* hours of the day. That is a real, mechanically coherent shape — and it is exactly what a long-beta strategy in a rising tape also looks like.

### 1.3 Regime — the sample has never been stressed

`core-decisions.jsonl` (36,599 rows, 52 dates): daily-max VIX **14.71–20.64**, 3 sessions >20, **zero >21**. SPY **+4.0%** over the window; worst day **−2.01%**; only 3 of 51 days down >1%. There is no crash, no multi-day drawdown, no sustained downtrend anywhere in the evidence that produced the gate numbers, the −50% catastrophe cap conclusions, or the "edge". The gate has no criterion for regime coverage.

### 1.4 Beta-shaped — and untested against a null

Book day P&L vs SPY open→close return: **corr +0.23** (vs |return| +0.35). SPY-up days **+$2,473 (n=20)**; SPY-down days **−$481 (n=20)**. Calls made $3,125 on up days and $123 on down days; puts lose on both. Every null in the repo is feature-level (`null_baseline.py`, gate-cell nulls); the only engine-level null prereg (`exit-policy-beats-null-2026-08-23`) is `UNDERPOWERED -- NOT RUN`. **Nobody has asked whether the whole engine beats (a) random entry times through the same exit machinery, (b) buy one ATM call at 09:35 and hold to 15:40 every day, (c) the mirror-image direction.** What would falsify the beta story: the engine beating the 95th percentile of both nulls on post-08-11 days *and* positive P&L on SPY-down days.

### 1.5 Honest n

r=0.846 across arms (LEVER-CORRELATION): the 4-arm fleet is one bet in four sizes, yet the gate requires four independent per-arm passes (`go_live_gate.py:661 stat_pass = all(per_arm…)`) and the correlated book rollup (P(PF≤1)=0.367 as-traded, **0.573 ex-best-day**) is disclosure only. Entry/exit logic has been stable since 08-11 (15 sessions); the sizing caps since 08-29 (4 sessions with fills). The honest independent evidence for "is the current engine profitable" is ~15 days, 2 of which carry all the profit.

**One sentence:** there is a real right-tail mechanism (bullish reclaims, let the runner run, structure stops) that pays in a calm rising tape; its evidence is 15 correlated sessions, two of which are the profit, and it has never been tested against a null, a down-tape, or real quotes.

---

## 2. The plan's arithmetic — October was never reachable (DECISION)

`go_live_gate.py` pools each arm's **full** engine history (no window argument; `statistical_criterion()` filters by arm only). Appending 19–20 more days changes a 26–30-day denominator, not a fresh window. Two independent computations this session:

| Arm | Existing mean $/day | Needed added $/day for 19 days (zero-variance best case) to reach CI_lo>1.0 | P(pass) appending 20 post-ladder-like days |
|---|---:|---:|---:|
| safe-2 | −$7.20 | **+$166** | 0.00 |
| bold-2 | +$3.75 | +$138 | 0.02 |
| safe-3 | +$32.35 | +$137 | 0.13 |
| risky-1 | +$49.69 | +$115 | 0.10 |
| Book | — | — | 0.03 |

No arm has ever strung more than 3–4 consecutive positive sessions. A standalone 20-day window resampled from the good era passes the as-traded+ex-best-day bar only 9–39% of the time. Separately, **two frozen clocks disagree**: the 08-29 review says Sep 1–29 → arm early October; `PREREG-TIGHT-LADDER-2026-08-28` freezes a 40-trading-day window closing **2026-10-30** and frames "the November live question." Nobody reconciled them.

**Decision (Gamma-decides; written here tonight, CLAUDE.md:65 text edit lands Saturday 09-05 per Rule 9; revoke = `git revert`):**
1. **One governing clock.** The frozen-config window opened 2026-09-01. The first arming *decision* is at the TIGHT-LADDER close, **2026-10-30**, on ≥40 scored days. The 09-29 gate re-run is a checkpoint, not an arming date.
2. **What "GREEN" means for arming.** Criterion 5 (prod-shadow: the designated candidate profile, scored on the frozen window, net of the A1 cost model, all three views) + criteria 2–4 green. Criterion 1 (pooled lifetime per-arm PF) remains reported as lifetime robustness disclosure; it is not the arming bar, because it structurally cannot clear on a history that includes an engine we no longer run. This is not bar-softening — the frozen window is the harder test (it cannot borrow 08-04).
3. **Expectation set honestly:** the base case is that no real money is deployed in 2026. The path that keeps "before 2027" alive is: freeze holds → 40 clean days → criterion 5 green net of costs → J's bounded accept/decline in early November → a small live pilot in November/December under the live caps ($1,000/position, $400/day, 5 contracts). If the window scores like July, the correct real-money allocation is $0 and the gate saying so is the product working.

---

## 3. The map J asked for — RIGHT / WRONG / IMPROVE / ADD / BLIND SPOT

Severity is real-money impact after refutation. "Status" = what happened tonight or where it lives. Ids point into `2026-09-01-audit/findings.json`.

### 3.1 RIGHT — protect these (each independently re-verified tonight)

- **Deterministic core + byte-identical parity.** No LLM on the hot path; `heartbeat_core.py` calls the backtest's own `engine_cli`; tick integrity 772/772 rows/day for 10 straight days, 89/90 PLACED orders match a fill (the 90th is an unfilled limit).
- **The right-tail exit machine and structure stops.** Exits ≥1.3× carry ~$23.6K of winner dollars; the 08-28 identical-contract natural experiment (structure stop +195% vs premium stop −19%) retired risky-3 correctly; `pre_tp1_ladder` closed the give-back leak (19/45 → 0/14 round-trips-to-loss).
- **Live risk caps are far tighter than the doctrine text** (08-29 tight-ladder): $1,000/position, $400/day, 3–5 contracts → worst trade ≈ $500 (9% of $5.6K), worst day 7% — not the 15–25%/30% Rules 5/6 imply. Protect this; fix the text (§3.2).
- **Never-average-down is code, not prose** (`is_flat_spy_options`, 9/9 tests, RED-proofed, no-bypass signature pinned) — J's costliest historical pattern is guarded.
- **Start-of-day equity capture** is deterministic and un-blockable by LLM/router outages (`daily_loss_guard.rearm`, broker REST).
- **Reconciliation to the cent** on all 4 arms (fee-adjusted diff ≤ $1.04); FIFO matcher (`fills_fifo.py`) verified 385/385 against an independent path.
- **Manual-trade handling is protective, not hostile:** adoption applies only a −50% cap + time stop and never overrides J's exit; a position J closes in the app is reconciled safely in ~2 ticks (2-consecutive-flat-reads prune).
- **The single broker surface** (`fleet_broker.py`), the incident-hardened hidden launcher (`_shared.ps1`), quiet mode (fired on schedule at 18:17 ET tonight, trading chain exempt), github audit **GREEN** on 13,335 tracked files, secrets gitignored.
- **The regulatory research** (FINRA PDT repeal confirmed live on both accounts) and the doctrine hooks (fail-open verified, 187/187 tests, freeze override token exists).
- **The adversarial process itself:** 5 of 37 HIGH findings were killed by independent refuters (§8). Trust the process, not the narrator.

### 3.2 WRONG — defects and false beliefs

| Sev | Finding | Evidence | Status |
|---|---|---|---|
| **CRITICAL** | **Kill-switch is a 3-way filename mismatch.** Engine reads `(STATE/"kill-switch")` bare (heartbeat_core.py:2646, j_intent_executor.py:219) — zero writers. `eod_flatten.py:167` writes `kill-switch-{arm}.json` — zero readers. The LLM flattener wrote `kill-switch.json` on 08-31 and 09-01 — zero readers. The only enforced halt (`circuit-breaker.json.tripped`) is unaware of all three and is re-armed every premarket. Bare-name path is also global (would halt both accounts — Rule 5 isolation). | logs `eod-flatten-aggressive-2026-08-31/09-01.log`; `kill-switch.json` repeat_count=2 | **Fixing tonight (W2):** escalations trip the per-account breaker; rearm refuses while unresolved; engine_health goes RED on any escalation flag; LLM prompts consult the Core's 15:52 result first; today's false flag archived with resolution. |
| **CRITICAL** | **Fire-and-forget wrapper defeats overlap guards.** `Gamma_HeartbeatCore` runs `wscript → run_exe_hidden.vbs (shell.Run …, False) → pythonw`, so `MultipleInstances=IgnoreNew` / `ExecutionTimeLimit=PT1M` are measured against wscript's millisecond lifetime. Overlapping live ticks are ledger-proven (3 distinct `core_tick_id`s writing inside one minute on 08-11; a documented −$371 duplicate-entry incident 08-14 led to the entry claim-lock). Entries are now locked (`_acquire_claim`); **exits are not.** | L275/L277; `core-decisions.jsonl` | Frozen (heartbeat_core.py, run-heartbeat-core.ps1). Queue for 09-29: pidfile mutex around exit management + fix the vbs for this task. Interim: duplicate-tick monitor (queued). |
| HIGH | **Conductor never picked the gate blockers** — parser scope bug (items above `## Active backlog` invisible) + priority order (self-audit tier 3 > queue HIGH tier 4). | STATUS fires 08-31..09-01 "Fell through to STAGE-1 priority #3" ×7 | **Fixing tonight (W3).** |
| HIGH | **Behavioural PASS measures a dead ledger.** `rule-breaks.jsonl` has 1 row (2026-05-18), untouched since 06-15; `mistakes.md` last entry 06-15; a documented 08-20 anomalous entry reached neither. Gate reports `0 rule breaks → PASS`. | go_live_gate.py:527-590 | **Fixing tonight (W5):** PASS_UNVERIFIED when the ledger is stale. Writer restoration queued. |
| HIGH | `planned_stop ≠ executed_stop` in 79% of premium-stop exits (122/154); still no `executed_stop` field anywhere. Consumers are 4 analysis artifacts (not the gate, not preregs). | queue.md:24, open since 08-23 | Post-freeze (touches exit_manager). Root-cause read-only now. |
| MED | `journal/trades.csv` actively corrupting: 25/556 rows overflow the 44-col header (unescaped JSON), newest 08-25; flagged 07-18 with 2 rows, never fixed. pandas cannot parse the file. | csv sweep | Queued (journal writer, not frozen). |
| MED | SIGNATURE.md argues with itself ("still red" vs +$2,883). | winner_signature.py:366-368 | **Fixing tonight (W4):** conditional prose + ex-best-2-days column. |
| MED | 15 preregs frozen 18–27 days, self-labeled NOT RUN, zero consumers; 13/14 recommendations-log entries in 30 days still `pending`; 400+ distinct top-level keys across 121 prereg JSONs; one malformed JSON. The loop files, it does not close. | census | Queued: nightly stale-prereg flagger; schema canon. |
| MED | Stale queue items describe fixed defects: POSTFIX-RECENCY-CHECK-UNSOUND-REPLAY (fixed 08-08, `56c2cdc9`), G7-ACTIVATE-EOD-FLATTEN-CORE (active since 07-09). | git log | Closed tonight in queue.md. |
| MED | bold-2 reverted to OTM-2/OTM-3 on 08-20 (rail fired: ATM −$808 vs OTM +$406) — correct — but `aggressive/params.json` doc field and `strike_selection.py` docstring still say ATM is live; 27 SKIP_MIN_PREMIUM_FLOOR in 10 sessions vs 0 on the 3 ATM arms. | heartbeat_core.py:2665-2679 | Doc fix queued (params.json doc field is frozen; docstring is not). |
| MED | CLAUDE.md drift: Rule 7 PDT text and "both accounts grow $5K→$10K→$25K+" flagged stale 08-18, unfixed; `tp1_qty_fraction 0.8/0.667` is a **shadowed** value (strategies.py hardcodes 0.667 both accounts; `dead_knob_audit` 6 SHADOWED keys, known since 08-17); `decisions.jsonl` (dead since 06-25, 63 rows) cited 3× as the live ledger (live = `core-decisions.jsonl`). | dead_knob_audit fresh run | Saturday 09-05 Rule-9 doc pass. |
| MED | The "3-strategy registry" is one live strategy: `vwap_continuation` and `vwap_reclaim_failed_break` disarmed via `extra_setup_exec_armed`; 5 of 7 extra_signals evaluated every tick have **zero** real trades ever; 80% of trips are two ribbon setups. This is the mechanism of r=0.846. | strategies.py, params.json | Tracked HIGH (WATCHER-LANE-PROVENANCE-AUDIT, 08-23, pending). |
| MED | A $10 BTC/USD round trip runs nightly **inside the safe-2 account** (dress_rehearsal canary, 155 fills) — contradicts the crypto twin's "never a fleet/core account" rule and CLAUDE.md's "trading loop retired 06-17"; FIFO float dust makes `pnl-statement.json` report 16 phantom open lots (broker confirms flat). Not contaminating the SPY edge (only 10 real manual option fills, last 07-17). | fills-ledger | Queued: move canary to the twin account; fix dust threshold. |
| MED | Quiet mode disables the documented 20:30 ET conductor fire (`Gamma_Conductor` not in ESSENTIAL) — a third of nightly throughput, undocumented. STATUS `### BROKEN` blocks (CHART-DRAWING stale since 06-29, TRENDLINE-DRAW since 08-27) recur every 30 min with no drain to queue. | quiet_mode.py; STATUS.md | Queued. |
| LOW | 3 tests RED since 08-29 (`test_cheap_contract_qty_boost`: the new $5 cap clamps the qty-10 boost — the cap is right, the fixtures are stale); tracked MED. Two expired 64-day-old levels still ship in key-levels.json (engine-side `_level_expired` neutralizes). `current-position*.json` still git-tracked (L214 class). `feed=iex` + filter-10 `vol_mult=0.7` ratified on SIP (documented 08-07, untracked). | various | Queued / post-freeze. |

### 3.3 IMPROVE

- **Gate honesty (shipping tonight, W5):** effective-n block, frozen-window view per arm and book, plan-reachability $/day line, PASS_UNVERIFIED on stale ledgers, criterion 5 wired.
- **HOME.md's one number.** It shows day P&L per arm (the number that invites intervention) and nothing about the gate. Add: frozen-window book PF ex-best-day, days scored / days needed, P(pass at window end). Generator change in `obsidian_vault_sync.py` (queued).
- **Prereg hygiene:** canonical `status`/`verdict` field, nightly flag for FROZEN/NOT RUN > N days with zero consumers; a mechanical graveyard check before Chef cooks (doctrine names "prevent zombie resurrections"; nothing enforces it).
- **Hot-path size:** 7 modules breach the 800-line rule (heartbeat_core 3,309; filters 2,342; risk_gate 1,724; fleet_executor 1,613; build_shared_signal 1,440); `_execute` is 521 lines / cyclomatic 82; `check_order` 378 / 44. The tight-ladder-vs-boost regression lives in exactly this kind of function. Post-freeze: extract `_execute` and `check_order` into named steps with unit tests.
- **Repo hygiene:** `requirements.txt` declares 8 of 66 installed packages, no lockfile; 1,039 of 1,944 backtest `.py` files are flat one-off scripts (77% of a sample have no importers); 35 `claude/*` branches; 3,014 dirty tracked files; `analysis/deep-research/` grew 139 files in August with zero folded (DOC-ARCHITECTURE's own fold rule is not operating); ARCHITECTURE.md stale since 06-25 and omits the fleet layer that holds 3 of 4 scored arms.
- **Fee model:** reconciliation uses a static FEE_RATES dict calibrated once (08-18); Alpaca's FEE activities are available and unpulled. **Exit slippage:** the gate's cost-adjusted view uses a fixed 2¢/contract; the quote-tape recorder has ~1 RTH session of data (310 rows, 09-01) and 3/391 exits joined. Let it accrue ≥20 days, then recalibrate.
- **Levels are zones** (J 07-17): 7 of 20 active levels still on the never-validated default width, 5 (all MEMORY_RES_*) still point levels.

### 3.4 ADD

- **Whole-engine null study** (pre-registered, analysis-only, freeze-compatible): random entry times through `walk_exit_manager` on real OPRA; buy-ATM-call/put-daily baselines; opposite-direction; scored on post-08-11 and frozen-window days and on SPY-down days. Published with each Friday gate re-run. This is the single most important research item on the board.
- **Dead-man's switch** — shipping tonight (W1) as an independent scheduled watchdog; then the runbook's 10-kill drill.
- **Early-close calendar awareness** (see §4). Must ship before 2026-11-27.
- **Broker-sweep-aware time stop** (see §4): pre-register `time_stop_et 15:40 → ≤15:20` as a kill-type reduction for 09-29.
- **Phone-reachable HALT** (Discord command that trips the per-account breaker and optionally flattens) — a hard go-live prerequisite.
- **Duplicate-tick monitor** over `core-decisions.jsonl` (same-minute per-account duplicates) until the wrapper/mutex fix lands.
- **Regime-coverage line in the gate** (or an explicit waiver) — a GREEN gate on an all-calm window must say so.
- **Break-even and after-tax lines** (§4).
- **Weekly / multi-day circuit breaker** for core arms (only the weekly lane has one).

### 3.5 BLIND SPOTS — the things J is not saying or thinking of

Detailed in §4. In one line each: the edge may be beta; the sample has never been stressed; Alpaca liquidates expiring ITM longs from 15:30 ET on its own terms; two 13:00 early-close days sit inside the target window and nothing in the stack knows; every paper decision was made on delayed/indicative option quotes; no option position ever has a broker-side stop; there is no phone-reachable stop; the first live month for safe-2 is a coin flip to be negative with a plausible −$1.6K to −$2.2K drawdown; the runbook's first live account is the arm scheduled for retirement; SPY options are taxed as ordinary short-term gains with wash-sale exposure (SPX/XSP are not); the rig's known cash floor is ~$299/mo against a per-arm edge of −$7 to +$50/day; and the research machine (155 tasks, 1,177 commits in August, 153 open queue items, 121 preregs, 6,623 tracked markdown files) is now larger than the edge it studies and is eating the verification bandwidth the go-live path needs.

---

## 4. Real-money blind spots — mechanism, evidence, what to do

1. **Alpaca's 15:30 ET expiration sweep.** Alpaca's own options doc (fetched live tonight): from 3:30pm ET on expiry day it evaluates every expiring position; an ITM long the account cannot afford to exercise (every arm at ~$5.6K cannot cover one SPY contract) is **liquidated by Alpaca "while it's still ITM"**, and "positions slightly OTM may also be liquidated." Our time stop is 15:40, EOD flatten 15:52/15:55 — all *after* the broker starts. Zero handling of `OPEXC/OPASN/OPEXP` activities anywhere in the repo. Only 15/556 historical exits landed after 15:25, so exposure is small but it is unmodeled and invisible in paper. **Do:** pre-register `time_stop_et → ≤15:20` for 09-29; log/reconcile any broker-initiated close separately.
2. **Early-close days 2026-11-27 and 2026-12-24 (13:00 ET).** Verified against the live broker calendar. `heartbeat_core._is_rth` is `weekday()<5 and 9.5<=h<=16.0` (first line of `main()`, no calendar); entry cutoffs 09:35/15:00 and the time stop 15:40 are fixed clocks; EOD flatten fires 15:52/15:55; Task Scheduler triggers are plain Mon–Fri. `engine_health.market_is_open()` is holiday-aware (built after the 2026-07-03 incident) but is never called by the engine and its cache discards the `close` field. On either date a 0DTE opened before 13:00 has no automated exit before it expires; an ITM contract auto-exercises into ~$77K of stock per contract. Invisible in paper. **Do:** persist `close` in `calendar.json`, make `_is_rth`/entry cutoff/flatten calendar-relative (heartbeat_core is frozen → ship 09-29; ample margin before 11-27).
3. **Indicative option quotes.** `analysis/data-tier/summary.json` (16:20 ET today): all 4 arms `option_opra_ok: false ("OPRA agreement is not signed")`, live path inferred **INDICATIVE (delayed trades, modified quotes)**, stock on IEX. Every premium-floor check, TP1/stop evaluation and paper "fill" in the track record used a derived, delayed feed. The live account's tier is an unchecked runbook box (Algo Trader Plus ~$99/mo) and buying it does not fix filter-10's SIP-ratified `vol_mult=0.7` running on IEX volume (~3.6% of SIP). **Do:** sign OPRA + `feed=sip` + re-derive `vol_mult` as one paired post-freeze item; treat paper→live fill parity as unknown until the quote tape has ≥20 days.
4. **No broker-side stop, ever.** Alpaca rejects bracket/OTO/OCO for options (422/42210000, `fleet_broker.place_bracket` cascades to a bare limit). Every exit is a software `market_sell` on a ~1-minute tick. If the process dies, nothing at the broker protects the position until the 15:52 flatten. The dead-man's switch (W1) is therefore the *only* backstop, not hardening; `heal-engine.ps1` restarts the process (8-min threshold) but never flattens.
5. **The human control surface.** From a phone J has Discord (approve/shelve bus + Q&A; the responder's own denylist makes "kill switch" capture-only) and the Alpaca app (close a position by hand; the engine reconciles it safely but can re-enter next tick). `GAMMA_CORE_ARMED` is hardcoded `'1'` in a tracked `.ps1` read at process start. There is no single "flatten everything and disarm" action anywhere. **Do:** Discord `HALT <arm>` → per-account breaker tripped (the field actually read) + optional close-all; make it a go-live prerequisite.
6. **First live month, in dollars.** Trade-level Kelly: safe-2 **−0.022**, bold-2 −0.007, safe-3 +0.057, risky-1 +0.033; average entry cost 5.5–8.2% of equity (above full Kelly for safe-2/bold-2/risky-1; safe-3 slightly below its own). 20-day month bootstrap for safe-2: all-history P(month<0)=**0.55**, p5 −$1,895, maxDD p95 −$2,225 (40% of equity, pre-cap days so an upper bound); post-ladder P(month<0)=0.21, p5 −$941, maxDD p95 −$1,586. Nobody had modeled this. The runbook's "Day 1 = 1 contract" cannot execute (`MIN_CONTRACTS ≥ 3` hard-denies); the runbook cites "TASK A2" ruin numbers whose source is not findable (UNVERIFIED).
7. **Wrong first account.** LIVE-FLIP-RUNBOOK §1 says safe-2 first; the 08-29 consolidation handoff (J's directive) retires safe-2 at window close and consolidates toward safe-3 + risky-1; safe-2 is the only arm negative on its full sample. Decided tonight: **prod-shadow candidate = safe-3** (W5); runbook §1 pointer added.
8. **Tax.** SPY options are equity options: ordinary short-term gains plus wash-sale exposure at ~500 round trips/yr with same-day same-symbol re-entries — the wash-sale pattern by construction. SPX/XSP are Section 1256 (60/40, wash-sale exempt, cash-settled — which also removes the assignment risk in items 1–2). Documented in REGULATORY-BROKER-LANDSCAPE §Q5 and COST-REALISM §5 (the critic corrected the audit's "zero coverage" claim), but no after-tax number exists and no CPA has been consulted. XSP as an *expression* of the same read has never been evaluated. **Do:** an after-tax version of the $100–200/day target before any live flip; evaluate XSP in the lab (not a config change).
9. **Break-even.** Known cash floor ≈ $299/mo (Claude Max $200 + proposed data $99; TradingView Plus cost is nowhere in the vault). Required edge to cover it ≈ $14/day. safe-2 full-sample never; post-ladder +$41/day covers 2.9×; risky-1 +$50/day covers 3.5×. Linear "grow the account" scaling is already broken by the $1,000 flat position cap (binding below the pct caps at today's equity). The list-price token estimate ($3,309 trailing-7d; $24–$1,908/day) is not cash under the flat plan, but as a compute-intensity proxy it runs 10–100× the edge.
10. **Complexity as risk.** 155 `Gamma_*` tasks, 1,177 commits since 08-01, 2,413-line queue with 153 open items, 121 preregs, 6,623 tracked `.md` (~479 human-written), 583K lines under `backtest/`. Verification bandwidth, not dollars, is the binding constraint — the freeze week's fires went to self-audit triage, live-watch archives and popup fixes while the two gate blockers sat. Simplification target for the post-freeze weekend: kill list (dead extra_signals, 15 frozen-never-run preregs, stale queue items, one-off scripts to `_attic`), keep list (§3.1).

---

## 5. Decisions made tonight (Gamma-decides; each reversible; revoke = `git revert` the named commit)

1. **Build the dead-man's switch now** as an independent scheduled watchdog (W1) — the freeze exempts kill-type risk reductions and it touches no frozen file.
2. **Fix the kill-switch wiring** (W2): escalations trip the per-account circuit breaker; premarket rearm refuses while an escalation is unresolved; engine_health RED on any escalation flag; LLM flatteners consult the Core's result before escalating; today's false flag archived with its resolution.
3. **Fix the conductor** (W3): parser scans the whole queue; new tier 2b GATE-BLOCKING above self-audit; explicit "freeze = the hook's file list, nothing else."
4. **Designate safe-3 as the prod-shadow candidate** on the frozen window 2026-09-01→09-29 with the 40-day extension to 10-30 (W5); wire criterion 5; add effective-n, frozen-window, reachability and PASS_UNVERIFIED disclosures. Pass logic of the overall gate unchanged tonight (Rule 9).
5. **Reframe the calendar** (§2): first arming decision 2026-10-30; October arming was never reachable; base case = no real money in 2026; CLAUDE.md:65 text edit Saturday 09-05.
6. **Fix the generators** (W4): wikilink false positives (58 → real count), SIGNATURE era prose conditional + ex-best-2 column.
7. **Queue, with owners and dates:** whole-engine null prereg; early-close calendar fix (before 11-27); `time_stop_et ≤15:20` prereg; phone HALT; duplicate-tick monitor; pidfile mutex + vbs fix for the heartbeat task (09-29); trades.csv writer fix; canary out of safe-2; HOME.md one-number; prereg hygiene; fee recalibration; OPRA+SIP+vol_mult paired item; runbook §1/§4/§5 rewrite against the live caps; Rule 7/Goal/tp1/decisions.jsonl doc pass (Saturday).

**Not decided by Gamma (J's alone):** the live-money accept/decline itself (OP-0 #1), when criterion 5 turns green; the Kalshi key; any paid subscription (OPRA/Algo Trader Plus, ~$99/mo) — recommended as a go-live prerequisite, not bought.

---

## 6. Shipped tonight (5 Sonnet builders → independent verifier → adversarial reviewer verdict **SHIP**; every claim below re-checked cold by this session)

| # | What | Proof (this session) | Revoke |
|---|---|---|---|
| 1 | **Dead-man's switch** — `setup/scripts/dead_mans_switch.py` (independent, pure Python, no LLM): flattens via broker REST only when an arm's decision ledger is >10 min stale (after `heal-engine.ps1`'s 8-min restart window) AND the broker read is OK AND it holds an open SPY option; fail-closed on action, fail-open on process. Task `Gamma_DeadMansSwitch` weekdays /2 min 09:32–15:58 ET; added to quiet-mode ESSENTIAL. | `pytest tests/test_dead_mans_switch_2026_09_01.py` → `13 passed`; RED-proof (STALE_MIN=999999 → 4 failed); `Get-ScheduledTask` → `State: Ready`, `NextRunTime 9/2/2026 7:32 MT`, `Interval PT2M`, `Duration PT6H26M`; gate → `2. OPERATIONAL [PASS]` / `dead_mans_switch… [PASS] 13 passed` | `Unregister-ScheduledTask -TaskName Gamma_DeadMansSwitch -Confirm:$false` |
| 2 | **Kill-switch wiring** — `eod_flatten.py` escalation now trips the per-account `circuit-breaker.json` (`tripped` + `escalation_unresolved`); `daily_loss_guard.rearm()` refuses to clear while unresolved; `engine_health` gains CRITICAL `escalation_flags`; both LLM flatten prompts consult the Core's 15:52 result first and never write the bare file. Today's false flag archived with resolution. | `61 passed` (new + eod_flatten/daily_loss_guard/engine_health suites); RED-proof on the rearm refusal; `engine_health.py` → `escalation_flags: no unresolved escalation flags`; `automation/state/kill-switch.json` gone, `archive/kill-switch.resolved-2026-09-01.json` present | `git revert` the session commit |
| 3 | **Conductor picker** — `task_scorer._active_lines()` scans the whole queue (prefix items were invisible); `conductor.md` STAGE-1 tier **2b GATE-BLOCKING** above self-audit; freeze scope stated as the hook's file list only; both blockers tagged. | `task_scorer.py --all` now lists PROD-SHADOW-ARM-DESIGNATION (DMS is checked off); `82 passed` task_scorer suites; RED-proof (old gate → 3 failed) | `git revert` |
| 4 | **Go-live gate** — criterion 5 wired to `automation/state/prod-shadow-designation.json` (arm **safe-3**, window 2026-09-01→09-29, min 20 days; 40-day view to 10-30); FROZEN-CONFIG-WINDOW, EFFECTIVE EVIDENCE, PLAN REACHABILITY disclosure blocks; behavioural rule-breaks → `PASS_UNVERIFIED` on the stale ledger. Pass logic unchanged. | gate → `5. PROD-SHADOW [FAIL] status=INSUFFICIENT_DAYS · arm=safe-3 … days_scored=0/20`; reachability recomputed independently: safe-3 $136.58/day, safe-2 $166.33, risky-1 $115.39, bold-2 $137.64 (match §2); `34 passed`; RED-proof (8 failed) | delete the designation file (→ NOT_WIRED) |
| 5 | **Generators** — `obsidian_vault_sync.py` resolves extensionless wikilinks to `.json`; `winner_signature.py` era prose conditional on sign + `ex-best-2-days net` column. | MAP.md `broken wikilinks: 33` (was 58; remainder are memory-mirror slugs); SIGNATURE.md era table now carries the column (post-ladder **−$762 ex-best-2 on all arms** vs the audit's −$154 on the 4 active arms — same conclusion, wider population); `58 passed` | `git revert` |
| 6 | **Preregs filed** (frozen, not run): `prereg-whole-engine-null-2026-09-01.json`, `prereg-time-stop-broker-sweep-2026-09-01.json`. **Docs:** ROADMAP.md dated update; LIVE-FLIP-RUNBOOK §1 supersession note; queue.md follow-ups section (19 items) + 3 stale items closed; STATUS.md REVOKE entry; CHANGELOG row. | files on disk; `git status` | delete / revert |

### 6b. Wave 2 (same night, 21:30–23:00 ET; 8 Sonnet builders → verifier → reviewer SHIP after one fix round)

| # | What | First reading / proof | Revoke |
|---|---|---|---|
| 1 | **Whole-engine null study runner** `setup/scripts/whole_engine_null.py` (per the prereg; 300 resamples/day disclosed; cache-warm, 0 network fetches) + task `Gamma_WholeEngineNull` Fridays 16:55 ET | **Verdict WITHHELD (harness unreliable):** the exit walker reproduces the engine's own realized fill signs on **79.3%** of 121 P1 entries (bar 85%, bias −$20.76/trade). Mechanical sub-checks are all green on the raw numbers (engine P1 +$3,562 > N_a p95 $2,546; > N_b_call −$2,642 + IQR; P3 +$19 ≥ 0; N_c −$4,676 ≤ 0) and are published as `mechanical_verdict`, but they describe the walker, not the engine, until fidelity clears. A review pass promoted this to PASS because the frozen JSON did not literally name V9; **reversed** — the rule is doctrine (02-VALIDATION V9) and is now a dated addendum in the prereg (`addendum_2026_09_01_validator_fidelity`). Root-cause candidate: 94/121 rows have no real chart-level `trigger_level` in `trades-enriched.jsonl`. **Top research item: WALKER-FIDELITY-TRIGGER-LEVEL.** | `Unregister-ScheduledTask Gamma_WholeEngineNull`; `git revert` |
| 2 | **Early-close flatten** — `setup/scripts/market_calendar.py` (calendar.json gains `early_closes`), `eod_flatten.py --only-if-early-close`, task `Gamma_EodFlattenEarlyClose` 12:32 ET, engine_health `early_close_today` | 10 tests, RED-proof (threshold 30→5 min fails); NOOP on a 16:00 day; acts at close−30 min on a 13:00 day; refuses when the calendar is unknown. Entry-cutoff half (heartbeat_core) waits for 09-29. | `Unregister-ScheduledTask Gamma_EodFlattenEarlyClose` |
| 3 | **Monitors** — `duplicate_ticks` in engine_health (tail-read, distinct `core_tick_id` per account-minute; GREEN 09-01), `prereg_hygiene.py` + task `Gamma_PreregHygiene` 16:58 ET (malformed prereg fixed), gate **REGIME COVERAGE** block with the literal "calm-only window" warning | 22 tests; RED-proofs on each | revert / unregister |
| 4 | **HOME.md `## The gate`** block (render-only from `go-live-gate.json` + the null summary line) | rendered live; regenerated after the null re-run | `git revert` |
| 5 | **Phone HALT** — `setup/scripts/halt_command.py` wired into the Discord responder: `HALT <arm>` / `HALT ALL` / `HALT <arm> FLATTEN` / `RESUME <arm>`, allowlisted author only, fail-closed FLATTEN on a failed broker read. Correction to the audit: fleet arms **are** haltable now — `fleet_live.py` (not frozen) reads a per-arm `circuit-breaker.json` every tick. | 52 tests; RED-proof (fail-closed guard removed → 2 failed). **Open: J's phone drill.** | `git revert` |
| 6 | **Time-stop band measured** for the ≤15:20 prereg: the [15:20,15:40] band carries **0.00%** of post-08-11 gross winner dollars (< 5% ship line) → mechanical **SHIP at 09-29**; give-up at 15:20 −$294 over 16 open positions; 5 positions ITM/near-ATM at 15:30 (sweep exposure set). | `analysis/recommendations/time-stop-band-2026-09-01.{json,md}` | n/a (measurement) |
| 7 | **LIVE-FLIP-RUNBOOK rewritten** against the live caps: safe-3 candidate, Day 1 = 3 contracts ≤$0.50, abort at −$400/day / $500/trade, the prerequisite checklist (DMS drill, early-close, sweep, OPRA, HALT drill, null PASS, after-tax, 20 clean duplicate-tick days), TASK A2 marked UNVERIFIED. | doc | `git revert` |
| 8 | **`journal/trades.csv` fixed** — canonical `setup/scripts/trades_csv_writer.py`; 25 overflow rows repaired (backup `trades.csv.bak-2026-09-01`); pandas parses (556, 44); guard test; prompts + log-trade skill point at the writer. | 4 tests incl. a RED-proof that reproduces the old corruption | restore the .bak |

Frozen-path check: `git diff --stat` over the 10-file frozen list → **empty**. Reviewer's two LOW notes: (a) the live-queue test read a mutable file and went stale when W1 checked off its own item — fixed this session by normalising the two ids' status before parsing (fixture snapshot queued); (b) `heartbeat_core.py:2646`'s bare-name OR-clause remains a latent shared-kill vector with zero writers — noted here so no future writer targets it (fix belongs to the post-freeze mutex item).

---

## 7. The path to real money — revised

| When | What | Bar |
|---|---|---|
| **Tonight** | §5 items 1–4, 6 shipped + verified; queue items filed with dates | tests green; gate re-run shows criterion 2 PASS and criterion 5 scoring |
| **Sat 09-05** | Rule-9 doc pass: CLAUDE.md:65 arming definition (criterion 5 on the frozen window), Rule 7 text, Goal line, tp1/decisions.jsonl references; runbook §1/§4/§5 against live caps | written, committed |
| **Sep 1 → Sep 29** | Freeze holds. Weekly Friday gate re-run publishes: frozen-window PF per arm/book, days scored/needed, P(pass at 10-30), null-study status | no trading-path edits except pre-registered kill-type reductions |
| **Sep 29** | Checkpoint (not arming). Post-freeze ship list: time_stop ≤15:20, early-close awareness, pidfile mutex + vbs fix, `executed_stop` field, OPRA+SIP+vol_mult, `_execute`/`check_order` extraction | each with guard + RED-proof + one-line revert |
| **Oct 30** | 40-day window closes. If criterion 5 GREEN net of costs on all three views AND 2–4 green AND the null study says the engine beats random/beta → J's bounded accept/decline for ONE account (safe-3 profile) at the live caps. If RED → another window; no arming on a red gate. | Gate GREEN as defined in §2 |
| **Nov–Dec** | If accepted: live pilot, real-fill quote tape as the parity instrument, weekly gate; paper fleet stays the lab | recency CONFIRM stays green |

Expectation, no sugar: tens of dollars a day at this tier if it works; $100–200/day per account is a ≥$10K-tier 2027 outcome; the probability that 2026 ends with real money deployed is below one half.

---

## 8. Killed by the refuters — do not re-find these

| Claim | Why it died |
|---|---|
| "EOD flatten is LLM-only with no deterministic fallback" | `Gamma_EodFlattenCore` (pure Python, 15:52 ET) has been the PRIMARY flattener since 07-09 and fired both 08-31 and 09-01, broker-verifying all 4 arms flat 3 minutes before the LLM tasks; the LLM tasks are labeled defense-in-depth. |
| "The fidelity harness cannot see structure/ribbon exits" | Fixed 08-11 (`6a49b21a`, SPY feed union); 26/182 anchored positions in `harness-fidelity.json` exited via `structure_stop`. The docstring was stale, not the harness. |
| "Core flattener is built but not activated" | Active since `2b9d9385` (07-09), expanded to all arms 08-18; the queue item G7-ACTIVATE is stale. |
| "The cost model shows the book losing money net of fees" | The 08-18 snapshot did; a fresh re-run tonight on 266 round trips: +$1,992 as-traded, +$1,892 fee-adjusted, −$272 at 2¢ exit slip. The stale JSON was the problem. |
| "The 11K-test fast suite never completes, which is why the 08-29 regression sat undetected" | `Gamma_GuardsFull` runs the full `not slow` suite nightly at 23:15 with a 60-min budget and **did** catch the 3 RED tests on 08-29 (queue.md:84, MED). The suite is slow, not absent. |

Also corrected by the critic before reaching J: tax coverage is "no after-tax number, no CPA," not "zero coverage"; the two conductor-starvation mechanisms are both true and both fixed; "honest n = 2 sessions" is definitional (sizing caps changed 08-29; entry/exit logic n≈15 post-ladder).

---

## 9. Verification log (OP-33)

- `python setup/scripts/et_clock.py` → `2026-09-01 18:10:02 Tuesday EDT market_hours=False`
- `python setup/scripts/go_live_gate.py` (18:11 ET) → OVERALL RED; per-arm CI_lo quoted in §Verdict; `dead_mans_switch… NO TEST FOUND`; prod-shadow NOT_WIRED; recon PASS ×4; behavioural PASS
- `git log --since=2026-08-31 -- <7 frozen files>` → empty; `git status --porcelain -- <7 files>` → empty
- `pytest tests -m "not slow" -x` (venv) → `1 failed, 845 passed` (fails at the known `test_cheap_contract_qty_boost`); `tests/test_graduated_guards.py -m "not slow"` → `94 passed, 1 skipped`; `tests/test_gate_e2e_2026_06_18.py` → `22 passed in 41s` (the "stall" was suite size, ~25 min total, not a hang)
- Fills re-derivation: `scratchpad/R3/r3_edge_rederive.py` → book n=385 PF 1.058 +$1,220; safe-2 gate bootstrap reproduced `ci_lower_2.5=0.333` via two independent paths
- `r10_analysis.py` (reproduced by two verifiers) → corr(pnl,ret)=0.232; P(pass) appending 20 days 0.00/0.02/0.13/0.10/0.03
- Alpaca docs fetched live (`us/options-trading-overview`, `us/historical-option-data`); broker calendar GET → `2026-11-27` and `2026-12-24` `close: 13:00`
- `analysis/data-tier/summary.json` (16:20 ET) → all 4 arms `option_opra_ok: false`, live path INDICATIVE
- `github_audit.py` → `13335 tracked files … VERDICT: GREEN`
- Fix-workflow verification: see §6 / CHANGELOG once complete
- UNVERIFIED items are labeled inline (TASK A2 source; TradingView Plus cost; whether the mid-August cessation of overlapping ticks reflects a fix or luck).
