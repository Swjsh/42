# Lesson-inbox handoff — postmortems awaiting L## authoring

> Created 2026-06-29 during the doc-fold (per `infra/DOC-ARCHITECTURE.md` §"How dated one-offs FOLD").
>
> These four point-in-time postmortems carry **durable findings that have NOT yet been folded up into
> `doctrine/LESSONS-LEARNED.md` as an L## entry.** Per the fold doctrine ("Freeze the why, evolve the
> what"), the raw postmortem stays in place as frozen provenance; the stable `symptom → root-cause → fix`
> needs to be extracted into a numbered lesson by the **lesson-author persona** (the only author with
> OP-25 / LESSONS-LEARNED write access). The doc-fold pass deliberately did NOT author these — that
> requires the lesson-author's L## numbering + CLAUDE.md OP-25 bullet, not a mechanical move.
>
> **lesson-author action:** for each item below, read the postmortem, extract the durable lesson, append
> a properly-formatted L## entry to `markdown/doctrine/LESSONS-LEARNED.md` + the matching CLAUDE.md OP-25
> row, then tick it off here. Leave the source postmortem where it is (it ages out under retention).

## Queue

| # | Postmortem (leave in place) | Durable finding to fold | Likely theme |
|---|---|---|---|
| 1 | [`audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`](audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md) | Heartbeat chart-data freshness/alignment failure mode and its fix (closed-bar / stale-feed handling). | C5 (as-of trigger time) / C7 (audit outputs) |
| 2 | [`audits/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md`](audits/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md) | Long grinder dies silently (reaper kills stale project python > 5 min) — symptom/root-cause/fix. Partially captured by the grind-reaper memory; confirm it has an L## anchor. | C7 / C8 (headless spawn) / grind-reaper |
| 3 | [`research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md`](research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md) | Engine HELD through 2 clean J-read setups; ~85% root cause was the frozen-levels bug (fixed via Gamma_LevelRefresh); 2 detectors gated on a redundancy backtest. "When J says 'engine missed X' → check the level feed FIRST, then beat the null." | C5 / C26 (level role) / C3 (beat the null) |
| 4 | [`research/CONFLUENCE-REALFILLS-VERDICT-2026-06-20.md`](research/CONFLUENCE-REALFILLS-VERDICT-2026-06-20.md) | Confluence signal loses money as a 0DTE trigger on real OPRA fills across 16 months / every quarter / every VIX band — supersedes the SPY-direction proxy (a structural-gate pass a null reproduces is an exit-structure artifact, not signal alpha). | C3 (SPY-price edge ≠ option edge) / C4 |

_When all four are folded, this handoff file can be deleted (its only job is the handoff)._
