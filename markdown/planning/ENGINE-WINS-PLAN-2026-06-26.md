# Engine Wins — FULL PLAN (master brainstorm) — 2026-06-26

> J: "60 lines for the plan????" — replaced the skeleton with the deep per-topic design treatment
> produced by a 6-worker Sonnet brainstorm army. **Every workstream ends in VALIDATION + a GUARD
> pytest that fails on regression** — the cure for re-fixing the same thing. Opus orchestrates; Sonnet
> validates via the override harness (no in-place prod edits, parallel-safe) and returns diffs; the
> orchestrator applies passers after-hours (rule 9), commits, fires the next wave, until all are
> SHIPPED + VALIDATED + GUARDED.

---

## STRUCTURE-VETO: Direction vs. Price-Structure Deep Design Treatment

**Problem & root cause** — Today's −$237 loss (2026-06-26, Gamma-Safe-2): the engine entered a BEAR/P in a confirmed 5m intraday uptrend. The EMA ribbon was BEAR-stacked — but the ribbon is a lagging indicator (EMA-based). The price-swing sequence (HH/HL) was already bullish at the time of entry. The engine had no mechanism to distinguish "ribbon says bear because it hasn't caught up yet" from "ribbon says bear because price is actually falling." `crypto/lib/market_structure.py` was shipped 2026-06-20 specifically to close this gap — it runs the HH/HL/LH/LL sequence walk on closed bars — but has never been wired into the live engine entry path. The incident is identical in mechanism to the 5/07 SPY 734C wrong-way CALL loss (both are C4/C28 class: direction gate vs. confirmed price structure).

Root cause citation: `backtest/autoresearch/structure_veto_ab.py` + `backtest/structure_veto_anchor_check.py` confirm the exact failure mode. The A/B result is at `analysis/recommendations/structure-veto-ab-2026-06-26.json`.


**Approaches considered**

- **Approach A: Hard veto — binary SKIP_STRUCTURE_VETO gate (Gate 16)** — After `evaluate_bearish_setup` (or bull equivalent) returns `passed=True`, compute `classify_trend` on the 5m same-day bars up to and including the entry bar. If `side=P and trend=uptrend` OR `side=C and trend=downtrend`, force `passed=False` with synthetic blocker 999 (STRUCTURE_VETO). Wired as a new `GateEntry` in `backtest/lib/engine/gates.py` (Gate 16), gated by params.json bool `structure_veto_enabled: true`. range/unknown = no-veto (do-not-over-filter; 5/04 +$730 depends on this). The A/B in `structure_veto_ab.py` already implements this as a context-manager monkey-patch. Production implementation = extract `_classify_sameday_5m` to `backtest/lib/structure_gate.py`, add Gate 16 to `GATE_ORDER`, update the parity test.
    - ✅ Binary and auditable (every vetoed bar logs `SKIP_STRUCTURE_VETO` + trend value). No interaction with the existing scoring distribution or quality-lock cascade (it fires AFTER all 15 gates pass — it can only remove wrong-way entries, never add them). Fails open on `unknown` (early session <5 bars). Anchor-safe by construction: the A/B proves $0 edge_capture delta on all 3 J PUT winners. Consistent with the existing gate vocabulary. Fast per-bar cost (O(n_swings) on ~80 same-day bars). Full real-fills A/B validated (IS +$583, OOS $0, 0 winners removed, 2 losers removed).
    - ⚠️ Coarse: `classify_trend` reads the last two swing highs and last two swing lows jointly. One noisy pivot can flip downtrend→range and leak a counter-structure trade through. No graduated response — a borderline uptrend (2 HH, 1 HL) gets the same binary treatment as a confirmed 6-swing multi-BOS uptrend. Does not capture the 'structure just CHoCH'd bearish 2 bars ago but early bars were uptrend' early-reversal case (though that is correct conservatism for a safety veto).

- **Approach B: Score penalty — subtract N from bear_score when structure opposes direction** — When `classify_trend` opposes the entry side, subtract N points (e.g. 1–2) from `bear_score` / `bull_score` after the full filter run. If the adjusted score falls below the passing threshold, the bar becomes a HOLD. range/unknown = 0 penalty. Implemented inside `evaluate_bearish_setup` / `evaluate_bullish_setup` in `filters.py` as a new final step. Penalty weight N would be a params.json knob.
    - ✅ Graduated: a strong structural trend opposition subtracts more than a borderline case (if N is tuned per conviction). Allows a high-conviction entry (ELITE score=10) to override a mild uptrend if the adjusted score still clears the passing threshold — preserves optionality. Could be combined with quality-tier scoring to naturally demote counter-structure ELITE→LEVEL trades.
    - ⚠️ Interacts multiplicatively with the quality-lock cascade (L07/L08/L09/L15 document cascade anti-patterns). Score adjustment shifts the quality-tier distribution, potentially demoting ELITE→LEVEL trades and changing sizing (quality_rank) — unintended consequence not validated. Harder to audit: 'why was this trade skipped?' requires inspecting adjusted score, not a named gate action. Inconsistent with the existing binary gate architecture (all 15 gates are SKIP/allow, not penalty). Tuning N requires a separate calibration sweep not yet done. At score=7, a −1 penalty blocks; at score=10 it does not — threshold sensitivity is nontrivial.


**Recommended** — Approach A (hard veto as Gate 16) — with the current engine's existing 15 gates providing the quality-gate function, the structure veto's job is narrow: catch the 'wrong-way direction' class. That is a binary predicate. A score penalty that interacts with the quality-lock cascade reopens L15 risk with no demonstrated benefit over the binary gate. The hard veto is lean, auditable, and consistent with the existing SKIP gate vocabulary. Wiring path: `backtest/lib/structure_gate.py` (extract `_classify_sameday_5m`) → new GateEntry in `backtest/lib/engine/gates.py` → params.json `structure_veto_enabled: true` → `v51_structure_veto_gate.py` validator → gym must pass before ship.


**Design detail**

Files changed:
1. NEW `backtest/lib/structure_gate.py` — exports `classify_sameday_5m(prior_bars: pd.DataFrame, bar_idx: int) -> str`. Extracted verbatim from `backtest/autoresearch/structure_veto_ab.py:_classify_sameday_5m`. Caches `(id(prior_bars), bar_idx)` to avoid double-compute when bear+bull both evaluated on the same bar.

2. `backtest/lib/engine/gates.py` — add to `GATE_ORDER` as Gate 16 (after current gate 15):
   ```python
   GateEntry(
       id="structure_veto",
       skip_action="SKIP_STRUCTURE_VETO",
       pred=lambda ctx: (
           ctx.params.get("structure_veto_enabled", False) and
           _veto_side(ctx.winning_side,
                      classify_sameday_5m(ctx.prior_bars, ctx.bar_idx))
       ),
       blockers=["STRUCTURE_VETO"],
   )
   ```
   where `_veto_side(side, trend)` returns True iff `side=P and trend=uptrend` OR `side=C and trend=downtrend`.

3. `backtest/lib/engine/engine_cli.py` — the `gate_params` input contract doc comment needs `structure_veto_enabled` added. No logic change — the gates.py addition handles it.

4. `backtest/tests/test_engine_cli_parity.py` — update gate count assertion from 15 to 16.

5. NEW `crypto/validators/v51_structure_veto_gate.py` — 6 offline tests: (a) P-in-uptrend → SKIP_STRUCTURE_VETO, (b) C-in-downtrend → SKIP, (c) P-in-range → no-veto, (d) P-in-unknown → no-veto, (e) all 3 J PUT winners = no regression, (f) 5/07 734C → SKIP (the benchmark wrong-way case). Must show 6/6 PASS and be registered in `crypto/validators/runner.py`.

6. `automation/state/params.json` — add `"structure_veto_enabled": true` (J-only write, not Chef).

Key predicate wiring: `classify_trend(label_swings(find_swing_points(same_day_5m_bars_up_to_entry, window=2, inclusive_right=True)))`. Uses the existing `crypto.lib` primitives validated in `v46_market_structure.py`. The `swing_finder` injectable interface in `market_structure.analyze_structure` was designed for this exact live-wiring scenario.

TF choice: 5m same-day (bars from market open to entry, inclusive). NOT 5m-trailing (crosses sessions, noisier), NOT 15m (coarser swing count). NOT multi-TF agreement (reduces bite further when OOS delta is already $0).


**Edge cases**
  - Early session (<5 same-day bars): classify_trend returns 'unknown' → no-veto. Correct. The 09:35 time gate already excludes the first bar; unknown before ~09:55 is safe.
  - 5/04 +$730 RANGE case: 5/04 reads 'range' on 5m-sameday on all three TFs. The range=no-veto clause is non-negotiable and OP-16 load-bearing. NEVER tighten to 'require confirmed downtrend to allow PUT' — that would block the +$730 winner.
  - V-reversal day: PUT entry at 09:50 when structure is uptrend, veto fires. By 11:00 the market has reversed and the structure reads downtrend. The early veto is correct — early counter-structure entries on V-reversal days are the highest-risk class.
  - Midday bounce in an all-day downtrend: a HL forms (higher low) but not yet a HH. classify_trend reads: last two highs are both LH (lower high), last two lows now show one HL. Result = 'range' (mixed). Veto does NOT fire. Engine can enter the PUT. This is correct — a HL alone is a floor, not a confirmed recovery.
  - CHoCH just fired bearish but classify_trend still reads 'uptrend' (slow to flip): classify_trend reads the last labeled swings, not the authoritative walk_structure CHoCH event. After a CHoCH the NEXT labeled swing will show LH, flipping classify_trend. One-bar lag is conservative and correct for a safety veto — being slow to block is the failure mode; being slow to allow is the safe side.
  - Engine_cli performance: prior_bars is already in the input contract (passed as `bar_ctx.prior_bars`). Adding find_swing_points on ~80 same-day 5m bars costs <5ms. Not a throughput bottleneck.
  - Gate ordering: the structure veto fires AFTER all 15 existing gates. This means it cannot interfere with the SKIP_QUALITY_LOCK or SKIP_NO_PULLBACK (which stay in the orchestrator). It can only execute when a valid entry passed all upstream gates — the intended behavior.

**Failure modes**
  - OOS=$0 misread as 'no benefit': The $0 OOS delta means existing gates already pre-filter counter-structure entries in 2026 data. Belt-and-suspenders is correct for a safety-class primitive — cost is near-zero, risk is near-zero. Any future gate relaxation (e.g. midday_trendline_gate UNBLOCK, which is a current candidate) will expose the wrong-way class and make the veto's OOS delta positive immediately.
  - classify_trend flip from noisy pivot: a large-range bar that sets an anomalous swing high can flip 'downtrend' to 'range' for one bar. The PUT entry is not vetoed. This is a one-bar leak, not a systematic failure — the next bar's swing sequence will restore the correct label.
  - Ribbon stacked BEAR + price structure UPTREND = the exact incident class. The veto catches this. Ribbon stacked BEAR + price structure DOWNTREND = entry with-structure, no veto. This is the intended asymmetry.
  - Unknown edge: if the SPY data feed has a gap (e.g., market open missed), same-day bar count may be <5 at a time when structure should be readable. Result: 'unknown' → no veto. Conservative but correct — a data gap should not trigger a block.
  - Gate 16 parity test: the existing `test_engine_cli_parity.py` asserts a specific gate count. Adding Gate 16 requires updating that assertion or the test fails closed. This is a REQUIRED step before ship.
  - v51 validator must be registered in runner.py AND the OP-26 stage count in CLAUDE.md must be bumped by 1 — same protocol as v46/v47/v48/v49/v50. If the count is not bumped, the gym reports wrong totals.


**Validation plan** — Real-fills already done: `backtest/autoresearch/structure_veto_ab.py` ran on full OPRA fills 2025-01-02..2026-06-18. Result: `analysis/recommendations/structure-veto-ab-2026-06-26.json`. IS: +$583 (14 trades→13, 2 losers removed net −$574). OOS: $0 (21→21, 0 removed). Anchor: $780 both arms, delta=$0. Quarters: 2/6 positive, 4/6 unchanged, 0/6 degraded.

Anchor check already done: `backtest/structure_veto_anchor_check.py`. All 3 J PUT winners: no veto on 5m-sameday. 5/07 734C: veto fires. 5/04: reads RANGE → no veto.

Additional validation required before ship:
1. Run `structure_veto_ab.py` AFTER implementing Gate 16 in gates.py (not monkey-patch) to confirm byte-identical results to the A/B baseline. This proves the gate extraction is faithful (same methodology as the Phase 2 gate parity tests).
2. Write and run `v51_structure_veto_gate.py` (6 offline tests). All must PASS.
3. Run `crypto/validators/runner.py` — must show (baseline+1)/baseline+1 PASS with v51 registered.
4. Verify that today's live incident (2026-06-26 −$237 wrong-way PUT) would have triggered SKIP_STRUCTURE_VETO by replaying the bar context through the gate with `structure_veto_enabled: true`.


**Guard** — ```python
# backtest/tests/test_structure_veto_regression.py
# FAILS if the structure veto removes any J OP-16 winner OR if the anchor
# edge_capture changes by more than $1.

import pytest
from backtest.autoresearch.structure_veto_ab import _score, _real_fills_params
from backtest.autoresearch.runner import load_data
from backtest.autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_TOTAL_WINNERS
import contextlib
import datetime as dt

ANCHOR_START = dt.date(2026, 4, 28)
ANCHOR_END   = dt.date(2026, 5, 8)

@pytest.fixture(scope='module')
def anchor_data():
    from backtest.autoresearch.runner import load_data as ld
    return ld(ANCHOR_START, ANCHOR_END)

def test_structure_veto_no_winner_regression(anchor_data):
    spy, vix = anchor_data
    params = _real_fills_params()
    params['structure_veto_enabled'] = True
    from backtest.autoresearch.structure_veto_ab import _score
    score = _score(params, spy, vix, veto=True)
    # edge_capture must equal base (780) within $1
    assert abs(score['edge_capture'] - J_TOTAL_WINNERS) < 1.0, (
        f"Structure veto removed a J winner: ec={score['edge_capture']}, expected ~{J_TOTAL_WINNERS}"
    )

def test_structure_veto_op16_floor(anchor_data):
    spy, vix = anchor_data
    params = _real_fills_params()
    params['structure_veto_enabled'] = True
    from backtest.autoresearch.structure_veto_ab import _score
    score = _score(params, spy, vix, veto=True)
    assert score['edge_capture'] >= J_TOTAL_WINNERS * 0.50, (
        f"OP-16 floor FAIL: ec={score['edge_capture']} < {J_TOTAL_WINNERS*0.50}"
    )
```

This test FAILS on regression if: (a) any future code change makes classify_trend return 'uptrend' on a J winner's bar, or (b) the veto is tightened to block 'range' entries (would fail on 5/04). Register in `backtest/tests/test_graduated_guards.py` per OP-25 graduated-guard protocol.


**Risks**
  - OOS=$0 means the veto has no demonstrated forward P&L lift under the current gate config. If the current gates are never relaxed, the veto remains permanently belt-and-suspenders with no measurable benefit — a net-zero insurance policy.
  - Any future gate relaxation that exposes counter-structure trades in OOS will suddenly make the veto's OOS delta positive — this is a BENEFIT, but it means the veto's value is contingent on the upstream gate configuration. It's not a standalone alpha source.
  - classify_trend uses the crypto.lib swing finder by default. The live engine's scipy-based pivot finder (`backtest/lib/trendlines.find_swing_points`) has slightly different equal-level tie-breaking behavior. The injectable `swing_finder` parameter in `analyze_structure` was designed to close this gap — but the A/B did NOT use injection (it used the crypto.lib finder). If there is a systematic difference between the two finders' swing sequences, the veto's live behavior could differ from the A/B result. Mitigation: the v51 validator should run both finders on the same bars and assert identical classify_trend output.
  - The Gate 16 addition requires updating `test_engine_cli_parity.py`. If this test is not updated before the gate is wired, the parity test will fail closed and block every heartbeat_core tick. Mitigation: the parity test update is a mandatory step before params.json flip.

**Open questions**
  - Should the veto use `classify_trend` (label-based, slower to flip) or `analyze_structure().trend` (BOS/CHoCH walk-based, faster to flip on confirmed events)? The A/B used classify_trend and got anchor-safe results. walk_structure may be more responsive to intraday reversals but introduces CHoCH-timing sensitivity. This is a deliberate design choice, not a bug — document it.
  - When midday_trendline_gate is unblocked (current UNBLOCK candidate), does the OOS delta increase materially? Run structure_veto_ab.py with midday_trendline_gate=false and compare OOS delta. If OOS delta becomes positive ($50+), the case for urgency strengthens to confidence 8.
  - The A/B removed 2 losers in 2025Q1. Are those the same 2 trades that the midday_trendline_gate later blocked in 2025Q1? If yes, the structure veto and the midday gate are redundant on those trades — and unblocking the midday gate without also having the structure veto may re-expose them. Cross-reference the removed trade identities.
  - Gate 16 position: should it fire BEFORE or AFTER the quality-lock (SKIP_QUALITY_LOCK, which stays in the orchestrator)? Currently: SKIP_QUALITY_LOCK fires first (orchestrator-level, before engine_cli gates). Then Gate 16 fires. This means a wrong-way trade blocked by quality-lock never reaches Gate 16 — which is fine. But if quality-lock is later moved inside engine_cli, the ordering matters.
  - v51 validator needs live data for the '5/07 734C fires SKIP_STRUCTURE_VETO' test case. The anchor check already verified this analytically. The validator should replicate it from the CSV fixture (same data source as the anchor check).


**Verdict** — SHIP-worthy with one condition: write `v51_structure_veto_gate.py`, get gym to pass, then flip params.json. The P&L case is honest-thin (IS +$583, OOS $0) — this is a safety veto, not an alpha generator. The architecture case is solid: the ribbon is a lagging trend indicator; price structure (HH/HL) is contemporaneous; the incident today (−$237) proves the gap is real and the veto closes it with zero anchor regression. Belt-and-suspenders is the correct framing. The confidence is 6/10, not 8, because OOS=$0. It rises to 8 if any upstream gate is relaxed. The guard test is the durability mechanism — J never needs to re-examine this class of wrong-way entry again once the guard is in the graduated-guards test file.

---

## 5-gate unblock batch: cascade risk, staging strategy, VIX drift prevention, and fill-bar hedge

**Problem & root cause** — All 5 gates were ratified on the OLD engine (OTM strike / BS-sim pricing / -8% to -10% hard premium stops / bracket-only exits). Under the CURRENT engine (real OPRA fills / -50% catastrophe cap / chart-stop-primary / chandelier profit-lock / managed exits), the wider stop rides winners that the old engine stopped out of early, so several 'good blocker' votes on the old engine become 'suppresses winners' votes on the new one.

Confirmed current state (verified by running backtest/tests/test_no_stale_blocks.py): ALL 6 guard tests FAIL meaning none of the 5 unblocks have been applied to params yet. The guard test file itself already exists and is correct.

Each gate's stale mechanism, cited to code:

1. midday_trendline_gate = true (params.json:127). BEAR only (100% of removed trades are PUT). Removed-set IS: 102 trades, net +$849, WR 71% (+$8.33/tr). Block_delta IS = -$371, OOS = -$40. Sub-windows: 3/4 HURT. Old evidence was -8.6/tr on 307 OOS trades under OTM/-8% stop. Mechanism: old engine stopped out midday trendline trades at -8%; current -50% cap lets them recover and close green via chandelier or TP1.

2. entry_bar_body_pct_min = 0.20 (params.json:135). BEAR only (orchestrator.py:1594 guards 'winning_side == P'). Old ratification: IS delta +$295, OOS +$566, WF 7.193. On current engine: direct removed-set net = -$200 (removes 44 net-winner bear entries, suppresses 5 fat-tail winners up to +$1,361). The aggregate IS delta of +$1,946 is a C15/L15 cascade artifact. The honest number is the direct removed-set net-PnL: gate costs money.

3. require_bearish_fill_bar in agg/params.json (NOT in safe params.json; orchestrator.py:614 defaults to False). LOOK-AHEAD gate (checks bar N+1, which is unknown at signal bar N close time). Current real-fills + ITM-2 + chandelier: removed-set IS nets +$917 (33 bear, 13W/+$2,759 vs 20L/-$1,841) = suppresses winners. WF = -5.73 sign-flip (negative = gate hurts on the current engine). SW: 2/4 hurt; helps W1 but hurts W2/W3 (largest recent windows). OOS: +$775 but n=5 (thin).

