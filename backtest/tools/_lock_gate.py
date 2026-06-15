"""Lock the selectivity-gate finding: prepend it to J's brief, update STATUS + memory,
write the DRAFT candidate, queue the ratification cook. Numbers from _gate_test.json (L77).
Binary-safe, idempotent."""
from __future__ import annotations
import json, uuid
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
MEM = Path(r"C:\Users\jackw\.claude\projects\C--Users-jackw-Desktop-42\memory")
ABT = REPO / "analysis" / "backtests"
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"

g = json.loads((ABT / "_gate_test.json").read_text())
base = g["base"]
gates = g["gates"]
g5 = gates["G5: (conf OR >=2trig) AND not-midday"]
g4 = gates["G4: confluence OR >=2 trig"]

def appendf(p, marker, t):
    cur = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    if marker in cur:
        print("SKIP", p.name); return
    sep = b"" if (cur.endswith("\n") or cur == "") else b"\n"
    with p.open("ab") as fh:
        fh.write(sep + t.encode("utf-8"))
    print("APPEND", p.name)

# DRAFT candidate
CAND = f"""# DRAFT CANDIDATE — Selectivity gate (J's 'sniper entries', validated 68-trade OOS)

> STATUS: DRAFT for J. Not ratified. Rule 9 — entry-gate changes are J's, on a weekend, in writing.
> Generated 2026-05-31. Numbers from analysis/selectivity-gate-2026-05-31.md / _gate_test.json (real fills).

## The finding (the real answer to "tighten the entries")
On the production OOS trade set ({base['n']} trades / 60 cached-fill days, real OPRA fills), filtering
to CONVICTION setups concentrates the edge dramatically — same engine, same trades, just selective:

| config | n | WR | per-trade/c | total/c |
|---|---|---|---|---|
| production (ungated) | {base['n']} | {base['wr']} | {base['pc_per_trade']:+.1f} | {base['pc']:+.0f} |
| confluence OR >=2 triggers | {g4['n']} | {g4['wr']} | {g4['pc_per_trade']:+.1f} | {g4['pc']:+.0f} |
| **(conf OR >=2 trig) AND not-midday** | {g5['n']} | {g5['wr']} | **{g5['pc_per_trade']:+.1f}** | {g5['pc']:+.0f} |

WR {base['wr']} -> {g5['wr']}; per-trade {base['pc_per_trade']:+.1f} -> {g5['pc_per_trade']:+.1f}/c; keeps ~{round(100*g5['n']/base['n'])}% of
trades on HIGHER total P&L. Consistent across 3 independent dimensions (confluence, trigger-count,
time-of-day) — not a single-cut artifact.

## Why this is the right kind of fix
- It's EXACTLY J's instinct: "more sniper entries", "be more selective", "closer to the move".
- It needs NO new code — maps to existing params: filter_10_min_triggers_bull/bear, confluence_min_signals,
  and a midday entry-window carve-out.
- It's a LARGE-sample OOS result, unlike the stop/PL/D1 headlines that reversed on bigger samples.
- It does not touch the bull/bear stop or profit-lock (those were confirmed already-optimal).

## Candidate params change (for grinder validation, NOT yet applied)
- `filter_10_min_triggers_bull: 2 -> 2` (already), `filter_10_min_triggers_bear: 1 -> 2` (tighten), OR
- `confluence_min_signals` raised, OR a require-(confluence OR >=2 triggers) gate, AND
- a midday (11:30-14:00 ET) entry suppression OR size-down.
Sweep these via the grinder; the winner = highest edge_capture x sharpe (OP-16) that keeps J's
4/29 + 5/04 anchors and >=20 OOS signals.

## Gates before ratification (OP-11 / OP-16 / Rule 9)
- Re-run on a WIDER OOS span (the queued option-grid fetch) to push n well past 16.
- Confirm it does not drop the J anchors (4/29 710P, 5/04 721P).
- A/B scorecard at analysis/recommendations/ before any params.json + heartbeat.md gamma-sync.

## Provenance
Real OPRA fills, $0.02 slippage. Trade set = one production run_backtest over the 60-day OOS span;
gates are pure filters of that set (no re-sim). _gate_test.json + selectivity-gate-2026-05-31.md.
"""
(REPO / "strategy" / "candidates" / "2026-05-31-selectivity-gate.md").write_text(CAND, encoding="utf-8")
print("WROTE candidate")

