# SIZING-CEILING RECONCILIATION — the 6% ceiling vs min-3 on $2K (the practical blocker)

> **Item 2 of the profitability campaign / master-plan row B6.** Resolves the doctrine
> contradiction the D1/B1-feasibility batch surfaced: the sizing-study's **6% premium ceiling
> FORBIDS the structurally-required min-3** on SPY 0DTE — which **blocks trading any validated
> edge on the $2K Safe account.**
>
> **Status: ANALYSIS + PROPOSE-ONLY. Risk doctrine is J's call. NOTHING live changed.**
> Real OPRA fills / real chain prices. Built by `backtest/autoresearch/sizing_ceiling_reconciliation.py`.
> Scorecard: [`analysis/recommendations/sizing-ceiling-reconciliation.json`](../analysis/recommendations/sizing-ceiling-reconciliation.json).
> Window: 2025-01-02 .. 2026-05-29 (351 trading days, bounded by real OPRA coverage).

---

## TL;DR

1. **The contradiction is real and it blocks $2K trading.** Min-3 SPY 0DTE puts cost **$216–$423
   median** at real OPRA prices (ATM = $423 = **21% of $2K**; SPY traded a median of **$653**).
   The sizing-study's **6% ceiling ($120) fits 0% of days at ATM, 2% at OTM-1, 14% even at OTM-2.**
   You literally cannot put on the mandatory 3 contracts under a 6% gross-premium cap.

2. **The 6% ceiling is an SPX-OTM3 artifact.** It was derived for J's **cheap $0.30–0.50 OTM-3**
   contracts (mean premium $1.94, half-Kelly 3.9% of equity → min-3 at $0.40 = $120 = 6%). It is a
   **$-RISK budget disguised as a gross-premium %** for a 40-cent contract. It does not translate to
   ATM/ITM options on a **$600 underlying**.

