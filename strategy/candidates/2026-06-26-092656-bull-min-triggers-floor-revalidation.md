# Strategy candidate: KEEP bull_min_triggers floor (re-validated on current engine)

> DRAFT — Chef proposal 2026-06-26 09:26:56 ET. J ratifies. Verdict: **KEEP** (block still earns its keep).

## Hypothesis
Block under re-validation: **bull side requires >=2 filter-10 triggers; bear requires >=1.**
Claim to test (per J-directed 2026-06-26 target state): most bull-blocks were ratified on the
OLD engine (OTM strikes + BS-sim + premium-stops). Under the CURRENT engine (REAL OPRA fills +
managed exits: partial TP1 + runner + trailing profit-lock + -50% catastrophe cap), a gate that
correctly blocked a losing OTM bull config may now be suppressing a WINNER. Directional claim to
falsify: unblocking (bull=1, bear-symmetric) produces a positive or neutral delta.

**Result: FALSIFIED. The block still produces a large positive delta. KEEP.**

## Mechanism correction (important — the inventory was partly wrong)
The block's premise stated the floor is `max(2, min_triggers)` at `orchestrator.py:767`, "not a
params knob — a Python max()." That is only **half true**:
- Line 767 is `bull_min_triggers = min_triggers_bull if min_triggers_bull is not None else max(2, min_triggers)`.
- Production **explicitly sets** `filter_10_min_triggers_bull` (Safe=2, Bold=1), which flows through
  orchestrator lines 354-355 / 709 into `min_triggers_bull`. So the ternary **takes the left branch**
  and the `max(2, ...)` floor **never executes in production**. It is a dormant fallback for callers
  who pass neither key.
- The bull suppressor production actually experiences IS the **params value** `filter_10_min_triggers_bull=2`
  on Safe (vs bear=1). It **is** a params knob. Bold already runs bull at 1 (fully symmetric) — so this
  asymmetry is **Safe-only**, not "both accounts."

The A/B therefore tests the real binding lever: Safe bull=2 (BLOCKED) vs bull=1 (UNBLOCKED).

## Backtest evidence
Engine: `run_backtest(use_real_fills=True)` + managed exits (premium_stop -0.50 both sides, tp1 0.50 @
0.667 qty, runner 2.5x, trailing profit-lock thr 0.05 / trail 0.15) + strike_offset=2 (OTM-2, Safe tier)
+ all production gates (block_level_rejection, block_elite_bull, entry_bar_body 0.20, vix_bear_hard_cap 23).
Data: `spy_5m_2025-01-01_2026-06-18.csv`. IS 2025-01-02..2026-05-07, OOS 2026-05-08..2026-06-18.

| Metric | BLOCKED (bull=2, prod) | UNBLOCKED (bull=1) | Delta (unblock − block) |
|---|---|---|---|
| ALL n | 128 | 199 | +71 |
| ALL total | **+$3,518** | **−$233** | **−$3,751** |
| ALL sharpe | **0.140** | −0.006 | −0.146 |
| ALL WR | 45.3% | 42.2% | −3.1pp |
| BULLS n | 57 | 128 | +71 |
| BULLS total | +$1,301 | −$2,450 | **−$3,751** |
| BEARS total | +$2,217 | +$2,217 | **+$0 (identical)** |
| IS total | +$3,512 | −$196 | −$3,708 |
| OOS total | +$6 | −$37 | −$43 |

**The marginal trades the block suppresses are homogeneous bleeders:** all 71-72 extra trades are
**single-trigger `level_reclaim`-only** bull entries → **−$3,421 total, avg −$47.5/trade, WR 37.5%,
sharpe −0.303**. Not one is a winner the new ITM/managed structure rescues. This is a textbook
single-trigger reclaim with no confluence/sequence/ribbon backing (L102 / C20).

- edge_capture (OP-16): not the operative metric here — see anchor-no-regression below. The block
  touches ONLY bull trades; all J source-of-truth anchors are bearish (puts), so the bear leg is
  byte-identical between arms.
