"""Keepalive for the claude-code-router (CCR) gateway, in Python.

WHY THIS EXISTS: since 2026-07-08 every `claude` CLI session routes through this
local gateway (~/.claude/settings.json ANTHROPIC_BASE_URL -> 127.0.0.1:3456). It
died overnight 07-08->07-09 with no auto-restart and every LLM scheduled fire
failed with ConnectionRefused until a manual restart the next day. This gives it
the same treatment as the Discord bridge (`Gamma_DiscordBridge` / OP-27): a 5-min
TCP-probe + auto-restart + episode-deduped Discord ping if restart can't recover it.

INTERACTIVE-PATH GUARD (added 2026-07-14, J's #1 directive that morning): the
07-08 wiring made CCR the DEFAULT for every claude fire globally via
~/.claude/settings.json's `env`/`apiKeyHelper` keys -- which ALSO silently
captured J's Desktop app and bare terminal `claude` CLI, not just automation.
Root cause of the 2026-07-14 lockout: `~/.claude-code-router/config.json`'s
`Router.default` is hardcoded `"ollama,qwen3.6:35b"` with ZERO Anthropic provider
entry, so any cold boot where CCR's fuller gateway/profile stack isn't yet live
still leaves port 3456 LISTENING (this keepalive's TCP probe sees "up") while
every default-routed request -- including J's interactive session -- silently
gets served local Ollama with no error. J lost a full workday because "port up"
!= "serving real Claude". Fix: J's interactive surfaces now hit Anthropic
DIRECTLY (settings.json's router override removed); CCR stays available only for
automation lanes that opt in per-fire in their OWN launch chain (doctrine:
markdown/planning/BRAIN-SOVEREIGNTY.md sec 4, pattern: launch_claude_local.ps1).
This script now ALSO asserts every fire that settings.json stays clean of the
router override -- if anything (a CCR reinstall/update, `ccr code` re-sync, a
future session) re-writes the hijack back in, this self-heals within 5 min and
pings J. See `_check_and_fix_interactive_settings`.

Task action (flash-free, matches window_leak_detector_keepalive.py /
crypto_grinder_keepalive.py / preopen_readiness.py):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> this file
No PowerShell anywhere in the fire chain (OP-27 L41 window-leak discipline).

RESTART INVOCATION -- direct node.exe call on the bundled CCR CLI, NOT
`powershell.exe -File ccr.ps1`:
  `ccr.ps1` (C:\\Users\\jackw\\AppData\\Roaming\\npm\\ccr.ps1) is a thin shim -- it
  Test-Path's a `node.exe` sitting NEXT TO ITSELF (absent on this box; node lives at
  `C:\\Program Files\\nodejs\\node.exe` instead) and falls through to its `else` branch:
  `& "node.exe" "$basedir\\node_modules\\@musistudio\\claude-code-router\\dist\\main\\cli.js" $args`.
  Going through the .ps1 buys nothing but an extra powershell.exe hop (execution-policy
  + profile-load risk in a non-interactive scheduled-task context) on top of that SAME
  underlying node call. We reproduce the fallback branch directly:
      node.exe <cli.js> start
  Confirmed via cli.js source (grepped 2026-07-09): the gateway child is spawned with
  `detached: process.platform !== "win32"` and always `.unref()`'d, so on Windows the
  CLI's `start` command launches the actual gateway as an independent background
  process and the `start` invocation itself returns almost immediately -- it does not
  block in the foreground, which is exactly what a scheduled-task action needs (we
  never call .wait()/.communicate() on it here either way, so this is fail-safe even
  if that assumption is ever wrong). If node.exe or the bundled cli.js ever move (a
  reinstall), `_restart_ccr` falls back to `powershell.exe -NoProfile -File ccr.ps1
  start` so a path drift degrades gracefully instead of going silent.

STATE: automation/state/ccr-keepalive.json -- {ts_et, port_up, consecutive_failures,
last_restart_et, ping_sent_this_episode}. `ping_sent_this_episode` is the de-dupe: one
ping per continuous down-episode (>=3 consecutive failed-restart cycles), reset the
moment a probe finds CCR up again. Fail-open throughout: any unexpected exception is
logged and this still exits 0 (OP-33e) -- it must never be the thing that breaks a
scheduled fire.
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════════════
# ⛔ TOMBSTONE 2026-08-23 -- THIS KEEPALIVE IS RETIRED. DO NOT RE-ENABLE.
#
# Second occurrence of the interactive-surface lockout scar (first: 2026-07-14, cost J a
# full workday). On 2026-07-14 CCR was audited to have ZERO production benefit (nothing
# routes through port 3456 -- kitchen/swarm/veto reach ollama and OpenRouter on their own
# ports) and Gamma_CcrKeepalive was DISABLED. The task was later re-enabled and had been
# resurrecting the gateway every 10 min ever since, leaving 3456 LISTENING with an
# ollama-only Router.default.
#
# What changed since July: Claude Desktop now has its OWN third-party-inference setting
# ("Connection: Gateway" + gateway base URL). That app-side config is invisible to this
# script's _check_and_fix_interactive_settings() guard -- which only watches
# ~/.claude/settings.json -- so keeping the gateway ALIVE is what let J's desktop app sit
# broken across every restart ("Your gateway couldn't serve claude-sonnet-4-5").
#
# The doctrine (memory: interactive-surfaces-never-gatewayed) is that J's interactive
# surfaces must not have our components as dependencies AT ALL. A dead port fails loudly
# and is fixed in one click; a live port serving the wrong models fails silently.
#
# Exits 0 immediately so any stale re-registration of Gamma_CcrKeepalive is inert rather
# than a broken fire. If a future automation lane genuinely needs routed models, it opts
# in PER-FIRE in its own launch chain -- it does not resurrect a machine-wide gateway.
# ══════════════════════════════════════════════════════════════════════════════════════
import sys as _tombstone_sys
print("ccr_keepalive: RETIRED 2026-08-23 (interactive-surface lockout scar #2) -- no-op.")
_tombstone_sys.exit(0)

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "ccr-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "ccr-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402

# CREATE_NO_WINDOW -- every subprocess spawn from this script must carry it (OP-27 L41;
# this repo REDs on bare-console spawns -- audit_window_leak_compliance.py).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DETACHED_PROCESS = 0x00000008 if sys.platform == "win32" else 0

STATE_DIR = REPO / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = STATE_DIR / "ccr-keepalive.json"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
DISCORD_CFG = STATE_DIR / ".discord-config.json"

CCR_HOST = "127.0.0.1"
CCR_PORT = 3456
PROBE_TIMEOUT_SEC = 3.0
RESTART_WAIT_SEC = 8.0
PING_THRESHOLD = 3  # consecutive failed-restart cycles (~15 min at the 5-min cadence)

# --- interactive-path guard (2026-07-14) ------------------------------------------------
# J's Desktop app + bare terminal `claude` CLI read THIS file by default (no per-project
# override). It must never point them at the CCR gateway -- see module docstring.
INTERACTIVE_SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
_ROUTER_URL_MARKERS = ("127.0.0.1:3456", "localhost:3456")
_ROUTER_ENV_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_BASE_URL", "CLAUDE_AGENT_API_BASE_URL")

# Primary restart path: direct node invocation (see module docstring for why).
NODE_EXE = Path(r"C:\Program Files\nodejs\node.exe")
CCR_CLI = Path(r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@musistudio\claude-code-router\dist\main\cli.js")
# Fallback restart path if the hardcoded node/cli.js paths ever drift (reinstall, etc).
CCR_PS1 = Path(r"C:\Users\jackw\AppData\Roaming\npm\ccr.ps1")


def _log_path() -> Path:
    return LOG_DIR / f"ccr-keepalive-{dt.date.today().isoformat()}.log"


def _log(msg: str) -> None:
    try:
        _log_path().parent.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001 -- logging must never be the thing that crashes this
        pass


def _now_et_str() -> str:
    return et_now().strftime("%Y-%m-%d %H:%M:%S")


def _probe_ccr(host: str = CCR_HOST, port: int = CCR_PORT, timeout: float = PROBE_TIMEOUT_SEC) -> bool:
    """TCP-connect probe only (no HTTP). True iff the socket connects. Never raises --
    ConnectionRefusedError/timeout/etc are all OSError subclasses and mean simply "down"."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"ts_et": None, "port_up": None, "consecutive_failures": 0,
             "last_restart_et": None, "ping_sent_this_episode": False,
             "interactive_settings_clean": None, "interactive_settings_last_fixed_et": None}


