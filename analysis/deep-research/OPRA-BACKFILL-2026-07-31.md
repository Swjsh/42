# OPRA Backfill 2026-07-31 — Completeness Verification & Population-Boundary Gate

**Written 2026-08-02, closing a loop Friday night's backfill agent left open.** That agent ran
`tools/_backfill_opra_2024_01_18_2024_12_31.py` to extend the OPRA option cache toward 2024,
reported (in its own progress file, never in a doc) a true data floor of **2024-01-18** and a
target of 241 additional trading days, then stopped without writing this document. Per
`markdown/infra/DATA-PROVENANCE.md`'s own rule ("new bar producers register here... before their
output is consumed"), every study run since Friday night correctly treated the pre-existing
**391-day population (2025-01-02..2026-07-31)** as the verified frame and left the 2024 range
locked — the doc that unlocks it didn't exist. This document is that gate. It was produced by
independently re-deriving every claim from disk state and live Alpaca re-queries, not by trusting
the Friday-night run's own logs.

**Read this before citing 2024 data in any study.**

---

## 1. Headline verdict

- **2024 stratum: CLEARED FOR USE, with two excluded days and three minor-caveat days —
  239 of 241 targeted trading days (2024-01-18..2024-12-31) are verified usable; 236 are fully
  clean.** Every future study that touches 2024 must disclose it as a **separate stratum** (§7) —
  never silently concatenated with the existing 391-day population.
- **Two days are EXCLUDED, both independently re-confirmed LIVE against Alpaca this session
  (not just trusted from the cache):**
  - **2024-02-02** — OPRA options gap. Zero option bars across an 82-contract net (ATM ±20
    strikes, both sides) queried live right now. Genuine upstream hole, not a fetcher artifact
    (§4).
  - **2024-12-23** — SPY 5m bar gap. Only 11 of 78 expected bars (session cuts off at 10:20 ET).
    **This is a NEW finding — Friday night's run never surfaced it.** Live re-query returns the
    identical 11 bars with an explicit "no more pages" signal from Alpaca — genuine IEX
    single-venue thinness on an unusually quiet session (Monday before Christmas Eve), not a
    fetcher bug. The OPTIONS side of that same day is fully populated (§4).
- **Three days carry a disclosed minor tail-only SPY-bar gap** (≤5 of 78 bars missing, all at the
  very end of the session) — usable for anything not anchored to the closing 20-30 minutes:
  2024-08-27 (−1 bar), 2024-11-22 (−4 bars), 2024-12-31 (−5 bars).
- **No feed seam at the 2025-01-01 boundary.** The 2024 SPY segment uses the identical feed +
  script (Alpaca IEX via `extend_data_v2.py`) as the existing 2025+ masters. The pre-existing
  `spy_5m_2025-01-01_2026-07-22.csv` master is **verified unmutated three independent ways**
  (§6) — mtime, byte-for-byte row equality, and a pinned hash in the new guard test.
