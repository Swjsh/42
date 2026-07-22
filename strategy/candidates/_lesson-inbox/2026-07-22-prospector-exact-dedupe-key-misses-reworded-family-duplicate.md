# Lesson Inbox — exact dedupe_key misses a re-worded concept-family duplicate

**Routed by:** conductor (AFTERHOURS fire, 2026-07-22 ~05:48-07:50 ET)
**Source commit:** `a4368bd`

## Symptom
`setup/scripts/prospector.py`'s dedupe_key is `beat:slugify(idea_text, 40)` —
stable only for EXACT idea wording. The free-tier swarm re-discovers the SAME
underlying concept under different beats and different phrasing every few
days: live count found 2026-07-22, **5 separate VIX1D chef-inbox items**
(`vix1d_gate`, `cboe-vix1d-index-tracking` ×2, `vix-term-structure-slope-
vix1d-minus-vix`, `cboe-vix1d-index-as-volatility-gauge`) and **3 separate
Volume-Profile/VPVR items** (`volume_shelf_tv_vp`, `volume-profile-visible-
range-vpvr-shows-`, `volume-profile-visible-range-vpvr-visual`) — each with
a unique dedupe_key, each independently promoted into `_chef-inbox/`, each
requiring a human/conductor fire to manually notice the duplication before
folding it (versus the file just sitting there as fresh-looking, untriaged
work).

## Root cause
`already_promoted_from_inbox()` (built for a DIFFERENT, earlier incident —
see the sibling `state.json`-loss lesson near L214/L228, C34) matches by
dedupe_key TAIL, which is still exact-wording-dependent. There was no
SECOND, coarser check for "is this the same underlying concept, just worded
differently by a different beat/model." Nothing enforced that the swarm's
paraphrase-diversity (a FEATURE for idea generation) couldn't also produce
duplicate WORK for the chef/conductor to re-triage.

## Fix (this instance)
`FAMILY_KEYWORDS` + `family_already_covered()` in `prospector.py`: a small,
hand-curated keyword-family allowlist (currently `vix1d`, `volume_profile`).
Before `promote_top1` writes a new chef-inbox file, it checks whether the
new idea's text hits the same keyword family as an EXISTING chef-inbox item
(open or `.DONE` — a `.DONE` item means the concept was already researched,
which is the point). If so, it folds (marks the dedupe_key consumed, writes
NO new file) instead of re-promoting. Retroactively folded the 2 live
duplicates found this fire. Guard tests: `backtest/tests/test_prospector.py`
(`test_idea_family_*`, `test_family_already_covered_*`,
`test_promote_top1_folds_family_duplicate_*` / `test_promote_top1_still_
writes_new_file_for_family_less_idea` — 12 new cases, 64/64 total pass).

## Generalization
Any producer that (a) generates candidate work items via an LLM with
paraphrase variance, and (b) dedupes by an exact/near-exact key derived
from that LLM's own wording, is exposed to this class: exact-key dedup
catches EXACT re-asks, never a re-WORDED re-ask of the same concept. The
fix pattern (a small hand-curated keyword-family allowlist, checked as a
coarse SECOND layer before the exact-key check, favoring false-negatives
over false-positives) generalizes to any other LLM-fed inbox in this repo
(skill-inbox, validator-inbox) if the same symptom is ever observed there —
not pre-built speculatively, only if/when the symptom actually recurs.

## Related
C7 (silent success is failure — 64 already-DONE files sat unnoticed as
"noise" for weeks before this fire's manual audit caught it), the sibling
`state.json`-loss lesson (L214/L228, C34 — same SYMPTOM class "duplicate
_chef-inbox files," different root cause: state loss vs exact-key-misses-
rewording).

## Priority / Dependencies
depends:none — code already shipped in commit `a4368bd`; this item is for
`lesson-author` to fold the prose above into `markdown/doctrine/LESSONS-
LEARNED.md` as the next `L##` and append the CLAUDE.md OP-25 index bullet
(new theme, or fold into C34/C7's existing rows if judged a natural fit).
