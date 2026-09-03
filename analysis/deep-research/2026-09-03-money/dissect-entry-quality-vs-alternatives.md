# D5 ENTRY QUALITY TODAY vs J'S ALTERNATIVES

**Stamp:** 2026-09-03T11:40 ET · **Slug:** entry-quality-vs-alternatives · **Data cutoff:** core-decisions.jsonl through 11:45 ET (session live)
**Verdict: INCONCLUSIVE** on a reusable rule; several FACT-level findings about today survive.
Data + tools: `dissect-entry-quality-vs-alternatives.json` (all numbers), `backtest/tools/dissect_entry-quality-vs-alternatives.py` (builder, cached-data-only, re-runnable, $0, no network).

## TL;DR

- **Correction to the question's framing: only 2 of the 3 named engine entries are losers.** The 11:06
  entry (E3) hit TP1 at +107.6% and is fully closed as a winner (real fills: bold-2 bought 5x 772C @0.37,
  sold 3@0.78 + 2@0.75, **+$199, +107.6%**). Only **E1 (09:41, -48.98%, catastrophe cap, -$144)** and
  **E2 (10:16, -15.71%, structure stop, -$66)** are confirmed losers. This is FACT from `fills-ledger.jsonl`,
  not the task's premise -- reported as found, not smoothed over.
- **J's put (Alt1) is ALSO a mechanical loser under the production exit rule -- the "orphan band" the
  morning audit already flagged.** It ran to **+37% favorable** (SPY 767.78) before round-tripping to a
  **structure-stop loss of ~-21.6% (~-$23/contract, APPROXIMATE)** at 11:06 -- the exact same bar (SPY
  closing back above 769.81) that fired the engine's own E3 chase entry. One bar, two opposite outcomes.
- **J's calls (Alt2, Alt3) are the day's cleanest entries by outcome.** Alt2 (10:45, 768.00 reclaim)
  crossed **TP1 at +108.8%** by 11:31 with a runner still open (+97.2% unrealized at cutoff);
  Alt3 (10:55) is **unresolved but favorable (+80.0% at cutoff, no stop touched)**. Both ride the SAME
  breakout the engine's own structure stop had just shaken E2 out of nine minutes earlier.
- **The feature that best separates today's clean losers (E1, E2, Alt1) from the rest: zero confirming
  closed 5-min bars before entry** -- all three fired on the FIRST bar to close beyond the level. E3 is
  the exception (also zero-confirmation, but a momentum breakout, not a chop-reclaim, and it won).
  Alt2 had 2 confirming bars held before entry; Alt3 had 3. **n=6 -- not remotely a statistical claim.**
- **This exact feature has never been tested historically** (not in the entry-location schema; would need
  the same bar-close reconstruction across all 191 trades, out of scope here). Its closest tested cousin,
  range_position / chase-the-extreme, does **NOT** reliably separate winners from losers at n=186-191
  (gap CI **[-72.84, +38.91]**, sign flips at 0.90/0.10 threshold) -- so today's clean n=6 pattern should
  be read as a candidate for the F2 forward instrument the morning audit already queued, not as a rule.

## Method

Six entries, one feature set, computed identically:
1. **Engine entries (E1, E2, E3):** real decision rows (`core-decisions.jsonl`, account=safe/bold) at the
   exact fill timestamps, cross-checked against real fills (`fills-ledger.jsonl`).
2. **J's alternatives (Alt1-3):** the same decision-row schema at J's stated timestamps -- every one of
   J's three ticks corresponds to a REAL row the engine itself logged (bull/bear score, triggers,
   blockers), not a hypothetical reconstruction of price alone.
