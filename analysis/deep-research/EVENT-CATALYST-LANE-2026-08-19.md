# THE MRNA TRADE — is it catchable, and what would it take? (2026-08-19 night)

> **J's ask:** Moderna moved ~130% overnight on cancer-trial news; the $120 calls expiring
> Friday went astronomically. *"There's no way you caught the overnight unless you're dumb lucky
> or an insider. But what you COULD catch is the move it made today after the news and market
> open."* → what scanners do we need, what news can we get, how do we start trading names?

---

## 1. THE FACTS, VERIFIED (not taken on faith)

**Underlying — Alpaca daily bars, pulled live this session:**

| Date | Open | High | Close | Volume |
|---|---|---|---|---|
| 2026-08-18 | 62.87 | 64.15 | **62.93** | 129,956 |
| 2026-08-19 | **116.17** | **176.59** | **174.27** | **3,673,339** |

- Close-to-close **+177%** — J said 130%, he *understated* it.
- The **gap alone** was +84.6% (62.93 → 116.17). That part is genuinely uncatchable.
- **After the open: 116.17 → 176.59 = +52% still available intraday.**
- Volume **28x normal**.

**The $120 call (MRNA260821C00120000, expiring 2026-08-21):**

| Date | Open | High | Close | Volume | Trades |
|---|---|---|---|---|---|
| 2026-08-17 | 0.01 | 0.01 | **0.01** | **1** | 1 |
| 2026-08-19 | **4.75** | **58.00** | 54.20 | **30,314** | **11,202** |

- Monday close → Wednesday high = **+579,900%**. J's "260,000%" is the right universe; the exact
  multiple depends on the reference price. **Not a typo, not an error.**
- **The catchable move: open $4.75 → high $58.00 = +1,121% INTRADAY.**
- The $70 strike ran 0.08 → 100.40. The $150 strike ran 1.00 → 30.00.

**The single most important number here:** that contract traded **1 lot on Monday and 30,314
lots across 11,202 trades on Wednesday.** You could actually have been filled.

## 2. THE FEASIBILITY FINDING — the news was on a feed we already own, 2h43m early

Queried Alpaca's news endpoint (already wired, $0, no new vendor) for MRNA:

| UTC | ET | Headline |
|---|---|---|
| 10:47:27 | **06:47** | *Merck And Moderna Announce Topline Results From The Phase 3 Interpath-001 Trial…* |
| 11:40:56 | 07:40 | *…Landmark Personalized Cancer Therapy Trial Success, Stocks Soar* |
| 12:07:04 | 08:07 | *12 Health Care Stocks Moving In Wednesday's Pre-Market Session* |
| — | **09:30** | **open; the $120 call opens $4.75 and runs to $58.00** |

**The catalyst was on the wire 2 hours 43 minutes before the tradeable move began.** This is not
an insider problem and not a latency problem. It is a *detection and decision* problem — the
kind this shop can actually solve.

## 3. THIS BOUNDS LAST NIGHT'S CONCLUSION (an honest revision)

Last night's screen concluded **HOT != TRADEABLE** — the hottest names carry 45-95% option
spreads, so the tradeable universe is small. **That was measured on NORMAL days and does not
survive contact with a catalyst day.**

MRNA on a normal day is exactly the mid-liquidity name that screen rejects: ~130K shares, a $120
strike trading *one contract*. On the catalyst day the same contract traded 30,314 lots. **The
event CREATES the liquidity.**

The rule splits in two:

- **Momentum-chasing on a normal day** → HOT != TRADEABLE holds. Use the liquid vehicle.
- **Event-catalyst day** → liquidity is created by the event; a static universe screen is the
  wrong instrument and a LIVE liquidity check at decision time is the right one.

This does not retract last night's finding. It bounds it.

## 4. THE DISCIPLINE PROBLEM — and it is the whole ballgame

**We are looking at the winner.** MRNA is one name, on one day, that got noticed *because* it
worked. That is textbook survivorship — and last night's own filed lesson
(`small-n-symbol-sample-manufactures-a-mechanism`) exists for exactly this failure mode, where
one spectacular name manufactured a mechanism that nine symbols destroyed.

The honest question is **not** "how do we catch the next MRNA." It is:

> **Of all large news-gap-ups, what fraction continue after the open, and what fraction fade?**

