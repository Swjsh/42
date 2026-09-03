# Verify (CODE lens): trendline-capability-and-shadow — pass 2

**Stamp:** 2026-09-03T17:52 ET (`setup/scripts/et_clock.py`, market_hours=False)
**Target:** `analysis/deep-research/2026-09-03-money/trendline-capability-and-shadow.md` (+ its .json)
**Lens:** CODE — re-trace every code claim against source, line by line. Any claim without a matching line is refuted.
**Role:** SKEPTIC. Default to refuted unless independently confirmed.

## Verdict: SUPPORTED — every code claim re-traced and confirmed. One non-code (exhibit cross-check) discrepancy found, does not change the verdict.

---

## Code claims re-traced line-by-line (all CONFIRMED)

| # | Claim | File:line | Confirmed |
|---|---|---|---|
| 1 | `trendline_detector.py` DETECTOR_VERSION 1.0.0, built 2026-08-09 | `backtest/lib/trendline_detector.py:104` `DETECTOR_VERSION = "1.0.0"` | YES — docstring dated 2026-08-09 |
| 2 | `kinds=("resistance","support")`, `require_slope=any\|rising\|falling` | `trendline_detector.py:107-108` (`LineKind`), `:443` (`require_slope: Literal["any","rising","falling"] = "any"`), enforced at `:289,296,298` | YES |
| 3 | `anchor_mode` wick/body structurally never mixed (bar-view transform precedes pivot search + assert) | `trendline_detector.py:50-57` docstring + `_body_view` function at `:222` | YES — transform runs before pivot search, matches claim |
| 4 | Defaults: min_touches=3, min_bars_between_touches=6, min_span_bars=6, touch_tolerance=$0.20, pivot_window=2 | `trendline_detector.py:120-136` | YES — every number matches exactly |
| 5 | `heartbeat_core.py` never imports `trendline_detector` | `grep -n trendline_detector setup/scripts/heartbeat_core.py` → 0 hits | YES |
| 6 | RTH-only filter at line 903, before W=150 window slice | `setup/scripts/heartbeat_core.py:903` (`df = df[(_ts.dt.time >= time(9,30)) & (_ts.dt.time < time(16,0))]...`), `:906` `W = 150`, `:907` `win = df.iloc[-W:]` | YES — exact line numbers, exact order (filter before slice) |
| 7 | `prior_bars` fed to the trigger functions comes from this RTH-only slice | `heartbeat_core.py:925-928`: `bars_all = win[[...]].to_dict("records")`; `prior = bars_all[:trig_idx+1]`; `bar_ctx["prior_bars"] = prior` (`:964`) — `win` is the RTH-filtered slice from #6 | YES — full chain traced, no gap |
| 8 | `trend_cache_producer.py` is unrelated to trendline detection (daily-bar regime cache extender, 0 refs) | `grep -in trendline setup/scripts/trend_cache_producer.py` → 0 hits; file docstring confirms it extends `regime_classifier`'s daily-bar cache | YES — correction is accurate |
| 9 | LIVE bear trigger `detect_trendline_rejection_bearish` at `filters.py:758`, pivot HIGHS only, hard-rejects non-decreasing slope | `backtest/lib/filters.py:758-848` — uses `window["high"].values` only (no lows read anywhere in the function); `if require_decreasing and val >= recent_pivots[-1][1]: return None` (early pivot check) AND `if require_decreasing and slope >= 0: return None` (post-fit check) | YES — both rejection points confirmed, exact line |
| 10 | SHADOW-only bull trigger `detect_trendline_reclaim_bullish` at `filters.py:1101`, "byte-identical pivot search" to the bear function | `filters.py:1101-1200` — pivot-search block (MIN_BAR_SEPARATION, highs=window["high"].values, same argmax loop, same least-squares fit) is textually identical to the bear function's block; only the terminal outcome check (closes above vs below) differs, downstream of the shown code | YES — "byte-identical" claim literally true for the pivot-fit portion |
| 11 | Bull mirror deliberately kept in `shadow_triggers`, excluded from `triggers`/scoring | `filters.py:1464-1469` — computed into `shadow_triggers` list, comment states "deliberately kept OUT of `triggers`"; bear trigger at `:1717` feeds directly into `blockers`/live scoring | YES |
| 12 | `trendlines.py::detect_trendlines` is wick-only, no `anchor_mode` param | `backtest/lib/trendlines.py:34-36` docstring: "This detector runs on bar HIGHS and LOWS. Wicks count. If you want body-only trendlines, pre-process bars..." — no `anchor_mode` parameter exists in `detect_trendlines` signature (`:207`) | YES |
| 13 | `trendline_shadow.py` THEO_EVENTS = {(ascending,BREAK),(ascending,REJECT),(descending,REJECT)}, min_touches=3, R²≥0.70, $0.15 tolerance, TP+1.00/stop-0.50/60min time-stop, stop checked first | `setup/scripts/trendline_shadow.py:269-273` (THEO_MIN_TOUCHES=3, THEO_MIN_R2=0.70), `:112` (TOUCH_TOL_USD=0.15), `:271-273` (THEO_TP_POINTS=1.00, THEO_STOP_POINTS=0.50, THEO_TIME_STOP_BARS=12=60min), `:278-279` (THEO_EVENTS set, byte-identical to claim), `:294-297` (stop check precedes tp check in code order) | YES — every constant matches exactly |
| 14 | Refit every 6 bars (30min), min 24 bars (~2h) context | `trendline_shadow.py:110` (REFIT_EVERY_BARS=6), `:111` (MIN_BARS_BEFORE_FIT=24) | YES |
| 15 | Bar source cumulative `spy_5m_*.csv`, includes premarket from 04:00 ET | `trendline_shadow.py:107` `BARS_GLOB = ".../spy_5m_*.csv"`; on-disk `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` first row `2026-05-19 04:00:00-04:00` | YES |

