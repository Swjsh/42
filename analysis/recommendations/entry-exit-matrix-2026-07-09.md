# T-W7 layers (a)+(b) — ENTRY-EXIT-MATRIX confirmatory pass (T5)

Frozen v2 pre-registration, EXACTLY these candidates -- no re-picks, no new cells. Preflight: signal-set sha256_16 `b5e8931994b9d34b` (OK), pre-registration version 2 (OK).

**Fresh-slice signal set:** 18 signals kept (dated >= `2026-06-19`) of 54 generated over the full detector run `2026-05-01..2026-07-08` (everything before `2026-06-19` is warmup, discarded -- never replayed). sha256_16 `d10e1a3a51cbf155`. **~13 trading days -- SMALL BY CONSTRUCTION, disclosed not padded.**

## VERDICT TABLE

| candidate | layer (a) fresh-slice | layer (b) real-fills anchor | OVERALL |
|---|---|---|:--:|
| **exit-A (-50/+150/sell66/trail15/tgt-none)** | n=18, exp $-272.54, Δ-171.87 | $1500.9 vs ctl $-757.1 (n/r, n=17) | **FAIL** |
| **exit-B (per-band stop on exit-A body)** | n=18, exp $-253.57, Δ-152.90 | $2046.95 vs ctl $-757.1 (n/r, n=17) | **FAIL** |
| **exit-C + entry-2 (PAIRED, floor $0.30)** | n=11, exp $-14.73, Δ+85.94 | N/A (no real fills under entry-2) | **INCONCLUSIVE_NO_ANCHOR** |
| **entry-1 (floor $0.30) + CONTROL exit** | n=11, exp $-173.82, Δ-73.15 | $-72.5 vs ctl $-757.1 (n/r, n=6) | **FAIL** |
| **entry-1 (floor $0.30) + exit-A [likely ship combo]** | n=11, exp $-434.55, Δ-333.88 | $2820.6 vs ctl $-757.1 (n/r, n=6) | **FAIL** |

`Δ` = delta vs CONTROL replayed on the FULL fresh-slice population (same detector, same window). `n/r` = no-regression. Anchor `n` = unique (date,symbol) signals, NOT position count (ground rule 8).

## KEY FINDINGS (read before the per-candidate detail)

