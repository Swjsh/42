# ONE-POSITION-AT-A-TIME CONSTRAINT COST — 2026-08-02

**Lane type: MEASUREMENT ONLY. Ships nothing, arms nothing.** Concurrency (whether the
engine may ever hold 2+ SPY 0DTE positions at once) is a risk-posture call under Rule 6
(per-trade cap) and Rule 5 (daily kill switch) — J's call, not this session's. This
document is the number and the risk analysis; the decision is explicitly left to J,
framed at the bottom.

Prereg (frozen before any code ran): [`PREREG-ONE-POSITION-CONSTRAINT-COST-2026-08-02.md`](PREREG-ONE-POSITION-CONSTRAINT-COST-2026-08-02.md)
(commit `3434525d`). Runner: [`backtest/tools/one_position_constraint_cost_2026_08_02.py`](../../backtest/tools/one_position_constraint_cost_2026_08_02.py).
Raw output: [`ONE-POSITION-CONSTRAINT-COST-2026-08-02.json`](ONE-POSITION-CONSTRAINT-COST-2026-08-02.json).
Guards: [`backtest/tests/test_one_position_constraint_cost_2026_08_02.py`](../../backtest/tests/test_one_position_constraint_cost_2026_08_02.py)
(18/18 pass, RED-proofed — see Methodology). Window 2025-01-02..2026-07-22 (386 calendar
days), current live sizing shape both arms (Bold `min_contracts=5`, Safe `min_contracts=3`),
static live-verified equity (Bold $1,197.52, Safe $1,746.75).

## Bottom line

- **The refused cohort is tiny and mostly not worth having.** Over 386 days, exactly **3
  Bold signals** and **7 Safe signals** were ever refused purely because a slot was
  occupied. Bold's refused cohort **lost money** (−$130.00, 0% win rate). Safe's refused
  cohort made **+$493.60** — real, but **zero of it falls inside either arm's most recent
  25 trades** (J's own recency-first doctrine's primary window is untouched by this
  entire question).
- **3 concurrent slots is not a real option — it never binds.** Going from 2 slots to 3
  captures **exactly $0.00 more** for both arms across the full 386-day history. The
  actual question is 1 vs 2, full stop.
- **2 slots would have pushed peak simultaneous capital-at-risk to 63.9% (Bold) / 85.4%
  (Safe, likely overstated — see caveat) of account equity** — well past the 50%/30%
  single-trade ceiling the "one max-loss trade = day is done" design (risk-rules.md,
  confirmed live in both params files at a strict 1:1 per-trade-cap : kill-switch ratio)
  was built around.
- **Historically, no NEW kill-switch-breach day resulted** from allowing 2 slots — same
  breach days, same count, at K=1 and K=2 for both arms. But this is an end-of-day
  realized-P&L proxy, a **disclosed lower bound**, not a live intraday mark-to-market
  check — the real gate could plausibly trip mid-session under concurrency even on a day
  that closes fine. Say this plainly: absence of evidence here is not evidence of absence.
- **Slot-turnover (the "cheaper lever") is not actually cheap.** For Safe, 5 of the 7
  refused signals were blocked by a trade in its **`runner_stop`** phase — i.e., a
  *winner correctly riding its runner leg*, exactly the behavior the strategy is designed
  to protect. Freeing the slot faster there means clipping a runner short, not trimming
  fat. For Bold, the 3 occupants are `time_stop`/`structure_stop` exits (not runner-clips,
  genuinely cheaper to shorten) — but Bold's refused cohort is net-negative anyway, so
  there is nothing worth rescuing on that side either.
- **Recommendation to J: keep the constraint.** The measured upside is small-to-negative,
  entirely absent from the window that matters most under the recency doctrine, and the
  one lever that would recover part of it (faster exits) mostly means cutting winners'
  runners short — a cost, not a free lunch. The risk side is a real, non-trivial stretch
  of the kill-switch design margin for a return this thin. This is a validated constraint,
  not an unexamined one — see Provenance below for the one place its own justification was
  imprecise (a different rule than the one it cites) and the one gap surfaced along the way
  (Safe's population never modeled the risk-cap-affordability filter Bold's does).

---

## 1. Provenance — what is this constraint, really?

**The mechanism.** `setup/scripts/heartbeat_core.py` (~line 1895):

