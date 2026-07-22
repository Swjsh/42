# PULLBACK-HOLD-BULL-TRIGGER -- Stage Summary (2026-07-22)

**Verdict: NO_CELL_SHIPS (honest null).** 0/36 pre-registered cells clear the ship bar.
Every cell is disqualified at the sanity-anchor fidelity gate BEFORE dollar economics are
even consulted -- and the dollar economics don't support shipping anyway (best cell is
flat-to-noise, worst cells lose meaningfully).

Pre-reg (frozen before any grid run): `analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json`
Scorecard (full detail, all 36 cells): `analysis/recommendations/pullback-hold-bull-2026-07-22.json`
Detector: `backtest/tools/pullback_hold_bull_detector.py`
Grid runner: `backtest/tools/pullback_hold_bull_replay.py`
Guard tests: `backtest/tests/test_pullback_hold_bull.py` -- **16/16 PASS**

## Grid

36 cells = `up_structure_mode {MARKET_STRUCTURE, PRICE_VWAP} x zone_band_cents {15,25,40} x
hold_bars_n {1,2,3} x confirm_mode {NONE, BOTH}` (BOTH = RSI-reset AND green-close together --
combined into one axis, disclosed in the pre-reg, to respect the 36-cell cap).

## Populations

- Full history (detector-frequency only): 44 trading days, 2026-05-19 .. 2026-07-22.
- OPRA-covered (real-fills dollar validation): 39 days, 2026-05-19 .. 2026-07-17.
- Held-out (never touched during tuning): last 10 OPRA days, 2026-07-01 .. 2026-07-17.

## Root cause of the universal anchor-1 miss

Anchor 1 (2026-07-22, higher-low 746.80 over a level_memory level -- LevelMemory independently
finds **746.54** exactly, matching J's live read) requires an entry inside `[10:44, 10:53]` ET.
**Zero of the 36 cells produce it**, because both up-structure qualifier candidates -- evaluated,
per the frozen pre-reg, AT the pullback-low bar itself (10:40 ET) -- read **False** at that exact
bar:

| Qualifier | Reads True at 10:40? | Recovers True at |
|---|---|---|
| PRICE_VWAP (close > session VWAP) | No | 10:55 ET (15 min late) |
| MARKET_STRUCTURE (crypto/lib/market_structure uptrend) | No | 11:25 ET (45 min late) |

Verified as a genuine timing gap, not a bug: SPY's session VWAP on 07-22 legitimately crossed
below price during the 10:20-10:50 pullback (confirmed bar-by-bar against the session-anchored
VWAP math), and MARKET_STRUCTURE had not yet accumulated enough confirmed swing labels that early
in the session to call "uptrend." **This is the exact root-cause tension the whole queue item
exists to fix** -- J's own exhibit text notes "ribbon still labeled BEAR... flipped BULL 11:16,
30 min LATE" at the same moment. The two up-structure qualifier CANDIDATES this pre-reg was
scoped to choose from (market-structure trend, price-vs-VWAP) are themselves lagging-confirmation
signals, so by construction neither can see J's earliest, most valuable read. A future iteration
would need a genuinely earlier up-structure proxy (not in the pre-registered candidate set) to
clear this gate -- **not a reason to loosen this frozen grid's definition after seeing the miss**.

Anchor 2 (2026-07-21 shelf 745.77-745.85 -> 11:15 close 747.41) fires on **18/36 cells** (every
`confirm_mode=NONE` cell, both up-structure modes, all bands/N) -- LevelMemory independently finds
a persistent support cluster at **745.78-745.88** across the shelf, and the eventual reclaim
(747.41) is far enough above any plausible zone_top that the hold condition trivially clears. The
18 `confirm_mode=BOTH` cells miss anchor 2 too: real RSI(14)/green-close at the actual entry bar
does not satisfy the combined RSI-reset + green-close requirement on this specific reclaim bar.

Because BOTH anchors are required (`cell_disqualified_if` in the pre-reg), and anchor 1 alone
already fails universally, **all 36 cells are disqualified** regardless of dollar performance.

## Dollar economics (disclosed anyway, for the record -- none of this overrides the anchor gate)

Top cell by expectancy, real fills only (39-day OPRA population):

| Cell | n | Total P&L | Expectancy/tr | WR | p-value | BH-FDR sig (q=0.10) |
|---|---|---|---|---|---|---|
| PRICE_VWAP_band40c_N1_NONE | 506 | $808.93 | $1.60 | 35.2% | 0.878 | No |
| MARKET_STRUCTURE_band40c_N1_NONE | 353 | -$559.03 | -$1.58 | 33.1% | 0.890 | No |
| MARKET_STRUCTURE_band40c_N2_NONE | 350 | -$694.82 | -$1.99 | 32.9% | 0.862 | No |

**No cell clears BH-FDR** (all p-values 0.44-0.99 -- nowhere close to q=0.10 significance). The
best cell is statistical noise ($1.60/trade on n=506, WR 35%), not an edge. n>=340 per cell on
just 39 days (roughly 9-13 entries/day) is itself informative: at the widest pre-registered band
(40c), "low within band of ANY known LevelMemory level" is satisfied by a large fraction of bars
-- the detector as gridded is far less selective than the distinctive, occasional pattern J
described live. Tighter bands (15c/25c) push expectancy sharply MORE negative (-$4 to -$38/trade)
as N grows, not less -- the tight/short cells are the worst performers in the grid, not the best.

## What this means for the queue item

The root-cause diagnosis in `automation/overnight/queue.md` (ELITE level_reclaim fires too late,
block_elite_bull kills the whole bull lane on genuine up days) is unaffected by this null --
it stands on its own evidence. What this stage-1 build establishes is narrower: **the two
up-structure qualifier candidates pre-registered for this specific grid (market-structure trend,
price-vs-VWAP) are not early enough to see J's own named exhibit**, and the detector as gridded
is not selective enough to show a real dollar edge even where it does fire. Per the mission's own
instruction, this frozen grid is not re-opened or hand-loosened to manufacture a pass. A follow-on
iteration (a NEW dated pre-reg, not an edit to this one) would need either (a) a genuinely earlier
up-structure proxy than trend-confirmation/VWAP-crossing, or (b) a tighter selectivity mechanism
than "low within N cents of any LevelMemory level" -- both are real, actionable next steps, not
excuses.

## Test evidence

```
backtest/tests/test_pullback_hold_bull.py -- 16 passed
```

Covers: basic fire, zone-is-a-band (not penny-exact, same bars fire at band=0.40 and not at
band=0.15), N-bar hold window respected, confirm_mode=BOTH gates RSI-reset AND green-close
independently, no duplicate/overlapping signals from one dip, no-look-ahead (truncation test:
truncating right after the entry bar reproduces the identical signal; truncating before it drops
the signal entirely), both of J's named exhibits reproduced on synthetic fixtures shaped to their
real OHLC numbers, and the `up_structure_series`/`session_vwap_series`/`market_structure_up_ok`
feature-precomputation helpers sanity-checked in isolation.
