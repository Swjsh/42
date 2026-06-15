# Modes Sweep — fire instructions

Built 2026-05-08. Ready to run; waiting on J's signal.

## What it does

Runs the autoresearch loop independently for three starting points
(STRICT, BALANCED, AGGRESSIVE) and produces a side-by-side comparison
on a held-out validation window. Each mode evolves its own parameter set
within the SEARCH_SPACE; the setup STRUCTURE (filter list, trigger types,
exit doctrine) is invariant.

## What it tests

- Both directions: BEARISH_REJECTION_RIDE_THE_RIBBON and
  BULLISH_RECLAIM_RIDE_THE_RIBBON. Bullish trades now flow through the
  BS pricing sim (call pricing was added 2026-05-08; previously dropped).
- Per-mode parameter starting points:
  - STRICT — high min_triggers (3), tight stop (-5%), strict ribbon spread (40c),
    high VIX bar (18.0), restricted hours (10:30-13:00 + post-15:30 only).
    Expectation: few high-quality trades, higher WR, lower total P&L.
  - BALANCED — current production v14 defaults.
  - AGGRESSIVE — low min_triggers (1), wide stop (-15%), loose ribbon (20c),
    low VIX bar (16.0), trades any time after 09:35.
    Expectation: many trades, lower WR, higher total P&L if winners run.

## Train/validate split (overfitting guardrail)

| Window   | Range                       | Days   | Use                             |
|----------|-----------------------------|--------|---------------------------------|
| Train    | 2025-01-01 → 2026-02-13     | ~290   | Used for keep/revert decisions   |
| Validate | 2026-02-14 → 2026-05-07     | ~60    | Reported but NOT used to decide  |

A modification is KEPT only if (a) train sharpe improves AND
(b) validate sharpe doesn't drop more than 20% vs the validate baseline.
Otherwise REVERTED. Validate is the unbiased measure of the final winner.

## Honest baseline (what we're trying to beat)

BALANCED mode (= production v14 rules) on the master 16-month dataset
WITH bullish enabled:

| Window   | Trades | WR   | P&L     | Sharpe   |
|----------|--------|------|---------|----------|
| TRAIN    | 171    | 15%  | -$321   | -0.41    |
| VALIDATE | 59     | 24%  | -$57    | -0.24    |

Bullish setup is bleeding. Autoresearch needs to find a bullish-or-bearish
configuration that beats these honest numbers. Success criteria (J's words):
**higher WR AND higher P&L** on the validate window.

## How to fire

### Quick first pass (~1.5 hours, 10 iters per mode)

```powershell
.\setup\run-modes-sweep.ps1 -Iterations 10
```

### Recommended (~5 hours, 30 iters per mode)

```powershell
.\setup\run-modes-sweep.ps1
```

### Deep run (~8 hours, 50 iters per mode)

```powershell
.\setup\run-modes-sweep.ps1 -Iterations 50
```

### Resume an interrupted run (no reset)

```powershell
.\setup\run-modes-sweep.ps1 -Iterations 10 -NoReset
```

## What you'll get

- **Live log:** `backtest/autoresearch/_state/sweep.log`
  Tail it from another terminal to watch progress:
  ```powershell
  Get-Content C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\sweep.log -Wait -Tail 30
  ```

- **Per-mode state:** `backtest/autoresearch/_state/{strict,balanced,aggressive}/state.json`
  Final parameter set + final TRAIN baseline + final VALIDATE baseline.

- **Per-mode history:** `backtest/autoresearch/_state/{strict,balanced,aggressive}/history.jsonl`
  Every iteration: proposal, train metrics, validate metrics, keep/revert decision.

- **Summary:** `analysis/autoresearch_results.md`
  Generated at the end. Side-by-side table ranking all 3 modes by validate sharpe
  → P&L → WR. Names the winner. Lists which parameters changed per mode.

## Cost

Pure Python — zero LLM tokens. Plan budget unaffected.

CPU-bound on a single core. Approximate per-iteration time on the master
dataset is ~3-3.5 minutes (train + validate backtests). 30 iters × 3 modes
× 3.5 min = ~5 hours.

## Stop the run safely

Ctrl+C in the running terminal. State files are saved after every iteration,
so the run can be resumed via `-NoReset`.

## After the run

1. Read `analysis/autoresearch_results.md`.
2. Check the winner's validate metrics vs current production
   (171 trades, 15% WR, -$321 P&L on train; 59 trades, 24% WR, -$57 on validate).
3. Inspect the winner's `state.json` to see which parameters changed.
4. Cross-check `history.jsonl` for the KEEP rows that drove improvement —
   each lists the proposal, the metrics, and the delta.
5. **Do NOT auto-write to `automation/prompts/heartbeat.md`.** Operating
   principle 8: J reviews and approves before the live engine moves.
