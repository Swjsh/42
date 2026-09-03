# VERIFY — dissect-wave-autopsy (pass 1, skeptic)

**Verdict on the finding: NOT REFUTED.** Every specific number I re-derived independently from
raw ledgers (not the script's scratch copies) matched the report exactly — fills, $/%%
P&L, HWM/MAE ticks, implied-delta ratios, zone widths, config flags, SPY path values, the
population stats it cites, and the doc-string quote. I found one real completeness gap (the
report's own "wave 4 out of scope" flag catches 1 of 3 legs and gives no dollar figure) and one
minor presentational imprecision (structure-veto window description). Neither changes any of the
report's stated conclusions; both are noted below so the next reader isn't misled by the "+$4.00,
roughly breakeven" headline into thinking today is flat.

## Method

Re-read `automation/state/fills-ledger.jsonl`, `automation/state/core-decisions.jsonl`,
`automation/state/fleet/{safe-3,risky-1}/decisions.jsonl`, `automation/state/key-levels.json`,
`automation/state/params.json` / `aggressive/params.json`, and
`analysis/deep-research/2026-09-03-money/entry-location-rows.json` fresh in this session —
independent Python one-offs in scratch, not the report's `dissect_wave_autopsy.py` scratch-copy
pipeline. No broker/market-data API called (same hard constraint). All checks below are
`grep`/`python -c` one-offs against the live files; no automation/state/**, journal/**, or
quote-tape file was written.

## What checked out exactly (FACT confirmed independently)

- **Every fill** (15 buy/sell legs across wave 1–3, 3 more in the unscoped wave 4) — arm,
  symbol, qty, price — matches `fills-ledger.jsonl` byte-for-byte.
- **Every $ and %% P&L figure** in all three wave tables (12 positions) recomputed from raw
  buy/sell fills: exact match, including the wave totals (−$779 / −$266 / +$1,049 / net +$4)
  and every %%-premium and %%-equity figure (recomputed off the task's own start-of-day
  equities: safe-2 $5,653.81, bold-2 $5,593.52, safe-3 $5,639.10, risky-1 $6,149.12).
- **Every HWM/MAE tick** (8 positions, wave 1+2) cross-checked against `exit_pass.best_premium
  /worst_premium` in both `core-decisions.jsonl` (safe/bold) and the fleet `decisions.jsonl`
  files (safe-3/risky-1): exact match on value, timestamp, and minutes-to-HWM.
- **All 8 "implied realized delta" ratios** (wave 1: 2.462×/1.172×/2.769×/2.872×; wave 2:
  0.537×/0.341×/0.317×/0.317×) recomputed from scratch using entry/exit SPY ticks pulled
  independently from `core-decisions.jsonl`: exact match to 3 decimals on all 8.
- **Zone mechanics**: `key-levels.json` confirms 768.00/`INTRADAY_PMH` `zone_width=0.384` and
  769.36/`SHELF_768.56_770.16` `zone_width=0.8` exactly as quoted; the wave-2 stop row
  (`trigger=768.0, last_closed_5m_close=767.96`) is the literal row in `core-decisions.jsonl`
  at 10:36:03/10:36:05 for both safe and bold — the "4-cent raw-level breach, zone edge never
  touched" claim is real, not a rounding artifact.
- **Distance-from-level / zone-width ratios** (0.469 / 0.964 / 1.356) recomputed from the same
  SPY-at-entry and trigger_level values: exact match.
- **safe-2's wave-3 refusal**: `SKIP_BULL_1100_1200` 11:06:03–11:10:04, then
  `SKIP_STRUCTURE_VETO` reason text ("structure-veto: C entry blocked — price structure is
  'downtrend'") — confirmed in `core-decisions.jsonl`, including the exact SPY-price sequence
  quoted (770.73→771.5→772.02→772.11→772.93→772.93).
- **Config confirmation**: `automation/state/params.json:314` = `"structure_veto_enabled":
  true`; `automation/state/aggressive/params.json:52` = `"structure_veto_enabled": false`, doc
  string quote ("over 25,821 ledger rows SKIP_STRUCTURE_VETO fired 116 times for account=safe
  and ZERO times for bold") reproduced verbatim in the live file.
- **`structure_reason` shadow classifier**: bold-2's conviction blob at 11:06:04 reads
  `"structure_reason": "range"`; at 11:27:04 it reads `"downtrend"` — exact match (my first
  pass missed this by reading `conviction.components.structure_reason`; it lives at
  `conviction.structure_reason` top-level — a script bug on my side, not the report's).
- **SPY path values**: 767.78 (10:11–10:15), 769.265 (11:01–11:03), 772.93 (11:31), and the
  "latest known tick 11:49:04 ET SPY=772.58" — all confirmed exactly against a fresh read of
  `core-decisions.jsonl`.
- **Population stats**: `entry-location-rows.json`, BULLISH_RECLAIM_RIDE_THE_RIBBON calls,
  n=113, winners mean range_position 0.824 (n=36), losers mean 0.8431 (n=70) — recomputed
  from the file directly, exact match.
- **08-13/08-27 "blocked-cluster wins" claim**: cross-checked against
  `entry-location.md` (a sibling doc, correctly cited as reused not rebuilt) — confirms
  2026-08-13's day total is $1,748 and flips to a $147 loss under the naive 0.75/0.25 chase
  rule because the blocked trades were mostly winners; 08-27 similarly cut 59%. The report's
  parenthetical is accurately sourced, not fabricated.

## Two things worth flagging (neither refutes the finding)

### 1. The "wave 4 / out of scope" footnote is incomplete, and the day is NOT "roughly breakeven"

The report flags one wave-4 leg (bold-2 5×774C@0.39→0.56, +$85, entered 11:27, closed 11:34) as
"already open... out of scope... flagged only so the +$4.00 three-wave net isn't read as the
session total." That's true but understates by a lot: **two more legs from the SAME wave-4
window are missing from the report entirely** —

| Arm | Symbol | Entry | Exit(s) | $ | Timing |
|---|---|---|---|---:|---|
| safe-3 | 772C | 5×0.74 (11:22:07) | 3×1.63 + 2×1.57 (11:30/11:34) | **+$433** | inside the report's own analyzed window |
| risky-1 | 772C | 5×0.76 (11:22:08) | 3×1.26 + 2×1.58 (11:27/11:34) | **+$314** | inside the report's own analyzed window |

(Both confirmed directly in `fills-ledger.jsonl`, same P&L-recompute method as above: safe-3
buy 5×0.74=$370, sell 3×1.63+2×1.57=$803, net +$433; risky-1 buy 5×0.76=$380, sell
3×1.26+2×1.58=$694, net +$314.)

Including all three wave-4 legs, the **running total through 11:34 ET is +$836**, not +$4 —
the report's own chosen scope boundary (wave 3, "task cutoff 11:19–11:27") lands at almost
exactly the point where three large, all-winning positions were about to close, so the
headline "netted +$4.00... roughly breakeven" is accurate for the report's *self-defined*
three-wave scope but would badly mislead a reader using it as a proxy for "how is today going."
safe-2 was excluded from wave 4 too (still under `SKIP_STRUCTURE_VETO` through 11:35:04 per the
ledger), so this doesn't change the report's structure-veto-cost finding — if anything it
**strengthens** it (see arm-split below).

### 2. "SKIP_STRUCTURE_VETO 11:11:04–11:35:04" reads as continuous; it isn't

The safe account's own tape in that window alternates: `SKIP_STRUCTURE_VETO` at 11:11–11:13,
11:16–11:18, 11:21–11:23, 11:26–11:28, 11:31–11:35, but plain `HOLD — "no setup passed
scoring (neither bear nor bull)"` at 11:14–11:15, 11:19–11:20, 11:24–11:25, 11:29–11:30 (~40%%
of the ticks). The SPY-price sequence the report quotes (770.73/771.5/772.02/772.11/772.93) is
correctly picked from *only* the veto-firing ticks, so the specific numbers are right, but the
prose implies one continuous 24-minute block when it's actually five separate ~3-minute
re-qualify-then-veto episodes. Doesn't change the conclusion (safe-2 was blocked every time the
bull setup *did* re-qualify), and arguably makes the case for a real, repeated cost slightly
stronger, not weaker — but the report should say "intermittently, 5 separate re-qualified
ticks" rather than a single continuous span.

## LENS: winner-killer / concentration

**No live change is proposed** (`change_class: NONE`), so there is nothing to test against
08-06/08-13/08-27/08-28 in the normal sense, and the report says so. I independently checked
whether the one candidate idea in the report (zone-edge-adjusted structure stop, i.e. loosen
the raw-level stop to the level's own zone edge) is even *testable* against those four anchor
days with data on disk: **it is not.** `key-levels.json` is today's live state only —
historical structure-stop rows on 08-13 (2 hits) and 08-27 (1 hit) reference price levels
(775.73, 776.70, 768.29) that no longer have a `zone_width` anywhere in the current
`key-levels.json` (lookup returns `None` for all of them). So the report's own "not tested,
candidate for future work" scoping isn't just caution — it's correct, because the data to test
it against the anchor days doesn't currently exist anywhere in this repo. This should be logged
as a prerequisite for whoever picks up the F3 zone-width-grid instrument the report points to.

**Remove-top-3 concentration test** (done independently, both on the report's own wave 1–3
scope and on the fuller wave 1–4 picture I found above):

| Scope | Full net | Top-3 legs removed | Net w/o top-3 |
|---|---:|---|---:|
| Report's wave 1–3 (12 legs) | **+$4** | safe-3 w3 +$507, risky-1 w3 +$343, risky-1 w1 −$280 | **−$566** |
| Full day through 11:34 (14 legs) | **+$836** | safe-3 w3 +$507, safe-3 w4 +$433, risky-1 w3 +$343 | **−$447** |

Both cuts confirm extreme concentration — 3 of 14 correlated legs on one uptrend swing carry
the entire day. This is the *same* fact the report's own synthesis section already states in
different words ("wave 3's real gains almost exactly offsetting wave 1+2's decay/stop losses")
— running the explicit top-3 test doesn't surface anything the report was hiding, it just makes
the magnitude concrete, and the fuller wave-4-inclusive version makes it a bit more dramatic. It
does NOT change the report's own explicit disclaimer that n=3 waves is not a sample.

**Split by arm** (report's wave 1–3 scope, then extended through wave 4):

| Arm | Wave 1–3 net | Wave 1–4 net | Note |
|---|---:|---:|---|
| safe-2 | **−$210** | **−$210** | worst performer — ate every loss, got zero wins because it was gated out of both wave 3 AND wave 4 |
| bold-2 | +$44 | +$129 | |
| safe-3 | +$172 | +$605 | |
| risky-1 | −$2 | +$312 | |

This split independently **confirms and sharpens** the report's central wave-3 finding: safe-2
isn't just "one wave" worse off, it is the day's clear worst performer specifically because
`structure_veto_enabled=true` (safe-only) cost it every winning wave while `structure_stop`/
catastrophe-cap losses hit it the same as everyone else. The report's ≈+$500 opportunity-cost
estimate for wave 3 alone is, if anything, conservative once wave 4 (which safe-2 also missed,
same veto, confirmed still firing through 11:35:04) is counted.

**Split by VIX band**: not meaningful today. VIX ranged **14.83–15.10** across the entire
session so far (confirmed from `core-decisions.jsonl`, n=155 ticks) — a 0.27-point range, i.e.
one calm regime, no band to split by. This is itself a caveat worth stating explicitly: none of
today's findings (decay-dominated wave 1, structure-edge wave 2, veto-cost wave 3) have been
observed under any other VIX regime, and should not be generalized beyond "calm, low-VIX
morning" without more days.

**Today's 11:06 wave specifically**: not hurt by anything — it's the day's best wave, and no
change was proposed that would touch entries (the only candidate idea targets exits/stops).

## Other checks

- **Probe-arm mechanism** (task hint: "find any probe ledger it writes" for
  `SKIP_BULL_1100_1200`): confirmed `build_shared_signal.py`'s `PROBE_ALLOWED_VERDICTS =
  {"SKIP_BULL_1100_1200"}` is real, and the designated probe arm is `risky-3`
  (`accounts.json`'s `probe_arm` block, `enabled: true`). But `risky-3`'s own arm-roster entry
  carries `"retired_at": "2026-08-28"` (repurposed for the weekly-1 non-SPY lane) — a
  live config contradiction (probe block says enabled, arm roster says retired). I confirmed
  **zero `risky-3` fills today** (`grep` on `fills-ledger.jsonl` for `date_et=2026-09-03`), so
  this mechanism produced no data for today's block_bull_1100_1200 instance either way. The
  report's silence on this is benign — there was nothing to find — but the config
  contradiction (`enabled:true` vs `retired_at`) is a live dead-knob candidate worth a
  separate one-line note somewhere (not this report's job).
- **Quote-tape gap** for the wave-2→wave-3 "should have held" ≈+$1,000 notional claim:
  confirmed `analysis/quote-tape/2026-09-03.jsonl` has genuinely zero 770C rows between
  10:37 and 11:07:20 — the report's own "not directly observed" caveat on that number is
  accurate, not hand-waved.

## Bottom line

Every checkable number in the finding is correct. The headline dollar figures, wave-by-wave
mechanics, config-divergence root cause, and population-comparison citations all survive
independent re-derivation from raw ledgers. The two gaps found (incomplete wave-4 footnote;
imprecise "continuous veto" phrasing) are presentational, not factual errors, and the
concentration/arm/VIX-band lens tests I ran independently all *reinforce* the report's stated
conclusions rather than undercut them — most notably, extending the day to its actual latest
tick makes safe-2's structure-veto opportunity cost look larger, not smaller, than the report
already claims.
