# 42 Futures Edition — Plan, Architecture, and Stage-1 Results (2026-06-14)

> Spun up at J's direction: "an entire futures edition to the 42 project … same engine … won't do 0DTE …
> all the same strategies … test them all on futures." Built by Gamma (Opus orchestrator + Sonnet research
> subagents). This doc is the plan, the engine-reuse map, the decisions (researched, not guessed), the
> first results, and the roadmap. **Backtest research only — no live order placement.**

---

## TL;DR — the futures hypothesis holds

Rerunning **every existing watcher** over our 16-month data, graded with **futures point-P&L instead of
0DTE options P&L** (theta removed), on **MES** (Micro S&P, qty 3, net of commissions + 1-tick slippage):

| Result | 16-mo net | WR | per-trade |
|---|---:|---:|---:|
| **Curated v1** (ORB + TBR-long + Shotgun-long + Morning-rejection) | **+$4,716** | 47.3% | +$3.80 |
| **ORB alone** (the cleanest edge) | **+$755** | 68.8% | **+$23.58** |
| Shotgun-scalper LONG only | +$2,506 | 45.2% | +$2.89 |
| TBR-high-vol LONG only | +$1,403 | 47.3% | +$5.82 |
| Run-everything-blindly (all 11 watchers, both directions) | −$21,020 | — | −$5.69 |

**The edge that was marginal/regime-locked as 0DTE options (ORB) is solidly profitable as futures.**
Theta removal helped exactly where J predicted. But it is **not** a blanket win — see the honest caveats.

### Honest caveats (read before believing the number)
1. **MES proxy.** These bars are SPY×10 (S&P 500). MES is the true apples-to-apples port of our SPY-tuned
   engine. **MNQ (Nasdaq) — what the Reddit source traded — needs real Nasdaq bars** (Phase 1, Databento).
2. **Long bias is doing heavy lifting in a 2025-26 bull regime.** Every short side bled (shotgun-short
   −$7,508, tbr-short −$2,220). The long-only edge is **regime-dependent**: Q3-2025 (−$813) and Q1-2026
   (−$1,032) were negative. Needs the same VIX/regime gate the options engine uses. Not a free lunch.
3. **ERL→IRL loses on futures too** (−$4,367 both directions) — confirming the earlier finding that ERL→IRL
   is a *bad detector* (loose, R:R-mismatched), not a theta victim. Theta was never its problem.
4. **High-WR-but-negative trap**: LBFS (74% WR, −$2,268) and ERL→IRL (73% WR) win often but small and lose
   rarely but big — classic R:R mismatch the futures sim exposes cleanly. Fixable with tighter stops / R≥2.
5. Stage-1 fidelity: RTH-only, simplified bracket fills, 1-tick slippage, no overnight, no real fills.
   This is a **signal**, not a live-ready P&L.

Full per-strategy + direction split: `analysis/recommendations/futures-mes-stage1-results.json`;
raw signals: `analysis/recommendations/futures-mes-signals.jsonl`.

---

## Decisions (researched 2026-06-14, cited in chat)

