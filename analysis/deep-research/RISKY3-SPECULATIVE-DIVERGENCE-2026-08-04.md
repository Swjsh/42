# RISKY3-SPECULATIVE — divergence measurement + what shipped (2026-08-04, lane 3)

**Verdict first: J's complaint is CONFIRMED with numbers, then fixed from the validated
menu.** Over the last 5 sessions risky-3 took only **4 trades the safes did not** (real
closed P&L **-$229**), every one of them lane=`normal` — and across ALL TIME, all 39
risky-3 placed entries are lane=`normal`: **probe, score-ladder, and full-send have never
placed a single trade**. Risky-3 has effectively been "safe-3 minus the confluence
requirement, min-size 5 vs 3, and a wider trail." Tonight it gains a genuine speculative
lane from the validated menu (vwap_reclaim_failed_break fleet extension), and the weekly
instrument that keeps this measured without J asking.

Window: 2026-07-28, 07-29, 07-30, 07-31, 08-03 (5 weekday sessions).

---

## 1. Enumerated config deltas (from source, not memory)

| Axis | safe-2 (core) | safe-3 | risky-1 | risky-3 |
|---|---|---|---|---|
| Execution | mcp_heartbeat, `params.json` | fleet_rest, SAFE base | fleet_rest, BOLD base | fleet_rest, BOLD base |
| gate_override | — | `min_triggers 2 + require_confluence_or_sequence` | `full_send: true` (normal lane UNGATED) | `min_triggers: 1` |
| hard-skip opt-out | n/a | inherits global | inherits global | `gate_params.hard_skip_verdicts=[]` (trades through `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`) |
| Rescue lanes | extra_exec (5 setups, 3 armed) | none | FULL_SEND (0 fires ever — L246 wall #2) | PROBE (0 fires ever) · LADDER (disarmed 07-27) |
| Strike table | `safe` (ATM thru $10K) | `bold_core` | `bold_core` | `bold_core` |
| Sizing | core tiers | SAFE base 8/elite 12 @$5K, min 3 | BOLD, but full-send clamps ALL entries to min 5 | BOLD base 8/elite 12 @$5K, min 5 + SHIP C boost (qty 10 when premium <$0.50) |
| Exit | CORE registry | patch: structure+trailing | patch: tp1 0.5 + structure (REACHABLE-TP1) | patch: structure+trailing, trail 0.20 (ZONE-RIDE) |

**Two axes are currently flattened:** (a) the recency-RED clamp reduces every ribbon_ride
entry to min_contracts (12→5, 8→3) — risky-3's qty edge over safe-3 is just 5-vs-3 while
RED persists; (b) `min_triggers 1` blocks 0 ticks (fleet-history measurement quoted in
fleet_executor.py: 0/3479 on risky-3) — there is nothing left to loosen on that knob.

## 2. Real-ledger divergence (last 5 sessions, broker-truth fills)

Placed: risky-3 **7** · safe-3 **5** · risky-1 **2** · safe-2 core **3 real intraday**
(07-28 10:36 vwap_reclaim_failed_break 737P; 07-28 13:50 + 08-03 13:21 bollinger_squeeze
— the 08-03 one is the +$67.85 entry three counters missed, L244).

**Marginal cohort (risky-3 took, NEITHER safe took same-minute): n=4, closed -$229**

| Entry | Quality | Why the safes didn't | Real P&L |
|---|---|---|---|
| 07-30 11:34 733P | BASE | safe-3 gate: requires confluence/sequence | **-$165** |
| 07-30 11:43 734P | BASE | safe-3 gate: 1 trigger < 2 | **-$110** |
| 07-31 12:19 746C | ELITE | safe-3's contract priced 0.15 < $0.30 floor (equity-tier strike divergence) | **+$126** |
| 07-31 13:25 747C | ELITE | same floor mechanism (0.23 < 0.30) | **-$80** |

Reverse divergence: safe-3 took 07-28 11:28 744C which risky-3 missed **by one cent**
(premium 0.29 < 0.30 floor), and 07-31 12:31 747C while risky-3 was NOT_FLAT riding its
12:19 winner. n-SMALL: 5 sessions, 4 marginal trades — a description of the week, not an
edge estimate.

## 3. Config-level replay (fleet_arm_replay population layer, $5K forward equity)

Run under the in-flight ATM-TIER-EXTENSION-2K-10K table (parallel lane's edit was on disk
— disclosed, and it is the Tuesday-forward truth). Entry-layer only. risky-3 config admits
5 entries vs safe-3's 5 and safe-2's 6, but different ones: risky-3-minus-safe-3 = 3
(07-28 11:20C, 07-30 11:25P base, 07-31 11:40C). The `hard_skip_verdicts=[]` opt-out
accounts for exactly **1** admission in 5 sessions (the 07-30 base bear — the same cohort
that lost real money above). The rest of the divergence is base-params family
(SAFE vs BOLD filter sets), not gate_override.

## 4. Menu adjudication (nothing from the graveyard)

- **Lower min_triggers on risky-3 — DEAD as differentiation.** Already 1; blocks 0/3479
  ticks; producer admission is upstream. Verified live-wired but saturated.
- **Score-ladder floor 7 — RE-DERIVED, stays dead.** The 07-27 fullhist disarm plus the
  pre-registered LADDER-SUBSET-VERDICT-2026-07-28 measured the floor-7 lane directly:
  SENSITIVITY_lane7 +$306 aggregate but WR 0.29, day-majority FAIL (14/41), drop-best
  FAIL — frozen consequence verbatim: "the ladder concept is dead at every granularity we
  can currently express." The -$16,642 figure was floor=8 (risky-1 doc); floor=7 was
  separately measured and also fails the frozen bars. Not re-armed.
- **Extra-setups arming on risky-3 — SHIPPED** (§5).
- **SHIP C (cheap-contract qty 10) — already live** (tonight's earlier commit; consumer
  verified in `finalize()`, guard `test_cheap_contract_qty_boost_2026_08_03.py`). Zero
  fires yet — all window fills predate it; 3 of 7 risky-3 entries this week had premium
  <$0.50, so it would have applied ~3 times going forward.

## 5. What shipped tonight (prereg 6658c2c3 BEFORE the arm)

**FLEET-VWAP-RECLAIM-EXTENSION-RISKY3** — the validated edge #2
(`vwap_reclaim_failed_break`: 8/8 anti-cherry-pick gates on real OPRA; ARMED live on core
safe-2 with a real PLACED fill 07-28 10:36) now emits into the fleet producer's
`strategies[]`. Selectivity does the differentiation exactly as doctrine demands: safe-3's
own gate HOLDs it (3 triggers, none confluence/sequence — guard-proven), risky-3 ENTERs at
tier qty (recency clamp is ribbon-scoped and does not flatten it), risky-1 at full-send
min-size. Strike routing: `STRATEGY_STRIKE_TIERS` prices these entries ATM-class
(PROBE table) because the OTM cell is MEASURED FAILING (C29) — same precedented mechanism
as probe/ladder/full-send. Exit = the Safe-2 armed ATM cell (-8%/+30%/sell 80%/fixed),
per-arm exit_patch overlays on top by existing design.
- Kill (frozen): n≥10 risky-3 fills or 10 sessions, cohort net real-fill P&L < 0 → revert.
- Revert (one line): `build_shared_signal.RUN_VWAP_RECLAIM_FB = False`.
- Guards: `test_vwap_reclaim_fleet_extension_2026_08_04.py` 10/10 (divergence on a
  real-shaped signal, live strike-routing knob, exit port, producer kill, emission).

**Caught and fixed while shipping it (C7/L241 class): the FIX2 vwap_continuation fleet
emission has been IMPORT-DEAD since 2026-06-25.** `fleet_market._lazy_imports` did
`from filters import BarContext` off a `backtest/lib` path entry, but `filters.py` opens
with a package-relative import — permanent ImportError, swallowed by the fail-safe
`except`, `vwap_strategy_block` returned None every tick. Evidence: 0 vwap rows in ANY
fleet arm's 3,865-row ledger. Fixed to package imports (`lib.filters`, `lib.watchers.*`);
`test_lazy_imports_actually_resolve` RED-proofs it (verified failing on the pre-fix
spelling live). Consequence: vwap_continuation now goes genuinely live for the fleet for
the first time, under its existing registry note/caveats and its own `RUN_VWAP=False`
revert.

**The weekly instrument** — `Gamma_RiskyDivergenceWeekly` (Sun 17:00 ET):
`full_send_vs_gated.py --weekly` writes `analysis/fleet-weekly/risky-divergence-<date>`
with the standing headline "risky-3 took N trades the safes did not; that cohort paid $X"
(extra_exec-LIST-aware core counting per L244; real FIFO P&L via the extracted
`fleet/fills_fifo.py` single implementation; weekday-window guard — a stray Saturday
2026-08-01 ledger row was silently evicting a real session). Guards 3/3; task registered,
State=Ready, NextRun Sun 08/09 17:00 ET.

## 6. Open findings for other owners (not this lane's scope)

1. **After-hours `bollinger_squeeze PLACED` rows**: 10 core-safe extra_exec rows stamped
   2026-07-30 18:49–19:41 ET claim action=PLACED on expired 0DTE contracts. Needs eyes
   (FreeManager-RED era? replay contamination?). Surfaced by the L244-correct counter.
2. **Parallel-lane test pins**: 5 fleet tests RED against the in-flight
   ATM-TIER-EXTENSION-2K-10K table edit (`test_risky1_lane_composition_check` ×2,
   `test_full_send_arm` ATM pin, `test_floor_rescue` ×2) — they assert the OLD $2K
   boundary; owned by task #73's lane.
3. **recency-RED clamp** is currently the binding sizing constraint fleet-wide
   (12→5/8→3); if J wants risky-3's qty edge expressed while RED, that is a policy call,
   not a bug.

_Sources: per-arm `decisions.jsonl` + `core-decisions.jsonl` + `fills-ledger.jsonl`
(FIFO), `fleet_arm_replay` population layer on `spy_5m_2026-05-19_2026-08-03.csv`.
Prereg: `analysis/recommendations/fleet-vwap-reclaim-extension-prereg-2026-08-04.json`._
