# Funnel-v2 Pre-Trust Audit — fable-too-good hunt before STOP-B

**Date:** 2026-07-09. **Current ET at analysis time:** 2026-07-09 18:15:16 EDT (`et_clock.py`), market_hours=False.
**Mission:** hunt the artifact in `mass-grind-funnel-v2-0.jsonl` BEFORE tonight's `mass_grind_phase5` output becomes the STOP-B kill-check on the SS-B exit shipment. Analysis only — no production files touched.

**Snapshot discipline:** the grind (`mass_grind.py`) and funnel (`mass_grind_funnel.py`) are LIVE processes appending to these files throughout this audit. Every substantive number below (Checks 1–4) comes from **one** read-once load, done via `funnel_audit.py` (kept at `C:\Users\jackw\AppData\Local\Temp\claude\...\scratchpad\funnel_audit.py`, not committed):

| File | Rows read (this audit's snapshot) |
|---|---|
| `mass-grind-funnel-v2-0.jsonl` | **546** |
| `mass-grind-v2-progress.jsonl` | **6,906** (a few minutes later, a second read-only query saw 6,918; a final freshness check at write-up time saw progress=6,954 / funnel=552 — confirms the process is still live and appending, consistent with the mission brief; it does **not** change any Check 1–4 finding below, all of which are pinned to the 546/6,906 snapshot) |
| `mass-grind-funnel-{0..5}.jsonl` (v1 union) | **1,390** (6 files) |
| `mass-grind-progress{,-a,-b,-c}.jsonl` (v1 union) | **8,960** |
| `mass-grind-total.json` | `{"total": 7560}` |

No files were opened for write except this report and the one guard test noted in Check 5.

---

## BOTTOM LINE: **TRUST-WITH-CORRECTIONS**

The funnel's **gate math is clean** — the two things this audit was most worried about (a vacuous P2/P3/P4 gate, and a repeat of the 181/181 dead lock/trail knob) are both **conclusively refuted** on the current v2 data, with full-dataset (not just sampled) consistency checks at zero violations. The "66% P4 rate" that triggered this audit is **not anomalous** — v1's own historical funnel ran at 67.1%, in the same ballpark, and the ~4pp v2 uptick has a specific, sound mechanism (below). But **CHECK 5 is a real, confirmed gap**: `mass_grind_phase5.py` has **zero code-level awareness of grind completeness** — nothing stops it being run against the current 91%-done, ITM-2-and-wide-stop-light snapshot and silently producing a "final-looking" summary. The only automated safeguard that would have caught this (`Gamma_Grind_Watchdog`) is confirmed **Disabled** right now, and would be wired to the wrong (legacy v1) files even if re-enabled. **Tonight's phase5 output can be trusted ONLY IF it is generated fresh AFTER the grind reaches 7,560/7,560 (specifically: after the ITM-2 strike bucket, currently 438/1,080 = 40.6% done, finishes) — not before, and not by reusing any file generated earlier tonight.** A guard test proving this gap now exists at `backtest/tests/test_phase5_completion_gate.py` (currently RED by design; turns green once phase5 is fixed).

---

## CHECK 1 — GATE VACUITY: **CLEAN**

Read `mass_grind_funnel.py::_evaluate()`, `null_baseline.py::null_gate/random_entry_null`, `strategy_space_grind.py::metrics_for/validate`. Thresholds: P2 `qpf>=0.60`; P3 `qpf>=0.75 AND live_real_exp>0 AND live_admit_pct>=0.50` (live realizability via `qty_realizability`'s `safe2000_q5` slice); P4 `beats_null_max AND drop_top5_beats_null_mean` from a 10-seed random-entry null, **only evaluated at all if P3 passed**.

Recomputed all 4 gate thresholds from each row's own stored raw fields (`qpf`, `live_real_exp`, `live_admit_pct`, `p4_null.per_trade/drop_top5_per_trade/null_mean/null_max`) on 10 random PASS-P4 rows (seed=42) — **0/10 mismatches** between recomputed and stored `p2_pass`/`p3_pass`/`p4_pass`. Then widened to the full dataset:

- **None-vacuity scan across all 389 PASS-P4 rows**: 0 None-valued threshold fields (a missing field would default the comparison to failing, not passing, in this code — but there were none anyway).
- **Structural check** `(p4_null is not None) == p3_pass` across all 546 rows: 0 violations.
- **Impossible-state scan**: `p3_pass=True` but `live_admit_pct<0.50 OR qpf<0.75`: **0/546**. `p4_pass=True` but `NOT(beats_null_max AND drop_top5_beats_null_mean)`: **0/546**.
- **verdict-consistency scan**: stored `verdict` vs. the verdict implied by `(p2_pass,p3_pass,p4_pass)` across all 546 rows: **0 mismatches**.

No vacuity anywhere in the chain. The gate is doing exactly what its code says.

**One real (non-vacuity) oddity flagged, not dismissed:** of 546 v2 rows, **PASS-P3 count = 0** — every row that clears P3 also clears P4 this snapshot (389 PASS-P4, 0 PASS-P3-only). v1's union shows PASS-P3=140 (10.1%) — a real population of P3-survivors-that-failed-P4. Investigated in Check 3 below; conclusion there is **SUSPECTED, not confirmed-clean** — flagging it here rather than silently letting the "0 mismatches" finding imply everything about the funnel's current output is fully understood.

---

## CHECK 2 — DEAD-KNOB DUPLICATES: **CLEAN (opposite of the old scar)**

Old scar (2026-07-08 discovery, referenced in `mass_grind.py`'s docstring): 181/181 fixed-vs-trailing P4 pairs were **byte-identical** (`profit_lock_mode` set via `gate_patch`/`params_overrides`, which `_params_to_kwargs` silently drops — L156). T-W2/T-W3 fixed this by passing `profit_lock_mode`/`profit_lock_trail_pct`/`time_stop_minutes_before_close` as explicit `run_cell` kwargs.

Grouped all 546 v2 rows by every combo axis **except** `(lock_mode, trail_pct)`, and separately by every axis **except** `time_stop_minutes_before_close`:

| Axis grouped out | Multi-variant groups | Fully byte-identical | Rate |
|---|---|---|---|
| lock/trail | 139 groups (279 rows) | **0** | **0.0%** |
| time-exit (ts10 vs ts60) | 226 groups | **0** | **0.0%** |

This is the **opposite** signature of the old bug (which was 100% identical; here it's 0% identical). The one group containing all 3 lock/trail variants for the same (strike,stop,tp,tq,ts) cell shows genuinely different numbers: `fixed` EC=1600.53/exp=7.92 vs `trailing0.15` EC=2011.47/exp=24.56 vs `trailing0.22` EC=1707.83/exp=14.87 — a $410 edge_capture spread, not noise. Time-exit pairs show the same pattern (e.g., one cell: ts60 EC=937.54/exp=9.89/wf=16.6 vs ts10 EC=937.54/exp=11.59/wf=6.5 — expectancy and wf clearly differ even where edge_capture, a narrow 6-anchor-day metric, coincidentally repeats because those specific 6 days' trades weren't affected by the time-stop change). **Verdict: the T-W2/T-W3 fix is real and verified on the current run's own data — this is not a repeat of the dead-knob scar.**

---

## CHECK 3 — SURVIVOR-RATE BASE RATE: **NOT ANOMALOUS in aggregate; one SUSPECTED residual**

**Headline comparison (same P2/P3/P4 gate code, both runs):**

| | v2 (n=546) | v1 union (n=1,390) |
|---|---|---|
| STOP-P2 | 3.7% | 1.9% |
| PASS-P2 | 25.1% | 21.0% |
| PASS-P3 | 0.0% | 10.1% |
| **PASS-P4** | **71.2%** | **67.1%** |

The mission's premise — "prior grinds' P4 rates were far lower" — **does not hold up**: v1's own historical P4 rate (67.1%) is in the same range as v2's (71.2%/66% earlier). Two more denominators make this even clearer:
- **Underlying banger rate** (of ALL evaluated combos, not just funnel-tested ones): v1 15.85%, v2 15.65% — essentially identical, so phase-1 (`EC>=771, WF>=0.70`) hasn't gotten easier.
- **P4-of-all-combos** (the most honest whole-grid denominator): v1 **10.40%**, v2 **5.63%** — by this measure v2 is *stricter*, not looser, than v1.

**Why the tested-banger population differs (grid composition, verified not assumed):** v2's raw progress rows show the STOP axis is being swept evenly (720–840 rows per stop value, all 9 values present — the grind has *not* dropped wide stops). But the **banger rate per stop bucket** is wildly non-uniform: stop-8 → 57.6% banger rate, stop-12 → 38.1%, stop-15 → 22.6%, stop-20 → 2.9%, stop-25 → **0.0%** (0/720), stop-30 → 1.3%, stop-35 → 1.1%, stop-40 → 3.6%, stop-50 → 2.9%. Wide stops structurally almost never clear the anchor-day `EC>=771` bar (wide stops let losing trades bleed further, directly inflating `edge_capture_block`'s `loser_penalty` term) — this is an economically sound, expected mechanism, not an artifact. Because of it, v2's *currently tested* funnel population is 91.9% tight-stop (-8/-12/-15), vs. v1's much broader mix (v1 also swept 4x more BLOCK_LR×MIN_TRIG gate combinations, giving wide stops more distinct "shots" at a rare banger — a disclosed, intentional v2 scope cut per `mass_grind.py`'s own docstring, not a hidden change).

**The SUSPECTED residual (Check 1's PASS-P3=0 flag, followed through, not resolved):** controlling for stop-bucket alone doesn't fully close the gap — v1's own tight-stop-only subset (-8/-12/-15) still shows PASS-P3-only-fails-P4 at 19.7% (523 P4 of 651 P3-or-better = 80.3%), and even v1 rows matching v2's *exact* fixed gate (`blr=False, mt=1`) show only 51.6–57.9% P3→P4 conversion — both meaningfully below v2's current 100%. Chased a second hypothesis (trade count `n` inflating the null-beat rate): v2's P3-or-better rows have a strikingly high median `n=397` (range 360–411) vs. v1's median `n=78` (range 68–218) — but **v1's own internal pattern runs the opposite direction** (v1 rows that fail P4 have a *higher* median n=202 than rows that pass, n=76 — more trades makes the null harder to beat in this framework, not easier), so the n-inflation hypothesis is **refuted by v1's own data**, not confirmed. Margin check: v2's PASS-P4 rows clear the null by a real but **thinner** median margin (+$27.14/trade, min +$12.29, all comfortably positive — no marginal near-zero passes) vs. v1's median +$74.80/trade. **Verdict: SUSPECTED, not CONFIRMED artifact, not fully explained** — the gate math itself is proven clean (Check 1), but why the *current* v2 slice converts P3→P4 at 100% is not fully accounted for by the two mechanisms tested. Most likely a real property of this narrow, non-representative-yet slice (6 of 7 strikes done, ITM-2 and the harder wide-stop tail still thin) rather than a bug — **recommend re-running this exact comparison once the grind hits 7,560/7,560**, before leaning on the raw P4 rate as evidence of anything beyond "phase5's own neighbor-plateau + qpf==1.0 layer is what should actually gate STOP-B," not the funnel's raw 71% headline.

---

## CHECK 4 — METRIC SANITY: **CLEAN** (two self-caught false alarms corrected below)

Top 5 by `edge_capture` (all `OTM-2:stop-8:tp+30%` variants, EC=2187.34):
- **Progress/funnel parity**: joined each funnel row to its `mass-grind-v2-progress.jsonl` counterpart by label — `edge_capture` and `n` matched **exactly** on all 5 (e.g. EC=2187.34/n=362 both sides, EC=2187.34/n=398 both sides). Two independent write paths (the original grind's `_run()` and the funnel's re-run `_evaluate()`) reproduce byte-identical results — good evidence against a harness-drift artifact (fable-too-good H4).
- **`trades_per_day` plausibility**: `n / trades_per_day` implies 231–240 active trading days for these rows, well inside the ~370-trading-day (2025-01-01..2026-06-18) window — plausible, not degenerate.
- **`max_dd` sign convention**: `_summ()` computes `mdd = min(eq - peak)` where `peak >= eq` always after each update, so `max_dd <= 0` is enforced by construction. Verified **True on all 5 top rows** (e.g. -424.78, -403.48).
- **`wf` outliers**: found values far more extreme than the queue's flagged "13.7" — up to **wf=703.233** (on a STOP-P2 row, not even a survivor) and **wf=94.254** (on a fixed-lock row in the Check-2 fixed-vs-trailing example). Traced the formula: `wf = (OOS_per_trade/n_oos) / (IS_per_trade/n_is)` — a small-but-positive IS denominator legitimately blows the ratio up; this is **not a divide-by-zero bug** (that path explicitly returns 0.0) and, critically, **`wf` is never used as an upper-bound-exploitable P2/P3/P4 threshold** — only as a phase-1 *floor* (`wf>=0.70`). A huge wf is a display/interpretation footgun (don't read "wf=13.7" as "13.7x better"), not a gate-passing mechanism.

**Self-caught correction #1 (qty_frontier "monotonicity"):** first pass flagged **6,310/6,310** rows (100%!) as violating "admit_pct declines with qty" — an alarming number. Read `lib/cap_admission.py` before reporting it: `cap_allows` calls the REAL `risk_gate.check_order` with `BOLD_MIN_CONTRACTS=5` / `SAFE_MIN_CONTRACTS=3`. Every `bold1648_q3` row is qty=3 against a 5-contract floor → **hard, deterministic, by-design 0.0**, unrelated to premium/capacity. Re-ran excluding the below-floor point: **0/6,326 true violations**, and the floor itself is **100% consistent** (0/6,326 exceptions to "bold q3 always 0.0"). This was my own check being wrong, not the data — correcting it here per fable-too-good H6 discipline rather than shipping the scarier first number.

**Self-caught correction #2:** the static "does 'total' appear in `main()`" idea for the Check-5 guard test would have vacuously passed today because `main()` legitimately uses an unrelated `neighbors_total` dict key — tightened the guard test to check for `mass-grind-total`/`_grind_complete`/`grind_complete` specifically (see Check 5).

---

## CHECK 5 — PHASE5 READINESS: **CONFIRMED gap**

- **`mass-grind-total.json` = `{"total": 7560}`** — correct, matches `mass_grind.py`'s own emitted `len(combos)` for the 7×1×1×9×5×4×3×2 v2 grid.
- **Grind completeness (live-verified, not assumed):** raw v2 progress strike distribution: **ATM / ITM-1 / OTM-1 / OTM-2 / OTM-3 / OTM-4 all exactly 1,080/1,080 (100%)**; **ITM-2 = 438/1,080 (40.6%)** — the *only* incomplete bucket, consistent with `_combos()`'s strike-outer iteration order (ITM-2 enumerated last) and exactly reconciling the 6,918-row snapshot (6×1,080 + 438 = 6,918). **The grind is not done. ~642 combos remain, all in ITM-2.**
- **`mass_grind_funnel.py::_grind_complete()`** correctly reads `mass-grind-total.json` (falls back to the wrong legacy `3360` only if that file is missing/unreadable — it isn't) and requires `n>=7560`. This gate is real and correctly wired — **but it only governs when the FUNNEL WORKER's own poll loop exits**, not when `mass_grind_phase5.py` may safely run.
- **`mass_grind_phase5.py::main()` has ZERO reference to completeness** — confirmed by direct source inspection (no `_grind_complete`, no `mass-grind-total`, no progress-file read anywhere in the module). It reads whatever `phase_reached==4` rows exist in `mass-grind-funnel-v2*.jsonl` **at the moment it is invoked** and writes `mass-grind-phase5-summary.json` with no flag distinguishing a mid-grind snapshot from a final one. **Mechanically proved** with a guard test (below) — not just asserted from reading the code.
- **No working automated trigger exists.** `Get-ScheduledTask` (live-queried this session): `Gamma_Grind_Watchdog`, `Gamma_Funnel_0..5`, `Gamma_Grind_all`, `Gamma_Grind_Vwap` are **all `Disabled`**. Even if `Gamma_Grind_Watchdog` (`setup/scripts/grind-shard-watchdog.ps1`) were re-enabled, it watches `mass-grind-progress*.jsonl` / `mass-grind-funnel-*.jsonl` — **the legacy v1 globs**, not `mass-grind-v2-progress*.jsonl` / `mass-grind-funnel-v2*.jsonl` — so it could never correctly detect v2 completion; it would either never fire phase5 (v1's frozen progress count never reaches the now-shared 7560 total) or fire on stale v1-only banger accounting. This is a **second, independent bug** in that script, moot only because the task is currently disabled.
- **The real safeguard tonight is a markdown checklist item**, not code: `automation/overnight/queue.md`'s `T-W7C-GRIND-VERIFY-THEN-STOPB` explicitly says *"verify complete-vs-reaper-killed; if incomplete relaunch...then run mass_grind_phase5 regen + convene STOP-B"* — a correct, sound plan, but entirely dependent on whoever executes it actually checking `progress/7560` first. Nothing in the code stops a premature run.
- **Incompleteness's directional risk on phase5's own math** (reasoned through `_neighbors()`/`_key()`): missing neighbor evaluations can only *reduce* `neighbors_elite`, never inflate it — a config's plateau check under-counts, biasing toward **false negatives** (wrongly rejecting a real survivor), not false positives, EXCEPT that this is scoped mainly to strike-axis neighbors touching ITM-2 (i.e., ITM-1 configs specifically); the stop/tp/qty axes are already well-populated for the tight-stop cohort that dominates today's elites. So an early run isn't "unsafe" in the sense of manufacturing fake winners out of nothing — but it *would* silently omit/under-credit ITM-2-adjacent candidates and would certify against the Check-3-flagged thin/non-representative slice.

**Guard test written** (per the mission's "optional test file"): `backtest/tests/test_phase5_completion_gate.py` — two tests, both **currently RED by design** (verified: ran them, both fail for the documented reason, not a fixture bug):
1. `test_phase5_summary_discloses_grind_completeness` — behavioral: feeds `main()` a synthetic 1-progress-row-of-7560 fixture, proves `mass-grind-phase5-summary.json` has no `grind_complete` key today.
2. `test_phase5_main_has_no_completion_gate_today` — static: `inspect.getsource(main)` contains none of `mass-grind-total`/`_grind_complete`/`grind_complete` (deliberately NOT a bare `"total"` substring check, since `neighbors_total` already appears in `main()` and would make a naive check vacuously pass for the wrong reason — caught this exact trap while writing the test).

These will turn green once `mass_grind_phase5.py` threads a real progress-vs-total check (mirroring `mass_grind_funnel.py`'s own `_grind_complete()`) into its output. Do not delete/weaken them to make that happen.

---

## Recommendation for tonight

1. **Do not run/trust `mass_grind_phase5` yet.** Wait for `mass-grind-v2-progress.jsonl` (union) to reach 7,560/7,560 — concretely, wait for ITM-2 to finish (642 combos left as of this snapshot).
2. Once complete, **regenerate `mass-grind-phase5.jsonl`/`-summary.json` fresh** — do not reuse anything written before completion (nothing on disk currently distinguishes a stale file from a fresh one; check the file mtime against the progress file's completion time by hand until the guard-test fix lands).
3. When STOP-B reviews the P5 output, **weight the neighbor-plateau + qpf==1.0 layer over the raw P4 rate** — Check 3 found the 71% P4-of-bangers headline is not itself anomalous vs. history, but also not fully explained; P5's stricter, per-config robustness test is the layer actually built to catch an unrepresentative/lucky slice, which is exactly the open question here.
4. Ship the completeness-flag fix to `mass_grind_phase5.py` when convenient (test file above is ready to graduate green) and consider re-pointing `grind-shard-watchdog.ps1` at the v2 globs or retiring it explicitly — right now it's a disabled trap that would misbehave if anyone re-enables it without knowing it's v1-only.
