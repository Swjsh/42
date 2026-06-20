# SHOTGUN_SCALPER Grinder — Integration Gap (Discovered 2026-05-15 Evening)

> **Status:** BLOCKING. Grinder runs end-to-end without errors but fires zero trades on all 8 anchor days. Smoke test exit code 0 — silent failure mode.
> **Estimated fix:** 1–2 hours of focused work. Targeted for Saturday morning.

## Root cause

The detector (Agent A's output) and grinder (Agent B's output) were built in parallel with different API contracts that nobody reconciled before the smoke test:

**Detector signature** (`lib/watchers/shotgun_scalper_detector.py::detect`):
```python
def detect(
    today_bars: pd.DataFrame,
    today_bar_idx: int,
    levels: list[dict],
    ribbon: dict,         # {fast, pivot, slow, spread_cents, stack}
    vix: float,
    htf_15m_stack: Optional[str],
) -> Optional[dict]: ...
```

**Grinder call site** (`backtest/autoresearch/shotgun_scalper_grinder.py::run_shotgun_day` line 528):
```python
signal = detect(
    bar=bar,           # ← wrong kwarg name
    bar_idx=bar_idx,   # ← wrong kwarg name
    bars=combined,     # ← wrong kwarg name
    params={ ... },    # ← detector doesn't take params; expects 4 separate args
)
```

The detector silently rejects unknown kwargs via Python's strict kwargs check → throws TypeError → grinder catches it in a bare `except Exception: continue` block → no trade fires → grinder reports 0 trades → smoke test reports "no regressions found" because the floor gates are all "did at least one trade fire" gates.

## Two-layer fix needed

### Layer 1: API contract reconciliation (15 min)

Rewrite `run_shotgun_day` line 528 to call detect with the correct keyword names AND supply the missing inputs:

```python
signal = detect(
    today_bars=combined,
    today_bar_idx=bar_idx,
    levels=levels_for_this_date,
    ribbon=ribbon_snapshot_for_this_bar,
    vix=vix_for_this_date,
    htf_15m_stack=htf_for_this_bar,
)
```

### Layer 2: Per-bar context plumbing (the actual hard part, ~1 hour)

For each historical date and each bar, the grinder needs to provide:

1. **Levels list** — currently nothing loads them. Options:
   - **Quick-and-dirty:** auto-derive from `combined` itself. For each date, compute: prior-day H/L, prior-day RTH session H/L, premarket H/L, ON H/L. Tag as `Active` tier. This misses ★★★ Carry levels but covers Tier 1 and most of Tier 2.
   - **Real:** load `automation/state/key-levels.json` snapshots from a historical archive (these snapshots don't currently exist as a time-series — would need to back-fill them from the Gamma_Premarket logs).
   - **Recommended:** start with quick-and-dirty for Stage 1. Add real-snapshot loading in Stage 2 if Stage 1 keepers look promising.

2. **Ribbon snapshot per bar** — compute Saty Pivot Ribbon EMAs from the rolling 5m bars. The math:
   - Fast EMA (length 8 on 5m): 8-period EMA of close
   - Pivot EMA (length 21): 21-period EMA
   - Slow EMA (length 34): 34-period EMA
   - `spread_cents = (slow - fast) × 100`
   - `stack = "BULL" if fast > pivot > slow else "BEAR" if fast < pivot < slow else "MIXED"`
   - Need to verify these EMA lengths match the actual TV indicator settings. Check `backtest/autoresearch/runner.py` for existing impl.

3. **VIX per date** — fetch historical VIX from yfinance (`^VIX`) and join into `spy_full` by date. Use the close-of-prior-day as the proxy if intraday isn't available.

4. **HTF 15m stack** — resample 5m bars to 15m, compute the same EMAs (probably shorter periods on 15m, e.g., 8/21/34 on 15m), determine stack. Could be set to `None` for Stage 1 if the detector tolerates it (verify against `_detect_open_rejection` and `_detect_level_reject` — they should optionally accept missing HTF).

## Test gating BEFORE next smoke test

The current floor gates are "did at least one trade fire" — they passed despite 0 trades because of how `regressions` is computed in `_keeper_check`. Add an additional gate to the smoke runner:

```python
if combo_result["wide_n_trades"] == 0:
    combo_result["regressions"].append("zero_trades_critical_failure")
```

This way a future API mismatch crashes loudly instead of silently.

## Validation checklist after fix

Once Layer 1 + Layer 2 land:

1. Run `--smoke` on 2026-04-29 (J winner) — expect at least 1 Tier 1 fire near the open.
2. Run `--smoke` on 2026-05-15 (today) — expect at least 1 Tier 1 fire on the 09:30 bar rejection AND 1 Tier 3 fire on the 15:00 trendline break.
3. Run `--smoke` on 2026-05-05 (J loser) — verify filters correctly REJECT (chop day, no Tier qualifies).
4. If all three pass, launch the full Stage 1 grinder (~6 hours) for Option A.
5. Clone the grinder, modify Tier 1 window from `[09:30:30, 09:34:55]` to extend ±2 bars for "Option B" continuation entries, launch in parallel.

## Why this didn't get caught tonight

L8 (Multi-agent API contract drift — added to `docs/2026-05-15-LESSONS.md`):
> When spawning parallel agents for components that must interface, SPECIFY THE EXACT API CONTRACT in both prompts. Agent A's contract drifted to one shape, Agent B's to another, both compiled cleanly, both reported "done." Only a real-data smoke test caught it. **Encoded prevention:** future multi-component prompts include an `## API Contract` section verbatim in every parallel agent's brief.

## Adjacent gap discovered

The agent that built the detector created `lib/watchers/` at the repo root, but the existing watcher pattern lives at `backtest/lib/watchers/`. Two parallel packages with the same name caused an import collision (Python picks up the first match on sys.path). Worked around tonight by copying shotgun files into `backtest/lib/watchers/`. Both copies now exist. **Cleanup task:** delete `lib/watchers/shotgun_scalper_*.py` from the repo root and remove the `lib/__init__.py` + `lib/watchers/__init__.py` package init files added by the original agent. Keep only the `backtest/lib/watchers/` copies.
