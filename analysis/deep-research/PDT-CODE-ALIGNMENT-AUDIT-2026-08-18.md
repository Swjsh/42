# PDT / Cash-Account Code Alignment Audit — 2026-08-18

> Worker-tier code audit (Sonnet). ASSESS AND REPORT — no trading behavior changed, nothing armed,
> no `params*.json` edited. Four pure documentation/comment-staleness fixes applied where the
> correct value was already proven in-repo (listed under SAFE-NOW, below). Written 2026-08-18
> ~18:37 ET (`et_clock.py`).
>
> Reads first: [`REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`](../../markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md)
> (today's regulatory research — fact 1: FINRA eliminated the $25k/day-trade-count PDT rule for
> margin accounts effective 2026-06-04, SR-FINRA-2025-017, 18-month firm grace window to
> 2027-10-20; fact 2: Alpaca sells no true cash-account product — "all accounts are set up as
> margin accounts"), [`MAP.md`](../../MAP.md) (routing table), and the prior live-account audit
> [`PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`](PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md).

---

## VERDICT

**2 LIVE-and-now-wrong premises found. 0 arms are currently blocked by either one.**

- **Premise A — "both core accounts are CASH accounts."** Live: it is the selected justification
  for `pdt_gate_mode="cash_settlement"`, which BOTH core accounts (safe-2, bold-2) run on every
  tick today (confirmed via `self-check-last.json`, 2026-08-18T18:09:56 ET — both `status: "OK"`).
  Wrong: Alpaca sells no cash-account product at all; both accounts read `multiplier=4` (margin),
  confirmed twice — 2026-08-06 audit and a fresh 2026-08-18 orchestrator broker read (below).
  **Does not currently mis-block anything** — both accounts have ample settlement headroom.
- **Premise B — "the margin-PDT $25k/3-day-trade rule models a currently-enforced FINRA/broker
  constraint."** Live: the code (`risk_gate.py`'s `margin_pdt` branch, `pdt_tracker.py`'s
  fill-history count) still runs every tick — for the 3 fleet arms (pinned to `margin_pdt`) and as
  the legacy one-line-revert path for core — and CLAUDE.md's Rule 7 text still states it as current
  doctrine. Wrong: FINRA eliminated this exact rule for margin accounts 2026-06-04. **Does not
  currently block anything** — the fleet-arm count fed to it is structurally always 0 (see below),
  so `0 >= 3` never trips regardless of the regulatory question.
