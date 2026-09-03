# VERIFY — T4 sight-check (trendline-sight-check.md), LOOK-AHEAD/DEFINITION lens

Stamp: 2026-09-03T17:52 ET (`et_clock.py` verified: `2026-09-03 17:52:01 Thursday EDT`). Read-only — no files under review edited, no network/broker calls, no writes outside this note.

## Verdict: core finding CONFIRMED independently; one FACT-labeled sub-claim in §5 is WRONG

The primary sight-check verdict — the live engine could not have seen J's rising-support line at the 10:55 candle, for two stacked structural reasons — reproduces exactly under my own independent re-derivation. I found **one concrete factual error**: the report's §5 cross-check claims the premarket-inclusive general-detector's anchors "land on the same two lows J named (08:20 premarket low, 10:10 double-bottom)." They do not — the actual anchor bars are **07:30 ET** and **10:30 ET**, off by 50 and 20 minutes respectively from J's stated 08:20/10:10 anchors. This is stated as **FACT** in the report's FACT-vs-INFERENCE section and is not qualified as approximate; it should be. It does not overturn the primary verdict (which rests on the geometry gap + RTH exclusion, confirmed independently below), but it is a real inaccuracy that inflates how well the "shadow-only fix would recover this exact line" argument actually holds up.

## What I independently re-derived (all matched)

1. **RTH filter location/order** — read `setup/scripts/heartbeat_core.py` lines ~898-927 directly: `df` is RTH-filtered (`>=09:30, <16:00 ET`) on the full multi-day frame *before* `W=150` windowing; `trig_idx = n - 2`; `prior_bars = bars_all[:trig_idx+1]`. Matches the report verbatim.

2. **Resistance-only geometry** — read `backtest/lib/filters.py::detect_trendline_rejection_bearish` (line 758) and `detect_trendline_reclaim_bullish` (line 1101) in full. Both pivot-search exclusively over `window["high"].values` with a `require_decreasing` check; `detect_trendline_reclaim_bullish`'s own docstring confirms it is a **breakout above a descending resistance line** (design choice "(a)" over an ascending-support alternative "(b)", explicitly rejected 2026-07-15) — not a reclaim of a support line at all. No low/support code path exists in either function. Confirmed.

3. **Byte-level bar reconstruction** — rebuilt the RTH-only concatenation myself from `spy_5m_2026-09-0{1,2,3}.json` independently of the study script:
   - Per-day RTH bar counts: 78/78/78 (matches report).
   - Concatenated 10:55 bar lands at absolute index 173, 11:00 at 174 (234-bar concat) → after `W=150` slice, `trig_idx=148` → maps to the **10:55** bar, forward bar → **11:00**. Matches exactly.
   - Trigger-bar OHLC pulled directly from cache: `O768.62/H769.33/L767.45/C769.28` — matches the report byte-for-byte.

