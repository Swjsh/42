# T2 today, mechanically: J's 2026-09-03 rising support line

**Stamp: 2026-09-03T17:30 ET.** Script: `backtest/tools/trendline_study_today-exhibit.py`
(read-only; imports `backtest/lib/trendline_detector.py` and `crypto/lib/trendlines.py`,
never edits them). Full numeric output: `trendline-today-exhibit.json` (this directory).
Data: `backtest/data/spy_sip_cache/spy_1m_2026-09-03.json` (673 1m bars, 04:00–16:15 ET).

**Verdict up front:** J's line is a real, visually-legible local low → rally → break shape,
and the CLOSE-based read ("closes above and right on the line" at 10:55, "breaks at 14:30")
is directionally confirmed on the timeframe J actually named for each leg. But the repo's
own pivot-anchored detector — using its own default rules (3-touch minimum, fractal-pivot
anchors, $0.20 tolerance) — **could not have drawn this line at 10:55, with or without
premarket bars, and could not draw it on 15m at all, even with full-day hindsight.** J's
own 5m anchor (08:20) is not even a mechanical pivot; the nearest one is one bar earlier
(08:15, $0.01 lower). This is a dated, concrete instance of the existing shadow-lane finding
("rising support invisible") — not a new problem, but now pinned to an exact bar and an exact
gate (the 3-touch requirement) that killed it.

---

## 1. Aggregation convention (stated, verified)

5m/15m bars built from the 1m cache: **a bar labeled `T` covers the interval `[T, T+width)`**
— open-of-interval, i.e. the 5m bar labeled `08:20` = 1m bars `08:20`–`08:24` inclusive; the
15m bar labeled `08:15` = 1m bars `08:15`–`08:29` inclusive. `open`=first 1m open,
`high`=max(1m highs), `low`=min(1m lows), `close`=last 1m close.

**Verified against the existing cache** (`spy_5m_2026-09-03.json`): 148 bars compared,
**146/148 exact matches**. The only mismatch is the final `16:15` bucket (my aggregation
built it from a single 1m bar because the 1m cache has only one tick at `16:15` and no
`16:16`–`16:19` bars; the cached 5m file's `16:15` bar apparently drew on a richer feed —
`l=771.60` there vs `l=772.76` from the 1m cache alone). **Irrelevant to this study** — no
anchor or query timestamp is near 16:15 — flagged for completeness, not corrected.

**Data-gap caveat (FACT, new finding):** the 1m cache has real gaps throughout the
**04:00–07:55 premarket window** — most 5m buckets in that stretch are built from 1–4 of the
expected 5 one-minute bars (full list in `meta.incomplete_5m_buckets_1m_data_gaps` in the
JSON), consistent with genuinely thin extended-hours liquidity (not independently verified
against a second feed — UNVERIFIED whether this is liquidity or a cache artifact). **From
~08:00 onward through the full RTH session there are zero gaps** — every bucket used for this
study's anchors and query candles (08:15, 08:20, 10:00, 10:10, 10:55, 14:30) is built from a
complete, full-width set of 1m bars. The gap matters only for one number below (the day's
absolute premarket low) and for the detector's *other* (non-J) candidate lines, which anchor
in that gappy window — flagged inline where it applies.

---

## 2. The anchor bars, quoted

