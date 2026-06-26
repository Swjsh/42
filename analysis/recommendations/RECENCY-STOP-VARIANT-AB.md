# RECENCY STOP-VARIANT A/B — edge #1 `vwap_continuation`

> **VERDICT: `-8%_REMAINS_OPTIMAL`** — run 2026-06-21, frame `2025-01-02..2026-06-18`, recent window `2026-05-14..2026-06-18` (25 trading days), OPRA cache last `2026-06-18`.

SAFE research, $0, NOT live path. Real OPRA fills (C1); detector + sim + risk-machinery REUSED byte-for-byte (`_edgehunt_vwap_continuation.detect_signals` = the LIVE detector; `lib.simulator_real.simulate_trade_real`; `_b10_exit_variance` L175 metrics; `null_baseline` C3/L58). Per-trade EXPECTANCY, not WR (OP-14). RESEARCH ONLY — no watcher/params/risk_gate/orchestrator/heartbeat edit, no orders, no commit.

## Question

Is there a STOP variant for edge #1 that REDUCES the recency drawdown WITHOUT breaking the full-sample edge — holds/beats `-8%` expectancy, passes no-truncation + the L175 risk-adjusted bar, AND lifts the recent ~25-day window out of RED?

## Answer: NO. The `-8%` stop dominates every variant on every dimension at once.

The recency-RED diagnosis correctly flagged that edge #1 **passes** the no-truncation gate (chart-stop-only stays positive full-sample → the edge does not *depend* on the tight stop inverting losers' sign). That made a looser stop a legitimate candidate to A/B — which is exactly what this run does. **The A/B result is that the no-truncation pass was NECESSARY but not SUFFICIENT: the edge survives a looser stop, but `-8%` is simultaneously the variance/Sortino-optimal AND the recency-optimal stop.** Every looser variant makes BOTH the full sample AND the recent window strictly worse, monotonically. No variant clears the WIN bar on either tier.

## Full vs recent, per variant (real OPRA fills)

`noTrunc` = full-sample exp > 0. `null` = random-entry null_pass (C3/L58). `L175` = per-trade Sharpe holds AND book Sortino holds AND book maxDD no material-worse (+25% thresh) vs the `-8%` baseline at the SAME tier.

### Tier ATM (strike_offset +0 — live Safe-2). Baseline `-8%`: full n=157, exp **+$45.01**, Sharpe/tr 0.388, Sortino 18.86, maxDD −$454.56.

| variant | FULL exp/tr | FULL Sharpe/tr | FULL maxDD | FULL Sortino | RECENT n | RECENT exp/tr | RECENT total | noTrunc | null | L175 | WIN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **(a) −8% [BASELINE]** | **+$45.01** | **0.388** | **−$455** | **18.86** | 10 | **−$22.46** | **−$224.64** | ✓ | ✓ | — | — |
| (b) chart-stop-only −0.99 | +$35.01 | 0.156 | −$2,686 | 3.19 | 10 | −$191.94 | −$1,919.40 | ✓ | ✓ | ✗ | — |
| (c) premium −15% | +$38.33 | 0.283 | −$913 | 9.25 | 10 | −$52.83 | −$528.30 | ✓ | ✓ | ✗ | — |
| (c) premium −20% | +$29.63 | 0.200 | −$1,450 | 5.48 | 10 | −$74.52 | −$745.20 | ✓ | ✓ | ✗ | — |
| (c) premium −25% | +$29.93 | 0.184 | −$1,396 | 4.61 | 10 | −$96.21 | −$962.10 | ✓ | ✓ | ✗ | — |
| (d) chart-stop + −50% cap | +$32.87 | 0.163 | −$2,042 | 3.55 | 10 | −$143.49 | −$1,434.90 | ✓ | ✓ | ✗ | — |
| (e) −20% premium + tighter TP1 +20% | +$22.59 | 0.163 | −$1,402 | 4.27 | 10 | −$78.60 | −$786.00 | ✓ | ✓ | ✗ | — |

### Tier ITM-2 (strike_offset −2 — live Bold). Baseline `-8%`: full n=158, exp **+$69.53**, Sharpe/tr 0.406, Sortino 19.78, maxDD −$1,013.04.

| variant | FULL exp/tr | FULL Sharpe/tr | FULL maxDD | FULL Sortino | RECENT n | RECENT exp/tr | RECENT total | noTrunc | null | L175 | WIN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **(a) −8% [BASELINE]** | **+$69.53** | **0.406** | **−$1,013** | **19.78** | 11 | **−$75.27** | **−$828.00** | ✓ | ✓ | — | — |
| (b) chart-stop-only −0.99 | +$61.35 | 0.194 | −$3,848 | 4.05 | 11 | −$244.69 | −$2,691.60 | ✓ | ✓ | ✗ | — |
| (c) premium −15% | +$57.58 | 0.287 | −$1,899 | 9.35 | 11 | −$141.14 | −$1,552.50 | ✓ | ✓ | ✗ | — |
| (c) premium −20% | +$51.06 | 0.232 | −$2,533 | 6.45 | 11 | −$188.18 | −$2,070.00 | ✓ | ✓ | ✗ | — |
| (c) premium −25% | +$45.36 | 0.189 | −$3,232 | 4.77 | 11 | −$230.32 | −$2,533.50 | ✓ | ✓ | ✗ | — |
| (d) chart-stop + −50% cap | +$61.30 | 0.209 | −$3,463 | 4.61 | 11 | −$220.96 | −$2,430.60 | ✓ | ✓ | ✗ | — |
| (e) −20% premium + tighter TP1 +20% | +$44.56 | 0.224 | −$2,110 | 5.90 | 11 | −$160.18 | −$1,762.00 | ✓ | ✓ | ✗ | — |

