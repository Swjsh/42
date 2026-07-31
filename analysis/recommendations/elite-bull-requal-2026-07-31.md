# block_elite_bull POST-FIX requalification — 2026-07-31 (corrected-feed era)

> **Verdict: (a) LIFT-GATE TRIAL on bold-2, min-size, forward kill-criterion.** Chosen by the
> FROZEN verdict rule (prereg locked 16:46:41 EDT, before any fetch/replay ran):
> [`elite-bull-requal-prereg-2026-07-31.json`](elite-bull-requal-prereg-2026-07-31.json).
> Full evidence table: [`elite-bull-requal-2026-07-31.json`](elite-bull-requal-2026-07-31.json).
> Tool: `backtest/tools/elite_bull_postfix_requal_2026_07_31.py` · Guard: `backtest/tests/`
> `test_elite_bull_postfix_requal_2026_07_31.py` (15 passed, RED-proofed both mutation directions).

## Why now

- The gate's own written re-eval condition was **"re-eval at n≥20 under corrected feed."** The
  levels compiler v2 (SIP + shelves + weights, commit `7b4aa3f4`) shipped 2026-07-27 evening;
  corrected-feed sessions available: **07-28..07-31 (4 days — partially met, stated plainly).**
- 2026-07-31: the gate blocked the core arms **111 times** on a gap-up → V-recovery day; the
  ungated fleet arms took the same signals and went green (+$120.48 book, first green day of the
  week). J: *"being blocked on an elite bull setup is not really ideal."*
- J's chart reads keep landing ON the compiled shelves to within pennies (737.68 = SHELF w5;
  739.72 vs 739.73 w5; 742.97 vs MEMORY_RES 742.90) — the mechanism the old gate evidence
  predates is now demonstrably different.

## The evidence, side by side (all real OPRA; entry+1; live registry-CONTROL exit shape)

| Era | Cohort | n | Total | WR | Drop-best | Source |
|---|---|---|---|---|---|---|
| **OLD (broken feed)** | Raw real fills, all arms, since SS-B | 24 | **−$885** | 0% | — | bull-requalification-2026-07-22.md |
| OLD | Decision-log mining ATM (06-25..07-17) | 30 | +$665.60 | 16.7% | **−$1,420.80** | bull-elite-atm-decision-log-mining-2026-07-22.json |
| OLD | Backtest-detection ATM | 9 | −$1,720.50 | — | — | bull-requalification-2026-07-22.json |
| OLD | OTM-2 SS-B (07-10) | 28 | −$3,873.60 | 28.6% | negative | block-elite-bull-ssb-revalidation.json |
| **POST-FIX** | **Safe sequential-hold, qty 3 (PRIMARY)** | **5** | **+$867.00** | **40%** | **+$177.40** | this study |
| POST-FIX | Safe per-event, qty 3 (sensitivity) | 10 | +$882.00 | 40% | +$192.40 | this study |
| POST-FIX | Bold sequential-hold, qty 3 | 5 | −$2.60 | 20% | −$321.00 | this study |
| **POST-FIX** | **Fleet REAL fills on the same signals** | **7 trades** | **+$1,242.00** | 71% | — | fills-ledger, FIFO, all 7 mapped ≤15 min to blocked clusters |
| POST-FIX | Core bold-2 REAL fill on cohort (gate not binding, VIX 18.38) | 1 | −$295.00 | 0% | — | 07-28 C741 11:28 |

**The drop-best on the PRIMARY cell is POSITIVE (+$177.40)** — the post-fix cohort is not one
lucky trade. The old-era mining cohort *failed* exactly this bar (drop-top-1 −$1,420.80). That is
the cleanest single-number statement of what changed.

