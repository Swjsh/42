# Capital Efficiency — the honest capital curve

Generated 2026-08-02T11:44 ET. Runner: `backtest/tools/capital_efficiency_2026_08_03.py`.
Guards: `backtest/tests/test_capital_efficiency_2026_08_03.py` (42 tests, RED-proofed live
this session — see §7). Raw data: `analysis/deep-research/CAPITAL-EFFICIENCY-2026-08-03.json`.

**Scope: MEASUREMENT + ARITHMETIC ONLY.** Zero edits to any trading-path file
(`heartbeat_core.py`, `params.json`/`aggressive/params.json`, `exit_manager.py`,
`exit_actuator.py`, `option_pricing_real.py`, `exit_manager_walk.py` — all read-only this
session). This document ships no trading change; it answers whether the engine's edge can
ever produce J's $100–200/day goal, and at what account size.

**Motivating question:** the current-live core-Safe engine's full-history replay is
published as $4,808.75 / 191 trades / 387 RTH days (`analysis/recommendations/
engine-fullhist-replay-2026-07-23.json`) = $25.18/trade, $12.43/calendar-day — an 8–16x gap
under FOCUS-DOCTRINE's $100-200/day target. Twelve pre-registered SELECTION attempts this
weekend all nulled. Nobody had checked whether the gap is closable by **SIZE** (capital
deployed) instead of selection — that is this document's job.

---

## Verdict first

- **The published $4,808.75 headline itself needed a correction before anything else could
  be trusted** (§0). It grades trades at a vestigial internal simulator qty (up to 13
  contracts), never the real live formula (always exactly `min_contracts`=3, clamped down,
  never up). Corrected to what the live engine would actually have placed: **$5,302.47 over
  159 trades ($33.35/trade)** at the population's own $1,746.75 baseline equity — HIGHER
  per-trade than published, because the risk cap's side effect excludes the 32 priciest
  candidates (premium > $1.75), which were themselves a net **loser** (-$1,456.70).
- **% return per dollar deployed** (task item 1, §1): mean **+6.4%/trade**, median **-20%**
  (the mechanical stop), winners average **+82.4%** (median +96.4%), losers cluster tightly
  at the stop (-20% to -25%), win rate **29.3%**. Classic small-frequent-losers /
  large-infrequent-winners shape.
