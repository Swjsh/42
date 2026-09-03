# VERIFY — G5 design-intent finding (role-blind sourcing of sig['strategies'])

Stamp: 2026-09-03T14:39 ET (`et_clock.py`, market_hours=True). Read-only skeptic pass on
`analysis/deep-research/2026-09-03-money/fleet-gates-design-intent.md`. Independent join
rebuilt at `backtest/tools/fleetgates_verify_design-intent_1.py`, output
`analysis/deep-research/2026-09-03-money/fleetgates-verify-design-intent-1.json`. No
`automation/state/**` file written; no trading-path file edited; no broker/market call made.

## Verdict up front

**NOT REFUTED — the finding's central, checkable claims all independently verify, several of
them exactly, and my own ledger rebuild extends (not just reproduces) the evidence. But
`refuted=false` comes with real caveats: section "2a" of the report mischaracterizes which arms
its own cited primary source (`build_shared_signal.py:281`'s SCORING_PEAK_LIVE comment) actually
names, misclassifies `bold-2` as a consumer of the bypass it is structurally incapable of
consuming, and never engages the single most on-point piece of counter-evidence in the repo
(`accounts.json`'s own grid-founding `_doc`, dated the same day as the flip). None of these
overturn the headline verdict, but the main session should not cite section 2a as clean support
without the corrections below.**

---

## 1. Code claims — every line-number citation checked against current HEAD, all exact

| Report claim | My check | Result |
|---|---|---|
| `_perception_for_arm` at fleet_executor.py line 108, docstring calls it a "perception-source confound fix" | `grep -n "def _perception_for_arm"` -> line 108; docstring text read in full | **EXACT MATCH** |
| `plan_all`'s `strategies` branch at line ~933-935 | `grep -n 'if signal.get("strategies")'` -> line 933 | **EXACT MATCH** |
| `strategies.fired() -- INERT` comment ~line 495-497 | `grep -n` -> line 494 (comment block starts there) | **MATCH** (off by one line, immaterial) |
| stale "apply UNIFORMLY to every arm" comment at fleet_executor.py:790 | `grep -n "apply UNIFORMLY"` -> line 791 | **MATCH** (report also says 789/790 elsewhere — both are in the neighborhood of the actual line 791; not a material discrepancy) |
| `EMIT_STRATEGIES = True` at build_shared_signal.py:293 | `grep -n` -> line 293 | **EXACT MATCH** |
| `SCORING_PEAK_LIVE = True` since 2026-06-25 | `grep -n` -> line 281, comment text read | **MATCH, with a correction — see §3 below** |
| `build_shared_signal.py:1131` "genuinely-looser arm... producer-side lane" quote | read lines 1110-1145 | **TEXT MATCHES VERBATIM, but is the FULL-SEND lane's rationale, not the EMIT_STRATEGIES/dual-perception mechanism under investigation — see §3** |
| STALE-GUARANTEE CORRECTION dated 2026-08-14 in build_shared_signal.py's module docstring | read lines 1-24 | **EXACT MATCH**, including the "-$325" and "11:41-11:43" figures |
| commit hashes/dates: `e816178d` (2026-08-12 22:43:16 -0600), `e3a44956` (2026-08-12 23:12:20 -0600), `667217a1` (2026-06-26 14:15:44 -0600), `ae6e0059` (2026-08-13 15:09:09 -0600) | `git show -s --format="%H %ci %s"` on each | **ALL EXACT** |
| e816178d: "43 fills -$1,046" | `git show -s --format=%B e816178d \| grep` | **EXACT** ("TOTAL 43 fills -$1,046") |
| ae6e0059: "THIRD stale-guarantee comment found today" + "I could not resolve a contradiction: fleet_executor.py:789 asserts... apply UNIFORMLY to every arm" | `git show -s --format=%B ae6e0059 \| grep` | **EXACT** |
| "the comment... is STILL uncorrected... verified by direct read... 2026-09-03" | `git log -p --all -- fleet_executor.py \| grep "apply UNIFORMLY"` returns exactly ONE hit across the entire history of the file; `git log --since=2026-08-14 -- fleet_executor.py` shows 5 commits, none of which touch that comment (checked each commit's diff stat and none modifies that line range) | **CONFIRMED — resolves the report's own "UNVERIFIED: whether a commit reverted a prior correction" caveat. It did not.** |
| "no hits in dashboard/" for fleet-gate-coverage claims | `grep -rIl "fleet.*gate\|gate.*fleet\|strategies\["  dashboard/` (non-timing-out, completed) -> only `dashboard/lib/fleet-pnl.ts:50`, a display-order array comment naming arms, zero admission/gate-coverage claim | **CONFIRMED — resolves the report's other "UNVERIFIED" (weak-grep) caveat. The negative result holds up under a completed run.** |
| DEEP-REVIEW-2026-08-13-MULTIAGENT.md §3 quote: "at 11:41-11:43 safe returned SKIP_BULL_1100_1200... safe-3, risky-1 and risky-3 all entered at 11:42:05 for -$325 = 42% of the day's losses" | `grep -n` on that file | **EXACT, word for word** |

Every checkable factual citation in the report holds up. This is a well-sourced report on the
mechanics.

---

## 2. Independent ledger rebuild (the assigned LEDGER lens) — CONFIRMS and EXTENDS the pattern

Built my own join from scratch (`backtest/tools/fleetgates_verify_design-intent_1.py`), not
reading either of this session's two prior report scripts: `core-decisions.jsonl` (37,981 rows,
9,168 unique `core_tick_id`s, 0 malformed lines, 0 duplicate account/tick pairs) joined to each
of `safe-3`/`risky-1`/`risky-3`'s `decisions.jsonl` (only `ENTER_BULL`/`ENTER_BEAR` rows kept)
on `core_tick_id`, classified against the tick's own `safe` and `bold` core verdicts, then
cross-checked against `fills-ledger.jsonl` buy-side fills by arm+symbol+nearest-timestamp
(matched 38/40 role-blind entries to a real fill within 180s; 2 unmatched, both explainable —
see caveats).

**Recount, whole-history, per arm (`role_blind_ride` = safe's own core verdict at that exact
tick was blocked (`HOLD`/`SKIP_*`/`ERROR`) AND bold's core verdict at that same tick was
`ENTER_<same side>`):**

| Arm | total live ENTER rows | `safe_faithful` (safe's own verdict already agreed) | `role_blind_ride` (rode bold's verdict) | `no_safe_row_for_tick` (no core row joins — see caveat) | other/no-explanation |
|---|---|---|---|---|---|
| safe-3 | 91 | 43 (47.3%) | **13 (14.3%)** | 33 | 2 |
| risky-1 | 149 | 71 (47.7%) | **17 (11.4%)** | 34 | 27 |
| risky-3 (retired 2026-08-28) | 149 | 58 (38.9%) | **10 (6.7%)** | 48 | 33 |

**Gate breakdown of the 40 `role_blind_ride` events (which safe-side gate was actually the
blocker):** `SKIP_BULL_1100_1200` (29 of 40, ~73%), `SKIP_STRUCTURE_VETO` (9 of 40), and
`SKIP_DOJI_ENTRY_BAR` (2, risky-1 only). This matches the two gates `veto-scope-safe-3.md`
independently named as the load-bearing ones (`block_bull_1100_1200`, `structure_veto_enabled`
— both confirmed absent from `aggressive/params.json`, both present in `params.json`).

**08-13 example — matches DEEP-REVIEW-2026-08-13-MULTIAGENT.md exactly:** my join independently
found `core_tick_id 2026-08-13T11:41:02.990155`, safe=`SKIP_BULL_1100_1200`, bold=`ENTER_BULL`,
and all three of safe-3/risky-1/risky-3 firing `ENTER_BULL` on that exact tick — the same event
the deep review named, found independently rather than copied from either report.

**08-27 — a second, previously-uncited instance of the identical signature:** `core_tick_id
2026-08-27T11:51:02.356914` (safe-3, risky-1) and `2026-08-27T11:52:02.413124` (risky-3), same
`SKIP_BULL_1100_1200`/`ENTER_BULL` shape. Neither report cited this date; it is new corroborating
evidence this session generated, not carried over.

**09-03 (today) — matches veto-scope-safe-3.md's quoted rows exactly**, `core_tick_id
2026-09-03T11:06:02.738610` and `2026-09-03T11:21:02.576928`, safe-3 AND risky-1 both entering
on both ticks (the companion doc quoted only safe-3's rows — my join shows risky-1 rode the
identical ticks too, which the companion doc did not report).

**09-02 — a THIRD previously-uncited instance, one day before this session started:**
`core_tick_id 2026-09-02T11:16:02.370383` and `2026-09-02T11:56:02.455136`, same
`SKIP_BULL_1100_1200`/`ENTER_BULL` shape, safe-3 and risky-1 both entering both ticks. Neither
report mentions 09-02. This means the bypass is not a rare, cherry-picked event — it recurred on
4 of the 5 most recent trading-day instances I could check (08-13, 08-27, 09-02, 09-03), always
via the identical two gates.

**08-06 and 08-28 (the other two named "winning days"): ZERO `role_blind_ride` events on either
day**, for any of the three arms. This session's HARD CONSTRAINTS instruct checking the four
named winning days; I did, and two of the four show no trace of this specific bypass signature —
neither report claimed otherwise (neither report ties dollar wins on those two dates to this
mechanism), so this is a clean check, not a contradiction, but it is worth stating plainly: this
mechanism is not what made 08-06 or 08-28 winning days.

**September window (09-01 through today):** 8 `role_blind_ride` events total, 4 safe-3 / 4
risky-1, on 09-02 (4) and 09-03 (4); 09-01 had zero fleet ticks at all (Labor Day, market
closed — sanity-consistent, not investigated further). Rough notional (qty x premium x 100, the
decision-row basis) for safe-3 alone in the window is $1,545 across 4 entries; fill-basis
notional is materially the same ($1,547) — the two bases agree within noise, which is a good
sign the join is not systematically mis-attributing fills.

**Caveat on `no_safe_row_for_tick` (33/91 for safe-3, 34/149 for risky-1, 48/149 for
risky-3):** I did not fully explain this bucket. A spot check of a handful of these rows shows
`setup_name` values outside `BULLISH_RECLAIM_RIDE_THE_RIBBON` (consistent with
`vwap_continuation`, the REST-detector strategy build_shared_signal.py documents as
"un-blockable... not core-gated" and therefore not expected to have a matching
`core-decisions.jsonl` row at all) — plausible, but I did not verify this line-by-line, so it is
**UNVERIFIED, not asserted as fact**. It does not change the `role_blind_ride` counts above,
which only count rows where a core row for both accounts and that exact tick actually exists.

**Net: my independent, from-scratch ledger rebuild does not disagree with either report's
ledger claims anywhere I could check them, and materially extends them (two new dates, one new
arm-on-a-known-date, and one basis-cross-check that holds up).** Per this task's own standard
("a material disagreement is a refutation"), I found no material disagreement.

---

## 3. Where the report's argument (not its ledger evidence) has real problems

These are corrections to the SUPPORTING ARGUMENT in section "2a" of the report, not to its
ledger claims (§2 above), and not, on balance, enough to flip the verdict — but the main session
should not repeat them uncorrected.

### 3a. `bold-2` is not a fleet_rest consumer of this bypass — it cannot read `sig['strategies']` at all

`accounts.json`'s own per-arm `execution` field: `safe-3`=`fleet_rest`, `risky-1`=`fleet_rest`,
`risky-3`=`fleet_rest` (retired), **`bold-2`=`mcp_heartbeat`**, same as `safe-2`. `bold-2` is
one of the two CORE accounts, traded directly by `heartbeat_core.py` off its own ledger's
verdict — it never calls `fleet_executor.plan_all`, never reads `shared-signal.json`, and is
structurally incapable of "consuming" the `sig['strategies']` bypass the report's headline is
about. It is a **SOURCE** of the bypass (its own `ENTER_BULL` row is what gets peak-sourced into
`sig['strategies']` on ticks where safe's row is blocked) — a different, opposite role from
"genuinely looser arm that reads the bypassed signal." The report's section 2a lists `bold-2`
alongside `risky-1`/`risky-3` as one of the arms for which the bypass is "documented,
deliberate, J-directed" — that is a category error. Notably, the report's OWN cited source
(`DEEP-REVIEW-2026-08-13-MULTIAGENT.md` §3, line 86) does NOT make this error: it names only
"safe-3, risky-1 and risky-3" as the arms that "entered where production refuses," and reports
`bold-2`'s dollar figure on a separate line (§3, table row, `-$410` for the 4-arm group vs
`-$325` for the 3-fleet-arm-only group) — i.e. the primary source the report cites keeps this
distinction clean; the report's own synthesis blurred it.

### 3b. The SCORING_PEAK_LIVE comment names different, and now-retired, arms

The report's strongest piece of "2a" evidence quotes the flip flag's comment as documenting
intent for "all paper fleet ar[ms]" without completing the quote. Read in full
(`build_shared_signal.py:281`):

> `SCORING_PEAK_LIVE = True  # flipped 2026-06-25 (J directive): all paper fleet arms live for
> the DATA; loose arms (safe-1/risky-3) consume scoring-peak passes.`

The comment's own named "loose arms" are **`safe-1` and `risky-3`** — not `bold-2` and not
`risky-1`, the two arms the report's headline treats as clearly-and-currently covered. Checked
both against `accounts.json`:

- `safe-1`: `status: "retired"`, `retired_at: "2026-07-11"` — retired **two weeks before**
  `SCORING_PEAK_LIVE` was even flipped is wrong (flip was 06-25, retirement was 07-11, so it WAS
  active for ~2 weeks under the flag) but has been gone for 7+ weeks as of today.
- `risky-3`: `status: "retired"`, `retired_at: "2026-08-28"` — the one arm this specific
  comment names as a going concern is now retired, 6 days before this verification.

So the ONE code comment that names specific arms for THIS EXACT mechanism (not the separate
`full_send`/`probe`/`score_ladder` lanes, which have their OWN separate documented rationales
and are correctly attributed to `risky-1`/`risky-3` respectively) names zero arms that are both
(a) active today and (b) actually the ones riding the bypass in my ledger rebuild (`safe-3`,
`risky-1`). `risky-1`'s documented "genuinely looser" status comes from a DIFFERENT mechanism
entirely (`full_send`, `accounts.json`'s `full_send_doc` field, its own separate producer block
`FULL_SEND_ALLOWED_VERDICTS` / consumer `_full_send_plan`) — real and well-documented on its own
terms, but not the same mechanism as `EMIT_STRATEGIES`/`_plan_from_strategies`, which is what my
ledger rebuild shows is actually firing every `role_blind_ride` row (all 40 have `setup_name
BULLISH_RECLAIM_RIDE_THE_RIBBON` via the normal `strategies[]` path, none via `_full_send_plan`).
The report conflates three separate, individually-documented bypass mechanisms (`full_send` for
risky-1, `probe`/`score_ladder` for risky-3, `SCORING_PEAK_LIVE` dual-perception for the shared
`strategies[]` block) into one undifferentiated "documented for bold-2/risky-1/risky-3"
sentence. Each individual mechanism's documentation is real; the merged attribution is not
accurate to any one of them.

**Net effect on the verdict:** if anything this sharpens, rather than undermines, the report's
central claim — it shows that even the ONE mechanism-specific naming comment in the entire
codebase does not name `safe-3` (nor does it currently name any active arm), which is consistent
with "safe-3's inclusion in this specific bypass was never separately decided." It does mean
section 2a overstates how cleanly "documented and deliberate" the bypass is for the arms
currently riding it.

### 3c. A genuinely new piece of evidence neither report found: a dead, never-enforced per-arm intent flag

`accounts.json:191` carries `"consumes_scoring_peak": true` on `risky-3` — and **nowhere else**
(checked every arm block; `safe-3` and `risky-1` carry no such key). `grep -rn
"consumes_scoring_peak" automation/ backtest/ setup/` returns exactly one code-adjacent hit
(the `accounts.json` line itself, plus its pre-grid backup and an integrity snapshot) — **the
flag is never read by any Python file.** It is pure metadata: someone, at some point, tried to
mark per-arm intent for exactly this mechanism (which arm SHOULD consume the scoring-peak
signal), named only `risky-3`, and the marking has zero runtime effect — every arm that takes
the `strategies` branch gets the identical peak-sourced list regardless of this flag. This is
independent, load-bearing corroboration for the report's "2b" claim (safe-3's inclusion was
never separately decided) that neither report surfaced — worth folding into the record.

### 3d. A significant piece of counter-evidence the report never engages: the grid's own founding doc

`accounts.json`'s top-level `_doc` field (dated 2026-06-25, the SAME day as the `SCORING_PEAK_LIVE`
flip and the grid rebuild) states plainly: *"AN ACCOUNT IS NOT A STRATEGY. Every account is a
(gate-strictness x contract-sizing) profile; EVERY validated strategy in
automation/state/fleet/strategies.py runs on EVERY account via fleet_executor.plan_all. The
account only decides how SELECTIVE the entry gate is (gate_override) and how BIG the position is
(sizing)."* The same file's `update_note` (also 2026-06-25): *"6 SPY arms recast as a clean 2x3
matrix... Strategies now live in strategies.py and run on all arms."*

This is the single most authoritative, most directly on-point, and EARLIEST-dated design
document governing the grid architecture in the whole repo — more primary than any of the four
secondary docs (`FABLE-DECISIONS-2026-07-07.md`, `GATE-PROVENANCE-AUDIT-2026-07-02.md`,
`WEEKLY-OPTIONS-PROGRAM.md`, `MAP.md`) the report's §3 quotes instead, all of which postdate and
paraphrase it. Read plainly, it is a dated, explicit statement that safe-3 (one of "every
account") was always meant to receive the SAME shared strategy pipeline as every other arm,
differentiated only by gate + sizing downstream — which is close to a decision, made at the
grid's founding, that covers safe-3 by name category. The report's §3 makes essentially this
same "doctrine read literally" argument using weaker secondary sources and never cites the
primary one.

**This does not settle the question either way** — the grid doc is explicitly about the
STRATEGY MENU (ribbon_ride + vwap_continuation both available to every account, fixing the old
per-account strategy-silo bug) and does not address the narrower, later-emerging question of
WHICH SIDE's (safe's vs bold's) pass/fail verdict should seed that menu on any given tick — a
distinction the grid doc does not appear to have anticipated. But it is real, on-point evidence
the report should have engaged with and did not, and a reader could reasonably weigh it either
way. I flag it as an omission, not as a refutation.

---

## 4. What this changes about the report's conclusions

- **Headline verdict ("SUPPORTED... never separately decided for safe-3... dead carve-out...
  caught and left unresolved on 08-13"): stands.** Every checkable fact underneath it is
  accurate, and my independent ledger rebuild both reproduces the cited examples exactly and
  finds 3 additional, previously-uncited instances of the identical signature (08-27, 09-02, plus
  risky-1 riding the same 09-03 ticks the companion doc attributed to safe-3 alone).
- **Section 2a ("documented, deliberate, J-directed... for bold-2/risky-1/risky-3") overstates
  its case and contains one factual error** (`bold-2` cannot consume this bypass) **and one
  incomplete citation** (the SCORING_PEAK_LIVE comment names `safe-1`/`risky-3`, not
  `bold-2`/`risky-1`, and both named arms are now retired). Recommend the main session correct
  this framing rather than repeat it: the intentional-and-documented arms/mechanisms are
  `risky-1`+`full_send` and `risky-3`+`probe`/`score_ladder`/`consumes_scoring_peak` — each real
  on its own terms — not a blanket "SCORING_PEAK_LIVE covers bold-2/risky-1/risky-3."
  `SCORING_PEAK_LIVE`'s dual-perception mechanism itself (the one actually producing every
  `role_blind_ride` row in my rebuild) is the one for which NO currently-active arm is named in
  its own flip comment.
  Its two UNVERIFIED caveats are both now resolved by direct checks this session ran to
  completion: the stale `fleet_executor.py:791` comment has never been touched since it was
  written (single hit across the file's entire git history), and `dashboard/` genuinely has no
  fleet-gate-coverage claim (completed grep, not a timeout-truncated one).
- **Proposed DOC_FIX is unaffected** — both proposed edits are additive/correcting-comment-only,
  consistent with what this session's own read-only ledger evidence supports, and would be
  improved by folding in the §3a/§3b corrections above (name `full_send`/`risky-1` and
  `probe`+`consumes_scoring_peak`/`risky-3` specifically, rather than a blanket
  "bold-2/risky-1/risky-3").

---

## Scripts and artifacts

- `backtest/tools/fleetgates_verify_design-intent_1.py` — independent join script, written from
  scratch this session (did not read or adapt the report's own scripts before writing it).
- `analysis/deep-research/2026-09-03-money/fleetgates-verify-design-intent-1.json` — full output
  (per-arm classification counts, gate breakdown, per-named-day and September-window detail, and
  a 50-row sample of every `role_blind_ride` event found).
- Runtime: single Python process, ~10s wall time, no network/broker call, no
  `automation/state/**` file written.

## What I did not verify

- The `no_safe_row_for_tick` bucket's composition (assumed to be `vwap_continuation` entries on
  spot-check, not exhaustively confirmed row-by-row) — does not affect the `role_blind_ride`
  counts, which only count rows with a genuine core-row match.
- Whether `08-06`/`08-28`'s status as "winning days" is itself accurate (out of scope for a
  design-intent question; I only checked whether THIS mechanism explains them, and it does not).
- Full dollar P&L reconciliation against `analysis/pain-ledger/mae-mfe.json`'s 394 scored trades —
  this note uses decision-row and fills-ledger notional (qty x premium x 100) as a fast proxy,
  which agreed with itself within noise (§2) but was not cross-checked against the pain-ledger's
  own scored numbers.
