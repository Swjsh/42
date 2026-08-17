---
filed: 2026-08-17
filed_by: EOD full review (J: "is TP1 static or dynamic?")
kind: lesson
status: pending
---

# A config key that is REFERENCED can still be a lie — the whole exit shape in both params files is overridden by a hardcoded cell

## Symptom

J watched the day's one winning trade take TP1 and asked whether TP1 is static or dynamic.

- `automation/state/aggressive/params.json` says **`tp1_premium_pct: 0.75`**
- The engine took TP1 at **+100%**

Proven on the real fill rather than inferred. Entry 0.72, so +75% = 1.26 and +100% = 1.44:

| tick | `best_premium` | clears +75% (1.26)? | clears +100% (1.44)? | fired? |
|---|---:|---|---|---|
| 13:24 | 1.40 | **yes** | no | **no** |
| 13:26 | 1.55 | yes | **yes** | **yes** |

A +75% TP1 would have fired at 13:24. It did not. The live value is the literal
`tp1_premium_pct=1.0` at `automation/state/fleet/strategies.py:131`, inside RIBBON_RIDE's
`ExitShape`.

## Root cause, and why grep says everything is fine

The hardcode itself is **correct practice**: it is the SS-B validated cell, ported whole per
C29 ("never mix fields across cells"). The defect is that `params.json` keeps advertising a
different number to whoever reads or tunes it next.

And the key **IS referenced** in the codebase — so every "is this knob dead?" check that greps
for the name reports it healthy. Two genuinely different failure modes hide behind one word:

| class | what it looks like | does grep catch it? |
|---|---|---|
| **UNREFERENCED** | name appears in no `.py` | ✅ yes |
| **SHADOWED** | name IS referenced, but a hardcoded literal wins downstream | ❌ **no — reports healthy** |

The TP1 lie is the SHADOWED class. Conflating the two is what let it survive.

## Scope — it is not one key

`tp1_premium_pct`, `tp1_qty_fraction` and `premium_stop_pct` are shadowed in **both** params
files. **Anyone tuning stop, target or size from the config is tuning nothing.** Plus 58
unreferenced keys, of which several were *already known dead and left in the file*:

- `bid_ask_spread_max_cents` — `heartbeat_core.py:2361`'s own comment calls it a dead knob
- `open_interest_min` — a crypto validator notes it is "prose-referenced not key-named"
- `delta_min_abs`, `enable_news_no_trade_windows` — appear in **zero** non-test `.py`
- `ribbon_min_spread_cents` — known dead since `fleet_gate_sweetspot.py:505` wrote it down

The live gate reads the module constant `RIBBON_SPREAD_MIN_CENTS`; the orchestrator's key is
`ribbon_spread_min_cents` (no `min_` prefix). **Sweeping the params key in a study would have
produced identical cells at every threshold and "proved" the spread threshold does not
matter.** That near-miss is what triggered this audit.

## Generalisations worth keeping

1. **"Referenced" is not "authoritative."** The only proof a knob is live is VARY-AND-ASSERT:
   change it, run, and assert the output changed. A study that sweeps a knob should assert its
   cells differ before reporting anything — a null result and a dead knob are indistinguishable.
2. **A config file is a claim about behaviour.** When it drifts from the engine it does not go
   quiet, it goes *wrong*: the next tuner reads 0.75, changes it to 0.60, sees nothing happen,
   and concludes the parameter has no effect.
3. **Knowing a knob is dead and leaving it in the file is worse than not knowing.** Three of
   these were documented in code comments and still sat in production config. A comment in a
   `.py` is not visible to someone reading `params.json`.
4. **Prefer a standing check to prose.** Annotating params.json would rot and risks editing a
   live decision-gating file; a nightly audit does not. `dead_knob_audit.py` now rides the
   Gamma_WinnerAutopsy fold and reports both classes separately.

## Guards

`backtest/tests/test_dead_knob_audit.py` — pins the TP1 finding specifically, asserts the whole
exit shape is flagged (not just TP1), keeps `_doc` prose out of the report so the real six are
not buried, and AST-checks that the audit stays wired into the nightly fire.

Commit: `f0e5cd51`.
