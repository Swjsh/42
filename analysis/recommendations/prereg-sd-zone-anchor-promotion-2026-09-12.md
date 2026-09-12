# PRE-REGISTRATION — SD_ZONE ANCHOR PROMOTION (Smart Money Concepts order-block zones), 2026-09-12

**Status: FROZEN before any forward reading.** Commit timestamp of this file is the freeze proof. This is a **risk EXPANSION candidate** (it would ADD a new anchor class to the entry gate, not remove one) — eligible ONLY at the **2026-10-30 checkpoint**, never at 09-29, and only after the forward-clock eligibility gate below is met.

Parent: [`automation/state/goals/GOAL-SD-LIQUIDITY-ZONES-2026-09-11.md`](../../automation/state/goals/GOAL-SD-LIQUIDITY-ZONES-2026-09-11.md) item (d)/(e). Sibling instrument (do not confuse the two — that one is a risk REDUCTION eligible at 09-29): [`prereg-trigger-anchor-level-class-2026-09-11.md`](prereg-trigger-anchor-level-class-2026-09-11.md).

---

## 1. What is being judged

`setup/scripts/sd_zones_producer.py` (shipped 2026-09-12) reads `Smart Money Concepts [LuxAlgo]` order-block boxes headlessly over CDP, scores each with the already-ratified `_uniform_touches` math, and writes a SHADOW file (`automation/state/sd-zones.json`, live snapshot) plus a per-day archive (`journal/sd-zones-archive/{day}.json`). Neither file is read by `heartbeat_core.py` or `automation/state/fleet/build_shared_signal.py` (pinned by `test_trading_path_never_references_the_shadow_file` and `test_module_never_imports_heartbeat_core_or_writes_key_levels`).

**The candidate rule (NOT decided here):** promote SD_ZONE bases/liquidity pools into the live entry gate as a named anchor class alongside PRIOR_DAY / PMH-PML / RTH H-L / MEMORY / SWING — either as a new trigger-anchor source in `heartbeat_core.py`'s level readers, or narrower, as a *confluence* filter (only take a swing/memory-anchored trigger if it also sits inside an SD zone). Which shape ships, if any, is decided AFTER the forward read in §3-4, not pre-committed here — this document freezes the *evaluation protocol*, not the implementation.

## 2. Why this candidate exists (disclosure, not evidence — cannot ratify on this alone)

`FABLE-FULL-AUDIT-2026-09-11` §2b found the two worst-performing anchor classes are same-day `INTRADAY_SWING_*` 3-bar pivots (−$586, Sept −$1,237) and multi-day `MEMORY_*` prices (−$106, Sept −$811), while the structural class (prior-day/premarket/session H-L) made +$3,037 over the same window (2026-08-17..2026-09-11). Neither losing class is a supply/demand base or a liquidity pool in the trader's sense — J's own doctrine already frames the play as zone → wait for the return → structure shift (2026-07-28 memory). The hypothesis: an SD-zone-anchored or SD-zone-confirmed entry would out-perform both losing classes, closer to the STRUCT baseline. **This is a hypothesis, not a finding** — zero SPY trades have ever been taken with SD-zone information available; every dollar figure above pre-dates this instrument.

## 3. Forward-clock eligibility gate (must clear BEFORE any read counts)

- `automation/state/sd-zone-forward-clock.json.eligible_for_forward_read` must be `true` — i.e. **≥ 10 distinct trading-day snapshots** archived in `journal/sd-zones-archive/`. Each snapshot only counts on a real `status="OK"` capture (never a `--dry-run`, never a `SKIPPED_TV_DOWN` carry-forward of a stale zone set — guarded by `test_dry_run_never_archives_or_advances_the_clock` / `test_tv_down_skip_never_archives_or_advances_the_clock`).
- Cadence: `Gamma_SdZonesProducer`, 08:44–~16:00 ET weekdays, every 15 min (`setup/scripts/install-sd-zones-producer.ps1`). First possible archived session: **2026-09-14** (Monday). At one session/trading-day, 10 sessions accrue by roughly **2026-09-25**, well inside the 10-30 checkpoint.
- **Before this gate clears, no forward read counts as evidence** — a mid-accrual peek (e.g. 3-4 sessions) is curiosity, must be labeled as such if reported, and does not shorten the window.

## 4. Forward protocol (frozen)

- **Window:** from the date the forward-clock gate clears (§3) through **2026-10-28** (2 sessions before the 10-30 checkpoint), live frozen/near-frozen config, all four arms.
- **Read:** `backtest/.venv/Scripts/python.exe backtest/tools/trigger_anchor_class_read.py --sd-zone --since <clock-clear-date> --until 2026-10-28`. The instrument joins each fill to its ENTER tick's SPY spot (±2 min, identical tolerance to the ratified `read()` path) and checks that spot against the day's archived SD-zone snapshot — `in_zone` vs `out_of_zone` vs `no_archive_days` (a day with no archive must never be silently folded into `out_of_zone`).
- **Nothing is armed, tuned, or peeked at mid-window** beyond the labeled-curiosity carve-out in §3.

## 5. Forward gates — ALL must pass to ship (10-30 checkpoint only; this is an EXPANSION, never 09-29)

- **G1 sign:** `in_zone` bucket net P&L **> 0**.
- **G2 discriminates:** `in_zone` per-leg P&L **exceeds** `out_of_zone` per-leg P&L over the same window (the zone must add information, not just track the existing edge).
- **G3 frequency:** **≥ 10 distinct `in_zone` legs** (else EXTEND, no ship — an n<10 read cannot support adding a new live anchor class).
- **G4 concentration:** drop the single best `in_zone` signal (day+3-min slot); G1 still holds.
- **G5 no-regression control:** the STRUCT class (PRIOR_DAY / PMH-PML / RTH H-L) does not go negative over the same forward window — if it does, the tape/regime is the discriminator, not the zone, and this prereg dies with it (mirrors the sibling prereg's §6 falsification clause).
- **G6 coverage:** `no_archive_days` is **0** for the read window (the clock-eligibility gate in §3 should already guarantee this, but the read script must report it explicitly rather than assume it).

## 6. Kill criterion (pre-committed)

`in_zone` net P&L **≤ 0**, OR G2 fails (in_zone does not beat out_of_zone), over ≥ 10 `in_zone` legs → **KILL**, record here, never re-propose SD_ZONE as a live anchor class on this population. Fewer than 10 `in_zone` legs by 2026-10-28 → **EXTEND** the clock; the shadow file keeps accruing regardless (it costs $0 and blocks nothing).

## 7. What would falsify the whole idea

If `out_of_zone` legs perform just as well as `in_zone` legs (G2 fails even though G1 might pass), the zones are not adding discriminating information — they may simply be common enough (order blocks are frequent) that most entries land near one by chance, and this is noise dressed as structure. The `kind` (supply/demand) label is itself a naming heuristic (position relative to spot at write time, per `sd_zones_producer.classify_zones`'s own docstring) and has never been independently validated — a G1 pass with a G2 fail should be read as "the zones are ubiquitous," not "the zones don't work."

## 8. Revert / revoke

Before promotion: nothing to revert (paper-shadow only, zero live-path references — pinned by test). If a future 10-30+ session ships SD_ZONE as a live anchor: `git revert <ship sha>`; `sd_zones_producer.py` and its archive keep running unaffected (the revert is behaviour-only in `heartbeat_core.py`/the fleet signal builder, not a data-collection change).
