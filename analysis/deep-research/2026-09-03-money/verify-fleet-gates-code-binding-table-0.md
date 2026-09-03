# VERIFY (CODE-PATH lens): G1 code truth table (fleet-gates-code-binding-table)

Stamp: 2026-09-03T14:31 ET (market hours). Read-only re-trace of every load-bearing claim
against source and ledger data, fresh this session. Target: [`fleet-gates-code-binding-table.md`](fleet-gates-code-binding-table.md) / [`.json`](fleet-gates-code-binding-table.json).

## Verdict: SUPPORTED — confirmed, not refuted

Every quoted line, branch condition, config value, and ledger row I re-traced independently
matched the finding exactly. I could not find a single misquote, wrong line reference, or
unsupported binding claim among the ~20 discrete factual assertions checked. This is the rare
case where the skeptic pass comes back clean.

## What I re-traced myself (source, not the report's quotes)

**The central branch** — `fleet_executor.py` `plan_all`, read fresh:
```python
if signal.get("strategies") is not None:
    plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
else:
    src = _perception_for_arm(signal, arm)
```
Matches the report's quote verbatim. `_perception_for_arm` (lines 108-122) does exist and does
implement safe/bold role routing — but only 3 call sites total: line 153 (unreachable `else`
branch of `plan_all` itself), line 936 (same `else` branch), line 1543 (`run_dry`, whose own
docstring says "one-shot CLI/demo evaluation" — not the live path `fleet_live.py` uses). I
confirmed this third site independently; the report flagged it as "located but not traced,"
which undersells slightly — it's a demo/dry-run function, not a live entry point, so the
role-router is dead on the ONLY path that places real orders, not merely "unverified."

**Why the `if` branch is always taken in production** — traced end to end, not assumed:
- `EMIT_STRATEGIES = True` at `build_shared_signal.py:293` (verified — grep).
- `build()`'s `if __name__ == "__main__": s = build()` (verified, no args) → `emit_strategies`
  defaults to `None` → `do_strats = EMIT_STRATEGIES` = `True`.
- Every one of `build()`'s exit paths (blind/beacon fallback, no-row, and the main row-found
  path) sets `sig["strategies"]` when `do_strats` is true — confirmed by reading all three
  assignment sites (`:714`, `:739`, `:823`), never leaving the key absent.
- `SCHEDULED-TASKS.md`'s `Gamma_FleetExecutor` row (read directly, not from the report):
  "Two serial pure-Python steps: `build_shared_signal.py` derives ... `shared-signal.json` ...
  then `fleet_live.py` fans it to every active `fleet_rest` arm" — confirms `build_shared_signal.py`
  runs as its own process (hitting the `__main__` block, not some other emit_strategies=False
  call site) ahead of `fleet_live.py` every cycle, 09:31-16:01 ET.
- `fleet_live.py` loads the JSON file from disk (`json.loads(path.read_text(...))`, line 116)
  and calls `fx.plan_all(arm, signal, ...)` directly (lines 375, 996) — no intermediate that
  could strip the key.
- Live proof: today's on-disk `automation/state/fleet/shared-signal.json`, re-read this session
  at 14:31 ET, carries `"strategies": []` and `"written_at": "2026-09-03T14:31:03-0400"` —
  fresher than the report's own 14:22 cite, same conclusion.

**`_plan_from_strategies` and `_gate_check`** — read the full function bodies myself:
`_plan_from_strategies` (lines 721-774) iterates only `signal.get("strategies") or []`; no
reference to `signal["safe"]`/`["bold"]`/`["bear"]`/`["bull"]` anywhere in the function.
`_gate_check` (lines 599-620) reads only `arm.get("gate_override")` — `min_triggers`,
`require_confluence_or_sequence`, `min_setup_quality`. No role/safe/bold logic. Both match the
report exactly.

