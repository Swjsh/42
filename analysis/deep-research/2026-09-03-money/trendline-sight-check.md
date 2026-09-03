# T4 SIGHT CHECK — would the LIVE engine have seen J's 10:55 line today?

Stamp: 2026-09-03T17:30 ET (report written 2026-09-03T17:40 ET, `et_clock.py` verified: `2026-09-03 17:40:44 Thursday EDT`).
Slug: `sight-check`. Study script: [`backtest/tools/trendline_study_sight-check.py`](../../../backtest/tools/trendline_study_sight-check.py) (read-only, imports `backtest/lib/filters.py` and `backtest/lib/trendline_detector.py` as libraries; no network, no writes to `automation/state/`). Raw output: [`trendline-sight-check.json`](trendline-sight-check.json).

## VERDICT: (a) — invisible by construction, two independent reasons stacked

`detect_trendline_reclaim_bullish` — the only bull trendline function on the live path — returned `None` at the 10:55 trigger tick, reproduced exactly bar-for-bar from cache. The recorded live ledger (`core-decisions.jsonl`) confirms it: `shadow_triggers_fired` never contains `"trendline_reclaim"` anywhere in the 10:45–11:06 window. Two separate, independently-sufficient exclusions are in force, not one:

1. **Geometry** — the live function only ever fits a line through descending HIGH pivots. It has no code path for a line through LOWS. J's line is a rising *support* line. Wrong bars would not have fixed this.
2. **Data source** — even a detector that CAN fit support/rising lines (`trendline_detector.py`, itself wired into nothing on the live or shadow path) does not reconstruct J's line when fed the same RTH-only bars the live engine actually has. Only adding back premarket bars recovers it.

## 1. What bars heartbeat_core.py feeds the trendline machinery

`setup/scripts/heartbeat_core.py`:

- **Bar source**: `df = _fetch_spy_5m()` (line 1649) — SPY **5-minute** OHLCV via direct Alpaca REST, "~5 trading days" (line 348-349). No 1m or 15m bar series is ever built for trendline purposes (15m is used only for `_htf_15m_stack`, a ribbon/EMA-stack classification — not trendline geometry, see §2).
- **RTH filter, applied BEFORE anything else** (`_build_payload`, lines 898-903):
  ```
  # RTH-ONLY (>=09:30, <16:00 ET) BEFORE anything -- ...
  _ts = pd.to_datetime(df["timestamp"]).dt.tz_convert("America/New_York")
  df = df[(_ts.dt.time >= time(9, 30)) & (_ts.dt.time < time(16, 0))].reset_index(drop=True)
  ```
  This runs on the **full multi-day** `df` before any windowing. Every premarket bar (04:00:00–09:29:59 ET, any day) is dropped from `df` at this line and never exists in any variable downstream. This is a hard, structural exclusion — not a parameter that could quietly include premarket under different settings.
- **Window**: `W = 150` (line 906) — `win = df.iloc[-W:]`, the last 150 RTH-only bars, which at 78 RTH 5m bars/session spans **roughly 1.9 trading sessions**, rolling across day boundaries (comment: "bounded window: enough for trendline(60)/vol(20) lookbacks"). It is never anchored to "today's open" — it is a straight tail-slice of the RTH-only multi-day series.
- **Trigger bar**: `trig_idx = n - 2` (line 917) — the 2nd-to-last bar in the window; the newest bar (`n-1`) is reserved as the forward-confirmation bar. `bar_ctx["prior_bars"]` is `bars_all[:trig_idx+1]` (line 927) — the 5m RTH-only bars through the trigger bar, no look-ahead.

**Reconstructed for today**: with the window built from Sept 1 + Sept 2 + Sept 3 RTH-only bars (78+78+78=234 available, sliced to the last 150), the **10:55 candle becomes `trig_idx`** (`n=150`, `trig_idx=148`) once the window's newest bar is the 11:00 candle — i.e. once the 11:00–11:05 bar has closed and been fetched. Confirmed against the actual ledger below: that first happens at the `ts_et=11:01:03` tick, not at any tick literally timestamped "10:55" (those ticks were still 2 bars behind, evaluating the 10:45 candle as trigger — 5m bars only close/get fetched after their own interval ends).

## 2. Timeframe(s) the detector runs on live