- CONTROL ITSELF loses on the fresh slice: exp $-100.67/tr, WR 5.6% (1 win of 18), worst trade $-386.0 -- 2026-06-19..07-08 was a genuinely bad stretch for ribbon_ride (both directions), not an exit-shape-specific problem.
- Every one of the 18 fresh signals that stopped out under CONTROL also stopped out under exit-A/exit-B at EXACTLY 2.5x the loss (stop-A/-B never once recovered to trigger TP1 in this window) -- verified by hand against the raw 5-min option bars (e.g. 2026-06-22 P entry $1.07: low touches -30.8% on the ENTRY bar itself, control stops immediately at -20%, price keeps bleeding to -50%+ by 13:00 with no bounce -> exit-A's -50% stop just rides the SAME decay further before cutting). This is why the wide/trailing exits that WIN on the burned window and the real-fills anchor LOSE MORE on this specific fresh slice: with no recoveries, a wider stop only adds downside, never captures upside.
- Layers (a) and (b) DISAGREE for exit-A/exit-B/entry-1+exitA: the real-fills anchor (7 trading days, 06-29..07-08) shows LARGE gains (+$1,501 to +$2,821 vs control -$757), while the fresh 13-day slice (06-22..07-08, a superset of the anchor's days) shows LARGE losses (control itself -$100.67/tr, candidates -$253 to -$435/tr). Per the pre-registration's own auto-ratify bar ('ALL must hold'), a failing OOS layer kills auto-ratification regardless of anchor strength -- verdict is FAIL/escalate-to-STOP-B, not a silent override in either direction. This conflict, not a clean pass, is the honest headline.
- entry-1's floor ($0.30) EXCLUDES the fresh slice's ONLY winning trade (2026-06-23 P, entered at $0.27 -- 3 cents under the floor), so entry-1+control's n=11 subset has ZERO winners (WR 0.0%) and looks strictly worse than the unfiltered control. This is a small-n artifact, not evidence against the floor thesis: one flipped trade (of 18) swings the entire sign of this candidate's layer (a) result, which is why n=11 barely clears the small-n gate (8) in spirit even though it clears it in number.
- exit-C+entry-2 is the ONE candidate that outperforms control on the fresh slice (exp $-14.73 vs control $-100.67, delta +85.94) -- still net negative in $ terms (the window was bad for everything) but the SMALLEST loss of any candidate and the only one with a positive WR trend (0.364 vs control's 0.056). No anchor exists to corroborate (entry-2 is shadow-only) -- this is suggestive, not confirmatory.

## Per-candidate detail

### `exit-A-wide-ride` — exit-A (-50/+150/sell66/trail15/tgt-none)

- **Verdict:** FAIL — layer(a) exp $-272.54 vs control $-100.67 (delta -171.87) -> FAIL; layer(b) anchor $1500.9 vs control $-757.1 -> no-regression
- Layer (a): n_eligible=18 (of 18 fresh signals), n_missed=0, expectancy $-272.54, total $-4905.8, WR 0.056, drop-top-3 $-347.0
  - control (same fresh window, full pop) exp $-100.67 | control (same eligible subset) exp $-100.67
  - delta vs control (full pop) -171.87 | delta vs control (same subset) -171.87
  - per-band: <0.20: n=4 exp=-76.25, 0.20-0.50: n=5 exp=-39.16, 0.50-1.00: n=7 exp=-415.0, >1.00: n=2 exp=-750.0
- Layer (b): anchor_total $1500.9 vs control $-757.1, n_positions=79, n_unique_signals=17, no_regression=True

### `exit-B-perband-hybrid` — exit-B (per-band stop on exit-A body)

- **Verdict:** FAIL — layer(a) exp $-253.57 vs control $-100.67 (delta -152.90) -> FAIL; layer(b) anchor $2046.95 vs control $-757.1 -> no-regression
- Layer (a): n_eligible=18 (of 18 fresh signals), n_missed=0, expectancy $-253.57, total $-4564.3, WR 0.056, drop-top-3 $-328.73
  - control (same fresh window, full pop) exp $-100.67 | control (same eligible subset) exp $-100.67
  - delta vs control (full pop) -152.90 | delta vs control (same subset) -152.90
  - per-band: <0.20: n=4 exp=-38.12, 0.20-0.50: n=5 exp=-1.36, 0.50-1.00: n=7 exp=-415.0, >1.00: n=2 exp=-750.0
- Layer (b): anchor_total $2046.95 vs control $-757.1, n_positions=79, n_unique_signals=17, no_regression=True

### `exit-C-paired-scalp` — exit-C + entry-2 (PAIRED, floor $0.30)

- **Verdict:** INCONCLUSIVE_NO_ANCHOR — layer(a) exp $-14.73 vs control $-100.67 (delta +85.94) -> FAIL; layer(b) N/A (entry-2-limit-headroom is SHADOW-only per STOP-A sign-off condition 3 -- zero real fills exist under...)
- Layer (a): n_eligible=11 (of 18 fresh signals), n_missed=2, expectancy $-14.73, total $-162.05, WR 0.364, drop-top-3 $-177.07
  - control (same fresh window, full pop) exp $-100.67 | control (same eligible subset) exp $-173.82
  - delta vs control (full pop) +85.94 | delta vs control (same subset) +159.09
  - per-band: <0.20: n=0 exp=None, 0.20-0.50: n=2 exp=87.1, 0.50-1.00: n=7 exp=-23.91, >1.00: n=2 exp=-84.43
- Layer (b): **N/A** — entry-2-limit-headroom is SHADOW-only per STOP-A sign-off condition 3 -- zero real fills exist under a limit-headroom entry. Replaying exit-C's exit body against the REAL market-priced entries would test exit-C standalone with a market entry, which the pre-registration explicitly forbids (exit-C is weak standalone: exp $13.19/tr, rank 609/2016 in the exploratory grid). Anchor owed once entry-2's shadow ledger (or a live arm) produces real limit-headroom fills.

### `entry-1+control` — entry-1 (floor $0.30) + CONTROL exit

- **Verdict:** FAIL — layer(a) exp $-173.82 vs control $-100.67 (delta -73.15) -> FAIL; layer(b) anchor $-72.5 vs control $-757.1 -> no-regression
- Layer (a): n_eligible=11 (of 18 fresh signals), n_missed=0, expectancy $-173.82, total $-1912.0, WR 0.0, drop-top-3 $-204.25
  - control (same fresh window, full pop) exp $-100.67 | control (same eligible subset) exp $-173.82
  - delta vs control (full pop) -73.15 | delta vs control (same subset) +0.00
  - per-band: <0.20: n=0 exp=None, 0.20-0.50: n=2 exp=-75.0, 0.50-1.00: n=7 exp=-166.0, >1.00: n=2 exp=-300.0
- Layer (b): anchor_total $-72.5 vs control $-757.1, n_positions=16, n_unique_signals=6, no_regression=True

### `entry-1+exitA` — entry-1 (floor $0.30) + exit-A [likely ship combo]

- **Verdict:** FAIL — layer(a) exp $-434.55 vs control $-100.67 (delta -333.88) -> FAIL; layer(b) anchor $2820.6 vs control $-757.1 -> no-regression
- Layer (a): n_eligible=11 (of 18 fresh signals), n_missed=0, expectancy $-434.55, total $-4780.0, WR 0.0, drop-top-3 $-510.62
  - control (same fresh window, full pop) exp $-100.67 | control (same eligible subset) exp $-173.82
  - delta vs control (full pop) -333.88 | delta vs control (same subset) -260.73
  - per-band: <0.20: n=0 exp=None, 0.20-0.50: n=2 exp=-187.5, 0.50-1.00: n=7 exp=-415.0, >1.00: n=2 exp=-750.0
- Layer (b): anchor_total $2820.6 vs control $-757.1, n_positions=16, n_unique_signals=6, no_regression=True

## Layer (b) anchor overview

Reconstructed **79 positions** = **17 unique (date,symbol) signals** over 7 trading days (2026-06-29..2026-07-08) from fleet_rest engine-attributed fills (safe-1/safe-3/risky-1/risky-3). Actual realized: $-893.0 vs replayed CONTROL: $-757.1 (n_valid=79, n_nodata=0).

## Disclosures

- Fresh-slice window 2026-06-19..2026-07-08 (~13 trading days) is SMALL BY CONSTRUCTION -- disclosed, not padded (STOP-A directive).
- Detector warmed up on 2026-05-01..2026-06-18 (ribbon EMA<=48 5-min bars, level lookback<=10 trading days) -- warmup-window signals produce NO kept trades (filtered out before any replay).
- Frictionless fills at trigger levels; 5-min OPRA bars for layer (a) (touch stops; 1m-close timing owed); premium-only replay (ribbon/level/chart exits OFF, same as every prior anchor).
- qty 10 fixed; absolute $/edge_capture ignore the kill switch + per-trade cap -- relative-to-control and the anchor are the trustworthy signals (same caveat as T4).
- Real-fills anchor = ONE regime, 1-min Alpaca OPRA bars, engine-attributed fleet_rest arms only (safe-1/safe-3/risky-1/risky-3) -- core-lane (safe-2/bold-2) engine fills excluded (fleet_rest is the anchor tool's established scope, per exit_shape_parity_study.py).
- exit-C-paired-scalp has NO real-fills anchor: entry-2 is SHADOW-only (STOP-A sign-off condition 3) -- zero live limit-headroom fills exist; testing exit-C against market-priced real entries would violate the pair-only constraint and is NOT done here.
- Layer (c) [fresh P5 grind, ~7560 combos] is a separate KILL-CHECK per STOP-A sign-off condition 2 -- NOT run by this pass.
- ribbon_ride only (ground rule 11); vwap_continuation entry/exit matrix is owed separately.

---
_Source: `backtest/tools/t5_confirmatory_matrix.py`. Layer (c) [fresh P5 grind] and layer (d) [forward paper] run separately per the STOP-A sign-off. Nothing ships from this file -- STOP CHECKPOINT B (Opus/Fable/J) decides what arms._

---

## ⛔ STOP-B DISPOSITION — Fable, 2026-07-09 ~01:25 ET (authority: J directive + signed STOP-A)

**KILLED tonight (layer-a fail per the pre-registration's own ALL-must-hold bar and STOP-A
sign-off condition 1):** exit-A, exit-B, entry-1+exit-A. The anchor says these shapes rescue
the fleet's real fills; the fresh slice says they lose 2.5x more in the current zero-recovery
regime. Under a layer conflict, the confirmatory layer wins BY DESIGN — that is exactly what
it was pre-registered for. The kill is a deliverable, not a failure.

**Root of the conflict (queued for stratified re-read):** premium-band confound — the anchor
population is dominated by sub-$0.20 fleet fills (where wide stops rescued), the fresh slice
by richer backtest-tier premia (where nothing recovered). If the stratified read confirms it,
the band-conditional exit-B is the natural re-candidate AFTER layer (c) (the 7560-combo grind)
completes — with the T2 caveat that per-band was always the refinement the data asked for.

**SHIPS tonight (each on its own evidence, unaffected or supported by this scorecard):**
1. **entry-1 premium floor $0.30, engine-wide, both lanes.** Fresh-slice "fail" is a
   disclosed one-trade artifact (the floor excluded the lone winner at $0.27 — n=11, one
   trade flips the sign). Standing evidence: T3 full population n=157 (control $22.91 →
   $36.62/tr at the floor), T2 mechanism (2-tick stops, 42% spread proxy sub-$0.20), and
   THIS scorecard's anchor: entry-1+control −$72.50 vs control −$757.10 — the floor alone
   rescued ~$685 of the real week's losses by refusing the toxic cohort. Floor only
   REFUSES trades; worst case = skipped winners, never a blow-up. Revert: one params key.
2. **vwap_continuation fleet-shape port** (T-W6 option a): full validated core cell
   (−0.06/+0.40/frac 0.8/PL fixed) replaces the stale, never-validated fleet ExitShape.
   Validated 2026-07-07, all 5 OP-22 gates PASS (vwapcont-exit-ab-ship-gate.json). Strike-
   distribution caveat recorded (validated at ATM; fleet arms size per account) — both old
   and new fleet combos are unvalidated at fleet strikes; the new one at least carries the
   validated exit body and matches the core lane. Revert: one ExitShape literal + waiver.

**STAYS SHADOW:** entry-2/exit-C — the ONLY candidate that beat control on the fresh slice
(−$14.73 vs −$100.67), which upgrades it to the strongest forward candidate, but it has no
live anchor and arming a brand-new order state machine overnight violates sign-off cond. 3.
Path: forward shadow accrual → T6 paper A/B.

**RIBBON_RIDE exit stays the incumbent −20/+150 tonight** — not because it is good (it is a
proven loser) but because every tested replacement is WORSE in the current regime per the
confirmatory layer, and the floor removes the cohort where it lost most. Layer (c) + the
band-stratified read decide the next candidate. This disposition is REVOKE-able by J.
