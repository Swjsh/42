# T80 — ORB + BULL fire-rate regression — ROOT CAUSE LOCATED

> Diagnosed 2026-05-14T19:42 ET (Fire #37). Root cause: ORB watcher is a per-day state machine, but `Gamma_WatcherLive` runs as a fresh Python process every 5 min — module-level `_orb_state` is reset on every fire so the breakout→wait_retest→retest_held state sequence never completes. BULL has a separate likely cause (VIX gate) under investigation.

## What I tested

`backtest/autoresearch/t80_orb_bull_regression.py` calls `detect_orb_break` and `detect_bullish_setup` directly (bypassing runner.py's medium-confidence filter at L98+L104) across 6 dates: 5/05, 5/07, 5/08, 5/12, 5/13, 5/14.

## Per-day raw return counts (offline batch run)

| Date | Bars | ORB total | ORB by conf | BULL total | BULL by conf |
|------|------|-----------|-------------|------------|--------------|
| 5/05 | 77 | 1 | medium 1 | 6 | medium 6 |
| 5/07 | 78 | 2 | low 1, medium 1 | 1 | medium 1 |
| 5/08 | 78 | 1 | low 1 | 7 | low 2, medium 5 |
| 5/12 | 78 | 1 | low 1 | 5 | low 2, medium 3 |
| 5/13 | 78 | 1 | medium 1 | 17 | low 5, medium 12 |
| **5/14** | 78 | **1** | **medium 1** | **7** | **low 3, medium 4** |

**CORRECTION 2026-05-14T20:25 (L34):** Per J — "my claude plan ran out of usage on 5/11 and 5/12 thats why it was silent those days." So 5/11 + 5/12 zero-observation days are NOT a regression — they're Claude offline. Real regression boundary is 2026-05-13 (first day Claude back online showing the silent-watcher bug). Pre-5/08 6-12 obs/day still appear to come from `Gamma_WatcherReplay` Sunday batch (sequential within one process), NOT live-tick path — that diagnosis stands. The ORB stateful-detector + fresh-process-per-tick root cause stands as documented.

So the **detectors fire correctly on every date including 5/13 + 5/14**. The medium-confidence filter at runner.py L98 + L104 is NOT the problem — there are 5 medium-conf signals on 5/14 (1 ORB + 4 BULL) that the filter would pass. Yet production logged ZERO observations 5/14.

## ORB root cause — STATEFUL + fresh-process per fire

`lib/watchers/orb_watcher.py` line 90: `_orb_state: dict[str, dict] = {}` is **MODULE-LEVEL**. Per-day state machine progression:

```
NEUTRAL → (breakout bar arrives) → WAITING_RETEST_LONG → (retest bar arrives within 8 bars) → ENTRY signal
```

Verification (run inline):

```
SCENARIO A — sequential calls (state preserved across bars in one process):
  ORB on 5/14: 1 fire at 10:30 medium (ORB_RETEST_LONG) ✓

SCENARIO B — fresh state, JUST 10:30 bar (mimics production):
  ORB returns None ✗
  _orb_state after call: {'2026-05-14': {'state': 'WAITING_RETEST_LONG', 'breakout_close': 745.99, 'breakout_ts': '2026-05-14 10:30:00', 'bars_since_breakout': 0, 'or_data': OpeningRange(high=745.89, low=743.56, ...)}}
  → state correctly transitioned to WAITING_RETEST_LONG, BUT process exits before next bar can execute the retest

SCENARIO C — PROD-MIMIC (fresh state every bar, like watcher_live's per-fire process):
  0 fires across 78 bars ✗ ✗ ✗
```

**This perfectly matches production:** `automation/state/watcher-observations.jsonl` shows 0 ORB observations 5/14 and only 6/day historically — those historical fires probably came from a different code path (e.g., `watcher_replay.py` Sunday batch, which DOES iterate sequentially within one process).

## Why did ORB fire 6/day pre-5/08?

Two hypotheses:

1. **Sunday batch replay (`Gamma_WatcherReplay` 17:00 ET)** populated obs after-the-fact — those 6 obs/day were retrospective batch observations, not live-tick observations.

2. **`Gamma_WatcherLive` task was changed** between 5/07 and 5/08 from sequential-batch mode to per-tick mode — possibly when the yfinance intraday top-up was added (CLAUDE.md L31 mentions ~5/13 changes). Need to git log `watcher_live.py` to confirm.

Either way: today's expectation is that ORB lives via `watcher_live.py` per-tick fires, and that path **fundamentally cannot work for stateful watchers** without persistent state across processes.

## BULL root cause — UNDER INVESTIGATION (T81)

BULL has 4 medium signals 5/14 in offline test. Production showed 0. Most likely cause: production's VIX gate L8 (VIX < 17.20 OR vix_falling) blocking. Today's diag showed vix_now=17.88 / 17.93 / 17.81 — all above 17.20 threshold. If `vix_falling` is computed wrong (or not computed at all in live path), BULL gets blocked.

Other candidates: htf_15m_stack=BEAR (production builds it; T80 passes None), level_states empty (production rebuilds; T80 passes empty too), L11 `htf != BEAR` filter.

Queued **T81** for next fire.

## Fix candidates (queued T82)

For ORB:

1. **State persistence across processes:** write `_orb_state` to `automation/state/_orb_state-YYYY-MM-DD.json` after every fire; load at start of every fire. Simple, low-risk.

2. **Sequential warm-up per fire:** in `watcher_live.py`, instead of calling `detect_orb_break` on just the latest bar, REPLAY all today's RTH bars from 09:30 → latest bar in one fire. Adds ~78 calls × ~1ms = ~80ms per fire (negligible). State naturally builds up, then the latest bar fires the entry signal correctly. **Recommended** — no new state file, no JSON I/O race conditions.

3. **Move ORB to `watcher_replay.py`** Sunday batch only — accept that ORB is a research-only signal that grades retrospectively, not a live-fire watcher. Lowest engineering cost but loses live alerting capability.

For BULL: depends on T81 outcome.

## What I shipped

- `backtest/autoresearch/t80_orb_bull_regression.py` — re-runnable bypass-conf-filter diag across N dates
- `automation/state/t80-orb-bull-diag.json` — raw results (per-date, per-watcher, per-confidence breakdown)
- This document

## What I did NOT do

- Did NOT modify production `runner.py` (rule 9 — confidence filter changes need J ratification)
- Did NOT modify production `watcher_live.py` (would change live behavior overnight without J review)
- Did NOT modify `_orb_state` semantics

## OP-25 lesson candidate

> **Stateful watchers + per-tick fresh-process scheduled tasks = silent zero observations.** Module-level state in a Python module is reset on every process start. Any watcher that depends on multi-bar state (state machine, dedup ledger, prior-bar memo) will silently no-op when invoked via Windows scheduled task that spawns a new pythonw per tick. Two fixes: (1) sequential warm-up replay every fire, (2) persistent state file. Neither was in place for ORB → 6 obs/day historical (from Sunday batch replay path) misleadingly suggested live coverage that never existed.

## Cost: ~$0.30 (1 Python diag script + 2 verification calls + this doc + queue update)