3. **range_position:** two numbers shown per entry -- the engine's own live-computed `conviction.
   components.range_position` (session-scoped OHLC envelope, most authoritative, available only for E1/
   E2/E3) and a **close-tape** version computed identically to this morning's `money_entry_location.py`
   (session hi/lo = max/min of the 1-min bar-close `spy` field, ticks <= entry, no look-ahead) -- the only
   version computable for J's alternatives since today's true intrabar OHLC isn't cached anywhere local.
4. **Zone-width distance:** `|spy_at_entry - level| / zone_half_width`, using `key-levels.json`'s
   `zone_width` field (a half-width -- e.g. `SHELF_768.56_770.16` at price 769.36 has zone_width 0.8,
   confirmed against the label's own bounds). Levels sourced from `level_memory` (Alt1's 769.81) have no
   registered zone_width -- raw dollar distance reported instead, explicitly flagged.
5. **Retest vs breakout:** classified from the 5-min bar-CLOSE sequence (`bar_freshness.bar_et` +
   `spy`, one value per closed bar) around each level -- did price close on the opposite side of the
   level in a PRIOR bar and then close back (retest), or skip through without an in-between close
   (breakout)? **No true OHLC (wick) data is cached for today** -- this is a close-only reconstruction,
   stated as a limitation everywhere it matters (Alt3 especially).
6. **Bar volume vs 20-bar baseline:** **UNVERIFIED for all six** -- no cached OHLCV-with-volume exists
   for today's live session anywhere in the checked local files (`backtest/data/highres/` only has
   09-01/09-02 option bars; no SPY volume bar cache for 09-03).
7. **Walk-forward exit simulation:** structure-stop direction verified against the ACTUAL production code
   (`automation/state/fleet/exit_manager.py:_structure_stop_hit`, read-only) -- calls exit on close below
   trigger_level, puts on close above, structure checked BEFORE the -50% catastrophe cap, matching the
   documented ordering exactly. Option premiums for J's alternatives are a **Black-Scholes proxy**
   (r=0, sigma=VIX/100, T=minutes-to-16:00-ET/(390*252)), **calibrated** to the nearest real NBBO quote
   in `analysis/quote-tape/2026-09-03.jsonl` for that exact strike (a multiplicative factor forcing the
   model to match the real market at the anchor tick, held constant forward/backward). Cross-checked at
   the put anchor via put-call parity against the real 770C quote (model-free): calibrated BS put $1.083
   vs parity-derived $1.215, **-10.9% apart** -- stated as the proxy's rough error bar.

## Part 1 -- entry-tick feature table

| # | ts ET | side | level | zw-half | spy | range_pos (close-tape / engine C4) | dist $ | dist zw | retest/breakout | confirm bars | HTF bull-align age | ribbon-width c | option spread real | vix |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **E1** engine | 09:41:03 | C | 769.36 | 0.80 | 769.735 | 1.000 / **0.966** | 0.375 | 0.469 | BREAKOUT-reclaim | **0** | 11 min | 97.6 | $0.02 | 15.02 |
| **E2** engine | 10:16:03 | C | 768.00 | 0.384 | 768.37 | 0.695 / **0.336** | 0.370 | 0.964 | RETEST-reclaim | **0** | 46 min | 169.3 | $0.02 | 15.00 |
| **E3** engine | 11:06:04 | C | 769.36 | 0.80 | 770.445 | 1.000 / **1.000** | 1.085 | 1.356 | BREAKOUT-chase | 0 (momentum) | 96 min | 162.2 | $0.00 | 14.95 |
| **Alt1** J put | 09:50:04 | P | 769.81 | n/a | 769.79 (769.66 live) | 1.000 | 0.02-0.15 | n/a | RETEST-rejection | **0** | 20 min | 129.0 | ~$0.01 (analog) | 14.97 |
| **Alt2** J call | 10:45:05 | C | 768.00 | 0.384 | 768.20 | 0.659 | 0.20 | 0.521 | RETEST-reclaim | **2** | 75 min | 154.1 | ~$0.01 (analog) | 14.94 |
| **Alt3** J call | 10:55:03 | C | 767.58 | 0.80 | 768.75 | 0.777 | 1.17 | 1.462 | BREAKOUT-late-chase | 3 (but see caveat) | 85 min | 147.0 | ~$0.01-0.05 (analog) | 14.98 |

HTF alignment (daily=downtrend / hourly=uptrend / m15=uptrend, bull agree 2/3, bear agree 1/3) was
**identical and unchanged for all six entries** -- it fixed fresh at today's 09:30:06 open and never moved
through 11:45 ET, so "age" above is simply minutes into the session. Ribbon has been BULL continuously
since **2026-09-02T15:16:03 ET** (prior session) -- no intraday flip today, so "minutes since flip" in
wall-clock terms (1105-1190 min for the six entries) spans the overnight close and isn't a meaningful
trading clock; minutes-into-session is the useful number and is shown above.

**Ribbon-width ("spread_cents") caveat:** this ledger field is the SPY EMA-ribbon fast/slow band width in
cents (verified against `heartbeat_core.py` source comments), **not** the option's bid-ask spread. The
real option NBBO spread (from `exec.nbbo` on real fills / `quote-tape` for the rest) was $0.00-0.02 for
every entry with a real quote today -- liquidity was never the story on any of the six.

## Part 2 -- the retest/breakout evidence (5m bar-close sequences)

- **E1:** `...765.13 -> 768.99(<769.36) -> 769.735(>769.36, ENTRY)`. Reclaim and entry are the SAME bar.
- **E2:** `...768.16(>768) -> 767.78(<768, dip) -> 768.37(>768, ENTRY)`. A real dip-and-reclaim, but entry
  fires on the reclaim bar itself.
- **E3:** `...768.62 -> 769.265(<769.36) -> 770.445(ENTRY, already past the WHOLE zone's 770.16 edge)`.
  No in-zone close at all -- a momentum thrust, not a level interaction.
- **Alt1:** `769.735 -> 769.79` -- price stalls just under 769.81 for two bars; the engine's own
  `bear_rejection_level_raw=769.81` / `bear_triggers_raw=['level_rejection','confluence']` fired at this
  exact tick (09:50), independently confirming this was a real rejection signature, not J eyeballing a
  chart after the fact.
- **Alt2:** `768.16 -> 767.78(<768, SAME breach that stopped E2) -> 768.20(reclaim #1) -> 768.19(HOLD, bar
  #2) -> [ENTRY at 10:45]`. Two confirming closed bars above the level before J's stated entry.
- **Alt3:** `768.20 -> 768.19 -> 768.75 -> [ENTRY at 10:55]`. By the stated entry tick, price had already
  closed three bars above the 767.58 shelf's center -- **not** a fresh touch of "767.5-768" by this
  reading. **No OHLC/wick-low data is cached for today**, so the literal wick J describes (a low print
  below any closed-bar value on file) cannot be confirmed or refuted from local data -- flagged as
  UNVERIFIED rather than assumed. If the true entry were at the wick low itself (~767.6-767.9, closer to
  the 10:05/10:30 bar closes of 767.78/767.96) rather than at 10:55's prevailing price, the zone-width
  distance and confirmation-bar count would both look like Alt2's, not like E3's.

## Part 3 -- walk-forward P&L

| # | entry premium | mechanism / result | pct | $/contract | status |
|---|---|---|---|---|---|
| **E1** | $0.98 (real fill) | catastrophe cap -50%, real sell @$0.50, 10:03 ET | **-48.98%** | **-$48.00** | FACT, closed loss |
| **E2** | $1.40 (real fill) | structure stop, real sell @$1.18, 10:36 ET | **-15.71%** | **-$22.00** | FACT, closed loss |
| **E3** | $0.37 (real fill) | TP1 @+100%, real sells @$0.78/$0.75, 11:16-11:21 ET | **+107.57%** | **+$39.80 avg** | FACT, closed win |
| **Alt1** (put) | $1.083 (calibrated BS; parity cross-check $1.215) | peaked +37.0% (10:11), structure stop (close>769.81) @11:06 | **-21.6%** | **~-$23** | APPROXIMATE, would-be closed loss |
| **Alt2** (call) | $1.234 (calibrated BS) | TP1 @+100% crossed 11:31 (+108.8%); runner open +97.2% at cutoff | **+108.8%** (partial) | blended **~+$131** | APPROXIMATE, TP1 confirmed / runner open |
| **Alt3** (call) | $1.352 (calibrated BS) | never stopped; +80.0% unrealized at 11:46 cutoff, no TP1 cross yet | **+80.0%** (unrealized) | **~+$108** unrealized | APPROXIMATE, UNRESOLVED |

All three exit-timing determinations (which bar, in which direction) are **FACT** -- they come directly
from the real SPY bar-close tape and the production code's own stop-direction rule, verified by reading
`_structure_stop_hit` in `automation/state/fleet/exit_manager.py` (read-only). Only the **dollar/percent
magnitude** for Alt1-3 is APPROXIMATE (BS-proxy, ~11% model-vs-parity gap at the one point checkable
model-free). Alt2's blended $ figure additionally assumes the SAFE tier's 0.8 TP1 sell-fraction --
stated assumption; Bold's 0.667 would shift it slightly, not the sign.

## Part 4 -- does any single feature separate today's losers?

Today's outcomes, ranked by what actually happened/is happening:
**Losers:** E1 (-48.98%, FACT), E2 (-15.71%, FACT), Alt1 (-21.6%, APPROXIMATE).
**Winners/favorable:** E3 (+107.57%, FACT), Alt2 (+108.8% partial, APPROXIMATE), Alt3 (+80.0% unrealized, APPROXIMATE, unresolved).

- **Zone-width distance does NOT cleanly separate them.** E1 (loser, 0.469 zw) and Alt1 (loser, ~0.03 zw)
  are both close-to-the-level, but E2 (loser, 0.964 zw) is nearly at the outer zone edge -- same bucket
  as the winners (Alt2 0.521, E3/Alt3 1.36-1.46). No threshold on this feature cuts the six cleanly.
- **Confirmation-bar-count comes closer.** All three losers (E1, E2, Alt1) fired on the FIRST closed bar
  to cross the level -- zero bars of confirmation held before entry. Alt2 had 2 confirming bars; Alt3
  (by the literal 10:55 reading) had 3. **E3 is the clean exception**: also zero-confirmation, yet the
  day's biggest winner -- because it was a momentum breakout through an already-vacated zone, not a
  chop-level interaction. The feature works for chop-reclaim setups (E1, E2, Alt1, Alt2) and says nothing
  useful about breakout-momentum setups (E3, arguably Alt3).
- **n=6. This is not a statistical claim** -- it is a pattern worth watching, stated as such.

**Does this feature (or its closest tested cousin) separate winners from losers historically?**
Zone-width distance and confirmation-bar-count have **never been computed** for the historical population
-- `entry-location-rows.json`'s schema has no such field, and `SYNTHESIS.md`'s own forward-instrument list
(F3) names "the true zone width in force on past triggers" as an **unresolved prerequisite**, not
something already answered. The closest tested cousin is **range_position / chase-the-extreme**, from
this morning's H1 report (n=186, cutoff 2026-08-06+): gap between chase (>=0.75/<=0.25) and rest is
**$2.12 vs $18.90/trade, 95% CI [-$72.84, +$38.91]** -- crosses zero -- and the sign **flips** at the
0.90/0.10 threshold (chase does BETTER there: $20.07 vs $3.44). Within `BULLISH_RECLAIM_RIDE_THE_RIBBON`
alone (n=108, the setup all six of today's trades share), chase nets -$0.87/trade (PF 0.99) vs rest
+$42.27/trade (PF 1.67) -- directionally matching a "fresh/confirmed beats chase" story, but the gap CI
**[-$128.89, +$37.97]** still crosses zero at that sample size. **Conclusion: the historically-tested
near-cousin of today's clean n=6 pattern has NOT held up before.** Today's confirmation-bar-count read
should go into the F2 forward instrument queue (entry-location x trend-quality shadow ledger) already
proposed this morning, not be treated as an actionable rule.

## Caveats

- E3 is a real, closed WIN (TP1 hit, +107.6%) -- the task's framing of "three engine losers" does not
  match the fills ledger; corrected explicitly above rather than silently matched to the premise.
- Bar volume vs 20-bar baseline: UNVERIFIED for all six entries -- no cached OHLCV-with-volume exists for
  today's live session anywhere checked (highres cache only covers 09-01/09-02; no today SPY bar cache).
- No true intraday OHLC (only 5m bar closes) is cached for today -- the retest/breakout classification and
  Alt3's "wick bounce off 767.5-768" in particular rest on close-only reconstruction; flagged inline.
- J's alternatives' option premiums are a calibrated Black-Scholes proxy, not real fills -- cross-checked
  against real quotes/parity where possible (~11% model-vs-parity gap at the one checkable point); treat
  dollar magnitudes as directionally right, not fill-accurate.
- Alt2/Alt3 P&L is measured only through the 11:45/11:46 ET data cutoff (session was still live when this
  was run) -- both may move further before the real close; Alt3 in particular is explicitly unresolved.
- No live/production file was read from anywhere but its logged, already-written state; nothing in
  `automation/state/**`, `journal/**`, or `analysis/quote-tape/**` was modified.
