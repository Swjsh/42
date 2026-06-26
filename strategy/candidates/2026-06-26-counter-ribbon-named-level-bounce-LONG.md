# Strategy candidate: counter-ribbon named-level bounce (LONG / CALLS)

> DRAFT — Chef proposal 2026-06-26T14:35Z. J ratifies.
> **VERDICT: REJECTED — HOLD.** Loses money AND loses to its own random-entry null.

## Hypothesis
Enter CALLS on a confirmed reclaim/bounce off a named Active/Carry SUPPORT level
(level tag + rejection wick ≥8c below + close ≥5c back above), **ribbon gate
relaxed (counter-ribbon ALLOWED)** — the live-engine ribbon-lag miss is the whole
motivation. Anti-theta structure: **ITM strikes + TIGHT target** (the
vwap_continuation winning profile), outer-band only (~$0.30 of the level),
confirmed candle not a bare tag, hard cap 2 entries/session, no re-entry on a
broken level. Directional claim: the level-holding bounce is a positive-expectancy
LONG independent of ribbon direction.

**Claim is FALSE on real fills.** This is the most-attempted / most-failed 0DTE
family (counter-trend bounce scalp) and it fails here exactly as the family
predicts.

## Backtest evidence
- **Window:** 2025-01-02 .. 2026-06-18 (365 trading days, real OPRA fills). The
  two motivating anchors (06-24, 06-26) are AFTER the OPRA cache end (06-18) →
  un-fillable; the detector fires on the same PML/PMH level types throughout.
- **Detector:** forked from `_edgehunt_vwap_continuation` — byte-identical
  `simulate_trade_real` fill path + `metrics_for`-style bundle. New module:
  `backtest/autoresearch/_edgehunt_named_level_bounce.py`.
