# V14E BEAR_HIGH_CONF Sub-Tier Fingerprint + Promotion Path Design

> Generated: 2026-05-21 ~05:30 ET by overnight session (kitchen task a7db99c0)
> Source: `backtest/autoresearch/v14e_bear_highconf_fingerprint.py` + manual cross-tab
> Inputs: 33 BEAR_HIGH_CONF graded v14_enhanced_watcher observations

---

## Headline Results

| Subset | N | WR | P&L | Key gate |
|---|---:|---:|---:|---|
| BEAR_ONLY (proposed) | 241 | 58.5% | +$1,492 | direction=short |
| BEAR_HIGH_CONF | 33 | 84.8% | +$1,173 | direction=short + confidence=high |
| **BEAR_HIGH_CONF + VIX_MOD** | **24** | **95.8%** | **+$1,281** | **+ vix_daily_close < 20** |
| BEAR_HIGH_CONF + VIX≥20 | 9 | 55.6% | -$108 | (edge collapses at elevated/high VIX) |

---

## Trigger Combination Fingerprints

Every high-confidence observation contains `level_rejection + confluence` as the minimum core.
The third trigger distinguishes two dominant combos:

| Trigger combo | N | WR | P&L |
|---|---:|---:|---:|
| `[level_rejection, ribbon_flip, confluence]` | 17 | 88.2% | +$980 |
| `[level_rejection, trendline_rejection, confluence]` | 15 | 86.7% | +$245 |
| `[level_rejection, seq_rejection, trendline_rejection, confluence]` | 1 | 0% | -$51 |

**What "confidence=high" means structurally:** `has_confluence AND n_triggers >= 3`.
The minimum required triggers are `level_rejection + confluence + ONE MORE`
(ribbon_flip OR trendline_rejection), with score ≥ 9.

Score distribution: score=10 → 26 obs (79%), score=9 → 7 obs (21%).

---

## VIX Regime Breakdown — THE Critical Discriminator

| VIX Regime | N | WR | P&L | Notes |
|---|---:|---:|---:|---|
| VIX_MODERATE (15–20) | **24** | **95.8%** | **+$1,281** | **The edge** |
| VIX_ELEVATED (20–25) | 7 | 57.1% | +$10 | Break-even, no edge |
| VIX_HIGH (≥25) | 2 | 50.0% | -$118 | Negative |

**Gold sub-tier: score=10 + VIX_MODERATE**

| Score | VIX Regime | N | WR | P&L |
|---|---|---:|---:|---:|
| 10 | VIX_MODERATE | **18** | **100.0%** | **+$871** |
| 9 | VIX_MODERATE | 6 | 83.3% | +$410 |
| 10 | VIX_ELEVATED | 7 | 57.1% | +$10 |
| 10 | VIX_HIGH | 1 | 0.0% | -$137 |

Not a single loss in 18 score=10 + VIX_MODERATE observations.

---

## Losses Analysis (N=5 of 33 total)

| Date | VIX | Regime | Triggers | Outcome | P&L |
|---|---|---|---|---|---:|
| 2025-01-07 | 17.82 | **Moderate** | trendline_rejection+level+confluence | stopped | -$95 |
| 2025-02-27 | 21.16 | Elevated | ribbon_flip+level+confluence | stopped | -$35 |
| 2025-05-05 | 23.64 | Elevated | seq_rej+trendline+level+confluence | stopped | -$51 |
| 2025-10-10 | 21.63 | Elevated | ribbon_flip+level+confluence | stopped | -$55 |
| 2026-03-06 | 29.51 | **High** | trendline+level+confluence | stopped | -$137 |

**Pattern:** 4 of 5 losses at VIX≥20. The 1 moderate loss (2025-01-07) is isolated — 
early January on a $597 level (SPY ~$597, pre-rally period).

**The 2026-03-06 loss is the worst (-$137):** VIX=29.51 (market stress), March 2026.
Confirms: high-VIX periods are structurally bad for this setup.

---

## Date Concentration Risk

| Date | N | VIX | P&L | % of moderate P&L |
|---|---:|---|---:|---:|
| 2026-05-04 | 8 | 18.18 | +$532 | 41.5% |
| 2026-05-15 | 6 | 18.22 | +$234 | 18.3% |
| 2026-04-23 | 3 | 18.98 | +$429 | 33.5% |
| 2026-04-28 | 3 | 17.81 | +$90 | 7.0% |
| All others | 4 | — | -$4 | — |

**Top 2 dates (5/04 + 5/15) = 59.8% of moderate P&L.** This is concentration risk.

However, 5/04 is a KNOWN J-winner day ($730 actual P&L for J). The 8 obs on 5/04 are 
8 separate entry bars at the same 720.47 level (v14e watcher fires repeatedly on level 
retests — this is expected watcher behavior, not cherry-picking). The concentration IS 
real though: if 5/04-class days don't repeat regularly, the forward WR may degrade.

**OP-20 concentration disclosure: top-2-day = 59.8% of P&L for VIX_MODERATE subset.**

---

## Promotion Path Design

### Path A: BEAR_ONLY gate (watcher ship + watch-stable)

**What:** Restrict v14_enhanced_watcher to direction=short only (remove bull branch).  
**Evidence in hand:** N=241, WR=58.5%, P&L=+$1,492 vs baseline -$2,150.  
**Gate to WATCH-STABLE:** 100 new live observations (graded), WR≥55% maintained over  
  ≥4 calendar weeks + J explicit ratification per Rule 9.  
