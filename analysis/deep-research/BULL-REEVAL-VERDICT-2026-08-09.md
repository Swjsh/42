# BULL SIDE — the owed re-evaluation — 2026-08-09

**Verdict: KEEP bull enabled. The "lose most days, one day pays" shape is a property of the 0DTE BOOK, not of calls — bear has it too (12/17 negative days vs bull's 14/18). Neither side is an edge right now. No block, and no direction-specific conclusion is supported by this data.**

> ## ⚠️ CORRECTED 2026-08-09, same evening, after J pushed back
>
> The first version of this document called bull "a trend-day lottery ticket, not a steady edge"
> and led with "14 of 18 bull days are negative", as though that were a **bull** property. It is
> not. I ran the day-level distribution on calls only — because OP-16 asked for a *bull* re-eval —
> and never ran the mirror on puts. Running it:
>
> | | n | days | total | mean/tr | negative days | best day | ex-best-day |
> |---|--:|--:|--:|--:|--:|--:|--:|
> | Calls (bull) | 164 | 18 | −$1,129 | −$6.88 | **14/18 (78%)** | +$3,624 (08-04) | **−$4,753** |
> | Puts (bear) | 80 | 17 | −$84 | −$1.05 | **12/17 (71%)** | +$1,501 (08-06) | **−$1,585** |
>
> **Same shape on both sides.** Bear loses on 71% of its days and its total is carried by one
> session exactly as bull's is. Ex-best-day, both are deeply negative. Asymmetric analysis
> produced an asymmetric-looking conclusion; the conclusion was an artifact of which cut I ran.
>
> J's correction, verbatim: *"i dont understand the gripe witth 'calls' vs PUTS, you're very keen
> on bear setups. we need to play both sides of the market, period."* That is not a preference —
> it is already ratified doctrine (OP-16: **"direction is NOT a scope, validation is"**).
>
> **What survives from the original:** bull is modestly worse per trade (−$6.88 vs −$1.05) on
> double the sample, and the recent "+$948 since 07-25" really is one day wide (ex-Tuesday
> −$2,676). Those are real. What does NOT survive is treating the day-distribution shape as
> evidence against calls specifically.
>
> **What this exposed downstream:** see
> [`DIRECTION-SYMMETRY-AUDIT-2026-08-09.md`](DIRECTION-SYMMETRY-AUDIT-2026-08-09.md) — the live
> config makes bull materially harder to ENTER than bear (2× triggers, higher macro bar, a
> 5-point narrower VIX window, plus a bull-only time veto), on evidence samples as small as
> n=11 from June. That asymmetry, not the day distribution, is the real finding this re-eval
> should have surfaced.

## Why this is filed now

`CLAUDE.md` OP-16 carries a standing debt, written 2026-07-11:

> bull evidence corrected 2026-07-11: old +$5,586/56% WR was a real-OPRA SIM, not broker fills; live paper fills bull n=80 WR 1.2% −$1,573 (9-day, VIX pinned, small-n) — **stays enabled pending honest re-eval at n≥20** under SS-B + corrected strike tier.

The bar was **n ≥ 20**. The real-fills book now carries **n = 164 bull fills across 18 trading days**. The debt is payable, so it is being paid rather than carried another week.

## The numbers — real broker fills only, engine-attributed, 27-day book

| slice | n | days | total | mean/trade | WR |
|---|--:|--:|--:|--:|--:|
| **Calls (bull), all** | 164 | 18 | **−$1,129** | −$6.88 | 14.0% |
| Puts (bear), all | 80 | 17 | −$84 | −$1.05 | 27.5% |
| **Calls since 2026-07-25** (current config) | 64 | 8 | **+$948** | +$14.81 | 32.8% |

Bull setups: `BULLISH_RECLAIM_RIDE_THE_RIBBON` 124 · unlabelled 23 · `VWAP_CONTINUATION` 17.

**Day-level distribution is the whole story: 14 of 18 bull days are negative. Worst −$2,758. Best +$3,624.**

## The recent slice is not the recovery it looks like

+$948 since 07-25 looks like the corrected config working. It is not, and this is the honest reading:

**That window contains Tuesday 2026-08-04's +$3,624. Ex-Tuesday, the recent bull slice is −$2,676 across the other 7 days.**

So the "bull turned positive under the corrected strike tier" story is one day wide. The prior 2026-07-11 correction already caught a bull number that was a sim rather than broker fills; this is the same class of mistake one level up — a real number whose entire sign comes from a single session.

## Verdict, and why it is KEEP rather than BLOCK

**KEEP ENABLED.** Three reasons, in order of weight:

1. **The payoff profile IS the strategy.** A directional 0DTE call book that loses small on most days and makes a large amount on trend days is not malfunctioning — that is the shape. 14/18 negative days with a +$3,624 tail is a lottery-ticket distribution, and you do not evaluate a lottery ticket on its median day. What must be checked is whether the tail pays for the bleed, and over 18 days it *nearly* does (−$1,129 net on 164 fills, i.e. −$6.88/trade).
2. **Blocking on an 18-day aggregate is the exact error already recorded.** `block_elite_bull` blocked a perfect 11/11 setup 111 times on stale evidence. On paper, doctrine says bias toward *taking* the trade and letting the forward clock speak.
3. **Bear is not a better alternative.** Puts are −$84 over 80 fills — flat. Killing bull does not reveal a profitable bear book underneath; it just halves the sample.

**What changes:** the label. Bull is no longer described as "pending re-eval". It is **measured, enabled, and negative-but-small on 164 fills**, with its positive slice attributable to one session. Anyone citing bull P&L must cite the day distribution alongside it.

## What would actually flip this to a block

- Bull's per-trade expectancy goes materially more negative over the next 20 trading days **while** the trend-day tail fails to appear, or
- The tail appears and still does not cover the bleed over ≥ 40 days, or
- A pre-registered study isolates a bull sub-cohort that is negative independent of regime (the 23 unlabelled fills are the obvious first place to look — they are 14% of bull volume with no setup attribution).

## Open item this surfaced

**23 of 164 bull fills carry no `setup` label.** That is 14% of bull volume that cannot be attributed to a named pattern, which sits badly with Rule 1 ("no setup, no trade"). Not adjudicated here — flagged as the highest-value next slice, because an unattributed cohort is exactly where a silent loser hides.

## Doctrine action

`CLAUDE.md` OP-16's "stays enabled pending honest re-eval at n≥20" clause is **DISCHARGED** by this document. Bull stays enabled on evidence, not on inertia.
