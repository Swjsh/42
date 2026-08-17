# RIBBON SPREAD MATRIX — 2026-08-17

> J's ask, after a session where filter 6 was the SOLE blocker on four level rejections he
> called correctly: *"The whole thirty cent ribbon spread thing, I think, is too static. I
> think it needs to be a bit more dynamic depending on what the day is doing. Can we get a
> backtest matrix staged that tests dynamic ribbon spread of like fifteen cents all the way
> through thirty cents to see if that helps or hurts us."*
>
> One-variable sweep, 2025-01-01..2026-06-18, real OPRA fills. Machine artifact:
> [`ribbon-spread-matrix-2026-08-17.json`](../recommendations/ribbon-spread-matrix-2026-08-17.json).
> Runner: [`ribbon_spread_matrix_2026_08_17.py`](../../backtest/autoresearch/ribbon_spread_matrix_2026_08_17.py).
> **PROPOSE-ONLY. Nothing armed, no params file touched.**

---

## VERDICT

**Your instinct is right — the gate should not be a fixed 30c — but the variable to condition
on is NOT the spread. It is the VIX REGIME, and the honest finding is much less comfortable
than "loosen the gate":**

**In 89% of trades (calm + mid VIX) this strategy loses money at EVERY spread threshold from
15c to 30c. No setting rescues it. All the profit lives in the 11% of trades taken at VIX ≥ 20.**

---

## 1. The aggregate sweep — production is the worst cell

| threshold | n | /day | total | exp/trade | WR | edge_capture |
|---|---:|---:|---:|---:|---:|---:|
| 15c | 343 | 1.51 | +$368 | +$1.1 | 41% | +689 |
| 18c | 324 | 1.47 | +$946 | +$2.9 | 41% | +709 |
| 20c | 317 | 1.46 | +$451 | +$1.4 | 40% | +709 |
| 22c | 312 | 1.46 | +$281 | +$0.9 | 40% | +709 |
| 24c | 307 | 1.45 | +$554 | +$1.8 | 40% | +709 |
| 26c | 293 | 1.42 | +$942 | **+$3.2** | 41% | +709 |
| 28c | 288 | 1.40 | +$800 | +$2.8 | 41% | +709 |
| **30c — PRODUCTION** | 281 | 1.38 | **+$41** | **+$0.1** | 41% | **−621** |

⚠️ **Do NOT read an optimum out of the total column.** It zigzags — +946, +451, +281, +554,
+942, +800 — which is noise, not a threshold response. A real effect would be monotonic. The
$281–$946 spread across ~300 trades is well inside variance.

**The one non-noisy signal is edge_capture**, and it is a cliff, not a slope:

```
18c .. 28c   EC = 709.07   (byte-identical across SIX thresholds -> same anchor trades)
30c PROD     EC = -621.0   ($1,330 swing at a single boundary)
```

EC being *identical* from 18c to 28c means the anchor-day trade set does not change until 30c.
Seven trades drop between 28c and 30c and at least one is a high-value anchor. **Production
sits at −40.3% of max edge capture; every looser setting sits at +46%.** OP-16 rejects any rung
below +50% regardless of aggregate — production fails its own doctrine bar on this metric.

## 2. The stratification — and this is the actual finding

| VIX bucket | n | best threshold | exp at best | exp across ALL thresholds |
|---|---:|---:|---:|---|
| calm (<15) | 31 | 20c | −$6.70 | −13.8 → −6.7 — **every cell negative** |
| mid (15–20) | 256 | 18c | −$5.23 | −12.1 → −5.2 — **every cell negative** |
| **elevated (≥20)** | **35** | 26c | **+$83.16** | **+65.8 → +83.2 — every cell positive** |

**The regime effect is ~$90/trade. The threshold effect inside any regime is ~$5.** The gate we
have been arguing about is a rounding error next to the question of whether to trade at all.

The tool printed `dynamic_justified: True` because the per-bucket optima differ (20 / 18 / 26).
**That is technically true and substantively misleading** — those optima wander inside noise
(the mid bucket's whole range is −$5.2 to −$12.1 on n=256). The distinct-optima test is too
weak a criterion; recording it here so nobody cites "dynamic justified" as if it endorsed a
dynamic spread rule. It does not.

## 3. What this says about today

Today ran at **VIX 15.0–15.1 — the mid bucket**, where expectancy is negative at every
threshold tested. So filter 6's four refusals were, on this evidence, **more likely to have
saved money than cost it** — and we still finished **+$124** on the one trade that cleared.

That is the opposite of the conclusion the live exhibit invited, and it is exactly why the
matrix was run before touching anything.

## 4. Honest limits

- **n is thin at the edges**: elevated n=35, calm n=31 over 18 months. The mid bucket (n=256)
  is the only well-populated cell, and it is unambiguously negative.
- This is **one strategy family on the Safe $2K config**, not the whole book.
- The backtest window (2025-01..2026-06) shows **bear P&L positive and bull P&L negative in
  every single cell** (+$1,542..+$2,844 vs −$1,163..−$2,415). ⚠️ That **cuts against** the
  live-fills finding filed 2026-08-16 in [[DIRECTION-SYMMETRY-AUDIT-2026-08-09]], which had
  bull ahead on a 4-week July–August window. Different eras, both measured honestly — which
  means "bull is the better side" is **not robust across periods** and should not be treated
  as settled. Flagging against my own prior finding.
- No permutation null, no matched suppress-k-at-random control. Per the 2026-08-12 standing
  rule, any rule that deletes k trades on a losing population earns the base rate for free.

## 5. What I did NOT do

**Nothing is armed.** No params file touched, no threshold changed, no filter edited.

The defensible next step is **not** "set the spread to 26c". It is a pre-registered test of
**a VIX-regime standdown** — the effect that is 18× larger than the knob J asked about — with
its own OOS split, permutation null and random-suppression control. Loosening filter 6 on a
noisy total column would be re-deriving the base rate and calling it edge.

---

**Method note.** The first run of this study reported `dynamic_justified: false` because the
VIX extractor guessed at field names (`vix`/`vix_now`/`vix_at_entry`) and missed the real one
(`entry_vix`), silently bucketing 100% of trades as "unknown". A false negative dressed as an
answer. The runner now refuses to report a dynamic verdict when VIX is unresolved on ≥50% of
trades, rather than repeating it.
