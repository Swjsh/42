# VERIFY — fleet-gates-ledger-binding-check.md (CODE-PATH lens)

Stamp: 2026-09-03, ~14:20-14:45 ET (market hours), read-only. Re-traces the claimed
binding/non-binding mechanism directly from `automation/state/fleet/fleet_executor.py` and
`automation/state/fleet/build_shared_signal.py` source, re-derives the ledger join
independently, and **executes the actual production functions** (`_map_core_row`,
`_bold_passed_blocks_from_row`) against the report's own quoted `core_tick_id`s to check
whether the swap the report describes actually fires on those exact ticks.
Script: `backtest/tools/fleetgates_verify-ledger-binding-check.py` (read-only, <10s).

## Verdict: REFUTED (partial) — Table A confirmed, Table B's stated mechanism is wrong

**Table A and the core branch-selection mechanism are CONFIRMED, byte-for-byte, by direct code
read and direct code execution.** But **Table B's headline claim — that `SKIP_CONF_LVL_REC_AFTERNOON`
is a "safe-cohort" gate leaking via the "default, undiluted" no-swap path — is REFUTED by running
the actual production code against the report's own two quoted `core_tick_id`s for that gate.**
The swap the report says does NOT happen on Table-B ticks in fact DOES happen on both examples I
tested. The report's "Is the sourcing symmetric — NO" causal explanation is real for one of its
three cited gates (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`, the hard-skip case) and wrong for the
other (`SKIP_CONF_LVL_REC_AFTERNOON`, the report's own "strongest single finding" and headline
example).

---

## Part 1 — CONFIRMED: branch selection, GATE_KEYS, and Table A's mechanism

### 1a. `fleet_executor.plan_all` branch selection — confirmed exact

Read directly (`automation/state/fleet/fleet_executor.py:933-935`):

```python
if signal.get("strategies") is not None:
    plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
else:
    src = _perception_for_arm(signal, arm)
```

`_plan_from_strategies` (lines 721-774) iterates `signal.get("strategies") or []` and applies
only `_gate_check` (lines 598-620: `min_triggers`, `require_confluence_or_sequence`,
`min_setup_quality` — no safe/bold role, no reference to any `params.json` GATE_KEYS name) plus
sizing. Matches the target report's and `veto-scope-safe-3.md`'s premise exactly.

### 1b. `EMIT_STRATEGIES = True` and the safe-default/bold-override swap — confirmed exact

`build_shared_signal.py:293`: `EMIT_STRATEGIES = True`. The swap (`build_shared_signal.py`,
inside `build()`, ~line 811-816):

```python
s_bear, s_bull = bear, bull
if use_peak:
    bold = sig.get("bold") or {}
    if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
        s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
```

`bear`/`bull` (the default) come from `row = _latest_today_decision(today, core_tick_id=_core_tick_id)`
— default `account="safe"` (signature at line 238) — confirmed.

### 1c. GATE_KEYS — confirmed exact match to established context

`setup/scripts/heartbeat_core.py:184-197`, read directly, byte-matches the list already given in
context (`block_level_rejection` ... `structure_shift_confirmation_enabled`, 18 keys).
`_gate_check` (fleet_executor.py) never reads any of these — confirmed no cross-reference in the
whole `_plan_from_strategies`/`_gate_check` code path.

### 1d. Table A's numeric join — independently reproduced, EXACT match

Re-ran the ledger join from scratch (my own script, not the target's):

```
TABLE A (safe gated, bold entered), n=133
  safe-3:  11/133 = 8.27%   (report: 11, 8.3%)  MATCH
  risky-1: 15/133 = 11.28%  (report: 15, 11.3%) MATCH
  risky-3: 8/133  = 6.02%   (report: 8, 6.0%)   MATCH
```

### 1e. Table A's causal mechanism — confirmed by EXECUTING the actual production functions

Imported `automation/state/fleet/build_shared_signal.py` directly and ran `_map_core_row` +
`_bold_passed_blocks_from_row` against the raw ledger rows for all 4 of the report's quoted Table
A `core_tick_id`s. All 4 confirm `SWAP OCCURS: True` — bold's block (`bull_score=11`,
`score_peak_passed=True`) becomes `s_bull`, safe's `SKIP_STRUCTURE_VETO`/`SKIP_BULL_1100_1200`
block never reaches `sig["strategies"]`:

```
2026-08-07T12:36:02.451616  safe=SKIP_STRUCTURE_VETO  bold verdict=ENTER_BULL (action=RISK_DENY_PDT)
  bold_passed.bull.passed=True  SWAP OCCURS: True
2026-08-21T13:34:02.490082  safe=SKIP_STRUCTURE_VETO  bold verdict=ENTER_BULL (action=SKIP_MIN_PREMIUM_FLOOR)
  bold_passed.bull.passed=True  SWAP OCCURS: True
2026-09-03T11:21:02.576928  safe=SKIP_STRUCTURE_VETO  bold verdict=ENTER_BULL (action=SKIP_MIN_PREMIUM_FLOOR)
  bold_passed.bull.passed=True  SWAP OCCURS: True
2026-08-13T11:41:02.990155  safe=SKIP_BULL_1100_1200  bold verdict=ENTER_BULL (action=PLACED)
  bold_passed.bull.passed=True  SWAP OCCURS: True
```

**Table A and its mechanism narrative are CONFIRMED — FACT, code-executed, not just read.**

---

## Part 2 — REFUTED: Table B's "safe-cohort gate" framing and stated mechanism

### 2a. `SKIP_CONF_LVL_REC_AFTERNOON` and `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` are BOLD-configured
gates, not safe-cohort gates — the opposite polarity of what the report's Method section implies

The report's Method section lists these two gates alongside `SKIP_STRUCTURE_VETO`/
`SKIP_BULL_1100_1200` as the "four gates [that] map by name directly to the `params.json`
GATE_KEYS this queue item cares about" — implying all four are the same kind of safe-side
cohort restriction. Direct read of both config files (independently, not quoted from any prior
doc) shows the reverse for Table B's two gates:

| GATE_KEYS key | safe (`automation/state/params.json`) | bold (`automation/state/aggressive/params.json`) |
|---|---|---|
| `structure_veto_enabled` | `true` | `false` |
| `block_bull_1100_1200` | `true` | `<absent>` |
| `block_conf_lvl_rec_afternoon` | **`<absent>`** | **`true`** (line 162) |
| `require_bearish_fill_bar` | **`<absent>`** | **`true`** |

Table A's two gates (structure_veto, bull_1100_1200) are genuinely safe-only. Table B's two
gates (conf_lvl_rec_afternoon, bearish_fill_bar) are genuinely **bold-only** — safe never applies
them at all. Calling Table B "the mirror" of Table A and citing `block_conf_lvl_rec_afternoon` as
the finding's headline example of a leaking cohort gate is a mischaracterization: this gate was
never a restriction on safe or safe-tier fleet arms to begin with. (`aggressive/params.json:163`'s
own doc-comment additionally records this specific gate as "KEPT but DEAD (0 impact in all
contexts)" for bold itself, historically.)

### 2b. Executed the actual code against the report's own quoted `SKIP_CONF_LVL_REC_AFTERNOON`
examples — the swap DOES occur, contradicting the report's stated mechanism

The report's "Is the sourcing symmetric — NO" section states the asymmetry exists because a
Table-B tick "feeds every fleet arm safe's own, undiluted, default-path signal" (no swap), while
only Table-A ticks "reach fleet arms via the override branch." I ran `_map_core_row` +
`_bold_passed_blocks_from_row` against the report's own two quoted `SKIP_CONF_LVL_REC_AFTERNOON`
ticks:

```
2026-08-12T14:16:02.973209
  safe:  verdict=ENTER_BULL  action=RISK_DENY_SETTLEMENT  -> own bull_pass=True
  bold:  verdict=SKIP_CONF_LVL_REC_AFTERNOON  action=SKIP_CONF_LVL_REC_AFTERNOON (BOTH match --
         this IS a scoring-level block on bold, not execution noise)
  bold_passed.bull: passed=True, score_peak_passed=True, bull_score=11
  SWAP OCCURS: True   <-- contradicts "default, undiluted path"

2026-08-13T15:11:02.929340
  safe:  verdict=ENTER_BULL  action=SKIP_LATE_ENTRY -> own bull_pass=False (time-gate
         override forces safe's OWN mapped action to HOLD here, per
         build_shared_signal.py's `_TIME_GATE_SKIPS` set -- safe's own row does NOT
         independently pass on this tick either)
  bold:  verdict=SKIP_CONF_LVL_REC_AFTERNOON  action=SKIP_CONF_LVL_REC_AFTERNOON
  bold_passed.bull: passed=True, score_peak_passed=True, bull_score=11
  SWAP OCCURS: True   <-- again, the swap branch is what fires, not the default path
  (also: safe's own passed=False here means this tick's fleet-arm entries are NOT
  explained by "safe's undiluted signal" AT ALL -- they can only be explained by the
  swap to bold's block, which the report says doesn't happen for Table B)
```

**Root cause (verified in code, not inferred):** `block_conf_lvl_rec_afternoon` is not in
`_HARD_SKIP_VERDICTS = frozenset({"SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"})`
(`build_shared_signal.py:861`) — the ONE gate deliberately hard-coded to zero out
`_bold_passed_blocks_from_row`'s `passed` regardless of score. Every other GATE_KEYS-derived
SKIP_* (including `block_conf_lvl_rec_afternoon`) only clears the `action == "ENTER_BULL"`
fast-path in `_score_peak_check`; the OR fallback (`score >= peak_threshold and trig_ok`,
`build_shared_signal.py:891-901`) still evaluates the row's `bull_score`/`triggers_fired` fields,
which are populated independently of the entry-gate outcome (the setup scored fine; only the
gate blocked the verdict). So bold's own `block_conf_lvl_rec_afternoon` block does not stop
`_bold_passed_blocks_from_row` from reporting `passed=True` for bold's bull side, which triggers
the SAME swap-into-`sig["strategies"]` branch Table A uses. This is a distinct, more precise
mechanism than what the report describes, and it means the swap fires for Table B just as often
as the "default path" framing implies it doesn't.

### 2c. `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` (n=87, Table B's largest bucket) — report's framing
IS consistent, on the one example checked

```
2026-08-06T10:31:02.400016
  safe: verdict=ENTER_BEAR action=PLACED -> own bear_pass=True
  bold: verdict=SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY action=SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY
  bold_passed.bull: passed=False  bold_passed.bear: passed=False (hard_skip=True forces both)
  SWAP OCCURS: False   <-- matches report's "default, undiluted path" claim
```

This gate IS the one `_HARD_SKIP_VERDICTS` entry, so it genuinely cannot rescue itself via the
score fallback — the report's "BINDING for safe-3, LEAKY for risky-1/risky-3" characterization
for THIS specific row is not contradicted by this check (n=1 spot-check only; not re-run across
all 87 ticks this session — see caveats).

---

## Part 3 — arithmetic re-check: minor n discrepancy, immaterial

Independently re-ran the full Table A/B join (own script, own tick load, live market currently
open so `core-decisions.jsonl` is being appended to in real time between the report's 12:26
generation and this check's ~14:30 run):

- Table A: n=133 — **exact match** to report.
- Table B: n=188 (mine) vs n=187 (report) — off by one, entirely inside `SKIP_CONF_LVL_REC_AFTERNOON`
  (46 vs 45). No duplicate `(core_tick_id, account)` rows exist in `core-decisions.jsonl`
  since 2026-08-06 (checked directly — 0 dups). Most likely explanation: one additional core
  tick appended to the live ledger between the report's run and this verification's run (market
  is open, `market_hours=True` confirmed via `et_clock.py` at both 14:19:33 and now). Not
  independently re-run at the report's exact generation timestamp, so this is UNVERIFIED as to
  cause, but the 1-tick delta is immaterial to any conclusion (45/187=24.1% vs 46/188=24.5% for
  the raw gate count; doesn't change any binding/non-binding call).
- `SKIP_LATE_ENTRY` symmetric check: both=16, either=52 — **exact match** to report.
- `SKIP_STALE_TRIGGER`: both=120, either=120 — **exact match**.
- `SKIP_MIN_PREMIUM_FLOOR`: both=0, either=50 — **exact match**.

---

## What this means for the finding under verification

**CONFIRMED (FACT, code-executed):**
- The `plan_all` strategies-branch mechanism and `_gate_check`'s role-blindness.
- Table A's numbers (n=133, safe-3 8.3%/risky-1 11.3%/risky-3 6.0%) and its causal narrative —
  all 4 quoted example ticks genuinely swap through bold's independently-passing block, verified
  by executing the actual production functions, not just reading them.
- GATE_KEYS list, `EMIT_STRATEGIES=True`, `structure_veto_enabled`/`block_bull_1100_1200`
  safe-only asymmetry.
- The three "symmetric gate" and one "never symmetric" claims (`SKIP_LATE_ENTRY`,
  `SKIP_STALE_TRIGGER`, `SKIP_MIN_PREMIUM_FLOOR`).

**REFUTED (contradicted by direct code execution against the report's own quoted evidence):**
- The claim that `SKIP_CONF_LVL_REC_AFTERNOON` is a "safe-cohort" GATE_KEYS gate comparable to
  `SKIP_STRUCTURE_VETO`/`SKIP_BULL_1100_1200` — it is bold-only by config, the opposite polarity.
- The report's stated causal mechanism for Table B's higher leak rate ("safe's own, undiluted,
  default-path signal... never touching the override branch") — disproved on both of the
  report's own quoted `SKIP_CONF_LVL_REC_AFTERNOON` example ticks, where the swap branch fires.
  The real mechanism (score+trigger fallback in `_score_peak_check` rescuing a
  non-hard-skip-gated bold row) is different, more specific, and not stated anywhere in the
  target report.
- By extension, the `proposed_change` follow-on ("mirror the safe-cohort gate into the leaking
  arm's own `gate_override`") is aimed at the wrong target for `block_conf_lvl_rec_afternoon`
  specifically — there is no safe-side version of that gate to mirror; the leak for this gate
  runs through bold's own swap-eligibility check, not a missing safe-side mirror.

The finding's Table A conclusions stand verified. Its Table B headline conclusion (the "leakiest
gate," and the stated reason Table B leaks worse than Table A) does not survive independently
executing the production code against the report's own cited ledger rows, and is REFUTED as
stated. The raw percentage/count numbers in Table B are themselves accurate (independently
reproduced), but the report's causal attribution and gate classification for that table are
wrong.

## Not re-verified this session (caveats)

- Did not re-execute the code path for all 133+188 ticks — spot-checked 7 (4 Table A + 3 Table
  B) chosen to cover the two powered gates in each table. `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`'s
  "swap never occurs" claim rests on n=1 executed example, not all 87 rows.
- Did not re-derive `_gate_check`/settlement-cap/dedup/premium-floor internals that explain why
  risky-1 (nominally ungated on min_triggers) still only enters 11-22%/21.9% of qualifying ticks
  rather than ~100% — same scope gap the target report itself disclosed as unresolved.
- Did not re-score P&L impact of any leak — out of scope, matches target report's own disclosed
  scope limit.
- ET clock verified once this session via `et_clock.py` (14:29:41 ET, `market_hours=True`); no
  trading-path file was edited, only imported read-only (`build_shared_signal.py`) for direct
  function execution against already-written ledger data.
