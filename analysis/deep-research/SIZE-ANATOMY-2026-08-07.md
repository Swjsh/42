# LANE 4 — THE $629 SIZE ANATOMY (2026-08-07)

**Run:** Friday 2026-08-07 ~12:1x ET, market OPEN — clock verified this session via
`python setup/scripts/et_clock.py` → `2026-08-07 12:07:13 Friday EDT, market_hours=True`.
Analysis-only: no trading-path file touched. Runner: `backtest/tools/size_anatomy_2026_08_07.py`
(assertions reconcile every day total against the official book before any cell is computed).
Data: `journal/trades.csv` T1 broker-truth round trips (Mon–Thu) + `automation/state/trade-today.json`
broker fills (Friday morning; bridge backfill not yet run). JSON twin:
`SIZE-ANATOMY-2026-08-07.json`.

**Verdict line:** −$629 was **not an oversize event** — it was 6.8% of the combined Rule-5 kill
budgets, per-contract loss a routine ~$22.50, and every arm sized exactly per its frozen design.
The 28-contract count is the frozen 2×3 grid EXPRESSING for the first time (ELITE tier + recency
GREEN + 4 arms on one shared signal). The requested {1.5%, 2%, 3%} dollar-risk cells are
**indistinguishable from each other at these equities** (the min-contract floors bind on 44–50 of
51 positions) and the one shippable variant fails G4 + sub-window + the standing population
refutation (LEVER-SIZING-2026-08-06 cell (e)). **No prereg staged. Nothing ships tonight.**

---

## 1. How 28 contracts happened — exact qty resolution, ledger-quoted

The morning trade: 09:40 close above PDH 771.82 → shared ENTER_BULL (bull_score 11, tier
SUPER/ELITE, triggers `level_reclaim + ribbon_flip + confluence`, trigger_level 771.53), filled
09:46–09:47 into the 09:45 pullback bar; 09:55 bar dumped 772.08→770.47; closed-bar structure
stops exited all four arms 10:01–10:02.

| Arm | Entry (fill) | qty | Resolution path (code-quoted) | Notional | Cat-cap $ risk (−50%) | P&L | $/ct |
|---|---|---:|---|---:|---:|---:|---:|
| safe-2 (core) | 772C @ 1.67, 09:46:34 | **3** | `heartbeat_core.py:2011-2015` — core sizes at `params.min_contracts` **flat** (3), then affordability-shrink only. Core NEVER reads `position_sizing_tiers`. Equity $5,727.59 → 30% cap $1,718 → 10 affordable → no shrink. | $501 (8.7% eq) | $250 (4.4% eq) | −$153 | **−$51.00** |
| safe-3 (fleet) | 772C @ 1.33, 09:47:07 | **8** | `fleet_executor._qty_for` → safe tier $2K–$10K `elite_qty: 8` (quality ELITE; equity $5,780.15). Recency GREEN today — no `qty clamped 8->3: recency RED` note (contrast its 08-04 rows). Notional 18.4% < 30% cap → no shrink. | $1,064 (18.4%) | $532 (9.2%) | −$176 | −$22.00 |
| risky-1 (fleet) | 772C @ 1.33, 09:47:08 | **5** | Bold tier elite 12 → ledger reason verbatim: `"qty clamped 12->5: FULL_SEND min size"` (`_apply_full_send_min_sizing`, bold `min_contracts: 5`). | $665 (10.5%) | $332 (5.3%) | −$95 | −$19.00 |
| risky-3 (fleet) | 774C @ 0.62, 09:47:09 | **12** | Bold tier $2K–$10K `elite_qty: 12` (equity $5,342.98). Strike 774 = OTM-2 via `bold_core_pre_ext` (the 08-06 per-arm ATM kill — **first live session on the reverted tier**). `cheap_contract_qty_boost` INERT (fires only < $0.50; premium 0.62). Notional 13.9% < 50% cap → no shrink. | $744 (13.9%) | $372 (7.0%) | −$204 | −$17.00 |
| bold-2 (core) | — | 0 | `RISK_DENY_PDT` at 09:46:35 — PDT-denied, did not trade. | — | — | — | — |

