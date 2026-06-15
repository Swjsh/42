# HANDOFF — Continue J-Strategy Engine Refactor (2026-05-09 night → next session)

> Context: prior chat hit context limit mid-grind. Mission per CLAUDE.md OP 17 (GRIND-UNTIL-DONE):
> the engine MUST beat J on each of his historical winners while skipping/profiting his losers.
> 5 conditions, 1 met (5/4 ✓). 4 remaining. Continue without asking permission.

## Mission state (as of handoff)

| Day | J actual | Engine current best | BEATS J? | Gap |
|---|---|---|---|---|
| 4/29 | +$342 | +$72 | ❌ NO | $270 short |
| 5/01 | +$470 | -$9 to $0 | ❌ NO (loses money) | $479+ short |
| 5/04 | +$730 | **+$820** | ✅ YES | +$90 margin (LOCKED via exit doctrine) |
| 5/05 (loss) | -$260 | $0 (skip) | ✅ YES | n/a |
| 5/06 (loss) | -$300 | $0 (skip) | ✅ YES | n/a |
| 5/07 (loss) | -$165 total | +$148 (engine bear-shorted) | ✅ YES | n/a |

**Status: 4 of 5 BEAT-J conditions met. Two remain (4/29 and 5/1).**

## What's already done — DO NOT REDO

1. **`lib/filters.py` — `detect_trendline_rejection_bearish`** is TDD'd and working.
   - Algorithm: SEQUENTIAL DESCENDING PEAKS (60-bar lookback, 10-bar min separation, asymmetric pivot)
   - Tests in `backtest/tests/test_trendline_trigger.py` — 3/3 PASS
   - Wired into bear setup eval; trendline_rejection is in the level_tied set
   - Chop-zone relaxation: when trendline is ONLY level-tied trigger, filters 5/8/9 become demerits
2. **`lib/simulator.py` BS simulator strike_offset bug FIXED.** Earlier weekend research was on ATM strikes regardless of param — now honors strike_offset properly.
3. **`doctrine/seed10095-exit-doctrine.md`** locks the 4 exit knobs that beat J on 5/4: `tp1_premium_pct=+30%` (default), `tp1_qty_fraction=0.5`, `runner_target_premium_pct=2.0`, `premium_stop_pct_bear=-0.20`. Apply to every winner.
4. **`backtest/autoresearch/j_edge_tracker.py`** is the canonical scorer per OP 16. Use this — never aggregate sharpe.
5. **CLAUDE.md OP 16 + OP 17 + GRIND-UNTIL-DONE clause** locked. Read these first.
6. **All 152 existing tests + 3 new trendline tests PASS.** Don't break them.

## What you need to do

### Goal: BEAT J on 4/29 and 5/1

Root cause already diagnosed: **engine takes multiple trades per day, each hits stop, re-enters, churns.** J takes ONE trade and holds. Engine's per-trade P&L gets diluted.

### Required engine refactors (in `backtest/lib/orchestrator.py`)

1. **First-entry-per-day lock** — once engine takes a trade on a setup type today, do NOT re-enter that same setup the same day even if triggers re-fire. The `skip_until_idx` mechanism only skips through the current trade's exit; need a per-day-per-setup lock.
2. **Qty scaling by conviction** — J trades 6-20 contracts on his strong setups; engine hardcoded to 3 (BASE) or 5 (ELITE). Need a sizing rule that goes higher on confluence + multiple-trigger setups.
3. **Per-setup exit logic** — confluence (5/4) wants long runner. Single-trigger trendline (5/1) wants quick TP1 + tight stop because chop SPY moves are small. Engine currently uses one set of exit knobs for all setups.

### How to verify each change

After EACH change, run:
```
cd C:\Users\jackw\Desktop\42\backtest
.venv\Scripts\python.exe -m autoresearch.j_edge_tracker
```

That prints the per-day J-vs-engine table. Iterate until all 5 BEAT-J conditions in CLAUDE.md OP 17 are met.

Also run existing tests after every change to make sure nothing breaks:
```
.venv\Scripts\python.exe -m pytest tests/ --tb=line -q --ignore=tests/pressure_tests --ignore=tests/test_autoresearch_validation.py
```

(The two skipped test paths have known pre-existing failures unrelated to this work.)

### Where to look first

- 5/1 specifically: engine's entries hit time stop with $0 exit. Likely the strike picker is picking too ITM for chop SPY moves. Try `strike_offset_bear=2` (OTM-2) only when trendline_rejection is the trigger. Or shorter time stop for trendline-only setups.
- 4/29: engine takes 3 sequential trades, all small. The first-entry-per-day lock will likely fix this — engine takes ONE trade, holds through stops via wider tolerance.

## Operational rules

1. **GRIND-UNTIL-DONE.** Don't ask "want me to keep going?" — keep going until all 5 conditions met.
2. **No console flashes.** Never use multiprocessing.Pool that spawns python.exe workers (causes window flashes that disrupt J's video games). Use serial mode (workers=1) or pythonw.exe.
3. **No background tasks J doesn't know about.** Currently no Discord bridge running, no scheduled tasks active (J's call). If you need a long-running process, ask before launching.
4. **Status updates yes, permission requests no.** Tell J what you're doing and what you found. Don't ask permission for the assignment work.
5. **Discord still wired** if J wants pings: `setup\scripts\gamma-notify.ps1 -Message "..."` writes to outbox. Bridge process needs restart if you want sends to actually go.

## Quick orientation

| File | Purpose |
|---|---|
| `CLAUDE.md` | Soul file. READ FIRST. OP 16 + OP 17 are the rules of this work. |
| `journal/trades.csv` | Truth — J's actual trade log. |
| `backtest/autoresearch/j_edge_tracker.py` | The scorer. Use for every iteration. |
| `backtest/lib/filters.py` | Trigger detection. Trendline trigger lives here. |
| `backtest/lib/orchestrator.py` | Main backtest engine. Refactor target. |
| `backtest/lib/simulator.py` | BS simulator (fast, used for autoresearch). |
| `backtest/lib/simulator_real.py` | Real OPRA fills (slower, used for production verification). |
| `backtest/autoresearch/audit_j_winners.py` | Per-day J vs engine compare for ad-hoc inspection. |
| `analysis/recommendations/v15-j-edge.json` | Current candidate state. Update after each milestone. |
| `analysis/seed10095-report.html` | Visual report (refresh via `render_seed10095_report.py`). |
| `doctrine/seed10095-exit-doctrine.md` | The 5/4 exit pattern locked in. |

## Smoke test before any commit

```
cd C:\Users\jackw\Desktop\42
setup\scripts\test-multi-agent-gamma.ps1 -SkipLive
```

Should report 70/70 pass. If something I built before broke, the harness catches it.

## When done

When all 5 BEAT-J conditions are met:
1. Update `analysis/recommendations/v15-j-edge.json` with the final winning params
2. Append CHANGELOG.md row
3. DM J on Discord (or just message him in chat)
4. Wait for J's ratification before any `params.json` bump (rule 9)

Until then: keep grinding.
