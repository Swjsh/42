# EOD 2026-08-06 — LENS 3: The Two Silent Arms (4th session) + owed-debt clearance

> Clock verified `setup/scripts/et_clock.py` → **2026-08-06 16:13:50 Thursday EDT, market_hours=False** (session start),
> **16:34:19** (write). Nothing below is carried from the briefing without re-derivation.
> Machine-readable twin: [`EOD-2026-08-06-SILENT-ARMS.json`](EOD-2026-08-06-SILENT-ARMS.json)

## Verdict

**The silence cost $911.35 today — 38.4% of the achievable day.** Both root causes re-verified on Thursday's own
ledgers, and **one of them changed**: safe-3 was NOT signal-absent today, it was gate-blocked on the winning trade.
The account-type facts are resolved and **no key was touched** — J has a genuine fork. Both owed debts are cleared:
the PDT guard is RED-proofed, and the TV watchdog was verified by killing TV and watching it come back.

⚠️ **The briefing's "central question of the day" is void as posed** — the 14:21 long did not come from filter 5.

---

## 1. Root causes, re-verified on TODAY's ledgers

| Arm | Verdict | Evidence |
|---|---|---|
| **bold-2** (CORE-BOLD, `PA3WEBXJU67N`) | ✅ **CONFIRMED — PDT hard-block** | `RISK_DENY_PDT` ×3 at **10:32:48 / 10:34:01 / 10:34:56 ET**, each with `verdict=ENTER_BEAR`, reason *"passed scoring + all entry gates (tier TRENDLINE)"* |
| **safe-3** (FLEET-TIGHT-S, `PA32T7Q1O20H`) | ❌ **CORRECTED — not signal-absent** | 5 ticks **10:32–10:36 ET** reason `gate: 1 triggers < 2`, setup `BEARISH_REJECTION_RIDE_THE_RIBBON`, quality BASE |

### 🚨 Correction to a standing finding

The briefing carried *"safe-3 silence root cause = signal-absent (1 signal in 384 ticks on 08-05), not gates."*
**That held Wednesday. It is false for Thursday.** The signal fired; safe-3's own `gate_override.min_triggers = 2`
rejected it.

The discriminator is clean — same shared signal, same minute, three different gates:

| Arm | `gate_override` | Outcome |
|---|---|---|
| safe-3 | `min_triggers: 2` + `require_confluence_or_sequence` | **blocked** ("1 triggers < 2") |
| risky-3 | `min_triggers: 1` | fired → **+$827.80** |
| risky-1 | `full_send: true` | fired → **+$294.55** |

The gate is the entire difference. **Caveat:** `min_triggers=2` is safe-3's *designed* selectivity as the tight arm,
not a bug — n=1 cannot judge a selectivity knob.

**Nuance on bold-2:** PDT was not its only blocker. At **10:31:54** — the exact minute safe-2 filled — bold-2 was
blocked by `require_bearish_fill_bar`, not PDT. Lifting PDT alone would have entered at ~10:32:48, not 10:31.

---

## 2. What the silence cost — real OPRA

**Method.** Real Alpaca OPRA 1-min bars (`SPY260806P00770000`, 396 bars) replayed through the **live**
`exit_manager.plan_exit_actions` core. Quantities come from each arm's **own realized broker fills** since 08-03
(bold-2 filled qty 5 on all three 08-04 entries; safe-3 filled qty 3 on all six). Entry 1.28 = the real sibling
fill at the same minute.

### Parity check first (L251 — a counterfactual is worthless until the harness reproduces a known outcome)

| | Broker truth | Replay | Delta |
|---|---|---|---|
| safe-2 actual, 3 @ 1.28 | **+$338.45** | +$346.45 | **$8.00 (2.4%)** ✅ PASS |

### Result

| Arm | Qty | Forgone | Blocker |
|---|---|---|---|
| bold-2 | 5 | **+$564.90** | `RISK_DENY_PDT` |
| safe-3 | 3 | **+$346.45** | `min_triggers=2` |
| **Combined** | | **$911.35** | |

