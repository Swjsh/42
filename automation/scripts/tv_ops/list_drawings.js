/* list_drawings.js — replacement for the broken draw_list MCP tool.
 *
 * Returns: { success, count, drawings: [{ id, title, point_count, points }] }
 * Filters to line-tool drawings (anything with a "line/trend/ray/channel/fib" title).
 * Each point: { time: unix_seconds | null, price: number }.
 * Validated against TradingView Desktop 3.1.0.7818 on 2026-05-08.
 *
 * No placeholders. Pass directly to ui_evaluate.
 */
(() => {
  try {
    const w = window._exposed_chartWidgetCollection?.activeChartWidget?._value;
    if (!w) return { success: false, error: "no_active_chart_widget" };
    const m = (typeof w.model === "function") ? w.model() : w.model;
    if (!m || typeof m.dataSources !== "function") return { success: false, error: "no_chart_model" };
    const sources = m.dataSources() || [];

    const isLineTool = (t) => /line|ray|trend|channel|fib|arrow|pitchfork|gann/i.test(String(t || ""));
    const drawings = [];
    for (const src of sources) {
      try {
        let title = null;
        try { title = (typeof src.title === "function") ? src.title() : src.title; } catch (e) {}
        if (!isLineTool(title)) continue;

        let pts = [];
        if (typeof src.points === "function") {
          try { pts = src.points() || []; } catch (e) {}
        }
        if (!pts.length) continue;

        const points = pts.map((p) => ({
          time: p?.time ?? p?.timestamp ?? null,
          price: p?.price ?? p?.value ?? null,
        }));

        let id = null;
        try { id = (typeof src.id === "function") ? src.id() : (src.id || null); } catch (e) {}

        drawings.push({ id, title, point_count: points.length, points });
      } catch (innerErr) {
        drawings.push({ error: String(innerErr) });
      }
    }
    return { success: true, count: drawings.length, drawings };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})()
