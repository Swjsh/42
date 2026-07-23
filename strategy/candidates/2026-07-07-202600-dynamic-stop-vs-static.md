# Strategy candidate: DYNAMIC_STOP_VS_STATIC (vwap_continuation exit)

> DRAFT — Chef proposal 2026-07-07 20:26 ET. J ratifies.
> Answers J's directive: "every factor of each trade should be DYNAMIC based on current data, not hardcoded 8%."

## Hypothesis

`exit_manager.py:220` sets `stop = entry*(1+premium_stop_pct)` — a FIXED % (−0.06 / −0.08). J wants a
RULE that scales the stop to CURRENT market state at entry. **This tests the RULE-based dynamic stop**
(ATR-scaled / IV-scaled / structure-based, all computed causally at entry), NOT walk-forward re-optimization
(that already OVERFITS — `vwapcont-walkforward.json`). Directional claim under test: *a data-adaptive stop rule
beats a good fixed number out-of-sample.*

**Result: FALSIFIED. STATIC-IS-FINE.** No genuinely-varying dynamic rule beats a good fixed premium stop
OOS after drop-top3 + null. The one apparent "win" is the IV-scaler degenerating into a slightly-tighter
fixed constant (≈−0.06), which just reproduces the already-known `−0.06 > −0.08` fixed-number result — not a
dynamic edge. Same lesson as re-optimization: the *number* can be improved once; the *rule* adds nothing.

## Backtest evidence

- Signal: `vwap_continuation` (live watcher port, byte-for-byte), 166 signals (C=90, P=76).
- Fills: **real OPRA** via `_dte_expansion_sim.simulate_dte_trade` (C1) — next-bar entry, conservative
  stop-before-TP, honest overnight gap + expiry-intrinsic settlement. Same harness as `multiday-dte-compare.json`.
- OOS = 2026 (held out); IS = 2025. Strike tiers held CONSTANT within each comparison (C29): ATM Safe-2 cell
  (static baseline −0.06) and ITM-2 production cell (static baseline −0.08).
- Pre-registered grid (frozen before results read): STATIC | ATR_k{1.0,1.5,2.0} | IV_base{−0.06,−0.08} |
  STRUCT_buf{0.25,0.50}, each × DTE {0,1,2} × 2 tiers = 42 cells. Discipline: OOS split, drop-top3-days,
  random-entry null (120 iters, L172), BH-FDR q=0.10, exit-reason-mix (bind%) to prove the stop bound differently.

**Baseline static OOS exp/tr** (the answer to "does anything beat −0.06?"):

| Tier / DTE | Static OOS exp | Static drop3 | Best genuinely-varying dyn (OOS) | Verdict |
|---|---:|---:|---|---|
| ATM  DTE0 | **$28.90** | $31.62 | IV≈−0.06 $24.94 · ATR_k1.0 $12.33 · STRUCT $5.37 | STATIC-WINS |
| ATM  DTE1 | **$43.36** | $38.12 | ATR_k1.5 $36.92 · IV $35.88 · STRUCT $7.15 | STATIC-WINS |
| ATM  DTE2 | **$45.04** | $43.36 | STRUCT $112.41 **but drop3 $40.57 ≤ static, null_exp −$30** | STATIC-WINS (fat-tail mirage) |
| ITM2 DTE0 | **$36.34** | $45.13 | IV≈−0.06 $41.49 (drop3 $47.56) | DEGENERATE¹ |
| ITM2 DTE1 | **$59.02** | $59.05 | IV $50.63 · ATR_k1.5 $30.89 · STRUCT $18.36 | STATIC-WINS |
| ITM2 DTE2 | **$66.13** | $58.94 | STRUCT $118.75 **but drop3 $57.28 ≤ static, null_exp −$29** | STATIC-WINS (fat-tail mirage) |

¹ **The only cell that beats static on OOS AND drop3 is a mirage.** ITM2 static is −0.08; the IV-scaler at
VIX≈median collapses to a near-constant **−0.061** (p25/p75 = −0.069 / −0.057). So "IV beats static" here is just
**−0.06 beating −0.08** — the exact ship-gate finding, NOT a data-adaptive edge. Against the *same* fixed number
(ATM: static −0.06 vs IV≈−0.06) **static wins $28.90 vs $24.94** and bind% is identical (55.1 vs 55.8).

**The stop genuinely bound differently** (not a no-op relabel): premium-stop bind% moves 55% (static) → 12–29%
(STRUCT, med −0.58 to −0.79) → 26–52% (ATR). The dynamic rules DO change the trades — they just make them
worse OOS. Wider stops inflate full-sample WR (STRUCT ATM DTE0 WR 80.1%) and full-sample exp — the classic
in-sample WR mirage (C4) — while OOS exp collapses.

