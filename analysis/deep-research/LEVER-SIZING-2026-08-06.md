# LEVER 2 — SIZING AS THE LOSS AMPLIFIER

**Run:** 2026-08-06 after the close · clock verified this session via `python setup/scripts/et_clock.py`
→ `2026-08-06 16:45:22 Thursday EDT`, `market_hours=False`. Analysis-only; no trading-path file touched.

**Verdict: NULL.** Sizing is not the lever that caps a Wednesday. It is provable in one line, and
the proof is a *hard constraint*, not a fitted result.

---

## 0. The one-line proof

Set **every arm to qty 3 — the tightest size Rule 6 permits** — on every trade in the book.
That is the ORACLE lower bound: no sizing policy, conditional or otherwise, can beat it.

| | Live | Rule-6 floor everywhere | Δ |
|---|---:|---:|---:|
| **Wed 2026-08-05** | −$1,935.00 | **−$968.55** | +$966.45 |
| **Tue 2026-08-04** | +$3,624.00 | +$2,658.90 | **−$965.10** |
| **Thu 2026-08-06** | +$1,465.00 | +$827.85 | **−$637.15** |
| 26-day book | +$1,782.01 | +$1,447.01 | −$335.00 |

**Wednesday still loses $969 at the legal floor, and getting there costs $1,602 across Tuesday
and Thursday.** J's target is −$500. Sizing cannot reach it. Everything below is the search for a
*conditional* trigger that buys some of that Wednesday relief without the Tuesday bill — and
nothing found clears both populations.

---

## 1. risky-1 −$140 vs risky-3 −$1,462: the exact decomposition

Both arms took the **identical contracts** on Wednesday — `SPY260805C00776000` five times each and
`SPY260805P00772000` once each, seconds apart. Matched pairwise, decomposed by **exact Shapley over
all 3! orderings** of three levers (qty · entry price · exit price), summing to the gap with
`sum_check = 0.0`.

Options-only: risky-1 −$138.00, risky-3 −$1,458.00, **gap −$1,320.00**.

| Lever | Shapley | % of gap |
|---|---:|---:|
| **Exit price** (TP1 +50% vs +100% → reachability) | **−$1,031.22** | **78.1%** |
| **Contract count** (5 vs 8) | −$314.77 | 23.8% |
| Entry price (execution) | **+$26.00** | −2.0% *(a credit — risky-3 bought better)* |

### The strike tier contributes EXACTLY $0.00

The brief asks how much of the gap is the ATM-vs-OTM tier. The answer is **zero, and it is not a
modelling choice — it is a fact about the ledger.** Both arms have carried
`strike_tier_table="bold_core"` since 2026-08-01 and bought the *same OCC symbols*. There is no
strike difference to attribute. Any decomposition charging the ATM extension for Wednesday's
risky-3 loss is attributing a variable that did not vary.

### The two events are cleanly separable — the "overlap" is an artifact, not a mystery

| Event | Gap | qty | entry | exit |
|---|---:|---:|---:|---:|
| **776C spiral** (5 re-entries) | −$309.00 | **−$294.38 (95.3%)** | $0.00 | −$14.62 (4.7%) |
| **772P** (1 position) | −$1,011.00 | −$20.40 (2.0%) | +$26.00 | **−$1,016.60 (100.6%)** |

The calls are a **pure size story** — neither arm's TP1 was ever live (max MFE 11.5% against a
+50% tightest target), both exited on the same structure stop, so the exit knob did literally
nothing there. The put is a **pure exit-config story**. They do not overlap in the *event*
dimension at all.

### Verifying and correcting the prior audit

The prior figures reproduce **to the cent**: size $546.75, knob $1,237.20. They sum to 135% of the
gap because both are **last-in waterfall marginals measured at the other factor's risky-3 level** —
size priced at TP1 = +100%, knob priced at qty 8. Each is individually correct; the
$463.95 excess is the interaction term and the two **cannot be added**. Shapley resolves it exactly:
**23.8% size / 78.1% exit / −2.0% entry-credit.**

---

## 2. The sizing policies, both populations, real fills

**Method.** A sizing policy is a per-position scalar on realised P&L: it cannot change which
signal fires, what contract is bought, or the fill prices. So its effect is exact **arithmetic on
real broker fills** — strictly more faithful than any replay. Rule 6's min-3 floor binds every cell
(`max(3, round(q/2))`). Sequential per (arm, date); no independent trades recombined.

