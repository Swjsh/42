# Backtest-as-Heartbeat — Design Proposal

> **Status:** DESIGN — not yet implementation. Authored 2026-05-15 evening from J's directive: *"the backtest needs to start being more like a real trade. the backtest needs to act like a heartbeat to tell you about a trade or something to simulate a real setup."*
>
> **Author:** Gamma. **Reviewers:** J (decision authority).
>
> **Companion doc:** `docs/2026-05-15-LESSONS.md` (lessons L37, L42, L43 are the proximate motivators).
>
> **Operating principles invoked:** OP 11 (Karpathy reproducibility), OP 14 (WR not primary), OP 16 (J's edge measurement), OP 17 (3-of-3 + grind-until-done), OP 19 (self-healing pipeline), OP 20 (non-theatre validation), OP 22 (don't stop cooking).

---

## TL;DR

Build a **replay-heartbeat** that walks historical RTH bar-by-bar at simulated real-time pace, calling the same heartbeat decision logic that fires live, with the same closed-bar discipline, the same MCP-style data fetches (mocked), the same order placement (mocked), the same fill-confirmation polling — and writes the same decision/position/journal state files as a live session.

This is **not a replacement** for the batch grinder (`backtest/autoresearch/runner.py`). It is a NEW validation tier that sits **between** the batch grinder and live trading:

```
Batch grinder (fast, parallel, 1000+ combos/day)
    → Replay-heartbeat (slow, serial, 1 combo/day, behavior-faithful)
    → Live paper trading (real-time, 1 day at a time)
    → Live real-money
```

The replay-heartbeat catches failure modes the batch grinder cannot see: closed-bar latency on fast-V days (L37), partial-fill ambiguities, EOD-flatten edge cases, MCP-call timeouts, watcher-vs-heartbeat race conditions, and the gap between "the math works on the chart" and "the prompt actually makes that decision when the data lands."

**Recommended decision:** ship **Phase 1** (single-day, single-combo, console output) in the after-4pm work block this week. Defer Phases 2 (parallelize across days) and 3 (integrate with grinder for ratification) until Phase 1 surfaces ≥ 1 behavioral gap the batch backtest could not have caught.

---

## 1. Motivation — what gaps this fills

### 1.1 Failure modes the batch backtest cannot simulate

The current batch backtest (`backtest/autoresearch/runner.py` + `backtest/lib/filters.py`) is fast, parallel, deterministic, and **runs faster than real-time with full bar lookahead per-tick**. It is a great tool for parameter sweeps and J-edge measurement. It cannot reproduce:

| Failure mode | Why batch misses it | Real-world example |
|---|---|---|
| **Closed-bar latency on fast-V reversals** | Batch sees every bar's full OHLC at once; the latency between "bar prints" and "heartbeat tick observes it" is collapsed to zero. | L37 — engine 09:46 entry at $3.14 vs J's 09:41 entry at $1.51. Batch would say "valid setup, entry on 09:45 close." Live reality: the 09:40 wick AND recovery happened in the same bar that triggers entry. |
| **Partial-fill ambiguity** | Batch fills at one premium per bar. Live fills can be partial, slipped, or stuck on a limit. | 5/12 EOD-flatten partial-fill — 13 of 15 contracts liquidated, 2 went to expiry, 200-share assignment. Batch never saw this. |
| **MCP-call timeouts mid-tick** | Batch reads CSV bars; no network in the loop. | 2026-05-15 10:18 ET heartbeat tick timed out; next tick at 10:21 ET reported stale SPY 748.32 / VIX 16.42 (per journal). Batch cannot generate stale data. |
| **Watcher-vs-heartbeat race conditions** | Batch runs one detector at a time; the live system runs watchers AND heartbeat in parallel processes. | 5/13 ORB warmup bug (L35) — fresh-process state reset. Batch has one process. |
| **EOD-flatten edge cases** | Batch closes at 15:55 ET row deterministically; live EOD-flatten polls Alpaca for position-actual, retries on errors. | EOD-flatten partial-fill blind spot (CLAUDE.md lessons absorbed). |
| **Decision/journal/state file mutations during the day** | Batch writes one summary row per simulation; live writes 100+ state files per session. | A heartbeat that updates `loop-state.json` mid-day and then re-reads it has a different code path than a batch-evaluator with one global state dict. |
| **Time-of-day ordering effects** | Batch can score bar N before bar N-1 in some parallel paths. Live is strictly sequential. | Any state machine (ORB ratchet, ODF, ribbon) — batch parallelization can hide order-dependent bugs. |

