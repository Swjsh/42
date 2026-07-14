# Runbook: repointing a core account (safe-2 / bold-2) at a different broker account

> Triggered whenever a core-engine account (`safe-2` = core Safe, `bold-2` = core Bold) needs
> to move to a DIFFERENT Alpaca paper account — e.g. the current account was deleted (2026-07-10
> Safe-2 incident), needs replacing, or is being merged with a fleet arm's account (2026-07-11
> repoint). This is the checklist a future repoint MUST run, mined from the 2026-07-11
> `SAFE-2-ACCOUNT-REPLACEMENT` repoint (`STATUS.md`, commit `61cfca0`) and the 2026-07-13
> PDT-inheritance scar it caused (`analysis/daily-brief/2026-07-13-FULL-AUDIT.md` §2). Follow it
> in order — step 1 is the step the 07-11 repoint SKIPPED, and it cost core Safe its entire
> first live trading day back.

## Why this exists (the scar)

The 2026-07-11 repoint moved core Safe onto account `PA3DHPT7KIQE` — a REAL, already-active
account that had been trading for weeks as fleet arm `safe-1` (57 lifetime round trips). The
repoint correctly updated credentials, retired the donor fleet arm, reset the equity baseline,
and swept every fills-attribution consumer it could find (broker_fills.py, mcp_audit.py,
accounts_status.py, docs — see the consumer table in `STATUS.md`'s 2026-07-11
`SAFE-2-ACCOUNT-REPLACEMENT` entry). **It did NOT reset or even inspect the account's inherited
`day_trades_used_5d` PDT counter** — the account had 9 day-trades already logged against it from
its life as safe-1. Two days later (2026-07-13, core Safe's first REAL trading day on the new
account), that inherited count silently denied a valid, gate-passing `ENTER_BEAR` signal at
`risk_gate.check_order`'s PDT check. Nobody knew until a manual full-day audit found it — not an
instrument. Rule 7 (PDT awareness) fired exactly as designed; the bug was that the account-swap
never treated the PDT budget as a thing to decide about.

**The fix that closes this permanently:** `self_check.py`'s `check_pdt_status()` +
`firm_brief.py`'s `## PDT status (Rule 7)` section (shipped 2026-07-14) now show
day-trades-used/remaining/rolloff-date for both core accounts EVERY ~30 min, and a blocked
account renders LOUD (`BLOCKED`, DEGRADED/YELLOW), never silently green. **Step 1 below is now
verifiable in one glance instead of requiring a broker API call by hand** — check the brief
before you decide.

## The checklist (run every item, in order)

### 1. Inherited PDT day-trade budget — check FIRST, before touching anything else

The target account may already carry a `day_trades_used_5d` history from ITS prior life (a
retired fleet arm, a different execution path, or manual trading). This is a DELIBERATE decision
now, never an accidental inheritance:

- Run `backtest/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'setup/scripts'); import pdt_tracker as p; from datetime import datetime, timezone; print(p.fetch_day_trades_detail({'key':'<key>','secret':'<secret>','base_url':'https://paper-api.alpaca.markets'}))"`
  against the TARGET account's credentials — or, once the repoint is live, read
  `automation/state/firm-brief.md`'s `## PDT status (Rule 7)` section / `self-check-last.json`'s
  `"pdt"` key.
- **Decide explicitly**: does the new occupant INHERIT the count (conservative — respects real
  same-security day trades against the SAME broker account regardless of who initiated them,
  since FINRA's PDT rule is account-level, not strategy-level) or does it get a clean slate
  (only correct if you are CERTAIN the account's trading history genuinely doesn't apply to
  the new occupant — rare, and arguably never technically correct since PDT is about the
  ACCOUNT, not the strategy)?
- **Whichever you decide, write it down** in the repoint's `accounts.json` doc field AND the
  `STATUS.md` REVOKE-report entry — the 07-11 repoint's failure mode was not deciding, not
  deciding wrong.
- If the inherited count is already at or near `PDT_DAY_TRADE_LIMIT` (3, see
  `backtest/lib/risk_gate.py`), the account will be effectively DEAD for new entries until it
  rolls off (5 business days from the oldest inherited day-trade) — decide whether that's
  acceptable for the repoint's timeline, or whether it changes which donor account to pick.

### 2. Circuit-breaker reset (equity baseline)

- Re-query the target account's LIVE equity (`/v2/account`, direct REST — never trust a cached
  number) and write it into `automation/state/circuit-breaker.json` (safe) or
  `automation/state/aggressive/circuit-breaker.json` (bold): `starting_equity_today` /
  `current_equity` (safe) or `equity_start_of_day` / `equity_current` (bold — field names
  diverge, see the `_schema_note` in each file).
- Recompute `daily_loss_limit_dollars` (safe: 30% of equity) or `loss_pct` baseline (bold: 50%)
  off the FRESH equity, not the donor account's stale number.
- Decide `day_trades_used_5d` per step 1 above and set it explicitly (don't leave the field
  untouched hoping it's fine — that silence is exactly what caused the 07-13 scar).

### 3. Credential repoint + MCP reload

- Update the canonical secret locations (gitignored — never a tracked file): `.mcp.json`'s
  `alpaca` (safe) or `alpaca_aggressive` (bold) server env, AND
  `automation/state/fleet/secrets.json`'s matching `safe-2`/`bold-2` entry (mirrors `.mcp.json`
  per house convention).
- **`heartbeat_core.py` resolves credentials fresh every scheduled-task fire** (each is a new
  process reading `.mcp.json` directly via `alpaca_keys.py`) — production trading picks up the
  new key IMMEDIATELY, no reload needed for the live engine.
