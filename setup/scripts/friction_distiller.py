"""friction_distiller.py — the organ Gamma lacked: accumulate friction across time, read it
as a PATTERN, and flag when it's been metabolized long enough to question the frame.

J 2026-06-29: the discovery-fleet reframe was FRICTION-gated, not intelligence-gated — it
required feeling the SAME bottleneck enough times that the constraint felt like a tax, not a
law. Gamma forgets every session. This distiller gives it the missing memory: it HARVESTS
recurring friction that already exists (it does not invent it) and COUNTS recurrence, so the
Step-Back ritual (Opus, weekly) can run J's Constraint Provenance Audit on what's actually
been grinding us for weeks. See markdown/meta/REFRAME-ENGINE.md.

PIPELINE 2 (meta-ideation). Pure-Python, $0, propose-only, never writes analysis/recommendations/.
A pattern is STEP-BACK-ELIGIBLE at occurrences>=5 across >=2 sources spanning >=14 days —
that threshold IS the encoded form of "metabolized for months."

EXCEPTION — OPERATOR friction (recurring_user_question): a REPEATED state-question from J is
a missing instrument, not a query (OP-33(e)). It escalates in 2 asks (FAST_ESCALATE), trips
action=BUILD_ELIMINATING_INSTRUMENT (build the standing surface, don't re-answer), and is fed
by automation/state/j-question-ledger.jsonl (captured by setup/hook-detect-correction.ps1).
This points the friction organ at the OPERATOR, closing the blind spot the metacog dissection
(2026-06-29) found let the self-check go un-invented until J had to dictate it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    import datetime as _dt
    def et_now(): return _dt.datetime.utcnow()

LEDGER = REPO / "automation" / "state" / "friction-ledger.jsonl"

# Friction PATTERN classes — normalized buckets the four-beat can question. Each is a
# CONSTRAINT we keep grinding against, keyed by signature phrases.
PATTERNS = {
    "validation_gates_all_trading": {
        "constraint": "every candidate must pass the validate-before-trade gauntlet before it can generate any data",
        "keys": ["no armable edge", "not trading", "no_armable", "mirage", "fails oos", "oos-fail", "oos fail",
                 "washes out", "coin flip", "null reproduces", "null-reproduces", "didn't beat the null", "hold all day",
                 "engine held", "no edge currently armable", "only 2 validated", "2 strategies"],
    },
    "sim_dies_on_real": {
        "constraint": "edges validated in BS-sim die on fresh OPRA real fills",
        "keys": ["dead knob", "dead-knob", "fresh opra", "recency red", "bs-sim", "sim-validated", "ranking-only",
                 "validated at qty", "notional cap"],
    },
    "regime_dependence": {
        "constraint": "edges flip sign by regime — a full-period number hides the truth",
        "keys": ["regime", "vix regime", "bull-recovery", "regime-dependent", "regime flip", "anti-correlate"],
    },
    "silent_failure": {
        "constraint": "the rig fails silently (exit 0, no output) and we discover it late",
        "keys": ["silent failure", "silent death", "silently", "exit 0", "parse error", "reaper", "killed externally",
                 "frozen", "stale", "blind", "didn't fire", "never fired"],
    },
    "small_account_constraint": {
        "constraint": "the $2K account's min-contracts / risk-cap / PDT plumbing suppresses signals",
        "keys": ["min 3 contracts", "min-3", "notional cap", "pdt", "risk cap", "$2k", "2000", "sizing tier", "per-trade risk"],
    },
    # OPERATOR friction (not rig friction). A REPEATED state-question from J is a missing
    # instrument, not a query (OP-33(e)). The metacog dissection (2026-06-29) found the
    # load-bearing root cause of the self-check blind spot: the friction organ counted the
    # SYSTEM's pain and never J's, so "J asked 6 times" crossed no threshold. This class
    # fixes that — it is fed by automation/state/j-question-ledger.jsonl (J's interrogatives,
    # captured by setup/hook-detect-correction.ps1) and escalates FAST (>=2, see distill()).
    "recurring_user_question": {
        "constraint": "J has to repeatedly ASK the same state-question (is-it-running / did-it-crash / is-it-trading) -- a visibility gap that should be a standing instrument, not a per-turn answer",
        "keys": ["is it running", "is it trading", "did it crash", "is it working", "well?",
                 "any update", "is it actually", "did it fire", "still running", "no visibility",
                 "no confidence", "you told me", "you said it worked", "did it save", "where is"],
    },
}

# This class escalates on operator-repetition, NOT on the months-of-system-friction bar.
FAST_ESCALATE = {"recurring_user_question": 2}


def _classify(text: str) -> str | None:
    t = text.lower()
    for pid, spec in PATTERNS.items():
        # recurring_user_question is OPERATOR friction -- it must come ONLY from J's actual
        # question-ledger (force-classified in _harvest), never from prose in mistakes/LESSONS
        # that happens to mention "no visibility"/"you told me". Else an empty ledger still
        # falsely trips BUILD_ELIMINATING_INSTRUMENT = a phantom signal that erodes trust.
        if pid == "recurring_user_question":
            continue
        if any(k in t for k in spec["keys"]):
            return pid
    return None


def _date_in(text: str) -> str | None:
    m = re.search(r"20\d\d-\d\d-\d\d", text)
    return m.group(0) if m else None


def _harvest():
    """Yield (pattern_id, source, date) hits from the recurring-friction sources."""
    today = et_now().strftime("%Y-%m-%d")
    sources = {
        "mistakes": REPO / "journal" / "mistakes.md",
        "status_known_broken": REPO / "automation" / "overnight" / "STATUS.md",
        "lessons": REPO / "markdown" / "doctrine" / "LESSONS-LEARNED.md",
        "postmortems": REPO / "markdown" / "research" / "MISSED-SETUPS-POSTMORTEM-2026-06-29.md",
    }
    for src, p in sources.items():
        if not p.exists():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            if len(ln.strip()) < 12:
                continue
            pid = _classify(ln)
            if pid:
                yield pid, src, (_date_in(ln) or today)
    # jsonl state sources (recurring across runs = structural)
    for src, rel in (("conductor", "automation/state/conductor-outcomes.jsonl"),
                     ("gap_log", "analysis/self-audit/gap-log.jsonl"),
                     ("rejections", "automation/state/recency-confirmation.json")):
        p = REPO / rel
        if not p.exists():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln in txt.splitlines():
            pid = _classify(ln)
            if pid:
                yield pid, src, (_date_in(ln) or today)
    # OPERATOR friction: J's question-ledger. Every line is a state-question J had to ask,
    # so force the class (don't rely on keyword match) -- each line is one occurrence.
    qledger = REPO / "automation" / "state" / "j-question-ledger.jsonl"
    if qledger.exists():
        try:
            for ln in qledger.read_text(encoding="utf-8", errors="replace").splitlines():
                if len(ln.strip()) < 2:
                    continue
                yield "recurring_user_question", "j_questions", (_date_in(ln) or today)
        except OSError:
            pass


def distill() -> dict:
    agg: dict[str, dict] = {}
    for pid, src, date in _harvest():
        a = agg.setdefault(pid, {"pattern_id": pid, "constraint": PATTERNS[pid]["constraint"],
                                 "occurrences": 0, "sources": set(), "dates": []})
        a["occurrences"] += 1
        a["sources"].add(src)
        a["dates"].append(date)

    rows = []
    for pid, a in agg.items():
        dates = sorted(d for d in a["dates"] if d)
        first, last = (dates[0], dates[-1]) if dates else (None, None)
        span_days = 0
        if first and last:
            import datetime as dt
            try:
                span_days = (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days
            except ValueError:
                span_days = 0
        if pid in FAST_ESCALATE:
            # operator-repetition escalates in N asks, not months across 2 sources
            eligible = a["occurrences"] >= FAST_ESCALATE[pid]
            action = "BUILD_ELIMINATING_INSTRUMENT"  # build the standing surface, not re-answer
        else:
            eligible = a["occurrences"] >= 5 and len(a["sources"]) >= 2 and span_days >= 14
            action = "STEP_BACK_RITUAL"  # Opus weekly Constraint Provenance Audit
        rows.append({"pattern_id": pid, "constraint": a["constraint"], "occurrences": a["occurrences"],
                     "n_sources": len(a["sources"]), "sources": sorted(a["sources"]),
                     "first_seen": first, "last_seen": last, "span_days": span_days,
                     "step_back_eligible": eligible, "action": action})
    rows.sort(key=lambda r: (-int(r["step_back_eligible"]), -r["occurrences"]))

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return {"ts_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"), "patterns": rows,
            "eligible": [r["pattern_id"] for r in rows if r["step_back_eligible"]],
            "build_now": [r["pattern_id"] for r in rows
                          if r["step_back_eligible"] and r.get("action") == "BUILD_ELIMINATING_INSTRUMENT"]}


if __name__ == "__main__":
    out = distill()
    print(f"=== FRICTION LEDGER ({out['ts_et']}) ===")
    for r in out["patterns"]:
        flag = "** STEP-BACK-ELIGIBLE **" if r["step_back_eligible"] else ""
        print(f"  {r['pattern_id']:30} occ={r['occurrences']:3} sources={r['n_sources']} "
              f"span={r['span_days']}d {flag}")
        print(f"     constraint: {r['constraint']}")
    print(f"\n  Eligible for the Step-Back ritual (Constraint Provenance Audit): {out['eligible']}")
    if out["build_now"]:
        print(f"  ** BUILD THE ELIMINATING INSTRUMENT NOW (operator friction): {out['build_now']} **")
