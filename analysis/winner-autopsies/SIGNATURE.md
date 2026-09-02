# Winner signature — what does our money actually look like?

_Generated 2026-09-01 20:22:29 ET · real-fills journal · $0 (pure Python) · `setup/scripts/winner_signature.py`._

> **DESCRIPTIVE ONLY — this file ratifies nothing.** Read the three disclosures in the module docstring before quoting any number: (1) arms are not independent, the honest denominator is WAVES not trades; (2) hold-time and exit-multiple are OUTCOMES, never entry filters; (3) day realized range is LOOK-AHEAD and unusable as a gate.

## The population

- **521 real fills** across 6 arms and 49 sessions (2026-04-29 → 2026-09-01).
- Collapsed to **130 independent impulse waves** (>15 min gap = new wave). **This is the honest denominator.**
- Engine decision context recovered for **98%** of fills (the shortfall is fills predating `core-decisions.jsonl`; they stay in P&L, drop out of context buckets).
- **Trade level:** 178 winners / 343 losers · WR **34.2%** · net **$3,027**.
- **Wave level:** WR **28%** — three of every four impulses we commit to lose money.

### ⚠ ERA SPLIT — this population is not one engine (2026-08-11 boundary)

On **2026-08-10** ribbon_ride shipped `pre_tp1_ladder`, a stop RATCHET that locks the runner stop at entry×1.30 once MFE clears +50%. On the pain ledger's real-OPRA MFE/MAE over the full population: **before** the ship, 19 of 45 positions that reached ≥+50% favorable still closed at or below entry, giving back **$2,549**; **after**, 14 of 14 closed green and worst-case heat fell from −46%/−72% MAE to −4%/−15%. Pooling across that is describing an engine we no longer run — and would keep nominating exit fixes for a leak that is already closed.

| era | sessions | fills | waves | trade WR | wave WR | net | $/session | ex-best-2-days net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pre-ladder (≤2026-08-10) | 34 | 312 | 80 | 26% | 22% | $144 | $4 | $-4,980 |
| post-ladder (≥2026-08-11) | 15 | 209 | 50 | 46% | 38% | $2,883 | $192 | $-762 |

**Read this honestly in both directions.** The ratchet did what it was built to do — the give-back leak is measurably closed. It DID make the book positive: the post-ladder era is net **+$2,883**, though ex its best 2 days that becomes **$-762** — this many sessions concentrated in a couple of days is not yet evidence of a broad edge, only that the ratchet stopped actively bleeding. That concentration is what `day-throttle-forward-prereg-2026-08-18` measures — and the post-ladder era is far too few sessions to conclude anything from on its own.

> **Consequence for every section below:** they are still pooled across both eras, because splitting them would leave cell sizes that cannot support any read at all. Treat the EXIT-shaped findings as describing the pre-ladder engine, and the ENTRY/REGIME-shaped findings as the ones that survive the boundary.

- Winners **$25,217** (avg $142, median $109, max $1,500).
- Losers **$-22,190** (avg $-65, median $-35, worst $-770).
  - top 5 winners = $3,709 (**15%** of all winner dollars)
  - top 10 winners = $5,615 (**22%** of all winner dollars)
  - top 20 winners = $8,804 (**35%** of all winner dollars)
  - top 30 winners = $11,370 (**45%** of all winner dollars)

## 1. The shape of the money (outcome anatomy — descriptive, NOT a filter)

| exit ÷ entry premium | n | total $ |
|---|---:|---:|
| ≥2.0× | 42 | $7,711 |
| 1.3–2.0× | 95 | $15,863 |
| 1.0–1.3× | 63 | $1,643 |
| 0.7–1.0× | 224 | $-10,507 |
| <0.7× | 97 | $-11,683 |

**Practically all of it comes from exits at ≥1.3× entry** — 137 fills, 26% of the book, $23,574.

> The claim is NOT the tautology that winners won. It is that **a small win is worth almost nothing here**: the 1.0–1.3× band is 63 fills for $1,643 — 7% of what the runner bands carry — against a loss book of $-22,190. Scalping this system toward a higher win rate would buy more of the band that does not pay. The right tail IS the business.