- **Liquidity is NOT the binding constraint** (task item 2, §2) — but true NBBO **size**
  data does not exist anywhere in this repo, historical or live (a finding in itself). Using
  the best available proxy (5-min trade volume in each historical entry's own bar), even at a
  hypothetical **33x today's size (qty 100)**, median utilization of one bar's own volume is
  **1.2%**; the volume-flow "knee" (median trade crossing 10% of its own bar's volume)
  extrapolates to roughly **qty 830** — two orders of magnitude beyond anything the risk cap
  ever produces at realistic account sizes.
- **THE CAPITAL CURVE IS FLAT** (task item 3, §3, the headline finding). From $5,000 to
  $50,000 Safe equity, $/trade and $/day are **byte-identical** ($20.13/trade, $27.27/trading
  -day) at every single grid point. Bold: same story, flat $47.75/trade at every grid point
  from $2,000 to $50,000. Mechanism: `heartbeat_core.py:1964` sizes every order at exactly
  `params['min_contracts']` and never scales up, even though real headroom exists (Safe can
  legally afford 5/12/21/42/85 contracts at $2K/5K/10K/25K/50K — only 3 are ever requested,
  falling from 60% utilization of available headroom at $2K to **3.5% at $50K**). **Growing
  the account, by itself, does not move the daily-P&L needle under today's code** — this
  contradicts FOCUS-DOCTRINE's implicit assumption that "scaling comes from compounding the
  tier."
- **Frequency** (task item 4, §4): at the flat ~$20/trade rate, $100-200/day needs
  **5.0–9.9 trades per ACTIVE trading day**, against an actual **1.36/active-day** (0.49/
  calendar-day). The regime-participation study shows the shortfall is 42.4% GATE_BLOCKED +
  20.6% under-scored, not "no setups exist" (only 0.5% genuine no-vocabulary) — frequency
  competes directly with selection quality, which 12 pre-registered attempts already tried
  and nulled this weekend.
- **Recency** (task item 5, §5) is the one genuinely encouraging number: the last 25 trading
  days (2026-05-28..2026-07-21) run **$64.41/trading-day** live-faithful, vs **$44.19/trading
  -day** for the full 18-month history — real, recent improvement, though still short of
  target and thin (n=33 trades).
- **Real fills** (n=38, core Safe, 2026-04-29..2026-07-28) average $32.32/trade raw, closely
  matching the corrected simulation, and on the **14 distinct days J actually traded**,
  averaged **$87.71/day** — the closest any number in this document gets to $100-200/day, but
  too small (14 days) and too self-selected (J chose which setups to take) to trust as a
  forward estimate.
- **Blunt answer** (§8): at today's actual code and actual equity, this engine makes
  roughly **$10-19/calendar-day, $27-64/trading-day per account** — not $100-200. Scaling the
  account alone will not fix that (flat curve). The single highest-leverage, already-
  half-built fix is wiring core's sizing to actually use its own legal headroom (the fleet
  lane already has this exact mechanism, `position_sizing_tiers`, unused by core) — not a
  better edge, not more trades.

---

## 0. A correction that had to happen before anything else could be trusted

`engine_fullhist_replay.py` — the tool behind the $4,808.75 / 191-trade headline everyone
cites — grades every trade at `orchestrator.run_backtest`'s own internal "quality-tiered
sizing" (`backtest/lib/orchestrator.py:1194-1226`, a vestigial v13 concept: SUPER=15,
ELITE=10, LEVEL=22, TRENDLINE_LEG2=20, TRENDLINE/BASE=3 contracts, then scaled *down* only if
unaffordable at a static $1,746.75 equity). That is **not** what the live engine does. The
real formula (`setup/scripts/heartbeat_core.py:1964`, confirmed byte-exact against real fills
for both accounts):

```python
qty = int(params.get("min_contracts", 3))
afford = rg.max_affordable_qty(equity=equity, premium=mid, params=params)
if afford and qty > afford:
    qty = afford
```

Qty is **always** `min_contracts` (3 Safe / 5 Bold) — never auto-scaled up, and if even the
floor is unaffordable the *whole order is denied* (never shrunk further). 61 of the 191
replayed trades (32%) used qty 4–13, never 3.

