# 42 FUTURES EDITION — HANDOFF & RUNBOOK

> **Purpose:** This is a complete, self-contained handoff prompt for a fresh chat to finish the
> Futures Edition and start paper-trading futures **tonight**, using a Databento API key.
> Read it top-to-bottom once, then work the RUNBOOK (§6). Everything you need — context, decisions,
> file map, environment gotchas, exact commands — is here. Author: Gamma, 2026-06-14.

> **You are picking up a working build.** The futures backtest engine exists, all 11 strategies have
> been tested on a 16-month S&P (MES) proxy, and a curated, regime-gated config nets **+$14,243 / 16mo
> in-sample**. Your job: (1) pull REAL MNQ/MES data with the Databento key, (2) re-run on true Nasdaq,
> (3) validate OUT-OF-SAMPLE, (4) wire IBKR paper trading, (5) start cooking.

---

## 0. QUICKSTART — the first hour tonight

```
1. Read §5 (ENVIRONMENT GOTCHAS) first — they will waste hours if you don't know them.
2. Put the Databento key in an env var (NEVER hardcode it): export DATABENTO_API_KEY=db-...
3. Run §6 Step 1 — pull MNQ + MES 1-min historical (check cost first with metadata.get_cost).
4. Run §6 Step 2 — build continuous series, normalize to the engine bar schema.
5. Run §6 Step 3 — re-run the all-strategy backtest on REAL MNQ and MES.
6. Run §6 Step 4 — OOS walk-forward of curated v2b. THIS is the make-or-break test.
Then decide: if v2b survives OOS on real data → start §6 Step 6 (IBKR paper). If not → iterate (§6 Step 4b).
```

---

## 1. MISSION & WHY FUTURES

**Project Gamma** is an autonomous SPY **0DTE options** trading engine (see `CLAUDE.md`). It reads price
action via a TradingView MCP, detects setups with a fleet of "watchers," sizes positions, journals every
trade, and places paper orders via Alpaca. It trades on signal-driven intraday directional setups.

**The problem we found:** the *entries* are good (directional win-rates are solid), but **0DTE option theta
+ delta + premium-stop misfires destroy otherwise-good trades.** A Reddit futures trader (NQ/MNQ) inspired
the question: do these same setups make money on **futures**, where there's no theta and P&L is linear?

**The answer (proven):** YES for several strategies. We reran every watcher over 16 months with **futures
point-P&L instead of options P&L** and the marginal/negative options strategies became profitable as
futures. ORB went from regime-locked-marginal to **+$23.58/trade, 68.8% WR**. See §3.