Day actual **+$1,460.80** → all-five day would have been **$2,372.15**. **Silence = 38.4% of the potential day.**
Unlike Wednesday, the silence unambiguously **cost** money.

> 🔧 **The first replay was wrong and the parity check caught it.** `replay_position` silently omits
> `structure_stop_enabled`/`trigger_level`, degrading structure mode to a −20% premium stop. It reported safe-2 as
> **−$76.80** against a truth of **+$338.45** — a $415 error with the sign flipped. Fixed locally; the shared helper
> is still broken (SWEEP-2).

---

## 3. The account-type question — FACTS FOR J. No key changed.

**Live, this session, raw REST + MCP on all six arms:**

| Field | safe-2 | bold-2 |
|---|---|---|
| account | `PA3POKNV46VG` | `PA3WEBXJU67N` |
| **multiplier** | **4** | **4** |
| max_margin_multiplier | 4 | 4 |
| shorting_enabled | true | true |
| equity / cash | $5,727.91 | $5,477.71 |
| regt_buying_power | $11,455.82 | $10,955.42 |
| created_at | 2026-08-03 | 2026-08-03 |
| `pattern_day_trader` | **ABSENT** | **ABSENT** |
| `daytrade_count` | **ABSENT** | **ABSENT** |

**Sharper than the standing note:** those two fields are not `null`, they are **absent from the payload entirely** on
all six arms — so `.get()` can only ever return its default.

**Live day-trade counts** (`pdt_tracker` over broker FILL activities, rolling 5bd, 16:20 ET):
safe-2 **8** · bold-2 **3** · safe-3 6 · risky-1 8 · risky-3 9. *(Briefing said safe-2 was 7; live truth is 8.)*

### The paragraph J can act on