**Population A** — 208 real-fill positions, 26 ET dates. **Population B** — the 191-trade /
141-traded-day / 387-RTH-day replay whose exits were re-walked through
`exit_manager.plan_exit_actions`. *Correction to my own first assumption: population B is **not**
fixed at qty 3. It runs 3→13 (equity-scaled), with 130 of 191 at the floor — so a shrink policy
bites on the other 61.*

### (b)/(c) Halve after N losing round trips — **REFUTED, twice**

| Cell | Wed | **Tue cost** | Thu | Book Δ | Days harmed |
|---|---:|---:|---:|---:|---:|
| halve after 1, arm-scoped | −$1,252.80 | **−$806.00** | $0 | −$107.00 | 2 |
| halve after 2, arm-scoped | −$1,318.80 | **−$626.00** | $0 | +$7.00 | 2 |
| halve after 3, arm-scoped | −$1,438.80 | **−$742.00** | $0 | −$205.80 | 1 |
| halve after 1, fleet-scoped | −$1,252.80 | **−$1,027.60** | $0 | −$338.20 | 3 |
| halve after 2, fleet-scoped | −$1,252.80 | **−$1,027.60** | $0 | −$532.20 | 3 |
| halve after 3, fleet-scoped | −$1,318.80 | **−$791.60** | $0 | −$214.60 | 2 |

**Every cell fails the hard gate**, costing Tuesday $626–$1,028. The reason is not a tunable
threshold — it is the shape of the day:

> **Tuesday's FIRST closed round trip is a loser: risky-1's 762C, entered 09:46:07, exited
> 09:47:06 for −$75.** Seventy-seven seconds into the best day in the book, the trigger arms. The
> 23 positions entered after it are worth **+$3,803.00**, including the +$788 and +$651 12:28 769C
> legs and the +$640 763C runner. Everything before it is worth −$179.00.

And this is not a Tuesday quirk. The **scale-free selection test** — does the trigger pick losers? —
answers the same way on both populations:

| | Cohort shrunk (≥1 prior closed loss) | Cohort kept (no prior loss) |
|---|---|---|
| **BOOK** | n=138, **+$10.88/trade** | n=70, +$4.01/trade |
| **REPLAY (141 days)** | n=36, **+$50.98/trade** | n=155, +$19.18/trade |

