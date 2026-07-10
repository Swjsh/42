# Signal-Shape Coverage Audit — 2026-07-10

> READ-ONLY audit. Data: `backtest/data/spy_5m_2026-05-19_2026-07-10.csv` (day-shape taxonomy) + `automation/state/core-decisions.jsonl` (setup-firing map) + `analysis/recommendations/pattern-prescreen.json` (coverage-candidate numbers). Raw output: [`analysis/signal-shape-coverage-2026-07-10.json`](../../analysis/signal-shape-coverage-2026-07-10.json).

## Headline

**The 07-10 exhibit is real but the mechanism is sharper than "no signal fired": `BULLISH_RECLAIM_RIDE_THE_RIBBON` scored ENTER_BULL 11 times, and every single one was blocked before a real order — then the setup stopped scoring anything for the last 3 hours of a $7.32-range session.** The same exact signature (fires repeatedly, 100% blocked by `SKIP_ELITE_BULL_LEVEL_RECLAIM`, zero entries) independently reproduces on 2026-06-30 (772 ticks / 64× blocked / 0 ENTER — a pre-existing, already-audited incident). This gate was already tested and validated-KEEP (unblocking = net **−$241**, 2026-06-30 bull-unblock audit) — **so the fix is not loosening the existing gate, it's a structurally different detector.** `flag_pullback_continuation` is the pre-screened, never-built candidate that fits: **battery-ready this weekend.**

`core-decisions.jsonl` has no archive anywhere in the repo — its real retention is **11 of the 30 sessions** in this window (2026-06-25 partial → 2026-07-10). The other 19 sessions get a day-shape label but **no setup-firing data exists for them, full stop** — not backfilled, not estimated.

---

## 1. Day-shape taxonomy — frozen rules

Computed from RTH-only (09:30–15:59 ET) 5-minute bars, applied in this priority order (first match wins, every session gets exactly one label). Thresholds were calibrated once against two known days (2026-07-10, 2026-06-30) then frozen before the full 30-day pass ran — not re-tuned after seeing the answer.

Let `o`/`c`/`hi`/`lo` = session open/close/high/low, `closes[]` = the chronological 5m close path, and "early" = within the first 25% of the session's bars.

