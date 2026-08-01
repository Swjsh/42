# LESSON CANDIDATE: an A/B backtest reading an on-disk OPRA cache that a CONCURRENT backfill is actively appending to must freeze its own snapshot, or arms silently diverge on DATA, not treatment

**Date:** 2026-08-01 (WS4, PAIRED-RIBBON-AB-2026-08-01 study — same study as the sibling
`2026-08-01-filters-py-demerit-vanishes-under-raw-disable-filters.md` item; prereg
`e5e323f2`, runner `4814e6bb`, verdict NULL `96ae89bb`).

**Symptom:** the prereg's control anchor assumed "raw entry production is
OPRA-cache-independent" (`CONTROL_RAW_ENTRY_ANCHOR = 211`, taken from the 2026-07-31
filter5-ribbon run, asserted with a documented +/-10 cache-artifact tolerance band). On the
live run, CONTROL's raw entry count drifted 211 -> 212 — purely from elapsed time WITHIN
the same study process, not from any code difference. Root cause traced to a concurrent
overnight OPRA backfill actively appending to the shared contract cache
(`CACHE_DIR`/`option_pricing_real.py`) DURING the study: 14225 -> 14342 -> 14400 contracts
across the session. Because `use_real_fills=True` means the ENTRY layer reads the SAME
cache too (`simulator_real.py:420`, `load_contract_bars`, used for the entry fill price and
the $0.30 premium floor) — not just the exit/walk layer — a cache growing BETWEEN two
sequential backtests inside ONE process (CONTROL's run, then PAIRED's run, run back to
back in the same script) could make the two arms price the "same" contract/day off
genuinely different underlying data, fabricating a phantom book difference unrelated to the
actual treatment under test.

**Root cause:** any backtest/study that reads an on-disk cache or data directory that
ANOTHER concurrent process might be actively writing to cannot assume "it's reading from
disk" implies "deterministic within this run." Two sequential runs inside the SAME script
(a study's own control-then-treatment sequence) are exactly as exposed to this race as two
genuinely separate processes would be — the exposure isn't about multiprocessing, it's
about the read happening at different WALL-CLOCK MOMENTS while a writer is live.

**Fix (shipped, in this study):** `freeze_contract_cache(snapshot)` —
`backtest/tools/paired_ribbon_ab_2026_08_01.py:162-192`. Takes a `frozenset` of cache
filenames via `CACHE_DIR.glob("SPY*.csv")` captured ONCE at the very start of `main()`
(line ~486), then monkeypatches BOTH by-name bindings of the loader
(`lib.option_pricing_real.load_contract_bars` AND `lib.simulator_real.load_contract_bars` —
first asserts they `is` the SAME function object, so the dual-patch cannot silently miss
one binding) with a `gated()` wrapper: returns `None` for any symbol absent from the frozen
snapshot, else delegates to the real loader (whose own process-lifetime memoization then
guarantees a contract's FIRST-touch content is what every later read — either arm, either
layer, either backtest — sees for the rest of the process). This guarantees CONTROL and
PAIRED observe exactly ONE consistent cache view, fully decoupled from whatever the
concurrent backfill does on disk mid-run. Not restored on purpose — the freeze is meant to
outlive the whole study process.

**Why it matters / generalizable pattern:** this is the SAME class of bug as the 2026-08-01
git shared-index absorption incidents (see
`2026-08-01-shared-index-absorption-between-parallel-lanes.md`) one layer down the stack —
a concurrent writer mutating shared on-disk state that a reader implicitly assumed was
stable for the duration of its own operation. There: git's index. Here: an OPRA contract
cache directory. **Any future backtest tool reading option-cache files (or any other
externally-appended cache) during a window when a backfill might be running concurrently
should snapshot-and-freeze its own view at the top of `main()`** — the same pattern as this
fix — rather than trust "the file's on disk, so reading it twice gives the same answer."

**Caught how:** the prereg's own disclosed, asserted control-count anchor (211, with an
explicit +/-10 cache-artifact tolerance band written into the prereg BEFORE the run) tripped
on the first attempt. The team stopped and diagnosed the mechanism (cache growth, traced to
the concurrent backfill) rather than silently loosening the anchor or accepting the drift —
the anchor did its job as a tripwire.

**Encoded in:** `backtest/tools/paired_ribbon_ab_2026_08_01.py` (`freeze_contract_cache`,
lines 160-192) for THIS study only — not yet extracted into a reusable helper. **Suggested
follow-up (not built, flagged for a future session):** promote `freeze_contract_cache` (or
an equivalent) into a shared module — `backtest/lib/option_pricing_real.py` itself, or a
small new `backtest/lib/cache_freeze.py` — so future A/B studies reading the OPRA cache
during a backfill window get this protection by default instead of re-discovering the race
from a tripped anchor each time. File/line citations:
`backtest/tools/paired_ribbon_ab_2026_08_01.py:160-192` (`freeze_contract_cache`),
`backtest/lib/simulator_real.py:420` (entry-layer cache read),
`backtest/lib/option_pricing_real.py` (`CACHE_DIR`, `load_contract_bars`). Disclosed in
`analysis/recommendations/paired-ribbon-2026-08-01.md` ("Control parity" section) and the
study's output JSON `note` field. **Related:** C34 (shared-checkout concurrent-write
hazards — same family as the git absorption lessons, different shared resource).
