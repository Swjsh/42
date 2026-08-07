# STAGED: regime-attribution self-heal — apply AFTER 15:55 ET 2026-08-07

> Produced by Lane 4 (week-close prep) at ~12:20 ET. Zero judgment left: run the
> blocks below in order. Everything here was verified in-session (patch dry-run
> clean, guard tests GREEN-on-patched / RED-on-original).

**Root cause (one sentence):** `Gamma_RegimeAttribution` (17:45 ET) reads
`analysis/regime-library/day-archetypes.json`, which is only rebuilt premarket
(`Gamma_RegimeStamp` 06:40 ET) or manually — so the target day is never present
at fire time and every session grades `UNTAGGED` (08-05 + 08-06 verified;
`attribution-history.jsonl` holds only the 08-04 manual wiring-day row because
`upsert_history` skips non-OK rows).

## Step 1 — TODAY's insurance (run ~16:30 ET, after the rolling spy_5m file lands ~16:16 ET, BEFORE 17:45)

```powershell
cd C:\Users\jackw\Desktop\42
# pre-check: today's rolling cache file exists (lands ~16:16 ET daily, 40-session cadence)
Get-ChildItem backtest\data\spy_5m_2026-05-19_2026-08-07.csv
backtest\.venv\Scripts\python.exe backtest\tools\build_day_archetypes.py
python -c "import json; d=json.load(open('analysis/regime-library/day-archetypes.json')); print('2026-08-07 in library:', '2026-08-07' in d['days'])"
```

Expected: `2026-08-07 in library: True`. If the cache file has NOT landed, wait
for it (do not substitute another feed — C4/provenance). The 17:45 fire then
grades today OK. **Abort condition:** builder exits non-zero → skip Step 1,
ship Step 2 anyway (self-heal will retry at every future fire), and log to
STATUS.md Known broken.

## Step 2 — durable self-heal (apply once, any time after 15:55 ET)

```powershell
cd C:\Users\jackw\Desktop\42
git apply analysis\deep-research\staged\regime-selfheal-2026-08-07\regime_attribution_selfheal.patch
Copy-Item analysis\deep-research\staged\regime-selfheal-2026-08-07\test_regime_attribution_selfheal_2026_08_07.py backtest\tests\
backtest\.venv\Scripts\python.exe -m pytest backtest\tests\test_regime_attribution_selfheal_2026_08_07.py -q
```

Expected: `3 passed`. (Pre-verified in-session: 3 passed on patched source,
3 failed `AttributeError` on original = RED-proof.)

## Step 3 — commit (scoped, never bare git)

```powershell
python setup\scripts\commit_scoped.py "fix(instruments): regime_attribution self-heals missing target day (rebuild-on-miss); guard test" setup/scripts/regime_attribution.py backtest/tests/test_regime_attribution_selfheal_2026_08_07.py
```

## Revert (one line)

```powershell
git checkout HEAD~1 -- setup/scripts/regime_attribution.py; git rm -q backtest/tests/test_regime_attribution_selfheal_2026_08_07.py
```

(or `git revert <commit>` — the commit touches exactly these two files.)

## Blast radius (checked)

- `regime_attribution.py` consumers: `Gamma_RegimeAttribution` scheduled task
  (16:45 MT wrapper) + `automation/state/regime-attribution.json` readers
  (firm_brief render). The patch only adds a rebuild-on-miss branch inside
  `build_report`; all existing statuses/fields unchanged. Fail-open preserved
  (rebuild failure → same UNTAGGED row as today).
- `build_day_archetypes.py` is deterministic (inputs_sha256-stamped), additive
  by day; the premarket `Gamma_RegimeStamp` rebuild is unaffected.
- NOT trading-path: nothing on the engine hot path reads the archetype library
  intraday.
