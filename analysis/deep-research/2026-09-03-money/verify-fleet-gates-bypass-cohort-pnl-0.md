# Verify G3 (bypass-cohort-pnl) — CODE-PATH lens

Stamp: 2026-09-03 ~14:55 ET (market open, `python setup/scripts/et_clock.py` confirmed
`market_hours=True`). Read-only skeptic pass on
`analysis/deep-research/2026-09-03-money/fleet-gates-bypass-cohort-pnl.md` / `.json` and its
builder `backtest/tools/fleetgates_bypass-cohort-pnl.py`. Assigned lens: **re-trace the claimed
binding/non-binding from source myself** (`fleet_executor.plan_all` branch selection,
`build_shared_signal` strategies construction, `heartbeat_core` `GATE_KEYS`) — any claim not
backed by a quoted line and a matching ledger row is refuted.

Verification script (copy of the original with only the output path changed, not its logic —
kept so the rerun is exactly reproducible and diffable against the shipped JSON):
`backtest/tools/fleetgates_verify-bypass-cohort-pnl-0.py`. Output:
`analysis/deep-research/2026-09-03-money/verify-fleet-gates-bypass-cohort-pnl-0.json`.

## Verdict

**NOT REFUTED.** Every mechanism claim in the report's Method section traces to real,
quoted source lines, and re-running the builder reproduces every headline dollar/WR/PF/CI
figure I checked **exactly** — including a from-scratch hand recomputation of all 8 of today's
raw fills (safe-3 + risky-1) from `fills-ledger.jsonl`, which is the number the whole "SUPPORTED"
verdict hinges on. **One factual error found**: the report's Method item 4 ("0 unmatched trades
remain in any cohort for any arm") is false — 2 trades are unmatched, in cohort C only. This is
real, quotable, and undisclosed in the `.md` text, but it is narrow-scope: it touches candidate
(b)'s trade count only, not any of the safe-3/population cohort A/B headline numbers, all of
which I independently confirmed carry `n_unmatched: 0`.

---

## 1. Code-path re-trace (the assigned lens)

### 1a. `fleet_executor.plan_all` branch selection — `automation/state/fleet/fleet_executor.py:933-935`

Read directly (not from the report's quote):

```python
if signal.get("strategies") is not None:
    plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
else:
    src = _perception_for_arm(signal, arm)
    ...
```

Confirmed: `_plan_from_strategies` (`fleet_executor.py:721-774`) iterates `signal["strategies"]`
directly — no per-arm role routing, no read of `signal["safe"]`/`signal["bold"]` anywhere in that
function. The role-routed `_perception_for_arm` path exists only in the untaken `else` branch.
This matches the report's method claim exactly.

### 1b. `build_shared_signal.py`'s `strategies[]` construction — the actual swap logic, traced deeper than the report's cited source (`veto-scope-safe-3.md`)

`build_shared_signal.py:293`: `EMIT_STRATEGIES = True` — confirmed as literal source, not
inferred.

`build_shared_signal.py:816-823` (`build()`, `do_strats` branch):

```python
s_bear, s_bull = bear, bull                      # bear, bull = SAFE's own top-level row
if use_peak:
    bold = sig.get("bold") or {}
    if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
        s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
```

This is a nuance the report's method section doesn't spell out but that its classification
logic depends on being true: the swap condition is "bold passed **either** side," and once true,
**both** `s_bear` and `s_bull` are replaced with bold's blocks wholesale (`bold.get("bear")` is
always a truthy dict, so the `or bear` fallback never actually fires once inside this branch).
Since a single core-decisions row's `action` can only ever equal one of `ENTER_BULL`/`ENTER_BEAR`
at a time, this collapses to "if bold entered anything this tick, source both sides of
`strategies[]` from bold's row" — which is exactly the swap the report's `classify_entry()`
(`safe_verdict != want` and `bold_verdict == want` ⇒ `A_BYPASS`) is modeling. **Confirmed
mechanistically correct**, not just plausible.

### 1c. Whether the `verdict`-field proxy the script uses actually matches what `_bold_passed_blocks_from_row`/`_score_peak_check` compute — the report's biggest self-flagged caveat, checked here

The report's own caveats section says cohort classification is "a verdict-field proxy, not a
byte-exact replay of `_score_peak_check`." I traced one layer further than the report did:

`_bold_passed_blocks_from_row` (`build_shared_signal.py:583-585`) reads `action =
row.get("action")` and feeds that into `_score_peak_check(side, action, ...)`, whose logic
(`build_shared_signal.py:891-899`) is:

