# EOD FABLE AUDIT — 2026-08-17 (+$124)

> J's ask, verbatim intent: review Opus's day, review the engine, figure out why we didn't
> *really* make money, protect the tight-stop discipline, and answer three questions about the
> winner: **what did the engine see, why only 5 contracts, how do we make more on the one
> good trade.** Everything below re-derived from ledgers this session, not recalled.

## VERDICT

**The day was right-shaped, and J named the distribution himself: "take the setup every time,
keep it tight, and when it pays it really pays." Today that machine measurably existed —
payoff 6.1 : 1 at 20% WR (avg win $360, avg loss $59), positive expectancy +$24.8/trade.**
The handoff's breakeven math needs 2.3 : 1 at this WR; today delivered nearly triple that.

Per-account (the doctrine lens — never the combined number):

| account | day | vs $100–200 target |
|---|---:|---|
| **bold-2** | **+$360** | ✅ **above target** (+7.8% of $4,609) |
| safe-2 | −$36 | flat-ish; missed the winner (below) |
| risky-3 | −$200 | all tuition on ONE experiment (below — killed tonight) |
| risky-1, safe-3 | $0 | gates held them out all day — correct at VIX 15 |

"Why didn't we really make money" decomposes exactly: **one arm hit target; one experiment
paid −$236 tuition and executed its own pre-registered kill; two arms correctly sat out.**

---

## 1. The winner, forensically — J's three questions

### What did the engine see at 13:06?

```
SPY 774.67 · ribbon BEAR, spread 35.6c · VIX 15.1 · bear_score 8
trigger bar 13:00 (closed) · trigger: trendline_rejection (wick-flavor engine line)
verdict: ENTER_BEAR — "passed scoring + all entry gates (tier TRENDLINE)"
```

**It entered through the trendline-only lane — the ONLY bear lane that can fire at VIX 15.**
Filter 8 requires VIX > 17.30 *and rising*; at VIX 15 the entire ordinary bear machinery is
structurally off. The trendline-only shape waives filters 5/8/9 (`filters.py:1662-1672`, each
waiver logged as a chop-demerit). Filter 6 (spread ≥ 30c) passed on its own merits at 35.6c —
the ribbon had genuinely opened.

**A perverse detail worth knowing:** 13:04–13:05 had *more* evidence (level_rejection +
trendline_rejection, score 9) and was **blocked** — the extra level trigger made it not
"trendline-only," so the filter-8 waiver didn't apply. At 13:06 the level trigger aged off the
new bar, the setup got *narrower*, the waiver applied, and it fired. The entry happened
because the setup weakened in the eyes of the classifier. That is a real quirk of the lane
design, filed as an observation, not a change.

### Why only 5 contracts?

