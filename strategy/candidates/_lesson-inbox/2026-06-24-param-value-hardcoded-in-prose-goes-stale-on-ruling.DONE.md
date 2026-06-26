# Lesson candidate: a hardcoded param-VALUE claim in prose goes stale the moment the param is flipped

**Filed:** 2026-06-24 (conductor fire, ~20:05 ET)
**Theme:** C7 (silent failure / cry-wolf observability) + the L170/L173/L179/L181/L185 no-closing-handshake stale-breadcrumb family
**Status:** propose — decide whether to GRADUATE to a drift ratchet (it is arguably a re-violation → STAGE 4.5 says a re-violated lesson MUST become a test)

## Symptom
The task-scorer ranked `GATE-STACK-OVERBLOCK-A-PLUS-RECLAIM` as the #1 ready item (score 6.0, HIGH). Its entire headline premise was "the `block_bull_morning_agg` gate is BLOCKING A+ reclaims → quality-condition it." But J had **already removed that gate entirely earlier the same day** (mid-session Rule-9 override, `aggressive/params.json#block_bull_morning_agg: false`). A fire that trusted the breadcrumb would have spent a full cycle (and a real backtest) researching how to fix a gate that no longer fires. Two consumer surfaces also disagreed with the live param:
- `automation/prompts/aggressive/heartbeat.md` line 356 still annotated the gate "(currently `true`)" — the LIVE PROMPT the engine reads contradicting the param it reads. (Behavior was still correct because the gate logic is param-gated at runtime — but the annotation is misleading to any reader, human or model.)
- `queue.md` GATE-STACK item + task-scorer ranking both treated `=true` as current.

## Root cause
When J makes a mid-session param ruling, the **canonical state** (the `params.json` value + its `_doc`) gets updated, but the **reverse-references** that hardcode the value — queue research items that name the param as a live lever, and heartbeat-prompt annotations of the form "currently `<value>`" — do NOT get swept. They are write-once prose that silently rots. The `_doc` field captured J's quote perfectly; everything pointing AT the param did not.

## Fix (this fire, manual)
Reconciled the queue item to RESOLVED-BY-J + reframed the residual (the genuine open question — does blanket-removal reopen a net drain a quality-conditioned gate would prevent — needs a fresh scored backtest, surfaced to J). Staged rail-4 proposal `gp-2026-06-24-001` to sync the heartbeat prose. Pinged J.

## Proposed guard (graduate-if-it-recurs)
A presence/drift ratchet (same class as `crypto/validators/v25_filter_gates.py` / `test_params_filters_drift.py`): scan the heartbeat prompts for the pattern `params.json#<key>` … `(currently \`<value>\`)` and assert `<value>` equals the live `params.json[<key>]`. Fails loud the next time a ruling flips a param but leaves a prompt annotation stale. (Optional extension: flag queue.md research items that assert a param value the live file contradicts.)

## Watch-out
Do NOT hardcode a param VALUE in any prose that another surface reads as authoritative. Reference the key and let the runtime read it; if an annotation MUST state the current value, it is a drift liability that needs a guard.

## Related
L181 (STATUS.md regrowth stale-breadcrumb), L185 (fused-verdict-anchor), L170/L173/L179 (no-closing-handshake). C14 (dead/translated-but-unapplied knobs — a flipped gate whose prose still claims active is the inverse: an inactive knob whose prose claims active).
