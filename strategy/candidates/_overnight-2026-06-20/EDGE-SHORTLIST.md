# EDGE SHORTLIST — Overnight Mine 2026-06-20

> **Author:** overnight specialist (J asleep, SAFE autonomous authorization).
> **Status:** PROPOSALS ONLY. Nothing here touches live doctrine, `params*.json`, `heartbeat*.md`, `filters.py`, or `CLAUDE.md`. Each is a *testable* hypothesis with an exact backtest + kill criteria. Ratification path = OP-11 / OP-16 (OOS positive AND WF >= 0.70 AND sub-window stable AND anchor-no-regression AND A/B scorecard filed), shipped after-hours, J revokes.
>
> **What this is:** the top 8 highest-value, under-tested *trading-edge* hypotheses mined from the doctrine + (crucially) J's 667 real Webull fills — the richest, least-exploited ground truth Gamma owns. Ranked by `expected_edge_capture x feasibility`.

---

## Why these and not the 400+ candidates already cooked

The `strategy/candidates/` archive is ~400 files, overwhelmingly **bearish-rejection gates, VIX filters, exit-knob sweeps, and sniper level-break param tuning** on the *5m SPY synthetic* engine population. Two whole seams are nearly untouched:

1. **J's REAL fills (2021-2023, 667 SPX/SPY round-trips)** — `markdown/0dte/J-WEBULL-EDGE-2021-2023.md` + `J-LOSERS-STOPPED-THEN-PRINTED.md`. These are *real OPRA-anchored behaviour*, the strongest ground truth in the project, and L168 explicitly flags two findings as **"deserve an A/B, NOT yet applied"**: time-of-day and VWAP-side. Almost every cooked candidate ignores them.
2. **The ENTRY side.** C28 (L139,141,156,157) is unambiguous: exit tuning has diminishing returns once stop-rate > 70%; **research ENTRIES.** Most of the archive is exits/gates. The blueprint's #1 named gap (memory `project_chart_master_ta_layer`): the engine read trend from the ribbon, not price structure — `market_structure.py` (HH/HL/LH/LL/BOS/CHoCH) shipped 2026-06-20 but is **WATCH_ONLY, not yet an entry signal.** That is a live, un-mined entry edge.

