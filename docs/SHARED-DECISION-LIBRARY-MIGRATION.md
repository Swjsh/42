# Shared Decision Library — Migration Spec (Phase 2b + "compile the decision core out of prose")

> **Status:** DESIGN ONLY. This document changes no live code. It specifies the final big architectural refactor so it can be executed deliberately and safely, one conductor-sized task at a time, with a parity gate as backpressure.
>
> **Source:** Blueprint `docs/GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md`, Phase 2b ("Detector→Insight registry + one shared decision library (backtest=live parity)") and the cross-cutting "drift-detection test kills manual `gamma-sync` … better: **generate** the derived copies … the manual sync ritual IS the drift vector."
>
> **Owner of execution:** the `Gamma_Conductor` after-hours fire (`automation/prompts/conductor.md`), one bounded task per fire, parity gate g-by-gate.
>
> **Author / date:** Gamma research session, 2026-06-18.

---

## 0. TL;DR

The decision logic that decides *whether to take a SPY 0DTE trade* currently exists in **three incompatible forms that drift**:

| Form | File | Nature | Authority |
|---|---|---|---|
| Config | `automation/state/params.json` | JSON knobs | canonical for *values* |
| **LIVE engine** | `automation/prompts/heartbeat.md` (~750 lines) | English prose an LLM **re-derives every tick** | what actually trades |
| BACKTEST engine | `backtest/lib/filters.py` (1388 lines) + `backtest/lib/orchestrator.py` (gates inline) | hardcoded Python | what we research against |

"Does the backtest match what trades live?" is enforced only by a daily text **pin-check** + the manual **`gamma-sync`** ritual (now partly a failing test via `backtest/tests/test_params_filters_drift.py`). Because the live path is prose, **two ticks on the same bar can disagree** — the prose is re-interpreted each time, by a possibly-different model (Haiku vs Sonnet escalation).

**The target:** ONE tested Python **decision library** (`backtest/lib/engine/`) that holds the deterministic scoring + gate evaluation, imported by **BOTH** the backtest (orchestrator/filters call it) AND the live path (the heartbeat shells out to it via a thin shim, exactly as `pre_order_gate.py` already does for risk). The LLM keeps only the judgment it is good at — chart read, trigger recognition, "is this bar a clean rejection" — and the **deterministic verdict comes from code**. This is the NautilusTrader principle ("same source code for backtest and live") applied to Gamma, and the LEAN decoupling (Alpha→Risk→Execution) made literal.

**The proof already exists.** `backtest/lib/risk_gate.py#check_order` is exactly this pattern for the risk rules: ONE pure function, the backtest's orchestrator delegates to it, and the live heartbeat shells out to it via `automation/scripts/pre_order_gate.py`. This migration **repeats that proven move** for the scoring + entry-gate layer.

**This is a multi-week effort.** It is sequenced into small, independently-shippable, parity-gated steps, ordered by leverage and safety. The crux is Phase 4 — the heartbeat is an LLM prompt, so the shim/shell-out boundary (what the LLM still decides vs what code decides) is the genuinely hard part, and it is the LIVE MONEY path, so every step is reversible and validated before the next.

---

## 1. The problem, confirmed against the files

### 1.1 The three forms and where they live

**Live prose (`automation/prompts/heartbeat.md`).** The "Scoring" section defines BEARISH (10 filters) and BULLISH (11 filters) as numbered English rules (lines ~324-474). After scoring it layers:

- **Gates A–D** — Ribbon momentum / freshness / midday-trendline quality / afternoon conf+lvl_rec (the "RIBBON CONVICTION GATE", lines ~352-380).
- **Gates E–I** — `vix_bear_hard_cap`, `block_level_rejection`, `entry_bar_body_pct_min`, `block_bull_1100_1200`, `block_elite_bull` (the "PORTED BACKTEST GATES", lines ~384-423). These were *manually ported* from `orchestrator.py` to the prompt on 2026-06-18 — a live/backtest parity gap that someone had to notice and hand-transcribe.
- **Pre-execution gate sequence** G5/G7/G1/G2/G10/first-entry/G6/G6b (lines ~634-647).
- **Sizing + exits** — strike-per-tier tables, quality-tiered qty, the full exit hierarchy (chart stop / ribbon-flip / profit-lock chandelier / premium catastrophe cap / TP1 / runner).

**Backtest Python (`backtest/lib/filters.py` + `orchestrator.py`).** `evaluate_bearish_setup()` (filters.py:1011) and `evaluate_bullish_setup()` (filters.py:808) implement the same 10/11 filters as real code returning a `SetupResult{passed, bear_score, blockers, triggers_fired, …}`. The orchestrator's `run_backtest()` (orchestrator.py:429) takes **every gate as a kwarg** (`midday_trendline_gate`, `block_level_rejection`, `entry_bar_body_pct_min`, `vix_bear_hard_cap`, `block_bull_1100_1200`, `block_elite_bull`, `min_ribbon_momentum_cents`, … lines 441-629) and applies them **inline** as ~15 `if gate and <condition>: decisions.append({… "action": "SKIP_…"}); continue` blocks (orchestrator.py:1153-1438). The orchestrator computes `winning_side` ("P"/"C"), `winning_triggers`, and `quality_tier` ("LEVEL"/"ELITE"/"TRENDLINE"/…) from the two `evaluate_*` results (orchestrator.py:999-1052) — that derivation is itself decision logic that exists nowhere in the live prose except as the prose's implicit tier mapping.