The batch backtest is **optimization-shaped**. The live system is **time-shaped**. A faithful replay must be time-shaped too.

### 1.2 What we don't currently have

We currently have these validation surfaces:

| Surface | Speed | Faithfulness to live | Cost |
|---|---|---|---|
| Batch grinder (`runner.py`) | ~50 combos/sec | LOW (no time, no MCP, no state file I/O) | ~$0/run (pure Python) |
| `simulator_real.py` (OPRA fills) | ~5 days/sec | MEDIUM (real fills, but still batch evaluator + no live state) | ~$0 |
| Live paper trading | Real-time, 1 day at a time | PERFECT (it IS the live system) | ~$0.30/day |
| Backtested heartbeat replay | **MISSING** | Should be HIGH | TBD |

The missing tier is what J asked for: *"act like a heartbeat to tell you about a trade or something to simulate a real setup."*

### 1.3 Per OP 16 (J's edge is the source of truth)

J's 09:41 P738 trade today exposed a gap: when J takes a manual trade, the engine should be able to tell us "would Monday's engine have taken the same trade?" — and the answer right now requires guesswork. The batch backtest can SAY yes/no on the 5m bar grid; the replay-heartbeat can SAY yes/no on the live tick stream WITH the closed-bar gate WITH the watcher state machines WITH the partial-fill simulation.

Per OP 16: edge_capture is computed from `sum(engine_pnl on J winning days)`. If the engine's "would have" answer is wrong by 5 minutes of latency, the J-edge measurement is wrong. The replay-heartbeat tightens this measurement.

### 1.4 Per OP 20 (non-theatre validation)

A "ready" claim currently requires: (1) account-size, (2) sample-bias, (3) OOS test, (4) real-fills, (5) failure-mode enumeration, (6) concentration. The replay-heartbeat adds a 7th: **(7) live-faithfulness** — the same code path that fires Monday at 09:35 ET produced the same decision in replay. No more "the math worked on the chart but the prompt didn't pick it up."

---

## 2. Architecture

### 2.1 Module layout

```
backtest/
  replay_heartbeat/
    __init__.py
    main.py                  # CLI entry: python -m backtest.replay_heartbeat --date 2026-05-15 --setup BEARISH_REJECTION_RIDE_THE_RIBBON
    clock.py                 # SimulatedClock — wall-clock time replaced with bar-aligned sim time
    data_feed.py             # ReplayDataFeed — drop-in replacement for TradingView MCP + Alpaca MCP reads
    order_router.py          # ReplayOrderRouter — drop-in replacement for Alpaca order placement, simulates fills against OPRA bars
    state_writer.py          # ReplayStateWriter — writes loop-state, decisions.jsonl, current-position.json into a per-run scratch dir
    heartbeat_runner.py      # Wraps automation/prompts/heartbeat.md invocation OR a Python re-impl of the heartbeat decision logic
    watcher_runner.py        # Mirrors automation/state/watcher-live invocation
    fixtures.py              # Loads SPY 5m bars + OPRA option bars + today-bias.json + VIX + ribbon + HTF stack
    report.py                # Renders a markdown trade-card and a JSON eod-deep-equivalent
  tests/
    replay_heartbeat/
      test_clock.py
      test_data_feed_freshness.py    # asserts no in-progress bars leak (per L34)
      test_order_router_partial.py
      test_state_isolation.py        # one run does not bleed into another
      test_end_to_end_5_15.py        # full replay of 2026-05-15, expects 1 entry at $3.14 / 1 exit at $2.37
```

### 2.2 Interfaces

The core abstraction: **the heartbeat logic doesn't know it's in replay**. Same prompt, same code paths, same I/O contract — only the SOURCES are mocked.

