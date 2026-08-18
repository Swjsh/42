# THE ROADMAP — Project Gamma, one canonical statement

> **This is the ONE place the roadmap lives.** Every other doc that used to restate a
> destination, threshold, or milestone now points here instead. Written 2026-08-18 ~18:40 ET
> per J's directive: *"there is no single statement of the roadmap... make sure everything is
> properly aligned to future proof ourselves."* Consolidation audit, not a strategy change —
> **nothing in this document arms anything, edits params, or changes rule semantics.**
>
> **How to read this doc:** every claim is tagged **RATIFIED** (in force now, code/doctrine
> agrees), **PROPOSED** (written, awaiting J, not yet acted on), or **OPEN QUESTION** (no
> answer exists yet — stated as a question, not invented). Every number carries its source and
> date. Where a gate's pass/fail criterion isn't actually wired to code, this doc says
> **"criterion undefined"** rather than inventing one.

---

## 1. The destination

**SPY 0DTE directional options, trading real money, sized off a compounding equity curve —
reached only through gates that have already cleared with evidence, never by decree.**

The concrete form of "success" is defined narrowly and deliberately (`markdown/doctrine/FOCUS-DOCTRINE.md`,
J-directed 2026-07-22, recorrected 2026-08-09 — **RATIFIED, currently in force**):

- **$100–200/day is the target, evaluated PER ACCOUNT, never as a combined book number.** One
  clean +30%-premium level trade pays one account's day. A strong arm's number must never mask
  a weak arm's miss (J's correction, 2026-08-09 — see `feedback_daily_target_per_account_2026_08_09.md`
  in session memory). Summed across whatever accounts are active, the book-wide figure is a
  secondary rollup, reported *after* the per-account read, never instead of it.
- **Scaling comes from compounding the tier, not from more trades per day at the same tier**
  (FOCUS-DOCTRINE §1). Equity climbs in stages; the strategy doesn't change shape to chase a
  bigger number at the same account size.
- **The research lane stays bounded to level interaction** (rejection, reclaim, S/R flip+retest,
  range ping-pong) — FOCUS-DOCTRINE §2. This roadmap doesn't relitigate that; it's cited here
  because "the destination" includes *how* Gamma is allowed to get there, not just the dollar
  figure.

**This paper-trading program's entire purpose is to earn the right to trade real money.**
Nothing here is live. OP-0 #1 (`CLAUDE.md`) means arming live money is the one category of
decision that always needs J — this doc does not, and cannot, change that.

---

## 2. Current position — every number sourced and dated

| Fact | Value | Source | Verified |
|---|---|---|---|
| Safe-2 equity | **$5,266.38** | `mcp__alpaca__get_account_info` (account `PA3POKNV46VG`), live pull this session | 2026-08-18, fresh this session (also matches `CLAUDE.md:57`, commit `ac9e84a7`) |
| Bold-2 equity | **$5,048.40** | `mcp__alpaca_aggressive__get_account_info` (account `PA3WEBXJU67N`), live pull this session | 2026-08-18, fresh this session (also matches `CLAUDE.md:58`) |
| Account shape | **Margin-shaped, NOT cash** — `multiplier="4"` on both, confirmed by this session's live pull and by `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md` | Alpaca live account read | 2026-08-06 and 2026-08-18, consistent |
| Rule version | Safe v15.3 (ratified live 2026-06-01) · Bold v15.2 | `CLAUDE.md:30` | current |
| Trading mode | **PAPER only.** No live-money account exists. | `automation/state/fleet/accounts.json` (`live` field null/absent on both core arms); OP-0 #1 | current |
| Active real-fills arms | 5 — safe-2, bold-2 (core), safe-3, risky-1, risky-3 (fleet) | `automation/state/fleet/accounts.json` grid | current, since 2026-06-25 grid rebuild |
| Fleet correlation | **r = 0.846 (r² = 0.716), 95.7% sign agreement, 139 matched trade pairs — every one of 15 pairwise daily correlations positive.** The 5-arm book is "one bet in five sizes," not five diversified strategies. | `analysis/deep-research/LEVER-CORRELATION-2026-08-06.md` — 47/47 assertions independently re-derived by a second code path (`lever_correlation_verify_2026_08_06.py`) | 2026-08-06; 2026-08-16 forward-check confirmed the correlation persists |
| PDT config (live, both core arms) | `pdt_gate_mode: "cash_settlement"` | `automation/state/params.json:10`, `automation/state/aggressive/params.json:4` | current on disk, 2026-08-18 |

