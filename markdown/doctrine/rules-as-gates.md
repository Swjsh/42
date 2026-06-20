# Rules as Gates — Doctrine v1

> **Multi-Agent Gamma 2.0 — Big Win #3.** Source pattern: Jesse Vincent (obra/superpowers),
> "Rules and Gates" (blog.fsck.com, 2026-04-07).
>
> A **rule** has an opt-out path — it can be rationalized away ("just this once"). A **gate**
> doesn't — the next observable action is BLOCKED until a specific check executes and returns a
> known answer.
>
> Every one of Gamma's 10 trading rules has been converted to gate form below. The gate is the
> read-and-check action, not the prohibition.
>
> **The gate test:** *when I'm about to skip it, does the gate formulation give me a concrete
> question I can't answer?* "Do I have order_id with status=filled?" is gate-shaped.
> "Did I confirm the fill?" is rule-shaped.

---

## Authority hierarchy

If a gate fires (returns BLOCK), the action does not proceed. PERIOD. No mid-session
rationalization. The only escape valve is operating principle 8 (no deferral, no fallback to
manual) — which means the engine fixes the failed gate, not bypasses it.

A rule violation = log a NOTE. A gate failure = HARD STOP, journal entry, kill-switch consideration.

---

## The 10 Gates

### Gate 1 — "No setup, no trade" → Playbook membership check

**Action being gated:** `mcp__alpaca__place_option_order`

**Gate logic (executed BEFORE order):**
```
setup_name = developing_setup.name from loop-state.json
playbook_setups = parse markdown/0dte/playbook.md → extract "## Setup: NAME" headings
IF setup_name NOT IN playbook_setups: BLOCK with reason "setup_name_not_in_playbook:{name}"
```

**Question that can't be answered if you skip it:** "Which heading in playbook.md contains this exact setup_name?"

---

### Gate 2 — "Wait for the trigger" → Closed-bar trigger fire check

**Action being gated:** `mcp__alpaca__place_option_order`

**Gate logic:**
```
last_closed_bar_time = SPY 5m bar where time_close < now_et
trigger_fired_on_closed_bar = developing_setup.triggers_fired evaluated against ONLY bars where time_close < now_et
score_at_closed_bar = filter score computed using closed-bar values

IF developing_setup.score < score_max OR trigger_fired_on_closed_bar IS EMPTY: BLOCK
  reason = "score_or_trigger_not_yet_confirmed_on_closed_bar"
```

**Question that can't be answered:** "What's the timestamp of the bar where the trigger fired? Is it strictly less than now_et?"

---

### Gate 3 — "Defined stop on entry" → Stop-fields-non-null check

**Action being gated:** writing `automation/state/current-position.json` after a fill

**Gate logic:**
```
new_position_record = {entry_premium, qty, side, ...}
IF new_position_record.premium_stop IS NULL AND new_position_record.chart_stop IS NULL: BLOCK
  reason = "no_stop_defined_at_entry"
```

**Question that can't be answered:** "What dollar value is in the premium_stop field? What price is in chart_stop?"

---

### Gate 4 — "No adding without a NEW confirmed trigger" → Add-on trigger-fire check

**Action being gated:** add-on `mcp__alpaca__place_option_order` when current-position.qty > 0

**Gate logic:**
```
last_add_at = current-position.add_history[-1].timestamp_et (or entry_time if no adds)
fresh_triggers = developing_setup.triggers_fired filtered to bars where time_close > last_add_at

IF fresh_triggers IS EMPTY: BLOCK
  reason = "no_fresh_trigger_since_last_entry_at_{last_add_at}"
```

**Question that can't be answered:** "Which trigger event fired on a bar that closed AFTER the last fill?"

---

### Gate 5 — "Daily kill-switch" → Realized-P&L check

**Action being gated:** ANY `mcp__alpaca__place_option_order` (entry OR add-on)

**Gate logic:**
```
today_realized_pnl = sum(decisions.jsonl rows today where action LIKE 'EXIT_%' AND filled=true).pnl_dollars
start_equity = circuit-breaker.start_equity_today
threshold = start_equity * params.json.daily_loss_kill_switch_pct  # 0.50

IF today_realized_pnl <= -threshold:
  REPLACE order placement with journal NOTE "kill_switch_blocked"
  SET circuit-breaker.tripped = true
  BLOCK
```

**Question that can't be answered:** "What's the sum of pnl_dollars across all today's filled exits in decisions.jsonl?"

---

### Gate 6 — "Per-trade risk cap (50%)" → Pre-fill sizing check

**Action being gated:** `mcp__alpaca__place_option_order`

**Gate logic:**
```
proposed_premium_dollars = limit_price * 100 * qty
account_equity = circuit-breaker.current_equity (refreshed from get_account_info if older than 5 min)
risk_pct = proposed_premium_dollars / account_equity

IF risk_pct > params.json.per_trade_risk_cap_pct:  # 0.50
  REJECT (or REDUCE qty until risk_pct <= cap, with floor=3)
  IF reduced_qty < 3: BLOCK with reason "cant_size_within_cap_minimum_3"
```