- **VIX has a real, disclosed granularity cliff inside the 2024 stratum**: hourly through most of
  it, but **daily-only for 2024-01-18..2024-07-30** (yfinance's 730-day intraday cap). Any study
  gating on intraday VIX *character* (not just level — see doctrine C5) is **ineligible** for that
  sub-range (§5).
- **The population boundary is enforced by convention, not by a hard gate** — a finding beyond
  what was asked, but load-bearing (§7). Checked exhaustively (48 files using a "biggest SPY file
  wins" pattern, not a partial grep): 45 are safe (34 by explicit anchor, 11 incidentally via an
  unrelated VIX-pairing filter). **One script (`backtest/tools/d1_vix_gated.py`) was actually
  broken by Friday night's backfill (would now crash with `FileNotFoundError`) and is fixed here.**
  Two more (`pml_scan.py`, `v14e_chart_stop_research.py`) now silently read the bigger,
  2024-inclusive file with an unresolved (not crash-risk, but unverified) chance of pulling 2024
  rows into an aggregate — flagged as a follow-up, not fixed blind.

---

## 2. What's on disk

| | Old span (existing, unchanged) | New 2024 stratum |
|---|---|---|
| SPY 5m bars | `spy_5m_2025-01-01_2026-07-22.csv` (+ daily rolling chain) | `spy_5m_2024-01-18_2024-12-31.csv` (new) + `spy_5m_2024-01-18_2026-07-22.csv` (merged, additive) |
| OPRA option contracts | 2025-01-02..2026-07-31, part of the shared `data/options/` cache | 2024-01-18..2024-12-31, same shared cache, same schema |
| VIX | `vix_5m_2025-01-01_*` hourly chain | `vix_daily_proxy_2024-01-18_2024-07-30.csv` (daily) + `vix_5m_2024-08-01_2024-12-31.csv` (hourly, mislabeled "5m") |
| Population (per existing doctrine) | 391 trading days | 241 trading days targeted, **239 verified usable** |

`backtest/data/options/` currently holds **634 distinct expiry-dates with real (non-empty) data**
across the whole cache (240 in 2024 + 249 in 2025 + 145 in 2026 — independently recomputed from
the raw filenames, matches exactly) plus one 2024 expiry-date (2024-02-02) that has files but
**zero real ones** (22 empty sentinels only) — 635 distinct expiry-dates total on disk, 634 with
usable data. **Distinct expiry-dates is not the same number as verified-usable trading days** —
see §3 for why (this is the exact conflation this document exists to avoid).

---

## 3. Completeness methodology — what "usable" means here

A trading day only counts as usable if **both** of the following hold, checked independently, not
inferred from file existence alone:

1. **SPY 5m bar completeness.** The day's actual bar count in `spy_5m_2024-01-18_2024-12-31.csv`
   must be at or near the expected count for that day's real session length (78 bars for a normal
   RTH session, 42 for the three 2024 early closes: 07-03, 11-29, 12-24 — expected counts derived
   from the NYSE XNYS calendar, cross-checked and found to match the SPY master's own day-set
   exactly: 241/241, zero calendar days missing from the master). A day with a deficit of more
   than ~15 bars (≈19% of session) is a **hard fail** — a bar file existing is not the same as the
   session being covered.
2. **Near-ATM OPRA coverage.** For that day's ATM strike (`round(daily_close)`) ± 2, both call and
   put (10 contracts — the same "has data" definition `_probe_opra_floor.py` used to establish the
   floor), at least one must be a **real** cached file (not a `.csv.empty` sentinel, not a
   header-only/near-empty file under 100 bytes).

This two-part check is what caught 2024-12-23: it has full near-ATM option coverage (both sides
real all day) but only 11 of 78 SPY bars — a day that a naive "does an expiry-date directory
exist" check (which is what Friday night's own draft verification script did — see §8) would have
silently marked complete.

**Verification tool:** `backtest/tools/_verify_opra_backfill_2024.py` (rewritten 2026-08-02,
dependency-free — no `pandas_market_calendars` in `backtest/requirements.txt`, so the 2024
trading-day calendar is a hardcoded holiday list, cross-checked against the SPY master's own
day-set). Re-run it any time the 2024 cache changes; it exits nonzero if any day is non-clean.

### Full result table

| Status | Count | Days |
|---|--:|---|
| PASS (fully clean) | 236 | — |
| PASS_WITH_CAVEAT (minor tail-only SPY gap, ≤5 bars) | 3 | 2024-08-27 (−1), 2024-11-22 (−4), 2024-12-31 (−5) |
| FAIL (excluded) | 2 | 2024-02-02 (options gap), 2024-12-23 (SPY gap) |
| **Total targeted** | **241** | 2024-01-18..2024-12-31 |
| **Verified usable (PASS + CAVEAT)** | **239** | cite this number, not 241 or 240 |

---

## 4. The two excluded days — root-caused, not assumed

### 2024-02-02 — OPRA options gap (confirmed genuine, live)

