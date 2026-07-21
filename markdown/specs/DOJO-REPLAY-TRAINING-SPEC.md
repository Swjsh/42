# THE DOJO — tick-by-tick replay training room (J + engine, side by side)

> **Provenance:** J's idea, spoken 2026-07-20 ~21:30 ET, thought through and specced by Fable
> the same evening. **This file IS the Opus build prompt** (J's routing: Fable maps → Opus
> builds the framework → Sonnet runs sessions with J). Opus: read this whole file, then build
> Phase 1. Do not redesign the intent schema or the validation stack — extend what exists.

## The idea in J's words (condensed, faithfully)

Buy the TradingView tier that unlocks intraday bar replay. J + an agent replay a historical
day candle-by-candle, watching the indicators FORM (the ribbon looks completely different
forming than it does in hindsight). At each step the agent surfaces what the engine sees and
would do; J advises what it SHOULD or SHOULD NOT be doing — including per-arm direction
("this put on two of the arms, this stop for one of them"). The agent ensures the code can
EXPRESS everything J directs. Arms get scored on J's directed trades. Then it becomes a
cheap, repeatable ritual: J + Sonnet pick random days and fine-tune the engine hands-on.

## Why this is the right idea (Fable's assessment)

1. **It attacks the proven #1 gap.** The 2026-07-20 winning-trade map + goal-loop synthesis
   established the engine's losses are LOGIC-shaped, not code-shaped. The missing input is
   J's chart judgment, which today reaches the engine only as after-the-fact corrections.
   The dojo makes it a structured, high-bandwidth, repeatable channel.
2. **The "watch it form" point is deep, not cosmetic.** Hindsight charts lie — a formed
   ribbon looks obvious; a forming one doesn't. Replay forces J's reads to be CAUSAL
   (information-limited, same constraint the engine faces). That makes his labels honest:
   a "nothing to do here" while the bar forms is a validated NEGATIVE label, killing the
   hindsight-bias class of "why didn't we take X" arguments — in both directions.
3. **It manufactures the scarcest asset: labeled decisions.** Live trading yields ~5
   labeled episodes/day. One dojo session yields 50+ (chart state, engine state, J
   directive, sim outcome) tuples per replayed day. Every pre-reg study we run starves for
   n; this is the n-factory. (Framing from the literature: this is DAgger-style
   imitation learning — expert corrections collected ON the learner's trajectory — applied
   to a trading policy. Prop firms do the human half of this as standard replay drills.)
4. **Per-arm direction lands on architecture that now exists.** The 2026-07-20 exit-diversity
   overlay (per-arm `exit_patch`) + the deterministic `j_intent_executor` intent schema
   (trigger/invalidation/exits/sizing per account) are exactly the rails a dojo directive
   needs. Nothing fundamental is missing — the dojo is mostly PLUMBING + RITUAL.

## THE ONE DANGER (load-bearing — Opus must build this in, not bolt it on)

A replayed day is n=1. The same evening this was specced, a zone-boundary stop that
"obviously" should have held (+$130 counterfactual on the day) FAILED the population test
(-$63.73/tr vs control). If J's dojo directives patch the engine directly, the dojo becomes
an anchor-trade overfitting factory (C24/L140) with a charismatic UI.

**The fix is a hard two-lane split on everything harvested from a session:**

