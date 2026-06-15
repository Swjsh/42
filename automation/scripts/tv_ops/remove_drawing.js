/* remove_drawing.js — replacement for the broken draw_remove_one MCP tool.
 *
 * PLACEHOLDER: __ENTITY_ID__  → replace with the entity_id (string) before passing
 * to ui_evaluate. Example:
 *   const expr = readFile("remove_drawing.js").replace("__ENTITY_ID__", '"5EWHJK"')
 *
 * Returns: { success, removed_id, removed_type } on success
 *          { success: false, error: "not_found" | <other> } on failure
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
    const ctorName = src?.constructor?.name || "unknown";

    m.removeSource(src);
    return { success: true, removed_id: id, removed_type: ctorName, removed_title: title };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})()
