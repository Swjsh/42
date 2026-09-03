"""Minimal headless Chrome-DevTools-Protocol client for the TradingView Desktop chart.

WHY THIS EXISTS (2026-08-06, J's second ask -- OP-33(e) missing instrument):
    The TradingView MCP's draw_shape / draw_list / draw_remove_one tools are only
    callable from a live Claude+MCP session. The T14 note in trendline_draw_state.py
    verified that and concluded the DRAW step "is necessarily an on-demand skill
    invocation, not a new pythonw daemon".

    That conclusion was true of the *MCP*, not of the *chart*. The MCP is itself just
    a Node process that speaks CDP to TradingView Desktop on port 9222 and calls
    `window.TradingViewApi._activeChartWidgetWV.value()`. Nothing about that path is
    Node-specific. This module speaks the same CDP to the same port from Python, so a
    headless pythonw scheduled task can drive the chart with no LLM and no MCP -- $0.

    Mechanism parity is deliberate: the JS entry points here (createShape,
    getAllShapes, getShapeById, removeEntity) are the exact ones the MCP uses in
    SwjshAlgoKnife/mcp-servers/tradingview-mcp/src/core/drawing.js, so this client and
    the MCP cannot drift into drawing two different kinds of object.

SCOPE: read + draw only. This module never removes anything it was not handed an
explicit entity_id for, and it deliberately does NOT expose removeAllShapes() --
that TV primitive takes no arguments and would wipe J's hand-drawn work.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222

# Same path the TradingView MCP uses (src/connection.js KNOWN_PATHS.chartApi).
CHART_API = "window.TradingViewApi._activeChartWidgetWV.value()"

_WS_TIMEOUT_SEC = 15


class TvCdpError(RuntimeError):
    """TradingView CDP is unreachable or the chart API is not ready."""


def _http_json(path: str, timeout: float = 5.0) -> Any:
    url = f"http://{CDP_HOST}:{CDP_PORT}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (localhost only)
        return json.loads(resp.read().decode("utf-8", "replace"))


def find_chart_target(timeout: float = 5.0) -> dict:
    """Return the CDP target dict for the TradingView chart page.

    Raises TvCdpError when TradingView Desktop is not running / CDP is not exposed,
    which callers are expected to treat as a soft skip, not a crash.
    """
    try:
        targets = _http_json("/json/list", timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise TvCdpError(f"CDP not reachable on {CDP_HOST}:{CDP_PORT} ({exc}) -- is TradingView Desktop running?") from exc
    except json.JSONDecodeError as exc:
        raise TvCdpError(f"CDP /json/list returned non-JSON: {exc}") from exc

    for t in targets or []:
        if t.get("type") == "page" and "tradingview.com/chart" in (t.get("url") or ""):
            if t.get("webSocketDebuggerUrl"):
                return t
    raise TvCdpError(
        "No TradingView chart page found on CDP. "
        f"Saw {len(targets or [])} target(s); expected one with url containing 'tradingview.com/chart'."
    )


class TvChart:
    """A single CDP websocket session against the TradingView chart page.

    Usage:
        with TvChart() as chart:
            chart.list_shapes()
    """

    def __init__(self, ws_url: str | None = None) -> None:
        if ws_url is None:
            ws_url = find_chart_target()["webSocketDebuggerUrl"]
        self._ws_url = ws_url
        self._ws = None
        self._msg_id = 0

    def __enter__(self) -> "TvChart":
        try:
            from websockets.sync.client import connect
        except ImportError as exc:  # pragma: no cover - env guard
            raise TvCdpError(
                "python package 'websockets' is required for CDP. Use backtest/.venv "
                "(scheduled tasks already run on its pythonw)."
            ) from exc
        # TradingView ships large chart payloads; the default 1MB frame cap is too small.
        self._ws = connect(self._ws_url, max_size=32 * 1024 * 1024, open_timeout=_WS_TIMEOUT_SEC)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    # ---- protocol -------------------------------------------------------

    def evaluate(self, expression: str) -> Any:
        """Run a JS expression in the chart page and return its value.

        Raises TvCdpError on a JS exception so a broken selector can never be
        mistaken for a legitimately empty result (C7: silent success is failure).
        """
        if self._ws is None:
            raise TvCdpError("TvChart used outside its context manager")
        self._msg_id += 1
        msg_id = self._msg_id
        self._ws.send(
            json.dumps(
                {
                    "id": msg_id,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                }
            )
        )
        # CDP interleaves unsolicited events with command replies; skip to our id.
        while True:
            raw = self._ws.recv(timeout=_WS_TIMEOUT_SEC)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise TvCdpError(f"CDP error: {msg['error']}")
            result = msg.get("result", {})
            if result.get("exceptionDetails"):
                detail = result["exceptionDetails"]
                text = detail.get("exception", {}).get("description") or detail.get("text")
                raise TvCdpError(f"JS exception: {text}")
            return result.get("result", {}).get("value")

    # ---- chart API ------------------------------------------------------

    def require_chart_api(self) -> None:
        ok = self.evaluate(f"typeof ({CHART_API}) !== 'undefined' && ({CHART_API}) !== null")
        if not ok:
            raise TvCdpError(f"Chart API not available at {CHART_API} (chart still loading?)")

    def symbol(self) -> str | None:
        return self.evaluate(f"(function(){{ try {{ return {CHART_API}.symbol(); }} catch(e) {{ return null; }} }})()")

    def last_price(self) -> float | None:
        """Last traded price of the chart's main series, or None if unavailable."""
        js = f"""
        (function() {{
          try {{
            var bars = {CHART_API}._chartWidget.model().mainSeries().bars();
            var last = bars.last();
            if (!last) return null;
            var v = last.value;
            return v && v.length > 4 ? v[4] : null;
          }} catch (e) {{ return null; }}
        }})()
        """
        val = self.evaluate(js)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def list_shapes(self) -> list[dict]:
        """[{id, name}, ...] for every shape on the chart (ours AND J's)."""
        js = f"""
        (function() {{
          var api = {CHART_API};
          return api.getAllShapes().map(function(s) {{ return {{ id: s.id, name: s.name }}; }});
        }})()
        """
        return self.evaluate(js) or []

    def shape_text(self, entity_id: str) -> str | None:
        """Read a shape's text override, used to recognise our own tagged drawings."""
        js = f"""
        (function() {{
          try {{
            var api = {CHART_API};
            var s = api.getShapeById({json.dumps(entity_id)});
            if (!s) return null;
            var p = null;
            try {{ p = s.getProperties(); }} catch (e) {{ try {{ p = s.properties(); }} catch (e2) {{ return null; }} }}
            if (!p) return null;
            if (typeof p.text === 'string') return p.text;
            if (p.text && typeof p.text.value === 'function') return p.text.value();
            return null;
          }} catch (e) {{ return null; }}
        }})()
        """
        return self.evaluate(js)

    def create_horizontal_line(self, price: float, text: str, overrides: dict | None = None) -> str | None:
        """Draw one horizontal line; returns the new entity_id (or None if TV gave none).

        `time` is required by createShape even for a horizontal line; TV ignores it
        for horizontal_line placement but rejects a non-finite value.
        """
        price_f = float(price)
        if price_f != price_f or price_f in (float("inf"), float("-inf")):
            raise ValueError(f"non-finite price: {price!r}")
        ovr = json.dumps(overrides or {})
        js_before = f"{CHART_API}.getAllShapes().map(function(s) {{ return s.id; }})"
        before = set(self.evaluate(js_before) or [])
        self.evaluate(
            f"""
            {CHART_API}.createShape(
              {{ time: 0, price: {price_f!r} }},
              {{ shape: "horizontal_line", overrides: {ovr}, text: {json.dumps(text)} }}
            )
            """
        )
        after = self.evaluate(js_before) or []
        new_ids = [i for i in after if i not in before]
        return new_ids[0] if new_ids else None

    def create_trend_line(self, point: dict, point2: dict, text: str, overrides: dict | None = None) -> str | None:
        """Draw one two-point `trend_line` shape; returns the new entity_id (or None).

        `point`/`point2` are `{"time": unix, "price": float}` -- SAME shape and same
        canonical-unix-direct convention documented in
        `automation/scripts/tv_ops/draw_trendline.md` for `mcp__tradingview__draw_shape`
        (no manual TZ offset needed; TV's own storage-layer -14400 shift is internal to
        the chart widget regardless of caller). Added 2026-09-03 (TRENDLINE-DRAW-HEADLESS).

        Uses `createMultipointShape(points, options)`, NOT `createShape` -- verified
        live this session: `createShape({point}, {..., point2: {...}})` throws
        "Wrong points count for trend_line. Required 2" (`_createMultipointShape`'s own
        validation). `create_horizontal_line` above is correctly single-point (`createShape`
        with `point` only); a `trend_line` is a 2-point shape and needs the sibling API,
        which (also verified live) returns the new entity_id directly -- no before/after
        id-diffing needed here, unlike `create_horizontal_line`.
        """
        for pt in (point, point2):
            v = float(pt["price"])
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError(f"non-finite price in point: {pt!r}")
        p1 = json.dumps({"time": int(point["time"]), "price": float(point["price"])})
        p2 = json.dumps({"time": int(point2["time"]), "price": float(point2["price"])})
        ovr = json.dumps(overrides or {})
        eid = self.evaluate(
            f"""
            {CHART_API}.createMultipointShape(
              [{p1}, {p2}],
              {{ shape: "trend_line", overrides: {ovr}, text: {json.dumps(text)} }}
            )
            """
        )
        return eid or None

    def remove_entity(self, entity_id: str) -> bool:
        """Remove ONE shape by id. Returns True only if it is verifiably gone."""
        js = f"""
        (function() {{
          var api = {CHART_API};
          var eid = {json.dumps(entity_id)};
          var all = api.getAllShapes();
          var found = false;
          for (var i = 0; i < all.length; i++) {{ if (all[i].id === eid) {{ found = true; break; }} }}
          if (!found) return {{ removed: false, missing: true }};
          api.removeEntity(eid);
          var after = api.getAllShapes();
          for (var j = 0; j < after.length; j++) {{ if (after[j].id === eid) return {{ removed: false, missing: false }}; }}
          return {{ removed: true, missing: false }};
        }})()
        """
        res = self.evaluate(js) or {}
        return bool(res.get("removed"))
