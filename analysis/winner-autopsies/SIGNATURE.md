# Winner signature — what does our money actually look like?

_Generated 2026-08-18 08:47:33 ET · real-fills journal · $0 (pure Python) · `setup/scripts/winner_signature.py`._

> **DESCRIPTIVE ONLY — this file ratifies nothing.** Read the three disclosures in the module docstring before quoting any number: (1) arms are not independent, the honest denominator is WAVES not trades; (2) hold-time and exit-multiple are OUTCOMES, never entry filters; (3) day realized range is LOOK-AHEAD and unusable as a gate.

## The population

- **424 real fills** across 6 arms and 39 sessions (2026-04-29 → 2026-08-17).
- Collapsed to **102 independent impulse waves** (>15 min gap = new wave). **This is the honest denominator.**
- Engine decision context recovered for **98%** of fills (the shortfall is fills predating `core-decisions.jsonl`; they stay in P&L, drop out of context buckets).
- **Trade level:** 127 winners / 297 losers · WR **30.0%** · net **$-668**.
- **Wave level:** WR **24%** — three of every four impulses we commit to lose money.

### ⚠ ERA SPLIT — this population is not one engine (2026-08-11 boundary)

On **2026-08-10** ribbon_ride shipped `pre_tp1_ladder`, a stop RATCHET that locks the runner stop at entry×1.30 once MFE clears +50%. On the pain ledger's real-OPRA MFE/MAE over the full population: **before** the ship, 19 of 45 positions that reached ≥+50% favorable still closed at or below entry, giving back **$2,549**; **after**, 14 of 14 closed green and worst-case heat fell from −46%/−72% MAE to −4%/−15%. Pooling across that is describing an engine we no longer run — and would keep nominating exit fixes for a leak that is already closed.

| era | sessions | fills | waves | trade WR | wave WR | net | $/session |
|---|---:|---:|---:|---:|---:|---:|---:|
| pre-ladder (≤2026-08-10) | 34 | 312 | 80 | 26% | 22% | $144 | $4 |
| post-ladder (≥2026-08-11) | 5 | 112 | 22 | 41% | 27% | $-812 | $-162 |

**Read this honestly in both directions.** The ratchet did what it was built to do — the give-back leak is measurably closed. It did NOT make the book positive: the post-ladder era is still red, and its losses now sit almost entirely in sub-1.0× exits, i.e. trades that never worked at all rather than winners handed back. That is the absorption problem, which is what `day-throttle-forward-prereg-2026-08-18` measures — and the post-ladder era is far too few sessions to conclude anything from on its own.

> **Consequence for every section below:** they are still pooled across both eras, because splitting them would leave cell sizes that cannot support any read at all. Treat the EXIT-shaped findings as describing the pre-ladder engine, and the ENTRY/REGIME-shaped findings as the ones that survive the boundary.

- Winners **$17,967** (avg $141, median $97, max $1,500).
- Losers **$-18,635** (avg $-63, median $-30, worst $-770).
  - top 5 winners = $3,709 (**21%** of all winner dollars)
  - top 10 winners = $5,577 (**31%** of all winner dollars)
  - top 20 winners = $8,458 (**47%** of all winner dollars)
  - top 30 winners = $10,701 (**60%** of all winner dollars)

## 1. The shape of the money (outcome anatomy — descriptive, NOT a filter)

| exit ÷ entry premium | n | total $ |
|---|---:|---:|
| ≥2.0× | 35 | $6,184 |
| 1.3–2.0× | 61 | $10,883 |
| 1.0–1.3× | 50 | $900 |
| 0.7–1.0× | 192 | $-8,720 |
| <0.7× | 86 | $-9,915 |

**Practically all of it comes from exits at ≥1.3× entry** — 96 fills, 23% of the book, $17,067.

> The claim is NOT the tautology that winners won. It is that **a small win is worth almost nothing here**: the 1.0–1.3× band is 50 fills for $900 — 5% of what the runner bands carry — against a loss book of $-18,635. Scalping this system toward a higher win rate would buy more of the band that does not pay. The right tail IS the business.

**The 2× club — 35 fills (8% of the book) carrying $6,184.** Median hold **43 min**, median entry premium **$0.84**, concentrated on **10 sessions**. That is the edge in one line: a near-the-money contract given room to run through a real impulse.

**The bleed dies small, not catastrophically:** median losing exit is **0.82×** entry (≈-18%), nowhere near the −50% catastrophe cap. The book is not killed by disasters — it is nibbled to death by a high count of small, fast invalidations.

## 2. Ex-ante buckets (wave level = the honest denominator)

