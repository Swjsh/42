"""Lock the expanded-gate finding (307 trades, 345 OOS days) into STATUS, memory,
the DRAFT candidate, and the ratification cook queue. Numbers from _expanded_gate.json (L77)."""
from __future__ import annotations
import json, uuid
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")
ABT = REPO / "analysis" / "backtests"
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"

g = json.loads((ABT / "_expanded_gate.json").read_text())
base = g["base"]
gates = g["gates"]
oos = g["oos_days"]
g_no_mid_tl = gates["G_NO_midday_trendline"]
g_ge2_notmid = gates["G_ge2trig_AND_not_midday"]
g_not_mid = gates["G_not_midday"]
g_all = gates["ALL production (real fills only)"]

def appendf(p, marker, t):
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        print("SKIP", p.name); return
    sep = b"" if (cur.endswith("\n") or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + t.encode("utf-8"))
    print("APPEND", p.name)

STATUS = f"""
## 2026-05-31 (EXPANDED GATE — 307 trades, 345 OOS days) -- large-sample confirmation

The selectivity gate holds at scale. {g_all['n']} real-fills trades over {oos} OOS days:
- **Production ungated: {g_all['pc_per_trade']:+.1f}/trade, WR {g_all['wr']}, n={g_all['n']}.**
- G_ge2trig AND not-midday: **{g_ge2_notmid['pc_per_trade']:+.1f}/trade**, WR {g_ge2_notmid['wr']}, n={g_ge2_notmid['n']}, total {g_ge2_notmid['pc']:+.0f}/c.
- G_NO_midday_trendline (surgical — block only 1-trig trendline midday): **{g_no_mid_tl['pc_per_trade']:+.1f}/trade**, n={g_no_mid_tl['n']} (71% trades kept), HIGHEST total {g_no_mid_tl['pc']:+.0f}/c.
- not-midday only: {g_not_mid['pc_per_trade']:+.1f}/trade, n={g_not_mid['n']}.
- Midday autopsy confirmed: 24 of 32 midday losers = 1-trigger trendline -> premium stop. That one pattern accounts for −323/c of the bleed.
- CANDIDATE: strategy/candidates/2026-05-31-selectivity-gate.md (updated). Ratification cook queued. Rule 9.
"""
appendf(REPO / "STATUS.md", "EXPANDED GATE — 307 trades", STATUS)

MEMA = (f"\n\n**EXPANDED GATE 307-trade OOS 2026-05-31:** selectivity gate holds at scale ({oos} cached days). "
        f"G_NO_midday_trendline (block 1-trig trendline entries in midday) = {g_no_mid_tl['pc_per_trade']:+.1f}/trade "
        f"({g_no_mid_tl['n']} trades, highest total {g_no_mid_tl['pc']:+.0f}/c) vs ungated {g_all['pc_per_trade']:+.1f}/c. "
        f"Surgical: keeps 71% of trades. Midday autopsy: 24 of 32 midday losers = 1-trig trendline->premium-stop "
        f"(-323/c). G_ge2trig_AND_not_midday = {g_ge2_notmid['pc_per_trade']:+.1f}/trade (n={g_ge2_notmid['n']}, strongest per-trade). "
        f"DRAFT candidate updated. Ratification cook queued. Rule 9. Tools: run_expanded_gate.py, midday_autopsy.py.")
appendf(MEM / "project_missed_week_2026_05.md", "EXPANDED GATE 307-trade OOS", MEMA)

