# PREREG — TIGHT-LADDER FORWARD TEST (frozen 2026-08-28, before the window opens)

> **Status: FROZEN.** Written and committed 2026-08-28 evening ET, before any data in the test
> window exists. The market is closed; the window opens 2026-09-01 09:30 ET. Nothing in this file
> may be edited after the window opens — corrections go in a dated addendum below the signature line.
>
> **This file arms nothing.** It defines a measurement and a decision rule. Arming live money
> remains J's action alone (OP-0 #1).

---

## 1. THE HYPOTHESIS (J's framing, 2026-08-28)

> *"Enough contracts to scale out and ride the ribbon, but keep it tight."*

The engine's money comes from the exit ladder, not from position size. Between 2026-08-18 and
2026-08-19 a set of size/exposure fixes landed (book-exposure ceiling armed `3a032973`, wired to the
fleet path `05ae765b`, cap refresher `1c9aa55a`; later the extra-setup lane disarm `a905ad5f`).

**H1 — the post-fix engine has positive per-contract expectancy that survives its best day and
realistic execution costs.**

Observed but NOT proven (this is what the test is for), measured 2026-08-19..2026-08-28:

| Cut | Pre-fix (34d, n=313) | Post-fix (8d, n=69) |
|---|---:|---:|
| Total | −$2,313 | +$3,455 |
| Win rate | 22% | 43% |
| Max position | $1,880 | **$925** |
| Trades > $1,200 | 10 | **0** |
| Mean position | $365 | $366 |
| **Per contract** | **−$0.20** | **+$13.02** |
| Per contract, ex-best-day | −$3.30 | **+$6.73** |

**The mechanism we believe is operating** (and which the test must be able to falsify): the ladder
was always profitable; what changed is the cost of the losers.

| | ladder exits | everything else |
|---|---:|---:|
| Pre-fix | +$14,521 (44 trades) | −$16,834 (−$63/trade) |
| Post-fix | +$4,634 (13 trades) | −$1,179 (−$21/trade) |

**Explicitly disclosed weakness:** per-contract P&L is size-neutral by construction, so a size cap
alone CANNOT explain a move from −$0.20 to +$13.02. Part of the observed improvement is therefore
other fixes, regime, or noise on 8 days — two of which (08-27 +$1,897, 08-28 +$1,304) are among the
period's best. **This prereg exists because that ambiguity cannot be resolved on the data that
generated the hypothesis.**

---

## 2. THE CONFIGURATION UNDER TEST

Held constant for the whole window. No mid-window tuning (Rule 9).

| Knob | Value | Rationale |
|---|---|---|
| Contracts per entry | **3 minimum, 5 maximum** | 3 = TP1 sells 2, 1 rides (floor for a real runner). 5 = sells 3, 2 ride. Above 5 adds drawdown, not runner quality. |
| Hard dollar cap per position | **$1,000** | Contracts alone do not bound risk — 3 contracts of a $2.50 option is $750. Both caps bind. |
| Exit ladder | **unchanged** — rungs +50%/+75%, TP1 +100% sell 66.7%, trail 15% off HWM, structure stop, −50% cap | The ladder is the profit engine. It is NOT under test. |
| Signal flow | **all qualifying signals** | The per-day figures assume the full signal flow, not one arm's fraction. |
| Setups | current armed set only | The extra-setup lane stays disarmed (`a905ad5f`). |

**Nothing else changes during the window.** No new filters, no re-tuning, no arm reconfiguration.
A clean window is the entire point; changing the system mid-window voids the test.

---

## 3. THE METRIC — fixed now, not chosen later

**Primary:** mean P&L **per contract**, day-clustered, one-sided, net of measured execution cost.

Per-contract because it is size-neutral: it cannot be flattered by sizing up on good days.
Day-clustered because all arms trade one shared signal (pairwise r ≈ 0.62–0.72); the trading day is
the only honest independent unit.

**Execution cost:** the measured value from `analysis/quote-tape/` (recorder shipped 2026-08-28,
first data 2026-09-01). Until ≥100 matched exit quotes exist, report the metric at **$0.00, $1.00
and $2.00 per contract** and treat **$2.00 as the headline** (the repo's own conservative figure).
When the measured number lands, it replaces the sweep — and the measured number is used regardless
of whether it helps or hurts.

**Secondary (reported, not decisive):** ladder-reach rate (fraction of entries reaching +50% of
premium), loser cost per trade, max position size, WR.

---

## 4. THE WINDOW — start AND end registered

- **Opens:** 2026-09-01 09:30 ET
- **Closes:** **2026-10-30 16:00 ET** (or the first day the day-count bar below is met, whichever is later)
- **Day-count bar:** ≥ **40 trading days** with ≥ 1 qualifying entry.

Registering the end date is deliberate. On the existing tape, moving the window end by ONE day
swung the required sample from 54 days to 132 — an unregistered end date is a free parameter for
whoever writes the report.

---

## 5. THE DECISION RULE — written before the data

Evaluated once, at window close. All four must hold to call H1 supported:

1. **Sign:** mean per-contract P&L > 0 at the measured cost level.
2. **Significance:** day-clustered one-sided lower confidence bound > 0 at 95%.
3. **Concentration (primary, not a side condition):** the sign **survives removing the single best
   day**. This is the test this engine has historically failed; it is not a tiebreaker.
4. **No regression:** no rule break, no manual intervention (target 0 — counted by
   `analysis/interventions/summary.json`), and zero ITM-at-expiry violations.

**If supported:** H1 becomes the basis for a *separate* live-arming decision by J. Support here is
necessary, not sufficient — it does not authorize real money by itself.

**If not supported — the kill rule, stated now:** the tight-ladder config is not carried forward as
an assumption. Specifically, if mean per-contract P&L at the measured cost is **≤ 0**, or the sign
fails the ex-best-day test, then the post-fix improvement is declared **regime or noise**, the
November live question is answered NO, and the next question becomes whether the strategy has an
edge at all rather than how to size it.

**Peeking:** interim readings may be produced (the nightly chain will emit them) but MUST NOT
change the configuration, the metric, the window, or this decision rule.

---

## 6. WHAT WOULD MAKE THIS TEST INVALID

Stated up front so it cannot be rationalized later:

- Any change to the exit ladder, setup set, sizing rule, or gate set during the window.
- Any manual trade or override on the tested arms.
- Substituting a different cost assumption than the measured one once it exists.
- Reporting a window other than the registered one.
- Any arm reconfiguration or retirement inside the window (note: risky-3 was retired 2026-08-28,
  BEFORE the window opens — that is fine; a mid-window equivalent would not be).

---

## 7. PROVENANCE

- Hypothesis source: J, 2026-08-28 — *"enough cons to scale out and ride the ribbon but keep it tight."*
- Supporting analysis, this session: per-contract economics, pre/post-fix split at 2026-08-19,
  exit-reason decomposition, ex-best-day concentration checks. All computed from
  `analysis/trades-enriched.jsonl` (canonical basis, FIFO-reconciled).
- Related instruments: `setup/scripts/quote_recorder.py` (cost measurement),
  `analysis/interventions/summary.json` (criterion 4), `setup/scripts/lib/scorecard_guards.py`
  (day-bootstrap + ex-best-day machinery), `setup/scripts/go_live_gate.py` (separate live gate).
- Doctrine: OP-11 eval-first, C4 concentration disclosure, C6 no look-ahead, Rule 9 no mid-window
  rule changes, OP-0 #1 arming is J's alone.

---

*Frozen 2026-08-28 evening ET. Addenda below this line only; the sections above are immutable.*
