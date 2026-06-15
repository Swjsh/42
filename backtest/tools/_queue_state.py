"""UTF-8-safe final snapshot of the SNIPER-family + TRUE-SNIPER + premium-stop cook
tasks: latest event per task_id. Writes to a flat file (avoids console cp1252 crash)."""
from __future__ import annotations
import json
from pathlib import Path

CQ = Path(r"C:\Users\jackw\Desktop\42\automation\state\cook-queue.jsonl")
OUT = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests\_queue_state.txt")

ct, latest = {}, {}
for ln in CQ.read_text(encoding="utf-8").splitlines():
    try:
        j = json.loads(ln)
    except Exception:
        continue
    tid = j.get("task_id")
    if not tid:
        continue
    if j.get("event") == "create":
        ct[tid] = j.get("task", "")
    latest[tid] = j.get("event")

STAT = {"create": "PENDING", "claim": "in_progress", "complete": "completed",
        "requeue": "ARCHIVED", "fail": "failed"}

lines = ["== TRUE-SNIPER tasks (my corrected fleet) =="]
for tid, txt in ct.items():
    if txt.startswith("TRUE-SNIPER"):
        lines.append(f"  [{STAT.get(latest.get(tid), latest.get(tid)):>11}] {tid[:8]} {txt[:70]}")
lines.append("")
lines.append("== original SNIPER-fleet tasks I queued then corrected (should be ARCHIVED) ==")
ORIG = ["SNIPER pullback-param", "SNIPER chart-stop buffer", "SNIPER OOS validation",
        "SNIPER missed-move", "SNIPER bearish-side", "SNIPER momentum-gate combo",
        "SNIPER ribbon-ride exit hold"]
for tid, txt in ct.items():
    if any(txt.startswith(m) for m in ORIG):
        lines.append(f"  [{STAT.get(latest.get(tid), latest.get(tid)):>11}] {tid[:8]} {txt[:60]}")
lines.append("")
lines.append("== premium-stop low-VIX cook (first one queued) ==")
for tid, txt in ct.items():
    if "low-VIX BULLISH_RECLAIM exit fix" in txt:
        lines.append(f"  [{STAT.get(latest.get(tid), latest.get(tid)):>11}] {tid[:8]} {txt[:60]}")
lines.append("")
# counts
pend = sum(1 for tid in ct if latest.get(tid) == "create")
lines.append(f"TOTAL create-events seen: {len(ct)} | currently PENDING (create is latest): {pend}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT)