- **Decisive new evidence (orchestrator-supplied live broker read, 2026-08-18, NOT independently
  re-verified by this session per the task's broker-API restriction):** fresh `GET /v2/account` on
  both core accounts — safe-2 equity $5,266.38, bold-2 equity $5,048.40 — found
  `pattern_day_trader` and `daytrade_count` **entirely ABSENT** from the payload (not null —
  gone), replaced by `intraday_adjustments` (the new IML mechanism); `multiplier: "4"` on both;
  `get_account_config` carries no `pdt_check` key on either account. This answers the one open
  empirical question both research docs flagged (which PDT regime our specific accounts are
  under): **both are confirmed on Alpaca's NEW post-2026-06-04 regime**, not held back under the
  18-month legacy-grace-window clause. This is treated as HIGH-CONFIDENCE — it is a direct field
  read, not an inference — but is reported here as relayed, not independently re-run by this
  session.
- **Fact (1) hedge, honored per task instructions:** a separate agent was independently
  re-verifying FINRA's rule elimination as this audit ran. The orchestrator's follow-up reports
  that re-verification returned CONFIRMED (FINRA's live Rule 4210 page today contains zero
  occurrences of "pattern day trader", "$25,000", or "day trade"). This report's conclusions do
  not depend on that outcome either way: every code/doc citation below is dated and sourced, no
  gate was flipped, and the two LIVE-and-wrong premises are flagged for J's decision, not
  auto-corrected in behavior. If fact (1) is ever walked back, the four documentation edits this
  session made (below) cite their source inline and are a clean one-paragraph revert each.
- **No live order-path code needed to change.** Both wrong premises are currently either
  (a) harmless-but-mislabeled (cash_settlement's discipline still functions as a reasonable
  same-day-entries throttle regardless of account type) or (b) structurally inert (margin_pdt's
  day-trade count for fleet arms can't be anything but 0 given the broker no longer reports it).
  The risk is **forward-looking**, not current — see the NEEDS-J landmine in the change list.

---

## Findings table

| # | File:Line | Assumption encoded | LIVE / DEAD | Correct behavior (post 2026-06-04 / post today's research) | Smallest safe change |
|---|---|---|---|---|---|
| 1 | `automation/state/params.json:10` + `automation/state/aggressive/params.json:4` (`pdt_gate_mode: "cash_settlement"`) | Safe-2 and Bold-2 are CASH accounts; settlement-pool gating (not a trade count) is the regulatorily-correct Rule 7 model for them | **LIVE** — traced: `heartbeat_core.py:2435` calls `rg.check_order(...settled_cash_available=..., same_day_entries_used=...)` every core tick; confirmed executing today via `self-check-last.json` (2026-08-18T18:09:56 ET): safe `1/5 entries, $5,079.53/$5,184.53 remaining`, bold `1/5 entries, $4,793.65/$4,968.65 remaining`, both `status: "OK"` | Premise is false (Alpaca sells no cash accounts; both read `multiplier=4`). The gate ITSELF is not necessarily wrong to keep — it's a voluntary capital-discipline throttle J explicitly chose 2026-08-09 ("I always use cash accounts... that's how much we have until it settles") independent of what Alpaca's account object says. Whether to keep modelling cash-style settlement on a margin account is a J decision, not a bug fix | **Doc-only, DONE this session**: corrected the false "multiplier=1 / cash account" claim in `settlement_ledger.py`'s module docstring and `risk_gate.py`'s PDT/SETTLEMENT docstring section. Did **not** touch `params.json`/`aggressive/params.json` (explicitly out of scope) — their `_pdt_gate_mode_doc` fields still assert the false premise; flagged NEEDS-J below |
| 2 | `backtest/lib/risk_gate.py:120-121` (`PDT_EQUITY_THRESHOLD = 25_000.0`, `PDT_DAY_TRADE_LIMIT = 3`) + `margin_pdt` branch (was lines ~447-456, now shifted by this session's comment insert) | Models "FINRA's margin-account PDT rule": >=3 day-trades/5bd AND equity<$25K → deny | **LIVE CODE** — the branch executes whenever `pdt_gate_mode` resolves to `margin_pdt`: today that's exactly the 3 fleet arms (forced, see #4) plus the function-level default for any caller that omits the key (revert path). **Not currently binding** for any of the 5 arms (see #4) | FINRA eliminated this exact rule for margin accounts 2026-06-04 (SR-FINRA-2025-017). Correct framing: this is now **local policy with an obsolete rationale** if ever reactivated with a real count — not a faithful model of any current broker/regulator rule | **Doc-only, DONE this session**: rewrote both the module docstring's PDT/SETTLEMENT section and the constants' inline comment to state the 2026-06-04 elimination + the corrected account-type facts + the orchestrator's field-absence evidence. Zero logic changed |
| 3 | `automation/state/fleet/fleet_executor.py:1223-1224` (`_fleet_params["pdt_gate_mode"] = "margin_pdt"`, hardcoded, overrides whatever the shared params file says) | Fleet arms (safe-3, risky-1, risky-3) should be isolated onto the legacy margin-style gate, independent of core's mode | **LIVE** — runs on every fleet `finalize()` call, i.e., every fleet order | The PIN itself is not a regulatory claim — it's a deliberate blast-radius guard (documented: fleet never computes `settled_cash_available`/`same_day_entries_used`, so inheriting `cash_settlement` would fail-closed on every fleet order). Leave it. What it's pinned **to** (`margin_pdt`'s obsolete math) is the problem, addressed in #4 | No change. If fleet PDT gating is ever revisited, retarget away from `margin_pdt`'s $25k/3-trade math (see NEEDS-J) |
| 4 | `automation/state/fleet/fleet_live.py:787` (`day_trades_legacy = int(acct.get("daytrade_count", 0) or 0)`) + `:773-789` (`fleet_pdt_enforce` flag, unset everywhere checked → defaults False) | Fleet arms' live PDT gate should default to reading the broker's own `daytrade_count` field (enforcement off by default, pending a real wiring decision) | **LIVE** — `day_trades_legacy` is computed and passed to `finalize()`/`check_order` every tick for safe-3/risky-1/risky-3 | Confirmed **twice** now that this field can never be anything but effectively 0: 2026-08-06 audit found it present-but-null; the 2026-08-18 orchestrator read found it **entirely absent** (replaced by `intraday_adjustments`). Python's `.get(key, 0)` / `.get(key) or 0` idiom already used here returns identical output (`0`) whether the key is null or absent — **no new fail-open/fail-closed defect from the schema change itself**, verified by re-reading both consumer call sites line-by-line | No change — structurally inert as a gate (DEAD in effect, LIVE in execution). The `fleet_pdt_enforce` flag is the actual landmine — see NEEDS-J |
| 5 | `setup/scripts/pdt_tracker.py` (whole module — `fetch_day_trades_used_5d`, `compute_day_trades_used_5d`) | Reconstructs a FINRA-style trailing-5-business-day day-trade count directly from Alpaca fill history (deliberately NOT from the broker's own `daytrade_count`/`pattern_day_trader` fields, which were already known-unreliable) | **LIVE** — called every core tick (`heartbeat_core.py:2327`, feeds `circuit-breaker.json`'s `day_trades_used_5d`: safe=**12**, bold=**11** as of the 2026-08-17 computation) and by fleet's `_true_day_trades_5d` (`fleet_live.py:143`) for the `day_trades_true` visibility field | This is exactly the orchestrator's "local policy with an obsolete rationale" pattern: a locally-reconstructed shadow-count of a regulatory concept that (a) the broker no longer signals at all (fields gone) and (b) FINRA no longer enforces for margin accounts. Currently **VISIBILITY-ONLY** for both core and fleet — not consumed by any live deny (core: `cash_settlement` is the live gate; fleet: `margin_pdt` fed a structurally-0 count) | **Doc-only, DONE this session**: added a STATUS UPDATE paragraph to the module docstring stating both the account-type correction and the FINRA-elimination fact, and explicitly warning against re-arming `fleet_pdt_enforce` against this module's count without addressing both first |
| 6 | `markdown/0dte/risk-rules.md:209-217` ("Rule 7 (PDT) — fleet vs. core enforcement asymmetry", dated 2026-07-08) | Core enforces Rule 7 via a live day-trade count; fleet "does not check PDT at all... hardcoded `day_trades: 0`" | **DOC-ONLY** — described a state since superseded twice (core moved to `cash_settlement` 2026-07-14/08-09; fleet gained real-count visibility 2026-08-06) | Both halves stale for different reasons (mechanism drift + regulatory drift) | **DONE this session** — appended a dated UPDATE block after the original section (kept verbatim per doc-architecture fold rule), covering both drifts and warning `PDT-WIRE-FLEET-ARMS` against wiring the obsolete math |
| 7 | `CLAUDE.md` Rule 7: *"PDT awareness. Under $25K: 3 day-trades per rolling 5 business days (margin) or respect settlement (cash)."* | States the pre-2026-06-04 margin rule as current doctrine, and implies a cash-account option that Alpaca doesn't sell | **DOCTRINE** — one of the 10 rules Gamma enforces; read as ground truth by every session | The margin clause is regulatorily obsolete (fact 1); the cash clause rests on an account-type premise that's false for Alpaca (fact 2) | **NOT edited.** Rule-text changes are gated by CLAUDE.md's own Rule 9 (no mid-session rule changes; weekend-ratified, written reason) and this audit's fact (1) was still under independent re-verification while this session ran. **NEEDS-J** |
| 8 | `backtest/lib/cap_admission.py:58-65`, `automation/scripts/pre_order_gate.py:64-71` (`equity_min/max` $25,000 band boundary, `max_pct` ladder) | An equity-tier boundary at exactly $25,000 | **DEAD w.r.t. live order gating** — grep-confirmed neither `heartbeat_core.py` nor `fleet_executor.py`/`fleet_live.py` (the two live order paths per `MAP.md`) imports either module. Both are consumed only by `backtest/autoresearch/*` (Kitchen/research pipeline) | Classify **(b) — unrelated account-tier milestone**, not PDT-derived. This is the same leverage/sizing ladder as CLAUDE.md's own "$5K → $10K → $25K+" growth roadmap — $25K is coincidentally both the old PDT line and Gamma's own equity-growth milestone; not the same mechanism | No change |
| 9 | `automation/state/params.json` `v15_max_premium_pct_of_account` (equity-tier `max_pct` ladder, $25K boundary) | Same $25K boundary, different table | **LIVE** — `risk_gate.py`'s `_max_premium_pct_for_equity` reads this key inside `check_order`'s `MAX_PREMIUM_TIER` gate (real, executing, per-order sizing cap) | Classify **(b)** — a leverage/notional-cap ladder, unrelated to day-trade counting or account eligibility. Verified via its own `v15_hard_gate_logic` doc: "Prevents 315%-leverage situations" — a sizing safety rule, not a PDT rule | No change |
| 10 | `automation/state/params.json` `v15_strike_offset_per_tier` (equity-tier strike-offset ladder, $25K boundary → ITM-2) | Same $25K boundary, strike-selection table | **DEAD on the live core path** — per the table's OWN doc field (`_v15_strike_offset_per_tier_doc`, pre-existing): `heartbeat_core.py` does NOT read this table; it calls `crypto/lib/strike_selection.py#pick_strike()` against hardcoded `V15_SAFE_TIERS`/`V15_BOLD_TIERS` directly. **LIVE only on the sim/backtest lane** (`orchestrator.py`'s `_apply_param_overrides`) | Classify **(b)**, same as #9 — unrelated milestone. Already correctly self-documented as vestigial; not a new finding, confirmed | No change |
| 11 | `crypto/lib/strike_selection.py` `V15_SAFE_TIERS`/`V15_BOLD_TIERS` ($25K boundary, ITM-2 tier) | The ACTUAL live strike-offset ladder core Safe/Bold trade against | **LIVE** — module's own docstring: "`heartbeat_core.py`... calls `pick_strike()` against these hardcoded tables directly" | Classify **(b)** — same leverage-milestone reasoning as #9/#10, not PDT-derived | No change |
| 12 | `setup/scripts/preopen_readiness.py:259,273` (`pdt = bool(acct.get("pattern_day_trader"))`; `elif pdt and equity < 25000 and dtc >= 3`) | Broker-reported PDT flag + day-trade count feed a YELLOW-only (never RED) informational readiness line | **LIVE** (executes every readiness check) but **structurally unreachable**: `pattern_day_trader` is confirmed absent from the live payload (orchestrator's 2026-08-18 read), so `pdt` is always `False` and this branch can never fire | Cosmetic only — the code comment already says "never RED the readiness on it... the live risk_gate enforces PDT." Re-verified no fail-open/fail-closed defect: `.get(key)` with no default returns `None` whether the key is absent or present-with-null, matching the pre-existing `bool(None) == False` handling | No change needed; low-priority candidate for deletion/relabel (dead YELLOW branch is harmless) — **NEEDS-EVIDENCE/LOW**, not touched this session |
| 13 | `setup/scripts/fast_path_executor.py` (whole module, `--mode live`-capable) | A second, dormant order-placement path with ZERO Rule 7 logic (imports `risk_gate` zero times, reimplements kill-switch/risk-cap/min-contracts inline, but nothing PDT/settlement-shaped) | **LATENT** — live sentinel `automation/state/fast-path-live-enabled.flag` exists (J-ratified 2026-05-18) but nothing currently invokes it (no scheduled task; decisions ledger last written 2026-05-20) | Not "obsolete regulatory assumption" — it has **no** Rule 7 assumption at all, old or new. Already covered by a purpose-built tripwire (`backtest/tests/test_fast_path_pdt_gap_2026_08_12.py`) that goes RED the moment this path becomes reachable while still missing Rule 7 | No action — already guarded; noted for completeness only |
| 14 | `automation/state/parity-registry.json` (`RISK_DENY_PDT`, `RISK_DENY_SETTLEMENT` both `"LIVE_ONLY_DIVERGENCE"`) | The backtest engine (`orchestrator.py`) never simulates Rule 7 denials at all — PDT is explicitly neutralized in the sizing-agreement assert, and `cash_settlement` is structurally unreachable (`pdt_gate_mode` never set → defaults to `margin_pdt` → settlement inputs never supplied) | **LIVE finding about the backtest engine**, adversarially verified 2026-08-12 | Not wrong/obsolete on its own — an honest, tested disclosure of a known sim/live divergence, unaffected by the FINRA change (backtest already ignores Rule 7 entirely) | No change — flagged for completeness; relevant context for anyone reading historical backtest trade counts against live PDT-blocked reality |
| 15 | `analysis/recommendations/prereg-pdt-blocked-counterfactual-2026-08-11.json` (`explicitly_forbidden`: *"PDT is a real regulatory rule for live accounts under $25k and is NOT being questioned there"*) | A FROZEN research prereg's guardrail, written 2026-08-11 (before today's research), assumes the $25k PDT rule is settled/current for live accounts | **RESEARCH ARTIFACT**, status `FROZEN_BEFORE_RUNNER` — appears never executed (also listed as an unresolved `SHADOW.md` wikilink) | That specific premise is now contradicted by fact (1) (with the caveat that fact (1) was under independent review as this audit ran, now reportedly confirmed) | **Not edited** — altering a frozen prereg post-hoc would violate the pre-registration/research-integrity discipline this repo otherwise enforces. If/when this prereg is ever run, it needs a companion amendment note or a re-frozen v2 with the corrected premise. **NEEDS-J / NEEDS-EVIDENCE** (unclear whether it ever ran — see below) |
| 16 | `automation/overnight/queue.md:2317` (`PDT-WIRE-FLEET-ARMS`, `status:todo`, `depends:WS2-exit-parity-study-complete`) | An existing queued task to eventually wire real PDT enforcement into fleet arms "before any fleet arm is armed live" | **QUEUE ITEM**, not code | Whenever picked up, must NOT wire the legacy `margin_pdt` $25k/3-trade math | **Not edited** (queue.md is a high-traffic shared append-only file outside this task's declared scope) — flagged here so the eventual implementer finds this audit first via the `risk-rules.md` pointer already added |

---

## Prioritized change list

### SAFE-NOW (done this session)

1. `backtest/lib/risk_gate.py` — corrected the PDT/SETTLEMENT docstring section and the
   `PDT_EQUITY_THRESHOLD`/`PDT_DAY_TRADE_LIMIT` comment: removed the false "both are cash accounts,
   multiplier=1" claim, added the FINRA 2026-06-04 elimination + the 2026-08-18 field-absence
   evidence. **Zero logic changed.**
2. `setup/scripts/settlement_ledger.py` — added an UPDATE paragraph to the module docstring
   correcting the same false account-type premise and framing the settled-cash gate as J's
   voluntary capital-discipline choice, not a regulatory requirement. **Zero logic changed.**
3. `setup/scripts/pdt_tracker.py` — added a second STATUS UPDATE paragraph (2026-08-18) beside the
   existing 2026-07-14 one, correcting the account-type premise and explicitly warning against
   re-arming `fleet_pdt_enforce` against this module's obsolete-rationale count. **Zero logic
   changed.**
4. `markdown/0dte/risk-rules.md` — appended a dated correction under the existing "Rule 7" section
   (kept the 2026-07-08 original verbatim, per doc-architecture fold rule) covering both the
   mechanism drift (cash_settlement/FLEET-PDT-PARITY) and the regulatory drift (FINRA 2026-06-04).

### NEEDS-J

5. **CLAUDE.md Rule 7 text.** Currently states the pre-2026-06-04 margin rule as live doctrine and
   implies a cash-account option Alpaca doesn't sell. This is doctrine text, not a comment — Rule 9
   ("no mid-session rule changes... weekend-ratified, written reason") applies, and this audit's
   headline fact was still under independent re-verification while it ran. Recommend J decide the
   replacement wording once fact (1) is fully settled — likely something like *"PDT count/$25K
   threshold retired by FINRA 2026-06-04 for margin accounts (grace window to 2027-10-20); Alpaca
   accounts are margin, not cash — [name the model actually in force: voluntary settlement-style
   throttle / broker-native intraday-margin trust / whatever J picks]."*
6. **The `cash_settlement` policy question itself.** Not a bug — a deliberate J directive
   (2026-08-09) built on a belief ("I always use cash accounts") that today's research shows
   doesn't match Alpaca's actual product lineup. Three honest options, none silently applied:
   (a) **keep it as-is** — a voluntary, slightly-conservative same-day-entries throttle is a
   defensible risk posture on its own merits, independent of what regulatory rule (if any)
   justifies it; (b) **move to a broker-native model** — trust Alpaca's own new intraday-margin-
   deficit monitoring (now confirmed live on both accounts via the absent-field/`intraday_
   adjustments` evidence) and drop the local settlement simulation; (c) **if a true cash account
   matters to J for other reasons** (habit, discipline, a future non-Alpaca live account), that's a
   broker-choice question per the regulatory doc's Q4 comparison, not an Alpaca-account-settings
   question — Alpaca structurally cannot provide one.
7. **`params.fleet_pdt_enforce` landmine.** Currently `False` everywhere (unset). `fleet_live.py`'s
   own comment already flags the plan to flip it once "the account-type question is settled" — but
   the enforcement target it would flip TO is `margin_pdt`'s obsolete $25k/3-trade math, which would
   instantly jail fleet arms with real day-trade counts of 6-9 (per the 2026-08-06 measurement) on a
   retired rule. **Before this flag is ever set true, the enforcement target must be redesigned**
   (point at `cash_settlement`-style gating, or a broker-native/no-limit mode) — not just flipped
   on top of the existing `margin_pdt` branch. No urgency (nothing is blocked today), but this is
   exactly the kind of loaded gun this audit was asked to find.
8. **`params.json`/`aggressive/params.json`'s `_pdt_gate_mode_doc` fields** still assert the false
   "cash account, multiplier=1" premise (explicitly out of scope for this session — "do NOT edit
   params*.json"). When J or a future session next touches either params file for an unrelated
   reason, fold in the same correction already applied to the sibling `.py` docstrings.

### NEEDS-EVIDENCE

9. **Did `prereg-pdt-blocked-counterfactual-2026-08-11.json` ever actually run?** Status reads
   `FROZEN_BEFORE_RUNNER` and it's listed as an unresolved `SHADOW.md` wikilink — suggests no. If it
   never ran, its stale premise is moot (nothing to correct, just note the frozen file's guardrail
   needs a v2 note before it's ever run). If it DID run and the result was never folded back, that's
   a separate, unrelated gap worth a follow-up check — **not verified either way this session**
   (out of scope — this is a Chef/Kitchen research-pipeline question, not a code-alignment one).
10. **`preopen_readiness.py`'s now-permanently-dead YELLOW `pdt` branch** (#12 above) — harmless,
    but a candidate for cleanup/relabeling once someone is already in that file for another reason.
    Not touched this session (outside the "prove the value, fix the comment" scope — this would be
    a logic/behavior change to a branch, however inert).
11. **Whether `WS2-exit-parity-study-complete` (the `PDT-WIRE-FLEET-ARMS` dependency) has closed** —
    not checked this session; if it has, that queue item may already be actionable, and whoever
    picks it up needs the NEEDS-J #7 redesign, not the original 2026-07-08 spec.

---

## What this audit did NOT check

- **Did not call the Alpaca broker API directly** (per explicit task instruction). All live-account
  numbers in this report are either (a) already on disk from a prior session's live read
  (`PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`, `self-check-last.json`, `circuit-breaker.json`,
  `settlement-ledger.json` — all read directly by this session) or (b) relayed from the
  orchestrator's own fresh broker read, attributed as such, not independently re-run here.
- **Did not independently re-verify fact (1)** (the FINRA rule elimination itself) — that was
  explicitly another agent's job, running in parallel. This report cites the research doc and the
  orchestrator's relay of that re-verification's outcome, but did not re-fetch any FINRA/SEC source.
- **Did not run the test suite.** No `pytest` invocation this session — the four edits made are
  comment/docstring-only inside otherwise-untouched files, and none of the existing guard tests
  (`test_risk_gate.py`, `test_settlement_ledger.py`, `test_pdt_gate_mode_cash_parity_2026_08_09.py`,
  `test_fleet_pdt_parity.py`, `test_self_check_pdt_status.py`, `test_fast_path_pdt_gap_2026_08_12.py`)
  assert on docstring text, so none should be affected — but this was not empirically confirmed by
  running them.
- **Did not check every file the initial `pdt_gate_mode`/`cash_settlement`/`margin_pdt` greps
  surfaced** (~180 files total across the three searches). Triaged to: live order-path code
  (`heartbeat_core.py`, `fleet_executor.py`, `fleet_live.py`, `risk_gate.py`, `settlement_ledger.py`,
  `pdt_tracker.py`), the visibility surfaces that render PDT status (`self_check.py`, `firm_brief.py`,
  `preopen_readiness.py`), doctrine (`CLAUDE.md`, `risk-rules.md`), the backtest-parity registry, and
  one frozen prereg. Did **not** individually open every dated `EOD-*.md`/`fill-funnel-*.json`
  historical log file the grep matched (dozens) — these are point-in-time records of past
  `RISK_DENY_PDT` events under the old `margin_pdt` regime; they are historical fact, not live
  code, and don't need correcting.
- **Did not check `analysis/swarm-consult/*` or `strategy/candidates/*` PDT mentions** — these are
  free-model research/ideation artifacts (Chef/swarm output), not code or doctrine; a stale
  regulatory assumption inside an old ideation doc doesn't gate anything.
- **Did not determine whether Alpaca's 18-month firm-level grace window (to 2027-10-20) could still
  apply to OUR accounts by contract even though the field evidence shows the new-regime schema.**
  The orchestrator's field-absence finding is strong circumstantial evidence our accounts are on
  the new regime, but this session did not read Alpaca's Customer Agreement Section 32 text again
  (already quoted in the source research doc) to check for any account-specific carve-out language
  beyond what that doc already flagged as unresolved.
- **Did not touch, arm, or flip any gate, flag, or params file**, per explicit instruction.
