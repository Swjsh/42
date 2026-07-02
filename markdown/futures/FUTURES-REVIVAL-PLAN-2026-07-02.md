# Futures Revival Plan — Multiday Swing (MNQ/MES) — 2026-07-02

> **Directive (J, 2026-07-02):** keep 0DTE SPY running; revive the futures side for **multiday swing** trades. *"We get direction right but get eaten alive by theta."*
> **Status of this doc:** inventory verified on disk this session (every claim cites its file); build plan is the map — no code shipped with it.
> **Scope:** paper autonomous per the standing grant; **real futures money is J-gated LIVE** (OP-0 #1 — and futures losses are not capped at margin, so the bar is *higher* than arming paper options ever was).

---

## 0. The evidence that triggered this (why futures, why now)

Three independent studies this week converged on the same shape — **real direction alpha, destroyed by 0DTE option mechanics**:

1. **E2 null-controlled replay** ([`analysis/j-webull/E2-machine-management-replay.md`](../../analysis/j-webull/E2-machine-management-replay.md)): J's 2021-23 entry moments carry a 59.2% directional hit rate; machine exits on his entries flip −$13K to positive on every variant, while the **opposite-direction null control loses money** (P(sum>0)=0.085). Direction-attributable spread ≈ $253.6/trade (BS-sim, ranking-only per C1). The signal was real; management + deep-OTM strikes + theta were the leak.
2. **RIBBON_REJECTION_WICK kill** ([`analysis/recommendations/ribbon-rejection-wick.json`](../../analysis/recommendations/ribbon-rejection-wick.json), verdict FAIL 2026-07-02): 16 of 24 combos survive Benjamini-Hochberg FDR against the random-entry null (null expectancy −$23.53 short / −$33.41 long per trade — the *option premium bleed floor*), several with 63-66% WR — yet **every combo fails OOS expectancy and slippage-breakeven**. Beats random, killed by the instrument's carry cost.
3. **J's own career** (C31 / WeBull fresh-eyes 2026-07-01): the real kernel is 59.2% direction + at-PD-level/aligned/midday context; the killers were averaging-down and no stops — not the read.

A linear instrument keeps the direction and deletes the theta. Futures are that instrument, and most of the groundwork already exists (below).

**Honesty check — the June counter-evidence:** [`analysis/futures-vs-options-control-2026-06-20.md`](../../analysis/futures-vs-options-control-2026-06-20.md) ran this exact hypothesis on the *old engine's* signals and returned **NO-EDGE-IN-SIGNAL** (44-50% directional read; full watcher fleet on real MES bars: 2,611 signals, −$26,127, WR 48%). That verdict binds the **old v3 watcher-fleet signal set**, not the new candidate pile (J's entry contexts, RRW short cohort, structure/level reads — none of which were in the June fleet). The June control is the *methodological template* to reuse; its verdict is why the kill-pile — not the v3 configs — is the seed list.

---

## 1. Inventory — what exists on disk (verified 2026-07-02)

### 1.1 Reference library — COMPLETE, current

[`markdown/futures/`](.) — built 2026-06-17 from primary sources, all cited in [`SOURCES.md`](SOURCES.md):

| File | Contents (verified) |
|---|---|
| [`README.md`](README.md) | The futures-vs-0DTE mentality reframe: linear P&L, no theta, point-based stops, quarterly roll (flat-by-EOD is a *choice*, not expiry defense), margin leverage, mark-to-market, Section 1256 60/40 tax |
| [`CONTRACT-SPECS.md`](CONTRACT-SPECS.md) | MNQ $2/pt ($0.50/tick), MES $5/pt ($1.25/tick), NQ/ES, continuous symbols `CME_MINI:MNQ1!`/`MES1!`, quarterly H/M/U/Z expiry, P&L formula matching `POINT_VALUE` in `tastytrade_paper.py` |
| [`MARGIN-LEVERAGE-RISK.md`](MARGIN-LEVERAGE-RISK.md) | Day vs **overnight/initial margin** (overnight = several hundred to ~$2K+ per micro — load-bearing for swing), margin-call mechanics, size-by-stop-not-by-margin rule |
| [`SESSIONS-ROLLOVER-TAX.md`](SESSIONS-ROLLOVER-TAX.md) | Globex hours (Sun 6pm–Fri 5pm ET, 5-6pm break), settlement, quarterly rollover mechanics, Section 1256 |

