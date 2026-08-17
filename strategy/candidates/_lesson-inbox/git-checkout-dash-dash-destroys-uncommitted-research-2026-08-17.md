# Foot-gun: `git checkout -- <file>` silently destroys uncommitted content on append-only research files

**Date:** 2026-08-17, conductor AFTERHOURS fire
**Severity:** MEDIUM (self-corrected same fire, zero permanent loss, but was one keystroke from real data loss)

## What happened

While editing `analysis/self-audit/new-gaps-flagged.md` (an append-only, DONE-marker-annotated
research log the self-audit swarm writes to independently of any conductor commit), an `Edit`
tool call failed to match `old_string` because the file mixes CRLF line endings with several
Unicode punctuation characters (U+2011 non-breaking hyphen, U+2013 en-dash, U+202F narrow
no-break space) that a hand-typed `old_string` cannot reliably reproduce byte-for-byte.

The recovery instinct was: run `git checkout -- analysis/self-audit/new-gaps-flagged.md` to get
back to a "clean" state before retrying with a Python byte-patch script. **This was wrong.**
`git checkout --` restores the file to `HEAD`, not to "the state before my last edit attempt" --
and this file had ~17 lines of genuine, never-committed self-audit swarm output (the 2026-08-16
and 2026-08-17 gap batches) sitting in the working tree, produced by a process that runs
independently of conductor commits. The checkout wiped that content instantly and silently (exit
0, no warning -- git has no way to know the discarded content was never staged anywhere else).

## Why it wasn't a real loss this time

Pure luck: the exact content that was destroyed had been read verbatim into this session's own
transcript two tool-calls earlier (`Read` with `offset=850 limit=106`), so it could be
reconstructed byte-for-byte from the conversation history. Had that Read call used a narrower
offset, or had this been a *second* recovery attempt, the content would have been permanently
gone -- no other copy exists (not staged, not committed, no OneDrive version-history tool
available to this agent).

## Root cause

Two compounding gaps:
1. **No pre-flight check before a destructive git op.** `git checkout -- <path>` is listed as a
   "destructive git command" in the standing git-safety protocol, but the trigger for treating it
   that way was never fired here -- it was reached for as a routine "undo my broken edit" reflex,
   not flagged as needing a `git status`/`git diff` check first to confirm nothing unstaged and
   uncommitted would be lost.
2. **Unicode/CRLF byte mismatches silently break `old_string` matching with no signal about
   WHY.** The `Edit` tool correctly refused the ambiguous replace, but the failure mode looks
   identical to "I mis-copied the string" and "there is invisible content I can't see" -- nothing
   nudges toward "read the raw bytes before touching this file again."

## Fix (recommended, not yet built)

- **Never run `git checkout --`, `git reset --hard`, or `git clean` on ANY path without first
  running `git status --porcelain <path>` and `git diff <path>` in the SAME turn**, and reading
  the diff before deciding it's safe to discard. This should apply even when the intent is
  "revert my own change" -- the file may carry OTHER uncommitted content that predates this
  session's edit.
- When an `Edit` `old_string` match fails on a file with non-ASCII characters, the safe next step
  is a byte-level Python read/patch (as eventually done here), NOT a git revert -- git revert
  should be reserved for "I want to discard MY edit," never used as a generic "start over" button
  on a file whose full working-tree provenance hasn't been checked first.
- Candidate graduation (if this recurs): a `pre-commit`/pytest guard is a poor fit here (this is
  an operator-discipline gap, not a code-shape gap) -- the more durable fix is folding an explicit
  "check `git status`/`git diff` before ANY `git checkout --`/`reset`/`clean` call" line into the
  git-safety section every conductor-family prompt already references, so it's read every fire
  rather than relying on the general safety-protocol prose being recalled under pressure.

## Disposition

Self-corrected within the same fire: reconstructed the destroyed content byte-for-byte from this
session's own transcript, re-verified against `git diff --stat` (57 insertions, 0 deletions vs
HEAD -- confirms nothing else was lost), and committed cleanly (`a242a66b`). No J action needed;
filed here per OP-25 so a re-occurrence graduates to an enforced guard rather than staying a
one-off scare.