The post-loss cohort is the **more profitable** one — 2.7× per trade over 141 independent days.
Halving it destroys money by construction. Population B agrees in dollars too: halve-after-1
= **−$903.99** (10 days harmed, 13 helped). (Halve-after-2 on the replay is +$134.60 but touches
only **3 trades** — noise, reported so it isn't mistaken for evidence.)

### (a) Flat qty across arms — mechanically the floor result

Book: qty 3 → +$1,447.01 (Tue −$965.10). qty 4 → +$1,929.35 but Wed worsens to −$1,291.40.
qty 6 and 8 make Wednesday *worse* (−$1,937 / −$2,583) while making the book richer. There is no
flat size that is simultaneously good for Wednesday and neutral for Tuesday, because there cannot be.

### (d) Volatility-scaled — **the only trigger that discriminates, and it fails population B**

`qty × clip(median_vol / vol_at_entry)`, where `vol_at_entry` = mean 5-min (high−low)/close % over
the **6 closed bars before entry** (strictly causal, 0 missing on the book).

Wednesday's entries were taken at **2.2× Tuesday's realised volatility** — median entry vol
**0.1647%** (Wed) vs **0.0750%** (Tue) vs 0.0926% (Thu), against a population median of 0.0958%.
That is a real, pre-entry-observable discriminator, and it is the only one this lane found.

| Cell | Wed Δ | Tue Δ | Thu Δ | Book Δ | ex-week Δ | harmed/helped | **REPLAY Δ** |
|---|---:|---:|---:|---:|---:|---:|---:|
| clip [0.5, 1.0] | +$515.35 | **−$170.50** | $0.00 | +$300.25 | −$44.60 | 6/10 | **−$315.00** |
| clip [0.5, 2.0] | +$515.35 | **+$430.50** | −$12.00 | +$494.05 | −$439.80 | 13/9 | **−$46.46** |

On the book it looks like the answer: Wednesday +$515, Tuesday untouched or *improved*. On the
**141-day replay it is negative at every shrink-capable cell** (−$315.00 at [0.5,1.0], 7 days
harmed). It does not survive both populations. **NULL as a sizing lever** — but see the handoff in §5.

### (e) Premium-scaled / constant dollar risk — **the theoretically sound cell, and it is refuted**

`qty = max(3, round(scale × B_arm / (premium × 100)))`, `B_arm` = that arm's own mean entry
notional (budget-neutral, in-sample, disclosed).

Constant dollar risk pays off **only if return-per-dollar-of-notional is flat in premium.** It is
not. It is hump-shaped, and both populations agree on the shape:

| Entry premium | BOOK return-on-notional | REPLAY return-on-notional |
|---|---:|---:|
| $0.00–$0.50 | **+0.42%** (n=98) | −2.06% (n=5) |
| $0.50–$1.00 | +3.96% (n=40) | +3.83% (n=64) |
| $1.00–$1.50 | **+14.00%** (n=49) | +9.72% (n=75) |
| $1.50–$2.00 | −10.12% (n=11) | **+12.91%** (n=28) |
| $2.00+ | −8.93% (n=10) | −7.56% (n=19) |

Constant-dollar sizing forces **more** contracts into the $0–0.50 bucket (+0.42% RON, the flattest
cell in the book, 98 positions) and **fewer** into the $1.00–1.50 sweet spot. That is exactly
backwards, and the dollars say so:

| Budget scale | Book total | Book Δ | Wed | **Tue Δ** |
|---|---:|---:|---:|---:|
| ×0.50 | −$174.59 | −$1,956.60 | −$968.55 | −$965.10 |
| ×0.75 | −$828.59 | −$2,610.60 | −$968.55 | −$970.90 |
| **×1.00 (budget-neutral)** | **−$1,199.08** | **−$2,981.09** | −$968.55 | −$812.60 |
| ×1.25 | −$1,669.46 | −$3,451.47 | −$1,051.55 | −$537.80 |

It turns a +$1,782 book into a −$1,199 book. Wednesday only reaches −$968.55 because Wednesday's
contracts were all expensive ($1.65–$2.35), so every position collapses to the Rule-6 floor — i.e.
it buys nothing the floor didn't already buy, and pays for it everywhere else.
*(The REPLAY shows +$182.89/+$1,506.37 at scales 1.0/1.25 — but 130 of its trades are AT the floor
so the policy can only size **up** there. That is a **leverage** result on a profitable population,
not a risk-control result. Labelled, never netted against the book.)*

**REFUTED.** Note this also condemns risky-3's live `cheap_contract_qty_boost` (qty 10 under
$0.50) on the same evidence: it up-sizes the worst return-on-notional bucket in the book.

---

## 3. (f) Revert risky-3's ATM tier? — **the kill criterion is NO LONGER MET; do not execute**

The 08-04 audit called this "a ~2.2x size increase in a strike-selection costume." **Measured:
median premium ratio ATM/OTM-2 = 2.169×.** The framing is confirmed with a number, which is why
this cell belongs to the sizing lane.

**Revert target is OTM-2, not OTM-3** — risky-3 sits at ~$5.98K, the $2K–$10K bracket.

### The criterion flipped overnight

The prereg kills an arm whose post-arming cohort is net-negative at the sample floor. The
2026-08-06 **03:39 ET** evaluation found n=14 / **−$653 → KILL_CRITERION_MET**. That evaluation ran
**before Thursday's session.**

| Session | risky-3 ATM cohort |
|---|---:|
| 2026-08-04 | +$805.00 |
| 2026-08-05 | −$1,458.00 |
| 2026-08-06 | **+$830.00** |
| **n=15 total** | **+$177.00** |

**The cohort is net-positive on the closed book. The kill criterion is not met and the revert
should not be executed.** (Honest counter-reading: `sub_window_stable` fails hard — three sessions
of violently opposite signs, no session under 50% of the total. The correct state is
**UNDETERMINED / keep measuring**, not KEEP-with-confidence and certainly not REVERT.)

### What the revert would actually have returned — real OPRA, real production exit core

15 positions, each walked twice through `walk_exit_manager → exit_manager.plan_exit_actions` on
real 1-min OPRA: once on the **actual** ATM contract at the **actual fill price** (the parity
control), once on the **OTM-2** contract at **its own real OPRA price in the same minute**, same
qty, same exit shape, same trigger level. All 30 contract-days have full liquid coverage
(371–405 bars, median volume 26–1,965; zero gaps).

