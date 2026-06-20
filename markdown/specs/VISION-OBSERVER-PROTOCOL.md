# Vision Observer Protocol — DRAFT 2026-05-17

> **Status:** SCAFFOLD ONLY. Scheduled task NOT YET REGISTERED. Awaiting J's authorization
> to begin live observation per the install command at the bottom of this document.
>
> **Owner:** Gamma (the file is doctrine; the persona is the executor).
>
> **Doctrine references:** OP-3 (cost gate), OP-11 (Karpathy method — shadow mode parallel),
> OP-20 (non-theatre validation), OP-21 (watch-first promotion path), OP-22 (don't stop
> cooking — after-4pm window), OP-26 (crypto harness as vision validation surface — same
> mental model, different surface), OP-27 (scheduled-task discipline).

---

## 1 — Why we're building this

### 1.1 The "see the chart like a person" mandate

J's directive: *"Claude must see the chart like a person not a robot."*

The production heartbeat (v15.1) reads OHLCV via TV MCP and applies hard numeric filters
(ribbon stack, spread, VIX, time, level events, score thresholds). The filters are correct.
But the filters are blind to chart features a human trader sees instantly:

- **In-progress candlestick shape** — a hammer FORMING at a key level vs a hammer that
  closed and was confirmed. The closed-bar rule (v15.1 R1) was specifically introduced to
  prevent acting on the in-progress bar, because the prompt was misreading TV's `data_get_ohlcv`
  index [-1] (the live bar) as a closed bar. The cure was correct (per R1 lesson 2026-05-14)
  but the cure means we wait the full 5-minute bar before any decision, even when the
  forming candle is obvious to a human.
- **Visible level interactions** — price touching, wicking through, rejecting a named
  ★★+ key level in real time, before the bar has closed.
- **Momentum acceleration / fade** — a chart-reader sees this in the bar progression
  and the wick patterns; the filter framework sees only the closed-bar score.
- **Gestalt regime read** — choppy vs trending vs ranging is obvious to a trader's eye
  and very hard to encode as a numeric filter that survives regime changes.

### 1.2 The 5/15 fast-V foot-gun

`journal/2026-05-15.md` documents the −$770 BEARISH_REJECTION_RIDE_THE_RIBBON loss caused
by the closed-bar rule entering on the 09:46 ET fill into the bounce of a fast V reversal.
By 09:50 the trade was already underwater. Per the journal: *"v15.1 closed-bar rule
entered into the bounce."*

The strategy candidate `strategy/candidates/2026-05-17-live-price-first-bar-trigger.md`
proposes a doctrine fix (v15.3) for that specific event. The vision observer is the
OBSERVATION SURFACE that will help validate whether the v15.3 mechanism (or any future
fix) catches similar foot-guns BEFORE we modify production. It's the watch-first promotion
path (OP-21) applied to a chart-reading capability.

### 1.3 The watch-first promotion guarantee

This layer ships as OBSERVER ONLY for at least 20 trading days. No trades, no doctrine
edits, no order placement, no production state writes. Per OP-21 the promotion path
requires 3+ historical observations that would have won, 3+ live observations confirmed
by J, positive expectancy over the full observation window, and J's explicit ratification
before any "vision can VETO heartbeat" branch ships to production.

---

## 2 — Architecture

```
+--------------------------------+
|     Gamma_ChartVision          |     (Task Scheduler, every 3 min 09:30-15:55 ET wd)
|     (NOT YET REGISTERED)       |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| run-chart-vision-observer.ps1  |     (wrapper — same gates as heartbeat)
| - weekday/holiday/market-hours |
| - idempotency check (per tick) |
| - heartbeat-busy yield gate    |
| - state self-heal              |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| Invoke-Claude (haiku, $0.15    |     (per OP-3 budget cap)
| budget, 60s timeout, --print)  |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| chart_vision_observer.md       |     (the prompt — reads chart, emits 1 JSON line)
| - capture_screenshot via TV    |
| - data_get_ohlcv (grounding)   |
| - quote_get (price_now)        |
| - get_account_info (context)   |
| - emit JSON to stdout +        |
|   append to JSONL              |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| automation/state/              |     (append-only log, one line per tick)
| vision-observations.jsonl      |
+--------------------------------+

                 ... EOD 16:05 ET ...

+--------------------------------+
| eod_deep/main.py Stage 4a.7    |     (existing pipeline + new stage)
+----------------+---------------+
                 |
                 v
+--------------------------------+
| vision_observer_grader.py      |     (pairs vision obs vs heartbeat dec; grades on
|                                |      next-bar SPY close from master CSV)
+----------------+---------------+
                 |
                 v
+--------------------------------+
| analysis/                      |     (per-day scorecard; feeds 20-day promotion-path
| vision-vs-heartbeat-{date}.json|      decision per OP-21)
+--------------------------------+
```

