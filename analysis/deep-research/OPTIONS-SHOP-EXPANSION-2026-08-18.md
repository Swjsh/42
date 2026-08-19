# OPTIONS-SHOP EXPANSION — deep research synthesis (2026-08-18, evening)

> **J's directive (2026-08-18 ~21:57 ET, verbatim in substance):** "We're gonna add a new sector
> to this project… trade the different weekly Friday expirations of other stocks, like Gold,
> Tesla, Nvidia, QQQ, Apple, Rivian… turn this from a 0DTE shop into a full-blown option shop…
> full brainstorm approach: how do we layer this in, what accounts, how/where do we document it,
> what are we wiring up exactly. Fill in the blanks and find the unknown unknowns."
>
> Method: 5 parallel Sonnet research agents (universe screen · sector heat · weekly-vs-0DTE
> mechanics · SPY-coupling repo audit · account layering) + Fable-tier synthesis + direct
> broker-rail probes (`get_option_chain` on the live Alpaca paper MCP, 2026-08-18). Every
> current-market claim is dated and was web- or broker-verified this session, not recalled.
> **Living doc this folds into:** `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md` (the program's
> canonical home going forward — read that, not this, for current state).

---

## Verdict up front

**GO — as edge-search, not as scaling.** Stand up ONE new paper arm (`weekly-1`, dedicated
Alpaca paper account, J provisions) trading a pilot basket of **GLD + QQQ weeklies first**
(NVDA joins after its 8/26 earnings; TSLA/AAPL wave 2; RIVN parked), long premium only,
level-interaction setups only, shadow-first before any paper order. The SPY 0DTE book keeps
running untouched — this is a new lane beside it, never mixed into it.

**The honest frame, stated first (anti-oversell):** the 2026-07-10 cross-ticker verdict
(`markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md`) said NO second chain until
(1) SPY book net-positive ≥20 days, (2) capacity-bound, (3) the setup shows edge on SPY first.
**None of those preconditions are met today** — `analysis/recommendations/live-readiness.json`
(2026-08-18) shows all 5 arms at WR 21.3–26.9% vs the 45% bar, expectancy −$2.15 to −$18.92/trade.
J's directive tonight explicitly supersedes that scope-lock, which is his call to make (the
July doc was doctrine-recorded, not one of the 10 rules). But the expansion thesis must
therefore be **"level trading may pay BETTER on slower-theta weekly surfaces than on 0DTE SPY"**
— a search for where the edge lives — not "replicate a working machine on more tickers."
The machine's framework is dialed in; its edge is not yet. Kill criteria are pre-registered
in the program doc so this lane can't quietly become sprawl.

Why the thesis is mechanistically plausible (not just hope): the engine's known edge is a
right tail — money comes only from exits ≥1.3× entry premium
(`memory: engine-edge-right-tail-2026-08-18`) — and 0DTE ATM theta (~100%/session) plus spread
noise is the harshest possible surface for letting a level thesis play out. A 3–5 DTE weekly
burns ~18–19%/day (broker-verified across all six names tonight) — the same level-rejection
entry gets days, not minutes, of survival. That is a real mechanical difference, and it is
exactly J's native style (supply/demand zones + structure shift, swing-paced).

---

## Finding 1 — the universe (broker-verified + web-verified, 2026-08-18)

Expiration cadence was established by querying the live Alpaca chain contract-by-contract —
several web sources are wrong about it.

