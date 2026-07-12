# PROFITABILITY DEEP-RESEARCH — synthesis of 5 parallel streams (Fable, 2026-07-11)

> J's ask: "deep-research my project and ways to improve it to make it profitable."
> Method: 5 scoped Sonnet streams (ledger forensics · participation cost · external mechanisms ·
> friction budget · dormant assets), each with honesty rails, synthesized here. Stream reports:
> `analysis/deep-research/2026-07-11-*.md` + `markdown/research/EXTERNAL-0DTE-MECHANISMS-2026-07-11.md`.

## The headline

**The engine loses through ONE dominant channel, and every link of it already has a
validated or shipped fix in-house.** Real fills 2026-06-26→07-09: engine **-$1,699 over 109
episodes** (J's 3 manual trades: +$274). The loss decomposes as a single multiplicative chain:

```
far-OTM strikes (2x the friction of ATM — measured, 146K decay observations)
  × -20% premium stops reading spread noise (86% of ALL exits; median losing hold: 3 MINUTES)
  × morning entries (34/34 losers in-window)
  = -$1,699 / 9 days
```

Not five problems. One chain, three links.

## Why this is good news (no oversell — the evidence is the reason)

Each link's fix already exists at some stage of validation:

| Link | Fix | Evidence state |
|---|---|---|
| Premium-stop noise deaths | **SS-B chart-stop-primary** | SHIPPED on core 07-09/10 — but the forensics window is almost entirely PRE-SS-B, so its live effect is UNPROVEN (0 fills since). The 4 fleet arms still run -20% premium stops — the channel stays open at volume until they're migrated. |
| Far-OTM friction | **Strike-tier shift (OTM-2 → ATM/ITM-2)** | The identical OTM→ITM gradient was already proven on real P&L for 5 sibling setups (WP5-STRIKE-AB) and shipped — core `ribbon_ride` never got it. Friction math: affordable NOW at $1.7K equity (68% of ceiling), no rule change needed. |
| Morning bleed | **Time-of-day gate** | 34/34 in-window losers + external practitioner convergence — but the window is 9 days with VIX pinned. Needs the full-history pre-registered test before it ships. |

## What the research KILLED (kills are deliverables)

- **Broad gate relaxation** — the counterfactual replay says the gates were mostly RIGHT.
  block_bull_1100_1200's two live blocks net **-$157** if taken. Participation is bounded by
  premium floor + settled-KEEP gates + hard doctrine (54.7% of blocker-events), not accidental
  gates. The path to more participation is the probe arm's forward evidence, not loosening.
- **GEX/dealer-gamma as a standalone build** — the most rigorous study found its signal
  collapses to noise once VIX + ATM IV are controlled. Test later only as "beyond-VIX," never
  as a standalone edge. (Saved a build.)
- **NLWB** — real-fills gate FAILED 2026-05-21 (WR 47.8%, -$1,294); the remembered "71% WR" was
  a scan proxy. Stays dead.
- **T-W8 headroom/retest** — ran 07-09: 0 PASS / 10 FAIL / 2 INCONCLUSIVE. Closed.
- **3-contract-minimum as a suspect** — it's SLACK (27% of affordability ceiling used), not
  binding. Rule 6 needs no change.

## Doctrine corrections (filed with this synthesis)

1. **CLAUDE.md OP-16 mislabel**: "Bull is net-positive on real OPRA fills (+$5,586 / 56% WR)"
   traces to `chef-bull-scope-ab` — a **simulated backtest**, not broker fills. Live paper
   fills to date: bull n=80, WR 1.2%, -$1,573 (9-day window, VIX pinned — small-n, labeled).
   Correction shipped to CLAUDE.md + CHANGELOG this session. Direction stays enabled; the honest
   re-evaluation point is n≥20 bull episodes under the corrected exit/strike shape.
2. **`spread_cents` in decision ledgers is the SPY EMA-ribbon spread, NOT option bid-ask** —
   flagged before it contaminated friction analysis. No NBBO history exists anywhere in the
   repo; `bid_ask_spread_max_cents: 8` is a confirmed dead knob (zero consumers, in the
   KNOWN_DEAD test allowlist). → NBBO capture is now a first-class work item (below).
3. **queue.md statuses drift from reality** (3 tickets found stale vs their own artifacts).
   Two closed this session with artifact citations.

## The ranked plan (expected $ × probability ÷ effort)

1. **P1 — Fleet exit-shape parity.** Per-arm exit_manager replay of SS-B vs the arms' current
   -20% premium stop (C29: exit knobs never transfer across tiers/arms without independent
   verification). If it clears per-arm: migrate arms. This closes the 86%-of-exits channel at
   volume. *Kill criterion: any arm where SS-B replays worse on its own fills keeps its shape.*
2. **P2 — Strike-tier A/B for core `ribbon_ride` (OTM-2 → ATM/ITM-2).** WP5's scorecard
   machinery, pointed at the ribbon_ride cohort. Clears → v15.4 weekend rule update with
   scorecard attached (auto-ratify path if OOS+WF+stability pass). *Kill: gradient doesn't
   reproduce on this setup's cohort.*
3. **P3 — Morning-session gate, pre-registered, full OPRA history.** Frozen registration
   BEFORE the run; the 9-day 34/34 is the hypothesis source, so that window is excluded from
   evaluation (no peeking). *Kill: full-history expectancy delta ≤ 0 or nulls survive.*
4. **P4 — NBBO capture at decision time.** Persist option bid/ask/mid for the chosen contract
   on every decision row + entry/exit event. Unblocks ALL future friction/exit research and
   revives the dead liquidity knob with real data. Pure additive telemetry.
5. **P5 — Expected-move/VIX1D gate, pre-registered.** The one external mechanism that
   survived: compute session expected range from the morning ATM straddle (free, from our own
   Alpaca chain); skip signals whose target-to-cost math can't clear it. *Kill: no expectancy
   lift over the existing VIX gates.*
6. **Running already:** FDR-16 real-fills confirmation (16 BH-FDR survivors, top n=1,318, NEW
   `level_rejection` family) + P5 top-cell confirm — sequential crew on the OPRA cache now.
   Probe-arm dead-wiring fix in flight (forward participation evidence starts accruing when it
   lands).

## What this does NOT promise

9 days of fills, one VIX regime, zero surviving positive cohorts — nothing here claims an
edge exists yet. What it claims: the measured loss mechanism is specific, the fixes are
cheap-to-verify, and the verification machinery (replay, scorecards, probe arm, twin) is
built. Monday's tape starts producing forward evidence on SS-B core; the plan above converts
the rest from "shipped/plausible" to "measured" or kills it.

## Instruments that auto-report progress (no memory dependence)

- Fill funnel + firm brief (daily) — SS-B live behavior, probe-arm entries
- `Gamma_FreeModelAudit` (every-other-day) — veto-gate trust trajectory
- Per-item scorecards in `analysis/recommendations/` — P1/P2/P3/P5 verdicts as they land
- STATUS.md dated entries per ship — the audit trail
