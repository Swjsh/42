# Rule-Engine Alignment Audit — 2026-08-18

> J's question, verbatim intent: *"Do we have all of our rules? And do we have them all aligned with the
> engine? ... if we over trade one day and spend money we don't have, does the engine know about that?
> And other things of this nature that I'm not mentioning."* This document answers that literally: for
> every rule this project claims to enforce, is it ACTUALLY enforced in code, or honour-system prose —
> traced by reading the actual call sites, not by trusting a comment or a constant's existence.
>
> Scope: CLAUDE.md's "The 10 rules" (lines 38-47) + `markdown/0dte/risk-rules.md`. Method: read the two
> live execution paths — `setup/scripts/heartbeat_core.py` (core: safe-2, bold-2, `mcp_heartbeat`
> execution) and `automation/state/fleet/fleet_executor.py` + `fleet_live.py` (fleet: safe-3, risky-1,
> risky-3, `fleet_rest` execution) — and traced every rule to its actual read path. AUDIT ONLY: no gate
> changed, no `params*.json` edited, nothing armed. Two proven-stale doctrine passages were corrected in
> `markdown/0dte/risk-rules.md` (append-only, matching that doc's own correction style) — see the Rule-4
> and Rule-3 rows below.

---

## VERDICT

**7 of 10 rules are genuinely enforced in code on BOTH paths with no material gap. 2 of 10 are
PARTIALLY enforced (a real asymmetry between core and fleet, or between the rule's literal words and
what the automated path actually does). 1 of 10 — no mid-session rule changes — is HONOUR-SYSTEM ONLY:
`params.json` is read fresh from disk on every tick (`heartbeat_core.py:1454`), so a same-day edit takes
live effect within about one minute, with zero code that detects or blocks it intraday.**

**The single biggest gap is NOT one of the 10 named rules — it's the thing underneath J's own worry:
there is no book-level exposure ceiling across the 5 correlated arms.** Each of the 5 SPY arms
(safe-2, bold-2, safe-3, risky-1, risky-3) is a separate real Alpaca paper account with its own isolated
per-account kill switch and risk cap — those work correctly and independently. But all 5 consume ONE
shared signal (`build_shared_signal.py`, documented r=0.846 correlation,
`analysis/deep-research/LIVE-READINESS-FIRST-READING-2026-08-18.md`), and nothing anywhere sums or caps
what they can do SIMULTANEOUSLY. MAP.md's own words: *"on 08-07 all four bought the same contract within
15 seconds."* Computed from TODAY's real per-arm equities (`journal/2026-08-18.md`'s EOD table), a single
correlated tick could commit **~$10,279 of the ~$24,518 book (about 42%) to one same-direction bet**,
and no code measures this, let alone caps it. Full detail in its own section below.

**Runner-up gap:** Rule 8 (journal every trade in real time) is honour-system for the part that's actually
load-bearing — the pre-trade narrative thesis. Verified live against TODAY's journal: two real fills
(safe-2 14:36 ET, bold-2 14:40 ET) and the manual `## Trades` section of `journal/2026-08-18.md` is
empty; the only record is a mechanical EOD table written at 16:45:01 ET by `obsidian_vault_sync.py`,
40-65 minutes after the fills and after both had already closed.

---

## The 10 rules — enforcement table

| # | Rule | Enforcement | File:line (the actual read path) | Core path | Fleet path | On violation |
|---|---|---|---|---|---|---|
| 1 | No setup, no trade | **PARTIALLY ENFORCED** | `automation/state/fleet/strategies.py:102,125,160,188` (`entry_setups` tuples) + `build_shared_signal.py:734,788` (`ENTRY_TRIGGERS` frozenset, `trig_ok = bool(fired) and (trigger in ENTRY_TRIGGERS)`) | Yes — reads the same shared-signal producer | Yes — same producer, `strategies.py` runs on every arm (`accounts.json:2` "EVERY validated strategy... runs on EVERY account") | No ENTER is ever constructed (fail-closed to HOLD) — but see caveat |
| 2 | Wait for the trigger (no anticipation) | **ENFORCED** | `build_shared_signal.py:788` (`fired` must be True AND trigger in allowlist) + `fleet_live.py:100-102` (`SIGNAL_MAX_AGE_SEC` staleness refusal, `signal_stale_{age}s`) | Yes | Yes | Fail-closed to HOLD / `signal_stale_*` skip |
| 3 | Defined stop on entry, stated before entry | **ENFORCED** (software-polled, not broker-resident — see correction below) | Stop level computed+stored: `exit_manager.py` `ExitState.from_entry`, `runner_stop = entry*(1+premium_stop_pct)` (`exit_manager.py:440`); enforced by: `exit_manager.py:140,514,632` (`_structure_stop_hit`, checked once per tick) | Yes, same `exit_manager.py` | Yes, same `exit_manager.py` | Stop only fires when a LATER tick evaluates it (~1/min RTH) — no exchange-resident stop order exists for options (Alpaca rejects bracket/OTO on options; confirmed no `order_class=` call anywhere in `heartbeat_core.py`) |
| 4 | No adding without a NEW confirmed trigger | **ENFORCED** (the CLAUDE.md rule as literally written) | `risk_gate.py:494-503` (`CODE_NOT_FLAT`) + `heartbeat_core.py:2413` (`fb.is_flat_spy_options`) | Yes | Yes, same `check_order` call | Deny → HOLD, no order placed |
| 5 | Daily loss kill switch, per account, isolated (Safe −30% / Bold −50%) | **ENFORCED**, thresholds consistent across paths | `risk_gate.py:399-414` (`CODE_KILL_SWITCH`, dual trigger: latch OR drawdown floor) | `heartbeat_core.py:2402` (`killed = cb.get("tripped") or kill-switch file`), per-account circuit-breaker | `fleet_live.py:106-108` (`_limit_pct_for`: 0.30 safe-prefixed / 0.50 else) + `fleet_live.py:150-170` (`_load_or_arm_breaker`, PER-ARM file under `FLEET_DIR/<arm_id>/`) | Deny → HOLD; 5 separate real Alpaca accounts (`accounts.json`) so isolation is real, not just a flag |
| 6 | Per-trade risk cap per account (Safe 30% / Bold 50%), min 3 contracts | **ENFORCED**, thresholds consistent | `risk_gate.py:513-560` (`CODE_MIN_CONTRACTS` / `CODE_RISK_CAP` / `CODE_MAX_PREMIUM_TIER`) | `params.json:274-275,88` (0.3, 3) | `fleet_executor.py:1290-1310` (`_base_params_for`/`_params_for` re-read the SAME base Safe/Bold `params.json`) | Deny → HOLD |
| 7 | PDT awareness | **PARTIALLY ENFORCED — asymmetric by path** | See dedicated section below | Real mechanism, different from the doctrine's literal text (settled-cash gate, not day-trade count) — `risk_gate.py:420-481`, fed by `settlement_ledger.py` | Structurally inert by design — `fleet_executor.py:1212-1224` forces `pdt_gate_mode="margin_pdt"` fed a day-trade count that is always 0 unless `fleet_pdt_enforce` (default False) | Core: hard Deny (`CODE_SETTLEMENT`). Fleet: never fires (0 >= 3 is never true) |
| 8 | Journal every trade in real time | **PARTIALLY ENFORCED → effectively HONOUR-SYSTEM for "real time"** | See dedicated finding below | Machine ledger (`core-decisions.jsonl`) IS real-time; narrative journal + `trades.csv` are NOT | Same architecture, same gap | No block of any kind — a fill can be placed with zero pre-trade thesis ever written |
| 9 | No mid-session rule changes | **HONOUR-SYSTEM ONLY** | `heartbeat_core.py:1454` (`params = json.loads(cfg["params"].read_text(...))`, fresh disk read every tick); `fleet_executor.py:1290-1299` same pattern | Zero technical barrier | Zero technical barrier | Nothing — a same-day edit takes effect on the next ~1-minute tick. Only mitigant: `premarket_deterministic_fallback.py:463-475`'s `compute_rule_version_pin`, which runs ONCE at ~08:30 ET and cannot see an 11am edit |
| 10 | Gamma flags a violation → the trade does not happen | **ENFORCED** (verified by reading the call sites, not assumed) | `heartbeat_core.py:2494` (`if not decision.allowed: ...RISK_DENY_*`) and `fleet_executor.py:1270-1281` (`if not decision.allowed: return ArmDecision(..., "HOLD", ...)`) | Confirmed: no code path found that places an order after a Deny | Confirmed same | This rule's strength is exactly as strong as whichever underlying rule fired it — it's the delivery mechanism for 4/5/6/7, not an independent check |

### Rule-by-rule caveats that don't fit in the table

**Rule 1 caveat — the playbook and the code have already drifted.** `markdown/0dte/playbook.md` is the
document Rule 1 names as authoritative ("a named pattern in playbook.md"). Cross-checked its headers
against every setup name live in `strategies.py`/`build_shared_signal.py`:

- **`VWAP_RECLAIM_FAILED_BREAK` trades live** (it's `J_VWAP_RECLAIM_FB`, edge #2, with its own validated
  ITM-2 Bold cell documented in `automation/state/aggressive/params.json:98-109`, and its own per-setup
  risk_gate stop override, `risk_gate.py:882-890`) **but does not appear anywhere in `playbook.md`**
  (grepped both the exact code name and the lowercase form — zero hits). A literal reading of Rule 1
  says these trades have no named pattern in the file the rule cites.
- **`GAP_AND_GO` is documented in `playbook.md:259`** as a live setup (not filed under the "NOT YET
  TRADABLE" candidates section that starts at line 282) **but is wired nowhere in code** — zero hits in
  `strategies.py`, `build_shared_signal.py`, `heartbeat_core.py`, or `filters.py`. It cannot fire; the
  playbook describes a trade the engine has never been able to take.

Nothing cross-validates `playbook.md` against the code's own setup registry, so the two can silently
diverge — and already have, in both directions. Rule 1 downgraded from ENFORCED to PARTIALLY ENFORCED
for exactly this reason: the CODE enforces "must match code's OWN named-setup registry," which is real
and effective, but does NOT enforce "must match `playbook.md`" — the two registries aren't the same list.

**Rule 3 / Rule 4 corrections — made directly in `markdown/0dte/risk-rules.md` this audit** (licensed
under "may fix proven documentation staleness," appended in the doc's own established correction style,
original text preserved verbatim):
- The "Bracket-order execution" section described `order_class="oto"`/naked-limit as a rare *fallback*.
  Code shows it's the only path that has ever run (Alpaca rejects bracket/OTO on options every time, not
  occasionally) — corrected in place.
- The "First-entry rule" section (no 2nd entry on a setup that stopped out today) is **deleted from
  code** (`risk_gate.py:92-96,505-510`, explicit "DELETED (J directive 2026-07-02)" comment) but was
  still described in present tense as a live rule — corrected in place.

---

## J's specific worry: "if we over-trade one day and spend money we don't have, does the engine know?"

### Does anything track buying power / settled cash before placing an order?

**Yes for core (safe-2, bold-2). No for fleet (safe-3, risky-1, risky-3) — by deliberate, documented
design, not oversight.**

- **Core:** `setup/scripts/settlement_ledger.py` models a cash-account settled-funds pool (T+1 options
  settlement) — each entry DEBITS its notional from a start-of-day settled-cash pool
  (`compute_settled_cash_remaining`, `settlement_ledger.py:75-85`); closing a position does NOT credit
  the pool back same-day (prevents Good-Faith-Violation-style same-day recycling,
  `settlement_ledger.py:27-51`). `heartbeat_core.py:2398-2401` reads this every tick and feeds
  `settled_cash_available`/`same_day_entries_used` into `risk_gate.check_order`
  (`heartbeat_core.py:2487-2493`), which is **fail-closed** in this mode — a missing value denies rather
  than silently passing (`risk_gate.py:428-439`). A ledger-file I/O error fails OPEN (defaults to "full
  SOD cash available," `settlement_ledger.py:58-66`) — deliberately the same direction as every other
  state-file failure in this codebase (an outage can only widen availability, never invent a new block),
  but worth naming: it means a corrupted ledger file silently drops the cash-tracking half of Rule 7 for
  that day rather than halting trading.
- **Fleet:** `fleet_executor.py:1212-1224` explicitly force-pins `pdt_gate_mode="margin_pdt"` for all
  three fleet arms, REGARDLESS of what the shared `params.json` says, specifically BECAUSE fleet never
  computes `settled_cash_available`/`same_day_entries_used` — wiring cash-settlement mode in blind would
  fail-closed on every fleet order (a real regression), so the comment documents this as an intentional,
  scoped tradeoff, not a hole nobody noticed. **The practical effect: no fleet order is ever checked
  against a settled-cash pool.** What DOES still bound a single fleet order is Rule 6 (notional ≤ 30-50%
  of that account's own CURRENT, live-fetched equity — `fleet_live.py:756` reads equity fresh each tick)
  — so a fleet arm cannot blindly place an order sized against stale or wrong equity, and cannot stack a
  second position while one is open (Rule 4/NOT_FLAT). What it CAN do that core cannot: round-trip the
  same real (if it were live) capital more times in a session than a cash-account discipline would
  allow, because nothing throttles same-day entry COUNT on the fleet path (next question).

### Does anything cap the number of entries per day, and is it per-arm or book-wide?

**Core: yes, per-account, 5/day (`params.json`'s `max_same_day_roundtrips`, both Safe and Bold, read at
`risk_gate.py:455-469`, denies with `CODE_SETTLEMENT` at the 5th). Fleet: no cap of any kind was found**
— exhaustively grepped `automation/state/fleet/` for `max_entries`/`daily_entry_cap`/`entries_per_day`/
`max_daily_trades`/`trade_count_cap` and found nothing. The only per-day counter on the fleet side is
`accounts.json:218-224`'s `probe_arm.daily_cap: 3`, which governs ONE cohort-bypass lane on ONE arm
(risky-3's `PROBE_ARM`-tagged entries only) — it is not a general entry-count throttle and does not apply
to the arm's normal trading. **Nothing is book-wide** — every cap found is scoped to a single account.

### Book-level exposure: could all 5 arms pile into the same direction with no aggregate cap?

**Yes, structurally — and no code anywhere sums or caps it. This is the highest-value finding in this
audit, exactly as flagged.**

Evidence chain:
1. **5 separate real broker accounts**, confirmed in `automation/state/fleet/accounts.json`: safe-3
   (`PA32T7Q1O20H`, lines 27-50), safe-2 (`PA3POKNV46VG`, lines 51-70), risky-1 (`PA3S9N1IV0A4`, lines
   91-116), bold-2 (`PA3WEBXJU67N`, lines 117-135), risky-3 (`PA3V7JT25H6Z`, lines 136-166). Isolation
   between accounts is real (a genuinely separate broker balance each), which is why Rule 5's kill
   switches work correctly per-account — that part of the system is NOT the gap.
2. **All 5 read ONE shared signal.** `automation/state/fleet/build_shared_signal.py` is, per MAP.md's own
   description, the single producer "all arms consume ... this is why arms correlate." Documented
   correlation: **r=0.846** (`analysis/deep-research/LIVE-READINESS-FIRST-READING-2026-08-18.md:50` —
   "the five arms trade one signal at r=0.846, so this is not five independent samples"). Same document,
   same file: on 2026-08-04 the book's single best day accounted for MORE than 100% of every individual
   arm's cumulative P&L — a correlated-tape effect, not five diversified bets.
3. **This already happens in practice.** MAP.md's own arms table (line 121): *"That is also why they
   lose together: on 08-07 all four bought the same contract within 15 seconds."*
4. **Nothing sums the simultaneous exposure.** Exhaustively grepped `automation/state/fleet/` and
   `backtest/lib/` for `book_level`/`aggregate_exposure`/`portfolio_risk`/`total_notional`/
   `cross_account`/`combined_notional`/`fleet_cap` (case-insensitive) — zero matches anywhere in the
   codebase. Each arm's `risk_gate.check_order` call evaluates ONLY that arm's own equity, own kill
   switch, own settled-cash pool (core) — no shared state, counter, or ceiling is read or written across
   arms.
5. **Illustrative same-tick worst case, computed from TODAY's real broker-reported equities**
   (`journal/2026-08-18.md:38-45`, the auto EOD table — safe-2 $5,266.38, bold-2 $5,048.40, safe-3
   $4,639.03, risky-1 $4,911.06, risky-3 $4,654.16, book total $24,518.03) **against each arm's own live
   per-trade cap** (30% safe-tier / 50% risky-tier, `risk_gate.py:530` × `params.json`/`aggressive/
   params.json`): safe-2 $1,580 + bold-2 $2,524 + safe-3 $1,392 + risky-1 $2,456 + risky-3 $2,327 =
   **≈$10,279, about 42% of the book, deployable into ONE correlated same-direction bet on a single
   tick, with zero circuit breaker above the individual-account level.** This is an illustration
   computed fresh for this report, not a stored/monitored metric — that absence is precisely the point.

### What happens if a fill would exceed available cash — hard reject, silent partial, or broker rejection after the fact?

- **Core (cash_settlement mode):** hard reject BEFORE the order is ever sent to the broker —
  `risk_gate.py:471-481`, `CODE_SETTLEMENT` — computed from the LOCAL settlement ledger, not a live
  broker balance call. This is the one path with a genuine pre-flight "do we actually have this cash"
  check.
- **Fleet (margin_pdt mode, no settlement ledger):** no local settled-cash pre-check exists. The only
  pre-flight capital check is Rule 6's notional-vs-current-equity cap, which is real and does prevent
  single-order overdraft against that account's own live equity — but it does not model settlement/GFV
  at all. If Alpaca's own margin/buying-power rules would independently reject an order for a reason
  Rule 6 didn't already catch, that rejection happens **after submission, at the broker** — this audit
  found no fleet-side code that pre-computes buying power the way `settlement_ledger.py` does for core.
  Practically bounded (equity is fetched live each tick, and NOT_FLAT prevents stacking), but it is a
  materially weaker guarantee than core's, and the gap is specifically the same-day-cash-recycling
  discipline, not a raw "can this account afford this trade" check.

---

## Undocumented constraints — real, live, code-enforced, and named nowhere in CLAUDE.md or risk-rules.md

J asked for these explicitly ("other things of this nature that I'm not mentioning"). These materially
affect whether a trade happens, but neither CLAUDE.md's 10 rules nor risk-rules.md name them:

1. **`min_entry_premium` floor ("ENTRY-1 PREMIUM FLOOR").** Refuses any entry priced below a threshold
   (currently $0.30 core / configurable per arm) — `heartbeat_core.py:2470-2480`,
   `fleet_executor.py:1189-1211`. Validated (STOP-B disposition, `entry-exit-matrix-2026-07-09.md`: sub-
   $0.20 fills cost ~$685 of one week's real losses) and fires constantly in production — TODAY's journal
   doesn't show it, but it is one of the most commonly-cited SKIP reasons across recent EOD digests. Not
   named in risk-rules.md's liquidity section (which covers spread/delta/OI/quote-validity, not a flat
   premium floor) or anywhere in CLAUDE.md.
2. **Bold's 15:00 ET entry cutoff.** `automation/state/aggressive/params.json:17`: *"entry cutoff 15:00
   ET (entries blocked after 15:00, open positions still held to 15:50)."* CLAUDE.md only states a
   generic "09:35 ET entry gate" and a 15:50 ET flatten — Bold's own, earlier, entry-side cutoff is
   real, active, and unmentioned.
3. **Fill-bar quality vetoes** (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`, `SKIP_DOJI_ENTRY_BAR` — both fired
   live today per `journal/2026-08-18.md:60-68`'s engine-action tally). Validated
   (`require_bearish_fill_bar`, OOS +$1,153/WF 18.5 per `accounts.json:155`) but applied
   **inconsistently by design**: bold-2 and risky-1 inherit the global hard-skip; risky-3 explicitly
   opts out (`accounts.json:154`, `"gate_params": {"hard_skip_verdicts": []}`). A real, deliberate,
   documented-in-a-comment-only per-arm threshold difference that doesn't appear in either rules
   document.
4. **`score_ladder_floor` rescue.** A per-arm score-based override (varies 7-9 across arms, bear-only
   today) that can promote what would otherwise be a HOLD into an ENTER when a raw level-tied trigger
   fired even though the primary gate refused it (`accounts.json:42,110,153`, `heartbeat_core.py`'s
   `_apply_score_ladder`). Two of three instances were DISARMED after a 390-day replay showed the armed
   rule losing (`-$10,903`/`-$16,642` vs baseline, per the same doc fields) — machinery stays wired but
   inert. Not named in either rules document; a meaningful mechanism for how an otherwise-refused signal
   can still become a real trade.
5. **Free-model veto is currently DISABLED**, the inverse problem — CLAUDE.md's own tech-stack table
   still lists "2 free-model veto" as part of the live decision chain, but
   `heartbeat_core.py:1055-1063` shows it's been off since 2026-08-12 (*"DISABLED by default since
   2026-08-12 (J: no free models on the money path)"*) — the row is still logged so the disabling is
   visible per-tick, but the doctrine table describing the engine's defenses is stale in the direction
   of overstating them.
6. **`day_throttle_shadow` (T-2/T-6 per-arm realized-loss circuit breaker) — the most relevant in-flight
   answer to J's own worry, not live yet.** `setup/scripts/day_throttle_shadow.py` is mid a 15-session
   forward pre-registration (window opened TODAY, 2026-08-18) measuring whether halting an arm once its
   own session-realized P&L hits −2% or −6% of start-of-day equity would have helped. Explicitly
   "SHADOW ONLY. Neither threshold refuses anything live" (`day_throttle_shadow.py:36-37`). This is
   per-arm, not book-wide — it doesn't touch the aggregate-exposure gap above — but it's a real,
   already-designed answer to "does the engine catch a bad session earlier than the −30%/−50% kill
   switch," worth knowing about before anyone proposes building a new one.

---

## Where two paths enforce the SAME rule at DIFFERENT thresholds

- **Rule 7 (PDT/settlement) — the significant one.** Core: real settled-cash gate, denies on genuine
  cash exhaustion. Fleet: `margin_pdt` mode fed a day-trade count that is hardcoded/inert
  (`fleet_live.py:787-790`: `day_trades_legacy` reads Alpaca's `daytrade_count`, which paper always
  returns null → 0; `day_trades_true` is computed correctly since 2026-08-06 but only BINDS when
  `fleet_pdt_enforce` — default False — AND `arm.get("live")` are both true). Broker-verified real
  counts on 2026-08-06 were 6/7/8 for safe-3/risky-1/risky-3 against a legal limit of 3 — i.e., all
  three fleet arms would fail this check today if enforcement were flipped on. This is not a hidden
  bug: `fleet_live.py:756-785`'s comment names the exact tradeoff and the exact one-line revert
  (`params.fleet_pdt_enforce`).
- **Entries-per-day** — core capped at 5, fleet uncapped (see above). Not framed as the "same rule" in
  the codebase (fleet is architecturally on a different gate mode), but it is the same underlying
  question — "how many times can this account re-trade today" — answered differently by construction.
- **Kill switch / risk cap percentages — checked for divergence, found NONE.** Both paths resolve 30%
  (safe-tier) / 50% (risky-tier) from the same base `params.json`/`aggressive/params.json` files
  (`fleet_executor.py:1290-1299` reads the identical files core does) and `fleet_live.py:106-108`'s
  `_limit_pct_for` matches. This is a genuine parity success worth stating plainly rather than only
  reporting gaps.
- **Bold's premium (catastrophe-cap) stop — a doctrine-internal inconsistency, not a code bug.**
  CLAUDE.md's "The strategy" section states premium stops are "now −50% catastrophe caps both sides."
  Bold's actual live `automation/state/aggressive/params.json:22-25` shows `premium_stop_pct: -0.07`,
  `premium_stop_pct_bear: -0.07`, `premium_stop_pct_bull: -0.05` — NOT −50%. This is not a code gap:
  `markdown/0dte/risk-rules.md`'s own, more detailed "Dual-Account Rules" table already correctly says
  "−7% bear / −5% bull" for Bold (this table was NOT edited by this audit — it was already right). The
  mismatch is CLAUDE.md's summary sentence being imprecise about which account "both sides" covers, not
  the code disagreeing with its rules doc. Flagged below as NEEDS-J since it's CLAUDE.md's own rule
  text, out of this audit's edit license.

---

## Prioritised gap list

**SAFE-NOW** (low blast radius, reversible, matches this codebase's own established "ship visibility
before enforcement" pattern — a future session could do these without controversy; NOT done in this
audit per its explicit scope):
- Book-level exposure **visibility** (not yet a cap): log the sum of same-tick, same-direction notional
  proposed across all 5 arms, the same way `FLEET-PDT-PARITY` added `day_trades_true` visibility before
  any enforcement decision. Zero behavior change, answers "how close did we get today" every session.
- Document `min_entry_premium` and Bold's 15:00 ET entry cutoff in `risk-rules.md` (pure doc addition,
  no code/threshold change).
- Add `playbook.md` ↔ code setup-name parity as a cheap automated check (a one-file grep-based guard,
  mirroring this audit's own method) so `VWAP_RECLAIM_FAILED_BREAK`-style drift is caught going forward
  instead of found by hand a month later.
- *(Done in this audit, already shipped:* the two proven-stale `risk-rules.md` passages — First-entry
  rule, bracket-order fallback framing — corrected in place.)

**NEEDS-J** (real judgment calls — thresholds, scope, or CLAUDE.md's own rule text):
- Whether to build an actual book-level exposure CEILING (not just visibility) across the 5 arms, and
  at what % of book equity — this changes live trading behavior and needs a threshold decision.
- Whether to flip `fleet_pdt_enforce=true` — would immediately start denying entries on all three fleet
  arms (real counts were already 6/7/8 vs. a limit of 3 as of 2026-08-06), which could silence most of
  the book's fill volume. High-impact, one-line revert, but not this audit's call.
- CLAUDE.md's imprecise "−50% catastrophe caps both sides" sentence — either fix the sentence (Bold is
  intentionally tighter, per risk-rules.md) or decide Bold should actually move to −50% too. Out of this
  audit's edit license (CLAUDE.md rule/strategy text).
- `GAP_AND_GO`: retire from `playbook.md` (dead doctrine, never wired) or build it. `VWAP_RECLAIM_FAILED_
  BREAK`: add to `playbook.md` (it's live-trading without its named pattern documented where Rule 1
  points).
- Whether the FINRA PDT repeal (confirmed, `markdown/trading-knowledge/PDT-CLAIM-VERIFICATION-2026-08-
  18.md`) changes anything about keeping `cash_settlement` mode on core — per that document's own
  finding, the answer today is "no, it's J's voluntary capital-discipline choice independent of the
  regulatory question," so no action is implied, just noted per this task's instruction to flag it.

**NEEDS-EVIDENCE** (already in motion; let the clock run before deciding):
- `day_throttle_shadow`'s T-2/T-6 pre-registration — 15-session forward window opened today
  (2026-08-18). Don't pre-empt it; it's the natural next instrument for "catch a bad day earlier,"
  per-arm.
- Any fleet PDT-enforcement decision should be read alongside `LIVE-READINESS-FIRST-READING-2026-08-18.
  md`'s finding that no arm (core or fleet) is yet distinguishable from breakeven — tightening a gate on
  arms that aren't earning their fill volume yet is a different conversation than tightening one on a
  proven arm.

---

## What this audit did NOT find

No evidence of a rule that is claimed enforced but silently no-ops on both paths (the specific "dead
knob" failure mode C14 warns about) among the 10 named rules — every enforced rule traced to a real
`Deny`/`HOLD` outcome on at least one path, and where a path doesn't enforce a rule (fleet/Rule 7), the
code says so in its own comments rather than pretending otherwise. The gaps here are real, but this is
not a codebase quietly lying to itself about the 10 rules — it is, however, missing a book-level
instrument it has never built, and its human-facing journal is honour-system for the automated path.

## Reproduce / verify

- Kill-switch, risk-cap, PDT/settlement gate: `backtest/lib/risk_gate.py` (read directly, pure function,
  no I/O — safe to open any time).
- Live per-arm equities used in the book-exposure illustration: `journal/{today}.md`'s auto EOD table
  (written by `obsidian_vault_sync.py`, 16:45 ET daily) or `automation/state/fleet/<arm>/circuit-
  breaker.json` for a specific arm.
- Fleet PDT visibility-vs-enforcement: `automation/state/fleet/<arm>/decisions.jsonl`'s
  `day_trades_true`/`day_trades_source`/`pdt_enforced` fields, written every tick since 2026-08-06.