Because option P&L is exactly linear in qty (`orchestrator.py:1919`'s own comment: *"option
P&L is linear in qty"*; independently re-derived in `bold_fullhist_replay.py`'s docstring
finding #1, which already applied this exact correction for Bold on 2026-08-01), every trade
can be honestly rescaled by pure arithmetic — no re-simulation needed:

| Correction step | Total P&L | n trades | $/trade | vs. published |
|---|---:|---:|---:|---:|
| **Published headline** (vestigial internal qty) | $4,808.75 | 191 | $25.18 | — |
| **Qty rescaled to min_contracts=3** (removes over-sizing, ignores affordability) | $3,845.77 | 191 | $20.13 | 80.0% |
| **Fully live-faithful** (qty=3 AND `order_affordable` cap-checked at the population's own $1,746.75 baseline) | **$5,302.47** | **159** | **$33.35** | **110.3%** |

The fully-corrected number is *higher* than published, not lower — traced and verified (not
assumed): the 32 trades excluded by the affordability check are exactly the highest-premium
candidates (all above the $1.75/contract ceiling at this equity — `premium_ceiling` from
`risk_gate.explain_block`), and that excluded cohort was a **net loser** historically (7
winners / 25 losers, -$1,456.70 rescaled). At this specific equity, the risk cap's side
effect of refusing expensive contracts happened to filter out a losing cohort. This is a
genuinely different, non-obvious mechanism from the ENTRY-1 premium-floor doctrine (which
filters the *cheap* end, sub-$0.20) — this is its mirror on the *expensive* end, discovered
by this analysis, not previously disclosed anywhere in the repo.

**All arithmetic downstream of §0 (the capital curve, §3) uses the fully live-faithful basis
(qty=`min_contracts`, cap-checked, never the raw historical qty).** The % return section (§1)
is unaffected by this correction — see why below.

---

## 1. Return per dollar deployed (task item 1)

`% return = dollar_pnl / (entry_premium × qty × 100)`. This ratio is **qty-invariant**
whenever P&L scales linearly with qty (proven true above, and unit-tested directly —
`test_qty_invariance`): whatever qty a trade historically used, this percentage is exactly
what the real min_contracts=3 fill would also have produced. So this section uses the
population's raw 191 rows directly — the §0 correction does not change it.

| | n | mean | median | p10 | p25 | p75 | p90 | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **All trades** | 191 | +6.44% | -20.00% | -40.22% | -20.00% | +10.89% | +103.03% | -68.93% | +138.11% |
| **Winners** (n=56, 29.3%) | 56 | +82.45% | +96.42% | +7.11% | +72.74% | +107.04% | +118.79% | +0.92% | +138.11% |
| **Losers** (n=135, 70.7%) | 135 | -25.09% | -20.00% | -49.03% | -21.89% | -20.00% | -20.00% | -68.93% | -5.88% |

Shape: **frequent small losers, infrequent large winners.** Losers cluster tightly around
-20% to -25% (median/p75/p90 all sit almost exactly at -20%) — consistent with a mechanical
premium/structure stop doing its job, not a fat-tailed blowup risk. Winners run wide and
strongly right-skewed (median +96%, max +138%) — the runner-cohort behavior this engine is
built around. This is the engine's true, size-independent edge: **every dollar deployed
returns +6.4% on average**, and that number is what everything else in this document scales
from.

---

## 2. Does the edge scale? Liquidity assessment (task item 2)

**Disclosed data gap (verified, not assumed):** this repo has never cached real NBBO
**size** (bid_size/ask_size) anywhere, historical or live. `backtest/data/options/*.csv`
(14,409 files, the entire OPRA cache `lib.option_pricing_real` serves) is OHLCV **trade**
bars only — `timestamp_et,open,high,low,close,volume,vwap,trade_count` — confirmed by
reading the schema directly and every fetch script (`fetch_option_data.py` calls Alpaca's
*bars* endpoint, never a quotes/NBBO endpoint). The one "nbbo" field that exists anywhere
(`core-decisions.jsonl` since 2026-07-20) is a **reconstructed** bid/ask/mid/spread with **no
size field**, algebraically inverted from `mid + entry_px + a fixed cross-buffer assumption`
(`test_nbbo_capture_2026_07_20.py`) — not a captured market observation. So "measure the real
displayed NBBO size" is not literally answerable from anything this repo has ever recorded.
A live weekend snapshot pull was considered and rejected: Sunday's SPY 0DTE contracts are
already-expired from Friday, so a live quote right now would be stale/worthless, not
representative — a fast-follow for an intraday Monday check, not fabricated here.

**Best available, fully disclosed proxy: 5-minute trade volume in each of the 191 trades'
own entry bar.** All 191 trades had bar data (0 excluded for missing cache). This is a
trade-**flow** proxy (how much the contract actually printed in a 5-minute window around our
entry), not a displayed-**depth** proxy (what was resting at the NBBO at the instant of our
order) — directionally informative, not proof.

| Hypothetical qty | median ratio (qty / bar volume) | p90 ratio | % of trades where ratio > 5% | > 10% | > 25% |
|---:|---:|---:|---:|---:|---:|
| 3 (today) | 0.036% | 0.083% | 0.0% | 0.0% | 0.0% |
| 10 | 0.120% | 0.277% | 0.0% | 0.0% | 0.0% |
| 30 | 0.361% | 0.830% | 0.0% | 0.0% | 0.0% |
| 100 | 1.203% | 2.766% | 3.7% | 1.0% | 0.0% |

**No knee shows up anywhere in the requested 3→10→30→100 range.** Even at 100 contracts
(33x today's actual size), the typical trade would represent about one-eightieth of its own
5-minute bar's print volume. Linear extrapolation (the ratio scales proportionally with qty
by construction) puts the volume-flow "knee" — the point where a *typical* trade would
represent 10% of its own bar's volume — at roughly **qty 830** (median) to **qty 360** (90th
percentile, the more cautious read). Both are two orders of magnitude beyond any qty the
capital curve below ever actually produces (max 3 contracts, always — see §3). **By this
proxy, liquidity headroom is not the constraint that limits this engine at any account size
in the $2K-$50K range** — capital-cap and code-scaling constraints bind first, by a wide
margin (§3). This conclusion is bounded by the proxy's own limits (trade flow ≠ displayed
depth, and market impact of *our own* order is not modeled — see §6).

