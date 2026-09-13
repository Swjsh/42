"""Guard: the station security amendments (2026-09-13) -- automation/state/
station/config.json is TRACKED in a PUBLIC repo (github.com/Swjsh/42) and must
never carry real network facts (a discovered TV's IP/MAC, this PC's own LAN
IPs). Those live ONLY in the gitignored tv.json and are overlaid onto
config.json in memory at runtime by station_board.load_merged_station_config().

Also locks in station_serve.py's AllowlistProxyHandler: the 403/404/405
decisions, and that error bodies never echo the request path/query back (no
reflected-XSS surface in this hand-rolled proxy).
"""
from __future__ import annotations

import json
import re
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import station_board as sb  # noqa: E402
import station_serve as ss  # noqa: E402

CONFIG_PATH = REPO / "automation" / "state" / "station" / "config.json"

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}\b")

# The ONLY dotted-quad-shaped strings this config is allowed to carry are
# generic/non-identifying addresses: 127.0.0.1 (loopback -- "this machine",
# true of every machine on earth) and 0.0.0.0 (the wildcard/"no specific
# address" -- this repo's own doc prose names it explicitly as the bind
# address to AVOID, so it legitimately appears in comments, not as a real
# configured value). Neither identifies J's network.
_ALLOWED_IPV4 = {"127.0.0.1", "0.0.0.0"}


# ============================================================================
# config.json (tracked, public repo) -- no real network facts, ever
# ============================================================================

def test_tracked_config_json_carries_no_real_ip_or_mac():
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    ip_hits = [m.group(0) for m in _IPV4_RE.finditer(raw) if m.group(0) not in _ALLOWED_IPV4]
    mac_hits = _MAC_RE.findall(raw)
    assert not ip_hits, f"config.json (public repo) contains non-loopback IP-shaped value(s): {ip_hits}"
    assert not mac_hits, f"config.json (public repo) contains MAC-shaped value(s): {mac_hits}"


def test_tracked_config_json_identifying_keys_are_placeholders():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("tv_host", "tv_mac", "tv_name", "tv_model", "station_url"):
        assert cfg.get(key, "") == "", f"config.json key {key!r} must be an empty placeholder, got {cfg.get(key)!r}"
    assert cfg.get("pc_lan_ips") == [], f"config.json pc_lan_ips must be empty, got {cfg.get('pc_lan_ips')!r}"


def test_tracked_config_json_keeps_non_identifying_keys():
    """The fix must not over-correct into deleting keys that were never
    identifying in the first place."""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(cfg.get("station_serve_port"), int)
    assert cfg.get("dashboard_origin", "").startswith("http://127.0.0.1")
    assert isinstance(cfg.get("kiosk_display_index"), int)


# ============================================================================
# station_board.load_merged_station_config -- fail-loud on missing tv.json
# ============================================================================

def test_load_merged_station_config_raises_when_tv_json_missing(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"model": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="tv.json missing"):
        sb.load_merged_station_config(config_path, tmp_path / "does-not-exist-tv.json")


def test_load_merged_station_config_overlays_tv_json_fields(tmp_path):
    config_path = tmp_path / "config.json"
    tv_path = tmp_path / "tv.json"
    config_path.write_text(json.dumps({"tv_host": "", "tv_mac": "", "pc_lan_ips": [],
                                       "station_serve_port": 8420}), encoding="utf-8")
    tv_path.write_text(json.dumps({"tv_host": "10.0.0.5", "tv_mac": "AA:BB:CC:DD:EE:FF",
                                   "pc_lan_ips": ["10.0.0.9"]}), encoding="utf-8")
    merged = sb.load_merged_station_config(config_path, tv_path)
    assert merged["tv_host"] == "10.0.0.5"
    assert merged["tv_mac"] == "AA:BB:CC:DD:EE:FF"
    assert merged["pc_lan_ips"] == ["10.0.0.9"]
    assert merged["station_serve_port"] == 8420, "non-overlaid keys must pass through from config.json"


def test_load_merged_station_config_missing_config_json_still_fails_loud_on_tv_json(tmp_path):
    # config.json itself is fail-OPEN ({} on missing/garbled); tv.json is fail-LOUD.
    tv_path = tmp_path / "tv.json"
    tv_path.write_text(json.dumps({"tv_host": "10.0.0.5"}), encoding="utf-8")
    merged = sb.load_merged_station_config(tmp_path / "no-config.json", tv_path)
    assert merged["tv_host"] == "10.0.0.5"