```python
if not fb.is_flat_spy_options(creds):
    _adopted = _adopt_untracked_positions(...)
    return {"status": "NOT_FLAT", "adopted": _adopted}
```

with the code's own comment immediately above it (lines 1885-1898, verbatim):

> "FLAT-verify (broker = source of truth, L47/C11) + MANUAL/ENGINE COEXISTENCE (FIX1,
> 2026-07-07, J: 'get rid of the lockout'). **Any open SPY-option position still BLOCKS a
> 2nd (stacked) entry — that protects the Rule-6 per-trade risk cap.** ... We STILL return
> NOT_FLAT: no stacking."

**Rule 6's actual text** (CLAUDE.md): "Per-trade risk cap — per account: Gamma-Safe: 30%
of account equity. Gamma-Bold: 50% of account equity. Min 3 contracts (2 TP + 1 runner)."
This is textually a **PER-TRADE** cap. Two concurrent positions, each independently sized
under its own 30%/50% ceiling, do not violate Rule 6's letter — nothing in its text
addresses a second position existing at all.

**So the code comment is imprecise about WHICH rule it protects.** What actually breaks if
two capped positions stack is not Rule 6 — it's the deliberate 1:1 relationship between
Rule 6's per-trade cap and **Rule 5's** daily kill switch. `risk-rules.md` states this
explicitly, in the section titled "The math behind the daily stop":

> "At max-risk-per-trade = 50% and daily-stop = 50%, by construction: **One max-loss trade
> = day is done.** This is intentional. The system is designed so that a single losing
> trade doesn't get followed by a revenge trade. The kill switch fires on the same trade
> that hit the per-trade risk cap. **Behavioral protection.**"

This is not legacy prose — it is **still true today, verified live in both params files**:

| Account | `per_trade_risk_cap_pct` | `daily_loss_kill_switch_pct` | Ratio |
|---|---|---|---|
| Safe (`automation/state/params.json`) | 0.30 | 0.30 | **1:1** |
| Bold (`automation/state/aggressive/params.json`) | 0.50 | 0.50 | **1:1** |

Both accounts, unchanged from the original single-account design, are still built so that
**one fully-sized losing trade already exhausts the daily kill switch.** A second
concurrent position, each independently within its own Rule-6 cap, can put up to 2× that
— 100% of equity (Bold) or 60% (Safe) — at risk simultaneously. That is squarely against
the *spirit* of Rule 5 even though it never touches Rule 6's letter. **This is the
tension the task asked to be stated explicitly, and it is real**: Rule 6 alone would
happily allow it; the "one max-loss trade = day is done" design behind Rule 5 would not.

**Classification: (b), a conservative implementation choice — but one whose own
justification cites the wrong rule number.** It is not (a) a direct requirement of any
rule's literal text (no rule bans concurrency outright). It is not (c) an unexamined
default — the code comment shows it *was* reasoned about once (FIX1, 2026-07-07, J: "get
rid of the lockout" — the flat-check was deliberately kept even after that fix loosened
the adjacent manual/engine-coexistence lockout). It protects the **Rule 5/Rule 6
interaction** (the 1:1 "one max-loss trade = day done" design), not "the Rule-6 per-trade
risk cap" in isolation as currently written. Separately, `automation/overnight/queue.md`
(2026-07-20 entry) independently describes "the primary ribbon path already has its own
one-position-at-a-time + gate discipline" as a settled, load-bearing design property this
session did not introduce or question — consistent with (b), not (c).

---

## 2. Opportunity cost — what does K=1 actually refuse?