---

## 3. THE CAPITAL CURVE (task item 3 — headline deliverable)

Computed by applying each account's REAL sizing formula (`qty = min_contracts`, clamped by
`risk_gate.max_affordable_qty`, excluded entirely if even the floor is unaffordable — the
exact live code path, imported and reused, never re-derived) across the requested equity
grid, holding each trade's real historical entry premium fixed.

### Safe (per_trade_risk_cap_pct=0.30, min_contracts=3, V15_SAFE_TIERS)

| Equity | Strike tier | n included / blocked | Total P&L | $/trade | $/trading-day | $/calendar-day | Max affordable qty | **Utilization of headroom** | Binding constraint |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| $2,000 | ATM (matches pop.) | 172 / 19 | $4,844.18 | $28.16 | $34.36 | $12.52 | 5 | **60.0%** | risk_cap ($600) |
| $5,000 | ATM (matches pop.) | 191 / 0 | $3,845.77 | $20.13 | $27.27 | $9.94 | 12 | 25.0% | risk_cap ($1,500) |
| $10,000 | Slight ITM (⚠ not modeled) | 191 / 0 | $3,845.77 | $20.13 | $27.27 | $9.94 | 21 | 14.3% | max_premium_tier (25% < 30%, $2,500) |
| $25,000 | ITM-2 (⚠ not modeled) | 191 / 0 | $3,845.77 | $20.13 | $27.27 | $9.94 | 42 | 7.1% | max_premium_tier (20%, $5,000) |
| $50,000 | ITM-2 (⚠ not modeled) | 191 / 0 | $3,845.77 | $20.13 | $27.27 | $9.94 | 85 | **3.5%** | max_premium_tier (20%, $10,000) |

### Bold (per_trade_risk_cap_pct=0.50, min_contracts=5, V15_BOLD_CORE_TIERS, no tiered premium cap)

| Equity | Strike tier | n included / blocked | Total P&L | $/trade | $/trading-day | $/calendar-day |
|---:|---|---:|---:|---:|---:|---:|
| $2,000 | OTM-2 (⚠ not modeled) | 156 / 0 | $7,448.40 | $47.75 | $63.66 | $19.25 |
| $5,000 | OTM-2 (⚠ not modeled) | 156 / 0 | $7,448.40 | $47.75 | $63.66 | $19.25 |
| $10,000 | OTM-1 (⚠ not modeled) | 156 / 0 | $7,448.40 | $47.75 | $63.66 | $19.25 |
| $25,000 | ITM-2 (⚠ not modeled) | 156 / 0 | $7,448.40 | $47.75 | $63.66 | $19.25 |
| $50,000 | ITM-2 (⚠ not modeled) | 156 / 0 | $7,448.40 | $47.75 | $63.66 | $19.25 |

