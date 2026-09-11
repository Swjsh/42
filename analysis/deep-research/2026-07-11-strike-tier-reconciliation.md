# Strike-Tier Reconciliation — What Each Surface Actually Trades

**Spawned from commit `81b25b4`'s open finding + task `task_265ea4d0`, 2026-07-11.** Scope: three
sources disagree about what strike tier Safe-side accounts trade; resolve it against real fills,
not config archaeology. Read-only — no params/config/accounts.json touched, no orders placed.

**Ground-truth method:** reconstructed every real entry fill's strike tier for
2026-06-26→2026-07-09 (the ledger-forensics window) from `automation/state/fills-ledger.jsonl`
(broker-truth Alpaca fills) joined to SPY spot-at-entry via `automation/state/core-decisions.jsonl`
(nearest-timestamp join, median gap 1.5s, max 25.2s, zero rows over the 120s tolerance ledger-
forensics itself uses). Cross-validated: 112 distinct entry orders / 109 engine-attributed —
**exact match** to `analysis/deep-research/2026-07-11-ledger-forensics.md`'s independently-computed
112-episode / 109-engine-episode totals. Full row-level detail written to scratchpad during this
run (research artifact, not committed, same convention ledger-forensics used).

---

## 1. Headline

- **Only ONE of six SPY 0DTE accounts trades ATM: core Safe (`safe-2`) — 100% of its 17 engine
  fills this window.** It gets there via the GENERIC strike fallback, not the ribbon_ride
  override tonight's commit armed (which is numerically redundant with that fallback at current
  equity — see §4b).
- **All five other accounts trade OTM strikes, 100% of the time** — core Bold (`bold-2`) and, more
  importantly, **both "safe"-branded fleet arms** (`safe-1`, `safe-3`). They are deliberately
  routed to the OTM ("bold") tier table by an explicit `params_patch` in
  `automation/state/fleet/accounts.json`, unrelated to branding.
