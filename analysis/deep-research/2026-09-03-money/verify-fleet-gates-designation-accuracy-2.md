# VERIFY-2 (CONSEQUENCE lens) — G4-DESIGNATION-ACCURACY

Stamp: 2026-09-03, ~14:33-15:10 ET (market hours), read-only, zero writes to
`automation/state/**`/`journal/**`/`analysis/quote-tape/**`. Skeptic re-check of
`fleet-gates-designation-accuracy.md`/`.json`, extending (not duplicating) the prior
`verify-fleet-gates-designation-accuracy-1.json` pass. Scripts: `backtest/tools/
fleetgates_verify-designation-accuracy.py` (day-level reproduction) and
`backtest/tools/fleetgates_verify_designation-accuracy_2_dollars.py` (dollar stress test),
both <5s runtime.

## Verdict up front

**NOT REFUTED. The finding is SUPPORTED and the core claims independently re-verify
exactly** — code line numbers, the `667217a`/2026-06-26 commit, the safe-3 first-fill date,
the `go_live_gate.py` output, and the 12-date/0-sole-source day-level check all reproduce
byte-for-byte. Applying the CONSEQUENCE lens (remove top-3 contributors, recompute) does
**not** change the pass/fail-relevant claim (day-count survival) but **does overturn the
finding's own soft qualitative claim that a 09-29 fix "would very likely cost some
entries/dollars."** Once concentration is stripped, safe-3's leak-derived P&L flips from
+$752 to **-$491** — the opposite sign. This is a correction to one sentence in the
finding's JSON (`kills_winners`), not to its verdict: the report's own `.md` body never
computes a dollar figure and explicitly defers that question to the sibling doc, so the
overreach lives only in the JSON's informal characterization, not in the load-bearing claim
the question asked about (day-count survival).

---

## 1. Code/ledger claims — all re-verified exactly

| Claim | My independent check | Result |
|---|---|---|
| `accounts.json` safe-3 `gate_override` = `{min_triggers:2, require_confluence_or_sequence:true}` | `sed -n '45,80p' automation/state/fleet/accounts.json` | **MATCH**, verbatim |
| `_gate_check` at `fleet_executor.py` ~599-620 | Read the function directly | **MATCH**, verbatim (including the `SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX` docstring) |
| `plan_all` branches on `signal.get("strategies") is not None` at ~933-935 | Read the function directly | **MATCH** |
| `EMIT_STRATEGIES = True` at `build_shared_signal.py:293` | `grep -n EMIT_STRATEGIES` | **MATCH**, line 293 exactly |
| Commit `667217a` dated 2026-06-26, both `git log -S` searches land on it | `git log -S'EMIT_STRATEGIES = True'` and `git log -S'signal.get("strategies") is not None'`, both on `build_shared_signal.py`/`fleet_executor.py` | **MATCH** — both commands return only `667217a1`, dated `2026-06-26 14:15:44 -0600` |
| safe-3's first fill = 2026-06-29 | `grep '"arm": "safe-3"' automation/state/fills-ledger.jsonl \| head` | **MATCH** — first row `ts_et: 2026-06-29T14:51:15` |
| `go_live_gate.py:826` carries `profile_summary` through display-only | `grep -n profile_summary setup/scripts/go_live_gate.py` -> exactly one hit, at line 826, inside the `result["designation"]` dict, never referenced by any `pass`/status computation elsewhere in the file | **MATCH** |
| `first_live_day_review.py`/`live_readiness.py` have zero matches on gate/cohort/min_triggers/structure_veto/profile_summary | `grep -nE "cohort\|min_triggers\|structure_veto\|profile_summary\|gate_override"` on both files | **MATCH** — zero hits in both (my broader plain `"gate"` grep does hit `live_readiness.py`, but only in generic phrases like "go-live gate" / "readiness gate," never gate-identity vocabulary — consistent with the report's more precise grep set) |
| `walker_full_population_anchor.py` covers `{safe-2, bold-2, safe-3, risky-1}`, same 4 arms as `go_live_gate.py`'s `ACTIVE_ARMS`, no gate-identity read | `grep -n "safe-3\|ACTIVE_ARMS\|gate\|cohort"` on `backtest/tools/walker_full_population_anchor.py` (note: actual path is `backtest/tools/`, not `setup/scripts/` as the report's table header implies — cosmetic path slip, substance unaffected) | **MATCH** on substance |
| `prod-shadow-designation.json` `profile_summary` text quoted verbatim | Read the file directly | **MATCH**, byte-for-byte |
| Calendar: 43 total trading days (09-01..10-30 ex Labor Day), 3 elapsed, 40 remaining, 19 pre-fix, 24 post-fix | Independent Python date-loop, Labor Day (09-07) excluded, no other NYSE holiday in range | **MATCH** — 43/3/40/19/24, exactly |
| `go_live_gate.prod_shadow_criterion()` read-only: `days_scored=1, days_needed=20, status=INSUFFICIENT_DAYS`, scored date 2026-09-02 | Ran `go_live_gate.load_ledger_rows()` + `prod_shadow_criterion()` directly, read-only (confirmed `load_ledger_rows()` only does a `.read_text()` on `TRADES_ENRICHED`, no refresh call) | **MATCH**, exact note text: `"1/20 scored trading days for arm 'safe-3' in 2026-09-01..2026-10-30."` |
| PREREG-TIGHT-LADDER-2026-08-28.md is the source of the 40-day/2026-10-30 "extended_clock" disclosure view | `grep` the file directly | **MATCH** — "Closes: 2026-10-30... Day-count bar: >= 40 trading days" |

