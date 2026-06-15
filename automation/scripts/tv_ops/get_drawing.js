/* get_drawing.js — replacement for the broken draw_get_properties MCP tool.
 *
 * PLACEHOLDER: __ENTITY_ID__  → replace with the entity_id (string).
 *
 * Returns: { success, id, title, ctor, points, properties }
 * Properties includes ALL property values (linecolor, linewidth, linestyle,
 * extendLeft, extendRight, etc.) as a flat object.
 */
(() => {
  try {
    const w = window._exposed_chartWidgetCollection?.activeChartWidget?._value;
    if (!w) return { success: false, error: "no_active_chart_widget" };
    const m = (typeof w.model === "function") ? w.model() : w.model;
    if (!m || typeof m.dataSourceForId !== "function") return { success: false, error: "no_chart_model" };

    const id = __ENTITY_ID__;
    const src = m.dataSourceForId(id);
    if (!src) return { success: false, error: "not_found", id: id };

    let title = null;
    try { title = (typeof src.title === "function") ? src.title() : src.title; } catch (e) {}

    let pts = [];
    if (typeof src.points === "function") {
      try { pts = src.points() || []; } catch (e) {}
    }
    const points = pts.map((p) => ({
      time: p?.time ?? p?.timestamp ?? null,
      price: p?.price ?? p?.value ?? null,
    }));

    let propsRaw = null;
    try { propsRaw = (typeof src.properties === "function") ? src.properties() : src.properties; } catch (e) {}
    const propValues = propsRaw?._values || propsRaw || {};

    return {
      success: true,
      id: id,
      title: title,
      ctor: src?.constructor?.name || "unknown",
      point_count: points.length,
      points: points,
      properties: propValues,
    };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})()
