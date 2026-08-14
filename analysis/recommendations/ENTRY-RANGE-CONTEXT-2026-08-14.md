# ENTRY-RANGE-CONTEXT — verdict

**Prereg:** `prereg-entry-range-context-2026-08-14.json` (frozen at HEAD `327661f3`, BEFORE this runner existed).
**Runner:** `backtest/autoresearch/entry_range_context_2026_08_14.py`.
**Raw:** `analysis/recommendations/entry-range-context-2026-08-14.json`.
**Population:** identical to the location study — `engine-fullhist-replay-2026-07-23`, real-OPRA fills,
n=173 after the same causal exclusions. Bars, population and `features()` are **imported** from
`entry_location_gate_2026_08_14.py`, so the two studies cannot drift apart.

---

## VERDICT: NOT-RUN — all 16 cells. Nothing is armed, nothing is proposed.

The hypothesis (from the location study's anchors: *"the 08-14 loser was knowable as 0.81pt of
range 16 minutes in; the 08-13 winner had 2.74pt already established"*) **cannot be tested on
this population.** The largest cell gates 14 trades against the pre-registered n>=30 floor.

| side | `range<0.75` | `range<1.00` | `range<1.50` | `range<2.00` |
|---|---|---|---|---|
| **puts** | 1 | 1 | 4 | **14** |
| **calls** | 1 | 5 | 8 | **12** |

**Why so few:** the engine almost never enters into a small established range — by the time a
trigger fires, the day has usually already moved >2pt. The condition the anchors pointed at is
**rare**, which is itself the finding: it is not a lever that touches enough of the book to
matter even if it were real.

---

## The bull side runs OPPOSITE to the hypothesis (reported, not decidable)

All numbers below are **descriptive only** — every cell is under-powered, no permutation test
was run, nothing entered an FDR family. Reported because the prereg says report ALL cells.

| cell | n gated | gated mean | kept mean | blocked winners | book delta if gated |
|---|---|---|---|---|---|
| `C\|range<1.00` | 5 | **+$231.11** | −$0.18 | 3 (**$1,318.55**) | **−$1,155.55** |
| `C\|range<1.50` | 8 | +$61.07 | +$31.56 | 3 ($1,318.55) | −$488.55 |
| `C\|range<2.00` | 12 | +$5.55 | +$63.81 | 4 ($1,350.55) | −$66.55 |
| `P\|range<1.50` | 4 | −$88.05 | +$17.29 | 1 ($6.00) | +$352.20 |
| `P\|range<2.00` | 14 | −$25.06 | +$18.61 | 2 ($711.55) | +$350.85 |

**The side that generated the hypothesis is the side that contradicts it.** The anchor was a
BULL loser in a 0.81pt range. In the replay population, bull entries into a sub-1pt range were
the *best* calls on the book (+$231 mean vs −$0.18), and gating them would have cost **$1,156**.
The put side leans the hypothesis' way (−$25 vs +$19) but at n=14 that is noise.

This is the second time in two days that a plausible entry-context intuition has been
contradicted by the data it was built from. **Both are now on the record so neither gets
re-proposed.**

---

## The confound test, run anyway (prereg G4)

| side | gated n, all sessions | gated n, `>=10:30` only |
|---|---|---|
| puts, `range<2.00` | 14 | **14** |
| calls, `range<2.00` | 12 | **3** |

- **Puts: NOT confounded with time.** Every small-range put entry was late-session. A put taken
  into a 2pt range at 13:00 is a genuinely different thing from an open-avoidance rule.
- **Calls: mostly confounded.** 9 of 12 small-range call entries are pre-10:30, i.e. a bull
  range gate would largely be an open-avoidance gate wearing a different name — exactly what
  G4 was written to catch. The cold-open guard shipped 2026-08-14 (`SKIP_COLD_OPEN`) already
  covers that window on its own evidence.

---

## Validity gates

- **G1 population parity** — PASS. Same 173 trades, same exclusions, same imported features.
- **G2 monotonicity** — PASS both sides (P 1/1/4/14, C 1/5/8/12 as the threshold widens). The
  feature is live, not inert (C14).
- **G3 anchors** — the two named anchors point the hypothesis' way (`0.81pt` loser gated by
  three of four thresholds; `2.74pt` winner gated by none) and are **two data points**. They
  generated the hypothesis; they cannot also confirm it.
- **G4 time confound** — RUN, and disqualifying on the bull side (above).
- **G5 read-only** — PASS. No params touched, nothing armed.

---

## What this closes

`min_contracts_equity_scaled` stays **disarmed**. Its re-arm condition is a *validated*
entry-quality gate; two studies have now returned nothing that qualifies:

| study | verdict |
|---|---|
| `ENTRY-LOCATION-GATE-2026-08-14` | NULL (bear 0/4 survive BH-FDR; bull NOT-RUN at n=29) — and **refuted by its own anchors** |
| `ENTRY-RANGE-CONTEXT-2026-08-14` | NOT-RUN, all 16 cells; bull side runs opposite |

**The binding constraint is the same in both, and it is data, not analysis:** the engine logs
nothing that separates a good bull setup from a bad one, so the population contains no such
column to test. `setup/scripts/entry_location_shadow.py` records `range_pts` and the location
features on every live entry from today forward. That is the only path that changes this
answer, and it changes it in weeks, not tonight.

**Handoff item N4 is CLOSED as an armable idea and stays OPEN as a shadow-recorded feature.**
