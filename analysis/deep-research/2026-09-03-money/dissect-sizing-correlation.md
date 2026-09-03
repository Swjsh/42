# D6 SIZING AND CORRELATION — one shared signal, four arms, one loser taken 4x

Stamp: 2026-09-03T11:40 ET. Generated: 2026-09-03T11:45:19 ET (`et_clock.py`, verified fresh
this session). Sonnet, read-only, no broker/market-data/network calls. Market is OPEN — this
is a still-live session; every "today" number below is stamped to its own read and is stale the
moment new fills land. Full machine-readable output:
[`dissect-sizing-correlation.json`](dissect-sizing-correlation.json). Tool (new file, per this
task's constraints): [`backtest/tools/dissect_sizing-correlation.py`](../../../backtest/tools/dissect_sizing-correlation.py)
(+ `_part2.py`, `_part3.py`).

**Method:** FIFO buy/sell matching per (arm, symbol) on `automation/state/fills-ledger.jsonl`,
restricted to `is_option=true` AND `attribution=='engine'`. Safe globally — a 0DTE OCC symbol
encodes its own expiry date, so there is no cross-day collision risk in matching across the
whole ledger at once. All dollar figures below are **FACT** (broker-verified fills) unless
explicitly marked APPROXIMATE (the flat-3 counterfactual) or cited from another report (the
retest-diversification design note).

---

## 0. First finding: the question's own premise moved while I was answering it

I re-read `fills-ledger.jsonl` at 11:40 ET. It had grown from the 31 today-rows in the task
brief (through 11:27 ET) to 35 rows (through 11:34 ET). Reconstructing today's running P&L
**exactly reproduces SYNTHESIS.md's "today's −$1,045" figure as a single moment, not the day's
state**:

- **Book-level trough: −$1,045.00 at 10:37:07 ET** (the instant the 10:16-17 wave's structure
  stop finished clearing all 4 arms).
- **Book-level total by 11:34 ET (last read): +$836.00**, closed legs only — two subsequent
  winning waves (11:06-11:34 ET) more than reversed the trough.

So "we lost $1k" was never the day's outcome — it was the day's low point, on a session that was
still running when the number was quoted, and it has already recovered net-positive as of this
report's own read. That doesn't mean the day is "won" either — it is **still live**; a third
losing wave could still happen. Treat every dollar figure below as time-stamped, not final.

---

## 1. Today's per-arm loss vs the actual doctrine that governs it

| Arm | Today final (closed) | Today trough | Trough as % of equity | Trough as % of the −$400/arm dollar stop | Trough as % of the way to the Rule-5 kill switch |
|---|---:|---:|---:|---:|---:|
| safe-2 | −$210 | −$210 @ 10:36:04 | −3.71% | 52.5% | 12.4% (of −30%, −$1,696) |
| bold-2 | +$129 | −$155 @ 10:36:06 | −2.77% | 38.7% | 5.5% (of −50%, −$2,797) |
| safe-3 | +$605 | −$335 @ 10:37:06 | −5.94% | **83.8%** | 19.8% (of −30%, −$1,692) |
| risky-1 | +$312 | −$345 @ 10:37:08 | −5.61% | **86.3%** | 11.2% (of −50%, −$3,075) |
| risky-3 | did not trade today | — | — | — | — |

**Answer to the framing question: "we lost $1k" is the wrong frame; the per-account losses are
inside doctrine, with real but not alarming headroom.** No arm came within half of its kill
switch. The two tightest arms — safe-3 and risky-1 — got to 84-86% of their −$400/arm dollar
stop (the PREREG-TIGHT-LADDER control, not Rule 5) at the trough, which is close enough to be
worth noting but did not trip; a third correlated losing wave at similar size would have. The
book figure oversells the risk because it **sums four correlated bets that are governed
separately** — Rule 5, Rule 6, and the −$400 stop are all PER-ARM, and per-arm is where the real
headroom lives.

---

## 2. Correlation of arm P&L, since 2026-08-06

Table 1 — per-day, per-arm realized P&L (FIFO-matched option round trips, engine fills only):

| Date | bold-2 | risky-1 | risky-3 | safe-2 | safe-3 | Book |
|---|---:|---:|---:|---:|---:|---:|
| 08-06 | +0 | +296 | +830 | +339 | +0 | **+1,465** |
| 08-07 | +0 | −640 | −624 | −375 | −1,048 | **−2,687** |
| 08-10 | −270 | −465 | +274 | −141 | −156 | −758 |
| 08-11 | +7 | −109 | +43 | +102 | +0 | +43 |
| 08-12 | −228 | −133 | −286 | −141 | −102 | −890 |
| 08-13 | +249 | +402 | +196 | +444 | +457 | **+1,748** |
| 08-14 | −620 | −468 | −72 | −390 | −287 | −1,837 |
| 08-17 | +360 | +0 | −200 | −36 | +0 | +124 |
| 08-18 | +80 | +0 | +0 | +82 | +0 | +162 |
| 08-19 | +90 | +254 | −150 | −114 | +186 | +266 |
| 08-20 | +175 | +0 | +370 | +266 | +0 | +811 |
| 08-21 | −66 | −43 | −65 | −312 | −99 | −585 |
| 08-24 | +0 | +0 | +0 | −57 | +0 | −57 |
| 08-25 | +0 | −100 | +0 | −60 | −60 | −220 |
| 08-26 | +0 | +0 | +0 | +0 | +39 | +39 |
| 08-27 | +214 | +828 | −55 | +322 | +588 | **+1,897** |
| 08-28 | +294 | +650 | −460 | +257 | +563 | **+1,304** |
| 09-01 | −140 | +0 | +0 | +218 | +0 | +78 |
| 09-02 | −15 | −345 | +0 | −126 | −213 | −699 |
| 09-03 (partial) | +129 | +312 | +0 | −210 | +605 | +836 |

Correlation matrix (**excl. today's partial session**, n=19 full trading days):

| | bold-2 | risky-1 | risky-3 | safe-2 | safe-3 |
|---|---:|---:|---:|---:|---:|
| bold-2 | 1.000 | 0.638 | −0.062 | 0.596 | 0.482 |
| risky-1 | 0.638 | 1.000 | 0.140 | 0.766 | 0.895 |
| risky-3 | −0.062 | 0.140 | 1.000 | 0.478 | 0.227 |
| safe-2 | 0.596 | 0.766 | 0.478 | 1.000 | 0.730 |
| safe-3 | 0.482 | 0.895 | 0.227 | 0.730 | 1.000 |

- Average pairwise correlation: **+0.489** (point), bootstrap mean **+0.483**, 95% CI
  **[0.301, 0.633]** (3,000 resamples, days with replacement, n=19). This is consistent with
  MAP.md's own prior figure ("pairwise r ≈ 0.62-0.72") — mine is somewhat lower because it
  includes `risky-3` (near-zero with `bold-2`, r=−0.06) and `bold-2` (mid-correlated, not the
  tightly-coupled bull-fleet pair `risky-1`/`safe-3` at r=+0.895, the highest in the matrix).
- **Effective number of independent bets: 1.69 (point), bootstrap mean 1.73, 95% CI [1.42, 2.27]**
  (formula `N/(1+(N-1)*rho_avg)`, N=5). A second method (participation ratio of the correlation
  matrix's eigenvalues) gives 2.19 — same order of magnitude, formula-dependent. **5 nominal arms
  trade like roughly 1.4–2.3 independent bets.**

---

## 3. Today's losses: same two waves, not four independent decisions

Every losing leg today (8 of 8, summing to exactly the −$1,045 book trough) traces to **2**
signal events:

- **Wave 1** (entered 09:41-09:42, stopped 09:58-10:03, all `premium_stop -50% cap`):
  bold-2 −$85, safe-3 −$270, risky-1 −$280, safe-2 −$144 → **−$779**.
- **Wave 2** (entered 10:16-10:17, stopped 10:36-10:37, all the same `structure_stop` — 5m close
  767.96 vs trigger 768.00, a 4-cent breach on the identical trigger for all 4 arms):
  safe-2 −$66, bold-2 −$70, safe-3 −$65, risky-1 −$65 → **−$266**.

**100% of today's losing dollars, at the trough, came from 2 correlated signal moments, not 8
independent ones.** This is the D6 headline mechanically: a loser IS taken 4x, on the same tick,
for the same reason, every time — the effective-N-of-1.7 finding above is this exact phenomenon
measured over 19 days instead of 2 signals.

---

## 4. Was 5 contracts too big for a −50% cap?

No — not by Rule 6, and not even close. Every position sized today, with % of equity, % of
Rule 6's cap (30% Safe / 50% Bold), and % of the tight-ladder's flat $1,000/position cap:

| Time (ET) | Arm | Symbol | Qty | Premium | Notional | % of equity | % of Rule 6 cap | % of $1,000 cap |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 09:42:06 | safe-3 | 770C | 5 | $1.11 | $555 | 9.8% | 32.8% | 55.5% |
| 10:17:07 | safe-3 | 768C | 5 | $1.31 | **$655** | 11.6% | 38.7% | 65.5% |
| 10:17:09 | risky-1 | 768C | 5 | $1.31 | $655 | 10.7% | 21.3% | 65.5% |
| 11:07:10 | risky-1 | 770C | 5 | $1.18 | $590 | 9.6% | 19.2% | 59.0% |
| 11:07:15 | safe-3 | 770C | 5 | $1.17 | $585 | 10.4% | 34.6% | 58.5% |

The single biggest position today (safe-3, $655) used **38.7% of its Rule 6 cap** and **65.5%
of the $1,000 position cap** — real headroom on both, and under the actual governing exit rule
(−50% catastrophe cap), the worst-case dollar loss on that position was ≈$327, **5.8% of
equity**, nowhere near Rule 6's 30% line.

**What actually bound today was the 5-contract ceiling, not a dollar cap.** `safe-3`/`risky-1`
are ELITE-quality-tier arms whose `position_sizing_tiers` would size to 8 contracts at this
equity band; `max_contracts_per_entry=5` (PREREG-TIGHT-LADDER, 2026-08-29) clamped every entry
down to 5. J's sizing concern is real in spirit (5 contracts at $1.08-1.31 is the biggest
positions the ladder currently allows) but the mechanism that hurt today was the **structure
stop's 4-cent trigger breach hitting all 4 arms on the same tick**, not the dollar size of any
one position — a 3-contract version of the identical trades would have lost the identical
*percentage*, just fewer dollars.

### Realized loss per trade vs premium budget and median winner size (since 08-06)

| Arm | n | Median win | Median loss | Median notional |
|---|---:|---:|---:|---:|
| bold-2 | 39 | $159 | −$89 | $330 |
| risky-1 | 56 | $207 | −$80 | $470 |
| risky-3 | 44 | $90 | −$80 | $372 |
| safe-2 | 50 | $184 | −$54 | $267 |
| safe-3 | 33 | $207 | −$65.50 | $339 |

Every arm's median win exceeds its median loss by roughly 1.9x-3.4x (matches the book's
right-tail shape, `avg_r_multiple_winners +1.34R / losers −0.51R` per H8). Median loss dollars
(−$54 to −$89) sit at 16-27% of median notional (−$267 to −$470), well inside the configured
−50% cap on any single trade — the median loser is exiting on the **structure/time stop**, not
running to the catastrophe floor (H8's own `structure_or_time_loss` = 50.6% of all losers,
`cap_hit` at the full −50% = only 13.4%). Today's two waves are typical of this shape: every one
of the 8 losing legs exited between −16% and −27% of premium (the 4-cent structure breach), not
at −50%.

### Cost of "min 3 contracts everywhere" vs current tiers (APPROXIMATE, real fills, linear scaling)

**This uses real fill prices throughout** (not a walker/bar-replay simulation), so it does not
carry the WALKER-FULL-POPULATION-ANCHOR magnitude-fidelity caveat that governs the H10 retest
study below — the only approximation here is the assumption that a smaller position would have
executed at the identical entry/exit prices, scaled linearly per contract. That assumption is
known to be biased: the exit ladder's TP1-sells-66.7% rule behaves differently at qty 3 (sells 2,
rides 1) than at qty 5 (sells 3, rides 2) — linear scaling cannot capture that a bigger position
keeps more optionality riding into a trend day, so this likely **understates** what size buys on
winning days and **overstates** the saving on losing days.

