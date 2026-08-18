# Account Identity Alignment Audit — 2026-08-18

> Follow-up to commit `ac9e84a7` (CLAUDE.md's account table named four identifiers that exist
> nowhere in the system). That fix was narrow (CLAUDE.md + one guard). This audit hunts every
> OTHER tracked-file instance of the same defect class across the whole repo: stale/phantom PA
> account numbers, stale PK key prefixes, stale equity figures presented as current, and
> Safe-2/Bold-2 alias confusion. Method: `git grep` over all tracked files for
> `PA[A-Z0-9]{10}` and `PK[A-Z0-9]{6}`, cross-checked against `automation/state/fleet/
> accounts.json` (registry) and `.mcp.json` (gitignored, read locally, never printed past 8
> chars), plus two parallel research passes reading full file context for every living-doc
> hit. A separate, independent effort (commit `a28175b0`, "consolidate the scattered roadmap")
> landed concurrently during this audit and already fixed `markdown/specs/ARCHITECTURE.md` and
> created `markdown/planning/ROADMAP.md`; this doc cross-references rather than duplicates that
> work.

---

## 1. Canonical identity table (source: `automation/state/fleet/accounts.json`, cross-checked live via `.mcp.json` 2026-08-18)

| Arm ID | Display name | Account # | Alias (canonical) | MCP server / execution | Config | Status |
|---|---|---|---|---|---|---|
| `safe-2` | CORE-SAFE (46VG) | `PA3POKNV46VG` | Gamma-Safe-2 | `alpaca` MCP (key `PKWEWC7N…`) / `mcp_heartbeat` | `automation/state/params.json` | **active** — production core |
| `bold-2` | CORE-BOLD (U67N) | `PA3WEBXJU67N` | Gamma-Bold-2 (NOT "Risky-2" — see §5) | `alpaca_aggressive` MCP (key `PKEZ6OKP…`) / `mcp_heartbeat` | `automation/state/aggressive/params.json` | **active** — production core |
| `safe-1` | RETIRED (=CORE-SAFE acct 46VG) | `PA3POKNV46VG` (shares safe-2's account, by design) | — | `fleet_rest` (status-gated inert) | — | **retired** 2026-07-11 |
| `safe-3` | FLEET-TIGHT-S (T20H) | `PA32T7Q1O20H` | — | `fleet_rest` (custom REST, no MCP) | `accounts.json` params_patch | **active** — fleet |
| `risky-1` | FLEET-FULLSEND-R (V0A4) | `PA3S9N1IV0A4` | — | `fleet_rest` (custom REST) | `accounts.json` params_patch | **active** — fleet |
| `risky-3` | FLEET-LOOSE-R (5H6Z) | `PA3V7JT25H6Z` | — | `fleet_rest` (custom REST) | `accounts.json` params_patch | **active** — fleet, also the probe arm |
| `mes-mnq-div-futures` | FUTURES-DIV (dormant, 3759) | `5WW73759` (TT sandbox) | — | — | `edge3_mesmnq_div.py` | **dormant**, `enabled=false` |
| `mes-linear-sim` | FUTURES-LINEAR (pending, 3759) | `5WW73759` (TT sandbox) | — | — | — | **pending_build** |
| — (not an arm) | CRYPTO-TWIN | `PA38EG1JTFBT` | — | separate 24/7 engine, own state tree | `automation/state/crypto-twin/` | **active**, never re-funded |

**Arm count, confirmed against the registry:** 5 active real-fills arms (safe-2, bold-2, safe-3,
risky-1, risky-3) + 1 retired (safe-1) + 2 futures (1 dormant, 1 pending) + crypto-twin (separate
engine, not a registry arm) = 8 registry entries + 1 non-registry account. `CLAUDE.md:66`'s "5
active real-fills arms" and its fleet doc-string's "Active fleet_rest roster: {safe-3, risky-1,
risky-3} (3, was 4)" both **match this table exactly** — no arm-count contradiction found in any
currently-read doc (checked `CLAUDE.md`, `MAP.md`, `markdown/specs/ARCHITECTURE.md`). The
"variously say 5/3/etc." pattern that motivated hunt item #5 turned out to be **consistent**
once cross-checked — every count found was correct for what it was counting (5 active-real-fills
vs 3 active-fleet_rest vs 6-if-counting-crypto-twin vs 8-if-counting-futures — different
questions, not contradictions).

**Alias confusion (§5) resolved:** `bold-2`'s canonical alias is **Gamma-Bold-2**. "Gamma-Risky-2"
/ "Risky-2" is the account's **pre-2026-07-17 name** (before `ARM-DISPLAY-NAMES.md`'s
display-name scheme). A third, distinct arm (`risky-3`) also legitimately exists, so "Risky-2" is
actively confusable with it — this is the confusion the task flagged, and it is real.

