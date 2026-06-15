# TradingView Chart Operations Library

> JavaScript payloads for `mcp__tradingview__ui_evaluate` that work around the
> broken `getChartApi`-based MCP tools (`draw_list`, `draw_remove_one`,
> `draw_get_properties`).

## Tool capability matrix

Tested against TradingView Desktop 3.1.0.7818 (MSIX, Electron 38) on 2026-05-08.

### Native MCP tools that WORK

| Tool | Verified | Use it for |
|---|---|---|
| `draw_shape` | ✅ | Creating horizontal_line, vertical_line, trend_line, rectangle, text |
| `draw_clear` | (not tested — destroys all drawings, don't probe) | Nuke all drawings |
| `chart_set_symbol` | ✅ | Symbol switching |
| `chart_set_timeframe` | ✅ | Timeframe (1, 5, 15, 60, D, etc.) |
| `chart_set_type` | ✅ | Bars, candles, heikin-ashi, line, area |
| `chart_get_state` | ✅ | Read symbol/timeframe/indicator list |
| `chart_get_visible_range` / `chart_set_visible_range` | ✅ | Zoom/scroll by unix range |
| `chart_scroll_to_date` | ✅ | Scroll to ISO date |
| `chart_manage_indicator` | ✅ | Add/remove indicators by full name |
| `data_get_ohlcv` | ✅ | Pull bars (always pass `summary=true` unless you need each bar) |
| `data_get_study_values` | ✅ | Read current values from any visible indicator |
| `data_get_pine_lines` / `_labels` / `_tables` / `_boxes` | ✅ | Read Pine-Script-drawn output |
| `quote_get` | ✅ | Real-time quote |
| `capture_screenshot` | ✅ | full / chart / strategy_tester |
| `ui_evaluate` | ✅ | Run arbitrary JS in the chart context (the swiss-army knife) |
| `tv_health_check` | ✅ | Verify CDP connection |

### Native MCP tools that are BROKEN (need ui_evaluate workaround)

| Tool | Error | Workaround |
|---|---|---|
| `draw_list` | `getChartApi is not defined` | `tv_ops/list_drawings.js` |
| `draw_get_properties` | same | `tv_ops/get_drawing.js` |
| `draw_remove_one` | same | `tv_ops/remove_drawing.js` |

The MCP server's drawing-management endpoints reference a `getChartApi` symbol
that isn't wired up in the desktop build. The same chart-widget API path
(`window._exposed_chartWidgetCollection.activeChartWidget._value.model()`)
works fine when invoked via `ui_evaluate` directly.

## Internal API path (chart-widget object surface)

```
window._exposed_chartWidgetCollection
  └─ activeChartWidget          ← WatchedValue wrapper (has _value)
       └─ _value                ← actual ChartWidget object
            └─ .model()         ← returns ChartModel (NOT m_model)
                 ├─ .dataSources()         → all sources
                 ├─ .dataSourceForId(id)   → find by entity_id
                 ├─ .removeSource(src)     → delete one
                 ├─ .removeSources(srcs[]) → delete many
                 ├─ .removeAllDrawingTools()
                 ├─ .removeAllStudies()
                 ├─ .createLineTool(...)   → programmatic create
                 └─ ... many more
```

A source object has:
- `src.constructor.name` — minified ("Wt" = horizontal_line, "v" = trend_line)
- `src.title()` — human-readable ("horizontal line", "trendline")
- `src.id()` — entity ID
- `src.points()` — array of `{time, price}` with time in unix seconds (or null for horizontal lines)
- `src.properties()` — property bag (`._values` has linecolor, linewidth, etc.)

## File index

- `list_drawings.js` — return all line-tool drawings (replacement for `draw_list`)
- `get_drawing.js` — get one drawing by ID (replacement for `draw_get_properties`)
- `remove_drawing.js` — remove one drawing by ID (replacement for `draw_remove_one`)
- `remove_by_title.js` — bulk-remove drawings whose title matches a substring
- `update_drawing_color.js` — change color/width of an existing drawing

## Usage from a prompt

```
1. Read file content (Read tool, automation/scripts/tv_ops/<file>.js)
2. If the file has {{placeholders}}, substitute them
3. Pass the resulting expression to mcp__tradingview__ui_evaluate
```

Most files have at most one `{{var}}` placeholder. See each file's header.
