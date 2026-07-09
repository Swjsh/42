# Gamma_Prospector — the exogenous-idea organ

> Built 2026-07-09. Scheduled-task registry: [`automation/state/SCHEDULED-TASKS.md`](../../automation/state/SCHEDULED-TASKS.md). Code: [`setup/scripts/prospector.py`](../../setup/scripts/prospector.py). Guard: `backtest/tests/test_prospector.py` + `backtest/tests/test_firm_brief_prospector_section.py`.

## Why this exists

J, 2026-07-09, verbatim: *"these are things gamma should be thinking of on its own! where is the autonomy? gamma hasn't introduced a single new idea like this at all yet."*

Diagnosis (Fable): every existing idea-producing organ in Project Gamma is **ENDOGENOUS** — it looks inward at Gamma's own output:

| Organ | What it mines |
|---|---|
| `trade_autopsy.py` (Gamma_TradeAutopsy) | OUR OWN losing fills (counterfactual replay) |
| `chef` agent | OUR OWN strategy variants (parameter tweaks, new setup modes) |
| Kitchen (`kitchen_daemon.py` + seeder + reviewer) | OUR OWN knob-tuning search space |
| `swarm_consult.py` | Adversarial review of OUR OWN proposals |
| Analyst / EOD review | OUR OWN trade history against the 10 rules |

Not one of them scans **OUTWARD**: new data feeds, indicator ecosystems, community tooling, published academic intraday anomalies, cross-asset tells. `Gamma_Prospector` is that organ — the first one whose entire job is to bring something INTO the system that wasn't already here.

## The loop (one nightly fire, 21:30 ET)

```
pick_next_beat()  →  scan_beat()  →  triage_one() × N  →  append_ledger_rows()  →  promote_top1()  →  surface()
   (rotate 7)         (1 free LLM      (coerce to fixed      (idempotent by         (oldest battery-      (firm-brief line +
                        call/beat)       schema, weakest-      dedupe_key; kills      ready idea → Chef's    state counters —
                                          bucket defaults)      block re-entry)        _chef-inbox as a      NOT autonomy-
                                                                                       STUDY SPEC, not       metric.json, see
                                                                                       code)                 below)
```

1. **`pick_next_beat(state)`** — rotates through 7 fixed research beats; the index is persisted in `analysis/prospector/state.json` so consecutive nights cover *different* ground:
   `data_feeds_free · tv_community_indicators · options_structure_metrics · academic_intraday_anomalies · cross_asset_signals · futures_positioning · microstructure_internals`
2. **`scan_beat(beat)`** — ONE free-tier LLM call for that beat. Reuses `swarm_consult.py`'s provider-call plumbing (`_provider_call`: the openrouter/cerebras/groq routing, key loading, fail-open error envelope) directly, rather than its higher-level `consult()`/brainstorm mode — brainstorm mode bakes in a fixed prose-template instruction that would collide with the strict-JSON contract this module needs. Tries each model in `DEFAULT_PERSPECTIVE_MODELS + PERSPECTIVE_FALLBACK_POOL` **in turn** (sequential, not a 5-way fan-out) until one returns a parseable JSON array. A nightly single-beat scan only needs ONE well-formed response — sequential-until-success is cheaper (OP-3) and still fail-open across the whole free roster. If every model fails, this is NOT an error: log it, exit 0, ledger untouched ("skip-with-log", explicitly anticipated by the build brief).
3. **`triage_one(beat, raw)`** — coerces each raw object into the fixed idea-row schema (below). Unparseable/ambiguous fields default to the **weakest** bucket, so a parsing fluke can never falsely qualify an idea for promotion: unknown `cost` → `"paid"`, unknown `instrument_fit` → `"both"`, unknown `testability` → `"vague"`.
4. **`append_ledger_rows(rows)`** — idempotent append to `analysis/prospector/ideas-ledger.jsonl`, keyed by `dedupe_key`. A `dedupe_key` that was ever recorded as killed (a `"kind":"kill"` row) can never re-enter, even under a different beat's future wording of the same idea.
5. **`promote_top1(rows, state)`** — the single **oldest** not-yet-promoted `testability=="battery-ready"` idea becomes a pre-registered STUDY SPEC stub (hypothesis / data / null / pass bar — **not code**) written into `strategy/candidates/_chef-inbox/`.
6. **`surface()`** — writes `automation/state/prospector-last.json` (firm_brief.py renders one line from it) and bumps Prospector's own counters in `analysis/prospector/state.json`.

Never touches engine/params/exits. Never places an order. Never edits another organ's ledger. Notify-only, propose-only, $0, fail-open, exits 0 always.

## Idea-row schema