def _write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_user_mention() -> str:
    """Verbatim pattern from trade_today_watcher.py:_load_user_mention -- every Discord
    ping producer in this repo reuses this exact fail-open shape so a missing/malformed
    config degrades to a silent-but-sent, un-mentioned ping rather than a crash."""
    try:
        cfg = json.loads(DISCORD_CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


def _send_ping(msg: str) -> None:
    mention = _load_user_mention()
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "content": mention + msg,
            "source": "ccr_keepalive",
            "queued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }) + "\n")


def _scan_settings_for_router_leak(data: dict) -> list[str]:
    """Pure function (no I/O) -- unit-testable against synthetic fixtures as well as the
    real file. Returns a human-readable violation string per offending key found in a
    parsed ~/.claude/settings.json, or [] if the file is clean.

    2026-07-14 root cause: `~/.claude-code-router/config.json`'s Router.default is
    hardcoded to ollama with NO Anthropic provider entry, so ANY cold boot where CCR's
    fuller gateway/profile stack isn't yet live still leaves port 3456 listening (probe
    sees "up") while default-routed traffic -- including J's interactive session --
    silently resolves to local Ollama. The only durable fix is: J's interactive surfaces
    never carry the override in the first place.
    """
    violations: list[str] = []
    env = data.get("env") or {}
    for key in _ROUTER_ENV_KEYS:
        val = str(env.get(key, ""))
        if any(marker in val for marker in _ROUTER_URL_MARKERS):
            violations.append(f"env.{key}={val!r} points at the CCR gateway")
    helper = str(data.get("apiKeyHelper", ""))
    if "claude-code-router" in helper:
        violations.append(f"apiKeyHelper={helper!r} routes auth through CCR")
    return violations


def _strip_router_leak(data: dict) -> dict:
    """Immutable update (coding-style.md): returns a NEW dict with only the router-only
    top-level keys removed. Every other user setting (hooks, plugins, theme, model,
    autoCompact, ...) passes through untouched."""
    return {k: v for k, v in data.items() if k not in ("apiKeyHelper", "env")}


def _check_and_fix_interactive_settings() -> dict:
    """Guard: J's Desktop app + bare `claude` CLI (via ~/.claude/settings.json, the
    global default both entrypoints read) must NEVER depend on CCR being alive. Runs
    every keepalive fire, independent of the TCP probe above -- 2026-07-14 proved
    "port 3456 is listening" and "the gateway is serving real Claude" are NOT the same
    fact, so this checks the ACTUAL consumer-facing config, not a proxy for it.

    Returns {"checked": bool, "violations": [str, ...], "fixed": bool}. Fails open: any
    exception here is logged and swallowed -- this guard must never break the CCR-restart
    half of this script (OP-33e).
    """
    result = {"checked": False, "violations": [], "fixed": False}
    try:
        if not INTERACTIVE_SETTINGS_FILE.exists():
            return result
        raw = INTERACTIVE_SETTINGS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        result["checked"] = True
        violations = _scan_settings_for_router_leak(data)
        result["violations"] = violations
        if violations:
            # One dated backup per day, not one per 5-min fire.
            backup = INTERACTIVE_SETTINGS_FILE.with_name(
                f"settings.json.router-leak-{dt.date.today().isoformat()}.bak"
            )
            if not backup.exists():
                backup.write_text(raw, encoding="utf-8")
            cleaned = _strip_router_leak(data)
            INTERACTIVE_SETTINGS_FILE.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
            result["fixed"] = True
            _log(f"INTERACTIVE SETTINGS LEAK FIXED: {violations}")
            _send_ping(
                "CCR LEAK: ~/.claude/settings.json was re-pointing your Desktop app / "
                "claude CLI at the CCR gateway again (" + "; ".join(violations) + "). "
                "Auto-fixed just now -- removed the router override, your NEXT launch "
                "hits Anthropic directly (already-open sessions are unaffected either way). "
                "2026-07-14 lockout class -- see LESSONS-LEARNED."
            )
    except Exception as e:  # noqa: BLE001 -- must never break the restart loop
        _log(f"interactive-settings check FAILED (non-fatal): {e}")
    return result


def _restart_ccr() -> None:
    """Fire-and-forget launch. Never call .wait()/.communicate() on this -- ccr start's
    own child is detached+unref'd on its end; we must not risk blocking on ours."""
    if NODE_EXE.exists() and CCR_CLI.exists():
        cmd = [str(NODE_EXE), str(CCR_CLI), "start"]
        _log(f"  restart via direct node: {cmd}")
    else:
        _log("  node.exe or cli.js missing at the hardcoded path -- falling back to ccr.ps1")
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(CCR_PS1), "start"]
    subprocess.Popen(
        cmd,
        cwd=str(REPO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
        close_fds=True,
    )


def main() -> int:
    state = _load_state()
    consecutive_failures = int(state.get("consecutive_failures") or 0)
    last_restart_et = state.get("last_restart_et")
    ping_sent = bool(state.get("ping_sent_this_episode", False))

    # Interactive-path guard runs every fire, independent of the probe below (2026-07-14:
    # "port up" and "serving real Claude" are not the same fact -- see module docstring).
    interactive_check = _check_and_fix_interactive_settings()
    interactive_clean = not interactive_check["violations"]
    interactive_last_fixed_et = (
        _now_et_str() if interactive_check["fixed"] else state.get("interactive_settings_last_fixed_et")
    )

    if _probe_ccr():
        _log(f"CCR up ({CCR_HOST}:{CCR_PORT}) -- no action")
        _write_state({
            "ts_et": _now_et_str(),
            "port_up": True,
            "consecutive_failures": 0,
            "last_restart_et": last_restart_et,
            "ping_sent_this_episode": False,
            "interactive_settings_clean": interactive_clean,
            "interactive_settings_last_fixed_et": interactive_last_fixed_et,
        })
        return 0

    _log(f"CCR DOWN ({CCR_HOST}:{CCR_PORT}) -- attempting restart")
    try:
        _restart_ccr()
    except Exception as e:  # noqa: BLE001
        _log(f"  restart invocation FAILED to launch: {e}")

    time.sleep(RESTART_WAIT_SEC)
    now_et = _now_et_str()

    if _probe_ccr():
        _log("  restart OK -- CCR back up")
        _write_state({
            "ts_et": now_et,
            "port_up": True,
            "consecutive_failures": 0,
            "last_restart_et": now_et,
            "ping_sent_this_episode": False,
            "interactive_settings_clean": interactive_clean,
            "interactive_settings_last_fixed_et": interactive_last_fixed_et,
        })
        return 0

    consecutive_failures += 1
    _log(f"  restart FAILED -- still down (consecutive_failures={consecutive_failures})")

    if consecutive_failures >= PING_THRESHOLD and not ping_sent:
        _send_ping(
            f"CCR GATEWAY DOWN: {CCR_HOST}:{CCR_PORT} unreachable after "
            f"{consecutive_failures} consecutive restart attempts (~{consecutive_failures * 5} min). "
            f"Every `claude` CLI session routes through this gateway -- LLM scheduled fires are "
            f"failing ConnectionRefused. Manual check needed: `ccr start` / `ccr status`."
        )
        _log("  >= threshold, PINGED J (episode-deduped)")
        ping_sent = True

    _write_state({
        "ts_et": now_et,
        "port_up": False,
        "consecutive_failures": consecutive_failures,
        "last_restart_et": now_et,
        "ping_sent_this_episode": ping_sent,
        "interactive_settings_clean": interactive_clean,
        "interactive_settings_last_fixed_et": interactive_last_fixed_et,
    })
    return 0


def _main_safe() -> int:
    """Fail-open entry point -- ANY unhandled exception anywhere above is logged and
    swallowed. This keepalive must never be the reason a scheduled fire shows non-zero."""
    try:
        return main()
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL unhandled exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(_main_safe())