```python
def _score_peak_check(side, action, score, trigger, fired) -> bool:
    if action in _SIGHT_FAILURE_VERDICTS: return False
    enter = "ENTER_BULL" if side == "bull" else "ENTER_BEAR"
    ...
    return (action == enter) or (int(score or 0) >= peak and trig_ok)
```

This reads `row.get("action")` — but the `row` passed in is **not** the raw
`core-decisions.jsonl` row; it has already gone through `_map_core_row`
(`build_shared_signal.py:132-162`), which does:

```python
def _map_core_row(row: dict) -> dict:
    verdict = row.get("verdict")
    if row.get("action") in _TIME_GATE_SKIPS:
        verdict = "HOLD"
    ...
    return {"action": verdict, ...}   # verdict drives production_action + passed
```

**So `_score_peak_check`'s `action` parameter is the raw ledger row's `verdict` field**, not its
raw `action` field — which is exactly the field the report's `classify_entry()` compares
(`safe_row.get("verdict")` / `bold_row.get("verdict")`). This is not stated anywhere in the
report; I derived it independently to check whether the proxy is directionally sound. It is: the
report's `verdict`-based classification uses the *same field* production's real pass/fail check
resolves to (mod the time-gate-skip→HOLD remap and the score/trigger OR-fallback for non-literal
SKIP verdicts, both of which — if anything — would only make the script **undercount** cohort A,
never misclassify a trade the wrong direction). I confirmed empirically (`core-decisions.jsonl`
full scan) that wherever `action == "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"` (the one
`_HARD_SKIP_VERDICTS` member), `verdict` is *also* `"SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"` in
every one of 273 such rows — i.e. the hard-skip is baked into `verdict` itself, so the proxy
never wrongly credits a hard-skipped tick as "passed."

### 1d. `heartbeat_core.py` `GATE_KEYS` and per-account params — matches the session's established context and the report's cited gates

```
GATE_KEYS = ["block_level_rejection", "trendline_requires_ribbon_flip", "block_elite_bull",
  "block_elite_bull_vix_low", "block_elite_bull_vix_high", "block_bull_ribbon_flip",
  "block_bull_1100_1200", "block_bull_morning_agg", "require_bearish_fill_bar",
  "min_ribbon_momentum_cents", "max_ribbon_duration_bars", "midday_trendline_gate",
  "block_conf_lvl_rej_midday_afternoon", "block_conf_lvl_rec_afternoon",
  "entry_bar_body_pct_min", "entry_bar_body_pct_min_bull", "vix_bear_hard_cap",
  "structure_veto_enabled", "structure_shift_confirmation_enabled"]
```
(`setup/scripts/heartbeat_core.py:183-199`, read directly.)