| | Tue 08-04 | **Wed 08-05** | Thu 08-06 | Total |
|---|---:|---:|---:|---:|
| ATM, real fills | +$805.00 | −$1,458.00 | +$830.00 | +$177.00 |
| ATM, walked (control) | +$910.52 | −$1,188.96 | +$728.00 | +$449.56 |
| OTM-2, walked | +$869.00 | **−$672.48** | +$418.00 | +$614.52 |
| **walk-vs-walk Δ** | **−$41.52** | **+$516.48** | **−$310.00** | **+$164.96** |

The revert buys **+$516 on Wednesday** and pays **−$310 on Thursday** for it. Net +$165 over three
sessions — inside the harness's own error bar: the parity control is **+$272.56 optimistic**
(worst single position +$195.68, on the 5th spiral leg). Quote the walk-vs-walk delta, never the
+$437.52 that mixes a walked counterfactual against a real fill.

### And the population says the revert target is the worst cell available

An existing coverage-matched **1-minute real-OPRA** study
(`ribbon-ride-strike-exit-ab-1min-coverage-matched-2026-08-02.json`) ran all four strike cells over
the same cohort:

| Strike | n | Expectancy | wf ≥ 0.70 | sub-window stable |
|---|---:|---:|---|---|
| **ATM** (current) | 244 | **+$48.64** | ✅ | ✅ |
| OTM-1 | 249 | +$19.55 | ✅ | ✅ |
| ITM-2 | 231 | +$15.78 | ❌ | ❌ |
| **OTM-2** (revert target) | 250 | **+$1.25** | ❌ | ❌ *(2nd half −$1,614)* |

**Executing the revert would move risky-3 from the best strike cell to the worst**, on the basis of
an n=15 two-session criterion whose entire negative signal is one day — a day whose loss Shapley
attributes **0% to strike tier**.

---

## 4. C31 checked as a prior — and sharpened

`analysis/j-webull/trades-normalized.csv`, 1,079 closed episodes.

| | CLAUDE.md C31 as written | Episode-level truth |
|---|---:|---:|
| 1–2 lots | **+$4,576** | **−$9,448** (n=884) |
| 3+ lots | −$17,461 | −$12,993 (n=195) |

The standing correction holds and must not be re-quoted in its old form: **J was never net
profitable at any size.** What survives is a *shallow* monotone per-contract gradient —
−$8.47/ct (1–2) → −$14.44 (3–5) → −$15.10 (6–10), a 1.8× spread.

**The real signal is 8× steeper and it is not about lot size at all:**

| | n | Total | Per episode |
|---|---:|---:|---:|
| **Scaled-in** | 97 (9.0%) | **−$13,249** (59% of all loss dollars) | **−$136.59** |
| Not scaled-in | 982 (91.0%) | −$9,192 | −$9.36 |

**14.6× worse per episode.** C31's usable content is *adding into a position*, not *how many
contracts you started with* — and Wednesday's 776C spiral (2.35 → 2.27 → 2.19 → 2.12 → 2.09 into a
falling contract) is averaging-down executed by re-entry, invisible to `fb.is_flat_spy_options`
because the arm is genuinely flat between legs. **That is a re-entry-cap problem (CAP-3), not a
sizing problem.** C31 points away from this lane, not into it.

The same warning applies to reading the size gradient in *our* book: qty is set by a dollar risk
cap, so it is mechanically inverse to premium (REPLAY median premium falls 1.35 → 0.40 as qty rises
3 → 13). Premium-stratified control, the one band where both populations have big-qty depth
($0–$1.00): BOOK small ≤5 **+$1.64/ct** vs big ≥6 **−$3.13/ct**; REPLAY **+$8.43** vs **−$6.06**.
Directionally consistent, but n_big = 13 and 17. A hint, not a finding.

---

## 5. Verdict, and what to hand to the other lanes

**NULL for the sizing lever.** Not one cell caps Wednesday near −$500, and every cell that moves
Wednesday materially fails the Tuesday gate, population B, or both. The binding constraint is
structural: at the Rule-6 floor Wednesday is still −$968.55.

Three things worth carrying out of this lane:

1. **Do not execute the ATM revert.** Kill criterion no longer met (+$177 on the closed book), the
   revert target is the worst of four strike cells over 244 real-OPRA trades, and the day that
   triggered it owes 0% of its loss to strike tier. State: **UNDETERMINED, keep measuring.**