**Mechanism story:** old evidence was gathered entirely under the broken level feed (IEX
premarket, fabricated PMH, stale levels → reclaims of levels that weren't really there → 0% WR
on 24 real fills). The v2 compiler produces shelves that persist across days and that price
respects to within pennies. Reclaims of REAL shelves, replayed through the REAL exit engine on
real OPRA, are green on 2 of 4 corrected-feed days and flat-to-small-red on the others.

## Honesty constraints (stated, not buried)

- **n=5 (PRIMARY) over 4 sessions.** This is NOT a ratified edge; it is exactly enough signal to
  justify a min-size forward trial with a kill-criterion — the trial IS the instrument that
  builds n≥20 under the corrected feed.
- **One trade (07-29 +$689.60) is 79% of the PRIMARY total.** Drop-best stays positive (+$177.40)
  but concentration at this n is unavoidable; the kill-criterion, not the entry bar, is the guard.
- **Bold's own blocked cohort replays flat (−$2.60/5tr, drop-best −$321).** Bold's gate binds only
  at VIX [15,18), so the bold trial samples a narrower population than Safe's [0,25) block — the
  trial arm is bold-2 (frozen pre-run, per the lane), and this caveat is the main reason to keep
  the kill bar tight rather than celebrate early.
- **Data provenance:** 07-28/29 contracts = Alpaca OPRA trade prints aggregated to 5-min
  client-side (the /options/bars endpoint began 403ing "OPRA agreement is not signed" mid-study;
  it worked 07-23). 07-31 contracts = TradingView OPRA_DLY 5-min bars, **cross-validated against
  the fleet's real broker fill prints on C746 — 3/3 fills inside the corresponding bar ranges.**
  All real OPRA prints; zero synthetic pricing. Standing repair filed for the agreement gap.
- **Late cluster (informational, never graded):** the 15:05–15:46 blocked signals replay
  +$634.70/6tr but are untradeable under `entry_no_trade_after_et = 15:00` regardless of this
  gate — lifting elite-bull does NOT unlock them. Logged as a separate future question only.
- Replay convention notes: entry fill = next 5-min bar open after the signal tick (same as the
  07-22 study); exits entry+1 strict `>` via the canonical `walk_exit_manager`; $0.02 exit
  slippage; qty-10 comparability cells in the JSON alongside the qty-3 primary.

## THE RECOMMENDATION — (a) LIFT-GATE TRIAL (bold-2, min-size, kill-criterion)

**Change (one key, one account, paper):** `automation/state/aggressive/params.json` →
`block_elite_bull: false` (leave `block_elite_bull_vix_low/high` untouched for instant revert).
Bold-2 then takes ELITE bull level_reclaim entries inside VIX [15,18) at its normal path;
**min-size only**: 3 contracts (Rule 6 floor), via the existing qty floor — no sizing change.

**Forward kill-criterion (frozen):** after **n≥10 elite-bull fills OR 10 sessions** (whichever
first): net P&L < 0 → set `block_elite_bull: true` again, question closed. Net ≥ 0 → run the
full OP-22 scorecard for permanent retirement of the gate.

**Revert:** one-line params flip back. **Blast radius:** bold-2 only; Safe's gate untouched;
fleet arms unaffected (they never read this key); kill switches unchanged (Rule 5 still bounds
the day at −50%).

**Authority:** paper-only gate flip on the paper Bold account = covered by ratified paper
autonomy (J 2026-07-01) + Rule 9 satisfied (weekend window, in writing, documented reason —
this file). **Does not touch the 10 rules, does not arm live money → does not need J first;
J's lever is REVOKE.** Per this session's lane (no live-config edits), the flip itself is left
to the conductor/next session to apply verbatim from this paragraph.

**What this does NOT do:** does not unblock Safe's gate (its [0,25) block stays; its forward
re-eval trigger: post-fix distinct tradeable safe events ≥ 20 or 10 corrected-feed sessions —
2026-08-08 — whichever first, per the prereg b-branch machinery). Does not touch the 15:00
entry ceiling. Does not re-litigate the exit-mechanism graveyard.
