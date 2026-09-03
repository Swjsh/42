import json
import pathlib
import sys

BASE = pathlib.Path("C:/Users/jackw/Desktop/42")

# Kitchen status
ks_path = BASE / "automation/state/kitchen-status.json"
if ks_path.exists():
    ks = json.loads(ks_path.read_text())
    print("=== KITCHEN STATUS ===")
    print("daemon_alive:", ks.get("daemon_alive"))
    print("current_task_id:", ks.get("current_task_id"))
    print("pid:", ks.get("pid"))
    print("queue_depth:", ks.get("queue_depth"))
    print("last_updated:", ks.get("last_updated"))
else:
    print("kitchen-status.json not found")

print()

# Overnight grinder progress
prog_path = BASE / "backtest/autoresearch/_state/overnight_grinder/progress.json"
if prog_path.exists():
    prog = json.loads(prog_path.read_text())
    print("=== OVERNIGHT GRINDER PROGRESS ===")
    print("completed:", prog.get("completed"), "/", prog.get("total"))
    print("failed:", prog.get("failed"))
    running = prog.get("running", [])
    print("running_count:", len(running))
    print("start_time:", prog.get("start_time"))
    print("elapsed_min:", prog.get("elapsed_min", "?"))
    keepers = prog.get("keepers", [])
    print("keepers:", len(keepers))
    for k in keepers[:5]:
        print("  ", k)
else:
    print("No overnight grinder progress.json found")
    # Check for any progress files
    state_dir = BASE / "backtest/autoresearch/_state"
    if state_dir.exists():
        for p in state_dir.rglob("progress.json"):
            print("Found:", p)

print()

# Cook queue task status
print("=== GRINDER TASK STATUS ===")
cq_path = BASE / "automation/state/cook-queue.jsonl"
lines = cq_path.read_text().strip().split("\n")
task_ids = ["4678c8ce", "6d517160", "e8afcadc", "33ac1dc9"]
task_events = {t: [] for t in task_ids}
for line in lines:
    try:
        ev = json.loads(line)
        tid = ev.get("task_id", "")
        for t in task_ids:
            if tid.startswith(t):
                task_events[t].append(ev)
    except Exception:
        pass

labels = {
    "4678c8ce": "v14_enhanced (high)",
    "6d517160": "vwap (medium)",
    "e8afcadc": "regime_switcher (medium)",
    "33ac1dc9": "sniper_real_fills (medium)",
}
for t, evs in task_events.items():
    latest = evs[-1] if evs else None
    status = latest.get("event") if latest else "NOT FOUND"
    desc = (evs[0].get("task") or "")[:55] if evs else ""
    print(f"  {t} [{labels[t]}]: event={status}  desc={desc}")