(Bold population: a fresh re-run this session of `bold_fullhist_replay.py`'s own already-
validated `replay_population` — walk_exit_manager-based, byte-exact against 7/7 real bold-2
fills — at current-live `block_elite_bull=True`, `min_contracts=5`. n=156, reproducing that
study's own published n exactly, a strong internal cross-check.)

**Reading the table straight:** every single row from $5,000 to $50,000 on Safe, and *every
row on the entire Bold grid*, is **byte-identical** in $/trade and $/day. This is not
rounding — it is because the live sizing formula literally never asks for more than
`min_contracts`, so nothing downstream of that changes as equity grows. The "Utilization of
headroom" column is the sharpest way to see it: at $2,000 the account is already using 60% of
what it could legally afford; by $50,000 that number has collapsed to **3.5%** — the account
got 25x bigger and the position size did not move at all.

**Caveats disclosed, not hidden:**
- *Safe* stays genuinely ATM (matching the population) through $5,000 — those two rows are
  fully trustworthy. $10,000+ rows hold the population's real ATM premiums fixed even though
  the live strike tier would actually shift to Slight-ITM/ITM-2 (higher real premiums,
  flagged `strike_tier_matches_population: false`) — not re-priced here (would need a fresh
  option-chain re-fetch and re-walk, outside this measurement-only lane). Directionally, a
  real ITM premium is higher, which cuts two ways not resolved by this analysis: bigger $
  swings per contract, but also a *tighter* dollar cap at those tiers (25%→20%, shrinking as
  equity grows) that could reintroduce deadlock risk instead of headroom.
- *Bold*'s own ATM strike tier only holds below $2,000 — **every single row in the Bold table
  is a sizing-only counterfactual** (today's real ATM premiums, resized under Bold's real
  qty/cap formula at a higher hypothetical equity), not a strike-tier-aware forecast. Treat
  the flatness of the Bold curve as the load-bearing finding; treat the absolute Bold dollar
  values at $10K+ as directional, not exact.
- Two known research artifacts (`min-contracts-bold-2026-08-02.json`,
  `bold-fullhist-replay-2026-08-01.json`) already independently found the identical mechanism
  for Bold specifically, at Bold's *actual* current equity ($1,197.52): min_contracts=5
  deadlocked 160 of 334 raw candidates (48%) there, and lowering the floor to 3 unlocked
  +83.3% more participation at a lower $/trade. This document generalizes that finding across
  the equity axis for both accounts, using pure arithmetic on top of the same validated
  primitives, rather than re-deriving it.
- **This capital curve is a scaling exercise, not a forecast that a $50K account would
  actually exist or behave this way** — see §6 for what is NOT modeled (market impact,
  compounding equity paths, real strike re-pricing).

---

## 4. The frequency term (task item 4)

At the flat live-faithful rate ($20.13/trade at $5K+ equity, $28.16/trade at $2K):

| Equity | Avg $/trade | Trades/active-day for $100/day | for $150/day | for $200/day | **Actual trades/active-day** |
|---:|---:|---:|---:|---:|---:|
| $2,000 | $28.16 | 3.55 | 5.33 | 7.10 | **1.22** |
| $5,000+ | $20.13 | 4.97 | 7.45 | 9.94 | **1.36** |

The engine would need to **3.6x to 7.3x its actual trade frequency** to hit $100-200/day at
this edge size, holding everything else fixed. Cross-referencing
`analysis/deep-research/REGIME-PARTICIPATION-2026-08-02.md` (full 389-day population): only
**36.5%** of days see an entry at all; of the days that don't, **42.4%** are `GATE_BLOCKED`
(a real trigger fired and a named filter vetoed it) and **20.6%** are `CORRECTLY_FLAT` (a
trigger fired but never reached the score≥8 qualifying bar) — only **0.5%** (2 of 389 days)
are genuine `NO_VOCABULARY` (zero triggers all session). **The ceiling on frequency is almost
entirely a selection/gate/scoring question, not a "no setups exist" question** — which means
raising trades/day competes directly with trade *quality*, the exact axis 12 pre-registered
attempts already tried and nulled this weekend. Frequency is not a free lever sitting next to
the capital lever; it is a harder, already-contested one.

---

## 5. The recency check (task item 5, J's dynamic-market rule — recency > aggregate)

Recomputed on the population's own newest 25 trading dates (2026-05-28 → 2026-07-21, 33
trades — reuses `regime_participation_study.recent_n_trading_days`, the standing repo
convention for "recent N," not a new ad-hoc window):

