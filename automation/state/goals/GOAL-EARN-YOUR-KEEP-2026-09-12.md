# GOAL: EARN-YOUR-KEEP-2026-09-12

> J verbatim (2026-09-12 ~17:05 ET, Saturday, `/goal`): *"I want an automated gamma trading multiple
> markets, and it needs to be hungry to actually be alive and learn and make money … I'm still just
> prompting you like a chatbot. You've built things that aren't in use because they aren't useful or
> intuitive enough … we had a decent month in August. We learned a lot. I just feel like we haven't
> done anything in September … You have exactly six days to earn your keep … you better pace
> yourself. If you blow yourself up and run yourself out of tokens, that means you can't follow an
> instruction."*

Parent evidence: [`FABLE-FULL-AUDIT-2026-09-11.md`](../../../analysis/deep-research/FABLE-FULL-AUDIT-2026-09-11.md)
(§0 verdict, §2b anchor-class table, §5 what ships, §7 consolidation). Hard deadline: **2026-09-18**
(subscription renews). Model tier: Fable = judgment + this file; every build item is a Sonnet spawn.

## THE DIAGNOSIS THIS GOAL ACTS ON (one paragraph, so a fresh session does not re-derive it)
September's losses are not a regression -- nothing on the signal path changed 08-29 → 09-11 (939
commits, 0 on the signal). The engine is a range-day machine (P&L vs SPY daily range corr 0.62) that
fires on same-day 3-bar swing pivots (`INTRADAY_SWING_*`: Sept −$1,237, 8 of 10 signals lost) with
the same standing as yesterday's high (prior-day / premarket / session H-L class: +$3,037 since 08-17).
The book is four copies of one trade: every arm fires the same signal within ~15 s, so four frozen
arms produce ONE data point per session. The config freeze (08-31 → 10-30) protects a go-live score
that no arm is within reach of (frozen-window PF 0.112, gate needs CI-lower > 1.0) -- four identical
frozen windows carry no more evidence than one. The 09-11/09-12 directives already cut the level
noise (22 → 6 lines, trendline fitter OFF, cap authority on both readers; clean window restarts
09-14). The tickers lane has traded AMZN/AAPL/NVDA/TSLA/AVGO/QQQ/GLD every session since 09-04 and is
INVISIBLE on HOME.md. What "alive and learning" means here, concretely: **each trading day must
produce evidence that changes what the rig does the next day, on a surface J already reads.**

## WHAT GPT-6 "ASTRA" ACTUALLY CORRELATES TO (researched 2026-09-12, sources in PROGRESS LOG)
- CONFIRMED-official: runs open-ended jobs for days unattended; "improves a trading model based on
  what worked … as part of a continuous session" = in-session iteration, NOT persistent learning.
- CONFIRMED-independent: Fable 5.1 leads Astra on the Intelligence Index (66 vs 61) and the Coding
  Agent Index (70 vs 67); Astra leads on terminal/computer-use benchmarks (57.7 vs 55.8, 72.6 vs 70.2).
  The "AGI" claim fails OpenAI's own bar by 37 points per the benchmark's authors.
- RUMOR: every "Astra trades real money 24/7" post is a creator demo, not an OpenAI result.
- **The one thing to take from it:** the loop that scores what worked and changes the next run is the
  product. Gamma has the pieces (fleet, EOD, preregs, HOME) and has never closed that loop on live
  fills. This goal closes it. Model switch: no case (cost $10/$50 per M, no capability we lack).

## DONE-WHEN (falsifiable; each checked by a command or ledger row quoted in the PROGRESS LOG)
- (1) **A challenger arm runs a different hypothesis from the control, live, from 09-14.** `risky-3`
  is revived as the exact twin of `risky-1` (same sizing / gate / exit profile) plus ONE per-arm gate:
  `gate_override.anchor_class_denylist: ["INTRADAY_SWING_"]` -- the 09-29 prereg
  (`prereg-trigger-anchor-level-class-2026-09-11.md`) run on a paper challenger 15 days early.
  Control (`risky-1`) and the two Safe arms are byte-identical to today. Check: a session's
  `automation/state/fleet/risky-3/` ledger shows ≥1 signal REFUSED with reason `anchor_class_denied`
  on a day risky-1 filled that signal, OR ≥3 sessions where no denied signal existed (null logged).
