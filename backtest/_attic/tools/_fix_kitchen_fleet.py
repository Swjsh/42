"""SCRUB + REPLACE the sniper Kitchen fleet.

L77 violation #3 self-correction: the 7 SNIPER tasks loaded by _load_kitchen_fleet.py
were written BEFORE entry_experiment.py finished and embed a FABRICATED premise
('V_pullback made the week 4/4 green +247.9/contract'). The real result: nothing hit
4/4; best is 2/4; V_pullback is 2/4 (+22.1/c ATM-8%) but SKIPS 05-28 & 05-29 entirely;
chart-stop UNDERPERFORMED the premium stop. We archive the false-premise tasks (requeue
reason=archived per OP-31) and enqueue TRUE-premise replacements sourced from
analysis/backtests/_sniper_digest2.txt.

Idempotent: archive is keyed to the bad-task markers; replacement create events are
marker-guarded. Engine-benefit R&D queueing only. No doctrine/order writes."""
from __future__ import annotations
import json
import uuid
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42")
CQ = REPO / "automation" / "state" / "cook-queue.jsonl"
STAMP = "2026-05-31T13:00:00+00:00"

# Markers of the FALSE-premise tasks to archive (from _load_kitchen_fleet.py).
BAD_MARKERS = [
    "SNIPER pullback-param sweep",
    "SNIPER chart-stop buffer sweep",
    "SNIPER OOS validation Jan-Apr",
    "SNIPER missed-move cost analysis",
    "SNIPER bearish-side pullback",
    "SNIPER momentum-gate combo",
    "SNIPER ribbon-ride exit hold",
]

# TRUE-premise replacements. Verified facts (analysis/backtests/_sniper_digest2.txt,
# sniper-entry-experiment-2026-05-31.md):
#   - Missed week: NO combo made 4/4 green. Best = ATM stop-8% V0_baseline 2/4 +27.5/c (n=8).
#   - V_pullback (retest the level, enter the bounce): 2/4 +22.1/c ATM-8% (n=5) but fires only
#     5 of 8 signals and ZERO on 05-28 & 05-29 (skipped the two trend days = J's "too late" risk).
#   - chart-stop UNDERPERFORMED premium stop (V0 ATM chart-stop -8.1/c vs +27.5/c premium).
#   - Per-entry trace: most losers' MFE barely exceeded entry then reversed into the stop
#     (bars->MFE=2); the lone big winner 05-29 09:40 had bars->MFE=6 (a real run).
#   - Anchor cross-check: V_pullback 1/6 +22.3/c, V0 1/6 +21.2/c (pullback doesn't crater
#     anchors but doesn't dominate; 5/04 721P +804 must be preserved).
NEW_TASKS = [
    ("TRUE-SNIPER entry-timing fine sweep", "high",
     "TRUE-SNIPER entry-timing sweep (replaces an archived task that had a fabricated premise). "
     "VERIFIED baseline from analysis/backtests/_sniper_digest2.txt: on the missed week NO entry "
     "variant made all 4 days green; best was ATM stop-8% V0_baseline 2/4 +27.5/contract; "
     "V_pullback (retest level then enter bounce) was 2/4 +22.1/c but fired only 5 of 8 signals "
     "and took ZERO trades on 05-28 & 05-29 (the two trend days it should have ridden). GOAL: "
     "find the entry timing between 'too early (chopped on retest)' and 'too late (missed the "
     "move)'. Sweep pullback wait-window (2/3/4/6/8 bars) x retest-proximity "
     "(0.10/0.20/0.30/0.40) x bounce-confirmation (enter-on-touch vs enter-on-next-in-dir-bar), "
     "real OPRA fills, missed week. Objective: maximize days-green WITHOUT dropping below 6 of 8 "
     "signals taken. Report per-contract per OP-16. Harness: backtest/tools/entry_experiment.py."),

    ("TRUE-SNIPER 05-28 ideal-entry reverse-engineer", "high",
     "TRUE-SNIPER 05-28 deep dive (replaces archived fabricated-premise task). VERIFIED: 05-28 "
     "was the cleanest trend day of the missed week (SPY +4.39, close 754.64) yet the engine LOST "
     "on it (V0_baseline -10.5/c ATM; the 10:15 entry's MFE was only +0.05 over entry before it "
     "reversed into the stop). Walk 05-28 bar-by-bar (backtest/data/spy_5m_2026-05-19_2026-05-29."
     "csv + real OPRA fills): identify the bar where a sniper SHOULD have entered to ride the "
     "trend, what distinguished it (ribbon stack/spread, vol, distance to fast EMA, pullback "
     "depth), and propose a single concrete rule that would have fired there but NOT at the "
     "10:15 chop entry. Output the rule + the per-contract it would have captured."),

    ("TRUE-SNIPER chart-stop vs premium-stop honest re-test", "high",
     "TRUE-SNIPER stop re-test (replaces archived task; CORRECTS my own L76 hypothesis). "
     "VERIFIED SURPRISE from the experiment: chart-stop UNDERPERFORMED the premium stop on the "
     "missed week (V0_baseline ATM chart-stop -8.1/c vs premium-stop +27.5/c; V_pullback ATM "
     "chart-stop -62.1/c vs premium +22.1/c). So 'replace premium stop with chart stop' (my L76 "
     "DRAFT direction) is NOT supported by this data. Re-test rigorously: sweep level-stop buffer "
     "(0.20/0.35/0.50/0.75/1.00) for BULLISH_RECLAIM calls on the missed week + J-anchor window, "
     "real OPRA fills. QUESTION TO ANSWER: is there ANY buffer where chart-stop beats the premium "
     "stop, or is the premium stop fine and the ENTRY the whole problem? Per-contract per OP-16. "
     "Update strategy/candidates/2026-05-31-low-vix-bull-reclaim-premium-stop.md with the verdict."),

    ("TRUE-SNIPER pullback skip-cost vs OOS", "high",
     "TRUE-SNIPER pullback skip-cost (replaces archived fabricated-premise task). VERIFIED: "
     "V_pullback skipped 3 of 8 missed-week signals including BOTH trend days (05-28, 05-29) -- "
     "it avoids chop but risks missing moves (J's 'fine line'). Quantify across OOS: for every "
     "baseline signal where V_pullback did NOT fire, what did baseline make/lose? Net the chop "
     "avoided against the moves missed. Use whatever OOS trading days have cached OPRA fills "
     "(report coverage honestly; do NOT fabricate days). Verdict: is pullback-entry net-positive "
     "vs baseline once skip-cost is counted? Per-contract per OP-16."),

    ("TRUE-SNIPER momentum-gate loosening", "medium",
     "TRUE-SNIPER momentum-gate (replaces archived task). VERIFIED: V_mom_gate (trigger bar "
     "vol>=1.3x & body>=0.5 in-dir) and V_mom_and_prox (also within 0.35 of fast EMA) were too "
     "strict -- they fired 0-1 signals on the missed week (essentially no trades). Loosen and "
     "sweep: vol_mult (1.0/1.1/1.2/1.3) x body_min (0.35/0.45/0.55) x ema_prox (0.25/0.35/0.50/"
     "off). GOAL: a momentum/proximity gate that keeps >=6 of 8 signals while filtering the worst "
     "chop entries. Real OPRA fills, missed week + anchor window. Per-contract per OP-16."),

    ("TRUE-SNIPER ribbon-ride exit hold", "medium",
     "TRUE-SNIPER exit-hold (replaces archived task; premise re-verified). VERIFIED: on 05-28 "
     "(clean trend day) the engine LOST partly because it never rode the trend; on 05-29 the one "
     "winner (09:40) had bars->MFE=6 (a real run captured by TP1_THEN_RUNNER_RIBBON). Test "
     "whether holding the runner to ribbon-flip-back ONLY (drop the +30% premium TP1) captures "
     "more of trend-day moves, paired with the best entry variant from the timing sweep. Real "
     "OPRA fills, missed week + anchor. Must NOT reduce the 05-29 capture or the 5/04 anchor. "
     "Per-contract edge_capture x sharpe per OP-16."),

    ("TRUE-SNIPER preserve J-anchors gate", "medium",
     "TRUE-SNIPER anchor-preservation (replaces archived task). VERIFIED: on the J-anchor window "
     "V_pullback scored only 1/6 days green (+22.3/c, n=2) -- it SKIPS most anchor trades. The "
     "non-negotiable (OP-16): any entry/stop change that improves the missed week must still "
     "CAPTURE 5/04 721P (+804) and not turn the 4/29 + 5/01 anchors worse. For each candidate "
     "from the other SNIPER cooks, run it on the anchor window and report whether 5/04 is still "
     "captured. Any candidate that drops 5/04 is REJECTED regardless of missed-week gain. Real "
     "OPRA fills. This is the gate, not a strategy."),
]