Method: `bold_fullhist_replay.py`'s already-shipped, already-anchored candidate
population (Bold) + a hand-built exit_time_et-capturing variant of
`engine_fullhist_replay.py`'s own loop (Safe, that file itself untouched) → a generalized
`_sequential_admit_concurrent(rows, K)` (proven byte-parity with the already-shipped
`_sequential_admit` at K=1, and cross-checked against an independently-coded "cascading
servers" formulation on the real population — 6/6 exact matches, Bold/Safe × K∈{1,2,3}).

### Per concurrency level (recent-25 first, per J's dynamic-market/recency doctrine)

**BOLD** (equity $1,197.52, 156 candidate signals after the live risk-cap-affordability
filter):

| K | n admitted | Total P&L | Recent-25 P&L | WR | Gained vs prior K | Gained P&L |
|---|---|---|---|---|---|---|
| 1 (current live) | 153 | $+7,578.40 | **$+2,841.40** | 33.99% | — | — |
| 2 | 156 | $+7,448.40 | **$+2,864.40** | 33.33% | +3 | **−$130.00** |
| 3 | 156 | $+7,448.40 | $+2,864.40 | 33.33% | +0 | $0.00 |

**SAFE** (equity $1,746.75, 191 candidate signals — no risk-cap-affordability filter
modeled, see caveat below):

| K | n admitted | Total P&L | Recent-25 P&L | WR | Gained vs prior K | Gained P&L |
|---|---|---|---|---|---|---|
| 1 (current live) | 184 | $+4,315.15 | **−$1,238.05** | 29.35% | — | — |
| 2 | 191 | $+4,808.75 | **−$1,238.05** | 29.32% | +7 | **+$493.60** |
| 3 | 191 | $+4,808.75 | −$1,238.05 | 29.32% | +0 | $0.00 |

**K=3 is moot for both arms — it never once admits a signal K=2 wouldn't have.** The
practical question this whole study reduces to is 1 vs 2, not "how many slots."

**The refused-at-K=1 cohort, in full:**

| Arm | n | Total P&L | WR | Drop-best remainder | Recent-25 (=whole cohort, n<25) |
|---|---|---|---|---|---|
| Bold | 3 | **−$130.00** | 0% | −$115.00 (still negative) | −$130.00 |
| Safe | 7 | **+$493.60** | 28.6% | −$38.40 (flips negative) | +$493.60 |

Safe's refused cohort's own drop-best check **fails** (removing its single best trade,
+$532.00, flips the remaining 6 to net negative) — the entire positive read is one trade.
Combined with zero presence in the recent-25 window, this is a thin, concentrated,
stale edge, not a robust one.

### Side finding, disclosed per OP-33 (not fixed, out of this lane's scope)

Safe's already-shipped headline (`engine-fullhist-replay-2026-07-23.json`, n=191,
$4,808.75, cited as the Safe engine's full-history number) **was never checked for
position-sequencing validity before this study.** A true K=1 sequential walk shows **7 of
those 191 rows were themselves mutually overlapping** (self-pre-emption) — true
one-at-a-time Safe P&L is $4,315.15/n=184, not $4,808.75/n=191. This is exactly the
`filter5_ribbon_fate_2026_07_31.py` / Bold-adaptive-sizing precedent (a naive candidate
count silently assumes every row is independently takeable) surfacing on the Safe side for
the first time. Flagged, not corrected here — correcting the shipped Safe headline is a
separate, narrowly-scoped fix.

---

## 3. Risk cost — equal weight, not an afterthought

### Peak simultaneous capital deployed

"Capital at risk" = `entry_premium × qty × 100`, the same notional definition
`resolve_bold_qty` / `risk_gate`'s own RISK_CAP gate uses for Rule 6 — not invented fresh.

| Arm | K | Peak notional | % of equity | Peak concurrent count | When |
|---|---|---|---|---|---|
| Bold | 1 | $595.00 | 49.7% | 1 | 2025-05-09 |
| Bold | 2 | $765.00 | **63.9%** | 2 | 2025-10-24 14:45 |
| Safe | 1 | $840.00 | 48.1%* | 1 | 2026-06-25 |
| Safe | 2 | $1,491.00 | **85.4%*** | 2 | 2025-09-17 13:20 |

**\*Caveat, load-bearing:** Safe's K=1 peak (48.1%) already **exceeds Safe's own 30%
Rule-6 cap** ($524.02) by $315.98. This is not a concurrency artifact — it's the disclosed
gap that Safe's inherited candidate population (unlike Bold's) never modeled the
risk-cap-affordability exclusion `resolve_bold_qty` applies for Bold. Some individual Safe
candidate trades in this population are already oversized relative to what live
`risk_gate`'s RISK_CAP gate would actually allow. Safe's absolute percentages here likely
**overstate** true live exposure at both K=1 and K=2; the picture the *delta* tells
(+37.3 points from adding a second slot) is more trustworthy than either raw number. This
gap is a good candidate for its own follow-on fix — not attempted here.

Bold's numbers carry no such caveat (`resolve_bold_qty` already filters unaffordable
signals out of the candidate population) — **63.9% simultaneous exposure at K=2 is a
clean, trustworthy reading**, and it is materially above the 50% ceiling the "one max-loss
trade = day done" design assumes for a single position.

