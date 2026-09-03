# Rule-9 doctrine pass — DRAFT for Saturday 2026-09-05 (apply on the weekend, one session, one commit)

> Prepared 2026-09-03 02:30 ET (Fable, overnight loop) so the Saturday pass is mechanical. **Nothing here is applied
> yet** — CLAUDE.md is untouched until Saturday per Rule 9. Source: OPUS-WORK-ORDER-2026-09.md §1 "Sat 09-05" and the
> facts verified this week. Each item = exact OLD text → exact NEW text + the evidence. Apply in order, run the
> context-budget guard (`check-context-budget.ps1`) and the safety gate, one commit, one CHANGELOG row, revoke = `git revert`.

## 1. CLAUDE.md:65 — Live threshold

**OLD (line starts):** `- **Live threshold (per account independently — reworded 2026-08-29 per Gamma-decides; revoke = \`git revert\`):** go-live gate GREEN — day-level bootstrap **PF CI-lower(2.5%) > 1.0 on as-traded AND ex-best-day AND cost-adjusted** over ≥20 scored trading days, plus operational guards green, reconciliation green, 0 rule breaks in window, prod-shadow green net of costs. Measured ONLY by \`setup/scripts/go_live_gate.py\`. …`

**NEW:**
`- **Live threshold (per account independently — reworded 2026-09-05 per the 2026-09-01 audit; revoke = \`git revert\`):** arming = go-live gate **criterion 5**: the designated prod-shadow profile (\`automation/state/prod-shadow-designation.json\`, currently safe-3) on the frozen window 2026-09-01..2026-10-30 shows day-level bootstrap **PF CI-lower(2.5%) > 1.0 on as-traded AND ex-best-day AND cost-adjusted over ≥20 scored trading days**, AND criteria 2–4 green (operational guards, reconciliation, 0 rule breaks in window). **Criterion 1 (lifetime robustness) is a DISCLOSURE, not a bar.** Governing clock **2026-10-30**; the gate is re-scored every Friday and at the 09-29 safety checkpoint, decided only at 10-30. Measured ONLY by \`setup/scripts/go_live_gate.py\`. WR is a diagnostic, NOT a bar (rationale: \`analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md\` §3). \`live_readiness.py\` remains the per-trade diagnostic.`

