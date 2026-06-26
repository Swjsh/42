# Strategy candidate: entry_bar_body_pct_min (BEAR doji gate) re-validation

> DRAFT — Chef proposal 2026-06-26 11:37 ET. J ratifies.
>
> **Re-validation of a direction-block under the CURRENT real-fills engine** (J-directed 2026-06-26 prune: every direction-block must justify itself under the current ITM/managed-exit engine or be removed).
>
> **CLASSIFICATION CORRECTION:** the work item labeled this a "bull-direction block." It is **NOT**. Gate #13 `entry_bar_body_pct_min` fires **only when `side == "P"` (BEAR/puts)** — `backtest/lib/engine/gates.py:380` `if _body_min > 0.0 and side == "P"`. There is a SEPARATE bull twin (gate #14 `entry_bar_body_pct_min_bull`, default 0.0 = OFF). The scorecard itself says `"applies_to": "BEAR entries only (BULL not yet analyzed)"`. I evaluated the block as it actually is: a **BEAR** doji-entry suppressor.

## Hypothesis
`entry_bar_body_pct_min=0.20` blocks BEAR (put) entries whose trigger-bar body is < 20% of its range (doji/wick-dominant = "no directional conviction"). It was ratified 2026-06-18 on the **OLD engine** (BS-sim discovery + OTM + wide premium-stop bracket): IS +$295, OOS +$566, WF 7.193. The directional claim to test: **under the CURRENT engine (REAL OPRA fills + per-tier strikes + managed exit_manager with −50% caps + chandelier trail), does blocking these doji-entry bears STILL produce a positive delta, or does the new exit structure now turn those doji entries into net winners the gate is suppressing?**

## Backtest evidence
- **Engine:** `run_backtest(..., use_real_fills=True, entry_bar_body_pct_min=X)` — the canonical REAL-fills simulator (`backtest/lib/simulator_real.py`, the only WR authority per C1). Direct kwarg, no params-cascade ambiguity.
- **Window:** 2025-01-02 .. 2026-06-18 (full OPRA option-bar coverage, 365 trading days).
- **A/B:** BLOCKED `entry_bar_body_pct_min=0.20` (prod) vs UNBLOCKED `=0.0`.

| Arm | Trades | Total real-fills P&L |
|---|---:|---:|
| UNBLOCKED (0.0) | 331 | **+$8,383** |
| BLOCKED (0.20, prod) | 291 | **+$10,329** |
| Aggregate gap | −40 | +$1,946 (BLOCKED higher) |

**Aggregate looks pro-block (+$1,946) — but that is a CASCADE ARTIFACT, not the gate's causal effect (L15):**
- **Direct causal effect** (side+date+time+strike identity diff): the gate removes **44 BEAR trades** netting **+$200** (15 winners +$4,649 vs 29 losers −$4,448; removed-set WR 34.1%, +$4.5/trade). → **direct block delta = −$200** (blocking these LOSES $200).
- The +$1,946 aggregate gap is driven by **4 cascade-introduced trades worth +$2,146** that appear only in the blocked run — they are state-shuffle (cooldown/sequence re-alignment after earlier bars are removed), NOT signal attributable to the body filter.
- The gate **suppresses 5 large bear winners**: +$1,361, +$881, +$841, +$493, +$320 (= +$3,896 of removed-winner P&L). The doji-entry filter is killing fat-tail winners, exactly the C3 trap.

- **edge_capture (OP-16):** UNCHANGED both arms. None of the 44 removed trades, and none of the engine's fired trades, fall on the 7 source-of-truth anchor dates. Anchor edge_capture is byte-identical blocked vs unblocked → **delta_edge_capture = 0.0**. (Both arms: anchor n=0 on all 6 in-range anchor dates — the orchestrator's `BEARISH_REJECTION` trigger does not fire on J's exact anchor entries in this config; the gate touches none of them either way.)
- **aggregate sharpe:** secondary tiebreaker only; the +$1,946 aggregate is a cascade artifact and not used to justify a verdict.
- **positive_quarters:** removed-set is net-positive in aggregate over the window; the direct block delta is the wrong sign (−$200) → the gate does not earn its keep on the metric that matters.
- **real_fills_validated:** YES — entire analysis is `use_real_fills=True`.