**Deliberate, not a bug — and I traced the exact line.** Core sizing is
`qty = int(params.get("min_contracts", 3))` (`heartbeat_core.py:2388`): a flat 5 for bold,
3 for safe. No tier lookup. The `position_sizing_tiers` table in aggressive/params.json
(base 8 / elite 12 at bold's $4,609) is **not consumed on the core path** — one more entry in
the dead-knob ledger. And `min_contracts_equity_scaled = false` is the standing state from the
08-15 handoff: **"Re-arm needs a VALIDATED entry-quality gate. The condition is not met."**

So bold deployed $360 of premium — 7.8% of equity — on the day's best setup, by design,
until an entry-quality gate validates.

### How do we make more on the one good trade?

**The path runs through one chain, and today produced the first honest evidence about it:**

> more contracts ← equity-scaled sizing re-arm ← validated entry-quality gate ← **conviction
> must first learn to see trendlines** (next section)

Quantified, today: equity-tier sizing (8 lots) would have made the winner **+$576 vs +$360**;
safe un-vetoed adds ~**+$216**. ≈ **$430 left on the table — but each dollar sits behind a
deliberate, evidence-bearing guard.** Flipping either without its validation is how the book
got hurt in August. Not flipped.

## 2. 🚨 The conviction gate would have BLOCKED the winner — first post-fix data

Today is day 1 of C4/C5 actually scoring (the 08-14 fix). 58 post-fix rows, **100%
would_block — including the 13:06 winner, which scored 0/8:**

- `named_level: 0` — the trigger was a **trendline**; `trigger_level_exact` is null and
  **conviction has no trendline component at all**
- `range_position: 0.046` — price at the session LOW; C4 is built for mean-reversion ("puts
  want the TOP of the envelope") and scores momentum breakdowns as zero
- The outcome join's day-1 ledger: **WOULD_BLOCK n=1, P&L +$360. WOULD_ALLOW n=0.**

**Had conviction been armed today, the book finishes −$324 worse.** One day, n=1 — not a
verdict on the ratchet. But it is a precise design finding: **as built, conviction is blind to
the only lane that fires at mid-VIX**, which is where this book lives most days. It cannot
validate while it scores the winners zero — and sizing re-arm waits on that validation.
**Queued: a trendline-quality component (line age / touches / wick-flavor per doctrine) before
the ratchet's next evaluation.** This is the single highest-leverage design fix on the board.

## 3. Safe missed the winner — structure veto read "uptrend" at the breakdown

All **17** `SKIP_STRUCTURE_VETO` ticks today were safe's, spanning **13:06–13:25 — exactly the
winning window**. The sameday swing classifier still read the 10:30→12:30 higher-low sequence
as "uptrend" while the 13:00 bar broke down — a **lagging read, C28's entry-side cousin
(L243)**. Bold, unencumbered, took it 1 second later: the champion/challenger asymmetry doing
its job, and today the challenger's freedom was right. Cost to safe ≈ $216. **Reported to the
standing structure-veto audit lane with today as an exhibit; gate untouched** — it has its own
evidence base and one day doesn't overturn it.

## 4. The four losers — right thesis, early clock, and one executed kill

All four were **one family** (`vwap_reclaim_failed_break`), all exited by its own validated
−8% premium stop. All four theses eventually paid: the 10:23 scratch was **the same 775P
contract** bold rode to +100% three hours later; the 776P entries reached ~+140% intrinsic by
13:30. So J's "maybe we hold one longer" is a real question — and it already has an
instrument:

- **The stop-mode A/B clock** (pre-registered 08-09) walks every fill under structure-hold vs
  premium-stop. **Interim, 95 trades / 5 days: premium stops AHEAD by +$1,809** — on recent
  tape, holding longer has *lost* money vs tight stops. Today's four accrue tomorrow
  (same-day OPRA bars are 403). Decision at the 20-day bar, not by feel. **Tight stops stay.**
- The 09:53→09:56 pair was a **3-minute same-contract re-entry after a stop** — the M3 churn
  family — and cost −$136 of the −$200.
- **THE KILL, executed tonight:** the fleet extension's own frozen checkpoint landed today
  (10 sessions from arming, ahead of n≥10; cohort net **−$200 < 0** → revert).
  `RUN_VWAP_RECLAIM_FB = False` — the prereg's named one-line revert. n=3 disclosed as thin;
  frozen criteria are not relitigated with hindsight. **Core safe-2's lane is outside that
  prereg and stays, on watch** (07-28 one fill, today −$36).

## 5. Review of Opus's day (J asked)

**Holds up:** the open-incident handling (blind engine, zero orders, repaired live, keepawake
root cause), the dead-knob audit (the SHADOWED-vs-UNREFERENCED distinction is the right cut),
the honest self-corrections (the matrix's VIX-extractor false negative was caught before
publication; the same-day-403 refinement corrected its own prior doc).

**Two pushbacks, so they don't calcify:**
1. *"Production 30c fails the OP-16 edge-capture bar"* is **overstated**. The EC cliff
   (709 → −621 between 28c and 30c) is driven by a handful of boundary trades — identical EC
   across six thresholds proves the anchor set only changes at one seam. That's a flag to
   autopsy the boundary trades, not a verdict on production.
2. Keep the matrix's regime finding scoped: it swept the **ribbon/core config**. Today's four
   losers were **vwap-family** — a different animal. "Filter 6 saved money today" is
   supportable for the ribbon lane only.

Minor: the j-question ledger classifies free-model audit prompts as `is_running` (43× is
inflated) — the instrument J's hook keeps citing needs its intent classifier fixed before its
counts mean anything.

## 6. What changed tonight / what deliberately did not

| action | status |
|---|---|
| vwap fleet kill (`RUN_VWAP_RECLAIM_FB=False`) | ✅ **executed** — pre-registered criterion, J-revocable |
| Discord trade-ping reformat (J's spec) | 🔄 Sonnet agent running; reports separately |
| Conviction trendline component | 📋 queued as the gate to sizing re-arm |
| Filter 6 / spread threshold | ⛔ untouched — matrix says regime, not spread |
| Premium stops / exit shapes | ⛔ untouched — stop-mode clock decides at D20 |
| Structure veto | ⛔ untouched — today filed as an exhibit to its standing audit |

**Nothing about today argues for loosening the discipline J praised. The evidence machine he
funded is doing its job: one experiment killed itself by its own rule, one gate produced its
first honest (and humbling) data, and the payoff-shape he described showed up in the ledger.**
