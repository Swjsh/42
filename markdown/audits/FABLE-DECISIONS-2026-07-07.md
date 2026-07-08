# FABLE DECISION MEMO — 2026-07-07 (pre-adjudicated calls, executable without me)

> Companion to `FABLE-GAP-AUDIT-2026-07-07.md`. Each decision: VERDICT + rationale + revert path + **what would change my mind** (pre-registered, so monitoring is mechanical, not vibes). Items marked **[J: one word]** need only yes/no. Everything else is standing judgment Opus executes under existing paper autonomy.

---

## D1 — STRATEGIC: freeze options-ENTRY research; pivot effort to execution infrastructure + futures. (standing until revoked)
**VERDICT: FREEZE new options-entry batteries for ~30 days.**
**Why:** the axis is exhausted — 6 independent kills tonight, the 2026 OOS window burned (~130 reads), and the surviving candidates are unaffordable at current equity. Every additional battery on old data now *manufactures* mirages faster than it finds edges. The binding constraints are (a) fresh data and (b) execution fidelity — neither is produced by another battery.
**Effort goes to:** G4 fleet forward-farm, G5 alert/capture, G8 greeks capture, G9 parity ledger, futures arming. These GENERATE new data; research resumes when there's something new to mine (forward fills, greeks corpus, J-call anchors, post-2026-07 OPRA).
**Exceptions (allowed):** G6 (J's exact weekly spec — one pre-registered battery, it's his named idea and the cache exists), and log-analysis studies (G12) that read decisions history, not OPRA.
**Conductor note:** task_scorer should deprioritize any new options-entry battery accordingly.
**Changes my mind:** post-07-07 OPRA accumulating ≥3 months; or the J-call corpus reaching n≥30; or a regime break that invalidates the burned-window concern.

## D2 — Adopted-position exit policy (G1): CAP-ONLY + FLATTEN + PING. Never impose a strategy on J's trade.
**VERDICT: adopted manual positions get catastrophe management ONLY** — −50% premium cap + 15:50/15:55 time-stop/flatten + Discord ping on adoption ("adopted your 747P ×5 — cap-only, you drive the exit"). **NO TP1, NO chandelier, NO ribbon-flip** on adopted positions.
**Why:** today's real trade proves it — J scalped 80% at +47–53% and held runners toward 2.5×. A v15 TP1 at +40% would have cut his runner and fought his plan. The engine cannot know J's thesis for a trade it didn't originate; its job there is disaster-prevention, not strategy. His explicit instructions (via chat/Discord) override, executed as given.
**Guard:** pin the adopted-shape default in `test_audit_fix_heartbeat.py`; red-proof it.
**Changes my mind:** J explicitly asks for full engine management of manual entries (he half-implied it once — "is the engine primed with trailing stop?" — if he says it plainly, flip to v15-full and pin that instead).

## D3 — vwap −0.06/0.40 ship: pre-registered REVOKE trigger.
**VERDICT: stands (it cleared every gate), with a mechanical forward kill-switch:** if after **15 live vwap_continuation fills** realized expectancy < $0, OR after any 5-consecutive-loss streak where the old −0.08/0.30 shape would have exited better on ≥4 of 5 (computable from fill + bar data), revert to −0.08/0.30 and mark the family forward-failed.
**Why pre-register:** the OOS that validated it is burned (R1); forward fills are the real test; deciding the threshold NOW prevents post-hoc rationalization later.
**Owner:** EOD digest / fill-funnel — add the counter; no human memory required.

## D4 — Safe-2 equity: RESET to $2K with an epoch marker. **[J: one word]**
**VERDICT: recommend paper-reset.**
**Why:** the account is a *measurement instrument*, not money. At $1,352 the sizing floors disqualify edges (ITM2, 2DTE) and distort every arming decision — the instrument is bending the experiment. Reset restores measurement range.
**Integrity condition (non-negotiable):** log an epoch boundary (`analysis/equity-epochs.jsonl`: date, closing equity, reason) and track cumulative cross-epoch P&L — the compounding truth stays visible; only the instrument is re-ranged.
**Against (stated honestly):** resetting can hide a bleeding strategy. Answer: the cross-epoch ledger keeps the bleed on the record; what we remove is the artifact where *research conclusions* depend on account balance.

## D5 — min-3-contract rule: propose a per-shape amendment. **[J: one word — it's his Rule 6]**
**VERDICT: recommend** — min-3 stays for split shapes (2 TP + 1 runner — its actual provenance); **min-1 permitted for single-exit shapes** (`tp1_qty_fraction=1.0`), where the structural reason for 3 does not exist.
**Why:** tonight the floor blocked a candidate independent of edge quality. The rule's provenance is the exit *structure*, not a risk principle — a single-exit trade with 1 contract respects every risk cap.
**If J says no:** the floor stands everywhere; note it as a hard armability constraint in the G7 gate (fine — it just shrinks the affordable set).

## D6 — cd-2026-06-27-001 (G7 pure-Python EOD-flatten backstop): ACTIVATE. **[J: one word — it was J-gated]**
**VERDICT: recommend activate.**
**Why:** it's a fail-safe that only acts at day-end on leftover positions; tonight's G3 gap (runner exits unverified at EOD) is *exactly* the failure class it retires. It fails safe (no positions → no-op), is trivially revertible, and after tonight's exit-path changes a second, independent flattener is cheap insurance.
**Changes my mind:** nothing plausible — the only cost is redundancy, which is the point.

## D7 — Fleet arm profiles (G4 phase-2 design): pre-made, with J's own constraint honored.
**Constraint honored first:** J's standing (angry, repeated) correction — **arms are RISK PROFILES, not strategies.** All arms pick from the SAME validated setup menu; they differ only in expression parameters (sizing, gate-strictness, stop/exit shape, DTE, drawdown). The profiles below stay inside that line — flagging explicitly that DTE + exit shape are *expression* parameters; if J reads them as "strategy," he vetoes and we collapse to sizing/strictness-only diversity.
**The 6:**
1. **Safe-control** — current v15.3 exactly (baseline; never changes)
2. **Bold-control** — current v15.2 exactly (baseline)
3. **One-gate-away** — same signals, gate threshold −1 (the ratified risky-arm doctrine, finally live)
4. **2DTE-forward** — same signals, DTE override 2, same-day exit, funded $10K paper (forward-tests tonight's HOLD honestly)
5. **Scalp-shape** — same signals, quick-TP 80% + tiny runner (J's own style as a standing arm; forward-tests the E8 family)
6. **J-mirror** — executes only alert-confirmed J calls (G5 flow); its clean P&L stream IS the measured value of the discretionary edge
**Why these six:** 2 controls + 3 forward-experiments that each answer a live question from tonight + 1 that turns J's judgment into a measurable book. Every HOLD verdict from tonight becomes a running experiment instead of a shelf item.

---

## Tomorrow-morning watch order (first hour, in priority)
1. Adoption path: if J trades manually, verify the ping fires + cap-only shape attached (D2 guard).
2. First live vwap fill under −0.06/0.40 → D3 counter starts.
3. fill_funnel: NOT_FLAT days must now read DEGRADED/OK, never PLACEMENT-BROKEN RED (FIX4) — a RED tomorrow is REAL, treat it as such.
4. Expired-levels drop (FIX2): confirm the active set still populates (feed thinning risk → G11).

*Written at ~95% Fable usage. Nothing above requires me again: D1–D3, D7 execute under standing paper autonomy with guards; D4–D6 await one word each from J.*
