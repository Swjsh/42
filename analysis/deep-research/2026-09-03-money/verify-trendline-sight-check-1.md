# VERIFY (STATISTICS lens) — T4 sight-check, run 1

Stamp: 2026-09-03T17:51 ET (`et_clock.py` verified: `2026-09-03 17:51:13 Thursday EDT`).
Target: [`trendline-sight-check.md`](trendline-sight-check.md) / [`.json`](trendline-sight-check.json), script [`backtest/tools/trendline_study_sight-check.py`](../../../backtest/tools/trendline_study_sight-check.py).
Role: SKEPTIC — default to refuted unless independently reproduced. Read-only; no network, no writes outside this note.

## Lens fit — stated up front

The assigned lens (session-clustered CIs, top-3-session removal, time-of-day baseline, tolerance ×0.5/×2) is built for a **rate/points-per-trade study over many sessions**. This finding is not that shape: it is a **single-tick, deterministic code reconstruction** (does one specific function call at one specific bar return `None`?) cross-checked against one ledger window. There is no sampling distribution to bootstrap — `n=1` tick, 3 calendar dates only exist in the window because `W=150` bars span ~1.9 RTH sessions, not because 3 independent trials were run. Session-clustered CI and top-3-session removal do not apply and I did not fabricate ones. Instead I ran the closest defensible analogs: (1) a threshold-robustness sweep on every free parameter (`min_swings`, `lookback_bars`, `touch_tolerance_dollars`, the hardcoded `MIN_BAR_SEPARATION`) at the requested ×0.5/×2 multiples, and (2) a "base rate" pass — how often the *same* live function fires across every other tick in the same 150-bar window, as a time-of-day-agnostic baseline for how ordinary a `None` result is.

## VERDICT: core claim SUPPORTED and independently reproduced; two secondary claims in the report do not hold up and are flagged below

## 1. Reproduction — the script re-run cleanly, byte-identical output

Ran `python backtest/tools/trendline_study_sight-check.py` fresh (exit 0, no stderr). Output matches the committed `trendline-sight-check.json` exactly on every field checked: `trig_idx=148`, trigger bar `2026-09-03 10:55:00` (O768.62/H769.33/L767.45/C769.28), `detect_trendline_reclaim_bullish`→`None`, `detect_trendline_rejection_bearish`→`None`, pivot replay `n_pivots=2` (need 3), general-detector RTH-only line (anchors 764.35/764.75, status `intact`), general-detector premarket-inclusive line (anchors 764.21/767.83, status `testing`).

## 2. Source-line citations — verified against the actual files, not just the report's prose

