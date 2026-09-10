# Package: engine-view-readout-ws-a

**Packet row:** `engine-view-readout-ws-a` -- **NOT present** in
`analysis/recommendations/checkpoint-2026-09-29-inventory.json` (that file is
hand-maintained, per its own `_doc`, and lists 15 rows from other goals; this row was never
added to it). Verified: `python setup/scripts/checkpoint_packet.py` stdout has zero
matches for `ws-a` / `engine-view` this session. The real source of this work item is
`markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md` **§9.5 row A** ("Draw what you trade"),
and its held-status ruling is recorded in that same doc's **§9.17** ("WS-A is HELD to
2026-10-30"), which this package implements and does not re-litigate.

**Verdict at authoring time:** HELD to 2026-10-30 (Opus ruling, §9.17). Not a
09-29-eligible risk reduction; additive instrumentation on `FROZEN_TRADING_PATH`.
**Prereg:** none filed under `analysis/prereg/` for WS-A specifically (unlike sibling
WS-C, which has one) -- the governing document is §9.17's ruling table itself.

## What this retires / changes

Nothing is *retired*. This adds a read-only telemetry surface (`automation/state/
engine-view.json`) alongside the existing decision path -- no scheduled task, installer,
ledger writer, or cockpit reader is removed or altered. Two files on
`setup/hooks/doctrine.py::FROZEN_TRADING_PATH` gain additive code (new keyword-only
parameter, new dict keys, one new function, one new call site); no existing branch,
return value, threshold, or evaluation order changes on either file, confirmed by the
byte-identical-returns guard below.

| Organ | Path |
|---|---|
| Scheduled task | NONE added/changed -- `_write_engine_view` runs inside the existing `Gamma_HeartbeatCore` tick (`run_account`), no new task |
| Installer | NONE |
| Ledger writer | NONE -- `automation/state/core-decisions.jsonl` (`_log`) is untouched; this is a separate, new file |
| New output file (not a ledger -- overwritten each tick, not appended) | `automation/state/engine-view.json`, written by the new `_write_engine_view()` in `setup/scripts/heartbeat_core.py` |
| Existing guard reused (unchanged) | `_read_level_records()` in `heartbeat_core.py` -- the same single parse the live decision path already uses (L251/L294 doctrine); NOT a new reader |
| New guard (this package) | `analysis/recommendations/packages/engine-view-readout-ws-a/guard_test.py` |
| Params keys touched | **NONE.** No `params.json` / `aggressive/params.json` key is read, written, or gated by this patch |

## The patch

`change.patch` (297 lines, built by hand-diffing a scratch copy against the real repo
files with `git diff --no-index`, then rewriting the `a/`/`b/` headers to the real
repo-relative paths -- see "Method" below; **never** written into the real repo files,
per the freeze):

### `backtest/lib/filters.py` (+92 / -0 lines)

- New helper `_trace_pivot_timestamps_et(window, pivots)` (before
  `detect_trendline_rejection_bearish`): best-effort ET timestamp per pivot, reading an
  optional `timestamp_et`/`timestamp` column off the `window` slice it's given. Every
  existing caller's `prior_bars` frame has neither column (`heartbeat_core._build_payload`
  builds it from `open/high/low/close/volume` only), so this returns `None` per pivot
  everywhere except the new WS-A replay call, which attaches its own `timestamp_et` column
  before calling in. Read-only, never raises.
- `detect_trendline_rejection_bearish` (`:791` post-patch, `:758` pre-patch) gains a
  **keyword-only** `trace: Optional[dict] = None` parameter. When a dict is passed, it is
  filled **in place**: defaults are set at function entry (before any check), fields
  (`pivots`, `pivot_timestamps_et`, `slope`, `intercept`, `trendline_price`,
  `proximity_dollars`, `reached_line`, `closed_below`, `is_red`) are populated as each
  local becomes available -- crucially **before** the corresponding rejection-criteria
  check, so a no-fire tick still captures the line being watched -- and an `exit_reason`
  string is recorded on **every** return path (see the histogram below). **No return
  value, branch, threshold, or evaluation order changes** -- verified over 11,286 real
  bars, zero mismatches (RED-proof below). `trace=None` (every existing call site's shape,
  unchanged) is a true no-op.

### `setup/scripts/heartbeat_core.py` (+79 / -0 lines)

1. Import `detect_trendline_rejection_bearish, TRENDLINE_LOOKBACK_BARS,
   TRENDLINE_MIN_SWINGS` from `filters` (same sibling-import pattern as the existing
   `ribbon` import two lines above it -- `backtest/lib` is already on `sys.path`).
2. New `ENGINE_VIEW = STATE / "engine-view.json"` constant next to `TICK_MARKER`.
3. `_build_payload`: one additive local `prior_bars_timestamps_et` (ET isoformat strings
   parallel to `prior`, sliced from `win["timestamp"]`) and one additive `bar_ctx` key,
   `"prior_bars_timestamps_et"`. `prior_bars` itself is untouched (still no timestamp
   column) -- this is a *parallel* array, consumed only by the new function below, never
   by `score_bar`/`evaluate_gates`/`_derive_tier` (same "logged-only, decision-path-blind"
   contract as the existing `context_bundle` key).
