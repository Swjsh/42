# Grind: brand-NEW entry families — 2026-06-25

> **Mandate:** widen the strategy table beyond the one family already found (tight-stop OTM
> ride on the ribbon rejection/reclaim entry) by grinding genuinely-**new ENTRIES** through
> the phased grinder. The bar: real OPRA fills (C1) + beat the random-entry null MAX +
> drop-top5 (C3/L58/L171) + WF≥0.70 + cross-quarter (qpf) + live-cap realizable (L180), with
> the multiple-testing hurdle disclosed (C4). **Most candidates will DIE at the null — that
> is the point** (a 0DTE asymmetric bracket is mildly positive on almost any entry; only a
> real entry edge beats random entry through the SAME bracket).

---

## What was built (propose-only, zero production touch)

Four new ENTRY detectors (not strike/exit variations of the live ribbon edge), from the
SwjshAlgoKnife extraction shortlist (`markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md`):

| Family | Entry thesis | Source |
|---|---|---|
| `supply_demand_zone` | fresh impulse-candle S/D zone, reversal on FIRST retest | Boba (#5) |
| `ema_adx` | EMA(9/21) cross GATED by ADX(14) > 25 (trend, not chop) | EMA+ADX (#6) |
| `three_ducks` | multi-timeframe SMA alignment (5m cross + slow SMA39/78 agree) | Three Ducks (#7) |
| `bollinger_squeeze` | BB(20,2) bandwidth squeeze → expansion breakout + volume | BB squeeze (#8) |

Code (all new, all `backtest/autoresearch/`, $0, no LLM in the loop, no orders, no
production module edited):
- `family_detectors.py` — the 4 causal detectors + per-session causal indicators (SMA/EMA
  continuous; ATR/ADX/Bollinger per-session so overnight gaps never inject a TR/std spike).
- `test_family_detectors.py` — TDD incl. the **look-ahead guard** (truncation-invariance:
  truncating after bar T must not change any signal at bar_idx < T — C6/L14/34/57/61). 12/12 pass.
- `family_grind.py` — shared harness: strike×stop matrix → exit refine → funnel (qpf +
  live-cap realizable + **null**) → consolidation. Reuses `simulate_trade_real` (C1),
  `null_baseline` (C3), `mass_grind.qty_realizability` (L180).
- `grind_new_families.py` — driver + cross-family multiple-testing accounting.

### Methodology notes (the disciplines that make this honest)

- **Real OPRA fills only (C1).** Every cell is `simulate_trade_real` over the cached OPRA
  bars; uncached strikes (e.g. OTM-4 outside the ±$5 band) are counted as `no_data`, never faked.
- **The null is the binding gate (C3/L58/L171).** For each P3 survivor we re-run the SAME
  trade count / call-put mix / strike / stop / **exit bracket** at RANDOM RTH bars in the
  same entry window. The signal must beat the null's MAX (luckiest of 10 seeds), and the
  concentration-robust drop-top5 per-trade must beat the null MEAN. **Stricter than the stock
  funnel null:** ours uses the cell's *matching* exit bracket (via a `sim_fn` partial), so a
  PASS isolates ENTRY-timing alpha, not a better exit knob leaking in.
- **Stop geometry held identical to the null.** Each signal's stop is the same 12-bar swing
  invalidation the null uses → the only difference signal-vs-null is WHERE the entry is.
- **Candidate bar (not EC≥771).** The ribbon mass-grind gates on OP-16 `edge_capture` ≥ 771,
  built on J's 3 bearish-PUT anchor days. A brand-new (often bullish, often non-anchor-day)
  entry has ~0 trades there → `edge_capture` is **vacuous** (backlog #5 flags this exactly).
  So new families gate on the edgehunt candidate bar (OOS_exp>0 AND ≥4/6 positive quarters
  AND top5<200% AND n≥20) + the null; `edge_capture` is computed FOR DISCLOSURE ONLY (with a
  `vacuous` flag).
- **Live-cap realizability (L180/C11).** P3 requires the live order gate to admit the order
  at the $2K Safe account minimum (`safe2000_q3` real_exp>0 AND admit≥0.5).
- **Multiple testing (C4/OP-20).** Each P3 survivor is one shot at the null (~p=1/11). The
  driver reports the shot count and family-wise false-positive rate; a lone PASS-P4 among
  many shots is treated as search-luck → forward paper-validation as a fleet challenger,
  NEVER an in-sample params flip.

### Detector signal counts (real data, 2025-01-01 .. 2026-06-18, 365 trading days)

| Family | signals | C / P | days fired | IS-2025 / OOS-2026 | note |
|---|---|---|---|---|---|
| `supply_demand_zone` | 248 | 82 / 166 | 178 (49%) | 188 / 60 | put-tilted |
| `ema_adx` | 136 | 72 / 64 | 107 (29%) | 95 / 41 | balanced, selective |
| `three_ducks` | 1133 | 649 / 484 | 357 (98%) | 759 / 374 | **frequent** (5m MA-cross fires most days; disclosed — the null adjudicates) |
| `bollinger_squeeze` | 316 | 157 / 159 | 248 (68%) | 214 / 102 | balanced |

---

## Results (grind complete 2026-06-25, 28.6 min, real OPRA fills)

`analysis/recommendations/grind-new-families-summary.json` + per-family
`family-grind-{family}.json` / `mass-grind-{family}-{progress,funnel}.jsonl`.

| Family | signals | P1-cand | P3 | P4 (stock null) | dir-null cross-check | **verdict** |
|---|---|---|---|---|---|---|
| `bollinger_squeeze` | 316 | 3 | 13 | **13** | **SURVIVES** | **FORWARD-VALIDATE** |
| `three_ducks` | 1133 | 5 | 8 | 4 | **COLLAPSES** | DEAD |
| `supply_demand_zone` | 248 | 12 | 28 | 1 | (1/28 = chance) | DEAD |
| `ema_adx` | 136 | 4 | 15 | 0 | n/a | DEAD |

**Total: 64 null shots → 18 stock-null P4 → ONE survives adversarial verification.**

### The stock random-entry null is necessary but NOT sufficient — the direction-controlled null

The standard null (C3/L58/L171) randomizes entry timing AND shuffles the call/put **side**.
A directional entry therefore beats it partly just by *picking the right direction* (the
null's calls land on down-moves half the time). To isolate genuine **selection** alpha from
mere direction-vs-random-direction, each survivor was re-tested against a **direction-
controlled null**: random bars, but side = the entry bar's OWN direction (a momentum-aware
random entry). `backtest/autoresearch/_verify_bollinger.py` (parameterized by family/cell).

- **`three_ducks`** passed the stock null (4/8 P4) but **COLLAPSES** vs the dir-null: signal
  $10.9 < dir-null max $15.0; drop-top5 $8.2 < dir-null mean $9.1. Its "edge" is pure
  direction-following — a momentum-aware coin-flip *beats* it. It fires on 98% of days
  (C27 noise) and only passed the stock null because that null guesses direction. **DEAD.**
- **`bollinger_squeeze`** **SURVIVES** the dir-null: signal $34.9 > dir-null max $26.3;
  drop-top5 $24.0 > dir-null mean $17.8 (+$6.3 robust). The squeeze pre-condition adds
  selection value beyond "follow the last bar." (Honest limit: drop-top5 does NOT beat the
  dir-null *max* $26.3 — the robust margin is modest.)

### `bollinger_squeeze` — the one survivor (headline cell ATM / −8% / +30% TP1 / sell 66% / chandelier-trail 15%)

- **$34.9/trade** (qty 3), **n=303**, WR 37%. **OOS-2026 $43.6/tr > IS-2025** → **WF 1.43**
  (out-of-sample *stronger* than in-sample — not overfit). IS total $6,161 / OOS $4,407 /
  **total $10,568** over 18 months.
- **qpf = 1.0** (every one of the 6 quarters net-positive). top5-day concentration 33%
  (well under the 200% cap). max drawdown −$139 (qty 3, sequential).
- **Two-sided** (NOT a 2025-26 bull-drift artifact): CALLS +$4,531 ($29/tr) **and** PUTS
  +$6,037 ($41/tr) — puts profit *more*; both sides positive in *both* years.
- **13/13 is a coherent strike/stop surface** (ATM & OTM-1 columns, −8% through −20%), not a
  scattered lucky cell — which argues *against* multiple-testing luck (a false positive
  scatters; a real edge fills a column).
- Beats the stock-null MAX robustly: drop-top5 $24.0 > stock-null max $21.96.

## Verdict

**1 of 4 new families produced a genuine, adversarially-verified edge; 3 died — each for a
distinct, documented reason. A wall is progress: it eliminates three entry classes.**

- ❌ **`ema_adx`** — exit-structure artifact (C3/L58). 0/15 P4; positive cells are the
  bracket+regime, the EMA+ADX entry adds nothing over random entry.
- ❌ **`supply_demand_zone`** — search-luck + concentration. 1/28 P4 is *below* the ~2.5
  false-P4 chance expectation for 28 shots; the lone cell's drop-top5 per-trade is
  **negative** (−$3.65) → remove its 5 best days and it loses per trade.
- ❌ **`three_ducks`** — direction-following artifact. Passed the stock null (random side)
  but a momentum-aware random entry beats it; no squeeze/MTF *selection* alpha. 98%-day noise.
- ✅ **`bollinger_squeeze` → FORWARD-VALIDATE (fleet challenger).** The first *new* entry to
  clear the established null bar AND survive the stricter direction-controlled null:
  two-sided, OOS-stronger (WF 1.43), every quarter positive, coherent strike/stop surface.

**This is NOT an in-sample params flip.** It is a 64-shot search win — the deploy path is
**forward paper-validation as a fleet challenger** (backlog #5 / `consolidate_elites`
caveat / OP-20), never a blind `params.json` flip. Disclosures (OP-20): in-sample search
(multiple testing, partly mitigated by the coherent surface + dir-null cross-check + the
WF-1.43 OOS strength); $10,568 is qty-3 over 18 months (~$590/mo at 3 contracts, before the
live per-trade cap — realizability gated at `safe2000_q3` in P3); single 2025-26 regime; the
robust (drop-top5) margin over the momentum-aware null is modest. **Next step:** wire the
`bollinger_squeeze` detector into the fleet champion/challenger executor for live forward
validation; promote to live doctrine only after it proves forward (≥20 trades, OOS-consistent).

_Code (all `backtest/autoresearch/`, propose-only, $0): `family_detectors.py`,
`family_grind.py`, `grind_new_families.py`, `_verify_bollinger.py`, `test_family_detectors.py`._
