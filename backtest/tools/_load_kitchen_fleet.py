"""Load a FLEET of Kitchen cook tasks for the sniper-entry R&D thread (J directive
2026-05-31: 'why only one kitchen cook? test the system until last week is profitable
every day'). Idempotent: each task is marker-guarded; re-run won't duplicate. Matches
the cook-queue.jsonl 'create' event schema by mirroring the most recent create event."""
from __future__ import annotations
import json
import uuid
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"
STAMP = "2026-05-31T12:30:00+00:00"

# Each: (unique marker substring, priority, full task text)
TASKS = [
    ("SNIPER pullback-param sweep", "high",
     "SNIPER pullback-param sweep: in backtest/tools/entry_experiment.py the V_pullback entry "
     "(wait up to 6 bars for price to retest the level +/-0.20, enter on bounce) + chart-stop "
     "made the missed week 4/4 green (+247.9/contract ITM2) and stayed +97.4/c on the J-anchor "
     "window. Sweep the pullback knobs: wait-window (3/4/6/8/10 bars), retest-proximity "
     "(0.10/0.20/0.30/0.40), and bounce-confirmation (enter on touch vs enter on next in-dir "
     "bar). Real OPRA fills, missed week + anchor window. Report per-contract edge_capture x "
     "sharpe per OP-16; find the knob set that maximizes days-green on BOTH windows."),

    ("SNIPER chart-stop buffer sweep", "high",
     "SNIPER chart-stop buffer sweep: chart-stop (level +/- buffer) beat premium-stop on every "
     "row of the missed-week + anchor experiment. Sweep LEVEL_STOP_BUFFER (0.20/0.35/0.50/0.75/"
     "1.00 dollars) for BULLISH_RECLAIM calls AND BEARISH_REJECTION puts, real OPRA fills, "
     "missed week + anchor window. Find the buffer that survives the retest wick without giving "
     "back too much. Compare vs current -8pct/-15pct premium stop. Per-contract per OP-16."),

    ("SNIPER OOS validation Jan-Apr", "high",
     "SNIPER OOS validation: the V_pullback+chart-stop combo is validated on the missed week + "
     "anchor window (small N). Run it OUT-OF-SAMPLE on every available trading day in the "
     "backtest data (use backtest/run.py windows or simulate_day across 2026-01..2026-04 where "
     "option fills are cached; where not cached, note coverage). Measure: does V_pullback+chart-"
     "stop beat baseline premium-stop per-contract across the full OOS set? Report days-green "
     "fraction + the MISSED-MOVE COST (signals V_pullback skipped that baseline would have won)."),

    ("SNIPER missed-move cost analysis", "high",
     "SNIPER missed-move cost: V_pullback takes fewer signals than baseline (6 vs 8 on missed "
     "week) because it skips entries with no clean pullback. Quantify the 'too late / missed "
     "move' risk J flagged: for every baseline signal where V_pullback did NOT fire, what would "
     "baseline have made/lost? Net out: is the chop avoided worth more than the moves missed? "
     "Real OPRA fills, missed week + anchor window + any OOS days available."),

    ("SNIPER bearish-side pullback", "medium",
     "SNIPER bearish-side test: V_pullback on the anchor window (mostly BEARISH_REJECTION puts) "
     "already scored 4/6 green +97.4/c. Stress it: run V_pullback + chart-stop specifically on "
     "the J-anchor PUT trades (4/29 710P, 5/01 721P, 5/04 721P winners) and confirm it still "
     "captures them (must NOT drop 5/04 +804). Also test on the 5/05-5/07 J losers — does "
     "pullback-entry turn them less-bad or skip them? Per-contract per OP-16."),

    ("SNIPER momentum-gate combo", "medium",
     "SNIPER momentum-gate combo: V_mom_and_prox (trigger bar vol>=1.3x + body>=0.5 in-dir AND "
     "entry within 0.35 of fast EMA) was the most selective entry. Test V_pullback COMBINED with "
     "the momentum/proximity gate (pullback bounce that is ALSO a high-conviction bar near the "
     "ribbon). Does combining them raise win-rate without dropping too many signals? Real OPRA "
     "fills missed week + anchor. Per-contract per OP-16."),

    ("SNIPER ribbon-ride exit hold", "medium",
     "SNIPER exit study: the engine 'rides the EMA ribbon' but TP1+runner may exit too early on "
     "trend days (05-28 was the cleanest trend day yet baseline LOST). Test holding the runner "
     "until ribbon-flip-back ONLY (no premium TP1) vs current TP1 0.50 + runner, paired with "
     "V_pullback entry + chart-stop. Does letting the ribbon ride longer capture more of the "
     "05-28-type move? Real OPRA fills. Per-contract edge_capture x sharpe per OP-16."),
]


def load_lines():
    return CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []


def find_template(lines):
    for ln in reversed(lines):
        try:
            j = json.loads(ln)
        except Exception:
            continue
        if j.get("event") == "create" or ("task" in j and "task_id" in j):
            return j
    return None


def build_event(template, task, priority):
    tid = str(uuid.uuid4())
    if template:
        evt = dict(template)
        for k in list(evt.keys()):
            kl = k.lower()
            if kl == "event": evt[k] = "create"
            elif kl in ("task_id", "id", "taskid"): evt[k] = tid
            elif kl in ("task", "description", "desc", "prompt"): evt[k] = task
            elif kl in ("priority", "pri"): evt[k] = priority
            elif kl in ("source", "src", "origin"): evt[k] = "claude"
            elif kl in ("status", "state"): evt[k] = "pending"
            elif "time" in kl or "_at" in kl or kl in ("ts", "created", "timestamp"): evt[k] = STAMP
            elif kl in ("attempts", "retries", "tier"): evt[k] = 0
            elif kl in ("claimed_by", "model", "output_path", "error", "result"): evt[k] = None
            elif kl == "cost_usd": evt[k] = 0
        for kk, vv in [("event", "create"), ("task_id", tid), ("task", task),
                       ("priority", priority), ("source", "claude"), ("status", "pending")]:
            evt.setdefault(kk, vv)
    else:
        evt = {"event": "create", "task_id": tid, "task": task, "priority": priority,
               "source": "claude", "status": "pending", "created_at": STAMP, "attempts": 0}
    return evt


def main():
    lines = load_lines()
    template = find_template(lines)
    existing = "\n".join(lines)
    added, skipped = 0, 0
    with CQ.open("a", encoding="utf-8") as fh:
        for marker, pri, task in TASKS:
            if marker in existing:
                print(f"SKIP (queued): {marker}")
                skipped += 1
                continue
            evt = build_event(template, task, pri)
            fh.write(json.dumps(evt) + "\n")
            print(f"ENQUEUED [{pri}] {marker}  id={evt['task_id'][:8]}")
            added += 1
    # also confirm the pending depth
    lines2 = load_lines()
    pend = 0
    seen = {}
    for ln in lines2:
        try:
            j = json.loads(ln)
        except Exception:
            continue
        tid = j.get("task_id")
        ev = j.get("event")
        if tid:
            seen[tid] = ev
    pend = sum(1 for v in seen.values() if v == "create")
    print(f"\nADDED {added}, SKIPPED {skipped}. cook-queue create-events (rough pending upper bound): {pend}")


if __name__ == "__main__":
    main()
