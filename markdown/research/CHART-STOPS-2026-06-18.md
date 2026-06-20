# Chart-stops as default — premium stop demoted to a wide catastrophe cap (2026-06-18)

**Status: SHIPPED on Safe. NO-SHIP on aggressive (regresses).** Market closed (Juneteenth) — legit doctrine window.

## What changed (Safe account only)

The BEAR-side premium stop was the PRIMARY exit (−10%). The 0DTE-options literature, Gamma's
lessons C2/C3, the missed_week backtest, and the blueprint all say fixed-% premium stops get
whipsawed by theta/vega/gamma on 0DTE. This change **demotes the premium stop to a wide −50%
catastrophe cap** and makes the **chart-level stop + ribbon-flip-back + profit-lock chandelier +
15:40 time stop** the primary invalidation.

| Param (`automation/state/params.json`) | Before | After |
|---|---|---|
| `premium_stop_pct_bear` | −0.10 | **−0.50** |
| `premium_stop_pct` (bull/generic) | −0.08 | **−0.50** |
| `premium_stop_multiplier` | 0.92 | 0.50 |

Heartbeat prose (`automation/prompts/heartbeat.md`) reordered: the Position-branch exit hierarchy now
leads with the chart stop / ribbon-flip / profit-lock as PRIMARY and labels the premium stop a
BACKSTOP; the broker disaster-stop bracket leg widened to `× 0.50`; the v15-ratification note marks
the prior −10% as superseded.

## Validation (real OPRA option fills)

Method: single-variable A/B via `autoresearch.runner.run_with_params(params, ...)` with
`use_real_fills=True` — the params-driven path that actually reaches the engine (raw `run.py` uses
orchestrator defaults, NOT params.json, so it was not used). Anchor via `j_edge_tracker.score_candidate`.
DSR/PSR via `lib.validation.gate.evaluate_candidate`. Window bounded by real OPRA coverage
(option CSVs end ~2026-05-29).

### Full-history real-fills (2025-01-01 .. 2026-05-29, n=26 trades)

| Config | n | WR | total P&L | edge_capture | DSR |
|---|---|---|---|---|---|
| A — current live (bear −10 / bull −8) | 26 | 38% | $8,160 | +$1,340 | PASS, PSR 0.993 |
| B1 — bear-only cap (−50 / −8) | 26 | 50% | $10,553 | +$1,340 | PASS, PSR 0.998 |
| **B2 — both cap (−50 / −50) — SHIPPED** | 26 | **65%** | **$16,671** | **+$1,340** | PASS, PSR 0.998 |

### Bear-stop sweep (n=17 bear trades) — shows tight stops whipsaw

| bear stop | premium-stop exits | bear WR | total P&L | bear P&L |
|---|---|---|---|---|
| −5% | 15 | 12% | $4,473 | $823 |
| −8% | 14 | 18% | $4,136 | $486 |
| −10% (live) | 10 | 41% | $8,160 | $4,510 |
| −15% (empirical peak) | 8 | 53% | $11,016 | $7,366 |
| −20% | 8 | 53% | $10,775 | $7,125 |
| −50% (shipped cap) | 5 | 59% | $10,553 | $6,903 |

### Decision gate (all PASS)

1. **edge_capture no-regression** — INVARIANT at +$1,340 across every stop width (−10 … −50). The bear
   stop never touches the J-anchor outcomes: J winners (4/29, 5/01, 5/04) ride to TP1/ribbon/time
   regardless; J losers (5/05, 5/06) are not taken (losers_added=$0); 5/07 = +$378 regardless.
2. **anchor no-regression** — confirmed (above).
3. **OOS P&L not materially worse** — B2 is +$8,511 BETTER (+104%), not worse.
4. **DSR advisory** — B2 PASS (PSR 0.998) ≥ A PASS (0.993).

### Knob-liveness proof (rules out the BS-sim-ignored-strike-offset class, OP-16 sim-accuracy gate)

`premium_stop_pct_bear` is a LIVE knob: at −2% both bear trades hit the premium stop (bear P&L −$71);
at −10%+ zero bear trades hit it (bear P&L +$1,188). The A==B result on the first narrow OOS run was
NOT a dead knob — it was that −10% already sits past the whipsaw cliff, so the premium stop already
never bound on bear winners in that window.

### Why −50% and not the −15% empirical peak

−15% is the single best total P&L ($11,016) but it is a narrow optimum on n=17 bear trades and risks
overfitting. A wide −50% cap is the blueprint's explicit "catastrophe cap" design: regime-agnostic,
within 4% of peak, and it makes the chart/ribbon/profit-lock exits unambiguously primary. J may tighten
to −15..−20% later — the full sweep is preserved in the scorecard.

## Aggressive account — NO-SHIP (regresses; C29/L149)

The same A/B on `aggressive/params.json` (ITM-2 strikes, 5.0x runner, looser gates → n=206 trades)
**regresses**: current bear −7% total $7,970; both −50% total $4,420; bear-only −50% total $365. The
aggressive bear-stop sweep is jagged and the current −7% is a sharp local optimum (−20% → −$9,026).
With ITM strikes + high trade frequency the tight premium stop is load-bearing (it cuts many small
losers before they run). **`aggressive/params.json` + `aggressive/heartbeat.md` LEFT UNCHANGED.** Bold
keeps bear −7% / bull −5%. This is the per-account honest outcome the validation gate demands.

## Revert path (Safe only)

1. `automation/state/params.json`: `premium_stop_pct_bear` → −0.10, `premium_stop_pct` → −0.08,
   `premium_stop_multiplier` → 0.92.
2. `automation/prompts/heartbeat.md`: restore the Position-branch exit block to premium-stop-primary
   (`entry × 0.90` bear / `entry × 0.92` bull) and the broker disaster-stop to `× 0.90` / `× 0.92`.
3. Backtest reads params.json directly, so step 1 reverts backtest behaviour too. Further fallback:
   `cp automation/prompts/heartbeat-v14-prod-backup.md automation/prompts/heartbeat.md`.

Scorecard (machine-readable): `analysis/recommendations/chart-stops-ab-2026-06-18.json`.
Validation script: `backtest/autoresearch/_chart_stops_ab_2026_06_18.py`.