```json
{
  "id": "vix1d_gate",
  "dedupe_key": "vix1d_gate",
  "beat": "options_structure_metrics",
  "idea": "Read CBOE's VIX1D as a same-horizon vol gate...",
  "mechanism_1line": "why this would help, one sentence",
  "data_source": "CBOE VIX1D index -- same access path Gamma already uses for VIX",
  "cost": "$0 | paid",
  "instrument_fit": "0dte | mes | both",
  "testability": "battery-ready | needs-data | vague",
  "kind": "idea",
  "status": "proposed",
  "date": "2026-07-09",
  "source": "J-2026-07-09 | fable-2026-07-09 | swarm:<model-slug>",
  "ts_et": "..."
}
```

A **kill row** is `{"kind": "kill", "dedupe_key": ..., "reason": ..., "ts_et": ...}` — the ledger is append-only truth; a kill is a new row, never a mutation of the original idea row.

`id == dedupe_key` always in this build (kept as two fields per the task brief's schema, but there is no case yet where they'd usefully differ). Seeded rows use their own human-chosen slug as the key (e.g. `gex_flip_from_banked_cboe`); swarm-sourced rows use a beat-namespaced slug of the idea text (`make_dedupe_key`) so two different beats' similar-sounding ideas don't collide.

**Known v1 limitation:** dedupe is by stable string match, not semantic similarity. An LLM rewording the same underlying idea on a later night will NOT collapse into the existing row — only identical/near-identical repeats dedupe. Acceptable for a first version; a future pass could add a cheap embedding-similarity pre-check before append.

## Why `_chef-inbox/`, not `queue.md` or `cook-queue.jsonl`

The build brief named three candidate intakes to inspect: `automation/overnight/queue.md`, a `_skill-inbox`-style author inbox, or `automation/state/cook-queue.jsonl`. All three were read before deciding:

- **`cook-queue.jsonl`** is the Kitchen daemon's own task ledger (create/claim/complete events consumed by `kitchen_daemon.py`) — it drives *tuning* cooks (parameter sweeps, existing-strategy variants), not new-data-signal research. Wrong shape for "here is an external idea, go design a study."
- **`queue.md`** is the generic conductor backlog. `trade_autopsy.py` already appends there and calls it *"conductor/chef intake"* in its own docstring — a legitimate precedent. But it is generic prose the Conductor persona reads top-to-bottom by priority tier; nothing marks an item as *Chef's* specifically, and `conductor.md`'s own STAGE 1 read-order ranks it BELOW the author inboxes for MED/LOW items (`queue.md priority HIGH` is priority #2, but plain `queue.md priority MED → LOW` is priority #7 — dead last before this build).
- **`strategy/candidates/_chef-inbox/`** is a **purpose-built, already-existing intake exclusively for Chef**, read via `conductor.md` STAGE 1 priority #5 ("Author inboxes... `_chef-inbox` → chef... **engine-benefit, observer/authoring-only — ships without J ratification**"), ranked ABOVE generic `queue.md` MED/LOW items. Its own README (`strategy/candidates/_chef-inbox/README.md`) documents an item template — **Routed by / Priority / Category / Source / The Finding / Research Question for Chef / Backtest Request / Files for Reference / Priority-Dependencies** — that maps *exactly* onto "a pre-registered STUDY SPEC stub (hypothesis, data, null, pass bar)": Research Question = hypothesis, Backtest Request = data + null + pass bar. `render_chef_inbox_item()` reuses that real template verbatim (verified against the live README in `test_render_chef_inbox_item_matches_required_sections`).

**Decision: promote into `_chef-inbox/`.** It is Chef's own dedicated intake, structurally the best fit for the deliverable, and a higher-priority read than a generic `queue.md` append. `_chef-inbox` items are also covered by the existing OP-29 reconciliation guard (`test_author_inbox_reconciliation.py`) — a Prospector-authored item open >7 days is automatically surfaced as an advisory (fail-open, never a hard failure), so a promoted idea Chef never gets to cannot silently rot forever unnoticed.

## Why `automation/state/autonomy-metric.json` was NOT touched

The build brief's instruction was conditional: *"update `automation/state/autonomy-metric.json` with a generative counter **if that file's schema allows additive keys** (read it first; additive only)."* It was read first. `conductor_outcome.compute_metric()` is the sole writer:

```python
metric: dict[str, Any] = { ... fully reconstructed from conductor-outcomes.jsonl ... }
if write:
    met_path.write_text(json.dumps(metric, indent=2) + "\n", encoding="utf-8")
```

This is a **wholesale overwrite from a freshly-computed dict** — no read-merge of the existing file. Any externally-added key would be silently wiped the next time `compute_metric()` runs (a rolling window fold that fires routinely from the conductor's own STAGE 5). The schema does **not** durably allow additive keys, despite looking like a flat, additive-friendly JSON dict at a glance. Per the instruction's own condition, the correct action is: don't. Prospector instead tracks its own generative counters (`fires_total`, `ideas_total`, `promoted_total`, `promoted_dedupe_keys`) in `analysis/prospector/state.json`, a file it fully owns.

## Files

| File | Written by | Purpose |
|---|---|---|
| `setup/scripts/prospector.py` | — | The organ. `run()` is the testable core; `main()` is a thin argparse wrapper that never lets an exception escape. |
| `setup/scripts/install-prospector.ps1` | — | Registers `Gamma_Prospector` (daily 21:30 ET). |
| `analysis/prospector/state.json` | prospector.py | Beat rotation index + generative counters + `promoted_dedupe_keys` (promotion idempotency). |
| `analysis/prospector/ideas-ledger.jsonl` | prospector.py | Append-only idea rows + kill rows. Source of truth. |
| `automation/state/prospector-last.json` | prospector.py | One-shot snapshot of the last fire; firm_brief.py reads this (same pattern as `trade-autopsy-last.json`). |
| `strategy/candidates/_chef-inbox/{date}-prospector-{slug}.md` | prospector.py (promote_top1) | The promoted STUDY SPEC stub(s). |
| `backtest/tests/test_prospector.py` | — | Guard: dedupe/idempotency, kill-never-re-enters, beat rotation, fail-open, promotion FIFO + idempotency, chef-inbox format, seed-data validity. |
| `backtest/tests/test_firm_brief_prospector_section.py` | — | Guard for the small additive `firm_brief.py` section. |

## Scheduling

`Gamma_Prospector`, **daily** (not weekdays-only — ideation needs no market hours, matching the Kitchen's 24/7 cadence) at **19:30 MT = 21:30 ET**. Wiring: `wscript → run_exe_hidden.vbs → backtest\.venv\Scripts\pythonw.exe → prospector.py` (flash-free GUI-subsystem chain, matches `trade_autopsy`/`broker_fills`/Kitchen). `backtest/.venv` is required — `prospector.py` imports `swarm_consult.py`, whose cerebras/groq lanes need the `openai` package that lives only in that venv (not system Python).

The installer forces the trigger's first occurrence to **tomorrow's date explicitly** (`(Get-Date).Date.AddDays(1).AddHours(19).AddMinutes(30)`), not a bare time-of-day. A bare `-At "19:30"` would resolve to *today* if 19:30 local hadn't yet passed at install time — this build was installed at 17:24 MT (19:24 ET), i.e. *before* 19:30 MT, so a naive trigger would have fired the same night. Forcing the date avoids that unconditionally, satisfying the build instruction ("it first fires on its schedule, never tonight") regardless of what time the installer happens to run.

## What it never touches

Same rail as every other OP-22/OP-29 engine-benefit organ: no edits to `automation/prompts/heartbeat*.md`, `automation/state/params*.json`, live order placement, or any *other* organ's own ledger/state file. The only production-adjacent file this build touched is `setup/scripts/firm_brief.py` (one small additive, fail-open section + footer line — mirrors the pre-existing trade-autopsy section exactly) and `automation/state/SCHEDULED-TASKS.md` (documentation, per convention).

## Tonight's seed (12 entries, 2026-07-09)

Seeded via `prospector.py --seed` (idempotent — safe to re-run). Source `J-2026-07-09` (5): `volume_shelf_tv_vp, community_pine_sr, finra_short_volume, dix_daily, pattern_grammar`. Source `fable-2026-07-09` (7): `gex_flip_from_banked_cboe, vix1d_gate, tick_add_internals, moc_imbalance_window, globex_levels, cot_mes_positioning, timeofday_seasonality_own_fills`.

`testability="battery-ready"` (exactly 3, per the build instruction): `gex_flip_from_banked_cboe`, `vix1d_gate`, `volume_shelf_tv_vp`. Everything else is `needs-data` or `vague` (`pattern_grammar` — a methodology, not a data signal).

`gex_flip_from_banked_cboe` was promoted as this build's first `_chef-inbox` study-spec stub: 14 sessions are **already banked** by `Gamma_CboeOiBank` and `gex_regime.py`'s dealer-GEX computation is **already built** — zero new data fetch, zero new code, cheapest possible first study. Its hand-authored spec is honest about the real constraint: a well-powered backtest needs ≥60–90 as-of days per `gex_regime.assess_backtest_feasibility` (only 14 banked as of 2026-07-09), so the bounded first deliverable is a feasibility check + a **pre-registered** backtest design, not an early/underpowered run.

## Future work (not built this session — scope-bounded)

- **Staleness note** on the firm-brief section (like `autopsy_staleness_note` for trade-autopsy) — catches a dark `Gamma_Prospector` clock-trigger the same way OP-33b demands. Skipped here to keep the `firm_brief.py` diff minimal; cheap to add later.
- **Closing the loop from Chef back to the ledger** — today, nothing marks a promoted idea's eventual DONE/KILLED verdict on the *ledger* row itself (Chef's own `_chef-inbox` closing-handshake convention — rename `.DONE` — covers the inbox side; `kill_idea()` exists and is guard-tested, but nothing calls it automatically yet). A future pass could have Chef (or a reviewer organ) call `prospector.kill_idea(dedupe_key, reason)` when a promoted study comes back negative, so a rejected idea is provably retired rather than just quietly un-promoted.
- **Semantic dedupe** — see the "known v1 limitation" note above.
