# DEPLOYMENT HARDENING — vwap_continuation 1DTE WP-5/WP-8 (pre-Monday, SAFE/read-only)

**Date:** 2026-06-21 (Sunday) · **Cost:** $0 · **Scope:** read-only verification of an
already-deployed config; no orders, no commit. **Verdict: MONDAY_READY** (Safe-2 live, as
scoped). One pre-existing, already-documented, by-design gap on Bold (edge inert there —
no mis-trade risk).

The deployment armed #1 `vwap_continuation` at its validated cell for Monday via the A5
deterministic resolver (`backtest/lib/live_order_resolver.py#live_order_params`), invoked
by the VWAP_CONTINUATION block in `automation/prompts/heartbeat.md`. New live
capabilities: 1DTE contract selection + a dollar-anchored premium backstop. EOD-flatten
(`automation/prompts/eod-flatten.md` + aggressive mirror) made expiry-agnostic.

Reproduce: `backtest/.venv/Scripts/python.exe backtest/_vwap_harden_verify.py`

---

## CHECK 1 — MULTI-DAY RESOLVER CONSISTENCY — **PASS**

Pulled the **166 real #1 signal days** the live detector fires over the full 363-day SPY
5m history (2025-01-02 .. 2026-06-16), then called `live_order_params` on every signal day
× both accounts against the **real on-disk params.json** (not synthetic dicts).

| Account | Distinct resolutions | Result (× count) | Mismatches | Errors |
|---|---|---|---|---|
| **Safe-2** | **1** | `strike_offset=0 (ATM) / expiry_dte=1 / stop_dollars=35.88 / stop_pct=None / qty=3` ×166 | 0 | 0 |
| **Bold** | **1** | `strike_offset=-2 (ITM-2) / expiry_dte=1 / stop_dollars=67.68 / stop_pct=None / qty=3` ×166 | 0 | 0 |

Deterministic and correct on every signal day: exactly ONE resolution per account, byte-
matching the validated cell, zero None/error, both directions (C and P). The exactly-one-
stop invariant (`stop_dollars` set XOR `stop_pct` set) holds on every call.

Regression net green: `pytest test_engine_live_order_resolver_parity.py
test_engine_strike_parity.py test_vwap_continuation_watcher.py` → **121 passed**. Watcher
self-test → **ALL PASS** (10/10).

## CHECK 2 — 1DTE EOD-FLATTEN IN PRACTICE — **PASS**

Traced both flatten prompts against a simulated open 1DTE SPY position. The flatten is
expiry-agnostic by construction:

- **Step 1.5** (unconditional Alpaca cross-check) calls `get_all_positions` filtered to
  options with **no expiry-date filter** → a T+1 SPY option is seen and treated as source
  of truth → routes to Step 3.
- **Step 3** retry-until-zero loop reads `get_all_positions` and market-sells whatever
  option qty is open, up to 3 attempts, escalating to a kill-switch on residual qty.
- Scanned both `eod-flatten.md` and `aggressive/eod-flatten.md` for any expiry/same-day/
  0DTE position filter that could strand a 1DTE position overnight → **none found** (the
  only date references are the partial-fill root-cause note and the fill-reconciliation
  step, neither of which filters the position scan).

A 1DTE position opened today is flattened today at 15:55 exactly like a 0DTE one. It will
NOT be left open overnight — the load-bearing 1DTE safety property holds.

## CHECK 3 — NO-1DTE-LISTING FALLBACK — **PASS**

The resolver always states `expiry_dte=1` when the 1DTE flag is on; the fallback to 0DTE
is the heartbeat's job (heartbeat.md line 378: confirm a T+1 contract exists via
`get_option_contracts`; if none listed → build the 0DTE contract and log
`WP8_1DTE_UNAVAILABLE_FELL_BACK_0DTE`). Verified the resolver's `strike_offset` /
`stop_dollars` / `qty` are **expiry-independent**, so a 0DTE-fallback contract build reuses
them cleanly — the fallback path neither errors nor incorrectly skips the trade; it is a
clean contract-build swap that preserves the validated strike/stop/qty.

## CHECK 4 — PUT-VIX-GATE INTERACTION (the review's [MEDIUM]) — **BENIGN/CONSERVATIVE**

