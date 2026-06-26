# Strategy candidate: vix_bear_hard_cap (Safe) — re-validation under CURRENT engine

> DRAFT — Chef proposal 2026-06-26T11:35 ET. J ratifies.
> Verdict: **KEEP** (block still earns its keep under the current ITM/OTM-2 + managed-exit engine).

## Hypothesis
The Safe `vix_bear_hard_cap` gate (gate #15, blocks BEAR/P entries when VIX ≥ 23.0) was ratified
2026-06-18 on the **OLD engine** (static OTM-2 strikes + a TIGHT −10% bear premium stop). Its stated
mechanism: high-fear VIX inflates put IV → the −10% premium stop fires on tiny adverse moves (C3/L149).
The current engine demoted premium stops to **−50% catastrophe caps** (chart-stop-primary) and added the
**chandelier trailing profit-lock** (mode=trailing, thr 0.05, trail 0.125). A wider stop + managed exits
**could** now let high-VIX bears survive long enough to win — which would mean the cap is stale and
suppresses winners. Directional claim tested: **does blocking still beat not-blocking on REAL fills under
the current exit structure?**

## Backtest evidence
- **Engine:** `backtest/lib/orchestrator.run_backtest`, `use_real_fills=True` (real OPRA cache), params_overrides path,
  `initial_equity=2000` → per-tier strike = **OTM-2**, premium caps **−0.50** both sides, chandelier trailing **0.125**,
  tp1 0.50@0.667, runner 2.5×, full Safe gate battery. (NOT the old static-OTM-2 + −10% bear-stop profile.)
- **A/B:** `vix_bear_hard_cap=23.0` (blocked) vs `None` (unblocked); identical opportunity set otherwise.
- **Train (IS) 2025-01-02 … 2026-02-27:** removed 8 trades, removed P&L **−$112.11** (−$14.01/trade). Block delta bear P&L **+$112.11**. Bear WR 0.214 vs 0.194. All-sharpe 0.043 vs 0.019.
- **Test (OOS) 2026-03-02 … 2026-06-16:** removed 3 trades, removed P&L **−$32.80** (−$10.93/trade). Block delta bear P&L **+$32.80**. All-sharpe 0.033 vs 0.019.
- **FULL 2025-01-02 … 2026-06-16:** removed 11 trades, removed P&L **−$144.92** (−$13.17/trade). Block delta bear P&L **+$144.91**. Bear WR 0.25 vs 0.236, bear sharpe 0.19 vs 0.145. All-strategy P&L $307 vs $162; all-sharpe **0.040 vs 0.019**.
- **edge_capture / final_score:** N/A — this is a single-gate keep/remove A/B, not a full-strategy candidate. The OP-16 anchor check is run directly below (no edge_capture regression because no anchor trade is touched).
- **positive sub-windows:** removed-trade P&L is negative in **3/3 windows** (IS, OOS, FULL) — the blocked trades are net losers everywhere, not a single-regime artifact.
- **max_drawdown:** not the binding metric here; both arms identical except for the 11 removed losers (removing losers cannot worsen DD).
- **real_fills_validated:** **yes** (simulate_trade_real via run_backtest --real-fills path, the only WR authority per C1).

## Disclosures (per OP-20)
1. **Account-size assumption:** Safe-2 at **$2,000** equity → per-tier strike = OTM-2 (the live tier). Result is tier-specific (C29); not asserted for ITM tiers / Bold.
2. **Sample-bias disclosure:** small n on the *blocked* set (11 trades full history; 3 OOS). The sign is consistent across IS+OOS+FULL but the magnitude is modest (~$13/trade). This is a small, stable edge, not a large one.
3. **Out-of-sample test:** OOS removed-trades = −$32.80 over 3 trades (−$10.93/trade), block delta **+$32.80**. OOS sign matches IS. PASS.
4. **Real-fills check:** done — full real-OPRA fills, current managed-exit structure, both arms.
5. **Failure-mode enumeration:** (a) only 11 lifetime trades clear VIX≥23 + the Safe bear gate battery — thin; a regime with more high-VIX bear days could shift it. (b) Magnitude is small; if J wants maximum trade count under the "validation is the only scope" target, the cost of KEEPing is ~−$145 of *avoided losses* (i.e. KEEP is the profitable choice). (c) the cap is a one-sided VIX-level gate; it does not adapt to VIX *character* (C5) — a calm-but-high VIX day is treated same as a spiking one.
6. **Concentration:** removed-trade losses are spread across 11 trades in 3 windows (not one outlier); no single trade dominates the −$145.

## Anchor-no-regression (OP-16)
- The 3 bear source-of-truth winners (4/29 710P, 5/01 721P, 5/04 721P) all occurred on days with **VIX < 23** → the cap removes **none** of them. Confirmed: blocked vs unblocked anchor-day bear P&L identical (0 anchor bear trades fire in this Safe gate-path config in either arm; delta = 0). **No regression. PASS.**

## Verdict & recommendation: KEEP
Under the CURRENT engine the block STILL produces a positive delta in every window — the high-VIX bears it
removes are **net losers even with the −50% wide cap + chandelier managed exits** (per-trade −$10.93 to −$14.01).
The new exit structure did NOT flip them into winners. This is the rare bear-direction block whose original
mechanism survives the chart-stop-primary migration: at VIX≥23 the issue is not just stop-misfire (which the
wide cap would have fixed) but that the underlying high-fear bear setups simply don't pay at this strike tier.
Removing the cap would add 11 losing trades for −$145 and HALVE the aggregate Sharpe (0.040 → 0.019).

**OP-22 honesty check:** I am NOT recommending UNBLOCK merely to "trade more." The evidence says the block
still helps. Recommending KEEP.

## Knob changes proposed
**None.** `vix_bear_hard_cap` stays **23.0** in `automation/state/params.json`. (NEVER edited by Chef.)
> If UNBLOCK had been warranted, the diff would have been: `"vix_bear_hard_cap": 23.0 → null`. It is NOT warranted.

## Pre-merge gate
No production code touched (throwaway harness `backtest/_chef_vix_bear_cap_revalidate.py` + result JSON only;
no params.json / gates.py / filters.py change). Gym state unchanged. `python crypto/validators/runner.py`
expected 30/30 PASS (no edit could have broken it — zero production diff).

## My confidence (1-10) and why
**8.** Evidence is clean and directionally unanimous across IS/OOS/FULL on real fills under the exact current
engine profile; anchor untouched. Docked 2 points only for thin n (11 lifetime blocked trades) — the *sign*
is robust but the *magnitude* is small enough that a high-VIX-heavy future regime warrants a periodic recheck.
