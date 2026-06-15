# SHOTGUN_SCALPER Full Pipeline

> **Strategy:** SHOTGUN_SCALPER — 0DTE SPY directional scalp triggered by volume-confirmed momentum bars with target-level proximity.
> **Detector:** `backtest/lib/watchers/shotgun_scalper_detector.py` (built in parallel)
> **Status as of 2026-05-16:** Stage 3 + Stage 4 running (see Execution Log below). WATCH-ONLY (OP 21).

---

## Execution Log (2026-05-16 — Directional Pipeline Run)

### Stage 3 (Directional Participation — 972 combos, 4 workers)
- **Started:** 14:44 ET, deadline 17:44 ET. **Data:** 5/12 master (no 5/14+5/15 OPRA). **Run ID:** `2026-05-16_67e97648_8de89a_028a39`
- **FINAL (17:44:25):** 505/972 combos completed (deadline cut). 9 keepers, **ALL dir_score=2/5 (structural ceiling).**
- **Structural ceiling explained:** 4/29 engine fires LONG (J was SHORT — bullish trendlines dominate the detector). 5/14 and 5/15 had no OPRA data cached at Stage 3 start → 0 fires on those days. Max achievable dir_score = 2/5 (5/01 + 5/04 fires SHORT like J).
- **Top 10 keepers — all share stop=-0.35, chandelier=0.6 (consistent signal):**

  | Rank | tp | time | strike | vol_ratio | edge_capture | sharpe | wide_pnl | final_score |
  |------|----|------|--------|-----------|-------------|--------|----------|-------------|
  | 1 | 0.5 | 12 | +1 | 1.5 | 368.1 | 3.89 | $17,178 | 1432.69 |
  | 2 | 0.5 | 15 | +1 | 1.2 | 368.1 | 3.87 | $17,061 | 1424.48 |
  | 3 | 0.5 | 15 | +1 | 1.0 | 368.1 | 3.87 | $17,061 | 1424.48 |
  | 4 | 0.5 | 12 | +1 | 1.2 | 368.1 | 3.87 | $17,061 | 1424.48 |
  | 5 | 0.5 | 12 | +2 | 1.2 | 285.0 | 4.68 | $23,894 | 1334.49 |

- **Stage 3 vs Stage 4 gap:** Best Stage 3 final_score=1432 vs Stage 4 early best=4689 → **3.3× gap** driven by OPRA vol_ratio gate filtering wrong-direction fires (particularly 4/29 LONG).
- **Output:** `analysis/recommendations/shotgun-scalper-stage3.json` (10 keepers)

### Bug found and fixed (2026-05-16 afternoon)
1. **UTC double-conversion in `_compute_htf_stacks_for_day`** (would have caused HTF gate to see only 30/78 bars). Fixed in `shotgun_scalper_stage4.py`.
2. **OPRA data gap: 5/13-5/15 options not cached.** Fixed: fetched 22+22+22 = 66 new contracts via `tools/fetch_opra_5_14_15.py`. Now 5/14 and 5/15 anchor days have real-fills coverage.
3. **`vol_ratio_threshold` dead knob.** The parameter was in `ShotgunCombo` and the grid but never compared in `run_shotgun_day`. Fixed: added `if signal.get("vol_ratio",1.0) < combo.vol_ratio_threshold: continue` gate in grinder.py. Documented as L38 in `docs/LESSONS-LEARNED.md`.

### Stage 4 (Vol-ratio + directional — 288 combos, 4 workers)
- **Started:** 16:53 ET, deadline 22:53 ET (6h). **Data:** 5/15 master (includes 5/14+5/15 OPRA). **Run ID:** `2026-05-16_67e97648_68c2c0_028a39`
- **Vol_ratio gate:** active (0.60/0.80/1.00/1.20 genuinely different).
- **In progress (17:44 ET — 115/288 = 40%):** 7 keepers, best final_score=4689 vs Stage3 best=1432 (+3.3×).
  - **Why Stage 4 >> Stage 3:** vol_ratio gate skips afternoon LONG fires on 4/29 (low-vol slots) → engine fires SHORT like J.
  - 4/29: 1 SHORT fire ✓ | 5/01: 5 SHORT fires ✓ | 5/04: 4-5 SHORT fires ✓
  - 5/14: 1 LONG fire ✓ (first anchor day captured) | 5/15: miss (engine LONG, J SHORT — structural)
