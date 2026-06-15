import json
import pathlib

BASE = pathlib.Path("C:/Users/jackw/Desktop/42")

# Show last 20 cook-queue events
lines = (BASE / "automation/state/cook-queue.jsonl").read_text().strip().split("\n")
print("Last 20 queue events:")
events = []
for line in lines[-25:]:
    try:
        events.append(json.loads(line))
    except Exception:
        pass
for ev in events[-20:]:
    tid = (ev.get("task_id") or "?")[:8]
    evtype = ev.get("event", "?")
    task = str(ev.get("task") or ev.get("reason") or "")[:45]
    print(f"  {tid}  {evtype:<18}  {task}")

print()

# Show pending tasks by priority
print("Pending tasks:")
task_latest = {}
for line in lines:
    try:
        ev = json.loads(line)
        tid = ev.get("task_id", "")
        task_latest[tid] = ev
    except Exception:
        pass

pending = [(v["task_id"][:8], v.get("priority","?"), str(v.get("task",""))[:50])
           for v in task_latest.values()
           if v.get("event") == "create"]
# Sort by priority
prio_order = {"high": 0, "medium": 1, "low": 2}
pending.sort(key=lambda x: prio_order.get(x[1], 9))
for p in pending[:15]:
    print(f"  {p[0]}  prio={p[1]:<8}  {p[2]}")