```python
# data_feed.py
class ReplayDataFeed:
    """Drop-in for mcp__tradingview__* and mcp__alpaca__* read tools."""
    def __init__(self, date: str, sim_clock: SimulatedClock):
        self._bars_5m = load_spy_5m_bars(date)       # full day, tz-aware ET
        self._opra = load_opra_cache(date)            # all strikes, 1-min OPRA
        self._vix = load_vix_5m_bars(date)
        self._clock = sim_clock

    def quote_get(self, symbol: str) -> dict:
        """Returns the last bar's close that is <= sim_clock.now() - 5s freshness margin."""
        now = self._clock.now()
        bar = self._bars_5m[self._bars_5m["bar_close_et"] <= now].iloc[-1]
        return {"symbol": symbol, "last": bar["close"], "ts": bar["bar_close_et"].isoformat()}

    def data_get_ohlcv(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        """Returns the last N CLOSED bars. Filters per L34: bar.close_et + 5min <= sim_clock.now()."""
        now = self._clock.now()
        closed = self._bars_5m[self._bars_5m["bar_close_et"] + pd.Timedelta(minutes=5) <= now]
        return closed.tail(count).to_dict(orient="records")

    def get_option_chain(self, ...) -> ...:
        """Returns chain snapshot as of sim_clock.now(), pricing each strike from OPRA cache."""

    def get_account_info(self) -> dict:
        """Returns simulated account state from ReplayStateWriter."""
```

```python
# order_router.py
class ReplayOrderRouter:
    """Drop-in for mcp__alpaca__place_option_order."""
    def __init__(self, opra_cache, sim_clock, slip_model):
        self._opra = opra_cache
        self._clock = sim_clock
        self._slip = slip_model

    def place_option_order(self, symbol, qty, side, type, limit_price=None) -> dict:
        """Simulates fill against the OPRA 1-min bar at sim_clock.now() (+0–60s)."""
        # Lookup the OPRA bar covering [now, now+60s]
        # If market order: fill at mid + slip
        # If limit order: fill if limit is within bar's H-L range; else stuck (queue for next bar)
        # Returns Alpaca-shaped order dict
```

```python
# clock.py
class SimulatedClock:
    """Wall-clock time replaced with bar-aligned sim time. Advances on tick() calls."""
    def __init__(self, start: datetime, end: datetime, tick_seconds: int):
        self._now = start
        self._end = end
        self._tick = tick_seconds  # e.g. 180 for 3-min heartbeat cadence

    def now(self) -> datetime:
        return self._now

    def tick(self) -> None:
        self._now += timedelta(seconds=self._tick)

    def done(self) -> bool:
        return self._now >= self._end
```

### 2.3 Time simulation strategy

The heartbeat fires every 3 min in live. Replay mirrors this exactly:

- Start: 09:30:00 ET. End: 15:55:00 ET. Tick interval: 180 seconds.
- Per tick: advance sim clock → call heartbeat decision logic with current data-feed view → process any resulting orders via order router → update state writer → log decision to scratch `decisions.jsonl`.
- Replay-heartbeat is **strictly sequential within a day**. No parallelization across ticks (that would defeat the purpose). Parallelization only across DAYS (Phase 2).

### 2.4 Data feed mocking strategy

The fidelity question is: how close is `ReplayDataFeed` to what the live MCP returned?

| Field | Strategy | Faithfulness |
|---|---|---|
| `quote_get.last` | OPRA 1-min bar close ≤ sim_now | HIGH (the same bar live would have read) |
| `data_get_ohlcv` | 5m bars filtered by closed-bar rule | HIGH (mirrors L34 fix exactly) |
| Option chain | Per-strike OPRA mid at sim_now | HIGH if OPRA cache covers all strikes; MEDIUM otherwise |
| VIX | VIX 5m bars filtered by sim_now | HIGH |
| Ribbon EMAs | Computed live from SPY bars up to sim_now (no lookahead) | HIGH |
| HTF 15m stack | 15m bars filtered by closed-bar rule | HIGH |
| Account equity | Replay-state running balance | HIGH (we control this) |
| News calendar | Reads `automation/state/news.json` snapshot from `data/snapshots/news-{date}.json` if it exists, else the current `news.json` (and we flag it as stale-replay-source) | MEDIUM-LOW (news.json was not snapshotted historically — see Risks) |

The biggest fidelity gap is the **option chain at sim_now**: OPRA gives us the prices, but the "chain snapshot" the live engine sees includes Greeks, OI, and bid/ask spread that OPRA aggregates do not have at 1-min resolution. **Mitigation:** for Phase 1, replay treats chain as `{strike, expiry, type, mid, spread_assumption=5c}` only. Greeks and OI are computed from BS (with skew adjustment) OR omitted — and the heartbeat decision logic doesn't use them anyway (verified by reading `automation/prompts/heartbeat.md`).

### 2.5 State isolation

Every replay run gets its own scratch directory:

