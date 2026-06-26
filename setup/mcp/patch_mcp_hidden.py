"""Point every stdio MCP server at the windowless pythonw shim (mcp_stdio_hidden.py).

Rewrites each server's launch from a bare console launcher (uvx/node/...) to:
    command = <pythonw.exe>
    args    = [<shim.py>, <original command>, *<original args>]
    env     = <unchanged>

Idempotent: a server already wrapped is left untouched. Patches BOTH config sources
(checked-in .mcp.json + the live ~/.claude.json project entry) so the fix applies to the
interactive session AND every `claude --print` scheduled tick. Backs up each file first.

Run:  python setup/mcp/patch_mcp_hidden.py
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHONW = r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
SHIM = str(REPO / "setup" / "mcp" / "mcp_stdio_hidden.py")
SHIM_BASENAME = "mcp_stdio_hidden.py"
HOME_CFG = Path.home() / ".claude.json"
STAMP = dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def is_wrapped(cfg: dict) -> bool:
    args = cfg.get("args") or []
    return (
        str(cfg.get("command", "")).lower().endswith("pythonw.exe")
        and len(args) >= 1
        and SHIM_BASENAME in str(args[0])
    )


def wrap(cfg: dict) -> tuple[dict, bool]:
    """Return (new_cfg, changed)."""
    if is_wrapped(cfg):
        return cfg, False
    orig_cmd = cfg.get("command")
    if not orig_cmd:
        return cfg, False
    orig_args = cfg.get("args") or []
    new = dict(cfg)
    new["command"] = PYTHONW
    new["args"] = [SHIM, orig_cmd, *orig_args]
    return new, True


def patch_servers(servers: dict) -> list[str]:
    changed = []
    for name, cfg in list(servers.items()):
        if not isinstance(cfg, dict):
            continue
        new, did = wrap(cfg)
        if did:
            servers[name] = new
            changed.append(name)
    return changed


def patch_file_mcp_json(path: Path) -> None:
    if not path.exists():
        print(f"  (skip) {path} does not exist")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    if not servers:
        print(f"  (skip) {path} has no mcpServers")
        return
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-winfix-{STAMP}"))
    changed = patch_servers(servers)
    data["mcpServers"] = servers
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  {path}: wrapped {changed or '(none, already wrapped)'}")


def patch_home_claude_json() -> None:
    if not HOME_CFG.exists():
        print(f"  (skip) {HOME_CFG} does not exist")
        return
    data = json.loads(HOME_CFG.read_text(encoding="utf-8"))
    projects = data.get("projects") or {}
    target_keys = [
        k for k, v in projects.items()
        if k.replace("/", "\\").rstrip("\\").endswith("Desktop\\42")
        and isinstance(v, dict) and v.get("mcpServers")
    ]
    if not target_keys:
        print(f"  (skip) {HOME_CFG}: no project entry with mcpServers for Desktop\\42")
        return
    shutil.copy2(HOME_CFG, HOME_CFG.with_name(HOME_CFG.name + f".bak-winfix-{STAMP}"))
    total = []
    for k in target_keys:
        changed = patch_servers(projects[k]["mcpServers"])
        total += [f"{k} -> {c}" for c in changed]
    HOME_CFG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  {HOME_CFG}: wrapped {total or '(none, already wrapped)'}")


def main() -> int:
    print(f"pythonw: {PYTHONW}")
    print(f"shim:    {SHIM}")
    print("Patching configs:")
    patch_file_mcp_json(REPO / ".mcp.json")
    patch_home_claude_json()
    patch_file_mcp_json(Path.home() / ".claude" / "settings.json")
    print("Done. New `claude` processes (heartbeat ticks, EOD, interactive restarts) "
          "will spawn MCP servers windowless.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
