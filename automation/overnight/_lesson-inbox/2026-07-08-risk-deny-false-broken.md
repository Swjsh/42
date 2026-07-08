# Lesson candidate: alarm classified rule-enforcement as breakage (2nd false-RED on the same instrument)

**Symptom:** Discord spammed "PLACEMENT BROKEN: 13 attempted, 0 broker-accepted" all afternoon 2026-07-08 while the engine was CORRECTLY refusing entries (RISK_DENY_PDT — day-trade budget spent; fleet arms simultaneously did 12 clean round trips).

**Root cause:** fill_funnel counted RISK_DENY_* as a placement *attempt* (deliberately, for fail-open visibility), so attempted>0 & accepted==0 pattern-matched "broken." Same disease as the 2026-07-07 NOT_FLAT false-RED: the funnel had only two buckets (attempt / skip) for a three-kind world (attempt / skip / RULE-BLOCK). An alarm that cries BROKEN on correct rule enforcement erodes trust in ALL alarms (cry-wolf).

**Fix:** third funnel stage `rule_blocked` + informational RULE-BLOCKED flag, never RED; fail-open preserved (unknown statuses still RED). Guards: test_fill_funnel_guard.py::test_risk_deny_is_rule_block_not_broken + test_unknown_exec_status_still_fails_open_to_red; classifier param cases updated in test_audit_fix_funnel.py.

**Generalization:** when an instrument false-alarms TWICE for the same structural reason (missing category in its state taxonomy), the fix is a new CATEGORY, not another special-case — and each category needs its own verdict semantics (broken / blocked-by-design / idle).