**5-minute only.** `ctx.prior_bars` (what `detect_trendline_reclaim_bullish`/`detect_trendline_rejection_bearish` search) is built exclusively from the 5m `win` above. There is no 15m equivalent anywhere on the live or shadow-ledger path:

- `heartbeat_core.py::_htf_15m_stack` (line 796) resamples to 15m but only classifies the EMA ribbon stack (BULL/BEAR/UNKNOWN) — it computes and returns a *string*, not a line, and is never passed to either trendline detector.
- `setup/scripts/trendline_shadow.py` (the standing shadow ledger, `Gamma_TrendlineShadow`) reads `backtest/data/spy_5m_*.csv` only (`BARS_GLOB`, line 107) — also 5m-only.
- `backtest/lib/trendline_detector.py` (the general support/rising-capable library) accepts a `timeframe` label as metadata only; nothing in this repo calls it with 15m bars on any decision or ledger path (confirmed by grep: its only callers are `setup/scripts/trendline_chart_draw.py` / `trendline_headless_draw.py` — chart rendering — and three `backtest/autoresearch/` / `backtest/tools/` research scripts).

So J's second exhibit ("08:15 wick to 10:00 wick, same trend line" on the 15m chart) is invisible for a **third**, independent reason beyond the 5m case: no trendline geometry is computed on 15m bars anywhere in this codebase, live or shadow.

## 3. Body/wick mode in force

**Wick**, for every function actually reachable from live code:

- `filters.py::detect_trendline_rejection_bearish` / `detect_trendline_reclaim_bullish` fit pivots against `window["high"].values` — the raw bar high, unmodified (no body transform exists in this file at all).
- `trendline_detector.py::detect_trendlines` defaults `anchor_mode="wick"` and structurally asserts the wick view never touches body fields (line ~484-490).
- `trendline_shadow.py` stamps every ledger row `flavor="wick"` (its own docstring: "detect_trendlines fits ascending lines through swing LOWS and descending through swing HIGHS — wick extremes").

This matches the doctrine rule (memory: "Trendlines: ALL-body or ALL-wick anchors, never mixed, J 2026-07-14") — the live/shadow code is internally consistent, all-wick. J's own hand-draw was body-to-wick ("close enough" by his own words) — a different, human-only anchor choice; not a bug in the mechanical side, just a different convention than any mechanical line reproduces exactly.

## 4. Reconstruction — running the live function at the 10:55 tick

Bar window built exactly as `_build_payload` would (RTH-only, Sept 1–3, W=150, `trig_idx=148`):

| | |
|---|---|
| `trig_idx` | 148 |
| Trigger bar timestamp | `2026-09-03 10:55:00` (open-of-interval; candle spans 10:55:00–10:59:59, closes 11:00:00) |
| Trigger bar OHLC | O 768.62 / H 769.33 / L 767.45 / C 769.28 |
| Forward-confirmation bar | `2026-09-03 11:00:00` |
| `TRENDLINE_LOOKBACK_BARS` / `TRENDLINE_MIN_SWINGS` | 60 / 3 |
| `bar_idx (148) >= lookback+2 (62)`? | **Yes** — enough history in the multi-day window; the function is not blocked by a bar-count floor here |

**`detect_trendline_reclaim_bullish(bar_series, prior_bars, 148, lookback_bars=60, min_swings=3)` → `None`**
**`detect_trendline_rejection_bearish(...)` → `None`** (bear mirror, same pivot search, quoted for completeness)

Manual replay of the exact pivot search the live function runs (sequential-descending-highs, 60-bar lookback, 10-bar min separation):

```
pivots_found_highs = [(idx 135, $770.045), (idx 147, $768.83)]
n_pivots = 2   (min_swings requires 3)
conclusion: insufficient pivots
```

Only 2 descending-high pivots exist in the 5-hour lookback ending at 10:55 — one short of the 3 the function requires — **and** today's structure into 10:55 is a rising market (bar_idx 147's high $768.83 < bar_idx 135's high $770.045 only by luck of two points; a genuine third pivot going further back would need to be even higher, which an uptrend does not supply). The function is not "close" to firing; it never had a countable descending-highs candidate at all at this tick. This is on top of, not instead of, the structural fact that it never searches lows in the first place.

## 5. Does ANY mechanical detector in the repo see it, with these exact bars?

