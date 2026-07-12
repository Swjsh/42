# FILL-BAR CONVENTION AUDIT — did T4/T5's bar-0 inclusion change any shipped decision?

**Date: 2026-07-11 (Sat evening). Verdict: NO — zero T5 verdict flips, both STOP-B ships stand (the floor is REINFORCED), the three kills stand byte-identically. One narrative correction: exit-C+entry-2's fresh-slice outperformance was a same-bar-TP1 artifact and its "strongest forward candidate" upgrade is evidence-revoked.**

Companion artifact: [`entry-exit-matrix-fillbar-audit-2026-07-11.json`](entry-exit-matrix-fillbar-audit-2026-07-11.json) (full per-trade numbers). Guard: [`backtest/tests/test_fill_bar_convention.py`](../../backtest/tests/test_fill_bar_convention.py).

---

## The finding being audited

`t4_exit_matrix._load_bars()` builds the exit-replay bar list with `ts >= entry_ts` — the **fill bar is included** and `replay()` checks its own high/low for stops/TP1. `lib/simulator_real.simulate_trade_real` — the fills authority every P5 cell, mass grind, and ship-gate was graded under — starts its walk at `entry_idx_opt + 1`: **fill bar excluded**, "min hold = one full bar." A P5-topcell real-fills confirm script (2026-07-11, separate session) found the convention **sign-flips** a trailing/zero-arm-threshold P5 cell (−$20.23/tr → +$25.62/tr). T4/T5 were already run and acted on (STOP-A sign-off → STOP-B disposition, 2026-07-09), so the question: **did the convention bias the specific tested candidates enough to change any verdict?**

## Why the mechanism is much narrower for T4/T5 than for the P5 cell

- T4/T5 shapes never set `profit_lock_arm_scope` → exit_manager default **`post_tp1`**: pre-TP1, bar-0 can only trigger the **premium stop** (bar-0 low) or **TP1** (bar-0 high). The trailing-HWM seeding that flipped the P5 cell (sim-parity `full` scope, zero arm threshold) cannot fire pre-TP1 here.
- Market-entry candidates fill at **bar-0's OPEN** → every bar-0 print is post-entry (no look-ahead); the divergence is purely a min-hold convention. And stops fill **at the stop level** frictionlessly, so a stop firing on bar 0 vs. later is P&L-identical unless bar-0's low was the *only* touch (dip-then-recover).
- TP1 at +150% on a 5-min bar-0: **0/18 fresh, 2/250 burned** — effectively unreachable.
- The one structurally unsafe combination: a **limit fill mid-bar** (entry-2) replayed against that same bar's full H/L — prints that may predate the fill (5-min bars can't order them) can credit a TP1 the trade never saw. That is look-behind, not min-hold.

## Method

Reproduce T5 layer (a) with the as-run loader, then re-run with the fill bar **excluded from management only** (entry premium unchanged = fill-bar open; `bars[1:]` = simulator_real parity). Entry-2's limit scan keeps the full bar list (an order legitimately lives during bar 0); only its exit replay starts one bar after the fill bar. Layer (b) anchors are reused verbatim from the published scorecard — they run on `exit_shape_parity_study` real 1-min bars and never touch `t4._load_bars`. Preflight verified both frozen inputs: fresh set sha16 `d10e1a3a51cbf155` ✓, burned set sha16 `b5e8931994b9d34b` ✓.

**Reproduction check: EXACT.** All six published layer-(a) numbers reproduced to the penny (control −$100.67; exit-A −$272.54; exit-B −$253.57; exit-C −$14.73; entry-1+control −$173.82; entry-1+exitA −$434.55).

## T5 verdicts under both conventions (layer b pinned to published anchors)

| candidate | layer (a) as-run (exp / Δ ctl) | layer (a) fill-bar-excluded | overall as-run | overall fixed | flip? |
|---|---|---|:--:|:--:|:--:|
| exit-A-wide-ride | −272.54 / −171.87 | **−272.54 / −171.87 (identical)** | FAIL | FAIL | no |
| exit-B-perband-hybrid | −253.57 / −152.90 | **−253.57 / −152.90 (identical)** | FAIL | FAIL | no |
| exit-C-paired-scalp | −14.73 / **+85.94** | **−138.26 / −37.59** | INCONCLUSIVE_NO_ANCHOR | INCONCLUSIVE_NO_ANCHOR | no |
| entry-1+control | −173.82 / −73.15 | **−173.82 / −73.15 (identical)** | FAIL | FAIL | no |
| entry-1+exitA | −434.55 / −333.88 | **−434.55 / −333.88 (identical)** | FAIL | FAIL | no |

Per-trade diffs: **0/18, 0/18, 0/11, 0/11 trades changed** for the four market-entry candidates — in the fresh window's zero-recovery bleed, every bar-0 stop touch was re-touched later at the same fill level (control bar-0 −20% touches: 9/18; exit-A −50%: 4/18 — all re-touched). exit-C: **3/11 changed**, two of them sign flips.

