> [!DANGER] QUARANTINED — FABRICATED ARTIFACT CLAIMS
> This report names files/commits that do not exist. It was NOT
> accepted as work done. Missing: analysis/data/sec_release_calendar_2026.jsonl
> Checked by setup/scripts/worker_output_verify.py

<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=1.821s | action=harvest-sec-release-calendar -->
<!-- reason: RELEASE-BLACKOUT-FORWARD (HIGH, kill-type, bundle 09-29) is shadow-running and needs a forward read that INCLUDES a T-20 variant per queue.md note ('the forward read must include a T-20 variant as disclosure'); without a precise per-release time ledger the prereg cannot disclose the window's start. Today's ISM/9:41 was missed because R1 starts 09:45. Forager role is fresh (last 2 cycles were critic). -->

```json
{
  "status": "completed",
  "target_file": "analysis/data/sec_release_calendar_2026.jsonl",
  "source_url": "https://www.sec.gov/news/edgar/duedates or official SEC fiscal/reporting calendar feeds / federalregister.gov API mirrors",
  "row_count": 0,
  "date_only_rows": [],
  "verification_status": "SEC release calendars and regulatory filing schedules (such as 10-K, 10-Q, and 8-K deadlines or SEC open meeting schedules) do not publish synchronized minute-by-minute macro release timestamps (like CPI, Payrolls, FOMC, or ISM). SEC filing deadlines are generally bound by rule-based calendar days ending at 5:30 PM ET (or 10:00 PM ET for certain sections), whereas macroeconomic indicators (CPI, Employment Situation, FOMC rate decisions) are published by the BLS, BEA, and Federal Reserve Board respectively.",
  "note": "Per instructions to NOT invent times and to explicitly flag missing exact-minute data, no synthetic macro release calendar rows were written to sec_release_calendar_2026.jsonl since SEC.gov does not govern or schedule FOMC, CPI, Payroll, or ISM releases."
}
```