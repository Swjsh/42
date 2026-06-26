# LIVE TRADING PLAN — what we trade & how (as of 2026-06-20)

> The engine's live book. SPY 0DTE options, paper, both accounts. Every setup below is wired LIVE in `automation/prompts/heartbeat.md` + gated by `automation/state/params.json`. Read order: setup → trigger → entry → stop → exit → sizing.

## THE BOOK — 3 live setups

### 1. Gap-and-go (PUT side) — `gap_and_go_enabled=true, side=put`
- **What:** opening-gap continuation. Your momentum-breakout archetype (from your Webull winners).
- **Trigger:** the 09:30 RTH bar gaps **down ≥0.25%** vs prior close AND closes **red** (confirms the gap direction). Skip if |gap|>1.5% (runaway) or the bar doesn't confirm.
- **Entry:** next bar open (~09:35), **puts**. Once per day.
- **Stop:** CHART-STOP = the first RTH bar's HIGH (structurally tight — this is why it works).
- **Exit:** TP1 chart-level OR +50%, 2/3 off; runner 2.5× with breakeven + chandelier-15% trail; 15:40 hard time-stop.
- **Edge:** +$41/t, 73% WR, WF +1.87, real-fills validated. ~5 gap-down days/mo.

### 2. VWAP-continuation (BOTH sides) — `j_vwap_cont_enabled=true, side=both`
- **What:** your near-daily winning pattern — trade the side price is already on vs session VWAP. Mined from your 313 Webull winners.
- **Trigger:** first 3 RTH closes all one side of session VWAP → that's the trend side. Then the **first morning bar (≤10:30 ET)** that continues in-trend (breakout = fresh in-trend extreme, OR pullback = shallow VWAP-ward dip then a with-trend close).
- **Entry:** next bar open. Above VWAP → **calls**; below → **puts**.
- **Stop:** CHART-STOP = session extreme against the trade.
- **Exit:** standard v15 stack (TP1 0.667 / runner 2.5× / chandelier-15% / 15:40).
- **Edge:** +$38/t, 76.5% WR, OOS +$24 sign-stable, DSR pass, both dirs +. **Fires ~56% of days (~2-3/wk = near-daily).**

### 3. Everyday book — BEARISH_REJECTION (v15.3, the ratified engine)
- **What:** bearish rejection at a named level + ribbon conviction (the 10-filter rubric).
- **Trigger:** rejection at resistance/level, ribbon spreading ≥5c/3bars + fresh ≤15 bars + no midday single-trendline.
- **Entry:** [09:35, 15:00) ET continuous, puts. Skip 11:30-12:00.
- **Stop:** CHART-STOP primary; −50% premium catastrophe cap only.
- **Exit:** TP1 0.667 / runner 2.5× / chandelier-15% / 15:40.
- **Edge:** the P&L engine ($152/wk in the leaderboard) — rare (~1.5/mo) but sharp.

## SIZING (all setups) — risk_gate enforces
- **Min 3 contracts** (2 TP + 1 runner). No adding, no revenge, no sizing-up after a loss (the L168 killer).
- Per-tier strike (Safe $2K → OTM-2) + premium ceiling: `v15_max_premium_pct_of_account` = **40% at $2K** ($800/trade max). Min-3 ATM fits ~96% of days.
- Kill-switch: −30% of start-of-day equity (Safe −$600/day).

## HOW WE READ IT — TradingView MCP (the eyes)
Per tick (every 3 min, 09:30-15:55 ET): SPY 5m chart on BATS:SPY.
- `data_get_ohlcv` — the bars (closed-bar only, discard the in-progress [-1]).
- `data_get_study_values` — Saty Pivot Ribbon (fast/pivot/slow EMA) + VWAP + 50-EMA.
- `data_get_pine_lines/labels` — key levels (PDH/PDL/PMH/PML/round/overnight) from the levels indicator.
- `quote_get` on TVC:VIX — VIX level + character.
- Then score the 3 setups → if a trigger fires + connectivity is GREEN + flat-verified → bracket order via Alpaca MCP.

## DAILY FLOW (autonomous)
`08:30 premarket` (levels/bias/news) → `09:30-15:55 heartbeat` (read → score → trade → manage) → `15:55 EOD flatten`. Both accounts. Self-healing state.

## THE GUARANTEES (head-to-toe)
- **Connectivity-gated:** no tick acts unless TV MCP can read live SPY data AND Alpaca can read the account AND the position is flat-verified AND market is open (see the `connectivity-gate` skill).
- **Chart-stop primary:** premium stops are a wide catastrophe cap only (your shake-out lesson, proven on your losers).
- **The hold is mechanical:** TP1/runner/chandelier/time-stop are computed, not negotiated — the engine holds the rules you couldn't.
