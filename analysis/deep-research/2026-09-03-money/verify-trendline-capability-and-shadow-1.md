# SKEPTIC verify — trendline-capability-and-shadow (STATISTICS lens)

**Stamp:** 2026-09-03T17:47:16 ET (`setup/scripts/et_clock.py`, market_hours=False)
**Target:** `analysis/deep-research/2026-09-03-money/trendline-capability-and-shadow.md` (+ its `.json`)
**Method:** independent recompute, own script (`backtest/tools/trendline_study_verify1.py`), own RNG stream, no code shared with the original except the two library modules it exercises (`backtest/lib/trendlines.py`, `setup/scripts/trendline_shadow.py`) — both read-only, unmodified. Read-only against the shadow ledger and every trading-path file. No new rows written to the ledger. Ran in 2.8–3.3s per tolerance pass, well under the 5-minute cap.

## Verdict: CONFIRMED, not refuted

Every ledger-composition number and headline statistic in the original report reproduces from a fresh read and an independent bootstrap. The stats lens (session-clustered CI recompute, top-3 removal, threshold robustness, time-of-day baseline) does not surface anything that undercuts the finding's central claims — if anything, the top-3 removal test makes the concentration problem look *worse* than the original number alone conveys, and the tolerance-robustness test shows the null result itself is stable, not an artifact of one arbitrary `$0.15` choice.

## What I independently reproduced exactly

Fresh `Counter` over all 4,986 ledger rows, direction × event, rows vs. theo-qualifying:

| direction/event | rows | theo | matches report |
|---|---:|---:|---|
| ascending/BREAK | 762 | 686 | yes |
| ascending/REJECT | 439 | 388 | yes |
| ascending/RETEST | 301 | 0 | yes |
| ascending/TOUCH | 1080 | 0 | yes |
| descending/BREAK | 752 | 0 | yes |
| descending/REJECT | 436 | 387 | yes |
| descending/RETEST | 336 | 0 | yes |
| descending/TOUCH | 880 | 0 | yes |

Ascending-TOUCH `mfe_30m`: n=1066, mean **+0.6717** — matches the report's "+0.67 pts, exploratory only" note exactly.

