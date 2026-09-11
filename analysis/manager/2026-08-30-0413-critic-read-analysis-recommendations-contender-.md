<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=11.496s | action=Read analysis/recommendations/contender- -->
<!-- reason: Sweep has 8835 rows and last entry is deeply negative with op16_reject=true; need an adversarial read on whether the ranker itself is the bug before grinding more variants. Critic lane hasn't touched sweep-math this cycle and the last critic actions were all candidate critiques, not the sweep pipeline. -->

**(a) Why expectancy ≠ edge_capture**  
Expectancy is the *average* profit‑per‑trade ( E[PNL] ) and stays positive because the few trades that hit the +150 % TP generate large gains that outweigh the many small –40‑stop losses (WR≈33 %). Edge_capture, however, is usually defined as the *difference* between the realized PNL and the *expected* PNL given the model’s edge (often a per‑unit, risk‑adjusted metric). When a trailing exit is used, the trade frequently closes *before* the TP is hit, turning a potentially large win into a modest profit or even a loss. Those early exits produce large negative residuals (realized PNL << expected PNL) that drive edge_capture deeply negative, while the occasional full‑TP win still lifts the arithmetic mean (expectancy). The asymmetry of a tight –40 stop versus a wide +150 % TP amplifies this effect, and if `qty_frontier` is null the sweep writer may be computing edge_capture on a *unit‑size* basis while expectancy is reported on the actual (scaled) position size, further widening the gap.

**(b) Most likely silent accounting error**  
The sweep writer probably flips the sign when calculating edge_capture: it stores `expected_pnl – actual_pnl` instead of `actual_pnl – expected_pnl`. A trade that actually outperforms its model (large positive residual) would then be recorded as a large negative edge_capture, exactly what we see (‑717.6) while the underlying expectancy remains positive.

**(c) One concrete diagnostic**  
Run a quick sanity‑check that recomputes edge_capture from the raw trade log and compares it to the stored field:

```bash
jq '
  .[] |
  select(.contender=="ITM-2:LR0:mt2:stop-40:tp+150%:sell100%:trailing") |
  {
    edge_capture_stored: .edge_capture,
    expectancy: .expectancy,
    win_rate: .win_rate,
    edge_capture_recomputed:
      ([.trade_log[] | .pnl] | add) -
      ([.trade_log[] | .model_expected_pnl] | add)
  }
' sweep.json
```

*Keys inspected*: `contender`, `edge_capture`, `expectancy`, `win_rate`, `trade_log[]`, each trade’s `pnl` and `model_expected_pnl`. If the stored `edge_capture` has the opposite sign of the recomputed value, the sign‑flipping artifact is confirmed. (≤300 words)