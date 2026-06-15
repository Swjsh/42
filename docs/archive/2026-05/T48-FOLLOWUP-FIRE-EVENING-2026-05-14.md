# T48 follow-up — wake fire 19:17 ET 2026-05-14 (evening cron block)

> Verified the T76 fix shipped overnight, then discovered a SECOND regression: ORB + BULL watchers have stopped firing entirely since 2026-05-13 despite firing 6-12 obs/day from 4/23 → 5/07. Documented for next-fire investigation.

## What I verified (T76 fix works)

`watcher_live.py` ran 76 times on 5/14:
- **Pre-T76 fix (09:30 → 11:30 ET, 24 fires):** `latest_bar_v == 0` on every fire — yfinance was returning the IN-PROGRESS bar at fire-time. All watchers correctly returned None on V=0 bars (vol gate failure).
- **Post-T76 fix (11:35 → 15:50 ET, 52 fires):** `latest_bar_v` 222K-716K (real volume), proper OHLCV. Bar-data is no longer the bottleneck.
- `sniper_5d_high` correctly populated at 740.73 in ALL 76 diag entries → multi_day_rth construction is working.

T76 mitigation = SUCCESSFUL. The "in-progress bar with V=0" failure mode is gone.

## What's NEW — distinct from T48 (regression beyond bar-data)

**Per-day production observation count regression timeline** (`watcher-observations.jsonl`):

| Date | Total obs | Watchers firing |
|------|----------|-----------------|
| 4/23-5/07 | 3-14/day | Mix of orb_watcher (6/day typical) + bullish_watcher (1-6/day) + v14_enhanced_watcher (2-5/day) |
| **5/08** | **2/day** | only `v14_enhanced_watcher` |
| **5/11** | **2/day** | only `v14_enhanced_watcher` |
| **5/12** | **2/day** | only `v14_enhanced_watcher` |
| **5/13** | **0** | (T48 doc captured this — was attributed to SNIPER missing fire) |
| **5/14** | **0 today** | (this fire's investigation) |

**Conclusion:** ORB + BULL fire-rate dropped to ZERO starting 2026-05-08. Sniper RETIRED by J directive on 5/14 morning (per runner.py lines 154-168 commented-out block, `sniper_watcher.py` preserved for reference). v14_enhanced_watcher firing rate dropped from 4-5/day to 2/day on 5/08 then 0/day after 5/12.

## Manual reproducer (post-market in-process)

Tonight's fire ran `run_all_watchers` directly against today's mid-day bars (09:55, 10:30, 11:30, 12:00, 13:30, 14:30, 15:00) with full ribbon + level + multi_day_rth context. Result: **0 signals across all 7 sample bars**, all 8 watchers silent.

The bars themselves are clean:
- `09:55: O=745.02 C=744.43 V=526K stack=BULL spread=142c => 0 signals`
- `12:00: O=749.28 C=749.42 V=330K stack=BULL spread=238c => 0 signals`
- `13:30: O=746.92 C=747.07 V=703K stack=MIXED spread=64c => 0 signals`

So it's not a live-fire path issue (production AND manual are silent). The watchers themselves return None on every today bar.

Not surprising for sniper (retired intent), VWAP (correctly skipped — see `_smoke_vwap_diag.py` finding: 58/78 bars failed `vwap_distance > $0.10` because price never returned to VWAP), ODF (no opening drive exhaustion footprint on a CPI gap-and-go), PFF (no premarket fail — gap held all day).

But ORB and BULL going SILENT is **suspicious** — these caught 6-7 J winners across April and consistently fired 6-12 obs/day until 5/07. Two possibilities:
1. The medium-confidence-only filter (runner.py L98 + L104) became too strict for current market regime — ORB / BULL are returning low or high confidence today, all suppressed.
2. A code change between 5/07 and 5/08 broke their detector logic.

## Hypothesis test for next fire (T80)

Bypass the `confidence == "medium"` filter temporarily:
```python
# Before runner.py L94-99 + L100-105: capture EVERY confidence
orb_raw = detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline_20)
if orb_raw:
    print(f"ORB raw conf: {orb_raw.confidence} reason: {orb_raw.reason}")
bull_raw = detect_bullish_setup(ctx)
if bull_raw:
    print(f"BULL raw conf: {bull_raw.confidence} reason: {bull_raw.reason}")
```

Run across 5/13 + 5/14 bars. If they fire LOW or HIGH consistently, the filter is too tight (regime mismatch). If they fire NOTHING at all, detector logic broke.

## What I shipped this fire

- This document (`docs/T48-FOLLOWUP-FIRE-EVENING-2026-05-14.md`)
- Queue task **T80** for next fire to bypass confidence filter and trace per-bar disposition
- STATUS.md + queue.md + log.md updated per Stage 4 protocol

## What I did NOT do

- Did NOT modify production `runner.py` (would change live-fire behavior mid-arc; per CLAUDE.md rule 9 confidence-filter changes need J ratification)
- Did NOT modify production `heartbeat.md` / `params.json` (per OP-25 banned)
- Did NOT place live Alpaca orders (OP-21)
- Did NOT touch the SNIPER retirement comment block — it's J-authorized

## Cost: ~$0.40 (4 PowerShell + 6 Python diagnostic calls + 2 Read tool calls + this doc + queue updates)