- aggregate sharpe: 0.140 (blocked) — unblocking destroys it (−0.006).
- final_score: edge_capture is governed by the bear leg (unchanged); the bull block's contribution is
  +$3,751 aggregate / +0.146 sharpe preserved.
- positive_quarters: not re-stratified (the verdict is KEEP/no-change; full 6-window stratification is
  only required for a SHIP). IS and OOS both favor the block (signs agree).
- real_fills_validated: **yes** (`use_real_fills=True`, C1 authority).

## Anchor-no-regression (OP-16) — PASS
BEARS total is **identical** (+$2,217) in both arms; the bull-trigger floor has zero effect on any
bearish trade. The J source-of-truth winners (4/29, 5/01, 5/04) and losers (5/05, 5/06, 5/07) are all
puts → completely untouched. Unblocking would NOT regress the bearish edge; it would only add losing
bull trades. Confirmed: no anchor regression in either direction.

## Disclosures (per OP-20)
1. **Account-size assumption:** initial_equity=$2,000, strike_offset=2 (OTM-2) = the live Safe-2 tier.
   Bold (bull=1 already) is out of scope — this asymmetry is Safe-only.
2. **Sample-bias:** the J anchor window (4/29–5/07) sits in IS; the marginal-bull bleed is broad-based
   (72 trades across full 17-month history), not anchor-clustered. OOS sign agrees with IS.
3. **Out-of-sample:** OOS (2026-05-08..06-18) unblocked = −$37 vs blocked +$6; bull leg −$2,450 vs +$1,301
   spans IS+OOS. Sign-stable: blocking wins in both windows.
4. **Real-fills check:** entire A/B run on `simulate_trade_real` via `use_real_fills=True`. No BS-sim.
5. **Failure-mode enumeration:** (a) the inventory mis-described the lever as a non-params `max()` —
   corrected: it is `filter_10_min_triggers_bull` (a params knob), Safe-only; (b) edge_capture is
   bull-insensitive here, so the bear-anchor floor is not the discriminator — aggregate bull P&L is;
   (c) regime risk: the marginal bleed is single-trigger level_reclaim, a known L102/C20 anti-pattern,
   so the result is structural, not a 2025-regime artifact.
6. **Concentration:** the −$3,421 marginal loss is spread over 72 trades (avg −$47.5, no single trade
   dominates); top5_pct not separately computed but the per-trade homogeneity (all one combo,
   tight avg) rules out concentration distortion.

## Knob changes proposed
**NONE. KEEP `filter_10_min_triggers_bull: 2` on Safe (`automation/state/params.json`).**
The exact diff that WOULD unblock — and which the evidence says NOT to apply — is:
`automation/state/params.json` `"filter_10_min_triggers_bull": 2 -> 1`. Do not apply.
(Bold's `filter_10_min_triggers_bull: 1` is already symmetric and is unaffected.)

The dormant `max(2, min_triggers)` fallback at `orchestrator.py:767` is cosmetic (never reached in
production). It could be normalized to `min_triggers` for code clarity, but that is a no-op refactor,
not a strategy change, and is out of scope for ratification.

## Pre-merge gate
`python crypto/validators/runner.py`: **passed=97/98 overall_pass=True** (1 known-flaky excluded). No
code changed (read-only A/B; temp scripts deleted) — gate is green before and after.

## My confidence (1-10) and why
**9.** The block suppresses a single, homogeneous, broad-based loser cohort (72 single-trigger
level_reclaim bulls, −$47.5/trade, WR 37.5%) under the CURRENT real-fills + managed-exit engine — the
exact "did the new structure turn these into winners?" question answered NO. Bears are byte-identical,
so anchor-no-regression is trivially satisfied. The −1 is only because the underlying bull setup
(BULLISH_RECLAIM) is itself DRAFT/unproven (OP-16 setup-scope lock), so "bull at 2 triggers" is
admitting a weak setup at a higher bar rather than a proven setup — but that is an argument for keeping
the floor (or stricter), never for lowering it.