**DTE-interaction (multiday caveat test — "does a wider/structure stop travel better for a multi-day hold?"):
NOT confirmed.** Wider ATR (k2.0) mostly gets WORSE at higher DTE OOS (ATM: −$5.4 → +$4.7 → −$7.3; ITM2:
+$39.8 → +$31.9 → +$20.0, declining). The DTE2 STRUCT "benefit" is fat-tail settlement — drop-top3 pulls it back
to ≈static. Confirms the multiday memory: **the DTE lift is lower-theta-on-entry, not a wider stop.**

- FDR survivors (q=0.10, null-only): 6 cells clear the *null* — but the null just proves "beats a random entry,"
  which is trivially true for a real signal. The decisive gate is OOS-exp-vs-static + drop3, which none survive.
- real_fills_validated: **yes** (real OPRA via the same simulate path; anchor twin 585P reproduced in multiday run).

## Disclosures (per OP-20)

1. **Account-size assumption:** ATM cell = Safe-2 (~$1.76K, strike_offset 0); ITM-2 cell = $2–10K tier. Each tier
   held constant within its comparison; results do NOT cross tiers (C29).
2. **Sample-bias:** vwap_continuation only; 166 signals, OOS n=49–51/tier. Single family — not a market-wide claim.
3. **Out-of-sample:** OOS = 2026 held out. Every genuinely-varying dynamic rule LOSES to static OOS; the lone
   "beat" degenerates to a fixed constant (see ¹).
4. **Real-fills check:** real OPRA day-T bars + honest overnight settlement (C1). No BS-sim.
5. **Failure-mode enumeration:** (a) STRUCT/ATR wide stops → full-sample WR/exp mirage that drop-top3 erases;
   (b) IV-scaler at VIX≈median degenerates to base constant (dead knob risk, C14); (c) delta translation uses a
   FIXED per-tier approx (ATM 0.50 / ITM2 0.65) — no per-contract greeks in the DTE cache (bounded by clamp
   [−0.99,−0.02] + bind% audit); (d) VIX used as IV proxy — no per-contract IV feed; (e) DTE2 STRUCT wins are
   overnight-settlement fat tails, not a hold-longer edge.
6. **Concentration:** the two OOS "winners" (STRUCT DTE2) have OOS ≈$112–119 collapsing to drop3 ≈$40–57
   (≤ static) — i.e. top-3-day concentration IS the apparent edge. Static's OOS↔drop3 are close ($28.90↔$31.62,
   $66.13↔$58.94) = robust, not concentrated.

## Knob changes proposed

**NONE.** This is a NEGATIVE result that DEFENDS the current fixed premium stop against the "make it dynamic"
directive. `premium_stop_pct` stays a fixed number. (Secondary, out of scope here: the ship-gate already found
−0.06 > −0.08 for the ATM Safe-2 cell — a one-time fixed re-pick, not a dynamic rule; that ships via
`vwapcont-exit-ab-ship-gate.json`, not this candidate.) NEVER edit params.json myself.

## Pre-merge gate

`python crypto/validators/runner.py` — **103/104 PASS**. Sole FAIL = `v53_setup_dispatch.live`
(`SKIP_NO_FEED:sameday_5m_bars_missing`, market-closed, not chef-caused — identical to the WEEKLY_DTE baseline).
New guard `backtest/tests/test_dynamic_stop_ab.py` = **8/8 PASS** (static-ignores-features, ATR-widens-with-ATR,
IV-widens-with-VIX, structure-scales-with-distance, clamp-bounds, BH-FDR planted + all-null, ATR-causal-look-back).
No engine/params/production touched — only new files under `backtest/autoresearch/` + `backtest/tests/`.

## My confidence (1-10) and why

**8/10** that DYNAMIC-STOP loses to a good fixed number OOS on this setup. Two independent decisive tells:
(1) every genuinely-varying rule (ATR, STRUCT, high-vol IV) loses OOS and its "wins" evaporate under drop-top3;
(2) the lone survivor is the IV-scaler collapsing to a ≈−0.06 constant, so it's a fixed-number result wearing a
dynamic costume — against the same fixed number static wins. Docked 2: the delta→premium translation uses a
fixed per-tier delta (no greeks feed), and IV is VIX-proxied — a real per-contract-IV/greeks stop MIGHT behave
differently, but the burden of proof is now on that richer feed, not on the current fixed stop. Same lesson as
the walk-forward re-optimization test: **the number is worth a one-time re-pick; the adaptive machinery is not.**

Files: `backtest/autoresearch/dynamic_stop_ab.py`, `backtest/tests/test_dynamic_stop_ab.py`,
`analysis/recommendations/dynamic-stop-ab.json`.
