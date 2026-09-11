# Multi-day structure verification — 737.72 floor + uptrend trendline (2026-07-31)

**Scope:** J made two multi-day structural claims after Friday's close. Read-only bar-by-bar
verification against the repo's SIP-sourced 5m cache (`backtest/data/spy_5m_2026-05-19_2026-07-31.csv`,
source `alpaca_sip` per `analysis/backtests/data-versions.jsonl`, ET-stamped, 04:00-16:00 ET coverage
per day = premarket + RTH). All times below are ET. Today (07-31) session low was confirmed
**737.68 @ 10:15 ET** — matches J's stated number exactly.

---

## CLAIM 1 — the 737.72 multi-day floor

### Per-day summary

| Date | Session low (04:00-16:00) | Premarket low (04:00-09:25) | RTH low (09:30-16:00) | Bars within $0.15 of 737.72 |
|---|---|---|---|---|
| 07-24 Fri | 737.29 @ 15:20 | 737.68 @ 04:00 | 737.29 @ 15:20 | 12 |
| 07-27 Mon | 735.87 @ 13:15 | 744.10 @ 04:00 | 735.87 @ 13:15 | 4 |
| 07-28 Tue | 735.98 @ 09:45 | 736.16 @ 04:00 | 735.98 @ 09:45 | 6 |
| 07-29 Wed | 729.10 @ 15:55 | 738.20 @ 04:00 | 729.10 @ 15:55 | 1 |
| 07-30 Thu | 729.88 @ 04:00 | 729.88 @ 04:00 | 734.59 @ 11:15 | 5 |
| 07-31 Fri | 737.68 @ 10:15 | 742.79 @ 08:40 | 737.68 @ 10:15 | 1 |

### Touch ledger (every 5m bar whose LOW came within $0.15 of 737.72, forward reaction over next 30/60 min)

