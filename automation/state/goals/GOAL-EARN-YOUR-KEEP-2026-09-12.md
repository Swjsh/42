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
- [ ] (2) `obsidian_vault_sync.py` gains `## What Gamma learned today` (challenger-vs-control table from the fleet ledgers + tomorrow's one change from the challenger LADDER); numbers reconcile to `fleet_eod`. DONE-WHEN: regenerated HOME.md carries the block with 09-14 numbers after that close (dry-run on 09-11 data before Monday).
- [ ] (3) tickers lane on HOME (per-arm per-session table from `automation/state/tickers/*/day-*.json`) + anchor-class read over the tickers ledgers 09-04..09-17. DONE-WHEN: table renders; read prints per-class $ for the lane.
- [ ] (4) challenger LADDER rows (H1 live, H2, H3, H4) with kill/promote criteria + n, appended to the existing prereg doc (`prereg-trigger-anchor-level-class-2026-09-11.md`), not a new file. DONE-WHEN: rows exist; conductor.md STAGE 1 knows to read the top row when H1 terminates.
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

## HONEST STATE
Opened. Nothing built yet. The challenger (1) is the load-bearing item: without it, 09-14..09-17
produce four more copies of one trade and the 09-18 verdict is "nothing learned". UNVERIFIED until
the builder proves it: that `conviction.matched_level_label` is populated on every ENTER row the
fleet consumes (the audit's read joins on it, so it is populated on the ticks the audit counted),
and that risky-3's paper credentials still resolve.