**Cadence ground truth:** true DAILY expiries: SPY, QQQ, IWM, **GLD, XLF, SMH** (the last three
are unpublicized — nobody's marketing copy flags GLD as daily). Mon/Wed/Fri: NVDA, AAPL, TSLA,
MSFT, AMZN, GOOGL, AMD, AVGO, META, SLV, TLT, XLE, MU. Wed/Fri oddball: USO. Friday-only: DIA,
GDX, XBI, RIVN, PLTR, COIN, MSTR, HOOD, SOFI, NIO.

**Tiers (ATM weekly, closing quotes 2026-08-18 — spreads are directional, closing prints run wide):**

| Tier | Names | Note |
|---|---|---|
| **1 — trade-ready** | QQQ, IWM, GLD, NVDA, AAPL, TSLA, MSFT, AMZN, GOOGL, AMD, AVGO | NVDA tightest of all 30 screened (2.15% ATM spread, OI to 94,924); AMD/AVGO premium-expensive at $5K ATM |
| **2 — spread discipline required** | XLF, SMH, SLV, TLT, XLE, USO, META, MU, PLTR, SOFI, HOOD, COIN, MSTR, RIVN, GDX | PLTR the sleeper: 1.1% spread, 12–14K OI despite Friday-only |
| **3 — avoid** | XBI (96% ATM spread — placeholder quotes), NIO (sub-nickel premium, tick = 50%+ of value), DIA (QQQ/IWM beat it on every axis) | |

**J's six, verdicts:** GLD ★ biggest positive surprise (daily expiries, 2.7% spread, no
earnings, diversifies off tech beta — but note: GLD ETF options, NOT GC futures options).
QQQ ★ (daily, 1.1% spread on my close probe, the July doc's designated exception). NVDA ★
best liquidity in the screen but **earnings Wed 8/26 AMC — the exchange doesn't even list that
Wednesday's expiry** (verified absent from the chain). TSLA fine (3.8% spread; 3 ATM contracts
$1,569 ≈ the $1,580 Safe cap — use OTM-1). AAPL fine (8% closing spread but 35K OI; verify
intraday). **RIVN honest no for now:** Friday-only + $0.17–0.19 ATM premium where the $0.02
spread = 11–19% — our own sub-$0.20 noise-floor lesson (`project_noise_floor_entry_exit_matrix`)
says %-stops just read spread there; sizing to cap needs ~75 contracts, breaking the 3-lot
formula.

**Affordability at ~$5K/30% cap ($1,580):** 3 ATM contracts — NVDA $837 ✅, GLD $891 ✅,
AAPL $969 ✅, TSLA $1,569 ⚠️edge, QQQ $1,632 ⚠️ (OTM-1 fits). Broker-probed directly.

**Theta ground truth (my probe, all six names, 3DTE ATM):** −18 to −19%/day uniformly. This is
the number weekly exit rules must be built around.

## Finding 2 — the game changes in 4 structural ways (mechanics agent)

1. **Decay regime:** 5–7DTE theta ≈ 2–3× the 30DTE rate — steep but survivable; 0DTE is a
   cliff (>50% extrinsic gone in ~2h). Convention: buy 0.40–0.70Δ; for genuinely multi-day
   intent buy **next-week Friday**, reserve same-week for 1–2 session holds. "Weekly Friday
   expirations" per J = both, selected by intended hold, min DTE at entry ≥3.
2. **Earnings IV crush is a new failure class SPY never had:** IV peaks day-before, collapses
   20–60% post-print — right direction can still lose money (MIT working paper: retail
   documented losing to crush, not direction). Hard gate required: earnings blackout + IV-rank
   check (favor IVR 0–30 for long premium).
3. **Overnight gaps break the chart stop structurally** — it is inert while the market is
   closed. SPY gaps ~0.5% avg; single names ~2× that; binary events 5–10%+. Convention:
   overnight holds at 25–50% of intraday size; reduce into close; defined-risk through events.
   v1 answer: overnight-hold sizing multiplier 0.5 + weekend holds banned + earnings blackout.
4. **Structures:** long premium stays default (exit_manager understands it); debit spreads are
   the correct tool for event windows/wide spreads but the exit manager can't price spread P&L
   — **deferred to v2** rather than shipping two unknowns at once. Consequence accepted: v1
   simply never holds through earnings.

Full 10-row rule-delta table: folded into `WEEKLY-OPTIONS-PROGRAM.md` §4.