**Question that can't be answered:** "What is `(limit_price * 100 * qty) / current_equity`?"

---

### Gate 7 — "PDT awareness" → Day-trade-budget check

**Action being gated:** `mcp__alpaca__place_option_order` (entry only — exits don't count toward PDT)

**Gate logic:**
```
day_trades_used_5d = sum(circuit-breaker.day_trades_history[-5:].count_for_day)
account_equity = circuit-breaker.current_equity
account_type = circuit-breaker.account_type  # 'margin' or 'cash'

IF account_type == 'margin' AND account_equity < 25000 AND day_trades_used_5d >= 3: BLOCK
  reason = "pdt_limit_3_in_5d_under_25k"

IF account_type == 'cash':
  unsettled_funds = get_account_info().non_marginable_buying_power_held
  IF proposed_premium_dollars > settled_buying_power: BLOCK
    reason = "cash_settlement_insufficient"
```

**Question that can't be answered:** "How many day-trades have been counted across the last 5 business days?"

---

### Gate 8 — "Journal real-time" → Pre-trade-thesis check

**Action being gated:** `mcp__alpaca__place_option_order`

**Gate logic:**
```
journal_today = read journal/{today}.md
proposed_trade_id = generated UUID for this entry attempt
required_section = "## Trade {N} — {setup_name} ({side})" with subsections "Thesis:", "Entry:", "Stop:", "Target:"

IF journal_today does not contain a Thesis section for this entry attempt: BLOCK
  reason = "pre_trade_thesis_missing_from_journal"
```

The thesis goes in BEFORE the order. This gate forces the write order: thesis → order → fill confirm → exit logic → exit log → lesson.

**Question that can't be answered:** "What is the exact thesis text for this trade in journal/{today}.md?"

---

### Gate 9 — "No mid-session rule changes" → File-mtime check

**Action being gated:** modifying `automation/state/params.json`, `automation/prompts/heartbeat.md`,
or `automation/prompts/premarket.md`

**Gate logic:**
```
now_et = current ET time
in_market_hours = (now_et.weekday < 5) AND (09:30 <= now_et.time <= 16:00)

IF in_market_hours: BLOCK
  reason = "no_doctrine_changes_during_market_hours_rule_9"
```

This gate is enforced at the SAVE step of any doctrine-altering edit. Save attempts inside
market hours are rejected; the user must wait until 16:01 ET (operating principle 1's
post-market window).

**Question that can't be answered:** "Is now_et inside [09:30, 16:00] on a weekday?"

---

### Gate 10 — "Heed Gamma's flags" → Block-list check

**Action being gated:** `mcp__alpaca__place_option_order`

**Gate logic:**
```
recent_blocks = parse heartbeat-{today}.log lines containing "BLOCK"
last_block_for_this_setup = filter(recent_blocks, setup == developing_setup.name) last record

IF last_block_for_this_setup AND now - last_block_for_this_setup.time < 15_minutes:
  BLOCK with reason "still_within_15min_of_gamma_block_for_this_setup"
```

A 15-minute cooldown after any BLOCK ensures J doesn't override a gate by waiting 30 seconds and
re-firing the same setup.

**Question that can't be answered:** "When was the most recent BLOCK log line for this setup, and how many minutes ago was that?"

---

## Cross-cutting gate: First-entry-after-stop (already in v14 production)

**Action being gated:** `mcp__alpaca__place_option_order` (entry only)

**Gate logic:**
```
loop_state.first_entry_lock = list of {setup_name, exit_reason, ...}
IF developing_setup.name in [s.setup_name FOR s IN first_entry_lock WHERE s.exit_reason in {"premium_stop", "chart_stop", "ribbon_flip_back"}]:
  BLOCK with reason "first_entry_after_stop_blocked_for_{setup_name}"
```

This is already in heartbeat.md production. Listed here for completeness.

---

## How gates appear in heartbeat.md

The Entry Branch section of heartbeat.md should sequence gates in this order:
1. Gate 5 (kill-switch — fastest, cheapest, shortcut everything)
2. Gate 7 (PDT — also cheap)
3. Gate 1 (playbook membership)
4. Gate 2 (closed-bar trigger)
5. Gate 10 (recent block cooldown)
6. Cross-cutting: first-entry-after-stop
7. Gate 8 (pre-trade thesis written)
8. Gate 6 (per-trade sizing)
9. Gate 4 (add-on trigger — only if qty > 0)
10. Place order via Alpaca MCP
11. On fill: Gate 3 (stops written before position record persisted)

Gate 9 is enforced at file-write time (post-tool hook in settings.json — see Big Win #6's hook
infrastructure for plumbing).

---

## Doctrine note

This is doctrine, not code. The actual gate enforcement lives in `automation/prompts/heartbeat.md`
(entry branch) and (for Gate 9) in a future PreToolUse hook. Cross-references:
- CLAUDE.md operating principle 11 (Karpathy method) for ratification path
- `docs/plans/multi-agent-gamma.md` Big Win #5 (Iron Law verification gate) for the post-fill writes
- `automation/state/params.json` for thresholds (`daily_loss_kill_switch_pct`, `per_trade_risk_cap_pct`)