Book: **−$628 gross fills / −$629.46 official** (fees). 28 = 3+8+5+12.

**Intended design or emergent artifact? Both, at different levels — and neither is "cheap premiums":**

- **Per-arm: intended design.** The tier tables were frozen 2026-06-25 (`accounts.json`
  grid: safe 5/8, bold 8/12 at $2K–$10K); every fleet arm has been inside that band since its
  $5K start. qty is premium-blind — the elite numbers are what the design says at ELITE quality.
- **What changed Friday: the design finally EXPRESSED.** Mon–Tue the recency clamp was RED
  (`qty clamped 8->3` on safe-3's own 08-04 rows); the week's wins turned it GREEN, ELITE fired,
  so safe-3 went 8 and risky-3 went 12 for the first time. Equity growth did NOT raise qty
  (that needs $10K → 15/20).
- **Cheap premium argument is backwards.** risky-3's $0.62 OTM-2 premium made its *dollar*
  exposure SMALLER (13.9% of equity vs ~28% had it still been ATM at ~$1.33 × 12). The boost
  knob that would tie qty to cheapness never fired.
- **Book level: emergent, unbudgeted.** There is NO cross-arm book risk budget — by design
  (champion/challenger needs identical signals). 4 correlated arms × tier sizes = 28 contracts
  with one shared stop level. The book number J feels is per-arm-designed, book-unbudgeted.
- **Per-contract loss ordering INVERTS size:** safe-2 (qty 3) lost −$51/ct — worst — because core
  entered 64s earlier at 1.67 top-tick; the fleet arms filled 1.33/0.62 into the pullback and lost
  −$17 to −$22/ct. The morning's per-contract pain was **entry timing**, not size.

---

## 2. The dollar-risk lens — {1.5%, 2%, 3%} of equity, sequential, all arms, morning + week

**Design (frozen in the JSON `prereg_frame` before the run):** risk unit per contract =
`0.5 × entry_premium × 100` (the v15.3 −50% catastrophe cap — the designed max loss per
contract; a full-premium/gap-to-zero reading is the same table at f/2). `qty_cf = floor(f ×
equity_cf / risk_unit)`, sequential per-arm equity compounding from each arm's first
`equity_pre` of the week, `pnl_cf = pnl × qty_cf/qty` (position-level exact; LEVER-SIZING's
leg-rounding caveat carried). Population: 51 closed positions, 5 arms, Mon 08-03 → Fri 08-07
morning. **All cells reported.**

### The structural fact first

At $5.3–6.3K equities, f ∈ {1.5%, 2%, 3%} budgets $80–$190/trade. A $1.33 premium carries
$66.50 cat-cap risk per contract → computed qty 1–2, **below every production floor** (Rule 6
min-3 safe / `min_contracts` 5 bold). The directive's own example resolves to the deadlock:
constant-dollar at 2% would size safe-3's 1.33 entry at **qty 1**; the smallest legal safe
position (3 ct = $199.50 risk = 3.45% of equity) already exceeds every requested f. **The three
f-cells are therefore the SAME policy** wherever the floor binds — which is 44–50 of 51
positions. Proof: the shrink variant returns byte-identical results at all three f values.

### All cells (week Δ vs actual; actual week = +$3,060 incl. Friday morning)

| Cell | Week Δ | Fri AM (vs −$628) | Wed (vs −$1,935) | G3 ex-best Δ | G4 runner Δ | Drop-best-day Δ | floored | skipped | upsized |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.5% prod_floor | +$454 | −$399 | −$1,388 | +$766 | −$375 | +$513 | 50 | 0 | 1 |
| 1.5% prod_floor_shrink | **+$406** | **−$399** | **−$1,388** | +$717 | **−$423** | +$465 | 50 | 0 | 0 |
| 1.5% no_floor | −$1,484 | −$75 | $0 (all skipped) | −$758 | −$4,875 | +$1,225 | 0 | 17 | 1 |
| 2% prod_floor | +$503 | −$399 | −$1,388 | +$814 | −$326 | +$561 | 47 | 0 | 1 |
| 2% prod_floor_shrink | **+$406** | **−$399** | **−$1,388** | +$717 | **−$423** | +$465 | 47 | 0 | 0 |
| 2% no_floor | −$1,636 | −$143 | −$226 | −$910 | −$4,664 | +$1,102 | 0 | 6 | 1 |
| 3% prod_floor | +$850 | −$399 | −$1,388 | +$1,162 | +$21 | +$909 | 44 | 0 | 4 |
| 3% prod_floor_shrink | **+$406** | **−$399** | **−$1,388** | +$717 | **−$423** | +$465 | 45 | 0 | 0 |
| 3% no_floor | −$414 | −$218 | −$436 | +$209 | −$3,010 | +$1,428 | 0 | 0 | 4 |

The **shrink cell** (never size above live, floors respected — the pure "$629 is too big"
overlay) per day: Mon $0.00 / Tue −$58.50 / **Wed +$546.75** / Thu −$311.25 / **Fri AM +$229.00**;
week +$406.00. Its entire footprint is 14 positions — 12 of them risky-3 (8→5, 12→5) plus
Friday's safe-3 (8→3). It is not a dollar-risk policy in practice; **it is a "cap risky-3's tier
qty at min" policy wearing a dollar-risk costume.**

The **no_floor** cells are the only ones that actually cap risk at f — and they destroy the week
(−$414 to −$1,636) by cutting winners to 1–2 contracts (runner cohort −$3,010 to −$4,875) and
converting sizing into entry-gating (17 skips at 1.5%; Wednesday "saved" only because every
Wednesday trade got skipped). Not shippable (violates Rule 6), reported as sensitivity.

### Battery verdict for the best shippable cell (shrink)

- **G1 aggregate: PASS on the week** (+$406).
- **G3 ex-best: PASS** (+$717).
- **G4 runner cohort: FAIL** (−$423 — it shrinks the multi-leg winners: Tue's 763C +$524→+$328,
  Thu's 770P +$830→+$519).
- **Sub-window: FAIL** — halves flip sign (Mon–Wed +$488 / Thu–Fri −$82).
- **Drop-best-day: PASS** (+$465).
- **Population: FAIL by standing evidence.** LEVER-SIZING-2026-08-06 cell (e) refuted
  constant-dollar sizing on the 26-day book (−$2,981 at budget-neutral scale; return-on-notional
  is hump-shaped in premium, and constant-dollar loads the worst bucket). Its floor-everywhere
  oracle: 26-day book Δ −$335 with Tue −$965 (floor=3 defn; ours is 3/5 — definitions disclosed,
  direction identical). n=5 days here — no FDR pretense; the population verdict governs.

**DECISION: DO NOT STAGE a dollar-risk prereg.** 2 of 5 week gates fail, the population refutes
the family, and the requested f-range is unimplementable below the Rule-6/min-5 floors anyway.
The honest residual candidate — "risky-3 ELITE tier qty 12→5" — is week-positive (+$406) but
population-negative-by-proxy and sign-unstable; it goes to the shadow ledger as a MEASUREMENT
(risky-3's tier-qty exposure now has a priced weekly footprint), not a prereg. Wednesday still
loses −$1,388 in every legal cell — sizing does not cap a Wednesday (same conclusion
LEVER-SIZING reached at the Rule-6 floor).

---

## 3. Kill-switch context + C31

| Arm | SOD equity | Rule-5 budget | Morning loss | % of budget |
|---|---:|---:|---:|---:|
| safe-2 | $5,727.59 | −30% → $1,718.28 | −$153 | 8.9% |
| safe-3 | $5,780.15 | −30% → $1,734.05 | −$176 | 10.1% |
| risky-1 | $6,338.25 | −50% → $3,169.13 | −$95 | 3.0% |
| risky-3 | $5,342.98 | −50% → $2,671.49 | −$204 | 7.6% |
| **Book** | | **$9,292.95 combined** | **−$629.46** | **6.8%** |

The morning consumed 3–10% of any single arm's kill budget. −$629 *feels* large because it
aggregates four accounts; no arm was within an order of magnitude of its Rule-5 switch.

**C31, said plainly:** risky-3 at 12 lots (and safe-3 at 8) is deep inside C31's "3+ lots
−$17,461" band by count. **The caveat is load-bearing:** C31's corrected mechanism
(LEVER-SIZING §4, episode-level) is *averaging-down* — scaled-in episodes −$136.59 each vs
−$9.36 not-scaled (14.6×), while the pure per-contract size gradient is shallow (−$8.47 →
−$15.10/ct, 1.8×). This morning had **zero adds**: one entry, one closed-bar stop exit per arm,
and the 12:06 re-entry is a fresh trigger two hours later, not a scale-in. Today's tape even
inverts the size gradient (qty-3 arm lost the most per contract). 12 lots is C31-*territory*,
not C31-*mechanism* — the structural no-add guard (`fb.is_flat_spy_options` +
`test_never_average_down_2026_07_20.py`) is the thing actually standing between this book and
C31, and it held.

---

## 4. What this lane hands the close package

1. **−$629 anatomy closed:** design-expressed sizing (tier ELITE + recency GREEN + 4-arm
   correlation), 6.8% of combined kill budgets, per-contract loss driven by entry timing not size.
   The open sizing question is **book-level correlation budgeting** (4 arms, one signal, no
   cross-arm cap) — flagged as a finding, no proposal tonight.
2. **Dollar-risk normalization: REFUTED at the requested fractions** (floor-bound,
   indistinguishable cells, G4 + sub-window + population fails). No prereg staged. Sizing does
   not cap a Wednesday; that money lives in the entry/gating lanes.
3. **risky-3 OTM-2 revert, first live datapoint:** 12 × 0.62 = $744 notional (13.9% eq) —
   the reverted tier delivered a *smaller* dollar loss than ATM-at-12 would have carried into the
   same stop-out. One day, n=1, logged for the tier-kill forward ledger, no conclusion.
4. **Cross-lane pointer (ladder lane, not duplicated here):** `arm_score_ladder_replay.py`
   EXISTS at `backtest/tools/arm_score_ladder_replay.py`, with siblings
   `ladder_fullhist_replay.py` + `ladder_subset_prereg.py` and evidence set in
   `analysis/arm-ladder/` (ARM-LADDER-V1-2026-07-27, LADDER-FULLHIST-2026-07-27,
   LADDER-SUBSET-VERDICT-2026-07-28). `accounts.json` carries the DISARMED
   `score_ladder_doc` state on safe-3/risky-1 (floor=9 −$10,903 / floor=8 −$16,642 vs baseline
   +$5,307 on the 390-day replay) and risky-3's armed bear-only ladder. The new demote-not-veto
   semantics differ from the 07-27 floor test — that distinction belongs in the ladder prereg.

## Caveats

- Friday-morning rows come from `trade-today.json` broker fills (gross −$628; official −$629.46
  includes fees); Mon–Thu rows are T1 broker-truth `round_trips`. Mixed provenance, both broker-level.
- `pnl_cf = pnl × qty_cf/qty` holds fills fixed; a smaller order could fill differently
  (unmeasurable; LEVER-SIZING carried the same assumption).
- The 12:06–12:07 ET second-wave entries were OPEN at run time and are excluded from every number
  here; today's day total will move after the close.
- Same-day OPRA is 403 until ~16:21 — nothing here prices counterfactual contracts; every number
  is real-fill arithmetic (LABEL: no EST track needed for this lane).
- G4 "runner cohort" = multi-leg positions (n=17); Friday positions are single-exit and cannot
  enter that cohort.
- Sub-window halves on 5 days is a sign check, not a statistic; the population verdict rides on
  LEVER-SIZING's 26-day book + 141-day replay, quoted with its floor-definition difference (3
  everywhere vs 3/5 here).

## Artifacts

- `analysis/deep-research/SIZE-ANATOMY-2026-08-07.md` (this file)
- `analysis/deep-research/SIZE-ANATOMY-2026-08-07.json` (all cells, all positions, prereg frame)
- `backtest/tools/size_anatomy_2026_08_07.py` (runner; reconciliation assertions inline)
