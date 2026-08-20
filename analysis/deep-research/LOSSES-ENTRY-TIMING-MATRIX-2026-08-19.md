# Entry timing and the size of our losses — the full matrix

> Lane: SMALLER LOSSES / entry timing. Built `2026-08-20 00:30 ET`.
> Dataset: [`analysis/recommendations/trade-matrix.json`](../recommendations/trade-matrix.json) —
> 303 closed round trips, 35 trading days (2026-06-26 → 2026-08-19), 5 arms.
> Scope: **analysis and proposal only.** Nothing armed, no params touched, no orders.

---

## VERDICT — **NO EDGE.** Entry timing is not the lever, and the pullback rule is the wrong sign.

Three findings, in order of how much they should change what we do:

1. **The pullback-entry rule loses money in every window and at every threshold tested.**
   All 30 "require a retrace before entering" cells are negative against the random-block null;
   the tightest ones are significantly *worse* than random (z = −3.3). Waiting for a pullback in a
   0DTE trend means you buy **1.044× the price, a median 1 minute later, with less time left** —
   you skip the moves that pay and take the ones that stall. This is not a knob to tune. It is a
   sign error.

2. **"Entering into extended moves" does not systematically lose — at 10 and 20 minutes it is
   where all of the money is.** Wave-level quintiles of the prior-20-minute impulse: the two most
   extended quintiles are the only profitable ones (+$3,612 and +$802 gross); the least extended is
   −$1,925. The lane's hypothesis is **falsified at the horizon that matters**. Only the immediate
   5-minute chase tilts negative, and it flips sign at 10 minutes — so it is noise, not mechanism.

3. **The one cell that looked good is a losing-book artifact plus one bad day.** `block imp5 ≥ 0.20`
   shows +$5,061 gross. 47% of that is a single day (2026-08-07) on which the gate blocks **all 12
   trades, not a selection**. Its excess over the random-block null is z = 1.57, p = 0.054 — the best
   of 78 cells, i.e. exactly what you expect from 78 draws. And it is **negative in the first half of
   the sample** (excess −$383) with the entire effect in the second half.

**No cell in this matrix is proposed for arming.** The recommendation at the bottom is a
pre-registered *shadow* hypothesis with a kill criterion, and it points the opposite way from the
lane's premise.

---

## 0. The methodological trap that decides this whole lane

The book is **net negative**. Therefore *any* gate that blocks trades "improves" P&L for free:

```
mean per-trade gross = -$1,805 / 303 = -$5.96
blocking K trades at random is worth +$5.96 x K, for nothing
```

Half the cells below look profitable purely because of this. Every cell is therefore reported with
a **random-block null**, permuted at **wave level** (the 5 arms trade one shared signal, so trades
inside a wave are the same decision), 4,000 draws:

```
excess = actual delta  -  what blocking that many random waves gives
```

A cell with a big `dGross` and a small `excess` has found nothing. **Read the `excess` and `p`
columns, not the `dGross` column.**

### Production baseline

| | gross | net of real fees | net of fees + measured exit slippage |
|---|---:|---:|---:|
| **303 round trips** | **−$1,805** | **−$1,940** | **−$3,801** |

Win rate 23.1% by trade. Winner dollars $15,684 (70 winners) · loser dollars −$17,489 · average loss
−$75 · worst loss −$664 · max drawdown (realisation order, after costs) −$6,144.

Exit slippage is computed **per exit leg** from that leg's own traded range
(0.129 × range × 100 × qty, per [`COST-REALISM-2026-08-18`](COST-REALISM-2026-08-18.md)), not from
the book-wide median. That gives **$1,861** total versus the ~$895 the median-based estimate implies —
because exit qty and range are both right-skewed, and the median understates the sum. Both figures
are stated; the per-leg one is used here.

**PRODUCTION CELL: no entry-timing gate at all.** The engine enters the instant the signal releases
(ribbon spread expanding past 30¢), regardless of how far SPY has already run. There is no
impulse test, no extension test, and no pullback requirement anywhere in the entry path.

### Independence

| clustering | count |
|---|---:|
| raw round trips | 303 |
| distinct trading days | 35 |
| distinct (date, direction) | 49 |
| waves @ 5-min | 120 |
| waves @ 15-min | 104 |
| **waves @ 30-min (used as n_effective)** | **92** |

303 is never quoted as a sample size. All permutation tests resample **waves**, not trades.

---

## 1. MATRIX 1 — descriptive: how extended was the move, and did it matter?