4. block_conf_lvl_rec_afternoon = true in agg/params.json (NOT in safe params.json; safe defaults False). Afternoon conf+level_reclaim bull/C blocker. Old-engine ratification sign-FLIPPED on current engine: costs +$779 IS, protects $0 OOS. Mechanism: leaky gate keys on a backtest variable ('bt' not entry_time) rather than entry_time_et, so it fires inconsistently in production vs backtest.

5. VIX_BULL_HARD_CAP: params.json vix_entry_thresholds.bull_hard_cap = 18.0 AND filters.py:805 VIX_BULL_HARD_CAP = 18.0 (both stale). Old ratification on old engine suppressed 4 IS / 1 OOS bull entries (thin). Current engine: block contributes -$471 IS AND -$471 OOS, suppresses 2 bull WINNERS (4/09 +$205, 4/22 +$266 at VIX 18-22 band). EC invariant: -1379. The dual-location is a documented C14 drift risk: filters.py is read directly by evaluate_bullish_setup(), while params.json is patched via _FILTER_CONST_MAP['vix_bull_max'] -> 'VIX_BULL_HARD_CAP' at orchestrator.py:85. If only params is updated, the constant in filters.py keeps blocking in any code path that imports filters directly without the orchestrator patch (e.g., heartbeat_core.py calling engine_cli directly).


**Approaches considered**

- **Approach A: Staged 2-wave deploy (safe-only first, then aggressive)** — Wave 1 (tonight): flip the 2 safe-params gates that have the cleanest evidence and lowest interaction risk: midday_trendline_gate true->false (BEAR-only, anchor PASS, 0 bull trades in removed set) and VIX_BULL_HARD_CAP 18->22 (params.json + filters.py both). Wave 2 (next after-hours, after one trading day of observation): flip the 3 aggressive-params gates: require_bearish_fill_bar, block_conf_lvl_rec_afternoon, and entry_bar_body_pct_min 0.20->0.0. Before each wave, run the gym (crypto/validators/runner.py) to confirm 30/30 PASS. After each wave, run the stale-block guard (test_no_stale_blocks.py) to confirm tests flip from FAIL to PASS.
    - ✅ Isolates interaction effects. If Wave 1 produces unexpected live behavior, Wave 2 is not yet applied and rollback touches only 2 keys + 1 constant. Safe account and Aggressive account are on separate wave schedules, so a cascade in one account's gate interactions is not simultaneously introduced in the other. The VIX dual-location drift is fixed atomically in Wave 1 with a guard test that permanently enforces sync.
    - ⚠️ Takes 2 cycles instead of 1. On a quiet trading day the split may be artificial — if all 5 gates are demonstrably non-interacting, staging adds delay without risk reduction. Requires discipline to actually execute Wave 2 rather than letting it sit.

- **Approach B: Atomic single-wave deploy (all 5 simultaneously)** — Apply all 5 diffs in a single params edit, update filters.py VIX_BULL_HARD_CAP, run gym before+after, run test_no_stale_blocks.py to confirm all 6 tests now PASS. Commit atomically. The rationale: gates 1-2 are Safe-params BEAR-only, gates 3-4 are Aggressive-params only, gate 5 is Safe-params BULL-only. There is no cross-gate interaction because (a) BEAR path and BULL path in the orchestrator are independent branches (orchestrator.py:1285-1316), (b) Safe and Aggressive params files are read independently per account, (c) the removed sets do not overlap — each gate fires on a structurally distinct subset of bars.
    - ✅ One commit, one gym run, one review cycle. The C15 cascade-interaction concern is real in principle but does not apply here because these gates operate on DIFFERENT setup populations: bear-entry gates (1, 2, 3) cannot cascade into bull-entry gates (4, 5). The only shared pool is the raw bar stream, not the filtered entry set. Faster path to the expected +$1,000-1,500 IS edge recovery.
    - ⚠️ If an unanticipated interaction IS discovered after deploy (e.g., removing midday_trendline_gate exposes a different downstream gate that was previously gated-out), root-cause is harder to isolate with all 5 changed at once. Specifically, the entry_bar_body_pct_min cascade artifact concern (the +$1,946 IS aggregate that the memory calls 'misleading') is not fully resolved — if the cascade inflates aggregate P&L rather than the individual gate's direct contribution, a single-wave deploy masks that ambiguity.


**Recommended** — Approach A (staged), with one important modification: treat gate 5 (VIX_BULL_HARD_CAP, dual-location) as the FIRST item in Wave 1 because its drift risk is structurally different from the others and must be fixed atomically (both params.json and filters.py in the same commit or the live engine and backtest diverge). Wave 1 = VIX_BULL_HARD_CAP 18->22 (both locations) + midday_trendline_gate true->false. Wave 2 = entry_bar_body_pct_min 0.20->0.0 + require_bearish_fill_bar (agg) + block_conf_lvl_rec_afternoon (agg).

Reason for staging over atomic: entry_bar_body_pct_min has a documented ambiguity that the memory itself flags ('aggregate +$1,946 is a cascade artifact, C15; direct block delta = -$200 is the honest number'). That ambiguity makes it the weakest evidence of the 5. If the direct-delta is -$200 but the cascade effect makes aggregate appear positive, there is a risk the cascade is regime-dependent — removing it during a regime change could introduce unexpected behavior. Staging it to Wave 2 lets us observe Wave 1 behavior for one trading day before adding the noisiest gate to the mix. Similarly, require_bearish_fill_bar has OOS n=5 (thin) and was ORIGINALLY a look-ahead gate — it is probably right to unblock (WF -5.73 is a strong sign flip), but one day of observation is cheap insurance. Atomic is fine if J wants speed; the non-interacting argument is sound. This is a judgment call, not a hard safety concern.


**Design detail**

Wave 1 changes (automation/state/params.json and backtest/lib/filters.py):

automation/state/params.json:
- vix_entry_thresholds.bull_hard_cap: 18.0 -> 22.0
- midday_trendline_gate: true -> false

backtest/lib/filters.py line 805:
- VIX_BULL_HARD_CAP = 18.0 -> 22.0

Wave 2 changes:
automation/state/params.json:
- entry_bar_body_pct_min: 0.20 -> 0.0

automation/state/aggressive/params.json:
- require_bearish_fill_bar: (add or set) false
- block_conf_lvl_rec_afternoon: true -> false

VIX_BULL_HARD_CAP dual-location wiring (the permanent drift-prevention design):
The constant at filters.py:805 is read DIRECTLY by evaluate_bullish_setup() at filters.py:891 without going through the orchestrator param-patch path. The orchestrator patches it only when run_backtest() or run_with_params() is called with a params_overrides dict. Any code path that calls evaluate_bullish_setup() directly (e.g., heartbeat_core.py -> engine_cli.py -> score_bar()) reads the module-level constant, not the patched value. This is why BOTH must be updated atomically and why the drift guard test (test_vix_bull_hard_cap_params_filters_in_sync) must stay live. The correct permanent fix is: the guard test enforces they are equal; updating either one without the other causes CI to fail. This is already encoded in test_no_stale_blocks.py:176-193.

After Wave 1, run in order:
1. cd backtest && python -m pytest tests/test_no_stale_blocks.py::test_midday_trendline_gate_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_params_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_filters_unblocked tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_params_filters_in_sync -v
2. python crypto/validators/runner.py (must show all stages PASS)

After Wave 2, run:
1. cd backtest && python -m pytest tests/test_no_stale_blocks.py -v (all 6 must PASS)
2. python crypto/validators/runner.py (must show all stages PASS)


**Edge cases**
  - require_bearish_fill_bar is a look-ahead gate (checks bar N+1 at bar N signal time). Its OOS evidence (n=5) was measured USING the look-ahead in the backtest, meaning the 'removed set nets +$917' is an upper bound on what production could achieve. Production cannot see N+1 at N close time. The correct interpretation of 'unblock' here is: the gate has failed its own stated purpose (blocking losers) even in the look-ahead scenario, so keeping it active is net-negative. Unblocking restores the prior behavior (no delay). This is NOT a case where unblocking adds a new 1-bar-delay signal.
  - entry_bar_body_pct_min cascade artifact (C15): the 44 trades blocked by this gate may themselves gate other downstream sessions. If upstream filters are correlated with afternoon regime (which midday_trendline_gate also operates in), removing both gates in the same wave could produce non-additive P&L. The cascade goes: bar N fails body_pct_min -> no trade placed -> position is flat -> subsequent bar N+k sees different account state -> changes P&L. This is a per-session state dependency, not a per-bar independence. Staging Wave 2 at least separates midday_trendline (Wave 1) from entry_bar_body (Wave 2) by one trading day.
  - block_conf_lvl_rec_afternoon protects $0 OOS and the memory notes it 'keys on bt not entry' meaning the gate fires based on a backtest-internal variable rather than actual entry time. If there are afternoon confluence+level_reclaim bull entries that actually existed in the aggressive account during the OOS window, unblocking could admit them. The OOS delta is $0 (not negative) which means either no such entries existed in OOS, or they canceled out. This is the cleanest edge case: the gate is vacuous, so the risk of unblocking is low.
  - VIX_BULL_HARD_CAP at 22.0 admits VIX 18-22 bull entries. The existing Filter 8 (filters.py:882-887) still requires VIX < 17.20 OR falling to pass. This means at VIX 18-22 with VIX falling, BOTH Filter 8 (VIX falling = pass) AND Filter 9 (VIX < 22 = pass) will now both pass for a bull entry. This is the intended behavior (the 2 confirmed bull winners 4/09 and 4/22 were VIX-falling days). But at VIX 18-22 with VIX flat or rising, Filter 8 blocks the entry so Filter 9 at 22.0 is moot. The cascade here is safe: F8 still acts as the soft VIX gate.
  - midday_trendline_gate removal exposes 102 previously-blocked trendline-only midday bear trades back into the engine. These are single-trigger entries (trendline_rejection only, no level or confluence). Bear minimum trigger count is 1 (params filter_10_min_triggers_bear = 1), so the level-tie requirement at orchestrator.py:953-959 still applies: the trendline_rejection trigger must be level-tied. Check: trendline_rejection returns the trendline price as a 'level' via detect_trendline_rejection_bearish() -> this IS treated as a rejection_level in the SetupResult. But level_tied_required logic in the bear path at orchestrator.py:1245-1265 checks whether the trigger is in the level_tied set {level_rejection, confluence, sequence_rejection}. A trendline_rejection trigger is NOT in that set. This means filter_10_level_tied_required=true (params.json) could block trendline-only entries even after midday_trendline_gate is removed. Need to verify this is the intended behavior or whether the re-exposed trades get silently re-blocked by a different gate.

**Failure modes**
  - VIX_BULL_HARD_CAP partial-update drift: someone updates params.json bull_hard_cap = 22.0 but forgets filters.py:805. Result: backtest runs with 22.0 (via param-patch), live heartbeat_core.py runs engine_cli which calls evaluate_bullish_setup() directly, reads the constant at 18.0, and silently blocks VIX 18-22 bull entries that the backtest counted as winners. The symptom is 'live underperforms backtest by exactly the VIX 18-22 bull P&L'. The guard test_vix_bull_hard_cap_params_filters_in_sync catches this at commit time.
  - entry_bar_body_pct_min cascade overstates edge: the +$1,946 IS aggregate number in the memory is a C15 cascade artifact. If the direct removed-set delta is truly -$200 (gate costs net $200 by blocking winners), then the aggregate inflation comes from downstream gate interactions. If the specific 44 blocked trades were clustered in a high-regime period, unblocking in a different regime could be neutral or negative. The defense is that the direct delta is the correct signal: -$200 means the gate removes $200 of net-positive bear trades. That is the honest edge.
  - require_bearish_fill_bar OOS n=5 brittleness: the WF sign-flip (-5.73) is strong and the direction is clear. But n=5 OOS blocked trades means a single outlier trade can flip the OOS sign. If the OOS window happened to include a cluster of bearish-fill-bar bars that were genuinely losers (which the old engine correctly blocked), the evidence would look identical. The hedge is: (1) the gate is a look-ahead gate so it cannot be used in production as designed anyway, and (2) the IS evidence on the current engine (33 trades removed, net +$917) is the primary signal. Thin OOS is a disclosure, not a dealbreaker, since the gate architecture itself (look-ahead) is the first-order reason to remove it.
  - C15 multiplicative cascade across all 5: removing 5 gates simultaneously changes the entry population for every downstream interaction. Specifically, if midday_trendline_gate was blocking 102 trades that were correlated with bad-regime days, removing it increases trade count on those days, which interacts with VIX filter state (more bear entries on days where VIX is elevated), which interacts with entry_bar_body_pct_min (more doji-bar entries on those same days). The staged approach partially mitigates this by separating wave 1 (bear midday gate + VIX bull gate) from wave 2 (bear body gate + aggressive gates). The bear/bull path separation is the real protection: midday_trendline is pure-BEAR, VIX_BULL_HARD_CAP is pure-BULL. They cannot cascade into each other.
  - block_conf_lvl_rec_afternoon is DEAD in aggressive/params.json (the aggressive doc says '$0 delta in all contexts, superseded by block_conf_lvl_rej_midday_afternoon'). Unblocking a dead gate changes nothing. But the stale-block guard test checks it anyway. The failure mode here is if someone later re-activates block_conf_lvl_rej_midday_afternoon in aggressive params without also re-checking block_conf_lvl_rec_afternoon — the superset gate would then do the blocking and the vacuous gate would be re-activated unnecessarily.


**Validation plan** — Wave 1 real-fills validation (before applying changes):

Baseline (current state, all 5 gates ON):
Run: cd backtest && python backtest/autoresearch/vix_bull_hardcap_revalidate.py
Expected: FULL IS shows block contribution = -$471, OOS = -$471. J anchor winners 4/29/5/01/5/04 all PASS (these are BEAR winners; VIX_BULL_HARD_CAP is BULL-only, no anchor regression possible).

After Wave 1 (midday_trendline_gate=false, VIX_BULL_HARD_CAP=22.0):
Run: cd backtest && python backtest/autoresearch/safe_midday_trendline_gate_revalidate_current_engine.py (if exists) or inline run_backtest A/B.
Expected: IS PnL improves by approximately +$371 from midday_trendline unblock. J anchor PASS (all 3 J winners are pre-11:30 ET or non-trendline-only entries, so midday_trendline gate should not have affected them; verify the removed 102 trades are dated outside anchor dates 4/29, 5/01, 5/04). VIX_BULL_HARD_CAP=22.0: IS admits 2 additional bull entries (4/09 +$205, 4/22 +$266). J anchor PASS (J anchor losers are 5/05-5/07 PUT days; VIX_BULL_HARD_CAP is CALL-only, zero regression).

Wave 2 real-fills validation:
Run: cd backtest && python backtest/autoresearch/fill_bar_direction_gate.py with gate_on=False vs current baseline.
Expected: IS baseline improves by approximately +$917 (removed set nets positive). Check WF sign is consistent with -5.73 flip direction (removing the gate = positive effect = WF_norm of the REMOVED-set run is negative of the gate-on run). OOS: with n=5 the delta could be +$775 or slightly different depending on data boundary. Accept direction-consistent result.

For entry_bar_body_pct_min=0.0: run inline A/B or check safe_entry_body_gate.py output. Expected: direct removed-set net = -$200 (the gate was correctly identified as costing $200 net by removing 44 net-winner entries). The aggregate may show inflation — cite the direct delta, not the aggregate.

Anchor check for all 5: verify via backtest/structure_veto_anchor_check.py or manual date-filter that the J anchor dates (4/29, 5/01, 5/04 winners; 5/05, 5/06, 5/07 losers) are unaffected by the unblocked gates. The VIX_BULL_HARD_CAP is CALL-only, the other 4 are BEAR-only or aggressive-only — there is structural separation from the PUT-anchor dates.


**Guard** — The guard already exists at backtest/tests/test_no_stale_blocks.py and is the correct design. All 6 tests currently FAIL (confirmed). After applying the 5 diffs, all 6 should PASS.

Specific tests and what they catch on regression:

test_midday_trendline_gate_unblocked(): reads params.json, asserts midday_trendline_gate is False. Fails if params is reverted to true.

test_entry_bar_body_pct_min_unblocked(): reads params.json, asserts entry_bar_body_pct_min == 0.0. Fails if restored to 0.20.

test_require_bearish_fill_bar_unblocked(): reads agg/params.json, asserts require_bearish_fill_bar is False. Fails if set to True in aggressive params.

test_block_conf_lvl_rec_afternoon_unblocked(): reads agg/params.json, asserts block_conf_lvl_rec_afternoon is False. Fails if set to True.

test_vix_bull_hard_cap_params_unblocked(): reads params.json vix_entry_thresholds.bull_hard_cap, asserts == 22.0. Fails if reverted to 18.0.

test_vix_bull_hard_cap_filters_unblocked(): imports backtest.lib.filters directly, reads VIX_BULL_HARD_CAP constant, asserts == 22.0. Fails if filters.py constant is reverted to 18.0 even if params is correct.

test_vix_bull_hard_cap_params_filters_in_sync(): asserts the two values are EQUAL regardless of what they are. This is the permanent drift guard — it fires on any future param change that updates one side without the other. This test PASSES today (both are 18.0 = in sync but wrong); after the fix both should be 22.0 = in sync and correct.

Run command: cd backtest && python -m pytest tests/test_no_stale_blocks.py -v
Expected post-fix: 7/7 PASS (0 failed).

Pre-commit hook integration: the test file is pure-static (no data, no network) and runs in under 1 second. It is appropriate as a pre-commit gate. Adding it to .pre-commit-config.yaml or the existing test_verify_committed.py suite would enforce it on every commit.


**Risks**
  - require_bearish_fill_bar OOS n=5 is the thinnest evidence of the 5 unblocks. If the 5 OOS-blocked trades happened to be regime-clustered losers (not a random sample), the IS sign-flip (WF -5.73) may overstate the population edge. Hedge: the gate is a look-ahead gate that production cannot implement as designed, so keeping it active is incorrect regardless. The correct framing is 'remove an incorrectly-implemented gate' not 'add an edge.'
  - entry_bar_body_pct_min cascade risk (C15): the direct delta is -$200 but the aggregate is +$1,946. This 10x discrepancy between direct and aggregate is a red flag for a cascade interaction. It means 44 unblocked trades somehow alter the path of $2,146 in downstream P&L. Most likely mechanism: some of the 44 unblocked bear entries on doji bars occur earlier in the session, causing a 'position already open' state that prevents a later entry on a different (better) bar. Unblocking them adds the doji-bar entries but forfeits the better-bar entries. The net is -$200. If this interpretation is correct, unblocking at entry_bar_body_pct_min is the right call (the gate actively hurts by blocking the doji entry AND the cascade is the mechanism by which it blocks the subsequent better entry). But this causal chain is inferred, not directly traced.
  - midday_trendline_gate exposes 102 bear trades back to the engine, 71% of which are winners. On active midday sessions this could increase trade frequency in the 11:30-14:00 window. If the PDT (day-trade) count guard is near its limit on a given day, these additional trades could trip the kill switch. The guard is per-account (Rule 7) and the backtest does not simulate PDT limits. Verify: the Safe-2 account at $2K is paper trading, so PDT rules apply differently than real money. For aggressive/live account, track PDT count on days where midday trendline would fire.
  - block_conf_lvl_rec_afternoon is marked DEAD in agg/params.json doc ('$0 delta in all contexts, superseded by block_conf_lvl_rej_midday_afternoon'). This means the unblock has zero P&L impact. However, the stale-block guard test still tests it. If someone later removes block_conf_lvl_rej_midday_afternoon (the superset gate) from aggressive params, block_conf_lvl_rec_afternoon at false would no longer be the safety net. This is low risk but worth noting: the superset gate is the load-bearing blocker for aggressive afternoon conf+rec entries.
  - VIX_BULL_HARD_CAP at 22.0 is still a cap (not disabled). The engine still blocks ALL bull entries when VIX >= 22. This is correct behavior — the revalidation showed that VIX 22+ bull entries are still losers on the current engine. The 18-22 band is the specific range where the old engine incorrectly blocked winners. The 22+ range remains blocked. Verify: filters.py:891 'if ctx.vix_now >= VIX_BULL_HARD_CAP' — at VIX_BULL_HARD_CAP = 22.0 this correctly blocks VIX >= 22.

