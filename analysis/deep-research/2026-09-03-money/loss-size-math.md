# H8 — LOSS-SIZE MATH: is the -50%-of-premium catastrophe cap the right loss unit?

**Stamp:** 2026-09-03T10:24 ET · **Slug:** `loss-size-math` · **Author:** Sonnet subagent, read-only pass
**Data:** cached only, no broker/market-data calls made or needed.
**Companion JSON:** [`loss-size-math.json`](loss-size-math.json)
**Script:** `backtest/tools/money_loss_size_math.py` (rerun any time; deterministic, seed=20260903)

---

## Verdict: REFUTED — tightening the catastrophe cap is net negative at every level tested, and reproduces the prior settlement

A tighter premium/catastrophe cap (-30%, -35%, or -40% vs the current -50%) loses money book-wide,
loses money in every VIX regime cell that has meaningful n, and kills winners on **3 of the 4**
named big winning days. The effect is **monotonic**: the tighter the cap, the worse the net
dollar effect. **No live rule change is recommended.**

| Candidate cap | n winners killed | $ killed | n losses saved | $ saved | n false-stop-worsened | $ worsened | **Net $** | **95% CI** |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| -30% | 11 | -$6,202.70 | 50 | +$1,767.10 | 22 | -$670.00 | **-$5,105.60** | [-$9,579, -$1,272] |
| -35% | 8 | -$5,230.95 | 40 | +$1,174.25 | 19 | -$633.40 | **-$4,690.10** | [-$9,034, -$1,174] |
| -40% | 4 | -$2,650.20 | 31 | +$777.80 | 15 | -$697.60 | **-$2,570.00** | [-$6,041, -$17] |
| -50% (current, sanity check) | 0 | $0 | 12 | +$282.00 | 15 | -$762.00 | **-$480.00** | [-$1,144, +$151] |

All rows: full 394-position population, `mae_before_first_exit==True` only (n eligible per row printed
in the JSON; excludes the small post-partial-exit hypothetical-MAE cohort per the pain-ledger prereg).
Even at -40% the 95% CI barely excludes zero on the loss side; at -30%/-35% it is unambiguous.

This **confirms and extends** the prior settled hypothesis
(`automation/state/hypotheses-settled.json`, `mechanism: stop_inside_noise_floor`,
settled 2026-08-06, `verdict: REGIME_CONDITIONAL_NOT_SHIPPABLE`,
`graveyard_refs: ["hold-longer book-wide (-$451.50 / 21)", "any stop-width change in EITHER direction"]`).
That settlement covered data through 08-04/08-05. This report re-runs the same class of question on
the **current -50% cap era's population** (n=239, 2026-06-26 through 2026-09-02) and gets the same
answer: don't touch stop width in either direction.

---

## 1. Data & population

| Source | Role |
|---|---|
| `analysis/pain-ledger/mae-mfe.json` | n=394 scored positions (real OPRA 1-min bars, broker-truth P&L), frozen methodology per `PREREG-2026-08-01.md` |
| `automation/state/core-decisions.jsonl` | VIX ticks, `account=='safe'`, joined to trades by `date_et` → median VIX that day |
| `automation/state/hypotheses-settled.json` | prior settlement citation (not re-derived, cited) |

- n_scored = 394 (100 winners / 279 losers / 15 scratch), per the frozen ledger's own population count.
- VIX join: 0 trading dates missing a VIX row — full regime coverage.
- **Two cap cohorts exist in the ledger, by arm/date, from per-arm `exit_patch` configs, not from a
  single global knob:**
  - **Current cap cohort** (`premium_stop_pct == -0.5`): n=239, spans 2026-06-26 → 2026-09-02, all of
    safe-2 (88) + bold-2 (42) + parts of risky-1/risky-3/safe-3 = the CLAUDE.md-documented v15.3
    "-50% catastrophe cap both sides" policy. **This is the primary/policy-relevant cohort.**
  - **Legacy cohort** (n=155): -20% (n=111, 2026-06-29→08-28, older fleet-arm configs), -6% (n=41,
    08-04→08-12), -8% (n=3, 08-17 only) — earlier or parallel per-arm exit-patch experiments,
    **not** representative of the current live policy. Reported for context only; excluded from the
    headline verdict.

