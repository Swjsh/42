# VERIFY (CODE lens) — T4 trendline sight-check, pass 2

Stamp: 2026-09-03T17:46 ET (`et_clock.py`: `2026-09-03 17:46:46 Thursday EDT`).
Target: `analysis/deep-research/2026-09-03-money/trendline-sight-check.md` + `.json` + `backtest/tools/trendline_study_sight-check.py`.

## VERDICT: REFUTED (the narrow literal claim holds; the report's headline/proposed_change claim does not)

Every low-level code citation in the report — `heartbeat_core.py` line numbers, `filters.py` function bodies, the `core-decisions.jsonl` ledger rows — re-traces exactly and I independently re-ran the study script from scratch (fresh interpreter, byte-diffed against the committed JSON: **identical**). That part of the report is solid.

But the report's headline ("invisible by construction, two independent reasons stacked... no support/low code path exists at all... anywhere in this repo's live or shadow path") and its "What a shadow-only change would need" section (proposing to build "a support/rising-line search wired into the shadow ledger" as future work) are **false**. A support/rising-line search has been wired into the shadow ledger since 2026-08-20, it is a registered scheduled task (`Gamma_TrendlineShadow`), and its output for TODAY shows a `TOUCH` event on an ascending line **at the exact 10:55:00 ET tick J called out**, with a line price sitting inside that candle's high/low range. The report never opened this file.

## 1. Re-traced claims that HOLD (source-line exact)

| Report claim | Source | Verified |
|---|---|---|
| RTH filter before windowing | `setup/scripts/heartbeat_core.py:898-903` | Exact text match, confirmed by `grep -n` |
| `W = 150` / `trig_idx = n - 2` | lines 906, 917 | Exact match |
| `prior_bars` = `bars_all[:trig_idx+1]` | line 927 (`prior = ...`), stored as `"prior_bars": prior` at line 964 | Exact match |
| `df = _fetch_spy_5m()` | line 1649, `_fetch_spy_5m` def at line 348 | Exact match |
| `_htf_15m_stack` returns a ribbon-stack string only, never fed to trendline fns | lines 796-804 (`return rb["stack"] if rb else None`), only call site line 971 (`"htf_15m_stack": _htf_15m_stack(...)`) | Exact match — no other caller |
| `detect_trendline_rejection_bearish` / `detect_trendline_reclaim_bullish` fit **only** `window["high"].values`, sequential-descending-peaks, `require_decreasing` | `backtest/lib/filters.py:758-864` (bearish), `:1101-1206` (bullish) | Read both bodies in full — confirmed no low/support code path exists in either function. The bullish function's own docstring (`filters.py:1111-1130`) explicitly documents this as a **deliberate geometry choice**: "CHOSE (a)" (descending-high breakout) over "(b)" (ascending-support reclaim) |
| `TRENDLINE_LOOKBACK_BARS=60`, `TRENDLINE_MIN_SWINGS=3` | `filters.py:52-53` | Exact match |
| Shadow-only wiring: result appended to `shadow_triggers_fired`, never to `triggers`/`bull_score`/`passed` | `filters.py:1440-1467` | Exact match, comment explicitly states "kept OUT of `triggers`" |
| `trendline_detector.py` default `anchor_mode="wick"`, structural assert at "~line 484-490" | actual lines 437, 483-490 | Matches (off by ~1 line, immaterial) |
| `LineKind = Literal["resistance","support"]`, pivots via `crypto.lib.trendlines.find_swing_points` | `trendline_detector.py:88, 107` | Exact match |
| `trendline_shadow.py` reads `spy_5m_*.csv` via `BARS_GLOB` | line 107 | Exact match |
| `core-decisions.jsonl` 10:45–11:06: `shadow_triggers_fired` never contains `"trendline_reclaim"`; row shape at 11:01:03/04, 11:06:03 (`SKIP_BULL_1100_1200`)/11:06:04 (`ENTER_BULL`) | direct `jsonl` parse, both accounts, full 10:40-11:09 window | **Byte-for-byte match** to the report's table, including `bull_score` progression 9→8→9→8→10→11 and the exact verdicts |
| Fresh re-execution of `trendline_study_sight-check.py` (copied to scratchpad, `REPO_ROOT` hardcoded, run under `backtest/.venv`) | — | `diff` against committed `trendline-sight-check.json`: **zero differences**. `trig_idx=148`, trig bar OHLC 768.62/769.33/767.45/769.28, both live functions → `None`, pivot replay `[(135,770.045),(147,768.83)]` n=2 (need 3), general-detector RTH-only line (764.35→764.75, "intact"), premarket-inclusive line (764.21→767.83, "testing") — all reproduced exactly |