### Kill-switch impact

Day-level **realized** P&L vs `-equity × daily_loss_kill_switch_pct` (a disclosed **lower
bound** on true intraday risk — see caveat below).

| Arm | K | Threshold | Breach days | Worst day |
|---|---|---|---|---|
| Bold | 1 | −$598.76 | 1 (2025-06-06, −$605.00) | 2025-06-06, −$605.00 |
| Bold | 2 | −$598.76 | 1 (same day, same total) | 2025-06-06, −$605.00 |
| Safe | 1 | −$524.02 | 2 (2026-06-25 −$825, 2026-06-26 −$708) | 2026-06-25, −$825.00 |
| Safe | 2 | −$524.02 | 2 (same days, same totals) | 2026-06-25, −$825.00 |

**No new breach day appears at K=2 for either arm, historically.** That is genuinely
reassuring on its face — but read the caveat, not just the row:

> **This is END-OF-DAY REALIZED P&L, not a live intraday mark-to-market check.**
> `risk_gate.py`'s own kill-switch docstring defines the real trigger as "(b) realised
> drawdown: `equity <= start_of_day_equity × (1 - daily_loss_kill_switch_pct)`" — checked
> continuously, at the moment of every new entry attempt, against **live account equity**
> (which marks open positions to market). A day that closes fine by 16:00 could still have
> put two positions underwater AT THE SAME TIME mid-session, which this end-of-day proxy
> cannot see and this study does not model. **The error direction is one-sided: this
> measurement can only UNDERSTATE risk at K>1, never overstate it.** Take the "no new
> breach day" finding as "not disproven," not as "proven safe."

### This is the C31 pattern in a new shape, and the numbers say it plainly

C31 (CLAUDE.md doctrine): J's 667 real trades were +$4,576 at 1-2 lots and **−$17,461** at
3+ lots — the killer was sizing-UP behavior, not flat trade count. Concurrency is a
different mechanism for the same exposure shape: two simultaneous max-sized positions is
economically the same "more dollars on the table at once" bet 3+ lots was, just spread
across two option symbols instead of one. The measured numbers here are small (nobody is
proposing 3+ lots), but the DIRECTION is the same pattern this codebase has already paid
real money to learn: **capturing $130-$493 of thin, stale, mostly-one-trade edge while
stretching peak simultaneous exposure by 14-37 percentage points past design is not a
trade J's own trading history says to make.**

---

## 4. Slot turnover — the cheaper lever, honestly assessed

For each refused-at-K=1 signal: how many minutes earlier would the occupying trade have
needed to exit for this signal to have gotten a slot?

| Arm | n | Median gap needed | Median gap as % of occupant's own hold |
|---|---|---|---|
| Bold | 3 | 55 min (range 5-170) | 20.4% (range 7.1-68.0%) |
| Safe | 7 | 45 min (range 5-75) | 25.0% (range 6.2-57.7%) |

That alone might read as "trim the last quarter of a hold and you'd mostly free the slot
in time" — a free-looking lever. **It is not free.** The occupant's own exit reason tells
the real story:

- **Safe: 5 of 7 occupant-rows exit via `runner_stop`** (`@1.80`, `@2.68`, `@2.41` ×2 same
  trade, `@2.86`, `@3.01`) — i.e., a **winning trade correctly riding its trailing runner
  stop**, exactly the behavior the strategy is designed to protect (chandelier
  profit-lock, arms at +5% favor, trails 15% off HWM). Freeing the slot faster here means
  **cutting a winner's runner short** — not trimming idle fat, but giving up the exact
  upside the runner mechanic exists to capture. This is the same tension C30 already
  documents ("unconstrained exit targets... runner never hits 5x in 0DTE") from the other
  direction: shortening runners has a real, known cost.
- **Bold: occupants are `time_stop_15:40` (×2) and `structure_stop` (×1)** — no runner
  clips. Turnover speedup would be genuinely cheaper on the Bold side. But Bold's refused
  cohort is net **negative** ($−130.00) — there is nothing worth rescuing here regardless
  of how cheap the lever is.

