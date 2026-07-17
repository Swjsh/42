# Fleet attribution audit — risky-3 "+$248 / zero ENTER" mystery — 2026-07-17

**Verdict: NOT a logging gap. The decision ledger is 100% complete. The bug is in the
VISIBILITY layer (`trade_today_watcher.py`'s `_is_engine_attributed()`), which was blind
to the fleet-arm decisions.jsonl schema and mislabeled every fleet fill "UNATTRIBUTED FILL"
regardless of a real, matching decision row existing. Fixed + guarded this session.**

## The mystery as stated

risky-3 (account `PA31WIU8X15Q`) shows +$248 realized across 5 broker fills on 2026-07-17
per `automation/state/trade-today.json`, but `automation/state/fleet/risky-3/decisions.jsonl`
was reported to show ZERO ENTER verdicts today — money moved with no decision-ledger trail.

## Differential — hypotheses and verdicts

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | fleet_executor logs decisions somewhere else now | **KILLED** | `fleet_live.py:547` writes exactly one place per arm: `automation/state/fleet/{arm}/decisions.jsonl` (append-only, `"a"` mode). No alternate log path, no `core-decisions.jsonl` write for fleet_rest arms. Confirmed by direct read: `automation/state/fleet/risky-3/decisions.jsonl` contains 128 rows for 2026-07-17, continuous 09:31:02–15:52:02 ET, no gaps. |
| H2 | Fills came from a non-fleet path hitting the same account | **KILLED** | Every one of risky-3's 5 broker order ids in `trade-today.json` (`2951f12e…`, `8c874be4…`, `64a735e0…`, `766a8874…`, `7c6858bd…`) has an **identical** broker order record embedded in `fleet/risky-3/decisions.jsonl` under `placement.broker` (entries) or `exit_pass[].actions[].broker` (exits) — same id, same `client_order_id`, same `created_at`/`submitted_at` timestamps down to the millisecond. A foreign order generator could not have produced rows fleet_live itself logged with the broker's own returned order id. |
| H3 | trade-today.json mis-attributed fills vs accounts.json creds mapping | **KILLED** | `accounts.json`: risky-3 → `PA31WIU8X15Q` (broker `custom_rest`), a broker account **not shared** with any other arm. (Contrast: safe-1/safe-2 genuinely DO share account `PA3DHPT7KIQE` post the 2026-07-11 repoint — that's why their fill ids are duplicated verbatim in `trade-today.json`'s `fills[]`. That's documented, intentional, and unrelated to risky-3.) risky-3's 5 fill ids are unique to its own arm tag and match its own decisions.jsonl 1:1. |
| H4 | decisions.jsonl was written then truncated/rotated | **KILLED** | File mtime, line count, and content are all consistent with a normal, complete trading day: 128 rows today, first row 09:31:02 ET, last row 15:52:02 ET (current time at audit: 18:20 ET, well past close — no in-flight write in progress). No `.bak`/rotated sibling for today. Only stale artifact found: `automation/state/fleet/decisions/risky-3.jsonl`, a dead file last touched 2026-06-25 (pre-dates this grid) — not consulted by any live code path (`grep` confirms zero readers), but a plausible source of confusion for a human/tool looking at the wrong path. |
| **H5 (new, found via investigation)** | **The visibility layer's attribution checker doesn't understand the fleet-arm schema** | **CONFIRMED — root cause** | See below. |

## Root cause (one sentence)

`trade_today_watcher.py`'s `_is_engine_attributed(arm, symbol)` (added 2026-07-16, commit
`b5c575e`/`9a133ee`) only recognizes the **core heartbeat** decision schema — `row["exec"]`
and `row["extra_exec"][i]["exec"]` — but fleet_rest arms (`safe-1`/`safe-3`/`risky-1`/`risky-3`,
written by `fleet_live.py`/`fleet_executor.py`) use a **completely different schema**
(`action`: `"ENTER_BEAR"`/`"ENTER_BULL"` + `placement.broker` for entries,
`exit_pass[].actions[].broker` for exits) that **never contains an `"exec"` key at all** — so
for every fleet arm, `_is_engine_attributed()` was structurally guaranteed to return `False`
on every call, independent of whether a real decision row existed.

This is the **same anti-pattern class** as the incident that motivated `_is_engine_attributed`
in the first place (2026-07-16: the function's first version only checked `row["exec"]` and
missed the `extra_exec` G4 side-channel, mislabeling a real vwap_continuation trade
"UNATTRIBUTED" until J said "I did not do anything today" forced re-investigation). That fix
patched the core-schema gap but never extended to the fleet-schema sibling branch — a classic
partial fix (LESSONS-LEARNED C14: dead/translated-but-unapplied logic, one branch fixed,
sibling branch untouched).

## Confirmed live impact — the actual smoking gun

`automation/state/discord-outbox.jsonl` for 2026-07-17 contains **13 fleet-arm fill pings —
every single fleet fill today — all labeled "UNATTRIBUTED FILL (no matching decision row)"**:
4 for safe-3, 4 for risky-1, 5 for risky-3. This is almost certainly the actual origin of the
"zero ENTER verdicts" premise: whatever surface generated that claim was reading this
watcher's output (or a downstream consumer of the same function), not the raw decisions.jsonl
file itself. The raw file was correct the entire time.

## Full reconciliation — risky-3 (5 fills, +$248)

| Broker order id | Time (ET) | Symbol | Side/Qty | Price | Matching decisions.jsonl row |
|---|---|---|---|---|---|
| `2951f12e-94fb-4a5c-99a5-6425dec00464` | 11:07:06 | SPY260717P00741000 | buy 5 | 0.46 | `ENTER_BEAR` @ 11:07:02 ET, `BEARISH_REJECTION_RIDE_THE_RIBBON`, ELITE, trigger 744.82 |
| `8c874be4-9d5e-4b17-8603-2e34d8d9e7ef` | 11:13:03 | SPY260717P00741000 | sell 5 | 0.49 | `exit_pass` @ 11:13:01 ET, `SELL_ALL` stage=`structure_stop` |
| `64a735e0-491a-472d-b378-8519df80fd8f` | 13:52:03 | SPY260717P00743000 | buy 5 | 0.39 | `ENTER_BEAR` @ 13:52:02 ET, `BEARISH_REJECTION_RIDE_THE_RIBBON`, BASE, trigger 745.98 |
| `766a8874-b82d-446e-8bcd-42382346d5b1` | 15:16:04 | SPY260717P00743000 | sell 3 | 0.98 | `exit_pass` @ 15:16:02 ET, `SELL_PARTIAL` stage=`tp1` |
| `7c6858bd-7970-44d8-8065-02ac081677e8` | 15:28:04 | SPY260717P00743000 | sell 2 | 0.67 | `exit_pass` @ 15:28:02 ET, `SELL_ALL` stage=`trail` |

Round trip 1: entry 0.46 → structure-stop exit 0.49 = **+$15**.
Round trip 2: entry 0.39 → TP1 partial 0.98×3 + trail-stop 0.67×2 = **+$233**.
Total: **+$248** — matches `trade-today.json` exactly. Every leg has a matching, correctly
timestamped, correctly ordered decisions.jsonl row.

## safe-3 and risky-1 zero-net fills — reconciled

Both requested arms' 4 fills each are **real scratches, not rehearsal probes**. Rehearsal
probes are a structurally distinct, separately-tagged array in `trade-today.json`
(`rehearsal_probes[]`, 1-lot $0.01 canceled orders from `Gamma_DressRehearsal`) — none of
these fills are in that array; all are in the real `fills[]` array with `status: "filled"`.

- **safe-3**: `ENTER_BEAR` 741P×3 @0.45 (11:07 ET) → `SELL_ALL structure_stop` @0.48 (11:13 ET, +$9); `ENTER_BEAR` 742P×3 @0.30 (13:58 ET) → `SELL_ALL time_stop` @0.33 (15:40 ET, +$9). Net **~+$18** small, not exactly $0 — "zero-net" in the task framing referred to risky-1; see below. (Both entries/exits have matching decisions.jsonl rows: order ids `8670654d…`/`e67aa80f…` and `284317b1…`/`dc58ae41…`.)
- **risky-1**: `ENTER_BEAR` 741P×5 @0.49 buy (11:07 ET) → `SELL_ALL structure_stop` @0.48 sell (11:13 ET); `ENTER_BEAR` 742P×5 @0.33 buy (13:58 ET) → `SELL_ALL time_stop` @0.33 sell (15:40 ET). Entry and exit premiums are literally identical on both legs → **exact $0.00 net** — a real mechanical stop-out that happened to fill at (structure-stop leg) essentially the same premium and (time-stop leg) the identical premium, not a synthetic/rehearsal artifact. Order ids `58b74fd1…`/`86962362…` and `d7fd23e7…`/`6ea70ea1…` all present in decisions.jsonl with matching timestamps.

Both arms' full decision trails are intact — same conclusion as risky-3: no gap in the ledger,
only in the (now-fixed) watcher's attribution check.

## Fix shipped this session

`setup/scripts/trade_today_watcher.py::_is_engine_attributed()` extended with two more record
shapes (fleet ENTER via `action.startswith("ENTER")` + `placement.broker.symbol`; fleet EXIT
via `exit_pass[].symbol` + a populated `actions[].broker`), alongside the existing core
`exec`/`extra_exec` paths. Paper-only, visibility-only change — no order-placement or trading
logic touched, no `heartbeat.md`/`params.json` touched.

**Guard tests** (`backtest/tests/test_trade_today_watcher.py`, 5 new, 28/28 total green):
- `test_engine_attributed_true_for_fleet_arm_enter_row` — fixture, fleet ENTER path.
- `test_engine_attributed_true_for_fleet_arm_exit_row` — fixture, fleet EXIT path.
- `test_engine_attributed_false_for_fleet_arm_monitoring_tick_no_actions` — negative case: a monitoring tick with `exit_pass` present but empty `actions` must stay unattributed (guards against a fix that makes everything true).
- `test_engine_attributed_true_via_real_risky3_2026_07_17_incident` — pins against the REAL on-disk `fleet/risky-3/decisions.jsonl`, the exact incident this audit investigated.
- `test_unattributed_fleet_fill_label_wired_into_message_before_fix_reproduced` — end-to-end (`main()` → outbox message), reproduces the exact real-world shape that mislabeled 13/13 fleet fills today.

**Verified the guard actually reds on regression** (not vacuous): stashed the fix, reran —
all 5 new tests failed with the exact bug reproduced (`assert 'ENGINE TRADE [risky-3' in
'...UNATTRIBUTED FILL (no matching decision row) [risky-3]...'`); un-stashed, reran — 28/28
green. Money moving without a ledger row (or being *mislabeled* as if it had none) now REDs
this suite.

## Consumer sweep

`grep -rln "_is_engine_attributed\|_decision_rows_for_arm"` outside worktrees: only
`trade_today_watcher.py` itself and its test file. No other consumer to update.

## Residual (flagged, not fixed this session)

- `automation/state/fleet/decisions/` (the stale June-25 shared directory, 6 files, last
  touched 2026-06-25) is dead — zero readers found — but sitting there as a plausible trap
  for a future human/tool grep. Low priority; not itself causing any live behavior.
- `setup/scripts/fleet_journal_bridge.py`'s docstring says "`automation/state/trade-today.json`
  is a core-account-only state file, not per-arm" — this is now **stale**: the live schema
  clearly carries `"arm"` tags for all 6 accounts including fleet_rest arms. Doesn't affect
  correctness (the bridge intentionally doesn't consume that file), but the comment could
  mislead a future reader the same way the fleet-schema blind spot did here.

## STATUS.md

See dated entry appended to `automation/overnight/STATUS.md`.
