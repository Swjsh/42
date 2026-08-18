# Strike Matrix — Would a Different Contract Have Paid Better?

**STATUS: PROPOSE-ONLY.** No params, strategy file, or engine code touched. Nothing armed,
nothing revoked. This is research output only, per J's explicit "don't make any changes on
this though — obviously it's working."

**J's ask (in-chat, 2026-08-18, market closed):** "are we putting our winners through a matrix
for ATM, minus one, minus two, plus one, plus two... I'm just interested to see if we would have
bought a different contract today, would it have paid better? And is it a hard code of value for
the accounts to buy?"

Tool: [`backtest/tools/strike_matrix_build.py`](../../backtest/tools/strike_matrix_build.py)
(new, committed alongside this report). Machine output:
[`analysis/recommendations/strike-matrix-2026-08-18.json`](../recommendations/strike-matrix-2026-08-18.json).

---

## 0. Verdict (read this first)

- **Is the strike a hardcode? Yes, functionally, on both live paths.** The $-equity-to-offset
  MAPPING is a Python constant table (`crypto/lib/strike_selection.py`), not a params.json value,
  for CORE (Safe + Bold) and for FLEET (safe-3/risky-1/risky-3). `params.json`'s own
  `v15_strike_offset_per_tier` ladder *looks* like the live control surface but is **vestigial on
  the live core path** — only the sim/backtest orchestrator reads it (confirmed still true today,
  §1.3). The ONE place strike offset genuinely comes from a JSON value the live core path reads
  (the ribbon_ride per-setup override) is wired for Safe only, and has sat pinned at the same
  value (ATM, offset 0) since 2026-07-11 — config-changeable in principle, operationally frozen
  in practice.
- **Would a different offset have paid better? Not a clean case, once you correct for bet size.**
  Raw dollar P&L (same contract COUNT across offsets) says ITM-2 wins big: **+$65.69/trade vs
  ATM's +$41.88/trade, all trades** (**+$450.88/trade vs ATM's +$346.45, winners-only**). But
  ITM-2 costs **2.6–2.9x the notional** of what the real trade actually risked at that same
  contract count — it is a bigger bet, not a better strike. On a capital-normalized (%-return)
  basis the ranking **inverts**: ATM/OTM-1/OTM-2 all beat ITM-2 and ITM-1 on winners (§3.3). The
  honest read is **close to a wash with a mild tilt toward cheaper strikes on % return**, not a
  "switch the account to ITM-2" result — see the caveats in §2 before touching anything.
- **This is research, not a recommendation.** Per OP-16/C29, no strike change ships off one
  after-hours matrix. If this is worth pursuing, it needs a pre-registered A/B through the same
  gates every other strike-tier change in this repo has gone through (§1 links several).

---

## 1. Deliverable A — Is the strike a hardcode?

### 1.1 CORE path (`heartbeat_core.py` → `strike_selection.py`) — Safe (`safe-2`) + Bold (`bold-2`)

`setup/scripts/heartbeat_core.py:2334`:
```python
strike = ss.pick_strike(spy, equity, side, ss.V15_BOLD_CORE_TIERS if account == "bold" else ss.V15_SAFE_TIERS) \
    if ss else (int(round(spy)) + (2 if side == "P" else -2))
```
`ss` is `crypto/lib/strike_selection.py`. The tier tables are **Python constants**:

| Table | Consumer | $0–2K | $2K–10K | $10K–25K | $25K+ |
|---|---|---|---|---|---|
| `V15_SAFE_TIERS` (`strike_selection.py:61`) | Safe (`account=="safe"`) | ATM (0) | ATM (0) | Slight ITM (+1) | ITM-2 (+2) |
| `V15_BOLD_CORE_TIERS` (`strike_selection.py:153`) | Bold (`account=="bold"`) | ATM (0) | ATM (0)¹ | OTM-1 (−1) | ITM-2 (+2) |
| `V15_BOLD_TIERS` (`strike_selection.py:53`, the ORIGINAL, still fleet-default) | not used by CORE today | OTM-3 (−3) | OTM-2 (−2) | OTM-1 (−1) | ITM-2 (+2) |

¹ `$2K–10K` row was OTM-2 until the **ATM-TIER-EXTENSION-2K-10K** ship (2026-08-04, `strike_selection.py:157` comment) — a live example of "hardcode" meaning "requires a code edit," not "requires a config toggle."