3. **The fix (proposed, needs J's risk sign-off):** drop the 6% gross-premium ceiling for SPY 0DTE
   and bind per-trade size with **(a) the EXISTING Rule-6 notional cap (Safe 30% = $600)** plus
   **(b) a $-at-risk-to-the-chart-stop half-Kelly check (~4% ≈ $78)**. ATM min-3 fits the Rule-6 cap
   on **80% of days**, OTM-1 on **93%**, OTM-2 on **98%** — so the edge becomes tradeable on $2K
   without breaking any real risk rail. **Feasible-optimal strike = ATM, OTM-1 fallback on
   high-premium opens** (matches the D1/B1 finding).

---

## 1. THE CONTRADICTION — real min-3 cost vs the ceilings

Real OPRA 0DTE SPY **put** entry premiums (next-bar-open ASK = `bar.open + $0.02`, identical to the
live `simulator_real` fill), at the **09:35 ET entry** on every cached trading day. Exact strike, no
nearest-strike fallback (true moneyness cost). **SPY median over the window = $653** (range $499–$757).

| Strike | n days | Real premium (median / p10 / p90) | **Min-3 cost (median)** | **% of $2K** | Fits **6% ceiling** ($120) | Fits **Rule-6 30%** ($600) | Fits **live 40%** ($800) |
|---|---|---|---|---|---|---|---|
| **ATM** | 303 | $1.41 / 0.93 / 2.30 | **$423** | **21%** | **0%** | **80%** | 96% |
| **OTM-1** | 302 | $1.00 / 0.57 / 1.87 | **$302** | **15%** | **2%** | **93%** | 98% |
| **OTM-2** | 280 | $0.72 / 0.43 / 1.30 | **$216** | **11%** | **14%** | **98%** | 100% |

### The headline

**Min-3 SPY 0DTE puts cost $216–$423 (median) = 11–21% of a $2K account, because SPY is a ~$653
underlying.** The doctrinal **6% premium ceiling ($120) implies max ~$0.40/contract for min-3 —
unreachable at any strike with a validated edge** (only deep-OTM lottery tickets cost that little,
and those have no validated gap-and-go / everyday-book edge). **On $2K the 6% ceiling and the min-3
floor are mutually incompatible.**

> The earlier B1-feasibility block reported ATM min-3 = $683 (34%); that figure was on **gap-down
> signal days only** (elevated open IV). This block prices **every day** — the typical-day cost is
> lower ($423/21% ATM) but the conclusion is identical and now distribution-robust: **6% never fits.**

### Two ceilings exist and they disagree

- **6% = the SIZING-STUDY *recommendation*** ([`markdown/research/SIZING-STUDY-2026-06-19.md`](../markdown/research/SIZING-STUDY-2026-06-19.md))
  — prudent in spirit, but explicitly derived for J's **cheap OTM-3** style ($0.30–0.50, mean $1.94)
  and tabled only those premiums. **NOT ratified into params.**
- **40% = what `params.json` `v15_max_premium_pct_of_account[$0-2K]` actually enforces TODAY** ($800).
  The binding real-world gate, deliberately loose at the $0-2K tier.

---

## 2. WHY 6% doesn't translate — it's a $-risk budget, not a premium budget

The sizing-study's own math (its §4–§5):

- Half-Kelly on J's realized-payoff basis = **3.9% of equity ≈ $78** of **$-at-risk**.
- 3 contracts at OTM-3 **$0.40** = **$120** gross = 6% of $2K. The "6%" is just *"min-3 of a 40-cent
  contract"* — a number that only equals half-Kelly **because the contract is cheap and the loss was
  assumed to be ~the whole premium.**

That assumption breaks twice on SPY 0DTE:

1. **The contract isn't cheap.** ATM on a $653 underlying is ~$1.41, not $0.40 — 3.5× the premium the
   6% rule was built around. Same *number of contracts*, 3.5× the *gross premium %*.
2. **The loss isn't the whole premium.** The LIVE exit is **chart-stop-primary** (premium stop demoted
   to a **−50% catastrophe cap**; chart/ribbon/profit-lock are primary). The realistic loss is
   **premium × stop-distance**, not 100% of premium.

So the prudent quantity to bound is **$-at-risk-to-the-stop**, not gross premium:

| Measure (ATM min-3, median) | Value | % of $2K |
|---|---|---|
| **Gross premium (notional deployed)** | $423 | 21% |
| **$-at-risk to a ~30% chart/ribbon stop** | ~$127 | ~6% |
| **$-at-risk to the −50% catastrophe cap (worst case)** | ~$212 | ~11% |
| Rule-6 per-trade cap | $600 | 30% |
| −30% daily kill-switch | $600 | 30% |
| Half-Kelly ($-at-risk budget) | ~$78 | 3.9% |

The punchline: **ATM min-3's gross premium is 21% of $2K, but its actual loss exposure to the live
chart stop is ~$127 (≈6%) and the catastrophe-capped worst case is ~$212 (≈11%) — both comfortably
inside the −30% kill-switch and the Rule-6 30% per-trade cap.** The gross premium is the *notional
deployed*, not the *risk*. The 6%-on-premium rule confuses the two.

---

## 3. THE RECONCILED RULE (proposed — needs J's risk-doctrine sign-off)

Replace the single **6% gross-premium ceiling** for SPY 0DTE with a **two-part** rule:

### Part 1 — notional cap = the EXISTING Rule 6 (don't invent a new ceiling)
> Per-trade gross premium (min-3 cost) **≤ Rule-6 per-trade cap (Safe 30% of equity = $600)**.

This is already doctrine (Rule 6). It is the correct binding gate. **Fit rates:** ATM min-3 fits on
**80%** of days, OTM-1 **93%**, OTM-2 **98%**. The live params `$0-2K` tier is **40%** — *looser* than
Rule 6; **tighten it to 30% to MATCH Rule 6** (removes the 40%-vs-30% inconsistency, and 40% is the
number that "forces OTM bias" from an era when SPY math was different).

