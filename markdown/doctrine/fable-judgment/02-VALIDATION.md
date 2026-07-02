# 02 — VALIDATION: how to not fool yourself (or J)

> Task type: "is this strategy/signal/param worth shipping." The failure mode this chapter prevents: a beautiful backtest that is actually multiple-comparisons noise, a regime artifact, or an accounting illusion — armed, bled live, and trust destroyed.

## The commandments (each one has a body buried under it)

### V1 — Real fills are the only P&L authority
BS-sim/synthetic pricing = RANKING evidence only; stamp "ranking-only" on every artifact that uses it. The E2 replay showed +$109K on BS-sim — honest work, correctly labeled, and the ONLY reason it didn't mislead anyone is the label. (C1; the strike-offset sim incident invalidated an entire weekend once.)

### V2 — Pre-register, split, evaluate ONCE, correct for multiplicity
Write DESIGN.md (features/grid/metric/threshold) and COMMIT IT before computing any outcome. Split train/test BEFORE ranking. Rank on train only; take top-K (small) to ONE test evaluation; Benjamini-Hochberg across the K. A burned holdout stays burned — no post-hoc "nonlinear retry" on the same data, ever.
**Worked example (E6, 07-02):** 10 pre-registered structure features; train showed +21.8pp hit-rate separation — looked like a discovery. The untouched 2023 holdout INVERTED it (−17.6pp, p=0.876). Six months earlier this project would have shipped that as a detector. The pre-registration is the only thing that stopped it. This is not optional ceremony.

### V3 — Two nulls, always
(a) Random-entry null with the SAME exit shape and hold distribution — kills "the exit ladder made the money."
(b) **Opposite-direction null on the SAME entries** — the regime detector. When the flipped direction EARNS, your signal is a coin whose era ended.
**Worked example (E2 vs Phase-1-futures):** E2's machine-management replay survived the opposite null (anti-J entries LOST money → the sign was really J's read). The futures port of the same contexts FAILED it (opposite direction earned +$95/tr in 2026 → the 2021-23 context was regime-bound). Same seed, two different fates, and only the nulls could tell them apart.

### V4 — Anchor test before battery
A detector built from a human read must fire on the EXACT case that inspired it, with tight frequency (≤~5 fires/day = signal; more = noise). RRW had to hit J's own 10:30 bar before earning the 18-month battery. If it can't see the founding case, iterate the definition; if it only sees the founding case at spray-level looseness, kill it.

### V5 — The kill ladder: name the nail
Every negative verdict states WHICH nail: DIES_ON_SLIPPAGE (breakeven spread below realistic) / CONCENTRATION (drop-top-3 flips sign) / OOS_SIGN_FLIP (train-only mirage) / NULL_DOMINATED / UNPOWERED (parked, not disproven — n too small to know) / DEAD_KNOB (the variable never mattered). Named nails prevent zombie resurrections and often reveal the live vein: RRW died on premium-bleed WITH a real directional signal → reborn as a veto candidate. A kill with a named nail is a product; "didn't work" is waste.

### V6 — Interrogate the ACCOUNTING before the result
Before believing any aggregate, ask: what is one observation here, and does the grouping smuggle in a bias? The "profitable at 1-2 lots +$4,576" headline survived months because trips were counted per SELL FILL — profit-clips out of big positions credited to the small-size band. Episode-level recount: −$4,420. Same data, opposite conclusion, purely from the unit of account. Also in this family: winner-date-biased samples ("aligned = +$26/tr" pooled only winner days), pooled-vs-3-axis cells (the "midday profit cell" vanished when actually intersected).

### V7 — Aggregate is the tiebreaker, robustness is the test
OP-16: anchor/edge capture and robustness (quarters positive, drop-top-N, both halves, WF ratio, slippage sweep) outrank raw expectancy. The exit-parity A/B (07-02): the incumbent shape had the HIGHEST aggregate OOS (+$86/tr) and still lost the verdict — 22% WR lotto, 47% top-5-day concentration, negative anchor capture. The winner (+$66.8/tr) had 6/6 positive quarters. Prefer the number that survives subtraction.

### V8 — Fresh data is the referee for a real edge
Re-verify on data the original study never saw before arming. A real edge holds or strengthens (bollinger: +9 fresh signals, +$433, OOS above IS). A curve-fit decays. If recency re-checks say RED, capital stays frozen — paper trade-to-learn continues, but no scaling (CONFIRM-BEFORE-CAPITAL).

### V9 — Validate the VALIDATOR
The harness itself can lie: sim ignored strike_offset once; `_params_to_kwargs` silently dropped chandelier keys (every exit A/B modeled a different exit than production traded); masters stored fixed −04:00 year-round (winter sessions clipped). Before a big campaign, run one parity case through harness-vs-production and diff. When a harness bug is found, re-check which past verdicts it touches — don't assume they survive.

### V10 — Sample-size honesty
n<10: say "no information," never "promising." Concentration >50% in top-3 days: the edge is 3 lucky days until proven otherwise. WR without expectancy is noise (65% WR / negative expectancy killed RRW; J's whole book was 59% direction / net-negative). Never let a beautiful sub-cohort with n=13 rewrite a conclusion drawn from n=500.

## The shipping bar (all must hold)
Real-fills basis (V1) · pre-registered + FDR-survivor (V2) · beats both nulls (V3) · nail-free on the kill ladder (V5) · robust per V7 · fresh-data verified (V8) · harness parity known-good (V9) · adequate n (V10) → then it flows: scorecard JSON → proposal with apply_ops → WATCH → exec-arm on paper → ≥20 live trades before any capital talk. Any skipped step is how this project spent months lying to itself.
