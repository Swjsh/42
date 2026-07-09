# Futures Revival Phase 1 — MES Multiday Swing Battery — Summary

> **VERDICT: KILL, all 3 seeds.** `rrw_short` KILL · `e2_context` KILL · `structure_bos_choch` KILL.
> Zero of 96 tested cells clear the pre-registered PASS gate (OOS mean > 0 AND BH-FDR survivor at
> alpha=0.05 AND beats its own buy-and-hold-same-horizon benchmark). Per plan section 2f Phase 1:
> **"everything else waits on one seed clearing this."** Nothing cleared it — Phase 2/3 of the
> futures revival (broker wiring, paper swing engine) are **not unlocked**.
>
> Run: 2026-07-09, `backtest/futures/run_swing_battery.py`, `backtest/.venv`, 20.1s runtime, $0.
> Source: `backtest/data/futures/MES_1m_continuous.csv` (Databento GLBX.MDP3 back-adjusted
> continuous, md5 `22f02f1d45d3...`, 508,586 1-minute bars, verified **full ETH Globex session**
> 2025-01-01 18:00 ET → 2026-06-12 16:59 ET — see "Data corrections" below). Daily series extended
> 2026-06-12 → 2026-07-08 via yfinance `ES=F` (16 rows, disclosed lower-fidelity gap-fill, daily
> seeds only). 1 MES contract, $5/pt, $2.50/side commission+slippage ($5.00/round-turn),
> IS/OOS split 2026-01-01, ATR(14) stop 1.5×/target 3.0× (fixed, not gridded), BH-FDR α=0.05.

## Important: this is the SECOND independent Phase-1 pass

A prior, more granular battery already ran **2026-07-02** (commits `3c31bf2`, `950a3b6`,
`backtest/futures/analysis/PHASE1-swing-battery/`) at RTH-5m-signal / ETH-5m-fill granularity,
covering substantially the same RRW-short and E2-context hypotheses (plus daily structure as a
*filter*, never a standalone entry). **Verdict: `DOES_NOT_TRANSFER`, 0/12 test cells cleared
BH-FDR.** That result was never logged to `CHANGELOG.md` — fixed this session (see below).

**This scorecard is a genuinely independent second pass**, not a re-run of the first: it uses
DAILY/4h-of-RTH signal bars (this work order's explicit spec, vs. the prior battery's RTH-5m
signal timeframe), a new reusable `swing_sim.py` module (vs. the prior one-off `swing_battery.py`
script), and one genuinely new seed — **structure BOS/CHoCH traded directly as the entry signal**,
which the prior battery never tested (it only used daily structure as an alignment filter on other
signals, and found only 39 daily structure events in 18 months — too rare to trade on its own at
daily granularity; this pass runs it at 4h scale instead, where it fires far more often: 258
events). **Two independent implementations, two different signal granularities, the same
conclusion** — that is about as strong a converging kill as $0 research produces.

## Data corrections made this session

1. **The plan doc's "RTH 1m" premise is wrong** (already caught by the 2026-07-02 session, and
   independently re-verified from scratch this session): `MES_1m_continuous.csv` is **full ETH
   Globex** data (RTH bars are only 27.7% of the file; first row is 2025-01-01 **18:00 ET**;
   verified maintenance-break gap empty 17:00–18:00 ET + overnight 02:00 ET prints present). Real
   overnight/weekend gap bars are native to the cache through 2026-06-12 — no synthetic gap
   modeling was needed for that span.
2. **Found and fixed a real bug** in `backtest/futures/data.py::load_continuous_csv`: a continuous
   CSV spanning a DST transition (this file crosses two) parses its mixed `-05:00`/`-04:00`
   timestamp strings to `object` dtype on current pandas, and the `.dt` accessor then raised
   `AttributeError`. Regression test: `test_futures.py::TestDataLoading::
   test_load_continuous_csv_handles_mixed_dst_offsets`.
3. My own daily resample (`data.resample_daily`) was cross-checked against the prior session's
   independently-computed `derived/MES_daily_rth.csv`: **0.0 max abs difference** on open/high/
   low/close across all 367 rows — two independently-written resamplers agree exactly.

## Seed-by-seed verdict table

| Seed | Bars | Combos | Cells tested | BH-FDR eligible (OOS n≥5) | Clearing | Verdict |
|---|---|---|---|---|---|---|
| A — `rrw_short` (RRW ribbon-rejection-wick, both directions) | daily | 8 | 48 (×2 dir ×3 horizon) | 36 | 0 | **KILL** |
| B — `e2_context` (at-PD-level + VWAP-aligned) | daily | 2 | 12 | 12 | 0 | **KILL** |
| C — `structure_bos_choch` (BOS/CHoCH, standalone entry, NEW) | 4h-of-RTH | 6 | 36 | 24 | 0 | **KILL** |