### Part 2 — $-at-risk cap = restore the sizing-study's *actual* intent
> Per-trade **$-at-risk-to-the-chart-stop ≤ half-Kelly band (~4% of equity ≈ $78)**, where
> `$-at-risk = min3_gross_cost × stop_distance_fraction`.

This keeps the prudent-risk spirit of the 6% number **without** the OTM-3-specific gross-premium proxy.
ATM min-3's $-at-risk to the chart stop (~$127) sits a bit above strict half-Kelly ($78) — so either
**accept it as the structural floor** (min-3 is mandatory for 2-TP + 1-runner) **or step out to OTM-1/2**
to pull both gross and $-at-risk down (OTM-2 min-3 $-at-risk ≈ $65, *below* half-Kelly).

### Feasible-optimal strike on $2K
- **Primary: ATM** — best verified edge on the days it fits, already the LIVE strike with a filed
  all-gates-pass scorecard, fits Rule-6 on 80% of days.
- **Fallback: OTM-1** on high-premium (high-IV) opens where ATM min-3 would breach the cap (fits 93%).
- **Do NOT blanket-use ITM-1** — its +42% edge is real but it busts the ceiling on >half the days;
  **reserve ITM-1 for the $10k+ tier** (matches the per-tier strike ladder and the D1/B1 verdict).

### J's core insight is preserved
L168 (the 1-2-lot lesson) was about **ADDING / scaling-UP and post-loss revenge-sizing**, NOT the
base trade. min-3 as a **flat, atomic, chart-stopped bracket** is structurally different from J's
discretionary scaled-in 3-lots. Keep **min-3 + the no-add rule (Rule 4) + the post-loss throttle
design**; bound the *base-trade notional* by Rule 6, not by a 6%-premium proxy.

---

## 4. >>> J DECISION REQUIRED (risk doctrine) <<<

This is a **risk-rule change** — explicitly J's call, not auto-shippable. The proposal:

1. **DROP the 6% gross-premium ceiling for SPY 0DTE.** It is an SPX-OTM3 artifact, infeasible on a
   $600+ underlying (fits 0% of days at ATM).
2. **Bind per-trade size by the EXISTING Rule-6 30% notional cap + a $-at-risk-to-stop half-Kelly check.**
3. **Tighten the live params `$0-2K` tier 40% → 30%** to match Rule 6 (consistency).
4. **Trade ATM on $2K** (OTM-1 fallback on high-IV opens); reserve ITM-1 for $10k+.

**If J declines** and keeps a hard 6% premium ceiling: then **no validated edge is tradeable on the
$2K Safe account** (min-3 can't fit), and the honest consequence is the Safe account cannot trade the
book until it grows — the contradiction would resolve as "don't trade $2K," not "trade it smaller."

Nothing is changed in `params.json`, `risk_gate.py`, or either heartbeat. This is the propose step.

---

## Reproduce / files

- Script: `backtest/autoresearch/sizing_ceiling_reconciliation.py` (`backtest/.venv/Scripts/python.exe …`)
- Scorecard JSON: `analysis/recommendations/sizing-ceiling-reconciliation.json`
- Source docs: `markdown/research/SIZING-STUDY-2026-06-19.md` (the 6% derivation),
  `docs/J-DAILY-TRADING-BOOK.md` (B1 feasibility), `automation/state/params.json` (live rails)
- Master-plan row: **B6** in `docs/J-DATA-RESEARCH-MASTER-PLAN.md`

**Caveats:** (1) real-OPRA cache ends ~2026-05-29. (2) Exact-strike pricing drops a few cache-missing
days per strike. (3) Premiums are the 09:35 ET open fill (intraday rejection entries vary). (4) The
$-at-risk uses a ~30% premium-move proxy for the chart/ribbon stop distance (the −50% cap is worst
case). (5) **Propose-only — risk doctrine is J's sign-off.**
