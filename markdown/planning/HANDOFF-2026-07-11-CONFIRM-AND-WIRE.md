# HANDOFF 2026-07-11 — CONFIRM & WIRE (entry-exit matrix, phase 2)

**Written by Fable 2026-07-08 late, after independently re-verifying the STOP-A execution
(T1–T4 + P5 gate, commits `c11aa1d…482c35d`) and shipping 7 review corrections (`807bd88`).
Executor: Opus or Sonnet. Judgment calls are pre-made here; verify every number you build on;
do NOT re-litigate. One STOP checkpoint (B). Prior handoffs:
HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX (its ground rules 8–12 carry) and
HANDOFF-2026-07-09-TRUTH-AND-EXITS (its 1–7 carry). Read
[`STOP-A-ENTRY-EXIT-MATRIX.md`](STOP-A-ENTRY-EXIT-MATRIX.md) INCLUDING the Fable review
addendum before touching anything.**

## WHERE WE ARE (verified 2026-07-08 late — do not re-derive)

- **The finding stands, review-hardened:** the shipped ribbon_ride exit (−20%/+150%) **loses
  −$757 replayed on the 79 real fleet positions (actual realized −$893 — parity ✓)** while
  wide-stop/partial-scalp/trailing shapes make +$1,053–1,574 on the same fills. On the full
  250-signal OPRA population the −20% stop harvests 55–62% of eventual +150% winners in every
  premium band; worst-quartile MAE-10min is **−43%/−35%/−32%/−27%** by band (cheap→rich).
- **Passive entry is conditional** (entry offset = stop headroom): wins ONLY paired with a
  stop+reachable-target scalp; loses under a no-stop ride. Entry×exit are COUPLED.
- **Nothing trading-path has changed.** Every exploratory winner is a P5 non-survivor; the two
  live shapes ride PROVISIONAL waivers. STOP-A sign-off is queued to J (firm-brief carries it).
- **Review discoveries you inherit as fact (each verified with quoted evidence in the addendum):**
  1. The old mass-grind's **lock/trail axis was a dead knob** — `run_backtest` never translated
     `profit_lock_mode`/`profit_lock_trail_pct` from `params_overrides` (only tp1/frac/target,
     orchestrator.py L342–346). 181/181 fixed-vs-trailing P4 pairs byte-identical. The entire
     existing P5 survivor universe tested "fixed" twice.
  2. The P5 gate now reads the **full survivor JSONL** (86), not the 15-row summary.
  3. **Two-lane shape discrepancy (open):** `vwap_continuation` = −8%/+30% on fleet arms
     (strategies.py) but −6%/+40% on core arms (`j_vwap_cont_*` params keys). Unresolved.
  4. The engine-contract card (`automation/state/engine-contract.md`) is now the trustworthy
     "what is the engine taking" surface — auto-regenerated every Gamma_FirmBrief fire
     (verified through the production path), drift-guarded, and it now shows entry policy too.

## GROUND RULES (13–17 new; 1–12 from the prior two handoffs still bind)

13. **Sweep knobs must reach the simulator: kwargs, not params-dict hope.** The dead-trail scar.
    Any grind sweeping lock/trail/time-exit passes them as explicit `run_backtest` **kwargs**
    (the way `strategy_space_grind.run_cell` passes `premium_stop_pct`), AND carries a
    vary-and-assert probe: two different knob values MUST produce different books on a smoke
    window, or the run aborts. No probe = the run is invalid.