- **ETA complete:** ~19:00-19:15 ET (2.25 cpm × 173 remaining combos).
- **Best Stage 4 so far (17:44):** `{tp=0.75, stop=-0.35, time=12, strike=2, chandelier=0.6, vol=1.2}` → sharpe=5.09, wide_pnl=$22,084, ec=506.6 (12.2% of $4,150 max), dir=3/5, 6/6 quarters.
- **Best dir=4 so far:** `{tp=1.5, stop=-0.35, time=15, strike=2, chandelier=0.5, vol=1.0}` → sharpe=3.93, wide_pnl=$17,480, ec=259.2.

### Stage 5 (Ratification — analytics only)
- **File:** `backtest/autoresearch/shotgun_scalper_stage5.py` (built 2026-05-16)
- **Output:** `analysis/recommendations/shotgun-scalper-stage5.json` + `.md`
- **Intermediate result (17:00 ET, 6 Stage4 keepers):** 4/6 PASS. Best: WF test $7,642 (2026 window), Sharpe=5.09.
- **OP 16 caveat:** Stage 5's edge_capture gate is `> 0` (lenient), NOT the strict OP 16 50% floor ($2,075). Best combo captures only 12.2% of J-edge max. Disclosed to J via Discord outbox.
- **Re-run after Stage 4 completes (~19:00 ET):** `cd C:\Users\jackw\Desktop\42\backtest && python -m autoresearch.shotgun_scalper_stage5`

---

## Operating-principle index

Every stage of this pipeline must comply with the following CLAUDE.md operating principles. **Failure on any one rejects the run entirely** — no "we'll fix it later."

| OP | Rule | Where enforced |
|----|------|----------------|
| 11 | Karpathy method — eval-first, reproducibility | `run_id` via `backtest/lib/repro.py`, written into every artefact |
| 13 | Pure Python research, no LLM in the loop | All stages `pythonw.exe -m autoresearch.shotgun_scalper_*` |
| 14 | WR is NOT primary. Sharpe + expectancy + max-DD + edge_capture | `KeeperGates` in `shotgun_scalper_grinder.py` |
| 15 | MAX_PARALLEL_RESEARCH_WORKERS = 4. Pool-based (NOT threads) | `mp.Pool(min(workers, 4))` |
| 16 | edge_capture is PRIMARY. `final_score = edge_capture * sharpe` | Stage 1+ selection sort key |
| 19 | Every row carries top5_pct, quarter_pnl, positive_quarters, max_drawdown | `evaluate_shotgun_combo()` return dict |
| 20 | Non-theatre validation — 6 disclosures bundled with every "ready" claim | Stage 5 ratification scorecard |
| 21 | Watch-First Promotion Path — no live without J ratification | This whole doc |

---

## Strategy spec (frozen)

**Trigger:** Volume-confirmed momentum bar with target-level proximity.

- **Detector inputs:** 5m SPY bars, named-level set (prior day RTH H/L, 5-day H/L, premarket-H/L), 20-bar volume baseline.
- **Trigger conditions** (detector enforces; combo only tunes thresholds):
  - Body in direction of trade ≥ configurable cents.
  - Volume ≥ `vol_ratio_threshold` × 20-bar avg.
  - Target level within proximity dollars from bar close.
  - Entry-window time gate `[09:35, 15:00)` ET — outside this window = no fire.
- **Side mapping:** trigger direction = `short` → buy put; `long` → buy call.
- **Strike:** `round(spot) + strike_offset` for puts; `round(spot) − strike_offset` for calls. `-1 = OTM-1`, `0 = ATM`, `+1 = ITM-1`.

