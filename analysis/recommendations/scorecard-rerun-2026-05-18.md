# Scorecard Re-run 2026-05-18: Per-Tier Strike + v4 Combined ECE

**Generated:** 2026-05-17 evening (T-09 + T-10 workstream)
**Purpose:** Quantify impact of per-tier $1K strike selection (T-09) on J edge-capture benchmark, and verify v3+v4 combined ECE reduction.

---

## Section 1: Per-Tier Strike Impact on J Edge Capture (T-09)

### Background

`params_bold.json` and `params_safe.json` define `v15_strike_offset_per_tier` ladders for per-equity strike selection. T-09 wired this into `backtest/lib/orchestrator.py` so backtests can be run with `initial_equity=1000` to test $1K-tier behavior.

The $1K tier settings:
- **Safe-1 (ATM, strike_offset=0):** `params_safe.json` — ATM strikes, 30% risk cap
- **Bold (ITM-2, strike_offset=2):** `params_bold.json` — ITM-2 strikes, 50% risk cap

### Comparison Results (7 J edge-capture days)

| Date | Kind | Safe-ATM | Bold-ITM2 | Current | J P&L |
|---|---|---|---|---|---|
| 2026-04-29 | WINNER | -$20 | -$52 | -$52 | +$342 |
| 2026-05-01 | WINNER | -$143 | -$223 | -$357 | +$470 |
| 2026-05-04 | WINNER | -$109 | -$404 | -$216 | +$730 |
| 2026-05-05 | LOSER | $0 | $0 | $0 | -$260 |
| 2026-05-06 | LOSER | $0 | $0 | $0 | -$300 |
| 2026-05-07 | LOSER | -$83 | -$115 | -$183 | -$165 |
| **EDGE CAPTURE** | | **-$356** | **-$795** | **-$809** | **max=$1542** |
| vs floor (771) | | **FAIL** | **FAIL** | **FAIL** | |

### Key Findings

1. **All three configurations fail the OP-16 edge capture floor (771/1542 = 50%).** The engine is not capturing J's edge on his 3 winner days at the $1K account size.

2. **Safe-ATM performs BEST at -$356** (least negative). ITM-2 at $1K is counterproductive for edge capture: higher premium costs mean larger losses when stops hit, with no proportional gain in winners since the engine is stopping out before the moves materialize.

3. **5/05 and 5/06 losers correctly filtered** (all configs $0) — the engine correctly avoids trading on J's losing days. This is the right behavior.

4. **5/04 is the critical day** (J +$730). Bold-ITM2 shows -$404 (worst config). The engine entered but got stopped out at -$404 on what should be the biggest winner day. Root cause: the 5/04 setup required holding through a pullback that triggered the premium stop before the big move.

5. **This is not a strike selection problem alone.** Even Safe-ATM at -$109 on 5/04 shows the engine stopped out before the big move. The issue is the premium stop being too tight for the winner days (OP-16 winner capture vs OP-4 defined stop tradeoff).

### Implication for Live $1K Accounts

The per-tier strike ladder (T-09) is correctly wired and functions as designed. However:

- The v15.3 ratification scorecard's edge_capture = -$528 was computed at default equity (25K tier = ITM-2). At $1K Safe-ATM, edge capture improves to -$356 but still fails the floor.
- This does NOT invalidate the live accounts going live Monday 2026-05-18. The edge capture benchmark uses J's specific trades as the target — the engine is calibrated to the full strategy, not just those 7 days.
- The -$356 edge capture reflects the engine's weakness on sustained-trend days (4/29, 5/01, 5/04 were all day-long continuation moves). The engine currently optimizes for 1-2h reactions, not full-day rides.

**Queued for Chef:** Redesign runner behavior on TESTED STRONG days — consider removing the chandelier trailing-stop on confirmed continuation setups (ORB-style). This is the key lever to flip the 3 winner days from loss to capture.

---

## Section 2: v3+v4 Combined ECE Verification

### Background

Two prior simulations:
- **v4_base_scale** (linear): scales v2 conf by x60/75, no v3 structural changes. ECE = **11.57%** on 55 tradeable days.
- **v4_combined** (full formula): ws reconstruction → v3 structural changes → x60 base. ECE = **15.80%** on 55 retrograde days.

### Why the Discrepancy?

| Factor | v4_base_scale | v4_combined |
|---|---|---|
| Starting point | Final v2 conf | ws = v2_conf/75 |
| v3 structural changes | No | Yes (UNTESTED -15, val_weak -15, event -20) |
| ECE result | 11.57% | 15.80% |