## Ledger/verdict numbers re-derived independently (not just re-read)

Re-computed directly from `analysis/trendlines/shadow-ledger.jsonl` (not copied from the report):
- 4,986 rows, 74 sessions — **matches**
- `(direction,event)` counts: ascending/BREAK 762, ascending/REJECT 439, ascending/RETEST 301, ascending/TOUCH 1,080, descending/BREAK 752, descending/REJECT 436, descending/RETEST 336, descending/TOUCH 880 — **matches every cell exactly**
- `theo_qualifies=True` counts: ascending/BREAK 686, ascending/REJECT 388, descending/REJECT 387, all others 0 — **matches exactly**, including the fact that TOUCH rows never carry a qualifying trade (structural, confirmed at the THEO_EVENTS set level in #13 above, not just an empirical absence)

`analysis/trendlines/shadow-verdict.json` read directly: 73 sessions, n=1,451, +0.0386 pts/trade, WR 40.0%, 39/73 positive sessions, CI [-0.0301, 0.1177], top3=105.4% — **every field matches the report verbatim**, including the two-entry history (2026-08-20 reconstruction + 2026-09-02 recompute) and the "no status field" note on the prereg JSONs (checked all 4: `prereg-trendline-break-at-level-2026-08-13.json`, `prereg-trendline-context-conditioning-2026-08-01.json`, `prereg-trendline-engine-validation-2026-08-09.json`, `prereg-g2-trendline-bypass-2026-08-01.json` — none has a `status` key).

## The four preregs — independently re-verified

- `TRENDLINE-BREAK-AT-LEVEL-2026-08-13` result (`trendline-break-at-level-2026-08-14.json`): `cells` array has exactly 72 entries; `sum(c['survives_bh_fdr_q10'])` = **0**. Matches "0/72 cells survive BH-FDR" exactly.
- `prereg-trendline-context-conditioning-2026-08-01` result (`TRENDLINE-CONTEXT-CONDITIONING-2026-08-01.md`): line 3 literally reads "**Verdict: NULL** — no BH-FDR survivor meets the frozen decision rule," line 7 confirms "16 pre-registered tests." Matches "0/16 BH-FDR survivors" claim.
- `TRENDLINE-ENGINE-VALIDATION-2026-08-09` result (`trendline-engine-validation-2026-08-09.json`): cell_b `total = -27378.25` (exact), `status_counts.ok = 2411` (exact — matches "2,411 replays" even though the pre-status `n_after_dedup_and_window` is 2,452, i.e. 41 dropped for `no_contract`); cell_c `verdict = "KILL"`; cell_d `two_sample_p = 0.9636` (matches "p=0.96"), wick touch-respect 0.4765 vs body 0.4870 (matches "47.65% vs 48.70%" from the companion .md). All four cell claims confirmed.
- `G2-TRENDLINE-BYPASS-INVERTS-PRIORITY-2026-08-01` result (`g2-trendline-bypass-2026-08-01.md/.json`): ARM_EXTEND verdict NULL, ARM_REMOVE verdict NULL — matches "NULL, both arms" exactly.

## One discrepancy found — non-code, does not affect the CODE-lens verdict

The report's §"Premarket eligibility" paragraph cites the companion exhibit file (`trendline-today-exhibit.json`) as follows: *"its `5m_rth_only_asof_1050` detector call ... finds 0 support lines (only 17 RTH bars exist by then); its `5m_full_day_incl_premarket_asof_1050` call at the same instant ... finds 3 candidate support lines."*

Re-read that JSON directly:
- The actual key names are `5m_rth_only_asof_1055_nolookahead` and `5m_full_day_incl_premarket_asof_1055_nolookahead` — **"1055" not "1050"** (the file's own meta documents bar-label = open-of-interval, so the last bar in the no-lookahead-as-of-10:55 window is *labeled* 10:50 and closes at 10:55; the report's "as of the 10:50 close" phrasing is a defensible but non-obvious reading of that convention, not a fabrication).
- The **RTH-only side is confirmed exactly**: 17 bars available, 0 lines found (`n_lines_found: 0`).
- The **premarket-inclusive side count is wrong**: the JSON shows `n_lines_found: 4`, all four with `"kind": "support"` — **4 support lines, not 3** as the report states.

This is a citation-accuracy slip in a cross-referenced companion artifact the report explicitly flagged as *not independently re-derived* ("I did not independently verify... this work already exists in a parallel/sibling artifact... which I read and cited but did not re-derive or re-verify line-by-line" — stated in the report's own caveats). It does not touch any of the 15 code claims above, all of which are independently confirmed against the actual source files this session, and it does not change the structural finding (RTH-only is blind to premarket anchors; premarket-inclusive is not) — only the exact line-count (3 vs 4) is off.

## What was NOT re-verified in this pass (scope discipline)

- The exploratory `mfe_30m +0.67 pts` TOUCH-only mean (report already labels this non-CI'd/exploratory — out of scope for a CODE lens).
- Whether the detector reproduces J's exact narrated anchors bar-for-bar (report explicitly defers this to the sibling exhibit task; this pass only checked the sibling artifact's own internal numbers where cited, per above).
- `backtest/futures/trendline_geometry.py` and `backtest/lib/contracts/models.py` matched a raw `grep -rl trendline_detector` but on inspection both are comment-only mentions (file-ownership note / dict-shape reference), not actual imports — confirmed they are NOT undisclosed consumers the report should have listed. The report's 3-consumer list (`trendline_chart_draw.py`/`trendline_headless_draw.py`, `trendline_timeframe_matrix_2026_08_09.py`, `trendline_validation_cells_2026_08_09.py`) omits a handful of same-day scratch files (`trendline_study_sight-check.py`, `trendline_study_today-exhibit.py`) that do import the module — these are sibling T1/T2 tasks' own scratch tools created during this same investigation window, not pre-existing consumers, so the omission does not misstate the codebase as it stood before this round of work.

## Bottom line

All 15 discrete, checkable code claims (detector capability surface, live-vs-shadow trigger wiring, the heartbeat RTH-window chain, the shadow lane's THEO_EVENTS/constants, and every re-derivable ledger/verdict/prereg number) were re-traced against source this session and matched exactly — nothing here is invented or misquoted. The one error found is a minor citation slip (3 vs actual 4 support lines, and a bar-label vs bar-close timestamp ambiguity) in a companion artifact the report itself flagged as unverified — it does not touch the CODE-lens claims and does not change the finding's substance: the live engine is structurally RTH-only and blind to premarket rising-support anchors; the bull rising-support bounce pattern is logged (1,080 TOUCH rows) but structurally never scored as a trade; the ascending-BREAK pattern (his 14:30 exhibit shape) is the largest scored category and currently shows no statistically clear edge (CI straddles zero, concentration >100%).