**Exits (first-to-fire wins; stop checked first on same-bar conflict):**
1. Premium stop (`stop_premium_pct` × entry_premium).
2. Chandelier trail (arms at `chandelier_arm_pct` favor; trails 20 % off HWM).
3. Target-level touch (SPY bar high/low hits the level fed in by the detector).
4. TP premium (`tp_premium_pct` × entry_premium).
5. Time stop (`time_stop_min` minutes after entry).
6. EOD-flat at 15:50 ET regardless.

**Fill model:** OPRA real bars from `backtest/data/options/{symbol}.csv` per OP 16 + OP 20 disclosure 4. No Black-Scholes. Entry fills at next 5m bar's close at the trigger. Slippage NOT applied here (Stage 5 real-fills validation adds bid/ask half-spread).

---

## Stage 1 — Grinder (2,160 combos)

**File:** `backtest/autoresearch/shotgun_scalper_grinder.py`
**Wall-clock budget:** 4–6 hours on 4 workers.
**Output:** `analysis/recommendations/shotgun-scalper-stage1.json` (top 10) +
`autoresearch/_state/shotgun_scalper_stage1/keepers.jsonl` (all keepers).

### Search space

| Knob | Values | n |
|------|--------|---|
| `tp_premium_pct` | 0.50, 0.75, 1.00, 1.50, 2.00 | 5 |
| `stop_premium_pct` | −0.10, −0.15, −0.20, −0.25 | 4 |
| `time_stop_min` | 8, 12, 15, 20 | 4 |
| `strike_offset` | −1 (OTM-1), 0 (ATM), +1 (ITM-1) | 3 |
| `chandelier_arm_pct` | 0.15, 0.25, 0.40 | 3 |
| `vol_ratio_threshold` | 1.2, 1.5, 2.0 | 3 |
| **Total** | | **2,160** |

### Data window

- **Wide window:** 2025-01-01 .. 2026-05-15 (≈ 16 months, 350+ trading days).
- **Anchor days** (J source-of-truth trades, hardcoded in `J_WINNERS` / `J_LOSERS`):

  | Winners ($MUST trade) | $ J P&L | Losers ($SHOULD skip / lose less) | $ J P&L |
  |---|---|---|---|
  | 2026-04-29 | +342 | 2026-05-05 | −260 |
  | 2026-05-01 | +470 | 2026-05-06 | −300 |
  | 2026-05-04 | +730 | 2026-05-07 | −120 |
  | 2026-05-14 | +1,208 | | |
  | 2026-05-15 | +1,400 | | |
  | **Total** | **+4,150** | | **−680** |

  `edge_capture = winners_capture − losers_added`. Max possible = 4,150.

### Per-combo scorecard (24 fields)

```json
{
  "combo": {...},
  "by_day": {"YYYY-MM-DD": float, ...},
  "winners_capture": float,
  "losers_added": float,
  "edge_capture": float,
  "edge_capture_pct": float,
  "wide_pnl": float,
  "wide_n_trades": int,
  "wide_wr": float,
  "expectancy_per_trade": float,
  "sharpe": float,
  "top5_pct": float,
  "quarter_pnl": {"2025-Q1": float, ...},
  "positive_quarters": int,
  "quarter_count": int,
  "max_drawdown": float,
  "final_score": float,
  "passed_floors": bool,
  "regressions": [str, ...]
}
```

### Stage 1 keeper gates (strict; any failure → rejection)

| Gate | Threshold | Source |
|------|-----------|--------|
| `sharpe` | ≥ 0.8 | OP 14 |
| `max_drawdown` | ≤ $1,500 (qty=3 baseline) | OP 14 / OP 20 |
| `expectancy_per_trade` | > 0 | OP 14 |
| `wide_n_trades` | ≥ 30 | Statistical significance |
| `edge_capture_pct` | ≥ 50 % of max | OP 16 |
| `positive_quarters` | ≥ 4 of 6 | OP 11 / OP 19 |
| `top5_pct` | ≤ 50 % | OP 20 disclosure 6 |

