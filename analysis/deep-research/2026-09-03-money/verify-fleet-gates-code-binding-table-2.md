# VERIFY (skeptic pass #2): G1 code truth table — fleet-gates-code-binding-table

Stamp: 2026-09-03T14:34 ET (market hours, read-only). Verifier for `fleet-gates-code-binding-table.json/.md`, dated 2026-09-03T14:30 ET. LENS: CONSEQUENCE — does this change what the go-live gate measures, or what a 09-29 kill-type change would do; recompute any dollar effect with top-3 contributors removed.

## Verdict: NOT REFUTED — mechanism claims independently confirmed byte-for-byte. One interpretive claim (git-history "side effect, not stated intent") is weakened by a directly relevant doc the report didn't check. CONSEQUENCE lens: does not change what the go-live gate measures; does meaningfully change what a 09-29 GATE_KEYS-targeted kill-type change would do (nothing, to fleet arms); the finding carries no dollar claim of its own, and the one dollar-bearing artifact adjacent to it (bypass-cohort P&L) does NOT survive top-contributor removal — which is the right reason the finding stayed INSTRUMENT_ONLY.

---

## What I independently re-verified (fresh reads this session, not carried over)

Every quoted code line, every ledger row, and every git commit message in the finding was re-pulled from source and matched **exactly**:

| Claim | Check | Result |
|---|---|---|
| `fleet_executor.py:933-936` branch text | `sed -n '925,940p'` | Verbatim match, including `if signal.get("strategies") is not None:` |
| `build_shared_signal.py:293` `EMIT_STRATEGIES = True` | `sed -n '285,300p'` | Verbatim match, doc-comment included |
| `heartbeat_core.py:184-197` `GATE_KEYS` list | `sed -n '178,200p'` | Verbatim match, 19 keys |
| `sig["safe"]`/`sig["bold"]`/`sig["strategies"]` construction | `sed -n '575-630p'`, `800-830p'` | Verbatim match — `_bold_passed_blocks_from_row` uses `_score_peak_check`, no `GATE_KEYS` reference anywhere in it |
| `sig["strategies"]` never absent (only `[]` or built) | `grep -n '"strategies"'` across the file | 5 assignment sites, all `[]` or `_strategies_block(...)`, none `None`/omitted; `do_strats` defaults to `EMIT_STRATEGIES` unless a caller passes `emit_strategies=False` |
| No live caller overrides `emit_strategies=False` | `grep -rn emit_strategies` across `automation/state/fleet/` + `setup/` | Only test files (`test_fix2_strategies_emit.py`, `test_build_from_rows_replay.py`, `test_probe_arm.py`, `test_structure_stop_wiring.py`) pass it explicitly; `fleet_live.py` does not — confirms the branch is unconditionally live-taken, not just true-by-construction in theory |
| `accounts.json` gate_override/status table (safe-3, safe-2, safe-1, risky-1, risky-3, bold-2) | Full JSON parse | All 6 rows match the report's table exactly, including risky-3's `gate_params.hard_skip_verdicts: []` and bold-2's empty `{}` |
| `git log -S"EMIT_STRATEGIES"` + file-non-existence-before-667217a1 | `git log -S`, `git cat-file -e 667217a1^:...` | Confirmed: file didn't exist pre-commit, commit message is entirely about engine repairs and structure-veto, never mentions `build_shared_signal.py` |
| `e3a44956` commit message ("SELF-CORRECTION... INERT ON THE LIVE PATH") | `git log -1 --format=%B e3a44956` | Verbatim match |
| `go_live_gate.py` criterion 5 reads `prod-shadow-designation.json` naming safe-3 | Direct read of both files | Confirmed: `arm: "safe-3"`, window 2026-09-01..2026-10-30, min_days=20 |
| Ledger row 1: same-tick safe/bold divergence + safe-3 riding bold, both core_tick_ids | Fresh `core-decisions.jsonl` + `safe-3/decisions.jsonl` parse | Exact match: `SKIP_BULL_1100_1200`/`ENTER_BULL` and `SKIP_STRUCTURE_VETO`/`ENTER_BULL` at the two cited `core_tick_id`s; safe-3 rows carry `action:ENTER_BULL` at both |
| Broker order ids + fills | `fills-ledger.jsonl` grep for `8a8c237c`/`d6d0b3f8` | Exact match: fills at 11:07:15 ET $1.17×5 and 11:22:07 ET $0.74×5, same order ids appear in `safe-3/decisions.jsonl`'s `placement.broker.id` |
| risky-3 retirement live-enforced | Full parse of `risky-3/decisions.jsonl` (11,146 rows) | Last row `core_tick_id 2026-08-28T15:53:01.404946`, nothing after — confirmed |
| Live `shared-signal.json` carries `strategies` key today | Fresh parse, 14:34 ET | `strategies: []` (list, len 0) present, `written_at: 2026-09-03T14:34:02-0400` |
| `fleet_live.py` unconditional `exit_actuator` import; `heartbeat_core.py` `GAMMA_CORE_MANAGES_EXITS` env-gate | grep | Confirmed both shapes exactly as described |

