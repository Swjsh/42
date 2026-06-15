"""Add ONE more cook: the minimum-stop-width search (J's insight operationalized).
The less stop room a config needs to stay green, the better the entry. Idempotent."""
import json, uuid
from pathlib import Path
CQ = Path(r"C:\Users\jackw\Desktop\42\automation\state\cook-queue.jsonl")
STAMP = "2026-05-31T13:40:00+00:00"
MARK = "TRUE-SNIPER min-stop-width search"
TASK = ("TRUE-SNIPER min-stop-width search (J insight 2026-05-31: 'the less room we need, the "
        "better the entry'). VERIFIED: the missed week goes 4/4 green ONLY with a -50% stop + "
        "trailing-PL OFF (analysis/missed-green-sweep.md); -35% gives 3/4 (05-28 red). For each "
        "entry variant in backtest/tools/entry_experiment.py (V0 baseline, V_pullback, plus the "
        "designer's D1 retest-reclaim once implemented), find the MINIMUM premium-stop width that "
        "keeps the missed week 4/4 green with trailing-PL OFF. The variant that needs the SMALLEST "
        "stop is the best sniper entry (it enters closest to the launch). Cross-check each on the "
        "J-anchor window: the winning entry+stop must still capture 5/04 721P and keep worst-put-"
        "loss/contract shallower than the -50% baseline's -58/c. Real OPRA fills. Per-contract "
        "edge_capture x sharpe per OP-16. Deliverable: a table of (entry variant -> min stop for "
        "4/4 green -> anchor 5/04 capture y/n -> worst-loss/c), ranked by smallest stop.")
lines = CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []
if any(MARK in l for l in lines):
    print("SKIP: already queued")
else:
    tid = str(uuid.uuid4())
    with CQ.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "create", "task_id": tid, "task": TASK,
                             "task_type": "cook", "priority": "high", "source": "claude",
                             "ts": STAMP, "created_at": STAMP}) + "\n")
    print(f"ENQUEUED [high] {MARK} id={tid[:8]}")