- (2) **Every session scores the challenger against the control and prints it where J reads.**
  `HOME.md` (generator-written, never hand-edited) carries a `## What Gamma learned today` block:
  challenger vs control per session and cumulative (signals, refused, legs, $), plus the ONE change
  the rig makes tomorrow (or "no change: <reason>"). Written by an EXISTING EOD fire, no new task.
  Check: `grep -c "What Gamma learned" HOME.md` == 1 after the 09-14 close, numbers reconcile to
  `fleet_eod` ledgers.
- (3) **The tickers lane is visible and audited the same way.** HOME.md shows per-arm tickers
  P&L per session (it has traded 7 names since 09-04, −$785 book, invisible today), and the
  anchor-class read runs on its fills so 09-18 says whether non-SPY suffers the same swing-pivot
  disease. Check: HOME.md tickers table present; `trigger_anchor_class_read.py --lane tickers`
  (or equivalent) prints a table for 09-04..09-17.
- (4) **The rotation rule exists and is pre-registered, not improvised.** One living doc row per
  hypothesis in the challenger LADDER (H1 swing-pivot denylist ← live; H2 MEMORY_* denylist; H3
  compression sit-out; H4 SD-zone anchor, after its 10-session clock) with kill / promote criteria
  and the n they need. When H1 hits its criterion, H2 replaces it on the challenger. No code for
  rotation in this goal -- a decision row the conductor can execute.
- (5) **09-18 verdict, honest.** HONEST STATE closes with: per-arm September $, challenger vs
  control after 4 sessions (09-14..09-17), tickers lane verdict, what the rig changed on its own
  during the window, tokens spent per day. A null (challenger no better) is a valid close.

## OPERATING RULES
- **Subtraction posture stands** (GOAL-SUBTRACTION): this goal adds ONE per-arm gate key, ONE
  generator section, ONE lane on HOME. No new dashboard, task, sidecar, lane, or report. If an item
  needs a new scheduled task, it is designed wrong.
- **Freeze handling, decided:** `safe-2` (core control) and `safe-3` (go-live-gate prod-shadow arm)
  stay frozen and byte-identical -- they carry the clean score window that restarts 09-14.
  `risky-1` is the control twin; `risky-3` is the challenger and its window is spent on evidence.
  Applied under `GAMMA_FREEZE_OVERRIDE` on J's 2026-09-12 directive, with guard + RED-proof + revert
  line per edit. Revoke = `git revert` the commit, or set `risky-3.status` back to `retired`.
- **No LLM on the hot path** (J 07-15): the denylist is a string-prefix check in `_gate_check`;
  the scorer is pure Python. Claude writes this file and the specs only.
- **Token pacing (J's condition):** Fable spawns ≤ 2 Sonnet builders per day, sequential, each with
  objective / return schema / scope / do-not list. No fan-outs. No Fable-driven test sweeps -- the
  builder runs them and quotes the summary line. Per-day token estimate written in the PROGRESS LOG.
- Every fire that touches this goal calls `python setup/scripts/conductor_outcome.py record
  --task-id GOAL-EARN-YOUR-KEEP-2026-09-12 --drained <n> --added <n> --lessons <n> --tests-delta <n>
  --regressions <n> --note "<note>"`.
- Every `Agent` spawn passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only.
- Never `/loop` this goal in-session; the Stop hook (≤3 continuations) and `Gamma_Conductor` are
  the two continuation paths. CLAIM an item (`[ ]` → `[~]`) before working it.
- GOAL-SUBTRACTION-2026-09-11 is re-queued directly behind this goal on the ladder (items (b)–(e)
  still open); its tick dead-man item (b) is safety and the conductor should take it the moment this
  goal has no open item.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] (1) risky-3 revived as risky-1's twin + `anchor_class_denylist` gate in `fleet_executor._gate_check` (label carried on the side block by `build_shared_signal` from `conviction.matched_level_label`); refusal row written to the arm ledger; guard test RED-proofed; live account probe for risky-3 creds (read-only); commit + STATUS line. DONE-WHEN: a replayed 09-11 signal set shows risky-3 refusing the 10:01/10:51 `INTRADAY_SWING_*` entries while risky-1 keeps them.