---

## 2. Findings — PA account numbers (hunt #1)

### 2a. STALE-AND-WRONG (never real at any point — a documentation-only error, not a later repoint)

| Number | Claimed to be | Live truth |
|---|---|---|
| `PA3DHPT7KIQE` | Safe-2 / safe-1 | `PA3POKNV46VG` (confirmed via `accounts.json`'s own `_repoint_2026_07_11` doc field AND `automation/state/fleet/live-verified-account-numbers-2026-07-14.json`, which shows `live_account_number: PA3POKNV46VG` / `declared_account_number: PA3DHPT7KIQE` **as far back as its original 2026-07-14 verification** — i.e. even the oldest machine-verified record available shows this number was never real) |
| `PA33W2KUAT40` | Bold-2 | `PA3WEBXJU67N` (same fixture; bold-2 has no repoint history in `accounts.json` at all — this number appears to have simply been a transcription/corruption from inception, not a superseded real value) |

This distinction matters: it is tempting to read these as "the account changed later" (like
§2b below), but the evidence says otherwise — they were wrong from the moment they were first
written down.

### 2b. KNOWN HISTORICAL (were genuinely real, later superseded — fine as dated citations)

| Number | Was | Superseded by | Evidence |
|---|---|---|---|
| `PA3S2PYAS2WQ` | Original safe-2 account | `PA3POKNV46VG` (2026-07-11 repoint, after accidental deletion 2026-07-10) | `accounts.json`'s own `_repoint_2026_07_11` doc |
| `PA32RD49OB0Q` | safe-3, pre-2026-08-02 | `PA32T7Q1O20H` | `live-verified-account-numbers-2026-07-14.json`'s `_doc`: "Refreshed 2026-08-03 after J's full account wipe + $5,000 rebuild (2026-08-02)" |
| `PA3W17FD8G19` | risky-1, pre-2026-08-02 | `PA3S9N1IV0A4` | same |
| `PA31WIU8X15Q` | risky-3, pre-2026-08-02 | `PA3V7JT25H6Z` | same |
| `PA3PHRM47D1J`, `PA35NRWPGKD5` | Inception-era safe/bold accounts (pre-2026-06-15) | superseded by later repoints | old journal entries (2026-05-18 through 2026-06-15), `CLAUDE-md-pre-trim` backups |
| `PA3BP5DZARV2`, `PA3V90ZWCJQ3` | Early-project accounts | unclear, low-traffic | only in `CHANGELOG.md` + one archived queue file; not investigated further (immaterial — both dated/archived contexts only) |
| `PA38EG1JTFBT` | Crypto-twin | **still current** — not superseded. Confirmed unchanged across every dated reference found; `RESET-PLAN-2026-08-01.md` explicitly excludes it from the 2026-08-02 wipe ("DO NOT RESET"). Not an `accounts.json` arm by design (`ARM-DISPLAY-NAMES.md`). |

**The 2026-08-02 reset is the second root cause**, distinct from the CLAUDE.md scar: J did a
full account wipe + $5,000 rebuild on the three `fleet_rest` accounts (safe-3/risky-1/risky-3)
that legitimately orphaned every doc written before that date. Any doc mentioning
`PA32RD49OB0Q`/`PA3W17FD8G19`/`PA31WIU8X15Q` **without a date** is stale for this reason, not the
CLAUDE.md-scar reason.

### 2c. Fixed (documentation, minimal + surgical)

| File | What changed |
|---|---|
| `markdown/infra/ARM-DISPLAY-NAMES.md` | The canonical arm→display-name→account mapping table (the doc `accounts.json` itself points to as "full mapping table") had **every single row wrong** — both scars stacked: safe-2/bold-2 carried the never-real numbers, safe-3/risky-1/risky-3 carried the pre-2026-08-02-wipe numbers. Rewrote the table + every `(last-4)` fragment against `accounts.json`, added a dated correction banner. |
| `markdown/infra/mcp-install.md` | Self-describes as "how the trading rig is wired **today**." Had the wrong account number AND the wrong (further stale — pre-dates even `PKZFN5G3`) key prefix `PK7WRO5T…` for `alpaca`, plus wrong account + `PKQMQD2N…` for `alpaca_aggressive`. Also the "Gamma-Risky-2" mislabel (§5). All corrected to live values verified against `.mcp.json`. |
| `markdown/infra/MCP-401-RESTART-RUNBOOK.md` | Step 1 of the 401-recovery runbook told a future operator to expect key prefixes `PK7WRO5T…`/`PKQMQD2N…` — both wrong. Corrected to `PKWEWC7N…`/`PKEZ6OKP…`. |
| `markdown/infra/ACCOUNT-REPOINT-RUNBOOK.md` | The "Why this exists (the scar)" narrative — describing the SAME 2026-07-11 incident LESSONS-LEARNED L215 covers — misattributed `PA3DHPT7KIQE` as the real pre-repoint safe-1 account. Corrected to `PA3POKNV46VG` with a provenance footnote. (This runbook's own step 4 table, unprompted, already predicted the exact `mcp_audit.py`/`context_audit.py` false-fail bug found in §3 below — good corroborating evidence it was written by someone who understood the consumer graph correctly, just not the account number.) |
| `markdown/0dte/dual-account-design.md` | 3 value-rows (banner + both accounts' "Account #" table cells) carried the never-real numbers. Fixed the numbers; left the "Risky-2" alias and all parameter-table content untouched (frozen 2026-05-14 design-of-record, out of scope per its own banner — matches the treatment `ROADMAP.md`'s contradiction #5 already chose for this file). |
| `markdown/doctrine/LESSONS-LEARNED.md` | L215 (2026-07-14, PDT-inheritance-on-repoint lesson) named `PA3DHPT7KIQE` twice as the repointed account. The lesson's mechanism (PDT count inherited from a reused account) is unaffected by the account number, so corrected to `PA3POKNV46VG` in place, no "corrected" footnote needed (matches how a typo fix is normally handled, not treated as rewriting the lesson). |
| `.claude/skills/mcp-weekly-audit/SKILL.md` + `automation/prompts/mcp-weekly-audit.md` | **This is the live false-alarm bug.** Both files hardcode the wrong account numbers as the audit's PASS condition — see §3, this is the doc-side half of a currently-firing false RED. Corrected both PASS-condition account numbers and the JSON-template example values. |
| `.claude/skills/alpaca-paper-reset/SKILL.md` | The "Live roster" table (used to know WHICH account to delete when re-funding a starved arm) had every fleet_rest number pre-2026-08-02-wipe, plus the never-real safe-2/bold-2 numbers. This is the single highest-consequence fix in this audit — a wrong roster here risks a human deleting the wrong live paper account. Corrected against `accounts.json`; added a note that Alpaca UI labels themselves are unverified post-wipe and must be re-checked by account number, never by memory. |
| `.mcp.json.example` | Template's two `_account_label` placeholder strings said "Gamma-Safe-1" and "Gamma-Risky-2" (neither matches which MCP server they annotate). Cosmetic — no real account numbers or keys in this file — updated for consistency (§5). |
| `CLAUDE.md:67` | Self-contradiction: line 58 (fixed by `ac9e84a7`) says "Gamma-Bold-2 (fleet `bold-2`)"; line 67, ten lines later, still said "does NOT halt **Risky-2**." Same file, same account, two names. Fixed to "Bold-2." |

`markdown/specs/ARCHITECTURE.md` also carried both never-real numbers (§10) — **fixed by the
concurrent `ROADMAP.md`-consolidation effort, commit `a28175b0`**, landed during this audit. Left
untouched here; verified correct against the registry.

### 2d. Flagged, NOT fixed (code — per this audit's explicit rule not to change code behavior)

**CRITICAL — currently causing real, active false alarms:**

| File:line | What's wrong | Impact |
|---|---|---|
| `setup/scripts/mcp_audit.py:71,91,133,134` | `if account_num == "PA3DHPT7KIQE" and status=="ACTIVE"...` — hard equality against a phantom value. **Structurally unsatisfiable**; verdict is always RED regardless of real account health. | Weekly MCP audit permanently broken |
| `setup/scripts/mcp_audit_direct.py:44-45,54-55` | Same pattern, `check_alpaca(safe_env, "PA3DHPT7KIQE")` / `check_alpaca(bold_env, "PA33W2KUAT40")`. Always False → always RED → **fires a Discord alert and writes to `STATUS.md` "Known broken" on every run.** | Actively spamming a false alarm; empirically fired 2026-08-17 (`automation/state/mcp-weekly-audit-log.jsonl:21`: `"verdict":"RED","reason":"...PA3POKNV46VG != PA3DHPT7KIQE...PA3WEBXJU67N != PA33W2KUAT40..."`) |
| `setup/scripts/context_audit.py:98` | `c("Both account numbers present", "PA3DHPT7KIQE" in txt and "PA33W2KUAT40" in txt)` — a CLAUDE.md self-integrity check. Since CLAUDE.md was just correctly fixed to DROP these strings, **this check now false-fails the correct fix.** Consumed by `--verify` (used AFTER an edit) and `--check` (writes `context-budget.json#integrity_ok` every run). | The instrument built to catch doctrine loss now flags the doctrine repair as broken |

These three files need a human (or a future in-scope session) to update their literal string
constants to `PA3POKNV46VG`/`PA3WEBXJU67N`. This is a one-line-per-site fix with no logic change,
but it is still a code edit and this audit's mandate is documentation only.

**Lower severity — offline report-writer tools, not the hot path:**

19 files in `backtest/tools/` and `backtest/autoresearch/` (`bold_fullhist_replay.py`,
`bold_adaptive_sizing_2026_08_02.py`, `bold_selective_fallback_2026_08_02.py`,
`min_contracts_bold_ab_2026_08_02.py`, `engine_fullhist_replay.py`, and 6 `agg_*` + 9 `safe_*`
one-off sweep scripts) write a hardcoded phantom account string into their own generated
`analysis/recommendations/*.json` scorecard output (`out["account"] = "..."` or similar). These
mislabel generated reports; they do not gate any trading decision. Not fixed (code).

`cockpit/server.js:192` declares `const mcp = [...PA3DHPT7KIQE.../PA33W2KUAT40...]` but the array
is never referenced again elsewhere in the file (grep-confirmed) — dead code, does not reach the
dashboard's actual payload. Not fixed (code, and inert regardless).

**JSON state (production config — out of scope, flagged only):**

`automation/state/params.json:12`'s `_pdt_gate_mode_doc` field (non-functional, underscore-
prefixed comment, dated 2026-07-14) states *"Gamma-Safe-2 (`PA3DHPT7KIQE`) is a CASH account --
verified live: multiplier=1"* — both the account number and the multiplier claim are wrong (live
truth is `PA3POKNV46VG` at `multiplier=4`, margin-shaped; see `markdown/planning/ROADMAP.md`
contradiction #3 and `markdown/trading-knowledge/PDT-CLAIM-VERIFICATION-2026-08-18.md`, which
already flagged the multiplier half of this same field 12 days ago and left it uncorrected for
the identical reason — it's a `params.json` edit, outside a docs-only audit's bound). The sibling
field in `automation/state/aggressive/params.json:6` is **already self-corrected** (dated
2026-08-09, explicitly narrates "that account was DELETED in the 2026-08-03 fleet rebuild.
Current bold-2 is `PA3WEBXJU67N`") — only the Safe side needs the same treatment. Not fixed here
(production params, out of bound); this is now flagged in two independent places.

---

## 3. Findings — PK key prefixes (hunt #2)

Verified against `.mcp.json` (gitignored, read locally): `alpaca` → `PKWEWC7N…`, `alpaca_aggressive`
→ `PKEZ6OKP…` (first 8 chars only, per this being a public repo).

| Prefix | Status | Where it still appears (living docs only — dated/archived hits omitted) |
|---|---|---|
| `PKZFN5G3` | Stale (CLAUDE.md's old wrong value) | Only in the existing guard test's own docstring (describing the scar) — clean |
| `PKQMQD2N` | Stale (CLAUDE.md's old wrong value, also `mcp-install.md`/`MCP-401-RESTART-RUNBOOK.md`, both now fixed) | Fixed |
| `PK7WRO5T` | An **even older**, third-generation stale prefix (predates `PKZFN5G3`) | Was live-truth-presented in `mcp-install.md` and `MCP-401-RESTART-RUNBOOK.md` — both fixed. Elsewhere (17 hits) it's comment-only history in `setup/scripts/alpaca_keys.py`/`atomic_bracket_guard.py` (explicitly narrating the 2026-06-21 hardcoded-key incident that `alpaca_keys.py` was built to fix — genuinely historical, correct as-is) plus dated CLAUDE.md backups/archives |
| `PK33J2RV` | A fourth historical Safe key prefix | Comment-only in `backtest/tools/_backfill_opra_2026_05_30_06_18.py` ("the old PK33J2RV... key 401s") — historical, correct as-is |
| `PKGZIUWD` | The retired Safe-1 key (the ORIGINAL hardcoded-credential incident) | Comment-only, same two files as `PK7WRO5T` above — historical, correct as-is |

No PK prefix (current or historical) was found hardcoded into any LIVE comparison/branch outside
`.mcp.json` itself — the `alpaca_keys.py` refactor (2026-06-21 readiness audit) already fixed that
class of bug by making `.mcp.json` the single dynamic source; every remaining mention is either a
comment about that fix's own history, or (now) a corrected doc.

---

## 4. Findings — equity figures (hunt #3)

`CLAUDE.md`'s account table (lines 57-58) already carries current, dated, broker-verified figures
($5,266.38 / $5,048.40, 2026-08-18) — fixed by `ac9e84a7`, still correct at time of this audit.
Searched for the task's flagged examples (`$5,501`, `$1,633`) outside dated/archived paths: every
hit found is either a properly-dated historical trade-analysis reference (equity AT THE TIME of a
specific past trade being analyzed) or an explicitly source-and-dated citation (e.g.
`analysis/deep-research/STRIKE-MATRIX-2026-08-18.md:63`: *"`$5,501` per CLAUDE.md 2026-08-13"* —
honest about its own provenance and date, not a bare current-truth claim). **No stale-and-
presented-as-current equity figure found.** This hunt item came back clean.

---

## 5. Findings — alias inconsistencies (hunt #4)

Canonical (per the now-internally-consistent `CLAUDE.md` + `accounts.json`): **Gamma-Safe-2**
(`safe-2`) and **Gamma-Bold-2** (`bold-2`).

"Gamma-Risky-2" / "Risky-2" was the account's name **before** the 2026-07-17 display-name
rework (`ARM-DISPLAY-NAMES.md`: *"the safe-1/safe-2/safe-3/risky-1/risky-3/bold-2 scheme is
confusing... 'risky' vs 'bold' is inconsistent"*). It is genuinely confusable with the separate,
still-active `risky-3` arm — this is real, not imagined. `git grep` finds **137 hits across ~70
files** using "Risky-2"/"Gamma-Risky-2." The overwhelming majority are legitimately historical
(dated journals, dated `analysis/` reports, `CHANGELOG.md`, archived `STATUS`/`queue` logs) or are
**code** (`backtest/lib/cap_admission.py`, `backtest/lib/live_order_resolver.py`,
`setup/scripts/eod_flatten.py`, `setup/scripts/futures_mirror_shadow.py`,
`setup/scripts/pdt_tracker.py`, `automation/scripts/pre_order_gate.py`) or **production doctrine
prompts** (`automation/prompts/heartbeat.md`, `automation/prompts/aggressive/heartbeat.md`) — both
categories out of this audit's edit scope by the same "no code/behavior changes" rule as §2d, so
not touched. A full mass-rename across 70 files (many of them code) was judged out of scope for a
documentation-alignment audit (scope discipline: smallest correct diff, no drive-by renames) —
this is reported as a finding, not silently fixed everywhere.

**Fixed** (the one true self-contradiction — same file asserting both names for the same account):
`CLAUDE.md:67` ("Risky-2" → "Bold-2", ten lines below the table that already says "Bold-2").
`mcp-install.md`, `ACCOUNT-REPOINT-RUNBOOK.md`'s cross-reference, and `.mcp.json.example`'s
template labels were also normalized to Bold-2 as part of fixing those same files' account
numbers.

**Not fixed** (documented, not renamed): the ~70-file "Risky-2" footprint above. A future
in-scope pass — ideally paired with a `git grep`-driven blast-radius check per
`/fable-blast-radius`, since several hits are inside production prompt doctrine — could rename
the living-doc subset. Not attempted here.

---

## 6. What needs a human (cannot be safely auto-fixed by a docs-only audit)

1. **`setup/scripts/mcp_audit.py` + `mcp_audit_direct.py`** — fix the two hardcoded phantom
   account-number string literals (§2d). This is the single highest-priority follow-up: it is an
   active false alarm firing on a schedule (`Gamma_McpWeeklyAudit`, Sunday 18:30 ET) and polluting
   `STATUS.md`/Discord with a phantom problem that could mask a real one.
2. **`setup/scripts/context_audit.py:98`** — same fix, one string-literal pair.
3. **`automation/state/params.json:12`** (`_pdt_gate_mode_doc`) — correct the account number AND
   reconcile the multiplier=1/cash claim against live multiplier=4/margin truth (already an open
   question in `ROADMAP.md` §7 item 2 / `PDT-CLAIM-VERIFICATION-2026-08-18.md`) — a `params.json`
   edit needs its own review, not a drive-by inside a docs audit.
4. **The ~70-file "Gamma-Risky-2"/"Risky-2" footprint** (§5) — a deliberate rename decision, not
   attempted here given scope + the amount of production-prompt/code surface involved.
5. **19 offline `backtest/tools/`/`backtest/autoresearch/` scripts** (§2d) mislabel their own
   generated JSON reports with a phantom account string — cosmetic, low priority, code.

---

## 7. Guard

`backtest/tests/test_repo_wide_account_ids_2026_08_18.py` (new, sibling to
`test_claude_md_account_ids_2026_08_18.py` which stays CLAUDE.md-scoped). Scans every tracked
`*.md` file for a `PA3`-prefixed account number not present in `accounts.json` (plus one
documented exception, the crypto-twin account), excluding an explicit, individually-justified
allowlist of dated/append-only-history directories and living-tier files that carry a deliberate
"was X, corrected to Y" provenance footnote from this very audit. RED-proofed three ways: (a) a
synthetic `tmp_path` fixture asserting the regex/known-set logic flags a reintroduced phantom
account and does NOT flag a clean one, (b) a real tracked-and-staged scratch file (`git add`,
never committed) proving the full `git ls-files`-driven scan fires end-to-end, then removed, (c)
an allowlist-freshness check asserting every excluded path still exists (catches a stale
exclusion silently masking nothing). Pytest result, run fresh this session:

```
9 passed in 0.46s
```
(both guard files together: `test_repo_wide_account_ids_2026_08_18.py` + the existing
`test_claude_md_account_ids_2026_08_18.py`)

---

## 8. Cross-references

- The originating fix: `CLAUDE.md` commit `ac9e84a7`.
- The concurrent, broader effort this audit reconciles with rather than duplicates:
  `markdown/planning/ROADMAP.md` (esp. §6 "Contradictions found" #5/#6, §8 fold table) and
  `markdown/trading-knowledge/PDT-CLAIM-VERIFICATION-2026-08-18.md`.
- The 2026-08-02 second root cause: `analysis/deep-research/RESET-PLAN-2026-08-01.md`,
  `automation/state/fleet/live-verified-account-numbers-2026-07-14.json`.
- Naming scheme: `markdown/infra/ARM-DISPLAY-NAMES.md`.
