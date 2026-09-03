# VERIFY — G5 design-intent finding (fleet-gates-design-intent.md), CONSEQUENCE lens

Stamp: 2026-09-03 14:30 ET (`et_clock.py`). Read-only skeptic pass. Nothing armed, changed,
edited in any trading-path file, or ordered. New files only, per this session's constraint.

## Verdict up front

**NOT REFUTED.** Every checkable factual claim in `fleet-gates-design-intent.md` reproduces
against current on-disk code, git history, and the cited docs — commit hashes, dates, commit
messages, code line numbers, docstrings, and cross-doc quotes all match verbatim on independent
re-read. I could not find a single misquote, wrong line number, or unsupported leap. One piece
of NEW evidence I found (not in the original report) makes the "undocumented side effect" framing
*stronger*, not weaker (see §3). Under the CONSEQUENCE lens specifically: **this finding changes
neither what the go-live gate measures (confirmed: 100% ledger-derived, zero code path reads
`profile_summary` for pass/fail) nor what a 09-29 kill-type change would do (this finding proposes
no code change — DOC_FIX only, comment/doc text — and explicitly defers the substantive
admission-routing question to a future judgment call).**

---

## 1. Independent re-verification — what I checked directly, not by trusting the report

| Claim | Check performed | Result |
|---|---|---|
| `e816178d` / `e3a44956` are 2026-08-12, fix a narrower for-cause-disarm bug (`vwap_continuation`) | `git show -s --format` on both hashes | **Confirmed verbatim** — dates, messages, and the specific "43 fills / −$1,046" figure quoted correctly from `e816178d`'s own message |
| `EMIT_STRATEGIES`/FIX2 architecture actually introduced 2026-06-26 in `667217a1`, not the 08-12/08-13 cluster | `git show 667217a1 --stat` (shows `build_shared_signal.py \| 518 +`, i.e. file CREATED that commit) + `git log -S "EMIT_STRATEGIES"` (only 2 hits total, earliest = 667217a1) | **Confirmed** |
| `fleet_executor.plan_all` (line ~933-935) takes `_plan_from_strategies` whenever `signal.get("strategies") is not None`, and `_perception_for_arm` is reachable **only** in the `else` branch | Direct read of `automation/state/fleet/fleet_executor.py:909-970` this session | **Confirmed exactly** — quoted the real code below |
| `_plan_from_strategies` never calls `_perception_for_arm` / never reads `signal["safe"]`/`signal["bold"]` | Direct read of `fleet_executor.py:721-774` | **Confirmed** — it iterates `signal.get("strategies") or []` only, role-blind |
| `EMIT_STRATEGIES = True` is the live default, unchanged since introduction | `git log -p -S "EMIT_STRATEGIES = "` on `build_shared_signal.py` — single insertion, zero later toggles found in history | **Confirmed** |
| DEEP-REVIEW-2026-08-13-MULTIAGENT.md §3 ("the docstring is false") already proved the exact safe-3 symptom, quotes match | Direct read of `analysis/deep-research/DEEP-REVIEW-2026-08-13-MULTIAGENT.md` lines 1-140 | **Confirmed verbatim** — "$410 (53%)", "$325 (42%)", "$122 worse", "genuinely-looser arm... producer-side lane" all reproduce exactly |
| `ae6e0059`'s commit message states the exact unresolved scope limit + "THIRD stale-guarantee comment" quote | `git show -s --format=%B ae6e0059` | **Confirmed verbatim**, full text reproduces |
| `fleet_executor.py:790`'s "apply UNIFORMLY to every arm" comment is still present today, unqualified, unchanged since 2026-08-14 | Direct read of current file (lines 785-795) + `git log -L 780,800:...fleet_executor.py --since=2026-08-14` (zero commits touched that block) | **Confirmed** — still bare "apply UNIFORMLY to every arm," no clarifying clause added |
| `build_shared_signal.py`'s STALE-GUARANTEE CORRECTION dated 2026-08-14 exists | grep + direct read, line 12 | **Confirmed** |
| safe-3's `gate_override` = `min_triggers:2, require_confluence_or_sequence:true`; designation `profile_summary` text matches quoted string exactly; safe-3 is criterion-5's arm | Direct read of `accounts.json` and `prod-shadow-designation.json` | **Confirmed byte-for-byte** |
| `ARCHITECTURE.md` §3.2a "Known gaps" lists only kill-switch-latch + PDT-enforcement, omits the admission-source gap | Direct read of lines 160-168 | **Confirmed** — only those two bullets present |
| `dual-account-design.md`'s "no cross-contamination" is about the **core** safe-2/bold-2 pair, not fleet | Direct read, "Overlap Resolution" section (line 139) | **Confirmed** — doc has no fleet/safe-3 mentions at all |
| Dashboard grep for fleet-gate-coverage claims — report labels this UNVERIFIED/weak | Ran my own grep across `dashboard/` | **Consistent** — only hit was `fleet-pnl.ts:48`, a display-order comment ("fleet gate-variant arms"), not a coverage claim. Report's own UNVERIFIED caveat here is appropriately cautious, not overclaiming. |
| `go_live_gate.py`'s `prod_shadow_criterion()` never uses `profile_summary` for pass/fail | Direct read, `setup/scripts/go_live_gate.py:765-825` | **Confirmed** — `profile_summary` is carried into `result["designation"]` as **display-only** metadata; the pass/fail path is `window_rows = [r for r in engine_rows if r["arm"]==arm and window_start<=r["date"]<=window_end]` → `statistical_criterion()`, pure ledger arithmetic, no config/gate-identity read anywhere |
| Sibling doc's day-count arithmetic (43 / 3 / 19 / 24 trading days for the 09-01..10-30 window, Labor Day excluded) | Recomputed independently in Python | **Confirmed exactly** — all four numbers reproduce |

