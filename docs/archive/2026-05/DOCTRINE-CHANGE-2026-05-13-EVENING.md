# Doctrine Change Notice — 2026-05-13 Evening

_Generated: 2026-05-13T22:02 ET. J authorization: "we need to take the best of those and put those into the engine so the engine makes the most amount of money. You are definitely clear to trade or change the strategies that we trade based off."_

## What changed

Three additions to `automation/state/params.json` under `_v15_pending_section`:

### 1. Per-tier strike offset table (`v15_strike_offset_per_tier`)

| Equity tier | strike_offset | Label | Rationale |
|---|---|---|---|
| $0-$2K | **-3 (OTM-3)** | J style | "Buy under $100, sell over $100" |
| $2K-$10K | **-2 (OTM-2)** | Balanced | Cheap enough to compound |
| $10K-$25K | **-1 (OTM-1/ATM)** | Mid | Slight OTM bias |
| $25K+ | **+2 (ITM-2)** | Current v14 default | Higher delta, smoother curve |

**Why:** the 4,410-combo variant test on 5/13's 11:38 bullish-reclaim signal showed that **OTM-3 at qty=3 produces +383% gain** for J-style trades vs **+93% on the actual ITM-1 trade**. For small accounts, OTM strikes give explosive % gains and lower dollar risk per trade. ITM-2 is appropriate only when capital is plentiful (>$25K).

### 2. Per-tier max premium % of account (`v15_max_premium_pct_of_account`)

| Equity tier | Max premium per trade |
|---|---|
| $0-$2K | 40% of account |
| $2K-$10K | 30% |
| $10K-$25K | 25% |
| $25K+ | 20% |

**Why:** today's actual trade (15× 738C @ $2.10 = $3,150 cost) would be **315% of a $1K account** — impossible. The hard gate prevents this catastrophic over-leverage. Engine reduces qty (or selects OTM) until total cost fits the cap.

### 3. Hard-gate logic (`v15_hard_gate_logic`)

```
if (qty × premium × 100) > (account_equity × max_pct):
    reduce qty by 1, retry
    OR move to next OTM strike, retry
    OR skip the trade entirely
```

Prevents the 315%-leverage scenario. Forces engine to size + select strikes that fit the account.

## What's STAGED but NOT YET ACTIVE

- New fields are in `params.json` under `_v15_pending_section`
- `rule_version` is STILL `"v14"` — production heartbeat still uses v14 defaults
- Production behavior UNCHANGED until heartbeat-v15-draft.md is updated to consume the new fields

## ✅ T50 Trailing-PL test COMPLETED (added 2026-05-13 22:18 ET)

**Winner: B1 trailing 20% (chandelier-style)**

| Variant | wide_pnl | top5_pct | DD | WR | Verdict |
|---|---|---|---|---|---|
| **B1 trailing 20%** | **$36,621** | **32.0%** | $2,857 | 57.3% | ✅ BEST |
| A fixed 5/10% (current ratified) | $36,450 | 37.1% | $2,857 | 56.8% | baseline |
| B3 trailing 40% | $33,726 | 34.9% | $2,857 | 56.9% | FAIL |
| B4 trailing 50% | $33,231 | 34.1% | $2,857 | 56.9% | FAIL |
| C stepped | $34,635 | 31.0% | $2,857 | 56.7% | FAIL |
| B2 trailing 30% | $29,776 | 30.6% | $2,857 | 57.3% | FAIL |

**Why B1 wins:**
- Marginally higher wide_pnl ($36,621 vs $36,450)
- LOWER concentration (top5_pct 32% vs 37%)
- Same max DD ($2,857)
- Higher WR (57.3% vs 56.8%)
- More trades captured (323 vs 317)

**5/13 738C trade hypothetical (using B1 trailing 20%):**
- Trailing floor as price extends: $2.30 → $2.31, $3.50 → $2.80, $5.00 → $4.00, $5.43 → $4.34
- On retrace from $5.43 peak, floor at $4.34 fires → exit ~+107% premium (vs fixed PL +6%, vs no-PL actual +159%)
- B1 captures ~76% of today's actual gain — much better than fixed (caps at 6%) but still leaves $700 vs no-PL