4. **Pivot-search replay** — reimplemented the live sequential-descending-highs search independently (not reusing the study script's copy) over `prior_bars.iloc[88:148]` (`window = prior_bars.iloc[bar_idx-lookback:bar_idx]`, `bar_idx=148`, `lookback=60`): found exactly 2 pivots, `(win-idx 135, $770.045)` at `2026-09-03T09:50:00` and `(win-idx 147, $768.83)` at `2026-09-03T10:50:00`, then the search terminates (`search_start=147's_offset+10 >= len(highs)=60`) before a 3rd pivot can be found — `min_swings=3` required, only 2 available. Cross-checked both pivot prices against the raw cache (`09:50` bar high = 770.045, `10:50` bar high = 768.83) — exact match. Confirms `detect_trendline_reclaim_bullish` returns `None` for a structural reason (insufficient pivots), independent of the resistance-vs-support geometry gap.

5. **core-decisions.jsonl ledger** — read the 60-row 10:45–11:06 ET window directly (not via the study script). Row count matches (60). Confirmed exact-match on every quoted row: `trigger_bar_et=10:55:00` rows at `ts_et` 11:01:03/04 through 11:05:xx (both accounts) show `shadow_triggers_fired=['wick_reclaim','pullback_hold']`, `bull_triggers_raw=['level_reclaim','confluence']`, `bull_score=10`, verdict `HOLD`; at 11:06:03/04 `trigger_bar_et` advances to 11:00:00, `bull_score=11`, Safe → `SKIP_BULL_1100_1200`, Bold → `ENTER_BULL`. A full grep of the 60-row window for `"trendline_reclaim"` in `shadow_triggers_fired` returns **zero** matches. All confirmed exactly as reported.

6. **`trendline_detector.py` has zero live/shadow consumers** — repo-wide grep for importers confirms the only non-test/non-research callers are `trendline_chart_draw.py`/`trendline_headless_draw.py` (chart rendering). `trendline_shadow.py` independently confirmed to import `lib.trendlines.detect_trendlines` (the separate scipy module) and glob `spy_5m_*.csv` only — no 15m timeframe anywhere. Matches the report's claim that no 15m trendline geometry exists on any live/shadow path.

## Where the report overclaims (§5, "does ANY detector see it")

Re-ran the exact numbers the report's premarket-inclusive general-detector case rests on, independently:

- `premkt_bars` = today's cache filtered to `timestamp <= 10:55:00` = 84 bars, index 0 = **04:00:00**, index 83 (last) = **10:55:00**.
- Report's cited anchor `bar_index 42, price $764.21, "LL"` → I pulled `upto[42]` directly from the cache: **`2026-09-03T07:30:00`**, low `764.21`. J's stated anchor was the **08:20** ET premarket low. The bar at 08:20 itself has low `764.97` (also checked — the lows across 08:00–08:30 sit in the 764.9–765.6 range, all higher than 764.21). The mechanical anchor is a genuinely different, earlier low, not "≈08:20."
- Report's cited anchor `bar_index 78, price $767.83, "HL"` → `upto[78]` = **`2026-09-03T10:30:00`**, low `767.83`. J's stated anchor was the **10:10** double-bottom low. The actual bar at 10:10 has low `767.53` (lower than 767.83) — a genuine, distinct swing low that I confirmed independently *is* a valid pivot under the module's own `pivot_window=2, inclusive_right=True` rule (both left- and right-side confirmation bars checked directly against cache), yet the algorithm's best-scoring `(anchor_a, anchor_b)` pair did not select it — it picked the later `10:30` low instead (their prices, `767.53` vs `767.83`, are close enough — 30c — that "≈10:10" reads as plausible at a glance, but the bar timestamps are 20 minutes apart and are two different, independently-confirmed pivots).
- `current_value=768.33` and `slope_per_bar=0.1006` recompute exactly from `(764.21, idx42) → (767.83, idx78)` — the arithmetic itself is correct; only the "these are J's anchors" characterization is wrong.

This is stated as **FACT** in the report ("finds one matching J's anchors (764.21≈08:20, 767.83≈10:10, status 'testing')"), not flagged as approximate or inferred, which is a documentation standard the report otherwise holds itself to elsewhere (it correctly labels the "unrelated noise" characterization of the RTH-only line as INFERENCE). The `≈` in the report's own prose is doing more work than the report admits — 50 minutes and 20 minutes is not "≈" for a specific-candle chart read.

## Secondary, minor: slope arithmetic mismatch in the .md prose

The report's §5 table states the RTH-only-window line's slope as "**$0.018/bar**." The underlying JSON (`trendline-sight-check.json` → `general_detector_support_rising_search.rth_only_multiday_no_premarket.lines[0].slope_per_bar`) gives `0.014814814814813972`, and I independently recomputed `(764.75-764.35)/(130-103) = 0.40/27 = 0.0148` from the anchors quoted in the same table — matches the JSON, not the "$0.018" prose figure. Cosmetic (does not change the "unrelated line" conclusion), but another instance of a number in the .md not matching its own underlying JSON.

## LOOK-AHEAD check specifically (the assigned lens)

No look-ahead violation found in any of the reproduced code paths:

- `filters.py`'s pivot window (`prior_bars.iloc[bar_idx-lookback:bar_idx]`) strictly excludes the trigger bar itself; the terminal touch/close check reads only the trigger bar's own (fully-closed) OHLC — standard "known after the bar closes" definition, confirmed by direct read.
- `trendline_detector.py`'s `find_swing_points(window=2, inclusive_right=True)` requires 2 bars *after* a candidate pivot to confirm it (checked directly: `range(window, n-window)` — a pivot at index `n-1` or `n-2` can never be confirmed) — this is right-side confirmation, a legitimate not-yet-look-ahead requirement since the confirming bars are always strictly earlier than the query/"now" bar (`query_bar_index = len(bars)-1`), never later. I explicitly verified this for the winning anchors: idx78's confirming bars (10:35, 10:40) both close before the 10:55 query bar. No case found where a pivot's confirmation reached past the query bar.
- Touch/violation scanning in `_fit_candidate` walks bars `>= anchor_a` only (never credits touches before the line's own first anchor) and the terminal "testing/broken" status uses only the query bar's own close/low — confirmed by direct read of `_build_line_state`.

**Tolerance**: `touch_tolerance_dollars=$0.20` is doing real work in the RTH-only-window "3 touches" result (already flagged by the report itself as inference/unrelated-noise, correctly) but is not decisive for the primary sight-check verdict, which rests on the pivot-count/geometry-class gap, not a tolerance-band judgment call.

## Bottom line

- Primary verdict ("(a) invisible by construction, two independent stacked reasons") — **independently reproduced from source and from raw cache/ledger data, byte-for-byte where checked.** Stands.
- One FACT-labeled claim in §5 (anchor timestamps "match J's own anchors ≈08:20/≈10:10") is **factually wrong** — actual mechanical anchors are 07:30 and 10:30, confirmed against the same cache files the report itself used. Should be corrected to "a structurally similar rising line in the same region, different specific pivots than J's hand-drawn ones" rather than "matches."
- One cosmetic slope-value mismatch between the .md prose (0.018) and its own JSON (0.0148) in the RTH-only "unrelated noise" line.

Neither issue changes the answer to the T4 question itself (would the engine have seen it at 10:55 → no, confirmed two ways independently). They do mean the report's §5 "isolates premarket exclusion as independently sufficient" framing is weaker than stated: the detector, even fed the right (premarket-inclusive) bars, did not reconstruct J's *specific* line — it found a nearby, differently-timed rising-support candidate. The gap the report should own here is not just "the bars are missing" (true) but also "even with the bars present, this particular candidate-scoring algorithm (best-score-wins over ALL swing pairs, not human eyeballing) does not reliably reproduce a human chart-read's exact anchors" — a second, separate mechanism gap the report did not identify.
