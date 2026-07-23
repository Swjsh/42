# task_scorer's single-line status read silently defaulted a CLOSED item to READY

**Date:** 2026-07-22 (conductor, AFTERHOURS)

**Class:** C7 (audit outputs, not exit codes — a ranking tool's own output must be
verified, not trusted) + C14 (dead/translated-but-unapplied knob sibling: here it's
not a dead knob but a mis-scoped READ).

## Symptom

`setup/scripts/task_scorer.py --top` repeatedly surfaced already-CLOSED HIGH-priority
`queue.md` items as the #1 ready pick across multiple separate conductor fires
(`RANGE-SCALP-REGIME-STRATEGY`, `RIBBON-LAG-PRICE-STRUCTURE-TRIGGER`,
`POSITION-MONITOR-1MIN` in the 2026-07-18 session; `PULLBACK-HOLD-BULL-TRIGGER`
today, 2026-07-22, closed ~18:42 ET but still ranked `ready:true` at 19:42 ET). Each
prior recurrence was individually re-triaged (a `staleness_advisory()` stderr nudge
was even graduated 2026-07-18 telling the operator to "trace it against current
reality before executing") but the advisory only tells the operator to double-check
manually — it never fixed the actual mechanism producing the false-ready state.

## Root cause

`queue.md` items are written append-only (OP-22): many real items are long
multi-paragraph entries whose `- [ ]` checkbox line ends BARE at `::` (nothing
after it), and the item's actual closing `status:CLOSED-...` verdict is appended
many PHYSICAL LINES below, inside later continuation prose (confirmed exact case:
`PULLBACK-HOLD-BULL-TRIGGER`'s checkbox is line 14, its `status:CLOSED-LANE-B-
NO-CELL-SHIPS` is on line 44 — 30 lines and several paragraphs later).
`task_scorer.py`'s parser was line-based: it matched `ITEM_RE` against ONE line at
a time and extracted `status` from that single line's `rest` only. For these
multi-paragraph items, `rest` was empty (`""`), and the module's own ready-rule
treats an EMPTY status as ready (`status_ok = status in READY_STATUSES or status
== ""`) — a deliberate, correct behavior for genuinely status-less items (see
`test_no_status_item_is_ready`), but a silent false-positive for a closed item
whose status field simply wasn't on the same line as its checkbox.

## Fix

`_extract_field_last()` — scans an item's WHOLE block (checkbox line + every
continuation line up to the next item/header, via new `_item_blocks()`), bounding
each `::`-delimited field-value to its OWN LINE (so unrelated `::`-free trailing
prose can't bleed into the value — a real second-order bug caught and fixed via
its own guard test, `test_multiline_open_status_not_corrupted_by_trailing_
blockquote`), and returns the LAST matching `status:`/no — only `status` (kept
narrow; `depends` intentionally left checkbox-line-only per the existing
`TASK-SCORER-STATUS-VOCAB-GAP` item's own "don't rush this with a careless regex
change" discipline). Applied to both `parse_queue`'s per-item status read AND
`_open_item_ids`'s dependency-resolution status read (the same root cause, second
consumer).

## Guard

`backtest/tests/test_task_scorer_multiline_status.py` (7 tests) — pins: closed
multi-line item excluded from ready; visible under `--all` as `ready:false`; a
genuinely-open multi-line item is NOT corrupted by unrelated trailing blockquote
prose; a dependent naming a closed-but-unchecked item is unblocked;
`_extract_field_last` correctly bounds a value to its own line and takes the LAST
occurrence across a block; single-line items are unaffected (last == only, zero
regression risk for the common case). RED-proofed live via `git stash` — 6/7 new
tests failed against the pre-fix code with the exact expected `AttributeError`/
value-mismatch, `git stash pop` restored cleanly, re-verified 52/52 green across
the full `task_scorer` suite.

## Generalization

Any tool that parses this repo's append-only, multi-paragraph `queue.md`/journal
convention on a PER-LINE basis (not per-item-block) is exposed to the same class
of bug: a field's true, most-current value can live several lines below where the
naive parser looks. `task_scorer.py` is the second tool in this repo's history to
hit this (the first was the 2026-07-01 `depends:` annotation-parenthetical bug,
already fixed). Any future queue/journal parser should default to block-scoped
field reads, not line-scoped ones.
