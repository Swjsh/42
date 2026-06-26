# Strategy candidate: block_bull_1100_1200 re-validation (Safe) — KEEP

> DRAFT — Chef proposal 2026-06-26. J ratifies (REVOKE only — this recommends NO change).

## Hypothesis
Re-validate the Safe direction-block `block_bull_1100_1200` (gates.py gate #5 — blunt time-veto blocking ALL bull/C entries 11:00–12:00 ET, no quality condition) under the CURRENT engine (real OPRA fills via `simulate_trade_real`, Safe $2K / OTM-2, managed `exit_manager`). The block was ratified 2026-06-18 on the OLD engine (BS-sim era, n=11 IS bull victims). **Directional claim under test:** the new ITM/managed-exit structure may turn the once-losing midday bulls into winners → block would be stale → UNBLOCK. **Result: claim REJECTED. The block still earns its keep. Recommend KEEP.**

## Backtest evidence
- Train window (IS): 2025-01-02 → 2026-05-07
- Test window (OOS): 2026-05-08 → 2026-06-18
- Method: `run_backtest` with FULL production Safe params armed (`params.json` minus `_doc` keys), `use_real_fills=True`, `initial_equity=2000`, `per_trade_risk_cap_pct=0.30`; run with `block_bull_1100_1200` ON (production) vs OFF (unblocked); diff the trade sets → exactly the bull/C trades suppressed in 11:00–12:00 ET, scored under real fills + managed exits.
- **Blocked trades under the current engine (n=5, all CALLs in 11:0x–11:30 ET):**
  | Date | Time | Real-fills P&L | Exit |
  |---|---|---|---|
  | 2025-01-03 | 11:05 | −$273 | EXIT_ALL_PREMIUM_STOP |
  | 2025-02-10 | 11:05 | −$300 | EXIT_ALL_PREMIUM_STOP |
  | 2025-09-26 | 11:30 | −$240 | EXIT_ALL_PREMIUM_STOP |
  | 2025-12-09 | 11:30 | −$210 | EXIT_ALL_PREMIUM_STOP |
  | 2025-12-11 | 11:25 | −$276 | EXIT_ALL_PREMIUM_STOP |
- **edge_capture (block delta):** IS_delta = **+$1,299** (block removes 5 losers, WR=0%). OOS_delta = **$0** (zero OOS victims survive upstream gates under the current engine). total_delta(block) = +$1,299.
- aggregate effect of UNBLOCKING the whole engine (real fills): **−$1,014** (some downstream first-entry/quality-lock interactions shift, so it's not the full −$1,299, but directionally the block clearly helps).
- J-edge anchor (bear source-of-truth): **byte-identical** between runs — bear trade set n=38, $2,464 in BOTH runs. Bull-only gate never touches the 4/29, 5/01, 5/04 winners or the 5/05–5/07 losers.
- real_fills_validated: **yes** (real OPRA bars, `simulate_trade_real`, the C1 WR authority).

## OP-22 honest scoring
- **G1 IS_delta ≥ 0:** PASS (+$1,299; 5/5 surviving midday bulls are −50%-premium-stop losers).
- **G2 OOS_delta > 0:** SOFT — $0, not negative. Under the current engine NO bull setup survives upstream gates into the 11–12 window in the OOS period (incl. the original scorecard's single OOS victim 2026-05-20, now suppressed upstream — verified NOT a data gap; OPRA bars for 05-20 exist). So there is no fresh OOS confirmation, but also no OOS evidence against.
- **Anchor no-regression:** PASS (bear set identical).
- **Aggregate:** PASS (blocking helps ~+$1,014 real-fills).
- **The "new exit structure rescues these bulls" hypothesis:** empirically FALSE — every surviving midday bull still hits the −50% premium stop under OTM-2 + managed exits.

## Disclosures (per OP-20)
1. **Account-size assumption:** Safe-2, $2,000 equity, OTM-2 (strike_offset −2 per v15 tier table), per_trade_risk_cap 0.30. This is the exact account the block lives on.
2. **Sample-bias disclosure:** IS-dominant (5 victims, all IS). The old-engine n=11 shrank to n=5 because upstream gates (`block_level_rejection`, `block_elite_bull` VIX[0,25), doji gates) now suppress the other 6 before this gate sees them. OOS sample for this gate is empty under the current engine.
3. **Out-of-sample test result:** OOS_delta = $0 (no victims). Not a confirmation; not a contradiction.
4. **Real-fills check:** YES — all P&L is real OPRA fills via `simulate_trade_real`, not BS-sim. The original scorecard's −$89 IS figure was the old engine; under real fills the surviving subset is −$1,299.
5. **Failure-mode enumeration:** (a) The block is blunt (no quality condition) — a future genuinely high-conviction 11:XX bull SUPER would also be blocked; under the current engine NONE has appeared and all 5 surviving signals are −50% stop-outs, so this risk is theoretical. (b) If J ever promotes a bull-specific edge that fires midday (e.g. a vwap_continuation CALL in 11–12), this gate would suppress it — at that point re-validate as a setup-scoped (not time-scoped) exception, not a blanket removal.
6. **Concentration:** top5_pct = 100% (only 5 blocked trades; all 5 are the sample). N too small for a concentration metric to be meaningful — the signal is "5/5 losers," not a P&L-weighted distribution.

## Knob changes proposed
**NONE.** Recommend KEEP `block_bull_1100_1200: true` in `automation/state/params.json`. (Never edited by Chef.)
- Param diff to UNBLOCK (documented for completeness, NOT recommended): `block_bull_1100_1200: true → false`.

## Pre-merge gate
`python crypto/validators/runner.py`: **97/98 PASS, overall_pass=True** (1 known-flaky excluded) — both before AND after this work (read-only A/B; no engine/params change). No change recommended, so the gate state is moot for ratification.

## My confidence (1–10) and why
**8.** The IS evidence is clean and unambiguous: 5/5 surviving midday bulls are real-fills −50%-stop losers, anchor is provably untouched, and the "managed exits rescue them" hypothesis is directly falsified. The −1 from a perfect score is the empty OOS sample (G2 soft = $0, no fresh OOS confirmation) and the small n (5). But the asymmetry is decisive: unblocking adds zero winners and ~−$1,014; there is no evidence-based case to UNBLOCK. KEEP.
