# Project Gamma — End-to-End Wired Map (2026-06-26)

> The strung-together picture: every subsystem, how they connect into ONE autonomous
> loop, what got fixed this pass, what runs unattended TODAY vs. what still needs J,
> and the remaining gap queue. Builds on (does NOT replace):
> - `markdown/planning/GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md` (architecture diagnosis)
> - `markdown/planning/GAMMA-AUTONOMY-NEXT-LEVEL-2026-06-21.md` (deployment-not-discovery)
> - `markdown/specs/ARCHITECTURE.md` (cold-start wiring snapshot, refreshed 2026-06-25)
> - `markdown/planning/ENGINE-WINS-PLAN-2026-06-26.md` (per-workstream deep design)
>
> Every claim here was grounded in a file this fire. Where a value differs from the
> ENGINE-WINS plan it is because the plan's recommended fix has since LANDED.

---

## 0. The one loop (eye → brain → hand → ledger → learn → loop)

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

## 1. Subsystem map (5 subsystems, how they connect)

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

## 2. What got FIXED this pass (grounded in files)

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

## 3. Autonomous NOW (runs unattended today)

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

## 4. Still MANUAL (the exact blockers to 100%)

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

## 5. Remaining gap queue (P1/P2 → appended to queue.md for the conductor)

See `automation/overnight/queue.md` Tier-1/Tier-3. Summary:
- **P1:** EXEC-WIRE-EXTRA-SETUPS (G4), VIX-INTRADAY-FEED (G6), SWARM-PREMARKET-TZ (G5, task re-register), EOD-FLATTEN-PURE-PYTHON (G7), COMPANION-APPROVAL-BUS (G8).
- **P2:** SELF-AUDIT-NEVER-FIRED (G9), ORPHAN-TASKS-DOC (G9), EXIT-RIBBON-FLIPBACK-WIRE (G14), STRUCTURE-VETO-SYSPATH-HARDEN (G13), REVIEWER-GLOB-OP20 (G15).

---

## 6. autonomy_scorecard (blunt)

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