**Config (`params.json`).** Every threshold both forms read. `backtest/lib/contracts/models.py#ParamsModel` already documents its consumers: *"heartbeat.md — the live Safe trading loop reads every exit/entry/VIX/gate knob below on every tick"* and *"filters.py / orchestrator.py — the backtest engine reads the same knobs (Operating Principle 4: live and backtest must not drift)."* The contract names this as the explicit invariant the whole package exists to protect.

### 1.2 How drift is "enforced" today (and why it is insufficient)

1. **Premarket pin-check** (`RULE_VERSION` constant vs `params.json#rule_version`) — catches a version-number mismatch, not a *semantic* one. The prose can say "−10% stop" while params says `-0.50` and the pin still passes.
2. **`gamma-sync` skill** — a *human ritual*: "edit heartbeat.md AND filters.py simultaneously, then run pytest." The blueprint's own verdict: **"The manual sync ritual IS the drift vector."** The SKILL.md is referenced across the repo but the file itself is now superseded by an automated test.
3. **`crypto/validators/v25_filter_gates.py`** — the real guard. Binds 5 VIX/ribbon constants as hard equalities (P1-P5), binds `filter_9`/`filter_10` knobs (P6-P10), and runs a **presence ratchet** (PRES_*): every ACTIVE `block_*`/`*_gate`/`*_min`/`*_hard_cap`/`*_required` knob in each params file MUST appear by name in its heartbeat prompt, else FAIL ("ORPHAN"). `backtest/tests/test_params_filters_drift.py` ratchets this so no new gate knob can be added without v25 covering it.

**The gap v25 cannot close by construction:** it asserts a knob is *referenced* in the prose (a `grep` of the prompt) and that a *constant* matches a value. It cannot assert that the prose **computes the same answer** as `evaluate_bearish_setup` on the same bar — because the prose isn't executable. The only way to close that gap is to **make the live path execute the same code the backtest does.** That is this migration.

### 1.3 The drift incidents this has already caused (evidence the cost is real)

- **2026-06-16 (C14/L38):** the real-fills backtest path passed the GLOBAL `premium_stop_pct` (−0.08) instead of the side-specific bear stop, so every real-fills run used −8% regardless of `premium_stop_pct_bear=−0.20` in params.json. A sim-vs-production mismatch that "invalidated an entire weekend of research" (CLAUDE.md OP-16 sim-accuracy gate).
- **2026-06-18 (the 6-gate drift):** five gates (`vix_bear_hard_cap`, `block_level_rejection`, `entry_bar_body_pct_min`, `block_bull_1100_1200`, `block_elite_bull`) lived in `params.json` + the orchestrator but **were never wired into the live prompt** — silently inert in production while "active" in backtest. Found and hand-ported; the v25 presence ratchet was then built to prevent recurrence. This is precisely the bug class a shared library makes structurally impossible.

---

## 2. Target architecture

### 2.1 The shape: a deep module behind a narrow interface

```
                       params.json  (values — unchanged, still canonical)
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
   ┌───────────────────────────────────────────────┐
   │   backtest/lib/engine/   (the decision core)   │   ← NEW: one tested,
   │                                                │     deterministic, pure
   │   score.py   : score_bear() / score_bull()     │     Python module. No I/O.
   │   gates.py   : evaluate_gates()  (A–I + ports) │     No LLM. No mutation.
   │   alpha.py   : composite_alpha()  (detectors)  │
   │   verdict.py : EngineVerdict (frozen dataclass)│
   └───────────────────────────────────────────────┘
              ▲                           ▲
              │ imports                   │ shells out (thin shim, like
              │ directly                  │ pre_order_gate.py already does)
   ┌──────────┴──────────┐     ┌──────────┴───────────────────────────┐
   │ BACKTEST            │     │ LIVE                                  │
   │ orchestrator.py     │     │ heartbeat.md (LLM) ── reads chart,    │
   │ filters.py          │     │   recognizes triggers, then calls     │
   │ simulator_real.py   │     │   engine_cli.py → gets EngineVerdict  │
   └─────────────────────┘     │   → obeys it (does NOT re-derive)     │
                               └───────────────────────────────────────┘
```

This is **Ousterhout's "deep module"**: a large amount of decision logic (21 filters + ~15 gates + the side/tier derivation) hidden behind a *narrow* interface — one function `decide(detector_outputs, market_state, params) -> EngineVerdict`. It is a deliberate, documented exception to Gamma's "many small files" rule (the blueprint flags this tension explicitly via *Out of the Tar Pit* essential-vs-accidental complexity): the decision core is essential complexity that belongs concentrated and tested, not scattered across prose + Python + config. **The migration REDUCES surface area** — the ~450 lines of scoring/gate prose in `heartbeat.md` collapse to a "read the verdict, obey it" stub, and the ~15 inline gate blocks in `orchestrator.py` collapse to one `evaluate_gates()` call.

### 2.2 The interface (the narrow waist)

