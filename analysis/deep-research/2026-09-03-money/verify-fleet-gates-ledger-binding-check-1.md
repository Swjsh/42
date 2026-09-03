# VERIFY — fleet-gates-ledger-binding-check.md (G2 LEDGER TRUTH TABLE)

Stamp: 2026-09-03, ~14:29-14:34 ET (market hours), read-only. Independent SKEPTIC pass on
`analysis/deep-research/2026-09-03-money/fleet-gates-ledger-binding-check.md` /
`.json`, produced by `backtest/tools/fleetgates_ledger-binding-check.py`. Own re-derivation
script: `backtest/tools/fleetgates_verify_ledger-binding-check_1.py` (written fresh, not
copy-pasted; <5s runtime, read-only, no broker/network calls). Full raw output captured
in-session; key numbers reproduced below.

## Verdict up front

**NOT REFUTED on the numeric/binding claim (verdict, headline, gate x arm tables) — every
checkable number reproduces exactly.** But the report contains **one confirmed, material
factual error** in its own "facts" list: the claim that the `triggers` field is "empty on
every single row since 2026-08-06 (checked: 0 of 7,999 safe rows)" is **false**. 505 of 8,010
safe rows since 08-06 carry a non-empty `triggers` list — including **100% of
`SKIP_STRUCTURE_VETO` rows (72/72)** and **100% of `SKIP_BULL_1100_1200` rows (53/53)**, the
two gates the report's own Table A leans on hardest. The narrower claim the report actually
needed — "HOLD rows never carry a non-empty trigger set" — IS true (0 of 7,388 HOLD rows), and
that narrower fact is what the join logic (gated = `action` startswith `SKIP_`, not triggers)
actually depends on, so **the error does not propagate into any of the reported gate/arm
percentages** — every one of those reproduced to the same decimal. This is a fact-checking
overclaim inside the report, not a defect in its arithmetic. Confidence: **medium** (would be
high but for this confirmed inaccuracy sitting inside the "facts" array itself, which is meant
to be the load-bearing, independently-checked layer of the finding).

---

## What I independently re-derived (own script, own read of the raw ledgers)

Rebuilt the `core_tick_id -> {safe, bold}` join directly from `automation/state/core-decisions.jsonl`
and the `core_tick_id -> rows` join for each of `safe-3`, `risky-1`, `risky-3` directly from
`automation/state/fleet/<arm>/decisions.jsonl`, using the question's own literal definitions
(gated = that account's `action` starts with `SKIP_`; entered = the other account's `verdict`
is `ENTER_BULL`/`ENTER_BEAR`; fleet-entered = arm's `action` in
`{ENTER_BULL, ENTER_BEAR, PLACED}`).

| Check | Report claim | My independent recount | Match |
|---|---|---|---|
| n ticks both accounts present (since 08-06) | 7,998 | 8,007 (live now) / **8,001** at report's own ET-equivalent cutoff (~14:26 ET — see note) | Match within live-growth tolerance |
| Table A n (safe gated, bold ENTER) | 133 | **133** | Exact |
| Table A dates | 12 | **12** | Exact |
| SKIP_STRUCTURE_VETO (Table A) n / safe-3 / risky-1 / risky-3(raw/logged) | 54 / 5.6% / 9.3% / 1.9%(3.0%) | 54 / 5.6% / 9.3% / 1.85%(3.0%) | Exact |
| SKIP_BULL_1100_1200 (Table A) n / safe-3 / risky-1 / risky-3(raw/logged) | 53 / 15.1% / 15.1% / 13.2%(21.2%) | 53 / 15.09% / 15.09% / 13.21%(21.2%) | Exact |
| Table A aggregate (n=133) | safe-3 11(8.3%), risky-1 15(11.3%), risky-3 8(6.0%/8.7%) | safe-3 11(8.27%), risky-1 15(11.28%), risky-3 8(6.02%/8.70%) | Exact |
| Table A drop-best-day (n=103) | safe-3 8.7%, risky-1 12.6%, risky-3 7.8% | safe-3 8.74%, risky-1 12.62%, risky-3 7.77% | Exact |
| Table A named-winning-day share | 14/133 = 10.5% | 14/133 = 10.5% | Exact |
| Table B n (bold gated, safe ENTER) | 187 | **187** | Exact |
| Table B dates | 17 | **17** | Exact |
| SKIP_CONF_LVL_REC_AFTERNOON (Table B) n / risky-1 share | 45 / 53.3% | 45 / **53.33%** | Exact |
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY (Table B) n / safe-3 / risky-1 / risky-3 | 87 / 0% / 10.3% / 4.6%(5.7%) | 87 / 0% / 10.34% / 4.60%(5.7%) | Exact |
| SKIP_MIN_PREMIUM_FLOOR (Table B) n / all-arm | 32 / 12.5%,12.5%,6.25%(10.5%) | 32 / 12.5%,12.5%,6.25%(10.5%) | Exact |
| Table B aggregate (n=187) | safe-3 15(8.0%), risky-1 41(21.9%), risky-3 28(15.0%/18.7%) | safe-3 15(8.02%), risky-1 41(**21.93%**), risky-3 28(14.97%/18.67%) | Exact |
| Table B drop-best-day (n=155) | safe-3 9.7%, risky-1 26.5%, risky-3 16.8% | safe-3 9.68%, risky-1 **26.45%**, risky-3 16.77% | Exact |
| Sept-only Table A (SKIP_BULL_1100_1200 n=20, SKIP_STRUCTURE_VETO n=20) | both gates safe-3/risky-1 15.0%/5.0% | both gates safe-3/risky-1 15.0%/5.0% | Exact |
| Sept-only Table B | no gate reaches n>=10 | confirmed: max n=13 (SKIP_MIN_PREMIUM_FLOOR) | Exact |
| Symmetric-gate: SKIP_LATE_ENTRY | both=16, either=52 | both=16, either=52 | Exact |
| Symmetric-gate: SKIP_STALE_TRIGGER | both=either=120 | both=either=120 | Exact |
| Symmetric-gate: SKIP_MIN_PREMIUM_FLOOR | both=0, either=50 | both=0, either=50 | Exact |
| risky-3 retirement | last row 2026-08-28T15:53:06, 0 rows in Sept | confirmed: last row `core_tick_id 2026-08-28T15:52:02.380007`, ts_et `2026-08-28T15:53:06`; Sept-only table shows risky-3 0/0.0 on every gate | Exact |

