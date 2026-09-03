# Trendline capability + shadow audit (T1 WHAT WE HAVE)

**Stamp:** 2026-09-03T17:34:27 ET (`setup/scripts/et_clock.py`, market_hours=False) · **Slug:** capability-and-shadow
**Scope:** code + ledger inventory only. No backtest run, no order, no file touched outside this deliverable. Full data: [`trendline-capability-and-shadow.json`](trendline-capability-and-shadow.json).

## Headline — answering J directly

**Are we shadowing his pattern? Partially.** The *break* half of his pattern (rising support gives way, price declines — his 14:30 exhibit) IS shadowed, and is in fact the single largest trade category in the whole ledger. The *bounce* half (price touches rising support and continues up — his 10:55 exhibit) is logged as a raw event but is structurally excluded from ever becoming a scored trade. Nobody has ever asked "did the bounce make money."

**Which timeframes?** 5-minute bars, including premarket (04:00 ET onward), via one shadow lane only (`Gamma_TrendlineShadow`). No 15m/1m/1h shadow coverage of this pattern exists.

**Is it doing well? No green light.** 73 sessions, n=1,451 theoretical trades (through 2026-09-02): **+0.0386 SPY pts/trade**, session-clustered 95% CI **[-0.0301, +0.1177]** — straddles zero — top-3 sessions supply **105.4%** of all profit (everything else nets negative). None of this pool contains a single bounce-continuation trade — the headline number can't speak to J's specific pattern either way.

---

## 1. What `trendline_detector.py` can detect

Built 2026-08-09, `DETECTOR_VERSION` 1.0.0 (`backtest/lib/trendline_detector.py`), a pivot-anchored, general-purpose library:

| Parameter | Values | Default |
|---|---|---|
| `kinds` | `resistance` (fit through swing highs) \| `support` (fit through swing lows) — both requestable together | `("resistance","support")` |
| `require_slope` | `any` \| `rising` \| `falling` | `any` |
| `anchor_mode` | `wick` \| `body` — **never mixed within one line, structurally** (bar-view transform runs *before* pivot search, plus a belt-and-suspenders assert) | `wick` |
| `pivot_window` | fractal window (crypto.lib.market_structure) | 2 |
| `min_touches` | — | 3 |
| `min_bars_between_touches` | — | 6 |
| `min_span_bars` | — | 6 |
| `touch_tolerance_dollars` | zone width | 0.20 |

A rising-support line is fully expressible today: `kind="support", require_slope="rising"`. **It honors the ALL-body/ALL-wick rule structurally**, not just via assert.

**Who calls it, on what timeframe** — none of them the live decision path:
1. `setup/scripts/trendline_chart_draw.py` → `trendline_headless_draw.py` (`Gamma_TrendlineHeadlessDraw`, 08:40 ET + every 30min to 16:10) — draws wick+body × support+resistance onto the live TradingView chart. **Display only, 5m default, zero decision consumer.**
2. `backtest/autoresearch/trendline_timeframe_matrix_2026_08_09.py` — one-off research (1m/5m/15m/30m/1h touch-respect), not a running lane.
3. `backtest/autoresearch/trendline_validation_cells_2026_08_09.py` — the 4-cell study behind `TRENDLINE-ENGINE-VALIDATION-2026-08-09` (§3 below).

`heartbeat_core.py` **never imports this module.**

**Correction to the task's framing:** `setup/scripts/trend_cache_producer.py` is unrelated — it's a $0 daily-bar extender for the *multi-day trend-regime* classification cache (`regime_classifier.py`), zero references to `trendline_detector`/`detect_trendlines`. Not part of this stack.

### Premarket eligibility — the live engine is structurally blind to it

`heartbeat_core.py._build_payload` filters to **RTH-only (≥09:30, <16:00 ET) at line 903**, *before* the `W = 150` bar window is sliced at line 907. `W=150` (5m bars, ~1.9 RTH sessions) is sized for lookback headroom, but that's moot — **premarket bars never reach the window at all**, regardless of `W`. `prior_bars` fed to `detect_trendline_rejection_bearish` / `detect_trendline_reclaim_bullish` comes straight from this RTH-only slice.

**So: an 08:20 ET premarket low is NOT an eligible anchor at 10:55, ever, for the live engine** — not a data gap, a deliberate RTH-only filter (shipped 2026-06-25 to fix a 42%-score-parity backtest/live mismatch: extended-hours bars shift the ribbon EMAs).

This is independently confirmed by a companion exhibit run already on disk with the same stamp ([`trendline-today-exhibit.json`](trendline-today-exhibit.json)): its `5m_rth_only_asof_1050` detector call (RTH-only, as of the 10:50 close) finds **0** support lines (only 17 RTH bars exist by then); its `5m_full_day_incl_premarket_asof_1050` call at the *same instant*, premarket included, finds **3** candidate support lines. Same detector, same moment — the only variable is whether premarket bars are in the window.

## 2. Live vs shadow triggers, per side

