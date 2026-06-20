# Project Gamma — SPY Options Trading System

A disciplined, journaled, rules-based SPY options trading project.

## Quick start

1. Read `CLAUDE.md` first. It is the source of truth.
2. Install MCPs per `markdown/infra/mcp-install.md`.
3. Verify with `markdown/infra/verification.md`.
4. Read `markdown/0dte/risk-rules.md` until you've memorized the position sizing math.
5. The playbook (`markdown/0dte/playbook.md`) is empty until we journal the trades that worked. Fill it from real evidence, not theory.
6. Every trading day starts with a new file in `journal/YYYY-MM-DD.md`.

## Directory layout

```
.
├── CLAUDE.md                     # Soul file — read every session
├── README.md                     # This
├── setup/
│   ├── mcp-install.md            # Alpaca + TradingView MCP install steps
│   └── verification.md           # How to confirm MCPs are connected
├── strategy/
│   ├── playbook.md               # Named setups with entry/exit/stop rules
│   ├── risk-rules.md             # Position sizing, daily loss limit, PDT
│   └── checklists.md             # Pre-trade and post-trade checklists
├── journal/
│   ├── README.md                 # How to journal
│   ├── trades.csv                # Structured trade log
│   ├── mistakes.md               # Rule breaks (read every Monday)
│   └── YYYY-MM-DD.md             # Daily journals
└── analysis/
    ├── YYYY-Www.md               # Weekly reviews
    └── post-mortems/             # Deep dives on specific trades
```

## North star

> Discipline first. Edge second. Size last.

## Status

- [x] Project scaffolded
- [x] CLAUDE.md v1
- [x] Risk rules v1
- [ ] MCPs installed (Alpaca + TradingView)
- [ ] Recent winning trades captured
- [ ] Playbook v1 drafted from real trades
- [ ] 20 paper trades logged on v1 strategy
- [ ] Live trading thresholds met