- **Levels:** STRUCTURAL PROXY (PDH/PDL/PDC/PMH/PML) reconstructed causally —
  key-levels.json is NOT archived historically (BLOCKER, see Disclosures #2).
- **Signals:** 538 total (265 long / 273 short) over 365 days.

**LONG-side grid (the side under validation) — every cell:**

| Cell | n | exp/trade | OOS exp | WR | posQ | null_max | beats null? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| ITM-2 / chart-stop / tp+30% | 249 | **-$50.28** | -$49.96 | 36.5% | — | -$9.66 | NO |
| ITM-1 / chart-stop / tp+30% | 250 | **-$49.12** | -$44.78 | 41.2% | — | -$2.10 | NO |
| ATM / chart-stop / tp+30% | 253 | **-$38.72** | -$37.90 | 45.8% | 0/6 | -$0.46 | NO |
| *(all 12 cells: strike{ITM-2,ITM-1,ATM}×stop{-99,-50}×tp{30,50})* | | -$38 to -$51 | all neg | 36–46% | 0/6 | — | **0/12** |

- **edge_capture:** N/A — this is a LONG/CALL setup; OP-16 edge_capture measures
  J's BEARISH anchor-day capture (wrong axis, C24/OP-16). The honest gate for a
  net-new family is OOS per-trade > 0 — **FAILED on every cell.**
- **final_score:** negative (exp < 0 everywhere) → does not appear ranked.
- **positive_quarters:** **0/6** on the best (ATM) cell.
- **walk_forward:** None (IS expectancy ≤ 0, so WF ratio is undefined — there is
  no positive in-sample edge to carry forward).
- **real_fills_validated:** YES — real OPRA, and that is exactly what kills it.

## The critical gate — beats-the-null (C3 / L183)
For each real long signal I drew **40 random-entry null seeds**: same day, same
side, same [09:35,14:30] window, stop = nearest structural support. Identical fill
path. **The real signal loses MORE than the random-entry null on every cell** —
real exp -$38 to -$50 vs null_max -$0.46 to -$9.78. The level "signal" is not
neutral, it is *actively worse than random entry on the same structure*. There is
no exit-structure artifact masquerading as alpha here — there is just loss, and the
level selection makes it worse (it concentrates entries at the moment a level is
being run over by the counter-ribbon trend).

## Disclosures (per OP-20)
1. **Account-size assumption:** qty=3, v15 chandelier exits (arm +5% / trail 12.5%),
   runner 2.5×. L180 cap-realizability not separately re-checked — moot, edge is
   negative before any cap.
2. **Sample-bias / level-proxy:** key-levels.json holds only TODAY's J-curated
   levels (`level_source.load_named_levels` reads the live snapshot, per-calendar-day
   cache) — there is NO historical per-date named-level store, so this uses a
   STRUCTURAL PROXY (PDH/PDL/PDC/PMH/PML). Per L58/NLWB, PDL-proxy can understate
   ★★★ key-levels by ~20pp. But the proxy is the EASIER set and it loses to its own
   null — a ★★★ rescue of -$38..-$50/trade to >$0 AND beating the null is not
   plausible.
3. **Out-of-sample (2026):** OOS exp -$33 to -$50 on every cell — same sign as IS.
   Stable failure.
4. **Real-fills check:** done (this whole study is real OPRA). Exit histogram on the
   ATM cell: 167/253 = `PREMIUM_STOP`, 71/253 = `RIBBON_FLIP_BACK`. The
   counter-ribbon entries are run over by the trend they fade; even chart-stop-primary
   (-0.99) does not save the deep-ITM premium (premium stop still fires).
5. **Failure-mode enumeration:** (a) theta + fade = ITM premium decays while the
   bounce stalls; (b) counter-ribbon = entering against an established trend → ribbon
   flips back and stops you out (71 fires); (c) level selection times entries into
   the level break, worse than random; (d) anchors un-fillable (data gap), so the
   two motivating cases cannot even be tested.
6. **Concentration:** top5_day_pct = None (total P&L negative → undefined).

## Regime stratification (range vs trend — NOT averaged, L-stratified)
ATM/chart/tp+30 cell:
- **range days:** n=250, exp **-$38.36**, WR 45.6%, total -$9,590
- **trend days:** n=3, exp -$69.00 (negligible n)
Counter-ribbon bounces fire almost entirely on range days (by construction — a
support holds when price is chopping), and they lose -$38/trade there. No regime
rescues it.

## Theta sanity note
ITM + tight target is the CORRECT structure for vwap_continuation (a WITH-trend
continuation). It does NOT rescue a counter-ribbon REVERSAL entry — it just
realizes the loss faster and via a different exit (premium stop vs theta bleed).
ITM does NOT bleed slowly here; it gets stopped (167 premium-stop exits). The
anti-theta hypothesis is sound for with-trend entries and irrelevant for this
fade entry.

## Knob changes proposed
**NONE.** Do not wire this setup. Do not relax the ribbon gate on
`named_level_wick_bounce_watcher` or any level-bounce watcher. The existing
BEAR-blocks ribbon gate on NLWB is CORRECT — relaxing it to counter-ribbon makes
the setup strictly worse.

## Pre-merge gate
`python crypto/validators/runner.py` → **97/98 PASS, overall_pass=True** (1
known-flaky live-source excluded). Standalone module, no production path touched —
gate unchanged before/after.

## My confidence (1-10) and why
**9/10 that this is REJECTED.** Triangulated kill: (1) loses money on every cell;
(2) loses to its own random-entry null on every cell (C3/L183 — the decisive gate);
(3) 0/6 positive quarters; (4) the SHORT mirror was independently rejected
2026-06-26 (same null finding). The 1-point reservation: the 2 live anchors are
un-fillable (OPRA cache ends 06-18) — IF those two specific ★★★ levels behave very
differently from the 365-day PDL/PMH proxy population, a tiny J-specific edge could
exist. But a -$38..-$50/trade proxy that LOSES to random does not promote. To close
the door fully: fetch OPRA+SPY 2026-06-19..06-26 and proxy-test ONLY those 2 days.