**All 14 spot-checked `core_tick_id`s quoted in the report** (`2026-08-07T12:36:02.451616`,
`2026-08-21T13:34:02.490082`, `2026-09-03T11:21:02.576928`, `2026-08-13T11:41:02.990155`,
`2026-08-19T11:49:02.561586`, `2026-08-21T11:06:02.592949`, `2026-08-21T11:36:02.613080`,
`2026-08-12T14:16:02.973209`, `2026-08-13T15:11:02.929340`, `2026-08-26T14:56:02.621899`,
`2026-08-26T15:51:02.640393`, `2026-08-06T10:31:02.400016`, `2026-08-11T11:51:02.965227`,
`2026-08-12T11:26:03.024016`) were independently pulled and check out byte-for-byte against the
claimed gate/verdict/fleet-arm outcome in every case. Two representative rows, quoted verbatim
from my own read this session:

```
core_tick_id 2026-09-03T11:21:02.576928
  safe: action=SKIP_STRUCTURE_VETO verdict=SKIP_STRUCTURE_VETO
  bold: action=SKIP_MIN_PREMIUM_FLOOR verdict=ENTER_BULL
  safe-3=ENTER_BULL  risky-1=ENTER_BULL  risky-3=ABSENT (retired before this date)

core_tick_id 2026-08-26T14:56:02.621899
  safe: action=PLACED verdict=ENTER_BULL
  bold: action=SKIP_CONF_LVL_REC_AFTERNOON verdict=SKIP_CONF_LVL_REC_AFTERNOON
  safe-3=ENTER_BULL  risky-1=ENTER_BULL  risky-3=ENTER_BULL
```

**Note on the 7,998 vs 8,007/8,001 tick-count "gap":** the `n_ticks_both` figure grows live
during market hours. The original script's file mtime is `Sep 3 12:26` — but per this project's
own documented convention ("File mtimes are Mountain time (ET-2)"), that is **14:26 ET**, inside
the report's own stated `~14:20-15:10 ET` stamp window. Re-running my own join with the cutoff
`ts_et < 2026-09-03T14:26` gives **8,001** ticks — 3 off from the report's 7,998, well within
one tick's worth of jitter in exactly where the cutoff landed. This is not a disagreement, it
confirms the report's number was live and correctly time-stamped, not stale or miscounted.

---

## Confirmed error: the `triggers`-field "fact" is false as literally stated

The finding's `facts[1]` (and the .md report's Method section, same wording) states:

> "The literal 'triggers' field the question also names is empty on every row since 08-06
> (0/7,999 safe rows) -- gated set is defined by action startswith('SKIP_') only."

I ran this exact check myself against `automation/state/core-decisions.jsonl`, `account=safe`,
`ts_et >= 2026-08-06`:

```
total safe rows since 08-06:                8,010
HOLD rows:                                   7,388  (nonempty triggers: 0)
NOT_FLAT rows:                                 222  (nonempty triggers: 222)
SKIP_STALE_TRIGGER rows:                       122  (nonempty triggers: 5)
SKIP_STRUCTURE_VETO rows:                       72  (nonempty triggers: 72)
SKIP_BULL_1100_1200 rows:                       53  (nonempty triggers: 53)
SKIP_LATE_ENTRY rows:                           52  (nonempty triggers: 52)
PLACED rows:                                    39  (nonempty triggers: 39)
RISK_DENY_SETTLEMENT rows:                      25  (nonempty triggers: 25)
VETOED_BY_MODELS rows:                          16  (nonempty triggers: 16)
SKIP_DOJI_ENTRY_BAR rows:                       15  (nonempty triggers: 15)
SKIP_DUPLICATE_CLAIM rows:                       4  (nonempty triggers: 4)
SKIP_ORDER_STILL_OPEN_AFTER_CANCEL rows:         1  (nonempty triggers: 1)
SKIP_STALE_SIGHT rows:                           1  (nonempty triggers: 1)
--------------------------------------------------
Total safe rows with non-empty triggers:       505 of 8,010 (6.3%)
```

So **every non-`HOLD` row carries a non-empty `triggers` list**, including 100% of the two
gates (`SKIP_STRUCTURE_VETO`, `SKIP_BULL_1100_1200`) that Table A's "BINDING (mostly)" call is
built on. The report's stated check ("0/7,999 safe rows") is false as a universal claim over
all safe rows; it is only true if silently restricted to `action == "HOLD"` rows (0 of 7,388
HOLD rows have non-empty triggers — I verified this narrower claim is correct). The report never
discloses that restriction; it states the broader, false version as a checked fact.

**Why this doesn't change the verdict:** the report's actual "gated" definition, used
throughout the tables, is `action` startswith `SKIP_*` — never the `triggers` field. That
definition is applied correctly and consistently (confirmed by the exact-match recount above),
so this error is quarantined to one sentence of methodological color and does not touch any
reported percentage, n, or quoted tick. It would matter if a future reader relied on the
"triggers is always empty" claim for a different purpose (e.g. concluding the `triggers` field
is dead/unused generally) — it is not dead; it's populated on every actioned (non-HOLD) row and
would need re-deriving before anyone treats it as a data source.

---

## Other things checked and found consistent (not flagged)

- **GATE_KEYS mapping.** Verified directly against `automation/state/params.json` and
  `setup/scripts/heartbeat_core.py` (read-only): `structure_veto_enabled` (line 314),
  `block_bull_1100_1200` (line 215), and `require_bearish_fill_bar` /
  `block_conf_lvl_rec_afternoon` all appear in the live `GATE_KEYS` list
  (`heartbeat_core.py:184-199`) and in `params.json` — the action-name-to-params-key mapping the
  report asserts with confidence is correct.
- **risky-3 retirement.** Confirmed independently: last ledger row
  `core_tick_id=2026-08-28T15:52:02.380007`, `ts_et=2026-08-28T15:53:06...`. Sept-only join
  produces 0 risky-3 rows for every gate, matching the report's "retired, not evidence the gate
  binds it" caveat.
- **`SKIP_MIN_PREMIUM_FLOOR` never symmetric.** Confirmed: 0 of 50 window-wide occurrences hit
  both accounts together — genuinely per-account.
- **Row-count growth (safe-3/risky-1 12,590->9,011+... rows since the report ran).** Explained
  entirely by ~2 hours of additional live market-hours ticks between the report's script run
  (~14:26 ET per corrected mtime) and this verification (~14:34 ET) — proportional, not a
  discrepancy.
- **Underpowered-gate n's** (`SKIP_DOJI_ENTRY_BAR` n=9, `SKIP_STALE_SIGHT` n=1/n=2,
  `SKIP_STALE_TRIGGER` n=5) all reproduce exactly and are correctly excluded from
  binding/non-binding calls per the report's own n>=10 rule.

## What I did not re-derive

Did not re-verify the causal/mechanism claim (why Table B leaks ~2x more than Table A) against
`_plan_from_strategies` internals — the report itself labels that portion INFERENCE, not FACT,
and I have no reason to add or subtract confidence there; it is architecturally consistent with
`veto-scope-safe-3.md`'s independently-traced code path (`build_shared_signal.py:802-820`),
which I read but did not re-execute. Did not score P&L impact of the leak (report explicitly
scopes that out too).

## Bottom line for whoever consumes this

Treat the gate x arm tables, aggregates, drop-best-day robustness checks, and every quoted
`core_tick_id` in `fleet-gates-ledger-binding-check.md` as **independently verified and
reliable** — reproduced exactly on a from-scratch rebuild of the join. Do **not** cite the
report's "triggers field is empty on every row since 08-06" sentence anywhere else — it is
wrong; the correct, narrower fact is "triggers is empty on HOLD rows only; every actioned
(non-HOLD) row, including every SKIP_* gate row, carries a populated triggers list."