**GATE_KEYS / ACCOUNTS / run_account** — `heartbeat_core.py`, read fresh: the 19-key `GATE_KEYS`
list (lines ~184-197) is byte-identical to the report's quote. `ACCOUNTS` dict (lines ~146-149)
matches. `run_account` reads `cfg["params"]` directly (`json.loads(cfg["params"].read_text(...))`)
with no fleet `gate_override` merge — confirmed, no such merge exists anywhere in the function.

**Config divergence** — grepped both params files directly: `structure_veto_enabled: true` +
`block_bull_1100_1200: true` in `automation/state/params.json`; `structure_veto_enabled: false`
(explicit) and zero matches for `block_bull_1100_1200` in `aggressive/params.json`. Exact match.

**accounts.json per-arm profiles** — parsed the full JSON myself (not trusting the report's
table): safe-3 `gate_override={min_triggers:2, require_confluence_or_sequence:true}`,
exit_patch `{stop_mode:structure, profit_lock_mode:trailing}`; risky-1 full_send+min_triggers:2+
confluence, exit `{tp1_premium_pct:0.5, stop_mode:structure}`; risky-3 (retired)
`gate_override={min_triggers:1}` PLUS a separate `gate_params={hard_skip_verdicts:[]}` — the
report's claim that this is "a SEPARATE mechanism from gate_override" is correct: they are two
different top-level keys on the arm's record, confirmed by direct read. safe-2/bold-2 both
`gate_override={}`, `execution="mcp_heartbeat"` (not `fleet_rest`) — confirming the report's
claim that these two never enter `fleet_executor` at all. `probe_arm.arm_id="risky-3"`,
`enabled:true` — confirmed still naming the retired arm.

**Ledger verification — all 3 rows, re-pulled independently, not copy-checked against the
report's own quotes:**
1. `core-decisions.jsonl` `core_tick_id 2026-09-03T11:06:02.738610`: `account=safe` →
   `verdict:SKIP_BULL_1100_1200`; `account=bold` same tick → `verdict:ENTER_BULL,
   action:PLACED`, broker order `8a8c237c-...`, filled_avg_price `0.37`. Second tick
   `2026-09-03T11:21:02.576928`: `safe` → `verdict:SKIP_STRUCTURE_VETO` ("price structure is
   'downtrend'"); `bold` → `verdict:ENTER_BULL` but `action:SKIP_MIN_PREMIUM_FLOOR` on bold's
   OWN order (a different downstream strike). Both rows match the report's quotes exactly,
   field for field.
2. `automation/state/fleet/safe-3/decisions.jsonl` carries rows at these EXACT two
   `core_tick_id`s: `action:ENTER_BULL, placed:true`, broker order ids `8a8c237c-a1ba-...` and
   `d6d0b3f8-ccf0-...` — same ids as bold's core row for the first tick (safe-3 traded the SAME
   broker order bold's core account did — direct evidence of the strategies[]-from-bold swap
   landing in a real fleet fill, not just a code-path inference).
3. `automation/state/fills-ledger.jsonl` confirms both fills: `arm:safe-3`, order
   `8a8c237c-...`, `price:1.17`, `ts_et:2026-09-03T11:07:15...`; order `d6d0b3f8-...`,
   `price:0.74`, `ts_et:2026-09-03T11:22:07...`. Matches the report's "$1.17×5 ... $0.74×5"
   exactly.
