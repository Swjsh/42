# PRE-REGISTRATION — TRIGGER-ANCHOR LEVEL CLASS (exclude same-day swing pivots as reclaim/rejection anchors), 2026-09-11

**Status: FROZEN before any forward reading.** Commit timestamp of this file is the freeze proof. Candidate for the **2026-09-29 safety checkpoint** as a pre-registered **risk REDUCTION** (it only removes trigger anchors; it never adds an entry, sizes up, or widens a stop). Nothing in the live trading path changes before 09-29, and nothing changes then unless every forward gate in §4 passes.

Parent: [`analysis/deep-research/FABLE-FULL-AUDIT-2026-09-11.md`](../deep-research/FABLE-FULL-AUDIT-2026-09-11.md) §2b. Ratifying instrument: `backtest/tools/trigger_anchor_class_read.py` (committed alongside; one table, run on demand, no scheduled task).

---

## 1. What is being judged

`setup/scripts/refresh_levels_intraday.py#_swing_levels` writes two levels every 5-minute refresh — `INTRADAY_SWING_HIGH` / `INTRADAY_SWING_LOW` — defined as the **most recent 3-bar pivot in the RTH session**, with no age, hold, or touch requirement. `heartbeat_core._read_levels` appends every level within ±$12 of spot to `levels_active`; `detect_level_reclaim` / the bearish rejection test then accept *any* active level as a trigger anchor (`bar.low < level < bar.close`, or the mirror).

**The candidate rule:** a level whose label starts with `INTRADAY_SWING_` may still be drawn, journaled and used for confluence scoring, but **may not be the anchor of a `BULLISH_RECLAIM_RIDE_THE_RIBBON` or `BEARISH_REJECTION_RIDE_THE_RIBBON` trigger**. Implementation at 09-29 (if ratified): filter the anchor candidate set in the trigger detectors, or set `source` for swing levels to a non-anchor class — whichever is the smaller diff; the prereg binds the *behaviour*, not the line.

## 2. In-sample disclosure (the population that produced the hypothesis — cannot ratify)

All arms, fills 2026-08-17..2026-09-11 joined to their core ENTER tick's `conviction.matched_level_label`:

| Anchor class | Signals | Legs | Total | Sept | Winners (signals) |
|---|---:|---:|---:|---:|---:|
| INTRADAY_SWING_* | 13 | 27 | −$586 | −$1,237 (10 signals, 8 lost) | 4 |
| MEMORY_* | 15 | 41 | −$106 | −$811 | 6 |
| PRIOR_DAY / PMH-PML / RTH H-L | 11 | 37 | +$3,037 | +$506 | 5 |
| SHELF_* | 6 | 19 | +$148 | +$198 | 1 |
| none / unnamed price (ribbon-only) | 18 | 34 | +$836 | +$145 | 9 |

Signal = one (date, 3-minute entry slot) across all arms, exactly as the instrument defines it. Honest split: the swing class was **+$741 on two 08-19 signals (a trend day)** and **−$1,327 on the other 11**. n = 13 signals. Post-hoc. Concentration: 09-10 12:1x (−$600) + 09-11 10:5x (−$374) = 79% of September's class loss. This is exactly the profile that must NOT ship on in-sample numbers.

MEMORY_* is disclosed but **not** part of this candidate (n and direction are weaker; a second prereg may follow the forward read).

## 3. Forward protocol (frozen)

- **Window:** 2026-09-14 → 2026-09-28 inclusive (11 sessions), live frozen config, all four arms.
- **Read:** `backtest/.venv/Scripts/python.exe backtest/tools/trigger_anchor_class_read.py --since 2026-09-14 --until 2026-09-28`. The instrument joins each fill to its ENTER tick (±2 min) and reports signals / legs / P&L per anchor class. Run once, on 09-28 after the close, by whichever session holds the 09-29 checkpoint.
- **Nothing is armed, tuned, or peeked at mid-window.** A mid-window read for curiosity does not count and must be labeled as such.

## 4. Forward gates — ALL must pass to ship at 09-29