## Finding 3 — the stack is half-ready (coupling audit, file:line in program doc)

- **Already symbol-generic (proven by the crypto twin importing them verbatim):**
  `exit_manager.py` (all %-of-premium), `strategies.py`, `risk_gate.py`, `fleet_executor.py`,
  most of `fleet_broker.py`. The ACT lane is nearly drop-in.
- **The one dangerous hardcode:** `fleet_broker.py`'s `is_flat_spy_options` /
  `close_all_spy_options` + **4 duplicate `.startswith("SPY")` sites** (`atomic_bracket_guard.py`,
  `entry_location_shadow.py`, `fast_path_executor.py`, `trade_today_watcher.py`) — a non-SPY
  position on a core account is invisible to the flat-check and EOD-flatten (automated,
  permanent C11). This alone forces the dedicated-account answer. `atomic_bracket_guard.py:84`
  additionally indexes `symbol[9]` assuming a 3-char root — silently wrong for TSLA/NVDA/AAPL.
- **Genuinely absent logic:** expiry selection. `heartbeat_core.py:2445` sets
  `expiry = _et_now()` — 0DTE by construction, no "which Friday" concept exists. New module,
  not a parameter.
- **Do NOT reuse `heartbeat_core`'s SEE/DECIDE** — SPY-entangled throughout (the crypto twin's
  own docstring reached the same conclusion independently). New thin `weekly_core` instead.
- **State schema is symbol-less:** `key-levels.json`/`today-bias.json` have no symbol field;
  decision rows hardcode field name `"spy"` (read by ~503 files). Weekly lane gets its own
  per-symbol state files (`automation/state/weekly/…`); the 503-file rename is NOT attempted.
- **Zero backtestable history** for any new symbol (spy_5m + OPRA caches are SPY-only by
  construction) — the pilot starts as a live-paper mechanism trial, crypto-twin rules: its
  P&L is mechanism evidence, never edge evidence, until real fills accumulate.

## Finding 4 — where it trades (account layering)

**ONE new dedicated Alpaca paper account → new fleet arm `weekly-1`, basket-scoped.**
- vs reusing a failing SPY arm: destroys that arm's evidence trail (the 07-11 repoint scar),
  and "free capacity" is an artifact of one correlated signal failing, not spare slots.