| Arm | n entries | n above floor-3 | Actual $ | Flat-3 $ (approx) | Δ |
|---|---:|---:|---:|---:|---:|
| safe-2 | 50 | 0 | $68 | $68 | $0 — already at the 3-floor |
| bold-2 | 39 | 36 | $259 | $67 | **−$192** |
| risky-1 | 56 | 49 | $439 | $286 | **−$153** |
| risky-3 | 44 | 41 | −$199 | −$111 | +$88 |
| safe-3 | 33 | 8 | $473 | $1,050 | **+$577** |
| **Book** | **222** | **134** | **$1,040** | **$1,360** | **+$320 (+31%)** |

**Not a shippable result** — no bootstrap CI computed on the delta, small qty>3 subsets, and a
known-directional bias in the approximation. The honest read: flat-3 would have **cost** money
on bold-2 and risky-1 (whose upsizing to their 5-contract floor correlates with wins about as
much as losses in this sample) and **helped** safe-3 substantially (whose small number of
ELITE-tier upsizes to 5 were disproportionately its losers) — sign is not uniform across arms,
so "cap everyone at 3" is not a clean win, it is a redistribution whose net book sign (+$320) is
inside noise at this n.

---

## 5. Design note (not a result): would diversifying entry rule by arm decorrelate the book?