- **F1 sign:** forward swing-anchored signals net **< 0**.
- **F2 not a winner-killer:** forward blocked-winner dollars **< 0.5 ×** forward blocked-loser dollars.
- **F3 frequency:** **≥ 6 distinct** forward swing-anchored signals (else EXTEND to 10-30, no ship).
- **F4 concentration:** drop the single worst forward signal; F1 still holds.
- **F5 no-regression control:** forward P&L of the PRIOR_DAY / PMH-PML / RTH class is not the *only* thing keeping the engine positive in the window (i.e. the rule does not merely shift losses to the next-nearest line). Report the class table in full either way.

## 5. Kill criterion (pre-committed)

Forward swing-anchored signals net **≥ 0** over ≥ 6 signals → **KILL**, record here, never re-propose on the same population. Fewer than 6 signals by 09-28 → **EXTEND** the clock to 10-30 unchanged.

## 6. What would falsify the whole idea

If the STRUCTURAL class (prior-day / premarket / session H-L) also goes negative forward at a similar rate, the anchor class is not the discriminator — the tape is — and this prereg dies with it. Range compression (audit §2a) is the competing explanation and is named here so it cannot be discovered later as a surprise.

## 7. Revert / revoke

Before 09-29: nothing to revert (paper only). After a 09-29 ship: `git revert <ship sha>`; the swing levels are still produced and drawn, so the revert is behaviour-only and byte-identical to today.

## 8. Challenger LADDER (added 2026-09-12 under GOAL-EARN-YOUR-KEEP; J's six-day mandate)

The forward read in §3 no longer waits for the 09-29 checkpoint to produce evidence: from 2026-09-14
this rule runs LIVE on the paper challenger `risky-3` (revived as `risky-1`'s exact twin plus
`gate_override.anchor_class_denylist=["INTRADAY_SWING_"]`), while `risky-1` is the control and
`safe-2`/`safe-3` stay frozen for the score window. Gates F1-F5 and the §5 kill criterion apply
UNCHANGED to the challenger's refusals (a refusal on risky-3 of a signal risky-1 filled is one
forward "blocked" observation with a real dollar outcome). The 09-29 decision for the frozen arms
reads THIS ledger, not a replay.

One hypothesis holds the challenger at a time. When the live row terminates (KILL / SHIP / EXTEND per
its own criterion), the conductor moves the next `[ ]` row onto `risky-3` and logs it in the goal.
Rows are decision rows the conductor executes; no rotation code exists and none is planned.

| # | State | Hypothesis (ONE per-arm gate, reduction only) | Ship criterion | Kill criterion | n needed |
|---|---|---|---|---|---|
| H1 | `[~]` live 09-14 | deny `INTRADAY_SWING_*` as trigger anchor | F1-F5 above | §5: refused signals net ≥ 0 over ≥ 6 | 6 refused signals |
| H2 | `[ ]` next | deny `MEMORY_*` as trigger anchor (Sept −$811, 15 signals; §2 disclosure says weaker) | same F1-F5 on MEMORY refusals | refused net ≥ 0 over ≥ 6 | 6 refused signals |
| H3 | `[ ]` | compression sit-out: no entry before 10:30 when the 09:30-10:00 range < 0.35 × 20-day median first-30-min range (deterministic, computable at 10:00) | sat-out sessions' control P&L net < 0 AND F2-style winner test | sat-out sessions' control P&L net ≥ 0 over ≥ 5 sessions | 5 sat-out sessions |
| H4 | `[ ]` not before ~09-25 | SD-zone anchor: entries only when spot is inside an archived zone (`prereg-sd-zone-anchor-promotion-2026-09-12.md`, its own G1-G6) | its own prereg (EXPANSION — 10-30 only, never 09-29) | its own prereg | 10 archived sessions first |

H3's threshold (0.35 × median) is a first guess and is written here so it cannot be tuned after the
fact; if it never triggers in 5 sessions it is EXTENDED once, then KILLED as untestable. Nothing in
this table adds an entry, sizes up, or widens a stop.