---

## 2. Break-even WR vs observed WR

R-multiple defined per-trade as `realized_pnl / (notional × |configured_cap_pct|)` — i.e. 1R = the
dollar amount at risk if the position had run the full configured catastrophe stop. Break-even WR =
`|avg_loss$| / (avg_win$ + |avg_loss$|)`.

| Cohort | n | WR observed | WR CI (95%) | Breakeven WR | Edge (pp) | Avg win $ | Avg loss $ | PF | PF CI (95%) | Total $ | Total $ CI (95%) |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|---:|---|
| **All 394** | 394 | 25.4% | [21.1%, 29.4%] | 25.9% | -0.5 | $224.37 | -$78.50 | 1.024 | wide, crosses 1 | $535 | crosses 0 |
| **Current cap (-50%) n=239** | 239 | **32.6%** | [26.8%, 38.9%] | 29.3% | **+3.4** | $239.85¹ | -$99.19¹ | **1.233** | [0.840, 1.741] — crosses 1 | **$3,532** | [-$2,639, $9,825] — crosses 0 |
| Legacy cap n=155 | 155 | 14.8% | [8.4%, 20.0%] | 20.2% | -5.4 | — | — | 0.554 | — | -$2,997 | — |

¹ current-cap-cohort avg win/loss dollars from `current_cap_cohort_summary` in the JSON.

**Read:** the current -50%-cap era (n=239, the policy-relevant slice) shows a positive point-estimate
edge over breakeven (+3.4pp WR, PF 1.23, +$3,532), consistent with CLAUDE.md's "low-WR right tail —
wins must run ≥1.3x" framing (`avg_r_multiple_winners` = **+1.34R**, `avg_r_multiple_losers` = **-0.51R**
in the JSON — a win averages ~1.3× the loss unit, a loss averages just over half of it, which is the
textbook shape of a capped-loss / uncapped(-ish)-win system, and matches the HARD-CONSTRAINTS framing
"wins need >=1.3x" almost exactly). But **the 95% CI on both PF and total $ crosses the neutral
line** — this book is not yet statistically distinguishable from breakeven at n=239. That uncertainty
is exactly why a further-tightened cap needs a strongly positive signal to justify shipping, and the
sweep below shows the opposite sign.

---

## 3. Exit-stage R-multiple distribution (current -50% cap cohort, clean R-unit)

No ground-truth exit-reason tag exists in `fills-ledger.jsonl` or `mae-mfe.json` — stage is
**derived**: loser + `exit_pct <= cap_pct + 0.05` → `cap_hit` (closed at/near the configured stop);
loser otherwise → `structure_or_time_loss`; winner + `exit_pct >= 1.00` → `tp_or_target`; winner
otherwise → `small_win`. Disclosed as approximate.

| Stage | n | % of cohort | Avg R | Median R | Total $ |
|---|---:|---:|---:|---:|---:|
| `structure_or_time_loss` | 121 | 50.6% | **-0.37R** | -0.32R | -$8,863 |
| `cap_hit` (full -50% stop) | 32 | 13.4% | **-1.05R** | -1.03R | -$6,313 |
| `small_win` | 60 | 25.1% | +1.06R | +1.06R | +$12,179 |
| `tp_or_target` (≥+100%) | 18 | 7.5% | +2.27R | +2.14R | +$6,529 |
| `scratch` | 8 | 3.3% | 0 | 0 | $0 |

