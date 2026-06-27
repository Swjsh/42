<!-- Sonnet overseer 2026-06-26 20:03 ET -->
- **STOP** calling `rank_contenders` — you have run it three consecutive cycles (1813, 1833, 1853) and the output is byte-identical each time. The top survivor is known: `OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:fixed` (edge=1692, WF=1.98). Do not call `rank_contenders` again until the backtest data changes.

- **STOP** accepting chef outputs that misread the config (the 1753 draft described LR0 as "implying a short strategy" — that is wrong; LR0 is a long-ratio knob). Reject and re-prompt when the output contradicts the actual parameter definitions.

- **Action 1 — Adversarial critique:** Prompt critic: "The top contender `OTM-2:LR0:mt1:stop-8:tp+150%:sell80%` has WR=12.15%. At 0DTE OTM-2, does tp+150% ever realize before expiry worthless? Estimate how many of the 1880 survivors share this TP target and whether the edge is a stop-asymmetry artifact, not a true signal. Answer ≤200 words, structured."

- **Action 2 — Sub-window stability check:** Run or prompt chef to check whether the top-2 contenders (edge=1692 and edge=1563) hold positive OOS expectancy across each of the 4 calendar quarters in the backtest data. Report pass/fail per quarter.

- **Action 3 — Ideate one variant:** Chef proposes ONE `vwap_continuation` variant that adds an RVOL floor (e.g. rvol ≥ 1.2 at entry bar) to the existing live edge. State the hypothesis, expected filter rate, and what metric to check — no backtest needed yet.

- **Action 4 — Forage:** Pull one free FRED series not yet in the system (e.g. `T10YIE` breakeven inflation) and write one sentence on whether it correlates with SPY 0DTE realized vol direction.

- **Rule:** Every output ≤400 words, structured headers, no filler prose. If a free-model response exceeds 400 words or misreads a parameter, log `REJECTED: token-salad` and re-dispatch with a tighter prompt — do not accept and move on.
