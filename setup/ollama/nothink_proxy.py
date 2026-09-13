#!/usr/bin/env python3
"""nothink_proxy.py - make Claude Code's request shape acceptable to Ollama's /v1/messages.

WHY (root-caused 2026-07-08): qwen thinking-native models "think" for 30-120s per turn because
Claude Code never sends thinking:{type:disabled}; this proxy injects it.

WHY MORE (root-caused 2026-09-13, GAMMA-STATION item 8): in non-bare mode Claude Code 2.1.x also
sends things Ollama's compatibility layer does not accept: a mid-conversation {"role":"system"}
message (the GGUF Jinja template raised 'System message must be at the beginning'; Ollama's own
renderer then answered 'no user query found in messages'), plus output_config/effort and per-block
cache_control. Ollama's docs (docs.ollama.com/api/anthropic-compatibility) list prompt caching,
tool_choice and metadata as unsupported. So the proxy now NORMALIZES every /v1/messages request:
  * thinking -> {type: disabled}
  * role:"system" entries inside `messages` are folded into the top-level `system` (text kept, order kept)
  * output_config / fallbacks / context_management / metadata / tool_choice / betas are dropped
  * cache_control keys are stripped from system + content blocks
  * one log line per request (roles, drops, upstream status) -> automation/state/logs/nothink-proxy.log
Fully isolated: no global config, no router, no effect on the desktop app. Fail-open: any exception
in normalization forwards the original body untouched.

Point Claude Code at it:  ANTHROPIC_BASE_URL=http://localhost:11435
Upstream Ollama stays on: http://localhost:11434

Run:  python setup/ollama/nothink_proxy.py         (defaults 11435 -> 11434)
"""
import datetime as _dt
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
UPSTREAM = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:11434"
_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "..", "..", "automation", "state", "logs", "nothink-proxy.log")
BRAIN_MODE_PATH = os.path.join(_HERE, "..", "..", "automation", "state", "brain-mode.json")
DROP_TOP = ("output_config", "fallbacks", "context_management", "metadata", "tool_choice", "betas")


def _model_map() -> dict:
    """brain-mode.json 'map' (tier -> local model). Read per request so a mode flip needs no restart.
    Fail-open: unreadable file -> empty map -> model ids pass through untouched."""
    try:
        with open(BRAIN_MODE_PATH, encoding="utf-8-sig") as fh:
            return json.load(fh).get("map") or {}
    except Exception:  # noqa: BLE001
        return {}


def rewrite_model(payload: dict, model_map: dict) -> str:
    """GAMMA-STATION Slice 0 (2026-09-13): Claude Code resolves its own aliases ('sonnet' ->
    'claude-sonnet-5', Agent(model:'haiku') -> 'claude-haiku-4-5', ...) and ignores ANTHROPIC_MODEL for
    subagent spawns, so a local-brain fire that fans out would send Anthropic model ids to Ollama.
    Map any 'claude-<tier>*' id onto the tier's local model. Returns the log token 'old->new' or 'old'."""
    requested = str(payload.get("model") or "")
    for tier, local in model_map.items():
        if local and requested.startswith("claude-" + str(tier)):
            payload["model"] = local
            return f"{requested}->{local}"
    return requested


def _log(line: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + line + "\n")
    except Exception:
        pass