### 2.1 The data flow at a glance

| Step | When | Who | Reads | Writes |
|---|---|---|---|---|
| 1 — capture | every 3 min 09:30-15:55 ET wd | wrapper PS1 | screenshot dir | `vision-snapshots/{date}/tick_NNN.png` |
| 2 — observe | same tick | haiku via prompt | screenshot + grounding OHLCV + quote | one line to `vision-observations.jsonl` |
| 3 — grade | 16:05 ET nightly | grader module | `vision-observations.jsonl` + `decisions.jsonl` + SPY 5m CSV | `analysis/vision-vs-heartbeat-{date}.json` |
| 4 — review | weekly (Sun 16:00 ET if Treasurer; or any after-4pm session) | J or Chef | analysis files | promotion path proposal (only if 20+ days green) |

### 2.2 Why the layers are separate

- **Wrapper PS1** owns: gating, idempotency, throttle vs heartbeat, hidden-window discipline.
- **Prompt** owns: the visual read, the structured emission, the refusal of unsafe asks.
- **Grader** owns: pairing, grounding against next-bar truth, aggregate scoring.
- **EOD wiring** owns: invocation cadence, error-isolation (one stage failure cannot crash EOD).

Single-responsibility per layer makes each one independently testable and replaceable.

---

## 3 — The 6-question framework

The vision prompt forces an answer to exactly six fields per tick:

| # | Field | Type | Notes |
|---|---|---|---|
| Q1 | `q1_price_action_now` | 1-2 sentence string | What price is doing RIGHT NOW. Not "this session," not "the last closed bar." |
| Q2 | `q2_in_progress_pattern` | enum | hammer_forming, doji_forming, engulfing_forming, inside_bar_forming, outside_bar_forming, sweep_forming, none, other:DESCRIPTION |
| Q3 | `q3_level_interaction` | object | `named_level`, `interaction` (approaching/breaking/rejecting/reclaiming/holding_above/holding_below/no_relevant_level), `distance_dollars` |
| Q4 | `q4_momentum` | enum | accelerating_up/down, fading_up/down, stalled, choppy |
| Q5 | `q5_direction_call` + `q5_horizon_minutes` | enum + int | bull/bear/chop/unclear over the next 5/10/15 min |
| Q6 | `q6_confidence_1_10` + `q6_what_would_change_my_call` | int + 1-sentence string | Honest "I don't know" must score ≤3 |

The schema is deliberately narrow. The grader keys on Q5 + Q6 because those are the
falsifiable signals. Q1-Q4 are journal context for J's review.

---

## 4 — Promotion path (per OP-21)

### 4.1 Observation phase (mandatory, 20+ trading days)

- **NO live trading** based on vision output.
- **NO doctrine modifications** based on vision output.
- **NO order placement**, ever, from the vision prompt.
- Grader writes per-day scorecards; aggregate cross-day analysis runs Sunday weekly review.

### 4.2 Promotion gate (all of the following must be true)

| Gate | Threshold | Source |
|---|---|---|
| Calendar days observed | ≥ 20 trading days | grader output files |
| Total DIVERGED-ticks graded | ≥ 50 | aggregate sum |
| Vision accuracy on DIVERGED ticks | > Heartbeat accuracy + 10pp | grader output `aggregate.vision_minus_heartbeat_diverged_pp` |
| At least one DIVERGED case where vision-correct AND heartbeat-wrong WOULD have saved or made $500+ | manual review | per-tick walk of analysis JSON |
| J's explicit ratification | written authorization | Discord / direct message |
| Pre-merge gate | `python crypto/validators/runner.py` 29/29 PASS | OP-26 |

### 4.3 If promotion gate passes

Propose a NARROW vision-veto branch — example: *"If vision says BEAR with confidence ≥ 7
AND heartbeat is about to fire ENTER_BULL, BLOCK the bull entry for 1 tick and re-evaluate."*