### Stage 1 ranking

`final_score = edge_capture × sharpe` (OP 16). Aggregate `wide_pnl` is a tiebreaker only — engines that print money on three days and bleed on 200 are rejected by the concentration + positive-quarters gates.

### CLI

```powershell
# Smoke test first (single combo, J winner days only)
pythonw.exe -m autoresearch.shotgun_scalper_grinder --smoke

# Full Stage 1 run (4 workers, 6-hour deadline)
pythonw.exe -m autoresearch.shotgun_scalper_grinder --hours 6 --workers 4

# Reset prior run and start fresh
pythonw.exe -m autoresearch.shotgun_scalper_grinder --reset --hours 8
```

---

## Stage 2 — Refine top 5 (tighter neighborhoods)

**File:** `backtest/autoresearch/shotgun_scalper_stage2_grinder.py` (TBD — port from `sniper_stage2_grinder.py`).
**Wall-clock:** 1–2 hours.
**Output:** `analysis/recommendations/shotgun-scalper-stage2.json`.

For each of Stage 1's top-5 keepers, build a tighter neighborhood:

- `tp_premium_pct` ± 0.10 in increments of 0.05.
- `stop_premium_pct` ± 0.03 in increments of 0.01.
- `chandelier_arm_pct` ± 0.05.

Stricter gates than Stage 1 (everything Stage 1 enforced PLUS):
- `sharpe` ≥ 1.0
- `positive_quarters` ≥ 5 of 6
- `top5_pct` ≤ 40 %

---

## Stage 3 — Regime robustness

**File:** `backtest/autoresearch/shotgun_scalper_stages345.py` (TBD — port from `sniper_stages345.py`).
**Wall-clock:** < 5 min (pure filter pass).

For each Stage 2 keeper, drop any combo whose:
- `concentration ratio` (top-5-days / total) > 200 % (i.e. losing more than half the P&L would survive). Use the `top5_pct` field directly.
- ≥ 4 of 6 quarters net-positive (carried forward from Stage 1).
- Worst quarter draw-down < 30 % of total positive quarter sum.

---

## Stage 4 — Sub-window stability

**Output:** Same `stages345.json` artefact, `sub_window` block.

Decompose 16-month window into `Q1 2025`, `Q2 2025`, `Q3 2025`, `Q4 2025`, `Q1 2026`, `Q2 2026` (partial). For each candidate:

- Compute per-quarter `pnl`, `n_trades`, `expectancy`.
- **Gate:** all 6 quarters net-positive (zero exemptions). One losing quarter = drop.
- Compute `cv = stddev(quarterly_pnl) / mean(quarterly_pnl)`. **Gate:** `cv ≤ 1.0`.

This is the regime-robustness gate that catches "won 5 quarters at +$200, lost Q3 2025 at −$1,200" cherry-picks.

---

## Stage 5 — Final ratification scorecard

**File:** `backtest/autoresearch/shotgun_scalper_stages345.py` (final phase).
**Output:** `analysis/recommendations/shotgun-scalper-v1.json` (single winner combo with full scorecard).

This is the **only** stage whose output gates live promotion. Per OP 20, every claim of "ready" requires all six disclosures:

1. **Account-size assumption** — qty=3 baseline; headline P&L scales linearly with qty.
2. **Sample-bias disclosure** — selection from 2,160-combo grinder = overfit risk.
3. **Out-of-sample test** — `walk_forward_validate.py` on the winner; train ≤ T-1 year, held-out test.
4. **Real-fills check** — `simulator_real.py` (or `shotgun_scalper_real_fills.py`) on top-3 J winner days. Diff% < 20 % vs OPRA close fills.
5. **Failure-mode enumeration** — worst day, max drawdown, blow-up scenario.
6. **Concentration disclosure** — top-5 days as % of total P&L.

### Monday-Ready Checklist (`docs/MONDAY-READY-CHECKLIST.md`)

