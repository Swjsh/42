# Multi-day DTE compare, extended to 0-4 DTE (2026-09-05)

**Run:** `backtest/.venv/Scripts/python.exe backtest/autoresearch/multiday_dte_compare.py`
(single process, one run). Signal=`vwap_continuation`, ITM-2 strike, premium_stop=-8%,
TP1=+30% — identical config across all buckets (only DTE varies). Window
`2025-01-02..2026-06-16`, OOS=2026. Full JSON:
[`multiday-dte-compare-0to4-2026-09-05.json`](multiday-dte-compare-0to4-2026-09-05.json).

**Change made:** `_dte_expansion_sim.DTE_DIRS` gained `{3: options_3dte, 4: options_4dte}`
(same convention as 1/2-DTE); `multiday_dte_compare.DTE_BUCKETS` extended to
`[0, 1, 2, 3, 4]`; added `check_bucket_coverage()` which prints per-bucket coverage every
run and raises `BucketCacheMissingError` if a bucket fills zero signals or every signal
date has no listed expiry (fail loudly instead of silently reporting an empty result).

## Per-bucket results

| DTE | n | fill_rate | WR% | exp/tr | OOS n | OOS exp/tr | OOS WR% | drop3/tr (full) | null exp | p_null | held-overnight% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 159 | 0.958 | 45.3 | $49.83 | 50 | $37.15 | 40.0 | $43.74 | $0.85 | **0.005** | 0.0 |
| 1 | 166 | 1.000 | 42.8 | $67.25 | 51 | $59.02 | 41.2 | $59.05 | $-1.96 | **0.010** | 0.0 |
| 2 | 165 | 0.994 | 42.4 | $71.57 | 50 | $66.13 | 42.0 | $58.94 | $-2.23 | **0.045** | 1.2 |
| 3 | 165 | 0.994 | 43.6 | $72.07 | 50 | $95.43 | 46.0 | $49.08 | $21.48 | **0.304** | 4.2 |
| 4 | 163 | 0.982 | 38.7 | $19.47 | 49 | $106.10 | 38.8 | $-19.34 | $9.55 | **0.433** | 8.6 |

Coverage was healthy at every bucket (`fill_rate` 0.958-1.000; `no_expiry_listed`
0-2/166; no `BucketCacheMissingError` raised) — the guard did not need to fire on this
window, and it reported so at every bucket (quoted stdout below).

```
    [coverage] DTE=0: signals=166 filled=159 no_expiry_listed=0 cache_miss=7 fill_rate=0.958
    [coverage] DTE=1: signals=166 filled=166 no_expiry_listed=0 cache_miss=0 fill_rate=1.0
    [coverage] DTE=2: signals=166 filled=165 no_expiry_listed=1 cache_miss=0 fill_rate=0.994
    [coverage] DTE=3: signals=166 filled=165 no_expiry_listed=1 cache_miss=0 fill_rate=0.994
    [coverage] DTE=4: signals=166 filled=163 no_expiry_listed=2 cache_miss=1 fill_rate=0.982
```

## /fable-too-good discipline — the headline number does NOT survive scrutiny

The naive read ("OOS exp keeps climbing through 4-DTE, +$68.95/tr vs 0DTE") is the
extraordinary-result pattern this protocol exists to catch. Checked:

- **(a) Look-ahead in the exit** — PASS. `simulate_dte_trade` only reads day-T option
  bars during intraday management (loop breaks the instant `spy_time.date() != entry_day`);
  the multi-day life beyond day T is settled by walking real SPY opens/closes session by
  session via `_sessions_between()`, never a bar the position wouldn't have seen live.
- **(b) Weekend/overnight gaps priced** — PASS. `day_open_close` only contains real
  trading-day bars, so a Friday entry's next session is Monday — one honest gap is
  applied, not a fabricated multi-day one. `held_overnight_pct` rises monotonically with
  DTE (0.0/0.0/1.2/4.2/8.6%) exactly as the mechanism predicts.
- **(c) Cost model for wider spreads** — **CAVEAT, not verified safe.** Entry/exit
  slippage is a flat $0.02/contract constant, identical across every DTE bucket
  (copied from the 0DTE convention). Real-world weekly/monthly contracts are less liquid
  than the highest-volume 0DTE strikes, so this almost certainly **understates** 3/4-DTE
  transaction cost, inflating the apparent edge there relative to 0/1/2-DTE.
- **(d) Random-entry null** — **FAILS at 3/4-DTE. This is the decisive finding.** The
  same-strike/same-exit random-entry null clears significance at 0/1/2-DTE
  (p=0.005, 0.010, 0.045 — a random entry beats the real trigger 0.5-4.5% of the time).
  At 3-DTE and 4-DTE it does NOT clear (p=0.304, p=0.433 — a random entry into the same
  tape matches or beats the real `vwap_continuation` trigger 30-43% of shuffles).
  Combined with 4-DTE's **negative** full-sample drop-top3 ($-19.34) sitting under its
  **highest** OOS exp of the whole sweep ($106.10), the apparent monotone OOS lift into
  3/4-DTE reads as small-sample OOS concentration / generic long-drift capture from
  a multi-day hold in an up-trending 2026 OOS window — not signal-specific edge.

## Recommended leaderboard status

**Stays BLOCKED-ON-DATA — do NOT upgrade to a ratified OP-16 re-score off this run.**
The 3/4-DTE extension of the same signal fails the random-entry null that 0/1/2-DTE
clear, and 4-DTE's own full-sample de-concentration check is negative. Recommend the
candidate's status move toward `NEEDS-MORE-VALIDATION` / `NULL-FAILS-AT-3-4-DTE`, with
the original 1-2 DTE finding (which DOES clear its null) kept as the only validated part
of this thesis. This report does not itself change the leaderboard row — per the task's
hard rule that's left for orchestrator/J review.

**UNVERIFIED / not checked this session:** whether 2DTE's previously-cited regime risk
(random-null failing p=0.0647 in 2026-03..06 per
`strategy/candidates/_analysis/2026-09-03-weekly-dte-not-0dte-stage1-backtest.md`, itself
flagged UNVERIFIED against a primary source there) also affects 3/4-DTE sub-windows —
not re-derived here; would need a sub-window breakout of this same run.