def load_lines():
    return CQ.read_text(encoding="utf-8").splitlines() if CQ.exists() else []


def main():
    lines = load_lines()
    # Build tid -> task text for create events, and track latest event per tid.
    create_text = {}
    for ln in lines:
        try:
            j = json.loads(ln)
        except Exception:
            continue
        if j.get("event") == "create" and j.get("task_id"):
            create_text[j["task_id"]] = j.get("task", "")

    # Find tids to archive: create events whose task text contains a BAD_MARKER
    # AND the fabricated phrase (so we only nuke MY bad ones, not anything legit).
    to_archive = []
    for tid, txt in create_text.items():
        if any(m in txt for m in BAD_MARKERS) and ("4/4 green" in txt or "247.9" in txt
                                                    or "made the missed week 4/4" in txt):
            to_archive.append(tid)

    already_archived = set()
    for ln in lines:
        try:
            j = json.loads(ln)
        except Exception:
            continue
        if j.get("event") == "requeue" and j.get("reason") == "archived" and j.get("task_id"):
            already_archived.add(j["task_id"])

    existing = "\n".join(lines)
    with CQ.open("a", encoding="utf-8") as fh:
        # 1) archive bad tasks
        arch = 0
        for tid in to_archive:
            if tid in already_archived:
                print(f"SKIP archive (already) {tid[:8]}")
                continue
            fh.write(json.dumps({"event": "requeue", "task_id": tid,
                                 "reason": "archived", "ts": STAMP,
                                 "note": "false-premise (L77) — superseded by TRUE-SNIPER tasks"}) + "\n")
            print(f"ARCHIVED {tid[:8]}  ({create_text[tid][:55]}...)")
            arch += 1
        # 2) enqueue corrected tasks
        added = 0
        for marker, pri, task in NEW_TASKS:
            if marker in existing:
                print(f"SKIP add (queued) {marker}")
                continue
            tid = str(uuid.uuid4())
            fh.write(json.dumps({"event": "create", "task_id": tid, "task": task,
                                 "task_type": "cook", "priority": pri, "source": "claude",
                                 "ts": STAMP, "created_at": STAMP}) + "\n")
            print(f"ENQUEUED [{pri}] {marker}  id={tid[:8]}")
            added += 1

    print(f"\nDONE. archived={arch}, added={added}, to_archive_found={len(to_archive)}")


if __name__ == "__main__":
    main()