| Date | Time ET | Bar low | Dist. from 737.72 | +30min high (bounce) | +30min low (break) | +60min high (bounce) | +60min low (break) |
|---|---|---|---|---|---|---|---|
| 07-24 | 04:00 | 737.68 | -0.04 | 740.29 (+2.61) | 737.81 (-0.13) | 740.32 (+2.64) | 737.81 (-0.13) |
| 07-24 | 04:05 | 737.81 | +0.09 | 740.32 (+2.51) | 739.08 (-1.27) | 740.64 (+2.83) | 739.08 (-1.27) |
| 07-24 | 09:50 | 737.69 | -0.03 | 739.95 (+2.26) | 737.33 (+0.36) | 739.95 (+2.26) | 737.33 (+0.36) |
| 07-24 | 10:05 | 737.57 | -0.15 | 739.95 (+2.38) | 737.91 (-0.34) | 740.96 (+3.39) | 737.43 (+0.14) |
| 07-24 | 10:40 | 737.84 | +0.12 | 742.17 (+4.33) | 737.43 (+0.41) | 743.25 (+5.41) | 737.43 (+0.41) |
| 07-24 | 14:35 | 737.83 | +0.11 | 738.89 (+1.06) | 737.56 (+0.27) | 738.89 (+1.06) | 737.29 (+0.54) |
| 07-24 | 14:40 | 737.64 | -0.08 | 738.89 (+1.25) | 737.47 (+0.17) | 738.89 (+1.25) | 737.29 (+0.35) |
| 07-24 | 14:45 | 737.79 | +0.07 | 738.89 (+1.11) | 737.41 (+0.38) | 738.89 (+1.11) | 737.29 (+0.50) |
| 07-24 | 15:30 | 737.66 | -0.06 | 746.00 (+8.34) | 737.64 (+0.02) | 746.00 (+8.34) | 737.64 (+0.02) |
| 07-24 | 15:40 | 737.79 | +0.07 | 746.00 (+8.21) | 737.64 (+0.15) | 746.07 (+8.28) | 737.64 (+0.15) |
| 07-24 | 15:45 | 737.75 | +0.03 | 746.00 (+8.25) | 737.64 (+0.11) | 746.07 (+8.32) | 737.64 (+0.11) |
| 07-24 | 15:50 | 737.64 | -0.08 | 746.00 (+8.36) | 738.05 (-0.41) | 746.11 (+8.47) | 738.05 (-0.41) |
| 07-27 | 10:30 | 737.73 | +0.01 | 739.97 (+2.24) | 736.54 (+1.19) | 740.31 (+2.58) | 736.54 (+1.19) |
| 07-27 | 12:05 | 737.72 | **0.00 (exact)** | 739.68 (+1.96) | 736.86 (+0.86) | 739.68 (+1.96) | 736.07 (+1.65) |
| 07-27 | 12:25 | 737.71 | -0.01 | 739.35 (+1.64) | 736.64 (+1.07) | 739.35 (+1.64) | 735.87 (+1.84) |
| 07-27 | 14:10 | 737.62 | -0.10 | 737.83 (+0.21) | 736.62 (+1.00) | 739.58 (+1.96) | 736.62 (+1.00) |
| 07-28 | 06:40 | 737.69 | -0.03 | 738.91 (+1.22) | 737.59 (+0.10) | 739.23 (+1.54) | 737.59 (+0.10) |
| 07-28 | 07:10 | 737.59 | -0.13 | 739.23 (+1.64) | 737.62 (-0.03) | 739.75 (+2.16) | 737.62 (-0.03) |
| 07-28 | 07:15 | 737.63 | -0.09 | 739.23 (+1.60) | 737.62 (+0.01) | 739.75 (+2.12) | 737.62 (+0.01) |
| 07-28 | 07:40 | 737.62 | -0.10 | 739.75 (+2.13) | 738.12 (-0.50) | 740.25 (+2.63) | 737.51 (+0.11) |
| 07-28 | 09:35 | 737.76 | +0.04 | 738.34 (+0.58) | 735.98 (+1.78) | 738.62 (+0.86) | 735.98 (+1.78) |
| 07-28 | 10:45 | 737.86 | +0.14 | 740.57 (+2.71) | 738.01 (-0.15) | 742.45 (+4.59) | 738.01 (-0.15) |
| 07-29 | 14:05 | 737.68 | -0.04 | 739.29 (+1.61) | 735.95 (+1.73) | 742.68 (+5.00) | 735.95 (+1.73) |
| 07-30 | 09:55 | 737.59 | -0.13 | 739.30 (+1.71) | 737.38 (+0.21) | 739.30 (+1.71) | 735.61 (+1.98) |
| 07-30 | 10:20 | 737.62 | -0.10 | 739.30 (+1.68) | 736.09 (+1.53) | 739.30 (+1.68) | 734.59 (+3.03) |
| 07-30 | 10:25 | 737.73 | +0.01 | 739.11 (+1.38) | 735.61 (+2.12) | 739.11 (+1.38) | 734.59 (+3.14) |
| 07-30 | 10:40 | 737.68 | -0.04 | 738.15 (+0.47) | 734.83 (+2.85) | 738.15 (+0.47) | 734.59 (+3.09) |
| 07-30 | 12:40 | 737.75 | +0.03 | 740.13 (+2.38) | 738.00 (-0.25) | 740.24 (+2.49) | 738.00 (-0.25) |
| **07-31** | **10:15** | **737.68** | **-0.04** | **742.50 (+4.82)** | **738.38 (-0.70)** | **743.10 (+5.42)** | **738.38 (-0.70)** |

### Verdict on Claim 1

- **Today's low confirmed: 737.68 @ 10:15 ET.** Exact match to J's number. Single touch,
  no meaningful break below (worst forward low was 738.38, i.e. it never gave the level back),
  strong bounce (+4.82 in 30min, +5.42 in 60min).
- **No bar in six sessions ever printed the exact tick 737.72.** Closest exact prints: 737.71
  (07-27 12:25), 737.73 (07-27 10:30 and 07-30 10:25). This is a **zone**, not a price — consistent
  with J's own "levels are zones" doctrine (`feedback_levels_are_zones_2026_07_17`), not a literal
  penny-level support.
- **07-24 "bottom of the day, twice"** — literally false at the tick level: the session's absolute
  low was 737.29 (RTH, 15:20), $0.43 below 737.72, not the level itself. What IS true: the
  **premarket low (737.68 @ 04:00) and the RTH low (737.29 @ 15:20)** were the day's two session
  extremes and both landed within ~40 cents of 737.72 — that's the most charitable reading of
  "twice." The zone was also tested 8 more times intraday (04:05, 09:50, 10:05, 10:40, 14:35,
  14:40, 14:45, 15:30-15:50 cluster) — far more than twice if counting every touch.
- **07-27 "premarket respected it the whole time"** — true, but trivially: premarket never came
  within $6 of the level (low 744.10 @ 04:00). It wasn't respected, it wasn't tested. The real
  action was in RTH: three bounces off the zone (10:30, 12:05 exact, 12:25) before a clean break
  to 735.87 @ 13:15, then a failed retest-from-below at 14:10.
