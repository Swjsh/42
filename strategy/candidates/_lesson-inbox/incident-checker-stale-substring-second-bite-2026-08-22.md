## Lesson candidate: a status-checker's own heuristic can go stale when the code it checks is refactored — and it re-bites the SAME instrument that already fixed this once

**Where:** `setup/scripts/incident_fix_status.py#_chk_conviction_components`, fixed 2026-08-22, commit `6774b7cf`.

**What happened:** the checker asserted C5 (structure-agreement) was wired via a literal
substring, `"_sameday_structure_side(payload)" in s`. On 2026-08-18 an alignment review
refactored the live call site in `heartbeat_core.py` to `_sameday_structure_diag(payload)`
(adds a diagnosable reason string alongside the side) — a strictly *better* wiring, not a
regression. The substring stopped matching. The checker reported `[RED] conviction-c4-c5 ...
C5 still None` on every run for 4+ days across 8+ conductor fires, even though:
- the comprehensive pytest guard for the same fix (`test_conviction_c4_c5_wiring_2026_08_14.py`)
  stayed green the entire time (it asserts on the AST of the calling function, not a fixed
  call-site spelling), and
- the live decision ledger showed C5 fully wired and scoring: 164/164 `conviction` rows since
  2026-08-19 carry a real, diverse `structure_reason` (range/uptrend/downtrend/unknown/error,
  zero `None`).

**Why this is notable beyond "fix the substring":** `incident_fix_status.py`'s own docstring
already names this exact trap once — "AST, NOT SUBSTRING. The first version of this check did
`'"bars_prior"' in s`..." — and was rewritten to AST-walk for the transposed-key half of the
SAME function. The `struct` half sitting three lines below kept the substring pattern the doc
comment right above it was written to warn against. **A lesson learned about one half of a
function does not automatically protect the other half of the same function** — the fix has to
be applied at the pattern level (grep the file for every remaining raw substring check), not
just at the one call site that already burned someone.

**Generalizable guidance:** any status/health checker whose assertion is "does string X appear
in file Y" is coupled to Y's *exact current spelling*, not its *behavior*. When Y is refactored
for an unrelated reason (better diagnostics, a rename, an extracted helper), the checker can
silently flip RED on correct code — indistinguishable at a glance from a real regression, and
worse than no checker at all if nobody re-verifies against the guard test/live data before
believing it. Prefer (a) AST-based structural assertions (call-to-any-of-N-names, kwarg is not
a hardcoded literal) over (b) raw substrings, and when a file already contains one AST-based
check next to one substring check for closely related concepts, treat that asymmetry itself as
a code smell worth fixing preemptively.

**Cost of the false RED:** no financial impact (shadow-only telemetry surface, conviction is
disarmed — `would_block` branches on nothing yet), but real fire-time cost: at least 2-3
conductor fires spent re-triaging this same line ("needs real design work" / "flagging for
FABLE-ESCALATION") before this fire actually read the check's own source instead of trusting
its verdict.