4. `automation/state/fleet/risky-3/decisions.jsonl`'s last row: `core_tick_id
   2026-08-28T15:53:01.404946`, `ts_et 2026-08-28T15:54:06.143486-04:00` — confirmed via a
   direct Python parse of the last line (not grep), no rows after. Exact match.
5. `shared-signal.json`'s live `strategies` key — confirmed present today at a timestamp even
   fresher than the report's own cite.

**Git history** — reran both `git log -S` commands myself:
- `EMIT_STRATEGIES` in `build_shared_signal.py`: two hits, `667217a1` (2026-06-26, creates the
  file) and `24bc365c` (2026-07-20, unrelated dojo wiring). `git cat-file -e 667217a1^:...` →
  `fatal: ... exists on disk, but not in 667217a1^` — confirms the file did not exist before
  that commit. Same check on `fleet_executor.py` — also created in `667217a1`, confirmed.
- `strategies` in `fleet_executor.py`: `e3a44956` (2026-08-12) is indeed the commit with the
  FIX2-branch self-correction. Read the full commit message myself (not the report's excerpt):
  it opens "SELF-CORRECTION. The disarm I shipped earlier tonight in `strategies.fired()` was
  INERT ON THE LIVE PATH. `plan_all` branches on a top-level 'strategies' key; `build_shared_signal`
  ALWAYS emits one (:684) and the live shared-signal.json carries it, so production always takes
  the FIX2 branch and `fired()` is never called." — matches the report's characterization exactly,
  and is even more explicit than the excerpt quoted (it names the live shared-signal.json, not
  just the code default).
- `667217a1`'s full commit message, read myself: covers engine repairs, structure-veto, trendline
  tooling; contains the line "SAVE untracked new engine: heartbeat_core.py + sight_beacon.py
  (were never git-tracked)" — verbatim as quoted. The report's "bulk pre-existing commit"
  reading is correctly labeled INFERENCE (the untracked-files note is about two OTHER files, not
  build_shared_signal.py/fleet_executor.py themselves — the report does not overstate this).

**filters.py** — confirmed the docstring counts (10+1 bearish, 11+1 bullish), `min_triggers:
int = 1` default, `sweep_blocker_enabled: bool = False` default, both `vix_soft_mode` flags
default `False` — all read directly off the function signatures, matching exactly.

**finalize() gate ordering** — grepped and read the actual lines: `min_entry_premium` floor at
~1259-1270, `_fleet_params["pdt_gate_mode"] = "margin_pdt"` at line 1283 with the
"BLAST-RADIUS GUARD" comment immediately above at 1271, `fleet_settlement_gate_enabled` +
`check_settlement` call at 1383-1403. `max_same_day_roundtrips: 4` confirmed in both params
files, with doc-comments confirming the 2026-08-29 tighten-from-5 and dual consumer paths
(core cash_settlement + fleet finalize) exactly as the report states.

**Exit ownership** — `fleet_live.py` line 44: `import exit_actuator as ea  # noqa: E402  (the
tick-managed scale-out engine)` — unconditional import, exact text match. `heartbeat_core.py`
line 128: `CORE_MANAGES_EXITS = os.environ.get("GAMMA_CORE_MANAGES_EXITS", "0") == "1"` —
confirms the code-level default the report describes (mechanism-only, runtime value correctly
left unchecked/unclaimed by both the report and this verification).

## What I did NOT re-verify (same gaps the report already discloses)

- `GAMMA_CORE_MANAGES_EXITS`'s actual live process value (out of scope per this task's
  read-only/no-live-process constraint — same limitation the report states).
- Exhaustive grep of every commit message in repo history for an earlier undiscovered mention
  of role-blindness (the report's INFERENCE label on this point is appropriate, not a gap I can
  close in a bounded verification pass).
- `probe_arm` dispatch-gating-on-status beyond the `accounts.json` doc field itself — same as
  the report's own caveat.

## Assessment

This is a code-truth documentation task, and I re-derived the same truth independently: read
the branch condition myself, read the function bodies myself, re-pulled all 3 ledger rows
myself (one of them going one field further than the report — the safe-3 fill's broker order
id being the *same* id as bold's core-account order on the first tick, which is direct proof
the swap mechanism produced a real paper fill, not just a code-path inference), reran both git
log commands myself, and independently confirmed the config divergence and every arm's
`gate_override`/`params_patch`/`gate_params`. Nothing I checked contradicted the report. The
one place I'd tighten the report's own language: the `_perception_for_arm` call site at
`fleet_executor.py:1543` sits inside `run_dry`, a function whose own docstring calls it a
"one-shot CLI/demo evaluation" — so the safe/bold role router isn't merely "unreached on an
unverified path," it's dead code on every path that can place a real order, full stop. That
sharpens the finding; it does not weaken it.

**No refutation found.** `refuted=false`.