**Wave-level quintiles** (120 waves, so one signal = one row's worth of evidence):

### Prior-20-minute impulse — *more extended is BETTER*

| quintile | impulse range (pts, direction-signed) | waves | gross $ | after costs $ | winning waves |
|---|---|---:|---:|---:|---:|
| Q1 (fading / against) | [−1.45, −0.31] | 24 | −1,925 | −2,316 | 4 |
| Q2 | [−0.31, +0.30] | 24 | −2,674 | −3,069 | 6 |
| Q3 | [+0.30, +0.58] | 24 | −1,620 | −2,053 | 7 |
| Q4 | [+0.58, +1.02] | 24 | **+802** | +539 | 4 |
| **Q5 (most extended)** | **[+1.13, +2.93]** | 24 | **+3,612** | **+3,098** | 6 |

### Prior-10-minute impulse — same direction

| quintile | range | waves | gross $ | after costs $ |
|---|---|---:|---:|---:|
| Q1 | [−1.54, +0.03] | 24 | −1,681 | −2,021 |
| Q2 | [+0.03, +0.27] | 24 | −3,492 | −3,923 |
| Q3 | [+0.29, +0.46] | 24 | −1,951 | −2,293 |
| **Q4** | [+0.46, +0.73] | 24 | **+3,988** | **+3,479** |
| **Q5** | [+0.75, +2.22] | 24 | **+1,331** | +956 |

### Prior-5-minute impulse — the only window with the hypothesised sign, and it is non-monotone

| quintile | range | waves | gross $ | after costs $ |
|---|---|---:|---:|---:|
| Q1 | [−1.02, −0.27] | 24 | −1,184 | −1,459 |
| Q2 | [−0.25, +0.03] | 24 | −668 | −922 |
| **Q3 (flat)** | [+0.03, +0.19] | 24 | **+2,927** | **+2,458** |
| Q4 | [+0.21, +0.36] | 24 | −266 | −906 |
| Q5 (chase) | [+0.37, +1.57] | 24 | **−2,614** | −2,973 |

Q1 (fading a move) is *also* negative. The shape is "flat is good, motion in either direction is
bad" — not "chasing is bad". And it inverts at 10 minutes. **Correlations across every feature and
horizon are |r| ≤ 0.18**; the strongest are *positive* (imp20 vs $ net: r = +0.169), i.e. more
extension → better outcome.

### Retrace position at entry (0.00 = bought the exact extreme of the prior swing)

| ret10 bucket | n | WR% | gross $ | after costs $ | avg loss |
|---|---:|---:|---:|---:|---:|
| [−inf, 0.00) — *above everything in the window* | 3 | 0.0 | −206 | −223 | −69 |
| **[0.00, 0.15) — bought at the extreme** | 49 | **40.8** | **+4,511** | **+4,176** | −66 |
| [0.15, 0.30) | 106 | 17.0 | −3,642 | −4,255 | −78 |
| [0.30, 0.50) | 100 | 19.0 | −2,333 | −2,975 | −69 |
| [0.50, inf) — *waited for a deep pullback* | 45 | 28.9 | −135 | −525 | **−91** |

**Buying nearest the extreme is the best bucket on every metric that matters** — highest win rate,
the only strongly positive P&L, and the *smallest* average loss. Buying after a deep pullback has the
**largest** average loss (−$91). This is the lane's hypothesis inverted on its own chosen metric.

---

## 2. MATRIX 2 — chase block, null-controlled

Rule: skip the trade when SPY has already run ≥ T points in our direction over the prior N closed
1-minute bars. Decidable at the entry instant; uses no bar that had not closed.

`splitW` = waves the gate cut in half (a gate that takes one arm and blocks another on the *same*
decision is riding within-wave noise).

### N = 5 minutes — the only family with positive excess

| cell | blocked | dGross | dReal | null µ | **excess** | z | p | splitW |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **production (no gate)** | 0 | +0 | +0 | 0 | 0 | — | — | — |
| block imp5 ≥ 0.20 | 128 | +5,061 | +5,957 | +759 | **+4,302** | 1.57 | **0.054** | 16 |
| block imp5 ≥ 0.30 | 91 | +3,611 | +4,285 | +506 | +3,105 | 1.24 | 0.110 | 16 |
| block imp5 ≥ 0.40 | 64 | +1,920 | +2,441 | +334 | +1,586 | 0.71 | 0.254 | 15 |
| block imp5 ≥ 0.50 | 40 | +1,643 | +1,995 | +196 | +1,447 | 0.78 | 0.230 | 13 |
| block imp5 ≥ 0.60 | 29 | +740 | +971 | +155 | +585 | 0.36 | 0.396 | 7 |
| block imp5 ≥ 0.80 | 9 | +682 | +773 | +37 | +645 | 0.65 | 0.205 | 2 |
| block imp5 ≥ 1.00 | 6 | +317 | +345 | +39 | +278 | 0.33 | 0.353 | 0 |
| block imp5 ≥ 1.25 | 3 | +88 | +98 | +17 | +71 | 0.11 | 0.519 | 0 |

### N = 10 minutes — the SAME rule, one horizon out, sign fully reversed

| cell | blocked | dGross | dReal | null µ | **excess** | z | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| block imp10 ≥ 0.20 | 211 | −1,949 | −479 | +1,274 | **−3,223** | −1.29 | 0.902 |
| block imp10 ≥ 0.30 | 187 | −3,352 | −2,005 | +1,098 | −4,450 | −1.68 | 0.955 |
| block imp10 ≥ 0.40 | 137 | −4,705 | −3,731 | +813 | −5,518 | −2.01 | 0.979 |
| block imp10 ≥ 0.50 | 117 | −5,506 | −4,677 | +681 | −6,187 | −2.30 | 0.991 |
| **block imp10 ≥ 0.60** | 98 | **−5,975** | −5,268 | +553 | **−6,528** | **−2.55** | 0.996 |
| block imp10 ≥ 0.80 | 59 | −892 | −493 | +318 | −1,210 | −0.55 | 0.717 |
| block imp10 ≥ 1.00 | 36 | −0 | +235 | +167 | −167 | −0.09 | 0.576 |
| block imp10 ≥ 1.25 | 24 | +1,242 | +1,360 | +144 | +1,098 | 0.74 | 0.238 |

### N = 15 / 20 / 30 minutes — all negative in the band where a chase filter would bite

| cell | blocked | dGross | dReal | excess | z | p |
|---|---:|---:|---:|---:|---:|---:|
| block imp15 ≥ 0.20 | 187 | −4,288 | −3,111 | −5,386 | −2.04 | 0.982 |
| block imp15 ≥ 0.50 | 143 | −3,816 | −2,922 | −4,680 | −1.70 | 0.955 |
| block imp15 ≥ 1.25 | 25 | +1,834 | +2,028 | +1,682 | 1.11 | 0.113 |
| block imp20 ≥ 0.20 | 200 | −4,035 | −2,716 | −5,248 | −2.03 | 0.985 |
| block imp20 ≥ 0.50 | 149 | −3,499 | −2,536 | −4,382 | −1.60 | 0.941 |
| block imp20 ≥ 1.25 | 47 | −992 | −635 | −1,245 | −0.63 | 0.742 |
| block imp30 ≥ 0.20 | 205 | −2,494 | −1,179 | −3,727 | −1.46 | 0.931 |
| block imp30 ≥ 0.50 | 154 | −2,249 | −1,233 | −3,165 | −1.15 | 0.876 |
| block imp30 ≥ 1.25 | 81 | −1,271 | −689 | −1,715 | −0.70 | 0.759 |

(N = 3 minutes: all cells excess +$576…+$1,776, z ≤ 0.80, p ≥ 0.22 — nothing, and it splits up to
21 of 120 waves.)

**A gate whose sign reverses between a 5-minute and a 10-minute lookback is not measuring a
mechanism.** Best of 78 cells at p = 0.054 is, with 78 tests, the expected best draw from noise.

---

## 3. MATRIX 3 — require a pullback (J's rule as a filter)

Rule: skip unless price has *already* retraced ≥ X of the prior-W-minute swing at the entry instant.

| cell | blocked | dGross | dReal | null µ | **excess** | z | p | winner $ refused | winners blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| require ret10 ≥ 0.10 | 33 | −5,442 | −5,193 | +161 | **−5,603** | **−3.29** | 0.997 | 6,276 | 17 |
| require ret10 ≥ 0.15 | 52 | −4,305 | −3,953 | +270 | −4,575 | −2.20 | 0.981 | 6,426 | 20 |
| require ret10 ≥ 0.20 | 88 | −3,113 | −2,554 | +490 | −3,603 | −1.45 | 0.924 | 7,354 | 24 |
| require ret10 ≥ 0.25 | 127 | −1,185 | −379 | +753 | −1,938 | −0.70 | 0.757 | 9,031 | 30 |
| require ret10 ≥ 0.33 | 172 | −530 | +515 | +1,016 | −1,546 | −0.57 | 0.709 | 10,178 | 42 |
| require ret10 ≥ 0.50 | 258 | +1,670 | +3,277 | +1,540 | **+130** | 0.07 | 0.447 | 12,922 | 57 |
| require ret15 ≥ 0.10 | 40 | −4,989 | −4,700 | +196 | −5,185 | −2.80 | 0.995 | 6,096 | 17 |
| require ret15 ≥ 0.20 | 99 | −3,762 | −3,191 | +559 | −4,321 | −1.69 | 0.950 | 7,639 | 29 |
| require ret20 ≥ 0.10 | 47 | −4,706 | −4,382 | +253 | −4,959 | −2.50 | 0.990 | 6,105 | 18 |
| require ret20 ≥ 0.20 | 113 | −1,672 | −1,048 | +656 | −2,328 | −0.87 | 0.804 | 6,712 | 26 |
| require ret30 ≥ 0.10 | 50 | −4,772 | −4,430 | +262 | −5,034 | −2.47 | 0.989 | 6,351 | 21 |
| require ret30 ≥ 0.20 | 140 | −1,372 | −573 | +857 | −2,229 | −0.81 | 0.788 | 7,071 | 34 |
| require ret5 ≥ 0.10 | 31 | −2,135 | −1,929 | +155 | −2,290 | −1.39 | 0.905 | 3,048 | 12 |
| require ret5 ≥ 0.20 | 62 | −580 | −242 | +331 | −911 | −0.41 | 0.666 | 3,293 | 17 |

**Every one of the 30 cells is negative on excess.** Five are significantly worse than blocking the
same number of waves at random. The single cell with a positive raw `dReal` (+$3,277, `ret10 ≥ 0.50`)
has an excess of **+$130 (z = 0.07)** — it blocks 258 of 303 trades and its entire apparent gain is
the free money from a losing book. It also refuses **$12,922 of the $15,684 in winner dollars**, i.e.
82% of everything the strategy has ever earned.

---

## 4. MATRIX 4 — the deferred pullback entry (waiting, not skipping)

The rule as J actually described it: the signal fires, **do not buy**, watch minute by minute, buy
when SPY has retraced ≥ X of the prior-W-minute swing, at that bar's close + the measured $0.03/ctr
cross-buffer. If the retrace never arrives within M minutes, no trade.

**Stated limitation, not buried:** the option's minute bars only exist between the *actual* entry and
the *actual* exit. Where the retrace triggers after the real position was already closed, the
deferred entry cannot be priced. Those rows are carried at their **production** result — never zeroed,
never dropped. Coverage is reported per cell. This variant also holds the exit at the actual exit
timestamp and price, which is **generous to the rule**: it lets the deferred trade skip the stop-out
that the real trade suffered.

| cell | triggered | never | unpriceable | cov% | gross $ | Δgross | after costs $ | Δafter | WR% | avg loss | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **production** | — | — | — | 100 | −1,805 | — | −3,801 | — | **23.1** | −75 | −664 |
| W10 ret≥0.15 wait10 | 293 | 0 | 10 | 97 | −1,986 | −181 | −3,982 | −181 | 26.1 | −75 | −824 |
| W10 ret≥0.25 wait10 | 271 | 15 | 17 | 94 | −2,523 | −718 | −4,407 | −606 | 24.3 | −69 | −824 |
| W10 ret≥0.25 wait20 | 284 | 1 | 18 | 94 | −3,157 | −1,352 | −5,144 | −1,343 | 26.2 | −77 | −824 |
| W10 ret≥0.33 wait10 | 261 | 19 | 23 | 92 | −2,085 | −280 | −3,952 | −151 | 24.3 | −68 | −856 |
| W10 ret≥0.50 wait10 | 206 | 56 | 41 | 86 | −3,731 | −1,926 | −5,275 | −1,474 | 25.1 | −61 | −492 |
| W10 ret≥0.50 wait20 | 223 | 26 | 54 | 82 | −7,100 | −5,295 | −8,826 | −5,025 | 24.9 | −73 | −1,128 |
| **W20 ret≥0.15 wait20** | 288 | 1 | 14 | 95 | −2,074 | **−269** | −4,061 | −260 | **29.1** | −77 | −824 |
| W20 ret≥0.25 wait10 | 260 | 23 | 20 | 93 | −1,751 | **+54** | −3,602 | **+199** | 28.6 | −73 | −856 |
| W20 ret≥0.25 wait20 | 273 | 10 | 20 | 93 | −2,508 | −703 | −4,424 | −623 | 28.3 | −75 | −856 |
| W20 ret≥0.33 wait10 | 206 | 60 | 37 | 88 | −5,553 | −3,748 | −7,077 | −3,276 | 22.2 | −64 | −492 |
| W20 ret≥0.50 wait20 | 144 | 64 | 95 | 69 | −8,247 | −6,442 | −9,698 | −5,897 | 16.7 | −67 | −492 |

**15 of 16 cells lose money.** The single positive cell is +$54 gross / +$199 after costs — a
rounding error on a −$1,805 book.

### The trap, caught red-handed

`W20 ret≥0.15 wait20` raises win rate from **23.1% → 29.1%** — a 6.0-point improvement, the single
best win-rate number anywhere in this document — while making the book **$269 worse gross and $260
worse after costs**. Per the standing rule: *a change that improves win rate while reducing net P&L
is a FAILURE.* It is a failure. So is `W10 ret≥0.25 wait20` (WR 26.2%, −$1,343 after costs).

Note also that **worst loss gets worse**, not better: −$824, −$856, −$1,128 against production's
−$664. Deferring entry does not shrink the tail. It moves it.

### Why it loses — the mechanism, measured

For `W20 / retrace ≥ 0.25 / wait ≤ 10 min` (evaluable on 260 of 303 trades):

| | |
|---|---:|
| median wait until the retrace triggers | **1 minute** |
| deferred entry **cheaper** than production | 123 (47%) |
| deferred entry **more expensive** | 137 (53%) |
| p25 / p50 / p75 deferred ÷ production entry premium | 0.923× / 1.000× / 1.094× |
| **mean ratio** | **1.044×** |

In a 0DTE trend the pullback you are waiting for arrives **fast and shallow or not at all**. The
median wait is one minute — long enough to pay theta and re-cross the spread, not long enough to get
a better price. On average you pay **4.4% more premium** for a later entry with less time on it. That
is the whole mechanism, and it is why every cell in Matrices 3 and 4 points the same way.

---

## 5. Forensics on the best cell — `block imp5 ≥ 0.20`

Reported in full because it is the only cell anyone will be tempted by.

**Headline:** blocks 128 of 303 trades · dGross **+$5,061** · dAfterCosts **+$5,957** · WR 23.1% → 28.0%
· avg loss −$75 → −$52 · max DD −$6,144 → −$3,208.

### Concentration — the effect is two days

| day | contribution (after costs) | share of effect |
|---|---:|---:|
| **2026-08-07** | **+$2,774** | **47%** |
| 2026-08-05 | +$1,958 | 33% |
| 2026-08-13 | −$1,741 | −29% |
| 2026-08-14 | +$776 | 13% |
| 2026-07-27 | +$630 | 11% |
| top-3 days combined | | **50%** |
| top single trade (risky-3 2026-08-05) | +$675 | 11% |

On **2026-08-07 the gate blocks all 12 of the day's trades** — it does not separate good from bad, it
happens to sit on the wrong side of a day where every entry lost. That is a day-level coincidence
wearing a trade-level filter's clothes.

### Split-sample — the effect does not exist in the first half

| window | n | blocked | dGross | dAfterCosts | null µ | **excess** |
|---|---:|---:|---:|---:|---:|---:|
| first half (to 2026-07-27) | 117 | 47 | +291 | +496 | +674 | **−383** |
| second half | 186 | 81 | +4,770 | +5,460 | +56 | **+4,714** |

The gate is **worse than random** in the first half of its own sample. There is no out-of-sample
window left to test it on.

### What it does to the winners

| | count | dollars |
|---|---:|---:|
| production winners | 70 | $15,684 |
| winners kept | 49 | $9,849 |
| **winners refused** | **21** | **−$5,835** |

It throws away **37% of every winning dollar the book has ever made**, including the #4 largest
winner (risky-1 2026-08-04, +$640, imp5 = +0.68 → BLOCKED). In a right-tail book where the top 5
trades are ~48% of winner dollars, a gate that refuses 21 winners is one bad draw away from
destroying the strategy.

### Leave-one-day-out and per-arm

LOO never turns the cell negative (0/35), but that is weak evidence — dropping 2026-08-07 alone cuts
it from +$5,957 to +$3,183. Per-arm excess is positive in all 5 arms (+$474 … +$1,621), which reads
like five confirmations and **is one**: the arms trade one shared signal at r = 0.846 / 95.7% sign
agreement. It is a single result restated five times.

Finally, the gate **splits 16 of 120 waves** — taking one arm and blocking another on the same
decision, minutes apart. A rule that disagrees with itself inside one signal is reading noise.

---

## 6. Data defect found and worked around (reported, not silently patched)

`backtest/data/spy_sip_cache/spy_1m_2026-08-07.json` is **truncated at 12:01 ET** — 439 bars instead
of ~900, missing 238 RTH minutes. Cause: `entry_quality_ledger.py::_fetch_sip_range` clamps `end` to
*now − 16 min* for the Basic-plan SIP delay, and `load_bars` treats **cache existence** as cache
validity — so a day fetched intraday is frozen mid-session forever.

This is not cosmetic for this study: **8 round trips on that day** (including −$488, −$384, −$305)
would have been feature-less, and 2026-08-07 turns out to carry 47% of the best cell's entire effect.
Silently dropping them would have inverted the headline.

Handled by refetching the full session to the scratchpad and overriding the cache **read-only**. The
shared cache file was **not** modified — other sessions are live and it is a shared surface. Any other
consumer of that file is currently reading a half-day. Recommended fix, out of scope here: have
`load_bars` validate that a cached RTH day reaches 15:59 before accepting it.

---

## 7. Pre-registered hypothesis (SHADOW ONLY — nothing armed)

The matrix does not support an entry-timing gate. It does support the **opposite** claim, which is
worth a shadow clock precisely because it contradicts the lane's premise:

> **PREREG-ENTRY-EXTENSION-INVERSION-2026-08-19.**
> Hypothesis: entries taken when SPY has *already* run **≥ +0.58 pts in the trade's direction over
> the prior 20 closed 1-minute bars** (wave quintiles Q4–Q5) out-perform entries taken below that
> threshold. Measured on **waves**, not trades. In-sample: Q4+Q5 = +$4,414 gross over 48 waves;
> Q1–Q3 = −$6,219 over 72 waves.
> Log-only, no gating. Shadow-record the flag on every future entry; grade forward.

**KILL CRITERION (frozen now):** kill the hypothesis if, after **40 forward waves**, the Q4/Q5 group's
mean per-wave gross P&L does not exceed the Q1–Q3 group's by at least **$50/wave**, OR if the
forward-period sign disagrees with in-sample, OR if any single day contributes **> 35%** of the
forward spread. Any one of the three ends it.

**And the standing kill for this lane, also frozen:** `block imp5 ≥ 0.20` is **not** to be armed, and
is dead unless it independently clears (a) excess over the wave-permutation null at **p < 0.01**, and
(b) a positive excess in **both** sample halves. It currently fails both.

---

## 8. Limitations

- **n_effective = 92**, not 303. Every permutation resamples waves. 78 filter cells were tested; no
  multiple-comparison correction survives a best-cell p of 0.054.
- Matrix 4's exits are held at the **actual** exit timestamp and price. The real stop/TP levels are
  percentages of the *entry* premium, so a deferred entry would have shifted them. This is generous
  to the pullback rule — and it still loses.
- Matrix 4 cannot price a retrace that triggers after the real position closed (coverage 69–97% per
  cell, stated in the table). Unpriceable rows carry their production result.
- `spy_at_entry` is the engine's own snapshot and sits within a few cents of the containing 1-minute
  bar; it is used as "price now", never as a future bar.
- 5 of 303 exits have no logged reason (`fleet_eod.py` force-flatten writes no decision row) and 1 row
  has no OPRA bars. Both are inherited from the source table and are reported there, not imputed here.
- Exit-slippage totals differ from the $895 figure in the cost-realism doc ($1,861 here) because this
  study computes it per leg from that leg's own range rather than from the book-wide median. Both are
  disclosed; conclusions are unchanged under either.

---

## Reproduce

Source dataset: `analysis/recommendations/trade-matrix.json` (built by
`setup/scripts/trade_matrix_build.py`). Feature construction, the wave-permutation null, the
deferred-entry simulator, and the stability checks are pure functions of that file plus
`backtest/data/spy_sip_cache/spy_1m_*.json` (with 2026-08-07 refetched). No look-ahead: every
pre-entry feature reads only 1-minute bars that had **closed** before the entry timestamp.
