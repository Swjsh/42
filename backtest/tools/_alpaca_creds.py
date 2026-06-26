"""Resolve Alpaca market-data credentials from a single, non-hardcoded source.

Security: NEVER hardcode the live key/secret in source. Credentials are sourced,
in priority order, from:

  1. Environment variables ALPACA_API_KEY / ALPACA_SECRET_KEY
     (also accepts the legacy ALPACA_API_SECRET name for the secret).
  2. The project-local `.mcp.json` at the repo root — the `alpaca` server's
     `env` block (the same working Safe-2 paper key the live MCP uses).

These tools only READ historical market data (v1beta1/options/bars, stocks/bars);
they never place orders. The paper key is sufficient for market-data auth.

Raises a clear, actionable error if no credentials can be resolved, so a routine
backfill run fails LOUD instead of silently 401-ing on a dead literal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NamedTuple

# repo root = backtest/ -> 42/  (this file lives in backtest/tools/)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MCP_JSON = _REPO_ROOT / ".mcp.json"


class AlpacaCreds(NamedTuple):
    key: str
    secret: str
    source: str  # "env" or ".mcp.json:<server>" — for diagnostics, never the value


def _from_env() -> AlpacaCreds | None:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if key and secret:
        return AlpacaCreds(key=key, secret=secret, source="env")
    return None


def _from_mcp_json(server: str = "alpaca") -> AlpacaCreds | None:
    if not _MCP_JSON.exists():
        return None
    try:
        cfg = json.loads(_MCP_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    env = (
        cfg.get("mcpServers", {})
        .get(server, {})
        .get("env", {})
    )
    key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY") or env.get("ALPACA_API_SECRET")
    if key and secret:
        return AlpacaCreds(key=key, secret=secret, source=f".mcp.json:{server}")
    return None


def resolve_alpaca_creds(server: str = "alpaca") -> AlpacaCreds:
    """Return (key, secret, source). Raises RuntimeError if none found.

    `server` selects which `.mcp.json` server's env block to read (default the
    Safe-2 `alpaca` server). Env vars always win over `.mcp.json`.
    """
    creds = _from_env() or _from_mcp_json(server)
    if creds is None:
        raise RuntimeError(
            "No Alpaca credentials found. Set ALPACA_API_KEY + ALPACA_SECRET_KEY "
            f"in the environment, or provide the `{server}` server's env block in "
            f"{_MCP_JSON}. (Do NOT hardcode keys in source.)"
        )
    return creds


def masked(value: str) -> str:
    """First 4 chars + length, for safe logging. Never prints the full secret."""
    if not value:
        return "<empty>"
    return f"{value[:4]}...(len={len(value)})"