The branch:
- adds to `automation/prompts/heartbeat.md` as a NEW filter (filter 12 — vision_veto)
- adds a NEW field to `params.json` (`v16_vision_veto_enabled: true`, `_min_confidence: 7`)
- writes a parallel filter in `backtest/lib/filters.py` per OP-4
- is gated on a new entry in `crypto/validators/` per OP-26

### 4.4 If promotion gate fails

The observer continues running indefinitely as a cost-free validator. The
`vision-vs-heartbeat-{date}.json` file is a permanent advisory artifact for J's
weekly review. No production action is taken.

---

## 5 — Banned use cases (current phase)

- **NO live trading.** Vision prompt has zero write access to position state.
- **NO doctrine modifications.** Vision prompt has zero write access to `heartbeat.md`,
  `params*.json`, `CLAUDE.md`. The wrapper PS1 has read-only file access to those.
- **NO order placement.** The prompt body explicitly enumerates the banned MCP tools
  (`place_option_order`, `place_stock_order`, `place_crypto_order`) and the prompt's
  refusal protocol kicks in if injected.
- **NO writes to `decisions.jsonl`** (heartbeat owns that file — vision-only file is
  `vision-observations.jsonl`).
- **NO writes to `current-position*.json`** (heartbeat owns position state).
- **NO Discord pings** during observation phase (per OP-22 — vision is one of the
  many always-running observers).

---

## 6 — Cost projection

| Cadence | Ticks/day | $/tick (haiku w/ image + structured output) | $/day | $/month (21 trading days) |
|---|---:|---:|---:|---:|
| 1 fire per heartbeat tick | 127 | $0.05 | $6.35 | $133.35 |
| 1 fire per 2 heartbeat ticks (proposed throttle) | 64 | $0.05 | $3.20 | $67.20 |
| 1 fire per 3 heartbeat ticks (conservative) | 42 | $0.05 | $2.10 | $44.10 |

**Budget context (OP-3):** $100/mo Max 5x plan. Full-cadence observation ($133/mo standalone)
would BLOW THE BUDGET. The proposed deployment cadence is **1 fire per 2 heartbeat ticks**
(half-cadence) — $67/mo recurring. If observation produces measurable signal (vision_minus_
heartbeat_diverged_pp > 5 over first week), J ratifies escalation to full cadence with a
matched downgrade elsewhere (e.g., COOL-mode heartbeat throttle).

**Hard kill switch:** if cumulative vision-observer cost in a calendar month exceeds $80,
the scheduled task auto-disables itself and writes RED to STATUS.md. The kill is implemented
via a cost-counter file the wrapper checks before each fire (NOT yet shipped — Stage 2
deliverable when J authorizes the task).

**One additional cost line:** the EOD grader is pure Python ($0/day recurring).

---

## 7 — Testable hypotheses (first 20 days)

The observation phase is designed to resolve ONE hypothesis with statistical power:

**H1:** *In DIVERGED ticks where vision says BEAR (confidence ≥ 7) and heartbeat says ENTER_BULL
(or vice versa), the vision direction call is correct on the next-5m-bar more than 60% of
the time, while the heartbeat direction is correct less than 40% of the time.*

Per the grader's aggregate output:
- `diverged_vision_accuracy_pct` (on DIVERGED-only ticks) → target > 60%
- `diverged_heartbeat_accuracy_pct` (on DIVERGED-only ticks) → target < 40%
- `vision_minus_heartbeat_diverged_pp` → target > 20

Secondary signals (data flywheel — recorded but not gated):

**H2:** Q2 `in_progress_pattern` predicts the next-bar direction better than chance on bars
where Q2 ≠ "none" (chart-reading skill verification — does Claude actually SEE patterns).

**H3:** Q6 `confidence_1_10` is calibrated — accuracy at confidence ≥ 8 > accuracy at
confidence ≤ 5 by > 25pp.

---

## 8 — What J needs to do to authorize live observation

### 8.1 The 4-step install command (run once, after J approves)

