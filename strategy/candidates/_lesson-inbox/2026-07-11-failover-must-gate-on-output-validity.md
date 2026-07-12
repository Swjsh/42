# Failover ladders must gate on OUTPUT VALIDITY for the caller's contract, not transport success

## Symptom
`swarm_client.call_role_json` returned `parsed=None` on ~half of twin_review's critic
calls (live-tested 2026-07-11): the primary lane (openrouter nemotron-3-super-120b)
drifted into inline chain-of-thought prose instead of JSON, even under a strict
"ONLY raw JSON" system prompt at low temperature. The same prompt passed FIRST-TRY
on the local ollama floor (qwen3:14b) — but the roster never fell through to it.
Same mechanism silently threw away one of the heartbeat_core 2-model entry-veto
votes (`no_valid_json`) whenever the critic lane drifted on a live ENTER candidate.

## Root cause
`call_role`'s failover condition was `ok=True AND non-empty content` — transport
success. A lane that ANSWERED with malformed-for-the-caller content (prose when the
caller needs schema-valid JSON) was treated as the winning lane, so the ladder never
reached the compliant cerebras/local-floor lanes. The one repair-retry re-entered
`call_role` fresh at lane 0, re-rolling the same noncompliant primary. The module
header even documented "repair-retry then failover to the next lane" — the failover
was never implemented (docstring described intent, not code).

## Fix
`call_role_json` now owns its lane loop (swarm_client.py, 2026-07-11): schema-valid
JSON is the WIN CONDITION per lane; transport-ok prose is a failed lane and falls
through. One repair-retry total, pinned to the lane it repairs (spent on
parseable-but-schema-invalid output; forfeited on no-JSON-at-all except on the final
lane). Worst case = len(lanes)+1 calls. Envelope now carries `json_attempts` +
`json_lanes_rejected` so per-lane compliance evidence accumulates in caller ledgers
for the free-model audit harness. `call_role` (prose consumers) untouched.
Generalization: any retry/failover ladder must test the caller's ACCEPTANCE
criterion, not the transport's — "it returned bytes" is C7 silent success.

## Encoded in
- `setup/scripts/swarm_client.py::call_role_json` (the mechanism)
- `backtest/tests/test_swarm_client_json.py` (9 graduated guards: prose fallthrough,
  repair budget, worst-case call bound, unchanged `call_role` prose semantics)
- Verified live 2026-07-11: keyless run → floor won with valid JSON
  (`lane=ollama::qwen3:14b`); real-key runs → compliant primary wins in 1 attempt
  (zero added latency when the primary behaves).

## L## (optional)
Suggest theme C7 (silent success / audit outputs) — cross-reference C14 (dead knob:
the documented-but-never-implemented failover was a dead contract).