`automation/state/params.json:215` `"block_bull_1100_1200": true`; **absent** from
`automation/state/aggressive/params.json` (grep, zero matches). `automation/state/params.json:314`
`"structure_veto_enabled": true`; `automation/state/aggressive/params.json:52`
`"structure_veto_enabled": false` (explicit, with its own doc-comment citing "116 times for
account=safe and ZERO times for bold" over 25,821 rows). Both gates the report names as "the
dominant/second-most-common bypass gate" are confirmed present-for-safe /
absent-or-disabled-for-bold in the actual config files, independent of any prior session's claim.

**Conclusion of the code-path lens: every mechanism claim underlying the join (branch selection,
strategies swap, verdict-as-pass-check, per-account gate config) is real and traces to quoted
source.**

---

## 2. Numeric reproduction

### 2a. Full rerun of the builder (unmodified logic, output path only changed)

```
$ python backtest/tools/fleetgates_verify-bypass-cohort-pnl-0.py
```

Reproduced **exactly**, digit for digit, against the shipped
`fleet-gates-bypass-cohort-pnl.json`:

| Cut | Report | Rerun |
|---|---:|---:|
| safe-3 cohort A | n=13, +$752, WR 30.8%, PF 2.08, CI(-48,+184) | n=13, +752.0, WR .3077, PF 2.077, CI(-47.54,186.31) |
| safe-3 cohort B | n=20, -$203, WR 20.0%, PF 0.89 | n=20, -203.0, WR .20, PF 0.885 |
| risky-3 cohort A | n=9, -$823, WR 0%, CI(-124,-64) | n=9, -823.0, WR 0.0, CI(-124.22,-64.11) |
| risky-3 A gate breakdown | SKIP_BULL_1100_1200 n=8 -$619; SKIP_STRUCTURE_VETO n=1 -$204 | identical |
| Population cohort A | n=38, +$33, WR 21.1%, PF 1.01, drop-today -$1,564(34) | n=38, +33.0, WR .2105, PF 1.012, drop -1564.0(34) |
| Population cohort B | n=60, -$1,325, WR 21.7%, PF 0.78, drop-08-13 -$2,354(56) | identical |
| Candidate (a) removed | n=13, +$752; winners removed 4/$1,450; losers removed 9/-$698 | identical |
| Candidate (b) removed-all | n=29, +$1,323, best-day 08-06 +$1,126, drop-best +$197 | identical |
| Candidate (b) gate breakdown | SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY n=11 +$466; SKIP_CONF_LVL_REC_AFTERNOON n=5 +$105 | identical |
| Candidate (b) named-day effect | 08-06 +1126(n=2), 08-13 +315(n=2)*, 08-27 +303(n=1), 08-28 $0 | identical |
| safe-3 VIX <15 / 15-18 | +977/WR60%/PF4.67(n=5); -225/WR12.5%/PF0.48(n=8) | identical |
| safe-1 unmatched-if-matched | -$300 (n=24, 0 with core_tick_id) | identical |
| join_stats real-placement counts | safe-3 68, risky-1 90, risky-3 96, safe-1 24 | identical |
| core_tick_id first-seen | 2026-08-03T09:30:04 ET | confirmed via independent full-file scan: first row `ts_et=2026-08-03T09:30:04`, `core_tick_id=2026-08-03T09:30:02.045613` |

\* the `.md` text's candidate-(b) subsection says "08-13 +$315" — matches; earlier prose in the
same section quotes "-$90" for candidate (a)'s 08-13 effect, a different (correctly smaller)
scope — not a contradiction, just two different candidates on the same day; verified both
independently and both are right for their own scope.

### 2b. Hand recomputation of every "today" trade directly from `fills-ledger.jsonl` (not via the pain-ledger, not via the script — raw arithmetic)

This is the number the entire sign-flip headline rests on, so I recomputed it from the rawest
available source, bypassing both the pain-ledger and the builder script:

**safe-3** (`automation/state/fills-ledger.jsonl`, `attribution=="engine"`, `arm=="safe-3"`,
`date_et=="2026-09-03"`):

| Entry (core_tick_id) | Buy | Sell(s) | P&L | Report claim |
|---|---|---|---:|---:|
| 09:42 (both-passed) | 5@1.11=$555 | 5@0.57=$285 | **-270.00** | -270 ✓ |
| 10:17 (both-passed) | 5@1.31=$655 | 5@1.18=$590 | **-65.00** | -65 ✓ |
| 11:07 (bypass, SKIP_BULL_1100_1200) | 5@1.17=$585 | 3@2.32+2@1.98=$1,092 | **+507.00** | +507 ✓ |
| 11:22 (bypass, SKIP_STRUCTURE_VETO) | 5@0.74=$370 | 3@1.63+2@1.57=$803 | **+433.00** | +433 ✓ |

**risky-1** (same file/filters, `arm=="risky-1"`):

| Entry | Buy | Sell(s) | P&L | Report claim |
|---|---|---|---:|---:|
| 09:42 (both-passed) | 5@1.08=$540 | 5@0.52=$260 | **-280.00** | -280 ✓ |
| 10:17 (both-passed) | 5@1.31=$655 | 4@1.18+1@1.18=$590 | **-65.00** | -65 ✓ |
| 11:07 (bypass) | 5@1.18=$590 | 3@1.81+2@1.95=$933 | **+343.00** | +343 ✓ |
| 11:22 (bypass) | 5@0.76=$380 | 3@1.26+2@1.58=$694 | **+314.00** | +314 ✓ |

All 8 fills-ledger reconstructions match the report to the dollar. I additionally re-pulled the
`core-decisions.jsonl` `safe`/`bold` rows at each of the 4 `core_tick_id`s used above and
confirmed the cohort call by hand: 09:42/10:17 both `safe.verdict==bold.verdict==ENTER_BULL`
(cohort B); 11:06:02.738610 `safe.verdict=SKIP_BULL_1100_1200`, `bold.verdict=ENTER_BULL`
(cohort A); 11:21:02.576928 `safe.verdict=SKIP_STRUCTURE_VETO`, `bold.verdict=ENTER_BULL`
(cohort A) — for **both** safe-3 and risky-1 (both arms ride the same core_tick_id pairs, as
expected since they're both safe-role/risky-role siblings reading the same shared signal). No
new fleet-arm entries exist between the report's ~14:20 ET stamp and this pass's ~14:55 ET check
(re-grepped `decisions.jsonl` for all 4 arms; counts unchanged), so the "today" totals are still
current.

---

## 3. The one verified error: "0 unmatched trades remain in any cohort for any arm" is false

The `.md`'s Method item 4 states: *"After the real-placement fix, **0 unmatched trades remain**
in any cohort for any arm."* This is checked against the shipped JSON's own fields and is
**false**:

- `risky-1`: `join_stats.n_entry_decisions=90`, `n_joined_to_pain_ledger=89` (1 short);
  `per_arm.risky-1.cohort_C_other.n_unmatched=1`.
- `risky-3`: `join_stats.n_entry_decisions=96`, `n_joined_to_pain_ledger=95` (1 short);
  `per_arm.risky-3.cohort_C_other.n_unmatched=1`.

I traced the specific rows: both arms have a `2026-08-26T14:57:06 ET` `ENTER_BULL`
`BULLISH_RECLAIM_RIDE_THE_RIBBON` entry with `placement.placed=true`, `placement.error=None`,
`symbol=SPY260826C00766000` (risky-1) / `SPY260826C00768000` (risky-3), qty=5 — but **zero**
rows exist in `automation/state/fills-ledger.jsonl` for either arm on 2026-08-26 at all (grepped
directly, empty result both arms). The decision ledger says the order was placed cleanly; no
fill of any kind was ever logged. Neither the pre-built pain-ledger nor the script's own
fills-ledger-reconstruction fallback can produce a P&L for a trade that has no fill rows, so both
land correctly as `matched=False` — the code is doing the right thing; it's the `.md` prose's
blanket completeness claim that's wrong.

**Consequence, scoped precisely:** both unmatched rows sit in cohort `C_OTHER`
(`safe_verdict==want`, `bold_verdict!=want` — the mirror-direction case), which only enters the
analysis via candidate (b)'s risky-role removal query (`bold_gated_safe_passed`). I re-ran that
exact filter and confirmed both 08-26 rows satisfy it (`safe.verdict=ENTER_BULL`,
`bold.verdict=SKIP_CONF_LVL_REC_AFTERNOON`). So candidate (b)'s removal set is actually **31
decision rows**, not the 29 the `.md` states — 2 of them (same-day, same-setup, both risky-role
arms) have **completely unknown dollar impact**, and this gap is not mentioned anywhere in the
`.md`'s candidate-(b) section. This does **not** touch safe-3's or the population's cohort A/B
headline numbers — I independently confirmed `n_unmatched: 0` on both of those directly in the
JSON (`population_overall.cohort_A_bypass_all_arms.n_unmatched=0`,
`...cohort_B_both_passed_all_arms.n_unmatched=0`, `safe3_only.cohort_A_bypass.n_unmatched=0`).
It's a real, disclosable gap, confined to a secondary candidate-costing figure, not a defect in
the primary finding.

*(Note: a sibling verify pass, `verify-fleet-gates-bypass-cohort-pnl-2.md`, independently found
this same "0 unmatched" discrepancy via a CONSEQUENCE-lens angle, plus ran a top-3-trade-removal
stress test that flips several headline cuts negative, including candidate (b)'s "only cut that
survives" framing. That pass and this one triangulate on the same underlying data issue from two
different lenses, which strengthens rather than weakens the case that it's real.)*

---

## What was NOT independently re-derived here

- The candidate (b) mirror-case gate breakdown and named-day table were checked against the
  rerun JSON (matches), but I did not hand-verify the risky-role mirror-case dollar figures
  against raw fills the way I did for today's 8 trades — time-boxed to the sign-flipping claim.
- I did not re-implement `_strategies_block`/`_ribbon_strategy_entries` line-by-line to prove the
  `side`/`setup` fields `classify_entry()` reads always match what a real fleet-arm order carries
  — I verified this empirically instead (4 core_tick_id pairs, both arms, exact match), which is
  weaker than a full static proof but is a direct ledger-row check, per the assigned lens's own
  standard.
- I did not re-verify the September/named-day sub-splits beyond what the rerun JSON already
  reproduces byte-identically to the shipped JSON.

## Bottom line

CODE-PATH lens result: the join mechanism is real, traces to quoted source at every step
(`fleet_executor.py:933-935`, `build_shared_signal.py:293`/`583-599`/`816-823`,
`heartbeat_core.py:183-199`, `params.json:215`/`314`, `aggressive/params.json:52`), and the
`verdict`-field proxy the script uses is shown — via a trace one layer deeper than the report's
own citation (`_map_core_row`'s `"action": verdict` remap) — to be the *correct* field for the
production pass-check, not merely a plausible stand-in. Every headline dollar/WR/PF/CI number I
checked reproduced exactly on rerun, and the sign-flipping "today" claim reproduces to the penny
from raw fills for both arms. One disclosed-nowhere factual error stands: the "0 unmatched"
claim is false by 2 rows, both in the non-headline cohort C, undercounting candidate (b)'s true
scope from 29 to 31 trades with 2 of unknown effect. **Finding stands: SUPPORTED, not refuted.**