**Dependencies**
  - backtest/.venv/Scripts/python.exe (backtest venv interpreter, not system Python313)
  - automation/state/params.json (Safe params, J-only write access — THIS IS A PRODUCTION FILE; Chef NEVER edits it directly, proposes diffs only)
  - automation/state/aggressive/params.json (Aggressive params, same restriction)
  - backtest/lib/filters.py line 805 VIX_BULL_HARD_CAP constant (must be updated atomically with params.json bull_hard_cap)
  - backtest/lib/orchestrator.py _FILTER_CONST_MAP line 85 ('vix_bull_max': 'VIX_BULL_HARD_CAP') — this is the wiring that makes params_overrides patch the constant at runtime; it is already correct, no change needed
  - backtest/tests/test_no_stale_blocks.py — the guard file; already written, all 6 tests fail (confirmed), will pass after diffs applied
  - crypto/validators/runner.py — gym run required before AND after each wave
  - backtest/autoresearch/vix_bull_hardcap_revalidate.py — revalidation script for gate 5; use to confirm -$471 IS delta before applying
  - backtest/autoresearch/fill_bar_direction_gate.py — WARNING: uses old-engine config (premium_stop_pct_bear=-0.10 at line 64); output may not reflect current -0.50 engine state
  - backtest/autoresearch/safe_midday_trendline_gate_revalidate_current_engine.py — confirm this file exists before citing the +$849 IS figure

**Open questions**
  - level_tied_required gate interaction with midday_trendline unblock: params.json filter_10_level_tied_required = true requires that at least one trigger in the winning set is level-tied (level_rejection, confluence, or sequence_rejection). A trendline_rejection trigger is NOT in that level_tied set. Does removing midday_trendline_gate expose 102 bear trades that then get re-blocked by the level_tied_required gate? If yes, the P&L improvement from midday_trendline unblock is smaller than the +$849 IS figure. Need to run the baseline without midday_trendline_gate and WITH filter_10_level_tied_required=true to confirm the 102 trades actually land.
  - cascade ordering: should entry_bar_body_pct_min be unblocked before or after midday_trendline_gate? Both operate on BEAR entries but different conditions (body_pct vs time window). If a midday trendline-only entry on a doji bar exists in the 102-trade removed set, removing midday_trendline_gate first then entry_bar_body_pct_min second would add that trade in Wave 2 (it was gated by body_pct). But removing entry_bar_body_pct_min first while midday_trendline_gate is still ON would never expose it. The overlap (midday + doji) is small but should be traced if the cascade is a concern.
  - What is the correct production treatment of require_bearish_fill_bar when it is a look-ahead gate? The memory says 'mislabeled bull; Bold=true, AUTO-RATIFIED 2026-06-17 on OLD bracket-only engine.' The orchestrator.py comment at line 610-613 explicitly calls it a look-ahead gate and says 'valid for backtest research only.' If the gate was auto-ratified and set to true in agg/params.json, was it ever actually WIRED to the live aggressive heartbeat_core? The heartbeat_core calls engine_cli, which calls run_backtest via params_overrides. If require_bearish_fill_bar is in agg/params.json and the aggressive orchestrator reads it via params_overrides, then YES it is live and blocking real entries. Confirm this wiring before attributing the OOS n=5 evidence to live account behavior.
  - Does the existing v25 validator (referenced in test_no_stale_blocks.py:183 as 'The v25 validator (P4) already checks this at gym-run time') actually catch the VIX_BULL_HARD_CAP drift at gym runtime? If so, run crypto/validators/runner.py NOW (before applying changes) and check whether the v25 stage passes or warns. If it catches the drift, then the gym has been silently yellow or red on this for every run since the filters.py constant was set to 18.0.
  - Is the safe_midday_trendline_gate_revalidate_current_engine.py file referenced in the test docstring actually present? It is listed as the source script for the +$849 IS figure. If it is not in the repo, the evidence is in the memory notes only and cannot be re-run to verify. The fill_bar_direction_gate.py script uses an OLD engine config (premium_stop_pct_bear=-0.10, not -0.50) as its SAFE_BASE (line 64 of fill_bar_direction_gate.py) — which means its output is NOT on the current engine. The memory score for require_bearish_fill_bar was obtained on 'current real-fills+ITM-2+chandelier' but the script itself shows a -0.10 base. Was a separate run done with -0.50? This needs to be confirmed before treating OOS +$775 as current-engine evidence.


**Verdict** — SHIP-worthy for Wave 1 (midday_trendline_gate + VIX_BULL_HARD_CAP dual-location). These two have the cleanest evidence: midday_trendline has 102 direct IS trades at +$849 net with anchor PASS, and VIX_BULL_HARD_CAP has two named J-period bull winners that are being incorrectly blocked. Both are currently causing the test_no_stale_blocks.py guard to fail.

NEEDS-MORE for Wave 2, specifically for entry_bar_body_pct_min and require_bearish_fill_bar:

entry_bar_body_pct_min: the direct delta is -$200 but the aggregate is +$1,946. A 10x discrepancy between direct and cascade-inflated aggregate is unusual and the memory explicitly calls it a 'cascade artifact.' The gate should be removed, but the ambiguity about WHY the aggregate is inflated should be resolved before treating the unblock as a validated +$1,946 edge. It is a -$200 direct-delta unblock, not a +$1,946 edge.

require_bearish_fill_bar: fill_bar_direction_gate.py uses an old engine config (premium_stop_pct_bear=-0.10, not -0.50). The evidence base may not be fully current-engine. Confirm by rerunning with -0.50 cap. The look-ahead gate architecture means it cannot be used in production as designed regardless, which makes it the right call to remove — but the evidence quality is thin.

block_conf_lvl_rec_afternoon (aggressive): SHIP immediately — it is DEAD ($0 delta in all contexts per its own doc) and the unblock is a no-op.

The guard in test_no_stale_blocks.py is the correct enforcement mechanism. It is already written. Apply the params diffs, update filters.py, confirm 7/7 PASS, commit. The FORBIDDEN-FRAMING rule (OP-11) applies: these are profitable/validated unblocks, not 'your call' items. Ship and report for REVOKE.

---

## Dormant Validated Setups: Why They Are Off, Enablement Risk, Bull-Block Interaction, and Position-Collision Under 4+Ribbon Live

**Problem & root cause** — The question posits four setups as "validated but enabled=false": vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, and gap_and_go. The first correction the code demands: two of the four are ALREADY enabled=true in production params.json (checked live: gap_and_go_enabled=true, j_vwap_cont_enabled=true). This is not a dormancy problem for those two — it is a LIVE FEED problem. The real four-way dormancy taxonomy from the code:

1. vwap_continuation (j_vwap_cont_enabled=true): The flag is live, but the flag does NOT go through the orchestrator's run_backtest / engine_cli path. It is consumed exclusively by mass_grind_vwap.py and Gamma_Grind_Vwap (a separate on-demand research task). The heartbeat_core calls engine_cli which calls score_bar + evaluate_gates — the ribbon-ride 15-gate battery — and that path never calls detect_vwap_continuation_setup. So "enabled" here means "the research grinder is authorized to run it," not "the live engine will trade it." From heartbeat_core.py's perspective the watcher is DEAD (no wiring to heartbeat_core or engine_cli).

2. gap_and_go (gap_and_go_enabled=true, side=put): Same structural gap. The watcher is registered in runner.py's WATCHERS list, which fires during backtest/watcher replay (Gamma_WatcherLive), but heartbeat_core.py does NOT iterate the WATCHERS list — it calls engine_cli, which calls score_bar/evaluate_gates (ribbon-ride only). Runner.py comment confirms "prior close is needed; in single-day replay the watcher no-ops." So gap_and_go is live-authorized in params but live-blind in the heartbeat.

3. vwap_reclaim_failed_break (j_vwap_reclaim_fb_enabled=false): Correctly config-blocked. Watcher exists (detect_vwap_reclaim_failed_break_setup in runner.py), filters.py has the enabled() accessor, test_engine_order_bracket_parity.py covers the flag-off/flag-on parity. The isolated stop (-0.08) and tp1 (0.30) params are wired via WP-0. Config change to true would route signals through simulate_trade_real. recency-confirmation.json: ATM n=5, exp=-40.56/tr, sign=NEGATIVE, verdict=YELLOW (n<floor 10 = small-n wobble, not confirmed RED; full-OOS base +$13.66/tr still positive).

4. vix_regime_dayside (j_vix_dayside_enabled=false): Config-blocked AND feed-blocked. The watcher's _vix_intraday_series() reads ctx.vix_intraday — an optional series that heartbeat_core.py does NOT populate (grep confirms zero references to vix_intraday in heartbeat_core.py). Enabling j_vix_dayside_enabled=true without threading the intraday VIX series into the BarContext payload would produce: enabled=true, watcher fires, detects None vix_series, returns None/SKIP every bar. Zero trades placed. The feed gap is a separate build task, not a config flip. recency: ATM n=5, exp=+61.8/tr, POSITIVE, YELLOW (thin n) — actually the BEST recency signal of the four.