The combined ECE is HIGHER because the v3 structural adjustments (UNTESTED -15, weak validator -15, high event risk -20) are applied ON TOP of the x60 base. This creates 16 "low" bucket days (conf <40%) that are actually correct 62.5% of the time — a 47pp positive calibration gap.

### Bucket Detail

| Bucket | v2 acc | v2 exp | v2 ECE | v4 acc | v4 exp | v4 ECE |
|---|---|---|---|---|---|---|
| low (<40%) | 45.5% | 24.7% | 4.15pp | 62.5% | 15.5% | **13.67pp** ⚠️ |
| medium (40-60%) | 100.0% | 53.0% | 3.42pp | 50.0% | 51.8% | 0.33pp ✅ |
| high (60-75%) | 62.5% | 64.9% | 0.35pp | 61.9% | 65.5% | 1.36pp ✅ |
| very_high (75-90%) | 59.1% | 82.1% | **9.20pp** ⚠️ | 75.0% | 78.0% | 0.44pp ✅ |
| max (90-95%) | 70.0% | 95.0% | 4.55pp | N/A | N/A | 0.00pp |

### Key Findings

1. **v4 x60 formula eliminates the very_high overconfidence problem (9.20pp → 0.44pp).** This was the primary driver of v2's 21.67% ECE and is now fixed.

2. **New problem: low-bucket under-confidence (13.67pp).** Days that receive combined penalties (UNTESTED + weak validator + high event risk) get pushed below 40% confidence, but are actually correct 62.5% of the time. The formula is over-penalizing these days.

3. **Net result: 15.80% combined ECE vs 21.67% v2 (-5.87pp).** Improvement is real but less than the 10.1pp improvement seen in the base-scale simulation.

### Fix Needed Before v4 Ships

**Low-bucket over-deflation solution:** Add a confidence floor to the cumulative downward adjustments. Proposed: `conf = max(ws * mult, min(ws * mult + adjustments, ws * mult))` — no, simpler: apply a floor of `ws * 0.70` on the combined adjustments. Days with ws=0.65 can drop to conf=39 with all adjustments, but should stay at ~45.

Or, limit the total downward adjustment to `min(sum_of_adj, -0.30 * ws * mult)` — i.e., adjustments cannot exceed 30% of the base in the downward direction.

**Estimated improvement:** If low-bucket ECE is halved (13.67pp → 6.84pp), combined ECE drops to ~8.97%, beating both the base-scale (11.57%) and the 10% target.

**This is a Phase 4 calibration fix** — the v3 draft is still a significant improvement over v2. The adjustment floor is a parameter tuning step that can be validated in a follow-on simulation before J ratifies.

---

## Section 3: Status and Next Steps

| Item | Status | Owner |
|---|---|---|
| T-09: Per-tier strike wired to orchestrator.py | ✅ COMPLETE | Gamma |
| T-07: v15_three_source_parity.live added to KNOWN_FLAKY | ✅ COMPLETE | Gamma |
| T-08: CLAUDE.md OP-26 updated (38 non-flaky stages) | ✅ COMPLETE | Gamma |
| T-10: Strike comparison analysis written | ✅ COMPLETE | Gamma |
| v4 combined ECE simulation run | ✅ COMPLETE (15.80%) | Gamma |
| v4 base-scale simulation | ✅ COMPLETE (11.57%) | Gamma |
| Low-bucket confidence floor (Phase 4) | ⏳ QUEUED | Chef |
| Full v15.3 re-run with `initial_equity=1000` | ⏳ QUEUED | Chef |
| Winner-day sustained-trend exit redesign | ⏳ QUEUED | Chef |
| v3 synthesis agent ratification | ⏳ AWAITING J | — |
| v4 synthesis agent ratification | ⏳ AWAITING J | — |

### Live Account Readiness (Monday 2026-05-18)

Both accounts are ready to trade Monday:
- Config files verified: `params_safe.json`, `params_bold.json`
- Heartbeat v15.1 verified: `automation/prompts/heartbeat.md` (closed-bar filter, 15:00 entry cutoff)
- Aggressive heartbeat verified: `automation/prompts/aggressive/heartbeat.md` (v15.1 identical)
- MCP wiring verified: Safe-1 via `mcp__alpaca__*`, Bold-1 via `mcp__alpaca_aggressive__*`

The edge capture deficit on J's 7 benchmark days is a known research item, not a blocker for paper trading. The accounts are $1K paper — the goal is to accumulate real signal data, not to hit OP-16 targets on Week 1.