**Key fact for the hypothesis:** only **32 of 153 losers (20.9%)** in the current-cap cohort actually
run the position to the full -50% cap — the other **121 (79.1%) already exit earlier**, via structure
stop or time, averaging **-0.37R**, well inside a -50% cap. A tighter cap can only ever act on this
79.1% majority as a **pre-emptive** trigger (since their actual configured cap never bound) — and that
pre-emptive action is exactly the "kills a recovering trade before its structure-stop naturally lets
it go" mechanism the sweep below prices out.

---

## 4. The cap-tightening sweep — methodology

For candidate cap `C ∈ {30%, 35%, 40%, 50%}`, restricted to positions where
`mae_before_first_exit == True` (the adverse excursion happened while the full position was still
open — the only case a stop rule could plausibly have fired on; per-prereg the complementary case is
flagged hypothetical/post-partial and excluded):

- If `mae_pct <= -C` (price traded through -C% at some point in the window): assume the position
  exits **at exactly -C%** on first touch. `counterfactual_pnl = notional × (-C)`.
- Else: unaffected, `counterfactual_pnl = realized_pnl`.
- `delta = counterfactual_pnl - realized_pnl`, bucketed:
  - **winner + breached → `winner_killed`** (delta always negative — real profit given back)
  - **loser + breached + actual worse than -C → `loss_saved`** (delta positive)
  - **loser + breached + actual better than -C (i.e. it recovered before its real exit) →
    `false_stop_worsened`** (delta negative — the tighter rule fires on a dip the trade would
    otherwise have shaken off)
  - not breached → `unaffected`

**Look-ahead note:** the proposed *live rule itself* is look-ahead-free — "exit when current price
crosses a static -C% threshold from entry" needs only the entry tick's own premium and the current
tick, nothing from the future (C6-compliant). The **evaluation** here uses each trade's full-window
MAE to determine IF that threshold would ever have been crossed, which is standard retrospective
backtesting of a causal rule, not a look-ahead rule design. The genuine hindsight element is
narrower: **we only know a trade recovered from a dip (the `winner_killed` / `false_stop_worsened`
buckets) after the fact** — a live version of the tightened rule has no way to distinguish "this dip
recovers" from "this dip is the start of the real move," which is precisely why those buckets exist
and are priced as losses in the sweep, not survivor-biased away.

**Approximation disclosed:** exit assumed at exactly -C% on first touch (no slippage / gap-through
modeled beyond the existing bar-low convention frozen in `PREREG-2026-08-01.md`); the prereg's own
caveat applies ("bar-low basis... overcounts touches vs live behavior" — the live actuator samples
one NBBO snapshot per ~minute, not every intra-minute print).

---

## 5. Sweep results

### All 394 positions (any configured cap; sensitivity view)

| Cap | n eligible | Winners killed | $ | Losses saved | $ | False-stop-worsened | $ | **Net $** | 95% CI | Big winning days hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| -30% | 372 | 11 | -6,202.70 | 50 | +1,767.10 | 22 | -670.00 | **-5,105.60** | [-9,579, -1,272] | 08-06, 08-27, 08-28 |
| -35% | 372 | 8 | -5,230.95 | 40 | +1,174.25 | 19 | -633.40 | **-4,690.10** | [-9,034, -1,174] | 08-06, 08-27, 08-28 |
| -40% | 372 | 4 | -2,650.20 | 31 | +777.80 | 15 | -697.60 | **-2,570.00** | [-6,041, -17] | 08-06, 08-27, 08-28 |
| -50% | 372 | 0 | 0 | 12 | +282.00 | 15 | -762.00 | **-480.00** | [-1,144, +151] | none |

### Current -50%-cap cohort only (n=239, the policy-relevant slice)