- vs trading on core accounts: the flat-check blindness above + kill-switch coupling +
  per-account P&L attribution pollution (J's 2026-08-09 correction).
- vs one-account-per-sector: "fragment before evidence" — the exact pattern
  `ONE-ACCOUNT-TRANSITION-2026-08-18.md` is correcting on the SPY side. Split per-underlying
  only after the basket clears the fleet's own `promotion_gate` (n≥30 clean, OOS+, WF≥0.70…).
- Verified: multiple paper accounts per login work (we run 3 per login today); paper
  auto-grants options Level 3; no symbol exclusions found for the basket.
- Precedent followed: the crypto twin (dedicated account, dedicated code path, explicit
  non-comparability doctrine, own state dir, graduation bar frozen before evidence).

## Finding 5 — sector heat, now and recurring (sector agent)

- **Now (2026-08-18):** 🔥 XLE +9.9%/1M (oil ~$85, Iran/Hormuz), XLV +6.6%/1M and 3M leader
  +16.5%, XLK +5.6% but rolling over (chips shed >$1T late July; SMH −4.1% on 8/18).
  🥶 XLU −2.1%, XLRE −1.3%, XLC −5.6%/3M. Macro: 30-yr yield ~5.3% (2-decade high) is THE
  cross-asset story; VIX ~15.8 off a 2026 low; Sept-16 FOMC ~69% hold. Gold +18–21%/1M (GDX)
  before a −3.2% yield-spike day.
- **Recurring structure worth encoding:** earnings cluster weeks (late Jan/Apr/Jul/Oct — but
  semis run offset fiscal years: NVDA 8/26, MRVL 8/27, AVGO 9/2); September weakness is REAL
  but trend-conditional (above 200dma: +1.3% avg / 60% win; below: −4.2% / 15%) — the one
  seasonal worth a gate; energy crack-spread seasonality is mechanistic; "sell in May" and
  gold-September folklore: do not build on (sources contradict).
- **Instrument to build:** nightly $0 pure-Python sector-heat scanner — 15 ETFs, RS-vs-SPY +
  simplified RRG quadrant + MA-stack + breadth + dollar-volume proxy → composite rank → top-3
  sectors → their liquid top-10 holdings ranked. Output `analysis/sector-heat/{date}.json`.
  **Selection layer only — never an entry signal.** Spec folded into the program doc §6.

---

## The decisions (ranked, with kills)

1. **Pilot = GLD + QQQ** (daily expiries, tightest economics, zero earnings risk, one
   non-tech). NVDA enters post-8/26. TSLA/AAPL wave 2. **Killed for v1:** RIVN (noise floor),
   XBI/NIO/DIA (tier 3), MSTR/COIN-class names (crypto-beta + Friday-only — revisit only via
   scanner evidence).
2. **v1 trade shape:** long calls/puts only · 0.40–0.70Δ · min DTE ≥3 at entry (this-Friday
   only for Mon–Tue entries; else next-Friday) · level-interaction setups only (FOCUS-DOCTRINE
   scope holds — same edge thesis, new surface) · earnings blackout (no entry ≤3 sessions
   before that name's print; no holding through any print) · IV-rank note logged per entry ·
   overnight holds sized ×0.5 · **no weekend holds in v1** (close by Fri 15:30 ET) ·
   chart-structure stop during RTH + −50% catastrophe premium cap · TP1/runner/trail shapes
   inherited then re-fit on real fills.
3. **Engine = new thin `weekly_core`** (levels from per-symbol daily/4h/1h zones +
   `market_structure.py` which is already symbol-agnostic) → existing fleet ACT lane
   (`fleet_executor`→`fleet_broker`→`exit_manager`) with the SPY-prefix hardcodes generalized
   (4+4 sites) + a new expiry-selector module + per-symbol state under
   `automation/state/weekly/`. `heartbeat_core.py` untouched.
4. **Shadow-first (OP-11):** the signal engine runs WATCH-only writing a shadow ledger of
   would-be entries/exits BEFORE any paper order — this starts before the account even exists.
   Paper orders begin only after the shadow ledger shows the mechanism firing sanely
   (prereg in the program doc).
5. **Account = `weekly-1`**, J provisions (4 steps, ~5 min: pick login → Open New Paper
   Account $5K → confirm Level 3 → key into gitignored `secrets.json`). Everything else is
   autonomous.

**Program kill criteria (pre-registered, program doc §8):** shadow phase produces <10 valid
signals in 20 sessions (setup doesn't occur) → kill; after ≥30 real-fills trades the basket
underperforms the concurrent SPY book on expectancy → kill and fold lessons; any C11-class
position-visibility incident → halt lane until root-caused. Sector-scanner dies if its top-3
picks show no lift over an equal-weight null after 60 sessions.

## Cost (OP-3 gate)

$0 recurring: Alpaca paper + free data + pure-Python scanner. Build labor = Sonnet-tier.
No new vendors, no new keys beyond J's own paper-account key.

---

*Agent reports (session scratchpad, folded here + into the program doc; scratchpad is
ephemeral by design): universe-screen, sector-heat, weekly-mechanics, spy-coupling-audit,
account-layering. Broker probes: live `mcp__alpaca__get_option_chain`/`get_stock_snapshot`,
2026-08-18 ~21:00 ET. Prior art: CROSS-TICKER-BRAINSTORM-2026-07-10 (superseded in part by
J's directive tonight — banner added), FOCUS-DOCTRINE (scope survives: levels-first),
ROADMAP.md (expansion registered as PROPOSED).*
