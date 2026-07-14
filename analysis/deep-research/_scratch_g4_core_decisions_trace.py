"""Read-only trace of today's core-decisions.jsonl for the G4 exhibit. No writes to production state."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEC = REPO / "automation" / "state" / "core-decisions.jsonl"

rows = []
with DEC.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("ts_et", "").startswith("2026-07-14"):
            rows.append(d)

print(f"total today rows: {len(rows)}")

# non-HOLD verdicts / any setup fired
interesting = [d for d in rows if d.get("verdict") not in (None, "HOLD") or d.get("setup")]
print(f"non-HOLD or setup!=null rows: {len(interesting)}")
for d in interesting:
    print(d.get("ts_et"), d.get("account"), d.get("verdict"), d.get("side"), d.get("setup"), d.get("reason"))

# bear_score / bull_score extremes
print("\n--- bear_score/bull_score range across today ---")
bears = [d.get("bear_score") for d in rows if d.get("bear_score") is not None]
bulls = [d.get("bull_score") for d in rows if d.get("bull_score") is not None]
if bears:
    print("bear_score min/max:", min(bears), max(bears))
if bulls:
    print("bull_score min/max:", min(bulls), max(bulls))

# sample every ~15 rows for a timeline sanity check (safe account only to halve volume)
print("\n--- safe-account timeline sample ---")
safe_rows = [d for d in rows if d.get("account") == "safe"]
for i, d in enumerate(safe_rows):
    if i % 8 == 0:
        print(d.get("ts_et"), "spy=", d.get("spy"), "ribbon=", d.get("ribbon"), "vix=", d.get("vix"),
              "bear=", d.get("bear_score"), "bull=", d.get("bull_score"), "verdict=", d.get("verdict"),
              "reason=", (d.get("reason") or "")[:70])

# extra_signals fired=True anywhere today
print("\n--- extra_signals fired=True today ---")
for d in rows:
    for sig in d.get("extra_signals", []) or []:
        if sig.get("fired"):
            print(d.get("ts_et"), d.get("account"), sig)