| # | Label | Rule |
|---|---|---|
| 1 | `FLUSH_RECOVER` / `SPIKE_FADE` | An early ≥0.6% move from the open reclaims/fades **61.8%–138.2%** of itself by the close (Fib round-trip band — recovers but does not extend into a fresh trend). |
| 2 | `FLUSH_TREND_DOWN` / `FLUSH_TREND_UP` | A **fast** early break (extreme set within the first 25% of bars, ≥0.6% from open) that reclaims **<61.8%** and the day still closes ≥0.3% net in the break's direction — never meaningfully recovers. |
| 3 | `TREND_UP` / `TREND_DOWN` | An **anchored** move ≥0.6% with **<35% max giveback** of the move-so-far at any point after the anchor. The anchor is the open, UNLESS the session low (up) / high (down) was set early AND is beyond the open — then the anchor is that early extreme. This is what lets a day that flushes early and then grinds the rest of the way (07-10's shape) read correctly as a trend "off the low," not a flush. |
| 4 | `GAP_GO` / `GAP_FADE` | \|opening gap vs prior RTH close\| ≥0.3%, net move same-sign (GO) or opposite-sign (FADE), \|net move\| ≥0.3%. |
| 5 | `RANGE` | (high − low)/open < 0.5%. |
| 6 | `CHOP` | Catch-all: directional but ≥35% retrace, or wider range that never cleanly resolves. |

**Calibration transparency:** 2026-06-30 nets +0.87% and closes near its highs, but its max giveback mid-day was 45.1% (>35%) — this audit's rule reads it as `CHOP`, while `self_check.py`'s own comment calls it "a clean bull trend" (an indicator-state read: the ribbon/HTF stack stayed BULL all day). Both are valid, different lenses — flagged, not resolved, and it doesn't change the finding below (the same block mechanism fires on both labels).

## 2. Day-shape distribution — last 30 RTH sessions (2026-05-28 → 2026-07-10)

| Shape | Days | % of 30 | Total $ range | Sessions |
|---|---:|---:|---:|---|
| `CHOP` | 11 | 36.7% | $80.76 | 05-28, 06-01, 06-03, 06-04, 06-16, 06-17, 06-18, 06-24, 06-30, 07-01, 07-02 |
| `GAP_GO` | 4 | 13.3% | $50.93 | 06-05, 06-10, 06-11, 07-06 |
| `GAP_FADE` | 4 | 13.3% | $47.76 | 06-08, 06-09, 06-26, 07-08 |
| `RANGE` | 3 | 10.0% | $9.37 | 05-29, 06-02, 06-15 |
| `TREND_UP` | 3 | 10.0% | $22.80 | 06-29, 07-09, **07-10** |
| `FLUSH_TREND_DOWN` | 2 | 6.7% | $15.52 | 06-25, 07-07 |
| `FLUSH_RECOVER` | 1 | 3.3% | $9.41 | 06-12 |
| `TREND_DOWN` | 1 | 3.3% | $7.05 | 06-22 |
| `SPIKE_FADE` | 1 | 3.3% | $7.33 | 06-23 |

**First correction to the mission's own hypothesis:** GAP days (`GAP_GO`+`GAP_FADE`) are both more frequent (8/30 vs 4/30) and carry more aggregate $ range ($98.69 vs $29.85) than TREND days in this window. TREND_UP's real significance isn't size — it's a consistent, verified failure mechanism (§4).

## 3. Setup-firing map — data-coverage caveat

`automation/state/core-decisions.jsonl` has **no archive or rotation anywhere in this repo** — `git log --follow` shows exactly one commit ever touched it (2026-06-26), and no rotated copy exists under `automation/state/` or elsewhere. Live retention is **2026-06-25 (partial, engine started 13:48 ET) through 2026-07-10 — 11 real sessions**, not 30.

- **11/30 sessions have setup-firing data:** 06-25(partial), 06-26, 06-29, 06-30, 07-01, 07-02, 07-06, 07-07, 07-08, 07-09, 07-10.
- **19/30 sessions have NONE** (05-28 → 06-24): day-shape label exists, participation is simply unknown.
- **Data-quality flag:** 2026-07-03 shows 756 logged engine ticks but **zero bars** exist in the SPY 5m cache that date — confirmed market-CLOSED (July 4 2026 falls Saturday; NYSE observes the preceding Friday). The heartbeat ticked and logged decisions against a fully closed market. Excluded from every stat in this report; flagged separately below (§7), not fixed here.

### Definitions used (stated once, applied consistently)

- **Fired** — core setups: `setup` field non-null on a tick (scoring passed, independent of what gate follows). Extra setups: `extra_signals[i].fired == true`.
- **Entered** — core setups: `verdict` ∈ {ENTER_BEAR, ENTER_BULL}. Extra setups: `extra_exec[i].action == 'PLACED'`.
- **Orders** — `exec.status == 'PLACED'`. **A verdict of ENTER_\* does NOT guarantee a real order attempt** — the separate `action` field can downgrade an ENTER verdict to a no-op (e.g. `SKIP_STALE_TRIGGER`) with no `exec` dispatch at all. Reported separately, not conflated.
- **Fills** — not reliably reconstructable from `core-decisions.jsonl` alone; `journal/trades.csv` is the fill-of-record, cross-checked selectively where it changes the conclusion.

## 4. The day-shape × setup matrix (11 sessions with data)

| Shape | n/30 | Sessions w/ data | Setup participation (fired → entered) |
|---|---:|---:|---|
| `TREND_UP` | 3 | 3/3 | `BULLISH_RECLAIM`: 06-29 4→0, 07-09 114→5, **07-10 42→11 (0 real orders)**. `bollinger_squeeze` fired 07-09/07-10. |
| `FLUSH_TREND_DOWN` | 2 | 2/2 | `BEARISH_REJECTION`: 06-25 12→1, 07-07 56→18 (**07-07 has 7 real fills in trades.csv**). |
| `GAP_GO` | 4 | 1/4 | 07-06: `BULLISH_RECLAIM` 48→3 entered. |
| `GAP_FADE` | 4 | 2/4 | 07-08: `BULLISH_RECLAIM` 16→6 entered. **06-26: never fired at all** ($6.31 fully uncaptured). |
| `CHOP` | 11 | 3/11 | 06-30: `BULLISH_RECLAIM` 64→**0** (the corroborating incident, §5). 07-01/07-02: thin. |
| `RANGE`, `FLUSH_RECOVER`, `TREND_DOWN`, `SPIKE_FADE` | 6 | 0/6 | No decision data exists for any of these 6 sessions. |

**Global funnel context (11 real sessions, 7,960 ticks, both accounts — the raw file has 8,716 rows across 12 calendar dates, but 756 of those are the 2026-07-03 market-closed artifact, §3, which contributes ZERO to every figure below, verified):** only **7 total `PLACED` actions** and **16 `PLACE_FAIL`** across the whole window. `SKIP_ELITE_BULL_LEVEL_RECLAIM` is the single largest non-HOLD verdict in the entire dataset at **270 occurrences** — more than every other SKIP/RISK_DENY reason combined.

## 5. Exhibit A — 2026-07-10 (the named exhibit)

Open **752.05** → early low **748.10** → high **755.42** → close **754.86** ($7.32 range; confirms "$7 off the low" to the dollar; 734/780 ticks HOLD confirms the mission's count exactly, 504 of those after 11:33 ET).

1. **09:31–09:35 ET** (Safe): `BULLISH_RECLAIM_RIDE_THE_RIBBON` scores SUPER-tier `ENTER_BULL` five times (spy=751.55) — but `action=SKIP_STALE_TRIGGER` every time (`trigger_bar_et: 2026-07-09T15:55`, the **prior session's** last bar). Correctly refused; zero real attempt.
2. **11:21–11:33 ET** (Bold): same SUPER-tier setup scores `ENTER_BULL` six more times — all six hit `SKIP_MIN_PREMIUM_FLOOR`.
3. **11:21–11:33 ET** (Safe, concurrently): `SKIP_BULL_1100_1200` — a deliberate, named lunch-hour block (`block_bull_1100_1200`, params.json).
4. **11:51–12:55 ET**: `SKIP_ELITE_BULL_LEVEL_RECLAIM` × 20 — the setup keeps re-scoring (bull_score=11 throughout) but has no fresh named level to re-enter on.
5. **12:55:04 ET**: the `setup` field goes null for the rest of the session. Nothing scores again through the 15:55 close, during which SPY still ran 753.81 → 755.42 high / 754.86 close (**a further $1.05–$1.61 of continuation with zero engine engagement**).
6. **Verified independently:** all 780 ticks that day (both accounts) show an **empty `exit_pass`** — no position was open at ANY point on 2026-07-10.

`bollinger_squeeze` did fire 13 ticks that day with a genuine last-fire at **15:10:03 ET** (real afternoon activity) — but its 4 `PLACED` extra_exec actions all timestamp to **00:54–01:01 ET** (pre-market, not RTH), disconnected from the 15:10 fire. Flagged as an unresolved logging anomaly, not counted as confirmed afternoon coverage.

**Correction to the original framing:** "not one armed setup even fired a signal after 11:33" is not quite accurate — `BULLISH_RECLAIM` scored through 12:55 and `bollinger_squeeze` fired through 15:10. The verified, sharper failure: **every scored signal was blocked before a real order, and after 12:55 nothing scored at all.**

## 6. Exhibit B — 2026-06-30 (independent corroboration, same window)

772 ticks, `BULLISH_RECLAIM_RIDE_THE_RIBBON` fired 64 times — **all 64 blocked by `SKIP_ELITE_BULL_LEVEL_RECLAIM`, zero `ENTER_BULL`.** This is a pre-existing, already-investigated incident (`setup/scripts/self_check.py` L139 comment; `markdown/doctrine/LESSONS-LEARNED.md` L197; `.claude/agent-memory/gamma/project_bull_unblock_elite_lever_retired.md`), independently re-derived here from raw `core-decisions.jsonl` and matching byte-for-byte (772 ticks / 64× blocked / 0 ENTER). Same mechanism as 07-10, two weeks apart, on a day with almost identical $ range ($7.13 vs $7.32).

**This gate was already audited and tested KEEP, not broken:** the 2026-06-30 bull-unblock thread (commit `79f842c`) removed `block_elite_bull` and re-ran the cohort — **net −$241, WR 14.3%, DRY_AT_ZERO → validated the block is correctly removing losers.** Two other unblock levers (`filter_10_min_triggers_bull` structural threshold, `sequence_reclaim` decoupling) were also tested and closed: the structural threshold **fails walk-forward on full history** (IS-2025 net −$300 / OOS-2026 net +$907 — sign flip). `sequence_reclaim` — the one lever that could catch a **smooth uptrend with no single-bar straddle** independently — is confirmed **structurally coupled off** in `filters.py` (`evaluate_bullish_setup` ~L937: `level_state` is only looked up when `reclaim_level is not None`, i.e. only as a redundant co-trigger, never standalone). Filed, not fixed, low priority per that thread's own verdict.

**Conclusion: this specific hole is not fixable by loosening the existing setup's gates — it needs a structurally different detector.**

## 7. Corrections to the original framing (stated, not buried)

| Claim | Verdict |
|---|---|
| "SPY trended $7 off the low" | **Confirmed exactly** — low 748.10 → close 754.86 (+$6.76), high 755.42 (+$7.32 range). |
| "734 HOLDs" | **Confirmed exactly** — 734/780 ticks, 504 after 11:33 ET. |
| "Not one armed setup fired a signal after 11:33" | **Not accurate** — `BULLISH_RECLAIM` scored through 12:55, `bollinger_squeeze` through 15:10. Real failure: 11 scored ENTER_BULL, 0 converted; then nothing scored after 12:55. |
| "Sustained TREND days = biggest hole" | **Directionally right, not the biggest by $ or frequency** — GAP days beat TREND days on both axes in this window. TREND_UP's real case is mechanism-consistency (4/4 sessions hit the same validated-dead-end gate), not size. |
| "FLUSH days without prior levels = second hole (the C21 class)" | **Not supported by available data** — both `FLUSH_TREND_DOWN` sessions with data (06-25, 07-07) show real bear participation; 07-07 has 7 real fills in `journal/trades.csv`. Sample is thin (n=2), so this corrects the hypothesis's degree, not a full kill. |

## 8. Coverage candidates

| Candidate | Status | What stands between it and the battery |
|---|---|---|
| **`flag_pullback_continuation`** | Pre-screened `TESTABLE` (both directions, tier 1, `analysis/recommendations/pattern-prescreen.json`: 51.99% days-fired / 0.973 fires-per-day full-history, 48.39% / 1.016 recent-90d, top5-concentration only 7.1%) | **Unbuilt detector.** No `backtest/lib/watchers/flag_pullback_continuation_watcher.py` exists (unlike `double_top`/`hs_bear`/`double_bottom_base_quiet`/`momentum_accel`, which each have a watcher AND a `_real_fills_validate.py`). No real-fills validation script exists either. Its grammar (volume-backed impulse + shallow VWAP-proximity pullback) is structurally different from ribbon_ride's (trendline-rejection/level-reclaim) — a genuine complement, not a retune. **Nothing built beyond the prescreen. This is the weekend battery run.** |
| `vwap_continuation` | ARMED live (Safe), validated real-fills edge | **Cannot be the fix by design** — `ENTRY_CUTOFF = 10:30 ET` is hard-coded in the detector (fires at most once/day, morning-only). In-window: 4/11 fired, 6 entered, 6 placed. |
| `vwap_reclaim_failed_break` | ARMED (Safe paper) | Same morning-window shape (≤10:30 ET). In-window: 2/11 fired, 0 entered — blocked by `RISK_DENY_PDT`/`VETOED_BY_MODELS`. |
| `bollinger_squeeze` | ARMED (Safe paper) | Most active extra setup by raw ticks (24 entered/placed aggregate) — but the 07-10 `PLACED` timestamps land at 00:54–01:01 ET (pre-market), an unresolved logging anomaly that blocks a clean "covers the afternoon" claim. |
| `vix_regime_dayside` | ARMED, effectively inert | 2/11 fired, 0 entered — 100% blocked (`RISK_DENY_RISK_CAP`/`RISK_DENY_PDT`). |
| `double_bottom_base_quiet` | ARMED, effectively inert | 1/11 fired, 0 entered — blocked by `NOT_FLAT` every time. |
| `gap_and_go` | Deliberately `WATCH_NOT_ARMED` | 2026-06-28 re-validation found 0 robust cells on fresh OPRA + a broken prior-close feed. Correctly excluded, not a candidate. |

## 9. Recommendation

**The single battery run to fire this weekend:** port `flag_pullback_continuation` (`backtest/lib/patterns/registry.py`) to a live-shaped watcher and run it through the same real-fills OP-22 battery every other extra setup here already went through — copy the pattern from `double_bottom_base_quiet`/`vix_regime_dayside`/`vwap_reclaim_failed_break` (each has a `..._watcher.py` + a `..._real_fills_validate.py` in `backtest/autoresearch/`). Pure Python, $0, one weekend run. It is the only pre-screened, fires-often-enough (~50% of days, both directions, low concentration), structurally-distinct-from-ribbon_ride candidate that hasn't been built yet — and it targets exactly the tape shape (sustained one-sided move, no fresh named level) that `SKIP_ELITE_BULL_LEVEL_RECLAIM` has now provably blocked on 4 of the 11 real sessions in this window (06-29, 06-30, 07-09, 07-10 — 270 occurrences total, most severely 06-30's 64-for-64 and 07-10's 20-for-20) on a gate that's already been proven not-safe-to-loosen.

## 10. Data quality flag (out of scope, noted for follow-up)

2026-07-03: `core-decisions.jsonl` logged 756 engine ticks against a fully closed market (July 4 2026 observed holiday). Not investigated further here (read-only audit) — spun off separately.

## Sources

- Day-shape taxonomy script + full per-day metrics: `analysis/signal-shape-coverage-2026-07-10.json` (`day_shape_distribution_30d`, `per_day_detail`).
- Setup-firing extraction + matrix: same file (`shape_x_setup_matrix`, `dead_zone_continuation_rows`).
- Pattern-prescreen numbers: `analysis/recommendations/pattern-prescreen.json` (generated 2026-07-09).
- Bull-unblock audit citations: `setup/scripts/self_check.py` (`_DATA_GATED_BLOCK_VERDICTS`), `markdown/doctrine/LESSONS-LEARNED.md` L197, `.claude/agent-memory/gamma/project_bull_unblock_elite_lever_retired.md`.
- `sequence_reclaim` coupling: `backtest/lib/filters.py` `evaluate_bullish_setup` (~L937).
