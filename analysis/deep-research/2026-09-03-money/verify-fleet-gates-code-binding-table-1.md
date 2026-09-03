# VERIFY — G1 CODE TRUTH TABLE (fleet-gates-code-binding-table.md/.json)

Stamp: 2026-09-03 ~14:35-14:55 ET (market hours), read-only. Skeptic pass on the
`code-binding-table` finding. Independent script (imports nothing from the finding's own
tooling): `backtest/tools/fleetgates_verify_code-binding-table_1.py`. Companion data:
`verify-fleet-gates-code-binding-table-1.json`.

## Verdict up front

**NOT REFUTED — SUPPORTED, independently reproduced and extended.** Every source-code
citation (line ranges, exact quotes, git commit hashes/messages) was re-read fresh this
session and matches the finding verbatim. The ledger join was rebuilt from scratch (own
script, own join key, own pass/fail derivation) and reproduces the finding's exact 2
quoted `core_tick_id` rows byte-for-byte, plus surfaces **40 total divergence instances**
across history that the finding's 3-row sample did not claim to be exhaustive about (it
never claimed n=3 was the full count — it called them "3 ledger rows independently
re-read," which is accurate). No claim in the finding was contradicted.

---

## What I re-verified directly against source (not trusted from the finding)

| Claim | My check | Result |
|---|---|---|
| `build_shared_signal.py:293` `EMIT_STRATEGIES = True`, unconditional | `sed -n` read | MATCH — verbatim, plus confirmed `do_strats = EMIT_STRATEGIES if emit_strategies is None else ...` (line 673/1307) and that **every** code path in `build()` (main row, beacon-fallback, no-row, replay-no-row) sets `sig["strategies"]` when `do_strats` is true — a list, never absent. This is a stronger confirmation than the finding gave (it cited 3 line numbers for the empty-list case; I read all 4 branches). |
| `sig["strategies"]` swap logic (lines ~805-823) | `sed -n` read | MATCH — `s_bear, s_bull = bear, bull` then swapped to `bold.get(x) or y` together whenever bold passed *either* side. Confirmed both-swap-together behavior and the "neither passes -> stays safe" fallback via a live example (below). |
| `fleet_executor.py:933-936` `plan_all` branch (`if signal.get("strategies") is not None`) | `sed -n` read | MATCH verbatim. |
| `_perception_for_arm` (fleet_executor.py:108-122) role router, called only in the dead `else` branch | `sed -n` read | MATCH verbatim, including the exact fallback logic. |
| `_plan_from_strategies` (~721-774) never reads `signal['safe']`/`['bold']`/`['bear']`/`['bull']`, never calls `_perception_for_arm` | full read | MATCH — confirmed by reading the whole function body, not just the summary. |
| `_gate_check` (~599-620) reads only `min_triggers`/`require_confluence_or_sequence`/`min_setup_quality`, no role logic | full read | MATCH verbatim. |
| GATE_KEYS list (heartbeat_core.py:184-197), 19 keys | `sed -n` read | MATCH verbatim, byte-identical list including the comment about `structure_shift_confirmation_enabled` being listed-but-inert. |
| `params.json` has `structure_veto_enabled:true`/`block_bull_1100_1200:true`; `aggressive/params.json` has `structure_veto_enabled:false` explicit, `block_bull_1100_1200` absent | `grep` both files | MATCH — same line numbers, same doc-comment text (the "25,821 ledger rows... 116 times... ZERO times for bold" quote is verbatim in the file). |
| filters.py filter counts: 10 bear + sweep = 11; 11 bull + sweep = 12 | read both docstrings | MATCH — docstring text matches the finding's paraphrase closely (finding says bear docstring is "1-18" listing 10 filters, my read of the actual numbered list confirms 10 numbered + sweep as filter 11 elsewhere in the body, consistent). |
| Git: `build_shared_signal.py` did not exist before `667217a1` | `git cat-file -e 667217a1^:...` | MATCH — `fatal: ... exists on disk, but not in 667217a1^` reproduced exactly. |
| Git: `667217a1` commit message never mentions build_shared_signal/fleet, and separately notes "SAVE untracked new engine: heartbeat_core.py + sight_beacon.py (were never git-tracked)" | `git log -1 --format=%B 667217a1` | MATCH — quote reproduced exactly. |
| Git: `e3a44956` "SELF-CORRECTION... INERT ON THE LIVE PATH... fired() is never called" | `git log -1 --format=%B e3a44956` | MATCH — quote reproduced exactly (finding's JSON quotes a slightly trimmed version; full message confirms the same claim, plus additional detail about a second/third bug in the same commit not mentioned by the finding — omission, not a distortion). |
| Live `shared-signal.json` carries `strategies` key | fresh `json.load` this session (14:33 ET tick) | MATCH — key present, type `list`, `[]` on this no-fire tick, `written_at: 2026-09-03T14:33:02-0400`. |
| No live arm carries `gate_override.score_ladder_floor`; `full_send` is risky-1-only and orthogonal to `_gate_check` | `grep` accounts.json | MATCH — doc fields confirm both claims verbatim. |

One thing the finding flagged as "not traced further" — `fleet_executor.py:1543`'s second
`_perception_for_arm` call site — I did trace it this session (finding explicitly left it
open, so this is an extension, not a correction): it lives in a **premium-estimation
fallback** inside the plan-to-order path, used only when the chosen strategy entry lacks an
`est_premium` field in `signal["strategies"]`. It supplies a WATCH-mode risk-gate premium
estimate, not an entry gate — it does not reintroduce role-awareness into whether an arm
enters. This closes the finding's own flagged gap in the finding's favor.

---

## Independent ledger rebuild — method

Script `backtest/tools/fleetgates_verify_code-binding-table_1.py` (own code, no import from
the finding's scripts):

1. Load `automation/state/core-decisions.jsonl` (37,979 rows), index by `core_tick_id` ->
   `{account: row}` — 9,167 distinct ticks, **zero duplicate (tick, account) pairs**.
2. Load each fleet arm's `decisions.jsonl` (safe-3/risky-1/risky-3), filter to rows whose
   `action` starts with `ENTER_`.
3. For each such row with a `core_tick_id` that joins to a tick carrying both a `safe` and
   a `bold` core row: compute `safe_passed = (safe_row.verdict == "ENTER_<SIDE>")` and
   `bold_passed = (bold_row.verdict == "ENTER_<SIDE>")` (verdict, not action — matches the
   finding's own documented distinction, confirmed live: bold rows can carry
   `verdict:ENTER_BULL, action:SKIP_MIN_PREMIUM_FLOOR` and still count as passed for the
   shared-signal swap).
4. Flag a **divergence join**: `not safe_passed AND bold_passed` — i.e. the exact mechanism
   the finding names: safe's own core row blocked this side, bold's independently passed
   it, and the fleet arm entered on that identical tick.
5. Cross-check each divergence join against `fills-ledger.jsonl` via the entry row's
   `placement.broker.id`.
6. `core_tick_id` only exists on fleet-arm rows from **2026-08-03 onward** (9,012/12,600
   safe-3 rows carry it; earlier rows are pre-instrumentation and are correctly excluded,
   not silently miscounted as "no divergence"). All 4 named winning days (08-06/13/27/28)
   and the full September window fall inside this joinable range.

## Independent ledger rebuild — results

| Arm | ENTER rows | Joinable (has core_tick_id + core pair) | Divergence joins | Fills confirmed |
|---|---|---|---|---|
| safe-3 | 91 | 58 | **13** | 13/13 |
| risky-1 | 149 | 115 | **17** | 16/17 |
| risky-3 | 149 | 101 | **10** | 9/10 |
| **Total** | 389 | 274 | **40** | 38/40 |

(The 2 unconfirmed fills are HOLD-adjacent edge cases — the entry row exists with
`placed:true` but no matching `broker.id` was carried in that row's `placement` block on
inspection; not investigated further, flagged as a minor gap, does not change the
mechanism conclusion.)

**`safe_verdict` reason breakdown (union across arms):** `SKIP_BULL_1100_1200`: 29,
`SKIP_STRUCTURE_VETO`: 9, `SKIP_DOJI_ENTRY_BAR`: 2. Both of the two flag-named GATE_KEYS
cohort gates the finding calls out (`block_bull_1100_1200`, `structure_veto_enabled`)
dominate the count, consistent with the finding's mechanism claim (these are exactly the
two gates the finding's ledger section quotes).

**The 2 exact `core_tick_id` rows the finding quoted verbatim** (`2026-09-03T11:06:02.738610`,
`2026-09-03T11:21:02.576928`) were independently re-derived by my script from a cold
re-read of the ledgers — `safe` verdict/action/reason, `bold` verdict/action/reason, both
fleet arms' `ENTER_BULL` rows, strike/qty/premium, and matching fills at 11:07:15 ($1.17×5)
and 11:22:07 ($0.74×5) — **all fields match the finding's quotes exactly.**

### Concentration disclosure (STANDARD requirement)

40 divergence instances span **10 distinct trading days**, not concentrated in one session:
08-04(6), 08-07(3), 08-11(1), 08-12(3), 08-13(3), 08-19(3), 08-21(10), 08-27(3), 09-02(4),
09-03(4). Top-1 day (08-21) = 10/40 = 25%. Top-3 days (08-21+08-04+one of the 4-count days)
= 20/40 = 50%. **Drop-best-day** (remove 08-21): 30/40 = 75% remains across 9 other days —
the mechanism is not a single-day artifact.

### The 4 named winning days, checked individually

| Day | Divergence instances (any arm) | What actually happened |
|---|---|---|
| 2026-08-06 | 0 | 1 fleet ENTER_BEAR fired (risky-1/risky-3), but **safe's own core row already said `ENTER_BEAR` too** — no gate blocked safe on that tick, so no divergence is expected here. (Side detail: bold's own core row was `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`, a hard-skip verdict, on this exact tick — confirming the finding's "neither bold side passes -> strategies[] stays sourced from safe" branch of its own swap-logic table, live.) |
| 2026-08-13 | 3 (safe-3, risky-1, risky-3 each 1) | `SKIP_BULL_1100_1200` on safe, `ENTER_BULL` on bold, all 3 fleet arms entered, all 3 fills confirmed. |
| 2026-08-27 | 3 (safe-3, risky-1, risky-3 each 1) | Same pattern as 08-13, `SKIP_BULL_1100_1200`, all 3 fills confirmed. |
| 2026-08-28 | 0 | 6 fleet ENTER rows fired across the 3 arms that day, but **safe's own core row agreed (`ENTER_BULL`/`ENTER_BEAR`) on every one of those ticks** — verified directly against `core-decisions.jsonl` for all 6 `core_tick_id`s. No gate blocked safe on any of them, so — correctly — no divergence. |

**This is not a gap in the finding.** The finding never claimed the mechanism fires on
every winning day — it demonstrated the mechanism exists and gave live 09-03 proof. Two of
the four winning days (08-06, 08-28) simply didn't contain a tick where safe was gated and
bold wasn't; the mechanism is silent (a no-op, by construction) whenever safe and bold
already agree, which is most of the time. That two winning days show zero divergence is
consistent with, not contrary to, "the leak is real but partial" — see also the companion
`fleet-gates-ledger-binding-check.md` (G2, same session-cluster), which independently
computed the leak rate at ~6-22% of qualifying (gated) ticks depending on arm/direction —
my count-based join and that percentage-based join are different methodologies measuring
the same mechanism and do not conflict.

### September window (2026-09-01..today)

8 divergence instances across 3 days (09-02: 4, 09-03: 4), all with confirmed fills, all
`SKIP_BULL_1100_1200` (2) / `SKIP_STRUCTURE_VETO` (2) on 09-03 and `SKIP_BULL_1100_1200`
(4) on 09-02. Full detail in the JSON companion.

### Retirement enforcement (risky-3)

Independently confirmed: **0 rows on or after 2026-08-29**; last row
`2026-08-28T15:54:06.143486-04:00` — matches the finding's quoted
`core_tick_id 2026-08-28T15:53:01.404946 / ts_et 2026-08-28T15:54:06` exactly (my check
used `ts_et`, same value to the second).

---

## Disagreements found

**None.** Every line citation, quote, commit hash, ledger row, and mechanism claim in the
finding was independently reproduced from a cold read of the same files this session. The
40-instance/10-day count is a genuine **extension** (the finding sampled 3 rows and called
them representative of a real, live mechanism — it never claimed n=3 was exhaustive), not a
correction.

## What I did not (re)verify

Same scope boundary as the finding, for the same reason (read-only, no live process/env
inspection permitted): `GAMMA_CORE_MANAGES_EXITS`/`GAMMA_CORE_ARMED` runtime values.
`probe_arm`'s dispatch-gating-on-arm-status claim (accounts.json doc field only, not
re-traced through `fleet_live`/`run_dry` code this session either). The `667217a1`
"bulk pre-existing commit" INFERENCE (I did not run a reflog/stash search to try to recover
an earlier working-tree state — same limitation the finding itself disclosed). I did not
independently re-derive the G2 companion's percentage-based leak rate (6-22%) — I only
confirmed my count-based numbers do not contradict it.

## FACT vs INFERENCE

**FACT** (re-derived from a cold read this session): every source-line quote in the table
above; both git-history quotes; all 40 ledger divergence-join rows (own join, own script);
the 2/4/38-of-40 breakdown; risky-3's retirement enforcement; live shared-signal.json state.

**INFERENCE**: none introduced by this verification pass beyond what the finding already
labeled as inference (the `667217a1` bulk-commit reading).
