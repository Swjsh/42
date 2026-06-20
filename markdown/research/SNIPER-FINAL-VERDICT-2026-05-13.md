# SNIPER FINAL VERDICT — Real-Fills 432-combo Stage 1

_Generated: 2026-05-13T19:08 ET (after T42-full Stage 1 completion at 19:02 ET)_

## TL;DR

**SNIPER cannot pass OP 16 J-anchor floors on real OPRA fills.** 0 of 432 combos survive.

The strategy DOES produce positive aggregate edge ($14K wide / 58.5% WR / 5/6 quarters), but it loses money on the specific J winner days (4/29: -$329, 5/04: -$234) regardless of knob settings. Under the J-edge framework (OP 16), this is a REJECTION.

## Key data

**Best combo (5 ties for #1):**
- knobs: `premium_stop_pct=-0.10, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.08, strike_offset=2`
- wide_pnl: **$14,344** real (vs $38,022 BS sim Stage 5 winner — BS over-estimates by 165%)
- edge_capture: **-$799** (NEGATIVE — fails J-edge floor)
- 4/29 J anchor: **-$329** (J had +$342 manual)
- 5/04 J anchor: **-$234** (J had +$730 manual)
- positive_quarters: 5/6 (passes Stage 4 ≥5)
- top5_pct: **0.54** (FAILS ≤0.40 concentration floor)
- WR 58.5% over 193 trades
- BS-sim Stage 5 winner (PL=0.0 OFF) was a WORSE combo — the 432-grid found a small improvement (PL ON 0.05/0.08).

## Distribution by stop width (counter-intuitive)

| premium_stop_pct | positive_wide combos | best wide |
|---|---|---|
| **-0.10** (tightest) | **108/108** | **$14,344** |
| -0.15 | 108/108 | $11,647 |
| -0.20 (mirrors v14e) | 60/108 | $6,318 |
| -0.25 (widest) | 42/108 | $4,839 |

**Surprise:** wider stops HURT SNIPER. Unlike v14_enhanced (where -0.20 stop was best), SNIPER trades that hit the -10% stop quickly are LESS painful than those held longer at wider stops. The detector fires on "level break with vol confirmation"; when the move fails, the failure is FAST (next 1-3 bars). Wider stops just absorb more loss before exiting.

## Why BS over-estimated by 165%

BS sim's IV proxy (`vix/100`) ignores per-strike-per-DTE skew. 0DTE ITM-2 strikes have heavy skew → real entries fill ~10-25% higher than BS estimate. SNIPER buys at the worse price; even small adverse spot moves trigger the stop instantly.

## Action for morning brief

1. **Mark SNIPER NOT RATIFIABLE** in `sniper-v1.json` next_actions. The current Stage 5 winner is invalid.
2. **Add a "SNIPER-aggregate" reframe option** for J: if J accepts aggregate metrics WITHOUT per-J-anchor requirement, the best real-fills combo (stop=-0.10, PL=0.05/0.08, ITM-2) is a marginal-edge strategy producing $14K over 16 months on 193 trades = ~$74/trade × 0.585 WR = sustainable but small edge. J's call whether to ratify aggregate-only.
3. **REGIME_SWITCHER should EXCLUDE SNIPER** as a sub-strategy (per OP 16 floor). Or alternatively, route SNIPER ONLY to days where v14_enhanced doesn't fire.
4. **The 4/29 + 5/04 J anchor days are SNIPER's blind spot** — the level-break-with-vol pattern those days produced was not actually a winning setup with real fills. J's edge on those days came from a DIFFERENT pattern (premarket structure, pre-RTH setup) that SNIPER doesn't capture.

## Files

- Script: `backtest/autoresearch/sniper_real_fills_grinder.py`
- Launcher: `setup/scripts/launch-sniper-real-fills-stage1.ps1`
- Results: `backtest/autoresearch/_state/sniper_real_fills_stage1/{progress.json, rejections.jsonl, keepers.jsonl}`
- Companion: `docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md` (the strategy that DID rescue)

## Comparison to v14_enhanced (the ratifiable strategy)

| Metric | SNIPER (best real) | v14_enhanced #1 (real, PL ON) |
|---|---|---|
| wide_pnl | $14,344 | **$36,450** |
| edge_capture | -$799 | **+$366** |
| 4/29 J anchor | -$329 | **+$869** |
| 5/04 J anchor | -$234 | **+$214** |
| 5/12 J anchor | (not measured) | **+$464** |
| 5/07 J loser | (not measured) | **+$616** (beats J -$45) |
| 5/05 J loser | (not measured) | -$198 (vs J -$260) |
| positive_quarters | 5/6 | **6/6** |
| top5_pct | 0.54 (FAIL) | **0.37** (PASS) |
| WR | 58.5% | **56.8%** |
| Max DD | n/a in rejections | **$2,857** |

**v14_enhanced is the ratifiable strategy of the night.** SNIPER's real-fills numbers are not bad in aggregate but the J-anchor floors say NO.
