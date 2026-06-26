---
name: short-level-rejection-killed
description: The SHORT counter-ribbon named-level rejection (resistance fade) primitive is dead — killed three independent ways. Do not re-cook.
metadata:
  type: project
---

SHORT-side counter-ribbon named-level rejection (PUTS off named Active/Carry RESISTANCE, ribbon gate relaxed, ITM+tight target) = **REJECTED, beats no null.** Validated 2026-06-26 (leaderboard #39). Do NOT re-propose without NEW anchor real-fills.

**Why (three convergent prior results — already paid for):**
1. `analysis/recommendations/level-rejection-gate-01.json` — RATIFIED 2026-06-17. This EXACT SHORT subset (`level_rejection` = counter-trend fade of a resistance touch): IS n=22, avg **-$584/trade, -$13,389 total.** Production gate `block_level_rejection=true` ships in params.json + aggressive/params.json specifically to BLOCK it. Proposing this setup = re-enabling a gate J ratified OFF.
2. `analysis/level-quality/level-quality-benchmark.json` — 220 days, 3,202 levels, 3 null shuffles. Named levels have PLACEMENT edge (touch 0.529 real vs 0.219 rand) but **NO reaction edge**: respect_of_touched 0.250 real vs **0.255 distance-matched null**, median reaction 1.798 vs **1.807 DM-null**. A random-entry null at matched distance is respected as often/more. C3/L143/L183 exit-artifact signature.
3. `analysis/recommendations/gate_sweep_patterns_levels.json` — Chef 2026-06-17. vol_ratio=0.0 at ALL J winner entry bars → the vol≥1.2-1.5x confirmation this setup mandates ANTI-correlates with J's actual edge bars.

**Regime (VIX-stratified, NOT averaged):** low/range reaction only 1.165pt (too shallow for ITM theta); high/trend respect LOWEST 0.240 (fade run over). No regime where the SHORT fade is both respected AND deep enough.

**Theta:** ITM+tight is correct for vwap WITH-trend continuation but does NOT rescue a no-edge counter-ribbon REVERSAL entry — just realizes the loss faster. Breakeven after 6 bars theta: ITM-1 ~0.24pt; the null says the entry can't predict that better than random.

**BLOCKING DATA GAP (same as [[named-level-trigger-scope]]):** the 06-24 PMH 737.11 SHORT reject anchor and 06-26 PML 728.50 LONG reclaim anchor are UN-FILLABLE — OPRA cache `backtest/data/options/` stops at SPY260618 (2026-06-18); AND there is NO historical per-day named-level store (`level_source.py` reads only the live `key-levels.json` snapshot; `build_day_contexts` carries prior_close+RTH only). Any historical "named-level" backtest is a PROXY (PDH/PDL/extreme), not J's curated levels.

**Only path to reopen:** fetch OPRA + SPY 5m bars for 2026-06-19..06-26, then run a proxy-named-level real-fills check on ONLY the 2 anchor days. If it does not CLEARLY beat the distance-matched null there, the primitive is permanently closed.

**CURRENT-ENGINE RE-VALIDATION (2026-06-26, J-directed block audit) — KEEP confirmed.** The mirror-image question: does the production gate `block_level_rejection=true` (Safe) still earn its keep under real fills + ITM/managed exits (partial TP1 + runner + chandelier + -50% cap), or does the new exit structure now rescue the level_rejection losers it blocks? A/B over the original IS+OOS window (2025-01-02..2026-05-22), real fills (`use_real_fills=True`), production params.json as override base, flipping ONLY `block_level_rejection`:
- BLOCKED (prod): n=53, total **$27,068**. UNBLOCKED: n=66, total **$25,224**. **Block delta = +$1,843** (unblocking adds 13 LEVEL-tier bear level_rejection PUTs that are net losers — bear_lvlrej subset goes $12,623@n15 → $10,780@n28, i.e. the 13 added trades drag it down by exactly $1,843).
- Anchor-no-regression: 5/01 & 5/04 winner days IDENTICAL both arms ($0 / +$300). 5/05/5/06/5/07 losers IDENTICAL ($0/$0/+$404). 4/29 winner-DAY: blocking IMPROVES it +$951 (unblocked adds a 14:10 `level_rejection+ribbon_flip` PUT = -$1,342). The 5/04 J-source-of-truth winner (+$1,340, triggers `level_rejection+ribbon_flip+confluence`) is a higher tier than LEVEL → gate's `quality_tier=="LEVEL" and winning_side=="P"` guard PRESERVES it. New exit structure did NOT rescue the losing fades — ITM+tight just realizes them faster (consistent with the SHORT-side kill above). **Verdict: KEEP. No param diff.** NOTE: this block's `direction` field is `bear/P` — the audit preamble mislabeled it a "bull-direction block"; the gate predicate is `winning_side=="P"` (BEAR-only). Gym 97/98 (overall_pass) before+after.