- **Tonight's own `STATUS.md` blast-radius table for commit `81b25b4` is factually wrong about the
  fleet lane.** It states `safe-1`/`safe-3` resolve to `V15_SAFE_TIERS` (ATM) via `_tiers_for_arm`.
  They actually resolve to `V15_BOLD_TIERS` (OTM) — confirmed both in code
  (`_tiers_for_arm`'s `params_patch` check wins before any id-prefix default) and in 100% of both
  arms' real fills (43/43 engine entries, zero ATM).
- **Independently verified LIVE, this session:** the core Safe Alpaca account (`mcp__alpaca__*`,
  key `PK65KLS3...`) returns **401 Unauthorized** right now. A control call to the Bold account
  (`mcp__alpaca_aggressive__*`) succeeded normally (status `ACTIVE`, equity $1,963.04) — so the
  401 is specific to the Safe credential, not a general outage. This corroborates (does not
  itself *prove* the specific mechanism behind) commit `81b25b4`'s "account deleted, pending
  replacement" claim. Last confirmed-good Safe equity fetch on file:
  `automation/state/circuit-breaker.json`, Friday 2026-07-10 08:30 ET premarket, $1,512.71,
  `SAFE_ALPACA_MCP_401: false`. The break happened sometime between then and now.
- **The fleet accounts registry itself hasn't caught up either:** `automation/state/fleet/accounts.json`'s
  `safe-2` entry still reads `"status": "active"` despite the claimed deletion — a separate,
  smaller drift item, filed below.

---

## 2. Per-account strike-tier histogram (real fills, 2026-06-26 → 2026-07-09)

Engine-attributed entries only (J's own hand trades excluded per ledger-forensics' attribution
convention; shown separately below). Deduped by broker `order_id` (126 raw buy-fill rows include
13 partial-fill splits of the same order; 112 distinct entry orders remain).

| Account | Lane | n (engine) | ATM | OTM-1 | OTM-2 | OTM-3 | ITM-1 | ITM-2 | % ATM |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **safe-2** (core Safe) | core | 17 | **17** | 0 | 0 | 0 | 0 | 0 | **100%** |
| **bold-2** (core Bold) | core | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0% |
| **safe-1** | fleet | 24 | 0 | 0 | 7 | 17 | 0 | 0 | 0% |
| **safe-3** | fleet | 19 | 0 | 0 | 2 | 17 | 0 | 0 | 0% |
| **risky-1** | fleet | 19 | 0 | 0 | 2 | 17 | 0 | 0 | 0% |
| **risky-3** | fleet | 27 | 0 | 0 | 5 | 22 | 0 | 0 | 0% |
| **Total (engine)** | | **109** | **17** | 0 | 16 | 76 | 0 | 0 | **15.6%** |

Manual/other-attributed entries excluded from the table above (J's own hand trades embedded in
the same accounts, per ledger-forensics §1's attribution convention): `safe-2` ×1 (OTM-2, 2026-06-26),
`bold-2` ×2 (OTM-1, ITM-1). Including these, all-attribution totals are 18/6/24/19/19/27 = 113 —
one more than ledger-forensics' 112 because that report's per-account appendix table (§ "By
account/arm") counts 18 for `safe-2`'s "all" column too; the +1 discrepancy versus its headline
112 is the same single mixed-attribution episode ledger-forensics' §1 already disclosed
(`safe-2 SPY260626P00732000`, engine entry / untagged exit) — not a new gap, the same one,
re-surfaced here because this reconstruction counts by entry fill, not by closed episode.

**Sample evidence rows** (symbol, spot-at-entry, computed offset):

```
safe-1   2026-06-29 SPY260629C00743000  spot@entry=740.97  atm=741  offset=-2  OTM-2
safe-1   2026-06-30 SPY260630C00746000  spot@entry=743.16  atm=743  offset=-3  OTM-3
safe-3   2026-06-29 SPY260629C00743000  spot@entry=740.96  atm=741  offset=-2  OTM-2  (same tick as safe-1 — shared signal)
risky-1  2026-06-30 SPY260630C00746000  spot@entry=743.16  atm=743  offset=-3  OTM-3
bold-2   2026-06-26 SPY260626P00729000  spot@entry=732.02  atm=732  offset=-3  OTM-3
safe-2   2026-06-26 SPY260626P00732000  spot@entry=732.02  atm=732  offset=+0  ATM
safe-2   2026-07-02 SPY260702P00746000  spot@entry=746.26  atm=746  offset=+0  ATM
```

`safe-1`/`safe-3`/`risky-1` picking the identical strike on the identical tick (2026-06-29,
2026-06-30) is expected, not a bug: all fleet arms read the same shared signal off the same SPY
tape (`automation/state/fleet/shared-signal.json`) and, per §3, three of these four fleet arms
resolve to the identical tier table.

---

## 3. Config → lane → reality map

| Account | Execution lane | Strike code path (file:line) | Table resolved | Real fills | Matches CLAUDE.md prose / `params.json` ladder (OTM-3/-2/-1/ITM-2)? |
|---|---|---|---|---|---|
| `safe-2` | core, `heartbeat_core.py` | generic fallback, `_execute()` line 1229: `ss.pick_strike(spy, equity, side, V15_BOLD_TIERS if account=="bold" else V15_SAFE_TIERS)` — reads the **hardcoded Python constant**, never touches `params.json#v15_strike_offset_per_tier` | `V15_SAFE_TIERS` (ATM/ATM/ITM-1/ITM-2) | 100% ATM | **NO** — contradicts both |
| `bold-2` | core, `heartbeat_core.py` | same line, `account=="bold"` branch | `V15_BOLD_TIERS` (OTM-3/-2/-1/ITM-2) | 100% OTM-3 | YES |
| `safe-1` | fleet, `fleet_executor.py` | `_tiers_for_arm()` (line 146-158): checks arm's `params_patch.strike_tier_table` **first**; `accounts.json` sets it explicitly to `"bold"` for this arm | `V15_BOLD_TIERS` (forced) | 100% OTM (7 OTM-2 / 17 OTM-3) | Numerically yes, but **not because of `params.json`** — it never reaches that file; coincidental value match against a hardcoded constant |
| `safe-3` | fleet | same, `params_patch.strike_tier_table="bold"` | `V15_BOLD_TIERS` (forced) | 100% OTM (2 OTM-2 / 17 OTM-3) | same caveat as `safe-1` |
| `risky-1` | fleet | `_tiers_for_arm()`: no `params_patch` override present → falls to id-prefix default (`"bold"`, since `"risky-1"` doesn't start with `"safe"`) | `V15_BOLD_TIERS` | 100% OTM | YES (same caveat) |
| `risky-3` | fleet | same default | `V15_BOLD_TIERS` | 100% OTM | YES (same caveat) |

**Why `safe-1`/`safe-3` are patched to the OTM table despite being "safe" arms** —
`accounts.json`'s own `sizing_profiles.safe` doc string states the reason plainly: *"OTM strikes
(params_patch strike_tier_table='bold' to fit the $600 notional cap at $2K — ATM doesn't place
this small)."* This is a deliberate, documented sizing decision (ATM premiums are typically too
expensive to clear the strategy's own minimum-contract floor, Rule 6, at $2K equity), not an
oversight in `accounts.json` itself — the oversight is that nobody carried this fact into
`CLAUDE.md`'s tier-table prose, `params.json`'s own ladder, or (as of tonight) `STATUS.md`'s
blast-radius table for `81b25b4`.

**Root cause of the three-way disagreement — a 2026-06-18 migration that was never fully swept:**
`git log --diff-filter=D -- automation/state/params_safe.json` shows `automation/state/params_safe.json`
and `automation/state/params_bold.json` were **both explicitly retired on 2026-06-18** (commit
`5da0da2`, ironically titled "bulletproof engine against partial-visibility (producer/consumer
contract) bugs" — ret retired paths preserved at `automation/state/params_safe.json.retired-2026-06-18`
/ `.../params_bold.json.retired-2026-06-18`, plus `.lastgood` snapshots). The retired
`params_safe.json` snapshot's own `v15_strike_offset_per_tier` **already matched** `V15_SAFE_TIERS`
(ATM/ATM/ITM-1/ITM-2) — so the migration correctly moved Safe's ATM ladder into the hardcoded
Python constant. What it left behind, unswept:
- `crypto/lib/strike_selection.py`'s own module docstring still says `automation/state/params.json`
  is "Bold/base config" and that "Account-specific overrides (`params_safe.json`)" make Safe ATM —
  describing a file that has not existed at that path in three and a half weeks.
- `automation/state/params.json#v15_strike_offset_per_tier` is now a **vestigial key on the live
  core-Safe strike path** — still present, still shows the OTM-3/-2/-1/ITM-2 ladder, but
  `heartbeat_core.py` line 1229 never reads it for Safe. (It is NOT dead everywhere — the
  sim/backtest lane genuinely consumes this key: `backtest/lib/orchestrator.py`,
  `backtest/lib/filters.py`, `setup/scripts/fast_path_executor.py`, and
  `setup/scripts/engine_contract.py` all read `params["v15_strike_offset_per_tier"]` for
  replay/contract-validation purposes. It is specifically dead on the ONE path this task was asked
  to check: the live core-Safe entry strike.)
- `backtest/lib/orchestrator.py:359` still comments "`params_safe.json` / `params_bold.json` carry
  `v15_strike_offset_per_tier`" — both files it names are retired.
- At least one sim tool loads the stale assumption directly rather than through any override:
  `backtest/safe_midday_trendline_gate_revalidate_current_engine.py:75-76` explicitly does
  `params_overrides={"v15_strike_offset_per_tier": json.load(open(...params.json...))["v15_strike_offset_per_tier"]}`
  while its own file-level comment (line 10) calls this "Safe sizing: OTM-2 tier at $2,000 equity."
  That tool is testing OTM-2 and labeling it Safe, when live Safe has been ATM since (at latest)
  the 2026-06-18 migration.
- `CLAUDE.md`'s "The strategy" section tier-table prose ("OTM-3 at $1K / OTM-2 at $2-10K / OTM-1
  at $10-25K / ITM-2 at $25K+") describes `V15_BOLD_TIERS` only, unlabeled as Bold-specific — a
  reader has no way to know from that sentence alone that Safe is a different ladder.

---

## 4. The four answers

**(a) What did each surface actually trade in the window (2026-06-26 → 2026-07-09)?**
Exactly the histogram in §2. Core Safe traded 100% ATM. Every other account — core Bold and all
four fleet arms, **including both "safe" fleet arms** — traded 100% OTM (predominantly OTM-3,
some OTM-2, equity-tier dependent). The "safe" fleet-arm branding does not mean ATM; only the
single core-lane Safe account (`safe-2`, `mcp_heartbeat` execution) does.

**(b) What will each surface trade MONDAY given commit `81b25b4`?**
- **Core Safe:** nothing — the wired Alpaca credential is returning 401 right now (independently
  verified live, this session; see §1). Whenever J reprovisions the account, ribbon_ride will
  trade **ATM — unchanged from what it was already doing.** The override's flat offset
  (`j_ribbon_ride_strike_offset_safe = 0`) and the generic fallback's tier-0 offset
  (`V15_SAFE_TIERS[0..1].strike_offset = 0`) are numerically identical at any equity under $10K,
  which covers every dollar figure this account has ever run at. The override *would* start to
  matter only if/when core-Safe equity crosses $10K — at that point the generic fallback moves
  to "Slight ITM" (+1) but the override (a flat scalar, not a tier lookup —
  `heartbeat_core.py:1236-1244`) would keep forcing 0/ATM. Not relevant today.
- **Core Bold:** unaffected — separate params file (`automation/state/aggressive/params.json`),
  no enable key present, continues OTM-3/-2 exactly as before.
- **All four fleet arms** (`safe-1`, `safe-3`, `risky-1`, `risky-3`): **completely unaffected.**
  `fleet_executor.py` has no per-setup strike-override dispatch mechanism at all (confirmed —
  grepped the file for any equivalent of `_SETUP_STRIKE_OVERRIDES`; none exists) and structurally
  cannot see the two new `params.json` keys `81b25b4` added. They continue exactly as reconstructed
  in §2: 100% OTM.
- **Net: zero live behavioral change fleet-wide from `81b25b4`**, for two independent, stacking
  reasons — the dormant account, and the override being numerically redundant with what was
  already firing even before tonight.

**(c) Was the AB scorecard's "control = live tier" framing accurate per-surface?**
No, for the one surface the override actually targets. `analysis/recommendations/ribbon-ride-strike-exit-ab.json`
(`axis1_strike.control`) and tonight's own `STATUS.md` table both label **OTM-2** as "control,
live tier" for core-Safe ribbon_ride. Per §2, core Safe's real fills this window were **100% ATM**
— the true live control was already ATM, not OTM-2. The scorecard's ATM-vs-OTM-2 comparison
(+$47.96/tr) is a legitimate simulated comparison in the abstract (it replays real OPRA bars
through the live exit-manager core, clearly disclosed as MEASURED-not-REALIZED throughout the
artifact), but calling OTM-2 "the live tier" isn't accurate for the account it's meant to describe
— it appears to trace to the scorecard reading `params.json`'s documented (but, per §3, vestigial
on this path) OTM-2 ladder as ground truth, rather than what `heartbeat_core.py` actually executes.
Practically inert either way (per 4b, nothing was armed differently), but the label itself should
not be read as "what core Safe was doing before tonight."
For the fleet safe arms, the question is moot the other way: the override is structurally
unreachable there regardless of labeling (per §3/§4b). If it *were* someday extended to the fleet
lane, "OTM-2" still wouldn't be the single right label for `safe-1`/`safe-3` — their real mix this
window is majority OTM-3 (34 of 43 engine fills) with a OTM-2 minority, not a clean OTM-2 control.

**(d) What config edit would put the FLEET safe arms on ATM? (evidence only — not applied)**
In `automation/state/fleet/accounts.json`, remove (or change to `"safe"`) the
`"params_patch": {"strike_tier_table": "bold"}` key on the `safe-1` and `safe-3` arm entries.
Deleting the key entirely is sufficient — `_tiers_for_arm()`'s fallback
(`fleet_executor.py:156`) defaults any arm id starting with `"safe"` to the `"safe"` table
automatically, so no other file needs to change. **This is not a free move**: `accounts.json`'s
own doc string explains the patch exists specifically because ATM premiums are usually too
expensive to clear the strategy's minimum-contract floor (Rule 6: min 3 contracts) at $2K starting
equity — flipping this without a compensating sizing change risks trading affordability-driven
SKIPs instead of a clean tier swap. Evaluating that tradeoff is out of this task's scope by design;
this is the mechanism, not a recommendation.

---

## 5. Doc/code drift filed

Three related, now-resolved-by-evidence discrepancies, filed to `STATUS.md` (dated entry) and
`automation/overnight/queue.md` (new active-backlog item) per this task's brief:

1. **`crypto/lib/strike_selection.py`'s own module docstring is stale** — cites
   `automation/state/params_safe.json` as the live source of Safe's ATM override; that file has
   been retired since 2026-06-18 (`automation/state/params_safe.json.retired-2026-06-18`). The
   *content* it describes is correct (Safe = ATM/ATM under $10K); the *citation* is dead.
2. **`params.json#v15_strike_offset_per_tier` and `CLAUDE.md`'s tier-table prose describe
   `V15_BOLD_TIERS`, unlabeled as Bold-only** — accurate for Bold, wrong for Safe, and there is
   nothing in either surface warning a reader that Safe diverges.
3. **Tonight's `81b25b4` blast-radius table in `STATUS.md` mis-describes the fleet lane** —
   states `safe-1`/`safe-3` resolve to `V15_SAFE_TIERS`; they resolve to `V15_BOLD_TIERS` via an
   explicit `accounts.json` `params_patch`, confirmed in code and in 100% of both arms' real
   fills. (The table's bottom-line conclusion — "net Monday behavior change is ZERO" — is still
   correct, just for a reason the table itself gets wrong: it says the fleet is unaffected *because
   it already matches*; the fleet is unaffected because the mechanism can't reach it at all,
   regardless of which table it happens to match.)
4. **Smaller, adjacent:** `automation/state/fleet/accounts.json`'s `safe-2` entry still reads
   `"status": "active"` despite the account returning 401 live (§1) — the registry hasn't been
   updated to reflect the dormancy either.

---

## 6. What was independently verified live, this session

- `mcp__alpaca__get_account_info` (core Safe key) → **HTTP 401 Unauthorized**, quoted verbatim:
  `Error calling tool 'get_account_info': HTTP error 401: Unauthorized - {'message': 'unauthorized.'}`
- `mcp__alpaca_aggressive__get_account_info` (core Bold key, control) → succeeded normally:
  `status: "ACTIVE"`, `account_number: "PA33W2KUAT40"`, `equity: "1963.04"`, `balance_asof:
  "2026-07-10"`. Confirms the 401 above is credential-specific, not an MCP/network-wide outage.
- `setup/scripts/et_clock.py` → `2026-07-11 22:53:40 Saturday EDT`, `market_hours=False` (context
  for "tonight"/"Monday" framing throughout this report).

---

## 7. Method + data sources

- **Fills:** `automation/state/fills-ledger.jsonl` (broker-truth, Alpaca FILL activities; 421 raw
  option+crypto fills → 261 SPY option fills → 126 buy-side entry fills in window → 112 distinct
  entry orders after dedup by `order_id`).
- **Spot-at-entry:** `automation/state/core-decisions.jsonl`'s `spy` field (8,725/8,732 rows have
  it), nearest-timestamp join — both core "safe" and "bold" account rows share one live SPY tape,
  so this is a valid spot source for all six accounts, not just the two core ones. Join quality:
  median gap 1.5s, max 25.2s, 0 rows over 120s.
- **Tier convention:** `crypto/lib/strike_selection.py`'s own formula, inverted —
  `atm = round(spot)`; puts: `offset = strike - atm`; calls: `offset = atm - strike`; labels
  −3/−2/−1/0/+1/+2 → OTM-3/OTM-2/OTM-1/ATM/ITM-1/ITM-2 (the union of `V15_BOLD_TIERS` and
  `V15_SAFE_TIERS`' own label sets).
- **Cross-validation:** entry-order count (112) and engine/manual split (109/3) match
  `analysis/deep-research/2026-07-11-ledger-forensics.md`'s independently-computed episode totals
  exactly — same underlying ledger, different reconstruction code, same answer.
- **Code paths read (not modified):** `setup/scripts/heartbeat_core.py` (`_execute`,
  `_SETUP_STRIKE_OVERRIDES`, lines ~1152-1245), `automation/state/fleet/fleet_executor.py`
  (`_tiers_for_arm`, lines 146-158), `automation/state/fleet/accounts.json` (arm registry),
  `crypto/lib/strike_selection.py` (tier tables + `pick_strike`/`moneyness`),
  `automation/state/params.json`, `automation/state/aggressive/params.json`,
  `automation/state/params_safe.json.retired-2026-06-18` /
  `automation/state/.lastgood/params_safe.json`, `backtest/lib/orchestrator.py`.
- **Not in scope / not audited:** the sim/replay lane's own per-setup strike dispatch
  (`backtest/lib/risk_gate.py#select_strike_offset`, flagged by tonight's `STATUS.md` as
  carrying only a `VWAP_CONTINUATION` entry) — orthogonal to what six real accounts actually
  traded, which is this task's question.