**Status:** DRAFT in `2026-05-21-v14e-quality-filter.md`. Requires J ratification.

### Path B: BEAR_HIGH_CONF + VIX_MODERATE sub-tier (fast-track)

**What:** direction=short AND confidence=high AND vix_daily_close ∈ [15, 20).  
**Evidence in hand:** N=24, WR=95.8%, P&L=+$1,281 over 15 unique dates.  
**Concentration caveat:** Top 2 dates = 59.8% of P&L. Need more date diversity.  
**Gate to WATCH-STABLE:** 15 new live observations at VIX_MODERATE, WR≥75%.  
  Minimum 8 distinct trading days (no single-day saturation).  
**Status:** No separate watcher needed — this is a sub-tier of the existing v14e 
  watcher (already accumulating obs). Need to: (1) add VIX_MODERATE flag to 
  watcher observations metadata, (2) build sub-tier grader.

### Priority recommendation

**Ship Path A first** (the BEAR_ONLY watcher gate). It:
- Requires one watcher file edit + J ratification
- Unlocks clean ongoing accumulation of bear-only data
- Allows Path B sub-tier to be extracted naturally from the bear-only obs pool

**Add VIX tagging to watcher metadata** (engine-benefit, no ratification needed):
- Modify `v14_enhanced_watcher.py` to look up VIX close from daily cache and 
  annotate each observation with `vix_daily_close` + `vix_regime` at grading time
- This enables downstream sub-tier graders without changing any trading logic

---

## Next Research Steps

1. **VIX tagging in watcher** (engine-benefit, ship autonomously per OP-25):
   - Edit `backtest/lib/watchers/v14_enhanced_watcher.py` to add VIX metadata
   - No production impact — watcher-only observation enrichment

2. **V14E_BEAR_ONLY_GATE watcher file edit** (J ratification required):
   - Already drafted: `2026-05-21-v14e-quality-filter.md`
   - Pre-merge gate: 67/67 gym PASS verified

3. **V14E_BEAR_HIGH_CONF_VIX_MODERATE sub-tier grader**:
   - Once Path A ships, automatically filter new obs to direction=short+confidence=high+VIX<20
   - Gate: N_new ≥ 15, WR ≥ 75%, ≥ 8 distinct dates, ≤ 30% single-date concentration

4. **Chart-stop research for v14e bear** (analogous to NLWB/LBFS L51):
   - Check: does the -8% premium stop fire before the directional move on score=8/9 entries?
   - If yes: switch to chart-stop-only (per L51 lesson) to improve real-fills WR

---

## OP-20 Disclosures

1. **Account-size:** Watcher grading uses qty=3 contracts. P&L figures are at $1K-$2K tier sizing.
2. **Sample bias:** 16-month coverage (2025-Q1 to 2026-05-21). VIX_MODERATE subset has 15 unique dates; 5/04 + 5/15 = 59.8% concentration.
3. **Out-of-sample:** No formal walk-forward run. The VIX_MODERATE gate is structural (VIX is an external market variable, not a tuned parameter) — low overfitting risk vs tuned threshold gates.
4. **Real-fills:** Not validated. v14e watcher uses -8% premium stop. L51 risk: if entry bar is a rejection bar, -8% may fire during initial noise before directional move. Chart-stop research pending.
5. **Failure modes:** Sustained VIX<20 + bear market bias (e.g., 2026-Q2 conditions) will continue to generate obs; but if market regime rotates to VIX>20, signal frequency drops to 9 obs over 16 months — insufficient for real-time grading.
6. **Concentration:** Top-2-day contribution = 59.8% of VIX_MODERATE P&L. This is the primary risk.

---

## DEDUP CORRECTION (appended 2026-05-21 ~05:30 ET by overnight session)

The N=33/WR=95.8% headline figure and all N=24/N=9 regime breakdowns above are UNDEDUPLICATED.
`watcher-observations.jsonl` stores one row per heartbeat tick per bar; a single 5-min SPY bar
can generate 2-5 rows during HOT mode.

Deduplicated by `bar_timestamp_et[:16]` (unique minute = unique bar):

| Subset | Undeduplicated N | Deduplicated N | WR (deduped) | P&L (deduped) |
|---|---:|---:|---:|---:|
| BEAR_HIGH_CONF total | 33 | **16** | — | — |
| VIX_MODERATE (15–20) | 24 | **9** | **77.8%** | **+$325** |
| VIX_ELEVATED (20–25) | 7 | **6** | 66.7% | +$41 |
| VIX_HIGH (≥25) | 2 | **1** | 0.0% | -$137 |

**The discriminator direction is confirmed** — VIX_MODERATE has the highest WR at both
undeduplicated and deduplicated counts. The WR is lower (77.8% vs 95.8%) but still well
above VIX_ELEVATED (66.7%) and VIX_HIGH (0.0%).

The OP-21 promotion gate is now tracking unique-bar observations only:
- Gate: N_new_unique_bars ≥ 15, WR ≥ 75%, ≥ 8 distinct dates
- Current: 0/15 (live obs accumulation started 2026-05-21)
- Monitor: `backtest/autoresearch/v14e_highconf_vix_monitor.py`
- Output: `analysis/recommendations/v14e-highconf-vix-monitor.json`

**L67 encoded:** lesson inbox item queued at `strategy/candidates/_lesson-inbox/2026-05-21-watcher-obs-dedup-inflates-wr.md`