Whole-sample stats at `end_date=2026-09-02` (matching `shadow-verdict.json`'s `latest`): my recompute gives **n_sessions=73, n_trades=1451, WR=0.4004, pts/trade=0.0386, top3_share=1.0543** — identical to the stored verdict to 3-4 decimal places (WR/top3 share match at the precision the report quotes).

## 1. Session-clustered CI, recomputed with a different RNG stream

Own bootstrap (n_boot=5000, seed=20260903, day-level resample-with-replacement, pool trades — same *concept* as `trendline_shadow_verdict.py`'s but a separate implementation and separate seed):

- **Mine:** mean 0.0377, CI **[-0.0347, +0.1170]**
- **Stored:** mean 0.0386, CI **[-0.0301, +0.1177]**

Both straddle zero by a wide margin; the two CIs overlap almost completely. The stored CI is not an artifact of one bootstrap seed — a differently-seeded, 2.5x-larger bootstrap lands on essentially the same interval. **Confirmed, not refuted.**

## 2. Currency check — the stored verdict is stale by one session (minor, does not change the substance)

`shadow-verdict.json`'s `latest` entry is dated 2026-09-02 (73 sessions). The ledger itself already has a 74th session — **today, 2026-09-03** (27 rows, 10 theo trades, RTH bars 06:30–15:30 ET, confirming the market genuinely closed for the day before this audit ran). `trendline_shadow_verdict.py` was not re-run today.

Recomputing on the full 74-session ledger: **n=1461, pts/trade=0.0381, CI [-0.0341, +0.1142]** — materially unchanged from the 73-session number. This is a bookkeeping gap (the verdict file needs a re-run, outside this task's write scope), not a substantive problem with the finding — flagging it, not treating it as a refutation.

## 3. Remove the top-3 sessions — the effect does not survive

Top-3 sessions by total theo profit (from the full 74-session ledger): **2026-05-20 (+32.4 pts), 2026-07-16 (+15.5 pts), 2026-05-22 (+11.1 pts)** — three sessions out of 74 supplying +59.0 of the ledger's +55.7 total (that's *where* the reported 105.9% concentration figure comes from, made concrete).

Remaining 71 sessions, 1347 trades: **pts/trade = -0.0024** (total -3.3 pts), CI **[-0.0611, +0.0601]** — dead-centered on zero, and the point estimate flips negative. This independently confirms the report's concentration claim in the strongest possible way: **the entire positive headline number lives in 3 of 74 sessions; the other 96% of the sample is a wash-to-slightly-negative.** This is not a new finding — the original report's `top3_session_share_of_profit: 1.054` already said this — but running the actual exclusion test rather than trusting the ratio is worth doing, and it holds up.

## 4. Time-of-day — noisy, not clean evidence either way, and not a volatility-timing artifact

Theo trades bucketed by ET entry hour (n, WR, pts/trade) vs. a baseline of every 5m bar's realized |next-30m move| at the same hour, same 74 sessions (undirected — a pure "how much does price move in this hour" reference, not bias-matched):

| hour | theo n | theo pts/trade | baseline mean\|30m move\| |
|---|---:|---:|---:|
| 09:00 | 70 | **-0.136** | 1.996 (2nd-highest baseline vol) |
| 12:00 | 186 | +0.062 | 1.204 |
| 13:00 | 201 | +0.090 | 1.106 |
| 14:00 | 287 | **-0.043** | 1.102 |
| 15:00 | 270 | +0.111 | 1.085 |

The 09:00 hour has the second-highest realized-move baseline in the day but the *worst* theo pts/trade (-0.136); 15:00 has middling baseline vol but the best mid-day pts/trade. If the shadow lane's "edge" were simply riding whichever hour has the most raw volatility, pts/trade should track the baseline column — it doesn't (correlation is not visually apparent and the swings are large in both directions across adjacent hours). **This rules out the single crudest confound** (pure volatility-timing) as the explanation, but the per-hour n (70–290) is too small and too noisy to call this evidence *for* an edge either — it's exploratory, same caveat the original report already applies to its own ad hoc TOUCH-mfe number, and I'm applying it here too.

## 5. Threshold robustness — the null result is stable across 0.5x/1x/2x touch tolerance

Re-ran the actual detector (`trendlines.detect_trendlines`) and the shadow's own classifier (`trendline_shadow._events_for_session`) over all 74 sessions with `TOUCH_TOLERANCE_USD` / `TOUCH_TOL_USD` both scaled together (they're never varied independently in the live lane, so scaling them together is the faithful sensitivity test):

| tolerance | n theo trades | WR | pts/trade | session-clustered CI |
|---|---:|---:|---:|---|
| 0.5x ($0.075/$0.10) | 1379 | 0.400 | +0.0363 | [-0.033, +0.105] |
| **1.0x ($0.15/$0.20, as-shipped)** | 1461 | 0.401 | +0.0381 | [-0.033, +0.109] |
| 2.0x ($0.30/$0.40) | 1566 | 0.398 | +0.0346 | [-0.034, +0.106] |

Trade count scales sensibly with tolerance (looser tolerance → more qualifying touches/lines → more trades, +13.6% from 0.5x to 2x). The point estimate moves in a narrow band (0.0346–0.0381) and **every CI straddles zero at every tolerance setting tested.** The "no green light" verdict is not a fragile artifact of the specific `$0.15` constant — it holds at half and double that value. This is evidence the *null* is robust, not evidence of a hidden edge the shipped tolerance happens to miss.

## What I did not verify (scope of this pass)

- Did not re-verify J's exact narrated exhibit (08:20/10:10/10:55/14:30 anchors) against today's bars — that's `trendline-today-exhibit.json`'s job, cited but not re-derived here either, matching the original report's own disclosed scope limit.
- Time-of-day baseline is undirected realized range, not a bias-matched "would a naive momentum/reversion trade at this hour also profit" null — a tighter version of that comparison (e.g., a fixed-hold random-entry null stratified by hour) would be the next rigor step if this lane is ever pushed toward a promotion decision. Flagging as a gap, not treating its absence as grounds to refute what's already been shown.
- Did not re-run the four preregs' own statistics (BH-FDR survivor counts, the -$27,378 Cell B replay) — out of scope for this ledger-focused stats lens; nothing in this pass touches those claims one way or the other.

## Bottom line for the STATISTICS lens questions asked

- **n, rates, CIs with session clustering, recomputed independently:** match the original to within bootstrap noise. Confirmed.
- **Remove top-3 sessions:** effect collapses to ~zero/slightly negative. Confirms the concentration problem is real and total, not partial.
- **Compare against time-of-day baseline:** no clean volatility-timing confound found; result is inconclusive/exploratory in the direction of "not obviously an artifact," but underpowered per-hour to call it evidence of a real edge.
- **Threshold-robust (tolerance x0.5, x2)?** Yes — the point estimate and the zero-straddling CI both hold across a 4x range of touch tolerance.

Files: `backtest/tools/trendline_study_verify1.py` (scratch, this session), full stdout captured above. No trading-path file, ledger, or generated surface was modified.