**Pain-ledger cross-reference (separate, smaller, real-fills dataset — descriptive only,
not row-joined):** across 21 real winning fills with usable MFE timing (of 160 total
scored positions, 22 distinct dates 2026-06-26..2026-07-31), the median winner spends only
**7.7%** of its total hold time after its own MFE peak (mean 17.4%, p75 33.3%). Most of a
real winning trade's hold time is spent reaching its peak, not lingering past it — this
does **not** support a "there's easy idle time to trim" story; it's consistent with, and
corroborates, the runner-clip finding above: slots are occupied by trades that are still
legitimately working, not coasting.

**Verdict on turnover: not a clean win.** It is real for Bold (cheap, but pointless — the
cohort it would rescue already loses money) and costly for Safe (the trades doing the
blocking are the ones the strategy most wants to protect). Neither arm gets a free lunch
here.

---

## 5. Recommendation to J

This is your call — Rule 6 and Rule 5 are your rules, and concurrency touches both. The
numbers:

| | Opportunity (386d) | Recent-25 impact | Peak exposure at K=2 | New kill-switch breaches (lower bound) |
|---|---|---|---|---|
| **Bold** | −$130.00 (3 trades) | $0.00 | 63.9% of equity (clean reading) | 0 (but see intraday caveat) |
| **Safe** | +$493.60 (7 trades, one trade is the whole story) | $0.00 | 85.4%* of equity (likely overstated) | 0 (but see intraday caveat) |

**My read: keep the one-position constraint as-is.** The upside on the table is small
(Safe), negative (Bold), or entirely stale — none of it shows up in either arm's most
recent 25 trades, the window your own recency doctrine says to weight most. What it costs
to unlock is a real, disclosed stretch of the exact design margin ("one max-loss trade =
day done") your risk rules were built around, measured only as a lower bound. Three
concurrent slots isn't even a live question — it never once bound in 386 days. If you
still want to explore this, the narrowest, lowest-risk next step is not "flip concurrency
on" — it's fixing the disclosed Safe risk-cap-affordability gap this study surfaced (so
Safe's own numbers stop being partly an artifact of an unmodeled filter) and re-running
this exact measurement on a fresh, longer OOS window before touching anything live.

If the honest answer is "the constraint is correct," that's the deliverable — same as any
other validated-not-shipped result this weekend.

---

## Methodology notes (guards, parity, disclosed limitations)

- **Parity, all green**: Bold K=1 reproduces the already-shipped `bold-adaptive-sizing-
  2026-08-02.json#control_sequential` exactly (n=153, $+7,578.40). Safe's unsequenced
  population reproduces the already-shipped `engine-fullhist-replay-2026-07-23.json`
  headline exactly (n=191, $+4,808.75). The generalized admission function is
  cross-checked against an independently-coded "cascading servers" formulation **on the
  real population** (not just a fixture) — 6/6 exact matches across both arms × all 3
  concurrency levels.
- **Guards**: `backtest/tests/test_one_position_constraint_cost_2026_08_02.py`, 18/18
  green. RED-proofed: one assertion (`gap_minutes_needed == 15.0`) was deliberately
  mutated to a wrong value (`999.0`), confirmed to FAIL (`assert 15.0 == 999.0`), then
  restored and reconfirmed green — proves the guard discriminates rather than being
  vacuously true.
- **Not touched**: `heartbeat_core.py`, `automation/state/fleet/*`, both `params.json`
  files, `exit_manager.py`, `exit_actuator.py`, `strike_selection.py`,
  `backtest/lib/filters.py`, `backtest/lib/option_pricing_real.py`,
  `journal/gex-archive/`. `engine_fullhist_replay.py` was **imported, not edited** — this
  study's own Safe-side loop is a separate, hand-built function that reuses its
  `SAFE_BASE_LIVE`/ribbon helpers verbatim.
- **Disclosed limitations** (also in the prereg): static non-compounding equity for both
  arms (this repo's established full-window-study convention); kill-switch breach
  counting is an end-of-day-realized lower bound, not a live intraday check; Safe's
  candidate population carries no risk-cap-affordability exclusion (Bold's does — a
  pre-existing asymmetry, not introduced here); the pain-ledger cross-reference is a
  separate, much smaller, real-fills-only dataset, never row-joined against the 386-day
  synthetic population; no modeling of `structure_veto_enabled`, PDT/settlement, or any
  other runtime/state-dependent `risk_gate` check (same gap every `*_fullhist_replay.py`
  tool in this repo already discloses).