No factual claim I checked in §1-3 of the report failed re-verification.

---

## 2. The day-level leak-dependency check (§4c) — independently reproduced, then EXTENDED

### 2a. Exact reproduction (decision-level, since 2026-08-06)

Ran my own from-scratch join of `core-decisions.jsonl` (`account=safe` `SKIP_*` matched to
`account=bold` `verdict` `ENTER_*` on `core_tick_id`) against `automation/state/fleet/
safe-3/decisions.jsonl`, independent of both the report's own script and the prior
`verify-1` pass's script. Result: **byte-identical to both** —

```
total_leak_ticks=133 distinct_leak_dates=12
dates: 2026-08-07, 08-11, 08-12, 08-13, 08-17, 08-18, 08-19, 08-20, 08-21, 08-27, 09-02, 09-03
dates_where_leak_was_sole_source: [] (count=0 of 12)
```
Every per-date total/via_leak/non_leak triple matches the report's `per_date_breakdown`
exactly (e.g. 2026-08-21: 4/3/1; 2026-09-03: 4/2/2). This is now **three independent
reproductions** (the report, `verify-1`, and this pass) of the identical 133-tick/12-date/
0-sole-source result.

### 2b. CONSEQUENCE-lens stress test — remove the top-3 leak-heaviest dates

Per the assigned lens, I removed the 3 dates contributing the most leak-sourced entries
(`2026-08-21`: 3, `2026-09-02`: 2, `2026-09-03`: 2 — a tie for #2/#3 broken by date order) and
recomputed on the remaining 9 dates:

```
after removing top-3 dates: 9 leak-eligible dates remain, sole-source count = 0
conclusion (0-of-N sole-source) survives without top-3: True
```

This is unsurprising once stated plainly: the "0 of 12" claim is a **universal (for-all)**
claim across independent dates, not an aggregate/average — removing any subset of dates
cannot manufacture a sole-source date among the ones that remain if none of them had one to
begin with. **The claim was never at risk from a top-3-date knockout test; it is a claim
that a stronger single-date counterexample would refute, and there is none in the sample.**

### 2c. A stronger, independent check the report did not run: FILL-LEVEL, FULL HISTORY

The report's own caveat #2 says the day-level check is "bounded to the 34 trading days
since 2026-08-06, not safe-3's full 06-29-start history" and caveat #1 says it measures
*decisions* (ENTER-type), "not the exact `trades-enriched.jsonl` FIFO-fill criterion
`prod_shadow_criterion()` actually uses." I closed both caveats at once: reused the
sibling `fleetgates_bypass-cohort-pnl.py` module's own join machinery (core-decisions join
+ `analysis/pain-ledger/mae-mfe.json` + fills-ledger fallback — i.e. **matched, realized
P&L trades**, not decision-log rows) across **safe-3's entire trading history**
(2026-06-29 to today), and asked the same question: is there any date where every matched
trade was leak-sourced (`cohort == A_BYPASS`)?

