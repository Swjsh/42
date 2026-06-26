"""alpaca_keys -- single source of truth for the live paper Alpaca creds.

Reads the GITIGNORED project-root `.mcp.json` (the same file Claude Code loads the
MCP servers from) and returns {"safe": (key, secret), "bold": (key, secret)} mapped
from the `alpaca` (Safe) and `alpaca_aggressive` (Bold) MCP server env blocks.

WHY THIS EXISTS (2026-06-21 readiness audit, finding C1/P0-1): the REST safety
helpers (atomic_bracket_guard.py, ghost_order_reconciler.py) used to HARD-CODE the
account keys. The Safe key drifted to the RETIRED Safe-1 key (PKGZIUWD...) while the
live account is Safe-2 (PK7WRO5T...), so every Safe guard run returned HTTP 401 and
the naked-order / ghost-order safety nets were silently DEAD on the Safe account
(the exact L47/L76 incident class they exist to catch). Hard-coding also committed a
LIVE paper secret into git-tracked source. Reading from the gitignored .mcp.json
fixes BOTH: the keys can never drift from what the engine actually trades with, and
no secret lives in committed source.

FAIL-LOUD: raises a clear error if .mcp.json is missing or an account block is
absent. Callers (the guards) catch it and report an error rather than silently
falling back to a stale key (which is what caused the original bug).
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MCP_JSON = PROJECT_ROOT / ".mcp.json"

# .mcp.json server name -> our account label
_SERVER_FOR_ACCOUNT = {
    "safe": "alpaca",
    "bold": "alpaca_aggressive",
}


def load_account_keys(mcp_json: Path | None = None) -> dict[str, tuple[str, str]]:
    """Return {"safe": (key, secret), "bold": (key, secret)} from .mcp.json.

    Raises FileNotFoundError if .mcp.json is missing, KeyError/ValueError if a
    required server env block or credential is absent. Never returns a stale key.
    """
    path = Path(mcp_json) if mcp_json is not None else MCP_JSON
    if not path.exists():
        raise FileNotFoundError(
            f"alpaca_keys: {path} not found -- cannot resolve live Alpaca creds. "
            "The REST guards refuse to run on a stale/guessed key."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    servers = cfg.get("mcpServers", {})
    out: dict[str, tuple[str, str]] = {}
    for account, server_name in _SERVER_FOR_ACCOUNT.items():
        env = (servers.get(server_name) or {}).get("env", {})
        key = env.get("ALPACA_API_KEY")
        secret = env.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise KeyError(
                f"alpaca_keys: server '{server_name}' (account '{account}') is "
                f"missing ALPACA_API_KEY/ALPACA_SECRET_KEY in {path}"
            )
        out[account] = (key, secret)
    return out


def keys_for(account: str, mcp_json: Path | None = None) -> tuple[str, str]:
    """Return (key, secret) for a single account ('safe' or 'bold')."""
    keys = load_account_keys(mcp_json)
    if account not in keys:
        raise KeyError(f"alpaca_keys: unknown account '{account}' (have {list(keys)})")
    return keys[account]


if __name__ == "__main__":
    # Diagnostic only -- prints account labels + a MASKED key, never the secret.
    for acct, (k, _s) in load_account_keys().items():
        print(f"{acct}: key={k[:6]}...{k[-4:]}  secret=<hidden>")