Full cell tables, nulls, regime splits, and disclosures: `analysis/recommendations/
futures-swing-rrw_short.json`, `futures-swing-e2_context.json`, `futures-swing-structure_bos_choch.json`.

## What killed each seed (the honest read, ranked by how close each got)

### Seed A — RRW-short: the cleanest kill (no cherry-picking possible)

**All 24 short-direction eligible cells (138 total OOS trades) have a negative-or-zero OOS mean.
Zero exceptions.** The long mirror's best cell (`rrw_w0.35_lb5_any`, 1d, OOS n=11) reaches only
+$57.61/trade with p=0.45 (nowhere near significant) and its "edge" exactly equals its own
buy-and-hold benchmark ($57.61 both) — i.e., not the wick-rejection pattern doing anything, just
whatever residual drift the entry dates happened to sit in. 10/36 eligible cells flip sign
IS→OOS. Disclosed non-portable component: the detector's day-relative volume filter
(`vol_mult_min`) has no meaning at daily granularity (exactly one bar/day — "today's prior bars"
is always empty) and was fixed at 0.0 for every combo rather than faked; see
`backtest/futures/seeds/rrw_seed.py` docstring.

### Seed B — E2 context: instability, and the "good" cell is just beta

**9 of 12 eligible cells flip sign IS→OOS** (more unstable than Seed A). The long side's best cell
(`e2_tol0.001`, 5d horizon) looks the most interesting on paper: IS is **negative**
(-$128.93/trade, n=38, WR 47%) and OOS **flips positive** (+$359.68/trade, n=18, WR 78%,
raw p=0.02). But the buy-and-hold-same-horizon benchmark on the *identical* OOS entry bars is
**+$364.10** — *better* than the actual ATR-stop/target signal. The at-level+VWAP context isn't
predicting anything here; any long position opened on those 18 dates and held 5 days would have
made slightly more money, because 2026 H1 was simply an uptrend (regime split confirms it: VIX≥17.5
subset alone is +$612/trade, VIX<17.5 subset is only +$44/trade — the "edge" concentrates entirely
in the higher-vol/bigger-trend days). This is exactly the "pure long-bias artifact of the 2025-26
uptrend" the battery's `beats_buy_and_hold` gate exists to catch, and it caught it. Disclosed
non-portable component: the "morning 10:00-11:00" time-of-day filter has no meaning on a bar that
spans the whole RTH session — skipped, not faked (see `e2_context_seed.py` docstring).

### Seed C — structure BOS/CHoCH (the new seed): a "too good" trap, correctly caught by BH-FDR

The single most eye-catching raw number in the whole battery: `structure_w3_BOS` long, 5-day
horizon, OOS **n=6, WR=100%, mean=+$529.37/trade, raw p=0.009**. On its own this would look like
the best result in the battery. It is not evidence of an edge: **6 winning trades in a row is
easy to get from chance**, its own buy-and-hold benchmark (+$560.21) is again *better* than the
signal, and — the discipline working as designed — **BH-FDR correction across the seed's 24
eligible cells fails it** (surviving rank 1 alone at α=0.05 needs p≤0.0021; 0.009 doesn't clear
it). This is the textbook shape of a small-sample fluke, not a discovery, and the pre-registered
battery gate refused to be fooled by it. Frequency note: window=2 (more sensitive fractal) fires
far more than window=3, and `trade_on=BOS` (continuation) outnumbers `CHoCH` (reversal) roughly
1.15:1 — neither knob shows a stable direction of effect once BH-FDR is applied.

## Both-direction / regime disclosure (mandatory, per battery discipline)

- **No seed is short-only or long-only positive with the other side silent** — every seed's
  "best" cell was checked against its own opposite direction and against buy-and-hold. RRW-short
  is uniformly negative on the named (short) cohort itself; E2 and structure's apparent long-side
  strength is beta, not signal (above).
- **VIX regime split** (>=/< 17.5) shows every seed's better-looking cells concentrate in the
  higher-VIX / bigger-trend-day bucket — consistent with "caught some of 2026 H1's drift," not
  with a repeatable pattern-based edge.
- **Buy-and-hold-same-horizon** beats the actual signal in every top cell examined across all
  three seeds. This is the single most consistent finding of the whole battery.

## Cross-check against the 2026-07-02 battery