## The exit-C mechanism, quoted (why its fresh-slice edge was an artifact)

- **2026-06-22 P** — signal open $1.07, limit fills at $0.963 *on the way down* (fill bar 10:55 o=1.07 h=1.45 l=0.74 c=0.81). As-run credits TP1 at +50% off that bar's $1.45 high; **post-fill-bar MFE is −5.5%** (the premium never again came within 5.5% of the fill). As-run **+$439.1** → excluded **−$337.1** (rides to the −35% stop).
- **2026-06-25 P 12:45** — fill $0.738; fill-bar high $1.14 (+54.5%); **post-fill-bar MFE +22.0%** — TP1 never reachable after the bar. As-run **+$341.4** → excluded **−$258.3**.
- 2026-07-06 C — fill-bar high +53.4%, but the trade ran to +291% MFE afterwards anyway: +$174.2 → +$191.2 (immaterial).

Strictly: on 5-min bars the intrabar order is unknowable — the high *could* have printed post-fill. But both big flips required the +50% print to land in the minutes after a fill that price never revisited, on bars that closed near their lows. The honest label is **unreliable, biased toward phantom TP1 credit** — exactly the "1m-close timing owed" disclosure, at its sharpest on limit fills. The hazard note is now on `t5.replay_entry2_pair` itself.

## Burned population (the STOP-A / T3 / T4 evidence base), both conventions

| number | as-run (published) | fill-bar-excluded | note |
|---|--:|--:|---|
| control full pop (n=250) | **$22.91** | **$35.54** | +$12.63 — matches the STOP-A Fable-addendum probe exactly (independent cross-validation) |
| control at floor $0.30 (n=157) | **$36.62** | **$54.41** | |
| **floor lift** | **+$13.71** | **+$18.87** | the shipped entry-1 decision gets STRONGER under the corrected convention |
| exit-A full pop | $42.99 | $43.03 | leaders ≈ immune (bar-0 −50% touch: 11/250) |
| exit-B full pop | $42.32 | $42.34 | |
| entry-1+exitA (floor subset) | $60.05 | $60.05 | |

Bar-0 −20% stop touches on the burned window: **113/250 (45%)** — the convention is genuinely load-bearing for tight-stop absolute numbers (control's expectancy is understated ~$12.63/tr by first-5-minute noise, consistent with the T2 noise-floor finding). It did **not** distort any decision because every decision compared shapes under the *same* convention, and the decisive layer (real-fills anchor) is convention-immune.

## Decision-by-decision disposition

1. **KILLS (exit-A, exit-B, entry-1+exitA)** — stand, byte-identical layer (a). ✅ no re-litigation needed.
2. **SHIP: entry-1 premium floor $0.30** — stands, REINFORCED (floor lift +$13.71 → +$18.87; anchor evidence untouched). ✅
3. **SHIP: vwap_continuation fleet-shape port** — never exposed: its gate (`vwapcont-exit-ab-ship-gate.json`) states `fills_authority: lib.simulator_real.simulate_trade_real`, the fill-bar-EXCLUDING authority. ✅
4. **STAYS SHADOW: entry-2/exit-C** — decision unchanged (it didn't arm), **but the STOP-B line "the ONLY candidate that beat control on the fresh slice... strongest forward candidate" is evidence-revoked**: under sim parity it *underperforms* control (−$138.26 vs −$100.67). T6 paper A/B should inherit a NEUTRAL prior on the pair, not an upgraded one; its real evidence remains the T3 net-of-misses grid (convention-shared) + the forward shadow ledger (real fills, artifact-free).

## Convention judgment (which is "right")

Neither, universally — **as-run (include bar 0) is closer to the live 1-min exit actuator for market entries** (it can and does act inside the first 5 minutes); **simulator_real's skip-a-bar is the ratified-population convention** (P5 cells, grinds, ship-gates). Both are legitimate; **mixing them silently is the failure mode** (T4's P5-survivor gate column compares across conventions — quantified here as immaterial for the shapes compared, ≤$0.65 on the wide shapes). Resolution shipped: disclosure blocks at every point of use + `test_fill_bar_convention.py` pinning both sides, so any future change REDs and forces a conscious re-audit. `t4._load_bars` semantics deliberately **unchanged** — published T3/T4/T5 artifacts stay reproducible, and other sessions' in-flight work isn't pulled out from under them.

## Follow-ups (owed, not blocking)

- `vwapcont_entry_exit_matrix.py` (the owed vwap matrix, pre-registered) shares the `>=` + `fill_idx:` pattern — its 4 **limit-entry probe cells** carry the same look-behind hazard; its market-entry cells are near-immune per this audit. Its §4 parity check vs simulate_trade_real covers the control cell; extend the sensitivity to one limit cell before reading the entry-probe results.
- 1-min-close stop timing on live data remains the standing owed item that subsumes this whole class.
