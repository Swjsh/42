# SSR — sweep→structure-shift→retest at HTF levels (futures) — battery verdict + forward path

- **Source:** J-supplied screenshots 2026-08-07 (IG trader "Socrates Dimataris" 6-step
  checklist + his GCZ6 short exhibit). Full extraction/spec:
  `markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md`. Pre-reg + verdicts:
  `backtest/futures/analysis/SSR-battery/{DESIGN,RESULTS}.md`.
- **Verdict (both pre-registered batteries): KILL at the FDR bar.** v0: 0/24 smoke + 0/8
  regime. v1 (level-fidelity: running extremes + 4H-anchor knob): 0/48 + 0/16.
  Scorecards: `analysis/recommendations/futures-ssr{,-v1}-{smoke,regime}.json`.
- **PULSE tier (pre-registered): 5 cells, ALL SHORT-side.** NQ=F 15m anchor-2000
  (best: zone 0.5/sweep 0.1 — n=58, OOS mean +$1,324/tr, p=0.0135) and GC=F 1h
  (n=205-210, OOS n=38-41, OOS mean +$816-841/tr, beats B&H, p=0.045-0.062). None survive
  the 48/16-cell FDR tax — resolution is forward evidence, not more grinding on
  sanity-tier (yfinance 60d) data.
- **Diagnostics:** stops fire ~3× runner payoffs; ALL low-side-sweep (long) level families
  net-negative; ALL profitable families are high-side sweeps (shorts). Direction asymmetry
  consistent with the SPY engine's own bear-side validation. C27 flag: 5 ES wide-zone
  combos fire 81-85% of days — noise territory, none PULSE, suspect if revisited.
- **Shipped (paper/$0, J holds REVOKE):** `Gamma_SsrShadow` — own-book watch-only forward
  shadow of the two frozen PULSE configs (NQ 15m short + GC 1h short, anchor 2000,
  zone 0.5, sweep 0.1), every 15 min Mon-Fri 03:00–17:15 ET; ledger
  `automation/state/futures/ssr-shadow-would-be.jsonl`; arming bar = ≥20 closed trips AND
  positive expectancy AND beats same-horizon hold null (`ssr-shadow-progress.json`).
- **Registry note:** ran as a J-directed reopen petition against the closed
  `ohlcv_bar_pattern_mining_family` class (grounds in DESIGN §0). KILL verdicts uphold the
  closure for long-side/generic expressions; the short-side PULSE resolves via shadow.
- **Unresolved:** exhibit's 4,429.8 level is not causally reconstructible from GC=F
  front-month data at his entry moment (GCZ6 contract basis and/or chart-TZ ambiguity) —
  disclosed, non-gating.
- **Blocked on J (parked):** Tastytrade PROD-token rotation (any real futures order path);
  new-broker approval would be a net-new vendor (needs explicit OK).
