"""station_serve.py -- the Station's LAN reverse proxy (GOAL-GAMMA-STATION-2026-09-13
item (5), Wi-Fi/security amendments 2026-09-13).

WHAT THIS IS: a stdlib-only HTTP proxy that lets the Samsung TV's browser (which
cannot reach 127.0.0.1 -- that is THIS PC's loopback, not the TV's) open the
dashboard's `/station` page over the LAN. It forwards a small allowlisted set of
GET/HEAD requests to the already-running Next.js dashboard at
`http://127.0.0.1:3000` and denies everything else.

SECURITY (J, 2026-09-13 "build this with safety guards -- credentials, open ports,
everything security conscious"):
  * Binds ONLY to this PC's own LAN IP (`pc_lan_ips[0]`, sourced from the
    gitignored tv.json -- never from the tracked config.json, see amendment 6
    below) -- NEVER 0.0.0.0. A process bound to a specific interface is
    unreachable from anywhere Windows doesn't already route that IP to.
  * config.json is tracked in a PUBLIC repo and never stores real network
    facts. tv_host/tv_mac/pc_lan_ips live ONLY in the gitignored tv.json and
    are overlaid onto config.json in memory (station_board.
    load_merged_station_config); a missing tv.json is a loud startup failure,
    never a silent wildcard bind.
  * Application-level allowlist BEFORE any routing: the requesting IP must be
    `tv_host`, 127.0.0.1, or one of `pc_lan_ips` -- everyone else gets 403 with a
    static body (no echoed input, so there is nothing here for a reflected-XSS
    probe to reflect).
  * GET/HEAD only -- every other method is 405. This proxy has no reason to ever
    carry a mutating request: the TV is a read-only kiosk view (`?kiosk=1` hides
    the dashboard's own action buttons and chat box), and every interactive
    Test/Kill/Ask/"Talk to Gamma" call happens directly against the dashboard on
    127.0.0.1:3000, never through this LAN path.
  * Path allowlist: exactly `/station`, `/api/station`, `/favicon.ico`, and
    anything under `/_next/` (Next.js's own hashed static asset prefix, required
    for the page's CSS/JS to load) -- everything else is 404. No directory
    listing exists anywhere in this file; there is no directory being served,
    only a fixed set of forwarded paths.
  * Every response carries `Cache-Control: no-store` and every request is logged
    with its client IP, method, path, and outcome to a plain log file.
  * NEVER reads or writes .mcp.json, secrets.json, .alpaca-keys, or any
    credential file. NEVER discovers or broadcasts on the network -- the only
    two addresses this file ever contacts are the fixed upstream
    (dashboard_origin, default 127.0.0.1:3000) and whatever client already
    connected to it.
  * This module places no order, calls no LLM, and does not touch the trading
    path in any way -- it is a dumb, narrow, read-only pipe.

Usage: python station_serve.py [--once-check]
  (no args)     start the proxy and block forever (serve_forever) -- this is
                the mode the kiosk keepalive launches via the hidden
                wscript->run_exe_hidden.vbs->pythonw chain, same as every other
                always-on daemon in this repo.
  --once-check  print the resolved bind address + allowlist and exit 0 without
                binding a socket -- a cheap sanity check for -Status callers
                that must never actually hold the port.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
STATION_DIR = REPO / "automation" / "state" / "station"
CONFIG_PATH = STATION_DIR / "config.json"
TV_JSON_PATH = STATION_DIR / "tv.json"
LOG_DIR = Path("E:/Gamma/logs")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_board  # noqa: E402 -- reuse read_json_or_none + load_merged_station_config
from et_clock import et_now, et_today_str  # noqa: E402

DEFAULT_PORT = 8420
DEFAULT_UPSTREAM = "http://127.0.0.1:3000"

# Fixed, minimal path allowlist -- see the module docstring for why each entry
# exists. Never grown to a wildcard/passthrough without re-reading that
# reasoning; a new page needing this proxy is a new named entry, not "allow /".
ALLOWED_EXACT_PATHS = {
    "/station", "/api/station", "/api/station/tv-probe",  # tv-probe: GET-only self-report, see the Next route
    "/favicon.ico", "/webgl-canary.html", "/hq", "/api/hq",
}
ALLOWED_PATH_PREFIXES = ("/_next/",)

UPSTREAM_TIMEOUT_S = 10


def load_config() -> dict:
    """SECURITY (amendment 6): the merged view (config.json + tv.json overlay) --
    never the raw config.json alone, since tv_host/tv_mac/pc_lan_ips only exist
    in the gitignored tv.json. Raises ValueError("tv.json missing") if tv.json
    is absent/unreadable -- propagated by the caller, never swallowed here."""
    return station_board.load_merged_station_config(CONFIG_PATH, TV_JSON_PATH)


def resolve_bind_and_allowlist(config: dict) -> tuple:
    """Returns (bind_ip, port, allowlist_set, upstream_origin). Fails loud (raises
    ValueError) rather than falling back to a wildcard bind -- an unconfigured
    pc_lan_ips is a reason to refuse to start, never a reason to guess 0.0.0.0.
    The allowlist is built ENTIRELY from tv.json's own pc_lan_ips + tv_host
    (already overlaid onto `config` by load_config()) plus the fixed loopback
    address -- nothing here is hardcoded to this specific TV or PC."""
    pc_lan_ips = config.get("pc_lan_ips") or []
    if not pc_lan_ips or not isinstance(pc_lan_ips, list):
        raise ValueError("tv.json has no pc_lan_ips -- refusing to bind a wildcard address")
    bind_ip = str(pc_lan_ips[0])
    port = int(config.get("station_serve_port", DEFAULT_PORT))
    upstream = str(config.get("dashboard_origin", DEFAULT_UPSTREAM)).rstrip("/")
    allowlist = {"127.0.0.1"}
    allowlist.update(str(ip) for ip in pc_lan_ips)
    tv_host = str(config.get("tv_host") or "").strip()
    if tv_host:
        allowlist.add(tv_host)
    return bind_ip, port, allowlist, upstream


def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = f"[{et_now().strftime('%Y-%m-%d %H:%M:%S ET')}] {msg}\n"
        with (LOG_DIR / f"station-serve-{et_today_str()}.log").open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001 -- logging must never crash the proxy
        pass


def make_handler(allowlist: set, upstream: str):
    class AllowlistProxyHandler(BaseHTTPRequestHandler):
        server_version = "GammaStationProxy/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # noqa: A002 -- stdlib override, keep name
            _log(f"{self.client_address[0]} {fmt % args}")

        def _deny(self, code: int, reason: str) -> None:
            body = reason.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _allowed_path(self, path: str) -> bool:
            return path in ALLOWED_EXACT_PATHS or path.startswith(ALLOWED_PATH_PREFIXES)

        def _proxy(self) -> None:
            client_ip = self.client_address[0]
            if client_ip not in allowlist:
                _log(f"403 client_ip={client_ip} path={self.path}")
                self._deny(403, "Forbidden")
                return

            parsed = urlsplit(self.path)
            if not self._allowed_path(parsed.path):
                _log(f"404 client_ip={client_ip} path={parsed.path}")
                self._deny(404, "Not Found")
                return

            # Static test page served straight from disk (Next.js only serves public/ files that existed at build
            # time, and a rebuild is not worth a 2-minute WebGL canary on the TV). Read-only, fixed path.
            if parsed.path == "/webgl-canary.html":
                canary = Path(__file__).resolve().parents[2] / "dashboard" / "public" / "webgl-canary.html"
                if canary.exists():
                    body = canary.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    _log(f"200 client_ip={client_ip} path={parsed.path} (static)")
                    return

            upstream_url = upstream + self.path  # query string (e.g. ?kiosk=1) passes through as-is
            # J (2026-09-13): the TV address is just http://<pc-lan-ip>/station -- a bare /station from a LAN
            # client (the TV) is the kiosk view; the PC's own full UI stays at http://127.0.0.1:3000/station.
            if parsed.path == "/station" and not parsed.query and client_ip != "127.0.0.1":
                upstream_url = upstream + "/station?kiosk=1"
            try:
                req = urllib.request.Request(upstream_url, method=self.command)
                with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT_S) as resp:  # noqa: S310 -- fixed upstream only
                    body = resp.read()
                    self.send_response(resp.status)
                    content_type = resp.headers.get("Content-Type", "application/octet-stream")
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    _log(f"{resp.status} client_ip={client_ip} path={parsed.path}")
            except urllib.error.HTTPError as e:
                # The dashboard itself answered with an error status -- pass it
                # through honestly rather than masking it as a proxy failure.
                body = (e.read() or b"")
                self.send_response(e.code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                _log(f"{e.code} (upstream) client_ip={client_ip} path={parsed.path}")
            except Exception as exc:  # noqa: BLE001 -- upstream down/unreachable -> 502, never a crash
                _log(f"502 client_ip={client_ip} path={parsed.path} error={exc.__class__.__name__}")
                self._deny(502, "Bad Gateway -- dashboard unreachable")

        def do_GET(self) -> None:  # noqa: N802 -- stdlib method name
            self._proxy()

        def do_HEAD(self) -> None:  # noqa: N802
            self._proxy()

        def _method_not_allowed(self) -> None:
            _log(f"405 client_ip={self.client_address[0]} method={self.command} path={self.path}")
            self._deny(405, "Method Not Allowed -- this proxy is read-only (GET/HEAD)")

        def do_POST(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_PUT(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_DELETE(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_PATCH(self) -> None:  # noqa: N802
            self._method_not_allowed()

    return AllowlistProxyHandler


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """One page server per port, enforced at bind time (2026-09-13). The stdlib
    default allow_reuse_address=True sets SO_REUSEADDR, which on WINDOWS lets a
    second process bind the same ip:port successfully -- seven station_serve.py
    processes were found alive at 19:48 ET, each with whichever allowlist it was
    started with, and the TV got a 404 from a stale one. SO_EXCLUSIVEADDRUSE makes
    the second bind fail loudly (WinError 10048) instead."""

    allow_reuse_address = False

    def server_bind(self):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="Station LAN reverse proxy (read-only, allowlisted).")
    ap.add_argument("--once-check", action="store_true",
                    help="print the resolved bind/allowlist and exit without binding a socket")
    args = ap.parse_args(argv)

    try:
        config = load_config()
        bind_ip, port, allowlist, upstream = resolve_bind_and_allowlist(config)
    except ValueError as e:
        print(f"NOT CONFIGURED: {e}")
        return 0 if args.once_check else 1

    if args.once_check:
        print(json.dumps({
            "bind": f"{bind_ip}:{port}", "allowlist": sorted(allowlist), "upstream": upstream,
        }, indent=2))
        return 0

    handler = make_handler(allowlist, upstream)
    try:
        httpd = ExclusiveThreadingHTTPServer((bind_ip, port), handler)
    except OSError as e:
        _log(f"FAILED to bind {bind_ip}:{port}: {e}")
        print(f"FAILED to bind {bind_ip}:{port}: {e}")
        return 1

    _log(f"listening on {bind_ip}:{port} -> {upstream}, allowlist={sorted(allowlist)}")
    print(f"listening on {bind_ip}:{port} -> {upstream}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
