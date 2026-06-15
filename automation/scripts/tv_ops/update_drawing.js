/* update_drawing.js — update properties of an existing drawing (color, width, style).
 *
 * PLACEHOLDERS:
 *   __ENTITY_ID__   → the id to modify (string literal: '"5EWHJK"')
 *   __PROPS_OBJ__   → JSON object literal with new property values, e.g.
 *                     '{"linecolor": "#22c55e", "linewidth": 3}'
 *
 * Returns: { success, id, applied_props } on success.
 *
 * NOTE: TradingView's property paths follow a "/" namespace convention
 *   (e.g., "linecolor" is at "linesStyle.linecolor" on some shape types).
 *   For trend_line and horizontal_line top-level keys work directly.
 */
(() => {
  try {
    const w = window._exposed_chartWidgetCollection?.activeChartWidget?._value;
    if (!w) return { success: false, error: "no_active_chart_widget" };
    const m = (typeof w.model === "function") ? w.model() : w.model;
    const id = __ENTITY_ID__;
    const src = m.dataSourceForId(id);
    if (!src) return { success: false, error: "not_found", id: id };

    const propsObj = __PROPS_OBJ__;
    const props = (typeof src.properties === "function") ? src.properties() : src.properties;
    if (!props) return { success: false, error: "no_props" };

    const applied = [];
    for (const [k, v] of Object.entries(propsObj || {})) {
      try {
        const child = props.childs?.()?.[k] || props.child?.(k);
        if (child && typeof child.setValue === "function") {
          child.setValue(v);
          applied.push({ key: k, applied: true, via: "child" });
        } else if (props._values && k in props._values) {
          props._values[k] = v;
          applied.push({ key: k, applied: true, via: "_values" });
        } else {
          applied.push({ key: k, applied: false, reason: "no_setter_path" });
        }
      } catch (e) {
        applied.push({ key: k, applied: false, error: String(e) });
      }
    }
    return { success: true, id: id, applied_props: applied };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})()