**Verdict: reuse as-is.** One gap: everything margin/session was written for *intraday*; the overnight-margin and roll-date sections become load-bearing for swing and need a swing-specific addendum (Phase 2).

### 1.2 The 3 scheduled tasks — ALL DISABLED (verified via Task Scheduler)

| Task | State (verified) | Last ran | What it executes |
|---|---|---|---|
| `Gamma_FuturesHeartbeat` | **Disabled** | Never (result 267011 = never run) | `setup/scripts/run-futures-heartbeat.ps1` → `Invoke-Claude` on [`automation/prompts/futures-heartbeat.md`](../../automation/prompts/futures-heartbeat.md), Haiku watch / Sonnet in-position, $0.25/tick budget, every 3 min RTH |
| `Gamma_FuturesPremarket` | **Disabled** | Never | `run-futures-premarket.ps1` → LLM premarket: MNQ levels, VIX gate, bias, journal seed ([`futures-premarket.md`](../../automation/prompts/futures-premarket.md)) |
| `Gamma_FuturesEod` | **Disabled** | 2026-06-17 (exit 0, once) | `run-futures-eod.ps1` → LLM EOD replay/review ([`futures-eod.md`](../../automation/prompts/futures-eod.md)) |

All three load `.env.tastytrade` into process env before firing (`run-futures-heartbeat.ps1` lines 8-16). A fourth prompt, [`futures-eod-flatten.md`](../../automation/prompts/futures-eod-flatten.md), survives on disk but its task was **deliberately removed 2026-06-17** (CHANGELOG: futures roll quarterly; flatten belongs as a heartbeat time-stop, not an expiry task) — for swing it stays dead by design.

**Key architectural note:** these are **LLM-heartbeat** tasks — the architecture the SPY side *retired* on 2026-06-25 in favor of the deterministic `heartbeat_core.py`. Revival should NOT re-enable them; it should build the deterministic equivalent (§2b).

### 1.3 Broker path — tastytrade sandbox; **auth VERIFIED LIVE this session**

- **Adapter:** [`backtest/futures/tastytrade_paper.py`](../../backtest/futures/tastytrade_paper.py) — `TastytradeBroker` with `connect / get_positions / is_flat (L76 ghost-prevention) / get_account_equity / place_bracket (entry LIMIT DAY + TP1 LIMIT GTC + STOP GTC + optional runner GTC) / cancel_all / close_position`. `WATCH_ONLY = True` (line 52), flipped back True by the 2026-06-21 readiness audit ("engine is an unbuilt stub… loaded gun"). GTC exit orders happen to be exactly what multiday swing needs.
- **Retired predecessor:** `ibkr_paper.py` (IBKR was never set up; tastytrade replaced it 2026-06-16, CHANGELOG).
- **OAuth helper:** [`setup/scripts/tastytrade_oauth.py`](../../setup/scripts/tastytrade_oauth.py).
- **Creds:** `.env.tastytrade` exists (repo root, 2026-06-17), **gitignored** (`.gitignore:2`, confirmed untracked via `git check-ignore` + `ls-files`). Keys present (names only): `TT_CLIENT_ID, TT_SECRET, TT_REFRESH, TT_SANDBOX, TT_ACCOUNT, TT_PROD_SECRET, TT_PROD_REFRESH`. ⚠ The **live-PROD token pair is still in the file — token rotation owed by J since the 2026-06-22 audit, still outstanding.**
- **$0 read-only auth ping (ran this session, raw REST, no SDK, no keys printed):**
  - `POST api.cert.tastyworks.com/oauth/token` (refresh grant) → **200**
  - `GET /customers/me/accounts` → **200, 1 account (5W\*\*\*\*59, margin)** — matches the CHANGELOG's sandbox account 5WW73759.
  - **Sandbox auth WORKS TODAY.** But the account listing returned `futures_approved=False` on the cert account — **order placement in cert is UNVERIFIED** and must be proven with a `dry_run=True` order before anything else trusts it (§2d).
- **Gap:** the `tastytrade` SDK is installed in **neither** `backtest/.venv` (3.10) nor system Python 3.13 (checked via `find_spec`) — whatever env verified connect on 2026-06-17 is gone. `pip install tastytrade` into `backtest/.venv` is a Phase-2 prerequisite. `databento` is also uninstalled; `yfinance` lives only in `backtest/.venv`.

### 1.4 Backtest support — REAL and passing TODAY

[`backtest/futures/`](../../backtest/futures/) is a full stack, not a stub:

- `instruments.py` (specs), `futures_sim.py` (linear point P&L sim), `risk.py` (**prop-firm kill-switch models**: Topstep EOD-trailing w/ lock, Apex intraday-trailing, `size_contracts()` = contracts from $-risk / (stop_pts × point_value) with hard cap), `data.py` (continuous-contract loader + RTH filter + 5m resampler + **back-adjusted-series doctrine** in the docstring), `fetch_data.py` (Databento puller), `run_native_backtest.py` (watcher fleet on real futures bars), `strategy_config_v3.py` / `strategy_config_v3_mes.py` (curated per-instrument configs — **instruments need separate configs**: MNQ config on MES = −$5,788), `futures_vs_options_control.py` (the instrument-swap control harness), `mine_winning_signals.py`, `tastytrade_paper.py`.
- **Test suite: `test_futures.py` — 64/64 PASSED in 0.70s, run this session** (`backtest/.venv` Python). Specs, P&L sim, prop risk, config isolation guards, data loading, E2E smoke — all green today.
- **Limitation for swing:** everything above is **intraday RTH 5m** — `data.py` filters to 09:30–16:00 and `futures_sim.py` assumes same-day exits. Multiday swing needs a horizon extension (overnight bars or daily/4h bars + gap-aware stop fills), which is *the* main net-new build (§2a, Phase 1).

### 1.5 Data on disk

`backtest/data/futures/` (verified, with end-dates read from file tails):

| File | Size | Coverage |
|---|---|---|
| `MNQ_1m_continuous.csv` / `MNQ_5m_continuous.csv` | 33 MB / 1.9 MB | 2025-01-02 → **2026-06-12 15:55 ET** (RTH only) |
| `MES_1m_continuous.csv` / `MES_5m_continuous.csv` | 31 MB / 1.8 MB | same window (RTH only) |
| `MNQ_native_rows.jsonl` / `MES_native_rows.jsonl` | 2,254 / 2,611 scored signals | per-row real VIX |

