"""Archive ALL 7 original false-premise SNIPER tasks (the TRUE-SNIPER replacements
are already queued). My first archiver's guard was too narrow (only matched the
literal '4/4 green' phrase, present in just 1 of 7). This catches the rest by marker,
excluding the TRUE-SNIPER replacements and any already-archived. Idempotent."""
from __future__ import annotations
import json
from pathlib import Path

CQ = Path(r"C:\Users\jackw\Desktop\42\automation\state\cook-queue.jsonl")
STAMP = "2026-05-31T13:10:00+00:00"

ORIG_MARKERS = [
    "SNIPER pullback-param sweep",
    "SNIPER chart-stop buffer sweep",
    "SNIPER OOS validation Jan-Apr",
    "SNIPER missed-move cost analysis",
    "SNIPER bearish-side pullback",
    "SNIPER momentum-gate combo",
    "SNIPER ribbon-ride exit hold",
]

lines = CQ.read_text(encoding="utf-8").splitlines()
create_text, latest = {}, {}
for ln in lines:
    try:
        j = json.loads(ln)
    except Exception:
        continue
    tid = j.get("task_id")
    if not tid:
        continue
    if j.get("event") == "create":
        create_text[tid] = j.get("task", "")
    latest[tid] = j.get("event")

already = set()
for ln in lines:
    try:
        j = json.loads(ln)
    except Exception:
        continue
    if j.get("event") == "requeue" and j.get("reason") == "archived":
        already.add(j.get("task_id"))

targets = []
for tid, txt in create_text.items():
    if txt.startswith("TRUE-SNIPER"):
        continue  # never archive the corrected ones
    if any(txt.startswith(m) or (m in txt[:90]) for m in ORIG_MARKERS):
        if tid not in already and latest.get(tid) != "complete":
            targets.append(tid)

with CQ.open("a", encoding="utf-8") as fh:
    for tid in targets:
        fh.write(json.dumps({"event": "requeue", "task_id": tid, "reason": "archived",
                             "ts": STAMP,
                             "note": "false-premise (L77) — superseded by TRUE-SNIPER tasks"}) + "\n")
        print(f"ARCHIVED {tid[:8]}  {create_text[tid][:60]}...")

print(f"\narchived {len(targets)} (already had {len(already)})")

# Final pending snapshot of SNIPER-family tasks
print("\n== SNIPER-family create events + their latest status ==")
relines = CQ.read_text(encoding="utf-8").splitlines()
ct, lt = {}, {}
for ln in relines:
    try:
        j = json.loads(ln)
    except Exception:
        continue
    tid = j.get("task_id")
    if not tid:
        continue
    if j.get("event") == "create":
        ct[tid] = j.get("task", "")
    lt[tid] = j.get("event")
for tid, txt in ct.items():
    if "SNIPER" in txt[:80] or "low-VIX BULLISH_RECLAIM" in txt:
        ev = lt.get(tid)
        status = {"create": "PENDING", "claim": "in_progress", "complete": "completed",
                  "requeue": "ARCHIVED/requeued", "fail": "failed"}.get(ev, ev)
        print(f"  [{status:>16}] {txt[:62]}")