```
FULL-HISTORY dates where ALL matched trades that day were A_BYPASS (leak): 0
total distinct dates with any A_BYPASS trade (full history): 8
  [2026-08-04, 08-07, 08-13, 08-19, 08-21, 08-27, 09-02, 09-03]
```

This is a **materially stronger check than the one in the report**: it uses actual filled/
realized trades (not decision logs that might not have produced a fill), and it covers
safe-3's *entire* trading history, not just the 34-day post-2026-08-06 sample. It closes
both caveats the report itself flagged as open, and the answer is the same: **zero**. Note
it also surfaces one date (`2026-08-04`) with a leak-sourced trade that predates the
report's 2026-08-06 window and therefore never appeared in its 12-date sample — a genuine
gap in the original check's date range, but one that (per this extended check) does not
change the conclusion, since 08-04 also has a non-leak matched trade that day (not shown
in the report at all — an omission worth folding in if this doc's finding is ever cited as
"the" day-level check).

**Net effect on the report's central numeric claim: strengthened, not weakened.** The
20-scored-day-bar-survives conclusion now rests on independent confirmation at two levels
(decisions and fills) and two scopes (34-day sample and full history), all agreeing.

---

## 3. CONSEQUENCE-lens dollar stress test — the one real correction

The report's `.md` body explicitly declines to compute a dollar figure ("P&L/dollar impact
of closing the leak is not computed in this report... this report answers only the
day-count/designation-accuracy question asked") and points to the sibling
`fleet-gates-ledger-binding-check.md` / `fleet-gates-bypass-cohort-pnl.json` for that. But
the finding's own **JSON** `kills_winners` field does make an unquantified qualitative
claim: *"it would very likely cost some entries/dollars (a real but partial effect...)."*
I stress-tested that claim against the very cohort data the sibling doc supplies.

**Source data (already on disk, `fleet-gates-bypass-cohort-pnl.json`, safe-3
`cohort_A_bypass`, n=13):** `total_pnl=$752`, `wr=30.8%` (4 win / 9 loss),
`mean_pnl_ci95=[-49.46, 182.23]` (**crosses zero**), `top3_gross_win_concentration=0.857`,
`top3_win_dollars=$1243`, `drop_best_day_total_pnl=-$188` (already disclosed in the JSON,
not surfaced in the designation-accuracy `.md`).

**My independent trade-level reconstruction** (reused the sibling script's own join
functions rather than re-deriving the math from the summary stats, so this is not a
recomputation-from-aggregates but the actual 13 trades):

```
2026-09-03 SPY260903C00770000: +507   2026-09-03 SPY260903C00772000: +433
2026-08-27 SPY260827C00770000: +303   2026-08-19 SPY260819C00770000: +207
2026-08-04 SPY260804C00768000: -39    2026-09-02 SPY260902C00765000: -48
2026-08-21 SPY260821C00766000: -63 (x3)   2026-08-04 SPY260804C00769000: -66
2026-08-13 SPY260813C00776000: -90    2026-09-02 SPY260902C00766000: -90
2026-08-07 SPY260807C00772000: -176
total = $752.0  (exact match to the sibling JSON's total_pnl)
```

`drop_best_day_total_pnl` from this reconstruction = **-$188.0**, exactly matching the
sibling JSON's own figure — confirms my join methodology is faithful to theirs, not an
independent artifact.

