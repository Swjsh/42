# VOLRANKER SIZING OVERLAY — overnight-realized-vol as a SIZING knob on LIVE edge #1

**slug:** `overnight-vol-sizing-overlay` | **kind:** sizing_overlay (NOT a gate, never zeroes a day → L174-safe)
**Run:** 2026-06-21 | **Harness:** `backtest/autoresearch/_volranker_sizing.py` | **JSON:** `analysis/recommendations/volranker-sizing.json` (+ `volranker-sizing-mult-sweep.json`)
**Window:** 2025-01-02 .. 2026-06-18 (#1 stream); classifiable join bounded by MES 1m → 2026-06-12. **Fills:** real OPRA (C1, `_b10_sizing.simulate_stream`). **$0, Sunday research, no live edit / no orders / no commit.**

## VERDICT: **MARGINAL**

The overnight-realized-vol ranker is a legitimate, VIX-independent day-quality signal (W-track), and as a **sizing overlay** it is L174-safe by construction (never zeroes a day → no winner-removal). But its measurable benefit is **confined to the cap-bound $2K regime**, where it cleanly improves risk-adjusted return on BOTH books incl. OOS. At **$10K** (the hoped-for compounding case) it **FAILS the risk-adjusted bar** — and the reason is structural and important: **the min-3 contract floor pins the book at exactly 3 contracts at every realistic equity**, so the overlay has no room to size down and can only nudge top-vol days 3→4, which is an L175 variance-up trade (more total, worse Sharpe/Sortino, deeper maxDD).

---

## The hypothesis (and why it's well-founded)

The Sunday W-track (`_deploytiming_overnight_vol.py`) established overnight realized vol — `sum(|MES 1m logret|)` over 18:00→09:30 ET — as a **real, VIX-INDEPENDENT day-quality ranker**:
- **Within-VIX-mid-tercile control** (entry VIX 16.72–18.61, 53 days, VIX held ~constant): HIGH-overnight-vol days = **$141.35/day** (Sharpe 0.745, Sortino 3.736) vs LOW = **$24.20/day** (Sharpe 0.17). corr(overnight_rv, entry_VIX) = 0.874 but the control **survives** → overnight FLOW, not the DEAD VIX-level knob (C5/L122).
- It **failed as an ABSTAIN GATE** (L174 winner-removal): the low-vol days it would skip are still net-POSITIVE (+$4,803 Safe / +$6,816 Bold).

**The insight under test:** a ranker that fails as a *gate* can still work as a *sizing overlay* — it never zeroes a day (L174-safe), it only re-weights: size UP on top-tercile, DOWN on bottom (toward min-3, never below), BASE on mid. The W-track scorecard's own forward-looking note called for exactly this: *"a SIZE-UP-on-high-overnight-vol study, never an abstain."* This is that study.

## Method (all reused byte-for-byte — Sunday money-path guard)

- **Detector:** `_edgehunt_vwap_continuation.detect_signals` — the **LIVE #1** detector (167 signals).
- **Trade stream + fills:** `_b10_sizing.simulate_stream` (real OPRA; `pct` = qty-invariant return-on-capital). Safe-2 @ ATM (155 classifiable trades), Bold @ ITM-2 (156).
- **Overnight feature:** `_deploytiming_overnight_vol.overnight_vol_by_day` — the EXACT W-track definition.
- **Rule-6 clamp:** `_b10_sizing.contracts_from_fraction` — the same cap-clamp WP-3 uses (per-trade cap + min-3).
- **Causal tercile (no look-ahead, L06/L34):** each day's overnight_rv ranked vs the PRIOR 60-day window (shift-1); cuts = 1/3 & 2/3 quantiles of that trailing window; `<20` priors → BASE (no guess). Tercile counts: top 117 / mid 99 / bot 138 / base_warmup 20.
- **Schedule:** top ×1.5 / mid ×1.0 / bot ×0.6 on the per-trade equity fraction, then RE-CLAMPED through Rule-6 (never breaches cap, never zeroes a takeable day).

## Results — FLAT-3 vs overlay (real OPRA, fixed-equity risk metrics + compounding replay)

### $2,000 (Safe-2 current; cap-bound — overlay sizes DOWN organically via the per-trade cap)

| book | arm | per-trade Sharpe | per-day Sortino | total $ | maxDD frac | growth | **IMPROVES** |
|---|---|---|---|---|---|---|---|
| Safe-2 | FLAT-3 | 0.464 | 5.75 | 7,207 | 4.98% | 4.54× | — |
| Safe-2 | **overlay** | 0.463 | **6.04** | **7,724** | 6.32% | **4.87×** | **YES** |
| Bold | FLAT-3 | 0.452 | 7.08 | 11,528 | 11.95% | 6.60× | — |
| Bold | **overlay** | **0.455** | **7.78** | **12,737** | 12.16% | **7.19×** | **YES** |

**OOS-2026 (the honesty check) — also improves on both:** Safe Sortino 6.66→**7.74**, total $2,331→**$2,710**; Bold Sortino 6.21→**7.26**, total $3,938→**$4,599**. `OOS_HONEST_CLEAN = True` on BOTH books at $2K. The lift is NOT an in-sample lever-up artifact.

### $10,000 (the hoped-for compounding case — FAILS the risk-adjusted bar)

| book | arm | per-trade Sharpe | per-day Sortino | total $ | maxDD frac | growth | **IMPROVES** |
|---|---|---|---|---|---|---|---|
| Safe-2 | FLAT-3 | **0.387** | **1.49** | 6,976 | **2.89%** | 1.698× | — |
| Safe-2 | overlay | 0.377 | 1.31 | 7,643 | 3.65% | 1.757× | **NO** |
| Bold | FLAT-3 | **0.415** | **2.58** | 11,122 | **4.83%** | 2.112× | — |
| Bold | overlay | 0.399 | 1.87 | 12,232 | 6.02% | 2.223× | **NO** |

At $10K the overlay raises **total** (+$667 Safe / +$1,109 Bold) but **lowers per-trade Sharpe AND per-day Sortino** and **widens maxDD** on both books — a textbook **L175 variance-up trade**: more return bought with disproportionate downside. `OOS_HONEST_CLEAN = False`.

## Why $10K fails — the structural finding (the real takeaway)

The qty histograms expose it:

- **$10K FLAT-3:** **100% of trades sit at exactly 3 contracts** (`{"3": 155}`). The overlay can only move top-tercile days 3→4 (46–49 trades); mid/bot stay **pinned at 3 because min-3 is already the floor** — there is **no room to size DOWN**. So at $10K the overlay is purely a top-day up-size = the variance-up trade.
- **$2K FLAT-3:** already varies `{"1":8,"2":23,"3":122}` — the per-trade cap forces sub-min-3 on expensive trades, so the overlay's down-weighting happens **organically via the cap**, and the cheap top days up-size 3→4. Net: Sortino + total UP, OOS-clean.

**The deeper cause:** the book's **median premium is ~$1.35 (Safe) / $2.54 (Bold)**, so 3 contracts is only ~4% of a $10K account — far below even quarter-Kelly (WP-3 also lands on min-3 at these equities). The min-3 floor *dominates* the sizing. **Confirmed at $25K and $50K too:** FLAT stays at exactly 3 contracts and the overlay only nudges top days to 4 — the overlay never gets real room because the **baseline itself never lifts off the min-3 floor** at any realistic equity with this premium profile. A multiplier sweep (1.5/1.25/1.15/down-only/up-only) found every gentler schedule produces **zero delta** from FLAT at $10K (the multiplier can't cross an integer-contract boundary on a ~4%-of-equity base), and only the aggressive 1.5× moves anything — and what it moves is the variance-up trade.