I found **zero factual discrepancies** in the mechanism trace. This is one of the more thoroughly source-verifiable findings I've reviewed — nearly every load-bearing sentence is a direct quote checkable against a specific file:line, and all of them check out.

---

## The one real crack: the "side effect, not stated intent" interpretive claim

The report's git-history section investigates whether role-blind `strategies[]` sourcing (the mechanism that makes `GATE_KEYS` unreachable for fleet arms) was **stated design intent** or a **side effect** discovered later. It searches `build_shared_signal.py` (`EMIT_STRATEGIES`) and `fleet_executor.py` (`strategies`) history and concludes: the narrow disarm-bug fix (`e3a44956`, "SELF-CORRECTION... discovered while debugging vwap_continuation") documents the *mechanical* fact but not as a *planned design review* of the broader consequence — verdict "side effect, not stated intent."

I checked one thing the report didn't: `accounts.json`'s own top-level `_doc` field, introduced in **the same originating commit** (`667217a1`, 2026-06-26 14:15:44 -0600 — same commit that created `build_shared_signal.py`/`fleet_executor.py` wholesale, confirmed via `git log -S"AN ACCOUNT IS NOT A STRATEGY"`). It reads, verbatim:

> "AN ACCOUNT IS NOT A STRATEGY. Every account is a (gate-strictness x contract-sizing) profile; EVERY validated strategy in `automation/state/fleet/strategies.py` runs on EVERY account via `fleet_executor.plan_all`. The account only decides how SELECTIVE the entry gate is (`gate_override`) and how BIG the position is (sizing...). NO direction locks, NO per-account strategy silos (the old PUT_ONLY / loose-aggressive-as-a-strategy framing was the bug J flagged)."

This is a **direct, contemporaneous, on-point statement of design intent** — from the exact commit the report was already examining for other reasons — that fleet arms are meant to run the SAME shared signal and differentiate ONLY through `gate_override` (a documented, separate selectivity axis from `GATE_KEYS`) and sizing. It doesn't prove the author *foresaw* the specific consequence that `structure_veto_enabled`/`block_bull_1100_1200` etc. would be permanently unreachable for fleet arms — but it does show the *shape* of that consequence (fleet arms use `gate_override`, not a copy of a core account's own params-file cohort gates) was written down as the intended design on day one, not discovered as an accident eight weeks later. This softens — without overturning — the report's "never stated as intent anywhere found in this repo's tracked history" line. I'd call this a **partial correction to one interpretive sentence**, not a refutation of the mechanism trace, which stands.

---

## CONSEQUENCE lens

### 1. Does this change what the go-live gate is measuring?

**No.** Read `go_live_gate.py::prod_shadow_criterion` (criterion 5) directly: it pulls `engine_rows` for the designated arm (`safe-3`) over the designated window, computes `days_scored` (a scored day requires a fill), and runs `statistical_criterion()` — a bootstrap CI on **realized, as-traded, cost-adjusted P&L**. It does not inspect *why* an entry fired, does not read `GATE_KEYS`, does not distinguish a bypass-sourced fill from a both-perceptions-passed fill. Criterion 5 is outcome-based and mechanism-agnostic by construction. This finding correctly does not claim otherwise (`change_class: INSTRUMENT_ONLY`), and that framing is right: the mechanism trace explains *how* safe-3's realized trades came to exist, but doesn't change what the gate computes from them.

### 2. Does this change what a 09-29 kill-type change would do?