# update candidate doc with the larger-sample evidence
cand_path = REPO / "strategy" / "candidates" / "2026-05-31-selectivity-gate.md"
update = f"""

---

## LARGE-SAMPLE UPDATE 2026-05-31 (307 real-fills OOS trades, 345 days)

{g_all['n']} OOS trades, all-day: {g_all['pc_per_trade']:+.1f}/trade, WR {g_all['wr']}.

GATE RESULTS (n>=30 only):
| gate | n | WR | per-trade/c | total/c |
|---|---|---|---|---|
| >=2 triggers AND not-midday | {g_ge2_notmid['n']} | {g_ge2_notmid['wr']} | **{g_ge2_notmid['pc_per_trade']:+.1f}** | {g_ge2_notmid['pc']:+.0f} |
| conf AND not-midday | {gates['G_conf_AND_not_midday']['n']} | {gates['G_conf_AND_not_midday']['wr']} | **{gates['G_conf_AND_not_midday']['pc_per_trade']:+.1f}** | {gates['G_conf_AND_not_midday']['pc']:+.0f} |
| NO midday-trendline (surgical) | {g_no_mid_tl['n']} | {g_no_mid_tl['wr']} | {g_no_mid_tl['pc_per_trade']:+.1f} | **{g_no_mid_tl['pc']:+.0f} (highest)** |
| not-midday only | {g_not_mid['n']} | {g_not_mid['wr']} | {g_not_mid['pc_per_trade']:+.1f} | {g_not_mid['pc']:+.0f} |

AUTOPSY: 24 of 32 midday losers = 1-trigger trendline rejection -> premium stop. That single pattern = -323/c of the midday bleed.

SURGICAL RECOMMENDATION: block MIDDAY entries that have only a trendline_rejection trigger (i.e., require >=2 triggers or a level_rejection if midday). This preserves 71% of all trades while improving per-trade +3.8->{g_no_mid_tl['pc_per_trade']:+.1f}/c and achieving HIGHEST total P&L.

Param mapping: `filter_10_min_triggers_bear: 1` -> `filter_10_min_triggers_bear_midday: 2` (or add a midday trendline-only block in filters.py). Grinder sweep needed for exact param → gamma-sync once ratified.
"""
cur = cand_path.read_text(encoding="utf-8", errors="ignore") if cand_path.exists() else ""
if "LARGE-SAMPLE UPDATE 2026-05-31" not in cur:
    with cand_path.open("ab") as fh:
        fh.write(update.encode("utf-8"))
    print("UPDATED candidate")
else:
    print("SKIP candidate (already updated)")

# Queue ratification cook for the expanded finding
mark = "RATIFY expanded-selectivity-gate 307-trade"
lines = CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []
if not any(mark in l for l in lines):
    task = (f"RATIFY expanded-selectivity-gate 307-trade scorecard (engine-benefit; DRAFT, Rule 9 - no "
            f"params/heartbeat/order edits). VALIDATED 2026-05-31 (analysis/expanded-gate-2026-05-31.md): "
            f"on {g_all['n']} real-fills OOS trades/{oos} days, G_NO_midday_trendline (block 1-trigger trendline "
            f"entries in midday) = {g_no_mid_tl['pc_per_trade']:+.1f}/trade ({g_no_mid_tl['n']} trades, highest total "
            f"{g_no_mid_tl['pc']:+.0f}/c) vs ungated {g_all['pc_per_trade']:+.1f}/c. Midday autopsy: 24 of 32 midday "
            f"losers = 1-trig trendline->premium-stop (-323/c). TASK: sweep in the grinder: "
            f"{{filter_10_min_triggers_bear in [1,2], with_midday_exception for trendline-only, confluence_min_signals}}, "
            f"full walk-forward over all cached-fill days, A/B scorecard at analysis/recommendations/ per OP-11 "
            f"(dominates + data_hash_match + thresholds_4_of_4 + sub_window_stable + evidence_n>=20). Must keep J's "
            f"4/29 710P + 5/04 721P anchors. Compare G_NO_midday_trendline vs G_ge2trig_AND_not_midday to find "
            f"the least restrictive gate that captures the lift. Output ratification-ready scorecard for J.")
    tid = str(uuid.uuid4())
    with CQ.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "create", "task_id": tid, "task": task, "task_type": "cook",
                             "priority": "high", "source": "claude", "ts": "2026-05-31T16:30:00+00:00",
                             "created_at": "2026-05-31T16:30:00+00:00"}) + "\n")
    print(f"ENQUEUED expanded gate cook {tid[:8]}")
else:
    print("SKIP expanded gate cook (queued)")
print("DONE")