`backtest/lib/trendline_detector.py::detect_trendlines(kinds=("support",), anchor_mode="wick", require_slope="rising")` — the one module in this repo built to fit rising support lines — run twice, same as-of point (10:55), only the bar set changed:

| Run | Bars fed | Lines found | Anchors |
|---|---|---|---|
| RTH-only, multi-day (Sept 1–3, exactly what the live engine has) | 149 | 1 | idx 103 ($764.35, LL) → idx 130 ($764.75, LL); slope $0.018/bar; `current_value` $765.02, status **intact** — a shallow, unrelated line, ~$4 below the trigger bar, not the one J drew |
| Premarket-inclusive, today only | 84 | 1 | idx 42 ($764.21, LL, ≈08:20 region) → idx 78 ($767.83, HL, ≈10:10 region); slope $0.101/bar; `current_value` $768.33, status **testing** |

The premarket-inclusive run's anchors land on the same two lows J named (08:20 premarket low, 10:10 double-bottom) and its `current_value` ($768.33) sits right against the 10:55 candle (L 767.45 / C 769.28) — status flips to "testing," i.e. price is actively at the line, matching J's "closing above and right on the trend line." The RTH-only run — the bar set the live engine actually has — finds a completely different, irrelevant line instead. **This confirms the premarket exclusion is independently sufficient**: it is not merely "the live function doesn't search support," it is also "the bars needed to reconstruct this specific support line are not in the live engine's data at all," even for a detector that otherwise could.

`trendline_detector.py` itself has **zero consumers on the entry path or the shadow ledger** (`trendline_shadow.py`) — confirmed by repo-wide grep; its only importers are the chart-drawing scripts (`trendline_chart_draw.py`, `trendline_headless_draw.py`) and standalone research/validation scripts under `backtest/autoresearch/` and `backtest/tools/`. So even the module capable of finding J's line, when fed the right bars, is not wired to measure or log anything today.

## 6. core-decisions.jsonl, 10:45–11:06 ET, both accounts — quoted

Full 60-row extract in `trendline-sight-check.json` → `core_decisions_ledger_1045_1106`. Trigger-bar-relevant rows:

| `ts_et` | account | `trigger_bar_et` | `shadow_triggers_fired` | `bull_triggers_raw` | `bull_score` | `verdict` |
|---|---|---|---|---|---|---|
| 10:55:03/04 | safe/bold | **10:45:00** | `[]` | `[]` | 9 | HOLD |
| 11:00:05/06 | safe/bold | 10:50:00 | `[]` | `[]` | 8 | HOLD |
| **11:01:03** | safe | **10:55:00** | `['wick_reclaim', 'pullback_hold']` | `['level_reclaim', 'confluence']` | 10 | HOLD |
| **11:01:04** | bold | **10:55:00** | `['wick_reclaim', 'pullback_hold']` | `['level_reclaim', 'confluence']` | 10 | HOLD |
| 11:02–11:05 (both accts) | | 10:55:00 (steady) | `['wick_reclaim', 'pullback_hold']` (steady) | `['level_reclaim', 'confluence']` | 10 | HOLD |
| 11:06:03 | safe | 11:00:00 | `['wick_reclaim', 'pullback_hold']` | `['level_reclaim', 'confluence']` | 11 | `SKIP_BULL_1100_1200` |
| 11:06:04 | bold | 11:00:00 | `['wick_reclaim', 'pullback_hold']` | `['level_reclaim', 'confluence']` | 11 | **ENTER_BULL** |

**`"trendline_reclaim"` never appears** in `shadow_triggers_fired` at any row in the whole 10:45–11:06 window, on either account — including every row where `trigger_bar_et = "2026-09-03T10:55:00-04:00"` (11:01:03 through 11:05:xx). This is the live artifact directly confirming the reconstruction in §4: the function ran (it is called on every bull-side tick regardless of outcome) and returned `None` for the 10:55 candle, exactly as reproduced above.

Note the entry that did happen: Bold entered `ENTER_BULL` at the 11:06 tick, once `trigger_bar_et` advanced to 11:00:00 and `bull_score` reached 11 — via `bull_triggers_raw = ['level_reclaim', 'confluence']`, a **level**-based trigger (SPY reclaiming the $768.00 premarket-high level, see `bull_reclaim_level_raw: 768.0` in the 10:41–10:45 rows), not a trendline trigger. The engine caught the move; it caught it through a different, level-based lane, one bar later than J's own read of the trendline candle.