- **07-28 "premarket respected it the whole time"** — partially true. The very first premarket
  print (04:00) **undercut** the level by $1.56 (low 736.16), then price reclaimed and hovered in
  the 737.6-737.9 zone for the rest of premarket (06:40-07:40). So: broke on the open print,
  reclaimed, then respected for the remainder of premarket — not a clean "respected the whole
  time," but not a false claim either once the open-print undercut is accounted for.
- **07-29 was the breakdown day** (session low 729.10, a $8.62 collapse below the level) — the
  zone acted as a brief failed-bounce point (14:05) mid-selloff, not support.
- **07-30 flips the geometry**: price approached from BELOW (premarket low 729.88, continuing
  Wednesday's selloff) and the 737.6-737.8 zone acted as **overhead resistance**, rejected four
  times (09:55, 10:20, 10:25, 10:40) before finally being reclaimed around midday (13:00 close
  739.95).

**Bottom line: 737.72 is a real, repeatedly-reacted-to zone across all six sessions — but the
"literal bottom, twice" framing overstates precision.** It's a multi-day pivot zone that has
acted as both support (07-24, 07-27, 07-31) and resistance (07-30), which is exactly what a
level with real memory looks like, not a single clean floor line.

---

## CLAIM 2 — the multi-day uptrend trendline

### Anchor resolution

J's stated anchor ("Wednesday the twenty-ninth at seventeen fifty-five") has **no bar at literal
17:55 ET** — that's past the 16:00 close, outside all cached/tradeable data. Checked candidate
misreadings (13:55, 11:55, 09:55, 07:55 ET) — none are structurally distinguished. The bar that
**is** structurally meaningful is **15:55 ET**, the last bar of 07-29's RTH session and the
**exact session low of the entire selloff (729.10)** — "fifteen fifty-five" vs "seventeen
fifty-five" is a one-phoneme slip and 15:55 is the only candidate that's actually a pivot.
Used as anchor A.

Anchor B per J's instruction: 07-30 11:30 ET, `O=734.84 H=736.08 L=734.68 C=736.08` — a local
higher-low (the day's actual absolute low was 5 min earlier at 11:15, 734.59; J's 11:30 bar is
the reversal candle off that low).

**Per J's standing rule (bodies XOR wicks, never mixed): both flavors computed, both reported.**

| Flavor | Anchor A (07-29 15:55) | Anchor B (07-30 11:30) | Slope (trading-hour basis) |
|---|---|---|---|
| WICK (low-low) | 729.10 | 734.68 | +$0.7358/hr |
| BODY (min(O,C)) | 729.51 | 734.84 | +$0.7029/hr |

91 five-minute trading bars (7.58 trading-hours) elapse between the two anchors, counting only
04:00-16:00 ET weekday bars and skipping the overnight/weekend gap — this is how TradingView's
default intraday chart actually renders elapsed distance (gaps compressed), and is the basis
used for the projections below. A naive wall-clock (calendar-hour) alternative is given for
reference but is **not** the chart-realistic number (it stretches the same 2-point slope across
~60 dead hours and produces implausible values — see table).

### Projection: trading-bar basis (chart-realistic) vs actual price

| Checkpoint | WICK line value | BODY line value | Actual price | Gap (actual − line, wick) |
|---|---|---|---|---|
| 07-31 04:00 premarket open | 737.99 | 738.00 | O=745.06 L=744.02 | **+6.0 to +7.0** (never came close) |
| 07-31 09:30 (open) | 742.04 | 741.87 | O=744.68 H=746.30 L=744.58 C=746.00 | **+2.5 to +4.3** |
| 07-31 09:35 | 742.10 | 741.93 | O=745.98 H=746.26 L=744.11 C=744.12 | **+2.0 to +4.2** |
| 07-31 10:15 (session low bar) | 742.59 | 742.40 | L=737.68 | **−4.9** (clean break BELOW) |

### Verdict on Claim 2 — falsifiable Monday projection

**The strict 2-point mechanical fit does NOT put the 09:30/09:35 candle "at the top of the
line."** Price opened and traded $2.50-4.30 ABOVE the projected line value both at 09:30 and
09:35 — it wasn't touching the line, it was floating well above it. Premarket ran $6-7 above the
line the entire morning, so "premarket respected it" is true only in the trivial sense that
price never got low enough to test it. **What the mechanical line DOES confirm**: the 10:15
session-low bar (737.68) sits **$4.9 below** the wick-flavor line (742.59) — a genuine, sizable
break of the ascending support, consistent with "it clearly broke the trend." But the sequence
J described (top-of-line at the open → break → retest-from-underneath → dump) does not match
the actual bar-by-bar path: price fell in a fairly continuous slide from the 09:35 high (746.26)
down to the 10:15 low (737.68) — there's no clean retest-then-second-leg-down in between; it's
one slide, then a sharp V-recovery.

**Independent cross-check against the LIVE production trendline engine** (`backtest/autoresearch/
trendline_engine.py`, fires every 5 min RTH, `analysis/trendlines/trendline-log.jsonl`): its own
best-fit ascending support line, using DIFFERENT anchors than J's (07-30 12:00 → 07-30 14:35,
i.e. its own scored pick, not a human eyeball), computed a current value of **741.96 (wick) /
741.65 (body) at 09:45:02 ET** — within a few cents of this report's independent 2-point fit
(~742.0). Two independently-derived lines landing in the same $741.9-742.1 pocket is strong
convergent evidence that **the real ascending-support value at Friday's open genuinely was
~$742**, not the $744-746 where price actually opened. The production engine's own log shows the
**exact break event**: at the 10:15:02 fire, `status=BROKEN`, `last_close=738.49` vs
`current_value=741.93` (wick). By 10:30:02 the engine had re-anchored to a fresh pair (07-30
11:15 @734.62 → 07-31 10:15 @737.7 — i.e. Thursday's actual low and today's capitulation low)
and returned to INTACT as price recovered.