- [x] (2) `obsidian_vault_sync.py` gains `## What Gamma learned today` (challenger-vs-control table from the fleet ledgers + tomorrow's one change from the challenger LADDER); numbers reconcile to `fleet_eod`. DONE-WHEN: regenerated HOME.md carries the block with 09-14 numbers after that close (dry-run on 09-11 data before Monday).
- [x] (3) tickers lane on HOME (per-arm per-session table from `automation/state/tickers/*/day-*.json`) + anchor-class read over the tickers ledgers 09-04..09-17. DONE-WHEN: table renders; read prints per-class $ for the lane.
- [x] (4) challenger LADDER rows (H1 live, H2, H3, H4) with kill/promote criteria + n, appended to the existing prereg doc (`prereg-trigger-anchor-level-class-2026-09-11.md`), not a new file. DONE-WHEN: rows exist; conductor.md STAGE 1 knows to read the top row when H1 terminates.
- [ ] (5) 09-18 HONEST STATE verdict with the numbers in DONE-WHEN (5). NOT-BEFORE 2026-09-17 close.

## J-DECISIONS
- None open. Live-money arming is not in scope. Revoke surface = STATUS line at OPEN.

## PROGRESS LOG
- 2026-09-12 17:1x ET (Fable, interactive): goal authored from J's `/goal`. Evidence gathered this
  session: 09-11 audit §0/§2b/§5/§7; STATUS known-broken; live `key-levels.json` (cap kept 6, pruned
  9, as_of 17:00 ET); tickers lane day files (t1 ≈ −$89, t2 −$204, t3 −$492, 09-04..09-11);
  fleet decision path mapped (core → `core-decisions.jsonl` → `build_shared_signal` →
  `fleet_executor.plan_all` → `_gate_check` is the per-arm seam; every file on FROZEN_TRADING_PATH).
  GPT-6 Astra research (Sonnet, 6 fetches): openai.com/index/gpt-6-astra, artificialanalysis.ai
  benchmarking + comparison pages, techcrunch 09-03, washingtonpost 09-03. Tokens this session
  before the first build: ~220K (two Sonnet agents 122K + 95K, Fable context ~40K).
  GOAL-SUBTRACTION re-queued behind this goal (ladder `[~]` → `[ ]`, active pointer moved).

- 2026-09-12 17:2x ET (Fable): **(4) DONE** — §8 Challenger LADDER appended to the prereg (H1 live 09-14, H2 MEMORY denylist, H3 compression sit-out with a frozen 0.35× threshold, H4 SD-zone after its clock); F1-F5 + §5 kill apply unchanged to risky-3 refusals. Item (1) builder (Sonnet) running.

- 2026-09-12 17:2x ET (Sonnet builder, item 3): **(3) DONE** — `obsidian_vault_sync.py::render_tickers_lane` (+call site in `render_other_lanes`) now prints a per-arm per-session table for the 5 sessions on disk (09-04/08/09/10/11) plus cumulative-since-09-04 per arm and a lane total, evidence-class-labelled "paper fills on real quotes -- same scorer as SPY core"; regenerated HOME.md shows tickers-1 −$89.00 / tickers-2 −$204.00 / tickers-3 −$492.00 / lane −$785.00 over 11+9+13=33 fills, reconciling the memory-note figure. NVDA 09-10 gap: `flatten-last-run.log` shows tickers-1's NVDA260911P00217500 WAS closed by the 14:52 ET safety-net flatten (`closed=['NVDA260911P00217500']`) but `_lookup_closing_fill` found 0 matching broker sell orders (`FLATTEN_PNL_UNRESOLVED`), so no SELL row/P&L landed anywhere -- a reconciliation gap, not a naked position; filed as `TICKERS-DAYFILE-EXIT-GAP` in `automation/overnight/queue.md` (fix needs a poll/retry, not an obvious ≤10-line patch). Anchor-class read: `trigger_anchor_class_read.py --lane tickers` added; the tickers ENTER row schema carries NO `matched_level_label`/`level` field at all (bull/bear_triggers only: level_reclaim, level_rejection, trendline_rejection, ribbon_flip, confluence) and `level-states/*.json` carries only a numeric ladder with a generic `role`, not a class -- so the read is a PROXY bucketing by trigger name; 09-04..09-11 verdict: LEVEL_RECLAIM −$458/8 legs, TRENDLINE_REJECTION −$129/5 legs, LEVEL_REJECTION −$198/1 leg, 1 open/unreconciled leg (the NVDA gap) -- same-shape losing pattern as SPY core's swing-pivot disease, though the class taxonomy doesn't map 1:1. Guard `backtest/tests/test_home_tickers_lane_2026_09_12.py` (6 tests) RED-proofed on `classify_tickers_row`. Filtered suite (`-k "obsidian or vault_sync or trigger_anchor"`) 29 passed, 0 pre-existing REDs.

- 2026-09-12 17:3x ET (Sonnet builder, item 1): **(1) PARTIAL / BLOCKED on activation.**
  Confirmed `conviction.matched_level_label` is populated on real ENTER rows (grepped
  `core-decisions.jsonl` 09-11 10:01/10:51 bold rows: `MEMORY_RES_153` / `INTRADAY_SWING_LOW_
  2026-09-11`). Shipped: `build_shared_signal.py` -- `_map_core_row` now passes through the
  core row's `conviction` dict (WITHOUT this the whole gate is a dead knob: neither
  `_bold_passed_blocks_from_row` nor the top-level bear/bull ever see conviction otherwise),
  both perceptions' bear/bull blocks + `_ribbon_strategy_entries`' FIX2 `strategies[]` entries
  now carry additive `trigger_anchor_label` (production's live route is FIX2,
  `EMIT_STRATEGIES=True`, so the label had to reach `_gate_block_for_entry` too, not just the
  side-block fallback -- fixed). `fleet_executor.py::_gate_check` denies
  `anchor_class_denied:<label>` on a prefix match, fail-open on None/missing;
  `_gate_block_for_entry` passes the label through. `accounts.json`: risky-3's `gate_override`/
  `params_patch`/`exit_profile` set BYTE-IDENTICAL to risky-1's resolved config (incl.
  `full_send:true` -- a twin means the whole risk profile) plus
  `gate_override.anchor_class_denylist: ["INTRADAY_SWING_"]`; removed `consumes_scoring_peak`,
  `score_ladder_doc` (no floor was actually set), `gate_params`/`gate_params_doc`
  (hard_skip_verdicts opt-out), `strike_tier_table_doc` + the retired premium-stop docs as
  pure-twin-breaking leftovers. **BLOCKED: did NOT flip status/live.** risky-3's account
  `PA3V7JT25H6Z` was re-tasked to `weekly-1` on 2026-08-28 (verified live via
  `fleet_broker.get_account`: acct ****5H6Z, equity $4,282.65 -- matches weekly-1's tracked
  balance, confirming it's the SAME account, not a fresh one) and weekly-1's own
  `hard_prerequisite_met`/risky-3's own `retired_reason` fields explicitly say not to revert
  risky-3 while weekly-1 is wired to it (SPY-symbol-filtered flat-check blind spot, C11) --
  un-wiring weekly-1 is a separate decision outside this item's file scope. Documented as
  `revival_blocked_2026_09_12` on the arm; two unblock paths named (repoint weekly-1's
  account, or give the challenger a new dedicated account). Guard
  `backtest/tests/test_challenger_anchor_denylist_2026_09_12.py` (18 tests) RED-proofed
  (broke the prefix check -> 2 failures -> restored -> 18/18 green). Offline replay of the
  real 09-11 core-decisions rows (no broker call): 10:01 `MEMORY_RES_153` -> both risky-1 and
  risky-3 ENTER; 10:51 `INTRADAY_SWING_LOW_2026-09-11` -> risky-1 ENTERs,
  risky-3 `anchor_class_denied:INTRADAY_SWING_LOW_2026-09-11` -> HOLD. **Caused regression**
  (named, not fixed -- out of this item's file scope): risky-3's identity change breaks 18
  pre-existing assertions across 7 files (`test_bold_core_strike_tier_2026_07_15.py`,
  `test_dojo_exit_diversity_replay.py`, `test_fleet_arm_parity.py`,
  `test_fleet_arm_replay.py`, `test_fleet_strike_tier_floor_collision_2026_07_31.py`,
  `test_trade_today_watcher.py`, `test_vwap_reclaim_fleet_extension_2026_08_04.py`) that
  hardcode risky-3's old retired identity; filed as a follow-up chip (task_9e8814e8). Filtered
  suite `-k "fleet or shared_signal or arm_roster or accounts_json or line_level_consolidation"`:
  421 passed, 18 failed (all named above, all caused by this change), 1 xfailed. Commit +
  `conductor_outcome.py` record done same session. QUEUE item (1) stays `[~]` (not `[x]`):
  the gate mechanism ships and is guard-proven, but the arm is not live, so the DONE-WHEN's
  "risky-3 refusing while risky-1 keeps them" is proven only in an offline replay, not on a
  running paper arm yet.

- 2026-09-12 19:5x ET (Fable, after a power outage killed the box + the builder mid-run): builder's commits `a0d970c8` (risky-3 ACTIVATED on ****5H6Z, twin of risky-1 + denylist; weekly-1 is pending_build with no task on that account, so the challenger takes it) and `093311e3` (18 stale risky-3 identity pins updated, 0 weakened) landed before the crash. Re-verified cold this session: `arm_roster.active_arms()` -> ['safe-3','safe-2','risky-1','bold-2','risky-3']; `test_challenger_anchor_denylist_2026_09_12.py` 19 passed. Item (1) stays `[~]` until Monday's ledger shows a live refusal (DONE-WHEN as written). Item (2) had NOT started (generator diff = 0 lines) -- re-spawned as a fresh builder. Tokens today (harness-measured): research 122K + map 95K + builder-3 193K + builder-1 268K before crash.

- 2026-09-12 20:1x ET (Fable): Stop hook offered item (5); it is NOT-BEFORE 2026-09-17 close by its own text (same convention as GOAL-SD item (e)) -- left `[ ]`, not claimed, not faked. Items (1)/(2) are `[~]`: (1) waits for Monday's live refusal, (2) is in a running Sonnet builder. Post-crash Monday readiness verified: quiet-mode restore list holds 136 tasks incl. Gamma_FleetExecutor/Conductor (re-enable 23:00 ET); FleetExecutor next fire 09-14 09:31 ET; TV relaunch via Gamma_LaunchTV 08:00; risky-3's 08-28 entry-claim is TTL-scoped (harmless).

- 2026-09-12 20:1x ET (Sonnet builder, item 2): **(2) DONE** — `obsidian_vault_sync.py`
  gains `render_learned_today()` (+ helpers `_fleet_arm_dates`, `_fleet_arm_session_stats`,
  `_fleet_arm_realized_pnl`, `_next_ladder_row`) and its call site in `build_home` directly
  under `## Position & P&L`. Refusal source: `automation/state/fleet/<arm>/decisions.jsonl`
  field `reason`, prefix `"gate: anchor_class_denied:<label>"` (written by
  `fleet_live.py::_log` from `fleet_executor.py::_gate_check`'s item-(1) denial string;
  "signal" = a row where `setup_name` is non-null). Realized-$ source:
  `automation/state/pnl-statement.json` `per_day.<date>.<arm>.realized_pnl` — the SAME
  T1 broker-truth round-trips file `fleet_journal_bridge.py` cites in journal/trades.csv
  notes. RECONCILE (real data, dry-run): risky-1 2026-09-11 `pnl-statement.json` says
  `-145.0`; independently summing journal/trades.csv `dollar_pnl` for the 5 risky-1 rows
  that date (`-125,+90,+40,-5,-145`) also totals `-145.00` — reconciles exactly (the
  goal's own hint text said "-146.00"; verified actual is -145.00 and reported the real
  number, not the hint). Today (2026-09-12, before the 09-14 clean window) risky-3 has
  zero decisions.jsonl rows on/after 09-14 (last row 2026-08-28, pre-activation), so the
  block correctly renders the "no sessions yet" form — quoted:
  `> no sessions yet (first 2026-09-14)` / `**Tomorrow's change:** none (H1 clock
  running: 0/6 refused)`. `grep -c "What Gamma learned" HOME.md` == 1; tickers block
  (item 3) still present once (`## Other lanes` → `### 🎯 Tickers` unchanged). H1 tally
  reads prereg §4/§5 (n needed = 6, from the §8 LADDER row); on KILL (refused >=6 AND net
  >=0) it names the next `[ ]` LADDER row by reading the prereg file fresh (no hardcoded
  H2 text) — guard-proven with a fixture prereg. Guard
  `backtest/tests/test_home_learned_today_2026_09_12.py` (6 tests: no-data pre-09-14,
  no-data on missing files, one-refused-signal F1<0 tally 1/6, 6-refused KILL names H2,
  KILL-fires-but-prereg-unreadable renders n/a not exception, build_home carries exactly
  one block) RED-proofed: broke the `anchor_class_denied` prefix match ->
  3/6 failed -> restored -> 6/6 green. Filtered suite
  `pytest backtest/tests -k "obsidian or vault_sync or learned or home_tickers"`:
  **34 passed**, 0 pre-existing REDs in that filter. Pre-existing unrelated collection
  error named, not fixed: an unscoped `-k` run (no path) crashes pytest's collector on
  `share/self-correction-skill/test_self_correction.py` (`sys.exit(0)` at import time) —
  present before this session, reproduced by running the bare `-k` filter with no
  `backtest/tests` path; scoping the path avoids it, which is what the guard run above
  does.

## HONEST STATE
Opened. The challenger (1) is BLOCKED on activation, not on the mechanism: the gate itself
(build_shared_signal's `trigger_anchor_label` passthrough + fleet_executor's
`anchor_class_denylist` check) is built, guard-tested, RED-proofed, and proven against real
09-11 data offline. What's missing is an account for risky-3 to trade on -- its own account is
now weekly-1's, and reactivating it there would reopen a closed safety hole (C11 flat-check
blind spot). Until that's resolved (repoint weekly-1, or give the challenger a fresh account),
09-14..09-17 still produce four copies of one trade and the 09-18 verdict stays "nothing
learned" on THIS item. Two other sessions completed items 3 and 4 in parallel this evening
(see their PROGRESS LOG entries above) -- item 1 was the load-bearing one and is the one that
did not fully land. UNVERIFIED / needs a human or a follow-up session: which unblock path J
wants (repoint weekly-1's account_number, or provision a new paper account for risky-3).
