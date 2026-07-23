# HARVEST-DAY ANATOMY — 2026-07-23

> Foundation doc for tonight's cook lanes. Joins the 190-trade / 141-trading-day full-history
> replay of the **current live core-Safe engine** (`analysis/recommendations/engine-fullhist-replay-2026-07-23.json`,
> RIBBON_RIDE entries only, real OPRA fills, real exit_manager) to the 386-day archetype
> inventory (`analysis/edge-matrix/day-inventory-2026-07-23.json`) and this week's real fills
> (`journal/trades.csv`, 2026-07-17→22, all account arms). Pure join/aggregation — no new
> backtest run, no live wiring, no commits. Build script:
> `analysis/kitchen/_harvest_anatomy_build.py`. Machine-readable output:
> `analysis/kitchen/day-archetype-map.json`.

**SCOPE DISCLOSURE (inherited from the replay's own doc, restated here):** the replay only
models the RIDE_THE_RIBBON family (`BEARISH_REJECTION_RIDE_THE_RIBBON` /
`BULLISH_RECLAIM_RIDE_THE_RIBBON`) — the two setups in `params.json`'s `setups_allowed`. It does
**not** model the "extra setups" (`bollinger_squeeze`, `vwap_continuation`,
`vwap_reclaim_failed_break`, `vix_regime_dayside`, `double_bottom_base_quiet`, `gap_and_go`)
which place real Safe-paper orders live today via `setup_dispatch.py` but have no full-history
batch-replay harness. **Every "sit-out" number below is a core-ribbon_ride sit-out, not a
whole-engine sit-out** — §4 shows the extra-setups are already partially covering the archetypes
core ribbon_ride skips.

**Data-join caveat:** 1 of 141 trading days (2026-06-15) has a trade in the replay but no
archetype row in the day-inventory (`day-inventory-2026-07-23.json` itself discloses this date
in `opra_dates_without_spy_bars` — a SPY-bar gap, not an OPRA gap). It is counted in all
headline/win/loss totals but excluded from day_type/vix_band joins. 1/190 trades, doesn't move
any conclusion below.

---

## Headline (for orientation)

- **190 trades / 141 trading days / 386 calendar RTH days in the window (2025-01-02→2026-07-22).**
- Total P&L (RIBBON_RIDE only): **+$5,064.75**. Win rate 29.47%. Profit factor 1.333.
- **36.4% of days traded** (141/387 per the replay's own count) — the FOCUS-DOCTRINE brief's
  "64% sits out" is this number's mirror, joined to archetype below.
- Regime split: 2025H1 -$55.55 (38 tr), 2025H2 +$1,633.60 (72 tr), 2026 YTD +$3,486.70 (80 tr,
  best win rate 37.5%) — confirms the engine has been getting *better* over the window, not
  worse; 2026 carries the bulk of the edge.

---

## 1. What the WINNING days share (48 days, +$45,588 combined... see day list; 48 win / 93 loss / 0 exact-flat)

| Dimension | Win days (n=48, 71 trades) |
|---|---|
| **day_type** | range 23 (48%) · trend 17 (35%) · chop 5 (10%) · unclassified 2 |
| **VIX band** | mid 37 (77%) · elevated 5 (10%) · low 5 (10%) · **high: 0** |
| **avg gap %** | +0.081% (essentially flat — gap size does NOT discriminate, see §2) |
| **avg RTH range** | $6.91 (wider than loss-day avg $6.26 — modest, real) |
| **entry hour mix** | 13:00 dominant (28%), 14:00 (21%), 09:00/11:00 tied (14% each), 12:00 (13%), 10:00 (10%), **15:00: 0%** |
| **trigger mix (rate/trade)** | trendline_rejection 61% · **confluence 39%** · ribbon_flip 28% · level_rejection 25% · level_reclaim 24% |
| **tier mix** | TRENDLINE 51% · SUPER 31% · ELITE 11% · LEVEL 7% |
| **setup/side** | BEARISH/P 76% · BULLISH/C 24% |
| **exit category** | runner_stop 49% (the payoff) · premium_stop 23% · structure_stop 11% · time_stop 11% · ribbon_flip_back 6% |

**Read:** winning days are disproportionately `range` and `trend` (83% combined vs 45% of the
full 386-day population), **mid-VIX, entered 13:00-14:00**, and — the single sharpest
discriminator — carry a **confluence trigger 2.6x more often than losing days** (39% vs 15% of
trades, see §2). ELITE/SUPER tiers (which require multi-trigger confluence by construction) are
2.5-4x over-represented on win days vs loss days. Zero win days ever touched `high` VIX (≥25) —
consistent with the engine never trading that band at all (§3).

## 2. What the LOSING days share (93 days, 119 trades)

| Dimension | Loss days (n=93, 119 trades) |
|---|---|
| **day_type** | **chop 36 (39%)** · range 35 (38%) · trend 21 (23%) · unclassified 1 |
| **VIX band** | mid 72 (77%) · elevated 16 (17%) · low 5 (5%) · **high: 0** |
| **avg gap %** | +0.088% (statistically indistinguishable from win-day +0.081% — not a discriminator) |
| **avg RTH range** | $6.26 |
| **entry hour mix** | 14:00 (21%), 12:00 (20%), 11:00 (18%), 13:00 (17%), 09:00 (11%), 10:00 (9%), **15:00 (3%, 4 trades — win days had zero)** |
| **trigger mix (rate/trade)** | **trendline_rejection 76%** (single-trigger, low-conviction) · ribbon_flip 19% · level_reclaim 18% · confluence 15% · level_rejection 8% |
| **tier mix** | **TRENDLINE 74%** · SUPER 13% · LEVEL 11% · ELITE 3% |
| **setup/side** | BEARISH/P 82% · BULLISH/C 18% |
| **exit category** | **premium_stop 64%** (the -50% catastrophe cap eating trades) · structure_stop 22% · ribbon_flip_back 13% · time_stop 2% |

**Read:** losing days skew `chop` (39% vs 10% of win days — the single strongest day_type
signal in either direction) and fire almost exclusively off a bare `trendline_rejection` with no
confirming confluence (76% of loss-day trades vs 61% of win-day trades, but critically **without**
the confluence trigger riding alongside it — TRENDLINE tier alone is 74% of loss-day volume vs
51% of win-day volume). The premium_stop catastrophe cap (-50%) is the dominant loss-day exit
(64% of trades) — these are trades that never got a chance to ride.

**Cross-cutting finding (not day-type-specific, applies across both cohorts):** TRENDLINE tier
is **124/190 trades = 65% of ALL engine volume**, and it is a net loser: **-$1,830.10 total,
19.35% win rate** — the worst-performing tier by both win rate and total $ (LEVEL is the only
other loser: 18 trades, -$990.45, 27.8% WR). ELITE (11 tr, 72.7% WR, +$2,758) and SUPER (37 tr,
51.4% WR, +$5,127) are the two winners and together are only 48/190 = 25% of volume. **The
engine is running two-thirds of its trade count through its worst-quality tier.** By exit
category matrix-wide: premium_stop (92 tr, -$8,584, avg -$93/tr) and structure_stop (34 tr,
-$5,166, avg -$152/tr) fund runner_stop (35 tr, **+$15,774**, avg +$451/tr) and time_stop (10 tr,
+$2,836, avg +$284/tr) — a classic few-big-winners/many-small-losers shape (WR 29.5%, PF 1.33).

## 3. What the 64% SIT-OUT days look like (246/386 = 63.7% of all days, core-ribbon_ride scope)

By day_type (this is the uncovered market a most-days trader would need to work):

| Archetype | n sit-out days | % of all 386 | % of sit-out pool | Coverage rate (traded/total of type) | Avg RTH range | Directionality (n=sample) |
|---|---|---|---|---|---|---|
| **chop** | 95 | 24.6% | 38.6% (largest slice) | 41/136 traded = **69.9% sits out** (worst coverage) | $4.49 (median $4.08) — tightest | 61 up / 23 down / 11 flat (64% up-tilt) |
| **range** | 90 | 23.3% | 36.6% | 58/148 traded = 60.8% sits out | $7.75 (median $6.88) | 51 up / 36 down / 3 flat (57% up-tilt) |
| **trend** | 59 | 15.3% | 24.0% | 38/97 traded = 60.8% sits out | $11.23 (median $9.72) — widest | 36 up / 23 down (61% up-tilt) |
| unclassified | 2 | 0.5% | 0.8% | ATR-20 warmup artifact (first ~20 days of the window only) — not a real archetype | 8.31 | n=2, ignore |

**Plus an orthogonal, fully-dark archetype: `high` VIX band (≥25).** 35/386 days (9.1% of the
whole window) are high-VIX, and **0 of them were ever traded** — 0% coverage, the only archetype
at exactly zero. This is not a discovery, it's confirmation the standing `vix_bear_hard_cap=23.0`
+ `block_elite_bull` VIX[0,25) gates are doing exactly what they're configured to do on an
unvalidated regime. Not a cook target.

**Read:** the market tilts bullish across the whole window (57-64% up-days in every archetype,
consistent with the broad 2025-2026 SPY tape and the engine's own BULLISH_RECLAIM WR (41.0%)
running ahead of BEARISH_REJECTION (26.5%) per the replay's `per_setup` block) — this is a
regime characteristic to carry into any new lane's directional weighting, not a discriminator by
itself. `chop` is simultaneously the **largest sit-out cohort** (38.6% of all skipped days) *and*
the **worst-performing archetype when the engine does trade it** (-$43.83/day, 12.2% day win
rate, see §4 table) — sitting it out more, not less, is directionally correct; the sit-out rate
being "only" 69.9% (not ~100%) is itself informative.

## 4. Per-archetype economics + natural cook-lane assignment

Traded-day P&L by day_type (what the engine actually earns/loses when it DOES fire on that
archetype — this is the ranking signal for where to spend R&D):

| day_type | n traded days | total P&L | avg $/day | day-win-rate | Verdict |
|---|---|---|---|---|---|
| **trend** | 38 | **+$3,516.95** | **+$92.55** | 44.7% | Best traded archetype, most underexploited (60.8% sit-out on a good archetype) |
| range | 58 | +$2,629.10 | +$45.33 | 39.7% | Second-best, largest absolute sit-out count |
| **chop** | 41 | **-$1,797.00** | **-$43.83** | **12.2%** | Only net-losing archetype — bleeds when traded, still trades 30% of it |
| unclassified | 3 | +$649.70 | +$216.57 | 66.7% | n=3, warmup-window noise, ignore |

VIX-band traded-day P&L (secondary cut): low-VIX days are the best per-day economics
(+$176.87/day, 50% day-WR, n=10) but rare (26/386 days); mid-VIX carries the volume
(+$22.59/day, 33.9% WR, n=109); elevated is positive but low-WR (+$36.55/day, 23.8% WR, n=21 —
fat-tail-winner shape, not a reliable day-consistency signal per FOCUS-DOCTRINE §3).

### Archetype → tonight's 6 lanes

| Archetype / finding | Natural lane (primary) | Secondary | Why |
|---|---|---|---|
| **trend** (59 sit-out, 60.8% of type, best traded $/day) | **trend-continuation** | extra-lanes harness | ribbon_ride's trigger needs a level TOUCH (rejection/reclaim); pure trend days without a clean level touch never generate one. This is the single most underexploited GOOD archetype — highest traded avg-$/day (+$92.55) yet 61% of its population sits idle. Real fills this week already show `vix_regime_dayside`/`vwap_continuation`/`bollinger_squeeze` firing on trend days (6 fills) — validate/extend that live path with real evidence before building new. |
| **chop** (95 sit-out, largest sit-out cohort, WORST traded archetype) | **day-gate** | class-conditional exits | Chop is the one archetype the engine actively bleeds on when it fires (-$43.83/day, 12.2% day-WR) — the cheapest, most FOCUS-DOCTRINE-aligned fix is a veto using data the day-inventory already computes (`range_ratio<0.75` — no new indicator, no new gate stacked on a weak signal, states in one sentence: "don't trade ribbon_ride on chop days"). Extra-setups already fire some chop-day trades too (8 real fills this week) — those need class-conditional (tighter) exits, not a blanket day-gate, since they're a different entry family. |
| **range** (90 sit-out, largest ABSOLUTE sit-out share, 2nd-best traded $/day) | **extra-lanes harness** | — (explicitly NOT range-fade) | `EDGE-MATRIX-FULLHIST-2026-07-23.md` already killed range-pingpong ENTRY signals: 16/16 cells negative, day-WR ≤39% both runs — do not re-cook. Real fills this week show 22 extra-setup/refinement fills already landing on range days (`TRENDLINE_BREAK_RETEST`, `bollinger_squeeze`, `BEARISH_REJECTION_RIDE_THE_RIBBON`) — this archetype is already being reached by the live extra-setup path, not by a new range-specific entry family. |
| **TRENDLINE-tier volume/quality mismatch** (cross-cutting, 65% of ALL volume, -$1,830, 19.4% WR) | **trendline refinement** | class-conditional exits | The named lane exists for exactly this: TRENDLINE tier is single-trigger (`trendline_rejection` alone, no confluence) by construction and is the dominant loser. Refining the tier's admission bar (require a 2nd confirming trigger, e.g. what SUPER/ELITE already do) or applying tighter/faster exits specifically to TRENDLINE-tier entries (they eat premium_stop -$8,584 and structure_stop -$5,166 disproportionately) are both directly actionable from data already in hand. |
| **high-VIX (≥25)** (35 days, 9.1% of population, 0% ever traded) | *(none — not a cook target)* | — | Already fully gated by `vix_bear_hard_cap=23.0` + `block_elite_bull` on an unvalidated regime. Flag for awareness only. |
| unclassified (5 days total) | *(none)* | — | ATR-20 warmup artifact of the classification method (first ~20 days of the 386-day window can't compute a 20-day trailing ATR) — not a market archetype, disclose and ignore. |

---

## Disclosures

- All $ figures are RIBBON_RIDE-only per the replay's own scope disclosure — extra-setups
  (which DO fire live, see §3/§4 tables) are not in any full-history replay harness as of this
  run, so their true historical day-coverage/economics are unquantified; only this week's
  qualitative fill pattern (`journal/trades.csv`) is available and is disclosed as such, not as
  a backtested number.
- `journal/trades.csv` rows include partial-close legs and multiple fleet-arm entries per
  round-trip trade (safe-2/safe-3/risky-1/risky-3/bold-2 all journal separately) — the §3/§4
  "this week" fill counts are fill-row counts, not distinct-trade counts, and are used only for
  qualitative "does this setup fire on this archetype" evidence, never as a P&L claim.
- Directionality (`up_days`/`down_days`/`flat_days`) reconstructed from
  `backtest/data/spy_5m_2025-01-01_2026-07-22.csv` (first-bar open vs last-bar close per RTH
  day) under that cache's known fixed `-04:00` year-round offset (the documented DST-frame
  artifact, `project_dst_frame_artifact_2026_07_02`) — safe for date-bucketing here since a
  ±1hr shift never pushes an RTH (09:30-16:00) bar across a calendar-date boundary; not safe to
  reuse for anything intraday-timing-sensitive.
- 1/141 trading days (2026-06-15) has a trade but no day-inventory archetype row (SPY-bar gap
  disclosed in the inventory's own `opra_dates_without_spy_bars`); counted in headline
  win/loss/population totals, excluded from day_type/vix_band joins. Immaterial to every
  conclusion above (1/190 trades).
- No new backtest run performed. No live wiring, no commits, no broker imports — pure
  join/aggregation over `engine-fullhist-replay-2026-07-23.json`,
  `day-inventory-2026-07-23.json`, and `journal/trades.csv` per the task's constraint.