**Monday 08-03 projection (the falsifiable number), trading-bar basis:**

| Checkpoint | WICK line value | BODY line value |
|---|---|---|
| MON 08-03 09:30 (open) | **$750.87** | **$750.30** |
| MON 08-03 12:00 (midday) | **$752.71** | **$752.06** |

(Wall-clock/calendar-hour alternative, NOT recommended — included only for completeness:
09:30 open ≈ $760.4-761.5, midday ≈ $761.1-762.2. This stretches the 2-point slope across the
full ~60 dead hours of Friday-evening + weekend and is not how the chart or the live engine
renders elapsed distance; it implies an implausible ~$15 gap from Friday's 746.82 close.)

**J's thesis is falsifiable as: if the ascending support line (anchored 07-29 15:55 / 07-30
11:30) is real and still governing, SPY should be finding support/resistance interaction in the
$750-753 zone around Monday's open and midday — a level roughly $4-6 above Friday's 746.82 close.**
Given price already ran $2-4 above this exact line all Friday morning without ever touching it,
the more likely outcome is the line is already stale/overrun (price has been trading above it,
not on it) unless Monday opens with a pullback into that zone.

---

## ENGINE QUESTION 3 — does the level compiler carry multi-day touch history?

**Compiler:** `setup/scripts/refresh_levels_intraday.py` ("Premarket Level-Compiler v2", built
2026-07-27 off a live-flagged incident) writes `automation/state/key-levels.json`.

**Weight formula — a flat 3-tier constant by SOURCE TYPE, not a continuous function of touch
count:**

```python
LEVEL_WEIGHT_INTRADAY = 2       # this script's own intraday levels (PMH/PML/RTH hi-lo/swings)
LEVEL_WEIGHT_PRIOR_DAY_HLC = 3  # yesterday's H/L/C
LEVEL_WEIGHT_SHELF = 5          # multi-week shelf / daily-close cluster (from daily_context.py)
```

(`refresh_levels_intraday.py` lines 82-91)

**Multi-day touch history DOES gate which tier a level lands in, but does NOT scale weight within
a tier.** The only source that earns the top weight (5) is a "shelf" computed in
`setup/scripts/daily_context.py`, which scans **60 calendar days (~40 trading sessions) of DAILY
SIP bars**, clusters O/H/L/C values into a **$1.60-wide band**, and requires **≥3 sessions
touching the band spanning ≥10 sessions** (`SHELF_MIN_TOUCHES=3`, `SHELF_MIN_SPAN_SESSIONS=10`,
`daily_context.py` lines 45-49) before it counts as a shelf at all. The touch count IS computed
and carried in the shelf's `reasoning` string ("Multi-week shelf X-Y ({touches} touches over...")
— but a shelf touched 3 times and a shelf touched 15 times both get the identical flat weight of
5. So: **a level's weight reflects whether prior days interacted with it (binary: shelf vs. not),
not how many.** There is no continuously-scaling function of prior-day touch count anywhere in
this compiler.

---