# ============================================================================
# station_serve.py -- resolve_bind_and_allowlist never defaults to a wildcard
# ============================================================================

def test_resolve_bind_and_allowlist_raises_without_pc_lan_ips():
    with pytest.raises(ValueError):
        ss.resolve_bind_and_allowlist({"pc_lan_ips": []})


def test_resolve_bind_and_allowlist_never_returns_0000():
    bind_ip, port, allowlist, upstream = ss.resolve_bind_and_allowlist(
        {"pc_lan_ips": ["192.0.2.17"], "tv_host": "192.0.2.10", "station_serve_port": 8420})
    assert bind_ip == "192.0.2.17"
    assert bind_ip != "0.0.0.0"
    assert allowlist == {"127.0.0.1", "192.0.2.17", "192.0.2.10"}


# ============================================================================
# station_serve.py -- AllowlistProxyHandler: real handler class, mocked I/O
# (no real socket, no real upstream fetch) -- exercises the SAME code path a
# live curl probe hits, per BaseHTTPRequestHandler's own documented seam.
# ============================================================================

def _make_handler_instance(allowlist, client_ip, path, method="GET"):
    """Constructs a real AllowlistProxyHandler instance without going through
    socketserver's normal __init__ (which wants a live socket) -- the
    standard technique for unit-testing BaseHTTPRequestHandler subclasses:
    bind the class's methods to a plain object carrying the attributes they
    read (client_address, command, path, wfile) and a mocked send_response/
    send_header/end_headers trio to capture what would have gone on the wire."""
    handler_cls = ss.make_handler(allowlist, "http://127.0.0.1:9/unused")
    inst = handler_cls.__new__(handler_cls)
    inst.client_address = (client_ip, 54321)
    inst.command = method
    inst.path = path
    inst.wfile = BytesIO()
    inst.send_response = MagicMock()
    inst.send_header = MagicMock()
    inst.end_headers = MagicMock()
    return inst


def test_proxy_denies_non_allowlisted_ip_with_403_no_echo():
    inst = _make_handler_instance({"10.0.0.5"}, "10.9.9.9", "/station?x=1")
    inst._proxy()
    inst.send_response.assert_called_once_with(403)
    body = inst.wfile.getvalue()
    assert body == b"Forbidden"
    assert b"10.9.9.9" not in body and b"x=1" not in body, "error body must never echo request input"


def test_proxy_allows_allowlisted_ip_past_the_gate():
    # Path is disallowed (not upstream-reachable in this test), so the FIRST
    # gate this proves is that an allowlisted IP does NOT get 403 -- it
    # proceeds to the path check next (404), never denied for its identity.
    inst = _make_handler_instance({"192.0.2.17"}, "192.0.2.17", "/not-a-real-path")
    inst._proxy()
    inst.send_response.assert_called_once_with(404)


def test_proxy_404s_a_path_outside_the_allowlist():
    inst = _make_handler_instance({"127.0.0.1"}, "127.0.0.1", "/etc/passwd")
    inst._proxy()
    inst.send_response.assert_called_once_with(404)


@pytest.mark.parametrize("path", ["/station", "/api/station", "/favicon.ico", "/_next/static/x.js"])
def test_proxy_path_allowlist_accepts_expected_paths_shape(path):
    # Confirms the allowlist LOGIC recognizes each path as allowed (does not
    # 404 it) -- the subsequent upstream fetch will fail in this offline test
    # (no real server on the unused port), which the handler turns into a 502,
    # never a 403/404/405. Proves the path gate specifically, independent of
    # network reachability.
    inst = _make_handler_instance({"127.0.0.1"}, "127.0.0.1", path)
    inst._proxy()
    inst.send_response.assert_called_once()
    status = inst.send_response.call_args[0][0]
    assert status != 403 and status != 404, f"{path} should pass the allowlist/path gate (got {status})"


def test_proxy_rejects_post_with_405():
    inst = _make_handler_instance({"127.0.0.1"}, "127.0.0.1", "/station", method="POST")
    inst.do_POST()
    inst.send_response.assert_called_once_with(405)


@pytest.mark.parametrize("method,fn_name", [
    ("PUT", "do_PUT"), ("DELETE", "do_DELETE"), ("PATCH", "do_PATCH"),
])
def test_proxy_rejects_other_mutating_methods_with_405(method, fn_name):
    inst = _make_handler_instance({"127.0.0.1"}, "127.0.0.1", "/station", method=method)
    getattr(inst, fn_name)()
    inst.send_response.assert_called_once_with(405)