**CLAUDE.md's claim ("core Safe trades ATM, fills-verified 2026-07-11") is CORRECT and still true
today** at safe-2's current equity band (`$5,501` per CLAUDE.md 2026-08-13 → the `$2K–10K` ATM
row). **`params.json`'s `v15_strike_offset_per_tier` ladder (line 212) does NOT match this table**
— it still lists OTM-3/OTM-2/OTM-1/ITM-2 (params.json:212–227) — and its own doc field says so
explicitly:

> `params.json:211` `_v15_strike_offset_per_tier_doc`: *"VESTIGIAL ON THE LIVE CORE PATH... This
> key remains a REAL, live consumer on the SIM/BACKTEST lane: `backtest/lib/orchestrator.py`'s
> `_apply_param_overrides` (T-09) reads it when a backtest supplies `account_equity`... Root
> cause: `analysis/deep-research/2026-07-11-strike-tier-reconciliation.md`."*

**This is the pre-existing discrepancy the task asked me to verify — confirmed still present,
unchanged, as of 2026-08-18.** Nobody is silently trading the wrong tier: the live core path
never reads `v15_strike_offset_per_tier` at all, it reads the hardcoded tables above. The
discrepancy is between two DOCS (`params.json`'s ladder vs. reality), not between config and
code.

### 1.2 The per-setup override — genuinely params-driven, but pinned

`heartbeat_core.py:1898` (`_SETUP_STRIKE_OVERRIDES`) maps each dispatcher setup name to 3 params
keys (enable flag, Safe offset, Bold offset). Applied at `heartbeat_core.py:2384-2392`, **after**
the generic tier lookup above, **before** the order is priced:
```python
_sov = _SETUP_STRIKE_OVERRIDES.get(str(setup_name or "").lower())      # :2384
if _sov and params.get(_sov[0]):                                        # :2385
    _off_key = _sov[2] if account == "bold" else _sov[1]                # :2386
    _off = int(params.get(_off_key, 0))                                 # :2388
    strike = (_atm + _off) if side == "P" else (_atm - _off)            # :2392
```
For the two CORE always-on setups (`bearish_rejection_ride_the_ribbon` /
`bullish_reclaim_ride_the_ribbon` — CLAUDE.md's "Both directions ACTIVE," the only setups that
fire unconditionally on core):

- **Safe**: `j_ribbon_ride_strike_override_enabled=true` (`params.json:316`),
  `j_ribbon_ride_strike_offset_safe=0` (`params.json:317`) → forces ATM (offset 0), **live since
  2026-07-11, unchanged since**. At Safe's current equity band this is numerically redundant
  with the generic `V15_SAFE_TIERS` lookup (both say ATM) — but it WOULD win if equity crossed
  into the `$10K–25K` band, where the generic table wants Slight-ITM(+1) but the pinned override
  would still force ATM(0). So Safe's ribbon_ride strike is params-driven in the sense that
  changing `j_ribbon_ride_strike_offset_safe` needs no code edit — but it has been a frozen
  constant (0) for 5+ weeks, i.e. hardcoded in practice if not in mechanism.
- **Bold**: this override **does not apply**. `heartbeat_core.py:130-133` (`ACCOUNTS` dict) wires
  `account=="bold"` to a **separate params file**, `automation/state/aggressive/params.json`
  (not `automation/state/params.json`). That file has **no `j_ribbon_ride_strike_override_enabled`
  key at all** (grepped directly, confirmed absent — it only carries the unrelated
  `j_vwap_cont_strike_*` keys at lines 88-90). So `params.get(_sov[0])` is falsy for Bold, the
  whole override block short-circuits, and Bold's ribbon_ride strike falls through purely to the
  hardcoded `V15_BOLD_CORE_TIERS` lookup from §1.1. **Verified live, not assumed from the old doc
  comment** (`params.json:318`'s doc predates today by 5+ weeks and could have drifted — it has not).

**Bottom line for CORE:** Safe's strike is ATM today via **two** paths that currently agree
(hardcoded table AND the pinned override); Bold's strike is **purely** the hardcoded
`V15_BOLD_CORE_TIERS` table, no live params override in play.

### 1.3 FLEET path (`fleet_executor.py` → `accounts.json`) — safe-3, risky-1, risky-3

`fleet_executor.py:180` `_tiers_for_arm(arm)` resolves a **table NAME** from `accounts.json`
(`arm["strike_tier_table"]` or `arm["params_patch"]["strike_tier_table"]`, defaulting to
`"safe"`/`"bold"` by id-prefix if absent), then maps that name to one of the SAME hardcoded
`strike_selection.py` constants:

| Name | Resolves to | Who sets it (accounts.json) |
|---|---|---|
| `"safe"` (default fallback) | `V15_SAFE_TIERS` | nobody currently — every active fleet arm overrides |
| `"bold"` (default fallback) | `V15_BOLD_TIERS` (OTM-3/OTM-2/OTM-1/ITM-2 — the OLD table) | `safe-1` (retired) |
| `"bold_core"` | `V15_BOLD_CORE_TIERS` | **safe-3** (`accounts.json:44`), **risky-1** (`accounts.json:111`) |
| `"bold_core_pre_ext"` | `V15_BOLD_CORE_PRE_EXT_TIERS` (ATM $0-2K / OTM-2 $2-10K / OTM-1 $10-25K / ITM-2 $25K+) | **risky-3** (`accounts.json:159`, per-arm kill of the 08-04 extension, `n=14` fills net `-$653`) |

So: which hardcoded table an arm uses is config-driven (a JSON string in `accounts.json`); the
table's actual $-tier→offset numbers are not. `fleet_executor.pick_strike` call sites:
`:579` (normal arm plan, uses `_tiers_for_arm(arm)`), `:755` (`_plan_from_strategies`, can use a
**per-strategy** table instead — see next paragraph), `:890`/`:1054`/`:1109` (probe/ladder/
full-send lanes, all hardwired to `PROBE_STRIKE_TIERS`, `:820-826`, a **standalone** ATM-class
table, deliberately NOT a reference to `V15_SAFE_TIERS` so a future Safe-tier retune can't
silently also move probe pricing).

One more override layer: `STRATEGY_STRIKE_TIERS` (`fleet_executor.py:838-840`) force-routes
`vwap_reclaim_failed_break` entries to `PROBE_STRIKE_TIERS` (ATM-class) **regardless of the arm's
own table** — this is the mechanism that keeps that ONE setup off the OTM-2 cell it's measured
failing on (see §2, C29 caveat). Currently moot either way: the fleet producer for that setup is
OFF (`automation/state/fleet/build_shared_signal.py:316` `RUN_VWAP_RECLAIM_FB = False`).

---

## 2. Deliverable B — Method (read before the table)

**Population:** every CLOSED round trip (`automation/state/fleet/fills_fifo.mine_real_arm_fills`,
`attribution=='engine'` only — never J's manual fills) for arms `{safe-2, bold-2, safe-3,
risky-1, risky-3}`, dated `2026-07-20` through `2026-08-17` inclusive.

- **2026-08-18 (today) explicitly EXCLUDED, not silently dropped**: Alpaca's option-bars endpoint
  403s on same-day 0DTE contracts (measured 2026-08-17 per `fetch_option_data.py`'s own topup
  docstring — a past 0DTE expiry returns bars fine, the CURRENT session does not). 2 trades on
  today's date were removed from the population for exactly this reason (`safe-2` x1, `bold-2`
  x1 — see `excluded_today_symbols` in the JSON).
- **183 in-window round trips found → 175 priced, 8 excluded** (`excluded_no_spot` in the JSON):
  all 8 are `2026-08-07` entries after 12:01 ET. That date's local SPY 1-minute spot cache
  (`backtest/data/spy_sip_cache/spy_1m_2026-08-07.json`) stops at 12:01 ET (file mtime 10:17
  local/12:17 ET — the refresh process died mid-day, matching this repo's own "THIS RIG KILLS ITS
  OWN PROCESSES" scar). Rather than compute an ATM anchor off a spot that could be 2+ hours stale
  (SPY can move $1-3 in that time, enough to misclassify the whole offset ladder by 1-3 strikes),
  these 8 trades are excluded and disclosed, not approximated.
- **For each priced trade:** SPY spot at the real `entry_ts_et` is read from the local 1-minute
  cache (gap-tolerant to 300s, the same tolerance `option_pricing_real.bar_containing()` already
  uses for option bars — verified this cache is ET wall-clock, not UTC, via the 09:30 volume
  spike). `atm = round(spot)`. The 5 counterfactual strikes use the SAME sign convention as
  `strike_selection.StrikeTier` (positive = ITM): calls `atm − offset`, puts `atm + offset`.
- **Pricing model:** every offset (and the REAL strike, for a matched baseline) is priced with
  `option_pricing_real.bar_containing()` at the real `entry_ts_et` and real `exit_ts_et` (the
  LAST sell leg's timestamp for multi-leg TP1+runner exits), using each 5-min bar's `vwap` as the
  fill proxy — the same primitive the rest of the backtest engine already trusts, no new fill
  model invented.
- **Contracts:** `topup_from_fills_ledger()` ran first (0 missing — nightly fold already had every
  REAL traded contract cached). 192 unique contracts needed across all 5 offsets × 175 trades;
  152 already cached, **40 fetched** via `fetch_contract_bars` directly (well under the ~150 cap;
  0 failures, 0.35s sleep between calls).

### 2.1 Why the headline number is NOT simply "modeled P&L per offset" — 3 corrections

1. **Model vs. real, not model vs. model, if compared carelessly.** The real trade's `real_pnl`
   is broker-exact (spread-crossing, live marketable-limit fills). The 5-min-bar-vwap model
   applied to the SAME strike the real trade used (`modeled_actual_pnl`) differs from
   `real_pnl` by a **mean absolute $53.35/trade (all trades, n=174) / $85.94/trade (winners,
   n=54)**. Every delta in §3 is therefore **modeled-vs-modeled** (counterfactual offset vs. the
   same bar-vwap model applied to the real strike) — never modeled-vs-broker-exact — so the
   comparison is apples-to-apples, but treat every number as directional, not exact.
2. **Leverage/notional artifact (the big one).** Raw $ P&L holds contract COUNT fixed across all
   5 offsets. ITM strikes cost far more per contract than OTM/ATM ones — measured: **ITM-2's
   mean entry premium is $2.57 vs. the real trades' own mean $1.03 (2.6x); ITM-1 is $1.84
   (1.8x); OTM-2 is $0.55 (0.5x)**. A same-contract-count ITM-2 buy is therefore a **2.6-2.9x
   bigger bet** than what was actually risked, and Rule 6's per-trade risk cap (30% Safe / 50%
   Bold) would commonly have refused that qty at that premium in real life. §3 reports both the
   raw $ table (what J asked for) AND a capital-normalized (%-return-on-notional) table, because
   the raw $ table alone would overstate ITM's case by conflating "better strike" with "bigger
   bet."
3. **C29 (this repo's own scar — exit knobs ratified on one strike tier don't transfer to
   another).** Every offset's exit price is read at the REAL trade's own exit timestamp — this
   answers *"what would this other contract's premium have been at the moment the real exit
   fired,"* it does **not** re-run `exit_manager`'s stop/TP1/trailing logic against that
   contract's own premium path. A different strike has different delta/theta and could have hit
   a %-based catastrophe stop or a chart-stop-triggered exit earlier or later than the real trade
   did. Nothing here validates that the exit RULE would behave the same way on a different
   strike — only that this matrix's numbers use "same clock" pricing, not "same clock, replayed
   exit logic."

### 2.2 min_entry_premium floor (params.json:48, value `0.30`)

A counterfactual entry priced below $0.30 is **excluded from n_priced/totals** and counted
separately as `floor_blocked` — the live engine (`heartbeat_core._execute` AND
`fleet_executor.finalize`, both lanes) would have refused these at plan time, so they are not
"available" alternatives. This hits the cheap end hard: **19/174 OTM-1 and 46/173 OTM-2
counterfactuals (all-trades pool) would have been floor-blocked** (of the trades where a bar
existed to check at all) — meaning OTM-2's reported
average is measured on the SUBSET of days its premium happened to clear $0.30, a mild
survivorship lean in the cheap direction that's worth remembering when reading its favorable
%-return number in §3.3.

### 2.3 vwap_reclaim_failed_break / OTM-2 (the note the task flagged)

`automation/state/fleet/strategies.py:186-197`'s `VWAP_RECLAIM_FAILED_BREAK` docstring: *"validated
at ATM (Safe-2) and ITM-2 (Bold); OTM-2 measured FAILING (theta/delta)."* Structurally moot for
this population: §1.3 already showed `STRATEGY_STRIKE_TIERS` force-routes that ONE setup to an
ATM-class table regardless of arm, and its fleet producer is currently OFF
(`RUN_VWAP_RECLAIM_FB=False`). No trade in this population could have been routed to the failing
cell today — this matrix's OTM-2 numbers are governed by whatever setups actually fired
(predominantly `ribbon_ride`, both directions — the only always-on setup per CLAUDE.md), not by
the specific setup this caveat warns about.

### 2.4 Concentration (C4 doctrine — disclose it, don't let n inflate confidence)

**175 trades is NOT 175 independent bets.** All 5 arms trade the SAME `build_shared_signal.py`
output (MAP.md: *"on 08-07 all four bought the same contract within 15 seconds"*) — within a
signal cluster, the strike/sizing/exit-patch is the only thing that differs by arm. Measured:
**175 trades collapse to 64 unique (date, contract) combos across 20 unique dates**, one date
alone (`2026-08-12`, 11 legs on one symbol) contributing 38 of the 175 rows. Read every n in §3
as bounded by ~64 independent signals, not the row count. Winners' top-3-trade P&L share by
offset (a single/two-trade artifact check): ITM-2 20.1%, ITM-1 21.4%, ATM 23.6%, OTM-1 28.1%,
OTM-2 31.5% — moderate concentration everywhere, worst at OTM-2 (also its smallest n).

---

## 3. Deliverable B — The matrix

### 3.1 ALL TRADES (n=175 priced; population = every closed round trip 2026-07-20..08-17)

| Offset | n priced | floor-blocked | **Total $** | **Mean $/tr** | modeled WR | notional vs. actual | **mean % return** | actual (matched) | **Δ % return** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ITM-2 | 174 | 0 | +$11,429.73 | +$65.69 | 28.7% | 2.57x | 6.1% | 9.1% | **−3.0** |
| ITM-1 | 170 | 0 | +$9,458.86 | +$55.64 | 27.6% | 1.83x | 7.4% | 9.3% | **−1.9** |
| **ATM** | 174 | 0 | +$7,287.43 | +$41.88 | 24.7% | 1.27x | 9.1% | 9.1% | **0.0** |
| OTM-1 | 155 | 19 | +$4,088.60 | +$26.38 | 20.6% | 0.87x | 5.6% | 5.6% | **0.0** |
| OTM-2 | 127 | 46 | +$4,175.74 | +$32.88 | 25.2% | 0.61x | 15.6% | 12.0% | **+3.6** |

Real broker-exact grounding for this same 175-trade pool: total **+$873.00**, mean **+$4.99/tr**,
WR **30.9%**. (Modeled WR differs from broker WR because ~31% of the pool wasn't actually traded
ATM — see §3.4 — so the "ATM" column reprices those as a genuine counterfactual, not a
sanity-check of the real fills.)

### 3.2 WINNERS ONLY (n=54; real_pnl > 0 — the population J specifically asked about)

| Offset | n priced | floor-blocked | **Total $** | **Mean $/tr** | modeled WR | notional vs. actual | **mean % return** | actual (matched) | **Δ % return** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ITM-2 | 54 | 0 | +$24,347.72 | +$450.88 | 74.1% | 2.88x | 37.9% | 67.0% | **−29.1** |
| ITM-1 | 52 | 0 | +$21,900.47 | +$421.16 | 76.9% | 2.04x | 50.0% | 69.6% | **−19.6** |
| **ATM** | 54 | 0 | +$18,708.41 | +$346.45 | 74.1% | 1.39x | 63.1% | 67.0% | **−3.9** |
| OTM-1 | 42 | 12 | +$13,262.74 | +$315.78 | 71.4% | 1.01x | 73.2% | 67.5% | **+5.7** |
| OTM-2 | 39 | 15 | +$9,962.16 | +$255.44 | 76.9% | 0.70x | 93.4% | 72.7% | **+20.7** |

Real broker-exact grounding: total **+$13,228.00**, mean **+$244.96/tr**, WR 100.0% (by
definition — this is the winners pool).

**This is where the raw-$ vs. %-return tables tell opposite stories.** Raw dollars rank
ITM-2 > ITM-1 > ATM > OTM-1 > OTM-2 — the ranking J would see from "which column has the biggest
number." %-return-on-capital ranks the exact reverse: OTM-2 > OTM-1 > ATM > ITM-1 > ITM-2. Both
are "true" — they're answering different questions ("biggest $ if I buy the same contract count"
vs. "best use of the same dollar of risk"). Given Rule 6's fixed-%-of-equity risk cap, the second
question is the one that matters for "should the account buy something different."

### 3.3 Concrete example (illustrates the leverage effect directly)

`safe-3`, 2026-07-29, bull call, real strike 740 (spot-at-entry implied ATM=737, so the REAL
trade was **OTM-3**, entry $0.85, held 14:34:48→15:04:48 ET, broker-exact **+$265.00**, modeled
(bar-vwap at the same strike) +$400.91 / +145.9%):

| Offset | Strike | Entry | Exit | $ P&L | % return |
|---|---:|---:|---:|---:|---:|
| ITM-2 | 735 | $3.32 | $6.18 | **+$859.68** | 86.4% |
| ITM-1 | 736 | $2.72 | $5.62 | **+$869.34** | 106.4% |
| ATM | 737 | $2.09 | $4.86 | +$830.80 | 132.4% |
| OTM-1 | 738 | $1.70 | $4.02 | +$694.09 | 135.8% |
| OTM-2 | 739 | $1.26 | $3.23 | +$589.80 | **156.1%** |

Every offset made money (SPY ran hard that afternoon) — but the $ column and the % column point
opposite directions for "which was best," for exactly the reason in §2.1.2: ITM-1's extra ~$40
of raw dollars over OTM-2 cost ~2.2x more capital to obtain.

### 3.4 Real strike distribution (what was actually bought, this population)

| Real offset | n | share |
|---|---:|---:|
| ATM | 120 | 68.6% |
| OTM-2 | 24 | 13.7% |
| OTM-1 | 16 | 9.1% |
| OTM-3 or wider (pre-dates the 08-01/08-04 ATM-tier extensions, §1.3) | 14 | 8.0% |
| ITM-1 | 1 | 0.6% |

### 3.5 Per-arm composition (context, not a separate finding)

| Arm | n priced | winners | WR |
|---|---:|---:|---:|
| safe-2 | 41 | 10 | 24.4% |
| bold-2 | 21 | 4 | 19.0% |
| safe-3 | 23 | 10 | 43.5% |
| risky-1 | 44 | 16 | 36.4% |
| risky-3 | 46 | 14 | 30.4% |

---

## 4. Disclosures (everything that could NOT be priced, and why)

- **2 trades excluded — same-day 403** (2026-08-18, `safe-2` + `bold-2`): Alpaca has no bars for
  a contract until the session after it expires.
- **8 trades excluded — no local spot coverage** (all `2026-08-07` after 12:01 ET, across
  `safe-2`×2, `safe-3`×2, `risky-1`×2, `risky-3`×2): local 1-min SPY cache for that date stops at
  12:01 ET (partial-day cache gap, unrelated to this task). None were re-priced off stale data.
- **Per-offset cell gaps** (bar exists for the contract but no bar covers the exact
  entry/exit timestamp, `no_bar_at_entry_or_exit_ts`): ITM-1 4 cells, OTM-2 2 cells, out of
  175×5=875 total cells (~0.7%) — negligible.
- **1 trade with no `modeled_actual_pnl`** (real-strike bars didn't cover its entry or exit
  timestamp) — excluded from every offset's matched-baseline delta for consistency, counted in
  `n_no_data`.
- **Floor-blocked counterfactuals** (§2.2): OTM-1 19/174 (all) · 12/54 (winners); OTM-2 46/173
  (all) · 15/54 (winners) — excluded from stats, not silently priced through the floor.

Full per-trade, per-offset detail (entry/exit price, $ P&L, % return, floor flag, status) is in
[`strike-matrix-2026-08-18.json`](../recommendations/strike-matrix-2026-08-18.json)'s `trades`
array (175 rows × 5 offset cells each).

---

## 5. Bottom line

1. **Hardcode: yes**, on the number itself — both live paths ultimately read
   `crypto/lib/strike_selection.py` Python constants, and the one place a JSON value genuinely
   reaches the live core path (Safe's ribbon_ride override) has been pinned to the same value for
   5+ weeks. `params.json`'s parallel `v15_strike_offset_per_tier` ladder is real but sim-only —
   confirmed, not just repeated from the old doc note.
2. **Matrix: no clean win for switching.** Raw dollars favor ITM-2 by a wide margin, but that's
   substantially a bigger-bet effect (2.6-2.9x the real notional at equal contract count) that
   Rule 6's risk cap would not commonly allow in practice. Capital-normalized, the current ATM
   choice sits in the middle of the pack, with a real-but-modest edge showing up for cheaper
   (OTM-1/OTM-2) strikes on winners specifically — undercut by floor-blocking ~30% of those
   contracts and by C29 (no offset here has its exit logic re-validated).
3. **Nothing armed.** If OTM is worth a real look, the next step per this repo's own gates
   (§1.3's `atm-tier-extension` preregs are the template) is a **pre-registered A/B** with its own
   kill criterion — not a same-night flip off an after-hours matrix.
