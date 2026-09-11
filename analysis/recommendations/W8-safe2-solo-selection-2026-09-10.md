# W8 — safe-2 solo-selection discriminator (measurement only, no package)

**Orchestrator, 2026-09-10 23:22:39 Thursday EDT (`et_clock.py`).** Goal:
`automation/state/goals/GOAL-WHY-THIS-WEEK-2026-09-10.md` item W8, continuing W6's finding that
the safe-2 (−$675) vs safe-3 (+$953) engine-attributed gap is NOT sizing/strike/exit (25 shared
waves are near-identical) but lives in SELECTION — which waves each arm takes solo.

## Basis
`analysis/trades-enriched.jsonl` filtered `attribution == "engine"`, arms safe-2/safe-3 only.
Wave-dedupe rule: entry_ts_et floored to a 10-minute bucket = one market event (unchanged from
W6/prior work). 163 engine rows total (95 safe-2, 68 safe-3).

## 1. Recomputed solo populations (engine-attributed, wave-deduped)

| population | waves | legs | net $ | $/wave |
|---|---:|---:|---:|---:|
| shared (both arms, same wave) — safe-2 side | 25 | 27 | +192 | +7.68 |
| shared (both arms, same wave) — safe-3 side | 25 | 25 | +272 | +10.88 |
| **safe-2 solo** | **58** | 68 | **−867** | **−14.95** |
| **safe-3 solo** | **42** | 43 | **+681** | **+16.21** |

Reconciles exactly: shared(+192) + solo(−867) = **−675** (matches W6's gate number to the
dollar); shared(+272) + solo(+681) = **+953** (matches). This supersedes W6's raw-ledger solo
counts (70/42) — those were pre-reconciliation and included pre-engine legs; **58/42 is the
correct engine-attributed split.**

**Answer to the payoff question up front: safe-2's solo population is systematically worse, not
just more numerous** — its $/wave (−14.95) is negative and below its OWN shared-wave rate
(+7.68), while safe-3's solo $/wave (+16.21) is *better* than its shared rate. But the badness is
not spread evenly — see §3.

## 2. Why safe-3 didn't take the 58 safe-2-solo waves

Matched each safe-2-solo wave's entry timestamp (±5 min) against `automation/state/fleet/safe-3/decisions.jsonl` (safe-3's own per-tick decision ledger) and classified the dominant HOLD reason:

| dominant reason category | waves | net $ | $/wave |
|---|---:|---:|---:|
| `NEVER_SAW_SIGNAL` ("no qualifying setup — no strategy fired") | 51 | −497 | −9.75 |
| `TRIGGER_GATE` ("1 triggers < 2" / "requires confluence/sequence") | 6 | −438 | **−73.00** |
| `MIN_PREMIUM_FLOOR` | 1 | +68 | +68.00 |

**NOT_FLAT does not appear here at all** — every one of these 58 waves found safe-3 flat and
watching; it just didn't fire the setup or refused it on the trigger-count gate. (NOT_FLAT is
W7's question, on ENTER verdicts that safe-3 itself generated and then couldn't act on — a
different mechanism, correctly not conflated here per the goal's own instruction.)

Cross-checked against `automation/state/fleet/build_shared_signal.py` and
`automation/state/params.json`'s `extra_setup_exec_armed` block: safe-2's non-ribbon setups
(`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`, `bollinger_squeeze`) are
an **architecturally SAFE-ONLY lane** (`_extra_setup_exec_armed_doc`: "SAFE ONLY", routed via
`heartbeat_core._route_extra_setups`, not the fleet path). `bollinger_squeeze` and
`vix_regime_dayside` do not appear anywhere in `build_shared_signal.py` or `fleet_market.py` —
safe-3 has no detector for them at all. `vwap_reclaim_failed_break` IS emitted into
`strategies[]` for the fleet arms but the code comment states plainly: *"safe-3's
require_confluence_or_sequence structurally HOLDs it (the setup's 3 triggers carry no
confluence/sequence)"* — i.e. a real, documented, permanent gate mismatch, not a bug.

## 3. The discriminator, with dollars

Regrouping the 58 safe-2-solo waves by setup family (ribbon-primary, which both arms run, vs.
the four SAFE-only secondary setups) isolates the effect cleanly:

| safe-2 solo, by setup family | waves | net $ | $/wave |
|---|---:|---:|---:|
| RIBBON_PRIMARY (BEARISH_REJECTION / BULLISH_RECLAIM — the shared strategy) | 30 | **−31** | **−1.03** |
| SECONDARY: vwap_continuation | 7 | −355 | −50.71 |
| SECONDARY: vwap_reclaim_failed_break | 5 | −234 | −46.80 |
| SECONDARY: vix_regime_dayside | 2 | −153 | −76.50 |
| SECONDARY: bollinger_squeeze | 14 | −94 | −6.71 |
| **all 4 secondary setups combined** | **28** | **−836** | **−29.86** |

For comparison, safe-3's 42 solo waves are **100% RIBBON_PRIMARY** and net +$681 (+$16.21/wave)
— and 23 of the 25 shared waves are also RIBBON_PRIMARY.

**THE DISCRIMINATOR, one sentence:** *safe-2's −$675 vs safe-3's +$953 engine-attributed gap is
not a gate/threshold difference on a shared setup — it is that safe-2 alone runs four SAFE-only
secondary setups (`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`,
`bollinger_squeeze`, armed by design per `params.json:extra_setup_exec_armed` and never wired
into safe-3's `build_shared_signal.py` path), and those four setups account for **−$836 across
28 waves (96% of the entire −$867 solo deficit)**, while safe-2's solo trades of the one setup
both arms actually share (RIDE_THE_RIBBON) net **−$31 across 30 waves — statistically
indistinguishable from breakeven**, close to safe-3's own shared/solo ribbon rate.

## 4. Which gate/threshold admits the bad population

Not a threshold — an **architecture/scope difference that predates this week and is documented
in-repo as deliberate** (`_extra_setup_exec_armed_doc`: "SAFE ONLY"). Two of the four secondary
setups (`bollinger_squeeze`, `vwap_reclaim_failed_break`) were already **disarmed 2026-08-24**
after their own independent EOD review found the whole extra-setup lane "n=26 / −$1,055 since
arming and has NEVER been net positive" (quoted from `params.json`'s own disarm doc) — this W8
finding is consistent with, not contradictory to, that prior kill. `vix_regime_dayside` and
`vwap_continuation` remain armed on safe-2 today and are the two worst per-wave performers found
here (−$76.50 and −$50.71/wave respectively), though on small n (2 and 7 waves — **UNDERPOWERED,
flagged, not a kill call on this sample alone**).

## Freeze-test (would this have been proposed last Friday at +$2,323?)
**Yes** — the SAFE-only secondary-setup lane's poor standalone economics were independently
found and partially acted on (2 of 4 setups disarmed) on 2026-08-24, over two weeks before this
losing week. This is not drawdown-chasing; it is confirming and extending an existing,
pre-dated finding with a cleaner engine-attributed cut.

## What this is and is not
- **Not a package.** No trading-path edit ships from this file. `vix_regime_dayside` and
  `vwap_continuation` remain armed; this is measurement only, per the CONFIG FREEZE and W8's own
  scope ("Name the discriminator... with the $ attached" — not "ship a fix").
- **Candidate future 09-29 kill-type reduction** (would need its own prereg, its own n, and to
  clear the freeze process, NOT opened here): disarm `vix_regime_dayside` and
  `vwap_continuation` in `extra_setup_exec_armed`, matching the 08-24 treatment already applied
  to their two siblings. Flagged, not proposed — n=2 and n=7 are too thin to prereg tonight.
- **RIBBON_PRIMARY is exonerated on this cut**: when safe-2 trades the ribbon strategy alone, it
  is breakeven, matching safe-3's shape. The mechanism question W6 raised ("selection, not
  mechanics") is now precise: it is not "which waves" in general, it's "which *setups*" — four
  specific, already-partially-killed secondary strategies that only exist on safe-2's core lane.

## UNVERIFIED / caveats
- The ±5-minute decision-ledger match is a nearest-neighbor join, not a foreign-key join
  (`decisions.jsonl` doesn't carry a wave/trade id back-reference) — spot-checked several rows
  for plausibility (setup name matches, timing matches) but not exhaustively audited row-by-row.
- 2 of the 25 *shared* waves were also secondary-setup trades (1 vwap_continuation, 1
  bollinger_squeeze) — safe-3 does occasionally clear the confluence gate for these, so
  "never wired" is directionally correct but not absolute; noted, does not change the finding.
- Inherits W1's defect #2 caveat (`Gamma_TradeAutopsy` 403-blind on option bars back to 09-02) —
  irrelevant here since this analysis uses realised `pnl_dollars`, not re-priced bars.
