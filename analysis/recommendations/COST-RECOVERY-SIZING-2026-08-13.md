# COST-RECOVERY SIZING — J directive 2026-08-13

> **J, verbatim:** *"we're not a home run factory. we need to ensure we are buying the right
> amount and right size contracts 20-40% and make back the money we spent on the entire trade.
> thats where the runners come in. i dont care what the math says... its not going to happen.
> you need to re think this."*

**Status:** FINDING + DESIGN. Nothing shipped. Written during market hours; no trading-path edit.

---

## The law J stated, formalized

First tranche must **recover the entire cost of the trade**. Sell `n` of `Q` at gain `r`:

```
n * E(1+r) * 100  >=  Q * E * 100        ->        n = ceil(Q / (1+r))
free_runners(Q, r) = Q - ceil(Q / (1+r))
```

`E` cancels — **the required tranche fraction depends only on `r`, and viability only on `Q`.**

| Q | +20% | +25% | +30% | +40% | +50% |
|---|---|---|---|---|---|
| 3 | 0 | 0 | 0 | 0 | **1** |
| 4 | 0 | 0 | 0 | **1** | **1** |
| 5 | 0 | **1** | **1** | **1** | **1** |
| 6 | **1** | **1** | **1** | **1** | **2** |
| 8 | **1** | **1** | **1** | **2** | **2** |
| 16 | **2** | **3** | **3** | **4** | **5** |

(cells = free runners after full cost recovery)

**Minimum Q to cost-recover inside J's 20-40% band:** +40% -> Q>=4 · +30% -> Q>=5 · +20% -> Q>=6.

> **3 contracts cannot cost-recover below +50%.** This is arithmetic, not a tuning opinion.

---

## Root cause chain (every link evidence-quoted)

1. **Rule 6 sets `min_contracts = 3`** — "Min 3 contracts (2 TP + 1 runner)", authored at $1-2K equity.

2. **The recency clamp uses that FLOOR as a CEILING.**
   `automation/state/fleet/fleet_executor.py:343-346`
   ```python
   min_qty = int(params.get("min_contracts", 3))
   clamped = min(int(qty), min_qty)
   ```

3. **It fired today.** `automation/state/fleet/<arm>/decisions.jsonl`, 2026-08-13:
   - `safe-3 : qty clamped 8 -> 3  : recency RED`  (equity 4470.48)
   - `risky-1: qty clamped 12 -> 5 : recency RED`  (equity 4979.42)

4. **Equity has tripled; the floor did not.** safe-2 live equity **$5,500.84** (CLAUDE.md still
   claims $1,746.75). 30% risk cap = $1,650; at $1.03/contract that affords **16**. Took **3**.

5. **3 contracts force TP1 >= +50%**, so the +100% TP1 inherited from the SS-B whole-cell port
   (`strategies.py:131`, commit `933bd651`) was never challenged — it was *consistent* with a
   3-lot even though nobody derived it that way.

6. **Result: a strategy that only pays on home runs.** TP1 +100% fires **20.4%** of the time
   (`tp1-reachability-2026-08-06.json`, `popA_tp1_fire_rate`).

**The exit shape is a symptom. The sizing is the disease.**

---

## Why the earlier "the math says no" did not apply

`tp1-reachability-2026-08-06.json` swept `tp1_premium_pct` x `tp1_qty_fraction` as **independent
knobs on a fixed position**. It never anchored the tranche to cost recovery and **never varied Q**.
Every cell it rejected lowered TP1 *while leaving the position at 3-5 lots* — which, per the law
above, guarantees the tranche cannot recover cost and the runner is still carrying the trade.
**J's structure was never a cell in that study.** The REJECT verdict does not bind here.

---

## Proposed design (NOT shipped)

**Decouple two decisions that are currently fused.**

- **KEEP the recency clamp.** It is A/B validated (`recency-sizing-ab.json`,
  `policy_dominates=true`, -$1,274 improvement over 8 real fleet-fill days). Removing it re-opens
  a proven loss. It correctly answers *"how much capital do I risk on an unconfirmed edge?"*
- **DERIVE the exit from realized Q at fill time.** The bug is that the exit shape is static
  (+100%) no matter whether the engine ends up holding 3 or 16 contracts.

```
r_first   = min{ r in [0.20 .. 0.50] : Q - ceil(Q/(1+r)) >= 1 }
qty_first = ceil(Q / (1 + r_first))          # sells exactly enough to recover cost
runners   = Q - qty_first                    # free carry, zero cost basis
```

Self-correcting: whatever the clamp does to Q, cost recovery stays achievable and runners are
always free. At Q=3 it reproduces today's +50% floor; at Q=8 it lands at +20%.

**Second lever (separate prereg):** `min_contracts` is pinned to $2K-era equity. The recency
config block itself still declares `equity: {safe: 2000.0, bold: 1648.0}` and `qty: {safe: 3,
bold: 5}` at `run_date 2026-08-12`. That is the L288-L290 class — *a cap mis-sized at birth fails
silently forever*. Scaling the floor with equity is a **separate** change and must not be bundled
with the exit-derivation change.

---

## The hard fact that constrains all of this

`tp1-reachability-2026-08-06.json`:
- `in_trade_under_control_walk_bar_open.median_mfe` = **+15.2%**
- `unconditional_session_max_bar_high.median_mfe` = **+83.8%**

**The median trade never reaches +20%.** No exit structure rescues a position that never moves in
your favor. Cost-recovery sizing fixes *how we get paid when we're right*; it does not fix *how
often we're right*. Both are live problems and they must not be conflated — a cost-recovery ladder
validated on entries with +15% median MFE would look like a losing change even if the structure is
correct.

**Therefore the study must report entry-conditional results**, not one pooled number.

---

## Validity gates (pre-registration, before any runner)

- **G1** — control arm reproduces today's live config exactly (Q=3/5, TP1 +100%) per arm.
- **G2** — vary-and-assert: the derivation must change `r_first` when Q changes, or it did not bind (C14).
- **G3** — report ALL cells including NOT-RUN; never report only movers.
- **G4** — stratify by whether the trade reached +20% at all. Pooling a +15%-median population
  hides the mechanism.
- **G5** — `automation/state/*` is READ-ONLY for the study.
- **G6** — a sign flip is not a resurrection. No cell is armed by this document.

## Provenance

- Root cause found 2026-08-13 ~10:50 ET from live decision ledgers + `fleet_executor.py`.
- Live equity read from broker `/v2/account` per arm, not from any cached state file.
- Directive is J's, unprompted, and overrides the earlier REJECT reading — correctly, because
  that study's population did not contain this structure.
