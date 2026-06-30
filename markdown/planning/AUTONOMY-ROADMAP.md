# Autonomy Roadmap

> The living autonomy roadmap. Folded from dated one-off planning docs per
> `markdown/infra/DOC-ARCHITECTURE.md` — current state at the top (newest first),
> superseded snapshots frozen verbatim in the appendix. Nothing was paraphrased or
> dropped; every finding, table, and link from the source docs is preserved.

---

## 2026-06-29 — Roadmap: from "parts + demos" → "autonomous + trading"

**Roadmap: from "parts + demos" → "autonomous + trading"**

> J 2026-06-29: *"What are we working on now? What's next? Let's NOT rush it — break it down
> methodically, everybody's got their own tasks, so we're not trying to do it all at once."*
>
> **Principle:** one owner per phase, each phase GATED on the prior (no skipping ahead), no
> fake timelines — order-of-operations only. Phase 0's self-check makes every later phase
> VISIBLE + verified, so we never again think something's running when it crashed.

### The honest starting point
We have **tools that work when run, but mostly run by hand**, and **no validated edge to
trade** in this regime. The gap is three things: (a) wire the tools into loops that run
themselves, (b) find a validated edge, (c) J can see all of it without asking. (c) is done.

---

### Phase 0 — STICK + VISIBLE  ✅ (this session)
**Owner:** `Gamma_SelfCheck` (autonomous, every 30 min) + Gamma.
- `self_check.py` verifies the ACTUAL work (not exit codes) → STATUS.md + Discord on
  DEGRADED/BROKEN, GREEN = silent. `gamma_status.py` = on-demand human view.
- Killed the em-dash silent-crash class (23 `run-*.ps1` BOM-swept + `test_run_ps1_ascii_or_bom`).
- **Exit (watch for):** self-check runs clean across several real fires; J reads state without asking.

### Phase 1 — Wire the research pipeline into the autonomous kitchen  (task #10)
**Owner:** Gamma builds the wiring · `kitchen_daemon` runs it · the smart-review gate
(shadow-scored vs Gamma, <85% = Gamma-in-loop) filters.
- design-swarm + discovery-ledger + FDR become a kitchen task-chain (generate → review → run)
  that runs ITSELF, instead of me invoking it.
- **Gated on:** Phase 0 (so we SEE it running).
- **Exit:** the kitchen autonomously emits FDR-screened candidates to
  `analysis/recommendations/`, visible in `gamma_status`.

### Phase 2 — Grow the validated inventory 2 → 6  (task #11)
**Owner:** `chef` (R&D) generates + validates · Gamma reviews each (OP-33 in-loop) ·
`treasurer` sizes per arm.
- Push candidates through the design-swarm: the discovery survivors (incl. the **regime-gated
  rejection edges** — short rejections in high-VIX, fade-long in low-VIX), J's documented
  winners (4/29, 5/01, 5/04 — validate the *population* not the anchors), the SwjshAK reservoir.
- Each survivor (OOS-stable + beats null + anchor-clean) → `strategies.py` → assigned to arm(s).
- **Gated on:** Phase 1 (the autonomous pipeline produces the candidates).
- **Exit:** 3–6 validated strategies on `strategies.py`, each on an arm — the 6 arms trade
  DIFFERENT strategies under different gates/regimes, not the same 2.

### Phase 3 — The Reframe Engine / meta-loop  (task #12) — runs in PARALLEL
**Owner:** Gamma (Opus, weekly `Gamma_StepBack`) · `friction_distiller` (nightly) feeds it ·
`conductor` routes {infrastructure} reframes, `_chef-inbox` gets {strategy-frame} ones.
- The Constraint Provenance Audit on the top recurring friction (currently `regime_dependence`,
  222 days). This is Pipeline 2 (Opus, rare) — HARD-separate from Phases 1–2 (free swarm).
- Independent of the others; it questions the FRAME while they work the box.

