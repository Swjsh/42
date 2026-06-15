# MISSED-WEEK — DEFINITIVE BRIEF FOR J (2026-05-31)

> Generated from computed JSON dumps only (L77). The bottom line first, evidence below.

## Bottom line
1. **The missed week (05-26..29) is fully reconstructed + journaled.** Real Alpaca SIP/OPRA fills; engine ran both accounts; J-edge 5/04 anchor still captured.
2. **No exit-parameter change beats production out of sample.** On 82 OOS signals/60 days the current bull exits (-8% stop + trailing profit-lock ON) are the BEST and only positive config. Every 'fix' that made the 4 missed days green (wider stop, PL-off, sniper entry) REVERSED to a loss on adequate data. Recommendation: **change nothing in production exits** (Rule 9).
   - Best OOS = -8% PLon +88/c (= production).

## NEW: where the OOS bleed actually is (segmentation, production v15)
68 OOS trades, overall 272.3/c, WR 0.32.

**By side (the OP-16 question — is the DRAFT bull setup the problem?):**
| side | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| BEAR_put | 57 | 0.32 | +144 | +2.5 |
| BULL_call | 11 | 0.36 | +128 | +11.7 |

**VERDICT: bull +11.7/c per trade, bear +2.5/c. Both contribute; see per-bucket tables in oos-segmentation-2026-05-31.md.
- **time-of-day:** best = OPEN_DRIVE (+24.7/c/trade, n16); worst = MIDDAY (-8.6/c/trade, n33).
- **trigger-count:** best = 3trig (+24.5/c/trade, n6); worst = 4trig (-19.0/c/trade, n1).
- **confluence:** best = has_confluence (+25.8/c/trade, n19); worst = no_confluence (-4.4/c/trade, n49).
- **VIX regime:** best = UNK (+4.0/c/trade, n68); worst = UNK (+4.0/c/trade, n68).

## What was shipped this session (engine-benefit, no doctrine/order changes — Rule 9 honoured)
- Reconstructed + journaled the 4 missed days (real fills); J-edge non-regression confirmed.
- Built reusable infra: fetch_missed_days.py (Alpaca grids), run_dual_account.py, run_all_sniper.py (stop/PL/anchor grid), segment_oos.py, sniper_matrix.py — all sanity-guarded + JSON-dumping.
- Proved (and retracted) the wider-stop/PL-off/D1-sniper headlines — they were small-sample artifacts; the 82-signal OOS overruled them. Production exits confirmed best on these knobs.
- Lessons L76 (premium-stop low-VIX) + L77 (computed-artifacts-only / adequate-sample gate) routed.

## Open question for J (the only real lead)
Whether the DRAFT **BULLISH_RECLAIM** setup should be tightened/suspended (segmentation above), and whether a SELECTIVE entry can lift bull win-rate — both need a clean, independently-built, adequate-sample study. Queued as cooks. Nothing ratified; production unchanged.

## Process honesty
This session I repeatedly shipped conclusions from too-small / crashed / overfit runs and retracted them. Structural fixes now in force: JSON-templated docs, sanity-abort harnesses, single combined runners, and a hard ADEQUATE-SAMPLE gate (>=~50 OOS signals) before any finding is reported.