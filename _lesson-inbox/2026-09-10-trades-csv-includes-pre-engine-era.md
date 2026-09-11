---
kind: lesson
date: 2026-09-10
source: GOAL-WHY-THIS-WEEK-2026-09-10 W6
---

# Per-arm engine claims sourced from journal/trades.csv are inflated by the pre-engine era

**Symptom.** A session computing per-arm P&L from `journal/trades.csv` got safe-2 = **+$1,117
over 148 legs** and used it to "correct" `go_live_gate.py`'s **−$654**, publicly withdrawing a
correct audit finding on the strength of the wrong number.

**Root cause.** `go_live_gate.py` reads `analysis/trades-enriched.jsonl` filtered to
`attribution == "engine"` (`go_live_gate.py:89`, `:509`). `journal/trades.csv` is the RAW leg
ledger: it spans the **pre-engine era (2026-04-29 → 2026-06-26)** and includes manual/J-era
fills. For safe-2 that is **12 legs worth +$1,587** — including +$1,795 on 05-14 and +$730 on
05-04 — none of it the engine's work. Restricted to the engine span the two agree to within
one trip / $21 (CSV −$470 within-span legs vs enriched −$675 engine trips).

**Fix / how to avoid.** Any claim of the form "arm X is up/down $N" as a statement about the
ENGINE must be sourced from `analysis/trades-enriched.jsonl` filtered to
`attribution == "engine"`, never from raw `journal/trades.csv`. The CSV is correct as a leg
ledger and is the authority for real fills (C1) — it is simply the wrong POPULATION for an
engine claim. Right file, wrong population: a provenance-seam error (C1/C4).

**Second-order lesson.** The wrong number was used to overturn a correct one. When a fresh
computation contradicts an established instrument, **reconcile the populations before
withdrawing the instrument's claim** — the instrument usually encodes a filter you have not
replicated. A too-bad-to-be-true number deserves the same artifact hunt as a too-good one.
