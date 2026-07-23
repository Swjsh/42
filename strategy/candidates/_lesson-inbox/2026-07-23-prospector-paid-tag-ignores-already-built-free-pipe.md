# Lesson inbox — prospector "Cost: paid" tag ignores already-built free data pipes

**Filed by:** conductor (AFTERHOURS), 2026-07-23 ~07:xx ET, during a chef-inbox 15-item backlog triage.

## Symptom
3 of 15 open chef-inbox prospector items (Put/Call Ratio, IV Skew 10Δ/25Δ, Max Pain) were
tagged `Cost: paid` (CBOE Live API / OptionMetrics / Bloomberg B-PIPE / CBOE DataShop) as if a
new paid vendor were required to test the idea. A 4th (CBOE Dealer Gamma Exposure) was tagged
`Cost: paid` for a signal that is **already built and accruing for free**
(`backtest/lib/engine/gex_regime.py` + `backtest/tools/cboe_oi_bank.py`, free CBOE CDN,
24 sessions accrued as of this fire).

## Root cause
The prospector agent (`Gamma_Prospector`) surfaces ideas from general market-structure
knowledge (what indicator/data-point WOULD help) without cross-checking against this repo's
OWN already-wired data pipes before tagging cost. Two independent misses stack: (1) it
doesn't know `gex_regime.py`/`cboe_oi_bank.py` already compute dealer gamma for $0, so it
re-proposes the paid-vendor version of a solved problem; (2) it doesn't know
`fleet_broker.get_option_greeks` (automation/state/fleet/fleet_broker.py:139) already pulls
free per-contract greeks+IV from Alpaca's `/v1beta1/options/snapshots` endpoint for every live
entry (G8, log-only) — a signal that plausibly extends to put/call volume ratio, IV skew, and
max-pain (OI) with zero new vendor, just a fuller pull across the chain instead of one symbol.

## Fix (this fire)
Manually re-tagged the 4 items during triage: CLOSED the GEX-duplicate outright (already
built); REFRAMED the other 3 (put/call ratio, IV skew, max pain) as "likely free via existing
Alpaca options-snapshots pipe, downgrade the paid-vendor framing" rather than closing them —
the underlying idea is fine, only the cost tag was wrong.

## Generalizable guardrail (for lesson-author to graduate)
Before `Gamma_Prospector` (or any chef-inbox author) tags an idea `Cost: paid`, it should
grep the repo for an existing free pipe that already produces the same DATA CLASS (options
greeks/IV/OI via `fleet_broker.get_option_greeks`, GEX via `gex_regime.py`/`cboe_oi_bank.py`,
SPY price via the SIP 5m cache + Alpaca broker feed) before assuming a vendor license is
required. A cheap version of this check: maintain a short "already-free" registry (data class
→ existing free source file) that any cost-tagging step consults first. Doesn't need to be
perfect — even a 4-entry lookup (options greeks/IV, options OI, GEX/dealer-gamma, SPY price)
would have caught 4/4 of these misses.

## Scope / revert
Pure doc/triage — no code touched by this lesson filing itself (the chef-inbox file edits
that motivated it are their own disposition, already applied). depends:none