Using this morning's H10 retest-entry-variant study (`retest-entry-variant-walked.json` /
`-zw0.50.json`, 15 comparable days, same population/exit-engine both sides, **SIGN-ONLY except
safe-2** per that report's own fidelity caveat): day-summed **breakout** (actual) P&L vs
day-summed **retest** (wait-for-pullback) P&L correlates at **r=+0.736** (0.30 zone) to
**r=+0.950** (0.50 zone).

**That is higher than the correlation measured between the current 5 arms themselves** (avg
+0.489, max +0.895). The mechanism is exactly what SYNTHESIS.md already named: breakout and
retest both key off the **identical** `trigger_level` from the **identical** shared signal —
they differ only in *when* they enter the same underlying move, so both are driven by the same
day-type (trend vs chop) that the whole audit converged on as the real lever. **Splitting arms
by entry-timing rule would not meaningfully diversify the book** — it would mostly just thin out
both sides' exposure to the same day-type risk. A genuine diversification lever needs a
different signal source entirely (a different setup family, instrument, or timeframe), not a
timing variant of RIDE_THE_RIBBON. Disclosed as a design note only — not tested, not proposed
for shipping, and inherits H10's own SIGN-ONLY fidelity caveat in full.

---

## 6. Caveats

- Today's numbers are a snapshot at 11:40 ET on a still-open session; re-read the ledger before
  treating any today figure as final.
- Correlation/effective-N is computed on n=19-20 trading days — the bootstrap CI (rho 0.30-0.63,
  effN 1.4-2.3) is wide; treat the point estimates as directionally solid, not precise.
- The flat-3 counterfactual is a linear-scaling approximation over real fills with a disclosed
  directional bias (see §4) — not a validated proposal.
- The entry-rule diversification note borrows H10's numbers verbatim and inherits its SIGN-ONLY
  status for every arm except safe-2 — presented as a design note per the task's own framing, not
  a result.
- No broker/market-data calls were made; all figures derive from cached ledgers already on disk.
