# J-Grounded Setup Specs — Automation Definitions Parameterized From His Winners

> **Status: SPEC (propose-only, Rule 9).** These are automation-ready *definitions*,
> not wired code. No heartbeat, params, `j_edge_tracker`, or `regime_book` behavior is
> changed. Each spec slots into `regime_book.REGIME_SETUP_MAP` as a `WATCH_ONLY`
> `SetupSlot`; promotion to `REGIME_ACTIVE` requires the gates in
> [`markdown/0dte/J-EDGE-GROUND-TRUTH.md`](J-EDGE-GROUND-TRUTH.md) §4-5. Authored 2026-06-19.
>
> **Every parameter below is DERIVED from J's actual winning trades** in
> `analysis/webull-j-trades/winner_setups.json` (look-ahead-free features at his entry
> bar) + the style tables in [`markdown/0dte/J-WEBULL-EDGE-2021-2023.md`](J-WEBULL-EDGE-2021-2023.md).
> Where a value is an *observed envelope* from a small n, it is flagged as such — these
> are J's observed values, **not** values optimized on 2025-26 SPY (the era gap;
> `J-EDGE-GROUND-TRUTH.md` §3). They are the **starting envelope for in-era
> re-validation**, per Tier 2.

---

## 0. The mapping at a glance (his winning archetype → automated setup)

J's 9 feature-tagged top winners collapse into **4 archetypes**. Each maps to an
existing `regime_book` setup slot and a regime cell. This is the "his winning archetype
X → automated setup Y, parameters from his data" payoff:

| J's winning archetype | n (bull/bear) | → Automated setup (regime_book slot) | → Regime cell | Tier-1 gateable? |
|---|---|---|---|---|
| **pullback-continuation** (`*_pullback_resumption`) | 2 (1/1) | **`VWAP_TREND_PULLBACK`** (H4 — already in book) | `BULL_TREND` (bull-side) + `BEAR_TREND` (bear-side) | bear-side ✅ / bull-side ❌ |
| **trend-continuation** (`trend_continuation_midrange`) | 3 (2/1) | **`VWAP_TREND_PULLBACK`** (same slot, midrange variant) | `BULL_TREND` + `BEAR_TREND` | bear-side ✅ / bull-side ❌ |
| **momentum-breakout** (`momentum_breakout_continuation`) | 2 (1/1) | **`GAP_AND_GO`** (H2b — already in book) | `BULL_TREND` + `BEAR_TREND` | bear-side ✅ / bull-side ❌ |
| **reversal-off-extreme** (`bearish_reversal_off_high`) | 2 (0/2) | **`BEARISH_REJECTION_RIDE_THE_RIBBON`** (the confirmed edge) + `BULLISH_RECLAIM` (mirror, bull) | `BEAR_TREND` / `HIGH_VOL` (fade) | ✅ (bearish) |

**Two of J's four archetypes map onto setups ALREADY in `regime_book`**
(`VWAP_TREND_PULLBACK`, `GAP_AND_GO` — the two DSR-PASS discovery survivors), and the
other two map onto the confirmed bearish edge + its bull mirror. **No new setup string
is invented** — J's winners *corroborate and parameterize* setups the book already
carries as `WATCH_ONLY`. That is the strongest possible outcome: his real edge and the
data-discovered edge **point at the same setups**.

