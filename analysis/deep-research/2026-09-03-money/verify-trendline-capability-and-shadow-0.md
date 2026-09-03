# SKEPTIC verification — trendline-capability-and-shadow (T1)

**Stamp:** 2026-09-03T17:43 ET (`setup/scripts/et_clock.py`, market_hours=False)
**Lens:** LOOK-AHEAD / DEFINITION — were anchors confirmed pivots at the time of the touch? Does touch/break use only the closed bar? Is tolerance doing the work? Rebuilt exhibit bars and re-derived the line myself.
**Target report:** `analysis/deep-research/2026-09-03-money/trendline-capability-and-shadow.md`

## Verdict: NOT REFUTED, but the exhibit-linkage claim is materially overstated — downgrade confidence on that one line

Every checkable factual/code claim in the T1 report reproduced exactly under independent re-derivation. The one place the report reaches past what it verified — tying the aggregate ascending/BREAK category to "J's 14:30 exhibit" — fails when checked against the actual production ledger for the exact day in question.

## What I independently confirmed (all matched, no daylight)

1. **RTH-only filter, order of operations.** Read `setup/scripts/heartbeat_core.py:898-907` directly: the `_ts.dt.time` filter to `[09:30, 16:00)` runs immediately, *before* `W=150` is sliced at line 906-907. Premarket bars are excluded from `df` itself, so `W`'s size is irrelevant — confirmed exactly as claimed.
2. **Live/shadow trigger geometry.** Read `backtest/lib/filters.py:758` (`detect_trendline_rejection_bearish`) and `:1101` (`detect_trendline_reclaim_bullish`) in full. Both use `window["high"].values` only (no lows), both hard-reject any non-strictly-decreasing sequential-peak pick when `require_decreasing=True` (default). Bull function's docstring explicitly states it reuses the bear function's descending-pivot search "byte-identical," confirmed by diffing the pivot-search block — identical `MIN_BAR_SEPARATION=10`, identical global-max-then-next-max loop. Neither implements an ascending-support geometry. Matches report exactly.
   - Minor accuracy note not in the report: the bear function's own docstring describes its pivot method as "local-high pivots (a bar's high > both neighbors)," but the actual code is a *global-max, then next global-max ≥10 bars later* search, not a local-neighbor test. Doesn't change any conclusion (still causal, still highs-only) but the docstring itself is a stale description of its own algorithm.
3. **`trendline_detector.py` capability + anchor_mode guarantee.** Read the file directly: `_view_for_mode` swaps the bar view once before any pivot search (line ~249), `detect_trendlines(...)` asserts `anchor_mode=="wick"` accesses raw high/low and `anchor_mode=="body"` accesses `max/min(open,close)` and never the other (lines ~484-492). Structural, not just documented. Confirmed.
4. **`trendlines.py` (what `Gamma_TrendlineShadow` actually runs) has no `anchor_mode` — wick-only, via `find_peaks` on raw `high`/`low`.** Confirmed by reading the file; report correctly attributes the body/wick guarantee to a module the shadow does *not* use, and correctly attributes wick-only to the module it *does* use. No conflation.
5. **`THEO_EVENTS` excludes ascending-TOUCH.** Read `setup/scripts/trendline_shadow.py`: `THEO_EVENTS = {("ascending","BREAK"), ("ascending","REJECT"), ("descending","REJECT")}`. Confirmed — the bounce pattern structurally cannot become a theoretical trade today.
6. **No look-ahead in the shadow's fit or event classification (C6 claim holds up under direct trace).**
   - Refit: `if i >= MIN_BARS_BEFORE_FIT and i % REFIT_EVERY_BARS == 0: lines = detect_trendlines(day.iloc[:i])` — `day.iloc[:i]` excludes bar `i`. The freshly-fit lines are then used to classify bar `i` itself and the next 5 bars until the next refit. Fit always strictly precedes use.
   - Pivot confirmation: `find_peaks` runs on `bars[0:i]` only (via `_find_swing_indices`); a peak near the array's tail still needs `distance_bars=3` lower neighbors *within that same truncated array* to register, so the newest confirmable pivot always lags several bars behind `i`. No future data enters the swing search.
   - Touch/break classification reads `bar["low"]/["high"]/["close"]` — i.e., the bar's own, fully-closed OHLC — never a later bar's.
   - **This part of the report is accurate: the shadow mechanism is genuinely causal as coded.**
