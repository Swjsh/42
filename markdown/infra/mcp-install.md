# MCP Install — Alpaca + TradingView (Claude Code)

> How the trading rig is wired today. Verify with [`markdown/infra/verification.md`](verification.md) after any change.

**Host:** Claude Code (Cowork's connector registry doesn't carry Alpaca or TradingView MCPs).
**Config file:** repo-root **`.mcp.json`** (`C:\Users\jackw\Desktop\42\.mcp.json`) — project-scoped, picked up on Claude Code restart. The same server block is mirrored in `~/.claude.json` under this project's entry; keep the two in sync.

There are **three** MCP servers: `tradingview`, `alpaca` (Gamma-Safe-2), `alpaca_aggressive` (Gamma-Risky-2). Both Alpaca servers run the same binary under different keys.

---

## The pythonw hidden-window shim

Every server is launched through `setup\mcp\mcp_stdio_hidden.py` run by the **Store Python 3.13 `pythonw.exe`** (`...\Python\Python313\pythonw.exe`). The shim re-spawns the real command (`uvx ...` / `node ...`) with `CREATE_NO_WINDOW` so no black console flashes on Win11 (the window-leak fix). Do NOT invoke `uvx`/`node` directly in `.mcp.json` — always go through the shim.

---

## 1. Alpaca MCP (paper trading) — two accounts

Binary: `uvx alpaca-mcp-server` (uv fetches/pins it; no clone, no `pip install -e`). One server per account, distinguished only by the `env` keys.

### Get paper API keys

1. Sign in to alpaca.markets → toggle to **Paper Trading**.
2. Generate **API Key** + **Secret** for each paper account. Save to a password manager — never paste into chat.

### Server blocks (in repo-root `.mcp.json`)

```jsonc
{
  "mcpServers": {
    "alpaca": {                         // → Gamma-Safe-2  (PA3S2PYAS2WQ)
      "command": "C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe",
      "args": [
        "C:\\Users\\jackw\\Desktop\\42\\setup\\mcp\\mcp_stdio_hidden.py",
        "uvx", "alpaca-mcp-server"
      ],
      "env": {
        "ALPACA_API_KEY": "PK7WRO5T…",      // Safe-2 key
        "ALPACA_SECRET_KEY": "…",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"
      }
    },
    "alpaca_aggressive": {              // → Gamma-Risky-2 (PA33W2KUAT40)
      "command": "C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe",
      "args": [
        "C:\\Users\\jackw\\Desktop\\42\\setup\\mcp\\mcp_stdio_hidden.py",
        "uvx", "alpaca-mcp-server"
      ],
      "env": {
        "ALPACA_API_KEY": "PKQMQD2N…",      // Risky-2 key
        "ALPACA_SECRET_KEY": "…",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"
      }
    }
  }
}
```

Tools come through as `mcp__alpaca__*` (Safe) and `mcp__alpaca_aggressive__*` (Bold).

> **Important:** `.mcp.json` holds live secrets — it must stay out of git. If it ever lands somewhere version-controlled, swap secrets for env-var refs sourced from a `.gitignore`d `.env`.

---

## 2. TradingView MCP

Launched via the **SwjshAlgoKnife launcher** (`launcher.cjs`), also wrapped in the hidden-window shim:

```jsonc
{
  "mcpServers": {
    "tradingview": {
      "command": "C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe",
      "args": [
        "C:\\Users\\jackw\\Desktop\\42\\setup\\mcp\\mcp_stdio_hidden.py",
        "node",
        "C:\\Users\\jackw\\Desktop\\SwjshAlgoKnife\\mcp-servers\\tradingview-mcp\\launcher.cjs"
      ]
    }
  }
}
```

### Launch TradingView desktop with the debug port

TradingView on Windows installs as an MSIX package. The normal Windows launcher (`start`, `ShellExecute`, double-click) strips the `--remote-debugging-port` flag before it reaches the Electron binary. Use the project launch script instead — it bypasses the MSIX activator via direct `CreateProcess`:

```powershell
# From anywhere:
C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1

# If TradingView is already open without the debug port, kill and relaunch:
C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1 -Kill
```

Expected output: `CDP ready at http://localhost:9222`. In production this runs automatically (`Gamma_LaunchTV` 08:00 ET + `Gamma_TvWatchdog` keepalive). The TV MCP connects to the debug port at startup — if you open Claude Code before the port is up, restart Claude Code.

---

## 3. Restart Claude Code

After editing `.mcp.json`, fully restart Claude Code (and mirror the change into `~/.claude.json`). The MCP servers need a fresh process to load — a rotated key only takes effect on restart.

---

## 4. Verify

Proceed to [`markdown/infra/verification.md`](verification.md).

---

## Where to journal the install

Log doctrine/wiring changes in [CHANGELOG.md](../../CHANGELOG.md), not inline in CLAUDE.md.
