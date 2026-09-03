# Verification — G5 design-intent finding (fleet-gates-design-intent.md)

_Generated 2026-09-03 ~14:35 ET (`et_clock.py`, market_hours=True). Skeptic pass, CODE-PATH lens: every claim re-traced from source, not taken from the report's own quotes. Read-only; nothing armed, changed, or ordered._

## Verdict: NOT REFUTED (confidence: high)

Every load-bearing claim in the report was independently re-derived from source and, where a
ledger row was cited, from the raw ledger — not from the report's paraphrase. I found zero
contradictions and two pieces of additional corroborating evidence the report did not cite.
The report's own hedges (dashboard/ grep weak, git-window-not-walked) were checked further and
both held up or were resolved in the report's favor.

## What was re-traced from source (not from the report)

**1. `plan_all` branch selection — CONFIRMED, exact.**
`automation/state/fleet/fleet_executor.py`:
```
909  def plan_all(...):
933      if signal.get("strategies") is not None:
934          plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
935      else:
936          src = _perception_for_arm(signal, arm)
```
(Report cited "~933-935"; actual is 933/934/936 — a one-line docstring/blank shifts it, same branch.)

**2. `EMIT_STRATEGIES = True` — CONFIRMED, exact line.**
`automation/state/fleet/build_shared_signal.py:293`. Module-level constant, no override at the
production call site (see #7 below) — `do_strats` is always `True` in production.

**3. `_perception_for_arm` is dead on the production path — CONFIRMED by direct trace, not inference.**
Defined at line 108 (docstring: *"a safe arm reads signal['safe']... perception-source confound
fix"*), called only at line 153 (a legacy `plan_entry`-style helper, not `plan_all`) and inside
`plan_all`'s `else` branch (line 936) and one other spot (line 1543) — both reached **only when
`signal.get("strategies") is None`**. Traced the actual production entrypoint at the bottom of
`build_shared_signal.py`:
```
if __name__ == "__main__":
    s = build()
```
Called with **zero arguments** → `emit_strategies=None` → falls back to `EMIT_STRATEGIES=True`.
`ARCHITECTURE.md`'s documented signal flow (`run-fleet-executor.ps1` → `build_shared_signal.py`
then `fleet_live.py`) uses this exact entrypoint. So `signal["strategies"]` is unconditionally
present in production, and `_perception_for_arm` never runs on the live path — confirmed at the
script-entrypoint level, one layer deeper than the report's own trace.

**4. `sig['strategies']` is sourced from whichever side passed — CONFIRMED by full read of the construction, not just the comment.**
`build_shared_signal.py:672-673, 795-823`: `row = _latest_today_decision(today, core_tick_id=...)`
with **default `account="safe"`** (confirmed at `_latest_today_decision`'s signature, line 238) —
so top-level `bear`/`bull` are the SAFE row (production-faithful). At line 814-823:
```python
s_bear, s_bull = bear, bull                       # starts from SAFE
if use_peak:
    bold = sig.get("bold") or {}
    if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
        s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull   # overridden by BOLD
sig["strategies"] = _strategies_block(s_bear, s_bull, ...)
```
This is the mechanism, read end-to-end myself: `sig['strategies']` starts SAFE-sourced and is
overridden to BOLD's block whenever bold passed a side safe didn't. Matches the report exactly.

**5. The cited ledger pair — CONFIRMED against the raw files, exact match.**
`automation/state/core-decisions.jsonl` line 37594 (`account: "safe"`, `core_tick_id:
"2026-09-03T11:21:02.576928"`, `verdict: "SKIP_STRUCTURE_VETO"`) and line 37595 (`account:
"bold"`, same `core_tick_id`, `verdict: "ENTER_BULL"`) — same tick, opposite verdicts, verified
by direct grep of the raw file, not the report's quote.
`automation/state/fleet/safe-3/decisions.jsonl` line 12410: `core_tick_id:
"2026-09-03T11:21:02.576928"`, `action: "ENTER_BULL"`, `strike: 772`, `qty: 5`, `premium: 0.73`,
order `submit_ts: "2026-09-03T11:22:07"`. Exact match to the report's cited row.

**6. Independent mechanism check the report did NOT run — further corroboration.**
`heartbeat_core.py:184-191` — `structure_veto_enabled` is one of `GATE_KEYS` (the safe-only
cohort-gate list). `fleet_executor._gate_check` (line 599-620) implements exactly three checks:
`min_triggers`, `require_confluence_or_sequence`, `min_setup_quality` — **no mention of
`structure_veto` or any other `GATE_KEYS` member.** This independently confirms, at the code
level and without relying on the report's framing, that the gate which blocked safe on this
exact tick (`SKIP_STRUCTURE_VETO`) has **zero implementation anywhere on the fleet path** — not
just "bypassed by peak-sourcing" but structurally absent from `_gate_check`. Stronger than what
the report claimed.

**7. `accounts.json`'s own grid labels safe-3 as the "safe" row — further corroboration, not cited by the report.**
`automation/state/fleet/accounts.json:37`: `"safe-3": "safe x tight"` (2×3 grid: {safe,risky} ×
{tight,base,loose}). This reinforces the report's central tension: the roster's own taxonomy
puts safe-3 in the "safe" row (implying it should inherit safe's perception per
`_perception_for_arm`'s docstring), while the actual `plan_all` code path is role-blind to that
row/column distinction entirely at admission — only `_gate_check`/sizing/exit differ by cell.

## Commit and quote verification (git log ground truth, not the report's transcription)

All four commits exist with the exact hash, author date, and subject the report claims:
| Hash | Date | Subject |
|---|---|---|
| `e816178d` | 2026-08-12 22:43:16 -0600 | fix(fleet): a params DISARM must reach the fleet arms, not just core |
| `e3a44956` | 2026-08-12 23:12:20 -0600 | fix(fleet): move the params disarm to select_plan |
| `667217a1` | 2026-06-26 14:15:44 -0600 | feat(engine): EOD 2026-06-26 — engine repairs... |
| `ae6e0059` | 2026-08-13 15:09:09 -0600 | feat(gates): gate x arm matrix |

- `667217a1`'s diff of `build_shared_signal.py` contains `EMIT_STRATEGIES = True` and the `FIX2`
  comment block verbatim (grepped the diff directly) — confirms EMIT_STRATEGIES/FIX2 originates
  06-26, not in the 08-12/08-13 cluster. Report's separation of these as three distinct events
  holds.
- `e816178d`'s full commit message: confirms the report's summary is accurate (vwap_continuation
  disarm not reaching fleet arms via `strategies.fired()`, 43 fills/-$1,046) — this is a
  different bug from role-blind `strategies[]` sourcing, correctly distinguished by the report.
- `ae6e0059`'s full commit message: contains the "THIRD stale-guarantee comment" line and the
  scope-limit paragraph verbatim, matching the report's quote almost word-for-word.
- `DEEP-REVIEW-2026-08-13-MULTIAGENT.md` §3 ("The fleet CAN enter where production refuses — the
  docstring is false"): read the full section directly — the −$325/11:42:05/safe-3+risky-1+risky-3
  quote is verbatim in the source file, not paraphrased by the report.
- `build_shared_signal.py:8-19` docstring: the "STALE-GUARANTEE CORRECTION (2026-08-14...)" block
  is verbatim what the report quotes, including "fleet exposure is NOT bounded by production's
  gate perimeter."
- `fleet_executor.py:790-791` ("apply UNIFORMLY to every arm"): read directly — still present,
  unqualified, as of this read (2026-09-03). **I went one step further than the report and
  walked `git log --since=2026-08-14` on this file**: 5 commits touched
  `automation/state/fleet/fleet_executor.py` since 08-14 (`924927a3`, `05ae765b`, `d91dd2cb`,
  `da6e961d`, `4245d4ce`), none of their diffs contain the string "apply UNIFORMLY" — so the
  comment was not touched, let alone reverted, in that window. This resolves one of the report's
  own two self-flagged UNVERIFIED caveats in the report's favor (confirmed, not merely assumed).

## Doctrine quotes — all confirmed verbatim at cited/near-cited locations

- `markdown/audits/FABLE-DECISIONS-2026-07-07.md:43` — "arms are RISK PROFILES, not strategies...
  differ only in expression parameters" — verbatim.
- `markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md:121` — "arms are RISK profiles, not
  strategies... same strategy menu everywhere, different tolerance" — verbatim.
- `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md:299` (table row, not line 299 exactly but the
  same passage) — "a RISK PROFILE inside one lane — differs ONLY by sizing/gates/stop" — verbatim.
- `MAP.md` — "The arms — risk profiles, NOT strategies... All arms trade the SAME shared signal.
  They differ only in sizing, gates and exit shape." — verbatim, confirms the report's central
  tension (the doctrine's plain reading vs. the peak-sourced admission mechanism).
- `markdown/specs/ARCHITECTURE.md:115` — "fleet_executor.py (per-arm sizing/admission,
  gate/sizing profile)" — verbatim. §3.2a's "Known gaps" list (read in full, lines 165-168)
  contains exactly 2 bullets (kill-switch latch, PDT enforcement) — the admission-source gap is
  genuinely absent, confirmed by reading the whole section, not just grepping for it.
- `automation/state/prod-shadow-designation.json:3` — the `profile_summary` string is verbatim.
- `markdown/0dte/dual-account-design.md:139` — "No cross-contamination. Safe's stricter filters
  protect it..." — verbatim, and correctly scoped by the report to the core (safe-2/bold-2) path
  only; the doc predates the fleet.
- `setup/scripts/gate_arm_matrix.py:148` — "necessary but not sufficient" — confirmed (near-exact
  paraphrase of the report's slightly longer quote, same substance).

## The one caveat I re-checked and partially extended

Report caveat: "UNVERIFIED whether dashboard/ genuinely contains zero fleet-gate-coverage
claims... first attempt timed out." I ran a broader grep than the report describes (source dirs
`dashboard/app`, `dashboard/lib`, `dashboard/components`, keyed on `gate|admission|strateg[y]|
perception|shared.signal`) and found exactly one hit outside node_modules/build cache:
`dashboard/lib/fleet-pnl.ts:48`, a comment — *"the three fleet gate-variant arms"* — which is a
display-ordering label, not a coverage or admission-source claim. The report's "no fleet-gate-
coverage claim in dashboard/" holds up under a more thorough check; the caveat can be downgraded
from UNVERIFIED to VERIFIED (weak-negative, i.e., confirmed absence, not just an unreturned grep).

## Assessment against the report's classification

`change_class: DOC_FIX`, `kills_winners: N/A` — appropriate. No trading-path file is touched by
either proposed edit; both are additive comments. The report correctly declines to resolve the
substantive fork (route safe-3 through `_perception_for_arm` vs. leave it) and hands that to the
main session as a judgment call, consistent with the session's read-only constraint on
`automation/state/**` and the active config freeze (kill-type reductions need a prereg,
2026-09-29).

I checked the "both sides" argument in the report for internal consistency against source: the
"leave it" side's dollar citation ("$942 moved... Running BOTH ratified gates on all arms would
have been $122 WORSE than actual") is a verbatim quote from `ae6e0059`'s commit message, correctly
attributed, not a number the report computed itself — properly labeled as quoted evidence, not a
fresh calculation.

## Nothing found that contradicts the finding

I did not find any commit, doctrine doc, prereg, or code comment stating an explicit decision to
route safe-3 through the shared/peak-sourced admission (as opposed to the general "genuinely
looser arms" doctrine, which itself never names safe-3). I did not find a revert or correction of
`fleet_executor.py:790`'s stale comment in the 08-14→09-03 window. I did not find a
dashboard-side claim that contradicts "fleet admission is not always safe-faithful." Every number,
quote, commit hash, and ledger row I checked matched the report exactly or supported it further.

## What I did not re-verify (scope limits of this pass)

- Did not re-run `analysis/pain-ledger/mae-mfe.json` or bootstrap any dollar CI — this report
  makes no dollar-effect claim of its own (correctly, per its `kills_winners: N/A`), so none was
  owed.
- Did not check every one of the ~479 human-written markdown files for a possible undiscovered
  doctrine document explicitly authorizing safe-3's admission source; checked the four cited plus
  a live grep pattern (`arms are risk profiles`) which returned exactly those four plus
  `build_shared_signal.py`'s own comment (already covered above) — reasonably exhaustive for the
  claim as scoped ("never separately decided"), not exhaustive against every file in the repo.