2. **`cheap_contract_qty_boost` (risky-3, qty 10 under $0.50) is up-sizing the worst
   return-on-notional bucket in the book** (+0.42% RON, n=98). It was shipped as a trade-to-learn
   A/B with its own kill criterion; this is independent evidence against it.
3. **Entry-time realised volatility separates Tuesday from Wednesday 2.2:1 (0.0750% vs 0.1647%),
   causally, at the moment of entry.** It fails as a *sizing* lever on 141 days. It is a
   **regime/gating** observation, and it belongs to whichever lane owns standdown — especially
   given the pre-registered early regime classifier failed at 20.9% accuracy on 2026-08-02. This is
   a *measurement*, not a forecast. **Shadow it; do not arm it here.**

---

## Verification

`25 / 25` assertions PASS, re-derived from the raw ledger inside the runner.
**RED-PROOFED:** mutating the Shapley averaging denominator (`len(orders)` → `5`) drops the suite to
**18/25 with 7 targeted failures**; restoring the file byte-identical
(`sha256 bca6783909930710`, matched) returns it to **25/25**. Green alone was not accepted as proof.

## Caveats

- **Rescaling a multi-leg exit is exact at the position level, approximate at the leg level.** Real
  TP1 fractions round to whole contracts; a halved position's TP1 leg would round differently.
  Immaterial at these sizes, but it is an assumption.
- **Every "size" cell holds entry and exit prices fixed.** True by construction for a pure size
  change, but a materially smaller order could in principle fill better. Unmeasurable here.
- **The vol-scaled reference is the population's own median** — in-sample calibration on 26 days.
  Disclosed; it is also why the 141-day replay result (which uses its own median) is the one that
  decides the cell.
- **The (f) counterfactual carries a +$272.56 harness optimism bias** measured against real fills on
  the same 15 positions. Only walk-vs-walk deltas are quoted; the absolute OTM-2 total is not
  trustworthy to better than a couple of hundred dollars.
- **The (f) OTM-2 walk passes `ribbon_tick_df` built from the same SPY series as the ATM walk**, so
  ribbon-flip fidelity is identical between arms — but it is a reconstruction, not the live ribbon
  state the engine actually saw.
- **Population B is one arm, one strategy family.** It validates *mechanisms* across 141
  independent days; it cannot express fleet effects and structurally cannot produce a Wednesday.
- **All P&L here is SPY-options-only** (Wed −$1,935.00 / risky-3 −$1,458.00), matching Lane 0.
  The brief's all-in figures (−$1,943.66 / −$1,462.29) include crypto-twin residual. Both correct,
  different scopes.
- **Graveyard check run, no collision.** This is not stop-width, not stopped-then-paid, not pre-TP1
  profit-lock arming, not hold-longer, not take-profit-earlier, not a per-setup time cooldown, not a
  regime standdown. Cells (b)/(c) are the nearest relative to the graveyarded per-setup TIME
  cooldown — and they fail on the same Tuesday mechanism, which is corroboration, not a re-run.
- **The C31 recomputation is episode-level from the normalised file.** It reproduces the standing
  correction independently; it does not re-derive the original per-sell-fill banding that produced
  the retired +$4,576 figure.

## Artifacts

- `analysis/deep-research/LEVER-SIZING-2026-08-06.md` (this file)
- `analysis/deep-research/LEVER-SIZING-2026-08-06.json`
- `analysis/deep-research/LEVER-SIZING-ATM-REVERT-2026-08-06.json`
- `backtest/tools/lever_sizing_2026_08_06.py`
- `backtest/tools/lever_sizing_atm_revert_2026_08_06.py`

## OPEN defect found while running (not fixed here — shared surface)

`backtest/tools/_option_bars_1min_cache.py:48` does `df["timestamp_et"]` unconditionally. Three
files in `backtest/data/highres/` — `SPY260805C00776000`, `SPY260805C00777000`, `SPY260805P00772000`,
all `2026-08-05` — were written by a different producer with a `timestamp` (UTC) column instead.
Any consumer touching an 08-05 contract through the shared cache raises `KeyError: 'timestamp_et'`.
Three known scripts import this helper. Worked around locally in
`lever_sizing_atm_revert_2026_08_06.py::load_1min`; **reported OPEN rather than patched blind in
another lane's surface.**
