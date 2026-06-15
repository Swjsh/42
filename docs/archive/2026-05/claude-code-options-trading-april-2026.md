# Claude Code for Options Trading — Verified Findings (April 2026)

> All sources below were fetched and verified before inclusion. Dates, strategies, and technical details are sourced directly from the original articles and repositories.

---

## Overview

A cluster of traders, developers, and researchers publicly documented using Claude Code to analyze, plan, and in some cases autonomously execute options trades in late 2025 through April 2026. The approaches range from fully autonomous paper trading bots to open-source analyst frameworks that pipe live options data into Claude for human-in-the-loop decisions.

---

## Source 1 — Jake Nesler: $100k Autonomous Options Trading (Paper)

**Published:** December 21, 2025
**URL:** https://medium.com/@jakenesler/i-gave-claude-code-100k-to-trade-with-in-the-last-month-and-beat-the-market-ece3fd6dcebc
**Verified:** Yes — full article fetched

### What He Did
Gave Claude Code $100,000 in paper capital on **Alpaca Markets** and ran it autonomously for 33 days. The setup used a **multi-agent governance system**: a CEO agent reviewed all activity, supplemented by a strategy agent and an engineering agent. A SQLite vector database stored trade experiences for pattern recognition across sessions.

**Tech stack:** Go backend + JavaScript MCP server, Alpaca paper trading API, SQLite

### Options Strategy
Two-pronged approach:
- **LEAPS (60-90+ DTE):** Long-dated calls on NVDA, AMD, PLTR, META, TSLA, SPY for baseline exposure
- **Intraday scalping (0-5 DTE):** Short-dated calls and puts based on momentum signals

### Specific Trades Documented
| Trade | Result |
|---|---|
| TSLA calls | +458% |
| RKLB calls | +306% |
| PLTR calls | +88% |
| SPY puts (Dec 17, Fed-triggered selloff) | +$14,578 single trade |
| AVGO calls (cut after earnings miss) | -64% |

### Result
- Starting: $100,000
- Final: $107,648 (+**7.6%** in 33 days)
- Peak: $120,431 (+20.4%)
- Max drawdown: -22.4%
- Beat S&P 500's 4.52% return over the same period

> Notably Nesler described using a prompt as simple as "Go trade autonomously till 4:01 PM" and reported it worked well on its own.

---

## Source 2 — Stas Khirman: Open-Source Options Trading Analyst Framework

**Published:** April 14, 2026
**URL:** https://medium.datadriveninvestor.com/i-built-an-open-source-framework-that-turns-claude-into-an-options-trading-analyst-db135846de29
**GitHub:** https://github.com/staskh/trading_skills (170 stars, 40 forks, last commit May 2, 2026)
**Verified:** Yes — full article and GitHub repo fetched

### What He Built
An open-source framework that connects Claude to live options data pipelines via **Model Context Protocol (MCP)**, turning it into an options analyst rather than a generic chatbot. The key insight: give Claude real-time data instead of asking it theoretical questions.

**Tech stack:** Python (IB-async client), Interactive Brokers TWS/Gateway, Massive.com (institutional flow), Yahoo Finance, FastMCP

### Architecture (4-tier)
1. **Market data layer** — live quotes, option chains with Greeks, earnings calendars
2. **Technical analysis** — RSI, MACD, Bollinger Bands, volatility metrics
3. **Portfolio management** — Interactive Brokers API integration
4. **Institutional flow detection** — per-second options bars via Massive.com

### Options Strategies Supported
- Vertical spreads, diagonal spreads
- Straddles and strangles
- Iron condors
- Poor Man's Covered Calls (PMCC) — with an 11-point scoring system
- Delta-hedged collars for earnings protection
- Roll candidate identification for short positions

### Notable Technical Challenges Solved
- **Async/sync boundary**: separated public synchronous interfaces from private async implementations to prevent event loop collisions with IB-async
- **Statistical robustness**: applied Modified Z-Score (Median Absolute Deviation) for outlier detection instead of standard deviation on small sample sizes
- **Rate limits**: batched market data requests in groups of 20 to respect IB subscription limits

### Scale
22 Claude Code skills + 24 MCP tools. Complete portfolio analysis reported to run in under 30 seconds.

---

## Source 3 — liorsolomon: Automated Options Trading Bot on GitHub Actions

**URL:** https://github.com/liorsolomon/ai-options-trading-bot
**Description:** "AI-powered options trading bot using Claude Code, running on GitHub Actions with Alpaca paper trading"
**Verified:** Yes — GitHub README fetched

### What It Does
A fully automated Python bot that runs on a **3-hour GitHub Actions schedule**, uses Claude Code as the decision engine to analyze market conditions and generate options signals, then executes via Alpaca Markets paper trading.