14. **The exploratory window is BURNED for confirmation.** 2025-01-01..2026-06-18 (including its
    internal 2026 "OOS" split — it was visible during T4's ranking). Confirmation lives only in
    the four layers of the pre-registration's `t5_holdout_definition`.
15. **Pre-registration integrity is hash-pinned.** Before any confirmatory run, verify
    `analysis/exit-parity/signal-set.json` sha256 starts `b5e8931994b9d34b` and
    `entry-exit-matrix-stop-a-preregistration.json` says `"version": 2`. A mismatch = STOP,
    re-amend BEFORE running anything, log v3 with a reason.
16. **The real-fills anchor is a KILL-check, never a ratifier** — 17 unique (date,symbol)
    signals over 7 trading days, one regime. State the unique-signal count in every anchor stat.
17. **Prefer zero new knobs.** exit-A needs none. exit-B (per-band stop) and the entry_manager
    are new machinery — each ships only if its candidate SURVIVES T5, and each needs its own
    red-proofed guard + engine-contract card section (the card must auto-show any new knob).

## THE WIRING MAP — how a ratified shape/policy actually reaches the engine

*(This section answers "does it fit + how do we wire it." Every path verified by reading the
live code 2026-07-08; file:line anchors quoted. The engine-contract card §2/§3/§3b renders this
live — if the card and this map ever disagree, the card (regenerated) wins and this doc needs a
fold.)*

### EXIT — one source of truth, two consumption lanes

| lane | arms | shape source | consumption path | to change it |
|---|---|---|---|---|
| **fleet_rest** | safe-1/3, risky-1/3 | `strategies.py` `RIBBON_RIDE.exit` (ExitShape) | `fleet_executor._exit_shape_dict` (L260) → EntryPlan → `ExitState.from_entry` → per-tick `plan_exit_actions` fed (ask,bid) as (best,worst) (`fleet_broker` L222–239) | **edit the ExitShape literal in `automation/state/fleet/strategies.py`** |
| **core controls** | safe-2, bold-2 | SAME `strategies.py` shape for generic ribbon setups (`heartbeat_core` ~L1230 imports `strategies.by_name("ribbon_ride")`); `_SETUP_EXIT_OVERRIDES` j_* params keys for the 5 armed extra setups (L998–1013); params tp1/frac fallback | requires `GAMMA_CORE_MANAGES_EXITS=1` — set in production by `run-heartbeat-core.ps1:12`. Options can't bracket (Alpaca 42210000): params tp/stop are plan-LOG values only | **the same strategies.py edit covers ribbon entries on ALL 6 arms.** Per-setup cells: edit the `j_*` params keys |
| **research/BS-sim** | backtests | `run_backtest` kwargs | `simulate_trade_real` via orchestrator | pass exit knobs as **kwargs** (ground rule 13) |

**ExitShape is fully expressive for exit-A** (7 fields: stop/tp1/frac/lock/target/trail/arm — all
consumed by `ExitState.from_entry`, exit_manager.py L100–130). **exit-B (per-band stop) is NOT
expressible today** — the stop freezes at entry in `from_entry`; the clean implementation is a
pure resolver `stop_for_premium(entry_premium, band_table) -> stop_pct` applied by BOTH lanes
*before* `from_entry` (one function, two call sites, one guard). Spec in T-W4.

**Shipping gate for ANY shape change (all three, no exceptions):**
`test_p5_shape_gate.py` green (shape is a survivor of the CURRENT grind or J-signed waiver) +
A/B scorecard at `analysis/recommendations/` + STOP-B sign-off. The P5 gate now reads
`mass-grind-phase5.jsonl` — after a fresh grind, regenerate it via
`python -m autoresearch.mass_grind_phase5` or the gate judges against stale survivors.

### ENTRY — currently one hardcoded policy, no seam

Today (all arms): **marketable simple limit `ask + entry_cross_buffer` ($0.03 default)** —
`heartbeat_core:1140` → `fleet_broker.marketable_limit_price:249`; stale un-crossed BUYs
cancel-replaced each tick; **no premium floor; no patience/passive logic anywhere** (verified:
no `entry_manager*.py` exists in the repo). So:
- **entry-1 (premium floor)** = a plan-time admission check. Wire as params key
  `min_entry_premium` (default 0 = OFF), checked where the plan is built in BOTH lanes
  (heartbeat_core `_execute` pre-`check_order`; fleet_executor plan builder). It is strategy
  admission, NOT a risk_gate rule — do not touch risk_gate. Guard: vary-and-assert (floor 0.30
  must reject a $0.25 plan in a unit test; floor 0 must be byte-identical).
- **entry-2 (limit-below + patience + cancel)** = a NEW state machine, `entry_manager.py`,
  mirroring exit_manager's split: PURE core (`plan_entry_action(state, quote, now_et) ->
  place/hold/cancel/convert`) + thin actuator. Shadow-first: log-only alongside live entries
  for ≥3 sessions before any arm consumes it. Full spec in T-W5.

### READ PATH — who must be able to see it (the blind-spot fix)

Any change above must be VISIBLE without reading code: (a) the engine-contract card
auto-renders arms/shapes/entry-policy/floors — extend `engine_contract.py` in the SAME commit
that adds a knob; (b) `Gamma_FirmBrief` (verified scheduled: last fire 18:01 07-08 result 0,
next 06:35) regenerates it twice daily; (c) the drift guard + CI-on-push
(`.github/workflows/safety-gate.yml`, full suite per `run_safety_gate.py:14`) catch un-regenerated
edits; (d) `test_engine_contract_drift.py` red-proofed. **A knob that isn't on the card doesn't
exist** — that's the standing rule going forward.

## TASKS

### Sanctioned NOW (no STOP-A dependency — infra/shadow/data only)

**T-W1 — OPRA cache extension (the confirmatory fuel).** Extend `backtest/data/options/` from
its current end (2026-07-01) to the latest completed session via `backtest/tools/fetch_option_data.py`
(reaper rules: ONE process, backtest venv). Acceptance: cache file count grows; spot-check 3
new dates load via `load_contract_bars`; quote the new date span.

**T-W2 — kill the dead knob at the source.** Add `profit_lock_mode` + `profit_lock_trail_pct`
translation to the orchestrator's `_params_to_kwargs` block (mirror the existing
tp1_premium_pct pattern at L342–346) so params-driven sweeps can never silently drop the lock
axis again. **Graduated guard (red-proof it):** a smoke backtest with trail 0.10 vs 0.30 must
produce different books (vary-and-assert); revert the fix → guard REDs → restore. This is a
research-path file (orchestrator) — allowed now, but run the full guard suite; `simulator_real`
itself is untouched.

**T-W3 — fresh P5 grind with the trail axis REAL (weekend-scale).** Re-run
`-m autoresearch.mass_grind` (shards per its header) with the T4-informed grid: add trail
{0.15, 0.22} × time-exit as swept kwargs per ground rule 13 — smallest grid that covers the
v2 candidates' neighborhoods. Then the funnel (`-m autoresearch.mass_grind_funnel`, sharded)
→ `-m autoresearch.mass_grind_phase5`. Acceptance: `mass-grind-phase5.jsonl` regenerated;
fixed-vs-trailing pairs now DIFFER (quote 3); the P5 gate's survivor count reported.
**This is the grind the P5-hard-gate judges the candidates against.**

**T-W4 — per-band stop resolver (exit-B's machinery, shadow).** Pure function + unit tests
only (no arm consumes it yet): `resolve_stop_pct(entry_premium, band_table)` in a small module
both lanes can import. Red-proofed guard; engine-contract card section stub behind "not armed".

**T-W5 — entry_manager v1 (entry-2's machinery, shadow).** Pure core mirroring exit_manager:
`EntryState` (signal_premium, limit_price=signal×(1−δ), patience_ticks, policy cancel|convert,
placed_order_id) + `plan_entry_action(state, bid, ask, now_et)` → PLACE_LIMIT / HOLD / CANCEL
(miss) / CONVERT (marketable). Unit tests for fill/miss/convert/patience (port
`test_t3_entry_matrix.py` semantics tick-wise). Shadow actuator: for ≥3 live sessions log what
entry-2 WOULD have done next to each real entry (`automation/state/entry-shadow.jsonl`) — fill
rate + basis delta vs the real ask+$0.03 fills. Acceptance: shadow ledger has ≥3 sessions and
its fill-rate is within ±15pts of T3's backtest fill-rate for δ=10%/pat3 (sim-live parity
check BEFORE T6 trusts the backtest numbers).

**T-W6 — vwap two-lane discrepancy (investigation, read-only).** Git-archaeology both numbers:
`strategies.py` VWAP_CONTINUATION (−8/+30, note says "OOS +$105/tr") vs params
`j_vwap_cont_premium_stop_pct/_tp1_pct` (−6/+40). Which has a scorecard? (`analysis/
recommendations/vwapcont-exit-parity.json` is referenced by heartbeat_core's comment — read
it.) Deliverable: one-page provenance + a recommendation; the reconciliation itself is a
J/STOP-B decision. **[J: which vwap cell is the validated one?]**

### GATED on STOP-A sign-off (do NOT start before J/Fable/Opus signs)

**T-W7 — T5 confirmatory on the frozen v2 candidates.** Verify ground rule 15 hashes first.
Run the four layers from `t5_holdout_definition` for each of exit-A/B/C × entry-1/2 (C pairs
only with entry-2): (a) fresh-slice replay (T-W1 data; reuse `t4_exit_matrix.replay` — it IS
the live exit_manager); (b) real-fills anchor incl. days since 07-08; (c) P5 membership on
T-W3's fresh grind; (d) leave paper A/B to T-W8. Produce
`analysis/recommendations/entry-exit-matrix-2026-07-{date}.json` A/B scorecards (auto-ratify
bar in the pre-registration). **Report per candidate: PASS/FAIL per layer, no re-picks, no new
cells.** Anything that fails ≥1 layer is DEAD — a kill is a deliverable.

### ⛔ STOP CHECKPOINT B: scorecards → Opus/Fable/J pick what arms which fleet cell. Nothing ships past this line without it.

**T-W8 — (post-STOP-B) wire + paper A/B.** Per the WIRING MAP: strategies.py ExitShape edit
(+ waiver replacement or fresh-grind P5 pass so `test_p5_shape_gate.py` stays green), premium
floor key, entry_manager armed on the challenger arms J picks. Champion arms KEEP the ratified
control. 2 weeks of broker-truth fills → champion/challenger report. The engine-contract card
must show the new state in the SAME commits (rule 17).

## PRE-EXISTING BREAKAGE (unchanged from the prior handoff — do not confuse with your work)
15 test failures pre-date this chain (gamma_narrative ×2, bollinger watcher orphan ×2,
replay_fleet_arms ×3, setup_dispatch ×5, state_contracts ×1, trade_to_learn ×2). Fleet ledger
field is `setup_name`, not `setup`.

## J-DECISIONS (surface in firm-brief until answered)
- **STOP-A sign-off** (unblocks T-W7) — the package + review addendum: `STOP-A-ENTRY-EXIT-MATRIX.md`.
- **P5 waivers**: sign, replace-via-T5, or retire the two provisional waivers.
- **vwap two-lane cell** (T-W6 will bring evidence): −8/+30 or −6/+40?
- Carry-forward: account split · D-SIP $99/mo · D4/D5/D6.

## DEFINITION OF DONE
1. T-W1 cache extended + quoted span; T-W2 dead-knob fix red-proofed; T-W3 fresh grind +
   phase5 regenerated with a REAL trail axis (3 differing pairs quoted).
2. T-W4/T-W5 shadow machinery: unit-tested, red-proofed, ≥3 shadow sessions logged, sim-live
   fill-rate parity stated. Zero arms consuming them.
3. T-W6 provenance page filed; J question queued.
4. If STOP-A signed: T-W7 scorecards filed for EXACTLY the v2 candidates (hashes verified,
   quoted) and the STOP-B package delivered — not acted on.
5. Every number in your report carries quoted evidence (OP-33); every anchor stat carries a
   unique-signal count (rule 16); every new knob appears on the engine-contract card (rule 17).
**Tells you're failing:** you ran a grind without a vary-and-assert probe; you quoted an anchor
without unique-n; you tested a candidate not in the v2 file; you touched strategies.py before
STOP-B; the card and the code disagree at your final commit.