7. **Ledger composition — recomputed independently from the raw JSONL, not copied from the report:**
   ```
   (ascending, BREAK)  762   |  (descending, BREAK)  752
   (ascending, REJECT) 439   |  (descending, REJECT) 436
   (ascending, RETEST) 301   |  (descending, RETEST) 336
   (ascending, TOUCH) 1080   |  (descending, TOUCH)   880
   theo trades: ascending/BREAK 686, ascending/REJECT 388, descending/REJECT 387 = 1461 total
   ```
   Byte-for-byte match on every row/theo count in the report's table.
8. **Verdict-file numbers.** Read `analysis/trendlines/shadow-verdict.json` directly: 73 sessions, n=1451, +0.0386 pts/trade, 95% CI [-0.0301, 0.1177], top-3 share 105.4%. Matches exactly. The **1461 (my fresh count, includes today) vs 1451 (verdict file, dated 2026-09-02) discrepancy is NOT an error** — I traced it: today's ledger (2026-09-03, read live) added exactly 10 new theo-qualifying rows (06:50, 07:30, 10:00-asc, 10:15, 12:30, 12:35, 15:00, 15:10, 15:20, 15:30), and 1451+10=1461. The verdict file is honestly one day stale, as its own "latest date: 2026-09-02" label discloses.
9. **Preregs.** Spot-checked file existence and `status` field absence for all four cited paths — matches the report's "no status field ≠ never run" framing; did not re-verify each prereg's internal statistical result (out of scope for this lens pass).

## Where the LOOK-AHEAD/DEFINITION lens actually breaks something: two findings the report did not surface

### Finding A — "touch" tolerance is not doing the restrictive work the $0.15 number implies

`trendline_shadow.py`'s touch test:
```python
touched = (bar["low"] - TOUCH_TOL_USD) <= proj <= (bar["high"] + TOUCH_TOL_USD)
```
This is "does the line's projected price fall inside this bar's own high-low range, padded by $0.15 on each side" — **not** "is price within $0.15 of the line." For any 5m SPY bar with a realistic intrabar range (the 10:55 bar today, for instance, spans $1.88 high-to-low), the $0.15 pad is negligible next to the range doing the actual work. A "touch" under this definition fires whenever the line merely passes through the bar's candle body/wick span — a materially looser bar than "price approached the line to within 15 cents." This isn't a bug (the function is internally consistent and coded exactly as intended, and the report accurately describes the $0.15 number), but the report never flags that the nominal tolerance is nearly meaningless relative to bar-range noise, which matters directly for weighing the 1,080-row ascending-TOUCH population the report's own "Gap" section proposes building a THEO_EVENTS category on top of — that population is looser/noisier than the flat "$0.15 tolerance" phrasing suggests.

### Finding B — rebuilt today's exhibit from raw 1m bars myself; the actual production shadow ledger does not contain J's 14:30 break

Per the lens instruction, I aggregated `backtest/data/spy_sip_cache/spy_1m_2026-09-03.json` (673 1m bars) into 5m/15m bars myself, independent of the sibling `trendline-today-exhibit.json` file the T1 report cites. My rebuild reproduced that file's anchor bars **exactly**:
- 5m 08:20: o=764.9999 h=765.48 l=764.97 c=765.47 v=2359 — match
- 5m 10:10: o=767.83 h=768.38 l=767.53 c=768.36 v=480565 — match
- 5m 10:55 candle: o=768.62 h=769.33 l=767.45 c=769.28 — match
- Naive 2-point line (08:20 low 764.97 → 10:10 low 767.53, slope $0.02327/min) projects to **768.5773** at 10:55 and **773.5809** at 14:30 — matches the exhibit file's math exactly.

Then I went one step further than either existing artifact and pulled the **actual, already-run** `analysis/trendlines/shadow-ledger.jsonl` rows for `date == "2026-09-03"` (27 rows, the real `Gamma_TrendlineShadow` output for today, not a re-derivation):