**The goal:** a "Futures Edition" of Gamma trading **MNQ (Micro Nasdaq) and MES (Micro S&P)** micros — small
enough for a small account — reusing the SAME engine and strategies, NOT 0DTE. Eventually paper-trade it on
IBKR, then (J's call) go live on a prop firm.

---

## 2. CURRENT STATE — WHAT'S BUILT (file map)

All under the repo root `C:\Users\jackw\Desktop\42` (bash mount: `/sessions/<id>/mnt/42`).

### The futures module — `backtest/futures/`  (NEW, this is the Futures Edition)
| File | What it does |
|---|---|
| `instruments.py` | MNQ/MES/NQ/ES specs: point value, tick, `spy_to_index` proxy factor, round-turn cost. `get("MES")`. |
| `futures_sim.py` | `simulate_futures(direction, entry, stop, tp1, runner, future_bars, instrument, qty)` → point-P&L bracket sim (net of commissions + 1-tick slippage). **Replaces the entire options pricing/Greeks/theta layer.** |
| `risk.py` | `PropAccount` (Topstep EOD vs Apex intraday-trailing drawdown models) + `size_contracts()`. |
| `data.py` | Continuous-contract CSV loader (FirstRate/Databento), `rth_only()`, `pull_yfinance()` (sanity), Databento snippet. Normalizes to engine bar schema. |
| `run_futures_backtest.py` | **Resumable, time-budgeted** harness. Runs `run_all_watchers` over the data, grades each signal with `futures_sim`, streams rows to JSONL, checkpoints to a state file. Driven across many short calls. |
| `tradingview.py` | TV MCP futures capability: symbol map (`CME_MINI:MNQ1!`/`MES1!`), `chart_config()`, `CHART_READER_RECIPE`. Reuses the identical `mcp__tradingview__*` toolset as SPY. |
| `strategy_config.py` | **The iterated curated config** — `CURATED_V2B_RULES` + `should_take(watcher, dir, conf, vix)`. The futures analog of `params.json`. |

### Reused UNCHANGED (the "same engine" promise) — `backtest/lib/`
- `lib/watchers/` — every watcher (ORB, ERL→IRL, ribbon/level bearish-rejection, shotgun, TBR, LBFS, NLWB,
  double-bottom, H&S, RSI-div, bullish, …). They operate on OHLCV bars and are instrument-agnostic.
- `lib/filters.py`, `lib/ribbon.py`, `lib/levels.py`, `lib/orchestrator.py` — context-building (ribbon, levels, HTF, VIX).
- `lib/watchers/runner.py::run_all_watchers(...)` — runs the whole fleet per bar, returns deduped signals.

### Results & docs
- `FUTURES-EDITION-2026-06-14.md` — plan, architecture, decisions, results, roadmap. **Read this too.**
- `analysis/recommendations/futures-mes-stage1-results.json` — per-strategy × direction × confidence results + curated v1/v2b.
- `analysis/recommendations/futures-mes-signals.jsonl` — raw 3,695 signal rows (date, watcher, setup, dir, conf, net, outcome). Re-usable for analysis without re-running.

### Related prior work (context, not futures)
- `strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md` — the Reddit ORB-15 + ERL→IRL
  options watchers (watch-only, failed options real-fills). `backtest/lib/filters.py::detect_fvg()` is the
  reusable FVG primitive that came out of it.

---

## 3. RESULTS SO FAR (what works, the numbers, the honest caveats)

**Setup:** rerun all 11 watchers over our existing 16-month SPY 5m data (2025-01-01 → 2026-05-22), grade
each signal with MES point-P&L. **MES proxy: ES/MES track S&P 500; SPY ≈ S&P500/10, so SPY price × 10 ≈
ES/MES index level.** qty=3, net of $1.24 round-turn + 1-tick slippage/side, RTH only.

### Per-strategy (raw, both directions)
| watcher | 16-mo net | WR | note |
|---|---:|---:|---|
| **orb_watcher** | **+$755** | 68.8% | **cleanest edge, +$23.58/trade, all long** |
| bearish_rejection_morning | +$53 | 59% | J's real anchor edge (4/29, 5/04), ~breakeven, short |
| tbr_high_vol | −$818 | 47% | but **LONG +$1,403** / short −$2,220 |
| shotgun_scalper | −$5,002 | 44.5% | but **LONG +$2,506** / short −$7,508 |
| erl_irl | −$4,367 | 73% | **loses on futures too** → bad detector, not a theta victim |
| (lbfs, nlwb, rsi_div, orb15, bullish, bearish_reversal) | all negative | — | R:R mismatch / wrong-regime |

### The iteration ("change it up") → CURATED v2b
Drop short-side momentum, add a **VIX≥16 regime gate**, restrict ERL→IRL to its one working slice
(short/high/VIX-16–22). Encoded in `strategy_config.py`.

| Version | 16-mo net (MES) | WR | $/trade | quarters positive |
|---|---:|---:|---:|---:|
| Curated v1 (long-bias + ORB + morning-rej) | +$4,716 | 47.3% | +$3.80 | 4/6 |
| **Curated v2b (regime-gated)** | **+$14,243** | 54.5% | **+$16.50** | **6/6** |

### ⚠️ HONEST CAVEATS — do not skip
1. **MES = S&P proxy, NOT real MNQ (Nasdaq).** The whole engine was tuned on SPY (S&P). MES is the fair
   port; **MNQ/Nasdaq is untested** — the proxy literally cannot produce Nasdaq bars. THIS is why Step 1 is
   pulling real data.
2. **v2b is IN-SAMPLE slice selection.** Picking the slices that won on the same data always looks good.
   The VIX≥16 gate is mechanistically sound (momentum needs volatility), but the specific per-slice VIX
   cuts risk overfit. **OOS walk-forward (Step 4) is the real test.** Treat +$14,243 as a hypothesis.
3. **Long bias leans on the 2025-26 bull regime.** Every short side bled. Watch regime dependence.
4. **Stage-1 fidelity:** RTH-only, simplified bracket fills, 1-tick slippage, no overnight, no real fills.
   A signal, not a live-ready P&L.

---

## 4. LOCKED DECISIONS (researched 2026-06-14 — don't re-litigate without reason)

| Topic | Decision | Detail |
|---|---|---|
| **Instruments** | MES + MNQ micros | MNQ $2/pt, MES $5/pt, tick 0.25 ($0.50 / $1.25). Quarterly roll H/M/U/Z, 3rd Fri. Globex ~23h. Micros = small-account friendly. |
| **Backtest data** | **Databento GLBX.MDP3** | `$125` free signup credits. `ohlcv-1m`. Continuous front-month `MNQ.c.0` / `MES.c.0`. ~2yr 1-min for both ≈ **$2–5** of credit (call `metadata.get_cost()` first). Historical only — live data needs a paid sub (irrelevant for backtest). Backup: FirstRate Data (one-time CSV). yfinance `=F` only 7d(1m)/60d(5m) — sanity only. |
| **Continuous contract** | **Roll-adjusted, NEVER raw spliced** | Use Databento continuous symbology (`.c.0`) or back-adjusted series. Raw splicing fabricates P&L on roll dates (the #1 futures-backtest footgun). Back-adjusted (Panama) for point strategies; ratio-adjusted for %-returns. |
| **Paper-trading venue** | **Interactive Brokers paper** | IB Gateway (headless, Docker/Xvfb) + `ib_async` (maintained fork of ib_insync). Port 4002 = paper. Native MNQ/MES brackets + fill callbacks. **Prop-firm APIs (TopstepX/ProjectX) REJECTED — they ban VPS/remote/unattended.** Tradovate = paid fallback ($25/mo + funded acct). |
| **Chart/levels** | **Same TV MCP, futures symbols** | `CME_MINI:MNQ1!` / `CME_MINI:MES1!`. 10-min delayed by default (fine for pattern reading); real-time = ~$7/mo CME add-on. |
| **Risk layer** | Topstep (EOD fixed floor) + Apex (intraday trailing) encoded | `futures/risk.py`. The futures kill-switch + sizing. |

---

## 5. ⚠️ ENVIRONMENT GOTCHAS — READ BEFORE TOUCHING CODE (these wasted hours; don't repeat)

1. **Cowork FUSE mount serves TRUNCATED views of files you just edited via the file tools (L78).** After a
   `Write`/`Edit`, the bash mount may show a stale/truncated copy for tens of seconds. **The authoritative
   files are correct (Windows side); only the bash view lags.** Practice: **do ALL build + validation in a
   sandbox-native `/tmp` working copy**, then deliver to the repo via the file tools (Write/Edit) or `cp`,
   and verify with the `Read` file tool (authoritative), NOT bash.
2. **Background processes are KILLED when a bash cell exits.** `nohup ... &` does NOT survive to the next
   call. → Use the **resumable/time-budgeted** pattern (`run_futures_backtest.py` already does this:
   `--budget 38` processes ~37 days then checkpoints; re-invoke to continue until `reached_end: true`).
3. **Bash calls hard-timeout at ~45s.** Size every long job to finish under that, or make it resumable.
4. **Fresh bytecode:** prefix python with `PYTHONPYCACHEPREFIX=/tmp/pyc` to avoid stale `.pyc` from the mount.
5. **Deps in the sandbox:** `pip install <pkg> --break-system-packages`. You'll need `pandas`, `numpy`,
   `scipy`, `pytest`, and for data `databento`, `yfinance`. (scipy is needed by `lib/pricing.py`.)
6. **Running the harness as a module fails** — `autoresearch/__init__.py` imports a file the mount truncates.
   Run scripts as plain files (`python3 futures/run_futures_backtest.py`), not `-m autoresearch.x`.
7. **Recommended working copy setup** (what the prior session used):
   ```bash
   GB=/tmp/gb; SRC=/sessions/<id>/mnt/42/backtest
   mkdir -p $GB && cp -r $SRC/lib $GB/lib && cp -r $SRC/futures $GB/futures \
     && cp -r $SRC/tests $GB/tests && ln -s $SRC/data $GB/data && ln -s $SRC/fixtures $GB/fixtures
   # build/validate in /tmp/gb, then deliver final files to the repo with cp + Read-verify.
   ```

---

## 6. THE RUNBOOK (do these in order)

### Step 1 — Pull REAL MNQ + MES historical data (Databento)
- Put the key in env: `export DATABENTO_API_KEY=db-xxxx` (NEVER hardcode/commit it).
- `pip install databento --break-system-packages`
- **Cost-check first**, then pull (snippet is in `futures/data.py::DATABENTO_SNIPPET`):
  ```python
  import os, databento as db
  c = db.Historical(os.environ["DATABENTO_API_KEY"])
  # Pull ~16-18 months to match/extend the existing SPY window.
  for sym in ["MNQ.c.0", "MES.c.0"]:
      cost = c.metadata.get_cost(dataset="GLBX.MDP3", symbols=[sym], stype_in="continuous",
                                 schema="ohlcv-1m", start="2025-01-01", end="2026-06-14")
      print(sym, "cost $", cost)            # expect well under $5 total
  data = c.timeseries.get_range(dataset="GLBX.MDP3", symbols=["MNQ.c.0","MES.c.0"],
            stype_in="continuous", schema="ohlcv-1m", start="2025-01-01", end="2026-06-14")
  df = data.to_df()                          # save per-symbol CSVs into backtest/data/futures/
  ```
- Resample 1-min → 5-min to match the engine's bar cadence (the watchers were built on 5m). Keep both.
- Save as `backtest/data/futures/MNQ_5m_continuous.csv` and `MES_5m_continuous.csv` (schema:
  `timestamp_et, open, high, low, close, volume`, tz America/New_York). Use `futures/data.py::load_continuous_csv`.

### Step 2 — Build the native-bars path in the harness
- `run_futures_backtest.py` currently loads SPY and uses the **proxy** (`spy_to_index=10`). Add a native
  mode: when given real MNQ/MES bars, pass `px_to_points=1.0` to `simulate_futures` (levels already in index
  points) and feed the futures bars directly to `run_all_watchers` (they only need OHLCV + a VIX series).
- **Important:** the watchers reference named price levels and a VIX series. For native futures bars you need
  a VIX alignment too (VIX is index-level, instrument-agnostic — reuse the existing VIX CSV, aligned by time).
  The levels engine (`_detect_from_history`) works on whatever bars you give it.
- Sanity: confirm a handful of signals fire and P&L is in a sane $ range for MNQ ($2/pt) vs MES ($5/pt).

### Step 3 — Re-run ALL strategies on REAL MNQ + MES
- Drive the resumable harness to completion for each instrument (this is the real test the proxy couldn't do):
  ```bash
  cd /tmp/gb && rm -f fut_rows.jsonl fut_state.json
  while true; do
    out=$(PYTHONPYCACHEPREFIX=/tmp/pyc timeout 44 python3 futures/run_futures_backtest.py \
          --inst MNQ --budget 38 2>/dev/null)
    echo "$out"; echo "$out" | grep -q '"reached_end": true' && break
  done
  ```
  (Repeat for MES. The `while` loop won't survive one cell — re-invoke per call until `reached_end: true`,
  ~13–16 calls for the full window. Each call resumes from the checkpoint.)
- Aggregate per watcher × direction × confidence (reuse the analysis in `futures-mes-stage1-results.json`).
- **Key question:** does ORB / long-momentum still win on **Nasdaq (MNQ)**? Nasdaq is more volatile than
  S&P — expect bigger point ranges and possibly different optimal gates.

### Step 4 — OUT-OF-SAMPLE walk-forward of curated v2b (THE make-or-break test)
- Split: **train = 2025-01-01 → 2025-12-31, test = 2026-01-01 → 2026-06-14** (or rolling 6-mo windows).
- Re-derive the curated slices + VIX gates **on TRAIN ONLY**, then apply UNCHANGED to TEST. Report test
  WR / $/trade / per-quarter. Gate: **OOS expectancy positive AND OOS/IS ratio ≥ 0.5** (same bar the options
  engine uses — see `docs/BACKTESTING-PLAYBOOK.md`).
- If v2b's edge is in-sample curve-fit, it will collapse OOS. If it survives, it's real.
- **Step 4b (if it fails):** the edge is probably ORB + one or two robust momentum slices, not the full v2b.
  Strip to what survives OOS. Prefer fewer, mechanistically-justified rules over a fitted slice salad.

### Step 5 — Stratification + concentration + costs
- Stratify by VIX regime and by quarter; check no single quarter/day is >40% of P&L (concentration flag).
- Stress costs: re-run with 2-tick slippage and higher commissions; the edge must survive realistic fills.
- Add roll-date handling sanity (continuous series should have no fabricated jumps).

### Step 6 — IBKR paper wiring (start paper-trading)
- Create an IBKR account (IBKR Lite, no min deposit) → enable a **paper** account. (J does this — account
  creation is a human step.)
- Run **IB Gateway headless** (Docker): `ghcr.io/gnzsnz/ib-gateway`, `TRADING_MODE=paper`, port 4002.
- `pip install ib_async`. Bracket order on MNQ (front-month dated contract, e.g. `MNQU2026`):
  ```python
  from ib_async import IB, Future
  ib = IB(); ib.connect('localhost', 4002, clientId=1)
  mnq = Future('MNQ', '202509', 'CME', multiplier='2'); ib.qualifyContracts(mnq)
  bracket = ib.bracketOrder('BUY', 1, limitPrice=21000, takeProfitPrice=21075, stopLossPrice=20950)
  for o in bracket: ib.placeOrder(mnq, o)
  ib.execDetailsEvent += lambda trade, fill: print("FILL", fill.execution.price)
  ```
- Build a **futures heartbeat** mirroring `automation/prompts/heartbeat.md` but: chart symbol
  `CME_MINI:MNQ1!`, P&L/stops in points, sizing via `futures/risk.py`, no theta/strike logic, IBKR instead
  of Alpaca. Start **WATCH-ONLY / paper** — log would-be trades before placing.
- Wire the futures risk layer (`PropAccount.would_violate()`) as the kill-switch before every entry.

### Step 7 — TradingView MCP futures chart-reader (live)
- The capability is built (`futures/tradingview.py`). In the futures heartbeat, replace
  `chart_set_symbol("BATS:SPY")` with `chart_set_symbol("CME_MINI:MNQ1!")`; everything else
  (`data_get_ohlcv` with the count=3 closed-bar fix, `data_get_study_values` ribbon, HTF switch,
  `capture_screenshot`, VIX via `TVC:VIX`) is identical. See `CHART_READER_RECIPE`.

### Step 8 — Schedule + go
- Add scheduled tasks (Windows Task Scheduler, like the options engine) for the futures heartbeat /
  premarket / EOD-flatten, registered in `automation/state/SCHEDULED-TASKS.md`.
- Keep it lean; respect the cost discipline (OP-3) and the rate-limit reminder in `CLAUDE.md` (no
  interactive sessions during market hours that starve the heartbeat).

---

## 7. REFERENCE

### Curated v2b rules (`backtest/futures/strategy_config.py`)
`should_take(watcher, direction, confidence, vix)` returns True iff a signal matches one of:
```
shotgun_scalper_watcher          long  medium  VIX>=16
shotgun_scalper_watcher          long  high    VIX>=16
tbr_high_vol_watcher             long  medium  VIX>=16
tbr_high_vol_watcher             long  high    VIX>=16
orb_watcher                      long  medium  VIX>=16
bearish_rejection_morning_watcher short medium  (all VIX)
bearish_rejection_morning_watcher short low     VIX>=22
erl_irl_watcher                  short high    16<=VIX<22
tbr_high_vol_watcher             short medium  VIX>=22
```

### Harness commands
```bash
# resumable backtest (re-invoke until reached_end:true)
PYTHONPYCACHEPREFIX=/tmp/pyc python3 futures/run_futures_backtest.py --inst MES --budget 38
#   --inst {MES|MNQ}  --budget <seconds>  --rows <jsonl>  --state <json>  --start/--end
# aggregate rows: load fut_rows.jsonl, group by (watcher,dir,conf), sum net, compute WR.
```

### Instrument facts (verified, CME)
MNQ $2/pt · MES $5/pt · NQ $20/pt · ES $50/pt · tick 0.25 · round-turn ≈ $1.24 micros / $4 minis ·
quarterly expiry 3rd Fri (H=Mar M=Jun U=Sep Z=Dec) · Globex Sun 5pm–Fri 4pm CT.

### Key sources
Databento GLBX.MDP3 (databento.com/datasets/GLBX.MDP3) · ib_async docs
(ib-api-reloaded.github.io/ib_async) · IB Gateway Docker (github.com/gnzsnz/ib-gateway-docker) ·
TradingView CME_MINI:MNQ1! · continuous-contract methodology (quantpedia.com).

---

## 8. GUARDRAILS — what NOT to do (inherited from `CLAUDE.md`)

- **Do NOT place live/real-money orders.** Paper only. Going live is J's explicit call (Rule 9, OP-21
  watch-first: 3+ live-confirmed wins + ratification). Even paper order placement should start WATCH-ONLY.
- **Do NOT treat curated v2b as live-ready.** It's in-sample. No live config until it clears OOS (Step 4).
- **Do NOT trade the raw spliced continuous series.** Roll-adjusted only.
- **Do NOT hardcode/commit the Databento or IBKR credentials.** Env vars / local config only.
- **Respect the FUSE + background-process + 45s constraints (§5)** — validate in `/tmp`, deliver via file tools.
- **No mid-session rule changes to the live options engine** — the futures work is a separate module and must
  not alter `automation/prompts/heartbeat*.md` or `automation/state/params*.json` for the options engine.

---

## 9. OPEN QUESTIONS FOR J (surface these early)
1. **MNQ vs MES priority** for going live first? (MNQ = the Reddit source's market + more volatile; MES = our tuning.)
2. **Account size / risk per trade** for sizing (`futures/risk.py` defaults to micros, 3 contracts).
3. **Prop firm or personal IBKR** as the eventual live venue? (Affects whether prop drawdown rules bind.)
4. **Overnight or flat-by-EOD?** Current sim is RTH intraday + EOD flat. Futures allow overnight holds.

---

**Bottom line for tonight:** the engine is built and a regime-gated config looks strong in-sample. The two
things that turn this from "promising backtest" into "real" are (1) **real MNQ data** (Databento key — Step 1)
and (2) **OOS validation** (Step 4). Do those first. If the edge holds out-of-sample on real Nasdaq bars,
wire IBKR paper (Step 6) and start cooking. If it doesn't, strip to what survives — likely ORB + a couple of
robust momentum slices — and cook that. Either way you have a working harness to iterate fast.
