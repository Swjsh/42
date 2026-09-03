# FILTER 5 (ribbon) HTF-BEAR FORGIVENESS — frozen pre-reg (2026-09-03)

**Queue item:** `G1-FILTER5-VS-REJECTION-SETUPS` (CRITICAL, engine-edge, pre-reg required), `automation/overnight/queue.md` line 188, filed 2026-07-27, FABLE-REVIEW AMENDMENTS same line, same date evening.

**Frozen at:** 2026-09-03 05:06:25 Thursday EDT (`python setup/scripts/et_clock.py`, run this session — box is Mountain, ET = local+2; bash `TZ=` is wrong here per L21/L42/L49/L56/L60).

**Frozen before any run.** This is a DOCUMENT-ONLY session: no code, params, or queue.md edits; no replay/OPRA run executed. Everything below is a specification for a future build/run session, not a result.

**Prior-art check (mandatory, run first):** grepped `analysis/recommendations/` for `filter5|filter_5|ribbon.*lag|htf_15m|bearish_reversal_bypass` before writing anything. Hits: `prereg-filter5-ribbon-2026-07-31.json` / `filter5-ribbon-2026-07-31.md` exist and are CLOSED (both arms NULL) — but they test a **different candidate**: ARM_A deletes filter 5 outright (both directions), ARM_B bypasses filter 5 for *any* level-anchored trigger (bull+bear, no HTF condition). Neither arm conditions the bypass on `htf_15m_stack`. `prereg-structure-shift-confirmation-2026-07-28.json` / `structure-shift-replay-2026-07-28.json` test a *different* OR-alternative to filter 5 (price-structure break-of-swing-low via `detect_structure_shift_bear`, flag `structure_shift_confirmation`) — also not HTF-conditioned, and that arm's own bull-side no-op note is why it does not answer this study either (see queue text). No existing prereg tests the specific three-conjunct HTF-bear forgiveness this queue item asks for. This file is therefore new, not a duplicate.

---

## 1. Candidate rule (exact, no hand-tuning)

**In `evaluate_bearish_setup` (`backtest/lib/filters.py`), forgive filter 5 (do not append blocker 5) when ALL THREE hold at the trigger bar, in addition to the existing filter-5 check:**

1. `"level_rejection" in triggers` — i.e. `detect_level_rejection(ctx.bar, ctx.levels_active)` fired (verified call site `filters.py:1710`; trigger appended `filters.py:1759`).
2. `"confluence" in triggers` — i.e. `detect_confluence(rejection_level, ctx.multi_day_levels)` is not None (verified call site `filters.py:1712`; trigger appended `filters.py:1776-1777`).
3. `ctx.htf_15m_stack == "BEAR"` — the 15-min HTF ribbon stack **agrees** with the trade direction. **Verified as read**: today `htf_disagrees = ctx.htf_15m_stack == "BULL"` (`filters.py:1709`) is the ONLY current consumer of `htf_15m_stack` on the bear path, and it is a **-1 SOFT score demerit** applied at `filters.py:1916-1917`, never a hard blocker. `htf_15m_stack == "BEAR"` is therefore the *no-demerit* (agreement) case today — the candidate proposes promoting that same agreement signal from "no penalty" to "affirmative override of the ribbon-stack veto," a materially different (stronger) use of the same field.

**Forgiveness site**: mirror the existing `trendline_chop_demerit` / `bearish_reversal_demerit` pattern exactly (`filters.py:1817-1828`, `1839-1879`) — if blocker 5 is present and the 3-conjunct condition holds, `blockers.remove(5)` and apply a `-1` score demerit (`htf_bear_forgiveness_demerit`), never a free pass. New flag, default `False`, byte-identical when off: `htf_bear_ribbon_forgiveness: bool = False`.