**Evidence:** designation file (window_end 2026-10-30, min_days 20, `_superseded_2026_09_02` with J's authority quote); work order §0 decision 1; the 09-02 gate reading (criterion 1 RED on every arm by 0.71–0.75 while criterion 5 is the arming bar).

## 2. CLAUDE.md:44 — Rule 7 (PDT)

**OLD:** `7. **PDT awareness.** Under $25K: 3 day-trades per rolling 5 business days (margin) or respect settlement (cash).`

**NEW:** `7. **Day-trade awareness (PDT floor repealed).** FINRA repealed the $25K margin day-trading floor 2026-06-04; both accounts are verified on the new intraday-margin regime, so $25K is a compounding waypoint, not a legal gate. The engine's own day-trade accounting stays as-is (fleet computes trailing-5d day trades every tick; \`fleet_pdt_enforce\` is deliberately OFF): the pre-registered PDT counterfactual (\`analysis/recommendations/pdt-blocked-counterfactual-2026-09-02.md\`) returned FAIL_PDT_STAYS_AS_IS — the self-imposed constraint was **not demonstrated costly** (caveat: the walker's magnitude bias, WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY). Cash-settlement awareness unchanged.`

**Evidence:** PREREG-BACKLOG-ADJUDICATION RUN 1 (09-02); FLEET-PATH-AUDIT residual (4).

## 3. CLAUDE.md:64 — Goal line

**OLD:** `- **Goal:** Both accounts grow → $5K → $10K → $25K+. Dual-account experiment answers which risk profile compounds better at each tier. ⚠️ **$25K was PDT-derived, not a fixed target** — …`

**NEW:** `- **Goal:** ONE live account (the designated prod-shadow profile, currently safe-3) plus a paper lab (the other arms). Grow $5K → $10K → $25K+ by compounding; **$25K is a waypoint, not a gate** (PDT floor repealed 2026-06-04). The paper lab answers which risk profile compounds better; only the prod-shadow profile is a candidate for money. Canonical destination + ordered gates: [\`ROADMAP.md\`](markdown/planning/ROADMAP.md).`

**Evidence:** work order §0/§4 (one live account + paper lab); TWO-ACCOUNT-CONSOLIDATION handoff; designation file.

## 4. CLAUDE.md:30 — tp1_qty_fraction phrase

**OLD fragment:** `tp1_qty_fraction 0.8 Safe / 0.667 Bold (Safe raised 2026-06-28, pk-2026-06-28-001)`

**NEW fragment:** `tp1_qty_fraction 0.667 both (the 0.8 Safe value in params.json is SHADOWED — \`strategies.py\` hardcodes ribbon_ride at 0.667; read the arm's \`exit-state.json\` for live truth)`

**Evidence:** work order §1 Sat box ("tp1_qty_fraction 0.8/0.667 (shadowed — strategies.py hardcodes 0.667 both)"); the Account-context TP1 warning already in CLAUDE.md.

## 5. CLAUDE.md:81, 126, 128 — `decisions.jsonl` → `core-decisions.jsonl`

Three literal replacements of `decisions.jsonl` with `core-decisions.jsonl` (the shadow eval row, the Execution row, the Post-trade row). **Evidence:** the live engine writes `automation/state/core-decisions.jsonl`; every 2026-09 instrument (first-live-day review, fill latency, sole-blocker miner) reads that name.

## 6. CLAUDE.md:42–43 — Rules 5 and 6 gain the live $ caps

**Rule 5 OLD tail:** `… Day closed for that account. No revenge trades.`
**Rule 5 NEW tail:** `… Day closed for that account. No revenge trades. The live floor is the **tighter of the % kill and the $400/day cap** (PREREG-TIGHT-LADDER-2026-08-28, \`daily_loss_kill_switch_dollars\`).`

**Rule 6 OLD tail:** `… Min 3 contracts (2 TP + 1 runner). Scale per [risk-rules.md].`
**Rule 6 NEW tail:** `… Min 3 contracts (2 TP + 1 runner), **max 5 per entry, max $1,000 per position** — the tighter of the % cap and these $ caps wins (\`risk_gate.cap_entry_qty\`, both money paths). Scale per [risk-rules.md].`

**Evidence:** params.json `_max_contracts_per_entry_doc_2026_08_29`, `_max_position_dollars_doc_2026_08_29`; ARCHITECTURE §3.2b tight-ladder caps verified on both paths.

## 7. CLAUDE.md:66 — the arm roster in the Daily P&L target line

**OLD fragment:** `Across the 5 active real-fills arms (safe-2, bold-2, safe-3, risky-1, risky-3) that's ~$500–1,000/day book-wide`
**NEW fragment:** `Across the 4 active real-fills arms (safe-2, bold-2, safe-3, risky-1 — risky-3 retired 2026-08-28) that's ~$400–800/day book-wide`

**Evidence:** `accounts.json` risky-3 `status: retired, live: false`; the work order's ADDED 2026-09-02 note; `arm_roster.py` on the bundle branch.

## 8. CHANGELOG rows + LESSONS index

- One CHANGELOG.md entry: "2026-09-05 Rule-9 doctrine pass: live threshold → criterion 5 / 10-30 clock; Rule 7 PDT repeal; Goal = one live account + paper lab; tp1 0.667 both (shadow); core-decisions.jsonl ×3; Rules 5/6 live $ caps; 4-arm roster. Revoke: git revert <sha>."
- LESSONS L302/L303 landed 2026-09-03 (`6629e1b8`); **L304–L309 landed 2026-09-03 03:50 ET** (the five 09-01 field lessons + the live-state-guard lesson), index rows folded. Nothing left for the lesson-author on Saturday.
- ⚠️ **Budget: CLAUDE.md reads 8,912 / 9,000 tokens (99%, YELLOW) after the L304–L309 index fold.** Items 1–7 above are net +~120 words, so the pass WILL go RED unless it trims first. Trim candidates, in order: (a) the Rule-7 evidence clause; (b) the Account-context TP1 warning block (now redundant with item 4); (c) shorten item 1's parenthetical rationale pointer to the doc name only. Run `check-context-budget.ps1` after each trim; the pass lands only at ≤ 9,000.

## Pre-flight checklist (Saturday)

1. `python setup/scripts/et_clock.py` → confirm Saturday. 2. `git status` clean on CLAUDE.md (no foreign hunks). 3. Apply 1–7 verbatim. 4. `check-context-budget.ps1` ≤ 9K tokens (the NEW texts are net +~120 words; trim the Rule 7 evidence clause first if RED). 5. `python backtest/tests/run_safety_gate.py`. 6. One commit + CHANGELOG row. 7. Tick the work-order boxes; STATUS entry; revoke line.
