# Gym validators: no-lookahead-causality (from 2026-06-29 missed-setups post-mortem)

Source: markdown/research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md. N=1 discipline: assert DETECTION on fixtures, arm nothing.

Fixtures = the real 06-29 SPY 5m bars (in the post-mortem). Build crypto/validators/v{NN}_{slug}.py with run_offline()+run_live().

## v_no_lookahead_both_detectors
Both detectors, given prior_bars sliced to the trigger bar, never read bar_idx+1 fields for the DECISION (entry timing reads next bar only as the EXECUTION bar, not the trigger) — C6 causality guard; fails if the detector peeks forward to decide.