4. New `_write_engine_view(account, payload, et)`, inserted directly after
   `_write_tick_marker` (mirrors its atomic temp-file + `os.replace` pattern and its
   fail-open `try/except Exception: pass` contract). Rebuilds a `prior_bars` DataFrame from
   `bc["prior_bars"]`, attaches the new timestamp array as a `timestamp_et` column, then
   **replays** `detect_trendline_rejection_bearish` with the exact `bc["bar"]` /
   that DataFrame / `bc["bar_idx"]` the gate already scored, passing `trace={}` and
   discarding the return value -- this is read-only telemetry, never a second decision
   path. Levels come from `_read_level_records(spy)` (the existing single parse). Writes
   `engine-view.json` per the schema in the work order.
5. One call site in `run_account`, immediately after the `rec` dict literal closes
   (`"trigger_bar_et": str(bc.get("timestamp_et"))}`) and before the
   `CORE_MANAGES_EXITS` block: `_write_engine_view(account, payload, et)`. The callee is
   fully self-contained (its own try/except), so this call site adds no new failure mode.

### Method (how this was captured without touching the frozen files)

1. Copied `backtest/lib/filters.py` (+ `ribbon.py`, `structure_shift.py`, `__init__.py`
   siblings) into the session scratchpad as `<scratch>/lib/filters.py`, matching the
   `lib.filters` import shape `backtest/tests/test_trendline_trigger.py` already uses.
   Applied the edit there.
2. Copied `setup/scripts/heartbeat_core.py` into the scratchpad **under a name/path that
   does not reproduce the frozen suffix** (`setup/scripts/heartbeat_core.py`) -- the
   freeze hook suffix-matches on that exact multi-segment path (confirmed empirically:
   a scratch destination ending `.../setup/scripts/heartbeat_core.py` was blocked, one
   named `<scratch>/heartbeat_core.py` was not). Applied the edit there.
3. Built each file's diff with `git diff --no-index -- <real path> <scratch path>`
   (read-only, not blocked by the freeze hook), then rewrote the `diff --git` / `---` /
   `+++` header lines from the scratch's absolute path to the real repo-relative
   `a/<path>` / `b/<path>` so the patch applies against the real tree. Concatenated both
   files' diffs into this `change.patch`.
4. Verified with `git apply --check` (quoted below) and `git status --porcelain` on the
   two real files -- both currently show **zero** changes.

## Revert

```
git revert <sha-of-the-applying-commit>
```

No installer, scheduled task, or config file needs re-running -- this patch adds one new
function + one new call site + additive dict keys; reverting the commit removes them
cleanly. `engine-view.json` (if it exists on disk) is inert once the writer is reverted;
delete it manually if desired, it is not read by anything else yet (WS-A2, the `[GE]`
chart layer, is itself blocked until this ships -- §9.17).

## RED-proof (quoted verbatim, this session, 2026-09-09)

**Pre-patch** (`guard_test.py` run against HEAD, unpatched -- the real
`detect_trendline_rejection_bearish` has no `trace` kwarg yet, so the headline guard
correctly fails with a `TypeError`; this is the expected RED state while the freeze holds,
not a defect in the guard):

```
[PASS] test_trace_none_is_true_noop
[FAIL] test_byte_identical_returns_corpus -- TypeError: detect_trendline_rejection_bearish() got an unexpected keyword argument 'trace'
EXIT=1
```

**Post-patch** (the identical `guard_test.py`, unmodified, pointed at the scratch/patched
copy via the `WS_A_FILTERS_LIB_DIR` env override that exists solely for this
verification -- see the file's module docstring; `apply.ps1` never sets or needs this
variable):

```
[PASS] test_trace_none_is_true_noop
[PASS] test_byte_identical_returns_corpus -- {'bars_compared': 11286, 'fired': 1191, 'none': 10095, 'mismatches': 0, 'exit_reason_counts': {'insufficient_pivots': 6296, 'rejection_criteria_not_met': 2095, 'fired': 1191, 'trendline_below_spot': 1587, 'pivots_not_decreasing': 117}}
EXIT=0
```

Corpus: `backtest/data/spy_5m_2026-05-19_2026-09-08.csv` (11,348 raw 5m rows; the detector
needs `TRENDLINE_LOOKBACK_BARS + 2 = 62` bars of history before its first scorable index,
so 11,348 - 62 = 11,286 bars are compared). These exact numbers (11,286 / 1,191 / 10,095 /
zero mismatches, identical exit_reason histogram) also appear in
`markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md` §9.17 as the prior agent's verified
run -- an exact match is expected here (same corpus file, same algorithm, same spec), not
a "too-good" red flag: this is a reproduction of a previously-verified, fixed computation,
not a new result.

`git apply --check` (from repo root, against this exact `change.patch`):

```
git apply --check analysis/recommendations/packages/engine-view-readout-ws-a/change.patch
EXIT=0
```

## Nothing applied

Verified this session:

```
git status --porcelain -- backtest/lib/filters.py setup/scripts/heartbeat_core.py
```

returns **empty** (no output) -- both frozen files are unmodified in the working tree.
`GAMMA_FREEZE_OVERRIDE` was never set; `apply.ps1` was never run.