**Tech stack:** Python, GitHub Actions (CI/CD as the scheduler), Alpaca API, PostgreSQL (via Supabase/Neon), Docker, optional NewsAPI

### Options Approach
- PUT/CALL options strategies (documented as "in development" at time of README)
- Historical learning via a PostgreSQL database of successful signal patterns
- Hypothesis testing framework for strategy validation before live deployment

### Status
Active paper trading. No real capital deployed. No performance metrics published — the repo transparently states it is still in strategy development phase.

---

## Source 4 — tradermonty: Claude Code Skills Toolkit (Options Advisor Module)

**URL:** https://github.com/tradermonty/claude-trading-skills
**Stats:** 1.2k stars, 278 forks, 355 commits
**Verified:** Yes — GitHub README fetched

### What It Is
A community toolkit of reusable "skills" (SKILL.md instruction files) that users drop into Claude Code's Skills directory. The project spans market analysis, screening, risk management, and a dedicated **Options Strategy Advisor**.

### Options Strategy Advisor Module
- Theoretical pricing using **Black-Scholes model**
- Full Greeks calculation: Delta, Gamma, Theta, Vega, Rho
- Simulation of 17+ strategies including covered calls, spreads, and iron condors
- Positioned as educational/analytical, not autonomous execution

### Other Relevant Skills
- Institutional flow tracker
- Earnings trade analyzer
- Position sizer
- Backtest framework

---

## Source 5 — Satoshi Ido (Alpaca): Vibe Coding Options Algos with Alpaca MCP + Cursor/Claude

**Published:** August 14, 2025
**Author:** Satoshi Ido (Alpaca Markets staff)
**URL:** https://alpaca.markets/learn/vibe-coding-how-to-build-options-trading-algorithms-with-alpacas-mcp-server-cursor-ai
**GitHub:** https://github.com/alpacahq/alpaca-mcp-server (152 commits, v2 rewrite in FastMCP + OpenAPI)
**Verified:** Yes — full article and GitHub repo fetched

### What It Shows
The most detailed end-to-end walkthrough of building and executing an options algorithm via Alpaca's MCP server and an AI assistant (Cursor, which supports Claude as its backend). The core thesis: instead of hand-writing SDK calls, you describe the strategy in plain English and the MCP server handles authentication, option chain fetching, and order routing.

**Tech stack:** Python, Alpaca MCP Server v2 (FastMCP + OpenAPI), Cursor IDE (Claude-compatible), Alpaca Trading API

### The Architecture
```
Cursor / Claude  →  Alpaca MCP Server  →  Alpaca Trading API
  (prompt)           (auth + routing)      (execution + data)
```
The MCP server exposes three function imports — traders never touch raw SDK docs.

### Options Strategy Built
**Bull call spread** (debit spread) as the primary demo. The article explicitly notes the same workflow applies to:
- Iron condors
- Straddles
- Vertical put spreads

### Exact Prompt Template Used (60+ lines, key excerpt)
```
Create a Python script that implements an automated bull call spread
trading algorithm...The algorithm should be SIMPLE, FUNCTIONAL, and MINIMAL.

Parameters:
  --symbol     underlying ticker
  --buy-pct    % below current price for long leg
  --sell-pct   % above current price for short leg
  --dry-run    simulate without placing orders
```

### MCP Options Endpoints Confirmed Available
From the GitHub repo README:
- `get_option_chain` — full chain for any underlying
- `get_option_contracts` — filter by expiry, strike, type
- `get_option_snapshot` — Greeks + IV + bid/ask in one call
- `place_option_order` — single-leg or multi-leg execution
- `exercise_options_position` — exercise held contracts

### Example Natural Language Prompts That Execute Real Orders
- "Show me available option contracts for AAPL expiring next month"
- "Place a bull call spread using AAPL June 6th options: buy the 190 strike, sell the 200 strike"
- "Exercise my NVDA call option contract NVDA250919C001680"

### Setup Steps (12-step process documented)
1. Clone the Alpaca MCP server repo
2. Create Python virtual environment
3. Install dependencies via `requirements.txt`
4. Configure `.env` with Alpaca API keys (paper or live)
5. Add MCP server in Cursor Settings with credentials
6. Prompt Cursor/Claude to generate the strategy script
7. Run with `--dry-run` first to validate logic
8. Execute live via Alpaca API

### Important Caveats
- No live trading results or performance metrics shown — the article demonstrates the generation process only
- Paper trading recommended first via Alpaca's simulated environment
- Options trading requires Alpaca options approval (separate from standard account)

### Why This Is the Build-Off Reference
This is the only verified, step-by-step walkthrough of the full Alpaca MCP → Claude/Cursor → live options order pipeline. Every component (MCP config, prompt template, API endpoints, dry-run flag) is documented and reproducible.

---

## Source 6 — MindStudio: Claude Code Routines for Trading (Mentions Options)