"Gap and go" and "gap and fade" are both real, common, documented behaviours. If gap-ups fade on
average, a scanner that finds them is a machine for losing money faster — and building it before
measuring the base rate would repeat every mistake of the last two days.

**We can measure it.** That is the payoff from last night: ingestion, the multi-day walk,
delta-matched selection, adverse-first resolution and the random-entry null harness all exist and
are proven. A gap-continuation study is now a one-session job, not a week's build.

## 5. WHAT TO BUILD — the scanners, ranked

**Already have, $0, verified working this session:**
1. **Alpaca news feed** (`/v1beta1/news`) — carried the catalyst at 06:47 ET.
2. **Daily/intraday bars** for gap % and relative volume.
3. **Live option-chain snapshots** for at-the-moment liquidity.

**Need to build, in dependency order:**

| # | Instrument | What it answers | Cost |
|---|---|---|---|
| 1 | **Gap-continuation base-rate study** (historical, offline) | Do large gap-ups continue or fade after the open? **GATES EVERYTHING ELSE.** | $0 |
| 2 | **Premarket gap scanner** | Which names gapped >X% on >Y-times relative volume, by 09:00 ET | $0 |
| 3 | **News tagger** | Does the gap have a *catalyst*, and of what class? An FDA readout permanently reprices a company; a squeeze does not | $0 |
| 4 | **Live liquidity gate** | At decision time, is the chain tradeable *today* — replacing the static screen for event days | $0 |
| 5 | **Halt / resumption watcher** | Big-news names get halted; resumption is the key entry moment | $0 |

**Deliberately NOT proposing:** a paid news feed, low-latency anything, or an options-flow
subscription. The catalyst sat on a free feed for 163 minutes before the move — speed is not the
binding constraint, and paying for it would solve a problem we do not have.

## 6. THE ACCOUNT — why I did not repoint the crypto key

J suggested reusing the Alpaca key "we use for crypto." Found and probed read-only:

- Account **PA38EG1JTFBT**, equity **$9,628.45**, **options level 3**, crypto ACTIVE, one dust
  BTC position worth $0.0002.
- Technically capable of exactly what J wants.
- **But it is LIVE.** `Gamma_CryptoTwin` last ran 21:50:36 tonight and the twin is writing a
  decision every 60 seconds with `armed: true`.

Trading single-name options in it would blend two programs into one equity curve — polluting the
twin's own P&L health gauge, exposing its breaker to option positions, and destroying the
non-comparability doctrine J set for it. **That is the same mistake we refused to make on the SPY
core accounts; convenience is not a reason to make it here.**

**The better answer, which honours the intent behind the request:** *we do not need an account
yet.* Every item in §5 is market-DATA work. The base-rate study, the scanners and the backtest
all run without placing a single order. **The account is the last step, exactly as it was last
night** — and when we reach it, a fresh paper account (2 minutes of J's time) beats a
cannibalised live instrument.

## 7. HOW THIS FITS — the lane just got its v2 hypothesis

Last night ended with: *"the lane needs a genuinely different signal hypothesis, and picking one
is a design decision I would rather make with J than guess at overnight."*

**J just supplied one.** Event-catalyst momentum is a completely different thesis from
level-interaction mean-reversion:

| | v1 (dead) | v2 (proposed) |
|---|---|---|
| Thesis | price returns to a level and reverses | news repriced the company; momentum continues |
| Edge source | chart structure | information + attention |
| Frequency | ~7 signals per 100 bars | rare — a handful of real catalysts a month |
| Liquidity | static screen | created by the event |
| What kills it | theta while nothing happens | the gap fades |

It is testable with the machinery already built and proven. That is the whole reason last night
was worth doing.

## 8. ORDERED PLAN (order only, no time estimates)

1. **Measure the base rate.** Historical gap-ups >=20% on elevated volume across a broad symbol
   universe → what happens open-to-close and open-to-high? Stratify by gap size, relative volume
   and news class. **This gates everything.**
2. **Random-entry null on the same population** — the gate that killed v1. If gap-continuation
   does not beat entering randomly on those same days, it dies here and we have spent one session
   instead of a program.
3. If it survives: **build the premarket scanner + news tagger**, run in SHADOW (log what it
   would have taken, place nothing).
4. **Pre-register** entry/exit rules before looking at shadow P&L — same discipline as the expiry
   experiment.
5. Only then an account, and only then paper orders.

**Nothing here is armed. No order was placed. The crypto twin was probed read-only and left
untouched.**