**Every cell:** no-truncation ✓ (full exp stays positive — confirms the diagnosis) and null_pass ✓ (a real signal, not an exit-structure artifact). But **L175 fails for every non-baseline variant on both tiers**, and **every variant's recent window is MORE negative than the `-8%` baseline** — none reduces the bleed; all deepen it.

## The mechanism — why looser stops make recency WORSE, not better (exit-mix)

The recency-RED diagnosis named the loss fingerprint: 9/10 ATM + 11/11 ITM-2 recent losers exited on `EXIT_ALL_PREMIUM_STOP`. The intuition was "the −8% stop is firing, so a looser stop would stop firing and bleed less." The exit-mix proves the opposite — the `-8%` stop was **truncating** those losers; removing/widening it lets them ride to a LATER, DEEPER exit:

- **Baseline `-8%` (ATM recent):** `{PREMIUM_STOP: 9, TP1_THEN_RUNNER_RIBBON: 1}` → recent total **−$224.64**.
- **Chart-stop-only `-0.99` (ATM recent):** `{RIBBON_FLIP_BACK: 5, TIME_STOP: 2, LEVEL_STOP: 1, TP1_THEN_RUNNER_RIBBON: 2}` → the premium stop is gone, the losers now exit via ribbon-flip / time / level — far later and deeper → recent total **−$1,919.40** (8.5× worse). maxDD blows out from −$455 to −$2,686.
- **Wider premium `-15/-20/-25%` (ATM recent):** exit-mix is UNCHANGED (`{PREMIUM_STOP: 9, ...}`) — the same losers still hit the (now-deeper) premium stop, just at a worse level → recent −$53 / −$75 / −$96. Monotonic.
- **Catastrophe cap `-50%` (ATM recent):** partially reverts to chart exits (`{PREMIUM_STOP: 5, RIBBON_FLIP_BACK: 2, TIME: 1, ...}`) → recent −$143. Between (b) and (c), still much worse than baseline.

ITM-2 shows the identical pattern (baseline `{PREMIUM_STOP: 11}`, −$828; chart-stop-only −$2,692). **The tight `-8%` premium stop IS edge #1's risk management — it caps the left tail exactly when the day goes against the morning VWAP-continuation read. Loosening it converts truncated −8% losers into ribbon/time-exit losers that bleed full premium.** Textbook C2/C28/C3: on 0DTE first-strike entries the premium stop is doing real work, and wider stops bleed full premium.

## Why this is consistent with the no-truncation gate passing

No-truncation asks: *does the edge's sign survive without the tight stop truncating losers?* It does (chart-stop-only full exp = +$35 ATM / +$61 ITM-2, still positive). That correctly rules out the "exit-structure artifact" failure mode and made the looser-stop A/B worth running. But "the edge survives a looser stop" ≠ "a looser stop is better." Here the `-8%` stop is the **variance-optimal** point: it has the highest full-sample per-trade Sharpe (0.388 / 0.406), the highest book Sortino (18.9 / 19.8 vs single-digit for every looser variant), the shallowest maxDD, AND the least-negative recent window. There is no looser stop that trades a bit of mean for less recency pain — looser stops give up mean AND deepen recency drawdown together.

## Verdict

**`-8%_REMAINS_OPTIMAL`.** The `-8%` premium stop is the right stop for edge #1 on both tiers. The recency RED is a genuine ~2.2–2.4σ tail in a stationary-mean edge (per RECENCY-RED-DIAGNOSIS.md) — a **regime to wait out**, NOT a stop-tuning problem. There is no stop variant that reduces the recency bleed without breaking the full-sample edge; every variant breaks it (L175 fail) AND deepens the bleed.

**Action: HOLD capital scaling on edge #1 until `recency_check.py` flips it to CONFIRM** (recent exp/tr > 0, n ≥ floor). Do NOT widen the live stop. The confirm-before-capital gate is working correctly.

This run also tightens doctrine: a no-truncation PASS licenses a looser-stop *experiment*, but the tight stop can still be variance-optimal — the L175 risk-adjusted bar is the deciding gate, and it rejected all 12 looser-stop cells here. (Sibling read to L175: a per-trade-mean view alone would have ranked chart-stop-only +$35/+$61 as "still positive"; the Sharpe/Sortino/maxDD view exposes it as a 8×-deeper-drawdown trade.)

---

Files: `analysis/recommendations/RECENCY-STOP-VARIANT-AB.json` (machine), `backtest/autoresearch/_recency_stop_variant_ab.py` (this harness). Inputs reused: `_edgehunt_vwap_continuation.py`, `recency_check.py`, `lib/simulator_real.py`, `_b10_exit_variance.py`, `null_baseline.py`.