```
backtest/replay_heartbeat/runs/
  2026-05-15_BEARISH_REJECTION_b7c4a2e_v15.1/
    decisions.jsonl
    loop-state.json
    current-position.json
    journal.md           # synthesized as replay progresses
    trade_card.html      # final artifact
    run_meta.json        # {date, setup, params_hash, code_hash, opra_data_hash, start, end}
```

`run_meta.json` follows OP 11 reproducibility: `run_id = {date}_{code_hash[:8]}_{data_hash[:6]}_{params_hash[:6]}`. Replaying the same inputs ALWAYS produces the same outputs.

### 2.6 Where the heartbeat decision logic lives in replay

Two options for executing the heartbeat decision:

**Option A — Re-invoke the live prompt via `claude --print`.** Faithful to the live system (same model, same prompt, same tool surface). Cost: each tick is a $0.05–$0.15 invocation; a full day = 127 ticks = $6–$19/day. A weekend grinder run over 60 days = $360–$1140. **Too expensive for routine use.**

**Option B — Python re-implementation of the heartbeat decision logic.** Cheaper, deterministic, but introduces a NEW source of drift (the Python re-impl can diverge from the prompt — exactly the foot-gun OP 4 forbids). **Lower fidelity unless we lock the two via cross-tests.**

**Recommendation: hybrid.**
- **Phase 1 (sanity tier):** Python re-impl. The re-impl is essentially `backtest/lib/filters.py` with `ReplayDataFeed` injected — we already have this code. Replay-heartbeat in Phase 1 is `filters.py` driven by the simulated clock + the state writer + the order router. Cost ~$0/run.
- **Phase 3 (high-fidelity tier):** spot-check via `claude --print` invocation on N=10 ticks per day where the Python re-impl said "enter trade." If the prompt-driven version disagrees, that's a drift event — log it, surface it in the EOD pipeline, fix the drift. Cost ~$1–$3/day for spot-checks.

This keeps the routine cost at $0 while still validating the Python re-impl against the prompt at decision-critical moments.

---

## 3. Cost-vs-accuracy tradeoff

### 3.1 Speed comparison

| Backend | Wall-clock for 60-day replay | Combos per second |
|---|---|---|
| Batch grinder (`runner.py`) | ~20 sec for 60 days × 1000 combos | ~3000 combos/sec |
| `simulator_real.py` (OPRA) | ~12 sec for 60 days × 1 combo | ~5 days/sec |
| **Replay-heartbeat (Phase 1)** | ~3–5 min for 60 days × 1 combo | ~0.2 days/sec |
| Live paper | 6.5 hrs/day | N/A |

