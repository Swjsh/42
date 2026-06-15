# Autoresearch + Darwinian + JANUS — build summary

> Built 2026-05-08. Inspired by Karpathy's autoresearch and ATLAS-GIC's
> JANUS / Darwinian agent layers. Adapted for Gamma's 0DTE SPY
> directional-options strategy.

## Status

| Module        | LOC | Tests | Status                             |
|---------------|-----|-------|------------------------------------|
| autoresearch  | 5 files | 27 | smoke-tested, ready for nightly use |
| darwin        | 2 files | 14 | builds + applies, not yet wired to live |
| janus         | 1 file  | 15 | builds + applies, not yet wired to live |

Total: 117 tests pass (vs 76 before this work).
Full backtest test suite still green; no regressions.

## Data prerequisites

Master training set: `backtest/data/spy_5m_2025-01-01_2026-05-07.csv`
(SPY+VIX 5-min, 30,389 SPY bars, ~340 trading days = 16 months).

Built via:
```powershell
python tools/extend_data_v2.py --start 2025-01-01 --end 2025-05-31
python tools/extend_data_v2.py --start 2025-06-01 --end 2025-12-31
python tools/merge_data.py --start 2025-01-01 --end 2026-05-07
```

To extend further back (Alpaca IEX feed supports ~5y of history):
```powershell
python tools/extend_data_v2.py --start 2024-01-01 --end 2024-12-31
python tools/merge_data.py --start 2024-01-01 --end 2026-05-07
```

## Performance optimisation