| Claim | grep/read result |
|---|---|
| RTH filter before windowing | `heartbeat_core.py:898` (`# RTH-ONLY...`), filter applied at 902-903 — **exact line match** |
| `W = 150` | `heartbeat_core.py:906` — **exact match** |
| `trig_idx = n - 2` | `heartbeat_core.py:917` — **exact match** |
| `prior = bars_all[:trig_idx+1]` | `heartbeat_core.py:927` — **exact match** |
| `TRENDLINE_LOOKBACK_BARS=60`, `TRENDLINE_MIN_SWINGS=3` | `filters.py:52-53` — **exact match** |
| Bull/bear trendline functions search only descending HIGHS | Read `detect_trendline_reclaim_bullish` in full (`filters.py:1101-1180+`) — its own docstring states the design choice explicitly ("CHOSE (a)" — reuse the bear function's descending-high pivot search; a support/rising alternative "(b)" was named and rejected as unbuilt) — **confirmed from source, not inferred** |
| `trendline_shadow.py` reads `spy_5m_*.csv` via `backtest/lib/trendlines.py`, not `trendline_detector.py` | `trendline_shadow.py:99,107` — **exact match** |
| `trendline_detector.py` has zero callers on the live/decision/ledger path | `grep -rn "from backtest.lib.trendline_detector import\|from lib import trendline_detector"` across the repo → only `backtest/autoresearch/*`, `backtest/tests/test_trendline_detector.py`, `backtest/tools/trendline_study_*.py`, and `setup/scripts/trendline_chart_draw.py` (imported indirectly by `trendline_headless_draw.py` via `import trendline_chart_draw as tcd`). Zero hits in `heartbeat_core.py`, `trendline_shadow.py`, `filters.py` — **confirmed** |

## 3. Ledger cross-check — independently re-pulled, not copy-checked

Parsed `automation/state/core-decisions.jsonl` myself for `2026-09-03T10:4*`–`T11:0*` (60 rows total in that band). Every field in the report's table reproduces exactly, including the two rows that matter most:

```
2026-09-03T11:01:03 safe 2026-09-03T10:55:00-04:00 ['wick_reclaim','pullback_hold'] ['level_reclaim','confluence'] 10 HOLD
2026-09-03T11:01:04 bold 2026-09-03T10:55:00-04:00 ['wick_reclaim','pullback_hold'] ['level_reclaim','confluence'] 10 HOLD
...
2026-09-03T11:06:04 bold 2026-09-03T11:00:00-04:00 ['wick_reclaim','pullback_hold'] ['level_reclaim','confluence'] 11 ENTER_BULL
```

`"trendline_reclaim"` is absent from every row 10:45–11:06 on both accounts — confirmed. Also checked it isn't a globally-dead string that would make its absence unremarkable: `grep -c "trendline_reclaim" core-decisions.jsonl` → **2833 hits repo-wide**, so the trigger fires routinely on other ticks/days; its absence specifically in this window is a real, meaningful negative, not an artifact of the field never being populated.

## 4. STATISTICS-lens work actually applicable here

### 4a. Threshold robustness — `min_swings` / `lookback_bars` (the live function's real knobs)

At the **live default** (`min_swings=3`), the result is `None` at **every** `lookback_bars` tested (30/60/90/120) — robust in that direction. But at `min_swings=2` (one notch looser — not a ×0.5/×2 move, just the next integer down), the **same function, same geometry** fires: returns `768.73` at all four lookback values. This matters for how the report frames the result:

> report §4: *"The function is not close to firing; it never had a countable descending-highs candidate at all at this tick."*

That is **not accurate** as stated. The function found exactly 2 of the 3 required pivots — one pivot short, which is a near-miss by definition, not "not close." The recomputation shows lowering `min_swings` from 3→2 flips `None`→`768.73` immediately. The **conclusion under the actual live config is still correct** (2 < 3, returns `None`), but "not close to firing" oversells the margin.

### 4b. `touch_tolerance_dollars` sweep (×0.5 / ×1 / ×2) on the general detector's premarket-inclusive line

| Bars | tol ×0.5 ($0.10) | tol ×1.0 ($0.20, default) | tol ×2.0 ($0.40) |
|---|---|---|---|
| RTH-only | anchors (103,764.35)→(130,764.75), `intact` | same | **different** anchors (38,759.48)→(123,765.07), still `intact`, still not J's line |
| premarket-inclusive | **different** anchors (34,764.36)→(51,764.96), current $766.09 | anchors (42,764.21)→(78,767.83), `testing` — the anchors the report cites as matching J | same as ×1.0 |

**The premarket-inclusive "match to J's anchors" is NOT robust at ×0.5 tolerance** — tightening the touch tolerance to $0.10 loses J's line entirely and substitutes an earlier, tighter pair. It IS robust upward (×2 unchanged). This is a real fragility the report's §5 doesn't disclose — the cross-check's headline result depends on sitting at (or above) the library's own default tolerance, not on some tolerance-independent geometric fact.

### 4c. Anchor-timestamp check — the report's §5 "matches J's own anchors" claim does not hold up

I independently pulled the actual bar rows at `bar_index 42` and `bar_index 78` of the premarket-inclusive series from the raw cache (`spy_5m_2026-09-03.json`, 148 total bars, first bar 04:00:00):

```
idx 42 → timestamp 2026-09-03 07:30:00, low=764.21   (report claims "≈08:20 region")
idx 78 → timestamp 2026-09-03 10:30:00, low=767.83   (report claims "≈10:10 region")
```

Both are **off** — 42 is actually 07:30 ET (50 min before 08:20), and 78 is actually 10:30 ET (20 min after 10:10). Checking what the bars actually at 08:20 and 10:10 look like: idx 52 (08:20:00) has low $764.97 — a *different*, higher low than the $764.21 the algorithm anchored on; idx 74 (10:10:00) has low $767.53 — a *different*, lower low than the $767.83 the algorithm anchored on (i.e. the algorithm didn't even pick the actual local minimum at 10:10; a lower low exists 20 minutes earlier that it skipped over, consistent with `min_bars_between_touches`/pivot-window mechanics, but it means the "same lows J named" claim is wrong on both ends — different bars, different prices, only coincidentally nearby).

This means report §5's illustrative cross-check ("its anchors land on the same two lows J named... matching J's own anchors") **overstates the match**. The two lines are in the same rough price neighborhood and both flip to a "the line is being tested right now" status at the trigger bar — that qualitative point survives — but the specific claim of anchor correspondence to J's named touch times is not supported by the actual bar data and should be corrected or softened in the report.

### 4d. Base-rate / time-of-day-baseline analog

Ran `detect_trendline_reclaim_bullish` (live defaults) across every eligible tick in the same 150-bar window (idx 62 through 147, 87 ticks, spanning 2026-09-01 through 2026-09-03 — the only 3 sessions the window can contain): **6/87 fire (6.9%), 81/87 return `None`.** A `None` outcome is the overwhelmingly typical result for this function generally, not something specific to 10:55 today — this actually *supports* the report's core point (nothing anomalous singled out the 10:55 tick; it behaved like ~93% of ticks in-window) even though it undercuts the "not close" language in §4a above (2-of-3 pivots is still a common near-miss shape, evidently, not a rare structural failure).

Session clustering / top-3-session removal: not meaningful here — only 3 calendar dates exist in the 150-bar window by construction (not by trial count), and this is a single boolean outcome, not a rate with a confidence interval to shrink.

## Recomputed numbers (for the record)

- RTH-only general-detector line slope: **0.0148 $/bar** (`(764.75-764.35)/(130-103) = 0.40/27`), reproduced from the raw `trendline-sight-check.json` (`slope_per_bar: 0.014814814814813972`). The **markdown report states "$0.018/bar"** for this same line — a transcription error (~22% off from the JSON it's sourced from). Non-fatal (doesn't change "unrelated line" conclusion) but should be fixed for accuracy.
- Premarket-inclusive line slope: JSON `0.10055555...` → report's "$0.101/bar" is a correct rounding.
- Live-function base rate in-window: 6/87 = 6.9% fire rate at live defaults.
- Pivot near-miss margin: 2 of 3 required pivots found; flips to firing at `min_swings=2` (not merely a distant miss).

## FACT vs INFERENCE (this verification pass)

- FACT: script reproduces byte-identical on fresh execution.
- FACT: all 5 source-line citations checked against current file contents are exact.
- FACT: ledger window independently re-pulled matches the report's table exactly; `trendline_reclaim` absent in-window despite firing 2,833 times elsewhere in the same file.
- FACT: `touch_tolerance_dollars` ×0.5 breaks the premarket-inclusive anchor match; ×2 does not.
- FACT: anchor bar_index 42/78 timestamps (07:30, 10:30) do not match the report's claimed "≈08:20"/"≈10:10" regions; the true local lows at 08:20 and 10:10 are different bars with different prices than what the algorithm anchored on.
- FACT: base rate of the live function firing across the in-window ticks is 6.9% (6/87).
- INFERENCE: none of the above overturn the report's primary VERDICT (the live engine, at actual live defaults, did not and structurally could not have surfaced J's rising-support line at the 10:55 tick) — that conclusion rests on the RTH-filter/high-only-geometry code facts and the ledger's absence of `trendline_reclaim`, both independently confirmed here.

## Overall call

Primary claim (engine invisibility at 10:55, via two independent structural reasons) — **CONFIRMED**, independently reproduced from source and from a fresh ledger pull, not merely re-read from the report.

Two secondary claims in the report are **not supported** as stated and should be corrected: (1) the RTH-only line's slope figure ($0.018/bar — actual $0.0148/bar), and (2) §5's claim that the premarket-inclusive detector's anchors "match J's own anchors" / land on "the same two lows J named" — the actual bar timestamps and prices at those anchor indices are measurably different from the 08:20/10:10 bars J referenced, and the match is not robust to a tighter (×0.5) touch tolerance. The "not close to firing" framing in §4 is also an overstatement — the live function missed by exactly one pivot, a near-miss, not a wide margin — though a base-rate check shows `None` is the ordinary outcome for this function regardless (6.9% fire rate in-window), which is a fair mitigating point in the report's favor.

No fatal flaw was found in the core code-tracing verdict. The errors found are corroboration/framing overstatements in the report's secondary evidence, not in its central claim.
