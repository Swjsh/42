# VERIFY — dissect-wave-autopsy (skeptic pass #0)

**Verdict: NOT REFUTED.** Confidence: HIGH. Every dollar figure, SPY tick, zone width, config
value, and the central code-mechanism claim were independently recomputed from the raw ledgers
(not re-read from the target report) and matched exactly. Five non-fatal presentation/rigor
issues found and logged below; none change the headline or the wave1/wave2/wave3 P&L.

## What I recomputed independently (raw ledger -> my own numbers, not copied from the report)

**Fills P&L, all 10 positions, from `automation/state/fills-ledger.jsonl` directly** (35 today
option rows pulled fresh, sorted, matched by arm/symbol/ts):
- Wave1: safe-2 (0.98->0.50, 3x) = -$144.00; bold-2 (0.37->0.20, 5x) = -$85.00; safe-3
  (1.11->0.57, 5x) = -$270.00; risky-1 (1.08->0.52, 5x split 3+2 buy) = -$280.00. **Sum -$779.00.**
- Wave2: safe-2 (1.40->1.18, 3x) = -$66.00; bold-2 (0.48->0.34, 5x) = -$70.00; safe-3
  (1.31->1.18, 5x) = -$65.00; risky-1 (1.31->1.18, 5x split 4+1 sell) = -$65.00. **Sum -$266.00.**
- Wave3: bold-2 (0.37 -> 3@0.78+2@0.75, 5x) = +$199.00; safe-3 (1.17 -> 3@2.32+2@1.98, 5x) =
  +$507.00; risky-1 (1.18 -> 3@1.81+2@1.95, 5x) = +$343.00. **Sum +$1,049.00.**
- **Net = -779 -266 +1049 = +$4.00.** Matches the report's headline exactly, computed fresh from
  the ledger, not copied from the report or its JSON.
- %-of-premium figures cross-checked for all 10 legs (e.g. safe-2 w1 -144/294=-48.98%, bold-2 w3
  199/185=+107.57%, safe-3 w3 507/585=+86.67%, risky-1 w3 343/590=+58.14%) — all exact matches.

