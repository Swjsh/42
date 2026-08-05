# A fail-safe except around a LAZY IMPORT hid a permanently-dead producer lane for 6 weeks

**Date:** 2026-08-04 (RISKY3-SPECULATIVE lane) · **Cluster:** C7 (silent success is failure) / C14 sibling · **Severity:** architecture-scale silent gap

## Symptom
The FIX2 fleet `strategies[]` vwap_continuation emission (shipped 2026-06-25, documented,
flag-gated `RUN_VWAP=True`, registry-carried, tested) never emitted once: **0 vwap rows in
any fleet arm's 3,865-row decisions.jsonl**. Nobody noticed for 6 weeks because nothing
errored — the arms just "had no vwap signal."

## Root cause (one sentence)
`fleet_market._lazy_imports()` did `from filters import BarContext` off a `backtest/lib`
sys.path entry, but `backtest/lib/filters.py` opens with a PACKAGE-relative import
(`from .ribbon import RibbonState`), so the top-level import raises ImportError on every
call — and the surrounding fail-safe `except Exception: return (None, None, None)`
converted a permanent wiring bug into "detector returned no signal this tick," forever.

## Mechanism that made it invisible
- The fail-safe was CORRECT design for transient fetch/dep misses — but it also swallowed
  a **deterministic, permanent** failure class (import spelling), which a fail-safe must
  never be allowed to hide without a resolve-check somewhere.
- Tests imported the detector through OTHER paths (package imports in the pytest env), so
  suites stayed green while the producer's own import spelling was broken.
- Second env trap found while fixing: the producer runs under SYSTEM python via
  `_shared.ps1#Invoke-PythonHidden`, which injects the backtest venv via `PYTHONPATH` —
  a bare `python x.py` repro WITHOUT that env var "reproduces" failures prod doesn't have
  (and vice versa). **Repro must copy prod's PYTHONPATH/VIRTUAL_ENV.**

## Fix + guard (shipped `aa2e3f07`)
- Imports corrected to package form (`lib.filters`, `lib.watchers.*`) with `backtest/` on
  sys.path — verified OK under the prod-faithful env (system python + venv PYTHONPATH).
- **Guard shape worth generalizing:** `test_lazy_imports_actually_resolve` — for every
  lazily-imported, fail-safe-wrapped dependency chain, one test that calls the lazy
  importer and asserts it returns real objects. RED-proofed against the pre-fix spelling.

## Lesson candidate (for LESSONS-LEARNED L###)
Every `try: import ... except: return None` lane needs a companion resolve-test that
fails loudly when the import can NEVER succeed; and any "runs under Invoke-PythonHidden"
repro must include prod's PYTHONPATH env or it tests a different interpreter reality.
