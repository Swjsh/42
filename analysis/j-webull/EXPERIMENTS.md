# Ranked Fine-Tuning Experiments from the J-WeBull Re-Analysis (specs only — 2026-07-01)

> Constraint that shapes everything: **real OPRA fills exist only for 2025-26 SPY** (the
> rig's cache). There is NO 2021-23 intraday options data on the free tier (Plan-B memory),
> so J's exact historical entries can only be replayed with BS-synthetic pricing =
> **RANKING-ONLY per C1**. Anything promotable must be re-expressed as a detector on
> 2025-26 SPY and validated on OPRA real fills.

---

## E1 — J-entry-fingerprint detector on real OPRA fills (HIGHEST VALUE)

- **Hypothesis:** J's only positive-expectancy context — entry ≤0.1% from a prior-day level
  (PDH/PDL/PDC), VWAP-aligned, 1-2 lots, midday-weighted — is a portable setup, not a J-era fluke.
- **Inputs (all exist):** `spy_5m_2025-01-01_2026-06-16.csv` + VIX 5m + OPRA cache;
  fingerprint params from `traits.json → entry_fingerprint`.
- **Tool:** new detector module in `backtest/autoresearch/` (clone the
  `j_daily_pattern_ratify.py` harness shape) run through `lib.simulator_real` (real OPRA,
  causal next-bar entry, v15 exit stack) and scored by `backtest_design_swarm.py` canonical
  battery (expectancy + OOS + regime, NOT WR — OP-32).
- **Decision informed:** whether a J-fingerprint setup joins the validated-setups menu
  (both accounts trade it per arms-are-risk-profiles). Gate: OOS positive AND WF ≥ 0.70 AND
  anchor-no-regression AND A/B scorecard at `analysis/recommendations/`.
- **Runtime:** ~1-2 h build + minutes per sweep; overnight for the full battery.

## E2 — "J entries + machine discipline" counterfactual (RANKING-ONLY)

- **Hypothesis:** J's 59% directional read + v15 mechanical exits (chart-stop primary,
  −50% catastrophe cap, TP1/runner) + hard 2-lot cap flips his −$12,885 book positive.
- **Inputs:** `trades-normalized.csv` (entry ts + direction + strike/moneyness), SPY 5m cache
  2021-23 (here), BS-synthetic option pricing (the Kitchen's Plan-B path).
- **Tool:** small replay script reusing the BS-sim used by `engine_stress_swarm.py`;
  compare J-actual vs J-entries+v15-exits vs J-entries+v15-exits+2-lot-cap.
- **Decision informed:** how much of J's leak the CURRENT engine discipline already
  captures — sizes the remaining prize for entry-mining (if even machine exits can't make
  his entries positive, stop mining 2021-23 entries and keep engine triggers). ⚠ BS-sim →
  ranking evidence only, never a promotion gate (C1).
- **Runtime:** <30 min build, seconds to run.

## E3 — Trigger-coverage audit: do our detectors even fire where J made money?

- **Hypothesis:** the engine's validated triggers (BEARISH_REJECTION, vwap_continuation,
  BULLISH_RECLAIM) structurally MISS J's profitable cluster (midday 11:00-13:00, at-level,
  aligned continuation) — e.g. the 09:35 gate + morning-biased detectors.
- **Inputs:** context distribution of J's 235 winners vs 332 losers (`trades-normalized.csv`);
  the engine's fired-entry log on 2025-26 (`run_backtest` trade lists / funnel jsonl).
- **Tool:** distribution-overlap analysis (no per-trade join across eras): bucket engine
  entries 2025-26 by the same context features (tod, level-dist, vwap-side, range-pos) and
  measure share of engine entries inside J's positive-expectancy cells vs his bleed cells.
- **Decision informed:** whether to commission new midday/at-level detector families for the
  P1 discovery swarm; also flags if the engine currently concentrates in J's BLEED cells
  (e.g. 09:35 open window = his worst bucket).
- **Runtime:** ~1 h; pure pandas, $0.

## E4 — Entry-window weighting A/B (midday vs open)

- **Hypothesis:** blocking the empirically toxic windows (11:30, 13:30, ≥15:00) or
  midday-weighting improves the CURRENT production setups on real fills without regressing
  the OP-16 anchors (which are morning trades — tension to be measured, not assumed).
- **Inputs:** existing `run_backtest use_real_fills` grid; window knobs already in params
  (`entry gate` 09:35); J-priors from `traits.json → by_tod`.
- **Tool:** `run_backtest` sweep + `j-winner-audit` (anchor-no-regression) + A/B scorecard;
  small-n per bucket in J's data means the 2025-26 fills decide, J's data only seeds the grid.
- **Decision informed:** per-account entry-window params (Rule 9: ship any after-hours
  evening if the four auto-ratify gates pass).
- **Runtime:** hours (grid on cached OPRA).

## E5 — Guard validation: Rule 4 / day-after-red throttle evidence pack

- **Hypothesis (already evidenced here):** no-adds (Rule 4) is worth −$9,281 of J's loss;
  a day-after-red risk throttle (half size) is worth part of the −$90/day red-day drag;
  post-loss trade vetoes are NOT (his post-loss trades were fine — don't build that guard).
- **Inputs:** `traits.json → tilt / loss_streak_escalation / daily`; live `risk_gate`
  settings + fleet decisions.jsonl.
- **Tool:** `engine_stress_swarm.py` perturbation (add a synthetic "allow adds" variant to
  prove the guard's value on the REAL engine path); gym validator asserting the engine can
  never average down (graduated guard, `test_graduated_guards.py` style).
- **Decision informed:** keep/strengthen Rule 4 enforcement in `risk_gate`; whether to add a
  day-after-red position-size multiplier to params (A/B first).
- **Runtime:** stress swarm ~1 h ($0 free models); guard test <15 min.

## Explicitly NOT worth running

- **Post-loss cooldown timers** (fast re-entry after loss ≈ −$5.9/trade vs patient −$2.7 —
  the delta doesn't fund a guard).
- **Stop-after-2-daily-losses kill switch tightening** (saves only $2,246 across 3 years in
  his data; current per-account kill switches already dominate).
- **Fade/reversal-off-extreme detector mining from J's winners** (population expectancy
  −$37/trade; the 2 anchor fades were exceptions — C24).