### New finding this pass (not in the original report, strengthens it)

`_perception_for_arm` and `EMIT_STRATEGIES = True` (and the `plan_all` branch that makes the
former unreachable whenever the latter holds) were **all introduced in the same commit**,
`667217a1` (2026-06-26) — confirmed via `git show 667217a1:automation/state/fleet/fleet_executor.py`
and `git show 667217a1:automation/state/fleet/build_shared_signal.py`, both already containing the
identical branch shape and default. This means the "purpose-built safe carve-out" was not a
working mechanism later orphaned by a subsequent change (which would read as ordinary code drift)
— it was **built unreachable in production from its very first commit**, alongside the mechanism
that pins it there. This is *more* consistent with "undocumented side effect / never separately
decided," not less: nothing in the historical record shows a moment where someone deliberately
chose FIX2-over-role-routing for safe-3 — the two were authored together without an evident
adjudication between them.

---

## 2. CONSEQUENCE lens — direct answer

**Does the finding change what the go-live gate is measuring?**

**No.** Verified directly (not merely cited from the sibling doc): `go_live_gate.prod_shadow_criterion()`
filters `trades-enriched.jsonl` rows by `arm == "safe-3"` and date window, then runs a bootstrap
PF/CI purely on realized fills. `profile_summary` — the only place safe-3's gate identity is even
described — is passed through into the report as inert text (`result["designation"]["profile_summary"]`)
and never enters the pass/fail arithmetic. The gate already, today, scores exactly what safe-3
actually traded — including every entry sourced via the bold-perception leak — whether or not
anyone believes safe-3 "should" have been gated differently. G5's finding (was this intended?)
changes the *interpretation* of what that number represents (safe's own edge vs. a blend
contaminated by bold's looser admission) but changes **zero bytes** of the measurement itself.

**Does the finding change what a 09-29 kill-type change would do?**

**No — because G5 proposes no kill-type change.** Its own `change_class` is `DOC_FIX`
(two comment/doc edits, confirmed NOT YET applied — I re-read both target locations and both
still show the original, unqualified text) and its own `kills_winners` field states the
substantive question is deliberately **not** resolved here, only handed to the main session as a
judgment call. The quantitative "what would a 09-29 admission-routing fix do to the go-live
clock" question is answered by a **sibling** document in this same batch
(`fleet-gates-designation-accuracy.md` §4), not by G5 — and that sibling's own day-level
methodology (joining `core-decisions.jsonl` leak-ticks against `safe-3/decisions.jsonl` per date,
finding 0 of 12 leak-affected dates were the *sole* reason that date scored) is a genuinely
different, harder check than the naive participation-rate math, and its arithmetic reproduces
exactly under independent recomputation (43/19/24 trading-day split, above). G5 is correctly
scoped as a prerequisite ("was this ever decided") to that separate quantitative question, not a
restatement of it.

---

## 3. Top-3-contributor removal test

Ranking the three most load-bearing individual facts behind the SUPPORTED verdict:

1. **Fact 4** — `_perception_for_arm` is dead code on the production path (the mechanical crux).
2. **Fact 2** — FIX2/`EMIT_STRATEGIES` actually dates to 2026-06-26 (`667217a1`), correcting the
   task brief's own conflation with the 08-12/08-13 cluster.
3. **Fact 5** — the 2026-08-13 36-agent review already caught and named this exact symptom three
   weeks earlier (the "already found, left open" narrative spine of the headline).

**Remove all three and re-ask the underlying question** ("was safe-3's inclusion in the
role-blind bypass ever separately decided?") using only what remains:

- Fact 3 (verified): `SCORING_PEAK_LIVE`/the "genuinely-looser arm" doctrine text is explicitly
  scoped to bold-2/risky-1/risky-3 — it argues for the **general mechanism**, never names
  safe-3, and safe-3's own designation profile calls it "safe sizing, tight **gate**," never
  "tight signal source."
- Fact 8 (independently re-verified this session, not merely re-quoted): the one comment that
  *would* claim uniform gate application (`fleet_executor.py:790`) is still unqualified today,
  unedited since 08-14, i.e. no corrective decision has ever been recorded there either.
- Facts 9-13 (independently re-verified: doctrine text, `ARCHITECTURE.md`'s gap-list omission,
  `dual-account-design.md`'s core-only scope): all still hold without Facts 2/4/5.

**The SUPPORTED verdict survives** on this residual evidence alone — it is over-determined, not
resting on any single fact. What is lost without the top-3 is the *richness* of the narrative (the
dead-code mechanism trace, the precise 06-26 origin date, the "already caught 3 weeks ago"
drama) — none of which is necessary to answer the underlying yes/no design-intent question, only
to make the case vivid. This is a genuine robustness property, not a coincidence: the doctrine
documents (`CLAUDE.md`, `MAP.md`, `GATE-PROVENANCE-AUDIT-2026-07-02.md`,
`WEEKLY-OPTIONS-PROGRAM.md`) independently and repeatedly assert "same shared signal, differ only
in sizing/gates/exit" — a claim that is either true of safe-3's admission path or it isn't, and no
document anywhere affirmatively carves safe-3 into the bold-sourced bypass the way `SCORING_PEAK_LIVE`'s
own comment does for the three "genuinely looser" arms by name.

---

## 4. What I did not (and could not, given scope) re-verify

- The report's own two UNVERIFIED caveats (dashboard-grep completeness; whether any commit
  between 08-14 and 09-03 reverted a prior fix to the stale comment) — I ran the same class of
  check (grep + `git log -L`) independently and got the same negative result, but neither check
  is exhaustive proof of absence; they remain appropriately labeled UNVERIFIED, not FACT.
- I did not re-verify the sibling documents' full P&L/entry-count exposure figures (the "~8% of
  entries, 11/133 ticks" number in `veto-scope-safe-3.md`/`fleet-gates-ledger-binding-check.md`)
  beyond spot-checking the three quoted core-decisions/fleet-decisions/fills-ledger rows in
  `veto-scope-safe-3.md`, which reproduce exactly as quoted. A full independent re-join of the
  ledgers was out of scope for a design-intent verification and is not needed to assess G5's own
  claim (design intent, not dollar exposure).
- No trading-path file was read for behavior beyond what is quoted, no code executed, nothing
  armed/changed/ordered — consistent with this session's read-only constraint.

---

## Bottom line

The finding is **NOT REFUTED**. Confidence: **high**. Every falsifiable claim I checked —
commit hashes/dates/messages, code branch logic, live default values, cross-document quotes,
designation-file text, and the go-live gate's actual pass/fail mechanics — reproduced exactly.
Under the CONSEQUENCE lens, the finding is inert with respect to the go-live gate's math (by
design: it is a DOC_FIX proposal, not a code change) and correctly defers the one question that
*would* have consequence (should safe-3 be re-routed through `_perception_for_arm`, and what would
that cost the go-live clock) to a sibling document that already ran the harder, non-naive version
of that check and whose headline day-count arithmetic reproduces exactly under independent
recomputation.