**The 2× club — 42 fills (8% of the book) carrying $7,711.** Median hold **47 min**, median entry premium **$0.84**, concentrated on **13 sessions**. That is the edge in one line: a near-the-money contract given room to run through a real impulse.

**The bleed dies small, not catastrophically:** median losing exit is **0.81×** entry (≈-19%), nowhere near the −50% catastrophe cap. The book is not killed by disasters — it is nibbled to death by a high count of small, fast invalidations.

## 2. Ex-ante buckets (wave level = the honest denominator)

_A finding only counts if it holds at wave level AND is knowable BEFORE the entry._

**Entry premium (ex-ante — the strike we chose)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `$1.00–2.00` | 42 | 36% | $5,763 | $137 |
| `$0.30–0.60` | 32 | 38% | $570 | $18 |
| `$0.60–1.00` | 35 | 29% | $-386 | $-11 |
| `<$0.30` | 19 | 0% | $-787 | $-41 |

**Hour of entry (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `10:xx` | 17 | 29% | $3,700 | $218 |
| `14:xx` | 23 | 30% | $2,042 | $89 |
| `13:xx` | 27 | 37% | $-36 | $-1 |
| `09:xx` | 22 | 27% | $-661 | $-30 |
| `11:xx` | 20 | 20% | $-719 | $-36 |
| `12:xx` | 20 | 25% | $-1,215 | $-61 |

**Setup (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | 56 | 30% | $4,502 | $80 |
| `BEARISH_REJECTION_RIDE_THE_RIBBON` | 47 | 32% | $821 | $17 |
| `bollinger_squeeze` | 8 | 25% | $-299 | $-37 |
| `VWAP_CONTINUATION` | 6 | 33% | $-622 | $-104 |

**Side (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `C` | 66 | 30% | $4,895 | $74 |
| `P` | 64 | 27% | $-1,868 | $-29 |

**VIX at entry (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `14–16` | 64 | 33% | $2,863 | $45 |
| `18+` | 16 | 31% | $-371 | $-23 |
| `16–18` | 41 | 17% | $-1,012 | $-25 |

**Trigger set (ex-ante)**

| bucket | waves | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `confluence,level_reclaim` | 47 | 32% | $4,092 | $87 |
| `trendline_rejection` | 36 | 31% | $1,465 | $41 |
| `none` | 38 | 26% | $-408 | $-11 |

> ⚠ **Ribbon width (`spread_cents`) is a TRAP — logged so the next session does not re-discover and ship it.** Filtering out width ≥40¢ turns the whole book positive, which is why it looks irresistible; it also removes ~81% of the population and kills 18 of the top-25 winners. It is a trend-EXTENSION measure, not a bid-ask spread. That is survivorship, not edge.

## 3. Regime — the strongest signal in the data, and it is LOOK-AHEAD

**Realized day range vs day P&L** (⚠ range is known only at the CLOSE):

| realized range | days | fills | total $ | $/day | green days |
|---|---:|---:|---:|---:|---:|
| <0.5% | 10 | 104 | $-4,514 | $-451 | 2/10 |
| 0.5–0.8% | 16 | 179 | $3,072 | $192 | 9/16 |
| 0.8–1.2% | 15 | 143 | $-610 | $-41 | 4/15 |
| 1.2%+ | 7 | 91 | $5,001 | $714 | 5/7 |

**Every pre-open proxy for that range fails.**

| ex-ante candidate | r vs realized range | r vs day P&L |
|---|---:|---:|
| ATR14 prior % | +0.24 | -0.21 |
| VIX open | +0.42 | -0.07 |
| abs(gap %) | +0.15 | -0.17 |
| _realized range (POST-HOC, unusable)_ | — | **+0.34** |

**Conclusion: the day cannot be pre-selected.** The regime that decides our P&L is invisible before the open, so the lever cannot be a pre-open gate — it has to be an intraday feedback loop.

**Day archetype (post-hoc taxonomy)**

| bucket | days | win% | total $ | avg $ |
|---|---:|---:|---:|---:|
| `gap-go` | 15 | 40% | $3,857 | $257 |
| `range-chop` | 19 | 58% | $2,902 | $153 |
| `V-reversal` | 3 | 33% | $-453 | $-151 |
| `pin-day` | 3 | 0% | $-1,451 | $-484 |
| `gap-fade` | 5 | 0% | $-3,329 | $-666 |

## 4. The feedback signal the engine does not currently use

- **first wave LOST** (33 sessions): everything traded AFTER it — 203 fills — came to **$-2,070** ($-63/session, 5/33 sessions green).
- **first wave WON** (16 sessions): everything traded AFTER it — 86 fills — came to **$2,213** ($138/session, 4/16 sessions green).

**Per-arm intraday stop — counterfactual.** Halt an arm for the day once its own REALIZED P&L (only trades already exited at the moment of the next entry — no look-ahead) crosses a threshold:

| arm-day stop | fills kept | fills skipped | book total |
|---|---:|---:|---:|
| −$50 | 346 | 175 | $5,194 |
| −$75 | 385 | 136 | $5,742 |
| −$100 | 418 | 103 | $5,514 |
| −$150 | 448 | 73 | $5,578 |
| −$200 | 474 | 47 | $4,244 |
| −$300 | 504 | 17 | $5,134 |
| −$400 | 512 | 9 | $4,628 |
| **none (what we actually did)** | 521 | 0 | $3,027 |

> **Every threshold beats no-stop.** Monotonicity across a wide knob range is why this deserves a pre-registration rather than a knob-fit — but read §5 before believing the SIZE of it.

**Why the existing Rule-5 kill switch never engages:** over 143 arm-days the loss distribution runs worst **$-1,458**, p10 **$-305**, median **$-42**. Rule 5 halts Safe at −30% of start-of-day equity (≈−$1,400 at current size) — roughly **4× wider than the 10th-percentile bad day**. In practice the engine runs with no daily throttle at all.

## 5. Concentration disclosure (why nothing here is ratified)

- The book-level −$400 day-stop moves **6 of 49 sessions**; the top 3 carry $2,721 of a $2,966 total delta.
- Sessions moved: `2026-08-07` $+2,059, `2026-08-05` $+1,225, `2026-08-11` $-563, `2026-08-21` $-358, `2026-08-12` $+335, `2026-08-14` $+268.
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
| 2026-08-28 | safe-3 | C | 10 | $1.84 | $3.77 | 2.05× | 2 | 32m | **$386** | 0.91% | range-chop |
| 2026-08-04 | risky-3 | C | 12 | $1.32 | $2.60 | 1.97× | 3 | 40m | **$384** | 1.69% | gap-go |
| 2026-08-04 | risky-3 | C | 09 | $1.40 | $1.99 | 1.42× | 6 | 7m | **$354** | 1.69% | gap-go |
| 2026-07-02 | risky-3 | P | 11 | $0.49 | $1.36 | 2.78× | 4 | 69m | **$348** | 1.51% | range-chop |
| 2026-08-04 | risky-1 | C | 09 | $1.39 | $4.87 | 3.50× | 1 | 95m | **$348** | 1.69% | gap-go |
| 2026-08-28 | safe | C | 10 | $1.74 | $3.46 | 1.99× | 2 | 32m | **$344** | 0.91% | range-chop |
| 2026-08-28 | risky-1 | C | 10 | $1.85 | $3.57 | 1.93× | 2 | 47m | **$344** | 0.91% | range-chop |
| 2026-04-29 | safe | P | 10 | $1.67 | $2.24 | 1.34× | 6 | 131m | **$342** | 0.53% | range-chop |
| 2026-08-28 | risky-1 | C | 10 | $1.85 | $2.87 | 1.55× | 3 | 23m | **$306** | 0.91% | range-chop |
| 2026-08-13 | bold | C | 09 | $1.01 | $1.99 | 1.97× | 3 | 21m | **$294** | 0.68% | gap-go |
| 2026-08-04 | risky-1 | C | 09 | $1.39 | $2.12 | 1.53× | 4 | 16m | **$292** | 1.69% | gap-go |
| 2026-08-06 | safe | P | 10 | $1.28 | $2.71 | 2.12× | 2 | 104m | **$286** | 0.57% | range-chop |
| 2026-08-27 | safe-3 | C | 09 | $1.65 | $2.60 | 1.58× | 3 | 82m | **$285** | 0.68% | gap-go |