**Cross-cutting parameters (apply to ALL specs, from J's style tables):**

| Parameter | Value (from J's data) | Source |
|---|---|---|
| **Sizing** | **1-2 lots** (his +$4,576 profitable band; 3+ lots = −$17,461). Min-3 floor in `risk_gate` is a *separate* per-trade-cap concern — see note ‡. | `J-WEBULL` sizing table, L168 |
| **VWAP alignment** | **Mandatory.** All 7 trend/continuation/breakout winners entered on the correct VWAP side for direction; the 2 reversals deliberately faded from the wrong side. | `winner_setups.json#vwap_side` |
| **Time-of-day weight** | Prefer **11:00 / 13:00 / 14:30 ET** (positive expectancy); de-weight the 09:30-10:30 open and 11:30/12:30/13:30/15:30 dead zones. | `J-WEBULL` time-of-day table |
| **Hold ceiling** | Winners cut fast (median 15.3 min). A **time-stop well inside the session** matches his winning behavior; do not let a thesis-failed trade run (his loser leak). | `J-WEBULL` hold table |
| **Direction** | Two-sided, but **calls held up better** for J (−$6/trade vs −$33 puts). Engine's *proven* edge is bearish; bull specs need J's own 2026 SPY bull winners before going active. | `J-WEBULL` call/put table |

> ‡ **Sizing reconciliation.** L168 finds J's edge lives in 1-2 lots and dies at 3+.
> The current `risk_gate.MIN_CONTRACTS ≥ 3` (2 TP + 1 runner) is a *structural* floor
> for the TP/runner split, **not** a contradiction — the L168 finding is about *scaling
> up after losses / into adverse excursion*, which `risk_gate` does **not** yet throttle
> (L168 code-gap note). These specs adopt J's 1-2 *lot intent* as the **base sizing
> tier** (`SetupSlot.sizing_tier="base"`, an advisory hint); the actual contract count
> and the post-loss-add throttle remain `risk_gate`'s authority and a **separate
> propose-only proposal** (do not wire here).

---

## 1. SPEC — `VWAP_TREND_PULLBACK` (J archetypes: pullback-continuation + trend-continuation)

**Provenance (J's winners that define this spec):**

| Date | Bias | Entry ET | Hold | VWAP side | Prior-30m | New extreme? | Retrace frac | P&L | Sub-archetype |
|---|---|---|---|---|---|---|---|---|---|
| 2023-06-01 | bull | 10:31 | 16m | above | +0.19% | no | 0.64 | +$525 | pullback-resumption |
| 2022-06-06 | bear | 11:11 | 7m | below | −0.41% | no | 0.75 | +$445 | pullback-resumption |
| 2023-06-02 | bull | 10:10 | 52m | above | −0.04% | no | 0.71 | +$450 | trend-continuation |
| 2023-05-30 | bear | 10:57 | 24m | below | −0.10% | no | 0.81 | +$390 | trend-continuation |
| 2022-07-27 | bull | 14:21 | 14m | above | +0.13% | no | 0.74 | +$390 | trend-continuation |

**n=5 (3 bull / 2 bear). Total +$2,200. This is J's single most-represented family.**

**The structure (what every one of these has in common):**
- Price is on the **correct side of session VWAP** for the trade direction (above→calls,
  below→puts) — **100% of the 5**.
- **NOT a new session extreme** (`new_session_extreme=False` on all 5) — J joins a trend
  on a *pullback/retrace*, he does not chase the high/low.
- **Retrace fraction 0.64-0.81** — price pulled back into but not through the prior
  swing (a shallow-to-medium retrace, then resumed). This is the defining feature: a
  pullback *toward* VWAP/prior structure that holds, then resumes the trend.
- Prior-30m drift is **mild** (−0.41% to +0.19%) — these are *orderly* trends, not
  parabolic ones.

### Automation spec

```
SETUP_ID:        VWAP_TREND_PULLBACK            (regime_book slot, status=WATCH_ONLY)
REGIME (Layer1): BULL_TREND  → call side        (ribbon BULL, VIX not rising, not compressed)
                 BEAR_TREND  → put  side        (ribbon BEAR, VIX not falling)
DIRECTION:       trade WITH the regime/ribbon (continuation, never counter-trend here)

ENTRY CONDITIONS (all must hold at the trigger bar, look-ahead-free):
  1. Session VWAP side matches direction:  close > VWAP for calls / close < VWAP for puts.
  2. Ribbon stack matches direction (BULL for calls, BEAR for puts)  [= the regime gate].
  3. Price has PULLED BACK toward VWAP/prior swing and is RESUMING:
       retrace_frac of the last swing in [0.50, 0.90]  (J's observed 0.64-0.81, widened
       modestly for the envelope), AND the current bar closes back in the trend direction.
  4. NOT a fresh session extreme on the entry bar  (new_session_extreme == False).
  5. Prior-30m drift is in the trend direction OR mild-against (|drift| <= ~0.50%) —
       i.e. an orderly trend, not exhaustion.

TRIGGER (the bar that fires the order):  the pullback bar's high (calls) / low (puts)
  is reclaimed by the next bar's price crossing it — i.e. the resumption is CONFIRMED,
  not anticipated (Rule 2). For Gamma-Bold, live bid crossing the reclaim level
  (feedback_aggressive_live_trigger); for Gamma-Safe, closed-bar confirmation.

TIME WINDOW:     prefer 10:00-14:30 ET; weight UP 11:00 / 13:00 / 14:30; AVOID the
                 11:30 / 12:30 / 13:30 dead zones and the 15:00+ close (J's time table).
                 (J's 5 entries: 10:10-14:21 — all inside this window.)

SIZING:          base tier = 1-2 lots intent (sizing_tier="base"); risk_gate owns count.

EXIT:
  - Time-stop: hard cut well inside the session (J winners median hold ~15-24 min for
    this family; ceiling ~52 min observed). Default to the engine's existing exit
    geometry (chart-stop-primary per 2026-06-18) for the in-era re-validation; J's hold
    profile says do NOT let it run past the session-time stop.
  - TP1 at the next structural level OR the engine's premium fallback; runner with a
    breakeven move (existing v15 management).
  - Chart/ribbon stop primary; premium stop is the −50% catastrophe cap (L168 / C1).

REGIME CELL MAPPING:
  regime_book.REGIME_SETUP_MAP[Regime.BULL_TREND]  → VWAP_TREND_PULLBACK  (call side)  ✅ already present
  regime_book.REGIME_SETUP_MAP[Regime.BEAR_TREND]  → VWAP_TREND_PULLBACK  (put  side)  ✅ already present

GATING (per J-EDGE-GROUND-TRUTH §4):
  - bear-side: Tier-1 edge_capture applies (3 anchors are bearish) + §6.1 bars 1-3,5.
  - bull-side: Tier-1 CANNOT gate (no bull anchor); needs in-era re-validation + J's
    own logged 2026 SPY bull winners before REGIME_ACTIVE.
```

**Why this slot:** `VWAP_TREND_PULLBACK` (H4) is already the strongest data-discovered
survivor in the book (DSR PASS, OOS sign-stable, both directions positive,
`regime_book.py` BULL_TREND/BEAR_TREND cells). **J's 5 winners are independent
real-fills corroboration of the exact same structure** — a pullback to VWAP in the
trend direction. The spec tightens the discovery setup's definition with J's observed
features (the `new_session_extreme==False` + retrace-band conditions).

---

## 2. SPEC — `GAP_AND_GO` (J archetype: momentum-breakout)

**Provenance (J's winners that define this spec):**

| Date | Bias | Entry ET | Hold | VWAP side | Prior-30m | New extreme? | Retrace frac | P&L |
|---|---|---|---|---|---|---|---|---|
| 2022-05-02 | bull | 10:25 | 6m | above | +0.45% | **yes** | 1.20 | +$460 |
| 2022-07-22 | bear | 13:18 | 17m | below | −0.43% | **yes** | 1.08 | +$400 |

**n=2 (1 bull / 1 bear). Total +$860. low_power — do not over-read (C24).**

**The structure (what distinguishes this from the pullback family):**
- **New session extreme = True** on both — this is the *opposite* of the pullback
  family. Here J is joining a **breakout to a fresh high/low**.
- **Retrace frac > 1.0** (1.08, 1.20) — price pushed *beyond* the prior swing extreme
  (a breakout/extension, not a retrace).
- **Stronger prior-30m drift** (+0.45% / −0.43%) — momentum is already running.
- VWAP-aligned (above→call, below→put), short holds (6-17 min — fast momentum capture).

### Automation spec

```
SETUP_ID:        GAP_AND_GO                     (regime_book slot, status=WATCH_ONLY)
REGIME (Layer1): BULL_TREND → call side / BEAR_TREND → put side
DIRECTION:       WITH the breakout (momentum continuation)

ENTRY CONDITIONS (all at trigger bar, look-ahead-free):
  1. VWAP side matches direction (close > VWAP calls / < VWAP puts).
  2. Ribbon stack matches direction  [= regime gate].
  3. FRESH session extreme made on/just before the entry bar (new_session_extreme==True)
     OR an opening-gap continuation (H2b — the original GAP_AND_GO definition: opening
     gap + a confirming first bar in the gap direction).
  4. Momentum present: prior-30m drift in trend direction, magnitude >= ~0.30%
     (J's observed 0.43-0.45%).
  5. Extension confirmed: price trades THROUGH the prior swing extreme (retrace_frac > 1.0),
     not merely tagging it.

TRIGGER:  the prior session extreme (or opening-gap edge) is broken by price crossing it,
  confirmed on close (Safe) or live bid (Bold). Breakout is CONFIRMED, never anticipated.
  NOTE (C20): this is a BREAKOUT setup — any proximity/level gate must be oriented so it
  does NOT anti-correlate with a breakout (a "near a level" filter would suppress exactly
  the breaks this setup wants — proximity gates anti-correlate with breakout setups).

TIME WINDOW:     J's 2 entries 10:25 + 13:18 — both midday-ish; same time weighting as §1
                 (the H2b discovery variant is opening-gap, so the morning also applies
                 for the gap-continuation flavor).

SIZING:          base tier = 1-2 lots intent; risk_gate owns count.

EXIT:            fast — J held 6-17 min. Tight time-stop; TP1 at measured-move/next level;
                 chart/ribbon stop primary, −50% premium catastrophe cap.

REGIME CELL MAPPING:
  regime_book.REGIME_SETUP_MAP[Regime.BULL_TREND]  → GAP_AND_GO  (call side)  ✅ already present
  regime_book.REGIME_SETUP_MAP[Regime.BEAR_TREND]  → GAP_AND_GO  (put  side)  ✅ already present

GATING:  same as §1 (bear-side Tier-1 gateable; bull-side needs in-era + J bull winners).
         EXTRA caveat: n=2 from J — this archetype's J-provenance is low_power. The
         book slot's real strength is the H2b discovery eval (5/6 quarters positive,
         DSR PASS); J's 2 winners are corroboration, not the primary evidence.
```

**Why this slot:** `GAP_AND_GO` (H2b) is the *other* DSR-PASS discovery survivor —
opening-gap / breakout continuation. J's 2 momentum-breakout winners (fresh extreme +
extension + momentum) are the same structure. The `new_session_extreme==True` +
`retrace_frac>1.0` conditions are what separate this from `VWAP_TREND_PULLBACK` in
automation — **the discriminator is "fresh extreme / extension" (breakout) vs "not a new
extreme / shallow retrace" (pullback)**, which is theme C16 (multi-bar reversal vs
single-bar continuation discriminator) applied to J's data.

---

## 3. SPEC — reversal-off-extreme → `BEARISH_REJECTION_RIDE_THE_RIBBON` (+ bull mirror)

**Provenance (J's winners that define this spec):**

| Date | Bias | Entry ET | Hold | VWAP side | Prior-30m | New extreme? | Retrace frac | P&L |
|---|---|---|---|---|---|---|---|---|
| 2022-03-14 | bear | 11:20 | 23m | above (fade) | −0.09% | no | 0.38 | +$500 |
| 2022-05-12 | bear | 11:16 | 38m | above (fade) | +0.67% | no | 0.21 | +$390 |

**n=2, BOTH bear. Total +$890. This is the FADE play — J's only counter-VWAP winners.**

**The structure (deliberately the inverse of §1-2):**
- **Price is on the WRONG side of VWAP for the direction** — above VWAP, but J bought
  *puts* (fading the push above VWAP into a session high). This is the only family where
  VWAP-side is counter to direction, *by design*: it's a reversal, not a continuation.
- **Low retrace frac (0.21, 0.38)** — price had pushed up and J faded the *exhaustion*
  at/near the high (the opposite of the 0.64-0.81 pullback band and the >1.0 breakout band).
- Not a new extreme on the entry bar (the high was *just before*; J enters on the
  rejection/rollover).
- Entries clustered **11:16-11:20** — late-morning exhaustion fades.

### Automation spec

```
SETUP_ID:        BEARISH_REJECTION_RIDE_THE_RIBBON   (the CONFIRMED edge; WATCH_ONLY in book pending real-★★★ re-confirm)
                 + mirror: BULLISH_RECLAIM_RIDE_THE_RIBBON (bull fade-off-low; needs J bull winners)
REGIME (Layer1): BEAR_TREND (the rollover regime) and/or HIGH_VOL (exhaustion fades)
DIRECTION:       AGAINST the immediate push (reversal/fade) — but WITH the larger ribbon
                 once it flips. "Ride the ribbon" = fade the exhaustion, then ride the
                 new down-leg the ribbon confirms.

ENTRY CONDITIONS (at trigger bar, look-ahead-free):
  1. Price has pushed to / above session VWAP into a recent session HIGH (for puts) —
     i.e. the FADE side: vwap_side == "above" while taking PUTS (J's signature here).
  2. REJECTION confirmed: a rejection candle / lower-high / ribbon roll-over at the
     extreme (a named-level or trendline rejection — the playbook BEARISH_REJECTION
     trigger). This is the trigger, NOT mere proximity to the high (Rule 2).
  3. Low retrace_frac (<= ~0.45) — price faded from NEAR the extreme, not after a deep
     pullback (J's 0.21-0.38).
  4. Ribbon flip corroboration (the "ride the ribbon" leg): 5m ribbon rolling from
     BULL/MIXED toward BEAR confirms the reversal is taking hold.

TRIGGER:  the rejection level breaks downward (price crosses below the rejection
  candle's low / the reclaimed level fails), confirmed on close (Safe) / live bid (Bold).
  This is the SAME trigger family as J's 3 in-era OP-16 anchors (711.4 rejection +
  ribbon flip, trendline rejection, premarket level + trendline) — Tier 1 directly applies.

TIME WINDOW:     J's 2 fades 11:16-11:20; the broader engine edge fires across the session.
                 Same time weighting (favor 11:00/13:00/14:30).

SIZING:          base tier = 1-2 lots intent; risk_gate owns count.

EXIT:            J held 23-38 min (longer than continuation — a reversal needs room to
                 develop). Chart/ribbon stop primary; the chandelier profit-lock + runner
                 (existing v15) fits the "ride the new leg" intent.

REGIME CELL MAPPING:
  regime_book.REGIME_SETUP_MAP[Regime.BEAR_TREND] → BEARISH_REJECTION_RIDE_THE_RIBBON  ✅ already present (the J-anchored slot)
  regime_book.REGIME_SETUP_MAP[Regime.HIGH_VOL]   → (candidate cell for exhaustion fades — NOT in seed map; propose as future WATCH_ONLY)
  bull mirror → REGIME_SETUP_MAP[Regime.BULL_TREND] → BULLISH_RECLAIM_RIDE_THE_RIBBON  ✅ already present (WATCH_ONLY, needs J bull winners + low-VIX gate)

GATING:  This is the ONE archetype Tier-1 gates fully — J's 3 OP-16 anchors ARE this
  pattern (bearish rejection + ribbon flip). edge_capture applies directly. It is also
  the only setup with J's real *in-era* winners, so it is the closest to promotion —
  bar = re-confirm on real ★★★ levels + the accruing live archive (REGIME-AWARE-BOOK §6.1).
```

**Why this slot:** This archetype is the bridge between the two tiers. J's **2021-23
SPX fade winners** (Tier 2) and his **3 2026 SPY rejection anchors** (Tier 1) are the
*same structure* — fade/reject an extreme, confirm with a ribbon flip, ride the new leg.
`BEARISH_REJECTION_RIDE_THE_RIBBON` is the confirmed engine edge; J's data corroborates
it from both eras. The bull mirror (`BULLISH_RECLAIM`) is the reversal-off-*low* — J has
no bull fade winner in the top-10, so it stays the weakest-evidenced and needs his own
logged bull winners (consistent with `regime_book.py`'s BULLISH_RECLAIM note).

---

## 4. The discriminator table (how automation tells the archetypes apart)

The four archetypes are **mechanically separable** from features already computed each
bar — this is what makes them implementable as distinct setups rather than one fuzzy
"trend trade." The separating features, straight from J's winners:

| Feature | pullback-cont. | trend-cont. | momentum-breakout | reversal-off-extreme |
|---|---|---|---|---|
| **VWAP side vs direction** | WITH | WITH | WITH | **AGAINST (fade)** |
| **new_session_extreme** | False | False | **True** | False |
| **retrace_frac** | 0.64-0.75 | 0.71-0.81 | **>1.0 (extension)** | **0.21-0.38 (fade near top)** |
| **prior-30m drift** | mild w/ dir | ~flat | **strong w/ dir** | mixed |
| **→ setup** | VWAP_TREND_PULLBACK | VWAP_TREND_PULLBACK | GAP_AND_GO | BEARISH_REJECTION |
| **hold (J median)** | ~12 min | ~24 min | ~12 min | ~30 min |

- **WITH-VWAP + not-new-extreme + retrace 0.5-0.9** → `VWAP_TREND_PULLBACK` (pullback or
  midrange trend — same slot, the spec covers both).
- **WITH-VWAP + new-extreme + retrace>1.0 + strong drift** → `GAP_AND_GO`.
- **AGAINST-VWAP + low-retrace + rejection-at-extreme** → `BEARISH_REJECTION` (fade).

This collapses cleanly: **3 of 4 are WITH-trend (continuation/breakout) and route to the
two discovery survivors; 1 is the fade and routes to the confirmed bearish edge.** It is
the same continuation-vs-reversal discriminator theme C16 already names, now grounded in
J's real fills.

---

## 5. What is NOT claimed (honest boundaries — read with `J-EDGE-GROUND-TRUTH.md` §6)

- **Not wired.** These are `WATCH_ONLY` specs. `select_setups()` returns `()` for every
  regime today; nothing changes in the heartbeat, params, or order path (Rule 9).
- **Not optimized parameters.** Every number is J's *observed* value from a small n
  (2-5 per archetype), on **SPX 2021-23**, reconstructed via SPY-proxy 5m bars. They are
  the **starting envelope for in-era re-validation on 2025-26 real ★★★ levels**, not
  tuned thresholds. Widen/narrow only with in-era evidence (C24 — anchor winners can be
  one-off exceptions; verify the IS population WR before expanding).
- **Not a P&L claim.** No spec asserts "$X on 2025-26 SPY." That requires the §5
  in-era validation in `J-EDGE-GROUND-TRUTH.md`.
- **Bull side is the weakest link.** Three specs have a bull side, but Tier-1 cannot
  gate any of them and J has **no logged 2026 SPY bull winners yet**. Bull slots stay
  `WATCH_ONLY` until J banks bull winners on the live engine (`regime_book.py`
  BULLISH_RECLAIM note + `REGIME-AWARE-BOOK.md §6.1 bar 4`).
- **The specs corroborate setups already in the book.** They do not introduce new setup
  strings — `VWAP_TREND_PULLBACK`, `GAP_AND_GO`, `BEARISH_REJECTION_RIDE_THE_RIBBON`,
  `BULLISH_RECLAIM_RIDE_THE_RIBBON` all already exist in `regime_book.REGIME_SETUP_MAP`.
  J's winners *parameterize and validate* them at the pattern level.

---

## 6. Files

| File | Role |
|---|---|
| `markdown/0dte/J-EDGE-SETUP-SPECS.md` | **This doc** — the per-archetype specs + archetype→regime_book-slot mapping. |
| `markdown/0dte/J-EDGE-GROUND-TRUTH.md` | The two-tier ground-truth design these specs gate against. |
| `analysis/webull-j-trades/winner_setups.json` | The source feature rows every parameter is derived from. |
| `backtest/lib/engine/regime_book.py` | The `WATCH_ONLY` book these specs slot into (`VWAP_TREND_PULLBACK`, `GAP_AND_GO`, `BEARISH_REJECTION_RIDE_THE_RIBBON`, `BULLISH_RECLAIM_RIDE_THE_RIBBON` cells). |
| `backtest/autoresearch/j_edge_tracker.py` | Tier-1 `edge_capture` gate (the 3 SPY anchors). |