---

## 3. The gates between here and the destination

These are not strictly sequential — some run in parallel — but this is the dependency order.
Each row states what the gate needs as **evidence**, not what would be convenient.

```mermaid
flowchart TD
  A["NOW: 5 paper arms\nr=0.846, one bet in\nfive sizes"] --> B["Gate 1: Strategy\nratification (OP-11)\nRATIFIED + enforced"]
  A --> C["Gate 2: Per-account\npaper threshold\nCRITERION PARTIAL"]
  A --> D["Gate 3: Regulatory/\nbroker premise\nOPEN QUESTION"]
  B --> E["Gate 4: One-account\nconsolidation decision\nPROPOSED, not ratified"]
  C --> E
  D --> E
  E --> F["Gate 5: Conviction /\nsizing validated\nOPEN, in progress"]
  F --> G["Gate 6: Live-money\narming (OP-0 #1)\nalways needs J"]
  G --> H["DESTINATION:\nlive-money trading,\ncompounding tiers"]
```

| # | Gate | Status | What it requires as evidence | Current state |
|---|---|---|---|---|
| 1 | **Strategy ratification** (which edges are even allowed to trade) | **RATIFIED, actively enforced** | OOS positive AND WF ≥ 0.70 AND sub-window stable AND anchor-no-regression AND evidence_n (`CLAUDE.md` OP-11 says ≥15, **advisory**; `accounts.json#promotion_gate.min_clean_trades` says **30**, appears to be what's actually consumed — see Contradiction #2) | Live and enforced across dozens of `backtest/autoresearch/validate_*.py` scripts (e.g. `validate_level_family.py:477`: *"Gates: deduped n>=20 AND WR>=45% AND exp>0 AND real-fills exp>0 AND anchor-no-regression"*) |
| 2 | **Per-account paper-to-live threshold** | **Criterion PARTIALLY DEFINED** | `CLAUDE.md:65`: ≥20 trades, WR≥45%, positive expectancy, ≤2 rule breaks, **per account independently** | Trade count / WR / expectancy are computable from `journal/trades.csv`. **No script was found that computes this exact 4-condition tuple at the account level.** The only wiring found is `.claude/agents/treasurer.md:135`'s narrative "Live threshold status \| M/4 conditions met" table — a persona template, not an automated check. **"Rule breaks ≤2" has no found automated tally at account scope.** This is the gate CLAUDE.md's account table has always pointed to as "the" live threshold, and it is less automated than it reads. |
| 3 | **Regulatory / broker premise resolved** | **OPEN QUESTION** | Confirm which PDT regime actually applies to Safe-2/Bold-2 specifically; confirm the cash-vs-margin premise the code runs on | See §5 below — Alpaca's contract reserves the right to keep legacy PDT per-account during its 18-month phase-in (through 2027-10-20); this was never independently confirmed against Gamma's own two accounts. Separately, Alpaca sells no true cash-account product at all — a structural fact, not a config toggle — yet both core arms' live `pdt_gate_mode` is `cash_settlement`. |
| 4 | **One-account consolidation decision** | **PROPOSED — not ratified** | J's explicit go-ahead; `ONE-ACCOUNT-TRANSITION-2026-08-18.md` explicitly self-labels "PLANNING / DOCUMENTATION ONLY... Live arming needs J (OP-0 #1)" | Recommendation on the table: ONE live account (the product) + the paper fleet continues as the laboratory. Directly reframes `CLAUDE.md:64`'s "both accounts grow" language — see Contradiction #1. |
| 5 | **Conviction / sizing gates validated** | **OPEN, in progress** | Per `ONE-ACCOUNT-TRANSITION-2026-08-18.md` §6: (a) conviction v0 or v2 demonstrates measurable separation (blocked trades worse than allowed trades) over enough paired rows post-fix; (b) `min_contracts_equity_scaled` re-arms ONLY on that validated gate; (c) strike question settled by the strike matrix, not intuition; (d) this document's regulatory picture confirmed | Conviction v2 shipped 2026-08-18 (shadow). Its own doc is explicit: v2 fixes *blindness* (can now see the paying lane) but its *discrimination* power (the quality bar) is UNPROVEN — "do not read v2 as 'conviction fixed.'" |
| 6 | **Live-money arming** | **Always needs J (OP-0 #1)** | No criterion beyond "the gates above have cleared" is defined anywhere in the repo | **Criterion undefined beyond J's judgment call.** This is by design (OP-0 #1) — not a gap to fix, a line that should never be automated. |

---

## 4. RATIFIED vs PROPOSED vs OPEN QUESTION — the compressed view

| Statement | Status |
|---|---|
| $100–200/day per account is the success bar | **RATIFIED** (FOCUS-DOCTRINE, J 2026-07-22 / recorrected 2026-08-09) |
| Strategy ratify gate (OOS+WF+sub-window+anchor) | **RATIFIED**, enforced in code |
| Per-account paper→live threshold (20 trades/45% WR/+exp/≤2 breaks) | **RATIFIED as doctrine, but criterion partially undefined in code** (Gate 2 above) |
| "Both accounts grow $5K→$10K→$25K+" | **STALE FRAME — see §5.** Not false, but no longer the sharpest statement of the destination given the r=0.846 finding. |
| ONE live account + paper fleet as laboratory | **PROPOSED**, 2026-08-18, awaiting J |
| $25K as a hard milestone | **REFRAMED, not deleted — see §5.** It was a regulatory floor; that floor no longer exists at the FINRA level. |
| `pdt_gate_mode=cash_settlement` on both core arms | **LIVE IN CODE**, resting on a premise (this is a cash account) that broker reads say is false |
| Conviction v2 "fixes" ranking | **FALSE — explicitly disclaimed by its own doc.** It fixes visibility, not discrimination. |
| Live-money arming criteria | **OPEN QUESTION** — undefined beyond "J decides," which is intentional |

---

## 5. What changed and why

### 5a. The $25K milestone — reframed, not deleted

**Where it came from.** `CLAUDE.md:64` reads *"Goal: Both accounts grow → $5K → $10K → $25K+."*
`CLAUDE.md:44` (Rule 7) reads *"PDT awareness. Under $25K: 3 day-trades per rolling 5 business
days (margin) or respect settlement (cash)."* Read together, $25K was never picked as an
arbitrary "big number" — it is the classic FINRA pattern-day-trader (PDT) equity floor: below
it, a margin account restricted to 3–4 day-trades per rolling 5 business days.

**What changed.** `markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`
(commissioned by J tonight, primary sources fetched and quoted directly) confirms: **FINRA
eliminated the $25,000 PDT floor and the day-trade-count trigger for margin accounts**, via
Rule 4210 amendment SR-FINRA-2025-017, SEC-approved 2026-04-14, **effective 2026-06-04**
— replaced by a continuous "intraday margin deficit" (IML) solvency check instead of a fixed
dollar wall. 0DTE options are explicitly named in FINRA's own rulemaking record as a gap the
old rule missed and the new one covers.

**So is $25K dead as a number? No — but its MEANING changed, and this is the reframe:**

- **$25K is no longer a regulatory wall Gamma must climb to unlock day-trading.** That
  specific mechanical reason for the milestone is gone as of 2026-06-04.
- **$25K remains a legitimate milestone for an entirely different reason: it is simply the
  next compounding step after $10K**, same as $5K→$10K was a step, not a regulatory unlock.
  Keeping it in the roadmap is honest **only if it's labeled as an equity-growth waypoint, not
  a rule the account is chasing permission from.**
- **The floor is not cleanly gone for Gamma specifically.** Three live caveats, all sourced in
  the regulatory doc:
  1. FINRA gives member firms up to **18 months to fully implement, through 2027-10-20**, and
     Alpaca's own Customer Agreement (Section 32, quoted directly in the regulatory doc)
     **reserves the right to keep legacy PDT on specific accounts during that window** — this
     was never independently confirmed against Safe-2 (`PA3POKNV46VG`) or Bold-2
     (`PA3WEBXJU67N`) specifically.
  2. **Alpaca sells no true cash-account product at all** ("We do not offer cash accounts. All
     accounts are set up as margin accounts" — Alpaca support page, fetched directly
     2026-08-18). This directly conflicts with the `pdt_gate_mode=cash_settlement` premise
     currently live on both core arms (§2 above, Contradiction #3 below).
  3. `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md` independently found, from a live broker read
     twelve days before the regulatory doc: Alpaca PAPER reports **no PDT telemetry at all**
     (`pattern_day_trader`/`daytrade_count` both `null` on every arm) and demonstrably does not
     enforce day-trade counts in practice — consistent with, but not proof of, the new regime.

**Net effect on this roadmap:** $25K stays as a compounding waypoint ($5K → $10K → $25K+),
**relabeled** from "the wall PDT makes us climb" to "the next tier once $10K is reached" —
and Rule 7's PDT framing is flagged as needing J's explicit review (§7, Open Question), because
rewriting one of the 10 rules is not a docs-consolidation act (Rule 9: rules change on weekends,
in writing, with documented reason) — this document surfaces it, it does not resolve it.

### 5b. "Both accounts grow" vs the one-account proposal

**Where it came from.** `markdown/0dte/dual-account-design.md` (ratified 2026-05-14) built the
premise: *"At $1K–$25K, what risk profile — tight stops/early TP vs wide stops/late TP —
produces better compounding?"* Two accounts, same signal, different expression, paired
observations. `CLAUDE.md:64` still frames the goal as "Both accounts grow."

**What changed.** The fleet grew from 2 accounts to 5 arms (2026-06-25 grid rebuild), and
`LEVER-CORRELATION-2026-08-06.md` (§2 above) measured what that fleet actually produces:
**r=0.846, 95.7% sign agreement.** The arms do not behave as 5 independent bets — they behave
as one directional call, scaled 5 ways. `ONE-ACCOUNT-TRANSITION-2026-08-18.md` draws the
direct conclusion tonight: *"Today read as '+$162 across two arms.' On one account it is simply:
one signal → 8 contracts of 768P → +$162."*

**The proposal on the table (PROPOSED, not ratified):** ONE live account (the product) +
the paper fleet continues running beside it (the laboratory) — same shared signal, different
gates, zero capital at risk in the lab. This is explicitly J's own reasoning in that document
("I prefer to do one, but just thinking out loud"), written up with the supporting evidence,
**not yet an instruction to execute.**

**This is a genuine, live conflict with `CLAUDE.md:64`'s current wording**, which this document
resolves by pointer (§6, CLAUDE.md fold) rather than by silently picking a side — the choice
between "grow both accounts" and "consolidate to one" is J's, not a docs-audit's, to make.

---

## 6. Contradictions found — both sides cited

| # | Contradiction | Side A | Side B | Resolution here |
|---|---|---|---|---|
| 1 | Both-accounts-grow vs one-account proposal | `CLAUDE.md:64` — *"Both accounts grow → $5K → $10K → $25K+. Dual-account experiment answers which risk profile compounds better."* | `markdown/planning/ONE-ACCOUNT-TRANSITION-2026-08-18.md:15-22` — the fleet is r=0.846 correlated, "one bet in five sizes," so the dual-account experiment's original question is already answered (they don't diverge) | Presented as PROPOSED vs RATIFIED in §4; CLAUDE.md's Goal line now points here instead of asserting either side (§8) |
| 2 | Strategy-ratify evidence_n: 15 vs 30 | `CLAUDE.md` OP-11 — *"evidence_n ≥ 15 is advisory"* | `automation/state/fleet/accounts.json#promotion_gate.min_clean_trades` = **30**, with no "advisory" qualifier — reads as the actual number code would check | Flagged as Open Question §7; not resolved here — do not assume which one governs without reading the consuming code path fresh |
| 3 | `cash_settlement` premise vs broker reality | `automation/state/params.json:10` / `automation/state/aggressive/params.json:4` — `pdt_gate_mode: "cash_settlement"`, live on both core arms today | `markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md:98` — *"No, we do not offer cash accounts. All accounts are set up as margin accounts"* (Alpaca, quoted directly); `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md:16` — live broker read shows `multiplier=4` (margin-shaped) on every arm | Flagged as Open Question §7 — this is a live code premise, not a stale doc, and outside this audit's mandate to change (no params edits) |
| 4 | $25K: regulatory wall vs compounding waypoint | `CLAUDE.md:44` (Rule 7) — frames $25K as the PDT unlock threshold | `markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md` — FINRA eliminated that floor 2026-06-04 (with the phase-in caveats above) | Reframed in §5a; Rule 7 itself is NOT edited by this audit (rule changes need J, in writing, per Rule 9) — flagged §7 |
| 5 | Account identifiers stale in 3 places | `CLAUDE.md:57-58` (current, fixed tonight, commit `ac9e84a7`) — `PA3POKNV46VG` / `PA3WEBXJU67N` | `markdown/specs/ARCHITECTURE.md:196` still cites `PA3DHPT7KIQE` / `PA33W2KUAT40` ("Date of Last Update: 2026-07-11"); `markdown/0dte/dual-account-design.md:11` still cites the same two dead identifiers | ARCHITECTURE.md corrected as part of this audit (§8); dual-account-design.md gets a pointer note, not a full rewrite (out of scope — it's a frozen 2026-05-14 design record) |
| 6 | Superseded strike-tier ladder repeated as current | `CLAUDE.md:30` — *"live truth (fills-verified 2026-07-11): core Safe trades ATM... params.json's ladder is vestigial"* | `markdown/specs/ARCHITECTURE.md:197` still states the old ladder ("OTM-3 $1K / OTM-2 $2-10K / OTM-1 $10-25K / ITM-2 $25K+") as current strategy | Corrected as part of this audit (§8) |
| 7 | Daily P&L target: per-account vs book-wide | — checked for this explicitly, per the task brief — | `CLAUDE.md:66`, `FOCUS-DOCTRINE.md:13-19`, and `.claude/agents/treasurer.md` **all already frame per-account-first, book-wide-secondary**, consistent with J's 2026-08-09 correction | **No live contradiction found.** Stated here so the check is on record, not because a fix was needed. |
| 8 | "THE ROADMAP" mislabeled | `markdown/doctrine/FABLE-HANDOFF.md:44` — section literally titled *"THE ROADMAP,"* dated 2026-07-02, an execution queue (RISKY-ARM GATE TIERS, COOLDOWN A/B, etc.) 47 days stale as of this audit | This document | FABLE-HANDOFF.md §4 retitled with a pointer here (§8); its historical content is left intact as a frozen record, not deleted |
| 9 | "Live threshold" gate looks automated but mostly isn't | `CLAUDE.md:65` states it as a flat 4-condition bar | No script found that computes all 4 conditions at account scope (Gate 2, §3) — only `treasurer.md`'s narrative M/4 tracking | Documented honestly in Gate 2 rather than asserting it's enforced when the evidence doesn't show that |

---

## 7. Open questions for J — no invented answers

1. **PDT regime for Safe-2/Bold-2 specifically.** Alpaca's contract reserves the right to keep
   legacy PDT per-account during its phase-in (through 2027-10-20). Nobody has pulled a
   confirmation of which regime applies to these two accounts by name. (Low urgency on paper —
   Alpaca paper shows zero PDT enforcement in practice — but load-bearing before real money.)
2. **`pdt_gate_mode=cash_settlement` — intentional or drifted?** Both core arms run this mode
   today. The "these are cash accounts" premise it was originally built on is now confirmed
   false at the product level (Alpaca sells no cash accounts). This may already be J's
   considered choice (it matches "Option A: match the broker" from
   `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`) — but that decision was never explicitly closed
   out in writing against tonight's regulatory findings. Worth a one-line confirmation, not a
   re-litigation.
3. **Rule 7's PDT text.** Now describes a floor that no longer binds at the FINRA level (with
   the phase-in caveats above). This audit does not touch the 10 rules — that needs J, in
   writing, per Rule 9. Left exactly as-is pending that review.
4. **Strategy-ratify evidence_n: 15 (advisory, CLAUDE.md) vs 30 (accounts.json, no "advisory"
   qualifier).** Same gate, two numbers. Which one actually gates a ship decision today wasn't
   traced to a single consuming code path in this audit — flagged rather than guessed.
5. **The one-account proposal itself.** `ONE-ACCOUNT-TRANSITION-2026-08-18.md` is a
   recommendation, not a decision. This roadmap reflects it as PROPOSED. It becomes RATIFIED
   only when J says so, at which point this section (and `CLAUDE.md`'s account-context table)
   both need a same-day update.
6. **Account-level "Live threshold" — build the missing instrument, or drop the claim?** Gate 2
   (§3) is stated as doctrine but not fully wired. Either an automated per-account check should
   exist (trade count + WR are already computable from `trades.csv`; "rule breaks ≤2" needs a
   tally against `journal/mistakes.md`), or the doctrine should say plainly that it's a manual
   treasurer judgment call, not a script. Leaving it stated-but-unwired risks someone assuming
   it already gates something.

---

## 8. What this document folded — pointers replacing restatement

Per `markdown/infra/DOC-ARCHITECTURE.md`'s fold protocol (OP-22: compound, don't accumulate).
Nothing below lost information — dated/frozen records keep their content; only the *current
destination/gate* framing was replaced with a pointer to this file.

| Doc | What changed |
|---|---|
| `CLAUDE.md` (lines 64-65) | "Goal" and "Live threshold" prose folded to a pointer here + the $25K reframe stated inline in one line (Tier-1 stays lean; detail lives here) |
| `markdown/doctrine/FABLE-HANDOFF.md` §4 | Retitled to mark it a **2026-07-02 historical snapshot**, not the live roadmap; pointer added to this file. Fable's original content is untouched below the new note. |
| `markdown/specs/ARCHITECTURE.md` §9 | "Roadmap (current)" replaced with a pointer here (the infra work-items that were listed there are tactical backlog, not destination/gates — cross-referenced to `FUTURE-IMPROVEMENTS.md` instead) |
| `markdown/specs/ARCHITECTURE.md` §10 | Stale account identifiers (`PA3DHPT7KIQE`/`PA33W2KUAT40`) and the superseded OTM-ladder sentence corrected to match `CLAUDE.md`'s current truth; "Date of Last Update" bumped |
| `markdown/0dte/dual-account-design.md` | Pointer note added under the existing staleness banner, directing to this file's §5b for the current state of the "which risk profile compounds better" question. Content otherwise untouched — it's a frozen 2026-05-14 design record, not a duplicate to delete. |
| `markdown/README.md` | This file added to the `planning/` row's living-doc list |

**Not folded, and why:**
- `markdown/planning/FUTURE-IMPROVEMENTS.md` — a tactical engineering backlog (TODOs with
  triggers/scope/estimates), not a destination/milestone statement. Cited here as a source,
  left as-is.
- `automation/overnight/STATUS.md`, `automation/overnight/queue.md` — live, actively-written
  operational logs with uncommitted changes at audit time; per this audit's own instructions,
  left untouched and reported rather than edited.
- `MAP.md` / `HOME.md` / `SHADOW.md` — generated surfaces (`setup/scripts/obsidian_vault_sync.py`).
  Never hand-edited. They will pick up this file's existence on their next regeneration via
  `markdown/README.md`'s index.
- `markdown/planning/AUTONOMY-ROADMAP.md`, `LIVE-PATH-WORKPACKAGE.md` — large (107KB/313KB)
  dated-snapshot archives already self-described as "folded from dated one-offs... superseded
  snapshots frozen verbatim in the appendix." They are engineering-phase histories (Phase
  0/1/2/3 build sequencing), not statements of the trading destination/milestone roadmap this
  document consolidates. Out of this audit's scope; flagged here only so the next session
  doesn't assume they were missed.

---

## 9. Source index

| Claim | File | Verified |
|---|---|---|
| Safe-2 / Bold-2 equity | Live `mcp__alpaca__*` / `mcp__alpaca_aggressive__*` pulls | 2026-08-18, this session |
| Fleet correlation r=0.846 | `analysis/deep-research/LEVER-CORRELATION-2026-08-06.md` + `.json` | 2026-08-06, 47/47 assertions re-verified; 2026-08-16 forward-check |
| PDT/$25K regulatory finding | `markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md` | 2026-08-18, primary sources fetched directly (FINRA, SEC, Alpaca contract text) |
| Broker account-type facts | `analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md` | 2026-08-06, live broker reads |
| One-account proposal | `markdown/planning/ONE-ACCOUNT-TRANSITION-2026-08-18.md` | 2026-08-18, J-directed, PROPOSED status explicit in the doc itself |
| Strategy ratify gate in force | `backtest/autoresearch/validate_level_family.py`, `validate_breakout_family.py`, and ~15 sibling scripts | grepped live 2026-08-18 |
| Daily target per-account | `markdown/doctrine/FOCUS-DOCTRINE.md` | J-directed 2026-07-22, recorrected 2026-08-09 |

---

[[CLAUDE|CLAUDE.md]] · [[markdown/README|doc index]] · [[markdown/planning/ONE-ACCOUNT-TRANSITION-2026-08-18|one-account proposal]] · [[markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18|regulatory landscape]]