| Side | Geometry | Status | Function |
|---|---|---|---|
| Bear | **Descending** resistance, rejection | **LIVE** (`trendline_rejection`) | `filters.py:758 detect_trendline_rejection_bearish` — pivot HIGHS only, hard-rejects any non-decreasing slope |
| Bull | **Descending** resistance, breakout above | SHADOW only (`trendline_reclaim`) | `filters.py:1101 detect_trendline_reclaim_bullish` — byte-identical pivot search to the bear function; deliberately chose "reclaim of a descending line" over "ascending-support reclaim" (doctrine precedent: playbook's `TRENDLINE_BREAK_VOLUME`) |
| Bull, rising-support **bounce** | Ascending support, touch-and-continue | **Logged, never scored** | `trendline_shadow.py` via `trendlines.py` — TOUCH event exists (1,080 rows), tagged bullish, forward MFE/MAE recorded, but **not** in `THEO_EVENTS` — never becomes a theoretical trade |
| Bear, rising-support **break** | Ascending support breaks → decline | **SHADOW, and the largest category in the ledger** | Same lane — `("ascending","BREAK")` IS in `THEO_EVENTS`: 762 events, 686 theoretical trades, bias=bearish. This is exactly J's 14:30 exhibit shape. |

**Bottom line:** no live or shadow trigger implements a rising-support *bounce* for calls. The rising-support *break* for puts IS shadow-scored, and it's the single biggest trade category the ledger has ever logged.

## 3. What `Gamma_TrendlineShadow` actually scores

`backtest/lib/trendlines.py::detect_trendlines` (general scipy `find_peaks`, both ascending-from-lows and descending-from-highs, **wick-only** — no `anchor_mode` param) wrapped by `setup/scripts/trendline_shadow.py` (daily 16:22 ET) into `analysis/trendlines/shadow-ledger.jsonl`.

- **Bar source:** cumulative `spy_5m_*.csv`, includes premarket from 04:00 ET (verified directly on 2026-09-02's file).
- **Events:** TOUCH / BREAK / RETEST / REJECT per line, refit every 6 bars (30min), min 24 bars (~2h) context, $0.15 touch tolerance.
- **Theoretical trade:** TP +1.00pt / stop -0.50pt / 60min time-stop, stop checked first — but ONLY for `THEO_EVENTS = {(ascending,BREAK), (ascending,REJECT), (descending,REJECT)}` with touch_count≥3 and R²≥0.70.

**Ledger composition, read fresh this session** (4,986 rows, 74 sessions through 2026-09-03):

| direction / event | rows | theo trades |
|---|---:|---:|
| ascending / BREAK | 762 | 686 |
| ascending / REJECT | 439 | 388 |
| ascending / RETEST | 301 | 0 |
| **ascending / TOUCH** (J's bounce) | **1,080** | **0** |
| descending / BREAK | 752 | 0 |
| descending / REJECT | 436 | 387 |
| descending / RETEST | 336 | 0 |
| descending / TOUCH | 880 | 0 |

For context only (exploratory, NOT bootstrap-CI'd, NOT pre-registered): the 1,066 ascending-TOUCH rows with a recorded `mfe_30m` average **+0.67 SPY pts** forward favorable excursion. This is not a trade result and should not be read as one.

**Verdict** (`analysis/trendlines/shadow-verdict.json`, latest = 2026-09-02, via `trendline_shadow_verdict.py`, day-level session-clustered bootstrap, n_boot=2000, seed=1337, ci=0.95):

- 73 sessions, n=1,451, **+0.0386 pts/trade**, WR 40.0%, 39/73 sessions positive
- **95% CI [-0.0301, +0.1177]** — does not clear zero
- **top-3 sessions = 105.4%** of total profit
- Frozen promotion bar (CI-lower>0 AND top3<50% AND n_sessions≥60, no new knobs): **fails 2 of 3 gates** (n_sessions clears, the other two don't)
- History: only 2 dated entries (the reconstructed 2026-08-20 one-off, and this 2026-09-02 recompute) — same shape, not resolving.

## 4. The four preregs — all resolved, none open

| Prereg | Verdict |
|---|---|
| `TRENDLINE-BREAK-AT-LEVEL-2026-08-13` | **NULL** — 0/72 cells survive BH-FDR; the naive positive (confluence looked like it raised MFE/MAE up to +26%) reproduces 41% of the time under a date-shuffle null — an artifact. |
| `TRENDLINE-ENGINE-VALIDATION-2026-08-09` | 4 cells: **A** trendline_rejection alone = strongest live cohort (already live) · **B** shadow bull-reclaim fired unconditionally loses -$27,378 over 2,411 replays, NOT shipped · **C** proximity-admissibility KILLED · **D** wick vs body indistinguishable (p=0.96). |
| `prereg-trendline-context-conditioning-2026-08-01` | **NULL** — 0/16 tests survive BH-FDR. |
| `G2-TRENDLINE-BYPASS-INVERTS-PRIORITY-2026-08-01` | **NULL, both arms** — neither EXTEND nor REMOVE clears its gates; control stays trendline-only. |

SHADOW.md's "no status field" note is accurate for the prereg JSON files (none carries a `status` key) but every one of the four has a completed result file with a final verdict — "no status field" ≠ "never run."

## 5. The 2026-08-20 "pivot-highs only" lesson — still true today

Origin: J hand-drew an ascending support line 2026-08-20 (08:35/10:20/11:30 lows); it broke, retested, rejected, ran to 763.04. He asked why the engine never saw it. Re-reading `detect_trendline_rejection_bearish` in full this session (§2 above) confirms the answer is unchanged: it is still the **only** trendline detector ever on the live entry path, still reads pivot HIGHS exclusively, still hard-rejects any non-decreasing slope. Ascending support is invisible to the live engine by construction — a geometry limit, not a regression. That gap is exactly what `trendline_shadow.py` was built the same day to start measuring.

## Gap and suggested next step

Nothing in this codebase — live, shadow, or research — currently scores "does a bounce off rising support that continues up make money." A pre-registered study adding ascending-TOUCH-continuation as its own `THEO_EVENTS` category, run over the same 74-session ledger, would directly answer J's 10:55 pattern — something the current +0.0386 headline structurally cannot do, since it has never contained one bounce trade.
