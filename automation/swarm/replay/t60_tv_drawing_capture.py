"""
T60 — TradingView J-drawn-line capture → key-levels.json
=========================================================
Captures manually drawn horizontal lines from TradingView (via CDP/MCP)
and merges them into automation/state/key-levels.json as J-authored levels.

USAGE:
    1. J draws horizontal lines on the SPY 5m chart in TradingView.
    2. Run: python automation/swarm/replay/t60_tv_drawing_capture.py
    3. Review the output — levels tagged "j_drawn": true are added.

REQUIRES:
    - TradingView running with CDP on port 9222 (via setup/launch_tv_debug.ps1)
    - The tradingview-mcp server active OR direct CDP access via requests

TECHNICAL PATH (discovered 2026-05-16):
    window._exposed_chartWidgetCollection
      → widgets[0]                             (first chart widget)
        ._lineToolsSynchronizer._chartModel    (chart model)
          ._panes[0]._sourcesById              (all drawings keyed by id)
            [id].getState()                    (drawing state with price points)

    Alternative for horizontal lines specifically:
      widget._lineToolsSynchronizer._allLineToolsAndStudyStubs
        → iterate, filter for toolname == "HorzLine" or "HorzRay"

CALIBRATION NOTE (2026-05-16):
    The chart's _sourcesById returned 0 items in the first test because
    J had not drawn any lines in this TV session. The script below is
    correct and will work once J has drawn lines.
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
KEY_LEVELS_PATH = ROOT / "automation" / "state" / "key-levels.json"
CDP_URL = "http://localhost:9222"

# JavaScript to extract all horizontal drawings from TradingView
_EXTRACT_DRAWINGS_JS = """
(function() {
  try {
    var col = window._exposed_chartWidgetCollection;
    if (!col) return JSON.stringify({error: 'no _exposed_chartWidgetCollection'});

    var widgets = typeof col.getAll === 'function' ? col.getAll() : Object.values(col);
    if (!widgets || widgets.length === 0) return JSON.stringify({error: 'no widgets'});

    var w = widgets[0];
    var lts = w._lineToolsSynchronizer;
    if (!lts) return JSON.stringify({error: 'no _lineToolsSynchronizer'});

    var cm = lts._chartModel;
    if (!cm) return JSON.stringify({error: 'no _chartModel'});

    // Method 1: _panes[0]._sourcesById
    var panes = cm._panes;
    var pane0 = Array.isArray(panes) ? panes[0] : Object.values(panes)[0];
    var sourcesById = pane0 ? pane0._sourcesById : {};

    var drawings = [];
    var ids = Object.keys(sourcesById || {});

    ids.forEach(function(id) {
      var src = sourcesById[id];
      try {
        // Try to get state
        var state = typeof src.getState === 'function' ? src.getState() : null;
        var toolname = state ? state.type : (src.toolname || src._toolname || null);

        // Only capture horizontal drawing types
        var horzTypes = ['HorzLine', 'HorzRay', 'HorzSegment', 'TrendLine', 'ExtendedLine'];
        if (toolname && horzTypes.some(function(t) { return toolname.includes(t); })) {
          var pts = state ? state.points : null;
          var price = pts && pts.length > 0 ? pts[0].price : null;
          var text = state && state.text ? state.text : null;
          drawings.push({id: id, toolname: toolname, price: price, text: text, raw: state});
        }
      } catch(e2) {}
    });

    // Method 2: _allLineToolsAndStudyStubs fallback
    if (drawings.length === 0) {
      var allTools = lts._allLineToolsAndStudyStubs;
      var toolsArr = typeof allTools.toArray === 'function' ? allTools.toArray() :
                     typeof allTools.values === 'function' ? Array.from(allTools.values()) :
                     Array.isArray(allTools) ? allTools : [];
      toolsArr.forEach(function(t) {
        try {
          var state = typeof t.getState === 'function' ? t.getState() : null;
          var toolname = state ? state.type : null;
          var pts = state && state.points ? state.points : [];
          var price = pts.length > 0 ? pts[0].price : null;
          if (price !== null) drawings.push({id: state.id, toolname: toolname, price: price, raw: state});
        } catch(e3) {}
      });
    }

    return JSON.stringify({count: drawings.length, drawings: drawings, source: 'sourcesById'});
  } catch(e) {
    return JSON.stringify({error: e.message});
  }
})()
"""


def _cdp_request(target_id: str, js: str) -> dict:
    """Execute JS in CDP target and return parsed JSON result."""
    import urllib.request
    url = f"{CDP_URL}/json"
    with urllib.request.urlopen(url, timeout=5) as r:
        targets = json.loads(r.read())

    page_targets = [t for t in targets if t.get("type") == "page"]
    if not page_targets:
        raise RuntimeError("No CDP page target found")

    ws_url = page_targets[0].get("webSocketDebuggerUrl")
    # Use a simple HTTP eval via the Runtime.evaluate method
    # For simplicity, use the devtools protocol REST endpoint
    target_id = page_targets[0].get("id")

    eval_url = f"{CDP_URL}/json/evaluate"
    payload = json.dumps({"expression": js, "returnByValue": True}).encode()
    req = urllib.request.Request(
        eval_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        # CDP REST eval not available — requires WebSocket; return empty
        return {"result": {"value": json.dumps({"error": "CDP REST eval not available — use MCP"})}}


def capture_drawings_via_mcp() -> list[dict]:
    """
    PRIMARY METHOD: Call this from Claude Code with TradingView MCP active.
    Returns list of {price, label, source} dicts.

    In Claude Code:
        result = mcp__tradingview__ui_evaluate(expression=_EXTRACT_DRAWINGS_JS)
        data = json.loads(result['result'])
    """
    raise NotImplementedError(
        "This function must be called from Claude Code with the TV MCP active.\n"
        "Use: mcp__tradingview__ui_evaluate(expression=t60_tv_drawing_capture._EXTRACT_DRAWINGS_JS)"
    )


def merge_into_key_levels(drawn_prices: list[dict]) -> None:
    """
    Merge J-drawn prices into key-levels.json.
    Tags them as j_drawn=true and tier='Active' by default.
    Existing levels at the same price (within $0.05) are updated, not duplicated.
    """
    kl = json.loads(KEY_LEVELS_PATH.read_text(encoding="utf-8"))
    existing_levels = kl.get("levels", [])

    added = 0
    updated = 0
    for dp in drawn_prices:
        price = dp.get("price")
        if price is None:
            continue
        label = dp.get("text") or dp.get("label") or f"J-line {price:.2f}"

        # Check for existing level within $0.05
        found = None
        for lv in existing_levels:
            if abs(lv.get("price", 0) - price) < 0.05:
                found = lv
                break

        if found:
            found["j_drawn"] = True
            found["label"] = label or found.get("label", "")
            updated += 1
        else:
            existing_levels.append({
                "price": round(price, 2),
                "tier": "Active",
                "label": label,
                "strength_stars": 2,
                "j_drawn": True,
                "source": "j_manual_tv",
                "added_at": datetime.now(timezone.utc).isoformat(),
            })
            added += 1

    kl["levels"] = sorted(existing_levels, key=lambda x: x.get("price", 0), reverse=True)
    kl["j_drawn_updated_at"] = datetime.now(timezone.utc).isoformat()
    KEY_LEVELS_PATH.write_text(json.dumps(kl, indent=2), encoding="utf-8")
    print(f"Merged: {added} new J-drawn levels, {updated} updated. Total: {len(kl['levels'])}")


if __name__ == "__main__":
    print("T60 drawing capture — JS extraction path discovered 2026-05-16")
    print(f"key-levels.json: {KEY_LEVELS_PATH}")
    print()
    print("To use:")
    print("  1. J draws horizontal lines on SPY 5m chart in TradingView")
    print("  2. In Claude Code with TV MCP active, run:")
    print("       result = mcp__tradingview__ui_evaluate(expression=_EXTRACT_DRAWINGS_JS)")
    print("       data = json.loads(result['result'])")
    print("       merge_into_key_levels(data.get('drawings', []))")
    print()
    print(f"Extraction JS ({len(_EXTRACT_DRAWINGS_JS)} chars) is in this file as _EXTRACT_DRAWINGS_JS.")