```python
# backtest/lib/engine/verdict.py
@dataclass(frozen=True)
class EngineVerdict:
    """The deterministic answer for ONE bar. Pure data; both paths obey it."""
    action: str            # "ENTER_BEAR" | "ENTER_BULL" | "HOLD" | "SKIP_<GATE>"
    side: Optional[str]    # "P" | "C" | None
    setup_name: Optional[str]
    bear_score: int
    bull_score: int
    bear_blockers: list[int]
    bull_blockers: list[int]
    triggers_fired: list[str]
    rejection_level: Optional[float]   # or reclaim_level for bull
    quality_tier: Optional[str]        # "LEVEL"|"ELITE"|"TRENDLINE"|...
    blocking_gate: Optional[str]       # the FIRST gate that fired SKIP, else None
    reason: str                        # one human clause

# backtest/lib/engine/__init__.py
def decide(
    *,
    bear_ctx: BarContext,              # already exists in filters.py
    bull_ctx: BarContext,
    params: Mapping[str, Any],         # the loaded params.json
    now_et: dt.datetime,
) -> EngineVerdict: ...
```

`decide()` is pure: no file reads, no MCP, no mutation (frozen result), exactly like `check_order`. It composes three already-existing bodies of logic, just relocated:

1. **`score.py`** — wraps the *existing* `evaluate_bearish_setup` / `evaluate_bullish_setup` (moved or re-exported from `filters.py`). No behavior change in step 1; this is a *relocation + a tested entry point*.
2. **`gates.py`** — `evaluate_gates(verdict_so_far, params, now_et)` returns the first SKIP gate or None. This is the ~15 inline `if gate and …: continue` blocks from `orchestrator.py:1153-1438` lifted verbatim into one ordered function. Gate order is preserved exactly (the orchestrator order *is* the spec).
3. **`alpha.py`** — `composite_alpha(...)` (Phase added later, §2.3): merges the watcher fleet's `WatcherSignal`s + the two live setups into one ranked list of detector insights.

### 2.3 The detector→Insight unification: what exists vs what's needed

The blueprint's Phase 2b second half: *"Each detector emits a uniform `Insight{direction, confidence, triggering_level, as_of_ts}` into a registry, merged by a composite (à la LEAN's CompositeAlphaModel)."*

**What already exists (most of it):**

- `backtest/lib/watchers/__init__.py#WatcherSignal` is **already the uniform detector contract**: `{watcher_name, setup_name, direction, entry_price, stop_price, tp1_price, runner_price, confidence, reason, triggers_fired, metadata}`. Every one of the 25 registered watchers emits exactly this shape.
- `backtest/lib/watchers/runner.py#WATCHERS` is **already the registry** ("being defined == being registered == being run"), with `run_all_watchers()` iterating it, per-day dedup, and a reconciliation test (`backtest/tests/test_watcher_registry.py`) asserting `set(detector files) == set(registry)` — the "engine couldn't see it" orphan guard. `registered_watcher_names()` / `WATCHER_COUNT` are the single source of truth for fleet size.
- A detector that emits nothing already does so *visibly*: every `spec.invoke` is wrapped `try/except → stderr` (the T63 silent-failure guard).

**What's needed (the gap):**

1. **The two LIVE setups do NOT yet emit `WatcherSignal`.** `BEARISH_REJECTION_RIDE_THE_RIBBON` and `BULLISH_RECLAIM_RIDE_THE_RIBBON` are scored by `evaluate_bearish_setup`/`evaluate_bullish_setup` returning `SetupResult`/`BullishSetupResult` — a *different* shape than `WatcherSignal`. To unify, add a thin adapter `setup_result_to_signal(SetupResult, …) -> WatcherSignal` (or register the two live setups in the same registry with a confidence derived from the score: e.g. `bear_score>=9 → "high"`). This is a ~40-line adapter, not a rewrite — the fields line up almost 1:1 (`rejection_level → triggering_level`, `triggers_fired → triggers_fired`, score → confidence tier).
2. **A `CompositeAlpha` merge step** — `composite_alpha(signals: list[WatcherSignal]) -> Optional[WatcherSignal]` that applies the live "more triggers wins, tie = neither" rule (heartbeat Decision line ~474) across *all* detector outputs, not just the two live setups. Initially it returns only the two live setups' merged verdict (parity with today); the 25 watchers stay WATCH_ONLY (OP-21 gate: 3 live J wins before any watcher trades). The composite is the *seam* through which a future ratified watcher becomes tradeable — by promotion config, not new prose.
3. **`Insight` vs `WatcherSignal`:** do NOT introduce a new `Insight` type. `WatcherSignal` already is the insight contract; renaming it would churn 25 files for zero behavior gain (against the LEAN-target leanness principle). The blueprint's `Insight{direction, confidence, triggering_level, as_of_ts}` maps onto existing fields; the only genuinely missing field is an explicit `as_of_ts` (currently carried as the `bar_timestamp_et` at the log site). Add `as_of_ts` to `WatcherSignal` if and only if the composite needs it for ordering; otherwise leave the contract alone.

**Net:** the detector→Insight unification is ~80% shipped. The remaining 20% is (a) one adapter so the live setups join the registry, and (b) one composite-merge function. Both are pure and independently testable.

### 2.4 What the LLM keeps (the judgment boundary)

The LLM (heartbeat) keeps ONLY what code cannot do from the JSON state files:

- **Reading the live chart** via TradingView MCP (the closed-bar filter, ribbon study values, VIX refresh, HTF 15m).
- **Recognizing triggers in real time** — "did this bar wick-reject 745.02", "is the ribbon freshly flipped" — i.e. populating the `BarContext` / detector inputs from what it sees.
- **Trade management nuance** the prose does well: screenshot capture, journal prose, dashboard speech, iron-law fill reconciliation against Alpaca.

Everything **deterministic** — scoring the filled `BarContext`, evaluating Gates A–I, computing side/tier, the sizing caps — moves to `decide()`. The LLM's job becomes: *observe → build the detector inputs → call `decide()` → obey the verdict → execute + journal.* It stops being a re-derivation engine and becomes an *eyes + hands* layer over a deterministic brain. That is the NautilusTrader "same code, backtest and live" guarantee: in backtest, `decide()` is fed `BarContext` from historical bars; live, it is fed `BarContext` from the LLM's chart read; the verdict function is byte-identical.

---

## 3. The phased migration (the heart of this doc)

Each phase: **what ships**, the **parity gate** that must pass before it counts as shipped, and the **rollback**. Every phase is independently valuable and independently revertible. No phase touches `params.json` *values* or the 10 rules — only *where the logic lives*. Phases 1–3 are engine-benefit (ship per the auto-ratify gate, no J pre-approval). Phase 4 touches the live prose surface = **propose-and-ping-J** (conductor rail 4); J's role is REVOKE.

### Phase 1 — Extract scoring into `engine/score.py`, backtest calls it (assert-agree)

**What ships:**
- New `backtest/lib/engine/score.py` exposing `score_bear(ctx, params) -> SetupResult` and `score_bull(ctx, params) -> BullishSetupResult`. Initially these **import and call** the existing `evaluate_bearish_setup` / `evaluate_bullish_setup` — zero logic change, just a stable, tested entry point that reads its parameters from a `params` mapping instead of scattered kwargs.
- `backtest/lib/orchestrator.py` changed to call `engine.score.score_bear/score_bull` instead of `filters.evaluate_*` directly.
- This mirrors exactly how `risk_gate.check_order` was integrated into the orchestrator's risk point in this session (task #9 "assert-agree with orchestrator").

