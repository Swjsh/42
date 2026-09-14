"""DASHBOARD-LOOPBACK-ONLY (GAMMA-STATION item 10; incident 2026-09-13 23:0x ET and again
2026-09-14 ~01:00 ET).

Twice in one night a SECOND :3000 listener appeared on `::` / `0.0.0.0` beside the loopback
one: a plain `next dev` / `next start` (a builder, or the Browser pane's launch.json entry)
binds every interface by default, and Windows lets a dual-stack `::` listener coexist with a
`127.0.0.1` one, so nothing failed loudly -- the dashboard was simply LAN-reachable until
someone noticed. J's standing directive: loopback only, everything security conscious.

Three things must all stay true:
  1. every scripted way to start the dashboard passes `-H 127.0.0.1` (package.json dev AND
     start; both launch.json entries the Browser pane can start),
  2. the 5-minute keepalive carries the rogue-listener guard (kill + log anything on :3000
     that is not 127.0.0.1 / ::1),
  3. the keepalive's own spawn line stays loopback.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _scripts() -> dict[str, str]:
    return json.loads((ROOT / "dashboard" / "package.json").read_text(encoding="utf-8"))["scripts"]


class TestEveryStartPathIsLoopback:
    def test_package_json_dev_and_start_bind_loopback(self):
        scripts = _scripts()
        for name in ("dev", "start"):
            assert "-H 127.0.0.1" in scripts[name], f"package.json '{name}' must bind 127.0.0.1: {scripts[name]!r}"

    def test_launch_json_next_dev_entries_bind_loopback(self):
        for rel in (".claude/launch.json", "dashboard/.claude/launch.json"):
            cfg = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            for c in cfg["configurations"]:
                args = c.get("runtimeArgs", [])
                if c.get("runtimeExecutable") == "npx" and args[:2] == ["next", "dev"]:
                    assert "127.0.0.1" in args, f"{rel} '{c['name']}' starts next dev on every interface: {args}"


class TestKeepaliveGuardsThePort:
    def test_keepalive_kills_non_loopback_listeners(self):
        src = (ROOT / "setup" / "scripts" / "run-dashboard-keepalive.ps1").read_text(encoding="utf-8")
        assert "NON-LOOPBACK-LISTENER GUARD" in src
        assert "$_.LocalAddress -ne '127.0.0.1'" in src
        assert "Stop-Process -Id $rg.OwningProcess" in src

    def test_keepalive_spawn_line_is_loopback(self):
        src = (ROOT / "setup" / "scripts" / "run-dashboard-keepalive.ps1").read_text(encoding="utf-8")
        assert 'start -p $port -H 127.0.0.1' in src
