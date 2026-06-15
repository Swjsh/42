# MCP Install — Alpaca + TradingView (Claude Code)

> Run these steps once on the trading rig. Verify with `setup/verification.md` after.

**Host:** Claude Code (we picked this because Cowork's connector registry doesn't carry Alpaca or TradingView MCPs).
**Config file:** `~/.claude/.mcp.json` (Linux/macOS) or `%USERPROFILE%\.claude\.mcp.json` (Windows).

---

## 1. Alpaca MCP (paper trading API)

There are several community Alpaca MCP servers. The most actively maintained one as of project kickoff is the official Alpaca Markets reference (`alpacahq/alpaca-mcp-server`) — verify which one you want before installing. Below assumes the Python reference impl; adjust if you choose a different one.

### Get paper API keys

1. Sign in to alpaca.markets.
2. Toggle to **Paper Trading**.
3. Generate **API Key** and **Secret** for paper. Save to a password manager — never paste into chat or files.

### Install

```bash
# clone or pip install — pick the one that matches the package you chose
pip install alpaca-mcp-server
# or
git clone https://github.com/alpacahq/alpaca-mcp-server.git ~/code/alpaca-mcp
cd ~/code/alpaca-mcp && pip install -e .
```

### Add to `~/.claude/.mcp.json`

Open that file and add an entry under `mcpServers`:

```jsonc
{
  "mcpServers": {
    "alpaca": {
      "command": "python",
      "args": ["-m", "alpaca_mcp_server"],
      "env": {
        "ALPACA_API_KEY_ID": "<paste paper key>",
        "ALPACA_SECRET_KEY": "<paste paper secret>",
        "ALPACA_PAPER": "true",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"
      }
    }
  }
}
```

> **Important:** keep the file out of git. If `~/.claude/.mcp.json` lives anywhere version-controlled, swap secrets for env-var refs and source from a `.env` you `.gitignore`.

---

## 2. TradingView MCP

```bash
git clone https://github.com/tradesdontlie/tradingview-mcp.git ~/code/tradingview-mcp
cd ~/code/tradingview-mcp
npm install
npm run build   # if the repo has a build step — check its README
```

### Launch TradingView desktop with the debug port

TradingView on Windows installs as an MSIX package. The normal Windows launcher (`start`, `ShellExecute`, double-click) strips the `--remote-debugging-port` flag before it reaches the Electron binary. Use the project launch script instead — it bypasses the MSIX activator via direct `CreateProcess`:

```powershell
# From anywhere:
C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1

# If TradingView is already open without the debug port, kill and relaunch:
C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1 -Kill
```

Expected output: `CDP ready at http://localhost:9222`

> This must run **before** opening Claude Code. The TV MCP connects to the debug port at startup. If you open Claude Code first, restart it after running the script.

### Add to `~/.claude/.mcp.json`

```jsonc
{
  "mcpServers": {
    "alpaca": { "...": "..." },
    "tradingview": {
      "command": "node",
      "args": ["~/code/tradingview-mcp/dist/index.js"],
      "env": {
        "TV_DEBUG_PORT": "9222"
      }
    }
  }
}
```

(Replace path/entry-point with whatever the repo specifies.)

---

## 3. Restart Claude Code

After saving `.mcp.json`, fully restart Claude Code. The MCPs need a fresh process to load.

```bash
# kill any running Claude Code processes, then re-launch
claude  # or however you start it
```

---

## 4. Verify

Proceed to `setup/verification.md`.

---

## Where to journal the install

When done, log in `CLAUDE.md` update table:

| Date | Update | By |
|---|---|---|
| YYYY-MM-DD | MCPs installed: Alpaca paper (vX.Y), TradingView (commit `abc1234`). Both responding to health checks. | J |