| Cap | n eligible | Winners killed | $ | Losses saved | $ | False-stop-worsened | $ | **Net $** | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| -30% | 228 | 11 | -6,202.70 | 34 | +1,332.50 | 17 | -626.30 | **-5,496.50** | [-9,823, -1,851] |
| -35% | 228 | 8 | -5,230.95 | 26 | +822.30 | 16 | -594.35 | **-5,003.00** | [-9,355, -1,583] |
| -40% | 228 | 4 | -2,650.20 | 19 | +495.00 | 14 | -647.60 | **-2,802.80** | [-6,045, -322] |
| -50% (sanity check vs own bar data) | 228 | 0 | 0 | 5 | +83.50 | 12 | -631.50 | **-548.00** | [-1,081, -123] |

**The -50% row is not "tighten the cap" — it's a sanity check** validating the sweep methodology
against the current rule's own configured level. Its negative net ($-548, CI excludes zero) is the
**bar-low-vs-live-actuator granularity gap** documented in the prereg, not evidence the live -50% cap
itself is unprofitable — it means "a hypothetical rule that stops on the FIRST bar-low touch of -50%"
would do slightly worse than what the live 1-min-poll actuator (and structure-stop layer) actually
achieved, because live sampling misses some of the bar-low's intra-minute noise. This is exactly the
2026-07-08 noise-floor finding generalized: bar-level MAE resolution is systematically pessimistic
about where a naive stop would have to fire.

### By VIX regime (all-population sweep, net $ only)

| Regime | n | -30% | -35% | -40% | -50% |
|---|---:|---:|---:|---:|---:|
| VIX < 15 | 95 | -2,924.20 | -2,639.65 | -1,106.40 | -387.00 |
| VIX 15-17 | 241 | -2,182.60 | -2,012.35 | -1,365.20 | +39.00 |
| VIX > 17 | 58 | +1.20 | -38.10 | -98.40 | -132.00 |

Negative (or ~flat) in every regime at -30%/-35%. The one near-zero cell (VIX>17, -30%, +$1.20 on
n=58) is not a signal — it is one cell out of twelve, magnitude is noise-floor-sized, and it flips
negative at -35% in the same regime. **No regime rescues the tightening.**

### Big winning days (named anchors: 08-06, 08-13, 08-27, 08-28)

| Date | Total realized $ | n winners | -30% kills | -35% kills | -40% kills | -50% kills |
|---|---:|---:|---|---|---|---|
| 2026-08-06 | $1,465 | 3 | 3 winners / -$1,501 | 3 / -$1,501 | 2 / -$1,205 | 0 |
| 2026-08-13 | $1,748 | 8 | 0 | 0 | 0 | 0 |
| 2026-08-27 | $1,897 | 9 | 1 / -$159 | 1 / -$159 | 1 / -$159 | 0 |
| 2026-08-28 | $1,304 | 4 | 4 winners / -$2,249 | 3 / -$1,722 | 1 / -$509 | 0 |

08-28 is the worst case: at -30% the counterfactual **kills every single winner that day**
(-$2,249 against a $1,304 day). 08-06 loses its entire day's profit at -30%/-35% (-$1,501 vs a
$1,465 day). Only 08-13 is untouched at every level tested. **A tighter cap would have materially
damaged 3 of the 4 named anchor days.**

---

## 6. By arm (current -50% cap membership; context, not the sweep target)

| Arm | n | WR | PF | Total $ |
|---|---:|---:|---:|---:|
| bold-2 | 42 | 35.7% | 1.016 | $60 |
| risky-1 | 83 | 26.5% | 1.201 | $947 |
| risky-3 | 94 | 22.3% | 0.911 | -$522 |
| safe-1 | 24 | 8.3% | 0.565 | -$242 |
| safe-2 | 88 | 25.0% | 0.922 | -$336 |
| safe-3 | 63 | 28.6% | 1.225 | $628 |

(These are the arm's cap-membership counts as recorded in the ledger, not the sweep's counterfactual
— arm-level counterfactual $ figures are in the JSON's `cap_sweep_current_cap_cohort_only` if a
follow-up needs the per-arm breakdown; not reproduced here to keep this report lean per the effort
budget, since the book-wide and regime cuts already carry the verdict.)