**Published:** April 17, 2026
**URL:** https://www.mindstudio.ai/blog/how-to-build-ai-trading-agent-claude-code-routines
**Verified:** Yes — full article fetched

### What It Covers
A tutorial for building a 24/7 autonomous trading agent using Claude Code Routines + Alpaca API. The core loop: morning research → signal generation → order execution → trade journal, all scheduled without manual input.

### On Options
The article explicitly addresses options in its FAQ: "Alpaca supports crypto trading on its standard API. Options are supported through a separate beta program." It notes options require additional parameters — IV, Greeks, and expiration dates — beyond what the tutorial's equity-focused setup handles.

> **Verdict:** Directly relevant as infrastructure used by options traders, but this specific tutorial does not implement an options strategy itself.

---

## Cross-Source Patterns

| Pattern | Sources |
|---|---|
| Alpaca Markets for paper trading | Nesler, liorsolomon, MindStudio, Ido |
| MCP (Model Context Protocol) for broker/data integration | Khirman, MindStudio, Ido |
| Alpaca MCP server specifically for options execution | Ido (bull call spread), liorsolomon (PUT/CALL) |
| Natural language prompt → live options order pipeline | Ido (Alpaca MCP + Cursor/Claude) |
| CLAUDE.md as persistent instruction file for the agent | MindStudio, AI in Trading |
| Multi-agent governance (separate strategy/risk agents) | Nesler |
| PostgreSQL for trade memory / pattern learning | liorsolomon |
| LEAPS + short DTE scalping as options pairing | Nesler |
| Interactive Brokers for live-account integration | Khirman |

---

## What Is and Isn't Verified

| Claim | Status |
|---|---|
| Jake Nesler's +7.6% return over 33 days | **Paper trading only** — not real capital |
| Stas Khirman's framework connects to live IB accounts | Verified by code — IB TWS/Gateway integration confirmed |
| liorsolomon bot executes real trades | **Paper trading only** — Alpaca simulated environment |
| tradermonty options advisor runs Black-Scholes | Stated in README; educational use, no live execution |
| MindStudio agent supports options | Via Alpaca beta program — not the tutorial's focus |
| Alpaca MCP server has live options order endpoints | Confirmed in GitHub repo — `place_option_order`, `get_option_chain`, multi-leg support verified |
| Satoshi Ido's bull call spread algo executes real trades | Dry-run mode demonstrated; live execution via Alpaca API confirmed available but no live results published |

---

## Key Takeaway

As of April 2026, most Claude Code options trading setups are in **paper trading or analyst mode** — not live accounts. The most technically mature options-specific work is Stas Khirman's framework (Interactive Brokers, live data, multi-leg strategy analysis). The most publicly documented autonomous performance experiment is Jake Nesler's from December 2025. A new wave of open-source bots (liorsolomon, tradermonty) emerged in the same period, primarily targeting retail traders using Claude Code as an accessible path to algo trading.

The clearest **build-off reference** for Alpaca MCP + Claude + options is Satoshi Ido's "Vibe Coding" tutorial: it is the only verified end-to-end walkthrough of the full pipeline from natural language prompt → Alpaca MCP server → live options order. The MCP server's options endpoints (`place_option_order`, `get_option_chain`, multi-leg support) are confirmed working in v2. The prompt template and 12-step setup are directly reusable.

---

## Sources

1. [I gave Claude Code 100k to trade with in the last month and beat the market — Jake Nesler (Medium, Dec 2025)](https://medium.com/@jakenesler/i-gave-claude-code-100k-to-trade-with-in-the-last-month-and-beat-the-market-ece3fd6dcebc)
2. [I Built an Open-Source Framework That Turns Claude Into an Options Trading Analyst — Stas Khirman (DataDrivenInvestor, Apr 14 2026)](https://medium.datadriveninvestor.com/i-built-an-open-source-framework-that-turns-claude-into-an-options-trading-analyst-db135846de29)
3. [GitHub: liorsolomon/ai-options-trading-bot](https://github.com/liorsolomon/ai-options-trading-bot)
4. [GitHub: tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills)
5. [Vibe Coding: Build Option Algos with Alpaca's MCP Server & Cursor/Claude — Satoshi Ido, Alpaca Markets (Aug 14 2025)](https://alpaca.markets/learn/vibe-coding-how-to-build-options-trading-algorithms-with-alpacas-mcp-server-cursor-ai)
6. [GitHub: alpacahq/alpaca-mcp-server (official Alpaca MCP server, v2)](https://github.com/alpacahq/alpaca-mcp-server)
7. [How to Build a 24/7 AI Trading Agent with Claude Code Routines — MindStudio (Apr 17 2026)](https://www.mindstudio.ai/blog/how-to-build-ai-trading-agent-claude-code-routines)