> On today's live broker data **safe-2's `cash_settlement` exemption is the defect and bold-2's `margin_pdt` is
> correct.** Both core accounts report multiplier=4, max_margin_multiplier=4, shorting_enabled=true and
> regt_buying_power at 2× equity — those are **RegT margin accounts, not cash accounts** — so the legacy FINRA PDT
> rule that safe-2's mode switches off entirely *does* apply, and both sit far under the $25,000 threshold at
> ~$5.5–5.7K. The 2026-07-14 provenance behind the exemption ("multiplier 1 … CASH account") is not merely stale:
> **the accounts it was measured on were deleted**, and every one of the six replacements built on 2026-08-03 reports
> margin. Consequence: safe-2 has taken **8 day-trades in 5 business days** on a sub-$25K margin account and its gate
> cannot see them, while bold-2 correctly stopped itself at 3 and has sat out four sessions — costing a verified
> **$564.90 today alone**. This is harmless *today* because it is PAPER and Alpaca's paper API returns no PDT fields
> at all, so no broker-side enforcement exists either way; it becomes a real compliance exposure the moment
> `GAMMA_CORE_ARMED=1` touches live money, where a real broker would flag safe-2 as a pattern day trader and freeze
> it. **The genuine fork — and why this is yours — is that the two defensible fixes point opposite ways:** tighten
> safe-2 to `margin_pdt` for correctness and accept that *both* core arms then jail themselves for days at a time on
> paper (bold-2's four silent sessions become the norm), **or** leave both loose on paper deliberately to keep
> collecting evidence and gate the correctness fix to live-arming instead. FINRA has in fact approved **eliminating
> the trade-count rule** in favour of intraday-margin monitoring, with a 12-month interim in which firms may apply
> either regime — so the constraint bold-2 is obeying may not exist by the time you arm live. I changed nothing and
> lean to the second path with an explicit live-arming checklist item, but the call is yours.

**Docs consulted** (`search_alpaca_docs` → `fetch_alpaca_doc`, page
`us/understanding-finras-new-intraday-margin-rule-and-the-end-of-pdt`): FINRA approved replacing legacy PDT with an
intraday-margin system — the $25K threshold and the four-in-five count are both eliminated, 0DTE long-option
expiration is explicitly an IML-reducing transaction, and there is a 12-month interim in which firms may apply either
regime by account or firm-wide. **Limitation:** the docs describe the forward regime; no page explains Alpaca paper's
cash-vs-margin reporting or the absent PDT fields. That absence is an empirical finding, not documented behaviour.

---

## 4. Owed debt #1 — RED-proof of `test_fleet_pdt_parity.py` ✅

Source: `automation/state/fleet/fleet_live.py` · baseline `sha256 061764f1…8737b46` · **11 passed in 0.19s**

| Mutation | Edit | Result |
|---|---|---|
| **M1** revert to null broker field (the original defect) | `n = int(_pdt.fetch_day_trades_used_5d(creds))` → `n = int((acct or {}).get("daytrade_count") or 0)` | **4 failed, 7 passed** |
| **M2** enforcement unconditional (C14 dead-knob) | `enforce_true = bool(params.get(...)) and bool(arm.get("live"))` → `enforce_true = True` | **1 failed, 10 passed** |
| **M3** fail-CLOSED instead of fail-open | `return int(...), "broker_field_fallback"` → `return 99, "broker_field_fallback"` | **1 failed, 10 passed** |

**Restored `sha256 061764f1…8737b46` — byte-identical: True → 11 passed in 0.19s.**

**Honest weakness:** M2 is caught only by `test_run_expression_matches_this_mirror`, a **source-text** assertion. It
pins a literal string, reds on any benign refactor, and does **not** prove the default-inert *behaviour*. That
property deserves a real behavioural test.

---

## 5. Owed debt #2 — TV watchdog heal, verified live ✅

| | State |
|---|---|
| Before | TV procs **0**, CDP 9222 **DEAD** (killed ~16:26 ET, market closed) |
| Ran | `setup/scripts/run-tv-watchdog.ps1` (the real scheduled entry point) |
| After | TV procs **9**, new PID **1728** started **16:27:44 ET**, CDP 9222 **HTTP 200** |
| Recheck 16:34 | TV procs 9, CDP 200 |

**Why this is discriminating:** pre-fix the child `powershell.exe` never executed a single line, so a dead TV could
not be revived. TV returning from a hard zero-process state is only possible if the argv fix genuinely runs
`launch_tv_debug.ps1`. Historical bug evidence still in `tv-watchdog.jsonl`: `relaunch_kill_FAILED` on 07-31 15:55,
07-31 16:00, and 08-05 08:50.

---

## 6. Sweep — other "reports success while doing nothing"

| ID | Sev | Where | Shape |
|---|---|---|---|
| **SWEEP-1** | 🔴 HIGH | `backtest/tools/stop_width_population_grid.py#get_bars` | **Poisoned empty cache.** On any fetch exception it sets `bars=[]` then writes the cache CSV **unconditionally**. Every later call sees `p.exists()` and returns 0 bars forever, silently. |
| **SWEEP-2** | 🔴 HIGH | `backtest/tools/exit_shape_parity_study.py#replay_position` | **Confidently wrong number.** Omits `structure_stop_enabled`/`trigger_level`; structure mode degrades to −20% premium. Measured error **$415.25, sign flipped**. |
| **SWEEP-3** | 🟡 LOW-MED | `connectivity-gate.ps1:199`, `preflight-gate.ps1:96` | Both emit `healed = [bool]$Heal` — a verbatim echo of the **request switch**, not the outcome. |

**SWEEP-1 proof** — same symbol, same key, only the end bound changed:

```
end=2026-08-06T20:15:00Z  ->  HTTP 403 {"message":"OPRA agreement is not signed"}
end=2026-08-06T19:00:00Z  ->  200 OK, 331 bars
end=2026-08-06T20:05:00Z  ->  200 OK, 396 bars
```

The hardcoded `end={date}T20:15:00Z` (16:15 ET) always falls inside Alpaca's last-15-minutes real-time embargo on a
same-day fetch. **I hit this live this session** — it wrote two 1-line CSVs. I deleted them and refetched; **the code
is unfixed.** Same family as L241, but worse: L241's fetcher returned nothing, this one *persists* the nothing.

**SWEEP-3 is disclosed as mild:** neither is a gate-logic defect. Both scripts compute their primary `verdict` from
real node checks, and connectivity-gate also emits `tv_heal_action` carrying the true outcome. Only the `healed`
field misleads. Swept clean elsewhere: `_shared.ps1:881` computes `healed` from a real post-action probe (correct);
`heal-engine.ps1:116` is an accumulator, not a claim.

---

## 7. 🚨 Briefing correction — the 14:21 long did NOT come from filter 5

**Claim:** *"The 14:21 safe-2 LONG is the first fire after filter 5 finally cleared … blockers shedding
[5,7,10,11] → [5,11] → [5] → fired."*

**Ledger truth** (`core-decisions.jsonl`) — `bull_blockers` **never empties**:

| Window ET | bull_blockers | bull_score | ribbon | action |
|---|---|---|---|---|
| 14:11–14:15 | `[5,7,10,11]` | 7 | BEAR | HOLD |
| 14:16–14:18 | `[5]` | 10 | MIXED | HOLD |
| 14:19–14:25 | `[5,11]` | 9 | MIXED | HOLD |
| 14:26–14:29 | `[5]` | 10 | MIXED | HOLD |

Every tick is `action=HOLD, verdict=HOLD, reason="no setup passed scoring"`. **Filter 5 never cleared and the core
path never emitted ENTER_BULL today.** `core-decisions` logs exactly **one** `PLACED` for `account='safe'` — the
10:31 put.

**What actually fired:** `safe-2/extra-setup-cooldown.json` → `{"bollinger_squeeze": "2026-08-06T14:15:00-04:00"}`
and `entry-claim.json` → `{"symbol": "SPY260806C00769000", "claimed_at_et": "2026-08-06T14:21:54"}`. Broker fill
confirms buy 3 @ 1.08 at 14:21:55 ET. **An extra-setup fire, not the ribbon bull path.**

**Consequence:** the "was the filter-5 bull entry late?" question is void — filter 5 did not fire it. The real
question is whether `bollinger_squeeze` should take counter-trend longs into a BEAR/MIXED ribbon while the core bull
path is still blocked. It lost −$36 in 5 minutes. Different investigation, still n=1. **The dormant
`structure_shift_confirmation` capability is neither supported nor refuted by today's tape — no prereg filed.**

---

## Open items (NOT done)

- **SWEEP-1** — skip the cache write on failed fetch + clamp `end` to now−15min.
- **SWEEP-2** — pass structure-stop params in `replay_position`; needs its own prereg + guard (it changes every historical study built on it).
- **SWEEP-3** — make `healed` reflect the outcome in both gate scripts.
- Replace the M2 source-text mirror with a behavioural default-inert assertion.
- `CLAUDE.md` account table still lists `PA3DHPT7KIQE` / `PA33W2KUAT40`; live truth is `PA3POKNV46VG` / `PA3WEBXJU67N`.

## Caveats

- **n=1 on everything P&L.** One trade, one day, one direction. PREREG-only; nothing here is a ship.
- `min_triggers=2` is safe-3's designed selectivity, not a defect. Today's cost is real but not a verdict on the knob.
- The bold-2 counterfactual assumes lifting PDT alone; its `require_bearish_fill_bar` block at 10:31:54 is separate and unaddressed.
- Counterfactual fills assume no market impact — defensible for 5 and 3 contracts of ATM SPY 0DTE.
- **No params key was changed. No trade was placed. TV was killed and restored as the assigned verification.**
