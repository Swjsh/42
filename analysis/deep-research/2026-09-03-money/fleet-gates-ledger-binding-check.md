# G2 LEDGER TRUTH TABLE — does a safe-only gate refusal actually stop the fleet arms?

Stamp: 2026-09-03, ~14:20-15:10 ET (market hours), read-only. Answers queue item
G2-LEDGER-BINDING-CHECK, extending `veto-scope-safe-3.md`'s single-mechanism trace into a
full empirical join across every gate and every active fleet arm, two windows
(2026-08-06..today, and the 2026-09-01..today sub-window), both directions. Script:
`backtest/tools/fleetgates_ledger-binding-check.py` (read-only, <5s runtime). Full per-gate
JSON: `analysis/deep-research/2026-09-03-money/fleet-gates-ledger-binding-check.json`.

## Verdict up front

**SUPPORTED, with a size correction.** `veto-scope-safe-3.md` proved the mechanism (bold's
passing perception silently overrides safe's block in `sig["strategies"]`) and gave 2 live
example ticks. This ledger join across the full window shows the leak is **real but partial,
not total**: fleet arms ride through a safe-only gate refusal on roughly **6-15% of the ticks**
where that specific gate fired and bold's perception passed (aggregate across all safe-side
gates: safe-3 8.3%, risky-1 11.3%, risky-3 6.0-8.7% of 133 qualifying ticks) — not 0% (fully
binding, which the params.json GATE_KEYS framing implies) and not 100% (fully inert). The
**mirror direction is NOT symmetric**: when bold is the one gated and safe's perception passes,
fleet arms ride through far more often (aggregate safe-3 8.0%, risky-1 21.9%, risky-3 15.0-18.7%
of 187 ticks, one gate as high as 53%). This lines up with, and gives ledger evidence for, the
directional mechanism `veto-scope-safe-3.md` §1c already traced in code: `sig["strategies"]`
**defaults to safe's own block** and only swaps to bold's block when bold's own perception
separately passes — so a bold-gated/safe-entered tick feeds fleet arms safe's undiluted, default
signal, while a safe-gated/bold-entered tick only reaches fleet arms via the override branch.

Two gates in the tables below (`SKIP_LATE_ENTRY`, and the underpowered `SKIP_STALE_TRIGGER`) are
**not safe-cohort gates at all** — they fire on both accounts simultaneously (verified below) —
and should not be read as evidence about `params.json` GATE_KEYS specifically.

---

## Method

- Source: `automation/state/core-decisions.jsonl` (37,951 rows total; 15,994 rows since
  2026-08-06, of which 15,990 are `armed:true` and every one of those carries a non-null
  `core_tick_id`). Joined `account=safe` and `account=bold` rows on `core_tick_id` — 7,998
  distinct ticks since 2026-08-06 have both rows present (100% pairing, no orphans).
- **"Gated"** = that account's own `action` field starts with `SKIP_` (the literal instruction
  in the question). The `triggers` field the question also names ("HOLD with a non-empty
  trigger set") is **empty on every single row since 2026-08-06** (checked: 0 of 7,999 safe
  rows) — it is a legacy field superseded by `bull_triggers_raw`/`bear_triggers_raw`/
  `shadow_triggers_fired`, so that clause contributes zero additional rows; the gated-set below
  is `action` `SKIP_*` only.
- **"Read ENTER_BULL/ENTER_BEAR"** = the *other* account's `verdict` field (not `action`) is
  `ENTER_BULL`/`ENTER_BEAR`. This matches `veto-scope-safe-3.md`'s own finding that
  `_bold_passed_blocks_from_row` keys off `verdict`, not the execution-time `action` (bold can
  read `verdict:ENTER_BULL` with `action:SKIP_MIN_PREMIUM_FLOOR` and still counts as "passed" for
  the shared-signal override — confirmed there against the live 11:21/11:22 ticks).
- **"Which gate"** = the gated account's own `action` string, verbatim (e.g.
  `SKIP_STRUCTURE_VETO`, `SKIP_BULL_1100_1200`). Four of the gates below map by name directly to
  the `params.json` GATE_KEYS this queue item cares about: `SKIP_STRUCTURE_VETO`
  (`structure_veto_enabled`), `SKIP_BULL_1100_1200` (`block_bull_1100_1200`),
  `SKIP_CONF_LVL_REC_AFTERNOON` (`block_conf_lvl_rec_afternoon`),
  `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` (`require_bearish_fill_bar`). The rest
  (`SKIP_DOJI_ENTRY_BAR`, `SKIP_LATE_ENTRY`, `SKIP_MIN_PREMIUM_FLOOR`, `SKIP_STALE_TRIGGER`,
  `SKIP_STALE_SIGHT`) were not independently traced to a specific `params.json` key this session
  — reported by action name only, not claimed as cohort gates.