---

## 7. Hindsight caveat (mandatory, C6)

MAE is knowledge of a trade's eventual worst point in its holding window — available only after the
fact. `PREREG-2026-08-01.md` states this explicitly: "MAE knowledge is hindsight by definition... a
live stop cannot condition on it." Every `winner_killed` / `loss_saved` / `false_stop_worsened` figure
in this report is a **retrospective counterfactual over the realized population**, evaluating "what
if a static, causal threshold rule had been running the whole time" — it is NOT itself a look-ahead
rule (see §4's look-ahead note), but it IS evaluated with the benefit of knowing which dips recovered.
That is unavoidable for ANY historical stop-width study and is why the **prior settlement** on this
exact mechanism (`stop_inside_noise_floor`) required "a PRE-REGISTERED regime classifier that
identifies the paying regime BEFORE the entry, not after" before it could be reopened — no such
classifier is proposed or tested here. This report's finding is **consistent with, not contradicting,
that standing bar** — it re-confirms the same conclusion on the current-era population rather than
attempting to clear that bar.

---

## 8. Caveats & limitations

- **Two-cohort mixing:** the "ALL 394" cuts blend the current -50% policy with three legacy per-arm
  configs (-20%/-6%/-8%, n=155 combined). The current-cap cohort (n=239) is the policy-relevant slice
  and is reported in parallel throughout — always prefer that column.
- **Derived exit-stage labels** (`cap_hit` / `structure_or_time_loss` / etc.) are approximate —
  no ground-truth exit-reason field exists in either `fills-ledger.jsonl` or `mae-mfe.json`.
  Classification is `exit_pct` vs `cap_pct` threshold-based; a small number of trades near the
  boundary (`cap_pct + 5pp`) could be mis-bucketed.
- **VIX regime join is date-level, not tick-level:** median of `account=='safe'` VIX ticks that day,
  applied to ALL arms (fleet arms' own `decisions.jsonl` carry `vix: null` throughout — verified before
  falling back to this join). Reasonable since VIX is a market quantity, not account-specific, but a
  same-day regime transition (e.g. VIX crossing 15 or 17 intraday) is not captured per-trade.
  0 of 394 trade-dates were missing a VIX row.
  - **Prior-settlement's `artifact_caveat`** (re-quoted here since it bears on this same mechanism):
  the `stop_inside_noise_floor` settlement notes its own `stopped_then_paid` tag was partly an
  artifact of an unbounded-upside hold-to-time counterfactual later quarantined as an ORACLE
  (2026-08-06 DIAGNOSTIC_COUNTERFACTUALS fix). This report's counterfactual is a **bounded** stop-at-C%
  model (not hold-to-time), so it does not inherit that specific artifact, but the general lesson —
  historical stop-width counterfactuals are easy to bias — applies to any reader extending this work.
- **Bootstrap:** 3,000 resamples, percentile method, 2.5%/97.5%. Sample sizes at the tail cuts (e.g.
  VIX>17 n=58, big-day n per date ≤9) are small; CIs on those cells are correspondingly wide and are
  presented as point context, not standalone claims.
- **n=239 current-cap cohort is itself not yet statistically distinguishable from breakeven**
  (PF CI [0.84, 1.74], total-$ CI crosses zero) — this analysis answers "does tightening help," not
  "is the current cap itself proven positive." Those are separate questions; only the former was in
  scope for H8.

---

## 9. Recommendation

**No live rule change.** The -50% catastrophe cap stays as configured. This is consistent with the
config freeze in force until 2026-10-30 (no edit was made to any trading-path file; this is a
read-only analysis). If a future session wants to revisit stop width, the prior settlement's own
condition for reopening applies: build and pre-register a regime classifier that identifies the
paying regime **before** entry — a bare width sweep, in either direction, is graveyarded twice now
(2026-08-06 original settlement + this report on the current-era population).