**Parity gate (the proof it's safe):**
- `backtest/tests/test_engine_score_parity.py` — for a corpus of saved `BarContext` fixtures (reuse `crypto/validators/v25_filter_gates.py`'s `_bear_ctx`/`_bull_ctx` builders, which already construct passing + boundary contexts), assert `engine.score.score_bear(ctx) == filters.evaluate_bearish_setup(ctx)` field-for-field (`bear_score`, `blockers`, `triggers_fired`, `rejection_level`). Same for bull. This is the "assert-agree before replace" discipline from the risk_gate precedent.
- **Full backtest run must produce byte-identical decisions** to pre-change: run `python backtest/run.py --start <60d ago> --end <today> --label engine_phase1` before and after; diff the `decisions.csv`/`trades.csv`. Zero diff = the relocation changed nothing. (CLAUDE.md: "compare results across ALL historical days before declaring improvement".)
- `python -m pytest backtest/tests/test_filters.py backtest/tests/test_engine_score_parity.py -q` green; full gym green (`crypto/validators/runner.py` + v25 offline).

**Rollback:** revert the orchestrator import line back to `filters.evaluate_*`; delete `engine/score.py`. One-line revert, no state touched. The backtest is the only consumer in Phase 1, so a regression can never reach live trading.

---

### Phase 2 — Extract Gates A–I into `engine/gates.py` + add the executable parity test

**What ships:**
- New `backtest/lib/engine/gates.py#evaluate_gates(verdict_so_far, params, now_et) -> Optional[GateBlock]`. Body = the ~15 inline gate blocks from `orchestrator.py:1153-1438` (`block_level_rejection`, `trendline_requires_ribbon_flip`, `block_elite_bull`, `block_bull_ribbon_flip`, `block_bull_1100_1200`, `require_bearish_fill_bar`, `min_ribbon_momentum_cents`, `max_ribbon_duration_bars`, `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_conf_lvl_rec_afternoon`, `entry_bar_body_pct_min`, `entry_bar_body_pct_min_bull`, `vix_bear_hard_cap`) lifted **verbatim** into one ordered function, each reading its `params` key. Order preserved exactly (the orchestrator's top-to-bottom order is the canonical sequence; document it as such).
- `orchestrator.py` replaces the inline blocks with a single `gate = evaluate_gates(...); if gate: decisions.append(gate.skip_row); continue`.
- The `gates.py#GATE_ORDER` list becomes the **single declared source of gate sequence**, replacing both the orchestrator's implicit order and the heartbeat's "Apply Gates E–I in order" prose.

**Parity gate:**
- `backtest/tests/test_engine_gates_parity.py` — extend the existing `backtest/tests/test_gate_e2e_2026_06_18.py` (the E2E gate test already shipped this session). For each gate, a fixture bar that the gate SHOULD and SHOULD NOT block; assert `evaluate_gates` returns the same SKIP code the inline orchestrator block did (capture the pre-refactor `decisions.csv` SKIP rows as golden).
- **The new structural parity test — `test_heartbeat_gate_intent_parity.py`:** statically assert that every gate key in `gates.py#GATE_ORDER` is (a) referenced by name in `heartbeat.md` AND (b) referenced in `aggressive/heartbeat.md` where applicable. This *generalizes v25's PRES_* presence ratchet* to the gate-sequence level and is the first executable bridge between the prose and the code. It does NOT yet prove the prose *computes* the gate (Phase 3 does), but it proves the prose can't silently omit one (the exact 2026-06-18 6-gate bug).
- Full backtest byte-identical diff (as Phase 1); gym + v25 green.

**Rollback:** revert orchestrator to inline blocks; delete `engine/gates.py`. Backtest-only consumer; cannot reach live.

---

### Phase 3 — Shadow-mode the engine verdict alongside the live prose for N days

**What ships:**
- A thin CLI `backtest/lib/engine/engine_cli.py` (modeled exactly on `automation/scripts/pre_order_gate.py`): reads a `BarContext`-equivalent JSON on stdin (the market state the heartbeat already computes each tick — spy bar, ribbon, vix, htf, levels, triggers it recognized), loads `params.json`, calls `decide()`, prints the `EngineVerdict` as JSON on stdout. Pure function behind a stdin/stdout shim, $0, no MCP.
- The heartbeat is **NOT yet changed to obey it.** Instead, reuse the **existing shadow controller** (`automation/state/shadow-version.json` + the heartbeat's "Shadow-mode" block, lines ~65-87): on each tick the heartbeat ALSO calls `engine_cli.py` with the state it just computed, and logs the engine's `EngineVerdict.action` to `decisions.jsonl` as a shadow row (`version: "engine"`) **alongside** its own prose-derived action (`version: "prose"`). The prose action still drives real orders; the engine verdict is read-only — identical guarantee to today's Karpathy shadow mode.
- EOD-summary's existing shadow-diff machinery (Section 8c → `analysis/shadow-scorecards/{date}.jsonl`) diffs the two and reports any tick where `prose.action != engine.action`, with the bar context for forensics.

**Parity gate (this is the behavioral proof on LIVE bars):**
- Run shadow for **N ≥ 5 trading days** (reuse the shadow controller's standard 5-10 day window). The gate to proceed to Phase 4: **engine and prose agree on the action for ≥ 99% of ticks**, and **100% of ENTER ticks** (a disagreement on a HOLD tick is far cheaper than on an entry). Every disagreement is triaged: it is either (a) a prose bug the migration FIXES — in which case the engine is more correct and that strengthens the case — or (b) an engine bug to fix before cutover.
- Because this runs only in the after-hours-safe shadow path during real ticks, it cannot affect live orders (read-only by construction — the same property that made Karpathy shadow mode safe).

**Rollback:** set `shadow-version.json#enabled: false`. Shadow logging stops; nothing else changes. The engine never touched an order in this phase.

**Why a full phase:** this is where we earn the right to let code drive. The blueprint's "verify-now-not-later" says prefer in-process reproducers — and Phases 1-2 DO that (byte-identical backtest diff). But the *live* path has one thing backtest can't reproduce: the LLM's real chart read feeding the `BarContext`. Shadow mode is the only way to prove `decide()` agrees with the prose *on the exact inputs the LLM actually produces live*. It is the irreplaceable wall-clock validation, scoped to read-only.

---

### Phase 4 — Cutover: heartbeat consults the verdict; prose becomes a thin wrapper

> **This phase touches the live trading prose = conductor rail 4 = PROPOSE-AND-PING-J. J's role is REVOKE.** It ships only after Phase 3's parity gate is green for N days and an A/B/agreement scorecard is filed.

**What ships (in two sub-steps, each independently revertible):**

**4a — Engine becomes authoritative for the VERDICT; prose still executes.**
- The heartbeat's "Scoring" + "Gates A–I" + pre-execution gate sections are **replaced** by: *"Build the detector inputs from your chart read. Call `engine_cli.py`. The returned `EngineVerdict` is authoritative — if `action` is `SKIP_*` or `HOLD`, you do NOT enter; if `ENTER_BEAR`/`ENTER_BULL`, proceed to execution with the returned `side`, `setup_name`, `triggers_fired`."* The ~450 lines of scoring/gate prose collapse to ~30 lines of "compute inputs, call, obey."
- The LLM still owns: chart read (input construction), execution mechanics (strike pick, liquidity downsizing, bracket order), journaling, screenshots, iron-law fill reconciliation. Sizing stays behind the *already-shipped* `pre_order_gate.py` (which already delegates to `risk_gate`), so risk is unaffected by this step.

**4b — Codegen the prose stub (kills the last drift vector).**
- Per the blueprint: *"better: generate the derived copies from params.json (codegen) so they CAN'T diverge."* The heartbeat's gate-list and the human-readable gate descriptions become **generated** from `gates.py#GATE_ORDER` + `params.json` by a small `backtest/tools/gen_heartbeat_decision_block.py`, written into a delimited region of `heartbeat.md` (`<!-- BEGIN GENERATED DECISION BLOCK -->` … `<!-- END -->`). A pre-commit/CI check regenerates and asserts no diff — so a human editing params can never leave the prose stale. This is the manual `gamma-sync` ritual replaced by codegen.

**Parity gate:**
- Phase 3's ≥99% agreement must hold for the full N-day window FIRST (precondition).
- After 4a: a fresh **5-day shadow in REVERSE** — now the *prose execution path* is driven by the engine verdict, and we log what the *old prose* WOULD have said (cheap to compute since we kept the scoring prose available as a commented reference for one release). Assert continued ≥99% agreement on live bars. Any divergence = REVOKE to 4a-pre.
- After 4b: `test_heartbeat_generated_block_fresh.py` — assert `gen_heartbeat_decision_block.py` produces byte-identical output to what's committed (the codegen freshness check).
- Full gym + v25 + `test_params_filters_drift.py` green (the ratchet now has far less to guard because the prose no longer holds independent logic).

**Rollback (three levels, mirroring the v15 revert pattern in CLAUDE.md):**
1. **Instant:** `git checkout <pre-4a> -- automation/prompts/heartbeat.md` restores the full scoring prose. The engine library stays in tree (backtest keeps using it); only the live path reverts to prose. The heartbeat already documents this exact revert idiom for v15 ("`cp automation/prompts/heartbeat-v14-prod-backup.md …`").
2. **Keep a `heartbeat-prose-decision-backup.md`** (the full pre-cutover scoring/gate prose) for one release cycle, exactly as `heartbeat-v14-prod-backup.md` is kept.
3. **J-revoke:** a one-line Discord "shelve" flips the proposal; the conductor never auto-applied it in the first place (rail 4 — it was a DRAFT + ping).

---

### Phase 5 (optional, follow-on) — Promotion-rigor wired in + dead-prose deletion

Not strictly part of the decision-core compile, but the natural close-out:
- The advisory `backtest/lib/validation/gate.py#evaluate_candidate` (DSR/PSR/PBO, currently advisory-only) can be attached to the engine's promotion path as a scorecard field (its docstring already specs "how to wire in later" — J ratifies making it a hard gate).
- Delete the now-dead scoring/gate prose backup after one clean release (Phase 3a of the blueprint: "aggressive deletion of what the new tests prove nothing consumes"). The `test_heartbeat_gate_intent_parity` + codegen freshness tests are the proof that the prose carries no independent logic.

---

## 4. Risk mitigation — how to do this without breaking live trading

This is the **LIVE MONEY path.** The whole sequencing is built so a mistake cannot reach an order without first failing a gate. The discipline, restated as invariants:

| Invariant | Mechanism | Precedent |
|---|---|---|
| **Assert-agree before replace** | Phases 1-2 keep the old code AND the new code, prove field-for-field equality on fixtures + byte-identical backtest diff, THEN swap the call site. The new code is never trusted on its first run. | `risk_gate` → orchestrator integration (task #9, this session). |
| **Shadow before cutover** | Phase 3 runs the engine read-only alongside the prose on real live ticks for N≥5 days; ≥99% agreement (100% on entries) required before code drives anything. | Karpathy shadow mode, already in `heartbeat.md` + `shadow-version.json`. |
| **Tests are the gate, not vibes** | v25 (`v25_filter_gates.py`) + `test_params_filters_drift.py` + the new `test_engine_score_parity` / `test_engine_gates_parity` / `test_heartbeat_gate_intent_parity` MUST be green at every phase boundary. A red test = NOT shipped (conductor STAGE 3). | OP-25 "a re-violated lesson graduates to a code assertion." |
| **Market-closed windows only** | Every code change ships in the after-4pm or weekend window; never 09:30-15:55 ET. The conductor's STAGE 0 market-hours gate enforces this (rail 1, the L54 scar). | `conductor.md` rail 1. |
| **Reversible at every step** | Each phase has a one-line/one-commit rollback that leaves `params.json` values and the 10 rules untouched. The live path can always snap back to prose (`git checkout` heartbeat.md). | v15→v14 revert path in `heartbeat.md`. |
| **J holds the off-switch** | Phase 4 (the only phase touching live prose) is propose-and-ping-J; J's role is REVOKE, never pre-approve. No automated process blocks J's session (OP-32 scar). | `conductor.md` rail 4 + OP-25. |
| **Risk path already isolated** | Sizing/kill-switch already runs through `pre_order_gate.py` → `risk_gate.check_order`. This migration does NOT touch that path; even mid-migration, every order is still capped by the proven risk gate. | `pre_order_gate.py` (this session). |
| **Fail-closed on bad input** | `decide()` inherits `check_order`'s discipline: any unreadable input → safe default (HOLD/SKIP), never a speculative ENTER. Uncertainty = no trade. | `risk_gate.py#_is_bad_number` / UNREADABLE_INPUT. |

**The one thing that is genuinely irreversible** — a real paper order placed on a wrong verdict — is gated three-deep: (1) the engine verdict is shadow-only until Phase 4; (2) at Phase 4 it still passes through `pre_order_gate.py`'s risk caps and the iron-law fill check; (3) it is paper, and J can revoke the whole cutover with one Discord line. There is no phase in which an unproven `decide()` can place a live order.

---

## 5. How the conductor drives it

`automation/prompts/conductor.md` exists (after-hours, one-bounded-task-per-fire, parity gate as backpressure). This migration is **a queue of conductor-sized tasks**, each ending at a parity gate that gives the next fire a clean go/no-go. Frame each as a `queue.md` HIGH item with a `depends:` chain so the conductor's STAGE 1 picker takes them in order and **skips any whose predecessor's parity gate hasn't gone green**.

Suggested `queue.md` decomposition (each = one conductor fire, ≤ a few hours, parity-gated):

1. `engine-1a` — create `engine/score.py` re-exporting `evaluate_*`; write `test_engine_score_parity.py`; **gate:** parity test green. *(Agent: `tdd-guide`.)*
2. `engine-1b` — switch `orchestrator.py` to call `engine.score`; **gate:** byte-identical backtest diff + gym green. *(depends: 1a. Agent: `general-purpose`.)*
3. `engine-2a` — create `engine/gates.py` (lift the 15 blocks verbatim) + `GATE_ORDER`; write `test_engine_gates_parity.py`. *(depends: 1b. Agent: `tdd-guide`.)*
4. `engine-2b` — switch `orchestrator.py` to `evaluate_gates()`; **gate:** byte-identical diff. *(depends: 2a.)*
5. `engine-2c` — write `test_heartbeat_gate_intent_parity.py` (prose ↔ GATE_ORDER presence). *(depends: 2b. This is engine-benefit; ships per auto-ratify gate.)*
6. `engine-3a` — write `engine_cli.py` (stdin/stdout shim, mirror `pre_order_gate.py`); unit-test it. *(depends: 2b.)*
7. `engine-3b` — wire the engine shadow row into the heartbeat's existing shadow block; arm `shadow-version.json`. **This edits `heartbeat.md` = propose-and-ping-J**, BUT it is read-only shadow logging (no order path touched), so the proposal is low-risk; J approves arming. *(depends: 3a.)*
8. `engine-3c` — **WAIT (not a code task): collect N≥5 days of shadow.** The conductor's role here is to read the shadow scorecard each fire and, once the agreement gate is met, file the A/B/agreement scorecard at `analysis/recommendations/engine-cutover.json` and flag J. *(depends: 3b.)*
9. `engine-4a` — DRAFT `heartbeat-engine-cutover-draft.md` (scoring/gates → "call the verdict, obey it"); ping J with the scorecard. **propose-only.** *(depends: 3c green.)*
10. `engine-4b` — after J ships 4a + a reverse-shadow window confirms: codegen the prose stub (`gen_heartbeat_decision_block.py` + freshness test). *(depends: 4a live + clean.)*
11. `engine-2b'` (detector unification, parallelizable with 3.x) — `setup_result_to_signal` adapter + `composite_alpha`; register the two live setups in the watcher registry; **gate:** `test_watcher_registry.py` still green + composite returns today's verdict on fixtures. *(depends: 2b.)*

The parity gate is the backpressure: a fire that finds its task's gate red does NOT proceed — it flags and stops (conductor STAGE 3). Independent sub-parts (e.g. the detector-unification track `engine-2b'` vs the shim track `engine-3a`) can be fanned out in parallel within a fire (OP-22 "no rationing"), but each remains one bounded *item* with its own gate.

---

## 6. Honest scope, sequencing, and the crux

**This is a multi-week effort.** Not because any single step is large — each is a few hours — but because Phase 3 has an **irreducible wall-clock cost**: N≥5 *trading* days of shadow before cutover is justified, and that window cannot be compressed (it's the one validation a synthetic reproducer can't replace, because it needs the LLM's real live chart reads). Phases 1-2 can land in a few after-hours sessions; Phase 3 is gated by the calendar; Phase 4 follows once the shadow agreement holds.

**Ordering by leverage + safety:**
- **Phases 1-2 first** because they are *pure backtest-internal* — highest safety (cannot reach live), and they immediately pay off: the backtest gains a tested, single decision entry point, and the orchestrator's 15 scattered gate blocks become one auditable function. They also *build the artifact* (`decide()`) that Phase 3 needs.
- **Phase 3 next** because it is the cheapest way to earn confidence on live bars (read-only, $0, reuses existing shadow infra) and it produces the evidence J needs to approve Phase 4.
- **Phase 4 last** because it is the only phase touching the live money prose, so it goes last, gated, propose-only, three-deep reversible.
- **Detector unification (the `composite_alpha` track) runs parallel to 3.x** — it is independent of the score/gate extraction and doesn't touch live execution (watchers stay WATCH_ONLY per OP-21).

**The crux — the genuinely hard part:** the heartbeat is an **LLM prompt**, so the shim/shell-out boundary is the whole game. Two specific difficulties:

1. **Input construction is the soft edge.** `decide()` is only as good as the `BarContext` the LLM hands it. The LLM must reliably translate "what I see on the chart" into the exact fields (`ribbon_now.stack`, `vix_now`/`vix_prior`, `levels_active`, `ribbon_history`, the triggers it recognized) that `evaluate_*` expects. If the LLM mis-populates an input, `decide()` returns a perfectly deterministic *wrong* answer. Phase 3 shadow mode is precisely the instrument that surfaces this: a systematic prose-vs-engine disagreement on entries usually means an *input-construction* gap, not a logic gap — and it must be closed (sharper input-spec prose, or moving more of the input computation into the chart-read tools) before cutover. This is why the gate is **100% agreement on ENTER ticks**, not just 99% overall.
2. **The boundary must not regrow prose logic.** The temptation at Phase 4 is to leave "just a little" scoring nuance in the prose ("if the verdict is HOLD but you see a textbook setup, consider…"). That re-opens the drift vector. The discipline: the prose may describe *what to observe* and *how to execute*, but it may contain **zero** "compute a score" or "evaluate a gate" language post-cutover — and `test_heartbeat_gate_intent_parity` + the codegen freshness check enforce it. The near-miss/override path (heartbeat's "Near-miss alert") stays — but it routes to J's dashboard for a *human* manual override, never a prose re-derivation.

**Effort estimate (honest):**
- Phases 1-2 (score + gates extraction, parity tests, byte-identical verification): **~3-5 conductor fires / after-hours sessions.** Low risk, backtest-only.
- Detector unification track: **~2 fires**, parallelizable.
- Phase 3 build (CLI shim + shadow wiring): **~2 fires**, then **5-10 trading days of wall-clock shadow** (calendar-bound, near-zero active effort — the conductor just reads the scorecard each fire).
- Phase 4 (cutover draft + J approval + reverse-shadow + codegen): **~2-3 fires** spread across J's REVOKE windows.
- **Total active work: roughly two to three weeks of after-hours fires; total elapsed: three to four weeks** dominated by the mandatory shadow window. There is no safe way to go faster — the shadow window is the price of letting code drive the live money path, and it is cheap insurance against the exact drift incidents (2026-06-16, 2026-06-18) this whole migration exists to end.

**What success looks like:** `heartbeat.md` shrinks by ~400 lines (scoring + gates → a verdict call); `orchestrator.py` loses ~15 inline gate blocks (→ one `evaluate_gates`); `gamma-sync` is deleted (codegen replaces it); the question "does the backtest match what trades live?" becomes *true by construction* instead of *checked by ritual*; and two ticks on the same bar **cannot** disagree, because the verdict is one deterministic function, not a prose re-interpretation. One source of truth, less prose, smaller surface — the LEAN target.

---

## Appendix A — File/function reference (verified 2026-06-18)

| Concern | File · symbol | Lines |
|---|---|---|
| Live engine (prose) | `automation/prompts/heartbeat.md` | ~750 total |
| — Scoring (10 bear / 11 bull filters) | heartbeat.md "Scoring" | ~324-474 |
| — Gates A-D (ribbon conviction) | heartbeat.md "RIBBON CONVICTION GATE" | ~352-380 |
| — Gates E-I (ported backtest gates) | heartbeat.md "PORTED BACKTEST GATES" | ~384-423 |
| — Pre-exec gate sequence G5/G7/G1/G2/G10/G6/G6b | heartbeat.md "Pre-execution gate sequence" | ~634-647 |
| Backtest scoring | `backtest/lib/filters.py` · `evaluate_bearish_setup` | 1011 |
| Backtest scoring (bull) | `backtest/lib/filters.py` · `evaluate_bullish_setup` | 808 |
| Backtest gate kwargs | `backtest/lib/orchestrator.py` · `run_backtest` | 429-629 |
| Backtest side/tier derivation | `backtest/lib/orchestrator.py` | 999-1052 |
| Backtest inline gates (→ `evaluate_gates`) | `backtest/lib/orchestrator.py` | 1153-1438 |
| **Proof-of-concept: risk extracted to one pure fn** | `backtest/lib/risk_gate.py` · `check_order` | 182 |
| **Proof-of-concept: live shells out to it** | `automation/scripts/pre_order_gate.py` | full |
| Detector contract (uniform) | `backtest/lib/watchers/__init__.py` · `WatcherSignal` | 116-129 |
| Detector registry | `backtest/lib/watchers/runner.py` · `WATCHERS` / `run_all_watchers` | 212-367 |
| State-file contracts (params/loop/position…) | `backtest/lib/contracts/models.py` | full |
| Drift guard (params↔filters↔heartbeat) | `crypto/validators/v25_filter_gates.py` | full |
| Drift coverage ratchet (kills `gamma-sync`) | `backtest/tests/test_params_filters_drift.py` | full |
| Promotion rigor (DSR/PBO, advisory) | `backtest/lib/validation/gate.py` · `evaluate_candidate` | full |
| Shadow controller | `automation/state/shadow-version.json` + heartbeat "Shadow-mode" | 65-87 |
| Conductor (drives this migration) | `automation/prompts/conductor.md` | full |
| E2E gate test (extend in Phase 2) | `backtest/tests/test_gate_e2e_2026_06_18.py` | — |
| Registry reconciliation test | `backtest/tests/test_watcher_registry.py` | — |

## Appendix B — External references (from the blueprint's research)

- **NautilusTrader** — "backtest = live by construction; every order passes through the RiskEngine; broker-as-truth reconciliation." *The single best architectural model for Gamma's same-code goal.*
- **QuantConnect LEAN** — the decoupled Alpha → Portfolio → **Risk** → Execution pipeline; **CompositeAlphaModel** = the watcher-registry/`composite_alpha` pattern.
- **Freqtrade** — the `IStrategy` plugin/registry contract (the `WATCHERS` registry analog).
- **SEC Rule 15c3-5 (Market Access Rule)** — automated risk controls mandatory; "human monitoring is not sufficient" (the reason `risk_gate`/`decide()` are code, not prose).
- **Out of the Tar Pit** (Moseley & Marks) — essential vs accidental complexity; the decision core is essential complexity that belongs concentrated.
- **Ousterhout, *A Philosophy of Software Design*** — "deep modules": a large implementation behind a narrow interface. `decide()` is a deliberate, documented exception to Gamma's "many small files" rule.
- **Fowler — Consumer-Driven Contracts** / Pact / "parse don't validate" — the contracts layer (`contracts/models.py`) and the parity tests.
