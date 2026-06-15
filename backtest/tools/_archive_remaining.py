"""Archive the remaining PENDING false-premise SNIPER tasks. Robust rule: any task
whose CREATE text starts with all-caps 'SNIPER ' but NOT 'TRUE-SNIPER', and whose
latest event is still 'create' (pending). This excludes legit 'Run sniper_..' grinders
(lowercase) and the corrected TRUE-SNIPER fleet. UTF-8-safe; writes report to file."""
from __future__ import annotations
import json
from pathlib import Path

CQ = Path(r"C:\Users\jackw\Desktop\42\automation\state\cook-queue.jsonl")
OUT = Path(r"C:\Users\jackw\Desktop\42\analysis\backtests\_archive_remaining.txt")
STAMP = "2026-05-31T13:20:00+00:00"

lines = CQ.read_text(encoding="utf-8").splitlines()
ct, latest = {}, {}
for ln in lines:
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

targets = [tid for tid, txt in ct.items()
           if txt.startswith("SNIPER ") and not txt.startswith("TRUE-SNIPER")
           and latest.get(tid) == "create"]

report = []
with CQ.open("a", encoding="utf-8") as fh:
    for tid in targets:
        fh.write(json.dumps({"event": "requeue", "task_id": tid, "reason": "archived",
                             "ts": STAMP,
                             "note": "false-premise (L77) - superseded by TRUE-SNIPER tasks"}) + "\n")
        report.append(f"ARCHIVED {tid[:8]} {ct[tid][:60]}")

report.append(f"\narchived {len(targets)} remaining")

# Re-snapshot SNIPER + TRUE-SNIPER status
ct2, lt2 = {}, {}
for ln in CQ.read_text(encoding="utf-8").splitlines():
    try:
        j = json.loads(ln)
    except Exception:
        continue
    tid = j.get("task_id")
    if not tid:
        continue
    if j.get("event") == "create":
        ct2[tid] = j.get("task", "")
    lt2[tid] = j.get("event")
S = {"create": "PENDING", "claim": "in_progress", "complete": "completed",
     "requeue": "ARCHIVED", "fail": "failed"}
report.append("\n== FINAL: my hand-written SNIPER fleet ==")
true_pend = orig_pend = 0
for tid, txt in ct2.items():
    if txt.startswith("TRUE-SNIPER"):
        st = S.get(lt2.get(tid), lt2.get(tid))
        report.append(f"  [{st:>11}] {txt[:62]}")
        if st == "PENDING":
            true_pend += 1
    elif txt.startswith("SNIPER "):
        st = S.get(lt2.get(tid), lt2.get(tid))
        report.append(f"  [{st:>11}] {txt[:62]}")
        if st == "PENDING":
            orig_pend += 1
report.append(f"\nTRUE-SNIPER pending: {true_pend} (want 7) | original-SNIPER pending: {orig_pend} (want 0)")
OUT.write_text("\n".join(report), encoding="utf-8")
print("wrote", OUT, "| archived", len(targets))