The cached state: all 22 near-band contracts (ATM±5, both sides) for the 2024-02-02 expiry are
`.csv.empty` sentinels — zero real files. The original backfill run recorded **0 HTTP errors**
across the whole 5,302-contract run (so this wasn't a retried-and-gave-up failure), meaning
Alpaca's API returned a clean 200 with an empty bars array, not an error.

**Live re-confirmed this session** (read-only GET against
`https://data.alpaca.markets/v1beta1/options/bars`, same auth path as the production tooling):
fetched the real SPY 2024-02-02 daily close (494.29) from Alpaca directly, then queried a wide
**82-contract net** (ATM ±20 strikes, both sides — the same order of magnitude cited in this
task's briefing) for that expiry. Result: **`total_bars=0`, zero contracts with any data,
`next_page_token: None`.** This is not a stale local cache artifact — Alpaca's OPRA feed reports
zero prints for SPY 0DTE options on this date, right now, across a strike range 4x wider than the
production fetch band. Genuine upstream hole. Excluded from the usable count.

### 2024-12-23 — SPY 5m bar gap (NEW finding, root-caused, live-confirmed)

Not mentioned anywhere in Friday night's run or its progress file — found by this verification's
per-day bar-count completeness check, which the original run never performed (it only checked
that an SPY bar file existed for the day at all, and that an option file existed per expiry — both
true for 2024-12-23).

**The data:** `spy_5m_2024-01-18_2024-12-31.csv` has 11 rows for 2024-12-23, spanning
09:30–10:20 ET, then nothing — a 67-bar deficit (86% of the session missing) on a day the NYSE
calendar shows as a completely normal full session (09:30–16:00 ET, not an early close; the early
close that week was 12-24).

**Two hypotheses were held and discriminated, not just the first one that fit:**

1. *Fetcher truncation* (`extend_data_v2.py`'s `fetch_spy_window` silently swallows exceptions
   mid-pagination — `except Exception: return rows`, no retry, no re-verification against expected
   count — a real, confirmed-present code pattern, and the short days cluster suspiciously at
   `_month_windows()` chunk boundaries: 2024-11-22, 2024-12-23, and 2024-12-31 are the *exact* last
   day of three consecutive ~30-day windows).
2. *Genuine upstream gap* (IEX — the single lit-venue feed `extend_data_v2.py` uses for SPY, not
   the consolidated tape — simply has no prints on SPY for part of an unusually quiet session, the
   Monday before Christmas Eve).

**Live re-query (read-only GET, same feed/params as `extend_data_v2.py`: `feed=iex`, 5-min bars,
09:00–17:05 UTC window) returned exactly 11 bars — identical count, identical first/last values to
the cache — with `next_page_token: None`.** A fresh, independently-scoped, single-window query
with no pagination history to inherit a bug from reproduces the exact same truncation. **This
falsifies hypothesis 1.** Hypothesis 2 stands: IEX genuinely has no SPY prints on this single venue
after 10:20 ET that session. The window-boundary clustering is very likely coincidental (or a
separate, much smaller tail-loss effect — see the three PASS_WITH_CAVEAT days, all also at window
boundaries, all with far smaller deficits) rather than the cause of this specific 67-bar hole.

**Corroborating evidence this is IEX-specific, not "no market that afternoon":** the OPTIONS cache
for 2024-12-23 (`SPY241223C00589000.csv` / `...P00589000.csv`) has 79 rows covering the full
session with real, actively-trading premiums (put decayed from 0.97 to 0.01, call ran up to 6.12
before fading) — real, liquid 0DTE activity all afternoon. Options bars come from OPRA
(consolidated across all listed options exchanges), a structurally different and much deeper feed
than IEX-only stock prints. A single quiet venue going dark on the underlying while the
(consolidated) options tape stays busy is a known IEX characteristic — already documented in
`markdown/infra/DATA-PROVENANCE.md` as "IEX volume ≈ 2-4% of consolidated" — not a new defect
class.

**Verdict: excluded from the usable count, root cause is a genuine single-venue feed limitation
(not a fetcher bug), and this day should NOT be silently "fixed" by a future re-fetch attempt
without re-running this verification and updating this doc's 239 figure.**

---

## 5. VIX — the granularity cliff

| File | Resolution | Span | Notes |
|---|---|---|---|
| `vix_daily_proxy_2024-01-18_2024-07-30.csv` | **Daily** (1 row/trading day, 09:30 ET anchor) | 134 rows, verified | yfinance's hourly VIX endpoint is capped at "within the last 730 days" of the *call* date — from 2026-07-31 that boundary lands at 2024-07-31, making hourly VIX for this sub-range permanently unfetchable via this path, regardless of how the request window is framed. |
| `vix_5m_2024-08-01_2024-12-31.csv` | **Hourly** (mislabeled "5m" — matches the existing chain's own naming convention, forward-filled to 5m downstream) | 1,496 rows, verified | Same yfinance-1h source as the rest of the `vix_5m_*` chain. No new caveat beyond the existing one. |

**Confirmed the daily-proxy file is genuinely daily** (opened it directly: one row per trading day,
no intraday rows) and **confirmed it is NOT merged into, and not glob-matched by, the `vix_5m_*`
chain** (its filename prefix is `vix_daily_proxy_`, not `vix_5m_`; every consumer glob found in
this codebase anchors on the `vix_5m_` or `vix_5m_2025-01-01_` prefix specifically).

**Practical consequence:** any study over 2024-01-18..2024-07-30 that gates on intraday VIX
*character* (rate of change, intraday spike/decline shape — doctrine C5: "VIX character > VIX
level") has **no eligible VIX signal** for that sub-range and must either skip it or fall back to a
daily-level-only proxy with that limitation stated in the study's own disclosure. Studies that only
need a VIX *level* snapshot (e.g., a daily regime label) are fine across the whole 2024 stratum.

---

## 6. Feed provenance — is there a seam at 2025-01-01?

**No feed seam.** Both segments of the 2024 backfill reuse the exact scripts/feeds already in use
for the 2025+ masters:

- **SPY bars:** `extend_data_v2.py`, Alpaca **IEX**, identical to `spy_5m_2025-*` masters. The 2024
  segment additionally uses the **DST-correct per-row offset** fix (`utc_iso_to_et_string`, shipped
  2026-07-02) — confirmed by inspecting raw rows: January/December 2024 rows carry `-0500` (EST),
  July rows carry `-0400` (EDT). This is *more* correct than the oldest legacy rows in the
  pre-existing 2025 master, which still carry the old fixed-offset convention from before that fix
  shipped (documented, unrelated to this backfill).
- **OPRA option bars:** same `fetch_contract_bars` / `write_cache` / `write_empty_sentinel` /
  `already_cached` functions from `expand_opra_cache.py`, same 8-column schema, same auth path.
  **One pre-existing, cross-cutting quirk carries over unchanged (not new to 2024):** the option
  writer stamps every row with a fixed `-04:00` label regardless of real DST state. For winter
  months this makes the *raw string* look off by an hour (e.g. a real 09:30 ET January bar is
  labeled `10:30:00-04:00`) — this briefly looked like a bug during this verification until
  checked carefully: because the label is a **timezone-aware offset**, not a naive wall-clock
  string, and the hour subtraction (`ts_utc - 4h`) is undone by the `+4h` implied by re-parsing the
  `-04:00` suffix, the encoded **absolute UTC instant is correct** — only a raw/naive read of the
  string is misleading. Any consumer that parses it as offset-aware (which `option_pricing_real.py`
  does: `pd.to_datetime(df["timestamp_et"])`) gets the right instant. Flagging this explicitly so
  the next person who opens a winter-month 2024 option CSV and does the mental math doesn't lose
  time re-deriving the same reassurance.

### The 2025+ master — verified unmutated, three independent ways

Per the task's explicit instruction to verify rather than trust the earlier agent's claim:

1. **mtime unchanged.** `spy_5m_2025-01-01_2026-07-22.csv` last modified **2026-07-22 20:36**, nine
   days before the 2024 backfill ran (2026-07-31). If the backfill had rewritten it in place, the
   mtime would show 2026-07-31.
2. **Byte-for-byte row equality.** Sliced the new merged file
   (`spy_5m_2024-01-18_2026-07-22.csv`) to rows `>= 2025-01-01` (37,816 rows) and compared against
   every row of the original `spy_5m_2025-01-01_2026-07-22.csv` (also 37,816 rows) — **exact
   value-for-value match on every column, zero diffs.**
3. **Hash pin.** `sha256(spy_5m_2025-01-01_2026-07-22.csv)` =
   `70be577fb3bd769b2e0cc26bd4a3e56281c054f53e13842d81a475f2ed01b289`, now pinned in
   `backtest/tests/test_graduated_guards.py::test_opra_2025_spy_master_unmutated_by_2024_backfill`
   — any future accidental rewrite of this exact file goes RED immediately.

The merge (`spy_5m_2024-01-18_2026-07-22.csv`) is a **new, additive file** — nothing was renamed,
overwritten, or deleted. `expand_opra_cache.py`'s `resolve_spy_master()` glob (anchored on the
`spy_5m_2025-01-01_` prefix) still resolves the old lineage untouched; the new
`_backfill_opra_2024_01_18_2024_12_31.py` script points at the new merged master explicitly. Live
re-import of `resolve_spy_master()` this session confirms it still resolves a `spy_5m_2025-01-01_*`
filename, not a 2024-dated one — guarded (§9).

---

## 7. Population-boundary enforcement — convention, not a hard gate (new finding)

Beyond what was asked, but load-bearing: **the option-cache reader itself
(`backtest/lib/option_pricing_real.py::load_contract_bars`) has no date floor whatsoever.** It
resolves purely by OCC symbol string — if a file with that name exists on disk, it loads it,
regardless of trade date. Before Friday night, this was safe *by accident*: no 2024 option cache
existed, so any request for a 2024 symbol (e.g. from a date-arithmetic bug, an off-by-one-year typo,
a bad `--start` flag) returned `None` loudly and predictably. **Now that 5,258 real 2024 contract
files exist, that safety net is gone for this specific window** — the same kind of bug would now
silently return real-looking 2024 data instead of failing loud.

**What actually keeps studies scoped to the 391-day population, checked exhaustively across every
`spy_5m`-globbing line in `backtest/*.py` and `backtest/tools/*.py` (48 files matched a
biggest-file-wins selection pattern, checked individually — this was NOT assumed from a partial
grep):**

- **34 scripts are safe by explicit filename anchor** — they glob `spy_5m_2025-01-01_*.csv`
  specifically, which structurally cannot match a `spy_5m_2024-*` file.
- **11 scripts use an unanchored `spy_5m_*.csv` glob but are incidentally protected** by a shared
  idiom that first filters candidates to those with a same-named `vix_5m_*` sibling
  (`p.name.replace("spy_5m", "vix_5m")`). No `vix_5m_2024-01-18_2026-07-22.csv` exists (the 2024
  segment's VIX files use different names — §5), so the new SPY merged file never survives that
  filter. Protected by accident, not by design — this idiom would silently break if a future VIX
  merge ever produces a name-matched sibling.
- **1 script (`backtest/tools/d1_vix_gated.py`) was ACTUALLY BROKEN by Friday night's backfill and
  is fixed as part of this verification pass.** It picks "the biggest `spy_5m_*.csv`" with no
  anchor and no vix-pairing filter, then separately derives its VIX path by name-substitution on
  whatever SPY file won. Before the backfill, the biggest file was
  `spy_5m_2025-01-01_2026-07-22.csv` (paired with an existing `vix_5m_2025-01-01_2026-07-22.csv`).
  After the backfill, the biggest file became `spy_5m_2024-01-18_2026-07-22.csv` — which has no
  `vix_5m_2024-01-18_2026-07-22.csv` sibling, so the script's `main()` would have raised
  `FileNotFoundError` on its next run. **Fixed by anchoring both occurrences to
  `spy_5m_2025-01-01_*.csv`**, restoring the exact pre-backfill resolution (verified: re-ran
  `get_oos_fill_days()` after the fix, got the same 60 real 2026 dates back, and confirmed both
  `spy_path`/`vix_path` now resolve to the existing paired files). Root cause in one sentence: two
  independent file-resolution mechanisms (SPY: biggest-file-wins; VIX: name-derived from whichever
  SPY file won) that used to coincidentally agree stopped agreeing the moment a new, bigger,
  unpaired SPY file appeared.
- **2 scripts (`backtest/autoresearch/pml_scan.py`, `backtest/autoresearch/v14e_chart_stop_research.py`)
  now silently resolve to the 2024-inclusive merged file and were NOT fixed here** — neither reads
  a paired VIX file (no crash risk), and both appear (from what was read) to key their actual
  analysis off specific 2026 dates (`J_ANCHOR_DAYS`, `watcher-observations.jsonl`) rather than
  aggregate the full SPY population, which would make the extra 2024 rows harmless — but this was
  **not fully traced end-to-end** and is flagged rather than assumed safe. Filed as a follow-up
  (see task chip).

**Net assessment:** the population boundary is safe for the overwhelming majority of the codebase
(45 of 48 checked scripts, either by design or by an incidental-but-currently-effective filter), one
real breakage was found and fixed, and two scripts have an unresolved, low-confidence-but-plausible
risk of silently including 2024 rows in an aggregate. None of the 48 checked scripts are part of the
live trading path (heartbeat_core.py, params.json, filters.py) — this is entirely a backtest/research
tooling surface. Worth a dedicated, properly-scoped audit of the "biggest file wins" idiom generally
(convert it to an explicit floor parameter) rather than patching resolvers one at a time as they're
individually discovered — out of scope for this verification pass.

---

## 8. Spot checks — 6 files opened directly (3 required + 3 from the rewritten tool)

Filenames, row counts, and first/last rows, quoted directly (not summarized):

| Date | File | Rows | First row | Last row |
|---|---|--:|---|---|
| 2024-01-19 | `SPY240119C00482000.csv` | 69 | `10:30:00-04:00, o=0.07 h=0.07 l=0.06 c=0.06 vol=24` | `17:00:00-04:00, o=0.41 h=0.72 l=0.38 c=0.68 vol=4257` |
| 2024-02-13 | `SPY240213P00494000.csv` | 79 | `10:30:00-04:00, o=1.05 h=1.30 l=0.82 c=0.84 vol=13990` | `17:00:00-04:00, o=0.12 h=0.25 l=0.12 c=0.16 vol=5934` |
| 2024-07-16 | `SPY240716C00565000.csv` | 80 | `09:30:00-04:00, o=0.35 h=0.49 l=0.34 c=0.48 vol=13847` | `16:10:00-04:00, o=0.04 h=0.05 l=0.02 c=0.02 vol=2932` |
| 2024-08-05 | `SPY240805C00519000.csv` | 81 | `09:30:00-04:00, o=2.06 h=2.48 l=1.84 c=2.03 vol=488` | `16:10:00-04:00, o=1.10 h=1.10 l=0.20 c=0.21 vol=556` |
| 2024-07-08 | `SPY240708C00555000.csv` | 81 | `09:30:00-04:00, o=1.01 h=1.57 l=1.01 c=1.45 vol=13189` | `16:10:00-04:00, o=0.52 h=0.52 l=0.31 c=0.35 vol=1042` |
| 2024-10-21 | `SPY241021C00584000.csv` | 81 | `09:30:00-04:00, o=0.93 h=1.08 l=0.87 c=0.93 vol=11470` | `16:10:00-04:00, o=0.03 h=0.06 l=0.03 c=0.03 vol=2702` |

All six: real, positive OHLC, internally consistent (high ≥ max(open,close), low ≤ min(open,close)
on every row checked), plausible volume/trade-count shape for a 0DTE contract (decaying toward the
close, occasional intraday spikes). None empty, none header-only, none malformed. **No sampled file
failed** — the 2024 stratum passes the "did a fetcher silently write empty files" check (L241) on
every day sampled.

**Beyond the required 3 spot-checks:** ran a full-population sanity sweep over all 5,258 real 2024
option CSVs (not just the sample) — zero parse errors, zero header-only "fake-real" files, zero
NaN rows, zero non-positive OHLC values, zero internal OHLC-consistency violations (`high < low` or
similar), zero all-zero-volume contracts. 387,467 total data rows, average 73.7 rows/contract (of a
78-79 max) — the shortfall from max is normal (a contract with no trade in a given 5-min bucket
simply has no bar; Alpaca's options bars endpoint doesn't backfill zero-volume buckets).

**Note on the pre-existing draft verification script:** `backtest/tools/_verify_opra_backfill_2024.py`
already existed, untracked, from Friday night — but its methodology only checked "does the day have
any SPY bar at all" and "does the day have any real option file at all," which is exactly the
distinct-expiry-dates-vs-usable-coverage conflation this document warns against. It would have
reported 2024-12-23 as covered. Rewritten 2026-08-02 to perform the same two-part check this
document uses (§3); the numbers in §3's table come from running the rewritten version.

---

## 9. Guard tests

`backtest/tests/test_graduated_guards.py`:

- `test_opra_2024_backfill_verified_floor_2024_01_18` — no real contract files exist for
  2024-01-16 or 2024-01-17 (pre-floor); at least one exists for 2024-01-18 (the floor).
- `test_opra_2025_spy_master_unmutated_by_2024_backfill` — pins the sha256 hash from §6.3.
- `test_opra_cache_resolver_still_anchors_2025_population` — live-imports
  `expand_opra_cache.resolve_spy_master()` and asserts the resolved filename still starts with
  `spy_5m_2025-01-01_`, not a 2024-dated file — catches a silent widening of the population glob.
- `test_opra_2024_spy_bar_severe_gap_2024_12_23` — pins the §4 finding (11 rows, not the full 78)
  so a future silent "fix" of the cache doesn't leave this doc's 239-day figure stale without
  forcing a re-check.
- `test_opra_backfill_doc_discloses_required_facts` — reads this file and asserts the load-bearing
  facts (floor date, both excluded days, the 239 figure, the VIX caveat, the no-auto-extend
  warning) are actually present in the text.

All five are RED-proofed: #1 and #4 assert facts directly falsifiable against the same on-disk
data used throughout this document (a changed file layout flips them). #2 was demonstrated live —
temporarily substituted a wrong hash constant, ran pytest, confirmed RED
(`AssertionError: hash mismatch`), restored the real pinned hash, confirmed GREEN. #3 fails
immediately if `resolve_spy_master()`'s glob pattern is ever broadened past the `2025-01-01`
prefix — demonstrated the same way (temporarily widened the assertion's expected prefix to
something the real resolver doesn't return, confirmed RED, reverted, confirmed GREEN). #5 checks
this file's own text for the load-bearing facts — trivially falsifiable by deleting any one of
them, which was not done to the committed file but is the mechanism the guard relies on.

---

## 10. WARNING — read this before citing "the population" in any new study

**Every A/B scorecard, backtest result, or ratification decision produced before 2026-08-02 was
computed on the 391-day window (2025-01-02..2026-07-31, or whatever the rolling chain's endpoint
was at the time) and does NOT automatically extend to include 2024.** Nothing in the existing
pipeline silently picks up the new 2024 data (§7) — but any *new* study that explicitly opts into
2024 must:

1. **Cite exactly 239 usable days**, not 241 (targeted) or 240 (distinct real expiry-dates) —
   those are different numbers measuring different things (§3).
2. **Disclose 2024 as a separate stratum** in the study's own writeup, even when combined with the
   391-day population for a larger-N run — never a silent concatenation. State which sub-range(s)
   of 2024 the study actually touches.
3. **Exclude or explicitly justify inclusion of** 2024-02-02 and 2024-12-23.
4. **Disclose the VIX granularity cliff** (§5) if the study's gates depend on intraday VIX shape
   for any date in 2024-01-18..2024-07-30.
5. **Re-run `backtest/tools/_verify_opra_backfill_2024.py`** before trusting these numbers if the
   2024 cache has been touched since 2026-08-02 (exit code nonzero = something changed, re-audit
   before citing this doc's figures).

Combined potential population, if a study explicitly opts into both and discloses each stratum
separately: 239 (2024, this doc) + 391 (2025-2026, existing doctrine, unchanged) = **630 days** —
illustrative arithmetic only, not a new blessed single number; compute a study's actual eligible
day count from its own date range and gates.
