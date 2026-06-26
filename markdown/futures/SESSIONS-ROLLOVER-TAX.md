# Sessions, Rollover & Tax — Futures

> Sources: CME Group (hours, expiration), tastytrade (hours), NinjaTrader/Aeromir (rollover), Schwab/Green Trader Tax (Section 1256). See [SOURCES.md](SOURCES.md).

---

## 1. Trading hours & sessions

Equity index futures (ES, MES, NQ, MNQ) share **identical CME Globex hours**:

| | Central Time | Eastern Time |
|---|---|---|
| **Weekly open** | Sunday 5:00 p.m. CT | Sunday 6:00 p.m. ET |
| **Weekly close** | Friday 4:00 p.m. CT | Friday 5:00 p.m. ET |
| **Daily maintenance break** | 4:00–5:00 p.m. CT (Mon–Thu) | 5:00–6:00 p.m. ET |
| **Daily settlement** | 4:00 p.m. CT | 5:00 p.m. ET |

- **~23 hours/day** of trading. During the **1-hour maintenance break** no orders execute on any CME product — used for settlement processing and rolling to the next trading day.
- **RTH (Regular Trading Hours)** = the cash-equity session **09:30–16:00 ET** (08:30–15:00 CT). This is the high-volume, high-information window.
- **Globex/overnight** = everything else (the other ~17 hours). Lower volume, gap risk, but still liquid for micros.

**Our engine trades the RTH window (09:30–16:00 ET)** — that's what the v3 backtest validated. We do not currently trade the overnight session (no validated edge there yet).

**Holidays:** market closes for major US holidays (New Year's, Presidents' Day, Good Friday, Memorial Day, Independence Day, Labor Day, Thanksgiving, Christmas); some are half-days. The heartbeat's `Test-HolidayFromAlpaca` gate covers RTH holiday detection.

---

## 2. Contract rollover & expiration

### The quarterly cycle
Equity index futures expire **4× a year**: **3rd Friday of March, June, September, December.** Month codes (CME standard):

| Month | Code | | Month | Code |
|---|---|---|---|---|
| March | **H** | | September | **U** |
| June | **M** | | December | **Z** |

So `MNQM6` = MNQ June 2026, `MNQU6` = MNQ September 2026. (Full code set: F G H J K M N Q U V X Z = Jan–Dec.)

### Rollover mechanics
- Trading **terminates** on the expiration day; contracts **cash-settle** to the spot index (no delivery, **no assignment**).
- **Liquidity migrates to the next month ~8 days before expiry** — the **second Thursday before the 3rd Friday is "Rollover Thursday."** Volume + open interest jump to the back month then.
- **To roll:** close the expiring month and open the same position in the next month — ideally as a **calendar spread order** (sell front / buy back simultaneously) to eliminate leg risk.

### What this means for our engine
- The continuous chart symbol `MNQ1!` / `MES1!` **auto-rolls** to the front month, so chart reads are always on the active contract.
- The **broker** (Tastytrade) holds the specific dated contract. Near expiry, ensure orders route to the active month. In paper/sandbox + intraday-only, roll risk is minimal (we never hold through expiry), but a **rollover-week awareness flag** in premarket is a good future addition: around Rollover Thursday, the front-month volume/levels shift.
- **Action item (logged):** add a rollover-week check to `futures-premarket.md` so the engine notes when the front month is about to change.

---

## 3. Tax — Section 1256 (60/40) — a structural edge

> Paper now, but this is real money advantage when live. **Not tax advice — confirm with a CPA.**

Futures are **Section 1256 contracts**, which get uniquely favorable treatment:

### 60/40 rule
- **60%** of gains taxed at **long-term** capital-gains rates, **40%** at **short-term** — **regardless of actual holding period**, even on a trade held for 3 minutes.
- At the top 2026 bracket the **blended rate ≈ 26.8%** vs **37%** ordinary — roughly **10 points lower** than short-term-only treatment that equities/equity-options day trades get.

### Mark-to-market at year-end
- All **open** Section 1256 positions are **deemed sold at fair market value on Dec 31**, gain/loss recognized that year. New basis = year-end price.

### Wash-sale exemption
- The **wash-sale rule does NOT apply** to Section 1256 contracts. Losses are usable without the 30-day repurchase trap that hits stocks/options.

### Reporting
- Reported on **Form 6781** → flows to Schedule D. Brokers issue a 1099-B with aggregate 1256 gain/loss.

**Why it matters for the dual-account experiment:** an identical-edge strategy nets **more after tax** in futures than in equity options, because of 60/40 + no wash-sale. Factor this into any future "which instrument compounds better" comparison.

---

## 4. Costs (commissions & fees)

Per micro contract, **per side** (round trip = 2×), typical retail:
- **Commission:** broker-set, often **~$0.25–$1.50** per micro per side (Tastytrade micro futures are on the low end).
- **Exchange + clearing + NFA fees:** small per-contract amounts (cents to ~$0.40), bundled by the broker.
- **All-in micro round-trip:** typically **~$1–$3**. Small but **not zero** — at 1/10 micro size, fees are a larger % of P&L than on E-minis, so over-trading micros bleeds via fees. The engine's throttle + signal-quality gates protect against this.

> Confirm exact Tastytrade micro futures commissions on the live account before going live — fees compound on a small account.