- **"What did the fleet arm do"** = joined each of `safe-3`, `risky-1`, `risky-3`'s own
  `automation/state/fleet/<arm>/decisions.jsonl` on `core_tick_id`; "entered" = that arm's row
  `action` in `{ENTER_BULL, ENTER_BEAR, PLACED}`. `safe-2`/`bold-2` have no `decisions.jsonl` —
  they run `execution:mcp_heartbeat`, i.e. they ARE the `safe`/`bold` core rows directly, not a
  separate join target. `safe-1` retired 2026-07-10 (before the window). **`risky-3` retired
  ~2026-08-28** (last ledger row `2026-08-28T15:53:06`) — it has **zero logged rows for the
  entire 2026-09-01+ sub-window**; its Sept "0 entries" below is a coverage artifact of
  retirement, not evidence the gate binds it.
- **Absence handling**: contrary to the instruction's caveat, the fleet ledgers log a row for
  essentially every core tick, not just actioned ones (safe-3/risky-1: 12,590 rows/8,953 distinct
  ticks logged vs 7,998 core ticks in-window; risky-3 similarly until its retirement date). The
  0-40% "absent" counts per gate below are real small gaps (arm execution didn't run that exact
  minute) plus risky-3's retirement, not a systematic actioned-only ledger. Per instructions,
  absent = treated as no-entry.
- `n_ticks >= 10` required to call a gate's binding/non-binding finding safe; below that, flagged
  UNDERPOWERED and reported for completeness only.

---

## Table A — safe gated (SKIP_*), bold read ENTER_BULL/ENTER_BEAR — since 2026-08-06

| safe gate (n ticks) | safe-3 entries/share | risky-1 entries/share | risky-3 entries/share (of logged) | call |
|---|---|---|---|---|
| **SKIP_STRUCTURE_VETO** (54) | 3 / 5.6% | 5 / 9.3% | 1 / 1.9% (3.0% of 33 logged) | **BINDING (mostly)** — 87-98% of ticks the veto held; a real but small leak |
| **SKIP_BULL_1100_1200** (53) | 8 / 15.1% | 8 / 15.1% | 7 / 13.2% (21.2% of 33 logged) | **BINDING (mostly)**, leakier than structure-veto — ~1 in 7 ticks rides through |
| SKIP_DOJI_ENTRY_BAR (9) | 0 / 0% | 2 / 22.2% | 0 / 0% | UNDERPOWERED (n<10) |
| **SKIP_LATE_ENTRY** (16) | 0 / 0% | 0 / 0% | 0 / 0% | BINDING, but **not a safe-cohort gate** — fires on both accounts together (see below), so 0% fleet-entry reflects nothing being tradeable that tick system-wide, not this gate specifically holding fleet back |
| SKIP_STALE_SIGHT (1) | 0 / 0% | 0 / 0% | 0 / 0% | UNDERPOWERED (n<10) |