Replay-heartbeat is **~60× slower than `simulator_real.py`** because it runs the full decision-logic + state-writer + order-router loop on every 3-min tick (127 ticks/day vs `simulator_real.py`'s ~1 evaluation/bar = 78 bars/day).

### 3.2 Accuracy comparison

| Backend | Closed-bar latency | Partial-fill | MCP stale data | EOD-flatten edge | Watcher race |
|---|---|---|---|---|---|
| Batch grinder | NO | NO | NO | NO | NO |
| `simulator_real.py` | NO | partial | NO | NO | NO |
| Replay-heartbeat Phase 1 | **YES** | **YES** | partial (via injected timeouts) | **YES** | **YES** |
| Live paper | YES | YES | YES | YES | YES |

Replay-heartbeat fills 4 of 5 accuracy gaps the batch grinder cannot reach.

### 3.3 Dollar cost

Per OP 3 (cost-effectiveness gate, $100/mo Max 5x plan budget):

| Workload | Cost (Phase 1, Python re-impl) | Cost (Phase 3, with prompt spot-check) |
|---|---|---|
| Single-day replay (e.g., 2026-05-15) | ~$0 | ~$1–$3 |
| 60-day backfill replay | ~$0 | ~$60–$180 (one-shot; or $1–$3 incremental per new day) |
| Nightly EOD validation (1 day) | ~$0 | ~$1–$3 |
| Weekly weekend re-replay (5 days) | ~$0 | ~$5–$15 |

Phase 1 is essentially free. Phase 3 (prompt spot-check) is bounded at $5–$15/week — fits in the $100/mo budget easily.

### 3.4 Where replay-heartbeat is WORSE than batch

It is worse for **parameter sweeps**. Replay-heartbeat runs ~5 days/min for one combo. The grinder does ~5,000 combo-days/sec. For finding the right v15.x knob settings across a 1500-combo grid × 60 days, the grinder is **20,000× faster**. Replay-heartbeat is NOT a grinder replacement.

**The two play different roles:** grinder finds candidates; replay-heartbeat validates the survivors with live-fidelity.

---

## 4. Implementation phases

### 4.1 Phase 1 — Minimal (1 day at a time, console output)

**Scope:** single-day, single-combo replay, prints decisions to console + writes scratch dir. No parallelization. No prompt invocation (Python re-impl only).

**Deliverables:**
- `backtest/replay_heartbeat/` skeleton (8 files per layout above)
- `tests/replay_heartbeat/test_end_to_end_5_15.py` — replays 2026-05-15 with v15.1 params, asserts: 1 entry at $3.14 ± $0.05 at 09:46:38 ± 60s, 1 stop-exit at $2.37 ± $0.05 at 09:50:32 ± 60s. **This is the regression test for the entire system** — it must reproduce TODAY's actual engine behavior.
- `--date YYYY-MM-DD --setup <setup_name> --params <path>` CLI
- Markdown trade-card output at `backtest/replay_heartbeat/runs/{run_id}/trade_card.md`

**Acceptance:**
1. `python -m backtest.replay_heartbeat --date 2026-05-15 --setup BEARISH_REJECTION_RIDE_THE_RIBBON --params automation/state/params.json` reproduces TODAY's trade to within ±5¢ of fill price and ±60s of fill time.
2. The trade card surfaces the closed-bar lag explicitly: "Setup confirmed at 09:45:00 close (live tick 09:40 wick already absorbed). Entry latency: 6:38."
3. Run is deterministic — same inputs produce byte-identical outputs (verify by running twice + diffing scratch dirs).
4. `run_meta.json` includes `code_hash`, `data_hash`, `params_hash` per OP 11.

**Effort estimate:** 1 evening's work block (4–6 hours).
- `ReplayDataFeed` + `SimulatedClock`: ~2 hours
- `ReplayOrderRouter` (mid-fill, slip model): ~1 hour
- `ReplayStateWriter` + scratch dir: ~30 min
- Wiring + tests: ~1–2 hours

**Where to start:** copy `backtest/lib/filters.py` (existing batch evaluator) and replace its global state with `ReplayStateWriter` instance. Replace its data accessors with `ReplayDataFeed` injection.

### 4.2 Phase 2 — Parallelize across days

**Scope:** replay 60 days in parallel using `multiprocessing.Pool` (per OP 15 — `MAX_PARALLEL_RESEARCH_WORKERS = 4`, NEVER thread-based). Aggregate results into a `replay-heartbeat-report-YYYY-Www.json` weekly summary.

**Deliverables:**
- `backtest/replay_heartbeat/pool_runner.py` — `multiprocessing.Pool(4)`, one day per worker
- Aggregation: `replay-heartbeat-aggregate.py` rolls 60 days into Sharpe, expectancy, max-DD, edge-capture (per OP 16)
- Weekly cron task `Gamma_ReplayHeartbeatWeekly` — Sunday 17:00 ET

**Acceptance:**
1. 60 days replays in < 20 min (4-way parallel, ~5 days/min per worker)
2. Per-day results match Phase 1 single-day runs (idempotency check across parallelization)
3. Weekly summary includes the same six OP-20 disclosures (account size, sample bias, OOS, real-fills, failure modes, concentration)
4. **Within-day strict serial preserved** — only across-day parallelism; Phase 1's deterministic guarantee holds per day

**Effort estimate:** 1 evening's work block (3–5 hours), assuming Phase 1 is shipped and stable.

**Deferral condition:** ship Phase 1 first. Run it on 5–10 historical days. Only build Phase 2 if Phase 1 surfaces concrete bugs that a 60-day backfill would catch. If Phase 1 reveals nothing new in 5 days, the batch grinder is doing enough — Phase 2 is unnecessary.

### 4.3 Phase 3 — Integrate with grinder for ratification

**Scope:** the grinder's Stage 5 ratification step calls replay-heartbeat on its top-N candidates. Drops candidates that pass batch but FAIL replay-heartbeat (closed-bar lag, partial-fill, EOD edge). Also adds the optional `--prompt-spot-check` flag that fires `claude --print` against the live prompt on N entry ticks to validate Python re-impl.

**Deliverables:**
- `backtest/autoresearch/stage5_replay_ratification.py` — Stage 5 gate
- Drift report `analysis/recommendations/{rule_id}_replay_drift.json` — lists candidates that failed replay
- Spot-check sub-mode for prompt validation

**Acceptance:**
1. Stage 5 runs on the top-5 candidates from Stage 4, takes ~30–60 min (5 candidates × 60 days / 4 workers)
2. Any candidate that fails replay (different P&L by > 5% vs batch, OR different trade count) is logged with a drift narrative
3. Prompt spot-check (10 ticks/day across 5 days) fires < $5 of token spend
4. Auto-ratify (per OP 11 "thresholds_4_of_4") now requires REPLAY pass as the 5th gate

**Deferral condition:** Phase 2 stable and weekly summary actually surfacing replay-vs-batch divergences. If Phases 1+2 show batch and replay always agree, Phase 3 is overhead with no signal. Stop here.

**Effort estimate:** 1–2 evening work blocks.

---

## 5. Reuse opportunities

What can be lifted directly:

| Component | Source file | Reuse strategy |
|---|---|---|
| Heartbeat decision logic | `automation/prompts/heartbeat.md` | Phase 3 prompt-driven spot-check only. NOT a direct Python translate. |
| Filter math (ribbon spread, VIX direction, level proximity, BEAR stack check, level break confirm) | `backtest/lib/filters.py` | Direct reuse. This is already the Python encoding of the heartbeat logic. The drift between this file and the prompt is the OP 4 foot-gun the `/gamma-sync` skill exists to prevent. |
| OPRA 1-min bar loader | `backtest/lib/simulator_real.py` | Direct reuse for `ReplayOrderRouter` fill simulation. |
| Strike picker | `backtest/lib/strike_picker.py` | Direct reuse. |
| Bar load + ribbon EMA computation | `backtest/lib/ribbon.py`, `backtest/lib/spy_bars.py` | Direct reuse for `ReplayDataFeed`. |
| HTF 15m stack | `backtest/lib/htf.py` | Direct reuse. |
| VIX state | `backtest/lib/vix.py` | Direct reuse. |
| Watcher fleet | `lib/watchers/*.py` + `backtest/autoresearch/watcher_live.py` | Wrap in `WatcherRunner` that uses `ReplayDataFeed` instead of yfinance. The L33 yfinance-silent-skip fix is already there; replay-heartbeat inherits it. |
| Counterfactual computation (per L42 fix) | `analysis/eod_deep/counterfactual_engine.py` (to be built per L42) | Reuse for trade-card "what would v14 have done" comparisons. |
| Trade card HTML template | `journal/trade-card-2026-05-14.html` | Adapt for replay-heartbeat trade cards. Add "replay vs live actual" diff block. |

**Reuse principle:** every Python module in `backtest/lib/` is a candidate for inclusion. Replay-heartbeat is essentially "the same library, driven by a clock instead of by a batch loop."

---

## 6. Risks and unknowns

### 6.1 Risks

1. **Drift between Python re-impl and the live prompt (OP 4 foot-gun).** Phase 1 uses `backtest/lib/filters.py`. The live engine uses `automation/prompts/heartbeat.md`. The `/gamma-sync` skill (loaded today) exists explicitly to keep these in sync. Replay-heartbeat's value DEPENDS on `/gamma-sync` being kept current. If `filters.py` drifts from `heartbeat.md`, replay reports a false PASS on a setup the live engine wouldn't take. **Mitigation:** Phase 3 prompt spot-check + nightly drift detection in EOD pipeline.

2. **OPRA cache coverage gaps.** Replay needs OPRA 1-min bars for every strike the engine might pick. Today's OPRA cache covers the days documented in `data/opra_cache/`. Days outside the cache fail open (no OPRA = no fill simulation possible). **Mitigation:** add `data/opra_cache_index.json` listing all cached date-strike pairs; replay-heartbeat refuses to run on a day with missing strikes (fail closed, not silent fail).

3. **Snapshotted news / today-bias / params not historically preserved.** `news.json` is a live state file — there's no `data/snapshots/news-2026-05-15.json`. Replaying 2026-05-12 with TODAY's news.json is fiction. **Mitigation:** the EOD pipeline should snapshot `news.json`, `today-bias.json`, `params.json`, and `key-levels.json` per-day going forward (queue task for tonight's wake fires). Historical replay before snapshot rollout uses "best-effort historical context" with a disclaimer in the trade card.

4. **Sim clock drift from real-world clock.** Live heartbeat fires at wall-clock 09:30, 09:33, 09:36, etc. — but actually with jitter and occasional misses. Replay fires perfectly every 180s. The mismatch is small but real. **Mitigation:** in Phase 2, inject simulated jitter from the actual `automation/state/heartbeat-loop-state.json` history. This is OP-20 disclosure-grade detail.

5. **Watcher state-machine warmup parity (L35).** Live watchers are stateful and use the T82 warmup loop. Replay must mirror this EXACTLY. **Mitigation:** Phase 1 test suite includes a watcher-state parity test that runs `lib/watchers/orb_watcher.py` in replay vs live-style invocation and asserts state machines reach the same state at end-of-day.

6. **Scope creep.** Replay-heartbeat could grow into a 5,000-LOC framework. Phase 1's value cap is "find ≥ 1 bug the batch couldn't catch within 2 weeks of shipping." If it doesn't surface a bug, stop building. **Mitigation:** OP 17's grind-until-done has a target — phase-2/3 deferrals are encoded above with explicit "deferral condition" checkpoints.

### 6.2 Unknowns

1. **Will Phase 1 actually reproduce today's trade exactly?** The hypothesis is yes; the verification is the regression test. If Phase 1 says "engine would have entered at 09:46 at $3.18, not $3.14" — that's a 4¢ slip we need to explain (and either bug-fix or document as the expected variance).

2. **How much does OPRA 1-min granularity matter vs 5-sec ticks?** Live MCP reads SPY at sub-second resolution; OPRA 1-min bars compress that. For 5m-bar-resolution decisions this is fine. For the SHOTGUN_SCALPER live-tick trigger (L37 + `SHOTGUN_SCALPER.md`) it might NOT be fine — a 1-min OPRA bar can mask a 20-second rejection wick. **Investigate during Phase 1.**

3. **Should replay-heartbeat run the v14 frozen rules in parallel with v15.1 for shadow-diff scorecard?** Could be a Phase 4 — already overlaps with the existing shadow-version controller (`automation/state/shadow-version.json`). Defer until Phase 1 ships.

4. **Cost of running replay on EVERY entry the live engine makes, vs only on weekly review?** If we run it nightly on yesterday's session, ~$0/night (Python re-impl). If we run with prompt spot-check, ~$1–$3/night. Affordable either way; the question is when the signal-to-noise crosses below the time-cost of reviewing the report.

5. **Whether the replay-heartbeat report should be Discord-pinged to J in the morning summary.** Could be valuable for surfacing closed-bar drift events. Could also be noise. **Decide after 1 week of live data.**

---

## 7. Recommended decision

### 7.1 Ship Phase 1 in the after-4pm work block this week (OP 22)

**Why now:**
- L37 (today's closed-bar lag failure) and L43 (engine missed setups) are CURRENT problems. Phase 1 is the structural diagnostic surface for both. Without it, the next L37-equivalent failure is invisible until J catches it again.
- The OP 22 work cadence has 8 hrs/evening of available work-block. Phase 1 is 4–6 hrs.
- Phase 1 is essentially free (~$0 token spend, no infra cost).
- Reuse is high — every module in `backtest/lib/` is a building block. Phase 1 is glue + a clock + a state writer + a test.

**Acceptance gate before declaring Phase 1 done:**
1. Regression test `test_end_to_end_5_15.py` passes.
2. Trade card output for 2026-05-15 explicitly identifies the closed-bar lag as the loss driver (with the 09:40 wick → 09:45 close timeline).
3. Determinism verified: two runs of the same inputs produce byte-identical outputs.
4. Per OP 20: trade card includes the 6 disclosures (account-size, sample-bias, OOS — N/A for a single-day replay but stated explicitly, real-fills source = OPRA, failure modes = list any silent-fail paths, concentration = N/A single-trade).

### 7.2 Defer Phases 2 and 3 until Phase 1 proves value

**Phase 2 (parallelize across 60 days):** worth ~3–5 hours of build effort. Defer until Phase 1 has been run on 5+ historical days and the question "what would happen if we ran this on the whole backfill?" actually has a payoff in sight. If Phase 1 reproduces history perfectly with no new findings, Phase 2 adds 60× output but the same zero-finding rate.

**Phase 3 (grinder integration + prompt spot-check):** worth ~6–10 hours of build effort. Defer until Phase 2 has actually flagged ≥ 1 replay-vs-batch divergence on a grinder candidate. If batch and replay always agree, Phase 3 is theatre.

### 7.3 Cross-references back to lessons (L37–L44)

- **L37 (closed-bar lag):** Phase 1 trade card explicitly diagnoses this on 2026-05-15. Future days flagged automatically. Replay-heartbeat is the structural diagnostic surface for the closed-bar latency family.
- **L38 (OPRA HWM):** ReplayOrderRouter uses OPRA fills, so HWM/TP1 reachability is computed from real bars — no more "would have hit TP1" myths.
- **L40 (documentation ≠ enforcement):** Phase 1 is itself an enforcement artifact — the regression test against today's actual trade IS the encoded check.
- **L41 (SHOTGUN_SCALPER birth):** Replay-heartbeat is the validation surface for SHOTGUN_SCALPER's watch-only promotion path (OP 21 gate "3+ historical observations that grade as wins" runs through replay).
- **L42 (EOD pipeline bugs):** Phase 1's trade-card output replaces / supplements the buggy counterfactual generator. Phase 1 produces what `eod-deep` couldn't today.
- **L43 (missed setups):** Phase 1 produces a decision log per tick. Aggregating "decided NO" ticks gives missed-setup enumeration for free.
- **L44 (multi-agent API drift):** Phase 1's contract is locked in this doc + in the `replay_heartbeat/` module interfaces. Future agent work on this module receives the contract verbatim.

### 7.4 What "done" looks like at end of Phase 1

A single command:

```
python -m backtest.replay_heartbeat \
    --date 2026-05-15 \
    --setup BEARISH_REJECTION_RIDE_THE_RIBBON \
    --params automation/state/params.json \
    --output backtest/replay_heartbeat/runs/
```

Produces:

```
backtest/replay_heartbeat/runs/2026-05-15_BEARISH_REJECTION_<hash>/
  trade_card.md                # Markdown summary with timeline + closed-bar diagnosis
  decisions.jsonl              # All tick decisions (entered, blocked-why, skipped-why)
  trades.json                  # Synthetic trades.csv-shaped row
  loop_state.json              # Final state
  run_meta.json                # OP 11 reproducibility stamp
```

And the trade card includes a section like:

```
## Closed-bar lag diagnosis (L37)

  Setup confirmation tick: 09:46:00 ET (heartbeat tick after 09:45 bar close)
  Setup-defining event:    09:40:00 ET (5m bar low 737.96 touched Carry 738.10)
  Latency:                 6 min 38 sec
  SPY price at event:      737.96 (live tick during 09:40 bar)
  SPY price at entry:      738.64 (live tick at confirm)
  SPY price retraced:      +$0.68 during latency window
  Option premium at event: $1.49 (P740 OTM mid)
  Option premium at entry: $3.14 (engine paid)
  Cost-basis gap:          $1.65 (premium worse due to latency)

  Recommendation: SHOTGUN_SCALPER live-trigger branch (DRAFT, watch-only).
  See strategy/playbook/SHOTGUN_SCALPER.md.
```

That is the diagnostic surface J asked for: *"act like a heartbeat to tell you about a trade."*

---

## 8. Appendix: open design questions for J

These are deliberately not decided in this doc and should be confirmed before Phase 1 ships:

1. **Run cadence for Phase 1.** On-demand (J or wake fire invokes manually)? Nightly auto-run on yesterday's session? Both?
2. **Trade card delivery.** Saved to `backtest/replay_heartbeat/runs/` only? Or also rendered as part of EOD-deep `analysis/eod-deep-*.json`? Or both?
3. **Should replay surface its findings to Discord in the morning summary?** (default in this doc: NO — wait until proven valuable)
4. **Where to put the snapshot rollout for news.json / today-bias / params?** Phase 1 dependency or Phase 2?
5. **Phase 1 SHOTGUN_SCALPER replay scope.** Reproduce today's actual ride-the-ribbon trade FIRST, then add SHOTGUN_SCALPER replay as a separate test once `SHOTGUN_SCALPER.md` doctrine is implemented in `filters.py` or a new `lib/shotgun.py`?

Default answers (this doc's recommendation): (1) on-demand for Phase 1, nightly in Phase 2; (2) both — `runs/` is primary, EOD-deep gets a `replay_heartbeat_summary` field referencing the run_id; (3) NO until proven valuable; (4) Phase 1 dependency for the rollout going forward (replay of FUTURE days will have snapshots), Phase 2 dependency for historical replay; (5) RIDE-THE-RIBBON first; SHOTGUN second once doctrine has code.

---

*End of design proposal. Next step pending J approval: scaffold `backtest/replay_heartbeat/` per the layout in Section 2.1.*