## Caps + L174 honesty (all PASS)

- **0 cap breaches** at every cell (overlay never deploys past Rule-6 per-trade cap).
- **0 overlay-zeroed-FLAT-takeable trades** (overlay never removes a trade the baseline would take — L174-safe by construction).
- 2 `cap_skips_shared_both_arms` at Safe-2 $2K: two trades (prem $8.82, $6.06) where even **1 contract** breaches the 30% cap → un-takeable at $2K; **FLAT and overlay skip them identically** (a shared hard-cap constraint, NOT an overlay artifact). The hard cap correctly wins over min-3.

## Disposition

**MARGINAL — adopt the $2K rule, hold the $10K rule until the base lifts off min-3.**

1. **At sub-$5K (cap-bound), the overlay is a clean risk-reducer + return-adder** (both books, OOS-verified). This is the immediately-useful piece: on a low-overnight-vol night, size the #1 entry toward the bottom of the min-3 band / take the cheaper-strike fill; on a high-overnight-vol night, take the extra contract where the cap allows.
2. **At $10K+ the overlay as built is an L175 variance-up trade** (worse risk-adjusted) and should NOT ship — because the min-3 floor leaves no down-sizing room and the only action is a top-day up-size that fattens the tail.
3. **The compounding rule has VALUE only once the book sizes off the min-3 floor** — which, with the current low-premium profile, does not happen even at $50K under min-3 doctrine. The overlay becomes a genuine compounding lever **only if** the base size is lifted (e.g. a higher base contract count at higher tiers, or a higher-premium DTE/strike profile). Until then it's a $2K risk-tool, documented for the future.

**This is sizing research, not a flip.** Per the LIVE-PATH gate, #1 is currently **recency-RED** — no live sizing change ships on it regardless. This scorecard sets the *rule* for when capital is eventually deployed.

## NEXT DIRECTION

**Lift the base off the min-3 floor, THEN re-test the overlay** — the overlay is starved because min-3 dominates sizing at every realistic equity. Two concrete sub-questions:
- (a) **Premium-aware base sizing:** does anchoring the overlay on a *quarter-Kelly-or-higher* base (rather than min-3) at ≥$10K give the ranker room to express on BOTH the up- and down-side without the L175 penalty? (Requires WP-3 to adopt a base above min-3 at higher tiers — currently it doesn't.)
- (b) **Stack the overlay on the WP-8 1DTE/dollar-stop #1 config** (the actually-deployed variant, higher premium → 3 contracts is a larger % of equity → the floor binds less): the higher-premium 1DTE stream may give the overlay real down-sizing room at $10K where the 0DTE stream cannot. Re-run `_volranker_sizing` against the `_dte_stop_construction` 1DTE/dollar-stop fills.

---

*Reuse manifest (C14, no drift):* LIVE #1 detector + real-OPRA stream + Rule-6 clamp (`_b10_sizing`), overnight-vol feature (`_deploytiming_overnight_vol`), SPY/VIX merge (`recency_check`). Only new code = the causal tercile + the overlay sizing + the FLAT-vs-overlay risk-adjusted/compounding comparison. Validation: 8 deterministic self-tests PASS (`--validate`).