**Aggregate, any safe gate (n=133 ticks, 12 distinct dates):** safe-3 11 entries (8.3%),
risky-1 15 entries (11.3%), risky-3 8 entries (6.0% raw / 8.7% of 92 logged). Top-3 dates
(2026-09-03:30, 2026-08-17:21, 2026-08-21:20) = 53.4% concentration — **drop-best-day check**
(remove 2026-09-03, today's partial session): n=103, shares move to safe-3 8.7%, risky-1 12.6%,
risky-3 7.8% — **the finding is robust, not a single-day artifact.**

Concrete `core_tick_id`s, safe gated + bold ENTER + fleet-arm actually entered (>=3 each, per
instructions):
- `SKIP_STRUCTURE_VETO`: `2026-08-07T12:36:02.451616` (safe-3+risky-1), `2026-08-21T13:34:02.490082`
  (safe-3+risky-1), `2026-09-03T11:21:02.576928` (safe-3+risky-1 — the exact tick
  `veto-scope-safe-3.md` §2c already documents), `2026-08-07T12:39:02.421646` (risky-3 only).
- `SKIP_BULL_1100_1200`: `2026-08-13T11:41:02.990155`, `2026-08-19T11:49:02.561586`,
  `2026-08-21T11:06:02.592949`, `2026-08-21T11:36:02.613080` (all four: safe-3+risky-1 both
  entered).

Named-winning-days disclosure: only 14 of 133 Table-A ticks (10.5%) fall on the four named
winning days (08-06/08-13/08-27/08-28) — this leak is not concentrated on those days.

### Table A — 2026-09-01..today sub-window

| safe gate (n ticks) | safe-3 | risky-1 | risky-3 | call |
|---|---|---|---|---|
| SKIP_BULL_1100_1200 (20) | 3 / 15.0% | 3 / 15.0% | 0 / 0% (0 logged — retired) | BINDING(mostly), consistent with full-window rate |
| SKIP_STRUCTURE_VETO (20) | 1 / 5.0% | 1 / 5.0% | 0 / 0% (0 logged — retired) | BINDING(mostly), consistent with full-window rate |

Sept sample tick where all logged arms rode through: `2026-09-03T11:21:02.576928`
(`SKIP_STRUCTURE_VETO`, safe-3+risky-1 both entered — the same tick `veto-scope-safe-3.md`
quoted). `risky-3` cannot be evaluated in Sept — retired.

---

## Table B (mirror) — bold gated (SKIP_*), safe read ENTER_BULL/ENTER_BEAR — since 2026-08-06

| bold gate (n ticks) | safe-3 entries/share | risky-1 entries/share | risky-3 entries/share (of logged) | call |
|---|---|---|---|---|
| **SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY** (87) | 0 / 0% | 9 / 10.3% | 4 / 4.6% (5.7% of 70 logged) | BINDING for safe-3, LEAKY for risky-1/risky-3 |
| SKIP_STALE_TRIGGER (5) | 4 / 80% | 4 / 80% | 4 / 80% | UNDERPOWERED (n<10) — but **not a safe/bold-cohort gate**: fires on both accounts together 120/120 times across the whole window (see below) |
| **SKIP_CONF_LVL_REC_AFTERNOON** (45) | 7 / 15.6% | **24 / 53.3%** | 18 / 40.0% (47.4% of 38 logged) | **NON-BINDING for risky-1/risky-3** — this bold-side afternoon gate barely restrains them at all when safe supplied the entering signal |
| SKIP_LATE_ENTRY (16) | 0 / 0% | 0 / 0% | 0 / 0% | same shared-gate caveat as Table A |
| **SKIP_MIN_PREMIUM_FLOOR** (32) | 4 / 12.5% | 4 / 12.5% | 2 / 6.25% (10.5% of 19 logged) | BINDING(mostly) |
| SKIP_STALE_SIGHT (2) | 0 / 0% | 0 / 0% | 0 / 0% | UNDERPOWERED (n<10) |

**Aggregate, any bold gate (n=187 ticks, 17 distinct dates):** safe-3 15 entries (8.0%),
risky-1 **41 entries (21.9%)**, risky-3 28 entries (15.0% raw / 18.7% of 150 logged). Top-3 dates
(2026-08-20:32, 2026-08-12:22, 2026-08-26:20) = 39.6% concentration — **drop-best-day check**
(remove 2026-08-20): n=155, shares move to safe-3 9.7%, risky-1 **26.5%**, risky-3 16.8% — the
leak is not a single-day artifact and is if anything *understated* by including the biggest day.

Concrete `core_tick_id`s, bold gated + safe ENTER + fleet-arm entered (>=3 each):
- `SKIP_CONF_LVL_REC_AFTERNOON` (the leakiest row): `2026-08-12T14:16:02.973209` (safe-3+risky-1),
  `2026-08-13T15:11:02.929340` (risky-1), `2026-08-26T14:56:02.621899` (safe-3+risky-3),
  `2026-08-26T15:51:02.640393` (safe-3).
- `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`: `2026-08-06T10:31:02.400016` (risky-1+risky-3),
  `2026-08-11T11:51:02.965227` (risky-1), `2026-08-12T11:26:03.024016` (risky-1+risky-3).

### Table B — 2026-09-01..today sub-window

| bold gate (n ticks) | safe-3 | risky-1 | risky-3 | call |
|---|---|---|---|---|
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY (10) | 0 / 0% | 0 / 0% | 0 / 0% (retired) | UNDERPOWERED |
| SKIP_MIN_PREMIUM_FLOOR (13) | 2 / 15.4% | 2 / 15.4% | 0 (retired) | UNDERPOWERED but directionally matches full-window |
| SKIP_CONF_LVL_REC_AFTERNOON (5) | 1 / 20% | 1 / 20% | 0 (retired) | UNDERPOWERED |

No Sept-only bold-gate row reaches n>=10 — the full-window numbers above are the only powered
read for Table B.

---

## Is the sourcing symmetric? — NO

Answering the question's second half directly: fleet-arm bleed-through is **higher in the mirror
direction** (bold gated / safe entered) than in the primary direction (safe gated / bold
entered), for every arm, in aggregate and on the single richest comparable gate pair:

| | Table A (safe gated) aggregate | Table B (bold gated) aggregate |
|---|---|---|
| safe-3 | 8.3% (n=133) | 8.0% (n=187) — roughly flat |
| risky-1 | 11.3% (n=133) | **21.9%** (n=187) — ~2x |
| risky-3 | 6.0-8.7% (n=133, retirement-truncated) | 15.0-18.7% (n=187) — ~2x |

This is consistent with — though not independently re-derived beyond — the mechanism
`veto-scope-safe-3.md` §1c already traced in `build_shared_signal.py:802-820`:
`sig["strategies"]` **defaults to safe's own (bear, bull) block** and only swaps to bold's block
when bold's own perception separately passes (`_bold_passed_blocks_from_row`, keyed on verdict).
So a Table-B tick (bold gated, safe entered) feeds every fleet arm safe's own, undiluted,
default-path signal; a Table-A tick (safe gated, bold entered) only reaches fleet arms via the
override branch. The higher risky-1/risky-3 share in Table B (both effectively ungated on the
min-triggers axis — risky-1 is `full_send`) is the expected shape if the default (non-override)
path passes a broader/cleaner set of ticks through to `_plan_from_strategies` than the override
path does. **This causal attribution is INFERENCE, not re-verified against
`_plan_from_strategies`'s internals this session** — the numeric asymmetry itself is FACT,
quoted directly from the two ledgers.

---

## Symmetric (non-cohort) gate caveat — verified

Two gate names appear in both tables above and are **not safe-only or bold-only cohort gates**:

- `SKIP_LATE_ENTRY`: checked directly — the 16 ticks in each table are ticks where **both**
  `safe` and `bold` core rows independently carry `action:"SKIP_LATE_ENTRY"` at the same
  `core_tick_id` (verified on `2026-08-17T15:02:02.438566`: `safe` row =
  `{"action":"SKIP_LATE_ENTRY","verdict":"ENTER_BEAR"}`, `bold` row = byte-identical). Across the
  whole window, 16 of the 52 ticks where *either* account hits this action are ticks where
  *both* do — exactly the 16 that qualify for Table A/B (both need the other side's verdict to
  be ENTER, and a shared time-cutoff plus independently-scored verdict co-occurring is what
  produces that). This is a session-clock cutoff common to both accounts, not a `params.json`
  safe-cohort key — the 0% fleet-entry finding says nothing tradeable existed that tick
  system-wide.
- `SKIP_STALE_TRIGGER`: checked directly — 120 of 120 window-wide occurrences have both accounts
  hitting it together (fully symmetric, both==either). Same read: shared data-freshness gate, not
  a cohort gate. Its n=5 appearance in Table B is UNDERPOWERED regardless.

`SKIP_MIN_PREMIUM_FLOOR` was checked and found **never** symmetric (0 of 50 window-wide
occurrences hit both accounts together) — confirming it genuinely differs per account (different
strike/premium at each account's own sizing), consistent with it being a real per-account
outcome rather than a shared session gate.

---

## What this adds to / corrects in `veto-scope-safe-3.md`

- Confirms the mechanism direction and reproduces its exact example tick
  (`2026-09-03T11:21:02.576928`, `SKIP_STRUCTURE_VETO`, safe-3+risky-1 both `ENTER_BULL`) via an
  independent full-ledger join, not just the two hand-picked ticks that document quoted.
- **Corrects the implicit "fully inert" framing**: `SKIP_STRUCTURE_VETO` and
  `SKIP_BULL_1100_1200` are **mostly still binding for fleet arms** (held rate — 1 minus the
  per-arm entry share above — ranges 79-98% across the two gates and three arms, worst case
  risky-3 on `SKIP_BULL_1100_1200` at 78.8% of its own logged ticks) even though the mechanism
  that could bypass it exists — the doc's code-trace is right that the block CAN leak through,
  but empirically it does so a minority of the time for these two gates specifically. `SKIP_CONF_LVL_REC_AFTERNOON` (Table B) is the one gate in this dataset
  that is genuinely **non-binding** for risky-1 (53% bleed-through) — that is the strongest single
  finding here and the one most worth flagging if `SKIP_CONF_LVL_REC_AFTERNOON` (a.k.a.
  `block_conf_lvl_rec_afternoon`) is ever load-bearing for a fleet-arm-scoped conclusion.
- New finding not in the prior doc: the leak is **directionally asymmetric** (worse when bold is
  the gated side), a straightforward but previously unstated consequence of the same
  default-to-safe / override-to-bold construction.

## What this does NOT resolve

Does not re-derive `_plan_from_strategies`'s internal gate application (why risky-1, nominally
ungated on min_triggers, still only enters 11-22% of qualifying ticks rather than ~100% — other
filters: day-trade cap, duplicate-claim, flat-check, settlement cap, premium floor at risky-1's
own strike almost certainly explain most of the gap, not independently attributed here). Does not
score whether the leak is P&L-positive or -negative for the arms that ride it — that is a
separate expectancy question, out of scope for this ledger-truth-table task.