- **LANE A — CAPABILITY gaps ("the code CANNOT express what J directed").** Example: "trail
  only 2 of 3 contracts", "stop above that wick, not the level". These ship immediately as
  knobs/plumbing with guards (like tonight's exit_patch overlay). Expressiveness is never
  overfitting.
- **LANE B — POLICY rules ("the engine SHOULD do X when Y").** These become pre-registered
  hypotheses run through the EXISTING validation stack (frozen pre-reg → population replay
  via exit_manager_walk → OP-16 gates) before any live wire. J's judgment picks WHAT to
  test — that's his edge, and it collapses the search space; the battery decides what
  SHIPS. Burden-of-proof symmetry per OP-33(d): when a session shows the engine blocked a
  J-directed winner, the GATE owes provenance+evidence, not the trade.

Every session harvest doc routes each item to a lane explicitly. No third lane exists.

## Architecture (Phase 1 build, in order)

**Fence (non-negotiable):** the dojo NEVER touches live state or places broker orders. Own
state dir `automation/state/dojo/`, sim-only executor, hard no-orders guard test, and — per
the 2026-07-20 STATE-FILE-REVERSION incident — NO git operations on tracked live state.

1. **Replay Conductor** (`setup/scripts/dojo/replay_conductor.py`, deterministic Python, no
   LLM in the step loop). Picks a day; drives TradingView bar replay via the EXISTING MCP
   tools (`replay_start/replay_step/replay_status/replay_stop` — verify empirically against
   the running TV desktop before building higher layers); feeds the SAME closed bars to the
   REAL engine decision path in sim mode (reuse the backtest-as-heartbeat pattern — see
   markdown/specs/BACKTEST-AS-HEARTBEAT-DESIGN.md — so the code under training is the code
   that trades, not a model of it). Lockstep invariant: TV chart time == engine sim time at
   every pause, asserted, drift = hard stop. Controls: step, run-to-time, pause. Session
   ledger: `automation/state/dojo/sessions/YYYY-MM-DD-<replay-day>.jsonl`.
2. **Engine Whisper renderer** (`dojo/whisper.py`): compact human rendering of the decision
   row at each step — scores, gates hit, vetoes, what would place, per-arm intent — the
   "listen into the engine" surface. Data all exists (core-decisions schema); this is
   formatting, keep it terse (J reads it live).
3. **Directive channel**: J speaks; the session agent (Sonnet) translates to a structured
   directive EXTENDING the j-intent schema (new fields: `arms:[...]` targeting + per-arm
   exit overrides reusing `exit_patch` vocabulary; `dojo:true`). Directives are DATA logged
   to the session ledger with full context — the sim executor arms them exactly like
   j_intent_executor would live. If J directs something the schema can't express → that IS
   a Lane-A harvest item, logged at the moment it happens.
4. **Sim execution + arm scoring** (`dojo/sim_executor.py` + `dojo/scorecard.py`): fills
   directed trades from historical option data (reuse exit_manager_walk's fill/exit logic +
   OPRA cache; BS-synthetic fallback flagged per Free-Kitchen-Plan-B rules); runs each arm's
   REAL exit profile against the directive. End-of-session scorecard per arm: J-directed
   P&L vs engine-actual/counterfactual P&L, every divergence point listed. This doubles as
   PROSPECTIVE J-edge-capture measurement (OP-16's metric, measured forward not backward).
5. **Session harvest** (`dojo/harvest.py` + template): closes every session with a written
   doc — directives issued, divergences, Lane A items → build queue, Lane B items →
   hypothesis queue with pre-reg stubs. A session without a harvest doc didn't happen.
6. **Curriculum** (data, not code): start with known-informative days — 2026-07-17 (the
   +$679 day), 2026-07-20 (red day, stale-sight day), 06-30 / 07-02 / 07-08 (the HTF-level
   days J called out as misses). Random days after the ritual works; adversarially-selected
   days (engine/J likely to disagree) later still.

## TradingView tier — what J should actually buy

Replay MCP tools exist and are wired; the constraint is TV's plan gating for INTRADAY
replay. Guidance: buy the CHEAPEST tier that unlocks intraday bar replay (historically
Essential; verify current packaging at purchase), NOT premium — upgrade only if 1-min
replay history depth actually blocks the curriculum (deep intraday history is the
higher-tier feature; recent-weeks curriculum days likely fit the low tier). **Opus step 0:
empirically test replay_start/step on the current plan + document exactly what errors/limits
appear, BEFORE J pays** — the current tier's replay may already handle 5-min bars, which
covers the engine's native cadence; 1-min candle-forming is the J-experience upgrade.

## Cost + model routing (J's explicit design)

- Build: **Opus** (this spec is the prompt). Sessions: **Sonnet** + J, after-hours/weekends,
  Max-subscription capacity, $0 marginal. Step loop: pure Python, $0.
- Fable: session-harvest ADJUDICATION only (Lane B ship/kill calls), never the sitting.
- Per-session cost estimate for OP-3 gate: one Sonnet interactive session (~1-3h) — within
  Max plan; no new paid APIs. The TV tier subscription is the only new recurring cost and
  it is J-initiated.

## What this is NOT

- Not a new engine, not a new backtester (reuses exit_manager_walk / backtest-as-heartbeat).
- Not autonomous — the dojo is the HUMAN-teaching channel by design; the conductor/kitchen
  loops stay separate.
- Not a bypass around validation: Lane B exists precisely so dojo wisdom ships with the same
  evidence bar as every other edge.

## Deep-research add-on (queued, non-blocking)

One bounded Sonnet/free-tier research pass: imitation-learning-from-replay for trading
(DAgger framing), prop-firm replay-drill methodology, any open-source "trading replay
trainer" tooling worth mining. Feeds Opus's build; does not gate it.

## Success criteria (how we know the dojo works)

1. First session completes a full day tick-by-tick with lockstep never breaking, and J says
   the whisper surface actually shows him what the engine is thinking.
2. ≥10 directives captured as structured data in one session; zero directives the schema
   could not express by session 3 (Lane A drains).
3. First Lane-B hypothesis from a session survives pre-reg and ships — the full loop closed:
   J's eye → labeled data → validated rule → live engine.
4. Sonnet can run session 2+ from the runbook alone (no Fable/Opus in the room).