- **Any INTERACTIVE session's own `mcp__alpaca__*` / `mcp__alpaca_aggressive__*` tool calls WILL
  401** until that session's MCP server process is restarted (it holds the old key in memory) —
  per `MCP-401-RESTART-RUNBOOK.md`, this needs a session/task restart, not a live fix. This does
  NOT block production trading, only interactive tool calls in sessions started before the swap.

### 4. Fills-attribution consumers — sweep for hardcoded account numbers / arm lists

Grep the repo for the OLD account number and the OLD/retiring arm id before considering this
done. Known consumers from the 07-11 repoint (re-check this list is still current — new
consumers get added over time):

| Consumer | Risk if skipped |
|---|---|
| `setup/scripts/broker_fills.py` `FLEET_REST_ARMS` | Fills misattributed engine/manual if a retiring donor arm still shares the credential |
| `setup/scripts/mcp_audit.py` + `mcp_audit_direct.py` | False-FAIL the instant the fix lands (compares against the now-wrong expected account) |
| `setup/scripts/context_audit.py` | Same false-fail mode against CLAUDE.md's account-number integrity check |
| `setup/scripts/accounts_status.py` `ORDER`/`ENGINE_WIRING` | Duplicate-account row + double-counted TOTAL if the donor arm isn't dropped |
| `setup/scripts/fleet_journal_bridge.py` `FLEET_REST_ARMS` | Stale/inconsistent (low risk, local decisions.jsonl only) |
| `fleet_live.py#_arm_is_processable`, `fleet_executor.py#run_dry`, `fleet_eod.py` | Usually self-corrects from `accounts.json`'s `status` field — verify, don't assume |
| `automation/state/today-bias.json` | Stale equity fields (cosmetic, next premarket fire overwrites) |
| Tests reading real `accounts.json` (`test_six_account_routing.py`, `test_six_account_exit_shapes.py`, `test_broker_fills.py` fixtures) | Assert against a stale arm-count/fixture id world — update AND run, don't just inspect |

### 5. Donor arm retirement (if repointing onto a retiring fleet arm's account)

- Flip `status: "active"` → `"retired"` in `accounts.json` (NOT delete) — its `decisions.jsonl`
  and `circuit-breaker.json` are real trading history, leave them untouched.
- Flip `live: true` → `false` as a belt-and-suspenders signal (code gates on `status`, this
  documents intent).
- Add a dated `_retired_doc` field with the full mechanism + revert path, inline in
  `accounts.json` (so a future reader doesn't need to dig through `STATUS.md` history).
- Confirm the donor arm ID is REMOVED from every active-roster assumption
  (`fleet_live._arm_is_processable`, `fleet_executor.run_dry`, any hardcoded arm tuples) —
  write a guard test pinning "this arm is retired, not dispatched" (see
  `test_safe1_is_retired_not_dispatched` for the pattern).

### 6. Docs sweep

Update every doc that names the OLD account number or arm role: `CLAUDE.md` (account table +
tech-stack table), `dual-account-design.md`, `ARCHITECTURE.md`, `mcp-install.md`,
`mcp-weekly-audit.md`, any `SKILL.md` files, `cockpit/server.js` if it hardcodes account labels.
Grep is cheap; a stale account number in CLAUDE.md is a `context_audit.py` false-fail waiting to
happen (see step 4).

### 7. Verify — don't claim (OP-33)

- `accounts_status.py` — expect the new account `ACTIVE`, no 401, no duplicate rows, correct
  TOTAL.
- `self_check.py` — expect no NEW `BROKER KEY STALE/REVOKED` problem, and check the `## PDT
  status (Rule 7)` line for the repointed account: does it read `BLOCKED`, `OK`, or
  `NOT_APPLICABLE`? **This is the single check that would have caught the 07-13 scar BEFORE
  the market opened, not after a full-day audit found it.**
- `automation/state/firm-brief.md` — read the PDT section top-to-bottom before calling the
  repoint done; if it says `BLOCKED`, that is expected ONLY if step 1's decision was "inherit
  the count" — if it says `BLOCKED` and you intended a clean slate, step 1 was skipped or done
  wrong.
- Run the fleet test suite (`automation/state/fleet/` + `test_fleet_arm_parity.py` +
  `test_broker_fills.py` + `test_six_account_routing.py` at minimum) and quote the pass count —
  a repoint is not done until the suite is green (pre-existing unrelated failures must be
  PROVEN pre-existing via `git stash`-isolation, not assumed).

### 8. Revert plan — write it down before you need it

Every repoint is two things, not one: the credential move AND (if applicable) the donor arm
retirement. Document both halves' revert steps inline in `accounts.json`'s doc fields AND in the
`STATUS.md` REVOKE-report entry, so a future revert doesn't have to reverse-engineer the
mechanism from git history. Never revert only one half — running two execution paths off the
SAME broker account simultaneously reintroduces the double-fill/misattribution risk the repoint
exists to avoid in the first place.

## Related

- The 2026-07-11 repoint (full mechanism + consumer table): `STATUS.md` →
  `[2026-07-11] SAFE-2-ACCOUNT-REPLACEMENT resolved`.
- The scar this runbook exists to prevent: `analysis/daily-brief/2026-07-13-FULL-AUDIT.md` §2.
- PDT visibility instrument: `setup/scripts/pdt_tracker.py` (`fetch_day_trades_detail`),
  `setup/scripts/self_check.py` (`check_pdt_status`), `setup/scripts/firm_brief.py`
  (`render_pdt_lines`).
- 401 / stale-key recovery (a DIFFERENT scenario — same account, rotated key, not a repoint):
  `MCP-401-RESTART-RUNBOOK.md`.
- Rule 7 definition: CLAUDE.md's "The 10 rules" §7; `backtest/lib/risk_gate.py`
  (`PDT_DAY_TRADE_LIMIT`, `PDT_EQUITY_THRESHOLD`).
