# Strategy candidate: block_elite_bull re-validation (gate #3) — REVALIDATE_INCONCLUSIVE

> DRAFT — Chef proposal 2026-06-26 09:26 ET. J ratifies.

## Hypothesis
`block_elite_bull` (gates.py gate #3) blocks ELITE-tier BULL (C) entries carrying
`level_reclaim` inside VIX [0,25) on Safe (Bold band [15,18)). It was ratified
2026-06-18 on the **OLD engine** (BS-sim, OTM strikes, −8%/−10% premium stops). The
target-state question (J-directed 2026-06-26): under the **CURRENT engine** (REAL OPRA
fills + ITM/per-tier strikes + managed exits: partial TP1 + runner + chandelier
profit-lock + −50% catastrophe cap), does blocking these bulls STILL beat unblocking,
or does the new exit structure now turn the blocked config into winners?

**Directional claim tested:** the scorecard's OOS "loser" 2026-05-13 (−$29 on the old
engine) should flip sign under managed exits. **Confirmed** — it is now a **+$2,452
winner**. The old rationale is dead. But that does NOT automatically justify UNBLOCK.

## Backtest evidence
- **Engine:** `runner.run_with_params(..., use_real_fills=True)` — the C1 WR authority.
- **Window:** 2025-01-02 .. 2026-06-18 (full option-cache coverage; 8,408 contract CSVs).
- **A/B (block ON = production vs OFF = unblocked), whole book, real fills:**
  - BLOCK ON : 35 trades, **+$9,147** total, **$261/trade**
  - BLOCK OFF: 71 trades, **+$10,750** total, **$151/trade**
  - **Aggregate delta (OFF − ON): +$1,602** → raw P&L says unblocking earns money.
- **The gate-target subset (38 ELITE+level_reclaim bull trades the gate suppresses):**
  - Sum **+$3,297**, per-trade **+$86.8**, **WR = 8/38 = 21%**
  - **BUT concentration is fatal:** top1 = **74%** of the subset P&L (the +$2,452 on
    05-13). **ex-top1 per-trade = +$22.7; ex-top3 per-trade = −$51.9; ex-top5 =
    −$115.3.** In EVERY sub-window, removing just the single top winner flips the
    population negative (2025-H1 ex-top1 = −$11/t; 2025-09+ = −$8/t; 2026 = −$18/t).
  - per-trade Sharpe of the subset = **0.145** (mean $86.7 / sd $599).
- **Cascade:** blocking frees a quality slot → a **+$1,695 pair (2 trades)** that the
  OFF book never takes. So OFF gains +$3,297 on the targets but forfeits +$1,695 →
  net +$1,602.
- **Anchor no-regression (OP-16 bear source-of-truth):** **NO regression.** ON==OFF on
  every anchor date (4/29 −$540, 5/04 +$300, 5/07 +$378). The gate only touches BULL.
- real_fills_validated: **yes** (the whole A/B is real fills).

## The verdict tension (OP-22, applied honestly)
- **By raw aggregate P&L:** blocking does NOT beat unblocking — OFF is +$1,602.
- **By per-trade quality / `final_score = edge_capture × Sharpe`:** blocking WINS —
  unblocking dilutes book per-trade $261 → $151 and the subset has **no broad-based
  per-trade edge**; its positive aggregate is a 3-trade **lottery tail** (L166/L178/C24:
  "a positive aggregate a fat tail produces is not a per-trade option edge"; "anchor
  trades are one-off exceptional setups, the general population is losers").
- Recommending UNBLOCK here would be **"trading more on a fat tail"** (21% WR, 30 of 38
  systematic losers) — exactly the foot-gun OP-16's `final_score` multiplier exists to
  veto. Recommending a blind KEEP relies on the gate doing the right thing for a
  now-**stale** reason (the old OTM/BS-sim rationale is dead).
- **Therefore: REVALIDATE_INCONCLUSIVE.** The block must be **re-derived**, not blindly
  kept or dropped. The right fix is NOT "unblock all" (imports 30 losers for a tail) and
  NOT "keep the stale VIX[0,25) band" (its evidence is invalid) — it is a gate that keeps
  the systematic losers out **without forfeiting the structural right tail**.

## Disclosures (per OP-20)
1. **Account-size assumption:** A/B run with `enforce_cap=False` to measure the raw gate
   effect (not the $2K cap-admission). At Safe $2K/qty-tier the +$2,452 and +$1,295/+$1,362
   tail winners may be cap-clipped — meaning the *realized* unblock upside is likely
   SMALLER than +$1,602 (L180 cap-realizability). This strengthens KEEP/INCONCLUSIVE.
2. **Sample-bias:** 38 gate-target trades over 18 months. The entire positive aggregate
   rests on 3 dates (05-13-26, 12-24-25, 01-12-26). N-effective for the "edge" ≈ 3.
3. **Out-of-sample:** split 3 ways (2025-H1 / 2025-09+ / 2026-only). Every split is
   positive ONLY with its top winner; all flip negative ex-top1. No OOS-stable per-trade edge.
4. **Real-fills check:** done — this IS the real-fills A/B (C1 authority).
5. **Failure-mode enumeration:** (a) UNBLOCK imports 30 systematic −$185-avg losers to
   chase 8 tails; (b) the +$1,695 cascade pair is forfeited on unblock; (c) per-trade
   Sharpe 0.145 drags `final_score`; (d) cap-admission likely clips the very tail winners
   that make OFF look positive.
6. **Concentration:** top1 = **74%** of subset P&L; top5 = **216%** (losers net against
   it). This is the single worst concentration profile I have measured — auto-disqualifying
   for a clean UNBLOCK.

## Knob changes proposed
**NONE yet — do not change params.json.** This is INCONCLUSIVE, not a ship.
- **Reject the blind UNBLOCK** (`block_elite_bull=false`) — it is the "trade more on a
  tail" anti-pattern; `final_score` falls even as raw P&L rises.
- **Reject keeping the stale band as-is on its original evidence** — the 2026-06-18
  scorecard is invalid under the current engine (its OOS "loser" 05-13 is now a +$2,452
  winner). The gate currently does the right *aggregate-quality* thing for the wrong
  (stale) reason.
- **Re-derivation work item (next fire):** characterize the 30 systematic losers vs the
  3 tail winners — is there a separable trigger/time/VIX/structure signature (e.g.
  morning level_reclaim breakouts = the tails; midday/afternoon level_reclaim = the
  bleed)? If a clean discriminator exists, propose a *narrowed* gate that keeps the
  losers out and lets the tail through — that would be a genuine UNBLOCK-with-carveout
  with a real `final_score` gain. Until then, the gate stays.

## Pre-merge gate
`python crypto/validators/runner.py` → **97/98 PASS, overall_pass=True** (1 excluded =
KNOWN_FLAKY_LIVE_SOURCE). Green before and after this work (no production files touched;
only an autoresearch diagnostic added).

## My confidence (1-10) and why
**7/10** in the INCONCLUSIVE verdict. High confidence the blind UNBLOCK is wrong (the
74%-one-trade concentration is unambiguous and reproduces across every sub-window). High
confidence the original block evidence is stale (05-13 sign-flip is proven). The residual
uncertainty (why not 8 or 9) is that I have NOT yet found the loser/tail discriminator
that would convert this into a clean narrowed-gate proposal — that is the next fire.
