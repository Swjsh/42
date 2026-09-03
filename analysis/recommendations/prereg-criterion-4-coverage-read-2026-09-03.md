# PREREG — criterion-4 (behavioural) measurement change: read the coverage artifact, not the
# ledger mtime (frozen 2026-09-03, before the reading changes)

> **Status: FROZEN.** Written and committed 2026-09-03, before `go_live_gate.py` criterion 4's
> actual PASS/FAIL byte is touched. Per OP-11 (eval-first) this document exists to state the new
> rule BEFORE the reading changes — a measurement change slipped in without a prereg is the
> post-hoc-bar-change anti-pattern OP-11 bans, and queue.md's
> `CRITERION-4-CANNOT-READ-ITS-OWN-AUDITOR` item explicitly required this file first.
>
> **This file arms nothing.** It changes how one go-live criterion is MEASURED. Arming live
> money remains J's action alone (OP-0 #1).

---

## 1. THE PROBLEM (why the current rule is broken)

`setup/scripts/go_live_gate.py::behavioural_criterion()` (criterion 4) answers "is anyone
auditing rule breaks?" by reading `automation/state/rule-breaks.jsonl`'s **file mtime**. That
ledger is written only when a break is FOUND. `Gamma_RuleBreakAudit` (shipped 2026-09-02, commit
`4689dacd`) now runs nightly and correctly writes **nothing** on a clean night — so the mtime
never advances, and criterion 4 reports `PASS_UNVERIFIED` forever, even on nights that WERE
audited and were genuinely clean. The instrument cannot currently distinguish "clean" from
"nobody is looking."

---

## 2. THE RULE — stated now, before the reading changes

**Current rule (UNCHANGED by this prereg, still in force until the effective date below):**
`rb_status = PASS_UNVERIFIED` whenever `rule-breaks.jsonl`'s mtime predates the trailing
window's start (or the file doesn't exist), regardless of whether an audit ran. `pass` for
criterion 4 stays `(0 breaks in window) AND (0 manual/mixed-attribution fills in window)` —
this file does not touch that boolean, only the honesty-status label around it.

**New rule (takes effect on the date in §4, NOT before):** criterion 4's `PASS` (replacing
`PASS_UNVERIFIED`) requires all three of:

  (a) **0 in-window rule breaks** — unchanged, still read from `rule-breaks.jsonl`.
  (b) **Audited coverage** — `automation/state/rule-break-audit.json` (the coverage artifact
      `Gamma_RuleBreakAudit` writes every run, clean or not) exists, is readable, and its
      `date_range` **covers** the trailing window (`date_range[0] <= window_start` AND
      `date_range[1] >= window_end`).
  (c) **Disclosed rule set** — the gate output states which rules were actually checked
      (`rules_checked`) and which were not (`rules_NOT_checked`), sourced verbatim from the
      artifact, so a PASS can never silently mean "clean on rules nobody checked."

If (b) fails (artifact missing, unreadable, or its range doesn't cover the window), the status
stays `PASS_UNVERIFIED` with a note naming which of (b)/(c) failed — never a bare `PASS`.

---

## 3. WHAT CHANGES vs. WHAT DOES NOT

**Changes (at the effective date):**
- The signal source for "is anyone auditing" moves from `rule-breaks.jsonl` mtime to
  `rule-break-audit.json`'s `date_range` coverage.
- `PASS_UNVERIFIED` can become a real `PASS` on a clean, covered, disclosed window — something
  the current mtime-only rule can never produce.

**Does NOT change, ever, under this prereg:**
- Condition (a) — 0 in-window breaks is still the hard gate; a single logged break still fails
  criterion 4 outright, same as today.
- `overall_verdict` computation shape (`all(g["pass"] for g in groups.values())`) — untouched.
- Any other criterion (1/2/3/5) — untouched.
- No trading-path file (params, heartbeat_core, filters, risk_gate, exit_manager,
  fleet_executor/live, strategies, accounts.json, eod_flatten writers) is touched by this or the
  additive step in §5.

---

## 4. EFFECTIVE DATE

**2026-09-29** — the same safety-checkpoint / config-freeze close already governing this
window (`markdown/infra/DOCTRINE-HOOKS.md` September freeze, `prod-shadow-designation.json`'s
own window end). A gate-measurement change does not ship mid-freeze; it lands at the checkpoint
that already exists for exactly this kind of change, alongside whatever else is reviewed then.

**Before 2026-09-29:** this build ships an **ADDITIVE PREVIEW ONLY** (§5) — criterion 4's actual
`pass`/`status` byte stays computed exactly as today, unchanged, for the rest of the freeze
window. The preview shows what the new rule WOULD say, so its behaviour can be watched for the
rest of the window before it becomes load-bearing.

---

## 5. THE ADDITIVE STEP THIS BUILD SHIPS (2026-09-03)

`criteria.behavioural["coverage_preview"]` — a new, disclosure-only key computed from
`rule-break-audit.json`:

```
coverage_preview: {
  audited_range: [start, end] | null,       # artifact's date_range, verbatim
  covers_window: bool,                       # audited_range covers [w_start, w_end]?
  rules_checked: {...},                      # artifact's rules_checked, verbatim
  rules_not_checked: {...},                  # artifact's rules_NOT_checked, verbatim
  would_pass_under_prereg: bool,              # (a) AND (b) AND (c) above, computed now
  prereg_path: "analysis/recommendations/prereg-criterion-4-coverage-read-2026-09-03.md",
  artifact_status: "ok" | "missing" | "unreadable",
}
```

**Proof obligation (mutation-proof):** with the artifact present vs. deleted/corrupted,
`criteria.behavioural["pass"]` and `["rule_breaks_in_window"]["status"]` must be **byte-identical**
— only `coverage_preview` may differ (and on delete/corrupt it reports `artifact_status:
"missing"`/`"unreadable"` and `would_pass_under_prereg: false`, never crashes, never touches the
real verdict). Rendered in `analysis/go-live-gate.md` as a preview subsection under criterion 4,
also unconditionally.

---

## 6. REVERT

Delete this file and revert the `coverage_preview` addition in `go_live_gate.py` +
`render_markdown()` — both are strictly additive keys, so reverting drops back to the current
mtime-only behaviour with zero residue elsewhere in the report. `git revert` the landing commit.

---

## 7. PROVENANCE

- Filed: queue.md `CRITERION-4-CANNOT-READ-ITS-OWN-AUDITOR`, 2026-09-02.
- Coverage artifact producer: `setup/scripts/rule_break_audit.py` /
  `Gamma_RuleBreakAudit` (shipped `4689dacd`, 2026-09-02).
- Doctrine: OP-11 eval-first / no post-hoc bar changes, OP-33 verify-don't-claim, Rule 9 no
  mid-session rule changes (this is a mid-FREEZE gate-measurement change, held to the same
  standard), OP-0 #1 arming stays J's alone.

*Frozen 2026-09-03. Addenda below this line only if this document is ever revisited.*
