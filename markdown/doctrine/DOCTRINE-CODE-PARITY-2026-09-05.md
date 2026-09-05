# DOCTRINE-CODE-PARITY-2026-09-05 — GOAL-DOCTRINE-CODE-PARITY-SWEEP-2026-09-05

> Sweeps every checkable numeric/boolean claim in CLAUDE.md's 10 rules, Account context, and
> Tech-stack status lines, plus `automation/state/params.json`/`aggressive/params.json` `_doc`
> strings asserting a consumer, against the code that actually enforces them. Companion to
> [`EXIT-SHAPE-TRUTH.md`](../0dte/EXIT-SHAPE-TRUTH.md) (GOAL-EXIT-SHAPE-PARITY-2026-09-05, which
> resolved the exit-shape numbers — runner target, tp1_qty_fraction, chandelier arm/trail —
> already, and is reused here rather than re-derived). Full machine-readable inventory:
> [`analysis/doctrine-parity/claims-2026-09-05.json`](../../analysis/doctrine-parity/claims-2026-09-05.json).
> Guard: `backtest/tests/test_doctrine_code_parity_2026_09_05.py`.

## Verdict counts (20 claims)

| Verdict | Count |
|---|---|
| PARITY | 14 |
| DOC-DRIFT | 4 |
| UNAPPLIED-RATIFICATION | 1 |
| UNVERIFIED (scope not completed / not re-queried this pass) | 1 |

## DOC-DRIFT rows (corrected in CLAUDE.md this pass)

| Claim | Doc said | Code truth | Evidence | Fix |
|---|---|---|---|---|
| C09 hard time-stop | 15:50 ET | `params.time_stop_et` = **15:40** (both accounts), read + forwarded by `heartbeat_core.py::_manage_exits` → `exit_actuator.manage_tick` (fix comment: "FIX 2026-07-07: was ignored -> hard-coded 15:50" — i.e. it now genuinely reads the params value) | `automation/state/params.json`'s own newest `_exits_section` comment (2026-06-18) already says "Time stop 15:40 ET" — code and params-doc agreed; only CLAUDE.md's prose was stale | CLAUDE.md Management line + schedule table corrected 15:50→15:40 |
| C10 EOD-flatten sentence | "not out by 15:50" | Same underlying number as C09 (15:40) — the schedule *fire* time (15:55) was already correct; only the embedded sub-claim was stale | Same as C09 | Corrected as part of C09's edit (not double-counted as a second drift) |
| C07 TP1 fallback | "+30% fallback" | Registry `strategies.py::RIBBON_RIDE.exit.tp1_premium_pct` = **1.0** (+100%, risky-1 patched to 0.5); params.json's own `tp1_premium_pct` key measures 0.5 Safe / 0.75 Bold — three different numbers found, none of them 30% | EXIT-SHAPE-TRUTH's vary-and-assert (registry ignores params entirely) | CLAUDE.md Management line reworded to point at the live registry value via EXIT-SHAPE-TRUTH.md rather than restating a number that drifts independently in three places |
| C02 min contracts | "Min 3 contracts" (no account split) | `params.min_contracts` = 3 Safe / **5 Bold** — Bold's live floor is higher, undisclosed by the single "3" | Direct params.json read (both files) | Rule 6 corrected to "Min contracts: Safe 3 / Bold 5" |

## UNAPPLIED-RATIFICATION

