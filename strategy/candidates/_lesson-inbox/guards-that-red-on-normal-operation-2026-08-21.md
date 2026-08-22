---
kind: lesson
filed: 2026-08-21
theme: C7 (silent success is failure) — the INVERSE face: loud failure on success
severity: HIGH
---

# A guard that REDs during normal operation is training everyone to ignore RED

## The trigger

The nightly full suite reported **18 failures / 9,950 passes**. Triaging all 18 found
that **none** were caused by that day's work, and that the dominant category was not
"broken code" but **guards that fire when the system is working correctly**:

| Guard | Fired because | Frequency |
|---|---|---|
| `test_archive_ledgers` | the append-only ledger grew past a dated snapshot | **every trading day** |
| `dataset_integrity` (mae-mfe) | an append-only file was appended to | **every trading day** |
| `test_ccr_interactive_isolation` | retention archived an allowlisted narrative file | every archive |
| `test_pnl_attribution` / `test_regime_reslice` | a research artifact was legitimately regenerated | every regeneration |
| `test_guard_cmd_popup_fix_ws6` | **the popup bug was FIXED** (pattern deliberately demoted) | permanently, 5 weeks |
| `test_gate_e2e` | a gate was **deliberately lifted** 18 days earlier | permanently |
| `test_claude_md_account_ids` | it only knew one of the repo's two account registries | permanently |

Seven distinct guards, all RED for reasons that meant *"the system did its job."*

## Why this is dangerous, in this repo's own words

`dataset_integrity.py`'s docstring records the cost precisely. When a replay artifact was
silently mutated (190 → 191 trades by a commit "with no business touching a replay
artifact"), **"three downstream tests went RED and were nearly dismissed as stale pins,
and one study read the mutated file and published the wrong population size."**

A suite that REDs on normal operation manufactures exactly that reflex. The failures are
individually harmless and collectively corrosive: they teach every reader — human or
agent — that RED means "probably housekeeping."

**I demonstrated the failure mode while fixing it.** I updated a pinned count from 57 to
58 to match the regenerated population, and only *afterwards* checked whether the
regeneration was legitimate. It was. But the check belonged before the edit, and if it had
been the corruption case I would have papered over it in exactly the documented way.

## The rule

**A guard must fail only on states that are actually wrong.** Before shipping one, ask:
*what does the system do routinely that would trip this?*

Concretely, the three shapes that keep recurring here:

1. **Unbounded anchor** — pinning `len(growing_population)` or comparing a live
   append-only file to a dated snapshot. Fix: bound the live side to the snapshot's own
   declared window, or hash a declared **frozen prefix** and let the tail grow. Never pin
   a second copy of the boundary date; read it from the artifact.
2. **Stale pin** — asserting a value that was later changed on purpose. Fix: assert the
   current value *and cite the commit that set it*, so the next legitimate change is a
   deliberate update rather than a mystery. Never delete the assertion.
3. **Partial-registry guard** — asserting against one source when the system has several
   (fleet accounts vs the multi lane's own config; `queue.md` vs its dated archives). Fix:
   derive the rule (archives of allowlisted files inherit the sanction) rather than
   maintaining a list that a routine operation invalidates.

## The tell

If a guard's failure message would be equally true written as *"we traded today"* or
*"the producer ran"*, it is not a guard — it is a changelog with an exit code.

## Second finding: attribute failures before fixing them

Of the 18, seven **passed standalone and failed only in-suite** (`test_setup_dispatch` ×5,
plus two others) — order-dependent state leaking between modules. A suite that cannot say
*which* failures are real is a second-order version of the same problem. Triage by running
the failing test alone **first**; it separates "broken" from "polluted" in seconds and
costs nothing.