| Question | Decision | Why |
|---|---|---|
| **Instruments** | MES + MNQ micros (start MES) | Micros = small-account friendly ($0.50/tick MNQ, $1.25 MES). MES = S&P = our SPY tuning; MNQ = Nasdaq = the source's market. |
| **Contract facts** | MNQ $2/pt, MES $5/pt, tick 0.25, quarterly roll (H/M/U/Z, 3rd Fri), Globex ~23h | CME specs verified. |
| **Backtest data** | **Databento GLBX.MDP3** ($125 free credits ≈ covers 2yr 1-min MNQ+MES for ~$2-5), `ohlcv-1m`, continuous `MNQ.c.0`/`MES.c.0` | Cheapest clean programmatic path. FirstRate = static backup. yfinance `=F` only 7d(1m)/60d(5m) — sanity only. |
| **Continuous contract** | Use a **roll-adjusted** series (back-adjusted/Panama for point strategies). NEVER trade raw spliced contracts | Splicing fabricates P&L on roll dates (the #1 futures-backtest footgun). |
| **Paper-trading venue** | **Interactive Brokers paper** (IB Gateway headless + `ib_async`) | Free, no GUI (Docker/Xvfb), native MNQ/MES brackets + fill callbacks. **Prop-firm APIs (TopstepX/ProjectX) rejected — they ban VPS/remote/unattended use.** Tradovate = paid fallback. |
| **Chart/levels (TradingView MCP)** | Reuse the same TV MCP with `CME_MINI:MNQ1!` / `CME_MINI:MES1!` | TV fully supports CME futures; reads just like SPY. 10-min delayed is fine for pattern/level reading. |
| **Risk layer** | Prop drawdown models encoded (Topstep EOD-fixed-floor, Apex intraday-trailing) | Futures analog of our kill-switch + sizing. |

---

## Architecture — what reuses the engine vs what's new

**Reused unchanged** (this is the whole point — "same engine"): every watcher in `backtest/lib/watchers`
(ORB, ERL→IRL, ribbon/level bearish-rejection, shotgun, TBR, LBFS, NLWB, double-bottom, H&S, RSI-div, …),
plus `filters.py`, `ribbon.py`, `levels.py`, `orchestrator.py` context-building. They operate on OHLCV bars
and are instrument-agnostic — they ran on MES bars with **zero modification**.

**New (`backtest/futures/`):**
- `instruments.py` — MNQ/MES/NQ/ES specs (point value, tick, SPY→index proxy factor, round-turn cost).
- `futures_sim.py` — point-P&L bracket simulator: `pnl = points × point_value × contracts − slippage − commissions`.
  Replaces the options pricing/Greeks/strike/theta layer entirely. Bracket doctrine mirrors `grade_observation`.
- `risk.py` — `PropAccount` (Topstep/Apex drawdown models) + `size_contracts()`.
- `data.py` — continuous-contract CSV loader (FirstRate/Databento), session tagging, yfinance sanity puller,
  Databento snippet. Normalizes to the engine bar schema so watchers run unchanged.
- `run_futures_backtest.py` — resumable, time-budgeted harness: runs `run_all_watchers` over the data and
  grades each signal with `futures_sim`. Streams to JSONL + checkpoints (built around the sandbox's
  no-background-process constraint).

**What drops out vs the options engine:** theta/decay, strike selection, OPRA real-fills, 0DTE/EOD-theta
flatten. **What changes:** P&L in points×$ not premium%; stops/targets in points/ticks; sizing by contracts +
prop drawdown; near-24h sessions (we trade RTH); roll/continuous-contract data layer.

---

## Roadmap (next, in priority order)

1. **Real data** — pull MNQ + MES 1-min from Databento ($125 free credits), build the back-adjusted
   continuous series, re-run the all-strategy backtest on **true MNQ (Nasdaq)** and MES. (MNQ is the open
   question the proxy can't answer.)
2. **Curate + regime-gate** — promote ORB + long-side momentum (TBR-long, shotgun-long) into a `futures
   params` set; add the VIX/regime gate (the long edge is bull-regime-dependent — Q3-25/Q1-26 were negative).
3. **Fix or drop the R:R-mismatched setups** — ERL→IRL and LBFS win often but lose big; tighten stops / target
   R≥2, or drop. ERL→IRL loses on futures too, so it's exit-design, not instrument.
4. **TradingView MCP futures** — point the chart reader at `CME_MINI:MNQ1!`/`MES1!` for live levels.
5. **IBKR paper wiring** — IB Gateway (Docker, headless) + `ib_async`; bracket orders on MNQ/MES, fill
   callbacks; a futures heartbeat mirroring the options one. **Watch-only → paper only after backtest gates pass.**
6. **Validation rigor** — OOS walk-forward, per-regime stratification, concentration checks (same disclosure
   stack as the options engine). No live money until it clears.

---

## Iteration 1 — "change it up" (2026-06-14): direction + regime + confidence gating

Mined all 3,695 signals for the profitable sub-slices, then re-tested. Encoded in
`backtest/futures/strategy_config.py` (`CURATED_V2B_RULES` + `should_take(watcher, dir, conf, vix)`).

| Version | what changed | 16-mo net (MES, qty 3) | WR | $/trade | quarters + |
|---|---|---:|---:|---:|---:|
| Curated v1 | long-bias momentum + ORB + morning-rejection | +$4,716 | 47.3% | +$3.80 | 4/6 |
| **Curated v2b** | + drop short momentum, + **VIX≥16 gate**, + ERL→IRL only short/high/VIX16–22 | **+$14,243** | 54.5% | **+$16.50** | **6/6** |

The three highest-value changes (non-overlapping ≈ +$16k swing vs run-all): (1) **drop all
shotgun-scalper SHORTs** (+$7.5k recovered), (2) **restrict ERL→IRL to short/high/VIX-16–22 only**
(+$6.7k — every other ERL→IRL slice loses), (3) **VIX≥16 open gate on momentum longs** (+$2k —
the same signals are noise in calm markets). Per-quarter v2b is positive in all 6 quarters.

**Honest caveat (important):** v2b is **in-sample slice selection** — picking the slices that won on
the same data will always look good. The VIX≥16 regime gate is mechanistically sound (momentum needs
volatility to follow through), but the specific per-slice VIX cutoffs risk overfit. **Next: OOS
walk-forward + per-regime stratification before any trust** — same gate the options engine requires.

## TradingView MCP capability — built (`backtest/futures/tradingview.py`)

The futures engine has **everything the SPY engine has** on the chart side: it reuses the identical
`mcp__tradingview__*` toolset (`data_get_ohlcv`, `data_get_study_values` for the ribbon, HTF timeframe
switch, `capture_screenshot`, Pine `pine_*` tools, J-drawn-line capture via `ui_evaluate`). The ONLY
change is the symbol: `chart_set_symbol("CME_MINI:MNQ1!")` (or `MES1!`) in place of `"BATS:SPY"`. The R1
closed-bar fix (count=3, drop in-progress [-1] bar) and the `TVC:VIX` refresh carry over verbatim.
`chart_config()` + `CHART_READER_RECIPE` document the exact per-tick call sequence for the futures heartbeat.

## Guardrails
Backtest research only. No live/paper order placement wired. Live futures execution (IBKR paper) is a future,
J-gated step — same discipline as the options engine (OP-21 watch-first, Rule 9). Curated v2b is a
ratification CANDIDATE pending OOS validation, not a live config.
