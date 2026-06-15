# draw_trendline — usage notes

## Timestamps for `draw_shape` (CORRECTED 2026-05-08)

> **THE EARLIER VERSION OF THIS DOC HAD THE FORMULA INVERTED.** I claimed
> draw_shape shifted timestamps by −14400 and that you should ADD 14400 to
> compensate. That was wrong — I misinterpreted the read-back delta. With
> +14400 added, drawings landed 4 hours too late on the chart (in post-market
> areas). The correct rule is below.

## The correct rule

**Send canonical OHLCV unix timestamps directly to `draw_shape`. No offset.**

```python
# Want to anchor at "5/8 09:30 ET" (canonical unix from data_get_ohlcv)
canonical_ts = 1778247000   # this is what data_get_ohlcv returns for the 09:30 bar
draw_shape(point={"time": canonical_ts, "price": ...})  # NO addition, NO subtraction
```

## What's actually happening internally

TradingView stores drawing timestamps in a "naive-ET" representation: it takes
the local-clock time you intend (e.g., "5/8 09:30 ET") and stores it as if that
clock reading were UTC. That stored value is `canonical_unix - 14400` during EDT.

| Step | Value | Notes |
|---|---|---|
| OHLCV bar at 5/8 09:30 ET | `1778247000` | data_get_ohlcv returns canonical unix (real UTC) |
| You send to draw_shape | `1778247000` | Pass canonical directly |
| Chart stores internally | `1778232600` | = canonical − 14400 (naive ET as if UTC) |
| Chart renders the drawing | at 5/8 09:30 ET | Correct visual placement |

When you READ the drawing back via `list_drawings.js` / `get_drawing.js`, you get
the stored value (`canonical - 14400`). To compare it to OHLCV bar timestamps,
**add 14400** to get back to canonical real unix:

```python
real_unix = stored_t + 14400   # during EDT (-04:00)
real_unix = stored_t + 18000   # during EST (-05:00) — Nov–Mar
```

## Validation evidence (collected 2026-05-08 ~17:00 ET)

J's manually-drawn line `u6xABx` (placed visually at "5/7 11:00 ET, $736.11"):
- Stored: `t = 1778151600`
- Real unix for 5/7 11:00 ET: `1778166000`
- Delta: `1778151600 − 1778166000 = −14400` ✓ confirms the −14400 storage offset

My MCP-drawn line `efk6pj`, sent `point.time = 1778178600` (real unix for 5/7 14:30 ET):
- Stored: `t = 1778164200`
- `1778164200 + 14400 = 1778178600` ✓ confirms send-as-canonical works

Visual confirmation from the screenshot: line `efk6pj` renders at 5/7 14:30 ET → 5/8 14:55 ET, tagging the four documented swing points. **No timezone offset bug remained once the +14400 input compensation was removed.**

## Symbols other than trend_line

- `horizontal_line` — single point, time field is null/ignored. No TZ involved.
- `vertical_line` — has time. Use canonical directly (same rule as trend_line).
- `rectangle` — 2 points with time. Use canonical directly.
- `text` — has time. Use canonical directly.

## Reference: the working create→read→delete cycle

```
1. CREATE   mcp__tradingview__draw_shape(shape="trend_line",
              point={time: <canonical_ts>, price: <p1>},
              point2={time: <canonical_ts2>, price: <p2>})
            → returns { entity_id }

2. READ ALL ui_evaluate(automation/scripts/tv_ops/list_drawings.js)
            → returns drawings[] with stored timestamps (canonical − 14400)
              Add 14400 to each time before comparing with OHLCV bars.

3. READ ONE ui_evaluate(get_drawing.js with __ENTITY_ID__ replaced)

4. DELETE   ui_evaluate(remove_drawing.js with __ENTITY_ID__ replaced)
            → calls model.removeSource(model.dataSourceForId(id))
```