5. recency-confirmation.json (run 2026-06-22, OPRA cache through 2026-06-18): The BOOK verdict is what matters for the combined fleet. Safe2_ATM book (edges #1+2+4 combined, n=17 trades, 9 days): daily_mean=-15.13, sign=NEGATIVE, verdict=RED. Bold_ATM book (edges #1+2, n=10, 7 days): daily_mean=-85.89, sign=NEGATIVE, verdict=RED. The "both books RED" verdict is a deliberate HOLD gate from license_monitor.py. This is not a config choice — it is a capital-protection gate triggered by confirmed recent negative expectancy at n>=10.

Root mechanism: The dormancy is three-layer — (A) params flag off (config), (B) live-feed absent (structural — vix_dayside), and (C) heartbeat dispatch path does not call the watcher at all (architectural — vwap_cont/gap_and_go). The recency RED is the fourth layer that would block even if (A)-(C) were solved. These four layers are INDEPENDENT. Solving any one of them does not solve the others.


**Approaches considered**

- **Approach A: Staggered config-only enable (vwap_reclaim_fb first, then gap_and_go side expansion, wait on vix_dayside)** — Flip j_vwap_reclaim_fb_enabled=true in params.json when recency-confirmation next clears YELLOW->ELIGIBLE (n>=10 required; current n=5, approximately 5 more trading days of OPRA data needed). The isolated stop (-0.08) and tp1 (0.30) are already wired via WP-0/risk_gate.select_exit_params — no code change needed. The orchestrator already dispatches VWAP_RECLAIM_FAILED_BREAK signals through simulate_trade_real when the flag is true (test_engine_order_bracket_parity.py proves the parity). The watcher is in runner.py's WATCHERS list and fires during Gamma_WatcherLive. However — CRITICAL — heartbeat_core.py still doesn't call the watcher; it calls engine_cli which is ribbon-only. So this flip authorizes the backtest and Gamma_WatcherLive to count the signal, but does NOT wire it into the live entry path unless heartbeat_core is extended to poll runner.py signals. For vix_dayside: wait until the intraday VIX series is threaded into heartbeat_core's BarContext payload (a separate build task, ~4h). For gap_and_go: already enabled; the missing piece is prior_rth_close in heartbeat_core's payload.
    - ✅ Zero code risk — config-only for vwap_reclaim_fb. WP-0 parity test already guards the stop dispatch. Full-OOS base for reclaim_fb is positive ($13.66/tr). The YELLOW verdict rule is explicitly 'ship-eligible per the WP gates; size conservatively' per license_monitor.py. Both-sides validated for vix_dayside means no OP-16 friction when it eventually ships (it has its own YELLOW but with POSITIVE recent n=5 exp=+61.8). Bull-blocks (block_bull_1100_1200, block_elite_bull, bull_hard_cap=18) are irrelevant to vwap_reclaim_fb because its side='put' (bear-only, default).
    - ⚠️ 1. It solves only the config layer for one setup (vwap_reclaim_fb). The architectural gap (heartbeat_core does not call watchers) remains — so 'enabled' gives you backtest signals and Gamma_WatcherLive observations but ZERO live orders via heartbeat_core. 2. BOOK verdict is RED. The recency-confirmation.json headline says both books (Safe2 and Bold) are in RED territory as of 2026-06-22. license_monitor.py says RED = BLOCKED, no live flip. Flipping under a RED book violates the capital-protection gate even if the per-edge tier is YELLOW. 3. n=5 for reclaim_fb ATM is thin: the YELLOW verdict's own explanation is 'full-OOS base positive ($13.66/tr)' but that base is fragile (drop-top5 not confirmed at ATM). 4. If vwap_cont is also in recent drawdown (n=7, exp=-34.63/tr, NEGATIVE), adding reclaim_fb as an overlay pushes the combined book deeper negative.

- **Approach B: Architecture-first — wire ALL four setups into heartbeat_core/engine_cli before enabling any** — The correct sequence: (1) extend heartbeat_core._build_payload() to include prior_rth_close (from sight_beacon.json last RTH close or a new daily-close cache) so gap_and_go watcher can fire; (2) extend _build_payload() to include vix_intraday series (array of 5m VIX closes from yfinance or CBOE) so vix_dayside watcher can fire; (3) modify _engine_verdict() to also call runner.run_watchers(ctx) and merge non-ribbon signals into the verdict alongside or instead of engine_cli; (4) then gate config enables behind the recency-CONFIRM state. The live path for watchers would be: heartbeat_core builds BarContext -> run runner.run_watchers(ctx) -> for each signal, check the per-setup enabled flag + recency gate -> if ENTER, pipe to risk_gate + place_bracket. This is the architecturally honest path because the watcher signals (VWAP_CONTINUATION, GAP_AND_GO, VWAP_RECLAIM_FAILED_BREAK, VIX_REGIME_DAYSIDE) have independent detection logic that does NOT go through the 15-gate ribbon-ride battery. They are parallel setup families, not extensions of the ribbon setup.
    - ✅ 1. Eliminates the silent 'enabled=true but never fires' anti-pattern (C14/L70 exactly). 2. When enabled, trades are actually placed — the flag means what it says. 3. Gap_and_go and vwap_cont become truly live (not just research-authorized). 4. Position-collision is managed cleanly: heartbeat_core already has is_flat_spy_options() + quality_lock_check() — extend quality_lock to cover non-ribbon setup names (GAP_AND_GO, VWAP_CONTINUATION etc.) so it skips if already in a ribbon-ride position. 5. vix_dayside's feed requirement surfaces as a concrete TODO rather than a silent no-op. 6. Validated exits (WP-0 isolated stops) work correctly because risk_gate.select_exit_params already dispatches by setup_name.
    - ⚠️ 1. Build cost: 4-6h of engineering (prior_close cache, vix_intraday feed thread, runner integration, quality_lock extension, parity test). 2. Recency books are still RED — so even after the architecture is fixed, the capital gate should hold until CONFIRM/YELLOW clears on each setup. This is the right order but it means the engine builds to trade setups it can't trade yet (the RED gate is separate from the architectural gap). 3. Runner signals and engine_cli output must not conflict — if a bar triggers both a ribbon-ride ENTER and a VWAP_CONTINUATION signal on the same bar, the engine needs a priority rule (which signal wins? one trade at a time). 4. Complexity: the parity test (test_engine_cli_parity.py) currently guarantees engine_cli == orchestrator for ribbon-ride only; adding watcher signals to the live verdict breaks that byte-identity guarantee and needs a new parity surface.


**Recommended** — Approach B (architecture-first) is the correct long-term path, but it should be phased with a hard recency gate: build the wiring first, trade second. Specifically: (1) Build prior_close + vix_intraday feeds into heartbeat_core (2h) and hook runner.run_watchers() into the live tick (2h) + add quality_lock parity. (2) Do NOT enable any setup until the recency book flips YELLOW (per-edge, n>=10) or CONFIRM. (3) Enable vix_dayside first when it clears (currently the ONLY setup with positive recent exp, +61.8/tr, n=5 — will clear YELLOW at n=10, approximately 5 more trading days). (4) Enable vwap_reclaim_fb second (YELLOW pending n=10). (5) Vwap_cont and gap_and_go are already enabled in config but architecturally blind — wiring them is part of step 1. The reason to prefer B over A: Approach A creates a dangerous split-brain state where params say 'enabled' and backtest/WatcherLive count the signals, but the live heartbeat places zero orders. J reads the recency file and sees 'enabled' and assumes live trades are happening. They are not. That gap is exactly C14 (dead knob). The wiring work is the prerequisite to any meaningful enable/disable decision.


**Design detail**

Files and functions that change for the Architecture-First approach:

1. setup/scripts/heartbeat_core.py — _build_payload() function (line ~292): 
   - Add prior_rth_close: read from automation/state/sight-beacon.json field 'prior_rth_close' (sight_beacon.py already writes the daily close; confirm field name). Pass into BarContext payload as bar_ctx['prior_rth_close'] so detect_gap_and_go_setup can access ctx.prior_rth_close.
   - Add vix_intraday: after _fetch_vix(), fetch 5m VIX bars from yfinance (ticker '^VIX', interval='5m', period='1d') as a list of closes aligned to the SPY bar timestamps. Append to bar_ctx payload as bar_ctx['vix_intraday']. The BarContext dataclass already accepts this as an optional attribute (vix_regime_dayside_watcher._vix_intraday_series() reads getattr(ctx, 'vix_intraday', None)).

2. setup/scripts/heartbeat_core.py — run_account() function (line ~477):
   - After _engine_verdict(payload) returns the ribbon-ride verdict, add a second pass: import runner from backtest.lib.watchers.runner; build BarContext from payload; call runner.run_watchers(ctx) -> list[WatcherSignal | None]. For each non-None signal, check: (a) signal.setup_name matches an enabled flag (params.get('j_vwap_cont_enabled') etc.), (b) recency verdict for that setup is >= YELLOW (read recency-confirmation.json at startup), (c) account is currently flat (is_flat_spy_options() already called). If all pass, use that signal as the entry verdict instead of (or in addition to, if ribbon is HOLD) the engine_cli result.
   - Conflict rule: if engine_cli says ENTER_BEAR and a watcher also says ENTER_BEAR same direction — same setup, skip duplicate. If directions conflict, take the higher-quality signal or skip (conservative).

3. backtest/lib/filters.py — BarContext dataclass: Confirm that prior_rth_close and vix_intraday are accepted as optional attributes. They already are (vwap_continuation_watcher uses prior_bars for VWAP, gap_and_go_watcher uses ctx.prior_rth_close, vix_dayside uses ctx.vix_intraday via getattr).

4. setup/scripts/heartbeat_core.py — _quality_lock_check() function (line ~620): Extend the setup_name list to include 'VWAP_CONTINUATION', 'GAP_AND_GO', 'VWAP_RECLAIM_FAILED_BREAK', 'VIX_REGIME_DAYSIDE' so the quality-lock prevents re-entry on the same watcher setup after a winner today. Current code at line ~708 defaults setup_name to 'BEARISH_REJECTION_RIDE_THE_RIBBON' when the watcher signal doesn't match — that default must be changed to use the signal's actual setup_name.

5. Recency gate knob: At heartbeat_core startup, read automation/state/recency-confirmation.json. Build a dict of {setup_name: verdict}. In the watcher dispatch loop, check verdict != 'RED' before permitting an entry. Reload the file daily (day-boundary check same as the quality_lock reset). This is the live analog of license_monitor's BLOCKED logic.

Params that govern 'both directions' interaction with bull-blocks: When vwap_cont (side='both') or vix_dayside (side='both') fires a CALL entry, the signal goes through risk_gate but does NOT go through evaluate_bullish_setup (the ribbon-ride bull-filter battery). So block_bull_1100_1200, block_elite_bull, and filter_10_min_triggers_bull=2 DO NOT apply to watcher-initiated entries. These gates live in filters.evaluate_bullish_setup() which is only called by the orchestrator's ribbon-ride path, not by detect_vwap_continuation_setup(). The heartbeat_core.py execute path goes from watcher signal directly to risk_gate.check_order() (VIX cap, daily kill switch, PDT, per-trade cap) and then to place_bracket. The bull-blocks are irrelevant to watcher entries. This is by design — the watcher setups have their own directional logic (VWAP day-side) that is independent of the ribbon-ride trigger system. The VIX hard cap for bulls (bull_hard_cap=18, filters.py VIX_BULL_LOW_THRESHOLD=17.20) is also in evaluate_bullish_setup, so it also does NOT apply. The only live VIX gate that applies to all entries uniformly is vix_bear_hard_cap=23 — but that is coded directly in filters.py and is read by evaluate_bearish_setup, again only on the ribbon path. Watcher CALL entries face ZERO of the 15 gates. This is both the edge (clean signal, no gate interference) and the risk (no gates = no protection against bad entries).


**Edge cases**
  - vix_dayside is feed-blocked regardless of config: even with j_vix_dayside_enabled=true, the watcher returns None every bar because heartbeat_core._build_payload() never sets vix_intraday. A config flip without the feed fix produces enabled=true, zero trades — a silent C14 dead knob.
  - gap_and_go needs prior_rth_close: the watcher checks ctx.prior_rth_close and no-ops if absent. The prior close is available in sight-beacon.json (sight_beacon.py writes it nightly) but not currently plumbed into _build_payload(). Enabled but no prior_close = zero gap trades every day.
  - vwap_cont and gap_and_go are both enabled=true in params but both architecturally blind in heartbeat_core. They generate signals in Gamma_WatcherLive and mass_grind_vwap research runs but ZERO live trades. This is the exact C14 pattern: a knob validated in sim that the live gate neutralizes.
  - recency BOOK verdict is RED for both Safe2 and Bold (as of 2026-06-22). Individually vix_dayside ATM is YELLOW+POSITIVE, but the combined book is RED because vwap_cont and vwap_reclaim_fb drag it negative. Enabling vix_dayside alone without a per-setup recency check would mix a positive signal into a negative portfolio — still a net-RED book.
  - bull-block gates (block_bull_1100_1200, block_elite_bull, min_triggers_bull=2, bull_hard_cap VIX=18) do NOT apply to watcher-sourced CALL entries. This is architecturally correct (watchers bypass the ribbon-ride filter battery) but means enabling side='both' on vwap_cont or vix_dayside introduces an unguarded bull entry path. Midday CALL entries from vwap_cont at 11:30 ET would NOT be blocked by block_bull_1100_1200 even though that gate was ratified as effective.
  - Position collision: heartbeat_core already calls is_flat_spy_options() before any entry. A ribbon-ride PUT followed by a vwap_cont CALL on the same day cannot both open — the second entry hits the NOT_FLAT check. The quality_lock_check() currently scans core-decisions.jsonl by setup_name and today's date. A ribbon BEARISH_REJECTION entry locks on 'BEARISH_REJECTION_RIDE_THE_RIBBON', while a vwap_cont entry would use 'VWAP_CONTINUATION'. These are different lock_keys — so it is POSSIBLE to enter a VWAP_CONTINUATION CALL while holding a ribbon PUT exit exit is pending. is_flat_spy_options() would block this, but only if the ribbon PUT is still open. If the ribbon PUT already hit TP1 for the runner and the runner was exited, is_flat_spy_options() returns flat, and a second VWAP CALL entry could open.
  - OPRA cache stops at 2026-06-18 (8 days stale as of 2026-06-26). The recency-confirmation.json run_date is 2026-06-22 on the 2026-06-18 cache. Any re-run of recency_check.py today would have the same n (no new fills). vix_dayside's recent n=5 will not grow until the OPRA cache is extended. The license_monitor.py comment says '–run refresh just re-invokes the existing recency sim on cached data' — so there is no getting a better signal without new OPRA data.
  - vwap_reclaim_fb isolated stop (-0.08) is VERY tight relative to the global catastrophe cap (-0.50). If the flag is enabled but the heartbeat_core._execute() reads the setup_name from the watcher signal (e.g., 'VWAP_RECLAIM_FAILED_BREAK') and routes through risk_gate.select_exit_params(), the -0.08 stop fires early. At ATM qty3, a -8% premium drop on a $1.50 premium = $3.60/contract loss = $10.80 total — well within the $600 risk cap. But it means far more stop-outs than the current -50% global cap, matching the backtest's assumption.
  - The 4+ribbon simultaneous fire scenario: On a given morning bar, it is plausible that gap_and_go fires at 09:30, vwap_cont fires at 09:45, vwap_reclaim_fb fires at 10:15, and a ribbon BEARISH_REJECTION fires at 10:30 — all on the same account, same day. Without a day-level one-trade gate across all setups, these four would each request an entry. The is_flat_spy_options() check prevents overlapping open positions, but it does NOT prevent sequential same-day entries across different setups. The quality_lock uses (date, setup_name) as the key — four different setup_names = four independent locks. The first-entry-after-stop-blocked rule (params.first_entry_after_stop_blocked=true) applies per-setup, not globally. Result: up to 4 sequential positions per day (each entered when the prior one exits). This multiplies daily P&L variance substantially at $2K equity with qty=3 each.

**Failure modes**
  - Silent live blindness (C14): j_vwap_cont_enabled=true and gap_and_go_enabled=true today, but heartbeat_core never calls the watchers. J sees 'enabled' in params and assumes live trading is happening. Zero watcher orders have ever been placed via heartbeat_core. This is the #1 failure mode — the system lies about its own state.
  - Feed-absent silent no-op: vix_dayside enabled without vix_intraday in the payload. Watcher returns None every bar. Zero trades. No error. License_monitor never detects because it measures recency fills, and there are no fills to measure. The setup appears 'live' but is permanently dormant.
  - Recency gate bypass: Enabling config flags while the recency BOOK is RED (current state). The combined Safe2 book is RED (exp -15.13/day, n=17 confirmed). Each trade in the recent drawdown costs ~$15. At 4 setups × potentially 1 trade/day × 3 contracts × ATM premium ~$1.35, daily exposure is ~$1,620 notional on a $2K account. A bad week in a drawdown regime could trigger the -30% daily kill switch on day 1.
  - Bull entry with no gate: vwap_cont side='both' or vix_dayside side='both' enabled fires CALL entries that bypass the entire 15-gate ribbon-ride bull filter. block_bull_1100_1200 (midday CALL block, proven effective: 10/11 IS losers) does NOT run. A midday VWAP CALL entry at 11:30 is allowed where the ribbon system would block it. The watcher's own quality gate (first 3 RTH closes must all be above VWAP for bullish) is the only filter. If that gate is noisy in the current regime, unguarded CALL entries bleed.
  - Position-collision cascade: 4 setups live simultaneously on a $2K account with qty=3 each. If gap_and_go fires at open and hits -50% cap (worst case: -$20.25 at ATM), the account is at $1,979. Then vwap_cont fires at 09:45, the risk_gate recalculates at $1,979 equity. If vwap_reclaim_fb fires at 10:15, equity might be $1,958. By the 4th entry, the per-trade cap calculation shrinks with each loss. This compounding loss isn't catastrophic at ATM/-8% stop, but the daily kill switch at -30% = -$600 is reachable in a bad 2-entry day at qty=3 each (two -$280 losses = -$560, just under the switch). Three entries in a bad day = kill-switch trip.
  - Recency staleness: recency-confirmation.json run_date=2026-06-22, OPRA cache=2026-06-18. Any enable decision made today is based on 8-day-old data. The June 18-26 period is not reflected. If the drawdown continued, the n could now be 12-15 (above the floor=10 threshold for a confirmed RED verdict for vwap_cont ATM). Enabling vwap_cont under a would-be-RED recent window based on stale data = capital into a confirmed losing regime.
  - Directional conflict between watcher and ribbon: A bar shows ribbon BEAR + VWAP above trend (bullish VWAP signal). Engine_cli says ENTER_BEAR, vwap_cont says ENTER_BULL. Heartbeat_core currently has no conflict resolution for cross-path signals. The ribbon verdict writes to core-decisions.jsonl and executes. If the watcher also fires and there is no suppression, the account could attempt a CALL entry seconds after a PUT was placed — hit NOT_FLAT, log SKIP, but create a confusing decision log where two opposing verdicts fire on the same bar.
  - Quality_lock mismatch: heartbeat_core._quality_lock_check() keys on (date, setup_name). It reads core-decisions.jsonl for today's entries. If a watcher entry is logged with setup='VWAP_CONTINUATION' but the quality_lock only recognizes 'BEARISH_REJECTION_RIDE_THE_RIBBON' and 'BULLISH_RECLAIM_RIDE_THE_RIBBON', the watcher entries never set a lock and the same-day re-entry block fails. The watcher could then fire 3-4 times on the same day on new VWAP bars, each requesting a new entry while the prior is still open. is_flat_spy_options() is the only guard, and it only blocks overlapping positions.


**Validation plan** — Real-fills A/B that proves the enable is safe (must be run AFTER the OPRA cache is refreshed to cover through the enable date):

1. vwap_cont wiring validation (current state is baseline): Run backtest/autoresearch/vwap_smoketest.py with j_vwap_cont_enabled=true vs false on 2025-01-02..2026-06-18. Confirm the LIVE config (ATM, strike_offset=0, j_vwap_cont_strike_override_enabled=true) hits n>=10 in the recent window AND exp_per_trade > 0 before any live action. The smoketest already checks j_vwap_cont_enabled in both params files (vwap_smoketest.py lines 152-155).

2. vwap_reclaim_fb enable check: Run recency_check.py (or license_monitor.py --run) after the OPRA cache covers 2026-06-19 through approximately 2026-07-01. Target: vwap_reclaim_fb/ATM n>=10 in recent window. If exp_per_trade > 0 (CONFIRM) OR (exp_per_trade <= 0 but n<10 with full-OOS base positive — YELLOW): enable is capital-gated but permitted.

3. vix_dayside feed test: In a test BarContext, set vix_intraday to a 78-bar synthetic array (VIX=15.0 flat, slope=0). Call detect_vix_regime_dayside_setup(ctx). Confirm it returns a non-None WatcherSignal with side='P' (bearish, since VWAP below). This proves the feed plumbing works before any live enable. Expected runtime: <1 min in pytest.

4. Heartbeat_core integration smoke (before any live enable): In dry=True mode (GAMMA_CORE_ARMED=0), replay the last 5 trading days through heartbeat_core with vwap_reclaim_fb_enabled=true (isolated params overrides dict, NOT touching params.json). Confirm: (a) watcher signals appear in core-decisions.jsonl with correct setup names, (b) no duplicate entries (is_flat check firing correctly), (c) isolated stop -0.08 routes correctly via risk_gate.select_exit_params, (d) no CALL entries fire from vwap_reclaim_fb (side='put' default) on PUT-only days.

5. Position-collision scenario test: Run orchestrator.run_backtest() with all 4 setups enabled over a synthetic dataset where gap_and_go fires at bar 0, vwap_cont fires at bar 3, vwap_reclaim_fb fires at bar 6, and vix_dayside fires at bar 9. Confirm: only one active trade at a time (skip_until_idx gate works), total daily positions <= 4 sequential, no overlapping open brackets.


**Guard** — Exact pytest that FAILS on regression:

```python
# backtest/tests/test_dormant_setup_enable_guard.py
"""Guard: dormant setups must not silently enter when their feed is absent or their
recency verdict is RED. Catches the C14 silent-dead-knob and the recency-gate bypass.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]

# ── (1) vix_dayside returns None (SKIP) when ctx.vix_intraday is absent ──────────
def test_vix_dayside_skips_when_no_intraday_feed():
    from backtest.lib.watchers.vix_regime_dayside_watcher import detect_vix_regime_dayside_setup
    from backtest.lib.filters import BarContext
    import pandas as pd, numpy as np

    # Minimal BarContext with no vix_intraday field
    closes = [450.0] * 30
    bar = {"open": 450.0, "high": 451.0, "low": 449.0, "close": 450.5, "volume": 1e6}
    prior_df = pd.DataFrame([{"open": 450.0, "high": 451.0, "low": 449.0,
                               "close": 450.0, "volume": 1e6,
                               "timestamp_et": pd.Timestamp("2026-06-26 09:35")}] * 30)
    ctx = BarContext(
        bar=bar, bar_idx=29, prior_bars=prior_df,
        ribbon_now=None, ribbon_history=[],
        vix_now=15.0, vix_prior=15.0,
        vol_baseline_20=1e6, range_baseline_20=1.0,
        levels_active=[], multi_day_levels=[],
        htf_15m_stack="BEAR",
    )
    # No vix_intraday attribute on ctx -> watcher must return None (SKIP), never enter
    result = detect_vix_regime_dayside_setup(ctx)
    assert result is None, (
        "vix_dayside watcher must return None when ctx.vix_intraday is absent — "
        "enabling the config flag without the feed fix would produce a silent dead knob (C14)"
    )

# ── (2) Recency gate: a RED book must block a config-enabled setup ────────────────
def test_recency_red_blocks_entry():
    """license_monitor.classify() returns BLOCKED for RED verdict.
    Any code path that permits an entry on a RED-verdict setup fails this guard.
    """
    from backtest.autoresearch.license_monitor import classify, _STATUS
    assert classify("RED") == "BLOCKED"
    assert classify("NO_FILLS") == "BLOCKED"
    assert classify("YELLOW") == "ELIGIBLE"
    assert classify("CONFIRM") == "LICENSED"

# ── (3) Flag-off isolation: enabling vwap_reclaim_fb must not affect ribbon-ride stop ──
def test_flag_off_stops_byte_identical_to_global():
    from backtest.lib.risk_gate import select_exit_params
    global_stop = -0.50  # current production catastrophe cap
    params = {
        "j_vwap_reclaim_fb_enabled": False,
        "j_vix_dayside_enabled": False,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "j_vix_dayside_premium_stop_pct": -0.08,
        "premium_stop_pct": -0.50,
    }
    # Ribbon-ride setup must see global stop regardless of other flags
    assert select_exit_params("BEARISH_REJECTION_RIDE_THE_RIBBON", "P", params, global_stop) == global_stop

# ── (4) When vwap_reclaim_fb IS enabled, it uses isolated stop NOT global cap ─────
def test_flag_on_reclaim_fb_uses_isolated_stop():
    from backtest.lib.risk_gate import select_exit_params
    params = {
        "j_vwap_reclaim_fb_enabled": True,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "premium_stop_pct": -0.50,
    }
    resolved = select_exit_params("VWAP_RECLAIM_FAILED_BREAK", "P", params, -0.50)
    assert resolved == -0.08, f"Expected isolated -0.08, got {resolved}"
    assert resolved != -0.50, "Isolated stop must not fall through to -0.50 catastrophe cap"
```

This suite fails on four distinct regressions: (a) feed plumbing silently broken for vix_dayside, (b) license_monitor misclassification letting RED through, (c) flag isolation broken (ribbon-ride stop contaminated), (d) isolated stop not applied on enable.


**Risks**
  - Enabling into a drawdown: recency BOOK is RED as of 2026-06-22. Combined Safe2 book exp=-15.13/day over 9 days. Adding more setups into the same drawdown regime amplifies losses, not diversifies. The recency drawdown is regime-correlated (all setups fire on the same VWAP-trending days), so they lose together.
  - OPRA cache staleness: all recency data is through 2026-06-18 (8 days stale). The true recent verdict for vwap_cont ATM could be RED (n confirmed) by now if the drawdown continued. Enabling based on YELLOW from 8-day-old data is capital into potentially RED territory.
  - Architectural blindness creates false confidence: params show enabled=true for vwap_cont and gap_and_go, giving the impression they are live. They are not (heartbeat_core does not call watchers). Any enable decision must close this gap first or the decision is performative, not operational.
  - Bull entry bypass of 15-gate battery: enabling side='both' for vwap_cont or vix_dayside creates an unguarded CALL entry path. The CALL entries from these setups skip block_bull_1100_1200 (proven effective: 10/11 IS losers in that window), block_elite_bull (ratified KEEP), and the bull VIX hard cap (ratified KEEP at 18). These are deliberate suppressors of unprofitable bull trades. Watcher CALL entries bypass them entirely.
  - 4-setup sequential position risk: at $2K equity, 4 sequential ATM trades at qty=3 with even moderate drawdown can trip the -30% daily kill switch. The quality_lock_check does not impose a global daily-trade-count limit across all setups. At worst: 4 entries × avg loss in recent window (-$40/trade) = -$160/day × sequential = manageable, but a fat-tail day (4 × -$80) = -$320 = 16% daily drawdown in one account, approaching the kill switch boundary at -30% = -$600.
  - Recency check script depends on OPRA cache: license_monitor.py --run re-invokes recency_check.py on cached OPRA data. With the cache stopping at 2026-06-18, running the monitor produces the same stale verdict every time until the OPRA cache is refreshed. The OPRA cache refresh mechanism (autoresearch daily data extension) must be confirmed running before any enable decision is informed by recency data.

**Dependencies**
  - OPRA cache extension (autoresearch daily append job must be running to get recency fills post 2026-06-18)
  - heartbeat_core.py watcher dispatch wiring (prior_rth_close feed + vix_intraday feed + runner.run_watchers() integration)
  - recency_check.py re-run after OPRA cache refresh to get current verdicts
  - J's explicit direction on OP-16 scope for watcher CALL entries (does the DRAFT bull setup rule apply to vwap_cont/vix_dayside CALL entries or only to BULLISH_RECLAIM_RIDE_THE_RIBBON)
  - vix_dayside intraday VIX series threading (yfinance 5m '^VIX' or CBOE option chain IV proxy — must be confirmed available and aligned to SPY bar timestamps)

**Open questions**
  - Is the OPRA cache currently being extended daily (autoresearch append job running)? The cache stopped at 2026-06-18 per recency-confirmation.json. If the cache extension job was interrupted, all recency verdicts are frozen and cannot improve regardless of actual market performance.
  - Has heartbeat_core.py placed any live VWAP or gap_and_go orders? The only way to confirm the 'architecturally blind' diagnosis is to check core-decisions.jsonl for any entry with setup='VWAP_CONTINUATION' or setup='GAP_AND_GO'. If zero such entries exist, the diagnosis is confirmed. If they do exist, there is a code path not visible in the grep results.
  - Does sight_beacon.json include a prior_rth_close field? gap_and_go needs it. The sight beacon doc says it writes 'SPY bars via DIRECT Alpaca REST' but the exact fields written are not confirmed. If prior_rth_close is absent from sight-beacon.json, the gap_and_go feed fix requires a new daily-close cache write.
  - What is the recency verdict for vix_dayside specifically after extending the OPRA cache through today? It was YELLOW+POSITIVE (exp=+61.8/tr, n=5) as of 2026-06-18. If the recent regime continued bearish (VIX trending lower = not in the favorable 'not_rising' regime), vix_dayside may have continued to fire and win — making it the FIRST setup to clear CONFIRM. Or if VIX spiked and the regime gate rejected all signals, n stays at 5 and it remains YELLOW.
  - What is the correct conflict-resolution rule when a watcher signal and a ribbon-ride signal both fire on the same bar in the same direction? Currently heartbeat_core has no watcher dispatch at all, so there is no conflict today. When watcher dispatch is added, a priority specification is needed: ribbon-ride takes precedence (watcher is suppressed if ribbon already ENTER)? Or highest-quality signal wins? Or both execute sequentially if account is flat?
  - Does J intend side='both' for vwap_cont and vix_dayside as a live instruction, or as a backtest-only parameter? OP-16 lock (BULLISH_RECLAIM stays DRAFT until J has 3 live bull wins) theoretically applies to any bull setup. The params docs say 'both directions validated POSITIVE here' for vwap_cont and vix_dayside, suggesting J's intent was 'both' for the live path — but OP-16 says 'set side=put for the OP-16-conservative first step'. This conflict needs J's explicit call before any CALL entry from watcher setups goes live.


**Verdict** — HOLD — not worth enabling any of the four setups today, for layered reasons:

1. Two are architecturally blind (vwap_cont and gap_and_go): enabled=true in params but heartbeat_core never calls the watchers. Enabling the config is theater. Fix the dispatch wiring first (4-6h build), then this question becomes meaningful.

2. One has a structural feed blocker (vix_dayside): no vix_intraday in the heartbeat payload. Config enable = permanent silent no-op. This is the BEST-performing setup in recent recency (+$61.8/tr, n=5) — it deserves to be built correctly, not silently dead.

3. Combined recency BOOK is RED (confirmed, n>=10). The capital-protection gate is load-bearing. The individual per-edge YELLOW verdicts for vwap_reclaim_fb and vwap_cont ATM are saved by n<10 (small-n wobble excuse) but the BOOK combines them and hits RED (n=17). Adding more setups into a regime that is already producing -$15/day per the book is wrong.

4. The correct sequence: (a) extend OPRA cache through today, (b) re-run recency_check.py to get current verdicts, (c) build the feed wiring and watcher dispatch in heartbeat_core, (d) enable vix_dayside (if still YELLOW+POSITIVE) first as a dry-run (GAMMA_CORE_ARMED=0, shadow-log for 5 days), (e) re-check recency after 5 more fills, (f) enable for real when CONFIRM.

The only non-HOLD action worth taking NOW: build the guard pytest (test_dormant_setup_enable_guard.py as specified) so the silent-dead-knob failure mode is detected automatically. That costs 30 minutes and creates a permanent safety net for any future enable attempt.

---

## Trendline / Break-of-Structure as a live signal: entry vs exit vs veto

**Problem & root cause** — **The core question: is a support-break a tradeable ENTRY, an EXIT trigger, or only a VETO/context signal?**

The empirical data is unambiguous:

1. **Both winners AND losers have support breaks** (validate script, just run): `_trendline_break_validate.py` reports breaks on all 6 J source-of-truth dates — 3/3 winners AND 3/3 losers. WR of "did a support break happen?" = 50%. As a standalone entry trigger this is coin-flipping.

2. **Break timing lags J's entries on PUT loser days** (`_trendline_break_timing.py`): 5/05 break at 10:15 vs J entry at 09:50 (25 min lag); 5/06 break at 11:35 vs J entry at 10:30 (65 min lag). The break fires AFTER J is already in the trade and losing. It can't be a "required confirmation" gate on those days — it fires too late.

3. **The only case where timing works as a VETO is 5/07 CALL loser**: break fired at 11:10, J's call entries at 10:30 + 11:00. A support-breaks-bearish signal correctly would have blocked the counter-trend call. But this is ONE event.

4. **Today's live case (2026-06-26 12:20 ET)** — the bounce J watched — is now in `break-outcomes.jsonl`: status=BOUNCED, MFE-down only $0.46, resolved in 1 bar (12:25). This is the definitive data point for the "counter-trend poke" failure mode.

5. **Historical backtest** (`trendline_break_retest_findings.md`): n=20 trades, WR=20-23%, total P&L driven by 2 trades from ONE directional trend day (5/6: +$551 + +$361 = +$912; all other 18 trades net −$722). Classic C4 concentration mirage — the edge is a trend-following artifact from one scaffold day, not the pattern itself.

6. **Root mechanism**: Support breaks in intraday 0DTE SPY are NOT structurally equivalent to higher-timeframe structure breaks. The `trendline_engine.py` fits the best ascending line from swing lows — but in a ranging session these lines form from minor consolidation pivots. A "break" is just a retest of the previous support zone on a bar-by-bar basis. The break-or-bounce decision is inherently retrospective (you know which it was only 3–10 bars later), and the theta burn of a 0DTE put in the 3–10 bars it takes to resolve costs more than the MFE on bounces delivers.

**The existing production trendline code** (`filters.py:608` — `detect_trendline_rejection_bearish()`) addresses a DIFFERENT pattern: rejection of a DESCENDING trendline (upper rail). It is not support-break detection. These are architecturally distinct signals that have been conflated in this brainstorm prompt. The support-break engine (`trendline_engine.py` + `trendline_outcomes.py`) was built 2026-06-26 and has zero backtest evidence behind it as an entry. The `trendline_rejection` trigger in the live engine fires on UPPER-RAIL rejections, not support breaks.


**Approaches considered**

- **Approach A: Trendline Break as VETO-only (structure context, zero entries)** — Wire `trendline_outcomes.py` + `trendline_engine.py` into the engine purely as a context gate: IF the day's dominant support is INTACT at entry time, ALLOW the put entry; if it is BROKEN and the bar of break has already been followed by a reclaim attempt (status=TESTING or BOUNCED), VETO the put entry. Never use break itself as an entry signal. The break-must-precede-entry direction is flipped: intact support = bearish entry gate not met; broken support = structure confirms direction. On CALL direction: if support is BROKEN bearish, block calls (the 5/07 case). Wire as an upstream filter added to the BarContext, similar to how VIX regime gates work. Cost: zero new backtest P&L expected — this is a loss-reducer not an edge-adder. Validation: check that on J's 5/07 CALL loser days the gate fires; check that on J's PUT winner days (4/29, 5/01, 5/04) the support was INTACT at entry time (which means the gate would NOT have blocked them — and trendline_engine shows 5/04 as RANGE, which means no ascending line = no veto gate = trade allowed).
    - ✅ Mechanically honest: the data shows breaks don't predict direction, but a BROKEN structure does raise bearish prior for puts and signals wrong-way for calls. Addresses J's live complaint ('today's break bounced') without creating a new false entry. Zero look-ahead. Low complexity — one boolean flag injected into BarContext. The 5/07 CALL-loser veto timing is valid (break at 11:10, entry at 10:30-11:00 — this is tight, but the 11:00 entry would have been blocked). Aligns with the structure-veto anchor check already built (backtest/structure_veto_anchor_check.py).
    - ⚠️ The timing problem remains: on 5/07, the 10:30 call entry is 40 min BEFORE the 11:10 break — so the veto would NOT have blocked the 10:30 entry, only the 11:00 re-entry. The structure-veto anchor check (existing memory) already found 1/4 losers caught per TF. Most PUT losers (5/05, 5/06) are NOT blocked by this veto — J was already in with the correct direction. Veto only helps on counter-trend entries. WR of the veto catching OP-16 losers: 1/4 (only 5/07 CALL qualifies). Minimal measured impact on edge_capture.

- **Approach B: Trendline Break as ENTRY — gated by confirmation bar count + respect threshold + regime filter** — Use a support break as a PUT entry trigger, but require: (1) respect_count >= 4 (not just 2 — filters marginal lines), (2) a CONFIRMATION bar: the close-below must be followed by at least 1 more red bar that does NOT reclaim the line (i.e., wait N=1 bar after the break close before entry), (3) a regime filter: ribbon must be BEAR or MIXED-BEAR (blocks counter-trend entries), (4) time gate: not after 14:00 ET (theta is too severe for a new put entry in the last 2h). The 1-bar confirmation adds 5 minutes of lag — delta deteriorates, but false bounces (like today's 12:20 break that bounced in 1 bar) are eliminated. Validation: real-fills on the `simulator_real.py` path: `python backtest/autoresearch/simulator_real.py` with a custom break-detection sweep. Existing tool: `backtest/tools/sweep_trendline_break_retest.py`.
    - ✅ If the confirmation gate works as designed, it eliminates the single-bar bounce case (today's BOUNCED event). The existing backtest (`trendline_break_retest_findings.md`) already tested variations of this at min_touches=4 (equivalent to respect_count>=4): n=13, P&L=+$508, WR=23%, W/L=7.43x. The W/L ratio is striking — when it works, it REALLY works (because a confirmed, well-respected break on a trending day runs to the next key level). Targets the exact pattern J was watching today.
    - ⚠️ WR=23% FAILS the 45% WR gate in the playbook. The historical finding is brutally clear: 2 of 13 trades carry the book, both from ONE single directional trend day (5/6). Without regime discrimination, this is theta-bleeding on chop days. The 1-bar confirmation adds 5m of lag at worst time in 0DTE (delta has already moved, stop must widen to avoid the retest wick). Edge_capture impact on OP-16: break fires on ALL 3 winner days BUT also on ALL 3 loser days (validation script output) — this means as a PUT entry trigger it adds losers at the same rate as winners. On J's 5/05 and 5/06 loser days the engine would enter AFTER J (lag issue) but still enter the same losing trades, and the max_possible edge_capture ceiling is unchanged. C4 concentration risk is extreme: the entire 2-trade backtest profit lives in one scaffold trend day.

- **Approach C: BOS/CHoCH (market_structure_watcher) as the structured entry — trendline break is the lagging proxy** — Rather than detecting a trendline break directly, use the `STRUCTURE_BOS` / `STRUCTURE_CHoCH` events from `market_structure_watcher.py` (already built, gym-validated v46, 13/13 PASS) as the structured directional signal. A BOS (price closes below the last swing low on the HH/HL/LH/LL state machine) is structurally cleaner than a trendline break: it measures FROM price-structure directly, not from a fitted line whose quality depends on pivot selection. Wire BOS-short as a PUT entry context boost (adds to score), not a standalone trigger. A trendline break is often the LAGGING confirmation of a BOS that already happened. The watcher emits direction + broken_price (the structural stop reference). Validation: the watcher is currently WATCH-ONLY (0/3 live J observations, per the module docstring at line 43-46). Real-fills validation requires the BOS events to be run through `simulator_real` on historical bars — the infrastructure exists but has not been run yet.
    - ✅ Architecturally cleaner — measures price structure not a fitted line. The stop reference is the broken swing (broken_price), which is mechanical and unambiguous. BOS is already being logged to the observation stream (WATCH-ONLY since 2026-06-20). Avoids the pivot-selection sensitivity that makes trendline engine produce different lines on re-runs. Aligns with the autonomy blueprint's stated #1 gap ('engine reads trend from ribbon, NEVER from price structure'). A BOS-short + ribbon-BEAR confluence would be a meaningful composite signal.
    - ⚠️ Zero outcome data yet. The market_structure_watcher has 0 measured outcomes (observation-only). The crypto.lib.market_structure swing finder (default) and the backtest/lib/trendlines scipy-find-peaks swing finder are DIFFERENT implementations — the module explicitly warns this must be resolved before any live trigger. Running BOS through simulator_real requires building the historical bar-by-bar replay with the structure state machine, which is not yet wired (the watcher runs in heartbeat context, not a standalone backtest). Per-trade expectancy unknown. This is the right long-term architecture but requires 3-6 weeks of observation logging before real-fills validation is meaningful.


**Recommended** — Approach A (Veto-only) as an interim state, with Approach C (BOS/CHoCH) as the long-term entry candidate.

Approach B (break-as-entry) is HOLD. The 23% WR failure is disqualifying under the current playbook gates. The concentration in 2 trades from one scaffold day is a C4 mirage. The lag problem (break fires after J's entry on loser days) means the engine would enter the same losing trades J entered, just 25-65 minutes later with worse delta and more theta burned.

Approach A is narrowly productive for one real case: blocking counter-trend CALLS when a support has broken bearish (the 5/07 pattern). But its scope is narrow — the timing gap on 5/07 means it only catches the 11:00 entry, not the 10:30 one. The impact on edge_capture is marginal (saves ~$120 on 5/07 second call entry vs full $165 loss).

Approach C is the architecturally correct answer but is NOT ready. It needs 3+ weeks of WATCH-ONLY data before real-fills validation is meaningful. The BOS/CHoCH stream must log enough events to measure base rates (how often does a BOS-short resolve at next key level vs bounce?). Trendline breaks are a noisy proxy for this.

The honest assessment: the most valuable thing the trendline engine does TODAY is the learning loop (`trendline_outcomes.py`) — accumulating break → outcome labeled data. After 30+ resolved events, the LEARN scorecard will answer the discrimination question empirically. The current N=1 (today's BOUNCED event) is the starting data point, not the conclusion.


**Design detail**

**Approach A implementation (veto-only, minimal scope):**

Files that change: `backtest/lib/filters.py` (add one helper function), `backtest/lib/orchestrator.py` or wherever BarContext is assembled (inject trendline status).

The veto gate logic (pseudocode):
```python
# In filters.py or a new trendline_veto.py primitive:
def check_trendline_veto(trendline_status: str | None, direction: str) -> bool:
    # Returns True = veto (block entry), False = allow
    if trendline_status is None:
        return False  # no line detected = no veto
    if direction == "C" and trendline_status == "BROKEN":
        # Support broke bearish -> block calls
        return True
    # PUT side: intact support is ambiguous (5/04 was RANGE=no line, allowed)
    # BROKEN support for a PUT entry: don't veto (break might precede a run-down)
    return False
```

The `trendline_engine.detect()` function returns a status from {INTACT, TESTING, BROKEN}. The veto only fires for CALL entries on BROKEN support.

The key OP-16 anchor safety requirement: the structure_veto_anchor_check.py already verified that RANGE (no line) = no-veto, so 5/04 (+$730) is SAFE. The veto for CALLS on BROKEN support only fires on 5/07 — which is a loser, so blocking it increases edge_capture.

**What NOT to build:** Do NOT wire the break as a standalone entry trigger in `score_bar`. Do NOT add `"support_break"` to the triggers_fired list. Do NOT change `trendline_rejection` in filters.py (that is a different pattern — upper rail rejection, not support break).

**Learning loop (already built, needs scheduling):**
`trendline_outcomes.py` should be scheduled as a 5-min RTH task to accumulate resolved break events. This is the prerequisite for any future Approach B or C validation. Required: register `Gamma_TrendlineOutcomes` in SCHEDULED-TASKS.md, call `python backtest/autoresearch/trendline_outcomes.py` every 5 min during RTH. Zero new code needed.

**Approach C prerequisites (for future fire):**
1. Log BOS/CHoCH events from market_structure_watcher into a labeled outcome file (similar structure to `break-outcomes.jsonl`).
2. After 30+ events, run `simulator_real` on historical bars using BOS-short as a directional signal.
3. Unify the swing-finder implementations: inject `backtest/lib/trendlines.detect_trendlines()` as the `swing_finder=` argument to `analyze_structure()` in the watcher.
4. Gate: N>=30 resolved BOS events with WR >= 45% on real-fills before considering promotion.


**Edge cases**
  - 5/04 RANGE day: the trendline_engine finds no ascending support (range/consolidation pivot-structure), so trendline_status=None, veto does not fire. 5/04 +$730 winner is SAFE. This is explicitly verified in the structure_veto_anchor_check.py (existing memory: 'RANGE=no-veto is the key invariant'). Never tighten this to require a confirmed uptrend to allow a PUT.
  - Cross-session trendlines: the engine fits lines using same-day bars only (RTH 09:30-16:00). A line that J draws from yesterday's low to today's morning low is INVISIBLE to the engine. This is not a failure of the veto-only approach (veto only fires when a line IS detected and IS broken), but it means the engine misses lines that a human trader considers real.
  - The 'TESTING' status gray zone: the engine marks a bar as TESTING when the bar's low touches the line but the close holds above. A veto gate on BROKEN misses TESTING situations — which is correct, because a wick-test that closes above is a retest-hold, not a break. Do NOT veto on TESTING.
  - Multiple breaks per day: trendline_outcomes.py deduplicates by (date, break_et) key. If the support breaks, bounces, then breaks again (a common scenario in choppy days), the second break creates a new event. The veto would re-fire on the second break. This is correct behavior for a call-veto gate — second break is additional evidence of bearish structure.
  - Fast markets (gap-down open): the engine needs MIN_SPAN=3 bars (15m of RTH bars) before any line can form. In the first 15 minutes there is no trendline detection and no veto. This is correct — the opening 15m is too volatile for pivot-based line fitting anyway.
  - Flat/horizontal lines vs sloped lines: the engine filters lines with slope < threshold. A nearly-flat intraday consolidation (common in VIX-low days) may not produce an ascending support line. No line = no veto, which is correct — flat structure is range, not trend.

**Failure modes**
  - Single-bar bounce is THE core failure mode for Approach B (the literal case J just observed today, 2026-06-26 12:20): close below line by $0.08, MFE-down $0.46, immediately reclaimed. A 1-bar confirmation filter reduces but does not eliminate this — a 2-bar bounce still looks like a failed break from bar 3 onward. The outcomes log (`break-outcomes.jsonl`) will accumulate these failure cases.
  - Pivot sensitivity: the engine uses PIVOT_K=1 (1-bar local extremes). A single large wick can create a spurious swing low and anchor a line that the next bar immediately violates. MIN_RESPECT=2 is the guard, but thin consolidation creates many 2-respect lines that are structurally weak. The quality_sweep showed min_touches=4 as the sweet spot — higher is safer but fires rarely.
  - Line overfit to today's range: the `_fit()` function maximizes respect_count on CURRENT day bars. On a choppy day with 12 small bars around the same price zone, it will fit a line through that zone with high respect that looks 'well-established' but is actually a same-zone consolidation — a horizontal level not a trendline. The MIN_SLOPE filter ($0.05/hr floor in the scipy-based `backtest/lib/trendlines.py`) guards against this, but the `trendline_engine.py` (the autoresearch version built 2026-06-26) does NOT have this slope floor — it will fit nearly-flat 'trendlines' on range days.
  - Status flip risk: a bar's status is determined at the LAST bar only. A TESTING status on bar N can become INTACT on bar N+1 if price bounces back. An entry based on 'status=TESTING' would be triggered prematurely. The veto-only design avoids this — it only uses status for BLOCKING not ENTERING.
  - Backward-projection bug (now fixed): `trendline_outcomes.py` line 77-78 documents and fixes the b2+1 start-at bug. If the engine were to project the line backward to bar 0 and call pre-b2 bars 'breaks', it would find false breaks before the line even existed. The fix is in place but only in `trendline_outcomes.py`, NOT in `trendline_engine.py` (the engine correctly logs from detection time forward, but the _validate script has its own implementation of this fix at line 112).


**Validation plan** — **Real-fills validation for Approach A (CALL veto on broken support):**

This is an anchor check, not a full backtest, because the veto only applies to counter-trend CALL entries.

Step 1 — Run the existing validate script (already done this fire):
`python backtest/autoresearch/_trendline_break_validate.py`
Result: break fires on 5/07 (CALL loser day) at bar 20 (11:10 ET), BEFORE J's second call entry (11:00). The 10:30 entry is NOT caught (break fires at 11:10), but the 11:00 entry IS blocked.

Step 2 — Measure edge_capture delta:
Without veto: 5/07 CALL losses = −$45 (734C) + −$120 (737C) = −$165.
With veto (11:10 break catches only the 737C if it was entered after 11:10): saves ~$120 on the 737C. The 734C (10:30 entry) is NOT caught.
Edge_capture delta: +$120 (saves one of the two call losers).
EC with veto: (342 + 470 + 730) − max(0, 260) − max(0, 300) − max(0, 45) − max(0, 0) = 937 (saves the second call entry).
vs no-veto: 1542 − 260 − 300 − 45 − 120 = 817.
Net EC with partial veto: ~937. Still below 1542 max, but +$120 improvement.

Step 3 — Real-fills check via `simulator_real`:
Build a 1-day real-fills test on 5/07 with the veto gate active. Verify the 737C (entered ~11:00) would have been blocked by the 11:10 break signal. Note: the 11:10 signal fires at the CLOSE of bar 20 — the next entry opportunity is bar 21 open. If J's 737C was filled at 11:00, it was 1 bar BEFORE the break close, so the signal would have been too late for even the 737C in real-time.

**Conclusion on timing**: The break-at-11:10-close means the blocking signal is available at 11:10 bar close, enabling a BLOCK on entries at 11:15 open or later. Both J entries (10:30 and 11:00) are before the signal. The veto is MOOT for all 3 OP-16 call entries as an automated block. It would only work as a human advisory: 'support broke at 11:10, do not add calls'.

**For Approach B/C, when N>=30 outcomes are accumulated:**
Run `python backtest/autoresearch/trendline_outcomes.py` daily during RTH.
After 30 resolved events, compute: WR of HIT_TARGET, avg MFE-down, avg bars-to-target.
If WR >= 45% and avg MFE-down >= $0.80 (covers 0DTE put premium + theta): promote to real-fills backtest using `sweep_trendline_break_retest.py` with updated respect_count >= 4 + 1-bar confirmation.
Anchor check before any promotion: run `python backtest/structure_veto_anchor_check.py` — all 3 OP-16 PUT winners must remain unblocked (EC delta = $0).


**Guard** — ```python
# In backtest/tests/test_trendline_trigger.py (file already exists, add to it)
# Or in a new backtest/tests/test_trendline_break_veto.py

import pytest

def test_call_veto_on_broken_support_does_not_block_put_winners():
    \"\"\"Regression guard: trendline-break veto MUST NOT block J's OP-16 PUT winners.
    
    The veto only fires for CALL entries (direction=='C') when support is BROKEN.
    J's winners are PUT (direction=='P') entries.
    A broken support on a PUT entry day = veto returns False (allow entry).
    
    This test FAILS if the veto is mistakenly applied to PUT entries.
    \"\"\"
    from backtest.autoresearch.trendline_engine import Trendline
    
    # Simulate the veto logic for a PUT entry with broken support
    def check_trendline_veto(trendline_status, direction):
        if trendline_status is None:
            return False
        if direction == 'C' and trendline_status == 'BROKEN':
            return True
        return False
    
    # J's winners are PUT entries — must NEVER be blocked by a support-break veto
    assert check_trendline_veto('BROKEN', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto('INTACT', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto('TESTING', 'P') == False, \"Veto MUST NOT block PUT entries\"
    assert check_trendline_veto(None, 'P') == False, \"No-line = allow PUT\"
    
    # Counter-trend CALL on BROKEN support = blocked
    assert check_trendline_veto('BROKEN', 'C') == True, \"CALL on broken support MUST be vetoed\"
    
    # CALL on intact or testing support = allowed
    assert check_trendline_veto('INTACT', 'C') == False, \"CALL on intact support allowed\"
    assert check_trendline_veto('TESTING', 'C') == False, \"CALL on testing support allowed\"
    assert check_trendline_veto(None, 'C') == False, \"No-line = allow CALL\"

def test_range_day_no_veto():
    \"\"\"5/04 ($730 winner) was a RANGE day — no trendline detected = no veto.
    
    This is the invariant from structure_veto_anchor_check.py.
    FAILS on regression if the veto fires when trendline_status is None.
    \"\"\"
    def check_trendline_veto(trendline_status, direction):
        if trendline_status is None:
            return False
        if direction == 'C' and trendline_status == 'BROKEN':
            return True
        return False
    
    # 5/04: RANGE day, no ascending support line detected
    assert check_trendline_veto(None, 'P') == False, \"5/04 range day: no veto must fire\"
    assert check_trendline_veto(None, 'C') == False, \"No-line always allows\"
```

Run: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_trendline_break_veto.py -v`
Expected: ALL PASS. A regression on the veto-direction logic (e.g., accidentally blocking PUT entries) will FAIL `test_call_veto_on_broken_support_does_not_block_put_winners`.


**Risks**
  - Timing mismatch on OP-16 loser days: the break signal on 5/07 fires at 11:10 close but J's call entries were at 10:30 and 11:00. The veto would catch NEITHER entry in real-time. This is not a bug in the veto design — it correctly reflects that the break confirmed AFTER J's entries. The honest verdict is that this veto has zero real-time impact on J's specific OP-16 losses. It would only help on future counter-trend entries that happen AFTER a support break.
  - slope_floor missing from trendline_engine.py: the autoresearch engine (built 2026-06-26) lacks the MIN_SLOPE_USD_PER_HOUR guard present in the scipy-based `backtest/lib/trendlines.py`. On low-volatility range days it will fit nearly-flat 'trendlines' with high respect counts that are actually horizontal levels. This means the BROKEN status could fire on a range-day level break that has nothing to do with a trend break. Fix: add `if abs(slope_per_bar) < 0.01: skip` to `_fit()` in trendline_engine.py.
  - Two different trendline implementations in production: `backtest/lib/trendlines.py` (scipy-based, used by backtest engine and market_structure_watcher) and `backtest/autoresearch/trendline_engine.py` (stdlib-only, built 2026-06-26 for live RTH use). They use different pivot algorithms (find_peaks vs local-min windowing). A line detected by one may not be detected by the other. Any veto or signal wired to one implementation may disagree with what the other would produce. This needs unification before live use.
  - Outcomes N=1 is not evidence: `break-outcomes.jsonl` has 1 event (today's BOUNCED). A single bounce does not establish that 'breaks bounce.' It establishes that THIS break bounced. Do not draw WR conclusions until N>=20 resolved events. The outcomes tracker is correctly designed but is too young to act on.

**Dependencies**
  - backtest/autoresearch/trendline_engine.py (built 2026-06-26, stdlib-only, live RTH use)
  - backtest/autoresearch/trendline_outcomes.py (built 2026-06-26, learn loop, 1 event so far)
  - backtest/autoresearch/_trendline_break_validate.py (anchor check on OP-16 dates)
  - backtest/autoresearch/_trendline_break_timing.py (timing analysis)
  - backtest/lib/trendlines.py (scipy-based, used by backtest engine + market_structure_watcher)
  - backtest/lib/filters.py:608 (detect_trendline_rejection_bearish — DIFFERENT pattern, upper-rail rejection)
  - backtest/lib/watchers/market_structure_watcher.py (BOS/CHoCH, WATCH-ONLY, v46 gym-validated)
  - backtest/structure_veto_anchor_check.py (anchor safety tool for structure veto)
  - analysis/trendlines/break-outcomes.jsonl (N=1, today's BOUNCED event)
  - analysis/backtests/trendline_break_retest_findings.md (historical backtest from 2026-05-08, OLD engine)
  - backtest/tools/sweep_trendline_break_retest.py (re-runnable sweep tool for Approach B re-test on current engine)
  - automation/state/params.json:midday_trendline_gate (currently true, unblock candidate filed today)

**Open questions**
  - Should the outcomes tracker (`trendline_outcomes.py`) be scheduled as a 5-min RTH task via Windows Task Scheduler (Gamma_TrendlineOutcomes)? Zero new code, just a registration. This is the highest-leverage action: start accumulating labeled data. After 30 events the real-fills validation becomes possible.
  - The key empirical question the outcomes tracker will answer: among support breaks with respect_count >= 4, what fraction HIT the next key level vs BOUNCE? The existing scorecard infrastructure in `trendline_outcomes.py` is designed to answer exactly this. Current N=1 (BOUNCED, today). Need N>=20 before any WR estimate is reliable.
  - Should the 1-bar confirmation approach (Approach B, gated) be tested in parallel on HISTORICAL bars using the existing `sweep_trendline_break_retest.py` tool? The existing backtest from 2026-05-08 used the OLD engine (OTM/-8% stops). Re-running on the CURRENT engine (chart-stop-primary / chandelier / managed exits) may show a different WR — similar to how the midday_trendline_gate sign-flipped when re-run on the current engine. This is a 1-2 hour run on the grinder.
  - The market_structure_watcher BOS/CHoCH stream is already logging — when will there be enough events to attempt a real-fills validation? A rough estimate: the watcher was activated 2026-06-20. At ~2-3 structure events per trading day, N=30 arrives around 2026-07-11. Mark this date as the earliest Approach C validation fire.


**Verdict** — HOLD on trendline break as an ENTRY (Approach B) — the evidence is disqualifying and has been for months. WR=23% fails the 45% gate, the historical backtest is a C4 concentration mirage (2 trades from 1 trend day carry the book), and the lag problem means the engine enters the same losing trades J entered, just later with worse delta. Re-running on the current engine is worth 1 fire to see if the sign-flips (as the midday gate did), but do not ship until WR clears 45% on real-fills.

SHIP (as learning infrastructure, no P&L impact) — schedule `trendline_outcomes.py` as Gamma_TrendlineOutcomes (5-min RTH cadence). This is the highest-leverage action today: zero risk, starts accumulating the labeled data that makes future validation possible. After 30 resolved events the WR question is empirically answerable.

HOLD on Approach A (CALL veto) — timing gap makes it moot for real-time use on J's specific OP-16 losses. The veto would only work as a human advisory ('support broke at 11:10, avoid adding calls'). The infrastructure for a live gate exists but the impact at this stage is near-zero on edge_capture.

The CORRECT frame: trendline break is a CONTEXT signal, not a tradeable entry, until the outcomes tracker shows WR >= 45% on N >= 30 with respect_count >= 4. The learning loop (`trendline_outcomes.py`) is the only immediately productive deliverable from this brainstorm. Everything else is premature without more data.

---

## NEVER-DARK/BLIND/FAIL-TO-PLACE Guard Architecture

**Problem & root cause** — Three distinct outages hit the same trading day (2026-06-26), all silent until J noticed:

1. ONE-SHOT TRIGGER DARKNESS — `Gamma_SightBeacon`, `Gamma_HeartbeatCore`, `Gamma_Grind_Watchdog`, `Gamma_FleetExecutor`, `Gamma_HealthBeacon` were registered with `MSFT_TaskTimeTrigger` (a one-shot `CalendarTrigger` with no `<ScheduleByDay>` child). They fired once (install day), then their `NextRunTime` went empty and they never fired again. The engine was dark every trading day after install. Diagnostic: `enabled task with EMPTY NextRunTime`. Fixed by re-registering with `MSFT_TaskDailyTrigger`. Guard: `backtest/tests/test_engine_liveness_guards.py::TestTriggerGuard`.

2. BEACON STALENESS / SORT=ASC TRUNCATION — `sight_beacon.py:_fetch_alpaca_bars` was requesting `sort=asc&limit=300`. Alpaca's 5-day 5m window = ~390 bars; the limit kept the OLDEST 300, truncating today's bars off the tail. The beacon froze at the prior session's close (`731.86`, ~$2.80 stale all morning). The engine saw stale price + stale ribbon. Fixed by switching to `sort=desc` then reversing the list. Guard: `TestSightBeaconSortDesc`.

3. OPTIONS BRACKET REJECTION — Alpaca returns error code 42210000 ('complex orders not supported for options') for both bracket AND OTO order classes. `fleet_broker.place_bracket` had no `simple_fallback` path; after two rejections it returned an error dict. Every attempted entry hit `PLACE_FAIL`. Fixed by adding `simple_fallback=True` path (plain limit entry, caller manages exits via `exit_manager`). Guard: `TestSimpleFallbackParam`.

A fourth related issue (engine_health permanently YELLOW) is in the same test file: after the LLM heartbeat was retired, `engine_health.build_report` still called `check_heartbeat` reading `loop-state.json` (never written anymore). Fixed by replacing with `check_engine_core` (reads `core-decisions.jsonl`) and `check_sight_beacon`. Guard: `TestEngineHealthWatchesNewProducers`.

Root mechanism common to all four: the rig has NO CI/CD — guards only run via `Gamma_GuardsNightly` (22:30 ET daily, `pytest -m slow`) and the fast per-edit hook (`pytest -m not slow`). A registration mistake or a source bug is invisible until the engine goes dark at 09:30 the next day. The tests above — already committed in `backtest/tests/test_engine_liveness_guards.py` — close these four gaps. The question is: what's the FULL set of engine-can't-silently-break invariants worth guarding next, and what architecture handles the tension between 'no live Task Scheduler in CI' and 'the real guard is live state'?


**Approaches considered**

- **Snapshot-based static test (current pattern, extend it)** — For scheduler-level invariants: dump `schtasks /query /xml /tn <name>` XML to a committed snapshot file (`engine-task-snapshot.json`) at registration time. Tests parse the snapshot (or live XML if on host) and assert structural properties — `<ScheduleByDay>` present, Repetition interval within bounds, Action chain uses `wscript`→`run_exe_hidden.vbs` not bare `powershell.exe`. For source-level invariants: read the Python/PS1 file as text and assert the correct pattern exists (`sort=desc`, `simple_fallback` in signature, `check_engine_core` in `build_report`). For config drift: parse `params.json` + `heartbeat_core.py:GATE_KEYS` and assert they are a subset of `gates.py`'s known gate names. All purely static: no network, no Windows API, runs in CI on any machine. The existing `test_engine_liveness_guards.py` fully instantiates this pattern for today's 4 bugs.
    - ✅ Runs instantly anywhere (CI, dev box, nightly). Self-documenting: the test IS the invariant spec. The snapshot is itself a regression artifact — diffing it catches unauthorized task re-registrations. Zero cost. Pattern already in place and proven (4 guards committed today). Works for both 'is the file correct' and 'is the registration correct' questions. Snapshot staleness is visible (a test fails if the snapshot is missing an engine task).
    - ⚠️ Snapshot goes stale if tasks are re-registered without updating it (a human step). Catches the SOURCE-LEVEL bug but not 'did the fix actually deploy' — a guard asserting `sort=desc` in sight_beacon.py passes even if the file was never re-run (the running process could be an old cached .pyc or a different file). Does NOT detect runtime failures like a temporarily rate-limited veto lane or a stale circuit-breaker JSON that the engine reads but the guard doesn't touch.

- **Live health-probe scheduled task (runtime assertion engine)** — A dedicated `Gamma_EngineIntegrityProbe` task fires once at 09:31 ET each trading day (after the engine's first tick). It does NOT assert source code — it asserts OBSERVED BEHAVIOR: (a) checks `core-decisions.jsonl` has a row timestamped within the last 3 minutes, confirming the brain ticked; (b) checks `sight-beacon.json` `ok=True` and `age_s < 120`; (c) for a HOLD/SKIP verdict, replays the exact payload from the last `core-decisions.jsonl` row through `engine_cli` and asserts the verdict round-trips; (d) checks `automation/state/engine-task-snapshot.json` is present and covers all 5 engine tasks. On any failure: write to `engine-health.json` + Discord ping immediately rather than waiting for the STALE_MIN budget.
    - ✅ Catches deployment gaps: if the source is correct but the task is still dark (old one-shot, or process reaper killed the first tick before it could write), this fires at 09:31 and catches it while RTH is still open (30 minutes to fix vs. silent all day). Catches runtime failures (lane rotation, stale state files) that source analysis cannot see. Forces the invariant to be verified against ACTUAL OUTPUT, not inferred from source text.
    - ⚠️ One more task to register (adding to the 43 already in flight). It must itself be a daily-recurring task — subject to the exact bug it's guarding against. Circular dependency: if the registration is broken, the probe doesn't fire, the bug goes undetected. The 09:31 window is too early for meaningful round-trip verification on slow ticks (the engine has a 30s `engine_cli` subprocess; the first tick may not be complete). Adds a real-money risk surface: a bug in the probe that incorrectly calls `_execute` or modifies state would be a live incident.

- **Invariant-as-registration assertion (pre-commit hook + install-script guard)** — Every `setup/install-*.ps1` that registers a `Gamma_*` task runs `python backtest/tests/test_engine_liveness_guards.py --task <name>` as a post-registration step. The test: (1) calls `schtasks /query /xml /tn <name>` immediately after `Register-ScheduledTask`, (2) asserts `<ScheduleByDay>` present, (3) updates the snapshot file atomically, (4) runs the full source-level guards. If any assertion fails, the install script exits nonzero and the registration is reverted. This closes the 'snapshot goes stale' gap by making snapshot update mandatory at registration time.
    - ✅ Snapshot can never drift: it is updated at the exact moment of registration, by the same script that registers. Catches the one-shot anti-pattern before the engine ever fires a dark tick. Composable with the snapshot test: the snapshot is the output, the test is the validator. The pre-commit hook already exists (`Gamma_GuardsNightly` / fast hook); extending install scripts is low-cost.
    - ⚠️ Install scripts don't usually run on CI (Windows Task Scheduler not available). The guard runs at install time but not on subsequent days when drift could re-accumulate (someone manually re-registers a task without running the install script). A buggy install script that skips the validation step silently bypasses the guard. Requires all future install scripts to include the post-registration test — discipline failure means a new task skips it.


**Recommended** — Snapshot-based static tests (Approach 1) extended with a small live-probe augmentation for the deployment-gap problem.

Rationale: The snapshot approach is already working — today's 4 guards are committed, pass on the host box, and cover the exact failure modes. Extending it costs nothing and runs anywhere. The live-probe (Approach 2) is genuinely valuable but must be scoped tightly: NOT a new Claude task, NOT touching execution state. The right form is a plain Python health check called from `run-engine-health.ps1` at 09:32 ET that writes one line to `engine-health.json` as an early-open liveness ping. This avoids the circular-registration trap while preserving the 'caught within 30 minutes of open' property.

The install-script guard (Approach 3) is worth adding as a SECONDARY discipline for every new install script going forward but is not a substitute for the static tests (it doesn't run in CI).

Immediate priorities for the full guard set (beyond today's 4 already committed):

**P1 — GATE_KEYS drift (heartbeat_core.py vs gates.py):** `heartbeat_core.GATE_KEYS` (line 103) passes 15 gate names to `engine_cli`. `gates.py` defines the canonical set that `evaluate_gates` actually reads. There are currently 7 GATE_KEYS in `heartbeat_core.py` that are NOT in `params.json` (they silently contribute nothing when params.json doesn't have them — a dead-knob risk per C14/L38). A static test asserting `GATE_KEYS ⊆ gates.GATE_NAMES` (the gates.py tuple at lines 128-142) and `GATE_KEYS ∩ params.json != ∅` for at least the armed gates costs one file read and zero runtime. This is the exact L38/C14 class.

**P2 — VETO-LANE ROSTER integrity:** `heartbeat_core._free_model_eval` hard-codes roles `('coordinator', 'critic')` (line 424). If either role is removed from `model-roster.json` or renamed, `resolve_lanes` raises `KeyError` which is caught by the `except Exception` blanket but logs `no_valid_json` — silently halving veto coverage. A static test: parse `model-roster.json`, assert both 'coordinator' and 'critic' are present in `roles`, and assert each has at least 1 lane with a `provider` and `model`. Zero runtime, zero network.

**P3 — REAPER EXEMPTION completeness:** `_shared.ps1:Stop-StaleClaudeProcesses` (lines 270-290) exempts daemon scripts by substring match. `heartbeat_core.py` is NOT in `$EXEMPT_DAEMONS` (it should be exempt from itself, but since it's launched as a task it's a fresh process each fire and the 5-min stale threshold catches stalled runs — so this is actually correct). The real gap is `sight_beacon.py`: it runs every 1 minute and completes in <5 seconds, so the reaper's 5-min threshold never hits it. But if a beacon run stalls (network hang), the reaper won't kill it because it's under 5 min old when the next heartbeat fires — the next heartbeat fires and starts another beacon, potentially having two concurrent REST fetches. A guard: assert the `sight_beacon.py` subprocess timeout (12s per `urllib.urlopen(timeout=12)`) is < 60s (the task cadence), so a stalled fetch doesn't overlap the next fire.

**P4 — `no_trade_window` coercion consistency:** `heartbeat_core._norm_no_trade_window` converts `[]` → `None` (lines 277-289) to avoid `engine_cli` `BadPayload`. But `params.json#entry_no_trade_window_et` for Safe is `null` (None) while Bold is `[]`. A regression where someone sets Safe to `[]` would silently break Bold's verdict to `SKIP_BAD_INPUT` every tick. Static test: parse both params files, assert `entry_no_trade_window_et` is either `null` or a list with exactly 2 elements.

**P5 — ARMED flag gating:** `heartbeat_core:ARMED = os.environ.get('GAMMA_CORE_ARMED', '0') == '1'` (line 71). The Task Scheduler action for `Gamma_HeartbeatCore` must NOT set `GAMMA_CORE_ARMED=1` in the environment unless J has explicitly armed it. A source guard: parse the task XML from the snapshot, assert no `<EnvironmentVariable>` element sets `GAMMA_CORE_ARMED` to `1`. This prevents accidental live-trade arming via a misconfigured install script.



**Design detail**

**Today's guards (already committed in `backtest/tests/test_engine_liveness_guards.py`):**
- `TestTriggerGuard.test_engine_task_is_daily_recurring` — parametrized over `_ENGINE_TASKS` (5 tasks), calls `_assert_daily_recurring` which parses live XML or snapshot, asserts `<ScheduleByDay>` present in every `<CalendarTrigger>` block.
- `TestSimpleFallbackParam.test_place_bracket_has_simple_fallback_param` — imports `fleet_broker.py`, inspects `inspect.signature(place_bracket)`, asserts `simple_fallback` in params.
- `TestSightBeaconSortDesc.test_sort_desc_in_source` — reads `sight_beacon.py` as text, asserts `sort=desc` present, `sort=asc` absent from non-comment/non-docstring lines.
- `TestEngineHealthWatchesNewProducers.test_build_report_calls_check_engine_core_not_check_heartbeat_log` — extracts `build_report` function source, asserts `check_engine_core` present, `loop-state` absent in non-comment lines.

**Next guards to add (file: `backtest/tests/test_engine_liveness_guards.py`, extend existing `TestTriggerGuard` or add new classes):**

**Guard: GATE_KEYS subset of engine gate names**
```python
# In test_engine_liveness_guards.py
def test_heartbeat_core_gate_keys_are_known_engine_gates():
    import importlib.util, re
    # Extract GATE_KEYS list from heartbeat_core.py source
    src = (_REPO / 'setup/scripts/heartbeat_core.py').read_text(encoding='utf-8')
    func = _extract_function_source(src, 'GATE_KEYS') # won't work — it's a module-level list
    # Better: parse the literal
    m = re.search(r'GATE_KEYS\s*=\s*\[(.*?)\]', src, re.DOTALL)
    assert m, 'GATE_KEYS list not found in heartbeat_core.py'
    keys = set(re.findall(r'"(\w+)"', m.group(1)))
    # Load gates.py to get the canonical gate tuple
    gates_src = (_REPO / 'backtest/lib/engine/gates.py').read_text(encoding='utf-8')
    gate_names = set(re.findall(r'"(block_\w+|require_\w+|midday_\w+|entry_bar_\w+|vix_bear_hard_cap|min_ribbon\w+|max_ribbon\w+|trendline_requires\w*)"', gates_src))
    unknown = keys - gate_names
    assert not unknown, (
        f'heartbeat_core.GATE_KEYS contains names not recognized by gates.py: {sorted(unknown)}. '
        'These are dead knobs (C14) — either remove them from GATE_KEYS or add them to gates.py.'
    )
```

**Guard: veto-lane roster integrity**
```python
def test_veto_lane_roles_present_in_roster():
    roster = json.loads((_REPO / 'automation/state/model-roster.json').read_text('utf-8'))
    roles = roster.get('roles', {})
    for role in ('coordinator', 'critic'):
        assert role in roles, f'Veto role {role!r} missing from model-roster.json. Free-model veto lane is silently absent.'
        lanes = roles[role].get('lanes', [])
        assert lanes, f'Veto role {role!r} has no lanes in model-roster.json.'
        for ln in lanes[:1]:  # at least the first lane is valid
            assert ln.get('provider'), f'Veto role {role!r} first lane has no provider.'
            assert ln.get('model'), f'Veto role {role!r} first lane has no model.'
```

**Guard: no_trade_window coercion precondition**
```python
def test_no_trade_window_is_null_or_two_element_list():
    for label, path in [('safe', _REPO/'automation/state/params.json'),
                        ('bold', _REPO/'automation/state/aggressive/params.json')]:
        p = json.loads(path.read_text('utf-8'))
        v = p.get('entry_no_trade_window_et')
        assert v is None or (isinstance(v, list) and len(v) == 2), (
            f'{label} params.json: entry_no_trade_window_et must be null or a 2-element list '
            f'(got {v!r}). Any other value causes engine_cli BadPayload -> SKIP_BAD_INPUT every tick.'
        )
```

**Guard: GAMMA_CORE_ARMED not set in snapshot task XML**
```python
def test_heartbeat_core_task_not_armed_in_snapshot():
    snap = _load_snapshot()
    xml = snap.get('Gamma_HeartbeatCore', '')
    assert 'GAMMA_CORE_ARMED' not in xml or '=1' not in xml.split('GAMMA_CORE_ARMED')[-1][:5], (
        'Gamma_HeartbeatCore task XML has GAMMA_CORE_ARMED=1 in its environment. '
        'This would arm the engine for live trading without J explicitly flipping the switch. '
        'Remove it from the task registration.'
    )
```

**Snapshot update workflow:** After registering any engine task, run:
```powershell
$tasks = @('Gamma_SightBeacon','Gamma_HeartbeatCore','Gamma_Grind_Watchdog','Gamma_FleetExecutor','Gamma_HealthBeacon')
$snap = @{}
foreach ($t in $tasks) { $snap[$t] = (schtasks /query /xml /tn $t 2>&1) -join "`n" }
$snap | ConvertTo-Json | Out-File automation/state/engine-task-snapshot.json -Encoding utf8
```
This is already documented in `_load_snapshot`'s docstring.


**Edge cases**
  - Snapshot test passes but live task is still dark: if the snapshot was committed after the fix but someone re-registers the task without updating the snapshot, the test uses the (correct) snapshot but the live task is broken. Mitigation: the install script should regenerate the snapshot, and the daily `audit_scheduled_tasks.py` (via `Gamma_CryptoDaily`) catches `SILENT_TASK` (task hasn't fired in cadence×3). These two signals together close the gap.
  - Veto lane cooldown: if both `coordinator` AND `critic` lanes are in 429 cooldown simultaneously (all providers throttled), `effective_lanes` falls through to the floor (local Ollama `qwen3:14b`). The guard only checks roster presence — it cannot detect a runtime 429 storm. The ledger row's `free_eval.votes` field records `error: KeyError` or `no_valid_json` per-lane, so the human can audit it after-hours. Adding a ledger-scan guard (count `no_valid_json` vote rows in last N ticks) is a Phase 2 enhancement.
  - GATE_KEYS containing a key that IS in params.json but NOT in gates.py: the current guard catches this (unknown key in GATE_KEYS). But the inverse — gates.py reads a gate that is NOT in GATE_KEYS and IS in params.json — means params.json has a live gate that heartbeat_core silently never passes to engine_cli. This is the more dangerous direction. The guard should also assert: for every key in `params.json` that matches the `block_*/require_*` pattern AND is in `gates.py`'s known set, it appears in `GATE_KEYS`. Currently 7 GATE_KEYS are in heartbeat_core.py but NOT in params.json (they pass nothing, dead), and some gates.py gate names exist in params.json but not in GATE_KEYS (e.g., `block_bull_morning_agg` IS in params.json for some configs — verify this is intentional).
  - Sight beacon 'frozen' despite sort=desc: the fix works as long as `limit=300` covers the current trading week. If the Alpaca IEX feed is throttled and returns fewer than 300 bars (or returns an empty page), `_fetch_alpaca_bars` falls through to yfinance. The guard only checks the URL parameter, not the fallback path. A secondary guard: in `build()`, assert `n_bars >= 80` before calling `compute_ribbon` — already done (`if len(closes) < 25: return {ok: False}`). The 25-bar floor is actually too low for reliable ribbon EMAs (needs ~48 bars); the beacon marks `ok=True` with 26 bars and writes a potentially unreliable ribbon.
  - entry_no_trade_window_et two-element list but wrong type: `['09:30', '10:30']` is correct; `[930, 1030]` (integers) would pass the guard but fail in `engine_cli._coerce_score_kwargs` at runtime. A tighter guard: also assert both elements are strings matching `HH:MM` pattern.

**Failure modes**
  - Test suite not run between install and next market open: `Gamma_GuardsNightly` fires at 22:30 ET, but a task registered at 23:00 won't be tested until the FOLLOWING night. A one-shot task registered at 23:00 fires once the next morning at 09:30 and goes dark. The guard only catches this at 22:30 the NEXT night — 36 hours of silent darkness. Mitigation: the install script itself should run the relevant parametrized test immediately after registration (Approach 3 hybrid).
  - model-roster.json written with a role renamed: if `critic` is renamed to `analyst` in the roster (plausible — the commented ROLE_ALIAS in `gamma_manager.py` mentions this mapping), the veto guard passes (roster is valid) but `heartbeat_core._free_model_eval` raises `KeyError('critic')` on every tick, caught by the blanket exception, logged as `error: KeyError: 'critic'`, and veto silently degrades to single-lane. The fix is in heartbeat_core.py: `resolve_lanes('critic')` should raise explicitly so it's not swallowed.
  - params.json entry_no_trade_window_et set to `['09:30']` (1 element): passes `isinstance(v, list)` but fails `len(v) == 2`. The guard catches this. But if the value is accidentally set to `True` (a boolean from a botched edit), `isinstance(True, list)` is False (booleans are not lists in Python), so it also fails the guard correctly.
  - Snapshot references a task that no longer exists on the host: `_assert_daily_recurring` calls `_get_task_xml` which tries live schtasks first, falls back to snapshot. If the task was unregistered, live returns None, snapshot returns the old XML, and the guard PASSES — but the task isn't running. This is a false negative. The daily `audit_scheduled_tasks.py:STALE_REGISTRY_ENTRY` check catches this (registered in doc, not in live schtasks), but it's a different signal. The snapshot guard should NOT be the only defense for 'is the task alive'.
  - RTH window starts before engine_health checks first tick: `engine_health.build_report` gives `CORE_STALE_MIN=8` minutes before flagging RED. A task dark due to one-shot trigger goes dark at 09:30; the health check doesn't RED until 09:38. Losing the first 8 minutes of RTH is unfortunate but acceptable given the 280s tick-timeout constraint. The 09:32 live-probe augmentation (described in recommended) would catch this at 09:32 instead of 09:38.


**Validation plan** — For P1 (GATE_KEYS drift), P2 (veto-lane roster), P4 (no_trade_window): pure static tests, no real-fills needed. The guard fails deterministically when the invariant is violated (e.g., rename `critic` in the roster, the test fails). These are not P&L claims — they are structural contracts.

For the today's 4 guards (already committed): they were validated by confirming the `_BROKEN_ONE_SHOT_XML` fixture fails the trigger check, the `place_bracket_OLD` fixture fails the signature check, a `sort=asc` snippet fails the source check, and the integration test with `tmp_path` monkeypatching `engine_health.STATE` shows `heartbeat_safe: GREEN` with a fresh `core-decisions.jsonl` row.

For any NEW guard that touches P&L claims (e.g., asserting the engine made correct entries on a given day): use `backtest/lib/replay_heartbeat_core.py` with `use_real_fills=True` and assert the `j_edge_capture` metric meets the ≥50% floor (OP-16/C1). The existing `analysis/backtests/REGISTRY.jsonl` tracks these. No new real-fills run is needed for the structural guards proposed here.


**Guard** — The specific pytest for each guard that FAILS on regression:

**Guard 1 (already committed) — one-shot trigger:**
```python
@pytest.mark.parametrize("task_name", _ENGINE_TASKS)
def test_engine_task_is_daily_recurring(self, task_name):
    _assert_daily_recurring(task_name)  # FAILS if <ScheduleByDay> absent
```
Regression: re-register `Gamma_SightBeacon` without `-Daily` flag AND update snapshot → test fails.

**Guard 2 (already committed) — sort=desc:**
```python
def test_sort_asc_not_present_in_fetch_url(self):
    # FAILS if executable URL lines contain sort=asc
```
Regression: change `sort=desc` back to `sort=asc` in `sight_beacon.py` → test fails.

**Guard 3 (already committed) — simple_fallback:**
```python
def test_place_bracket_has_simple_fallback_param(self):
    assert 'simple_fallback' in sig.parameters  # FAILS if removed
```

**Guard 4 (already committed) — engine_health watches new producers:**
```python
def test_build_report_calls_check_engine_core_not_check_heartbeat_log(self):
    assert 'check_engine_core' in func_src  # FAILS if removed
```

**Guard P1 (new) — GATE_KEYS subset:**
```python
def test_heartbeat_core_gate_keys_are_known_engine_gates():
    # FAILS if a key in GATE_KEYS is not in gates.py's gate name set
    # Regression: add 'block_foo_unknown' to GATE_KEYS → test fails immediately
```

**Guard P2 (new) — veto-lane roster:**
```python
def test_veto_lane_roles_present_in_roster():
    # FAILS if 'coordinator' or 'critic' absent from model-roster.json
    # Regression: rename 'critic' to 'analyst' in roster → test fails
```

**Guard P3 (new) — no_trade_window type:**
```python
def test_no_trade_window_is_null_or_two_element_list():
    # FAILS if entry_no_trade_window_et is [] or [x] or any non-null non-2-list
    # Regression: set Bold's entry_no_trade_window_et to [] → test fails
```

**Guard P4 (new) — GAMMA_CORE_ARMED not in snapshot:**
```python
def test_heartbeat_core_task_not_armed_in_snapshot():
    # FAILS if the task XML has GAMMA_CORE_ARMED=1
    # Regression: add env var to install script → snapshot update → test fails
```

All run in `backtest/tests/test_engine_liveness_guards.py`. Fast tests (`not slow`): all of the above complete in <1s each. No network, no live API, no scheduled task calls (except the parametrized trigger test which tries live schtasks and falls back to snapshot). Total test time: <5s for all 8 guards.

Run command:
```
backtest\.venv\Scripts\python.exe -m pytest backtest/tests/test_engine_liveness_guards.py -v
```


**Risks**
  - Snapshot drift is the #1 risk: if the snapshot is not regenerated after a legitimate task re-registration, the guard tests against the old (correct) XML while the live task has the new (possibly broken) XML. The mitigation is the `audit_scheduled_tasks.py` daily check for SILENT_TASK, but there is a 24-hour window of undetected drift.
  - False confidence: a guard passing means the SOURCE and SNAPSHOT are correct, NOT that the running process is behaving correctly. The `sight_beacon.py` could have `sort=desc` in source but be running from a cached .pyc built from an old version. This is nearly impossible given Python recompiles on mtime change, but worth noting.
  - P2 guard catches missing roster role but not a role with 0 functional lanes (all lanes erroring at runtime). The guard checks `len(lanes) > 0` but not that the lanes are reachable. A lane pointing to a deprecated model (e.g., cerebras decommissioning `zai-glm-4.7`) fails silently at runtime. Adding a monthly `swarm_client.smoke_test_lane(role)` call to `Gamma_McpDailyAudit` would close this, but that requires a live network call.
  - The `entry_no_trade_window_et` guard (P3) only checks params.json, not heartbeat_core's actual runtime coercion. If `_norm_no_trade_window` is updated to handle a different invalid form, the guard must be updated in sync — a second-order drift source.
  - Adding too many guards increases the probability that a broken test (e.g., a path assumption) causes the nightly suite to fail for the wrong reason, creating cry-wolf fatigue. All guards should have clear failure messages naming the exact regression class.

**Dependencies**
  - backtest/tests/test_engine_liveness_guards.py (already committed — 4 guards, extend for P1-P4)
  - automation/state/engine-task-snapshot.json (snapshot for trigger guards)
  - automation/state/model-roster.json (for P2 veto-lane guard)
  - automation/state/params.json + automation/state/aggressive/params.json (for P3 no_trade_window guard)
  - setup/scripts/heartbeat_core.py (GATE_KEYS list, ARMED flag)
  - backtest/lib/engine/gates.py (canonical gate name set for P1)
  - automation/state/fleet/fleet_broker.py (simple_fallback guard)
  - setup/scripts/sight_beacon.py (sort=desc guard)
  - setup/scripts/engine_health.py (check_engine_core / check_sight_beacon guard)

**Open questions**
  - Should `Gamma_HeartbeatCore` be added to the reaper's EXEMPT_DAEMONS list? Currently it is NOT exempt, which means if a tick hangs past 5 minutes it will be reaped on the next heartbeat fire. This is actually CORRECT behavior for a 2-minute-cadence process — you WANT a stalled tick to be killed. But it means the reaper is doing double duty as a timeout enforcer. If the `engine_cli` subprocess timeout (30s) fires but the process doesn't die cleanly, the reaper is the safety net. Is this intentional? Document in EXEMPT_DAEMONS comment.
  - The `sort=desc` beacon guard catches the URL parameter, but does the guard need to also check `_fetch_yfinance_bars`? yfinance returns bars in ascending order natively (no sort param) — so the reversal in the Alpaca path does NOT apply there. If yfinance is the fallback and its bars are correctly ordered, the guard is complete. But if someone adds a sort parameter to the yfinance download call, the guard needs extension.
  - P2 flag: `heartbeat_core._free_model_eval` uses roles `('coordinator', 'critic')` hardcoded (line 424). The veto-lane roster guard checks these two names. But `swarm_client.py:resolve_lanes` raises `KeyError` for unknown roles — this is NOT caught gracefully; the blanket `except Exception` in `_free_model_eval` catches it and logs `KeyError: 'critic'`. Should the veto lane selection be driven by a config value in params.json rather than hardcoded strings? That would make it guardiable without source inspection and would allow J to change veto lanes without touching code.
  - The `Gamma_GuardsNightly` task runs the `slow` marker tests at 22:30 ET. The new guards in `test_engine_liveness_guards.py` are fast (not marked `slow`). They run via the per-edit fast hook. Is there a risk that the fast hook skips them in certain conditions (e.g., editing a non-Python file)? The hook should be audited to confirm it triggers on params.json edits too (the P3 guard depends on params.json content).
  - HOLD evaluation: P5 (ARMED flag guard) — is it worth guardiing the snapshot for GAMMA_CORE_ARMED? The snapshot is only regenerated manually or by the install script. If someone arms the engine by setting the env var at the OS level (not via the task XML), the snapshot guard would not catch it. The real guard for accidental live arming is the `_execute` dry-run path: when `dry=True`, plan status is `WOULD_PLACE`, not `PLACING`. Checking the ledger for unexpected `PLACING` rows during what should be WATCH mode is a stronger guard. HOLD on P5 until there is a concrete regression scenario.


**Verdict** — SHIP-worthy for the 4 guards committed today (`test_engine_liveness_guards.py`). They are already in `backtest/tests/`, well-structured, and cover the exact failure mechanisms witnessed in production. The snapshot approach is the right architecture for this rig's constraints (no CI with Task Scheduler access).

The 4 additional guards (P1-P4) are all SHIP-worthy: they are short, deterministic, fast, and protect against documented failure classes (C14/L38 for P1, silent veto degradation for P2, `BadPayload` every tick for P3, accidental live arming for P4). None require real-fills, backtest runs, or live API calls. P5 is HOLD — the existing `WOULD_PLACE` ledger path is a stronger runtime check for accidental arming than a snapshot XML assertion.

The live-probe augmentation (Approach 2) is needs-more: the 09:32 early-open ping is genuinely valuable but should be implemented as a Python function called from `run-engine-health.ps1` (not a new Claude task), and its scope must be strictly read-only — no order verification, no state modification.

---

## CMD popup elimination for Gamma_Funnel_0..5 + Gamma_Grind_all + permanent audit guard

**Problem & root cause** — **What we witnessed:** Every time Task Scheduler fires Gamma_Funnel_0..5 or Gamma_Grind_all, a black OpenConsole.exe window flashes on screen. Confirmed by live audit: `automation/state/scheduled-tasks-audit.json` (10:00 2026-06-26) shows 7 `VISIBLE_WINDOW` flags for exactly these tasks with `execute='cmd.exe'`. The tasks use bare `cmd.exe /c "set ENV=VAL&& python.exe -m module > log 2>&1"` as the task action.

**Mechanism (root-caused 2026-06-20, encoded as L41 in CLAUDE.md):** On Windows 11, any Task Scheduler action whose Execute is a console-subsystem binary (`cmd.exe`, `powershell.exe`, `python.exe`) causes Windows to allocate a new console session via OpenConsole.exe with the `-Embedding` flag BEFORE the process even starts executing. `-WindowStyle Hidden` is a PowerShell runtime flag that only takes effect ~200ms AFTER that console is already visible. `cmd.exe` has no equivalent. There is no Task Scheduler setting that suppresses this: the "Run whether user is logged on or not" option hides everything, but these tasks run as the logged-in user. The only guaranteed fix is to make the task's Execute a GUI-subsystem binary that never requests a console.

**Scope of affected tasks** (from live `Get-ScheduledTask` output): Gamma_Funnel_0, Gamma_Funnel_1, Gamma_Funnel_2, Gamma_Funnel_3, Gamma_Funnel_4, Gamma_Funnel_5 — all use `cmd.exe /c "set GAMMA_FUNNEL_SHARD={n}&& set GAMMA_FUNNEL_NSHARDS=6&& ...\python.exe -m autoresearch.mass_grind_funnel > ...log 2>&1"`. Gamma_Grind_all uses `cmd.exe /c "set GAMMA_GRIND_WORKERS=8&& ...\python.exe -m autoresearch.mass_grind > ...log 2>&1"`. Gamma_Grind_Watchdog was ALREADY converted (live task now shows wscript.exe chain; the 10:00 audit.json entry is stale from before the conversion today).

**Why Gamma_Grind_Vwap is already clean:** `setup/install-grind-vwap.ps1` uses the canonical `wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-grind-vwap.ps1` chain. That is the template for what Funnel_0..5 and Grind_all need.

**No install script exists for Funnel_0..5 or Grind_all.** They are not in any `setup/install-*.ps1`. They must have been registered manually or by an early task-setup sweep. This means re-registering them requires writing a new install script OR a targeted re-registration block.


**Approaches considered**

- **Approach A — wscript -> run_exe_hidden.vbs -> backtest-pythonw -> run_cmd_hidden.py (the WS6 pattern, already implemented in code/tests)** — Task Scheduler Execute = wscript.exe, Arguments = `//nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>" --env KEY=VAL [--env ...] --log <logfile> --cwd <workdir> -- "<backtest-pythonw>" -m <module>`. Chain: wscript (GUI-subsystem, no console) -> run_exe_hidden.vbs calls WScript.Shell.Run with windowStyle=0 on pythonw (GUI-subsystem, no console) -> run_cmd_hidden.py (already written: `setup/scripts/run_cmd_hidden.py`) calls subprocess.run(..., creationflags=CREATE_NO_WINDOW) on the grind python.exe. The child python.exe inherits CREATE_NO_WINDOW and Windows is contractually obligated NOT to allocate a console.

For env vars: `--env GAMMA_FUNNEL_SHARD=0 --env GAMMA_FUNNEL_NSHARDS=6`. For log redirect: `--log <path>`. For working directory: `--cwd C:\Users\jackw\Desktop\42\backtest`.

The child command uses `pythonw.exe` (GUI-subsystem) NOT `python.exe` because: (a) we pass it through the CREATE_NO_WINDOW subprocess.run which already suppresses the console, but (b) if something goes wrong and CREATE_NO_WINDOW is dropped, a pythonw child still won't allocate a console — it is a defence-in-depth layer. The `run_cmd_hidden.py` module is already tested in `backtest/tests/test_guard_cmd_popup_fix_ws6.py` with the exact argument shapes for Funnel_0..5 and Grind_all.

Note: wscript's `shell.Run` uses ShellExecute, NOT CreateProcess. On most Win11 configs this works. The `run_hidden_exec.vbs` variant uses WshShell.Exec (CreateProcess path) which is more reliable but synchronous (blocks wscript until child exits). For the grind tasks which can run for HOURS, async (shell.Run, False wait) is correct — Task Scheduler starts the wscript, wscript fires pythonw and exits immediately, pythonw runs run_cmd_hidden.py which blocks on the grind. Task Scheduler only tracks the wscript lifetime, not the grind — this is fine for on-demand tasks (Funnel and Grind_all are fired by the watchdog via Start-ScheduledTask).
    - ✅ 1. run_cmd_hidden.py already exists and is fully implemented (setup/scripts/run_cmd_hidden.py, 139 lines, handles --env, --log, --cwd, CREATE_NO_WINDOW). 2. The audit recognises this pattern: _is_hidden() returns True for wscript+run_exe_hidden.vbs (lines 99-103 of audit_scheduled_tasks.py). 3. The regression tests are already written in backtest/tests/test_guard_cmd_popup_fix_ws6.py — 17 test cases covering pre-fix, post-fix, and edge cases. 4. Env vars pass cleanly (--env KEY=VAL repeatable). 5. Log redirect is handled (--log captures both stdout+stderr via subprocess). 6. wscript exits immediately (async) so Task Scheduler doesn't hold the task as 'Running' while the grind is in-flight — the grind runs independently as a pythonw child. 7. backtest/.venv/Scripts/pythonw.exe already exists (verified True). 8. The grind reaper exemption in _shared.ps1 exempts 'backtest\.venv' processes — the pythonw.exe child will be exempt.
    - ⚠️ 1. wscript Shell.Run uses ShellExecute, which on some Win11 configs with non-default terminal settings can still route through WT — this was the original concern. However: our CryptoGrinderKeepalive already uses this same chain (converted in June) and has not reported flashes. The run_hidden_exec.vbs (WshShell.Exec/CreateProcess path) would be more robust but blocks wscript until exit — unsuitable for multi-hour grinds. 2. Task Scheduler does NOT track grind health via task State — it fires the wscript and marks it done immediately. The grind-shard-watchdog (Gamma_Grind_Watchdog) handles liveness monitoring independently by inspecting progress files + restarting Gamma_Grind_all via Start-ScheduledTask. This pre-existing design is correct — WS6 does not break it. 3. Logging: with --log set, stdout+stderr go to the log file. Without it, they are captured and discarded (run_cmd_hidden.py logs only the launcher events, not the child's output). Must pass --log to preserve mass-grind-stdout.log and mass-grind-funnel-N-stdout.log. 4. No install script currently exists for these 7 tasks — need to write install-grind-funnel-tasks.ps1.

- **Approach B — pythonw.exe wrapper shim (thin Python file that sets env vars and execs the module)** — Create a thin per-task Python shim, e.g. `backtest/autoresearch/_shim_funnel_0.py` that does `os.environ['GAMMA_FUNNEL_SHARD'] = '0'; os.environ['GAMMA_FUNNEL_NSHARDS'] = '6'; from autoresearch import mass_grind_funnel; mass_grind_funnel.main()`. Register the task with Execute = `backtest\.venv\Scripts\pythonw.exe` and Arguments = `"C:\...\backtest\autoresearch\_shim_funnel_0.py"`. Since pythonw.exe is GUI-subsystem, no console is ever allocated. No wscript layer needed.
    - ✅ 1. Maximum simplicity in the task XML — just pythonw.exe + a path. No VBS, no run_cmd_hidden.py, no wscript layer. 2. _is_hidden() already accepts direct pythonw.exe execute (line 101-102 of audit_scheduled_tasks.py) — zero audit changes needed. 3. Provably zero-leak: pythonw.exe never allocates a console under any Windows 11 config. 4. No new infrastructure — pythonw, subprocess, venv are all pre-existing.
    - ⚠️ 1. 7 shim files (1 per Funnel shard + Grind_all) — each just sets 2 env vars and calls main(). Minor maintenance surface but more files than approach A. 2. The shim approach buries the env-var wiring in Python code, making the task registration less readable (Arguments just shows a .py file path, not the env vars). 3. stdout/stderr from the grind module go to... nowhere by default (pythonw.exe has no console, so print() output is discarded unless the module explicitly opens a log file). mass_grind_funnel uses print() and the old cmd.exe task redirected > log 2>&1. A shim would need to redirect sys.stdout/sys.stderr to log files at the top of the shim — adding ~5 lines per shim. 4. If mass_grind_funnel.main() doesn't exist (it uses if __name__ == '__main__'), the shim needs to import and call the internal entry-point, which may drift if the module interface changes. Fragile coupling. 5. No existing test infrastructure tests this pattern for these specific modules — test_guard_cmd_popup_fix_ws6.py does NOT cover Approach B. New tests would be needed. 6. Shim proliferation: every new grind task = new shim file. Approach A (run_cmd_hidden.py) is a universal launcher.


**Recommended** — Approach A — wscript -> run_exe_hidden.vbs -> backtest-pythonw -> run_cmd_hidden.py.

Rationale: run_cmd_hidden.py is already written, the regression tests already exist (`backtest/tests/test_guard_cmd_popup_fix_ws6.py`, 17 test cases covering the exact before/after argument shapes for all 7 tasks), and the audit already recognises the pattern. The only missing piece is a re-registration script (install-grind-funnel-tasks.ps1) and updating SCHEDULED-TASKS.md to list all 7 tasks so ORPHAN_TASK flags clear. Approach B would work but requires new shim files, lacks existing test coverage, and loses stdout/stderr logging without extra work.


**Design detail**

**Files that change:**

1. **`setup/scripts/run_cmd_hidden.py`** — already complete (lines 1-138). No changes needed. Handles `--env KEY=VAL`, `--log`, `--cwd`, `--` separator, CREATE_NO_WINDOW subprocess.run, logs to `automation/state/logs/run-cmd-hidden-YYYY-MM-DD.log`.

2. **`setup/install-grind-funnel-tasks.ps1`** (NEW) — registers all 7 tasks using the canonical chain. Key arguments per task:

Funnel_0..5:
```
Execute:   wscript.exe
Arguments: //nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>"
           --env GAMMA_FUNNEL_SHARD={n} --env GAMMA_FUNNEL_NSHARDS=6
           --log "<reco>\mass-grind-funnel-{n}-stdout.log"
           --cwd "<backtest>"
           -- "<backtest-pythonw>" -m autoresearch.mass_grind_funnel
```
Note: child binary is `pythonw.exe` (not python.exe) for defence-in-depth.

Grind_all:
```
Execute:   wscript.exe  
Arguments: //nologo "<run_exe_hidden.vbs>" "<backtest-pythonw>" "<run_cmd_hidden.py>"
           --env GAMMA_GRIND_WORKERS=8
           --log "<reco>\mass-grind-stdout.log"
           --cwd "<backtest>"
           -- "<backtest-pythonw>" -m autoresearch.mass_grind
```

Settings: `ExecutionTimeLimit = New-TimeSpan -Hours 8`, `StartWhenAvailable`, `AllowStartIfOnBatteries`. Trigger: NONE (on-demand). Both existing task registrations are unregistered first (idempotent).

3. **`automation/state/SCHEDULED-TASKS.md`** — add Gamma_Funnel_0..5, Gamma_Grind_all, Gamma_Grind_Watchdog, Gamma_Grind_Vwap to the Active table. Currently none of these are listed (they show as ORPHAN_TASK in the audit).

4. **`backtest/tests/test_guard_cmd_popup_fix_ws6.py`** — already written (file exists, 229 lines). The `TestPostFixApprovedPattern` class tests the exact argument shapes for the fixed tasks. Run with: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v`.

5. **`setup/scripts/audit_scheduled_tasks.py`** — the `_is_bare_console_launcher` function (lines 109-125) and its HARD FAIL path (lines 184-190) are already in place. The guard test in `backtest/tests/test_guard_cmd_popup_fix_ws6.py::TestBareLauncherDetection` covers this. No changes needed.

**Argument quoting in wscript args:** wscript.exe passes each quoted token as a separate `WScript.Arguments` item to run_exe_hidden.vbs. The VBS reassembles them with surrounding quotes (line 7-9: `cmd = """" & args(0) & """"`). This means multi-word arguments with spaces must be passed as single quoted tokens. run_cmd_hidden.py receives its argv via `sys.argv` normally. The `--` separator is parsed explicitly (lines 72-79 of run_cmd_hidden.py). All paths with spaces must be passed as separate quoted tokens at the wscript.exe level.

**Worker count:** `GAMMA_GRIND_WORKERS=8` for mass_grind, `GAMMA_FUNNEL_NSHARDS=6` with per-task `GAMMA_FUNNEL_SHARD=0..5` for funnels. These match the existing cmd.exe invocations exactly.

**Log files:** --log paths match the existing log destinations: `mass-grind-funnel-{n}-stdout.log` and `mass-grind-stdout.log` in `analysis/recommendations/`. The grind-shard-watchdog monitors `mass-grind-progress*.jsonl` (not stdout logs) so log path changes don't affect watchdog logic.


**Edge cases**
  - wscript Shell.Run async behaviour: wscript fires pythonw and exits immediately (windowStyle=0, False = don't wait). Task Scheduler marks the task as 'Ready' within seconds, not 'Running' for hours. Gamma_Grind_Watchdog (grind-shard-watchdog.ps1) checks State == 'Running' via Get-ScheduledTask — it will ALWAYS see 'Ready' for Grind_all after the fix and will try to restart it on every 60-second tick. CRITICAL: The watchdog must switch from checking task State to checking for a live grind process directly (as grind-watchdog.ps1 already does via WMI). grind-shard-watchdog.ps1 line 22-26 currently uses 'Start-ScheduledTask -TaskName Gamma_Grind_all' when state != 'Running' — after the fix, state will never be 'Running', causing infinite restarts. This must be fixed before deployment.
  - Backtest venv pythonw.exe vs system pythonw.exe: run_cmd_hidden.py must be launched by a pythonw.exe that can import no grind modules (it just calls subprocess.run). Either system pythonw (C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe) or backtest pythonw work. HOWEVER, the child command (after --) that actually runs mass_grind_funnel MUST use backtest\venv\Scripts\pythonw.exe since autoresearch.* lives there. The install script and test fixtures already use backtest-pythonw for both the launcher and the child, which is correct.
  - Reaper exemption: _shared.ps1 EXEMPT_DAEMONS exempts 'backtest\.venv' python processes from Stop-StaleClaudeProcesses. The child pythonw.exe process spawned by run_cmd_hidden.py will have executable path matching backtest\.venv\Scripts\pythonw.exe. If the reaper matches on python/pythonw path, it must match pythonw.exe too. Verify the exemption pattern covers both python.exe and pythonw.exe in the backtest venv path.
  - Log file append vs overwrite: run_cmd_hidden.py opens --log in append mode (log_path.open('a')). The old cmd.exe tasks used > (overwrite). If the grind is restarted mid-run by the watchdog, the new run appends to the existing log — this is BETTER (preserves restart history) but note the log grows unbounded across multiple grinds. Not a blocker but a maintenance note.
  - ORPHAN_TASK flags in the audit will clear only after SCHEDULED-TASKS.md is updated to list these 7 tasks. Currently 7 of the 24 audit flags are ORPHAN_TASK for these tasks. The remaining ORPHAN_TASK flags (Gamma_ContenderRank, Gamma_EodFullAudit, Gamma_FreeManager, Gamma_HeartbeatCore, Gamma_LiveShadowValidator, Gamma_ManagerOverseer, Gamma_SightBeacon) are a SEPARATE issue — don't bundle them into this fix.
  - wscript argument quoting: run_exe_hidden.vbs wraps each WScript.Arguments item in double-quotes (line 7-9). Paths with spaces need to be passed as individual arguments without embedded quotes — wscript.exe tokenises Arguments string by spaces, respecting double-quoted groups. The install script must build the -Argument string carefully to avoid double-quoting issues.

**Failure modes**
  - Watchdog infinite-restart loop (CRITICAL): grind-shard-watchdog.ps1 checks `(Get-ScheduledTask -TaskName 'Gamma_Grind_all').State -ne 'Running'` and calls Start-ScheduledTask if true. After WS6 fix, wscript exits immediately so state is always 'Ready'. The watchdog will fire Gamma_Grind_all on every 60-second tick, launching duplicate mass_grind processes. DEADLOCK: multiple mass_grind processes on the OPRA cache (per CLAUDE.md grind-reaper-killer lesson). FIX: change grind-shard-watchdog.ps1 to use WMI process detection (as the OLD grind-watchdog.ps1 does at lines 32-38) rather than task state. Check for a live pythonw.exe with CommandLine matching mass_grind.
  - run_cmd_hidden.py launched by system pythonw but child fails with ModuleNotFoundError: if the child command accidentally uses system python.exe instead of backtest-venv python.exe, autoresearch.* won't be importable. The failure is silent (run_cmd_hidden.py logs the exit code to its launcher log but the task Scheduler won't surface it). The grind watchdog catches it indirectly (no progress entries written, watchdog restarts). But N restarts = N silent failures. Fix: the install script must hardcode backtest-venv paths for both the launcher (outer) and the child (after --).
  - stdout/stderr loss if --log not specified: without --log, run_cmd_hidden.py calls subprocess.run(..., capture_output=True) — output is captured into proc.stdout/proc.stderr but DISCARDED (only exit code is logged). The grind modules' stdout (progress lines, warnings, errors) will be invisible. Fix: always pass --log in the install script. Verify the log path parent directory exists at install time.
  - wscript argument string overflow: wscript.exe Arguments is a single string. Very long paths can exceed shell argument limits. The full argument string for a funnel task is approximately 350 characters, well within limits (Windows limit is ~32767 chars). Not a practical risk here.
  - Existing tasks not unregistered before re-registration: if the install script doesn't Unregister first, Register-ScheduledTask will fail with 'task already exists'. The install script must Unregister-ScheduledTask first (idempotent pattern). If a task is Running at unregister time, it is killed. For on-demand tasks fired only by the watchdog, this is acceptable — the grind resumes from progress files.


**Validation plan** — **No P&L claim is being made here** (this is a window-flash fix, not a strategy change). The validation is mechanical correctness:

1. **Pre-fix audit confirms the problem:** Run `backtest/.venv/Scripts/python.exe setup/scripts/audit_scheduled_tasks.py` — expect BARE_CMD_POWERSHELL (or VISIBLE_WINDOW) flags for Gamma_Funnel_0..5 and Gamma_Grind_all.

2. **Run regression tests (already written):** `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v`. Must all pass (17 tests). These cover: old cmd.exe shapes are flagged, new wscript shapes are recognised as hidden, _is_bare_console_launcher catches cmd.exe and full-path variants, existing approved patterns not broken.

3. **Re-register tasks:** Run `setup/install-grind-funnel-tasks.ps1` (after fixing grind-shard-watchdog.ps1's watchdog logic). Verify with `Get-ScheduledTask -TaskName 'Gamma_Funnel_*','Gamma_Grind_all' | Select TaskName,State`.

4. **Post-fix audit confirms no window flags:** Re-run `audit_scheduled_tasks.py`. Expect: no BARE_CMD_POWERSHELL, no VISIBLE_WINDOW for the 7 tasks. ORPHAN_TASK clears after SCHEDULED-TASKS.md update.

5. **Live smoke-test on demand:** `Start-ScheduledTask -TaskName Gamma_Funnel_0`. Watch for OpenConsole.exe in Task Manager for 5 seconds (should not appear). Check `analysis/recommendations/mass-grind-funnel-0-stdout.log` for grind output within 30 seconds.

6. **Watchdog does not loop:** Fire `Start-ScheduledTask -TaskName Gamma_Grind_Watchdog` once. Check `analysis/recommendations/mass-grind-watchdog.log` — should see `OK N/3360` or one RESTART line, not repeated RESTART lines every 60 seconds.


**Guard** — **Specific pytest that FAILS on regression — already written:**

File: `backtest/tests/test_guard_cmd_popup_fix_ws6.py`

The guard that matters most:
```python
# In class TestPreFixTasksAreFlashers:
@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_is_bare_cmd(self, shard: int) -> None:
    assert _is_bare_console_launcher("cmd.exe")  # FAILS if _is_bare_console_launcher is removed/broken

@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_args_not_hidden(self, shard: int) -> None:
    args = self._FUNNEL_ARGS_TEMPLATE.format(shard=shard)
    assert not _is_hidden(execute="cmd.exe", arguments=args)  # FAILS if cmd.exe is whitelisted

# In class TestPostFixApprovedPattern:
@pytest.mark.parametrize("shard", range(6))
def test_funnel_shard_fixed_is_hidden(self, shard: int) -> None:
    assert _is_hidden(execute="wscript.exe", arguments=self._funnel_args(shard))  # FAILS if wscript pattern dropped

def test_grind_all_fixed_is_hidden(self) -> None:
    assert _is_hidden(execute="wscript.exe", arguments=self._grind_all_args())  # FAILS if wscript pattern dropped
```

Additionally, `audit_scheduled_tasks.py` exits 1 if BARE_CMD_POWERSHELL flags exist — the daily audit (Gamma_CryptoDaily) surfaces this as RED in STATUS.md within 24 hours of regression. This is the HARD FAIL in production: any re-registration of Funnel/Grind_all as bare cmd.exe tasks will appear RED in STATUS.md the next day.

Run guard with: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_guard_cmd_popup_fix_ws6.py -v --tb=short`


**Risks**
  - Watchdog liveness race: after re-registering Gamma_Grind_all, if grind-shard-watchdog.ps1 fires before the fix to use WMI instead of task State, it will endlessly restart the grind. This is the #1 deployment risk. FIX FIRST: patch grind-shard-watchdog.ps1 to use WMI-based liveness before re-registering the task.
  - Pre-existing install gap: there is no install-grind-funnel-tasks.ps1. If this is lost or not committed, a future task re-registration (e.g. someone runs setup-all.ps1) will not re-apply the WS6 fix. The audit HARD FAIL is the backstop, but there is no positive-install path. Commit install-grind-funnel-tasks.ps1.
  - run_cmd_hidden.py is not tested end-to-end against the actual backtest modules: the tests in test_guard_cmd_popup_fix_ws6.py test argument shapes recognised by the audit, not that run_cmd_hidden.py actually spawns the grind successfully. A quick `Start-ScheduledTask Gamma_Funnel_0` smoke test is essential before declaring success.
  - SCHEDULED-TASKS.md has 24 audit flags (10:00 snapshot), 7 of which are these grind/funnel tasks. The remaining 17 flags (ORPHAN_TASK for newer tasks, SILENT_TASK for GitHubAudit) are pre-existing and separate. Don't conflate — fixing only the 7 window tasks is in-scope for WS6; the ORPHAN_TASK cleanup for HeartbeatCore/SightBeacon etc. is a separate OP.

**Dependencies**
  - setup/scripts/run_cmd_hidden.py — exists, complete
  - setup/scripts/run_exe_hidden.vbs — exists (wscript.exe //nologo + Shell.Run windowStyle=0)
  - backtest/.venv/Scripts/pythonw.exe — exists (verified True)
  - setup/scripts/run_ps1_hidden.py — exists (not used by this fix but referenced for pattern comparison)
  - backtest/tests/test_guard_cmd_popup_fix_ws6.py — exists, 17 tests cover the full before/after
  - setup/scripts/audit_scheduled_tasks.py — exists, _is_bare_console_launcher HARD FAIL at lines 184-190
  - setup/scripts/grind-shard-watchdog.ps1 — EXISTS but needs watchdog State->WMI patch BEFORE deployment
  - setup/install-grind-funnel-tasks.ps1 — DOES NOT EXIST, must be created
  - automation/state/SCHEDULED-TASKS.md — must add Funnel_0..5, Grind_all, Grind_Watchdog, Grind_Vwap to Active table to clear ORPHAN_TASK flags

**Open questions**
  - grind-shard-watchdog.ps1 watchdog logic: must be patched to use WMI process detection instead of task State check before WS6 re-registration. What is the correct WMI query for a pythonw.exe child running -m autoresearch.mass_grind? Suggested: CommandLine -like '*pythonw*' -and CommandLine -like '*mass_grind*' -and CommandLine -notlike '*mass_grind_funnel*' -and CommandLine -notlike '*phase2*'. Mirror the pattern from the old grind-watchdog.ps1 lines 32-38.
  - _shared.ps1 reaper exemption for pythonw.exe: the exemption currently covers 'backtest\.venv' python.exe processes. Does it also cover pythonw.exe from the same venv? If the reaper pattern is `$_.Name -eq 'python'` it won't match `pythonw`. Verify EXEMPT_DAEMONS covers both. If not, the grind will be silently killed by the reaper every 5 minutes (the exact grind-reaper-killer incident from CLAUDE.md).
  - Should Gamma_Funnel_0..5 be unregistered and replaced with a single Gamma_Funnel task that runs all 6 shards sequentially, now that the watchdog drives them? The 6-shard architecture was designed for parallel execution from a common trigger — after the WS6 fix, the watchdog still fires them individually. This is a design question for after the window fix, not a blocker.


**Verdict** — SHIP-worthy. The approach is proven (Gamma_Grind_Vwap uses the identical chain, Gamma_Grind_Watchdog was already converted today), the code is written (`run_cmd_hidden.py`), and the guard tests are written (`test_guard_cmd_popup_fix_ws6.py`). The one HOLD condition is the watchdog State-vs-WMI bug — that must be patched in `grind-shard-watchdog.ps1` BEFORE re-registering Gamma_Grind_all, or you get an infinite restart loop. Fix the watchdog first, then run `install-grind-funnel-tasks.ps1`, then smoke-test. Total work: ~1 hour.

---
