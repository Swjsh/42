/* remove_by_title.js — bulk-remove all line-tool drawings whose title matches a substring.
 *
 * PLACEHOLDER: __TITLE_SUBSTR__  → replace with a JS string literal like '"trendline"'.
 *
 * Common titles: "horizontal line", "trendline", "horizontal ray", "vertical line",
 *                "rectangle", "channel", "fib retracement", "text".
 *
 * Returns: { success, removed_count, removed_ids: [...] }
 *
 * Use case: end-of-day cleanup — remove all "trendline" drawings without
 *           touching horizontal lines (which represent persistent levels).
 */
(() => {
  try {
    const w = window._exposed_chartWidgetCollection?.activeChartWidget?._value;
    if (!w) return { success: false, error: "no_active_chart_widget" };
    const m = (typeof w.model === "function") ? w.model() : w.model;
    if (!m || typeof m.dataSources !== "function") return { success: false, error: "no_chart_model" };

    const needle = String(__TITLE_SUBSTR__).toLowerCase();
    const sources = m.dataSources() || [];
    const toRemove = [];
    for (const src of sources) {
      try {
        let title = null;
        try { title = (typeof src.title === "function") ? src.title() : src.title; } catch (e) {}
        if (!title) continue;
        if (!String(title).toLowerCase().includes(needle)) continue;
        toRemove.push(src);
      } catch (e) {}
    }

    const removedIds = [];
    for (const src of toRemove) {
      try {
        const id = (typeof src.id === "function") ? src.id() : (src.id || null);
        m.removeSource(src);
        removedIds.push(id);
      } catch (e) {
        removedIds.push({ error: String(e) });
      }
    }
    return { success: true, removed_count: removedIds.length, removed_ids: removedIds };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})()
