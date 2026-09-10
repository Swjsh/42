/* read_chart_drawings.js — pass to mcp__tradingview__ui_evaluate.
 *
 * Reason this exists: mcp__tradingview__draw_list throws "getChartApi is not defined"
 * (broken since at least 2026-05-07; same root cause as draw_remove_one which we
 * already worked around in key-levels.json's chart_cleanup_log via ui_evaluate).
 *
 * The TradingView MSIX desktop build minifies class names (constructor.name === "Wt"
 * for horizontal lines, "v" for trendlines, etc.) so we filter on the human-readable
 * `title` field instead. Validated against the live chart 2026-05-08 16:10 ET — found
 * 10 horizontal lines and 1 trendline successfully.
 *
 * Returns:
 *   { success: true, count, drawings: [
 *     { id, title, point_count, points: [{ time, price }], text }
 *   ] }
 *   - title is the reliable type discriminator: "horizontal line", "trendline",
 *     "horizontal ray", "trend line", "channel", "fib retracement", etc.
 *   - point.time is unix seconds; point.price is float USD
 *   - horizontal line has 1 point with time=null and price=<level>
 *   - trendline has 2 points with time/price for both anchors
 *   - text (ADDED 2026-09-09, WS-D/D1): the shape's on-chart text override, or `null`
 *     when unreadable/absent. This is the ONLY signal that lets a downstream reader tell
 *     an engine-drawn line (text starts with a tag like "[GTL] " / "[G] ") apart from one
 *     of J's own hand-drawn lines (text does not start with any engine tag, often "").
 *     Read via the SAME accessor pattern proven live in tv_cdp.py::shape_text -- try
 *     `properties()` first (more likely on a model.dataSources() object than on the
 *     getShapeById() object tv_cdp.py reads), fall back to `getProperties()`, fail soft
 *     to null on any shape that doesn't expose either -- NEVER throws out of the loop.
 *
 * On failure returns { success: false, error: <string> }.
 *
 * Usage from a prompt:
 *   mcp__tradingview__ui_evaluate({ expression: <contents of this file> })
 *
 * The expression is a self-invoking arrow function so ui_evaluate gets a single
 * value back.
 */
(() => {
  try {
    const collection = window._exposed_chartWidgetCollection;
    if (!collection) return { success: false, error: "no_chart_widget_collection" };
    const wrapper = collection.activeChartWidget;
    const widget = wrapper?._value;
    if (!widget) return { success: false, error: "no_active_chart_widget" };

    const model = (typeof widget.model === "function") ? widget.model() : widget.model;
    if (!model || typeof model.dataSources !== "function") {
      return { success: false, error: "no_chart_model" };
    }

    const sources = model.dataSources() || [];

    // Filter by `title` substring — robust against minified constructor names.
    // Anything that has at least one (time, price) point AND a title containing
    // a known line-tool keyword is captured.
    const isLineToolTitle = (t) => {
      if (!t) return false;
      const s = String(t).toLowerCase();
      return /line|ray|trend|channel|fib|arrow|pitchfork|gann/.test(s);
    };

    const drawings = [];
    for (const src of sources) {
      try {
        let title = null;
        try { title = (typeof src.title === "function") ? src.title() : src.title; } catch (e) {}
        if (!isLineToolTitle(title)) continue;

        let pts = [];
        if (typeof src.points === "function") {
          try { pts = src.points() || []; } catch (e) {}
        } else if (Array.isArray(src.m_points)) {
          pts = src.m_points;
        }
        if (!pts.length) continue;

        const points = pts.map((p) => ({
          time: p?.time ?? p?.timestamp ?? null,
          price: p?.price ?? p?.value ?? null,
        }));

        let id = null;
        try { id = (typeof src.id === "function") ? src.id() : (src.id || null); } catch (e) {}

        // text override -- see header comment. Try both property-accessor spellings,
        // in the order more likely to succeed on a dataSources() object; fail soft.
        let text = null;
        try {
          let p = null;
          try { p = (typeof src.properties === "function") ? src.properties() : null; } catch (e) {}
          if (!p) {
            try { p = (typeof src.getProperties === "function") ? src.getProperties() : null; } catch (e2) {}
          }
          if (p) {
            if (typeof p.text === "string") text = p.text;
            else if (p.text && typeof p.text.value === "function") {
              try { text = p.text.value(); } catch (e3) {}
            }
          }
        } catch (eOuter) {}

        drawings.push({
          id: id,
          title: title,
          point_count: points.length,
          points: points,
          text: text,
        });
      } catch (innerErr) {
        drawings.push({ error: String(innerErr) });
      }
    }

    return { success: true, count: drawings.length, drawings: drawings };
  } catch (e) {
    return { success: false, error: String(e), stack: e?.stack || null };
  }
})()