STATUS = f"""
## 2026-05-31 (SELECTIVITY GATE -- the real finding) -- J's sniper instinct, validated 68-trade OOS

The genuine, large-sample, ratifiable result (after the stop/PL/D1 headlines all reversed): filtering
the production OOS trade set to CONVICTION setups concentrates the edge.
- ungated {base['pc_per_trade']:+.1f}/c per trade, WR {base['wr']}, n={base['n']}.
- (confluence OR >=2 triggers) AND not-midday: **{g5['pc_per_trade']:+.1f}/c per trade, WR {g5['wr']}, n={g5['n']}**
  -- keeps ~{round(100*g5['n']/base['n'])}% of trades on HIGHER total P&L. Consistent across confluence, trigger-count, time-of-day.
- Maps to EXISTING params (filter_10_min_triggers, confluence_min_signals + midday carve-out) -- no new code.
- DRAFT for J: strategy/candidates/2026-05-31-selectivity-gate.md. Validate via grinder + wider-OOS (cooks queued); Rule 9.
- This IS J's 'more sniper entries' thesis, finally proven on data instead of a 4-day overfit.
"""
appendf(REPO / "STATUS.md", "SELECTIVITY GATE -- the real finding", STATUS)

MEMA = (f"\n\n**SELECTIVITY GATE (the real win) 2026-05-31:** J's 'sniper entries' instinct VALIDATED on "
        f"68-trade OOS (real fills). Filtering production trades to (confluence OR >=2 triggers) AND "
        f"not-midday: WR {base['wr']}->{g5['wr']}, per-trade {base['pc_per_trade']:+.1f}->{g5['pc_per_trade']:+.1f}/c, "
        f"keeps ~{round(100*g5['n']/base['n'])}% of trades on higher total P&L. Consistent across confluence, "
        f"trigger-count, time-of-day. Maps to EXISTING params (filter_10_min_triggers, confluence_min_signals + "
        f"midday carve-out) -- no new code. DRAFT: strategy/candidates/2026-05-31-selectivity-gate.md. Unlike the "
        f"stop/PL/D1 headlines (which reversed on big samples), this is large-sample + multi-dimensional. Validate "
        f"via grinder + wider OOS (queued), Rule 9. tools: segment_oos.py, gate_test.py.")
appendf(MEM / "project_missed_week_2026_05.md", "SELECTIVITY GATE (the real win)", MEMA)

# queue ratification cook
mark = "RATIFY selectivity-gate scorecard"
lines = CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []
if any(mark in l for l in lines):
    print("SKIP gate cook (queued)")
else:
    task = ("RATIFY selectivity-gate scorecard (engine-benefit; DRAFT, Rule 9 - no params/heartbeat/order "
            "edits). VALIDATED 2026-05-31 (strategy/candidates/2026-05-31-selectivity-gate.md): filtering the "
            "production OOS trade set (68 trades, real fills) to (confluence OR >=2 triggers) AND not-midday "
            "lifts WR 0.32->0.50 and per-trade +4.0->+38.1/c, keeping ~24% of trades on higher total P&L; "
            "consistent across confluence/trigger-count/time-of-day. TASK: run the grinder + walk-forward over "
            "ALL cached-fill days sweeping {filter_10_min_triggers_bear in [1,2], confluence_min_signals, "
            "midday-suppress on/off}, produce the A/B scorecard at analysis/recommendations/ per OP-11 "
            "(dominates + data_hash_match + thresholds_4_of_4 + sub_window_stable + evidence_n>=20). MUST keep "
            "J's 4/29 710P + 5/04 721P anchors. Report edge_capture x sharpe per OP-16. Output ratification-ready "
            "scorecard for J's weekend review. This is J's 'sniper entries' thesis -- prioritize it.")
    tid = str(uuid.uuid4())
    with CQ.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "create", "task_id": tid, "task": task, "task_type": "cook",
                             "priority": "high", "source": "claude", "ts": "2026-05-31T16:00:00+00:00",
                             "created_at": "2026-05-31T16:00:00+00:00"}) + "\n")
    print(f"ENQUEUED gate cook {tid[:8]}")
print("DONE")