Every hypothesis below is chosen to (a) attack an *unexploited* seam, (b) be falsifiable on existing data (`backtest/data/spy_5m_2025-01-01_2026-06-16.csv` + the real-fills validator), and (c) survive the 2026-06-20 guard battery: **L171 truncation cross-check** (same-strike chart-stop-only must not invert sign), **L172 random-entry-null** (must beat the null MAX, not just be positive), **C1 real-fills authority** (BS-sim is ranking-only), **OP-16 anchor-no-regression** (must not lose J's 4/29, 5/01, 5/04 winners or add his losers).

---

## The ranking

| # | Hypothesis | Seam | Exp. edge_capture | Feasibility | Score | Proposal |
|---|---|---|---|---|---|---|
| 1 | **VWAP-side alignment gate** (every J winner was on the correct VWAP side) | J real-fills | HIGH | HIGH (1 feature, existing data) | **9.0** | [H1](./H1-vwap-side-alignment-gate.md) |
| 2 | **Morning-shoulder (10:00) bleed gate** (OUR worst hour is 10:00 = -$4,937, not lunch) | OUR real-fills histogram | HIGH | HIGH (time feature) | **8.5** | [H2](./H2-morning-shoulder-bleed-gate.md) |
| 3 | **Market-structure BOS/CHoCH as an ENTRY signal** (ships WATCH_ONLY today) | entry structure | HIGH | MED (new entry path) | **7.5** | [H3](./H3-market-structure-bos-entry.md) |
| 4 | **Post-loss size/entry throttle** (J's whole loss = sizing-up; risk_gate has NO post-loss throttle — L168 code-gap) | J real-fills / risk | HIGH (loss-avoidance) | HIGH (sizing knob) | **7.5** | [H4](./H4-post-loss-throttle.md) |
| 5 | **Calls-vs-puts expectancy asymmetry** (J bull -$6/trade vs bear -$33; engine is bear-locked) | J real-fills / scope | MED-HIGH | MED (scope-lock interplay) | **6.5** | [H5](./H5-calls-vs-puts-asymmetry.md) |
| 6 | **Reversal-off-session-extreme** (2 of J's top winners; distinct from RIDE_THE_RIBBON) | J archetype | MED-HIGH | MED (new detector) | **6.0** | [H6](./H6-reversal-off-extreme.md) |
| 7 | **Pullback-resumption entry (don't chase fresh extremes)** (only 2/9 J winners hit a fresh extreme) | J archetype | MED | MED | **5.5** | [H7](./H7-pullback-resumption.md) |
| 8 | **Structural chart-stop, hold-past-first-poke** (J panic-sold at -42% median right before 67.9% continued) | exit / loss-rescue | MED | HIGH (exit knob, but C28 caveat) | **5.0** | [H8](./H8-hold-past-first-poke-chart-stop.md) |

**Score = expected_edge_capture (1-5) x feasibility (1-2) heuristic, normalized to 10.** Edge_capture estimate weights direct overlap with J's documented +$4,576 small-lot book and the -$17,461 sizing leak; feasibility weights data-on-hand + single-feature isolation + low anchor-regression risk.

---

## Top 3 (the ones to fire first)

1. **H1 — VWAP-side alignment gate.** J's single most universal winner trait: *every* trend/continuation/breakout winner entered on the correct side of session VWAP; the 2 reversal winners deliberately faded price extended *above* VWAP. This is a one-feature gate, trivially computable from existing 5m bars, and L168 explicitly green-lights it for an A/B. Highest edge-per-unit-effort in the project right now.

2. **H2 — Morning-shoulder (10:00) bleed gate.** L167 hands us the per-hour P&L histogram: OUR engine's worst hour is **10:00-10:59 (-$4,937, n=146)** — and the 09:35 entry gate fires straight into it, while **11:00 is the only solidly positive hour (+$1,526)**. This is the *data-validated* time gate (the lunch-trough folklore gate already FAILED, L167) — gate the hour that actually bleeds, with the histogram as the reproducer.

3. **H3 — Market-structure BOS/CHoCH entry.** The blueprint's #1 diagnosed gap: the engine reads trend from the lagging ribbon, not price structure. `market_structure.py` already detects HH/HL/LH/LL + BOS + CHoCH and is gym-validated (89/89) — but it only WATCHES. Promote a Break-of-Structure / Change-of-Character to an actual entry trigger and the engine finally trades the structure J reads by eye.

---

## Shared validation contract (every hypothesis inherits this)

Each proposal's "EXACT backtest" section is concrete, but all share this skeleton so nothing ships on a fake edge:

- **Data:** `backtest/data/spy_5m_2025-01-01_2026-06-16.csv` (5m SPY, IS) + VIX series; real-fills via the OPRA real-fills validator (`*_real_fills_validate.py`) for the top cell. J anchor scoring via `backtest/autoresearch/j_edge_tracker.py` (`J_WINNERS` 4/29,5/01,5/04 = $1542; `J_LOSERS` 5/05,5/06,5/07 = $725).
- **OOS split:** train <= 2026-Q1, hold out 2026-Q2 (and 2025 vs 2026 walk-forward where n permits). Per-month-normalized test/train >= 0.5 (L-playbook 4.6).
- **Mandatory guard battery (2026-06-20):**
  - **L171 truncation cross-check** — `backtest/lib/truncation_guard.py::cross_check_grid`: the chosen cell must NOT invert sign at the same strike with chart-stop-only (-0.99). A positive tight-stop number with a negative chart-stop-only number = REJECT.
  - **L172 random-entry null** — `backtest/autoresearch/null_baseline.py::null_gate`: signal per-trade must beat the null **MAX** (luckiest of 10 seeds, same count/side-mix/stop/strike), not merely be positive. `drop_top5_per_trade` must beat null mean.
  - **C1 real-fills authority** — BS-sim is ranking-only; WR/expectancy verdict comes from the real-fills validator on the top cell.
  - **OP-16 anchor-no-regression** — `edge_capture >= current baseline`; must not drop a J winner or add a J loser. Reject if `edge_capture < 771` (50% of max) regardless of aggregate.
  - **L167 time-gate discipline** (H2 specifically) — any time/seasonality gate must be justified by OUR per-hour P&L histogram, gate a genuinely negative window, and remove no anchor winner.
  - **C22 era-transfer caveat** — J's findings are SPX 2021-23; they are *hypotheses to test on SPY-now*, never auto-trusted. Every J-derived rule re-validates on the live SPY population first.
- **A/B scorecard:** `analysis/recommendations/{hypothesis_id}.json` with `edge_capture`, `top5_pct`, `quarter_pnl`, `positive_quarters`, `oos_per_trade`, `null_pass`, `truncation_pass`, `real_fills_exp`, `clears_bar`.
- **Cost:** $0 (pure-Python grinders, pythonw.exe per playbook §6.1). No LLM in the research loop (OP-3).

---

## Anti-patterns explicitly avoided (so we don't re-cook killed ideas)

- **NOT** another premium-stop sweep / exit-knob grinder (C28: exits are near-optimal; ~400 files already did this).
- **NOT** a lunch-trough time gate (L167: FAILED, removes near-breakeven fills and J's 5/01 anchor).
- **NOT** stairstep-continuation (RETIRED 2026-06-18, anti-J-edge, L-playbook).
- **NOT** raising/lowering `min_contracts` (L168: confounded — that's J's open question, not ours to resolve; H4 throttles *post-loss adds*, which is the un-confounded finding).
- **NOT** a cross-sectional/aggregate anomaly trusted as an option gate without causality + OOS sign-stability (L166).
- **Every** numeric claim ships with the OP-20 disclosure bundle (account-size scaling, concentration, regime sensitivity, failure modes).
