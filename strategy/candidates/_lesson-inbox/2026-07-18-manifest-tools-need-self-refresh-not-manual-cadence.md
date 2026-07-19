# A manually-run manifest with a "regenerate this" docstring WILL go stale — self-refresh at the point of use, not by cadence discipline

**Found:** 2026-07-18, conductor fire (F3-RED-BOOK-STILL-ARMED close).

**Symptom:** `backtest/tools/data_coverage_manifest.py` exists specifically to close a
"silent real-fills blind spot" (its own docstring: the option-chain OPRA cache lagging
behind the SPY price-bar cache invisibly). But nothing scheduled it — it's a manually-run
tool. Found stuck at `option_chain_realfills.last=2026-07-08` (manifest itself last
regenerated 2026-07-14, and even that regeneration had already undercounted) while the
REAL on-disk option-chain cache (`backtest/data/options/SPY*.csv`) had genuinely extended
to 2026-07-17 — a silent ~9-trading-day gap between "what the manifest claims" and "what's
actually on disk." `recency_check.py`'s `read_cache_last_date()` trusted the manifest
blindly, so the CONFIRM-BEFORE-CAPITAL gate's "recent window" was silently truncated by
~9 days on every nightly `Gamma_LicenseMonitor --run` fire — the guard needed a guard.

**Root cause:** a monitoring/manifest tool that answers "is my data fresh" is itself
data that can go stale, and "run this periodically" is not a mechanism — it's a hope. The
manifest's OWN staleness was invisible because nothing checked the checker.

**Fix pattern (generalizable):** when a cheap, deterministic manifest-generator function
exists (`build_manifest()` here — a pure re-scan of files already on disk, no network, no
heavy compute), the CONSUMER should call it inline at the point of use and rewrite the
manifest before reading, falling back to the stale file only on an exception (fail-open
for the gate's caller, never crash). This converts "nothing keeps this current" into
"every reader keeps this current for every other reader too" — self-healing by
construction, no scheduled task needed. Applied in
`backtest/autoresearch/recency_check.py::read_cache_last_date()`.

**Generalize:** any OTHER manually-run "manifest" / "coverage" / "freshness" reporter in
this repo that (a) is cheap to regenerate (pure file-scan, no heavy backtest) and (b) has
a known consumer that reads its JSON output as ground truth is a candidate for the same
self-refresh-at-point-of-use pattern, rather than relying on someone remembering to run it
or a scheduled task existing. Do NOT apply this pattern to EXPENSIVE manifests (full
backtest re-runs, OPRA re-fetches) — those genuinely need a scheduled cadence, not an
inline call on every read; the discriminator is "is regeneration itself cheap enough to
never be the bottleneck."

**Guard:** `backtest/tests/test_recency_check_self_refreshes_coverage.py` (4/4, RED-proofed).

**Candidate L#:** fold into C7 (Silent success is failure — audit outputs, not exit codes)
or C9 (anchor paths to `__file__`) family — closest existing precedent is the
`_shared.ps1` `wscript`-exit-code-masking lesson filed 2026-07-09/graduated 2026-07-18
earlier today (same session): a guard-generating mechanism whose OWN health nobody
verifies is a recurring shape in this codebase, not a one-off.
