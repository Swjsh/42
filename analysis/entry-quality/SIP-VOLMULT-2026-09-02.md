# SIP-VOLMULT-MISMATCH -- 2026-09-02 offline reproduction

**RESEARCH ONLY / NOT A RECOMMENDATION.** No threshold change proposed. Full data: [`SIP-VOLMULT-2026-09-02.json`](SIP-VOLMULT-2026-09-02.json). Script: [`backtest/tools/f10_volume_reproduce.py`](../../backtest/tools/f10_volume_reproduce.py).

## Reproduction count vs the queue item's 144/178

Using the engine's **real** `buyer_pressure_bar_v11` + `vol_baseline_20bar` functions (imported, not reimplemented) on real bars:

| Basis | n | blocked | % |
|---|---|---|---|
| Queue item (ticks, all core-decisions rows in window) | 178 | 144 | 80.9% |
| core-decisions.jsonl, deduped to unique 5-min bars, safe acct | 77 | 57 | 74.0% |
| SIP bars, real cross-session baseline (this reproduction) | 77 | 55 | 71.4% |
| IEX bars, real cross-session baseline (this reproduction) | 77 | 58 | 75.3% |

**Did not hit 144/178 exactly** -- that figure counts heartbeat *ticks* (~1-2/min, several ticks share one closed 5-min bar); the correct denominator for a per-bar filter is *bars*, which is 77 for the day's 09:35-16:00 RTH session. Reproduced against that denominator, both SIP (71.4%) and IEX (75.3%) land within a few bars of the actual live outcome (57/77 = 74.0%). The delta to 144/178 is a tick-vs-bar counting artifact, not an unmodeled mechanism.

## Traced baseline definition

Both engines compute the identical mechanism -- a 20-bar trailing SMA of volume over a **continuous, RTH-only, multi-day** series with **no per-day reset**:

- Backtest, `backtest/lib/filters.py:131-135`:
  ```
  def vol_baseline_20bar(prior_bars, idx):
      """20-bar SMA of volume immediately preceding bar `idx` (does NOT include bar idx)."""
      if idx < VOL_BASELINE_BARS:
          return float(prior_bars["volume"].iloc[:idx].mean()) if idx > 0 else 0.0
      return float(prior_bars["volume"].iloc[idx - VOL_BASELINE_BARS:idx].mean())
  ```
  fed `spy_df` (`orchestrator.py:803-824`) = RTH-only (09:30-16:00) bars built **once** across the whole multi-day backtest range, index reset only once -- not per day.

- Live, `setup/scripts/heartbeat_core.py:928`:
  ```
  vol20 = float(win["volume"].iloc[max(0, trig_idx - 20):trig_idx].mean())
  ```
  fed `win = df.iloc[-150:]` (`heartbeat_core.py:897-905`), `df` = RTH-only-filtered across whatever multi-day history was fetched, again no per-day reset.

**Consequence:** for the first ~20 RTH bars of any trading day (09:35 through ~11:15 ET), the 20-bar lookback window reaches backward into the **prior day's RTH tail** (15:xx bars). This is present in BOTH the backtest and the live path identically -- it is not a live-only artifact.

**Also confirmed (item's own point, step 6):** `core-decisions.jsonl` rows for 2026-09-02 carry `bull_blockers`/`bull_score`/etc. but **no `vol_baseline_20` or bar volume field** -- the number that decided every blocker-10 verdict that day is not recoverable from the decision log; it had to be reconstructed from raw bars, which is exactly why the log's own absence was flagged as the root cause of this taking a reconstruction at all.

## IEX vs SIP

| Feed | n bars | blocked | % | ratio p10/p50/p90 |
|---|---|---|---|---|
| SIP (cross-session baseline) | 77 | 55 | 71.4% | 0.48 / 0.80 / 1.73 |
| IEX (cross-session baseline) | 77 | 58 | 75.3% | 0.38 / 0.75 / 1.49 |

Ratio correlation (SIP vs IEX, same 77 bars): **0.77**.

Sensitivity check -- same script re-run with the prior-day warmup removed (`vol_baseline_20bar`'s own `idx<20` fallback: mean of only today's bars so far, isolating the session-crossing effect):

| Feed | n bars | blocked | % |
|---|---|---|---|
| SIP, same-day-only baseline | 77 | 50 | 64.9% |
| IEX, same-day-only baseline | 77 | 50 | 64.9% |

SIP and IEX block the **identical 50 bars** once session-crossing is removed.

## Which cause the evidence supports

- **(a) IEX/SIP bias or noise:** NOT the primary driver. With session-crossing removed, SIP and IEX agree on every single blocked bar (50/50 identical). With session-crossing included they diverge by only 3 bars (55 vs 58) out of 77, correlation 0.77 (real per-bar noise exists, but doesn't flip the outcome).
- **(b) Baseline window spans sessions and is inflated:** CONFIRMED PRESENT and quantified -- it adds ~6-10 percentage points (5-8 extra blocked bars) on top of the same-day-only rate. But it is a **secondary** contributor: the same-day-only baseline (no cross-session contamination possible) already blocks 64.9% of bars.
- **Overall:** the dominant fact is that on 2026-09-02, most individual 5-min bars traded at **under 70% of their own trailing 20-bar average volume** -- true under SIP, true under IEX, true with or without prior-day baseline carryover. Blocker 10 firing on 74-81% of bars/ticks that day is consistent with the ratified 0.7x threshold behaving as designed against this specific day's low-turnover, drifting-up volume shape -- not evidence of a computation bug. The session-crossing behavior (b) is real, present in both engines, and worth its own line item, but did not drive the bulk of the day's blocking.

## What was NOT resolved

- Digit-exact match to the queue item's 178/144 tick counts (explained as tick-vs-bar counting, not chased further).
- The specific defect in the queue item's own "crude approximate 20-bar baseline" reconstruction (which reported the condition mostly PASSING, e.g. 0.85x/1.56x/1.30x/1.40x) -- its code was not available this session; it disagrees with both the traced production mechanism and the live `core-decisions.jsonl` outcome (57/77 blocked), so whatever it did differently under-blocked relative to the real mechanism.
- IEX pulled for only 4 trading days; the 0.77 correlation is a single-day, n=77 sample, not a multi-day distribution.

## Files

- `backtest/tools/f10_volume_reproduce.py` -- deterministic reproduction script, `--date` argparse, imports the real filter functions, fetches/caches IEX via `alpaca_keys.py`.
- `analysis/entry-quality/SIP-VOLMULT-2026-09-02.json` -- full machine-readable report (per-cause evidence, sensitivity check, unverified list).
