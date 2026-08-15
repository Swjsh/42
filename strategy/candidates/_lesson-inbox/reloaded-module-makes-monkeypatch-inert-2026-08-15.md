---
filed: 2026-08-15
filed_by: handoff-queue fire (HANDOFF-2026-08-15-ENGINE-REVIEW item 3, Family D)
kind: lesson
status: pending
---

# `importlib.spec_from_file_location`-loading a module its PARENT already imported creates a second module object — every monkeypatch lands on the copy, and the test fires the REAL call it believed it had mocked

## Symptom

Two guards were failing and had been labelled **"network-dependent (2, confirm network-only
first)"** in the handoff. They are not network-dependent — both monkeypatch every LLM entry
point before calling anything:

```python
monkeypatch.setattr(sca, "_blind_reanswer",      lambda q, c, **kw: "independent answer")
monkeypatch.setattr(sca, "_agreement_judgment",  lambda q, b, s, **kw: {"agree": True, ...})
result = adapter.grade(items[0], {"allow_llm_fallback": True})
assert result["grading_method"] == "llm_judgment"
#   AssertionError: 'ungraded_insufficient_data' == 'llm_judgment'
```

Running the identical sequence by hand in a plain script returned `llm_judgment` — correct. It
only failed under pytest, and it failed in isolation too, so it was not cross-test pollution.

## Root cause

The guards load their modules with a helper that **re-executes the file**:

```python
def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # <-- overwrites whatever was already there
    spec.loader.exec_module(mod)
    return mod

fma = _load("free_model_audit", ...)                  # this ALSO imports the adapter below
sca = _load("free_model_audit_swarm_consult", ...)    # ...so this builds a SECOND copy
```

`free_model_audit` imports each adapter itself while building `AUDIT_SUBJECTS`, and the
adapter's `grade` closes over **that** instance. The second `_load` replaces the `sys.modules`
entry but cannot rebind the already-captured function. Measured directly:

```
adapter.grade.__globals__ is sca.__dict__   ->  False
```

So the patches decorated a module nothing calls, and `grade()` ran the genuine
`_blind_reanswer` — a live `claude` subprocess.

## Why this is worse than a red test

**It only failed because the real call fails on this box.** With a working subprocess it would
have gone GREEN while spending real money on every suite run — a mocked-looking test quietly
billing the API (OP-3). Proof the real call is now gone: the two suites went **4.38s → 0.34s**.

And the failure was not the worst case. A **third** guard, `prospector`, was **passing for the
wrong reason**: its two `monkeypatch.setattr(pa, ...)` calls were equally inert, so
`adapter.grade` read the **real production `ideas-ledger.jsonl`** instead of the `tmp_path`
fixture the test had carefully written, and asserted the value the unpatched path happened to
return. Silent live-state coupling inside a test that looked clean and green.

## The fix

Do not re-execute a module the parent already imported — bind to the one instance:

```python
fma = _load("free_model_audit", "setup/scripts/free_model_audit.py")
sca = sys.modules["free_model_audit_swarm_consult"]   # the instance the adapter closes over
```

Applied to **all four** sibling guards, including `heartbeat_veto`, which was not yet wrong
(its tests call `hv.grade_item` directly rather than through `adapter.grade`) but sat one added
adapter test away from the same defect.

## Generalisations worth keeping

1. **A passing test is not evidence its mocks are wired.** Assert the seam when the patch
   target is reached indirectly: `assert adapter.grade.__globals__ is mod.__dict__`. Cheap, and
   it is the only thing that distinguishes "mocked" from "accidentally live".
2. **`spec_from_file_location` + `sys.modules[name] = mod` is not idempotent.** It is a *second*
   module, not a re-import. Safe only for a module nothing else has imported. Prefer
   `sys.modules.get(name)` first, or a plain `import` on a `sys.path` entry.
3. **Suspect the diagnosis when a test fails under pytest but passes in a hand-written script
   with the same steps.** That gap is import identity or fixture state, not the code under test.
4. **"Network-dependent" is a conclusion, not a label to inherit.** The handoff's instruction to
   *confirm network-only first* is what surfaced all of this; taking the label at face value
   would have xfail'd four tests and left the real subprocess calls running.

## Guards

Seam verified for all four adapters (`swarm_consult`, `twin_review`, `prospector`,
`heartbeat_veto`): `adapter.grade.__globals__ is <module>.__dict__ -> True`. 92/92 green.

Fix: `7c0895f1`.
