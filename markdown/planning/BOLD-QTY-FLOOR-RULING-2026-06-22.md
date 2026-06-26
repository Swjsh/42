# J-RULING-BOLD-QTY-FLOOR — Resolution & After-Hours Runbook (2026-06-22)

> **Status: DECIDED (path ii), EXECUTION DEFERRED to the after-4pm block.**
> Market is OPEN (clock = 2026-06-22 09:51 ET, Mon). No live-path edit, no flag
> flip, no heavy compute during 09:30–15:55 ET — Rule 9 (no mid-session rule
> changes) + the load-bearing heartbeat-starvation discipline (shared Max pool) +
> the DTE-STOP / WP-5 scorecards' own "ships in an after-hours weekday block, NOT
> this session" gate. This doc is the ready-to-execute artifact for that block.

## The blocker (verified, not assumed)

Bold equity = **$1,648.75** (Alpaca `get_account_info`, 09:51 ET). Per-trade cap =
the tighter of `per_trade_risk_cap_pct` 0.50 and the Bold per-tier 0–2k max_pct 0.50
→ **$824**. `pre_order_gate.py` grid at $1,648, account=bold (measured this session):

```
qty3, any premium  -> BLOCK [MIN_CONTRACTS]  (3 < 5)   <- fires FIRST (gate 5 < gate 6)
qty4, any premium  -> BLOCK [MIN_CONTRACTS]  (4 < 5)
qty5, prem<=$1.50  -> PASS
qty5, prem>=$2.00  -> BLOCK [RISK_CAP]       ($1000+ > $824)
```

## The decision: PATH (ii). Path (i) is infeasible.

**Path (i) — re-validate at qty5 — REJECTED.** qty5 × any validated ITM-2 premium
breaches RISK_CAP: ITM-2 0DTE $2.55 → $1,275; ITM-2 1DTE $3.57 → $1,785; both > $824.
Re-deriving the dollar-stop does not change notional (`premium×qty×100`). The only
qty5-affordable strikes are deep OTM (~$1.50), which WP-5 proves is the WEAK/fragile
cell (OTM-2 OOS-drop-top5 +$1.17, posQ 4/6). qty5 cannot carry a validated cell here.

**Path (ii) — per-setup min_contracts override (qty3 floor for VWAP_CONTINUATION) —
ACCEPTED.** It is the correct structural fix: the validated economics for this setup
are genuinely **qty3** (the cap forbids qty5); the 5-floor is a generic default that
breaks a cap-constrained ITM setup at a $1.6K account. With the WP-8 1DTE/$-stop
flags **already reverted to false** (params lines 66–69), `j_vwap_cont_enabled=true`
resolves to the **0DTE** cell, not the unaffordable 1DTE doubling:

| Cell the resolver yields | median prem | qty3 notional | vs $824 cap | blocked by |
|---|---|---|---|---|
| ITM-2 / **0DTE** / −8% / qty3 (flags as-is) | $2.55 | **$765** | FITS (median) | **only MIN_CONTRACTS** ← path (ii) clears it |
| ATM / 0DTE / −8% / qty3 (WP-5 ATM cell) | $1.35 | **$405** | FITS (huge margin) | **only MIN_CONTRACTS** |
| ITM-2 / 1DTE / $67.68 / qty3 (the "doubling") | $3.57 | $1,071 | RISK_CAP | account-size-gated ≥ ~$2,142 |

So path (ii) unblocks a **validated, cap-fitting** cell. Path (i) does not.

## The wrinkle path (ii) exposes — STRIKE must be reconciled (do NOT blind-flip ITM-2)

The strike override is currently `j_vwap_cont_strike_offset_bold=2` (ITM-2), set from
the **cap-blind** WP-5 recommendation. But today's 07:06 ET B9 cap-aware rescore +
L182/L183 concluded "ITM-2 is unaffordable / affordable tier = ATM for both accounts"
— that rescore ran Bold at **qty5** and never tested **qty3**. Two unresolved facts:

1. ITM-2-qty3 fits the cap only at premium ≤ $2.747 (median $2.55) → the pricier days
   **cap-truncate** → an unvalidated, partial population (the exact L180/C11 trap that
   got WP-8 reverted yesterday). Flipping ITM-2 blind would repeat that defect.
2. ATM-qty3 ($405) fits with margin, no truncation, and is the robustly-validated WP-5
   cell (OOS +$46.23/tr, posQ 6/6, 11-gate PASS) — and mirrors Safe-2's live cell.

**Therefore the strike is gated on a cap-aware qty3 A/B (ATM-qty3 vs ITM-2-qty3,
truncation modeled, live −0.08 stop). Strong prior: ATM wins** (per the 3-hour-old
B9/L182/L183 doctrine). Likely live cell = **ATM / 0DTE / qty3 / −8%** on Bold.

## The code change (path ii) — ready to apply after-hours