| | Recent 25 trading days | Full 391-day-window history |
|---|---:|---:|
| % return mean / median | +5.20% / -20.00% | +6.44% / -20.00% |
| % return p25 / p75 | -40.22% / +53.47% | -20.00% / +10.89% |
| Live-faithful n included / blocked | 27 / 6 | 159 / 32 |
| Live-faithful total P&L | $1,352.54 | $5,302.47 |
| Live-faithful $/trade | $50.09 | $33.35 |
| **$/trading-day (live-faithful)** | **$64.41** | **$44.19** |

**The recent window is genuinely better, not just noisier** — $/trading-day is 46% higher
recently than in the 18-month aggregate, and $/trade is also higher ($50.09 vs $33.35).
Per J's standing rule, this recent number is the one that should inform near-term planning.
It is still short of $100-200/day (by roughly 1.6x-3.1x), and n=33 trades over 25 days is a
thin base for a durability claim — reported honestly as encouraging-but-not-sufficient, not
inflated into a trend.

---

## 6. Honesty requirements

- **This is a Safe-shape simulation, not broker fills**, for the primary 191-trade
  population. Real Safe fills exist for a much shorter, more recent window: `journal/
  trades.csv`, `account_id=='safe'`, n=38, 2026-04-29→2026-07-28. Their raw % return
  distribution (mean +1.57%, median -9.02%) differs from the simulated population's (mean
  +6.44%, median -20.00%) — real trades show *smaller* median losses than the simulated
  -20% mechanical stop, likely reflecting manual management/partial exits the simulation's
  mechanical exit-walk does not model. Real total P&L is $1,228.00 over 38 trades ($32.32/
  trade raw) — close to this document's corrected $33.35/trade live-faithful figure, and a
  meaningfully better match than the original $25.18/trade published headline. On the 14
  distinct calendar days J actually traded Safe in that window, real fills averaged
  **$87.71/day** — the single closest number in this entire document to the $100-200 target.
  Treat it as the most encouraging data point and the least statistically reliable one at
  the same time: 14 days is not enough to know if that rate holds, and those were the days
  J chose to trade, not a random or complete sample of trading days.
- **Real fills vs. simulated, side by side** (full detail in the JSON): the simulated
  population's median loss sits exactly at the mechanical -20% stop; real fills' median
  loss (-9.0%) is shallower, consistent with active management cutting losers earlier than
  the mechanical exit would.
- **Market impact of our own order is NOT modeled anywhere in this document.** §2's
  liquidity read (no knee below ~qty 360-830) uses *historical* trade volume as a static
  backdrop; it says nothing about how OUR OWN order at that size would move the quote while
  being filled. This matters more as qty grows, and is a real, disclosed limit on how far
  the liquidity conclusion in §2 can be trusted at the very largest hypothetical sizes.
- **NBBO size data does not exist in this repo** (§2) — the liquidity read is the best
  available proxy, explicitly not a "SPY is liquid" hand-wave, but explicitly not proof of
  displayed depth either.
- **The capital curve (§3) holds strike/premium fixed at ATM prices for every equity row.**
  Real strike-tier changes at $10K+ (Safe) and $2K+ (Bold) are flagged per-row
  (`strike_tier_matches_population: false`) rather than silently ignored or fabricated via a
  re-priced guess.
- **The §0 qty-correction is itself new** — the published $4,808.75/191-trade/$25.18-per-
  trade headline, cited in CLAUDE.md and multiple other deep-research documents this
  weekend, has never before been checked against the real live sizing formula. This document
  is the first to do so for Safe (Bold's own equivalent gap was already caught and fixed by
  `bold_fullhist_replay.py` on 2026-08-01). The corrected numbers should be preferred over
  the original headline in any future document that cites this population's $/trade.

---

## 7. Guard tests (RED-proofed)