`lib/orchestrator._compute_htf_15m_stack` was O(n) per call → O(n²) over a
full backtest. Replaced with `_precompute_htf_15m_stacks` (vectorised
searchsorted + per-15m-bar cache). Result: a 16-month baseline runs in
~3 minutes instead of ~20 minutes. Live engine code is unaffected
(heartbeat doesn't use the backtest orchestrator).

---

## 1. Autoresearch loop

**Pattern (Karpathy → Gamma):**

| Karpathy            | Gamma                                   |
|---------------------|-----------------------------------------|
| modifies `train.py` | modifies one filter parameter value     |
| 5-min GPU run       | one backtest over training window       |
| validation loss     | trade Sharpe ratio on training window   |
| `git commit/revert` | `state.json` keep/revert + JSONL log    |

**Files:** `backtest/autoresearch/{config,metrics,proposer,runner,decider,state,loop}.py`

**State files (auto-created):** `backtest/autoresearch/_state/{state,history}.{json,jsonl}`

**Run one iteration:**
```powershell
python -m autoresearch.loop --iterations 1 --start 2025-01-01 --end 2026-05-07
```

**Run a nightly batch:**
```powershell
python -m autoresearch.loop --iterations 10
```

**Inspect status without running:**
```powershell
python -m autoresearch.loop --status
```

**Reset to production defaults:**
```powershell
python -m autoresearch.loop --reset --iterations 1
```

### What the proposer does

Round-robin through 13 parameters in `config.SEARCH_SPACE`; for each,
proposes adjacent-step modifications (e.g. `f9_vol_mult: 0.7 → 0.8`).
Skips parameters modified within the last 3 iterations (cooldown).

### What the decider does

Computes new Sharpe + WR + W/L + max DD vs baseline. Returns KEEP iff:
- Sharpe improved, AND
- All hard gates pass (≥20 trades, ≥40% WR, ≥1.20 W/L, expectancy>0,
  max DD not regressing >1.5x).

Otherwise REVERTS — `state.json` is unchanged, only `history.jsonl` grows.

### Smoke-test result

16-month baseline (2025-01-01 → 2026-05-07):
- 81 trades, 56% WR, $2,598 P&L, Sharpe 3.48, max DD -$614

Iteration 1 tested `f9_vol_mult: 0.7 → 0.8`. Sharpe dropped 0.748 → REVERT
(as expected — v14 production rules are already well-tuned).

### How to wire into the daily lifecycle

Add an EOD task that runs N iterations after market close:

```powershell
# setup/scripts/run-autoresearch.ps1
& C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe `
    -m autoresearch.loop --iterations 5 `
    --start 2025-01-01 --end 2026-05-07 `
    >> automation/state/autoresearch.log 2>&1
```

Register via `Register-ScheduledTask` after `Gamma_DailyReview` (16:30 ET).
Each iteration takes ~3 min on the 16-month dataset; 5 iters = ~15 min.
**Cost:** zero LLM tokens — pure Python backtest loop.

### When KEEPs happen

`state.json.current_params` updates and the next morning the heartbeat
should be regenerated to reflect the new values. **Right now this is
manual** — see "Wire-up steps" below.

---

## 2. Darwinian filter weights

**Pattern (ATLAS → Gamma):**

| ATLAS                                      | Gamma                            |
|--------------------------------------------|----------------------------------|
| 25 agents with weight 0.3-2.5              | 13 filters (bear+bull setups)    |
| Top quartile ×1.05, bottom quartile ×0.95  | Same multipliers                  |
| Daily Sharpe-based ranking                 | Per-trade contribution attribution |

**Files:** `backtest/darwin/{scorecard,weights}.py`

**State files:** `backtest/darwin/_state/{scorecard,weights}.json`

**Usage:**
```python
from darwin.scorecard import FilterScorecard
from darwin.weights import FilterWeights, update_from_scorecard

sc = FilterScorecard.load_or_new()
sc.update_from_backtest(trades, decisions)   # walk a backtest result
sc.save()

fw = FilterWeights.load_or_new()
changes = update_from_scorecard(fw, sc)
fw.save()
print(changes)  # {filter_id: (old_weight, new_weight, reason)}
```

### Three usage modes

1. **ANALYTICS** (default, low-risk) — surface weights in
   journal/dashboard. Identifies low-confidence filters quickly.
2. **PROPOSER BIAS** (medium-risk) — autoresearch proposer biases
   toward modifying low-weight filters first. Faster convergence.
3. **WEIGHTED ENTRY** (high-risk) — replace `bear_score >= N` with
   `weighted_setup_score(passing) >= threshold`. Requires careful
   threshold calibration; not active by default.

### How to wire into autoresearch

In `autoresearch/proposer.py`, add after the candidate list construction:

```python
from darwin.weights import FilterWeights, low_weight_filters
fw = FilterWeights.load_or_new()
priorities = low_weight_filters(fw, threshold=0.7)
# Move proposals targeting low-weight filters to the front
options.sort(key=lambda o: 0 if o[0] in priorities else 1)
```

This is a 6-line patch — purposely left out for the initial build so the
proposer's behaviour stays simple and predictable until darwin has been
exercised over a few hundred backtest runs.

---

## 3. JANUS two-window regime detector

**Pattern (ATLAS → Gamma):**

| ATLAS                                  | Gamma                                  |
|----------------------------------------|----------------------------------------|
| 2 cohorts (18-month vs 10-year)         | 2 windows (10-day vs 60-day)            |
| Weight differential = regime signal    | Sharpe differential = regime signal    |
| NOVEL/HISTORICAL/MIXED                 | Same three states                       |

**Files:** `backtest/janus/detector.py`

**State files:** `backtest/janus/_state/regime.json`

**Usage:**
```python
from janus.detector import detect, save_regime, trades_to_daily_pnl

daily = trades_to_daily_pnl(trades)
sig = detect(daily, recent_window_days=10, baseline_window_days=60,
             divergence_threshold=0.5)
save_regime(sig)

print(sig.regime)                 # NOVEL_REGIME | HISTORICAL_REGIME | MIXED
print(sig.threshold_adjustments)  # heartbeat overrides if regime != MIXED
```

### Threshold adjustments per regime

| Regime           | min_triggers (bear) | min_triggers (bull) | spread bonus | size mod | max trades/day |
|------------------|---------------------|---------------------|---------------|----------|----------------|
| NOVEL_REGIME     | ≥2                  | ≥3                  | +5¢           | 0.5      | 1              |
| HISTORICAL_REGIME| 1                   | 2                   | 0             | 1.0      | unbounded      |
| MIXED            | 1                   | 2                   | 0             | 1.0      | unbounded      |

These are **suggestions**, not auto-applied. The heartbeat would read
`automation/state/regime.json` and apply per operating principle 8 (no
deferral, no fallback to manual — but also no live rule changes during
market hours per principle 9).

### How to wire into the daily lifecycle

Add to the EOD-summary task (16:00 ET) before it generates tomorrow's bias:

```python
# automation/scripts/compute_regime.py
import sys; sys.path.insert(0, "backtest")
from janus.detector import detect, save_regime, trades_to_daily_pnl
import pandas as pd
trades_df = pd.read_csv("journal/trades.csv")
# convert to TradeFill-compatible objects... or compute daily directly
sig = detect(daily_pnl_dict)
save_regime(sig, path="automation/state/regime.json")
```

Then in `automation/prompts/heartbeat.md` add a one-line instruction:

> If `regime.json` shows NOVEL_REGIME, use its `threshold_adjustments`
> as soft floors — i.e. raise `min_triggers` to its values, halve qty.

---

## Wire-up checklist (NOT yet done)

These are the deliberately-deferred integrations. None are required for
the modules to function standalone.

- [ ] `setup/scripts/run-autoresearch.ps1` + Task Scheduler entry
       (`Gamma_Autoresearch` after EOD-summary, 5 iterations)
- [ ] `setup/scripts/run-darwin-update.ps1` to refresh weights weekly
       from `journal/trades.csv` outcomes
- [ ] `automation/scripts/compute_regime.py` invoked in EOD-summary
       prompt; writes `automation/state/regime.json`
- [ ] `automation/prompts/heartbeat.md` reads `regime.json` and applies
       `threshold_adjustments` as soft floors
- [ ] `dashboard/` panel showing current regime + filter-weight heat map
- [ ] `analysis/recommendations-log.jsonl` ingestion of autoresearch KEEP
       events (as R-AR-NN entries)
- [ ] One full overnight run of 20-30 autoresearch iterations to verify
       convergence behaviour, with the resulting parameter set reviewed
       before any production write-back

## Cost analysis

All three modules are pure Python — no LLM calls in the loops.
- Autoresearch: ~3 min per iteration × 10 iters/night = 30 min CPU/day
- Darwin: <1 second per update
- JANUS: <100ms per detection

This fits inside operating principle 3's $100/mo Max 5x plan budget
trivially because nothing here consumes Claude tokens.

## Honest limitations

1. **No counterfactual P&L for blocked trades** — the Darwinian scorecard
   counts pass/fail credit on entered trades, but cannot attribute
   block credit without re-running the backtest with each filter
   disabled. The infrastructure is in place (`update_from_counterfactual_replay`
   stub) but not implemented yet.

2. **Single-knob proposer** — the proposer modifies one parameter at a
   time. Multi-parameter interactions (e.g. tighter `f9_vol_mult` paired
   with looser `min_triggers`) won't be discovered. Karpathy's loop has
   the same limitation; it's a known trade-off for tractability.

3. **Sharpe-only loss function** — Sharpe is sample-noisy on small trade
   counts. The `min_trades=20` hard gate mitigates this but a 16-month
   training window with 81 trades is still in the noise zone for some
   moves. Annualized Sharpe of 3.48 is suspiciously high — backtest
   probably overfits the rule set tested on the same window the rules
   were tuned on (operating principle 2: this is one piece of evidence,
   not n≥10 paper observations).

4. **No live rule write-back yet** — the autoresearch loop updates its
   internal `state.json` but does NOT modify `automation/prompts/heartbeat.md`
   automatically. This is intentional. Operating principle 9 ("goal is
   autonomous execution, full stop") points toward eventual auto-write,
   but principle 8 ("no deferral... ASK J") means the wire-up needs J's
   approval before code starts editing live production prompts.

5. **JANUS regime adjustments are recommendations only** — the heartbeat
   doesn't read `regime.json` yet. Wiring this up is a separate change
   that needs to be backtested itself (does NOVEL_REGIME tightening
   actually improve out-of-sample Sharpe?).