_A finding only counts if it holds at wave level AND is knowable BEFORE the entry._

**Entry premium (ex-ante — the strike we chose)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `$1.00–2.00` | 32 | 28% | $2,011 | $63 |
| `$0.60–1.00` | 25 | 28% | $346 | $14 |
| `$0.30–0.60` | 24 | 33% | $-105 | $-4 |
| `<$0.30` | 19 | 0% | $-787 | $-41 |

**Hour of entry (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `10:xx` | 13 | 31% | $2,025 | $156 |
| `14:xx` | 18 | 22% | $1,689 | $94 |
| `13:xx` | 20 | 35% | $279 | $14 |
| `12:xx` | 15 | 20% | $-1,054 | $-70 |
| `09:xx` | 20 | 25% | $-1,150 | $-58 |
| `11:xx` | 15 | 7% | $-2,373 | $-158 |

**Setup (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `BEARISH_REJECTION_RIDE_THE_RIBBON` | 37 | 27% | $870 | $24 |
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | 42 | 21% | $605 | $14 |
| `bollinger_squeeze` | 6 | 33% | $-227 | $-38 |
| `VWAP_CONTINUATION` | 6 | 33% | $-622 | $-104 |

**Side (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `C` | 51 | 24% | $1,052 | $21 |
| `P` | 51 | 24% | $-1,720 | $-34 |

**VIX at entry (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `18+` | 16 | 31% | $-371 | $-23 |
| `14–16` | 39 | 23% | $-781 | $-20 |
| `16–18` | 38 | 16% | $-1,063 | $-28 |

**Trigger set (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `trendline_rejection` | 26 | 23% | $1,514 | $58 |
| `confluence,level_reclaim` | 34 | 21% | $-108 | $-3 |
| `none` | 34 | 29% | $-255 | $-8 |

> ⚠ **Ribbon width (`spread_cents`) is a TRAP — logged so the next session does not re-discover and ship it.** Filtering out width ≥40¢ turns the whole book positive, which is why it looks irresistible; it also removes ~81% of the population and kills 18 of the top-25 winners. It is a trend-EXTENSION measure, not a bid-ask spread. That is survivorship, not edge.

## 3. Regime — the strongest signal in the data, and it is LOOK-AHEAD

**Realized day range vs day P&L** (⚠ range is known only at the CLOSE):

| realized range | days | fills | total $ | $/day | green days |
|---|---:|---:|---:|---:|---:|
| <0.5% | 5 | 74 | $-3,853 | $-771 | 0/5 |
| 0.5–0.8% | 13 | 132 | $98 | $8 | 6/13 |
| 0.8–1.2% | 14 | 127 | $-1,914 | $-137 | 3/14 |
| 1.2%+ | 7 | 91 | $5,001 | $714 | 5/7 |

**Every pre-open proxy for that range fails.**

| ex-ante candidate | r vs realized range | r vs day P&L |
|---|---:|---:|
| ATR14 prior % | +0.06 | -0.11 |
| VIX open | +0.34 | +0.03 |
| abs(gap %) | +0.14 | -0.15 |
| _realized range (POST-HOC, unusable)_ | — | **+0.41** |

**Conclusion: the day cannot be pre-selected.** The regime that decides our P&L is invisible before the open, so the lever cannot be a pre-open gate — it has to be an intraday feedback loop.

**Day archetype (post-hoc taxonomy)**

| bucket | days | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `range-chop` | 15 | 53% | $1,350 | $90 |
| `gap-go` | 12 | 25% | $987 | $82 |
| `V-reversal` | 3 | 33% | $-453 | $-151 |
| `pin-day` | 2 | 0% | $-866 | $-433 |
| `gap-fade` | 4 | 0% | $-3,109 | $-777 |

## 4. The feedback signal the engine does not currently use

- **first wave LOST** (28 sessions): everything traded AFTER it — 165 fills — came to **$-3,338** ($-119/session, 3/28 sessions green).
- **first wave WON** (11 sessions): everything traded AFTER it — 68 fills — came to **$2,269** ($206/session, 3/11 sessions green).

**Per-arm intraday stop — counterfactual.** Halt an arm for the day once its own REALIZED P&L (only trades already exited at the moment of the next entry — no look-ahead) crosses a threshold:

| arm-day stop | fills kept | fills skipped | book total |
|---|---:|---:|---:|
| −$50 | 273 | 151 | $1,763 |
| −$75 | 304 | 120 | $2,140 |
| −$100 | 335 | 89 | $2,117 |
| −$150 | 361 | 63 | $1,709 |
| −$200 | 383 | 41 | $708 |
| −$300 | 409 | 15 | $1,339 |
| −$400 | 415 | 9 | $933 |
| **none (what we actually did)** | 424 | 0 | $-668 |

> **Every threshold beats no-stop.** Monotonicity across a wide knob range is why this deserves a pre-registration rather than a knob-fit — but read §5 before believing the SIZE of it.

**Why the existing Rule-5 kill switch never engages:** over 111 arm-days the loss distribution runs worst **$-1,458**, p10 **$-339**, median **$-48**. Rule 5 halts Safe at −30% of start-of-day equity (≈−$1,400 at current size) — roughly **4× wider than the 10th-percentile bad day**. In practice the engine runs with no daily throttle at all.

## 5. Concentration disclosure (why nothing here is ratified)

- The book-level −$400 day-stop moves **5 of 39 sessions**; the top 3 carry $2,721 of a $3,324 total delta.
- Sessions moved: `2026-08-07` $+2,059, `2026-08-05` $+1,225, `2026-08-11` $-563, `2026-08-12` $+335, `2026-08-14` $+268.
- **Effective n is a handful of sessions, not 424 fills.** Any live change built on this needs its own forward pre-registration. This report is the hypothesis generator, not the evidence.

## 6. The top 20 winners, in full

| date | arm | side | hr | entry | exit | × | qty | hold | $ | day range | archetype |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2026-05-14 | safe | C | 09 | $1.67 | $3.17 | 1.90× | 10 | 119m | **$1,500** | 0.80% | range-chop |
| 2026-05-04 | safe | P | 10 | $0.85 | $1.58 | 1.86× | 10 | 50m | **$730** | 0.99% | range-chop |
| 2026-08-06 | risky-3 | P | 10 | $1.28 | $2.49 | 1.95× | 5 | 92m | **$605** | 0.57% | range-chop |
| 2026-05-01 | safe | P | 13 | $0.33 | $0.56 | 1.72× | 20 | 98m | **$470** | 0.61% | inverted-V |
| 2026-08-04 | risky-3 | C | 12 | $1.32 | $3.34 | 2.53× | 2 | 83m | **$404** | 1.69% | gap-go |
| 2026-08-04 | risky-1 | C | 12 | $1.33 | $3.29 | 2.47× | 2 | 83m | **$392** | 1.69% | gap-go |
| 2026-08-04 | bold | C | 09 | $1.38 | $2.68 | 1.94× | 3 | 19m | **$390** | 1.69% | gap-go |
| 2026-08-04 | risky-3 | C | 12 | $1.32 | $2.60 | 1.97× | 3 | 40m | **$384** | 1.69% | gap-go |
| 2026-08-04 | risky-3 | C | 09 | $1.40 | $1.99 | 1.42× | 6 | 7m | **$354** | 1.69% | gap-go |
| 2026-07-02 | risky-3 | P | 11 | $0.49 | $1.36 | 2.78× | 4 | 69m | **$348** | 1.51% | range-chop |
| 2026-08-04 | risky-1 | C | 09 | $1.39 | $4.87 | 3.50× | 1 | 95m | **$348** | 1.69% | gap-go |
| 2026-04-29 | safe | P | 10 | $1.67 | $2.24 | 1.34× | 6 | 131m | **$342** | 0.53% | range-chop |
| 2026-08-13 | bold | C | 09 | $1.01 | $1.99 | 1.97× | 3 | 21m | **$294** | 0.68% | gap-go |
| 2026-08-04 | risky-1 | C | 09 | $1.39 | $2.12 | 1.53× | 4 | 16m | **$292** | 1.69% | gap-go |
| 2026-08-06 | safe | P | 10 | $1.28 | $2.71 | 2.12× | 2 | 104m | **$286** | 0.57% | range-chop |
| 2026-08-05 | risky-1 | P | 11 | $1.69 | $2.62 | 1.55× | 3 | 21m | **$279** | 0.95% | gap-fade |
| 2026-08-04 | safe | C | 09 | $1.35 | $2.70 | 2.00× | 2 | 19m | **$270** | 1.69% | gap-go |
| 2026-08-04 | safe-3 | C | 09 | $1.38 | $2.68 | 1.94× | 2 | 18m | **$260** | 1.69% | gap-go |
| 2026-08-04 | safe-3 | C | 12 | $1.33 | $2.61 | 1.96× | 2 | 40m | **$256** | 1.69% | gap-go |
| 2026-08-04 | safe | C | 12 | $1.34 | $2.61 | 1.95× | 2 | 39m | **$254** | 1.69% | gap-go |