`backtest/tests/test_capital_efficiency_2026_08_03.py` — 42 tests over every new pure
function (`pct_return_on_capital`, `rescale_pnl_linear`, `percentile`, `distribution_stats`,
`split_by_outcome`, the liquidity-ratio functions, `order_clears_gate` / `capital_curve_row`'s
delegation to the already-tested `risk_gate.py`, `trades_per_day_for_target`,
`recent_n_trades`'s delegation to `regime_participation_study.py`). Includes a dedicated
`test_qty_invariance` pinning the load-bearing §0/§1 invariant (P&L linear in qty ⇒ % return
independent of historical qty).

RED-proofed live, this session: broke `rescale_pnl_linear` (returned `dollar_pnl` unscaled)
and `liquidity_knee_table` (inverted `>` to `<`) — 6 tests failed exactly as expected, both
mutations reverted, suite confirmed green again:

```
backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_capital_efficiency_2026_08_03.py -q
42 passed in 0.34s
```

---

## 8. The blunt answer

**What does this engine actually make, right now, at today's real equity?** Roughly
**$10-19/calendar-day, $27-64/trading-day, per account** — Safe at $1,746.75-equivalent
equity runs $12.52/calendar-day ($34.36/trading-day) on the live-faithful basis; Bold at its
ATM tier runs $19.25/calendar-day ($63.66/trading-day). Combined, call it **roughly
$30-50/calendar-day** most days, with the recent 25-day window running better (§5). None of
this is $100-200/day. **The target is not reachable at today's actual account sizes ($1,747
Safe / ~$1,200-1,633 Bold) under today's code**, and it should be reported as such rather
than rounded up.

**What would it take?** Two independent, non-exclusive levers, and this document's evidence
says they are not equally good:

1. **Fix the sizing-doesn't-scale bug.** The single highest-leverage, lowest-risk lever this
   document finds: `heartbeat_core.py`'s core-account sizing never grows qty with equity
   (§3) — it uses exactly `min_contracts` forever, leaving 96.5% of legal headroom unused at
   $50K. The fleet lane already has the fix built and running (`position_sizing_tiers` +
   `fleet_executor._qty_for`, base_qty scaling 5→8→15 by equity tier) — core simply never
   was wired to it. This is a mechanism gap, not a research question: no new edge, no new
   selection, no new gate — just spending the capital the account already legally has. Even
   a partial version (raising `min_contracts` in step with equity, the same shape fleet
   already uses) would move the $/trade number roughly linearly with qty, and the current
   $20-48/trade flat rate times even a modest 3-5x qty increase lands meaningfully closer to
   the $100-200/day range on the *existing* trading-day cadence — without touching selection
   at all. FOCUS-DOCTRINE's assumption that "scaling comes from compounding the tier" is
   currently **false** for the core accounts as wired; this is the fix that would make it
   true.
2. **Raise frequency.** Mechanically weaker and already contested: needs 3.6x-7.3x today's
   trade rate (§4), competes directly with selection quality (42.4% of blocked days are a
   *named filter* refusing a real trigger, not an absence of setups), and 12 pre-registered
   attempts to loosen selection this weekend already nulled. Not free, not fast, and this
   weekend's evidence says it is the harder of the two paths.

Neither lever is this document's to ship — this lane is measurement only. But if forced to
rank: **the sizing gap is the one already half-built, already validated elsewhere in this
repo, and directly explains why compounding the account "hasn't been working" — it structurally
cannot, yet, on the core path.**

---

_Sources: `analysis/recommendations/engine-fullhist-replay-2026-07-23.json` (Safe, 191
trades) · fresh `bold_fullhist_replay.replay_population()` re-run this session (Bold, 156
trades) · `automation/state/params.json` / `automation/state/aggressive/params.json` ·
`backtest/lib/risk_gate.py` (imported, not modified) · `backtest/data/options/*.csv` (OPRA
bar cache, 14,409 files) · `journal/trades.csv` · `analysis/recommendations/
min-contracts-bold-2026-08-02.json` · `analysis/deep-research/
REGIME-PARTICIPATION-2026-08-02.md` · `markdown/doctrine/FOCUS-DOCTRINE.md`._
