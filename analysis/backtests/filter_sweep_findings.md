# Filter-Tuning Sweep — Entry Configurations Benchmarked

**Run:** 2026-05-07
**Window:** 2026-03-15 → 2026-05-07 (53 calendar days, ~37 trading days)
**Engine:** v8 exits held constant; only entry filters varied
**All trades use real OPRA option fills** (auto-fetched any new contracts that fired)

---

## TL;DR

**Configuration B (min_triggers ≥ 1) is the clear single-knob winner.** Relaxing
filter 10 from "≥2 of 4 triggers" to "≥1 of 4 triggers":

- Doubles trade count: **13 → 27** (now passes the n≥20 deployment gate)
- Increases win rate: **46% → 59%** (single-trigger setups are MORE accurate
  when the engine catches them in the right window)
- Reduces total drawdown: **−$935 → −$814**
- Reduces expected loss per trade: **−$57 → −$20**
- Goes from **1/4 PASS → 2/4 PASS** on live deployment scorecard

The remaining failure points (W/L ratio, expectancy) are about loss SIZE, not
trade count or hit rate. Next lever is tighter stops or smarter strike selection.

---

## Side-by-side

| Metric | A_BASELINE | **B_RELAX_TRIG** | C_VIX_SOFT | D_ONE_SLACK |
|---|---|---|---|---|
| Trades | 13 | **27** | 14 | 48 |
| Win rate | 46% | **59%** | 43% | 56% |
| Avg winner | $110 | $92 | $110 | $120 |
| Avg loser | −$200 | −$183 | −$196 | −$200 |
| W/L ratio | 0.55× | 0.50× | 0.56× | 0.60× |
| Total P&L | −$742 | **−$546** | −$913 | −$973 |
| Expectancy/trade | −$57 | **−$20** | −$65 | −$20 |
| Max drawdown | −$935 | **−$814** | −$1,106 | −$1,731 |
| Live deploy | 1/4 | **2/4** | 0/4 | 2/4 |

---

## Configuration descriptions

**A_BASELINE** — current production rules. ≥2 of 4 triggers required. VIX hard
block. All 10 filters must pass.

**B_RELAX_TRIGGERS** — only filter 10 relaxed. ≥1 of 4 triggers (level_reject
OR ribbon_flip OR multi_day_confluence OR sequence_rejection). Everything else
unchanged.

**C_VIX_SOFT** — only filter 8 modified. Failing VIX condition becomes a −1
score modifier instead of a hard block.

**D_ONE_SLACK** — allow up to 1 non-structural filter blocked (filters 1–5
remain hard requirements; one of filters 6–10 can be blocked).

---

## Why B works (and why C and D don't)

**B catches the early single-trigger rejections** that J's eye fires on. On
days like 4/29, the engine's first level_rejection bar happens at 10:25 — but
ribbon_flip and confluence and sequence_rejection don't ALL line up until
12:35. Two-trigger requirement = miss the move's launch. One-trigger = catch it.

The key insight in the data: **WR went UP, not down, when B added more trades.**
This means the additional 14 trades B took were HIGHER quality on average
than the original 13. Single-trigger rejections at clean levels are the
J-quality entries the system was missing.

**C fails because VIX is meaningful.** Soft-modifying it added 1 trade with
WR 43% (worse). The VIX > 17.30 + rising filter is selecting for elevated-fear
regimes where bearish setups have follow-through. Relaxing it grabs setups
in calm regimes that don't deliver.

**D fails for the opposite reason.** Allowing any 1 filter blocked added too
many marginal trades — drawdown nearly doubled to −$1,731. The filters work as
a stack; loosening "any one" is too permissive.

---

## What's left to fix

Even at B's 59% WR, **W/L ratio is 0.50×** — losers are 2× the size of winners.
The structural cap on losers is the −50% premium stop (≈ $-200 per 3-contract
trade) vs winners capped by TP1 at +30% premium (≈ $90 per leg). Math:
- Winner = $0.30 × 2 contracts × 100 = $60 + runner = $90 avg
- Loser = $0.50 × 3 contracts × 100 = $150 plus slippage = $-200 avg

This asymmetry is the reason live deployment still fails the W/L threshold.
Levers to investigate next:

1. **Tighter premium stop** — −33% instead of −50%. Caps losers at ~$120 instead
   of $200. Risk: more whipsaws on choppy entries.
2. **Strike selection** — engine picks ATM-round; J picks 1-2 ITM (higher delta,
   smaller premium percentage stops in dollars). Test ITM-1 strike rule.
3. **Earlier TP1 conviction** — maybe lock half of TP1 at +20% premium (faster)
   to increase win rate further at the expense of magnitude.

Each is a separate backtest. **B alone is a clean immediate-win** that closes
the entry-timing gap without breaking anything.

---

## Specific note on 5/7

Even with B (≥1 trigger), 5/7 STILL didn't fire a BEAR trade. The day's near-miss
bars were blocked by filter 8 (VIX falling post-FOMC) and filter 9 (vol below
1.3× threshold) — not filter 10. To catch 5/7 specifically, we'd need both B
AND C — which fails the broader-window backtest.

5/7 was an honest skip given the post-FOMC drift profile.

---

## Recommended action

**Ratify Configuration B as the production entry rule.** Modify
`automation/prompts/heartbeat.md` filter 10 from "≥2 of 4 triggers" to "≥1 of 4
triggers." Sync `backtest/lib/filters.py`. Update CLAUDE.md operating principle
11 with the ratified configuration.

**Defer C and D.** Both showed worse net P&L; not worth the variance.

Next investigation: loss-cap tightening (premium stop) and strike selection
(ITM-1 vs ATM-round).

---

## Files

- `backtest/tools/sweep_filter_configs.py` — the harness
- `backtest/tools/simulate_day.py` — day-by-day per-bar walker
- `backtest/lib/filters.py` — the configurable filter eval
- `backtest/lib/orchestrator.py` — threading config through

Re-run any time:
```
cd backtest
.venv/Scripts/python tools/sweep_filter_configs.py
```