| | 2026-07-02 (5m-signal, ETH-5m-fill) | 2026-07-09 (this pass, daily/4h-signal) |
|---|---|---|
| RRW-short (tradeable freq.) | Train-negative, never reached test | OOS-negative on all 24 eligible cells |
| RRW-short (rare, vol≥2.5) | Train+/test+, but n=3-4, p=0.14-0.49, statistically empty ("parked, not disproven") | Not re-tested at daily scale (this pass fixed the vol filter off entirely, disclosed) |
| E2 context | Train+ (2025) → test− (2026 H1), sign flip, opposite-dir null wins | Train− → test+ sign flip (opposite direction of flip, same instability signature); test+ fully explained by buy-and-hold |
| Structure (as filter/entry) | Filter only, 39 events/18mo, too rare, never independently traded | **NEW**: traded directly at 4h, 258 events; best cell looks great raw, fails BH-FDR |
| **Verdict** | **DOES_NOT_TRANSFER** | **KILL, all 3** |

Same bottom line reached twice, independently, at two different signal granularities.

## Disclosures

- Fixed exit shape (ATR(14)×1.5 stop / ×3.0 target, not gridded) — sweeping the exit knob was
  explicitly out of scope this pass (the 2026-07-02 battery already swept 36 exit shapes across a
  cousin seed pile and found the exit knob doesn't rescue a losing signal; re-sweeping here would
  not have changed a kill driven by sign-instability and beta-explains-it, not exit mechanics).
- `MIN_OOS_N = 5`: cells below this are reported in the full JSON cell tables but excluded from
  the BH-FDR family and can never register as a PASS — pre-committed before the run, not chosen
  after seeing results.
- E2 context ran on the **native Databento window only** (through 2026-06-12) — VWAP needs
  intraday RTH bars, which were not re-fetched for the yfinance gap period. RRW ran on the
  **extended** window (native + 16 yfinance `ES=F` gap-fill days through 2026-07-08, disclosed
  lower-fidelity). Structure (4h) ran on the **native window only** (yfinance daily can't produce
  a 4h split).
- Back-adjusted continuous series: absolute price levels are roll-shifted for older dates; every
  signal here is relative (ribbon, PD levels, VWAP, ATR, swing structure) so this is internally
  consistent (same caveat the 2026-07-02 battery and `data.py`'s own docstring already carry).

## Session housekeeping

- Fixed the `load_continuous_csv` DST bug (above), with regression test.
- Appended the missing CHANGELOG.md entry for the 2026-07-02 `DOES_NOT_TRANSFER` battery (it had
  never been logged) plus this session's work.
- New reusable module: `backtest/futures/swing_sim.py` (ATR stops, gap-aware fills, max-hold-days
  exit, buy-and-hold benchmark helper) + `backtest/tests/test_swing_sim.py` (24 tests) +
  `backtest/tests/test_swing_seeds.py` (15 tests, including a no-look-ahead regression proof for
  the structure seed) — available for any future Phase-1b/2 work regardless of this verdict.

## Honest one-paragraph read: does ANY seed justify Phase 2/3?

**No.** Two independently-built batteries, at two different signal granularities, three months
apart in methodology but one week apart in wall-clock time, both return a clean kill on
essentially the same candidate pile: RRW-short has no edge on the linear instrument at any swing
horizon tested (this pass's cleanest result — literally zero of 138 OOS short trades average
positive), the E2 at-level+VWAP context is unstable across IS/OOS and its apparent OOS edge is
fully explained by simply holding through the same window (not by the context), and the one
genuinely new idea — trading BOS/CHoCH structure directly rather than using it as a filter —
produced a single eye-catching small-sample result that BH-FDR correctly refused to certify. The
"linear instrument deletes the theta, keeps the direction" thesis (plan section 0) is not wrong in
principle — J's underlying directional read is real (E2's own source study, the BS-sim ranking-only
replay, still shows genuine signal in his entry *moments*) — but **none of the three re-expressions
in this kill-pile carry that signal onto MES at 1-5 day ATR-stop swing horizons**. Per the plan's
own gate discipline ("everything else waits on one seed clearing this"), Phase 2 (broker wiring)
and Phase 3 (paper swing engine) remain unjustified by evidence. The productive next move, if this
line of research continues, is not re-testing this exact pile a third way — it is mining a
genuinely different candidate (the RRW rare/high-quality cohort the 2026-07-02 battery explicitly
parked as "not disproven," or a fresh structure-only idea at a longer lookback with a pre-committed
larger minimum-n bar) rather than grinding the same three signals against the same instrument
again.