```powershell
# (1) Verify the scaffold files are present
Test-Path "C:\Users\jackw\Desktop\42\automation\prompts\chart_vision_observer.md"
Test-Path "C:\Users\jackw\Desktop\42\setup\scripts\run-chart-vision-observer.ps1"
Test-Path "C:\Users\jackw\Desktop\42\backtest\autoresearch\vision_observer_grader.py"

# (2) Smoke-fire the wrapper once outside market hours to confirm no crash
# (it will exit 0 immediately due to the market-hours gate — that's the desired behavior)
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\jackw\Desktop\42\setup\scripts\run-chart-vision-observer.ps1"

# (3) Register the scheduled task — pending Stage 2 install script
# (this script is NOT shipped tonight; will be created in setup/install-chart-vision-observer.ps1
# matching the OP-27 hidden-window pattern: wscript + run_exe_hidden.vbs + run_ps1_hidden.py)

# (4) Verify zero-leak post-registration
python "C:\Users\jackw\Desktop\42\setup\scripts\audit_window_leak_compliance.py"
# Expected output: zero VISIBLE_WINDOW / PYTHON_NOT_PYTHONW flags
```

### 8.2 Read-only safety guarantees (the contract)

By authorizing live observation, J accepts and Gamma guarantees:

1. **Zero order placement.** The chart_vision_observer.md prompt has zero authority to place
   any order, on any account, ever. The prompt body explicitly refuses such requests.
   If injected via a chart annotation, the prompt's refusal protocol returns
   `direction_call: "unclear"` + `what_would_change_my_call: "REFUSED — prompt injection attempt"`.

2. **Zero production state mutation.** The vision prompt only WRITES to
   `automation/state/vision-observations.jsonl` (append-only, dedicated file). It does NOT
   write to `params.json`, `current-position*.json`, `decisions.jsonl`, `loop-state.json`,
   `trades.csv`, `today-bias.json`, `key-levels.json`, or any other production state file.

3. **Zero doctrine modification.** The vision prompt cannot edit `heartbeat.md`, `params*.json`,
   `CLAUDE.md`, or any other doctrine file. The wrapper PS1 has read-only file access to
   doctrine; the prompt has only its own emission target.

4. **Cost ceiling.** Daily cost ≤ $7 (at full cadence); monthly cost ≤ $80 (with auto-kill
   switch). Budget overshoot triggers auto-disable + STATUS.md RED entry.

5. **No interference with heartbeat.** The wrapper has a throttle gate that yields a tick
   when the heartbeat is currently in-flight (prevents TV CDP contention).

6. **Revert path.** To pause: `Disable-ScheduledTask -TaskName Gamma_ChartVisionObserver`.
   To remove: `Unregister-ScheduledTask -TaskName Gamma_ChartVisionObserver -Confirm:$false`.
   Per OP-27: re-run `python setup/scripts/audit_scheduled_tasks.py` after to confirm
   zero ORPHAN_TASK / STALE_REGISTRY_ENTRY flags. Vision observations to date are preserved
   in the JSONL log for forensic review.

---

## 9 — Open questions for J (parking lot)

These are NOT blockers for scaffold ship — they're the questions Stage 2 (task registration)
will resolve with J's call.

- **Q-A: Cadence.** Half-cadence (every 2nd heartbeat tick = 64 fires/day = $3.20/day) vs
  full-cadence (every tick = 127 fires/day = $6.35/day) vs HOT-mode-only (only when heartbeat
  is in HOT mode = ~30 fires/day = $1.50/day)?
- **Q-B: Vision-only blackout window.** Should vision fire during 14:00-15:00 ET (the period
  v15 removed from heartbeat's no-trade window)? Or only during the heartbeat's entry window
  09:35-15:00 ET?
- **Q-C: Multimodal input strategy.** Should the wrapper pre-capture the screenshot via a
  Python TV MCP client and pass the local PNG to Claude as multimodal input (cleaner, faster,
  $0.01-0.02/tick saved)? Or let the prompt itself call `capture_screenshot` (simpler scaffold,
  current design)?
- **Q-D: Grounding cadence.** Should the prompt ALWAYS call `data_get_ohlcv` for grounding
  (more reliable, +0.5s + 5 tokens/tick) or only when vision confidence is ≤ 6 (cheaper,
  matches the "see like a person" mandate more closely)?

---

## 10 — Append log

| Date | Change | Author |
|---|---|---|
| 2026-05-17 | Initial scaffold (prompt + wrapper + grader + EOD wiring + this doc + candidate spec). Task NOT registered. | autonomous wake fire |