## Disclosures (per OP-20)
1. **Account-size assumption:** Safe-2 ($2K), per-tier strike (OTM-2 at $2-10K). Real-fills run uses the production strike picker (round-spot $1, auto-detected entry strike) — matches live per the C1 strike-picker gate.
2. **Sample-bias disclosure:** 44 directly-removed bear trades over 18 months is a modest sample; the −$200 direct delta is −$4.5/trade and within noise. But it is the WRONG SIGN for a block, and the removal of 5 trades each worth +$300..+$1,361 is a structural fat-tail-suppression risk, not noise.
3. **Out-of-sample test result:** The original scorecard's "OOS +$566" was on **BS-sim / OTM / wide premium-stop** (old engine). Under the current real-fills engine the removed set is **net-positive (+$200)** → the OOS edge did not survive the engine migration. This is the canonical C3/L182 failure mode (a structural gate validated on BS-sim that REAL fills do not reproduce).
4. **Real-fills check:** This IS the real-fills check (simulator_real via run_backtest --real-fills equivalent).
5. **Failure-mode enumeration:** (a) Cascade-confounding — aggregate diff is dominated by 4 unrelated cascade trades, NOT the gate (mitigated by reporting the direct identity-diff). (b) Fat-tail suppression — body<0.20 doji bars include large eventual bear winners under managed exits (the runner/profit-lock structure lets a weak-bodied entry still ride to a big move). (c) Anchor blindness — neither arm fires on anchors, so anchor-no-regression is trivially satisfied; the verdict rests on the general bear population.
6. **Concentration:** removed winners are concentrated in 5 trades (+$3,896 of +$4,649 winner P&L = 84% in top-5). Symmetrically the removed losers are diffuse small premium-stops (−$40..−$430). The gate trades away a concentrated upside for diffuse small-loss avoidance — net negative.

## Recommendation: **UNBLOCK** (stale — no longer earns its keep under the current engine)

The block was ratified on the OLD engine (BS-sim + OTM + −10% bear premium stop). Under the CURRENT real-fills + per-tier + managed-exit engine, its **direct causal effect is −$200** (it removes a net-WINNING set of bear doji entries) and it **suppresses 5 fat-tail bear winners** (up to +$1,361). The +$1,946 aggregate "win" is a cascade artifact (4 unrelated state-shuffle trades = +$2,146), not the gate's merit. Per OP-16/OP-22, a block that removes net-positive trades and relies on a cascade artifact to look good in aggregate does NOT beat the null — it fails the bar honestly applied.

This is NOT an "unblock to trade more" recommendation: the evidence is that the gate now blocks a slightly-winning population AND amputates the fat tail. The mechanism it was built on (doji = no conviction → loser) was true under BS-sim/wide-stops but is FALSE under managed exits where a weak-bodied entry still rides the runner.

**Anchor-no-regression: PASS.** Unblocking does not regress the bearish source-of-truth trades — neither arm fires on any of 4/29, 5/01, 5/04 (winners) or 5/05, 5/06, 5/07 (losers); delta_edge_capture = 0.0.

## Knob changes proposed
`automation/state/params.json` (Safe-2 — I do NOT edit this; J ratifies):

```
"entry_bar_body_pct_min": 0.20   ->   0.0
```

Setting `0.0` disables gate #13 for BEAR entries (gate logic: `if _body_min > 0.0 and side == "P"`). The bull twin (`entry_bar_body_pct_min_bull`) is already 0.0/OFF and is untouched. Revert path is symmetric (restore 0.20).

## Pre-merge gate
`python crypto/validators/runner.py` — **PASS** (97/98, 1 known-flaky `benchmark` live-source excluded, `overall_pass=True`, 5/14 replay 0.0% err). No code changed (read-only backtests + temp scripts removed); gym state unchanged before and after.

## My confidence (1-10) and why
**7/10.** The direct causal delta (−$200) is small and within trade-count noise, which tempers confidence — a strict reading could call it "no material effect either way." But three things push the verdict to UNBLOCK rather than KEEP: (1) the sign is wrong for a block (it removes a net-winner set), (2) it amputates a concentrated fat tail of bear winners (+$1,361/+$881/+$841) that the managed-exit structure specifically enables, and (3) it was ratified on the now-superseded BS-sim/wide-stop engine — a textbook C3/L182 stale-block. The aggregate +$1,946 is a confounded cascade artifact and must not be used to defend the block. Per the target-state directive, a block that cannot justify itself causally under the current engine should be removed.
