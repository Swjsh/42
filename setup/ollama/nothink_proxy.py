#!/usr/bin/env python3
"""nothink_proxy.py - force thinking OFF for local qwen behind Claude Code.

WHY (root-caused 2026-07-08): qwen3.6:35b is a thinking-native model. Ollama's
Anthropic endpoint (/v1/messages) honors `thinking:{type:disabled}` and answers
in ~4s, but Claude Code never sends that flag (MAX_THINKING_TOKENS=0 doesn't
translate). So the model "thinks" for 30-120s on every turn. This proxy sits in
front of Ollama, injects thinking:disabled into every /v1/messages request, and
streams the SSE response straight back. Fully isolated: no global config, no
claude-code-router, no effect on the desktop app.

Point Claude Code at it:  ANTHROPIC_BASE_URL=http://localhost:11435
Upstream Ollama stays on: http://localhost:11434

Run:  python setup/ollama/nothink_proxy.py         (defaults 11435 -> 11434)
"""
import json
import socket
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
UPSTREAM = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:11434"


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 + Connection: close => no keep-alive, no chunked framing to get
    # wrong. We stream the body to the socket and close. Simple and robust.
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        # The one mutation: force thinking off on the messages endpoint.
        if method == "POST" and "/v1/messages" in self.path and body:
            try:
                payload = json.loads(body)
                payload["thinking"] = {"type": "disabled"}
                body = json.dumps(payload).encode("utf-8")
            except (ValueError, TypeError):
                pass  # non-JSON -> forward verbatim (fail open)

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
            self._error(502, f"nothink_proxy upstream error: {e}")
            return

        # Status line + headers (drop framing/encoding headers; HTTP/1.0 close
        # delimits the body, so no Content-Length needed for the stream).
        try:
            self.send_response(getattr(upstream, "status", 200) or 200)
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
        try:
            for line in upstream:
                self.wfile.write(line)
                self.wfile.flush()
                if b"message_stop" in line or b"[DONE]" in line:
                    break
        except (BrokenPipeError, ConnectionResetError, socket.error):
            pass
        finally:
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
    print(f"nothink_proxy: :{LISTEN_PORT} -> {UPSTREAM} (forcing thinking:disabled on /v1/messages)")
    ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler).serve_forever()