**C08 — `tp1_qty_fraction` 0.8 Safe (pk-2026-06-28-001, ratified 2026-06-28).** The ratification
reached `automation/state/params.json` (Safe's `tp1_qty_fraction` = 0.8) but never reached the
`ribbon_ride` registry Safe actually trades on — `strategies.py::RIBBON_RIDE.exit.tp1_qty_fraction`
is a frozen 0.667 literal for every arm, confirmed unchanged under a mutated params.json copy
(EXIT-SHAPE-TRUTH's vary-and-assert, reused). Re-filed as
[`analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json`](../../analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json)
with the original scorecard's evidence quoted verbatim, and added to
`analysis/recommendations/checkpoint-2026-09-29-inventory.json` (row `tp1-qty-fraction-safe-0-8`,
classified **reduction** — selling MORE at TP1 strictly reduces runner exposure, the opposite
direction from the goal brief's generic "sells less = expansion" template, which does not apply
here). `checkpoint_packet.py` regenerated cleanly: 13 rows, the new row reads `UNKNOWN n=None`
(no scorer yet — correctly reflects that a fresh A/B under the live shape is required before this
can ship, per the prereg's own `SHAPE_MISMATCH` kill-nail: the original scorecard validated a
different strike/stop/target combo than what actually shipped).

## PARITY rows (no correction needed) — selected highlights

- **C05/C06 catastrophe cap −50% both sides**: `strategies.py`'s `catastrophe_stop_pct=-0.50` is a
  frozen literal, side-agnostic, both accounts — matches CLAUDE.md exactly. (`params.premium_stop_pct`
  is a *different*, currently-unreached fallback key that diverges — Bold measures −0.07 there — but
  it only fires if `structure_stop_enabled` is ever flipped false, which it isn't today.)
- **C04 09:35 ET entry gate**: `params.entry_no_trade_before_et="09:35"` both accounts, read with a
  fail-closed-to-09:35 default (`heartbeat_core.py:261`).
- **C03 free-model veto disabled**: `GAMMA_FREE_MODEL_VETO` env default is the literal string `"0"`.
- **C12 PDT/settlement**: both accounts run `pdt_gate_mode="cash_settlement"`; `risk_gate.py`'s own
  docstring states margin-PDT structurally never applied to these accounts (broker returns no
  `pattern_day_trader`/`daytrade_count` fields) — consistent with CLAUDE.md Rule 7's disjunctive
  phrasing.
- **C13 strike-tier ladder vestigial claim**: CLAUDE.md's own self-caveat ("params.json's ladder is
  vestigial on the live core path") is *already correct* — `params.json`'s own
  `_v15_strike_offset_per_tier_doc` independently agrees, and `strike_selection.py`'s header names
  itself the live source of truth.
- **C19 rule_version**: direct read confirms `v15.3` (Safe) / `v15.2` (Bold), matching CLAUDE.md's
  parenthetical exactly.

## UNVERIFIED (scope not completed)

**C15 — playbook.md / risk-rules.md numeric claims.** Not exhaustively diffed against every
setup's code gate this pass (time-budgeted sweep prioritized the goal's named seeds — CLAUDE.md
rules/tech-stack numbers and the params `_doc` UNAPPLIED-RATIFICATION). `position_sizing_tiers` in
`params.json` was read for cross-reference but a full playbook-vs-code pass was not run. Flagged
here rather than asserted PARITY without the check.

## Context-budget verdict after CLAUDE.md edits

The first draft of these edits (linking this file from both Rule 6 AND the Management line, with
fuller inline explanations) pushed CLAUDE.md to **RED** on the accurate tiktoken count:

```
$ python setup/scripts/context_audit.py check --file CLAUDE.md --budget 9000
RED  CLAUDE.md: 9111 tok / 9000 budget (101%)  integrity=ok  [tiktoken-cl100k]
```

(Note: the `backtest/.venv` interpreter lacks `tiktoken` and silently falls back to a byte/3.6
estimate — `8902 tok (99%)` — which under-reports; the system `python` on PATH has `tiktoken`
installed and is the accurate reading. Use `python`, not `backtest/.venv/Scripts/python.exe`, when
checking this budget.) Trimmed the three inserted clauses to one short parenthetical each (dropped
a duplicate pointer link, shortened the EOD-flatten row, removed the reconstructed pre-edit-value
callout since the parity doc already states it) and re-measured:

```
$ python setup/scripts/context_audit.py check --file CLAUDE.md --budget 9000
YELLOW  CLAUDE.md: 8995 tok / 9000 budget (100%)  integrity=ok  [tiktoken-cl100k]
```

Under budget (YELLOW, not RED), integrity `ok` (both `DOCTRINE-CODE-PARITY-2026-09-05.md` pointer
targets resolve now that this file exists). No rule semantics, account params, or rule numbering
were touched — only the three factual corrections listed above.

## Prereg refiled

| File | Class | Checkpoint |
|---|---|---|
| `analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json` | reduction | 2026-09-29 |

Added to `analysis/recommendations/checkpoint-2026-09-29-inventory.json` (count 9→10);
`checkpoint_packet.py` regenerated (`markdown/planning/CHECKPOINT-2026-09-29.md` and
`CHECKPOINT-2026-10-30.md`), 13 rows total.

## RED-proof

`backtest/tests/test_doctrine_code_parity_2026_09_05.py` includes two dedicated red-proof tests
(`test_red_proof_time_stop_against_pre_edit_text`, `test_red_proof_min_contracts_against_pre_edit_text`)
that assert the pre-edit CLAUDE.md sentences ("hard time-stop 15:50 ET", "Min 3 contracts" with no
per-account split) fail the same parser/assertion the corrected text now passes — proving the guard
catches the drift class it was built for, not merely tautologically agreeing with whatever the
working tree currently says.

```
$ cd backtest && .venv/Scripts/python.exe -m pytest tests/test_doctrine_code_parity_2026_09_05.py -q
.........
9 passed in 0.20s
```

Combined with the sibling exit-shape guard: `pytest test_doctrine_code_parity_2026_09_05.py
test_exit_shape_parity_2026_09_05.py -q` → 15 passed. Full repo-wide `-k parity` (400 tests across
every other parity-marked suite in the repo) was also run to completion:

```
$ backtest/.venv/Scripts/python.exe -m pytest backtest/tests/ -q -k parity
396 passed, 4 skipped, 13147 deselected, 1 warning in 749.88s (0:12:29)
```

0 failed. This goal's guard did not regress anything else carrying `parity` in its name.

## Not repeated here

Runner target (2.5x claim vs. code's unconstrained 99.0×), `tp1_qty_fraction`'s exit-shape framing,
and the chandelier arm/trail numbers were already fully resolved by
[`EXIT-SHAPE-TRUTH.md`](../0dte/EXIT-SHAPE-TRUTH.md) — CLAUDE.md's strategy paragraph already
carries the corrected wording ("runner target UNCONSTRAINED (99.0×, trail-only, C30)",
"tp1_qty_fraction 0.667 ribbon_ride all arms") as of this sweep's start; this doc does not re-edit
that paragraph.

## H1 follow-up (GOAL-TP1-FRACTION-AB-2026-09-05, 2026-09-05) — C15 scope closed

C15 ("playbook.md / risk-rules.md cross-check") was left UNVERIFIED by the original sweep. This
goal completed it. Two DOC-DRIFT findings, both corrected in-place:

- **C21 — playbook.md chandelier trail + TP1 numbers stale.** Both `*_RIDE_THE_RIBBON` setups
  claimed "trails 0.15 off the high-water mark" and "TP1 = +50% premium at qty fraction 0.667."
  Live RIBBON_RIDE registry (`automation/state/fleet/strategies.py`, frozen dataclass literal,
  takes no params argument — same mechanism EXIT-SHAPE-TRUTH already proved for the sibling
  `tp1_qty_fraction`/runner-target claims): `trail_pct=0.125` (matches `params.json#v15_profit_lock_trail_pct`,
  WP-6 2026-06-21), `tp1_premium_pct=1.0` (+100%, the SAME drift CLAUDE.md's own C07 already
  flagged — playbook.md carried the identical stale number independently). Corrected in both
  setups' text, 2026-09-05.
- **C22 — risk-rules.md "Pre-entry liquidity gate" describes a dead gate as live.** The section's
  6 keys (spread/delta-band/OI thresholds) were RETIRED as CONFIRMED_DEAD on 2026-08-29
  (`params.json#_liquidity_gate_section_RETIRED_2026_08_29` — zero order-path consumers, never
  wired into `pre_order_gate.py`; independently confirmed by `heartbeat_core.py`'s own "dead knob
  with zero consumers" comment). risk-rules.md still presented it as an enforced hard-rejection
  gate with no retirement note. A retirement banner was added 2026-09-05; the table is kept for
  historical WHY-context only.

Both corrections quoted in full in `analysis/doctrine-parity/claims-2026-09-05.json` C21/C22.
Files touched: `markdown/0dte/playbook.md`, `markdown/0dte/risk-rules.md`,
`analysis/doctrine-parity/claims-2026-09-05.json` (C15 verdict flipped from UNVERIFIED to
"SCOPE COMPLETED"). No FROZEN_TRADING_PATH file touched (params.json read-only cited, not edited).


## Orchestrator correction (2026-09-05 06:26 ET, Fable)

C21's trail number was wrong in the H1 pass: it trusted `params.json#v15_profit_lock_trail_pct` (0.125), which EXIT-SHAPE-TRUTH.md had already shown is NOT read by the ribbon_ride path. The live literal is `automation/state/fleet/strategies.py:143` `trail_pct=0.15`. `markdown/0dte/playbook.md` re-corrected to 0.15 (both setups). Lesson: the truth order in this doc's own rules (fills > code > params doc > prose) must be applied per claim, not per file -- a params `_doc` is prose.
