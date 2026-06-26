# Engine Shadow Harness — Phase 3 prep (wired-not-enabled)

> **Status: BUILT + DRY-RUN-PROVEN, NOT yet firing live.** The harness code + tests ship now; the one live wiring (a ~2-line `heartbeat.md` shadow block) is **propose-only (Rule 9)** — J/conductor flips it on, after-hours. Authored 2026-06-19 (weekend loop). Spec parent: [`markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md`](SHARED-DECISION-LIBRARY-MIGRATION.md) §3 (Phase 3).

## 1. What & why

Phases 1-2 extracted the decision core (`engine/score.py` + `engine/gates.py`) and proved it **byte-identical to the orchestrator in backtests**. Phase 3 is the one validation a synthetic reproducer *cannot* give: does the engine library agree with the live **prose** heartbeat **on the exact `BarContext` the LLM produces live**? Only a live shadow answers that — it is the wall-clock gate that earns the Phase-4 right to let code drive real orders.

This harness is the read-only sidecar that measures it.

**Distinct from the existing Nemotron model shadow.** `setup/scripts/shadow_model_eval.py` → `shadow-model-decisions.jsonl` → EOD-summary 8c tests a candidate *model/params*. THIS shadow tests whether the decision-*library code* agrees with the prose. They write **separate files** and must not be conflated:

| Shadow | Producer | Ledger | Question |
|---|---|---|---|
| Model (existing) | `shadow_model_eval.py` (Nemotron) | `shadow-model-decisions.jsonl` | does a candidate model/params beat prod? |
| **Engine (this)** | `engine_shadow.py` (decide_payload) | `engine-shadow-decisions.jsonl` | does the library code == the prose? |

## 2. Architecture

```
 heartbeat tick (prose, LIVE)
   ├─ computes its decision  ──────────────►  places the real order (UNCHANGED)
   └─ writes the bar_ctx it computed to  ──┐
        automation/state/shadow/tick-payload.json   │  (the ~2-line propose-only edit)
                                                     ▼
        <venv-py> automation/scripts/engine_shadow.py --payload <f> --prose-action <a> ...
                                                     │
                       decide_payload(payload)  ◄────┘   (same fn engine_cli.main calls;
                       = score_bar + evaluate_gates       byte-identical to orchestrator)
                                                     │
                       append paired row ───────────►  automation/state/engine-shadow-decisions.jsonl
                                                     │
        (EOD/conductor)  --scorecard --date ────────►  analysis/engine-shadow/scorecard-<date>.json
```

The engine verdict is **read-only** — it never touches an order, position, param, or loop state in this phase. The prose still drives every real order.

## 3. The two iron guarantees (why it's safe to wire into the live heartbeat)

1. **READ-ONLY** — appends only to its own shadow ledger + (on demand) a scorecard. No order path, no mutation. (Verified structurally: the script imports nothing from the order/position layer.)
2. **FAIL-OPEN** — any error (bad payload, engine exception, unwritable ledger) is swallowed into a logged `SHADOW_ERROR` row and **exit 0**. The shadow can never break, slow, or block the live tick. This is the OP-25/OP-32 invariant (no automated process may degrade the live path or lock the human out).

Both are covered by `backtest/tests/test_engine_shadow.py` (17 tests) and the dry-run below.

## 4. Dry-run proof (verify-now-not-later, 2026-06-19)

Run end-to-end into a temp ledger (no real artifacts written):

- **Happy path** — quiet bar, prose `HOLD`: engine verdict `HOLD` (bear 5 / bull 7, neither passed) → `agree=true`, bucket `AGREE_NOENTRY`; scorecard `overall_agreement_rate=1.0`. ✅
- **Disagreement** — prose `ENTER_BEAR` while engine `HOLD` → logged `DISAGREE_PROSE_ONLY`, `entry_tick=true`. ✅
- **Fail-open** — a malformed payload (`prior_bars` shorter than `bar_idx`) → caught as `SHADOW_ERROR` (`IndexError ... out-of-bounds`), no crash, exit 0, row logged. ✅ (This also surfaced the payload contract gotcha in §6.)

## 5. The live wiring — EXACT `heartbeat.md` edit (PROPOSE-ONLY, do NOT apply yet)

Insert a "Phase-3 engine shadow" block where the tick has finalized its action AND still has the chart inputs in hand (after the decision, before/after the order — order placement is unchanged). Two steps:

```markdown
### Engine shadow (read-only Phase-3 — Karpathy inner loop)
After you've decided this tick's action, emit the engine's view for diffing (NEVER affects your order):
1. Write the bar context you just computed to `automation/state/shadow/tick-payload.json` as an engine_cli payload:
   `{"bar_ctx": { bar_idx, timestamp_et, bar:{o,h,l,c,v}, prior_bars:[…all bars this session incl. the trigger bar…],
     ribbon_now:{fast,pivot,slow,spread_cents,stack}, ribbon_history:[…], vix_now, vix_prior,
     vol_baseline_20, range_baseline_20, levels_active:[…], multi_day_levels:[…], htf_15m_stack }}`
   (the SAME inputs you used to score the tick — see markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md §3 / engine_cli input contract).
2. Shell out (fire-and-forget, ignore its output — it is read-only and fail-open):
   `backtest/.venv/Scripts/pythonw.exe automation/scripts/engine_shadow.py --payload automation/state/shadow/tick-payload.json --prose-action <YOUR_ACTION> --date <YYYY-MM-DD> --time <HH:MM> --require-trading-day`
```

This edit is **read-only shadow logging** (no order path touched), so it is a low-risk propose-and-ping-J (migration task `engine-3b`). Also arm `shadow-version.json` if you want the controller to track the window (optional — this harness writes its own ledger regardless).

## 6. Payload contract (the gotcha the dry-run caught)

`prior_bars` MUST contain **every bar of the session up to and including the trigger bar**, indexed so `bar_idx` is valid into it (the gates index by position). A short `prior_bars` → `IndexError` → `SHADOW_ERROR` (fail-open, but a wasted shadow tick). The heartbeat already holds the full session frame when it scores, so emit all of it. Optional fields (`level_states`, `fhh_level`, `vix_5d_ma`, `vix_20d_ma`) default safely if omitted.

## 7. The agreement gate + lifecycle

- Run for **N ≥ 5 trading days**.
- **Gate to proceed to Phase 4:** overall agreement **≥ 99%** AND **100% on entry ticks** (a HOLD disagreement is cheap; an entry disagreement is not). `--scorecard` computes both daily; `phase4_gate_pass` is the per-day flag (the real gate is the rolling N-day aggregate).
- **Every disagreement is triaged:** either (a) a prose bug the migration FIXES (engine is more correct → strengthens the case) or (b) an engine bug to fix before cutover. The scorecard lists each disagreement with its bar context for forensics.
- **Rollback:** remove the heartbeat block (or it simply stops being called). The engine never touched an order in this phase.

## 8. Enable checklist (J / conductor, after-hours)

1. Apply the §5 heartbeat edit (propose-and-ping-J; read-only).
2. `mkdir automation/state/shadow/` (the payload dir) — or let the heartbeat create it.
3. Let it run N≥5 trading days; read `analysis/engine-shadow/scorecard-<date>.json` each EOD (or wire a one-line EOD step / conductor read — propose-only follow-up, not done here).
4. When the rolling gate holds, file `analysis/recommendations/engine-cutover.json` and proceed to Phase 4 (J-gated cutover).