**Yes, materially, and the finding is the correct instrument for catching this in advance.** If a future session — reading only `CLAUDE.md`'s "arms are risk profiles, not strategies... differ ONLY by sizing, gates, and stop" doctrine — proposed a 09-29 kill-type reduction that tightens `structure_veto_enabled`, `block_bull_1100_1200`, or any other `GATE_KEYS` flag in `params.json`/`aggressive/params.json` with the intent of also tightening safe-3/risky-1's live entries, that change would do **nothing** to those arms: confirmed above, `GATE_KEYS` is read only inside `run_account`'s `gate_params` construction, a core-account-only path never touched by `fleet_executor._plan_from_strategies`. The only levers that actually bind a fleet arm are (a) engine_cli's scoring filters (shared, not per-role) and (b) the arm's own `accounts.json.gate_override` (`min_triggers`/`require_confluence_or_sequence`/`min_setup_quality`). This is a real, previously-undocumented gap between doctrine and mechanism that the finding correctly surfaces and correctly declines to "fix" under the current freeze — its `proposed_change` section names the two structurally different repair shapes (route `plan_all` per-arm, or stop the bold-swap in `build_shared_signal`) and correctly defers both to a post-09-29 prereg.

### 3. Dollar effect, top-3 contributors removed

The finding under review makes **no dollar claim** (`change_class: INSTRUMENT_ONLY`, explicitly: "no arm's gates or sizing were touched; no winners are at risk from this deliverable itself") — so there is, strictly, no dollar figure in this finding to invalidate by stripping contributors. That restraint is the correct call, and I checked why: the sibling artifact in the same directory, `fleet-gates-bypass-cohort-pnl.json` (a parallel session's P&L attribution of exactly this mechanism — "cohort A bypass" = safe gated, arm entered anyway riding bold's looser pass), which this report explicitly flagged as *not reconciled*, contains the dollar figures a "so is the bypass actually helping" question would need. I read it and recomputed:

| Arm | Cohort-A-bypass n / days | Total P&L | Top-3-gross-win concentration | P&L with best day dropped |
|---|---|---|---|---|
| safe-3 | 13 trades / 8 days | **+$752** | 85.7% of gross wins in top 3 | **-$188** |
| risky-1 | 16 trades / 10 days | **+$104** | 77.2% | **-$553** |
| risky-3 | 9 trades / 6 days | **-$823** | n/a (0 wins) | -$783 (already negative) |

For safe-3 and risky-1, the entire bypass cohort's positive P&L is carried by **one day each — both times 2026-09-03, today**, and specifically by 2 trades on that single day (safe-3: $507+$433=$940; risky-1: $343+$314=$657, matching `best_day_pnl` exactly). Stripping the top 3 winning trades outright (`top3_win_dollars`) rather than just the best day pushes safe-3's cohort to **-$491** and risky-1's to a loss as well. risky-3's bypass cohort is negative even including its best day. None of the three arms shows a bypass-cohort edge that survives removing its top contributor(s) — the September-2026 go-live-gate window itself (2 trading days scored so far) shows the identical pattern (`september_window.A_bypass`: safe-3 +$802 total, -$138 with best day dropped; risky-1 +$432, -$225 dropped).

**Conclusion under this lens: the mechanism claim survives (it's a code fact, not a P&L claim); a dollar-bearing argument built on top of it would not.** If a future session reads this finding and the adjacent bypass-cohort file together and concludes "the safe/bold role-blindness is quietly making money, leave it," that conclusion is refuted by the same evidence base — the apparent edge is a 1-2-trade artifact from the current session's own trading, not a robust pattern. This is exactly the caution the finding's own `caveats` field gestures at when it flags the unreconciled companion file, and the reconciliation now done here confirms flagging it (rather than either ignoring it or leaning on it) was the right call.

---

## Facts vs inference in this verification

**FACT** (re-verified against live source/ledgers this session): every table row in the "What I independently re-verified" section above; the bypass-cohort P&L figures quoted (direct read of `fleet-gates-bypass-cohort-pnl.json`, not recomputed from raw ledgers — I did not re-derive cohort membership or P&L matching independently, only re-transcribed and re-summed the file's own numbers, so this is a re-check of that file's internal arithmetic and its consistency with the code-binding-table's claims, not an independent re-run of its join logic against `core-decisions.jsonl`/`pain-ledger`).

**INFERENCE**: that `accounts.json`'s "AN ACCOUNT IS NOT A STRATEGY" doc constitutes intent specifically for the `GATE_KEYS`-unreachability consequence (it documents the *shape* — gate_override/sizing as the only axes — not a foreseen statement about `structure_veto_enabled` by name).

**UNVERIFIED / out of scope this session**: did not independently re-run `fleet-gates-bypass-cohort-pnl.json`'s join logic against `core-decisions.jsonl`/`analysis/pain-ledger/mae-mfe.json` from scratch; did not read `fleet-gates-design-intent.md/.json` or `fleet-gates-ledger-binding-check.md/.json` (the other unreconciled companions) for consistency; did not check `GAMMA_CORE_MANAGES_EXITS`'s live runtime value (same read-only/no-live-process constraint the original report cites).