**Remove the top-3 dollar contributors** (the 3 biggest winning trades: +507, +433, +303 =
$1243, which is 85.7% of the cohort's gross winning dollars — the JSON's own
`top3_gross_win_concentration` figure):

```
remaining 10 trades: total_pnl = -$491.0
sign flip from removing top-3: YES (+$752 -> -$491)
```

**Reading this honestly:** safe-3's leak-derived P&L is not a robust positive number — it
is a wide-CI, zero-crossing mean built almost entirely from 3 trades (85.7% of gross wins),
and single-best-day removal alone (`drop_best_day_total_pnl=-$188`) already flips it
negative; removing the top-3 *trades* flips it further negative (-$491). **On this
evidence, the claim that a 09-29 fix "would very likely cost dollars" is not well
supported** — the more defensible reading is that the leak's dollar contribution to safe-3
specifically is not statistically distinguishable from zero and may well be net-negative
once its concentration is accounted for. This does not touch the day-count question (a
day-count survives regardless of whether the leak trades that produced it were profitable
or not — a scored day only needs >=1 fill), so it does not change the SUPPORTED verdict on
what was actually asked. It corrects one unquantified sentence in a machine-readable field
that the human-readable report itself was already careful not to assert.

**Named-winning-days cross-check (STANDARDS disclosure):** of the 4 named days
(08-06/08-13/08-27/08-28), safe-3's `cohort_A_bypass` has entries on only 2
(08-13: 1 trade, **-$90**, a loss, not a win; 08-27: 1 trade, **+$303**, one of the top-3
contributors above). The leak's positive total is not concentrated on the doctrine's own
"named winning days" — if anything the leak lost money on one of them.

**September window (2026-09-01..today) checked separately per STANDARDS:** `cohort_A_bypass`
September n=4, total=+$802 (trades: -90, -48, +507, +433) — i.e. two of the three top-3
full-window contributors (+507, +433) are *from today, 2026-09-03*, a still-open trading
day at report-generation time. This is the single biggest driver of the whole cohort's
positive total and is the least-settled, most recent data point in the sample.

---

## 4. Minor, non-substantive observation

The designation-accuracy report's §4a states "8 real safe-3 fills across 4 round trips" for
2026-09-03 as of its ~14:30 ET generation. My own read of `fills-ledger.jsonl`, run later in
the same live session (~14:50s ET), shows **10 fills**, still 4 round trips (the two most
recent round trips each closed via 2 partial-exit fills). This is not a discrepancy in the
report — it is normal same-day fill accumulation during market hours between the report's
generation time and my later read. Flagged only so the number isn't mistaken for a fixed
fact if re-quoted later; it was accurate as of its own timestamp.

---

## 5. Answering the CONSEQUENCE lens directly

**Does this finding change what the go-live gate is measuring?** No — verified directly:
`go_live_gate.py`'s `prod_shadow_criterion()` reads only `arm`/`window_start`/`window_end`/
`min_days` from the designation file and scores realized `trades-enriched.jsonl` rows;
`profile_summary` is display-only (line 826, confirmed). The designation-text fix the report
proposes changes zero bytes of gate logic.

**Does it change what a 2026-09-29 kill-type change would do?** Only on the day-count axis
(the question asked): no — the survival conclusion is now backed by three independent
day-level reproductions (report, verify-1, this pass) plus a fourth, stronger fill-level/
full-history check that closes the report's own disclosed caveats and still finds zero
sole-source dates. **On the dollar axis** (not the question asked, but implied in the
finding's own JSON): the CONSEQUENCE-lens stress test suggests the fix's expected dollar
cost to safe-3 is weaker than implied and plausibly reverses sign once its top-3-trade
concentration is stripped — a correction worth folding into the `kills_winners` field if
this finding is promoted, but not a refutation of the finding's actual verdict.

## What this does not resolve

Does not re-open the "should the leak be fixed" adjudication, does not extend the dollar
stress-test to risky-1/risky-3 (out of scope for a safe-3-designation-accuracy check), and
does not test the untested future post-fix regime — same limits the original finding
already disclosed.