| Bar | t | o | h | l | c | n 1m bars |
|---|---|---|---|---|---|---|
| 5m `08:20` (J's 5m anchor A) | 08:20:00 | 764.9999 | 765.48 | **764.97** | 765.47 | 5/5 |
| 5m `10:10` (J's 5m anchor B) | 10:10:00 | 767.83 | 768.38 | **767.53** | 768.36 | 5/5 |
| 15m `08:15` (J's 15m anchor A) | 08:15:00 | 765.14 | 765.68 | **764.96** | 765.47 | 15/15 |
| 15m `10:00` (J's 15m anchor B) | 10:00:00 | 769.53 | 769.57 | **767.53** | 768.36 | 15/15 |

**FACT:** the 15m `10:00` bar's low (767.53) is the *same underlying 1m print* as the 5m
`10:10` bar's low — both trace to the `10:10` 1m tick (`o=767.83 h=767.8948 l=767.53
c=767.66`). The 5m and 15m double-bottom anchors are not independent observations of two
different lows; they are the same physical low read at two zoom levels.

**FACT — is 08:20 really "the" premarket low?** No. The absolute low of the 04:00–09:30
window is **763.59** at the 04:00 1m bar (itself built from only 4/5 expected 1m ticks —
gappy-window caveat applies) and the next-lowest wick print is **764.21** at the 5m `07:30`
bar (also gappy: 4/5 ticks). Price fell from the 04:00 open to a ~764.2–764.4 floor by 06:45–
07:30, chopped there, and the **local minimum right before the sustained rally into the cash
open** is actually the 5m `08:15` bar (low **764.96**) — one nickel-cent lower than J's stated
`08:20` bar (764.97). **J's "premarket low" is a local low at the very end of the premarket
chop, not the session's global minimum** — a reasonable, common chart-reading usage ("the low
right before things turned"), but worth stating precisely: the true adjacent-bar pivot is the
`08:15` bar, one 5m bar before the one J named, by one cent.

**FACT — the 10:10 "double bottom":** 09:55 high 769.61 → 10:00 low 768.11 → 10:05 low
767.61 → **10:10 low 767.53** (the deepest of the dip) → 10:15 reclaims to 768.22–768.88. Two
adjacent closes within $0.08 of each other (767.61, 767.53) at the bottom of one clean
down-swing — a legible "double bottom" read, with 10:10 the (marginally) lower of the two, as
J named it.

---

## 3. Three mechanical lines, 5m (anchors 08:20 → 10:10)

| variant | anchor A price | anchor B price | value@10:55 | value@14:30 |
|---|---|---|---|---|
| all-wick (lows) | 764.97 | 767.53 | 768.5773 | 773.5809 |
| all-body (min(o,c)) | 764.9999 | 767.83 | 768.9878 | 774.5193 |
| **mixed — J's own draw (08:20 body → 10:10 wick)** | 764.9999 | 767.53 | 768.5650 | 773.5102 |

### The 10:55 5m candle

`10:55:00 o=768.62 h=769.33 l=767.45 c=769.28` — **the bar's low (767.45) comes from an
intra-bar wick inside the 10:56 1m tick** (`10:56:00 o=768.72 h=768.82 l=767.45 c=768.40`): a
$1.28 down-spike-and-recover within one minute. Quoted as given by the cache; UNVERIFIED
against a second feed whether this is a real print or a bad tick — either way it is what a
5m chart built from this data would show, and it dominates every "low vs line" touch check
below.

| variant | low − line | close − line | touch ≤$0.10 | touch ≤$0.20 | touch ≤$0.30 | close above line? |
|---|---|---|---|---|---|---|
| all-wick | **−1.1273** | **+0.7027** | no | no | no | **yes** |
| all-body | −1.5378 | +0.2922 | no | no | no | yes |
| mixed (J's draw) | **−1.1150** | **+0.7150** | no | no | no | **yes** |

**Verdict on the 10:55 5m "touch":** the CLOSE is above the line in all three variants (J's
"closing above" is confirmed), but the candle's LOW does not come within $1.10 of the line
under any variant or tolerance band — the 10:56 wick blows straight through it before
reclaiming. This is not a gentle touch; it's a flush-and-reclaim, and it would look that way
on any chart built from this same data. **Next 60 min high after the 10:55 candle closes
(11:00–12:00): 773.32** — a real, substantial follow-through rally, consistent with J's "the
bounce that started the run to 772.9" (actual subsequent high slightly exceeds the number he
cited).

### The 14:30 5m candle and the break

`14:30:00 o=773.759 h=773.88 l=773.55 c=773.86` (close **773.86**, above all three lines'
14:30 projected values at that exact bar — **not yet broken at 14:30 itself** in any 5m
variant). Scanning forward from 13:00 for the first CLOSE that breaks the line by more than
the detector's own $0.20 tolerance:

| variant | first close-break (5m) | line value there | close | miss vs 14:30 |
|---|---|---|---|---|
| all-wick | **14:40** | 773.8136 | 773.60 | 10 min late |
| all-body | **13:15** | 772.5897 | 772.335 | broke over an hour BEFORE 14:30 — not consistent with J's call |
| **mixed (J's draw)** | **14:50** | 773.9703 | 773.62 | 20 min late |

Next 60 min low after the 14:30 candle closes (14:35–15:35): **773.13** — a real, if modest
($0.7), pullback consistent with "we start declining."

**Verdict on the 5m break:** none of the three mechanical variants breaks exactly at 14:30.
J's own stated recipe (mixed) breaks 20 minutes late; all-wick breaks 10 minutes late;
all-body broke over an hour early and is therefore the wrong shape entirely for this claim.
5m alone does not vindicate "broke at 14:30" to the minute.

---

## 4. Three mechanical lines, 15m (anchors 08:15 → 10:00)

| variant | anchor A price | anchor B price | value@10:55 | value@14:30 |
|---|---|---|---|---|
| **all-wick — J's own quote for 15m ("wick to wick")** | 764.96 | 767.53 | 768.8762 | 774.1386 |
| all-body | 765.14 | 768.36 | 770.0467 | 776.6400 |
| mixed (body→wick, for symmetry only — not what J said for 15m) | 765.14 | 767.53 | 768.7819 | 773.6757 |

The 15m candle containing 10:55 is the `10:45–11:00` bar: `o=768.17 h=769.33 l=767.45
c=769.28` (same underlying 10:56 wick as the 5m case). Low−line is −1.33 to −2.60 across
variants (no touch in any tolerance band); close−line is **+0.40 (all-wick, J's stated
recipe, close above)**, **−0.77 (all-body, close BELOW — this variant never even reads as a
bounce)**, +0.50 (mixed).

The 14:30 15m bar is an exact 15m boundary: `o=773.759 h=773.9 l=773.5097 c=773.60`.

| variant | first close-break (15m) | line value there | close | miss vs 14:30 |
|---|---|---|---|---|
| **all-wick (J's 15m recipe)** | **14:30** | 774.1386 | 773.60 | **exact — 0 min miss** |
| all-body | before 13:00 (already broken at first scanned bar) | 773.88 | 772.435 | broke well before 14:30 |
| mixed | 14:45 | 774.0171 | 773.67 | 15 min late |

**This is the sharpest confirmation in the whole exercise:** J's own stated 15m recipe
(wick→wick) breaks by CLOSE, past the detector's own $0.20 tolerance, on the **exact 14:30
bar** — to the minute. His coarser-timeframe read is the one that lands precisely; the
finer-timeframe (5m) read of the same moment is off by 10–20 minutes.

---

## 5. Does the repo's own detector (`detect_trendlines`, defaults, `kinds=('support',)`,
`require_slope='rising'`, `anchor_mode='wick'`) find this line?

### 5a. Top-ranked output (what the detector would actually report)

| run | bars | support lines found (rising) | best anchors |
|---|---|---|---|
| 5m + premarket, EOD hindsight | 148 (04:00–16:15) | 5 | `idx42@764.21(07:30) → idx144@772.61(15:50)`, touches=4 — **not J's pair** |
| 5m RTH-only, EOD | 78 (09:30–15:55) | 1 | anchors both after 13:00 — 08:20 doesn't exist in this bar set at all |
| 15m + premarket, EOD hindsight | 50 (04:00–16:15) | 1 | `idx14@764.21(07:30) → idx37@772.12(13:15)`, touches=3, **status=broken** — not J's pair |
| 15m RTH-only, EOD | 26 (09:30–15:45) | **0** | — |
| 5m + premarket, **no-lookahead (only bars closed ≤10:55)** | 47 (04:05–10:50) | 4 | best: `idx15@764.96(08:15) → idx42@767.83(10:30)`, touches=3 — **still not J's pair** (right first anchor, WRONG second anchor: 10:30, not 10:10) |
| 5m RTH-only, no-lookahead ≤10:55 | 17 (09:30–10:50) | **0** | — |
| 15m + premarket, no-lookahead ≤10:55 | 12 (07:15–10:30) | **0** | — |
| 15m RTH-only, no-lookahead ≤10:55 | 5 (09:30–10:30) | **0** | — |

**In no configuration, at any point, does the detector's own top-ranked candidate list
contain J's anchor pair.** With premarket bars included it finds *other* rising support
lines (touching the same general 764–768 zone but anchored differently); RTH-only removes
the premarket anchor from the data entirely, so it's structurally impossible there.

### 5b. Direct check on J's SPECIFIC anchors (bypassing the ranking — does the pair even qualify?)

| pair tested | is A a confirmed swing-low pivot? | is B a confirmed pivot? | `_fit_candidate` result |
|---|---|---|---|
| 5m 08:20→10:10, no-lookahead ≤10:55 | **False** | True | n/a (A isn't a pivot) |
| 5m 08:20→10:10, EOD hindsight | **False** | True | n/a (A isn't a pivot, even with the whole day available) |
| 15m 08:15→10:00, no-lookahead ≤10:55 | **False** | True | n/a |
| 15m 08:15→10:00, EOD hindsight | **False** | True | **08:15 is never a confirmed pivot on 15m, at any point in this session** — 06:45 (764.36) and 07:30 (764.21) are both lower and dominate the fractal search there |
| 5m 08:15→10:10 (adjusted to the nearest ACTUAL pivot), no-lookahead ≤10:55 | True | True | **rejected — insufficient touches** (only the 2 defining anchors qualify; no 3rd touch by 10:50) |
| 5m 08:15→10:10 (adjusted), EOD hindsight | True | True | **accepted**: touches=`[08:15, 10:10, 14:40]` (3, clearing the min-touches gate at the 14:40 bar — almost exactly J's "14:30" break moment), but immediately followed by **17 straight violation bars from 14:55 through EOD** (`score = −79.7`, deeply negative — never a line the ranker would surface) |

**Why 08:20 fails as a pivot (mechanism, stated plainly):** `find_swing_points` requires a
swing low's neighbors on the left to be *strictly higher*. The 5m `08:15` bar's low (764.96)
is one cent *lower* than `08:20`'s (764.97) — so `08:20` cannot pass the left-side test no
matter how far forward you look. The nearest bar that IS a mechanical pivot is one 5m bar
earlier, price one cent lower. On 15m, `08:15` fails the same test against `06:45`/`07:30`,
which are $0.6–0.75 lower and sit within the same 2-bar-window fractal neighborhood.

**No-look-ahead check, answered directly:** as of 10:55 ET, with only bars whose close time is
`<=10:55` visible (5m: through the `10:50` bar; 15m: through the `10:30` bar — both fully
complete, no partial trailing bucket), the detector had the `10:10` pivot available (confirmed
by the `10:20` bar, well before 10:55) in every premarket-inclusive configuration. It did
**not** have a valid `08:20`/`08:15` pivot to pair it with under either timeframe's own strict
fractal rule, and even the corrected nearest-pivot pairing (5m `08:15`→`10:10`) was rejected
outright for insufficient touches at that point in the session — it only clears the 3-touch
bar four hours later, in hindsight, at 14:40.

---

## 6. Verdict

Is J's 10:55 read a coincidence under a mechanical definition?

- **Confirmed** by: the CLOSE-above-line read on both 5m and 15m, all wick/mixed variants
  (not the all-body variant); the follow-through rally to a new high (773.32) matching "the
  run to 772.9"; the 15m wick-wick break landing on the exact 14:30 bar, to the minute.
- **Not confirmed** by: any strict touch/tolerance test on the candle's LOW at 10:55 (the
  10:56 1m wick to 767.45 blows $1.1–$2.6 through every line variant — this was a violent
  flush-and-reclaim, not a gentle touch); the 5m break timing (10–20 min late depending on
  anchor mode, vs. exact on 15m); the all-body variant on either timeframe (breaks over an
  hour before 14:30, or never even shows the close above the line at 10:55 on 15m).
- **Not found by the mechanical pivot detector at all**, on either timeframe, with or
  without premarket bars, at 10:55 or with full-day hindsight — except one adjusted,
  one-bar-shifted variant that becomes valid for exactly 25 minutes (14:40–14:55) before
  racking up 17 straight violations. J's eye is reading a real, legible chart shape (rising
  local-low-to-local-low support, held, then broken); the repo's fractal-pivot + 3-touch
  detector is calibrated to a stricter, higher-bar definition that this specific line does
  not clear at the moment J drew it, and structurally cannot clear on 15m at all this
  session.

This reproduces, with an exact bar and an exact gate, the standing memory-doctrine finding:
**"trendline shadow lane (2026-08-20): pivot-highs only; rising support invisible."** Today's
case shows precisely *why* it's invisible here — not "the pivot search doesn't look for
rising lines" (it does, `require_slope='rising'` is exactly this), but that the **3-touch
minimum and the strict-neighbor pivot test reject the specific line a human draws from two
eyeballed extremes** before either the touch count or the anchor identity itself can match.

---

## 7. What this is NOT

- Not a claim that the detector is broken — it is doing exactly what its own documented
  design says (3+ touches, matches "the Tori method" and `filters.py`'s existing bar). This
  is a scope/definition gap, not a bug.
- Not a backtest, not an n>1 result, not evidence of an edge. **n=1 session.** No
  significance test is meaningful here; none is claimed.
- Not a change to any trading-path file. `backtest/lib/trendline_detector.py`,
  `crypto/lib/trendlines.py`, `crypto/lib/market_structure.py` were imported read-only and
  are untouched.

See the companion prereg for a scoped, forward-looking next step:
[`prereg-trendline-rising-support-2026-09-03.md`](../../recommendations/prereg-trendline-rising-support-2026-09-03.md).
