# Strategy candidate: UNBLOCK require_bearish_fill_bar (Bold)

> DRAFT — Chef proposal 2026-06-26 09:43:31. J ratifies.

## Hypothesis
`require_bearish_fill_bar` (gates.py gate #7, Bold=true, J-ratified 2026-06-17) is a
look-ahead BEAR-direction gate: after a bear (P) signal it requires the next (fill)
bar to close bearish; a bullish/doji fill bar => SKIP. It was ratified on the OLD
engine profile (bracket-only exits: TP1 + fixed runner_target + premium_stop, generic
strike). **Directional claim:** under the CURRENT Bold engine (real fills, ITM-2 strike,
tight -7% bear cap, MANAGED chandelier exit: arm +5% / trail 15% off HWM), the gate
now SUPPRESSES net-winning bear trades in-sample because the managed exit lets the
winners run and caps the losers — inverting the economics that justified the gate.
Recommend UNBLOCK (set `require_bearish_fill_bar=false` on Bold).

## Backtest evidence
- Engine profile: `simulator_real` real fills + `strike_offset=-2` (ITM-2) + `premium_stop_pct_bear=-0.07` + chandelier `profit_lock_mode=trailing, threshold=0.05, trail=0.15` + managed TP1(0.667)/runner.
- Train window (IS): 2025-01-02 .. 2026-05-07
- Test window (OOS): 2026-05-08 .. 2026-06-18
- A/B (gate ON = current state vs gate OFF = proposed):
  - **IS_delta (gate ON vs OFF): -$676** — gate ON COSTS money in-sample (G1 FAIL).
  - **OOS_delta: +$775** — gate ON helps OOS, but on a thin set (G2 PASS).
  - **WF_norm: -5.73** — IS and OOS deltas have OPPOSITE signs (G3 FAIL, sign-unstable).
  - **SW_hurt: 2/4** sub-windows hurt by gate ON > $500 (G4 FAIL).
  - Anchor (OP-16): PASS — engine takes ~0 trades on the exact J anchor dates; where it does (5/04 bear) candidate=+$32 vs base 0, no winner regression (G5 PASS).
- **Removed-trade audit (the decisive evidence):** the bear trades the gate REMOVES under the current managed exit are net **+$917 IS** (13 wins +$2,759 / 20 losses -$1,841) — i.e. removing them suppresses a net-winning set. OOS removed set is -$211 (n=5, marginal).
- **Per-window sign-stability of the gate's VALUE** (net P&L of removed bear trades; positive = gate suppresses winners):
  - W1 2025H1: -$888 (helps) | **W2 2025H2: +$937 (suppresses winners)** | **W3 2026Q1: +$972 (suppresses winners)** | W4 Apr-May26: -$104 | OOS: -$211 (n=5)
  - The gate only helps in the OLDEST window (W1) + a thin OOS tail; it actively hurts in the two largest, most-recent IS windows (W2, W3).
- aggregate sharpe: not the deciding metric here (gate is a single-population filter); P&L delta + sign-stability govern.
- real_fills_validated: yes (`simulator_real` via `run_backtest --real-fills`).

## Disclosures (per OP-20)
1. **Account-size assumption:** Bold/aggressive at ITM-2, 50% per-trade risk cap, $1.65K equity. Strikes do NOT transfer to Safe (C29); this is the Bold cell only.
2. **Sample-bias disclosure:** OOS removed-set is only n=5 trades — the OOS "gate helps" signal is statistically thin and should not outweigh the IS n=33 removed-set inversion. The OP-16 anchor days fall in the IS window, not OOS, and the engine barely trades them (the anchor "PASS" is near-vacuous — no-regression, not a strong endorsement).
3. **Out-of-sample test result:** OOS_delta=+$775 (gate ON helps OOS marginally) BUT WF_norm=-5.73 (sign-flip vs IS) => NOT OOS-sign-stable. Fails the OP-22 WF>=0.70 bar.
4. **Real-fills check:** entire study run on `simulator_real` (the only WR authority, C1). No BS-sim.
5. **Failure-mode enumeration:** (a) look-ahead gate — live needs a one-bar confirmation delay (Rule 9), so its live value is already softer than the backtest upper-bound; (b) removing it lets more bear trades through, slightly raising stop-rate exposure on doji fill bars — but the -7% cap + chandelier bound the downside (removed losses avg only -$92/trade IS); (c) OOS n=5 could be regime-lucky; (d) UNBLOCK trades MORE — must not be motivated by volume (it is not: motivated by the IS removed-set being net-positive).
6. **Concentration:** the gate's positive value is CONCENTRATED in W1 (2025 H1, -$888 removed) — a single older sub-window. top "helps" window carries the entire IS justification. Disclosed.

## Knob changes proposed
`automation/state/aggressive/params.json`:
- `require_bearish_fill_bar`: `true` -> **`false`**
(Also drop/annotate `_require_bearish_fill_bar_doc` as REVOKED-by-revalidation.)
NEVER edited by Chef — J ratifies. Safe account already has this REJECT (anchor FAIL on old engine); no change to Safe.

## Pre-merge gate
`python crypto/validators/runner.py`: **PASS** (97/98, overall_pass=True, 1 known-flaky `benchmark` excluded). Confirmed before and after this work; all changes are read-only analysis scripts + one JSON output, no live config touched.

## My confidence (1-10) and why
**6.** The IS removed-set inversion (+$917 net, driven by the managed exit letting winners run) is a clean, mechanism-level reason the gate is stale, and it shows up in the two largest recent IS windows (W2, W3). That is a genuine "no longer earns its keep / now blocks winners" signal, exactly the failure the re-validation was looking for. BUT: it is NOT a slam-dunk — OOS (n=5) still leans the gate's way, and a look-ahead gate's true live contribution is muddier than the backtest. The honest read per OP-22 is REVALIDATE/UNBLOCK-leaning, not a confident KEEP. The gate fails 3 of 5 OP-22 gates (G1 IS, G3 WF, G4 SW) under the current engine; it passed AUTO-RATIFY on the old engine. Recommend UNBLOCK with the REVOKE note, since the standing TARGET STATE is "nothing validated is blocked, nothing unvalidated trades" and this gate no longer clears its own validation bar under the engine it now runs on.
