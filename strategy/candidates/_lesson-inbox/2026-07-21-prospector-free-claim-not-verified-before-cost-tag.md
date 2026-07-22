# Lesson candidate: prospector's swarm self-labels "Cost: $0" on data it never verified is actually free

> Queued by conductor (AFTERHOURS, acting as chef persona) 2026-07-21 ~20:45 ET, from a
> chef-inbox backlog triage covering 31 stale prospector items (2026-07-09..2026-07-21).

## Symptom

During this fire's chef-inbox triage, at least 5 of ~31 open `_chef-inbox/prospector-*.md`
items claimed "Cost: $0" / "free" for data that turned out to be either (a) verifiably
inaccessible on our actual free stack, or (b) not free at all in reality:

- **TICK Index (NYSE Tick)** (2026-07-10 item): claimed "Cost: $0" via "Yahoo Finance via
  ^TICK." Live-verified this fire: `yf.Ticker('^TICK').history(period='5d')` returns HTTP 404
  ("Quote not found"). The ticker does not exist on our yfinance path.
- **NYSE Advance-Decline Line** (`^ADD`, cited elsewhere as Quandl `NYSE/ADLINE`): live-verified
  `yf.Ticker('^ADD')` returns no data.
- **TRIN/Arms Index** (`^TRIN`): live-verified `yf.Ticker('^TRIN')` returns no data.
- **NYSE OpenBook auction imbalance** (2026-07-10 item): claimed "Cost: $0," but NYSE
  OpenBook / OpenBook Ultra is a licensed, paid, real-time proprietary market-data product
  requiring a vendor subscription — the public nyse.com page *describes* the product, it is
  not itself a free feed.
- **FlowAlgo "free tier"** (2026-07-11 item): claimed "Cost: $0," but FlowAlgo's public "free"
  page is a limited marketing/demo sample, not a documented, stable, programmatic free API
  suitable for automated backtest ingestion.

Notably, a SIBLING prospector item proposing the SAME underlying NYSE TICK data one batch
later (2026-07-13) self-labeled it "Cost: paid" (Bloomberg/Refinitiv/Polygon.io) — the swarm
is internally INCONSISTENT about the same instrument's cost/accessibility across different
model runs, which is itself evidence the "Cost: $0" tag is not being checked against reality
at write time, just asserted by whichever free-tier LLM wrote that day's ledger row.

## Root cause

`setup/scripts/prospector.py` (the ideation organ that writes these `_chef-inbox/` items) asks
its free-model swarm to self-report a `Cost:` field in the same generation pass that invents
the idea — there is no independent feasibility check (a live ticker probe, an API-docs lookup,
or even a simple "is this a known institutional data vendor" heuristic) before that self-report
is written into the ledger and the inbox file. LLMs confidently assert "free via Yahoo Finance"
for tickers that sound plausible (market-internals symbols ARE a real, well-known category;
the SPECIFIC ones asserted here simply aren't on yfinance) — a hallucination class distinct
from, but adjacent to, the already-fixed dedup/re-promotion bug (L in this same batch's sibling
lesson, `2026-07-21-producer-state-loss-silent-inbox-flood.md` — that one was about the SAME
idea recurring; this one is about a WRONG idea being asserted feasible in the first place).

## Fix (this instance)

No code change this fire (scope: inbox triage, not prospector.py surgery). The 5 items above
were dispositioned by hand this fire with a live yfinance probe as the discriminating check
(see `strategy/candidates/_chef-inbox/*.md.DONE` markers dated 2026-07-21 ~20:40 ET). The
durable fix — a cheap, automatable feasibility gate in `prospector.py` before it writes
`Cost: $0` into a ledger row (e.g., "if the idea names a specific ticker symbol, attempt a
live yfinance/Alpaca probe and downgrade the cost tag to `Cost: UNVERIFIED` on failure, or at
minimum flag known-paid-vendor names like NYSE OpenBook/Bloomberg/Refinitiv/FlowAlgo/IQFeed/
Quandl/ThetaData/Tradier/Interactive-Brokers/CBOE-LiveVol/Polygon-paid-tier as `Cost: LIKELY
PAID` by name-matching a small denylist) — is real, bounded, buildable work, not done this
fire (scope discipline: this fire's job was draining the backlog, not building new prospector
machinery).

## Encoded in

Not yet graduated to code — this is a FIRST occurrence (one fire, one triage pass), not a
re-violation, so it does not yet meet the OP-25 "re-violated lesson -> code assertion" bar.
Filed here for `lesson-author` to write up properly in `markdown/doctrine/LESSONS-LEARNED.md`
+ fold into a CLAUDE.md OP-25 index row (candidate: extend C14 "dead/translated-but-unapplied
knobs" or C7 "silent success is failure," since an unverified "Cost: $0" claim silently
propagating into a ledger row and a chef-inbox file for 12 days before anyone checked is the
same shape as those two classes). If a FUTURE prospector batch repeats this exact pattern
(another self-labeled "$0"/"free" item that fails a live feasibility check), THAT is the
re-violation trigger for graduating this to the `prospector.py` feasibility-probe fix described
above.

## L## (optional)

lesson-author: grep current max (through L235 per CLAUDE.md's "current through" pointer as of
this fire) and assign next.
