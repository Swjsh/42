"""Sync key-levels.json entity_ids after the 2026-06-24 pre-open chart cleanup
(wiped 48 stale horizontal lines, redrew 6 near-price levels). Far levels (>$12 from
spot) intentionally not drawn -> entity_id null. Clears stale chart_cleanup_log refs.
"""
import json, os

KL = r"C:\Users\jackw\Desktop\42\automation\state\key-levels.json"
NOW = "2026-06-24T08:53:00-04:00"

# price -> freshly-drawn entity_id (None = intentionally not drawn, far from spot)
DRAWN = {737.11: "WQ9hJp", 743.35: "U6uh98", 745.33: "Dh1hNs",
         747.25: "TctS5T", 734.97: "pBY4wg", 734.80: "lgkJSQ"}
FAR = {750.18, 750.00, 752.09}

with open(KL, "r", encoding="utf-8-sig") as f:
    kl = json.load(f)

drawn_summary = []
for lv in kl["levels"]:
    p = round(float(lv["price"]), 2)
    if p in DRAWN:
        lv["entity_id"] = DRAWN[p]
        lv["draw_needed"] = False
        drawn_summary.append(f"{p}->{DRAWN[p]}")
    elif p in FAR:
        lv["entity_id"] = None
        lv["draw_needed"] = False
        lv["notes"] = (lv.get("notes", "") + " | Not drawn 2026-06-24 (>$12 from spot ~736.97; awareness-only until price approaches).").strip(" |")

kl["chart_drawing_summary"] = {
    "drawn_count": len(drawn_summary),
    "drew_this_session": drawn_summary,
    "draw_needed_levels": [],
    "as_of": NOW,
    "note": "Pre-open chart cleanup 2026-06-24: wiped 48 stale horizontal lines (kept trendlines/rays/rectangle), redrew 6 near-price levels. Far levels (750.18/750.00/752.09) not drawn until price approaches.",
}
kl.setdefault("chart_cleanup_log", []).append({
    "ran_at": NOW,
    "method": "interactive_preopen_cleanup (remove_by_title 'horizontal line' + redraw near-price)",
    "before_count": 58,
    "removed_count": 48,
    "after_horizontal_lines": 6,
    "preserved": "7 trendlines, 1 ray, 1 horizontal ray, 1 rectangle (J manual structural)",
    "stale_entities_on_chart": [],
    "note": "Root fix: per-entity removal was unreliable so level lines accumulated to 58. Switched to wipe-by-title + redraw. Premarket Step 5 now does this every morning.",
})

tmp = KL + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(kl, f, indent=2)
with open(tmp, "r", encoding="utf-8") as f:
    json.load(f)
os.replace(tmp, KL)
print("entity_ids synced:", drawn_summary)
print("far (not drawn):", sorted(FAR))
