# Bull Requalification — 2026-07-22 (the owed OP-16 re-eval, run at ATM)

> CLAUDE.md OP-16: bull "stays enabled pending honest re-eval at n>=20 under SS-B + corrected
> strike tier" — that re-eval had never been run at ATM. This is it. Full evidence table:
> [`bull-requalification-2026-07-22.json`](bull-requalification-2026-07-22.json). Census of every
> bull gate + mirror-parity facts: [`MIRROR-PARITY-AUDIT-2026-07-22.md`](../../markdown/audits/MIRROR-PARITY-AUDIT-2026-07-22.md).
> Pre-registered method (frozen before any replay ran): [`bull-requalification-prereg-2026-07-22.json`](bull-requalification-prereg-2026-07-22.json).

## Verdict summary

| Gate | n (best evidence) | Verdict | Basis |
|---|---|---|---|
| `block_elite_bull` (Safe) | 30 (decision-log mining, ATM+SS-B) | **KEEP** | Total +$665.60 but drop-top-1 flips to **-$1,420.80**; WR 16.7%; top3-day = 580.8% of net. Concentrated, not a real edge. |
| `block_bull_1100_1200` (Safe) | 1-2 | **RETEST-INSUFFICIENT-N** | Gate fires too rarely (1-2 events in 2 months) to grade either way at any strike/exit. |

**Both gates' original 2026-06-18 verdicts SURVIVE requalification under current config** — not
because the old evidence was trustworthy (it wasn't: wrong strike, wrong exit shape, disclosed as
STALE in the companion audit), but because three independent current-config measurements agree:

1. **Backtest re-detection at ATM** (2026-05-21..07-17, 5-min-bar cadence): `block_elite_bull`
   added-cohort n=9, total **-$1,720.50** — too small to grade against the n≥20 floor, but the
   sign agrees with everything below.
2. **Decision-log mining at ATM** (2026-06-25..07-17, live 1-min-tick cadence, n=30): total
   **+$665.60**, but drop-top-1 (removing the single largest winner) flips it to **-$1,420.80** —
   fails the stability bar. WR 16.7% (5 wins / 30).
3. **Raw current-config real fills** (all 6 fleet arms, engine-attributed, since SS-B shipped
   2026-07-09): **n=24, WR 0%, total -$885.00.** n=24 ≥ 20 — the OP-16 evidence-n bar is MET on
   this number alone. Core Safe specifically (ATM-confirmed since 2026-07-11): n=8, all losers,
   -$312.00.

## Reconciling the prior evidence

- **`block-elite-bull-ssb-revalidation.json` (2026-07-10):** already applied SS-B exit shape but
  used **strike_offset=-2 (OTM-2)**, explicitly pinned in its own pre-registration as a
  continuity choice, not an ATM test. n=28, total **-$3,873.60**, WR 28.6%, drop-top-1 still
  negative, verdict KEEP. **This requalification's window overlaps that study's window almost
  entirely (2026-05-21..07-10 vs today's 07-17 extension) and agrees in every qualitative respect**
  (low WR, one/two huge days carrying the cohort, drop-top-1 negative, verdict KEEP) — the ATM
  correction changed the dollar magnitude, not the conclusion.
- **`bull-unblock-elite-replay-2026-06-30.json`:** OLD exit shape, OTM-2, n=7, -$241.26. Superseded
  by the SS-B study above; not re-litigated.
- **`bold-strike-axis-2026-07-15.json`:** Bold-account ATM-cell A/B, disjoint account/VIX-band/
  equity scope from this Safe-only study. No shared cohort, no direct comparison possible; flagged
  in the census as a Bold-side open gap (Bold's `block_elite_bull` has never been revalidated at
  any exit shape).

No contradiction to explain away — every current-config measurement, by every method tried,
lands in the same place: **the ELITE bull level_reclaim cohort is a low-win-rate, day-concentrated
population that a couple of big trend days keep near breakeven-to-negative, at ATM exactly as it
was at OTM-2.**

## Too-good / too-bad discipline (both directions checked)

- The decision-log-mining ATM total (+$665.60) is smaller in magnitude and a different sign than
  the OTM-2 SS-B total (-$3,873.60) on an overlapping window — flagged and hunted per this study's
  own pre-registered discipline clause. Conclusion: **not a flip** — the pass-bar's own drop-top-1
  condition catches it (fails), and the underlying shape (WR 16.7%, top3-day 580.8% of net) matches
  the OTM-2 study's shape (WR 28.6%, one dominant 07-09 day) closely enough to be the same
  phenomenon at different leverage, not a different phenomenon.
- The raw-fills 0% WR (n=24) is extraordinary in the *losing* direction — hunted explicitly (see
  the JSON's `too_good_hunt_bad_direction` block): partially explained by shared-signal
  duplication across fleet arms (n=24 is an upper bound on independent trials, not a clean
  count) and day-concentration (3 dates drive the safe-2 losses). Real, not a data bug
  (cross-checked against `fills-ledger.jsonl`), but should not be read as "bulls always lose" —
  read as "no winning bull fill yet under the current exit shape, small and correlated sample."

## What this does NOT conclude

No gate was unblocked. `block_elite_bull` and `block_bull_1100_1200` stay armed as-is —
KEEP and RETEST-INSUFFICIENT-N are both "do not change" verdicts under this study's own frozen
pass bar. Bold's `block_elite_bull` (VIX[15,18) band) was never in scope here and remains
un-revalidated at any exit shape — the clearest remaining gap, not addressed this session.

## Method, in one paragraph

Two new tools (`backtest/tools/bull_gate_atm_ssb_requalification.py`,
`backtest/tools/bull_elite_atm_decision_log_mining.py`), 100% local-cache, zero broker/Alpaca
imports (verified via import graph, not just runtime behavior). Signals detected via
`run_backtest(use_real_fills=True, strike_offset=0)` (backtest-detection) and by mining
`core-decisions.jsonl`'s `SKIP_ELITE_BULL_LEVEL_RECLAIM`/`SKIP_BULL_1100_1200` rows
(decision-log mining) — added-cohort method (trades present when the gate is OFF but not when
ON) isolates exactly what each gate removes. Every trade's EXIT was then re-walked through the
REAL production exit_manager (`backtest/lib/exit_manager_walk.py#walk_exit_manager`) at the
live-shipped `RIBBON_RIDE` SS-B shape (`automation/state/fleet/strategies.py`), not the
known-divergent `simulate_trade_real` every prior sim study used for its P&L. Guard tests:
`backtest/tests/test_bull_requalification_2026_07_22.py`, **12 passed** (pure-function grading-
ladder + stats-helper guards; fresh run this session).