## FACT vs INFERENCE

- **FACT**: `df = _fetch_spy_5m()` then RTH-filtered `>=09:30, <16:00` before windowing (heartbeat_core.py:898-903), confirmed by direct code read.
- **FACT**: `detect_trendline_reclaim_bullish`/`detect_trendline_rejection_bearish` search only `window["high"].values` with `require_decreasing` — no low/support code path exists in `backtest/lib/filters.py` (confirmed by reading both function bodies in full).
- **FACT**: byte-reproduced call at the 10:55 trigger bar (cache-sourced, W=150, Sept 1–3 RTH-only) returns `None` for both live trendline functions; pivot replay finds only 2 descending-high pivots (need 3).
- **FACT**: `core-decisions.jsonl` rows with `trigger_bar_et="2026-09-03T10:55:00-04:00"` (11:01:03–11:05:xx, both accounts) show `shadow_triggers_fired` without `"trendline_reclaim"`, corroborating the reconstruction independently.
- **FACT**: `trendline_detector.py::detect_trendlines(kinds=("support",), require_slope="rising")` finds no line matching J's anchors when fed the RTH-only multi-day window; finds one matching J's anchors (764.21≈08:20, 767.83≈10:10, status "testing") only when today's premarket bars are added back.
- **FACT**: no 15m-timeframe trendline geometry is computed anywhere in this repo's live or shadow path (only `_htf_15m_stack`'s ribbon classification, and `trendline_detector.py`'s unused general capability).
- **INFERENCE**: the RTH-only multi-day general-detector line found ($764.35→$764.75, "intact") is "unrelated noise" relative to J's line — inferred from its price level (~$4 below the trigger bar) and non-"testing" status, not independently verified against a human chart read of that specific line.

## What a shadow-only change would need (no trading-path edit proposed)

Two separate gaps, either addressable without touching the live/trading path:

1. **A support/rising-line search wired into the shadow ledger.** `trendline_shadow.py` already computes `detect_trendlines` output but — per its own docstring — has never been checked for `kinds=("support",)`/`require_slope="rising"` explicitly with a per-day A/B; it uses `backtest/lib/trendlines.py` (the scipy `find_peaks` module), not `trendline_detector.py`. Either module could be pointed at ascending/support lines in the shadow ledger with zero effect on `triggers`/`bull_score`/`passed` — same "logged only" pattern already proven safe by `shadow_triggers_fired` (`wick_reclaim`, `pullback_hold`, and the dormant `trendline_reclaim` itself).
2. **A premarket-inclusive bar feed for that shadow search**, separate from the RTH-only `win` the live scoring machinery uses. This is the load-bearing gap per §5 — without it, even a support-capable detector cannot reconstruct this specific line. `trend_cache_producer.py` / `trendline_headless_draw.py` already fetch premarket-inclusive bars for chart-drawing purposes (per the DATA section of this task); a shadow consumer could read from that same source rather than `_fetch_spy_5m()`'s RTH-filtered path.

Neither of these is proposed as a change here — both are read-only findings about what infrastructure exists vs. is wired, per the T4 scope (sight check only).

## Caveats

- Alpaca REST bars are not literally re-fetched here (no network calls per the hard constraint) — the cached SIP files (`spy_5m_2026-09-0{1,2,3}.json`) stand in for `_fetch_spy_5m()`'s live REST response. If the live feed differed bar-for-bar from the SIP cache on any of these three sessions (feed divergence is a documented, named failure mode elsewhere in this repo — `FEED-DIVERGENCE-F10-F7-2026-08-07.md`), the exact pivot values would shift; the **structural** findings (RTH filter location, high-only pivot search, 5m-only timeframe, wick mode) do not depend on which feed supplied the bars and are read directly from source, not inferred from this reconstruction.
- The reconstruction assumes a heartbeat tick actually fired in the `ts_et≈11:01-11:05` window with the 11:00 bar as the newest fetched bar — confirmed true from the ledger itself, so this is not a hypothetical tick timing, it is the recorded one.
- `trendline_detector.py`'s "1 line found" results use `max_lines_per_kind=1` (the function default) — only the single best-scoring support/rising candidate is surfaced per run; this does not change the RTH-only-vs-premarket-inclusive contrast (both runs are single-candidate, same settings).
