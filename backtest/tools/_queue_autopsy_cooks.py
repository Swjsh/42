"""Queue targeted Kitchen cooks from the midday autopsy + expanded gate findings.
Each cook is precisely targeted and premise-verified from the JSON data. L77 compliant."""
from __future__ import annotations
import json, uuid
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"
ABT = REPO / "analysis" / "backtests"

g = json.loads((ABT / "_expanded_gate.json").read_text())
base = g["base"]
gates = g["gates"]
oos = g["oos_days"]

TASKS = [
    ("BEAR-midday trendline suppression OOS WF",
     "high",
     f"BEAR-midday trendline suppression OOS walk-forward (engine-benefit; Rule 9). "
     f"VALIDATED from analysis/expanded-gate-2026-05-31.md ({base['n']} trades, {oos} OOS days): "
     f"blocking 1-trigger trendline entries in the midday window (11:30-14:00 ET) improves "
     f"per-trade from {base['pc_per_trade']:+.1f} to {gates['G_NO_midday_trendline']['pc_per_trade']:+.1f}/c "
     f"while keeping 71% of all trades (highest total P&L {gates['G_NO_midday_trendline']['pc']:+.0f}/c). "
     f"Midday autopsy: 24 of 32 midday losers = trendline_rejection (single trigger) -> premium stop. "
     f"TASK: implement G_NO_midday_trendline filter in filters.py (skip if midday AND ntrig==1 AND "
     f"only_trigger==trendline_rejection), run full grinder sweep over all cached-fill days, compare "
     f"vs: (a) current production, (b) G_ge2trig_AND_not_midday, (c) completely blocking midday. "
     f"Report edge_capture x sharpe per OP-16 + must keep 4/29 + 5/04 anchors. Produce A/B scorecard "
     f"for J's ratification. This is the LEAST DISRUPTIVE ratifiable change found today."),

    ("VIX-context for midday trendline fails",
     "medium",
     f"VIX-context for midday trendline fails (R&D). Midday autopsy confirmed 24 losers all hitting "
     f"premium stop on trendline-only entries. QUESTION: are the midday trendline winners and losers "
     f"differentiated by VIX level or character (L73: VIX trending vs spike-revert)? Specifically: "
     f"are all 24 midday losers in LOW/MID VIX (< 18) flat-day sessions? If yes, a VIX-regime gate "
     f"on midday trendline entries (only fire if VIX > threshold OR VIX escalating) might be the "
     f"cleaner gate than time-of-day. Cross with the L73 VIX-character filter (5-day rolling). "
     f"Use analysis/backtests/_midday_autopsy.json for the trade list + watcher-observations.jsonl "
     f"for the VIX character on those dates. Report: does VIX/regime split the winners from losers "
     f"better than time-of-day does?"),

    ("BULL-call selectivity OOS study",
     "medium",
     f"BULL-call selectivity OOS study (BULLISH_RECLAIM is DRAFT, OP-16 scope lock). "
     f"Expanded gate data: BULL_only n={gates['G_BULL_only']['n']} trades, {gates['G_BULL_only']['pc_per_trade']:+.1f}/trade, "
     f"WR {gates['G_BULL_only']['wr']}. The DRAFT bull setup beats the production bear setup per-trade — "
     f"investigate whether the bull selectivity gate matters differently. Specifically: does requiring "
     f"confluence OR >=2 triggers on the bull side close the gap with bear performance even further? "
     f"And: are the bull losses also midday-trendline-dominated? Cross-reference G_BEAR_conf "
     f"({gates['G_BEAR_conf']['pc_per_trade']:+.1f}/trade n={gates['G_BEAR_conf']['n']}) vs G_BULL_only "
     f"to see if the bear confluence gate alone would match bull without the DRAFT promotion risk."),
]

lines = CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []
existing = "\n".join(lines)
added = 0
with CQ.open("a", encoding="utf-8") as fh:
    for mark, pri, task in TASKS:
        if mark in existing:
            print(f"SKIP: {mark}"); continue
        tid = str(uuid.uuid4())
        fh.write(json.dumps({"event": "create", "task_id": tid, "task": task, "task_type": "cook",
                             "priority": pri, "source": "claude", "ts": "2026-05-31T16:45:00+00:00",
                             "created_at": "2026-05-31T16:45:00+00:00"}) + "\n")
        print(f"ENQUEUED [{pri}] {mark} id={tid[:8]}")
        added += 1
print(f"DONE. added {added}")
