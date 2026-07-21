# THE DOJO — architecture decision + module contracts (Opus, 2026-07-20)

> Companion to DOJO-REPLAY-TRAINING-SPEC.md (the why/what). This file is the HOW: the one
> load-bearing architecture correction + the frozen module contracts every Phase-1 builder
> implements against. Builders: implement TO THE CONTRACT below; do not change a signature
> without updating this file first.

## THE CORRECTION (why the spec's "Python drives TV replay" was imprecise)

The TradingView replay tools (`replay_start/step/status/stop`) are **MCP tools available to the
session AGENT, not a Python library.** A standalone `replay_conductor.py` cannot call them. So
the conductor is NOT one Python process driving everything. It is two roles:

- **THE HANDS — the Session Agent (Sonnet + J, interactive).** The only thing that can call TV
  MCP tools. Loop: `replay_step` (advance one bar) → `replay_status` (read `current_date`
  epoch cursor) → invoke the Dojo Engine CLI with that cursor → relay the whisper to J →
  capture J's spoken directive → invoke the Dojo Engine CLI to log/arm it. Pure orchestration
  + relay; makes NO trading decision.
- **THE BRAIN + BOOKS — the Dojo Engine (deterministic Python, `setup/scripts/dojo/`).** Given a
  cursor timestamp, runs the REAL engine decision path (reusing `heartbeat_core._build_payload`)
  in sim mode, renders the whisper, validates + logs directives, sim-executes directed trades
  (reusing `backtest/lib/exit_manager_walk.py`), scores arms. ZERO LLM, ZERO live state, ZERO
  broker. Own state dir `automation/state/dojo/`.

This satisfies the spec's real intent — "no LLM in the step loop": the ENGINE decides
deterministically, J is the human advisor, the LLM only clicks + relays. It is the exact
[[feedback_no_llm_in_live_trade_loop_2026_07_15]] shape applied to training.

## DATA SEPARATION (critical — do not scrape bars off TV)

The engine is fed from OUR historical bar store (the SIP 5-min cache the backtest/live engine
already uses — reuse `replay_today_eval.load_spy_ribbon()`'s loader pattern), NOT from reading
TV's chart. Reasons: (1) avoids CDP contention (the MCP server already holds 9222); (2)
guarantees the engine sees EXACTLY the bars it would trade on live, not TV's possibly-different
feed; (3) `_build_payload`'s RTH-only + trig_idx=n-2 conventions must be preserved and that's
our data, our code. TV replay is J's VISUAL surface + the CLOCK only. The cursor epoch from
`replay_status.current_date` selects WHICH bar of our store to feed.

## FROZEN MODULE CONTRACTS (Phase 1)

All modules live in `setup/scripts/dojo/`. sys.path adds `("backtest", "setup/scripts",
"automation/state/fleet")` per the futures_edge3_sim.py pattern. All times ET, tz-aware.

### clock.py  (Opus builds — pure, no I/O)
- `resolve_cursor(current_date_epoch: int) -> datetime` — TV replay epoch → tz-aware ET datetime.
- `latest_closed_5m_bar_et(cursor_et: datetime) -> datetime` — the ET timestamp of the latest
  5-min RTH bar CLOSED at/before cursor (the trigger bar the engine scores; mirrors
  _build_payload trig_idx=n-2). Returns the bar's close time.
- `is_rth(cursor_et) -> bool`.

### engine_step.py  (Agent A)
- `step(replay_day: date, cursor_et: datetime, bars_df: pd.DataFrame) -> list[DojoDecision]` —
  slice bars_df to <= cursor_et, call the REAL `heartbeat_core._build_payload` + the same decide
  path heartbeat_core uses, for BOTH accounts (safe, bold) AND surface each fleet arm's gated
  view. Return one DojoDecision per arm. MUST reuse the live path, not re-implement scoring
  (that's what replay_today_eval.py is — an audit re-impl; do NOT copy it, import the real one).
- `@dataclass(frozen=True) DojoDecision`: `arm, side, verdict, bear_score, bull_score, ribbon,
  htf_15m, vix, triggers, setup, trigger_level, would_place: bool, spy, cursor_et, context_bundle`.

### whisper.py  (Agent B) — pure formatting
- `render(decisions: list[DojoDecision], cursor_et: datetime) -> str` — terse multi-arm
  human block for the agent to relay to J. One line per arm: verdict, scores, side, trigger,
  key levels near. No fabricated data — only fields present on DojoDecision.

### directive.py  (Agent B) — extends j_intent schema
- `@dataclass(frozen=True) DojoDirective`: `id, issued_et, cursor_et, arms: list[str], side,
  trigger, invalidation, exits (exit_patch vocabulary from accounts.json), sizing, note,
  dojo: True`. Reuse `j_intent_logic` validation primitives where they exist; extend, don't fork.
- `parse_and_validate(raw: dict) -> DojoDirective` — raise on unknown arm id, unknown exit_patch
  key (reuse fleet_executor's EXIT_PATCH_ALLOWED_KEYS), malformed trigger. Fail LOUD.
- `to_ledger_row(d: DojoDirective) -> dict`.

### sim_executor.py  (Agent C) — reuse exit_manager_walk, NO broker
- `arm_directive(state, directive, bars_df, option_bars) -> state` — fill the directed entry
  from historical option data at cursor (OPRA cache; BS-synthetic fallback FLAGGED per
  Free-Kitchen-Plan-B), then each subsequent step advances open positions via
  `exit_manager_walk.walk_exit_manager` using THAT ARM's exit profile (registry shape +
  accounts.json exit_patch). Positions are per-arm. HARD FENCE: never import any alpaca/broker
  module; a test asserts this.
- `@dataclass DojoPosition` + `advance(state, cursor_et, bars_df, option_bars) -> (state, events)`.

### scorecard.py  (Agent C)
- `score_session(session_ledger: Path) -> dict` — per-arm: J-directed P&L vs engine-actual /
  engine-counterfactual P&L, divergence points listed. This is PROSPECTIVE J-edge-capture
  (OP-16 metric measured forward). Write `automation/state/dojo/sessions/<id>-scorecard.json`.

### session.py  (Opus builds — the spine + CLI)
- CLI: `python -m dojo.session start --replay-day YYYY-MM-DD` (creates session id + ledger) ·
  `... step --session <id> --cursor <epoch>` (calls engine_step, prints whisper, advances sim) ·
  `... directive --session <id> --json '<json>'` (parse/validate/log/arm) · `... close
  --session <id>` (scorecard + harvest stub).
- Session state machine: CREATED → STEPPING → CLOSED. Ledger: append-only JSONL at
  `automation/state/dojo/sessions/<id>.jsonl`, one row per step/directive/event.
- HARD FENCE (guard-tested): dojo package imports NOTHING from alpaca/broker/live-order paths;
  writes ONLY under automation/state/dojo/; performs NO git operations (2026-07-20
  STATE-FILE-REVERSION scar).

## HARVEST (two-lane, from the spec — enforced at close)
`close` emits a harvest doc stub routing every session divergence to LANE A (capability gap →
build queue) or LANE B (policy rule → pre-reg hypothesis). No third lane. Fable adjudicates
Lane B; Sonnet ships Lane A.

## Phase 1 DONE = success criterion 1
A full replayed day steps tick-by-tick, lockstep never breaks (clock asserts TV cursor ==
engine bar), the whisper shows J the engine's mind, ≥1 directive is captured as structured
data, and Sonnet can drive it from DOJO-SESSION-RUNBOOK.md alone. Sim P&L scoring (criteria 2)
may finish in 1b; the spine + fence + clock + whisper + directive capture are Phase 1.