### 1. `backtest/lib/risk_gate.py` — params-driven per-setup floor (only lowers; never below Rule-6 floor of 3; absent key ⇒ byte-identical)

Add near the CODE_* constants:
```python
ABSOLUTE_MIN_CONTRACTS = 3  # Rule 6 hard floor (2 TP + 1 runner) — never overridable below this
```
Add helper:
```python
def _per_setup_min_contracts(setup_name, account_min, params):
    """Effective min-contracts floor for ONE setup. A params `min_contracts_overrides`
    map may LOWER the floor for a named setup (C29 — per-setup, never blanket), but only
    to as low as ABSOLUTE_MIN_CONTRACTS. Absent/unreadable/higher/<3 override => account
    floor stands (fails safe toward the stricter floor; byte-identical when key absent)."""
    if not isinstance(setup_name, str):
        return account_min
    overrides = params.get("min_contracts_overrides")
    if not isinstance(overrides, Mapping):
        return account_min
    raw = overrides.get(setup_name)
    if _is_bad_number(raw):
        return account_min
    floor = int(_as_float(raw))
    if ABSOLUTE_MIN_CONTRACTS <= floor < account_min:
        return floor
    return account_min
```
Replace gate 5 body:
```python
    effective_min_contracts = _per_setup_min_contracts(setup_name, min_contracts, params)
    if qty_i < effective_min_contracts:
        return Deny(CODE_MIN_CONTRACTS,
            f"{account}: proposed_qty {qty_i} < minimum {effective_min_contracts} "
            "(need 2 TP + 1 runner)")
```

### 2. `automation/scripts/pre_order_gate.py` — make the CLI setup-aware
- Add `p.add_argument("--setup", default="PRE_ORDER_SIZING_CHECK")`; thread it into `check(...)` → `setup_name=args.setup`.
- In `_params_for("bold")` add `"min_contracts_overrides": {"VWAP_CONTINUATION": 3}`.
- Heartbeat A5 block then calls `... --account bold --setup VWAP_CONTINUATION` so the CLI pre-check matches `check_order`.

### 3. `automation/state/aggressive/params.json` (after-hours)
- Add `"min_contracts_overrides": {"VWAP_CONTINUATION": 3}`.
- Set the strike per the A/B winner (likely `j_vwap_cont_strike_offset_bold=0` = ATM).
- Flip `j_vwap_cont_enabled=true` (and `j_vwap_cont_side="put"` first, OP-16). Recency-RED ⇒ base qty3, no scaling.

### 4. Unit test — `backtest/tests/test_risk_gate_min_contracts_override.py` (new)
- override present + VWAP_CONTINUATION + qty3 + Bold(min5) + premium fits ⇒ **ALLOW** (was MIN_CONTRACTS).
- override present + OTHER setup + qty3 ⇒ **MIN_CONTRACTS** (5-floor preserved for everything else).
- override **absent** ⇒ qty3 VWAP_CONTINUATION ⇒ MIN_CONTRACTS (**parity / byte-identical**).
- override = 2 (below Rule-6 3) ⇒ qty2 ⇒ MIN_CONTRACTS (never below 3).
- override = 7 (raises) ⇒ ignored (only lowers).
- override present + VWAP_CONTINUATION + qty3 + premium $3.57 ($1,071>$824) ⇒ **RISK_CAP** (proves the override does NOT bypass the cap — the L180-honest test: only the affordable cell trades).

## After-hours runbook (16:00 ET, weekday — autonomous, J-aware; mirrors the Safe-2 deploy gates)
1. Apply changes 1–2 + the new test. `pytest backtest/tests/test_risk_gate*.py` green.
2. **Cap-aware qty3 A/B** (real OPRA, `simulator_real`): ATM-qty3 vs ITM-2-qty3, notional-cap truncation modeled at $1,648, live −0.08 stop. Pick the strike that clears the bar (OOS>0, posQ, 11-gate incl L173, beats null). If neither clears → keep dormant + account-size-gate (do NOT flip).
3. **GYM green:** `test_engine_live_order_resolver_parity.py` + `test_graduated_guards.py` (PARITY: enabled=false byte-identical — my gate change adds parity for `min_contracts_overrides` absent too).
4. **EOD-flatten:** trivially satisfied — target is 0DTE (1dte flag stays OFF), no overnight position to flatten; expiry-agnostic flatten already verified.
5. Apply change 3 (params): override map + strike winner + `j_vwap_cont_enabled=true` (`side="put"`). Update params `_j_vwap_cont_doc` to record the ruling.
6. Report for **REVOKE** (OP-22 standing authorization). REVOKE = `j_vwap_cont_enabled=false`.

## REVOKE / revert
- Keep dormant: `j_vwap_cont_enabled=false` (current).
- Drop the floor override: remove `min_contracts_overrides` (gate reverts byte-identical).
