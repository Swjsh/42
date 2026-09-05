# Wave-day pre-open conditions -- GOAL-WAVE-DAY-CONDITIONS-2026-09-05 (W1/W2)

> Hypothesis GENERATOR, n=25 total sessions (20 wave / 5 no-wave). Never a filter or a
> gate on this evidence -- see the goal file's own framing. Computed $0, from cached
> SPY/VIX bars (`backtest/data/spy_sip_cache/spy_1m_<date>.json` + `vix_5m_2026-05-19_
> 2026-09-04.csv`), `automation/state/key-levels-history/<date>/0835.json`, and
> `journal/<date>.md`'s premarket "Bias:" line. Tool: `setup/scripts/
> wave_day_conditions.py` (`build_row(date)`), fired once per date in this backfill.

## Method notes (read before the table)

- **Wave label**: `>= 1` genuine right-tail wave per `backtest/lib/right_tail_waves.py`
  (`meets_threshold` = peak option premium >= 1.3x entry over the entry->16:00 ET
  window), read from `analysis/right-tail/CAPTURE-<date>.json`'s
  `n_waves_meeting_threshold`. This is the goal's own DONE-WHEN definition -- it is
  NOT the doctrine's narrower "top-5 dollar days" (`edge-master-doctrine.md`'s "August
  2026 big-day anatomy" names 5 specific $ outliers within this same 20-wave-day set).
  Over the full 08-03..09-04 window this reads **20 wave-days / 5 no-wave-days**, not
  the doctrine's n=5 -- the goal preamble's "n=5" refers to that narrower dollar-outlier
  set, not this table's wave/no-wave split.
- **Overnight gap %**: today's RTH 09:30 open vs prior trading day's RTH 16:00 close.
- **First-15-min range / 20-day ATR**: 09:30-09:45 ET high-low, divided by the mean
  daily RTH high-low range over the 20 trading days strictly before this date (a
  simple range-ATR, not Wilder true-range -- disclosed per-row via the script's
  `atr20_definition` field).
- **VIX open-vs-prior-close**: VIX's first 5-min bar at/after 09:30 ET minus the prior
  trading day's VIX close (~16:00 bar). **VIX 5-day slope**: (today's VIX close -
  VIX close 5 trading days ago) / 5 -- per Lesson C5, read as *character* (direction of
  the recent walk), not as a level.
- **Prior-day close vs prior-day VWAP**: prior trading day's RTH close vs that day's own
  RTH volume-weighted-average price, as a %.
- **Distance to nearest zone**: |09:30 print - nearest key-levels.json price| from that
  morning's premarket snapshot (`key-levels-history/<date>/0835.json`).
- **Bias correct?**: premarket bias (journal `Bias:` line, classified bullish/bearish/
  no_trade) compared to the day's actual direction -- wave day: the first genuine
  wave's side; no-wave day: RTH close-vs-open sign (a weak proxy, disclosed). `n/a`
  when the bias was `no_trade`, unparseable, or the wave label itself is unresolved.
- **n/a cells are real data gaps, not zeros** -- `2026-08-31` has no per-day 1-min SIP
  cache file (first-15-min needs 1-min granularity the aggregate 5-min fallback lacks);
  8 of 25 journal files (08-12/13/14/17/31, 09-01/02/03/04) carry no "Bias:" line at
  all (auto-generated journals with no premarket narrative section that session);
  a few `key-levels-history` snapshots are missing a level list close enough to price.
  Every gap is fail-open (never a crash, never a fabricated number) per C7.

## W1 -- per-day table (n=25: 20 wave / 5 no-wave, 2026-08-03..2026-09-04)

| Date | DoW | Wave? | n_waves(meet/all) | Gap% | First15/ATR20 | VIX open-prior | VIX 5d slope | PriorClose-vs-VWAP% | Dist-to-zone | Bias | Bias correct? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-03 | Mon | no-wave | 0/0 | 0.296 | 0.442 | 0.210 | -0.594 | 0.351 | 0.02 | bullish | True |
| 2026-08-04 | Tue | WAVE | 3/5 | 0.422 | 0.230 | -0.190 | -0.370 | 0.192 | 0.38 | bullish | True |
| 2026-08-05 | Wed | WAVE | 1/1 | 0.536 | 0.207 | 0.790 | -0.918 | 0.321 | 0.71 | no_trade | n/a |
| 2026-08-06 | Thu | WAVE | 1/1 | 0.048 | 0.238 | 0.230 | -0.410 | -0.374 | 0.03 | bearish | True |
| 2026-08-07 | Fri | WAVE | 1/2 | 0.293 | 0.193 | -0.030 | -0.236 | -0.046 | 0.02 | bearish | False |
| 2026-08-10 | Mon | WAVE | 1/1 | -0.029 | 0.151 | 0.530 | -0.070 | 0.096 | 0.22 | no_trade | n/a |
| 2026-08-11 | Tue | WAVE | 2/2 | 0.194 | 0.237 | 0.070 | -0.218 | -0.030 | 0.43 | no_trade | n/a |
| 2026-08-12 | Wed | WAVE | 2/5 | 0.561 | 0.331 | -0.410 | -0.254 | -0.159 | 0.10 | n/a | n/a |
| 2026-08-13 | Thu | WAVE | 3/5 | 0.264 | 0.323 | 0.000 | -0.144 | 0.016 | 0.03 | n/a | n/a |
| 2026-08-14 | Fri | WAVE | 1/4 | 0.098 | 0.127 | -0.050 | -0.120 | 0.065 | n/a | n/a | n/a |
| 2026-08-17 | Mon | WAVE | 2/2 | 0.013 | 0.206 | 0.740 | -0.048 | -0.063 | n/a | n/a | n/a |
| 2026-08-18 | Tue | WAVE | 2/2 | -0.510 | 0.231 | 0.630 | 0.102 | -0.175 | 0.33 | bearish | True |
| 2026-08-19 | Wed | WAVE | 2/3 | 0.391 | 0.202 | -0.570 | 0.094 | -0.087 | 0.73 | bullish | True |
| 2026-08-20 | Thu | WAVE | 3/3 | -0.420 | 0.276 | 0.900 | 0.296 | -0.081 | 1.33 | bearish | True |
| 2026-08-21 | Fri | WAVE | 3/4 | 0.427 | 0.225 | -0.630 | 0.180 | -0.251 | 0.56 | no_trade | n/a |
| 2026-08-24 | Mon | no-wave | 0/0 | -0.103 | 0.394 | 0.670 | 0.136 | -0.037 | 0.59 | no_trade | n/a |
| 2026-08-25 | Tue | WAVE | 1/1 | 0.358 | 0.144 | -0.720 | -0.078 | -0.035 | 0.21 | bullish | True |
| 2026-08-26 | Wed | no-wave | 0/2 | -0.141 | 0.313 | 0.190 | 0.096 | 0.056 | 0.19 | bullish | True |
| 2026-08-27 | Thu | WAVE | 3/3 | 0.309 | 0.370 | -0.370 | -0.312 | 0.029 | 0.20 | bullish | True |
| 2026-08-28 | Fri | WAVE | 1/3 | 0.088 | 0.255 | -0.040 | -0.156 | 0.119 | 0.18 | no_trade | n/a |
| 2026-08-31 | Mon | no-wave | 0/0 | -0.254 | n/a | 0.850 | -0.192 | -0.207 | 0.25 | n/a | n/a |
| 2026-09-01 | Tue | WAVE | 1/2 | -0.641 | 0.254 | 1.170 | 0.172 | n/a | 0.12 | n/a | n/a |
| 2026-09-02 | Wed | WAVE | 1/4 | 0.126 | 0.247 | -0.200 | -0.016 | -0.068 | 0.24 | n/a | n/a |
| 2026-09-03 | Thu | WAVE | 2/5 | 0.358 | 0.472 | -0.350 | -0.042 | 0.044 | 0.28 | n/a | n/a |
| 2026-09-04 | Fri | no-wave | 0/3 | -0.079 | 0.232 | -0.200 | 0.020 | 0.121 | 0.61 | n/a | n/a |

## W2 -- honest read (n=20 wave / n=5 no-wave; ranges disclosed, no threshold proposed)

**No condition cleanly separates at this n.** Every continuous condition's no-wave
range sits fully or almost fully inside the wave range's span -- there is no value
that, if used as a cutoff, would sort the 5 no-wave days from the 20 wave days without
also excluding several real wave days. What follows is a direction-only read, group
means/medians with n and range disclosed on every line, per the goal's own
no-p-value-at-n=5 instruction.

**Conditions that show a directional lean (weak, overlapping, worth carrying forward as
a hypothesis -- not a filter):**

1. **Day of week.** No-wave days: 3 of 5 (60%) fell on Monday (08-03, 08-24, 08-31);
   wave days: 2 of 20 (10%) fell on Monday (08-10, 08-17). n=5 no-wave is far too small
   to call this more than a lean, but it is the single starkest split in this table --
   Monday is 3x over-represented among no-wave days relative to its 1-in-5 base rate.
2. **Overnight gap %.** Wave days: mean +0.144%, median +0.229% (n=20, range -0.641% to
   +0.561%). No-wave days: mean -0.056%, median -0.103% (n=5, range -0.254% to
   +0.296%). Wave days lean toward a positive overnight gap; no-wave days lean flat/
   negative. Full overlap: 08-19 (WAVE, gap +0.391%) sits right next to 08-03 (no-wave,
   gap +0.296%) -- a same-sign gap on both sides of the split.
3. **VIX open vs prior close.** Wave days: mean +0.075, median -0.035 (n=20, range
   -0.72 to +1.17). No-wave days: mean +0.344, median +0.210 (n=5, range -0.20 to
   +0.85). No-wave days lean toward VIX popping UP at the open (a fear-spike/gap-fear
   premarket read); wave days lean flat-to-down. Per C5 this is read as VIX
   *character* at the open, not a level -- and it overlaps heavily (08-17, WAVE, VIX
   open +0.74 sits inside the no-wave range).

**Conditions that do NOT separate (report so this instrument stops re-deriving them):**

4. **First-15-min range / 20-day ATR20.** Wave days: mean 0.246, median 0.234 (n=20,
   range 0.127-0.472). No-wave days: mean 0.345, median 0.353 (n=4, one n/a for
   08-31's missing 1-min cache). This runs the OPPOSITE of the naive "big first 15
   minutes = wave" intuition -- no-wave days had a *larger* early range relative to
   their own ATR20 in this sample. Read as noise at this n, but disclosed because it
   contradicts the intuitive prior rather than confirms it.
5. **VIX 5-day slope.** Wave: mean -0.127 (n=20). No-wave: mean -0.107 (n=5).
   Essentially identical -- no separation.
6. **Prior-day close vs prior-day VWAP %.** Wave: mean -0.026 (n=19). No-wave: mean
   +0.057 (n=5). Small, fully overlapping ranges (wave -0.374% to +0.351%; no-wave
   -0.207% to +0.351%) -- not a real separator at this n.
7. **Distance of the 09:30 print to the nearest key-levels zone.** Wave: mean 0.339,
   median 0.230 (n=18). No-wave: mean 0.332, median 0.250 (n=5). Nearly identical
   distributions -- no separation.
8. **Whether premarket bias called the direction.** Unusable at this n: only 10 of 25
   days have BOTH a parseable premarket bias AND a resolved wave label (8 journal
   files have no "Bias:" line at all -- see method notes). Of those 10, 7 wave-days
   read `True` (bias called it) and 1 `False`; both no-wave days with a bias read
   `True`. Sample too small and too gappy (missing not-at-random -- the no-bias days
   cluster in 08-12..08-17 and all of September) to say anything about this condition
   either way.

**Top separating candidates carried into the W2 prereg:** (1) day-of-week (Monday
under-represented among wave days) and (2) overnight gap % (wave days lean positive).
VIX-open-vs-prior-close (#3) is a secondary/tertiary lean, noted but not carried as a
primary hypothesis leg -- three overlapping legs would dilute an already n=5-limited
kill test. No threshold is proposed for either carried condition; the prereg (`analysis/
recommendations/prereg-wave-day-conditions-10-30-2026-09-05.json`) states the direction
only and evaluates at n>=20 forward sessions per its own kill rule.