`j_vwap_cont_put_vix_gate=true` on Safe restricts PUT entries to as-of VIX 5-bar slope ≥ 0.
Quantified TWO ways:

- **Continuous-series harness (research detector):** 166 signals (90 C / 76 P) no-gate →
  165 (90 C / 75 P) gated. **1 put blocked (1.3%).** Calls untouched.
- **Faithful LIVE-watcher replay** (production `detect_vwap_continuation_setup`, per-session
  VIX reconstruction + 1-bar fallback — what actually runs Monday): 166 (90 C / 76 P) both
  gate ON and OFF. **0 puts blocked (0.0%).** Calls untouched.
- **First week** (first 5 signal days): 2 put entries with and without the gate — no
  early-week drought.
- **Full history:** the gate keeps 98.7%–100% of puts.

No put-entry drought. The gate is the *validated-stronger* cell (it lifts the put book in
the scorecard); any block is by-design conservatism, not a defect. The two methods bracket
the live effect: it ranges from 0 to 1 blocked put over 18 months — negligible.

## CHECK 5 — SIZING / RECENCY — **PASS**

`qty=3` (WP-3 cap-respecting base) on every signal day × both accounts. The resolver
contains **no scaling logic**: it returns `current_qty` verbatim (passing `current_qty=99`
returns 99), `WP3_BASE_QTY` default = 3. Recency-RED → no scaling is enforced upstream
(the resolver never sizes up; `risk_gate.check_order` remains the placement authority and
final veto). The deploy is base-size-only by construction.

---

## ISSUE FOUND (NOT a Monday must-fix) — Bold edge is inert by design

On the **Bold/aggressive** account the master switch `j_vwap_cont_enabled` is **ABSENT**
from `automation/state/aggressive/params.json` (the WP-5/WP-8 override flags ARE set, but
they are dormant because the edge cannot fire). The aggressive `heartbeat.md` also has **no
VWAP_CONTINUATION block at all** (it carries only VWAP_RECLAIM_FAILED_BREAK / edge #2).

This is **already documented and deliberate**, not a regression introduced by this deploy:
`automation/overnight/STATUS.md` records it at the deploy entry ("Bold ... flags armed but
INERT ... No Bold behavior change Monday"), in the deploy's "armed-but-inert by design"
note, and in the **Known broken** ledger (B1 finding, 2026-06-21) with the fix (add the
master key — a daylight live-path edit).

**Why it does NOT block MONDAY_READY:** because the Bold block never runs, there is **zero
mis-trade risk** on Bold Monday — it is silently inert, the fail-safe direction. The
deployment as scoped (Safe-2 live) is fully verified and clean. Bold activation is a
future, deliberate, J-aware step that requires TWO changes (not one):

1. Add `j_vwap_cont_enabled: true` (+ `j_vwap_cont_side`, optional `j_vwap_cont_put_vix_gate`)
   to `automation/state/aggressive/params.json`.
2. **Port the VWAP_CONTINUATION block (incl. the A5 callable invocation) into
   `automation/prompts/aggressive/heartbeat.md`** — without it, setting the param alone
   still won't fire the edge on Bold. (This is the under-documented half of the gap: the
   B1 note covers the missing key but not the missing heartbeat block.)

Both are daylight live-path edits gated behind J / OP-22, out of scope for a SAFE
read-only Sunday pass and carrying no Monday risk.

---

## VERDICT: **MONDAY_READY**

All five checks pass for the in-scope deployment (Safe-2 ATM / 1DTE / $35.88 / qty3, both
directions). The resolver is deterministic and correct across all 166 real signal days, the
1DTE EOD-flatten safety property holds, the holiday fallback is clean, the VIX put-gate is
benign (0–1 put blocked in 18 months), and sizing never scales. No mis-trade risk for the
live money-maker Monday. The one documented Bold gap is inert-by-design (no risk) and is a
future J-aware activation, not a pre-Monday fix.

**NEXT DIRECTION:** when J authorizes Bold activation (daylight), do it as a coupled
two-part edit — (1) Bold params master key + (2) port the VWAP_CONTINUATION + A5 block into
`automation/prompts/aggressive/heartbeat.md` — then re-run this harness against Bold for
the same 166-day determinism proof before flipping. (Pre-Monday, nothing else is needed.)