Source was **Databento GLBX.MDP3** free credits (one-time pull 2026-06-16); **no `DATABENTO_API_KEY` exists anywhere now** (checked env files + user env). yfinance (`NQ=F`/`ES=F`) is the documented sanity-only fallback (`data.py`: 1m ≤ 7d, 5m ≤ 60d — but **daily bars are unrestricted and 1h goes back ~730 days**, which is exactly the swing timeframe; the intraday limits that made yfinance useless for 5m backtests don't bite at daily/4h).
⚠ Cached bars are **RTH-only** — fine for entries/exits at RTH decision points, but overnight-gap risk modeling needs session-open prices (daily bars from yfinance carry the gap; good enough).

### 1.6 State, journal, prompts — scaffolding exists, all frozen at 2026-06-17

- `automation/state/futures/`: `position.json` (flat), `account.json`, `risk.json` ($2K start / $1,600 floor / −$200 day per `MARGIN-LEVERAGE-RISK.md` §risk-controls), `key-levels.json`, `loop-state.json`, tick snapshots — all last written 6/16-6/17. `would-be-trades.jsonl` **does not exist** → the watch-only engine never logged a single would-be trade. **The futures engine has zero trades of any kind, ever.**
- `journal/futures/`: `trades.csv` (header only, 0 rows — schema already includes `pnl_pts`), `2026-06-17.md`, `heartbeat-ticks.jsonl` (a few test ticks).
- Prompts: the 4 `automation/prompts/futures-*.md` files (§1.2) — well-written for the *intraday LLM* architecture; reusable as spec text, not as the engine.

### 1.7 Why it was shelved — and which reasons still stand

| # | Reason (source) | Still valid? |
|---|---|---|
| 1 | **Max-pool cost** — `Gamma_FuturesHeartbeat` DISABLED 2026-06-17 "shares Max plan rate-limit pool" ([`SCHEDULED-TASKS.md`](../../automation/state/SCHEDULED-TASKS.md) line 54, CHANGELOG 2026-06-17) | **OBSOLETE** — the SPY side proved the deterministic-engine pattern (LLM heartbeats retired 2026-06-25); a Python swing engine costs $0 from the pool. Also: swing cadence is 1 decision fire/day, not 1/min. |
| 2 | **Engine was an unbuilt stub** — broken VIX read, unwired levels, no watcher integration; WATCH_ONLY forced True (2026-06-21/22 readiness audit, quoted in `tastytrade_paper.py` lines 52-57 + CHANGELOG: "honest BUILDS, not production") | **STILL TRUE** — and revival should not resurrect that stub; it targets a different (simpler) architecture (§2). |
| 3 | **No validated futures edge** — the 2026-06-20 control returned NO-EDGE-IN-SIGNAL on the old fleet's signals | **Superseded in scope** — new candidate pile exists (§0); nothing arms until it passes the battery on futures bars. |
| 4 | **Live-PROD tokens in `.env.tastytrade` = loaded gun; rotation owed by J** | **STILL OPEN** (carried to §5). |

---

## 2. Build plan — multiday swing, minimal-new / maximal-reuse

**Design premise:** this is NOT the 0DTE engine pointed at a new symbol. Different cadence (days, not minutes), different risk problem (overnight gaps, margin, uncapped loss), different exit logic (ATR point stops, no theta clock). What ports wholesale is the **discipline stack** — gates, journaling, funnel instruments, verification culture.

### (a) Decision cadence — EOD decision fire + lightweight intraday monitor

- **Signal timeframe:** daily + 4h bars (resampled from the cached 1m + yfinance daily). Hold horizon 1-5 days.
- **One decision fire per day:** new task `Gamma_SwingCore` at **15:35-15:45 ET** (before the 16:00 CT settle, liquid RTH) — deterministic Python: read bars → compute setups → risk_gate → place/adjust GTC bracket via `TastytradeBroker`. No LLM on the hot path (mirror of `heartbeat_core.py` architecture, [`setup/scripts/heartbeat_core.py`](../../setup/scripts/heartbeat_core.py)).
- **Intraday stop monitor:** `Gamma_SwingMonitor` every 15 min during Globex-liquid hours — pure Python, $0: verify broker stop orders still live (GTC orders already rest at the broker — the monitor is *verification*, not execution), detect gap-through-stop, write heartbeat state for the visibility layer. NOT a 1-min LLM heartbeat. Reuses the never-blind beacon pattern (`sight_beacon.py`) with yfinance `NQ=F/ES=F` quotes as the un-blockable price read.
- **No EOD flatten** — by design (the 2026-06-17 flatten-removal decision, CHANGELOG). The time-stop becomes a **max-hold-days stop** (5 days) + a roll-date stop (never hold into the roll week without an explicit re-decision).

### (b) Discipline stack — port, don't rebuild

| SPY instrument | Futures-swing port |
|---|---|
| `risk_gate` in `heartbeat_core.py` (cap / min-contracts / kill-switch) | `size_contracts()` already in [`backtest/futures/risk.py`](../../backtest/futures/risk.py) — per-trade risk % on **ATR-based point stops**, margin-aware cap (overnight initial margin per contract ≤ free equity), floor semantics from `PropAccount` (EOD-trailing model fits overnight holds better than intraday-trailing) |
| Kill switch (Rule 5, per-account isolated) | Adapted for gap risk: daily-loss kill on **settlement marks**, plus a per-position rule — size so a 2×ATR adverse overnight gap ≤ the per-trade cap (stops don't protect through gaps; sizing does) |
| Fill funnel ([`setup/scripts/fill_funnel.py`](../../setup/scripts/fill_funnel.py)) | Same funnel, swing lane: signals → gated → placed → filled → managed → closed. The 2026-06-30 audit lesson (GREEN-while-dead) applies with full force — **the funnel is the measure from day one** |
| Dress rehearsal ([`setup/scripts/dress_rehearsal.py`](../../setup/scripts/dress_rehearsal.py)) | Nightly cert-broker rehearsal: auth → account → dry-run order → cancel. Proves "are-we-good-for-tomorrow" against the tastytrade cert env instead of claiming it |
| Honest digest / EOD | Extend the existing EOD digest with a swing section (positions held overnight, settle marks, funnel counts) — not a separate report |
| Journaling (`journal/futures/` + Rule 8) | Structure already exists (§1.6); `trades.csv` schema already has `pnl_pts` |
| Guard tests (`test_graduated_guards.py` culture) | Every revival fix ships with a pytest that REDs on regression; `test_futures.py` (64 green) is the base |
| `et_clock.py` discipline | Unchanged — settlement/roll windows are ET/CT sensitive |

### (c) Strategy seeds — the kill-pile is the candidate pile

Re-test on MES (primary — direct SPY×10 mapping; MNQ second) at 1-5-day horizons with ATR stops, through the **same battery discipline** (canonical battery: expectancy + OOS split + regime stratification + random-entry null + BH-FDR — [`backtest/autoresearch/backtest_design_swarm.py`](../../backtest/autoresearch/backtest_design_swarm.py), [`discovery_shadow_ledger.py`](../../backtest/autoresearch/discovery_shadow_ledger.py)):

1. **RRW short cohort** — 16 BH-FDR survivors, short-side expectancy positive pre-carry ([`ribbon-rejection-wick.json`](../../analysis/recommendations/ribbon-rejection-wick.json)); re-express as MES short with multiday horizon.
2. **E2 direction contexts** — at-PD-level ≤0.1% + VWAP-aligned + morning cell (E2 variant (c): 79.3% WR, n=29) and the broader midday/at-level families; detectors re-run on 2025-26, graded on futures bars.
3. **Structure/level reads** — `market_structure.py` BOS/CHoCH + trendline engine + key-level reclaim/reject, at daily/4h scale (these are J's actual craft, and swing is their native timeframe).
4. **Null control is mandatory per test** (the June control template, `futures_vs_options_control.py` methodology): every candidate must beat random-entry-same-horizon on the SAME bars, both directions reported, IS/OOS split at 2026-01-01.

**Explicitly NOT seeds:** the v3/v3_mes intraday watcher configs (their signal population was the June NO-EDGE verdict's subject), and ORB (killed on futures data, [`futures-edition-summary.md`](../../analysis/recommendations/futures-edition-summary.md)).

### (d) Broker path — what works TODAY vs needs building

| Layer | Status |
|---|---|
| tastytrade cert auth (OAuth refresh) | **WORKS — verified 200 this session** (§1.3) |
| Account read (equity/positions endpoints) | **WORKS** (accounts endpoint 200; adapter code for balances/positions exists, verified working 2026-06-17 per CHANGELOG) |
| `tastytrade` SDK installed | **MISSING** — `pip install tastytrade` into `backtest/.venv` (one command) |
| Order placement in cert | **UNVERIFIED** — cert account shows `futures_approved=False`; must prove with `dry_run=True` bracket. If cert can't take futures orders, fallback = watch-only paper via our own fill-sim against live quotes (the `would-be-trades.jsonl` lane that already exists in the adapter) while a tastytrade *live-account paper* alternative or prop-firm sim (Topstep — `risk.py` already models it) is evaluated |
| Bracket semantics | `place_bracket()` already places GTC exits — **multiday-compatible as-is**; needs only the no-OCA cancellation logic moved from the dead LLM prompt into the deterministic monitor |
| Sandbox quirk | Cert resets positions/orders **every 24h** (adapter docstring) — fine for auth/dress-rehearsal, **useless for holding a 3-day paper position** → multiday paper validation needs the own-fill-sim lane or a live-env paper account regardless. Plan for it now, not after surprise |

### (e) Data plan — free and sufficient

| Need | Source | Status |
|---|---|---|
| Backtest daily/4h, 2025-01 → 2026-06 | **Resample the cached Databento 1m** (RTH sessions) — on disk now | READY tonight |
| Backtest daily, deep history (5-10y) | yfinance `ES=F`/`NQ=F` daily (unrestricted) | free, fetch on demand |
| Backtest 1h/4h, ~2y | yfinance 1h (≤730d) → resample 4h | free |
| Gap/overnight modeling | yfinance daily open vs prior close (carries the gap the RTH cache lacks) | free |
| Live reads (monitor) | yfinance quotes + TradingView MCP `CME_MINI:MNQ1!/MES1!` (already proven, `futures-premarket.md`) | works |
| Data refresh 2026-06-12 → now | Small gap; yfinance 1h covers it. Databento re-pull only if a validated edge needs tick-grade fidelity (new key = J decision, §5) | acceptable |
| Provenance | Record every set in `analysis/backtests/data-versions.jsonl` (existing discipline) | port |

### (f) Phase gates — ordered by shortest-path-to-first-validated-swing-backtest

**Phase 1 — first validated swing backtest ($0, no broker, no new creds — data already on disk).**
Build `backtest/futures/swing_sim.py` (multiday extension: daily/4h bars, ATR stops, gap-aware fills — gaps fill at the open beyond the stop, never at the stop) + resample cached 1m → 4h/daily + run the §c seed list through the canonical battery with null controls. **Gate:** a scorecard at `analysis/recommendations/futures-swing-{seed}.json` per seed — pass or kill, published either way. *Everything else waits on one seed clearing this.*

**Phase 2 — broker + instruments (parallel-safe with Phase 1, small).**
`pip install tastytrade` into `backtest/.venv`; dry-run order proof against cert (resolves `futures_approved=False` question); nightly futures dress-rehearsal task; fill-funnel swing lane; swing addendum to `MARGIN-LEVERAGE-RISK.md` (overnight margin table, roll calendar); guard tests. **Gate:** dress rehearsal GREEN 3 consecutive nights.

**Phase 3 — paper swing engine (autonomous per standing paper grant).**
`swing_core.py` (deterministic, mirrors `heartbeat_core.py` stages: see → gates → risk_gate → act) + `Gamma_SwingCore` (daily 15:35 ET) + `Gamma_SwingMonitor` (15-min verify loop) + journal/decisions/state wiring + Discord/STATUS visibility surface (OP-33c: J can see held-overnight positions without asking). Trades ONLY setups that cleared Phase 1. **Gate:** first paper round-trip with the full funnel populated and an honest digest entry.

**Phase 4 — validation → J-gated LIVE decision.**
Paper bar (mirrors the 0DTE live threshold): **≥20 closed swing trades, WR ≥ 45%, positive expectancy on settle marks, ≤2 rule breaks, zero unexplained funnel drops.** Then and only then the LIVE conversation — which for futures includes: real account choice (tastytrade live vs prop firm), token rotation completed, overnight-gap risk sign-off. **Arming live futures = J FIRST, no exceptions** (OP-0 #1; uncapped-loss instrument).

---

## 3. TL;DR

- **Groundwork is ~70% real:** reference library complete; broker adapter + gitignored creds exist and **cert auth verified live today**; full backtest stack **64/64 green today**; 18 months of real MNQ/MES 1m bars on disk; state/journal scaffolding present. The futures engine itself never traded (0 trades, 0 would-be trades) and its LLM-heartbeat architecture is obsolete by our own 2026-06-25 migration.
- **The shelving reason (Max-pool cost) is obsolete** — the deterministic-engine pattern makes a $0 swing engine; and swing cadence is 1 fire/day anyway. What still stands: no validated futures edge yet (the June NO-EDGE verdict on the *old* signals), token rotation owed, cert order-path unverified.
- **The plan:** validate first, wire second. Phase 1 needs no broker, no creds, no new data — resample the cached bars and run the kill-pile (RRW shorts, E2 contexts, structure reads) through the existing battery discipline at 1-5-day horizons on MES.

## 4. Single fastest next step

**Resample the cached Databento 1m CSVs to daily/4h and run the first null-controlled multiday battery on the RRW short cohort + E2 at-level/VWAP-aligned contexts on MES** (`backtest/data/futures/MES_1m_continuous.csv` → `swing_sim` → scorecard). Zero new infra, zero creds, zero cost — and it answers the only question that gates everything else: *does the direction alpha survive on the linear instrument at swing horizons?*

## 5. Open questions for J

1. **Token rotation (owed since 2026-06-22):** live-PROD OAuth pair still sits in `.env.tastytrade`. Rotate/revoke the prod tokens (sandbox pair suffices for everything until Phase 4).
2. **Overnight risk appetite:** max contracts held overnight, and are **weekend holds** (Fri → Mon gap) allowed at all in the 1-5-day window? Plan default: no weekend holds until 20 paper trades.
3. **Paper venue if cert can't hold multiday positions** (24h resets + `futures_approved=False`): own fill-sim lane vs tastytrade live-env paper vs a Topstep sim account (`risk.py` already models Topstep). Plan default: own fill-sim lane first — it's the only one that needs nothing from anyone.
4. **Databento refresh:** OK to create a new key (fresh free credits, or ~$10-30) *if* a Phase-1 pass justifies tick-grade validation? yfinance covers Phase 1 as-is.
5. **Capital framing for live-someday:** dedicated futures account sizing, and whether the prop-firm route (Topstep/Apex eval) is preferred over self-funded — changes which kill-switch model (`eod_trailing` vs `intraday_trailing`) we harden first.

---

*Inventory session 2026-07-02. Verification quoted per OP-33: task states from `Get-ScheduledTask`; auth ping outputs OAUTH_STATUS=200 / ACCOUNTS_STATUS=200 ACCOUNT_COUNT=1 / PING_RESULT=AUTH_OK; test run `64 passed in 0.70s`; data end-dates read from CSV tails; cred key-names read without values. Nothing in this session placed an order, wrote live state, or touched production params.*
