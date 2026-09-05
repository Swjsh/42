# Package: tickers-theta-budget-cadence

**Packet row:** `tickers-theta-budget-cadence` in `analysis/recommendations/checkpoint-2026-09-29-inventory.json`.
**Verdict at authoring time:** <PASTE from `python setup/scripts/checkpoint_packet.py` stdout>
**Prereg:** <path> -- status <status>.

## What this retires / changes

<Name every organ this package touches: scheduled task(s), installer script(s), the
ledger writer, the ledger path, the guard test that already exists, cockpit tiles or
readers left alone, and confirm which params keys (if any) are touched -- FROZEN
params-key edits must be called out explicitly and only applied 2026-09-29 with
GAMMA_FREEZE_OVERRIDE per the goal's OPERATING RULES.>

| Organ | Path |
|---|---|
| Scheduled task | `TODO` |
| Installer | `TODO` |
| Ledger writer | `TODO` |
| Ledger | `TODO` |
| Existing guard | `TODO` |
| Params keys touched | `TODO -- NONE, or name them + note FREEZE gating` |

## The patch

`change.patch` (from `git diff` against HEAD, captured then reverted -- HEAD's working
tree is unchanged by authoring this package):

<Describe each file the patch touches and why.>

## Revert

```
git revert <sha-of-the-applying-commit>
<any installer re-run needed to restore a scheduled task>
```

## RED-proof (quote verbatim, this session)

**Pre-patch:**
```
TODO -- paste guard_test.py output run against HEAD (before the patch)
```

**Post-patch (applied to a scratch worktree or the working tree, then reverted before
ending the session -- never left applied):**
```
TODO -- paste guard_test.py output run with the patch applied
```

## Nothing applied

`change.patch` was captured via `git diff`, then the working-tree edits were reverted
with `git checkout -- <files>` before this README was finalized. Verify:
`git status --porcelain -- <files>` is empty.