- The only ascending-line event near J's 10:55 bounce is a **TOUCH** at 10:55 with `line_price=768.03` — a **$0.55 discrepancy** from the naive 2-point line's 768.5773 (larger than every tolerance the sibling exhibit tested: 0.10/0.20/0.30). The production detector fit a *different* line than the one J describes drawing by eye, because it's anchored on its own `find_peaks`-selected swing lows, not literally the 08:20/10:10 points J named. `touch_count=3, r2=0.9949` — a real 3-touch line, just not J's line.
- **There is no ascending BREAK, REJECT, or TOUCH event of any kind between 12:35 and 15:00** in today's ledger — an 85-minute gap that fully spans J's stated 14:30 break. The nearest ascending BREAK before the gap is at 12:30 (line=772.96); the nearest one after is at 15:00 with `line_price=778.67` — a value ~$5 away from anything near 773.5-773.9 (the actual price at 14:30), i.e. a wholly different, newly-formed line, not a continuation broken at 14:30.
- Raw price action around 14:30 is also not a sharp single-bar break: the 5m 14:25 bar closes 773.73, the 14:30 bar closes 773.86 (**up**, not down), and SPY only drifts down to 772.77 by the 16:15 close — a gradual ~$1.09 fade over 1h45m, not a discrete break-and-decline bar. That shape is consistent with why no `BREAK` event fired: this detector's break test is a single-bar `close` crossing the line, not a multi-bar drift.

**So: the report's own words — "(ascending, BREAK)... 686 theoretical trades, bias=bearish. This is exactly J's 14:30 exhibit shape"** — are true only as a *geometry-class* statement (ascending-line-breaks-bearish is the same shape family as J's description). Read as "this mechanism captured today's specific exhibit," it is false: the running shadow lane fired no break event near 14:30 today, and its 10:55 line differs from J's line by more than any tested tolerance. The T1 report's own caveats section already flags that it "did not independently verify that the detector reproduces J's EXACT narrated anchors... did not re-derive or re-verify line-by-line" and attributes that work to the sibling exhibit file — but that sibling file *also* never checked the actual production ledger output, only a manual two-point projection. Neither existing artifact had actually looked at what `Gamma_TrendlineShadow` produced for today until this pass did.

### Secondary methodological note (not independently a refutation, but relevant to both findings above)

`trendline_shadow.py` keys persistent per-line state by `(direction, round(slope_per_sec,10), round(intercept_price,4))`, and lines are refit from scratch (not incrementally tracked) every 6 bars. A continuously-present real trendline whose least-squares fit shifts even slightly between refits (new swing added, existing swing re-weighted) gets a **new** dict key — silently resetting its `broken` state and splitting what a human would call one line's history across multiple key-identities. This is consistent with what's observed above (a 10:00 ascending BREAK at line=768.55, then fresh ascending TOUCH events at a *lower* line value 767.75→768.03 through 10:30-10:55 — plausibly the "same" support line re-emerging under a new fit key after refit, rather than a real re-touch of the broken line). Not evaluated deeply here (out of scope for this pass), but it means BREAK/TOUCH/REJECT counts in the ledger are not guaranteed to correspond 1:1 with a human's count of "how many times did price interact with visually-the-same line" — worth a follow-up note if anyone builds the proposed ascending-TOUCH THEO_EVENTS study on this ledger.

## Bottom line for the parent session

- Keep the T1 report's capability inventory, live/shadow trigger table, ledger stats, verdict numbers, RTH-only finding, and prereg-resolution table — all independently reproduced this session from source, byte-for-byte where checkable.
- Downgrade or drop the one line equating the aggregate ascending/BREAK category with "J's 14:30 exhibit" — on the actual data for that exact day, the production shadow ledger shows no break event near 14:30 and a materially different fitted line at 10:55 than J's hand-drawn one.
- If a follow-up (T2) study is built on this ledger, note Finding A (loose touch tolerance) and the line-identity-churn note before trusting TOUCH/BREAK counts as clean, mutually-exclusive events per physical line.

## Verification method / what I ran

- `python setup/scripts/et_clock.py` for the timestamp.
- Read `heartbeat_core.py`, `filters.py` (both trendline functions in full), `trendline_detector.py` (docstring + anchor_mode implementation), `trendlines.py` (full file), `trendline_shadow.py` (full file) directly from disk this session.
- Loaded `backtest/data/spy_sip_cache/spy_1m_2026-09-03.json` (673 bars) and independently aggregated to 5m/15m bars in a throwaway script (`scratchpad/rebuild_exhibit.py`), matching the "bar label = open-of-interval" convention stated in the sibling exhibit file, then cross-checked every anchor value against `trendline-today-exhibit.json`.
- Read `analysis/trendlines/shadow-ledger.jsonl` (4,986 rows) directly and recomputed the full direction×event and theo-trade breakdown via a one-off Python `Counter`, and separately isolated `date=="2026-09-03"` to inspect the day's actual fired events.
- Read `analysis/trendlines/shadow-verdict.json` directly.
- No file outside this report and the throwaway scratchpad script was written or modified. No trading-path file touched. No network/broker calls made.
