# Project Gamma — SPY Options Trading System

A disciplined, journaled, rules-based SPY options trading project.

## Quick start

1. Read `CLAUDE.md` first. It is the source of truth.
2. Install MCPs per [`markdown/infra/mcp-install.md`](markdown/infra/mcp-install.md).
3. Verify with [`markdown/infra/verification.md`](markdown/infra/verification.md).
4. Read [`markdown/0dte/risk-rules.md`](markdown/0dte/risk-rules.md) until you've memorized the position sizing math.
5. The playbook ([`markdown/0dte/playbook.md`](markdown/0dte/playbook.md)) is filled from real journaled evidence, not theory.
6. Every trading day starts with a new file in `journal/YYYY-MM-DD.md`.

## Directory layout

```
.
├── CLAUDE.md                     # Soul file — read every session
├── README.md                     # This
├── CHANGELOG.md                  # Append-only evolution log / audit trail
├── markdown/                     # All human-authored reference docs (see markdown/README.md)
│   ├── infra/
│   │   ├── mcp-install.md         # Alpaca + TradingView MCP install steps
│   │   └── verification.md        # How to confirm MCPs are connected
│   └── 0dte/
│       ├── playbook.md            # Named setups with entry/exit/stop rules
│       └── risk-rules.md          # Position sizing, daily loss limit, PDT
├── automation/
│   ├── state/params.json          # Canonical config — Gamma-Safe (source of truth)
│   ├── state/aggressive/params.json  # Canonical config — Gamma-Bold
│   └── overnight/STATUS.md        # Live operational status (what J wakes to)
├── journal/
│   ├── trades.csv                # Structured trade log
│   ├── mistakes.md               # Rule breaks (read every Monday)
│   └── YYYY-MM-DD.md             # Daily journals
└── analysis/
    └── YYYY-Www.md               # Weekly reviews
```

## North star

> Discipline first. Edge second. Size last.

## Status

Live status is not tracked here. For current state read [`CLAUDE.md`](CLAUDE.md) (rules, accounts, strategy version) and [`automation/overnight/STATUS.md`](automation/overnight/STATUS.md) (operational status — what J wakes to).