**Entry range_position, from `automation/state/core-decisions.jsonl` directly** (own script, not
the report's): wave1 (09:41:03, SPY 769.735) — prefix n=12, hi=lo=769.735 -> rp=1.0000, session
range 765.13-769.735, exact match. wave2 (10:16:03, SPY 768.37) — prefix n=47, hi=769.79,
lo=765.13 -> rp=0.6953, exact match. wave3 (11:06:04 bold / 11:06:03 safe both read SPY 770.445)
— prefix n=97, hi=770.445=spy_at_entry -> rp=1.0000, exact match. The bold/safe tick agreement at
770.445 also independently confirms the "one shared signal, near-simultaneous SPY reads across
accounts" claim.

**Zone widths, from `automation/state/key-levels.json` directly:** level 769.36
(`SHELF_768.56_770.16`) has `zone_width: 0.8`, and its own `backside_retest.shelf_band` field is
literally `[768.56, 770.16]` — confirms 769.36 is the shelf's midpoint and zone_width is used as
a **radius**, exactly as the report's `769.36 ± 0.8` methodology assumes. Level 768.00
(`INTRADAY_PMH`) has `zone_width: 0.384`. Both exact matches.

**The exact wave2 stop-mechanics row, pulled directly from `core-decisions.jsonl`:**
`2026-09-03T10:36:03 SPY260903C00768000 last_closed_5m_close=767.96 trigger_level=768.0
actions=[('structure_stop','structure_stop @ 768.0', True)]` — byte-for-byte match to the
report's central Wave-2 claim (4-cent raw-level breach, 767.96 vs 768.00).

**SPY path after the wave2 stop:** queried `core-decisions.jsonl` for the min/max SPY between
10:36 and 11:35 independently — min is exactly `('2026-09-03T10:36:03', 767.96)` (the stop tick
itself) and max is exactly `('2026-09-03T11:31:03', 772.93)`. The $4.97 rally claim is exact.

**Implied realized delta, recomputed from scratch** (not read from the JSON) using the same
1-min-snapshot method: safe-2 w1 2.462x, bold-2 w1 1.172x, safe-3 w1 2.769x, risky-1 w1 2.872x,
and w2 legs 0.537x/0.341x/0.317x/0.317x — every value matches the report's `q2_spy_points_at_stop`
JSON block exactly, computed independently from the raw SPY ticks at each fill's own timestamp.

**The core code-mechanism claim — this is the load-bearing one for the whole "should have held"
Wave-2 argument, so I read the source rather than trust the report's description.** Read
`automation/state/fleet/exit_manager.py` lines 140-148 directly:
```
def _structure_stop_hit(side, trigger_level, last_closed_5m_close):
    ...
    return (last_closed_5m_close < trigger_level) if side == "C" else (last_closed_5m_close > trigger_level)
```
This compares the 5m close against the **raw** `trigger_level` with no zone/band adjustment
anywhere in the function or its 15 lines of docstring. **Independently confirms** the report's
central claim that the live structure-stop mechanism is not zone-aware, at the source-code level
— not just inferred from one trade's numbers.

**Config values — read fresh, not copied:** `automation/state/params.json:314`
`"structure_veto_enabled": true`; `automation/state/aggressive/params.json:52`
`"structure_veto_enabled": false`, doc string `"...over 25,821 ledger rows SKIP_STRUCTURE_VETO
fired 116 times for account=safe and ZERO times for bold"` — verbatim match, both lines.

**Population stats, recomputed from `entry-location-rows.json` directly:** n=113
BULLISH_RECLAIM_RIDE_THE_RIBBON calls, winners n=36 mean range_position 0.824, losers n=70 mean
0.8431 — exact match (I did not audit that file's own row-level construction; it's a reused
sibling artifact, out of this pass's scope).

**Cross-referenced citations verified verbatim in their source docs:** `entry-location.md` lines
101-102 (mid-band n=32, $51.69/trade, WR 40.6%, PF 2.14) and `SYNTHESIS.md` line 31 (orphan-band
45.5% of 279 losers) both match the report's quoted figures exactly.

**structure_reason "range"->"downtrend" flip:** confirmed at the correct JSON path
(`conviction.structure_reason`, top-level of the conviction dict, not under `.components`) —
bold-2's own row reads `"range"` at 11:06:04 and `"downtrend"` at 11:27:04. Exact match.

## Independent corroboration found: a sibling report already re-derives the same Wave-2 result

`analysis/deep-research/2026-09-03-money/dissect-hold-counterfactual.md` (a same-day, same-audit
D4 report, different script, quote-tape-validated methodology with a `last_closed_5m_close`
formula cross-checked against 47 ground-truth points, 0 mismatches) independently reaches the
same conclusion for Wave 2: *"the real structure stop... fired on a 4-cent breach... the
zone-adjusted floor... is 767.616 — and the 5m close never went below 767.96 in the whole
observed session, so a zone-respecting version of the same rule would never have fired."* Its
own book-level "Real (what happened)" total across the same 8 wave1+wave2 legs is **-$1,045**,
which is exactly `dissect-wave-autopsy`'s wave1(-$779)+wave2(-$266) sum. Two independently-run
scripts against the same raw ledger produced the identical total — strong corroboration, not
just self-consistency within one document.

D4 also refines (without contradicting) D1's Wave-1 "should have held" answer: it shows a
zone-respecting stop would NOT have saved Wave 1 either — SPY kept falling to 767.78 by
10:11-10:15, a genuine zone-floor breach, so a zone stop would have fired at 10:06 at a *worse*
price than the actual cap. D1 says the same thing more briefly ("a zone-edge-stop rule would have
behaved identically... the catastrophe cap alone determined the exit") — consistent, not in
tension.

## Issues found (non-fatal — presentation/rigor gaps, not fabrications)

1. **The markdown's per-arm equity percentages for safe-3/risky-1 are not actually produced by
   the cited script.** The JSON literally stores `"pnl_pct_of_equity": None` for safe-3/risky-1
   in every wave (verified: the script's `waves` dict sets `"equity": None` for fleet arms and
   the percentage is only computed `if pos.get("equity")`, which is falsy for None). The
   markdown's "-4.79%" / "-4.55%" / "-1.15%" / "-1.06%" / "≈+8.99%" / "≈+5.58%" figures were
   evidently hand-computed against the task-prompt's supplied start-of-day equity figures
   (safe-3 $5,639.10, risky-1 $6,149.12) outside the script — I recomputed them against those
   equity figures and they check out arithmetically, but "the script reproduces this report" is
   not quite true for these six cells.

2. **"SKIP_STRUCTURE_VETO 11:11:04-11:35:04 continuously" overstates the real pattern.** I pulled
   every safe-account row from 11:00-11:36 directly: the window actually alternates —
   `SKIP_STRUCTURE_VETO` fires for 3 consecutive minutes, then **`HOLD` / "no setup passed
   scoring (neither bear nor bull)"** for ~2 minutes (11:14-15, 11:19-20, 11:24-25, 11:29-30),
   then `SKIP_STRUCTURE_VETO` resumes. 17 of the ~25 minutes were vetoed; 8 were minutes where
   safe-2 had no qualifying bull signal at all, independent of the veto. The report's own JSON
   (`safe2_wave3_refusal`) doesn't even substantiate the full window it describes — its filter
   (`"11:0" <= ts <= "11:22"`) is a string-comparison bug that truncates the list at 11:22,
   silently dropping the 8 SKIP_STRUCTURE_VETO rows from 11:23-11:35 that I found by direct
   query. The underlying conclusion (safe-2 was denied entries bold/safe-3/risky-1 got, during a
   rally, by a gate those arms don't run) is correct and independently confirmed, but "blocked
   continuously the entire window" is not literally what the ledger shows.

3. **Wave2's zone_width (0.384) carries `zone_width_provenance: "default_pre_ab"`** — a static,
   unmeasured default — versus Wave1/3's shelf level, whose zone_width (0.8) has provenance
   `"shelf_band_observed"`, i.e. empirically derived from 7 actual touches over 17 sessions. The
   report uses both with equal confidence and doesn't flag that the specific "$0.344 inside the
   zone" number for Wave 2 rests on an unvalidated default rather than a measured band. The
   qualitative code-level finding (raw-level-only comparison, no zone consulted at all) is solid
   regardless of the exact width value — but the specific magnitude is softer than presented.

4. **Minor overstatement: "767.96... was the exact local low of the whole morning session so
   far."** I checked: the actual session low through that point was **765.13 at 09:31 ET**, $2.83
   lower and over an hour earlier. 767.96 was only the local low *from the wave2-entry window
   (10:16) onward*, not the whole morning's low. Doesn't affect any dollar figure.

5. Did not re-verify `entry-location-rows.json`'s own row-level outcome/range_position labeling
   (a separate, reused sibling artifact) — inherited as given, consistent with the report's own
   disclosure that it was "built earlier today by a sibling H1 investigation, reused not
   rebuilt."

## Look-ahead check (per task lens)

No live rule change is proposed (`change_class: NONE`, confirmed correct — trading-path files
were read-only throughout this verification too). The one *candidate* future rule described
(compare 5m close against `trigger_level - zone_width` instead of the raw level) uses only
information available at decision time (zone_width is a static per-level field already known
before any given 5m bar closes) — no look-ahead in the described mechanism. The narrative
evidence used to argue "should have held" for Wave 2 (safe-3/risky-1's real Wave-3 fills on the
same 770C strike, ~40 minutes later) is explicitly and correctly labeled hypothetical/approximate
color for a documented gap, not a backtested, tradable rule result — appropriate for a same-day
retrospective autopsy, not a look-ahead-tainted live-rule claim.

## Bottom line

Recomputing independently from `fills-ledger.jsonl`, `core-decisions.jsonl`,
`key-levels.json`, `params.json`/`aggressive/params.json`, and `exit_manager.py` source
reproduced every dollar figure and the central code-mechanism claim exactly, and an independent
sibling script (D4) reached the same Wave-2 conclusion by a different, more rigorous method with
an identical real-P&L total. The five issues above are real but narrow (a reproducibility gap on
six equity-percentage cells, an overstated "continuously" framing with a truncated companion
JSON, an unflagged default-vs-measured zone-width provenance gap, one imprecise sentence about
"the session low," and an unaudited upstream population file). None of them touch the headline
+$4.00 net, the wave-level P&L, or the verified structure-stop code mechanism. **Verdict:
SUPPORTED stands.**
