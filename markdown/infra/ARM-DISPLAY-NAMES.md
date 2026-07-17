# Fleet arm display names

> Added 2026-07-17. J: "i dont like how the arms are named currently" — the
> safe-1/safe-2/safe-3/risky-1/risky-3/bold-2 scheme is confusing on its own merits (numbers
> carry no meaning, "risky" vs "bold" is inconsistent) **and** unsafe — safe-1 (retired) and
> safe-2 point at the SAME broker account (`PA3DHPT7KIQE`, the 2026-07-11 repoint), which
> caused a real double-count in a report before this fix.

## What changed, what didn't

- **Arm ids are UNCHANGED.** `safe-1`, `safe-2`, `safe-3`, `risky-1`, `risky-3`, `bold-2`,
  `mes-linear-sim`, `mes-mnq-div-futures` remain exactly as they are. They are load-bearing
  keys across 80+ consumers (executor dispatch, decision-ledger directory names, secrets.json,
  guard tests, scheduled-task state) — a full blast-radius grep (2026-07-17, `automation/`,
  `setup/`, `backtest/`, `dashboard/`) confirmed renaming them was not a safe option.
- **Each arm in [`automation/state/fleet/accounts.json`](../../automation/state/fleet/accounts.json)
  gained a `display_name` field.** This is READ-SURFACE ONLY — no executor, ledger, or
  state-file keying logic reads it.
- **[`setup/scripts/arm_display.py`](../../setup/scripts/arm_display.py)** is the single
  resolver every read surface imports. It never raises (fail-open to the raw id/label on any
  lookup miss) and never mutates state.

## The mapping

| arm id | display_name | account (last-4) | note |
|---|---|---|---|
| `safe-2` | `CORE-SAFE (KIQE)` | `PA3DHPT7KIQE` | production core Safe, live heartbeat |
| `bold-2` | `CORE-BOLD (AT40)` | `PA33W2KUAT40` | production core Bold, live heartbeat |
| `safe-3` | `FLEET-TIGHT-S (OB0Q)` | `PA32RD49OB0Q` | safe sizing, tight gate (fleet_rest) |
| `risky-1` | `FLEET-TIGHT-R (8G19)` | `PA3W17FD8G19` | risky sizing, tight gate (fleet_rest) |
| `risky-3` | `FLEET-LOOSE-R (X15Q)` | `PA31WIU8X15Q` | risky sizing, loose gate (fleet_rest); also the probe arm |
| `safe-1` | `RETIRED (=CORE-SAFE acct KIQE)` | `PA3DHPT7KIQE` | **shares CORE-SAFE's account** — retired 2026-07-11, never places orders (status-gated), left in place as historical trading record |
| `mes-mnq-div-futures` | `FUTURES-DIV (dormant, 3759)` | `5WW73759` (TT sandbox) | edge3 MES/MNQ divergence, `enabled=false` |
| `mes-linear-sim` | `FUTURES-LINEAR (pending, 3759)` | `5WW73759` (TT sandbox) | `status=pending_build`, not yet wired |

Crypto Twin (a separate 24/7 mechanism-validation engine, not an `accounts.json` arm — see
`automation/state/crypto-twin/`) displays as **`CRYPTO-TWIN`** on any surface that resolves it
through `arm_display.display_name_for_label("crypto-twin"/"twin")`.

**Reading the account-collision at a glance:** `safe-1` and `safe-2` are the only two arms
that share a real account_number. Their display names both surface the SAME last-4 (`KIQE`),
so any status line showing both side by side makes the shared-account fact impossible to miss
— that visibility is the concrete fix for the double-count incident.

## Where display names show up

`arm_display.py` exposes two functions:

- `display_name_for_arm_id(arm_id)` — resolves a bare accounts.json id.
- `display_name_for_label(label)` — resolves any label shape a read surface already emits:
  `"safe"`/`"bold"` (heartbeat_core's short account labels), `"core:safe"`/`"fleet:safe-3"`
  (fill_funnel.py's funnel account keys), a bare arm id, or `"crypto-twin"`/`"twin"`.

Read surfaces updated 2026-07-17 to prefer the resolved display name (raw id kept alongside it
wherever something downstream — a human correlating against `decisions.jsonl` — still needs
it):

| Surface | What changed |
|---|---|
| `setup/scripts/trade_today_watcher.py` | Discord fill ping: `[safe-2]` → `[safe-2 CORE-SAFE (KIQE)]` |
| `setup/scripts/firm_brief.py` | PDT section: `- core Safe:` → `- core Safe [CORE-SAFE (KIQE)]:` |
| `setup/scripts/gamma_status.py` | ACCOUNTS section now lists every arm: `id` + `display_name` + `[status]` |
| `setup/scripts/participation_daily.py` | Markdown table: `safe (safe-2)` → `safe (safe-2 CORE-SAFE (KIQE))` |
| `setup/scripts/fill_funnel.py` | `render_text`/`render_markdown` account rows + the P&L by-arm bullet lines |

**Deliberately NOT touched:** `funnel["flags"]`/`funnel["accounts"]` dict keys, fill_funnel's
ENTER-events line, `_CORE_ACCOUNT_FOR_ARM`/`CORE_ARM_LABEL` mappings, any executor dispatch or
decision-ledger write path, and `firm_brief.py`'s exact-pinned `"- TWIN:"` line prefix (guarded
by an exact-string test) — all of those are either ledger-keyed or already covered by a pinned
test asserting the pre-existing exact text, and neither needed the change to satisfy this fix.

## Guards

- [`automation/state/fleet/test_arm_display_names.py`](../../automation/state/fleet/test_arm_display_names.py)
  — every arm has a display_name, names are unique, safe-1's flags the shared account, any two
  arms sharing a real account_number show the same last-4.
- [`backtest/tests/test_arm_display.py`](../../backtest/tests/test_arm_display.py) — the
  resolver functions against the real accounts.json, all label shapes, fail-open on a
  missing/corrupt accounts.json.
- Existing [`automation/state/fleet/test_duplicate_account_guard.py`](../../automation/state/fleet/test_duplicate_account_guard.py)
  (pre-dates this change) already guarded the underlying safety property (no two ACTIVE arms
  share an account) — this doc's guards are additive, not a replacement.

## Known separate bug this surfaced (not fixed here — flagged as its own task)

While verifying `trade_today_watcher.py`'s ping output for this change, live inspection of
today's `automation/state/trade-today.json` found 46 fill rows but only 31 unique order ids —
15 duplicated, every one tagged `['safe-1', 'safe-2']`. Because those two arms share Alpaca
credentials, `trade_today_watcher.py` polls the SAME account twice (once per credential label)
and double-counts every real fill in `spy_fills_today`/`placed_not_filled_today`. This is very
likely the exact "double-count in today's reporting" incident that prompted this whole task.
`accounts_status.py` already hit this and worked around it (its `ORDER` list deliberately
excludes `safe-1`); `trade_today_watcher.py` never got the equivalent fix. Root cause is
one sentence, fix is scoped and low-risk, but it's a distinct bug from arm *naming* — tracked
separately rather than folded into this change.
