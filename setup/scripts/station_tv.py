"""station_tv.py -- TV control over Wi-Fi for the Station "TV face"
(GOAL-GAMMA-STATION-2026-09-13 item (5) + the 2026-09-13 Wi-Fi/security amendments).

Talks to J's Samsung Tizen TV (discovered 2026-09-13, recorded in the gitignored
automation/state/station/tv.json) via `samsungtvws` -- pip install
"samsungtvws[async,encrypted]"==3.0.6, the ONE new dependency this build adds,
installed into backtest/.venv (every OTHER station_* module stays dependency-free).

SECURITY (J: "build this with safety guards"; amendment 6 tightened this further):
  * `tv_host`/`tv_mac`/`pc_lan_ips` are NEVER read from config.json (tracked in a
    PUBLIC repo) -- only from the gitignored tv.json, overlaid at runtime by
    load_config(). A missing tv.json is a loud "NOT CONFIGURED" on every command,
    never a guessed address.
  * NEVER discovers or broadcasts -- only ever connects to the single `tv_host`
    IP tv.json names. No ARP scan, no SSDP, no mDNS.
  * The pairing token lives ONLY in .tv-token (gitignored); --pair ACL-locks it
    to the current Windows user immediately after writing and this script never
    prints or logs its contents.
  * --pair refuses without --i-am-j, so no automated fire can trigger the TV's
    "Allow this device?" prompt -- only a human, deliberately.
  * Reads config.json / tv.json / .tv-token only -- never .mcp.json, secrets.json,
    .alpaca-keys, or any credential file.

FAIL OPEN, NEVER A TRACEBACK: unconfigured/unreachable/missing-dependency all
print ONE line and exit 0 -- must never block the kiosk fallback path.

Commands: --status --on --source <NAME> --volume <0-100> --key <KEY_XXX>
          --pair --i-am-j --open-url <URL> --face [--volume N]
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

SAMSUNGTVWS_VERSION = "3.0.6"  # pip install "samsungtvws[async,encrypted]"==3.0.6 into backtest/.venv, 2026-09-13
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_VOLUME_RESET_PRESSES = 50  # best-effort floor -- see cmd_volume's docstring

REPO = Path(__file__).resolve().parents[2]
STATION_DIR = REPO / "automation" / "state" / "station"
CONFIG_PATH = STATION_DIR / "config.json"
TV_JSON_PATH = STATION_DIR / "tv.json"
TOKEN_PATH = STATION_DIR / ".tv-token"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_board  # noqa: E402 -- reuse read_json_or_none + load_merged_station_config


def load_config() -> dict:
    """SECURITY (amendment 6, 2026-09-13): config.json is tracked in a PUBLIC
    repo and never stores tv_host/tv_mac/pc_lan_ips -- those live only in the
    gitignored tv.json, overlaid here at runtime. Raises ValueError("tv.json
    missing") if tv.json is absent/unreadable; every caller in this file must
    let that propagate as a printed "NOT CONFIGURED"/failure line, never guess
    an address."""
    return station_board.load_merged_station_config(CONFIG_PATH, TV_JSON_PATH)


def _load_config_safe() -> dict | None:
    """Every cmd_* function's entry point: load_config() but turn the
    "tv.json missing" ValueError into the same NOT-CONFIGURED print-and-
    return-0 contract every other missing-prerequisite path in this file
    already uses, instead of repeating a try/except in all eight commands."""
    try:
        return load_config()
    except ValueError as e:
        print(f"NOT CONFIGURED: {e}")
        return None


def station_face_url(config: dict) -> str:
    """The Station page URL to open on the TV -- ALWAYS computed from tv.json's
    real pc_lan_ips + config.json's non-identifying station_serve_port, never
    a literal stored in config.json (which is tracked in a public repo)."""
    pc_lan_ips = config.get("pc_lan_ips") or []
    if not pc_lan_ips:
        return ""
    port = int(config.get("station_serve_port", 8420))
    # The Tizen TV browser treats any URL with an explicit port as a Google search (2026-09-13), so the
    # face is served on port 80 and the URL carries no port suffix at all.
    suffix = "" if port == 80 else f":{port}"
    return f"http://{pc_lan_ips[0]}{suffix}/station?kiosk=1"


def _import_samsungtvws():
    """Lazy, guarded import -- this module must still `python -c "import station_tv"`
    cleanly even before the dependency is installed (e.g. a fresh checkout before the
    one-time `pip install` step runs). A missing dependency is a printed line, never
    an ImportError bubbling out of a caller (the kiosk fallback path depends on
    every command here returning 0 no matter what)."""
    try:
        from samsungtvws import SamsungTVWS
        return SamsungTVWS
    except ImportError as e:
        print(f"DEPS MISSING (run: backtest\\.venv\\Scripts\\python.exe -m pip install "
              f"\"samsungtvws[async,encrypted]\"=={SAMSUNGTVWS_VERSION}): {e}")
        return None


def _send_wol(mac: str) -> bool:
    """Broadcasts a standard Wake-on-LAN magic packet (6x 0xFF + 16x the target MAC,
    102 bytes) over UDP to the LAN broadcast address -- stdlib only, no new
    dependency, no discovery (the MAC is a fixed config value, never scanned for).
    Returns False (never raises) on a malformed MAC or a socket failure."""
    try:
        clean = mac.replace(":", "").replace("-", "")
        if len(clean) != 12:
            return False
        mac_bytes = bytes.fromhex(clean)
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, ("255.255.255.255", 9))
        return True
    except Exception:  # noqa: BLE001 -- WoL is best-effort, never fatal
        return False


def _lock_token_acl() -> str:
    """Restricts .tv-token to the current Windows user only. Best-effort: a failure
    is reported, never raised -- the file is already gitignored either way, this is
    defense in depth, not the only guard."""
    if not TOKEN_PATH.exists():
        return "skipped (no token file written)"
    try:
        user = os.environ.get("USERNAME", "")
        if not user:
            return "skipped (USERNAME env var unavailable)"
        out = subprocess.run(
            ["icacls", str(TOKEN_PATH), "/inheritance:r", "/grant:r", f"{user}:R"],
            capture_output=True, text=True, timeout=10, creationflags=_CREATE_NO_WINDOW,
        )
        ok = out.returncode == 0
        return f"locked to {user}" if ok else f"icacls exit {out.returncode}: {out.stdout.strip()[:120]}"
    except Exception as e:  # noqa: BLE001
        return f"icacls failed: {e.__class__.__name__}"


def cmd_status(_args) -> int:
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    host = (cfg.get("tv_host") or "").strip()
    if not host:
        print("NOT CONFIGURED: automation/state/station/config.json has no tv_host")
        return 0
    SamsungTVWS = _import_samsungtvws()
    if SamsungTVWS is None:
        return 0
    try:
        tv = SamsungTVWS(host=host, port=8001, timeout=3)
        info = tv.rest_device_info()
        dev = info.get("device", {}) if isinstance(info, dict) else {}
        print(f"ONLINE host={host} name={dev.get('name', '?')} model={dev.get('modelName', '?')} "
              f"tokenAuth={dev.get('TokenAuthSupport', '?')} type={dev.get('type', '?')} "
              f"os={dev.get('OS', '?')}")
    except Exception as e:  # noqa: BLE001 -- an unreachable TV is a status line, never a crash
        print(f"UNREACHABLE host={host} ({e.__class__.__name__}: {str(e)[:120]})")
    return 0


def cmd_on(_args) -> int:
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    mac = (cfg.get("tv_mac") or "").strip()
    host = (cfg.get("tv_host") or "").strip()
    if not mac and not host:
        print("NOT CONFIGURED: no tv_mac/tv_host in config.json")
        return 0
    if mac:
        print(f"WOL {'sent' if _send_wol(mac) else 'failed'} to {mac}")
    if not host:
        return 0
    SamsungTVWS = _import_samsungtvws()
    if SamsungTVWS is None:
        return 0
    for attempt in range(3):
        try:
            tv = SamsungTVWS(host=host, port=8001, timeout=3)
            tv.rest_device_info()
            print(f"CONNECTED host={host} (attempt {attempt + 1})")
            return 0
        except Exception:  # noqa: BLE001 -- keep retrying the bounded window, then report
            time.sleep(2)
    print(f"NOT YET REACHABLE host={host} (TV may still be waking from standby)")
    return 0


def _connect(cfg: dict, *, timeout: int = 6):
    """Shared setup for every websocket-based command (source/key/open_url/
    volume/face): host check, guarded samsungtvws import, connection build.
    Returns (tv_or_None, host) -- caller returns 0 immediately when tv is None,
    a NOT-CONFIGURED/DEPS-MISSING line has already been printed."""
    host = (cfg.get("tv_host") or "").strip()
    if not host:
        print("NOT CONFIGURED: no tv_host in config.json")
        return None, host
    SamsungTVWS = _import_samsungtvws()
    if SamsungTVWS is None:
        return None, host
    # Port 8002 = the token-authenticated secure websocket (tokenAuth=true on this Tizen TV; port 8001 answers
    # 'ms.channel.unauthorized' before any Allow prompt -- observed live 2026-09-13 18:4x ET). REST info stays on 8001.
    return SamsungTVWS(host=host, port=8002, token_file=str(TOKEN_PATH), timeout=timeout), host


def cmd_source(args) -> int:
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    tv, host = _connect(cfg)
    if tv is None:
        return 0
    name = args.source.strip()
    key = name if name.upper().startswith("KEY_") else f"KEY_{name.upper()}"
    try:
        tv.send_key(key)
        print(f"SENT {key} to {host}")
        tv.close()
    except Exception as e:  # noqa: BLE001
        print(f"UNREACHABLE/FAILED host={host} key={key} ({e.__class__.__name__}: {str(e)[:120]})")
    return 0


def cmd_volume(args) -> int:
    """Best-effort APPROXIMATE absolute volume. Samsung's remote-control protocol
    (send_key/shortcuts, the only surface samsungtvws exposes) has no absolute
    getter or setter -- only relative volume_up()/volume_down()/mute(). This resets
    toward the floor with a fixed number of volume_down presses (a guess generous
    enough to bottom out on any Samsung model's own 0-N scale, never verified
    against this specific TV's real ceiling) and then presses volume_up() once per
    requested unit. That is NOT a calibrated 1-to-1 mapping onto the TV's own 0-100
    display -- it is the most honest approximation available without an absolute API
    to read back against."""
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    tv, host = _connect(cfg, timeout=10)
    if tv is None:
        return 0
    level = max(0, min(100, args.volume))
    try:
        sc = tv.shortcuts()
        for _ in range(_VOLUME_RESET_PRESSES):
            sc.volume_down()
        for _ in range(level):
            sc.volume_up()
        tv.close()
        print(f"VOLUME approx {level} via {_VOLUME_RESET_PRESSES} down-resets + {level} up-presses "
              f"(best-effort -- no absolute volume API exists on this TV's remote protocol)")
    except Exception as e:  # noqa: BLE001
        print(f"UNREACHABLE/FAILED host={host} ({e.__class__.__name__}: {str(e)[:120]})")
    return 0


def cmd_key(args) -> int:
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    tv, host = _connect(cfg)
    if tv is None:
        return 0
    try:
        tv.send_key(args.key)
        print(f"SENT {args.key} to {host}")
        tv.close()
    except Exception as e:  # noqa: BLE001
        print(f"UNREACHABLE/FAILED host={host} key={args.key} ({e.__class__.__name__}: {str(e)[:120]})")
    return 0


def cmd_open_url(args) -> int:
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    tv, host = _connect(cfg, timeout=10)
    if tv is None:
        return 0
    try:
        tv.open_browser(args.open_url)
        print(f"OPENED {args.open_url} on {host}")
        tv.close()
    except Exception as e:  # noqa: BLE001
        print(f"UNREACHABLE/FAILED host={host} url={args.open_url} ({e.__class__.__name__}: {str(e)[:160]})")
    return 0


def cmd_face(args) -> int:
    """Wake (WoL) + open the configured Station URL, optionally set volume. This is
    what station_kiosk.ps1 -Start calls when the PC has no second display -- it must
    NEVER raise and must always return 0, since a bad TV state must never take down
    the rest of the kiosk keepalive fire."""
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    host = (cfg.get("tv_host") or "").strip()
    mac = (cfg.get("tv_mac") or "").strip()
    station_url = station_face_url(cfg)
    if not station_url:
        print("NOT CONFIGURED: tv.json has no pc_lan_ips -- cannot compute the Station URL")
        return 0
    if not host:
        print("NOT CONFIGURED: no tv_host in config.json")
        return 0
    if mac:
        print(f"WOL {'sent' if _send_wol(mac) else 'failed'} to {mac}")
        time.sleep(3)  # give the TV a moment off standby before the websocket connect attempt
    SamsungTVWS = _import_samsungtvws()
    if SamsungTVWS is None:
        return 0
    try:
        tv = SamsungTVWS(host=host, port=8002, token_file=str(TOKEN_PATH), timeout=8)  # 8002 = token-auth WSS
        # Researched 2026-09-13 (xchwarze/samsung-tv-ws-api APPLICATIONS.md): the Internet app's id changed on
        # 2020+ Tizen sets -- "3202010022079" (newest) / "3201907018784" / legacy "org.tizen.browser", which is
        # what samsungtvws.open_browser() sends and which launched nothing on this QN43Q8FAAFXZA. Send the newest
        # id first, then the others (a repeat launch of the same app is harmless). Config may pin one.
        ids = [i for i in [cfg.get("tv_browser_app_id"), "3202010022079", "3201907018784", "org.tizen.browser"] if i]
        for i, app_id in enumerate(dict.fromkeys(ids)):
            tv.run_app(app_id, "NATIVE_LAUNCH", station_url)
            print(f"FACE launch sent app_id={app_id} url={station_url} on {host}")
            if i < len(ids) - 1:
                time.sleep(4)
        if args.volume is not None:
            level = max(0, min(100, args.volume))
            sc = tv.shortcuts()
            for _ in range(_VOLUME_RESET_PRESSES):
                sc.volume_down()
            for _ in range(level):
                sc.volume_up()
            print(f"VOLUME approx {level} (best-effort, see --volume)")
        tv.close()
    except Exception as e:  # noqa: BLE001
        print(f"UNREACHABLE/FAILED host={host} ({e.__class__.__name__}: {str(e)[:160]})")
    return 0


def cmd_pair(args) -> int:
    """The ONLY command that may trigger the TV's "Allow this device?" prompt --
    refuses outright without --i-am-j so no automated fire can ever reach this
    branch. J presses Allow on the TV itself; this process just waits out its
    timeout for that to happen."""
    if not args.i_am_j:
        print("REFUSED: --pair requires --i-am-j (a human must be at the TV to press "
              "Allow -- an automated fire may never trigger this prompt)")
        return 0
    cfg = _load_config_safe()
    if cfg is None:
        return 0
    host = (cfg.get("tv_host") or "").strip()
    if not host:
        print("NOT CONFIGURED: no tv_host in config.json")
        return 0
    SamsungTVWS = _import_samsungtvws()
    paired = False
    if SamsungTVWS is not None:
        try:
            tv = SamsungTVWS(host=host, port=8002, token_file=str(TOKEN_PATH), timeout=45)  # 8002 = token-auth WSS
            tv.open()  # the call that pops "Allow this device?" on the TV screen
            tv.close()
            paired = True
        except Exception as e:  # noqa: BLE001
            print(f"PAIR FAILED host={host} ({e.__class__.__name__}: {str(e)[:160]})")
    if paired:
        print(f"PAIRED (or already paired) with {host} -- token written to "
              f"{TOKEN_PATH.relative_to(REPO).as_posix()}")
    print(f"TOKEN ACL: {_lock_token_acl()}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="Station TV control (Samsung Tizen, Wi-Fi, samsungtvws).")
    ap.add_argument("--status", action="store_true", help="REST device-info probe, no pairing needed")
    ap.add_argument("--on", action="store_true", help="Wake-on-LAN + bounded reachability check")
    ap.add_argument("--source", metavar="NAME", help="send a remote key, e.g. HDMI1")
    ap.add_argument("--volume", type=int, metavar="0-100", help="best-effort approximate absolute volume")
    ap.add_argument("--key", metavar="KEY_XXX", help="send one raw remote key")
    ap.add_argument("--pair", action="store_true", help="establish the websocket once so the TV can prompt Allow")
    ap.add_argument("--i-am-j", action="store_true", help="required alongside --pair")
    ap.add_argument("--open-url", metavar="URL", help="open a URL in the TV's browser")
    ap.add_argument("--face", action="store_true", help="wake + open the configured station_url (optional --volume)")
    args = ap.parse_args(argv)

    if args.status:
        return cmd_status(args)
    if args.on:
        return cmd_on(args)
    if args.source is not None:
        return cmd_source(args)
    if args.key is not None:
        return cmd_key(args)
    if args.pair:
        return cmd_pair(args)
    if args.open_url is not None:
        return cmd_open_url(args)
    if args.face:
        return cmd_face(args)
    if args.volume is not None:
        return cmd_volume(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