After Stage 5 produces a winner candidate, run the existing `monday_ready_check.py` against it. The checklist is binary — pass all OR the candidate stays watch-only.

---

## Stage 6 — Watch-First live promotion (OP 21)

Even after Stages 1–5 + Monday-Ready pass, the strategy starts in **watcher mode**:

- Add `shotgun_scalper_watcher.py` to `backtest/lib/watchers/`.
- Register in `Gamma_WatcherLive` task (5-min cadence).
- Stateful detectors must be added to `watcher_live.py` T82 warmup loop (per CLAUDE.md L35 lesson — fresh-process invocation resets module state).
- Log observations to `automation/state/watcher-observations.jsonl`.
- Promotion to live order placement requires:
  - **3+ historical observations** that would have won (graded via `watcher_grader.py`).
  - **3+ live observations** confirmed by J as valid signals.
  - **Positive expectancy over 16-month full backfill** at the chosen knob set.
  - **Per-confidence-tier expectancy positive** (no all-or-nothing — each tier must stand on its own).
  - **J's explicit ratification** in writing.

---

## Reproducibility

Every run computes a content-addressed `run_id` via `backtest/lib/repro.py`:

```
run_id = {date}_{code_hash[:8]}_{data_hash[:6]}_{params_hash[:6]}
```

- `data_hash = sha256(spy_csv || vix_csv)` — detects data drift.
- `code_hash = git rev-parse HEAD` (or `sha256(lib/*.py)` fallback).
- `params_hash = sha256(canonical(params.json))`.

The `run_id` is written into every Stage 1+ artefact's `run_identity` block. Historical runs stay frozen — re-running with different data/code/params produces a different `run_id`, never an unannounced change.

---

## Cost ceiling

Per CLAUDE.md OP 3 (cost-effectiveness gate):

- **Stage 1:** Pure Python, $0 LLM cost. CPU time only (≈ 4–6 hours on 4 workers).
- **Stage 2:** Pure Python, $0.
- **Stages 3–4:** Pure Python filter, < 5 min, $0.
- **Stage 5:** Pure Python, $0.
- **Total pipeline cost:** $0 LLM, ≈ 8–10 hours wall-clock on 4 workers.

---

## Anchor-day quick reference

```python
# Hardcoded in shotgun_scalper_grinder.py — DO NOT MODIFY without J ratification
J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342},
    {"date": "2026-05-01", "j_pnl": 470},
    {"date": "2026-05-04", "j_pnl": 730},
    {"date": "2026-05-14", "j_pnl": 1208},
    {"date": "2026-05-15", "j_pnl": 1400},
]
J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260},
    {"date": "2026-05-06", "j_pnl": -300},
    {"date": "2026-05-07", "j_pnl": -120},
]
J_TOTAL_WINNERS = 4150  # max edge_capture possible
```

---

## Queue position

Stage 1 is queued as the next executable item after the SHOTGUN_SCALPER detector lands at `backtest/lib/watchers/shotgun_scalper_detector.py`. Smoke-test (`--smoke`) is the gate — once it returns a non-error result for one J winner day, run the full Stage 1 grinder.

## Foot-gun checklist (before each stage launch)

- [ ] Detector importable: `python -c "from lib.watchers.shotgun_scalper_detector import detect"` succeeds.
- [ ] Smoke test passes: `pythonw -m autoresearch.shotgun_scalper_grinder --smoke` returns a result with `passed_floors` field (may be True or False — just no exceptions).
- [ ] OPRA cache covers J winner + loser strikes for the anchor dates: spot-check `backtest/data/options/SPY2604{29,30}P*.csv`, etc.
- [ ] `_state/shotgun_scalper_stage1/` writable. PIDFILE not stale (if `runner.pid` exists, check process via `Get-WmiObject Win32_Process -Filter "ProcessId = N"` per CLAUDE.md L33).
- [ ] `analysis/recommendations/` writable.
- [ ] No prior `progress.json` to clobber unless `--reset` is intended.