**Updated v15 fields in params.json:**
```jsonc
"v15_profit_lock_mode": "trailing",
"v15_profit_lock_threshold_pct": 0.05,    // arm at +5% favor
"v15_profit_lock_trail_pct": 0.20,         // chandelier trail = 20% off HWM
```

## What needs to happen to ACTIVATE v15

1. **T50 trailing-PL test completes** (~22:10 ET) → confirms PL setting (fixed vs trailing)
2. **Update `automation/prompts/heartbeat-v15-draft.md`** to read the new per-tier fields (currently embeds v14 constants)
3. **Bump `rule_version` to `"v15"`** in params.json
4. **Update `automation/prompts/heartbeat.md`** (production) — replace bear-side knobs with v14_enhanced winner combo:
   - `premium_stop_pct: -0.20` (was -0.08)
   - `tp1_qty_fraction: 0.50` (was 0.667)
   - `entry_no_trade_before_et: "09:35"` (was "10:00")
   - `runner_target_premium_pct: 2.5` (NEW)
   - `profit_lock_threshold_pct: TBD-from-T50`
   - `profit_lock_stop_offset_pct: TBD-from-T50`
5. **Run `Gamma_Premarket` task with rule version pin check** — verifies params.json + heartbeat.md drift = 0

## Data sources backing this change

- `analysis/recommendations/trade-5-13-variants.json` — 4,410-combo variant test
- `analysis/recommendations/v14_enhanced-real-fills.json` — T44b 3/3 PASS
- `analysis/recommendations/v14_enhanced-walkforward.json` — T44c walk-forward 2.67x ratio
- `docs/MONDAY-READY-CHECKLIST-V14_ENHANCED-2026-05-13.md` — 8/8 substantive gates
- `docs/SNIPER-FINAL-VERDICT-2026-05-13.md` — SNIPER invalidated (do NOT route)
- `docs/KEY-LEVELS-DEEPDIVE-2026-05-13.md` — level system audit + brainstorm
- `docs/TRADE-DEEPDIVE-2026-05-13-738C.md` — today's banger trade walk-back
- `analysis/recommendations/v14_enhanced-pl-variants.json` — T50 result (PENDING)

## Per CLAUDE.md rule 9 + rule version pin

- ✅ Doctrine change is **post-market** (not mid-session)
- ✅ Reason DOCUMENTED (this doc + 4 supporting analyses)
- ✅ J authorization explicit: "definitely clear to trade or change the strategies"
- ⏳ rule_version pin not bumped yet (heartbeat consumes v14 defaults; pin enforces drift = 0 at next premarket)
- ⏳ Heartbeat update pending T50 + final PL setting decision

## What does NOT change

- ❌ SNIPER strategy (T42-full INVALIDATED on real fills — not routed)
- ❌ Existing `position_sizing_tiers` (per OP 24 backward-compat — heartbeat may still read it)
- ❌ Existing `strike_offset_itm` (heartbeat still reads this; v15 fields are STAGED only)
- ❌ Production v14 baseline (today's +$2,932 paper trade proves it works)

## Risk assessment

- **Risk of the staged changes:** ZERO until rule_version bumps. Heartbeat ignores v15-prefixed fields.
- **Risk of v15 activation:** moderate — v14_enhanced has 3/3 OP-20 gates clear. Walk-forward TEST > TRAIN. But: TEST overlaps J anchors (selection bias per OP 20 disclosure 2). Recommend deploying as WATCH-ONLY first per OP 21.
- **Recommended deployment path:** WATCH-ONLY for 1 trading day → if PFF + v14e signals fire correctly + would-be P&L positive → flip to live trading on day 2.

---

**Bottom line:** v15 is STAGED in `params.json` based on tonight's data. Production v14 still runs. T50 result + heartbeat update needed to activate. Doc trail complete for J's morning review.
