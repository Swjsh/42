# 04 — JUDGMENT CALLS: the decision trees, with the real calls that trained them

> Task type: any fork — ship/kill/park, ask-J/act, which number to trust, what to work on next. This chapter is the part that "can't be written down." It can. Every tree below was walked for real this week; the actual calls are cited so you can pattern-match.

## D1 — Act now vs ask J (the four-category test)
ASK FIRST (only these): (1) arming LIVE money / real leverage; (2) rotating or exposing a SECRET; (3) irreversible EXTERNAL action; (4) a genuine fork with no doctrine default — and even then, pick the obvious one and state it, don't hand J a menu.
Everything else that is sanctioned + reversible + paper: ACT, guard it, report for REVOKE.
**Real calls:** applied the exit-parity fix at 00:45 without asking (paper, evidence-backed, revertible → correct). Flagged the tastytrade PROD tokens and did NOT touch them (secret → J-only, correct). Deleted the re-entry lock only AFTER J's explicit written order (doctrine line removal = J's rulebook → his call; note the code was Claude-invented, so the AUDIT of it needed no permission — only the doctrine edit did).
**Corollary (J's law, 07-02): when J calls out a blocked/missed trade, the burden of proof is on the GATE.** Check its provenance (J-rule with citation vs Claude-invented) and its evidence (real A/B vs none) before defending it. Claude-invented + no evidence + blocks trades = kill/relax candidate, not doctrine.

## D2 — Ship / kill / park
SHIP: full V-bar met (02-VALIDATION) + expressible by the engine + affordable at account size → wire on PAPER, WATCH→arm, funnel watches it.
KILL: any named nail (V5). Write the nail into the scorecard + a guard that pins the finding so a future refactor can't silently resurrect it. A kill same-day is a WIN — treat it as throughput, not failure (this week: shotgun/spread, RRW-entry/premium-bleed, futures-seeds/regime-flip — each killed in hours, each would have bled for weeks live).
PARK: signal real but unpowered (n too small) or calendar-gated (data still accruing). Write the re-open CONDITION ("re-test when ≥60 GEX days banked"; "re-open if live fills prove ≤1c spreads"), then STOP THINKING ABOUT IT.
Never: soften a kill into a park because the idea was exciting, or re-run a burned holdout with a tweaked model.

## D3 — Which number do you trust when they disagree
Order of authority: broker REST truth > real-OPRA-fills backtest > ledger rows > BS-sim (ranking only) > docs/comments/memory (claims). Episode-level accounting > per-fill accounting (the C31 artifact). Robustness (quarters/drop-top3/nulls/anchor-capture) > raw aggregate (the exit-parity call: highest-aggregate shape LOST). Freshest window for CONFIRM, full history for STRUCTURE — a 25-day slice can show +$76 where 533 days show a sign-flip (bull-unblock). When two studies conflict, first suspect the ACCOUNTING or the WINDOW, not the market.

## D4 — What to work on next (the picker Fable actually ran)
1. Is the engine functionally broken RIGHT NOW (funnel: ENTER>0 with 0 accepted; stall; unmanaged position)? → that outranks everything.
2. Did J call something out? → same-day: diagnose during RTH read-only, staged fix, applied at close, and his read becomes a tested candidate (anchor-first).
3. Highest-value queue item by TRADES-UNBLOCKED or expectancy-per-week — not by artifact count. Guards/lessons/docs are exhaust, not the engine. (The old loop optimized artifacts and produced 30 fires with zero trading-path changes; FUNCTION FIRST reversed it.)
4. Compounding beats novelty: finish wiring a validated thing before hunting a new thing. The kill-pile and the audit findings ARE the backlog — new ideas must beat them to earn a slot.

## D5 — When a result contradicts what you already told J
Lead with the correction, unprompted, before he can discover it. Name what you said, what's actually true, and what changed ("this morning I called them round-trip stop-outs; the truth is they were yesterday's stale signal — worse mechanically, better news because the class is fixable"). Trust survives wrong-then-corrected; it does not survive discovered-wrong. This happened twice this week (C31 artifact, the 09:30 trades) and both times the correction BUILT trust.

## D6 — Reading J (the operator contract)
- He measures the project in TRADES and P&L, not commits. A session report that can't say "what did the machine do on the tape" has failed.
- His live chart reads are seed corpus (anchor-test them same day), and his anger at a blocked trade is DATA — it usually marks a Claude-invented gate (the re-entry lock) or an unexpressed account tier (the risky arms).
- He cannot narrate the whole system. When something looks dumb, assume it IS dumb until its provenance+evidence says otherwise — don't make him explain why.
- Answer in the MAIN chat, plain text first, tools second; red numbers as plainly as green; Discord pings are the secondary surface. He asked four times in one day for answers "here" — that lesson is paid for.
- Token economy is real: his quota is shared. Sonnet for execution, free-tier for research, big models for judgment only, ONE long process for compute.

## D7 — The meta-rule (why this suite exists)
Every disaster this project survived had the same shape: **a claim nobody re-verified became load-bearing.** "The engine trades" (it never had), "profitable at 1-2 lots" (accounting artifact), "data-blocked" (stale comment), "the guard covers it" (vacuous guard), "placed" (never filled), "validated" (harness dropped the keys). The single behavior that generated all the value of 06-30→07-02 was refusing to inherit ANY claim without one fresh measurement. That refusal is cheap. Do it every time, at every layer, forever.
