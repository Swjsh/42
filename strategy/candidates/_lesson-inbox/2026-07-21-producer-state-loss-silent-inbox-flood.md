# Lesson Inbox — producer state.json loss silently floods an author inbox for weeks

**Filed by:** conductor (AFTERHOURS), 2026-07-21 ~07:48-08:20 ET
**Category:** C34 (tree-wide git ops revert live state) extension — a NEW discovery angle

## The finding

The 2026-06-27..07-13 git-stash-drop incident (commit 41889a0, already covered by L214/L228
under C34) reset `analysis/prospector/state.json`, wiping its `promoted_dedupe_keys` list.
That specific downstream CONSEQUENCE was never traced until now: `Gamma_Prospector`'s daily
fire kept re-selecting the SAME already-promoted ledger rows as "oldest not-yet-promoted"
(their promotion memory was gone even though the idea rows themselves survived in the
append-only ledger), silently re-writing near-duplicate `_chef-inbox/prospector-*.md` files
under a fresh date every few days for **24 days** (2026-06-27 to 2026-07-21) before any
fire noticed. By the time this fire found it: 65 files in `_chef-inbox`, 37 of them (57%)
pure re-promotion noise across 17 duplicated ideas, and **0 of the 28 unique underlying
ideas had EVER been reviewed by chef** (0 hits for "prospector" in `_chef-log.jsonl`).

## Why this is a NEW lesson, not just a C34 repeat

C34's existing lessons (L214/L228) are about the git-ops MECHANISM (tree-wide stash/reset
reverting decision-gating snapshots backward). This is about the DETECTION GAP one level up:
a silently-reset producer-side idempotency/dedup state can flood a downstream author inbox
for WEEKS with zero functional symptom (no crash, no RED, no error) — the only observable
was volume growth in a directory nobody was auditing for backlog size specifically (author
inboxes were being *drained oldest-first* per STAGE 1 priority-5, but nobody had checked
whether the SAME idea was reappearing under new filenames — a dedup-integrity check, not a
staleness check).

## Root cause class

Any daily/periodic autonomous producer that (a) tracks "already emitted X" in a small
state file separate from its main append-only ledger, and (b) that state file lives in a
path that could be touched by a tree-wide git recovery/reset, is exposed to this same
class: state loss => idempotency memory loss => re-emission flood, invisible until manually
audited. The fix applied here (derive "already promoted" from the CONSUMER-SIDE artifact
itself — the inbox filesystem — not just the producer's own state file) is the general
antidote: **make idempotency self-healing by checking the downstream artifact, not just an
upstream counter that can be reset independently of it.**

## Suggested guard / graduation

Already graduated for prospector specifically: `already_promoted_from_inbox()` in
`setup/scripts/prospector.py` + 6 new tests in `backtest/tests/test_prospector.py` (commit
`ff8ac55`). Worth a broader sweep (future fire, not this one — scope discipline): grep for
other daily/periodic producers writing to author inboxes with a similar
state-file-tracks-what-was-emitted pattern (kitchen seeder, self-audit gap-finder, swarm
consult routers) and check whether each has an equivalent self-healing check against its own
downstream artifact, or is exposed to the same silent-flood-on-state-loss class.

## Evidence

`analysis/prospector/state.json` (`fires_total: 4` — itself a symptom, the real fire count
since 2026-06-16 is far higher, left unfixed as cosmetic/non-load-bearing), commit `41889a0`
(the original state-loss event), commit `ff8ac55` (this fire's fix + backfill + backlog
dedup), `strategy/candidates/_chef-inbox/` (37 `.DONE`-renamed duplicate files with pointer
notes to their surviving first-surfaced copy).