**Falsifiable claim (H1):** the cohort of bear setups where `level_rejection AND confluence AND htf_15m_stack=="BEAR"` fire while the ribbon is NOT BEAR-stacked (i.e. filter 5 is the sole thing blocking them, or blocks them alongside only non-structural filters forgiven separately) has **positive real-OPRA expectancy walked through the real exit manager**, is **NOT explained by the same ribbon-flip-exit round-trip mechanism that nulled the 07-31 study** (§ "by-product" finding in `filter5-ribbon-2026-07-31.md` — 76.2% of that study's unlocked trades exited on `ribbon_flip_back` within minutes), and clears the standing four ratification gates over BOTH the recent window and the deep population. If it does not, H0 stands: filter 5 stays structurally required and the 07-27 loss is disclosed as a single-anecdote cost with no armed fix.

**Structural note carried over from the queue's Fable-amendment #1, verified unchanged**: `STRUCTURAL_REQUIRED = {1, 2, 3, 4, 5}` (`filters.py:1933`, `+{11}` only when `sweep_blocker_enabled`) — filter 5 is excluded from `allow_one_blocker`'s slack pool regardless of how many other filters pass. Any arm must therefore create a NEW forgiveness path (as above); it cannot piggyback on `allow_one_blocker`.

---

## 2. Line-number drift since 2026-07-27 (verified, no logic change found)

The queue item cites `filters.py:1427-1430` (filter 5 bear) and `filters.py:1589-1607` (`bearish_reversal_bypass`). Re-read today:

| Item | Queue-cited (07-27) | Verified now (09-03) |
|---|---|---|
| Bear filter 5 block | `1427-1430` | `1650-1660` (`blockers.append(5)` at **1660**) |
| Bull filter 5 block | — | `1330-1332` (`blockers.append(5)` at **1332**) |
| `bearish_reversal_bypass` param + doc | `1589-1607` | doc block `1551-1556`; live logic `1839-1879` |
| `STRUCTURAL_REQUIRED` | not cited | `1933` (`{1,2,3,4,5}`) |
| `htf_15m_stack` bear consumer | not cited | `1709` (soft demerit only, applied `1916-1917`) |

Drift is ~220 lines, attributable to flags added after 07-27 (`vix_soft_mode_bull`, `structure_shift_confirmation` mirror block, `trendline_bypass_scope`, docstring growth) — confirmed by reading the intervening code; **the filter-5 bear/bull logic itself is unchanged in substance** from the queue's description. `bearish_reversal_bypass` remains fhh-only (`"fhh_level_rejection" in triggers"`, `filters.py:1850`), `ribbon.stack=="BULL"`-gated (`1853`), default `False` — confirmed still true, still NOT the mechanism this candidate needs (candidate requires `level_rejection`, not `fhh_level_rejection`, and is agnostic to ribbon stack rather than requiring BULL).

---

## 3. Populations

### 3a. Historical P1 population (backtest evidence)
- **Frame**: the 386-trading-day OPRA-cached inventory, 2025-01-02 .. 2026-07-22 (`analysis/edge-matrix/day-inventory-2026-07-23-summary.md`; confirmed elsewhere e.g. `analysis/edge-matrix/prereg-bear_level_rejection-fullhist-2026-07-23.json`). State lives in `backtest/data/` (SPY/VIX 5m CSVs) + real OPRA cached contract bars (`lib/option_pricing_real.load_contract_bars`). **Orchestrator replay**: `backtest/tools/engine_fullhist_replay.py` — named directly in `analysis/deep-research/BOLD-HARNESS-2026-08-01.md:34` as "the 386-day/116s walker." This study must extend the population forward to the current run date at build time (386 days is the frame as of 2026-07-22; a fresh run adds every trading day since, per the standing recency directive — memory `feedback_dynamic_market_recency_over_aggregate_2026_07_31`).
- **IS/OOS window scheme — chosen per playbook §4.5 (`markdown/research/BACKTESTING-PLAYBOOK.md:300-303`), NOT decided by feel**: §4.5's rule is *"if the knob's expected changed-trade fraction is < 33% of the population... prereg EQUAL-CHANGED-TRADE-COUNT buckets (`canonical_battery.py::equal_count_buckets`, n_buckets=4) instead of calendar windows; at/above 33%, calendar windows stand."*
  - **Expected changed-trade fraction, evidenced**: the live sole-blocker miner (§3b below) found exactly **1** bear-filter5-sole-blocked episode in a 20-trading-day rolling window against a ~191-trade CONTROL book (`filter5-ribbon-2026-07-31.md` Cohort B, full-window n=191). Even the STRICTLY BROADER 2026-07-31 study (filter 5 forgiven for ANY level-anchored bear trigger, no HTF gate) added only 21 trades over the FULL 386-day population against a 191-trade control book (~11%). This candidate is a **strict subset** of that (adds the `htf_15m=="BEAR"` conjunct on top), so its expected changed-trade fraction is materially **below** the 07-31 study's ~11% — far under the 33% floor.
  - **Scheme chosen: EQUAL-CHANGED-TRADE-COUNT buckets, n_buckets=4** (`backtest/lib/canonical_battery.py::equal_count_buckets`). Calendar windows are REJECTED for this knob — a low-fire-rate knob in fixed calendar windows can get permanently starved below the n>=5-changed floor in past windows regardless of forward data (§4.5's own worked example, `tp1-r50-readjudication-2026-08-23.json`).
  - **Sub-window stability gate** (part of "the standing four," §4 below) is evaluated across these 4 equal-changed-trade buckets, not calendar quarters.

### 3b. Live treatment cohort (production evidence, NOT backtest)
- **Source**: `automation/state/core-decisions.jsonl`, mined by `backtest/autoresearch/gate_expiry_check.py::mine_sole_blockers` (reuses `backtest/tools/postfix_gate_costing.py::sole_blocker_rows`, extracted 2026-09-03 per that file's own docstring so both instruments agree on the selection). Selection rule verified at `postfix_gate_costing.py:129`: `(r.get(bkey) or []) == [filt]` — i.e. `bear_blockers == [5]` **exactly** (bear door key = `"bear_blockers"`, `postfix_gate_costing.py:123`).
- **Quoted count (fresh, this session, `automation/state/gate-registry-status.json`, `run_date: 2026-09-03`, rolling window `2026-08-05..2026-09-01`, 20 trading days)**: cell `bear_filter5_safe` = `{n_events: 1, episodes_distinct: 1, n_cost_money: 1, n_saved_money: 0, costing: "NOT_REPLAYED"}`. Cell `bear_filter5_bold` is byte-identical (same 1 episode, cross-account dedup collapses to `episodes_distinct: 1` — read from either cell per `sole_blocker_flagship_results`'s own convention, never summed across accounts). **`costing: "NOT_REPLAYED"`** — this cell is mined but has never been walked through the real exit manager; it is a COUNT, not a P&L number. Note `bear_filter5` is NOT one of the two named `SOLE_BLOCKER_FLAGSHIPS` (`filter-8-bear-sole`, `filter-10-bull-sole`, `gate_expiry_check.py:586-589`) — it is generically mined but not yet a tracked flagship watch.
- **This is a THIN live cohort (n=1 in 20 days).** It corroborates the mechanism (filter 5 alone is binding rare-but-real bear setups) but cannot itself carry a ratification decision — it is disclosed as supporting evidence for the miner's existence and the mechanism's live incidence rate, not as the study's population.

---

## 4. Ratification bar

An arm SHIPS only if ALL of the following pass (no partial credit, no cherry-pick):

1. **The standing four** (CLAUDE.md OP-11 auto-ratify bar, `feedback_ship_validated_engine_wins` / `feedback_realistic_goal_levels_focus_2026_07_22` lineage): **OOS_positive AND WF >= 0.70 AND sub_window_stable (evaluated over the §3a equal-changed-trade-count buckets, NOT calendar windows) AND anchor_no_regression**.
2. **Pooled BH-FDR** (Benjamini-Hochberg, alpha=0.10, one-sided mean-per-changed-trade > 0) **across every cell this study opens** — not per-cell alpha. If this study opens more than one arm (e.g. a variant that also requires `sequence_rejection` per L96-style level-tied trigger discipline, or a variant that pairs the entry relaxation with a `ribbon_flip_back`-exit suppression per the 07-31 finding below), all cells share one pooled correction.
3. **C28/L243 disclosure, both directions, stated explicitly in the run's output** (per CLAUDE.md doctrine table row C28 and the L243 fire-count guard): *ribbon lag is BOTH a lagging-EXIT story (C28: "Ribbon flip is a lagging exit," L139/141/156/157/175/243 — the existing `ribbon_flip_back` exit rule already fires on the same lagging indicator this candidate relaxes on entry) AND a lagging-ENTRY story (this candidate's own thesis: the ribbon vetoes entries at the exact moment — a fresh rejection at an extreme — where a 3-EMA stack is definitionally still pointed the old direction).* Any arm that relaxes ONLY the entry side while `ribbon_flip_back` still owns the exit is PRE-REFUTED by `filter5-ribbon-2026-07-31.md`'s own finding: 76.2% of that study's unlocked trades round-tripped through `ribbon_flip_back` within minutes (vs 9.9% of the control book) because the entry gate and the exit rule read the identical lagging signal. **This study's ARM_A (see §6) must therefore report the exit-reason mix of its added cohort and flag if `ribbon_flip_back` dominates it the same way** — a repeat of that pattern is grounds to fail G4/G1 even if headline P&L looks positive, per the 07-31 study's explicit warning that a paired (entry+exit) change is the only version worth running.
4. **Concentration disclosure** (C4: "Disclose concentration, normalize OOS, stratify by regime") — report the added cohort's day-count / trade-count ratio and top-3-day P&L share; a positive delta driven by 1-2 anchor days does not ship (mirrors the drop-best-day gate discipline used throughout this doctrine, e.g. G3 in the 07-31 study).
5. **Sign-only walker caveat, disclosed wherever bold-2/aggressive-account numbers are quoted**: `analysis/deep-research/BOLD-HARNESS-2026-08-01.md` §"Finding #4" states directly that *"the frozen verdict rule is sign-only, and that's a real gap"* — the Bold parity walker passed 6/7 dates within tolerance and 7/7 same-sign (line 203), but at least one date (2026-07-28, `SPY260728C00741000`) failed the magnitude tolerance ($110 outside $88.50) while matching sign (line 201). **Any per-arm P&L reported for bold-2/aggressive must be labeled sign-reliable, magnitude-UNVERIFIED** unless replayed through a magnitude-passing walker; do not present bold-side dollar deltas from this candidate with the same confidence as safe-2's.

---

## 5. Mandatory veto: G4 runner-anchor no-regression

Carried forward verbatim as a HARD requirement (not advisory) from `prereg-filter5-ribbon-2026-07-31.json`'s `G4_runner_anchor_no_regression`: **in the treatment arm, both the COUNT and the TOTAL P&L of runner-cohort exits (`exit_reason` containing `"runner"` or `"trail"`) must be >= 95% of CONTROL's, over the full population.** Rationale (unchanged): 35 `RUNNER_TRAIL` winners = +$15,774 in the 07-31 study's CONTROL book = the book's entire profit engine. Any exit-side degradation from this candidate — plausible, since forgiving filter 5 changes WHICH bar the position enters on, which changes downstream ribbon/structure-stop timing — FAILS the arm regardless of headline delta. This gate is listed separately from §4's "standing four" because it is candidate-specific (not part of the generic auto-ratify bar) and non-negotiable per the 07-31 precedent that ships G4 as PASS/FAIL, no soft version.

---

## 6. Arms

- **CONTROL**: `run_backtest(**SAFE_BASE_LIVE)` — live production config, unchanged, `htf_bear_ribbon_forgiveness=False`.
- **ARM_A_htf_bear_forgiveness**: CONTROL + new flag `htf_bear_ribbon_forgiveness=True` exactly as specified in §1 — three-conjunct forgiveness (`level_rejection AND confluence AND htf_15m_stack=="BEAR"`), `-1` score demerit, mirrors `trendline_chop_demerit`/`bearish_reversal_demerit` implementation pattern. This is the ONLY arm the queue item asks for; no additional arms are pre-registered here without a documented reason (no hand-tuning per the queue item's own instruction).
- **Reported but not gating**: full-population delta, added/dropped trade counts, exit-reason mix of the added cohort (per §4.3), per-arm (Safe vs Bold) split per Fable-amendment #3 below.

---

## 7. Full `decide_payload` replay requirement (Fable amendment #2, carried forward)

Per the queue item's own amendment: **the pre-reg build MUST replay the FULL `decide_payload` path** (`backtest/lib/engine/score.py` -> `engine_cli`), **not `evaluate_bearish_setup` in isolation** — the structure veto (`_classify_sameday_5m` / structure_veto downstream) binds later in the session and is asymmetric by arm (`structure_veto_enabled: Safe=True, Bold=ABSENT` in both params files — re-verify this asymmetry is still current at build time, it was last confirmed 2026-07-27). An evaluate-only A/B overstates recovered P&L because it never lets the veto claw back a bar the relaxed filter 5 admitted. **Report recovered P&L PER ARM (Safe, Bold) separately** (Fable amendment #3) — do not pool them, and do not "fix" the structure-veto label to admit the 12:57 07-27 knife-catch loser; that veto's provenance was audited twice (G16 2026-07-02, F2 closed 2026-07-18, verdict KEEP, fail-open safety-class) and is out of scope for this study.

---

## 8. Pre-committed prediction + refutation

**Prediction (stated before any run, per OP-33/anti-sycophancy discipline — this is a guess, not a result):** ARM_A likely NULLs on the standing-four bar for the same structural reason the broader 07-31 study nulled — the added cohort's exit mix will skew toward `ribbon_flip_back` (same lagging-indicator round-trip mechanism), and the cohort is small enough (§3a fraction estimate, well under the 07-31 study's already-thin 21-trade addition) that G3 (survives-drop-best) and G2 (day-majority) are likely to fail on noise alone, mirroring ARM_A/ARM_B's fate in `filter5-ribbon-2026-07-31.md`. The HTF conjunct narrows rather than strengthens the cohort relative to that prior study.

**Refutation condition (what would prove this prediction WRONG and the candidate genuinely live):** ARM_A's added cohort clears G1-G5 in §4/§5 on both the recent window and the ≥4 equal-changed-trade buckets, AND its exit-reason mix is NOT dominated by `ribbon_flip_back` (i.e. the `htf_15m=="BEAR"` conjunct is doing real work — filtering out the exact setups that would immediately round-trip, unlike the undifferentiated 07-31 bypass). If that happens, the prediction above was wrong and the candidate should be reported as the strongest filter-5 relaxation evidence to date, explicitly contrasted against the two prior NULLs.

**If NO arm passes**: filter 5 STAYS structurally required for the bear path (matches the 07-31 and 07-28 precedent verdicts), and the 07-27 anecdote (§9) remains disclosed as a documented, understood, UNRECOVERED cost — not evidence of a fixable gate, since the study that would fix it was run and failed.

---

## 9. Motivating exhibit (disclosed as seen, not re-litigated)

2026-07-27: J-quality rejection at 09:40 ET, level_rejection @ 744.9, bear_score 9/10, `htf_15m` already BEAR at that bar — engine blocked solely on filter 5 (ribbon not yet BEAR-stacked). Ribbon flipped BEAR at 10:41, 61 minutes after the rejection and 5 minutes before the session low. The engine then bought puts into the bottom at 12:57/13:10/13:31 and lost **-$571.64**. This is the single anecdote that filed the queue item; it motivates the question and is NOT treated as evidence of the population-level answer (same disclosure discipline as the 07-31 study's own `motivating_incident.note`: "n=1 day = ANECDOTE. It motivates the question; it does not answer it.").

---

## 10. Build step (structured, for the next session that runs this)

```
build_step:
  id: FILTER5-HTF-BEAR-FORGIVENESS-2026-09-03
  new_flag: htf_bear_ribbon_forgiveness (bool, default False) in evaluate_bearish_setup, backtest/lib/filters.py
  forgiveness_site: mirror filters.py:1817-1828 (trendline_chop_demerit) / 1839-1879 (bearish_reversal_demerit) pattern
  replay_cell_file: backtest/tools/filter5_htf_bear_forgiveness_2026_09_03.py
    - reuse engine_fullhist_replay.py's build_ribbon_lookup / ribbon_tick_df_for / match_entries_by_strike_side_time
      (per BOLD-HARNESS-2026-08-01.md:34, "reused verbatim")
    - MUST call the full decide_payload path (engine_cli), not evaluate_bearish_setup alone (see sec 7)
    - window scheme: equal_count_buckets(n_buckets=4) from backtest/lib/canonical_battery.py, NOT calendar windows (see sec 3a)
    - per-arm (Safe/Bold) P&L reported separately; Bold numbers labeled sign-reliable/magnitude-unverified (see sec 4.5)
  guard_test: backtest/tests/test_htf_bear_ribbon_forgiveness_default_inert_2026_09_03.py
    - RED-proofed: flag default False must be byte-identical to pre-flag behavior
  cross_check: gate-registry-status.json bear_filter5_{safe,bold} cells should be re-mined post-arm to confirm the
    live sole-blocker incidence rate this study measured against (currently n=1/20 trading days)
  status: NOT STARTED -- this document is the frozen spec only. No code/params/queue.md touched this session.
```

---

## 11. Expansion clause

**Nothing before 2026-10-30.** No follow-on arm (paired entry+exit variant, bull-side mirror, sequence_rejection-inclusive variant, etc.) may be pre-registered or run off this study until ARM_A's verdict is filed AND that date has passed, per the standing September clean-window / config-freeze doctrine (memory `project_september_clean_window_plan_2026_08_29`: "freeze to ~09-29; safe-2 A/B ships by 08-31 or never" — this study ships or nulls within that discipline, and any expansion is deliberately pushed past the freeze window into the next planning cycle, not squeezed in during it).

---

## 12. Out-of-lane (do not touch, other agents' work per queue conventions)

- `bearish_reversal_bypass` fhh-only mechanism itself (separate, already-shipped-inert flag; not this candidate).
- Structure-veto label/provenance (audited twice, KEEP verdict, out of scope per sec 7).
- Bold-side parity walker magnitude fix (BOLD-HARNESS-2026-08-01.md's own open item, not this study's job).
- OPRA cache backfill (the 07-31 study's own flagged highest-value input — this study inherits the same coverage gaps and must disclose them the same way if the recent window is thin, per that study's `opra_coverage` section).