def _strip_cache_control(blocks):
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict):
                b.pop("cache_control", None)
    return blocks


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def normalize(payload: dict) -> dict:
    """Return (payload, summary) with Claude-Code-only fields folded/dropped for Ollama."""
    summary = {"roles": [], "folded_system": 0, "dropped": []}
    summary["model"] = rewrite_model(payload, _model_map())
    payload["thinking"] = {"type": "disabled"}
    for k in DROP_TOP:
        if k in payload:
            payload.pop(k, None)
            summary["dropped"].append(k)
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        kept, folded = [], []
        for m in msgs:
            role = m.get("role") if isinstance(m, dict) else None
            if role == "system":
                txt = _text_of(m.get("content"))
                if txt.strip():
                    folded.append(txt)
                summary["folded_system"] += 1
                continue
            if isinstance(m, dict):
                _strip_cache_control(m.get("content"))
            kept.append(m)
        payload["messages"] = kept
        summary["roles"] = [m.get("role") for m in kept if isinstance(m, dict)]
        # diagnostic: shape of the last two messages (block types + text lengths), never the text itself
        shapes = []
        for m in kept[-2:]:
            c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, str):
                shapes.append(f"{m.get('role')}:str{len(c)}")
            elif isinstance(c, list):
                shapes.append(m.get("role") + ":[" + ",".join(
                    (b.get("type", "?") + ("%d" % len(b.get("text", "")) if b.get("type") == "text" else ""))
                    if isinstance(b, dict) else "?" for b in c) + "]")
            else:
                shapes.append(f"{m.get('role')}:{type(c).__name__}")
        summary["shapes"] = shapes
        sv = payload.get("system")
        summary["system"] = ("str%d" % len(sv)) if isinstance(sv, str) else ("[%d blocks]" % len(sv) if isinstance(sv, list) else "none")
        if folded:
            sys_val = payload.get("system")
            extra = "\n\n".join(folded)
            if isinstance(sys_val, list):
                _strip_cache_control(sys_val)
                sys_val.append({"type": "text", "text": extra})
            elif isinstance(sys_val, str) and sys_val:
                payload["system"] = sys_val + "\n\n" + extra
            else:
                payload["system"] = extra
    if isinstance(payload.get("system"), list):
        _strip_cache_control(payload["system"])
    return payload, summary


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 + Connection: close => no keep-alive, no chunked framing to get
    # wrong. We stream the body to the socket and close. Simple and robust.
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        summary = None

        if method == "POST" and "/v1/messages" in self.path and body:
            try:
                payload = json.loads(body)
                payload, summary = normalize(payload)
                body = json.dumps(payload).encode("utf-8")
            except Exception as exc:  # noqa: BLE001 -- fail open, forward verbatim
                _log(f"normalize failed, forwarding verbatim: {exc!r}")

        fwd = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in ("content-length", "host", "connection",
                      "transfer-encoding", "accept-encoding", "keep-alive"):
                continue
            fwd[k] = v
        fwd["Content-Length"] = str(len(body))
        fwd["Accept-Encoding"] = "identity"
        fwd["Connection"] = "close"

        req = urllib.request.Request(UPSTREAM + self.path,
                                     data=body if body else None,
                                     headers=fwd, method=method)
        try:
            upstream = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            upstream = e
        except Exception as e:
            _log(f"upstream error: {e!r} summary={summary}")
            self._error(502, f"nothink_proxy upstream error: {e}")
            return

        status = getattr(upstream, "status", 200) or 200
        if summary is not None:
            _log(f"POST {self.path} -> {status} model={summary.get('model')} roles={summary['roles']} folded_system={summary['folded_system']} dropped={summary['dropped']} system={summary.get('system')} last2={summary.get('shapes')}")

        # Status line + headers (drop framing/encoding headers; HTTP/1.0 close
        # delimits the body, so no Content-Length needed for the stream).
        try:
            self.send_response(status)
            for k, v in upstream.headers.items():
                if k.lower() in ("content-length", "transfer-encoding",
                                 "connection", "content-encoding", "keep-alive"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return

        # Stream the body line-by-line. CRITICAL: Ollama keeps the SSE socket
        # open for keep-alive after emitting `message_stop`, so reading to EOF
        # blocks ~60s. We forward the terminal event, then close immediately.
        err_head = b""
        try:
            for line in upstream:
                self.wfile.write(line)
                self.wfile.flush()
                if status >= 400 and len(err_head) < 400:
                    err_head += line
                if b"message_stop" in line or b"[DONE]" in line:
                    break
        except (BrokenPipeError, ConnectionResetError, socket.error):
            pass
        finally:
            if status >= 400:
                _log(f"upstream {status} body: {err_head[:400]!r}")
            try:
                upstream.close()
            except Exception:
                pass

    def _error(self, code, msg):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": msg}}).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        self._proxy("POST")

    def do_GET(self):
        self._proxy("GET")


if __name__ == "__main__":
    print(f"nothink_proxy: :{LISTEN_PORT} -> {UPSTREAM} (thinking off + Claude-Code request normalization on /v1/messages)")
    ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler).serve_forever()