So on the literal T4 question as scoped ("would the LIVE engine have seen it... check core-decisions.jsonl 10:45-11:06 for shadow_triggers_fired") — **yes, confirmed, the live engine never saw it and the ledger proves it.**

## 2. The claim that is REFUTED: "no support/low code path exists... anywhere in this repo's live or shadow path"

The report's §5 treats `backtest/lib/trendline_detector.py` as "the one module in this repo built to fit rising support lines" and states (fact #12) that `trendline_shadow.py` — the actual standing shadow ledger — "uses `backtest/lib/trendlines.py`, a different scipy-based module," then drops the thread. It never opens that module or the ledger it writes.

**`backtest/lib/trendlines.py`** (a *third*, distinct module from both `filters.py`'s live functions and `trendline_detector.py`) has its own docstring, lines 1-13:

```
1  """Auto-trendline detection — finds ascending and descending trendlines in OHLCV bars.
...
6  2. For every pair of swing-highs, fit a candidate descending trendline. For every
7     pair of swing-lows, fit a candidate ascending trendline.
```

This module fits **ascending (support) lines through swing LOWS** — the exact geometry the report says has "no code path... at all" in the repo.

**It is wired, not orphaned.** `setup/scripts/trendline_shadow.py:97-100`:
```python
def _detect_trendlines():
    """backtest/lib/trendlines.detect_trendlines, imported on demand (it needs pandas)."""
    from lib.trendlines import detect_trendlines
    return detect_trendlines
```
called every 6 bars in `_events_for_session` (line ~163: `lines = _detect_trendlines()(day.iloc[:i])`), no look-ahead (fit uses `day.iloc[:i]` only, C6-compliant), writing FORMED/TOUCH/BREAK/RETEST/REJECT events to `analysis/trendlines/shadow-ledger.jsonl`.

**It is registered and running**, not a stray script — `automation/state/SCHEDULED-TASKS.md:218`, `Gamma_TrendlineShadow`, daily 16:22 ET, quoted verbatim:
> "**The trendline shadow ledger — J-directed 2026-08-20** ("we need to check EVERY SINGLE DAY: do we see any trend lines? how do we act on them?")... Wraps `backtest/lib/trendlines.py::detect_trendlines` — which fits ASCENDING lines from swing lows, is well-tested, and had ZERO consumers — into an append-only ledger... **Why it exists:** `filters.py::detect_trendline_rejection_bearish` — the only trendline detector on the entry path — reads pivot HIGHS and hard-rejects non-decreasing slopes, so ascending support/break/retest is invisible BY CONSTRUCTION... J's 2026-08-20 line... could never have been seen."

The task itself was J asking this exact question five weeks ago, and this instrument was built specifically to answer it. `trendline_shadow.py`'s own docstring (lines 14-24) records a **second confirmed catch**: "SECOND OCCURRENCE (J, 2026-08-27) — the lane worked as designed... THIS ledger caught it: an ascending wick BREAK at 13:30..." — i.e. the "gap" the sight-check report proposes to fill as future work was closed and validated two weeks before this task ran.

## 3. Direct evidence: the shadow ledger caught TODAY's line, at the exact tick

The bar source for `trendline_shadow.py` (`backtest/data/spy_5m_2026-05-19_2026-09-03.csv`) is **premarket-inclusive** — confirmed by reading it directly:
```
$ head -3 backtest/data/spy_5m_2026-05-19_2026-09-03.csv
timestamp_et,open,high,low,close,volume
2026-05-19 04:00:00-04:00,738.97,739.33,735.35,738.71,100777
$ grep "^2026-09-03" ... | head -1
2026-09-03 04:00:00-04:00,765.18,766.53,763.59,766.2,86690
```
144 bars for 2026-09-03 (04:00 ET onward) — this is the RTH-exclusion gap the sight-check report correctly diagnosed for the *live* engine, but this shadow lane does not have it: it never filters to RTH before fitting.

`analysis/trendlines/shadow-ledger.jsonl`, filtered to `"date": "2026-09-03"`, ascending-direction rows near 10:55 (anchor timestamps converted to ET):

```
2026-09-03T10:00:00 BREAK  ascending  768.55  anchors: 07:30=764.21, 07:45=764.76, 09:05=766.96
2026-09-03T10:15:00 REJECT ascending  768.99  anchors: 07:30=764.21, 07:45=764.76, 09:05=766.96
2026-09-03T10:30:00 TOUCH  ascending  767.75  anchors: 05:55=764.70, 09:05=766.96, 10:10=767.53   touch_count=3  r²=0.9949
2026-09-03T10:35:00 TOUCH  ascending  767.81  (same line)
2026-09-03T10:45:00 TOUCH  ascending  767.92  (same line)
2026-09-03T10:55:00 TOUCH  ascending  768.03  (same line)   <-- EXACT 10:55:00 ET tick
```
Trigger-bar OHLC at 10:55 (from the report's own reconstruction, independently re-verified above): O 768.62 / H 769.33 / L 767.45 / C 769.28. The shadow ledger's touch rule (`trendline_shadow.py`, `_events_for_session`):
```python
touched = (bar["low"] - TOUCH_TOL_USD) <= proj <= (bar["high"] + TOUCH_TOL_USD)
```
767.45 − 0.15 = 767.30 ≤ 768.03 ≤ 769.33 + 0.15 = 769.48 → **True**, matching the logged `TOUCH` event exactly — this is not a coincidence of timestamps, the geometry mechanically fires on this candle.

The anchor set (764.70 @ 05:55, 766.96 @ 09:05, 767.53 @ 10:10) is a close — not identical — read of J's own two named lows (08:20 premarket low, 10:10 double-bottom): the 10:10 anchor matches J's stated pivot time exactly; the low-end anchor differs (05:55 vs J's 08:20, both premarket) because `find_peaks`-based fitting picked a different early-session low than J's eye did — a legitimate "different mechanical read of the same regime," not evidence the line is unrelated. A second, separate ascending line active earlier in the window (07:30=764.21, 07:45=764.76, 09:05=766.96) has an anchor at exactly $764.21 — the same price the sight-check report's own `trendline_detector.py` premarket-inclusive run independently found for "≈08:20" (off by ~50 min from this ledger's 07:30 timestamp for the same price — likely the same swing bar, approximated differently in each report). Two independently-built detectors converging on the same $764.21 low is corroborating, not contradicting.

## 4. What this means for the report's claims

- **REFUTED**: "(a) Invisible by construction, two independent reasons stacked" (headline) and "no support/low code path exists at all... anywhere in this repo's live or shadow path" — false for the shadow path. `backtest/lib/trendlines.py` has fit ascending/support lines since before this task, wired into `trendline_shadow.py`, itself a registered daily task, and it logged a `TOUCH` on an ascending line at the exact 10:55 candle today.
- **REFUTED**: proposed_change item (1), "A support/rising-line search wired into the shadow ledger [...] has never been checked for `kinds=('support',)`/`require_slope='rising'` explicitly" — the shadow ledger doesn't use `trendline_detector.py`'s `kinds=`/`require_slope=` API at all (that's a strawman comparison); it uses a *different*, already-wired module (`trendlines.py`) that has supported ascending lines from day one. There is nothing left to build here — the report's own recommended next step already shipped 2026-08-20.
- **CONFIRMED, unaffected**: the live-engine-specific claim (heartbeat_core.py → filters.py → core-decisions.jsonl `shadow_triggers_fired`) is accurate and re-verified independently. The report's geometry analysis of the two `filters.py` functions (descending-highs only, by design) is also accurate and well-cited.
- **Unverified, not re-checked**: the report's 15m-timeframe claim ("no 15m-timeframe trendline geometry is computed anywhere in this repo's live or shadow path") — `trendline_shadow.py` also 5m-only (`BARS_GLOB` on `spy_5m_*.csv`), so this specific sub-claim is not contradicted by what I found, but I did not independently search for a possible 15m consumer of `trendlines.py` beyond grep already done in the original report.

## FACT vs INFERENCE

- FACT: every `heartbeat_core.py`/`filters.py` line-number claim re-traces exactly (quoted above).
- FACT: independent re-execution of the study script (fresh process, hardcoded repo root) is byte-identical to the committed JSON.
- FACT: `core-decisions.jsonl` 10:40–11:09 ET today, both accounts, directly parsed — matches the report's table exactly, `"trendline_reclaim"` absent throughout.
- FACT: `backtest/lib/trendlines.py` fits ascending lines from swing lows (docstring, lines 6-7) and is imported by `trendline_shadow.py:99` (`from lib.trendlines import detect_trendlines`).
- FACT: `Gamma_TrendlineShadow` is registered, daily 16:22 ET, per `SCHEDULED-TASKS.md:218`, quoted verbatim above.
- FACT: `backtest/data/spy_5m_2026-05-19_2026-09-03.csv` (the file `trendline_shadow.py` reads) starts at 04:00 ET and has 144 bars for today — premarket-inclusive, unlike the live engine's RTH-only window.
- FACT: `analysis/trendlines/shadow-ledger.jsonl` has a `TOUCH` / `ascending` row at `"ts_et": "2026-09-03T10:55:00"`, `line_price: 768.03`, anchors 764.70/766.96/767.53, `touch_count: 3`, `r_squared: 0.9949` — read directly, not synthesized.
- INFERENCE: that this ledger line is "the same line" J drew by eye — supported by the shared 10:10 anchor and a second nearby line sharing the $764.21 anchor with the sight-check report's own premarket-inclusive `trendline_detector.py` run, but not confirmed against a human re-read of the chart at 05:55/07:30 ET specifically.
- INFERENCE: whether the ledger's 14:30 "break, then decline" moment (J's second exhibit) is captured — no ascending BREAK event lands exactly at 14:30 in today's ledger (nearest ascending BREAK events are 12:30 and 15:00/15:10); this was not the object of my re-verification and I did not chase it further.

## Caveats

- I did not re-verify the report's 15m-timeframe claim beyond re-confirming `_htf_15m_stack` is string-only; I did not exhaustively re-grep for a 15m consumer of `backtest/lib/trendlines.py`.
- No network/broker calls made (constraint respected). All reads were of already-committed/cached repo files (`SCHEDULED-TASKS.md`, `shadow-ledger.jsonl`, `spy_5m_2026-05-19_2026-09-03.csv`) plus one fresh, sandboxed re-execution of the study script (output written only to the session scratchpad, not to the tracked JSON/MD).
- I did not modify, re-run, or touch `trendline_shadow.py` itself, `analysis/trendlines/shadow-ledger.jsonl`, or any trading-path file — read-only throughout, per the task's hard constraints.