## ENGINE QUESTION 4 — does the trendline engine draw multi-day lines?

Two trendline code paths exist in the repo. Only one is live.

### Dead path: `automation/scripts/compute_trendlines.py`
Wraps `backtest/lib/trendlines.py`. `--lookback-sessions` defaults to **2** trading sessions,
and **explicitly strips premarket bars** ("Keep RTH bars only (09:30-16:00) — premarket bars
confuse swing detection", line 60). Wick-only (no body-flavor call site). Its output files
(`automation/state/chart_drawings.json`, last modified **Jun 18**; `automation/state/
trendlines.json`, last modified **Jun 20**) are **6+ weeks stale** and the script does not appear
anywhere in `automation/state/SCHEDULED-TASKS.md` — it is not wired to any scheduled fire. Dead
code, not the production path.

### Live path: `backtest/autoresearch/trendline_engine.py`
This IS the production engine — scheduled task `Gamma_Trendlines`, **every 5 min, 09:30-16:00 ET
weekdays** (`SCHEDULED-TASKS.md` line 73), confirmed firing today through 16:00:03 ET
(`analysis/trendlines/trendline-log.jsonl`, `automation/state/trendlines-live.json`).

- **Lookback: `N_DAYS = 5` trading days**, genuinely multi-day. Pivots and line-fitting run
  across the WHOLE lookback window with no per-day reset (`find_pivots`/`_fit` are pure
  index-based) — this was an explicit fix (T8, 2026-07-08) for the exact gap this task is
  asking about: *"the single-day version could not structurally represent a real line J trades
  off that spans multiple days"* (docstring, verified against real 07-06..07-08 data in
  `test_trendline_multiday.py`).
- **Bar timeframe: 5-min**, matches.
- **Body/wick handling: BOTH families detected every fire, structurally never mixed within one
  line** — `_fit`'s own assertion guards that both anchors of a given line come from the same
  accessor (wick=low/high field with a minimum protruding-wick gate; body=min/max(open,close)).
  This directly satisfies J's "bodies XOR wicks, never mixed" rule and is pytest-guarded
  (`test_no_mixed_wick_body_anchors`).
- **Demonstrated live today**: at the 10:15:02 ET fire the engine independently logged
  `status=BROKEN` on its own best-fit ascending support (last_close 738.49 vs. line 741.93),
  then re-anchored by 10:30:02 to a pair almost identical in spirit to what J describes (Thursday
  07-30 11:15 low → today's 07-31 10:15 low). This is real-time, same-day confirmation that the
  multi-day lookback mechanism works as designed.
- **Gap #1 — still RTH-only.** Line 154-155 filters bars to `13:30:00 <= t <= 20:00:00` UTC
  (09:30-16:00 ET). **Premarket is structurally invisible to this engine too** — it cannot see
  or score the premarket leg of J's story ("premarket today... respected it") at all, regardless
  of the 5-day lookback.
- **Gap #2 — shadow-only, not wired to trading decisions.** Explicit in the code:
  *"the engine does NOT trade off these yet (the trendline-as-veto / BOS-break-trigger entry-wire
  is A/B-gated NEEDS-REVIEW)."* It logs and can drive the chart-drawing skill, but the heartbeat
  does not gate entries on it.
- **Minor provenance note (not core to this task):** `trendline_engine.py` fetches its own bars
  live via `feed=iex` (line 141), not the SIP feed used for the cache analyzed above — a possible
  source of small (cents-level) discrepancies between this report's numbers and the engine's own
  logged anchors; not large enough to change any conclusion here but worth a DATA-PROVENANCE.md
  note if it isn't already tracked.

### Blunt yes/no

**Level compiler:** weight is source-type-gated (binary shelf/not-shelf via a multi-week daily
scan), NOT a continuous multi-day-touch-count function.

**Trendline engine:** **YES, the live production engine (`trendline_engine.py` / `Gamma_Trendlines`)
CAN and DOES represent multi-day lines like the one J describes** — it's proven itself today,
live, on close to the exact structure in question. The premise "if the engine only fits within
one session it structurally cannot see what he sees" is **outdated** — that limitation existed
and was fixed 2026-07-08. **The two real gaps that remain are: (1) premarket blindness** (both
trendline paths, dead and live, exclude 04:00-09:30 ET bars entirely), so the engine cannot see
the exact premarket-respect claim J made, and **(2) shadow-only status** — even when the engine
sees and logs a break/retest correctly (as it did today, 10:15 ET), that signal isn't wired to
entries.