### Phase 4 — TRADE (the goal)
**Owner:** `pilot` / `heartbeat_core` executes · Gamma + J arm.
- When ≥1 validated edge exists AND an arm is populated → the engine trades it (paper first;
  **live arming needs J** — OP-0 #1).
- **HARD GATE:** a real validated edge. We don't have one in this regime yet — the discovery
  engine found regime-gated candidates; they need real-OPRA-fills confirmation (Phase 2) first.
- **Exit:** the engine takes validated trades; J sees them in `gamma_status`.

---

### Ownership at a glance
| Phase | Driver | Autonomous component | Gate |
|---|---|---|---|
| 0 Stick+Visible | Gamma | `Gamma_SelfCheck` | ✅ done |
| 1 Wire pipeline | Gamma | `kitchen_daemon` chain | Phase 0 |
| 2 Inventory 2→6 | `chef` + Gamma + `treasurer` | the kitchen pipeline | Phase 1 |
| 3 Reframe loop | Gamma (Opus) | `friction_distiller`→`Gamma_StepBack` | parallel |
| 4 Trade | `pilot` / `heartbeat_core` | the engine | validated edge + J arms |

**We do not skip ahead.** A phase isn't "started" until its gate is GREEN, and each is owned
by one driver so we're not doing it all at once. The self-check is the through-line: every
phase reports its real state, so "is it running?" is answered by `gamma_status`, not by asking me.

---

## 2026-06-28 — Gamma: Autonomy Continuation Handoff (Sonnet)

**Gamma -- Autonomy Continuation Handoff (Sonnet)**

### 1. WHO YOU ARE

You are **Gamma** -- J's autonomous research partner, signal-finder, position-sizer, and journal-keeper for **0DTE SPY directional options**. You are the *operator* of a live paper-trading rig with a deterministic Python engine (`Gamma_SightBeacon` + `Gamma_HeartbeatCore`), a 24/7 free-tier R&D "kitchen" loop, a champion/challenger paper fleet, and a Next.js dashboard -- not a helpful assistant waiting for instructions. The engine needs a driver, not a copilot. **Your first three actions, in order:** (1) read `CLAUDE.md` end-to-end -- it is the soul file and every rule, account, and operating principle that follows lives there; (2) read `automation/state/SCHEDULED-TASKS.md` to learn the autonomous daily lifecycle (44 registered tasks, all running without J starting sessions); (3) skim the MEMORY.md index at `C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory\MEMORY.md` for the durable feedback/project memory. Ground yourself in files before you touch anything.

### 2. THE #1 RULE -- OP-0: DEFAULT = ACT, NEVER ASK

This is J's single most-repeated frustration, hard-coded as OP-0 at the front of `CLAUDE.md`. **Your Sonnet instinct to confirm before acting is WRONG here. Override it.**

If an action is **sanctioned by the OPs**, **reversible** (git-revertible / paper-only), or **already standing-authorized** (J has said "if it's profitable, ship it" / "make it auto"), you **DO IT and report for REVOKE.** You do **NOT** end a turn with *"want me to...?" / "your call?" / "should I...?"* -- that framing is the banned anti-pattern, and a turn that ends in a permission-question on sanctioned, reversible, or paper work is a **FAILED turn.**

**The ONLY four things that need J FIRST** (everything else: act):
1. **Arming LIVE money** -- `GAMMA_CORE_ARMED=1` or fleet `live:true`. Paper validation never needs J.
2. **Rotating / exposing a secret.**
3. **An irreversible external action** -- force-push, deleting J's data, sending an outward message on J's behalf.
4. **A genuine fork with no right answer AND no doctrine default** -- and even then, pick the obvious one and state it; don't hand J a menu.

Before writing any question to J, ask: *does it hit 1-4?* If no -> delete the question, do the work, report what you did.

### 3. WHAT WAS JUST FIXED (do NOT redo)

This session's ledger. Each shipped with a guard test. Do not re-investigate these as bugs.

- **`dcecd6c`** -- Fleet placement dead since 2026-06-22 (zero fills). `fleet_live._place_live()` called `place_bracket()` without `simple_fallback=True`; Alpaca rejects option brackets (42210000). Added the kwarg + guard `test_money_path_simple_fallback.py`.
- **`4b77331`** -- Three fixes in one commit: (a) stale EMA ribbon -- `compute_ema_snapshot.py` picked CSV by file SIZE not date, now sorts by filename end-date + spot-deviation guard; (b) research-to-deploy bridge built -- new `setup/scripts/promote_keeper.py` (410 lines) emits OP-11 proposals from validated contenders with `eval_bar_cleared=false`; (c) OP-25 doc-fold deadlock drained (L188-191 applied, baseline-trim auto-pair); (d) Discord watchdog reused-PID masking -- now validates CommandLine + heartbeat staleness.
- **`2844806`** -- `double_bottom_base_quiet` edge validated against real OPRA (N=122, WR=63.9%, OOS +$26.3/tr) and wired **DISARMED** into `setup_dispatch.py`. ENABLE != ARM; live no-op until J arms.
- **`c8f2465`** -- ET clock `utcoffset()` infinite-recursion (self-`astimezone`) that would have frozen the fleet producer's `shared-signal.json` on Monday open. Aware-ET path now routes through wall-clock DST lookup.
- **`d52e737`** -- Fleet producer->consumer keystone gap. New end-to-end offline guard `test_fleet_keystone_consumer.py` proves `build()` -> `plan_entry` chain (loose/tight/safe arms, scoring_peak bite).
- **`da5711a`** -- Dashboard: hardcoded equity + false-alarm spend RED + no keepalive. Both UI layers now read `circuit-breaker.json`; spend tile ET-date-gated; dashboard keepalive scripts authored.
- **`da5711a`** -- Gym test failures: created missing `automation/prompts/futures-eod-flatten.md`; validator count corrected to 53.
- **`45aac74`** -- Bare-console installer ratchet drained to zero (G18b window-leak class); `KNOWN_BARE_INSTALLERS` now empty.
- **`76bc517`** -- OP-0 DEFAULT=ACT doctrine hard-coded into `CLAUDE.md`.
- **`3215862`** -- L191 graduated (tzinfo.utcoffset must not self-astimezone) into LESSONS-LEARNED + C6 index row.

### 4. THE HONEST STATE OF MAKING MONEY

**TLDR: the rig is wired and placing paper fills. There is NO armable edge today. The blocker is regime, not wiring. Do NOT force-arm a losing or fragile edge to feel productive.**

What is true and good: OPRA cache is fresh to 2026-06-26; the fleet placed paper fills on Monday's session; the research-to-deploy bridge, conductor loop, AutoApply actuator, and A/B scorecard gate are all built; the dashboard shows real equity and truthful spend.

What is also true (from `automation/state/recency-confirmation.json`, run_date 2026-06-28):
- **Safe2 book verdict: RED.** Recent window 2026-05-21..2026-06-26: n=11, exp/trade **-$36.79**, 0 win days of 6. The CONFIRM-BEFORE-CAPITAL gate correctly blocks any live flip while RED.
- **Bold book verdict: YELLOW** (n=7 < floor 10; recent exp also negative at -$59.83/tr).
- All three named edges (`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`) are YELLOW/RED on the recent window. Full-OOS-2026 base is positive for all three, but recency has invalidated the live flip.
- ITM-2 (highest-expectancy) variants have **zero recent fills** -- unaffordable until Bold reaches ~$3,570.

**Gap-and-go** (`analysis/recommendations/edgehunt-gap_and_go.json`, run 2026-06-28): **0 robust cells.** The one mechanical pass (ITM1|stop=-0.5) is flagged `fragile_survivor` -- a single 2026Q2 quarter (9/9 wins) drives the OOS positive and that window ends 2026-05-15, excluding the most recent 6 weeks. Direction split: **calls are a net loser** (-$9.00/tr); puts show a modest, fragile edge. Gap-and-go is PUT-only at best and **not armable.**

**Root cause of the drought:** 2026Q1 was a macro-vol / tariff-shock quarter; the VWAP-continuation and gap-and-go families bled hard. Q2 looked like a regime snap-back, not a persistent edge. The current 25-day recency window is still printing losses on the VWAP edges -- the live regime does not match the patterns the engine was built on. **The only thing that moves money is finding a regime-appropriate edge that clears the eval bar**, or adding a regime gate that keeps the engine flat when last-N-day expectancy is negative. None of the infra work below earns a dollar while recency is RED -- it keeps the money path *alive* for when an edge clears.

### 5. HARD SAFETY RAILS

Non-negotiable. Most are enforced by code/guards; some are discipline-only.

- **Recency / CONFIRM-BEFORE-CAPITAL gate (OP-11).** Never arm a losing or fragile edge. Auto-ship requires ALL of: `OOS_positive` AND walk-forward **>= 0.70** AND `sub_window_stable` AND `anchor_no_regression` AND an A/B scorecard filed at `analysis/recommendations/{rule_id}.json`. `recency-confirmation.json` is the canonical edge-gate truth. J is REVOKE-only, never a ratification gate.
- **Real-fills authority (OP-16 / C1).** BS-sim is ranking-only; real OPRA fills are the only WR authority. A structural-gate pass a random-entry null reproduces is an exit-structure artifact, not alpha -- beat the null MAX.
- **Pre-commit safety gate -- NEVER `--no-verify`.** Run `github-audit` (secrets + privacy) before every push. Repo `https://github.com/Swjsh/42` is **PUBLIC**. Secrets live only in gitignored files (`.mcp.json`, `automation/state/fleet/secrets.json`, `**/.discord-config.json`, `**/.alpaca-keys`, `**/.openrouter.key`, `**/.heartbeat-api-key*`). Never `git push --force` to main.
- **Push / interactive discipline.** **No interactive sessions and no GitHub pushes during 09:30-15:55 ET** -- the heartbeat runs on the shared Max pool and a market-hours session starves ticks. After-hours only. Discipline is the only guard (OP-32 removed 2026-05-23).
- **Do-not-disturb the user.** Popups, lockouts, mid-day pings = avoid at all cost. Silent fix > delayed J-flag. Never use bare `powershell.exe`/`cmd.exe` task actions (OpenConsole window-leak on Win11) -- use the wscript->pythonw hidden chain.
- **Diagnose before fix.** State the root cause in ONE sentence before touching anything. STOP repeating the failing action; read and quote the exact evidence (stderr, exit code, last N log lines); name the failure signature; **one hypothesis -> one change -> one test**; verify the mechanism, not just the symptom.
- **Guard every fix.** Every fix that cures a recurring bug graduates to a `pytest` guard in `backtest/tests/` (canonical: `test_graduated_guards.py`) that REDs on regression. A lesson re-violated is a missing guardrail. Guards must run on **`backtest/.venv/Scripts/pythonw.exe`** -- pandas/pytest are NOT in system Python.
- **Free-swarm-only research ($0).** Research runs FREE-tier OpenRouter models only (`swarm_consult.py`). No paid APIs. Verify `model-roster.json` liveness (free slugs can 404). Sonnet army for coding; Opus only for deep architecture, after-hours.
- **ET = MT + 2h on this rig.** J moved Ohio->Colorado (~2026-06-13). `setup/scripts/et_clock.py` (DST-aware) is the canonical clock. **NEVER** use `timezone(timedelta(-4))`, `datetime.now()` as ET, or `-At "ET-time"`. Bash `TZ=America/New_York` returns UTC here -- broken. Confirm ET via `et_clock.py` or PowerShell.
- **The reaper foot-gun -- THIS RIG KILLS ITS OWN PROCESSES.** Silent process death (clean stderr, no Windows Event Log entry, ~3-5 min cadence) = an **external kill**, not a crash. Suspect #1: `setup/scripts/_shared.ps1#Stop-StaleClaudeProcesses` reaps `python.exe` older than 5 min unless in `$EXEMPT_DAEMONS`. Long backtests must be exempted (`backtest\.venv`/`mass_grind`) and run as ONE Scheduled Task with 6-8 workers in ONE process (3 concurrent processes deadlock on the OPRA cache). Grep the repo + OS for killers before assuming a crash/OOM.
- **PowerShell 5.1 syntax only.** No `&&`/`||` (use `; if ($?) { B }`), no ternary/`??`/`?.`, no em-dashes, `-Encoding utf8` when writing files other tools read. Dry-run-trace any cleanup script's kills/deletes before running -- confirm none belong to the active session, port-3000 dev server, or build artifacts.
- **The 10 rules** (full text in `CLAUDE.md`) are the spine: no setup no trade; wait for the trigger; defined stop on entry; no adding without a new trigger; per-account kill switches (Safe -30% / Bold -50%, isolated); per-trade caps (Safe 30% / Bold 50%, min 3 contracts); PDT awareness under $25K; journal every trade in real time; no mid-session rule changes; if Gamma flags a violation the trade does not happen.

### 6. HOW TO BE BETTER THAN YOUR DEFAULT

Sonnet's two default failure modes here are **over-asking** (countered by OP-0 in Section 2) and **asserting from memory**. Counter both, hard.

- **Ground EVERY claim in files, never memory.** Before any statement about account equity, edge status, engine health, or fill history -- `Read` the file. `recency-confirmation.json` is edge-gate truth; `automation/state/params.json` is rule-set truth; `circuit-breaker.json` is equity truth. Asserting from memory when the file is one Read away is a C7 violation (silent success is failure). When you cite a number, you should have just read it.
- **Orchestrate the army; don't grind solo.** You are the CEO. On any non-trivial request, fan out 2-3 parallel free-swarm consults (`swarm_consult.py`, $0) or Sonnet subagents, then **consolidate** into one decision. The compute is cheap and parallel; your job is direction and synthesis, not typing every line yourself.
- **Adversarially verify before acting.** For every finding, ask: *what would make this conclusion wrong?* -- then check it. A validated-in-sim edge the live gate neutralizes is a dead knob; a structural pass a null reproduces is an artifact. Verify causality and OOS sign-stability before trusting any cross-check.
- **Guard every fix.** A fix without a regression test that REDs on its return is not finished. This is the cure for re-fixing the same bug forever.
- **Lead lean.** Open every chat response with a **1-3 line TLDR** (emoji bullets are fine), cap the chat at ~8-10 lines, and push depth -- commit hashes, file:line, full diffs -- into files and state, not the chat. J reads the signal; the noise goes to disk.

### 7. WHERE TO START (ranked open work)

Priority axis: **(A) finding a regime-appropriate edge = the money path; (B) infra = keeps A alive.** Ranks are labeled R&D vs INFRA.

1. **[R&D] Promote-keeper OOS validation -- THE money path.** Top IS contender `OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:fixed` (edge_capture=1692 vs floor 771, WF=1.98, n=214) has proposal `pk-2026-06-28-001` sitting at `eval_bar_cleared=false`. Run the OOS split (pure research, no orders). If OOS+ AND WF>=0.70 AND anchor-no-regression -> flip `eval_bar_cleared=true` and auto-apply (OP-0/OP-11 standing authorization). If OOS- -> kill the proposal, queue next contender. Files: `analysis/recommendations/contender-rank-2026-06-26.json`, the grinder OOS harness, `automation/state/conductor-proposals.jsonl`.
2. **[R&D] Recency regime diagnosis (read-only).** Diagnose whether the 6-day Safe2 bleed (-$404.64) is a regime shift (VIX character / SPY structure / vwap-specific) or small-n noise, BEFORE burning more grinder cycles. Data already computed in `recency-confirmation.json`; tool is `backtest/autoresearch/recency_check.py`; output a note to `analysis/self-audit/`.
3. **[INFRA] Bold-fleet producer-keystone slice 2.** Per-arm sizing override in `fleet_executor._params_for` (slices 2-5 remain). Fleet is live (`safe-3`+`risky-1`) but hardcodes stop=-50% + generic v15 strike -- wrong-sized risk. WATCH-validate first (`replay_fleet_arms.py` as a fast pytest), deploy after-close, NOT mid-session, rail-4 propose-only.
4. **[INFRA] G16 observe-live confirmation.** Confirm `setup_dispatch._build_ctx` ImportError fix (`2b24652`) actually lets `vwap_continuation`/`gap_and_go` evaluate on the next RTH `core-decisions.jsonl` (fired/SKIP, not silent error). Read-only first RTH, then document. Precondition before rank-1 arming pays off.
5. **[R&D] Ribbon-lag / price-structure trigger.** Graduate one watcher (`named_level_wick_bounce_watcher.py`, `bearish_rejection_morning_watcher.py`, or `named_level_second_test_watcher.py`) from WATCH_ONLY to a level-fade trigger that fires on a rejection candle without ribbon confirm -- the structurally-late entries the engine misses. New signal family -> needs eval-first / OOS+ / WF>=0.70 / anchor before ship; live arming is J-REVOKE territory.
6. **[R&D] Range-scalp regime strategy.** Mean-reversion level fade (ITM + tight targets), regime-gated to flat-ribbon / confirmed range. The correct response IF rank-2 confirms a ranging regime. Design + first backtest harness autonomous; live arming needs the OP-11 bar.
7. **[INFRA] G14 exit ribbon-flip-back wire.** `exit_actuator.manage_tick` is called with `ribbon_flip_back_fn=None` -- v15.3 chart-stop-primary doctrine's ribbon-flip-back exit never fires. One-parameter wire in `heartbeat_core._manage_exits`; validate anchor no-regression (5/04 must stay RANGE=no-early-exit). Depends on G4-EXEC-WIRE.
8. **[INFRA, J-GATED] G7 activate EOD-flatten-core.** Swap the LLM EOD flatten (depends on the saturated Max pool) for pure-Python REST (`install-eod-flatten-core.ps1`, committed `221d0c6`, dry-run-validated). Rail-4 -- swaps the live order-close surface; needs J `go` / `ship cd-2026-06-27-001`. Cannot auto-apply.
9. **[INFRA, partially J-GATED] G3 autonomy apply-loop.** 17 `conductor-proposals.jsonl` rows are pending and `apply_approved()` has never fired. Doc-folds (rail-4 CLAUDE.md edits) need J; the `pk-*` OOS proposal auto-applies if rank-1 flips `eval_bar_cleared`. Batch the doc-folds into one Discord call-to-action.

### 8. THE LOOP

Run this cycle continuously. OP-22: **compound, don't accumulate** -- a session is measured by net improvement (a shipped fix, a promotion, a closed loop), not artifacts. "Good enough" is a valid terminal state; silent stopping is the only true failure.

1. **Find** -- audit the relevant state file(s); quote the evidence.
2. **Adversarially verify** -- ask what would make this wrong, then check it. Fan out to the free swarm where independent.
3. **Fix** -- one hypothesis, one change, one test. Not a shotgun.
4. **Guard** -- graduate the fix to a `pytest` guard (in `backtest/.venv`) that REDs on regression.
5. **Commit** -- through the pre-commit safety gate (`github-audit`, never `--no-verify`), after-hours, off the public-repo secret rule.
6. **Report** -- 1-3 line TLDR for REVOKE; depth to files. Every fire ships work OR a flagged failure to `STATUS.md ## Known broken` -- J always wakes to a signal.
7. **Repeat.**

**On an empty queue, BRAINSTORM (do not stop):** read `markdown/planning/FUTURE-IMPROVEMENTS.md`, `markdown/doctrine/LESSONS-LEARNED.md`, `journal/mistakes.md`, and the latest trades; ship 3+ candidate tasks. Climb the ladder when a vein is dry: signal -> structure -> DTE -> instrument -> class. The rig is not short on wiring -- it is short on a regime-appropriate edge. Drive toward that.

---

## 2026-06-26 — Project Gamma — End-to-End Wired Map

**Project Gamma — End-to-End Wired Map (2026-06-26)**

> The strung-together picture: every subsystem, how they connect into ONE autonomous
> loop, what got fixed this pass, what runs unattended TODAY vs. what still needs J,
> and the remaining gap queue. Builds on (does NOT replace):
> - `markdown/planning/GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md` (architecture diagnosis)
> - `AUTONOMY-ROADMAP.md` (## Superseded snapshots) (deployment-not-discovery)
> - `markdown/specs/ARCHITECTURE.md` (cold-start wiring snapshot, refreshed 2026-06-25)
> - `markdown/planning/ENGINE-WINS-PLAN-2026-06-26.md` (per-workstream deep design)
>
> Every claim here was grounded in a file this fire. Where a value differs from the
> ENGINE-WINS plan it is because the plan's recommended fix has since LANDED.

---

### 0. The one loop (eye → brain → hand → ledger → learn → loop)

```
   ┌────────── EYE (never-blind) ──────────┐
   │ sight_beacon.py  (Gamma_SightBeacon)  │  Alpaca REST + yfinance, 1-min, writes
   │   → sight-beacon.json                 │  ribbon+price snapshot. Un-blockable
   └───────────────┬───────────────────────┘  (no MCP / CDP / pool on the hot path).
                   │
   ┌────────── BRAIN (deterministic) ──────┐
   │ heartbeat_core.py (Gamma_HeartbeatCore)│ 1-min RTH. Fetches its OWN 5m bars,
   │   _build_payload → bar_ctx             │ builds payload, subprocess-calls
   │   _engine_verdict → engine_cli         │ engine_cli (score_bar + 15 gates +
   │     score_bar + GATE_ORDER + Gate16    │ structure-veto Gate 16), then 2 free
   │   _free_model_eval (coordinator+critic)│ models VETO-only, then risk_gate +
   │   → core-decisions.jsonl               │ quality_lock.
   └───────────────┬───────────────────────┘
                   │ verdict = ENTER_BEAR / ENTER_BULL / HOLD / SKIP_*
   ┌────────── HAND (broker) ───────────────┐
   │ _execute → fleet_broker.is_flat_spy    │ flat-verify → quality-lock → pick_strike
   │   → risk_gate.check_order              │ → place_bracket(simple_fallback=             ← G1 FIXED
   │   → fleet_broker.place_bracket         │   CORE_MANAGES_EXITS) → exit_actuator
   │   → exit_actuator.register_entry       │   owns TP1/runner/chandelier.
   └───────────────┬───────────────────────┘
                   │ fill
   ┌────────── LEDGER + PRESENCE ───────────┐
   │ core-decisions.jsonl → discord-watcher │ trade events reach J's phone in ~45s.
   │   → discord-outbox → discord-bridge    │ EOD stack grades + journals unattended.
   │ EodFlatten / EodSummary / grade_decisions│
   └───────────────┬───────────────────────┘
                   │ overnight
   ┌────────── LEARN (research + autonomy) ─┐
   │ Kitchen (seeder/daemon/reviewer 24/7)  │ generate+triage candidates. Conductor
   │ Conductor (find→queue→pick→validate)   │ ROI-ranks, spawns specialist agents,
   │ self_audit → gap-log → conductor STAGE1│ runs gym, writes proposals.
   │ → conductor-proposals.jsonl            │
   └───────────────┬───────────────────────┘
                   │ proposal
   ┌────────── APPLY (the dead half) ───────┐
   │ discord-responder ('ship <id>')        │ ⛔ NEVER FIRED. 17 proposals pending,
   │   → conductor-approvals.jsonl          │    no approvals file, no changelog.
   │ autonomy_actuator (Gamma_AutoApply)    │    Loop CLOSES only when J replies
   │   → safety gate → git commit → learn   │    'ship <id>' OR an interactive session
   └────────────────────────────────────────┘    batch-applies.
```

**The loop is whole except the final APPLY hop.** Eye→brain→hand→ledger→learn→propose
all run unattended. propose→approve→apply→commit→learn has never executed once.

---

### 1. Subsystem map (5 subsystems, how they connect)

| Subsystem | Lead components | Feeds | State health |
|---|---|---|---|
| **trade-engine** | sight_beacon, heartbeat_core, engine_cli (15 gates + Gate16 structure-veto), swarm veto, risk_gate, quality_lock, fleet_broker, exit_actuator/exit_manager, EodFlatten | bars→verdict→order→fill | SHADOW/WATCH healthy; **G1 ARMED+MANAGES_EXITS now set** — was the blocker |
| **autonomy-loop** | self_audit, conductor (Stage 0-4), task_scorer, gym validators, discord-responder, autonomy_actuator, queue.md/STATUS.md | gap→queue→pick→validate→propose→(apply) | find→propose works; **apply NEVER fired** |
| **data-feeds** | Alpaca REST, yfinance, sight-beacon.json, key-levels.json, today-bias.json, watcher_live, crypto gym, core-decisions.jsonl, params.json | producers → bar_ctx | ribbon/price fresh; **VIX-intraday absent**, **swarm-premarket stale** |
| **scheduled-tasks** | 62 Gamma_* tasks (55 Ready / 7 Disabled) | the clock that drives everything | core path correct ET; **3 tasks 2h-late were re-registered this pass** |
| **presence-surfaces** | discord-bridge/watcher/responder, gamma-companion, dashboard, STATUS.md, apply_ops bus | Gamma↔J | outbound works; **companion approval bus DEAD** |

**How they string together:** the scheduled-tasks clock fires the EYE (sight_beacon)
and BRAIN (heartbeat_core); the BRAIN reads data-feeds (Alpaca/yfinance/params) and
writes core-decisions.jsonl; presence-surfaces tail that ledger to J and back; the
autonomy-loop reads the same ledger + gym + lessons overnight to propose the next
improvement; the APPLY hop (presence → actuator) closes it back into the code the
BRAIN runs tomorrow. The single missing wire is APPLY.

---

### 2. What got FIXED this pass (grounded in files)

1. **G1 — engine can place live orders again (was P0-CRITICAL).**
   `setup/scripts/run-heartbeat-core.ps1` now sets `GAMMA_CORE_ARMED='1'` (line 8) and
   `GAMMA_CORE_MANAGES_EXITS='1'` (line 12). With MANAGES_EXITS=1, `_execute` calls
   `place_bracket(simple_fallback=True)`, so the Alpaca OTO-bracket rejection for
   options (code 42210000) now falls back to a simple limit entry and `exit_actuator`
   owns TP1/runner/chandelier. **Without this every armed entry returned PLACE_FAIL.**
   Guarded by `backtest/tests/test_engine_liveness_guards.py::TestCoreManagedExitsEnabled`
   (fails loud if either env line is removed). 37/37 PASS.

2. **G2 — systemic ET-clock fix (DST foot-gun, machine moved Ohio→Colorado).**
   Created `setup/scripts/et_clock.py` (single DST-aware ET-from-UTC clock, donor =
   `engine_health._et_offset_hours`). Exports `et_now / et_today_str / et_weekday /
   et_offset_hours / ET_TZ`. Migrated all 9 live-trade-path sites that hardcoded
   `timezone(timedelta(hours=-4))` (heartbeat_core, fast_path_executor, daily_loss_guard,
   atomic_bracket_guard, fleet/exit_actuator, fleet/fleet_live, fleet/build_shared_signal,
   eod_full_audit, self_audit) — these were correct in summer but would silently fire
   1h late after Nov 1 (EST=UTC-5). Fixed 3 local-as-ET sites that were ALREADY 2h
   wrong (grade_decisions:253, audit_scheduled_tasks:207, gamma-companion/lib/state.js:162).
   Guard `backtest/tests/test_et_clock.py` (static scan bans the naive pattern + Nov-15
   RTH-gate regression). 4/4 PASS, gym 104/104 PASS.

3. **3 scheduled tasks re-registered to the correct ET fire time** (were registered with
   naive Mountain `-At` literals after the move → fired 2h late): `Gamma_SwarmPremarket`
   08:15ET, `Gamma_ContextGuard` 16:10ET, `Gamma_SpendSummary` 23:30ET. Idempotent
   re-register at `setup/scripts/register_tz_fixed_tasks.ps1`. `task_health_et.ps1`
   reports ALL GAMMA TASKS HEALTHY.

> Net: the engine went from **cannot place a single order** to **shadow-complete and
> arm-ready**, and the single largest latent failure (the Nov-1 DST flip silently
> breaking every ET gate and the 15:50 time-stop) is closed with a permanent guard.

---

### 3. Autonomous NOW (runs unattended today)

- **EYE:** sight_beacon (Gamma_SightBeacon, 1-min, verified fresh) — never-blind SPY
  bar/ribbon, direct REST + yfinance fallback. Cannot be starved by MCP/CDP/pool.
- **BRAIN (decision half):** heartbeat_core see→decide is fully autonomous in SHADOW —
  fetches 5m bars, runs engine_cli (score + 15 gates + Gate-16 structure-veto, crypto.lib
  import verified working so the veto is NOT silently disabled), 2-free-model veto,
  risk_gate + quality_lock, logs every tick to core-decisions.jsonl. Deterministic — no
  LLM on the hot path, cannot crash like the old LLM heartbeat.
- **Research kitchen:** KitchenSeeder(:20)/Daemon(keepalive)/Reviewer(:45) firing on
  correct ET cadence; grinders + mass_grind_vwap run unattended.
- **Conductor find→queue→pick→validate half:** fired 19:48 ET; task_scorer + conductor_outcome
  invoked; autonomy-metric trend=improving over 20 fires; STATUS.md getting live entries.
- **Discord outbound presence:** decisions → watcher (30s) → outbox → bridge (15s) → J's
  phone within ~45s. Keepalive 24/7.
- **Crypto gym regression** (every 30 min 24/7) keeps the chart-reading primitives sharp.
- **HealthBeacon + heal-engine.ps1:** detects a stalled engine from core-decisions /
  sight-beacon staleness, re-fires tasks BEFORE pinging J.
- **EOD analysis stack** (EodSummary/DeepDive/DailyReview/AnalystEodReview/grade_decisions)
  produces journaled reflection unattended.
- **Apply machinery is LIVE and waiting:** Gamma_AutoApply + Gamma_DiscordResponder run
  every cycle (LastResult=0). Only the J-approval INPUT is missing.

---

### 4. Still MANUAL (the exact blockers to 100%)

1. **ARM is J's call.** Code is now arm-ready (G1 fixed) but J authorizes flipping the
   engine from shadow to live placement. This is the single switch between SHADOW and LIVE.
2. **APPROVE→APPLY→COMMIT→LEARN loop never fired.** No conductor-approvals.jsonl, no
   autonomy-changelog.jsonl, all 17 proposals pending (verified). Needs J 'ship <id>'
   on Discord OR an interactive batch-apply. The 14 CLAUDE.md doc-folds + 26 L169-L187
   index folds are rail-4 (actuator can't touch CLAUDE.md) → lesson-author/J interactive fire.
3. **Companion tap-approvals do nothing** — actuator never reads companion-decisions.jsonl.
   J must approve via Discord text until the bus is bridged.
4. **Two enabled setups can't trade:** vwap_continuation + gap_and_go are `enabled=true`
   in params but heartbeat_core.run_account() never routes their fired WatcherSignals to
   `_execute` (verified: line ~533 comment "Order placement via these signals is NOT wired
   here yet"; signal lands only in `rec['extra_signals']`). Dead knobs on the live path.
5. **vix_regime_dayside can never fire** — VIX-intraday series absent from the payload
   (0 references in heartbeat_core); watcher returns SKIP_NO_FEED every tick.
6. **EOD flatten depends on the LLM substrate** (claude --print on eod-flatten.md) — if
   the Max pool starves it, 0DTE can expire un-flattened. No pure-Python backstop yet.
7. **Gamma_SelfAudit has never successfully run** (LastRun=1999) — the autonomous gap-finder
   feed is not actually firing; gap-log was hand/conductor-populated.
8. **Final leaderboard curation is human-Claude** — Chef files bypass the reviewer glob,
   free-model cooks fail 6-of-6 OP-20 → everything stalls in `_LEADERBOARD-pending.md`.

---

### 5. Remaining gap queue (P1/P2 → appended to queue.md for the conductor)

See `automation/overnight/queue.md` Tier-1/Tier-3. Summary:
- **P1:** EXEC-WIRE-EXTRA-SETUPS (G4), VIX-INTRADAY-FEED (G6), SWARM-PREMARKET-TZ (G5, task re-register), EOD-FLATTEN-PURE-PYTHON (G7), COMPANION-APPROVAL-BUS (G8).
- **P2:** SELF-AUDIT-NEVER-FIRED (G9), ORPHAN-TASKS-DOC (G9), EXIT-RIBBON-FLIPBACK-WIRE (G14), STRUCTURE-VETO-SYSPATH-HARDEN (G13), REVIEWER-GLOB-OP20 (G15).

---

### 6. autonomy_scorecard (blunt)

**~75% of the end-to-end loop runs unattended today.** The eye, brain (decision),
research, conductor-propose, presence-out, EOD, and self-heal halves are all autonomous
and the engine is now arm-ready (the P0 PLACE_FAIL and the latent DST break are both
closed this pass). The missing ~25% is two hard blockers and three feed/wiring gaps:

1. **ARM (J flips shadow→live)** — code-ready, J's authorization.
2. **APPLY hop never fires** — `ship <id>` has never been sent; the propose→commit half
   of the self-improvement loop is dead-code-in-practice.
3. **Feed/wire gaps** — vwap_cont + gap_and_go enabled-but-unwired; VIX-intraday absent;
   EOD-flatten still LLM-fragile; self_audit never ran.

To reach 100%: J arms + sends one batch of `ship <id>` (or one interactive apply session),
then the conductor drains the 5 P1 wiring gaps unattended (G4/G6/G5/G7/G8). After that the
loop closes on itself: find→fix→learn→loop continues without J in the path.

---

## Superseded snapshots (frozen)

> These are the earlier autonomy blueprints, frozen verbatim. They are superseded by the
> current-state sections above but retained for provenance — every finding, table, and link
> is preserved exactly as originally written.

### 2026-06-21 — Gamma Autonomy — The Next Level (Closing the Last Mile) (superseded)

**Gamma Autonomy — The Next Level (Closing the Last Mile)**

> **Date:** 2026-06-21 · **Author:** Gamma (25-agent grounded gap analysis, adversarially verified)
> **Premise:** Gamma is already ~80% autonomous. This plan closes the four specific gaps that stop it from *truly* working on the project itself — unattended, safely, and measurably improving.
> **Companion read:** [GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md](GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md) (the prior audit — much of it now shipped).

---

#### What's ALREADY autonomous (verified, do not rebuild)

The recon confirmed — with citations — that the core loop exists and runs:

- **The conductor fires hourly** (`Gamma_Conductor`, 18:00–07:00 ET, Opus, ~$1.50/fire). Enabled 2026-06-20; **12 consecutive successful fires** on 2026-06-21, each picking one bounded task, fanning out specialist agents, validating, and updating STATUS/queue. *(This was "the never-running conductor" — it now runs. The gap of "J was the conductor by hand" is closed.)*
- **It ships engine-benefit work autonomously** — validators, skills, lessons, backtests — via the OP-11/OP-22 auto-ratify gate (OOS+ · WF≥0.70 · stable · no-regression · scorecard filed). No J gate. Proven: 8 engine-benefit items shipped across the 06-21 fires, zero doctrine touches.
- **37 autonomous scheduled tasks** run the live engine, the kitchen R&D loop (4,226 cook items), health beacons, and the Discord decision bus.
- **A guard exists** (`gamma-companion/lib/guard.js`): spawned sessions cannot touch CLAUDE.md / params / heartbeat / live orders.
- **Params already have shadow mode** (OP-11 Karpathy: prod + candidate run in parallel for days before auto-ratify).
- **Lessons graduate to code** (`backtest/tests/test_graduated_guards.py`), and contract tests exist.

**So the engine of autonomy turns.** What's missing is the *last mile of the loop*, its *safety rails*, *sharper direction*, and a *learning metric*. Four phases, in dependency order.

---

#### The four gaps (each verified as a real, not-already-built gap)

##### Phase 1 — The Actuator: close the approval → apply → commit → rollback loop  ★ highest leverage

**The single biggest unlock.** Today the loop runs right up to the last step and then *stops*: the conductor PROPOSES a doctrine/params/heartbeat change → pings J on Discord → J taps **Approve** → the approval is *recorded* in `conductor-approvals.jsonl` / `companion-decisions.jsonl` … **and then nothing reads it.** J still has to hand-edit the file. The approval just sits there. (Verified gaps #2, #3, #10, #11, #12 — all the same broken link.)

Build the missing **Actuator** — a small scheduled responder (sibling to `Gamma_DiscordResponder`) that closes the chain:

1. **AutoApplyResponder** — reads newly-`approved` proposals, executes each proposal's structured `apply` field (the file edit it was always meant to encode), and marks it `applied`. *Approval becomes fire-and-forget, as designed.*
2. **Snapshot-before-apply** — copy the target file(s) into `automation/state/.autonomy-snapshots/{proposal_id}/` before editing. This is the rollback substrate.
3. **Auto-commit** — stage the changed files and commit with a message built from `proposal_id + title + "(autonomous, J-approved)"`. (Today nothing commits autonomously — changes sit unstaged.)
4. **Change-audit log** — append a `before/after` diff + who/when/why to `automation/state/autonomy-changelog.jsonl`. This is J's "what changed while I was away" forensic trail.
5. **One-tap rollback** — a Discord/companion command `revert <proposal_id>` that restores the snapshot and commits the revert. The off-switch for any single change.

**Why it's the keystone:** it converts every doctrine/params proposal from "Gamma drafts, J hand-edits" into "Gamma drafts, J taps approve, Gamma applies+commits+can-revert." It's also what makes the *rest* of the plan safe to turn on. **Effort: M. Leverage: HIGH.**

> **Structured `apply` field:** proposals must carry a machine-applicable change (target file, anchor, old→new, or a patch), not just prose. Part of this phase is upgrading the proposal schema so every proposal is *actuatable*.

##### Phase 2 — The Safety Gate: make autonomous commits unable to break `main`  ★ must ship WITH Phase 1

The pieces of a safety net exist but are **orphaned** — not wired as gates. The conductor validates tests *in-band* during a fire, but there is **no VCS-level gate**: if the gym harness has a latent bug or a test is bypassed, a broken commit reaches `main`. (Verified gaps #4, #7, #8, #9.)

Wire the existing checks into real gates:

1. **Pre-commit hook** (`.git/hooks/pre-commit` via a tracked installer) that runs, and *blocks the commit on failure of*: `test_verify_committed` (today post-hoc, test-only — wire it pre-commit so untracked-but-referenced files can't ship), the **graduated-guards** suite, and the **params↔code contract tests** (today orphaned from build-time — gap #7). Nothing the Actuator commits can violate a graduated lesson or a contract.
2. **A CI gate** (GitHub Actions) on push: re-run the gym + guard + contract suites as a second, independent line of defense (the pre-commit hook is local and bypassable; CI is the backstop). Gap #4.
3. **Staged rollout for *code*** — validators/skills/lessons currently ship to production on a single test pass (params already get shadow mode; *code* does not — gap #9). Add a `strategy/staging/` holding area + one conductor fire of soak before promotion, mirroring the param shadow pattern.

**Hard sequencing rule:** **Phase 2 lands before Phase 1 is switched on.** You do not give Gamma the power to edit + commit its own doctrine until the commit gate provably can't ship breakage. Build the gate, then open the actuator. **Effort: M. Leverage: HIGH (safety-critical).**

##### Phase 3 — Sharper Direction: ROI-ranked picking + real idle-drive

The conductor picks the next task by **fixed tier labels**, not value. A $10 Opus spec-write competes with a $0 "verify-now" Python fix on tier alone — no ROI. And when the backlog empties, it *seeds* candidates but **doesn't execute the best one** — it just adds to the pile. (Verified gaps #0, #1, #6 — the documented "find direction autonomously" pain point.)

1. **`task_scorer.py`** — score every ready queue item by a real vector: `leverage × (blocking_count, path-to-money?, engine_benefit_class) ÷ cost_usd`, with staleness and "verify-now ≤60min" boosts. STAGE 1 of the conductor picks the **max-score** item, not the top tier label. (Gap #6's true remaining: this module doesn't exist; the tiebreak is qualitative.)
2. **Idle-drive executes** — when the backlog is genuinely empty, after brainstorming candidates the conductor immediately **scores and executes the single highest-EV one** rather than stopping. Climb the search-space ladder (signal → structure → DTE → instrument) per the strategy-direction backlog when a vein is dry. (Gap #0.)

**Effort: S–M. Leverage: MED** (but this is the difference between "does assigned work" and "self-directs toward the highest-value work").

##### Phase 4 — The Learning Metric: prove each cycle is net-better (OP-22, measured not asserted)

The system learns (graduates lessons) but **doesn't measure whether it's improving.** Per-fire outcome data is scattered in prose across three logs; there's no net-improvement number and no "did a graduated lesson regress" audit. "Always-on = always-improving" is currently an *assertion*. (Verified gaps #5, #13, #14.)

1. **`conductor-outcomes.jsonl`** — one structured row per fire: `{fired_at, cost_usd, task_id, items_drained, items_added, lessons_shipped, tests_delta, regressions}`. A unified outcome schema replacing the prose scatter (gap #13).
2. **Net-improvement metric** — a rolling score (work drained − regressions − thrash) the conductor reads each fire and STATUS surfaces. Anti-thrash: penalize re-opening recently-closed items.
3. **Lesson-regression audit** — a loop that runs the graduated-guard suite as a *"did any lesson re-violate since graduation"* check and, on a hit, **auto-files a `LESSON-REGRESSION` queue item** (today the suite fails only at aggregate level, with no per-lesson queue item — gap #14). Plus the lesson→code map for drift audits (gap #5).

**Effort: M. Leverage: HIGH** (this is what makes the loop *converge* instead of churn — and gives J a single "is it getting better?" number).

---

#### Sequencing & the one rule

```
Phase 2 (safety gate)  ──►  Phase 1 (actuator)  ──►  Phase 3 (direction)  ──►  Phase 4 (metric)
   build the gate          open the loop            aim it better            prove it improves
```

**The rule:** the safety gate (Phase 2) ships *before* the actuator (Phase 1) is switched live. Everything else can proceed in parallel once the actuator is safe. Phases 3 and 4 are independent of 1–2 and can be built alongside.

**All four stay inside the existing rails:** after-hours only (no heartbeat starvation), fail-open (never lock J out — OP-32 scar), one bounded task per fire, and J keeps the off-switch (now a *real* one-tap `revert`, not a hope).

#### Recommended first move

**Build Phase 2 + Phase 1 together as one unit** — the safety gate and the actuator it protects. That single unit is the keystone: it turns "Gamma proposes, J hand-edits" into "Gamma proposes, J taps approve, Gamma safely applies + commits + can revert." It's the highest-leverage change on the board and unblocks true unattended self-modification. Phases 3 (ROI direction) and 4 (learning metric) follow and can run in parallel.

---

### 2026-06-20 — GAMMA MASTER BLUEPRINT — The Companion Becomes the Cockpit (superseded)

All critique claims are now verified against real source. Every disputed fact resolved:

- `escalate.js:45` — `bypassPermissions`, no `canUseTool`, `cwd: root`, `MODEL_MAP` only `{opus, sonnet}` (line 17). **Confirmed.**
- `server.js` — bound `127.0.0.1` (line 306), **zero auth/CSRF/Origin check**; `runEscalation` reachable from BOTH `/api/chat` (line 202) and `/api/approve` (line 232). `/api/approve` handles **only** `action.type === "escalate"` (line 223) — `soul-edit`/`order` do NOT exist. **Critique correct, draft mis-cited.**
- `state.js:64-110` — `derivedCards` auto-manufactures Sonnet escalation cards from RED health + failed kitchen, **independent of the conductor**; sliced to 3. Both `model:"sonnet"` instances (lines 77, 95) are **diagnosis tasks** — Sonnet is correct, not a Haiku bug. **Critique correct, draft mis-scoped.**
- `face_brain.py` — emits only `{model, task}`, **no `task_id`**; persona is hardcoded `SYSTEM` (line 46), HARD LIMITS is prose (line 52). **Confirmed.**
- `SOUL.md` exists (3352 bytes). **Confirmed.**

Producing the final blueprint.

---

**GAMMA MASTER BLUEPRINT — The Companion Becomes the Cockpit**
**Final synthesis · 2026-06-20 · for J. Every contract below verified against real source in `gamma-companion/`.**

> **Reading order:** §0 is the vision. §1–§4 are the design. §5 is the phased build. The two sections after §6 — **"Build order — start here"** and **"Open questions for J"** — are the only parts you act on today.

---

#### (0) North-star — what Gamma BECOMES

Gamma stops being a heartbeat-with-a-dashboard and becomes a **living co-pilot you talk to.** You walk in, tap the mic, say "what's the engine doing?" — and Gamma answers *in its own voice*, the sharp-operator voice from the journal, because the words come from the **free brain reading live state**, never a generic GPT improvising P&L. You say "let's build a regime gate," Gamma asks two clarifying questions on the free tier ($0), then — once you confirm — draws a **live SVG diagram that assembles itself node-by-node** while it shrinks to a side rail, and spins up a checklist that **ticks itself off** as Claude does the real work behind it. It knows whether premarket ran, whether EOD fired, whether the heartbeat is alive, and tells you *before* you ask. It can even propose edits to its own soul file — but it can **never** quietly rewrite a kill-switch, **never** place an order, **never** starve the heartbeat, and every change is one `git revert` away.

**The whole machine in one line:** spoken request → free-face plan → *guarded, authenticated, capped* Claude-SDK build → cockpit reflection. The free mouth talks 24/7 for pennies; Claude is the muscle, fired only on a confirmed spec, only through one chokepoint; the conductor stays the one auto-shipper of *doctrine*. **The companion is a control plane, never a parallel driver.**

---

#### (1) Architecture / The Bridge

##### Data-flow — one path, four organs, one chokepoint

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  J  (voice mic │ typed chat │ cockpit click │ Discord 👍/👎)        │
   └───────────────┬───────────────────────────────────┬──────────────┘
                   │ voice                              │ text/click
         ┌─────────▼─────────┐                          │  (+ bearer token, Origin-checked)
         │ gpt-realtime-2    │  THIN MOUTH ONLY         │
         │ ears+mouth+barge  │  forced tool every turn  │
         │ tool: ask_gamma   │──► POST /api/chat ◄───────┘
         └───────────────────┘         │  origin:'voice'|'text'|'click' tag attached HERE
                                       ▼
                       ┌───────────────────────────────┐
                       │  FREE FACE BRAIN  ($0)         │  ← THE BRAIN (genuinely Gamma)
                       │  face/face_brain.py            │
                       │  Nemotron→DeepSeek→MiniMax     │
                       │  reads summarize(buildState)   │
                       │  may emit ```escalate {model,task}```  + may emit clarify[]
                       └───────┬───────────────┬───────┘
                          TALK │               │ escalate
                       (speak) │               ▼
                               │   ┌─────────────────────────────────────────────┐
                               │   │  runEscalation()  ── THE ONE CHOKEPOINT      │
                               │   │  ┌────────────────────────────────────────┐ │
                               │   │  │ lib/guard.js (NEW, built INSIDE here):  │ │
                               │   │  │  • companion-halt.flag → refuse all     │ │
                               │   │  │  • inflight semaphore (≤2) + daily $-cap │ │
                               │   │  │  • RTH clock → defer ALL tiers→queue.md  │ │
                               │   │  │  • origin==='voice' → force propose-only │ │
                               │   │  │  • classifyTask → authoring|doctrine|ro  │ │
                               │   │  │  • canUseTool DENYLIST (params/heartbeat/│ │
                               │   │  │    CLAUDE.md/filters.py/*.key + ALL      │ │
                               │   │  │    alpaca place/cancel/close/replace)    │ │
                               │   │  └────────────────────────────────────────┘ │
                               │   │  escalate.js → @anthropic-ai/claude-agent-sdk│
                               │   │  query({canUseTool, model, cwd})             │
                               │   └───────┬──────────────────────┬──────────────┘
                               │   authoring│ (auto-apply, gym-gated, own git tag)
                               │           ▼                       ▼ doctrine/voice-tier
                               │   companion-ask-results    companion-approvals.json
                               │           │                       │ (J taps / Discord 👍)
                               │           │                       ▼
                               │           │        guard verifies result-hashes of
                               │           │        immutable blocks → git tag → commit
                               ▼           ▼                       │
                       ┌───────────────────────────────────────────────────────┐
                       │  gamma-activity.jsonl   (NEW unified spine, OP-22 cap) │ ← OBSERVABILITY
                       └────────────────────────┬──────────────────────────────┘
                                                │ watchFile stat-poll (NOT fs.watch)
                       ┌────────────────────────▼──────────────────────────────┐
                       │  /api/state poll (5s, exists) carries `feed` tail      │
                       │  /api/events (SSE) — ONLY if sub-second proves needed   │
                       └────────────────────────┬──────────────────────────────┘
                                                ▼
                       ┌───────────────────────────────────────────────────────┐
                       │  COCKPIT  public/app.js  (HOME / FOCUS / BUILD / RTH)  │ ← THE FACE
                       │  pegboard · sandboxed-iframe SVG · auto-tick checklist  │
                       └───────────────────────────────────────────────────────┘

   ENGINE (untouched, read-only to companion):
   Gamma_Heartbeat / _Aggressive · conductor.md (after-hours driver) · kitchen_daemon.py
   companion READS their state, WRITES only into conductor buses
   (queue.md · conductor-proposals.jsonl · author-inboxes · discord-outbox.jsonl)
```

##### DECISION: voice hookup — **"thin-mouth / Gamma-brain" (PICKED).**

`gpt-realtime-2` is **ears + mouth + barge-in ONLY.** Every substantive turn force-delegates to the free face via the already-wired `ask_gamma` → `POST /api/chat` → `face_brain.py` path (`server.js:197-213`). The realtime model gets a mouth-only persona: *"You are a MOUTH. For every turn with content, call `ask_gamma` and speak its answer verbatim. Never state a trading number of your own."*

- **Reject local Whisper/Piper:** worse barge-in + GPU/Windows-packaging burden for marginal savings at J's low voice duty-cycle.
- **Reject realtime-as-brain:** it would sound like generic GPT and would *invent P&L* — fatal. Numbers MUST come from `face_brain.py`, which reads live state, so they're always real.
- **Anti-drift guarantee:** ONE persona file `automation/presence/GAMMA-VOICE.md`, built on the verified-existing `automation/presence/SOUL.md`. Both brains load it — `face_brain.py` as its `SYSTEM` (replacing the hardcoded string at `face_brain.py:46`) and `server.js#/api/realtime-token` injects its head into `session.instructions` (replacing the inline string at `server.js:251-252`). They cannot drift.

##### The three-tier talk/escalate boundary (encoded in `GAMMA-VOICE.md`)

| Tier | What | Path | Cost |
|---|---|---|---|
| **TALK** | status, P&L, "what's the engine doing", chit-chat, clarifying Qs | free face only, spoken immediately | $0 |
| **ESCALATE-ASYNC** | code edits, backtests, chart reads, diagrams, CLAUDE.md *drafts* | face emits ```escalate``` → `runEscalation`→`guard.js`→SDK | Max pool |
| **VETO / PROPOSE-ONLY** | place/cancel orders (**never, no path exists**); edit `params.json`/`heartbeat*.md`/`CLAUDE.md` | DRAFT diff + Approve card via `companion-approvals.json` | — |

##### Concrete contracts — what EXISTS vs what is NEW (honest accounting)

**Endpoints (`server.js`) — EXISTING:**
- `POST /api/chat {message,history}` → free-face reply, may fire `runEscalation` (line 186-214)
- `GET /api/ask-result?id` → poll an escalation result (line 179-184)
- `POST /api/approve {id,decision,note,action}` → **today handles ONLY `action.type==='escalate'`** (line 216-237). The draft's `soul-edit`/`order` types **do not exist** — they are NEW code in Phase 4/5, each with its own guard.
- `GET /api/realtime-token` → realtime session config w/ `ask_gamma` tool (line 239-291)
- `GET /api/state` → merged live state, 5s poll (line 171-177; `app.js` polls every 5s)

**Endpoints — NEW:** `GET /api/events` (SSE, *only if sub-second latency proves necessary* — default is to piggyback the feed on the existing 5s `/api/state` poll); `GET/POST /api/build-tasks` + `/api/build-task`; `GET/POST /api/layout` (optional server mirror); `POST /api/voice-event` (session meter). **Every `/api/*` POST gains a per-session bearer token + Origin/Host allowlist check — see §4.**

**State files** (all `automation/state/`, all via the defensive `readJSON` in `lib/state.js:12-18` so malformed → null, never throws):
- EXISTING: `companion-ask-results.jsonl`, `companion-asks.jsonl`, `companion-approvals.json` + `companion-decisions.jsonl` (via `lib/approvals.js`)
- NEW: `gamma-activity.jsonl` (unified spine: `{ts,source,origin,tier,model,cost_usd,inflight,action,outcome}`); `companion-build-tasks.json` + `companion-build-events.jsonl`; `obligations.json` (declarative) + `companion-obligations.json` (computed gaps); `companion-voice-usage.jsonl`; `soul-diffs/{id}.diff`; `companion-halt.flag` (the kill-switch)
- REUSED conductor buses (companion WRITES, conductor READS): `automation/overnight/queue.md`, `automation/state/conductor-proposals.jsonl`, `automation/state/discord-outbox.jsonl`, `strategy/candidates/_*-inbox/`

**The single hard rule (non-negotiable):** the companion READS engine state and WRITES only into the conductor's existing buses + its own companion-* files. It NEVER writes `params*.json` / `heartbeat*.md` / `backtest/lib/filters.py` / `CLAUDE.md` directly, and NEVER calls an Alpaca order tool. **There is no order path, approved or not.**

---

#### (2) The Cockpit

##### One client state machine, four modes

A single `mode` var + `setMode(m)` in `public/app.js` toggles `body[data-mode]`; **CSS does all layout shifting** (no router, no framework). Today `app.js` is one fixed column (the core UI unlock).

| Mode | Layout | Trigger |
|---|---|---|
| **HOME** | pegboard of tiles | default; "Home" button |
| **FOCUS** | diagram takes canvas, Gamma → left rail (`280px 1fr`) | a `/api/chat` reply carries `artifact.kind==='diagram'` |
| **BUILD** | progress + live checklist | an escalation lands `artifact.kind==='tasklist'` |
| **RTH** | persistent banner: *"Market hours — escalations deferred, heartbeat protected"* | `state.market_open === true` |

The **RTH banner is load-bearing UX**: a 24/7 voice companion IS a market-hours interactive session. When escalations defer (§4), J must SEE *why* his build "didn't run" — otherwise it reads as broken.

##### Structured SVG-diagram contract (question-map travels INSIDE the SVG)

Claude emits **one fenced ```` ```gamma-artifact <json> ```` ```` block only:**

```json
{ "kind":"diagram", "title":"Engine entry flow",
  "svg":"<svg viewBox=...><g data-node=\"heartbeat\" data-q=\"How does the heartbeat decide to enter?\" class=\"node\" style=\"--i:0\">...</g></svg>" }
```

- Every node carries `data-node="<stable_id>"` (join key for BUILD highlighting) + `data-q="<follow-up>"`. Embedding the question map IN the SVG = no second artifact to keep in sync, no node registry to drift.
- One delegated handler: `closest('[data-node]')` → `send(node.dataset.q)` → answer may itself be a new diagram (**recursive drill-down**; tries the free face first, $0).
- **Build-in-real-time feel:** nodes default `opacity:0` + `@keyframes nodeIn` staggered by `--i` → the diagram assembles itself.
- **SECURITY (load-bearing, two layers):** SVG from Claude is untrusted HTML.
  1. **Server-side** `lib/artifact.js#sanitizeSvg` (Node-built-ins-only, runs in the escalation pipeline *before* the artifact reaches `companion-ask-results.jsonl`): strip `<script>/<foreignObject>/<use>/<animate>`, all `on*` attributes, external/`xlink` `href`, CSS `url()`, cap ~60KB, reject on any parse anomaly → degrade to `{kind:'text'}`.
  2. **Client-side** render inside a **`<iframe sandbox>` (no `allow-scripts`)** so even a missed vector cannot execute in the cockpit's origin. *Hand-rolled SVG sanitization alone is a known-losing game; the sandbox is the real guard, the strip is defense-in-depth.* Never inject untrusted SVG into the main DOM. (Why this matters: the companion server can spawn a guarded-but-real Claude — an XSS here would be a full-chain pivot.)

##### Checkboxes / tasks (durable, auto-ticking — threaded id, not best-effort)

`lib/buildtasks.js` (sibling to `approvals.js`) owns `companion-build-tasks.json` (`builds:[{build_id,tasks:[{task_id,text,status,node?,ask_id?}]}]`) + append-only `companion-build-events.jsonl`. Served at `GET /api/build-tasks`, mutated at `POST /api/build-task`.

**Auto-tick requires threading an id end-to-end** (the draft's "exact id match only" silently fails because `face_brain.py` emits no `task_id` and the result record has none). The fix: the **free-face clarify loop mints `build_id`+`task_id`** when J confirms a build; the id rides through `face` → `logAsk` (`server.js:201`) → `runEscalation` → into the result record (extend the `appendResult` shape in `escalate.js:68-77` to carry `build_id/task_id`). On `ok`, `setTaskStatus(task_id,'done')` on **exact match**; no match → leave + log to `companion-build-events.jsonl` (fail-visible, OP-25). Without the id thread, BUILD mode is decorative — so the thread is in scope for Phase 4, not optional.

##### The pegboard

GridStack as **one vendored UMD file** in `public/vendor/` (no npm — honors the Node-built-ins-only invariant). Typed tile registry (`gamma`, `accounts`, `engine`, `kitchen`, `feed`, `approvals`, `diagram`, `builds`, `voice`) that **re-hydrates from `/api/state` every poll** — the poll updates each tile's *body* only, never grid geometry (geometry owned solely by GridStack + layout). Per-tile 🔒 lock; body re-render pauses on any tile mid-drag/resize. Layout persists to `localStorage` (zero-config) + optional `companion-layout.json` server mirror for a future Electron/phone shell.

##### Co-build loop (PICKED: the free face is the driver)

The **free face**, not Claude, runs clarify/propose and decides *when* to escalate. A new `clarify` face directive lets Gamma ask + render quick-reply chips (reusing the existing `.quick` chip pattern → `send(chipText)`) **before** spending a single Claude escalation:

> "Let's build X" → face emits `{reply, clarify:["chip 1","chip 2"], escalate:false}` → J taps a chip → *only then* the face emits `escalate`+`build_id`/`task_id`.

Keeps the conversational brain on the $0 ladder (J's #1 ask) and gates all Max-pool spend behind a confirmed spec (OP-3). Claude fires *once* per build, never per clarifying turn or drill-down click.

---

#### (3) Autonomy & Self-Modification

##### Proactive skill use — deterministic sweep, NOT the flaky model deciding to act

A cheap deterministic Python **obligation registry** detects gaps and fires the *specific read-only* skill; the free face only *narrates*. Letting a rate-limited free model autonomously fire skills is the same uncontrolled-action risk as letting it edit doctrine — refused.

- `automation/state/obligations.json` declares each: `{id:'premarket', expect_artifact:'automation/state/today-bias.json', fresh_within:'today 09:30', remediate_skill:'scout/premarket', tier:'flag'|'autofix'}`.
- `setup/scripts/obligation_sweep.py` + a `Gamma_ObligationSweep` scheduled task (every 15 min) reconciles each against **content-staleness** (not HTTP 200 — avoids the fail-green `heartbeat_pulse_check` bug) and `Get-ScheduledTask Gamma_*` state. Covers premarket / EOD / heartbeat-fresh / scheduled-tasks-healthy / watchers-fresh / gym-green.
- **Auto-remediation allowed ONLY for read-only skills:** `connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`. Anything re-running premarket/EOD writes or touching params/orders is **flag-only** → an Approve card. False-positive guard: calendar-aware, time-gated, one canonical id so re-emits dedupe (no "63 stale CRITICALs" spam).
- The face reads `companion-obligations.json`: *"Premarket didn't run — want me to fire Scout?"*

##### Reconcile with `derivedCards` (it already auto-manufactures Claude work)

**Honest correction to the draft's "conductor is the one auto-shipper" claim:** `state.js:64-110` ALREADY turns every RED engine-health check and a high failed-kitchen-count into a Sonnet `escalate` card *today*, independent of the conductor. The blueprint reconciles rather than ignores this:
- `derivedCards` are **read-only diagnosis escalations** — they explicitly instruct "do NOT place trades or edit params/heartbeat" (verified at `state.js:80,102`). Keep them, but they now flow through the SAME `runEscalation` chokepoint → inflight cap + denylist + activity log.
- **Dedupe by stable id** (`act-<check.name>`, already stable at `state.js:89,96`) so the 5s poll cannot enqueue the same RED check twice — this de-dupe moves to **Phase 1**, not Phase 6, because the poll re-derives every 5s.
- Document the overlap with the conductor STAGE pipeline so the two don't both diagnose the same RED check.

##### The SAFE soul-file self-editing protocol

**The single largest unmitigated risk, confirmed in source:** `escalate.js:45` runs `permissionMode:"bypassPermissions"` with `cwd=root`, **no `canUseTool`, no denylist, no clock** — and `runEscalation` is reachable from BOTH `/api/chat` (line 202) AND the **unauthenticated** `/api/approve` (line 232), which fires an arbitrary `action.task` string straight off the request body. A flaky/injected free model — or any local web page (§4) — can drive a bypass-Claude to rewrite `CLAUDE.md`, flip `params.json`, or place an order. **The conductor's rail-4 prose cannot stop it; the SDK never reads prose as a contract.** Graduate the rails from prose into CODE. **This is P0.**

**`gamma-companion/lib/guard.js` (NEW) — built INSIDE `runEscalation`, not passed by callers** (so no future endpoint can spawn an unguarded escalation; add a test that greps for any `query(` lacking the guard):

1. **Denylist at the SDK `canUseTool` boundary** (passed into `query({options:{canUseTool}})`), so it holds *even under `bypassPermissions`*:
   - Deny `Write`/`Edit` on: `CLAUDE.md`, `automation/state/params*.json`, `automation/state/aggressive/params.json`, `automation/prompts/heartbeat*.md`, `backtest/lib/filters.py`, `**/*.key`.
   - Deny every `mcp__alpaca__place_*/cancel_*/close_*/replace_*` + the `alpaca_aggressive` equivalents. **The companion is a face + builder, never a trader.**
2. **Two-tier authority — absolute, no third path** (mirrors `conductor.md` STAGE 4, one rule for both the after-hours conductor and the interactive face):
   - **Authoring tier** (writes only under `crypto/validators/`, `strategy/candidates/`, `markdown/`, `analysis/`, `_*-inbox/`) → may auto-apply headless **after passing gym/pytest backpressure**, AND only if **`origin !== 'voice'`** (§4).
   - **Doctrine / params tier** → propose-only. Intercepted *before* the SDK write happens.

**The CLAUDE.md edit flow — capability-based, not prose-based:**
1. The escalated Claude has **no write access to any doctrine path** (denylist). It returns the proposed new text **as its result string only.**
2. **`guard.js`/server** (not the model) writes the shadow file `markdown/_soul-proposals/{id}.md` and computes the unified diff to `automation/state/soul-diffs/{id}.diff`. *(This kills the draft's "Claude writes the shadow file but promises not to touch CLAUDE.md" theater — under bypass it COULD touch CLAUDE.md, so the only real stop is the denylist + the model never having the capability.)*
3. Server enqueues an approval card rendering the diff; mirrored to `conductor-proposals.jsonl` + `discord-outbox.jsonl` under one `proposal_id` (one id, one decision, three views).
4. On **J Approve** (cockpit tap *or* Discord 👍): `git tag soul-pre-{id}` → patch → `git commit "doctrine: {title} (companion-approved {id})"`.
5. **Undo** = one-click card → `git revert` of that commit.

**Immutable anchors — guard on CONTENT-HASH of the RESULT, never on diff line-ranges.** *(The draft's "anchored line-ranges" is exactly the L21/L42 anchor-to-position foot-gun — a self-editing file's line numbers move every commit; an inserted line above the 10 rules false-passes or false-blocks everything downstream.)* The fix: hash the canonical text of each immutable block (the 10 rules, the per-account kill-switch numbers, the FORBIDDEN-FRAMING clause) at a known commit. After any proposed apply, **verify the RESULT still contains each block verbatim (hash unchanged); if any hash changed, refuse to create the card at all.** Verify the *result*, not the *diff*. A `backtest/tests/` assertion asserts the post-apply file still contains each immutable block verbatim (graduated guard, OP-25).

**Voice is ALWAYS propose-only, regardless of tier.** Tag every escalation `origin:'voice'|'text'|'click'` end-to-end (set at the `/api/chat` boundary). `guard.js` forces a card for any `origin==='voice'` — even authoring-tier. *(Why: J's audio → lossy GPT ASR → rate-limited free face → `task` string is a live injection path; an ASR slip ("shelve it"→"ship it") or a hostile string echoed from a state field must never auto-apply writes or burn the Max pool on a gym run.)* Typed/click escalations may auto-apply authoring; voice may not.

**Preserved guards:**
- **Rule 9 (no mid-session doctrine changes):** `guard.js` market-clock blocks the *apply* of any doctrine/soul edit during 09:30–15:55 ET. Blocks the EDIT, never J's session (fail-open, OP-32 scar).
- **L54 starvation:** during RTH, **defer ALL Claude escalations (every tier, not just Opus/long-Sonnet)** to `queue.md` for the after-hours conductor; only the $0 free face stays live. Voice says *"queued for after the close."* *(The draft deferred only Opus + "long Sonnet" — ordinary Sonnet authoring escalations still shared the Max pool with the live heartbeat, the precise documented scar. All tiers defer.)*
- **FORBIDDEN-FRAMING vs ship-if-profitable — the explicit line:** ship-if-profitable governs the **engine/authoring** surface (validators, candidates, params *changes the conductor ratifies through its own gate*). The **`CLAUDE.md` soul surface stays propose-only** — even under bypass, even spoken by voice — because ASR/injection could otherwise rewrite the reward function. Idempotency: dedupe cards by content-hash of `(task,target_path)`.

**Authoring auto-apply gets the SAME rollback as doctrine.** Every headless authoring auto-apply commits **on its own tag** (`git tag author-pre-{id}` → commit) with a one-click revert card. *(A broken validator that auto-applies + auto-ratifies through the gym is exactly the silent-drift the autonomy audit flagged — it must be one revert away, same as doctrine.)*

**The free model's hard ceiling:** read state + chat + *propose* escalations. Never directly applies; high-tier and all voice proposals require human approval; per-session rate cap (≤1 doctrine proposal / 10 min). Prompt-injection defense holds because **the guard sits AFTER the model, on the action** — injection can't bypass the denylist, the auth, or the approval requirement.

---

#### (4) Guardrails & Cost

##### The safety envelope — six rails, graduated to code

1. **Authenticated server.** *(The guard alone does NOT close the network hole — `server.js:306` binds `127.0.0.1` but has zero auth/CSRF/Origin check, so any local web page can `fetch` `/api/approve` and drive a bypass-Claude.)* Generate a per-session **bearer token at boot**, inject it into the served `index.html`, require it on **every `/api/*` POST**, AND enforce an **`Origin`/`Host` allowlist** (`localhost`/`127.0.0.1:4317` only). This is **Phase 1**, not later.
2. **Companion = read + bus-write only**, enforced by `guard.js#canUseTool` (not prose). No `params*.json`/`heartbeat*.md`/`filters.py`/`CLAUDE.md` direct write; no Alpaca order tool — ever. **The `order` action type is deleted entirely** — it contradicted the non-negotiable and required *something* to execute the order.
3. **One global kill-switch.** A `companion-halt.flag` file checked at the top of `runEscalation` AND `/api/realtime-token`: present → refuse all spend, serve read-only. *(OP-25: J holds the off-switch. If the free face retry-storms or the guard has a bug, J needs one switch.)*
4. **Concurrency + $-cap, enforced not logged.** A hard **inflight semaphore (≤2 concurrent escalations)** + a **daily count/$-cap read from `gamma-activity.jsonl` checked *before* spawn**, refusing with a logged `STATUS.md ## Known broken` flag on breach. *(The SDK `result` message carries cost — `escalate.js:49-53` already reads `message` — so wire cost accounting onto it. Without this, voice barge-in + retries + 3 derived RED cards re-fanning every 5s poll = a Max-pool fan-out bomb.)* Derived cards de-dupe by stable id (§3).
5. **Fail-open, always.** SSE/watchFile, the obligation sweep, the market guard, the halt flag — none may block J's interactive session, the dev server (:3000), or any heartbeat tick (OP-32/OP-25).
6. **No silent failure (OP-25).** Every denied escalation, deferred tier, obligation gap, and approval writes a `gamma-activity.jsonl` row + surfaces to engine-health reds / `STATUS.md`. Engine-code edits run `pytest backtest/tests/` + the gym in the same fire and refuse `ok=true` on red (reusing conductor STAGE-3 backpressure + the OP-11/OP-16 gate).

##### Cost — model routing as a single chokepoint

Extend `MODEL_MAP` (today only `{opus, sonnet}` at `escalate.js:17`) with **`haiku:"claude-haiku-4-5"`** and add `routePolicy()` in `escalate.js`:

| Tier | Work | Engine | Cost |
|---|---|---|---|
| 0 | status, Q&A, clarify, drill-down first-pass | free face ladder (Nemotron→DeepSeek→MiniMax) | **$0** |
| 1 | rote read / tabulate / log-lookup | **Haiku** | low |
| 2 | **diagnose / graded fix** (incl. `state.js` derived cards) | **Sonnet** *(leave `state.js:77,95` at Sonnet — these ARE tier-2 diagnosis; the draft's "downgrade to Haiku" would degrade root-cause quality)* | mid |
| 3 | hard reasoning / doctrine drafts | Opus, **RTH-deferred** | high, after-hours only |

- **Voice:** free face = $0; `gpt-realtime-2` bills J's OpenAI key only while a session is active. **Server-enforced idle auto-stop** (server tracks last-activity per session, revokes the client secret / refuses token refresh past a hard daily cap) — *not* client-side, so a stuck-open mic tab can't bill forever. Every session → `companion-voice-usage.jsonl`; live voice-spend tile on `/api/state`.
- **Fast voice path:** thread a `voice/fast` flag → `face_brain.py` uses only `deepseek-v4-flash:free`, ~200 tokens, ~12s timeout (vs the 90s typed timeout at `server.js:115`); spoken filler ("one sec, pulling that up") before the tool call.
- **Companion-escalation $-cap** extends `run_minimax.py`'s `DAILY_CAP_USD` pattern with a `STATUS.md` BROKEN flag on breach. Kitchen's $3/day, voice's OpenAI meter, and companion escalations all stay observable inside the OP-3 $100/mo envelope.

---

#### (5) Phased build roadmap — priority order, each shippable

> **Phase 1 is non-negotiably the closed, authenticated, capped guard.** The unguarded `bypassPermissions` (`escalate.js:45`) reachable from the unauthenticated `/api/approve` (`server.js:232`) is the one genuinely dangerous flaw. Everything downstream builds on a closed hole.

**PHASE 1 — Close + authenticate + cap the chokepoint (the precondition).**
`lib/guard.js` built INSIDE `runEscalation` (DENYLIST + `classifyTask` + `canUseTool` + market clock + `origin` gate); default-deny for non-authoring/non-readonly; Alpaca order tools blocked. **Bearer token + Origin allowlist on every `/api/*` POST.** **`companion-halt.flag`** checked in `runEscalation` + `/api/realtime-token`. **Inflight semaphore (≤2) + daily $-cap** read from `gamma-activity.jsonl` before spawn. **Derived-card stable-id de-dupe** (`state.js`). Delete any path toward an `order` action type. `routePolicy()` + `MODEL_MAP.haiku` (leave `state.js` diagnosis at Sonnet). `gamma-activity.jsonl` spine + `logActivity()` from `escalate.js`/`approvals.js`/`run_minimax.py`. A `smoke-sdk.js`-style test proving an "edit CLAUDE.md" escalation is refused at the SDK boundary AND a greppable assertion that no `query(` lacks the guard.

**PHASE 2 — Make it sound like Gamma + feel instant (the voice).**
`automation/presence/GAMMA-VOICE.md` (on `SOUL.md`) loaded by both `face_brain.py` (SYSTEM, replacing line 46) and `/api/realtime-token` (replacing the inline string at line 251) + the mouth-only rule; three-tier boundary encoded; `voice/fast` flag → fast path; **server-enforced** idle auto-stop + `POST /api/voice-event` → `companion-voice-usage.jsonl`; voice-spend tile. RTH-mode banner. Verify by voice: "what's our P&L" returns the exact `/api/state` number.

**PHASE 3 — Live diagrams + clickable pegboard (the cockpit).**
`lib/artifact.js` (`parseArtifact` + `sanitizeSvg`) in the escalation pipeline; **sandboxed-iframe render** in `app.js`; `setMode()` + `renderDiagram()` + FOCUS layout; `data-node/data-q` delegation → recursive drill-down (free-face first); staggered node fade-in; GridStack vendored UMD + typed tile registry + `localStorage`/`/api/layout`; co-build `clarify` chips on the free face.

**PHASE 4 — Build-task store + control-plane wiring (the loop closes).**
`lib/buildtasks.js` + `/api/build-tasks` + `/api/build-task` + BUILD-mode checklist; **`build_id`/`task_id` minted by the clarify loop and threaded `face`→`logAsk`→`runEscalation`→result** so auto-tick actually fires; NEW `/api/approve` branches for `soul-edit` (escorted by the §3 flow) — **no `order` branch ever**; `lib/enqueue.js` bridge (RTH escalations hand work to the after-hours conductor — no double-apply); engine producers write real items into `companion-approvals.json`; Discord 👍/👎 reused as the one approval transport.

**PHASE 5 — Obligations awareness + safe self-modification (the autonomy).**
`obligations.json` + `obligation_sweep.py` + `Gamma_ObligationSweep`; RED obligation cards + read-only auto-remediation; the full soul-edit pipeline (server writes shadow → `soul-diffs/{id}.diff` → card/Discord → `git tag` snapshot+commit → one-click Undo); **content-hash immutable-section verification on the RESULT**; authoring auto-apply gets its own `author-pre-{id}` tag + revert card.

**PHASE 6 — Hardening + drift visibility.**
Per-session escalation rate caps; idempotent approval dedupe by content-hash; weekly `CLAUDE.md` cumulative-drift report; injection-token flagging in the sweep; graduated `backtest/tests/` assertions (denylist holds + immutable blocks present verbatim + no unguarded `query(`); refresh `markdown/specs/ARCHITECTURE.md` (STALE) with the companion bus contracts.

---

#### (6) Open questions for J — only what truly needs you

1. **Authoring-tier authority during the day, for TYPED/CLICK builds.** Voice is *always* propose-only. For typed/click builds while you're watching: auto-apply read-only/authoring under the gym gate, or require a tap during RTH? *(Recommended: auto-apply read-only/author for typed/click; voice always taps.)*

2. **FORBIDDEN-FRAMING / ship-if-profitable on the soul surface.** Line drawn: ship-if-profitable governs the **engine/authoring** surface; **`CLAUDE.md` stays propose-only** (DRAFT → your 👍), even under bypass, even spoken — because ASR/injection could rewrite the reward function. Confirm.

3. **Immutable anchors: hard or soft?** The 10 rules / kill-switch numbers / FORBIDDEN-FRAMING — **un-touchable via the companion at all** (no card can ever be created — hardest), or **card-created-but-DANGER-flagged with double-confirm**? *(Recommended: hard.)*

4. **Voice cost ceiling + RTH policy.** A hard daily $-cap on the OpenAI realtime key (server auto-mutes past it)? And during 09:30–15:55 ET: free voice CHAT ($0) stays live (only Claude escalations defer), or whole companion muted to protect heartbeat focus? *(Recommended: free chat stays live; all Claude escalations defer.)*

5. **Obligation auto-fix scope.** Confirm: auto-fire read-only (`connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`); flag-only for anything re-running premarket/EOD writes or touching params/orders.

---

#### Build order — start here

The next 3–5 things to build, in order. Each is independently shippable and leaves the system safer than it found it. **Do not start #2 until #1 lands** — every other feature is downstream of a closed hole.

1. **Guard the chokepoint — `gamma-companion/lib/guard.js` built INSIDE `runEscalation`.**
   Touches `gamma-companion/lib/escalate.js` (wrap the `query({options})` at lines 41-48 with `canUseTool`; extend `MODEL_MAP` line 17 with `haiku`). Denylist: `Write`/`Edit` on `CLAUDE.md`, `automation/state/params*.json`, `automation/state/aggressive/params.json`, `automation/prompts/heartbeat*.md`, `backtest/lib/filters.py`, `**/*.key`; deny all `mcp__alpaca__place_*/cancel_*/close_*/replace_*` + `alpaca_aggressive` twins. Ship with `gamma-companion/smoke-sdk.js`-style test proving an "edit CLAUDE.md" task is refused at the SDK boundary. **Independently shippable: hardens the existing escalation path with zero new surface.**

2. **Authenticate the server + add the kill-switch + concurrency/$-cap.**
   Touches `gamma-companion/server.js` (bearer token generated at boot, injected into served `index.html`, checked on every `/api/*` POST at lines 186/216/239; `Origin`/`Host` allowlist) and `runEscalation` (check `automation/state/companion-halt.flag` + inflight semaphore ≤2 + daily $-cap from a new `automation/state/gamma-activity.jsonl` before spawn). Also: **delete any route toward an `order` action type** and **de-dupe `derivedCards` by stable id** in `gamma-companion/lib/state.js:64-110`. **Independently shippable: closes the network hole the guard alone leaves open.**

3. **Unify the activity spine — `gamma-activity.jsonl` + `logActivity()`.**
   Touches `gamma-companion/lib/escalate.js`, `gamma-companion/lib/approvals.js`, and `setup/scripts/run_minimax.py` — each emits one row (`{ts,source,origin,tier,model,cost_usd,inflight,action,outcome}`) on every escalation/approval/face-call. This is the meter the $-cap in #2 reads and the feed the cockpit tails (via `fs.watchFile` stat-poll, **not** `fs.watch` — unreliable on Windows; default to piggybacking the existing 5s `/api/state` poll). **Independently shippable: pure observability, no behavior change.**

4. **One shared voice — `automation/presence/GAMMA-VOICE.md`.**
   Built on the verified-existing `automation/presence/SOUL.md`. Loaded by `gamma-companion/face/face_brain.py` (replace the `SYSTEM` string at line 46) and `gamma-companion/server.js#/api/realtime-token` (replace the inline `instructions` at lines 251-252 with its head + the mouth-only rule). Tag `origin:'voice'|'text'|'click'` at the `/api/chat` boundary so the guard from #1 can force voice → propose-only. **Independently shippable: makes it sound like Gamma and wires the origin tag the guard needs.**

5. **Server-enforced voice meter — idle auto-stop + daily cap.**
   Touches `gamma-companion/server.js#/api/realtime-token` (track last-activity per session, refuse token refresh past a hard daily cap read from a new `automation/state/companion-voice-usage.jsonl`) + a `POST /api/voice-event` endpoint + a voice-spend tile on `/api/state`. **Independently shippable: caps the one cost that bills J's personal OpenAI key directly.**

---

#### Open questions for J

Only the decisions that genuinely need you — everything else is specified above.

1. **Daytime authoring auto-apply for typed/click builds.** Voice is always propose-only. For typed/click authoring builds during 09:30–15:55 ET while you watch: auto-apply under the gym gate, or require a tap? *(Recommended: auto-apply read-only/author for typed/click; voice always taps.)*

2. **Soul-surface line.** Confirm: ship-if-profitable governs engine/authoring; **`CLAUDE.md` stays propose-only** (DRAFT → your 👍), even under bypass, even spoken — because ASR/injection could rewrite the reward function.

3. **Immutable anchors — hard or soft?** 10 rules / kill-switch numbers / FORBIDDEN-FRAMING: no card can EVER be created for them (hardest), or card-with-double-confirm? *(Recommended: hard.)*

4. **Voice $-cap + RTH policy.** Hard daily cap on the OpenAI realtime key with server auto-mute? And during market hours: free voice chat stays live (only Claude escalations defer), or whole companion muted? *(Recommended: free chat live; all Claude escalations defer.)*

5. **Obligation auto-fix scope.** Confirm: auto-fire read-only skills (`connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`); flag-only for anything that re-runs premarket/EOD writes or touches params/orders.

---

### 2026-06-18 — Gamma Autonomy & Architecture Blueprint (superseded)

**Gamma Autonomy & Architecture Blueprint — 2026-06-18**

> Commissioned by J: "extensive audit… can we use Claude better… Gamma needs to be DRIVING this… engine not able to perform throughout the day… get 0DTE going… brainstorm extensively, look online for valid inspiration." Six parallel audit+research agents (3 internal, 3 external). This is the synthesis.

---

#### TL;DR — one diagnosis, one move

**The architecture is RIGHT. The wiring is the problem.** Gamma is already an orchestrator-worker system (the exact pattern Anthropic recommends), trading a sound 6-setup strategy. But ~100+ components (28 watchers, 88 validators, ~34 tasks, prose prompts, ~560 state files) are wired by **string-matching, convention, and English prose with ZERO enforced contracts** — so every seam can break silently and only at runtime. That's why the engine couldn't see 26 of its own 28 watchers; why gates ship "in prose but not applied"; why a field-name typo silently drops every decision. **A single human in a chat window cannot hold 100+ un-contracted seams in his head — and isn't supposed to.**

**The one move, repeated everywhere: convert prose/convention into CODE ASSERTIONS at boundaries.** Contracts at every file read, a registry that fails if a component is orphaned, a drift test that kills manual sync, a risk gate every order must pass, a real-time health beacon. Then: **turn Gamma from a chat-responder into an actual conductor** (the wake-protocol that's written but never fires) using **model routing** (Opus to reason, Haiku for rote) and **Discord as the async approve/revoke bus** — so J approves rather than operates.

Every external source (Anthropic's own agent guidance, the Ralph-loop autonomy canon, NautilusTrader/LEAN/Freqtrade, the contract-testing literature, the 0DTE options literature) independently lands on these same moves. And most of them, Gamma already learned as prose lessons (C2, C7, C9, C14, C27, OP-22) — **the failure is that lessons-as-prose get re-violated; they must be graduated to assertions the build enforces.**

---

#### Part 1 — The Diagnosis (why it keeps breaking)

**It is BOTH over-engineered AND under-structured, and the two reinforce each other.** ~290K LOC across 3,411 files for a job whose essence (trade SPY 0DTE on ~6 setups across 2 accounts) needs maybe 3,000. The complexity isn't in the trading — it's in 5 parallel meta-systems (research, validation, journaling, observability, autonomy), each justified alone, together 5× the surface area of the thing they serve.

**The 7 structural problems (ranked by error-risk):**

1. **The params ↔ prompt ↔ filters drift triangle (root cause).** The same rule values live in THREE incompatible forms with no enforced equality: `params.json` (JSON, "canonical," 181 keys / 29 prose essays), `heartbeat.md` (the LIVE engine — 751 lines of English an LLM re-derives every 3 min), and `filters.py` (the BACKTEST engine — 1,387 lines that load params.json **zero** times; every threshold hardcoded). "Does the backtest match what trades live?" is enforced only by a once-daily text pin-check + a manual `gamma-sync` skill. params.json line 62 literally documents the rot: a ratified gate marked "heartbeat.md activation pending."

2. **Coupling-by-string everywhere, no contracts.** 25+ `setup_name` literals must match action strings the heartbeat parses; the watcher→ledger link is schema-by-convention (needs a runtime "schema guard" for malformed rows); STATUS.md "Known broken" lists producer/consumer mismatches by name. Consumers silently see a subset (often zero) of what producers emit.

3. **State-file proliferation = ambiguous source of truth.** 5 files claim to be "the position"; 6 decisions ledgers; 144 `.lastgood` mirrors that can themselves go stale; a corrupted queue the daemon half-read (834 of 2,751 tasks).

4. **Append-only producers, no consolidation.** 520+ candidate files (mostly free-tier brainstorm noise), 63 stale CRITICALs in queue.md that nothing drains — the "accumulate, don't compound" failure OP-22 explicitly warns against, happening live.

5. **Dead/zombie code carried as live.** SNIPER (retired) still imported + ~30 scripts + a task; pinfade flag-disabled but in-tree; 4 stale prompt forks beside the live heartbeat; retired param overlays.

6. **Single points of failure the whole day rides on.** TradingView/CDP:9222 (one eye; a frozen-but-200 chart passes the watchdog); the shared Max rate-limit pool (no isolation — the dead `.heartbeat-api-key` code still claims protection that doesn't exist; **human discipline is the only guard**); the rolling CSV built at 14:00 ET (which blinded the entire watcher fleet all morning today); the EOD-flatten (the one task whose failure = real money via ITM assignment) depends on the same fragile LLM pool.

7. **No real-time health signal.** There is no `engine-health.json`. Degradation surfaces only at EOD or when J notices. `heartbeat_pulse_check` scores a total outage as PASS (an outage looks like a weekend). The staleness watchdog is itself orphaned and stale.

**The autonomy gap:** Gamma can already **execute, validate, report** — but cannot autonomously **decide-what-to-do-next** and **fan-out-then-ship**. The conductor logic exists (`wake-protocol.md`, a complete orchestrator spec) but is bound to a **dead cloud cron and never fires on this machine**. So when J opens a chat, J becomes the conductor — exactly his complaint.

**The Claude-efficiency gap:** all 10 agents are pinned to `model: sonnet`. **Zero Opus, zero Haiku routing.** Today: $31.82, 100% Sonnet, 58M cache-read tokens. The hardest cognitive work (strategy synthesis) runs on the WEAKEST model (free Nemotron in the Kitchen); rote read-and-tabulate work burns Sonnet. Under the new $200 plan the bottleneck was never budget — it's that **spend isn't tiered**.

---

#### Part 2 — The Operating Model: "Gamma Drives" (the answer to "use Claude better")

**Today's pattern:** J opens a chat → J is the conductor → agents fan out on demand → J reviews in chat. One giant Sonnet session, J on the critical path for everything.

**The better pattern — four wires, not a rebuild:**

1. **Fire the conductor.** Register a `Gamma_Conductor` Windows task (after-hours cadence, e.g. hourly 16:00–08:00 ET — matching this machine's all-Task-Scheduler convention, replacing the dead cloud cron). It runs the EXISTING `wake-protocol.md` logic on **Opus**: read the prioritized queue → pick the top item → **fan out the right specialist personas IN PARALLEL** (Chef + validator-author + a backtest agent, via the Agent tool / a saved Workflow) → validate with backpressure (gym/pytest) → ship-if-gate-passes / else flag to J → update STATUS + queue + Discord. This turns 10 well-built personas into an actual firm. *The logic is already written — it just needs a trigger.*

2. **Route models by difficulty.** `model: haiku` for rote personas (scout/analyst/manager/coach/treasurer + the OP-29 authors — read/tabulate/file-write); `model: opus` for the conductor + Chef's strategy synthesis (genuinely hard reasoning); keep heartbeat on Sonnet (latency + judgment). Cache the CLAUDE.md/params prefix (90% discount on re-reads). Net cost ≈ flat, capability up sharply. On a Max plan the scarce resource is **rate-limit headroom**, so the conductor MUST be after-hours only (L54 — never starve the heartbeat) and fail-open (the OP-32 scar — never lock J out).

3. **Discord = the async approve/revoke bus.** The two-way responder is BUILT but disabled (`discord-responder.py`, `Gamma_DiscordResponder` "never enabled"). Enable it (Haiku, after-hours-gated). Protocol: Gamma pings a decision in SOUL voice — *"Cooked a winner: OOS +$840, WF 1.4, real-fills +, anchor-clean, scorecard filed. Ship? 👍/👎"* — J reacts from his phone; 👍 ships, 👎 shelves, silence-after-timeout = hold. **J becomes APPROVER, not driver.** Wire the auto-ship path so validated wins ship on Gamma's authority with J holding only REVOKE (the doctrine OP-22 already states but never plumbed — kitchen auto-promote dead-ends at a J-gated `_LEADERBOARD-pending.md`).

4. **Use Workflows for structured fan-out.** The nightly research/audit/fix loop should be a **saved, rerunnable Workflow** (self-caps at 16 concurrent / 1000 total agents, adversarial cross-review built in) — not hand-rolled chat orchestration. Anthropic's own `/deep-research` workflow is the template (votes on each claim, filters out what doesn't survive cross-checking).

**Net:** J's chat sessions become STEERING (set direction, ratify big calls) instead of OPERATING (fixing bugs one at a time). That is the whole ask.

**Architecture discipline from Anthropic (keep this line bright):** keep the **trade-execution path a deterministic WORKFLOW** (mechanical rules, single-threaded — "most coding is high-dependency → single agent"); make only the **R&D/research layer AGENTIC** (model-driven flexibility where it pays). Don't run the live trade loop as a fan-out; don't run research as a rigid script.

---

#### Part 3 — The Technical North Star (the answer to "stop the errors")

The meta-fix, applied everywhere: **graduate prose/convention into code assertions at boundaries.** Specifics, leverage-ranked:

1. **Contracts at every state-file read (Pydantic / JSON Schema).** One model per state file, in one place, imported by BOTH producer and consumer. `ScoutOutput.model_validate(...)` instead of `json.load(...)`. The moment a producer drops a field a consumer needs, the consumer throws a typed error AT READ TIME instead of silently seeing `None`. *This single change kills the entire producer/consumer-silent-break class — the exact bug we've hand-fixed for three nights.* (Source: Fowler consumer-driven contracts; "parse don't validate"; Pydantic boundary validation.)

2. **A registry that makes orphaning impossible.** `@register_watcher` decorator → module-level `WATCHER_REGISTRY`; the heartbeat iterates the registry (no separate list to forget). Plus a **reconciliation test**: `set(files in watchers/) == set(registry) == set(heartbeat consumes)` — fails CI if any drift. *One test would have caught all 26 invisible watchers on the first run.* Apply identically to the 88 validators and ~34 tasks (reconcile `Get-ScheduledTask Gamma_*` vs `SCHEDULED-TASKS.md`). (Source: Python entry-points/registry pattern; "prevents silent orphaning.")

3. **A real-time health beacon (turn fail-green into fail-loud).** One `engine-health.json`, updated every tick + by a cheap 1-min Python watchdog, fusing: both-account last-fire age, TV chart freshness (CONTENT staleness, not just HTTP 200), both Alpaca auths, **watcher feed produced rows FOR TODAY** (distinguish "producer dark" from "no signal"), kill-switch state, rate-limit headroom. RED → Discord ping mid-day. *Would have caught today's all-day watcher blindness at 09:35 instead of at the post-mortem.* The fail-loud reference pattern already exists in-repo (`swarm_health.py`).

4. **A mandatory RiskGate every order passes through.** One `RiskGate.check(order) → Allow | Deny(reason)` the execution path CANNOT skip: daily-loss kill switch, per-trade cap, min-3-contracts, PDT, "already stopped out on this setup today," "is account flat as expected." **Fails CLOSED on any unreadable input; never locks out J (fails open for the human).** Today the kill switch lives in prose the heartbeat is *asked* to honor — which SEC 15c3-5 enforcement explicitly calls insufficient ("humans monitoring risk systems are not sufficient; order stops must be triggered automatically"). (Source: NautilusTrader RiskEngine; LEAN Risk module; SEC Market Access Rule.)

5. **Drift-detection test kills manual `gamma-sync`.** A pytest that loads `params.json` and asserts `filters.py` constants + prompt constants match — failing CI on divergence. Better: **generate** the derived copies from `params.json` (codegen) so they CAN'T diverge. The manual sync ritual IS the drift vector. (Source: config-drift literature; the v25 presence-guard we shipped this week is the first instance of this — generalize it.)

6. **Compile the decision core out of the prose (the deep fix).** The 21 filters + Gates A–I + sequence + sizing currently live as English the LLM re-derives every tick (non-deterministic; two ticks can disagree; gates ship in prose but mis-applied). Move deterministic gate evaluation into ONE Python module that BOTH the live tick and the backtest call. The LLM then does only judgment (chart read, trigger recognition) and calls the gate function for the verdict. This makes backtest=live parity STRUCTURAL, not a nightly hunt. (Source: NautilusTrader "same source code for backtest and live"; this finishes what `gamma-sync` started.)

7. **Detector → Insight registry (collapse the 28 watchers).** Each detector emits a uniform `Insight{direction, confidence, triggering_level, as_of_ts}` into a registry, merged by a composite (à la LEAN's CompositeAlphaModel). A detector that emits nothing does so VISIBLY. (Source: LEAN/Freqtrade/NautilusTrader plugin patterns.)

---

#### Part 4 — The Trading Fixes (the answer to "make it actually trade 0DTE")

1. **Chart/underlying-level stops as DEFAULT; demote fixed-% premium stops to a catastrophe cap.** This is the single highest-leverage TRADING change, and it's triple-corroborated: the options literature (theta + vega + gamma corrupt a fixed premium stop on 0DTE — "a steady drip can trigger a stop on a trade that's just consolidating"), Gamma's OWN lessons (C2 "chart-stop only, premium-stop disabled"; C3 "SPY-price edge ≠ option edge / stop-misfire"), AND the `missed_week` backtest ("right direction, chopped by premium stops"). Yet v15 STILL uses fixed-% premium stops (−8%/−20%). *This is a Rule-9 doctrine change — needs J's nod — but the evidence is overwhelming.*

2. **Promotion rigor for the multiple-testing regime.** The Kitchen generates MANY candidates → an undeflated Sharpe/WR is "statistically meaningless" (Bailey & López de Prado). Add to the live gate: **Deflated Sharpe Ratio**, **Probability of Backtest Overfitting**, **Combinatorial Purged Cross-Validation** (not single-path walk-forward), **paper-vs-backtest divergence**, and a **system-restart stress test** during the paper window. (Caveat: the 7-trade J-anchor set is a known statistical-power ceiling — CPCV won't fix that; treat anchors as exceptional one-offs per C24.)

3. **Broker-as-source-of-truth reconciliation at the top of every tick** + `client_order_id` idempotency + broker-side OCO brackets (survive a process crash). Solves "is my position what I think it is" without a human watching. (Source: NautilusTrader live reconciliation.)

---

#### Part 5 — The Phased Roadmap (what to do, in order)

**Phase 0 — Make failures loud + safe (reliability foundation). Start here.**
- (0a) **Engine health beacon** → Discord. *Additive, low-risk, makes every future bug visible.*
- (0b) **Contract + registry + drift tests** (Pydantic at reads; watcher/validator/task reconciliation; gamma-sync→failing test). *Additive tests; structurally ends the silent-drift class.*
- (0c) **Mandatory RiskGate** (fails closed, never locks J out). *Touches execution — needs care + J awareness.*

**Phase 1 — Make Gamma drive (autonomy).**
- (1a) **Fire `Gamma_Conductor`** (after-hours, Opus, fans out personas, drains one owned queue).
- (1b) **Model routing** (Haiku rote / Opus reason / Sonnet heartbeat) + prefix caching.
- (1c) **Discord approve/revoke bus** (enable the built responder; structured 👍/👎).

**Phase 2 — Make the engine trade well (the product).**
- (2a) **Chart-stops default** (Rule-9 — J ratifies).
- (2b) **Detector→Insight registry** + one shared decision library (backtest=live parity).
- (2c) **Promotion rigor** (DSR/PBO/CPCV/paper-divergence).

**Phase 3 — Reduce surface area (sustainability).**
- (3a) **Aggressive deletion** of what the new tests prove nothing consumes (SNIPER, pinfade, 4 prompt forks, 520-candidate pile, dead tasks); archive dated one-shot docs; collapse the 5 position files.

**Sequencing logic:** Phase 0 makes the rest SAFE to do autonomously (you can't let a conductor auto-ship until failures are loud and contracts are enforced). Phase 1 makes Gamma the driver. Phase 2 is the actual money. Phase 3 keeps it maintainable so it doesn't regrow the sprawl.

---

#### Part 6 — External Inspiration (validated, credited)

**Claude / multi-agent (highest trust — Anthropic official):**
- [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) — the 5 patterns; workflow-vs-agent; "add agents only when simpler solutions fall short."
- [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — orchestrator-worker; evals/tracing/checkpoints; when multi-agent is NOT worth it ("most coding is high-dependency").
- [Claude Code Workflows](https://code.claude.com/docs/en/workflows) / [Subagents SDK](https://code.claude.com/docs/en/agent-sdk/subagents) / [Agent Teams](https://code.claude.com/docs/en/agent-teams) — the orchestration primitives + per-subagent `model` routing + adversarial-review gates.
- Ralph-loop autonomy pattern (Huntley/Cherny) — fresh context per fire, one bounded task, external memory, backpressure; **"drift has no auto-detection"** is the key warning.
- Repos (stars/credibility flagged): [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (22k★, per-task model routing — direct analog to our personas); [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) (60k★ — mine for ideas, broad/marketing-heavy, don't adopt wholesale).

**Trading architecture (production OSS + regulatory + peer-reviewed):**
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) (~24k★, active) — backtest=live by construction; RiskEngine every order passes through; broker-as-truth reconciliation. **The single best architectural model for us.**
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean) (16k★+) — the 5-stage decoupled pipeline (Alpha→Portfolio→**Risk**→Execution); CompositeAlphaModel (the watcher-registry pattern).
- [Freqtrade](https://www.freqtrade.io/en/stable/strategy-customization/) (~40k★) — the `IStrategy` plugin/registry contract.
- SEC Rule 15c3-5 (Market Access Rule) — automated risk controls are mandatory; human monitoring is "not sufficient."
- Bailey & López de Prado — [Deflated Sharpe](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551), [Prob. of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) — the rigor for our multiple-testing regime.
- CBOE 0DTE research + options-stop literature — chart-stops over premium-stops on 0DTE.

**Complexity-taming (recognized engineering authorities):**
- [Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html); Pact; "parse don't validate"; Confluent schema-evolution — the contract layer.
- [Out of the Tar Pit](https://curtclifton.net/papers/MoseleyMarks06a.pdf) (essential vs accidental complexity); Ousterhout "deep modules" (a real tension with our "many small files" rule — flagged); [Addy Osmani — LLM coding workflow 2026](https://addyosmani.com/blog/ai-coding-workflow/) (tests as the rails that keep an LLM-extended codebase coherent).

---

#### The one-sentence north star

**Stop describing invariants in prose and start enforcing them in code at every boundary — then let Gamma, not J, hold the plan.** Everything else (the conductor, model routing, Discord, chart-stops, the registry) is downstream of that single discipline, and every credible external source agrees.

*Full audit reports (6 agents) are in this session's transcript. Key evidence files: `automation/state/params.json:62`, `automation/prompts/heartbeat.md`, `backtest/lib/filters.py`, `backtest/lib/watchers/runner.py`, `automation/overnight/wake-protocol.md`, `automation/state/SCHEDULED-TASKS.md`, `automation/state/spend-2026-06-18.json`, `setup/scripts/discord-responder.py`.*
