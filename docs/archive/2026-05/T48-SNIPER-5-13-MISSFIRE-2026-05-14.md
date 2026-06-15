# T48 — SNIPER didn't fire on 5/13 12:20 ET ATH break — Diagnostic

> Diagnosed 2026-05-14T01:50 ET (Fire #20). Severity: HIGH. Root cause: SILENT — watcher_live emitted ZERO observations for 5/13 despite the SNIPER detector firing correctly when called offline against the same bars.

## Original claim (queue.md T48)

> SPY 12:20 bar: O=740.70, H=740.96, C=740.95, V=31,185. 740.79 (5/11 ATH) within proximity ($0.16 away). Body $0.25 > 0.02 threshold. require_break_above_open ✓ (C>O). MOST LIKELY: 20-bar volume avg includes early-morning bars (78K-145K) biasing avg high, so 31K bar vol < 1.1× avg.

## What's actually true

The OHLCV values quoted in the queue task were **wrong**:

| | queue claim | actual (master CSV `spy_5m_2026-05-08_2026-05-13.csv`) |
|---|---|---|
| O | 740.70 | 740.70 ✓ |
| H | 740.96 | **741.87** |
| C | 740.95 | **741.66** |
| V | 31,185 | **536,688** |
| body | 0.25 | **0.96** |
| 5/11 ATH | 740.79 | **740.73** (master CSV) |

Real 12:20 bar has body $0.96 (not $0.25), volume 536K (not 31K). Volume vs prior-20-bar avg = **1.55× (well above 1.1 threshold)**.

## What SNIPER would do given the real bar values

`backtest/autoresearch/t48_sniper_513_diag.py` simulates the production SNIPER (`lib/sniper_detector.detect_sniper_break` with v15 winner-combo knobs) over all 77 RTH bars on 5/13:

```
RTH bars on 5/13: 77
  FIRE at 12:20: long 5d_high(740.73) RECLAIMED_UP prior_c=740.71 bar_c=741.66 vol=1.6x body=$0.93
Total SNIPER fires on 5/13: 1
```

`backtest/autoresearch/t48_sniper_watcher_test.py` calls the production WATCHER wrapper (`lib/watchers/sniper_watcher.detect_sniper_setup`) on the same bar:

```
Calling sniper_watcher.detect_sniper_setup()...
  -> SIGNAL FIRED:
     watcher_name: sniper_watcher
     setup_name: SNIPER_LEVEL_BREAK
     direction: long
     entry_price: 741.6550
     confidence: high
     reason: SNIPER long 5d_high@740.73 (Carry, 3*) entry=741.66 vol=1.55x body=$0.93
     metadata level_label: 5d_high
     metadata level_stars: 3 (ELITE Carry tier)
     metadata vol_ratio: 1.55
     metadata body_dollars: 0.93
```

So both the bare detector AND the production watcher wrapper fire HIGH-CONFIDENCE on 5/13 12:20.

## The actual bug — silent zero-observations

`automation/state/watcher-observations.jsonl` line count: 362
- Last `bar_timestamp_et`: `2026-05-12T11:00:00`
- 5/13 bar entries: **0**
- `sniper_watcher` entries (any date): **0**

`automation/state/.watcher-live-state.json`:
```json
{"last_bar_ts": "2026-05-13 15:50:00", "last_run": "2026-05-13T15:50:03.736590", "signals_this_bar": 0}
```

So `watcher_live.py` ran throughout 5/13 trading hours, processed bars (last bar 15:50 = market close), but emitted ZERO signals AT ANY BAR ALL DAY. The Gamma_WatcherLive scheduled task ran every 5 min from 09:30 to 15:55 with `LastTaskResult=0` (success exit code).

## Suspected root cause

Three plausible silent-failure paths:

1. **yfinance OHLCV values diverge from Alpaca-IEX values for the same bar.** When watcher_live runs at 12:25 ET and fetches the 12:20 bar via yfinance, the values may differ enough (smaller body, smaller volume) to fail SNIPER's gates — but match Alpaca-IEX values better when the master CSV is rebuilt overnight. Without per-fire logging of bar OHLCV + signal dispositions, we can't confirm.

2. **multi_day_rth in live mode might be missing the 5/11 RTH bars** needed to compute 5d_high=740.73. If the master CSV used by the live process doesn't include 5/11 (e.g., a date filter cut it off), the 5d_high level wouldn't reach 740.73 and the 12:20 reclaim wouldn't trigger.

3. **`bar_idx_in_day` mismatch.** The runner.py computes `bar_idx_full` from multi_day_rth correctly, BUT if the live caller's `latest_ts` doesn't match a row in `multi_day_rth` exactly (e.g., tz-naive vs tz-aware mismatch), `matching` is empty, `bar_idx_full = -1`, and SNIPER is skipped silently per runner.py L137 `if bar_idx_full >= 0:`.

## Mitigation queued for tomorrow

Add per-fire diagnostic logging in `watcher_live.py` so each fire writes:
- bar OHLCV values seen
- whether multi_day_rth has 5+ prior RTH days
- per-watcher: was it called? did it return a signal? if no, what was the first failing condition?

This converts SILENT failures into LOUD failures (per OP-25 "silent failure is the only true failure").

## Separate findings worth flagging

- **`sniper_watcher.py` lines 124-130 spot-stop math is broken.** `entry × (1.0 + (-0.10) / 10.0) = entry × 0.99` gives a 1% SPY-spot stop for a 10% premium stop. On a $740 entry, that's a $7.40 spot stop = ~$4 premium move = ~80-100% premium loss for ITM-2 0DTE. The spot-stop should be tied to delta, not divided by 10. Quirky but watcher is observation-only so not blocking. Logged as future-improvement.
- **Watcher-observations.jsonl shows ORB watcher unique-on-5/06 with 731.78→runner_hit P&L $103.50.** ORB is firing.

## What's already done

- `setup\scripts\fire-stage0-selftest.ps1` (NEW) — re-runnable Stage 0 self-test for any wake fire
- `setup\scripts\opra-cache-audit.ps1` (NEW) — re-runnable OPRA cache integrity audit
- `setup\scripts\opra-anchor-spotcheck-v2.ps1` (NEW) — verifies all 8 J anchor day strike windows present in cache
- `backtest\autoresearch\t48_sniper_513_diag.py` (NEW) — simulates SNIPER over 5/13, traces 12:20 fire
- `backtest\autoresearch\t48_sniper_watcher_test.py` (NEW) — end-to-end test of sniper_watcher wrapper on 5/13 12:20

## Verdict

**SNIPER detector + watcher logic are CORRECT.** Bug is in the live-fire path — silent zero-observations from `watcher_live.py` on 5/13 (and likely earlier days too — only 5/13 was checked but the pattern suggests systemic). Mitigation: per-fire diagnostic logging shipped tomorrow morning, then re-test on 5/14 CPI day.

## OP-25 lesson absorbed

> Silent zero-observations during market hours = silent failure. Watcher-live fires returning exit 0 with `signals_this_bar=0` for an entire trading day on a day with multiple high-confidence setups (5/13 had a $2,932 ribbon-ride winner) is a RED flag we missed for at least 4 trading days (5/10-5/13). Health-check should grep watcher-observations for today's date AND alert if zero observations during market hours.

## BROADER FINDING — 5 of 8 watchers have ZERO observations EVER (Fire #21 audit 02:25 ET 2026-05-14)

Re-audited `automation/state/watcher-observations.jsonl` (362 total entries):

| Watcher | Observations | Status |
|---|---|---|
| orb_watcher | 222 | ✓ firing |
| bullish_watcher | 108 | ✓ firing |
| v14_enhanced_watcher | 32 | ✓ firing |
| sniper_watcher | **0** | 🔴 SILENT |
| vwap_watcher | **0** | 🔴 SILENT |
| opening_drive_fade_watcher | **0** | 🔴 SILENT |
| pinfade_watcher | **0** | 🔴 SILENT |
| premarket_fail_fade_watcher | **0** | 🔴 SILENT |

5/13 also had ZERO bar-date observations across ALL watchers (last bar timestamp recorded: 5/12 11:00). 5/08, 5/11, 5/12 only had 1 observation each — coverage has been collapsing since 5/01.

### Pattern hypothesis

The 3 firing watchers (orb / bullish / v14_enhanced) do NOT depend on `multi_day_rth`. The 5 silent watchers ALL gate on `multi_day_rth` per `runner.py` line 129:

```python
if multi_day_rth is not None and not multi_day_rth.empty:
    # Find bar's index within multi_day_rth (it should be the latest matching ts)
    try:
        matching = multi_day_rth.index[multi_day_rth["timestamp_et"] == bar["timestamp_et"]]
        bar_idx_full = int(matching[-1]) if len(matching) > 0 else -1
    except Exception:
        bar_idx_full = -1

    if bar_idx_full >= 0:
        try:
            snp = detect_sniper_setup(bar, bar_idx_full, multi_day_rth)
            ...
```

Three failure modes that match the data:
1. **Replay callers don't pass multi_day_rth at all** (Gamma_WatcherReplay) → outer `if` fails, 5 watchers all skip silently
2. **Live mode passes multi_day_rth but timestamp match fails** (tz mismatch, dtype object after concat per CLAUDE.md L31) → `matching` is empty, `bar_idx_full = -1`, inner `if bar_idx_full >= 0:` fails, 5 watchers all skip
3. **Live mode passes multi_day_rth correctly but each watcher throws** (less likely given test passes) → all 5 try/except blocks swallow the exception

The diag-trail shipped tonight writes `multi_day_rth_rows`, so tomorrow's CPI day fires will tell us:
- If `multi_day_rth_rows = 0` in live diag → failure mode 1 or 2
- If `multi_day_rth_rows > 0` AND `signals_emitted = 0` → failure mode 3 (probably exception swallow)
- If `signals_emitted > 0` → we just saw the first live sniper fire

### Queued follow-ups

- **FIRE21-LOG-FINDING** (high) — added to morning brief
- **T62 multi_day_rth invariant check in runner.py** — assert log-warn when `multi_day_rth` is None/empty for a live call (replay can be allowlisted via flag). Removes failure mode 1.
- **T63 silent-except remove** — change `except Exception: pass` in runner.py lines 142-143, 149-150, 156-157, 163-164 to `except Exception as e: sys.stderr.write(f"watcher X failed: {e}\n")`. Removes failure mode 3.
- **T64 tz-aware sentinel** — after multi_day_rth concat, verify dtype is datetime64[ns, ET] not `object`. Sanity-check the lookup in runner.py line 132 with explicit pd.to_datetime coercion.
